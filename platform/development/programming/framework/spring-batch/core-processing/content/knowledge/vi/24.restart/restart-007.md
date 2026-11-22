# Restart sau process bị kill

Trong Spring Batch, restart cho phép tiếp tục một JobInstance đã chạy nhưng chưa hoàn tất sau khi execution trước bị lỗi hoặc dừng. Khi JVM, container hoặc máy chủ bị kill đột ngột, Spring Batch thường không có cơ hội chạy các callback kết thúc Step/Job hoặc cập nhật trạng thái cuối cùng vào JobRepository. Vì vậy, dữ liệu nghiệp vụ và metadata có thể phản ánh những thời điểm khác nhau: một số chunk đã commit, chunk đang chạy có thể rollback, còn JobExecution hoặc StepExecution có thể vẫn mang trạng thái `STARTED`.

Restart sau process bị kill cần xử lý cả hai vấn đề: xác định phần công việc đã commit và đưa metadata của execution cũ về trạng thái cho phép restart. Chỉ khởi chạy lại cùng JobParameters chưa chắc đủ, vì JobRepository có thể vẫn xem JobInstance đang chạy. Trước khi restart, phải xác nhận process cũ thực sự đã dừng, kiểm tra checkpoint và side effect, rồi dùng cơ chế quản trị phù hợp để hoàn tất execution bị bỏ dở.

## 1. Process bị kill khác với Job được dừng có kiểm soát

Spring Batch hỗ trợ yêu cầu dừng một Job đang chạy thông qua `JobOperator.stop(jobExecutionId)`. Đây là yêu cầu dừng có kiểm soát. Framework có cơ hội nhận biết yêu cầu và dừng tại điểm an toàn của quá trình xử lý, chẳng hạn sau khi chunk hiện tại hoàn tất transaction.

Process bị kill là tình huống khác:

- JVM có thể bị `kill -9`, `SIGKILL` hoặc bị hệ điều hành chấm dứt.
- Container có thể bị runtime hủy sau khi hết thời gian graceful shutdown.
- Máy ảo hoặc máy chủ có thể bị mất điện hoặc crash.
- Tiến trình có thể bị OOM killer chấm dứt.
- Ứng dụng có thể bị terminate trước khi Spring Batch cập nhật metadata cuối cùng.

Trong các trường hợp này, callback `afterStep`, `afterJob`, `ItemStream.close()` hoặc logic cleanup của ứng dụng có thể không được gọi. Không nên dựa vào shutdown hook để bảo đảm JobRepository luôn được cập nhật thành `FAILED` hoặc `STOPPED`.

| Tình huống | Cách kết thúc | Metadata thường thấy |
|---|---|---|
| Job hoàn tất bình thường | Framework kết thúc các Step và Job | `COMPLETED` |
| Job được yêu cầu stop và xử lý yêu cầu | Framework dừng theo cơ chế kiểm soát | `STOPPED` sau khi dừng xong |
| Exception được xử lý và Step thất bại | Framework ghi nhận lỗi | Thường là `FAILED` |
| JVM/process bị kill đột ngột | Không có đường kết thúc bình thường | Có thể còn `STARTED` hoặc trạng thái chưa được cập nhật cuối cùng |

Một execution còn `STARTED` sau khi process đã chết thường được gọi là execution stale hoặc orphaned. Spring Batch không thể tự kết luận process đã chết chỉ từ metadata đó; cần bước phục hồi vận hành.

## 2. Vì sao JobExecution có thể vẫn ở trạng thái STARTED?

JobRepository lưu trạng thái JobExecution và StepExecution trong database metadata. Khi Job bắt đầu, trạng thái được cập nhật thành `STARTED`. Trong quá trình chạy, framework tiếp tục cập nhật các bộ đếm, ExecutionContext và trạng thái Step.

Nếu process bị kill trước khi framework ghi trạng thái cuối, metadata có thể vẫn hiển thị:

```text
BATCH_JOB_EXECUTION.STATUS = STARTED
BATCH_STEP_EXECUTION.STATUS = STARTED
```

Điều này không chứng minh Job vẫn đang chạy. Nó chỉ cho biết metadata chưa ghi nhận kết thúc execution. Ngược lại, cũng không nên tự kết luận execution stale chỉ vì đã lâu không có log: một Step có thể đang chạy một truy vấn dài, chờ dịch vụ ngoài hoặc xử lý một item tốn thời gian.

Trước khi thay đổi trạng thái, phải xác minh process/container/host tương ứng đã dừng và không còn worker cũ nào đang thực hiện side effect. Nếu đánh dấu `FAILED` trong khi process cũ vẫn hoạt động, một lần restart có thể chạy song song với execution cũ và gây ghi trùng hoặc tranh chấp dữ liệu.

## 3. Điều gì xảy ra với transaction khi process chết?

Chunk Step thường xử lý mỗi chunk trong một transaction. Khi process chết, kết quả phụ thuộc thời điểm chết và transaction manager:

- Chunk đã commit: các thay đổi thuộc transaction đã commit vẫn được giữ.
- Chunk đang chạy nhưng chưa commit: database thường rollback transaction khi nhận biết connection/session đã đóng.
- Process chết trong lúc commit: client có thể không biết chắc commit đã thành công hay chưa; cần kiểm tra dữ liệu và metadata.
- Side effect ngoài transaction: HTTP request, email, message hoặc file có thể đã hoàn tất dù transaction database rollback.

```text
Chunk 1                 Chunk 2 đang chạy          Chunk 3
BEGIN                   BEGIN                     Chưa bắt đầu
Read/Process/Write      Read/Process/Write
COMMIT                  Process bị kill
                        DB phát hiện mất session
                        ROLLBACK (nếu chưa commit)

Chunk 1 vẫn được giữ     Chunk 2 cần phục hồi       Chunk 3 chưa chạy
```

Nếu database đã commit chunk 2 nhưng process chết trước khi nhận phản hồi commit hoặc trước khi cập nhật metadata liên quan, kết quả có thể không rõ ràng. Không nên chỉ dựa vào log cuối cùng của ứng dụng để quyết định chunk đã commit hay chưa.

Thời điểm database phát hiện connection mất cũng phụ thuộc database, driver, mạng và cấu hình timeout. Với host crash hoặc network partition, rollback có thể không xảy ra ngay lập tức. Hãy xác minh transaction/session cũ đã được database giải phóng trước khi khởi chạy lại cùng công việc.

## 4. Checkpoint quyết định nơi Step tiếp tục

Với reader hỗ trợ `ItemStream`, Spring Batch dùng `ExecutionContext` để lưu trạng thái như vị trí đọc, số dòng hoặc khóa cuối cùng. Các callback quan trọng:

- `open(ExecutionContext)`: khôi phục trạng thái đã lưu khi Step bắt đầu hoặc restart.
- `update(ExecutionContext)`: chép trạng thái hiện tại vào context tại điểm cập nhật của chunk.
- `close()`: giải phóng resource khi vòng đời stream kết thúc bình thường.

Trong chunk Step, stream cập nhật context trước khi transaction chunk commit. Khi metadata và dữ liệu nghiệp vụ tham gia cùng transaction phù hợp, checkpoint mới được xác nhận cùng chunk đã commit. Nếu chunk rollback, checkpoint của chunk đó không trở thành mốc restart đã commit.

Ví dụ, reader tệp đã xử lý đến dòng 10.000 và checkpoint đó được commit. Process chết khi đang xử lý dòng 10.001–10.200. Khi restart, reader có thể khôi phục từ checkpoint cuối cùng và xử lý lại phần chưa commit.

```text
Checkpoint đã commit: dòng 10.000
       |
       v
Đọc dòng 10.001–10.200
       |
       v
Writer xử lý chunk
       |
       X Process bị kill trước commit
       |
       v
Restart từ checkpoint đã commit: 10.000
```

Reader cần có state ổn định và hỗ trợ restart. Nếu reader tùy chỉnh không triển khai `ItemStream`, không lưu trạng thái hoặc không khôi phục được vị trí nguồn, Step có thể đọc lại từ đầu hoặc không thể tiếp tục đúng vị trí mong muốn.

## 5. Restart giữ nguyên JobInstance

Spring Batch phân biệt `JobInstance` với `JobExecution`:

- `JobInstance` đại diện cho một lần nghiệp vụ, được xác định bởi Job name và các identifying JobParameters.
- `JobExecution` đại diện cho một lần chạy cụ thể của JobInstance.
- Một JobInstance có thể có nhiều JobExecution khi lần chạy trước thất bại/dừng và được restart.

Ví dụ, Job `dailyOrderImport` chạy với identifying parameter `businessDate=2026-11-15`. Nếu execution bị kill rồi được phục hồi, restart phải tiếp tục cùng JobInstance với cùng định danh nghiệp vụ.

Không nên thêm timestamp hoặc UUID mới vào identifying parameters chỉ để chạy lại. Điều đó thường tạo JobInstance mới, khiến Spring Batch coi đây là một lần nghiệp vụ khác và có thể xử lý lại toàn bộ dữ liệu.

| Hành động | Kết quả |
|---|---|
| Restart execution cũ với JobInstance/identifying parameters cũ | Tiếp tục lần nghiệp vụ cũ theo metadata và checkpoint. |
| Launch cùng Job với cùng identifying parameters sau khi execution cũ đủ điều kiện restart | Tạo JobExecution mới cho cùng JobInstance. |
| Thêm identifying parameter mới | Tạo JobInstance mới. |
| Thay đổi non-identifying parameter | Không tạo JobInstance mới chỉ vì tham số đó thay đổi. |
| Launch JobInstance đã `COMPLETED` | Thông thường bị từ chối vì instance đã hoàn tất. |

Nếu nghiệp vụ thực sự muốn tạo một đợt import mới, hãy dùng identifying parameter phản ánh định danh đợt mới, ví dụ batch ID hoặc business date mới. Đừng dùng cách đó để giả lập restart.

## 6. Vì sao không thể restart ngay một execution còn STARTED?

Khi JobRepository vẫn ghi JobExecution là `STARTED`, Spring Batch có thể xem JobInstance đang được thực thi. Một lần launch khác với cùng identifying parameters có thể bị từ chối bằng lỗi như `JobExecutionAlreadyRunningException`.

Đây là bảo vệ quan trọng để ngăn hai process cùng chạy một JobInstance. Nếu process cũ thực sự đã chết nhưng metadata chưa được cập nhật, cần phục hồi trạng thái stale execution trước khi restart.

`JobOperator.restart(executionId)` dùng để restart một execution đã kết thúc trong trạng thái cho phép restart, chẳng hạn `FAILED` hoặc `STOPPED`. Nó không phải lệnh kill process và không nên được gọi như cách ép chạy lại một JobExecution vẫn được metadata xem là đang chạy.

Quy trình phục hồi cần:

1. Xác định đúng JobExecution ID bị stale.
2. Xác minh process cũ và mọi worker của nó đã thực sự dừng.
3. Kiểm tra trạng thái JobExecution/StepExecution và checkpoint cuối đã commit.
4. Dùng cơ chế quản trị/recovery được ứng dụng hỗ trợ để kết thúc execution stale ở trạng thái phù hợp, thường là `FAILED` khi cần restart.
5. Sau khi metadata hợp lệ, restart cùng JobInstance bằng API vận hành phù hợp.

Việc chuyển trạng thái stale execution là thao tác quản trị nhạy cảm. Không nên tự động đánh dấu mọi execution `STARTED` lâu hơn một ngưỡng thành `FAILED` nếu chưa kiểm tra heartbeat, host và worker. Cần tránh hai process cùng sở hữu một execution.

## 7. Xác minh process cũ đã chết trước khi phục hồi

Trước khi thay đổi metadata hoặc restart, hãy kiểm tra trạng thái thực tế của process:

- Nếu chạy trên máy ảo hoặc máy chủ, xác nhận PID/process không còn tồn tại.
- Nếu chạy trong Kubernetes, xác nhận Pod cũ đã ở trạng thái terminated và không còn container/worker cũ xử lý dữ liệu.
- Nếu chạy trong container platform khác, xác nhận task/container đã dừng hoàn toàn.
- Nếu Job dùng remote partitioning, xác nhận các worker process và message đang xử lý đã được xử lý theo quy trình phục hồi.
- Kiểm tra database session/transaction cũ đã được giải phóng hoặc hết thời gian phục hồi.
- Kiểm tra scheduler hoặc hệ thống điều phối không tiếp tục launch một execution khác cùng định danh.

Một Pod mới được tạo không tự chứng minh Pod cũ đã dừng hoàn toàn. Trong lúc rolling restart hoặc node partition, có thể tồn tại hai process cùng nghĩ rằng chúng có quyền xử lý một batch. Cần có cơ chế khóa/lease hoặc fencing phù hợp nếu triển khai nhiều instance.

## 8. JobOperator.stop không thay thế phục hồi sau kill

`JobOperator.stop(jobExecutionId)` gửi yêu cầu dừng một Job đang chạy. Framework có thể quan sát yêu cầu này và dừng tại điểm an toàn. Khi process đã bị kill, không còn worker nào để nhận yêu cầu và cập nhật metadata hoàn tất.

Nếu gọi `stop` cho một execution stale còn `STARTED`, trạng thái có thể chuyển sang `STOPPING` nhưng không có process cũ để hoàn tất việc dừng. Vì vậy, không dùng `stop` như một lệnh dọn metadata cho process đã chết.

Phân biệt các thao tác quản trị:

| API/khái niệm | Mục đích | Khi nào dùng |
|---|---|---|
| `JobOperator.stop(executionId)` | Yêu cầu process đang chạy dừng có kiểm soát | Khi execution còn hoạt động và có thể nhận yêu cầu. |
| `JobOperator.restart(executionId)` | Restart execution đã kết thúc và đủ điều kiện | Sau khi execution cũ ở trạng thái restartable. |
| `JobOperator.abandon(executionId)` | Đánh dấu execution đã kết thúc là không tiếp tục restart | Khi quyết định bỏ hẳn execution cũ theo chính sách. |
| Recovery stale execution | Sửa trạng thái execution bị bỏ dở sau khi process chết | Khi đã xác minh không còn process cũ và có quy trình quản trị an toàn. |

`ABANDONED` mang ý nghĩa execution bị bỏ, không phải trạng thái trung gian để restart. Nếu mục tiêu là tiếp tục công việc, không đánh dấu execution là `ABANDONED`.

## 9. Phục hồi metadata stale một cách có kiểm soát

Spring Batch không thể biết chắc process đã chết chỉ từ một bản ghi `STARTED`. Tùy phiên bản, hạ tầng và cách vận hành, ứng dụng cần một công cụ admin hoặc quy trình recovery để cập nhật trạng thái của JobExecution và StepExecution bị bỏ dở.

Quy trình đó cần tuân thủ các nguyên tắc:

- Chỉ xử lý execution đã xác minh không còn process/worker hoạt động.
- Tải đúng JobExecution và StepExecution từ JobRepository/JobExplorer.
- Kiểm tra trạng thái, version, thời điểm cập nhật và các execution liên quan.
- Chuyển execution stale sang trạng thái kết thúc phù hợp theo API repository/admin được hỗ trợ trong phiên bản đang dùng.
- Cập nhật nhất quán cả trạng thái StepExecution liên quan và JobExecution; không để metadata cha/con mâu thuẫn.
- Ghi audit người thực hiện, thời gian, lý do và execution ID.
- Sau đó mới gọi restart theo cùng JobInstance.

Không nên cung cấp một câu SQL chung để đổi `STATUS='STARTED'` thành `FAILED` trên mọi bảng. Metadata có quan hệ giữa JobInstance, JobExecution, StepExecution, ExecutionContext, version và thời gian cập nhật. Sửa trực tiếp một vài cột có thể tạo trạng thái không hợp lệ hoặc làm mất khả năng restart.

Nếu ứng dụng cần tự động hóa recovery, hãy xây dựng một admin operation có khóa/lease, xác minh process owner, kiểm tra timeout/heartbeat và dùng API JobRepository tương ứng. Kiểm thử quy trình này trên đúng phiên bản Spring Batch và database metadata trước khi đưa vào production.

## 10. Restart bằng JobOperator

Sau khi execution cũ đã ở trạng thái cho phép restart, có thể dùng `JobOperator.restart` với execution ID cũ:

```java
@Service
public class BatchRestartService {

    private final JobOperator jobOperator;

    public BatchRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public long restart(long previousExecutionId) throws Exception {
        return jobOperator.restart(previousExecutionId);
    }
}
```

`restart` nhận ID của JobExecution trước đó, không phải JobInstance ID hoặc StepExecution ID. JobOperator sử dụng metadata để xác định Job, JobParameters và trạng thái cần tiếp tục.

Trước khi gọi phương thức này, ứng dụng phải bảo đảm execution trước đã được kết thúc hợp lệ và không còn process cũ. Nếu execution vẫn `STARTED`, đã `COMPLETED` hoặc `ABANDONED`, thao tác restart có thể bị từ chối theo trạng thái và quy tắc của Spring Batch.

Có thể dùng `JobExplorer` để tra cứu thông tin execution phục vụ màn hình quản trị:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution == null) {
    throw new IllegalArgumentException("JobExecution not found");
}

BatchStatus status = execution.getStatus();
JobParameters parameters = execution.getJobParameters();
```

Đoạn code chỉ minh họa cách đọc metadata. Không chuyển trạng thái chỉ dựa trên object đọc được; recovery cần xác minh process owner và cập nhật qua cơ chế quản trị phù hợp.

## 11. Reader checkpoint và saveState

Để restart từ vị trí phù hợp, reader cần lưu trạng thái. Nhiều reader chuẩn của Spring Batch triển khai `ItemStream` và hỗ trợ `saveState`.

Ví dụ reader file:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

`saveState(true)` cho phép reader lưu vị trí đọc vào ExecutionContext. Cần giữ tên reader ổn định vì tên thường tham gia tạo key checkpoint. `@StepScope` cho phép reader nhận JobParameters của execution hiện tại.

Với reader tùy chỉnh, triển khai `ItemStreamReader` và quản lý `open`, `update`, `close`. Không lưu trạng thái checkpoint của một execution trong field mutable của singleton được chia sẻ giữa nhiều Job.

### Nguồn dữ liệu phải ổn định

Checkpoint theo dòng hoặc offset chỉ có ý nghĩa nếu nguồn dữ liệu giữ thứ tự ổn định. Nếu file bị thay thế hoặc database có bản ghi thêm/xóa giữa lần chạy và restart, reader có thể bỏ sót hoặc đọc trùng.

Các cách giảm rủi ro:

- Dùng file input bất biến và checksum/manifest để xác nhận đúng file khi restart.
- Dùng khóa tăng dần hoặc cursor ổn định thay vì offset trên tập dữ liệu thay đổi.
- Lưu high-watermark hoặc snapshot ID của lần chạy.
- Không tái sử dụng cùng JobInstance với một input file khác nội dung.

## 12. Chunk đã commit và chunk chưa commit

Giả sử Step import 1.000 item với chunk size 100. Process bị kill khi đang xử lý chunk thứ sáu.

| Chunk | Trạng thái trước khi kill | Hành vi khi restart |
|---|---|---|
| 1–5 | Đã commit | Dữ liệu đã commit được giữ; thường không xử lý lại trong cùng Step restart. |
| 6 | Chưa commit | Transaction thường rollback; xử lý lại từ checkpoint đã commit gần nhất. |
| 7–10 | Chưa bắt đầu | Được xử lý sau khi chunk trước hoàn tất. |

Đây là mô hình mong đợi khi reader checkpoint, JobRepository và writer cùng tuân thủ transaction/restart contract. Nếu business data và metadata dùng hai transaction manager độc lập, không có bảo đảm nguyên tử tự động giữa hai database; có thể phải đối soát dữ liệu trước khi restart.

Nếu chunk thứ sáu thực tế đã commit nhưng process chết trước khi nhận ACK, cần kiểm tra dữ liệu đích và checkpoint. Writer nên idempotent hoặc dùng unique business key để một lần xử lý lại không tạo dữ liệu trùng.

## 13. Tasklet và restart sau process kill

Tasklet thường thực hiện một hành động trong transaction của TaskletStep. Nếu process chết giữa thao tác, kết quả phụ thuộc resource:

- Thay đổi database trong transaction chưa commit có thể rollback.
- Thay đổi database đã commit vẫn tồn tại.
- File đã move hoặc HTTP request đã gửi không tự rollback.
- Metadata Step có thể còn `STARTED` nếu process chết trước khi cập nhật trạng thái cuối.

Tasklet được chạy lại từ đầu khi restart theo chính sách. Vì vậy, Tasklet phải idempotent hoặc có cách kiểm tra thao tác đã hoàn tất chưa.

Ví dụ, một Tasklet archive file nên kiểm tra cả file nguồn và file đích:

```java
if (Files.exists(targetPath)) {
    verifyArchivedFile(targetPath, expectedChecksum);
} else if (Files.exists(sourcePath)) {
    Files.move(sourcePath, targetPath, StandardCopyOption.ATOMIC_MOVE);
} else {
    throw new FileNotFoundException("Source and target are missing");
}
```

Đây là ví dụ minh họa; cần xử lý riêng filesystem không hỗ trợ atomic move, file đích không đúng checksum và lỗi giữa các thao tác. Không nên giả định transaction database có thể khôi phục một thao tác filesystem.

## 14. Side effect ngoài transaction và idempotency

Process bị kill có thể xảy ra ngay sau khi hệ thống ngoài đã xử lý request nhưng trước khi JobRepository ghi nhận chunk/Step hoàn tất. Khi restart, cùng request có thể được gửi lại.

Trước khi restart, cần xác định:

- Writer/processor có gọi HTTP, gửi email hoặc publish message không?
- Hệ thống ngoài có thể đã xử lý request trước khi response mất không?
- Có idempotency key ổn định qua retry và restart không?
- Có thể truy vấn trạng thái operation bằng business key không?
- Có outbox/inbox hoặc cơ chế deduplication không?

Với side effect cần phát sau khi dữ liệu chính commit, transactional outbox là lựa chọn phổ biến: ghi business data và outbox record trong cùng transaction, rồi relay gửi event. Relay vẫn cần idempotency vì có thể gửi thành công rồi crash trước khi đánh dấu event đã gửi.

Không nên retry mù quáng một operation thanh toán, đặt chỗ hoặc tạo tài nguyên nếu không biết lần trước đã thành công hay chưa. Hãy tra cứu trạng thái, dùng cùng idempotency key hoặc đưa operation vào quy trình reconciliation.

## 15. JobRepository phải bền vững

Khả năng restart dựa vào metadata được lưu trong JobRepository. Nếu JobRepository chỉ dùng bộ nhớ hoặc database metadata bị mất, Spring Batch không có đủ thông tin bền vững để khôi phục JobInstance, JobExecution và checkpoint.

Trong production:

- Dùng JobRepository lưu trong database bền vững.
- Backup metadata theo chính sách vận hành.
- Không xóa các bảng `BATCH_*` khi Job còn có thể restart hoặc cần audit.
- Đảm bảo metadata schema tương thích với phiên bản Spring Batch.
- Theo dõi dung lượng, index và thời gian truy vấn repository.
- Giữ dữ liệu JobParameters/ExecutionContext có thể serialize và tương thích qua nâng cấp.

Nếu metadata repository bị restore từ backup cũ hơn business database, checkpoint có thể lùi so với dữ liệu đích. Khi đó, restart có thể phát lại side effect; cần reconciliation hoặc khôi phục hai resource về trạng thái nhất quán.

## 16. Process kill trong môi trường container/Kubernetes

Trong môi trường container, orchestrator có thể gửi tín hiệu terminate trước khi xóa container. Ứng dụng nên có thời gian graceful shutdown đủ dài để dừng nhận Job mới và cho Job hiện tại hoàn tất chunk hoặc dừng có kiểm soát.

Một số điểm vận hành:

- Cấu hình `terminationGracePeriodSeconds` phù hợp với thời gian chunk tối đa và cleanup.
- Đảm bảo ứng dụng nhận SIGTERM và đóng context theo quy trình Spring.
- Dừng scheduler/trigger trước khi terminate để tránh launch thêm Job.
- Nếu cần dừng Job cụ thể, gửi `JobOperator.stop(executionId)` khi process còn sống.
- Nếu hết thời gian grace và container bị SIGKILL, xử lý như process crash; kiểm tra metadata stale trước khi restart.
- Dùng readiness/liveness probe hợp lý; liveness restart liên tục có thể kill Job đang chạy.
- Với nhiều replica, dùng khóa hoặc cơ chế điều phối để ngăn hai instance cùng sở hữu một business operation.

Graceful shutdown giảm khả năng metadata stale nhưng không thay thế checkpoint, idempotency và quy trình recovery. Không thể bảo đảm shutdown hook luôn chạy khi node hoặc kernel bị crash.

## 17. Scheduler và tránh launch trùng sau khi process bị kill

Sau khi một instance chết, scheduler hoặc instance khác có thể cố launch lại Job. Nếu metadata vẫn là `STARTED`, JobRepository thường ngăn một execution mới cho cùng JobInstance. Tuy nhiên, hệ thống điều phối cần tránh tạo JobInstance mới bằng identifying parameter khác chỉ để vượt qua lỗi này.

Nên:

- Dùng business key ổn định cho identifying parameters.
- Kiểm tra execution hiện tại trước khi launch.
- Chỉ tự động recovery sau khi xác minh owner cũ đã chết.
- Dùng distributed lock/lease có fencing token nếu nhiều scheduler/replica cùng hoạt động.
- Lưu correlation ID giữa scheduler run, JobInstance và JobExecution.
- Tách quy trình tạo JobInstance mới khỏi quy trình restart JobInstance cũ.

Nếu scheduler dùng timestamp làm identifying parameter mỗi phút, một lần process bị kill có thể dẫn đến nhiều JobInstance khác nhau cùng xử lý một tập dữ liệu. Cần thiết kế tham số định danh theo nghiệp vụ thay vì theo thời điểm gọi scheduler.

## 18. Những lỗi thường gặp

### Launch lại ngay với cùng JobParameters

Nếu JobExecution cũ còn `STARTED`, JobRepository có thể xem JobInstance đang chạy và từ chối launch. Xác minh process cũ, phục hồi metadata stale rồi mới restart.

### Thêm timestamp để tạo JobInstance mới

Điều này né trạng thái execution cũ nhưng có thể xử lý lại toàn bộ dữ liệu và tạo side effect trùng. Restart phải giữ identifying parameters của lần nghiệp vụ cũ.

### Gọi JobOperator.stop sau khi process đã chết

Không còn process để nhận yêu cầu và hoàn tất dừng. Cần recovery metadata stale qua quy trình quản trị.

### Đánh dấu execution ABANDONED rồi mong restart

`ABANDONED` thể hiện execution không được tiếp tục. Nếu cần resume, hãy dùng trạng thái kết thúc restartable phù hợp, thường là `FAILED`, theo recovery procedure.

### Sửa trực tiếp một cột STATUS trong bảng BATCH_*

Metadata có nhiều quan hệ và version. Sửa thủ công một cột có thể làm JobExecution/StepExecution không nhất quán. Dùng API repository/admin được hỗ trợ và audit thao tác.

### Tin rằng chunk chưa commit chắc chắn chưa có side effect

HTTP, email, message và file có thể đã được xử lý bên ngoài transaction. Kiểm tra hệ thống đích hoặc dùng idempotency/outbox trước khi chạy lại.

### Reader không lưu checkpoint

Reader có thể đọc lại từ đầu hoặc không thể khôi phục đúng vị trí. Dùng reader hỗ trợ `ItemStream`, bật `saveState` và giữ input ổn định.

### Restart khi process cũ vẫn chạy

Hai execution có thể cùng xử lý một business key. Xác minh PID/container/worker và database session trước khi recovery.

### Dùng in-memory JobRepository trong production

Process chết làm mất metadata; không thể restart đáng tin cậy. Dùng repository bền vững.

## 19. Quy trình vận hành sau khi process bị kill

Một runbook phục hồi có thể đi theo trình tự sau:

1. **Ngăn launch mới:** tạm dừng scheduler hoặc trigger tạo cùng business operation.
2. **Xác định execution:** tra cứu Job name, JobInstance, JobExecution ID, StepExecution và identifying parameters.
3. **Xác minh process:** kiểm tra PID, container, Pod, host và remote worker; bảo đảm không còn process cũ hoạt động.
4. **Kiểm tra transaction:** xác nhận database session cũ đã đóng và transaction chưa commit đã được rollback hoặc phục hồi.
5. **Đọc metadata:** xem BatchStatus, ExitStatus, thời điểm cập nhật, failure exception, commit/rollback count và ExecutionContext.
6. **Đối chiếu dữ liệu:** xác định chunk cuối đã commit, dữ liệu đích có bản ghi trùng hay không và side effect ngoài transaction đã xảy ra chưa.
7. **Phục hồi stale execution:** dùng admin/recovery API được hỗ trợ để kết thúc trạng thái `STARTED` bị bỏ dở sau khi xác minh process cũ đã chết; cập nhật nhất quán các execution liên quan.
8. **Giữ nguyên định danh:** không thêm identifying parameter mới nếu mục tiêu là restart JobInstance cũ.
9. **Restart:** gọi `JobOperator.restart(previousExecutionId)` hoặc cơ chế launch tương ứng sau khi execution đủ điều kiện restart.
10. **Giám sát:** theo dõi JobExecution mới, StepExecution, checkpoint, retry/skip count và dữ liệu đích.
11. **Đối soát:** xác nhận không có side effect bị mất hoặc lặp; xử lý các operation có trạng thái không rõ.
12. **Mở lại scheduler:** chỉ tiếp tục lịch tự động khi JobInstance và dữ liệu nghiệp vụ đã ở trạng thái an toàn.

| Kiểm tra | Bằng chứng cần có trước restart |
|---|---|
| Process cũ | PID/container/Pod đã terminated, không còn worker sở hữu execution. |
| Transaction | Session cũ đã giải phóng; trạng thái commit/rollback đã được xác định hoặc đối soát. |
| Metadata | Job/Step execution stale được nhận diện và recovery theo quy trình. |
| Checkpoint | ExecutionContext phản ánh chunk cuối đã commit. |
| Input | File/snapshot/cursor đúng với JobInstance ban đầu. |
| Side effect | Có idempotency, trạng thái tra cứu hoặc reconciliation cho operation không rõ. |
| JobParameters | Identifying parameters giữ nguyên cho lần restart. |

## 20. Kiểm thử restart sau process kill

Không chỉ kiểm thử Job thất bại do exception. Cần mô phỏng process dừng đột ngột ở các thời điểm khác nhau:

- Trước khi chunk bắt đầu.
- Sau khi reader đã đọc item nhưng trước writer.
- Trong khi writer đang ghi nhưng trước commit.
- Trong lúc commit đang diễn ra.
- Sau commit nhưng trước khi ứng dụng ghi log hoặc nhận response.
- Sau khi side effect ngoài transaction thành công nhưng trước khi metadata được cập nhật.
- Trong lúc một partition worker đang chạy.
- Trong Tasklet đang di chuyển file hoặc gọi API.

Sau mỗi tình huống, xác nhận:

- JobRepository có trạng thái execution đúng hoặc có thể phục hồi.
- Các chunk đã commit vẫn tồn tại.
- Chunk chưa commit được xử lý lại theo checkpoint.
- Reader khôi phục đúng vị trí và không bỏ sót dữ liệu.
- Writer không tạo bản ghi hoặc side effect trùng.
- JobInstance giữ nguyên định danh.
- Recovery procedure không cho phép hai process chạy cùng operation.

Nên chạy kiểm thử với database và transaction manager thực tế hoặc môi trường tương đương production. Mock không chứng minh được hành vi rollback khi socket mất, commit ACK bị mất hoặc metadata và business data dùng datasource khác nhau.

## 21. Quyết định giữa restart, reprocess và Job mới

Không phải mọi lần process bị kill đều nên restart cùng JobInstance. Hãy phân biệt ba ý định:

| Ý định | Cách thực hiện |
|---|---|
| Tiếp tục phần còn lại của cùng lần nghiệp vụ | Phục hồi execution stale rồi restart cùng JobInstance. |
| Chạy lại một số item đã bị lỗi hoặc reject | Tạo quy trình reprocess riêng với business key và input đã sửa. |
| Xử lý một đợt nghiệp vụ mới | Tạo JobInstance mới bằng identifying parameters mới phản ánh batch/business run mới. |

Restart không tự động đưa dữ liệu đích về trạng thái trước Job. Nếu cần chạy lại toàn bộ từ đầu, phải có chiến lược xóa/ghi đè/idempotency rõ ràng và hiểu các side effect đã xảy ra.

## Kết luận

Khi process bị kill, Spring Batch có thể không kịp cập nhật JobExecution/StepExecution khỏi `STARTED`. Các chunk đã commit vẫn tồn tại; transaction chưa commit thường được database rollback khi session đóng, còn trạng thái commit tại thời điểm mất kết nối có thể cần đối soát. Reader checkpoint trong `ExecutionContext` xác định nơi Step tiếp tục, nhưng JobInstance chỉ restart được khi execution cũ đã ở trạng thái cho phép. Hãy xác minh process/worker cũ đã chết, phục hồi metadata stale qua cơ chế quản trị được hỗ trợ, giữ nguyên identifying JobParameters và gọi restart bằng execution ID cũ. Vì rollback không thu hồi side effect ngoài transaction, writer/Tasklet cần idempotency, outbox hoặc reconciliation để restart không làm mất hoặc lặp hành động nghiệp vụ.
