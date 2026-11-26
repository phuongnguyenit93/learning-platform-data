# Test concurrent metadata update trong Spring Batch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt cập nhật **metadata của Spring Batch** với cập nhật **business data**, nhất là khi một job dùng multi-threaded step, parallel steps, partitioning hoặc remote worker.
- Nắm rõ vai trò của `JobRepository`, `JobExplorer`, `JobInstance`, `JobExecution`, `StepExecution` và hai loại `ExecutionContext` khi nhiều luồng hoặc JVM cùng hoạt động.
- Giải thích cơ chế **optimistic locking bằng cột `VERSION`** của các bảng execution, và vì sao nó ngăn ghi đè im lặng nhưng **không tự giải quyết** mọi race trên context hoặc side effect.
- Viết kiểm thử đồng thời có kiểm soát bằng **Java 17, Spring Batch 5.x, JUnit 5, `ExecutorService`, `CountDownLatch`**, cho hai bản sao metadata có cùng version.
- Phát hiện **lost update**, **stale checkpoint**, xung đột `ExecutionContext`, nhầm ownership khi remote worker chết và tình huống business commit nhưng metadata chưa persist.
- Dùng PostgreSQL để quan sát `VERSION`, `READ_COUNT`, `COMMIT_COUNT`, `ROLLBACK_COUNT`, `STATUS` và context metadata **chỉ bằng câu lệnh đọc**.
- Thiết kế các test cho commit/rollback, retry, restart, duplicate delivery, failover, rolling deployment và race ở ranh giới chunk.
- Lập tiêu chí PASS dựa trên **chính xác trạng thái metadata, kết quả nghiệp vụ và khả năng restart** chứ không chỉ “test có hai thread và job COMPLETED”.
- Phân tích sức chịu tải của `JobRepository`, connection pool, isolation, lock wait và chọn phạm vi đồng thời an toàn.

## 1. Một lỗi rất khó thấy: hai worker cùng ghi tiến độ của một StepExecution

Module **SPRING_BATCH_SCALING_OPERATIONS** học cách mở rộng Spring Batch qua đa luồng, parallel steps, partitioning và xử lý phân tán. Khi tăng concurrency, không chỉ reader/writer phải thread-safe: **metadata điều phối và checkpoint** cũng phải giữ ngữ nghĩa đúng.

Giả sử worker A và worker B vô tình cùng xử lý một `StepExecutionId=501`:

~~~text
Tại t0, metadata database:
  StepExecutionId=501
  VERSION=12
  READ_COUNT=2000
  COMMIT_COUNT=10
  STATUS=STARTED

Worker A đọc bản version 12.
Worker B cũng đọc bản version 12.

A xử lý thêm 200 item, ghi READ_COUNT=2200.
B xử lý thêm 200 item khác, cũng dự định ghi READ_COUNT=2200.
~~~

Nếu một database update ghi đè cả bản ghi mà không kiểm tra version, kết quả có thể là **lost update**: metadata vẫn ghi 2.200 trong khi tổng xử lý logic kỳ vọng là 2.400. Khi restart, reader có nguy cơ đọc lại hoặc bỏ qua công việc tùy cách sử dụng checkpoint.

Trong `JdbcJobRepository` chuẩn, các bảng execution quan trọng sử dụng `VERSION` cho optimistic locking. Khi một writer cập nhật thành công, writer còn giữ version cũ thường nhận lỗi optimistic locking thay vì im lặng ghi đè. **Nhưng việc lỗi được phát hiện không có nghĩa cả hai worker cùng xử lý một StepExecution là thiết kế đúng.** Hệ thống phải xác định ai sở hữu việc, dừng/recover an toàn và đối soát dữ liệu. Đây là mục tiêu của bài kiểm thử.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant R as Jdbc JobRepository
    participant D as BATCH_STEP_EXECUTION
    A->>R: Read StepExecution 501, version 12
    B->>R: Read StepExecution 501, version 12
    A->>R: update(step 501, expected version 12)
    R->>D: Conditional UPDATE
    D-->>R: 1 row, VERSION=13
    R-->>A: Success
    B->>R: update(step 501, expected version 12)
    R->>D: Conditional UPDATE
    D-->>R: 0 rows matched
    R-->>B: OptimisticLockingFailureException
~~~

**Điểm phân biệt:** sơ đồ thể hiện hai *bản sao* `StepExecution` được load độc lập để tạo xung đột version. Nếu hai thread cùng cầm **một object Java** rồi sửa field và gọi repository, còn có race trong heap; kết quả cần được kiểm thử riêng.

## 2. Metadata nào thuộc đối tượng nào?

Các đối tượng và bảng JDBC metadata trong Spring Batch 5.x:

| Java domain | Bảng mặc định | Điều cần giữ đúng khi concurrent |
| --- | --- | --- |
| `JobInstance` | `BATCH_JOB_INSTANCE` | Identity: job name + identifying parameters |
| `JobExecution` | `BATCH_JOB_EXECUTION` | Lifecycle/status/version của một lần chạy job |
| `JobParameters` | `BATCH_JOB_EXECUTION_PARAMS` | Parameters và cờ identifying, không dùng như shared mutable state |
| `StepExecution` | `BATCH_STEP_EXECUTION` | Counters, status, exit code, `VERSION` và checkpoint lifecycle |
| Job `ExecutionContext` | `BATCH_JOB_EXECUTION_CONTEXT` | State cấp job execution, tránh nhiều nhánh cùng ghi key |
| Step `ExecutionContext` | `BATCH_STEP_EXECUTION_CONTEXT` | State của từng step/partition, cần serializable và ổn định qua restart |

`JobRepository` chịu trách nhiệm tạo, lưu, cập nhật metadata; `JobExplorer` cung cấp khả năng đọc execution history/state. Đừng lấy một row trong `BATCH_STEP_EXECUTION` làm nguồn sự thật duy nhất cho business commit hoặc trạng thái broker.

### Hai context khác nhau quan trọng thế nào?

- **StepExecutionContext**: lưu reader position, partition input key, phạm vi đọc, state của `ItemStream`; trong chunk-oriented step, thường được cập nhật ở các điểm chunk commit theo lifecycle framework.
- **JobExecutionContext**: thông tin được dùng giữa các step; theo mẫu sử dụng phổ biến, được persist ở ranh giới step thay vì mỗi lần chunk commit. Không lấy nó làm progress counter của nhiều worker đang chạy.
- **Business database**: nơi lưu các item đã commit, idempotency ledger hoặc kết quả nghiệp vụ; có thể ở DataSource/transaction khác repository.

Ví dụ hai partition độc lập có thể cùng thuộc một `JobExecution`, nhưng nên có **hai `StepExecution` khác nhau**, mỗi cái sở hữu context riêng:

~~~text
JobExecution 700
  workerStep:partition0000, StepExecution 701
    snapshotId=snap-42; range=[1,5001); reader checkpoint riêng
  workerStep:partition0001, StepExecution 702
    snapshotId=snap-42; range=[5001,10001); reader checkpoint riêng
~~~

Không cần ép cả hai partition ghi chung `StepExecutionId=701` chỉ để “dồn tổng readCount”. Sau khi các nhánh hoàn tất, dùng manager/aggregator và business reconciliation để tính kết quả tổng.

## 3. Optimistic locking: cơ chế bảo vệ bản ghi execution

Các bảng như `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION` có `VERSION`. Về mặt logic, một cập nhật có thể được hình dung như sau:

~~~sql
-- SQL minh họa tư duy compare-and-swap.
-- KHÔNG chạy trực tiếp câu này lên bảng BATCH_* đang được framework quản lý.
UPDATE BATCH_STEP_EXECUTION
SET READ_COUNT = :newReadCount,
    COMMIT_COUNT = :newCommitCount,
    VERSION = :oldVersion + 1
WHERE STEP_EXECUTION_ID = :stepExecutionId
  AND VERSION = :oldVersion;
~~~

Khi update affected rows = 1, phiên bản dự kiến còn đúng lúc cập nhật. Khi affected rows = 0, dữ liệu có thể đã được writer khác cập nhật, hoặc row không còn tồn tại; repository sẽ xử lý xung đột theo API của nó. **Đừng copy query minh họa này thành DAO tự ghi bảng metadata.** Spring Batch còn các trường, transaction, serialization và invariant khác mà thao tác SQL thô không bảo vệ.

### Sự khác biệt giữa optimistic và pessimistic locking

| Thuộc tính | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Ý tưởng | Kiểm tra version khi UPDATE; conflict thì từ chối | Khóa row/resource trước hoặc trong lúc thao tác |
| Khi xung đột | Một writer thất bại rõ | Writer khác thường chờ hoặc bị timeout/deadlock |
| Ưu điểm | Giảm nhu cầu khóa giữ lâu khi ít tranh chấp | Tốt khi phải serialize phần critical section |
| Hạn chế | Conflict không tự merge dữ liệu đúng | Lock có thể làm nghẽn, deadlock nếu khóa sai |
| Dùng ở đây | Repository execution version và các CAS ứng dụng | Ownership/lease lock hoặc row-level guard tùy thiết kế |

**Optimistic locking phát hiện xung đột, không thay nghiệp vụ giải quyết xung đột.** “Bắt exception rồi gọi `repository.update(staleStepExecution)` thêm 100 lần” chỉ tạo retry storm. Muốn thử lại phải hiểu object/stale state, liệu business effects đã commit chưa và owner hợp lệ là ai.

### Version không phải timestamp

Không dùng `LAST_UPDATED` để thay `VERSION`. Timestamp chịu độ chính xác DB, lệch clock và việc nhiều update cùng thời điểm. Version tạo **điều kiện so khớp trạng thái** theo giao thức repository, còn timestamp chủ yếu giúp giám sát.

## 4. ExecutionContext là một vùng rủi ro khác

Một điều dễ bị bỏ qua: các bảng `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT` trong schema chuẩn **không có cột `VERSION` độc lập giống `BATCH_STEP_EXECUTION`**. Chúng lưu context đã serialize theo execution ID.

Vì vậy, không được kết luận rằng **mọi thao tác update bất kỳ lên mọi field của ExecutionContext đều tự có CAS** chỉ vì StepExecution có version.

Hai luồng làm:

~~~java
// Anti-pattern: hai parallel steps cùng ghi một key job-level.
ExecutionContext sharedJobContext =
        stepExecution.getJobExecution().getExecutionContext();

sharedJobContext.putString("inputStatus", "READY_A");
// Trong thread khác:
sharedJobContext.putString("inputStatus", "READY_B");
~~~

Kết quả `inputStatus` phụ thuộc lịch chạy và thời điểm persist; cùng một `ExecutionContext` được chia sẻ giữa threads không phải giao thức trao đổi business state có thứ tự. Kể cả các thao tác trên map được bảo vệ ở mức thao tác riêng lẻ, **đọc–sửa–ghi cả chuỗi không tự atomic**.

### Vì sao context serialization là thách thức?

- Một job/step context được serialize thành representation để persist; nếu hai writer cùng tính từ bản cũ, update toàn bộ context có thể **ghi đè key của nhau**.
- State `ItemStream` có thể chứa reader index/checkpoint. Ghi đè context có thể làm restart đọc sai.
- Context sửa trong RAM nhưng chưa persist có thể bị mất khi JVM crash.
- Lưu object tùy ý khó serialize hoặc chứa resource/connection sẽ làm restart/version upgrade không đáng tin.
- Một context rất lớn làm tăng write/read latency và gây contention với metadata transaction.

### Thiết kế an toàn hơn

1. Giữ **state worker-local** trong từng `StepExecutionContext`; không chia sẻ một object context qua nhiều worker.
2. Mỗi partition có **StepExecution ID/name và input key riêng**.
3. Sử dụng immutable snapshot/manifest để reader mới có thể tái tạo đúng data.
4. Nếu cần tổng hợp nhiều nhánh, dùng **output/ledger bền vững có unique keys** và bước reconcile sau barrier, thay vì concurrent writes vào job context.
5. Nếu promote state giữa các bước, dùng key tách biệt và trình tự promotion rõ; không để hai sibling flows cùng ghi cùng job key tùy tiện.
6. Không tự cập nhật `BATCH_*_EXECUTION_CONTEXT` bằng JDBC SQL để “sửa offset”.

## 5. Các mô hình concurrency tạo ra race khác nhau

| Mô hình | Các StepExecution | Nguồn race metadata | Phép thử bắt buộc |
| --- | --- | --- | --- |
| **Sequential step** | Step chạy theo flow | Restart/state lỗi giữa chunk/step | Checkpoint commit/rollback và resume |
| **Parallel steps** | Step riêng trong các sibling flows | Cùng `JobExecution`/job context; promotion xung đột | Two branches same key, barrier, job-level merge |
| **Multi-threaded step** | Một `StepExecution` cho nhiều chunk threads | Cập nhật counters/context, reader/writer shared | Nhiều chunk hoàn tất lệch thứ tự, restart |
| **Local partitioning** | `StepExecution` riêng theo partition | Sai partition identity, manager aggregation, shared beans | Đếm đủ partitions và context isolation |
| **Remote partitioning** | StepExecutions ở nhiều JVM | Giao trùng một StepExecution, duplicate reply, owner cũ | Two-worker delivery, stale-version/fencing |
| **Remote chunking** | Manager thường sở hữu reader/chunk metadata | Request/reply mất, redelivery và checkpoint manager | Commit thành công nhưng reply mất |
| **Parallel jobs với cùng parameters** | Có thể cạnh tranh JobInstance identity | Hai launch cùng JobInstance | Chỉ một launch hợp lệ theo JobRepository policy |

**Không đánh đồng multi-threaded step và partitioning.** `@StepScope` tạo bean theo `StepExecution`, hữu ích cho partitioning, nhưng không biến một `ItemStreamReader` chia sẻ trong **cùng StepExecution** thành nhiều reader riêng theo thread.

### Khối hệ thống cần test

~~~mermaid
flowchart TD
    J["JobInstance + JobExecution"] --> PA["Parallel/partition manager"]
    PA --> SA["StepExecution A + StepContext A"]
    PA --> SB["StepExecution B + StepContext B"]
    SA --> RA["Reader/Writer A"]
    SB --> RB["Reader/Writer B"]
    RA --> OUT["Business output"]
    RB --> OUT
    SA --> REPO["JobRepository JDBC"]
    SB --> REPO
    J --> JC["JobExecutionContext shared scope"]
    JC --> RISK["Risk: concurrent job-context writes"]
    REPO --> VAL["Version/metadata integrity checks"]
    OUT --> REC["Business reconciliation"]
~~~

## 6. Bất biến để đánh giá một test metadata concurrency

Một test PASS không đơn thuần là “cả hai threads kết thúc không throw”. Với concurrent metadata, mục tiêu thường là **chặn cập nhật sai và giữ khả năng recovery**.

| Bất biến | Cách kiểm chứng |
| --- | --- |
| Không lost update im lặng trên một `StepExecution` | Hai snapshot cùng version, tối đa một cập nhật từ version cũ thành công |
| Version tăng có kiểm soát | Reload DB, kiểm tra `VERSION` và giá trị cuối đúng một writer |
| Metadata không chỉ tồn tại trong RAM | Dùng `JobExplorer`/JDBC đọc lại bản đã persist |
| Không dùng chung partition identity | StepExecution IDs/names khác nhau cho partitions khác nhau |
| Step context của A không nhiễm B | Reload hai contexts, kiểm tra keys/ranges/reader state |
| Job context không bị dùng như counter global concurrent | Test conflict keys/merge sau barrier |
| State không vượt quá business commit | Test rollback; checkpoint restart không skip uncommitted item |
| Business effect không bị nhân đôi sau replay | Unique key/operation ledger và source–target reconciliation |
| Thất bại phải có đường xử lý rõ | Conflict log, chủ sở hữu, retry/fail policy, không silent swallow |
| Không để hai node ghi khi ownership chưa xác thực | Fencing/cách ly và test split-brain |
| Không dùng metric thay DB truth | Đối chiếu logs/metrics với metadata và business DB |

### Hai loại lỗi phải phân biệt

**False success:** hai thread đều báo “metadata update thành công” nhưng DB chỉ giữ kết quả của thread cuối, mất dữ liệu thread đầu.

**Safe rejection:** một thread được commit, thread còn lại nhận `OptimisticLockingFailureException`. Hệ thống vẫn có việc phải xử lý lại/điều tra, nhưng đã tránh được **silent overwrite** trên bản ghi versioned.

Đối với hai **StepExecution khác ID**, cả hai có thể update thành công mà không xung đột; đó mới là mục tiêu đúng của local/remote partitioning.

## 7. Môi trường thử nghiệm: phải có JDBC JobRepository thật

Muốn kiểm chứng optimistic locking của Spring Batch trên PostgreSQL, dùng **một `JobRepository` JDBC và `JobExplorer` đọc cùng metadata database**.

### Setup khuyến nghị

- Java 17, Spring Batch **5.x** với Spring Boot và JUnit 5 tương thích; database PostgreSQL test hoặc Testcontainers PostgreSQL.
- Dùng schema Batch đúng phiên bản library (các bảng `BATCH_*`); không copy ngẫu nhiên DDL của Spring Batch 6.x.
- Giữ đầy đủ transactions của `JobRepository`. **Không mock `JobRepository.update`** nếu mục tiêu là optimistic locking DB thật.
- Test phải dùng hai object `StepExecution` load **độc lập từ DB** và cùng một version ban đầu.
- Test method **không đặt `@Transactional`** bao ngoài, vì transaction test thread không được tự động truyền sang worker threads. Parent transaction chưa commit có thể làm worker không nhìn thấy fixture hoặc treo chờ lock.
- Dùng `CountDownLatch`/`CyclicBarrier` để điều khiển điểm đua, không chọn `Thread.sleep(100)` để “hy vọng” race xảy ra.
- Mỗi test tạo `JobInstance` bằng **identifying parameter duy nhất** để tránh đụng các fixture khác.
- Không thực hiện concurrent test phá dữ liệu trên `JobRepository` production hoặc trên những `StepExecution` thực đang chạy.

### Vì sao H2 hoặc mock có thể chưa đủ?

H2 có thể dùng cho unit smoke tests nhưng transaction isolation, row locking, sequence và timing khác PostgreSQL. Một test mock chỉ chứng minh code test đã gọi update, **không chứng minh** JDBC CAS, deadlock behavior hoặc recovery schema của DB đích.

Trong integration test cần lưu kết quả: kết quả của hai futures, exception class, `VERSION` trước/sau, row counters và việc StepExecution có thể được load lại.

## 8. SQL read-only để quan sát metadata

**Chỉ truy vấn SELECT trên schema Batch**, không thay đổi các bảng framework quản lý.

### StepExecution, counters và version

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    VERSION,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

### JobExecution version

~~~sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    VERSION,
    STATUS,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_JOB_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId;
~~~

### Metadata context existence, không dump nội dung nhạy cảm

~~~sql
SELECT
    s.STEP_EXECUTION_ID,
    s.STEP_NAME,
    CASE WHEN c.STEP_EXECUTION_ID IS NULL THEN FALSE
         ELSE TRUE END AS has_context
FROM BATCH_STEP_EXECUTION s
LEFT JOIN BATCH_STEP_EXECUTION_CONTEXT c
  ON c.STEP_EXECUTION_ID = s.STEP_EXECUTION_ID
WHERE s.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY s.STEP_EXECUTION_ID;
~~~

Context có thể chứa đường dẫn, input key, tên tenant, checkpoint hoặc thông tin nhạy cảm. Không xuất `SERIALIZED_CONTEXT` ra log công khai để “debug cho nhanh”.

### Cột VERSION không nằm ở đâu?

Theo schema metadata 5.x tiêu chuẩn, `BATCH_STEP_EXECUTION_CONTEXT`/`BATCH_JOB_EXECUTION_CONTEXT` không có `VERSION` riêng. Đừng xây giả thuyết “update context được CAS theo version riêng của context row” nếu chưa có kiểm chứng. Nếu một phiên bản/schema đã được tùy biến, kiểm tra DDL **đã triển khai**, không dựa vào tên bảng suy đoán.

## 9. Java 17 + JUnit 5: tạo hai bản metadata stale và ép cập nhật

Test tích hợp này kiểm chứng `JobRepository.update(StepExecution)` dùng optimistic locking thực tế. Nó chạy hai update qua **hai object độc lập** có cùng `VERSION` và dùng latch để cả hai cố update sau khi đã load stale state.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.OptimisticLockingFailureException;

@SpringBootTest
class ConcurrentStepMetadataIntegrationTest {

    @Autowired JobRepository repository;
    @Autowired JobExplorer explorer;

    @Test
    void staleUpdateMustNotSilentlyOverwriteNewerStepVersion()
            throws Exception {

        String jobName = "metadata-probe-" + UUID.randomUUID();
        var parameters = new JobParametersBuilder()
                .addString("snapshotId", "fixed-test-snapshot", true)
                .toJobParameters();

        JobExecution job = repository.createJobExecution(
                jobName, parameters);

        StepExecution initial = job.createStepExecution(
                "workerStep:partition0000");
        repository.add(initial);

        // Hai object độc lập, không chia cùng reference heap.
        StepExecution left = explorer.getStepExecution(
                job.getId(), initial.getId());
        StepExecution right = explorer.getStepExecution(
                job.getId(), initial.getId());

        assertNotNull(left);
        assertNotNull(right);
        assertNotSame(left, right);
        assertEquals(left.getVersion(), right.getVersion());

        int oldVersion = left.getVersion();
        left.setReadCount(11);
        right.setReadCount(22);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<Throwable> updateLeft =
                    () -> tryUpdate(left, ready, release);
            Callable<Throwable> updateRight =
                    () -> tryUpdate(right, ready, release);

            Future<Throwable> a = pool.submit(updateLeft);
            Future<Throwable> b = pool.submit(updateRight);

            assertTrue(ready.await(5, TimeUnit.SECONDS),
                    "Both workers must reach the race gate");
            release.countDown();

            Throwable aError = a.get(15, TimeUnit.SECONDS);
            Throwable bError = b.get(15, TimeUnit.SECONDS);

            // Chính xác một phiên bản stale được phép thắng.
            assertTrue(
                    (aError == null) != (bError == null),
                    "Exactly one update should succeed");

            Throwable failure =
                    aError != null ? aError : bError;
            assertTrue(
                    failure instanceof OptimisticLockingFailureException,
                    "Stale writer should be rejected: " + failure);

            StepExecution persisted = explorer.getStepExecution(
                    job.getId(), initial.getId());

            assertNotNull(persisted);
            assertEquals(oldVersion + 1, persisted.getVersion());
            assertTrue(
                    persisted.getReadCount() == 11
                    || persisted.getReadCount() == 22);
        } finally {
            release.countDown(); // Không để threads chờ mãi khi assert lỗi.
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));
        }
    }

    private Throwable tryUpdate(
            StepExecution snapshot,
            CountDownLatch ready,
            CountDownLatch release) throws InterruptedException {

        ready.countDown();
        if (!release.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Race gate timed out");
        }

        try {
            repository.update(snapshot);
            return null;
        } catch (RuntimeException ex) {
            return ex;
        }
    }

}
~~~

**Khi chạy test thật:** cấu hình Spring test context có `JobRepository`, `JobExplorer` JDBC đọc cùng schema metadata và không bao test bằng `@Transactional`. Test dùng trực tiếp `repository.update(snapshot)` và phải chạy trên một database riêng của môi trường integration test. Nếu repository tự chạy qua proxy transaction, lỗi optimistic locking có thể được gói bởi transaction infrastructure; khi đó kiểm tra chuỗi nguyên nhân cùng row/version được reload, không sửa bảng `BATCH_*` để ép test pass.

**Lý do tránh dùng ngủ:** cả hai object đã load chung version **trước** khi tạo futures, và `ready/release` bảo đảm cả hai worker tới điểm đua. Kể cả database serialize hai UPDATE theo thứ tự khác nhau, điều kiện version khiến tối đa một update stale thành công.

**Giới hạn test:** nó kiểm tra **đúng một row execution versioned**. Nó chưa chứng minh hai context rows không mất cập nhật hoặc reader checkpoint khớp business DB sau crash; cần các phép thử tiếp theo.

## 10. Test hai StepExecution độc lập không được nhiễm checkpoint của nhau

Test mục 9 **cố ý cho hai bản metadata cùng ID cạnh tranh**. Trong partitioning đúng, mỗi partition có `StepExecution` riêng và `StepExecutionContext` độc lập:

~~~text
JobExecution ID=800
  StepExecution ID=801 / workerStep:partition0000
    inputKey=shard-A; lastCommittedId=500
  StepExecution ID=802 / workerStep:partition0001
    inputKey=shard-B; lastCommittedId=1500
~~~

### JUnit 5 dùng repository thật và barrier

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PartitionContextIsolationIntegrationTest {

    @Autowired JobRepository repository;
    @Autowired JobExplorer explorer;

    @Test
    void differentStepContextsPersistIndependently() throws Exception {
        JobExecution job = repository.createJobExecution(
                "partition-context-" + UUID.randomUUID(),
                new JobParametersBuilder()
                    .addString("snapshotId", "snap-fixture", true)
                    .toJobParameters());

        StepExecution p0 = job.createStepExecution(
                "workerStep:partition0000");
        StepExecution p1 = job.createStepExecution(
                "workerStep:partition0001");
        repository.add(p0);
        repository.add(p1);

        p0.getExecutionContext().putString("inputKey", "shard-A");
        p0.getExecutionContext().putLong("lastCommittedId", 500L);
        p1.getExecutionContext().putString("inputKey", "shard-B");
        p1.getExecutionContext().putLong("lastCommittedId", 1500L);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            var a = pool.submit(() -> {
                ready.countDown();
                await(go);
                repository.updateExecutionContext(p0);
            });
            var b = pool.submit(() -> {
                ready.countDown();
                await(go);
                repository.updateExecutionContext(p1);
            });

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            go.countDown();
            a.get(15, TimeUnit.SECONDS);
            b.get(15, TimeUnit.SECONDS);
        } finally {
            go.countDown();
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));
        }

        StepExecution reloaded0 = explorer.getStepExecution(
                job.getId(), p0.getId());
        StepExecution reloaded1 = explorer.getStepExecution(
                job.getId(), p1.getId());

        assertNotNull(reloaded0);
        assertNotNull(reloaded1);
        assertEquals("shard-A",
                reloaded0.getExecutionContext().getString("inputKey"));
        assertEquals(500L,
                reloaded0.getExecutionContext().getLong(
                        "lastCommittedId"));
        assertEquals("shard-B",
                reloaded1.getExecutionContext().getString("inputKey"));
        assertEquals(1500L,
                reloaded1.getExecutionContext().getLong(
                        "lastCommittedId"));
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
    }
}
~~~

**Điều kiện chạy:** Spring test context cung cấp `JobRepository`/`JobExplorer` đọc cùng JDBC database; test **không có `@Transactional` trên method**. Hai `StepExecution` phải có ID khác nhau, mỗi context là một row riêng. Đọc lại qua repository/explorer để kiểm chứng **state persisted**, không chỉ object Java đã sửa trong heap.

Đây là test **context isolation**, chưa phải test đúng input range hoặc idempotency của writer. Hai context có thể không nhiễm nhau nhưng cả hai worker vẫn bị cấu hình đọc cùng business items nếu manifest sai.

## 11. Test JobExecutionContext read–modify–write không tự atomic

Ngay cả khi đọc/ghi từng key không làm hỏng cấu trúc map, phép “đọc, cộng một, ghi lại” không là một transaction atomic giữa hai threads.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class SharedContextLostUpdateTest {

    @Test
    void concurrentReadModifyWriteCanLoseUpdate()
            throws Exception {

        ExecutionContext context = new ExecutionContext();
        context.putLong("total", 0L);

        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch releaseWrites = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            var a = pool.submit(() -> increment(
                    context, bothHaveRead, releaseWrites));
            var b = pool.submit(() -> increment(
                    context, bothHaveRead, releaseWrites));

            assertTrue(bothHaveRead.await(5, TimeUnit.SECONDS));
            releaseWrites.countDown();
            a.get(10, TimeUnit.SECONDS);
            b.get(10, TimeUnit.SECONDS);

            // Cả hai cùng đọc 0, sau đó cùng ghi 1.
            // Kết quả này mô phỏng một lỗi thiết kế có chủ đích.
            assertEquals(1L, context.getLong("total"));
        } finally {
            releaseWrites.countDown();
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));
        }
    }

    private static void increment(
            ExecutionContext context,
            CountDownLatch bothHaveRead,
            CountDownLatch releaseWrites) {
        long before = context.getLong("total");
        bothHaveRead.countDown();

        try {
            if (!releaseWrites.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }

        context.putLong("total", before + 1L);
    }
}
~~~

**Đây là test cố ý tái hiện bug.** Nó PASS nếu cho kết quả 1 thay vì 2, để minh họa lost update của phép read-modify-write. Trong ứng dụng thực, nếu hai business updates phải được tính đủ thì kết quả 1 là **FAIL nghiệp vụ**.

### Giải pháp đúng

- Mỗi step/partition giữ `processedCount` riêng trong `StepExecutionContext`.
- Chờ split/join/barrier, rồi một aggregation step tính tổng từ output hoặc state đã commit.
- Nếu cần shared counter xuyên JVM, dùng database transaction/atomic update hoặc ledger theo unique operation ID.
- `AtomicLong` có thể an toàn trong một JVM nhưng không tự persist và không đồng bộ giữa hai worker machines.
- Không dùng `JobExecutionContext` làm distributed latch, job-wide shared counter hoặc message queue.

## 12. Thử CAS trên **bảng application**, không sửa bảng BATCH_*

Để minh họa optimistic update cho metadata nghiệp vụ, tạo bảng **do ứng dụng sở hữu** trong schema test riêng:

~~~sql
CREATE TABLE app_partition_summary (
    snapshot_id VARCHAR(100) NOT NULL,
    partition_name VARCHAR(100) NOT NULL,
    processed_count BIGINT NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_id, partition_name)
);

INSERT INTO app_partition_summary (
    snapshot_id, partition_name, processed_count, version
) VALUES ('snap-fixture', 'partition0000', 100, 7);
~~~

Hai clients cùng đọc `processed_count=100`, `version=7`. Client A:

~~~sql
UPDATE app_partition_summary
SET processed_count = 150,
    version = version + 1
WHERE snapshot_id = 'snap-fixture'
  AND partition_name = 'partition0000'
  AND version = 7
RETURNING processed_count, version;
~~~

Client B cũng dùng expected version 7:

~~~sql
UPDATE app_partition_summary
SET processed_count = 160,
    version = version + 1
WHERE snapshot_id = 'snap-fixture'
  AND partition_name = 'partition0000'
  AND version = 7
RETURNING processed_count, version;
~~~

Trong PostgreSQL, một update có thể thành công; update còn lại thường trả **0 hàng** vì version đã tăng lên 8, hoặc có thể nhận lỗi serialization ở isolation level nghiêm ngặt. **Kết quả mong muốn là xung đột được phát hiện**, không yêu cầu A thắng B hoặc ngược lại.

Không tự động “sửa” conflict bằng việc tải version 8 rồi ghi `processed_count=160`. Cần biết 150/160 là hai absolute checkpoints, hay hai increments độc lập, hay hai worker đã làm trùng business items. Việc merge phải theo business contract và idempotency.

### Ledger chống replay đáng tin hơn đếm attempts

~~~sql
CREATE TABLE app_completed_item (
    snapshot_id VARCHAR(100) NOT NULL,
    business_item_id BIGINT NOT NULL,
    partition_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (snapshot_id, business_item_id)
);

INSERT INTO app_completed_item (
    snapshot_id, business_item_id, partition_name
)
VALUES (:snapshotId, :businessItemId, :partitionName)
ON CONFLICT (snapshot_id, business_item_id) DO NOTHING;
~~~

Unique key giúp cùng business item không tạo duplicate row khi replay. Nhưng `ON CONFLICT DO NOTHING` không tự chống double side effect gửi email/API/thanh toán, cũng không tự chứng minh phân vùng đúng; phải có ownership và reconciliation.

## 13. Ranh giới transaction: business commit khác metadata commit

Nếu `JobRepository` và business writer dùng **hai datasource hoặc transaction managers độc lập**, business output có thể đã commit trong khi checkpoint metadata vẫn cũ:

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant B as Business DB
    participant J as JobRepository
    participant R as Recovery Worker
    W->>B: Commit chunk N
    B-->>W: COMMIT OK
    Note over W,J: JVM crash trước metadata checkpoint
    R->>J: Đọc StepExecutionContext
    J-->>R: Last durable checkpoint N-1
    R->>B: Replay chunk N
    B-->>R: UPSERT/dedup, final output đúng
~~~

**Cột VERSION của metadata không tạo ra distributed transaction** giữa business DB, repository và broker. Với cùng **một local transaction DB** được cấu hình đúng cho business output và metadata, khả năng atomic commit ở chunk boundary mạnh hơn; phải kiểm thử cấu hình thực tế.

### Test failure window bắt buộc

1. Chuẩn bị immutable snapshot nhỏ với thứ tự đọc unique.
2. Cho writer hoàn tất một chunk vào business DB.
3. Inject lỗi ở đường persist metadata tại cấu hình có **hai transaction resources riêng**, để mô phỏng “business commit trước checkpoint”.
4. Khôi phục cùng `JobInstance` sau khi trạng thái được đưa về restartable theo quy trình hợp lệ.
5. Kiểm tra reader replay phần chưa có checkpoint, nhưng writer không nhân đôi effect.
6. Đối chiếu source–target business key, payload/version và external side effects.
7. Xác minh `StepExecutionContext` không skip một item chưa commit.
8. Lưu lại actual failure window thay vì chỉ đếm số thread thử nghiệm.

`READ_COUNT`/`WRITE_COUNT` là metadata của framework, không trực tiếp là số unique business rows mới trong DB khi có retry, skip, upsert và rollback. Oracle cần có input snapshot và output đã commit.

## 14. Concurrent launch cùng JobInstance: hai schedulers chạy trùng

Một dạng race khác xảy ra khi **hai scheduler** cùng khởi động một job với **cùng job name và identifying parameters**.

~~~text
Scheduler A -> launch import-orders(snapshotId=snap-42)
Scheduler B -> launch import-orders(snapshotId=snap-42)

Cả hai tới JobRepository gần như đồng thời.
~~~

Với một JDBC `JobRepository` được cấu hình đúng, việc tạo `JobInstance`/`JobExecution` có transaction và isolation bảo vệ identity. Tùy trạng thái job, timing và database, một request có thể bị từ chối vì execution đang chạy, duplicate identity hoặc conflict transaction.

### Checklist test

- Cùng `JobLauncher` setup thật, cùng `JobRepository` JDBC; không mock repository.
- Hai launch dùng cùng **identifying `JobParameters`** và một start barrier.
- Không tạo hai bộ worker xử lý cùng `snapshotId` một cách ngoài ý muốn.
- Reload `BATCH_JOB_INSTANCE`/`BATCH_JOB_EXECUTION` bằng `SELECT` để xác minh identity, số execution và status.
- Ghi lại exception thực tế: `JobExecutionAlreadyRunningException`, race khi tạo instance, serialization/duplicate-key exception có thể phụ thuộc thời điểm.
- Nếu job đã `COMPLETED`, request chạy lại có thể bị từ chối bởi completed-instance policy; **không** ép mọi race phải ném cùng một exception type.
- Nếu execution còn `STARTED` mồ côi sau crash, cần recovery/ownership runbook; không sửa `BATCH_*` trực tiếp hoặc tạo identifying `run.id` mới chỉ để né lỗi.

**Isolation level ở các phương thức `create*` của repository có thể cấu hình** và ảnh hưởng contention. Trong Spring Batch 5.x, hãy đối chiếu cấu hình thực với database hiện tại; `SERIALIZABLE` bảo vệ mạnh hơn trong một số ngữ cảnh nhưng dễ gây chờ/serialization failures. Không suy ra “READ_COMMITTED luôn an toàn” từ một bài smoke test.

## 15. Remote partitioning: duplicate delivery và stale owner

Trong remote partitioning, manager dispatch yêu cầu chạy một `StepExecution` qua middleware. Nếu worker đã xử lý nhưng reply bị mất, request có thể được gửi lại cho worker khác.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant A as Worker A
    participant J as JDBC JobRepository
    participant B as Worker B
    M->>Q: Request StepExecution 501
    Q->>A: Deliver 501
    A->>J: Update version 12 -> 13
    Note over A,M: Reply bị mất
    Q->>B: Redelivery 501
    B->>J: Reload current state
    J-->>B: Version 13 + current status/context
    B->>M: Follow ownership/recovery protocol
~~~

### Phép thử cần có

1. Hai consumers nhận cùng `StepExecutionId` trong một cửa sổ thời gian.
2. Worker A commit output rồi mất reply; worker B nhận request lại.
3. Worker A chỉ mất kết nối tới manager nhưng vẫn ghi được business DB.
4. Worker B chỉ takeover sau **fencing/cách ly** A hoặc chứng minh A không còn chạy.
5. B dùng state mới nhất từ `JobRepository`, không xem serialized request cũ là source of truth.
6. Reply của các workers tới không theo thứ tự dispatch; manager dùng correlation/ownership đúng.
7. Worker mới dùng metadata schema/serializer tương thích với worker cũ.
8. Manager chết trong khi một số workers còn chạy; recovery đối soát current metadata và output.
9. Nhiều partitions song song nhưng không bao giờ tái sử dụng tên/ID cho input range khác trong cùng JobInstance.

**Version của StepExecution không đủ để fencing tất cả business effects.** A vẫn có thể gọi API ngoài hoặc ghi database khác trước khi bị repository từ chối. Nếu takeover chủ động trong network partition, cần generation/lease được **đích ghi** kiểm tra, hoặc phải cô lập owner cũ.

### Remote chunking cần phép thử khác

Remote chunking thường để manager sở hữu reader/checkpoint, còn workers nhận item chunks để process/write. Bởi vậy không áp assumption mỗi worker có reader offset riêng của remote partitioning. Hãy test request/reply correlation, redelivery, manager checkpoint và writer idempotency trên cùng operation identity.

## 16. Parallel steps: test xung đột khi promote job context

Một job có hai sibling flows:

~~~text
Flow customers:
  customerStep -> promote key "loadedCount"

Flow orders:
  orderStep    -> promote key "loadedCount"

Sau split:
  reportStep đọc "loadedCount"
~~~

Không có bảo đảm “loadedCount là tổng của cả hai” chỉ vì cả hai flow `COMPLETED`. Một promotion có thể ghi đè hoặc hai branches có thể dùng chung object context trên heap.

### Phép thử lịch chạy đối nghịch

- Test A: giữ customers tại barrier trước khi kết thúc, cho orders hoàn thành trước.
- Test B: giữ orders tại barrier, cho customers hoàn thành trước.
- Trong cả hai lần, dữ liệu business report phải giống nhau.
- Nếu output khác, rất có thể job đang dựa vào **last-writer-wins** hoặc đọc staging khi chưa READY.
- Cách đúng: mỗi stage ghi output/marker riêng; sau split barrier có bước validate/reconcile các stage đã commit.

### Metadata riêng do ứng dụng sở hữu

~~~sql
CREATE TABLE app_stage_marker (
    snapshot_id VARCHAR(100) NOT NULL,
    stage_name VARCHAR(50) NOT NULL,
    expected_count BIGINT NOT NULL,
    committed_count BIGINT NOT NULL,
    validated BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (snapshot_id, stage_name)
);
~~~

Gate của bước downstream:

~~~sql
WITH required(stage_name) AS (
    VALUES ('customers'), ('orders')
)
SELECT r.stage_name
FROM required r
LEFT JOIN app_stage_marker m
  ON m.snapshot_id = :snapshotId
 AND m.stage_name = r.stage_name
WHERE m.stage_name IS NULL
   OR m.validated IS DISTINCT FROM TRUE
   OR m.expected_count IS DISTINCT FROM m.committed_count;
~~~

Kỳ vọng **0 hàng** mới cho phép tiếp tục. Count equality có thể che thiếu/thừa triệt tiêu nhau, nên report quan trọng cần reconcile business key/version, không chỉ count. Marker phải được công bố **sau commit** và theo đúng immutable snapshot.

### JobExecutionContext không tự là distributed barrier

Một `ExecutionContextPromotionListener` có thể giúp chuyển giá trị từ step context sang job context **khi step hoàn tất**, nhưng không thay cho khóa, barrier hoặc rule merge giữa hai sibling flows. Nếu dữ liệu quan trọng và đồng thời, sử dụng stage-specific keys, thứ tự flow rõ và output/ledger bền vững.

## 17. Multi-threaded step: cùng StepExecution, nhiều chunk threads

Trong một multi-threaded step, nhiều chunk có thể chạy qua một `StepExecution`. Ngoài optimistic locking ở DB, có các race **ngay trong memory và checkpoint**:

- `ItemReader` có cursor/index mutable không thread-safe.
- `ItemWriter` hoặc `ItemProcessor` giữ state singleton không được bảo vệ.
- Chunk hoàn thành không theo thứ tự đọc, khiến cursor checkpoint không còn biểu thị prefix input đã commit.
- Listener ghi biến `lastProcessedId` từ nhiều threads theo completion order bất định.
- Code gọi `repository.update(...)` thủ công trong worker threads và cạnh tranh với lifecycle của framework.
- Một chunk rollback trong khi chunk khác commit, gây hiểu sai progress nếu chỉ nhìn shared counter.
- Một `@StepScope` reader trong cùng `StepExecution` không tự tạo bean riêng cho **mỗi thread**.

### Test cần làm

1. Tạo snapshot 10.000 items với unique business keys và ordering deterministic.
2. Baseline chạy một thread để biết expected output.
3. Chạy concurrency 2, 4, 8 trên workload tương đương và database cùng quota.
4. Inject processing delay có điều khiển để ép chunk commit lệch thứ tự.
5. Kill JVM giữa lúc một chunk vừa commit, chunk khác còn in-flight.
6. Restart cùng `JobInstance`, snapshot và checkpoint, không đổi reader ordering.
7. Query source–output missing/extra/version mismatch, duplicate effect theo business identity.
8. So `StepExecution`/`VERSION`/`ExecutionContext` trong repository với logs/metrics.
9. Kiểm tra reader/writer thread safety dựa trên Javadoc và test, không dựa vào “không thấy exception”.
10. Nếu checkpoint không an toàn, chuyển sang partitioning mỗi worker có `StepExecution` riêng hoặc dùng process-indicator/idempotency thay vì chỉ thêm `synchronized`.

`SynchronizedItemStreamReader` hoặc wrapper khóa `read()` có thể giảm race giữa các cuộc gọi reader, nhưng **không tự chứng minh restart đúng** khi chunk hoàn tất/rollback không theo thứ tự. Phải đo bằng fault injection.

## 18. Metadata contention: không chỉ correctness mà còn ảnh hưởng throughput

Khi số worker/chunk tăng, `JobRepository` phải ghi nhiều metadata. Trên một database chia sẻ, bảng `BATCH_STEP_EXECUTION`/context có thể trở thành một nút thắt.

### Các chỉ số liên quan

| Nhóm | Tín hiệu | Câu hỏi |
| --- | --- | --- |
| Metadata integrity | `OptimisticLockingFailureException` | Có hai writers cạnh tranh cùng StepExecution hay bug lifecycle? |
| Repository DB | Write latency, lock wait, deadlocks, IO | Metadata transaction có chậm bất thường không? |
| JDBC pool | Active/idle/pending/max, acquire p95 | Worker đang chờ lấy repo connection? |
| Chunk | Commit/rollback rate, chunk p95/p99 | Quá nhiều commits/s làm metadata churn tăng? |
| Step | `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT` | Metadata có tiến triển theo expected work? |
| Worker | Active threads, queue, retry count | Backpressure đã đặt giới hạn chưa? |
| Recovery | Last durable checkpoint, RTO | Một restart có thể resume từ state đúng không? |
| Business | Unique commits/s, reconciliation mismatches | Throughput nhanh nhưng dữ liệu có đúng không? |

`StepExecution.VERSION` **tăng là bình thường** khi framework cập nhật row, không phải mặc định một lỗi. Sự kiện optimistic conflict, exception hoặc mismatch mới là tín hiệu có vấn đề cần phân loại.

### PostgreSQL: lock/session khi repository có tải

~~~sql
SELECT
    application_name,
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    now() - query_start AS query_age,
    left(query, 140) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

Chỉ dùng quyền truy cập giám sát phù hợp, không log SQL chứa data nhạy cảm. Không kết luận nhiều `BATCH_STEP_EXECUTION` rows là xung đột nếu chúng thuộc **những StepExecution ID khác nhau**; một job partitioned lớn vốn có nhiều rows hợp lệ.

### Vì sao không giải quyết bằng cách tắt checkpoint?

Giảm metadata frequency có thể tăng throughput trên một số workload nhưng làm tăng phần việc chưa checkpoint và chi phí retry/restart. Tắt state persistence để “hết optimistic lock” có thể khiến job không resume đúng. Trước khi đổi chunk size, hãy xác định **ai đang ghi cùng row** và vì sao.

## 19. Ma trận kiểm thử concurrency metadata và fault injection

Một test đáng tin cậy phải phân biệt **race logic**, **race repository**, **race transaction** và **race owner giữa các worker**.

| Kịch bản | Cách kích hoạt | Oracle / kỳ vọng |
| --- | --- | --- |
| Hai copies cùng `StepExecutionId/version` | Load trước barrier, cùng gọi `repository.update` | Một success, stale writer bị từ chối, không lost update silently |
| Hai contexts thuộc IDs khác nhau | Persist đồng thời | Context mỗi partition đọc lại đúng input key/offset |
| Hai threads increment chung context | Cùng đọc trước barrier, rồi cùng ghi | Tái hiện lost update và sửa design |
| Hai clients CAS application row | Cùng expected version | Một thắng, một conflict rõ |
| Hai schedulers launch cùng instance | Barrier trước `JobLauncher.run` | Không có hai bộ worker xử lý cùng JobInstance vô ý |
| Sibling flows promote cùng key | Cho A/B lần lượt finish trước | Phát hiện output phụ thuộc thứ tự finish |
| Multi-thread chunks hoàn thành đảo thứ tự | Chặn một chunk trước writer | Checkpoint/restart không làm thiếu business item |
| Chunk rollback sau context mutation | Inject writer failure | Durable checkpoint không vượt uncommitted work |
| Business DB commit trước metadata | Dùng hai resources, inject failure | Replay không tạo double effect |
| Repository commit nhưng reply mất | Drop reply | Manager đối soát state và correlation |
| Worker A bị network partition | Chặn control plane, giữ business DB path | Fencing/cách ly owner, tránh double effect |
| Manager crash khi workers còn chạy | Kill manager | Recovery từ persisted state, không blind dispatch |
| Rolling deploy đổi serializer | Worker mới mở context cũ | Compatibility hoặc fail có thông báo |
| Snapshot hết retention | Reopen checkpoint | Fail rõ, không fallback nguồn live |
| Repository JDBC pool nhỏ | Tăng chunk/worker concurrency | Pending/lock wait có metric, backpressure |
| Business output thiếu/trùng | Inject trên bảng application test | Reconciliation FAIL dù step COMPLETED |

### Những quy tắc khi inject lỗi

- Chạy **trong staging/test**, không sửa metadata của job production đang active.
- Sử dụng fault injection ở DAO/proxy/network/transaction boundary của **test**; không sửa `VERSION`/`STATUS` trong `BATCH_*` để “ép race”.
- Latches hoặc barriers kiểm soát thời điểm, timeout để không treo CI; `Thread.sleep` không phải cách tạo race đáng tin cậy.
- Mỗi test dùng `JobInstance` identifying parameters riêng, tránh test song song làm nhiễm fixture.
- Không để test thay đổi metadata version liên tục bằng vòng retry vô hạn.
- Cleanup fixture bằng test database isolation và lifecycle framework.
- Lưu phiên bản Spring Batch, JDBC driver, DB isolation, connection pool và kết quả chi tiết.
- Chạy thử nhiều lịch biểu/seed để tăng khả năng phát hiện lỗi; **không thay thế barrier bằng chạy ngẫu nhiên 1.000 lần**.

## 20. Ba lớp oracle: metadata, business output và recovery

Một optimistic conflict được báo đúng chưa đủ để PASS. Cần kiểm chứng cả ba gate:

~~~mermaid
flowchart TD
    T["Concurrent metadata / fault test"] --> M["A: Metadata integrity"]
    T --> O["B: Business reconciliation"]
    T --> R["C: Restart/recovery"]
    M --> G{"Tất cả đều PASS?"}
    O --> G
    R --> G
    G -->|"Có"| OK["Test PASS"]
    G -->|"Không"| FAIL["Test FAIL + root cause"]
~~~

### Gate A: metadata integrity

- `VERSION` của một `StepExecution` chỉ được tăng khi update hợp lệ theo repository.
- Bản ghi stale không silently overwrite counters/checkpoint.
- `StepExecutionContext` thuộc đúng partition, snapshot, reader state.
- Context được **reload từ DB** sau commit; không chỉ assert trên object trong heap.
- `JobExecutionContext` không được dùng làm nơi nhiều flow cộng tiến độ không có giao thức merge.
- Worker owner cũ không còn chạy song song không kiểm soát với worker mới.

### Gate B: business output

Giả sử ứng dụng sở hữu `app_input_snapshot` và `app_output` với `(snapshot_id,record_id)` là business identity:

~~~sql
-- Những record bắt buộc nhưng chưa xuất hiện ở output.
SELECT record_id
FROM app_input_snapshot
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT record_id
FROM app_output
WHERE snapshot_id = :snapshotId;
~~~

~~~sql
-- Output không thuộc snapshot cần xử lý.
SELECT record_id
FROM app_output
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT record_id
FROM app_input_snapshot
WHERE snapshot_id = :snapshotId;
~~~

~~~sql
-- Đúng key nhưng sai version/payload.
SELECT s.record_id
FROM app_input_snapshot s
JOIN app_output o
  ON o.snapshot_id = s.snapshot_id
 AND o.record_id = s.record_id
WHERE s.snapshot_id = :snapshotId
  AND (
      s.source_version IS DISTINCT FROM o.source_version
      OR s.payload IS DISTINCT FROM o.payload
  );
~~~

Với bài toán copy nguyên snapshot, kỳ vọng **0 hàng** ở mọi query. Nếu processor filter/transform, hãy đối chiếu **expected output set theo nghiệp vụ**, không mặc định output count=input count. Không dùng `COUNT(*)` đơn lẻ vì một record thiếu và một record thừa có thể triệt tiêu.

### Gate C: restart/recovery

- Lỗi xảy ra tại cửa sổ đã định nghĩa; có bằng chứng output/metadata lúc ấy.
- Xác minh old worker dừng hoặc đã bị fenced.
- Khởi chạy lại cùng identifying `JobParameters` và snapshot/partition mapping.
- Kiểm tra reader sort order, checkpoint được phục hồi và idempotent writer.
- Đối soát business DB/ledger sau replay.
- Nếu execution còn `STARTED` mồ côi, dùng runbook/khả năng điều hành của framework; không tự sửa `BATCH_*`.

## 21. Vì sao retry OptimisticLockingFailureException vô điều kiện là nguy hiểm?

Anti-pattern minh họa:

~~~java
// Không copy vào production.
for (int attempt = 0; attempt < 100; attempt++) {
    try {
        repository.update(staleStepExecution);
        break;
    } catch (OptimisticLockingFailureException ignored) {
        // Vẫn dùng object stale, không xác minh owner.
    }
}
~~~

Sai ở những điểm sau:

1. `staleStepExecution` có version/counters/checkpoint không còn phù hợp.
2. Business effect có thể đã commit trước khi metadata conflict.
3. Worker đang cố update có thể **đã mất quyền sở hữu** partition.
4. Một retry loop có thể làm `JobRepository` DB/connection pool tăng tải.
5. “Gán version mới” vào object cũ rồi ghi lại có thể đánh mất tiến độ của owner thật.
6. Không có merge semantics cho checkpoint; không thể cộng hai offset/counters tùy tiện.

| Nguyên nhân | Hướng sửa |
| --- | --- |
| Hai workers ghi cùng StepExecution ID | Sửa dispatch/ownership, chặn double processing |
| Multi-threaded step tự update metadata ngoài framework | Bỏ custom concurrent update, sửa reader/writer state |
| Shared JobExecutionContext key | Tách key/step context, merge sau barrier |
| Duplicate request/reply | Correlation/owner fencing, reload state, idempotent writer |
| Business commit trước metadata | Recover/replay với business key, đối soát |
| Repository JDBC lock/pool saturation | Backpressure, sizing và rút transaction |
| Schema/serializer version lệch | Migration và rolling deploy compatibility test |

**Conflict là bằng chứng xung đột được phát hiện, không phải lỗi bắt buộc phải nuốt** để dashboard báo job thành công.

## 22. Observability cho concurrent metadata update

| Tín hiệu | Vì sao cần |
| --- | --- |
| `jobName`/`jobInstanceId` | Xác định logical run |
| `jobExecutionId` | Phân biệt các attempts/restart |
| `stepExecutionId`/`stepName` | Chỉ đúng row metadata |
| `snapshotId`/`partitionName` | Biết worker sở hữu phạm vi nào |
| `expectedVersion`/`persistedVersion` | Giải thích stale update |
| `workerId`/owner epoch | Xác định node nào có quyền ghi |
| `commitCount`/last checkpoint | Đặt conflict vào failure window |
| Repository transaction p95/p99 | Phân biệt contention và chậm DB |
| Hikari pending/acquisition timeouts | Metadata write có chờ connection không |
| Retry/rollback/skip counts | Phân biệt duplicate attempts với useful work |
| Unique business commits + mismatch | Xác minh dữ liệu thực |

Không log toàn bộ `ExecutionContext`/payload nhạy cảm để debug. Dùng structured logs/tracing với quyền phù hợp; `stepExecutionId` hoặc item ID không nên trở thành high-cardinality labels của Prometheus.

### Cẩn trọng với “nhiều rows” trong metadata

Nhiều `BATCH_STEP_EXECUTION` rows là điều bình thường của partitioning. Điều cần quan sát là **cùng StepExecution ID bị ghi cạnh tranh**, version không hợp lệ, context bị trộn, hoặc duplicate owner — không phải tổng số row cao.

## 23. Runbook khi phát hiện concurrent metadata update bất thường

Khi `OptimisticLockingFailureException` xuất hiện hoặc checkpoint/metadata sai lệch:

1. **Khoanh vùng** job, JobInstance, JobExecution, StepExecution ID/name, partition và timestamp.
2. **Kiểm tra ID thực sự bị tranh chấp:** cùng `StepExecutionId` hay hai StepExecutions độc lập?
3. **SELECT metadata**: `VERSION`, `STATUS`, `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT`, `ROLLBACK_COUNT`, `LAST_UPDATED`. Không sửa schema của framework.
4. **Xác minh ownership**: có duplicate delivery, hai schedulers, failover stale worker, multi-threaded step custom update hay không?
5. **Phân tích context**: input key/range, reader checkpoint, job-level promotion; không dump serialized context công khai.
6. **Xem transaction boundaries**: business DB, repository và broker có thật sự dùng cùng transaction resource không?
7. **Đối soát business output** theo unique key/version, kiểm tra email/payment/event side effects.
8. **Xác nhận worker cũ đã dừng hoặc bị fenced** trước khi redispatch.
9. **Phân loại root cause**: lost update trong heap, stale JDBC update, context overwrite, DB lock/timeout, serializer mismatch hoặc message redelivery.
10. **Khôi phục execution theo framework runbook**, không sửa trực tiếp các bảng `BATCH_*`.
11. **Giảm áp lực có kiểm soát** nếu retry storm/metadata pool saturation đang xảy ra.
12. **Tạo regression test** dùng barrier/injection tại đúng failure window.
13. **Đánh giá lại** metadata transaction latency, optimistic conflict count, last durable checkpoint, RTO và output reconciliation.
14. **Đóng sự cố** chỉ khi metadata, business data và ownership đều đúng, không phải chỉ khi exception ngừng xuất hiện.

### Những phản xạ cần tránh

- Chạy `UPDATE BATCH_STEP_EXECUTION SET VERSION=...` bằng SQL để ép qua lỗi.
- Xóa `BATCH_STEP_EXECUTION_CONTEXT` để “làm lại checkpoint”.
- Tăng `run.id` và tạo JobInstance mới khi execution cũ vẫn chạy.
- Bắt, bỏ qua `OptimisticLockingFailureException` rồi báo `COMPLETED`.
- Lấy stale object, đổi version cho bằng database rồi ghi lại các counters cũ.
- Dựa vào timestamp log ở hai JVM làm chứng cứ tuyệt đối về thứ tự commit.
- Chỉ tăng thread/JDBC pool trong khi nguyên nhân là duplicate ownership.
- Tắt `saveState` mà không có restart strategy và idempotency thay thế.

## 24. Bài tập tình huống: version 12 và hai remote workers

Một job remote partitioning xử lý snapshot 10.000 orders. Do lỗi dispatch, `StepExecutionId=501` được gửi tới **cả A và B**.

~~~text
BATCH_STEP_EXECUTION:
  STEP_EXECUTION_ID = 501
  VERSION = 12
  READ_COUNT = 2000
  COMMIT_COUNT = 10
  STATUS = STARTED

Worker A và B đều load version 12.

A muốn lưu READ_COUNT=2200, COMMIT_COUNT=11.
B muốn lưu READ_COUNT=2400, COMMIT_COUNT=12.

A đã ghi 200 orders vào business DB.
B cũng có thể đã ghi 200 orders.
Business DB và repository dùng hai transaction managers.
~~~

**Câu hỏi:**

1. Với optimistic locking chuẩn, cả A lẫn B có được cập nhật `VERSION=12` thành công không?
2. Nếu A thắng, giá trị `VERSION` và `READ_COUNT` có thể là bao nhiêu?
3. B nhận `OptimisticLockingFailureException` có chứng minh B chưa commit business output không?
4. Vì sao không được cộng `READ_COUNT` của A và B để làm “tổng”?
5. Làm sao xác định 200 orders của B khác hay trùng với 200 orders của A?
6. Vì sao `JobExecution.getStatus()==COMPLETED` chưa đủ để PASS?
7. Nếu partition0000 và partition0001 thật sự độc lập, nên có bao nhiêu StepExecution ID?
8. Hai sibling flows cùng ghi job context key `processedTotal` có cho ra tổng đúng không?
9. Nêu cách dùng `CountDownLatch` để tạo stale-version conflict có thể lặp lại.
10. Nêu test kiểm tra hai contexts khác ID được persist độc lập bằng `JobRepository`.
11. Tại sao đổi identifying `run.id` sẽ tạo rủi ro reprocess thay vì restart checkpoint cũ?
12. Nêu ba loại oracle cần kiểm chứng trước khi công bố kết quả sau recovery.

### Gợi ý đáp án

- **(1)** Không, trong mô hình hai stale copies cập nhật cùng row/version qua JDBC optimistic locking; tối đa một cập nhật version cũ thắng.
- **(2)** Thường `VERSION=13`, `READ_COUNT=2200` khi A thành công. Luôn reload DB thay vì đọc log trước commit.
- **(3)** Không. B có thể đã commit business output nhưng chưa persist metadata; hai resources không atomic mặc định.
- **(4)** `READ_COUNT` là absolute progress counter của **cùng StepExecution**, không phải hai lượng business items độc lập.
- **(5)** Kiểm tra business key, snapshot membership, partition range, ledger và source–target reconciliation.
- **(6)** Cần cả metadata đúng, output không thiếu/trùng và restart an toàn.
- **(7)** Mỗi worker partition một `StepExecution` độc lập; ít nhất hai StepExecution IDs cho hai partitions trong một attempt đúng.
- **(8)** Không. Shared context không tự là atomic counter; merge sau barrier.
- **(9)** Load hai copies trước khi release barrier, đồng thời gọi `repository.update`, assert một success/một conflict và reload version cuối.
- **(10)** Tạo hai StepExecution IDs khác nhau, update contexts qua repository và reload theo từng ID.
- **(11)** Identifying parameter mới tạo `JobInstance` khác, có thể quét lại snapshot và phát side effect lặp.
- **(12)** Metadata integrity, business reconciliation và restart/recovery/ownership.

## 25. Checklist trước production

- [ ] Xác định schema `BATCH_JOB_EXECUTION`/`BATCH_STEP_EXECUTION`/contexts đúng phiên bản Spring Batch đang triển khai.
- [ ] Phân biệt execution row `VERSION` với serialized context tables **không có version riêng**.
- [ ] Có integration test dùng hai independent copies của **cùng StepExecution ID/version**.
- [ ] Test một stale writer bị từ chối và DB version/counters được reload đúng.
- [ ] Test hai StepExecution IDs khác nhau persist context đồng thời mà không nhiễm input key/offset.
- [ ] Test read-modify-write shared `ExecutionContext` để thấy nguy cơ lost update.
- [ ] Không dùng job context làm distributed counter hoặc latch giữa parallel steps.
- [ ] Dùng latches/barriers/timeouts; không test race bằng `Thread.sleep`.
- [ ] JDBC repository thực và database/test schema tương thích production; không chỉ dùng mock.
- [ ] Test method đa thread không bị transaction cha che fixture chưa commit.
- [ ] Không ghi thẳng `BATCH_*` ngoài framework.
- [ ] Có test concurrent launch cùng identifying `JobParameters`.
- [ ] Có test duplicate delivery/stale owner của remote partitioning.
- [ ] Có test remote chunking mất reply và writer replay-safe.
- [ ] Có test commit/rollback/crash trước/sau metadata checkpoint ở nhiều transaction resources.
- [ ] Có snapshot/manifest immutable và partition ID stable cho restart.
- [ ] Writer idempotent theo business key, external effects có ledger/outbox/fencing khi cần.
- [ ] Test multi-threaded step khi các chunk hoàn tất/rollback đảo thứ tự.
- [ ] Theo dõi optimistic conflict, metadata DB lock/pool, chunk latency và RTO.
- [ ] Không retry optimistic exception vô điều kiện hay tăng concurrency khi repository đã nghẽn.
- [ ] Merge stage-specific output sau barrier, đối soát keys/version trước publication.
- [ ] Có runbook cho `STARTED` mồ côi, duplicate owners, serializer/schema compatibility.

## 26. Tài liệu tham khảo

- [Spring Batch 5.2 – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/5.2/schema-appendix.html): cột `VERSION`, bảng execution và context.
- [Spring Batch 5.2 – JobRepository Configuration](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): JDBC transaction và isolation trong create-execution.
- [Spring Batch 5.2 – Common Batch Patterns](https://docs.spring.io/spring-batch/reference/5.2/common-patterns.html): phân biệt Job/Step context và promotion sau step.
- [Spring Batch 5.2 – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): multi-threaded step, parallel steps, partitioning.
- [Spring Batch 5.2 – Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html): checkpoint/metadata và chunk transaction.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): JobInstance, JobExecution, StepExecution, ExecutionContext.
- [Spring Batch Reference – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` và restart state.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning/chunking.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): integration testing batch workflows.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries và rollback.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): test fixtures, assertions và timeout.
- [Java 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ threads trong test.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): concurrent UPDATE, row locks và serializability.
- [PostgreSQL – Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): session/lock wait diagnostics.
- [PostgreSQL – INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): idempotent business ledger.

## Ghi nhớ

**Test concurrent metadata update phải chứng minh nhiều luồng/JVM không âm thầm ghi đè tiến độ batch hoặc tạo checkpoint sai khi restart.** Trong Spring Batch JDBC, `VERSION` bảo vệ nhiều row execution bằng optimistic locking; writer stale nên nhận lỗi thay vì silently overwrite. Nhưng context serialization, shared mutable objects, business DB và middleware có failure windows riêng: **optimistic locking không tự bảo đảm exactly-once**. Hãy dùng barrier để tái hiện race, kiểm tra hai StepExecution IDs độc lập, không tự viết SQL sửa `BATCH_*` và luôn kiểm chứng **metadata, business output cùng khả năng recovery**. Một concurrent test chỉ PASS khi **state bền vững đúng, ownership rõ ràng, restart an toàn và không bỏ sót/nhân đôi hiệu ứng nghiệp vụ**.
