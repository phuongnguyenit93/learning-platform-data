# Không skip lỗi hạ tầng tùy tiện trong Spring Batch

> **Chương:** Skip và recovery
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và xử lý phân tán. Bài này tập trung vào phân loại lỗi, retry/rollback/restart, giám sát sự cố và **không biến lỗi hệ thống thành việc mất item không được phép** khi tăng số worker.

Trong chunk-oriented processing, khả năng `skip` giúp một job tiếp tục khi gặp **bản ghi lỗi có thể chấp nhận loại khỏi luồng**. Nhưng nếu database mất kết nối, API đối tác timeout hoặc broker không nhận phản hồi, việc bỏ qua item chỉ vì “đã retry vài lần” có thể làm dữ liệu thiếu mà job vẫn báo `COMPLETED`. Lỗi hạ tầng thường không chứng minh item nghiệp vụ sai; ngược lại, nó cho thấy **hệ thống không đủ điều kiện xử lý hoặc chưa biết chắc kết quả**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **lỗi dữ liệu có thể skip** với **lỗi hạ tầng tạm thời**, **lỗi hệ thống kéo dài** và **tác dụng phụ chưa rõ đã commit hay chưa**.
2. Cấu hình `faultTolerant()` để chỉ skip exception có chủ đích, retry lỗi phù hợp có giới hạn và **fail step khi hạ tầng không phục hồi**.
3. Giải thích vì sao `skipLimit` không bảo vệ dữ liệu nếu dùng `skip(Exception.class)`, đặc biệt với nhiều partition và các lần restart.
4. Thiết kế transaction, checkpoint, idempotency và reconciliation cho lỗi xảy ra trong reader, processor, writer và remote worker.
5. Kiểm thử hệ thống khi DB outage, timeout, rollback, retry exhausted, hai worker cùng lỗi và broker phát lại message.
6. Xây dựng guardrails, cảnh báo và runbook để dừng job an toàn rồi khôi phục từ `JobRepository`, thay vì “skip cho job xanh”.

## 1. Tình huống: 20 bản ghi xấu khác với 20.000 bản ghi không ghi được

Giả sử hệ thống nhập **2 triệu đơn hàng** chia thành 8 partition. Trong một lần chạy:

- 12 dòng CSV sai định dạng ngày hoặc thiếu mã đơn hàng.
- Database đích mất kết nối trong 3 phút khi worker đang ghi.
- Một API làm giàu dữ liệu trả timeout, không rõ request đã được xử lý hay chưa.

Ba tình huống này **không thể dùng cùng một chính sách skip**:

| Sự cố | Bản chất | Hành động ưu tiên | Vì sao |
| --- | --- | --- | --- |
| Một dòng CSV sai format rõ ràng | Lỗi của **record cụ thể** | Skip có kiểm soát và quarantine, nếu nghiệp vụ cho phép | Chỉ một item không hợp lệ; cần sửa/replay |
| Database không kết nối được | Lỗi hạ tầng có thể ảnh hưởng **mọi item** | Retry có giới hạn, rồi **fail/stop** nếu chưa phục hồi | Item có thể hoàn toàn hợp lệ |
| API timeout sau khi đã gửi lệnh | **Trạng thái kết quả chưa rõ** | Reconcile theo business operation ID; fail/defer có trạng thái bền vững | Skip có thể che side effect đã xảy ra |
| Schema DB thay đổi bất ngờ | Lỗi hệ thống/cấu hình | **Fail fast**, điều tra deploy/migration | Retry/skip từng item không sửa được nguyên nhân |
| Hết dung lượng disk hoặc queue đầy | Lỗi tài nguyên dùng chung | Backpressure, alert, dừng/khôi phục | Skip sẽ làm thất lạc dữ liệu hợp lệ |

Nếu cấu hình `skip(Exception.class)`, mỗi item gặp lỗi kết nối có thể trở thành một “item hỏng” giả. Job có thể tiếp tục đến khi chạm `skipLimit`, lãng phí tài nguyên, che nguyên nhân gốc và làm sai tỷ lệ lỗi nghiệp vụ.

**Nguyên tắc nền tảng:** *“Không xử lý được lúc này” khác “bản ghi này không được phép xử lý”*. Chỉ nhóm thứ hai mới có thể cân nhắc skip.

## 2. Skip, retry, fail, filter và defer không thay thế cho nhau

~~~mermaid
flowchart TD
    A["Gặp exception trong reader / processor / writer"] --> B{"Lỗi thuộc về item hay hệ thống?"}
    B -- "Dữ liệu sai xác định" --> C{"Nghiệp vụ cho phép skip?"}
    C -- "Có và còn skip budget" --> Q["Skip item + ghi quarantine"]
    C -- "Không / quá giới hạn" --> F["FAILED: không tự loại item"]
    B -- "Hạ tầng tạm thời" --> R["Retry có timeout và backoff"]
    R --> T{"Phục hồi trong budget?"}
    T -- "Có" --> S["Commit kết quả hợp lệ"]
    T -- "Không" --> F
    B -- "Kết quả external không rõ" --> U["UNKNOWN + reconciliation / stop an toàn"]
    B -- "Bug / schema / cấu hình" --> F
~~~

Sơ đồ là **chính sách đề xuất**, không phải thứ tự callback cố định của mọi reader/writer trong framework. Với fault-tolerant chunk step, rollback, retry và cơ chế cô lập item lỗi có thể xen giữa các nhánh; phải kiểm thử trên cấu hình thực tế.

| Cơ chế | Dùng khi nào? | Hệ quả đối với dữ liệu |
| --- | --- | --- |
| `skip(...)` | Một loại lỗi **cụ thể của item** được phép loại bỏ | Item đó chưa được áp dụng, cần dấu vết |
| `retry(...)` | Một thao tác có khả năng thành công nếu thử lại | Attempt có thể lặp; phải xét transaction và idempotency |
| `filter` bằng processor trả `null` | Item **hợp lệ** nhưng không thuộc tập phải ghi | Tăng `filterCount`, không phải skip |
| Fail step/job | Không thể bảo đảm kết quả hợp lệ tại thời điểm chạy | Giữ metadata để điều tra và restart |
| Defer/recovery | Hợp đồng nghiệp vụ cho phép công việc chờ xử lý sau | Phải lưu `PENDING/UNKNOWN` bền vững; không bỏ item âm thầm |
| Rollback | Hủy các thay đổi **trong transaction chưa commit** | Không tự hoàn tác HTTP, email hoặc datasource ngoài transaction |

Lỗi hạ tầng tạm thời thường nên **retry rồi fail**, không chuyển sang filter hay skip chỉ để step tiếp tục. Với một số workload không bắt buộc hoàn tất ngay, có thể chuyển toàn bộ công việc sang durable deferred queue, nhưng đó là **một hợp đồng workflow được thiết kế riêng**, không phải bỏ qua exception và trả `null`.

## 3. Phân loại exception theo nguyên nhân, không theo mức độ phiền toái

### 3.1. Lỗi dữ liệu có thể skip

Ví dụ phù hợp:

- `FlatFileParseException` cho một dòng CSV không parse được và có file/line để sửa.
- `InvalidOrderRecordException` do validator chủ động phát ra khi item thiếu trường bắt buộc.
- Một exception **nghiệp vụ chuyên biệt** mô tả một record từ chối được xác định rõ, có định danh nguồn và cách replay.

Điều kiện để skip có trách nhiệm:

1. Quy tắc dữ liệu rõ ràng và lỗi **không ảnh hưởng khả năng xử lý những item khác**.
2. Nghiệp vụ chấp nhận kết quả thiếu item tạm thời.
3. Có `skipLimit` và giới hạn **toàn job/toàn snapshot** tương ứng.
4. `SkipListener` ghi nhận source key, loại lỗi và tình trạng quarantine.
5. Có quy trình sửa, replay hoặc quyết định từ chối vĩnh viễn.

### 3.2. Lỗi hạ tầng transient

Ví dụ:

- `TransientDataAccessException` và các subclass được Spring JDBC/DAO dịch đúng từ lỗi DB tạm thời.
- Lỗi kết nối mạng ngắn, mất broker connection, rate limit có cơ chế thử lại.
- Deadlock/lock contention nếu thao tác có thể retry trong transaction mới và không tạo side effect ngoài DB.

**Transient không đồng nghĩa chắc chắn retry an toàn.** Một lỗi mạng sau khi gửi request **không chứng minh** bên nhận chưa commit. Một lỗi DB commit timeout cũng có thể mang kết quả chưa rõ nếu caller không biết transaction đã hoàn tất hay chưa. Chọn retry dựa trên **semantics operation**, không chỉ tên exception.

### 3.3. Lỗi hệ thống không giải quyết được bằng retry item

Ví dụ:

- Sai credentials/permission; schema, migration hoặc SQL không tương thích.
- Hết disk, thiếu quota không thể giải quyết nhanh, cấu hình Kafka topic/broker sai.
- Bug lập trình: invariant vỡ, `NullPointerException` không mong đợi.
- Thiếu dữ liệu tham chiếu dùng chung, chẳng hạn bảng tỷ giá bắt buộc trống do pipeline upstream thất bại.

Các lỗi này cần **fail fast, alert và sửa nguyên nhân gốc**. Nhiều lần thử với cùng input và điều kiện hệ thống không đổi thường không làm lỗi biến mất.

### 3.4. Lỗi dữ liệu biểu hiện dưới dạng lỗi DB

Đây là trường hợp tinh tế. Ví dụ unique constraint bị vi phạm vì record nguồn bị trùng theo business key. Tùy hợp đồng:

- Có thể là **duplicate replay hợp lệ**: writer idempotent phải xác nhận payload tương đương và no-op.
- Có thể là **conflict dữ liệu nghiêm trọng**: cùng operation ID nhưng amount khác, phải fail/quarantine theo quy trình.
- Có thể là **lỗi triển khai**: partition overlap hoặc writer đặt sai key.

**Không** xử lý cả nhóm bằng `skip(DataIntegrityViolationException.class)`. Một lớp exception SQL có thể chứa nhiều nguyên nhân, và việc skip tất cả có thể che mất dữ liệu hoặc tác dụng phụ trùng.

## 4. Cấu hình chống skip lỗi hạ tầng bằng Spring Batch 5.x

Ví dụ dưới đây giả định một chunk step đọc đơn hàng, xác thực dữ liệu và ghi database. Chỉ lỗi parse/validation **đã được định nghĩa** mới được skip; lỗi DB transient có một số lượt thử, rồi fail nếu không phục hồi.

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
import org.springframework.dao.DataAccessException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputOrder> reader,
        ItemProcessor<InputOrder, OutputOrder> processor,
        ItemWriter<OutputOrder> writer,
        SkipListener<InputOrder, OutputOrder> skipListener) {

    ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
    backoff.setInitialInterval(200L);
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(2_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<InputOrder, OutputOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            // Chỉ các lỗi DB được phân loại transient mới retry.
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .backOffPolicy(backoff)
            // Bỏ qua lỗi của một record, không phải lỗi hạ tầng.
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderRecordException.class)
            .skipLimit(10)
            // Rào chắn tường minh: lỗi truy cập DB không skippable.
            .noSkip(DataAccessException.class)
            .listener(skipListener)
            .build();
}
~~~

`InputOrder`, `OutputOrder` và `InvalidOrderRecordException` là kiểu ứng dụng cần khai báo. Đoạn code minh họa **Spring Batch 5.x** cùng Spring Retry/Spring DAO tương thích và các bean reader/processor/writer phù hợp. Cần cấu hình transaction manager thực sự quản lý tài nguyên ghi nghiệp vụ.

### Hiểu chính xác từng cấu hình

| Cấu hình | Chức năng |
| --- | --- |
| `.faultTolerant()` | Bật builder có retry/skip cho chunk processing |
| `.retry(TransientDataAccessException.class)` | Cho phép retry loại lỗi DB transient đã phân loại |
| `.retryLimit(3)` | Đặt giới hạn attempt theo retry policy của framework; kiểm thử số calls thực tế |
| `.backOffPolicy(backoff)` | Giãn các lần retry; tránh retry dồn dập |
| `.skip(FlatFileParseException.class)` | Có thể skip dòng parse lỗi nếu còn budget |
| `.skip(InvalidOrderRecordException.class)` | Có thể skip record sai validation |
| `.skipLimit(10)` | Tối đa 10 skip được chấp nhận **trong một StepExecution**, tính chung read/process/write |
| `.noSkip(DataAccessException.class)` | Nhấn mạnh không skip nhóm lỗi DB, kể cả nếu policy khác mở rộng |
| `.listener(skipListener)` | Ghi nhận **item thực sự được skip**, không phải mọi exception từng phát sinh |

**Hai điểm cần kiểm tra tại runtime:**

1. Spring có thể bọc exception nhiều lớp hoặc dùng exception translator khác nhau. Nếu code chỉ retry `TransientDataAccessException` nhưng thực tế nhận loại `SQLTransientException` không được dịch, thao tác có thể fail ngay. Hãy quan sát **exception thực tế** và chỉ bổ sung loại retryable đã được chứng minh an toàn.
2. Cơ chế read/process/write, cách retry, transaction và callback không hoàn toàn giống nhau. Ví dụ writer có thể bị gọi lại sau rollback để phân lập item lỗi. Không suy ra mọi item có đúng ba HTTP/SQL calls chỉ từ `retryLimit(3)`.

### Vì sao không sử dụng các cấu hình này?

~~~java
// Nguy hiểm: chấp nhận skip cả lỗi hệ thống.
.faultTolerant()
.skip(Exception.class)
.skipLimit(100_000)
~~~

~~~java
// Cũng nguy hiểm: coi mất kết nối database là lỗi item.
.faultTolerant()
.skip(DataAccessException.class)
.skipLimit(10_000)
~~~

Hai ví dụ trên **không phải giải pháp recovery**. Chúng biến lỗi không xử lý được thành “dữ liệu nguồn lỗi”, rồi có thể gây mất dữ liệu hợp lệ. Hãy dùng exception whitelist hẹp và policy fail rõ ràng.

## 5. Phân biệt lỗi validation với lỗi hệ thống trong processor

Một processor nên phân loại lỗi tại ranh giới **được hiểu rõ**:

~~~java
public final class InvalidOrderRecordException
        extends RuntimeException {
    public InvalidOrderRecordException(String message) {
        super(message);
    }
}

public final class OrderValidator
        implements ItemProcessor<InputOrder, OutputOrder> {

    @Override
    public OutputOrder process(InputOrder input) {
        if (input.orderCode() == null
                || input.orderCode().isBlank()) {
            throw new InvalidOrderRecordException(
                    "Thiếu orderCode, sourceId=" + input.sourceId());
        }

        if (input.amountMinor() <= 0) {
            throw new InvalidOrderRecordException(
                    "Amount không hợp lệ, sourceId=" + input.sourceId());
        }

        return new OutputOrder(
                input.sourceId(),
                input.orderCode(),
                input.amountMinor());
    }
}
~~~

`InputOrder` và `OutputOrder` là các record/POJO do dự án định nghĩa; ví dụ dùng `sourceId()`, `orderCode()` và `amountMinor()`. Cần thêm import `ItemProcessor`; khi viết class Java thật, đặt mỗi `public` top-level class vào file riêng. Mã exception message chỉ nên chứa source ID an toàn, không log số thẻ, tên người dùng hoặc dữ liệu nhạy cảm.

**Không nên viết:**

~~~java
try {
    return enrichFromDatabase(input);
} catch (Exception ignored) {
    return null; // Filter ngầm cả khi DB mất kết nối!
}
~~~

`ItemProcessor.process(...)` trả `null` sẽ tăng `filterCount`, **không tăng skipCount**, không gọi `SkipListener`. Đây là cách đặc biệt nguy hiểm để che sự cố hạ tầng: job có thể báo thành công nhưng tất cả dữ liệu đáng ra được ghi đều bị “lọc”.

Một thiết kế an toàn hơn: chỉ ném `InvalidOrderRecordException` khi **bản ghi** thật sự sai quy tắc; với lỗi DB hoặc API, để lỗi có kiểu riêng được xử lý bằng retry/fail/reconcile, không trả `null`.

## 6. Khi hết retry: fail, không tự động skip

Với ví dụ trong phần 4:

~~~text
Worker ghi một chunk:
  Attempt #1 -> TransientDataAccessException
  Attempt #2 -> TransientDataAccessException
  Attempt #3 -> TransientDataAccessException

Sau khi retry policy không cho thử tiếp:
  - DataAccessException không skippable
  - Worker step có thể FAILED
  - Giữ metadata/checkpoint phục vụ restart
  - Không tự xem 200 item trong chunk là "dữ liệu xấu"
~~~

Con số attempts là **minh họa của chính sách được kiểm thử**, không phải cam kết số lần gọi writer tuyệt đối trong mọi điều kiện. Khi một chunk rollback, framework có thể thực thi thêm những lời gọi khác phụ thuộc reader/writer, retry/skip, transaction và lần restart.

### Cảnh báo retry không an toàn

Ngay cả lỗi `TransientDataAccessException` cũng cần xét **tác dụng phụ**:

- Retry lại một transaction database đã rollback thường có thể an toàn nếu writer thuần DB và dữ liệu được bảo vệ bởi transaction.
- Nếu processor/writer đã gửi email, message hoặc HTTP request trước khi DB lỗi, replay có thể gửi lại.
- Nếu commit DB đã thành công nhưng caller bị timeout và không xác định được kết quả, cần idempotency key/kiểm tra business ledger trước khi thử lại.

**Retry và fail không đủ để đạt exactly-once side effect.** Chúng chỉ là một phần của recovery; dữ liệu đích phải có unique business key/idempotent operation hoặc quy trình reconcile.

## 7. Transaction: phân biệt rollback thực với kết quả chưa rõ

### 7.1. Writer và metadata cùng transaction phù hợp

Khi business database và checkpoint của `JobRepository` thực sự tham gia cùng transaction atomic phù hợp, rollback có thể đưa cả dữ liệu chưa commit và tiến độ step về trạng thái trước đó. Điều này hỗ trợ restart từ checkpoint.

~~~mermaid
sequenceDiagram
    participant S as Worker chunk
    participant D as Business DB
    participant R as JobRepository
    S->>D: Write 200 items trong transaction
    S->>R: Lưu checkpoint/metadata theo lifecycle
    Note over D,R: Atomic chỉ khi được điều phối cùng transaction
    S--xD: Lỗi trước commit
    D-->>S: Rollback
    Note over S: Retry hoặc restart từ checkpoint trước
~~~

**Không suy ra atomic chỉ từ tên `transactionManager` hoặc annotation `@Transactional`.** Nếu job dùng business DB và repository DB khác nhau, một transaction manager địa phương thường không bao trùm cả hai. Phải biết tài nguyên nào được enlist và kiểm thử crash windows.

### 7.2. Writer gọi HTTP hoặc message broker

~~~text
Item A -> Writer gọi HTTP API -> API commit thành công
                                 |
                                 +-- response bị mất
                                 |
                                 +-- worker ném timeout
                                 |
                                 +-- chunk transaction rollback
                                 |
                                 +-- item A được xử lý lại
~~~

Lúc này:

- Rollback của Batch **không** hoàn tác transaction HTTP đã commit ở đích.
- Timeout không chứng minh API chưa thực thi.
- Skip item A sau timeout cũng không chứng minh tác dụng phụ không xảy ra.
- Retry bằng key mới có thể tạo side effect **lần thứ hai**.

**Cách an toàn:** tạo stable business operation ID; phía nhận xử lý idempotent; với trạng thái không chắc chắn, tra cứu kết quả theo operation ID và lưu `UNKNOWN/PENDING_CONFIRMATION` cho tới khi xác nhận. Nếu API không hỗ trợ idempotency hoặc truy vấn trạng thái, không được hứa “exactly once” từ riêng Spring Batch.

### 7.3. Dùng transactional outbox khi cần gửi event

Nếu một chunk ghi database và phát sự kiện `OrderImported`:

1. Writer ghi business row và **outbox row** trong cùng transaction phù hợp.
2. Sau commit, dispatcher đọc outbox và publish.
3. Dispatcher có thể publish lại sau timeout; event ID phải **ổn định** qua retry.
4. Consumer downstream dùng inbox/dedupe hoặc operation ID để chặn effect lặp.

Outbox làm ý định gửi trở nên bền vững, **không tự biến broker delivery thành đúng một lần đến mọi hệ thống**. Ngược lại, “skip khi publish thất bại” mà không có outbox có thể làm mất event hợp lệ.

## 8. SkipListener không phải nơi ghi lỗi DB như item hỏng

`SkipListener<I,O>` có ba callback:

~~~java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
~~~

Callback nên được dùng cho **item thực sự được skip** sau khi framework xác định có thể bỏ qua. Retry transient thành công **không** phải skipped item. Một lỗi hạ tầng không skippable làm step fail và cần được ghi vào **log/metric/alert sự cố** hoặc `StepExecutionListener`, không tự đưa tất cả item lỗi DB vào quarantine như “bad record”.

### Ví dụ listener ghi lỗi dữ liệu

~~~java
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public final class OrderDataSkipListener
        implements SkipListener<InputOrder, OutputOrder> {

    private final DataQuarantineSink sink;
    private final String sourceVersion;
    private final String fileId;

    public OrderDataSkipListener(
            DataQuarantineSink sink,
            String sourceVersion,
            String fileId) {
        this.sink = sink;
        this.sourceVersion = sourceVersion;
        this.fileId = fileId;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        if (!(error instanceof FlatFileParseException parsed)) {
            throw new IllegalStateException(
                    "Read skip thiếu source position đáng tin", error);
        }
        String key = fileId + ":" + parsed.getLineNumber();
        sink.record(sourceVersion, key, "READ", "PARSE_ERROR");
    }

    @Override
    public void onSkipInProcess(InputOrder item, Throwable error) {
        sink.record(sourceVersion, item.sourceId(),
                "PROCESS", "INVALID_ORDER");
    }

    @Override
    public void onSkipInWrite(OutputOrder item, Throwable error) {
        sink.record(sourceVersion, item.sourceId(),
                "WRITE", "REJECTED_ITEM");
    }
}
~~~

`DataQuarantineSink` là contract do ứng dụng tự định nghĩa và phải lưu bền vững, idempotent. Trong dự án thật, mapping reason code cần kiểm tra exception chính xác; không gắn mọi write exception thành `REJECTED_ITEM`. Ví dụ giả định **chỉ các exception dữ liệu chuyên biệt** mới có thể đi qua listener.

### Lỗi đọc cần định danh vật lý

Nếu reader parse CSV lỗi trước khi tạo `InputOrder`, không thể dùng business ID của một object chưa tồn tại. Dùng `sourceVersion + fileId + logicalRecordPosition`, với ngữ nghĩa record/dòng được kiểm tra trên parser thực tế. Một khóa chung `UNKNOWN` cho mọi read skip là sai vì nhiều dòng lỗi sẽ bị gộp.

### Không để listener làm rò dữ liệu giữa worker

Trong local partitioning, nếu listener singleton giữ trường mutable `currentFileId` thay đổi ở `beforeStep`, worker B có thể ghi đè tên file mà worker A đang dùng. Dùng `@StepScope` để bind metadata per `StepExecution` hoặc viết listener stateless hoàn toàn. Quarantine sink phải thread-safe và dùng unique key ở database; scope của bean không thay thế transaction.

## 9. Vì sao skipLimit không đủ bảo vệ toàn job khi scale

Trong partitioned job, mỗi worker có `StepExecution` riêng với `readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipLimit`.

Ví dụ manager tạo **16 worker**, mỗi worker cấu hình `skipLimit(10)`:

~~~text
Ngưỡng riêng worker = tối đa 10 skip được chấp nhận
Số worker           = 16

Nếu 16 worker đều dùng hết ngân sách:
  Tổng số skip được chấp nhận trong những executions
  có thể lên tới 160, không phải 10.
~~~

Nếu chuyển lỗi `DataAccessException` thành skippable, một outage chung có thể dẫn tới **nhiều worker cùng tiêu thụ ngân sách**, khiến số item bị bỏ đi tăng nhanh. Khi các worker khác đã commit, rollback riêng worker lỗi **không** hoàn tác dữ liệu từ worker đã hoàn thành.

### Hai tầng guardrails

| Tầng | Mục tiêu | Thiết kế |
| --- | --- | --- |
| **Worker StepExecution** | Chặn một partition có quá nhiều bản ghi sai | Exception whitelist + `skipLimit` thấp, cảnh báo |
| **JobInstance/snapshot** | Chặn tổng chất lượng dữ liệu không đạt | Đếm item lỗi unique, tỷ lệ theo tenant/file, publish gate |
| **Hạ tầng toàn cụm** | Dừng cả workload khi DB/API/broker chung bị lỗi | Circuit breaker/health gate/incident coordinator; worker failure propagation |
| **Workflow downstream** | Không công bố dữ liệu thiếu/trùng | Staging, reconciliation, publish có kiểm soát |

**Không dùng `static AtomicInteger` làm ngân sách toàn job**: nó mất khi restart và không chia sẻ qua nhiều JVM. Nếu nghiệp vụ cần quota toàn cục chính xác, dùng store có thao tác atomic, xem xét rollback/replay và identity của item; hoặc validate trước và publish sau khi đối soát.

## 10. Multi-threaded step và parallel steps: lỗi hạ tầng khuếch đại

### Multi-threaded step

Một `TaskExecutor` cho cùng một step có thể làm nhiều chunk xử lý đồng thời. Khi DB lỗi, nhiều thread có thể retry cùng lúc:

- Mỗi retry chiếm thread và một phần tài nguyên.
- Connection pool hết slot có thể tạo thêm timeout, khiến lỗi lan rộng.
- Reader/writer stateful không tự thread-safe; `@StepScope` là **theo StepExecution**, không phải theo chunk thread.
- Một biến `lastProcessedId` được nhiều thread cập nhật có thể tạo checkpoint không đúng thứ tự.

**Đừng tăng retryLimit để bù thread starvation.** Đo queue, pool connection, lock wait, transaction latency và chọn giới hạn concurrency phù hợp.

### Parallel steps

Hai flow steps chạy song song có thể cùng dùng một database; một outage ảnh hưởng cả hai. Một step fail có thể kéo job về trạng thái không hoàn thành tùy flow và transition, trong khi step còn lại có thể đã commit nhiều chunk.

Tránh cố skip hàng loạt exception để ép các bước độc lập tiếp tục: phải tách rõ **step nào cần dừng**, step nào có thể phục hồi an toàn và điều kiện tổng hợp khi job kết thúc.

### Partitioning

~~~mermaid
flowchart TB
    M["Partition manager"] --> A["Worker A: DB write OK<br/>COMPLETED"]
    M --> B["Worker B: DB timeout<br/>Retry → FAILED"]
    M --> C["Worker C: DB timeout<br/>Retry → FAILED"]
    M --> D["Worker D: đã commit một số chunks"]
    A --> R[("JobRepository / metadata")]
    B --> R
    C --> R
    D --> R
    R --> S["Operator: điều tra & restart<br/>cùng JobInstance"]
~~~

Một worker `FAILED` không đồng nghĩa các worker khác chưa ghi dữ liệu. Khi khôi phục, dùng `JobRepository`, checkpoint và business identity để xác định những phần cần xử lý lại; tránh chạy lại toàn bộ input dưới **JobInstance mới** mà không có kế hoạch idempotency.

## 11. Remote chunking/partitioning: khi timeout không đồng nghĩa worker thất bại

### Remote chunking

Manager gửi chunk request qua broker; worker xử lý và trả reply. Một timeout ở manager có thể là:

1. Message chưa được broker giao.
2. Worker đã nhận nhưng chưa xử lý.
3. Worker đã ghi dữ liệu và commit, **reply/ACK bị mất**.
4. Reply đã tới broker nhưng manager chưa nhận hoặc chưa cập nhật tiến độ.

**Không skip cả chunk vì manager không nhận reply đúng hạn**. Bản chất đây là sự cố giao tiếp/trạng thái chưa rõ, không phải 200 item của chunk đều không hợp lệ.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant W as Worker
    participant D as Business DB
    M->>Q: ChunkRequest C-17
    Q->>W: Deliver C-17
    W->>D: Process/write
    D-->>W: Commit
    W--xM: Reply không tới
    M->>M: Timeout
    Note over M: Không được suy ra item sai
    Q->>W: Redelivery nếu transport yêu cầu
    W->>D: Dedupe theo business operation key
    W-->>M: Reply/correlation hợp lệ
~~~

Hành vi redelivery, ACK, reply correlation phụ thuộc broker và adapter thực tế, không phải một cam kết chung cho mọi cấu hình Spring Batch Integration.

### Remote partitioning

Một worker `StepExecution` chạy ở JVM khác có thể vẫn đang thực thi khi manager cho rằng worker timeout. Nếu khởi động worker mới, **hai owners** có thể cùng làm một partition.

Biện pháp:

- Kiểm tra `StepExecution`/`JobRepository` và heartbeat/claim tùy kiến trúc.
- Có lease/fencing khi cần ngăn worker cũ tiếp tục ghi sau failover.
- Bảo vệ business effect tại đích bằng unique business operation key/idempotency.
- Chỉ restart cùng `JobInstance` theo policy, giữ partition key → input range ổn định.
- Đối soát dữ liệu trước khi chuyển trạng thái downstream/publish.

**Không coi metadata failure/timeout là bằng chứng external side effect chưa xảy ra.** Nếu worker đã gọi API ngoài transaction, phải tra cứu trạng thái thực tế tại đích.

## 12. Backoff, timeout, circuit breaker và fail-fast

Một chính sách lỗi hạ tầng tốt không phải “retry thật nhiều”, mà là **retry có giới hạn và đo được**.

### Backoff có giới hạn

Giả sử các attempts được cấu hình để chờ `200 ms → 400 ms` giữa những lần thử theo `ExponentialBackOffPolicy`. Các giá trị này **chỉ minh họa**, không phải khuyến nghị mặc định. Một outage kéo dài nhiều phút không tự được giải quyết bằng chờ vài trăm mili giây.

Khi nhiều workers cùng retry, thêm **jitter** hoặc giải pháp throttling phù hợp để không khiến toàn bộ pods thức dậy và gọi cùng lúc. `ExponentialBackOffPolicy` cơ bản chỉ minh họa exponential backoff, **không mặc định hứa có jitter**.

### Deadline cho mỗi request

Một thao tác có:

- Connect timeout;
- Read/response timeout;
- Tổng deadline;
- Retry budget và thời gian backoff;
- Giới hạn concurrency.

Không có timeout, một thread có thể treo lâu và chiếm connection slot. Không có budget, một item có thể thử liên tục khi hạ tầng đang lỗi.

### Circuit breaker và health gate

Khi tỉ lệ lỗi vượt ngưỡng chung:

1. Ngừng cấp thêm công việc mới cho những worker phụ thuộc dịch vụ lỗi.
2. Cho phép inflight chunk hoàn tất/rollback theo ranh giới an toàn.
3. Alert rõ backend nào lỗi, từ thời điểm nào, ảnh hưởng bao nhiêu partitions.
4. Thử phục hồi với lưu lượng thấp khi dependency khỏe.
5. Restart/resume từ checkpoint có thể tin cậy và đối soát business effects.

**Circuit breaker không thay `JobRepository` hay transaction**; nó giúp ngăn khuếch đại outage và giảm request storm.

### Retry lồng nhau

~~~text
Spring Batch faultTolerant retryLimit(3)
  × HTTP client retry(2)
    × broker redelivery / job restart

Tổng lời gọi thực tế có thể vượt xa số attempts
người vận hành đọc từ cấu hình một tầng.
~~~

Phân công **tầng chịu trách nhiệm retry chính** và đo số requests thật. Không retry một lệnh thanh toán không idempotent chỉ vì một exception có chữ “Timeout”.

## 13. Dùng metadata để điều tra thay vì biến lỗi thành skip

Trong schema mặc định, `BATCH_STEP_EXECUTION` lưu status và counters cho từng step/worker execution.

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

Chú ý table prefix có thể thay đổi so với `BATCH_`; nên dùng `JobExplorer` nếu muốn đọc metadata qua API. Manager và worker có executions riêng; **không cộng các counters của manager lẫn worker** rồi coi là số item duy nhất.

### Cần xem thêm những gì?

| Tín hiệu | Cách hiểu |
| --- | --- |
| `readSkipCount` / `processSkipCount` / `writeSkipCount` | Số skip được ghi nhận trong execution; dùng cho lỗi dữ liệu |
| `rollbackCount` tăng mạnh | Writer/transaction có thể đang lỗi; cần kiểm tra exception |
| `BatchStatus.FAILED` | Step/job không hoàn tất; cần điều tra và restart policy |
| `ExitStatus`, failure exceptions | Mô tả nguyên nhân/exit rule; không thay thế xác minh transaction |
| Kết nối DB đang cạn | Nhiều worker retry quá mức hoặc downstream chậm |
| Queue lag, broker redelivery | Hệ thống message có thể đang phát lại work unit |
| Số item `UNKNOWN`/reconcile pending | External effect chưa xác nhận, không nên publish |
| Input/output unique business keys | Bằng chứng dữ liệu có đủ và không trùng |

Một job có `BatchStatus.COMPLETED` và `readSkipCount=500` **không tự chứng minh** đã xử lý đủ 500 bản ghi lỗi. Cần kiểm toán source key và chính sách chất lượng đã duyệt.

### Quy tắc cảnh báo cho hạ tầng

Không chờ tới khi `skipLimit` cạn mới phát hiện outage. Các alert nên dựa trên:

- Tỉ lệ `DataAccessException`/connection timeout trên **nhiều workers**;
- P95/P99 transaction latency, pool wait, lock wait;
- Tốc độ rollback/retry và số `FAILED`/`STOPPED` partitions;
- Tỉ lệ request lỗi 5xx/429, broker redelivery, DLQ depth;
- Số business operations chưa xác nhận và mismatch sau reconciliation.

Các chỉ số cần phân biệt **số attempts** với **số source/business IDs duy nhất**. Không đưa từng `sourceId` thành label time series vì cardinality lớn; dùng log/audit có kiểm soát để tra cứu.

## 14. Kiểm thử: chứng minh lỗi DB không bị skip

Một cấu hình trông hợp lý vẫn có thể phân loại exception sai do adapter, exception wrapper hoặc một đoạn code đã `catch (Exception)` rồi trả `null`. Cần test cả **hành vi framework** và **dữ liệu đích**.

### 14.1. Unit test phân loại exception

Giả sử ứng dụng tự viết một classifier thuần để giám sát/guardrail, test có thể kiểm tra danh sách lỗi:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.batch.item.file.FlatFileParseException;

public final class FailureClassifier {

    public boolean isDataErrorAllowedToSkip(Throwable error) {
        return error instanceof InvalidOrderRecordException
                || error instanceof FlatFileParseException;
    }

    public boolean isTransientInfrastructure(Throwable error) {
        return error instanceof TransientDataAccessResourceException;
    }
}
~~~

`FailureClassifier` là **mã minh họa** và **không tự thay thế exception classifiers của Spring Batch**. Việc xác định toàn bộ transient infrastructure trong dự án thật phải dựa trên driver, exception translation và API đích. Ở ví dụ, một subclass DB transient được dùng để làm test dễ hiểu:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.dao.TransientDataAccessResourceException;

class FailureClassifierTest {

    private final FailureClassifier classifier =
            new FailureClassifier();

    @Test
    void loiDbKhongDuocCoiLaItemLoiDeSkip() {
        RuntimeException dbOutage =
                new TransientDataAccessResourceException("DB tạm lỗi");

        assertFalse(classifier.isDataErrorAllowedToSkip(dbOutage));
        assertTrue(classifier.isTransientInfrastructure(dbOutage));
    }

    @Test
    void loiValidationCoTheDuocSkip() {
        RuntimeException badRecord =
                new InvalidOrderRecordException("sourceId=ORD-17");

        assertTrue(classifier.isDataErrorAllowedToSkip(badRecord));
        assertFalse(classifier.isTransientInfrastructure(badRecord));
    }
}
~~~

Nếu lỗi DB được bọc trong một exception khác, cả phép `instanceof` ở trên và policy của step cần được kiểm chứng theo **đúng exception thực tế**. Không viết bộ duyệt `getCause()` tự động mở rộng mọi loại lỗi thành skippable; việc unwrap phải bảo tồn nguyên nhân và policy nghiệp vụ.

### 14.2. Integration test: DB outage vượt retry budget

Với `spring-batch-test`, `@SpringBatchTest` và `JobLauncherTestUtils`, một khung test:

~~~java
@SpringBatchTest
@SpringJUnitConfig(classes = InfrastructureFailureJobConfig.class)
class InfrastructureFailureIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void dbOutageKhongDuocSkip() throws Exception {
        // Test config dùng processor/DAO giả lỗi transient có kiểm soát
        // hoặc Testcontainers/proxy mô phỏng outage sau vài item.
        // Reader/writer/transaction manager và JobRepository phải sẵn sàng
        // để chính job có thể ghi nhận trạng thái FAILED.
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", "infra-outage-001")
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, execution.getStatus());

        // Hoàn thiện assertions cho worker step:
        // - failure exception thuộc nhóm hạ tầng đúng mong đợi;
        // - processSkipCount/writeSkipCount không tăng vì DB outage;
        // - output/quarantine không có item được skip giả;
        // - không có business effect ngoài transaction bị nhân đôi.
    }
}
~~~

Đây là **khung integration test**, không phải Java class độc lập: cần imports JUnit 5, Spring Batch Test, bean cấu hình/fixture và một fake fault injector hoặc cơ sở dữ liệu thử nghiệm. Khi test outage ở **database của JobRepository**, framework có thể không lưu được metadata cuối ngay lập tức; cần tách **lỗi business DB** khỏi **lỗi repository DB** và kiểm tra khả năng khôi phục khi repository sẵn sàng trở lại.

### 14.3. Ma trận fault injection

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Một dòng CSV sai định dạng | Được skip có audit nếu whitelist/limit cho phép |
| Bản ghi thiếu mã bắt buộc | `InvalidOrderRecordException` và quarantine đúng source key |
| DB timeout 1–2 attempts rồi phục hồi | Retry thành công; **không tăng skipCount** |
| DB outage kéo dài vượt retry limit | Step `FAILED`; không skip toàn bộ item |
| Sai schema/credentials | Fail fast hoặc thất bại rõ, không retry/skip vô hạn |
| Driver trả exception bị wrapper | Classifier vẫn không bỏ qua lỗi hạ tầng |
| Processor bắt exception rồi trả `null` | Test phát hiện `filterCount` tăng sai và input thiếu |
| Lỗi writer khiến chunk rollback | Các item chưa commit không được xem đã áp dụng |
| DB commit thành công nhưng response mất | Replay có unique operation key; không ghi effect hai lần |
| HTTP timeout sau khi provider xử lý | Giữ same idempotency key, reconcile `UNKNOWN` |
| Một worker fail, các partition khác complete | Metadata và output được đối soát trước restart |
| Nhiều worker cùng DB outage | Retry bounded, không tạo request storm quá quota |
| Remote chunk reply bị mất | Không coi chunk thành “bad data”; xử lý redelivery an toàn |
| Worker cũ chưa dừng, worker mới chạy | Fencing/claim và idempotency tại đích bảo vệ effect |
| Skip limit đúng ngưỡng với lỗi dữ liệu | Các skip được chấp nhận nằm trong giới hạn |
| Một lỗi DB xảy ra khi vẫn còn skip budget | **Vẫn fail sau retry**, không tiêu thụ ngân sách skip |
| Quarantine/audit store không hoạt động | Không âm thầm skip item nếu audit là điều kiện bắt buộc |
| Restart từ checkpoint | Không thiếu/nhân đôi business key, không đổi partition plan |

### 14.4. Không chỉ assert BatchStatus

Một test đáng tin cậy phải kiểm tra thêm:

1. Tập source business keys được cố định bằng snapshot/manifest.
2. Output duy nhất theo business operation key và có giá trị đúng.
3. Item `QUARANTINED` là **lỗi dữ liệu được phép skip**, không phải DB/network outage.
4. Những item chưa commit không bị đánh dấu `APPLIED`.
5. Các `FAILED` partitions còn đường restart, các `COMPLETED` partitions không bị chạy lại vô cớ.
6. Side effects ngoài transaction không bị gửi lặp không kiểm soát.

Nếu chỉ nhìn số `writeCount`, test có thể bỏ sót writer đã thực hiện upsert/no-op hoặc đã gửi HTTP nhiều lần. Đối soát tại **business store/receiver** mới là bằng chứng hiệu ứng thực.

## 15. Runbook vận hành: dừng và khôi phục lỗi hạ tầng

Khi xuất hiện hàng loạt `DataAccessException` hoặc timeout trong batch:

1. **Xác định phạm vi:** Ghi lại `JobInstance`, `JobExecution`, tên step/partition, input snapshot và khoảng thời gian outage.
2. **Phân loại nguyên nhân:** Connection pool, DB restart, lock wait, disk, credentials, schema migration, broker/API hay lỗi mạng? Kiểm tra exception/cause thực tế.
3. **Dừng cấp công việc mới nếu cần:** Hạn chế retry storm; bảo đảm in-flight chunks có đường rollback/commit rõ.
4. **Đọc trạng thái workers:** `FAILED`, `STOPPED`, `COMPLETED`, checkpoint và số chunk đã commit; không giả định mọi worker thất bại đồng thời.
5. **Kiểm tra hệ thống đích:** Có business effects đã commit nhưng Batch chưa ghi nhận? External API có trạng thái `UNKNOWN` cần reconcile?
6. **Không tăng skipLimit như phản xạ đầu tiên:** Lỗi hạ tầng không trở thành lỗi item chỉ vì số lượng item lớn.
7. **Khắc phục dependency:** Phục hồi database/broker/API, chỉnh pool/timeout/rate limit hoặc rollback deploy gây lỗi.
8. **Kiểm thử phục hồi ở tải thấp:** Xác nhận health, transaction, query/SQL và idempotency trước khi mở rộng concurrency trở lại.
9. **Restart đúng cơ chế:** Giữ cùng `JobInstance` và partition key → input range khi cần resume; dùng API vận hành được hỗ trợ thay vì sửa metadata DB.
10. **Đối soát trước publish:** Tập source keys, output, filter hợp lệ, quarantine và các operation chưa xác nhận phải phù hợp hợp đồng dữ liệu.

### Khi nào cần ngừng publish?

Chặn publish nếu:

- Lỗi hạ tầng làm không xác định được item nào đã commit;
- Có output business thiếu/trùng hoặc `APPLIED` mà đích chưa xác nhận;
- Một worker vẫn `FAILED/STOPPED` trong pipeline yêu cầu đầy đủ;
- Có chuyển khoản/thanh toán/email ở trạng thái **chưa biết đã xảy ra hay chưa**;
- Quarantine chứa quá nhiều item hoặc nguyên nhân lỗi không thuộc whitelist;
- Partition plan/snapshot có thể đã thay đổi khiến checkpoint không còn hợp lệ.

Nếu pipeline đã phát ngay kết quả cho downstream, publish gate cuối job **không thể tự thu hồi side effects**; vì vậy cần staging, outbox hoặc cơ chế compensation/reconciliation từ đầu.

## 16. Checklist thiết kế trước production

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| Exception whitelist | Chỉ lỗi dữ liệu được duyệt mới skippable |
| No broad skip | Không `skip(Exception.class)`/`skip(DataAccessException.class)` bừa bãi |
| Retry classifier | Có danh sách lỗi transient thực tế và điều kiện an toàn để retry |
| Retry budget | Có limit, timeout, backoff và không nhân bội tầng retry vô tình |
| Transaction | Biết rõ business DB, JobRepository và broker/API tham gia transaction nào |
| Checkpoint | Reader `ItemStream`, input snapshot, sort key/partition plan ổn định |
| Idempotency | Business operation key ổn định xuyên retry/restart/redelivery |
| Audit | `SkipListener` lưu source key/lý do của item thật sự skip, không gán lỗi hệ thống vào bad records |
| Partitioning | Mỗi worker độc lập state; lỗi chung được phát hiện ở cấp toàn job/cụm |
| Remote delivery | Reply/ACK loss không khiến chunk bị skip hay effect bị nhân đôi |
| Observability | Có rollback/retry/infrastructure error metrics và quality reconciliation |
| Recovery | Có runbook fail/restart/reconcile; không sửa metadata thủ công |
| Validation | Fault injection bao phủ DB outage, timeout sau commit và worker concurrency |

## 17. Bài tập tình huống

Một batch nhập **4 triệu bản ghi** từ 16 file CSV, chia 8 partitions. Worker step cấu hình:

~~~java
.faultTolerant()
.skip(Exception.class)
.skipLimit(5_000)
.retry(TransientDataAccessException.class)
.retryLimit(3)
~~~

Sau 10 phút, database đích mất kết nối. Các worker tiếp tục thử ghi, rollback, rồi skip nhiều item. Dashboard vẫn hiển thị một số partition `COMPLETED`, còn `writeCount`/`skipCount` tăng bất thường. Nhóm vận hành đề xuất **tăng `skipLimit` lên 50.000** để job hoàn tất trước giờ mở cửa.

**Câu hỏi:**

1. Vì sao `skip(Exception.class)` nguy hiểm hơn một whitelist validation cụ thể?
2. Sau ba attempts lỗi DB, điều đúng đắn nên xảy ra với worker là gì?
3. Những item bị skip do lỗi DB có thể được xem là “data quality errors” không?
4. Nếu DB đã commit một chunk nhưng worker mất reply, retry có thể gây gì?
5. Khi 8 worker cùng retry DB, những tài nguyên nào có thể trở thành bottleneck?
6. Nên thay cấu hình và quy trình vận hành thế nào để không mất hoặc nhân đôi dữ liệu?
7. Cần đối soát những gì trước khi cho phép publish?

**Định hướng trả lời:** Lỗi DB có thể ảnh hưởng item hoàn toàn hợp lệ, vì vậy broad skip chuyển lỗi hạ tầng thành mất dữ liệu. Hãy whitelist `InvalidOrderRecordException`/`FlatFileParseException` cho skip, dùng retry có giới hạn cho exception DB transient, fail step nếu dependency chưa phục hồi, điều tra `JobRepository` và commit. Business writer cần idempotency để chịu replay, đặc biệt khi DB/outbox/HTTP khác transaction. Giới hạn concurrency và backoff ngăn retry storm. Sau khắc phục, restart đúng `JobInstance`, giữ partition plan/snapshot và đối soát tập source business keys với output, filter, quarantine và các kết quả chưa xác nhận.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): exception classification, `skipLimit` và ví dụ.
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry fault-tolerant chunk step.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, `ItemStream` và restart.
- [Spring Batch Reference — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): read/process/write/transaction.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listener và quan sát vòng đời.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote chunking/partitioning qua middleware.
- [Spring Framework Reference — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html): phân loại `DataAccessException` và nhóm transient.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary và rollback.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): status/counters trong `BATCH_STEP_EXECUTION`.

> **Ghi nhớ:** **Lỗi hạ tầng không phải lỗi của item.** Với Spring Batch, hãy **skip có chọn lọc** những record sai dữ liệu được phép cách ly; **retry có giới hạn** cho lỗi transient mà thao tác thử lại an toàn; **fail và restart có kiểm soát** khi hạ tầng không phục hồi. Khi có API/broker/database ngoài transaction, phải bổ sung **idempotency, trạng thái UNKNOWN và đối soát**, nhất là khi job chạy song song hoặc phân tán. Không tăng `skipLimit` để che mất kết nối, timeout hoặc lỗi hệ thống.
