# Rollback và retry cùng partition trong Spring Batch

Một hệ thống nhập 18 triệu giao dịch chia thành 24 partition để đáp ứng cửa sổ batch. Mỗi worker đọc phần dữ liệu riêng, xử lý các chunk 200 bản ghi rồi ghi vào PostgreSQL. Tới partition `range-0017`, chunk chứa một record gặp deadlock; Spring Batch retry. Sau vài lần retry, partition này báo `FAILED` trong khi 23 partition khác đã `COMPLETED`.

Ba câu hỏi vận hành xuất hiện ngay: **Rollback đã xóa toàn bộ dữ liệu của `range-0017` hay chỉ chunk đang lỗi? Retry có chạy lại những item đã commit không? Khi restart JobInstance, những partition đã hoàn tất có bị chạy lại?** Nếu trả lời sai, đội vận hành có thể xóa dữ liệu hợp lệ, chạy lại cả job hoặc tạo duplicate business effects.

Bài **“Rollback và retry cùng partition”** thuộc chương **Transaction boundary** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu của module là mở rộng Spring Batch cho workload lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực. Trọng tâm bài là **ranh giới rollback của một chunk trong một partition, sự khác nhau giữa retry ngay và restart từ checkpoint, cùng cách bảo toàn kết quả khi nhiều worker chạy đồng thời**.

Các ví dụ nhắm tới Spring Batch 5.2.x, Spring Framework 6.x và Java 17+, với PostgreSQL ở phần SQL minh họa. Các snippet có thể cần bổ sung bean infrastructure và cấu hình Spring Boot của dự án; nơi dùng pseudocode sẽ ghi rõ. Không có quy tắc rằng Spring Batch mặc nhiên đem lại exactly-once đối với mọi resource.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **item**, **chunk**, **transaction**, **partition**, **worker StepExecution**, **JobExecution** và **JobInstance**.
2. Giải thích rollback thường chỉ hoàn tác những cập nhật **chưa commit trong transaction chunk hiện tại**, không xóa các chunk trước đã commit.
3. Hiểu retry một lỗi transient **trong StepExecution đang chạy** khác restart một partition **ở JobExecution sau**.
4. Thiết kế `FaultTolerantStepBuilder` với `retry`, `retryLimit`, `skip`, `skipLimit` và backoff có giới hạn.
5. Phân loại lỗi nên retry, nên skip và nên fail thay vì retry vô hạn.
6. Giữ `Partitioner`, `ExecutionContext` và reader checkpoint ổn định để phục hồi partition lỗi mà không xử lý lại các partition đã `COMPLETED` theo mặc định.
7. Thiết kế JDBC writer idempotent trước replay do crash/rollback và nhận diện side effects ngoài transaction.
8. Phân tích remote partitioning, message redelivery và tình huống worker cũ còn chạy.
9. Thực hiện fault-injection tests tại các điểm trước commit, sau commit, mất response và mất JobRepository metadata.
10. Đo retry/rollback, committed throughput, DB locks và SLA để chọn giới hạn tài nguyên phù hợp.

## 2. Bản đồ ranh giới: rollback là của transaction, không phải của partition

Một partitioned step tạo một **manager StepExecution** và nhiều **worker StepExecution**. Mỗi worker thông thường xử lý một loạt chunk và mỗi chunk có transaction riêng.

~~~mermaid
flowchart TD
    J["JobInstance: import(snapshot=v42)"] --> M["Manager PartitionStep"]
    M --> P0["worker:range-0000"]
    M --> P1["worker:range-0001"]
    M --> P2["worker:range-0002"]
    P1 --> C1["Chunk #1 → COMMIT"]
    P1 --> C2["Chunk #2 → COMMIT"]
    P1 --> C3["Chunk #3 → ROLLBACK"]
    C3 --> RT["Retry theo fault tolerance policy"]
    RT --> OK{"Retry thành công?"}
    OK -->|Có| C4["Commit chunk và tiếp tục"]
    OK -->|Không| F["Worker StepExecution FAILED"]
~~~

**Không có một transaction JDBC bao trùm toàn bộ partition** trong cấu hình chunk-oriented step tiêu chuẩn. Nếu partition đã commit 50 chunk, rồi chunk thứ 51 rollback thì 50 chunk đầu **vẫn tồn tại trong database**. Framework không rollback 50 chunk đã commit chỉ vì status cuối của partition là `FAILED`.

### 2.1. Năm tầng trạng thái không được lẫn

| Tầng | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| Item | `event_id=10057` | Có thể được xử lý lại khi chunk rollback hoặc restart |
| Chunk | 200 items/lần xử lý | Thường có một transaction/commit boundary; fault tolerance có thể replay nhiều lượt |
| Worker partition | `worker:range-0017` | Một `StepExecution` với context, counters, checkpoint và status riêng |
| Manager step | `importManager` | Điều phối split, handler và tổng hợp worker results |
| Job | `importJob(snapshot=v42)` | Một JobInstance có thể có nhiều JobExecutions khi restart |

**Rollback** thuộc phạm vi resource transaction. **Retry** là quyết định thử lại một operation hoặc item/chunk sau lỗi có thể hồi phục. **Restart** là khởi động JobExecution mới trên **cùng JobInstance**, sử dụng lịch sử trong JobRepository và checkpoint.

### 2.2. Một câu ngắn để tránh nhầm

> *“Rollback không có nghĩa undo mọi chunk đã commit; retry không có nghĩa tạo JobExecution mới; restart không có nghĩa tạo JobInstance mới.”*

Đây là ba hành động ở ba ranh giới khác nhau. Chúng có thể xảy ra liên tiếp trong một sự cố, nhưng không thay thế nhau.

## 3. Chu kỳ xử lý chunk và vị trí của transaction

Ví dụ worker step:

~~~java
@Bean
public Step eventWorkerStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<SourceEvent> reader,
        ItemProcessor<SourceEvent, SourceEvent> processor,
        ItemWriter<SourceEvent> writer) {

    return new StepBuilder("eventWorker", repository)
            .<SourceEvent, SourceEvent>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong chunk-oriented step tiêu chuẩn, một vòng chunk được xử lý dưới transaction do `PlatformTransactionManager` của Step điều phối. Framework phối hợp `ItemStream`, `ExecutionContext` và metadata trước commit theo cơ chế của `TaskletStep`.

~~~mermaid
sequenceDiagram
    participant S as Worker Step
    participant T as Transaction Manager
    participant R as ItemReader / Processor
    participant W as ItemWriter
    participant D as Business Database
    participant J as JobRepository
    S->>T: BEGIN chunk transaction
    loop Đọc và xử lý tới chunk size
        S->>R: read() / process()
    end
    S->>W: write(Chunk)
    W->>D: INSERT / UPDATE
    S->>J: Update ExecutionContext / StepExecution
    S->>T: COMMIT
    Note over S,D: Nếu write/commit lỗi, rollback phần chưa commit
~~~

Sơ đồ thể hiện **luồng logic phổ biến**, không cam kết thứ tự chính xác mọi callback hoặc khả năng atomic giữa hai datasource. Nếu JobRepository và business DB dùng **hai local transaction managers khác nhau**, checkpoint và business write không tự commit như một giao dịch.

### 3.1. Giải thích với 1.250 records

Giả định một partition đọc 1.250 records theo ID tăng dần, `chunk(100)` và writer trên một JDBC datasource transactional.

| Chunk | ID dự kiến | Lượt đầu | Hậu quả |
| --- | --- | --- | --- |
| 1–10 | 1–1.000 | `COMMIT` | 1.000 bản ghi đã được ghi bền |
| 11 | 1.001–1.100 | `ROLLBACK` vì deadlock | Chưa commit thay đổi của chunk 11 |
| 11 retry | Cùng công việc chưa hoàn tất | `COMMIT` nếu retry thành công | Ghi chunk, tiếp tục |
| 12–13 | 1.101–1.250 | `COMMIT` nếu không lỗi | Kết thúc partition |

Nếu retry chunk 11 cuối cùng thất bại, partition có thể `FAILED` dù dữ liệu 1–1.000 **đã commit**. Trong một lần restart an toàn, reader sử dụng checkpoint của các chunk đã commit và tiếp tục phần còn lại. ID chính xác được đọc lại còn tùy reader implementation, snapshot, checkpoint, transaction boundary và replay; không suy từ `readCount` một cách máy móc.

### 3.2. Phải phân biệt transaction manager với datasource

Rollback chỉ bảo vệ các SQL/side effects thực sự tham gia transaction của `transactionManager` đã truyền vào worker Step. Nếu writer dùng datasource B nhưng chunk manager là của datasource A, dữ liệu ở B có thể auto-commit hoặc nằm trong transaction khác. Lúc đó “Spring Batch đã rollback chunk” **không đồng nghĩa output B đã rollback**.

Với JDBC, bảo đảm reader/writer/`JdbcTemplate` và manager dùng resource factory đúng. Với JPA, chọn `JpaTransactionManager` của đúng `EntityManagerFactory`. Nếu JobRepository tách datasource, phải thử failure window giữa checkpoint và business commit.

## 4. Retry **cùng partition đang chạy** khác restart partition sau lỗi

Spring Batch cung cấp hai tầng phục hồi.

### 4.1. Retry trong một StepExecution

Một worker partition đang chạy và gặp exception được phân loại retryable. Fault-tolerant chunk step có thể thử lại operation/item theo policy mà **không tạo JobExecution mới**. Retry state, số lần thử và chi tiết reprocessing phụ thuộc giai đoạn lỗi (read/process/write), retry policy và rollback behavior.

~~~text
JobExecution #510
  worker:range-0017
    chunk X -> attempt 1 -> transient DB error -> rollback
            -> attempt tiếp theo -> success -> COMMIT
    worker vẫn RUNNING/hoàn tất bình thường
~~~

Lợi ích: lỗi ngắn như deadlock, lock timeout hoặc network glitch thoáng qua có thể được giải quyết trong cùng execution.

### 4.2. Restart StepExecution của partition ở JobExecution mới

Khi retry đã hết giới hạn hoặc lỗi không retryable, worker `FAILED`. Manager có thể báo fail và JobExecution cũng không hoàn tất. Sau khi vận hành xác nhận nguồn/tác dụng phụ, có thể **restart cùng JobInstance** để framework kiểm tra metadata các partition.

~~~text
JobInstance: import(snapshot=v42)

JobExecution #510
    worker:range-0000  COMPLETED
    worker:range-0001  COMPLETED
    worker:range-0017  FAILED
    worker:range-0023  COMPLETED
    manager            FAILED
    job                FAILED

JobExecution #511 (restart cùng JobInstance)
    worker:range-0017  được phục hồi từ ExecutionContext cũ
    các partition COMPLETED trước đó không chạy lại theo mặc định
    manager/job COMPLETED nếu recovery thành công
~~~

Các StepExecutions sau restart có **identity/ID và lịch sử thực thi mới**, nhưng giữ tên partition logic và context đã lưu để đối chiếu. `SimpleStepExecutionSplitter` quyết định partition cần thực thi theo trạng thái JobRepository và chính sách restart.

### 4.3. Retry budget có giữ nguyên giữa hai JobExecutions không?

**Không được coi số lần retry in-memory là global durable counter**. Một retry policy trong worker StepExecution thường quản lý attempts của lần thực thi hiện tại; khi tạo StepExecution mới sau restart, retry context có thể được dựng mới. Nếu một record độc hại luôn tạo transient exception, job có thể tiếp tục tốn công qua nhiều lần restart dù mỗi lần có `retryLimit(3)`.

Production cần **giới hạn số lần thử bền vững theo business key/partition** nếu nghiệp vụ yêu cầu trần toàn vòng đời, có failure classification và cơ chế quarantine/manual review thay vì restart vô hạn.

### 4.4. Bảng so sánh

| Thuộc tính | Retry ngay trong worker | Restart cùng JobInstance |
| --- | --- | --- |
| Trigger | Exception retryable trong read/process/write | JobExecution/StepExecution đã failed/stopped, đủ điều kiện restart |
| Phạm vi | Operation/item/chunk theo retry policy | Worker partition chưa hoàn tất theo repository |
| JobExecution mới? | Không | Có |
| Sử dụng checkpoint | Rollback/retry state nội bộ + ItemStream | Lấy context đã persist từ lần trước |
| Partition `COMPLETED` khác | Vẫn làm việc độc lập | Không chạy lại theo mặc định |
| Khi nguồn input thay đổi | Có nguy cơ re-read khác | Nguy cơ nghiêm trọng cho restart/cursor |
| External side effect | Cần idempotency | Vẫn cần idempotency |
| Retry budget | Thường cục bộ theo policy/lần chạy | Cần chính sách bền vững nếu giới hạn liên execution |

## 5. Những loại lỗi nên retry, skip hoặc fail

Không có một classification áp dụng cho mọi job. Chính sách phải dựa trên **khả năng hồi phục và tác động nghiệp vụ**, không chỉ tên exception.

| Lỗi | Chính sách khởi đầu | Lý do |
| --- | --- | --- |
| Database deadlock / lock contention ngắn | Retry hữu hạn với backoff/jitter | Có thể thành công khi xung đột qua đi |
| Network timeout khi đọc dữ liệu versioned | Retry hữu hạn nếu call có deadline | Có thể là lỗi transient |
| HTTP 429/503 | Retry sau Retry-After/backoff nếu quota cho phép | Tránh retry storm |
| Constraint unique khi replay cùng business key/version | Xử lý idempotent ở writer hoặc phân loại duplicate hợp lệ | Không nên biến retry bình thường thành fail |
| Thiếu field bắt buộc ở record không thể sửa | Skip/quarantine nếu policy chấp nhận, nếu không fail | Retry không thay đổi record |
| SQL syntax error/schema mismatch | Fail nhanh | Cần sửa code/migration, retry không giúp |
| Authentication/authorization sai | Fail và báo vận hành | Thường là vấn đề cấu hình/chính sách |
| Dữ liệu snapshot bị thay đổi checksum | Fail closed | Restart tiếp có thể sai output |
| Disk full, DB unavailable kéo dài | Retry hữu hạn rồi fail để hồi phục hạ tầng | Retry vô hạn tăng áp lực |
| POST tạo charge/email đã thực thi nhưng mất response | Không retry mù; dùng idempotency key/tra trạng thái | Phía ngoài DB transaction có thể đã thành công |
| Business rule violation nhất quán | Fail hoặc skip có audit | Không coi là lỗi transient |

**Skip không đồng nghĩa “bỏ qua không sao”.** Với dữ liệu tài chính/đối soát, bỏ một record có thể vi phạm invariant và cần fail cả job. Nếu cho phép skip, phải có giới hạn, log/audit và downstream reconciliation rõ ràng.

## 6. Cấu hình retry/skip bằng FaultTolerantStepBuilder

Ví dụ thiết kế cho lỗi DB tạm thời và một loại record nghiệp vụ có thể đưa vào hàng cách ly:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importWorkerStep(
        JobRepository repository,
        @Qualifier("businessTxManager") PlatformTransactionManager tx,
        ItemReader<ImportEvent> reader,
        ItemWriter<ImportEvent> writer) {

    ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
    backoff.setInitialInterval(200L);
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(2_000L);

    return new StepBuilder("importWorker", repository)
            .<ImportEvent, ImportEvent>chunk(200, tx)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .backOffPolicy(backoff)
            .skip(RecoverableRecordException.class)
            .skipLimit(10)
            .build();
}
~~~

`ImportEvent` và `RecoverableRecordException` là kiểu ứng dụng tự định nghĩa; phần import `@Bean`, `@Qualifier` và hạ tầng Batch cần bổ sung. Nếu không có chính sách cho phép bỏ record, **bỏ toàn bộ `skip(...)`/`skipLimit(...)`** và fail khi lỗi dữ liệu.

### 6.1. Những điều quan trọng về retryLimit

- `retryLimit(3)` cấu hình giới hạn nỗ lực theo retry policy của builder. Không tự tuyên bố đây là đúng ba lần **gọi lại** sau thất bại cho mọi giai đoạn; hãy kiểm tra semantics theo Spring Batch 5.2 và bằng integration test.
- Retry thuộc Step, không có nghĩa retry tất cả StepExecutions/partitions đã hoàn thành.
- Độ rộng của exception type quan trọng: `TransientDataAccessException` là một **họ exception**, có thể gồm nhiều tình huống; production nên thu hẹp theo failure modes đã chứng minh an toàn.
- Backoff tăng dần giảm khả năng các worker retry cùng lúc, nhưng không chữa DB đang quá tải kéo dài.
- `skipLimit(10)` là chính sách skip của **worker step** trong ví dụ; nếu có 24 partitions, không tự suy ra toàn Job có trần skip bằng 10 khi mỗi worker có StepExecution riêng.
- Các `RetryListener`/`SkipListener` có thể ghi metric/audit, nhưng phải hiểu thời điểm callback và commit để không nhân đôi tác dụng phụ.

### 6.2. Retry ở read/process/write không hoàn toàn giống nhau

| Giai đoạn lỗi | Hệ quả điển hình | Cần kiểm chứng |
| --- | --- | --- |
| `read()` lỗi transient | Reader có thể được gọi lại, tùy retry policy | Reader state/cursor còn hợp lệ? |
| `process(item)` lỗi retryable | Item có thể được xử lý lại | Processor có stateless/idempotent không? |
| `write(Chunk)` lỗi | Chunk transaction thường rollback, writer có thể được gọi lại | Có side effect ngoài transaction trước khi lỗi không? |
| Commit/connection bị mất khi chưa biết kết quả | Không chắc server đã commit hay chưa | Business idempotency key và reconciliation |
| Skip sau retry exhaustion | Có thể bỏ item theo chính sách và tiếp tục | Audit, skip count, không được làm mất nghĩa vụ nghiệp vụ |

Với lỗi writer, framework có thể **replay chunk và tách xử lý để tìm item lỗi** trong recovery/skip path. Không giả định mỗi item chỉ được gọi `process()` hoặc `write()` một lần. Với reader `ItemStream` stateful, checkpoint và ordering cần test trên dữ liệu thực.

### 6.3. Cẩn trọng với noRollback()

Spring Batch có cấu hình phân loại lỗi **không yêu cầu rollback** trong một số trường hợp, nhưng lạm dụng `noRollback(...)` cho lỗi writer có thể tạo partial writes và mất nhất quán. Tài liệu Spring Batch nhấn mạnh rollback thường cần thiết khi writer thất bại; chỉ thay đổi chính sách nếu đã chứng minh reader/writer/transaction semantics và có test hồi phục đầy đủ.

**Không cố dùng `noRollback` để che một lỗi deadlock**: database đã abort transaction thì Step phải xử lý lại trong transaction mới, không “giữ commit” của transaction đã lỗi.

## 7. Rollback thực sự làm gì ở worker transaction?

Một transaction JDBC bao một chunk có thể chứa nhiều SQL statements. Nếu writer làm:

~~~sql
BEGIN;

INSERT INTO normalized_event(event_id, source_version, amount)
VALUES (1001, 1, 20.00);

INSERT INTO normalized_event(event_id, source_version, amount)
VALUES (1002, 1, 30.00);

-- Sau đó lỗi deadlock/constraint (chưa COMMIT)

ROLLBACK;
~~~

Nếu cả hai insert **đều thực sự tham gia cùng JDBC transaction**, rollback loại bỏ cả hai cập nhật của chunk. Nhưng:

- Các chunk đã commit trước đó không bị undo.
- Một email/HTTP request đã gửi không bị rollback cùng SQL.
- SQL dùng datasource khác có thể đã commit riêng.
- File append/object upload đã thành công không tự quay ngược.
- Kafka/Rabbit publish/ACK có transaction/confirm riêng.
- Các update metadata `JobRepository` dùng DB khác có thể có timeline commit độc lập.

### 7.1. Transaction và business effect là hai phạm vi

~~~mermaid
flowchart LR
    B["Chunk TX trong worker"] --> D[("Business JDBC DB")]
    B --> J["JobRepository metadata"]
    B --> API["HTTP / Broker / File"]
    D --> R["Rollback được nếu cùng DB TX"]
    J --> Q["Chỉ atomic nếu cấu hình cùng transaction"]
    API --> N["Không tự rollback theo JDBC"]
~~~

Trong mọi ví dụ, **transaction manager của Step phải khớp resource writer**. Một `PlatformTransactionManager` không thể rollback “mọi thứ mà code Java chạm vào”.

### 7.2. Đừng giữ transaction qua network call

Giả sử một chunk xử lý 200 items, mỗi item gọi API mất 100 ms, và các calls tuần tự. Chỉ thời gian chờ đã khoảng 20 giây/chunk. Với 16 workers, transaction có thể giữ connection/locks lâu, gây Hikari pending và DB deadlock tăng, từ đó làm phát sinh **nhiều retry hơn**.

Tách network enrichment thành bước không giữ outer DB transaction (durable claim → API call → persist response) rồi cho Batch xử lý immutable snapshot bằng chunk transaction ngắn. Với API tạo side effect, cần stable idempotency key và outbox/inbox.

## 8. Tại sao lỗi cùng một partition không rollback các partition khác?

Trong partitioned step chuẩn, mỗi worker có `StepExecution` riêng. Worker A rollback chunk không trực tiếp rollback transaction mà worker B đã commit.

~~~text
Manager Step: importManager
  Worker P0: chunk #1 COMMITTED, chunk #2 COMMITTED → COMPLETED
  Worker P1: chunk #1 COMMITTED, chunk #2 FAILED    → FAILED
  Worker P2: chunk #1 COMMITTED, chunk #2 COMMITTED → COMPLETED

=> Không có global transaction gộp cả P0+P1+P2.
=> P0/P2 output vẫn tồn tại khi manager/job thất bại.
~~~

Manager có thể báo `FAILED` khi một worker `FAILED`, nhưng trạng thái aggregate **không tạo hiệu ứng JDBC rollback ngược thời gian** cho các partition đã hoàn tất.

### 8.1. Partition key và ExecutionContext

~~~text
worker:range-0000
  snapshotId = v42
  minInclusive = 1
  maxExclusive = 100001

worker:range-0001
  snapshotId = v42
  minInclusive = 100001
  maxExclusive = 200001
~~~

Framework lưu các contexts trong JobRepository và dùng tên partition để đối chiếu khi restart. Phạm vi logic phải **không chồng lấn và bất biến**. Một lỗi retry ở P1 không cho phép sửa P1 thành range rộng hơn rồi chạy lại trên cùng JobInstance.

### 8.2. PartitionNameProvider khi restart

Nếu `Partitioner` triển khai `PartitionNameProvider`, `getPartitionNames(gridSize)` cho phép splitter lấy **tên các partition của plan cũ** mà không tính lại map context đầy đủ. Interface không chọn riêng partition FAILED; splitter dùng trạng thái repository để làm việc đó.

**Tập tên phải khớp tên của lần phân hoạch ban đầu.** Không tạo UUID mới, không thay số partitions theo số pod khi restart, và không sử dụng danh sách file “latest” thay cho snapshot ban đầu.

## 9. Nền tảng cho ví dụ: immutable snapshot và output idempotent

Ví dụ một snapshot nguồn bất biến và bảng kết quả PostgreSQL:

~~~sql
CREATE TABLE event_snapshot (
    snapshot_id VARCHAR(100) NOT NULL,
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (snapshot_id, event_id)
);

CREATE TABLE normalized_event (
    event_id BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    amount NUMERIC(18,2) NOT NULL
);
~~~

Hợp đồng:

- Mọi worker đọc **cùng `snapshot_id`** đã được chốt, không đọc bảng nguồn sống thay đổi trong lúc retry/restart.
- `event_id` là định danh nghiệp vụ duy nhất trong ví dụ; nếu multi-tenant, key phải chứa `tenant_id`.
- `source_version` tăng đơn điệu theo business semantics đã xác nhận.
- Partition theo ID range nửa mở `[minInclusive,maxExclusive)`.
- Writer không tạo duplicate cho cùng `event_id/source_version`; version cũ không được ghi đè version mới.

### 9.1. Vì sao snapshot bất biến quan trọng?

Một reader cursor có thể checkpoint theo số item đã đọc. Nếu source rows bị insert/delete giữa hai JobExecutions, cùng vị trí checkpoint có thể trỏ vào record khác. Hai ranges vẫn không chồng lấn số học, nhưng restart có thể **bỏ sót hoặc đọc lại** item.

Một snapshot vật lý, versioned file manifest hoặc database CDC/cutoff có semantics rõ ràng là tiền đề. Chỉ thêm `WHERE updated_at <= cutoff` chưa đủ nếu rows có thể thay đổi/hồi tố sau cutoff.

### 9.2. SQL writer chống replay

~~~sql
INSERT INTO normalized_event(event_id, source_version, amount)
VALUES (:eventId, :sourceVersion, :amount)
ON CONFLICT (event_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    amount = EXCLUDED.amount
WHERE normalized_event.source_version < EXCLUDED.source_version;
~~~

Nếu cùng ID/version được replay, command có thể affect **0 rows**; đó là hành vi hợp lệ khi dữ liệu đã có. Nếu cùng version nhưng payload khác, cần **phát hiện conflict** và fail/quarantine, không coi `ON CONFLICT` đã xác nhận dữ liệu giống nhau.

## 10. Ví dụ reader theo partition và checkpoint

Worker có thể dùng `JdbcCursorItemReader` dưới `@StepScope` để đọc phạm vi cố định của từng partition:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record ImportEvent(
        long eventId, long sourceVersion, java.math.BigDecimal amount) {}

@Bean
@StepScope
public JdbcCursorItemReader<ImportEvent> eventReader(
        DataSource dataSource,
        @Value("#{jobParameters['snapshotId']}") String snapshotId,
        @Value("#{stepExecutionContext['minInclusive']}") Long minInclusive,
        @Value("#{stepExecutionContext['maxExclusive']}") Long maxExclusive) {

    return new JdbcCursorItemReaderBuilder<ImportEvent>()
            .name("eventReader")
            .dataSource(dataSource)
            .sql("""
                SELECT event_id, source_version, amount
                FROM event_snapshot
                WHERE snapshot_id = ?
                  AND event_id >= ?
                  AND event_id < ?
                ORDER BY event_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, snapshotId);
                ps.setLong(2, minInclusive);
                ps.setLong(3, maxExclusive);
            })
            .rowMapper((rs, rowNum) -> new ImportEvent(
                    rs.getLong("event_id"),
                    rs.getLong("source_version"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

`ImportEvent` là record minh họa, dùng Java 17; block chứa declaration record và bean method nhằm giải thích cách cấu hình, không phải một file Java tự biên dịch độc lập. Bean reader được tạo theo **worker StepExecution** nhờ `@StepScope`.

Đặc biệt:

- `minInclusive` và `maxExclusive` bảo đảm một partition không đọc sang vùng khác.
- `ORDER BY event_id` và khóa nguồn duy nhất bảo đảm thứ tự xác định cho restart của reader.
- `saveState(true)` cho phép `ItemStream` lưu state, với điều kiện lifecycle được Spring Batch quản lý đúng.
- `snapshotId` phải là identifying context của JobInstance và snapshot thực sự bất biến.
- `JdbcCursorItemReader` có tài nguyên cursor/connection của riêng reader; tránh chia sẻ cùng reader giữa nhiều chunk threads trong **multi-threaded step**.
- Với local partitioning, worker StepExecution riêng thường giúp tách state; singleton processor/writer mutable vẫn cần thread safety.

### 10.1. Reader rollback behavior không nhất thiết giống queue reader

JDBC cursor, file reader và transactional queue reader có semantics khác nhau khi transaction rollback. Một queue reader có thể trả message về broker/session để redeliver; một file reader thường phải dùng checkpoint/điều khiển state nội bộ; một JDBC cursor reader có thể có connection/cursor riêng.

Không tự kết luận rollback SQL luôn **rewind** mọi reader giống nhau. Phải chạy test fail giữa chunk, rollback, retry và restart với **reader implementation thật**, đúng nguồn và driver.

## 11. Writer dùng cùng business transaction và giữ replay idempotent

Ví dụ `JdbcBatchItemWriter` để thực thi upsert trong chunk transaction:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.context.annotation.Bean;

@Bean
public JdbcBatchItemWriter<ImportEvent> eventWriter(
        DataSource businessDataSource) {

    return new JdbcBatchItemWriterBuilder<ImportEvent>()
            .dataSource(businessDataSource)
            .sql("""
                INSERT INTO normalized_event(event_id, source_version, amount)
                VALUES (:eventId, :sourceVersion, :amount)
                ON CONFLICT (event_id)
                DO UPDATE SET
                    source_version = EXCLUDED.source_version,
                    amount = EXCLUDED.amount
                WHERE normalized_event.source_version
                      < EXCLUDED.source_version
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                        .addValue("eventId", item.eventId())
                        .addValue("sourceVersion", item.sourceVersion())
                        .addValue("amount", item.amount()))
            .assertUpdates(false)
            .build();
}
~~~

**Vì sao `assertUpdates(false)`?** Một upsert idempotent có điều kiện có thể update 0 rows khi record same/older version đã được ghi. Nếu writer mặc định đòi mỗi item affect ít nhất một row, một replay hợp lệ có thể bị báo lỗi không cần thiết.

Điều quan trọng hơn:

- Writer dùng **đúng `DataSource`** do `businessTxManager` của Step quản lý.
- Nếu worker crash sau DB commit nhưng trước khi metadata được xác nhận, replay cùng business key/version không làm tăng số rows hoặc ghi đè bản mới hơn.
- Nếu writer gọi thêm external API/queue ngoài JDBC transaction, upsert không bảo vệ external side effect.
- Nếu business yêu cầu “cộng tiền” hoặc “trừ tồn kho”, không chỉ upsert kết quả rồi coi tác dụng cộng/trừ là idempotent. Cần ledger/event ID duy nhất hoặc phép cập nhật có điều kiện được thiết kế riêng.
- Nếu writer cạnh tranh với online traffic, kiểm tra lock ordering, isolation và version conflict.


## 12. Manager Step và partition plan phải ổn định

Để retry/restart đúng **cùng partition**, cần giữ identity và phạm vi mỗi partition qua các lần chạy. Một `Partitioner` có thể đọc danh sách khoảng đã chốt từ manifest, không tính lại theo giá trị `MAX(id)` hiện tại.

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.partition.support.PartitionNameProvider;
import org.springframework.batch.item.ExecutionContext;

record RangeSpec(
        String key, long minInclusive, long maxExclusive) {}

interface RangePlanStore {
    // Đọc immutable manifest ứng với JobInstance snapshot này.
    List<RangeSpec> rangesFor(String snapshotId);
    List<String> partitionNamesFor(String snapshotId);
}

public final class SnapshotRangePartitioner
        implements Partitioner, PartitionNameProvider {

    private final RangePlanStore store;
    private final String snapshotId;

    public SnapshotRangePartitioner(
            RangePlanStore store, String snapshotId) {
        this.store = store;
        this.snapshotId = snapshotId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (RangeSpec range : store.rangesFor(snapshotId)) {
            if (range.key() == null || range.key().isBlank()
                    || range.minInclusive() >= range.maxExclusive()) {
                throw new IllegalStateException("Invalid range");
            }

            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("snapshotId", snapshotId);
            ctx.putLong("minInclusive", range.minInclusive());
            ctx.putLong("maxExclusive", range.maxExclusive());

            if (result.putIfAbsent(range.key(), ctx) != null) {
                throw new IllegalStateException(
                        "Duplicate partition key: " + range.key());
            }
        }

        if (result.isEmpty()) {
            throw new IllegalStateException("No partition plan");
        }
        return result;
    }

    @Override
    public Collection<String> getPartitionNames(int gridSize) {
        return List.copyOf(store.partitionNamesFor(snapshotId));
    }
}
~~~

Đây là ví dụ triển khai interface Spring Batch 5.2. Production phải kiểm tra **coverage/disjointness** của toàn bộ ranges, key nonblank/unique, và sự bằng nhau giữa `partition(...).keySet()` với `getPartitionNames(...)`. Hai phương thức phải dựa trên **cùng một manifest bất biến**, không phải query trên nguồn đang thay đổi.

### 12.1. Bean scope để lấy snapshot đúng

~~~java
@Bean
@StepScope
public SnapshotRangePartitioner snapshotRangePartitioner(
        RangePlanStore store,
        @Value("#{jobParameters['snapshotId']}") String snapshotId) {
    return new SnapshotRangePartitioner(store, snapshotId);
}
~~~

`@StepScope` giúp lấy `snapshotId` từ JobParameters tại thời điểm manager step thực thi. Không lưu một biến singleton mutable `currentSnapshotId` để nhiều JobExecutions chạy đồng thời ghi đè lên nhau.

### 12.2. Local partitioning manager

~~~java
@Bean
public Step importManagerStep(
        JobRepository repository,
        SnapshotRangePartitioner partitioner,
        @Qualifier("importWorkerStep") Step workerStep,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    return new StepBuilder("importManager", repository)
            .partitioner("importWorker", partitioner)
            .step(workerStep)
            .gridSize(24)
            .taskExecutor(executor)
            .build();
}
~~~

Các imports `StepBuilder`, `Step`, `JobRepository`, `TaskExecutor` và annotations được lược bỏ ở block này; `importWorker` phải là **tên Step** khớp cấu hình worker. Ví dụ tạo local partitioning, không phải remote message handler. Số partition từ manifest có thể khác 24; `gridSize` chỉ là hint cho partitioner và không đồng nghĩa có 24 threads.

**Khi restart:** giữ key `importWorker:range-0017` và context chứa phạm vi cũ. Tăng số worker threads/pods có thể thay đổi **năng lực thực thi**, nhưng không được tự chia lại snapshot theo concurrency mới.

## 13. Trạng thái và dấu hiệu hoàn tất ở cấp partition

Một partition có thể có nhiều lần chạy lịch sử trong cùng JobInstance. Những thông tin quan trọng:

- `BatchStatus`: `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPING`, `STOPPED`, `UNKNOWN`.
- `ExitStatus`: kết quả nghiệp vụ/điều kiện flow, có thể khác `BatchStatus`.
- `StepExecution`: ID, tên, read/write/commit/rollback counters, timestamps và exceptions.
- `ExecutionContext`: checkpoint và thông tin partition ban đầu.
- `JobExecution`: lần chạy cụ thể, không phải JobInstance.

### 13.1. FAILED không có nghĩa “đầu vào chưa từng được xử lý”

~~~text
JobExecution #900
  importWorker:range-0017
    chunk 001 ... 050  COMMITTED
    chunk 051          FAILED, transaction rolled back
    StepExecution      FAILED
    Manager            FAILED
    Job                FAILED
~~~

Dữ liệu của 50 chunk đầu **vẫn có thể tồn tại** trong bảng output. Nếu xóa toàn bộ output của partition rồi restart dựa trên checkpoint đã tiến qua chunk 50, có nguy cơ **mất dữ liệu** vì reader không đọc lại phần đã hoàn tất.

Ngược lại, nếu tạo JobInstance mới để xử lý lại toàn bộ mà writer không idempotent, các chunk 1–50 có thể ghi trùng. Vì thế runbook không được đơn giản “DELETE rồi restart”.

### 13.2. COMPLETED không nên chạy lại tùy tiện

Spring Batch mặc định tránh chạy lại partition đã `COMPLETED` khi restart theo metadata. Tuy nhiên, thay đổi chính sách như `allowStartIfComplete(true)`, đổi step names, đổi identifying JobParameters hoặc tự viết splitter có thể làm work được thực thi lại.

Một JobInstance mới không có lịch sử đã hoàn tất của instance trước để bỏ qua các partitions cũ.

### 13.3. STOPPED/UNKNOWN cần điều tra liveness

Khi stop được điều phối bình thường, metadata có thể cho biết `STOPPED`. Khi JVM mất điện hoặc remote worker còn chạy, có thể còn `STARTED` không phản ánh đúng thực tế hoặc `UNKNOWN`. **Không ép metadata sang FAILED/COMPLETED bằng SQL** nếu chưa xác định worker có còn đang ghi hay không.

Một worker cũ đang chạy và một worker mới cùng viết một range có thể gây duplicate/concurrent updates dù partition plan ban đầu không chồng lấn.

## 14. Local, remote và retry request cùng partition

### 14.1. Local partitioning

Trong local partitioning, manager dùng `TaskExecutorPartitionHandler` để chạy nhiều worker StepExecutions trong cùng JVM. Retry trong một worker ảnh hưởng transaction của worker đó; không rollback chunk đã commit ở worker khác.

Các rủi ro chính:

- Reader/processor/writer singleton mutable gây data race.
- Connection pool bão hòa khi quá nhiều worker đồng thời.
- Một partition lỗi liên tục chiếm worker thread, backlog tăng.
- Manager kết thúc lỗi nhưng các partition khác có dữ liệu đã commit.
- Thay partition keys giữa hai lần chạy phá mapping checkpoint.

### 14.2. Remote partitioning

Trong remote partitioning, manager gửi yêu cầu thực thi partition tới worker JVM qua middleware. Worker thường đọc/ghi shard của mình và dùng `JobRepository` tương thích/chia sẻ theo kiến trúc.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Middleware
    participant W as Remote Worker
    participant D as Business DB
    participant R as JobRepository
    M->>Q: StepExecutionRequest(range-0017)
    Q->>W: Deliver request
    W->>R: Load worker StepExecution/context
    W->>D: Chunk transactions / retry
    D-->>W: COMMIT chunk
    W->>R: Update execution status/context
    Note over Q,W: Crash hoặc mất reply sau DB commit
    W--xM: Reply bị mất / worker unreachable
    Note over M,Q: Không biết kết quả chỉ từ message timeout
~~~

Nếu manager không nhận được reply, **không được mặc định worker chưa xử lý**. Worker có thể đã commit DB nhưng chưa kịp gửi reply; request có thể bị broker redeliver. Cần định danh StepExecution, kiểm tra repository, worker liveness và business output trước khi re-dispatch.

### 14.3. Message acknowledgement không thay thế JDBC commit

- ACK message có thể đến **sau** DB commit.
- Worker crash giữa DB commit và ACK có thể khiến message redeliver.
- Message đã ACK trước khi business write bền vững có thể gây mất công việc nếu ack policy sai.
- Correlation của reply và worker StepExecution phải chính xác, không dựa chỉ vào số thứ tự request.
- Broker retry/DLQ không tự thay thế Batch retry/skip policy.

Đây là lý do **business idempotency** cần tồn tại ngay cả khi partition tên ổn định và checkpoint đúng.

### 14.4. Remote chunking là mô hình khác

Trong remote chunking, manager đọc item và gửi **ChunkRequest** cho worker xử lý/ghi; trong remote partitioning, worker tự đọc input shard. Hai mô hình đều có thể replay work khi mất ACK/reply, nhưng ranh giới checkpoint và nơi reader chạy khác nhau.

Không sao chép nguyên logic retry handler giữa remote chunking và remote partitioning khi chưa kiểm tra ownership, metadata và transaction boundaries của chúng.

### 14.5. Worker ownership và fencing

Giả sử worker A xử lý `range-0017` nhưng bị timeout lâu. Manager cho rằng A đã chết và khởi động worker B. Nếu A thực ra chưa dừng, **hai worker có thể viết cùng shard**.

1. Xác nhận worker A đã ngừng hoặc không còn giữ StepExecution trước restart.
2. Dùng generation/lease/fencing token ở orchestration nếu cần loại bỏ stale writes.
3. Writer idempotent, unique business key/version và database constraints.
4. Không sửa repository status để cưỡng ép re-execute khi chưa đối soát.
5. Đặt timeouts, heartbeats và grace period thống nhất với thời gian chunk dài nhất.

`JobRepository` là metadata/restart coordination quan trọng, nhưng không tự hoạt động như một global lock trên mọi external side effects.

## 15. Retry ở resource ngoài transaction: outbox và durable state

Một chunk writer gọi `paymentGateway.charge(...)` rồi ghi database có thể gặp tình huống:

~~~text
1. Charge thành công ở đối tác.
2. DB transaction rollback vì deadlock.
3. FaultTolerantStep retry cùng item.
4. Charge được gọi lần nữa.
5. Hai charge tồn tại dù chỉ một source item.
~~~

SQL rollback không thể hoàn tác payment ở hệ thống ngoài. Nếu nghiệp vụ cần tác dụng phụ đáng tin cậy:

- Ghi **business record + outbox event** trong cùng local JDBC chunk transaction.
- Dispatcher riêng claim outbox event bằng DB transaction ngắn.
- Dispatcher gọi API/publish broker **ngoài DB transaction** với stable idempotency key.
- Xác nhận thành công rồi mark SENT bằng transaction ngắn.
- Consumer/API đích dedupe hoặc tra trạng thái theo operation ID.
- Nếu crash giữa publish và mark SENT, retry cùng event ID không tạo hiệu ứng mới.

~~~mermaid
flowchart LR
    C["Chunk Writer"] --> DB[("Business DB<br/>Result + Outbox")]
    DB --> X["Dispatcher claim và COMMIT"]
    X --> E["External API / Broker"]
    E --> A["ACK / response"]
    A --> S["Mark SENT"]
    E -.->|"Lost response"| X
    X --> I["Stable idempotency key"]
    I --> E
~~~

**Outbox không bảo đảm delivery exactly-once.** Nó bảo đảm ý định publish được ghi cùng dữ liệu nghiệp vụ nếu cùng DB transaction; redelivery vẫn xảy ra sau crash, nên idempotency/inbox ở đích là phần còn lại của hợp đồng.

### 15.1. Nếu chỉ dùng GET API trong processor?

Một GET thuần đọc có thể an toàn hơn POST có side effect, nhưng nếu trả **giá hiện tại** hoặc trạng thái mutable, retry có thể trả dữ liệu khác với lần đầu. Cần API version/ETag/snapshot cutoff hoặc stage response để JobInstance dùng kết quả xác định qua restart.

Nếu latency mạng làm chunk transaction giữ DB connection/lock lâu, tách enrichment sang phase bên ngoài transaction, stage immutable response và cho worker Batch xử lý dữ liệu đã sẵn sàng.

### 15.2. Idempotency key phải sống qua retry/restart

Không tạo UUID mới **mỗi lần retry một request logic** rồi gọi đó là idempotency. Dùng stable key theo business operation/version, ví dụ:

~~~text
operationKey = "invoice-charge:" + invoiceId + ":" + operationVersion
~~~

Cùng key phải được hệ thống đích chấp nhận và xử lý idempotently. Nếu đích không hỗ trợ, cần query transaction status/reconciliation hoặc compensation; không tự tuyên bố exactly-once.

## 16. Retry count, skip count và budget ở nhiều partition

Với `P=24` partitions, mỗi worker có `retryLimit(3)` và `skipLimit(10)`, điều đó **không có nghĩa** toàn job chỉ retry tối đa ba lần hay skip tối đa mười records.

Giới hạn fault-tolerant step thường theo scope của **worker StepExecution**:

- Mỗi partition có thể gặp lỗi và retry độc lập.
- Tổng retry calls trên job có thể lớn hơn giới hạn của một worker.
- `skipLimit` ở worker có thể khiến số records skipped toàn job lớn hơn limit đơn.
- Restart có thể tạo worker StepExecution mới với retry budget mới.
- External effects cần budget bền vững nếu cùng business item xuất hiện qua nhiều executions.

### 16.1. Ví dụ retry storm

24 workers cùng gọi một database đang bị lock contention. Mỗi worker retry 3 lần không backoff, đồng thời nhiều jobs backfill. Tổng workload retry có thể khuếch đại tải, làm DB hồi phục chậm hơn.

Các biện pháp:

1. Bounded concurrency, executor queue và request admission.
2. Retryable classification hẹp, retryLimit hữu hạn.
3. Backoff + jitter và giới hạn toàn cluster khi cần.
4. Không retry duplicate HTTP side effect nếu thiếu idempotency key.
5. Giảm worker concurrency khi DB locks tăng.
6. Circuit breaker cho downstream nếu phù hợp.
7. Alert khi retry rate, p99 transaction duration và Hikari pending tăng.

### 16.2. Retry không phải giải pháp cho poisoned item

Nếu record có schema sai hoặc vi phạm quy tắc bất biến, retry 100 lần không sửa được. Cần fail và sửa dữ liệu nguồn có kiểm soát, hoặc quarantine nếu business policy cho phép skip. Phải log source ID, snapshot, partition key và lý do, rồi đối soát trước publish.

Một worker báo `COMPLETED` sau khi skip không có nghĩa Batch đã xử lý **toàn bộ** các bản ghi bắt buộc.

## 17. Ảnh hưởng tới throughput, memory và resource pools

Khi một chunk rollback, CPU/DB work trước lỗi có thể phải thực hiện lại. Nếu retry backoff chờ trong worker thread, concurrency hữu ích giảm dù executor vẫn có active threads.

Giả sử 8 workers, mỗi worker bình thường đạt 300 committed items/s, 20% thời gian worker dành cho rollback/retry/backoff và contention khác không đổi:

\[
R_{\mathrm{committed}}
\approx 8 \times 300 \times (1-0{,}2)
=1.920\ \text{items/s}.
\]

Đây là **ước lượng giả định**. Retry có thể đồng thời tăng DB contention nên throughput thực còn thấp hơn. Khi hết retries và partition fail, số workers có tiến độ giảm, còn partition bị skew có thể quyết định thời gian hoàn tất.

### 17.1. Những resource cần quan sát

| Resource | Khi rollback/retry tăng | Metric cần xem |
| --- | --- | --- |
| JDBC pool | Workers chờ connection/lock lâu hơn | Active/idle/pending, acquire/hold latency |
| Database | Deadlocks, WAL/redo và rollback work | Deadlocks/s, lock wait, transaction duration |
| CPU | Xử lý lại processor/serialization | CPU quota, GC, allocation |
| Executor | Threads busy nhưng throughput commit thấp | Active threads, queue age, rejection |
| Middleware | Reply lag, redelivery, duplicate request | Unacked, redelivery rate, correlation lag |
| JobRepository | Metadata updates chậm hoặc stale | Update latency, status age |
| Memory | Retry buffers, chunk allocations | Heap/RSS, GC pauses |
| External API | Duplicate request, 429/503, tail latency | Retry rate, quota, p95/p99, dedupe hits |

### 17.2. Chunk size thay đổi rollback scope

Với `chunk(100)`, lỗi writer trước commit có thể phải làm lại 100 items; với `chunk(10.000)`, cùng lỗi có thể khiến rollback 10.000 updates chưa commit, giữ DB locks lâu hơn và tăng memory.

Chunk quá nhỏ cũng tốn commit/metadata overhead. Hãy benchmark với **failure injection**, không chỉ clean-run throughput. Partition count ảnh hưởng skew và restart granularity; chunk size ảnh hưởng transaction duration/rollback scope — hai biến cần tune riêng.

### 17.3. Connection budget toàn cluster

Giả sử tám worker pods, mỗi pod Hikari pool tối đa 10 connections, manager pool tối đa 6:

\[
C_{\mathrm{configured}}=8\times10+6=86.
\]

Đây là trần pool cấu hình của nhóm minh họa, **không phải số connections đang dùng**, chưa tính online traffic. Nếu retry giữ transaction lâu do network/lock, tăng workers có thể làm hệ thống chậm hơn dù nhiều pods hơn.


## 18. Quan sát và truy vấn lịch sử theo partition

Để phân biệt retry trong một execution với restart ở execution khác, cần nhìn theo **JobInstance** và **partition key**, không chỉ JobExecution mới nhất.

### 18.1. Metadata SQL chỉ đọc

Ví dụ truy vấn schema mặc định Spring Batch:

~~~sql
SELECT
    je.JOB_INSTANCE_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.READ_SKIP_COUNT,
    se.PROCESS_SKIP_COUNT,
    se.WRITE_SKIP_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
WHERE je.JOB_INSTANCE_ID = :jobInstanceId
  AND se.STEP_NAME LIKE 'importWorker:%'
ORDER BY se.STEP_NAME, se.JOB_EXECUTION_ID;
~~~

Mục tiêu là xem **mọi lần chạy worker cùng tên** qua các JobExecutions. Nếu một partition `COMPLETED` ở #900 và không xuất hiện như worker chạy lại ở #901, đó có thể là hành vi restart đúng.

Không cộng tất cả `READ_COUNT` từ cả hai executions rồi suy rằng tất cả items đều khác nhau; một business key có thể được đọc nhiều lần do retry/restart.

### 18.2. Bộ metric đề xuất

| Metric | Câu hỏi |
| --- | --- |
| `retry_attempts_total{step,exceptionClass}` | Retry tập trung vào lỗi nào? |
| `rollback_count{partition}` | Partition nào thường rollback? |
| `committed_items_per_second` | Output có tăng thực sau retry không? |
| `chunk_transaction_duration_p99` | Tail/lock đang kéo dài transaction? |
| `partition_duration_max/p95` | Có straggler vì retry/skew? |
| `job_repository_update_latency` | Checkpoint có chậm hoặc timeout? |
| `writer_idempotency_conflicts` | Replay có nhiều, payload conflict xảy ra? |
| `remote_request_redelivery_count` | Transport có giao lại request? |
| `hikari_pending_connections` | Retry làm nghẽn pool? |
| `sla_remaining_time_seconds` | Recovery còn đủ deadline? |

Tên metric là **đề xuất**, không phải toàn bộ tự tồn tại trong Micrometer/Spring Batch. Tránh đưa `event_id` với hàng triệu giá trị vào metric labels; dùng log/traces cho high-cardinality IDs, metric theo step/error category.

### 18.3. Log phục vụ đối soát replay

Một log có cấu trúc nên liên kết:

~~~text
jobInstanceId
jobExecutionId
stepExecutionId
partitionKey
snapshotId
businessKey (nếu chính sách log cho phép)
retryAttempt / chunkCorrelation
exceptionClass
transactionOutcome
externalOperationId / idempotencyKey
~~~

Không log payload nhạy cảm; dùng correlation ID và audit store bảo vệ dữ liệu. Nếu StepExecution ID thay đổi khi restart, **partition key + snapshot + business key** vẫn giúp đối chiếu qua hai lần thực thi.

## 19. Kiểm thử lỗi ở các ranh giới trước/sau commit

Test nghiệp vụ quan trọng nhất không phải “job báo COMPLETED trên happy path” mà là **output sau failure/restart đúng như clean run**.

| Tình huống | Cách mô phỏng | Kết quả đúng |
| --- | --- | --- |
| Writer transient fail trước commit | Throw exception retryable ở chunk thứ 5 | Rollback chunk chưa commit, retry hữu hạn |
| Writer fail vượt retryLimit | Luôn throw cho một partition | Worker FAILED; chunk trước đã commit còn |
| Processor invalid record | Throw business validation | Fail hoặc skip theo chính sách và audit |
| JDBC commit không chắc trạng thái | Cắt connection sát commit | Idempotent writer + reconcile DB |
| Reader cursor fail | Ngắt JDBC read giữa chunk | Reader restore state đúng |
| Manager crash khi vài partitions COMPLETED | Kill manager trước tổng hợp | Repository giữ lịch sử; điều tra worker liveness |
| Remote worker crash sau DB commit | Kill trước gửi reply | Không double effect khi redelivery |
| Duplicate StepExecutionRequest | Deliver lại cùng request ID | Ownership/idempotency xử lý an toàn |
| Snapshot drift | Chỉnh file/checksum/rows giữa runs | Fail closed, không resume sai |
| Partition plan drift | Đổi key/range giữa restarts | Phát hiện, không silently repartition |
| Transaction manager sai | Writer dùng datasource B, tx A | Integration test phát hiện rollback sai |
| Worker cũ vẫn STARTED | Giữ worker A treo, kích hoạt recovery | Không đồng thời ghi cùng partition |
| Concurrent workers | Tăng C=1/4/8 | Output bằng reference, đo contention |
| Retry storm | DB timeout trên nhiều partitions | Backoff + bounded retries và quotas |
| Outbox dispatcher crash | Kill sau publish trước SENT | Consumer dedupe đúng |
| Restart đúng JobInstance | Fail một partition rồi restart | Completed partitions không chạy lại mặc định |

### 19.1. Test hợp đồng tên partition

Một test đơn vị quan trọng:

~~~java
@Test
void partitionNamesMatchExactlyOnRestart() {
    SnapshotRangePartitioner p =
            new SnapshotRangePartitioner(store, "snapshot-v42");

    Map<String, ExecutionContext> plan = p.partition(24);
    List<String> names = List.copyOf(p.getPartitionNames(24));

    assertEquals(plan.keySet(), new HashSet<>(names));
    assertEquals(names.size(), new HashSet<>(names).size());
}
~~~

`store` là test fixture đọc immutable manifest; bổ sung imports JUnit/collections. Production còn phải kiểm tra ranges coverage/disjointness, name key uniqueness, snapshot ID đúng và context không thay đổi. Test này **không thay thế** integration test splitter và JobRepository khi restart.

### 19.2. Test rollback JDBC thực

Chạy test trên database thật trong môi trường integration:

~~~text
Given:
  snapshot v42 gồm 500 events, output rỗng;
  worker partition range-0001 chứa ít nhất 300 events;
  chunk size = 100.

When:
  writer cố tình ném exception trước COMMIT chunk #3;
  retryLimit đủ thấp để worker cuối cùng FAILED.

Then:
  output chứa đúng hai chunk đã COMMIT trước đó
  (với giả định chúng cùng transactional datasource).
  Không có dữ liệu chưa commit của chunk #3.
  StepExecution có rollback/failure state đúng.
~~~

Sửa lỗi hoặc phục hồi hạ tầng rồi **restart cùng JobInstance**:

~~~text
When:
  JobOperator.restart(failedJobExecutionId)
  hoặc recovery mechanism phù hợp.

Then:
  partition FAILED được thực thi lại.
  partition COMPLETED trước không chạy lại mặc định.
  output cuối theo business key/source version
      == clean run trên cùng snapshot.
  không có duplicate external side effects.
~~~

### 19.3. Test retry không kéo dài vô hạn

Dùng fake repository/API luôn ném lỗi retryable và đếm invocations trong một worker StepExecution. Khi đạt giới hạn retry, worker phải fail hoặc xử lý theo skip policy đã định, không giữ thread retry vô hạn.

**Đo tổng số attempts thực tế** thay vì suy từ literal `retryLimit(3)`. Với restart qua nhiều JobExecutions, bổ sung một durable attempt budget nếu không được phép lặp vô hạn cùng business key.

### 19.4. Test khác biệt giữa rollback và retry

Một case giúp học sâu:

~~~text
1. Tạo 1.000 records thuộc một partition; chunk size = 100.
2. Ghi thành công 4 chunk đầu và kiểm tra DB có 400 kết quả.
3. Inject lỗi transient đúng tại writer chunk #5.
4. Xác nhận transaction chunk #5 rollback, không ghi partial.
5. Cho retry tiếp theo thành công và kiểm tra chunk #5 commit một lần logic.
6. Inject lỗi permanent ở chunk #6, để worker FAILED.
7. Restart JobInstance, không xóa 500 records đã commit.
8. Đối soát tập business IDs: đủ 1.000, không trùng, version chính xác.
~~~

Trình tự là **kế hoạch integration test**, không yêu cầu mã nguồn thực hiện ở đây. Mục tiêu là xác minh cả transaction rollback, retry trong execution hiện tại và restart execution kế tiếp.

## 20. Runbook khi một partition FAILED giữa chừng

Khi partition liên tục rollback/retry trong production, xử lý theo trình tự:

1. **Khoanh vùng:** ghi JobInstance, JobExecution, tên partition, StepExecutionId, snapshot và thời điểm lỗi.
2. **Giữ output chưa publish:** không công bố kết quả trước reconciliation.
3. **Kiểm tra worker liveness:** remote worker còn sống hoặc đang ghi dữ liệu không; tránh hai thế hệ cùng xử lý.
4. **Xác định phạm vi rollback:** chunk hiện tại có rollback thật không, trước đó đã commit bao nhiêu.
5. **Tìm lỗi gốc:** transient deadlock/timeout, data validation, schema mismatch hay API failure.
6. **Kiểm tra retry policy:** classification, retryLimit, backoff, skipLimit, retry storm.
7. **Kiểm tra metadata:** lịch sử partition, ExecutionContext, checkpoint và repository status.
8. **Kiểm tra resource pools:** Hikari active/pending, DB locks, queue age, HTTP p99 và retry rate.
9. **Xác minh input bất biến:** source checksum/version, min/max ranges, partition keys.
10. **Chọn phương án phục hồi:** sửa hạ tầng và restart đúng JobInstance; poisoned data cần repair/quarantine có phê duyệt; side effect không chắc kết quả cần reconciliation trước retry.
11. **Không xóa output chunk đã commit** nếu chưa có thiết kế rewind checkpoint đồng bộ.
12. **Không sửa `BATCH_STEP_EXECUTION.STATUS` bằng SQL** để ép job chạy tiếp hoặc đánh dấu completed.
13. **Chạy đối soát:** IDs, source versions, totals, checksums và external operation logs.
14. **Cập nhật runbook:** bổ sung fault tests, cảnh báo sớm và cải thiện backpressure/limits.

### 20.1. Kịch bản chống duplicate với thanh toán

Partition xử lý hóa đơn có `invoice_id=123` và gửi charge tới payment API. API timeout **sau khi đã trừ tiền**. Nếu chỉ bật retry trong ItemProcessor và tạo request ID mới, có nguy cơ trừ tiền lần nữa.

~~~text
businessOperationKey = "charge:invoice-123:v2"

1. Tra operation status từ hệ thống thanh toán nếu hỗ trợ.
2. Retry cùng businessOperationKey nếu gateway bảo đảm idempotency.
3. Ghi durable charge state và reconcile với ledger.
4. Không dùng DB rollback để kết luận gateway chưa charge.
~~~

Nếu payment gateway không hỗ trợ idempotency/status query, cần workflow reconciliation/exception handling đặc biệt, không hứa exactly-once nhờ Spring Retry.

## 21. Những hiểu nhầm cần tránh

| Nhận định | Điều cần chỉnh |
| --- | --- |
| “Một partition FAILED thì mọi chunk trước bị rollback.” | Chỉ transaction chưa commit rollback; chunk đã commit còn. |
| “Retry và restart là một.” | Retry trong execution hiện tại; restart mở JobExecution mới cùng JobInstance. |
| “Retry cùng partition luôn xử lý từ đầu.” | Restart có thể resume từ checkpoint; tùy reader/source. |
| “Rollback tự rewind mọi reader.” | File, JDBC cursor và queue reader có semantics khác nhau. |
| “StepExecution FAILED nghĩa output chưa có.” | Nhiều chunk có thể đã commit. |
| “Các partition COMPLETED phải chạy lại nếu manager FAILED.” | Splitter chuẩn thường bỏ qua completed partitions khi restart. |
| “Đổi gridSize sẽ tự cân bằng lại partition cũ.” | Plan phải ổn định khi restart cùng JobInstance. |
| “`retryLimit(3)` là giới hạn toàn đời record.” | Retry budget có thể reset qua JobExecutions. |
| “Tăng retryLimit luôn tốt.” | Tăng lock contention, API throttling và có thể trễ SLA. |
| “Skip được miễn job COMPLETED.” | Business phải chấp nhận skip có audit/reconciliation. |
| “Writer JDBC rollback thì email cũng rollback.” | External effects không tự theo JDBC transaction. |
| “Broker reply timeout chứng minh worker chưa commit.” | Worker có thể commit rồi mất reply/ACK. |
| “`@StepScope` làm reader riêng từng chunk thread.” | Scope theo StepExecution, không theo thread. |
| “JobRepository luôn atomic với writer.” | Chỉ khi cùng transaction resource/config phù hợp. |
| “ON CONFLICT DO NOTHING bảo đảm exactly-once.” | Không phát hiện cùng key nhưng payload mâu thuẫn. |
| “Cứ tăng pool khi retry nhiều.” | Retry có thể do DB/HTTP đã bão hòa. |
| “Job COMPLETED nghĩa output không trùng.” | Cần so business keys, versions, totals và side-effect logs. |

## 22. Checklist trước production

- [ ] Phân biệt rõ item/chunk/transaction/partition/StepExecution/JobExecution/JobInstance.
- [ ] Reader mỗi worker gắn với **snapshot và partition range bất biến**.
- [ ] Partition key và context không thay đổi giữa các lần restart.
- [ ] Reader/processor/writer/transaction manager khớp resource thực.
- [ ] Fault-tolerant retry chỉ cho lỗi transient.
- [ ] Có retryLimit, bounded backoff, rate limit và runbook khi hết attempts.
- [ ] Skip policy được nghiệp vụ chấp thuận, có audit/quarantine và error budget.
- [ ] Có integration test rollback thật khi writer DB lỗi.
- [ ] Checkpoint ItemStream và JobRepository bền vững, không dựa vào counters đơn lẻ.
- [ ] Writer idempotent cho replay do rollback, crash và redelivery.
- [ ] External API/message effects có idempotency key hoặc outbox/inbox/reconciliation.
- [ ] Không giữ JDBC transaction mở trong thời gian chờ network không kiểm soát.
- [ ] Resource pools, HTTP quotas và concurrency tính trên toàn worker cluster.
- [ ] Completed partitions không bị ép chạy lại ngoài chính sách.
- [ ] Remote worker cũ không tiếp tục ghi khi worker mới xử lý cùng partition.
- [ ] Đã test trước commit, sau commit, mất ACK/reply và crash worker/manager.
- [ ] Đã test restart cùng JobInstance, so output với clean run.
- [ ] Có dashboard rollback/retry/p99, committed throughput, worker status và ETA.
- [ ] Có quy trình repair poisoned data, không retry vô hạn.
- [ ] Không publish output khi reconciliation chưa đạt.

## 23. Câu hỏi tự kiểm tra

1. Vì sao worker partition `FAILED` vẫn có thể đã ghi hàng nghìn rows hợp lệ?
2. Rollback chunk thứ 51 có hoàn tác 50 chunk trước đã commit không?
3. Retry trong `FaultTolerantStepBuilder` khác `JobOperator.restart(...)` thế nào?
4. Với 24 partitions và `retryLimit(3)` mỗi worker, có phải job chỉ retry tổng cộng ba lần không?
5. Nếu có `skip(...)` phù hợp, điều gì có thể xảy ra sau retry exhaustion?
6. Vì sao writer có thể được gọi nhiều lần cho cùng item trong writer failure recovery?
7. Tại sao GET “latest” có thể trả dữ liệu khác khi restart?
8. Khi `JdbcCursorItemReader.saveState(true)`, điều gì phải giữ cố định để resume?
9. Nếu business DB và JobRepository dùng hai managers khác nhau, crash có nguy cơ gì?
10. Khi một partition FAILED, các partitions COMPLETED có chạy lại mặc định không?
11. `PartitionNameProvider#getPartitionNames` trả chỉ tên partition lỗi hay tất cả tên plan?
12. Vì sao đổi gridSize, ID ranges hoặc worker step name giữa restarts nguy hiểm?
13. HTTP POST charge timeout: có nên retry request ID mới không?
14. Vì sao mất broker ACK/reply không chứng minh worker chưa commit?
15. Tại sao tăng workers có thể làm retry rate/rollback count tăng?
16. Lý do dùng `assertUpdates(false)` trong JDBC upsert idempotent?
17. `ON CONFLICT` có đủ bảo vệ payload conflict khi cùng source version không?
18. Vì sao `readCount` của JobExecution mới nhất chưa đủ để biết số unique items đã xử lý?
19. Metric nào phân biệt deadlock/retry storm với partition skew?
20. Integration test quan trọng nhất để nghiệm thu restart partition là gì?

**Gợi ý:** (1) Chunk trước đã commit, partition fail ở chunk sau. (2) Không. (3) Retry trong StepExecution, restart mở JobExecution mới cùng JobInstance. (4) Không, retry theo từng worker context. (5) Skip có audit/limit hoặc fail theo policy. (6) Fault-tolerant recovery có thể replay chunk. (7) Nguồn mutable. (8) Immutable snapshot, deterministic ordering, checkpoint hợp lệ. (9) Replay/duplicate hoặc missing nếu metadata và data lệch. (10) Không, theo splitter chuẩn. (11) Toàn bộ tên plan gốc. (12) Checkpoint/identity không khớp. (13) Không, stable idempotency key hoặc tra trạng thái. (14) Reply có thể mất sau commit. (15) Contention/quota bão hòa. (16) Upsert no-op hợp lệ update count 0. (17) Không, cần compare payload conflict. (18) Retry/restart có thể lặp business ID. (19) Rollback/lock waits/Hikari + per-partition duration. (20) Inject failure, restart đúng instance, so output với clean run và xác minh completed partitions không chạy lại.

## Tài liệu tham khảo

- [Spring Batch Reference 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): partition manager/worker và restart semantics.
- [Spring Batch Reference 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ExecutionContext`, `ItemStream` và checkpoint.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault-tolerant step và retryable exceptions.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip policy.
- [Spring Batch Reference — Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html): rollback defaults và `noRollback`.
- [Spring Batch 5.2 — Transaction Attributes](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/transaction-attributes.html): transaction boundary.
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata persistence.
- [Spring Batch API 5.2 — FaultTolerantStepBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/step/builder/FaultTolerantStepBuilder.html): retry, skip, rollback.
- [Spring Retry — Backoff and Policies](https://docs.spring.io/spring-retry/docs/current/reference/html/): retry policies, bounded backoff.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): JDBC resource transactions và exception rollback.

**Điểm cốt lõi:** **Rollback thuộc transaction của chunk hiện tại, retry thuộc chính sách xử lý lỗi trong worker StepExecution, còn restart thuộc lịch sử JobInstance.** Trong partitioned Spring Batch job, một partition lỗi không hoàn tác các chunk đã commit hoặc dữ liệu do partition khác ghi. Để retry/restart cùng partition an toàn, cần **immutable snapshot + tên partition ổn định + JobRepository checkpoint + writer idempotent + retry hữu hạn + đối soát dữ liệu**. Với remote workers và API/broker, work có thể được phát lại: phải thiết kế ownership, ACK/reply, outbox/inbox và business idempotency phù hợp.
