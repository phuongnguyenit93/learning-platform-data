# Skip, retry và phân biệt lỗi dữ liệu với lỗi hệ thống

Một job Spring Batch nhập 500.000 dòng CSV có thể gặp vài dòng sai định dạng, deadlock cơ sở dữ liệu hoặc mất kết nối tới API đối tác. Ba sự cố ấy cần ba cách xử lý khác nhau: **skip** bản ghi xấu nếu hợp đồng cho phép, **retry** thao tác tạm thời thất bại nếu an toàn, và **fail** job khi hệ thống không thể đảm bảo kết quả đúng. Nếu bỏ qua lỗi hạ tầng như thể đó là dữ liệu xấu, job có thể báo hoàn tất dù phần lớn dữ liệu chưa được ghi.

Bài thuộc chương **Spring Batch** trong module **SPRING_BOOT_INTEGRATION**. Trong phạm vi tích hợp hệ thống Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration, bài tập trung vào quản lý cấu hình, hợp đồng dữ liệu, giao dịch, phân loại lỗi, xử lý trùng lặp, kiểm thử và quan sát luồng batch thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt lỗi dữ liệu cố định, lỗi hệ thống tạm thời, lỗi cấu hình và kết quả chưa xác định.
2. Mô tả ảnh hưởng của lỗi ở **ItemReader**, **ItemProcessor** và **ItemWriter** tới chunk, transaction, skip và retry.
3. Cấu hình Spring Batch 5.x với **faultTolerant**, **skipLimit**, **retryLimit**, skip listener và chính sách rollback.
4. Thiết kế quarantine, idempotency, checkpoint và restart để một job có thể phục hồi mà không làm mất hoặc tạo trùng dữ liệu.
5. Kiểm thử ngưỡng skip, retry cạn, deadlock, timeout sau side effect và phục hồi sau crash.
6. Đọc đúng các thống kê JobExecution/StepExecution để đánh giá chất lượng dữ liệu và độ tin cậy của quá trình nhập.

## 2. Nền tảng: chunk-oriented processing

Trong Spring Batch, một **Job** chứa một hay nhiều **Step**. Ở step xử lý theo chunk, framework đọc item từ **ItemReader**, chuyển đổi/kiểm tra bằng **ItemProcessor**, gom kết quả và gọi **ItemWriter**. Một transaction thường bao quanh việc xử lý một chunk, với những tài nguyên có thể tham gia vào transaction manager được khai báo.

~~~mermaid
flowchart TD
    J["Job / Step"] --> R["ItemReader.read()"]
    R -->|Có item| P["ItemProcessor.process()"]
    R -->|null: hết dữ liệu| FINISH["Hoàn tất step khi đủ điều kiện"]
    P -->|Trả item| B["Tích luỹ chunk"]
    P -->|Trả null| FILTER["Filter: không phải skip"]
    B --> W["ItemWriter.write(chunk)"]
    W --> TX["Commit transaction / lưu checkpoint"]
    TX --> R
    R -->|Exception| C["Phân loại lỗi"]
    P -->|Exception| C
    W -->|Exception| C
    C --> D{"Có thể tiếp tục an toàn?"}
    D -->|Retry có giới hạn| RETRY["Thử lại với backoff"]
    D -->|Skip trong ngưỡng| SKIP["Bỏ item + ghi nhận lỗi"]
    D -->|Không| FAIL["Step FAILED / Job FAILED"]
~~~

Sơ đồ thể hiện luồng quyết định ở mức khái niệm. Trong thực tế, lỗi writer có thể dẫn đến rollback và xử lý lại một phần chunk, còn cách reader tiếp tục phụ thuộc vào loại reader và trạng thái đã lưu. **Skip** và **retry** không hứa đảm bảo exactly-once.

### 2.1. Những thuật ngữ phải tách bạch

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Filter** | Processor trả **null** để cố ý loại item khỏi đầu ra; không phải lỗi | Bản ghi không thuộc khoảng thời gian cần đồng bộ |
| **Skip** | Bỏ qua item có lỗi được khai báo là chấp nhận được | Một dòng CSV sai định dạng ngày |
| **Retry** | Thử lại thao tác do lỗi có thể phục hồi | DB bị deadlock tạm thời |
| **Rollback** | Hoàn tác tác động của transaction chưa commit | Writer lỗi khi ghi một chunk |
| **Fail** | Dừng step/job vì không thể tiếp tục đúng hợp đồng | Schema sai, xác thực DB thất bại, quá giới hạn bản ghi xấu |
| **Quarantine** | Lưu dấu vết item lỗi ở nơi có thể điều tra/sửa và nhập lại | Bảng rejected_records với nguồn, vị trí, lý do |
| **Restart** | Chạy tiếp JobInstance đã thất bại dựa trên trạng thái lưu | Tiếp tục file từ checkpoint đã commit |

Lệnh **return null** trong ItemProcessor tăng **filterCount**, không tăng **processSkipCount**. Nếu cố tình trả null khi phát hiện dữ liệu lỗi để tránh chạm skip limit, hệ thống đã che giấu dữ liệu bị mất.

### 2.2. Những chỉ số quan trọng

**StepExecution** cung cấp các số như **readCount**, **writeCount**, **filterCount**, **readSkipCount**, **processSkipCount**, **writeSkipCount**, **commitCount** và **rollbackCount**. Chúng mô tả các giai đoạn xử lý khác nhau. Không dùng rollbackCount làm số lần retry: rollback có thể xuất phát từ nhiều nguyên nhân, còn item có thể được thực thi lại sau rollback.

## 3. Phân loại lỗi theo nguyên nhân và hợp đồng

| Nhóm lỗi | Tình huống | Chính sách khuyến nghị |
|---|---|---|
| **Lỗi dữ liệu riêng lẻ** | Sai ngày, thiếu trường bắt buộc, mã tiền tệ không hỗ trợ | Skip có giới hạn + quarantine **nếu nghiệp vụ cho phép** |
| **Duplicate đã xác minh** | External ID đã ghi với cùng nội dung và version | Idempotent no-op hoặc filter rõ ràng; cần lưu bằng chứng |
| **Lỗi tạm thời** | Deadlock, lock contention, throttling 429, 503 có thể phục hồi | Retry có giới hạn + backoff, nếu an toàn |
| **Lỗi kết nối/timeout** | Mất TCP, response timeout, DB connection reset | Xác minh side effect và độ an toàn trước retry |
| **Lỗi hợp đồng/cấu hình** | Sai credential, thiếu cột DB, file sai schema, quyền 403 | Fail-fast, sửa nguồn/cấu hình |
| **Bug lập trình** | NullPointerException, mapping sai, invariant bị phá | Fail và sửa code; không skip RuntimeException |
| **Lỗi dữ liệu diện rộng** | 70% số dòng có giá trị không parse được do nhà cung cấp đổi định dạng | Fail/giữ lô để kiểm duyệt khi vượt ngưỡng |
| **Kết quả không xác định** | HTTP POST đã được xử lý nhưng phản hồi mất | Đối soát theo request ID/idempotency key trước khi phát lại |

**Tên exception chưa đủ để ra quyết định.** Ví dụ **DataIntegrityViolationException** có thể là duplicate ID có thể xử lý idempotent, nhưng cũng có thể do foreign key sai, schema chưa migration hoặc dữ liệu không hợp lệ. Adapter nên chuyển nguyên nhân đã hiểu thành exception nghiệp vụ cụ thể; không nên skip toàn bộ họ exception của DB.

### 3.1. Cây quyết định

~~~mermaid
flowchart TD
    E["Exception ở read/process/write"] --> Q{"Lỗi của một item đã xác định?"}
    Q -->|Có| S{"Hợp đồng cho skip?"}
    S -->|Có| SL{"Còn skip budget?"}
    SL -->|Có| SK["Skip + quarantine"]
    SL -->|Không| F["Fail"]
    S -->|Không| F
    Q -->|Không / chưa rõ| T{"Lỗi tạm thời?"}
    T -->|Không| F
    T -->|Có| I{"Retry có an toàn/idempotent?"}
    I -->|Không rõ| REC["Đối soát hoặc dừng an toàn"]
    I -->|Có| L{"Còn retry budget?"}
    L -->|Có| RT["Backoff + retry"]
    L -->|Không| F
~~~

Phân loại phải trả lời đủ bốn câu hỏi: lỗi thuộc **item** hay **môi trường**, bản ghi có được phép bỏ khỏi kết quả không, thao tác đã có side effect chưa, và lỗi có thể tự hết mà không cần sửa dữ liệu/cấu hình không.

## 4. Skip: loại bỏ dữ liệu xấu có kiểm soát

Với Spring Batch 5.x, fault-tolerant chunk step có thể khai báo loại exception được skip và tổng số item skip tối đa.

~~~java
// Một phần chuỗi cấu hình FaultTolerantStepBuilder.
.faultTolerant()
.skip(InvalidImportRowException.class)
.skipLimit(50)
~~~

**skipLimit(50)** giới hạn tổng số skip của step trên các giai đoạn **read**, **process** và **write**. Đây không phải 50 lần riêng cho mỗi giai đoạn. Khi phát sinh item thứ 51 cần skip, step sẽ fail theo chính sách đã cấu hình.

### 4.1. Skip tại Reader, Processor, Writer

| Vị trí | Lỗi ví dụ | Điều cần chú ý |
|---|---|---|
| **ItemReader** | FlatFileItemReader không parse được một dòng | Có thể lấy line number từ FlatFileParseException; reader cần tiến qua dòng lỗi, không kẹt vô hạn |
| **ItemProcessor** | Dữ liệu không đạt validation | Có item đầu vào để quarantine; ném exception được skip, thay vì trả null |
| **ItemWriter** | Một item cụ thể vi phạm ràng buộc dữ liệu | Writer theo batch có thể khó định danh item gây lỗi; rollback và thử lại có thể tốn chi phí |

**Sai lầm nguy hiểm:**

~~~java
// Không dùng cho job dữ liệu quan trọng.
.faultTolerant()
.skip(RuntimeException.class)
.skipLimit(Integer.MAX_VALUE)
~~~

Cách này có thể che giấu lỗi kết nối, bug, schema sai và khiến job đạt COMPLETED dù dữ liệu đích thiếu nghiêm trọng. Nên định nghĩa exception riêng cho bản ghi lỗi, tách biệt khỏi lỗi hệ thống.

### 4.2. Filter khác skip

~~~java
// Filter có chủ đích: bản ghi không thuộc phạm vi.
if (!row.inRequestedPeriod()) {
    return null;
}

// Lỗi dữ liệu: cần tính vào số lượng skip và lưu quarantine.
if (row.externalId() == null || row.externalId().isBlank()) {
    throw new InvalidImportRowException("Thiếu externalId");
}
~~~

Với job tài chính, ngay cả dữ liệu sai cũng có thể **không được phép skip**: hợp đồng yêu cầu chặn file và yêu cầu đối tác gửi lại. Vì vậy skip là quyết định nghiệp vụ trước khi là cấu hình kỹ thuật.

### 4.3. Khi nào phải chặn cả file?

Nếu header, encoding, ký tự phân cách hoặc version schema của file sai, mọi dòng phía sau có thể bị hiểu sai. Thực hiện preflight header/schema, checksum, nguồn/version trước khi đọc vào step chính để phát hiện lỗi hợp đồng toàn lô, thay vì để skip hàng chục nghìn dòng rồi mới dừng.

## 5. Retry: thử lại lỗi tạm thời, không lặp vô hạn

~~~java
// Phần cấu hình fault-tolerant step cho lỗi DB tạm thời.
.faultTolerant()
.retry(org.springframework.dao.TransientDataAccessException.class)
.retryLimit(3)
~~~

**retryLimit(3)** đặt giới hạn lần thử (tính cả lần thực hiện ban đầu) theo cơ chế retry. Chỉ nên retry khi có cơ sở lỗi có thể phục hồi, thao tác có thể lặp an toàn và còn ngân sách thời gian.

Ví dụ deadlock trong transaction DB thông thường có thể thành công khi retry. Nhưng retry một lệnh **POST /payments** bị timeout có thể tạo thanh toán trùng nếu server đã thực hiện thao tác trước khi phản hồi bị mất.

### 5.1. Backoff và giới hạn chung

Thay vì retry ngay, dùng exponential backoff có giới hạn, có thể thêm jitter để nhiều worker không cùng retry một thời điểm:

~~~text
Lần 1: thực thi ban đầu
Lỗi tạm thời -> đợi khoảng 200 ms (+/- jitter)
Lần 2: thử lại
Lỗi tạm thời -> đợi khoảng 400 ms (+/- jitter)
Lần 3: thử lại
Vẫn lỗi -> dừng retry theo chính sách
~~~

Các con số chỉ minh hoạ, không phải mặc định của Spring Batch. Nếu có HTTP **429 Retry-After**, cần tôn trọng hạn mức đối tác. Không cấu hình client HTTP, service và batch step cùng retry nhiều tầng mà không giới hạn tổng số lần hoặc deadline.

### 5.2. Retry cạn thì xử lý ra sao?

- Nếu lỗi DB/network tạm thời ảnh hưởng cả chunk: **fail step** hoặc chờ điều phối vận hành, không skip các item đã không ghi được.
- Nếu lỗi là dữ liệu riêng lẻ và hợp đồng cho phép: dùng skip policy tường minh với giới hạn và quarantine.
- Nếu kết quả của side effect chưa rõ: lưu trạng thái **PENDING_RECONCILIATION** và tra cứu theo business key trước khi phát lại.

Retry chỉ giải quyết thời điểm thực thi. Một exception xác định do dữ liệu sai ngày sẽ không đúng lên sau ba lần gọi processor.

## 6. Ví dụ Spring Boot 3.x / Spring Batch 5.x

Giả sử ứng dụng đã có **ItemReader<ImportRow>** đọc CSV, **ItemWriter<ImportEntity>** ghi DB theo externalId một cách idempotent, cùng JobRepository và PlatformTransactionManager. Cấu hình sau mô tả chính sách nhập tối đa 50 bản ghi dữ liệu xấu, retry lỗi DB tạm thời 3 lần và fail nếu không thể ghi dữ liệu hợp lệ.

~~~java
import java.math.BigDecimal;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

record ImportRow(String externalId, String currency, BigDecimal amount) {}
record ImportEntity(String externalId, String currency, BigDecimal amount) {}

class InvalidImportRowException extends RuntimeException {
    InvalidImportRowException(String message) { super(message); }
}

@Configuration
class ImportBatchConfig {
    @Bean
    ItemProcessor<ImportRow, ImportEntity> importProcessor() {
        return row -> {
            if (row.externalId() == null || row.externalId().isBlank()) {
                throw new InvalidImportRowException("Thiếu externalId");
            }
            if (row.amount() == null || row.amount().signum() <= 0) {
                throw new InvalidImportRowException(
                        "Số tiền không hợp lệ: " + row.externalId());
            }
            return new ImportEntity(
                    row.externalId(), row.currency(), row.amount());
        };
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<ImportRow> importReader,
            ItemProcessor<ImportRow, ImportEntity> importProcessor,
            ItemWriter<ImportEntity> importWriter,
            SkipListener<ImportRow, ImportEntity> importSkipListener) {

        return new StepBuilder("importStep", jobRepository)
                .<ImportRow, ImportEntity>chunk(100, transactionManager)
                .reader(importReader)
                .processor(importProcessor)
                .writer(importWriter)
                .faultTolerant()
                .skip(InvalidImportRowException.class)
                .skip(org.springframework.batch.item.file.FlatFileParseException.class)
                .skipLimit(50)
                .retry(TransientDataAccessException.class)
                .retryLimit(3)
                .listener(importSkipListener)
                .build();
    }

    @Bean
    Job importJob(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("importJob", jobRepository)
                .start(importStep)
                .build();
    }
}
~~~

Đây là **khung cấu hình**; ứng dụng phải cung cấp reader, writer, listener, datasource và cách launch job. Writer cần có unique constraint/version check, nếu không retry/restart có thể ghi lặp. Quy tắc số tiền dương ở ví dụ cần thay bằng hợp đồng thực tế; trong nghiệp vụ hoàn tiền, số âm có thể là giá trị hợp lệ.

### 6.1. Quan sát skip qua listener

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SkipAuditConfig {
    private static final Logger log =
            LoggerFactory.getLogger(SkipAuditConfig.class);

    @Bean
    SkipListener<ImportRow, ImportEntity> importSkipListener() {
        return new SkipListener<>() {
            @Override
            public void onSkipInRead(Throwable failure) {
                log.warn("skip phase=read reason={}",
                        failure.getClass().getSimpleName());
            }

            @Override
            public void onSkipInProcess(ImportRow item, Throwable failure) {
                log.warn("skip phase=process id={} reason={}",
                        item.externalId(), failure.getClass().getSimpleName());
            }

            @Override
            public void onSkipInWrite(ImportEntity item, Throwable failure) {
                log.warn("skip phase=write id={} reason={}",
                        item.externalId(), failure.getClass().getSimpleName());
            }
        };
    }
}
~~~

Listener trên chỉ ghi audit tối thiểu, **không lưu quarantine bền vững**. Trong production, cần lưu nhận diện bản ghi, vị trí file/cursor, loại lỗi, version nguồn, ID lần chạy và tham chiếu tới dữ liệu gốc ở kho có quyền truy cập phù hợp. Nếu listener ghi DB khác transaction hoặc gọi HTTP, rollback/restart có thể làm sai lệch nhật ký lỗi; cần thiết kế transaction hoặc outbox phù hợp.

### 6.2. Dùng noSkip và noRetry đúng chỗ

Khi có exception class cha rộng, DSL cho phép loại trừ loại không được skip hoặc retry:

~~~java
// Ví dụ mảnh DSL, chỉ áp dụng trong chuỗi faultTolerant().
.skip(SomeBroadInputException.class)
.noSkip(InvalidFileSchemaException.class)
.retry(org.springframework.dao.TransientDataAccessException.class)
.noRetry(InvalidImportRowException.class)
~~~

Không tạo **SomeBroadInputException** và **InvalidFileSchemaException** bằng cách đoán tên framework; đây là **các exception nghiệp vụ tự định nghĩa** khi triển khai. Tốt hơn là cấu hình trực tiếp các nhóm exception cụ thể và test các nhánh phân loại. Khi cùng một exception vừa được retry vừa được skip, hành vi phụ thuộc cấu hình; phải kiểm tra theo test thay vì kỳ vọng “thử mãi rồi tự skip”.


## 7. Rollback và việc thực thi lại chunk

Lỗi trong writer thường khiến transaction hiện tại rollback. Spring Batch có thể thử lại hoặc xử lý từng item để xác định item lỗi theo chính sách skip; vì vậy **một item có thể được đọc, xử lý hoặc gửi tới writer nhiều lần** trong vòng đời job.

~~~mermaid
sequenceDiagram
    participant R as Reader
    participant P as Processor
    participant W as DB Writer
    participant T as Transaction Manager
    R->>P: Item A, B, C
    P->>W: Chunk [A, B, C]
    W->>T: Ghi thay đổi trong transaction
    T--xW: Deadlock -> rollback
    Note over R,W: Framework có thể thực thi lại một phần chunk
    W->>T: Retry sau rollback (nếu được phép)
    T-->>W: Commit / hoặc lỗi khi hết retry
~~~

**Transaction chỉ rollback được tài nguyên cùng tham gia giao dịch đó.** Nếu ItemProcessor đã gọi API HTTP để tạo đơn hoặc ItemWriter đã publish một message ra broker trước khi DB transaction rollback, side effect bên ngoài có thể đã xảy ra và không được tự động hoàn tác.

Vì thế:

- Không đặt side effect khó đảo ngược trong processor nếu không có idempotency và quy trình đối soát.
- Đặt thao tác ghi DB có thể rollback trong transaction của writer.
- Khi cần phát sự kiện sau commit DB, cân nhắc **transactional outbox**: commit dữ liệu nghiệp vụ và sự kiện cần phát trong cùng DB transaction, sau đó worker gửi event có chống lặp.
- Chỉ dùng cấu hình **noRollback** khi hiểu rõ vòng đời reader/writer, và có chứng cứ rằng việc tiếp tục không làm trạng thái sai.
- Phân biệt rollback do lỗi nghiệp vụ với rollback từ deadlock, writer và lỗi lúc commit. Đừng giả định mọi rollback đều là một retry.

### 7.1. Timeout sau side effect: tình huống đặc biệt nguy hiểm

~~~mermaid
sequenceDiagram
    participant B as Batch Writer
    participant A as External API
    participant D as External Database
    B->>A: POST create-payment (requestId=R17)
    A->>D: Commit payment R17
    D-->>A: Commit OK
    A--xB: Response lost / client timeout
    Note over B: Kết quả từ góc nhìn client là UNKNOWN
    B->>A: GET payment by requestId=R17
    A-->>B: Payment already exists
    Note over B: Xác nhận trạng thái rồi hoàn tất, không tạo lần hai
~~~

Một **SocketTimeoutException** không chứng minh API chưa nhận request. Nếu retry vô điều kiện, doanh thu hoặc thanh toán có thể được ghi hai lần. Cách giải quyết là dùng **idempotency key cố định**, tra cứu kết quả theo request ID, hoặc lưu trạng thái cần đối soát thay vì khẳng định thất bại hay thành công quá sớm.

## 8. Xử lý trùng lặp xuyên retry, rollback và restart

Cơ chế fault tolerance trong Spring Batch thường hướng đến xử lý được dữ liệu sau lỗi, nên **duplicate execution** là tình huống phải dự đoán.

Ví dụ transaction ghi DB đích commit xong, nhưng ứng dụng mất kết nối trước khi nhận xác nhận. Sau restart, item đó có thể được gửi lại. Nếu writer chỉ dùng INSERT không có business key, có thể tạo bản ghi trùng.

Một hợp đồng idempotency thường gồm:

1. **Định danh ổn định:** externalId kết hợp sourceSystem/tenant hoặc event ID, không sinh UUID mới mỗi lần retry.
2. **Ràng buộc ở đích:** unique constraint theo business key, không chỉ kiểm tra EXISTS bên phía ứng dụng rồi mới ghi (có race condition).
3. **Quy tắc duplicate:** cùng key và cùng nội dung/version có thể no-op; cùng key nhưng payload mâu thuẫn phải báo conflict.
4. **Quy tắc thứ tự:** chỉ cho phép cập nhật lên version mới hơn; không dùng việc “gói tin đến sau” làm bằng chứng dữ liệu mới hơn.
5. **Cơ chế đối soát:** với thao tác bên ngoài DB transaction, phải có cách truy vấn tác động đã commit trước khi retry.

### 8.1. Nhận diện duplicate khác với skip

Một bản ghi đã được ghi trong lần chạy trước không nhất thiết là “dữ liệu xấu”. Nếu hiện thực writer idempotent, việc nhận lại cùng external ID có thể được ghi nhận **duplicate_noop** với metric riêng. Nếu mọi duplicate đều bị ném thành lỗi skippable, số skip tăng giả và có thể làm step thất bại khi restart dù nghiệp vụ đã được xử lý đúng.

Khi cần phân biệt bằng số liệu, nên bổ sung counter riêng cho **duplicate** hoặc cập nhật trạng thái ở tầng staging; không suy luận duplicate từ readSkipCount.

### 8.2. Spring Batch không cung cấp exactly-once xuyên HTTP và broker

Một JobRepository có thể ghi checkpoint cho Step; một DB transaction có thể đảm bảo atomicity trong database đó. Nhưng transaction này không tự kết hợp với webhook, Kafka, RabbitMQ, Redis hay HTTP service đích thành một giao dịch nguyên tử toàn cục.

Dùng transactional outbox/inbox, consumer idempotent và đối soát business key khi thông điệp được phát lại. Các mức bảo đảm **at-most-once**, **at-least-once** và **effectively-once** cần được mô tả ở hợp đồng tích hợp, không suy ra chỉ từ **retryLimit**.

## 9. Quarantine và giới hạn chất lượng dữ liệu

Nếu một item được skip vì dữ liệu xấu, chỉ ghi log “skip success” là không đủ cho khả năng truy vết. Cần một nơi lưu bản ghi bị từ chối, lý do và trạng thái phục hồi.

| Trường quarantine | Ví dụ | Mục đích |
|---|---|---|
| source_system / source_file | đối tác A / file_20261121.csv | Truy nguồn |
| source_checksum / source_version | checksum, schema version | Chứng minh đầu vào chưa bị thay đổi |
| job_execution_id / step | 18321 / importStep | Ghép với Spring Batch metadata |
| record_locator | line 1483 / externalId=PAY-1473 | Xác định bản ghi |
| failure_phase / code | process / INVALID_CURRENCY | Phân loại, sửa dữ liệu |
| safe_payload_reference | object-storage key hạn chế quyền | Nhập lại mà không lộ dữ liệu nhạy cảm |
| status / retry_history | NEW, FIXED, REPROCESSED | Điều phối khắc phục |

Cần có yêu cầu riêng cho dữ liệu nhạy cảm. Không đưa số thẻ, token, secret, mật khẩu hoặc dữ liệu cá nhân thô vào log; sử dụng mã lỗi và tham chiếu được bảo vệ.

### 9.1. Skip limit chưa đủ khi kích thước lô thay đổi

**skipLimit(50)** tương ứng 50% nếu lô chỉ 100 dòng, nhưng là 0,005% nếu lô một triệu dòng. Chính sách nghiệp vụ có thể cần cả **ngưỡng tuyệt đối**, **tỷ lệ lỗi**, **loại lỗi bắt buộc fail** và **phạm vi đánh giá** (theo file, tenant, step hay job).

Một **SkipPolicy** tuỳ chỉnh có thể phân loại exception và số lượng skip:

~~~java
import org.springframework.batch.core.step.skip.SkipPolicy;

SkipPolicy policy = (failure, skipCount) -> {
    boolean dataError =
            failure instanceof InvalidImportRowException
            || failure instanceof org.springframework.batch.item.file.FlatFileParseException;

    // skipCount là số lần đã skip trước item đang được xem xét.
    return dataError && skipCount < 50;
};

// Đăng ký với FaultTolerantStepBuilder thông qua skipPolicy(policy).
~~~

Nếu cần giới hạn theo tỷ lệ, phải định nghĩa mẫu số (dòng nguồn, số record hợp lệ, hay tổng đầu vào) và thời điểm kiểm tra. Không nên chỉ lấy readCount chia ngẫu nhiên trong khi chunk có thể rollback. Với file sai schema, nên fail từ preflight thay vì đợi vượt ngưỡng skip.

### 9.2. Quarantine phải chịu được rollback

**SkipListener** được thiết kế để ghi nhận item thực sự bị skip, nhưng việc callback gửi HTTP hoặc ghi sang DB khác có thể thoát khỏi transaction và tạo trạng thái lệch. Nếu lưu quarantine vào cùng DB, cần xác định transaction manager và unique key cho lỗi. Nếu gửi ra broker, dùng outbox hoặc phát sau commit với dedupe.

Một bản ghi lỗi được sửa và nhập lại sau đó phải có **link tới lần skip trước**, tránh tính cùng một lỗi thành nhiều trường hợp chưa giải quyết.

## 10. Checkpoint, ExecutionContext và restart

Spring Batch lưu metadata qua **JobRepository**, trong đó **JobExecution** và **StepExecution** phản ánh trạng thái mỗi lần chạy. **ExecutionContext** cho phép những reader/writer thực hiện **ItemStream** lưu trạng thái cần thiết để khởi động lại.

### 10.1. Restart khác retry và rerun

| Cơ chế | Thời điểm | Điểm cần bảo đảm |
|---|---|---|
| Retry | Trong một StepExecution hiện tại | Thao tác có thể lặp, giới hạn attempts và backoff |
| Restart | JobInstance đã FAILED/STOPPED được thực thi tiếp | Metadata/checkpoint chính xác, nguồn dữ liệu ổn định |
| Rerun mới | JobParameters nhận diện mới tạo JobInstance mới | Có thể xử lý lại từ đầu, cần idempotency toàn nguồn |

**JobInstance** được định danh bởi tên job và bộ **identifying JobParameters**. Nếu mỗi lần chạy lại gắn một tham số nhận diện timestamp mới, đó thường là JobInstance khác và có thể đọc lại toàn bộ file. Không coi rerun là restart tự động an toàn.

### 10.2. Các bẫy checkpoint

- File bị thay nội dung nhưng vẫn dùng checkpoint theo dòng/byte cũ: có nguy cơ bỏ sót hoặc đọc sai.
- Reader tuỳ chỉnh không triển khai đúng lifecycle **open/update/close** của ItemStream: restart có thể bắt đầu sai vị trí.
- Reader gọi nguồn ngoài có cursor riêng, không nằm trong transaction DB: rollback không tự tua cursor.
- Batch đã ghi dữ liệu đích nhưng commit/checkpoint nhận được phản hồi không rõ: restart có thể gửi lại item.
- Step dùng queue hoặc async processing: checkpoint reader không đảm bảo các side effect bất đồng bộ đã hoàn tất.

**Runbook restart** nên kiểm tra JobExecution/StepExecution, số skip, nguồn còn nguyên theo checksum/schema, side effect chưa rõ và writer idempotent. Chỉ restart instance khi kết quả có thể được đối soát. Không sửa metadata JobRepository thủ công khi chưa kiểm tra quy trình recovery của phiên bản Spring Batch đang dùng.

## 11. Tích hợp HTTP, database và broker trong job batch

| Ranh giới | Lỗi thường gặp | Hành vi cần thiết |
|---|---|---|
| HTTP API đọc trang dữ liệu | 429, 5xx, cursor hết hạn | Retry có giới hạn, tôn trọng Retry-After, cursor/checkpoint ổn định |
| HTTP API ghi dữ liệu | Timeout sau khi server đã commit | Request ID, idempotency key và đối soát trước khi phát lại |
| DB reader | Deadlock, dữ liệu bị thay khi đang đọc | Isolation/cursor thích hợp, snapshot nếu cần |
| DB writer | Unique violation, lock timeout, connection reset | Phân loại duplicate, retry transient, tra cứu khi commit không rõ |
| Broker consumer | Message redelivery khi reconnect/rollback | ACK đúng thời điểm, idempotent handler và DLQ |
| Broker producer | Publish thành công nhưng phản hồi ACK mất | Outbox, dedupe/correlation ID |
| File/SFTP | File chưa ghi xong, bản sao trùng tên, input thay đổi | Quy ước file-ready, checksum, fingerprint và quản lý phiên bản |

### 11.1. Mẫu nhập bền vững trước khi phát ra ngoài

~~~mermaid
flowchart LR
    SRC["CSV / API / message source"] --> VALID["Parse + validate"]
    VALID -->|Lỗi item cho phép skip| Q[("Quarantine")]
    VALID -->|Hợp lệ| TX[("Staging DB + inbox/outbox transaction")]
    TX --> W["Worker idempotent"]
    W --> DEST["HTTP / broker / downstream"]
    DEST --> ACK["ACK hoặc đối soát"]
~~~

Step nhập dữ liệu có thể commit vào DB staging và outbox; worker khác thực thi side effect ngoài transaction, có retry và idempotency độc lập. Cấu trúc này làm rõ điểm được xem là “đã tiếp nhận” và điểm được xem là “đã xử lý nghiệp vụ”. Với sự kiện không được phép mất, outbox và retention cần được kiểm tra trong thử nghiệm crash.

## 12. Khi job có nhiều partition hoặc worker

Với multi-threaded step, partitioning hoặc remote chunking, mỗi worker/partition có thể có **StepExecution riêng**. Nếu cấu hình skipLimit(50) trên mỗi partition, tổng số item skip ở toàn job có thể lớn hơn 50. Cần một ngưỡng **toàn file/toàn job** nếu hợp đồng yêu cầu, và tổng hợp trạng thái trước khi publish kết quả cuối.

Cần chuẩn bị:

1. Partition key/range không chồng, hoặc atomic claim để tránh hai worker nhận một item.
2. Writer có unique constraint/idempotency khi partition retry/restart.
3. Giới hạn tổng connection pool, HTTP concurrency và retry của mọi worker.
4. Tổng hợp số skip, quarantine, duplicate và lỗi cho toàn job.
5. Nếu có yêu cầu ordering, phân vùng theo business key hoặc kiểm tra version thay vì mặc nhiên tin thứ tự thread.
6. Quy trình xử lý khi một partition fail sau khi các partition khác đã commit.

Việc tăng concurrency khi DB đang gặp lỗi tạm thời có thể khiến retry storm mạnh hơn. Đừng tăng worker như một cách che lỗi tài nguyên.

## 13. Quan sát vận hành

Để xác nhận một job chạy đúng, cần đo **tiến độ**, **chất lượng dữ liệu**, **độ bền** và **tác động nghiệp vụ**, không chỉ nhìn trạng thái COMPLETED.

| Nhóm | Metric / trạng thái | Tác dụng |
|---|---|---|
| Tiến độ | readCount, writeCount, commitCount, current cursor, throughput | Phát hiện job đứng, tiến độ chậm |
| Chất lượng | filterCount, readSkipCount, processSkipCount, writeSkipCount, quarantine count | Chứng minh dữ liệu bị loại theo đúng chính sách |
| Chịu lỗi | Retry attempts theo loại lỗi, rollbackCount, backoff duration | Nhận ra hệ thống đang quá tải hoặc lặp lỗi |
| Nhất quán | duplicate count, conflict, pending reconciliation | Xác định rủi ro mất/ghi trùng |
| Tài nguyên | DB pool, HTTP 429/503, CPU, memory, broker lag | Phát hiện retry hoặc batch đang gây sự cố dây chuyền |
| Vận hành | jobInstance, jobExecution, stepExecution, source checksum, schema version | Hỗ trợ restart và audit |

Có thể dùng **Micrometer/Actuator** cho metric, **JobRepository/JobExplorer** để xem lần chạy và **StepExecution** để đọc số đếm. Nhãn metric nên là tên job, step và loại exception đã chuẩn hoá; không gắn mỗi externalId làm metric label vì cardinality cao. Log phải có correlation ID và che thông tin nhạy cảm.

Cảnh báo nên tập trung vào **tỷ lệ skip vượt ngưỡng**, job kéo dài vượt SLA, quá nhiều retry, không có tiến độ, quarantine tồn lâu, hoặc pending reconciliation tăng. Một job COMPLETED vẫn có thể cần trạng thái “chưa được duyệt để publish” khi dữ liệu lỗi vượt yêu cầu kinh doanh.

## 14. Kiểm thử fault tolerance

| Kịch bản | Cách mô phỏng | Kết quả cần assert |
|---|---|---|
| Dòng CSV parse lỗi | Sai format ngày | Tăng readSkipCount, có dấu vết lỗi, tiếp tục trong ngưỡng |
| Processor validation lỗi | Thiếu externalId | Tăng processSkipCount, quarantine đúng record |
| Filter hợp lệ | Record ngoài phạm vi | Tăng filterCount; không tăng skip |
| Đúng skip limit | 50 record lỗi được skip | Step có thể COMPLETED nếu không có lỗi khác |
| Vượt skip limit | 51 record lỗi | Step FAILED, có bằng chứng dữ liệu chưa nhập |
| Deadlock tạm thời | Writer lỗi transient một lần rồi thành công | Retry đúng giới hạn, commit một tác động nghiệp vụ |
| Hỏng DB kéo dài | Writer luôn lỗi kết nối | Hết retry thì FAIL; không skip toàn chunk |
| Schema sai | Thiếu cột DB hoặc header file đổi | Fail-fast, không chạy retry vô nghĩa |
| Timeout sau side effect | API commit rồi response bị cắt | Dedupe/đối soát giữ đúng một tác động |
| Crash trước chunk commit | Kill app giữa chunk | Resume và xử lý item chưa commit |
| Crash sau commit nhưng trước checkpoint | Simulate trạng thái không rõ ràng | Không tạo dữ liệu trùng vì idempotency |
| Nhiều partition | Chạy nhiều worker trên cùng nguồn | Không giao chồng, tổng skip theo đúng phạm vi |

### 14.1. Thiết kế assertion theo hợp đồng

~~~text
A. [valid, invalid, valid]
   -> 2 bản ghi đích, 1 record quarantine,
      processSkipCount = 1, Step COMPLETED nếu hợp đồng cho skip.

B. [valid] + DB deadlock một lần
   -> có retry, chỉ 1 bản ghi đích, không duplicate.

C. [valid] + DB luôn mất kết nối
   -> Step FAILED, không chuyển lỗi hệ thống thành skip.

D. API đã tạo giao dịch nhưng response bị mất
   -> retry/restart sử dụng request ID để đối soát;
      hệ thống đích có đúng 1 giao dịch.

E. Quá ngưỡng chất lượng lô
   -> job không được tự động publish kết quả như đã hoàn tất.
~~~

Đối với transaction, deadlock, unique constraint và restart, integration test nên chạy với database thực hoặc môi trường có hành vi transaction tương thích. Mock không chứng minh được rollback hay commit không rõ kết quả. Đo cả số lần writer thực thi và số **side effect thực sự tồn tại** ở đích; chúng có thể khác nhau.

## 15. Tình huống tổng hợp: nhập giao dịch đối soát cuối ngày

Một ứng dụng Spring Boot đọc file doanh thu 200.000 dòng từ đối tác. Một số dòng sai ngày; database đích có thể deadlock lúc cao điểm; một số file được đối tác gửi lại sau khi sửa dữ liệu.

**Hợp đồng:**

- Lỗi parser ở bản ghi riêng lẻ được quarantine và skip tối đa 100 item, với ngưỡng tỷ lệ lỗi bổ sung theo file.
- Sai header/schema là lỗi cả file, job phải fail trước khi ghi dữ liệu.
- Deadlock được retry hữu hạn; nếu DB vẫn lỗi, job FAILED để có thể restart.
- External ID cùng version và payload là duplicate idempotent; external ID cùng version nhưng dữ liệu mâu thuẫn được đưa vào luồng điều tra.
- Bất cứ thao tác nào không rõ đã commit phải được tra cứu theo business key trước khi thực thi lại.

~~~mermaid
flowchart TD
    FILE["CSV source có version/checksum"] --> PREF["Preflight header/schema"]
    PREF -->|Sai hợp đồng| FAIL["Fail job"]
    PREF -->|Đúng| READ["FlatFileItemReader + checkpoint"]
    READ --> PROC["Validate + normalize"]
    PROC -->|Lỗi item được skip| Q[("Quarantine")]
    PROC -->|Hợp lệ| W["DB writer idempotent"]
    W -->|Transient lỗi| RET["Retry có giới hạn"]
    RET --> W
    W -->|Commit thành công| DB[("Business DB + unique/version key")]
    W -->|Lỗi hệ thống kéo dài| FAIL
    DB --> REPORT["Đối soát tổng nguồn/đích"]
    Q --> REPORT
~~~

Báo cáo cuối job phải trả lời: bao nhiêu dòng nguồn, bao nhiêu item đọc hợp lệ, bao nhiêu được filter, bao nhiêu bị skip có lý do, bao nhiêu duplicate no-op, bao nhiêu bản ghi đã commit, còn bao nhiêu cần đối soát. Không dùng **COMPLETED** đơn lẻ làm bằng chứng rằng tất cả bản ghi nghiệp vụ đã được tiếp nhận.

## 16. Checklist trước khi triển khai

- [ ] Lỗi dữ liệu, lỗi hạ tầng, lỗi cấu hình và kết quả không xác định đã được phân loại bằng hợp đồng rõ ràng.
- [ ] Dữ liệu cần giữ đủ không bị skip chỉ vì Retry thất bại.
- [ ] Không có skip(RuntimeException.class) hoặc skip(Exception.class) với giới hạn vô hạn.
- [ ] Skip limit, tỷ lệ lỗi, phạm vi step/partition/job và hành vi khi vượt ngưỡng đã được thống nhất.
- [ ] Filter bằng return null chỉ dùng cho bản ghi hợp lệ ngoài phạm vi.
- [ ] Retry có giới hạn, backoff, timeout và tính idempotent/đối soát của các side effect.
- [ ] Writer dùng business key, unique constraint và version check khi cần.
- [ ] Reader/checkpoint có thể restart trên nguồn dữ liệu cố định; execution metadata được giữ đúng.
- [ ] HTTP/broker side effect có outbox hoặc cách xử lý trùng thích hợp.
- [ ] SkipListener/quarantine lưu đủ bằng chứng với chính sách bảo vệ dữ liệu nhạy cảm.
- [ ] Có test vượt skip limit, retry cạn, rollback, timeout không rõ kết quả và restart.
- [ ] Có metric, cảnh báo chất lượng lô, runbook khôi phục và bước đối soát trước khi công bố kết quả.

**Nguyên tắc cốt lõi:** **skip** là quyết định nghiệp vụ cho phép loại một item khỏi kết quả, **retry** là quyết định kỹ thuật thử lại điều kiện có khả năng phục hồi, còn **fail** bảo vệ tính đúng khi không thể tiếp tục an toàn. Độ tin cậy của Spring Batch trong tích hợp hệ thống đến từ phân loại lỗi chính xác, giao dịch phù hợp, idempotency và bằng chứng đối soát, chứ không chỉ từ số lần retry hay skip được cấu hình.
