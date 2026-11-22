# Lỗi metadata không nhất quán trong Spring Batch

Spring Batch lưu thông tin vận hành của job và step trong metadata repository thông qua `JobRepository`. Metadata cho biết một job instance đã được tạo hay chưa, những lần thực thi nào đã diễn ra, step nào đã hoàn thành, trạng thái hiện tại là gì và checkpoint nằm ở đâu. Khi các thông tin này không phản ánh cùng một lịch sử thực thi, ứng dụng có thể gặp lỗi khởi chạy, restart, giám sát hoặc khôi phục dữ liệu.

**Metadata không nhất quán** là tình trạng các bản ghi hoặc trạng thái mà Spring Batch sử dụng không còn phù hợp với nhau hay với tiến trình nghiệp vụ thực tế. Nguyên nhân có thể nằm ở transaction, cấu hình database, chạy đồng thời, nâng cấp schema hoặc thao tác thủ công. Cần xác định đúng loại sai lệch trước khi phục hồi, vì sửa nhầm metadata có thể làm mất lịch sử hoặc khiến job xử lý dữ liệu trùng lặp.

## 1. Metadata repository lưu những gì?

Trong cấu hình JDBC phổ biến, Spring Batch lưu metadata trong các bảng có tiền tố `BATCH_`. Các bảng chính thể hiện những phần khác nhau của một lần chạy:

| Bảng | Vai trò |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Lưu danh tính của job instance, được xác định bởi tên job và identifying parameters. |
| `BATCH_JOB_EXECUTION` | Lưu từng lần thực thi của một job instance, gồm trạng thái và các mốc thời gian. |
| `BATCH_JOB_EXECUTION_PARAMS` | Lưu các tham số đã dùng khi khởi chạy execution. |
| `BATCH_STEP_EXECUTION` | Lưu trạng thái, bộ đếm và kết quả của từng step execution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Lưu execution context ở phạm vi job. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Lưu execution context ở phạm vi step. |

Quan hệ logic giữa chúng có thể hình dung như sau:

```text
JobInstance
    |
    +---- JobExecution 1
    |          |
    |          +---- StepExecution A
    |          +---- StepExecution B
    |          +---- JobExecutionContext
    |
    +---- JobExecution 2 (ví dụ lần restart)
               |
               +---- StepExecution A
               +---- StepExecution B
               +---- JobExecutionContext

Mỗi StepExecution có thể có StepExecutionContext riêng.
```

Một `JobInstance` có thể có nhiều `JobExecution`, ví dụ khi một lần chạy thất bại và được restart. Mỗi `StepExecution` thuộc về một `JobExecution` cụ thể. `ExecutionContext` lưu trạng thái cần thiết để các thành phần batch khôi phục tiến độ.

Metadata không phải dữ liệu nghiệp vụ. Ví dụ, bảng đơn hàng chứa các đơn hàng đã nhập; `BATCH_STEP_EXECUTION` lưu số item đã đọc, ghi, bỏ qua hoặc rollback. Hai nơi có thể nằm ở hai database khác nhau và vì vậy có thể xảy ra tình huống một bên đã commit còn bên kia chưa được cập nhật.

## 2. Metadata không nhất quán biểu hiện như thế nào?

Sai lệch có thể xuất hiện dưới nhiều dạng:

- Một execution vẫn có trạng thái `STARTED` dù tiến trình ứng dụng đã dừng từ lâu.
- Job execution và step execution có trạng thái hoặc mốc thời gian không phù hợp với nhau.
- Bản ghi metadata tham chiếu đến instance hoặc execution không còn tồn tại, thường do xóa dữ liệu thủ công hoặc ràng buộc khóa ngoại không được bảo vệ.
- Metadata báo job hoặc step đã hoàn tất nhưng kết quả nghiệp vụ chưa được ghi đầy đủ, hoặc dữ liệu đã được ghi nhưng checkpoint chưa phản ánh điều đó.
- Restart không thể khôi phục `ExecutionContext`, chẳng hạn do dữ liệu context bị thiếu, hỏng hoặc không thể deserialize.
- Ứng dụng không tạo được execution mới vì khóa chính, sequence hoặc unique constraint của metadata bị sai lệch.
- Hai tiến trình cùng cập nhật một execution khiến optimistic locking phát hiện phiên bản dữ liệu đã thay đổi.

Không phải mọi lỗi liên quan đến metadata đều chứng minh database đã hỏng. Chẳng hạn, `JobInstanceAlreadyCompleteException` có thể là kết quả đúng khi ứng dụng cố chạy lại một instance đã hoàn tất. `JobExecutionAlreadyRunningException` có thể cho biết một execution cùng instance đang hoạt động. Trước khi kết luận có sai lệch, cần kiểm tra trạng thái và identifying parameters của job.

## 3. Các nguyên nhân phổ biến

### 3.1. Transaction metadata và transaction nghiệp vụ không đồng bộ

Spring Batch cập nhật metadata trong các thao tác tạo hoặc cập nhật job execution, step execution và checkpoint. Với xử lý theo chunk, transaction thường bao quanh việc đọc, xử lý, ghi một chunk và cập nhật trạng thái cần thiết.

Nếu dữ liệu nghiệp vụ và metadata dùng chung database, cùng transaction manager và được cấu hình để tham gia đúng transaction, các cập nhật có thể được commit hoặc rollback cùng nhau. Nhưng nếu chúng dùng hai datasource hoặc hai transaction manager khác nhau, hai phần có thể commit độc lập.

Ví dụ:

```text
Step xử lý một chunk
       |
       +---- Ghi đơn hàng vào database nghiệp vụ
       |
       +---- Cập nhật checkpoint vào metadata database
                       |
                       v
                Một bên commit,
                bên kia thất bại
```

Nếu dữ liệu nghiệp vụ đã commit nhưng checkpoint chưa commit, lần restart có thể đọc lại một phần dữ liệu và ghi trùng. Nếu checkpoint đã commit nhưng dữ liệu nghiệp vụ chưa được ghi, job có thể bỏ qua những bản ghi chưa thực sự được lưu. Đây là vấn đề về ranh giới transaction giữa các tài nguyên.

### 3.2. Ứng dụng dừng đột ngột

Máy chủ có thể mất điện, container bị kill, JVM crash hoặc kết nối database bị ngắt. Nếu một execution đã ghi trạng thái bắt đầu nhưng không có cơ hội ghi trạng thái kết thúc, metadata có thể vẫn thể hiện `STARTED`.

Trạng thái `STARTED` cũ không tự chứng minh metadata bị hỏng. Có thể job vẫn đang chạy trên một node khác, hoặc tiến trình đã dừng trước khi cập nhật trạng thái cuối. Cần xác minh process, log, host và thời điểm cập nhật cuối cùng trước khi quyết định dừng hoặc restart execution.

### 3.3. Nhiều tiến trình khởi chạy hoặc cập nhật cùng một job

Trong môi trường nhiều node, scheduler hoặc người vận hành có thể gửi yêu cầu khởi chạy đồng thời. Spring Batch dùng `JobRepository`, transaction và cơ chế đồng bộ để bảo vệ việc tạo execution cho cùng một `JobInstance`.

Nếu các node dùng metadata repository riêng, mỗi node có thể tin rằng instance chưa chạy và khởi chạy cùng một công việc. Nếu chúng dùng chung repository nhưng cấu hình transaction hoặc database không phù hợp, có thể phát sinh xung đột khi tạo hoặc cập nhật bản ghi.

Spring Batch cũng sử dụng cơ chế optimistic locking trên các bản ghi execution. Cột phiên bản `VERSION` được dùng để phát hiện cập nhật dựa trên một phiên bản cũ. Khi hai luồng cùng sửa một bản ghi, một thao tác có thể thất bại với lỗi optimistic locking thay vì âm thầm ghi đè dữ liệu mới.

### 3.4. Dùng nhầm database, schema hoặc table prefix

Một ứng dụng có thể vô tình đọc metadata từ database test trong khi job ghi vào database production, hoặc một node dùng datasource/schema khác với node còn lại. Cấu hình table prefix tùy chỉnh cũng có thể khiến ứng dụng đọc một nhóm bảng và ghi vào nhóm bảng khác.

Hệ quả là `JobExplorer` có thể không tìm thấy execution mà `JobLauncher` vừa tạo, hoặc ứng dụng cho rằng chưa có instance trong khi instance thực tế nằm ở schema khác. Đây thường là lỗi cấu hình môi trường hơn là dữ liệu bị hỏng.

### 3.5. Sửa hoặc xóa metadata trực tiếp

Xóa một bản ghi `BATCH_JOB_EXECUTION` nhưng giữ lại `BATCH_STEP_EXECUTION`, hoặc xóa execution context trong khi step cần nó để restart, có thể phá vỡ quan hệ giữa các bản ghi. Nếu database có khóa ngoại, thao tác xóa có thể bị từ chối; nếu constraint bị tắt hoặc không tồn tại, dữ liệu mồ côi có thể xuất hiện.

Việc cập nhật thủ công `STATUS`, `END_TIME`, `VERSION` hoặc các trường khác cũng có thể khiến framework hiểu sai vòng đời execution. Không nên chỉnh sửa trực tiếp các bản ghi metadata chỉ để làm cho job có vẻ như đã hoàn tất hoặc có thể chạy lại.

### 3.6. Nâng cấp Spring Batch nhưng schema không tương thích

Khi nâng cấp phiên bản Spring Batch, schema metadata và cách lưu tham số hoặc execution context có thể thay đổi. Nếu ứng dụng chạy thư viện mới với schema cũ, hoặc nhiều phiên bản ứng dụng cùng ghi vào một schema theo cách không tương thích, có thể xuất hiện lỗi SQL, lỗi ánh xạ cột hoặc lỗi deserialize context.

Hãy dùng schema script và hướng dẫn nâng cấp tương ứng với phiên bản Spring Batch đang chạy. Không nên sao chép schema từ một phiên bản khác hoặc tự đổi tên cột để làm mất lỗi trước mắt.

### 3.7. Sequence, khóa chính và dữ liệu context bị lỗi

Một số hệ quản trị cơ sở dữ liệu dùng sequence hoặc bảng sequence để cấp ID cho job execution và step execution. Nếu giá trị sequence bị đặt lùi so với ID hiện có, thao tác tạo bản ghi mới có thể gặp lỗi duplicate key.

Execution context cũng có thể bị ảnh hưởng nếu dữ liệu lưu trữ bị cắt cụt, serializer thay đổi hoặc class được lưu trong context không còn tương thích sau khi triển khai phiên bản mới. Khi đó, job có thể tìm thấy execution nhưng không khôi phục được trạng thái cần thiết để restart.

## 4. Lỗi thường gặp và cách diễn giải

Thông báo lỗi cần được đọc cùng trạng thái execution và log tại thời điểm phát sinh:

| Lỗi hoặc dấu hiệu | Cách hiểu thường gặp |
| --- | --- |
| `JobExecutionAlreadyRunningException` | Một execution của cùng job instance đang được xem là chạy. Kiểm tra xem nó còn hoạt động hay là trạng thái cũ sau sự cố. |
| `JobInstanceAlreadyCompleteException` | Instance đã hoàn tất với identifying parameters hiện tại. Đây có thể là hành vi đúng, không phải metadata hỏng. |
| `JobRestartException` | Instance hoặc execution không đáp ứng điều kiện restart, hoặc trạng thái lưu không cho phép tiếp tục. |
| `NoSuchJobExecutionException` / `NoSuchJobInstanceException` | Không tìm thấy execution hoặc instance được yêu cầu trong repository mà ứng dụng đang truy vấn. Kiểm tra ID và datasource/schema. |
| `OptimisticLockingFailureException` | Một cập nhật execution dựa trên phiên bản cũ đã bị từ chối vì bản ghi được cập nhật đồng thời. |
| `DuplicateKeyException` | Có thể do tạo execution trùng hoặc sequence/ID của metadata bị lệch. Cần xem constraint và câu SQL gây lỗi. |
| Lỗi deserialize `ExecutionContext` | Dữ liệu context không đọc được với serializer hoặc class hiện tại. Kiểm tra thay đổi phiên bản và dữ liệu đã lưu. |
| Lỗi SQL về bảng hoặc cột metadata | Có thể ứng dụng đang dùng sai schema, thiếu migration hoặc không tương thích phiên bản. |

Tên exception cụ thể có thể khác tùy phiên bản Spring Batch, Spring Framework và database driver. Hãy dùng stack trace và câu SQL thực tế để xác định thao tác thất bại.

## 5. Phân biệt lỗi metadata với lỗi trạng thái job hợp lệ

Trước khi điều tra sâu, cần hiểu một số quy tắc của Spring Batch:

- `JobInstance` được xác định bởi tên job và các identifying `JobParameters`. Thay đổi một identifying parameter tạo instance khác; thay đổi non-identifying parameter không làm đổi danh tính instance.
- Một instance có thể có nhiều `JobExecution`, ví dụ lần chạy đầu `FAILED` và lần restart `COMPLETED`.
- `BatchStatus` mô tả trạng thái vòng đời của framework; `ExitStatus` mô tả mã và thông điệp kết thúc. Hai trường không nhất thiết có cùng giá trị.
- `END_TIME` chưa có giá trị trong một execution đang chạy là bình thường. Với execution đã dừng đột ngột, thời gian kết thúc có thể chưa được ghi nhận.
- Một step đã hoàn tất có thể không chạy lại trong lần restart theo quy tắc mặc định. Đây không phải dấu hiệu metadata thiếu step.

Ví dụ, cùng một job `importOrders` chạy với `businessDate=2026-11-15` sẽ nhắm đến cùng `JobInstance` nếu tham số này là identifying. Nếu instance đã `COMPLETED`, chạy lại cùng tham số có thể bị từ chối. Nếu mục tiêu là nhập dữ liệu của ngày khác, hãy truyền identifying parameter tương ứng thay vì sửa metadata của instance cũ.

## 6. Quy trình chẩn đoán an toàn

Nên điều tra theo thứ tự từ phạm vi rộng đến bản ghi cụ thể. Trước tiên, xác định job name, identifying parameters, execution ID, thời điểm lỗi và node đã chạy job. Thu thập log của ứng dụng và database để biết thao tác nào thất bại.

### Bước 1: Xác định đúng repository

Kiểm tra cấu hình datasource, schema, table prefix và transaction manager của `JobRepository`. Đối chiếu cấu hình giữa các node hoặc profile đang chạy. Nếu ứng dụng dùng nhiều datasource, xác định chính xác datasource nào lưu metadata và datasource nào lưu dữ liệu nghiệp vụ.

### Bước 2: Tra cứu bằng API của Spring Batch

Ưu tiên dùng `JobExplorer` để đọc lịch sử thay vì truy vấn hoặc sửa dữ liệu tùy tiện. Có thể lấy các instance và execution theo job name, sau đó xem trạng thái và step execution liên quan.

```java
List<JobInstance> instances = jobExplorer.getJobInstances("importOrders", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions = jobExplorer.getJobExecutions(instance);
    for (JobExecution execution : executions) {
        System.out.println(
            execution.getId() + " " + execution.getStatus()
                + " " + execution.getStartTime()
                + " " + execution.getEndTime()
        );
    }
}
```

Đoạn code minh họa cách xem execution của một job. Khi điều tra một instance cụ thể, cần so sánh identifying parameters, thời điểm chạy, step execution và execution context. API có thể khác đôi chút giữa các phiên bản thư viện.

### Bước 3: Đối chiếu quan hệ metadata

Khi cần kiểm tra trực tiếp database, chỉ bắt đầu bằng truy vấn đọc. Ví dụ dưới đây dùng tên bảng mặc định và một job name; có thể cần điều chỉnh tên schema, prefix hoặc cú pháp theo database:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_INSTANCE ji
LEFT JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrders'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

Để xem các step thuộc một execution cụ thể:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.START_TIME,
    se.END_TIME,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION se
WHERE se.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY se.STEP_EXECUTION_ID;
```

Các truy vấn này chỉ đọc trạng thái và quan hệ giữa job instance, job execution và step execution. Không dùng kết quả từ một truy vấn đơn lẻ để tự kết luận rằng có thể restart an toàn. Cần đối chiếu với log, node thực thi, transaction và kết quả nghiệp vụ.

### Bước 4: Kiểm tra context và phiên bản schema

Nếu lỗi xảy ra khi restart, kiểm tra execution context có được lưu và đọc thành công hay không. Nếu lỗi bắt đầu sau một lần triển khai, đối chiếu phiên bản Spring Batch, schema migration, serializer và class được lưu trong context. Không chỉnh sửa payload context bằng tay.

### Bước 5: Xác minh dữ liệu nghiệp vụ

So sánh bộ đếm trong `StepExecution` với dữ liệu đích, log của writer và các transaction đã commit. Nếu metadata và dữ liệu nghiệp vụ nằm ở hai hệ thống, cần xem xét khả năng một bên đã commit còn bên kia rollback hoặc mất kết nối.

## 7. Cách phục hồi theo từng tình huống

Không có một thao tác sửa chung cho mọi lỗi metadata. Hướng xử lý phải dựa trên nguyên nhân đã xác định.

### Execution còn STARTED nhưng tiến trình đã dừng

Trước tiên xác nhận không còn node nào thực sự chạy execution đó. Kiểm tra heartbeat, log, process, container và thời điểm cập nhật metadata cuối cùng. Nếu execution vẫn đang hoạt động, dùng cơ chế stop được hỗ trợ thay vì thay đổi trạng thái trong database.

Nếu tiến trình đã chết, xác định execution có thể restart hay cần được đánh dấu abandon theo quy tắc của phiên bản Spring Batch đang dùng. Có thể sử dụng các thao tác vận hành qua `JobOperator` khi trạng thái hiện tại cho phép. Chỉ restart sau khi đã hiểu dữ liệu nào được commit và reader/writer có thể khôi phục an toàn.

### Metadata và dữ liệu nghiệp vụ đã commit lệch nhau

Nếu dữ liệu nghiệp vụ đã được ghi nhưng checkpoint chưa được cập nhật, cần xác định phạm vi dữ liệu có thể bị xử lý lại. Nếu checkpoint đã tiến lên nhưng dữ liệu đích chưa được ghi, cần xác định cách đưa phần dữ liệu bị bỏ qua trở lại luồng xử lý.

Với các thao tác ghi ra hệ thống bên ngoài, nên dùng idempotency key, unique constraint, upsert hoặc cơ chế đối soát phù hợp để việc xử lý lại không tạo dữ liệu trùng. Khi hai tài nguyên không cùng transaction, có thể cần quy trình bù trừ hoặc đối soát nghiệp vụ.

### Schema hoặc cấu hình database không đúng

Sửa cấu hình datasource, schema, prefix hoặc transaction manager theo môi trường thực tế. Nếu schema thiếu migration, thực hiện migration được hỗ trợ cho đúng phiên bản sau khi sao lưu và theo quy trình triển khai database của ứng dụng. Không tự thêm hoặc xóa cột theo phỏng đoán.

### Sequence hoặc khóa chính bị lệch

Xác định cơ chế cấp ID của database và giá trị hiện tại so với các ID đã tồn tại. Chỉ điều chỉnh sequence theo hướng dẫn dành cho đúng database, schema và phiên bản Spring Batch, sau khi có backup và xác nhận không còn tiến trình ghi đồng thời. Không đặt sequence về một giá trị tùy ý.

### Execution context không thể deserialize

Kiểm tra thay đổi class, kiểu dữ liệu, serializer và phiên bản ứng dụng. Nếu có thể, triển khai tương thích ngược để đọc context cũ rồi chuyển đổi theo một quy trình có kiểm soát. Nếu không thể khôi phục context, cần lập kế hoạch chạy lại hoặc xử lý bù dựa trên dữ liệu nghiệp vụ; không xóa context chỉ để vượt qua lỗi khởi chạy.

### Bản ghi metadata bị xóa hoặc chỉnh sửa nhầm

Ngừng các tiến trình có thể tiếp tục ghi vào vùng dữ liệu bị ảnh hưởng. Đối chiếu backup, log database và thời điểm thao tác để xác định những bản ghi bị mất hoặc thay đổi. Khôi phục theo một phương án nhất quán với toàn bộ quan hệ khóa và lịch sử execution. Không tự tạo các hàng giả với trạng thái `COMPLETED` hoặc `FAILED` để làm cho quan hệ trông có vẻ hợp lệ.

## 8. Ngăn ngừa metadata không nhất quán

### Dùng một metadata repository nhất quán

Các node cùng điều phối một nhóm job nên dùng chung repository bền vững và cấu hình thống nhất. Không để từng node ghi metadata vào database riêng nếu chúng cần phối hợp cùng một lịch sử job. Quản lý datasource, schema và table prefix bằng cấu hình tập trung, có kiểm soát theo môi trường.

### Cấu hình transaction rõ ràng

Xác định transaction manager của step và transaction manager của `JobRepository`. Nếu metadata và dữ liệu nghiệp vụ cần tính nguyên tử, hãy thiết kế để chúng tham gia cùng transaction khi kiến trúc cho phép. Nếu chúng nằm ở các tài nguyên độc lập, cần có cơ chế idempotency, đối soát hoặc bù trừ.

### Tránh khởi chạy trùng

Dùng identifying parameters để mô tả đúng đơn vị công việc. Điều phối scheduler và các yêu cầu vận hành để hạn chế khởi chạy đồng thời cùng một instance. Trong môi trường nhiều node, dựa vào repository dùng chung và cơ chế khóa/transaction của Spring Batch; không giả định một khóa trong bộ nhớ của một node có thể điều phối toàn cụm.

### Bảo vệ metadata và backup

Giới hạn quyền ghi trực tiếp vào các bảng `BATCH_*`. Theo dõi thao tác migration, dọn dẹp và thay đổi schema. Sao lưu metadata cùng với dữ liệu nghiệp vụ liên quan, đặc biệt trước khi nâng cấp phiên bản hoặc thực hiện bảo trì lớn.

### Giữ khả năng tương thích khi triển khai

Khi nâng cấp Spring Batch, kiểm tra schema migration, cách lưu `JobParameters` và khả năng đọc lại `ExecutionContext` cũ. Trong giai đoạn rolling deployment, tránh để các phiên bản ứng dụng không tương thích cùng ghi vào một metadata schema.

### Theo dõi trạng thái và cảnh báo

Giám sát execution có trạng thái `STARTED` quá lâu, execution thiếu cập nhật, tỷ lệ restart, optimistic locking failure, lỗi database và chênh lệch giữa bộ đếm xử lý với kết quả nghiệp vụ. Ngưỡng cảnh báo cần dựa trên thời lượng bình thường của từng job, không dùng một mốc thời gian chung cho tất cả.

## 9. Những thao tác cần tránh

- Không xóa hàng trong `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` hoặc các bảng context để ép job chạy lại.
- Không tự sửa `STATUS`, `END_TIME`, `VERSION` hoặc identifying parameters bằng SQL trong môi trường đang vận hành.
- Không restart một execution cũ khi chưa xác nhận tiến trình cũ đã dừng hoàn toàn.
- Không dùng một `JobInstance` đã `COMPLETED` cho một đơn vị nghiệp vụ mới chỉ bằng cách thay đổi metadata.
- Không xóa execution context nếu step cần checkpoint để khôi phục tiến độ.
- Không nâng cấp thư viện mà bỏ qua schema migration và khả năng tương thích dữ liệu context.

Nếu phải thực hiện sửa chữa database ngoài API thông thường, cần có backup có thể phục hồi, kế hoạch dừng ghi, phương án kiểm tra sau phục hồi và sự phê duyệt theo quy trình vận hành của hệ thống. Thao tác phải dựa trên schema và trạng thái cụ thể, không dùng một câu lệnh SQL chung cho mọi trường hợp.

## 10. Ví dụ tình huống: job bị dừng giữa quá trình nhập dữ liệu

Giả sử job `importOrders` xử lý dữ liệu theo chunk 100 đơn hàng. Sau hai chunk, 200 đơn hàng đã được ghi và checkpoint đã lưu. Trong chunk tiếp theo, ứng dụng bị kill đột ngột.

```text
Chunk 1: đọc 1..100     -> ghi thành công -> commit
Chunk 2: đọc 101..200   -> ghi thành công -> commit
Chunk 3: đọc 201..300   -> ứng dụng dừng đột ngột
```

Sau sự cố, metadata có thể còn trạng thái `STARTED` hoặc trạng thái phản ánh lần cập nhật cuối cùng trước khi process dừng. Người vận hành cần:

1. Xác nhận không còn tiến trình `importOrders` nào đang xử lý cùng instance.
2. Xem `JobExecution` và `StepExecution` gần nhất, checkpoint trong `ExecutionContext`, log của reader/writer và transaction đã commit.
3. Đối chiếu database nghiệp vụ để xác nhận 200 đơn hàng đầu đã được ghi đầy đủ và không có phần ghi dở dang ngoài transaction.
4. Xác định reader có thể mở lại nguồn dữ liệu từ checkpoint hay không và writer có xử lý an toàn nếu một chunk được chạy lại hay không.
5. Dùng thao tác restart được hỗ trợ khi execution đủ điều kiện, sau đó theo dõi số lượng bản ghi và trạng thái hoàn tất.

Nếu writer ghi ra một API ngoài database và API đã nhận một số request trong chunk trước khi ứng dụng dừng, metadata checkpoint không thể tự chứng minh request nào đã thành công. Cần đối soát theo mã đơn hàng hoặc idempotency key trước khi gửi lại.

## 11. Nguyên tắc xử lý trong production

Khi gặp lỗi metadata, hãy coi repository là lịch sử vận hành quan trọng của ứng dụng. Xác định đúng job instance và execution, xác minh node đang chạy, kiểm tra datasource và transaction, sau đó đối chiếu metadata với dữ liệu nghiệp vụ. Chỉ chọn phương án stop, restart, abandon, migration hoặc phục hồi backup khi đã hiểu tác động của nó đến checkpoint và dữ liệu đã commit.

`JobRepository` giúp Spring Batch quản lý lịch sử và tiến độ thực thi, nhưng tính nhất quán cuối cùng còn phụ thuộc vào transaction, cấu hình database, cách điều phối nhiều node và thiết kế reader/writer. Bảo vệ metadata, dùng API vận hành phù hợp và thiết kế thao tác nghiệp vụ có thể xử lý lại sẽ giúp job phục hồi đáng tin cậy sau sự cố.
