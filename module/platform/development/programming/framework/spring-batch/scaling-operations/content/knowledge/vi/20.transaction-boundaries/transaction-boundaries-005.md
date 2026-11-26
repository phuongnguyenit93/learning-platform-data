# Commit độc lập và tính nhất quán

Khi mở rộng Spring Batch bằng **multi-threaded step, parallel steps, partitioning hoặc worker phân tán**, nhiều đơn vị xử lý có thể mở **transaction riêng** và commit tại các thời điểm khác nhau. Một worker có thể đã ghi thành công 10.000 bản ghi trong khi worker khác bị lỗi sau 200 bản ghi. Khi đó job có thể kết thúc ở trạng thái `FAILED`, nhưng những transaction đã commit trước đó **không tự bị rollback**. Đây chính là ý nghĩa thực tiễn của **commit độc lập** và là lý do thiết kế **tính nhất quán (consistency)** phải đi xa hơn việc đặt `@Transactional` lên một phương thức Java.

Bài học thuộc chương **Transaction boundary** trong module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và mô hình phân tán; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo nguồn lực thực tế. Ở đây, chúng ta tập trung vào **ranh giới commit thực sự**, hậu quả của **partial success**, cách bảo đảm **không trùng/không thiếu** và những mô hình giúp chỉ công bố dữ liệu khi toàn bộ batch đã đạt điều kiện nghiệp vụ.

**Nguyên tắc quan trọng nhất:** một `JobExecution` là đơn vị điều phối và theo dõi trạng thái; nó **không mặc định là một transaction ACID bao trùm tất cả worker, chunk, database và message broker**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt ranh giới transaction của **chunk**, **worker StepExecution**, **manager step**, **JobRepository** và các hệ thống bên ngoài.
2. Giải thích tại sao **một chunk/partition đã commit không tự rollback** khi partition khác thất bại.
3. Hiểu những cấp độ tính nhất quán: **không ghi trùng**, **đúng snapshot**, **đúng tổng**, **hiển thị nguyên batch** và **hiệu ứng xuyên hệ thống**.
4. Thiết kế partition không giao nhau và writer **idempotent** để retry/restart an toàn.
5. Xác định những bất thường khi nhiều worker đọc/ghi đồng thời: **read skew, phantom, lost update, write conflict, deadlock**.
6. Áp dụng mô hình **staging + validation + publish barrier** khi người tiêu thụ chỉ được nhìn thấy batch hoàn chỉnh.
7. Sử dụng **transactional outbox** hoặc idempotency key khi worker còn gửi message/gọi API ngoài DB transaction.
8. Xây kiểm thử có lỗi chủ đích giữa các commit, ngắt worker sau DB commit nhưng trước phản hồi và đối soát dữ liệu.
9. Đo commit latency, rollback count, lock contention, tiến độ từng partition và điều kiện công bố kết quả.

**Tình huống xuyên suốt:** một job chuẩn hóa 1.000.000 giao dịch cuối ngày, chia thành bốn partition P0–P3. Mỗi partition đọc một vùng nguồn không chồng lấn, xử lý theo chunk 200 item và ghi vào PostgreSQL. P0, P1, P2 đã commit dữ liệu; P3 bị lỗi DB sau nhiều chunk. Nếu bảng kết quả được downstream đọc trực tiếp ngay trong lúc job chạy, người dùng có thể nhìn thấy **kết quả chưa đầy đủ**. Hệ thống cần khôi phục P3 an toàn và bảo đảm downstream chỉ công bố batch khi tất cả partition đã hoàn tất và đối soát đạt.

## 2. Ranh giới commit là gì?

**Transaction boundary** xác định những thao tác thuộc **cùng một giao dịch** và vì thế có thể **commit hoặc rollback cùng nhau** theo transaction manager được dùng.

Trong Spring Batch chunk-oriented processing, một chunk thường có dạng:

~~~text
BEGIN transaction
  Đọc một nhóm item (kèm cơ chế checkpoint phù hợp)
  Process từng item
  Write kết quả của chunk
  Cập nhật trạng thái liên quan theo cơ chế framework
COMMIT transaction
~~~

Đây là **sơ đồ khái niệm**. Thứ tự chính xác, phạm vi trạng thái reader và metadata, cũng như transaction của JobRepository còn phụ thuộc reader, `PlatformTransactionManager`, resource và cấu hình Spring Batch. Không mặc định dữ liệu nghiệp vụ và mọi bảng metadata được commit nguyên tử nếu chúng sử dụng **hai transaction manager hoặc hai database độc lập**.

### Ba mức phạm vi phải tách biệt

| Phạm vi | Điều có thể được commit cùng nhau | Điều không tự động tham gia |
| --- | --- | --- |
| **Một chunk** | Các thao tác DB cùng resource/transaction manager của chunk | Chunk khác, partition khác, API ngoài |
| **Một worker StepExecution** | Nhiều chunk lần lượt commit, mỗi chunk có trạng thái riêng | Không có một transaction duy nhất bao trùm toàn step |
| **Một JobExecution** | Tổng hợp trạng thái các step và luồng điều phối | Không có global rollback cho mọi chunk đã commit |

Ví dụ `chunk(200)` với 1.000 item hợp lệ thường tạo khoảng **năm transaction xử lý dữ liệu thành công** trong mô hình đơn giản. Nếu lỗi ở chunk 5 sau khi chunk 1–4 đã commit, rollback của chunk 5 **không quay ngược bốn commit trước đó**.

**`@Transactional` không biến nhiều worker/JVM thành một transaction chung.** Spring transaction thông thường gắn với transaction manager và tài nguyên trong ngữ cảnh thực thi của nó; nó không tự lan qua message broker, sang tiến trình khác hoặc bao phủ cả JobExecution.

## 3. Commit diễn ra như thế nào khi chia partition?

~~~mermaid
flowchart TD
    J["JobExecution"] --> M["Manager Step"]
    M --> P["Partitioner + PartitionHandler"]
    P --> A["Worker P0"]
    P --> B["Worker P1"]
    P --> C["Worker P2"]
    A --> A1["chunk A1: COMMIT"]
    A --> A2["chunk A2: COMMIT"]
    B --> B1["chunk B1: COMMIT"]
    B --> B2["chunk B2: ROLLBACK"]
    C --> C1["chunk C1: COMMIT"]
    A1 --> DB[("Business DB")]
    A2 --> DB
    B1 --> DB
    C1 --> DB
    B2 -. "Không hoàn tác commit khác" .-> DB
    P --> R["JobRepository: trạng thái worker"]
~~~

Mỗi worker xử lý tập dữ liệu được giao và thường có **transaction riêng cho mỗi chunk**. `PartitionHandler` điều phối và tổng hợp kết quả, không đóng vai trò một transaction coordinator kiểu two-phase commit cho mọi chunk.

### Dòng thời gian với một partition bị lỗi

~~~text
T0  Manager tạo P0, P1, P2, P3 từ snapshot cố định
T1  P0 chunk 1 COMMIT      P1 chunk 1 COMMIT
T2  P2 chunk 1 COMMIT      P3 chunk 1 COMMIT
T3  P0 chunk 2 COMMIT      P3 chunk 2 COMMIT
T4  P1 chunk 2 COMMIT      P3 chunk 3 ROLLBACK (DB timeout)
T5  P0/P1/P2 đã COMPLETED; P3 FAILED
T6  Manager/job phản ánh trạng thái thất bại theo flow

Kết quả ở business DB: các chunk commit trước T4 vẫn tồn tại.
~~~

Trong test, không nên suy ra một job `FAILED` đồng nghĩa output DB rỗng. Ngược lại, cũng không được coi những partition đã `COMPLETED` là bằng chứng toàn bộ batch đã sẵn sàng công bố.

## 4. Các mô hình mở rộng có ranh giới khác nhau

| Mô hình | Đơn vị làm việc đồng thời | Ranh giới commit cần chú ý | Rủi ro |
| --- | --- | --- | --- |
| **Multi-threaded step** | Nhiều chunk trong cùng StepExecution | Các chunk có thể chạy/commit trên các thread khác nhau | Reader/writer không thread-safe; giả định thứ tự commit |
| **Parallel steps** | Nhiều step trong các flow độc lập | Mỗi step/chunk dùng transaction riêng | Flow A xong, flow B lỗi; dữ liệu A vẫn tồn tại |
| **Local partitioning** | Nhiều worker StepExecution trong cùng JVM | Chunk của từng worker commit độc lập | Partial success, tranh lock/index, restart |
| **Remote partitioning** | Worker step ở các process/node khác nhau | Transaction của từng worker ở nguồn/tài nguyên truy cập được | Mất node, reply muộn, checkpoint khác JVM |
| **Remote chunking** | Manager gửi chunk; worker xử lý/ghi | Commit worker độc lập với request/reply, broker ACK và manager metadata | Worker đã commit nhưng reply mất, chunk bị giao lại |

Đối với remote chunking, manager thường giữ `ItemReader`, còn worker nhận item qua `ChunkRequest` để process/write rồi gửi `ChunkResponse`. Đối với remote partitioning, worker thường tự đọc phần dữ liệu được mô tả bởi `ExecutionContext`. **Không gộp hai mô hình** khi thiết kế ranh giới commit và khả năng restart.

## 5. “Nhất quán” cần được định nghĩa cụ thể

Từ “nhất quán” không có nghĩa duy nhất. Hãy viết rõ điều kiện trước khi chọn giải pháp.

| Mục tiêu | Câu hỏi cần trả lời | Công cụ thường dùng |
| --- | --- | --- |
| **Không trùng bản ghi** | Một business key có được tạo hai kết quả khi replay không? | Unique constraint, idempotency key |
| **Không thiếu bản ghi** | Mọi record kỳ vọng đều có output hoặc lý do skip được phê duyệt? | Snapshot + đối soát |
| **Đúng giá trị** | Tổng tiền và từng dòng có khớp quy tắc nghiệp vụ? | Deterministic processing, checksums, validation |
| **Cùng một snapshot** | Các worker có đọc cùng phiên bản nguồn không? | Staging immutable, snapshot/version/cutoff |
| **Không lộ dữ liệu chưa hoàn tất** | Downstream có thấy nửa batch khi một partition còn chạy? | Staging + publish barrier |
| **Thứ tự nghiệp vụ** | Các sự kiện cùng tài khoản có được áp dụng đúng thứ tự? | Partition theo business key, serialize theo khóa |
| **Hiệu ứng ngoài DB không lặp** | Email, thanh toán, event có bị phát lại? | Outbox, dedup/idempotency tại consumer |

Một thiết kế có thể thỏa **không trùng dòng** nhưng vẫn **thiếu dòng**. Nó có thể ghi đủ dòng nhưng **sai giá trị** khi processor dùng tỷ giá biến đổi giữa các lần retry. Nó cũng có thể đúng dữ liệu ở trạng thái cuối cùng nhưng khiến báo cáo đọc phải **tập kết quả chưa đầy đủ** khi job đang chạy.

Vì thế, điều kiện `BatchStatus.COMPLETED` là **tín hiệu điều phối**, không thay thế toàn bộ bằng chứng về nhất quán nghiệp vụ.

## 6. Snapshot nguồn: mỗi worker phải xử lý cùng một tập dữ liệu logic

Giả sử dữ liệu được đọc từ bảng `orders` đang nhận insert/update liên tục. Nếu P0 đọc lúc 09:00, P1 lúc 09:03, P2 lúc 09:08, điều kiện `status = 'READY'` có thể cho kết quả khác nhau do hàng đã thay trạng thái hoặc được chèn thêm. Ranh giới partition không chồng lấn theo ID **chưa đủ** nếu bản thân **tập nguồn thay đổi**.

Một hợp đồng đầu vào an toàn thường có:

1. **`batchKey`/snapshotId** xác định tập dữ liệu của job.
2. **Danh sách record hoặc cutoff đã được chốt**; tiêu chí cutoff chỉ đủ khi nguồn tuân thủ hợp đồng bất biến/version tương ứng.
3. **Partition mapping ổn định** qua restart: `partition0` vẫn mang cùng vùng/key.
4. **Giá trị tham chiếu/rule version** được chốt nếu ảnh hưởng kết quả (tỷ giá, chính sách phí, mapping vùng).
5. **Không thay đổi dữ liệu staging** khi worker đã bắt đầu.

Ví dụ PostgreSQL về một **bảng staging bất biến theo batch**:

~~~sql
CREATE TABLE staged_order (
    batch_key       VARCHAR(100) NOT NULL,
    order_id        BIGINT NOT NULL,
    customer_id     BIGINT NOT NULL,
    gross_total     NUMERIC(18, 2) NOT NULL,
    partition_no    INTEGER NOT NULL,
    PRIMARY KEY (batch_key, order_id)
);

CREATE INDEX idx_staged_order_partition
    ON staged_order (batch_key, partition_no, order_id);
~~~

Trước khi chạy manager, một bước chuẩn bị tạo dữ liệu staging từ một **snapshot/cutoff đã xác định và kiểm chứng**. Worker chỉ đọc `WHERE batch_key = :batchKey AND partition_no = :partitionNo`. `partition_no` phải được tính một lần và lưu bền vững, thay vì mỗi lần restart băm lại với số partition khác.

### Vì sao chỉ “đọc trong REPEATABLE_READ” chưa đủ?

Transaction isolation như `REPEATABLE READ` giúp **một transaction** có cách nhìn nhất quán trong phạm vi DB tùy hệ quản trị. Nhưng bốn worker có bốn transaction khác nhau, khởi đầu tại thời điểm khác nhau, **không mặc định chia sẻ một snapshot toàn job**. Snapshot database xuất/nhập được giữa các session là một cơ chế chuyên biệt với nhiều điều kiện vận hành; không suy ra nó xuất hiện chỉ từ annotation `@Transactional(isolation=...)`.

Staging bất biến hoặc snapshot/version có thể đọc lại an toàn thường dễ vận hành hơn trong batch dài hàng giờ.

## 7. Hiện tượng đồng thời khi nhiều worker commit độc lập

| Hiện tượng | Ví dụ | Hậu quả | Biện pháp |
| --- | --- | --- | --- |
| **Dirty read** | Reader thấy dữ liệu transaction chưa commit ở mức isolation yếu | Đọc dữ liệu có thể rollback | Dùng isolation phù hợp, không đọc uncommitted |
| **Non-repeatable read** | Cùng record bị update giữa hai lượt đọc | Giá trị thay đổi | Snapshot/staging hoặc lock/version |
| **Phantom** | Query lần sau thấy thêm hàng phù hợp predicate | Đếm/coverage khác đi | Snapshot cố định, kiểm chứng source |
| **Lost update** | Hai worker ghi cùng counter/tài khoản từ bản giá trị cũ | Mất một thay đổi | Atomic UPDATE, optimistic locking, phân vùng theo owner |
| **Write conflict** | Hai partition cùng ghi cùng business key | Unique violation, deadlock hoặc overwrite | Non-overlap, constraint, idempotency |
| **Read skew** | P0 đọc tỷ giá version 1, P1 version 2 | Tổng báo cáo trộn nhiều version | Chốt rule/reference data theo batch |
| **Deadlock** | Worker A khóa X rồi Y, B khóa Y rồi X | Một transaction bị rollback | Thứ tự khóa ổn định, transaction ngắn, retry có giới hạn |

**Isolation level của database không thay thế thuật toán phân vùng đúng.** Nếu hai worker đều được giao cùng một record, tăng isolation có thể khiến một worker chờ hoặc lỗi, nhưng không tự sửa được kế hoạch phân chia. Ngược lại, partition không chồng lấn theo ID vẫn có thể cùng cập nhật một **row tổng hợp** và gây contention.

### Một câu SQL dễ tạo lost update

~~~text
Worker A đọc balance = 100
Worker B đọc balance = 100
Worker A ghi balance = 110
Worker B ghi balance = 120
Kết quả = 120; cộng thêm 10 của A bị mất
~~~

Nếu nghiệp vụ thực sự cần cộng dồn trong DB:

~~~sql
UPDATE account_balance
SET balance = balance + :delta
WHERE tenant_id = :tenantId
  AND account_id = :accountId;
~~~

`UPDATE` nguyên tử theo hàng giúp tránh **lost update** của phép cộng trong nhiều hệ DB, nhưng **không idempotent khi retry**: cùng `delta` được áp dụng lại sẽ cộng tiền hai lần. Phải kết hợp **operation ID + dedup transaction** hoặc tạo **aggregate từ staging** rồi ghi một kết quả quyết định.

## 8. Mỗi partition có thể hoàn thành ở thời điểm khác nhau

Giả sử manager tạo bốn partition, mỗi worker xử lý nhiều chunk:

| Thời điểm | P0 | P1 | P2 | P3 | Nhìn từ business DB |
| --- | --- | --- | --- | --- | --- |
| T1 | chunk 1 commit | chunk 1 commit | đang đọc | đang đọc | Kết quả từng phần đã xuất hiện |
| T2 | COMPLETED | chunk 2 commit | chunk 1 commit | chunk 1 commit | Vẫn chưa đủ cả batch |
| T3 | COMPLETED | COMPLETED | COMPLETED | chunk 2 lỗi | Ba vùng đủ, một vùng thiếu |
| T4 | COMPLETED | COMPLETED | COMPLETED | FAILED | Job có thể FAILED, dữ liệu từng phần vẫn có |
| T5 restart | giữ kết quả | giữ kết quả | giữ kết quả | xử lý lại an toàn | Dữ liệu tiến tới đầy đủ |

Hai nhận xét:

- **Hoàn thành không đồng bộ:** trạng thái StepExecution của các worker không phải một điểm commit thống nhất.
- **Hiển thị dữ liệu:** nếu downstream truy vấn bảng kết quả thẳng trong T1–T4, họ có thể đọc được một tập **không phải toàn bộ batch**, dù các transaction riêng lẻ đều ACID.

Khi nghiệp vụ yêu cầu **chỉ thấy tất cả hoặc không thấy gì**, cần một lớp **công bố kết quả** chứ không dựa vào transaction chunk.

## 9. Cách đơn giản: writer idempotent theo business key

Writer phải chịu được việc một chunk bị xử lý lại sau rollback, worker crash hoặc manager không nhận phản hồi. Với PostgreSQL:

~~~sql
CREATE TABLE normalized_order_staging (
    batch_key    VARCHAR(100) NOT NULL,
    order_id     BIGINT NOT NULL,
    partition_no INTEGER NOT NULL,
    net_total    NUMERIC(18, 2) NOT NULL,
    source_hash  VARCHAR(128) NOT NULL,
    PRIMARY KEY (batch_key, order_id)
);
~~~

Một kiểu ghi idempotent khi **input và quy tắc xử lý bất biến**:

~~~sql
INSERT INTO normalized_order_staging (
    batch_key, order_id, partition_no, net_total, source_hash)
VALUES (
    :batchKey, :orderId, :partitionNo, :netTotal, :sourceHash)
ON CONFLICT (batch_key, order_id)
DO UPDATE SET
    net_total = EXCLUDED.net_total,
    source_hash = EXCLUDED.source_hash,
    partition_no = EXCLUDED.partition_no;
~~~

Khóa `(batch_key, order_id)` làm cho một record có **tối đa một dòng kết quả** trong batch. Tuy nhiên, câu `DO UPDATE` có thể **che giấu lỗi** khi cùng record được hai worker gán sang partition khác hoặc phép tính thay đổi. Trong môi trường cần phát hiện sai lệch, sử dụng chính sách **so sánh và từ chối khi nội dung khác**.

### Một phương án nghiêm ngặt hơn: không âm thầm overwrite

~~~sql
INSERT INTO normalized_order_staging (
    batch_key, order_id, partition_no, net_total, source_hash)
VALUES (
    :batchKey, :orderId, :partitionNo, :netTotal, :sourceHash)
ON CONFLICT (batch_key, order_id) DO NOTHING;
~~~

Sau đó **đối chiếu** giá trị bản ghi đã tồn tại với `net_total`, `partition_no`, `source_hash` kỳ vọng. `DO NOTHING` **chỉ bỏ qua duplicate insert**; một mình nó cũng có thể che giấu conflict nội dung nếu không làm bước đối chiếu. Với nhiều writer đồng thời, thực hiện dedup và validation trong transaction/statement được thiết kế chống race; không dùng quy trình “SELECT rồi INSERT” không khóa phù hợp.

### Những điều không được dùng làm idempotency key duy nhất

- `StepExecutionId`: có thể khác khi job restart; một StepExecution chứa nhiều item.
- `ChunkRequest.sequence`: một business item có thể được gửi lại ở chunk khác.
- `brokerMessageId`: publish lại có thể có ID mới.
- `threadName`, `partitionIndex` hoặc vị trí dòng không ổn định: không định danh một tác động nghiệp vụ xuyên các lần chạy.

Chọn khóa theo **logical operation** thực sự, ví dụ `(batchKey, transactionId, operationType)` cho các side effect khác nhau.

## 10. Spring Batch 5.x: worker chunk với transaction manager rõ ràng

Một worker step trong partitioning thường cấu hình `StepBuilder`, `chunk(size, transactionManager)`, reader theo `@StepScope`, processor stateless và writer có kiểm soát ghi trùng.

Ví dụ Java 17+/Spring Batch 5.x cho nguồn staging ở phần 6:

~~~java
record OrderInput(long orderId, BigDecimal grossTotal) {}
record OrderOutput(long orderId, BigDecimal netTotal) {}

@Bean
@StepScope
JdbcPagingItemReader<OrderInput> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['partitionNo']}") Integer partitionNo) {

    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("SELECT order_id, gross_total")
            .fromClause("FROM staged_order")
            .whereClause("""
                    WHERE batch_key = :batchKey
                      AND partition_no = :partitionNo
                    """)
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .parameterValues(Map.of(
                    "batchKey", batchKey,
                    "partitionNo", partitionNo))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getLong("order_id"),
                    rs.getBigDecimal("gross_total")))
            .pageSize(200)
            .saveState(true)
            .build();
}

@Bean
ItemProcessor<OrderInput, OrderOutput> normalizeOrder() {
    return item -> {
        if (item.grossTotal() == null
                || item.grossTotal().signum() < 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
        return new OrderOutput(
                item.orderId(),
                item.grossTotal().setScale(2, RoundingMode.HALF_UP));
    };
}

@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, OrderOutput> normalizeOrder,
        ItemWriter<OrderOutput> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(
                    200, businessTransactionManager)
            .reader(orderReader)
            .processor(normalizeOrder)
            .writer(orderWriter)
            .build();
}
~~~

`orderWriter` là một bean cần được triển khai riêng bằng SQL idempotent và có `batchKey`/`partitionNo` ở scope phù hợp. Ví dụ trên không tự tạo bảng, datasource, JobRepository hoặc manifest; nó tập trung vào **cách truyền transaction manager tại ranh giới chunk**.

**Chú ý về wiring:** mỗi worker StepExecution có reader riêng nhờ `@StepScope`, nhưng processor/writer singleton vẫn có thể được gọi đồng thời ở nhiều worker. Stateless processor là một điểm khởi đầu tốt; writer dùng chung phải thread-safe hoặc được scope/thiết kế theo yêu cầu. Không bật thêm multi-threaded step bên trong worker stateful reader nếu chưa kiểm thử riêng.

### Transaction manager nào đang thực sự quản lý write?

Nếu writer dùng JDBC datasource A nhưng `businessTransactionManager` chỉ quản lý datasource B, commit/rollback của chunk **có thể không bao trùm write vào A**. Kiểm tra:

1. Datasource/transaction manager của reader, writer, business SQL.
2. Việc writer tham gia transaction hiện hành thông qua Spring-managed connections.
3. Resource khác (JPA, JMS, HTTP, Kafka) có tham gia transaction hay không.
4. JobRepository sử dụng DB và transaction manager nào; metadata có atomic với business write không.

**Không đánh giá tính nguyên tử chỉ từ annotation hoặc tên bean.** Hãy inject lỗi sau write nhưng trước commit và xác minh dữ liệu thật trong DB để biết rollback có đúng phạm vi dự kiến.

## 11. Chế độ lỗi: transaction lỗi nhưng các commit trước vẫn tồn tại

Xét worker xử lý chunk 200 item:

~~~text
chunk 1: 200 item -> COMMIT
chunk 2: 200 item -> COMMIT
chunk 3: 200 item -> ROLLBACK do deadlock
step:   retry chunk 3 nếu chính sách cho phép
~~~

**Retry tại chunk** có thể đọc hoặc xử lý lại item, tùy reader, checkpoint, cache và transaction. Không suy ra processor chỉ được gọi một lần. **Reader state** cần tương thích với dữ liệu nguồn bất biến; nếu nguồn đổi thứ tự, checkpoint có thể trỏ đến record khác.

| Loại lỗi | Ví dụ | Hướng xử lý phù hợp |
| --- | --- | --- |
| **Transient** | DB deadlock, timeout tạm thời | Retry giới hạn và backoff, kiểm tra transaction rollback |
| **Permanent data** | Dòng thiếu khóa, vi phạm schema | Skip theo hợp đồng hoặc fail; lưu lý do và đối soát |
| **Consistency violation** | Hai partition ghi cùng order với giá trị khác | **Fail/alert**, không retry vô hạn để ghi đè |
| **Infrastructure failure** | Worker/JVM bị kill | Restart theo JobRepository + snapshot, writer replay-safe |
| **Ambiguous outcome** | Mất kết nối sau khi DB có thể đã commit | Kiểm tra idempotency, đối soát, không đánh dấu chưa ghi một cách mù quáng |

**Không dùng `skip(Exception.class)` vô điều kiện**: có thể bỏ qua cả lỗi kết nối hoặc lỗi vi phạm bất biến và làm job báo thành công với dữ liệu thiếu. `retryLimit`, `skipLimit` và classifier phải gắn với nghiệp vụ.

## 12. Độc lập commit không đồng nghĩa tất cả dữ liệu sẵn sàng công bố

Nhiều hệ thống cần đọc kết quả ngay sau mỗi chunk; đây là **incremental visibility** và có thể phù hợp nếu downstream được thiết kế hiểu trạng thái `PROCESSING`.

Nhưng với báo cáo tài chính hay chốt sổ, downstream có thể yêu cầu **batch-complete visibility**: hoặc thấy toàn bộ kết quả hợp lệ của batch, hoặc không thấy dữ liệu batch đó.

**Đừng cố tạo một transaction duy nhất kéo dài vài giờ qua mọi worker.** Transaction rất dài giữ nhiều lock/version, làm DB khó phục vụ workload khác và vẫn không bao phủ broker/API bên ngoài nếu không có giao dịch phân tán.

Thiết kế thường hiệu quả hơn:

~~~mermaid
flowchart TD
    IN["Input snapshot đã chốt"] --> P["Các worker partition"]
    P --> S[("Staging results: commit theo chunk")]
    S --> V{"Đủ partition + đối soát OK?"}
    V -- "Chưa" --> HOLD["Không công bố batch"]
    V -- "Có" --> PUB["Publish barrier transaction"]
    PUB --> LIVE["Downstream chỉ thấy batch PUBLISHED"]
~~~

Mỗi worker vẫn commit độc lập vào staging. **Điểm công bố** chỉ quyết định lúc nào downstream nhìn thấy cả batch theo một hợp đồng đọc cụ thể.

## 13. Mẫu staging + validation + publish barrier

Định nghĩa bảng theo PostgreSQL:

~~~sql
CREATE TABLE batch_run (
    batch_key          VARCHAR(100) PRIMARY KEY,
    snapshot_id        VARCHAR(100) NOT NULL,
    expected_partitions INTEGER NOT NULL CHECK (expected_partitions > 0),
    expected_records   BIGINT NOT NULL CHECK (expected_records >= 0),
    state              VARCHAR(20) NOT NULL
                       CHECK (state IN (
                           'PREPARING','PROCESSING','VALIDATING',
                           'PUBLISHED','FAILED')),
    published_at       TIMESTAMPTZ
);

CREATE TABLE batch_partition_result (
    batch_key      VARCHAR(100) NOT NULL,
    partition_key  VARCHAR(80) NOT NULL,
    state          VARCHAR(20) NOT NULL,
    expected_count BIGINT NOT NULL,
    actual_count   BIGINT NOT NULL,
    PRIMARY KEY (batch_key, partition_key)
);

-- normalized_order_staging đã được tạo ở phần 9;
-- mọi worker ghi vào đó theo batch_key.
~~~

**Hợp đồng bắt buộc:**

- Worker **không được sửa** staging của một batch đã `PUBLISHED`.
- `batch_partition_result` phải phản ánh **đủ** số partition cố định trong manifest, không chỉ số dòng hiện có. Partition nào hoàn tất phải được ghi trạng thái bằng cơ chế được kiểm chứng; đừng cập nhật `COMPLETED` **trước** khi toàn bộ dữ liệu của partition thực sự bền vững.
- Kiểm tra `expected_records` dựa trên snapshot và các quy tắc lọc/skip được phê duyệt; tổng COUNT chỉ là một trong nhiều kiểm tra.
- Công bố phải là một thao tác **được serialize theo batch** để hai publisher không cùng quyết định hoặc publish sớm khi dữ liệu còn thay đổi.

Một bước cuối có thể khóa dòng `batch_run` và kiểm tra trạng thái, rồi chỉ chuyển sang `PUBLISHED` sau khi validation thực sự đạt:

~~~sql
BEGIN;

-- Đóng vai trò publication lock cho một batch.
SELECT state
FROM batch_run
WHERE batch_key = :batchKey
FOR UPDATE;

-- Trong cùng bước giao dịch có kiểm soát, ứng dụng đối soát:
--   1) state = 'VALIDATING', snapshot_id đúng;
--   2) manifest cố định có đủ expected_partitions;
--   3) mọi partition đã COMPLETED;
--   4) tập business key và business value khớp;
--   5) không có writer vẫn được quyền sửa kết quả.
--
-- Chỉ sau khi tất cả điều kiện trên đạt:
UPDATE batch_run
SET state = 'PUBLISHED',
    published_at = CURRENT_TIMESTAMP
WHERE batch_key = :batchKey
  AND state = 'VALIDATING';

COMMIT;
~~~

Đây là **phác thảo transaction publish**, **chưa phải stored procedure hoàn chỉnh**: phải viết code kiểm tra tất cả bất biến, xem row count của UPDATE, xử lý race và quyền ghi. **Row lock trên `batch_run` một mình không khóa những writer đang chỉnh `normalized_order_staging`** nếu writer không tham gia protocol khóa/trạng thái. Cần một **publication barrier thật sự**: dừng/quiesce mọi worker của batch và xác nhận kết thúc, hoặc buộc writer/claim operation kiểm tra trạng thái dưới cùng một protocol transaction phù hợp.

### Để downstream chỉ thấy batch đã công bố

~~~sql
CREATE VIEW published_normalized_order AS
SELECT r.batch_key, r.order_id, r.net_total
FROM normalized_order_staging AS r
JOIN batch_run AS b ON b.batch_key = r.batch_key
WHERE b.state = 'PUBLISHED';
~~~

Downstream chỉ truy vấn view/consumer contract này, không đọc thẳng staging. Khi trạng thái từ `VALIDATING` chuyển sang `PUBLISHED` trong một transaction, người đọc **sau commit** có thể thấy dữ liệu batch thông qua view theo isolation tương ứng. Một query đã bắt đầu **trước commit** vẫn có thể thấy snapshot cũ; đó là semantics MVCC bình thường.

**Điểm cốt lõi:** cách này tạo **atomic visibility theo cờ công bố**, **không phải global atomic commit của tất cả insert trước đó**. Nếu có quyền đọc thẳng bảng staging hoặc writer vẫn được phép sửa khi đã publish, tính chất này không còn được bảo đảm.

## 14. Bất biến trước khi chuyển trạng thái PUBLISHED

Một bước validate nên kiểm tra nhiều chiều, không dừng ở `COUNT(*)`.

| Bất biến | Kiểm tra | Lý do |
| --- | --- | --- |
| **Tập partition đầy đủ** | Manifest cố định so với tập partition COMPLETED | Không bỏ sót vùng dữ liệu |
| **Không có partition còn ghi** | Tất cả worker thực tế đã dừng/hoàn tất, không còn job cũ đang chạy | Tránh staging đổi sau validation |
| **Không thiếu business key** | `staged_order` left join output theo `batchKey,orderId` | COUNT tổng có thể đúng nhưng sai tập |
| **Không có output ngoài snapshot** | Output left join staging | Bắt record lạ/nhầm batch |
| **Giá trị khớp rule** | Tính lại hoặc đối soát checksum/aggregate | Tránh output có đủ row nhưng giá trị sai |
| **Skip/filter theo policy** | Bảng audit lỗi và tập record được phép bỏ | Không coi skip ngoài dự kiến là thành công |
| **Snapshot và rule version đồng nhất** | Metadata job/manifest/input hash | Tránh mix các lần deploy/reference data |
| **Tổng nghiệp vụ đúng** | SUM, grouping theo tenant/date/region | Bắt lỗi tổng và ranh giới nghiệp vụ |

Ví dụ đối soát trên hai bảng staging:

~~~sql
-- Record nguồn không có kết quả.
SELECT s.order_id
FROM staged_order AS s
LEFT JOIN normalized_order_staging AS o
  ON o.batch_key = s.batch_key
 AND o.order_id = s.order_id
WHERE s.batch_key = :batchKey
  AND o.order_id IS NULL;

-- Record kết quả không có trong snapshot.
SELECT o.order_id
FROM normalized_order_staging AS o
LEFT JOIN staged_order AS s
  ON s.batch_key = o.batch_key
 AND s.order_id = o.order_id
WHERE o.batch_key = :batchKey
  AND s.order_id IS NULL;

-- Kết quả được ghi bởi partition khác owner trong manifest.
SELECT o.order_id, o.partition_no AS actual_partition,
       s.partition_no AS expected_partition
FROM normalized_order_staging AS o
JOIN staged_order AS s
  ON s.batch_key = o.batch_key
 AND s.order_id = o.order_id
WHERE s.batch_key = :batchKey
  AND o.partition_no <> s.partition_no;
~~~

Nếu có skip/filter hợp lệ, tập `staged_order` kỳ vọng phải được **điều chỉnh bằng bảng audit/quy tắc được phê duyệt** trước khi kết luận thiếu dữ liệu. Nếu một record sinh nhiều output hợp lệ, mô hình business key cũng phải phản ánh điều đó.

## 15. Cách khác: output incremental với version và watermark

Không phải sản phẩm nào cũng yêu cầu đợi toàn batch. Với dashboard tiến độ hoặc nền tảng phân tích near-real-time, downstream có thể chấp nhận dữ liệu từng phần **nếu** có contract:

- Mỗi output có `batchKey`, `snapshotId`, `partitionKey` hoặc nguồn tương đương.
- Có `watermark`/tiến độ bền vững xác định những vùng đã hoàn tất.
- Truy vấn phải biết đâu là dữ liệu `PROVISIONAL` và đâu là `FINAL`.
- Không dùng tổng provisional để thực hiện quyết toán cuối ngày.
- Có khả năng replay/dedup và sửa kết quả khi một partition phải retry.

Ví dụ hiển thị:

~~~text
Batch 2026-11-26
  partition P0 COMPLETED  250,000/250,000
  partition P1 COMPLETED  250,000/250,000
  partition P2 COMPLETED  250,000/250,000
  partition P3 FAILED     180,000/250,000

Tổng 930,000 record hiện có là dữ liệu PARTIAL.
Không gắn nhãn batch FINAL.
~~~

**Watermark cũng cần hợp đồng rõ**: một timestamp “đã chạy tới 10:00” không chứng minh tất cả item trước 10:00 đều được xử lý nếu có sự kiện đến muộn hoặc partition chưa hoàn tất. Watermark dùng cho quyết định công bố phải gắn với owner/coverage thực sự.

## 16. Remote chunking: commit và reply qua broker không nguyên tử

Trong **remote chunking**, manager đọc item và gửi `ChunkRequest`. Worker xử lý/ghi, commit DB rồi trả `ChunkResponse`. Các mốc có thể khác giao dịch:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Request broker
    participant W as Worker
    participant D as Business DB
    participant R as Reply broker
    M->>Q: ChunkRequest #42
    Q->>W: Deliver #42
    W->>D: BEGIN / write / COMMIT
    D-->>W: Commit succeeded
    W->>R: Publish ChunkResponse #42
    R->>M: Deliver reply #42
    M->>M: Correlate và ghi nhận kết quả
~~~

**Bốn trạng thái phải phân biệt:**

1. **Broker nhận request**: chưa chứng minh worker chạy.
2. **Worker DB commit**: dữ liệu đã ghi trong DB, nhưng broker/manager có thể chưa biết.
3. **Consumer ACK / reply publish**: thuộc hợp đồng middleware, không tự bao hàm DB commit.
4. **Manager nhận và correlate reply**: tiến độ step có thông tin để tổng hợp; vẫn cần đối soát nghiệp vụ khi cần.

Kịch bản nguy hiểm:

~~~text
Worker commit thành công.
Worker crash trước khi gửi reply hoặc trước request ACK.
Broker có thể redeliver chunk.
Worker khác ghi lại cùng các business item.
~~~

Nếu writer idempotent, replay vẫn cho kết quả đúng. Nếu writer cộng dồn/trừ tiền/gửi event không có operation key, replay có thể làm sai dữ liệu. **Correlation ID giúp ghép reply; nó không thay idempotency key của business effect**.

Không tuyên bố “exactly-once end-to-end” chỉ vì broker có durable queue hoặc transaction ở worker. Bảo đảm end-to-end cần xét **source, broker, reply, JobRepository, business DB và side effect ngoài DB**.

## 17. Remote partitioning: worker mất kết nối sau commit

Trong **remote partitioning**, manager yêu cầu worker thực thi một `StepExecution` với `ExecutionContext`. Worker có thể đã commit nhiều chunk rồi mất kết nối middleware trước khi reply trạng thái về manager.

~~~text
Manager -> partition P7
Worker A chạy P7
  chunk 1 COMMIT
  chunk 2 COMMIT
  chunk 3 COMMIT
  kết thúc worker step
Network lỗi -> reply không tới manager

Manager chỉ thấy timeout / trạng thái chưa rõ.
~~~

Không nên lập tức chạy **worker B đồng thời trên cùng P7** khi worker A có thể vẫn đang chạy. Điều đó tạo nguy cơ hai executor cùng ghi vào một vùng. Để bảo vệ:

- Dùng **JobRepository chung và chính xác**, ghi nhận StepExecution theo protocol của Spring Batch.
- Đối chiếu trạng thái worker, heartbeat/lease nếu kiến trúc hỗ trợ, và kết quả DB.
- Khi recovery, bảo đảm **không còn worker cũ được phép tiếp tục ghi**, hoặc các ghi được bảo vệ bằng fencing/version/unique key ở sink.
- Giữ `ExecutionContext` và snapshot input của P7 ổn định khi restart.
- Writer idempotent theo record/operation, không theo hostname hoặc lần dispatch.

**Timeout là “không có phản hồi đúng hạn”, không phải “worker chắc chắn chưa commit”.**

## 18. Metadata của JobRepository không thay thế business transaction

`JobRepository` quản lý metadata như `JobExecution`, `StepExecution`, `ExecutionContext`, các bộ đếm read/write/commit/rollback. Dữ liệu nghiệp vụ có thể nằm trong DB khác hoặc cùng DB nhưng dưới transaction manager/cấu hình khác.

| Trạng thái quan sát | Điều có thể đã xảy ra | Không được kết luận |
| --- | --- | --- |
| StepExecution FAILED | Một worker lỗi, các chunk trước có thể đã commit | “Output DB của step chắc chắn rỗng” |
| StepExecution COMPLETED | Framework đã hoàn tất step theo contract | “Không có lỗi nghiệp vụ do viết SQL sai” |
| JobExecution FAILED | Flow tổng thể thất bại | “Mọi worker đã rollback toàn bộ” |
| Broker request ACK | Broker xử lý delivery theo policy | “Worker đã commit DB và manager nhận reply” |
| JobExecution COMPLETED | Framework kết thúc job thành công | “Mọi API ngoài đã thực hiện đúng một lần” |

Khi business DB và JobRepository dùng hai datasource, luôn kiểm thử tình huống **một resource commit, resource kia không cập nhật được metadata**. Hệ thống phải chịu được khả năng replay khi metadata không phản ánh ngay business commit. Nếu cùng một datasource/transaction manager được sử dụng, cần xác minh thực tế những thao tác metadata nào tham gia cùng transaction; không dựa vào tên `DataSource` hoặc suy luận chung chung.

**Tuyệt đối không tự sửa metadata StepExecution thành COMPLETED** để “khớp” với một phần kết quả DB mà chưa đối soát và hiểu đầy đủ trạng thái worker.

## 19. Event và API: transactional outbox thay cho gọi trực tiếp

Một worker có thể vừa cập nhật kết quả DB vừa cần gửi sự kiện `OrderNormalized` sang Kafka/RabbitMQ. Nếu code viết DB rồi gọi broker trực tiếp:

~~~text
DB COMMIT thành công.
Broker publish thất bại.
Database có kết quả nhưng downstream không có event.
~~~

Nếu làm ngược lại:

~~~text
Event publish thành công.
DB COMMIT thất bại.
Downstream thấy event cho dữ liệu không tồn tại.
~~~

**Transactional outbox** giảm rủi ro bằng cách lưu **business result và outbox record trong cùng một DB transaction**:

~~~sql
CREATE TABLE normalized_order (
    batch_key  VARCHAR(100) NOT NULL,
    order_id   BIGINT NOT NULL,
    net_total  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, order_id)
);

CREATE TABLE outbox_event (
    event_id    VARCHAR(160) PRIMARY KEY,
    batch_key   VARCHAR(100) NOT NULL,
    order_id    BIGINT NOT NULL,
    event_type  VARCHAR(80) NOT NULL,
    payload     JSONB NOT NULL,
    state       VARCHAR(20) NOT NULL DEFAULT 'NEW'
);
~~~

~~~sql
BEGIN;

INSERT INTO normalized_order (batch_key, order_id, net_total)
VALUES (:batchKey, :orderId, :netTotal)
ON CONFLICT (batch_key, order_id)
DO UPDATE SET net_total = EXCLUDED.net_total;

INSERT INTO outbox_event (
    event_id, batch_key, order_id, event_type, payload)
VALUES (
    :eventId, :batchKey, :orderId, 'ORDER_NORMALIZED',
    :jsonPayload)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

`eventId` phải là **ID của logical event** ổn định qua retry, ví dụ `batchKey + "/order/" + orderId + "/normalized"`, nếu mỗi order chỉ phát đúng một sự kiện loại đó trong batch. Publisher riêng đọc outbox và phát event; khi publish thành công theo broker contract, nó đánh dấu trạng thái đã gửi theo protocol phù hợp.

**Outbox không tự đảm bảo event được tiêu thụ đúng một lần.** Publisher có thể publish xong nhưng chết trước khi đánh dấu outbox SENT, khiến event được gửi lại. Consumer vẫn cần **dedup/idempotency key** theo `eventId`. Nếu yêu cầu chỉ phát event khi batch `PUBLISHED`, publisher phải lọc/join trạng thái công bố hoặc tạo outbox sự kiện **sau publication barrier** theo thiết kế rõ ràng; đừng phát kết quả provisional rồi gọi đó là FINAL.

## 20. Khi nào cần orchestration/Saga hoặc transaction phân tán?

Nếu job cần cập nhật **nhiều hệ thống độc lập** (DB thanh toán, CRM, kho hàng, broker), mỗi hệ thống có transaction riêng. Một JVM không thể mặc nhiên rollback tất cả sau khi vài hệ thống đã commit.

Có ba lựa chọn kiến trúc thường gặp:

1. **Idempotent eventual consistency:** mỗi hệ thống chấp nhận retry và đối soát; phù hợp khi có thể hoàn tất dần.
2. **Orchestration/Saga:** một điều phối viên quản lý các bước và **compensation** theo nghiệp vụ khi bước sau thất bại (ví dụ hoàn tiền, hủy giữ hàng); compensation **không phải rollback ACID** và có thể thất bại, cần retry/monitor.
3. **XA/2PC** nếu tất cả resource/transaction manager thực sự hỗ trợ và yêu cầu atomicity rất mạnh; phải cân nhắc hiệu năng, lock, coordinator failure, broker participation và độ phức tạp vận hành.

**Không tự chọn 2PC vì muốn “job thất bại thì rollback hết”**. Một batch kéo dài hàng giờ với nhiều chunk không nên giữ một transaction phân tán mở xuyên toàn bộ thời gian chạy. Thường dễ thiết kế hơn với staging, publish barrier, idempotency và compensation có kiểm soát.

### Điều gì là nhất quán cuối cùng?

Nếu hệ thống chấp nhận mọi component **hội tụ về một trạng thái nghiệp vụ đúng** sau retry, reconciliation và eventual delivery, đó là một dạng **eventual consistency**. Nó không có nghĩa chấp nhận mất dữ liệu vô thời hạn: cần SLA, giới hạn retry, DLQ/incident, metrics và cơ chế khôi phục rõ ràng.

## 21. Test bằng lỗi chủ đích: không chỉ nhìn status

Các bài kiểm thử phải dùng **snapshot cố định**, DB thật/DB tương đương production (ví dụ Testcontainers PostgreSQL) và **failure injection ở ranh giới commit**.

| Kịch bản | Injection | Assertion bắt buộc |
| --- | --- | --- |
| Một chunk thất bại | Writer ném lỗi trước commit | Chunk đó rollback; commit trước đó giữ nguyên |
| P3 fail sau vài chunk | Worker P3 ném lỗi khi P0–P2 đã commit | Job phản ánh thất bại, dữ liệu partial chưa PUBLISHED |
| Retry/restart | Restart cùng JobInstance | Không nhân đôi `(batchKey, orderId)`, đủ output cuối |
| Hai worker cùng business key | Cố giao overlap có kiểm soát | Conflict được phát hiện, không âm thầm ghi sai |
| Reference data đổi | Thay tỷ giá hoặc rule giữa các lần thử | Snapshot/rule version ngăn output trộn |
| Worker mất reply sau commit | Chặn reply/broker sau DB commit | Replay idempotent, không cộng dồn lặp |
| Manager mất metadata sau commit | Gây lỗi metadata theo mô hình hạ tầng | Recovery/đối soát an toàn, không assume transaction chung |
| Publication barrier | Giữ một partition chưa hoàn thành | Downstream view không thấy batch trước khi được PUBLISHED |
| Outbox publish duplicate | Publish rồi crash trước đánh dấu SENT | Consumer dedup theo eventId |

### Vì sao dùng CountDownLatch thay vì Thread.sleep?

`Thread.sleep(500)` không bảo đảm hai transaction thực sự overlap trên máy CI. Hãy dùng `CountDownLatch` hoặc barrier để giữ worker ở **điểm đã biết**:

~~~java
final class CommitBoundaryProbe {
    final CountDownLatch afterFirstCommit =
            new CountDownLatch(1);
    final CountDownLatch allowSecondPartition =
            new CountDownLatch(1);

    void firstPartitionCommitted() {
        // Chỉ gọi từ hook/cơ chế xác nhận SAU commit thật.
        afterFirstCommit.countDown();
    }

    void blockSecondPartition() throws InterruptedException {
        if (!allowSecondPartition.await(
                15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out in test");
        }
    }
}
~~~

Test runner đợi `afterFirstCommit`, kiểm tra DB đã có kết quả **đã commit**, sau đó làm partition thứ hai fail hoặc giữ nó lại trước publish. Dùng `finally` để mở latch và dọn task nếu test thất bại. **Không gọi `firstPartitionCommitted()` ngay sau `writer.write()` khi transaction vẫn đang mở**, vì write return không chứng minh commit.

Một bộ test còn nên kiểm tra **rollbackCount**, **commitCount**, output business keys và metadata StepExecution, không chỉ `BatchStatus`.

## 22. Test tính nhất quán của hai worker ghi chung DB

Giả sử hai worker có nguồn tách biệt nhưng cùng cập nhật một bảng tổng hợp. Một phép test hữu ích:

1. Cho worker A và B cùng đọc một row `account_balance` ban đầu.
2. Dùng barrier để cả hai chuẩn bị ghi từ cùng giá trị cũ.
3. Với implementation sai `SELECT balance` rồi `UPDATE balance = :newBalance`, chứng minh nguy cơ lost update.
4. Thay bằng `UPDATE balance = balance + :delta` và kiểm tra phép cộng đồng thời.
5. **Tiếp tục thử replay cùng operation ID** để chỉ ra atomic increment **vẫn có thể cộng hai lần**.
6. Thêm bảng dedup unique operation ID và ghi increment + dedup trong **cùng transaction**; kiểm tra chỉ một phép cộng có tác dụng.

Ví dụ schema cho idempotent effect ledger:

~~~sql
CREATE TABLE applied_operation (
    batch_key       VARCHAR(100) NOT NULL,
    operation_id    VARCHAR(120) NOT NULL,
    account_id      BIGINT NOT NULL,
    delta           NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, operation_id)
);
~~~

Một flow đúng phải dựa vào **kết quả chèn operation ID duy nhất** trong transaction (và từ chối conflict khác nội dung), chỉ khi operation được chấp nhận mới thay đổi balance. Hai statement cần ở **cùng DB transaction**:

~~~text
BEGIN
  Kiểm tra/ghi nhận operation ID bằng unique constraint
  Nếu operation mới và dữ liệu hợp lệ: cập nhật balance
  Nếu operation đã áp dụng: xác nhận giá trị cũ khớp và không cộng lại
COMMIT
~~~

Đừng làm `SELECT count(*)` ngoài transaction rồi `UPDATE`; hai worker có thể cùng nhìn thấy “chưa tồn tại” và cùng áp dụng. Unique constraint cùng transaction/locking phù hợp mới là nền chống race.

## 23. Metric để biết commit độc lập có an toàn không

| Metric | Câu hỏi vận hành | Dấu hiệu cảnh báo |
| --- | --- | --- |
| Per-partition `readCount/writeCount` | Vùng nào đang chậm hoặc bị thiếu? | Một vùng lệch mạnh khỏi kỳ vọng |
| `commitCount/rollbackCount` | Có nhiều lần rollback/retry? | Rollback spike |
| Commit latency p95/p99 | DB có chịu được số transaction? | Tăng khi worker pool lớn |
| Lock wait/deadlock | Partition có tranh cùng row/index? | Lock timeouts, deadlocks |
| DB active/waiting connections | Worker có làm cạn pool không? | Connection wait tăng |
| `duplicate_operation_count` | Replay có nhiều không? | Tăng đột biến hoặc conflict giá trị |
| `batch_publication_state` | Batch nào đã FINAL/PUBLISHED? | VALIDATING treo lâu |
| `validation_mismatch_count` | Có thiếu/trùng/sai giá trị? | Bất kỳ mismatch ngoài chính sách |
| `stale_worker_attempts` | Worker cũ còn ghi sau restart? | Commit từ attempt không hợp lệ |
| Outbox backlog/oldest age | Event chưa đến downstream? | Eventual consistency vượt SLA |
| Broker redelivery/reply timeout | Remote outcome có mơ hồ? | Retry storm, missing reply |

Không dùng chỉ một số `itemsPerSecond` để đánh giá. Một cấu hình 16 worker có thể xử lý nhanh hơn nhưng làm deadlock tăng, số lần replay nhiều hơn và publish batch chậm hơn. **Tính đúng đắn và thời gian hoàn tất *toàn pipeline*** mới là thước đo quan trọng.

### Tách `processed`, `committed` và `published`

~~~text
processed  = processor đã chạy qua item (có thể sẽ rollback)
committed  = DB transaction nghiệp vụ đã commit
published  = kết quả batch được công bố cho downstream
~~~

Ba số này khác nhau. Đừng tăng counter `committed` trực tiếp khi processor trả về hoặc writer gọi xong mà transaction vẫn chưa commit.

## 24. Chi phí hiệu năng và lựa chọn chunk size

Số transaction tăng khi chunk size nhỏ, đồng nghĩa chi phí commit, lock và metadata thường tăng. Nhưng chunk quá lớn khiến:

- rollback phải xử lý lại nhiều item hơn;
- transaction giữ lock/connection lâu hơn;
- bộ nhớ giữ item hoặc JDBC batch lớn hơn;
- một worker lỗi có thể làm chậm tail latency của partition;
- trong remote chunking, payload request/reply lớn hơn.

Một ma trận thử nghiệm:

| Kịch bản | Chunk size | Worker đồng thời | Điều cần đo |
| --- | ---: | ---: | --- |
| A | 50 | 2 | Baseline an toàn, commit overhead |
| B | 200 | 2 | Commit latency và DB pool |
| C | 200 | 4 | Throughput, lock wait, rollback |
| D | 500 | 4 | Heap, transaction time, retry cost |
| E | 200 | 8 | DB saturation, deadlocks, publish barrier delay |

Nếu nguồn 1.000.000 item và chunk 200, số chunk dữ liệu thành công lý tưởng khoảng 5.000 trên toàn bộ job, **không** phải 5.000 transaction trong một giao dịch lớn. Số commit thực có thể khác do chunk cuối, skip/filter, retry, transaction metadata và cấu hình reader.

**Tăng concurrency không tạo thêm tính nhất quán.** Nhiều worker làm tăng số transaction đồng thời và nguy cơ lock contention; chọn concurrency theo CPU, throughput nguồn, DB pool, I/O, latency và khả năng đối soát/restart.

## 25. Runbook khi job FAILED nhưng DB đã có kết quả

Khi người vận hành thấy job thất bại, nhưng bảng kết quả có dữ liệu:

1. **Xác định JobInstance/JobExecution** và danh sách StepExecution/partition theo trạng thái COMPLETED/FAILED/STARTED/UNKNOWN.
2. **Khóa quyền công bố** batch: downstream không được coi staging đang dở là FINAL.
3. **Đối chiếu snapshot và manifest**: số partition, phạm vi, version, identifying JobParameters có giữ nguyên không.
4. **Kiểm tra transaction đã commit**: record thật trong DB, số commit/rollback và các tác động ngoài DB.
5. **Phân loại lỗi**: permanent data, deadlock, DB timeout, worker crash, mất reply hay mismatch nghiệp vụ.
6. **Kiểm tra worker cũ**: chưa còn worker/process có thể ghi lại vùng dữ liệu trong khi restart.
7. **Sửa nguyên nhân**, không thay đổi partition mapping hoặc snapshot của cùng JobInstance một cách tùy ý.
8. **Restart an toàn** theo JobRepository và chính sách idempotency; chấp nhận một số item có thể được replay.
9. **Validate đầy đủ** tập business key, giá trị, partition coverage và trạng thái metadata.
10. **Công bố** batch chỉ khi validation thành công, publish barrier bảo đảm không còn write trái phép.
11. **Xử lý outbox/DLQ** và downstream idempotency trước khi đóng sự cố.

**Không chạy `DELETE FROM output WHERE batchKey=...` một cách vội vàng** khi các worker vẫn có thể ghi hoặc khi downstream đã tiêu thụ tác động ngoài DB; việc xóa dữ liệu không rollback được email, payment hay message đã gửi.

## 26. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân gốc | Cách sửa |
| --- | --- | --- |
| Job FAILED nhưng output còn | Hiểu nhầm JobExecution là global transaction | Chấp nhận commit độc lập, staging/publish, restart |
| Một partition fail làm tổng báo cáo sai | Downstream đọc staging trực tiếp | Publication gate hoặc contract provisional |
| Retry làm tổng tiền tăng hai lần | Writer dùng additive update không dedup | Business operation ID + transaction/unique constraint |
| Hai worker ghi đè nhau | Partition overlap hoặc cùng aggregate row | Non-overlap/owner key, optimistic locking/atomic ops |
| Restart đọc dữ liệu khác | Source mutable hoặc thay partition mapping | Snapshot/manifest bất biến |
| Reader rollback nhưng DB output có commit | Business write ngoài transaction manager dự kiến | Kiểm tra datasource/transaction manager/resource |
| Có đủ row nhưng số tiền sai | Upsert ghi đè giá trị khác, reference data đổi | Rule version, hash, đối soát giá trị |
| Worker đã commit nhưng manager timeout | Mất reply/ACK hoặc broker/network | Idempotency, correlation và xác minh outcome |
| Publisher phát event hai lần | Outbox publish xong trước khi mark SENT | Consumer dedup theo event ID |
| Batch PUBLISHED dù worker còn ghi | Validation không có writer quiescence/fencing | Publication barrier có protocol khóa/quyền rõ |
| Tăng worker làm job chậm | DB pool/lock/index đã bão hòa | Đo concurrency, giảm/chia lại tải |
| Job COMPLETED nhưng ngoài hệ thống thiếu side effect | Chỉ kiểm tra BatchStatus, bỏ qua outbox/DLQ | End-to-end reconciliation và SLA hội tụ |

## 27. Bài thực hành cuối bài

Xây một pipeline có **bốn partition** từ một snapshot 20.000 record, mỗi partition khoảng 5.000 record. Các worker ghi `normalized_order_staging` theo `(batchKey, orderId)` với chunk size 200. Downstream chỉ được đọc qua `published_normalized_order` khi batch `PUBLISHED`.

Thực hiện:

1. **Normal run:** chạy bốn partition đồng thời, xác minh output đủ key/giá trị và chỉ xuất hiện qua view sau publish.
2. **Partial failure:** cho P3 lỗi sau chunk thứ ba đã commit; kiểm tra P0–P2 vẫn có output staging, job không COMPLETED và view không thấy batch.
3. **Restart:** sửa lỗi, restart cùng JobInstance/snapshot; xác minh không nhân đôi và tất cả partition hoàn tất.
4. **Duplicate dispatch:** cố tình giao trùng một order cho hai worker; test phải phát hiện overlap hoặc conflict theo owner, không silently overwrite.
5. **Lost reply:** khi dùng remote flow, chặn reply sau DB commit rồi để chunk redeliver; dữ liệu vẫn đúng nhờ business idempotency.
6. **Publish barrier:** giữ P2 ở trạng thái chưa hoàn tất; cố publish phải thất bại. Sau khi P2 xong, validation toàn batch đạt mới publish.
7. **Outbox:** phát event từ outbox trong một publisher giả lập crash sau publish trước mark SENT; consumer dedup không xử lý tác động hai lần.
8. **Benchmark:** thử chunk 50/200/500 và worker 1/2/4/8, ghi commit latency, DB wait, throughput và tổng thời gian đến PUBLISHED.

### Checklist trước production

- [ ] Đã xác định ranh giới transaction thực của mỗi chunk/worker và các nguồn dữ liệu liên quan.
- [ ] Không kỳ vọng một JobExecution FAILED rollback các chunk/partition đã commit.
- [ ] Có snapshot/manifest, business rule version và mapping partition bất biến khi restart.
- [ ] Reader state/metadata phù hợp với transaction và checkpoint; writer replay-safe.
- [ ] Có unique business key/idempotency key, phát hiện conflict khác nội dung thay vì che giấu.
- [ ] Đã kiểm thử lock contention, deadlock, lost update, retry và replay sau kết quả commit không rõ.
- [ ] Khi cần batch-complete visibility, dùng staging + validation + publication barrier thật; downstream không đọc staging trực tiếp.
- [ ] Các worker cũ không còn quyền thay đổi staging sau validation/PUBLISHED.
- [ ] Những side effect qua broker/API có outbox/dedup, bounded retry và chính sách đối soát.
- [ ] Có failure-injection test giữa commit–reply/ACK và sau một số chunk commit.
- [ ] Có metric per-partition, commit/rollback, DB pool, validation mismatch, publish state và outbox backlog.
- [ ] Có runbook cho partial success, UNKNOWN StepExecution, job restart và kết quả nguồn/đích lệch.

**Ghi nhớ:** **commit độc lập là đặc tính bình thường của Spring Batch khi mở rộng song song và phân tán**. Transaction chunk chỉ bảo đảm tính nguyên tử của những tài nguyên thực sự tham gia **giao dịch đó**; nó không rollback các commit đã xảy ra ở worker khác, không giữ nguyên snapshot nguồn giữa mọi thread và không bảo đảm hiệu ứng ngoài DB đúng một lần. Thiết kế nhất quán đòi hỏi **snapshot bất biến, non-overlap partitions, writer idempotent, đối soát, publish barrier khi cần và cơ chế retry/restart có thể chứng minh bằng kiểm thử lỗi thực tế**.
