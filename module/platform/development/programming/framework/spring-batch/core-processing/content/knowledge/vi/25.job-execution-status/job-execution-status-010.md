# Không dùng message status thay cho BatchStatus

Trong Spring Batch, trạng thái thực thi của job và step được quản lý bằng `BatchStatus`. Một chuỗi mô tả hoặc message như “đã xử lý xong”, “có 12 bản ghi lỗi” hay “đang chờ đối soát” không thể thay thế trạng thái này.

`BatchStatus` biểu diễn vòng đời thực thi mà framework và `JobRepository` cần để biết execution đang chạy, đã hoàn thành, thất bại hay bị dừng. `ExitStatus` lại biểu diễn kết quả thoát của step/job, gồm một exit code và phần mô tả. Phần message/description dành cho con người đọc; không nên dùng nó làm dữ liệu điều khiển hoặc suy ra trạng thái lifecycle.

Phân biệt đúng ba khái niệm giúp tránh job bị báo sai trạng thái, flow chuyển nhánh sai và hệ thống monitoring hiểu nhầm một execution đã hoàn tất.

## 1. BatchStatus biểu diễn vòng đời execution

`BatchStatus` là enum của Spring Batch dùng để biểu diễn trạng thái thực thi của `JobExecution` và `StepExecution`. Framework cập nhật trạng thái này trong quá trình khởi chạy, thực hiện, dừng và kết thúc job/step.

Các giá trị thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Execution đang trong giai đoạn khởi tạo |
| `STARTED` | Execution đang chạy |
| `STOPPING` | Đã yêu cầu dừng và đang chờ dừng an toàn |
| `STOPPED` | Execution đã dừng theo yêu cầu |
| `COMPLETED` | Execution hoàn tất bình thường |
| `FAILED` | Execution thất bại |
| `ABANDONED` | Execution được đánh dấu không tiếp tục/restart theo quy trình thông thường |
| `UNKNOWN` | Không xác định được trạng thái đáng tin cậy |

Ví dụ, khi một step đang xử lý chunk, `StepExecution.getStatus()` thường là `STARTED`. Khi step kết thúc thành công, trạng thái được cập nhật thành `COMPLETED`; nếu exception không được xử lý làm step thất bại, trạng thái là `FAILED`.

`BatchStatus` không phải nơi lưu mô tả dài về lý do thành công hoặc thất bại. Nó là trạng thái lifecycle có ý nghĩa rõ ràng cho framework, operator và hệ thống giám sát.

## 2. ExitStatus là kết quả thoát của step/job

`ExitStatus` là một đối tượng khác với `BatchStatus`. Nó có hai phần chính:

- `exitCode`: mã kết quả ngắn, có thể là mã chuẩn hoặc mã tùy chỉnh.
- `exitDescription`: nội dung mô tả bổ sung, thường là thông tin dễ đọc cho người vận hành.

Các mã chuẩn thường gặp gồm `COMPLETED`, `EXECUTING`, `NOOP`, `STOPPED`, `FAILED` và `UNKNOWN`. Ứng dụng có thể dùng mã tùy chỉnh để biểu diễn kết quả nghiệp vụ như `COMPLETED_WITH_SKIPS` hoặc `EMPTY_INPUT`.

Ví dụ một step có thể có:

```text
BatchStatus:    COMPLETED
ExitStatus code: COMPLETED_WITH_SKIPS
Exit description: Skipped 12 invalid rows
```

Ý nghĩa: step đã hoàn tất về lifecycle, nhưng kết quả nghiệp vụ cho biết có 12 item bị skip. Mã exit tùy chỉnh có thể được dùng để điều hướng flow; description giúp con người hiểu thêm.

## 3. Message không phải là BatchStatus

Một message như `statusMessage = "Import finished"` chỉ là văn bản. Nó không tự cập nhật `StepExecution` hoặc `JobExecution`, không điều khiển transaction và cũng không làm thay đổi trạng thái lifecycle.

Các cách làm dễ gây nhầm lẫn:

- Ghi “SUCCESS” vào message rồi coi job đã hoàn thành.
- Ghi “FAILED” trong log nhưng `BatchStatus` vẫn là `COMPLETED`.
- Đọc nội dung `exitDescription` để quyết định step tiếp theo.
- Đưa nhiều thông tin biến động vào chuỗi status rồi parse lại ở job flow hoặc monitoring.

Message có thể bị thay đổi cách diễn đạt, dịch ngôn ngữ, thêm thông tin hoặc cắt ngắn. Dùng văn bản tự do để điều khiển hệ thống làm cho logic phụ thuộc vào câu chữ và rất dễ hỏng khi nội dung được chỉnh sửa.

## 4. Ba lớp thông tin cần tách biệt

Khi quan sát một execution, nên tách riêng:

| Thông tin | Đại diện bởi | Dùng để |
|---|---|---|
| Vòng đời thực thi | `BatchStatus` | Biết job/step đang chạy, hoàn thành, thất bại hay dừng |
| Kết quả điều hướng | `ExitStatus.exitCode` | Chọn transition hoặc phân loại kết quả step |
| Giải thích cho con người | `ExitStatus.exitDescription`, log hoặc business message | Cung cấp chi tiết, nguyên nhân và số liệu |

Ví dụ:

```text
BatchStatus = COMPLETED
ExitStatus  = COMPLETED_WITH_SKIPS
Description = "Skipped 12 of 10,000 input records"
```

Không nên gộp ba thông tin này thành một chuỗi duy nhất như `COMPLETED_WITH_SKIPS:12`. Hãy giữ exit code ổn định, số liệu ở counter/metadata phù hợp và message để giải thích.

## 5. Đọc BatchStatus từ JobExecution và StepExecution

Có thể lấy trạng thái lifecycle trực tiếp từ execution object:

```java
BatchStatus jobStatus = jobExecution.getStatus();
BatchStatus stepStatus = stepExecution.getStatus();

if (stepStatus == BatchStatus.FAILED) {
    log.error("Step {} failed", stepExecution.getStepName());
} else if (stepStatus == BatchStatus.COMPLETED) {
    log.info("Step {} completed", stepExecution.getStepName());
}
```

Khi cần kiểm tra trạng thái, dùng enum thay vì so sánh message:

```java
if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
    // Job lifecycle đã hoàn tất bình thường
}
```

Không nên viết:

```java
// Không nên: phụ thuộc vào câu chữ trong message
if ("Job completed successfully".equals(statusMessage)) {
    // Coi job đã hoàn thành
}
```

Thông điệp có thể thay đổi mà không làm thay đổi trạng thái thực thi. Enum cho phép compiler và các API thể hiện rõ ý nghĩa hơn.

## 6. Đọc ExitStatus code và description riêng biệt

Khi cần biết kết quả nghiệp vụ hoặc transition code, truy cập `ExitStatus` và đọc đúng thuộc tính:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();

String exitCode = exitStatus.getExitCode();
String description = exitStatus.getExitDescription();

log.info(
    "Step {} ended with exitCode={} description={}",
    stepExecution.getStepName(),
    exitCode,
    description
);
```

`exitCode` là phần có thể dùng để điều khiển flow. `exitDescription` là phần mô tả. Không dùng `getExitDescription()` để suy ra một mã kết quả bằng cách tìm từ khóa như “success”, “warning” hoặc “failed”.

## 7. Job flow dùng exit code, không dùng message

Các transition trong job flow được chọn dựa trên exit status code của step, không dựa trên `BatchStatus` message hay `exitDescription`.

Ví dụ, nếu một step hoàn tất nhưng có item bị skip, có thể trả exit code tùy chỉnh để chuyển sang bước kiểm tra:

```java
return new JobBuilder("importJob", jobRepository)
    .start(importStep)
        .on("COMPLETED_WITH_SKIPS").to(reviewRejectsStep)
    .from(importStep)
        .on("COMPLETED").to(publishStep)
    .from(importStep)
        .on("FAILED").fail()
    .end()
    .build();
```

Ở đây, pattern trong `.on(...)` khớp với exit code. Chuỗi mô tả như “Skipped 12 invalid rows” không được dùng để chọn transition.

Khi khai báo conditional flow, nên định nghĩa tập exit code nhỏ, ổn định và có ý nghĩa. Luôn có transition dự phòng cho kết quả ngoài dự kiến để job không vô tình đi theo đường thành công.

## 8. Tạo ExitStatus tùy chỉnh mà không sửa BatchStatus

Có thể dùng `StepExecutionListener.afterStep` để trả về exit status tùy chỉnh dựa trên kết quả step. Ví dụ, step hoàn tất nhưng có skip:

```java
public class SkipOutcomeListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {

            return new ExitStatus("COMPLETED_WITH_SKIPS")
                .addExitDescription(
                    "Skipped " + stepExecution.getSkipCount() + " items");
        }

        return null;
    }
}
```

Listener chỉ thay đổi kết quả thoát. `BatchStatus` vẫn do lifecycle của step quản lý. Ví dụ này chỉ gắn mã `COMPLETED_WITH_SKIPS` khi step thực sự đã `COMPLETED`; nếu step `FAILED`, listener không được biến nó thành kết quả thành công.

Khi có nhiều listener cùng thay đổi `ExitStatus`, kết quả cuối cùng được tổng hợp theo cơ chế của Spring Batch. Hãy kiểm tra exit code cuối trong integration test, đặc biệt nếu có listener khác cũng trả về status tùy chỉnh.

## 9. Không dùng exitDescription làm giao thức máy đọc

`exitDescription` hữu ích để bổ sung thông tin như exception summary, cảnh báo, số lượng record hoặc chi tiết vận hành. Nhưng nội dung mô tả không phải giao thức ổn định.

Không nên:

```java
if (stepExecution.getExitStatus()
        .getExitDescription()
        .contains("12 skipped")) {
    // Điều hướng theo chuỗi message
}
```

Thay vào đó, dùng exit code ổn định và lưu số liệu ở nơi phù hợp:

```java
if ("COMPLETED_WITH_SKIPS".equals(
        stepExecution.getExitStatus().getExitCode())) {
    // Xử lý theo mã kết quả đã định nghĩa
}

long skipped = stepExecution.getSkipCount();
```

Nếu cần thêm dữ liệu có cấu trúc, dùng `ExecutionContext`, execution counters, bảng nghiệp vụ hoặc event schema riêng. Không nhồi JSON hoặc chuỗi phân tách tự chế vào message rồi parse lại nếu dữ liệu đó là một phần của hợp đồng hệ thống.

## 10. BatchStatus và ExitStatus có thể khác nhau

`BatchStatus` và `ExitStatus` có quan hệ nhưng không phải hai tên gọi cho cùng một thứ. Một step có thể hoàn tất về lifecycle nhưng mang exit code nghiệp vụ tùy chỉnh.

| BatchStatus | ExitStatus code | Diễn giải |
|---|---|---|
| `COMPLETED` | `COMPLETED` | Hoàn tất bình thường |
| `COMPLETED` | `COMPLETED_WITH_SKIPS` | Hoàn tất nhưng có item bị skip |
| `COMPLETED` | `EMPTY_INPUT` | Hoàn tất hợp lệ với nguồn rỗng |
| `FAILED` | `FAILED` | Step thất bại |
| `STOPPED` | `STOPPED` | Step đã dừng |

Các mã tùy chỉnh cần được thiết kế nhất quán. Không nên tạo exit code thể hiện một lifecycle không đúng, chẳng hạn để step `FAILED` nhưng trả exit code `COMPLETED` chỉ nhằm đi tiếp qua nhánh thành công.

## 11. BatchStatus do framework quản lý

Trong code nghiệp vụ, không nên tùy tiện gán `BatchStatus` để làm cho job trông như đã hoàn thành hoặc thất bại. Framework quản lý vòng đời execution thông qua `JobExecution`, `StepExecution`, step implementation, exception handling, stop request và repository updates.

Ví dụ, không nên làm điều này trong processor hoặc writer:

```java
// Không nên sửa lifecycle status từ logic xử lý item
stepExecution.setStatus(BatchStatus.COMPLETED);
```

Việc sửa status thủ công giữa lúc step còn đang xử lý có thể làm metadata không nhất quán với transaction, exit status, counters và trạng thái thực tế. Nếu muốn điều hướng flow theo kết quả nghiệp vụ, hãy trả về `ExitStatus` tùy chỉnh từ listener hoặc dùng `JobExecutionDecider`.

Nếu cần yêu cầu dừng job, dùng cơ chế stop/abandon/restart phù hợp của Spring Batch và để framework hoàn tất lifecycle. Không biểu diễn yêu cầu dừng bằng cách ghi một message “STOPPED”.

## 12. Lưu trữ metadata trong JobRepository

Với schema JDBC chuẩn của Spring Batch, metadata job và step lưu riêng status, exit code và exit message/description.

| Metadata | Trường điển hình | Nội dung |
|---|---|---|
| Job execution | `STATUS` | Giá trị lifecycle của `BatchStatus` |
| Job execution | `EXIT_CODE` | Exit code của job |
| Job execution | `EXIT_MESSAGE` | Mô tả kết quả hoặc lỗi |
| Step execution | `STATUS` | Giá trị lifecycle của `BatchStatus` |
| Step execution | `EXIT_CODE` | Exit code của step |
| Step execution | `EXIT_MESSAGE` | Mô tả kết quả hoặc lỗi |

Việc tách cột giúp framework và công cụ vận hành đọc đúng loại thông tin. Không ghi chuỗi message vào trường status hoặc tự cập nhật bảng metadata để ép một execution sang trạng thái khác.

Khi truy vấn metadata để monitoring, dùng `STATUS` cho trạng thái lifecycle, `EXIT_CODE` cho phân loại kết quả và `EXIT_MESSAGE` cho chi tiết. Tránh viết truy vấn chỉ tìm từ khóa trong `EXIT_MESSAGE` để xác định job thành công hay thất bại.

## 13. BatchStatus không thay thế exit code nghiệp vụ

Đôi khi `BatchStatus.COMPLETED` chưa đủ để biểu diễn kết quả nghiệp vụ. Ví dụ, step đã chạy xong nhưng nguồn không có dữ liệu, hoặc một số item được skip theo chính sách.

Không nên tạo thêm các giá trị BatchStatus tự đặt như `COMPLETED_WITH_WARNINGS` hoặc `EMPTY`. `BatchStatus` là enum lifecycle chuẩn của framework. Hãy dùng `ExitStatus` tùy chỉnh cho các kết quả này.

Ví dụ các mã exit có thể dùng:

- `COMPLETED`: hoàn tất bình thường.
- `COMPLETED_WITH_SKIPS`: hoàn tất nhưng có item bị skip.
- `EMPTY_INPUT`: nguồn hợp lệ nhưng không có item.
- `REJECTED_INPUT`: đầu vào không đáp ứng chính sách nghiệp vụ.
- `FAILED`: step/job thất bại.

Chọn mã theo nhu cầu điều hướng hoặc báo cáo. Nếu kết quả chỉ cần giải thích cho con người và không ảnh hưởng flow, có thể giữ exit code chuẩn và bổ sung exit description.

## 14. JobExecution và StepExecution có trạng thái riêng

Một job gồm nhiều step, vì vậy trạng thái của một step không nhất thiết giống trạng thái cuối của job tại mọi thời điểm.

Ví dụ:

```text
JobExecution: STARTED
  validateInputStep: COMPLETED
  importRecordsStep: STARTED
  archiveInputStep: chưa chạy
```

Trong lúc `importRecordsStep` đang chạy, job vẫn có thể ở `STARTED`. Sau khi các step hoàn tất, framework cập nhật trạng thái JobExecution dựa trên kết quả toàn job. Không dùng message của một step để kết luận job đã hoàn tất.

Khi chẩn đoán, xem cả job-level và step-level metadata. Job có thể `FAILED` trong khi một số step đã `COMPLETED`; điều đó không có nghĩa metadata bị sai. Nó phản ánh một phần quy trình đã xong trước khi step khác thất bại.

## 15. Dùng status đúng trong API và monitoring

Khi xây dựng REST API, dashboard hoặc alert, hãy trả các trường riêng biệt thay vì một chuỗi status chung.

Ví dụ response có cấu trúc:

```json
{
  "jobName": "dailyImportJob",
  "jobExecutionId": 8452,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED_WITH_SKIPS",
  "exitDescription": "Skipped 12 invalid rows",
  "readCount": 10000,
  "writeCount": 9988,
  "skipCount": 12
}
```

Với cấu trúc này:

- UI dùng `batchStatus` để hiển thị lifecycle.
- Quy tắc điều hướng hoặc phân loại nghiệp vụ dùng `exitCode`.
- Người vận hành đọc `exitDescription` để biết chi tiết.
- Số liệu đọc/ghi/skip lấy từ execution counters.

Không dùng `exitDescription` để thay cho các counter vì message có thể bị thay đổi hoặc bị cắt ngắn. Không dùng `exitCode` thay cho `BatchStatus` vì exit code tùy chỉnh có thể không phản ánh lifecycle.

## 16. Xử lý message lỗi đúng cách

Khi step thất bại, exception và thông tin lỗi có thể được ghi trong exit description hoặc log. Message nên ngắn gọn, hữu ích và không chứa dữ liệu nhạy cảm.

Các nguyên tắc:

- Giữ exception gốc trong log/stack trace để điều tra.
- Dùng exit code ổn định để phân loại lỗi.
- Dùng description để bổ sung thông tin có thể đọc được.
- Không ghi password, token, connection string hoặc toàn bộ payload nhạy cảm.
- Không phụ thuộc vào nội dung message để retry, skip hoặc chuyển flow.
- Tránh message quá dài làm metadata khó đọc hoặc bị giới hạn bởi schema.

Ví dụ description phù hợp: `Partner API timed out after 3 attempts`. Exit code có thể là `FAILED` hoặc mã phân loại lỗi riêng theo thiết kế; BatchStatus vẫn do framework cập nhật dựa trên kết quả thực thi.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghi “SUCCESS” vào message rồi coi job đã hoàn tất | Metadata lifecycle vẫn có thể là `STARTED` hoặc `FAILED` | Đọc `JobExecution.getStatus()` |
| Parse `exitDescription` để chọn transition | Flow phụ thuộc câu chữ và dễ hỏng khi sửa message | Dùng `ExitStatus.exitCode` |
| Dùng `BatchStatus` tùy chỉnh cho kết quả nghiệp vụ | Không tương thích enum lifecycle của framework | Dùng custom `ExitStatus` code |
| Tự gán `BatchStatus.COMPLETED` từ processor/writer | Lifecycle và kết quả thực tế có thể lệch nhau | Để framework quản lý trạng thái |
| Dùng exit code tùy chỉnh như thể nó là BatchStatus | Monitoring có thể phân loại sai | Lưu riêng batchStatus và exitCode |
| Đưa số lượng lỗi vào message rồi parse lại | Dữ liệu không ổn định và khó truy vấn | Dùng skip/read/write counters |
| Dùng một message cho cả API và flow control | UI thay đổi câu chữ có thể làm logic sai | Tách lifecycle, exit code và description |
| Để step FAILED nhưng trả exit code thành công | Flow có thể đi vào nhánh không đúng nghiệp vụ | Chỉ tạo exit code phù hợp với trạng thái thực tế |

## 18. Kiểm thử BatchStatus và ExitStatus

Integration test nên xác nhận riêng lifecycle, exit code và description.

Các trường hợp nên kiểm tra:

1. Step chạy thành công: `BatchStatus.COMPLETED` và exit code chuẩn hoặc tùy chỉnh đúng thiết kế.
2. Step ném exception không được xử lý: `BatchStatus.FAILED` và thông tin lỗi có thể được chẩn đoán.
3. Step có skip: lifecycle hoàn tất nếu policy cho phép, exit code phản ánh kết quả có skip nếu flow cần phân biệt.
4. Step bị stop: trạng thái lifecycle là `STOPPED`, không suy ra từ message.
5. Custom exit code: transition khớp code, không phụ thuộc exit description.
6. Message được thay đổi: flow và monitoring vẫn hoạt động vì không parse câu chữ.
7. Job gồm nhiều step: job-level status được kiểm tra riêng với status của từng step.

Ví dụ assertion:

```java
assertThat(stepExecution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

assertThat(stepExecution.getExitStatus().getExitCode())
    .isEqualTo("COMPLETED_WITH_SKIPS");

assertThat(stepExecution.getExitStatus().getExitDescription())
    .contains("Skipped");
```

Các assertion này kiểm tra ba khía cạnh khác nhau: lifecycle, mã kết quả và phần mô tả. Không nên chỉ assert một message rồi kết luận toàn bộ step đã hoàn tất đúng.

## 19. Quy trình thiết kế status cho một job

Khi thiết kế job hoặc dashboard, hãy xác định:

1. Lifecycle cần theo dõi là trạng thái nào của job và step? Dùng `BatchStatus`.
2. Flow cần phân biệt những kết quả nghiệp vụ nào? Định nghĩa exit code ổn định trong `ExitStatus`.
3. Người vận hành cần biết chi tiết gì? Ghi `exitDescription`, log hoặc event có cấu trúc.
4. Có số liệu định lượng như read/write/skip count không? Dùng execution counters.
5. Có cần điều hướng theo kết quả không? Dùng transition khớp `ExitStatus.exitCode` hoặc `JobExecutionDecider`.
6. Có đang parse message hoặc tự gán BatchStatus không? Loại bỏ sự phụ thuộc đó.
7. Test riêng trạng thái job, trạng thái step, exit code và message.

## Kết luận

Không dùng message hoặc chuỗi status tự do thay cho `BatchStatus`. `BatchStatus` biểu diễn vòng đời thực thi của job/step; `ExitStatus.exitCode` biểu diễn kết quả thoát và có thể điều khiển job flow; `ExitStatus.exitDescription` chỉ bổ sung thông tin dễ đọc cho con người.

Hãy đọc lifecycle bằng `JobExecution.getStatus()` hoặc `StepExecution.getStatus()`, điều hướng bằng exit code ổn định và dùng description/log/counters cho chi tiết. Để Spring Batch quản lý `BatchStatus`, không parse message để suy ra thành công/thất bại và không đặt trạng thái nghiệp vụ tùy chỉnh vào enum lifecycle.
