# Thay đổi transaction behavior khi nâng cấp Spring Batch

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao **cùng một batch job** có thể thay đổi kết quả rollback, commit, retry và restart khi nâng cấp phiên bản Spring Batch, Spring Framework, Spring Boot, JDBC driver hoặc database.
- Phân biệt thay đổi **API cấu hình** với thay đổi **ngữ nghĩa giao dịch thực tế**, đặc biệt lúc chuyển từ Spring Batch 4.x sang 5.x.
- Chọn và nối đúng `JobRepository`, `DataSource` và `PlatformTransactionManager` khi cấu hình `StepBuilder`, tasklet và chunk-oriented steps trên Java 17 / Spring Batch 5.x.
- Kiểm chứng chunk transaction boundaries, propagation, isolation, timeout, rollback rules, writer side effects và checkpoint của `ExecutionContext`.
- Hiểu rủi ro với **hai transaction managers / hai databases**: business commit thành công nhưng repository metadata chưa ghi được, dẫn tới replay.
- Phân biệt retry/skip/`noRollback` với restart của `JobInstance` và redelivery của remote workers.
- Chỉ ra các failure window khi scale qua multi-threaded steps, parallel flows, partitioning, remote chunking và remote partitioning.
- Viết kiểm thử trước/sau nâng cấp bằng JUnit 5, JDBC repository, PostgreSQL và fault injection có kiểm soát.
- Thiết kế migration/rolling deployment có version pinning, schema/metadata compatibility, metrics, canary và rollback plan.
- Đánh giá nâng cấp là thành công khi **kết quả dữ liệu, trạng thái metadata và khả năng khôi phục** đều đạt, không chỉ khi ứng dụng compile hoặc job báo COMPLETED.

## 1. Tình huống: job chạy được sau nâng cấp nhưng checkpoint không còn đúng

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, ứng dụng mở rộng workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và nhiều worker. Một thay đổi nhỏ ở cấu hình transaction có thể bị khuếch đại thành hàng triệu bản ghi replay hoặc một loạt partition thất bại.

Giả sử job `importOrders` đọc snapshot 12 triệu đơn hàng:

- Trước nâng cấp, chunk size là 200, writer và metadata dùng cùng database/transaction resource theo cấu hình đã kiểm thử.
- Sau nâng cấp, người phát triển đổi sang `StepBuilder` mới và vô tình inject **transaction manager dành cho JobRepository**, trong khi writer sử dụng `DataSource` khác.
- Một chunk ghi thành công 200 đơn hàng vào business DB, nhưng cập nhật checkpoint hoặc metadata bị lỗi trên database repository.
- Sau restart, chunk có thể được đọc lại vì metadata chưa ghi nhận tiến độ mới. Nếu writer không idempotent, hệ thống có thể tạo double charge, double email hoặc duplicate rows.

Đây không đơn thuần là lỗi build. **Khả năng commit/rollback đồng bộ giữa dữ liệu nghiệp vụ và checkpoint** là thuộc tính phải được xác minh khi nâng cấp.

~~~mermaid
flowchart LR
    U["Nâng cấp Spring Batch / Boot / JDBC"] --> C["API + transaction wiring"]
    C --> S["Chunk: read / process / write"]
    S --> B["Business commit"]
    S --> R["JobRepository checkpoint"]
    B --> O["Business output"]
    R --> P["Durable restart position"]
    O --> V{"Hai trạng thái nhất quán?"}
    P --> V
    V -->|"Không"| X["Replay / missing / duplicate effects"]
    V -->|"Có"| Y["Restart an toàn"]
~~~

**Ý chính:** không mặc định “nâng cấp minor không đổi transaction behavior” hoặc “đã dùng `@Transactional` là an toàn”. Phải xem transaction manager, resource bindings và đường thực thi cụ thể.

## 2. “Transaction behavior” gồm những gì?

Trong batch processing, cụm từ này bao gồm nhiều thuộc tính khác nhau:

| Thuộc tính | Câu hỏi cần kiểm tra | Hệ quả nếu thay đổi |
| --- | --- | --- |
| **Transaction boundary** | Bắt đầu/kết thúc ở chunk, tasklet hay method nào? | Nhiều hoặc ít items cùng commit hơn |
| **Transaction manager** | Manager nào quản lý connection của reader/writer/repository? | Business DB và metadata không còn atomic như kỳ vọng |
| **Propagation** | `REQUIRED`, `REQUIRES_NEW`, `NESTED` được áp dụng ở đâu? | Checkout connection/commit độc lập, rollback bất ngờ |
| **Isolation** | `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`? | Visibility, lock conflict, phantom/serialization failure |
| **Rollback rule** | Exception nào dẫn tới rollback? | Partial effects hoặc retry trên trạng thái sai |
| **Retry/skip/recovery** | Item/chunk có thể được thử lại hoặc bỏ qua không? | Attempt amplification, thiếu dữ liệu |
| **Timeout** | Transaction/query/pool/HTTP timeout tác động thế nào? | Chunk fail hoặc giữ connection lâu |
| **Checkpoint persistence** | `ItemStream.update`/`ExecutionContext` và business write commit cùng boundary không? | Replay hoặc bỏ qua item khi restart |
| **Concurrency ownership** | Có bao nhiêu threads/JVM cập nhật cùng StepExecution? | Metadata conflicts, stale worker |
| **External side effect** | Email/API/broker có nằm trong transaction DB không? | Commit thành công nhưng ACK mất, duplicate effect |
| **Metadata serialization/schema** | Phiên bản mới đọc được trạng thái cũ không? | Restart fail dù business DB không lỗi |

Trong Spring Batch, **một StepExecution COMPLETED chỉ nói về lifecycle của Step**, không phải bằng chứng mọi side effect trên các hệ thống độc lập đã commit đúng một lần.

## 3. Đường nâng cấp: 4.x → 5.x → phiên bản đích

### 3.1. Phân biệt breaking API và breaking runtime semantics

Spring Batch 5.x gắn với hệ sinh thái Spring Framework 6 và yêu cầu Java 17 ở mức nền tảng. Một số API builder/factory cũ của dòng trước bị thay thế hoặc không còn được khuyến khích sử dụng. Trong cấu hình Java của Spring Batch 5.x, `StepBuilder` nhận `JobRepository` và cấu hình chunk/tasklet nhận **`PlatformTransactionManager` tường minh**.

Điều này có thể làm lộ giả định cũ: ứng dụng từng dựa vào transaction manager được chọn tự động qua factory/auto-configuration. Nếu chuyển code máy móc mà chọn nhầm manager, transaction behavior thay đổi dù xử lý item không sửa.

### 3.2. Ma trận kiểm tra theo trục tương thích

| Trục nâng cấp | Điều nên xác nhận | Không được suy đoán |
| --- | --- | --- |
| Spring Batch 4.x → 5.x | Job/Step builder APIs, Java baseline, repository config, metadata schema, serializer | “Chỉ sửa import là giữ nguyên transaction” |
| Spring Batch 5.x minor → minor | Release notes, deprecated APIs, retry/restart behavior, repository configuration | “Minor upgrade luôn không ảnh hưởng transaction” |
| Spring Batch 5.x → 6.x hoặc dòng mới | Compatibility matrix, migration guide chính thức của phiên bản **đích**, API/DDL thực tế | Không dùng code/DDL 5.x làm cam kết cho 6.x |
| Spring Boot 2.x → 3.x | DataSource/transaction auto-config, bean names, Java/Jakarta, Actuator instrumentation | “Bean nào cùng type cũng thay được” |
| JDBC driver/database upgrade | SQLSTATE mapping, auto-commit, cursor holdability, isolation/lock/timeout | “Không đổi Spring Batch thì transaction không đổi” |
| Broker/client upgrade | ACK/redelivery semantics, transaction scope, retries và DLQ | “Broker ACK đồng nghĩa business DB commit” |

Bảng định hướng những điểm phải **chứng minh với đúng bộ phiên bản**. Không phải mọi trường hợp ở đây đều đã được tuyên bố thay đổi hành vi mặc định. Kiểm tra release notes, schema migration và integration tests là bước bắt buộc.

### 3.3. Chốt BOM thay vì pha phiên bản

Không nên lấy một class từ hướng dẫn Spring Batch 5.2, một `spring-retry` tùy ý và một bản Spring Boot không tương thích rồi kỳ vọng vận hành đúng. Dùng BOM/dependency management được hỗ trợ, pin phiên bản thử nghiệm, ghi nhận:

~~~text
Java runtime
Spring Boot
Spring Framework
Spring Batch
Spring Retry
JDBC driver
Database server
Broker / integration libraries
Schema migration revision
~~~

Bảng này phải có trong release artifact/runbook để tái tạo kết quả trước/sau nâng cấp.

## 4. Ví dụ API: từ StepBuilderFactory sang StepBuilder với transaction manager rõ ràng

### Cấu hình kiểu cũ để nhận diện ý nghĩa

Trong các dự án Spring Batch 4.x, có thể gặp code theo mẫu:

~~~java
// Đoạn mô tả phong cách Spring Batch 4.x, KHÔNG dùng như
// mã nguồn biên dịch mới của Spring Batch 5.x.
@Autowired StepBuilderFactory stepBuilderFactory;

@Bean
Step importStep() {
    return stepBuilderFactory.get("importStep")
            .<Order, Order>chunk(200)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

Ở môi trường cũ, factory/framework có thể cấp `JobRepository` và transaction manager theo wiring của ứng dụng. Khi migrate, **phải biết manager nào thực sự được dùng**; không chỉ thay tên class.

### Cấu hình Spring Batch 5.x / Java 17

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.transaction.PlatformTransactionManager;

record Order(String snapshotId, long orderId, String payload) {}

@Configuration
class OrderStepConfiguration {

    @Bean("importOrdersStep")
    Step importOrdersStep(
            JobRepository repository,
            @Qualifier("businessTransactionManager")
                PlatformTransactionManager businessTxManager,
            @Qualifier("orderReader")
                ItemReader<Order> reader,
            @Qualifier("orderWriter")
                ItemWriter<Order> writer) {

        return new StepBuilder("importOrdersStep", repository)
                .<Order, Order>chunk(200, businessTxManager)
                .reader(reader)
                .writer(writer)
                .build();
    }
}
~~~

**Ý nghĩa:**

- `JobRepository` chịu trách nhiệm execution metadata; nó không có nghĩa `businessTxManager` sẽ tự quản lý tất cả transaction repository.
- `chunk(200,businessTxManager)` xác định manager điều phối chunk transaction của Step.
- `orderWriter` cần sử dụng tài nguyên được **manager đã chọn** thực sự quản lý, hoặc có contract riêng khi khác tài nguyên.
- `@Qualifier` tránh vô tình chọn sai manager nếu có nhiều `PlatformTransactionManager` beans.
- `Order`, `orderReader`, `orderWriter`, datasource và repository là thành phần ứng dụng phải cung cấp. Snippet là cấu hình trọng tâm, không phải dự án tự chạy đầy đủ.

### Với tasklet step

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("validateSnapshotStep")
Step validateSnapshotStep(
        JobRepository repository,
        @Qualifier("businessTransactionManager")
            PlatformTransactionManager txManager) {

    return new StepBuilder("validateSnapshotStep", repository)
            .tasklet((contribution, context) -> {
                // Chỉ làm validation phù hợp transaction/resource
                // được manager này quản lý.
                return RepeatStatus.FINISHED;
            }, txManager)
            .build();
}
~~~

`TaskletStep` và chunk step đều cần được audit transaction manager khi migrate. Đừng suy một `Tasklet` chỉ đọc input nên mọi side effect sẽ tự rollback nếu có lỗi.

## 5. JobRepository transaction không đồng nghĩa chunk transaction

Trong kiến trúc JDBC, cần phân biệt **transaction metadata** và **transaction nghiệp vụ**.

~~~mermaid
flowchart TD
    JOB["JobLauncher / Job"] --> ST["Chunk Step"]
    ST --> TM["PlatformTransactionManager được Step sử dụng"]
    ST --> JR["JobRepository"]
    TM --> BD["Business DataSource"]
    JR --> RM["Repository transaction configuration"]
    RM --> RD["Metadata DataSource"]
    BD --> O["Output rows / side effects"]
    RD --> E["StepExecution / ExecutionContext"]
~~~

Nếu business và repository cùng chia một transaction resource được cấu hình đúng, cập nhật dữ liệu và checkpoint **có thể** cùng commit/rollback trong chunk transaction. Nếu hai resources/transaction managers khác nhau, chúng **không tự có atomic commit**.

### Bảng tình huống

| Business writer | Repository | Có atomic commit mặc định không? | Cần chuẩn bị |
| --- | --- | --- | --- |
| Cùng DB, cùng local transaction/manager, wiring phù hợp | Cùng resource | Có thể atomic ở chunk boundary sau khi xác minh | Integration test rollback/checkpoint |
| Khác database, hai local managers | Metadata DB riêng | **Không** mặc định | Idempotent writer, reconciliation, crash tests |
| JDBC target + HTTP side effect | Metadata ở JDBC | **Không** cho HTTP call | External idempotency key/outbox |
| JDBC target + broker publish | Metadata ở JDBC | **Không** tự giao dịch chung | Outbox/dedup/ACK contract |
| JDBC writer + `REQUIRES_NEW` bên trong | Metadata dùng outer transaction | Có commit độc lập trong inner tx | Retry tests, ownership và failure window |

### Một “fix” dễ tạo lỗi

Đổi:

~~~text
chunk(..., businessTransactionManager)
~~~

thành:

~~~text
chunk(..., repositoryTransactionManager)
~~~

chỉ vì bean sau dễ inject có thể làm writer chạy ngoài transaction kỳ vọng. Một `JdbcTemplate` ở datasource khác không được manager đó quản lý tự động; thao tác business có thể autocommit, hoặc dùng giao dịch riêng. Job status và `COMMIT_COUNT` sẽ không đủ làm oracle.

## 6. Chunk transaction lifecycle: những gì xảy ra quanh commit?

Mô hình khái niệm cho chunk-oriented step:

~~~mermaid
sequenceDiagram
    participant S as Step / Chunk
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant D as Business DB
    participant J as JobRepository
    S->>S: Bắt đầu chunk transaction
    loop Items trong chunk
      S->>R: read
      S->>P: process
    end
    S->>W: write batch
    W->>D: SQL / business writes
    S->>J: Persist state / execution metadata theo lifecycle
    S->>D: Commit hoặc rollback
    Note over D,J: Quan hệ atomic tùy resource + transaction wiring
~~~

Sơ đồ không cam kết chính xác nội bộ thứ tự gọi/ghi của mọi reader, fault-tolerant step và repository. Điều cần kiểm thử là **trạng thái bền vững sau mỗi failure window**.

### Chunk size không chỉ là hiệu năng

Với `chunk(200, txManager)`, transaction được thiết kế quanh một nhóm items, nhưng không được suy tuyệt đối “mỗi 200 item tạo đúng một SQL transaction và commit một lần” khi có skips, filters, retry, read EOF, rollback và custom writer. Tăng chunk size có thể:

- Giảm metadata/commit overhead.
- Giữ connection/row locks lâu hơn.
- Tăng lượng công việc phải replay khi fail trước checkpoint.
- Tăng memory và kích thước batch JDBC.
- Làm tail latency và deadlock probability thay đổi khi nhiều worker cùng ghi.

Đánh giá chunk size cùng transaction latency, `READ_COUNT`/`WRITE_COUNT`/`COMMIT_COUNT`, unique business commits, DB lock waits và restart correctness.

## 7. Rollback behavior: đừng mặc định cùng Exception sẽ luôn giống nhau

Spring Batch cho phép cấu hình fault-tolerant read/process/write, retry, skip và rollback policy. Cơ chế thực tế phụ thuộc **phase phát sinh exception**, transaction manager, loại exception và cấu hình Step.

| Vị trí lỗi | Hành vi cần kiểm chứng | Rủi ro khi nâng cấp |
| --- | --- | --- |
| Reader | Exception có gây rollback hay được skip/retry theo policy? | Reader không rewind đúng, checkpoint lệch |
| Processor | Có side effect không? item được xử lý lại bao nhiêu lần? | Email/API gọi lại khi retry |
| Writer | Transaction rollback đúng khi SQL lỗi? | Partial business commit/autocommit |
| ItemStream update | Checkpoint được persist lúc nào, rollback thế nào? | Bỏ sót hoặc lặp items sau crash |
| Listener | Throwable/ExitStatus ảnh hưởng flow không? | Job báo COMPLETED dù business lỗi |
| Metadata persistence | Lỗi repository có rollback business cùng resource không? | Replay từ checkpoint cũ |
| External API/broker | Đích đã commit trước timeout chưa? | Duplicate event/payment |

**Không blanket khẳng định mọi lỗi ở ItemReader/Processor/Writer đều rollback giống nhau.** Spring Batch có quy tắc riêng cho lỗi đọc và fault-tolerant processing; khi cần bảo đảm transaction, hãy kiểm thử đúng phiên bản và đúng read/process/write path.

### Exception classification có thể đổi do JDBC/framework

Sau nâng cấp driver/Spring Framework, cùng SQLSTATE có thể được translate thành loại `DataAccessException` khác. Nếu retry policy chỉ match một class, hệ thống có thể thay từ retry sang fail-fast (hoặc ngược lại). Ghi lại:

- SQLSTATE/vendor error code có thể lấy từ DB.
- Exception chain sau translate, không ghi secrets trong message.
- `retry(...)`, `noRetry(...)`, `skip(...)`, `noRollback(...)` đang cấu hình.
- Transaction đã rollback chưa, có commit độc lập nào không.

### Không dùng `noRollback` để giấu DB error

Với lỗi SQL/constraint/deadlock làm transaction bị đánh dấu rollback-only, cố cấu hình `noRollback(...)` thường không thể biến transaction hỏng thành thành công. Có thể dùng rollback policy cho những lỗi đã được **chứng minh an toàn không rollback**, nhưng cần integration test khẳng định data correctness.

## 8. Ví dụ fault-tolerant step: phân loại retry/skip rõ ràng

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

Step createRetryingStep(
        JobRepository repository,
        PlatformTransactionManager businessTx,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    var backoff = new ExponentialBackOffPolicy();
    backoff.setInitialInterval(250L);
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(4000L);

    return new StepBuilder("retryingImportStep", repository)
            .<Order, Order>chunk(200, businessTx)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(CannotAcquireLockException.class)
            .retry(TransientDataAccessResourceException.class)
            .retryLimit(4)
            .backOffPolicy(backoff)
            .build();
}
~~~

Đây là cấu hình minh họa Spring Batch 5.x. `retryLimit` có ngữ nghĩa cụ thể của thư viện/phase được cấu hình; test số lần gọi thực tế thay vì suy từ phép nhân tổng quát. Các bean chưa được wiring để giữ snippet tập trung vào API. Spring Retry dependency cần tương thích với Spring Batch release.

**Điểm migration quan trọng:** nếu trước nâng cấp code tự retry `SQLException` hoặc `RuntimeException` rất rộng, thay bằng policy phân loại rõ không chỉ là “refactor”: nó thay cơ chế recovery và quyết định có fail/skip hay không. Mọi thay đổi này phải được review như thay đổi nghiệp vụ.

## 9. Transaction timeout khác query timeout và pool timeout

Một chunk có thể bị timeout ở nhiều lớp:

| Timeout | Tác động điển hình | Có nhất thiết rollback business DB không? |
| --- | --- | --- |
| Transaction timeout | Giao dịch bị giới hạn theo manager/DB | Phụ thuộc việc manager/driver thực thi timeout và trạng thái tx |
| JDBC statement/query timeout | Statement vượt thời gian | Có thể làm transaction cần rollback; DB/vendor-specific |
| Hikari `connectionTimeout` | Thread chờ checkout pool quá lâu | Chưa có connection cho thao tác đó; các thao tác khác có thể đã commit |
| JDBC socket/network timeout | Mất phản hồi của server | Có thể **không biết** DB đã commit chưa |
| HTTP request timeout | External API không trả kịp | Không biết remote side effect có hoàn tất |
| Broker ACK timeout | Không nhận xác nhận đúng hạn | Không chứng minh consumer chưa commit |

Không coi nâng `connectionTimeout` là sửa transaction conflict. Nó có thể chỉ làm các threads chờ lâu hơn và gây retry storms ở tầng khác.

### Có thể cấu hình transaction attribute tường minh

~~~java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;

// Ví dụ: chú ý isolation của database thật.
var txAttr = new DefaultTransactionAttribute();
txAttr.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
txAttr.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
txAttr.setTimeout(30);

// Trong builder của một chunk step đã có transaction manager:
// new StepBuilder("...", repository)
//     .<Input, Output>chunk(200, businessTxManager)
//     .transactionAttribute(txAttr)
//     .reader(...).writer(...).build();
~~~

**Không chọn `READ_COMMITTED` hoặc timeout 30s chỉ vì ví dụ.** Chúng phải phù hợp consistency, lock contention, processing time và database driver. Default isolation có thể do database đặt; mã hóa tường minh một mức isolation khác khi migrate có thể làm output/retry behavior đổi.

## 10. Isolation và optimistic locking ở JobRepository

`JobRepository` tạo và cập nhật execution metadata qua database. Đặc biệt khi **hai scheduler cùng launch cùng identifying JobParameters**, cơ chế transaction/isolation của các phương thức tạo execution ảnh hưởng tới khả năng ngăn duplicate launch.

### Những cấu hình đáng kiểm tra

- `isolationLevelForCreate` trong cấu hình JobRepository: có tác động đối với các phương thức tạo execution, không nên nhầm với isolation của toàn bộ business chunk.
- Một scheduler/manager có thể đồng thời với scheduler khác; phải xác minh chỉ một execution được phép sở hữu công việc theo lifecycle.
- `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION` có `VERSION` để phát hiện một số optimistic updates stale.
- ExecutionContext được serialize/persist theo workflow riêng; đừng suy rằng mọi sửa đổi context có compare-and-swap độc lập.
- Đổi transaction manager bean hoặc isolation làm lock waits/deadlocks và exception type thay đổi.

### SQL đọc để kiểm tra, không sửa bảng framework

~~~sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    VERSION,
    STATUS,
    START_TIME,
    END_TIME
FROM BATCH_JOB_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId;
~~~

~~~sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    VERSION,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

**Không tự chạy `UPDATE BATCH_STEP_EXECUTION SET VERSION=...`** để “sửa” retry/restart sau nâng cấp; làm vậy có thể phá optimistic-locking và tính đúng của checkpoint.

## 11. Hai DataSource: failure window giữa business commit và checkpoint

Khi tách repository và business data, ta thường dùng:

~~~text
repoDataSource      -> PostgreSQL metadata database
businessDataSource  -> PostgreSQL orders database

repoTransactionManager      -> quản lý metadata transaction
businessTransactionManager  -> quản lý business JDBC transaction
~~~

Hai đối tượng `PlatformTransactionManager` không hợp nhất thành transaction hai pha chỉ vì cùng tồn tại trong Spring context.

### Tình huống commit thành công nhưng metadata cũ

~~~mermaid
sequenceDiagram
    participant W as Batch Worker
    participant T as Business Transaction
    participant O as Orders DB
    participant R as JobRepository
    participant N as Restart Worker
    W->>T: Bắt đầu xử lý chunk N
    T->>O: INSERT/UPDATE 200 orders
    O-->>T: Commit OK
    Note over W,R: Crash / metadata write thất bại
    N->>R: Load last durable ExecutionContext
    R-->>N: Checkpoint tại chunk N-1
    N->>O: Replay chunk N
    O-->>N: Duplicate/UPSERT tùy idempotency
~~~

Đây là **cửa sổ có thể xảy ra khi resources không cùng transaction**, không phải khẳng định Spring Batch luôn commit business trước metadata theo một thứ tự cố định. Cửa sổ đối nghịch cũng phải được xét nếu ứng dụng có protocol tự quản lý checkpoint: tiến độ được ghi sớm trong khi output chưa commit có thể gây **skip dữ liệu**.

### Cách ứng phó

1. **Ưu tiên kiểm chứng cùng local transaction resource** cho writer và metadata nếu kiến trúc cho phép, không chỉ dựa vào tên bean.
2. Khi thực sự cần hai DB hoặc HTTP/broker, sử dụng business operation identity ổn định và **idempotent writer**.
3. Ghi input snapshot/partition range bất biến để replay cùng business keys.
4. Đối soát source–target sau recovery; không dùng một mình `COMMIT_COUNT` hoặc `WRITE_COUNT`.
5. Nếu yêu cầu atomicity xuyên nhiều systems, đánh giá giải pháp outbox/saga hoặc transaction protocol phù hợp; không giả định chọn `JtaTransactionManager` là đủ khi các resources không hỗ trợ.
6. Mô phỏng cả lỗi **trước commit**, **sau business commit** và **sau metadata persist** trong integration tests.

### Bảng application-owned chống duplicate

~~~sql
CREATE TABLE app_order_result (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);

INSERT INTO app_order_result (
    snapshot_id, order_id, source_version, payload
)
VALUES (:snapshotId, :orderId, :sourceVersion, :payload)
ON CONFLICT (snapshot_id, order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    payload = EXCLUDED.payload
WHERE (
    app_order_result.source_version,
    app_order_result.payload
) IS DISTINCT FROM (
    EXCLUDED.source_version,
    EXCLUDED.payload
);
~~~

Mẫu UPSERT bảo vệ **final database row** khi replay cùng snapshot, nhưng không tự bảo vệ trigger, external API, email hoặc broker publish. Một transaction replay cần business key/operation ID và reconciliation phù hợp. Đừng dùng `ON CONFLICT DO NOTHING` với mọi record nếu business rule cần báo lỗi khi cùng key có payload mâu thuẫn.

## 12. Transaction propagation: `REQUIRED`, `REQUIRES_NEW` và `NESTED`

Khi nâng cấp framework, cần kiểm tra custom services dùng `@Transactional` bên trong ItemProcessor/ItemWriter.

| Propagation | Ý tưởng chính | Nguy cơ khi scale |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction đang tồn tại hoặc tạo mới | Rollback-only có thể lan ra outer transaction |
| `REQUIRES_NEW` | Suspend outer và tạo transaction độc lập | Thêm checkout connection, commit inner không rollback cùng outer |
| `NESTED` | Savepoint bên trong transaction hiện có nếu hỗ trợ | Driver/transaction manager có thể không hỗ trợ như kỳ vọng |
| `NOT_SUPPORTED` | Chạy ngoài transaction hiện tại | Side effect/autocommit có thể không rollback |
| `MANDATORY` | Yêu cầu transaction hiện hữu | Fail ngay nếu proxy/wiring không thực sự mở transaction |

### Anti-pattern: transaction mới cho từng item

~~~java
// Mẫu nguy hiểm nếu service này được gọi trong chunk transaction.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void auditItem(Order order) {
    // Có thể commit audit trước khi chunk outer fail.
    jdbcTemplate.update("INSERT INTO app_audit ...");
}
~~~

Kết quả có thể là `app_audit` đã ghi nhưng orders chunk rollback, rồi retry lại ghi audit khác. Nếu audit bắt buộc đồng bộ cùng business commit, nên thiết kế cùng transaction hoặc transactional outbox theo yêu cầu.

### Một bẫy Spring AOP

~~~java
public void process(Order order) {
    saveInNewTransaction(order); // self-invocation trong cùng bean
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveInNewTransaction(Order order) {
    // Spring proxy thông thường không intercept
    // lời gọi nội bộ 'this.saveInNewTransaction(...)'.
}
~~~

Với Spring proxy-based AOP, self-invocation có thể bỏ qua `@Transactional`. Nếu trước và sau upgrade thay cấu hình proxy/bean composition, semantics có thể khác dự kiến. Tách method transactional thành service bean riêng được gọi qua proxy hoặc dùng `TransactionTemplate` có chủ đích, rồi kiểm thử commit/rollback.

### Connection pool starvation khi dùng REQUIRES_NEW

Nếu mỗi trong tám worker threads giữ một connection của outer transaction và cùng cần connection thứ hai cho `REQUIRES_NEW` từ **cùng pool max=8**, tất cả có thể chờ vô thời hạn đến checkout timeout. Tăng retry không sửa dependency này. Cần giảm nested transactions, bảo đảm pool headroom và đo Hikari `active/pending/usage`.

## 13. Transaction timeout và cấu hình isolation: migration phải đo DB thực

Có thể có nhiều mức isolation:

- `READ_COMMITTED`: mỗi statement đọc dữ liệu đã commit theo semantics DB.
- `REPEATABLE_READ`: snapshot/khả năng nhìn thấy dữ liệu trong transaction có thể khác `READ_COMMITTED`.
- `SERIALIZABLE`: DB có thể từ chối transaction cạnh tranh bằng serialization failure, đòi retry toàn bộ transaction theo policy.
- `DEFAULT`: để database/transaction manager xác định; không nên đoán chính xác nếu chưa đọc cấu hình DB.

Khi chuyển từ `DEFAULT` sang một mức explicit, ứng dụng có thể gặp nhiều retryable failures hơn hoặc có hành vi đọc khác trước đó.

### PostgreSQL: xem trạng thái backend khi có contention

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Trạng thái `idle in transaction` có thể giữ snapshot/locks dù session không chạy SQL; đừng đánh đồng `Hikari active` với PostgreSQL query đang dùng CPU.

### Hai loại timeout không giống nhau

Giả sử transaction timeout 30 giây, HTTP call bên trong processor có timeout 40 giây: nếu code vẫn giữ transaction/connection khi gọi HTTP, Step có thể không đạt SLA và rollback/commit behavior có thể rất khó đoán. Cần tách external I/O khỏi transaction quan trọng khi kiến trúc cho phép, dùng idempotency/outbox thay vì giữ lock xuyên network call.

### Đừng thay isolation để “sửa” restart

Nếu input source biến đổi trong khi reader đang paging/cursor, tăng isolation một cách tùy tiện không bảo đảm restart sau crash dùng cùng tập records. Cần **immutable snapshot hoặc stable watermark + deterministic ordering** cùng checkpoint semantics được kiểm chứng.

## 14. Cursor reader, paging reader và transaction connection lifetime

Với workload lớn, lựa chọn reader cũng ảnh hưởng transaction behavior:

| Reader | Mẫu hoạt động | Rủi ro khi nâng cấp |
| --- | --- | --- |
| `JdbcCursorItemReader` | Có thể giữ connection/cursor suốt Step `open() → close()` | Driver cursor holdability, autocommit/fetchSize, connection use/rollback |
| `JdbcPagingItemReader` | Query từng page, có sort key | Offset/keyset paging, snapshot drift, transaction visibility |
| File `ItemStreamReader` | Không dùng DB để đọc input | Checkpoint path/line count, file immutable |
| JPA reader | ORM/persistence context và transaction semantics | Flush/clear, lazy loads, connections và retry |
| Broker/HTTP reader | Resource bên ngoài JDBC transaction | ACK/replay, API consistency và backpressure |

### Cursor reader không phải một statement vô trạng thái

`JdbcCursorItemReader` thường mở connection riêng cho cursor; tùy `useSharedExtendedConnection` và proxy hỗ trợ, connection có thể liên quan chunk transaction theo cách khác. Nếu thay JDBC driver hoặc transaction manager, hãy test:

- Cursor có stream theo `fetchSize` và autocommit thực tế hay driver materialize toàn bộ result?
- Khi writer rollback, cursor position có được reset theo state/retry protocol đúng không?
- Khi chunk commit, cursor còn usable hay bị đóng bởi driver/server?
- Sau failover, reader mở lại từ checkpoint trên **cùng immutable snapshot** hay đọc live data đã đổi?
- Pool budget có đủ cho cursor connections dài hạn **và** writer transaction connections?

Không bật `useSharedExtendedConnection=true` chỉ để giảm số active connections mà chưa kiểm chứng driver/`ExtendedConnectionDataSourceProxy` và restart semantics.

### Paging cũng cần sort order duy nhất

Một sort key không unique có thể khiến các page trả record trùng/bỏ sót, đặc biệt khi DB isolation/config hoặc source data thay đổi. Với partitioning, chia range ổn định dựa trên snapshot/primary key và test restart sau lỗi ở page boundary.

## 15. Multi-threaded step: transaction theo chunk nhưng state có thể chia sẻ

Multi-threaded step cho phép nhiều chunks chạy đồng thời bằng `TaskExecutor`. Số transactions và số connections active có thể tăng cùng concurrency.

~~~mermaid
flowchart TD
    ST["One StepExecution"] --> CH1["Chunk thread A / tx A"]
    ST --> CH2["Chunk thread B / tx B"]
    ST --> CH3["Chunk thread C / tx C"]
    CH1 --> DB["Business DB"]
    CH2 --> DB
    CH3 --> DB
    ST --> JR["Shared StepExecution metadata"]
    CH1 --> S["Reader/writer shared state?"]
    CH2 --> S
    CH3 --> S
~~~

### Vì sao thay transaction manager có thể làm lỗi khó tái hiện?

- Nếu manager mới không quản lý writer datasource, chunk writes có thể autocommit dù step rollback.
- Nếu reader/writer shared object không thread-safe, các chunk có thể đọc/ghi trùng items.
- `@StepScope` gắn bean với StepExecution, **không tự tạo bean riêng cho mỗi thread** trong cùng Step.
- Một chunk xử lý chậm hoặc retry làm các chunks hoàn thành không theo thứ tự đọc.
- `ExecutionContext`/checkpoint của reader không đương nhiên biểu diễn tập đã commit khi các chunks hoàn thành lệch thứ tự.
- Metadata concurrency tăng có thể làm `JobRepository` lock/contention hoặc optimistic conflict xuất hiện.

### Tuning an toàn hơn

1. Baseline ở concurrency 1, đo business reconciliation.
2. Tăng 2 → 4 → 8 slots theo DB pool/lock capacity.
3. Inject lỗi ở một chunk, giữ chunk khác hoàn thành trước.
4. Kill JVM rồi restart cùng JobInstance.
5. Đối soát output unique keys/version và metadata checkpoint.
6. Nếu không bảo đảm thread safety/checkpoint, **partitioning** với `StepExecution` riêng có thể phù hợp hơn.
7. Không dùng `Thread.sleep` để “ép thứ tự” trong production; trong test dùng latches để điều khiển lịch chạy.

**Transaction per chunk không tạo exactly-once end-to-end** nếu reader index, input data hoặc external side effects không tuân contract.

## 16. Parallel steps: mỗi flow có transaction riêng, không có thứ tự bắt đầu mặc định

Với `split(TaskExecutor)`, các flows chạy đồng thời. Mỗi Step có transaction manager được cấu hình cho Step đó; các flows không được tự động gộp thành một transaction chung.

~~~mermaid
flowchart TD
    START["Job Start"] --> V["validateSnapshotStep"]
    V --> SPLIT["Split with TaskExecutor"]
    SPLIT --> A["loadCustomersStep / tx A"]
    SPLIT --> B["loadOrdersStep / tx B"]
    A --> JOIN["Join / barrier"]
    B --> JOIN
    JOIN --> REC["reconcileStep"]
    REC --> PUB["publishStep"]
~~~

Nếu `loadOrdersStep` cần output của `loadCustomersStep`, **không đặt chúng làm siblings độc lập** chỉ vì muốn song song hóa. Transaction commit của A không có nghĩa B sẽ đợi A xong. Cần biểu diễn dependency bằng flow graph hoặc readiness protocol.

### Nếu A commit còn B fail thì sao?

- A có thể đã commit nhiều chunks, và metadata A có thể `COMPLETED`.
- B có thể `FAILED` hoặc đã rollback chunk cuối.
- Một JobExecution cuối có thể thất bại; không nên publish tổng khi còn thiếu branch.
- Restart có thể bỏ qua step đã hoàn tất theo policy; nếu data của A đã bị purge, cần xác minh khả năng replay/rebuild.
- Một transaction của B rollback **không** rollback toàn bộ commits đã xảy ra ở A.

Vì thế, khi nâng cấp, test **partial-success** của parallel flows, restart và gate trước publication.

## 17. Local partitioning: transaction manager theo worker step, không theo manager step

Trong partitioning, manager chia input thành nhiều `ExecutionContext`, mỗi worker Step xử lý một range. Ví dụ Java 17/Spring Batch 5.x:

~~~java
import java.util.LinkedHashMap;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("rangePartitioner")
Partitioner rangePartitioner() {
    return gridSize -> {
        long[] bounds = {1, 1001, 2001, 3001, 4001};
        var result = new LinkedHashMap<String, ExecutionContext>();

        for (int i = 0; i < bounds.length - 1; i++) {
            var context = new ExecutionContext();
            context.putString("snapshotId", "fixed-test-snapshot");
            context.putLong("startInclusive", bounds[i]);
            context.putLong("endExclusive", bounds[i + 1]);
            result.put("partition" + i, context);
        }
        return result;
    };
}

@Bean("partitionExecutor")
ThreadPoolTaskExecutor partitionExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(4);
    executor.setThreadNamePrefix("part-worker-");
    executor.initialize();
    return executor;
}

@Bean("partitionManagerStep")
Step partitionManagerStep(
        JobRepository repository,
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("rangePartitioner") Partitioner partitioner,
        @Qualifier("partitionExecutor")
            ThreadPoolTaskExecutor executor) {

    return new StepBuilder("partitionManagerStep", repository)
            .partitioner("workerStep", partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(executor)
            .build();
}
~~~

Đây là **ví dụ cấu trúc local partitioning**. `workerStep` phải được cấu hình với **business transaction manager đúng** như mục 4, và `snapshotId`/ranges phải được persist/tái sử dụng ổn định qua restart; `rangePartitioner` cố định ở đây chỉ để minh họa, không phải manifest producer production.

### Thứ cần test

- Mỗi partition có `StepExecution` và checkpoint riêng.
- Các chunks của từng worker sử dụng đúng transaction manager.
- Không có các range bị chồng/thiếu hoặc bị thay khi restart.
- Manager nhận và aggregate statuses đúng, không tự publish khi một worker `FAILED`.
- Connection pool đủ cho concurrent cursor readers và writers, nhưng không tăng max vượt DB capacity.
- Một partition đã commit output rồi mất reply phải có replay-safe business key.
- `gridSize` là tham số thiết kế partitioning, không được mặc định là số threads thực tế ở remote architecture.

## 18. Remote partitioning: không có một transaction bao trùm tất cả workers

Một manager có thể dispatch nhiều `StepExecution` qua broker đến các JVM. Mỗi worker sử dụng transaction manager, datasource, driver và code **của chính JVM đó**.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Middleware
    participant A as Worker A vOld
    participant B as Worker B vNew
    participant D as Business DB
    participant R as JobRepository
    M->>Q: Dispatch step execution 501
    Q->>A: Deliver 501
    A->>D: Commit chunk N
    A->>R: Update metadata
    Note over A,M: Reply bị mất
    Q->>B: Redelivery 501
    B->>R: Reload execution state
    R-->>B: Latest status/version/context
    B->>M: Ownership/recovery decision needed
~~~

**Không có transaction DB duy nhất** bao phủ manager + broker + worker A/B + repository một cách tự nhiên. Khi nâng cấp rolling, old và new workers có thể đồng thời tồn tại; nếu chúng dùng transaction isolation hoặc schema serializer khác nhau, một redelivery có thể có semantics khác mong đợi.

### Fencing và idempotency

- Manager phải bảo đảm cùng một partition không có hai owners đang ghi ngoài kiểm soát.
- Worker mới phải reload metadata và tuân cơ chế takeover; message cũ không phải nguồn sự thật duy nhất.
- `BATCH_STEP_EXECUTION.VERSION` giúp phát hiện một số metadata update stale, **không** chặn worker cũ gọi external API hoặc commit database khác.
- Khi thay đổi transaction behavior, thêm test **split-brain, lost reply và duplicate delivery**.
- Với side effect quan trọng, dùng owner generation/lease được **đích ghi** kiểm tra hoặc cô lập owner cũ trước khi redispatch.

## 19. Remote chunking: broker ACK không là business commit hay checkpoint

Trong remote chunking, manager thường sở hữu reader/chunk metadata, worker thực hiện xử lý/ghi items và trả reply.

~~~text
Manager đọc chunk K
    -> publish request K
Worker nhận request K
    -> business write/commit
    -> reply K
Manager nhận reply
    -> tiếp tục checkpoint/dispatch
~~~

Nếu reply mất, manager/broker có thể gửi lại chunk K dù worker đã commit. Đổi transaction manager ở worker hoặc đổi broker ACK policy khi nâng cấp có thể tạo **new failure window**.

### Ma trận ranh giới

| Điểm lỗi | Có thể đã xảy ra | Cần chứng minh |
| --- | --- | --- |
| Trước worker business commit | Request có thể retry | Không bỏ sót items |
| Sau business commit, trước reply | Output đã có nhưng manager chưa biết | Idempotent replay |
| Sau reply, trước durable manager checkpoint | Manager có thể đọc lại chunk | Replay-safe và correlation |
| Broker redelivery khi worker cũ còn xử lý | Hai workers cùng cố ghi | Dedup/ownership |
| Manager restart dùng serializer mới | Reply/request cũ có thể còn trong queue | Contract compatibility |

Spring Batch chunk retry trong worker **khác** broker delivery retry/redispatch và whole-job restart. Một `retryLimit(4)` của step không tự điều khiển message redelivery count.

### Đừng lồng retry vô hạn

Nếu worker retry JDBC, HTTP client retry riêng, broker redeliver và scheduler restart toàn job, số attempts có thể bị nhân lên. Đặt tổng retry budget, backoff/jitter, DLQ/replay protocol và business idempotency.

## 20. Tương thích metadata schema và ExecutionContext serialization

Khi nâng cấp phiên bản, không chỉ code builder thay đổi. **JobRepository metadata schema** và cách mã hóa `ExecutionContext`/`JobParameters` có thể khác giữa các dòng phiên bản.

### Trục cần xem xét

| Thành phần | Câu hỏi trước migration |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Identifying JobParameters vẫn cho cùng logical identity không? |
| `BATCH_JOB_EXECUTION_PARAMS` | Schema và cách lưu parameter type/value có đúng DDL target? |
| `BATCH_STEP_EXECUTION` | Counters/status/version đọc được và migration script có tương thích không? |
| `BATCH_*_EXECUTION_CONTEXT` | Serializer/deserializer mới đọc được context cũ không? |
| Custom `ExecutionContextSerializer` | Có support object types cũ và new Java/Jakarta changes không? |
| Job/Step names | Tên/flow graph có ổn định cho restart từ execution cũ không? |
| Reader state keys | Name + checkpoint keys còn được hiểu cùng ngữ nghĩa không? |
| Batch DB transaction semantics | Schema migrations có lock/DDL ảnh hưởng active execution không? |

Spring Batch 5.x có thay đổi quan trọng về định dạng metadata và cách xử lý job parameters so với 4.x. Tuy nhiên, **không được tự phát biểu rằng mọi serializer và mọi persisted context đều tự động migrate được**. Luôn dùng migration scripts chính thức **cho phiên bản nguồn/đích chính xác**, kèm fixture đọc lại metadata của job cũ.

### Bẫy khi restart sau upgrade

Giả sử `JdbcCursorItemReader` lưu state theo key dựa trên tên reader. Khi refactor đổi bean/item stream name, reader mới có thể không đọc được checkpoint cũ, dẫn tới restart từ đầu hoặc failure. Khi đó transaction behavior có vẻ “đổi” dù nguyên nhân chính là **state compatibility**.

**Không sửa trực tiếp `BATCH_*` hoặc xóa checkpoint để ép job chạy.** Nếu cần data migration, làm ở window có kiểm soát, backup, rollback plan và test với bản metadata đã copy sang staging.

## 21. Contract tests trước/sau upgrade: chọn oracle đúng

Một migration test không nên hỏi “Step đã COMPLETED?” rồi dừng. Phải mô tả **transaction contract** độc lập với implementation.

### Các bất biến chính

| Bất biến | Tiêu chí PASS |
| --- | --- |
| **Atomicity cùng resource** | Khi writer ném exception trong chunk, không có business rows của chunk đó bị commit |
| **Progress đúng sau commit** | Checkpoint chỉ tương ứng phần việc đã commit và có thể phục hồi |
| **Retry có giới hạn** | Exception transient được retry đúng policy, không nuốt lỗi fatal |
| **Failure rõ ràng** | Khi không thể tiếp tục, Step/Job không báo COMPLETED giả |
| **No duplicate effect** | Crash rồi replay không tạo duplicate business operation |
| **Isolation dữ liệu** | Mỗi partition/StepExecution giữ input range và state riêng |
| **Metadata compatibility** | Phiên bản mới đọc đúng execution history/context từ fixture phiên bản cũ |
| **JobInstance identity** | Cùng identifying parameters vẫn định danh cùng logical job theo contract |
| **Bounded resources** | Không tăng JDBC pool/lock waits vượt quota khi số worker tăng |
| **Deterministic result** | Không phụ thuộc thứ tự hoàn thành của parallel steps |
| **Rollback deployment** | Phiên bản cũ chỉ được chạy lại khi schema/serializer còn tương thích và đã có kế hoạch |

### So sánh bằng business output, không bằng timestamps

Một test có thể đối chiếu hai snapshot input cùng logical content nhưng chạy bằng hai release binaries:

~~~text
Release old:
  input snapshot S
  expected output keys K
  end-state business rows O_old

Release candidate:
  cùng snapshot logic S (fixture tách biệt)
  output keys K
  end-state business rows O_new

PASS khi:
  O_new == O_old theo business equality
  metadata/restart invariant đạt
  failure/retry behavior được chấp nhận
~~~

Không yêu cầu cùng một giá trị `JOB_EXECUTION_ID`/timestamp qua hai test databases: sequence và scheduling có thể khác hợp lệ. So **business keys, payload/version, trạng thái sau fault injection** và metrics tương đối.

## 22. Java 17 + JUnit 5: kiểm thử transaction manager có rollback đúng DataSource

Trước khi thử một job lớn, kiểm chứng **writer dùng đúng manager** bằng một integration test rất nhỏ trên database ứng dụng. Dùng PostgreSQL test hoặc Testcontainers, với bảng application-owned:

~~~sql
CREATE TABLE app_tx_probe (
    run_id VARCHAR(100) PRIMARY KEY,
    payload TEXT NOT NULL
);
~~~

### Test cho rollback trên business DB

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class BusinessTransactionWiringIT {

    @Autowired
    @Qualifier("businessTransactionManager")
    PlatformTransactionManager businessTx;

    @Autowired
    @Qualifier("businessJdbcTemplate")
    JdbcTemplate businessJdbc;

    @Test
    void mustRollbackBusinessWriteOnRuntimeFailure() {
        String runId = UUID.randomUUID().toString();
        var tx = new TransactionTemplate(businessTx);

        assertThrows(IllegalStateException.class, () ->
                tx.execute(status -> {
                    businessJdbc.update(
                            "INSERT INTO app_tx_probe(run_id, payload) " +
                            "VALUES (?, ?)",
                            runId, "synthetic-test");
                    throw new IllegalStateException(
                            "Injected failure before commit");
                }));

        Integer committedRows = businessJdbc.queryForObject(
                "SELECT COUNT(*) FROM app_tx_probe WHERE run_id = ?",
                Integer.class, runId);

        assertEquals(0, committedRows);
    }

    @Test
    void rollbackOnlyMustNotLeaveBusinessRows() {
        String runId = UUID.randomUUID().toString();
        var tx = new TransactionTemplate(businessTx);

        tx.execute(status -> {
            businessJdbc.update(
                    "INSERT INTO app_tx_probe(run_id, payload) " +
                    "VALUES (?, ?)",
                    runId, "synthetic-test");
            status.setRollbackOnly();
            return null;
        });

        Integer committedRows = businessJdbc.queryForObject(
                "SELECT COUNT(*) FROM app_tx_probe WHERE run_id = ?",
                Integer.class, runId);

        assertEquals(0, committedRows);
    }
}
~~~

**Điều kiện của test:**

- `businessJdbcTemplate` phải dùng **cùng DataSource** mà `businessTransactionManager` quản lý. Nếu dùng JDBC với `DataSourceTransactionManager`, template sẽ tham gia transaction nhờ cơ chế tài nguyên thread-bound của Spring.
- Không đặt `@Transactional` trên toàn test method để tránh test framework rollback che giấu trạng thái commit.
- Các bảng application được tạo qua migrations/test setup; **không sửa `BATCH_*`**.
- Bài test này chứng minh transaction manager cho **một DataSource** hoạt động, **chưa chứng minh** `StepBuilder` đã được inject đúng manager. Phải có Step-level integration tests bên dưới.
- Khi ứng dụng dùng JPA, connection proxy hoặc datasource routing, kiểm tra manager-specific behavior thay vì chép ví dụ JDBC một cách máy móc.

### Negative test phát hiện manager bị chọn nhầm

Ở test configuration riêng, cố tình đưa `TransactionTemplate` của **repository DataSource** quanh insert dùng `businessJdbcTemplate` của resource khác. Test yêu cầu rollback business row; nếu row vẫn tồn tại, chứng tỏ hai resources không chia một local transaction như mong đợi.

Đây là **test trên database cô lập** để chứng minh wiring, không phải khuyến nghị intentionally chọn sai manager trong production.

## 23. Spring Batch integration test: thất bại giữa chunk phải không commit sai

Test wiring ở mục 22 mới là tầng JDBC. Cần chạy **Step thật** qua `JobLauncher`/`JobLauncherTestUtils` và `JdbcJobRepository` để kiểm chứng behavior khi migrate.

Ví dụ skeleton Spring Batch 5.x:

~~~sql
-- Các bảng application-owned của riêng môi trường test.
CREATE TABLE app_tx_input (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);

CREATE TABLE app_tx_output (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest
class ChunkRollbackCompatibilityIT {

    @Autowired JobLauncherTestUtils launcher;
    @Autowired JdbcTemplate businessJdbc;

    @Test
    void failingWriterMustNotCommitUnfinishedChunk()
            throws Exception {

        String snapshotId =
                "test-snapshot-" + UUID.randomUUID();

        // Fixture tạo synthetic input và bảng output
        // trong database test trước khi launch.
        prepareSnapshotFixture(snapshotId);

        JobExecution result = launcher.launchStep(
                "rollbackProbeStep",
                new JobParametersBuilder()
                    .addString("snapshotId", snapshotId, true)
                    .toJobParameters());

        // rollbackProbeStep được định nghĩa trong test config:
        // writer insert vào app_tx_output rồi cố ý ném
        // IllegalStateException trong cùng chunk transaction.
        assertEquals(BatchStatus.FAILED, result.getStatus());

        Integer persisted = businessJdbc.queryForObject(
                "SELECT COUNT(*) FROM app_tx_output " +
                "WHERE snapshot_id = ?",
                Integer.class, snapshotId);

        assertEquals(0, persisted);
    }

    private void prepareSnapshotFixture(String snapshotId) {
        // Đảm bảo fixture đã commit trước khi launchStep().
        businessJdbc.update(
                "INSERT INTO app_tx_input(snapshot_id, order_id, payload) " +
                "VALUES (?, ?, ?)",
                snapshotId, 42L, "synthetic-input");
    }
}
~~~

Đây là **skeleton có chủ đích**: ứng dụng test phải khai báo `rollbackProbeStep` đọc `app_tx_input`, writer insert `app_tx_output` rồi cố ý ném exception **trong cùng chunk transaction**. Cần bảo đảm `JobLauncherTestUtils` được gắn với đúng job khi context có nhiều Job beans. Không chạy chỉ mỗi class test rồi kết luận framework bị lỗi; phải lắp ráp các test beans đã mô tả và chỉ dùng database cô lập.

### Các assertion cần bổ sung cho Step-level test

- Writer được gọi, đã cố insert dữ liệu trong transaction và ném lỗi **sau insert**, không fail từ fixture trước khi Step start.
- `StepExecution` cuối có `FAILED`; database output của unfinished chunk không còn.
- `JobRepository` còn metadata hợp lệ để kiểm tra restart.
- Khi sửa writer để thành công và **restart cùng JobInstance**, output đúng một bản ghi mỗi business key.
- Với skip/retry được bật, phân biệt lỗi intentionally fatal với transient đã hết attempts.
- Nếu business và repository ở hai databases, kỳ vọng atomicity phải thiết kế theo contract thực; không dùng assertion “cùng rollback” khi kiến trúc cố tình không có distributed transaction.

### Failure windows cần thử riêng

| Injection | Khi dùng cùng local resource | Khi dùng hai resources |
| --- | --- | --- |
| Writer ném lỗi trước commit | Thường rollback business chunk | Business tx phải rollback theo manager đúng |
| Business commit hoàn tất, repository ghi checkpoint lỗi | Cửa sổ có thể thu hẹp khi cùng transaction | Có thể replay chunk đã commit |
| Worker crash ngay sau commit | Reload last durable state | Kiểm tra checkpoint/UPSERT và side effects |
| Retry hết attempts | Step phải fail hoặc theo skip policy | Đồng thời kiểm tra business output đã commit từ attempts trước |
| Process restart đổi reader state keys | Phải load checkpoint hợp lệ | Không được “reset offset” im lặng |

## 24. Test concurrency bằng barrier, không dựa vào Thread.sleep

Sau nâng cấp, transaction manager/isolation mới có thể làm hai chunks hoặc partitions chạm lock ở thời điểm khác. Để tái hiện một race có kiểm soát, dùng `CountDownLatch`.

### Mẫu test hai writer cùng business key

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class ConcurrentWriteCompatibilityIT {

    @Autowired JdbcTemplate businessJdbc;
    @Autowired PlatformTransactionManager businessTransactionManager;

    @Test
    void concurrentUpsertsKeepOneUniqueBusinessRow()
            throws Exception {

        String snapshotId = UUID.randomUUID().toString();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(2);

        try {
            var a = executor.submit(() ->
                    upsert(snapshotId, "same-payload", ready, start));
            var b = executor.submit(() ->
                    upsert(snapshotId, "same-payload", ready, start));

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();
            a.get(15, TimeUnit.SECONDS);
            b.get(15, TimeUnit.SECONDS);
        } finally {
            start.countDown();
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(
                    10, TimeUnit.SECONDS));
        }

        Integer count = businessJdbc.queryForObject(
                "SELECT COUNT(*) FROM app_order_result " +
                "WHERE snapshot_id = ? AND order_id = ?",
                Integer.class, snapshotId, 42L);

        assertEquals(1, count);
    }

    private void upsert(
            String snapshotId, String payload,
            CountDownLatch ready, CountDownLatch start) {

        ready.countDown();
        try {
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Gate timeout");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }

        var template = new TransactionTemplate(
                businessTransactionManager);

        template.execute(status -> {
            businessJdbc.update(
                    "INSERT INTO app_order_result(" +
                    "snapshot_id, order_id, source_version, payload) " +
                    "VALUES (?, ?, ?, ?) " +
                    "ON CONFLICT(snapshot_id, order_id) DO UPDATE " +
                    "SET payload = EXCLUDED.payload",
                    snapshotId, 42L, 1L, payload);
            return null;
        });
    }
}
~~~

**Chuẩn bị:** test database phải có `app_order_result` như mục 11. Nếu ứng dụng có nhiều managers, dùng `@Qualifier` thay vì autowire không phân biệt như skeleton. Hai payload giống nhau vì test chỉ nhắm tới **idempotency replay**; muốn kiểm tra conflict resolution khi payload khác nhau, tạo test riêng với version/ownership semantics rõ.

### Test mở rộng khi upgrade transaction behavior

1. Cho thread A giữ row lock trong một **test transaction có kiểm soát**, thread B cố ghi cùng row; quan sát SQLSTATE và rollback.
2. Đảo vai A/B, không giả định một worker luôn thắng.
3. Đưa commit thành công vào một branch, branch khác fail; assert downstream publication không chạy trước barrier/reconciliation.
4. Giữ một chunk trước commit, cho chunk khác hoàn thành; kill process rồi kiểm tra checkpoint.
5. Với remote worker, tạo duplicate delivery của cùng `StepExecutionId` và xác minh owner/fencing.
6. Đối chiếu pool/DB lock waits, không chỉ latency của test runner.

Không sử dụng `Thread.sleep(200)` để “tạo lock race”; sleep không đảm bảo scheduler/connection timing và làm CI flaky.

## 25. Migration và rolling deployment: trình tự an toàn

Khi transaction behavior hoặc metadata schema có thể thay đổi, deployment phải có kế hoạch **nhất quán giữa old/new binaries và active executions**.

~~~mermaid
flowchart TD
    A["Inventory version + transaction wiring"] --> B["Migration dry-run on copied metadata"]
    B --> C["Golden contract + fault tests"]
    C --> D["Quiesce/stop active jobs where required"]
    D --> E["Backup + supported schema migration"]
    E --> F["Deploy manager/workers per compatibility plan"]
    F --> G["Canary + business reconciliation"]
    G --> H{"Metrics + restart tests PASS?"}
    H -->|"Có"| I["Controlled scale-out"]
    H -->|"Không"| J["Stop dispatch, recover/rollback plan"]
~~~

### Giai đoạn 1: inventory

- Lập danh sách mọi `DataSource` và `PlatformTransactionManager` trên manager/worker.
- Ghi tên bean được StepBuilder inject, transaction attributes, retry/skip rules và timeout settings.
- Kiểm tra source/target/JDBC repository có dùng chung DB/transaction manager hay không.
- Lưu version matrix: Java, Spring Boot, Spring Batch, Retry, JDBC driver, DB và broker.
- Lập danh sách **job đang STARTED**, queued/leased partitions, broker unacked/retry/DLQ và persisted context serializer.

### Giai đoạn 2: rehearsal

- Copy metadata/data test theo policy an toàn; **không sử dụng credentials production** trong fixture.
- Chạy DDL migration được hỗ trợ cho đúng version nguồn→đích.
- Cho candidate binary reload một JobExecution cũ có checkpoint và resume trên snapshot test.
- Test lỗi sau business commit/trước metadata persist, duplicate delivery và rollback.
- Đo JobRepository write latency và throughput trước/sau.
- Chuẩn bị rollback đối với **cả schema lẫn binary**; không mặc định downgrade sau migration là khả thi.

### Giai đoạn 3: triển khai

- Với migration phá compatibility, **dừng dispatch và đưa active jobs về trạng thái an toàn** trước khi đổi schema.
- Xác minh manager và workers cũ thực sự dừng hoặc bị fenced; không chạy lẫn old/new khi metadata/message contract không tương thích.
- Backup metadata và theo dõi pending broker messages; không xóa queue để “làm sạch” trước deploy.
- Deploy theo nhóm tương thích đã xác minh. Có thể rolling khi **đã chứng minh** old/new hỗ trợ cùng schema và execution state; không phải mặc định.
- Canary trên snapshot đã biết expected output và kiểm tra restart, không chỉ happy-path.
- Chỉ tăng concurrency khi DB pool/lock metrics và business goodput đạt.

### Giai đoạn 4: rollback

Nếu candidate phát hiện migration phá restart compatibility:

1. Ngừng dispatch/chạy new work ngay theo quy trình.
2. Xác minh không còn workers cũ/new cùng cập nhật execution.
3. Xác định metadata schema/serializer đã được ghi theo format nào.
4. **Không** trỏ binary cũ vào schema mới nếu rollback compatibility chưa được chứng minh.
5. Dùng bản backup/forward-fix migration được thử nghiệm, đối soát data đã commit trong cửa sổ upgrade.
6. Tiếp tục xử lý cùng JobInstance/snapshot khi có thể; tránh tạo JobInstance mới vô ý.
7. Đánh giá business side effects đã xảy ra trước khi restore metadata để tránh replay nhân đôi.

## 26. Observability: phân biệt lỗi transaction với lỗi capacity

Theo dõi trước và sau upgrade trên **cùng workload**:

| Nhóm | Tín hiệu | Chẩn đoán |
| --- | --- | --- |
| Chunk | commit/rollback counts, chunk duration p95 | Transaction lâu hơn hoặc retry nhiều? |
| Metadata | `BATCH_STEP_EXECUTION.VERSION`, status, update latency | Concurrent stale writers hay repository bottleneck? |
| JDBC pool | Hikari active/idle/pending/max, acquire latency | Writer/reader đang chờ pool? |
| Database | lock waits, deadlocks, transaction age, IO/CPU | Thay isolation/connection strategy gây contention? |
| Retry | attempts, exhausted, backoff, skip count | Exception mapping sau upgrade khác? |
| Worker | concurrency slots, queue, partition skew | Tăng workers làm DB overload? |
| Recovery | restart success, RTO, checkpoint replay length | Metadata/serializer và transaction có tương thích? |
| Business | unique committed items/s, missing/extra keys | Goodput/correctness, không phải attempts/s |
| Broker | unacked, redelivery, DLQ, reply latency | Remote commit/ACK có mismatch không? |

### SQL PostgreSQL để kiểm tra transaction wait

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    left(query, 120) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start NULLS LAST;
~~~

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

Chỉ dùng quyền giám sát phù hợp, tránh log raw SQL có thông tin nhạy cảm. Dữ liệu từ `pg_stat_activity` là snapshot; một phiên `state='active'` có thể đang **đợi lock**, không nhất thiết sử dụng CPU.

### Đừng chỉ nhìn “giảm exceptions”

Một bản nâng cấp có thể giảm số exception vì đổi rollback/retry behavior, trong khi unique committed items/s giảm hoặc dữ liệu thiếu. **SLO đúng bao gồm outcome nghiệp vụ và recovery**, không chỉ số lần attempt thành công.

## 27. Ma trận fault injection khi transaction behavior có nguy cơ thay đổi

Một migration test tốt không chỉ chạy happy path trên một thread. Cần tái hiện **nhiều trạng thái trước và sau commit**, cùng các lịch chạy khác nhau.

| Kịch bản | Cách tạo lỗi ở test/staging | Kết quả mong đợi |
| --- | --- | --- |
| Writer ném exception trước commit | Insert synthetic row rồi throw trong chunk | Same-resource transaction rollback, không còn row |
| Writer lỗi sau vài chunk hoàn tất | Fail ở chunk N, chunks 1..N-1 đã commit | Restart không nhân đôi/không bỏ sót |
| Reader throw giữa chunk | Test reader có state kiểm soát | Retry/skip và checkpoint đúng theo policy |
| Processor có ngoại lệ fatal | Ném lỗi validation | Fail/skip đúng, không phát side effect mù |
| SQL deadlock/serialization | Tạo lock/concurrent update trong DB test | Rollback, retry có giới hạn/backoff, không silent overwrite |
| Wrong transaction manager | Test config dùng repo manager cho business JDBC | Negative test phát hiện business rollback không như contract |
| `REQUIRES_NEW` commit rồi outer fail | Audit service gọi inner tx, outer throw | Test phân biệt commit độc lập; sửa nếu không chấp nhận |
| JDBC connection timeout | Hạ pool max và tạo concurrent checkout | Không mất state, có metrics/feedback rõ |
| Database socket timeout | Proxy/ngắt network đúng failure window | Không giả định remote commit chưa xảy ra |
| Business commit rồi metadata fail | Hai DB/resources, inject repository outage | Replay idempotent và reconciliation PASS |
| Context serializer không đọc state cũ | Persist fixture với version trước upgrade | Fail/migrate có kiểm soát, không reset offset |
| Hai launch cùng identifying params | Barrier trước JobLauncher | Không có hai active owners cùng instance |
| Parallel step A complete, B failed | Đưa lỗi trong flow B | Không publish downstream output thiếu |
| Multi-threaded chunk finish đảo thứ tự | Latch giữa process/write | Checkpoint/restart không bỏ sót item |
| Remote partition reply mất | Drop reply khi worker đã commit | Manager reload state, owner/fencing đúng |
| Remote chunk reply mất | Worker commit rồi broker redeliver | Duplicate delivery không nhân double effect |
| Worker cũ vẫn sống khi failover | Cắt control plane, giữ DB path | Không cho hai owners ghi cùng partition không kiểm soát |
| Rolling schema migration có job active | Rehearsal trong copy staging | Chặn upgrade phá active execution/serialization |
| Rollback binary sau schema update | Test binary cũ đọc schema mới | Chỉ rollback khi đã chứng minh tương thích |
| Autoscaling làm DB nghẽn | Tăng worker replicas trên DB test | Bounded throughput, rollback/lock waits được giám sát |
| Business output bị sai có chủ đích | Chèn missing/extra/wrong-version records | Reconciliation FAIL dù JobExecution COMPLETED |

### Kiểm thử không dùng dữ liệu sản xuất

- Dùng database test/Testcontainers và snapshot synthetic **đúng shape**, không sao chép credentials thật.
- Với lỗi transaction, tiêm thất bại qua application-owned DAO/proxy/fixture. Không sửa trực tiếp `BATCH_*` đang được Spring Batch quản lý để tạo kết quả mong muốn.
- Dùng `CountDownLatch`/barriers và controlled executors thay vì `Thread.sleep` để canh lịch chạy.
- Giữ timeout của test hữu hạn; cleanup worker/session sau mỗi phép thử.
- Kiểm tra cả exception class, SQLSTATE, rollback, `StepExecution` status, repository context và business output.
- Chạy cùng suite trên **release đang hoạt động** và **release định nâng cấp**, cùng DB vendor/driver/isolation cấu hình thật.
- Khi kết quả khác, phân loại **intentional behavior change** với **regression**; cập nhật contract/spec nếu nghiệp vụ thật sự cho phép thay đổi.

### SQL đối soát theo key và version

Giả sử input/output do ứng dụng sở hữu có snapshot, order ID và source version:

~~~sql
-- Các business keys cần có nhưng output chưa có.
SELECT order_id
FROM app_input_snapshot
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT order_id
FROM app_order_result
WHERE snapshot_id = :snapshotId;
~~~

~~~sql
-- Những output keys không có trong input snapshot.
SELECT order_id
FROM app_order_result
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT order_id
FROM app_input_snapshot
WHERE snapshot_id = :snapshotId;
~~~

~~~sql
-- Key đúng nhưng source version/payload sai.
SELECT i.order_id
FROM app_input_snapshot i
JOIN app_order_result o
  ON o.snapshot_id = i.snapshot_id
 AND o.order_id = i.order_id
WHERE i.snapshot_id = :snapshotId
  AND (
      i.source_version IS DISTINCT FROM o.source_version
      OR i.payload IS DISTINCT FROM o.payload
  );
~~~

Kỳ vọng **0 hàng** khi business contract là copy nguyên dữ liệu. Với transform/filter, phải tính expected output theo rule thực. Hai tập có cùng count vẫn có thể khác keys; vì vậy không chỉ so `COUNT(*)`.

## 28. Runbook khi nâng cấp làm thay đổi commit/rollback/restart

Nếu sau deploy xuất hiện `UnexpectedRollbackException`, rollback count tăng, job fail khác trước, hoặc output sai dù status COMPLETED:

1. **Đóng băng phạm vi:** xác định release, Java/Boot/Batch/driver/DB version và thời điểm thay đổi.
2. **Khoanh JobInstance/JobExecution/StepExecution:** input snapshot, identifying parameters, partition map và tên Step.
3. **Kiểm tra việc cùng một job có nhiều owner** trước khi thao tác restart.
4. **So sánh transaction wiring thực tế:** bean nào inject vào `chunk(...,txManager)`/`tasklet(...,txManager)`; các JDBC/JPA/HTTP writers dùng datasource nào?
5. **Xác định resource boundary:** repository + business cùng local transaction hay hai independent resources?
6. **Kiểm tra propagation/isolation/timeout:** có `REQUIRES_NEW`, self-invocation, DB isolation đổi hoặc rollback-only flag?
7. **Đọc metadata bằng SELECT:** statuses, `VERSION`, counters, checkpoint existence; không sửa bảng `BATCH_*`.
8. **Đối chiếu DB activity:** SQLSTATE, lock waits, transaction age, connection pool pending/timeout và driver behavior.
9. **Tìm commit uncertain windows:** business DB có thể đã commit khi repository/broker báo lỗi hay không?
10. **Kiểm tra serialization/schema:** candidate có đọc context cũ không; name/keys của reader có đổi không?
11. **Tạm dừng publish/dispatch** nếu còn thiếu dữ liệu hoặc hai owner; không tạo một JobInstance mới chỉ để bỏ qua lỗi.
12. **Khôi phục theo policy đã thử nghiệm:** restart cùng identifying params khi hợp lệ, giữ snapshot/manifest và writer idempotent.
13. **Nếu cần rollback deployment:** xác minh schema/metadata compatibility với binary cũ trước khi chạy; cân nhắc forward-fix thay vì downgrade không hỗ trợ.
14. **Chạy lại contract/fault tests** trên staging hoặc canary với chính cấu hình đang vận hành.
15. **Đối soát business output và side effects**, rồi mới cho phép downstream publication.
16. **Ghi root cause**: thay đổi API/wiring, dependency mapping, transaction propagation, checkpoint codec, concurrency ownership hay downstream commit/ACK.

### Các thao tác nguy hiểm cần tránh

- Tự cập nhật `BATCH_STEP_EXECUTION.VERSION`, `STATUS` hoặc serialized `ExecutionContext` để ép job restart.
- Xóa repository metadata vì nghĩ “transaction cũ bị kẹt”.
- Đổi identifying `run.id` để tạo JobInstance khác trong lúc job cũ còn active.
- Coi `JobExecution.getStatus()==COMPLETED` là đủ cho correctness.
- Tắt retry/rollback checks chỉ để đạt throughput cũ.
- Tăng `maximumPoolSize`/worker count khi DB lock waits đã bão hòa.
- Giả định restore DB backup không ảnh hưởng business output đã commit sau thời điểm backup.
- Cho manager/worker old và new cùng xử lý một StepExecution khi message/schema/transaction contract chưa tương thích.

## 29. Bài tập tình huống: nâng cấp import 12 triệu orders

Một công ty có job `importOrders`:

~~~text
Before:
  Java: 11
  Spring Batch: 4.x
  Repo DB and business DB: same PostgreSQL resource
  Chunk size: 200
  Worker concurrency: 4 local partitions

After:
  Java: 17
  Spring Batch: 5.x
  Repo DataSource separated from business DataSource
  Worker concurrency: 16 partitions
  Chunk size: 500

Observed:
  WriteCount increases quickly
  PostgreSQL lock waits increase
  JobRepository pending JDBC connections > 0
  A worker crashed after a chunk business commit
  Restart replayed some records and sent duplicate emails
~~~

Một thành viên đề xuất “chỉ tăng `connectionTimeout` lên 120 giây và retry mọi `SQLException` 20 lần”. Một người khác đề xuất rollback binary về version cũ trên **cùng schema metadata vừa migrate**.

**Câu hỏi:**

1. Có bao nhiêu biến thay đổi cùng lúc khiến việc phân tích nguyên nhân khó?
2. Vì sao `StepBuilder` 5.x cần kiểm tra transaction manager tường minh?
3. Tách repository/business DataSource có tự tạo transaction nguyên tử giữa hai DB không?
4. Nếu business output commit nhưng metadata không update, điều gì xảy ra khi restart?
5. Vì sao tăng chunk size 200→500 có thể ảnh hưởng lock wait và replay cost?
6. Tăng concurrency 4→16 có thể làm DB chậm dù CPU chưa cao không?
7. Vì sao `WriteCount` tăng không chứng minh unique commits/s tăng?
8. `REQUIRES_NEW` trong writer audit có thể làm điều gì nếu outer chunk rollback?
9. Chuyển sang `SERIALIZABLE` từ `READ_COMMITTED` có thể cần điều chỉnh retry nào?
10. Có thể dùng một transaction DB để rollback email đã gửi không?
11. Có nên đổi `run.id` để job chạy lại từ đầu nhằm né lỗi checkpoint?
12. Vì sao rollback binary cũ trên schema mới nguy hiểm?
13. Hãy đề xuất ba test bắt buộc **trước** khi cho 16 partitions chạy production.
14. Những metrics nào cho biết nút thắt do repository hay business DB?
15. Chọn một hướng xử lý an toàn hơn so với hai đề xuất “tăng timeout” và “downgrade ngay”.

### Gợi ý đáp án

- **(1)** Ít nhất Java, Spring Batch/API wiring, tách resource/transaction manager, concurrency, chunk size, có thể cả Boot/driver/schema serializer. Cần tách từng biến trong rehearsal.
- **(2)** Để bảo đảm chunk writer dùng manager quản lý đúng datasource; repository manager không tự thay thế được business manager.
- **(3)** Không. Hai local transaction managers độc lập không tạo atomicity cross-DB.
- **(4)** Last durable checkpoint có thể cũ, chunk bị replay; writer phải idempotent, external side effects có dedup/ledger.
- **(5)** Transaction dài hơn, lock giữ lâu, nhiều items in-flight/chưa checkpoint; ảnh hưởng DB contention và restart.
- **(6)** Có. Lock, I/O, session/connection contention có thể là bottleneck dù CPU còn rảnh.
- **(7)** `WRITE_COUNT` ghi hoạt động batch theo semantics framework, không đếm duy nhất các bản ghi mới sau UPSERT/retry.
- **(8)** Inner tx có thể commit audit độc lập rồi outer rollback, gây sai lệch hoặc duplicate khi retry.
- **(9)** Serialization failures cần rollback/retry **toàn transaction hợp lệ** theo policy hữu hạn và phân loại SQLSTATE.
- **(10)** Không. Email/API bên ngoài không tự nằm trong local JDBC transaction; dùng outbox/idempotency/reconciliation.
- **(11)** Không. Identifying parameters mới tạo JobInstance khác, dễ reprocess/double effects.
- **(12)** DDL/job parameters/context serialization có thể không đọc được bởi binary cũ; rollback phải được rehearsal.
- **(13)** Test writer failure rollback, crash sau business commit/trước checkpoint, duplicate delivery hoặc concurrent partition + reconciliation; thêm context migration restart test.
- **(14)** Repository pool/latency/lock wait và Step metadata update time so với target DB transactions, Hikari pending, deadlocks, goodput.
- **(15)** Tạm giảm dispatch về mức an toàn, khoanh transaction wiring, xác minh output, triển khai writer idempotency, kiểm thử metadata compatibility và canary với một biến mỗi lần; chỉ tăng throughput sau khi chứng minh correctness.

### DAG triển khai có kiểm soát

~~~mermaid
flowchart TD
    A["Check transaction wiring + schema"] --> B["Run rollback and crash tests"]
    B --> C["Verify idempotent business output"]
    C --> D["Canary 1 to 4 workers"]
    D --> E{"Reconciliation + SLO PASS?"}
    E -->|"Có"| F["Scale gradually to target"]
    E -->|"Không"| G["Stop dispatch and recover"]
~~~

Bài học: **“nâng cấp ứng dụng thành công” không có nghĩa “giữ nguyên transaction contract”** nếu đồng thời thay resource topology, chunk size và concurrency.

## 30. Checklist trước production

- [ ] Đã lập danh sách phiên bản Java, Boot, Framework, Batch, Retry, JDBC driver, DB, broker và metadata schema.
- [ ] Đã đọc migration guides/release notes của **chính xác** version nguồn và đích.
- [ ] Đã phân loại thay đổi API config và thay đổi runtime semantics theo test.
- [ ] `StepBuilder` chunk và tasklet inject **đúng** `PlatformTransactionManager` có `@Qualifier` khi cần.
- [ ] Đã xác minh writer, reader, repository sử dụng datasource/transaction boundaries thực tế.
- [ ] Khi business và metadata dùng nhiều resources, đã thiết kế idempotency/failure windows rõ.
- [ ] Không giả định `@Transactional` self-invocation hoặc `REQUIRES_NEW` rollback cùng outer.
- [ ] Đã test transaction propagation, isolation, timeout và JDBC exception mapping.
- [ ] Đã phân loại retryable, skippable, fatal exceptions và rollback rules; không blanket retry.
- [ ] Đã kiểm tra `noRollback`/skip/retry semantics trên Step thực, không chỉ unit mock.
- [ ] Đã test writer insert rồi throw: cùng-resource transaction không để lại uncommitted rows.
- [ ] Đã test crash sau commit và restart cùng `JobInstance`: không thiếu/trùng business keys.
- [ ] Có idempotency ledger/outbox cho side effects ngoài JDBC transaction.
- [ ] Input snapshot/partition manifest/reader sort order bất biến qua restart.
- [ ] `ExecutionContext` và `JobParameters` từ version cũ được đọc/migrate đúng, không reset state im lặng.
- [ ] Job/Step/item-reader names không bị đổi làm mất checkpoint khi resume.
- [ ] Đã thử concurrent launch và optimistic metadata conflict ở JobRepository.
- [ ] Đã thử multi-threaded chunk commit đảo thứ tự và thread safety của reader/writer.
- [ ] Parallel flows không publish downstream trước khi mọi dependency hợp lệ.
- [ ] Local/remote partitions có StepExecution riêng, ownership và fencing khi redispatch.
- [ ] Remote chunking có correlation, business idempotency và xử lý lost ACK/reply.
- [ ] Đã tính JDBC pool DB budget cho manager/workers, cả rolling surge và failover.
- [ ] Có metric chunk commit/rollback, transaction age/lock waits, repository latency và unique commits/s.
- [ ] Có ma trận fault injection và benchmark được chạy trên environment tương đương production.
- [ ] DDL migration/backups được thử nghiệm trước khi chạm metadata hiện có.
- [ ] Không chạy old/new binaries trộn khi schema/serializer chưa chứng minh tương thích.
- [ ] Kế hoạch rollback có xét **cả binary lẫn schema và business effects đã commit**.
- [ ] Không tự sửa `BATCH_*`, xóa context hoặc tạo identifying parameters mới để né lỗi.
- [ ] Có runbook cho orphan `STARTED`, metadata conflict, job restart và message redelivery.
- [ ] Gate cuối: metadata đúng, output reconciliation PASS, recovery RTO và throughput SLA đạt.

## 31. Tài liệu tham khảo

- [Spring Batch 5.2 Reference](https://docs.spring.io/spring-batch/reference/5.2/index.html): tra cứu API/semantics của nhánh 5.2.
- [Spring Batch – Migration](https://docs.spring.io/spring-batch/reference/migration.html): các hướng dẫn migration và version compatibility; đối chiếu vị trí trang theo phiên bản.
- [Spring Batch – Configuring a Job](https://docs.spring.io/spring-batch/reference/job.html): JobInstance identity, JobExecution và restart.
- [Spring Batch – Configuring a Step](https://docs.spring.io/spring-batch/reference/step.html): Step/chunk/tasklet và cấu hình.
- [Spring Batch – Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk/commit behavior.
- [Spring Batch – Transaction Attributes](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/transaction-attributes.html): transaction settings của Step.
- [Spring Batch – Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html): rollback policies và fault tolerance.
- [Spring Batch – Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry/recovery semantics.
- [Spring Batch – Configuring JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): JDBC JobRepository và isolation-for-create.
- [Spring Batch – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): tables, job parameters, execution contexts và versioning.
- [Spring Batch – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint open/update/close.
- [Spring Batch – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning.
- [Spring Batch – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking và remote partitioning.
- [Spring Batch – Testing](https://docs.spring.io/spring-batch/reference/testing.html): `spring-batch-test` và integration testing.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): declarative/programmatic transactions.
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED, REQUIRES_NEW và NESTED.
- [Spring Boot – SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource và transaction auto-configuration.
- [Spring Retry](https://github.com/spring-projects/spring-retry): RetryTemplate, BackOffPolicy và retry classifiers.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation levels và serialization behavior.
- [PostgreSQL – Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, wait events và blockers.
- [PostgreSQL – SQL INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): replay-safe SQL patterns.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): JUnit tests và assertions.
- [Java 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): deterministic concurrency tests.

Các liên kết giúp nghiên cứu sâu; **không thay thế release notes/migration guide của đúng artifact versions đang dùng**. Ví dụ code nhắm Spring Batch 5.x; nếu target là 6.x hoặc một nhánh khác, hãy kiểm chứng signature/semantics trước khi áp dụng. Bài STEP 4 này cung cấp thiết kế và test cases, **không khẳng định đã chạy build hoặc QA chuyên môn của STEP 6**.

## Ghi nhớ

**“Thay đổi transaction behavior” khi nâng cấp Spring Batch không chỉ là lỗi biên dịch hay đổi cú pháp builder.** Phải xác minh lại `JobRepository`, `PlatformTransactionManager`, `DataSource`, chunk boundary, isolation, propagation, rollback, retry, checkpoint và metadata serialization. Trong kiến trúc có **nhiều resource hoặc remote workers**, business commit, repository checkpoint và broker ACK không tự động là một transaction nguyên tử. Giữ input snapshot/partition identity ổn định, dùng writer idempotent, test cả failure windows và owner takeover; không sửa `BATCH_*` thủ công để ép restart. Khi rolling upgrade, chứng minh tính tương thích của **binary + metadata schema + serializer + message contract** trước khi chạy lẫn phiên bản. **Nâng cấp được xem là an toàn khi dữ liệu cuối đúng, có thể phục hồi và đạt throughput ổn định trong SLA — không chỉ khi job hiển thị COMPLETED.**
