# Kiểm thử out-of-order completion

Một Spring Batch job chia 12 triệu giao dịch thành tám partitions có thể phát công việc theo thứ tự `partition0 → partition1 → ... → partition7` nhưng nhận kết quả theo thứ tự `partition3 → partition1 → partition7 → ... → partition0`. Điều này **không mặc nhiên là lỗi**: worker xử lý trên các thread/node khác nhau, dữ liệu có độ phức tạp khác nhau, database lock hoặc broker queue cũng tạo độ trễ khác nhau. Lỗi xuất hiện khi hệ thống **đồng nhất thứ tự hoàn tất với thứ tự nghiệp vụ**, kết hợp sai response, ghi đè trạng thái mới bằng kết quả cũ, hoặc công bố dữ liệu chưa đủ chỉ vì một worker đã báo xong.

Bài học **“Kiểm thử out-of-order completion”** thuộc chương **Ordering** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module nghiên cứu mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo bottleneck, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực. Chủ đề tập trung vào cách **chủ động tạo, quan sát và kiểm định** việc các chunk, partition và worker step **hoàn tất không cùng thứ tự được dispatch**, thay vì chỉ kiểm một JobExecution có trạng thái `COMPLETED`.

> **Nguyên tắc:** trong xử lý song song, **đúng dữ liệu** không nhất thiết đòi **đúng thứ tự kết thúc**. Chỉ áp đặt ordering ở nơi hợp đồng nghiệp vụ thực sự yêu cầu; còn ở những nơi không yêu cầu, test phải **chấp nhận mọi thứ tự hoàn tất hợp lệ** nhưng vẫn kiểm tra coverage, idempotency, correlation và kết quả bền vững.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **source order, dispatch order, start order, processor order, commit order, reply order, observed completion order và publication order**.
2. Giải thích vì sao local partitioning, remote partitioning, remote chunking và multi-threaded step có thể tạo **out-of-order completion**.
3. Tạo test **deterministic** bằng `CountDownLatch`/barrier để ép worker B hoàn tất trước worker A mà không phụ thuộc `Thread.sleep`.
4. Kiểm tra `JobRepository` và `StepExecution` theo **partition identity**, không suy ra từ vị trí trong một danh sách callback.
5. Phân biệt lời gọi writer/processor đã trả về với **transaction đã commit thành công**.
6. Chứng minh reply đến đảo thứ tự vẫn được ghép đúng `correlationId`, `JobExecutionId`, `StepExecutionId` và `chunkSequence`.
7. Tách **unordered completion** hợp lệ khỏi **missing, duplicate, stale, corrupted hoặc uncommitted completion**.
8. Kiểm tra idempotency, retry/restart, late reply và fencing khi worker cũ hoàn thành sau worker mới.
9. Thiết kế **reorder buffer, contiguous watermark, per-key ordering và publication barrier** nếu downstream cần đọc theo thứ tự.
10. Đo straggler, head-of-line blocking và tail latency để biết khi nào bảo toàn thứ tự đáng chi phí.

**Tình huống xuyên suốt:** job `dailyLedgerImport` nhận các record có `batchKey=ledger-2026-11-26` và `sequenceNo` tăng dần, chia thành bốn ranges. Worker xử lý `range 2000–2999` có dữ liệu nhẹ và commit xong trước `range 0–999` vốn có thao tác đối soát nặng. Ta cần xác nhận (a) mọi giao dịch được ghi đúng một lần, (b) manager không coi reply của range 2 là reply của range 0, và (c) nếu downstream yêu cầu publish theo sequence thì không được để `sequenceNo=2000` nhìn thấy trước khi `0–1999` sẵn sàng theo hợp đồng.

## 2. “Out of order” là thứ tự nào?

Có nhiều trục thứ tự không được trộn lẫn:

| Thứ tự | Ví dụ | Điều hệ thống có thể đảm bảo |
| --- | --- | --- |
| **Source order** | Record ID 10, 11, 12 trong file hoặc query | `ORDER BY`/file ordering trong một reader |
| **Partition mapping** | `p0=[0,1000)`, `p1=[1000,2000)` | Stable map và không overlap |
| **Dispatch order** | Manager gửi p0 trước p1 | Thứ tự gọi send, **không** đảm bảo nhận |
| **Start order** | Worker p1 bắt đầu trước p0 | Scheduler/broker quyết định |
| **Processor order** | Item 101 xử lý xong trước 100 | Concurrency, retry, blocking |
| **Commit order** | DB transaction p2 commit trước p0 | Transaction scheduler/locks |
| **Reply order** | Response p2 đến manager trước p0 | Network, broker, worker runtime |
| **Observed completion** | Manager ghi nhận p2 COMPLETED trước p0 | Metadata and callbacks |
| **Publication order** | Downstream nhìn thấy p0 rồi p1 | Chỉ khi có publication protocol |

**Đừng viết một assertion `replySequence == dispatchSequence` nếu contract không đòi điều đó.** Tương tự, `JobExecution.getStepExecutions()` trả tập thực thi; thứ tự iterate của collection hoặc thứ tự log **không** phải cam kết hoàn tất theo partition.

## 3. “Hoàn tất” phải có định nghĩa rõ

Trong Spring Batch có các mốc khác nhau:

~~~text
Worker nhận request
  → reader/processor xong
  → writer.write(...) trả về
  → chunk transaction COMMIT
  → StepExecution status được framework tổng hợp/persist
  → worker phát reply/status
  → manager correlate và ghi nhận outcome
  → toàn batch được verify/publish
~~~

Một worker có thể đã commit nhiều chunk rồi thất bại trước khi metadata/reply được xác nhận. Một response có thể đến manager sau timeout dù business output đã commit. Vì vậy:

- **Method completion** không đồng nghĩa database commit.
- **Chunk commit** không đồng nghĩa toàn partition đã xong.
- **Worker step COMPLETED** không đồng nghĩa mọi business effects đã được đối soát.
- **Broker ACK/reply publish** không đồng nghĩa manager đã correlate đúng.
- **Manager aggregation COMPLETED** không đồng nghĩa downstream đã thấy một batch được công bố.

Khi nói “kiểm thử out-of-order completion”, phải nêu **mốc completion** đang ép đảo thứ tự. Nếu chỉ kiểm hai processor callbacks, không được tuyên bố đã kiểm đảo **transaction commit order**.

## 4. Mô hình nào dễ xuất hiện completion đảo thứ tự?

| Mô hình Spring Batch | Đơn vị làm việc đồng thời | Cơ chế đảo thứ tự | Test trọng tâm |
| --- | --- | --- | --- |
| **Local partitioning** | Nhiều worker `StepExecution` trong cùng JVM | Executor scheduling, range skew, DB lock | Partition identity và StepExecution outcomes |
| **Remote partitioning** | Worker steps trong các JVM/nodes | Broker queue, node load, DB I/O, retry | Worker status, reply correlation, late completion |
| **Remote chunking** | Các `ChunkRequest` từ manager reader | Worker pool, network, chunk weight, redelivery | Chunk sequence/correlation, in-flight outcomes |
| **Multi-threaded step** | Nhiều chunks trong một `StepExecution` | Thread schedule và shared components | Reader/writer thread safety, checkpoint/order |
| **Parallel steps/flows** | Các independent flows | Chi phí và dependencies khác nhau | Join/flow transitions và output barriers |

**Trọng tâm khác nhau:** remote partitioning giao một **worker step/ExecutionContext**; remote chunking gửi **items trong chunk** và manager thường giữ reader. Một test chỉ gửi nhiều messages qua `ExecutorChannel` trong cùng JVM **không** chứng minh middleware remote có routing/ACK/redelivery đúng.

## 5. Một ví dụ đảo thứ tự hoàn tất hợp lệ

~~~text
Manager dispatch:   P0 ---- P1 ---- P2 ---- P3

Worker P0:          [=======================]  hoàn tất thứ 4
Worker P1:             [========]               hoàn tất thứ 2
Worker P2:                [===]                  hoàn tất thứ 1
Worker P3:                   [==========]        hoàn tất thứ 3

Completion observed: P2, P1, P3, P0
~~~

Nếu các partitions có **business keys không giao nhau**, writer idempotent và mỗi partition cuối cùng đều thành công, thứ tự `P2,P1,P3,P0` có thể hoàn toàn đúng. Nhưng nếu consumer mong chờ event `sequence=0` trước `sequence=2000`, cần một **publication/reordering layer** riêng.

### Sơ đồ luồng xử lý

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant W0 as Worker P0
    participant W1 as Worker P1
    participant W2 as Worker P2
    participant DB as Business DB
    M->>W0: Dispatch P0
    M->>W1: Dispatch P1
    M->>W2: Dispatch P2
    W2->>DB: Commit output P2
    W2-->>M: Reply P2 COMPLETED
    W1->>DB: Commit output P1
    W1-->>M: Reply P1 COMPLETED
    W0->>DB: Commit output P0
    W0-->>M: Reply P0 COMPLETED
    Note over M: Aggregate theo partition identity, không theo vị trí reply
~~~

Đây là **sơ đồ logic**; trong một deployment nhất định manager có thể quan sát trạng thái qua JobRepository thay vì một reply flow giống như hình. Test phải gắn với topology thật.

## 6. Bất biến chính: unordered success phải vẫn đúng dữ liệu

Với một snapshot đầu vào bất biến:

1. **Coverage:** mỗi business record expected thuộc đúng một partition/range hoặc một nhóm được hợp đồng cho phép.
2. **No overlap:** một record không được giao cho hai workers ngoài recovery/retry có chủ đích.
3. **Identity:** completion nào cũng gắn đúng `jobExecutionId`, `stepExecutionId`, `partitionName` hoặc `chunkSequence`.
4. **Outcome:** chỉ coi COMPLETED khi work thật đạt điều kiện commit/validation, không phải chỉ nhận response.
5. **Idempotency:** retry/redelivery không tạo duplicate logical effect, kể cả khi completion đến muộn.
6. **Reconciliation:** output key/value và filtered/quarantined set đúng, không chỉ `COUNT(*)`.
7. **Stable restart:** partition map/source version không đổi trong cùng JobInstance nếu cần phục hồi checkpoint.
8. **Publication:** nếu có thứ tự nghiệp vụ, downstream chỉ nhìn những kết quả đã qua gate thích hợp.

**Test cần có cả happy path và negative controls.** Ví dụ sửa cố ý code correlate theo chỉ số `pending[0]` thay vì request ID: test phải phát hiện P2 reply bị gán nhầm P0. Nếu test vẫn xanh, assertion chưa đủ sức bảo vệ correctness.

## 7. Fixture dữ liệu cho phép kiểm tra độc lập

Một fixture PostgreSQL tối giản:

~~~sql
CREATE TABLE staged_ledger (
    batch_key      VARCHAR(120) NOT NULL,
    sequence_no    BIGINT NOT NULL,
    tenant_id      VARCHAR(100) NOT NULL,
    amount         NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (batch_key, sequence_no)
);

CREATE TABLE ledger_output (
    batch_key      VARCHAR(120) NOT NULL,
    sequence_no    BIGINT NOT NULL,
    tenant_id      VARCHAR(100) NOT NULL,
    net_amount     NUMERIC(18,2) NOT NULL,
    source_hash    VARCHAR(128) NOT NULL,
    PRIMARY KEY (batch_key, sequence_no)
);

CREATE INDEX idx_ledger_source_range
    ON staged_ledger(batch_key, sequence_no);
~~~

Tạo 4.000 records với `sequence_no` thuộc `[0,4000)`, chia thành bốn ranges nửa mở `[0,1000)`, `[1000,2000)`, `[2000,3000)` và `[3000,4000)`. Thêm fixture phụ cho:

- **Sparse IDs:** 1, 5, 100, 2001, 3999 để kiểm reader không nhầm `endExclusive`.
- **Hai tenants/batches:** IDs giống nhau nhưng `batchKey` khác để kiểm isolation.
- **Một partition rất chậm:** chèn failpoint, không dùng random delay.
- **Zero/one item:** kiểm empty/degenerate partition không treo barrier.
- **Duplicate delivery có chủ đích:** cùng logical request được chạy lại; business key vẫn đúng.
- **Value mismatch:** cùng ID nhưng netAmount/sourceHash khác; writer phải phát hiện conflict.

**Nguồn phải bất biến trong một lượt benchmark/restart.** Nếu staging thay đổi sau khi manager chốt partition map, test có thể thấy gap/overlap giả hoặc kết quả phụ thuộc timing source mutation.

## 8. Test pyramid: test điều gì ở tầng nào?

| Tầng | Mục tiêu | Công cụ/phương pháp |
| --- | --- | --- |
| **Unit** | Pure ordering aggregator, contiguous gate, correlation map | JUnit 5, fake completion events |
| **Concurrency component** | Chứng minh P1 kết thúc trước P0 deterministic | `ExecutorService`, `CountDownLatch` |
| **Spring Batch integration** | Worker StepExecutions + DB commit + partition metadata | `@SpringBatchTest`, `JobLauncherTestUtils`, PostgreSQL |
| **Broker integration** | Out-of-order replies, redelivery, late message | Hai JVM, RabbitMQ/JMS/Kafka theo topology |
| **Crash/restart** | Partial commits, stale owner, new JobExecution | Kill child JVM/process, durable DB/JobRepository |
| **Load/performance** | Stragglers, buffer, head-of-line blocking | Thống kê p95/p99, queue age, throughput |

**Không phải mọi test đều cần broker/cluster**, nhưng không dùng một fake in-memory channel để kết luận broker guarantees. Nếu bài test chỉ kiểm pure correlation function, fake events là đủ; nếu kiểm reply routing, phải có transport và consumer topology thật.

## 9. Tạo đảo thứ tự có chủ đích bằng CountDownLatch

**Không dùng** `Thread.sleep(1000)` rồi dự đoán P0 sẽ xong chậm hơn P1. Scheduler, CI, GC và database có thể làm kết quả đảo ngược. Dùng hai latches:

~~~java
final class OutOfOrderGate {
    private final CountDownLatch slowStarted = new CountDownLatch(1);
    private final CountDownLatch releaseSlow = new CountDownLatch(1);

    void beforeSlowCompletes() throws InterruptedException {
        slowStarted.countDown();
        if (!releaseSlow.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Slow worker gate timed out");
        }
    }

    void awaitSlowStarted() throws InterruptedException {
        if (!slowStarted.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Slow worker did not start");
        }
    }

    void release() {
        releaseSlow.countDown();
    }
}
~~~

Khi slow worker tới failpoint, nó báo đã bắt đầu và chờ. Test runner đợi tín hiệu, chạy fast worker, chờ **fast completion thực**, rồi mới nhả slow worker. Như vậy test **chủ động tạo thứ tự** thay vì chỉ đo timing ngẫu nhiên.

**Cần timeout và `finally`**: nếu fast worker lỗi hoặc assert fail giữa chừng, phải release slow worker và shutdown executor, tránh để CI treo. Đặt failpoint tại **đúng milestone** định kiểm: nếu chặn trước `processor.process`, ta mới chứng minh processor/worker completion order, **không tự chứng minh commit order**.

## 10. Ví dụ JUnit 5: P1 hoàn tất trước P0

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.*;

class OutOfOrderCompletionTest {

    @Test
    void fastPartitionCompletesBeforeEarlierDispatchedPartition()
            throws Exception {

        OutOfOrderGate gate = new OutOfOrderGate();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Queue<String> completionOrder = new ConcurrentLinkedQueue<>();

        try {
            Future<String> slow = pool.submit(() -> {
                gate.beforeSlowCompletes();
                completionOrder.add("partition0");
                return "partition0";
            });

            gate.awaitSlowStarted();

            Future<String> fast = pool.submit(() -> {
                completionOrder.add("partition1");
                return "partition1";
            });

            // Fast must finish while slow is still blocked.
            assertEquals("partition1", fast.get(10, TimeUnit.SECONDS));
            assertFalse(slow.isDone());

            gate.release();
            assertEquals("partition0", slow.get(10, TimeUnit.SECONDS));

            assertEquals(List.of("partition1", "partition0"),
                    List.copyOf(completionOrder));
        } finally {
            gate.release();
            pool.shutdownNow();
        }
    }
}
~~~

Đây là **concurrency component test**, chưa chạy Spring Batch, DB hay middleware. Nó chứng minh rằng **completion callbacks có thể đảo thứ tự dispatch** và test có thể ép điều đó đáng tin. Phần sau sẽ nâng thành worker `StepExecution` thật và transaction/broker outcome.

**Một cách đọc test đúng:** `completionOrder.add` là event sau khi code trong task đến điểm định nghĩa “completed”. Nếu muốn chứng minh **database đã commit**, không được ghi event ngay ở `ItemWriter.write`; cần đo ở post-commit hook hoặc query từ transaction khác sau commit.

## 11. Tách completion order khỏi identity và payload

Một manager nhận responses `P2,P0,P1` nhưng dữ liệu dự kiến là `{P0,P1,P2}`. **Assertion đúng**:

~~~text
Observed completion order:  P2 → P0 → P1
Expected partition set:     {P0,P1,P2}

PASS khi:
  mỗi expected partition có đúng một final logical outcome hợp lệ,
  mỗi outcome gắn đúng partition + execution identity,
  không có extra/missing completion,
  mọi business effects được xác nhận đúng.
~~~

Sai:

~~~java
assertEquals(List.of("P0", "P1", "P2"), receivedReplyNames);
~~~

Nếu hệ thống **không có yêu cầu** đúng thứ tự reply, assertion này tạo false failure. Ngược lại, chỉ `assertEquals(3, receivedReplyNames.size())` có thể bỏ sót `P1` xuất hiện hai lần và `P2` biến mất.

Test đúng cần so sánh **tập identity**, kiểm **bội số và trạng thái**:

~~~java
List<String> received = List.of("P2", "P0", "P1");
Set<String> expected = Set.of("P0", "P1", "P2");

assertEquals(expected, new HashSet<>(received));
assertEquals(expected.size(), received.size());
~~~

Nhưng **đếm size/tập vẫn chưa kiểm payload**: nếu reply `P2` chứa kết quả của `P0` do bug serialization/correlation, danh sách tên vẫn đẹp. Cần assert `StepExecutionId`, source range/checksum và business output đúng theo partition.

## 12. Completion collector không được phụ thuộc vị trí nhận

Ví dụ mô hình aggregator ở lớp ứng dụng (không phải API Spring Batch nội bộ):

~~~java
record PartitionOutcome(
        long jobExecutionId,
        long stepExecutionId,
        String partitionName,
        String status,
        String sourceVersion) {}

final class PartitionOutcomeCollector {
    private final ConcurrentMap<Long, PartitionOutcome> outcomes =
            new ConcurrentHashMap<>();

    void accept(PartitionOutcome incoming) {
        PartitionOutcome previous = outcomes.putIfAbsent(
                incoming.stepExecutionId(), incoming);

        if (previous != null && !previous.equals(incoming)) {
            throw new IllegalStateException(
                    "Conflicting completion for StepExecution "
                            + incoming.stepExecutionId());
        }
    }

    Map<Long, PartitionOutcome> snapshot() {
        return Map.copyOf(outcomes);
    }
}
~~~

**Ý nghĩa:** lần nhận đầu tiên ghi theo `stepExecutionId`, reply lặp **cùng nội dung** có thể được nhận idempotently; reply cùng ID nhưng khác payload là conflict. Không dùng `List.add` rồi ghép phần tử thứ i của replies với phần tử thứ i của dispatch.

**Giới hạn quan trọng:**

- `ConcurrentHashMap` là **in-memory**; không bảo vệ trạng thái sau manager JVM crash. Production cần dựa `JobRepository`, durable request ledger hoặc protocol reply phù hợp.
- `stepExecutionId` chỉ đủ khi gắn đúng job/repository namespace; nếu tương tác nhiều JobRepositories hoặc tenants, khóa tổng hợp phải mang đầy đủ namespace.
- Khi restart, worker StepExecution mới có ID khác; **logical partitionName** có thể giống, nên không gộp outcome của attempt cũ và mới chỉ bằng một map key quá đơn giản.
- `status="COMPLETED"` là thông tin reply, **không tự chứng minh DB commit hay JobRepository status** nếu reply không đáng tin.

## 13. Dùng Half-open ranges để loại trừ overlap

Trong local/remote partitioning, một lỗi có thể giả dạng out-of-order: hai workers cùng đọc record tại boundary. Mỗi partition nên có một range ổn định:

~~~text
P0: [0, 1000)
P1: [1000, 2000)
P2: [2000, 3000)
P3: [3000, 4000)
~~~

Reader SQL:

~~~sql
SELECT batch_key, sequence_no, tenant_id, amount
FROM staged_ledger
WHERE batch_key = :batchKey
  AND sequence_no >= :startInclusive
  AND sequence_no <  :endExclusive
ORDER BY sequence_no;
~~~

`ORDER BY` đảm bảo thứ tự đọc **trong query này**, không đảm bảo commit, reply hoặc publish order giữa các workers. `BETWEEN start AND endExclusive` thường sai vì `BETWEEN` inclusive ở cả hai đầu.

**Unit test partition map** cần chứng minh:

1. Mọi range có `start < end` trừ empty-work policy được định nghĩa.
2. `end(P0)=start(P1)` và tương tự cho các ranges liền kề.
3. Union ranges bằng domain expected của snapshot.
4. Không có record nào xuất hiện ở hai partitions trong happy-path không retry.
5. Partition names và bounds giữ nguyên khi restart cùng JobInstance.

Như vậy một test **đảo completion order** sẽ không bị nhiễu bởi lỗi **partition overlap**.

## 14. @StepScope giúp tách reader state, không ép completion order

Worker step nhận `ExecutionContext` riêng:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<LedgerInput> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['startInclusive']}") Long start,
        @Value("#{stepExecutionContext['endExclusive']}") Long end) {

    return new JdbcCursorItemReaderBuilder<LedgerInput>()
            .name("ledgerPartitionReader")
            .dataSource(dataSource)
            .sql("""
                SELECT batch_key, sequence_no, tenant_id, amount
                FROM staged_ledger
                WHERE batch_key = ?
                  AND sequence_no >= ?
                  AND sequence_no < ?
                ORDER BY sequence_no
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, batchKey);
                ps.setLong(2, start);
                ps.setLong(3, end);
            })
            .rowMapper((rs, index) -> new LedgerInput(
                    rs.getString("batch_key"),
                    rs.getLong("sequence_no"),
                    rs.getString("tenant_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

`LedgerInput` là record/domain class của ứng dụng. Đây là khung Spring Batch 5.x/Java 17+, cần cấu hình datasource, import, test schema và bean wiring phù hợp. `@StepScope` giúp tạo reader state riêng per StepExecution, nhưng **không đồng bộ thời điểm kết thúc** của workers. Processor/writer singleton có mutable fields vẫn có thể bị race.

**Không đổi source version hoặc partition boundaries** trong lúc một JobInstance đang restart. Checkpoint đúng về mặt position nhưng đọc nguồn đã thay đổi có thể làm kết quả sai dù mọi completion spans đều đúng identity.

## 15. TaskExecutorPartitionHandler và thứ tự thực thi

Ví dụ cấu hình local partitioning (Spring Batch 5.x):

~~~java
@Bean
ThreadPoolTaskExecutor workerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("partition-");
    executor.initialize();
    return executor;
}

@Bean
TaskExecutorPartitionHandler localHandler(
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("workerExecutor") TaskExecutor executor) {
    TaskExecutorPartitionHandler handler =
            new TaskExecutorPartitionHandler();
    handler.setStep(workerStep);
    handler.setTaskExecutor(executor);
    handler.setGridSize(4);
    return handler;
}

@Bean
Step managerStep(
        JobRepository repository,
        Partitioner ledgerPartitioner,
        TaskExecutorPartitionHandler localHandler) {
    return new StepBuilder("managerStep", repository)
            .partitioner("workerStep", ledgerPartitioner)
            .partitionHandler(localHandler)
            .build();
}
~~~

`gridSize(4)` **không cam kết** đúng bốn threads active hoặc các partitions bắt đầu/hoàn tất theo thứ tự map insertion. Executor queue, partitioner, DB pool và workload quyết định thực tế. Test phải có **ít nhất hai workers thực thi đồng thời**; nếu pool vô tình dùng một thread, out-of-order test ép P1 xong trước P0 sẽ timeout/fail thay vì xanh giả.

**Không thêm `.taskExecutor(...)` vào worker chunk step** khi đang test thuần local partitioning, trừ khi cố ý kiểm hai tầng concurrency. Nếu làm thế, source reader/ItemStream thread safety và commit order trở nên phức tạp hơn.

## 16. Hook kiểm thử vào worker StepExecution

Để test thực sự chạy trong Spring Batch, dùng một listener **chỉ bật ở test profile**, có gates riêng cho một partition:

~~~java
final class PartitionCompletionGate implements StepExecutionListener {
    private final CountDownLatch slowStarted = new CountDownLatch(1);
    private final CountDownLatch releaseSlow = new CountDownLatch(1);
    private final CountDownLatch fastReachedAfterStep = new CountDownLatch(1);
    private final Queue<String> afterStepOrder =
            new ConcurrentLinkedQueue<>();

    @Override
    public void beforeStep(StepExecution step) {
        if (step.getStepName().endsWith(":partition0")) {
            slowStarted.countDown();
            awaitOrFail(releaseSlow, "slow worker release");
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        String name = step.getStepName();
        afterStepOrder.add(name);
        if (name.endsWith(":partition1")) {
            fastReachedAfterStep.countDown();
        }
        return step.getExitStatus();
    }

    void waitForSlow() { awaitOrFail(slowStarted, "slow start"); }
    void waitForFastAfterStep() {
        awaitOrFail(fastReachedAfterStep, "fast afterStep");
    }
    void release() { releaseSlow.countDown(); }
    List<String> order() { return List.copyOf(afterStepOrder); }

    private static void awaitOrFail(
            CountDownLatch latch, String milestone) {
        try {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timeout: " + milestone);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted: " + milestone, e);
        }
    }
}
~~~

**Cảnh báo về ngữ nghĩa:** `afterStep` cho biết **listener được gọi** sau worker step logic, **không nhất thiết** báo metadata `StepExecution` đã được persist hoặc transaction ngoài DB đã commit tất cả. Chỉ dùng `afterStepOrder` để khẳng định **callback order**. Sau khi `JobExecution` kết thúc, test còn phải truy vấn JobRepository và business DB.

Gates dùng chung trong **một test run duy nhất**; tạo listener/probe mới hoặc reset test context giữa các tests để latches không bị kế thừa từ test trước.

## 17. @SpringBatchTest: ép worker StepExecution đảo thứ tự

Một integration-test skeleton:

~~~java
@SpringBatchTest
@SpringBootTest
class LocalPartitionCompletionIntegrationTest {
    @Autowired JobLauncherTestUtils jobs;
    @Autowired PartitionCompletionGate gate;
    @Autowired JdbcTemplate jdbc;

    @Test
    void laterPartitionCanFinishFirstButJobRemainsCorrect()
            throws Exception {
        String batchKey = "ordering-it-001";
        seedImmutableLedger(batchKey, 4000);

        JobParameters params = new JobParametersBuilder()
                .addString("batchKey", batchKey)
                .addLong("sourceVersion", 1L)
                .toJobParameters();

        ExecutorService launcher = Executors.newSingleThreadExecutor();
        try {
            Future<JobExecution> job = launcher.submit(
                    () -> jobs.launchJob(params));

            gate.waitForSlow();
            gate.waitForFastAfterStep();
            assertFalse(job.isDone());
            gate.release();

            JobExecution execution = job.get(60, TimeUnit.SECONDS);
            assertEquals(BatchStatus.COMPLETED, execution.getStatus());
            assertTrue(gate.order().indexOf("workerStep:partition1")
                    < gate.order().indexOf("workerStep:partition0"));
            assertExpectedWorkerStepStates(execution);
            assertExactLedgerKeysAndValues(batchKey, jdbc);
        } finally {
            gate.release();
            launcher.shutdownNow();
        }
    }
}
~~~

`seedImmutableLedger`, `assertExpectedWorkerStepStates` và `assertExactLedgerKeysAndValues` là **test helpers ứng dụng cần tự viết**. Cấu hình test phải gắn `PartitionCompletionGate` vào **worker Step**, dùng `TaskExecutor` ít nhất hai active workers, partitioner sinh các ranges không rỗng, và inject Job bean đúng cho `JobLauncherTestUtils` nếu project có nhiều jobs. `JobLauncher` test setup phải cho phép test thread đợi `JobExecution` return theo contract launcher đang dùng; khi có `TaskExecutorJobLauncher` bất đồng bộ, test cần chờ status cuối qua JobRepository thay vì mặc định `launchJob` trả sau completion.

**Không dùng đơn lẻ `assertFalse(job.isDone())` làm bằng chứng concurrency**; tín hiệu `gate.waitForFastAfterStep()` khi P0 vẫn bị chặn mới là bằng chứng **có một worker khác vượt qua điểm chặn**.

## 18. Xác minh worker StepExecution theo ID, không theo thứ tự collection

Sau job:

~~~java
Map<String, StepExecution> byStepName = execution
        .getStepExecutions()
        .stream()
        .filter(s -> s.getStepName().startsWith("workerStep:"))
        .collect(Collectors.toMap(
                StepExecution::getStepName,
                Function.identity()));

assertEquals(Set.of(
        "workerStep:partition0",
        "workerStep:partition1",
        "workerStep:partition2",
        "workerStep:partition3"), byStepName.keySet());

assertTrue(byStepName.values().stream()
        .allMatch(s -> s.getStatus() == BatchStatus.COMPLETED));
~~~

Nếu có **restart**, cùng logical partition name có thể có **nhiều StepExecutions qua những JobExecutions khác nhau**; chỉ chọn một execution cụ thể hoặc group theo `JobExecutionId + StepExecutionId`. Trong test một happy-path JobExecution, map tên giúp phát hiện partition thiếu/trùng; trong forensic job history phải giữ tất cả attempts.

**Đừng dùng thứ tự `execution.getStepExecutions().iterator()` làm bằng chứng temporal order**. Thứ tự repository collection không phải completion ordering contract.

## 19. Commit order phải đo sau transaction, không sau writer callback

Trong chunk-oriented step, `ItemWriter.write` chạy trong transaction. Nếu test làm:

~~~java
void write(Chunk<? extends Output> items) {
    delegate.write(items);
    completionOrder.add("committed"); // SAI: commit chưa chắc xảy ra
}
~~~

Một exception có thể xảy ra sau khi writer trả về và làm transaction rollback. Event ấy chỉ là **writer-invoked**, không phải **commit-verified**.

Khi dùng Spring-managed transaction, có thể instrument outcome như sau:

~~~java
void registerCommitProbe(String partition,
                         Queue<String> committedPartitions) {
    if (!TransactionSynchronizationManager.isSynchronizationActive()) {
        throw new IllegalStateException("No active synchronization");
    }
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    committedPartitions.add(partition);
                }
            });
}
~~~

**Ràng buộc:** callback chỉ báo transaction manager đã thông báo commit **ở resource đang quản lý**. Nó không có nghĩa remote broker ACK hoặc mọi external side effects cùng commit. Nếu JobRepository dùng DB khác, callback business DB không xác nhận đồng thời metadata DB. Test nên **query output từ một connection/transaction khác** sau callback để xác minh committed rows thật, đồng thời kiểm JobRepository ở mốc framework hoàn tất.

**Phân biệt trong assertions:**

- `afterStepOrder`: thời điểm callback `afterStep`.
- `chunkCommitEvents`: business transaction commits đã quan sát.
- `replyReceivedOrder`: thứ tự manager nhận replies.
- `publishedSequenceOrder`: thứ tự downstream được phép nhìn dữ liệu.

Chúng có thể khác nhau và **đều hợp lệ** nếu hợp đồng dữ liệu được bảo vệ.

## 20. Đồng thời không đồng nghĩa muốn commit theo thứ tự nào cũng được

Đối với **upsert độc lập theo business key** `(batch_key,sequence_no)`, P2 commit trước P0 không làm output sai về tập khóa/giá trị. Nhưng các tác động **phụ thuộc lịch sử** có thể không giao hoán:

~~~text
Event E1: account.balance = 100
Event E2: account.balance = account.balance + 20
Event E3: account.balance = account.balance * 2

E1 → E2 → E3  => 240
E1 → E3 → E2  => 220
~~~

Nếu workers hoàn tất đảo thứ tự và apply các operations như các transaction độc lập, kết quả có thể sai. Không đủ chỉ unique `eventId`; cần **per-account serialization, sequence gate, optimistic version check hoặc ordered fold**.

**Đối chiếu hai bài toán:**

| Đặc tính nghiệp vụ | Cho phép out-of-order commit? | Giải pháp |
| --- | --- | --- |
| Insert record theo unique key không phụ thuộc nhau | Thường có | Idempotency + set/value reconciliation |
| Tính tổng giao hoán với operation ledger | Có thể, nếu phép tổng/rounding và dedup đúng | Ledger + atomic reduce |
| Update “latest status” theo event version | Chỉ nếu stale version bị từ chối | Compare-and-set version |
| Xử lý debit/credit theo lịch sử tài khoản | Không tự do | Per-key ordered processing/ledger |
| Xuất báo cáo theo sequence bắt buộc | Completion có thể đảo, publication phải ordered | Reorder buffer/contiguous watermark |
| Duyệt file CSV rồi ghi append vào một file chung | Không an toàn nếu không có protocol | Per-partition files + merge theo sequence |

Hãy **định nghĩa phép biến đổi có giao hoán không** trước khi chọn chiến lược ordering, không cứ thấy output commit đảo thứ tự là thêm global mutex làm mất scaling.

## 21. Remote chunking: dispatch C1 trước nhưng nhận C2 trước

Trong **remote chunking**, manager giữ reader và gửi nhiều `ChunkRequest` tới workers qua middleware. Các requests có thể đến workers khác nhau hoặc một worker có thể chậm bất thường:

~~~mermaid
sequenceDiagram
    participant M as Manager Reader
    participant Q as Broker
    participant A as Worker A
    participant B as Worker B
    M->>Q: C1 seq=1
    M->>Q: C2 seq=2
    Q->>A: C1
    Q->>B: C2
    B-->>M: Reply C2 COMMITTED/processed
    Note over M: C1 vẫn pending, không gán Reply C2 cho C1
    A-->>M: Reply C1 COMMITTED/processed
    Note over M: Đủ cả hai logical outcomes mới qua barrier
~~~

**Điều phải kiểm trong test:**

1. Request C1 và C2 có **identity độc lập**; sequence phải gắn cùng `JobExecution/StepExecution` hoặc batch namespace thích hợp.
2. Manager nhận C2 trước nhưng chỉ chuyển state của **C2** sang completed; C1 vẫn pending.
3. Không coi C2 là “chunk cuối” của toàn batch nếu C1 chưa có outcome hợp lệ.
4. Nếu C2 reply trùng, chỉ ghi nhận **một logical completion**, nhưng phải detect nếu nội dung khác.
5. Nếu C1 rollback, manager phản ánh failure/retry theo policy thay vì cộng bù status bằng C2.
6. Sau retry, writer bảo đảm business effects đúng dù cùng ChunkRequest được redeliver.

**Không ép manager khởi tạo một chunk mới chỉ khi reply trước đã về nếu nghiệp vụ không cần order.** Làm vậy serialize toàn pipeline và đánh mất lợi ích remote chunking. Thay vào đó, dùng **bounded in-flight budget và correlation per request**.

## 22. Correlation keys phải đầy đủ hơn chunkSequence

Một protocol ứng dụng có thể dùng envelope:

~~~java
record ReplyKey(
        String repositoryNamespace,
        long jobExecutionId,
        long stepExecutionId,
        long chunkSequence) {}

record ChunkResult(
        ReplyKey key,
        String requestCorrelationId,
        String outcome,
        String payloadHash) {}
~~~

Các kiểu trên là **lớp minh họa của ứng dụng**, không phải chữ ký constructor của `ChunkRequest`/`ChunkResponse` trong Spring Batch. Metadata sẵn có và header mapping phải lấy theo **phiên bản Spring Batch/Spring Integration đang chạy**.

**Bẫy thường gặp:** hai executions cùng có `chunkSequence=17`, nhưng một thuộc `JobExecution 845` và một thuộc `846`. Nếu registry chỉ keyed theo sequence, reply của execution cũ có thể “đánh dấu xong” chunk của execution mới. Tương tự, một message bị redeliver có thể mang cùng logical request nhưng delivery attempt khác.

### Quy tắc correlation

- Ghép reply theo **đúng request hiện hành**, không theo index của list dispatch.
- Kiểm job/step execution identity và source snapshot version.
- Lưu trạng thái `pending/committed/failed/unknown` theo protocol.
- Với duplicate reply **cùng ID và cùng outcome**, xử lý idempotently.
- Với cùng ID nhưng **khác outcome/payload hash**, alert/reconcile; không chấp nhận last-write-wins.
- Với reply của execution đã hết hiệu lực, ghi `stale_reply` và điều tra committed side effects, không tự gán vào execution hiện hành.

## 23. Unit test synthetic replies đến sai thứ tự

Một fake correlation registry đủ để kiểm riêng logic order:

~~~java
final class ChunkReplyRegistry {
    private final ConcurrentMap<ReplyKey, ChunkResult> results =
            new ConcurrentHashMap<>();
    private final Set<ReplyKey> expected;

    ChunkReplyRegistry(Set<ReplyKey> expected) {
        this.expected = Set.copyOf(expected);
    }

    void onReply(ChunkResult reply) {
        if (!expected.contains(reply.key())) {
            throw new IllegalArgumentException(
                    "Unknown or stale reply: " + reply.key());
        }
        ChunkResult previous =
                results.putIfAbsent(reply.key(), reply);
        if (previous != null && !previous.equals(reply)) {
            throw new IllegalStateException("Conflicting duplicate reply");
        }
    }

    boolean allHaveOutcomes() {
        return results.keySet().containsAll(expected);
    }

    Map<ReplyKey, ChunkResult> snapshot() {
        return Map.copyOf(results);
    }
}
~~~

Test:

~~~java
@Test
void acceptsOutOfOrderRepliesWithoutMixingRequests() {
    ReplyKey c1 = new ReplyKey("repo-A", 845L, 880L, 1L);
    ReplyKey c2 = new ReplyKey("repo-A", 845L, 880L, 2L);
    ChunkReplyRegistry registry =
            new ChunkReplyRegistry(Set.of(c1, c2));

    ChunkResult second =
            new ChunkResult(c2, "request-C2", "COMPLETED", "hash-2");
    ChunkResult first =
            new ChunkResult(c1, "request-C1", "COMPLETED", "hash-1");

    registry.onReply(second);
    assertFalse(registry.allHaveOutcomes());
    assertEquals(second, registry.snapshot().get(c2));
    assertFalse(registry.snapshot().containsKey(c1));

    registry.onReply(first);
    registry.onReply(second); // Same duplicate is harmless.
    assertTrue(registry.allHaveOutcomes());
    assertEquals(first, registry.snapshot().get(c1));
    assertEquals(2, registry.snapshot().size());
}
~~~

**Giới hạn:** `allHaveOutcomes()` chỉ nói đã thấy một result cho mỗi expected key, **không tự phân biệt mọi outcome là thành công**. Production phải kiểm status, StepExecution và business reconciliation trước khi aggregate success. Registry trên còn **in-memory**, không dùng làm durable pending ledger qua manager crash.

## 24. Tại sao ACK và reply không đồng nghĩa transaction hoàn tất?

~~~text
T1 Worker nhận C1
T2 Worker xử lý items
T3 DB commit thành công
T4 Worker gửi ChunkResponse
T5 Broker ACK request / reply transport xác nhận
T6 Manager nhận reply và correlate
~~~

Tùy container/broker, ACK có thể đến trước/sau reply hoặc bị mất; những mốc này **không cùng một ACID transaction** mặc định.

Kịch bản:

~~~text
Worker B commit C2 ở T3.
B chết trước khi gửi response ở T4.
Broker redeliver C2 tới Worker C.
C xử lý lại nhưng writer idempotent, không tạo effect lần hai.
Manager cuối cùng nhận outcome hợp lệ.
~~~

Trace có thể hiển thị hai attempts, nhưng business output chỉ có **một logical operation**. **Không lấy số reply, số ACK hoặc số lần gọi writer làm số item đã commit mới**.

**Test bắt buộc:** inject crash **sau commit nhưng trước reply**, sau đó query DB và kiểm broker redelivery/correlation. Nếu dùng một fake `ItemWriter` trả về không chứng minh DB commit, test sẽ không bảo vệ đúng khoảng lỗi.

## 25. Remote partitioning: worker step P2 hoàn tất trước P0

Trong remote partitioning, manager phân phối `StepExecutionRequest` và worker thường có reader riêng theo `ExecutionContext`. Có deployment nhận reply rõ, có deployment lấy kết quả từ JobRepository; **điểm chung** là worker StepExecutions có identity và outcome riêng.

**Test tình huống:**

~~~text
Manager JobExecution 845 gửi P0, P1, P2.
Worker A giữ P0 do DB lock hoặc injected gate.
Worker B xử lý xong P2 và persist StepExecution COMPLETED.
Worker C xử lý xong P1.
Worker A cuối cùng xử lý xong P0.
Manager aggregate tất cả theo StepExecution identity.
~~~

**Assertion:** P2 COMPLETED trước P0 **không** khiến manager đánh dấu `P0 COMPLETED`; `StepExecution` của P2 chứa đúng range/key/response. Khi tất cả worker outcomes hợp lệ, manager có thể COMPLETED và downstream publish theo batch barrier nếu cần.

### Không giả định reply của remote partitioning luôn cùng kiểu

`TaskExecutorPartitionHandler` chạy trong một JVM; remote partitioning qua Spring Batch Integration có thể dùng gateway/handler, broker và shared repository. **Cách manager xác định worker đã hoàn tất** phụ thuộc cấu hình remote partitioning cụ thể. Kiểm thử phải xem dữ liệu ở **mốc framework thực dùng** chứ không tự dựng một reply contract không tồn tại trong deployment.

## 26. Late reply sau restart: cùng partition, khác execution

~~~mermaid
sequenceDiagram
    participant M1 as Manager JobExecution 845
    participant A as Worker A StepExecution 884
    participant M2 as Manager JobExecution 846
    participant B as Worker B StepExecution 901
    M1->>A: P0, old execution
    Note over A: Tạm pause / reply chậm
    M2->>B: P0, restart execution
    B-->>M2: P0 COMPLETED (current execution)
    A-->>M2: P0 reply old execution 884
    Note over M2: Reject stale reply / reconcile old business side effects
~~~

**Không dùng duy nhất `partitionName=P0` để xác nhận reply sau restart**. Với cùng logical partition, worker StepExecution ID và JobExecution ID có thể khác; reply cũ có thể đến sau khi manager mới bắt đầu. Điều cần làm:

- Nhận diện `jobInstanceId/jobExecutionId/stepExecutionId` và request attempt.
- Chỉ ghi nhận completion cho **execution hiện hành hoặc outcome durable theo restart policy**.
- Không để stale result ghi đè `FAILED/RETRYING/COMPLETED` mới.
- Nếu worker cũ đã commit business effects, cần **idempotency, fencing hoặc reconciliation**; “bỏ reply cũ” không có nghĩa effects của nó đã rollback.
- Không tự coi lease timeout là bằng chứng worker cũ đã chết; worker có thể sống lại sau GC pause/network partition.

## 27. Out-of-order completion và per-key ordering

Thứ tự **toàn cục** thường rất tốn kém. Nhiều nghiệp vụ chỉ đòi **thứ tự trong một key**, ví dụ mỗi `accountId` cần áp dụng events theo `accountSequence`; hai accounts độc lập có thể xử lý song song.

~~~text
Account A: A1 -> A2 -> A3   (phải giữ thứ tự A)
Account B: B1 -> B2 -> B3   (phải giữ thứ tự B)

Các bước hợp lệ:
  A1, B1, B2, A2, A3, B3

Không hợp lệ:
  A2 trước A1 trên business sink của A.
~~~

Phương án:

1. **Partition by business key**: một key chỉ thuộc một serial worker/stream được bảo đảm.
2. **Optimistic version gate**: update `WHERE current_version = event_version - 1`.
3. **Reorder per key**: giữ events tương lai trong bounded buffer tới khi missing earlier sequence đến.
4. **Event-sourced ledger/fold**: lưu immutable events rồi rebuild ordered view theo key.

**Không lấy global UUID, broker offset của topic-partition khác hoặc worker completion timestamp làm thứ tự nghiệp vụ.** Sequence phải được producer/nguồn tin cậy xác định theo hợp đồng.

## 28. SQL optimistic sequencing cho một aggregate

Giả sử bảng account state lưu version:

~~~sql
CREATE TABLE account_state (
    account_id    VARCHAR(100) PRIMARY KEY,
    version_no    BIGINT NOT NULL,
    balance       NUMERIC(18, 2) NOT NULL
);

-- Sự kiện có sequence :eventVersion và amount delta;
-- chỉ áp dụng khi đúng phiên bản kế tiếp.
UPDATE account_state
SET version_no = :eventVersion,
    balance = balance + :delta
WHERE account_id = :accountId
  AND version_no = :eventVersion - 1;
~~~

Kiểm **số hàng affected**:

- **1 row:** event đúng version kế tiếp đã áp dụng trong transaction đó.
- **0 rows với state version thấp hơn expected:** event đến quá sớm; giữ pending/retry có giới hạn.
- **0 rows với state version bằng/cao hơn event:** duplicate hoặc stale; kiểm ledger/payload trước khi bỏ qua.
- **0 rows vì không có account:** cần policy initial state/create, không tự đổ lỗi ordering.

**Không chỉ dùng `ON CONFLICT DO NOTHING` cho ledger mà bỏ qua value check.** Một event cùng ID nhưng delta khác là data conflict cần fail/alert. Cần ghi operation ledger và business state **trong cùng transaction** để chống replay tạo double-apply.

### Test out-of-order cho account

~~~text
Initial account.version=0, balance=100
Submit event(version=2, delta=20) trước event(version=1, delta=10)

Event v2 UPDATE affected 0 -> pending (không đánh dấu success)
Event v1 UPDATE affected 1 -> balance=110, version=1
Retry v2 UPDATE affected 1 -> balance=130, version=2
Duplicate v1 must NOT apply -> balance stays 130
~~~

Đây là **sequencing strategy ở business sink**, khác với việc yêu cầu mọi worker hoàn tất theo thứ tự; workers vẫn có thể process/precompute song song, chỉ **commit effects phụ thuộc** cần được kiểm soát.

## 29. Khi downstream yêu cầu ordered visibility, dùng reorder buffer

Nếu output được xử lý song song nhưng downstream cần đọc theo sequence, tách hai khái niệm:

~~~text
Workers:
  C2 finished, C0 pending, C1 finished

Staging:
  completed = {C1, C2}
  not-yet-completed = {C0}

Publication:
  không publish C1/C2 nếu contract yêu cầu prefix C0..Cn
  C0 finished -> publish C0, C1, C2 theo logical order
~~~

**In-memory reorder buffer** phù hợp làm unit-test model, nhưng production cần:

- Bounded memory/disk quota vì một chunk đầu kẹt lâu có thể khiến hàng triệu chunks sau bị giữ.
- Durable status/payload reference để restart không mất items đã hoàn tất.
- Dedup và conflict check khi reply đến nhiều lần.
- Timeout/recovery khi chunk bị thiếu vĩnh viễn.
- Fencing để worker cũ không publish stale data.
- Publication cursor/pointer cập nhật atomic tại nơi downstream thực sự đọc.

**Không giả định “cứ đưa kết quả vào `TreeMap` là xong ordering”**: nếu publisher ghi file/event/DB trước khi checkpoint hoặc crash giữa publish và cursor update, phải có idempotent publish/reconciliation.

## 30. Java reorder buffer có kiểm tra duplicate

Mô hình thuần in-memory cho unit test:

~~~java
record VerifiedResult(long sequenceNo, String payloadHash) {}

final class ContiguousReorderBuffer {
    private long nextExpected;
    private final NavigableMap<Long, VerifiedResult> pending =
            new TreeMap<>();
    private final Map<Long, String> seenHashes = new HashMap<>();

    ContiguousReorderBuffer(long firstSequence) {
        nextExpected = firstSequence;
    }

    synchronized List<VerifiedResult> accept(VerifiedResult result) {
        String previous = seenHashes.putIfAbsent(
                result.sequenceNo(), result.payloadHash());
        if (previous != null && !previous.equals(result.payloadHash())) {
            throw new IllegalStateException("Conflicting duplicate");
        }
        if (result.sequenceNo() < nextExpected) {
            return List.of(); // Already released in this test run.
        }

        pending.putIfAbsent(result.sequenceNo(), result);
        List<VerifiedResult> ready = new ArrayList<>();
        VerifiedResult candidate;
        while ((candidate = pending.remove(nextExpected)) != null) {
            ready.add(candidate);
            nextExpected++;
        }
        return List.copyOf(ready);
    }

    synchronized long nextExpected() {
        return nextExpected;
    }
}
~~~

Test:

~~~java
@Test
void onlyContiguousResultsBecomeVisible() {
    var buffer = new ContiguousReorderBuffer(0);

    assertTrue(buffer.accept(new VerifiedResult(2, "h2")).isEmpty());
    assertTrue(buffer.accept(new VerifiedResult(1, "h1")).isEmpty());
    assertEquals(0, buffer.nextExpected());

    assertEquals(List.of(
            new VerifiedResult(0, "h0"),
            new VerifiedResult(1, "h1"),
            new VerifiedResult(2, "h2")),
            buffer.accept(new VerifiedResult(0, "h0")));
    assertEquals(3, buffer.nextExpected());

    assertTrue(buffer.accept(new VerifiedResult(1, "h1")).isEmpty());
    assertThrows(IllegalStateException.class,
            () -> buffer.accept(new VerifiedResult(2, "DIFFERENT")));
}
~~~

**Giới hạn:** code lưu toàn bộ `seenHashes` và `pending` trong RAM, sẽ tăng memory không giới hạn với stream lớn; `nextExpected++` cần kiểm overflow khi sequence tới giới hạn `long`. Nó **không thực hiện DB/file/broker publish**, và chỉ trả về những records **có thể** công bố. Production phải giữ durable ledger/pointer và gọi publisher với transaction/CAS/idempotency tương ứng.

## 31. Durable publication cursor thay vì buffer RAM vô hạn

Với job hàng triệu records/chunks, một cách tốt hơn là giữ outcomes ở **staging table** và công bố bằng **contiguous cursor**:

~~~sql
CREATE TABLE verified_segment (
    batch_key      VARCHAR(120) NOT NULL,
    start_seq      BIGINT NOT NULL,
    end_exclusive  BIGINT NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    status         VARCHAR(20) NOT NULL
                   CHECK (status IN ('STAGED','VALIDATED','FAILED')),
    PRIMARY KEY (batch_key, start_seq),
    CHECK (end_exclusive > start_seq)
);

CREATE TABLE publication_cursor (
    batch_key      VARCHAR(120) PRIMARY KEY,
    next_sequence  BIGINT NOT NULL,
    cursor_version BIGINT NOT NULL DEFAULT 0
);
~~~

Trong một **DB transaction ngắn**, publisher:

1. `SELECT publication_cursor ... FOR UPDATE` theo batch.
2. Lấy `next_sequence=N`; chỉ chọn `verified_segment` có `start_seq=N`, `status='VALIDATED'` và `end_exclusive > N`.
3. Xác nhận **segment không overlap/corrupt**, nguồn và payload immutable, các business effects tương ứng đã commit.
4. Tăng cursor tới `end_exclusive` (và `cursor_version`) dưới cùng transaction.
5. Tiếp tục với segment kế nếu nó bắt đầu đúng cursor mới, cho tới khi gặp gap hoặc hết work.

**Điều kiện tiên quyết quan trọng:** staging segments phải có **partition map/snapshot ổn định, không có ranges giao nhau**, và validator phải đánh dấu VALIDATED chỉ khi **mọi expected record của segment** có outcome đúng. Nếu source IDs sparse, “liên tục” nghĩa là **thứ tự các segments đã định nghĩa trong manifest**, không nhất thiết mọi số nguyên giữa min/max đều là một record có thật.

### Mẫu transaction có cursor lock

~~~sql
BEGIN;

SELECT next_sequence, cursor_version
FROM publication_cursor
WHERE batch_key = :batchKey
FOR UPDATE;

-- Publisher ứng dụng chọn segment có
-- start_seq = next_sequence, status = VALIDATED.
-- Nếu không tồn tại: dừng, không nhảy qua gap.
-- Sau khi kiểm chứng segment và source version:

UPDATE publication_cursor
SET next_sequence = :verifiedEndExclusive,
    cursor_version = cursor_version + 1
WHERE batch_key = :batchKey
  AND next_sequence = :expectedStart;

COMMIT;
~~~

Đây là **phác thảo giao dịch**: application phải kiểm số row updated, bắt buộc giữ lock/CAS trên cursor, và bảo vệ immutable segment state. Nếu kết quả được **đọc từ DB** theo predicate `sequence_no < publication_cursor.next_sequence`, cursor có thể là **logical visibility gate**. Nếu xuất ra Kafka/S3/filesystem, DB cursor update **không tự atomically publish** những tài nguyên đó; dùng **transactional outbox, immutable versioned artifacts và consumer idempotency** theo topology.

## 32. Out-of-order không có nghĩa có thể “nhảy watermark”

Ví dụ test với các segments:

~~~text
Expected: [0,100), [100,200), [200,300), [300,400)

Completion order: [200,300), [300,400), [0,100), [100,200)

Cursor lúc đầu = 0
Receive [200,300) -> cursor vẫn 0
Receive [300,400) -> cursor vẫn 0
Receive [0,100)   -> cursor thành 100
Receive [100,200) -> cursor có thể thành 400
~~~

**Negative test cần có:**

- Nhận `[200,300)` trước rồi **không** được cho cursor thành 300.
- Nhận `[0,100)` nhưng status FAILED → cursor vẫn 0.
- Nhận `[0,100)` với checksum sai → fail/alert, cursor vẫn 0.
- Nhận trùng `[100,200)` cùng hash → no-op; khác hash → conflict.
- `[100,200)` chồng với `[150,250)` → reject/điều tra, không tự merge.
- Cursor update thành công nhưng publisher crash trước ACK → retry phải nhận biết cursor đã tiến, không phát event lặp bừa.
- Whole-batch rule yêu cầu **tất cả partitions đạt VALIDATED** trước khi công bố bất kỳ record nào → không dùng prefix cursor như thay thế hoàn toàn; dùng **batch-level publication barrier**.

**Có hai contract khác nhau:** *ordered streaming visibility* cho phép prefix 0..N được đọc khi N an toàn; *all-or-nothing batch visibility* yêu cầu chỉ công bố toàn bộ khi batch đầy đủ. Test phải biết contract nào đang được triển khai.

## 33. Head-of-line blocking là giá phải trả cho ordered publication

~~~text
P0 xử lý 90 giây
P1/P2/P3 hoàn tất sau 2 giây

Nếu unordered publish:
  P1/P2/P3 có thể visible sớm; P0 tới sau.

Nếu global contiguous publication:
  P1/P2/P3 phải chờ P0 -> time-to-first-prefix tăng.
~~~

Đây là **head-of-line blocking** ở publication gate. Tăng workers giúp throughput compute/commit, nhưng **không** giải quyết gap của P0 nếu P0 là partition chậm nhất.

Phương án giảm chi phí:

- Giảm granularity của segment đầu để gap được lấp sớm hơn.
- Phân tải cân bằng theo số records/cost, không chỉ ID range.
- Giới hạn reorder buffer và dùng backpressure khi pending gap kéo dài.
- Dùng **per-key ordering** thay global nếu nghiệp vụ cho phép.
- Ưu tiên xử lý missing earlier segment mà không làm starve những workload khác.
- Báo alert cho oldest gap/straggler; không tự bỏ qua nó nếu không có data-loss policy.

**Không dùng “đợi 5 giây rồi publish luôn”** làm fallback nếu contract bắt buộc contiguous order. Timeout là signal để **fail/retry/escalate**, không phải bằng chứng rằng một segment chưa commit có thể được bỏ qua an toàn.

## 34. Kafka, RabbitMQ và JMS: transport order khác completion order

| Transport | Order guarantee thường gặp | Điều không được suy ra |
| --- | --- | --- |
| **Kafka** | Broker giữ thứ tự offset **trong một topic-partition**; consumer đọc theo offset khi thiết kế đúng | Nhiều consumers/async tasks không thể process/commit đảo thứ tự |
| **RabbitMQ** | Queue có thứ tự enqueue/delivery theo những điều kiện cụ thể | Nhiều consumers/prefetch/requeue không làm completion FIFO toàn cục |
| **JMS** | Provider/session có ordering contract theo cấu hình | Nhiều sessions/consumers hoặc redelivery có completion order như gửi |
| **Spring Integration DirectChannel** | Lời gọi handler thường đồng bộ theo thread của sender | Async gateway/broker tương đương |
| **ExecutorChannel/TaskExecutor** | Tasks được điều phối qua executor | Thứ tự bắt đầu/kết thúc giống thứ tự submit |

Ngay cả khi **transport delivery order được giữ**, worker A xử lý message đầu mất 5 giây còn worker B xử lý message sau 100 ms; **completion vẫn có thể đảo thứ tự** nếu có concurrency.

### Chọn partition key đúng

Nếu Kafka dùng `accountId` làm message key, các events cho cùng key thường được ánh xạ tới cùng topic-partition theo partitioning strategy. Nhưng ứng dụng consumer phải bảo vệ **sequential processing/offset commit** nếu nghiệp vụ cần order; đẩy từng message lên một executor không có gate có thể làm effects commit đảo thứ tự ngay trong cùng Kafka partition.

**Không coi broker offset của hai topic-partitions khác nhau là global order**, và không dùng Kafka transport ordering để thay business dedup/sequence checks khi retries hay replay.

## 35. Out-of-order completion khi multi-threaded step

Multi-threaded step và partitioned step dễ bị nhầm. Trong **multi-threaded step**, các chunk work có thể được thực thi trên nhiều threads **trong một StepExecution**, nên cùng reader/ItemStream state có thể là điểm nhạy cảm.

~~~text
Chunk 1 read/submit
Chunk 2 read/submit
Chunk 3 read/submit

Chunk 2 commit trước Chunk 1.
Chunk 3 có thể fail và rollback.
~~~

**Test cần:**

1. Kiểm reader và writer có thread-safe theo cách chúng được dùng (hoặc serialize component không thread-safe).
2. Giao source snapshot/record IDs ổn định; không dùng vị trí callback để suy ra record order.
3. So tập business keys và values, kiểm chunk rollback/retry.
4. Kiểm `ExecutionContext` checkpoint/restart khi chunk completions không cùng thứ tự đọc.
5. Nếu output yêu cầu order, stage theo sequence và publish qua gate thay vì multiple threads append cùng file.

**Không quảng cáo checkpoint exactly-once chỉ vì `saveState(true)`**: trong multi-threaded step, stateful reader và checkpoint semantics phức tạp hơn; thiết kế theo giới hạn của reader/version đang dùng và dùng idempotent writer/snapshot.

## 36. Parallel flows: hoàn tất branch sớm không bảo đảm toàn job sẵn sàng

Một job có hai branches:

~~~mermaid
flowchart TD
    J["Job start"] --> SPL["Split / parallel flows"]
    SPL --> A["Flow A: import khách hàng (nhanh)"]
    SPL --> B["Flow B: cập nhật tài khoản (chậm)"]
    A --> JOIN["Join / next dependent step"]
    B --> JOIN
    JOIN --> PUB["Validate + publish"]
~~~

Flow A `COMPLETED` trước B là bình thường. **Step công bố phụ thuộc cả hai** phải chờ/kiểm trạng thái kết thúc thích hợp; không được publish từ listener của A chỉ vì branch A thành công.

Test:

- Cố ý chặn B trong khi A hoàn tất.
- Xác minh publisher chưa chạy trước khi B đạt outcome hợp lệ.
- Cho B thất bại; publisher vẫn không đánh dấu batch hoàn tất.
- Restart theo JobInstance/snapshot và kiểm branches đã hoàn tất không tạo business effects trùng.

**Cẩn trọng:** thứ tự các callbacks `afterStep` giữa branches không phải ordering contract. Quy tắc phụ thuộc phải nằm ở **job flow/publication state** rõ ràng.

## 37. Khi nào nên cố ép global order?

| Nhu cầu | Có cần global ordering? | Giải pháp ưu tiên |
| --- | --- | --- |
| Bulk import rows độc lập | Thường không | Cho phép completion đảo, verify tập khóa |
| Event updates cho một account | Chỉ **per-key** | Key partition + sequence/CAS |
| Báo cáo CSV phải sort theo số thứ tự | Output ordered, worker completion không cần ordered | Parallel stage + sort/merge |
| Whole-batch publication | Không đòi commit order, chỉ **visibility barrier** | Batch manifest VALIDATED/PUBLISHED |
| Một external API đòi sequential calls | Có trong phạm vi API/key | Serial executor/queue theo key |
| Reconciliation totals giao hoán | Không, nếu phép tính và dedup đúng | Independent commits + aggregate |
| Financial ledger sequence pháp lý | Theo ledger contract, có thể mạnh | Durable sequence ledger, explicit ordering gate |

**Tradeoff:** global order thường tăng coupling giữa workers, khiến một straggler kéo chậm tất cả, tạo lock contention và head-of-line blocking. Hãy giữ order **chỉ trong vùng bắt buộc**, và cho phép compute/validation độc lập chạy song song khi có thể.

## 38. Performance test: thứ tự đảo có gây backlog không?

Đo những chỉ số:

| Metric | Điều trả lời |
| --- | --- |
| `worker_step_duration_seconds` | Partition nào là straggler? |
| `chunk_commit_duration_seconds` | DB commit hoặc lock wait có chậm? |
| `completion_lag_seconds` | Dispatch → outcome hợp lệ lâu bao nhiêu? |
| `reply_out_of_order_total` | Có bao nhiêu reply đến sau logical request khác đã hoàn tất? |
| `reply_stale_total` | Outcome của execution cũ còn đến? |
| `reorder_pending_segments` | Bao nhiêu segments đã validated nhưng chưa visible? |
| `reorder_pending_bytes` | Bộ đệm ordering đang tốn bao nhiêu bytes? |
| `publication_gap_oldest_age` | Segment thấp nhất đang thiếu đã chờ bao lâu? |
| `publication_watermark` | Prefix liên tục đã verified tới đâu? |
| `consumer_end_to_end_p99` | Ordered visibility ảnh hưởng SLA thế nào? |
| `business_reconciliation_mismatch` | Có thiếu/trùng/sai output không? |

**Không đưa `recordId`, `chunkSequence` hay `StepExecutionId` làm metric labels cho mọi item**: time-series cardinality sẽ tăng mạnh. Ghi các IDs này vào logs/traces/DB manifest với retention/access phù hợp.

### Bài test tải với straggler

~~~text
1. Run baseline: 4 partitions cùng thời gian.
2. Cố ý làm P0 chậm gấp 10 lần.
3. So unordered publication vs contiguous publication.
4. Đo worker throughput, job makespan, pending buffer bytes,
   time-to-first-visible và p99 record-to-visible latency.
5. Thử partition nhỏ hơn hoặc per-key ordering.
6. Đảm bảo mọi phương án có reconciliation PASS.
~~~

**Không so p99 của các loại latency khác nhau**: `worker.compute_p99` và `record-to-visible_p99` có thể chênh lệch lớn vì reorder wait, dù cùng workload.

## 39. Failure injection: kiểm thử những khoảng thời gian khó

| ID | Điểm gây lỗi/đảo order | Điều bắt buộc phải xác minh |
| --- | --- | --- |
| T01 | Chặn P0 tại `beforeStep`, để P1 hoàn tất trước | Callback order đảo có chủ đích; Job/DB vẫn đúng |
| T02 | P2 commit nhanh hơn P0 | Commit events theo đúng resource; query DB xác nhận |
| T03 | C2 reply trước C1 | Manager giữ C1 pending; correlate C2 theo key |
| T04 | C1 và C2 reply đồng thời | Registry thread-safe, không mất/đếm trùng |
| T05 | C2 reply hai lần giống nhau | Một logical outcome; duplicate metric |
| T06 | C2 reply lần hai nhưng payload khác | Reject/conflict, không last-write-wins |
| T07 | C3 reply dù chưa dispatch | Unknown correlation; không mark job COMPLETED |
| T08 | P0 rollback sau writer callback | Không ghi “committed” từ method callback |
| T09 | P0 FAILED, P1/P2 COMPLETED | Job/manager fail theo policy, partial commits được đối soát |
| T10 | Restart same JobInstance, partition names ổn định | Re-run failed work đúng, writer replay-safe |
| T11 | Reply cũ của JobExecution 845 đến sau restart 846 | Không match sang execution 846; reconcile old effects |
| T12 | Worker crash sau DB commit trước reply | Redelivery/retry không áp dụng business effect hai lần |
| T13 | Worker crash trước DB commit | Rollback/partial chunk recover đúng |
| T14 | Two JVM workers giành cùng logical partition | Global ownership/StepExecution protocol, không xử lý trùng sai |
| T15 | Chuyển source snapshot/range trước restart | Detect mismatch, không sử dụng checkpoint sai |
| T16 | Reorder buffer nhận seq 2, 1, 0 | Trước 0 không release; sau 0 release 0,1,2 |
| T17 | Segments trùng range hoặc hash khác | Reject/alert, cursor không nhảy |
| T18 | Publisher crash sau cursor update | Idempotent replay/outbox, không publish trùng |
| T19 | Segment đầu chậm, segment sau nhanh | Pending buffer bounded, head-of-line latency đo được |
| T20 | Worker output phụ thuộc account sequence | State version/CAS chặn v2 trước v1 |
| T21 | Reply routing tới manager không sở hữu request | Không ghép nhầm pending registry; alert |
| T22 | Broker redelivery khi consumer restart | Attempt mới có identity rõ, business dedup |
| T23 | Executor pool chỉ một thread | Deterministic overlap test thất bại như mong đợi |
| T24 | Source file/input record có size rất lệch | Straggler/p99 và publication buffer phản ánh đúng |

**Không phải mọi test đều thuộc cùng suite:** T01–T07, T16–T17 thích hợp ở unit/integration; các T11–T14, T18, T21–T22 đòi database/broker/process thật và cơ chế tiêm lỗi chính xác. Sau mọi bài test fault, phải có **data reconciliation**; test chỉ thấy exception đúng vẫn chưa đủ.

## 40. Broker integration test với hai JVM và reply đảo thứ tự

Đối với remote chunking hoặc remote partitioning thật, một test `DirectChannel` trong JVM không chứng minh được broker delivery/redelivery, connection loss hay reply routing. Harness hợp lý:

1. Khởi động một broker kiểm soát (RabbitMQ/JMS/Kafka theo topology) và PostgreSQL cho business/JobRepository.
2. Chạy manager và **ít nhất hai worker JVM/process riêng** với cùng source snapshot.
3. Gắn `requestCorrelationId` và `JobExecution/StepExecution/chunkSequence` theo protocol; không dùng trace ID thay thế.
4. Cho worker A nhận request sớm nhưng chặn trước commit/reply tại hook có handshake.
5. Worker B nhận request sau và hoàn tất, gửi reply tới manager trước.
6. Xác minh **manager correlated B**, A vẫn pending, không đổi nhầm StepExecution/chunk state.
7. Release A; xác nhận manager kết thúc đúng và output đủ key/value.
8. Lặp với duplicate reply, out-of-order ACK, stale reply sau restart và worker process kill.

### Một event envelope để debug

~~~json
{
  "event": "reply_received",
  "jobInstanceId": 819,
  "jobExecutionId": 845,
  "stepExecutionId": 884,
  "partitionName": "partition2",
  "chunkSequence": 12,
  "requestCorrelationId": "845/884/12",
  "deliveryAttempt": 2,
  "outcome": "COMPLETED",
  "sourceVersion": "snapshot-v1"
}
~~~

Envelope này là **log/audit model minh họa**, không phải JSON schema mặc định của Spring Batch. Trong thực tế một message có thể không chứa cả partition name lẫn chunk sequence; chọn các fields có nghĩa theo **loại giao thức**. Không dựa vào `deliveryAttempt` để quyết định idempotency nếu middleware không cung cấp attempt number bền vững; business logical key mới là nguồn dedup.

### Không đánh giá ACK như commit

Broker ACK có thể xác nhận **delivery đã được nhận/xử lý theo policy consumer**, nhưng không mặc định là business DB COMMIT; thứ tự các events phụ thuộc transaction/broker container config. Khi test crash sau commit trước ACK, expect redelivery/reconciliation **có thể** diễn ra. Khẳng định exactly-once chỉ khi đã có transactional/integrated protocol chứng minh theo scope rõ.

## 41. Test crash và restart phải có trạng thái durable

Một test chỉ throw exception từ processor **không mô phỏng** việc worker JVM bị kill ngay sau transaction commit. Với crash thật:

~~~text
Child JVM Worker A:
  - nhận C1
  - mở business transaction
  - COMMIT
  - báo test hook COMMIT_CONFIRMED
  - chờ tại điểm trước reply ACK

Test runner:
  - nhận COMMIT_CONFIRMED qua kênh điều khiển
  - kill worker A
  - giữ nguyên DB và broker volumes

Worker B:
  - redelivery/recovery theo protocol
  - verify idempotency key/payload
  - reply outcome hợp lệ

Manager:
  - correlate đúng request hiện hành
  - JobRepository/ledger và output cuối đúng
~~~

**Không kill theo `sleep(500)`** vì không biết transaction đã commit chưa. Test hook phải báo **sau commit outcome được xác minh**. Đồng thời cần test rollback case trước commit, và trường hợp outcome **không xác định** khi network bị ngắt đúng lúc commit response.

### Restart theo JobInstance

Trong Spring Batch, restart thường dùng lại **identifying JobParameters**, tạo `JobExecution` mới cho cùng `JobInstance` khi previous execution đủ điều kiện restart. Partition name/ExecutionContext/source snapshot phải ổn định. Không thêm `run.id` mới rồi gọi đó là test restart; đó có thể là **JobInstance khác**.

Nếu JVM bị kill khiến metadata còn `STARTED/UNKNOWN`, không assume `JobLauncher` sẽ tự nhận biết process đã chết. Cần **runbook recovery** và các kiểm tra trạng thái/liveness theo framework và deployment; không sửa bảng `BATCH_STEP_EXECUTION` thành COMPLETED để “đi qua” phần còn lỗi.

## 42. Kiểm thử outcome sau restart

Sau failure/restart, nên assert tối thiểu:

1. `JobInstanceId` giữ nguyên và `JobExecutionId` mới theo hợp đồng restart.
2. Partition names/source ranges/source version không bị đổi.
3. StepExecutions cũ và mới được phân biệt; reply cũ không match nhầm.
4. Source expected keys/values **không thiếu/không thừa/không sai**.
5. Business operation đã commit trước crash **không được áp dụng lần hai**.
6. Những work chưa commit được replay đúng và có final outcome.
7. Toàn bộ expected work hoàn tất, không có pending request/dangling partition bị bỏ qua.
8. Nếu có contiguous publish cursor, nó không nhảy qua gap, kể cả khi late reply về sau.
9. Các trạng thái `FAILED/RETRY/UNKNOWN` không bị count như logical success.
10. Dashboard/audit ghi nhận retry/redelivery nhưng không inflate committed throughput.

SQL kiểm gap:

~~~sql
-- Expected valid input thiếu trong sink.
SELECT s.sequence_no
FROM staged_ledger s
LEFT JOIN ledger_output o
  ON o.batch_key = s.batch_key
 AND o.sequence_no = s.sequence_no
WHERE s.batch_key = :batchKey
  AND o.sequence_no IS NULL;

-- Output ngoài source snapshot.
SELECT o.sequence_no
FROM ledger_output o
LEFT JOIN staged_ledger s
  ON s.batch_key = o.batch_key
 AND s.sequence_no = o.sequence_no
WHERE o.batch_key = :batchKey
  AND s.sequence_no IS NULL;
~~~

Hai truy vấn phải **không có row** nếu mọi input đều tạo đúng một output. Với filter/quarantine hoặc cardinality khác, mở rộng tập expected theo policy. **Cần kiểm thêm netAmount, tenantId, sourceHash/ruleVersion** để phát hiện giá trị sai dù keys đúng.

## 43. Nguyên nhân khiến test “out-of-order” bị flaky

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Test lúc pass lúc fail | `Thread.sleep` thay barrier | Latches + explicit milestone + timeouts |
| Hangs CI khi pool nhỏ | Barrier cần 4 tasks nhưng pool chỉ 2 | Chỉ cần 2 participants, pool đủ, bounded waits |
| Assert callbacks sai | Dựa vào unordered collection iteration | Explicit concurrent completion log |
| Tracing hiển thị order khác metadata | Span/clock skew/callback boundaries khác | Định nghĩa mốc và correlate exact IDs |
| Test ghi “committed” dù rollback | Ghi event trong `write()` | `afterCommit` + query DB riêng |
| Test xanh dù partition overlap | Writer `ON CONFLICT DO NOTHING` che trùng | Unit ranges + visit audit happy-path |
| Test xanh dù reply lẫn request | Chỉ assert số replies | Correlation ID + execution identity + values |
| Retry test đòi processor gọi đúng một lần | Retry/rollback có thể gọi lại | Assert logical business effect |
| Test restart thực ra chạy job mới | Thay identifying JobParameters | Same JobInstance; compare IDs |
| Snapshot thay đổi giữa test runs | Fixture không isolate/persist | Stable batchKey/version và cleanup riêng |
| Broker fake không redeliver | In-memory channel/test double | Transport integration + worker kill |
| Reorder buffer che memory leak | Test chỉ 3 segments | Stress with gap/bytes/timeout |
| Slow partition giả bằng CPU vô hạn | Tạo noise/CI variance | Controlled gates/failpoints, timed perf suite riêng |
| Test dùng chung singleton gate qua các runs | Latch đã countDown từ lần trước | New instance/context per run |

**Test instrumentation cũng phải thread-safe:** dùng `ConcurrentLinkedQueue`, `ConcurrentHashMap`, `AtomicInteger` khi nhiều workers ghi cùng log/audit; tránh `ArrayList.add` không đồng bộ rồi đổ lỗi cho batch code khi test tự bị race.

## 44. Runbook: manager nhận reply không theo thứ tự

1. **Xác định contract**: completion có được unordered không? Nếu cần order, là **per-key, per-partition hay toàn batch**?
2. **Chọn ranh giới**: dispatch, worker start, chunk DB commit, StepExecution final, broker reply hay publication?
3. **Khoanh vùng IDs**: JobInstance/JobExecution, StepExecution, partition/chunk sequence, request correlation, source snapshot.
4. **Kiểm broker/worker**: reply thật đến theo thứ tự nào, có redelivery/duplicate/late replies không, producer/consumer routing có đúng không?
5. **Kiểm JobRepository**: worker StepExecutions nào đã hoàn tất, failed, unknown; manager aggregation có bị timeout không?
6. **Kiểm business DB**: partial chunk commits, missing/extra keys, value conflicts và idempotency ledger.
7. **Kiểm stale owners**: job restart đã cấp execution mới nhưng worker cũ còn process không? Sink có fencing/quiescence đúng không?
8. **Kiểm publication**: watermark/prefix đã tiến đúng chưa, có gap thấp bị bỏ qua không, backlog/bytes của reorder buffer thế nào?
9. **Chọn recovery**: tiếp tục chờ trong budget, retry missing work có idempotency, quarantine conflict hoặc fail job; không gán reply sai.
10. **Verify sau xử lý**: exact source/output coverage, business values, metadata outcomes và publication order.
11. **Tối ưu nếu cần**: giảm straggler, điều chỉnh partition granularity, per-key order, queue fairness hoặc buffer capacity.
12. **Đóng incident**: lưu execution IDs, request IDs, timestamps, commit evidence và các failure-injection tests mới.

### Tình huống A — P2 trả trước P0, mọi thứ đúng

~~~text
P2 StepExecution COMPLETED, đúng range, DB rows verified.
P0 vẫn PROCESSING, chưa đến SLA timeout.
Manager pending P0, không match sai reply.
Publication buffer giữ P2 nếu cần strict prefix.

=> Không cần coi out-of-order là lỗi.
   Theo dõi P0 và buffer; publish khi contract cho phép.
~~~

### Tình huống B — reply C2 tới hai lần, lần hai khác payload

~~~text
requestCorrelationId=R2, chunkSequence=2
First reply: COMPLETED, hash=abc
Second reply: COMPLETED, hash=def

=> Conflict/corruption hoặc request identity reuse.
   Không last-write-wins, không mark success bừa;
   tra request ledger, source snapshot, worker attempts.
~~~

### Tình huống C — reply cũ đến sau restart

~~~text
Old JobExecution=845, WorkerStepExecution=884, partition=P0
Current JobExecution=846, WorkerStepExecution=901, partition=P0
Late reply references 845/884

=> Không cập nhật 846/901 từ reply cũ.
   Đối soát business effects của 845, dùng replay-safe
   writer và recovery contract cho current execution.
~~~

**Không sửa JobRepository thành COMPLETED, xóa request queue hoặc ép publisher nhảy qua sequence gap** chỉ để dashboard hết pending. Đó là hành động có thể che mất dữ liệu hoặc tạo duplicate.

## 45. Bài thực hành cuối bài

**Yêu cầu:** tạo Spring Batch 5.x/Java 17+ job xử lý **4.000 records** từ immutable PostgreSQL staging, bốn partitions trong một JVM, output có unique `(batchKey,sequenceNo)`, sau đó mở rộng một biến thể remote chunking qua broker.

**Phần A — local partitioning**

1. Chia `[0,4000)` theo bốn ranges nửa mở, snapshot/version ổn định.
2. Dùng `TaskExecutorPartitionHandler` với pool tối thiểu hai workers.
3. Gắn `PartitionCompletionGate`: giữ partition0 tại `beforeStep`, cho partition1 xử lý và tới `afterStep` trước.
4. Assert order `P1 trước P0` theo mốc callback, rồi release P0.
5. Assert Job/worker StepExecution statuses, exact source/output keys và values.
6. Instrument commit-verified events để phân biệt callback order với transaction outcome.

**Phần B — logical completion/reply**

7. Tạo fake registry và đưa replies `C2,C0,C1`; manager nhận mọi outcome đúng identity.
8. Gửi C2 duplicate giống nội dung, rồi duplicate khác hash; test lần đầu no-op, lần sau conflict.
9. Dựng reorder buffer; gửi `2,1,0`; test chỉ release dải `0,1,2` khi đủ.
10. Kiểm publication cursor DB không tiến qua gap hoặc status FAILED.

**Phần C — failure/restart**

11. Tiêm lỗi permanent vào partition0 sau một vài chunks; kiểm partition1 có thể đã commit trước.
12. Restart cùng JobInstance, giữ source snapshot và verify idempotent writer.
13. Gửi stale reply của execution cũ khi execution mới đang chạy; test reject/correlate đúng.
14. Kill worker JVM sau commit trước reply trên broker thật, quan sát redelivery và một logical effect.

**Phần D — performance**

15. Cho P0 chậm có kiểm soát, so unordered publish và contiguous publication.
16. Đo p95/p99 record-to-visible, reorder pending bytes, oldest gap age và job makespan.
17. Thử granularity nhỏ hơn hoặc per-key ordering và đánh giá tradeoff latency/throughput.

**Tiêu chí đạt:** test **chủ động tạo được** completion đảo thứ tự, không có assertion phụ thuộc FIFO ngoài contract, dữ liệu đủ/đúng/không trùng, reply được correlate đúng sau retry/restart, và publication bảo toàn sequence **chỉ ở nơi nghiệp vụ yêu cầu**.

## 46. Checklist trước production

- [ ] Đã định nghĩa rõ **thứ tự** đang nói: source, dispatch, start, process, commit, reply, completion hay publication.
- [ ] Đã phân biệt completion hợp lệ ngoài thứ tự với duplicate/missing/stale/failed/unknown outcome.
- [ ] Tạo test đảo thứ tự deterministic bằng `CountDownLatch`/barrier, không dựa `Thread.sleep`.
- [ ] Mọi gates có timeout, giải phóng trong `finally` và không dùng lại instance giữa test runs.
- [ ] `gridSize`, executor pool và số partitions đủ để có ít nhất hai workers concurrent thực tế.
- [ ] Partition ranges/IDs ổn định, không overlap/gap và đúng source snapshot/tenant.
- [ ] Reader state tách per `StepExecution`, writer shared component an toàn trong concurrency.
- [ ] `JobRepository` assertions dựa StepExecution identity, không dựa thứ tự iterator.
- [ ] Không coi `ItemWriter.write`/`afterStep`/broker ACK là bằng chứng cho mọi transaction đã commit.
- [ ] Có commit-outcome probe đúng resource và business DB reconciliation.
- [ ] Remote reply correlation dùng request/execution identity, không dùng FIFO hoặc trace ID.
- [ ] Duplicate reply cùng nội dung no-op, khác nội dung conflict; unknown/stale reply được quản trị.
- [ ] Late reply sau restart không ghi đè outcome của JobExecution/StepExecution mới.
- [ ] Business effects idempotent, có ledger/payload verification khi retry/redelivery.
- [ ] Nếu nghiệp vụ cần per-key sequence, sink có ordering/version gate thực thi.
- [ ] Nếu cần ordered publication, có bounded reorder buffer/durable cursor không vượt gaps.
- [ ] Whole-batch atomic visibility có gate riêng; không nhầm với contiguous prefix.
- [ ] Backpressure và recovery xử lý khi straggler giữ buffer quá lâu.
- [ ] Broker ordering guarantees được xác minh đúng transport/consumer topology đang chạy.
- [ ] Có test hai JVM, out-of-order replies, worker kill, stale owner, redelivery và restart.
- [ ] Input/output được đối soát key/value/source version, không chỉ `COUNT(*)`.
- [ ] Có metrics về pending/gap age, completion lag, stale reply, p99 và memory buffer.
- [ ] Không dùng high-cardinality IDs làm metric tags; dùng logs/traces/manifest phù hợp.
- [ ] CI có unit/component/integration/crash/performance tests với fixture độc lập.
- [ ] Runbook không cho phép sửa metadata hoặc nhảy sequence gap mù quáng.

**Ghi nhớ:** **kiểm thử out-of-order completion** là kiểm tra xem Spring Batch và kiến trúc điều phối có **vẫn đúng khi thứ tự hoàn tất khác thứ tự gửi việc** hay không. Chỉ riêng callback order đảo không chứng minh lỗi; cần kiểm **identity, commit outcome, JobRepository, business keys/values, retry/restart và reply correlation**. Nếu đầu ra bắt buộc đúng sequence, hãy **tách parallel processing khỏi ordered publication** bằng per-key gate, immutable staging và contiguous cursor có recovery, rồi đo chi phí head-of-line blocking. Kết quả mong muốn là **song song ở phần được phép**, giữ thứ tự ở **ranh giới thật sự cần**, và kiểm chứng cả hai bằng tests có điều kiện ép lỗi rõ ràng.
