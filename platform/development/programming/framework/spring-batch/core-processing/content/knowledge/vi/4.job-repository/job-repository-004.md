# Schema repository và bảng metadata

Trong Spring Batch, `JobRepository` là nơi lưu trữ metadata về các Job, lần chạy Job và lần chạy Step. Với cấu hình JDBC, metadata được lưu trong một nhóm bảng quan hệ thường có tiền tố `BATCH_`. Các bảng này giúp Spring Batch nhận diện một Job instance, theo dõi từng lần chạy, ghi nhận trạng thái và bộ đếm, lưu tham số khởi chạy, đồng thời giữ checkpoint để hỗ trợ restart.

Các bảng metadata là nền tảng cho những khả năng quan trọng của Spring Batch: ngăn chạy trùng một Job instance đang hoạt động, xem lịch sử thực thi, điều khiển restart, theo dõi tiến độ và tra cứu lỗi. Vì vậy, schema của repository cần được tạo đúng phiên bản, lưu bền vững và được quản lý như một phần của hạ tầng ứng dụng.

## 1. JobRepository và metadata repository

`JobRepository` là abstraction mà Spring Batch sử dụng để lưu và truy xuất thông tin thực thi. Khi JobLauncher khởi chạy Job, framework dùng repository để tìm hoặc tạo `JobInstance`, tạo `JobExecution`, tạo `StepExecution` và cập nhật trạng thái trong suốt quá trình chạy.

Với JDBC JobRepository, dữ liệu metadata được lưu trong cơ sở dữ liệu quan hệ. Đây là cách triển khai phổ biến trong ứng dụng cần lưu lịch sử qua lần khởi động lại, hỗ trợ nhiều tiến trình hoặc cần công cụ vận hành tra cứu execution.

Metadata repository lưu thông tin điều khiển việc chạy Batch, ví dụ:

- Tên Job và định danh của một Job instance.
- Các JobParameters được dùng để khởi chạy Job.
- Thời điểm bắt đầu, kết thúc và lần cập nhật cuối của mỗi execution.
- Trạng thái `BatchStatus`, `ExitStatus` và thông báo lỗi.
- Số item đã đọc, ghi, lọc, skip, số lần commit và rollback.
- `ExecutionContext` của Job và Step, bao gồm checkpoint phục vụ restart.

Metadata repository không phải nơi lưu toàn bộ dữ liệu nghiệp vụ được xử lý. Đơn hàng, giao dịch, khách hàng hoặc nội dung tệp đầu vào vẫn thuộc database hay hệ thống nghiệp vụ của ứng dụng. Các bảng `BATCH_*` chỉ lưu trạng thái và thông tin cần thiết để điều phối, theo dõi và khôi phục quá trình Batch.

## 2. Các bảng metadata chính

Một JDBC JobRepository tiêu chuẩn thường dùng sáu nhóm bảng sau:

| Bảng | Vai trò |
|---|---|
| `BATCH_JOB_INSTANCE` | Lưu định danh của từng JobInstance. |
| `BATCH_JOB_EXECUTION` | Lưu từng lần chạy của một JobInstance. |
| `BATCH_JOB_EXECUTION_PARAMS` | Lưu các tham số khởi chạy của JobExecution. |
| `BATCH_STEP_EXECUTION` | Lưu từng lần chạy Step thuộc một JobExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Lưu ExecutionContext ở phạm vi JobExecution. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Lưu ExecutionContext ở phạm vi StepExecution. |

Tên bảng có thể thay đổi nếu cấu hình table prefix khác. Ví dụ, prefix `APP_BATCH_` sẽ tạo các tên tương ứng như `APP_BATCH_JOB_INSTANCE` và `APP_BATCH_STEP_EXECUTION`, tùy cấu hình repository.

Sơ đồ quan hệ khái quát:

```text
BATCH_JOB_INSTANCE
  JOB_INSTANCE_ID (PK)
       |
       | 1 - N
       v
BATCH_JOB_EXECUTION
  JOB_EXECUTION_ID (PK)
  JOB_INSTANCE_ID (FK)
       |
       +--------------------------+
       |                          |
       | 1 - N                    | 1 - 1
       v                          v
BATCH_STEP_EXECUTION       BATCH_JOB_EXECUTION_PARAMS
  STEP_EXECUTION_ID (PK)     JOB_EXECUTION_ID (FK)
  JOB_EXECUTION_ID (FK)
       |
       | 1 - 1
       v
BATCH_STEP_EXECUTION_CONTEXT

BATCH_JOB_EXECUTION
       |
       | 1 - 1
       v
BATCH_JOB_EXECUTION_CONTEXT
```

Sơ đồ thể hiện các quan hệ logic chính. Chi tiết khóa, index, kiểu dữ liệu và cách sinh ID phụ thuộc vào script schema dành cho hệ quản trị cơ sở dữ liệu và phiên bản Spring Batch đang sử dụng.

## 3. Bảng BATCH_JOB_INSTANCE

`BATCH_JOB_INSTANCE` lưu một định danh cho mỗi JobInstance. JobInstance được xác định bởi tên Job và tập JobParameters có thuộc tính identifying.

Các cột quan trọng thường gồm:

| Cột | Ý nghĩa |
|---|---|
| `JOB_INSTANCE_ID` | Khóa chính, ID của JobInstance. |
| `VERSION` | Giá trị version phục vụ kiểm soát cập nhật đồng thời. |
| `JOB_NAME` | Tên Job. |
| `JOB_KEY` | Giá trị định danh được tạo từ các identifying JobParameters. |

Thông thường, cặp `JOB_NAME` và `JOB_KEY` được bảo vệ bằng unique constraint để không tạo hai JobInstance trùng định danh. `JOB_KEY` không phải tên hiển thị của Job; nó đại diện cho tập tham số dùng để phân biệt các lần nghiệp vụ.

Ví dụ, Job `dailySettlementJob` được chạy với tham số identifying `businessDate=2026-11-15`. Nếu khởi chạy lại cùng Job name và cùng identifying parameters, Spring Batch tìm lại cùng JobInstance. Nếu ngày nghiệp vụ thay đổi, đó là một JobInstance khác.

Điểm cần nhớ là không phải mọi JobParameter đều nhất thiết tham gia định danh. Những tham số không identifying có thể thay đổi mà không tạo JobInstance mới. Vì thế, khi thiết kế tham số và điều tra lỗi `JobInstanceAlreadyCompleteException` hoặc `JobExecutionAlreadyRunningException`, cần kiểm tra đúng tên Job và identifying parameters.

## 4. Bảng BATCH_JOB_EXECUTION

`BATCH_JOB_EXECUTION` lưu từng lần thực thi của một JobInstance. Một JobInstance có thể có nhiều JobExecution, chẳng hạn lần đầu thất bại và lần sau được restart.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `JOB_EXECUTION_ID` | Khóa chính của JobExecution. |
| `VERSION` | Version phục vụ optimistic locking. |
| `JOB_INSTANCE_ID` | Khóa ngoại đến JobInstance. |
| `CREATE_TIME` | Thời điểm tạo execution. |
| `START_TIME` | Thời điểm bắt đầu thực thi. |
| `END_TIME` | Thời điểm kết thúc, nếu đã kết thúc. |
| `STATUS` | BatchStatus của JobExecution. |
| `EXIT_CODE` | Exit code của kết quả thực thi. |
| `EXIT_MESSAGE` | Mô tả kết quả hoặc thông tin lỗi. |
| `LAST_UPDATED` | Thời điểm metadata được cập nhật gần nhất. |

Một số phiên bản schema cũ có khác biệt về cột thời gian hoặc cách khai báo nullability. Hãy dùng đúng script của phiên bản Spring Batch thay vì giả định mọi phiên bản đều có cấu trúc giống nhau.

Ví dụ, một JobInstance có thể có lịch sử:

| JobExecution | Status | Ý nghĩa |
|---|---|---|
| 9001 | `FAILED` | Lần chạy đầu gặp lỗi khi xử lý dữ liệu. |
| 9002 | `COMPLETED` | Lần restart hoàn tất thành công. |

Hai execution trên cùng tham chiếu một `JOB_INSTANCE_ID`, nhưng có `JOB_EXECUTION_ID` khác nhau. Đây là lý do khi tra cứu lịch sử phải phân biệt JobInstance và JobExecution.

`EXIT_CODE` và `EXIT_MESSAGE` là kết quả được lưu cho execution. Không nên tự sửa các cột này bằng SQL để ép Job thành công hoặc thất bại. Trạng thái phải phản ánh kết quả thực thi thực tế và được cập nhật qua cơ chế của Spring Batch.

## 5. Bảng BATCH_JOB_EXECUTION_PARAMS

`BATCH_JOB_EXECUTION_PARAMS` lưu các tham số được truyền khi khởi chạy một JobExecution. Tham số có thể gồm ngày nghiệp vụ, tên tệp, mã khách hàng, vùng dữ liệu hoặc các giá trị cấu hình khác.

Trong Spring Batch 5, schema chuẩn dùng cấu trúc tham số tổng quát với các cột thường gặp như:

| Cột | Ý nghĩa |
|---|---|
| `JOB_EXECUTION_ID` | JobExecution sở hữu tham số. |
| `PARAMETER_NAME` | Tên tham số. |
| `PARAMETER_TYPE` | Kiểu dữ liệu của tham số. |
| `PARAMETER_VALUE` | Giá trị được lưu dưới dạng biểu diễn phù hợp. |
| `IDENTIFYING` | Đánh dấu tham số có tham gia định danh JobInstance hay không. |

Schema của các phiên bản trước Spring Batch 5 có thể dùng các cột riêng theo kiểu như `STRING_VAL`, `DATE_VAL`, `LONG_VAL`, `DOUBLE_VAL`, cùng các trường tên/kiểu khác. Đây là thay đổi cần đặc biệt lưu ý khi nâng cấp framework. Không nên lấy DDL của Spring Batch 5 để chạy trực tiếp trên ứng dụng Spring Batch 4 hoặc ngược lại.

Ví dụ tham số khởi chạy:

```java
JobParameters jobParameters = new JobParametersBuilder()
        .addString("inputFile", "orders-2026-11-15.csv", true)
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Trong ví dụ này, `inputFile` và `businessDate` được đánh dấu identifying, còn `requestedBy` không tham gia định danh JobInstance. API builder có thể khác đôi chút tùy phiên bản; điều quan trọng là hiểu rõ cờ identifying và dùng kiểu tham số phù hợp.

Khi tra cứu tham số, hãy dùng `JobExplorer` hoặc API metadata của Spring Batch nếu có thể. Cách lưu giá trị và kiểu trong bảng có thể thay đổi theo phiên bản, do đó không nên xây ứng dụng phụ thuộc cứng vào cách giải mã thủ công `PARAMETER_VALUE`.

## 6. Bảng BATCH_STEP_EXECUTION

`BATCH_STEP_EXECUTION` lưu từng lần thực thi Step bên trong một JobExecution. Một JobExecution thường có nhiều StepExecution, tương ứng với các Step trong Job flow.

Các cột phổ biến gồm:

| Cột | Ý nghĩa |
|---|---|
| `STEP_EXECUTION_ID` | Khóa chính của StepExecution. |
| `VERSION` | Version dùng cho optimistic locking. |
| `STEP_NAME` | Tên Step. |
| `JOB_EXECUTION_ID` | Khóa ngoại đến JobExecution cha. |
| `CREATE_TIME`, `START_TIME`, `END_TIME` | Các mốc thời gian của StepExecution. |
| `STATUS` | BatchStatus của StepExecution. |
| `COMMIT_COUNT` | Số lần commit. |
| `READ_COUNT` | Số item đọc thành công. |
| `FILTER_COUNT` | Số item bị processor lọc. |
| `WRITE_COUNT` | Số item đã ghi. |
| `READ_SKIP_COUNT` | Số item bị skip ở reader. |
| `PROCESS_SKIP_COUNT` | Số item bị skip ở processor. |
| `WRITE_SKIP_COUNT` | Số item bị skip ở writer. |
| `ROLLBACK_COUNT` | Số lần rollback. |
| `EXIT_CODE`, `EXIT_MESSAGE` | Kết quả và mô tả kết thúc Step. |
| `LAST_UPDATED` | Thời điểm cập nhật metadata gần nhất. |

Các bộ đếm trong bảng giúp theo dõi tiến độ và phân tích lỗi. Chẳng hạn, nếu `READ_COUNT` cao nhưng `WRITE_COUNT` thấp, cần xem xét processor có lọc nhiều item hay chính sách skip có đang được áp dụng. Nếu `ROLLBACK_COUNT` tăng bất thường, cần điều tra transaction, lỗi writer, deadlock hoặc timeout.

Không nên tự suy ra số item được xử lý thành công chỉ từ một bộ đếm. Cần kết hợp `READ_COUNT`, `FILTER_COUNT`, các skip count, `WRITE_COUNT`, log lỗi và kết quả thực tế ở hệ thống nghiệp vụ.

## 7. Hai bảng ExecutionContext

Spring Batch lưu trạng thái trong `ExecutionContext` để hỗ trợ chia sẻ dữ liệu thực thi và restart. JDBC JobRepository lưu context ở hai phạm vi khác nhau.

### BATCH_JOB_EXECUTION_CONTEXT

Bảng này lưu ExecutionContext thuộc JobExecution. Nó phù hợp với thông tin cần chia sẻ giữa các Step trong cùng một lần chạy Job, ví dụ mã đợt import hoặc kết quả chuẩn bị mà Step sau cần đọc.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `JOB_EXECUTION_ID` | Khóa chính và khóa ngoại đến JobExecution. |
| `SHORT_CONTEXT` | Biểu diễn context rút gọn được lưu trong metadata. |
| `SERIALIZED_CONTEXT` | Phần context được serialize đầy đủ, tùy schema và độ dài dữ liệu. |

### BATCH_STEP_EXECUTION_CONTEXT

Bảng này lưu ExecutionContext thuộc StepExecution. Đây thường là nơi reader, writer hoặc Tasklet giữ checkpoint riêng, chẳng hạn vị trí dòng đã đọc, số trang tiếp theo hoặc trạng thái nội bộ cần phục hồi.

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| `STEP_EXECUTION_ID` | Khóa chính và khóa ngoại đến StepExecution. |
| `SHORT_CONTEXT` | Biểu diễn context rút gọn. |
| `SERIALIZED_CONTEXT` | Dữ liệu context serialize đầy đủ nếu schema sử dụng cột này. |

`ExecutionContext` được serialize trước khi lưu. Cấu trúc cụ thể phụ thuộc serializer và schema của phiên bản. Không nên đọc hoặc chỉnh sửa chuỗi serialized trực tiếp bằng SQL như thể đó là dữ liệu nghiệp vụ thông thường.

Chỉ lưu dữ liệu cần thiết để khôi phục hoặc chia sẻ trạng thái thực thi. Không nên lưu toàn bộ danh sách hàng triệu item hoặc dữ liệu nghiệp vụ lớn trong context. Hãy lưu khóa, vị trí, số trang hay checkpoint gọn nhẹ; dữ liệu chính vẫn nằm trong nguồn lưu trữ nghiệp vụ.

## 8. Khóa chính, khóa ngoại, unique constraint và index

Các ràng buộc trong schema giúp bảo vệ quan hệ giữa các bản ghi metadata.

### Khóa chính

Mỗi bảng execution có một ID riêng. Ví dụ `JOB_EXECUTION_ID` nhận diện một JobExecution, còn `STEP_EXECUTION_ID` nhận diện một StepExecution. Các ID này giúp framework liên kết trạng thái và context chính xác với lần thực thi tương ứng.

### Khóa ngoại

Các quan hệ thường gặp:

- `BATCH_JOB_EXECUTION.JOB_INSTANCE_ID` tham chiếu `BATCH_JOB_INSTANCE.JOB_INSTANCE_ID`.
- `BATCH_STEP_EXECUTION.JOB_EXECUTION_ID` tham chiếu `BATCH_JOB_EXECUTION.JOB_EXECUTION_ID`.
- `BATCH_JOB_EXECUTION_PARAMS.JOB_EXECUTION_ID` tham chiếu JobExecution tương ứng.
- `BATCH_JOB_EXECUTION_CONTEXT.JOB_EXECUTION_ID` tham chiếu JobExecution tương ứng.
- `BATCH_STEP_EXECUTION_CONTEXT.STEP_EXECUTION_ID` tham chiếu StepExecution tương ứng.

Khóa ngoại giúp ngăn metadata mồ côi và giữ tính toàn vẹn quan hệ. Khi dọn dữ liệu lịch sử, phải tuân thủ quan hệ này và thứ tự xóa phù hợp. Không xóa một JobInstance hoặc JobExecution cha khi vẫn còn các bản ghi con phụ thuộc.

### Unique constraint và index

Unique constraint trên tên Job và Job key giúp đảm bảo một định danh JobInstance không bị tạo trùng. Các index trên khóa ngoại và trường truy vấn thường dùng hỗ trợ tra cứu JobExecution, StepExecution và lịch sử thực thi.

Không tự ý bỏ unique constraint hoặc index để xử lý lỗi khởi chạy đồng thời. Nếu gặp xung đột, cần xác định nguyên nhân từ JobParameters, transaction hoặc việc có nhiều launcher khởi chạy cùng một JobInstance.

## 9. Sequence và cách sinh ID

Các bảng metadata cần ID duy nhất cho JobInstance, JobExecution và StepExecution. Cách sinh ID phụ thuộc vào hệ quản trị cơ sở dữ liệu và script schema tương ứng.

Một số script sử dụng database sequence, thường có tên như:

- `BATCH_JOB_SEQ`
- `BATCH_JOB_EXECUTION_SEQ`
- `BATCH_STEP_EXECUTION_SEQ`

Một số database hoặc script khác dùng identity/auto-increment hoặc cơ chế sinh khóa riêng. Không phải hệ quản trị nào cũng có cùng đối tượng sequence hoặc cùng cú pháp DDL.

Khi cài đặt schema, hãy dùng đúng script được đóng gói cho database đang sử dụng. Không sao chép phần tạo sequence từ Oracle sang MySQL hoặc ngược lại. Nếu sequence bị thiếu, sai tên hoặc không được cấp quyền, JobRepository có thể không tạo được execution dù các bảng chính đã tồn tại.

## 10. Cài đặt schema metadata

Spring Batch cung cấp script schema cho nhiều hệ quản trị cơ sở dữ liệu. Các script thường có trong artifact Spring Batch, dưới package schema của thư viện, với tên theo nền tảng database. Ví dụ, nhóm script có thể phân biệt H2, HSQLDB, MySQL, PostgreSQL, Oracle, SQL Server và các hệ quản trị khác tùy phiên bản phát hành.

Nguyên tắc quan trọng là dùng schema script đi kèm đúng phiên bản Spring Batch. Cấu trúc bảng, kiểu dữ liệu, tên cột, sequence và constraint có thể thay đổi giữa các phiên bản.

### Spring Boot tự khởi tạo schema

Với Spring Boot, thuộc tính cấu hình `spring.batch.jdbc.initialize-schema` điều khiển việc khởi tạo schema Batch trong các môi trường được hỗ trợ. Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| `embedded` | Khởi tạo schema cho embedded database theo chính sách mặc định của Boot. |
| `always` | Yêu cầu chạy script khởi tạo schema. |
| `never` | Không tự khởi tạo schema. |

Ví dụ cấu hình:

```yaml
spring:
  batch:
    jdbc:
      initialize-schema: always
```

Thiết lập `always` hữu ích trong môi trường phát triển hoặc thử nghiệm cần dựng database nhanh. Trong production, nên quản lý DDL bằng quy trình migration có kiểm soát, xác định rõ thời điểm triển khai và phiên bản schema. Không nên để ứng dụng tự chạy lại script tạo bảng trên database đang chứa metadata cần giữ.

### Khởi tạo thủ công bằng script

Có thể lấy script phù hợp từ thư viện Spring Batch và chạy bằng công cụ quản trị database hoặc công cụ migration của dự án. Trước khi thực hiện, cần xác định:

- Database engine và phiên bản đang dùng.
- Phiên bản Spring Batch thực tế trong dependency tree.
- Schema/database owner và quyền tạo bảng, sequence, index.
- Table prefix được cấu hình cho repository.
- Các bảng hoặc đối tượng metadata đã tồn tại hay chưa.
- Môi trường có cần giữ dữ liệu execution cũ hay là database mới hoàn toàn.

Nếu schema đã tồn tại, không chạy script khởi tạo một cách mù quáng. Script tạo bảng thường không phải script nâng cấp dữ liệu. Cần dùng migration tương ứng với phiên bản hoặc thực hiện quy trình nâng cấp đã được kiểm thử.

## 11. Cấu hình table prefix và schema riêng

Tên bảng mặc định thường bắt đầu bằng `BATCH_`. Trong một số hệ thống, cần đổi prefix để phân biệt nhiều ứng dụng, nhiều repository hoặc tránh xung đột tên bảng.

Ví dụ về cấu hình prefix:

```yaml
spring:
  batch:
    jdbc:
      table-prefix: APP_BATCH_
```

Tên bảng được repository sử dụng phải khớp với tên đã tạo trong database. Nếu cấu hình prefix là `APP_BATCH_` nhưng script chỉ tạo bảng `BATCH_`, JobRepository sẽ báo lỗi không tìm thấy bảng.

Prefix là phần tiền tố tên bảng, không đồng nghĩa với database schema hoặc catalog. Nếu muốn đặt bảng trong schema riêng, cần cấu hình datasource, quyền truy cập hoặc tên đối tượng theo khả năng của database và cấu hình ứng dụng. Không nên giả định đổi table prefix sẽ tự chuyển bảng sang một schema khác.

Trong Java configuration tùy biến JDBC JobRepository, table prefix cũng có thể được cấu hình trên factory/repository infrastructure tương ứng. Với Spring Boot, ưu tiên cấu hình property được phiên bản Boot hỗ trợ để tránh tạo hai cấu hình repository mâu thuẫn.

## 12. Transaction và tính nhất quán của metadata

JobRepository không chỉ là nơi lưu lịch sử. Các thao tác tạo và cập nhật metadata tham gia vào cơ chế điều phối thực thi của Spring Batch.

Ví dụ, khi bắt đầu Job, framework cần xác định JobInstance đã tồn tại hay chưa, có JobExecution đang chạy hay không và có được phép tạo execution mới không. Ràng buộc unique cùng transaction và isolation phù hợp giúp tránh hai tiến trình tạo cùng một JobInstance ngoài ý muốn.

Các bản ghi execution còn có trường `VERSION` để hỗ trợ optimistic locking. Khi một tiến trình cố cập nhật metadata dựa trên version cũ, repository có thể phát hiện xung đột thay vì âm thầm ghi đè trạng thái mới hơn.

Một số cấu hình JDBC JobRepository cho phép điều chỉnh isolation level cho thao tác tạo execution. Mức mặc định và cách cấu hình phụ thuộc phiên bản/cách dựng repository. Chỉ thay đổi isolation sau khi hiểu tải đồng thời, hành vi database và lỗi thực tế; không nên hạ mức cô lập chỉ để che giấu lỗi xung đột tạo JobInstance.

Metadata repository thường được cấu hình với transaction manager phù hợp với database lưu metadata. Nếu dữ liệu nghiệp vụ nằm ở database khác, cần hiểu rõ transaction boundary giữa metadata và business data. Một transaction manager JDBC không tự tạo ra transaction phân tán giữa nhiều database hoặc hệ thống HTTP.

## 13. Truy vấn metadata để theo dõi Job

Trong vận hành, có thể dùng `JobExplorer` để truy vấn metadata bằng API Spring Batch. Đây là lựa chọn phù hợp khi cần xem execution, danh sách StepExecution và trạng thái mà không phụ thuộc trực tiếp vào cấu trúc SQL của từng phiên bản.

SQL cũng hữu ích cho báo cáo hoặc điều tra. Các truy vấn dưới đây chỉ minh họa trên schema có tên bảng và cột phổ biến; cần điều chỉnh theo script thực tế của phiên bản.

### Liệt kê các lần chạy Job gần đây

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Truy vấn nối JobInstance với các lần chạy tương ứng. Một JobInstance có thể xuất hiện nhiều dòng nếu đã có nhiều JobExecution.

### Xem các Step của một JobExecution

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = 9002
ORDER BY STEP_EXECUTION_ID;
```

Truy vấn này giúp xác định Step nào đã chạy, trạng thái ra sao và các bộ đếm có bất thường hay không. Thay ID minh họa bằng `JOB_EXECUTION_ID` cần điều tra.

### Tra cứu tham số của một execution

Với schema Spring Batch 5, có thể xem các trường tham số mới:

```sql
SELECT
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = 9002;
```

Nếu ứng dụng dùng schema cũ, cần điều chỉnh truy vấn theo cấu trúc tham số của phiên bản đó. Không nên dùng một câu SQL duy nhất cho mọi phiên bản Spring Batch.

### Dùng API thay cho SQL trực tiếp

Ví dụ đọc một JobExecution bằng `JobExplorer`:

```java
@Service
public class BatchMetadataService {

    private final JobExplorer jobExplorer;

    public BatchMetadataService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printExecution(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null) {
            return;
        }

        System.out.println("Job: " + execution.getJobInstance().getJobName());
        System.out.println("Status: " + execution.getStatus());

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf("%s: %s, read=%d, write=%d%n",
                    step.getStepName(),
                    step.getStatus(),
                    step.getReadCount(),
                    step.getWriteCount());
        }
    }
}
```

`JobExplorer` là API đọc metadata. `JobRepository` chịu trách nhiệm lưu và cập nhật metadata trong quá trình thực thi. Khi một execution đang chạy, dữ liệu được đọc từ repository có thể phản ánh lần cập nhật gần nhất chứ không nhất thiết là trạng thái tức thời trong bộ nhớ của tiến trình.

## 14. Nâng cấp schema khi đổi phiên bản Spring Batch

Schema metadata là một phần của hợp đồng giữa phiên bản Spring Batch và database. Khi nâng cấp framework, cần kiểm tra thay đổi DDL trước khi triển khai.

Một ví dụ đáng chú ý là cấu trúc `BATCH_JOB_EXECUTION_PARAMS`: Spring Batch 5 chuyển sang cách lưu tham số tổng quát với tên, kiểu, giá trị và cờ identifying; các phiên bản cũ dùng các cột giá trị theo từng kiểu dữ liệu. Vì vậy, việc chỉ nâng dependency mà giữ nguyên schema cũ có thể gây lỗi khi đọc hoặc ghi JobParameters.

Quy trình nâng cấp nên gồm:

1. Xác định phiên bản Spring Batch hiện tại và phiên bản đích.
2. Đọc hướng dẫn migration và schema script của phiên bản đích.
3. Sao lưu metadata database trước khi thay đổi.
4. Tạo migration DDL/DML phù hợp với dữ liệu đang có; không xóa lịch sử nếu nghiệp vụ cần giữ.
5. Thử migration trên bản sao database với dữ liệu đại diện.
6. Triển khai migration và ứng dụng theo thứ tự đã định, tránh để hai phiên bản ứng dụng không tương thích cùng ghi một schema.
7. Kiểm tra khởi chạy Job, lưu tham số, tạo StepExecution, cập nhật context và restart trên môi trường thử nghiệm.

Không nên sửa schema thủ công theo phỏng đoán hoặc chép một file `schema-*.sql` của phiên bản mới lên database production đang hoạt động. Script khởi tạo thường dành cho database trống; migration nâng cấp cần bảo toàn và chuyển đổi dữ liệu metadata hiện hữu.

## 15. Quản lý schema và dữ liệu metadata trong production

Metadata repository cần được vận hành như một database quan trọng của ứng dụng Batch.

### Quyền truy cập

Tài khoản ứng dụng cần quyền đọc, ghi và cập nhật các bảng/sequence cần thiết. Tài khoản migration có thể cần quyền DDL cao hơn, nhưng không nhất thiết phải dùng cùng tài khoản với ứng dụng lúc runtime. Áp dụng quyền tối thiểu phù hợp với quy trình triển khai.

### Sao lưu và phục hồi

Nếu mất metadata, ứng dụng có thể mất khả năng xác định JobInstance đã chạy, trạng thái Step, checkpoint và lịch sử thực thi. Vì vậy, cần đưa metadata database vào kế hoạch backup/restore. Khi khôi phục, cần xem xét tính nhất quán giữa metadata và dữ liệu nghiệp vụ đã được ghi trước đó.

### Lưu giữ lịch sử

Theo thời gian, các bảng metadata có thể tăng kích thước do lưu nhiều JobExecution, StepExecution và context. Có thể cần chính sách retention để lưu lịch sử trong khoảng thời gian phù hợp.

Việc dọn metadata phải thực hiện có kiểm soát. Cần dùng API hoặc công cụ cleanup được thiết kế phù hợp với phiên bản Spring Batch, hoặc quy trình SQL đã hiểu rõ quan hệ khóa ngoại. Nếu xóa thủ công, phải xử lý bản ghi con trước bản ghi cha và không xóa execution đang chạy hoặc dữ liệu còn cần cho restart/đối soát.

### Bảo vệ dữ liệu trong context và tham số

JobParameters và ExecutionContext có thể chứa đường dẫn tệp, mã định danh, thông tin vận hành hoặc dữ liệu nhạy cảm nếu ứng dụng lưu vào đó. Chỉ lưu thông tin cần thiết, kiểm soát quyền đọc metadata và tránh ghi bí mật như mật khẩu, token hoặc khóa truy cập vào context hay exit message.

### Giám sát tăng trưởng và hiệu năng

Theo dõi số lượng execution, tốc độ tăng bảng context, thời gian truy vấn lịch sử và hiệu năng index. Nếu một Job chạy với tần suất cao, metadata có thể tăng nhanh dù mỗi lần chạy xử lý ít dữ liệu. Kế hoạch retention, index và backup cần phù hợp với tần suất thực thi.

## 16. Những lỗi thường gặp khi cấu hình metadata schema

### Không tìm thấy bảng BATCH_*

Nguyên nhân thường là schema chưa được khởi tạo, datasource trỏ nhầm database/schema, tài khoản thiếu quyền hoặc table prefix trong cấu hình không khớp tên bảng thực tế. Kiểm tra database URL, schema owner, cấu hình `initialize-schema` và table prefix.

### Sai phiên bản schema

Ứng dụng có thể lỗi khi truy vấn cột không tồn tại, ghi dữ liệu sai kiểu hoặc đọc tham số không tương thích. So sánh phiên bản Spring Batch với DDL đang triển khai và dùng migration đúng phiên bản.

### Thiếu sequence hoặc quyền sinh ID

Các bảng có thể đã tồn tại nhưng repository vẫn không tạo được JobExecution hoặc StepExecution vì sequence/identity chưa được tạo đúng hoặc tài khoản runtime không có quyền sử dụng. Kiểm tra script theo database và quyền truy cập các đối tượng sinh ID.

### Table prefix không khớp

Nếu repository truy cập `APP_BATCH_JOB_INSTANCE` nhưng database chỉ có `BATCH_JOB_INSTANCE`, truy vấn sẽ thất bại. Cấu hình và DDL phải dùng cùng prefix.

### Unique constraint bị vi phạm

Có thể có hai launcher cùng tạo JobInstance với cùng tên Job và identifying parameters, hoặc một tiến trình khác đã tạo instance trước đó. Kiểm tra tham số, trạng thái execution hiện có và cơ chế khởi chạy đồng thời. Không xóa constraint để bỏ qua lỗi.

### Optimistic locking failure

Lỗi version có thể xảy ra khi metadata bị cập nhật đồng thời hoặc execution được điều khiển từ nhiều tiến trình không đúng cách. Xác định tiến trình nào đang ghi, kiểm tra launcher và tránh sửa trực tiếp cột `VERSION`.

### Context không đọc được sau nâng cấp

Thay đổi serializer, kiểu dữ liệu hoặc schema có thể khiến context cũ không tương thích. Cần kiểm tra cơ chế serialize/deserialize và quy trình migration. Không xóa bảng context nếu checkpoint cũ còn cần cho restart.

### Khởi tạo schema lặp lại trong production

Nếu ứng dụng luôn chạy script tạo bảng trên database đã tồn tại, startup có thể thất bại hoặc làm gián đoạn triển khai. Production nên có migration có phiên bản và chỉ chạy một lần theo quy trình phát hành.

## 17. Quy trình thiết lập repository cho một ứng dụng mới

Khi đưa Spring Batch vào một ứng dụng mới, có thể triển khai theo trình tự sau:

1. Chọn database dùng cho metadata và cấu hình datasource phù hợp.
2. Xác định phiên bản Spring Batch đi cùng phiên bản Spring Boot của dự án.
3. Lấy schema script đúng database và đúng phiên bản.
4. Tạo các bảng, khóa, index và sequence/identity cần thiết trong database.
5. Cấu hình JDBC JobRepository dùng đúng datasource, transaction manager và table prefix.
6. Cấu hình quyền runtime để ứng dụng đọc/ghi metadata.
7. Khởi chạy một Job thử nghiệm để xác nhận JobInstance, JobExecution, JobParameters và StepExecution được lưu.
8. Thử một Job thất bại có thể restart, xác nhận ExecutionContext được lưu và đọc lại đúng.
9. Kiểm tra truy vấn bằng JobExplorer và quy trình backup/retention.

Một Job chạy thành công một lần chưa đủ để chứng minh schema repository đã được cấu hình đầy đủ. Nên kiểm tra cả lịch sử execution, tham số, bộ đếm Step, context và tình huống restart.

## 18. Cách lựa chọn nơi lưu metadata

Trong phát triển, embedded database có thể thuận tiện vì dễ khởi tạo và không cần dịch vụ database riêng. Tuy nhiên, nếu metadata chỉ tồn tại trong bộ nhớ hoặc trong một database tạm thời, lịch sử và checkpoint có thể mất khi ứng dụng dừng.

Với production, JDBC JobRepository dùng database bền vững thường phù hợp khi cần restart, nhiều instance ứng dụng, lịch sử thực thi và truy vấn vận hành. Cần bảo đảm tất cả launcher/worker liên quan dùng chung repository đúng cách và database có khả năng đáp ứng tải metadata.

Việc chọn database metadata cần cân nhắc:

- Mức độ bền vững và yêu cầu restart.
- Số Job và Step execution được tạo mỗi ngày.
- Số lượng tiến trình có thể khởi chạy Job đồng thời.
- Yêu cầu lưu lịch sử và thời gian retention.
- Khả năng backup, restore, giám sát và migration.
- Quyền truy cập và cách cô lập metadata với dữ liệu nghiệp vụ.

## Kết luận

Schema của JDBC JobRepository gồm các bảng lưu JobInstance, JobExecution, JobParameters, StepExecution và ExecutionContext. Các bảng liên kết với nhau bằng khóa chính, khóa ngoại và các ràng buộc nhằm giữ metadata nhất quán, hỗ trợ theo dõi và restart. Cần dùng đúng schema script theo phiên bản Spring Batch và database, cấu hình table prefix khớp với DDL, quản lý migration có kiểm soát và bảo vệ metadata như dữ liệu vận hành quan trọng của ứng dụng Batch.
