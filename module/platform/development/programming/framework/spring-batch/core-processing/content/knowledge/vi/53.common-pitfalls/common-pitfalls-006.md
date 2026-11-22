# Skip quá rộng che lỗi dữ liệu trong Spring Batch

Trong Spring Batch, `skip` cho phép một `Step` bỏ qua item bị lỗi và tiếp tục xử lý các item còn lại, miễn là lỗi và số lượng bỏ qua đáp ứng chính sách đã cấu hình. Đây là cơ chế hữu ích khi nguồn dữ liệu không hoàn hảo: một dòng CSV sai định dạng, một bản ghi tùy chọn không đạt validation hoặc một record hỏng không nhất thiết phải làm dừng toàn bộ lô hàng triệu bản ghi.

Tuy nhiên, **skip quá rộng** là một lỗi thiết kế nguy hiểm. Khi ứng dụng cho bỏ qua hầu như mọi exception, job có thể kết thúc `COMPLETED` trong khi hàng nghìn giao dịch bị mất, dữ liệu bắt buộc không được ghi, một thay đổi schema khiến tất cả record lỗi, hoặc writer đã không thể kết nối database. Người vận hành chỉ nhìn trạng thái xanh sẽ tưởng dữ liệu đã được nạp đầy đủ.

**Nguyên tắc trọng tâm:** *skip phải là một quyết định chất lượng dữ liệu có phạm vi, giới hạn và khả năng đối soát; không phải cách chung để che mọi failure.* Trong **Spring Batch Core Processing → Lỗi thường gặp**, bài này giải thích cách skip hoạt động ở reader/processor/writer, vì sao `.skip(Exception.class)` có thể nguy hiểm, cách phân loại lỗi, cấu hình giới hạn thích hợp, xử lý reject/quarantine, kiểm tra đầu ra và xây bài test ngăn silent data loss.

Ví dụ dùng Spring Batch 5.x trở lên với Java 17+, `JobRepository` và step chunk-oriented. Các class nghiệp vụ như `InvalidPaymentRecordException` là class minh họa do ứng dụng tự định nghĩa.

## 1. Dấu hiệu của một chính sách skip quá rộng

Giả sử một job nhập 10.000 dòng thanh toán từ file CSV vào database. Do cấu hình sai kiểu dữ liệu, 7.500 dòng gây lỗi, nhưng step cho skip mọi exception với giới hạn rất lớn:

~~~java
// Anti-pattern: có thể che nhiều loại lỗi không phải dữ liệu hỏng riêng lẻ.
.faultTolerant()
.skip(Exception.class)
.skipLimit(Integer.MAX_VALUE)
~~~

Nếu những exception phát sinh được cơ chế skip xử lý và chưa vượt giới hạn, step có thể kết thúc thành công với rất ít bản ghi được ghi ra. Thao tác “COMPLETED” chỉ phản ánh job đã đi tới cuối theo policy, **không chứng minh dữ liệu đầu ra đầy đủ**.

Một dashboard chỉ hiển thị:

~~~text
Job importPaymentsJob: COMPLETED
~~~

sẽ che đi sự thật:

~~~text
Nguồn dự kiến:       10.000 bản ghi
Đọc/ghi được:         2.500 bản ghi
Skipped:              7.500 bản ghi
Kết quả:              có thể thiếu dữ liệu nghiệp vụ nghiêm trọng
~~~

Đây không phải lúc nào cũng là bug của framework. Spring Batch làm đúng theo cấu hình được yêu cầu: **bỏ qua lỗi đủ điều kiện cho đến giới hạn**. Lỗi nằm ở hợp đồng chất lượng dữ liệu và chính sách skip không phù hợp.

### Vì sao lập trình viên dễ mắc lỗi này?

- Muốn “cho batch chạy hết” trước một deadline, nên tăng `skipLimit` đến mức rất lớn.
- Không phân biệt exception do **input record** với exception do **hạ tầng**.
- Bắt gặp nhiều loại lỗi lạ và chọn `Exception.class` thay vì xác định nguyên nhân.
- Nhầm `COMPLETED` với “tất cả bản ghi đã được xử lý thành công”.
- Không có báo cáo reject hoặc đối chiếu số bản ghi đầu vào/đầu ra.
- Test chỉ assert status mà không kiểm tra dữ liệu thật đã commit.
- Muốn tránh job bị dừng do một record lỗi nhưng thiếu cơ chế quarantine để xử lý sau.

## 2. Skip khác retry, filter và fail như thế nào?

Trong chunk-oriented step, mỗi cơ chế mang một ý nghĩa khác nhau:

| Cơ chế | Hành vi | Khi nào phù hợp? | Tác động dữ liệu |
|---|---|---|---|
| **Filter** | `ItemProcessor.process(...)` trả `null`; item không được gửi tới writer. | Record hợp lệ nhưng không thuộc phạm vi xử lý, như amount = 0 theo quy tắc được công bố. | Có chủ đích loại record; `filterCount` tăng. |
| **Skip** | Một exception được xem là có thể bỏ qua theo policy; step tiếp tục. | Record lỗi độc lập, có giới hạn chấp nhận và có cách báo cáo. | Có thể thiếu record ở output; counter skip tăng. |
| **Retry** | Thử lại thao tác sau exception được chỉ định. | Lỗi có khả năng tạm thời, như deadlock hoặc kết nối chập chờn. | Có thể gọi reader/processor/writer lại; phải bảo đảm an toàn khi replay. |
| **Fail** | Step dừng với trạng thái lỗi. | Sai cấu hình, không truy cập được dữ liệu, dữ liệu bắt buộc sai hoặc lỗi vượt ngưỡng. | Giữ dấu vết sự cố để sửa/restart; các chunk trước có thể đã commit. |

Ví dụ:

- Dòng có trạng thái `CANCELLED` và job chỉ xử lý `APPROVED`: có thể **filter** nếu hợp đồng nêu rõ.
- Một dòng CSV có format sai, đã được phép loại khỏi tập hợp xuất báo cáo tham khảo: có thể **skip** trong hạn mức.
- Database báo deadlock ngắn: có thể **retry** với backoff.
- Database không tồn tại bảng kết quả sau migration: phải **fail** và sửa hạ tầng, không bỏ qua mọi item.
- Một giao dịch ghi sổ bắt buộc có số tiền âm bất hợp pháp: thường cần **fail** hoặc đưa job vào trạng thái chưa được phê duyệt; không tự skip rồi báo sổ sách hoàn tất.

Một exception ở processor không tự động cho thấy record được phép bỏ qua. Cần hỏi **record có bắt buộc phải được đưa vào kết quả không?**, **nguyên nhân thuộc input hay code?**, và **việc loại record có được nghiệp vụ chấp thuận không?**.

## 3. Cách Spring Batch tính skip

Trong step có fault tolerance, `SkipPolicy` quyết định một `Throwable` có được bỏ qua với số lần skip hiện tại hay không. Các API builder thường dùng:

~~~java
.faultTolerant()
.skip(InvalidPaymentRecordException.class)
.skipLimit(5)
~~~

Ở đây:

- `.faultTolerant()` bật các cơ chế kiểm soát retry/skip cho chunk step.
- `.skip(...)` chỉ định loại exception được phép skip.
- `.skipLimit(5)` đặt **ngân sách tổng số skip của step**: đọc, xử lý và ghi đều góp vào số skip theo cơ chế step. Lần skip vượt giới hạn khiến step thất bại.
- Exception không được cấu hình skip thông thường sẽ làm step thất bại nếu không có cơ chế retry/handler khác phù hợp.

Trong các cấu hình Spring Batch phổ biến, nếu không đặt `skipLimit` thì giới hạn mặc định của builder là **10** khi sử dụng cách cấu hình skip tương ứng; không nên phụ thuộc vào mặc định cho yêu cầu chất lượng quan trọng. Hãy ghi rõ ngưỡng trong cấu hình và trong tài liệu vận hành.

### Ba loại skip

`StepExecution` có các bộ đếm:

| Bộ đếm | Nơi lỗi phát sinh | Diễn giải |
|---|---|---|
| `getReadSkipCount()` | `ItemReader`, chẳng hạn lỗi parse một dòng CSV. | Một đơn vị input không được đọc thành item hợp lệ và được chính sách cho skip. |
| `getProcessSkipCount()` | `ItemProcessor` ném exception. | Item đã đọc nhưng không tạo output do lỗi được skip. |
| `getWriteSkipCount()` | `ItemWriter` không ghi được một item theo chính sách. | Item bị loại trong khi ghi; có thể cần rollback và gọi writer lại để cô lập. |
| `getSkipCount()` | Tổng skip của step. | Tổng theo các loại skip mà `StepExecution` ghi nhận. |

Không nhầm `filterCount` với skip. Khi processor trả `null`, đó là một item **được lọc**, không phải lỗi được bỏ qua.

`readCount` thường tính item được reader trả thành công, **không nhất thiết là số dòng vật lý của file**. Header, dòng bỏ qua theo cấu hình và một số cách reader tự xử lý dữ liệu có thể tạo chênh lệch. Khi cần đối chiếu file, hãy định nghĩa rõ cách tính dòng dữ liệu vật lý và làm việc với snapshot nguồn cố định.

### Giới hạn skip tuyệt đối không đồng nghĩa tỷ lệ lỗi an toàn

Giả sử `skipLimit=50`:

- Với file 1.000.000 dòng, 50 reject tương đương tỷ lệ rất nhỏ.
- Với file 20 dòng, 19 reject vẫn có thể nằm dưới ngưỡng 50; job có thể kết thúc mà hầu hết input không có output.

Vì vậy một ngưỡng tuyệt đối có thể chưa đủ. Nhiều nghiệp vụ cần thêm **ngưỡng phần trăm**, **ngưỡng theo loại lỗi** và **quy tắc tuyệt đối không được skip một số nhóm bản ghi**. Ngưỡng phần trăm không phải một thuộc tính `skipLimit` có sẵn; có thể kiểm tra ở bước quality gate sau xử lý dựa trên nguồn dữ liệu và báo cáo reject.

## 4. Vì sao .skip(Exception.class) nguy hiểm?

`Exception.class` là kiểu cha rất rộng của checked exception và nhiều runtime exception. Cấu hình:

~~~java
.faultTolerant()
.skip(Exception.class)
.skipLimit(1000000)
~~~

có thể khiến các lỗi **nếu đi qua cơ chế skip** bị coi là ứng viên để bỏ qua, ví dụ:

- `FlatFileParseException` do dữ liệu CSV sai.
- `IllegalArgumentException` hoặc `IllegalStateException` do logic của processor sai.
- `NullPointerException` do bug ứng dụng ở một nhánh xử lý.
- `DataIntegrityViolationException` do ràng buộc dữ liệu bị vi phạm.
- Exception do reader không lấy được dữ liệu như mong đợi.
- Exception từ writer khi ghi database hoặc gọi hệ thống bên ngoài.

Không phải mọi failure của framework hoặc transaction đều có thể được skip thành công. Một số lỗi sẽ làm step thất bại dù policy rộng vì không thể phục hồi an toàn. Tuy nhiên **chỉ cần một số lỗi nghiêm trọng bị skip là đủ làm dữ liệu sai**.

### Ví dụ 1: Schema đã thay đổi

CSV upstream đổi cột từ `amount` thành `amount_cents` nhưng reader/processor vẫn mong giá trị cũ. Nếu mỗi dòng ném một exception rồi được skip, job có thể đọc hết file mà gần như không tạo output.

Đây là **lỗi contract của cả file**, không phải một vài dòng lỗi độc lập. Hành động đúng thường là **fail-fast ở bước preflight** (kiểm tra header, số cột, phiên bản schema) trước khi xử lý hàng loạt.

### Ví dụ 2: Writer mất quyền ghi

Role runtime không còn quyền `INSERT` vào bảng đích sau migration. Mọi chunk đều lỗi. Nếu chính sách skip cố gắng cô lập từng item với phạm vi quá rộng, hệ thống có thể thực hiện nhiều thao tác vô ích, tăng tải và làm sai số lượng output.

Một lỗi phân quyền database cần được **sửa ở hạ tầng**, không được chuyển thành “record không hợp lệ”.

### Ví dụ 3: Processor có bug

~~~java
public PaymentOutput process(PaymentInput payment) {
    // Một refactor gây bug khi currency null.
    String currency = payment.currency().toUpperCase();
    return new PaymentOutput(payment.id(), currency, payment.amount());
}
~~~

Nếu `currency == null` làm `NullPointerException`, một `skip(Exception.class)` có thể che việc code không xử lý input theo hợp đồng. Sửa lỗi có thể là validation tường minh hoặc chính sách dữ liệu thiếu currency, **không phải chấp nhận mọi NPE như record cần bỏ**.

### Ví dụ 4: HTTP writer không idempotent

Writer gửi một giao dịch tới API, nhận timeout sau khi API đã xử lý. Nếu lỗi được skip mà không đối soát, job có thể báo transaction bị bỏ qua dù tác động đã xảy ra ở đối tác. Nếu retry không có idempotency key, tác động còn có thể bị nhân đôi.

Đây không chỉ là vấn đề skip limit. Nó liên quan **transaction boundary**, **kết quả không chắc chắn** và **khả năng phục hồi** của đích ngoài database.

## 5. Phân loại exception trước khi đặt policy

Cách làm an toàn là định nghĩa rõ nhóm lỗi, phản ứng và chủ sở hữu trách nhiệm sửa:

| Nhóm lỗi | Ví dụ | Quyết định thường phù hợp |
|---|---|---|
| **Malformed record có thể cô lập** | Một dòng CSV sai số lượng cột theo chính sách reject cho phép. | Skip có giới hạn, giữ vị trí lỗi/quarantine. |
| **Business validation được phép reject** | Trường tùy chọn sai format hoặc record ngoài quy tắc chấp nhận. | Skip chính xác loại exception nghiệp vụ, có audit. |
| **Record bắt buộc** | Giao dịch thanh toán cần được xử lý đầy đủ. | Fail hoặc chặn publish; không auto-skip. |
| **Schema/format toàn nguồn** | Header sai, thiếu cột bắt buộc, charset sai toàn file. | Fail-fast trước step hoặc khi xác định lỗi cấu trúc. |
| **Bug lập trình** | NPE, class cast, trạng thái bất khả thi. | Fail và sửa code. |
| **Database transient** | Deadlock, lock timeout tạm thời. | Retry có giới hạn/backoff khi an toàn. |
| **Database permanent** | Thiếu bảng, sai SQL, thiếu quyền, constraint dữ liệu bắt buộc. | Fail, sửa schema/quyền/dữ liệu. |
| **Side effect ngoài transaction** | Timeout HTTP sau POST. | Tra trạng thái hoặc dùng idempotency; không skip mù quáng. |
| **Hết tài nguyên** | Disk full, quota, connection pool cạn kéo dài. | Fail, phục hồi tài nguyên rồi restart. |

Phân loại dựa trên **semantics nghiệp vụ** quan trọng hơn tên class exception. Ví dụ cùng `DataIntegrityViolationException` có thể là duplicate đã được phép bỏ qua hoặc là lỗi foreign key phản ánh hỏng dữ liệu. Nếu cơ chế không phân biệt được, không nên skip toàn bộ class đó.

### Dùng exception nghiệp vụ chuyên biệt

Thay vì ném `IllegalArgumentException` cho mọi tình huống, có thể biểu diễn những record được phép reject bằng kiểu riêng:

~~~java
public final class SkippablePaymentValidationException
        extends RuntimeException {

    private final String errorCode;

    public SkippablePaymentValidationException(String errorCode) {
        super(errorCode); // Không ghép dữ liệu nhạy cảm vào message.
        this.errorCode = errorCode;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Và một exception khác cho vi phạm dữ liệu bắt buộc:

~~~java
public final class CriticalPaymentException extends RuntimeException {
    public CriticalPaymentException(String errorCode) {
        super(errorCode);
    }
}
~~~

Chỉ `SkippablePaymentValidationException` được đưa vào danh sách skip. `CriticalPaymentException` sẽ làm step thất bại theo policy thông thường. Việc tách exception cần được gắn với quy tắc nghiệp vụ đã được phê duyệt; đổi tên class không tự khiến một lỗi trở thành an toàn để bỏ.

## 6. Ví dụ: bộ dữ liệu nhỏ cho thấy skip hợp lệ và skip nguy hiểm

Giả sử xử lý file thanh toán:

~~~csv
event_id,currency,amount
PAY-001,VND,100000
PAY-002,VND,50000
PAY-003,VND,abc
PAY-004,VND,0
PAY-005,VND,-20000
PAY-006,VND,70000
PAY-007,VND,30000
~~~

Quy tắc minh họa:

1. Mọi amount dương và currency hợp lệ được ghi đúng một lần.
2. `amount=0` được **filter có chủ đích**, vì job chỉ nhập giao dịch phát sinh số dư.
3. Amount không parse được ở một dòng độc lập có thể **read skip**, tối đa theo ngưỡng được phép.
4. Amount âm không được chấp nhận; trong job **tham khảo phi tài chính** có thể cho process skip theo policy; trong job ghi sổ bắt buộc nên **fail**, không áp dụng policy bỏ qua.
5. Nếu thiếu header `amount` hoặc nhiều dòng đồng loạt sai schema, toàn file phải **fail preflight**, không được xem là “một loạt record xấu”.

Với policy cho phép reject ở item 3 và 5, kết quả mong đợi:

| Record | Kết quả | Lý do |
|---|---|---|
| `PAY-001` | Written | Amount hợp lệ. |
| `PAY-002` | Written | Amount hợp lệ. |
| `PAY-003` | Read skip | `abc` không parse thành số. |
| `PAY-004` | Filter | Amount bằng 0 theo hợp đồng. |
| `PAY-005` | Process skip | Amount âm, chính sách reject cho phép ở bài toán minh họa. |
| `PAY-006` | Written | Amount hợp lệ. |
| `PAY-007` | Written | Amount hợp lệ. |

~~~text
sourceDataLines   = 7        (không tính header)
readCount         = 6        (item parse thành công)
readSkipCount     = 1
filterCount       = 1
processSkipCount  = 1
writeSkipCount    = 0
writeCount        = 4
actualOutputRows  = 4
expectedAmountVND = 250000
~~~

Phép giải thích nguồn:

~~~text
7 dòng nguồn
  ├── 1 read reject      (PAY-003)
  └── 6 item đọc thành công
        ├── 1 filtered    (PAY-004)
        ├── 1 process reject (PAY-005)
        └── 4 accepted/written
~~~

Trong ví dụ này, chênh lệch `7 - 4 = 3` được giải thích rõ bằng 1 read skip, 1 process skip và 1 filter. Nếu job là kế toán bắt buộc không cho reject PAY-005, thì chỉ cần record ấy xuất hiện đã là **sự cố dữ liệu cần chặn publish**, dù job có thể được cấu hình skip kỹ thuật.

Điểm cần lưu ý: các phép cộng `sourceDataLines = readSkip + filter + processSkip + written` chỉ hợp lý khi **mọi dòng được phân loại đúng một lần**, mapping là 1:1, không có duplicate/dedup đặc biệt, và các counter phản ánh execution đã hoàn tất. Trong thực tế, cần đối chiếu thêm dữ liệu đã commit ở đích và nguồn manifest.

## 7. Cấu hình skip hẹp trong Spring Batch 5

Một cấu hình step theo chính sách an toàn hơn:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer,
        SafePaymentSkipListener skipListener) {

    return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(SkippablePaymentValidationException.class)
        .skipLimit(5)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .listener(skipListener)
        .build();
}
~~~

Ở đây:

- Chỉ exception validation đã được nghiệp vụ đánh dấu là được phép reject mới nằm trong danh sách skip.
- `.skipLimit(5)` giới hạn tổng số skip của step, không phải năm skip riêng cho mỗi giai đoạn.
- Lỗi truy cập database transient được định hướng **retry**, không phải skip.
- Lỗi SQL schema, thiếu quyền, NPE không nằm trong danh sách skip, nên không được hợp thức hóa thành reject tùy tiện.
- `chunk(100, transactionManager)` xác định ranh giới transaction; nếu writer lỗi và rollback, item có thể được đưa vào xử lý lại.

Ví dụ dùng các bean `PaymentInput`, `PaymentOutput` và `SafePaymentSkipListener` do ứng dụng định nghĩa. Không thể copy nguyên fragment mà thiếu các bean/lớp đó; mục tiêu của code là minh họa **cấu hình policy**.

### Khi muốn skip lỗi parse CSV

`FlatFileItemReader` có thể ném `FlatFileParseException` khi một dòng không thể parse. Có thể thêm:

~~~java
.skip(org.springframework.batch.item.file.FlatFileParseException.class)
.skipLimit(5)
~~~

**Chỉ làm vậy sau khi biết chắc lỗi parse là loại có thể cô lập ở mức dòng.** `FlatFileParseException` có thể phát sinh từ nhiều lỗi parse/mapping, kể cả thay đổi format nguồn. Skip toàn class mà không xác thực header, số cột, version/schema và mức độ bất thường vẫn có thể che việc **toàn bộ file không tương thích**.

Cách thiết kế tốt hơn:

1. Preflight file: xác thực header, encoding, schema version, đường dẫn và manifest.
2. Trong reader: chỉ cho bỏ một số lỗi dòng đã được contract cho phép; ghi vị trí dòng và mã lỗi chuẩn hóa.
3. Ở quality gate: fail khi số lượng/tỷ lệ reject vượt policy hoặc nguồn có dấu hiệu lỗi hàng loạt.

Không cần thiết phải cho skip parse failure ở mọi batch. Với nguồn “all-or-nothing” như bảng chốt sổ, một dòng sai có thể là lý do dừng cả job.

## 8. SkipPolicy tùy chỉnh khi quy tắc phức tạp hơn

Khi cần phân loại lỗi động theo loại exception và số skip hiện tại, Spring Batch hỗ trợ `SkipPolicy`. Ví dụ policy chỉ skip `SkippablePaymentValidationException` với ngân sách tối đa năm:

~~~java
import org.springframework.batch.core.step.skip.SkipPolicy;

public final class NarrowPaymentSkipPolicy implements SkipPolicy {

    private static final long MAX_SKIPS = 5;

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        if (!(throwable instanceof SkippablePaymentValidationException)) {
            return false; // Lỗi khác phải xử lý theo cơ chế failure.
        }

        // Một số luồng framework có thể probe classifier với skipCount < 0:
        // lúc đó chỉ đánh giá loại lỗi, không áp giới hạn số lần.
        if (skipCount < 0) {
            return true;
        }

        return skipCount < MAX_SKIPS;
    }
}
~~~

Đăng ký:

~~~java
.faultTolerant()
.skipPolicy(new NarrowPaymentSkipPolicy())
~~~

Ví dụ này là policy **thuần xác định**: cùng loại lỗi và cùng skip count thì trả cùng quyết định. Nó không sử dụng một counter mutable tự tăng bên trong singleton, vì callback classifier có thể được gọi ở các thời điểm khác nhau hoặc để kiểm tra khả năng skip. Nếu muốn nhiều nhóm lỗi với ngân sách riêng, hãy thiết kế bộ đếm trạng thái có ranh giới execution và transaction phù hợp, hoặc thực hiện quality gate có audit bền vững.

Các trường hợp cần xử lý rõ hơn policy này:

- Exception bị bọc trong một hoặc nhiều `cause`. Nếu unwrap, phải có danh sách wrapper tin cậy, không vô tình nhận lỗi hạ tầng thành validation.
- Một record có nhiều lỗi. Phải định nghĩa code lỗi ưu tiên và kết quả reject duy nhất.
- Điều kiện dựa vào dữ liệu nghiệp vụ “record VIP không được skip”. Tốt hơn nên ném **exception khác** cho record critical hoặc kiểm tra eligibility ở tầng validation, không dựa vào việc đoán từ raw exception message.
- Ngưỡng tỷ lệ lỗi trên tổng file. Chỉ `skipCount` không biết chắc số dòng nguồn cuối cùng; cần dữ liệu manifest và quality gate.
- Các step chạy song song: mỗi step/partition có counters riêng, nên giới hạn toàn job cần tổng hợp và kiểm tra thêm.

Không nên dựa vào `SkipPolicy` để bù cho thiếu hợp đồng dữ liệu. Chính sách phải được thiết kế từ câu hỏi nghiệp vụ: **được bỏ bản ghi loại nào, tối đa bao nhiêu và ai phải xử lý phần bị bỏ?**

## 9. Retry đúng lỗi, không chuyển lỗi hạ tầng thành reject

Nếu database deadlock hoặc tạm không kết nối được, lỗi có thể biến mất khi thử lại. Với writer JDBC tham gia transaction của chunk, retry sau rollback có thể hợp lý nếu thao tác ghi an toàn khi replay.

Ví dụ:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(SkippablePaymentValidationException.class)
.skipLimit(5)
~~~

Điểm quan trọng:

- **Retry** lỗi transient theo giới hạn và backoff phù hợp.
- **Skip** lỗi dữ liệu đã được phép reject, không skip lỗi do database mất kết nối.
- Khi retry hết giới hạn, step cần **fail** hoặc dùng chính sách được thiết kế riêng. Không nên chuyển mọi lỗi retry-exhausted thành skip một cách mặc định.
- Không dùng `.retry(Exception.class)` cho mọi bug/chứng cứ sai dữ liệu; lỗi schema hoặc logic không tự khỏi.

### Lỗi writer có thể không an toàn khi skip

Trong chunk-oriented processing, writer có thể nhận cả chunk nhiều item. Nếu một item trong chunk gây lỗi, framework có thể rollback rồi gọi writer lại với dữ liệu để cô lập item bị lỗi theo thuật toán fault tolerance. Điều này giả định các lần thử ghi trước có thể được rollback hoặc replay an toàn.

Ví dụ writer gửi POST tới API ngoài transaction; một request timeout có thể vẫn đã được xử lý ở phía API. Skip item sau timeout **không chứng minh** item chưa tạo side effect. Trước khi cho skip writer error:

1. Xác định đích có transaction/rollback với chunk hay không.
2. Có thể tra trạng thái ở đích theo event ID không?
3. Có idempotency key ổn định để gọi lại không?
4. Exception có chỉ ra **item riêng lẻ** hay toàn bộ hệ thống đích đang lỗi?
5. Khi skip, output có còn phù hợp hợp đồng nghiệp vụ không?

Nếu không trả lời được, ưu tiên **fail, đối soát và phục hồi có kiểm soát**, thay vì auto-skip.

## 10. SkipListener: ghi lý do bỏ record nhưng không làm lộ dữ liệu

Một vấn đề của skip quá rộng là **không ai biết record nào bị bỏ**. Spring Batch có `SkipListener` cho ba giai đoạn:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class SafePaymentSkipListener
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
        log.warn("batch.item.skipped stage=WRITE category=OUTPUT_REJECTED");
    }
}
~~~

Đây là **listener minh họa log an toàn**, không có logic ghi quarantine. Trong ứng dụng thực, cần gắn loại lỗi đúng theo exception và chính sách xử lý cụ thể; không phải mọi lỗi reader đều là `FILE_FORMAT`, hoặc mọi lỗi writer đều là lỗi dữ liệu.

Không nên:

~~~java
log.warn("Skipped item={} exception={}", item, error);
~~~

`item.toString()` có thể chứa tên, email, số tài khoản, số tiền hoặc token. `FlatFileParseException.getInput()` có thể trả về cả dòng CSV lỗi; exception message/cause cũng có thể chứa dữ liệu. Hãy log **jobExecutionId, stepExecutionId, errorCode, resource alias và line number** nếu chúng được xác định là an toàn, không dump raw item.

### Đưa record lỗi vào quarantine

Với nguồn quan trọng, một reject cần có đường xử lý tiếp theo. Có thể tạo **quarantine store** với các trường:

| Trường | Vai trò |
|---|---|
| `batchKey` | Xác định kỳ/phiên bản nguồn. |
| `sourceId` / `resourceAlias` | Xác định nguồn logic. |
| `sourceRecordRef` | Opaque ID hoặc số dòng khi phù hợp; không lộ dữ liệu nhạy cảm. |
| `stage` | READ, PROCESS hoặc WRITE. |
| `errorCode` | Mã lỗi đã chuẩn hóa, không chứa raw message. |
| `jobInstanceId` / `jobExecutionId` | Truy vết quá trình phát hiện lỗi. |
| `disposition` | NEW, UNDER_REVIEW, CORRECTED, REPROCESSED hoặc REJECTED_FINAL. |
| `recordPayloadRef` | Tham chiếu tới vùng lưu dữ liệu nhạy cảm có kiểm soát nếu cần. |

Quarantine là **kho dữ liệu được bảo vệ**, không phải logger thông thường. Quyền truy cập, retention và mã hóa phải phù hợp phân loại dữ liệu.

Cần chú ý callback skip, rollback và transaction: nếu listener ghi một record ra hệ thống ngoài transaction, có thể bị gọi lại hoặc để lại dấu vết không tương ứng với trạng thái commit cuối. Hãy bảo đảm **idempotency** của bản ghi quarantine, ví dụ unique key theo `(batchKey, sourceRecordRef, errorCode)` khi business semantics cho phép. Nếu không có source record ID ở read error, dùng định danh thay thế đã được thiết kế như `(fileVersion, lineNumber)`.

Đừng giả định một `SkipListener` đơn giản tự bảo đảm exactly-once trong mọi cấu hình đa luồng/remote step. Kết quả quarantine cần được đối chiếu với số skip bền vững sau khi step kết thúc.

## 11. Bảo vệ dữ liệu bằng reconciliation, không chỉ trạng thái job

Một job có thể `COMPLETED` với nhiều skip hợp lệ. Để biết kết quả có thể công bố hay không, cần một phép đối chiếu từ nguồn tới đích:

~~~mermaid
flowchart TD
    A["Snapshot nguồn + manifest"] --> B["Read / Process / Write"]
    B --> C["StepExecution counters"]
    B --> D["Reject / filter audit"]
    B --> E["Output đã commit"]
    C --> F["Reconciliation + quality gate"]
    D --> F
    E --> F
    F --> G{"Đạt hợp đồng?"}
    G -->|Có| H["Publish / báo cáo thành công"]
    G -->|Không| I["Chặn publish + báo lỗi"]
~~~

Một phép đối chiếu đơn giản ở pipeline 1:1 với dữ liệu cố định:

\[
\text{sourceDataRows}
= \text{readRejected} + \text{filtered}
+ \text{processRejected} + \text{writeRejected} + \text{acceptedOutputRows}
\]

Đẳng thức này **có điều kiện**: mọi dòng phải được phân loại đúng một lần, không có thay đổi input trong lúc chạy, không có output 1:n hoặc n:1, không có duplicate policy đặc biệt, và các giá trị phải phản ánh kết quả cuối đã commit. Trong trường hợp khác, phải điều chỉnh grain và cách tính.

### Quality gate tối thiểu

Đối với job nhập dữ liệu, có thể quy định:

- `sourceDataRows` lấy từ manifest đã chốt, không lấy từ `writeCount`.
- Mọi reject phải có loại lỗi và nguồn tham chiếu truy vết.
- `totalSkipCount` không vượt **ngưỡng tuyệt đối**.
- `rejectRate` không vượt **ngưỡng phần trăm** được phê duyệt.
- Những loại record **critical** không được skip.
- `expectedAcceptedRows` bằng **số business key duy nhất ở output đã commit**, khi hợp đồng 1:1.
- Nếu dữ liệu có giá trị tiền tệ, tổng theo currency cũng phải đối chiếu và không có sai lệch ngoài tolerance đã xác định.
- Không có thiếu/thừa key dù count tổng bằng nhau.

Ví dụ:

~~~text
batchKey           = 2026-11-15:warehouse-A:v1
sourceDataRows     = 7
readRejected       = 1
filtered           = 1
processRejected    = 1
writeRejected      = 0
expectedOutputRows = 4
actualOutputRows   = 4
expectedAmountVND  = 250000
actualAmountVND    = 250000
qualityResult      = PASS_WITH_REJECTS
~~~

`PASS_WITH_REJECTS` là **trạng thái chất lượng do ứng dụng định nghĩa**, không phải `BatchStatus` mặc định. Nó chỉ được chấp nhận nếu các reject nằm trong policy nghiệp vụ. Với một hệ thống không cho phép reject ở nhóm thanh toán, chính cùng bộ số liệu trên phải dẫn tới `FAIL`.

### Không chỉ so count

Đầu vào hợp lệ có các ID `A, B, C`; output có `A, B, B`. Count đều bằng 3 nhưng **thiếu C và trùng B**. Nếu unique constraint làm writer bỏ các duplicate bằng `ON CONFLICT DO NOTHING`, `writeCount` vẫn không phải lúc nào cũng bằng số hàng mới insert.

Vì vậy cần so sánh theo **business key**, ví dụ tìm ID thiếu bằng SQL anti-join, ngoài việc so count và tổng amount.

## 12. Đặt quality gate thành một Step riêng

Một mô hình dễ vận hành là **load → reconcile → publish**:

~~~java
@Bean
Job importPaymentsJob(
        JobRepository jobRepository,
        Step loadPaymentsStep,
        Step reconcilePaymentsStep,
        Step publishPaymentsStep) {

    return new JobBuilder("importPaymentsJob", jobRepository)
        .start(loadPaymentsStep)
        .next(reconcilePaymentsStep)
        .next(publishPaymentsStep)
        .build();
}
~~~

Step `loadPaymentsStep` có thể `COMPLETED` dù đã skip trong ngân sách. `reconcilePaymentsStep` đánh giá policy từ snapshot nguồn, counters/audit reject và output đã commit. Nếu mismatch hoặc vượt ngưỡng chất lượng, step nên báo failure phù hợp để ngăn `publishPaymentsStep` chạy trong luồng thành công.

Lợi ích:

1. Trạng thái batch không chỉ phản ánh việc code đã chạy xong mà còn phản ánh điều kiện dữ liệu được công bố.
2. Một sai lệch chưa vượt `skipLimit` nhưng vượt tỷ lệ reject hoặc vi phạm nhóm critical vẫn có thể bị chặn.
3. Dashboard có thể tách rõ **lỗi hạ tầng**, **record reject** và **lỗi reconciliation**.
4. Kết quả có thể được lưu bền vững cùng `batchKey`, version nguồn, thời điểm và execution ID để audit.

Trong hệ thống mà dữ liệu đầu ra không thể “thu hồi” sau khi writer commit, nên ghi vào **staging có phân vùng batch/version** rồi chỉ công bố sau quality gate. Không nên cho downstream tiêu thụ output chưa được đối chiếu nếu hợp đồng yêu cầu all-or-nothing ở mức batch.

### Ví dụ SQL kiểm chứng đầu ra

Giả sử output đã lưu theo kỳ xử lý:

~~~sql
CREATE TABLE processed_payment (
    batch_key VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, event_id)
);

SELECT
    COUNT(*) AS actual_rows,
    COUNT(DISTINCT event_id) AS distinct_ids,
    COALESCE(SUM(amount), 0.00) AS actual_amount
FROM processed_payment
WHERE batch_key = :batchKey
  AND currency = 'VND';
~~~

Khi có nhiều currency, đối chiếu theo từng currency thay vì cộng các loại tiền khác nhau. Cần xác nhận expected amount được tính từ **nguồn đã chuẩn hóa** và loại reject/filter đúng quy tắc, không tự copy expected từ output.

Nếu cần kiểm tra missing keys, có thể dùng bảng staging `accepted_payment` chứa tập record được chấp nhận đã được chốt:

~~~sql
SELECT a.event_id
FROM accepted_payment a
LEFT JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND p.event_id IS NULL;
~~~

Kết quả phải rỗng khi mỗi accepted record bắt buộc có đúng một output. Với output đã có nhưng không thuộc accepted set, thực hiện anti-join theo hướng ngược lại. Chỉ dùng phép so sánh này khi `accepted_payment` thật sự là nguồn kỳ vọng đủ độc lập.

## 13. Skip quá rộng trong môi trường partitioning và chạy song song

Khi dùng partitioned step, multi-threaded step hoặc remote chunking, rủi ro “skip vẫn dưới ngưỡng” có thể tăng nếu mỗi worker/partition có ngân sách riêng.

Ví dụ:

~~~text
partition-A: skipLimit=10, skipped=9
partition-B: skipLimit=10, skipped=9
partition-C: skipLimit=10, skipped=9

Tổng ở mức job: 27 record bị bỏ
~~~

Nếu nghiệp vụ chỉ cho phép **tối đa 10 record reject cho toàn kỳ**, việc mỗi partition có `skipLimit=10` không bảo đảm ràng buộc toàn cục. `StepExecution` ở từng partition có counters riêng; manager có thể tổng hợp theo cơ chế partitioning, nhưng chính sách nghiệp vụ nên được kiểm tra trên **tập kết quả cuối toàn job**.

Đối với nhiều worker:

- Quarantine cần có khóa duy nhất để tránh bản ghi reject trùng khi worker bị retry.
- Số liệu read/write/skip của từng attempt không được cộng máy móc nếu có replay.
- Cần liên kết reject với `batchKey` và `partitionId` nhưng kiểm chứng unique business keys toàn cục.
- Bước quality gate chỉ chạy sau khi các partition cần thiết đã hoàn tất/được xác minh.
- Nếu một partition bị lỗi hạ tầng, không được coi toàn bộ output thiếu của nó là “các record được phép skip”.

Một bước kiểm tra theo source manifest và database đích giúp tránh phụ thuộc hoàn toàn vào thống kê cục bộ của từng worker.

## 14. Retry, rollback, restart và idempotency tác động tới skip

Lỗi writer có thể khiến transaction của chunk rollback và writer được gọi lại. Nếu một item được skip sau nhiều lần thử, **số lần gọi writer** không bằng số item đã được ghi thành công. Listener và log có thể xuất hiện tại những thời điểm khác nhau với retry/rollback, nên không được suy ra số output từ số log message.

### Chunk trước vẫn có thể đã commit

~~~text
chunkSize=3

Chunk 1: A, B, C  -> COMMITTED
Chunk 2: D, E, F  -> lỗi writer -> ROLLBACK
JobExecution #1: FAILED

JobExecution #2: restart của cùng JobInstance
          -> xử lý lại phần chưa hoàn tất theo checkpoint
~~~

Nếu skip policy quá rộng ở chunk 2, hệ thống có thể bỏ D/E/F rồi báo step hoàn tất, dù output bắt buộc bị thiếu. Khi được sửa và restart, các chunk trước vẫn tồn tại; vì vậy writer cần idempotency và metadata phải được giữ đúng.

Không nên xóa bảng `BATCH_*` hoặc thêm `run.id` mới chỉ để vượt qua trạng thái lỗi. Việc tạo JobInstance mới bằng identifying parameter ngẫu nhiên có thể chạy lại toàn bộ input và làm trùng side effect.

### Audit reject và restart

Giả sử lần đầu đã ghi `REJECTED` cho record R; sau khi sửa nguồn, lần restart xử lý được R. Cần quy định:

- Record R được giữ trong lịch sử reject với trạng thái `RESOLVED`, hay có một bản audit mới?
- Kết quả quality gate của **phiên bản nguồn hiện tại** tính R là accepted hay rejected?
- Có được sửa input khi restart cùng JobInstance không, hay cần tạo source version/revision mới để bảo đảm snapshot?
- Nếu write đã commit nhưng checkpoint chưa xác nhận ở cùng tài nguyên, record có thể xuất hiện lại không?

Một thiết kế tốt lưu `batchKey` + `sourceVersion` + business key + outcome cuối, đồng thời giữ lịch sử attempts riêng khi cần. **Không cộng mọi lần reject trong tất cả execution attempts như thể đó là số record duy nhất bị bỏ vĩnh viễn.**

## 15. Một bộ test tối thiểu để phát hiện skip quá rộng

Chỉ test happy path không giúp phát hiện dữ liệu bị bỏ âm thầm. Nên dùng fixture đủ nhỏ để biết chính xác từng record thuộc nhóm nào:

| Kịch bản | Dữ liệu/exception | Kỳ vọng |
|---|---|---|
| Record hợp lệ | 3 item đúng | Không skip, 3 output. |
| Validation được phép reject | 1 `SkippablePaymentValidationException` | Counter process skip tăng, quarantine có lý do. |
| Vượt skip limit | 6 record skippable, `skipLimit=5` | Step `FAILED` ở lần vượt giới hạn. |
| Critical record lỗi | `CriticalPaymentException` | Step `FAILED` ngay theo policy, không skip. |
| Bug lập trình | `NullPointerException` từ processor | Step `FAILED`, không hợp thức hóa thành reject. |
| Reader lỗi format đã cho phép | 1 dòng CSV sai format | Read skip được ghi nhận, vị trí dữ liệu được lưu an toàn. |
| Header/schema sai | Thiếu cột bắt buộc | Preflight fail trước xử lý hàng loạt. |
| Lỗi database transient | Lần đầu deadlock, lần sau thành công | Retry trong giới hạn, output đúng một lần. |
| Database thiếu quyền | Writer bị từ chối quyền | Step `FAILED`, không write skip hàng loạt. |
| Tỷ lệ reject vượt ngưỡng | File 10 dòng, 4 reject, `skipLimit=5` | Quality gate `FAIL` nếu tỷ lệ 40% không được phép. |
| Có filter đúng quy tắc | Amount 0 | `filterCount` tăng, không coi là skip. |
| Count đúng nhưng thiếu key | A, B, C → A, B, B | Reconciliation phát hiện thiếu C/trùng B. |
| Writer fail giữa chunk | Đã ghi một phần trong transaction rồi lỗi | Chunk rollback; không đếm dữ liệu chưa commit. |
| Restart job | Một chunk đã commit trước failure | Output cuối không trùng và đầy đủ theo business key. |

### Ví dụ assert counters sau integration test

Giả sử dùng `JobLauncherTestUtils` và các bean test đã cấu hình:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

JobExecution execution = jobLauncherTestUtils.launchJob(testParameters);

assertThat(execution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importPaymentsStep"))
    .findFirst()
    .orElseThrow();

assertThat(step.getReadSkipCount()).isEqualTo(1);
assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getWriteSkipCount()).isZero();
assertThat(step.getFilterCount()).isEqualTo(1);
assertThat(step.getWriteCount()).isEqualTo(4);

// Quan trọng: query database output theo batchKey và kiểm tra:
// 4 business key đúng; không trùng; tổng VND = 250000.
~~~

Đây là fragment kiểm thử minh họa; `jobLauncherTestUtils`, `testParameters` và step cụ thể được khởi tạo trong test context. Điều kiện `BatchStatus.COMPLETED` chỉ có ý nghĩa khi **chính sách cho phép các reject của fixture**. Với job không chấp nhận bỏ bản ghi, test phải mong `FAILED` thay vì cố làm các assertion trên đi qua.

### Test để bảo vệ chống broad exception

Một test regression nên cố ý cho processor ném `NullPointerException` hoặc exception của hạ tầng, sau đó khẳng định:

~~~java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(step.getProcessSkipCount()).isZero();
~~~

Nhờ vậy, nếu ai đó sửa config từ `.skip(SkippablePaymentValidationException.class)` thành `.skip(Exception.class)`, test sẽ có khả năng phát hiện thay đổi nguy hiểm.

Kiểm tra **đầu ra thật đã commit** luôn quan trọng hơn kiểm tra logger hoặc một con số `writeCount`. Trong những trường hợp UPSERT/dedup hoặc writer phát nhiều output từ một item, cần so sánh theo đúng grain nghiệp vụ.

## 16. Cảnh báo vận hành khi skip tăng đột biến

Một job có thể chạy “xanh” trong nhiều ngày, sau đó nhà cung cấp thay đổi format file và số skip tăng gấp 100 lần. Nếu hệ thống chỉ alert khi `BatchStatus.FAILED`, sự cố dữ liệu có thể tồn tại lâu.

Nên theo dõi:

| Chỉ số | Cách sử dụng |
|---|---|
| `readSkipCount` | Phát hiện lỗi parse/đọc nguồn tăng bất thường. |
| `processSkipCount` | Phát hiện vi phạm validation hoặc mapping nghiệp vụ. |
| `writeSkipCount` | Phát hiện bản ghi đầu ra bị từ chối; cần kiểm tra transaction/idempotency. |
| `filterCount` | Theo dõi thay đổi trong phân bố dữ liệu hợp lệ được lọc. |
| `skipped / sourceDataRows` | Tỷ lệ reject trên nguồn đã chốt, không chia cho một counter mơ hồ. |
| `writeCount` và actual output rows | Đối chiếu hoạt động writer với dữ liệu thật. |
| `errorCode` theo tần suất | Xác định nguyên nhân reject tăng như file schema, field missing, invalid amount. |
| `batchKey` / source version | Truy xuất kỳ dữ liệu, tránh gộp các phiên bản hoặc execution attempts. |

Có thể đặt các mức cảnh báo:

- **Warning:** số skip tăng so với baseline, nhưng vẫn trong ngưỡng chất lượng.
- **Critical:** xuất hiện lỗi thuộc danh sách “không được skip”, tỷ lệ reject vượt policy hoặc phép đối chiếu key/amount sai.
- **Block publish:** không công bố output khi batch chưa đạt quality gate, ngay cả khi load step `COMPLETED`.

Tránh dùng `jobExecutionId` hoặc ID mỗi record làm nhãn metric thông thường vì cardinality sẽ rất lớn. Dùng log/audit cho ID chi tiết, metric cho nhóm hữu hạn như `jobName`, `stepName`, `errorCode` và `status`.

### Xử lý an toàn với thông tin nhạy cảm

Không in nguyên dòng CSV hoặc cả item để giải thích skip. Dữ liệu lỗi có thể chứa tài khoản, email, số định danh hay token. Log có thể chứa:

~~~json
{
  "event": "batch.item.skipped",
  "batchKey": "2026-11-15:warehouse-A:v1",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stage": "PROCESS",
  "errorCode": "INVALID_AMOUNT",
  "sourceRecordRef": "line-6"
}
~~~

Đây là **schema log ứng dụng tự định nghĩa**. Dữ liệu gốc chỉ được lưu ở nguồn/quarantine có quyền truy cập riêng. `sourceRecordRef` phải được thiết kế an toàn; không dùng email/số điện thoại làm khóa log.

## 17. Một quy trình khắc phục khi phát hiện job skip quá rộng

Giả sử vận hành phát hiện job báo `COMPLETED` nhưng output thiếu dữ liệu. Không nên lập tức chạy lại bằng JobParameters ngẫu nhiên. Có thể xử lý theo trình tự:

1. **Ngừng công bố/tiêu thụ output đáng ngờ** nếu có thể, hoặc đánh dấu kỳ dữ liệu chưa đạt chất lượng.
2. **Chốt phạm vi sự cố:** jobName, business key, source version, JobInstance/JobExecution, thời điểm và những đích đã ghi.
3. **Đọc `StepExecution` counters:** read/process/write skip, filter, read/write/rollback counts; phân tích exception types an toàn.
4. **Đối chiếu dữ liệu nguồn với đích:** count, unique IDs, amount hoặc checksum; xác định những record thiếu/thừa/sai.
5. **Xác định nguyên nhân thật:** schema thay đổi, input xấu rải rác, bug processor, writer mất quyền hay side effect không transactional.
6. **Sửa policy:** thu hẹp loại exception, ngưỡng skip, thêm preflight và quality gate. Không chỉ hạ `skipLimit` nếu lỗi vẫn bị phân loại sai.
7. **Quyết định cách phục hồi:** sửa dữ liệu rồi restart đúng JobInstance nếu phù hợp, hoặc reprocess một source revision mới với quy tắc version hóa output rõ ràng.
8. **Bảo vệ idempotency:** unique business keys, checkpoint và đối soát trước khi replay; không nhân đôi các chunk đã commit.
9. **Lưu audit của reject và kết quả sửa:** ai quyết định bỏ record, lý do, trạng thái sau correction, kết quả đối chiếu cuối.
10. **Bổ sung test regression** cho exception class nguy hiểm và tỷ lệ reject bất thường trước khi triển khai lại.

Trong quá trình phục hồi, **không xóa `BATCH_*` chỉ để có thể chạy lại**: metadata chứa lịch sử execution và checkpoint cần cho restart. Không được tự cho rằng tất cả đầu ra đã rollback khi step từng thất bại; nhiều chunk có thể đã commit.

### Nếu đã có bản ghi bị bỏ vĩnh viễn?

Một record không được ghi có thể cần:

- Sửa nguồn và tái xử lý một **batch revision** mới.
- Bổ sung bằng job bù trừ với business key độc lập.
- Quarantine để người có thẩm quyền đánh giá.
- Giữ trạng thái reject cuối cùng nếu nghiệp vụ thực sự cho phép.

Cách chọn phụ thuộc yêu cầu nghiệp vụ và khả năng idempotency của writer. Một bước “replay tất cả file” không chắc an toàn khi database hoặc API đã nhận một phần side effect.

## 18. Các sai lầm thường gặp khi cấu hình skip

**“`.skip(Exception.class)` giúp job bền bỉ hơn.”** Nó có thể khiến bug, lỗi hạ tầng hoặc contract sai bị coi là dữ liệu xấu. Bền bỉ là phục hồi đúng lỗi tạm thời, không phải luôn tiếp tục bằng cách bỏ output.

**“`skipLimit` thật lớn cho phép xử lý hết file.”** Có thể, nhưng điều đó không chứng minh đủ dữ liệu. Với file nhỏ, một tỷ lệ reject lớn vẫn có thể chưa vượt ngưỡng tuyệt đối.

**“Processor trả `null` hay throw đều như nhau.”** Không. `null` là filter, exception được policy skip là reject; các counter và ý nghĩa nghiệp vụ khác nhau.

**“Nếu job COMPLETED thì không cần kiểm tra skip count.”** Sai. Một step có thể kết thúc thành công với skip được phép; chất lượng đầu ra phải qua quality gate.

**“Tôi log exception nên sau này sẽ tìm được item.”** Exception có thể chứa raw data nhạy cảm, và log không bảo đảm retention/audit đủ. Dùng code lỗi, record reference và quarantine phù hợp.

**“DataIntegrityViolationException nghĩa là item hỏng, có thể skip.”** Không luôn đúng: có thể là lỗi schema, thiếu reference data hay ràng buộc dữ liệu bắt buộc. Cần phân loại trước.

**“Writer lỗi thì cứ skip record cuối cùng.”** Khi writer nhận cả chunk, có thể chưa xác định item nào gây lỗi. Rollback và replay phải an toàn; với API ngoài transaction, kết quả có thể không chắc chắn.

**“Lỗi database transient nên skip để không chậm batch.”** Lỗi kết nối tạm thời có thể cần retry/backoff. Bỏ item do hạ tầng yếu không phải chiến lược chất lượng dữ liệu.

**“Bảng reject có bao nhiêu hàng thì có bấy nhiêu item skip.”** Listener và retry/rollback có thể tạo duplicate nếu audit không idempotent. Phải đối chiếu outcome theo business key và execution.

**“Mỗi partition có `skipLimit=10` thì job cũng tối đa 10 lỗi.”** Không nên giả định như vậy; giới hạn cấp partition/step không tự bảo đảm ngân sách toàn job.

**“Đầu ra ít hơn nguồn là lỗi.”** Không luôn đúng khi có filter, reject hoặc aggregate hợp lệ. Quan trọng là giải thích được và đối chiếu đúng grain.

**“Đầu ra bằng nguồn là đúng.”** Không luôn đúng: có thể thiếu một ID và thừa ID khác, hoặc amount sai nhưng tổng record vẫn bằng nhau. Kiểm tra tập khóa và giá trị nghiệp vụ.

## 19. Hướng dẫn thiết kế chính sách skip an toàn

Khi triển khai một job mới hoặc sửa một job đang skip quá rộng:

1. **Viết hợp đồng đầu vào/đầu ra.** Xác định record bắt buộc, record tùy chọn, filter, reject và quy tắc nguồn dữ liệu.
2. **Preflight nguồn.** Kiểm tra header, schema version, encoding, manifest và điều kiện làm lỗi toàn file. Không dùng row skip để che file sai cấu trúc.
3. **Phân loại exception.** Dùng exception nghiệp vụ riêng cho lỗi được phép skip; fail-fast lỗi code, bảo mật, cấu hình và dữ liệu critical.
4. **Phân biệt retry và skip.** Retry lỗi transient có giới hạn và an toàn replay; skip lỗi record cô lập đã được phê duyệt.
5. **Đặt ngân sách rõ.** Có `skipLimit` tuyệt đối, quality gate theo tỷ lệ và theo nhóm lỗi/nhóm dữ liệu quan trọng.
6. **Ghi reject có thể truy vết.** Mã lỗi chuẩn, business/source reference, quarantine có quyền và idempotency; không log toàn bộ item.
7. **Đối chiếu sau khi ghi.** Dùng snapshot nguồn, count, key, sum và output đã commit; không chỉ xem `BatchStatus`.
8. **Chỉ publish khi đạt chất lượng.** Phân biệt `loadStep COMPLETED` với `batch data approved`.
9. **Giữ khả năng restart.** Không sửa/xóa metadata bừa bãi, giữ identifying parameters và thiết kế writer idempotent.
10. **Kiểm thử các lỗi ngoài danh sách skip.** Chủ động gây NPE, lỗi schema, lỗi quyền DB, writer timeout và ngưỡng reject vượt policy.

Một chính sách tốt thường được mô tả dưới dạng bảng quyết định:

| Điều kiện | Hành động | Bằng chứng lưu |
|---|---|---|
| Record sai field tùy chọn, cho phép reject | Skip có giới hạn | Error code + source reference + quarantine |
| Record critical không hợp lệ | Fail | Job/step IDs + lỗi nghiệp vụ chuẩn hóa |
| File header/schema sai | Fail preflight | Source version + schema mismatch code |
| DB transient | Retry có giới hạn | Số retry + tình trạng hạ tầng |
| DB mất quyền/schema | Fail | Error category + component, không log credential |
| HTTP timeout không rõ kết quả | Reconcile trước retry | Idempotency key + trạng thái remote |
| Reject rate vượt ngưỡng | Block publish | Reconciliation report |
| Tất cả điều kiện đạt | Publish | Batch key + quality result + output totals |

## Kết luận

Trong Spring Batch, **skip quá rộng có thể biến lỗi dữ liệu hoặc lỗi hệ thống thành “thành công giả”**. Cấu hình `.skip(Exception.class)` hoặc nâng `skipLimit` vô hạn có thể khiến job chạy hết mà không bảo đảm đầu ra đầy đủ và đúng. `COMPLETED` chỉ có ý nghĩa trong phạm vi chính sách được lập trình, không phải chứng nhận chất lượng dữ liệu.

Để tránh silent data loss, hãy **skip hẹp theo exception và quy tắc nghiệp vụ**, phân biệt filter/retry/fail, đặt ngưỡng tuyệt đối và theo tỷ lệ, giữ reject audit/quarantine an toàn, đối chiếu snapshot nguồn với output đã commit theo business key và chỉ công bố kết quả khi quality gate đạt. Khi đó một bản ghi lỗi có thể được loại bỏ có chủ đích mà **không che mất những sự cố phải dừng job để xử lý**.
