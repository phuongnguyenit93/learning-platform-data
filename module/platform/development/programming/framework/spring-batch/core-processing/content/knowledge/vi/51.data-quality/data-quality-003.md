# Skip và báo cáo rejected item trong Spring Batch

Một Spring Batch Job thường đọc hàng nghìn đến hàng triệu bản ghi từ CSV, database hoặc message source. Trong tập dữ liệu lớn, có thể có một số bản ghi sai định dạng, thiếu trường bắt buộc, vi phạm quy tắc nghiệp vụ hoặc không thể ghi vào hệ thống đích. Nếu mọi lỗi đều làm cả Job dừng lại, những bản ghi hợp lệ có thể bị chậm xử lý. Ngược lại, nếu bỏ qua lỗi mà không ghi nhận, dữ liệu sẽ bị mất âm thầm và khó đối soát.

Trong nhóm **Data quality** của **Spring Batch Core Processing**, **skip và báo cáo rejected item** là cách cho phép Job tiếp tục xử lý những bản ghi được chấp nhận, đồng thời tạo dấu vết đủ rõ về các bản ghi bị loại. Giải pháp cần thiết kế cả **quy tắc chấp nhận lỗi**, **giới hạn số lỗi**, **nơi lưu kết quả bị loại** và **cơ chế xác minh**.

Bài này giải thích cơ chế fault-tolerant chunk processing, `SkipListener`, cấu trúc báo cáo rejected item, ví dụ Java Spring Batch 5.x, cách kiểm thử và các nguyên tắc vận hành. Với Spring Batch 6.x, một số package và API builder đã được tổ chức lại; khi triển khai, cần dùng đúng API theo dependency của dự án.

## 1. Phân biệt skip, filter, retry và Job thất bại

Trước khi viết code, phải xác định từng loại kết quả xử lý.

| Khái niệm | Điều xảy ra | Có được tính vào rejected item không? |
| --- | --- | --- |
| **Filter** | `ItemProcessor` trả về `null`, bản ghi được bỏ khỏi đầu ra theo quy tắc bình thường. | Không mặc định. Đây là quyết định xử lý hợp lệ, được tính vào `filterCount`. |
| **Skip** | Reader/processor/writer phát sinh exception đã được cấu hình là có thể bỏ qua, trong giới hạn cho phép. | Có. Đây là bản ghi lỗi cần phân loại và báo cáo theo hợp đồng dữ liệu. |
| **Retry** | Spring Batch thử lại thao tác gặp lỗi tạm thời. | Chưa chắc. Nếu retry thành công thì không có rejected item; nếu lỗi tiếp diễn có thể skip hoặc fail tùy policy. |
| **Fail** | Exception không được skip, hoặc tổng skip vượt ngưỡng, làm Step/Job thất bại theo flow. | Có thể có rejected item trước đó, nhưng kết quả Job là `FAILED`. |
| **Stop** | Job dừng có kiểm soát, ví dụ thao tác vận hành. | Không đồng nghĩa với dữ liệu bị reject. |

Ví dụ một Job đọc 10 dòng dữ liệu (không tính header):

```text
10 dòng nguồn
  |
  +-- 1 dòng lỗi định dạng số tiền ----------> READ SKIP
  |
  +-- 9 bản ghi đọc thành công
        |
        +-- 2 bản ghi không hợp lệ nghiệp vụ -> PROCESS SKIP
        |
        +-- 7 bản ghi hợp lệ -----------------> WRITE SUCCESS
```

Với một Step được cấu hình để skip ba lỗi trên, kết quả minh họa có thể là:

```text
BatchStatus         = COMPLETED
readCount           = 9
readSkipCount       = 1
processSkipCount    = 2
writeSkipCount      = 0
skipCount           = 3
writeCount          = 7
```

Số lượng trên phụ thuộc fixture và cơ chế reader/processor/writer được sử dụng. **`COMPLETED` không có nghĩa mọi dòng input đều được chấp nhận**; nó có thể có nghĩa Job đã hoàn thành theo chính sách cho phép bỏ qua một số lỗi.

## 2. Rejected item là gì?

**Rejected item** là một đơn vị đầu vào không được chấp nhận ở một giai đoạn xử lý, kèm lý do đủ rõ để phân tích, sửa dữ liệu hoặc tái xử lý.

Một bản ghi báo cáo rejection thường cần trả lời:

- Bản ghi xuất phát từ **nguồn dữ liệu nào**, ở vị trí hoặc khóa nào?
- Nó bị từ chối trong giai đoạn **READ**, **PROCESS** hay **WRITE**?
- Lỗi thuộc **nhóm lỗi nghiệp vụ hay lỗi kỹ thuật** nào?
- JobInstance, JobExecution và StepExecution nào đã xử lý nó?
- Bản ghi có thể được sửa và nạp lại hay cần xử lý thủ công?
- Có thể nhận diện cùng một bản ghi khi chạy lại mà không tạo báo cáo trùng một cách sai lệch không?

Ví dụ một dòng trong báo cáo:

```json
{
  "jobName": "importPaymentsJob",
  "jobInstanceId": 42,
  "jobExecutionId": 811,
  "stepExecutionId": 1311,
  "source": "payments-2026-11-16.csv",
  "sourceKey": "line:5",
  "phase": "READ",
  "errorCode": "INVALID_AMOUNT_FORMAT",
  "exceptionType": "FlatFileParseException",
  "reportedAt": "2026-11-16T02:30:00Z",
  "resolutionStatus": "NEW"
}
```

Đây là **mẫu nghiệp vụ**, không phải cấu trúc tự sinh sẵn của Spring Batch. Dự án cần tự thiết kế cách lưu, bảo mật, truy vấn và xử lý rejected item.

**Không mặc định rejected item đồng nghĩa với exception message.** Thông báo exception có thể chứa dữ liệu nhạy cảm, không ổn định giữa các phiên bản hoặc không dễ dùng cho người vận hành. Nên có `errorCode` chuẩn hóa và nội dung mô tả đã được kiểm soát.

## 3. Cơ chế fault-tolerant chunk processing

Một Step chunk-oriented thường chạy theo mô hình:

```text
ItemReader
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Commit transaction

Nếu phát sinh lỗi:
    |
    +-- Retry? ---> thử lại theo chính sách
    |
    +-- Skippable + chưa vượt skipLimit?
    |      |
    |      +-- Có ---> bỏ item lỗi, ghi nhận skip, tiếp tục
    |      |
    |      +-- Không -> Step thất bại
    |
    +-- Lỗi không skippable -> Step thất bại
```

Trong Spring Batch 5.x, `faultTolerant()` cho phép cấu hình chính sách skip và retry ở `StepBuilder`. Ví dụ:

```java
@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> paymentReader,
        ItemProcessor<Payment, Payment> paymentProcessor,
        ItemWriter<Payment> paymentWriter) {

    return new StepBuilder("importPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .processor(paymentProcessor)
            .writer(paymentWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidPaymentException.class)
            .skipLimit(100)
            .build();
}
```

Ở đây:

1. `chunk(100, transactionManager)` định nghĩa đơn vị đọc/xử lý/ghi theo chunk với transaction manager đã cấu hình.
2. `faultTolerant()` bật các khả năng xử lý lỗi cho Step.
3. `skip(FlatFileParseException.class)` cho phép bỏ qua lỗi phân tích dòng của `FlatFileItemReader`.
4. `skip(InvalidPaymentException.class)` cho phép bỏ qua lỗi do logic kiểm tra nghiệp vụ tạo ra.
5. `skipLimit(100)` cho phép tối đa **100 lần skip** trong Step; khi cần skip thứ **101**, Step sẽ thất bại thay vì tiếp tục bỏ qua vô hạn.

**Giới hạn skip tính trên tổng read skip, process skip và write skip của Step**, không phải 100 cho mỗi giai đoạn. Chính sách giới hạn có thể thay đổi nếu dự án dùng một `SkipPolicy` tùy biến.

### Khi nào nên dùng skip?

Nên skip lỗi thuộc nhóm **dữ liệu riêng lẻ không hợp lệ nhưng không làm mất khả năng xử lý những item còn lại**, ví dụ:

- Một dòng CSV có số tiền sai định dạng.
- Một đơn hàng thiếu mã sản phẩm bắt buộc.
- Một sự kiện có ngày nghiệp vụ nằm ngoài miền cho phép.
- Một giao dịch vi phạm quy tắc nghiệp vụ đã được định nghĩa là reject được.

Không nên cấu hình bỏ qua một cách rộng rãi cho các lỗi như:

- Không kết nối được database hoặc hệ thống lưu trữ.
- Driver, transaction manager hoặc schema không hoạt động.
- Timeout kéo dài trên toàn hệ thống.
- Lỗi lập trình như `NullPointerException` không được dự kiến.
- Lỗi ràng buộc dữ liệu có thể chỉ ra bug của writer, mapping hoặc transaction.

**Tránh `skip(Exception.class)` hoặc `skip(Throwable.class)` làm cấu hình mặc định.** Cách này có thể biến lỗi hạ tầng nghiêm trọng thành số lượng skip và khiến Job báo hoàn thành dù hệ thống thực tế không vận hành đúng.

## 4. Phân loại lỗi READ, PROCESS và WRITE

### 4.1. READ skip

Lỗi xảy ra trong quá trình gọi `ItemReader.read()`. Với `FlatFileItemReader`, một dòng chứa số không thể parse có thể gây `FlatFileParseException`.

Ví dụ:

```csv
source_key,payment_id,amount
r01,p01,100.00
r02,p02,not-a-number
r03,p03,25.00
```

Ở dòng `r02`, reader chưa tạo được đối tượng `Payment` hợp lệ. Vì vậy callback:

```java
void onSkipInRead(Throwable error)
```

chỉ nhận **exception**, không nhận item đã map thành công. Nếu exception là `FlatFileParseException`, có thể lấy `getLineNumber()` và `getInput()` để nhận diện dòng nguồn. Tuy nhiên `getInput()` là nội dung gốc và có thể chứa thông tin nhạy cảm; không nên đưa trực tiếp vào log chung.

Đối với lỗi I/O không thể tiếp tục đọc nguồn, việc skip không nhất thiết có ý nghĩa; cần phân loại là lỗi hạ tầng và có chính sách fail/retry tương ứng.

### 4.2. PROCESS skip

Reader tạo được item, nhưng `ItemProcessor` phát hiện quy tắc nghiệp vụ không hợp lệ:

```java
public final class PaymentValidationProcessor
        implements ItemProcessor<Payment, Payment> {

    @Override
    public Payment process(Payment payment) {
        if (payment.amount().signum() <= 0) {
            throw new InvalidPaymentException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }
        return payment;
    }
}
```

Nếu `InvalidPaymentException` được cấu hình skippable, item đó bị loại và được ghi vào `processSkipCount`. Callback:

```java
void onSkipInProcess(Payment item, Throwable error)
```

nhận cả item đã đọc được và exception. Đây là cơ hội thuận tiện để ghi `sourceKey`, mã lỗi và dữ liệu đã làm sạch phục vụ báo cáo.

Phân biệt với:

```java
return null;
```

Trả về `null` từ processor là **filter**, không tự kích hoạt `onSkipInProcess`. Nếu một điều kiện nghiệp vụ cần được thống kê trong báo cáo rejected item, hãy thiết kế chính sách rõ ràng: nó là filtered item hợp lệ hay rejected item do vi phạm quy tắc?

### 4.3. WRITE skip

Lỗi xảy ra khi `ItemWriter` ghi một hoặc nhiều item. Ví dụ một item vi phạm unique constraint trong database.

Nếu lỗi được cấu hình là có thể skip và framework cô lập được item gây lỗi, callback:

```java
void onSkipInWrite(Payment item, Throwable error)
```

sẽ thông báo về item bị loại. Tuy nhiên write skip phức tạp hơn read/process skip: writer thường nhận cả **chunk**, lỗi có thể làm transaction rollback và Spring Batch phải thực hiện logic phục hồi để xác định item lỗi.

Những điểm cần thận trọng:

- Một lời gọi writer có thể chứa nhiều item; exception ban đầu không luôn cho biết item nào sai.
- Writer có thể được gọi lại trong quá trình xác định lỗi; **không dùng số lần writer ném exception làm số rejected item**.
- Side effect ngoài transaction (gửi email, gọi API, publish message) có thể đã xảy ra trước rollback; cần idempotency và cơ chế tích hợp tin cậy.
- Chỉ cho phép skip loại lỗi write mà nghiệp vụ xác định rõ có thể bỏ qua. Một unique violation do dữ liệu trùng có chủ đích khác với unique violation do bug writer.

Khi tạo báo cáo rejected item, phải ghi rõ **giai đoạn lỗi** vì ý nghĩa và cách khắc phục rất khác nhau.

## 5. Thiết kế bảng rejected item

Một cách triển khai phổ biến là lưu rejection vào bảng riêng, ví dụ PostgreSQL:

```sql
CREATE TABLE batch_rejected_item (
    rejection_id       BIGSERIAL PRIMARY KEY,
    job_execution_id   BIGINT NOT NULL,
    step_execution_id  BIGINT NOT NULL,
    phase              VARCHAR(16) NOT NULL,
    source_key         VARCHAR(255) NOT NULL,
    error_code         VARCHAR(100) NOT NULL,
    exception_type     VARCHAR(255) NOT NULL,
    reported_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolution_status  VARCHAR(32) NOT NULL DEFAULT 'NEW',
    CONSTRAINT uq_batch_rejected_attempt
        UNIQUE (
            job_execution_id,
            step_execution_id,
            phase,
            source_key
        )
);
```

Đây là **schema minh họa**; điều chỉnh kiểu cột và tên bảng theo database. Bảng này là **dữ liệu báo cáo của ứng dụng**, không phải một bảng mặc định trong schema metadata của Spring Batch.

Ý nghĩa các trường:

| Trường | Vai trò |
| --- | --- |
| `rejection_id` | Khóa nội bộ cho từng bản ghi báo cáo. |
| `job_execution_id` | Nối với một lần chạy Job cụ thể. |
| `step_execution_id` | Nối với StepExecution đã reject item. |
| `phase` | `READ`, `PROCESS` hoặc `WRITE`. |
| `source_key` | Khóa đầu vào ổn định, ví dụ ID dòng nguồn hoặc số dòng file. |
| `error_code` | Mã lỗi do nghiệp vụ quy định, có thể phân tích và tổng hợp. |
| `exception_type` | Loại exception phục vụ chẩn đoán kỹ thuật. |
| `reported_at` | Thời điểm báo cáo được lưu. |
| `resolution_status` | Trạng thái xử lý sau đó, ví dụ `NEW`, `REVIEWED`, `CORRECTED`. |

### Chọn `source_key` đúng cách

Đối với input CSV, có thể dùng tên file + số dòng. Đối với database reader, dùng primary key nguồn; đối với message queue, dùng message ID hoặc partition + offset.

**Không dùng mỗi business key nếu nguồn cho phép nhiều dòng có cùng business key.** Hai dòng có cùng `payment_id` nhưng xuất hiện ở hai vị trí khác nhau là hai lần xuất hiện cần phân biệt; một unique constraint quá rộng có thể che mất một rejected item thật.

Để dedup trong phạm vi một lần thực thi, khóa có thể gồm:

```text
jobExecutionId + stepExecutionId + phase + sourceKey
```

Nếu muốn nhóm những lần reject **của cùng bản ghi nghiệp vụ qua nhiều lần restart**, cần thêm khóa khác ở phạm vi `JobInstance` hoặc dataset + source key. Không gộp hai mục đích này vào một unique constraint mà không định nghĩa rõ hành vi mong muốn.

### Lưu dữ liệu gốc ở đâu?

Có ba lựa chọn chính:

1. **Chỉ lưu khóa và mã lỗi**: an toàn và gọn, nếu có thể truy cập lại nguồn.
2. **Lưu snapshot đã làm sạch**: hữu ích khi nguồn thay đổi, nhưng phải giới hạn các trường được phép lưu.
3. **Lưu payload gốc trong kho cách ly**: dành cho quy trình xử lý dữ liệu cần đủ bằng chứng, có mã hóa, phân quyền, retention và audit riêng.

Không nên mặc định ghi cả dòng CSV chứa thông tin khách hàng vào exception message, application log hoặc bảng rejected item không được bảo vệ.

## 6. Cài đặt `SkipListener` để báo cáo rejected item

`SkipListener<I, O>` cung cấp ba callback tương ứng với ba pha:

```java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
```

Ví dụ dưới đây dùng Spring Batch 5.x. Giả sử có model đầu vào:

```java
import java.math.BigDecimal;

public record Payment(
        String sourceKey,
        String paymentId,
        BigDecimal amount) {
}
```

Một exception nghiệp vụ riêng:

```java
public final class InvalidPaymentException
        extends RuntimeException {

    public InvalidPaymentException(String errorCode) {
        super(errorCode);
    }
}
```

Cấu trúc dữ liệu để lưu rejection:

```java
public record Rejection(
        Long jobExecutionId,
        Long stepExecutionId,
        String phase,
        String sourceKey,
        String errorCode,
        String exceptionType) {
}
```

Giao diện đích báo cáo:

```java
public interface RejectionSink {
    void save(Rejection rejection);
}
```

Listener minh họa:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.listener.SkipListenerSupport;
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;
import org.springframework.batch.item.file.FlatFileParseException;

public final class PaymentSkipListener
        extends SkipListenerSupport<Payment, Payment> {

    private final RejectionSink sink;

    public PaymentSkipListener(RejectionSink sink) {
        this.sink = sink;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        String sourceKey;

        if (error instanceof FlatFileParseException parse) {
            sourceKey = "line:" + parse.getLineNumber();
        } else {
            // Các lỗi read khác cần được phân loại riêng.
            sourceKey = "unknown-read-position";
        }

        save("READ", sourceKey,
                "INVALID_INPUT_FORMAT", error);
    }

    @Override
    public void onSkipInProcess(
            Payment payment, Throwable error) {

        save("PROCESS", payment.sourceKey(),
                "INVALID_PAYMENT", error);
    }

    @Override
    public void onSkipInWrite(
            Payment payment, Throwable error) {

        save("WRITE", payment.sourceKey(),
                "PAYMENT_WRITE_REJECTED", error);
    }

    private void save(
            String phase,
            String sourceKey,
            String errorCode,
            Throwable error) {

        StepContext context = StepSynchronizationManager.getContext();
        if (context == null) {
            throw new IllegalStateException(
                    "Skip callback outside a Step context");
        }

        StepExecution step = context.getStepExecution();

        sink.save(new Rejection(
                step.getJobExecutionId(),
                step.getId(),
                phase,
                sourceKey,
                errorCode,
                error.getClass().getSimpleName()
        ));
    }
}
```

Điểm cần chú ý:

- Trong `onSkipInRead`, item đã parse **không có sẵn**; muốn xác định dòng nên dựa vào loại exception, reader hoặc dữ liệu nguồn phù hợp.
- Trong `onSkipInProcess` và `onSkipInWrite`, có item để lấy khóa nguồn.
- `StepSynchronizationManager` dùng context Step hiện hành để lấy các Batch ID. Cách này giả định listener được gọi trong ngữ cảnh Step do Spring Batch quản lý.
- `errorCode` phải có ý nghĩa ổn định. Ví dụ trên dùng mã cố định cho từng pha; trong dự án thật nên phân loại chính xác từng lỗi validation, lỗi ghi hoặc lỗi định dạng.
- Không đưa `error.getMessage()` hoặc raw input vào báo cáo mà không làm sạch; chúng có thể chứa dữ liệu nhạy cảm.
- Nếu nhiều dòng READ skip không xác định được vị trí, `unknown-read-position` không phải khóa duy nhất tốt. Cần bổ sung thông tin vị trí nguồn hoặc chuyển lỗi đó sang nhánh fail thay vì silently dedup.

`SkipListenerSupport` được dùng để dễ minh họa trong Spring Batch 5.x. Nếu phiên bản đang dùng hỗ trợ method mặc định của `SkipListener`, có thể implements interface trực tiếp. Tránh trộn package của Spring Batch 5 và 6 khi sao chép ví dụ.

## 7. Lưu rejection vào database bằng JDBC

Một implementation đơn giản của `RejectionSink` có thể dùng `JdbcTemplate`:

```java
import org.springframework.jdbc.core.JdbcTemplate;

public final class JdbcRejectionSink implements RejectionSink {

    private final JdbcTemplate jdbc;

    public JdbcRejectionSink(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void save(Rejection r) {
        jdbc.update(
            """
            INSERT INTO batch_rejected_item (
                job_execution_id,
                step_execution_id,
                phase,
                source_key,
                error_code,
                exception_type
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            r.jobExecutionId(),
            r.stepExecutionId(),
            r.phase(),
            r.sourceKey(),
            r.errorCode(),
            r.exceptionType()
        );
    }
}
```

Trong cấu hình Spring Batch sử dụng cùng `DataSource` và `PlatformTransactionManager` phù hợp, lời gọi `JdbcTemplate` từ callback có thể tham gia vào transaction của chunk đang chạy. **Tính nhất quán giao dịch cần được xác định theo cấu hình thực tế**, đặc biệt khi bảng reject nằm ở datasource khác hoặc Job dùng transaction manager khác.

Theo hợp đồng của Spring Batch, `SkipListener` được gọi ở điểm phù hợp để ghi nhận item đã skip và trước lúc transaction commit. Dù vậy, vẫn cần xử lý các trường hợp ứng dụng chết, transaction rollback, listener bị gọi lại hoặc lưu báo cáo thất bại.

### Nếu bảng reject ở database khác

Khi rejection sink dùng một datasource hoặc dịch vụ khác, transaction xử lý chunk không tự động bao phủ lời gọi đó. Có thể xảy ra:

```text
Chunk transaction              Rejection service
-----------------              -----------------
skip item A
send rejection A ------------> persisted
commit chunk -> FAILED

=> Report đã lưu, nhưng chunk chưa commit.
```

Nếu báo cáo cần nhất quán mạnh với kết quả xử lý, ưu tiên lưu vào cùng database/transaction hoặc dùng **transactional outbox** và một worker riêng để xuất báo cáo sau commit. Khi dùng outbox/message broker, xử lý idempotent để không đếm một event trùng nhiều lần.

Một callback `SkipListener` cũng không nên gửi email hoặc gọi HTTP trực tiếp cho từng bản ghi lỗi: điều này làm chậm Job, dễ tạo side effect lặp và khiến một hệ thống báo cáo tạm thời bị lỗi làm ảnh hưởng tới xử lý dữ liệu chính.

## 8. Ghép listener vào Step

Ví dụ Step hoàn chỉnh về cấu hình fault tolerance, dùng các bean đã được cung cấp từ ứng dụng:

```java
@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> paymentReader,
        ItemProcessor<Payment, Payment> paymentProcessor,
        ItemWriter<Payment> paymentWriter,
        PaymentSkipListener paymentSkipListener) {

    return new StepBuilder("importPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .processor(paymentProcessor)
            .writer(paymentWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidPaymentException.class)
            .skipLimit(100)
            .listener(paymentSkipListener)
            .build();
}
```

Đăng ký các bean liên quan:

```java
@Bean
PaymentSkipListener paymentSkipListener(RejectionSink sink) {
    return new PaymentSkipListener(sink);
}

@Bean
RejectionSink rejectionSink(JdbcTemplate jdbcTemplate) {
    return new JdbcRejectionSink(jdbcTemplate);
}
```

Nếu lớp được quản lý dưới dạng Spring bean qua `@Component`, không tạo thêm cùng bean bằng `@Bean` trừ khi chủ động dùng cấu hình tên/qualifier khác. Quan trọng nhất là listener phải được **gắn vào Step** để callback được gọi.

### Phân biệt listener được đăng ký và listener được thực thi

Chỉ khai báo class `PaymentSkipListener` trong source code không làm Spring Batch tự gọi nó. Một listener có thể có bean nhưng không được gắn vào Step; hoặc Step không được chạy trong flow của Job; hoặc không phát sinh item nào đủ điều kiện skip.

Trong các trường hợp đó, báo cáo có thể rỗng hoàn toàn mà không phải lỗi JDBC. Khi test cần kiểm tra chính xác số rejection, phải tạo fixture với lỗi có thể tái hiện được và xác nhận callback được gọi trong đường chạy thật.

## 9. Reader và processor minh họa

File CSV fixture:

```csv
source_key,payment_id,amount
r01,p01,100.00
r02,p02,0
r03,p03,50.00
r04,p04,not-a-number
r05,p05,12.00
r06,p06,-2
r07,p07,20.00
r08,p08,30.00
r09,p09,40.00
r10,p10,15.00
```

Giả sử file được lưu ở `src/test/resources/payments-fixture.csv` hoặc tài nguyên tương đương được truyền vào Job.

Reader Spring Batch 5.x:

```java
@Bean
@StepScope
FlatFileItemReader<Payment> paymentReader() {
    return new FlatFileItemReaderBuilder<Payment>()
            .name("paymentReader")
            .resource(new ClassPathResource("payments-fixture.csv"))
            .linesToSkip(1)
            .delimited()
            .names("source_key", "payment_id", "amount")
            .fieldSetMapper(fields ->
                    new Payment(
                            fields.readString("source_key"),
                            fields.readString("payment_id"),
                            fields.readBigDecimal("amount")
                    ))
            .build();
}
```

Các import chính:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.ClassPathResource;
```

Khi reader gặp `not-a-number`, bước map `readBigDecimal` thất bại và lỗi parse của reader có thể được bọc dưới dạng `FlatFileParseException`. Với Step cấu hình `skip(FlatFileParseException.class)`, dòng này được skip nếu chưa vượt giới hạn.

Processor:

```java
@Bean
ItemProcessor<Payment, Payment> paymentProcessor() {
    return payment -> {
        if (payment.amount().signum() <= 0) {
            throw new InvalidPaymentException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }
        return payment;
    };
}
```

Vì `r02` và `r06` có số tiền không dương, chúng bị process skip. Những bản ghi còn lại có số tiền dương được đưa sang writer.

Writer minh họa dùng `JdbcBatchItemWriter`:

```java
@Bean
JdbcBatchItemWriter<Payment> paymentWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Payment>()
            .dataSource(dataSource)
            .sql(
                """
                INSERT INTO accepted_payment (payment_id, amount)
                VALUES (:paymentId, :amount)
                """
            )
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("paymentId", item.paymentId())
                            .addValue("amount", item.amount()))
            .build();
}
```

Đây là ví dụ nạp dữ liệu; ứng dụng cần tạo bảng `accepted_payment` với kiểu phù hợp và xử lý dữ liệu cũ trước mỗi lần test. Các import chính gồm `javax.sql.DataSource`, `JdbcBatchItemWriter`, `JdbcBatchItemWriterBuilder` và `MapSqlParameterSource`.

Tổng kết của fixture 10 dòng:

| Giai đoạn | Dòng | Kết quả |
| --- | --- | --- |
| READ | `r04` | Reject vì `amount=not-a-number` |
| PROCESS | `r02` | Reject vì `amount=0` |
| PROCESS | `r06` | Reject vì `amount=-2` |
| WRITE | 7 dòng còn lại | Chấp nhận và ghi vào bảng đích |

Với dữ liệu và cấu hình ở trên, nếu không có lỗi hạ tầng và Job được cấu hình đúng, `skipCount` dự kiến là 3, `writeCount` là 7, Job có thể kết thúc `COMPLETED`.

## 10. Dùng `SkipPolicy` khi cần quy tắc phức tạp

`skipLimit(...)` và `skip(...)` thường đủ cho các bài toán phổ biến. Nếu dự án cần quy tắc kết hợp nhiều loại lỗi, có thể tạo `SkipPolicy`.

Ví dụ một chính sách có giới hạn tuyệt đối và danh sách exception:

```java
import org.springframework.batch.core.step.skip.SkipLimitExceededException;
import org.springframework.batch.core.step.skip.SkipPolicy;
import org.springframework.batch.item.file.FlatFileParseException;

public final class PaymentSkipPolicy implements SkipPolicy {

    private static final long MAX_SKIPS = 100;

    @Override
    public boolean shouldSkip(
            Throwable error, long skipCount)
            throws SkipLimitExceededException {

        boolean eligible =
                error instanceof FlatFileParseException
                || error instanceof InvalidPaymentException;

        if (!eligible) {
            return false;
        }

        if (skipCount >= MAX_SKIPS) {
            throw new SkipLimitExceededException(
                    MAX_SKIPS, error);
        }

        return true;
    }
}
```

Đăng ký:

```java
.faultTolerant()
.skipPolicy(new PaymentSkipPolicy())
```

`SkipPolicy.shouldSkip(...)` quyết định liệu một exception ở thời điểm đó có thể được skip hay không. Cần đặc biệt thận trọng với **ngữ nghĩa `skipCount`** trong API và các trường hợp framework kiểm tra policy trước khi tăng bộ đếm. Không tự chế một policy phức tạp nếu `skipLimit` cộng whitelist exception đã mô tả chính xác nghiệp vụ.

Nếu muốn áp dụng tỷ lệ reject tối đa (ví dụ số skip không vượt 1% tổng đầu vào), không chỉ nhìn `skipCount`. Cần thiết kế cách biết mẫu số chính xác, chọn thời điểm đánh giá và quyết định khi vượt ngưỡng:

- Nếu chỉ biết tổng dòng sau khi đọc hết, có thể có một Step kiểm tra chất lượng ở cuối và **fail Job** khi tỷ lệ vượt ngưỡng.
- Nếu biết trước số dòng đầu vào từ manifest, có thể xây dựng policy dựa trên thông tin đó và ngưỡng tuyệt đối suy ra.
- Nếu cần dừng ngay trong quá trình xử lý, phải tính toán đúng số item đã đọc/chấp nhận trong môi trường rollback/retry/concurrency.

Tránh giới hạn theo tỷ lệ “ngẫu nhiên” từ một bộ đếm tạm thời chưa phản ánh đầy đủ tình trạng dữ liệu.

## 11. Kết hợp retry và skip theo đúng loại lỗi

Một Job có thể gặp cả lỗi dữ liệu vĩnh viễn và lỗi kỹ thuật tạm thời. Ví dụ:

- `InvalidPaymentException`: dữ liệu đầu vào thiếu điều kiện hợp lệ → skip.
- `FlatFileParseException`: dòng không chuyển đổi được → skip.
- `DeadlockLoserDataAccessException` hoặc timeout transient có thể phục hồi → cân nhắc retry theo policy.
- Database không khả dụng kéo dài → fail và alert.

Ví dụ cấu hình minh họa:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidPaymentException.class)
.skipLimit(100)
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

Đây là ví dụ về cách **tách loại lỗi**; việc retry database phải xét tính idempotent của writer, transaction boundary và khả năng lỗi được phục hồi. Trong trường hợp writer gọi một hệ thống ngoài, retry có thể tạo side effect trùng nếu hệ thống đích không hỗ trợ idempotency key.

### Lúc nào một item được xem là rejected?

Một item **đã retry thành công** không phải rejected item. Một item chỉ được coi là skipped khi framework xác định bỏ qua nó theo skip policy và callback tương ứng được gọi.

Vì vậy, không nên phát báo cáo reject ngay mỗi khi bắt được exception trong processor hoặc writer. Nếu exception còn có thể được retry thành công, báo cáo sẽ chứa “lỗi giả” và dễ đếm trùng. Hãy đặt phần báo cáo rejected item ở `SkipListener` hoặc ở một cơ chế được gọi sau khi quyết định skip đã được xác nhận.

## 12. Transaction, callback và tính nhất quán của báo cáo

Cần phân biệt ba khái niệm:

1. **Item bị skip** theo policy Spring Batch.
2. **Bản ghi rejected item được lưu**.
3. **Chunk transaction commit thành công**.

Chúng có liên quan nhưng không luôn xảy ra như một thao tác nguyên tử nếu báo cáo lưu ở hệ thống ngoài.

### 12.1. Lưu báo cáo cùng transaction của Step

Nếu rejected item được ghi bằng JDBC vào cùng datasource và transaction manager với Step, có thể đạt được tính nhất quán tốt: metadata xử lý, writer và báo cáo rejection cùng tham gia một transaction khi callback diễn ra.

Nhưng vẫn cần xác nhận:

- `RejectionSink` không dùng transaction `REQUIRES_NEW` ngoài ý muốn.
- Dao/repository của báo cáo dùng đúng datasource.
- Lỗi ghi báo cáo có được phép làm Step fail hay không.
- Nếu transaction rollback sau callback, báo cáo không bị ghi vĩnh viễn mà không có xử lý đi kèm.

### 12.2. Ghi file rejected CSV

Một số dự án muốn xuất:

```csv
source_key,phase,error_code
line:5,READ,INVALID_AMOUNT_FORMAT
r02,PROCESS,AMOUNT_MUST_BE_POSITIVE
r06,PROCESS,AMOUNT_MUST_BE_POSITIVE
```

File report thuận tiện để người vận hành xem, nhưng ghi file không mặc nhiên rollback cùng database. Nếu listener trực tiếp append vào file, một chunk rollback rồi chạy lại có thể tạo dòng trùng.

Thiết kế an toàn hơn cho Job cần restart là **lưu rejection vào bảng/outbox có khóa dedup**, sau khi Job hoàn tất thì xuất file tổng hợp từ dữ liệu đã commit. File export có thể được tạo bằng tên tạm rồi rename khi hoàn tất, với cách xử lý retry/cập nhật phù hợp filesystem.

### 12.3. Gửi rejected item qua message queue

Nếu muốn đẩy rejected item sang hệ thống data quality:

```text
SkipListener
    |
    +-- Ghi rejection/outbox cùng transaction
           |
           v
      Transaction commit
           |
           v
      Outbox publisher
           |
           v
      Data quality queue/topic
```

Bộ publish có thể gửi lại sau lỗi, nên consumer cần xử lý **idempotent**. Dùng event ID ổn định và quy tắc dedup rõ ràng. Tránh gửi trực tiếp message từ callback nếu mục tiêu là “chỉ báo cáo những item skip đã commit”.

## 13. Báo cáo số liệu tổng hợp bằng `StepExecution`

Spring Batch duy trì các bộ đếm theo StepExecution:

| API | Ý nghĩa |
| --- | --- |
| `getReadCount()` | Số item đọc thành công theo cơ chế Step. |
| `getWriteCount()` | Số item ghi thành công được thống kê. |
| `getFilterCount()` | Số item bị processor lọc bằng `null`. |
| `getReadSkipCount()` | Số lần skip ở reader. |
| `getProcessSkipCount()` | Số item bị skip ở processor. |
| `getWriteSkipCount()` | Số item bị skip ở writer. |
| `getSkipCount()` | Tổng số skip theo Step. |
| `getCommitCount()` | Số commit đã được ghi nhận. |
| `getRollbackCount()` | Số rollback đã được ghi nhận. |

Có thể dùng `StepExecutionListener.afterStep` để phát log tổng hợp, hoặc đọc qua `JobExplorer` sau khi Job kết thúc:

```java
for (StepExecution step : execution.getStepExecutions()) {
    log.info(
        "batch.step.quality jobExecutionId={} "
            + "stepExecutionId={} stepName={} status={} "
            + "read={} written={} filtered={} "
            + "readSkipped={} processSkipped={} writeSkipped={} "
            + "totalSkipped={}",
        execution.getId(),
        step.getId(),
        step.getStepName(),
        step.getStatus(),
        step.getReadCount(),
        step.getWriteCount(),
        step.getFilterCount(),
        step.getReadSkipCount(),
        step.getProcessSkipCount(),
        step.getWriteSkipCount(),
        step.getSkipCount()
    );
}
```

Một báo cáo tổng hợp hữu ích:

```text
Job: importPaymentsJob
JobInstance: 42
JobExecution: 811
Status: COMPLETED
Input physical records: 10
Read successfully: 9
Read rejected: 1
Process rejected: 2
Write rejected: 0
Filtered: 0
Written: 7
Total rejected: 3
Rejection report: payment-rejections-811.csv
```

`Input physical records` không phải bộ đếm có sẵn trong mọi `StepExecution`. Nó cần được lấy từ manifest nguồn hoặc một cơ chế thống kê riêng. Đừng suy diễn số dòng vật lý trong mọi reader chỉ từ `readCount + readSkipCount` nếu có header, dòng trống, multi-line record hoặc cơ chế reader khác.

### Tại sao cần đối chiếu bảng rejection với Step counters?

Trong một JobExecution bình thường, ta mong số rejected item lưu được tương thích với số skip của Step. Nhưng nếu hệ thống báo cáo dùng transaction khác, dedup theo business key hoặc có retention khác, số bản ghi có thể lệch.

Một truy vấn minh họa:

```sql
SELECT
    step_execution_id,
    phase,
    COUNT(*) AS rejection_count
FROM batch_rejected_item
WHERE job_execution_id = :jobExecutionId
GROUP BY step_execution_id, phase
ORDER BY step_execution_id, phase;
```

Khi lệch, cần kiểm tra transaction, duplicate key, listener registration, policy và thời điểm query. Không mặc định “metadata sai” hoặc tự cập nhật bộ đếm metadata để khớp báo cáo.

## 14. Thiết kế lỗi có cấu trúc để hỗ trợ xử lý lại

Người vận hành cần biết **có thể làm gì với rejection**. Một chuỗi stack trace không phải báo cáo chất lượng dữ liệu tốt.

Nên thiết kế mã lỗi và nhóm xử lý, ví dụ:

| Error code | Giai đoạn | Ý nghĩa | Hướng xử lý |
| --- | --- | --- | --- |
| `INVALID_AMOUNT_FORMAT` | READ | Số tiền không parse được. | Sửa cột amount hoặc điều chỉnh nguồn xuất. |
| `AMOUNT_MUST_BE_POSITIVE` | PROCESS | Số tiền không dương. | Kiểm tra nghiệp vụ/nguồn dữ liệu. |
| `MISSING_REQUIRED_FIELD` | READ/PROCESS | Thiếu trường bắt buộc. | Bổ sung trường hoặc xác minh schema. |
| `UNKNOWN_CUSTOMER` | PROCESS | Không tìm thấy mã khách hàng hợp lệ. | Đồng bộ master data hoặc cập nhật mapping. |
| `DUPLICATE_BUSINESS_KEY` | PROCESS/WRITE | Trùng khóa nghiệp vụ. | Kiểm tra idempotency hoặc logic nhận diện trùng. |
| `WRITE_CONSTRAINT_REJECTED` | WRITE | Vi phạm một ràng buộc cụ thể được phép bỏ qua. | Kiểm tra nguyên nhân và quyết định có chấp nhận reject hay không. |

Không nên biến toàn bộ lỗi hạ tầng thành `WRITE_CONSTRAINT_REJECTED`. Mã lỗi phải phản ánh đúng phân loại **dữ liệu có thể sửa** và **sự cố vận hành**.

### Retry/reprocess rejected item sau khi sửa dữ liệu

Một quy trình phổ biến:

1. Job chính lưu rejected item và hoàn thành theo policy.
2. Bộ phận vận hành hoặc pipeline data quality xem báo cáo, sửa dữ liệu nguồn.
3. Tạo một dataset **reprocess** chứa những item cần thử lại.
4. Chạy một Job hoặc Step chuyên xử lý lại, với JobParameters nhận diện lượt xử lý.
5. Gắn kết quả reprocess về rejection gốc, cập nhật `resolution_status`.
6. Dùng khóa nghiệp vụ/idempotency để không ghi trùng những item đã xử lý thành công.

Không xóa rejected item gốc ngay khi reprocess thành công nếu cần audit. Có thể đánh dấu `RESOLVED` và lưu thời điểm, phiên bản sửa dữ liệu, JobExecution đã xử lý lại.

## 15. Giới hạn chất lượng dữ liệu: số tuyệt đối và tỷ lệ

`skipLimit(100)` dễ hiểu nhưng có thể chưa đủ cho mọi khối lượng:

- Job đọc 1.000 bản ghi, reject 100 → 10% lỗi.
- Job đọc 10 triệu bản ghi, reject 100 → 0,001% lỗi.

Cùng số skip nhưng mức độ vấn đề rất khác nhau. Có thể định nghĩa cả:

- **Hard limit:** không quá 100 rejected item trong một Step.
- **Error-rate threshold:** không quá 1% bản ghi nguồn.
- **Critical-rule threshold:** lỗi thuộc nhóm đặc biệt nghiêm trọng không được skip.
- **Customer/partition threshold:** không quá X lỗi trong một nhóm dữ liệu độc lập.

Một policy điển hình:

```text
READ parse error hợp lệ ---------> skip nếu trong giới hạn
PROCESS validation error --------> skip nếu trong giới hạn
WRITE duplicate xác định --------> skip nếu nghiệp vụ cho phép
Database unavailable ------------> fail/retry theo hạ tầng
Violation thuộc nhóm critical ---> fail ngay
Tổng reject vượt ngưỡng ---------> fail hoặc đánh dấu không đạt chất lượng
```

Việc kiểm tra tỷ lệ ở cuối Job có thể thực hiện bằng Step chuyên kiểm tra quality gate, đọc bộ đếm đã commit và tổng số bản ghi nguồn. Nếu quality gate không đạt, Job nên có kết quả rõ ràng (`FAILED` hoặc exit code nghiệp vụ tùy hợp đồng). Không lặng lẽ ghi `COMPLETED` rồi để đội vận hành tự phát hiện rằng chất lượng dữ liệu không đạt.

## 16. Kiểm thử skip và báo cáo rejected item

Một bài test tích hợp cần kiểm tra **hai lớp kết quả**:

1. Spring Batch có skip đúng lỗi và cập nhật StepExecution status/counters không?
2. Báo cáo rejected item có đủ số lượng, đúng pha, đúng mã lỗi và liên kết đúng execution không?

Ví dụ Spring Batch 5.x, JUnit Jupiter và AssertJ. Giả định Job `importPaymentsJob` dùng CSV fixture ở mục 9, writer ghi vào `accepted_payment` và `PaymentSkipListener` ghi vào `batch_rejected_item`.

```java
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class PaymentRejectionIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    @Qualifier("importPaymentsJob")
    private Job job;

    @BeforeEach
    void resetTestData() {
        // Chỉ dùng trên database/schema dành riêng cho test.
        jdbc.update("DELETE FROM batch_rejected_item");
        jdbc.update("DELETE FROM accepted_payment");
        jobRepositoryTestUtils.removeJobExecutions();
        jobLauncherTestUtils.setJob(job);
    }

    @Test
    void shouldSkipAndReportThreeInvalidRows() throws Exception {
        var params = new JobParametersBuilder()
                .addString("runId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(params);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        StepExecution step = execution.getStepExecutions().stream()
                .filter(it -> "importPaymentsStep".equals(it.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(step.getReadCount()).isEqualTo(9);
        assertThat(step.getReadSkipCount()).isEqualTo(1);
        assertThat(step.getProcessSkipCount()).isEqualTo(2);
        assertThat(step.getWriteSkipCount()).isZero();
        assertThat(step.getSkipCount()).isEqualTo(3);
        assertThat(step.getWriteCount()).isEqualTo(7);

        Integer rejected = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM batch_rejected_item
                WHERE job_execution_id = ?
                  AND step_execution_id = ?
                """,
                Integer.class,
                execution.getId(),
                step.getId());

        Integer accepted = jdbc.queryForObject(
                "SELECT COUNT(*) FROM accepted_payment",
                Integer.class);

        assertThat(rejected).isEqualTo(3);
        assertThat(accepted).isEqualTo(7);
    }
}
```

Trong bài test thực tế, nên bổ sung các assert theo `phase`, `source_key` và `error_code`, ví dụ:

```java
Integer readRejected = jdbc.queryForObject(
        """
        SELECT COUNT(*) FROM batch_rejected_item
        WHERE job_execution_id = ? AND phase = 'READ'
        """,
        Integer.class,
        execution.getId());

Integer processRejected = jdbc.queryForObject(
        """
        SELECT COUNT(*) FROM batch_rejected_item
        WHERE job_execution_id = ? AND phase = 'PROCESS'
        """,
        Integer.class,
        execution.getId());

assertThat(readRejected).isEqualTo(1);
assertThat(processRejected).isEqualTo(2);
```

**Giả định của test:** CSV chứa đúng 10 data records, reader không tạo item cho dòng parse lỗi, processor reject đúng hai khoản không dương, writer hoàn thành bảy khoản còn lại, và listener cùng transaction phù hợp để lưu ba rejection. Thư viện test và schema database phải được cấu hình trước. Đây là kiểm thử **hành vi mong muốn**, không phải một test độc lập có thể chạy nếu thiếu cấu hình ứng dụng/fixture.

### Test khi vượt `skipLimit`

Tạo fixture có nhiều item lỗi hơn giới hạn:

- `skipLimit(2)`.
- Ba item vi phạm rule skippable.
- Assert `JobExecution.status == FAILED` khi lần skip tiếp theo vượt giới hạn.
- Kiểm tra log/metadata Step và báo cáo đã commit.
- Không mặc định rằng tất cả item sau bản ghi gây fail cũng đã được đọc.

Lưu ý kết quả writer và rejection đã commit trước lần fail có thể vẫn tồn tại. Spring Batch không rollback toàn bộ lịch sử những chunk đã commit chỉ vì Job cuối cùng `FAILED`.

### Test lỗi không skippable

Cho reader hoặc writer ném một loại exception **không có trong skip policy**, ví dụ lỗi datasource không thể khôi phục. Assert Job thất bại và không tự ghi một rejection mang mã “lỗi dữ liệu không hợp lệ”.

### Test rollback/retry

Dùng fixture tạo một lỗi writer được retry, sau đó thành công. Assert:

- Item được ghi đúng một lần theo business key.
- Không có rejected item cho lỗi đã retry thành công.
- Không có báo cáo trùng do writer bị gọi lại.
- `rollbackCount`/retry instrumentation phản ánh hành vi mong đợi.

## 17. Restart và báo cáo rejected item

Một JobInstance có thể có nhiều JobExecution khi lỗi rồi restart:

```text
JobInstance #42
  |
  +-- JobExecution #811: FAILED
  |     |
  |     +-- read skip r04
  |     +-- process skip r02
  |
  +-- JobExecution #812: COMPLETED (restart)
        |
        +-- process skip r06 hoặc xử lý lại tùy checkpoint
```

Báo cáo nên bảo toàn cả hai góc nhìn:

- **Theo JobExecution:** lần chạy `811` đã reject những item nào?
- **Theo JobInstance hoặc dataset:** tổng số **nguồn item duy nhất** bị reject qua nhiều lần retry/restart là bao nhiêu?

Nếu báo cáo dùng mỗi `jobExecutionId` để dedup, cùng source item có thể xuất hiện lại dưới execution ID mới. Điều đó phù hợp cho audit theo từng lần thực thi, nhưng không phải một danh sách unique rejected business records.

Khi tạo báo cáo tổng hợp cuối cùng cho nghiệp vụ, có thể nhóm theo dataset/source key và trạng thái xử lý cuối, phân biệt item lỗi chưa giải quyết với item đã xử lý thành công sau reprocess.

**Không xóa metadata Spring Batch giữa lần thất bại và lần restart.** ExecutionContext và lịch sử Step giúp xác định điểm tiếp tục. Cũng không nên xóa bảng rejected item mà chưa bảo toàn audit nếu tổ chức yêu cầu truy vết.

## 18. Xử lý đồng thời và partitioning

Khi Step dùng multi-threaded chunk processing hoặc partitioning, việc báo cáo rejected item có thêm yêu cầu:

- Listener/sink dùng chung phải thread-safe.
- Không lưu `currentItem` hoặc `currentStepExecution` vào biến mutable singleton rồi giả định chỉ có một thread.
- `source_key` phải đủ duy nhất theo partition; một số dòng “line:10” ở hai file khác nhau không phải cùng bản ghi.
- Truy vấn tổng hợp nên nhóm theo JobExecution và StepExecution; với partition, các StepExecution có thể mang tên `workerStep:partition0`, `workerStep:partition1`.
- Nếu nhiều worker ghi cùng bảng báo cáo, unique key và index phải phù hợp throughput, tránh gây lock contention không cần thiết.
- Nếu một worker lỗi, các partition khác có thể đã commit; kết quả cuối và chính sách restart phải được hiểu theo flow và partition handler.

Ví dụ khóa nguồn an toàn hơn cho partition:

```text
sourceSystem + datasetId + partitionId + recordOffset
```

Không dựa vào thứ tự dòng log để tái tạo thứ tự dữ liệu khi có concurrency.

## 19. Observability và vận hành báo cáo reject

Một hệ thống data quality nên xuất các chỉ số sau:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `batch_read_skip_total` | Tổng skip ở reader theo Job/Step và loại lỗi. |
| `batch_process_skip_total` | Tổng skip ở processor. |
| `batch_write_skip_total` | Tổng skip ở writer. |
| `batch_rejected_ratio` | Tỷ lệ rejected theo mẫu số được định nghĩa. |
| `batch_job_status` | Trạng thái cuối của JobExecution. |
| `batch_rejection_backlog` | Số rejected item chưa được xử lý lại hoặc xác nhận. |
| `batch_reprocess_success_total` | Số rejected item được sửa và xử lý lại thành công. |

Đối với metrics, không nên gắn `jobExecutionId`, `source_key` hoặc message exception vào **metric labels** vì cardinality quá lớn. Có thể gắn chúng trong log/report chi tiết. Các tag metric nên giới hạn ở `jobName`, `stepName`, `phase`, `errorCode` và các giá trị đã được kiểm soát số lượng.

Một log hoàn thành Job có thể bao gồm:

```text
INFO batch.job.dataQuality
  jobName=importPaymentsJob
  jobExecutionId=811
  stepName=importPaymentsStep
  status=COMPLETED
  readCount=9
  writeCount=7
  readSkipped=1
  processSkipped=2
  writeSkipped=0
  totalSkipped=3
  reportId=payment-rejections-811
```

Nếu Job `COMPLETED` với rejected item, dashboard không nên chỉ hiển thị trạng thái xanh “thành công hoàn toàn” mà không có thông tin quality. Có thể bổ sung cảnh báo “completed with rejected data” ở tầng báo cáo hoặc exit code tùy chỉnh nếu đó là hợp đồng vận hành đã được thống nhất.

### Thiết kế quy trình xử lý rejected item

Một quy trình vận hành dễ kiểm soát có thể gồm:

1. **NEW:** Job phát hiện và lưu rejected item.
2. **REVIEWED:** Người vận hành hoặc hệ thống phân loại nguyên nhân.
3. **CORRECTED:** Dữ liệu nguồn đã được sửa hoặc bổ sung.
4. **REPROCESSED:** Một Job khác thử xử lý lại.
5. **RESOLVED:** Kiểm tra kết quả đã được ghi thành công; đóng rejection.
6. **WAIVED:** Quy tắc nghiệp vụ chấp nhận không xử lý bản ghi, có lý do/approval.

Các trạng thái trên là thiết kế nghiệp vụ đề xuất. Phải kiểm tra rằng dữ liệu không bị đưa vào vòng retry vô hạn hoặc liên tục báo cùng lỗi mà không có hành động khắc phục.

## 20. Những sai lầm thường gặp

### 20.1. Dùng `skip(Exception.class)` cho mọi loại lỗi

Một lỗi database hoặc bug có thể bị biến thành skip, che giấu vấn đề hệ thống. Chỉ skip các exception được phân loại rõ là lỗi dữ liệu riêng lẻ có thể bỏ qua.

### 20.2. Đánh đồng filter với reject

`ItemProcessor` trả `null` thường được tính vào `filterCount`, không gọi `SkipListener`. Nếu cần báo cáo mọi dòng bị loại, phải thiết kế thêm cơ chế quan sát filter theo quy tắc nghiệp vụ.

### 20.3. Ghi rejected item ngay trong `catch` của processor

Một lỗi có thể được retry thành công hoặc transaction có thể rollback. Báo cáo lúc exception vừa xuất hiện dễ gây trùng và không phản ánh quyết định skip cuối cùng. Ưu tiên `SkipListener` hoặc cơ chế có tính transaction/commit rõ ràng.

### 20.4. Dùng raw exception message làm `errorCode`

Message có thể thay đổi hoặc chứa dữ liệu nhạy cảm. Tạo mã lỗi ổn định và chỉ ghi nội dung đã được làm sạch khi cần.

### 20.5. Không xác định nguồn item trong read skip

Reader chưa tạo được item; callback `onSkipInRead` không có đối tượng nguồn đã map. Phải khai thác vị trí dòng, offset hoặc thông tin nguồn trong exception/reader nếu có. Nếu không thể xác định nguồn đủ đáng tin cậy, cần báo một loại lỗi không xác định rõ thay vì giả vờ biết record ID.

### 20.6. Dùng unique key quá rộng trong báo cáo

Gộp theo mỗi `paymentId` có thể làm mất thông tin hai dòng nguồn khác nhau có cùng payment ID. Dùng source occurrence ID cho audit theo lần thực thi, và khóa nghiệp vụ riêng cho báo cáo hợp nhất.

### 20.7. Quên rằng chunk có thể rollback

Writer bị gọi lại, listener có thể tham gia transaction khác và side effect ngoài transaction có thể lặp. Lưu rejection trong cơ chế có rollback/idempotency phù hợp.

### 20.8. Chỉ assert `JobExecution.COMPLETED`

Job có thể hoàn tất với nhiều rejected item. Test cần kiểm tra `skipCount` theo từng pha, dữ liệu đầu ra và báo cáo rejection, không chỉ trạng thái cuối.

### 20.9. Dọn metadata trước khi xuất báo cáo

Nếu báo cáo cần `jobExecutionId`, StepExecution counters hoặc tham số Job, xóa metadata trước khi tổng hợp sẽ làm mất thông tin đối chiếu. Giữ metadata đủ lâu theo chính sách retention và hoàn thành việc xuất report.

### 20.10. Không xử lý dữ liệu bị reject

Nếu báo cáo chỉ được tạo rồi bỏ đó, chất lượng dữ liệu có thể giảm dần. Cần quy trình review, sửa dữ liệu, reprocess và đóng rejection, cùng metric backlog và SLA phù hợp.

## 21. Bài tập thực hành

Giả sử `importCustomersJob` nhận một file CSV gồm 1.000 khách hàng. Trong đó có:

- 20 dòng thiếu email bắt buộc.
- 5 dòng có ngày sinh không parse được.
- 3 dòng bị trùng mã khách hàng theo quy tắc nghiệp vụ.
- Những dòng còn lại hợp lệ.

Hãy xây dựng một Step có khả năng bỏ qua các lỗi dữ liệu được phép và tạo báo cáo rejected item.

### Yêu cầu kỹ thuật

1. Định nghĩa các exception `MissingRequiredEmailException`, `InvalidBirthDateException` và `DuplicateCustomerException`; quyết định chính xác exception nào được skip.
2. Cấu hình `faultTolerant()`, whitelist exception và `skipLimit` hợp lý.
3. Viết `SkipListener` lấy source position ở READ và source key từ item ở PROCESS/WRITE.
4. Lưu rejection vào bảng có `jobExecutionId`, `stepExecutionId`, `phase`, `sourceKey` và `errorCode`.
5. Sau Job, xuất báo cáo CSV/JSON chỉ từ dữ liệu rejection đã commit.
6. Dùng `JobExplorer` hoặc `JobExecution.getStepExecutions()` để đối chiếu số skip theo pha.
7. Kiểm tra bản ghi hợp lệ được ghi đúng một lần theo business key.
8. Thử thêm trường hợp vượt skipLimit và xác nhận Job thất bại theo policy.
9. Thử lỗi database không nằm trong whitelist và xác nhận lỗi đó **không** được lặng lẽ bỏ qua.
10. Thử restart sau lỗi có kiểm soát và xác minh lịch sử rejection theo từng JobExecution.

### Một kết quả mong đợi

Nếu cả 28 bản ghi lỗi được nhận diện thành các lần skip riêng biệt, không có filter khác, giới hạn skip cho phép ít nhất 28, Job và writer hoạt động bình thường:

```text
Input records       : 1000
Rejected READ       : 5
Rejected PROCESS    : 23
Rejected WRITE      : 0
Total rejected      : 28
Accepted / written  : 972
Job status          : COMPLETED
```

Các số trên là **kịch bản minh họa**; vị trí READ/PROCESS của duplicate hay missing email phụ thuộc bạn triển khai validation ở lớp nào. Nếu duplicate chỉ bị phát hiện khi writer ghi DB, có thể phát sinh write skip thay vì process skip; cần thay đổi report và test theo cấu hình thật.

### Câu hỏi tự đánh giá

- `skipLimit(10)` cho phép bao nhiêu item bị skip trước khi Step thất bại?
- Vì sao lỗi READ có thể không cung cấp một item đã map thành công?
- Khi nào nên trả `null` từ `ItemProcessor`, khi nào nên ném exception để skip?
- Vì sao không nên ghi rejected item bằng HTTP request trực tiếp trong `onSkipInWrite`?
- Nếu writer retry ba lần rồi thành công, bản ghi đó có phải rejected item không?
- Vì sao `readCount` không nhất thiết bằng số dòng vật lý trong file?
- Nếu lần restart tạo `JobExecution` mới, làm cách nào báo cáo cả lịch sử và số rejected item unique?
- Vì sao Job `COMPLETED` vẫn có thể cần cảnh báo data quality?

## Tài liệu tham khảo

- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): cấu hình `faultTolerant`, exception được skip và `skipLimit`.
- [Spring Batch Reference – Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `SkipListener` và các listener liên quan.
- [Spring Batch Reference – Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry và cách phối hợp với fault-tolerant Step.
- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): reader, processor, writer và transaction.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): quan sát Job/Step, bộ đếm xử lý và kết quả.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử Job và Step với `spring-batch-test`.

