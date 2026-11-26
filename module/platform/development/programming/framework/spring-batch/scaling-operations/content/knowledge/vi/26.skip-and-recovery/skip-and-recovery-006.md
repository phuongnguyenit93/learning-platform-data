# Dead-letter record

Trong workload dữ liệu lớn, một vài bản ghi có thể thiếu định danh, sai CSV, vi phạm ràng buộc nghiệp vụ hoặc không thể ghi vào hệ thống đích. Nếu mọi lỗi đều làm job thất bại, hàng triệu record hợp lệ có thể bị chặn bởi một record hỏng. Nhưng nếu chỉ **skip** rồi bỏ qua, kết quả có thể thiếu dữ liệu mà không có cách giải thích hay sửa chữa. **Dead-letter record** là cách **cách ly và lưu bằng chứng về record không thể xử lý theo chính sách hiện tại**, phục vụ kiểm tra, sửa, xử lý lại hoặc phê duyệt loại trừ một cách có kiểm soát.

Bài học thuộc chương **Skip và recovery** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế. Nội dung tập trung vào **dead-letter ở mức record**, cách phối hợp với `SkipListener`, ranh giới transaction, khả năng idempotent khi retry và quy trình recovery khi nhiều chunk/partition/worker commit độc lập.

**Nguyên tắc:** skip một item không có nghĩa item ấy không còn giá trị nghiệp vụ. Record bị loại cần **định danh nguồn ổn định, lý do chuẩn hóa, trạng thái xử lý tiếp và khả năng đối soát**. Dead-letter không phải nơi để nuốt mọi exception.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **dead-letter record**, **quarantine table**, **reject file**, **broker DLQ** và audit log.
2. Quyết định lỗi nào được **skip**, lỗi nào cần **retry**, lỗi nào bắt buộc **fail**.
3. Dùng ba callback `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` trong Spring Batch 5.x.
4. Tạo dead-letter schema có batch/source identity, failure stage, reason code, snapshot và recovery status.
5. Ghi quarantine trong transaction phù hợp, không tách rời outcome của chunk nếu nghiệp vụ không cho phép.
6. Chống ghi trùng khi rollback/retry, worker restart, broker redelivery hay record bị giao cho hai partition.
7. Thiết kế **skip budget toàn job**, không nhầm `skipLimit` per StepExecution với hạn mức toàn batch.
8. Xây recovery job có claim/lease, idempotent output và audit sửa chữa.
9. Kiểm thử có chủ đích read/process/write skip, lỗi storage, transaction rollback, restart và dữ liệu cuối.

**Tình huống xuyên suốt:** mỗi đêm, hệ thống nhập 5 triệu giao dịch từ các file CSV vào PostgreSQL. Một số dòng sai cấu trúc; một số có số tiền âm, thiếu mã giao dịch; một số chunk gặp DB timeout tạm thời. Job cần tiếp tục với record tốt, cách ly record lỗi **được phép bỏ qua**, nhưng **không** biến lỗi kết nối DB hay cross-tenant inconsistency thành bad record. Batch chỉ được công bố nếu chất lượng toàn tập đáp ứng ngưỡng.

## 2. Dead-letter record khác broker dead-letter queue thế nào?

Dead-letter record ở đây là **một record nghiệp vụ không tạo output bình thường**, kèm metadata để điều tra và replay. Nó có thể lưu trong database, reject file, object storage hoặc một topic nghiệp vụ riêng. Broker dead-letter queue (DLQ) thường giữ **nguyên message** khi delivery/processing không thể tiếp tục theo retry policy.

| Khái niệm | Đơn vị | Mục đích | Tính nguyên tử với business DB |
| --- | --- | --- | --- |
| Record quarantine | Một input record | Giữ bằng chứng record bị skip để sửa | Chỉ khi cùng transaction/resource |
| Skip count | Số lượng item được skip theo step | Giám sát mức độ lỗi | Không lưu input hay lý do đủ replay |
| Reject file | Nhiều dòng dữ liệu lỗi | Xem và nạp lại dữ liệu | Thường không nguyên tử với DB |
| Broker DLQ | Một message, có thể chứa cả chunk | Ngăn poison message redeliver vô hạn | Không mặc định |
| Audit event | Một biến cố xử lý/sửa | Truy vết ai đã làm gì, lúc nào | Tùy storage và transport |

Ví dụ remote chunking: một `ChunkRequest` chứa 200 records. Nếu 1 record sai số tiền, dead-letter **record đó** khác với đẩy **cả message 200 items** vào broker DLQ. Manager còn phải nhận outcome hợp lệ của chunk hoặc thấy step thất bại, không được coi message đã vào DLQ là thành công nghiệp vụ.

## 3. Lỗi nào skip, retry hoặc fail?

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp | Giải thích |
| --- | --- | --- | --- |
| Malformed input | CSV sai cột, số không parse được | Skip có giới hạn + quarantine | Gắn với record và có thể sửa |
| Business validation | Thiếu transaction ID, amount âm không hợp lệ | Skip được phê duyệt + quarantine | Bảo toàn bằng chứng và quy trình phục hồi |
| Transient infrastructure | DB timeout, HTTP 503, deadlock | **Retry** hữu hạn/backoff | Không chứng minh input sai |
| Code/configuration | NullPointerException, thiếu credential, SQL sai | **Fail job** | Skip có thể che lỗi diện rộng |
| Consistency/security | Ghi chéo tenant, trùng khóa khác giá trị | **Fail/alert** | Không được coi là record xấu thông thường |
| Lỗi nghiệp vụ được chấp nhận | Tài khoản bị khóa, trạng thái loại trừ | Skip/filter theo hợp đồng và audit phù hợp | Cần thống nhất có được bỏ hay không |

**Không dùng `skip(Exception.class)` hoặc `skip(RuntimeException.class)` theo thói quen.** Một lỗi DB khiến cả chunk thất bại không có nghĩa mọi record trong chunk đều là bad record.

**Retry** thử lại một thao tác vì nguyên nhân có thể biến mất. **Skip** chấp nhận item không tạo output bình thường trong lần chạy. **Dead-letter** lưu dấu vết của quyết định ấy. **Recovery** xử lý record đã cách ly bằng nguồn và quy tắc đã được kiểm chứng.

## 4. Record đi qua các pha đọc, xử lý, ghi

~~~mermaid
flowchart TD
    S["Input snapshot bất biến"] --> R["ItemReader"]
    R -->|"Đọc OK"| P["ItemProcessor"]
    R -->|"Parse error được skip"| ER["onSkipInRead"]
    P -->|"Output hợp lệ"| W["ItemWriter"]
    P -->|"Validation error được skip"| EP["onSkipInProcess"]
    W -->|"Write OK"| O[("Business output")]
    W -->|"Write error được skip"| EW["onSkipInWrite"]
    ER --> DL[("Quarantine record")]
    EP --> DL
    EW --> DL
    DL --> REC["Review / repair / replay"]
~~~

Đây là **sơ đồ logic**, không phải thứ tự callback chính xác ở mọi đường lỗi. Với write error, Spring Batch có thể rollback/retry và kiểm tra lại từng item theo fault-tolerance policy trước khi thực sự quyết định skip.

### Vì sao dùng SkipListener?

`SkipListener` được Spring Batch thiết kế để báo item **thực sự bị skip**, khác với listener `onReadError`/`onProcessError`/`onWriteError` vốn có thể nhận lỗi **trong một lần thử trung gian** trước khi retry thành công. Framework cố gắng gọi SkipListener **một lần cho mỗi item đã skip** và **gần thời điểm chunk commit** để thuận tiện ghi audit vào transaction. Tuy vậy, redelivery, side effect ngoài DB và custom code vẫn đòi hỏi idempotency.

## 5. Dead-letter record cần những trường nào?

Một record cách ly tốt phải trả lời:

- **Record nào?** Source record key ổn định, không tạo UUID mới mỗi lần skip.
- **Từ snapshot nào?** Batch key, snapshot/source version, định danh file/record hoặc PK.
- **Lỗi ở đâu?** `READ`, `PROCESS`, `WRITE`.
- **Tại sao?** Reason code có danh sách cho phép; summary đã loại bỏ dữ liệu nhạy cảm.
- **Thuộc quyền ai?** Tenant/domain nếu có bằng chứng đáng tin.
- **Trạng thái hiện tại?** `PENDING`, `IN_REVIEW`, `REPROCESSED`, `WAIVED`...
- **Có thể replay không?** Còn dữ liệu nguồn bất biến, phiên bản rule và khóa chống lặp không?

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `batch_key` | `settlement-2026-11-26` | Batch logic cần đối soát |
| `source_key` | `snap-1/file-03/record-240` | Chủ thể dedup qua retry |
| `failure_stage` | `PROCESS` | Phân biệt parse, validation và write |
| `reason_code` | `NEGATIVE_AMOUNT` | Phân nhóm lỗi ổn định |
| `reason_summary` | `Amount must be non-negative` | Không lưu raw payload |
| `tenant_id` | `tenant-a` | Chỉ khi được xác thực |
| `snapshot_id` | `snap-2026-11-26` | Xác định version nguồn |
| `status` | `PENDING` | Vòng đời xử lý lỗi |

**Vấn đề CSV:** với dữ liệu có dấu xuống dòng bên trong trường được trích dẫn, **số dòng vật lý** khác **số record logic**. Muốn replay đúng, source key phải dựa trên **snapshot và vị trí được reader/record envelope xác nhận** chứ không đoán rằng dòng thứ N luôn là record thứ N.

## 6. Schema quarantine bằng PostgreSQL

~~~sql
CREATE TABLE dead_letter_record (
    batch_key      VARCHAR(100) NOT NULL,
    source_key     VARCHAR(240) NOT NULL,
    failure_stage  VARCHAR(16) NOT NULL
                   CHECK (failure_stage IN ('READ','PROCESS','WRITE')),
    snapshot_id    VARCHAR(100) NOT NULL,
    source_ref     VARCHAR(240) NOT NULL,
    tenant_id      VARCHAR(100),
    reason_code    VARCHAR(80) NOT NULL,
    reason_summary VARCHAR(300) NOT NULL,
    status         VARCHAR(24) NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN (
                       'PENDING', 'IN_REVIEW', 'REPROCESSED',
                       'WAIVED', 'REJECTED')),
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_key, source_key, failure_stage)
);

CREATE INDEX idx_dead_letter_pending
    ON dead_letter_record (status, first_seen_at);

CREATE INDEX idx_dead_letter_reason
    ON dead_letter_record (batch_key, reason_code, failure_stage);
~~~

Khóa chính giúp cùng logical failure không tạo vô số rows khi item bị replay. Nhưng `ON CONFLICT DO NOTHING` có thể che giấu tình huống **cùng source key mang reason/nội dung khác**. Production cần đối chiếu trường quan trọng trên conflict, hoặc lưu thêm audit history, và fail khi thấy dấu hiệu vi phạm snapshot.

**Không mặc định lưu raw record trong bảng.** Nếu cần bytes để phân tích parse error, giữ payload trong object storage đã mã hóa, quyền truy cập và retention phù hợp, rồi lưu reference. Exception của DB/parser đôi khi chứa PII, SQL values hoặc secrets.

## 7. Ba callback của SkipListener

~~~java
public interface SkipListener<T, S> {
    default void onSkipInRead(Throwable t) {}
    default void onSkipInProcess(T item, Throwable t) {}
    default void onSkipInWrite(S item, Throwable t) {}
}
~~~

`T` là kiểu item trước processor; `S` là kiểu item writer nhận. Khi reader lỗi quá sớm, Spring Batch **chưa có item**, nên `onSkipInRead` chỉ nhận exception.

| Callback | Có item? | Khóa truy vết có thể dùng | Lưu ý |
| --- | --- | --- | --- |
| `onSkipInRead(Throwable)` | Không | Reader exception + source position | Phải xác minh offset hoặc file/line |
| `onSkipInProcess(T,Throwable)` | Có input item | Source key trong item | Business reject đã phân loại |
| `onSkipInWrite(S,Throwable)` | Có output item | Source key được truyền qua processor | Writer có thể đã retry nhiều lần |

Không dùng `onProcessError` để khẳng định một record đã bị loại: record ấy có thể **retry thành công**. Khi writer báo lỗi JDBC batch, không phải lúc nào có thể nhận diện item cụ thể ngay; nếu không chắc lỗi **per item**, **fail** thay vì đoán.

## 8. Ví dụ model và processor có reason code

~~~java
record OrderInput(
        String sourceKey,
        String tenantId,
        String transactionId,
        BigDecimal grossAmount) {}

record OrderOutput(
        String sourceKey,
        String tenantId,
        String transactionId,
        BigDecimal netAmount) {}

final class InvalidRecordException extends RuntimeException {
    private final String reasonCode;

    InvalidRecordException(String reasonCode, String safeMessage) {
        super(safeMessage);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}

@Bean
ItemProcessor<OrderInput, OrderOutput> validateAndNormalize() {
    return input -> {
        if (input.transactionId() == null
                || input.transactionId().isBlank()) {
            throw new InvalidRecordException(
                    "MISSING_TRANSACTION_ID", "Transaction ID is required");
        }
        if (input.grossAmount() == null
                || input.grossAmount().signum() < 0) {
            throw new InvalidRecordException(
                    "INVALID_AMOUNT", "Amount must be non-negative");
        }
        return new OrderOutput(
                input.sourceKey(),
                input.tenantId(),
                input.transactionId(),
                input.grossAmount().setScale(2, RoundingMode.HALF_UP));
    };
}
~~~

**Source key không được dựa duy nhất vào transaction ID** vì chính ID đó có thể bị thiếu. Nên tạo source key từ snapshot/manifest và record ordinal đáng tin trước khi process. Processor giữ khóa này trong output để có thể truy vết ngay cả khi lỗi xảy ra ở writer.

## 9. Ví dụ Java: SkipListener ghi quarantine

~~~java
final class DeadLetterSkipListener
        implements SkipListener<OrderInput, OrderOutput> {

    private final JdbcTemplate jdbc;
    private final String batchKey;
    private final String snapshotId;
    private final String sourceId;

    DeadLetterSkipListener(JdbcTemplate jdbc, String batchKey,
                           String snapshotId, String sourceId) {
        this.jdbc = jdbc;
        this.batchKey = batchKey;
        this.snapshotId = snapshotId;
        this.sourceId = sourceId;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        if (!(error instanceof FlatFileParseException parse)
                || parse.getLineNumber() <= 0) {
            throw new IllegalStateException(
                    "Cannot identify skipped source record", error);
        }
        // Chỉ đúng nếu reader mapping line -> record ổn định.
        String key = sourceId + ":line:" + parse.getLineNumber();
        quarantine(key, "READ", null,
               "CSV_PARSE_ERROR", "Cannot parse source record");
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable error) {
        quarantine(item.sourceKey(), "PROCESS", item.tenantId(),
               reason(error), "Business validation rejected item");
    }

    @Override
    public void onSkipInWrite(OrderOutput item, Throwable error) {
        quarantine(item.sourceKey(), "WRITE", item.tenantId(),
               reason(error), "Write validation rejected item");
    }

    private String reason(Throwable error) {
        if (error instanceof InvalidRecordException invalid) {
            return invalid.reasonCode();
        }
        throw new IllegalStateException(
                "Unexpected non-business skip", error);
    }

    private void quarantine(String key, String stage, String tenant,
                        String reason, String safeSummary) {
        if (key == null || key.isBlank()) {
            throw new IllegalStateException("Missing stable source key");
        }
        jdbc.update("""
                INSERT INTO dead_letter_record(
                    batch_key, source_key, failure_stage,
                    snapshot_id, source_ref, tenant_id,
                    reason_code, reason_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (batch_key, source_key, failure_stage)
                DO NOTHING
                """,
                batchKey, key, stage, snapshotId, sourceId,
                tenant, reason, safeSummary);
    }
}
~~~

**Điều kiện của ví dụ:** `batchKey`, `snapshotId`, `sourceId` phải cố định; `JdbcTemplate` tham gia đúng transaction của worker nếu cần commit/rollback cùng output. `FlatFileParseException.getLineNumber()` chỉ được dùng nếu mapping vị trí nguồn ổn định, kể cả với CSV multiline. `DO NOTHING` phục vụ dedup nhưng chưa giải quyết **duplicate khác reason/value**; phần production cần kiểm tra conflict hoặc ghi audit history riêng. Nếu không xác định được source record, ví dụ cố tình fail thay vì tạo khóa random.

### Vì sao không ghi nguyên error.getMessage()?

Exception có thể chứa raw payload, SQL values, thông tin khách hàng hoặc credentials. Lưu **reason code thuộc allowlist** và summary an toàn; raw data chỉ nằm ở vùng kiểm soát quyền, mã hóa và retention rõ ràng.

## 10. Fault-tolerant step chỉ skip lỗi được phê duyệt

~~~java
@Bean
@StepScope
SkipListener<OrderInput, OrderOutput> deadLetterSkipListener(
        JdbcTemplate jdbc,
        @Value("#{jobParameters['batchKey']}") String batchKey,
        @Value("#{jobParameters['snapshotId']}") String snapshotId,
        @Value("#{stepExecutionContext['sourceId']}") String sourceId) {
    return new DeadLetterSkipListener(
            jdbc, batchKey, snapshotId, sourceId);
}

@Bean
Step importOrderStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer,
        SkipListener<OrderInput, OrderOutput> deadLetterListener) {
    return new StepBuilder("importOrderStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidRecordException.class)
            .skipLimit(30)
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .listener(deadLetterListener)
            .build();
}
~~~

Đây là bộ khung Spring Batch 5.x/Java 17+; cần bean reader/writer, imports và transaction manager đúng datasource. `sourceId` thuộc `StepExecutionContext` nên phải được cung cấp khi partition được tạo. Nếu single step không có sourceId, phải truyền từ JobParameters hoặc reader metadata, không để null dẫn đến khóa cách ly sai.

`skipLimit(30)` là **giới hạn skip của một StepExecution**, áp dụng cho tổng read/process/write skip. Khi job có nhiều partition, mỗi worker StepExecution có hạn mức riêng; **không tự động là giới hạn 30 lỗi cho toàn JobExecution**. Số lượng được phép skip toàn batch cần quality gate tổng hợp.

## 11. Read skip: khi không có item

Ví dụ:

~~~text
snapshot=file-2026-11-26-v1
line 1: transaction_id,tenant_id,amount
line 2: tx-001,tenant-a,100.00
line 3: tx-002,tenant-b,INVALID
line 4: tx-003,tenant-a,200.00
~~~

Nếu reader báo `FlatFileParseException` ở line 3, listener có thể lưu source key dựa trên **file snapshot + line number**. Tuy nhiên, file có newline bên trong dấu ngoặc kép hoặc custom `RecordSeparatorPolicy` có thể làm line position khác record ordinal. Với workload cần replay tự động, cách chắc chắn hơn là **stage record envelope với record ID ổn định trước bước parse nghiệp vụ**.

**Không** tạo `UUID.randomUUID()` làm source key trong listener: cùng record sẽ tạo nhiều quarantine rows sau rollback/restart. UUID phù hợp cho event audit riêng, không thay thế logical record identity.

## 12. Process skip và filter khác nhau

Ở processor, input có thể parse hợp lệ nhưng vi phạm nghiệp vụ, ví dụ amount âm. Khi `InvalidRecordException` được skip, `onSkipInProcess(item,error)` có source key và tenant đã được xác minh để cách ly.

Ngược lại, nếu `ItemProcessor.process` trả `null` thì Spring Batch xem đó là **filter item**, không mặc định tăng skip count hay gọi SkipListener. Một record có trạng thái `CANCELLED` và được loại khỏi báo cáo theo chính sách có thể là **filter hợp lệ**, không phải dead-letter. Hãy phân biệt trong hợp đồng đối soát:

~~~text
Input snapshot
    = processed + approved filtered + quarantined
      + deferred by explicit policy (nếu cho phép)
~~~

Không cho processor trả null ở mọi exception rồi gọi đó là “resilient”: như vậy có thể mất lý do lỗi, thiếu skip counter và làm batch báo success với dữ liệu không được giải trình.

## 13. Write skip khó hơn process skip

Một `ItemWriter` có thể ghi cả chunk 200 items bằng JDBC batch. Nếu DB ném exception ở mức batch, không phải lúc nào biết ngay **item cụ thể** gây lỗi. Trong fault-tolerant step, Spring Batch có thể rollback, retry và cô lập item bị lỗi theo chính sách đã cấu hình; do đó:

- Đừng mặc định một lần `onWriteError` nghĩa là **toàn bộ chunk** phải vào dead-letter.
- Đừng mặc định mọi lỗi writer là **lỗi dữ liệu**. DB timeout, connection loss, deadlock thường cần retry hoặc fail, không skip.
- Writer phải **replay-safe** trong những lần thử lại; side effect ngoài transaction có thể bị lặp.
- `onSkipInWrite` phải nhận output item vẫn mang **source key** ổn định.
- Nếu không thể xác định lỗi cho **một record**, hãy fail thay vì đoán record cuối cùng là thủ phạm.

Ví dụ không được skip:

~~~text
Writer ghi 200 giao dịch.
Database connection pool cạn, gây timeout.
Mọi item đều hợp lệ.

Sai: skip(SQLException.class), coi hàng loạt item là bad data.
Đúng: retry giới hạn/backoff, sau đó fail nếu hạ tầng chưa phục hồi.
~~~

Ví dụ có thể skip: writer kiểm tra quy tắc tài khoản và ném `InvalidRecordException("ACCOUNT_BLOCKED")` cho một item xác định, rollback/retry logic được chứng minh an toàn, và business policy cho phép cách ly item ấy.

## 14. Ghi quarantine phải nhất quán với chunk commit

~~~mermaid
sequenceDiagram
    participant B as Spring Batch Step
    participant D as Business DB
    participant Q as Quarantine table
    B->>D: BEGIN chunk transaction
    B->>B: Process và xác định record được skip
    B->>D: Write valid records
    B->>Q: SkipListener INSERT dead-letter
    Note over D,Q: Atomic nếu cùng DB resource/transaction
    B->>D: COMMIT hoặc ROLLBACK
~~~

Nếu business output và quarantine nằm **trong cùng PostgreSQL datasource**, cùng Spring-managed transaction được writer và listener thực sự tham gia, có thể thiết kế để:

1. Những item tốt của chunk và dead-letter của item đã skip commit **cùng nhau**.
2. Nếu transaction rollback, các write output và quarantine **trong transaction ấy** đều rollback.
3. Khi transaction chưa commit, `JdbcTemplate.update()` thành công **không** phải bằng chứng dead-letter đã bền vững.

Nếu quarantine ghi sang **DB khác**, file, HTTP API hay broker, chúng **không** tự rollback cùng chunk. Khi đó cần outbox/reconciliation hoặc hợp đồng xử lý từng phần rõ.

**Hai tình huống phải thử:**

- **Quarantine insert lỗi trước commit:** nếu lưu dead-letter là yêu cầu bắt buộc, listener cần báo lỗi; step không được tự coi skip là hoàn tất. Có rollback đồng bộ hay không phụ thuộc transaction resources.
- **Chunk đã commit, manager chưa nhận reply:** worker hoặc manager có thể replay item. Business writer **và** quarantine writer phải dùng khóa ổn định và idempotency.

Không viết `catch(Exception e) { log.warn(...); }` quanh quarantine insert để rồi tiếp tục báo success; như vậy skip count tăng mà bằng chứng record đã mất.

## 15. Tại sao outbox tốt hơn publish trực tiếp vào broker?

Giả sử callback SkipListener publish thẳng một sự kiện bad-record:

~~~text
T1: Worker xử lý record lỗi.
T2: SkipListener publish bad-record tới broker.
T3: Broker nhận event.
T4: Business DB transaction rollback.

Broker đã có một event cho skip chưa commit.
~~~

Tình huống đối xứng là DB commit nhưng broker publish lỗi. Nếu cần phát sự kiện cho hệ thống xử lý dead-letter, **transactional outbox** là một lựa chọn:

~~~sql
CREATE TABLE bad_record_outbox (
    event_id      VARCHAR(200) PRIMARY KEY,
    batch_key     VARCHAR(100) NOT NULL,
    source_key    VARCHAR(240) NOT NULL,
    failure_stage VARCHAR(16) NOT NULL,
    payload       JSONB NOT NULL,
    state         VARCHAR(20) NOT NULL DEFAULT 'NEW',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong cùng DB transaction:

~~~text
Ghi business output được phép commit.
Ghi dead_letter_record.
Ghi bad_record_outbox với eventId ổn định.
COMMIT.
~~~

Publisher độc lập gửi các outbox events khi broker sẵn sàng. Nếu publish xong nhưng crash trước khi mark `SENT`, cùng event có thể **được publish lại**; consumer phải dedup theo `eventId`. Một event ID phù hợp khi chỉ có một sự kiện cách ly per logical failure là bộ `(batchKey, sourceKey, failureStage, "QUARANTINED")` được chuẩn hóa.

**Không thay payload `ChunkResponse` của Spring Batch Integration bằng một JSON `{"status":"SUCCESS"}` chỉ để chuyển dead-letter event.** Remote chunking có protocol request/reply riêng, trong khi bad-record event là một luồng nghiệp vụ khác.

## 16. Skip limit per StepExecution và budget toàn job

Giả sử có 20 partition, mỗi worker step cấu hình `skipLimit(30)`. Nếu mỗi partition gặp 20 lỗi, từng StepExecution đều nằm dưới mức 30 nhưng **toàn job có 400 record bị skip**. Không có global skip budget 30 chỉ nhờ một tham số trên worker step.

Một quality gate sau các worker có thể đo:

~~~sql
SELECT failure_stage, reason_code, COUNT(*) AS quarantined
FROM dead_letter_record
WHERE batch_key = :batchKey
  AND status IN ('PENDING', 'IN_REVIEW', 'REJECTED')
GROUP BY failure_stage, reason_code;
~~~

Một hợp đồng ví dụ:

~~~text
Expected records: 1,000,000
Tổng quarantine tối đa: 100 records.
Không được có CROSS_TENANT, BALANCE_MISMATCH.
Không có source key ở trạng thái chưa giải trình.
Không còn worker ghi dữ liệu trước validation.
Chỉ publish batch khi toàn bộ điều kiện đều đạt.
~~~

**Không chỉ dùng COUNT(*)**: một item có thể có nhiều failure stages hoặc trạng thái recovery khác nhau, trong khi một item khác bị thiếu. Nên đối chiếu theo **tập source keys**, quy tắc approved filters, outcomes của StepExecution và snapshot.

Nếu cần fail sớm khi toàn job vượt ngưỡng, cần coordinator/global counter **bền vững, an toàn concurrency**. Các worker đang chạy vẫn có thể commit thêm chunk trước khi tín hiệu dừng lan tới; vì vậy **validation trước publication** dễ kiểm chứng hơn một biến đếm static in-memory.

## 17. Retry, restart và redelivery

~~~text
T0: worker P3 đọc record r-72 của snapshot S
T1: processor phát hiện INVALID_AMOUNT
T2: fault-tolerant step quyết định skip
T3: SkipListener ghi dead_letter_record(r-72)
T4: chunk COMMIT
T5: worker crash hoặc mất reply
T6: worker/manager restart cùng JobInstance và snapshot
T7: r-72 có thể xuất hiện lại do checkpoint/replay
T8: INSERT quarantine gặp unique key -> không tạo row thứ hai
~~~

Các bất biến:

1. `batchKey`, snapshot và identifying JobParameters giữ nguyên khi **restart cùng JobInstance**.
2. Source record key và partition mapping không thay đổi.
3. Business output writer và quarantine writer đều replay-safe.
4. Nếu record đã được sửa, phải tạo correction/version rõ ràng, không lén thay snapshot cũ.
5. Nếu broker redeliver một `ChunkRequest`, một message có thể chứa nhiều items; business idempotency vẫn cần áp dụng **per item**.

**Không dùng broker message ID làm khóa dead-letter record**, vì một logical input có thể xuất hiện trong request mới hoặc message redeliver với identity transport khác. Nếu item đã được xử lý thành công nhưng reply bị mất, retry phải kiểm tra business output và phản hồi theo contract chứ không đưa item tốt vào dead-letter.

## 18. Multi-threaded step, partitioning và tenant isolation

Với nhiều worker, một record có thể đi vào hai partition nếu thuật toán chia dữ liệu sai. `ConcurrentHashMap` và Java `synchronized` chỉ bảo vệ state **trong một JVM**, không thay thế unique constraint ở database chung.

**Tenant isolation phải áp dụng cho cả quarantine:**

~~~text
tenant-a / transaction-42
tenant-b / transaction-42
~~~

Chỉ `transaction-42` không đủ làm khóa nếu cùng ID có thể lặp giữa hai tenant. Dùng source key unique toàn batch, hoặc composite key có tenant namespace. Khi lỗi parse khiến chưa biết tenant, chỉ ghi tenant khi xác minh được từ manifest/nguồn đáng tin cậy; đừng tự gán một tenant mặc định.

### Nên tránh mutable singleton

~~~java
class UnsafeDeadLetterWriter {
    private String currentTenant; // Dễ bị worker khác ghi đè.
}
~~~

Thay bằng tham số/record immutable, `@StepScope` cho state từng StepExecution khi phù hợp, hoặc repository API yêu cầu tenant ID rõ ràng. Reader/writer chung phải thread-safe; `@StepScope` không tự bảo vệ những singleton services khác.

## 19. Recovery: sửa một record mà không phá batch đã công bố

Dead-letter là **đầu vào cho quy trình sửa**, không chỉ là một bảng để xem lỗi. Một workflow nên có:

1. **Triaging:** phân loại source, tenant, reason code, độ nghiêm trọng và khả năng tái hiện.
2. **Xác minh ownership:** người/operator xử lý có quyền truy cập record đó không.
3. **Phục hồi input:** đọc đúng snapshot và raw source được lưu an toàn; xác định nội dung sửa.
4. **Version hóa:** tạo `repairBatchKey`/correction version mới, không sửa snapshot của JobInstance cũ.
5. **Claim công việc:** tránh hai recovery workers cùng xử lý record, dùng state/lease/fencing khi cần.
6. **Replay:** validate lại và ghi output idempotent; không gọi side effect không thể đảo ngược hai lần.
7. **Đánh dấu recovery:** chỉ chuyển sang `REPROCESSED` sau khi transaction chứa effect thực sự commit.
8. **Đối soát và công bố:** nếu batch gốc đã PUBLISHED, dùng adjustment/correction event hoặc batch mới theo hợp đồng báo cáo.

Một audit table có thể lưu tiến trình:

~~~sql
CREATE TABLE dead_letter_recovery_event (
    recovery_id      VARCHAR(160) PRIMARY KEY,
    batch_key        VARCHAR(100) NOT NULL,
    source_key       VARCHAR(240) NOT NULL,
    failure_stage    VARCHAR(16) NOT NULL,
    repair_batch_key VARCHAR(120),
    action           VARCHAR(40) NOT NULL,
    actor_id         VARCHAR(120),
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nếu nguồn sửa có giá trị khác version ban đầu, record recovery không còn là replay thuần túy của cùng snapshot. Phải giữ **nguồn gốc và phiên bản sửa** để sau này đối soát/rollback nghiệp vụ nếu cần.

## 20. Claim một record để nhiều recovery workers không giẫm nhau

Một pattern PostgreSQL là `FOR UPDATE SKIP LOCKED`:

~~~sql
BEGIN;

SELECT batch_key, source_key, failure_stage
FROM dead_letter_record
WHERE status = 'PENDING'
ORDER BY first_seen_at, source_key
FOR UPDATE SKIP LOCKED
LIMIT 100;

-- Trong cùng transaction, chuyển những rows đã chọn
-- sang IN_REVIEW, đồng thời ghi owner/lease nếu cần.
COMMIT;
~~~

**Chú ý:** row lock chỉ tồn tại **đến cuối transaction**. Nếu chỉ SELECT rồi COMMIT mà không cập nhật state/lease một cách bền vững, worker thứ hai có thể claim lại ngay. Mẫu trên là minh họa, chưa phải implementation recovery hoàn chỉnh.

Recovery phải xử lý lease hết hạn, worker cũ vẫn chạy, lỗi sau khi business effect commit nhưng trước khi mark `REPROCESSED`. **Idempotency ở sink** là phòng vệ cuối cùng khi có duplicate claim/redelivery.

## 21. Không được mất dead-letter khi storage lỗi

| Tình huống | Nguy cơ | Cách bảo vệ |
| --- | --- | --- |
| Quarantine DB không truy cập được | Skip thành công nhưng không lưu dấu vết | Fail/rollback khi dead-letter bắt buộc |
| Quarantine ở DB khác business DB | Hai nơi commit độc lập | Outbox hoặc reconciliation |
| `ON CONFLICT DO NOTHING` gặp reason khác | Che lỗi source key hoặc snapshot | Verify existing row/audit conflict |
| File reject hết dung lượng | Không ghi được record lỗi | Alert/backpressure/fail, không silently drop |
| Retention dọn quá sớm | Không thể replay hoặc điều tra | Retention/backup phù hợp SLA |
| PII trong raw error | Lộ thông tin khách hàng | Sanitization, mã hóa, ACL và audit access |
| Repair crash sau output commit | State quarantine chưa đổi | Idempotent replay và reconciliation |

Nếu policy cho phép bỏ record nhưng **bắt buộc phải có bằng chứng**, mất khả năng ghi quarantine là **sự cố của job**, không nên được chuyển thành một warning rồi tiếp tục.

## 22. Đối soát đầu vào, output, filter và quarantine

Mỗi source record cần một **trạng thái cuối có giải trình**:

~~~text
Expected input snapshot
  = processed
  + approved filtered
  + quarantined
  + intentionally deferred (chỉ khi hợp đồng cho phép)

Không được có source key vừa processed vừa PENDING quarantine
trừ khi có protocol recovery giải thích rõ trạng thái chuyển tiếp.
~~~

Ví dụ SQL (giả sử `source_record`, `normalized_order` và `filtered_record` chứa `batch_key, source_key`):

~~~sql
SELECT s.source_key
FROM source_record AS s
LEFT JOIN normalized_order AS o
  ON o.batch_key = s.batch_key
 AND o.source_key = s.source_key
LEFT JOIN filtered_record AS f
  ON f.batch_key = s.batch_key
 AND f.source_key = s.source_key
LEFT JOIN dead_letter_record AS d
  ON d.batch_key = s.batch_key
 AND d.source_key = s.source_key
 AND d.status IN ('PENDING','IN_REVIEW','REJECTED','WAIVED')
WHERE s.batch_key = :batchKey
  AND o.source_key IS NULL
  AND f.source_key IS NULL
  AND d.source_key IS NULL;
~~~

Đây là một phép kiểm **coverage**, chưa chứng minh tính loại trừ trạng thái hoặc đúng giá trị. Cần thêm truy vấn tìm **duplicate states**, output không thuộc snapshot, result khác giá trị mong đợi và records đã recovery/published. Nếu input hợp lệ được filter theo policy, phải lưu bằng chứng filter tương ứng.

**COUNT(*) có thể đánh lừa:** input 1.000, output 990, quarantine 10 nhưng một record xuất hiện hai lần và record khác bị thiếu. Chỉ đối soát **tập business/source keys** mới thấy lỗi.

## 23. Dead-letter trong remote chunking và remote partitioning

**Remote chunking:** manager giữ `ItemReader`, gửi `ChunkRequest` gồm nhiều items; worker process/write và trả `ChunkResponse`. Một lỗi deserialize cả request có thể đưa **message** vào broker DLQ, còn một item business-invalid cần record quarantine nếu fault-tolerant worker flow cho phép skip theo contract. Hai đối tượng cách ly có **granularity khác nhau**.

**Remote partitioning:** mỗi worker StepExecution có reader và checkpoint riêng; skip count và listener ở worker. Quarantine store cần được các JVM dùng một cách nhất quán hoặc tổng hợp kết quả với hợp đồng rõ. `skipLimit` của mỗi worker không là quality gate toàn job.

### Ranh giới ACK, DB commit và reply

~~~text
Worker nhận request C17.
Worker commit business output và quarantine.
Worker chết trước broker ACK/reply.
Broker redeliver C17 hoặc manager replay sau timeout.

Output và quarantine không được nhân đôi.
Manager phải nhận outcome đúng protocol, không fake SUCCESS.
~~~

Broker DLQ không chứng minh record dữ liệu xấu; có thể là payload incompatibility, lỗi routing hoặc hạ tầng. Một message nằm trong DLQ mà manager vẫn đang chờ reply cần được điều tra, không được silently mark chunk COMPLETED.

## 24. Bảo mật, quyền tenant và retention

Record lỗi thường chưa qua validation, dễ chứa dữ liệu nhạy cảm hoặc payload không tin cậy. Các biện pháp:

- Chỉ lưu metadata tối thiểu; raw input cần storage riêng có encryption và retention.
- Dùng reason codes thuộc allowlist, tránh `error.getMessage()` chứa raw SQL/PII.
- Hạn chế quyền SELECT/UPDATE quarantine theo tenant/domain và vai trò vận hành.
- Không đặt credentials hoặc signed URLs trong source ref, log hay broker header.
- Kiểm tra dữ liệu nguồn đã sửa trước replay, tránh parser/deserializer không an toàn.
- Audit mọi hành động `WAIVED`, `REPROCESSED` và thay đổi policy.
- Không dùng source key/transaction ID làm metric tags với cardinality cực lớn.
- Có chính sách xóa dữ liệu sau hết SLA, backup/restore và tuân thủ yêu cầu pháp lý.

Nếu dùng hash của nội dung nhạy cảm, hash thuần vẫn có thể bị đoán khi miền giá trị nhỏ; cân nhắc HMAC hoặc chỉ lưu tham chiếu theo threat model.

## 25. Dashboard và chỉ số chất lượng

| Metric | Câu hỏi | Dấu hiệu cảnh báo |
| --- | --- | --- |
| Read/process/write skip count | Lỗi phát sinh ở đâu? | Đột biến theo stage |
| Pending quarantine count | Bao nhiêu record chưa review? | Vượt policy/quota |
| Dead-letter oldest age | Record chờ lâu nhất bao nhiêu? | Vượt SLA recovery |
| Skip ratio theo tenant/source | Nguồn nào giảm chất lượng? | Một tenant/file bất thường |
| Quarantine insert failure | Storage có khỏe không? | **Bất kỳ lỗi ngoài dự kiến** |
| Duplicate key/conflict | Retry hợp lệ hay nguồn không ổn định? | Same key khác content |
| Recovery throughput | Sửa kịp tốc độ phát sinh lỗi? | Backlog và age tăng |
| Reconciliation mismatches | Có record mất, trùng, sai value? | Không publish batch |
| Job/StepExecution status | Worker nào FAILED/UNKNOWN? | Retry/skip budget vượt |
| Broker DLQ/reply timeout | Message-level failure có ảnh hưởng? | DLQ tăng, request không có outcome |

Giữ correlation/source key trong log/tracing có quyền truy cập và retention, không gắn mỗi source key thành một time series metric riêng.

## 26. Unit test: phân loại reason và dedup

~~~java
@Test
void invalidAmountIsClassifiedForSkip() throws Exception {
    ItemProcessor<OrderInput, OrderOutput> processor =
            validateAndNormalize();

    OrderInput bad = new OrderInput(
            "snap-1/file-1/record-42",
            "tenant-a", "tx-42", new BigDecimal("-10.00"));

    InvalidRecordException ex = assertThrows(
            InvalidRecordException.class,
            () -> processor.process(bad));

    assertEquals("INVALID_AMOUNT", ex.reasonCode());
}

@Test
void duplicateSkippedRecordCreatesOneQuarantineRow() {
    var listener = new DeadLetterSkipListener(
            jdbcTemplate, "batch-1", "snapshot-1", "file-1");
    var bad = new OrderInput(
            "snapshot-1/file-1/record-7",
            "tenant-a", "tx-7", new BigDecimal("-1.00"));
    var error = new InvalidRecordException(
            "INVALID_AMOUNT", "Amount must be non-negative");

    listener.onSkipInProcess(bad, error);
    listener.onSkipInProcess(bad, error);

    Integer count = jdbcTemplate.queryForObject("""
            SELECT COUNT(*)
            FROM dead_letter_record
            WHERE batch_key = 'batch-1'
              AND source_key = 'snapshot-1/file-1/record-7'
              AND failure_stage = 'PROCESS'
            """, Integer.class);
    assertEquals(1, count);
}
~~~

Test trên cần fixture DB có schema, connection và cleanup phù hợp. Gọi listener trực tiếp chỉ chứng minh **logic SQL/idempotency**, chưa chứng minh Spring Batch gọi đúng callback trước commit hoặc rollback cùng chunk. Phải có integration test toàn step.

## 27. Integration test cho read/process/write skip

Chuẩn bị 100 input records bất biến, gồm 2 malformed, 3 vi phạm business rule và 95 hợp lệ:

1. **Read skip:** tạo `FlatFileParseException` có source position; verify 2 rows stage READ và raw data không lộ.
2. **Process skip:** processor ném `InvalidRecordException` với 3 records; verify 3 rows stage PROCESS và 95 outputs.
3. **Write skip:** tạo lỗi write **per item** thuộc skip policy trong test riêng; verify rollback/retry và `onSkipInWrite` đúng item.
4. **Skip limit:** thêm lỗi thứ sáu với `skipLimit(5)` trong **JobInstance test tách biệt**; step phải fail khi vượt ngưỡng.
5. **Transient DB:** tiêm timeout tạm thời; bước retry không lưu dead-letter cho item đã xử lý thành công.
6. **Quarantine failure:** làm insert dead-letter thất bại; verify không báo completion giả và rollback theo transaction contract.
7. **Crash/restart:** kill worker sau một chunk commit; restart cùng JobInstance/snapshot, verify không trùng output hoặc quarantine.
8. **Partitioning:** nhiều StepExecution dưới hạn mức riêng nhưng tổng toàn job vượt; quality gate phải chặn PUBLISHED.

### Kiểm thử ranh giới commit bằng latch

~~~java
final class DeadLetterCommitProbe {
    final CountDownLatch listenerCalled =
            new CountDownLatch(1);
    final CountDownLatch allowCommit =
            new CountDownLatch(1);

    void afterQuarantineSqlBeforeCommit()
            throws InterruptedException {
        listenerCalled.countDown();
        if (!allowCommit.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test timeout");
        }
    }
}
~~~

Test runner chờ `listenerCalled`, kiểm tra từ **connection khác** rằng bản ghi chưa commit chưa visible theo isolation đang dùng, rồi chủ động cho commit hoặc throw exception để rollback. Mở latch trong `finally`, luôn đặt timeout. **Listener được gọi không đồng nghĩa transaction đã commit.**

## 28. Failure injection và recovery test

| Kịch bản | Injection | Kết quả mong đợi |
| --- | --- | --- |
| Hai worker skip cùng source record | Duplicate delivery cố ý | Một quarantine row theo unique key |
| Worker commit rồi mất reply | Cắt response sau DB commit | Replay không tạo output/quarantine trùng |
| Partition mapping overlap | Giao cùng source key cho hai partition | Phát hiện ownership conflict |
| Source thay đổi trên restart | Đổi nội dung file snapshot trong test âm | Không quietly replay sai record |
| Hai recovery workers claim cùng record | Bắt đầu đồng thời bằng latch | Lease/claim và business dedup bảo vệ |
| Recovery crash sau output commit | Chưa mark `REPROCESSED` | Retry idempotent, reconcile state |
| Message deserialize failure | ChunkRequest malformed | Broker DLQ khác record quarantine |
| Cross-tenant write | Worker mang tenant mismatch | Fail/alert, không skip theo policy rộng |
| Quarantine storage down | Listener JDBC exception | Batch không báo COMPLETED giả |

**Kiểm thử với broker thật** khi dùng remote chunking/partitioning: `DirectChannel` trong cùng JVM không chứng minh ACK, durability, redelivery và late reply. Tách **kill process thật** khỏi test đơn giản ném exception, vì trạng thái commit/ACK khác nhau.

## 29. Runbook khi dead-letter tăng bất thường

1. **Khoanh vùng:** JobInstance, snapshot, tenant, file/partition, stage và reason code.
2. **Tìm nguồn gốc:** schema CSV hoặc rule version mới đổi, upstream xuất dữ liệu sai, encoding hoặc reference data thay đổi?
3. **Loại trừ lỗi hạ tầng:** DB timeout, broker restart hoặc credential issue có bị skip nhầm không?
4. **Đối chiếu:** skip counts trong JobRepository so với quarantine rows và input/output/filter source keys.
5. **Kiểm tra ngưỡng:** global bad-record count/ratio, reason codes bị cấm và SLA.
6. **Tạm chặn publication:** dữ liệu chưa đủ/không đúng không được gắn nhãn FINAL.
7. **Sửa nguyên nhân:** validator hoặc nguồn đúng version; không thay snapshot JobInstance đang chạy.
8. **Recovery có kiểm soát:** claim/lease, correction batch, replay idempotent và audit.
9. **Đối soát sau sửa:** đúng key/value/tenant, không có orphan, status dead-letter phù hợp.
10. **Đóng incident:** báo số lỗi, số được waive/reprocess, thời gian recovery và biện pháp phòng tái diễn.

**Không xóa bảng dead-letter, không tăng skipLimit vô hạn và không sửa JobRepository thành COMPLETED** chỉ để dashboard hết đỏ. Một batch có thể “hoàn thành kỹ thuật” nhưng vẫn thiếu dữ liệu quan trọng.

## 30. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| COMPLETED nhưng thiếu record | Không có quality gate | Global budget + coverage reconciliation |
| Dead-letter trùng sau restart | Source key random, thiếu constraint | Stable key + idempotent insert |
| Retry thành công vẫn có quarantine | Ghi tại on*Error thay vì skip decision | Dùng SkipListener đúng pha |
| DB timeout bị coi là dữ liệu xấu | Broad skip policy | Retry/fail theo classifier |
| Parse error không truy vết được | Không lưu snapshot/position | Stable record envelope hoặc reader offset |
| Quarantine commit nhưng chunk rollback | Sink khác transaction | Same DB transaction/outbox |
| Chunk commit thiếu quarantine | Listener nuốt lỗi ghi | Fail khi dead-letter bắt buộc |
| Trùng ID giữa tenant bị gộp | Key thiếu owner scope | Composite/global source identity |
| Repair chạy hai lần | Claim không bền hoặc worker cũ còn chạy | Lease/fencing + idempotent sink |
| Repair thay đổi output đã publish | Thiếu correction version | Adjustment batch/pub policy |
| Broker DLQ count khác skip count | Nhầm message với record | Metrics theo hai cấp |
| Log lộ PII | Lưu raw exception/payload | Sanitize/encrypt/access control |

## 31. Bài thực hành cuối bài

Thiết kế một job có 10.000 source records từ snapshot CSV cố định, chia làm bốn partition. Dữ liệu lỗi được tạo có chủ đích: 3 record sai cấu trúc CSV, 4 thiếu transaction ID, 2 có amount âm, và **một DB timeout tạm thời** ở một chunk khác.

Mục tiêu là **9 record lỗi dữ liệu** được quarantine; DB timeout phải được retry theo chính sách và **không** trở thành bad record. Kiểm thử toàn pipeline, không giả định mục tiêu sẽ tự đạt chỉ vì đã bật fault tolerance.

1. Tạo input snapshot và source key bất biến; quarantine schema có unique constraint.
2. Thiết kế reader báo parse error với vị trí đáng tin cậy.
3. Processor ném `InvalidRecordException` với reason code và giữ source identity.
4. Writer business output idempotent; SkipListener ghi quarantine trong transaction khi phù hợp.
5. Đối soát 9 bad records và tập output/filtered còn lại.
6. Giảm skipLimit để chứng minh step fail khi vượt ngưỡng; thử global quality gate trên bốn partitions.
7. Kill worker sau commit, restart cùng JobInstance và verify không duplicate.
8. Thử recovery record đã sửa qua correction batch, thay đổi status và audit.
9. Nếu dùng broker, test một redelivered ChunkRequest và phân biệt message DLQ với item-level quarantine.
10. Đo throughput, commit/rollback, quarantine insert latency và thời gian chờ recovery.

### Checklist trước production

- [ ] Lỗi được phân loại rõ **skip/retry/fail**; không broad skip exception.
- [ ] Source record key, batch/snapshot, tenant scope và partition mapping ổn định.
- [ ] Read skip có định danh input đáng tin, kể cả multiline records.
- [ ] SkipListener được gắn đúng callback; không coi mọi error callback là skip.
- [ ] Quarantine có unique key, phát hiện duplicate khác nội dung và reason code an toàn.
- [ ] Dead-letter và business output dùng cùng transaction nếu cần atomic; khác resource có outbox/reconcile.
- [ ] Có chính sách khi quarantine write thất bại: không silently drop.
- [ ] Skip budget toàn StepExecution và quality gate toàn JobExecution được phân biệt.
- [ ] Có coverage check từng input key và kiểm tra value, không chỉ COUNT(*).
- [ ] Có review/repair/waive với audit, version, claim/lease và SLA.
- [ ] Không sửa trực tiếp snapshot hay output batch đã published khi replay.
- [ ] Có tenant isolation, PII sanitization, ACL, retention, backup.
- [ ] Có test read/process/write skip, rollback, worker crash, restart và redelivery.
- [ ] Có metric skip stage/reason, pending age, quarantine failure và reconciliation.

**Ghi nhớ:** dead-letter record giúp **không mất dấu bản ghi bị bỏ qua**, nhưng chỉ hữu ích khi gắn với quyết định skip chính xác của Spring Batch, có **source identity ổn định**, lưu **durable và nhất quán với transaction**, và có workflow recovery/đối soát. Trong workload song song hoặc phân tán phải phân biệt **record quarantine** với **broker DLQ**, kiểm soát skip theo ngưỡng toàn batch và bảo vệ replay bằng snapshot bất biến cùng business idempotency.
