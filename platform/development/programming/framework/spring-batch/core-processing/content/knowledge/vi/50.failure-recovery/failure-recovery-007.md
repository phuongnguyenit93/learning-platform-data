# Database mất kết nối — Failure recovery trong Spring Batch

## 1. Tình huống: batch đang chạy thì database không còn truy cập được

Một job nhập đơn hàng chạy lúc 01:00, đọc dữ liệu từ file CSV, chuẩn hóa bằng `ItemProcessor` và ghi xuống PostgreSQL bằng `JdbcBatchItemWriter`. Sau 80.000 bản ghi, database chuyển primary trong quá trình failover. Connection hiện tại bị đóng; writer ném ngoại lệ. Job phải xác định phần nào đã commit, phần nào cần xử lý lại và cách tiếp tục khi PostgreSQL sẵn sàng.

Trong một hệ thống khác, database nghiệp vụ vẫn hoạt động nhưng database chứa metadata của Spring Batch lại mất kết nối. Job có thể xử lý dữ liệu nhưng không cập nhật được `StepExecution`, `JobExecution` hoặc `ExecutionContext`. Đây là tình huống khác biệt quan trọng: **thành công của thao tác nghiệp vụ trong bộ nhớ không đồng nghĩa với checkpoint đã được lưu**.

Khi database bị mất kết nối, ba quyết định vận hành cần tách biệt:

1. **Phát hiện và phân loại:** lỗi xảy ra ở reader, processor, writer, commit hay `JobRepository`? Có phải lỗi kết nối tạm thời, lỗi SQL cố định, hay tình trạng commit không rõ kết quả?
2. **Phục hồi:** có thể retry trong cùng step/transaction, phải rollback rồi restart `JobInstance`, hay cần điều tra và đối soát trước khi chạy lại?
3. **Đảm bảo dữ liệu:** các item đã commit phải không bị mất; item chưa commit phải được xử lý lại đúng cách; side effect phải không nhân đôi ngoài hợp đồng nghiệp vụ.

Bài học này thuộc nhóm **Failure recovery** trong **Spring Batch Core Processing**, tập trung vào cơ chế transaction, retry, checkpoint, restart, JDBC connection pool, metadata và khả năng quan sát khi database outage.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, HikariCP, JUnit 5. Một số API đã đổi ở Spring Batch 6.x; luôn đối chiếu phiên bản framework thực tế khi dùng code.

---

## 2. Hai loại database và hai loại mất kết nối

### 2.1. Database nghiệp vụ

Database nghiệp vụ là nơi reader đọc hoặc writer ghi customer/order/invoice. Nếu connection mất trong khi SQL đang thực thi:

- Reader có thể không lấy được item tiếp theo.
- Writer có thể thất bại khi gửi batch insert/update.
- Transaction có thể bị rollback.
- Step có thể `FAILED` nếu retry không xử lý được hoặc đã hết giới hạn.
- Một lần restart phù hợp có thể dùng checkpoint trong `ExecutionContext` để tiếp tục.

### 2.2. Metadata database của Spring Batch

`JobRepository` lưu metadata như:

- `JobInstance`: một đợt xử lý logic gắn với tên job và identifying `JobParameters`.
- `JobExecution`: mỗi lần job được thực thi; trạng thái `STARTED`, `FAILED`, `COMPLETED`...
- `StepExecution`: status, read/write/skip/rollback/commit counts của step.
- `ExecutionContext`: dữ liệu trạng thái cần để restart, ví dụ offset, cursor position hoặc checkpoint của reader/writer.

Một triển khai JDBC thường dùng các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`.

Nếu database metadata không khả dụng, Spring Batch có thể thất bại khi tạo execution **trước khi công việc nghiệp vụ bắt đầu**, hoặc không thể persist checkpoint/trạng thái khi step đang chạy. Nếu process chết đột ngột, metadata có thể còn ở `STARTED` dù không còn worker thực sự xử lý.

### 2.3. Sơ đồ phạm vi lỗi

```text
             Scheduler / REST / Operator
                        |
                        v
                   JobLauncher
                        |
                        v
           +---------------------------+
           | JobRepository             |
           | JobExecution              |
           | StepExecution             |
           | ExecutionContext          |
           +-------------+-------------+
                         |
                         v
                METADATA DATABASE
                  bảng BATCH_*
                         ^
                         |
              mất kết nối ở đây
              => có thể không ghi
                 được trạng thái

      +-----------------------+
      | Chunk Step            |
      | read -> process       |
      |          -> write     |
      +-----------+-----------+
                  |
                  v
             BUSINESS DATABASE
              bảng nghiệp vụ
                  ^
                  |
           mất kết nối ở đây
           => lỗi read/write/commit
```

Hai database có thể thực chất là cùng một database/schema và cùng `DataSource`, hoặc được tách riêng. Cơ chế phục hồi phụ thuộc vào cách wiring **`DataSource` và `PlatformTransactionManager`**, không chỉ tên bean.

| Tình huống | Metadata của Spring Batch | Dữ liệu nghiệp vụ | Hướng điều tra |
| --- | --- | --- | --- |
| Business DB mất, metadata DB còn | Có thể ghi nhận `FAILED` và checkpoint đã commit | SQL đang chạy thất bại | Retry có giới hạn, rollback, restart |
| Metadata DB mất trước khi launch | Chưa chắc tạo được `JobExecution` | Có thể chưa đụng đến | Sửa metadata DB, tra lại instance trước khi launch |
| Metadata DB mất giữa step | Có thể còn trạng thái cũ hoặc không cập nhật được kết quả | Có thể một số chunk đã commit | Reconcile cả hai bên trước khi restart |
| Cả hai cùng mất | Job/step metadata và giao dịch nghiệp vụ đều ảnh hưởng | Kết quả có thể chưa rõ | Phục hồi hạ tầng, đối soát checkpoint/commit |
| DB trả lời timeout tại commit | Metadata có thể đi trước hoặc đi sau tùy thứ tự | **Không chắc commit thành công hay thất bại** | Tra trạng thái thực tế; idempotency |

**Không giả định rằng cùng database vật lý tức tất cả metadata và business updates tự động nằm trong một transaction duy nhất.** Transaction manager, datasource, propagation và thứ tự ghi mới quyết định tính nguyên tử của từng phần.

---

## 3. Lỗi có thể xảy ra ở giai đoạn nào?

### 3.1. Trước khi job được launch

Ứng dụng không thể kết nối metadata DB khi gọi `JobLauncher.run(...)`. Framework có thể không tạo được `JobInstance`/`JobExecution`, hoặc tạo được một phần metadata trước khi caller nhận lỗi.

Điều cần làm: **tra repository sau khi kết nối phục hồi**, dùng tên job và identifying parameters để xác định có execution nào được tạo trước khi quyết định gửi launch lần nữa. Nếu client timeout sau khi yêu cầu đã đến server, việc gọi lại với parameters ngẫu nhiên có thể mở một đợt xử lý trùng.

### 3.2. Trong `ItemReader.read()`

Ví dụ `JdbcCursorItemReader` đang giữ một JDBC cursor. Khi connection hỏng:

- JDBC driver ném `SQLException` hoặc Spring JDBC bọc thành `DataAccessException`.
- Cursor/result set thường không còn hợp lệ.
- Retry trực tiếp `read()` trong cùng reader object có thể **không khôi phục được connection/cursor cũ**.
- Một restart step với reader được mở lại từ checkpoint đã lưu có thể phù hợp hơn.

Với `JdbcPagingItemReader`, mỗi lần fetch page là một truy vấn; sau khi datasource phục hồi, các truy vấn mới có thể chạy được. Tuy nhiên, phải đảm bảo sort key duy nhất/ổn định, state được lưu và dữ liệu nguồn không thay đổi theo cách gây thiếu/trùng item giữa các page.

### 3.3. Trong `ItemProcessor.process()`

Processor có thể là logic Java thuần hoặc gọi repository/JDBC/HTTP. Nếu processor gọi database để tra cứu trạng thái và connection mất, ta cần phân biệt:

- Lỗi kết nối tạm thời, có thể retry trong cùng chunk nếu thao tác và tài nguyên còn hợp lệ.
- Lỗi SQL không thể tự lành như thiếu cột, sai mapping, constraint violation.
- Lỗi nghiệp vụ không liên quan database, ví dụ dữ liệu đầu vào không hợp lệ.

Một processor đọc dữ liệu từ DB có thể được retry, nhưng side effect của processor không nhất thiết transactional. Nếu processor gửi sự kiện/email trước khi lỗi, retry có thể nhân đôi hành động.

### 3.4. Trong `ItemWriter.write(Chunk)`

Writer có thể ghi nhiều item trong một transaction. Khi JDBC mất kết nối:

- SQL batch có thể mới thực hiện được một phần tại database.
- Transaction có thể bị rollback hoặc connection chết trước khi kết quả xác định.
- Writer gọi lại trên cùng chunk khi retry có thể gặp duplicate key nếu một phần side effect đã tồn tại ngoài transaction.
- Không thể suy ra `write()` ném exception nghĩa là **mọi hiệu ứng ở hệ thống đích đều chắc chắn chưa xảy ra**.

Đặc biệt với remote API, message broker hoặc database khác transaction manager, những thao tác đã thành công trước lỗi có thể không bị rollback cùng chunk.

### 3.5. Trong transaction commit

`write()` có thể trả về thành công nhưng `PlatformTransactionManager.commit(...)` thất bại vì mất connection/timeout.

```text
Writer gửi INSERT thành công
           |
           v
Database nhận COMMIT
           |
           X  network mất khi trả response
           |
     Client không biết kết quả
```

Server có thể đã commit trước khi phản hồi bị mất; hoặc chưa commit và transaction bị rollback. Đây là **ambiguous commit outcome**. Mù quáng chạy lại với ID mới hoặc ghi thêm bản sao là nguy hiểm.

Cần dùng business key duy nhất, idempotency, query xác minh trạng thái database sau khi phục hồi và đối soát kết quả trước khi retry/restart.

### 3.6. Trong cập nhật `JobRepository` và checkpoint

Có thể transaction nghiệp vụ đã commit nhưng repository không ghi được `ExecutionContext`/`StepExecution` do metadata connection hỏng. Lần restart có thể bắt đầu từ checkpoint cũ và xử lý lại dữ liệu đã ghi.

Nếu metadata và dữ liệu nghiệp vụ cùng transaction manager và cùng transactional resource, ranh giới nguyên tử có thể tốt hơn. Nếu tách datasource, phải thiết kế để đối phó **không có atomic commit mặc định trên hai nguồn**. Đừng lấy một `ExecutionContext` trong bộ nhớ làm bằng chứng checkpoint đã persist.

---

## 4. Connection, transaction, chunk và checkpoint

Trong chunk-oriented processing, Spring Batch thường đọc và xử lý một nhóm item rồi ghi và commit. Ví dụ chunk size 100:

```text
Chunk 1: records 1..100   -> write -> COMMIT
Chunk 2: records 101..200 -> write -> COMMIT
Chunk 3: records 201..300 -> lỗi trước COMMIT
                            |
                            v
                       ROLLBACK
```

Nếu metadata/checkpoint 200 đã được lưu nhất quán, restart phải tiếp tục từ trạng thái cuối cùng đã commit, không phải từ item 300 đã đọc trong bộ nhớ.

### 4.1. Trạng thái “đã đọc” khác “đã commit”

Reader có thể đã trả về 280 item, nhưng transaction cuối mới commit đến 200. Các item 201–280 cần được phép xử lý lại. Điều này đòi hỏi reader lưu state theo contract `ItemStream` và writer xử lý idempotently khi gặp lại một item sau rollback/restart.

### 4.2. `ItemStream` và `ExecutionContext`

Reader/writer có trạng thái thường implement `ItemStream`:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

- `open` nhận context được khôi phục khi step bắt đầu, bao gồm restart.
- `update` ghi state mới vào context theo ranh giới checkpoint.
- `close` giải phóng tài nguyên.

Nếu delegate được bọc bởi wrapper, step cần nhận diện/đăng ký `ItemStream` thích hợp. Bỏ mất lifecycle callbacks có thể khiến step chạy bình thường đến lúc gặp outage rồi restart từ đầu.

Ví dụ luồng:

```text
Execution #1:
  open(context offset=0)
  commit chunk 1 -> context offset=100
  commit chunk 2 -> context offset=200
  chunk 3 error -> rollback, step FAILED

Repository: last persisted offset=200

Execution #2 (restart cùng JobInstance):
  open(context offset=200)
  tiếp tục xử lý các item chưa commit
```

Số offset là minh họa. Với paging/cursor reader thực tế, semantics checkpoint và việc rollback/restart cần được xác minh theo loại reader cụ thể.

### 4.3. Khi có retry và rollback

Spring Batch fault-tolerant step có thể retry lời gọi `read`, `process` hoặc `write` tùy chính sách. Một số lần gọi được thực hiện lại sau rollback; tổng number of method invocations không nhất thiết bằng `readCount`/`writeCount`.

Để chẩn đoán, nên thu thập `commitCount`, `rollbackCount`, retry attempts, loại exception và số item output. Không dựa vào việc exception chỉ xuất hiện một lần trong log để kết luận DB hỏng đúng một transaction.

---

## 5. Phân loại ngoại lệ: lỗi có thể phục hồi và lỗi cố định

### 5.1. Những exception thường gặp

Trong Spring JDBC, các exception thường được bọc thành `DataAccessException`. Một vài nhóm đáng phân biệt:

| Exception / nhóm | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `CannotGetJdbcConnectionException` | Không lấy được JDBC connection | Kiểm tra DB/pool/network; retry có hạn nếu hạ tầng dự kiến phục hồi |
| `DataAccessResourceFailureException` | Tài nguyên data access không khả dụng | Có thể là DB/network outage; thường cần phục hồi hạ tầng |
| `TransientDataAccessException` | Nhóm lỗi được mô tả là có khả năng thành công khi thử lại | Retry có giới hạn nếu thao tác an toàn |
| `TransientDataAccessResourceException` | Tài nguyên tạm thời không sẵn sàng | Retry/backoff sau khi xác nhận retryable |
| `DeadlockLoserDataAccessException` / lỗi locking transient | Transaction bị tranh chấp hoặc deadlock | Retry toàn transaction với backoff khi phù hợp |
| `QueryTimeoutException` | Truy vấn vượt timeout | Kiểm tra tải/SQL; timeout không tự chứng minh commit thất bại |
| `DuplicateKeyException` / constraint violation | Vi phạm ràng buộc dữ liệu | Thường không phải outage; xử lý idempotency hoặc lỗi nghiệp vụ |
| `BadSqlGrammarException` | SQL/schema không phù hợp | Không retry liên tục; sửa code/schema |
| `SQLTransientConnectionException` (JDBC) | Driver đánh dấu lỗi kết nối tạm thời | Phân loại theo driver và nguyên nhân thực |
| `SQLRecoverableException` (JDBC) | Có thể cần tạo connection mới và lặp lại transaction | Không reuse connection đã chết |

**Lưu ý về phân cấp exception:** một lỗi kết nối thực tế không nhất thiết nằm trong `TransientDataAccessException`. Ví dụ `CannotGetJdbcConnectionException` có thể được bọc qua tầng resource failure khác tùy Spring JDBC/driver và phiên bản. Vì thế, retry chỉ theo một superclass rất hẹp có thể bỏ sót outage, còn retry mọi `DataAccessException` lại có thể lặp vô ích lỗi SQL cố định.

### 5.2. SQLState và vendor error code

JDBC driver cung cấp `SQLState` và vendor error code. Ví dụ nhiều driver dùng nhóm SQLState `08xxx` cho connection exception; PostgreSQL có các mã `08006`, `08001` trong một số tình huống. Nhưng:

- Code cụ thể thay đổi theo driver và giai đoạn lỗi.
- Một exception có thể được framework bọc nhiều lớp.
- Connection timeout cũng có thể xuất hiện qua pool timeout hoặc network exception không còn SQLState.
- SQLState chỉ là một tín hiệu, không thay thế thông tin operation/transaction.

Một classifier có thể kiểm tra loại `DataAccessException`, cause chain, SQLState và operation để quyết định **retry, fail fast hoặc cần reconciliation**. Không nên chuyển tất cả `SQLException` thành “retryable” một cách vô điều kiện.

### 5.3. Phân loại theo thao tác quan trọng hơn tên exception đơn lẻ

Cùng một lỗi socket timeout nhưng ý nghĩa khác nhau:

- `SELECT` idempotent chưa trả row: thường có thể tạo connection mới rồi query lại.
- `UPDATE` trong transaction đã rollback xác định: có thể retry transaction.
- `COMMIT` không trả response: cần xác minh kết quả; retry mù có thể gây lặp.
- Gọi API thanh toán ngoài transaction: phải kiểm tra idempotency key ở hệ thống đích.

Cách phân loại nên đi cùng bối cảnh: **operation + transaction boundary + idempotency + available checkpoint**.

---

## 6. Retry tại chỗ hay restart job?

### 6.1. Retry trong một `StepExecution`

Retry có ích với lỗi ngắn hạn như:

- Connection pool tạm hết nhưng phục hồi trong vài giây.
- Deadlock hoặc serialization conflict, khi transaction có thể thực hiện lại.
- Network hiccup ngắn và thao tác idempotent.
- Database failover rất ngắn, với connection mới có thể hoạt động.

Retry cần:

- Giới hạn attempts.
- Backoff để không tạo retry storm.
- Timeout hợp lý để tránh kéo dài vô hạn.
- Ngoại lệ được phân loại.
- Khả năng tái tạo transaction/resource và giữ đúng semantics khi retry.

Retry **không bảo đảm** JDBC cursor đang hỏng có thể tiếp tục trong cùng reader. Nếu connection vẫn chưa phục hồi hoặc state không hợp lệ, để step kết thúc `FAILED` rồi restart từ checkpoint có thể an toàn hơn.

### 6.2. Restart tạo một `JobExecution` mới

Khi Step đã `FAILED` và nguyên nhân hạ tầng được xử lý, restart có thể tạo execution mới cho **cùng `JobInstance`**:

```text
JobInstance: importOrdersJob + businessDate=2026-11-16
    |
    +-- JobExecution #3001 FAILED
    |     reader checkpoint = 200
    |
    +-- JobExecution #3002 COMPLETED
          reader resumes from persisted checkpoint
```

Với Spring Batch 5.x:

```java
Long restartedExecutionId = jobOperator.restart(3001L);
```

`restart` nhận **JobExecution ID**, không phải JobInstance ID. Điều kiện: execution và job cho phép restart, định nghĩa job còn tồn tại, metadata repository truy cập được, không có execution khác đang chạy hoặc instance đã completed.

### 6.3. Quyết định theo tình huống

| Tình huống | Ưu tiên | Giải thích |
| --- | --- | --- |
| Reader query timeout ngắn, connection vẫn hợp lệ | Retry có giới hạn nếu driver/reader an toàn | Không cần tạo execution mới khi lỗi tạm |
| Cursor JDBC bị đóng sau network reset | Fail step rồi restart từ checkpoint | Không giả định cursor cũ tự lành |
| Writer gặp deadlock và transaction rollback được xác định | Retry transaction/chunk với backoff | Tránh retry mỗi statement tách rời |
| Metadata DB mất lâu, job không thể persist | Khôi phục metadata trước; reconcile | Không thể bảo đảm checkpoint/restart khi repository không khả dụng |
| Connection mất ngay tại `COMMIT`, kết quả không chắc | Reconcile output và metadata trước khi replay | Tránh duplicate/lost writes |
| SQL syntax sai hoặc table không tồn tại | Fail fast và sửa cấu hình/schema | Retry chỉ làm tăng tải |
| Business input cố định bị lỗi validation | Skip/quarantine theo hợp đồng nghiệp vụ | Không phải lỗi hạ tầng tạm thời |
| Job `COMPLETED` và cần xử lý ngày khác | Launch instance mới với parameters khác | Restart không dành cho job đã completed |
| Job execution cũ còn `STARTED` sau crash | Kiểm tra worker thực tế và recovery procedure | Không ép restart ngay khi chưa xác nhận process cũ đã ngừng |

---

## 7. Cấu hình fault-tolerant chunk retry trong Spring Batch 5

### 7.1. Ví dụ `StepBuilder`

Một chunk step ghi đơn hàng có thể cấu hình retry **một nhóm exception đã được lựa chọn rõ ràng**. Ví dụ này giả định các bean reader/processor/writer và transaction manager đã được định nghĩa trong ứng dụng:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, OrderRow> processor,
        ItemWriter<OrderRow> writer) {

    ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(4_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderRow>chunk(
            100, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOff)
        .build();
}
```

`OrderRow` là kiểu dữ liệu nghiệp vụ minh họa. Cấu hình trên tạo fault-tolerant step cho các lỗi thuộc nhóm `TransientDataAccessException`, với giới hạn tổng nỗ lực do `retryLimit(3)` quy định và backoff tăng dần. Chỉ riêng cấu hình này **không bao phủ mọi lỗi mất kết nối database**; classifier phải được điều chỉnh theo các ngoại lệ thực tế của JDBC driver, Spring exception translation và thao tác đang thực hiện.

### 7.2. Vì sao không dùng `retry(Exception.class)`?

Thử lại mọi exception có thể:

- Retry lỗi mapping/validation không bao giờ tự khỏi.
- Tạo nhiều query hoặc write không cần thiết khi database đang mất dài hạn.
- Che lỗi cấu hình, khiến step chạy lâu trước khi báo `FAILED`.
- Tạo lại side effect ngoài transaction.
- Gây “retry storm” khi nhiều worker cùng mất DB.

Ưu tiên danh sách lỗi có thể phục hồi **đã hiểu semantics**; còn lỗi cố định phải fail fast và được cảnh báo.

### 7.3. Vì sao không tự `Thread.sleep` trong reader/writer?

Tự viết vòng lặp vô hạn trong `ItemWriter.write` làm mất khả năng quản lý retry budget, rollback và kiểm soát stop. Nếu cần backoff, hãy dùng cơ chế retry của Spring Batch/Retry; quan sát duration và số attempts. Với outage dài, tốt hơn là fail step có kiểm soát để orchestrator/JobOperator restart sau khi DB đã phục hồi.

### 7.4. Cẩn thận với retry của writer

Một chunk có thể được gọi lại sau rollback. Nếu writer dùng JDBC trong cùng transaction, phần SQL chưa commit thường được rollback cùng transaction. Nhưng nếu writer gọi service ngoài transactional resource hoặc commit kết quả không xác định, retry có thể phát lệnh trùng.

Do vậy, trước khi bật retry cho writer, xác định:

- Transaction resource nào thực sự rollback?
- Batch SQL có atomic trong transaction hay từng statement auto-commit?
- Remote side effect có idempotency key không?
- Có thể truy vấn xác nhận kết quả sau lỗi timeout không?
- Checkpoint được cập nhật khi nào?

### 7.5. Skip không phải cách xử lý database outage

`skip(FlatFileParseException.class)` có thể hợp lý để bỏ một dòng file lỗi có thể cách ly. Nhưng nếu DB không kết nối được, `skip(DataAccessException.class)` có thể khiến hàng nghìn item bị bỏ qua và job báo `COMPLETED` với output thiếu.

Một outage là **lỗi hạ tầng** ảnh hưởng toàn chuỗi thao tác; thường nên retry có giới hạn rồi fail/restart. Chỉ skip khi nghiệp vụ định nghĩa rõ một record không thể xử lý và có nơi lưu lỗi/quarantine, không dùng skip để che mất DB.

---

## 8. Connection pool HikariCP sau khi database outage

Spring Boot 3.x thường sử dụng HikariCP cho JDBC datasource. HikariCP quản lý pool connection; khi một connection hỏng, pool có thể loại bỏ nó và tạo connection mới khi database trở lại. Nhưng **connection vật lý đã chết không được “chữa lành” bên trong transaction đang chạy**.

### 8.1. Những timeout cần phân biệt

| Cấu hình/khái niệm | Điều khiển | Điều không giải quyết |
| --- | --- | --- |
| `spring.datasource.hikari.connection-timeout` | Thời gian tối đa chờ lấy connection từ pool | Không giới hạn mọi query đang chạy |
| `validation-timeout` | Thời gian tối đa dành cho connection validation | Không phải timeout giao dịch |
| `idle-timeout` | Điều kiện loại bỏ connection nhàn rỗi, có ràng buộc theo pool settings | Không phục hồi transaction hỏng |
| `max-lifetime` | Tuổi thọ tối đa để pool thay connection theo cơ chế của Hikari | Không đảm bảo DB luôn sẵn sàng |
| JDBC driver connect timeout | Thời gian thiết lập kết nối mạng | Không phải retry budget |
| JDBC driver socket/read timeout | Chờ phản hồi từ database | Có thể để lại kết quả commit không chắc chắn |
| Statement/query timeout | Giới hạn thời gian SQL | Không thay thế transaction rollback/reconciliation |
| Batch retry backoff | Khoảng cách giữa các nỗ lực xử lý lại | Không tự tạo metadata/checkpoint đúng |

Các giá trị cần căn theo SLA, mức failover dự kiến, load và giới hạn downstream.

### 8.2. Ví dụ cấu hình có giới hạn chờ

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 5000
      validation-timeout: 2000
      max-lifetime: 1800000
```

Ví dụ dùng 5 giây cho việc chờ connection; không có nghĩa “sau 5 giây Spring Batch tự restart job”. Nếu PostgreSQL failover mất 60 giây, nhiều lượt retry ngắn có thể đều thất bại và job chuyển `FAILED`. Orchestrator phải dựa vào health/recovery signal để restart sau đó.

### 8.3. Hikari pool không thay thế observability

Khi database mất:

```text
Worker threads -> request JDBC connection
      |
      v
Hikari pool
  active  = 10
  idle    = 0
  pending = 30
      |
      v
Database unreachable
```

Nếu chỉ nhìn lỗi writer, dễ kết luận writer sai trong khi thực tế pool đang kẹt vì DB không đáp ứng. Cần xem metrics active/idle/pending, connection acquisition time, database health và network. Khi DB phục hồi, pool có thể dần tạo connection mới, nhưng task dùng connection cũ vẫn phải đi qua rollback/restart phù hợp.

### 8.4. Cẩn thận với connection do cursor giữ lâu

`JdbcCursorItemReader` có thể sử dụng connection/cursor xuyên nhiều lần read. Đứt connection giữa chừng làm mất cursor; dù pool đã phục hồi, reader đó không tự động biết cách tạo cursor ở vị trí an toàn. Cơ chế restart với `ExecutionContext` được persist quan trọng hơn việc hy vọng connection mới làm cursor cũ hoạt động.

---

## 9. Chọn reader phù hợp với chiến lược recovery

### 9.1. Cursor reader

`JdbcCursorItemReader` phù hợp để stream một result set, ít xử lý bộ nhớ hơn so với tải toàn bộ dữ liệu. Nhưng:

- Có thể phụ thuộc connection sống lâu.
- Khi connection mất, cursor invalid.
- Nguồn dữ liệu có thể thay đổi giữa execution và restart.
- Cần `saveState`, tên reader ổn định và checkpoint đúng.

Nếu muốn restart an toàn, đừng thay đổi tên/key của reader tùy tiện sau deploy, vì `ExecutionContext` đã lưu có thể không được đọc đúng.

### 9.2. Paging reader

`JdbcPagingItemReader` đọc theo page. Nó thường tạo query riêng cho page, có thể thuận tiện hơn khi không muốn giữ cursor mở lâu. Tuy nhiên:

- Sort key phải **duy nhất và ổn định**.
- Dữ liệu thêm/xóa/update trong lúc job chạy có thể làm tập item thay đổi.
- Page size khác chunk size và có ảnh hưởng riêng đến network/memory.
- Restart position phụ thuộc contract của reader và dữ liệu nguồn.

Khi dữ liệu thay đổi liên tục, cần cân nhắc snapshot, cutoff timestamp, deterministic ordering hoặc partition theo key range để không bỏ sót.

### 9.3. Reader từ file, writer vào database

Đây là trường hợp recovery dễ hình dung: file input thường bất biến, reader checkpoint lưu vị trí đã đọc, writer ghi vào DB. Sau DB outage và restart, reader có thể đọc lại từ offset cuối đã commit. Nhưng writer vẫn phải idempotent, vì mất kết nối ở commit có thể khiến một số output thực sự tồn tại dù metadata chưa cập nhật.

### 9.4. Không tự lưu offset “đã read” mỗi lần đọc như một commit

Một reader tự tăng `offset` mỗi khi trả item có thể được framework gọi `update` khi checkpoint, nhưng nếu code tự ghi offset vào một database riêng và commit ngay trước writer, offset có thể đi trước dữ liệu nghiệp vụ. Khi restart sẽ bỏ qua item chưa ghi.

Hãy để checkpoint theo lifecycle `ItemStream` của Spring Batch và hiểu transaction boundary. Nếu cần watermark riêng ngoài Spring Batch, quản lý nó cùng trạng thái output hoặc có reconciliation rõ ràng.

---

## 10. Writer idempotent để chịu được ambiguous commit

### 10.1. Vì sao cần idempotency?

Giả sử chunk có order IDs 201–300. Client gửi SQL, database đã commit chunk, nhưng response của `commit` mất. `JobRepository` không biết chắc checkpoint tương ứng đã persist. Khi restart, các order này có thể được đưa qua writer lần nữa.

Nếu mỗi lần ghi là insert không có unique constraint, database có thể có hai bản sao của cùng order. Một hệ thống robust cần đặt **business key** giúp việc ghi lại cùng item có kết quả hợp lệ.

### 10.2. Unique constraint

Ví dụ PostgreSQL:

```sql
CREATE TABLE imported_orders (
    source_system VARCHAR(40) NOT NULL,
    external_order_id VARCHAR(120) NOT NULL,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_imported_order
        UNIQUE (source_system, external_order_id)
);
```

Unique key nói rằng một order từ một source chỉ xuất hiện một lần. Chọn key đúng theo domain; có thể phải bao gồm version hoặc business date nếu cùng external ID được tái sử dụng theo kỳ.

### 10.3. UPSERT có semantics rõ ràng

PostgreSQL hỗ trợ:

```sql
INSERT INTO imported_orders (
    source_system,
    external_order_id,
    business_date,
    amount,
    imported_at
)
VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (source_system, external_order_id)
DO UPDATE SET
    business_date = EXCLUDED.business_date,
    amount = EXCLUDED.amount;
```

Nếu job restart và ghi lại cùng order, lệnh có thể cập nhật trạng thái hiện hữu thay vì tạo record thứ hai. Nhưng UPSERT không tự giải quyết mọi vấn đề:

- Nếu order đã được thay đổi hợp lệ sau lần import trước, việc ghi đè bằng dữ liệu cũ có thể sai.
- Nếu có trigger hoặc downstream event khi UPDATE, việc upsert lặp lại vẫn có side effect.
- Nếu cần append-only accounting, có thể phải dùng ledger event idempotent thay vì update.
- Nếu writer gửi email hoặc thanh toán, unique constraint trong database local không bảo vệ được hệ thống ngoài trừ khi idempotency key được truyền sang.

Một writer idempotent phải có **hợp đồng nghiệp vụ**, không chỉ câu lệnh SQL cho qua duplicate key.

### 10.4. Transactional outbox cho side effect ngoài DB

Khi Batch ghi trạng thái đơn hàng và cần phát event, có thể ghi bản ghi outbox trong cùng transaction database:

```text
Chunk transaction
   |
   +-- UPSERT imported_orders
   |
   +-- INSERT outbox_event (unique event_key)
   |
   +-- COMMIT
            |
            v
Outbox publisher đọc event chưa gửi
            |
            v
Message broker / API
```

Outbox giảm khoảng trống giữa “DB đã commit” và “event đã phát”, nhưng consumer/publisher vẫn phải idempotent vì có thể phát lại. Nếu business DB và metadata DB khác nhau, outbox **không tự tạo transaction nguyên tử với Spring Batch JobRepository**; restart vẫn phải xử lý khả năng dữ liệu nghiệp vụ đi trước checkpoint.

---

## 11. Một hoặc hai datasource ảnh hưởng recovery thế nào?

### 11.1. Cùng một datasource

Ứng dụng có thể dùng một `DataSource` cho `JobRepository` và JDBC writer. Khi step dùng transaction manager JDBC phù hợp, một số cập nhật trong chunk và metadata có thể tham gia các transaction được quản lý nhất quán theo cấu hình.

Tuy nhiên, phải kiểm tra **cụ thể** cấu hình của Spring Batch, transaction propagation, connection handling, step type và repository operation. Không mặc định mọi metadata write đều gắn chung một physical transaction với business SQL chỉ vì URL giống nhau.

### 11.2. Hai datasource riêng

```text
Spring Batch JobRepository
    |
    v
metadataDataSource -> DB A (BATCH_*)

JdbcBatchItemWriter
    |
    v
businessDataSource -> DB B (orders)
```

Nếu chunk writer commit tại DB B nhưng metadata checkpoint ở DB A lỗi, trạng thái có thể không đồng bộ. Hai local transaction managers không tự tạo distributed atomic commit.

Các chiến lược an toàn:

- Reader có state ổn định, checkpoint được persist khi có thể.
- Writer idempotent để xử lý lại chunk.
- Reconciliation giữa metadata và business output.
- Transactional outbox cho side effect thích hợp.
- Với yêu cầu nguyên tử xuyên nhiều resource cực chặt, xem xét distributed/XA transaction khi hệ thống thực sự hỗ trợ và chấp nhận chi phí vận hành; không coi đây là giải pháp mặc định cho mọi batch.

### 11.3. Database chứa metadata phải bền vững

Với job cần restart sau khi process chết, dùng JDBC `JobRepository` trên database giữ dữ liệu qua lần khởi động mới. H2 in-memory chỉ phù hợp để test restart trong cùng JVM khi database instance còn sống; nó không giữ lịch sử sau khi JVM tắt.

Nếu mất metadata database vĩnh viễn nhưng business output vẫn tồn tại, một job mới với `run.id` ngẫu nhiên không tự khôi phục nghĩa vụ còn dang dở. Cần có phương án restore backup/rebuild state và đối soát từ nguồn dữ liệu nghiệp vụ.

---

## 12. Khôi phục job với `JobOperator`

### 12.1. Điều kiện restart

Một `JobExecution` đã `FAILED` hoặc `STOPPED` có thể restart khi:

- Metadata repository truy cập được và còn lịch sử execution/context.
- Job definition hiện tại tương thích và được đăng ký để operator tìm thấy.
- Job cho phép restart; không cấu hình `preventRestart()`.
- JobInstance chưa có execution `COMPLETED` và không có execution khác đang chạy.
- Step chưa đạt `startLimit`, và data/checkpoint phù hợp.
- Sự cố database đã được xử lý và side effect đã được đối soát đủ để tiếp tục.

Trong Spring Batch 5.x:

```java
Long nextId = jobOperator.restart(failedExecutionId);
```

Method nhận **JobExecution ID cũ** và trả về ID execution mới. Tùy launcher synchronous/asynchronous, ID trả về chưa có nghĩa job đã `COMPLETED`.

### 12.2. Tra metadata trước khi gửi restart

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;

public class DatabaseFailureRecovery {

    private final JobExplorer explorer;
    private final JobOperator operator;

    public DatabaseFailureRecovery(
            JobExplorer explorer,
            JobOperator operator) {
        this.explorer = explorer;
        this.operator = operator;
    }

    public long restartAfterDatabaseRecovered(long executionId)
            throws Exception {

        JobExecution previous =
            explorer.getJobExecution(executionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                "Unknown JobExecution: " + executionId);
        }

        BatchStatus status = previous.getStatus();

        if (status != BatchStatus.FAILED &&
            status != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "Execution status does not permit restart: "
                    + status);
        }

        // Các kiểm tra an toàn quan trọng khác được thực hiện
        // tại lớp vận hành trước khi gọi method này:
        // DB health, actual running workers, side effects,
        // job definition compatibility, newer executions.
        return operator.restart(executionId);
    }
}
```

Precheck trên giúp thông báo lỗi rõ hơn nhưng không chống race: sau khi đọc `FAILED`, một node khác có thể đã restart cùng JobInstance. `JobOperator`/`JobRepository` vẫn phải kiểm tra điều kiện thực tế. Đừng bắt exception rồi tự thêm timestamp identifying mới để vượt qua việc instance đang chạy.

### 12.3. Xử lý execution bị kẹt ở `STARTED`

Nếu JVM chết đột ngột trước khi cập nhật trạng thái, repository có thể lưu `STARTED` dù worker đã mất:

```text
Metadata DB:
  JobExecution #901 = STARTED
Runtime:
  Pod cũ đã chết; không còn worker xử lý
```

Đây là **recovery trạng thái vận hành**, không phải job thất bại có status `FAILED` thông thường. Quy trình:

1. Xác nhận không có process/worker khác còn thực thi job.
2. Kiểm tra transaction đã commit và dữ liệu nghiệp vụ còn lại.
3. Thực hiện thủ tục recovery metadata phù hợp **phiên bản Spring Batch và chính sách vận hành**, để đưa instance về trạng thái cho phép restart.
4. Sau khi metadata hợp lệ, restart và giám sát execution mới.

Không tự `UPDATE BATCH_JOB_EXECUTION SET STATUS='FAILED'` bằng tay như cách sửa lỗi tổng quát: cần xét version/counter/context, lưu trữ transaction, khả năng process cũ vẫn sống và nhất quán với JobRepository.

**Ghi chú phiên bản:** Spring Batch 6.x bổ sung các API operator khác cho recovery, ví dụ cơ chế `recover` đối với execution kẹt sau crash; mã mẫu trong bài tập trung Spring Batch 5.x và không giả định API 6.x có sẵn ở 5.x.

---

## 13. Mất kết nối ngay trước và ngay sau commit: phân tích ba kịch bản

### Kịch bản A — Rollback xác định

```text
Order 1..100  -> COMMIT
Order 101..200 -> COMMIT
Order 201..300 -> writer exception
transaction rollback xác định
JobExecution -> FAILED
```

Khi DB trở lại, restart từ checkpoint 200; item 201..300 xử lý lại. Nếu writer JDBC cùng transaction và không có side effect khác, đây là tình huống tương đối rõ.

### Kịch bản B — Commit outcome không rõ

```text
Order 201..300 -> DB nhận COMMIT
Network mất đúng lúc server phản hồi
Client nhận connection error
```

Có thể 201..300 đã nằm trong database hoặc chưa. Phải query theo business key để đối soát; writer idempotent giúp an toàn nếu chunk cần replay. Chỉ đọc thông điệp “connection reset” không xác định được kết quả commit.

### Kịch bản C — Business DB commit rồi metadata DB mất

```text
DB B: orders 201..300 COMMITTED
DB A: checkpoint vẫn offset=200
Process chết
```

Khi restart, Batch có thể đọc 201..300 lần nữa. Nếu writer có unique constraint/idempotent upsert, dữ liệu cuối có thể vẫn đúng. Nếu writer append records không có business key hoặc phát side effect ngoài transaction, có thể xảy ra duplicate.

**Bài học:** Không lấy việc Spring Batch hỗ trợ restart làm bằng chứng exactly-once cho mọi hệ thống ngoài. Tính đúng phụ thuộc transaction boundaries, metadata persistence và thiết kế output idempotent.

---

## 14. Ứng xử khi outage dài hơn retry budget

Một cluster có 50 job song song; database failover kéo dài 3 phút. Nếu mỗi item retry dồn dập không backoff, 50 job có thể tạo hàng nghìn connection attempts mỗi giây ngay trong lúc DB khôi phục.

Nên thiết kế nhiều tầng:

```text
Short transient error
    |
    v
Bounded retry + exponential backoff
    |
    +-- Thành công -> tiếp tục chunk
    |
    +-- Hết budget -> step FAILED
                           |
                           v
                  Orchestrator ghi nhận
                           |
                           v
                 DB health + cooldown
                           |
                           v
                    Operator restart
                           |
                           v
                    Reconcile output
```

### 14.1. Vì sao cần exponential backoff?

Giả sử có ba nỗ lực với khoảng chờ 0,5 giây rồi 1 giây (ví dụ). Thay vì retry liên tục, backoff giảm áp lực lên database đang hồi phục.

Trong hệ thống nhiều node, nên cân nhắc **jitter** để không phải tất cả job cùng retry đúng một thời điểm. Nếu dùng một implementation backoff mặc định không có jitter, có thể cấu hình policy khác hoặc orchestration layer để phân tán nỗ lực.

### 14.2. Circuit breaker có thay thế restart không?

Circuit breaker ở client giúp ngừng gửi request đến DB/service hỏng trong một khoảng thời gian. Nhưng nó không tự chuyển `JobExecution FAILED` sang hoàn thành, không khôi phục reader checkpoint và không bảo đảm những item đã ghi không trùng.

Circuit breaker có thể là một phần của **admission control** hoặc xử lý I/O tạm thời; Batch recovery vẫn cần repository, checkpoint và orchestration.

### 14.3. Scheduler cần tránh tạo thêm backlog không kiểm soát

Nếu các batch daily/hourly mới tiếp tục được launch trong lúc DB down, hàng loạt executions có thể `FAILED` và cần restart. Scheduler nên có cơ chế trì hoãn/queue các slot mới hoặc giới hạn số job active dựa trên DB health. Sau khi DB phục hồi, chạy bù theo quota và trạng thái thực tế thay vì đồng thời khởi động mọi slot cũ.

---

## 15. Observability khi mất kết nối database

### 15.1. Các nhóm số liệu cần theo dõi

| Nguồn | Chỉ số/tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Spring Batch | `BatchStatus`, `ExitStatus` | Job/step đã kết thúc hay còn chạy |
| Spring Batch | `readCount`, `writeCount`, `commitCount`, `rollbackCount` | Đã xử lý/rollback bao nhiêu |
| Spring Batch | `ExecutionContext` checkpoint đọc lại qua `JobExplorer` | Mốc restart persisted |
| HikariCP | active/idle/pending connections | Pool có nghẽn hay hết connection |
| JDBC driver | connect timeout, socket timeout, SQLState, query failures | Phân biệt lỗi network/query |
| Database | availability, failover, replication lag, locks, active sessions | Gốc vấn đề hạ tầng |
| Application | retry attempts, backoff duration, failure count | Có xảy ra retry storm không |
| Business output | số unique business keys, checksum, reconciliation gaps | Đã ghi đủ và không trùng chưa |

Ví dụ các tên metric Hikari/Micrometer phổ biến được expose qua Micrometer, nhưng tên chính xác và tag phụ thuộc phiên bản/registry. Kiểm tra thực tế endpoint metrics/Prometheus trước khi thiết kế alert.

### 15.2. Log có context nhưng tránh dữ liệu nhạy cảm

Một log xử lý outage nên có:

```text
event=database_connection_lost
jobName=importOrdersJob
jobExecutionId=3001
stepName=importOrdersStep
batchStatus=FAILED
errorClass=CannotGetJdbcConnectionException
sqlState=08006
retryAttempt=3
metadataCheckpoint=200
databaseRole=business
correlationId=batch-3001
```

Không log username/password, raw connection strings có secrets, nội dung payment card hoặc toàn bộ `ExecutionContext` nếu có dữ liệu nhạy cảm. SQLState/errorClass chỉ minh họa, phải lấy từ exception thực.

### 15.3. Alert theo ảnh hưởng nghiệp vụ

Thay vì chỉ đếm số exception, có thể alert theo:

- Job quan trọng chưa hoàn thành trước deadline.
- Số execution `FAILED` do database trên ngưỡng.
- Hikari pending connections tăng liên tục.
- Database unavailable và thời gian từ lần commit/checkpoint cuối quá lâu.
- Queue/backfill tồn đọng lâu hơn SLA.
- Chênh lệch giữa số source records đã đến hạn và số output business keys đã hoàn thành.

Một lần retry thành công có thể không cần paging on-call; một ngày không có báo cáo dù không có `FAILED` execution lại là sự cố nghiệp vụ thật.

---

## 16. Integration test: mô phỏng transient failure ở writer

Mức test đầu tiên có thể dùng một writer test double ném `TransientDataAccessResourceException` trong vài nỗ lực đầu, sau đó thành công. Test xác minh chính sách retry và kết quả Batch, **chưa phải test mất kết nối JDBC thật**.

### 16.1. Writer giả lập lỗi

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessResourceException;

public class FlakyWriter implements ItemWriter<Integer> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public void write(Chunk<? extends Integer> chunk) {
        int attempt = attempts.incrementAndGet();

        if (attempt <= 2) {
            throw new TransientDataAccessResourceException(
                "Simulated temporary database outage");
        }

        // Fixture: ghi nhận item nếu test cần khẳng định output.
    }

    public int attempts() {
        return attempts.get();
    }
}
```

Writer này không đụng database, nên chỉ dùng để kiểm tra **retry wiring**. Mọi lần gọi phải giữ chunk input có thể xử lý lại; nếu muốn kiểm tra rollback thật cần dùng JDBC transaction và datasource trong test.

### 16.2. Test kỳ vọng

Giả sử step có:

- Reader tạo đúng một chunk item.
- Writer là `FlakyWriter`.
- Fault-tolerant config retry `TransientDataAccessException` với limit 3.
- Backoff nhỏ trong test.
- JobRepository test hoạt động bình thường.

Khi launch:

```java
JobExecution execution =
    jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertEquals(3, flakyWriter.attempts());
```

Hai phép assert này chỉ có ý nghĩa khi fixture được reset, có đúng một writer call logical và test không chạy song song với fixture dùng chung. Thêm assertion output để chắc chắn writer đã thành công đúng một lần theo business contract.

### 16.3. Test hết retry budget

Đổi writer để luôn ném exception, sau đó assert `JobExecution`/`StepExecution` chuyển `FAILED` khi không còn retry. Nếu database metadata cũng bị mất, `JobRepository` có thể không ghi được trạng thái `FAILED`; đó là kịch bản integration test khác, không thể chỉ mô phỏng bằng writer ném exception.

### 16.4. Unit test classification

Tách exception classifier thành component riêng, kiểm tra:

- `TransientDataAccessResourceException` được coi là transient.
- `BadSqlGrammarException` không được retry.
- Commit uncertainty có kết quả `RECONCILE_REQUIRED`, không phải retry mù.
- Lỗi vượt quá retry budget được đưa sang restart/orchestration thay vì vòng lặp vô hạn.

Nếu thực tế dùng driver/vendor error code, chuẩn bị các cause chain `SQLException` có SQLState tương ứng để test classifier theo cùng bối cảnh vận hành.

---

## 17. Integration test mất kết nối thật bằng Testcontainers

### 17.1. Vì sao H2 không đủ?

H2 in-memory hữu ích cho metadata test và transaction semantics cơ bản. Nhưng nó không tái hiện đúng tình huống TCP connection bị reset giữa query hoặc failover PostgreSQL/Oracle:

- Không cùng network driver, socket timeout và connection pool behavior.
- Locking/isolation khác production.
- Không có primary failover, connection termination, proxy latency như môi trường thật.
- Driver exception type/cause chain có thể khác.

Với production PostgreSQL, dùng Testcontainers PostgreSQL; khi cần cắt network một cách có kiểm soát, có thể kết hợp Toxiproxy hoặc cơ chế fault injection tương đương.

### 17.2. Thiết kế test outage

Một fixture đáng tin nên tách metadata database với business database để có thể **cố tình làm business DB mất kết nối nhưng `JobRepository` vẫn lưu được trạng thái failed**:

```text
Spring Batch metadata  -> stable test DB A
Spring Batch writer    -> PostgreSQL Testcontainer B
                              |
                              v
                       network fault proxy
```

Quy trình:

1. Tạo đủ schema, unique constraints và input dữ liệu cố định.
2. Chạy job chunk size 20; đảm bảo ít nhất hai chunk đã commit.
3. Đúng thời điểm đã xác định, cắt kết nối business DB qua proxy hoặc terminate backend connection.
4. Chờ job đi đến trạng thái terminal với timeout rõ ràng; kiểm tra exception thực tế.
5. Qua `JobExplorer`, đọc lại `StepExecution` và `ExecutionContext` đã persisted.
6. Phục hồi network, bảo đảm datasource tạo được connection mới.
7. Nếu `JobExecution FAILED` và restart hợp lệ, restart **cùng identifying `JobParameters` / `JobInstance`**.
8. Assert execution cuối `COMPLETED` và tập business keys đúng, không thiếu/trùng.
9. Nếu cố ý cắt kết nối tại commit, kiểm tra cả hai khả năng commit đã thành công/chưa thành công bằng reconciliation thay vì mặc định một kết quả.

Đây là **thiết kế kiểm thử**, không phải một đoạn Testcontainers độc lập đã tự setup fault proxy. Công cụ network fault injection, mapping container ports và trigger thời điểm cắt cần được hiện thực theo phiên bản Testcontainers/datasource của dự án.

### 17.3. Test mất riêng metadata DB

Ở kịch bản thứ hai, business DB vẫn sống còn metadata JDBC DB bị cắt:

- Test phải quan sát việc tạo/update execution/checkpoint thất bại.
- Sau khi phục hồi, tra lại record metadata thực tế, không tin status trong JVM cũ.
- Đối soát dữ liệu nghiệp vụ đã commit so với checkpoint persisted.
- Xác định thủ tục xử lý stale `STARTED` theo quy trình phiên bản/framework.
- Chỉ sau đó mới restart, và writer phải idempotent khi gặp item đã ghi.

Kịch bản này thường phát hiện lỗi thiết kế khi tách hai datasource rõ hơn test chỉ làm writer ném exception.

### 17.4. Tránh test bằng `Thread.sleep` không kiểm soát

Nếu cắt database “sau 2 giây” nhưng CI chạy chậm hơn hoặc nhanh hơn máy local, sự cố có thể xảy ra trước chunk đầu tiên hoặc sau khi job đã xong. Tốt hơn là fixture báo tín hiệu sau khi commit N chunk, rồi test mới kích hoạt network fault. Dùng latch/event và timeout, không phụ thuộc thời gian wall-clock tuyệt đối.

---

## 18. Ví dụ runbook khi database bị mất kết nối

### Trạng thái ban đầu

```text
Job:          dailyOrderImport
JobInstance:  #87
JobExecution: #4100
Step:         importOrdersStep
Business DB:  PostgreSQL (unavailable)
Metadata DB:  JDBC repository (available)
Step status:  FAILED
Checkpoint:   last committed page/key = 5000
```

### 18.1. Xác định phạm vi

1. Xác nhận database role gặp lỗi: business DB, metadata DB hay cả hai.
2. Kiểm tra kết nối mới từ node ứng dụng; dùng health check phù hợp, không chỉ ping host.
3. Kiểm tra `JobExecution`/`StepExecution` thật từ `JobExplorer`.
4. Thu thập exception class, SQLState, transaction outcome và thời điểm lỗi.
5. Kiểm tra job khác cùng datasource có thất bại hàng loạt không.

### 18.2. Khôi phục hạ tầng và đánh giá ảnh hưởng

1. Phục hồi database/quyền truy cập/network/connection pool.
2. Xác nhận replication lag hoặc failover đã ổn định cho thao tác cần thiết.
3. Xác định checkpoint **đã persist** qua repository.
4. Đối chiếu output nghiệp vụ tương ứng checkpoint, đặc biệt các chunk gần thời điểm mất connection.
5. Kiểm tra unique business keys và side effect bên ngoài.
6. Nếu đã có execution mới đang chạy, không gửi restart trùng.

### 18.3. Restart đúng instance

Nếu execution `4100` là `FAILED`, job có thể restart và đã hoàn tất đối soát:

```java
Long newId = jobOperator.restart(4100L);
```

Ghi lại `newId`, theo dõi `BatchStatus` đến khi terminal. Nếu launcher async, một ID trả về không phải bằng chứng job đã hoàn thành.

Nếu execution còn `STARTED` do crash, xử lý trạng thái theo recovery procedure trước; không ép sửa SQL để restart ngay. Nếu JobInstance đã `COMPLETED`, không restart lần cũ; cần xác định liệu chỉ thiếu cập nhật dashboard/ledger hay có nghiệp vụ mới.

### 18.4. Xác nhận hoàn tất

- `JobExecution` mới thuộc cùng `JobInstance`.
- Trạng thái terminal là `COMPLETED`.
- Các step đã hoàn thành trước đó không chạy lại ngoài chính sách có chủ đích.
- Step bị lỗi khôi phục checkpoint phù hợp.
- Không có duplicate business key; tổng records/amounts/checksum khớp nguồn.
- Các event/API side effect đã được đối soát.
- Scheduler/queue không còn tạo yêu cầu trùng cho cùng business date.
- Lỗi/alert được đóng sau khi kết quả nghiệp vụ xác nhận đúng.

---

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách làm phù hợp |
| --- | --- | --- |
| Retry mọi `Exception` vô hạn | DB downtime tạo retry storm; lỗi SQL cố định không tự khỏi | Classify lỗi, giới hạn attempts và backoff |
| Dùng `skip(DataAccessException.class)` cho outage | Job có thể `COMPLETED` dù mất nhiều item | Fail/restart outage; skip chỉ cho record lỗi được phép |
| Thấy `COMMIT` timeout rồi khẳng định chắc rollback | Server có thể đã commit trước khi response mất | Reconcile business state, idempotent writer |
| Mỗi lần thử lại thêm identifying UUID mới | Tạo `JobInstance` mới, mất checkpoint và gây trùng | Dùng stable job parameters; restart instance cũ |
| Tin `ExecutionContext` trong bộ nhớ đã persist | Repository update có thể thất bại | Đọc lại qua `JobExplorer` |
| Hikari reconnect nên cursor reader tự resume | Cursor cũ có thể invalid | Restart reader từ checkpoint |
| Tự sửa `BATCH_JOB_EXECUTION.STATUS` khi stuck `STARTED` | Metadata/process có thể không nhất quán | Xác minh worker và dùng recovery procedure kiểm soát |
| Giả định business DB và metadata DB luôn atomic | Hai transaction resources có thể commit lệch nhau | Idempotency + reconciliation; kiến trúc giao dịch rõ |
| Chỉ test writer ném exception giả | Không mô phỏng socket reset/ambiguous commit thật | Bổ sung integration test fault injection |
| Không theo dõi connection pool | Không biết lỗi do pool hay server | Theo dõi Hikari active/idle/pending và DB metrics |
| Restart ngay khi DB vừa ping được | Primary failover/replication có thể chưa ổn | Readiness theo thao tác và SLA |
| Chỉ assert `BatchStatus.COMPLETED` | Kết quả nghiệp vụ có thể thiếu/trùng | Assert business output + checkpoint |

---

## 20. Bài thực hành

### Bài 1 — Phân loại lỗi

Một job có reader từ PostgreSQL, processor thuần Java, writer vào PostgreSQL. Lần chạy xuất hiện lần lượt:

1. `CannotGetJdbcConnectionException` khi bắt đầu đọc.
2. `BadSqlGrammarException` sau khi deploy thiếu migration.
3. `DuplicateKeyException` cho một order ID đã tồn tại.
4. Socket timeout khi transaction đang commit.

Hãy giải thích trường hợp nào có thể retry, trường hợp nào phải fail fast, trường hợp nào cần reconciliation và vì sao không dùng một retry rule cho tất cả.

### Bài 2 — Cấu hình fault-tolerant step

Tạo step chunk size 25 với `FlakyWriter` thất bại hai lần đầu bằng `TransientDataAccessResourceException` rồi thành công. Cấu hình retry limit 3 và backoff nhỏ.

Kiểm tra `JobExecution COMPLETED`, writer call count và số business items chỉ được ghi đúng một lần theo fixture. Đổi writer luôn thất bại và xác minh step `FAILED` sau khi hết budget.

### Bài 3 — Mất kết nối sau hai chunk

Cho job nhập 100 item với chunk size 20; sau khi đã commit 40 item, gây outage ở chunk tiếp theo. Dùng `JobExplorer` đọc checkpoint cuối đã persisted. Restart và kiểm tra đủ 100 output items không trùng.

Mở rộng: cố ý gây timeout gần COMMIT, đánh giá hai khả năng transaction đã commit hoặc chưa và xây idempotent writer để cả hai đều cho kết quả đúng.

### Bài 4 — Khác datasource

Tạo metadata DB A và business DB B. Khi writer vào DB B thành công nhưng DB A bị ngắt trước checkpoint, mô phỏng JVM chết.

Yêu cầu: giải thích khả năng job xử lý lại item đã commit, thiết kế bảng unique key và reconciliation để tránh duplicate, rồi khôi phục execution an toàn.

### Bài 5 — Cursor so với paging

Xây `JdbcCursorItemReader` và `JdbcPagingItemReader` cho cùng dataset có sort key ổn định. Gây mất connection giữa lúc đọc, quan sát exception và khả năng phục hồi ở execution mới.

Yêu cầu: nêu giới hạn của việc retry trên cursor đã đóng và vai trò `ItemStream`/`ExecutionContext`.

### Bài 6 — Runbook production

Tình huống: job đối soát tiền đã ghi 70% kết quả, PostgreSQL primary failover, JobRepository còn `STARTED` sau khi container bị kill. Hãy viết quy trình xác nhận worker cũ đã dừng, phục hồi database, đối chiếu các giao dịch đã commit, xử lý trạng thái metadata theo phiên bản rồi restart đúng instance.

Bổ sung metric/alert cần có và cách bảo vệ API hoặc event phát ra ngoài transaction.

---

## 21. Nguyên tắc cốt lõi

Mất kết nối database trong Spring Batch không chỉ là một `SQLException`. Nó có thể ảnh hưởng đồng thời tới **transaction nghiệp vụ**, **checkpoint**, **JobRepository metadata** và **quy trình restart**. Một lần retry an toàn phải dựa trên khả năng khôi phục tài nguyên và tính idempotent của thao tác. Một lần restart an toàn phải dựa trên metadata đã persist và đối soát kết quả thật.

Giữ ba phân biệt sau:

- **Retry**: xử lý một lỗi tạm thời trong cùng logic thực thi với attempts/backoff được giới hạn.
- **Restart**: tạo `JobExecution` mới cho **cùng `JobInstance`** từ trạng thái đã lưu sau khi lỗi được xử lý.
- **Reconciliation**: đối chiếu metadata và dữ liệu nghiệp vụ khi commit/connection outcome không chắc chắn, trước khi quyết định xử lý lại.

Thiết kế tốt không chỉ giúp job chạy lại được, mà còn bảo đảm **không mất dữ liệu và không tạo side effect trùng** khi database mất kết nối đúng lúc khó nhất.

## 22. Tài liệu tham khảo

- [Spring Batch — Configuring a Step / Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk và transaction boundaries.
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault-tolerant retry và recovery.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` và checkpoint.
- [Spring Batch — Job Restart](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobExecution` và restartability.
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobExplorer` và `JobOperator`.
- [Spring Batch — Batch Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): bảng `BATCH_*`.
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html): Spring JDBC exception translation.
- [Spring Boot — Data Access / SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC datasource configuration.
- [HikariCP README](https://github.com/brettwooldridge/HikariCP): connection pool configuration và timeout semantics.
- [Testcontainers — Databases](https://java.testcontainers.org/modules/databases/): integration test với database gần production.
