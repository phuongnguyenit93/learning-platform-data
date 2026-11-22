# Kiểm tra trạng thái metadata sau rollback

Trong Spring Batch, rollback của một chunk và trạng thái cuối cùng của Job/Step là hai khái niệm khác nhau. Khi transaction của chunk rollback, các thay đổi nghiệp vụ chưa commit được hoàn tác trong phạm vi resource tham gia transaction. Metadata của Step như counter, trạng thái và `ExecutionContext` được JobRepository quản lý để Spring Batch có thể theo dõi tiến độ và restart.

Muốn kiểm tra đúng tình trạng sau rollback, cần xem đồng thời `BatchStatus`, `ExitStatus`, các counter của `StepExecution`, `ExecutionContext` và dữ liệu nghiệp vụ đã commit. Một rollback không nhất thiết làm Step thất bại: nếu lỗi transient được retry thành công, Step vẫn có thể kết thúc `COMPLETED` nhưng có ghi nhận rollback. Ngược lại, nếu process bị dừng đột ngột, metadata có thể còn trạng thái `STARTED` vì framework chưa kịp ghi nhận kết quả kết thúc.

## 1. Phân biệt rollback với trạng thái Step

Rollback là hành động của transaction manager đối với một transaction. `BatchStatus` mô tả trạng thái vòng đời của Step hoặc Job. Hai khái niệm liên quan nhưng không đồng nhất.

Ví dụ, một chunk có 100 item và writer gặp deadlock:

1. Spring Batch mở transaction cho chunk.
2. Reader đọc item, processor xử lý và writer bắt đầu ghi.
3. Database ném exception deadlock.
4. Transaction của chunk rollback.
5. Retry policy thử lại thao tác hoặc chunk theo cấu hình.
6. Lần thử tiếp theo thành công và chunk commit.
7. Step tiếp tục xử lý các chunk còn lại.

Trong tình huống này đã có rollback, nhưng Step vẫn có thể kết thúc với `BatchStatus.COMPLETED`. Rollback count có thể lớn hơn 0 mà Job vẫn thành công.

Nếu retry hết giới hạn và lỗi không được skip, Step thường kết thúc `FAILED`. Khi đó Job cha cũng thường thất bại theo flow. Nếu ứng dụng bị kill giữa transaction, metadata cuối cùng có thể chưa được cập nhật trạng thái thất bại; nó có thể vẫn phản ánh execution đang chạy.

## 2. Những lớp metadata cần kiểm tra

Spring Batch lưu metadata ở nhiều cấp. Khi điều tra một rollback, không nên chỉ nhìn một trường hoặc một bảng.

| Đối tượng | Nội dung cần xem | Câu hỏi cần trả lời |
|---|---|---|
| `JobExecution` | `BatchStatus`, `ExitStatus`, thời gian bắt đầu/kết thúc | Job đã hoàn tất, thất bại, dừng hay còn ở trạng thái đang chạy? |
| `StepExecution` | `BatchStatus`, `ExitStatus`, read/write/skip/commit/rollback counters | Step nào gặp lỗi và chunk đã tiến đến đâu? |
| Step `ExecutionContext` | Checkpoint reader/writer và state của Step | Lần restart sẽ tiếp tục từ checkpoint nào? |
| Job `ExecutionContext` | Dữ liệu chia sẻ giữa các Step | Các Step sau có thể dùng lại dữ liệu điều phối nào? |
| Dữ liệu nghiệp vụ | Bản ghi đã commit trong database hoặc hệ thống đích | Thay đổi nào thực sự tồn tại sau rollback? |

Metadata cho biết Spring Batch đã ghi nhận điều gì; dữ liệu nghiệp vụ cho biết hệ thống đích đang có trạng thái nào. Khi hai phần không cùng transaction hoặc có side effect ngoài transaction, cần đối chiếu cả hai.

## 3. BatchStatus và ExitStatus sau rollback

`BatchStatus` biểu diễn trạng thái vòng đời thực thi, ví dụ:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Execution đang trong quá trình khởi tạo |
| `STARTED` | Execution đang chạy |
| `COMPLETED` | Execution hoàn tất bình thường |
| `FAILED` | Execution thất bại |
| `STOPPING` | Đang trong quá trình dừng |
| `STOPPED` | Execution đã dừng |
| `ABANDONED` | Execution được đánh dấu không tiếp tục restart theo cách thông thường |
| `UNKNOWN` | Không xác định được trạng thái |

`ExitStatus` mô tả kết quả thoát, thường gồm exit code và mô tả. Ví dụ `COMPLETED`, `FAILED`, `STOPPED` hoặc một mã tùy chỉnh như `COMPLETED_WITH_SKIPS`.

Sau rollback, trạng thái phụ thuộc kết quả xử lý tiếp theo:

- Nếu retry thành công, Step có thể tiếp tục và cuối cùng `COMPLETED`.
- Nếu exception được skip và còn skip limit, Step có thể tiếp tục và `COMPLETED` với skip count lớn hơn 0.
- Nếu exception không retry được, không skippable hoặc vượt giới hạn, Step thường kết thúc `FAILED`.
- Nếu Job bị dừng có kiểm soát, Step/Job có thể kết thúc `STOPPED`.
- Nếu process bị kill đột ngột trước khi ghi metadata kết thúc, trạng thái lưu trong repository có thể vẫn là `STARTED`.

Không suy luận rằng cứ có rollback thì `BatchStatus` phải là `FAILED`. Hãy kiểm tra trạng thái cuối cùng cùng exception và counter.

## 4. Các counter của StepExecution

`StepExecution` chứa các bộ đếm phản ánh hoạt động của Step:

| Counter | Ý nghĩa |
|---|---|
| `readCount` | Số item đọc thành công |
| `writeCount` | Số item được ghi thành công |
| `filterCount` | Số item bị processor filter |
| `readSkipCount` | Số item bị skip khi đọc |
| `processSkipCount` | Số item bị skip khi xử lý |
| `writeSkipCount` | Số item bị skip khi ghi |
| `skipCount` | Tổng số item bị skip |
| `commitCount` | Số lần commit được ghi nhận cho Step |
| `rollbackCount` | Số lần rollback được ghi nhận cho Step |

Ví dụ, Step có `readCount=500`, `writeCount=490`, `filterCount=5`, `skipCount=5` có thể đã đọc 500 item, filter 5 và skip 5, nên writer ghi 490 item. Nếu `rollbackCount=2`, Step đã ghi nhận hai lần rollback trong quá trình thực thi; điều đó không có nghĩa toàn bộ 500 item đều bị rollback.

Các counter cần được đọc cùng trạng thái và lịch sử execution. Tùy thời điểm lỗi, retry, transaction và phiên bản framework, giá trị trong bộ nhớ và metadata đã commit có thể khác nhau trong lúc Step còn chạy. Sau khi execution kết thúc và metadata được cập nhật ổn định, counter là cơ sở tốt để phân tích kết quả.

`rollbackCount` không phải retry count. Một rollback có thể do lỗi không retryable, lỗi commit hoặc lỗi khác; retry policy cũng có thể gọi lại thao tác theo các đường xử lý khác nhau. Nếu cần số lần retry chính xác, hãy instrument retry policy hoặc dùng `RetryListener`.

## 5. ExecutionContext sau rollback

Reader restartable thường lưu checkpoint trong Step `ExecutionContext`. Ví dụ reader lưu ID cuối cùng đã commit:

```java
private static final String LAST_ID_KEY = "ordersReader.lastCommittedId";

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_ID_KEY, lastCommittedId);
}

@Override
public void open(ExecutionContext context) {
    lastCommittedId = context.getLong(LAST_ID_KEY, 0L);
    openSourceAfter(lastCommittedId);
}
```

Trong chunk processing, Spring Batch gọi `ItemStream.update()` tại các điểm lưu trạng thái của Step. Khi checkpoint được lưu cùng transaction phù hợp, nó đại diện cho tiến độ đã commit.

Giả sử reader đã commit đến order ID 4000. Chunk tiếp theo đọc ID 4001–4100 nhưng writer gặp lỗi và transaction rollback. Nếu Step được restart sau đó, checkpoint bền vững vẫn phải đại diện cho tiến độ đã commit gần nhất, tức ID 4000. Reader sẽ đọc lại phần từ ID 4001 theo quy tắc truy vấn.

Điều này chỉ hoạt động khi reader hỗ trợ `ItemStream`/restart, `saveState` được bật nếu reader yêu cầu, và nguồn dữ liệu vẫn ổn định. Reader không lưu state có thể không biết phải tiếp tục từ vị trí nào sau khi process kết thúc.

## 6. Rollback trong cùng process khác với restart sau crash

Hai tình huống này tạo ra dấu vết metadata khác nhau.

### Rollback trong lúc ứng dụng vẫn chạy

Khi chunk rollback nhưng process còn hoạt động, Spring Batch có thể retry hoặc phát lại các item đã đọc theo fault-tolerance policy. Step tiếp tục chạy. Nếu retry thành công, Step có thể hoàn tất với `BatchStatus.COMPLETED` và rollback count phản ánh rollback đã xảy ra.

### Process bị dừng đột ngột

Nếu JVM bị kill hoặc máy chủ mất điện giữa transaction, buffer trong bộ nhớ mất. Framework có thể không kịp cập nhật `BatchStatus` và `endTime` trong JobRepository. Bản ghi JobExecution/StepExecution có thể còn `STARTED`, dù không còn thread nào thực thi.

Khi đó, cần xác định execution có thực sự còn chạy hay không trước khi can thiệp. Không nên khởi chạy lại cùng JobInstance một cách tùy tiện nếu repository vẫn đánh dấu execution đang hoạt động; Spring Batch có thể từ chối do execution đang chạy.

Quy trình vận hành cần dựa trên JobExplorer/JobOperator và hướng dẫn recovery của hệ thống để xử lý execution bị treo. Không sửa trực tiếp `BATCH_*` table chỉ để đổi `STARTED` thành `FAILED` nếu chưa hiểu đầy đủ lock, version, metadata và dữ liệu nghiệp vụ.

## 7. Đọc metadata bằng JobExplorer

`JobExplorer` là API truy vấn metadata JobRepository theo hướng đọc. Có thể dùng nó để lấy JobExecution, StepExecution và ExecutionContext thay vì truy vấn SQL thủ công.

Ví dụ đọc trạng thái JobExecution và các StepExecution:

```java
public void inspectJobExecution(
        JobExplorer jobExplorer,
        long jobExecutionId) {

    JobExecution jobExecution = jobExplorer.getJobExecution(jobExecutionId);
    if (jobExecution == null) {
        log.warn("JobExecution {} was not found", jobExecutionId);
        return;
    }

    log.info(
            "jobExecutionId={}, jobInstanceId={}, status={}, exitStatus={}, start={}, end={}",
            jobExecution.getId(),
            jobExecution.getJobInstance().getId(),
            jobExecution.getStatus(),
            jobExecution.getExitStatus(),
            jobExecution.getStartTime(),
            jobExecution.getEndTime()
    );

    for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
        log.info(
                "step={}, stepExecutionId={}, status={}, exitStatus={}, " +
                "read={}, write={}, skips={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getId(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );
    }
}
```

Tên API cụ thể có thể khác đôi chút theo phiên bản Spring Batch. `JobExplorer` phù hợp cho màn hình giám sát, endpoint quản trị hoặc công cụ điều tra vì nó sử dụng abstraction của framework và không yêu cầu code ứng dụng tự phụ thuộc trực tiếp vào tên bảng metadata.

Khi đọc execution đang chạy, dữ liệu có thể thay đổi trong lúc truy vấn. Để phân tích kết quả cuối cùng, hãy đọc lại sau khi execution đã kết thúc hoặc sau khi quy trình recovery hoàn tất.

## 8. Truy vấn các bảng metadata trực tiếp

Trong schema JDBC repository tiêu chuẩn, metadata thường nằm trong các bảng `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`. Prefix/tên bảng có thể được tùy chỉnh; schema cũng có thể khác giữa phiên bản Spring Batch.

### Xem trạng thái JobExecution

```sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_JOB_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId;
```

Truy vấn này cho biết JobExecution đang `STARTED`, `COMPLETED`, `FAILED` hay trạng thái khác; đồng thời cho biết exit code và thời gian kết thúc.

### Xem trạng thái và counter của từng StepExecution

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

Khi một Step có rollback, xem `ROLLBACK_COUNT` cùng `COMMIT_COUNT`, counter đọc/ghi và `STATUS`. Đừng kết luận dữ liệu bị mất chỉ từ `ROLLBACK_COUNT`; cần đối chiếu số liệu đã commit và dữ liệu đích.

### Xem ExecutionContext của Step

```sql
SELECT
    STEP_EXECUTION_ID,
    SHORT_CONTEXT,
    SERIALIZED_CONTEXT
FROM BATCH_STEP_EXECUTION_CONTEXT
WHERE STEP_EXECUTION_ID = :stepExecutionId;
```

`SHORT_CONTEXT` thường chứa dạng rút gọn hoặc biểu diễn văn bản của context; `SERIALIZED_CONTEXT` có thể được dùng tùy cấu hình serializer và schema. Không nên chỉnh sửa trực tiếp các cột này bằng SQL để ép checkpoint sang vị trí khác.

Các tên cột có thể thay đổi theo schema/version và database. Hãy kiểm tra schema JobRepository mà ứng dụng thực sự cài đặt trước khi chạy query vận hành.

## 9. Đối chiếu metadata với dữ liệu nghiệp vụ

Metadata và dữ liệu nghiệp vụ có thể nằm trong cùng database hoặc ở các resource khác nhau. Khi dùng cùng transaction manager và cùng transaction, cập nhật business data và metadata checkpoint có thể được commit/rollback nhất quán. Nếu dùng nhiều transaction manager hoặc side effect ngoài transaction, không thể mặc định chúng atomic.

Ví dụ, writer ghi 50 đơn hàng vào database cùng transaction với chunk. Nếu insert thứ 51 gây lỗi và transaction rollback, 50 insert chưa commit có thể bị hoàn tác. Metadata checkpoint tương ứng cũng cần quay về tiến độ commit trước đó nếu cùng transaction được quản lý.

Ngược lại, nếu writer đã gửi 50 message lên broker rồi lỗi ở message 51, transaction database rollback không tự thu hồi các message đã được broker nhận. Metadata có thể cho thấy chunk chưa commit, nhưng hệ thống bên ngoài đã có side effect. Khi restart/retry, cần idempotency key hoặc inbox/outbox để tránh phát sinh trùng.

Khi điều tra, hãy lập bảng đối chiếu:

| Kiểm tra | Nguồn | Mục tiêu |
|---|---|---|
| Checkpoint gần nhất | Step ExecutionContext | Biết vị trí reader sẽ khôi phục |
| Commit/rollback counters | StepExecution | Hiểu lịch sử transaction ở cấp Step |
| Bản ghi đã ghi | Database đích | Xác nhận thay đổi nghiệp vụ thực sự tồn tại |
| Message/API/file đã phát | Hệ thống đích hoặc audit log | Phát hiện side effect không rollback được |
| Exception và exit message | Job/Step metadata và application log | Xác định nguyên nhân rollback/failure |

## 10. Ví dụ phân tích một Step sau rollback

Giả sử Step nhập 1.000 item với commit interval 100. Metadata sau khi Step kết thúc có:

| Trường | Giá trị minh họa |
|---|---:|
| `readCount` | 1.000 |
| `writeCount` | 1.000 |
| `commitCount` | 10 |
| `rollbackCount` | 2 |
| `skipCount` | 0 |
| `BatchStatus` | `COMPLETED` |
| `ExitStatus` | `COMPLETED` |

Một cách diễn giải hợp lý là Step đã trải qua hai lần rollback trong quá trình chạy, nhưng retry hoặc recovery đã thành công; cuối cùng 1.000 item được ghi và 10 chunk commit. Đây chỉ là số liệu minh họa; không suy ra số invocation chính xác chỉ từ các counter.

Trường hợp khác:

| Trường | Giá trị minh họa |
|---|---|
| `readCount` | 450 |
| `writeCount` | 400 |
| `commitCount` | 4 |
| `rollbackCount` | 1 |
| `BatchStatus` | `FAILED` |
| `ExitStatus` | `FAILED` |
| `ExecutionContext` | Checkpoint ở chunk cuối đã commit |

Step đã commit bốn chunk, sau đó chunk tiếp theo thất bại. Khi restart cùng JobInstance, reader có thể tiếp tục từ checkpoint của chunk cuối đã commit. Tuy nhiên, cần kiểm tra writer có side effect ngoài transaction hay không trước khi chạy lại phần chưa commit.

## 11. Trạng thái STARTED sau khi process bị kill

Một tình huống vận hành thường gặp là Job bị kill giữa chunk. Transaction database có thể rollback khi connection bị đóng, nhưng JVM không còn cơ hội chạy các callback kết thúc Step và cập nhật metadata trạng thái cuối.

Khi đó, bảng metadata có thể vẫn cho thấy:

```text
BATCH_JOB_EXECUTION.STATUS  = STARTED
BATCH_STEP_EXECUTION.STATUS = STARTED
END_TIME                    = NULL
```

Đây không phải bằng chứng rằng Job vẫn thực sự chạy. Cũng không phải bằng chứng chắc chắn transaction đã rollback hoàn toàn ở mọi resource. Cần kiểm tra process/worker, database session, lock, log và trạng thái các hệ thống đích.

Quy trình recovery cần được thực hiện bằng công cụ vận hành/API được hệ thống cho phép, ví dụ `JobOperator` hoặc quy trình quản trị riêng. Chỉ đánh dấu execution cũ là `FAILED`/`ABANDONED` sau khi xác nhận không còn worker hoạt động và hiểu tác động đến checkpoint, lock và dữ liệu đích.

Không chạy lại cùng JobInstance trong khi execution cũ vẫn được xem là đang chạy. JobRepository có thể từ chối khởi chạy trùng để bảo vệ metadata và dữ liệu.

## 12. JobExplorer và JobOperator có vai trò khác nhau

`JobExplorer` chủ yếu dùng để đọc metadata. Nó phù hợp cho việc kiểm tra trạng thái, lịch sử execution và checkpoint.

`JobOperator` cung cấp các thao tác vận hành như start, restart, stop hoặc truy vấn thông tin theo API của phiên bản Spring Batch. Đây là công cụ để điều khiển execution theo quy tắc framework, không phải lý do để bỏ qua việc xác minh execution cũ còn chạy hay không.

Khi phát hiện execution bị treo sau crash:

1. Dùng JobExplorer để xác định JobInstance, JobExecution và StepExecution liên quan.
2. Kiểm tra process/worker và database session để xác nhận execution không còn hoạt động.
3. Đối chiếu checkpoint cùng dữ liệu nghiệp vụ đã commit.
4. Thực hiện quy trình recovery được phê duyệt, dùng JobOperator hoặc công cụ quản trị của ứng dụng.
5. Restart với cùng identifying JobParameters nếu muốn tiếp tục cùng JobInstance.
6. Theo dõi execution mới và xác nhận không có side effect trùng.

API và quyền thao tác phụ thuộc cấu hình ứng dụng. Không nên xây dựng endpoint cho phép bất kỳ người dùng nào sửa trạng thái execution hoặc restart tùy ý mà không có kiểm soát vận hành.

## 13. Những nhầm lẫn thường gặp

**Cho rằng rollback luôn làm Step FAILED.** Retry có thể phục hồi lỗi và Step vẫn hoàn tất. Hãy xem trạng thái cuối cùng.

**Cho rằng rollbackCount là retry count.** Đây là hai chỉ số khác nhau. Dùng retry instrumentation nếu cần số lần thử chính xác.

**Cho rằng readCount bằng số item đã commit.** Item đã đọc có thể thuộc chunk rollback. Hãy xem write/commit counters và checkpoint.

**Cho rằng ExecutionContext luôn chứa vị trí reader vừa đọc cuối cùng.** Checkpoint bền vững cần phản ánh tiến độ đã commit. Chunk chưa commit không nên được coi là hoàn tất.

**Cho rằng process crash tự cập nhật FAILED.** Nếu process không kịp chạy callback cuối, metadata có thể còn STARTED. Cần quy trình recovery.

**Chỉ xem metadata mà không xem dữ liệu đích.** Side effect ngoài transaction có thể tồn tại dù chunk rollback. Đối chiếu business data và hệ thống ngoài.

**Sửa trực tiếp BATCH_* table để restart.** Metadata có quan hệ với version, context và transaction. Dùng API/quy trình vận hành có kiểm soát.

## 14. Kiểm thử metadata sau rollback

Để xác nhận hành vi của ứng dụng, nên có integration test dùng JobRepository và transaction manager phù hợp:

1. Tạo Step đọc một số item và writer cố ý ném exception trong chunk đầu tiên.
2. Xác nhận transaction của chunk rollback và các thay đổi database chưa commit không còn.
3. Cấu hình retry để lần thử tiếp theo thành công; xác nhận Step cuối cùng `COMPLETED` và rollback counter được ghi nhận phù hợp.
4. Tạo tình huống retry hết giới hạn; xác nhận Step/Job kết thúc `FAILED` và exit message có nguyên nhân.
5. Kiểm tra ExecutionContext sau commit để xác nhận checkpoint phản ánh chunk cuối đã commit.
6. Dừng Job giữa các chunk rồi restart cùng JobInstance; xác nhận reader khôi phục đúng vị trí.
7. Nếu có side effect ngoài transaction, xác nhận idempotency/outbox ngăn việc phát sinh trùng sau retry hoặc restart.
8. Kiểm tra trạng thái metadata khi execution bị dừng đột ngột bằng môi trường test có thể mô phỏng process failure phù hợp.

Không chỉ assert một giá trị `rollbackCount`. Hãy kiểm tra cả trạng thái, exit code, counter, ExecutionContext và dữ liệu nghiệp vụ cuối cùng. Một test dùng repository in-memory bị tạo mới giữa hai lần chạy không chứng minh được checkpoint bền vững qua process restart.

## 15. Quy trình kiểm tra sau rollback

Khi một chunk rollback, trước hết xác định đó là rollback được retry trong cùng process, lỗi khiến Step thất bại hay process crash giữa execution. Sau đó kiểm tra `JobExecution` và `StepExecution` để đọc `BatchStatus`, `ExitStatus`, counters và exception. Xem Step `ExecutionContext` để tìm checkpoint cuối cùng đã lưu, rồi đối chiếu với dữ liệu nghiệp vụ và side effect ở hệ thống ngoài.

Nếu Step vẫn đang chạy, theo dõi execution. Nếu retry phục hồi, xác nhận Step hoàn tất và dữ liệu đích nhất quán. Nếu Step thất bại, restart cùng JobInstance với identifying parameters ban đầu sau khi xử lý nguyên nhân. Nếu metadata còn `STARTED` sau crash, xác minh không còn worker hoạt động và dùng quy trình recovery được kiểm soát trước khi restart.

Kiểm tra metadata đúng cách giúp phân biệt một rollback đã được phục hồi với một execution thất bại hoặc bị treo. Kết hợp JobExplorer, JobRepository, ExecutionContext, log và dữ liệu nghiệp vụ sẽ cho thấy phần nào đã commit, phần nào cần chạy lại và side effect nào cần đối soát.
