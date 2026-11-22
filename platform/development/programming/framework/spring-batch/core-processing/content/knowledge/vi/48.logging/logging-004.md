# Không log toàn bộ dữ liệu nhạy cảm trong Spring Batch

Khi một Spring Batch job xử lý hàng nghìn hoặc hàng triệu bản ghi, logging là công cụ quan trọng để biết job đã bắt đầu chưa, step nào thất bại, bao nhiêu item được đọc/ghi, có retry hay skip hay không và lỗi thuộc nhóm nào. Nhưng nếu mỗi lần đọc, xử lý hoặc ghi đều in ra toàn bộ item, log có thể vô tình trở thành một bản sao dữ liệu sản xuất: số tài khoản, địa chỉ, số điện thoại, thông tin thanh toán, token, hồ sơ khách hàng và các trường nội bộ khác.

**Nguyên tắc của bài học: ghi đủ thông tin để điều tra vận hành, nhưng không log toàn bộ dữ liệu nhạy cảm.** Cách thực hiện bền vững nhất là **thiết kế một danh sách trường được phép log (allowlist)**, rồi chủ động tạo sự kiện quan sát từ các trường an toàn. Che một vài chuỗi bằng regex chỉ là lớp bảo vệ bổ sung, vì nội dung nhạy cảm có thể nằm trong object, exception, stack trace, HTTP client log, SQL bind parameter hoặc metadata của Spring Batch.

Trong ngữ cảnh **Spring Batch Core Processing → Logging**, cần đặc biệt quan tâm các điểm tiếp xúc dữ liệu: `ItemReader`, `ItemProcessor`, `ItemWriter`, listener, `JobParameters`, `ExecutionContext`, fault tolerance (skip/retry), `JobRepository` và luồng xử lý bất đồng bộ. Những ví dụ Java dưới đây dùng API Spring Batch 5.x trở lên (writer nhận `Chunk`), Java 17+ và logging qua SLF4J.

## 1. Vì sao log toàn bộ item là một vấn đề?

Giả sử file đầu vào chứa các bản ghi thanh toán:

~~~csv
payment_id,customer_name,email,account_number,amount
PAY-001,Nguyen An,an@example.test,1234567890123456,250000.00
PAY-002,Tran Binh,binh@example.test,9876543210987654,750000.00
~~~

Hai dòng này sử dụng dữ liệu giả lập để minh họa. Trong môi trường thực tế, nếu reader hoặc processor dùng:

~~~java
log.info("Read item: {}", item);
~~~

và `item.toString()` bao gồm mọi trường, chỉ riêng bước đọc đã đẩy tên, email và tài khoản của khách hàng vào hệ thống log. Nếu một job chạy lại do lỗi hoặc retry nhiều lần, cùng bản ghi còn có thể xuất hiện trong log nhiều lần.

Hậu quả có thể xảy ra:

- Người có quyền xem log nhưng **không có quyền xem dữ liệu gốc** vẫn đọc được thông tin nhạy cảm.
- Log được sao chép qua stdout, Docker/Kubernetes logging, collector, hệ thống tìm kiếm, dashboard, alert, vé hỗ trợ hoặc công cụ theo dõi lỗi.
- Thời gian lưu log có thể dài hơn thời gian cần thiết để xử lý dữ liệu; dữ liệu bị nhân bản sang nhiều hệ thống khó xóa đồng bộ.
- Một exception chứa toàn bộ dòng input hoặc câu SQL với tham số có thể lộ dữ liệu dù không có câu lệnh `log.info(item)` trực tiếp.
- Log quá chi tiết khiến việc tìm lỗi thật bị chìm trong hàng triệu bản ghi, tăng chi phí lưu trữ và xử lý.

Vì vậy, logging an toàn vừa là yêu cầu bảo vệ dữ liệu vừa là một cách làm cho monitoring hữu ích hơn. Thay vì xem toàn bộ nội dung payment, người vận hành thường chỉ cần biết **job nào, execution nào, step nào, loại lỗi nào, số lượng bao nhiêu và tại vị trí nào**.

## 2. Xác định dữ liệu nào được phép xuất hiện trong log

Một hệ thống nên phân loại dữ liệu theo mức nhạy cảm và mục đích sử dụng. Danh sách sau là ví dụ thiết kế, không thay thế chính sách phân loại dữ liệu hoặc nghĩa vụ pháp lý cụ thể của tổ chức.

| Nhóm thông tin | Ví dụ | Cách ứng xử gợi ý trong log |
|---|---|---|
| Bí mật xác thực | Password, API key, bearer token, cookie phiên, secret dùng ký số | **Không ghi giá trị** trong log hoặc stack trace; thay bằng mã loại lỗi và tên thành phần. |
| Dữ liệu định danh cá nhân | Họ tên, email, điện thoại, địa chỉ, số định danh | Mặc định không ghi; chỉ dùng thông tin giảm thiểu hoặc token khi thật sự cần. |
| Dữ liệu thanh toán/tài chính | Số tài khoản, số thẻ, hồ sơ giao dịch, số dư | Không dump item; số lượng và tổng hợp theo chính sách có thể đủ. |
| Dữ liệu nghiệp vụ mật | Giá hợp đồng, thông tin đối tác, công thức tính phí, hồ sơ nội bộ | Xem là nhạy cảm theo hợp đồng và phân quyền truy cập. |
| Nội dung đầu vào chưa xác thực | Toàn bộ CSV line, JSON payload, XML fragment, HTTP body | Không ghi nguyên văn; có thể chứa trường nhạy cảm hoặc ký tự điều khiển. |
| Metadata batch | `jobName`, `stepName`, `jobExecutionId`, `stepExecutionId`, số item/skip/rollback | Thường phù hợp để log, sau khi đảm bảo không chứa payload. |
| Định danh quan sát | `correlationId`, `requestId`, `triggerType` | Có ích khi là token an toàn; cần kiểm soát định dạng và không chứa PII. |
| Mã lỗi được chuẩn hóa | `FILE_FORMAT`, `VALIDATION_FAILED`, `DB_TIMEOUT` | Phù hợp để lọc, thống kê và tạo cảnh báo. |

Một **mã giao dịch nội bộ** vẫn có thể nhạy cảm nếu nó cho phép tra cứu dữ liệu khách hàng ngoài ý muốn. Không được mặc định “không phải email thì chắc chắn an toàn”. Cách đơn giản nhất là xác định một tập metadata an toàn theo hợp đồng và không đưa giá trị khác vào logger.

### Mục tiêu cụ thể của logging batch

Một log sự kiện có thể cho biết:

~~~json
{
  "event": "batch.step.completed",
  "jobName": "paymentImportJob",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stepExecutionId": 9204,
  "status": "COMPLETED",
  "readCount": 1500,
  "writeCount": 1498,
  "readSkipCount": 1,
  "processSkipCount": 1,
  "writeSkipCount": 0
}
~~~

Đây là ví dụ về **schema log do ứng dụng định nghĩa**, không phải JSON Spring Batch tự phát ra mặc định. Các bộ đếm cho biết khối lượng xử lý và vị trí lỗi, không có tên/email/số tài khoản. Muốn biết một lỗi thuộc request nào, có thể bổ sung `correlationId` an toàn, rồi dùng `jobExecutionId` để tra `JobRepository`.

## 3. Các vị trí dễ làm rò rỉ dữ liệu trong pipeline

Spring Batch xử lý item theo luồng thường gặp:

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu"] --> B["ItemReader"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter"]
    D --> E["Database / file / API"]
    B -. lỗi parse .-> F["Listeners / logger"]
    C -. lỗi validation .-> F
    D -. lỗi ghi .-> F
    F --> G["Stdout / log collector / dashboard"]
~~~

Các vị trí cần rà soát:

| Nguồn log | Câu lệnh hoặc hành vi có nguy cơ | Vấn đề |
|---|---|---|
| `ItemReader` | `log.debug("item={}", item)` | Gọi `toString()` của item, có thể in toàn bộ dòng. |
| `ItemProcessor` | `log.warn("Invalid customer: {}", item)` | Lỗi validation làm lộ cả dữ liệu không liên quan. |
| `ItemWriter` | `log.error("Failed chunk: {}", chunk)` | Một chunk có thể gồm hàng trăm item nhạy cảm. |
| `ItemReadListener.onReadError` | `log.error("Read failed", exception)` | Exception parse file có thể chứa dòng đầu vào gốc. |
| `ItemProcessListener.onProcessError` | `log.error("Bad item {}", item, exception)` | Lộ item và có thể lộ thêm thông tin trong exception. |
| `ItemWriteListener.onWriteError` | `log.error("Write failed {}", items, exception)` | In cả `Chunk` và stack trace với payload. |
| `SkipListener` / retry listener | Log mọi item bị bỏ qua hoặc thử lại | Dữ liệu nhạy cảm có thể lặp nhiều lần. |
| `JobParameters` / `ExecutionContext` | Dump toàn bộ map trạng thái | Lộ tham số đầu vào, đường dẫn, metadata hoặc state người phát triển đã lưu. |
| Hạ tầng JDBC/JPA | Debug SQL, bind parameters, lỗi constraint | Có thể lộ giá trị cột hoặc thông tin kết nối. |
| HTTP/message client | Debug request/response body, headers | Có thể lộ token, payload đã xử lý, dữ liệu từ hệ thống khác. |
| Monitoring/tracing | Đưa toàn bộ item làm span attribute | Truyền dữ liệu nhạy cảm sang backend tracing. |

**Nguy hiểm không chỉ nằm ở log do lập trình viên viết.** Những thư viện đang bật DEBUG/TRACE, interceptor của API client, error reporting SDK, formatter JSON và cấu hình log collection cũng có thể xuất payload.

## 4. Những anti-pattern phổ biến trong Spring Batch

### 4.1. Log trực tiếp item

~~~java
// Không nên khi item chứa thông tin nhạy cảm:
log.info("Processing payment: {}", payment);
~~~

Với Java record hoặc Lombok `@Data`, phương thức `toString()` thường bao gồm nhiều trường. Khi model thêm một trường mới như `accessToken`, câu log cũ có thể đột nhiên lộ thêm dữ liệu mà không cần ai sửa logging.

Thay thế bằng thông tin mô tả hành vi:

~~~java
log.debug("Processing payment record");
~~~

Trong pipeline nhiều item, một dòng log cho từng bản ghi vẫn có thể gây quá tải. Nếu không cần điều tra ở mức item, hãy log số đếm theo chunk/step. Nếu cần liên kết một item, cân nhắc **opaque record reference** do hệ thống cấp và đã được đánh giá an toàn.

### 4.2. In nguyên chunk khi ghi thất bại

~~~java
// Có thể làm lộ hàng chục hoặc hàng trăm bản ghi:
log.error("Chunk write failed: {}", chunk);
~~~

Thay bằng:

~~~java
log.warn("batch.write.failed category={} chunkItemCount={}",
    "DATA_CONSTRAINT",
    chunk.size());
~~~

`chunk.size()` là thông tin vận hành. Không in `chunk.getItems()` hoặc serialize chunk ra JSON chỉ để biết lỗi xảy ra ở đâu.

### 4.3. In exception mà chưa kiểm soát nội dung

~~~java
// Exception có thể chứa raw input, SQL parameters hoặc HTTP body:
log.error("Cannot parse input", exception);
~~~

Trong Java logging, đối số cuối là `Throwable` thường khiến logger in stack trace và message của toàn bộ cause chain. Điều này hữu ích khi chẩn đoán lỗi kỹ thuật, nhưng **không thể mặc định là an toàn** nếu exception do parser hoặc SDK tạo ra từ input nhạy cảm.

Thay thế ở luồng log thông thường:

~~~java
log.warn("batch.read.failed category={} lineNumber={}",
    "FILE_FORMAT",
    17);
~~~

Trong một số sự cố thực sự cần stack trace, hãy phân loại nguồn exception trước và dùng **kênh chẩn đoán được kiểm soát quyền truy cập, retention và nội dung**; không tự động chuyển nguyên exception chứa dữ liệu khách hàng sang hệ thống log tập trung.

### 4.4. Dùng toàn bộ JobParameters để truy vết

~~~java
// Không nên làm mặc định:
log.info("Job parameters: {}", jobExecution.getJobParameters());
~~~

`JobParameters` có thể chứa đường dẫn file, tên đối tác, định danh khách hàng hoặc tham số khác mà người khởi chạy đưa vào. Tương tự, `ExecutionContext` có thể chứa state do reader/writer hoặc ứng dụng lưu phục vụ restart.

Thay bằng các field chọn trước:

~~~java
log.info("Job started jobName={} jobExecutionId={}",
    jobExecution.getJobInstance().getJobName(),
    jobExecution.getId());
~~~

Chỉ thêm business key nếu đã xác định nó không chứa PII hoặc giá trị mật.

## 5. Allowlist: chỉ log trường đã được cho phép

Có hai chiến lược chính:

**Denylist/redaction:** Cho phép log đối tượng rồi tìm và che những trường trông giống email, token hoặc số tài khoản.

**Allowlist:** Xây bản ghi log chỉ từ những field đã xác định là an toàn như `jobExecutionId`, `stepName`, `errorCode` và các bộ đếm.

Allowlist phù hợp làm **phòng tuyến chính** vì khi model có một trường nhạy cảm mới, nó không tự động xuất hiện trong log. Redaction vẫn hữu ích như lớp giảm thiểu bổ sung ở logger/collector, nhưng regex không thể hiểu đầy đủ ngữ nghĩa dữ liệu.

Ví dụ:

~~~java
record PaymentInput(
    String paymentId,
    String customerName,
    String email,
    String accountNumber,
    java.math.BigDecimal amount
) {}

// Không tự tạo log bằng payment.toString().
// Những trường được chọn là metadata của quá trình xử lý.
log.info("batch.item.rejected category={} stepName={}",
    "BUSINESS_VALIDATION",
    "validatePaymentsStep");
~~~

Nếu cần biết record nào gây lỗi, một hướng là lưu thông tin chi tiết ở **kho dữ liệu nghiệp vụ có kiểm soát truy cập** và ghi một token tham chiếu an toàn trong log. Token này không nên tự tiết lộ ID khách hàng hoặc có thể đoán tuần tự để truy cập dữ liệu.

## 6. Ví dụ listener ghi log an toàn khi Step bắt đầu và kết thúc

Đối với monitoring tổng quan, `StepExecution` đã có nhiều thông tin hữu ích mà không cần truy cập từng item: số lần đọc, ghi, skip, rollback, commit và trạng thái cuối.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class SafeStepLoggingListener implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(SafeStepLoggingListener.class);

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info(
            "batch.step.started jobExecutionId={} stepExecutionId={} stepName={}",
            stepExecution.getJobExecution().getId(),
            stepExecution.getId(),
            stepExecution.getStepName()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "batch.step.finished jobExecutionId={} stepExecutionId={} " +
            "stepName={} status={} exitCode={} read={} written={} " +
            "filtered={} readSkipped={} processSkipped={} writeSkipped={} " +
            "commits={} rollbacks={}",
            stepExecution.getJobExecution().getId(),
            stepExecution.getId(),
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
        );
        return null; // Giữ nguyên ExitStatus hiện tại.
    }
}
~~~

Những điểm cần lưu ý:

- Các trường ghi ra là **metadata về execution**, không phải `StepExecution.toString()` hay danh sách item.
- `ExitStatus.getExitCode()` là thông tin tóm lược. **Không log mặc định `getExitDescription()`**, vì một exit description có thể chứa stack trace hoặc message của exception, trong đó có dữ liệu đầu vào.
- Bộ đếm của Spring Batch phản ánh các giai đoạn xử lý. `readCount` không nhất thiết bằng tổng số dòng vật lý khi có header, lỗi đọc hoặc skip; dùng đúng ý nghĩa từng chỉ số.
- Nếu tên step hoặc metadata được sinh từ dữ liệu không đáng tin cậy, cần chuẩn hóa trước khi đưa vào log.
- Listener cần được gắn vào step mục tiêu. Có thể đăng ký bằng `.listener(safeStepLoggingListener)` trong cấu hình `StepBuilder`.

Ví dụ cấu hình:

~~~java
@Bean
Step paymentImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer,
        SafeStepLoggingListener safeStepLoggingListener) {

    return new StepBuilder("paymentImportStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(safeStepLoggingListener)
        .build();
}
~~~

Ví dụ giả định đã có `PaymentInput`, `PaymentOutput` và các bean reader/processor/writer tương ứng. Phần trình bày chỉ tập trung vào việc gắn listener để log metadata; cấu hình nghiệp vụ của job có thể phức tạp hơn.

## 7. Logging an toàn trong ItemReadListener

Khi đọc CSV, lỗi parser có thể chứa toàn bộ dòng gốc. Ví dụ `FlatFileParseException` có phương thức `getInput()` lấy nội dung đầu vào gây lỗi và `getLineNumber()` lấy số dòng. Chính việc log `exception` hoặc `exception.getInput()` có thể làm lộ thông tin mà hệ thống đáng lẽ chỉ xử lý trong bộ nhớ.

Một listener chuyên ghi metadata:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.ItemReadListener;
import org.springframework.batch.item.file.FlatFileParseException;

public class SafeReadErrorListener
        implements ItemReadListener<PaymentInput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeReadErrorListener.class);

    @Override
    public void onReadError(Exception error) {
        if (error instanceof FlatFileParseException parseError) {
            log.warn(
                "batch.read.failed category={} lineNumber={}",
                "FILE_FORMAT",
                parseError.getLineNumber()
            );
        } else {
            log.warn("batch.read.failed category={}", "READER_ERROR");
        }
    }
}
~~~

Như vậy, một lỗi ở dòng 17 sẽ có log:

~~~text
batch.read.failed category=FILE_FORMAT lineNumber=17
~~~

Thay vì:

~~~text
Could not parse line 17: PAY-019,Nguyen An,an@example.test,1234567890123456,...
~~~

**Số dòng không phải nội dung dòng.** Nó thường đủ giúp nhóm có quyền truy cập nguồn dữ liệu định vị bản ghi lỗi trong công cụ kiểm tra riêng. Với nguồn có cấu trúc khác (database, queue, API), cần chọn metadata vị trí phù hợp mà không làm lộ payload.

Nếu reader nhận dữ liệu qua nhiều resource, một `resourceAlias` được định nghĩa từ cấu hình có thể hữu ích hơn đường dẫn file nguyên vẹn. Đường dẫn tuyệt đối có thể tiết lộ tên người dùng, cấu trúc hạ tầng hoặc thông tin khách hàng được nhúng trong tên file.

## 8. Logging trong processor, writer và skip/retry

### Processor

`ItemProcessListener.onProcessError(item, exception)` nhận chính item gây lỗi; rất tiện để debug nhưng dễ lộ dữ liệu khi nối object vào thông điệp. Nên log **loại lỗi** và ngữ cảnh step:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.ItemProcessListener;

public class SafeProcessErrorListener
        implements ItemProcessListener<PaymentInput, PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeProcessErrorListener.class);

    @Override
    public void onProcessError(PaymentInput item, Exception error) {
        // Không ghi item, exception message hay exception.toString().
        log.warn("batch.process.failed category={}", "VALIDATION_OR_TRANSFORM");
    }
}
~~~

Khi lỗi processor có nhiều loại, không cần in raw message để phân biệt. Có thể ánh xạ exception thành một **mã lỗi được chuẩn hóa** theo allowlist, ví dụ `INVALID_AMOUNT`, `MISSING_REQUIRED_FIELD` hoặc `UNSUPPORTED_CURRENCY`. Mã lỗi đó được định nghĩa bởi ứng dụng và không chứa giá trị thực tế mà người dùng đã nhập.

### Writer

Từ Spring Batch 5.x, `ItemWriteListener` nhận `Chunk<? extends T>`. Không nên đưa chunk này vào logger:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriteListener;

public class SafeWriteErrorListener
        implements ItemWriteListener<PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeWriteErrorListener.class);

    @Override
    public void onWriteError(
            Exception error,
            Chunk<? extends PaymentOutput> items) {
        log.warn(
            "batch.write.failed category={} attemptedItemCount={}",
            "WRITE_ERROR",
            items.size()
        );
    }
}
~~~

Số `attemptedItemCount` ở đây mô tả kích thước chunk được truyền trong callback lỗi, **không phải số item đã commit**. Nếu writer cùng transaction của step và lỗi dẫn đến rollback, kết quả commit phải được xác định theo trạng thái transaction và `StepExecution`, không suy ra từ log trên.

### Skip và retry

Khi step có `.faultTolerant()`, Spring Batch có thể thử lại hoặc bỏ qua item lỗi theo chính sách. Các callback có thể chạy nhiều lần, đặc biệt khi writer phải rollback và xử lý lại chunk để cô lập item gây lỗi.

Ví dụ một `SkipListener` log theo mã lỗi:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SafePaymentSkipListener
        implements SkipListener<PaymentInput, PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafePaymentSkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("batch.item.skipped stage=READ category=FILE_FORMAT");
    }

    @Override
    public void onSkipInProcess(PaymentInput item, Throwable error) {
        log.warn("batch.item.skipped stage=PROCESS category=VALIDATION");
    }

    @Override
    public void onSkipInWrite(PaymentOutput item, Throwable error) {
        log.warn("batch.item.skipped stage=WRITE category=WRITE_ERROR");
    }
}
~~~

Đây là ví dụ về việc **không in item**; trong ứng dụng thực, code phân loại lỗi phải dựa trên exception và chính sách skip cụ thể. Không nên gán mọi lỗi đọc là `FILE_FORMAT` nếu reader còn có thể lỗi kết nối hoặc I/O.

Không nên tạo một log `ERROR` cho mọi lần retry tạm thời rồi lại tạo `ERROR` khi step cuối cùng thất bại. Với tải lớn, điều đó tạo nhiễu và khiến một lỗi gốc bị đếm nhiều lần. Có thể ghi số lần retry theo metric/bộ đếm phù hợp và phát **một sự kiện tổng kết** khi step kết thúc, đồng thời giữ một số log lỗi đã chuẩn hóa ở mức đủ để điều tra.

## 9. Chuẩn hóa mã lỗi thay vì in exception message

`Throwable.getMessage()` và `Throwable.toString()` thường chứa nội dung không được kiểm soát. Các lớp exception do chính ứng dụng tạo ra cũng có thể vô tình ghép trường nhạy cảm:

~~~java
// Không nên:
throw new IllegalArgumentException(
    "Invalid account number " + payment.accountNumber()
);
~~~

Nếu lỗi được ghi bởi framework, message đã tiết lộ tài khoản dù logger không in `payment` trực tiếp.

Thay bằng exception/mã lỗi có thông điệp tách biệt khỏi dữ liệu nhạy cảm:

~~~java
throw new PaymentValidationException("INVALID_ACCOUNT_FORMAT");
~~~

Một hàm phân loại exception phục vụ logging:

~~~java
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.TransientDataAccessException;

static String safeErrorCode(Throwable error) {
    if (error instanceof FlatFileParseException) {
        return "FILE_FORMAT";
    }
    if (error instanceof DataIntegrityViolationException) {
        return "DATA_CONSTRAINT";
    }
    if (error instanceof TransientDataAccessException) {
        return "DATABASE_TRANSIENT";
    }
    if (error instanceof PaymentValidationException) {
        return "BUSINESS_VALIDATION";
    }
    return "UNCLASSIFIED_FAILURE";
}
~~~

`PaymentValidationException` là loại exception do ứng dụng minh họa tự định nghĩa. Với các exception được wrap nhiều lớp, một bộ phân loại thực tế có thể đi qua cause chain **để chọn mã lỗi**, nhưng không ghi message hoặc toàn bộ exception vào log thông thường.

Mã lỗi cần có danh mục và định nghĩa rõ; không dùng tên mã lỗi được tạo bằng cách nối giá trị người dùng nhập, ví dụ `"INVALID_ACCOUNT_" + accountNumber`.

### Khi cần stack trace

Không có nghĩa mọi stack trace đều bị cấm. Đối với lỗi lập trình như `NullPointerException` ở một vùng code không mang dữ liệu nhạy cảm, stack trace là dữ liệu chẩn đoán hữu ích. Nhưng không nên áp dụng một chính sách log mọi exception nguyên vẹn ở mọi tầng.

Có thể lựa chọn:

1. Log sự kiện an toàn thường trực bằng `errorCode`, job/step IDs, timestamp và số dòng/metadata an toàn.
2. Giữ stack trace trong kênh chẩn đoán có quyền truy cập và retention chặt chẽ **sau khi xác định nguồn exception không đưa raw input hoặc secrets vào message/cause**.
3. Nếu cần tra dòng lỗi thực, để người vận hành có quyền thích hợp dùng công cụ nội bộ truy cập dữ liệu gốc qua một reference, không sao chép dòng đó vào logging pipeline.

## 10. Redaction và masking: có ích nhưng không đủ

**Masking** thường che một phần dữ liệu, ví dụ chỉ hiển thị vài ký tự cuối của định danh. **Redaction** có thể thay toàn bộ giá trị bằng `[REDACTED]`. Hai kỹ thuật này không hoàn toàn giống việc loại bỏ field khỏi log.

| Cách làm | Ví dụ dạng log | Giới hạn |
|---|---|---|
| Không log field | `category=INVALID_ACCOUNT` | Giảm nguy cơ nhất vì giá trị không đi vào pipeline log. |
| Redact toàn bộ | `account=[REDACTED]` | Có thể hữu ích khi format cũ cần field, nhưng phải bảo đảm tất cả đường log đều được xử lý. |
| Mask một phần | `account=************3456` | Phần còn lại vẫn có thể định danh lại khi kết hợp với dữ liệu khác. |
| Regex lọc sau khi ghi | Thay pattern giống email/số thẻ | Bỏ sót định dạng lạ, dữ liệu encode, trường mới; giá trị có thể đã đi qua thành phần trước khi lọc. |
| Hash không khóa | `sha256(email)` | Email/số điện thoại có miền giá trị dễ đoán; đối tượng tấn công có thể thử từ điển. |
| HMAC có khóa | Token ổn định dựa trên secret nội bộ | Cần quản lý secret/rotation, vẫn có rủi ro liên kết các bản ghi; chỉ dùng khi thật cần đối chiếu. |

Nếu nghiệp vụ cần tìm các sự kiện cùng một khách hàng mà không log email thật, có thể sử dụng một **token tham chiếu nội bộ** hoặc HMAC có khóa, với secret quản lý bởi hạ tầng thích hợp. Dù vậy, token vẫn có thể là dữ liệu nhạy cảm theo ngữ cảnh nếu nó cho phép theo dõi một người trong thời gian dài.

Không nên sử dụng `email.hashCode()` hay SHA-256 đơn thuần để tuyên bố rằng email đã “ẩn danh hoàn toàn”. Những giá trị có thể đoán được thường dễ bị dò theo từ điển hoặc liên kết với dữ liệu ngoài.

### Ưu tiên ngăn dữ liệu nhạy cảm từ nguồn

Nếu code tạo `log.info("{}", payment)` rồi trông chờ một regex ở collector che hết, dữ liệu thô đã có thể đi qua logger, buffer hoặc stdout trước khi bị che. Cách tiếp cận chắc chắn hơn là:

~~~text
Domain object chứa dữ liệu nhạy cảm
    |
    v
Chọn field an toàn / mã lỗi chuẩn hóa
    |
    v
Structured log event
    |
    v
Logger -> Collector -> Dashboard
~~~

Với các hệ thống đã tồn tại nhiều log cũ, bộ lọc redaction cấp hạ tầng có thể là lớp giảm thiểu rủi ro tạm thời trong quá trình sửa ứng dụng. Nhưng nó không thay thế việc loại bỏ log raw payload ở source.

## 11. JobParameters, ExecutionContext và JobRepository

Trong Spring Batch, dữ liệu phục vụ vận hành và restart được lưu theo nhiều lớp:

- `JobParameters`: tham số khởi chạy job, có thể chứa đường dẫn file đầu vào, source ID, ngày xử lý hoặc các giá trị do caller cung cấp.
- `ExecutionContext`: trạng thái serializable của job/step, phục vụ checkpoint hoặc restart.
- `JobExecution` và `StepExecution`: trạng thái, thời gian, bộ đếm, exit status và các thông tin khác.
- `JobRepository`: lưu metadata bền vững, thường trong các bảng `BATCH_*`.

**Không biến JobParameters hoặc ExecutionContext thành kho chứa secrets.** Dữ liệu được lưu để phục vụ thực thi/restart có thể tồn tại lâu và được đọc bởi công cụ vận hành, không chỉ bởi một logger.

Ví dụ nên tránh:

~~~java
new JobParametersBuilder()
    .addString("accessToken", token, false)
    .toJobParameters();
~~~

Cờ `false` chỉ có nghĩa là non-identifying; nó **không làm tham số được mã hóa, giấu đi hoặc không lưu trong repository**.

Thay vào đó, lưu một tham chiếu an toàn nếu cần, rồi lấy secret từ cơ chế secret management có kiểm soát tại thời điểm thực thi. Không đưa secret vào `JobParameters` chỉ để tạo `@StepScope` bean dễ dàng hơn.

Ngoài ra, tránh:

~~~java
log.debug("Execution context: {}", stepExecution.getExecutionContext());
log.error("Job failure details: {}",
    jobExecution.getAllFailureExceptions());
~~~

Các đối tượng trên có thể chứa hoặc tham chiếu thông tin từ tầng xử lý dữ liệu và exception. Hãy chọn bộ đếm và trạng thái cụ thể cần log, thay vì serialize cả object.

## 12. SQL, HTTP, file và thư viện bên thứ ba

Ngay cả khi code ứng dụng không log item, logging chi tiết của các tầng bên dưới vẫn có thể làm lộ dữ liệu.

### JDBC/JPA

Đối với SQL, có khác biệt giữa câu lệnh mẫu có placeholder và giá trị bind thực tế:

~~~sql
INSERT INTO payment(account_number, amount)
VALUES (?, ?)
~~~

Đây là SQL cấu trúc. Nhưng nếu một logger/driver/proxy in toàn bộ binding như `account_number=1234567890123456` thì vẫn lộ dữ liệu. Cần xem xét mức logging của JDBC, Hibernate/JPA, SQL proxy, driver và exception do database trả về.

Không nên bật TRACE SQL bind parameters ở môi trường xử lý dữ liệu thật chỉ để điều tra một lỗi batch. Nếu cần nghiên cứu, ưu tiên môi trường kiểm thử dùng dữ liệu giả lập hoặc chẩn đoán trong phạm vi quyền truy cập chặt chẽ.

### HTTP client và messaging

HTTP request/response có thể chứa:

- Header `Authorization`, cookie, API key.
- JSON/XML body có dữ liệu khách hàng hoặc tài khoản.
- URL query string chứa token hoặc định danh.
- Response lỗi trích lại payload đã gửi.

Một interceptor kiểu “log full request and response” rất rủi ro khi writer gửi từng item tới đối tác. Cần cấu hình cho phép log method, tên endpoint đã chuẩn hóa, status code, thời lượng, request/correlation ID, và không log headers/body nhạy cảm. Với Kafka hoặc queue, cân nhắc tương tự cho payload và message headers.

### File

`FlatFileParseException` có thể cung cấp raw input qua `getInput()`; đừng log giá trị đó. Đường dẫn file cũng có thể chứa thông tin nhạy cảm trong tên, ví dụ tên khách hàng hoặc thư mục cá nhân. Thay thế bằng logical `resourceId` hoặc tên nguồn định nghĩa trong cấu hình.

### APM, tracing và error reporting

Không đưa full item vào span attributes, event annotations hoặc tags. Tracing pipeline cũng là nơi dữ liệu có thể được truyền tới bên thứ ba hoặc được nhiều nhóm cùng xem. `traceId` và `jobExecutionId` là phương tiện liên kết, không cần đính kèm toàn bộ record để đủ theo dõi.

## 13. Correlation: điều tra được mà không lộ payload

Một log an toàn vẫn cần trả lời được lỗi thuộc job nào. Các định danh quan sát thường hữu ích là:

| Field | Mục đích |
|---|---|
| `jobName` | Định nghĩa quy trình batch. |
| `jobInstanceId` | Công việc logic, giữ nguyên qua các restart của cùng instance. |
| `jobExecutionId` | Một lần thực thi cụ thể. |
| `stepName` / `stepExecutionId` | Định vị phần xử lý gặp lỗi. |
| `correlationId` | Nối request hoặc scheduler trigger với execution. |
| `triggerType` | Phân biệt HTTP, SCHEDULER, MANUAL, MESSAGE. |
| `errorCode` | Nhóm lỗi có định nghĩa chuẩn. |
| `lineNumber` / `resourceAlias` | Vị trí lỗi có thể tìm lại trong nguồn dữ liệu được kiểm soát quyền. |

Một bản ghi an toàn:

~~~json
{
  "event": "batch.item.skipped",
  "jobName": "paymentImportJob",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stepExecutionId": 9204,
  "correlationId": "req-301",
  "category": "FILE_FORMAT",
  "resourceAlias": "daily-payments",
  "lineNumber": 17
}
~~~

Không có email, số tài khoản, nguyên dòng CSV hoặc stack trace chứa dữ liệu. Khi cần xem bản ghi thực tế, người có quyền sử dụng `resourceAlias` và `lineNumber` để truy xuất tại hệ thống nguồn phù hợp; không cần mở rộng quyền xem log cho toàn bộ nhóm.

### MDC và thread pool

`MDC` của SLF4J có thể giúp mọi log trong cùng thread nhận `jobExecutionId` hoặc `correlationId` mà không truyền field theo từng câu lệnh:

~~~java
try {
    MDC.put("jobExecutionId", String.valueOf(jobExecution.getId()));
    MDC.put("correlationId", safeCorrelationId);
    runWork();
} finally {
    MDC.remove("jobExecutionId");
    MDC.remove("correlationId");
}
~~~

`safeCorrelationId` phải là ID đã được kiểm tra/chuẩn hóa, không chứa header tùy ý hoặc thông tin cá nhân. `MDC` là dữ liệu theo thread; nếu step dùng `TaskExecutor`, partitioning hoặc remote worker, cần thiết kế truyền context tới đúng worker, sau đó **dọn MDC** để thread tái sử dụng không mang ID của job khác.

Đặc biệt không đưa đối tượng item hoặc raw payload vào MDC: nhiều thư viện ghi MDC theo mỗi log event, khiến cùng giá trị bị nhân bản hàng nghìn lần.

## 14. Structured logging và mức log phù hợp

Logging có cấu trúc giúp tìm kiếm theo `jobExecutionId`, `stepName` và `errorCode` dễ hơn so với ghép một chuỗi dài chứa dữ liệu. Nhưng **structured logging không tự làm dữ liệu an toàn**: nếu đưa `payment` vào một field JSON, nó vẫn bị lộ.

Một chính sách mức log thường gặp:

| Mức | Ví dụ sự kiện | Nội dung nên có |
|---|---|---|
| `INFO` | Job/step bắt đầu, hoàn tất, số lượng đọc/ghi | IDs, trạng thái, counters, thời lượng. |
| `WARN` | Item bị skip, retry gần giới hạn, một lỗi dữ liệu có thể xử lý | Mã lỗi, giai đoạn xử lý, vị trí an toàn, số lần. |
| `ERROR` | Step/job thất bại, lỗi hạ tầng không phục hồi | Metadata, mã lỗi, thông tin chẩn đoán đã kiểm soát. |
| `DEBUG` | Chi tiết luồng kiểm thử hoặc chẩn đoán có mục đích | Metadata bổ sung; **không tự động được phép log dữ liệu nhạy cảm**. |
| `TRACE` | Thông tin cực chi tiết | Hạn chế trong môi trường phù hợp; đặc biệt chú ý SQL bind/request body. |

**DEBUG không phải vùng miễn trừ quy tắc bảo vệ dữ liệu.** Có thể vô tình bật DEBUG trong production khi xử lý sự cố, nên mọi câu lệnh debug phải được viết an toàn ngay từ đầu. Không dựa vào giả định “mức log này không bao giờ bật”.

Một sự kiện tổng kết sau step thường hữu ích hơn nhiều dòng `INFO` cho từng item. Với lỗi có tần suất lớn, có thể dùng sampling hoặc tổng hợp theo mã lỗi, đồng thời duy trì số đếm chính xác ở metric/counter phù hợp. Nếu sampling, không được làm mất tín hiệu lỗi nghiêm trọng hoặc vi phạm chính sách vận hành.

## 15. Test để phát hiện log nhạy cảm

Trong kiểm thử, hãy dùng **dữ liệu giả lập nhưng trông giống dữ liệu nhạy cảm** để xác nhận logger không in ra ngoài dự kiến. Không dùng email, số tài khoản hoặc token thật trong fixture.

Một cách là capture output của logger trong test rồi kiểm tra không xuất hiện chuỗi cần bảo vệ. Với Spring Boot Test, có thể sử dụng `OutputCaptureExtension`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class SafeReadErrorListenerTest {

    @Test
    void doesNotLogRawInvalidLine(CapturedOutput output) {
        String marker = "canary-secret@example.test";
        String rawInput =
            "PAY-019," + marker + ",1234567890123456,INVALID";

        FlatFileParseException exception = new FlatFileParseException(
            "Bad record: " + rawInput,
            rawInput,
            17
        );

        new SafeReadErrorListener().onReadError(exception);

        assertThat(output.getAll())
            .contains("category=FILE_FORMAT")
            .contains("lineNumber=17")
            .doesNotContain(marker)
            .doesNotContain("1234567890123456")
            .doesNotContain(rawInput);
    }
}
~~~

Test này cố tình đặt cùng dữ liệu giả lập cả trong raw input **và trong exception message**. Nếu ai đó đổi listener sang `log.error("...", exception)` hoặc `log.warn("{}", exception.getInput())`, test có thể phát hiện dữ liệu đã lọt vào output.

Lưu ý: cơ chế capture phụ thuộc cấu hình logging và test runner; nếu logger gửi dữ liệu đến collector bên ngoài mà không qua stream được capture, cần kiểm tra tại đúng appender/sink. Mục tiêu là kiểm chứng **sự kiện log thực tế được tạo**, không chỉ kiểm tra code không chứa một phương thức nguy hiểm.

### Những tình huống cần đưa vào kiểm thử logging

| Tình huống | Dữ liệu giả lập | Kỳ vọng về log |
|---|---|---|
| Reader parse CSV lỗi | Dòng có email, tài khoản giả, giá trị kiểu sai | Log category + line number, không có raw input. |
| Processor validation lỗi | Item chứa tên, email, số tiền | Log mã lỗi, không có `item.toString()`. |
| Writer JDBC lỗi | Chunk chứa nhiều account giả | Log kích thước chunk và loại lỗi, không có danh sách item. |
| HTTP writer gặp 4xx/5xx | Request chứa Authorization giả | Log status code và endpoint alias, không có token/body. |
| Retry và skip | Item bị thử lại nhiều lần | Không phát tán payload theo mỗi callback; số liệu tổng kết vẫn hữu ích. |
| JobParameters có secret giả | `accessToken=TEST_ONLY_SECRET` | Không log nguyên map parameters, không lưu secret trong metadata thật. |
| Job restart | JobExecution ID mới cùng JobInstance | Log các ID đúng, không nhân bản dữ liệu gốc. |
| Multi-threaded step | Nhiều task liên tục trong một pool | MDC không lẫn ID giữa các execution, không chứa item. |
| Framework debug logger | Bật các logger có thể in bind/body trên môi trường test | Kiểm tra log output và cấu hình mức log trước khi triển khai. |

Với các hệ thống có yêu cầu nghiêm ngặt, có thể sử dụng bộ giá trị canary được thiết kế đặc biệt để rà soát cả log file, stdout và tracing sink trong integration test. Không tự động đưa dữ liệu nhạy cảm thật vào hệ thống kiểm thử hoặc dịch vụ phân tích log.

## 16. Quyền truy cập, retention và log pipeline

Giảm dữ liệu từ nguồn là biện pháp quan trọng nhất, nhưng chính sách vận hành vẫn cần xét **toàn bộ đường đi**:

~~~text
Spring Batch JVM
   |
   +--> stdout / local log file
   |       |
   |       v
   +--> log shipper / sidecar
           |
           v
       log collector
           |
           v
       search index / dashboard / alert / export
~~~

Nếu dữ liệu nhạy cảm đã bị ghi ra ở bước đầu, mọi điểm phía sau đều có khả năng trở thành nơi lưu bản sao. Vì vậy cần:

- **Phân quyền xem log theo vai trò:** không mặc định quyền xem log đồng nghĩa quyền xem toàn bộ dữ liệu khách hàng.
- **Retention và vòng đời xóa:** đặt thời hạn giữ log theo nhu cầu điều tra và quy định áp dụng; có cơ chế xóa/ẩn đối với dữ liệu không nên tồn tại lâu.
- **Bảo vệ dữ liệu khi truyền và lưu:** dùng các cơ chế an toàn của hạ tầng logging theo chính sách tổ chức.
- **Quản lý export và cảnh báo:** alert gửi qua chat/email thường nên chứa mã lỗi và liên kết tới dashboard, không gắn raw payload.
- **Giới hạn log người dùng nhập:** header, path, query string có thể chứa newline/control characters; chuẩn hóa để tránh log injection.
- **Kiểm soát lưu trữ dump/snapshot:** heap dump, crash report hoặc bản sao file test có thể chứa dữ liệu mà policy logging không cho phép xuất hiện.

Ngay cả khi masking đã được thực hiện, dữ liệu vẫn có thể liên kết lại bằng các nguồn khác. Cần đánh giá khả năng tái định danh và chỉ giữ trường thật sự phục vụ vận hành.

## 17. Khi cần điều tra chính xác bản ghi lỗi

Một yêu cầu thực tế là: “Tôi biết item nào bị skip để sửa dữ liệu, nhưng không muốn email hoặc tài khoản xuất hiện trong log.” Cách giải quyết tốt là **tách kênh quan sát khỏi kênh xử lý dữ liệu nhạy cảm**.

Ví dụ:

1. Reader phát hiện dòng số 17 có định dạng sai.
2. Listener log: `jobExecutionId=8102`, `stepName=importPaymentsStep`, `resourceAlias=daily-payments`, `lineNumber=17`, `errorCode=FILE_FORMAT`.
3. Một công cụ nội bộ có phân quyền cho phép người chịu trách nhiệm dữ liệu mở đúng nguồn ở vị trí tương ứng.
4. Người sửa dữ liệu thao tác trong hệ thống có audit và quyền riêng, không copy toàn bộ dòng lỗi vào chat hoặc log.
5. Khi chạy lại, monitor theo JobInstance/JobExecution và xác nhận số item đã xử lý/skip sau khi khắc phục.

Với input từ queue hoặc database không có khái niệm dòng, có thể dùng một **opaque record reference** hoặc ID sự kiện được cấp bởi nguồn nếu chính sách cho phép. Không dùng email/số điện thoại làm correlation ID. Không ghi `toString()` của key khi key đó chứa dữ liệu nghiệp vụ bí mật.

Nếu cần lưu các bản ghi reject để phân tích, hãy dùng **quarantine/dead-letter store** được thiết kế cho dữ liệu nhạy cảm, có kiểm soát quyền truy cập và retention rõ ràng. Log chỉ chứa mã tham chiếu tới bản ghi reject và lý do đã chuẩn hóa. Việc ghi quarantine có transaction/retry riêng cần được thiết kế để không phát sinh bản ghi trùng ngoài ý muốn.

## 18. Một số lỗi triển khai thường gặp

**“Tôi chỉ log ở DEBUG, production sẽ không thấy.”** DEBUG có thể được bật khi điều tra; code logging vẫn cần an toàn. Với library logging, cần xác định logger nào bật TRACE bind values hoặc request body.

**“Đã che email rồi nên log nguyên item được.”** Item còn có tên, tài khoản, địa chỉ, trường bí mật mới thêm và nhiều dữ liệu nghiệp vụ khác. Regex không hiểu hết cấu trúc object.

**“Tôi không log item, chỉ log exception.”** Parse exception, validation message hoặc HTTP client exception có thể chứa chính raw item. Cần kiểm soát exception message và cause chain trước khi log.

**“Dùng `@ToString.Exclude` là đủ.”** Có thể vẫn tồn tại serializer, custom logger, nested object, record khác hoặc lỗi tầng dưới in payload. `@ToString.Exclude` hữu ích như lớp phòng vệ, không thay cho allowlist.

**“Non-identifying JobParameter không bị lưu.”** Sai. Non-identifying chỉ thay đổi cách xác định JobInstance; nó vẫn có thể được ghi vào metadata `JobRepository`.

**“Log toàn bộ ExecutionContext giúp debug restart.”** ExecutionContext có thể chứa thông tin ứng dụng chưa được kiểm soát và có thể được serialize lưu bền vững. Hãy log state keys an toàn hoặc tiến độ được chuẩn hóa, không dump cả map.

**“Gắn hash cho email tức là đã ẩn danh.”** Hash không khóa của dữ liệu dễ đoán có thể bị dò; thậm chí token ổn định vẫn có thể tạo liên kết giữa nhiều hành vi. Chỉ dùng phương án tokenization/HMAC khi có yêu cầu rõ và cơ chế quản lý phù hợp.

**“Một stack trace đầy đủ luôn cần để xử lý sự cố.”** Nhiều lỗi có thể điều tra bằng `errorCode`, location, job IDs và metrics. Khi thật cần stack trace, phải kiểm soát kênh lưu và nội dung có nguy cơ chứa payload.

**“Không log dữ liệu nhạy cảm thì không thể tìm item lỗi.”** Có thể dùng line number, resource alias, opaque record reference và hệ thống truy cập dữ liệu riêng. Log giúp **định vị**, còn kho dữ liệu có phân quyền phục vụ **xem nội dung** khi cần.

## 19. Quy trình áp dụng cho một Spring Batch job

Đối với một job mới hoặc khi cải thiện job hiện có, có thể thực hiện theo các bước:

1. **Liệt kê dữ liệu nhạy cảm mà job đọc/xử lý/ghi.** Xem model, file, DB columns, API payload, headers và thông tin nằm trong exception.
2. **Định nghĩa các trường log an toàn.** Bắt đầu từ `jobName`, execution IDs, step IDs, status, counters, error code, correlation ID đã kiểm tra và vị trí dữ liệu nếu an toàn.
3. **Thay các câu dump object/chunk/exception** bằng sự kiện có cấu trúc dùng allowlist. Không ghi `toString()` của item, full JobParameters hoặc ExecutionContext.
4. **Bổ sung Step/Job listeners để log tổng kết.** Log read/write/skip/rollback counts và trạng thái cuối, giảm nhu cầu log từng item.
5. **Đánh giá lỗi parser, writer, HTTP client và JDBC.** Xác định liệu message/stack trace/debug logger có mang raw input hoặc bind values hay không.
6. **Thiết kế kênh xử lý lỗi dữ liệu riêng.** Dùng resource alias, line number hoặc token tham chiếu và kho quarantine có quyền phù hợp.
7. **Kiểm soát propagation của MDC/tracing.** Truyền những ID an toàn qua async/remote workers và dọn context của thread sau khi xong.
8. **Kiểm thử rò rỉ bằng canary trong dữ liệu giả lập.** Chạy đường thành công, parse failure, skip/retry, writer exception và restart; kiểm tra log sink thực tế.
9. **Quản lý log pipeline.** Phân quyền, retention, alert, export và bộ lọc bổ sung, đồng thời xem xét các thư viện bên thứ ba.

### Nguyên tắc ghi nhớ

> **Log sự kiện xử lý, không dump bản ghi xử lý.** Log ID và trạng thái đủ để tìm đúng execution; dữ liệu nhạy cảm nằm ở hệ thống nguồn/đầu ra có phân quyền.

Một log hữu ích thường trả lời được **khi nào**, **job nào**, **step nào**, **lỗi thuộc loại gì**, **có bao nhiêu item bị ảnh hưởng** và **cách tìm lại nguồn cần sửa**. Nó không cần sao chép email, số tài khoản, token hay cả dòng dữ liệu vào một hệ thống quan sát rộng rãi.

## Kết luận

Trong Spring Batch, thực hành **không log toàn bộ dữ liệu nhạy cảm** phải áp dụng xuyên suốt `ItemReader`, `ItemProcessor`, `ItemWriter`, listener, lỗi parse/skip/retry, `JobParameters`, `ExecutionContext`, các thư viện JDBC/HTTP và hạ tầng tập trung log. Giải pháp trọng tâm là **allowlist metadata an toàn**, mã lỗi chuẩn hóa, log tổng kết ở mức job/step và correlation IDs để truy vết mà không cần in payload.

Masking, redaction, mã hóa và phân quyền log đều có vai trò bổ trợ, nhưng cách giảm nguy cơ tốt nhất là **không để dữ liệu nhạy cảm đi vào logger ngay từ đầu**. Khi hệ thống tách rõ thông tin quan sát khỏi dữ liệu nghiệp vụ, đội vận hành vẫn có thể tìm lỗi, hỗ trợ restart và đánh giá sức khỏe batch mà không biến log thành một kho dữ liệu khách hàng thứ hai.
