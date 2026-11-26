# Đối soát item bị skip trong Spring Batch

> **Chương:** Skip và recovery
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp; học đo nút thắt, bảo đảm thread safety, retry/restart và vận hành job theo tài nguyên thực tế.

**Skip giúp batch tiếp tục khi gặp một bản ghi lỗi được phép bỏ qua, nhưng không tự chứng minh dữ liệu cuối cùng là đúng.** Một job `COMPLETED` có thể vẫn thiếu những bản ghi quan trọng, còn một worker `FAILED` có thể đã commit nhiều kết quả trước đó. **Đối soát item bị skip** là quy trình chứng minh mỗi item đầu vào có một trạng thái nghiệp vụ có thể giải thích, mọi item lỗi có thể truy vết và replay, và không có mất dữ liệu hoặc tác dụng phụ trùng sau retry/restart.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các chỉ số `readSkipCount`, `processSkipCount`, `writeSkipCount`, `filterCount`, `readCount` và `writeCount` với số **business record duy nhất**.
2. Xây dựng bất biến đối soát theo **snapshot nguồn + source key + trạng thái kết quả**, kể cả lỗi parse chưa tạo được object.
3. Thiết kế quarantine/audit bền vững kết hợp `SkipListener` mà không tạo trùng khi rollback, retry, restart hoặc nhiều partition cùng xử lý.
4. Đối soát bằng SQL giữa source manifest, business output và quarantine; nhận diện item thiếu, trạng thái mâu thuẫn, trùng nghiệp vụ và item chưa xử lý.
5. Tổng hợp số liệu từ các worker `StepExecution` mà không cộng sai qua nhiều `JobExecution` hoặc nhầm kết quả `COMPLETED` với chất lượng dữ liệu đạt.
6. Xây dựng tiêu chí publish gate, runbook khắc phục và kiểm thử fault injection cho workload local/remote.

## 1. Câu hỏi thật sự cần trả lời

Giả sử job nhập 10 triệu đơn hàng, chia thành 16 partition, trong đó mỗi worker có `skipLimit(20)`. Sau khi chạy:

- Một số dòng CSV không parse được và bị skip khi đọc.
- Một số đơn hàng bị `ItemProcessor` từ chối vì sai quy tắc.
- Một số bản ghi đã xử lý không được writer ghi do lỗi riêng từng item.
- Một số item bị processor **filter hợp lệ**, không phải lỗi.
- Một worker lỗi và được restart; broker ở môi trường remote có thể giao lại request.

Các câu hỏi nghiệp vụ **không** được trả lời chỉ bằng `BatchStatus.COMPLETED`:

| Câu hỏi | Nguồn bằng chứng |
| --- | --- |
| Có bao nhiêu bản ghi trong snapshot đầu vào? | Source manifest/snapshot bất biến |
| Bản ghi nào đã tạo kết quả hợp lệ? | Business output/ledger với source identity |
| Bản ghi nào bị loại theo quy tắc hợp lệ? | Filter decision có thể truy vết |
| Bản ghi nào bị skip ở read/process/write? | `SkipListener` + quarantine bền vững |
| Bản ghi nào chưa được xử lý hoặc chưa xác nhận? | Outcome ledger/queue và đối soát thiếu |
| Có item nào vừa được ghi vừa bị đánh dấu skip không? | Kiểm tra trạng thái mâu thuẫn |
| Có bản ghi nào bị ghi hai lần sau replay? | Unique business key, reconciliation tại đích |
| Có lỗi chất lượng vượt chính sách toàn job không? | Tổng item lỗi duy nhất và các ngưỡng nghiệp vụ |

**Nguyên tắc:** Đối soát phải dựa trên **identity của dữ liệu và kết quả bền vững**, còn bộ đếm Spring Batch là tín hiệu kỹ thuật hỗ trợ điều tra.

## 2. Skip, filter, retry và trạng thái xử lý không giống nhau

Trong chunk step:

| Trường hợp | Tín hiệu Batch | Outcome nghiệp vụ cần có |
| --- | --- | --- |
| Reader trả item hợp lệ, writer commit thành công | `readCount` / `writeCount` tùy lifecycle | `APPLIED` hoặc kết quả tương ứng |
| Reader gặp record parse lỗi được cho phép skip | `readSkipCount` | `QUARANTINED` với file/line hoặc source position |
| Processor ném lỗi validation được phép skip | `processSkipCount` | `QUARANTINED` với source key |
| Writer không ghi được item riêng lẻ và được skip | `writeSkipCount` | `QUARANTINED` với source key, phải kiểm tra side effect |
| Processor trả `null` do quy tắc nghiệp vụ | `filterCount` | `FILTERED` nếu yêu cầu đối soát đủ từng item |
| Retry do lỗi tạm thời rồi thành công | Có thể có retry/rollback; không nhất thiết có skip | `APPLIED`, không phải `QUARANTINED` |
| Lỗi khiến step `FAILED` trước khi commit | `BatchStatus.FAILED` và checkpoint tương ứng | `PENDING`/chưa xử lý hoặc trạng thái cần xác minh |
| Đã ghi external API nhưng phản hồi thất lạc | Batch có thể rollback/retry | `UNKNOWN` cho tới khi xác minh với đích |

### Skip count là gì?

`StepExecution` có ba counter:

~~~text
skipCount = readSkipCount + processSkipCount + writeSkipCount
~~~

Trong một `StepExecution`, chúng giúp xác định **giai đoạn và số lượt skip được ghi nhận**. `skipLimit` của fault-tolerant step áp dụng cho tổng skip của execution đó, **không** là ngân sách riêng cho từng callback.

Nhưng đừng suy:

~~~text
Tổng số item lỗi duy nhất toàn job
    = SUM(skipCount của mọi StepExecution qua mọi lần restart)
~~~

Phép cộng trên **có thể đếm trùng** cùng item ở hai attempts và không chỉ ra item nào đã được khắc phục. Một `StepExecution` khác có thể xử lý lại cùng source record sau restart; các metadata lịch sử vẫn tồn tại. Cần dedupe theo source identity và quy tắc phiên bản.

### Vì sao readCount không tự bằng tổng dòng nguồn?

Ở nhiều reader, một record lỗi parse bị ném exception **trước khi tạo ra item trả về**, trong khi `readCount` theo dõi lượt đọc thành công theo semantics của framework. Dòng bị skip ngay tại reader không nhất thiết nằm trong số item đã đọc thành công. Với một số reader, một “item” có thể bao gồm nhiều dòng vật lý; một số pipeline lọc/ghép records. Vì thế:

- Không lấy `readCount` làm số dòng vật lý trong file khi chưa hiểu reader.
- Công thức `readCount + readSkipCount` **chỉ mang tính kiểm tra phụ** cho reader một-record-một-item đã xác minh semantics.
- Cũng không lấy `writeCount` làm số row SQL được insert mới nếu writer có upsert/no-op, aggregate hoặc ghi một-nhiều.

## 3. Định nghĩa bất biến đối soát trước khi triển khai

Một ví dụ đơn giản: **một source record hợp lệ tương ứng tối đa một business output**, và mọi record trong snapshot phải có đúng một **trạng thái kết thúc**.

Ký hiệu:

- `S`: tập source keys của **snapshot cố định**.
- `A`: tập keys đã `APPLIED` và xác nhận ở hệ thống đích.
- `F`: tập keys được `FILTERED` theo quy tắc có chủ đích.
- `Q`: tập keys `QUARANTINED` do skip/lỗi cần sửa.
- `P`: tập keys `PENDING` hoặc `UNKNOWN` chưa có kết luận cuối.
- `M`: tập keys thiếu outcome.

### Bất biến khi job đã kiểm toán hoàn tất

~~~text
S = A ∪ F ∪ Q     (khi không còn pending/unknown)
A ∩ F = ∅
A ∩ Q = ∅
F ∩ Q = ∅
M = ∅
~~~

Nếu job vẫn đang chạy hoặc vừa thất bại:

~~~text
S = A ∪ F ∪ Q ∪ P ∪ M
M có thể chưa rỗng, cần giải thích bằng trạng thái execution.
~~~

Phép so sánh trên yêu cầu các tập đã được định nghĩa từ một **nguồn chân lý có identity ổn định**. Với pipeline có nhiều output cho một input, aggregate, CDC update/delete hoặc một input sinh nhiều bước nghiệp vụ, phải thay bằng **bất biến thích hợp** (ví dụ một outcome cho mỗi operation, quan hệ input→n output, tổng amount/checksum), không áp dụng công thức một-một máy móc.

### Phân biệt trạng thái hiện hành và lịch sử

Sau khi một record lỗi được sửa và replay:

~~~text
Lúc đầu: sourceKey=orders.csv:127  → QUARANTINED
Sau sửa: cùng sourceKey          → APPLIED
~~~

Nếu chỉ có **một trạng thái hiện hành** thì phải chuyển sang `APPLIED` có điều kiện, đồng thời giữ **lịch sử sự cố** ở bảng audit riêng. Xóa dấu vết `QUARANTINED` cũ sẽ khiến việc điều tra “vì sao lượt chạy đầu thiếu dữ liệu?” khó khăn.

Ngược lại, nếu bản ghi nguồn được **sửa thành một phiên bản khác**, cần xác định liệu `sourceVersion` có đổi và việc replay tạo **operation nghiệp vụ mới** hay chỉ hoàn tất operation cũ. Đây là quyết định nghiệp vụ, không phải phép cộng counter.

## 4. Xây dựng source manifest có định danh bền vững

Đối soát chỉ có ý nghĩa khi biết **đầu vào được kỳ vọng**. Nếu chỉ nhìn những item reader đọc thành công, dòng parse lỗi có thể biến mất khỏi phạm vi thống kê.

### Với CSV hoặc file

Một identity đáng dùng:

~~~text
(pipelineId, sourceVersion, fileId, recordNumber)
~~~

Ví dụ:

~~~text
pipelineId    = "orders-import"
sourceVersion = "batch-2026-11-26-v1"
fileId        = "orders-region-A.csv"
recordNumber  = 127
sourceKey     = "orders-region-A.csv:127"
~~~

`recordNumber` phải có semantics đã thỏa thuận: dòng vật lý, logical record (nhiều dòng CSV quoted) hay row index do parser định nghĩa. `FlatFileParseException.getLineNumber()` thường cho vị trí dòng trong reader, nhưng hãy kiểm tra với input nhiều dòng/định dạng custom. Không lấy `ThreadLocal currentLine` từ worker khác làm identity.

### Với database

Có thể dùng:

~~~text
(pipelineId, snapshotWatermark, tenantId, primaryKey)
~~~

Snapshot/watermark cần cố định để cùng `sourceKey` trỏ **cùng bản ghi logic** qua restart. Nếu nguồn tiếp tục thêm/sửa/xóa dữ liệu, phải dùng snapshot isolation, manifest được materialize hoặc một quy tắc CDC/version rõ ràng.

### Với message broker

Các lựa chọn thường là:

- Business event ID được producer cấp **trước lần publish đầu**;
- Hoặc `topic + partition + offset` nếu danh tính thực sự là record trong log và retention/replay được kiểm soát;
- Kèm tenant/source namespace khi cần.

**Broker delivery tag**, `JobExecutionId` và `StepExecutionId` không phải source identity ổn định xuyên restart. Chúng hữu ích cho tracing/attempt, không thay thế business key.

## 5. Sơ đồ đối soát end-to-end

~~~mermaid
flowchart TB
    M["Source manifest / snapshot"] --> V["Đối soát theo source key"]
    R["Spring Batch<br/>reader → processor → writer"] --> O[("Business output")]
    R --> L["SkipListener"]
    R --> F["Filter decision"]
    L --> Q[("Quarantine / skip audit")]
    F --> U[("Outcome ledger")]
    O --> V
    Q --> V
    U --> V
    V --> C{"Mỗi key có outcome hợp lệ?"}
    C -- "Có, quality gates đạt" --> P["Publish / accept"]
    C -- "Không" --> I["Mismatch report<br/>quarantine / reconcile"]
    I --> X["Sửa lỗi + replay có kiểm soát"]
    X --> V
~~~

Luồng phản ánh **thiết kế nghiệp vụ**. `SkipListener` không tự tạo outcome ledger hoặc chạy đối soát; các bảng, listener, giao dịch và ranh giới publish cần được ứng dụng triển khai.

## 6. Thiết kế bảng manifest và outcome ledger

Dưới đây là **một mô hình minh họa bằng PostgreSQL** cho pipeline một-source-record-một-outcome. Để tránh mất trạng thái lịch sử khi replay, chia thành:

1. `source_manifest`: tập input logic cố định của snapshot.
2. `item_outcome_current`: outcome hiện hành theo source key.
3. `item_issue_history`: lịch sử lỗi/skip theo execution hoặc attempt.
4. Business output table: dữ liệu đích thực tế, có unique operation key riêng.

### 6.1. Manifest nguồn

~~~sql
CREATE TABLE source_manifest (
    pipeline_id       VARCHAR(100) NOT NULL,
    source_version    VARCHAR(160) NOT NULL,
    source_key        VARCHAR(240) NOT NULL,
    tenant_id         VARCHAR(100),
    partition_name    VARCHAR(160),
    source_hash       VARCHAR(128),
    PRIMARY KEY (pipeline_id, source_version, source_key)
);
~~~

Manifest phải được **chốt trước hoặc đồng thời với lúc xử lý** theo một quy tắc nhất quán. Nếu một source record chưa thể parse thành object, manifest vẫn phải có identity vật lý/logical của nó (ví dụ file + record position).

### 6.2. Outcome hiện hành

~~~sql
CREATE TABLE item_outcome_current (
    pipeline_id       VARCHAR(100) NOT NULL,
    source_version    VARCHAR(160) NOT NULL,
    source_key        VARCHAR(240) NOT NULL,
    outcome_status    VARCHAR(24) NOT NULL,
    outcome_reason    VARCHAR(100),
    last_execution_id BIGINT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (pipeline_id, source_version, source_key),
    CONSTRAINT ck_outcome_status CHECK (
        outcome_status IN ('APPLIED','FILTERED',
                           'QUARANTINED','PENDING','UNKNOWN')
    ),
    FOREIGN KEY (pipeline_id, source_version, source_key)
        REFERENCES source_manifest (
            pipeline_id, source_version, source_key)
);
~~~

Một key chỉ có **một trạng thái hiện hành**. Nếu pipeline có nhiều output hoặc nhiều operation từ một input, phải thêm `operation_type` hoặc bảng quan hệ riêng để tránh **false duplicate**.

### 6.3. Lịch sử sự cố

~~~sql
CREATE TABLE item_issue_history (
    issue_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id       VARCHAR(100) NOT NULL,
    source_version    VARCHAR(160) NOT NULL,
    source_key        VARCHAR(240) NOT NULL,
    phase             VARCHAR(16) NOT NULL,
    reason_code       VARCHAR(100) NOT NULL,
    job_execution_id  BIGINT,
    step_execution_id BIGINT,
    partition_name    VARCHAR(160),
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_issue_source
ON item_issue_history (
    pipeline_id, source_version, source_key);
~~~

Bảng lịch sử ở đây cố ý **không dùng source key làm unique**, vì cùng item có thể phát sinh nhiều sự kiện lỗi thực sự ở những lần chạy khác nhau. Nếu audit được gửi theo dạng at-least-once hoặc ghi ra hệ thống ngoài transaction, nên thêm một **event ID/idempotency key** và unique constraint để phân biệt **phát lại cùng sự kiện audit** với **một sự cố mới**.

### Không dùng transaction sai

Nếu business output và outcome nằm **trong cùng DB transaction phù hợp**, có thể commit atomically `APPLIED` cùng dữ liệu đích. Nhưng nếu output là HTTP/API/S3 ở bên ngoài, ghi `APPLIED` vào local DB **không** chứng minh đích đã commit. Khi chưa chắc chắn, giữ `UNKNOWN` và reconciliation từ hệ thống đích.

## 7. Ghi nhận skip bằng SkipListener

Spring Batch cung cấp ba callback:

~~~java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
~~~

| Callback | Có object item không? | Cách xác định source key |
| --- | --- | --- |
| `onSkipInRead` | Không | File ID + line/record position từ exception hoặc reader |
| `onSkipInProcess` | Có input item | Business/source ID của item |
| `onSkipInWrite` | Có output item | Output phải giữ correlation về source ID |

`SkipListener` được dùng để quan sát **item đã được quyết định skip**, không phải tất cả exception phát sinh trong các lần retry. Nếu processor trả `null` vì filter hợp lệ, đó là `filterCount` và **không gọi SkipListener**.

### Ví dụ listener bảo toàn identity

~~~java
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public record InputOrder(String sourceKey, String orderId) {}
public record OutputOrder(String sourceKey, String orderId) {}

public interface QuarantineSink {
    void record(String sourceKey, String phase,
                String reasonCode, String errorType);
}

public final class ReconcilingSkipListener
        implements SkipListener<InputOrder, OutputOrder> {

    private final QuarantineSink sink;
    private final String fileId;

    public ReconcilingSkipListener(
            QuarantineSink sink, String fileId) {
        this.sink = sink;
        this.fileId = fileId;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        if (!(error instanceof FlatFileParseException parse)) {
            // Không ghi nhiều lỗi đọc khác nhau vào một key UNKNOWN.
            throw new IllegalStateException(
                    "Không xác định được read skip source key", error);
        }
        String sourceKey = fileId + ":" + parse.getLineNumber();
        sink.record(sourceKey, "READ",
                "PARSE_ERROR", error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            InputOrder item, Throwable error) {
        sink.record(item.sourceKey(), "PROCESS",
                "INVALID_ORDER", error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(
            OutputOrder item, Throwable error) {
        sink.record(item.sourceKey(), "WRITE",
                "DESTINATION_REJECTED",
                error.getClass().getSimpleName());
    }
}
~~~

Đây là **contract ví dụ**: các class/record `public` cần đặt trong các file Java phù hợp. `QuarantineSink` phải được triển khai với transaction/idempotency và metadata `pipelineId`, `sourceVersion`, `StepExecutionId` trong ứng dụng thật. Các reason code không thể hardcode một mã cho mọi exception nếu nghiệp vụ cần phân loại chi tiết.

### Reader lỗi: đừng giả định có business object

Lỗi parse của CSV có thể không xây được `InputOrder`, vì vậy source key **không thể** phụ thuộc `item.getOrderId()`. Nếu một record nhiều dòng vật lý, hãy định nghĩa rõ file ID + logical record position và kiểm thử format. Để reprocess sau sửa, phải giữ tham chiếu tới **snapshot ban đầu** hoặc vùng quarantine bảo mật.

### StepScope trong partitioning

Nếu listener có `fileId`/`partitionName` theo worker, tạo listener `@StepScope` với late binding:

~~~java
@Bean
@StepScope
SkipListener<InputOrder, OutputOrder> skipListener(
        QuarantineSink sink,
        @Value("#{stepExecutionContext['fileId']}")
        String fileId) {
    return new ReconcilingSkipListener(sink, fileId);
}
~~~

Đoạn này cần `@Bean`, `@StepScope` và `@Value` import theo Spring. `@StepScope` tạo target listener theo **worker StepExecution**, giảm rủi ro dùng nhầm field mutable từ partition khác trong local partitioning. Nó **không** tự làm `QuarantineSink` an toàn trước nhiều worker đồng thời hoặc giải quyết ghi trùng vào database.

Nếu listener hoàn toàn stateless và nhận identity rõ từ item/error, một singleton thread-safe cũng có thể dùng được. Điều cần tránh là một singleton giữ `currentFileId` thay đổi liên tục giữa workers.

## 8. Transaction và idempotency của quarantine

`SkipListener` thường được framework gọi ở giai đoạn gần commit trong fault-tolerant chunk lifecycle, hỗ trợ ghi nhận skip cùng transaction khi hạ tầng cho phép. **Không** vì thế suy ra mọi audit gửi qua HTTP hoặc datasource khác đều nằm trong transaction ấy.

### Crash window minh họa

~~~mermaid
sequenceDiagram
    participant W as Worker chunk
    participant L as SkipListener
    participant Q as Quarantine DB
    participant B as Business DB
    W->>L: onSkipInProcess(item A)
    L->>Q: Ghi event lỗi A
    W->>B: Ghi các item hợp lệ
    Note over Q,B: Commit cùng transaction chỉ khi được cấu hình chung
    W--xW: Crash/rollback trước khi mọi trạng thái hoàn tất
    Note over Q: Nếu Q ngoài transaction, event A có thể đã tồn tại
    W->>L: Retry/restart: item A lại bị skip
    L->>Q: Có thể gửi lại cùng sự kiện
~~~

Yêu cầu tối thiểu:

1. **Stable source key** theo snapshot, không sinh UUID mới cho mỗi callback rồi coi đó là identity của item.
2. **Quarantine upsert/unique key** cho **trạng thái hiện hành**; tránh hai worker tạo hai dòng hiện hành cho cùng source key.
3. **Audit event ID riêng** nếu cần đếm/khử duplicate delivery; không xóa lịch sử sự cố hợp lệ.
4. **Rollback semantics rõ:** nếu sink chung transaction, audit và business write cần commit hoặc rollback phù hợp; nếu không, đối soát phải chịu được eventual consistency.
5. **Fail-closed khi audit bắt buộc:** nếu không thể ghi quarantine đáng tin cậy, đừng âm thầm bỏ qua lỗi audit rồi coi skip là thành công.

### Vì sao `ON CONFLICT DO NOTHING` có thể gây sai?

Giả sử outcome hiện hành đã là `APPLIED` nhưng một worker khác retry và báo `QUARANTINED` cùng source key. Một upsert “last writer wins” có thể ghi đè `APPLIED`; một `DO NOTHING` mù cũng có thể che **xung đột trạng thái**. Phải định nghĩa state transition được phép và kiểm tra output thật:

| Outcome hiện hành | Sự kiện mới | Hành động cần thiết |
| --- | --- | --- |
| Chưa có | `APPLIED` đã xác nhận | Insert `APPLIED` |
| Chưa có | Skip được chấp nhận | Insert `QUARANTINED` |
| `QUARANTINED` | Cùng skip event được giao lại | No-op có audit dedupe |
| `QUARANTINED` | Replay đã sửa và ghi thành công | Chuyển sang `APPLIED` có điều kiện, giữ lịch sử lỗi |
| `APPLIED` | Cùng operation và payload | No-op hợp lệ, không gửi side effect mới |
| `APPLIED` | Skip/error cho cùng source key | Điều tra conflict, không ghi đè mù |
| `UNKNOWN` | Provider xác minh đã commit | Chuyển `APPLIED` theo bằng chứng |
| Bất kỳ | Source version/key khác nghĩa | Phải xác minh identity; không tự gộp |

Nếu xử lý độc lập ở nhiều database/service, cập nhật trạng thái cần cơ chế concurrency control như unique constraint, compare-and-set hoặc optimistic locking tùy thiết kế.

## 9. Filter hợp lệ cũng cần dấu vết nếu muốn đối soát đủ

`ItemProcessor.process(item)` trả `null` được Spring Batch tính là **filter**, không phải skip. `SkipListener` **không** được gọi.

~~~java
@Override
public OutputOrder process(InputOrder item) {
    if (isCancelled(item)) {
        return null; // Filter hợp lệ, không có skip callback.
    }
    return transform(item);
}
~~~

Nếu nghiệp vụ cần đối soát **từng source key**, phải có cách ghi nhận filter:

- Ghi filter decision vào ledger bằng một bước riêng sau xử lý;
- Dùng `ItemProcessListener` để quan sát quyết định (nhưng cần giải quyết rollback/retry và durability);
- Hoặc thay mô hình `null` bằng một **decision envelope** (`APPLY` / `FILTER`) cho writer ghi outcome bền vững, rồi writer chỉ áp dụng business effect khi `APPLY`.

### Decision envelope minh họa

~~~java
public enum DecisionKind { APPLY, FILTER }

public record OrderDecision(
        String sourceKey,
        DecisionKind kind,
        OutputOrder output,
        String reasonCode) {}

public final class OrderDecisionProcessor
        implements ItemProcessor<InputOrder, OrderDecision> {

    @Override
    public OrderDecision process(InputOrder input) {
        if (isCancelled(input)) {
            return new OrderDecision(
                    input.sourceKey(),
                    DecisionKind.FILTER, null, "CANCELLED");
        }
        return new OrderDecision(
                input.sourceKey(),
                DecisionKind.APPLY,
                transform(input), null);
    }
}
~~~

`isCancelled` và `transform` là logic nghiệp vụ minh họa, cần triển khai trong dự án. Writer của `OrderDecision` ghi `FILTERED` hoặc ghi business output + `APPLIED` **trong transaction phù hợp**. Vì processor **không trả null**, framework sẽ **không tăng `filterCount`** cho decision `FILTER`; nên dùng metric/nghiệp vụ `filtered_outcome_count` riêng, tránh so sánh sai với `filterCount` mặc định.

**Lưu ý:** Nếu một record được filter rồi có một bước xử lý khác phát sinh output, mô hình trạng thái phải thể hiện rõ scope của kết quả (từng step/operation), tránh coi filter ở bước này là không có kết quả ở toàn pipeline.

## 10. SQL đối soát manifest, output và quarantine

Giả sử đã có `source_manifest` và `item_outcome_current` theo schema ở trên, cùng bảng business output `orders_output` với:

~~~sql
-- Giả định để minh họa các truy vấn đối soát:
-- orders_output (
--     pipeline_id, source_version, source_key,
--     tenant_id, order_id, amount_minor, ...)
~~~

Các truy vấn cần cố định `pipeline_id`, `source_version` và, khi thích hợp, tenant/snapshot/partition. Đừng gộp nhiều lần chạy của những snapshot khác nhau vào một tổng.

### 10.1. Tìm source item chưa có outcome

~~~sql
SELECT s.pipeline_id, s.source_version, s.source_key
FROM source_manifest s
LEFT JOIN item_outcome_current o
  ON o.pipeline_id = s.pipeline_id
 AND o.source_version = s.source_version
 AND o.source_key = s.source_key
WHERE s.pipeline_id = :pipelineId
  AND s.source_version = :sourceVersion
  AND o.source_key IS NULL
ORDER BY s.source_key;
~~~

Nếu job đã hoàn tất mọi worker, kết quả nên rỗng đối với pipeline có một outcome bắt buộc cho mỗi input. Nếu job đang chạy, nhiều source keys còn chưa có outcome là bình thường; cần đối chiếu tiến độ/partition state để kết luận.

### 10.2. Đếm outcome hiện hành theo loại

~~~sql
SELECT o.outcome_status, COUNT(*) AS item_count
FROM item_outcome_current o
WHERE o.pipeline_id = :pipelineId
  AND o.source_version = :sourceVersion
GROUP BY o.outcome_status
ORDER BY o.outcome_status;
~~~

Đây là số **source keys duy nhất đang ở trạng thái hiện hành**, không phải số skip callbacks hay tổng lỗi trong lịch sử.

### 10.3. Tìm outcome APPLIED nhưng thiếu business output

~~~sql
SELECT o.source_key
FROM item_outcome_current o
LEFT JOIN orders_output b
  ON b.pipeline_id = o.pipeline_id
 AND b.source_version = o.source_version
 AND b.source_key = o.source_key
WHERE o.pipeline_id = :pipelineId
  AND o.source_version = :sourceVersion
  AND o.outcome_status = 'APPLIED'
  AND b.source_key IS NULL;
~~~

Đây là tín hiệu **nguy hiểm**: ledger nói applied nhưng business row chưa thấy. Có thể do transaction/outbox chưa đồng bộ, dữ liệu ở đích khác hoặc logic ghi outcome trước commit. Với hệ thống external, cần tra trạng thái tại **đích có thẩm quyền**, không tự sửa `APPLIED`/`UNKNOWN` theo cảm tính.

### 10.4. Tìm business output không thuộc manifest

~~~sql
SELECT b.source_key
FROM orders_output b
LEFT JOIN source_manifest s
  ON s.pipeline_id = b.pipeline_id
 AND s.source_version = b.source_version
 AND s.source_key = b.source_key
WHERE b.pipeline_id = :pipelineId
  AND b.source_version = :sourceVersion
  AND s.source_key IS NULL;
~~~

Output “mồ côi” có thể do worker dùng sai snapshot, partition overlap, source ID trộn giữa tenant, hoặc output chưa được gắn identity đúng.

### 10.5. Tìm business output trùng theo operation key

~~~sql
SELECT tenant_id, order_id, COUNT(*) AS row_count
FROM orders_output
WHERE pipeline_id = :pipelineId
  AND source_version = :sourceVersion
GROUP BY tenant_id, order_id
HAVING COUNT(*) > 1;
~~~

Truy vấn này chỉ hợp lý nếu **mỗi tenant/order ID được phép có tối đa một output row trong snapshot**. Nếu order có nhiều dòng chi tiết hoặc nhiều operation hợp lệ, phải đổi nhóm theo **business operation key** đúng. Nên có unique constraint ở đích để chặn duplicate trước khi phải phát hiện bằng báo cáo.

### 10.6. Kiểm tra trạng thái không tương thích

~~~sql
SELECT o.source_key, o.outcome_status
FROM item_outcome_current o
JOIN orders_output b
  ON b.pipeline_id = o.pipeline_id
 AND b.source_version = o.source_version
 AND b.source_key = o.source_key
WHERE o.pipeline_id = :pipelineId
  AND o.source_version = :sourceVersion
  AND o.outcome_status IN ('FILTERED','QUARANTINED');
~~~

Nếu hợp đồng một-input-một-output không cho phép vừa filter/skip vừa applied thì kết quả phải rỗng. Với write skip đã có external effect một phần, dữ liệu có thể thực sự tồn tại dù outcome hiện hành đang `QUARANTINED` — đó là **incident phải reconcile**, không chỉ xóa row cho đẹp số liệu.

## 11. Đối soát bộ đếm trong JobRepository

Trong schema Spring Batch mặc định, `BATCH_STEP_EXECUTION` lưu các counters của từng `StepExecution`, bao gồm manager và workers ở mô hình partitioning.

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    ROLLBACK_COUNT,
    COMMIT_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Chú ý table prefix có thể khác `BATCH_` và tùy phiên bản/schema repository. `JobExplorer` là API đọc metadata được Spring Batch cung cấp nếu không muốn phụ thuộc SQL.

### Vì sao không cộng tất cả dòng StepExecution?

Một job partitioned có thể có:

~~~text
JobExecution #1
  managerStep                (manager metadata)
  workerStep:range-0000      COMPLETED, skip=2
  workerStep:range-0001      FAILED, skip=3

JobExecution #2 (restart cùng JobInstance)
  managerStep                (execution mới)
  workerStep:range-0001      COMPLETED, skip=1
~~~

Nếu cộng `2 + 3 + 1 = 6` thì được **tổng số skip observations trong các executions** theo dữ liệu minh họa; không chứng minh có sáu **source keys lỗi duy nhất**. Có thể một item bị skip ở attempt đầu và gặp lại ở attempt sau, hoặc lỗi đã được sửa rồi applied.

**Không** cộng counters của manager step và worker steps mà không hiểu handler tổng hợp thống kê thế nào. Manager có metadata riêng và một số counters có thể phản ánh thống kê tổng hợp; cộng mù dễ đếm hai lần. Khi cần thống kê execution, lọc **đúng worker step names** và **đúng lần chạy**, còn báo cáo chất lượng thì dựa vào outcome ledger đã dedupe.

### Một bảng tổng hợp khuyến nghị

| Chỉ số | Đơn vị | Nguồn đáng tin |
| --- | --- | --- |
| Input item expected | Source keys duy nhất | Manifest |
| Applied item | Source keys/operations duy nhất, có bằng chứng commit | Business store + outcome |
| Filtered item | Source keys có quyết định filter cuối cùng | Outcome ledger |
| Quarantined item | Source keys lỗi chưa khắc phục | Quarantine + outcome hiện hành |
| Pending/unknown | Source keys chưa kết luận | Outcome/intent/queue |
| Read/process/write skips | Skip events trong một execution | `StepExecution` counters |
| Retry attempts | Số lần thử thao tác | Retry metrics/logs |
| Outcome conflict | Source keys có trạng thái không nhất quán | Reconciliation queries |

Hai số `skipCount` và `quarantinedUniqueCount` **không buộc bằng nhau** qua mọi attempt: thứ nhất mô tả framework execution, thứ hai mô tả trạng thái dữ liệu đang cần xử lý.

## 12. Phân vùng dữ liệu: đối soát theo worker và toàn job

Trong partitioning, mỗi worker `StepExecution` có `ExecutionContext` riêng. Nếu manager chia 8 partition và mỗi worker cấu hình `skipLimit(10)`, **không có giới hạn 10 skip mặc định cho toàn job**: các worker có thể lần lượt dùng đến ngân sách của mình.

### Đối soát theo hai cấp

**Cấp worker/partition** giúp tìm vấn đề cục bộ:

- Input range, file/tenant và partition key được cấp;
- Số source keys expected trong phạm vi đó;
- Số applied/filtered/quarantined/pending;
- `readSkipCount`/`processSkipCount`/`writeSkipCount`;
- Tỷ lệ lỗi theo **mẫu số nguồn đúng**, không chỉ `readCount`.

**Cấp job/snapshot** giúp áp chính sách chung:

- Tổng unique source keys và tổng outcome hiện hành;
- Tổng lỗi nghiệp vụ/tenant/loại dữ liệu;
- Số item thiếu hoặc trùng;
- Số lỗi vượt giới hạn chất lượng toàn job;
- Trạng thái mọi worker, bao gồm restart attempts;
- Có được phép publish kết quả hay không.

### Partition overlap không phải lỗi SkipListener

Ví dụ cả `range-0000` và `range-0001` cùng đọc ID 500 do điều kiện SQL bị chồng. Mỗi worker có `@StepScope` riêng, skip counters đúng nhưng cùng business ID có thể xuất hiện hai lần ở output/audit.

Cần kiểm tra:

~~~text
inputKeys(partitionA) ∩ inputKeys(partitionB) = ∅
union(inputKeys(all partitions)) = expectedSnapshotKeys
~~~

Đối với input có thể được nhiều partition xử lý **có chủ đích**, phải định nghĩa operation key thích hợp để tránh coi xử lý hợp lệ là overlap sai.

## 13. Retry, rollback, restart và remote messaging

### 13.1. Retry có thể làm tăng số lần gọi nhưng không tạo skip

Nếu processor gặp lỗi transient hai lần, rồi lần thứ ba thành công, item **không phải skipped item**. Ghi một quarantine row mỗi khi processor throw exception sẽ làm đối soát lỗi **bị thổi phồng**.

Chỉ ghi trạng thái `QUARANTINED` khi item thực sự được quyết định skip theo policy, hoặc ghi attempts vào bảng riêng với semantics **lỗi tạm thời** và không coi đó là outcome cuối.

### 13.2. Rollback cần bảo toàn audit

Nếu cùng transaction bảo vệ business output và quarantine/outcome, khi chunk rollback phần chưa commit, kết quả/ledger tương ứng phải rollback cùng.

Nếu audit gửi ra broker hoặc database khác, audit có thể đã nhận event dù chunk rollback; cần **idempotent consumer**, transaction outbox hoặc reconciliation; không dựa vào việc listener được gọi một lần.

### 13.3. Restart không tự sửa item đã skip

Partition `COMPLETED` sau khi skip 8 item có thể **không chạy lại** khi toàn job được restart vì một partition khác `FAILED`. Tám item đó vẫn cần **quarantine và replay workflow riêng** nếu muốn khắc phục.

Khi restart một partition chưa hoàn tất, `JobExecution`/`StepExecutionId` có thể đổi; cần giữ **partition key → input snapshot/range** ổn định và dedupe audit theo source key.

### 13.4. Remote chunking

Trong remote chunking, manager gửi chunk requests và nhận replies. Nếu worker commit rồi mất reply, broker có thể giao lại request; writer/processor có thể xử lý lại những item cũ.

- Dedupe chunk request ID giúp giảm work thừa, nhưng **không thay thế idempotency cấp item** nếu đã có partial side effect ngoài transaction.
- Một reply lặp không đồng nghĩa một business effect đã xảy ra hai lần.
- Dùng business key để đối soát output/quarantine; giữ correlation request/attempt để điều tra transport.

### 13.5. Remote partitioning

Trong remote partitioning, worker cũ có thể vẫn đang chạy khi manager coi nó timeout. Một worker mới có thể nhận cùng partition; cả hai có nguy cơ ghi outcome/audit cho cùng source key.

Cần unique constraint tại hệ thống đích, claim/lease/fencing nếu có yêu cầu single active owner và quy tắc reconciliation. `StepExecutionId` mới không tạo ra **item mới**. Một biến `AtomicInteger` hoặc `ConcurrentHashMap` trong JVM không giải quyết đối soát toàn cụm.

## 14. Publish gate dựa trên chất lượng thực

Đối soát cần dẫn tới quyết định cụ thể. Với pipeline quan trọng, ghi đầu ra vào **staging** và chỉ publish sau khi thỏa mãn các kiểm tra được duyệt.

Ví dụ chính sách **minh họa**, không phải giá trị mặc định:

| Điều kiện | Ngưỡng ví dụ | Nếu vi phạm |
| --- | --- | --- |
| Item nguồn thiếu outcome | `0` | Chặn publish, điều tra input/processing |
| Item trùng business operation | `0` | Chặn publish, reconcile |
| Outcome `APPLIED` không có output | `0` | Chặn publish, kiểm tra transaction |
| Item `UNKNOWN` ở hệ thống đích | `0` với bước tài chính bắt buộc | Chặn publish, xác minh provider |
| Item `QUARANTINED` lỗi dữ liệu thường | ≤ 0,05% snapshot và ≤ 100 item | Chặn nếu vượt chính sách |
| Lỗi thuộc dữ liệu tối quan trọng | `0` | Không chấp nhận skip |
| Tất cả worker `COMPLETED` | Bắt buộc cho publish đầy đủ | Không publish khi còn worker lỗi/dừng |

### Vì sao hậu kiểm không thể thu hồi mọi side effect?

Nếu worker đã gọi thanh toán hoặc phát message trực tiếp cho downstream, publish gate ở cuối **không** thể tự thu hồi giao dịch. Khi yêu cầu phải kiểm toán trước công bố, thiết kế staged output/outbox và ranh giới publish rõ ràng ngay từ đầu.

### Ràng buộc theo tenant/partition

Tỷ lệ lỗi toàn job có thể rất thấp nhưng 100% input của một tenant nhỏ lại bị skip. Nên đặt thêm guardrails theo tenant, file, nguồn và phân đoạn quan trọng. Không chỉ dùng `skipLimit` tuyệt đối mỗi worker vì số bản ghi giữa partitions có thể chênh lệch lớn.

## 15. Kiểm thử đối soát bằng dữ liệu có đáp án

### 15.1. Fixture tối thiểu

Giả sử snapshot có 8 source records:

| Source key | Tình huống | Outcome kỳ vọng |
| --- | --- | --- |
| `file-A:1` | Hợp lệ, ghi thành công | `APPLIED` |
| `file-A:2` | Dòng CSV lỗi parse | `QUARANTINED / READ` |
| `file-A:3` | Hợp lệ nhưng trạng thái CANCELLED | `FILTERED` |
| `file-A:4` | Thiếu mã đơn bắt buộc | `QUARANTINED / PROCESS` |
| `file-A:5` | Hợp lệ, ghi thành công | `APPLIED` |
| `file-A:6` | Writer từ chối item riêng lẻ | `QUARANTINED / WRITE` |
| `file-A:7` | Retry timeout rồi thành công | `APPLIED` |
| `file-A:8` | Hợp lệ, ghi thành công | `APPLIED` |

Kỳ vọng cuối cùng:

~~~text
Số source keys = 8
APPLIED        = 4
FILTERED       = 1
QUARANTINED    = 3
PENDING        = 0
UNKNOWN        = 0
MISSING        = 0

4 + 1 + 3 = 8
~~~

Đó là số **business outcomes** cho fixture. Các bộ đếm Spring Batch có thể dùng kiểm tra phụ, nhưng không thay thế identity-based assertions.

### 15.2. Kiểm tra outcome theo source key

Một integration test có thể đọc trực tiếp outcome ledger sau khi job kết thúc:

~~~java
@Test
void doiSoatDuTamLoaiKetQua() {
    // Giả định test fixture file-A:1..8 đã được tạo,
    // pipelineId/sourceVersion được biết và job đã chạy.

    Map<String, String> outcomes = jdbc.query(
            """
            SELECT source_key, outcome_status
            FROM item_outcome_current
            WHERE pipeline_id = ? AND source_version = ?
            """,
            rs -> {
                Map<String, String> values = new HashMap<>();
                while (rs.next()) {
                    String prior = values.put(
                            rs.getString("source_key"),
                            rs.getString("outcome_status"));
                    if (prior != null) {
                        throw new IllegalStateException(
                                "Trùng source key trong outcome query");
                    }
                }
                return values;
            },
            "orders-import", "snapshot-fixture-01");

    assertEquals(8, outcomes.size());
    assertEquals("QUARANTINED", outcomes.get("file-A:2"));
    assertEquals("FILTERED", outcomes.get("file-A:3"));
    assertEquals("QUARANTINED", outcomes.get("file-A:4"));
    assertEquals("QUARANTINED", outcomes.get("file-A:6"));
    assertEquals("APPLIED", outcomes.get("file-A:7"));
}
~~~

Đây là **đoạn test tích hợp minh họa**, cần `JdbcTemplate`, `HashMap`, `Map`, JUnit 5, test database, schema và job/configuration thật. Test bổ sung cần kiểm tra:

- Manifest có đúng 8 keys và set key manifest **bằng** set key outcomes.
- APPLIED keys có output đúng amount/tenant/business ID.
- QUARANTINED keys có đúng phase/reason.
- Không có key mang hai outcomes hoặc duplicate business operation.
- Skip/read/write counters theo từng worker phù hợp kỳ vọng khi dùng đúng reader/processor/writer.

Nếu muốn xác minh **một bản ghi được phân loại READ skip** khi file parse lỗi, hãy bảo đảm test fixture và manifest vẫn có `file-A:2` dù reader không tạo `InputOrder`.

### 15.3. Ma trận lỗi bắt buộc

| Test | Điều cần chứng minh |
| --- | --- |
| `skipLimit(3)` với đúng ba item lỗi | Ba item được quarantine, không thất bại chỉ vì chạm giới hạn |
| Item lỗi thứ tư | Worker `FAILED`; không coi item thứ tư là skip đã được chấp nhận |
| Lỗi không skippable | Fail theo policy; không tạo outcome `QUARANTINED` sai |
| Processor trả `null` | Item filter được ghi nhận qua cơ chế riêng nếu yêu cầu đối soát |
| Retry rồi thành công | Không còn item ở quarantine hiện hành; output hợp lệ |
| Chunk rollback sau skip event | Audit không bị nhân đôi sai; outcome cuối nhất quán |
| Restart cùng `JobInstance` | Source identity/manifest giữ nguyên; không cộng trùng attempts |
| Partition `COMPLETED` đã skip item | Item cũ còn trong quarantine cho đến khi replay riêng |
| Hai worker cùng key | Unique constraint/state transition chống ghi đè |
| Source version thay đổi | Không dùng checkpoint/source key cũ cho dữ liệu đã đổi nghĩa |
| Remote chunk reply mất | Redelivery không làm double business effect |
| External writer timeout sau commit | Outcome `UNKNOWN` được reconcile, không tự tuyên bố `APPLIED` |
| Sink audit/quarantine bị lỗi | Theo policy bắt buộc: fail-closed hoặc cơ chế bù đáng tin |
| Output thiếu dù metadata `COMPLETED` | Publish gate phát hiện mismatch |
| Quarantine đã sửa rồi replay | Outcome thành `APPLIED`, lịch sử lỗi vẫn còn |

### Test có concurrency thật

Khi so sánh các partition, hãy chạy executor nhiều worker trên database thật hoặc Testcontainers nếu phù hợp. Hai worker cùng source key phải bị DB unique constraint/state machine phân xử; không dùng chỉ một `synchronized` service JVM để kết luận an toàn remote.

## 16. Hiệu năng khi đối soát hàng triệu records

Đối soát từng source key có thể tốn chi phí lưu trữ và query. Nhưng bỏ identity để “chỉ đếm tổng” sẽ đánh mất khả năng chứng minh không thiếu/trùng. Thiết kế nên cân bằng đúng đắn với chi phí:

| Kỹ thuật | Lợi ích | Điều kiện |
| --- | --- | --- |
| Index `(pipeline_id, source_version, source_key)` | Join manifest/outcome nhanh | Key có cùng semantics ở các bảng |
| Partition bảng theo source version/time | Giảm kích thước working set | Đừng xóa history trước cửa sổ restart/replay |
| Đối soát theo partition rồi toàn snapshot | Dễ phát hiện lỗi cục bộ, tối ưu truy vấn | Union partitions phải khớp snapshot |
| Tổng hợp counts/materialized views | Dashboard nhanh hơn | Không thay thế query mismatch theo key |
| Unique constraint business operation | Chặn double effect sớm | Phải xử lý conflict payload đúng |
| Staging/quarantine bền vững | Có thể sửa và publish sau validation | Retention và quyền truy cập rõ |
| Batching/upsert cẩn thận | Tăng throughput | Không đánh mất audit/transaction/idempotency |

Nếu nhiều worker ghi vào một outcome table, đo lock waits, connection pool, I/O, latency của `JobRepository` và tốc độ insert ledger. Tăng `gridSize` khi DB đang nghẽn có thể giảm throughput. Tập trung tối ưu theo **bottleneck quan sát được**, không bỏ unique key hoặc ACK sớm để tăng tốc.

### Metric nên theo dõi

- `expected_source_items`, `applied_unique_items`, `filtered_unique_items`, `quarantined_unique_items`, `pending_items`, `unknown_items`.
- `missing_outcome_items`, `output_without_source_items`, `outcome_conflict_items`.
- `readSkipCount`, `processSkipCount`, `writeSkipCount` theo worker/attempt.
- Retry/rollback count, thời gian commit, quarantine write latency, reconcile duration.
- Số item đang chờ replay, tuổi của item lâu nhất, số item đã sửa thành công.
- Số file/tenant/partition vượt ngưỡng chất lượng.

Không đặt `sourceKey` hoặc `StepExecutionId` làm nhãn Prometheus cho mỗi bản ghi: cardinality quá cao. Dùng bảng audit và log/tracing để tra cứu identity chi tiết; metric tổng hợp theo pipeline, error category và nhóm partition.

## 17. Runbook khi phát hiện số liệu không khớp

1. **Đóng băng nguồn tham chiếu:** Ghi rõ `pipelineId`, source version/snapshot, manifest, input file hashes và window.
2. **Xác định JobInstance:** Đọc identifying `JobParameters`, các `JobExecution` và `StepExecution` đã chạy/restart.
3. **Khoanh vùng mismatch:** Thiếu outcome, `APPLIED` thiếu output, output không thuộc source, duplicate operation, hay filter/skip bị nhầm?
4. **Tra skip events:** Đọc `readSkipCount`/`processSkipCount`/`writeSkipCount` và quarantine theo source key, phase, reason, partition.
5. **Kiểm tra giao dịch:** Audit/ledger và business output có commit cùng transaction không? Có HTTP/broker side effect ngoài transaction không?
6. **Kiểm tra input plan:** Partition key/range/file/snapshot có thay đổi giữa lần chạy và restart không? Có overlap hoặc thiếu range không?
7. **Kiểm tra concurrency:** Có singleton mutable, `ThreadLocal` không cleanup, worker cũ còn chạy hoặc broker redelivery không?
8. **Chặn publish nếu nghiêm trọng:** Không phát dữ liệu thiếu/trùng, nhất là tác dụng tài chính hoặc dữ liệu nhạy cảm.
9. **Sửa lỗi và replay có kiểm soát:** Dùng quarantine source keys và business operation IDs ổn định; không tự xóa metadata JobRepository hay dedupe keys.
10. **Đối soát lại:** Xác minh trạng thái hiện hành, lịch sử sự cố và output thực; chỉ publish khi mọi điều kiện bắt buộc đạt.

### Không “sửa cho khớp số” bằng cách sửa metadata

Tránh `UPDATE BATCH_STEP_EXECUTION SET WRITE_COUNT = ...` hoặc xóa `ExecutionContext` để ép restart. Metadata Batch phản ánh lịch sử thực thi và checkpoint; chỉnh tay có thể phá recovery, chưa chắc tác động đến output nghiệp vụ. Xử lý sai lệch qua code/policy/ledger và cơ chế restart/replay được hỗ trợ.

## 18. Bài tập tình huống

Một job nhập 8 triệu khách hàng từ 32 file CSV, chia thành 16 partition. Mỗi worker có `skipLimit(10)`. Sau lượt chạy thứ nhất, ba worker hoàn tất sau khi skip tổng cộng 18 record lỗi parse; một worker thất bại vì lỗi kết nối DB. Khi restart, worker lỗi được xử lý lại thành công. Dashboard cộng các `readSkipCount` ở mọi `StepExecution` và báo 23 skip, trong khi bảng quarantine có 18 source keys unique. Đồng thời output đích có thêm hai bản ghi mà manifest không chứa.

Nhóm vận hành đề xuất xóa năm bản quarantine để khớp tổng skip, đổi `status` Batch của các worker thành `COMPLETED` và publish ngay.

**Câu hỏi:**

1. Vì sao 23 skip observations không bắt buộc tương đương 23 source records lỗi duy nhất?
2. Làm sao xác định 18 record lỗi parse khi reader chưa tạo business object?
3. Vì sao hai output không có trong manifest phải được điều tra độc lập với tổng skip?
4. Nếu các item đã skip ở partition `COMPLETED` được sửa, restart job có tự xử lý lại không?
5. Cần làm gì để biết liệu worker retry có tạo external side effect kép?
6. Những điều kiện nào cần đạt trước khi được publish?

**Định hướng trả lời:** Cần phân biệt counters theo `StepExecution` và source keys unique xuyên attempts; dùng `sourceVersion + fileId + logical record position` cho lỗi parse. Hai output mồ côi có thể do SQL overlap, mapping sai tenant/snapshot hoặc writer ghi trùng, cần tra business operation ledger. Item bị skip trong partition hoàn tất cần workflow replay riêng; không được sửa JobRepository metadata bằng tay. Đối soát đủ input/output/filter/quarantine/pending, xác minh idempotency và external effects, giữ audit lịch sử, sau đó mới mở publish gate.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip, `skipLimit` và classification.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `SkipListener` và các listener trong chunk.
- [Spring Batch API — SkipListener](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/SkipListener.html): `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite`.
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry và lỗi transient.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và replay.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning và concurrency.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking/partitioning.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_STEP_EXECUTION` và `ExecutionContext`.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction và ranh giới commit.

> **Ghi nhớ:** Đối soát item bị skip không chỉ là `SUM(skipCount)`. Nó là phép chứng minh **mọi source key thuộc snapshot đều có outcome hợp lệ**, những skip được ghi nhận bằng identity bền vững và nguyên nhân cụ thể, không có item thiếu/trùng hoặc tác dụng ngoài transaction chưa xác nhận. Khi job scale qua nhiều partition và nhiều lần restart, hãy giữ manifest, audit, idempotency và publish gate làm **nguồn bằng chứng nghiệp vụ**, còn counters Spring Batch dùng cho chẩn đoán kỹ thuật.
