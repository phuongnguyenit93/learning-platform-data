# Test worker restart trong Spring Batch: kiểm chứng phục hồi khi chạy song song

Một batch job xử lý 24 triệu events bằng 16 partitions. Sau 40 phút, worker xử lý `range-07` bị kill đúng lúc chunk đang commit. Manager ghi nhận một partition lỗi, nhưng 15 partitions khác đã hoàn tất. Khi restart, job báo `COMPLETED`, tuy nhiên bảng output có một số event bị ghi hai lần hoặc bị bỏ sót. Test happy path trước đó không phát hiện vấn đề vì chỉ xác nhận `JobExecution.getStatus() == COMPLETED`.

**Test worker restart** là bài kiểm thử xem một worker bị lỗi, mất kết nối, bị hủy hoặc bị khởi động lại có thể **tiếp tục xử lý đúng phần việc còn thiếu** mà không làm hỏng dữ liệu đã commit, không chạy lại những partitions đã hoàn tất ngoài chính sách, và không nhân đôi business effects khi request bị phát lại.

Bài **“Test worker restart”** thuộc chương **Testing concurrency** trong module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu của module là mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và mô hình phân tán; đo nút thắt, giữ thread safety, retry/restart và vận hành workload dữ liệu lớn theo tài nguyên thực tế. Vì vậy kiểm thử worker restart vừa là **kiểm thử tính đúng đắn**, vừa là **kiểm thử concurrency/transaction/resource recovery**.

Các ví dụ lấy **Spring Batch 5.2.x**, **Spring Framework 6.x**, **Java 17+**, **JUnit 5**, **Spring Batch Test** và **PostgreSQL/Testcontainers** làm hệ quy chiếu. Các đoạn mã Java/SQL là thành phần tham khảo cần tích hợp với cấu hình application tương ứng; không giả định đã có broker, pods, migrations hoặc datasource trong dự án của người học. Những con số được ghi là fixture minh họa, không phải kết quả benchmark thực tế.

**Nguyên tắc nghiệm thu:** test chỉ đạt khi **business output sau restart bằng clean-run reference trên cùng immutable snapshot**, cộng với metadata/checkpoint và external side effects phù hợp; chỉ nhìn job status `COMPLETED` là **chưa đủ**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **retry một item/chunk**, **restart một worker StepExecution**, **restart JobExecution** và **tạo JobInstance mới**.
2. Giải thích quan hệ giữa manager StepExecution, worker StepExecutions, partition names, `ExecutionContext` và `JobRepository`.
3. Thiết kế input snapshot và phân hoạch **bất biến** để test không bị nhiễu bởi thay đổi dữ liệu.
4. Lập ma trận fault injection trước/giữa/sau business commit, trước checkpoint, trước broker ACK/reply và khi manager crash.
5. Viết test với `@SpringBatchTest`, `JobLauncherTestUtils`/`JobOperator`, JUnit 5 và database thật.
6. Chứng minh partitions `COMPLETED` không bị thực thi lại theo mặc định khi restart, còn partitions `FAILED` tiếp tục từ state phù hợp.
7. Chứng minh **chunk trước đã commit vẫn tồn tại**, chunk đang rollback không để lại partial writes, và replay không nhân đôi hiệu ứng nghiệp vụ.
8. Phân biệt test ném exception trong JVM với test **hard kill worker process/container**.
9. Kiểm thử remote partitioning, remote chunking, duplicate request, mất ACK/reply, stale worker và fencing/lease.
10. Phát hiện race condition giữa nhiều workers bằng so tập business keys/versions/checksums và SQL read-only.
11. Đo committed throughput, retry amplification, JDBC pool contention, JobRepository update latency và khả năng phục hồi theo SLA.
12. Đưa bộ test vào CI với tiêu chí pass/fail có thể lặp lại và runbook xử lý kết quả không chắc chắn.

## 2. “Worker restart” chính xác nghĩa là gì?

Trong Spring Batch, một **JobInstance** biểu diễn một lần xử lý logic theo job name và **identifying JobParameters**. Mỗi lần thực thi hoặc restart tạo một **JobExecution**. Mỗi Step có một hoặc nhiều **StepExecution** theo lịch sử. Với partitioning, worker step được chạy cho các partition names cố định, ví dụ `loadWorker:range-000`.

| Hành động | Phạm vi | Metadata/recovery |
| --- | --- | --- |
| Retry theo `FaultTolerantStepBuilder` | Lỗi item/chunk trong một worker execution | Retry policy và transaction rollback của chunk |
| Restart JobInstance bị FAILED/STOPPED | JobExecution mới, **cùng JobInstance** | Framework xét trạng thái steps/partitions và checkpoint |
| Worker process restart | JVM/pod mới thực thi work được điều phối | Cần repository, message transport, liveness/ownership |
| Redelivery remote request | Request chunk/partition được giao lại | Có thể phát lại work đã commit; cần idempotency/fencing |
| Rerun với `run.id` mới | **JobInstance khác** nếu run.id identifying | Không tự reuse lịch sử checkpoint của instance cũ |
| Reprocess kết quả đã COMPLETED | Quy trình revision/correction riêng | Không được gọi nhầm là restart an toàn |

**Một worker bị restart không có nghĩa Spring Batch tự spawn process mới**: framework cung cấp metadata và các cơ chế restart; scheduler, container orchestrator hoặc remote partition manager quyết định nơi và khi nào worker được khởi động lại.

### 2.1. Ví dụ trước/sau lỗi

~~~text
JobInstance: import(snapshot=v42, logic=v3)

JobExecution 9001:
  managerStep                  FAILED
  loadWorker:range-000         COMPLETED
  loadWorker:range-001         COMPLETED
  loadWorker:range-002         FAILED
  loadWorker:range-003         COMPLETED

JobExecution 9002 (restart cùng JobInstance):
  managerStep                  COMPLETED
  loadWorker:range-002         COMPLETED
  range-000/001/003            không cần chạy lại theo mặc định

Sau restart:
  expected unique event IDs   == actual unique event IDs
  expected content/version    == actual content/version
  external business effects   không có duplicate
~~~

Ví dụ là **mô hình kỳ vọng**, không phải một snapshot metadata đã đo. `StepExecution` của một partition có thể có bản ghi theo nhiều JobExecutions; test phải tra đúng lịch sử và không giả định worker cũ bị xóa khỏi repository.

### 2.2. Tại sao chỉ test FAILED → COMPLETED chưa đủ?

Một writer có thể ghi 100.000 bản ghi ở execution thứ nhất, commit, nhưng checkpoint không kịp cập nhật. Execution thứ hai phát lại 1.000 bản ghi và vẫn báo COMPLETED. Nếu SQL dùng `INSERT` không unique key hoặc `balance = balance + amount`, business output đã sai dù status thành công.

Ngược lại, checkpoint có thể tiến trước khi business commit nếu metadata và business dùng hai local managers; restart bỏ qua một số item, job vẫn COMPLETED nhưng output thiếu. Vì vậy **cần hai hướng đối soát**:

- **Duplicate/replay:** cùng business key được xử lý lại nhưng không được tạo side effect lặp.
- **Missing/skip:** mọi key trong snapshot phải có output đúng version/payload, kể cả khi checkpoint bị lệch.

## 3. Kiến trúc kiểm thử: manager, worker, metadata và business data

~~~mermaid
flowchart TD
    T["JUnit/Scenario Controller"] --> JL["JobLauncher / JobOperator"]
    JL --> MS["Partition Manager Step"]
    MS --> PH["Local TaskExecutor hoặc Remote PartitionHandler"]
    PH --> W0["Worker range-000"]
    PH --> W1["Worker range-001"]
    PH --> W2["Worker range-002"]
    W0 --> DB[("Business DB")]
    W1 --> DB
    W2 --> DB
    W0 --> JR[("JobRepository BATCH_*")]
    W1 --> JR
    W2 --> JR
    T --> FI["Fault Injection Control"]
    FI --> W1
    T --> O["Read-only Oracle + Reconciliation"]
    O --> DB
    O --> JR
~~~

Test harness điều khiển fault, ghi marker trước/sau các mốc quan trọng, rồi kiểm tra **cả business rows lẫn Spring Batch metadata**. Ở remote tests, cần thêm broker/container/network và job/worker process health checks.

### 3.1. Bốn đối tượng cần giữ ổn định

1. **Source snapshot**: event IDs, payload hashes, source versions và checksum cố định.
2. **Partition plan**: mỗi partition có key và shard range không chồng lấn; restart không tạo tên mới.
3. **Business operation key**: định danh event/output/idempotency key cố định qua retries.
4. **JobInstance identity**: identifying parameters không đổi giữa JobExecutions của một lần test restart.

Không so kết quả với một source database đang thay đổi trong lúc test. Nếu source mutable, failure có thể do input drift chứ không phải worker restart.

### 3.2. Không nhầm lỗi “exception” với “crash”

| Loại failure | Worker có cơ hội cleanup? | Có thể ghi metadata FAILED? | Ý nghĩa test |
| --- | --- | --- | --- |
| `ItemProcessor` ném RuntimeException | Có | Thường có | Kiểm tra retry, rollback, restart bình thường |
| `ItemWriter` ném lỗi trước commit | Có | Thường có | Xác minh chunk atomicity |
| Database timeout/deadlock | Tùy rollback/timeout | Thường có nếu process còn sống | Kiểm tra fault tolerance và retry budget |
| `SIGTERM` graceful với deadline | Có thể | Có thể STOPPED/FAILED tùy path | Kiểm tra shutdown contract |
| `SIGKILL` / container OOMKill | **Không** | Có thể còn STARTED | Kiểm tra crash recovery/liveness |
| Broker reply/ACK bị mất | Có thể worker đã commit | Manager có thể chưa biết | Kiểm tra redelivery và idempotency |
| Manager crash, worker còn chạy | Worker vẫn có thể commit | Manager stale STARTED | Kiểm tra fencing/ownership và restart |

Một unit test giả lập `throw new IllegalStateException()` **không chứng minh** hệ thống an toàn khi JVM mất điện sát commit. Cần lớp integration/process-level tests riêng.

## 4. Các bất biến dùng làm oracle cho mọi kịch bản

Mỗi test phải công bố **điều cần đúng** trước khi tiêm lỗi.

### 4.1. Bất biến dữ liệu

Giả sử snapshot `v42` chứa 1.200 items với ID duy nhất, có 4 partitions disjoint:

\[
S=\{eventId_1,\ldots,eventId_{1200}\}.
\]

Sau clean run hoặc restart thành công, với output `O`:

\[
\operatorname{keys}(O)=S
\]

và:

\[
\forall id\in S:
\operatorname{version}_{O}(id)
=\operatorname{version}_{S}(id),\quad
\operatorname{hash}_{O}(id)
=\operatorname{hash}_{S}(id).
\]

Không chỉ `COUNT(*)=1200`; một missing và một extra record có thể làm count bằng nhau. Với output versioned, so theo **(snapshotId, businessKey, outputRevision)** hoặc khóa đã được hợp đồng nghiệp vụ xác nhận.

### 4.2. Bất biến transaction

- Rows thuộc chunk đã **COMMITTED** trước lỗi không bị rollback bởi lỗi chunk sau.
- Chunk rollback không để partial business writes nếu writer tham gia đúng transaction.
- Restart **không xóa dữ liệu đã commit** chỉ để che duplicate.
- State reader/checkpoint phản ánh đúng nguồn và được restore hợp lệ.
- Metadata JobRepository có lịch sử FAILED/STOPPED/COMPLETED nhất quán, không sửa status bằng SQL để làm xanh test.
- Nếu business DB và metadata DB không cùng local transaction, test phải phát hiện và xử lý **cả checkpoint behind lẫn checkpoint ahead**.

### 4.3. Bất biến partition/concurrency

- Tên partition giống nhau qua restart một JobInstance.
- Mỗi source key thuộc đúng một logical partition, trừ khi thuật toán có cơ chế dedupe được chứng minh.
- Worker đã `COMPLETED` không chạy lại mặc định chỉ vì worker khác thất bại.
- Trong một thời điểm, nếu dùng ownership/lease, không có **hai generations** cùng được phép ghi một logical partition.
- Không có shared mutable reader/writer state gây race hoặc out-of-order corruption.
- Concurrency tăng/giảm không thay đổi output keys/versions.
- Task rejection, broker redelivery hoặc lost reply không làm work biến mất.

### 4.4. Bất biến external side effects

Nếu worker gửi email, gọi payment API hoặc publish message, JDBC rollback **không** rollback các hiệu ứng đó. Test cần:

- Stable idempotency key qua retry/restart.
- Outbox/inbox hoặc dedupe ledger nếu dùng broker.
- Reconciliation của request timeout/unknown outcome.
- Không tuyên bố exactly-once dựa riêng vào reply, ACK hoặc `BatchStatus.COMPLETED`.

## 5. Ma trận fault injection theo ranh giới commit

| Mốc lỗi | Business DB | JobRepository | Rủi ro chính | Test kỳ vọng |
| --- | --- | --- | --- | --- |
| Trước writer | Chưa ghi chunk | Checkpoint trước | Chỉ retry work chưa ghi | Không missing |
| Trong writer trước commit | Transaction rollback | Context cùng TX rollback nếu phối hợp đúng | Partial writes | Rollback chunk nguyên vẹn |
| Sau business SQL nhưng trước commit | Chưa chắc commit | Chưa chắc | Rollback/lock | Xác minh DB thực |
| Sát DB COMMIT, mất connection | **Không xác định từ client** | Có thể khác | Retry sau uncertain commit | Đối soát business key |
| Business COMMIT nhưng checkpoint chưa bền | Có rows | Checkpoint cũ | **Replay/duplicate** | Writer idempotent |
| Checkpoint bền nhưng business COMMIT thất bại | Thiếu rows | Checkpoint tiến | **Skip/missing** | Reconciliation/repair |
| Worker đã COMMIT, trước reply | Có rows | Có thể đã updated | Redelivery worker request | Idempotency/fencing |
| Reply sent nhưng manager chưa nhận | Có thể thành công | Manager chưa aggregate | Timeout/duplicate dispatch | Query repository, correlate |
| Worker ghi `COMPLETED`, manager crash | Rows tồn tại | Worker status COMPLETED | Manager restart | Không chạy lại finished worker |
| Manager và worker cùng crash | Tùy chunk | Có thể STARTED | Stale ownership | Recovery có kiểm chứng |
| Sau outbox publish, trước mark SENT | Effect có thể đến consumer | Outbox chưa SENT | Duplicate event | Consumer dedupe |
| Restart trong khi worker cũ còn chạy | Hai generations | Metadata version race | Double business effect | Fencing/lease/idempotency |

**Cẩn trọng:** bảng liệt kê *các trạng thái bất nhất có thể xảy ra* khi có **hai transaction resources không atomic**, không khẳng định Spring Batch luôn commit checkpoint trước business. Khi cùng datasource/transaction manager và operations tham gia đúng local transaction, business writes cùng metadata chunk checkpoint có thể commit/rollback atomic; vẫn cần test external effects và trường hợp client không biết kết quả commit.

### 5.1. Tại sao cần test sau commit?

Nhiều người chỉ inject lỗi bằng `throw` ngay trong `ItemWriter`. Lỗi này thường xảy ra **trước commit**, khiến rollback hoạt động khá dễ đoán. Trong production, vấn đề khó nhất là worker đã commit xong nhưng bị kill trước metadata/reply/ACK. Mốc ấy phải được kiểm bằng **barrier/hook ở process boundary, network fault hoặc DB proxy** phù hợp, không suy từ test exception.

### 5.2. Không “ép” metadata để tạo lỗi giả

~~~sql
-- ANTI-PATTERN: không dùng để tạo trạng thái restart giả.
UPDATE BATCH_STEP_EXECUTION
SET STATUS = 'COMPLETED'
WHERE STEP_EXECUTION_ID = :stepExecutionId;
~~~

Thao tác này không tạo business commit, có thể phá optimistic locking và checkpoint invariants. Fault injection nên thực hiện qua worker/process/network hoặc test adapter được kiểm soát. Nếu cần khôi phục metadata `STARTED` stale sau hard kill, đó là **quy trình vận hành riêng có bằng chứng và phê duyệt**, không phải trick trong integration test.

## 6. Fixture dữ liệu: nhỏ đủ kiểm tra chính xác, lớn đủ bộc lộ race

Một bộ fixture cân bằng nên có:

- Một snapshot `v42` gồm 1.200 events.
- Bốn partitions có tên ổn định: `p00`, `p01`, `p02`, `p03`.
- Mỗi partition 300 events, key ranges nửa mở không overlap.
- Chunk size `100`, mỗi partition có ba chunks trong happy path.
- Một partition `p02` bị fail ở event thứ 250 của partition sau khi hai chunks đã commit.
- Một JobInstance với identifying params cố định.
- Một output business table unique theo snapshot + event ID.
- Một source snapshot không đổi từ lần chạy đầu đến restart.
- Một số rows có payload/version/hash để test idempotency conflict, không chỉ COUNT.

### 6.1. SQL fixture tham khảo (PostgreSQL)

~~~sql
CREATE TABLE source_snapshot_event (
    snapshot_id VARCHAR(100) NOT NULL,
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (snapshot_id, event_id)
);

CREATE TABLE normalized_event (
    snapshot_id VARCHAR(100) NOT NULL,
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (snapshot_id, event_id)
);
~~~

Seed dữ liệu nguồn với keys `1..1200` và manifest:

~~~text
snapshot=v42, logic=v3
p00: [1,301)
p01: [301,601)
p02: [601,901)
p03: [901,1201)
~~~

Để fail ở **item thứ 250 của p02**, dùng business key `850` nếu key liên tục tăng từ 601 (vì `850-601+1=250`). Lần đầu p02 đã commit chunks 601–700 và 701–800, sau đó xử lý chunk 801–900 ném lỗi trước commit. Test phải chứng minh **200 rows đầu p02 vẫn tồn tại**, còn chunk thứ ba chưa commit nếu writer cùng transaction.

### 6.2. Output phải chống replay theo khóa nghiệp vụ

~~~sql
INSERT INTO normalized_event (
    snapshot_id, event_id, source_version,
    payload_hash, amount)
VALUES (
    :snapshotId, :eventId, :sourceVersion,
    :payloadHash, :amount)
ON CONFLICT (snapshot_id, event_id) DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` khiến retry cùng event không insert thêm row. **Nó không tự kiểm chứng payload đúng**: cùng `snapshotId,eventId` nhưng `source_version`/`payload_hash` khác phải được fail hoặc audit, không im lặng bỏ qua. Test cố tình tiêm một replay conflicting hash để chứng minh validator phát hiện.

Nếu business effect là `balance = balance + :amount`, unique source event table thôi chưa đủ trừ khi dedupe ledger và balance update được thực hiện **trong cùng transaction**.

### 6.3. Nguồn bất biến qua restart

Đừng thay rows/source checksum sau khi execution #1 thất bại, vì execution #2 có thể đọc dữ liệu khác. Với nguồn file, lưu URI + immutable version/etag/hash; với JDBC, có frozen staging hoặc source versioned. Dùng deterministic sorting và ranges disjoint thay vì đọc theo `ORDER BY` không cố định.

## 7. Test pyramid: lớp nào chứng minh điều gì?

| Lớp | Công cụ | Chứng minh được | Không tự chứng minh |
| --- | --- | --- | --- |
| Unit | JUnit 5, pure Java, mock | Partition plan, failure policy, idempotency key | DB rollback, process crash |
| Component | `@SpringBatchTest` + local JobLauncher | Step status/ExecutionContext/reader restart | Broker redelivery hoặc JVM kill |
| Integration | PostgreSQL Testcontainers, cùng metadata schema | JDBC transactions, unique constraints, restart | Multi-JVM remote liveness |
| Multi-process | Manager + worker processes, broker Testcontainers | Lost ACK/reply, crash worker, duplicate requests | Production scale/chaos toàn cluster |
| Chaos/staging | K8s pod kill, DB outage, rolling deployment | Recovery ngoài lab, quotas/locks/HA | Không thay deterministic CI oracle |

**Đừng mock `JobRepository`** cho test nghiệm thu restart: repository thật mới có lịch sử `JobInstance/StepExecution/ExecutionContext`, optimistic locking và các ranh giới transaction. Unit tests với mock chỉ phù hợp kiểm tra policy nhỏ, không thay một integration test restart.

### 7.1. Bộ thư viện và database

Một dự án Maven/Gradle cần các dependency tương ứng:

~~~text
spring-batch-core 5.2.x
spring-batch-test 5.2.x (test)
spring-jdbc / Spring Framework 6.x
postgresql JDBC driver
JUnit Jupiter 5.x (test)
Testcontainers PostgreSQL + JUnit Jupiter (test)
Spring Boot test nếu dùng @SpringBootTest
Spring Batch Integration / broker client nếu test remote
~~~

Không hardcode “latest” version không đồng bộ: Spring Batch/Spring Boot/Spring Framework/Testcontainers versions phải tương thích theo dependency management của dự án. Chạy schema JDBC JobRepository đúng **phiên bản Spring Batch** trong container PostgreSQL, không mock metadata với H2 nếu mục tiêu là kiểm tra PostgreSQL locking/commit failure.

### 7.2. Test isolation

- Mỗi test case dùng **unique identifying `testRunKey`** hoặc reset repository một cách an toàn trong DB container dành riêng cho test.
- Không xóa các `BATCH_*` của môi trường dùng chung.
- Khi cần restart, **không đổi identifying params giữa hai JobExecutions của cùng test case**.
- Nếu dùng `@Transactional` trên chính JUnit test method, transaction của test có thể che visibility/commit behavior; **tránh bọc toàn test restart trong một rollback-only test transaction**.
- Tách test fail-once khỏi test fail-permanent để không phụ thuộc thứ tự chạy JUnit.
- Dùng deterministic fixture và có timeout tổng thể; không chạy bài test chờ vô hạn.

## 8. Local partition restart: quy trình kiểm chứng tối thiểu

Một kịch bản đủ cụ thể:

~~~text
Given:
  JobInstance import(snapshot=v42, testRunKey=X)
  4 partitions p00..p03, chunk=100
  source keys 1..1200, output empty
  fail gate chỉ kích hoạt ở worker p02, eventId=850, đúng một lần

When:
  launch JobExecution #1 synchronously
  p02 processor throw non-retryable exception
  other workers complete (wait for all local task futures)

Then:
  job BatchStatus=FAILED
  p02 BatchStatus=FAILED
  p00/p01/p03 BatchStatus=COMPLETED
  p02 committed keys 601..800 remain in DB
  keys 801..900 of p02 are not partially committed
  JobRepository has persisted checkpoint for p02

When:
  release fail gate
  restart JobExecution #1 using JobOperator.restart(id)
  and wait for terminal JobExecution #2

Then:
  same JobInstance ID, new JobExecution ID
  p02 completes remaining work
  p00/p01/p03 are not reprocessed by default
  final output keyset/hash/version == expected snapshot
~~~

**Race chú ý:** TaskExecutor cho local partition workers chạy song song, nên *thứ tự hoàn tất* không xác định. Test cần đợi manager báo terminal và dựa vào partition names/status, **không** assert rằng p00 luôn hoàn thành trước p01.

### 8.1. Local test không đòi worker process tự restart

Ở local partitioning, các workers là những StepExecutions chạy trong **cùng JVM**, thường qua `TaskExecutor`. Khi processor ném exception, worker step thất bại; `JobOperator.restart` sau đó có thể chọn chạy lại partition chưa completed. Đây là test **restart logic**, không phải test pod kill.

### 8.2. “Fail once” trong test cần có nơi giữ trạng thái rõ

Một cờ `AtomicBoolean` trong bean test có thể dùng cho test local **cùng JVM**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

final class OneShotFailureGate {
    private final AtomicBoolean armed = new AtomicBoolean(true);

    void failOnceAt(long eventId) {
        if (eventId == 850L &&
                armed.compareAndSet(true, false)) {
            throw new IllegalStateException(
                    "Injected non-retryable failure at 850");
        }
    }
}
~~~

Nếu test restart **JVM/process**, cờ trong RAM biến mất sau kill, nên phải dùng fault controller ngoài process hoặc marker bền vững riêng của test. `AtomicBoolean` chỉ chứng minh fail-once khi worker và test runner cùng sống; đừng dùng nó làm bằng chứng process restart.

### 8.3. Đừng để test qua chỉ nhờ skip/retry policy

Nếu Step có `.faultTolerant().retry(IllegalStateException.class).retryLimit(3)`, lỗi fail-once có thể được retry và thành công **trong cùng execution**, khiến job chưa từng FAILED. Với test kiểm chứng restart, fault exception phải được phân loại **không retry**, hoặc đặt test gate làm thất bại vượt retry budget.

Ngược lại, để kiểm thử **chunk retry**, phải thiết kế một test khác với expected status/attempts tương ứng. Không trộn hai mục tiêu rồi assert sai.


## 9. Java: cấu hình worker Step và Partitioner cho test

Bên dưới là một **cấu hình rút gọn** để người học nhận ra vị trí lỗi. Các snippet được chia theo trách nhiệm; khi triển khai phải đặt bean methods trong `@Configuration`, nhập đủ imports và dùng cùng `DataSource`/`PlatformTransactionManager` phù hợp.

### 9.1. Khai báo loại dữ liệu và processor có fault gate

~~~java
import java.math.BigDecimal;

record SnapshotEvent(
        long eventId,
        long sourceVersion,
        String payloadHash,
        BigDecimal amount) {}
~~~

Một processor chỉ fail **event 850** trong lần chạy đầu, không thay đổi payload nghiệp vụ:

~~~java
import org.springframework.batch.item.ItemProcessor;

final class FailOnceProcessor
        implements ItemProcessor<SnapshotEvent, SnapshotEvent> {

    private final OneShotFailureGate gate;

    FailOnceProcessor(OneShotFailureGate gate) {
        this.gate = gate;
    }

    @Override
    public SnapshotEvent process(SnapshotEvent event) {
        gate.failOnceAt(event.eventId());
        return event;
    }
}
~~~

`OneShotFailureGate` ở mục 8.2 phải là singleton của test context và được inject vào đúng worker; nó không phải tính năng sẵn có của Spring Batch. Trong ứng dụng thật, fault injection cần **test-only switch** có authorization; không đưa switch gây lỗi vào production public API.

### 9.2. Step-scoped JDBC reader cho từng partition

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean("snapshotPartitionReader")
@StepScope
public JdbcCursorItemReader<SnapshotEvent> snapshotPartitionReader(
        @Qualifier("sourceDataSource") DataSource source,
        @Value("#{jobParameters['snapshotId']}")
            String snapshotId,
        @Value("#{stepExecutionContext['startInclusive']}")
            Long startInclusive,
        @Value("#{stepExecutionContext['endExclusive']}")
            Long endExclusive) {

    return new JdbcCursorItemReaderBuilder<SnapshotEvent>()
            .name("snapshotPartitionReader")
            .dataSource(source)
            .sql("""
                SELECT event_id, source_version, payload_hash, amount
                FROM source_snapshot_event
                WHERE snapshot_id = ?
                  AND event_id >= ?
                  AND event_id < ?
                ORDER BY event_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, snapshotId);
                ps.setLong(2, startInclusive);
                ps.setLong(3, endExclusive);
            })
            .rowMapper((rs, rowNumber) -> new SnapshotEvent(
                    rs.getLong("event_id"),
                    rs.getLong("source_version"),
                    rs.getString("payload_hash"),
                    rs.getBigDecimal("amount")))
            .fetchSize(100)
            .saveState(true)
            .build();
}
~~~

Điều kiện `>= start` và `< end` bảo đảm dải nửa mở không nhân đôi event biên. `@StepScope` tạo bean/proxy theo worker StepExecution, cho phép mỗi partition có reader state riêng. Nó **không tự bảo đảm thread safety** nếu một multi-threaded Step dùng chung reader trong cùng StepExecution.

### 9.3. Writer JDBC idempotent

~~~java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean("normalizedWriter")
@StepScope
public JdbcBatchItemWriter<SnapshotEvent> normalizedWriter(
        @Qualifier("businessDataSource") DataSource businessDs,
        @Value("#{jobParameters['snapshotId']}")
            String snapshotId) {

    return new JdbcBatchItemWriterBuilder<SnapshotEvent>()
            .dataSource(businessDs)
            .sql("""
                INSERT INTO normalized_event(
                    snapshot_id, event_id, source_version,
                    payload_hash, amount)
                VALUES (
                    :snapshotId, :eventId, :sourceVersion,
                    :payloadHash, :amount)
                ON CONFLICT (snapshot_id, event_id)
                DO NOTHING
                """)
            .itemSqlParameterSourceProvider(event ->
                    new MapSqlParameterSource()
                            .addValue("snapshotId", snapshotId)
                            .addValue("eventId", event.eventId())
                            .addValue("sourceVersion",
                                    event.sourceVersion())
                            .addValue("payloadHash",
                                    event.payloadHash())
                            .addValue("amount", event.amount()))
            .assertUpdates(false)
            .build();
}
~~~

**Điểm triển khai:** writer được khai báo `@StepScope` để SpEL job parameters được resolve trong context StepExecution; không dùng `@Value("#{jobParameters['snapshotId']}")` trong bean singleton tạo lúc startup. `JdbcBatchItemWriter` no-op `DO NOTHING` có update count 0, nên `.assertUpdates(false)` tránh coi replay hợp lệ là lỗi writer. Việc kiểm tra conflicting payload phải diễn ra bằng validation hoặc SQL write policy khác, không để `DO NOTHING` im lặng che dữ liệu sai.

### 9.4. Fixed partition plan không phụ thuộc số threads

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

final class FixedFourPartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (int i = 0; i < 4; i++) {
            long from = 1L + 300L * i;
            long toExclusive = from + 300L;

            ExecutionContext context = new ExecutionContext();
            context.putLong("startInclusive", from);
            context.putLong("endExclusive", toExclusive);

            String key = "p%02d".formatted(i);
            result.put(key, context);
        }
        return result;
    }
}
~~~

Ở fixture này, `gridSize` được cố tình bỏ qua vì manifest chỉ có bốn partitions cố định. Trong production, đọc work manifest bất biến từ snapshot/JobInstance, không hardcode 4 shards. Key của map là `p00`...`p03`; worker StepExecution có tên dạng `workerStep:p02` theo partitioning framework. Không sinh random keys khi restart.

### 9.5. Worker Step và manager Step

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("workerStep")
public Step workerStep(
        JobRepository repository,
        @Qualifier("businessTxManager")
            PlatformTransactionManager businessTx,
        @Qualifier("snapshotPartitionReader")
            ItemReader<SnapshotEvent> reader,
        @Qualifier("normalizedWriter")
            ItemWriter<SnapshotEvent> writer,
        OneShotFailureGate gate) {

    ItemProcessor<SnapshotEvent, SnapshotEvent> processor =
            new FailOnceProcessor(gate);

    return new StepBuilder("workerStep", repository)
            .<SnapshotEvent, SnapshotEvent>chunk(100, businessTx)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean("partitionManagerStep")
public Step partitionManagerStep(
        JobRepository repository,
        @Qualifier("workerStep") Step worker,
        @Qualifier("partitionExecutor") TaskExecutor executor,
        Partitioner fixedFourPartitioner) {

    return new StepBuilder("partitionManagerStep", repository)
            .partitioner("workerStep", fixedFourPartitioner)
            .step(worker)
            .gridSize(4)
            .taskExecutor(executor)
            .build();
}
~~~

Ứng dụng còn cần `Job` với `new JobBuilder("snapshotImportJob",repository).start(partitionManagerStep).build()` và `OneShotFailureGate` bean. Ví dụ giả định không bật skip/retry đối với injected `IllegalStateException`; nếu chính sách worker đang bật `retry(IllegalStateException.class)` thì test cần dùng exception không retryable riêng.

### 9.6. Bounded executor, không nhầm gridSize với threads

~~~java
@Bean("partitionExecutor")
public ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("restart-test-worker-");
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    return executor;
}
~~~

Bean do Spring quản lý sẽ được khởi tạo theo lifecycle tương ứng; cần import `ThreadPoolTaskExecutor`. Ví dụ có **4 active threads tối đa**, queue 8 tasks trong JVM này. `gridSize(4)` là hint cho Partitioner; số active workers thực phụ thuộc handler/executor và resource availability.

**Chỉ dùng bounded TaskExecutor với output idempotent không giải quyết restart remote**: ở nhiều JVM còn phải xét broker, worker owners và JobRepository shared state.

## 10. JUnit 5 + Spring Batch Test: kiểm thử restart local

Một integration test nên dùng **database thật** và chạy Job với synchronous JobLauncher để có terminal status trước khi assertion; nếu launcher asynchronous, test phải đợi theo một **deadline hữu hạn**.

### 10.1. Cấu trúc test ví dụ

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(classes = RestartTestApplication.class)
class WorkerRestartIntegrationTest {

    @Autowired JobLauncherTestUtils jobLauncherTestUtils;
    @Autowired JobOperator jobOperator;
    @Autowired JobExplorer jobExplorer;
    @Autowired JdbcTemplate businessJdbc;

    @Test
    void failedPartitionCanRestartWithoutDuplicateOutput()
            throws Exception {

        // Fixture seed(v42, 1200 rows) và fail-once gate
        // phải được chuẩn bị trong test context trước khi launch.
        JobParameters params = new JobParametersBuilder()
                .addString("snapshotId", "v42", true)
                .addString("logicVersion", "v3", true)
                .addString("testRunKey",
                        UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(params);

        // Dùng synchronous launcher cho kịch bản này.
        assertEquals(BatchStatus.FAILED, first.getStatus());

        Long jobInstanceId = first.getJobInstance().getId();
        Long firstExecutionId = first.getId();

        // Không đổi identifying parameters khi restart.
        long restartedId = jobOperator.restart(firstExecutionId);

        JobExecution second =
                jobExplorer.getJobExecution(restartedId);
        assertNotNull(second);
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertEquals(jobInstanceId,
                second.getJobInstance().getId());
        assertNotEquals(firstExecutionId, second.getId());

        Long count = businessJdbc.queryForObject(
                """
                SELECT COUNT(*) FROM normalized_event
                WHERE snapshot_id = ?
                """, Long.class, "v42");

        assertEquals(1_200L, count);
        // Bổ sung assert key-set/hash/version và
        // từng partition status, không chỉ COUNT.
    }
}
~~~

`RestartTestApplication` là cấu hình integration test ứng dụng tự tạo (Job, Steps, Datasources, repository schema, fixture seeding và `OneShotFailureGate`). Test trên dùng một snapshot ID `v42`; **không chạy song song các test cases cùng ghi output v42** trừ khi mỗi case có database/schema riêng. `testRunKey` là identifying **chỉ để cô lập JobInstance trong test**; tuyệt đối không đổi nó giữa execution đầu và restart.

`@SpringBatchTest` cung cấp các tiện ích như `JobLauncherTestUtils` và `JobRepositoryTestUtils` trong test context phù hợp. Nếu có nhiều Job beans, gọi `jobLauncherTestUtils.setJob(snapshotImportJob)` trong setup để chọn đúng job. `@SpringBootTest` chỉ dùng nếu ứng dụng dựa vào Spring Boot; với pure Spring có thể dùng `@SpringJUnitConfig` và hạ tầng bean tương đương.

### 10.2. Vì sao không đặt @Transactional trên test method?

~~~java
// Tránh cho test nghiệm thu restart:
@Transactional
@Test
void restartTest() {
    // Outer test rollback có thể che transactions/visibility
    // mà worker threads sử dụng và tạo fixture không commit.
}
~~~

Fixture cần được **commit trước khi worker threads đọc**, và assertion phải query business database sau các commits thật. Transaction rollback của test thread không tự bao quát worker threads; đặt test annotation sai có thể làm fixture không visible hoặc khiến kết quả không lặp lại.

### 10.3. Testcontainers ở mức fixture

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class PostgresBackedRestartTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("batch_test")
                    .withUsername("batch")
                    .withPassword("batch");

    @DynamicPropertySource
    static void datasourceProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void usesRealPostgresSemantics() {
        // Tạo schema Batch + business tables trong test setup;
        // chạy JobLauncherTestUtils rồi assert DB và metadata.
    }
}
~~~

Đây là **skeleton**, không phải project có đầy đủ schema migration. Nếu dự án dùng `@EnableBatchProcessing`, cấu hình Spring Boot tự động khởi tạo Batch schema có thể bị thay đổi; test phải tự xác nhận các bảng `BATCH_*` đúng version và datasource thực. Không trộn hai cấu hình JobRepository khác nhau rồi cho rằng đang test resource mong muốn.

### 10.4. Dùng unique test fixture để tránh false green

Một test có output sẵn 1.200 records trước khi launch có thể “pass” count dù worker không ghi gì. Do đó:

1. Mỗi case tạo **schema/database hoặc snapshot ID riêng**.
2. Verify output **trống trước launch**.
3. Verify source snapshot count/hash.
4. Verify fail gate thực sự được kích hoạt tại event 850.
5. Verify first execution `FAILED` và expected partial committed state.
6. Verify second execution mới và final output đúng.
7. Không dùng `@DirtiesContext` để che dữ liệu stale mà bỏ qua root cause.

## 11. Assert theo partition, không theo thứ tự threads

Trong test local concurrent, không nên assert thread p00 hoàn tất trước p01. Hãy assert **tên StepExecution và trạng thái** từ repository.

### 11.1. Kiểm tra metadata bằng SQL read-only

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
    se.VERSION,
    se.START_TIME,
    se.END_TIME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
WHERE je.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY se.STEP_NAME, se.JOB_EXECUTION_ID;
~~~

Expected names gồm `workerStep:p00`..`workerStep:p03`. Khi restart, so lịch sử **cùng partition name qua nhiều JobExecutions**. Hoạt động framework/version có thể khác ở cách lưu bản ghi skipped/not-reexecuted: điều quan trọng là **không có một worker execution xử lý lại output của completed partition ngoài chính sách**.

### 11.2. Assert nghiệp vụ mạnh hơn số StepExecutions

Một cách làm hiệu quả trong local integration test là có test-only audit ở **writer entry**:

~~~text
writer_attempt(snapshotId, eventId, jobExecutionId, partitionKey)
writer_committed(snapshotId, eventId, sourceVersion, payloadHash)
~~~

Lưu ý `writer_attempt` chỉ là test audit (có thể ngoài transaction để giữ lịch sử attempts), còn `writer_committed` là business output bền. Nếu worker p02 retry, có thể thấy attempts trùng; nhưng business key chỉ một lần logic. Với completed partitions p00/p01/p03, assert **không có attempts thuộc JobExecution restart** nếu policy mặc định không rerun.

Với remote worker process kill, audit trong memory không tồn tại; lưu event log/trace đến test collector hoặc database audit **không can thiệp transaction semantics** cần kiểm tra.

### 11.3. Phân biệt StepExecution ID và partition identity

`StepExecutionId` là ID metadata cho một lần thực thi, có thể khác giữa các lần restart. **Partition name ổn định** (ví dụ `workerStep:p02`), JobInstance ID và snapshot ID là các referents cần so xuyên executions.

Một test khóa cứng rằng StepExecutionId phải giống hệt nhau qua restart là test sai mô hình; framework có thể tạo bản ghi StepExecution mới cho lần restart.


## 12. Hard kill worker process khác exception trong JVM

Khi worker chạy trong JVM riêng, `SIGKILL` hoặc container OOMKill không cho nó gọi `finally`, `ItemStream.close` hay listener cleanup. Repository có thể còn ghi `STARTED` dù process đã chết; business DB có thể đã commit nhưng manager chưa nhận reply.

Test process-level cần ít nhất manager và worker chạy ở **hai processes** độc lập:

~~~text
JUnit/Scenario Controller
  +-- PostgreSQL Testcontainer (JobRepository + business tables)
  +-- Broker Testcontainer (nếu remote)
  +-- Manager JVM / batch application
  +-- Worker-A JVM (có fault-injection endpoint)
  +-- Worker-B JVM (worker replacement)
  +-- Test marker collector / read-only oracle
~~~

Không dùng một static `AtomicBoolean` giữa hai JVM rồi gọi đó là fault injection có kiểm soát. Test harness cần signal qua IPC/test-only HTTP/database marker hoặc network proxy, với quyền truy cập hạn chế và deadline.

### 12.1. Kill sau business commit trước reply

~~~mermaid
sequenceDiagram
    participant T as Test controller
    participant M as Manager
    participant Q as Broker
    participant W as Worker A
    participant B as Business DB
    participant R as JobRepository
    T->>M: Launch snapshot v42
    M->>Q: Dispatch worker:p02
    Q->>W: Deliver request
    W->>B: Write + COMMIT
    W->>T: Signal AFTER_BUSINESS_COMMIT
    T-xW: Force kill process
    Note over W,Q: No reply / ACK from Worker A
    T->>R: Query StepExecution status
    T->>B: Query committed keys
    T->>M: Controlled recovery after liveness checks
    M->>Q: Re-dispatch only when protocol permits
    T->>B: Reconcile final output
~~~

**Expected:** replay/redelivery nếu xảy ra không tạo duplicate effects. Không chỉ assert manager báo completed; kiểm tra business DB, JobRepository và broker state.

### 12.2. Barrier đúng thời điểm thay vì sleep may rủi

Nếu test đợi hai giây rồi kill, không biết code đang ở đâu: chưa vào writer, đang commit hay đã trả reply. Test có thể pass ngẫu nhiên.

Với local JDBC transaction, có thể đăng ký **test-only transaction synchronization** để báo sau commit:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

final class TestCommitSignal {

    private final ExternalTestSignalSink sink;

    TestCommitSignal(ExternalTestSignalSink sink) {
        this.sink = sink;
    }

    void signalAfterCommit(String marker) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException(
                    "No transaction synchronization active");
        }

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        sink.emit(marker);
                    }
                });
    }
}
~~~

`ExternalTestSignalSink` là hợp đồng riêng của test harness. Phải đăng ký callback **trong transaction của writer** và signal phải đi tới controller ngoài worker process. Signal sau commit chỉ chứng minh **transaction đó** đã commit, không chứng minh metadata ở datasource khác hoặc broker ACK đã được ghi bền.

**Không đưa callback có thể block vô hạn vào production.** Nếu cần giữ worker tại barrier để kill, dùng test profile có watchdog/timeout, không giữ SQL locks qua network vì một test không kiểm soát.

### 12.3. Sau kill phải xác minh gì?

- Worker process thật sự exited, không chỉ mất heartbeat.
- StepExecution đang `STARTED`, `FAILED` hay `UNKNOWN` trong repository?
- Business keys/version nào đã commit?
- Broker có unacked request hoặc reply orphan không?
- Worker A còn giữ lease/fencing token hay DB locks không?
- Snapshot checksum, partition names/ranges có giữ nguyên không?
- External API call có trạng thái **unknown outcome** không?

Nếu repository còn `STARTED` stale, **không mặc định `JobOperator.restart` sẽ chấp nhận**: framework có thể từ chối vì cho rằng job đang chạy. Test phải đi theo recovery runbook/manager protocol sau khi chứng minh worker cũ không còn hoạt động; không sửa status `BATCH_*` tùy tiện.

### 12.4. Test stale worker và fencing

~~~text
t0: Worker A sở hữu p02 và đang xử lý.
t1: Network partition, manager không nghe heartbeat.
t2: Lease A hết hạn; worker B nhận quyền xử lý p02.
t3: Network hồi phục, A tiếp tục gửi business write.
t4: A và B có thể cùng ghi output nếu không fencing.
~~~

Một `lease_generation` tăng đơn điệu có thể bảo vệ quyền sở hữu:

~~~sql
UPDATE partition_work_owner
SET lease_generation = lease_generation + 1,
    owner_id = :newWorker,
    lease_until = NOW() + INTERVAL '30 seconds'
WHERE snapshot_id = :snapshotId
  AND partition_key = :partitionKey
  AND lease_generation = :expectedGeneration
RETURNING lease_generation;
~~~

Nhưng **business writer cũng phải kiểm tra generation trong cùng transaction/resource** (hoặc dùng protocol tương đương). Chỉ đổi token ở database này không ngăn stale worker ghi vào database/API khác. Metadata optimistic locking của `JobRepository` cũng không tự fencing external effects.

## 13. Remote partitioning: test dispatch, worker, reply

Trong remote partitioning, manager tạo/điều phối worker `StepExecution` rồi gửi `StepExecutionRequest` qua middleware. Worker đọc `ExecutionContext`/repository và **tự đọc partition input**. Khi remote request bị mất/nhận lại, test phải bảo vệ identity và business output.

| Fault | Quan sát có thể xảy ra | Acceptance |
| --- | --- | --- |
| Manager gửi request thất bại | Work chưa tới broker | Có durable retry/dispatch evidence |
| Broker nhận nhưng manager timeout | Work có thể pending | Không tạo JobInstance mới mù |
| Request được giao hai lần | Hai workers cùng request | Ownership/fencing, idempotency |
| Worker commit, mất ACK | Request có thể được giao lại | Không duplicate output |
| Worker commit, mất reply | Manager chưa biết outcome | Query repository + output trước recovery |
| Old reply tới sau replacement | Late result của generation cũ | Không ghi đè kết quả mới |
| Worker completed, manager crash | Worker metadata COMPLETED | Restart manager không rerun completed partition |
| Worker crash trước commit | Chunk rollback hoặc chưa commit | Work chưa xong được xử lý |
| Worker crash sau commit | Output tồn tại, reply chưa chắc | Replay-safe writer + reconciliation |

### 13.1. Correlation keys test cần lưu

~~~text
jobInstanceId
jobExecutionId
stepExecutionId
snapshotId
partitionKey
brokerMessageId / requestId
workAttemptId
workerInstanceId
leaseGeneration
businessOperationKey
businessCommitMarker
replyMarker
~~~

`stepExecutionId` có thể thay đổi khi restart; **businessOperationKey** cần ổn định qua các attempts/restarts của cùng logical operation. Nếu dùng một StepExecutionId mới làm API idempotency key, có thể vô tình phát charge mới.

### 13.2. ACK và reply không thay business transaction

- Broker ACK nghĩa transport đã nhận confirmation theo protocol, không chứng minh dữ liệu business được reconcile.
- Worker reply success nghĩa worker báo trạng thái, không chứng minh consumer downstream thực hiện business effect đúng một lần.
- `StepExecution.COMPLETED` là metadata framework, không tự biết external API effect.
- Business row tồn tại không chứng minh manager đã nhận ACK/reply.

Không ACK request chỉ vì deserialize xong nếu không có durable recovery state. Nhưng ACK **sau commit** vẫn có crash window bị redelivery; cần idempotent writer. Kafka offset commit, Rabbit ACK và JMS session commit có semantics khác nhau: test phải dựa trên broker/driver đang triển khai.

### 13.3. Late replies và duplicate messages

Test manager nhận **reply trùng** hoặc **reply của worker generation cũ** sau khi replacement chạy. Acceptance là đúng partition status, đúng identity/correlation, và business output duy nhất theo logical key; không nhất thiết đúng một message.

Khi một worker cũ còn active, **không re-dispatch chỉ vì timeout**; phối hợp liveness, lease, ownership và fencing trước khi nhận worker generation mới.

## 14. Remote chunking: checkpoint nằm ở manager

Khác remote partitioning, remote chunking thường có **manager đọc item**, phát `ChunkRequest`; worker xử lý/ghi rồi gửi `ChunkResponse`. Reader checkpoint và result aggregation ở manager; worker không tự đọc shard nguồn.

~~~mermaid
flowchart LR
    subgraph RC["Remote chunking"]
      M1["Manager reader + checkpoint"] --> Q1["ChunkRequest"]
      Q1 --> W1["Worker processor/writer"]
      W1 --> R1["ChunkResponse"]
      R1 --> M1
    end
    subgraph RP["Remote partitioning"]
      M2["Manager partition plan"] --> Q2["StepExecutionRequest"]
      Q2 --> W2["Worker reader/process/writer + checkpoint"]
    end
~~~

### 14.1. Mất reply sau khi worker commit

~~~text
Given:
  Manager gửi chunk request #123 chứa event IDs 301..400.
When:
  Worker ghi 100 events + COMMIT;
  reply #123 bị drop;
  Manager timeout và retry/abort theo policy.
Then:
  Nếu #123 được gửi lại, writer không tạo duplicate effect;
  response correlation không làm checkpoint nhảy sai;
  301..400 tồn tại đúng version/hash.
~~~

Nếu manager crash trước checkpoint, một phần chunks đã xử lý có thể được gửi lại sau restart. Kiểm tra **cả manager checkpoint và worker business commits**, không chỉ queue depth.

### 14.2. Remote partitioning khôi phục reader trong worker

~~~text
Partition p02:
  snapshotId = v42
  range      = [601,901)
  reader     = deterministic ORDER BY event_id

After restart:
  partition names/ranges == original immutable plan
  snapshot checksum      == original snapshot
  output keyset p02      == [601,901)
~~~

Không đổi gridSize/worker pod count khiến partitioner tái chia dữ liệu khác tên trong cùng JobInstance. `gridSize` là hint cho partitioner/handler, không phải distributed pause/restart switch.

## 15. Kiểm thử chunk transaction và JobRepository

### 15.1. Cùng một local transaction resource

Nếu repository metadata và business writer dùng cùng datasource/transaction manager **và** các operations tham gia transaction đó:

~~~text
BEGIN chunk TX
  write business rows
  ItemStream.update(ExecutionContext)
  JobRepository updates StepExecution/context
  injected failure before COMMIT
ROLLBACK

Expected:
  No uncommitted business rows
  Checkpoint has not advanced past failed chunk
~~~

Không suy “cùng hostname/DB URL” là cùng transaction nếu có hai JDBC pools/managers độc lập. Integration test phải xem data/metadata sau fault trên PostgreSQL thật.

### 15.2. Hai datasources, hai local commits

| Tình huống | Rủi ro | Cách test |
| --- | --- | --- |
| Business commit, checkpoint cũ | Replay/duplicate | Restart với writer idempotent |
| Checkpoint tiến, business chưa commit | Skip/missing | Reconciliation phát hiện thiếu và repair |

**Writer idempotent chủ yếu bảo vệ replay; nó không tự tạo output bị bỏ qua do checkpoint ahead.** Khi tách JobRepository và business DB, cần thử hai hướng bất nhất và có recovery protocol riêng.

### 15.3. DB commit outcome không rõ

Nếu connection bị cắt sát `COMMIT`, client nhận exception **không đủ chứng minh rollback**. Test phải query business key/version sau network fault, đối chiếu checkpoint rồi mới retry/reconcile. Với HTTP payment tương tự: timeout không chứng minh server chưa charge.

### 15.4. Lỗi một chunk không rollback cả partition

Chunk 11 fail không rollback 10 chunks trước đã commit. Test kỳ vọng “toàn partition trống sau lỗi” chỉ đúng nếu ứng dụng có staging/commit protocol khác ngoài Spring Batch chunk mặc định.

## 16. Idempotency test: cùng key nhưng payload khác

Có hai kiểu replay:

- **Cùng payload/version/hash:** no-op hợp lệ, business effect không nhân đôi.
- **Cùng business key nhưng amount/version/hash khác:** data conflict; phải fail/audit theo policy.

SQL đối soát conflict:

~~~sql
SELECT s.snapshot_id, s.event_id,
       s.source_version AS expected_version,
       o.source_version AS actual_version,
       s.payload_hash AS expected_hash,
       o.payload_hash AS actual_hash
FROM source_snapshot_event s
JOIN normalized_event o
  ON o.snapshot_id = s.snapshot_id
 AND o.event_id = s.event_id
WHERE s.snapshot_id = :snapshotId
  AND (
      s.source_version <> o.source_version
      OR s.payload_hash <> o.payload_hash
      OR s.amount <> o.amount
  );
~~~

Result phải rỗng. Cố tình seed một conflicting row rồi replay; nếu writer dùng `DO NOTHING` nhưng validator không báo lỗi, **test FAIL**. Với additive business effect `balance=balance+amount`, cần transactional applied-event ledger hoặc recompute facts thay vì chỉ dựa vào unique key của output projection.

### 16.1. External API idempotency

~~~text
operationKey = "charge:" + invoiceId + ":" + sourceVersion
~~~

Chỉ dùng công thức khi invoice/source version thực sự xác định một charge hợp lệ. Khi timeout, giữ **cùng key** hoặc tra trạng thái, không phát request ID mới vì StepExecutionId mới. Nếu API không hỗ trợ idempotency/status, cần reconciliation/manual review cho `UNKNOWN` thay vì retry vô điều kiện.

### 16.2. Outbox và inbox fault test

~~~text
1. Worker ghi business row + outbox event trong cùng JDBC TX.
2. COMMIT.
3. Dispatcher publish message.
4. Kill dispatcher trước khi mark SENT.
5. Dispatcher restart và phát lại event.
6. Consumer inbox/dedupe cho đúng một business effect logic.
7. Audit attempts có thể >1 nhưng final state đúng.
~~~

Outbox cung cấp durable ý định gửi, không tự bảo đảm broker chỉ thấy một message; test theo **business effect**.

## 17. Test concurrency và resource pool trong recovery

| Run | Partitions P | Active workers C | Chunk K | Fault | Acceptance |
| --- | ---: | ---: | ---: | --- | --- |
| A | 4 | 1 | 100 | Không | Clean reference |
| B | 4 | 2 | 100 | p02 fail once | Restart đúng |
| C | 4 | 4 | 100 | p02 fail once | Không race |
| D | 4 | 4 | 25 | Writer transient | Retry/rollback đúng |
| E | 4 | 4 | 300 | Worker hard kill | Recovery đúng |
| F | 8 | 4 | 100 | p07 skew/chậm | Manager đợi đúng |
| G | 16 | 4/8 | 100 | Lost ACK/reply | Dedupe/fencing đúng |
| H | 8 | 8 | 100 | Hikari max=3 | Fail/backoff hữu hạn |
| I | 16 | 8 | 100 | Redelivery burst | Output invariant |
| J | 16 | 8→2 | 100 | Restart với C thấp hơn | Plan unchanged |
| K | 16 | 2→8 | 100 | Restart với C cao hơn | Plan unchanged |

Các số liệu là test configurations, không phải throughput measurements. Tăng `C` trong khi `P`/`K` giữ nguyên để cô lập biến; `gridSize` không nhất thiết là active threads.

### 17.1. Đo điều gì khi worker restart?

- Committed unique items/s, không chỉ `readCount` hoặc total attempts.
- Partition duration max/p95 và stragglers.
- Retry attempts, rollbacks, `StepExecution` failures.
- JobRepository update latency, optimistic-lock conflicts.
- Hikari active/pending và connection acquire/hold p99.
- Broker ready/unacked/replies/redeliveries.
- CPU throttling, heap/RSS/GC, pod restart counts.
- Mean time to recovery, reconciliation duration, SLA buffer.
- Business duplicate/missing/conflict keys.

### 17.2. Test không nên pass nhờ vô hạn retry

Một worker luôn trả lỗi Hikari timeout không được lặp vô hạn để rồi “tình cờ” pass khi DB phục hồi. Test phải có deadline, bounded retry budget, báo failure rõ và durable work ownership. Khi DB hết capacity, không được `skip` required business items chỉ để `COMPLETED`.

### 17.3. Đừng assert wall clock quá chặt trên CI

`assertTrue(jobFinishedUnder2Seconds)` dễ flaky do môi trường chạy test. Dùng timeout đủ phát hiện deadlock/hang, đo performance bằng nhiều trials và đánh giá p95/p99/throughput trên môi trường kiểm soát. **Data correctness là điều kiện cứng**, performance thresholds là tiêu chí riêng có calibration.


## 18. SQL oracle hai chiều: missing, extra và sai payload

Một test chỉ assert `COUNT(*) = 1200` không phát hiện “thiếu event 850 nhưng lại thừa event 2000”. Cần kiểm chứng ít nhất ba hướng: **missing**, **extra** và **content mismatch**.

### 18.1. Missing business keys

~~~sql
SELECT s.event_id
FROM source_snapshot_event s
WHERE s.snapshot_id = :snapshotId

EXCEPT

SELECT o.event_id
FROM normalized_event o
WHERE o.snapshot_id = :snapshotId;
~~~

Result phải rỗng sau restart hoàn tất. `EXCEPT` trong PostgreSQL làm set difference (loại duplicates theo mặc định), nhưng output unique constraint và test duplicate vẫn phải có riêng.

### 18.2. Extra business keys

~~~sql
SELECT o.event_id
FROM normalized_event o
WHERE o.snapshot_id = :snapshotId

EXCEPT

SELECT s.event_id
FROM source_snapshot_event s
WHERE s.snapshot_id = :snapshotId;
~~~

Result cũng phải rỗng. Unique output key không ngăn một event **không thuộc snapshot** bị ghi sai.

### 18.3. Mismatched versions, hash và amount

~~~sql
SELECT s.event_id,
       s.source_version AS expected_version,
       o.source_version AS actual_version,
       s.payload_hash AS expected_hash,
       o.payload_hash AS actual_hash
FROM source_snapshot_event s
JOIN normalized_event o
  ON o.snapshot_id = s.snapshot_id
 AND o.event_id = s.event_id
WHERE s.snapshot_id = :snapshotId
  AND (
       s.source_version <> o.source_version
       OR s.payload_hash <> o.payload_hash
       OR s.amount <> o.amount
  );
~~~

Result phải rỗng với immutable source. `amount` là PostgreSQL `NUMERIC(18,2)` ở fixture, tránh so binary floating point mà không có tolerance policy.

### 18.4. Duplicates và output version

~~~sql
SELECT snapshot_id, event_id, COUNT(*) AS copies
FROM normalized_event
WHERE snapshot_id = :snapshotId
GROUP BY snapshot_id, event_id
HAVING COUNT(*) > 1;
~~~

Với primary key đúng, query sẽ rỗng; đó là evidence rằng constraint hoạt động, **không chứng minh writer chưa từng được gọi lại**. Khi kiểm tra replay attempts, dùng test audit log ngoài business output và không khiến audit tự làm sai transaction semantics.

### 18.5. JUnit oracle với JdbcTemplate

~~~java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertTrue;

final class SnapshotReconciliation {

    static void assertNoMissingOrExtra(
            JdbcTemplate jdbc, String snapshotId) {

        List<Long> missing = jdbc.queryForList(
                """
                SELECT event_id
                FROM source_snapshot_event WHERE snapshot_id = ?
                EXCEPT
                SELECT event_id
                FROM normalized_event WHERE snapshot_id = ?
                """,
                Long.class, snapshotId, snapshotId);

        List<Long> extra = jdbc.queryForList(
                """
                SELECT event_id
                FROM normalized_event WHERE snapshot_id = ?
                EXCEPT
                SELECT event_id
                FROM source_snapshot_event WHERE snapshot_id = ?
                """,
                Long.class, snapshotId, snapshotId);

        assertTrue(missing.isEmpty(),
                () -> "Missing event IDs: " + missing);
        assertTrue(extra.isEmpty(),
                () -> "Extra event IDs: " + extra);
    }
}
~~~

Oracle production còn kiểm tra versions/hash/amount và external effects. Chạy oracle **sau fail đầu** với expected partial state riêng, và **sau restart thành công** với expected complete state.

### 18.6. Clean reference không được contaminate failure test

Chạy clean reference trên **database/schema cô lập** hoặc dùng output revision namespace khác. Không chạy clean reference và fail/restart cùng ghi vào một `normalized_event(snapshotId,eventId)` output không versioned; nếu kết quả đã sẵn, test restart có thể báo pass dù không ghi gì.

## 19. Kiểm chứng partial commit trước khi restart

Với fixture 4 partitions × 300 records, chunk 100, p02 fail ở event 850:

| Partition | Key range | Status lần đầu | Committed rows |
| --- | --- | --- | ---: |
| p00 | [1,301) | COMPLETED | 300 |
| p01 | [301,601) | COMPLETED | 300 |
| p02 | [601,901) | FAILED | 200 (601–800) |
| p03 | [901,1201) | COMPLETED | 300 |
| **Tổng** | 1–1200 | Job FAILED | **1100** |

Với **local partition handler** đã đợi mọi task kết thúc, đây là kết quả định lượng kỳ vọng. Với remote workers có thể còn in-flight, phải kiểm tra liveness và chờ terminal state thực trước khi assert.

### 19.1. SQL xác minh partial state

~~~sql
SELECT COUNT(*) AS already_committed
FROM normalized_event
WHERE snapshot_id = :snapshotId;

SELECT COUNT(*) AS p02_committed
FROM normalized_event
WHERE snapshot_id = :snapshotId
  AND event_id >= 601 AND event_id < 901;

SELECT COUNT(*) AS uncommitted_chunk_rows
FROM normalized_event
WHERE snapshot_id = :snapshotId
  AND event_id >= 801 AND event_id < 901;
~~~

Expected: `already_committed=1100`, `p02_committed=200` và `uncommitted_chunk_rows=0`. Nếu chunk bị rollback vẫn có 1–99 rows, writer có thể không tham gia đúng business transaction hoặc vị trí fault khác dự kiến.

### 19.2. Identity và skip completed partitions

~~~text
first.JobInstanceId   == restarted.JobInstanceId
first.JobExecutionId  != restarted.JobExecutionId
partition names       == original plan names
completed p00,p01,p03 do not re-execute by default
failed p02 resumes/replays safely
~~~

Để chứng minh completed partitions không bị thực thi lại, kiểm tra cả **metadata history** và **test-only writer attempts** trong second JobExecution. Nếu bật `allowStartIfComplete(true)`/custom splitter policy thì expected khác; ghi rõ cấu hình trong test case.

## 20. Các failure tests cần đưa vào CI và staging

### 20.1. Input file/source drift

Worker p02 thất bại sau hai chunks; trước restart, test thay file cùng URI bằng nội dung có checksum khác. Expected: manifest checksum/version guard báo **fail closed**, không đọc offset cũ trên file mới và không publish. Trong production nên dùng immutable object version/URI, không chỉ checksum sau khi bị overwrite.

### 20.2. Partition plan drift

~~~text
Before: p02 -> [601,901)
After:  p02 -> [551,851)
~~~

Nếu restart vẫn dùng checkpoint của p02 cũ trên range mới, có thể trùng/bỏ sót. Test phải phát hiện mismatch, không auto repartition JobInstance cũ. Muốn chia shard plan mới, tạo revision/JobInstance khác theo reprocess policy.

### 20.3. Worker A còn sống khi manager phát B

Giả lập network partition làm manager không nhận heartbeat A, nhưng A vẫn có thể ghi DB. Sau lease timeout, manager cho B xử lý cùng p02. Writer phải reject stale generation hoặc idempotent + reconciliation đảm bảo business effects đúng. Nếu chỉ unique JDBC rows mà HTTP payment không được bảo vệ thì test **FAIL**.

### 20.4. Manager crash khi workers còn chạy

Manager JVM chết, worker A vẫn processing. Recovery không được phát worker B chỉ vì metadata manager `STARTED` stale. Test phải xác minh liveness, ownership và quyền commit của A trước re-dispatch.

### 20.5. JobRepository DB outage

Chặn repository updates trong khi business writer còn khỏe. Kiểm tra trạng thái StepExecution, dirty `ExecutionContext`, partial business effects, outcome unknown và recovery protocol. Không gọi `COMPLETED` chỉ vì business rows đã có trong database.

### 20.6. Duplicate và reordered message

Tiêm duplicate `StepExecutionRequest` hoặc chunk request; gửi replies tới manager theo thứ tự ngược. Test correlation ID, generation, idempotency; không dùng “reply đến cuối cùng là đúng” vì reply của worker cũ có thể tới trễ.

### 20.7. Timeout sau external side effect

Fake payment API ghi charge rồi không trả reply. Worker restart và retry cùng stable operation key. Test phải assert **một charge logic**, không phải chỉ một HTTP attempt. Nếu API không hỗ trợ idempotency/status, workflow cần reconciliation/manual review cho outcome chưa chắc chắn.

## 21. Giảm flakiness: orchestration deterministic

Concurrency bugs có thể không hiện trong một lần CI; nhưng test dùng sleep ngẫu nhiên cũng dễ báo lỗi giả.

### 21.1. Dùng barrier có mốc xác định

- `CountDownLatch`/`Phaser` cho local JVM.
- Test-only endpoint/DB marker cho multi-process workers.
- Fault proxy để delay/drop packet ở request ID được chọn.
- `TransactionSynchronization.afterCommit` để ghi mốc **sau local business commit**.
- Broker interceptor để drop reply đã được xác định.
- Unique snapshot/job parameters/test ID để không bị trộn giữa tests.

### 21.2. Mỗi kịch bản có deadline

~~~text
maxJobStartWait
maxWorkerReadyWait
maxFaultMarkerWait
maxJobTerminationWait
maxRecoveryWait
maxReconciliationWait
~~~

Không dùng `Thread.sleep(60000)` để “chắc chắn” một Job đã xong. Poll theo deadline hữu hạn, khi timeout lưu diagnostic: JobExecution/StepExecution statuses, committed rows, pool pending và broker lag.

### 21.3. Isolation và cleanup

- Mỗi test có schema/test DB hoặc snapshot/output namespace riêng.
- Fixture source được commit trước khi concurrent worker threads đọc.
- Không để test `@Transactional` rollback-only che commit behavior.
- Reset fail gates, clock/correlation và fault hooks giữa test cases.
- Không sửa/xóa metadata `BATCH_*` trên môi trường dùng chung.
- Với multi-process tests, cleanup worker processes/containers/broker subscriptions theo test ID.
- Không bật tự retry vô hạn trong test; fail với message rõ khi vượt deadline.

### 21.4. Reproduce bằng seed

Với stress/property-based test, log random seed, snapshot manifest, partition plan, fault marker và execution IDs. Chạy nhiều seeds để mở coverage nhưng luôn có cách **tái hiện seed thất bại**. Performance threshold p99 cần đánh giá trên môi trường ổn định, không assert một wall-clock cực nhỏ trên shared CI.


## 22. Bộ test theo tầng trong CI/CD

Không phải mọi fault đều cần được chạy ở mỗi pull request, nhưng mỗi release phải có bằng chứng đủ cho risk profile của kiến trúc.

| Tầng chạy | Khi chạy | Bộ test tối thiểu | Acceptance |
| --- | --- | --- | --- |
| Unit | Mỗi PR | Partition planner, key uniqueness, snapshot hash, idempotency classification | Deterministic, nhanh, không cần DB |
| Local Spring Batch integration | Mỗi PR hoặc merge | PostgreSQL, 4 partitions, fail-once p02, JobOperator.restart, SQL oracle | Final output bằng snapshot, metadata đúng |
| Transaction fault suite | Nightly/merge trọng yếu | Before commit, deadlock, rollback, uncertain commit | Không partial data; unknown outcomes được reconcile |
| Remote multi-process | Nightly | Worker kill, lost ACK/reply, duplicate request, stale worker | No duplicate business effects, có recovery |
| Load/concurrency | Nightly hoặc release candidate | C=1/2/4/8, skew, pool pressure | Output invariant, timeout/budget rõ |
| Chaos/staging | Trước release major | Pod kill, broker outage, metadata DB outage, rolling update | SLA/recovery/operability đạt runbook |

### 22.1. Test naming và báo cáo

Đặt tên theo **fault boundary + expected recovery**, thay vì `testRestartWorks` chung chung:

~~~text
workerRestart_whenProcessorFailsBeforeCommit_resumesFromCheckpoint
workerRestart_whenBusinessCommittedAndReplyLost_dedupesReplay
workerRestart_whenMetadataAheadOfBusiness_detectsMissingKeys
workerRestart_whenManagerDiesAfterWorkerComplete_skipsFinishedPartition
workerRestart_whenStaleWorkerReturns_rejectsOldFenceToken
workerRestart_whenSnapshotChanges_failsClosed
workerRestart_whenPoolExhausted_preservesDurableWork
~~~

Mỗi test report nên chứa:

- Test scenario ID, seed/fixture version, snapshot checksum.
- First/restarted JobInstanceId/JobExecutionIds.
- Partition keys và trạng thái trước/sau lỗi.
- Fault marker và thời điểm tiêm lỗi.
- Số business rows đã commit trước/sau.
- Missing, extra và mismatch counts.
- Retry/redelivery/ACK/reply attempts.
- Kết quả liveness/fencing.
- Thời lượng recovery và quyết định pass/fail.

### 22.2. Quy ước pass/fail

**PASS chỉ khi** tất cả đều đúng:

1. Fault mong muốn thực sự xảy ra, đúng marker.
2. First execution/worker status phản ánh fault theo contract.
3. JobInstance identity và immutable partition plan được giữ đúng.
4. Completed partitions không re-execute ngoài policy.
5. Business DB không có partial uncommitted chunk rows.
6. Retry/restart xảy ra hữu hạn, không hang.
7. Missing/extra/mismatch SQL oracles đều rỗng sau final run.
8. External business effects không duplicate.
9. No stale worker/lease còn được phép commit.
10. Các resource pools/broker queues được giải phóng hoặc có durable recovery owner.

Một run không kích hoạt fault (do marker không tới) là **test invalid/fail**, không được tính PASS chỉ vì Job hoàn tất clean path.

### 22.3. Đánh giá test flaky

Nếu chỉ fail 1/100 lần, đừng gắn nhãn “môi trường CI chậm” ngay. Ghi seed, chronology, worker process states, DB transaction markers, broker delivery IDs. Nếu fail phụ thuộc thứ tự threads, có thể chính là race condition cần sửa.

Ngược lại, nếu test assert một mốc milliseconds không liên quan correctness, hãy tách performance benchmark khỏi functional restart assertions và sử dụng deadline đủ rộng, có evidence.

## 23. Runbook khi worker restart thất bại ở production

Khi job production đang xử lý dữ liệu lớn và một worker chết giữa chừng, ưu tiên **chẩn đoán phạm vi commit và quyền sở hữu** trước restart.

### 23.1. Thu thập evidence

1. Ghi `JobInstanceId`, `JobExecutionId`, worker `StepExecutionId`, `partitionKey`, `snapshotId`, thời điểm và deployment version.
2. Xác định worker đã chết hay chỉ mất liên lạc; lưu pod/container exit reason, logs và heartbeat.
3. Kiểm tra JobRepository `BatchStatus`, `ExitStatus`, start/end/last-updated và rollback/commit counts.
4. Kiểm tra reader `ExecutionContext` và immutable source manifest.
5. Truy vấn business DB: source/target keys, source versions/hashes, committed chunk ranges.
6. Kiểm tra HTTP/broker/outbox: request IDs, ACK/reply trạng thái và external idempotency keys.
7. Kiểm tra Hikari pending, DB lock waits, CPU/memory và broker lag để tìm nguyên nhân gốc.
8. Nếu status `STARTED` stale, xác minh không còn worker đang ghi trước mọi recovery action.

### 23.2. Quyết định recovery

9. Nếu chỉ lỗi retryable transient và Step đã FAILED, sửa dependency và đánh giá restart **cùng JobInstance**.
10. Nếu business commit outcome chưa chắc chắn, reconcile DB/external systems trước retry.
11. Nếu metadata checkpoint behind, bảo đảm writer idempotent trên replay.
12. Nếu checkpoint ahead nhưng business output thiếu, cần repair/reprocess từ immutable snapshot có kiểm soát, không chỉ restart từ cursor cũ.
13. Nếu source checksum/partition manifest thay đổi, **fail closed** và lên plan revision mới.
14. Nếu stale worker còn sống, điều phối lease/fencing/termination trước khi dispatch replacement.
15. Nếu remote reply bị mất, kiểm tra worker result/JobRepository thay vì phát request mới vô điều kiện.
16. Nếu service đang quá tải, giảm concurrency/admission; không tăng worker count để “chạy lại nhanh hơn”.

### 23.3. Restart và nghiệm thu

17. Với JobInstance eligible, gọi `JobOperator.restart(failedOrStoppedExecutionId)` theo quy trình; không thêm identifying `run.id` mới.
18. Theo dõi StepExecution per partition và timeout/retry budget.
19. Kiểm tra partitions đã COMPLETED không chạy lại ngoài policy.
20. Chạy SQL oracles missing/extra/mismatch cùng snapshot/reference version.
21. Đối soát external effects/outbox/inbox và source totals.
22. Chỉ công bố output khi quality gate PASS.
23. Lưu root cause, fault marker tái hiện, regression test và thay đổi capacity/fencing.

### 23.4. Những điều tuyệt đối tránh

Không sửa `BATCH_STEP_EXECUTION.STATUS` bằng SQL để ép Step COMPLETED/FAILED. Không xóa rows chunk đã commit nếu chưa có rewind/checkpoint migration được phê duyệt. Không chạy lại JobInstance mới chỉ để né `JobRestartException`. Không kill mọi worker pods khi manager mất reply mà chưa hiểu in-flight transactions. Không cho phép unbounded retry của side-effectful API.

## 24. Những hiểu nhầm thường gặp

| Nhận định | Điều cần chỉnh |
| --- | --- |
| “Worker restart chỉ là tạo Thread mới.” | Phải xét JobInstance/StepExecution/checkpoint và durable work. |
| “Job COMPLETED sau restart nghĩa kết quả đúng.” | Cần missing/extra/hash/version và side-effect oracle. |
| “Ném exception tương đương kill JVM.” | Exception còn cleanup/metadata; kill process không có. |
| “Một chunk lỗi làm rollback cả partition.” | Chunks đã commit trước còn dữ liệu. |
| “`retryLimit(3)` nghĩa job sẽ restart ba lần.” | Retry trong step execution khác Job restart. |
| “Đổi `run.id` để chạy lại cùng JobInstance.” | Identifying run.id mới tạo JobInstance khác. |
| “StepExecutionId phải giữ nguyên qua restart.” | StepExecution mới có thể có ID mới; partition name giữ ổn định. |
| “GridSize là số worker threads.” | Partition hint khác executor/remote concurrency. |
| “Reader `@StepScope` riêng cho từng chunk thread.” | Scope theo StepExecution, không theo thread. |
| “Một partition COMPLETED luôn phải rerun khi manager FAILED.” | Splitter thường không rerun completed partition mặc định. |
| “Cùng DB URL là cùng transaction.” | Có thể dùng khác datasource/manager/physical connection. |
| “Nếu commit ném exception chắc chắn rollback.” | Outcome có thể không xác định khi connection mất sát commit. |
| “Checkpoint có là đủ chống duplicate.” | Metadata có thể chậm hơn business commit. |
| “Idempotency upsert tự sửa missing do checkpoint ahead.” | Nó chỉ bảo vệ replay; cần reconciliation. |
| “ON CONFLICT DO NOTHING bảo đảm payload giống nhau.” | Cần source version/hash conflict checking. |
| “Unique output row nghĩa writer chỉ chạy một lần.” | Nó có thể được gọi nhiều lần, DB dedupe. |
| “Worker mất ACK nghĩa chưa ghi DB.” | Có thể commit rồi mất reply/ACK. |
| “Broker reply trùng là lỗi phải làm job fail.” | Protocol cần correlate/dedupe, không double effect. |
| “Manager stop nghĩa remote worker đã dừng.” | Worker cũ có thể còn sống/commit. |
| “Metadata optimistic lock tự ngăn stale HTTP call.” | Cần business fencing/idempotency riêng. |
| “Test ngủ 5 giây rồi kill là deterministic.” | Phải dùng barrier/hook tại fault boundary. |
| “Đổi partition ranges khi restart không sao.” | Checkpoint gắn partition identity cũ. |
| “COUNT bằng nhau là đủ.” | Thiếu và thừa có thể triệt tiêu nhau. |
| “Hikari exhausted thì skip record để xanh job.” | Capacity failure không phải business skip. |
| “Test remote phải luôn tạo đúng một message.” | At-least-once có thể redeliver; kiểm business effect. |
| “Status STARTED sau hard kill có nghĩa worker còn sống.” | Có thể stale vì worker chưa kịp update repository. |
| “Tăng retry vô hạn giúp job tự hồi phục.” | Tạo retry storm, sai SLA và có thể double side effects. |

## 25. Checklist trước nghiệm thu worker restart

- [ ] Scope test xác định local partitioning, multi-threaded step, remote partitioning hay remote chunking.
- [ ] Snapshot ID/input rows/versions/hashes là bất biến.
- [ ] Partition keys và ranges không đổi qua restart.
- [ ] JobInstance identifying parameters được giữ nguyên.
- [ ] First run có fault marker chắc chắn được kích hoạt.
- [ ] Local fail-once test phân biệt retry in-execution và restart new JobExecution.
- [ ] Source fixture và business output test được cô lập giữa test cases.
- [ ] `@SpringBatchTest` dùng repository/transaction manager thật, không mock toàn bộ.
- [ ] Test DB cùng vendor với production cho transaction/locking tests quan trọng.
- [ ] Worker reader `ItemStream`/`ExecutionContext` lưu state và restore hợp lệ.
- [ ] Reader/writer không chia sẻ mutable state không thread-safe.
- [ ] Chunk commit trước vẫn tồn tại, chunk rollback không partial writes.
- [ ] Completed partitions không chạy lại ngoài policy.
- [ ] Failed partitions cuối cùng hoàn tất với output đúng.
- [ ] Writer idempotent theo stable business key/version/operation.
- [ ] Conflicting payload replay được phát hiện, không im lặng ignore.
- [ ] SQL missing/extra/mismatch oracles đều PASS.
- [ ] Nếu metadata và business DB khác resource, test cả checkpoint ahead/behind.
- [ ] Hard kill test không được coi ngang exception injection.
- [ ] Worker liveness/lease/fencing được test khi manager mất kết nối.
- [ ] Broker duplicate/redelivery và lost ACK/reply được test.
- [ ] Remote chunking và partitioning có oracle đúng vị trí reader checkpoint.
- [ ] API tạo side effect dùng idempotency key ổn định qua restart.
- [ ] Outbox publish-before-SENT crash không gây double consumer effect.
- [ ] Resource saturation không làm mất durable work.
- [ ] Retry budget/deadline/timeout hữu hạn, tránh job hang.
- [ ] Test metadata `STARTED` stale có runbook, không sửa SQL tùy tiện.
- [ ] Concurrency levels C=1/2/4/8 vẫn cho output giống reference.
- [ ] CI ghi đủ snapshot hash, execution IDs, partition statuses và fault markers.
- [ ] Không publish kết quả business nếu reconciliation chưa đạt.
- [ ] SLA/recovery time và resource headroom được kiểm chứng ở staging.

## 26. Câu hỏi tự kiểm tra

1. Worker StepExecution khác JobExecution và JobInstance ở đâu?
2. Vì sao restart cùng identifying parameters khác việc tạo `run.id` mới?
3. Sau worker p02 fail ở event 850, hai chunks p02 trước đã commit có bị rollback không?
4. Trong fixture 4×300 items, p02 đã commit 200 còn các partitions khác completed, tổng rows sau fail là bao nhiêu?
5. Với chunk size 100 và event 850 ở p02, chunk nào rollback khi processor ném lỗi?
6. Vì sao test “throw trong ItemWriter” không chứng minh an toàn lúc SIGKILL?
7. Nguyên nhân `StepExecution.STARTED` có thể stale sau hard kill?
8. Những thông tin nào bắt buộc giữ ổn định khi restart một partition?
9. Vì sao không nên assert StepExecutionId giống nhau qua restart?
10. `PartitionNameProvider` giúp gì và nó có tự phân biệt partition lỗi không?
11. `JobLauncherTestUtils`/`@SpringBatchTest` dùng để kiểm tra điều gì?
12. Tại sao integration test nên chạy PostgreSQL thật thay vì chỉ mock repository?
13. Lý do không đặt `@Transactional` rollback-only trên test method có concurrent workers?
14. Khi DB commit xong nhưng checkpoint còn cũ, risk là gì?
15. Khi checkpoint đã tiến nhưng business DB rollback, idempotent writer có tự sửa không?
16. Tại sao `ON CONFLICT DO NOTHING` không đủ kiểm tra payload conflict?
17. Vì sao unique output row không chứng minh writer chỉ được gọi một lần?
18. SQL `EXCEPT` theo hai chiều kiểm tra điều gì?
19. Vì sao chỉ `COUNT(*)=expected` không đủ?
20. Vì sao phải có fail marker và deadline khi kill process?
21. Worker reply mất sau DB COMMIT: manager có được phát request mới ngay không?
22. Lease expired có đồng nghĩa worker cũ đã chết không?
23. Lease/fencing token khác idempotency key như thế nào?
24. Remote chunking và remote partitioning lưu reader checkpoint ở đâu?
25. Vì sao một worker `COMPLETED` có thể không cần chạy lại khi manager FAILED?
26. Test outbox publisher crash sau publish trước SENT kỳ vọng điều gì?
27. Test concurrency ở C=1 và C=8 phải giữ biến nào ổn định để so đúng?
28. Hikari pool exhausted có được coi là business skip không?
29. `retryLimit(3)` có giới hạn số lần restart qua nhiều JobExecutions không?
30. Khi metadata còn `STARTED` sau hard kill, vì sao không sửa status bằng SQL?
31. Những signals nào phân biệt worker chậm do DB connection pool với worker đang CPU-bound?
32. Tại sao test happy path COMPLETED không thay reconciliation/quality gate?

**Gợi ý trả lời:** (1) JobInstance là logical identity; JobExecution là một lần chạy; worker StepExecution theo step/partition. (2) Identifying run.id mới có thể tạo instance mới. (3) Không, chunk commits đã bền. (4) 1100. (5) Chunk 801–900. (6) Throw còn cleanup/metadata; kill không. (7) Process chết trước khi update status. (8) Snapshot, partition name/range, identifying params và business key. (9) ID của execution mới có thể đổi. (10) Danh sách partition names ổn định; splitter/repository quyết định restart. (11) Launch/test Job với context Spring Batch. (12) Transaction/locking/checkpoint persistence. (13) Fixture có thể không visible và che commit behavior. (14) Replay/duplicate nguy cơ. (15) Không, cần reconciliation/repair. (16) Im lặng bỏ qua same key khác payload. (17) DB constraint dedupe dù nhiều attempts. (18) Missing và extra. (19) Missing/extra có thể triệt tiêu. (20) Biết chính xác fault boundary và tránh test flaky. (21) Không, cần status/liveness/ownership và idempotency. (22) Không. (23) Quyền owner local vs chống duplicate effect tại downstream. (24) Manager trong remote chunking; worker trong remote partitioning. (25) Splitter chuẩn thường bỏ qua completed worker. (26) At-least-once publish, consumer dedupe. (27) Snapshot, plan và business rules. (28) Không, giữ durable work. (29) Không. (30) Có thể phá version/context/actual output. (31) Hikari pending/acquire/lock, CPU usage/throttling. (32) Job status không chứng minh keyset/hash/external effects.

## Tài liệu tham khảo

- [Spring Batch Reference 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils` và test scope.
- [Spring Batch Reference 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): local/remote partitioning, `Partitioner`, `gridSize` và StepExecutions.
- [Spring Batch Reference 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ItemStream`, `ExecutionContext` và checkpoint.
- [Spring Batch Reference 5.2 — Job Metadata](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): `JobInstance`/`JobExecution` và `JobOperator` lifecycle.
- [Spring Batch Reference 5.2 — Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html): fault-tolerant retry và phân loại lỗi.
- [Spring Batch Reference 5.2 — JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata persistence và transaction isolation.
- [Spring Batch Reference 5.2 — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/5.2/spring-batch-integration.html): remote chunking/partitioning integration patterns.
- [Spring Batch API 5.2 — JobOperator](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): `restart` và vận hành.
- [Spring Batch API 5.2 — JobLauncherTestUtils](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/test/JobLauncherTestUtils.html): launch Job và Step trong integration tests.
- [Spring Batch API 5.2 — JdbcCursorItemReaderBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/database/builder/JdbcCursorItemReaderBuilder.html): JDBC reader và checkpoint.
- [Spring Framework — Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries và callback semantics.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL thực trong integration tests.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): idempotent insert và conflict behavior.
- [PostgreSQL — Set Operations](https://www.postgresql.org/docs/current/queries-union.html): `EXCEPT` dùng kiểm tra missing/extra keys.

**Điểm cốt lõi:** **Test worker restart không chỉ là khiến một worker FAILED rồi xác nhận Job COMPLETED sau restart.** Phải cố định **JobInstance + immutable snapshot + partition plan**, inject fault tại **ranh giới giao dịch và giao nhận**, kiểm chứng metadata/worker ownership, và đối soát **missing, extra, payload/version conflict và external side effects**. Test local có thể chứng minh checkpoint/rollback; test hard-kill/remote mới phát hiện được mất ACK/reply và stale worker. Chỉ khi **output sau restart bằng clean reference, không mất/trùng business effects và recovery không vượt resource/SLA budgets**, mới nên coi tính năng worker restart đủ an toàn để mở rộng workload.
