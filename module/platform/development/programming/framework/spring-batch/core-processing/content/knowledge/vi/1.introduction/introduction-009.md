# Vai trò của metadata repository trong Spring Batch

Trong một ứng dụng Spring Batch, một job không chỉ cần biết phải đọc dữ liệu nào và xử lý dữ liệu ra sao. Framework còn phải biết job đã được khởi chạy hay chưa, đang chạy đến bước nào, lần chạy trước kết thúc như thế nào và có thể tiếp tục sau sự cố hay không. Spring Batch lưu những thông tin vận hành này trong **metadata repository**.

Thành phần trung tâm của cơ chế đó là `JobRepository`. Đây là nơi Spring Batch ghi và truy vấn metadata về job, step và trạng thái thực thi. Metadata repository giúp framework quản lý vòng đời của job, nhận diện một lần chạy logic, hỗ trợ restart và cung cấp dữ liệu cho việc theo dõi vận hành.

## 1. Metadata repository là gì?

Metadata là dữ liệu mô tả quá trình xử lý batch. Ví dụ, metadata có thể cho biết:

- Job nào đã được định nghĩa và một lần chạy thuộc về job logic nào.
- Job được khởi chạy lúc nào, kết thúc lúc nào và có trạng thái gì.
- Step nào đã bắt đầu, step nào đã hoàn thành hoặc thất bại.
- Có bao nhiêu item được đọc, ghi, bỏ qua hoặc rollback.
- Điểm kiểm tra gần nhất của một step để có thể tiếp tục xử lý.

Trong Spring Batch, `JobRepository` là abstraction chịu trách nhiệm lưu và truy xuất các thông tin này. Ứng dụng thường sử dụng repository dựa trên JDBC và một cơ sở dữ liệu quan hệ để metadata vẫn còn sau khi tiến trình ứng dụng dừng hoặc khởi động lại. Cách cấu hình cụ thể phụ thuộc phiên bản Spring Batch và cấu hình ứng dụng.

Metadata repository không phải nơi lưu dữ liệu nghiệp vụ mà job đang xử lý. Chẳng hạn, khi job nhập một triệu đơn hàng, nội dung đơn hàng và kết quả nghiệp vụ thuộc hệ thống dữ liệu của ứng dụng; repository lưu thông tin rằng job đã đọc, xử lý và ghi được bao nhiêu đơn hàng, trạng thái hiện tại ra sao và có thể tiếp tục từ đâu.

## 2. Phân biệt Job, JobInstance và JobExecution

Để hiểu vai trò của repository, cần phân biệt định nghĩa job với một lần thực thi cụ thể.

| Khái niệm | Ý nghĩa |
| --- | --- |
| `Job` | Định nghĩa quy trình batch, gồm một hoặc nhiều step và cách chúng được điều phối. |
| `JobParameters` | Các tham số được truyền vào khi khởi chạy job. Mỗi tham số có thể được đánh dấu là identifying hoặc non-identifying. |
| `JobInstance` | Một lần chạy logic của một job, được xác định bởi tên job cùng các identifying parameters. |
| `JobExecution` | Một lần thực thi cụ thể của một `JobInstance`. Một instance có thể có nhiều execution nếu cần restart sau lần chạy không thành công. |
| `StepExecution` | Thông tin về một lần thực thi cụ thể của một step trong một `JobExecution`. |
| `ExecutionContext` | Vùng lưu trạng thái dạng key-value để các thành phần batch có thể khôi phục tiến độ khi restart. |

Ví dụ, ứng dụng có job `importOrders` để nhập đơn hàng theo ngày. Khi chạy với tham số identifying `businessDate=2026-11-15`, Spring Batch xác định một `JobInstance` tương ứng với job đó và ngày nghiệp vụ đó.

Nếu lần chạy đầu thất bại, lần khởi chạy lại với cùng job và cùng identifying parameters có thể tạo một `JobExecution` mới thuộc cùng `JobInstance`. Repository giữ lại lịch sử của lần chạy trước và metadata cần thiết cho lần restart. Nếu ngày nghiệp vụ thay đổi, đó là một `JobInstance` khác.

Quan hệ này có thể hình dung như sau:

```text
Job: importOrders
  + identifying parameter: businessDate=2026-11-15
                 |
                 v
          JobInstance A
             /     \
            v       v
    JobExecution 1  JobExecution 2
        FAILED       COMPLETED
            |           |
            +-- restart-+

Mỗi JobExecution có các StepExecution tương ứng với những step
được thực thi trong lần chạy đó.
```

`JobInstance` thể hiện danh tính của công việc logic; `JobExecution` thể hiện một lần thử thực hiện công việc đó. Việc tách hai khái niệm giúp Spring Batch phân biệt một job mới với một lần restart.

## 3. Quản lý trạng thái và lịch sử thực thi

Khi job được khởi chạy, Spring Batch tạo và cập nhật các bản ghi metadata thông qua `JobRepository`. Trong suốt vòng đời job, repository lưu trạng thái của job và từng step, cùng các mốc thời gian và bộ đếm xử lý.

Một số trạng thái thường gặp của `BatchStatus` gồm:

| Trạng thái | Ý nghĩa khái quát |
| --- | --- |
| `STARTING` | Job hoặc step đang trong quá trình khởi tạo. |
| `STARTED` | Job hoặc step đang thực thi. |
| `COMPLETED` | Thực thi đã hoàn tất thành công theo trạng thái framework. |
| `FAILED` | Thực thi kết thúc do lỗi. |
| `STOPPING` | Đang xử lý yêu cầu dừng. |
| `STOPPED` | Thực thi đã dừng theo yêu cầu hoặc cơ chế dừng có kiểm soát. |
| `ABANDONED` | Execution được đánh dấu là không tiếp tục restart. |
| `UNKNOWN` | Không thể xác định chắc chắn trạng thái thực thi. |

Spring Batch cũng lưu `ExitStatus`. Hai thông tin này phục vụ mục đích khác nhau:

- `BatchStatus` mô tả trạng thái vòng đời mà framework quản lý, chẳng hạn `COMPLETED` hoặc `FAILED`.
- `ExitStatus` chứa mã kết thúc và thông điệp kết thúc. Ứng dụng có thể dùng exit code để biểu diễn kết quả nghiệp vụ hoặc điều khiển luồng tiếp theo.

Ví dụ, một job có thể hoàn tất về mặt kỹ thuật nhưng phát hiện không có bản ghi mới. Job vẫn có thể có `BatchStatus.COMPLETED`, trong khi `ExitStatus` mang mã riêng như `NO_DATA`. Vì vậy, khi xem lịch sử chạy, không nên coi hai trường này là một.

Metadata của `StepExecution` còn có các bộ đếm như số item đọc, ghi, filter, skip, commit và rollback. Những thông tin này giúp xác định step nào đã xử lý bao nhiêu dữ liệu và hỗ trợ điều tra khi kết quả không như mong đợi.

## 4. Hỗ trợ restart và khôi phục tiến độ

Một vai trò quan trọng của metadata repository là hỗ trợ restart. Job batch có thể chạy trong thời gian dài; tiến trình có thể gặp lỗi do dữ liệu đầu vào, kết nối, tài nguyên hoặc sự cố hạ tầng. Nếu mọi tiến độ chỉ nằm trong bộ nhớ, việc khởi động lại ứng dụng có thể khiến job phải xử lý lại từ đầu.

Spring Batch sử dụng `ExecutionContext` để lưu trạng thái cần thiết cho việc tiếp tục. Có hai phạm vi thường gặp:

- **Job `ExecutionContext`** lưu trạng thái ở phạm vi toàn job, có thể được dùng để chia sẻ thông tin giữa các step hoặc khôi phục luồng xử lý.
- **Step `ExecutionContext`** lưu trạng thái riêng của step, thường được dùng để ghi nhớ điểm đọc hoặc checkpoint của reader.

Với step xử lý theo chunk, framework xử lý một nhóm item rồi commit theo transaction boundary đã cấu hình. Những thành phần hỗ trợ restart, chẳng hạn reader triển khai `ItemStream`, có thể ghi vị trí hiện tại vào `ExecutionContext`. Khi step được restart, trạng thái đã lưu được nạp lại để reader tiếp tục từ vị trí phù hợp.

Ví dụ, một reader đọc file CSV theo từng dòng. Sau khi một chunk được commit, reader có thể lưu số dòng đã đọc. Nếu ứng dụng dừng sau đó, lần restart có thể mở lại file và tiếp tục từ checkpoint thay vì đọc lại toàn bộ file.

```text
Lần chạy đầu
  Đọc dòng 1..100  -> xử lý -> commit
  Đọc dòng 101..200 -> xử lý -> commit
  Đọc dòng 201..   -> xảy ra lỗi
                         |
                         v
               Lưu metadata/checkpoint
                         |
                         v
Lần restart         Khôi phục trạng thái
  Tiếp tục từ checkpoint phù hợp
```

Repository chỉ lưu và cung cấp metadata. Khả năng restart thực tế còn phụ thuộc vào cách thiết kế reader, writer và processor. Thành phần xử lý phải hỗ trợ lưu/khôi phục trạng thái khi cần; các thao tác ghi ra hệ thống bên ngoài cũng nên được thiết kế idempotent hoặc có cơ chế chống ghi trùng. Việc lưu checkpoint không tự động bảo đảm mọi side effect bên ngoài được thực hiện đúng một lần.

`ExecutionContext` nên chứa những giá trị nhỏ, ổn định và cần thiết để tiếp tục xử lý, ví dụ số thứ tự bản ghi hoặc khóa cuối cùng đã xử lý. Không nên dùng nó làm nơi lưu toàn bộ dữ liệu nghiệp vụ hoặc các object lớn.

## 5. Xác định danh tính lần chạy bằng JobParameters

`JobRepository` dựa vào tên job và các `JobParameters` được đánh dấu identifying để xác định `JobInstance`. Do đó, việc chọn tham số identifying ảnh hưởng trực tiếp đến khả năng chạy mới và restart.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

Trong ví dụ này:

- `businessDate` là identifying parameter. Hai lần gọi cùng job với cùng ngày nghiệp vụ sẽ nhắm đến cùng `JobInstance`.
- `requestedBy` là non-identifying parameter. Thay đổi người hoặc nguồn khởi chạy không tạo ra một `JobInstance` mới.

Hãy đánh dấu một tham số là identifying nếu giá trị đó thực sự phân biệt một đơn vị công việc logic. Ví dụ, nếu mỗi file đầu vào là một công việc riêng, tên file hoặc mã lô có thể cần được đánh dấu identifying. Nếu một tham số chỉ ghi nhận thông tin vận hành như người yêu cầu hoặc nhãn theo dõi, nó thường không cần xác định danh tính instance.

Khi một `JobInstance` đã `COMPLETED`, khởi chạy lại cùng job với cùng identifying parameters thường không được xem là một job mới và Spring Batch từ chối việc chạy lại instance đã hoàn tất. Để thực hiện một lượt nghiệp vụ mới, cần cung cấp một identifying parameter mới, chẳng hạn mã lô hoặc phiên bản xử lý. Ngược lại, khi instance kết thúc ở trạng thái có thể restart như `FAILED` hoặc `STOPPED`, việc chạy lại với cùng danh tính có thể tiếp tục instance đó theo quy tắc của Spring Batch.

Thiết kế tham số không phù hợp có thể gây hai vấn đề: vô tình tạo nhiều instance cho cùng một công việc, hoặc vô tình khiến hai công việc khác nhau bị coi là cùng một instance. Vì vậy, cần xác định rõ đơn vị công việc trước khi chọn identifying parameters.

## 6. Hỗ trợ điều phối và tránh chạy trùng

Repository là một phần trong cơ chế điều phối thực thi của Spring Batch. Khi khởi chạy job, framework kiểm tra metadata để biết instance tương ứng đã tồn tại chưa, có execution nào đang chạy không và trạng thái trước đó có cho phép restart không.

Với repository dựa trên cơ sở dữ liệu, các thao tác tạo execution được bảo vệ bằng transaction và cơ chế đồng bộ phù hợp với cấu hình repository, transaction manager và database. Điều này giúp hạn chế hai tiến trình đồng thời tạo các execution xung đột cho cùng một `JobInstance`.

Trong môi trường nhiều node, các node cần dùng chung một metadata repository có cấu hình nhất quán nếu chúng cùng điều phối một nhóm job. Nếu mỗi node ghi vào một kho metadata riêng, chúng không có cùng cái nhìn về lịch sử và trạng thái thực thi; nguy cơ chạy trùng hoặc restart sai sẽ tăng lên.

Repository cũng không thay thế thiết kế chống xử lý trùng ở tầng nghiệp vụ. Với thông điệp, API hoặc hệ thống đích bên ngoài, ứng dụng vẫn cần khóa nghiệp vụ, unique constraint, idempotency key hoặc cơ chế tương đương khi phù hợp.

## 7. Phục vụ giám sát và thao tác vận hành

Metadata repository cung cấp dữ liệu nền cho các công cụ truy vấn và điều khiển job:

- `JobExplorer` cung cấp API chỉ đọc để tra cứu job instance, job execution, step execution và execution context đã lưu.
- `JobOperator` cung cấp các thao tác vận hành ở mức job, chẳng hạn khởi chạy, dừng hoặc restart execution khi đáp ứng điều kiện của framework.

Ví dụ, một trang giám sát có thể dùng metadata để hiển thị thời điểm bắt đầu, thời điểm kết thúc, trạng thái hiện tại, thời lượng chạy và số bản ghi đã xử lý. Khi job thất bại, người vận hành có thể xem execution và step liên quan để tìm vị trí xảy ra lỗi trước khi quyết định restart.

`JobRepository` là thành phần quản lý metadata cốt lõi; `JobExplorer` và `JobOperator` là các abstraction khác giúp ứng dụng đọc hoặc thao tác với lịch sử thực thi. Chúng có liên quan chặt chẽ nhưng không phải cùng một vai trò.

## 8. Metadata thường được lưu ở đâu?

Với cấu hình JDBC phổ biến, Spring Batch lưu metadata trong các bảng thuộc schema batch. Tên bảng mặc định thường có tiền tố `BATCH_`, ví dụ:

| Bảng | Thông tin chính |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Danh tính của các job instance. |
| `BATCH_JOB_EXECUTION` | Các lần thực thi job, trạng thái và mốc thời gian. |
| `BATCH_JOB_EXECUTION_PARAMS` | Các tham số của từng job execution. |
| `BATCH_STEP_EXECUTION` | Trạng thái, bộ đếm và thông tin thực thi của step. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Execution context ở phạm vi job. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Execution context ở phạm vi step. |

Tên bảng, cột và schema cụ thể có thể thay đổi theo phiên bản Spring Batch, database và cấu hình prefix. Khi triển khai, cần dùng đúng script schema tương ứng với phiên bản thư viện và quản lý thay đổi schema cùng vòng đời nâng cấp ứng dụng.

Vì metadata là cơ sở cho restart và giám sát, cơ sở dữ liệu này cần được quản lý như một phần quan trọng của ứng dụng batch. Cần có chính sách backup, phân quyền truy cập và dọn dẹp lịch sử phù hợp. Không nên xóa metadata của những job còn cần khả năng restart hoặc đang được vận hành.

## 9. Những giới hạn cần hiểu đúng

Metadata repository hỗ trợ quản lý thực thi, nhưng không tự giải quyết mọi vấn đề của một hệ thống batch:

- Repository không lưu thay cho dữ liệu nghiệp vụ, file đầu vào hoặc kết quả đầu ra của ứng dụng.
- Có metadata không đồng nghĩa job tự động restart. Job phải được khởi chạy lại và các thành phần xử lý phải hỗ trợ khôi phục.
- Checkpoint không bảo đảm side effect ở hệ thống ngoài được thực hiện đúng một lần. Cần cân nhắc transaction, idempotency và khả năng xử lý lại.
- Metadata chỉ phản ánh chính xác khi ứng dụng ghi nhận trạng thái đúng và repository có cấu hình transaction phù hợp. Nếu metadata và dữ liệu nghiệp vụ nằm ở các transaction manager hoặc hệ thống khác nhau, cần thiết kế cách xử lý tình huống một bên commit còn bên kia thất bại.
- Việc sửa hoặc xóa trực tiếp các bản ghi metadata có thể làm mất khả năng restart hoặc khiến trạng thái job không nhất quán. Nên dùng API và quy trình vận hành của Spring Batch khi thao tác với execution.

## 10. Áp dụng khi thiết kế một job

Khi xây dựng job mới, hãy xác định đơn vị công việc logic trước, sau đó chọn identifying parameters phù hợp. Tiếp theo, quyết định trạng thái nào cần lưu trong `ExecutionContext`, bảo đảm reader hoặc writer có thể khôi phục từ trạng thái đó và kiểm tra cách transaction của metadata phối hợp với transaction xử lý dữ liệu.

Trong môi trường production, nên dùng metadata repository bền vững, được chia sẻ nhất quán giữa các node có cùng trách nhiệm chạy job. Cần theo dõi `BatchStatus`, `ExitStatus`, các bộ đếm của step và lịch sử execution để người vận hành có đủ thông tin điều tra. Cuối cùng, hãy thử tình huống job thất bại giữa chừng rồi restart để xác nhận checkpoint và thao tác ghi dữ liệu hoạt động như dự kiến.

Khi các cơ chế này được cấu hình đúng, metadata repository trở thành nền tảng giúp Spring Batch theo dõi từng lần chạy, phân biệt job mới với job restart, khôi phục tiến độ và hỗ trợ vận hành các quy trình batch một cách có kiểm soát.
