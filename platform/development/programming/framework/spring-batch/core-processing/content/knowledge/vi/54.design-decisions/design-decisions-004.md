# Chọn skip hay fail fast — quyết định thiết kế trong Spring Batch

## 1. Câu hỏi thiết kế: một bản ghi sai có nên làm dừng cả job?

Một batch job nhận 100.000 đơn hàng từ đối tác. Sau khi đọc 20.000 dòng, processor gặp một đơn có số tiền âm. Có ít nhất hai cách xử lý:

- **Skip**: bỏ qua dòng không hợp lệ này, ghi nhận lỗi để sửa sau và tiếp tục các dòng khác.
- **Fail fast**: coi lỗi là điều kiện không thể chấp nhận, kết thúc step/job ở trạng thái `FAILED` thay vì tiếp tục xử lý thêm dữ liệu.

Không có lựa chọn nào đúng cho mọi công việc. Nếu job nhập một danh sách sản phẩm cho mục đích tìm kiếm, bỏ qua một số dòng không hợp lệ có thể được phép. Nếu job lập bảng cân đối kế toán hoặc tạo lệnh chuyển tiền, bỏ sót dù một bản ghi có thể làm kết quả không thể sử dụng.

Trong **Spring Batch Core Processing**, quyết định này tác động trực tiếp tới:

1. **Tính đầy đủ và chính xác** của output.
2. **Trạng thái `JobExecution`/`StepExecution`** và cách giám sát.
3. **Transaction, rollback và khả năng restart**.
4. **Chi phí xử lý và năng lực phục hồi** khi data source có nhiều lỗi.
5. **Khả năng giải thích/audit** record nào bị loại và vì sao.
6. **Độ tin cậy của pipeline downstream**: consumer có thể hiểu nhầm job `COMPLETED` nghĩa là 100% input hợp lệ.

Bài học này thuộc nhóm **Quyết định thiết kế**, tập trung vào cách chọn **skip hay fail fast** cho các lỗi tại `ItemReader`, `ItemProcessor` và `ItemWriter`. Các ví dụ hướng đến **Java 17+, Spring Boot 3.x, Spring Batch 5.x, JUnit 5 và JDBC JobRepository**. Với các phiên bản framework khác, đối chiếu API và cấu hình tương ứng.

### Mục tiêu

Sau khi học, bạn có thể:

- Phân biệt `skip`, `filter`, `retry`, `fail fast` và `quarantine`.
- Đưa ra chính sách xử lý dựa trên loại lỗi, mức nghiêm trọng, số lượng và hậu quả nghiệp vụ.
- Dùng `.faultTolerant().skip(...).skipLimit(...)` cùng `.noSkip(...)`, `.retry(...)` đúng ngữ cảnh.
- Hiểu `readSkipCount`, `processSkipCount` và `writeSkipCount`.
- Thiết kế audit cho bản ghi bị skip mà không nhân đôi side effect khi rollback/restart.
- Kiểm thử các ngưỡng skip, trạng thái job, checkpoint, output completeness và quality gate.
- Nhận ra tình huống **không nên tiếp tục** dù Spring Batch có khả năng bỏ qua exception.

---

## 2. Trước tiên: skip, filter, retry và fail fast không giống nhau

### 2.1. Bốn hành vi chính

```text
        ItemReader.read()
                |
                v
        ItemProcessor.process(item)
                |
          +-----+--------------------+
          |                          |
      trả output O                trả null
          |                          |
          v                          v
   ItemWriter.write(chunk)       FILTERED
          |
          +---------- exception ---------+
                                        |
                              Fault-tolerant policy
                                        |
                    +-------------------+----------------+
                    |                   |                |
                  RETRY                SKIP            FAIL
             thử lại có hạn      bỏ qua có hạn      kết thúc lỗi
                    |                   |                |
                    v                   v                v
                success?          vẫn xử lý        Step FAILED
                    |              item khác
                    v
               tiếp tục
```

**Filter** là quyết định nghiệp vụ trong processor: trả `null` để một item không đi tới writer. Nó không cần exception và không tiêu thụ `skipLimit`.

**Skip** là cơ chế fault tolerance khi reader, processor hoặc writer ném một exception được cấu hình là *skippable*. Spring Batch có thể bỏ qua một item lỗi và tiếp tục, trong hạn mức đã định.

**Retry** là thử lại thao tác sau lỗi có thể phục hồi, như deadlock hoặc lỗi tạm thời của tài nguyên. Retry có thể thành công, hoặc hết retry budget và làm step fail/đi tới chính sách recovery khác.

**Fail fast** là dừng khi phát hiện một lỗi được xác định là không thể chấp nhận hoặc tiếp tục xử lý sẽ gây nguy hiểm. Trong thực tế, “fail fast” có thể nghĩa là không skip và không retry loại lỗi đó; framework sẽ xử lý rollback và đưa step tới `FAILED` khi exception không được phục hồi.

### 2.2. Ví dụ một input feed

| Input | Tình huống | Chính sách có thể chọn | Giải thích |
| --- | --- | --- | --- |
| Đơn `CANCELLED` | Dữ liệu hợp lệ nhưng không nằm trong phạm vi import | **Filter** | Không phải chất lượng dữ liệu kém |
| Ngày `2026-99-99` | Lỗi định dạng một dòng | **Skip + quarantine**, nếu cho phép | Có thể cách ly dòng sai |
| Amount bằng 0 | Vi phạm business rule từng item | Skip hoặc fail fast, tùy hợp đồng | Phụ thuộc mức độ nghiêm trọng |
| Thiếu toàn bộ file input | Không có dữ liệu để hoàn thành công việc | **Fail fast** | Không phải lỗi của một dòng |
| Không kết nối được database | Lỗi hạ tầng diện rộng | **Retry có hạn rồi fail** | Skip có thể làm mất cả feed |
| Số tài khoản đích không hợp lệ trong lệnh chi tiền | Vi phạm nghiệp vụ nghiêm trọng | **Fail fast / manual review** | Không được âm thầm bỏ giao dịch |
| Order không thuộc tenant đang nhập | Dữ liệu lệch phạm vi hoặc rò rỉ dữ liệu | Thường **fail fast và điều tra** | Có thể là lỗi ranh giới bảo mật |
| Một vài sản phẩm thiếu mô tả tùy chọn | Không đạt yêu cầu hiển thị | Filter/skip hoặc gán default theo policy | Cần quyết định sản phẩm có được công bố không |
| PostgreSQL deadlock | Transaction bị xung đột tạm thời | **Retry transaction** | Không phải dữ liệu lỗi cố định |
| SQL sai tên cột sau deploy | Lỗi code/schema | **Fail fast** | Retry/skip không sửa được |

Bảng trên là định hướng, không thay thế chính sách nghiệp vụ. Cùng một `amount=0` có thể là data error cho invoice nhưng hợp lệ với voucher hoặc sự kiện miễn phí.

### 2.3. Câu hỏi quan trọng nhất

**Nếu bỏ bản ghi này mà job vẫn báo `COMPLETED`, người tiêu thụ output có chấp nhận thiếu nó không?**

Nếu câu trả lời là “không”, mặc định nên **fail fast** hoặc **giữ dữ liệu trong staging/quarantine rồi chặn publish**. Bật skip chỉ vì Spring Batch hỗ trợ sẽ khiến một pipeline có vẻ thành công nhưng dữ liệu đã bị rút bớt.

---

## 3. Chọn skip hay fail fast bằng một khung quyết định

### 3.1. Năm tiêu chí cần xem xét

1. **Phạm vi lỗi:** một item riêng lẻ, cả file, cả partition hay toàn hệ thống?
2. **Tính độc lập:** có thể xử lý item khác mà không phụ thuộc item lỗi không?
3. **Ảnh hưởng nghiệp vụ:** bỏ item có làm sai số dư, tổng tiền, kết quả quyết toán, sequence hoặc quan hệ giữa các bản ghi không?
4. **Khả năng phục hồi:** lỗi tự hết khi retry, cần sửa dữ liệu hay không thể tự khắc phục?
5. **Khả năng giải trình:** có cần lưu record lỗi, rule code, nguồn và trạng thái remediation không?

Nếu không thể phân lập lỗi, việc skip thường không phù hợp.

### 3.2. Bảng quyết định theo loại lỗi

| Nhóm lỗi | Đặc điểm | Hướng xử lý ưu tiên |
| --- | --- | --- |
| Bản ghi lỗi cố định, độc lập, có thể loại theo hợp đồng | Một dòng malformed; các dòng khác không bị ảnh hưởng | Skip có giới hạn và lưu reject |
| Bản ghi hợp lệ nhưng ngoài phạm vi | Status không thuộc kỳ report | Filter có chủ đích |
| Tài nguyên tạm thời không khả dụng | DB timeout, HTTP 503, deadlock | Retry có backoff; hết budget thì fail/recover |
| Sai cấu hình/hệ thống | Thiếu schema, sai credentials, bug mapping toàn bộ file | Fail fast; sửa rồi restart |
| Bất biến bắt buộc của nghiệp vụ | Tổng tiền không khớp, thiếu transaction quan trọng | Fail fast hoặc quality gate ngăn publish |
| Lỗi liên quan security/tenant | Dữ liệu sai quyền sở hữu, chéo tenant | Fail fast và điều tra |
| Lỗi độc lập nhưng nhiều đến mức output vô nghĩa | 30% feed bị invalid | Chặn bằng skip threshold / quality gate |
| Không chắc side effect đã commit | Timeout sát thời điểm commit, external API không rõ kết quả | Reconciliation trước khi replay; không skip mù |
| Có yêu cầu audit mọi input | Cần accepted/rejected/review record tương ứng | Decision routing + quarantine; không chỉ skip |

### 3.3. Luồng quyết định

```text
Lỗi xảy ra?
     |
     v
Có phải item không thuộc phạm vi theo policy?
     | có
     +----> FILTER, ghi metric phù hợp
     |
     v
Có khả năng tự phục hồi qua retry an toàn?
     | có
     +----> RETRY có giới hạn + backoff
     |          |
     |          +-- success -> tiếp tục
     |          +-- exhausted -> xem severity / fail
     |
     v
Có thể cách ly đúng một item?
     | không
     +----> FAIL FAST hoặc tạm dừng/recover hạ tầng
     |
     v
Bỏ item có làm sai bất biến nghiệp vụ?
     | có
     +----> FAIL FAST / QUARANTINE + BLOCK PUBLISH
     |
     v
Có audit và ngân sách lỗi được phê duyệt?
     | không
     +----> FAIL FAST
     |
     v
SKIP + persist reject + quality gate
     |
     +-- vượt ngưỡng --> FAIL hoặc BLOCK PUBLISH
```

Đây là công cụ để thống nhất chính sách, không phải luồng xử lý nội bộ mặc định của Spring Batch.

---

## 4. Các trạng thái và phép đếm skip trong Spring Batch

### 4.1. Định nghĩa `StepExecution` counters

Spring Batch theo dõi các loại skip riêng:

- `getReadSkipCount()`: item không được đọc hoàn chỉnh do lỗi được skip tại reader.
- `getProcessSkipCount()`: item bị lỗi ở processor và được skip.
- `getWriteSkipCount()`: item bị lỗi ở writer và được skip.
- `getSkipCount()`: tổng các loại skip theo semantics của step.
- `getFilterCount()`: item processor trả `null`, khác với skip.
- `getReadCount()` và `getWriteCount()`: số item đọc/ghi theo bộ đếm của Spring Batch.
- `getRollbackCount()` / `getCommitCount()`: số rollback/commit; hữu ích để đánh giá tác động lỗi.

Ví dụ:

```java
StepExecution step = ...;

long readSkips = step.getReadSkipCount();
long processSkips = step.getProcessSkipCount();
long writeSkips = step.getWriteSkipCount();
long totalSkips = step.getSkipCount();
long filtered = step.getFilterCount();
long commits = step.getCommitCount();
long rollbacks = step.getRollbackCount();
```

Cần nhớ: `readCount` không nhất thiết bằng tổng số lần gọi Java `read()` khi reader có EOF/retry hoặc rollback. `writeCount` cũng không thay thế phép đếm chính thức của dữ liệu đã công bố nếu writer ghi nhiều bảng hoặc hệ thống ngoài.

### 4.2. `skipLimit` là ngân sách tổng

Ví dụ:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Trong một step execution, tối đa **10 skips** được chấp nhận theo policy. Khi gặp skip đủ điều kiện **thứ 11**, step sẽ vượt ngưỡng và thất bại. Hạn mức này tính chung các loại skip được framework theo dõi; nó không phải “10 read errors + 10 process errors + 10 write errors”.

Nếu cấu hình `skipLimit(0)`, không item nào được phép bỏ qua theo lỗi skippable. Trong nhiều trường hợp, cách diễn đạt rõ hơn là không cấu hình skip cho lỗi cần fail fast.

### 4.3. Một job `COMPLETED` vẫn có thể có skips

```text
JobExecution status: COMPLETED
StepExecution:
  readCount:        10.000
  filterCount:         100
  readSkipCount:         3
  processSkipCount:     10
  writeSkipCount:        2
  writeCount:         9.885
  skipCount:            15
```

Bộ số trên là ví dụ minh họa cho một scenario không có các semantics đặc biệt khác. **`COMPLETED` chỉ nói rằng step đã kết thúc theo chính sách lỗi và flow hiện tại**, không khẳng định output chứa đủ 100% raw input. Vì vậy dashboard nên hiển thị **completed with skips/rejects** như một tín hiệu khác với completed without data-quality issues.

### 4.4. `BatchStatus` và `ExitStatus`

`BatchStatus` phản ánh trạng thái vòng đời (`COMPLETED`, `FAILED`, `STOPPED`...), còn `ExitStatus` có thể chứa ý nghĩa nghiệp vụ/flow riêng, ví dụ “COMPLETED_WITH_SKIPS”.

Nếu muốn đánh dấu kết quả có warnings, có thể đặt `ExitStatus` tùy biến từ `StepExecutionListener` và định nghĩa transitions rõ trong job flow. Nhưng **đừng đánh đồng custom ExitStatus với việc đổi `BatchStatus`**: job có thể có `BatchStatus.COMPLETED` và custom exit code. Hệ thống nhận kết quả phải biết ý nghĩa của cả hai.

---

## 5. Cấu hình fault-tolerant step có giới hạn skip

### 5.1. Mô hình dữ liệu

Giả sử job đọc đơn hàng CSV, loại dòng `CANCELLED`, từ chối amount không hợp lệ, sau đó ghi accepted orders.

```java
import java.math.BigDecimal;

public record RawOrder(
    String externalId,
    BigDecimal amount,
    String status
) {}

public record AcceptedOrder(
    String externalId,
    BigDecimal amount
) {}
```

Ngoại lệ cho lỗi dữ liệu từng item:

```java
public class InvalidOrderException extends RuntimeException {

    private final String ruleCode;
    private final String externalId;

    public InvalidOrderException(
            String ruleCode,
            String externalId,
            String message) {

        super(message);
        this.ruleCode = ruleCode;
        this.externalId = externalId;
    }

    public String ruleCode() {
        return ruleCode;
    }

    public String externalId() {
        return externalId;
    }
}
```

Ngoại lệ cho lỗi nghiêm trọng không được skip:

```java
public class CriticalOrderException extends RuntimeException {

    public CriticalOrderException(String message) {
        super(message);
    }
}
```

### 5.2. Processor phân biệt filter, invalid và critical

```java
import org.springframework.batch.item.ItemProcessor;

public class OrderValidationProcessor
        implements ItemProcessor<RawOrder, AcceptedOrder> {

    @Override
    public AcceptedOrder process(RawOrder item) {
        if (item == null) {
            throw new CriticalOrderException(
                "Reader returned an unexpected null item");
        }

        if ("CANCELLED".equals(item.status())) {
            // Hợp lệ nhưng không nằm trong tập cần ghi.
            return null;
        }

        if (item.externalId() == null ||
            item.externalId().isBlank()) {

            throw new InvalidOrderException(
                "ORDER_ID_REQUIRED",
                item.externalId(),
                "Order ID is missing");
        }

        if (item.amount() == null ||
            item.amount().signum() <= 0) {

            throw new InvalidOrderException(
                "AMOUNT_MUST_BE_POSITIVE",
                item.externalId(),
                "Amount must be positive");
        }

        if ("CROSS_TENANT".equals(item.status())) {
            // Có thể là ranh giới quyền truy cập bị phá vỡ.
            throw new CriticalOrderException(
                "Cross-tenant data detected");
        }

        if (!"READY".equals(item.status())) {
            throw new InvalidOrderException(
                "STATUS_UNSUPPORTED",
                item.externalId(),
                "Unsupported order status");
        }

        return new AcceptedOrder(
            item.externalId().trim(),
            item.amount());
    }
}
```

Trong ví dụ, `CANCELLED` được filter trước khi validate amount. Đó là quyết định nghiệp vụ: các đơn đã hủy không đi vào tập dữ liệu cần kiểm tra amount của job này. Nếu bài toán yêu cầu thống kê chất lượng **toàn bộ nguồn**, nên validate trước khi filter hoặc có luồng đánh giá riêng.

Để dữ liệu có thể được retry/restart, processor nên thuần hàm: cùng input và rule snapshot cho cùng kết quả, không gửi email hoặc ghi DB ngoài transaction chỉ để đánh dấu “đã process”.

### 5.3. Cấu hình `StepBuilder`

Ví dụ các bean reader, processor, writer và transaction manager đã tồn tại:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> reader,
        ItemProcessor<RawOrder, AcceptedOrder> processor,
        ItemWriter<AcceptedOrder> writer,
        SkipListener<RawOrder, AcceptedOrder> skipListener) {

    ExponentialBackOffPolicy backoff =
        new ExponentialBackOffPolicy();
    backoff.setInitialInterval(250L);
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(2_000L);

    return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, AcceptedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        // Chỉ lỗi record độc lập mới được xem là skippable.
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        // CriticalOrderException KHÔNG được skip.
        .noSkip(CriticalOrderException.class)
        // Retry lỗi tài nguyên tạm; không skip DB outage.
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backoff)
        .listener(skipListener)
        .build();
}
```

**Ý nghĩa:**

- `.faultTolerant()` chuyển sang builder hỗ trợ skip/retry.
- `.skip(FlatFileParseException.class)` có thể phù hợp khi lỗi parse được xác định là lỗi của **một dòng**; không có nghĩa mọi lỗi đọc file đều skippable.
- `.skip(InvalidOrderException.class)` cho phép bỏ item có violation đã được nghiệp vụ phê duyệt.
- `.skipLimit(10)` là giới hạn skip tổng trong step execution, không phải giới hạn một loại exception.
- `.noSkip(CriticalOrderException.class)` minh thị rằng lỗi nghiêm trọng phải ngăn tiếp tục, đặc biệt hữu ích khi có policy skip superclass ở nơi khác.
- `.retry(TransientDataAccessException.class)` thử lại một số lỗi tạm được phân loại. Mất kết nối database thực tế có thể được bọc thành exception nằm ngoài nhóm này; cần xác minh exception translator/driver trước khi chọn classifier.
- `.retryLimit(3)` giới hạn attempts theo semantics retry của Spring Batch.
- `.listener(skipListener)` cho phép quan sát record bị skip; persistence của audit vẫn cần thiết kế transaction/idempotency.

Không đặt `skip(Exception.class)` chỉ để cho job “chạy hết file”, vì nó có thể che lỗi logic, lỗi kết nối, cấu hình hoặc dữ liệu quan trọng.

### 5.4. `noSkip` không thay thế đánh giá hậu quả

Một hệ thống có thể định nghĩa thêm các exception:

```java
.noSkip(CriticalOrderException.class)
.noSkip(SecurityException.class)
```

Tuy nhiên, lỗi hạ tầng như `DataAccessException` có thể xuất hiện ở nhiều lớp và được bọc khác nhau. Không chỉ dựa vào danh sách class mà bỏ qua nguyên nhân gốc; cần test lỗi thực tế của reader, processor, writer và commit.

---

## 6. Quy tắc skip ở reader, processor và writer khác nhau

### 6.1. Skip tại reader

Với `FlatFileItemReader`, một dòng sai định dạng có thể ném `FlatFileParseException`, chứa thông tin về dòng gây lỗi. Nếu reader đã tiến qua dòng đó theo contract và việc bỏ qua dòng không ảnh hưởng các dòng khác, skip có thể hợp lý.

Ví dụ:

```text
file.csv
1: ORDER-1,100,READY
2: ORDER-2,abc,READY     <- không parse được amount
3: ORDER-3,200,READY

Policy:
  line 2 -> read skip, ghi reject
  line 1 + line 3 -> tiếp tục xử lý
```

Không nên skip mọi exception ở reader. File không tồn tại, schema header sai, database cursor bị hỏng hoặc I/O lỗi có thể ảnh hưởng cả luồng. Nếu reader không đảm bảo tiến lên sau lỗi, việc retry/skip mù có nguy cơ lặp vô hạn hoặc mất dữ liệu.

**Điểm kỹ thuật:** ở read skip, listener có thể có exception và thông tin dòng do `FlatFileParseException` cung cấp, nhưng **không nhất thiết có object `RawOrder` hoàn chỉnh** vì parsing đã thất bại.

### 6.2. Skip tại processor

Processor đã nhận được item nhưng business rule không chấp nhận. Có thể dùng một exception chuyên biệt:

```java
if (item.amount().signum() <= 0) {
    throw new InvalidOrderException(
        "AMOUNT_MUST_BE_POSITIVE",
        item.externalId(),
        "Invalid amount");
}
```

Nếu policy cho skip, item không đi vào writer và `processSkipCount` tăng theo framework. Nếu contract yêu cầu ghi reject record, dùng listener hoặc decision-routing writer có persistence được kiểm soát.

Processor là nơi thích hợp để phân loại lỗi dữ liệu **theo từng item**; các quy tắc về tổng tiền, số lượng record, trùng key xuyên nhiều partition hoặc integrity toàn batch thường cần staging/DB constraint/quality gate khác.

### 6.3. Skip tại writer là trường hợp nguy hiểm hơn

Writer trong chunk-oriented step nhận **một chunk**:

```java
void write(Chunk<? extends AcceptedOrder> items)
    throws Exception;
```

Một lỗi ở `write(chunk)` có thể liên quan:

- Một item riêng lẻ vi phạm dữ liệu đích.
- Constraint toàn batch hoặc nhiều items.
- Mất connection/timeout/lock.
- Transaction commit không rõ đã thành công hay chưa.
- API ngoài không tham gia transaction.
- Bug trong serializer hoặc SQL writer.

Spring Batch fault-tolerant processing có thể dùng cơ chế retry/rollback và thử xác định item lỗi trong quá trình xử lý write skip. **Không mặc định mọi writer đều hỗ trợ cô lập một item an toàn**. Nếu writer đã thực hiện side effect ngoài transaction trước khi ném exception, việc gọi lại có thể nhân đôi thao tác.

Ví dụ:

```text
Chunk: [A, B, C, D]
Writer:
  insert A -> thành công
  insert B -> thành công
  insert C -> DuplicateKeyException
  throw
```

Nếu A/B đã auto-commit hoặc được gửi qua API ngoài, write retry có thể tạo lại chúng. Nếu JDBC writer tham gia **transaction chunk** và toàn bộ transaction rollback đúng, cơ chế cô lập item có cơ sở an toàn hơn.

### 6.4. Vì sao không skip mọi `DuplicateKeyException`?

Một duplicate có thể là:

- Item đã được import thành công ở lần chạy trước, writer idempotency chưa được xử lý.
- Một lỗi dữ liệu nguồn riêng lẻ được phép đưa vào reject.
- Vi phạm business invariant quan trọng.
- Dấu hiệu job bị launch trùng.
- Kết quả mơ hồ sau commit timeout.
- Lỗi thiết kế unique constraint.

Nếu bỏ qua tất cả duplicate keys, job có thể “hoàn thành” nhưng che vấn đề dữ liệu và mất khả năng đối soát. Xử lý duplicate nên dựa trên **business key** và chính sách update/ignore/reject/fail; khi cần idempotency, cân nhắc UPSERT hoặc unique key phù hợp, không tự coi database constraint là lỗi skippable.

---

## 7. Kiểu ngoại lệ nào nên skip và kiểu nào không?

### 7.1. Phân lớp exception theo nghĩa nghiệp vụ

Thay vì ném `RuntimeException` chung cho mọi lỗi, có thể xây các exception cụ thể:

```java
public abstract class ImportException extends RuntimeException {
    protected ImportException(String message) {
        super(message);
    }
}

public final class SkippableRecordException
        extends ImportException {

    private final String ruleCode;
    private final String recordId;

    public SkippableRecordException(
            String ruleCode,
            String recordId,
            String message) {
        super(message);
        this.ruleCode = ruleCode;
        this.recordId = recordId;
    }

    public String getRuleCode() {
        return ruleCode;
    }

    public String getRecordId() {
        return recordId;
    }
}

public final class FatalBatchException
        extends ImportException {

    public FatalBatchException(String message) {
        super(message);
    }
}
```

Step có thể:

```java
.skip(SkippableRecordException.class)
.noSkip(FatalBatchException.class)
.skipLimit(10)
```

Lợi ích của class riêng: chính sách skip rõ, test và log dễ gắn rule code, giảm nguy cơ bắt nhầm lỗi kỹ thuật.

### 7.2. Tránh một exception vừa có thể skip vừa có thể fatal

Nếu một processor ném `BusinessRuleViolationException` cho cả “thiếu mô tả” và “amount bất hợp lệ trong giao dịch thanh toán”, việc `skip(BusinessRuleViolationException.class)` vô tình bỏ qua cả lỗi critical.

Có hai cách phổ biến:

1. Tạo subclass rõ semantics: `SkippableRecordException` và `CriticalBusinessViolationException`.
2. Dùng `SkipPolicy` tùy biến đánh giá rule code/nhóm severity và số skip.

Chỉ dùng cách thứ hai khi phân loại cần dựa vào nhiều thuộc tính; class riêng thường dễ quan sát và kiểm thử hơn.

### 7.3. Lỗi theo giai đoạn

| Giai đoạn | Có thể skip | Thường fail fast / recover |
| --- | --- | --- |
| Read file | Một dòng CSV sai được cách ly và reader tiếp tục được | File mất, lỗi encoding toàn file, header/schema sai |
| Read JDBC | Một row được xác định riêng là malformed và reader có cơ chế tiến lên an toàn | Mất connection/cursor, SQL sai, transaction không khả dụng |
| Process | Vi phạm rule độc lập, được phép thiếu output | Lỗi quyền tenant, tổng tiền quan trọng, bug, reference data unavailable |
| Write JDBC | Item riêng lẻ rejectable và transaction cô lập được | Mất DB, commit ambiguous, constraint toàn cục, lỗi SQL |
| Write API | Chỉ khi API/writer hỗ trợ xác định item và idempotency rõ | Thanh toán, email không idempotent, network timeout không rõ kết quả |
| Metadata | Không coi lỗi `JobRepository` là item skippable | Không persist checkpoint/execution status |

**Thứ tự quyết định:** phân tích khả năng cô lập + business impact, rồi mới chọn exception class trong `StepBuilder`. Không làm ngược lại.

---

## 8. Khi nào cần `SkipPolicy` tùy biến?

`.skip(MyException.class).skipLimit(n)` đủ cho các rule đơn giản. Khi cần phân loại bằng rule code hoặc loại lỗi và nhiều hạn mức khác nhau, có thể định nghĩa `SkipPolicy`.

### 8.1. Ví dụ đánh giá exception và tổng skip

```java
import org.springframework.batch.core.step.skip.SkipPolicy;

public final class BusinessRecordSkipPolicy
        implements SkipPolicy {

    private final long maxSkippedRecords;

    public BusinessRecordSkipPolicy(long maxSkippedRecords) {
        this.maxSkippedRecords = maxSkippedRecords;
    }

    @Override
    public boolean shouldSkip(
            Throwable throwable,
            long skipCount) {

        // Spring Batch có thể gọi policy với giá trị đặc biệt
        // để kiểm tra khả năng skippable; tránh phụ thuộc
        // vào số skip dương trong trường hợp probe.
        if (!(throwable instanceof SkippableRecordException)) {
            return false;
        }

        return skipCount >= 0
            ? skipCount < maxSkippedRecords
            : true;
    }
}
```

Trong Spring Batch 5.x, `SkipPolicy.shouldSkip(Throwable, long)` nhận số skip đã có; framework có thể dùng giá trị âm (chẳng hạn để probe capability) tùy ngữ cảnh. Chính sách tùy biến phải xử lý loại lỗi độc lập với trạng thái probe.

Cấu hình:

```java
.faultTolerant()
.skipPolicy(new BusinessRecordSkipPolicy(10))
```

Với policy dạng này, item thứ 11 có lỗi thuộc nhóm skippable bị từ chối. Trong project thực, phải test cả read/process/write và trường hợp policy được gọi để probe.

**Đừng dùng một `SkipPolicy` singleton chứa bộ đếm mutable để kiểm soát skip**. Khi nhiều executions chạy song song, state có thể bị trộn. Tham số `skipCount` được framework cung cấp phù hợp hơn cho hạn mức cơ bản. Nếu muốn quota khác nhau theo tenant/file/rule, cần thiết kế theo execution context và dữ liệu được quản lý bền vững.

### 8.2. Hạn mức theo rule code

Yêu cầu: tối đa 10 lỗi mô tả tùy chọn nhưng **không được skip bất kỳ lỗi `PAYMENT_ACCOUNT_MISMATCH`**.

Một policy có thể kiểm tra:

```java
if (throwable instanceof SkippableRecordException ex) {
    if ("PAYMENT_ACCOUNT_MISMATCH".equals(ex.getRuleCode())) {
        return false;
    }
    return skipCount < 10;
}
return false;
```

Nếu cần quota **riêng cho từng rule**, một biến `skipCount` tổng không đủ để tính count từng code. Khi đó nên có decision/quarantine ledger hoặc pre-validation step tính quality metrics, rồi áp dụng quality gate tường minh thay vì giữ nhiều counter mutable trong processor.

### 8.3. Skip policy không thay thế toàn bộ lỗi business

Một số loại dữ liệu cần giữ record reject để vận hành sửa sau. Nếu chỉ trả `true` từ `SkipPolicy`, Spring Batch loại item khỏi output; policy không tự lưu reject payload hoặc tạo ticket xử lý. Persistence/audit phải được thiết kế riêng.

---

## 9. Khi nào fail fast là lựa chọn tốt hơn?

### 9.1. Lỗi phá bất biến toàn batch

Ví dụ job kết chuyển tài chính phải đảm bảo:

\[
\sum \mathrm{debit} = \sum \mathrm{credit}
\]

Nếu một giao dịch debit bị bỏ qua nhưng credit tương ứng vẫn được ghi, báo cáo có thể lệch. Một record lỗi riêng lẻ nhưng **hậu quả lan sang các item khác** không phù hợp để skip đơn thuần.

Tương tự:

- Dữ liệu yêu cầu sequence đầy đủ.
- Một snapshot phải có số record khớp manifest.
- Một bảng reference phải tải hoàn chỉnh trước khi processor dùng.
- Hóa đơn và dòng chi tiết phải cùng một phạm vi atomic publication.
- Một batch xuất dữ liệu cho đối tác yêu cầu “all records or none”.

Với tình huống này, fail fast hoặc staging + gate giúp tránh công bố kết quả sai.

### 9.2. Lỗi cấu hình hoặc code

Nếu mọi dòng đều ném `NullPointerException` do bug hay `BadSqlGrammarException` vì chưa migrate schema, skip càng lâu càng làm mất dữ liệu. Cần fail fast để buộc sửa nguyên nhân.

Không cấu hình:

```java
.skip(Exception.class)
.skipLimit(Integer.MAX_VALUE)
```

Chính sách trên dễ che lỗi code/hạ tầng và tạo một execution `COMPLETED` với output gần như rỗng.

### 9.3. Lỗi bảo mật

Một record thuộc tenant khác xuất hiện trong feed đang xử lý có thể phản ánh sai boundary truy cập hoặc sai routing từ nguồn. Tùy hệ thống, đây là security incident cần dừng job ngay và điều tra, không chỉ “skip một record và tiếp tục”.

### 9.4. Tài nguyên không đáng tin cậy

Nếu DB mất connection ở writer, việc skip chunk/items chỉ để tiếp tục là nguy hiểm: lỗi có thể ảnh hưởng toàn bộ output, commit không rõ trạng thái hoặc `JobRepository` không persist checkpoint. Cách thường hợp lý là retry có hạn rồi fail job, sau đó restart khi database ổn định và reconciliation đã hoàn tất.

### 9.5. Fail fast không tự động rollback toàn job

Một điều dễ hiểu nhầm:

```text
Chunk size = 100

Chunk 1: COMMIT
Chunk 2: COMMIT
Chunk 3: COMMIT
Chunk 4: phát hiện critical error -> ROLLBACK / FAILED
```

Job `FAILED` **không tự rollback ba chunk đã commit**. Fail fast giúp không xử lý tiếp, nhưng những output đã ghi cần được quản lý. Nếu nghiệp vụ đòi công bố toàn bộ hoặc không công bố gì, phải thiết kế **staging → quality gate → publish** hoặc cơ chế transaction/version phù hợp, không trông chờ một transaction xuyên toàn bộ job.

---

## 10. Giải pháp trung gian: quarantine và quality gate

Nhiều hệ thống không nên chọn giữa “bỏ mất record” và “dừng mọi thứ”. Giải pháp thứ ba là **chấp nhận xử lý phần hợp lệ nhưng giữ dấu vết bất hợp lệ và chỉ công bố khi đạt chuẩn**.

### 10.1. Mô hình pipeline

```text
Raw input
    |
    v
Parse + normalize
    |
    v
Validate / business rules
    |
    +----------------+------------------+
    |                |                  |
    v                v                  v
 ACCEPTED         REJECTED         NEEDS_REVIEW
    |                |                  |
    v                v                  v
 staging_ok      staging_reject     review_queue
    |                |                  |
    +----------------+------------------+
                     |
                     v
              Data Quality Gate
                  |
              +---+----+
              |        |
            PASS      FAIL
              |        |
              v        v
         Publish     Hold output,
         accepted    remediate input
```

Ở đây, một record bị reject không biến mất; nó có rule code, source identity, rule version và trạng thái xử lý sau đó.

### 10.2. Decision object thay cho exception

Java 17 có thể biểu diễn quyết định bằng sealed types:

```java
public sealed interface OrderDecision
        permits AcceptedDecision, RejectedDecision { }

public record AcceptedDecision(AcceptedOrder order)
        implements OrderDecision { }

public record RejectedDecision(
        String externalId,
        String ruleCode,
        String ruleVersion)
        implements OrderDecision { }
```

Processor:

```java
import org.springframework.batch.item.ItemProcessor;

public final class OrderDecisionProcessor
        implements ItemProcessor<RawOrder, OrderDecision> {

    @Override
    public OrderDecision process(RawOrder row) {
        if (row.amount() == null ||
            row.amount().signum() <= 0) {
            return new RejectedDecision(
                row.externalId(),
                "AMOUNT_MUST_BE_POSITIVE",
                "rules-2026-11");
        }

        return new AcceptedDecision(new AcceptedOrder(
            row.externalId(), row.amount()));
    }
}
```

Writer có thể chia chunk theo decision và ghi accepted/rejected vào các bảng staging. Khi **cùng datasource/transaction manager**, hai nhóm ghi có thể tham gia cùng chunk transaction. Nếu writer xuất vào các hệ thống khác nhau, cần idempotency/reconciliation và không được giả định atomicity.

Trong cách này, rejected item **không tiêu thụ `skipLimit`** vì processor trả object. Vì vậy, quality gate phải tự tính số/tỷ lệ rejects theo hợp đồng.

### 10.3. Data quality gate theo tỷ lệ

Ví dụ một ngày có 20.000 record eligible, trong đó 130 bị reject. Chính sách cho phép tỷ lệ reject không quá **0,5%**:

\[
\text{rejectRate} = \frac{130}{20\,000} \times 100\% = 0.65\%
\]

Tỷ lệ vượt ngưỡng, do đó gate phải fail hoặc giữ trạng thái `HOLD_FOR_REVIEW`, không publish output vào bảng phục vụ downstream.

Nếu raw input gồm 22.000 record nhưng 2.000 record hợp lệ nằm ngoài phạm vi thì mẫu số **eligible=20.000** khác với mẫu số toàn bộ raw input. Hợp đồng phải nêu rõ mẫu số để KPI không bị giải thích sai.

### 10.4. Hạn mức tuyệt đối và hạn mức tỷ lệ

| Chính sách | Ví dụ | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| `skipLimit(20)` | Tối đa 20 record lỗi | Dễ cấu hình, chặn nhanh | Không tương xứng giữa file 100 và 1 triệu dòng |
| Reject rate ≤ 0,5% | Tối đa 0,5% eligible | Phù hợp volume thay đổi | Cần đếm unique records và xác định mẫu số |
| Critical rules = 0 | Không cho bất kỳ rule critical nào | Bảo vệ bất biến | Có thể làm thất bại cả feed vì một lỗi |
| Kết hợp nhiều ngưỡng | ≤20 errors, ≤0,5%, critical=0 | Linh hoạt | Cần gate/ledger và test chi tiết |
| Manual approval | Kỳ dữ liệu nhạy cảm | Kiểm soát tốt | Tốn thời gian vận hành |

`skipLimit` của framework chỉ cung cấp **ngân sách skip tổng**, không tự cung cấp tỷ lệ lỗi theo từng rule/tenant. Nếu yêu cầu vượt chức năng đó, xây quality gate tường minh.

---

## 11. Audit record bị skip: `SkipListener` và giới hạn

### 11.1. Các callback

Spring Batch định nghĩa `SkipListener<I,O>` với ba loại sự kiện:

```java
import org.springframework.batch.core.SkipListener;

public final class ImportSkipListener
        implements SkipListener<RawOrder, AcceptedOrder> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Reader parse lỗi; có thể chưa tạo được RawOrder.
    }

    @Override
    public void onSkipInProcess(
            RawOrder item,
            Throwable throwable) {
        // Item đã đọc; processor không tạo output.
    }

    @Override
    public void onSkipInWrite(
            AcceptedOrder item,
            Throwable throwable) {
        // Writer loại một item theo chính sách fault tolerance.
    }
}
```

Với read errors, thông tin raw line có thể nằm trong `FlatFileParseException`. Với process errors, có input item; với write errors, có output item mà writer cố ghi.

### 11.2. Một mẫu ghi nhận rule code

```java
@Override
public void onSkipInProcess(
        RawOrder item, Throwable throwable) {

    if (throwable instanceof InvalidOrderException invalid) {
        // Ghi structured log hoặc đưa record vào
        // cơ chế reject/audit phù hợp transaction.
        String code = invalid.ruleCode();
        String key = invalid.externalId();
    }
}
```

Không nên đưa raw customer data, token hoặc payment details vào log. Rule code và source record identifier cần được bảo vệ theo chính sách dữ liệu.

### 11.3. Listener có bảo đảm exactly-once không?

Spring Batch thiết kế skip callbacks để giảm việc gọi lặp trong flow bình thường và gọi ở thời điểm liên quan commit. Tuy nhiên, **không được suy ra** rằng một HTTP request, email hay message gửi trong listener tự trở thành exactly-once với JDBC chunk transaction.

Ví dụ:

```text
onSkipInProcess(item A):
  gửi HTTP "reject A" -> thành công

Chunk transaction sau đó rollback:
  database chưa commit accepted records

Retry/restart:
  có thể cần xử lý lại A
```

HTTP call đã gửi không tự rollback. Nếu yêu cầu audit bền vững và không trùng, nên dùng:

- Bảng reject có unique key theo `sourceRecordId + ruleCode + businessPeriod`.
- Ghi vào datasource cùng transaction chunk khi có thể.
- Transactional outbox nếu cần phát event sau commit.
- Reconciliation khi metadata và nghiệp vụ dùng hai datasource.

Một listener chỉ tăng counter in-memory cũng có thể đếm *attempts* khi retry, không nhất thiết là unique rejected records.

---

## 12. Retry và skip cùng xuất hiện: xác định precedence bằng policy

### 12.1. Có lỗi nên retry trước khi fail

Ví dụ database deadlock có thể tạm thời. Mục tiêu là thử lại transaction, không bỏ một đơn hàng:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Cần chọn exception classes đủ chặt. Một số lỗi mất connection không thuộc `TransientDataAccessException` theo wrapper thực tế; phải kiểm tra exception của driver và ngữ cảnh read/write/commit.

### 12.2. Không retry business rule sai cố định

Một order có amount âm sẽ không tự trở thành hợp lệ sau khi retry ngay với cùng input và rule snapshot. Cấu hình `retry(InvalidOrderException.class)` có thể khiến framework lặp lại việc đánh giá không cần thiết rồi cuối cùng vẫn phải skip/fail.

Nếu business reference data có thể thay đổi, quyết định retry nên dựa vào **tính chất của lỗi tham chiếu** (service unavailable) thay vì retry lỗi validation đã được xác định.

### 12.3. Lỗi có thể vừa thuộc nhóm retry và nhóm skip

Tránh cấu hình cùng một nhóm exception quá rộng cho cả retry và skip mà không có quyết định rõ sau khi retry exhausted. Semantics thực tế phụ thuộc các retry/skip policies và phase read/process/write; cần test ca cụ thể, đặc biệt writer rollback và classifier nested exceptions.

Nếu yêu cầu “retry 3 lần, nếu vẫn lỗi thì dừng cả job”, **không cấu hình skip cho lỗi đó**. Nếu yêu cầu “retry tối đa 3 lần, sau đó quarantine item riêng lẻ”, cần chứng minh item có thể cô lập và ghi reject an toàn.

### 12.4. Backoff tránh retry storm

Với 20 batch jobs cùng gặp outage, retry ngay lập tức có thể gây hàng nghìn connection attempts. Dùng exponential backoff, jitter khi cần, giới hạn attempts và chuyển sang `FAILED` sau khi hết budget; orchestrator chỉ restart sau khi hạ tầng phục hồi.

Một job đã fail vì database outage phải được xử lý qua cơ chế recovery/restart, không bằng cách thêm `.skip(DataAccessException.class)` để chạy tiếp mà không ghi dữ liệu.

---

## 13. Transaction boundary quyết định giá trị của fail fast

### 13.1. Chunk-oriented processing commit từng phần

```text
Chunk size = 100

Chunk #1: items 1..100   -> COMMIT
Chunk #2: items 101..200 -> COMMIT
Chunk #3: items 201..300 -> critical violation
                             |
                             v
                          ROLLBACK
                          Step FAILED
```

Các chunk trước có thể đã commit. Khi restart, reader dùng checkpoint đã lưu để tiếp tục phần chưa được commit, nếu `ItemStream` và metadata repository được cấu hình đúng.

### 13.2. Skip có thể kéo theo rollback

Khi một lỗi xuất hiện trong processor/writer, fault-tolerant step có thể phải rollback một chunk rồi xử lý lại để xác định item nào có thể bỏ qua. Do đó:

- Số lần gọi `process()` hoặc `write()` có thể lớn hơn số item được ghi cuối.
- Side effect ngoài transaction có thể được lặp.
- Một counter trong processor có thể tăng nhiều lần cho cùng item.
- `StepExecution.getRollbackCount()` có thể tăng dù job cuối `COMPLETED`.
- “Skip đúng 1 item” không nhất thiết có nghĩa chỉ một invocation Java bị lỗi.

Cần thiết kế processor deterministic và writer idempotent, đặc biệt khi dùng mạng hoặc nhiều database.

### 13.3. Commit không rõ kết quả

Một database connection có thể đứt khi client chờ phản hồi `COMMIT`:

```text
Writer sent SQL
    |
    v
Database may have committed
    |
    X  response lost
    |
Client sees timeout
```

Không thể mặc định toàn bộ chunk đã rollback. Nếu writer được gọi lại sau skip/retry/restart, output có thể bị nhân đôi. Với yêu cầu correctness cao, dùng unique business key, idempotency, reconciliation và fail fast khi transaction outcome không xác định.

### 13.4. Metadata DB khác business DB

Nếu `JobRepository` lưu ở DB A, writer ghi ở DB B, hai local transaction managers không tự tạo một distributed transaction:

```text
DB B: business rows COMMITTED
DB A: checkpoint update FAILED
```

Sau restart, reader có thể xử lý lại records đã ghi vào DB B. Skip không sửa được vấn đề này; cần idempotent writer và reconciliation. Tương tự, một fail-fast step không tự xóa business rows đã commit.

---

## 14. Restartability và dữ liệu bị skip

### 14.1. Restart sau lỗi không giống chạy mới

```text
JobInstance #501:
  JobExecution #900 FAILED
      importStep checkpoint đã persist

  JobExecution #901 COMPLETED (restart)
      tiếp tục theo checkpoint
```

Trong Spring Batch 5.x, khi được cấu hình, operator có thể:

```java
Long newId = jobOperator.restart(900L);
```

Operator tạo `JobExecution` mới cho **cùng `JobInstance`**. Điều kiện: metadata còn, job restartable, trạng thái hợp lệ và không có execution khác đang chạy hoặc instance đã completed.

### 14.2. Các item đã skip có tự quay lại khi restart không?

Không nên giả định một item đã skip trong execution trước sẽ tự được đưa vào writer ở restart. Hành vi phụ thuộc state/checkpoint, transaction, vị trí lỗi và thiết kế reader. Nếu một chunk đã commit và record bị skip, reader thường đã tiến qua nó theo checkpoint; việc sửa nguồn sau đó không tự buộc job restart đọc lại record đã bỏ.

Nếu nghiệp vụ cần xử lý lại các rejects, nên xây **remediation/reprocess workflow** từ bảng quarantine hoặc nguồn đã sửa. Không dùng restart như một cách không có hợp đồng để “quét lại mọi item bị bỏ”.

### 14.3. Không tạo `JobInstance` mới bằng timestamp để né skip-limit

Nếu step fail vì vượt `skipLimit(10)`, thêm identifying `runAt=now` để launch instance mới sẽ:

- Bắt đầu từ checkpoint mới hoặc từ đầu theo data source.
- Có thể lặp side effects.
- Bỏ qua dấu hiệu data quality vượt ngưỡng.
- Che nguồn gốc của failed instance cũ.

Quy trình đúng là dừng phát hành, sửa nguồn/policy theo phê duyệt, đánh giá compatibility của checkpoint và quyết định restart/reprocess chính thức.

### 14.4. Quy trình phục hồi khi metadata cũ `STARTED`

Nếu process chết trong khi job chưa ghi được terminal status, repository có thể còn `STARTED`. Không ép sửa `BATCH_JOB_EXECUTION` bằng SQL tùy tiện để restart. Cần xác minh worker đã dừng, transaction output đã commit, state/checkpoint và thực hiện procedure recovery phù hợp phiên bản Spring Batch.

---

## 15. Không nên biến error budget thành dữ liệu không có nguồn gốc

### 15.1. Bộ chỉ số Data Quality

Một job có 10.000 records:

```text
raw rows:            10.000
read skips:               4
successfully read:     9.996
filtered (out of scope): 196
process skips:            8
write skips:              2
accepted written:     9.790  (ví dụ)
```

Các counters minh họa cần được kiểm tra với flow thực tế: filtering, retry, rollback và writer logic có thể thay đổi phép đếm. Một báo cáo vận hành nên ghi rõ **đơn vị item**, **mẫu số** và **điều kiện được xem là accepted**.

### 15.2. Quan sát tuyệt đối và tỷ lệ

Ví dụ:

\[
\text{invalidRate}
=
\frac{\text{unique rejected records}}
{\text{eligible source records}}
\times 100\%
\]

Nếu 5.000 dòng trong file nhỏ có 10 errors (0,2%) nhưng một file 1 triệu dòng có 10 errors (0,001%), cùng `skipLimit(10)` không mô tả cùng mức chất lượng.

Một policy có thể yêu cầu đồng thời:

- Không có lỗi critical.
- Tối đa 100 unique rejected records.
- Tỷ lệ rejected không vượt 0,25%.
- Mọi record bị reject đều có quarantine audit.
- Tổng amount của accepted data được reconcile với nguồn trong phạm vi cho phép.

Khi vượt một điều kiện, không publish dù step import kết thúc về mặt kỹ thuật.

### 15.3. `skipCount` không tự là unique rejected count toàn job

Một item có thể bị xử lý nhiều lần do restart hoặc retries; một source file có thể được nhập lại theo revision; nhiều StepExecutions có thể được tạo. Nếu báo cáo cuối cần đếm **unique source records rejected trong một business period**, nên đếm từ bảng quarantine có unique keys thay vì cộng máy móc các skip counts của mọi executions.

### 15.4. Quality gate sau ingestion

Một flow phổ biến:

```text
importToStagingStep
       |
       v
aggregateDataQualityStep
       |
       +-- PASS -> publishStep
       |
       +-- FAIL -> stop/fail job, hold staging
```

Lưu ý: `importToStagingStep` có thể `COMPLETED` và publish được ngăn lại bởi bước gate, nhưng có dữ liệu staging đã commit. Đó là hành vi **có chủ đích** để điều tra/reprocess, không phải transaction rollback toàn job.

---

## 16. Kiểm thử unit cho decision và processor

### 16.1. Không cần Spring context để test rule đơn giản

```java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderValidationProcessorTest {

    private final OrderValidationProcessor processor =
        new OrderValidationProcessor();

    @Test
    void filtersCancelledOrder() throws Exception {
        RawOrder input = new RawOrder(
            "ORDER-C", new BigDecimal("100.00"), "CANCELLED");

        assertNull(processor.process(input));
    }

    @Test
    void acceptsValidOrder() throws Exception {
        RawOrder input = new RawOrder(
            "ORDER-A", new BigDecimal("125.00"), "READY");

        AcceptedOrder output = processor.process(input);

        assertNotNull(output);
        assertEquals("ORDER-A", output.externalId());
        assertEquals(new BigDecimal("125.00"), output.amount());
    }

    @Test
    void classifiesAmountViolation() {
        RawOrder input = new RawOrder(
            "ORDER-X", BigDecimal.ZERO, "READY");

        InvalidOrderException ex = assertThrows(
            InvalidOrderException.class,
            () -> processor.process(input));

        assertEquals(
            "AMOUNT_MUST_BE_POSITIVE",
            ex.ruleCode());
    }

    @Test
    void criticalCrossTenantViolationCannotBeTreatedAsDataSkip() {
        RawOrder input = new RawOrder(
            "ORDER-S", new BigDecimal("90.00"),
            "CROSS_TENANT");

        assertThrows(
            CriticalOrderException.class,
            () -> processor.process(input));
    }
}
```

Unit test xác nhận processor phân loại đúng nhưng **không chứng minh Spring Batch có skip/fail theo chính sách**. Cần integration test kết hợp `JobRepository`, `StepBuilder`, reader và writer thật hoặc test fixtures.

---

## 17. Integration test: filter một item, skip hai item, ghi ba item

### 17.1. Fixture

Input gồm sáu records:

| ID | Amount | Status | Kết quả |
| --- | ---: | --- | --- |
| A | 10 | READY | Ghi |
| B | 5 | CANCELLED | Filter |
| C | 0 | READY | Process skip |
| D | 30 | READY | Ghi |
| E | -1 | READY | Process skip |
| F | 50 | READY | Ghi |

Policy `skipLimit(2)`. Kết quả kỳ vọng:

```text
JobExecution:     COMPLETED
readCount:        6
filterCount:      1
processSkipCount: 2
writeCount:       3
skipCount:        2
```

### 17.2. Cấu hình test H2

Gradle Groovy DSL trong Spring Boot 3.x project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Ví dụ `src/test/resources/application-skip-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  datasource:
    generate-unique-name: true
```

Dùng metadata repository trong cùng JVM để test. Nếu muốn test restart sau process/container crash, cần một database metadata bền vững.

### 17.3. Bài kiểm thử có context đầy đủ

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(classes = SkipOrFailFastIT.TestApp.class)
@ActiveProfiles("skip-test")
class SkipOrFailFastIT {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    AtomicInteger acceptedWrites;

    @Test
    void completesWhenExactlyTwoRecordsCanBeSkipped()
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("testCaseId",
                UUID.randomUUID().toString(), true)
            .toJobParameters();

        JobExecution execution = launcher.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
            .filter(s -> "importOrdersStep".equals(s.getStepName()))
            .findFirst()
            .orElseThrow();

        assertEquals(6L, step.getReadCount());
        assertEquals(1L, step.getFilterCount());
        assertEquals(2L, step.getProcessSkipCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(2L, step.getSkipCount());
        assertEquals(3L, step.getWriteCount());

        // In-memory sink dùng cho test này,
        // không phải writer transactional cho production.
        assertEquals(3, acceptedWrites.get());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(SkipTestJobs.class)
    static class TestApp {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class SkipTestJobs {

        @Bean
        AtomicInteger acceptedWrites() {
            return new AtomicInteger();
        }

        @Bean
        ItemReader<RawOrder> testReader() {
            return new ListItemReader<>(List.of(
                new RawOrder("A", new BigDecimal("10"), "READY"),
                new RawOrder("B", new BigDecimal("5"), "CANCELLED"),
                new RawOrder("C", BigDecimal.ZERO, "READY"),
                new RawOrder("D", new BigDecimal("30"), "READY"),
                new RawOrder("E", new BigDecimal("-1"), "READY"),
                new RawOrder("F", new BigDecimal("50"), "READY")
            ));
        }

        @Bean
        OrderValidationProcessor testProcessor() {
            return new OrderValidationProcessor();
        }

        @Bean
        ItemWriter<AcceptedOrder> testWriter(
                AtomicInteger acceptedWrites) {

            return chunk ->
                acceptedWrites.addAndGet(chunk.size());
        }

        @Bean
        Step importOrdersStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ItemReader<RawOrder> testReader,
                OrderValidationProcessor testProcessor,
                ItemWriter<AcceptedOrder> testWriter) {

            return new StepBuilder("importOrdersStep", repository)
                .<RawOrder, AcceptedOrder>chunk(
                    3, transactionManager)
                .reader(testReader)
                .processor(testProcessor)
                .writer(testWriter)
                .faultTolerant()
                .skip(InvalidOrderException.class)
                .skipLimit(2)
                .build();
        }

        @Bean
        Job importOrdersJob(
                JobRepository repository,
                Step importOrdersStep) {

            return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
        }
    }
}
```

Trong ví dụ test, `ListItemReader` và `AtomicInteger` chỉ phục vụ **một scenario đồng bộ**. Chúng không chứng minh checkpoint sau process restart hoặc transaction rollback của writer bên ngoài. Nếu mở rộng thành nhiều test methods, cần reset fixtures/context hoặc cung cấp reader state mới, tránh test ảnh hưởng nhau.

### 17.4. Test vượt ngưỡng

Thêm một input `G` với amount = 0 trong khi `skipLimit(2)` giữ nguyên. Tạo fixture độc lập và assert:

- `JobExecution` kết thúc `FAILED` khi xảy ra vi phạm skippable thứ ba.
- `processSkipCount`/exception phản ánh đã vượt ngưỡng theo framework.
- Những chunk đã commit trước khi lỗi có thể còn output.
- Không công bố incomplete output nếu contract đòi đầy đủ.
- Sau khi sửa nguồn, quyết định restart/reprocess dựa trên metadata và tình trạng output.

### 17.5. Test fail fast ngay cả khi skip budget còn

Thêm một record `CROSS_TENANT` vào input, giữ policy chỉ skip `InvalidOrderException`. Assert step `FAILED` khi gặp `CriticalOrderException`, dù mới skip 0 hoặc 1 record.

Test nên xác minh mã lỗi/nguồn để bảo đảm hệ thống không báo một generic failure khó điều tra.

### 17.6. Test read và write skip độc lập

- **Read skip:** dùng `FlatFileItemReader` với một dòng sai và assert `readSkipCount`. Kiểm tra raw line/source vị trí có được audit theo yêu cầu.
- **Write skip:** dùng một transactional writer có thể xác định một item không hợp lệ và rollback an toàn, assert `writeSkipCount`. Đồng thời test không ghi trùng các item cùng chunk sau retry.
- **Infrastructure failure:** làm writer ném lỗi DB tạm thời và assert nó không được bỏ qua bằng `skip(InvalidOrderException.class)`. Retry có thể diễn ra theo config; hết budget thì fail.

---

## 18. Quy trình ra quyết định bằng dữ liệu và SLA

### 18.1. Định nghĩa error budget từ nghiệp vụ

Trước khi bật `skipLimit`, có thể lập bảng chính sách:

| Thuộc tính | Câu hỏi |
| --- | --- |
| Data set | Feed nào, tenant nào, business period nào? |
| Required completeness | Có cần 100% records không? |
| Allowed reject types | Những rule codes nào được bỏ qua? |
| Critical violations | Rule nào bắt buộc dừng ngay? |
| Max rejects | Giới hạn tuyệt đối và/hoặc tỷ lệ bao nhiêu? |
| Audit evidence | Bản ghi lỗi được lưu ở đâu? |
| Remediation | Ai sửa, bao giờ reprocess? |
| Publication | Sau `COMPLETED` có được publish ngay không? |
| Side effects | Writer có idempotent không? |
| Restart | Nếu fail ở chunk N, phần đã commit được xử lý thế nào? |

Ví dụ chính sách cho catalog import:

```text
dataset: product_catalog
critical errors: schema invalid, cross-tenant, DB unavailable
skippable errors: malformed optional attribute, invalid image URL
absolute reject limit: 100 records
reject-rate limit: 0.5% eligible records
audit: quarantine table
publish condition: import completed AND quality gate passed
```

Lưu policy version cùng `JobInstance`/request metadata nếu rules có thể thay đổi qua deploy.

### 18.2. Thiết kế error budget theo phân loại

Có thể định nghĩa:

- `CRITICAL`: không skip, không publish.
- `RECOVERABLE_TECHNICAL`: retry có hạn; hết budget thì fail.
- `REJECTABLE_DATA`: skip/quarantine trong hạn mức.
- `OUT_OF_SCOPE`: filter, không tính là invalid.
- `MANUAL_REVIEW`: routing sang queue phê duyệt, có thể chặn publish một phần.
- `WARNING`: chấp nhận nhưng ghi nhận cảnh báo nếu policy cho phép.

Nếu một exception class mang tất cả ý nghĩa trên, sẽ khó cấu hình skip đúng. Tách exception types hoặc rule decisions giúp chính sách có thể đọc và test được.

### 18.3. Tính tổng tác động không chỉ tỷ lệ

Một feed mất 0,1% records có thể vẫn vi phạm SLA nếu record bị mất là một lệnh thanh toán trị giá rất lớn. Ngưỡng nên kết hợp **số lượng**, **trọng số rủi ro**, **rule severity** và **bất biến tổng**. Không quyết định chỉ dựa vào phần trăm dòng lỗi.

---

## 19. Giám sát và runbook khi xuất hiện skips

### 19.1. Metrics nên theo dõi

| Tín hiệu | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `readSkipCount` | Lỗi trong giai đoạn đọc | Không nhất thiết có parsed input item |
| `processSkipCount` | Lỗi processor được skip | Nên đối chiếu rule codes |
| `writeSkipCount` | Lỗi writer được skip | Cần giám sát rollback và side effects |
| `filterCount` | Item bị lọc hợp lệ | Không nên gộp vào reject rate |
| `rollbackCount` | Có transaction rollback | Có thể tăng do skip/retry |
| `JobExecution.BatchStatus` | Job completed/failed/stopped | Completed có thể vẫn có skips |
| `dataquality.reject_rate` | Tỷ lệ rejected trên mẫu số định nghĩa | Không phải metric built-in mặc định |
| `quarantine.backlog` | Số reject chưa được sửa | Có thể cần SLA xử lý riêng |

Các metric tùy biến là gợi ý; cần chọn labels có cardinality hữu hạn như `job.name`, `step.name`, `rule.code`, `rule.version`. Không dùng raw customer ID, externalOrderId hay `jobExecutionId` làm tag cho mọi item.

### 19.2. Structured log cho một reject

```text
event=batch_record_rejected
jobName=importOrdersJob
stepName=importOrdersStep
ruleCode=AMOUNT_MUST_BE_POSITIVE
ruleVersion=rules-2026-11
sourceFileId=file-418
sourceRecordId=ORDER-8821
decision=REJECTED
```

Chỉ log dữ liệu cần thiết; không đưa secrets, PII hay payload chưa được phân loại vào log. Cần audit store bền vững nếu downstream phải sửa record, thay vì chỉ đọc log.

### 19.3. Runbook khi số skip tăng

1. Xác định đúng job, business period, tenant, source và rule version.
2. So sánh read/process/write skips, filters, retries và rollback counts.
3. Kiểm tra distribution theo rule code, nguồn và thời điểm bắt đầu tăng.
4. Phân biệt lỗi dữ liệu cục bộ với lỗi hạ tầng lan rộng.
5. Kiểm tra quarantine có ghi đủ records và có unique keys không.
6. Nếu gần `skipLimit`, đánh giá nên dừng batch và điều tra trước khi output mất quá nhiều.
7. Nếu job `COMPLETED` nhưng có rejects, xác định gate/publish status độc lập.
8. Sửa dữ liệu/policy theo phê duyệt, reprocess có kiểm soát và đối soát output.

Không tự tăng skipLimit liên tục chỉ để dashboard xanh. Điều này có thể đổi hợp đồng chất lượng dữ liệu mà không được phê duyệt.

---

## 20. Các lỗi thường gặp khi chọn skip hoặc fail fast

| Sai lầm | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| `skip(Exception.class)` | Che bug và mất kết nối DB | Chỉ skip exception được phân loại |
| Dùng `return null` cho mọi violation | Mất audit; nhầm filter với reject | Decision/reject hoặc exception + skip listener |
| Tăng skipLimit sau mỗi lần fail | Chất lượng output giảm không kiểm soát | Định nghĩa error budget theo nghiệp vụ |
| Cho skip lỗi DB connection | Output thiếu vì tài nguyên không khả dụng | Retry có hạn rồi fail/restart |
| Skip lỗi liên record | Làm mất invariant tổng | Fail fast hoặc staging/quality gate |
| Skip writer không transactional | Side effects từng phần có thể lặp | Transaction/idempotency/reconciliation |
| Ghi HTTP audit trong SkipListener | Không rollback theo chunk | Outbox hoặc reject table có unique key |
| Chỉ kiểm tra `BatchStatus.COMPLETED` | Bỏ qua dữ liệu lỗi đã bị loại | Kiểm tra counters + business output |
| Cộng skip counts của mọi restarts làm unique rejects | Double-count | Ledger dedup theo source record |
| Quarantine không có source identity | Không biết sửa record nào | Lưu key, rule code, rule version |
| Fail fast nhưng cho rằng output được rollback hết | Chunk trước đã commit | Staging + publish gate |
| Retry lỗi validation cố định | Tốn tài nguyên, dễ loop | Skip/fail theo policy, không retry |
| Skip lỗi ở parser nhưng parser không tiến lên | Lặp lỗi hoặc mất vị trí | Kiểm tra reader contract |
| Dùng timestamp mới để chạy lại job vượt skip limit | Né lỗi, xử lý trùng và mất checkpoint | Restart/reprocess có phê duyệt |
| Chỉ test happy path | Không phát hiện lỗi thứ N+1 | Test exact limit, over limit, critical |
| Rule config đổi giữa restart | Cùng record có decision khác | Freeze rule version/snapshot hoặc migration |

---

## 21. Bài thực hành

### Bài 1 — Lập bảng quyết định

Phân loại các lỗi sau thành FILTER, SKIP, RETRY, FAIL FAST hoặc QUARANTINE + GATE:

1. Một dòng CSV có amount không parse được.
2. Order `CANCELLED` trong job chỉ nhập `READY`.
3. Một giao dịch thanh toán có số tài khoản đích không khớp.
4. Database mất kết nối 30 giây.
5. JDBC deadlock ở writer.
6. Hàng chục nghìn records có cùng external order ID.
7. Một optional product image URL không hợp lệ.
8. Tổng debit/credit không cân.

Với mỗi quyết định, ghi rõ điều kiện khiến bạn chọn khác và hành động remediation.

### Bài 2 — Skip limit chính xác

Tạo step với `skipLimit(2)` và processor ném `InvalidOrderException` cho các item amount ≤ 0. Test:

- Không lỗi: `COMPLETED`.
- Đúng hai lỗi: `COMPLETED` với `processSkipCount=2`.
- Ba lỗi: `FAILED`.
- Một lỗi critical: `FAILED` ngay, dù skip budget chưa dùng hết.

### Bài 3 — Filter khác skip

Tạo source gồm 10 item, trong đó 2 `CANCELLED` và 2 item invalid. Processor filter canceled, ném exception invalid.

Kiểm tra `filterCount=2`, `processSkipCount=2`, writer chỉ nhận accepted items và skip budget không bị canceled items tiêu thụ.

### Bài 4 — Reader parse lỗi

Dùng `FlatFileItemReader` đọc CSV có một dòng amount chữ thay vì số. Cấu hình skip `FlatFileParseException` và listener để ghi source line.

Test job tiếp tục được sau dòng sai; kiểm tra listener, `readSkipCount` và file output không có dòng lỗi.

### Bài 5 — Writer skip và rollback

Dùng một `JdbcBatchItemWriter` ghi vào bảng có constraint và tạo đúng một item vi phạm có thể cô lập. Cấu hình fault-tolerant step, kiểm tra transaction rollback và data isolation.

Bổ sung một writer giả lập side effect ngoài transaction để quan sát vì sao retry/write skip có thể lặp thao tác nếu không có idempotency key.

### Bài 6 — Quality gate sau staging

Cho feed 50.000 eligible records, 160 rejected, policy reject rate tối đa 0,25%. Tính tỷ lệ và thiết kế gate quyết định có publish hay không.

Đảm bảo việc step import `COMPLETED` không tự động cho phép publish khi ngưỡng chưa đạt.

### Bài 7 — Restart sau khi đã skip

Tạo chunk job có vài valid/invalid items. Cho writer thất bại sau một số chunk đã commit; restart đúng `JobInstance`.

Kiểm tra checkpoint, unique accepted output, reject ledger, và giải thích tại sao cộng counts của hai StepExecutions có thể không phải số unique rejects.

### Bài 8 — Chính sách vận hành

Viết runbook cho job nhập sản phẩm có 2% malformed rows trong khi policy chỉ cho 0,5%. Quyết định tạm dừng publish, điều tra nguồn, sửa dữ liệu và chạy lại như thế nào mà không tạo JobInstance mới bằng timestamp nhận diện.

---

## 22. Checklist trước khi áp dụng skip trong production

- [ ] Lỗi skippable chỉ ảnh hưởng record độc lập, không làm sai bất biến toàn batch.
- [ ] Có bảng rule code và severity được nghiệp vụ phê duyệt.
- [ ] Có ngưỡng skip rõ ràng, kèm tỷ lệ/gate nếu volume thay đổi lớn.
- [ ] Không skip lỗi kết nối DB, metadata repository hoặc lỗi hạ tầng lan rộng.
- [ ] Dùng filter cho item hợp lệ ngoài phạm vi, không biến filter thành silent reject.
- [ ] `SkipListener`/quarantine có audit nguồn và khả năng tránh duplicate.
- [ ] Reader xử lý skip an toàn và tiến qua item lỗi.
- [ ] Writer có transaction/idempotency phù hợp khi retry/rollback.
- [ ] Fail fast có chiến lược xử lý các chunk đã commit.
- [ ] Staging/publish gate được dùng nếu yêu cầu output all-or-nothing ở cấp toàn đợt.
- [ ] Có unit test, integration test exact limit, over limit và critical errors.
- [ ] Đã test restart, checkpoint, quyết định rule version và output reconciliation.
- [ ] Dashboard phân biệt `COMPLETED` có skip, `FAILED` và `HOLD_FOR_REVIEW`.
- [ ] Remediation owner, SLA và cách reprocess rejects đã được xác định.

## 23. Kết luận

**Skip** là công cụ tốt khi một lỗi có thể tách riêng một item, nghiệp vụ chấp nhận thiếu item đó trong giới hạn, và có cơ chế lưu/quản lý dữ liệu bị từ chối. **Fail fast** phù hợp với lỗi hệ thống, lỗi critical, rủi ro bảo mật hoặc trường hợp bỏ một record làm toàn bộ kết quả sai. **Retry** dành cho sự cố có thể phục hồi, **filter** cho item hợp lệ ngoài phạm vi, còn **quarantine + quality gate** là lựa chọn cần cân nhắc khi vừa muốn xử lý phần tốt vừa phải bảo đảm dữ liệu được công bố đạt chất lượng.

Đừng quyết định chỉ vì một exception có thể được `.skip(...)`. Hãy quyết định dựa trên **tính đúng của dữ liệu, khả năng giải trình và hậu quả khi restart**, rồi dùng Spring Batch để thực thi chính sách đó một cách nhất quán.

## 24. Tài liệu tham khảo

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): `skip`, `skipLimit`, `noSkip`.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): ranh giới chunk/transaction.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): fault-tolerant retry.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listeners, skip callbacks.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): filter và transformation.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint/restart.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` và integration testing.
- [Spring Batch 5.2 API — SkipPolicy](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/step/skip/SkipPolicy.html): interface `shouldSkip`.
- [Spring Batch 5.2 API — SkipListener](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/SkipListener.html): read/process/write skip notifications.
