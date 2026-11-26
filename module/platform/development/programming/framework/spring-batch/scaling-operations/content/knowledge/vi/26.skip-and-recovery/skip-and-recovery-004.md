# Skip listener ghi nhận item trong Spring Batch

> **Chương:** Skip và recovery
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; đo nút thắt, đảm bảo thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Trong một job xử lý hàng triệu bản ghi, **cho phép skip không có nghĩa là được phép đánh mất dấu vết của bản ghi bị bỏ qua**. `SkipListener` giúp ghi nhận nguyên nhân và nhận diện item đã bị bỏ qua trong giai đoạn đọc, xử lý hoặc ghi. Muốn sử dụng an toàn, ta còn phải hiểu lifecycle callback, ranh giới transaction, nguy cơ callback lặp khi restart và cách kiểm toán tập dữ liệu cuối cùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `onSkipInRead`, `onSkipInProcess` và `onSkipInWrite`, đặc biệt là trường hợp lỗi đọc **chưa tạo được item**.
2. Cấu hình `SkipListener` với fault-tolerant chunk step Spring Batch 5.x, whitelist exception và `skipLimit`.
3. Thiết kế bản ghi audit/quarantine có định danh item bền vững, mã lỗi và trạng thái xử lý lại.
4. Hiểu lời gọi listener liên quan ra sao tới commit, rollback, retry, restart, `ExecutionContext` và writer có side effect bên ngoài transaction.
5. Kiểm thử listener trên nhiều partition/worker mà không làm lẫn dữ liệu, không tạo bản ghi lỗi trùng và không che giấu sự cố.

## 1. Bài toán: job chạy tiếp nhưng bản ghi lỗi đi đâu?

Giả sử hệ thống nhập 500.000 đơn hàng từ một file CSV. Trong quá trình chạy có ba trường hợp:

| Giai đoạn | Ví dụ lỗi | Thông tin có thể có tại thời điểm lỗi |
| --- | --- | --- |
| **Read** | Dòng 127 không parse được ngày giao dịch | Exception, tên file và số dòng; **chưa chắc có `InputOrder`** |
| **Process** | `InputOrder` có số tiền âm | `InputOrder` gốc và exception |
| **Write** | Writer từ chối `OutputOrder` vì quy tắc nghiệp vụ của đích | `OutputOrder` dự kiến ghi và exception |

Nếu exception đó được cấu hình là *skippable*, `skipLimit` còn ngân sách và quá trình fault-tolerant xác định item có thể bỏ qua, Spring Batch sẽ tiếp tục xử lý phần dữ liệu khác.

Tuy nhiên, nếu không có nhật ký lỗi có thể truy vết, nhóm vận hành sẽ không biết:

- Bản ghi nguồn nào không được đưa vào output?
- Nó lỗi ở bước nào, vì quy tắc gì?
- Nó thuộc file/snapshot/tenant/partition nào?
- Sau khi sửa dữ liệu, cần replay những bản ghi nào?
- Có phải cùng một item đã bị ghi nhận nhiều lần sau rollback hoặc restart không?

`SkipListener` giải quyết phần **quan sát item đã skip**; chính sách skip, độ bền audit, khả năng replay và đối soát phải được thiết kế bổ sung.

~~~mermaid
flowchart TD
    A["Nguồn CSV / Database"] --> R["ItemReader"]
    R --> P["ItemProcessor"]
    P --> W["ItemWriter"]
    R -- "Lỗi skippable" --> S["Cơ chế skip / retry của chunk"]
    P -- "Lỗi skippable" --> S
    W -- "Lỗi skippable" --> S
    S --> L["SkipListener<br/>read / process / write"]
    L --> Q[("Quarantine / Audit")]
    W --> D[("Business output")]
    Q --> X["Sửa dữ liệu → replay có kiểm soát"]
~~~

Sơ đồ là luồng nghiệp vụ, không thể hiện đầy đủ rollback và các lần retry mà framework có thể thực hiện trước khi xác nhận một skip.

## 2. Hợp đồng SkipListener

Trong Spring Batch, interface `SkipListener<I, O>` có ba callback:

~~~java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
~~~

Trong các phiên bản Spring Batch hiện đại, các method có triển khai mặc định; class implement interface chỉ cần override những callback liên quan.

| Callback | Item nhận được? | Khi nào cần ghi nhận? | Chú ý |
| --- | --- | --- | --- |
| `onSkipInRead(Throwable)` | **Không** có item tham số | Reader không thể trả về item hợp lệ từ input | Lấy file/line hoặc source position từ exception hay metadata reader |
| `onSkipInProcess(I, Throwable)` | Có **item đầu vào** | Processor lỗi và item được skip | Dùng business/source ID ổn định của input |
| `onSkipInWrite(O, Throwable)` | Có **item đầu ra** | Writer lỗi và item được skip | Giữ correlation từ output trở về source ID |

**Phân biệt quan trọng:** Callback chỉ dành cho những item **đã được quyết định skip**, không phải mọi lần ném exception. Lỗi transient retry thành công không nên xuất hiện như một item bị skip. Item bị processor lọc bằng cách trả về `null` cũng **không** kích hoạt `SkipListener`.

### Tại sao onSkipInRead không có item?

Nếu reader đang phân tích chuỗi `"2026-99-55;ORDER-123"` và tokenizer/mapper thất bại, nó có thể chưa tạo được `InputOrder`. Do đó API chỉ truyền `Throwable`. Với `FlatFileItemReader`, `FlatFileParseException` thường cung cấp **số dòng** và thông tin dòng nguồn; không nên giả định mọi reader hay mọi exception đều có số dòng.

Không tạo một business key giả như `"UNKNOWN"` cho mọi lỗi đọc: điều đó sẽ khiến các lỗi khác nhau bị gộp thành một item và đánh mất khả năng replay.

### Listener khác gì bộ xử lý exception tổng quát?

| Cơ chế | Mục đích |
| --- | --- |
| `skip(...)` / `noSkip(...)` | Phân loại exception được phép bỏ qua |
| `skipLimit(...)` | Giới hạn tổng số skip được chấp nhận trong `StepExecution` |
| `retry(...)` / `retryLimit(...)` | Thử lại lỗi có thể tạm thời |
| `SkipPolicy` | Tùy biến quyết định có được skip khi gặp exception và count hiện tại |
| **`SkipListener`** | **Quan sát và ghi nhận item thực sự bị skip** |
| `ItemReadListener` / `ItemProcessListener` / `ItemWriteListener` | Quan sát các thao tác read/process/write, không chỉ skip |
| `StepExecutionListener` | Quan sát lifecycle và kết quả chung của step |

Không nên đặt logic “quyết định skip hay không” vào `SkipListener`. Việc listener tự ném exception có thể khiến step thất bại, nhưng đó không thay thế policy có thể kiểm thử của `faultTolerant()`.

## 3. Thời điểm gọi callback và ranh giới transaction

Trong fault-tolerant chunk processing, Spring Batch thiết kế các skip callbacks để được thông báo khi skip đã được xử lý thành công trong chu kỳ chunk; với luồng xử lý chuẩn, chúng được gọi **gần thời điểm commit** nhằm hỗ trợ lưu dấu vết cùng transaction. Không nên hiểu điều đó thành một cam kết “mọi phương thức audit bên ngoài đều được commit đúng một lần”.

~~~mermaid
sequenceDiagram
    participant R as Reader / Processor / Writer
    participant B as Fault-tolerant chunk step
    participant L as SkipListener
    participant A as Transactional audit store
    participant D as Business database
    R->>B: Gặp exception có thể skip
    B->>B: Retry / rollback / cô lập item nếu cần
    B->>L: Callback skip tương ứng
    L->>A: Ghi audit idempotent
    B->>D: Commit kết quả chunk phù hợp
    Note over A,D: Cùng transaction chỉ khi thực sự được cấu hình chung
~~~

Những điểm phải nhớ:

1. **Retry attempt không phải skip event.** Không nên ghi một bản quarantine mới cho mỗi exception trước khi biết item đã bị skip.
2. Một callback có thể phát sinh trong một giao dịch sau đó **rollback**. Nếu audit tham gia transaction đó, ghi nhận chưa commit có thể bị rollback theo.
3. Nếu listener gửi trực tiếp HTTP, email, Kafka hoặc ghi sang database khác, side effect đó **có thể đã xảy ra trước khi transaction chính commit**.
4. Giữa nhiều lần chạy/restart, cùng item có thể xuất hiện lại. Cơ chế callback trong **một lượt xử lý** không thay thế idempotency **xuyên lượt chạy**.
5. Nếu bản ghi audit là bắt buộc về mặt pháp lý/nghiệp vụ, lỗi ghi audit cần được xử lý theo chính sách fail-closed phù hợp; không được chỉ nuốt exception rồi để job tiếp tục “xanh”.

### Một ví dụ lỗi thực tế

~~~text
Worker xử lý ORDER-882
  ↓
Validation phát hiện dữ liệu sai, quyết định skip
  ↓
SkipListener gửi sự kiện "ORDER-882 bị skip" tới API audit
  ↓
API nhận thành công
  ↓
Transaction chunk rollback do lỗi khác
  ↓
Worker retry / job restart
  ↓
API audit có thể nhận sự kiện lần nữa
~~~

Để chống ghi nhận trùng, audit store phải hiểu **identity của bản ghi lỗi** thay vì dựa vào số lần callback được gọi.

## 4. Cấu hình fault-tolerant step và listener

Ví dụ Spring Batch 5.x nhập đơn hàng bằng chunk size 200:

~~~java
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputOrder> reader,
        ItemProcessor<InputOrder, OutputOrder> processor,
        ItemWriter<OutputOrder> writer,
        SkipListener<InputOrder, OutputOrder> skipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<InputOrder, OutputOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderRecordException.class)
            .skipLimit(10)
            .listener(skipListener)
            .build();
}
~~~

`InputOrder`, `OutputOrder` và `InvalidOrderRecordException` là các kiểu do ứng dụng khai báo; ví dụ chưa bao gồm cấu hình reader/writer, `@Configuration` và dependency cho database.

Ở đây:

- `skip(FlatFileParseException.class)` cho phép skip các record lỗi parse đã được kiểm soát.
- `skip(InvalidOrderRecordException.class)` cho phép bỏ qua item vi phạm quy tắc dữ liệu đã xác định.
- `skipLimit(10)` là **một giới hạn chung** cho read/process/write skips trong `StepExecution`, không phải mười skip cho mỗi callback.
- `listener(skipListener)` đăng ký callback ghi nhận item đã skip.
- Không khai báo `skip(Exception.class)` rộng vì có thể che các lỗi database, bug lập trình, lỗi kết nối hoặc invariant nghiệp vụ.

**Trường hợp write skip:** Nếu muốn bỏ qua một lỗi do writer phát hiện, phải phân loại exception **cụ thể, có chủ đích** và thiết kế writer an toàn khi bị rollback/chạy lại. Ví dụ `DestinationRecordRejectedException` chỉ biểu thị một item không đạt quy tắc của đích, không phải `DataAccessException` bất kỳ. Không mặc định lỗi ghi database là skippable.

### Đối tượng dùng trong ví dụ

~~~java
import java.math.BigDecimal;

public record InputOrder(
        String sourceId,
        String orderCode,
        BigDecimal amount) {}

public record OutputOrder(
        String sourceId,
        String orderCode,
        BigDecimal normalizedAmount) {}

public final class InvalidOrderRecordException
        extends RuntimeException {
    public InvalidOrderRecordException(String message) {
        super(message);
    }
}
~~~

`sourceId` là định danh bản ghi trong **snapshot input** và được bảo tồn khi chuyển từ input sang output. Nếu nguồn không có ID, thiết kế identity ổn định như `sourceVersion + fileId + lineNumber`; không sinh `UUID.randomUUID()` mỗi lần listener được gọi.

## 5. Cách viết SkipListener không làm lẫn item

Một listener tốt không chỉ gọi `log.warn(...)`. Nó nên tạo **sự kiện audit có cấu trúc** với identity, lỗi và ngữ cảnh partition rõ ràng.

### 5.1. Mô hình sự kiện audit

~~~java
public record SkipAuditEvent(
        String sourceVersion,
        String partitionName,
        String sourceKey,
        String phase,          // READ / PROCESS / WRITE
        String reasonCode,
        String exceptionType) {}

public interface SkipAuditSink {
    // Implementation phải được thiết kế idempotent và transactional
    // khi dùng trong listener production.
    void record(SkipAuditEvent event);
}
~~~

Đây là **một contract mẫu**, không phải implementation lưu database hoàn chỉnh. Nên tách trường audit được phép công khai và dữ liệu gốc có thể chứa PII. Nếu cần lưu raw record để sửa, nên đặt ở vùng quarantine bảo mật, kiểm soát quyền và thời gian lưu.

### 5.2. Implement ba callback

~~~java
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public final class OrderSkipAuditListener
        implements SkipListener<InputOrder, OutputOrder> {

    private final SkipAuditSink sink;
    private final String sourceVersion;
    private final String partitionName;
    private final String fileId;

    public OrderSkipAuditListener(
            SkipAuditSink sink,
            String sourceVersion,
            String partitionName,
            String fileId) {
        this.sink = sink;
        this.sourceVersion = sourceVersion;
        this.partitionName = partitionName;
        this.fileId = fileId;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        if (!(error instanceof FlatFileParseException parse)) {
            // Không tự gộp mọi lỗi đọc không rõ identity thành UNKNOWN.
            throw new IllegalStateException(
                    "Không xác định được source record của read skip",
                    error);
        }

        String sourceKey = fileId + ":" + parse.getLineNumber();
        sink.record(event(sourceKey, "READ",
                "INVALID_CSV_RECORD", error));
    }

    @Override
    public void onSkipInProcess(InputOrder item, Throwable error) {
        sink.record(event(item.sourceId(), "PROCESS",
                "INVALID_ORDER", error));
    }

    @Override
    public void onSkipInWrite(OutputOrder item, Throwable error) {
        sink.record(event(item.sourceId(), "WRITE",
                "DESTINATION_REJECTED", error));
    }

    private SkipAuditEvent event(
            String key, String phase, String reason, Throwable error) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException(
                    "Không có source key ổn định cho skipped item");
        }
        return new SkipAuditEvent(
                sourceVersion, partitionName, key,
                phase, reason, error.getClass().getSimpleName());
    }
}
~~~

Các `reasonCode` trên là mã ví dụ. Trong hệ thống thật, mapping từ exception sang mã lỗi cần **đầy đủ và có version**; không tự dán nhãn mọi lỗi writer thành `DESTINATION_REJECTED` nếu có nhiều loại lỗi khác nhau.

**Lưu ý về `onSkipInRead`:** Trong ví dụ, read skip chỉ được thiết kế cho `FlatFileParseException`. Việc ném lỗi khi không có identity là lựa chọn **fail-closed** có chủ đích. Với JDBC, JSON streaming hoặc message reader, cần cách lấy record ID/offset tương ứng; không thể giả định mọi source đều có `lineNumber`.

### 5.3. Đăng ký listener theo worker StepExecution

Một listener có field chứa `partitionName`/`fileId` riêng từng worker không nên là singleton mutable dùng chung khi partitioning:

~~~java
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
SkipListener<InputOrder, OutputOrder> ordersSkipListener(
        SkipAuditSink sink,
        @Value("#{jobParameters['sourceVersion']}")
        String sourceVersion,
        @Value("#{stepExecution.stepName}")
        String partitionName,
        @Value("#{stepExecutionContext['fileId']}")
        String fileId) {
    return new OrderSkipAuditListener(
            sink, sourceVersion, partitionName, fileId);
}
~~~

`@StepScope` cho phép target listener giữ metadata **bất biến cho từng `StepExecution`**; không dùng field `currentPartition` và cập nhật từ nhiều worker trên cùng một singleton. Ví dụ giả định manager/partitioner cung cấp `fileId`, job có tham số `sourceVersion` và step-scoped proxy được đăng ký qua `.listener(skipListener)`.

Không phải listener nào cũng cần `@StepScope`. Một listener hoàn toàn **stateless, thread-safe**, nhận identity từ item/error và giao cho một sink an toàn có thể dùng singleton. Nhưng không được dùng `@JobScope` như cơ chế cách ly state riêng của từng partition.

## 6. Quarantine phải có identity bền vững và chống trùng

Một log warning chỉ là **tín hiệu điều tra**; nó chưa chắc là kho lỗi đáng tin cậy. Với pipeline quan trọng, xây bảng/quarantine store có thể tìm, sửa, replay và đối soát.

Ví dụ một schema logic:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `source_version` | `import-2026-11-26-v2` | Snapshot hoặc manifest input |
| `source_key` | `orders.csv:127` hoặc `ORD-885` | Định danh ổn định của record |
| `phase` | `READ`, `PROCESS`, `WRITE` | Giai đoạn bị skip |
| `reason_code` | `INVALID_DATE` | Mã lỗi rõ ràng, có thể phân loại |
| `exception_type` | `FlatFileParseException` | Thông tin kỹ thuật tối giản |
| `partition_name` | `worker:range-0001` | Phạm vi phát hiện |
| `first_seen_at` / `last_seen_at` | Thời gian UTC | Audit và retry |
| `status` | `NEW`, `TRIAGED`, `FIXED`, `REPLAYED` | Quy trình xử lý |

Một ràng buộc ví dụ ở database:

~~~sql
CREATE TABLE skipped_records (
    source_version VARCHAR(120) NOT NULL,
    source_key     VARCHAR(220) NOT NULL,
    phase          VARCHAR(20)  NOT NULL,
    reason_code    VARCHAR(80)  NOT NULL,
    partition_name VARCHAR(180) NOT NULL,
    status         VARCHAR(20)  NOT NULL,
    first_seen_at  TIMESTAMP    NOT NULL,
    last_seen_at   TIMESTAMP    NOT NULL,
    PRIMARY KEY (source_version, source_key, phase)
);
~~~

Đây là **schema minh họa**: cách tạo timestamp, index và thao tác upsert phụ thuộc database. Khóa `(source_version, source_key, phase)` được chọn để một item/stage chỉ có một bản quarantine hiện hành trong snapshot. Nếu cần lưu **nhiều lý do lỗi của cùng item ở một stage**, hãy tách bảng **lịch sử attempt/reason** hoặc thiết kế khóa khác; không âm thầm ghi đè mất các nguyên nhân cũ.

### Chọn idempotency key theo nguồn

| Nguồn | Identity có thể dùng | Cần chú ý |
| --- | --- | --- |
| CSV cố định | `snapshotId + fileId + lineNumber` | File và thứ tự dòng phải cố định khi restart |
| Database | `snapshotId + primaryKey` | Bản ghi thay đổi giữa các lần chạy cần version/cutoff |
| Kafka/message | `topic + partition + offset` | Xác định phiên bản stream và chính sách retention/replay |
| API pagination | `sourceVersion + businessId` | Offset trang không ổn định nếu nguồn thêm/xóa record |
| Multi-tenant | `tenantId + sourceVersion + recordId` | Identity phải bao gồm namespace tenant |

Không dùng `StepExecutionId` làm **khóa duy nhất của item**: khi restart, cùng partition có thể có StepExecution mới. Nên lưu `StepExecutionId` để truy dấu attempt, còn dedupe phải dựa vào identity dữ liệu **không đổi giữa các lần chạy**.

## 7. Ghi quarantine cùng transaction hay gửi sang hệ thống khác?

### Lựa chọn A — Cùng database và cùng transaction phù hợp

Nếu sink ghi vào bảng quarantine bằng cùng connection/transaction boundary phù hợp với chunk, khi transaction rollback, audit chưa commit cũng bị rollback. Điều này giúp giảm trạng thái “có audit nhưng chunk chưa commit”.

**Nhưng:** Chỉ dùng cùng một `PlatformTransactionManager` không tự chứng minh mọi datasource khác nhau đều nằm trong một transaction atomic. Cần xác nhận reader/writer/audit thực sự dùng tài nguyên và transaction được điều phối đúng.

### Lựa chọn B — Ghi vào hệ thống bên ngoài

Gửi skip audit trực tiếp qua HTTP/queue/Kafka từ listener có thể hữu ích nhưng không phải mặc nhiên transactional với job:

~~~text
Listener gửi event tới audit API
  ↳ API báo thành công
Chunk ở business DB rollback
  ↳ audit event đã phát ra có thể không bị thu hồi
Retry / restart
  ↳ cùng item có thể được phát lại
~~~

Nếu downstream bắt buộc nhận sự kiện, cân nhắc **transactional outbox**: ghi sự kiện vào outbox cùng transaction phù hợp, rồi một dispatcher phát ra kênh ngoài với idempotency. Consumer audit cũng nên chống nhận trùng.

### Lựa chọn C — Chỉ log để theo dõi, đối soát ở bước cuối

Đối với các pipeline thử nghiệm hoặc dữ liệu có thể tái tạo, log có thể đủ để debug; nhưng **không** nên gọi đó là cơ chế quarantine có khả năng replay đáng tin cậy. Chốt rõ mức chấp nhận mất log, thời gian giữ log, quyền truy cập và chiến lược phát hiện item bị mất.

| Yêu cầu | Cách tiếp cận |
| --- | --- |
| Cần xử lý bù từng item sau khi job chạy | Durable quarantine + source key + trạng thái |
| Cần atomic với transaction chunk | Audit/outbox cùng transaction phù hợp |
| Gửi event ra xa | Outbox hoặc delivery có dedupe/reconciliation |
| Chỉ cần debug ngắn hạn | Log có cấu trúc, có giới hạn tốc độ và không lộ PII |
| Yêu cầu không được mất dữ liệu audit | Listener hoặc bước kiểm toán phải **fail** khi không thể ghi audit đúng chuẩn |

## 8. Tại sao write skip cần được kiểm thử kỹ hơn?

`ItemWriter` thường nhận **cả chunk**, không chỉ một item. Khi writer ném exception, framework có thể cần rollback chunk và thử lại ở dạng giúp xác định item gây lỗi. Vì vậy, việc writer hoặc processor được gọi **nhiều lần** không đồng nghĩa nhiều item đã được skip.

Ví dụ:

~~~text
Chunk có 5 item: A, B, C, D, E
Writer batch phát hiện C vi phạm quy tắc
      ↓
Giao dịch rollback
      ↓
Framework thử/cô lập item theo cơ chế fault-tolerant
      ↓
Chỉ C được xác định skippable
      ↓
onSkipInWrite(C, error) ghi nhận C
      ↓
Các item còn lại được commit theo chính sách step
~~~

Đó là mô hình khái niệm. Hành vi thực tế phụ thuộc writer, transaction manager, exception classifier, `skipLimit` và chính sách retry/no-rollback. Với writer có side effect ngoài transaction, thử lại cả chunk có thể gây phát lại request; cần idempotency cho từng business item.

**Không cấu hình `skip(DataAccessException.class)` hay `skip(Exception.class)` chỉ để listener “bắt được nhiều item lỗi”**. Lỗi deadlock, mất kết nối hoặc vi phạm schema cần chiến lược retry/fail và điều tra riêng.

## 9. SkipListener trong partitioning và remote workers

Khi tăng tốc bằng partitioning, manager chia việc thành nhiều `StepExecution`; listener được đăng ký trong **worker step** sẽ ghi nhận lỗi **tại worker đang xử lý item**.

~~~mermaid
flowchart TB
    M["Manager PartitionStep"] --> A["Worker A / StepExecution A"]
    M --> B["Worker B / StepExecution B"]
    M --> C["Worker C / StepExecution C"]
    A --> LA["SkipListener A"]
    B --> LB["SkipListener B"]
    C --> LC["SkipListener C"]
    LA --> Q[("Quarantine store dùng chung")]
    LB --> Q
    LC --> Q
    A --> R[("JobRepository")]
    B --> R
    C --> R
~~~

### Ba rủi ro khi nhiều worker chạy cùng lúc

**1. Cross-talk do bean singleton mutable.** Một listener giữ field `currentFileId` được `beforeStep` của nhiều worker ghi vào có thể ghi nhầm tên file. Dùng `@StepScope` hoặc thiết kế stateless với context/identity rõ ràng.

**2. Cạnh tranh ghi audit.** Hai worker có thể cùng gặp một source key vì dữ liệu overlap, retry hoặc message được phát lại. Quarantine store phải có unique constraint/upsert và logic xử lý conflict đúng nghiệp vụ.

**3. Skip limit không phải ngân sách toàn job.** Với 8 worker và `skipLimit(10)` mỗi worker, về lý thuyết có thể có đến 80 item skip được chấp nhận trong một lượt chạy nếu mỗi worker dùng đủ ngân sách. Listener không tự tạo giới hạn lỗi chung toàn job.

### Local và remote có gì khác?

| Yếu tố | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Listener ở đâu? | Trong worker thread cùng JVM | Trong JVM/container worker từ xa |
| Mutable singleton có thể chia sẻ trực tiếp? | Có, giữa các partition trong cùng context | Trong mỗi worker JVM nếu nó chạy nhiều partition; **không** chia Java heap giữa các JVM |
| Quarantine chung | Có thể là database cùng ứng dụng | Cần store chia sẻ/transport và quyền truy cập phù hợp |
| Giao lại yêu cầu | Chủ yếu qua lỗi/restart | Có thêm broker retry, redelivery, mất reply |
| Định danh bền vững | `sourceVersion + recordId` | Tương tự, đồng thời xét message identity và partition ID |

Trong remote partitioning, đừng giả định message chỉ được giao **đúng một lần**. Hệ thống cần đối soát `JobRepository`, trạng thái worker và audit store trước khi quyết định replay.

## 10. Theo dõi SkipListener bằng số liệu và log

Trong `StepExecution`, Spring Batch lưu các counter:

- `readSkipCount`: skip từ reader;
- `processSkipCount`: skip từ processor;
- `writeSkipCount`: skip từ writer;
- `skipCount`: tổng skip của execution.

Listener giúp ghi **identity của item**, còn counters giúp biết **có bao nhiêu skip** theo execution. Hai nguồn dữ liệu có thể khác nhau nếu audit bị rollback, duplicate đã được dedupe hoặc lỗi audit xảy ra. Không nên lấy số record quarantine mới bằng tổng callback raw một cách máy móc.

### Phép đối soát nên thực hiện

| Điều cần so sánh | Vì sao |
| --- | --- |
| `readSkipCount` ↔ record lỗi đọc có source position | Read skip có thể chưa có business object |
| `processSkipCount` ↔ item nguồn lỗi validation | Kiểm tra item ID và reason code |
| `writeSkipCount` ↔ item output bị đích từ chối | Đảm bảo còn correlation về source ID |
| `skipCount` theo từng worker và tổng job | Phát hiện partition bất thường |
| Quarantine **unique item IDs** theo snapshot | Phân biệt item lỗi thật với nhiều attempt |
| Business output + filter hợp lệ + quarantine | Phát hiện missing/duplicate khi đầu vào có thể đối soát |

Với phép đối soát tập dữ liệu đơn giản một-input-một-output, có thể kiểm tra bằng tập business keys:

~~~text
Input IDs dự kiến
  = Output IDs thành công
    ∪ IDs filter hợp lệ
    ∪ IDs quarantine

Các tập cần không giao nhau nếu quy tắc nghiệp vụ yêu cầu
mỗi input có đúng một trạng thái kết thúc.
~~~

Không áp dụng đẳng thức này mù quáng cho pipeline một-nhiều, aggregate, dedupe, multi-line records hoặc nguồn biến đổi; hãy định nghĩa invariant riêng.

### Logging có cấu trúc

Nên ghi: `JobInstance`, `JobExecutionId`, `StepExecutionId`, partition, source version, source key, phase, reason code. Không log toàn bộ raw dòng CSV hoặc exception chứa PII. Với volume lớn, tránh ghi stack trace cho từng validation item; có thể thống kê theo mã lỗi và lưu chi tiết cần thiết trong quarantine store.

Khi xuất metric time series, đừng gắn `sourceKey`/`StepExecutionId` vào mọi label Prometheus dài hạn: cardinality có thể tăng rất mạnh. Dùng số liệu tổng hợp theo job, partition group và reason code; điều tra item cụ thể qua audit/log.

## 11. Listener và retry/restart: những trường hợp dễ nhầm

| Tình huống | Điều có thể xảy ra | Nguyên tắc an toàn |
| --- | --- | --- |
| Validation exception được skip trong chunk commit | Listener ghi nhận item | Kiểm tra audit và business output đúng trạng thái |
| Lỗi transient retry thành công | **Không phải skipped item** | Không tạo quarantine chỉ vì từng có exception |
| Chunk rollback sau callback | Audit cùng transaction có thể rollback; external audit thì không | Cân nhắc transaction/outbox và dedupe |
| Worker fail sau khi đã commit các chunk trước | Các skip trước đó vẫn thuộc lịch sử | Giữ audit, dùng checkpoint phù hợp |
| Restart cùng `JobInstance` | Worker cần chạy lại có `StepExecution` mới | Không tạo identity item dựa trên StepExecutionId |
| Partition đã `COMPLETED` có item skip | Restart thường không chạy lại partition đó | Replay các item quarantined theo quy trình riêng |
| Broker giao lại remote partition request | Có thể gặp lại cùng item | Unique constraint và idempotency tại sink/đích |
| Input snapshot thay đổi | Source key theo line/offset có thể chỉ item khác | Cố định snapshot hoặc thêm source version |

**Phân biệt “replay item đã skip” với “restart job”.** Nếu một partition đã hoàn tất sau khi skip 5 item, và job sau đó lỗi ở partition khác, restart thường chỉ xử lý những partition chưa hoàn tất. Năm item lỗi thuộc partition đã hoàn tất không tự được xử lý lại. Quarantine phải hỗ trợ **một luồng sửa dữ liệu và replay riêng**.

## 12. Kiểm thử SkipListener

### 12.1. Unit test callback và payload

Một test nhỏ có thể gọi trực tiếp listener bằng fake sink để xác minh record ID, phase, reason code và định dạng source key. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderSkipAuditListenerTest {

    @Test
    void processSkipGhiDungItem() {
        List<SkipAuditEvent> saved = new ArrayList<>();
        SkipAuditSink sink = saved::add;

        OrderSkipAuditListener listener =
                new OrderSkipAuditListener(
                        sink, "snapshot-01", "worker:tenant-A", "orders.csv");

        InputOrder bad = new InputOrder(
                "ORDER-882", "ORD-882", null);
        listener.onSkipInProcess(
                bad, new InvalidOrderRecordException("Dữ liệu sai"));

        assertEquals(1, saved.size());
        SkipAuditEvent audit = saved.get(0);
        assertEquals("snapshot-01", audit.sourceVersion());
        assertEquals("worker:tenant-A", audit.partitionName());
        assertEquals("ORDER-882", audit.sourceKey());
        assertEquals("PROCESS", audit.phase());
    }
}
~~~

Test này chỉ kiểm tra **mapping callback → audit event**. Nó không kiểm tra framework có thực sự gọi callback đúng thời điểm hay không, không kiểm tra rollback và cũng không chứng minh độ bền của database audit.

### 12.2. Integration test với SkipLimit và writer thật

Dùng `spring-batch-test`, `@SpringBatchTest` và `JobLauncherTestUtils` hoặc cách khởi chạy job tương đương:

1. Chuẩn bị snapshot input có **một dòng CSV parse lỗi**, **một item validation lỗi**, và các item hợp lệ.
2. Cấu hình whitelist skip, `skipLimit`, transaction manager và listener/quarantine sink test.
3. Chạy job với `JobParameters` xác định; assert `BatchStatus.COMPLETED` khi số skip chưa vượt ngưỡng.
4. Đọc `StepExecution` và kiểm tra `readSkipCount`, `processSkipCount`, `writeSkipCount` đúng kỳ vọng.
5. Đọc quarantine store và xác nhận **đúng source key, phase, reason**; kiểm tra **không có** bản ghi audit cho item chỉ bị retry rồi thành công.
6. So sánh tập business IDs của output, filter và quarantine, tránh chỉ nhìn số item đã viết.

Để test `onSkipInWrite`, dùng writer test có khả năng ném **exception riêng cho một item xác định**, transaction được cấu hình đúng và `skip(...)` whitelist exception đó. Đừng dùng lỗi database không ổn định để kỳ vọng thứ tự callback cố định.

### 12.3. Kiểm thử biên, đồng thời và restart

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| `skipLimit(3)`, chính xác 3 item lỗi | Các item được skip và ghi audit đủ; step có thể hoàn thành |
| `skipLimit(3)`, item lỗi thứ 4 | Step thất bại vì hết ngân sách, không xem item thứ 4 là skip được chấp nhận |
| Exception không thuộc whitelist | Step thất bại, không sinh quarantine như item được skip |
| Processor trả `null` | Filter, **không** gọi skip listener |
| Lỗi transient được retry rồi thành công | Không ghi bản quarantine giả |
| Chunk rollback làm item được thử lại | Sink không sinh record trùng không kiểm soát |
| Hai partition xử lý khác tenant | Listener không rò partition/file/source ID của nhau |
| Pool tái sử dụng thread | Metadata từ worker trước không còn trong worker sau |
| Worker bị lỗi rồi restart | Audit item unique không tăng giả do attempt mới |
| Worker đã hoàn tất sau khi skip item | Có runbook replay riêng để sửa những item đó |
| Remote broker phát lại request | Quarantine và business output có cơ chế idempotency |
| Audit store không ghi được | Step xử lý theo chính sách bắt buộc: fail-closed hoặc cơ chế bù đáng tin cậy |

### 12.4. Không nên kiểm thử bằng cách đếm số lần writer được gọi

Trong fault-tolerant step, writer có thể bị gọi lại sau rollback để xác định item lỗi. Vì vậy, “writer được gọi ba lần” không có nghĩa “ba item đã bị skip”. Hãy assert **skip counters**, **quarantine records unique**, **business output** và trạng thái transaction.

## 13. Runbook vận hành khi số skip tăng đột biến

1. **Xác định phạm vi:** JobInstance, JobExecution, StepExecution, partition key, input snapshot, số skip đọc/xử lý/ghi.
2. **Kiểm tra loại lỗi:** Có một mã lỗi mới do schema/parser hoặc toàn bộ worker đều lỗi như nhau không?
3. **Đọc audit/quarantine:** Đủ source key và phase hay có nhiều lỗi `UNKNOWN` không xác định được item?
4. **Đối chiếu transaction:** Listener ghi ở cùng transaction hay gửi ra hệ thống ngoài? Có rollback/retry gần thời điểm lỗi không?
5. **Kiểm tra trạng thái nguồn:** File/manifest có bị thay đổi sau khi job bắt đầu không?
6. **Đánh giá ngân sách:** `skipLimit` là mỗi worker `StepExecution`, không tự đặt giới hạn tổng cho toàn job.
7. **Ngăn publish nếu cần:** Với pipeline quan trọng, ghi vào staging và kiểm toán chất lượng trước khi phát hành downstream.
8. **Khắc phục lỗi gốc:** Sửa dữ liệu, parser, validation hoặc writer; không tăng ngưỡng skip một cách phản xạ.
9. **Phục hồi có kiểm soát:** Restart phần việc chưa hoàn tất theo metadata; item đã skip trong partition hoàn tất cần replay riêng.
10. **Đối soát sau khôi phục:** Tập business keys không thiếu/trùng; quarantine thay đổi trạng thái chính xác; cảnh báo trở lại ngưỡng bình thường.

### Cần theo dõi những gì?

| Metric/quan sát | Mục tiêu |
| --- | --- |
| `readSkipCount` / `processSkipCount` / `writeSkipCount` | Phân biệt loại skip đang tăng |
| Số item lỗi **unique** theo snapshot và reason code | Không nhầm item với số attempt/callback |
| Số bản quarantine `NEW` và thời gian chờ sửa | Theo dõi backlog xử lý bù |
| `rollbackCount`, transaction latency | Phát hiện writer lỗi/lặp do transaction |
| Throughput, CPU, log volume | Đo overhead khi exception tăng |
| Tỷ lệ lỗi theo tenant/file/partition | Phát hiện lỗi cục bộ bị che bởi tổng |
| Số item replay thành công và vẫn lỗi | Đánh giá hiệu quả phục hồi |

## 14. Bài tập tình huống

Một job dùng 6 worker partition nhập dữ liệu khách hàng từ các file CSV, mỗi worker có `skipLimit(10)`. Listener được viết là singleton và giữ hai field mutable `currentFile`, `currentPartition`, được gán trong `beforeStep()`. Callback `onSkipInRead` luôn lưu `sourceKey = currentFile + ":" + lineNumber` vào database audit **khác transaction** của writer.

Trong lúc chạy, hai worker báo cùng một file trong audit; sau retry xuất hiện ba bản audit cho cùng dòng nguồn. Một worker hoàn thành dù đã skip 8 dòng. Hôm sau, nhóm vận hành restart job và kỳ vọng tám dòng đó tự được xử lý lại.

**Câu hỏi:**

1. Vì sao listener có thể ghi nhầm tên file giữa các worker?
2. Vì sao audit ở database khác transaction có thể trùng với rollback/retry?
3. Nên thiết kế khóa nào để chống ghi nhận một dòng CSV nhiều lần?
4. Có thể dùng `StepExecutionId` làm khóa dedupe chính không?
5. Vì sao restart job không tự sửa tám dòng đã skip ở worker `COMPLETED`?
6. Bạn sẽ bổ sung những bài test nào trước khi đưa job trở lại production?

**Định hướng trả lời:** Mutable singleton tạo **cross-talk**; dùng listener stateless hoặc `@StepScope` bind file/partition per worker. Audit ngoài transaction cần idempotency/upsert và có thể dùng outbox để bảo đảm giao sự kiện. Identity bền vững nên là `sourceVersion + fileId + lineNumber (+ phase)`; `StepExecutionId` thay đổi theo attempt nên chỉ dùng để truy dấu. Một partition đã hoàn tất thường không chạy lại khi restart; cần sửa input và replay từ quarantine bằng một workflow được phê duyệt. Test tối thiểu: đồng thời hai file, rollback, retry, restart, audit failure, duplicate source key và đối soát output.

## Tài liệu tham khảo

- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): các listener trong chunk-oriented step và ý nghĩa callback.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip policy, skip limit và phân loại exception.
- [Spring Batch API — SkipListener](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/SkipListener.html): chữ ký `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite`.
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry và lỗi transient.
- [Spring Batch Reference — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` và truyền metadata theo worker.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, multi-threaded steps và remote processing.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, restart và item replay.

> **Ghi nhớ:** `SkipListener` là nơi nhận diện **item thực sự bị skip** và lý do của nó, không phải nơi quyết định skip hay thay thế idempotency. Muốn dùng an toàn trên workload lớn, hãy ghi audit có **source key bền vững, phase, reason**, bảo đảm transaction/dedupe phù hợp, tách state theo worker, kiểm thử rollback/restart và có workflow xử lý lại từ quarantine.
