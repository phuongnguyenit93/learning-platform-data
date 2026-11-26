# Điều chỉnh retry backoff khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Hiểu **retry**, **backoff**, **jitter**, **retry budget** và **retry amplification** trong batch có nhiều thread, partition hoặc remote worker.
- Phân loại được lỗi **tạm thời, có thể thử lại** so với lỗi **không thể khắc phục bằng retry**, tránh retry dữ liệu sai hoặc side effect không idempotent.
- Cấu hình Spring Batch **5.x / Java 17** với `FaultTolerantStepBuilder.retry(...)`, `retryLimit(...)` và `backOffPolicy(...)` của Spring Retry.
- Phân biệt fixed delay, exponential backoff, exponential random backoff và cách lựa chọn cap theo SLA, transaction timeout và tải DB/broker.
- Biết retry diễn ra ở **item/chunk/step/message/job** khác nhau; không tự áp một retry limit lên tất cả tầng.
- Tính chi phí chờ, số lần thử tối đa, tác động của retry lên throughput, HikariCP connection usage và RTO/RPO.
- Thiết kế retry với **rollback, checkpoint, restart, idempotency và duplicate delivery** đúng trong multi-threaded step, parallel steps, partitioning và remote chunking.
- Kiểm thử bằng **JUnit 5, Spring Retry `RetryTemplate` và `BackOffPolicy` giả** mà không đoán thời gian qua `Thread.sleep`.
- Instrument retry attempts, backoff duration, exhausted retries và successful business commits để điều chỉnh dựa trên số liệu thay vì tăng số lần thử theo cảm tính.
- Xây dựng bảng tuning, thí nghiệm fault injection và runbook khi DB/HTTP/broker gặp sự cố trong production.

## 1. Tình huống: thêm worker khiến cả hệ thống retry đồng loạt

Module **SPRING_BATCH_SCALING_OPERATIONS** hướng đến xử lý workload lớn qua multi-threaded step, parallel steps, partitioning và nhiều JVM. Để đạt thông lượng cao cần đo nút thắt, bảo đảm thread safety, retry/restart và sử dụng tài nguyên theo thực tế.

Giả sử một job nhập **8 triệu đơn hàng** từ snapshot bất biến vào PostgreSQL bằng 16 worker. Một lần contention khiến khoảng 40 transaction cùng nhận lỗi không lấy được lock. Nếu mỗi worker retry ngay lập tức 5 lần:

~~~text
Lần đầu:   40 request đang tranh chấp
Retry #1:  40 request gần như đồng thời
Retry #2:  40 request gần như đồng thời
Retry #3:  40 request gần như đồng thời
Retry #4:  40 request gần như đồng thời
Retry #5:  40 request gần như đồng thời
~~~

Thay vì giúp DB phục hồi, retry không có khoảng dãn có thể làm **lock wait, connection pending, transaction latency và retry count** tăng. Tốc độ attempts/s đẹp hơn nhưng **business goodput** — số bản ghi hợp lệ đã commit — lại giảm.

~~~mermaid
flowchart TD
    F["DB tạm chậm / lock contention"] --> R["Nhiều chunks thất bại"]
    R --> I["Retry ngay lập tức"]
    I --> Q["Thêm DB requests, locks, pool contention"]
    Q --> F
    R --> B["Bounded backoff + jitter"]
    B --> S["Trải lại các lần thử theo thời gian"]
    S --> C["DB có cơ hội phục hồi, commit hữu ích"]
~~~

**Retry backoff** là chính sách dãn thời gian **giữa các lần thử sau lỗi**; nó không làm dữ liệu sai trở thành đúng, không tự tăng công suất database và không tạo exactly-once. Mục tiêu là tránh phản ứng dây chuyền, tăng xác suất retry có ích và giữ khả năng phục hồi.

## 2. Retry và backoff khác nhau ở đâu?

| Thuật ngữ | Nghĩa | Giới hạn |
| --- | --- | --- |
| **Attempt** | Một lần gọi read/process/write hoặc thao tác được retry | Có thể chưa commit |
| **Retry** | Thực hiện lại sau một thất bại được phân loại | Có thể nhân đôi side effect nếu operation không idempotent |
| **Retry limit** | Ngưỡng cho số lần thử theo policy tại một phạm vi retry | Không tự đồng bộ qua restart, pod hay broker |
| **Backoff** | Khoảng chờ giữa hai attempts | Không làm DB phục vụ nhanh hơn về lâu dài nếu vượt capacity |
| **Initial delay** | Khoảng chờ đầu tiên khi cần retry | Không đồng nghĩa timeout của query |
| **Multiplier** | Hệ số tăng delay giữa các retry | Không bảo đảm mọi khoảng chờ đều chính xác khi jitter |
| **Maximum interval (cap)** | Trần delay của một lần backoff | Khác tổng thời gian retry |
| **Jitter** | Yếu tố ngẫu nhiên để tránh retry cùng nhịp | Không thay điều khiển concurrency/circuit breaker |
| **Retry budget** | Giới hạn lượng retry theo một khoảng/đích/hệ thống | Cần điều phối nếu nhiều JVM cùng dùng DB |
| **Exhausted retry** | Không còn retry theo policy | Step có thể fail hoặc thực hiện skip/recovery nếu được cấu hình |
| **Idempotency** | Thực hiện lại operation không tạo hiệu ứng nghiệp vụ lặp sai | Không miễn trừ việc giữ đúng input/snapshot |

Ví dụ một policy có **tối đa bốn attempts, tính cả lần đầu** (định nghĩa rõ trong ví dụ này):

~~~text
Attempt 1 --fail--> wait 250 ms
Attempt 2 --fail--> wait 500 ms
Attempt 3 --fail--> wait 1000 ms
Attempt 4 --fail--> exhausted

Tối đa 4 attempts
Có tối đa 3 lần chờ trước các attempts kế tiếp
Tổng waiting time khi tất cả fail = 1750 ms
~~~

Bảng thời gian chỉ tính **backoff**; toàn bộ thời gian còn có SQL time, transaction rollback, queue wait, serialization và các chi phí khác.

**Lưu ý về API:** thuật ngữ và phép đếm của `retryLimit` trong Spring Batch/Spring Retry cần đối chiếu theo phiên bản/cấu hình; không được suy từ ví dụ “4 attempts gồm cả lần đầu” rằng mọi policy trong mọi layer dùng chính xác cùng semantics. Hãy kiểm thử số lần gọi thực tế.

## 3. Phân loại lỗi trước khi quyết định retry

Retry chỉ hữu ích khi lỗi có xác suất tự hết trong giới hạn thời gian và operation có thể thực hiện lại an toàn.

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| **Transient DB concurrency** | Deadlock, không lấy được lock, serialization conflict | Retry có backoff, giới hạn attempts; kiểm tra transaction rollback |
| **Transient DB connectivity** | Kết nối bị reset/DB failover trong thời gian ngắn | Bounded backoff, thử reconnect; cần health/circuit breaker |
| **Rate limit API** | HTTP 429 có `Retry-After` | Tôn trọng server hint và quota; jitter/rate limiter |
| **Server overloaded** | HTTP 503, broker tạm unavailable | Exponential backoff có cap và retry budget |
| **Transient network timeout** | Mất reply/timeout khi gọi API | Retry **chỉ khi** dedup/idempotency hợp lệ; timeout không chứng minh chưa commit |
| **Data validation** | Sai schema, bắt buộc thiếu field | Không retry mù; fail/skip theo business policy |
| **Business constraint** | Unique violation do dữ liệu sai/mismatch | Không blanket retry; phân loại duplicate hợp lệ vs lỗi thật |
| **Authentication/permission** | HTTP 401/403, DB permission denied | Thường fail fast; sửa quyền/credential rồi restart |
| **Serialization incompatibility** | Class không tồn tại, metadata codec lệch version | Fail rõ và migration; backoff không chữa |
| **Poison item** | Một record luôn làm processor throw | Không retry vô hạn; có policy fail/skip/DLQ rõ |
| **Out of capacity kéo dài** | Disk full, quota DB không đủ | Backoff có thể giảm tải tạm, nhưng cần xử lý nguyên nhân và dừng an toàn |

Không đánh đồng **mọi `SQLException`** hoặc **mọi `RuntimeException`** là retryable. Spring `DataAccessException` có phân loại transient và non-transient, nhưng mapping thực tế còn phụ thuộc JDBC driver, SQLSTATE và phiên bản Spring.

### Tách retryable khỏi skippable

- **Retryable:** có khả năng thành công sau một lần thử khác, ví dụ deadlock thoáng qua.
- **Skippable:** nghiệp vụ chấp nhận loại một item khỏi kết quả và có cơ chế audit/giới hạn, ví dụ dòng hỏng định dạng trong một job cho phép bỏ qua.
- **Fatal:** không thể tiếp tục job đúng, ví dụ snapshot đầu vào sai version, thiếu khóa truy cập, dữ liệu nghiệp vụ bất biến bị mâu thuẫn.

Một item có thể được retry trước, sau đó skip **chỉ khi** policy skip cho phép. Không dùng `skipLimit` rộng để job nhìn có vẻ nhanh hơn nhưng output thiếu records bắt buộc.

### Lỗi không chắc đã commit

HTTP call, broker publish hoặc database write có thể **thành công ở đích rồi mất reply**. Đây không đơn giản là “transient error thì gọi lại”; phải có business operation identity và idempotency guard, reconciliation hoặc giao thức xác nhận hợp lệ.

## 4. Retry ở tầng nào? Tránh lặp lại nhiều lớp

Spring Batch và một ứng dụng distributed có thể retry tại nhiều tầng:

~~~mermaid
flowchart TD
    J["Scheduler / whole Job retry"] --> ST["Step restart / replay"]
    ST --> C["Fault-tolerant chunk retry"]
    C --> S["HTTP/DAO client retry"]
    S --> Q["Broker redelivery / consumer retry"]
    Q --> DB["Business database/API"]
~~~

Nếu **mỗi tầng đều retry tối đa bốn lần**, một operation ở trường hợp xấu có thể gây **4 × 4 × 4 = 64 attempts ở phía sau** (khi cả ba tầng áp dụng tuần tự và không chặn trùng), thậm chí cao hơn nếu job restart hoặc broker cũng redeliver. Đây là phép tính **cận minh họa**, không phải mặc định Spring Batch luôn nhân retry theo cách ấy.

### Ví dụ chia trách nhiệm

- Step `FaultTolerantStepBuilder`: retry hữu hạn các lỗi DB transient trong read/process/write đúng contract.
- Client HTTP: chỉ retry nếu có idempotency key, quota và policy riêng; tránh cộng dồn vô tình.
- Broker: ack/nack, delayed retry/DLQ theo message delivery semantics, không đồng nhất với chunk retry.
- Scheduler: restart khi job thật sự thất bại, với `JobInstance`/snapshot/metadata được xác minh; không tự tạo `run.id` mỗi lần lỗi.
- Bảng business ledger: unique operation ID và reconciliation, giúp retry/replay không tạo duplicate effects.

**Nguyên tắc:** quyết định một nơi sở hữu chính sách retry cho **mỗi lớp failure** và đặt ngân sách tổng; không bật retry độc lập tại tất cả tầng chỉ vì từng thư viện đều hỗ trợ.

## 5. Fixed, exponential, randomized: chọn policy nào?

| Backoff policy | Delay minh họa | Lợi thế | Rủi ro |
| --- | --- | --- | --- |
| **No backoff** | 0,0,0 | Giảm latency nếu lỗi rất thoáng | Thundering herd, retry storm |
| **Fixed** | 500,500,500 ms | Đơn giản, dễ dự đoán | Worker cùng nhịp dễ retry đồng loạt |
| **Exponential** | 250,500,1000,2000 ms | Giảm tần suất khi lỗi kéo dài | Đồng bộ nếu cùng start và cùng schedule |
| **Capped exponential** | 250,500,1000,2000,4000,4000... ms | Không chờ một attempt vô hạn | Vẫn có herd nếu không jitter |
| **Exponential randomized** | Các khoảng chờ biến đổi tăng theo cấp số nhân | Phân tán attempts của nhiều workers | Cần kiểm soát cap và phân phối thực tế |
| **Full jitter theo envelope** | Random trong `[0, cappedDelay]` | Giảm đồng bộ mạnh | Có thể tạo delay ngắn, cần rate budget toàn cụm |
| **Delay từ Retry-After** | Hint của server, có bound | Tôn trọng quota/downstream | Header có thể thiếu/sai, vẫn cần cap và policy |

Các dãy delay là ví dụ. `ExponentialRandomBackOffPolicy` của Spring Retry **không mặc nhiên đồng nhất** với công thức “full jitter từ 0 đến cap”; muốn đúng thuật toán jitter cụ thể phải chọn/triển khai và test đúng policy.

### Công thức cấp số nhân với cap

Giả sử lần chờ đầu tiên là `d0`, hệ số tăng `m` và trần `dmax`:

\[
d_k = \min(d_{\max}, d_0 \times m^{k-1}),\quad k = 1,2,\ldots
\]

Với `d0=250 ms`, `m=2`, `dmax=4.000 ms`:

~~~text
Retry wait #1: 250 ms
Retry wait #2: 500 ms
Retry wait #3: 1000 ms
Retry wait #4: 2000 ms
Retry wait #5: 4000 ms
Retry wait #6: 4000 ms (đã chạm cap)
~~~

Trần **mỗi lần chờ** không bằng giới hạn tổng thời gian. Nếu một request thất bại mất 10 giây trước khi trả lỗi và có 5 attempts, tổng latency có thể lớn dù `maxInterval` chỉ 4 giây.

### Jitter hữu ích trong nhiều JVM

Nếu tất cả 50 workers nhận lỗi tại cùng thời điểm và dùng cùng fixed/exponential delay, họ có thể retry cùng những mốc thời gian:

~~~text
t = 0s       50 workers fail
t = 0.25s    50 workers retry
t = 0.75s    50 workers retry
t = 1.75s    50 workers retry
~~~

Với jitter, những attempts được trải theo một khoảng thời gian, giảm khả năng tất cả cùng tranh một index/lock/connection. **Jitter không thay throttling**: nếu arrival rate liên tục vượt DB service rate, backlog vẫn tăng.

## 6. Cấu hình Spring Batch 5.x: retry + capped exponential backoff

Trong Spring Batch 5.x, cấu hình fault-tolerant chunk step có thể sử dụng `FaultTolerantStepBuilder` cùng Spring Retry `BackOffPolicy`. Ví dụ Java 17:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.retry.backoff.BackOffPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

record OrderEvent(String snapshotId, long orderId, String payload) {}

@Configuration
class RetryBackoffStepConfiguration {

    @Bean("dbRetryBackOffPolicy")
    BackOffPolicy dbRetryBackOffPolicy() {
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();
        policy.setInitialInterval(250L);   // milliseconds
        policy.setMultiplier(2.0);
        policy.setMaxInterval(4000L);
        return policy;
    }

    @Bean("retryingImportStep")
    Step retryingImportStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("orderEventReader")
                ItemReader<OrderEvent> reader,
            @Qualifier("orderEventProcessor")
                ItemProcessor<OrderEvent, OrderEvent> processor,
            @Qualifier("orderEventWriter")
                ItemWriter<OrderEvent> writer,
            @Qualifier("dbRetryBackOffPolicy")
                BackOffPolicy backOffPolicy) {

        return new StepBuilder("retryingImportStep", repository)
                .<OrderEvent, OrderEvent>chunk(
                        200, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(CannotAcquireLockException.class)
                .retry(TransientDataAccessResourceException.class)
                .retryLimit(4)
                .backOffPolicy(backOffPolicy)
                .build();
    }
}
~~~

### Diễn giải đúng ví dụ

- `chunk(200, transactionManager)` xác định transaction boundary của chunk, **không phải** “cứ 200 item là một transaction chắc chắn thành công”.
- `retry(...)` chỉ định loại exception được phép retry. Ví dụ cố ý chọn **hai nhóm lỗi cụ thể**, không blanket retry toàn bộ `Exception`.
- `retryLimit(4)` đặt ngưỡng retry theo semantics của Spring Batch phiên bản đang chạy; để thiết kế SLA chính xác cần **integration test actual attempt count**.
- `backOffPolicy(...)` nhận policy Spring Retry. `ExponentialBackOffPolicy` trên có initial delay 250 ms, multiplier 2 và cap 4.000 ms cho **những lần cần backoff**.
- Khi retry đã cạn và không có `skip`/recovery rule, step có thể **FAILED** theo lifecycle. Đừng bắt tất cả lỗi rồi trả thành công giả.
- Ví dụ yêu cầu các bean reader/processor/writer, repository, transaction manager và database/schema đã được cấu hình riêng. Nó **không** là một ứng dụng tự chạy hoàn chỉnh chỉ bằng một class.
- Với reader có `ItemStream`, proxy/scoping đúng để framework đăng ký `open/update/close`. `@StepScope` không tự làm reader thread-safe nếu một StepExecution có nhiều chunk threads.
- Nếu ứng dụng có Spring Batch 5.x minor khác nhau, xác nhận exact builder methods/dependencies theo dependency tree của ứng dụng và chạy compilation/integration test ở bước kiểm thử dự án.

### Không phải lỗi nào cũng nên dùng cùng policy

Một lỗi deadlock DB có thể thử lại nhanh hơn lỗi HTTP 503 do hệ thống bên ngoài đang bảo trì. Tách **Step hoặc thao tác** theo nhóm dependency khi cần, không dùng cùng retry limit và delay cho mọi exception vì tiện.

## 7. Jitter trong Spring Retry: tránh đồng bộ lịch retry

Để có một dạng backoff tăng dần với randomization do Spring Retry cung cấp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.BackOffPolicy;
import org.springframework.retry.backoff.ExponentialRandomBackOffPolicy;

@Configuration
class RandomizedBackOffConfiguration {

    @Bean("randomizedDbBackOffPolicy")
    BackOffPolicy randomizedDbBackOffPolicy() {
        ExponentialRandomBackOffPolicy policy =
                new ExponentialRandomBackOffPolicy();
        policy.setInitialInterval(250L);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(5000L);
        return policy;
    }
}
~~~

Sử dụng bean này ở `.backOffPolicy(...)` thay bean cố định khi xác suất **nhiều worker cùng nhận lỗi** cao. Spring Retry có thuật toán randomization riêng của `ExponentialRandomBackOffPolicy`; **không nên mô tả nó như full jitter chính xác theo công thức `random(0, cap)`**.

### Số liệu để quyết định có cần jitter

- Nhiều pod báo lỗi trong cùng 1–2 giây sau DB failover?
- Retry attempts và lock wait tạo “sóng” theo chu kỳ delay cố định?
- Tại một mốc retry, Hikari `pending` cùng tăng ở tất cả pods?
- Khi bật jitter, `goodput` phục hồi mượt hơn, p95 DB commit thấp hơn và retry exhaustion có giảm không?
- Jitter có làm vượt deadline của message hoặc RTO, khiến work bị redeliver không?

Randomization có giá trị khi các clients cạnh tranh **cùng shared downstream**. Nếu một job chỉ có một worker, ưu thế của jitter có thể nhỏ; vẫn phải đo theo resource và workload thật.

## 8. Rollback, transaction và checkpoint: retry phải đi cùng correctness

Một lỗi trong chunk có thể dẫn đến rollback và retry theo fault-tolerant step lifecycle. Các điểm cần hiểu:

~~~mermaid
sequenceDiagram
    participant S as Chunk Step
    participant R as Reader
    participant W as Writer
    participant D as Business DB
    participant J as JobRepository
    S->>R: read items
    S->>W: write chunk
    W->>D: SQL fails (transient)
    S->>D: Rollback transaction
    S->>S: Retry policy / bounded backoff
    S->>W: Re-attempt eligible work
    W->>D: Commit business result
    S->>J: Persist checkpoint per configured transaction boundary
~~~

Sơ đồ là **mô hình khái niệm**, không mô tả chính xác thứ tự rollback/backoff của mọi reader/processor/writer, cấu hình stateful retry, transaction propagation và các DataSource. Spring Batch có thể đưa chunk/item qua retry/recovery paths khác nhau. Hãy instrument transaction và kiểm thử thực tế.

### Nguy cơ giữ connection và lock trong thời gian backoff

`BackOffPolicy` đồng bộ thường làm **thread hiện tại chờ**. Nếu delay xảy ra trong vùng còn giữ JDBC transaction/connection/lock theo cấu hình retry, nó có thể làm DB contention **nặng hơn** thay vì nhẹ đi. Không mặc định “thêm backoff là giải phóng connection”; phải đo Hikari usage, PostgreSQL `pg_stat_activity`/lock wait và transaction boundary thật.

### ItemStream state có thể rollback khác business side effect

- `ExecutionContext` và reader checkpoint được persist theo lifecycle chunk. Không sửa trực tiếp context hay nhảy offset để “bỏ chunk lỗi”.
- Nếu reader không hỗ trợ restart đúng, việc retry item có thể làm đọc lại/bỏ sót input.
- Nếu business DB và `JobRepository` là hai transaction resources khác nhau, business commit có thể xảy ra trước khi metadata checkpoint được lưu.
- Khi restart, một chunk có thể được replay từ **last durable checkpoint**; writer phải idempotent theo business key và snapshot.
- Retry limit trong-memory của một attempt không nhất thiết được tiếp tục qua JVM crash hoặc job restart. **Không dùng retryLimit như giới hạn số lần xử lý toàn đời của một business key**.

## 9. Retry, skip và rollback: cấu hình nào dẫn tới mất dữ liệu?

Một step fault-tolerant có thể vừa retry vừa skip, nhưng đó là **hai quyết định khác nhau**.

~~~java
// Ví dụ minh họa logic policy, KHÔNG bật skip cho dữ liệu bắt buộc.
return new StepBuilder("optional-data-step", repository)
        .<InputRow, OutputRow>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(CannotAcquireLockException.class)
        .retryLimit(4)
        .backOffPolicy(backOffPolicy)
        .skip(BadOptionalRowException.class)
        .skipLimit(10)
        .build();
~~~

Trong ví dụ, `BadOptionalRowException` là **custom exception** do ứng dụng định nghĩa, và chỉ được skip khi business contract chấp nhận tối đa 10 record lỗi. Không áp `skip(Exception.class)` cho đơn hàng tài chính bắt buộc, vì job có thể báo `COMPLETED` dù còn missing business keys.

### Khi nào rollback?

Rollback policy phụ thuộc loại exception, phase read/process/write, transaction manager và fault-tolerant configuration. Việc không rollback một exception chưa chắc an toàn cho business writer. **Không áp `noRollback(...)` cho lỗi DB chỉ để giảm retry latency** nếu transaction/database đã ở trạng thái lỗi hoặc cần rollback để tái thử hợp lệ.

### Khi không được retry?

Một `ItemProcessor` thay đổi external state mỗi lần được gọi (ví dụ tạo hóa đơn hoặc gửi email) không nên bị retry một cách mù quáng. Chuyển side effect sang writer/idempotent operation hoặc transactional outbox, giữ processor thuần khi có thể.

## 10. Idempotent writer: retry không làm nhân đôi bản ghi

Một writer có thể đã commit một số side effect trước khi process chết hoặc reply bị mất. Dùng **business operation identity** ổn định qua retry và restart:

~~~sql
CREATE TABLE imported_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);

INSERT INTO imported_order(snapshot_id, order_id, payload)
VALUES (:snapshotId, :orderId, :payload)
ON CONFLICT (snapshot_id, order_id)
DO UPDATE SET payload = EXCLUDED.payload;
~~~

Nếu snapshot immutable và payload luôn nhất quán, retry lại cùng `(snapshot_id, order_id)` không tạo hai rows. Tuy nhiên:

- UPSERT có thể kích hoạt **trigger/audit** lần nữa dù final row không trùng.
- Một API charge/payment/email ngoài DB không tự trở nên idempotent chỉ vì bảng đích có unique key.
- Nếu input biến đổi giữa hai lần chạy, retry có thể overwrite record theo phiên bản sai. Cần snapshot/version guard.
- `writeCount` của Spring Batch có thể đếm item writer xử lý, không nhất thiết số **unique rows newly committed**.
- Với multiple writers trên cùng order key, phải xác định conflict resolution; backoff không thay lock/order contract.

### Idempotency key cho external call

Một key ổn định có thể có dạng:

~~~text
operationKey = snapshotId + ":" + businessOrderId + ":" + operationType
~~~

Bên đích phải dedup theo key đó hoặc hệ thống phải dùng ledger/outbox. Chỉ sinh random UUID mới cho **mỗi retry attempt** làm key sẽ mất tác dụng chống duplicate.

### Phân biệt retry và reprocess hợp lệ

Nếu một business order được reprocess trên snapshot/version mới, nó có thể là operation **mới hợp lệ**, không phải duplicate sai. Định nghĩa idempotency key cần bao gồm đúng phạm vi nghiệp vụ; không chọn unique key quá rộng khiến job mới không thể cập nhật kết quả hợp lệ.

## 11. Kiểm thử retry và backoff mà không phải ngủ thật

Một phép thử tốt phải đo **số lần thử, exception và số lần gọi backoff**. Không dựa vào việc hệ điều hành sẽ đánh thức thread đúng sau 250 ms.

Đoạn Java 17/JUnit 5 sau dùng Spring Retry `RetryTemplate` với `BackOffPolicy` giả để quan sát callback mà không `Thread.sleep`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.retry.RetryContext;
import org.springframework.retry.backoff.BackOffContext;
import org.springframework.retry.backoff.BackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

class RetryPolicyTest {

    static class RecordingBackOffPolicy implements BackOffPolicy {
        final AtomicInteger backoffs = new AtomicInteger();

        @Override
        public BackOffContext start(RetryContext context) {
            return new BackOffContext() {};
        }

        @Override
        public void backOff(BackOffContext context) {
            backoffs.incrementAndGet();
        }
    }

    static RetryTemplate template(BackOffPolicy backOff) {
        Map<Class<? extends Throwable>, Boolean> retryable =
                Map.of(CannotAcquireLockException.class, true);
        var template = new RetryTemplate();
        template.setRetryPolicy(new SimpleRetryPolicy(4, retryable));
        template.setBackOffPolicy(backOff);
        return template;
    }

    @Test
    void succeedsAfterTwoTransientErrors() {
        var policy = new RecordingBackOffPolicy();
        var attempts = new AtomicInteger();

        String value = template(policy).execute(context -> {
            if (attempts.incrementAndGet() < 3) {
                throw new CannotAcquireLockException("Transient");
            }
            return "ok";
        });

        assertEquals("ok", value);
        assertEquals(3, attempts.get());
        assertEquals(2, policy.backoffs.get());
    }

    @Test
    void exhaustsAfterFourTotalAttempts() {
        var policy = new RecordingBackOffPolicy();
        var attempts = new AtomicInteger();

        assertThrows(CannotAcquireLockException.class, () ->
            template(policy).execute(context -> {
                attempts.incrementAndGet();
                throw new CannotAcquireLockException("Still locked");
            })
        );

        assertEquals(4, attempts.get());
        assertEquals(3, policy.backoffs.get());
    }

    @Test
    void doesNotRetryValidationException() {
        var policy = new RecordingBackOffPolicy();
        var attempts = new AtomicInteger();

        assertThrows(IllegalArgumentException.class, () ->
            template(policy).execute(context -> {
                attempts.incrementAndGet();
                throw new IllegalArgumentException("Invalid business row");
            })
        );

        assertEquals(1, attempts.get());
        assertEquals(0, policy.backoffs.get());
    }
}
~~~

**Quan trọng:** đây là test của `RetryTemplate` và `SimpleRetryPolicy`, trong đó max attempts = 4 **gồm lần thử đầu**. Không mặc định `FaultTolerantStepBuilder.retryLimit(4)` sẽ gọi writer/process/read đúng bốn lần trong mọi tình huống chunk rollback, reader state hoặc item buffering.

### Integration test với Spring Batch step thật

- Sử dụng `JobLauncher` và JDBC `JobRepository` trên database test, không chỉ mock StepBuilder.
- Writer giả ném `CannotAcquireLockException` trong những lần được điều khiển, rồi commit vào bảng application.
- Assert số lần gọi, rollback/commit và `StepExecution` cuối cùng.
- Test cả lỗi xảy ra ở reader, processor và writer; semantics retry có thể khác.
- Dùng latch/barrier để tạo DB-lock hoặc failover window, không dùng `Thread.sleep` để đoán thời điểm.
- Một test method có `@Transactional` không tự truyền transaction sang worker threads; tránh fixture chưa commit không đọc được.
- Kiểm tra business output sau restart, không suy từ số attempts thành số unique records.

## 12. Hiểu jitter qua phép toán thuần, tách khỏi thời gian thật

Đoạn dưới chỉ minh họa **full jitter** trên một capped exponential envelope; **không** khẳng định Spring Retry `ExponentialRandomBackOffPolicy` sử dụng cùng phân phối.

~~~java
import java.util.random.RandomGenerator;

public final class RetryDelayMath {

    private RetryDelayMath() {}

    public static long cappedExponential(
            long initialMillis, long maxMillis, int waitNumber) {

        if (initialMillis <= 0 || maxMillis < initialMillis
                || waitNumber < 1) {
            throw new IllegalArgumentException("Invalid backoff");
        }

        long delay = initialMillis;
        for (int n = 1; n < waitNumber; n++) {
            // Saturating multiplication, tránh tràn số khi nhân đôi.
            delay = delay > maxMillis / 2
                    ? maxMillis
                    : Math.min(maxMillis, delay * 2);
        }
        return delay;
    }

    public static long fullJitter(
            long delayEnvelopeMillis, RandomGenerator rng) {

        if (delayEnvelopeMillis <= 0 || rng == null) {
            throw new IllegalArgumentException("Invalid jitter");
        }

        // Phân phối trên [0, delayEnvelopeMillis).
        return rng.nextLong(delayEnvelopeMillis);
    }
}
~~~

Ví dụ test thuần không tạo thread/chờ thật:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.SplittableRandom;
import org.junit.jupiter.api.Test;

class RetryDelayMathTest {

    @Test
    void envelopeDoublesAndIsCapped() {
        assertEquals(250, RetryDelayMath.cappedExponential(
                250, 4000, 1));
        assertEquals(500, RetryDelayMath.cappedExponential(
                250, 4000, 2));
        assertEquals(1000, RetryDelayMath.cappedExponential(
                250, 4000, 3));
        assertEquals(4000, RetryDelayMath.cappedExponential(
                250, 4000, 20));
    }

    @Test
    void sampleIsInsideEnvelope() {
        var random = new SplittableRandom(42);
        for (int i = 0; i < 1000; i++) {
            long v = RetryDelayMath.fullJitter(1000, random);
            assertTrue(v >= 0 && v < 1000);
        }
    }
}
~~~

Ví dụ `maxMillis` có cap nhỏ phù hợp trong batch. Nếu đưa helper vào production, phải kiểm soát các edge cases (cap cực lớn, overflow, input không hợp lệ); Spring Retry đã có policy chuẩn nên không cần tự triển khai khi chỉ muốn exponential random thông thường. Test ngẫu nhiên nên xác nhận **bounds/thuộc tính**, không assert một thời điểm ngủ chính xác.

## 13. Retry budget và tải nhân lên khi tăng worker

Giả sử 24 workers xử lý đồng thời, policy cho tối đa **4 attempts gồm lần đầu** theo định nghĩa của mô hình này:

~~~text
24 workers × 4 attempts = tối đa 96 attempts tích lũy
24 workers × 3 retries  = tối đa 72 attempts bổ sung
~~~

Đây không phải 96 query **chạy cùng một lúc**, nhưng nếu workers cùng lịch backoff, có thể có 24 requests xuất hiện theo từng đợt.

Giả sử mỗi attempt thất bại mất 100 ms; ba khoảng chờ là 250, 500 và 1000 ms:

~~~text
Attempt time: 4 × 100 = 400 ms
Waiting time: 250 + 500 + 1000 = 1750 ms
Total idealized duration = 2150 ms
~~~

Thời gian thật còn connection acquisition, rollback, scheduler, metadata commit và broker. Nếu mỗi SQL call đợi lock tới 10 giây trước khi lỗi, retry có thể kéo dài vượt deadline job dù `maxInterval` nhỏ.

### Chính sách retry budget cấp cluster

Một thiết kế minh họa:

- Giới hạn tổng retry calls vào PostgreSQL ở mức **150 request/s toàn cụm**, không chỉ trong một JVM.
- Tối đa bốn attempts cho mỗi logical operation, có **idempotency key** ổn định.
- Một business key không được có vô hạn attempts song song.
- Khi lock waits, Hikari pending hoặc error rate tăng, **dừng scale-out** và giảm admission/concurrency.
- Có giới hạn toàn bộ **elapsed time** ngoài attempts; hết deadline thì fail/queue và phục hồi theo policy.

Các số trên **không phải thuộc tính mặc định** của Spring Batch. Limiter trong mỗi JVM riêng không tự tạo limit toàn cluster: nhân số replicas có thể vượt ngân sách database.

### Đo goodput song song attempts

Nếu attempt rate tăng từ 1.000 lên 2.000/s nhưng unique committed item/s giảm từ 900 xuống 500, retry đang làm hệ tốn tài nguyên hơn mà không hoàn tất nhiều nghiệp vụ hơn. Không dùng `writeCount` hoặc `readCount` một mình làm tiêu chí tuning.

## 14. Multi-threaded step: backoff có thể chiếm worker slots

Với backoff đồng bộ, thread thường chờ khi đang retry. Ví dụ:

~~~text
Executor slots = 8
5 threads đang backoff sau DB lock error
2 threads đang chờ lấy JDBC connection
1 thread đang commit business output

CPU còn rảnh, nhưng useful concurrency chỉ ~1.
~~~

Tăng lên 32 threads khi DB đang hết connections có thể tạo thêm lock wait, pending queue và retry storm. Cần đo `TaskExecutor.activeCount`, queue depth, Hikari `active/pending`, JDBC acquisition/usage time và PostgreSQL wait events trên cùng timeline.

**Đừng mặc định thread backoff đã giải phóng connection.** Retry scope và transaction boundaries quyết định liệu backoff có diễn ra lúc connection/lock còn giữ không; kiểm tra thực tế, rút transaction hoặc đổi chiến lược nếu cần.

### Thread safety và checkpoint

- `@StepScope` không tự cho mỗi **thread** một ItemReader riêng trong cùng `StepExecution`.
- Một reader có mutable cursor phải an toàn cho concurrency thực tế.
- Chunk completion có thể đảo thứ tự vì một chunk retry lâu hơn các chunk khác.
- Checkpoint/restart cần được test sau crash; wrapping reader bằng lock không tự tạo exactly-once.
- Không tự thêm `RetryTemplate` ở mọi processor/writer khi step đã dùng `faultTolerant()` vì nested retries có thể nhân số attempts.
- Spring Retry policies chuẩn duy trì retry/backoff context theo execution; không sửa bean cấu hình policy đang được các thread sử dụng.

## 15. Parallel steps và partitioning: retry theo worker, nhưng budget theo DB

Một `Job` có thể chạy nhiều flows hoặc partitions trên cùng PostgreSQL:

~~~text
64 input partitions
8 worker JVMs × 4 execution slots/JVM = 32 concurrent partitions
RetryPolicy được áp dụng riêng theo worker Step
Shared downstream vẫn là một database
~~~

`gridSize=64` không đồng nghĩa có 64 threads đồng thời. Số partitions và execution slots khác nhau; lịch điều phối của handler mới quyết định overlap.

Khi 32 partitions cùng gặp lock/error, retries có thể dồn vào một thời điểm. Jitter và admission control giúp giảm đồng bộ nhưng nếu DB saturated **liên tục**, phải giảm concurrency/giải quyết hot keys/transaction scope.

### Restart không đồng nghĩa retry

- Chunk retry xảy ra khi Step còn chạy và retry policy cho phép.
- Partition restart/redispatch là điều phối một `StepExecution`/partition đã failed hoặc mất owner.
- Job restart tạo `JobExecution` mới trong **cùng JobInstance** khi hợp lệ; không đổi identifying parameters chỉ để chạy lại.
- Không thay snapshot ID, partition names/ranges và reader ordering của một JobInstance đang resume.
- Nếu worker A còn sống nhưng manager mất kết nối, chỉ giao lại partition cho B sau khi xác minh A dừng hoặc có fencing.
- Một partition retry quá lâu có thể trở thành **straggler** kéo dài toàn job; đôi khi fail fast để vận hành phục hồi tốt hơn tăng limit vô hạn.

## 16. Remote chunking: retry tại broker không phải retry trong Step

Trong remote chunking, manager thường sở hữu reader và gửi chunk items qua middleware. Worker process/write rồi trả reply. Một `BackOffPolicy` gắn với Spring Batch StepBuilder **không tự cấu hình** broker delayed retries, nack/requeue, DLQ hoặc manager request timeout.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant A as Worker A
    participant D as Business DB
    participant B as Worker B
    M->>Q: Publish chunk K
    Q->>A: Deliver K
    A->>D: Commit business output
    Note over A,M: ACK / reply thất lạc
    Q->>B: Redeliver K
    B->>D: Idempotent replay theo business key
    B-->>M: Correlated reply K
~~~

| Cấp retry | Kích hoạt | Phải kiểm soát |
| --- | --- | --- |
| Batch chunk retry | Read/process/write exception được cho phép | Backoff, limit, rollback, checkpoint |
| Broker retry/redelivery | Unacked/NACK, consumer crash, delivery timeout | Delivery count, delayed queue, DLQ |
| Remote partition redispatch | Partition worker mất hoặc reply không đến | StepExecution ID, ownership/fencing |
| Job restart | Job/step failed/stopped, được phép resume | JobInstance, snapshot, checkpoint |

**Timeout không chứng minh business commit đã thất bại.** Chunk có thể được ghi thành công rồi mất reply; retry cùng message hoặc một chunk được chia lại phải sử dụng business operation ID ổn định, không chỉ UUID mới cho mỗi lần publish.

Đưa message vào **DLQ** không đồng nghĩa business output đã đầy đủ. Với dữ liệu bắt buộc, phải có runbook kiểm tra commit, retry/reconciliation, và không publish report khi còn missing keys. Không tự xóa DLQ/reply queue vì message có thể gắn với output đã commit.

## 17. HTTP 429/503: Retry-After, limiter và circuit breaker

Khi Spring Batch gọi API bên ngoài, một phản hồi có thể là:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 10
~~~

`Retry-After` có thể là số giây hoặc HTTP date, nên cần parse theo chuẩn bằng HTTP client, kiểm tra hợp lệ, đặt cap và deadline. Không tin vô điều kiện một header chứa thời gian cực dài.

Chính sách application-layer minh họa:

~~~text
clientDelay = exponentialWithJitter(retryIndex)
serverHint = parsed Retry-After nếu hợp lệ
chosenDelay = min(maxAllowedDelay, max(clientDelay, serverHint))

Nếu tổng elapsed budget hoặc deadline bị vượt:
    ngừng retry, báo lỗi hoặc đưa vào deferred queue
~~~

Đây **không phải behavior mặc định** của `ExponentialBackOffPolicy` trong StepBuilder; muốn xét `Retry-After` thường phải cấu hình tầng HTTP client/custom policy.

- **Rate limiter** kiểm soát calls/s theo quota, nhất là khi nhiều pods cùng gọi một API.
- **Circuit breaker** ngừng gọi tạm khi downstream hỏng kéo dài, có half-open/recovery policy.
- **Bulkhead** giữ số operations concurrent trong budget, không để một API lỗi chiếm mọi threads.
- **Idempotency key** bắt buộc cho payment/POST có thể đã thành công rồi timeout.
- **Backpressure** giảm admission khi downstream phục vụ chậm hơn input, không chỉ kéo dài delay.

HTTP 401/403 hoặc malformed schema thường không tự hết nhờ retry. Không blanket retry mọi HTTP 4xx hoặc mọi `RuntimeException`.

## 18. Đưa retry settings ra application properties

Một ví dụ cấu hình **do ứng dụng tự định nghĩa**, không phải Spring Boot/Spring Batch tự áp dụng:

~~~yaml
app:
  batch:
    retry:
      retry-limit: 4
      initial-delay: 250ms
      max-delay: 5s
      multiplier: 2.0
      randomized: true
~~~

Có thể bind bằng `@ConfigurationProperties`:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.batch.retry")
public record RetryTuningProperties(
        int retryLimit,
        Duration initialDelay,
        Duration maxDelay,
        double multiplier,
        boolean randomized) {

    public RetryTuningProperties {
        if (retryLimit < 1 || initialDelay == null
                || maxDelay == null || initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay.compareTo(initialDelay) < 0
                || !Double.isFinite(multiplier)
                || multiplier < 1.0) {
            throw new IllegalArgumentException(
                    "Invalid batch retry configuration");
        }
    }
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.retry.backoff.BackOffPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.backoff.ExponentialRandomBackOffPolicy;

@Configuration
@EnableConfigurationProperties(RetryTuningProperties.class)
class BackOffFromPropertiesConfiguration {

    @Bean("configuredBackOff")
    BackOffPolicy configuredBackOff(RetryTuningProperties p) {
        ExponentialBackOffPolicy policy = p.randomized()
                ? new ExponentialRandomBackOffPolicy()
                : new ExponentialBackOffPolicy();

        policy.setInitialInterval(p.initialDelay().toMillis());
        policy.setMaxInterval(p.maxDelay().toMillis());
        policy.setMultiplier(p.multiplier());
        return policy;
    }
}
~~~

Bean `configuredBackOff` được inject vào `backOffPolicy(...)`; `retryLimit()` phải được gán vào `retryLimit(...)` khi tạo Step. Kiểm tra positive/cap/overflow của `Duration.toMillis()` và số attempts thực tế bằng integration test.

**Không thay đổi setter của policy bean đang được nhiều chunk threads sử dụng.** Chọn effective config theo run/release, log policy version và tính cộng dồn tải khi rolling deploy khiến old/new workers tạm dùng hai cấu hình retry khác nhau.

## 19. Metrics: biết retry giảm tải hay đang làm tình hình xấu hơn

| Metric gợi ý | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `batch_retry_attempts_total` | attempts | Số lần retry được thực hiện ở layer xác định |
| `batch_retry_exhausted_total` | operations | Operations không còn retry |
| `batch_retry_backoff_calls_total` | calls | Số lần vào backoff |
| `batch_retry_backoff_wait_seconds` | time | Tổng/phân phối thời gian chờ |
| `batch_chunk_commit_seconds` | time | Latency commit chunk |
| `batch_chunk_rollback_total` | chunks | Số rollback |
| `batch_business_unique_commits_total` | items | Goodput, không nhân đôi replay |
| `hikaricp_connections_pending` | threads | Worker đợi JDBC connection |
| `db_lock_wait_seconds` | time | DB contention |
| `broker_redelivery_total` | messages | Broker-level retry, tách khỏi chunk retry |
| `batch_recovery_duration_seconds` | time | RTO từ failure đến xử lý hữu ích |

Tên metric tùy instrumentation/registry, **không mặc định** có sẵn đúng tên trong Spring Batch.

### Đo backoff duration bằng wrapper

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.retry.RetryContext;
import org.springframework.retry.backoff.BackOffContext;
import org.springframework.retry.backoff.BackOffPolicy;

public final class MeasuredBackOffPolicy implements BackOffPolicy {

    private final BackOffPolicy delegate;
    private final Counter calls;
    private final Timer waitTimer;

    public MeasuredBackOffPolicy(
            BackOffPolicy delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.calls = Counter.builder("batch.retry.backoff.calls")
                .tag("dependency", "orders-db")
                .register(registry);
        this.waitTimer = Timer.builder("batch.retry.backoff.wait")
                .tag("dependency", "orders-db")
                .register(registry);
    }

    @Override
    public BackOffContext start(RetryContext context) {
        return delegate.start(context);
    }

    @Override
    public void backOff(BackOffContext context) {
        calls.increment();
        long start = System.nanoTime();
        try {
            delegate.backOff(context);
        } finally {
            waitTimer.record(
                    System.nanoTime() - start,
                    TimeUnit.NANOSECONDS);
        }
    }
}
~~~

**Giới hạn của metric:** wrapper đo *số lần backoff* và thời gian trong callback, không tự đếm mọi business attempt hay kết quả commit. Nếu process chết ngay sau commit, telemetry trong JVM có thể không kịp export; business audit/reconciliation cần nguồn bền vững riêng.

Ví dụ PromQL khi tên counter được exporter chuẩn hóa như minh họa:

~~~promql
sum by (dependency) (
  rate(batch_retry_backoff_calls_total[5m])
)
~~~

Đặt cạnh biểu đồ `batch_business_unique_commits_total`, `hikaricp_connections_pending`, database lock wait và chunk p95. Không dùng `orderId`/`JobExecutionId` trong Prometheus labels vì cardinality tăng theo dữ liệu; đặt ID cụ thể vào structured logs/tracing có kiểm soát.

## 20. SLO và chi phí backoff theo thời gian hoàn tất job

Một job nhập **2,4 triệu items trong 40 phút**:

~~~text
Whole-job required average:
2,400,000 / (40 * 60) = 1,000 unique items/s

Nếu capture + reconciliation mất 5 phút:
processing budget = 35 phút
required processing goodput:
2,400,000 / (35 * 60) ≈ 1,143 unique items/s
~~~

Backoff quá ngắn làm DB khó phục hồi; quá dài giữ worker slots và kéo dài đuôi của job, nhất là một partition liên tục lỗi. Tuning nên tìm **độ ổn định và time-to-recovery**, không chỉ minimize retry wait.

Một SLO minh họa có thể bao gồm: tỷ lệ cửa sổ 5 phút đạt goodput mục tiêu khi còn input, retry exhaustion trong ngưỡng, JDBC pending và p95 commit có giới hạn, RTO sau DB outage ngắn, tổng thời gian job gồm reconciliation và **không có missing/duplicate business effects**.

Ngưỡng chỉ có giá trị khi workload và policy warm-up/steady/drain được công bố trước. Không loại bỏ các cửa sổ xấu sau khi đo chỉ để SLO trông đẹp.

## 21. Ma trận fault injection: retry policy phải được kiểm thử dưới lỗi thật

Một bài test backoff chỉ chứng minh policy gọi đúng delay chưa đủ. Phải thử cả **transaction boundaries, message delivery, nhiều worker và data correctness**.

| Kịch bản | Inject tại đâu | Điều phải đạt |
| --- | --- | --- |
| Deadlock DB thoáng qua | Writer chunk ném lock exception ở lần đầu | Retry hữu hạn, commit hợp lệ, không duplicate |
| DB mất kết nối ngắn | Source/target datasource hoặc proxy | Backoff bounded, connection cleanup đúng, recovery |
| DB mất kết nối kéo dài | Chặn DB vượt tổng retry budget | Exhausted rồi Step FAILED/STOPPED theo policy, không vòng lặp vô hạn |
| HTTP 429 có Retry-After | External client giả | Tuân thủ quota/deadline, không flood API |
| HTTP 401/403 | External client giả | Không retry mù lỗi permission |
| Validation sai chắc chắn | Processor ném lỗi nonretryable | Fail/skip có audit theo business contract |
| Poison record | Một input luôn ném lỗi | Không gây retry storm hoặc bỏ sót âm thầm |
| Jitter trên nhiều workers | Đồng bộ failure bằng barrier | Retry attempts được trải ra, không tất cả cùng nhịp |
| Hikari pool bão hòa | Giảm pool/tăng concurrency trên staging | Backoff không giữ transaction/lock quá lâu, pending được đo |
| Chunk commit rồi mất metadata | Hai resources, inject crash đúng window | Restart replay an toàn theo business key |
| Broker ACK/reply mất | Drop reply sau worker commit | Redelivery không gây double effect |
| Worker network partition | Chặn control plane, giữ đường DB | Không có hai owner ghi không kiểm soát |
| Manager chết giữa partition | Kill manager test | Recovery đúng StepExecution state |
| Partition skew | Một partition có nhiều record khó | Tail completion trong SLA hoặc fail rõ |
| Retry limit tại hai lớp | Bật cả client và Step trong fixture | Đo số attempts nhân lên, sửa policy tránh lặp |
| Rolling deploy | Old/new workers dùng config khác | Tổng retry load vẫn trong DB budget |
| Snapshot hết retention | Reopen reader sau failure | Fail rõ, không đọc source live thay thế |
| Dữ liệu đầu ra thiếu/trùng | Fault inject vào app-owned output | Reconciliation FAIL dù job status COMPLETED |

### Test có kiểm soát thay vì tác động production

- Dùng Testcontainers PostgreSQL hoặc staging database **cô lập** với bản dữ liệu đại diện.
- Chỉ dùng `SELECT` để quan sát bảng `BATCH_*`. Không sửa trực tiếp `VERSION`, `STATUS` hay serialized context để tạo lỗi.
- Dùng `CountDownLatch`/test doubles/transaction proxy để ép các failure windows; không chỉ dựa vào `Thread.sleep`.
- Ghi số attempts theo layer và outcome; tách item retry khỏi broker redelivery.
- Sau recovery, so output theo **unique business key**, payload/version và những side effects ngoài DB.
- Nếu một Step vẫn `STARTED` mồ côi, xử lý qua runbook hợp lệ và xác minh old process đã dừng/fenced trước khi restart.
- Test phải có timeout/cleanup để không làm CI treo khi policy lỗi.

### Test nonretryable là tiêu chí an toàn

Một validation error có thể không bao giờ thành công dù retry 1.000 lần. Với dữ liệu bắt buộc, phải fail rõ để operator sửa input. Đừng chuyển mọi error thành `skip` chỉ để đạt throughput/SLA bề ngoài.

## 22. Benchmark tuning theo một biến và đủ dài

Để chọn `retryLimit`/initial/cap/multiplier/jitter, chạy thử trên workload bất biến và quota thực tế.

### Baseline trước khi sửa policy

1. Chốt snapshot/partition manifest, output target và business constraints.
2. Đo baseline workers, chunk size, reader/processor/writer, transaction manager.
3. Ghi cấu hình DB: max connections, indexes, lock timeout, pool/IO/CPU.
4. Xác nhận metrics: goodput, p95/p99 chunk latency, rollback/retry, Hikari pending, DB wait events.
5. Chạy không injection để biết overhead policy khi không có lỗi.

### Ma trận thông số minh họa

| Phép thử | Attempts budget | Initial backoff | Max interval | Jitter | Khi nào hữu ích |
| --- | ---: | ---: | ---: | --- | --- |
| A – baseline | 3 | 0 ms | 0 ms | Không | Đo rủi ro retry storm; không phải cấu hình khuyến nghị |
| B – fixed | 3 | 500 ms | 500 ms | Không | Lỗi đơn giản, ít workers |
| C – exponential | 4 | 250 ms | 4 s | Không | Thử điều chỉnh tốc độ retry theo lỗi kéo dài |
| D – exponential randomized | 4 | 250 ms | 4 s | Có | Nhiều workers cùng gặp lỗi |
| E – slower recovery | 4 | 1 s | 10 s | Có | Downstream cần hồi phục dài hơn |
| F – fail fast | 1 | Không áp dụng | Không áp dụng | Không | Lỗi nonretryable/transaction không thể replay an toàn |

Các con số chỉ để **thiết kế thí nghiệm**, không phải khuyến nghị trực tiếp. “Attempts budget” ở bảng được định nghĩa là tổng số attempts logic tính cả lần đầu; map sang API thực phải qua test. Với “initial=0”, không sử dụng `ExponentialBackOffPolicy` cấu hình 0 ms nếu phiên bản thư viện không chấp nhận; triển khai no-backoff như một **policy riêng**.

### Đo cả stress và recovery

- Baseline không lỗi.
- Burst errors 5–15 giây, số workers tăng.
- Sustained downstream outage, xác minh exhaustion/fail policy.
- Tình huống DB lock/hot key và long transaction.
- Restart sau commit–checkpoint uncertain window.
- Soak đủ dài để thấy pooling, GC và retry amplification tích lũy.
- Lặp nhiều lần để giảm nhiễu từ cache/IO/noisy neighbor.
- Thay **một biến mỗi lần**: max attempts, initial, cap, multiplier, jitter, worker slots hoặc chunk size; không thay đồng thời cả bộ rồi suy nguyên nhân.

### Chọn cấu hình từ mục tiêu kinh doanh

Nếu SLO của job là 30 phút mà retry mỗi partition có thể chờ 10 phút, tail latency sẽ dễ phá SLA. Nếu lỗi thường tự hết sau 200 ms, initial 30 giây có thể gây downtime không cần thiết. Tính cả **worker slot occupancy**, connection usage, retry load toàn cluster, success rate và business reconciliation để chọn mức cân bằng.

### Không tối ưu “success after retry” một mình

Một policy có thể đạt 99% retry success nhưng giữ hàng nghìn connections/threads rất lâu hoặc làm goodput thấp hơn policy dừng sớm. Cần so time-to-recovery, completed business items/s, job duration và tail percentiles, không chỉ tỷ lệ exception biến mất.

## 23. Runbook khi xuất hiện retry storm trong production

Nếu retry attempts, pool pending và rollback tăng đồng thời:

1. **Khoanh vùng:** JobInstance/JobExecution, affected StepExecutions, snapshot, số workers, phiên bản config.
2. **Phân loại lỗi:** DB lock, connection, API 429/503, validation, broker redelivery, serializer/schema mismatch.
3. **Xác định retry ở tầng nào:** StepBuilder, `RetryTemplate`/HTTP client, broker hay scheduler; kiểm tra có nested retries không.
4. **Đọc metric cùng timeline:** goodput vs attempts, chunk latency, Hikari active/pending, DB lock/IO, broker ready/unacked/DLQ.
5. **Kiểm tra transaction:** retries có giữ JDBC connection/lock không? Business effect có thể đã commit trước lỗi không?
6. **Kiểm tra quota:** số worker JVM × threads, tổng DB pools, external rate limits và retry budget toàn cụm.
7. **Đừng tự tăng worker** khi bottleneck là DB/broker/API đang quá tải; ưu tiên bounded dispatch, backpressure hoặc tạm giảm concurrency.
8. **Không blanket retry lỗi nonretryable:** validation/permission/schema lỗi cần fail rõ và sửa nguyên nhân.
9. **Nếu downstream ngừng phục vụ kéo dài**, cân nhắc fail/stop theo policy thay vì giữ mọi worker sleep vô hạn.
10. **Xác minh ownership** nếu có remote partitions bị timeout; chỉ redispatch sau khi worker cũ được cô lập/fenced.
11. **Kiểm tra input và checkpoint** nếu cần restart; không đổi snapshot/range hoặc tự sửa `BATCH_*`.
12. **Đối soát output và side effects** sau khi áp backoff policy mới; không chỉ nhìn exceptions giảm.
13. **Benchmark/canary** policy mới trên cùng workload đại diện, quan sát recovery đủ dài.
14. **Ghi root cause và cập nhật test** cho đúng loại lỗi, failure window và config đã gây incident.

### Những việc không nên làm

- Cứ gặp `SQLException` là retry vô hạn, không xét SQLSTATE và transaction state.
- Tăng `retryLimit` từ 3 lên 50 khi DB đã deadlock/connection-starved.
- Bật `@Retryable` ở client đồng thời bật retry chunk rồi quên budget nhân.
- Tạo identifying `run.id` mới để né `JobExecutionAlreadyRunningException` mà không kế hoạch reprocess.
- Xóa broker DLQ/StepExecutionContext để dashboard không còn backlog.
- Bật `noRollback` cho lỗi DB nghiêm trọng để tránh rollback overhead.
- Dùng key idempotency mới cho mỗi attempt của cùng payment.
- Tăng `ThreadPoolTaskExecutor` để bù các threads đang ngủ backoff khi DB đã hết quota.

### Phân biệt tín hiệu tích cực và tiêu cực

Nếu backoff/jitter giúp lock wait giảm, fewer retries exhausted, **goodput tăng** và SLO recovery đạt, đó là thay đổi có ích. Nếu attempts giảm chỉ vì mỗi worker đang ngủ lâu hơn trong khi backlog tăng và job quá SLA, cần xem xét lại policy hoặc sửa bottleneck.

## 24. Bài tập tình huống: 32 workers gặp lock storm

Một job Spring Batch xử lý snapshot bất biến **6 triệu orders**, chia 64 partitions, chạy trên 8 JVM × 4 worker slots. Writer idempotent theo `(snapshotId, orderId)`; repository và business DB có hai transaction managers riêng.

Lúc 02:00, một transaction khác giữ row lock lâu. Cả 32 partitions đang active gặp `CannotAcquireLockException` gần như đồng thời. Đội phát triển đề xuất:

~~~text
Policy P1:
  retries không có backoff
  tối đa 4 total attempts
  32 concurrent workers

Policy P2:
  initial delay=250ms
  multiplier=2
  max delay=4s
  randomized=true
  tối đa 4 total attempts

Broker:
  redelivery 3 lần nếu reply mất

HTTP client trong ItemProcessor:
  riêng nó cũng retry tối đa 4 attempts
~~~

**Câu hỏi:**

1. Trong mô hình bốn attempts/partition, 32 partitions có thể tạo tổng tối đa bao nhiêu writer attempts chỉ ở một vòng chunk retry?
2. Có bao nhiêu retry attempts bổ sung so với lần đầu?
3. Với ba delays 250/500/1000 ms (không jitter), tổng thời gian chờ trước attempt cuối là bao nhiêu?
4. Tại sao P1 dễ gây thundering herd hơn P2?
5. `max delay=4s` có đồng nghĩa tổng retry không bao giờ quá 4 giây không?
6. Khi broker redeliver ba lần và HTTP client retry riêng, có thể xảy ra dạng amplification nào?
7. Nếu 32 worker threads đang ngủ backoff, CPU thấp có nghĩa hệ còn capacity xử lý không?
8. `connectionTimeout` của HikariCP tăng có chữa được lock contention không?
9. Nếu worker commit DB rồi mất reply trước checkpoint, có thể retry bằng key nào và phải kiểm tra gì?
10. Nếu record invalid schema, nên tăng retry limit hay fail/skip có kiểm soát?
11. Nếu một partition đợi retry quá lâu, hệ quả lên job end-to-end là gì?
12. Nêu năm metric cần đặt cạnh nhau khi đánh giá P2.
13. Sau triển khai P2, số exceptions giảm 80% nhưng backlog tăng, goodput giảm. Có được coi đã tuning thành công không?
14. Chỉ ra ba phép fault injection để xác minh policy ở môi trường test.

### Gợi ý đáp án

- **(1)** `32 × 4 = 128` total attempts trong mô hình một operation mỗi partition.
- **(2)** `32 × (4−1) = 96` retry attempts bổ sung.
- **(3)** `250+500+1000 = 1.750 ms`, chưa tính DB/rollback/metadata và jitter.
- **(4)** P1 phát lại đồng thời; P2 dãn và random hóa attempts, giảm xung đồng bộ.
- **(5)** Không. `maxInterval` là cap của **mỗi khoảng chờ**, không phải total elapsed retry.
- **(6)** Nested retries có thể nhân số downstream calls; phải đo thực tế và đặt ngân sách ở layer sở hữu.
- **(7)** Không. Threads có thể đang bị giữ bởi sleep hoặc JDBC wait, worker slots không làm việc hữu ích.
- **(8)** Không. Nó làm threads đợi connection lâu hơn, không giải phóng DB locks.
- **(9)** Dùng key ổn định theo snapshot/business operation, state từ repository/ledger, source–target reconciliation và owner hợp lệ.
- **(10)** Validation không tự hết nhờ retry; fail rõ hoặc skip chỉ nếu business policy cho phép và audit.
- **(11)** Straggler kéo dài critical path và có thể phá SLA toàn JobInstance.
- **(12)** Goodput, retry attempts/exhausted, Hikari pending/acquisition p95, DB locks, chunk latency p95; thêm broker DLQ/RTO.
- **(13)** Không. Giảm exceptions trong khi useful progress giảm và backlog tăng không đạt mục tiêu.
- **(14)** DB deadlock transient rồi hồi, outage kéo dài để exhaustion, lost reply sau writer commit để kiểm tra idempotency.

## 25. Checklist trước production

- [ ] Retryable exceptions được phân loại **cụ thể**, không blanket `Exception`/`SQLException`.
- [ ] Phân biệt retry, skip, fail fast và restart theo business contract.
- [ ] Có `retryLimit` hữu hạn và kiểm thử số attempts thật của Spring Batch step.
- [ ] Chọn fixed/exponential/randomized phù hợp với resource và số workers.
- [ ] Initial delay, multiplier và max interval có bound, không tràn số.
- [ ] Tổng elapsed retry time không vượt SLA/job deadline mà không có policy dừng.
- [ ] Đã tính retry budget toàn cluster và nested retry amplification.
- [ ] Có jitter hoặc phân tán retries khi nhiều workers cùng gặp lỗi shared DB/API.
- [ ] Có bounded executor/DB pool, admission/backpressure/circuit breaker khi cần.
- [ ] Đã kiểm tra thread/backoff có giữ JDBC connection/lock trong transaction không.
- [ ] Reader/writer thread-safe theo mô hình concurrency; checkpoint/restart đã test.
- [ ] Idempotency key ổn định qua retry, restart và message redelivery.
- [ ] External side effects có ledger/outbox/fencing khi cần; không đồng nhất UPSERT với exactly-once toàn hệ.
- [ ] Snapshot, partition mapping và reader ordering giữ nguyên khi resume JobInstance.
- [ ] Broker retry/DLQ tách khỏi chunk retry và có correlation/ACK policy.
- [ ] HTTP 429/503/Retry-After có deadline, quota, rate limiter và policy riêng.
- [ ] Config ứng dụng được bind/validate; không mutate policy shared bean đang chạy.
- [ ] Metrics phân biệt attempts, exhausted, backoff wait, rollback và unique commits.
- [ ] Đã chạy test pure policy không sleep và integration test với JDBC JobRepository.
- [ ] Đã fault-inject DB outage, lock, worker crash, lost reply và rolling deploy.
- [ ] Tuning đánh giá sustained goodput, RTO, chunk p95 và dữ liệu đúng; không chỉ exception rate.
- [ ] Có runbook xử lý retry storm, orphan executions, DLQ và rollback/recovery.

## 26. Tài liệu tham khảo

- [Spring Batch Reference – Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry exception và retry limit trong fault-tolerant step.
- [Spring Batch Reference – Configuring Skip](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): retry vs skip và `skipLimit`.
- [Spring Batch Reference – Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html): rollback semantics cho fault-tolerant processing.
- [Spring Batch Reference – Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk/commit/transaction boundary.
- [Spring Batch Reference – Transaction Attributes](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/transaction-attributes.html): transaction timeout/isolation config.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning, distributed processing.
- [Spring Batch Reference – Job Restart](https://docs.spring.io/spring-batch/reference/job.html): JobInstance/JobExecution, restart semantics.
- [Spring Batch Reference – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint open/update/close.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): Batch observability.
- [Spring Retry repository](https://github.com/spring-projects/spring-retry): `RetryTemplate`, `BackOffPolicy` và policy implementations.
- [Spring Retry API – ExponentialBackOffPolicy](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/backoff/ExponentialBackOffPolicy.html): initial interval, multiplier và cap.
- [Spring Retry API – ExponentialRandomBackOffPolicy](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/backoff/ExponentialRandomBackOffPolicy.html): randomized exponential policy.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction, rollback và resource lifecycle.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `@ConfigurationProperties` và binding.
- [Micrometer – Instrument Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): `Counter`/`Timer`.
- [Prometheus – Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase` và time windows.
- [PostgreSQL – Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE classes để phân loại lỗi DB.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): deadlock/serialization/transaction semantics.

## Ghi nhớ

**Điều chỉnh retry backoff là kiểm soát thời điểm, số lần và tổng tải của những thao tác có khả năng phục hồi — không phải che lỗi bằng cách thử đi thử lại vô hạn.** Với Spring Batch, dùng `retry(...)`/`retryLimit(...)` và một `BackOffPolicy` có cap, cân nhắc jitter khi nhiều workers cùng truy cập DB/API. Phân biệt chunk retry với broker redelivery, partition redispatch và whole-job restart; **các attempts có thể bị nhân lên nếu nhiều layer retry chồng nhau**. Đo retry calls/exhaustion, JDBC/DB contention, chunk latency cùng **goodput nghiệp vụ**; kiểm thử transaction rollback, crash/restart và side effect chưa chắc đã commit bằng idempotency. **Một cấu hình tốt giúp hệ thống hồi phục ổn định và đúng dữ liệu trong SLA, không chỉ làm số exception trên dashboard giảm.**
