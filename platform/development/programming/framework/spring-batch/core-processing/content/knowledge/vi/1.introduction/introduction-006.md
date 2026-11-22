# Định danh lần chạy và khả năng khởi động lại

Trong Spring Batch, một job có thể được khởi chạy nhiều lần. Có lần chạy xử lý một tập dữ liệu mới, có lần chạy tiếp tục công việc đã dừng vì lỗi. Để phân biệt hai trường hợp này, Spring Batch tách **JobInstance** (định danh một lần xử lý logic) khỏi **JobExecution** (một lần thực thi cụ thể của JobInstance).

Sự phân biệt đó quyết định khi nào một lần chạy được xem là mới, khi nào Spring Batch cho phép khởi động lại, và dữ liệu checkpoint nào được dùng để tiếp tục xử lý.

## 1. JobInstance và JobExecution

Một **JobInstance** được xác định bởi tên job cùng các JobParameters được đánh dấu là *identifying*. Có thể hiểu đây là danh tính của công việc cần hoàn thành, chẳng hạn nhập dữ liệu cho một ngày nghiệp vụ hoặc xử lý một tệp đầu vào cụ thể.

Một **JobExecution** đại diện cho một lần thử thực thi JobInstance. Nếu lần đầu thất bại và được khởi động lại, Spring Batch tạo JobExecution mới nhưng vẫn giữ nguyên JobInstance. Vì vậy, một JobInstance có thể có nhiều JobExecution theo thời gian.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Job | Định nghĩa luồng xử lý | `importOrders` |
| JobInstance | Một công việc logic, được xác định bởi job và identifying parameters | Nhập đơn hàng ngày `2026-11-15` |
| JobExecution | Một lần thực thi cụ thể của JobInstance | Lần chạy đầu thất bại, lần chạy sau tiếp tục |
| StepExecution | Một lần thực thi cụ thể của một step trong JobExecution | Step đọc và ghi đơn hàng ở lần chạy thứ hai |
| ExecutionContext | Dữ liệu trạng thái được lưu để tiếp tục xử lý | Vị trí đọc cuối cùng, số bản ghi đã xử lý |

Quan hệ tổng quát:

```text
Job: importOrders
        |
        +-- JobInstance (businessDate=2026-11-15)
                |
                +-- JobExecution #1  -> FAILED
                |       +-- StepExecution: loadOrders -> FAILED
                |
                +-- JobExecution #2  -> COMPLETED
                        +-- StepExecution: loadOrders -> COMPLETED
```

Hai JobExecution trong ví dụ thuộc cùng một JobInstance vì chúng có cùng tên job và cùng các identifying parameters. Mỗi execution có mã định danh và trạng thái riêng.

## 2. JobParameters quyết định danh tính

JobParameters truyền đầu vào cho job. Mỗi parameter có tên, kiểu dữ liệu, giá trị và cờ xác định nó có tham gia định danh JobInstance hay không.

- **Identifying parameter** tham gia tạo danh tính JobInstance. Thay đổi giá trị của parameter này sẽ tạo ra JobInstance khác.
- **Non-identifying parameter** được truyền cho execution nhưng không làm thay đổi danh tính JobInstance.

Ví dụ, ngày nghiệp vụ xác định tập dữ liệu cần nhập, còn người yêu cầu chạy chỉ là thông tin vận hành:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "nightly-scheduler", false)
    .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

Tham số thứ ba của `addString` là cờ identifying. Với ví dụ trên:

- `businessDate` là identifying. Chạy với ngày `2026-11-16` tạo JobInstance khác.
- `requestedBy` là non-identifying. Đổi từ `nightly-scheduler` sang `manual-user` không tạo JobInstance mới.

Các overload không truyền cờ identifying thường mặc định parameter là identifying. Khi thiết kế tham số, nên ghi rõ cờ này để tránh vô tình tạo instance mới hoặc vô tình dùng lại một instance.

### Chọn identifying parameters

Hãy chọn các giá trị mô tả **đơn vị công việc nghiệp vụ** mà job phải hoàn thành. Ví dụ:

| Trường hợp | Identifying parameter phù hợp |
|---|---|
| Tổng hợp giao dịch theo ngày | `businessDate` |
| Nhập dữ liệu từ tệp | `inputFile` hoặc mã lô tệp ổn định |
| Xử lý dữ liệu theo khách hàng | `tenantId` và `businessDate` |
| Tạo báo cáo theo kỳ | `reportPeriod` |

Các thông tin như người bấm nút chạy, tên máy, thời điểm yêu cầu hoặc ghi chú vận hành thường không cần tham gia định danh, trừ khi chúng thực sự tạo ra một công việc nghiệp vụ riêng.

Đừng thêm timestamp hoặc UUID mới vào identifying parameters mỗi lần khởi chạy chỉ để tránh lỗi trùng instance. Làm vậy sẽ tạo JobInstance mới trong mọi lần thử và khiến Spring Batch không nhận ra lần chạy sau là lần khởi động lại của công việc cũ.

Một điểm cần chú ý: non-identifying parameter vẫn có thể ảnh hưởng đến cách job xử lý dữ liệu. Nếu giá trị của nó thay đổi giữa lần chạy lỗi và lần khởi động lại, hai execution của cùng JobInstance có thể thực hiện công việc với cấu hình khác nhau. Vì vậy, các đầu vào ảnh hưởng đến kết quả nghiệp vụ nên ổn định trong suốt vòng đời của một JobInstance; nếu thay đổi đầu vào đồng nghĩa với một công việc mới, hãy đánh dấu parameter đó là identifying.

## 3. Điều gì xảy ra khi khởi chạy cùng parameters?

Khi gọi `JobLauncher.run(job, parameters)`, Spring Batch tra cứu JobInstance theo tên job và identifying parameters, sau đó kiểm tra trạng thái các execution trước đó.

| Trạng thái trước đó của JobInstance | Kết quả thường gặp khi chạy lại cùng identifying parameters |
|---|---|
| Chưa từng chạy | Tạo JobInstance và JobExecution đầu tiên |
| Đang chạy | Từ chối lần khởi chạy trùng, thường bằng `JobExecutionAlreadyRunningException` |
| Đã hoàn thành | Từ chối chạy lại cùng instance, thường bằng `JobInstanceAlreadyCompleteException` |
| Thất bại hoặc dừng | Có thể tạo JobExecution mới để khởi động lại, nếu job cho phép restart và metadata cho phép |
| Bị đánh dấu abandoned hoặc trạng thái không xác định | Không nên tự ý chạy lại; cần xử lý theo trạng thái metadata và quy tắc vận hành |

Các exception cụ thể còn phụ thuộc vào trạng thái metadata và cách khởi chạy. Điểm cốt lõi là: **cùng identifying parameters nghĩa là cùng JobInstance**. Spring Batch không coi một lần gọi `run` mới là một công việc mới chỉ vì đó là một lời gọi khác.

Nếu job đã hoàn thành nhưng nghiệp vụ cần xử lý lại dữ liệu, hãy tạo JobInstance mới bằng một identifying parameter mới có ý nghĩa rõ ràng, chẳng hạn mã lần tái xử lý hoặc phiên bản dữ liệu. Đừng thay đổi một parameter nghiệp vụ chỉ để né kiểm tra trạng thái mà không lưu lại lý do tái xử lý.

## 4. Cơ chế restart hoạt động như thế nào?

Restart là tiếp tục một JobInstance chưa hoàn thành sau khi một JobExecution trước đó thất bại hoặc dừng. Khi khởi động lại:

1. Spring Batch tìm JobInstance dựa trên job name và identifying parameters.
2. Repository kiểm tra lịch sử execution và xác định instance có thể restart hay không.
3. Spring Batch tạo JobExecution mới cho cùng JobInstance.
4. Các step đã hoàn thành thường được bỏ qua.
5. Step chưa hoàn thành được thực thi lại. Step có checkpoint có thể tiếp tục từ trạng thái đã lưu.

Ví dụ job có ba step:

```text
Execution #1
  validateInput  -> COMPLETED
  importRecords  -> FAILED
  publishReport  -> chưa chạy

Restart: Execution #2 (cùng JobInstance)
  validateInput  -> bỏ qua vì đã COMPLETED
  importRecords  -> chạy lại từ checkpoint đã lưu (nếu có)
  publishReport  -> chạy lần đầu
```

Đây là hành vi mặc định thường thấy khi restart. Có thể thay đổi cách step được chạy lại bằng cấu hình step, nhưng cần cân nhắc tác động đến dữ liệu đã ghi.

### Điều kiện để restart được

- Job phải cho phép restart. Job được cấu hình `preventRestart()` sẽ không cho phép restart sau khi execution thất bại.
- JobInstance phải ở trạng thái có thể tiếp tục. Một execution đang chạy, instance đã hoàn thành hoặc trạng thái metadata không an toàn đều có thể khiến yêu cầu bị từ chối.
- Các giới hạn chạy lại của step phải còn hiệu lực. Ví dụ `startLimit` giới hạn số lần step được bắt đầu.
- Repository phải còn metadata của lần chạy trước. Nếu metadata bị xóa hoặc repository chỉ lưu trong bộ nhớ rồi mất khi ứng dụng dừng, Spring Batch không thể khôi phục lịch sử và checkpoint đó.

Restart tạo JobExecution mới; nó không biến execution đã thất bại thành execution thành công. Lịch sử các lần thử vẫn được lưu để theo dõi và điều tra.

## 5. Checkpoint và ExecutionContext

Để tiếp tục từ giữa một step, Spring Batch cần lưu trạng thái xử lý. Trạng thái này thường được đặt trong **ExecutionContext** và lưu thông qua JobRepository.

Ví dụ, một step đọc tệp theo từng chunk. Sau khi một chunk được commit thành công, reader có thể lưu vị trí đọc hoặc trạng thái cần thiết. Nếu execution thất bại ở chunk tiếp theo, lần restart có thể tiếp tục từ checkpoint gần nhất thay vì đọc lại toàn bộ tệp.

```text
Đọc chunk 1 -> ghi và commit -> lưu checkpoint 1
Đọc chunk 2 -> ghi và commit -> lưu checkpoint 2
Đọc chunk 3 -> lỗi trước khi commit

Restart:
  khôi phục checkpoint 2
  tiếp tục từ phần dữ liệu sau chunk 2
```

Các reader/writer triển khai `ItemStream` có thể mở, cập nhật và đóng trạng thái qua các phương thức vòng đời như `open`, `update` và `close`. Nhiều thành phần đọc/ghi có sẵn của Spring Batch hỗ trợ lưu trạng thái; với thành phần tự viết, cần triển khai việc lưu và khôi phục trạng thái phù hợp. Nếu tắt lưu trạng thái, chẳng hạn cấu hình `saveState=false` trên một reader hỗ trợ tùy chọn này, không thể kỳ vọng reader tự tiếp tục đúng vị trí cũ.

Checkpoint thường gắn với ranh giới commit của chunk. Vì thế, khi thiết kế restart cần hiểu rõ transaction boundary và thứ tự cập nhật trạng thái. Dữ liệu đã commit trước khi lỗi thường được giữ lại; chunk chưa commit được xử lý lại theo cơ chế transaction và reader.

### Vì sao JobRepository phải bền vững?

JobRepository lưu metadata về JobInstance, JobExecution, StepExecution và ExecutionContext. Với môi trường chạy thực tế, repository thường dùng cơ sở dữ liệu để metadata tồn tại qua lần khởi động lại ứng dụng.

Nếu dùng repository chỉ lưu trong bộ nhớ, dữ liệu metadata có thể mất khi tiến trình kết thúc. Khi đó, lần chạy tiếp theo không còn đủ thông tin để nhận diện instance cũ hoặc khôi phục checkpoint. Vì vậy, khả năng restart qua nhiều lần khởi động ứng dụng phụ thuộc vào cấu hình repository bền vững và việc bảo toàn các bảng metadata của Spring Batch.

## 6. Chạy lại step đã hoàn thành và giới hạn số lần chạy

Mặc định, khi restart một JobInstance, step đã hoàn thành được bỏ qua. Hai cấu hình step thường liên quan đến hành vi này:

- `allowStartIfComplete(true)`: cho phép step đã hoàn thành được chạy lại khi job được restart.
- `startLimit(n)`: giới hạn số lần step được bắt đầu.

Ví dụ minh họa theo kiểu builder của Spring Batch 5:

```java
Step refreshReferenceData = new StepBuilder("refreshReferenceData", jobRepository)
    .tasklet(refreshTasklet, transactionManager)
    .allowStartIfComplete(true)
    .startLimit(3)
    .build();
```

`allowStartIfComplete(true)` hữu ích khi step cần thực hiện lại trong một lần restart, ví dụ làm mới dữ liệu tham chiếu. Hãy dùng cẩn thận với step có side effect như gửi email, thanh toán, gọi API bên ngoài hoặc ghi dữ liệu không có cơ chế chống trùng.

`startLimit(3)` giới hạn step được bắt đầu tối đa ba lần trong phạm vi instance. Khi vượt giới hạn, Spring Batch từ chối bắt đầu step và job có thể thất bại.

Nếu job đã hoàn thành toàn bộ, khởi chạy lại cùng identifying parameters vẫn bị chặn ở cấp JobInstance. `allowStartIfComplete` không biến một JobInstance đã hoàn thành thành một instance có thể khởi chạy lại từ đầu.

## 7. Tạo một JobInstance mới có chủ đích

Đôi khi yêu cầu nghiệp vụ là chạy lại toàn bộ job như một công việc mới, dù tên job và dữ liệu đầu vào chính giống lần trước. Khi đó cần một identifying parameter mới, chẳng hạn `reprocessVersion` hoặc `run.id`.

Spring Batch cung cấp `JobParametersIncrementer`; `RunIdIncrementer` là một triển khai phổ biến để tăng parameter `run.id`. Incrementer thường được dùng bởi thao tác yêu cầu tạo *next instance* (ví dụ `JobOperator.startNextInstance`). Nếu gọi trực tiếp `JobLauncher.run`, hãy bảo đảm bộ parameters truyền vào thực sự chứa giá trị identifying mới; việc chỉ cấu hình incrementer không có nghĩa mọi lời gọi `run` tự động tăng `run.id`.

Ví dụ về ý tưởng định danh:

| Lần xử lý | businessDate | reprocessVersion | Kết quả |
|---|---|---:|---|
| Nhập lần đầu | 2026-11-15 | 1 | JobInstance A |
| Restart sau lỗi | 2026-11-15 | 1 | Execution mới của JobInstance A |
| Tái xử lý theo yêu cầu | 2026-11-15 | 2 | JobInstance B |

Chỉ tăng version khi thực sự muốn tạo một công việc logic mới. Nếu execution trước chỉ thất bại do lỗi tạm thời, hãy restart cùng JobInstance thay vì tăng version.

## 8. Ví dụ vòng đời một job nhập đơn hàng

Giả sử job `importOrders` nhận `businessDate` và `inputFile` làm identifying parameters. Người vận hành khởi chạy job với ngày nghiệp vụ và tệp đầu vào cố định.

Lần đầu, step kiểm tra tệp hoàn thành. Step nhập dữ liệu xử lý được một số chunk rồi gặp lỗi kết nối cơ sở dữ liệu. JobExecution đầu tiên kết thúc với trạng thái `FAILED`; JobInstance vẫn đại diện cho công việc nhập tệp đó.

Sau khi khắc phục lỗi, hệ thống khởi chạy lại với cùng job name, `businessDate` và `inputFile`. Spring Batch tìm thấy JobInstance cũ và tạo JobExecution tiếp theo. Step kiểm tra tệp đã hoàn thành được bỏ qua. Step nhập dữ liệu tiếp tục từ checkpoint đã commit nếu reader và repository hỗ trợ khôi phục trạng thái. Khi các step còn lại hoàn tất, JobInstance đạt trạng thái hoàn thành.

Nếu người vận hành khởi chạy lại cùng parameters sau đó, Spring Batch từ chối vì JobInstance đã hoàn thành. Nếu nghiệp vụ yêu cầu nhập lại tệp, hãy tạo mã tái xử lý mới có chủ đích để tạo JobInstance khác, đồng thời bảo đảm quy trình ghi dữ liệu xử lý được bản ghi trùng hoặc có chiến lược thay thế dữ liệu phù hợp.

## 9. Các lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm timestamp mới vào identifying parameters mỗi lần chạy | Mỗi lần thử thành JobInstance mới; mất khả năng restart đúng instance cũ | Dùng identifying parameters ổn định theo đơn vị công việc |
| Đánh dấu nhầm parameter nghiệp vụ là non-identifying | Hai tập đầu vào khác nhau có thể bị xem là cùng JobInstance | Đưa mọi giá trị làm thay đổi đơn vị công việc vào danh tính |
| Thay đổi non-identifying parameter giữa các lần restart | Cùng JobInstance có thể chạy với cấu hình hoặc đầu vào khác nhau | Giữ đầu vào ảnh hưởng kết quả ổn định trong suốt vòng đời instance |
| Chỉ dùng repository trong bộ nhớ ở môi trường cần phục hồi sau khi ứng dụng dừng | Metadata và checkpoint có thể mất | Dùng JobRepository bền vững |
| Reader tự viết không lưu checkpoint | Restart có thể đọc lại từ đầu hoặc không khôi phục đúng vị trí | Triển khai `ItemStream` và lưu trạng thái cần thiết |
| Gửi side effect không có cơ chế chống trùng | Restart có thể gửi hoặc ghi lặp | Thiết kế thao tác idempotent hoặc dùng khóa nghiệp vụ để chống trùng |
| Dùng `allowStartIfComplete` để chạy lại job đã hoàn thành | Không vượt qua được quy tắc trạng thái ở cấp JobInstance | Tạo JobInstance mới khi nghiệp vụ thực sự yêu cầu tái xử lý |

Restart không tự bảo đảm mọi side effect bên ngoài chỉ xảy ra một lần. Transaction của Spring Batch có thể bảo vệ các thao tác nằm trong cùng transaction được cấu hình, nhưng lời gọi dịch vụ bên ngoài hoặc hệ thống không tham gia transaction có thể đã hoàn tất trước khi job ghi nhận checkpoint. Với những thao tác như vậy, nên dùng khóa idempotency, unique business key, outbox hoặc cơ chế đối soát phù hợp.

## 10. Quy trình lựa chọn khi vận hành

Khi một job cần được chạy lại, hãy xác định mục tiêu trước:

1. **Execution trước đang chạy:** kiểm tra tiến trình và trạng thái repository; không khởi chạy thêm một execution cùng JobInstance.
2. **Execution trước thất bại hoặc dừng:** kiểm tra nguyên nhân lỗi, tính restartable của job, step limit và checkpoint; sau đó restart với cùng identifying parameters.
3. **JobInstance đã hoàn thành nhưng cần xử lý một kỳ/tệp mới:** truyền identifying parameters mới tương ứng với đơn vị công việc mới.
4. **Cần tái xử lý cùng kỳ/tệp theo yêu cầu nghiệp vụ:** tạo một identifying parameter như mã tái xử lý hoặc version mới, đồng thời xác định cách xử lý dữ liệu đã ghi trước đó.
5. **Cần tiếp tục sau khi ứng dụng hoặc máy chủ khởi động lại:** xác nhận JobRepository và ExecutionContext được lưu bền vững, rồi mới dựa vào checkpoint để tiếp tục.

Khi theo dõi vận hành, hãy kiểm tra cả JobInstance, các JobExecution thuộc instance đó, trạng thái StepExecution và ExecutionContext. Chỉ nhìn trạng thái của một execution cuối cùng có thể bỏ qua lịch sử các lần thử trước.

## Kết luận

JobParameters xác định danh tính công việc thông qua cờ identifying. JobInstance đại diện cho công việc logic đó, còn mỗi lần thực thi hoặc restart tạo một JobExecution riêng. Khi một execution thất bại hoặc dừng, Spring Batch có thể tiếp tục cùng JobInstance bằng cách tạo execution mới và khôi phục checkpoint từ JobRepository. Khi công việc đã hoàn thành hoặc cần xử lý một đơn vị nghiệp vụ mới, hãy tạo JobInstance mới bằng identifying parameters có ý nghĩa rõ ràng.

Thiết kế tốt cần giữ parameters ổn định trong suốt quá trình restart, lưu metadata bền vững, checkpoint đúng cách và bảo vệ các side effect khỏi việc thực hiện lặp.
