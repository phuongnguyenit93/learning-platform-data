# Failure ở reader trong Spring Batch: phát hiện, retry, skip và phục hồi an toàn

## 1. Khi nào một ItemReader được xem là gặp lỗi?

Trong Spring Batch, **ItemReader** chịu trách nhiệm cung cấp lần lượt các item đầu vào cho một step. Trong một step xử lý theo chunk, framework gọi phương thức `read()` nhiều lần cho đến khi reader trả về một item, ném exception hoặc trả về `null` để báo hết dữ liệu.

Hợp đồng cơ bản:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Ba kết quả có ý nghĩa khác nhau:

| Kết quả `read()` | Spring Batch hiểu như thế nào? | Hành động thông thường |
|---|---|---|
| Trả về một item | Đọc thành công | Chuyển sang processor (nếu có), rồi writer |
| Trả về `null` | **End of input** | Kết thúc vòng đọc khi chunk phù hợp được xử lý |
| Ném exception | **Read failure** | Áp dụng retry/skip/fail theo fault-tolerance policy |

**Reader trả về `null` không phải lỗi**. Một bản ghi không đạt điều kiện nhưng vẫn đọc thành công nên thường được lọc trong `ItemProcessor` bằng cách trả `null`; đó là *filter*, không phải *read skip*. Ngược lại, lỗi đọc tệp, parse một dòng, timeout truy vấn, mất kết nối database hoặc lỗi giải mã đều có thể xuất hiện tại reader.

Ví dụ, file:

```csv
order_id,amount
A-101,120000
A-102,INVALID_AMOUNT
A-103,50000
```

Nếu reader dùng `FieldSet.readBigDecimal("amount")`, dòng thứ ba có thể gây lỗi mapping. Với `FlatFileItemReader`, lỗi từ line mapper thường được bọc thành `FlatFileParseException` với số dòng và nội dung đầu vào. Quyết định tiếp theo là **bỏ qua đúng dòng hỏng**, **thử đọc lại**, hay **dừng step**.

### Một read failure ảnh hưởng những gì?

Một lỗi không được xử lý có thể khiến `StepExecution` chuyển sang `FAILED`, làm job thất bại theo flow hiện tại. Với cấu hình fault tolerant, framework có thể retry hoặc skip để tiếp tục chạy. Dù chọn đường nào, việc phục hồi còn phụ thuộc trạng thái của reader, transaction và checkpoint.

```text
ItemReader.read()
    |
    +--- item ----------------------> process --> write
    |
    +--- null ----------------------> end of input
    |
    +--- exception
            |
            v
      Fault-tolerance policy
            |
            +--- retry --> gọi đọc lại khi phù hợp
            +--- skip  --> ghi nhận read skip, tiếp tục
            +--- fail  --> Step FAILED
```

**Phạm vi phiên bản:** Các đoạn Java chính dùng Spring Batch **5.2.x**, Spring Boot **3.x**, Java **17+**, JUnit Jupiter. Spring Batch 6 đã thay đổi một số package và cách cấu hình step; khi dùng 6.x cần đối chiếu API đúng phiên bản. Các khái niệm retry/skip/checkpoint vẫn cần được hiểu theo hợp đồng của reader cụ thể.

## 2. Phân loại lỗi reader trước khi chọn cách xử lý

Không phải exception nào của reader cũng có thể phục hồi bằng một chính sách chung.

| Nhóm lỗi | Ví dụ thực tế | Hướng xử lý thường phù hợp |
|---|---|---|
| **Dữ liệu của một bản ghi không hợp lệ** | Một dòng CSV sai số cột, `amount=ABC` | Skip có giới hạn; lưu dòng lỗi để sửa |
| **Nguồn đầu vào bị thiếu hoặc sai cấu hình** | File không tồn tại, sai bucket/path, sai quyền truy cập | Fail fast, sửa cấu hình hoặc bổ sung nguồn |
| **Lỗi hạ tầng tạm thời** | Database deadlock, lỗi kết nối thoáng qua, HTTP 503 | Retry có giới hạn và backoff, nếu reader giữ state an toàn |
| **Nguồn bị hỏng diện rộng** | File encoding sai toàn bộ, schema CSV thay đổi | Fail hoặc chặn ở bước validation; không skip hàng loạt |
| **Reader không thể xác định vị trí tiếp theo** | Cursor mất trạng thái, paging thiếu sort key ổn định | Dừng và phục hồi trạng thái; không blind retry |
| **Nguồn có tính transaction** | Đọc thông điệp từ queue được rollback cùng transaction | Cấu hình reader/transaction phù hợp, kiểm tra redelivery |
| **Lỗi logic ứng dụng** | `NullPointerException` trong custom mapper | Thường fail để sửa code; không cấu hình `skip(Exception.class)` mặc định |

Ba câu hỏi khi thiết kế policy:

1. **Lỗi có lặp lại không?** Một chuỗi `"ABC"` không thể parse thành số không tự sửa sau khi retry; timeout mạng có thể hết.
2. **Reader đã tiến qua dữ liệu hỏng chưa?** Nếu exception luôn xảy ra ở cùng một vị trí mà cursor không đổi, skip có thể gặp lại chính lỗi đó mãi.
3. **Mất một bản ghi có được chấp nhận không?** File giao dịch tài chính có thể yêu cầu dừng toàn bộ, trong khi dữ liệu catalog có thể cho phép một tỷ lệ nhỏ dòng lỗi.

Quy tắc kinh nghiệm: **skip lỗi dữ liệu có thể khoanh vùng; retry lỗi tạm thời có thể tự hồi phục; fail khi không bảo đảm tính toàn vẹn hoặc tiến độ đọc**.

## 3. Fault tolerance: mặc định và khi bật `faultTolerant()`

Một step chunk-oriented thông thường **không tự động bỏ qua mọi read exception**. Nếu reader ném lỗi không được xử lý, step có thể thất bại.

Ví dụ một step đọc dữ liệu rồi ghi:

```java
@Bean
Step importStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("importStep", repository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

Nếu reader gặp `FlatFileParseException`, không có policy nào trong cấu hình trên cho phép tiếp tục. `OrderRow` chỉ là kiểu DTO nghiệp vụ trong ví dụ.

Khi yêu cầu được phép bỏ qua tối đa 10 dòng CSV lỗi, cấu hình rõ:

```java
import org.springframework.batch.item.file.FlatFileParseException;

return new StepBuilder("importStep", repository)
        .<OrderRow, OrderRow>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
```

`skipLimit(10)` là **giới hạn tổng số skip trong step** ở các giai đoạn read/process/write, không phải 10 lần riêng cho reader. Ví dụ nếu đã có 6 read skips và 4 process skips, một skip bổ sung có thể khiến step vượt giới hạn và thất bại.

Không cấu hình chung:

```java
.skip(Exception.class)
```

nếu chưa hiểu rõ: cách này có thể che lỗi kết nối, lỗi lập trình, dữ liệu nguồn bị hỏng hàng loạt, hoặc lỗi không nên bị bỏ qua. Thay vào đó, chọn đúng exception và dùng `.noSkip(...)` hoặc `SkipPolicy` tùy nhu cầu khi có nhiều loại lỗi.

### 3.1. Skip, filter và retry khác nhau

| Hành vi | Được kích hoạt bởi | Bộ đếm liên quan |
|---|---|---|
| **Read skip** | Reader ném exception được phép skip | `readSkipCount` |
| **Process skip** | Processor ném exception được phép skip | `processSkipCount` |
| **Write skip** | Writer ném exception được phép skip | `writeSkipCount` |
| **Filter** | Processor trả `null` cho item hợp lệ đã đọc | `filterCount` |
| **Retry** | Thử lại lỗi theo policy | Có thể phát sinh nhiều callback lỗi; không đồng nghĩa skip |

`StepExecution.getReadCount()` phản ánh **item đọc thành công**. Một dòng gây lỗi rồi bị skip thường **không** tăng read count thành một item thành công; việc skip được thể hiện qua `readSkipCount`. Cần đọc kết hợp các counter và dữ liệu đầu ra.

## 4. Ví dụ thực tế: CSV có một dòng hỏng

Ta xây dựng một reader cho file đơn hàng. Dòng hợp lệ có `order_id` là chuỗi và `amount` là số thập phân. Nếu một dòng có `amount` sai kiểu, step được phép skip có kiểm soát.

### 4.1. DTO dữ liệu

```java
import java.math.BigDecimal;

public record OrderRow(
        String orderId,
        BigDecimal amount
) {
}
```

### 4.2. Cấu hình `FlatFileItemReader` theo `JobParameters`

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<OrderRow> ordersCsvReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("ordersCsvReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1) // Bỏ dòng tiêu đề CSV
            .delimited()
            .delimiter(",")
            .names("order_id", "amount")
            .fieldSetMapper(fieldSet -> new OrderRow(
                    fieldSet.readString("order_id"),
                    fieldSet.readBigDecimal("amount")))
            .build();
}
```

**Tại sao dùng `@StepScope`?** Mỗi lần chạy step cần reader và trạng thái đọc riêng, đồng thời `inputFile` được lấy từ `JobParameters` của execution thực tế. Dữ liệu được chạy lại với cùng tham số có thể được phục hồi theo checkpoint nếu nguồn và cấu hình không đổi.

**Tại sao `strict(true)`?** Đây là lựa chọn fail fast nếu resource cần thiết không tồn tại. Nếu dùng `strict(false)` một cách tùy tiện, một file thiếu có thể bị hiểu như đầu vào rỗng và job kết thúc “thành công” dù chưa đọc dữ liệu.

Nếu CSV có trích dẫn dấu phẩy, định dạng escape phức tạp hoặc nhiều kiểu bản ghi, cần cấu hình tokenizer/line mapping tương ứng. Ví dụ này dùng định dạng đơn giản, không thay thế CSV parser phù hợp mọi biến thể RFC.

### 4.3. Cấu hình step cho phép skip lỗi parse

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> ordersCsvReader,
        ItemWriter<OrderRow> orderWriter,
        ReadErrorLogger readErrorLogger,
        ReadSkipAudit readSkipAudit) {

    return new StepBuilder("importOrdersStep", repository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(ordersCsvReader)
            .writer(orderWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skipLimit(10)
            .listener(readErrorLogger)
            .listener(readSkipAudit)
            .build();
}
```

`orderWriter` là writer nghiệp vụ được khai báo riêng, chẳng hạn `JdbcBatchItemWriter<OrderRow>`. Hai listener `ReadErrorLogger` và `ReadSkipAudit` sẽ được định nghĩa ngay sau đây.

Một lỗi parse **bị skip** không có nghĩa mọi update trước đó sẽ rollback. Khi exception reader được cấu hình skip, Spring Batch thường không rollback transaction chỉ vì lỗi đọc đó; behavior tổng thể còn phụ thuộc nguồn dữ liệu và lỗi khác trong chunk. Phần transactional reader sẽ phân tích ngoại lệ quan trọng.

## 5. Phân biệt `onReadError` và `onSkipInRead`

Hai callback rất dễ bị nhầm:

- `ItemReadListener.onReadError(Exception)`: được gọi khi một thao tác đọc gặp exception. Nó có thể được gọi cho một lỗi cuối cùng được retry thành công hoặc một lỗi làm step thất bại.
- `SkipListener.onSkipInRead(Throwable)`: được gọi khi một lỗi đọc thực sự được **bỏ qua** theo chính sách skip.

Cùng một lỗi có thể có callback đọc lỗi mà **không có skip**, chẳng hạn reader retry rồi thành công. Vì vậy hãy dùng `onReadError` để quan sát các lần đọc thất bại, và dùng `onSkipInRead` để ghi nhận các bản ghi bị loại khỏi luồng xử lý.

### 5.1. Ghi log lỗi đọc

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ItemReadListener;

public final class ReadErrorLogger
        implements ItemReadListener<OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(ReadErrorLogger.class);

    @Override
    public void onReadError(Exception exception) {
        log.warn(
                "Reader failed: type={}, message={}",
                exception.getClass().getSimpleName(),
                exception.getMessage()
        );
    }
}
```

Không nên log nguyên file hoặc toàn bộ dữ liệu nhạy cảm ở `onReadError`. Với retry, một sự cố mạng có thể phát sinh nhiều log; nên dùng metric counter, cấu hình mức log và correlation ID phù hợp để tránh spam.

### 5.2. Audit dòng bị skip

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public final class ReadSkipAudit
        implements SkipListener<OrderRow, OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(ReadSkipAudit.class);

    @Override
    public void onSkipInRead(Throwable error) {
        if (error instanceof FlatFileParseException parseError) {
            log.warn(
                    "Skipped CSV line={}, reason={}",
                    parseError.getLineNumber(),
                    parseError.getCause() == null
                            ? parseError.getMessage()
                            : parseError.getCause().getMessage()
            );
            return;
        }

        log.warn(
                "Skipped read failure: type={}",
                error.getClass().getSimpleName()
        );
    }
}
```

`FlatFileParseException` có `getLineNumber()` và `getInput()`. `getInput()` chứa dòng gốc nên có thể mang thông tin cá nhân, tài khoản hoặc dữ liệu nhạy cảm: chỉ lưu vào kho quarantine có kiểm soát nếu thực sự cần, và tránh in tràn lan vào log.

**Điểm quan trọng:** `SkipListener.onSkipInRead` nhận `Throwable`, không nhận trực tiếp item vì quá trình đọc chưa tạo được item hợp lệ. Nếu muốn audit một dòng bị lỗi, reader/exception cần cung cấp đủ định danh (ví dụ số dòng và tên file). Không suy đoán ID nghiệp vụ từ một exception không chứa dữ liệu đó.

Các ví dụ listener trên được đăng ký bằng `.listener(readErrorLogger)` và `.listener(readSkipAudit)` trong `StepBuilder`, để Spring Batch thực sự gọi callback. Gọi trực tiếp hai phương thức trong unit test chỉ kiểm tra logic callback, không xác nhận wiring.

### 5.3. Lưu bản ghi lỗi vào quarantine

Với nhu cầu doanh nghiệp, nên có một nơi lưu tách biệt:

```text
source_file     = orders-20250512.csv
source_line     = 3
error_category  = PARSE_ERROR
error_message   = Invalid amount
job_execution   = 501
record_checksum = SHA-256 của nội dung phù hợp
```

Lưu ý về transaction: callback skip có thể diễn ra ở gần ranh giới commit của chunk. Nếu audit được ghi vào cùng transaction, rollback có thể làm mất audit; nếu audit ghi vào nguồn độc lập, retry có thể tạo trùng. Chọn ranh giới transaction và khóa idempotency theo nghiệp vụ, ví dụ `sourceFileChecksum + lineNumber + errorCategory`.

## 6. Retry lỗi reader: khi nào thực sự có ích?

Retry phù hợp cho lỗi **có khả năng tự biến mất**, chẳng hạn dịch vụ bên ngoài trả 503 hoặc kết nối database gặp lỗi tạm thời. Với lỗi parse CSV lặp lại cho cùng một chuỗi, retry chỉ làm tốn thêm thời gian.

Ví dụ cấu hình retry có chọn lọc:

```java
import org.springframework.dao.TransientDataAccessException;

return new StepBuilder("readFromDatabaseStep", repository)
        .<OrderRow, OrderRow>chunk(100, transactionManager)
        .reader(databaseReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Đây là ví dụ về **chính sách retry**, không phải bảo đảm mọi JDBC reader có thể hồi phục sau mất kết nối. Nếu cursor đọc bị mất, retry có thể lặp lại đúng exception hoặc làm lệch vị trí đọc; cần xác định hợp đồng của `databaseReader` trước khi bật retry.

### 6.1. Retry limit và skip limit là hai ngưỡng khác nhau

| Thiết lập | Mục đích |
|---|---|
| `retry(SomeException.class)` | Chọn exception có thể thử lại |
| `retryLimit(3)` | Giới hạn các lần thử theo chính sách retry |
| `skip(OtherException.class)` | Chọn exception có thể bỏ qua |
| `skipLimit(10)` | Giới hạn tổng số skip trong step |
| `noRetry(...)` / `noSkip(...)` | Loại trừ các exception không phù hợp |

Trong cấu hình có cả retry và skip, thứ tự xử lý, số lần gọi callback và counter phụ thuộc loại lỗi, phase và trạng thái transaction. Không nên viết test giả định **mỗi exception tương ứng một lần callback** khi fault tolerance cho phép nhiều lượt thử.

### 6.2. Backoff tránh retry liên tục

Retry không nên gây vòng lặp gọi API hoặc DB quá dày. Nếu dùng Spring Retry và policy phù hợp trong cấu hình step, có thể thêm backoff:

```java
import org.springframework.retry.backoff.FixedBackOffPolicy;

FixedBackOffPolicy backoff = new FixedBackOffPolicy();
backoff.setBackOffPeriod(200L); // minh họa: 200 ms

return new StepBuilder("remoteReaderStep", repository)
        .<OrderRow, OrderRow>chunk(50, transactionManager)
        .reader(remoteReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientReadException.class)
        .retryLimit(3)
        .backOffPolicy(backoff)
        .build();
```

`TransientReadException` là exception giả định của ứng dụng; cần khai báo lớp và ánh xạ lỗi mạng/HTTP vào đúng exception đó. Giá trị backoff phải xuất phát từ đặc điểm dịch vụ, thời gian timeout và giới hạn số lần thử; **200 ms chỉ là ví dụ**.

Cẩn trọng với retry ở reader: `read()` cần có semantics rõ ràng về vị trí dữ liệu. Nếu nó tăng offset rồi mới ném exception, lần retry tiếp theo có thể **không còn là cùng item**. Nếu nó không tăng offset và exception mang tính quyết định, nó có thể tiếp tục thất bại ở cùng bản ghi.

### 6.3. Thiết kế reader để có thể retry

Với reader tùy biến gọi API phân trang, cần xác định:

- Pagination cursor có được lưu chỉ sau khi page đã xử lý an toàn không?
- Request lỗi trước khi trả data có giữ nguyên cursor không?
- Server có bảo đảm cùng cursor trả cùng page trong lúc retry không?
- Có trùng lặp do retry khi API không ổn định không?
- Khi nhận nhiều item trong một page, checkpoint mô tả vị trí từng item như thế nào?

Nếu API không cho phép đọc lại nhất quán, nên đưa dữ liệu về một staging area bất biến trước rồi cho Spring Batch xử lý nguồn staging đó. Điều này có thể đáng tin cậy hơn nhiều so với retry trên một luồng dữ liệu thay đổi liên tục.

## 7. Tại sao không phải read exception nào cũng được skip an toàn?

Khả năng skip phụ thuộc cách reader tiến qua nguồn.

### 7.1. Reader đã tiến đến dòng tiếp theo

`FlatFileItemReader` có thể lấy một dòng gốc, rồi line mapper ném `FlatFileParseException`. Reader đã xác định được dòng lỗi, và ở lần đọc tiếp theo có thể chuyển sang dòng kế tiếp. Khi chính sách cho phép, skip một dòng hỏng thường có nghĩa rõ ràng.

```text
Line 1: header           -> bỏ qua
Line 2: A-101,120000     -> item hợp lệ
Line 3: A-102,INVALID    -> FlatFileParseException -> skip
Line 4: A-103,50000      -> item hợp lệ
```

### 7.2. Reader luôn lỗi tại cùng vị trí

Một custom reader viết sai:

```java
public OrderRow read() {
    String raw = lines.get(index);    // index chưa tăng
    return parse(raw);                 // lỗi ở raw này
}
```

Nếu `parse(raw)` ném exception trước khi cập nhật `index`, lần gọi tiếp theo vẫn gặp cùng dòng. Cấu hình skip không tự sửa hợp đồng tiến độ của reader; nó có thể tiêu hết skip limit mà không tiến được một bản ghi nào.

Phiên bản đơn giản có thứ tự thao tác rõ hơn:

```java
public OrderRow read() {
    if (index >= lines.size()) {
        return null;
    }

    String raw = lines.get(index++);
    return parse(raw);
}
```

Tuy nhiên, **tăng index trước parse** chỉ giải quyết một tình huống đơn giản về reader trong bộ nhớ. Với reader cần restart, offset phải được checkpoint và khôi phục đúng. Với queue transactional, cursor lại phải tuân thủ transaction. Không áp dụng một mẹo tăng index cho mọi nguồn.

### 7.3. Reader lấy dữ liệu rồi mất kết nối

Ví dụ một cursor JDBC lấy một số row rồi mất connection. Bật `skip(SQLException.class)` có thể khiến step bỏ qua cả một lỗi hạ tầng, nhưng không biết chắc bản ghi nào đã/ chưa được đọc. Trong trường hợp đó, **fail rồi restart bằng checkpoint đáng tin cậy** thường an toàn hơn bỏ qua.

## 8. Transaction và rollback khi lỗi xảy ra ở reader

Spring Batch chunk processing thường bao quanh đọc–xử lý–ghi trong một transaction, nhưng **hợp đồng transaction của nguồn đọc** có thể khác nhau.

Theo tài liệu Spring Batch 5.2, khi cấu hình skip, một exception từ `ItemReader` thường **không làm rollback** transaction của step chỉ vì lỗi đọc đó. Trong khi đó exception tại `ItemWriter` thường dẫn đến rollback theo mặc định. Điều này có tác động lớn đến counter và việc ghi audit.

### 8.1. Reader không có transaction riêng

Ví dụ đọc file CSV:

- Đọc một dòng không thể “rollback file pointer” giống như rollback hàng trong database.
- Spring Batch có thể giữ buffer item đã đọc để phục vụ xử lý lại khi chunk rollback.
- `FlatFileItemReader` implement `ItemStream`, cho phép lưu trạng thái để restart qua `ExecutionContext`.

Nếu chunk có 99 item thành công và một dòng hỏng được skip, step có thể tiếp tục xây dựng chunk và commit phần dữ liệu hợp lệ. Kết quả cần kiểm tra bằng counter và bảng đầu ra thực tế.

### 8.2. Reader lấy item từ queue transactional

Với JMS hoặc nguồn transaction thật, rollback có thể đưa message trở lại queue. Spring Batch có tùy chọn:

```java
return new StepBuilder("transactionalQueueStep", repository)
        .<OrderMessage, OrderMessage>chunk(20, transactionManager)
        .reader(transactionalQueueReader)
        .writer(orderWriter)
        .readerIsTransactionalQueue()
        .build();
```

`readerIsTransactionalQueue()` báo rằng reader dựa trên nguồn transactional; step không dùng cơ chế buffer item giống reader forward-only thông thường, vì khi rollback nguồn có thể redeliver message.

**Chỉ dùng khi nguồn đọc và transaction thực sự có semantics đó.** Bật tùy tiện cho file hoặc API reader có thể làm thay đổi hành vi retry/rollback ngoài dự kiến. Với queue, còn phải thiết kế redelivery count, dead-letter queue và idempotency để message lỗi không quay lại mãi.

### 8.3. Reader có side effect

Một `ItemReader` lý tưởng chủ yếu đọc dữ liệu. Nếu custom reader vừa lấy item vừa xóa record khỏi queue, xác nhận HTTP hoặc cập nhật bảng trạng thái, lỗi ở bất kỳ chỗ nào cũng có thể tạo **mất dữ liệu** hoặc **đọc trùng**.

Ví dụ:

```text
1. Reader nhận order-101
2. Reader gọi API đánh dấu order-101 đã xử lý
3. Processor/Writer gặp lỗi, transaction DB rollback
4. Restart: API không còn trả order-101
```

Để phục hồi an toàn, tránh side effect không rollback trong reader hoặc chuyển nó đến bước ghi/ack có semantics rõ ràng. Nếu không thể, cần transactional inbox/outbox hoặc cơ chế idempotency và reconciliation.

## 9. ItemStream và checkpoint: nền tảng để restart sau read failure

Spring Batch lưu tiến độ batch qua `ExecutionContext`. Nhiều reader hỗ trợ `ItemStream` với ba phương thức:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Vai trò:

- `open(...)`: khởi tạo reader, nếu có checkpoint phù hợp thì khôi phục vị trí.
- `update(...)`: ghi trạng thái của reader vào `ExecutionContext` tại mốc framework cập nhật checkpoint.
- `close()`: đóng resource.

`FlatFileItemReader` thực hiện cơ chế state và có `name` để tạo key trong execution context. Nếu reader không lưu được vị trí hoặc nguồn thay đổi giữa các execution, restart có thể đọc trùng hoặc bỏ sót bản ghi.

### 9.1. Lưu state khi dùng FlatFileItemReader

```java
return new FlatFileItemReaderBuilder<OrderRow>()
        .name("ordersCsvReader")
        .resource(new FileSystemResource(inputFile))
        .saveState(true)
        .strict(true)
        .linesToSkip(1)
        .delimited()
        .names("order_id", "amount")
        .fieldSetMapper(fieldSet -> new OrderRow(
                fieldSet.readString("order_id"),
                fieldSet.readBigDecimal("amount")))
        .build();
```

`saveState(true)` là cách thể hiện rõ ý định hỗ trợ restart. Một tên reader ổn định và riêng biệt giúp tránh xung đột khóa trạng thái nếu có nhiều reader cùng hoạt động trong execution context.

**Điểm cốt lõi:** Checkpoint không phải ảnh chụp toàn bộ file. Nếu người vận hành thay file nguồn sau khi step thất bại, cùng số dòng có thể trỏ đến bản ghi hoàn toàn khác khi restart.

Để tránh sai lệch:

1. Chốt `inputFile` và identifying parameters khi launch.
2. Lưu dữ liệu đầu vào bất biến hoặc version hóa (object storage version, file checksum).
3. Nếu file thay đổi, cân nhắc tạo `JobInstance` mới với quy trình làm lại dữ liệu rõ ràng, không restart mù quáng.
4. Đảm bảo writer idempotent; dữ liệu đã commit trước khi lỗi không bị ghi trùng.
5. Xác nhận reader luôn được mở lại qua `ItemStream.open(...)` và được framework quản lý đúng.

### 9.2. Lưu trạng thái trong custom reader

Nếu cần reader tùy biến, hãy xây dựng nó với cơ chế state rõ ràng, thay vì chỉ lưu offset trong field.

Ví dụ rút gọn reader đọc một danh sách cố định và hỗ trợ restart qua index:

```java
import java.util.List;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class IndexedReader<T> implements ItemStreamReader<T> {

    private final List<T> items;
    private final String stateKey;
    private int index;

    public IndexedReader(List<T> items, String stateKey) {
        this.items = List.copyOf(items);
        this.stateKey = stateKey;
    }

    @Override
    public void open(ExecutionContext context) {
        index = context.containsKey(stateKey)
                ? context.getInt(stateKey)
                : 0;
    }

    @Override
    public T read() {
        return index < items.size() ? items.get(index++) : null;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(stateKey, index);
    }

    @Override
    public void close() {
        // Không có resource cần đóng trong ví dụ.
    }
}
```

Đây là ví dụ cơ bản để giải thích `open/update/close`, **không phải reader dùng chung cho môi trường concurrent/multi-threaded**. Danh sách đầu vào phải giữ nguyên thứ tự qua restart; không dùng reader kiểu này với dữ liệu liên tục thay đổi rồi kỳ vọng checkpoint offset còn đúng.

### 9.3. JDBC reader cần thứ tự ổn định

Với `JdbcPagingItemReader`, cần cấu hình sort key ổn định, lý tưởng có tính duy nhất, để phân trang/restart không mất bản ghi khi thứ tự truy vấn thay đổi. Với `JdbcCursorItemReader`, cần đánh giá cách driver/cursor khôi phục sau lỗi kết nối và chi phí đọc lại dữ liệu đến checkpoint.

Ngay cả khi reader có checkpoint, việc dữ liệu database thay đổi trong lúc job chạy cũng có thể làm offset/paging không còn trỏ cùng tập bản ghi. Các giải pháp gồm snapshot, business cutoff cố định, truy vấn theo ID tăng dần hoặc staging table có dữ liệu bất biến.

## 10. Lỗi reader ở những giai đoạn khác nhau

Read failure không chỉ xảy ra trong `read()`. Có thể lỗi ngay khi mở hoặc đóng reader.

| Giai đoạn | Callback / phương thức | Ví dụ lỗi | Chiến lược |
|---|---|---|---|
| Khởi tạo | `ItemStream.open(...)` | File thiếu, credential sai, không mở được cursor | Fail fast; sửa resource/credential |
| Đọc | `ItemReader.read()` | Parse lỗi, timeout, mất kết nối | Skip/retry/fail theo nguyên nhân |
| Cập nhật checkpoint | `ItemStream.update(...)` | Không thể ghi state, exception nội bộ | Fail; bảo vệ metadata và consistency |
| Đóng | `ItemStream.close()` | Đóng resource thất bại | Log, giải phóng resource, xem trạng thái final |

Một exception ở `open()` **không nhất thiết** đi qua chính sách `skip(FlatFileParseException.class)` vốn dùng cho lỗi đọc item, và cũng không thể dùng `onSkipInRead` để suy ra rằng một file bị thiếu đã bị bỏ qua an toàn. Ví dụ `strict(true)` khiến file không tồn tại báo lỗi ngay khi mở; đó là hành vi mong muốn khi nguồn đầu vào là bắt buộc.

### 10.1. Lỗi “không đọc được gì” khác với file rỗng

Hai tình huống có thể tạo cùng `writeCount=0` nhưng ngữ nghĩa khác nhau:

```text
Case A: reader mở file thành công, file chỉ có header
       -> read() trả null, step có thể COMPLETED, 0 items

Case B: reader không mở được file
       -> open() ném lỗi, step FAILED
```

Nếu nghiệp vụ không cho phép ngày không có đơn hàng, cần thêm bước validation để phân biệt “hôm nay không có dữ liệu” với “file rỗng do pipeline thượng nguồn bị lỗi”. Cấu hình `strict` chỉ giúp xác minh resource tồn tại, không bảo đảm nội dung có dữ liệu.

## 11. Theo dõi lỗi reader qua StepExecution và listener

Khi điều tra, nên đọc ít nhất các counter sau:

```java
StepExecution step = ...;

System.out.println("status=" + step.getStatus());
System.out.println("readCount=" + step.getReadCount());
System.out.println("readSkipCount=" + step.getReadSkipCount());
System.out.println("processSkipCount=" + step.getProcessSkipCount());
System.out.println("writeSkipCount=" + step.getWriteSkipCount());
System.out.println("rollbackCount=" + step.getRollbackCount());
System.out.println("failureExceptions=" + step.getFailureExceptions());
```

Một ví dụ giả định:

```text
Input lines      = 1001 (bao gồm 1 header)
Valid records    = 997
Malformed records= 3

readCount        = 997
readSkipCount    = 3
writeCount       = 997
status           = COMPLETED
```

Điều kiện trên chỉ hợp lý khi reader xử lý đúng 1000 dòng dữ liệu, writer không có lỗi/filter khác và skip limit cho phép 3 dòng hỏng. Nếu dữ liệu nghiêm trọng đến mức không thể chấp nhận mất 3 đơn hàng, `COMPLETED` với skip vẫn có thể không đáp ứng yêu cầu nghiệp vụ; cần đặt ngưỡng chất lượng hoặc fail job theo rule riêng.

### 11.1. Đọc từ JobRepository

`JobExplorer` giúp truy vấn `JobExecution` và `StepExecution` theo ID để xem lại status/counter sau khi job kết thúc:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public void printReaderFailureStats(
        JobExplorer explorer, long jobExecutionId) {

    JobExecution execution =
            explorer.getJobExecution(jobExecutionId);

    if (execution == null) {
        throw new IllegalArgumentException(
                "Unknown jobExecutionId " + jobExecutionId);
    }

    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
                "step=%s status=%s read=%d readSkips=%d%n",
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getReadSkipCount()
        );
    }
}
```

Metadata phục vụ đối soát khi process đã kết thúc. Với step đang chạy, counter có thể chỉ được persist tại các mốc checkpoint; không phải lúc nào cũng phản ánh item mới nhất ngay lập tức.

### 11.2. Metric và alert

Một dashboard theo dõi reader có thể gồm:

- `readSkipCount` trên mỗi step execution, và tỷ lệ `readSkipCount/(readCount + readSkipCount)` khi các con số có ý nghĩa so sánh.
- `rollbackCount` để phát hiện transaction xử lý lại nhiều lần.
- Duration bước đọc hoặc item-read Timer nếu phiên bản bật Micrometer instrumentation.
- Số lỗi parse theo loại, nguồn file, schema version.
- Số job/step `FAILED` và số lần restart.
- Số bản ghi được gửi vào quarantine và số bản ghi được sửa/xử lý lại.

Không nên đặt `lineNumber`, `jobExecutionId`, tên khách hàng hoặc raw exception message làm label Prometheus: cardinality có thể tăng cực nhanh và làm lộ dữ liệu. Các giá trị đó phù hợp hơn cho log/audit đã kiểm soát quyền truy cập.

## 12. Unit test reader và lỗi có thể xác định trước

Một unit test cần cho thấy reader xử lý dữ liệu rõ ràng mà không cần datasource hay job context.

### 12.1. Test parse lỗi bằng nguồn cố định

Ví dụ tạo `FlatFileItemReader` từ dữ liệu trong bộ nhớ, rồi gọi `open` và `read` trực tiếp.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.ByteArrayResource;

class FlatFileReaderFailureTest {

    @Test
    void malformedAmountShouldRaiseParseException() throws Exception {
        String csv = """
                order_id,amount
                A-101,120000
                A-102,INVALID_AMOUNT
                """;

        FlatFileItemReader<OrderRow> reader =
                new FlatFileItemReaderBuilder<OrderRow>()
                        .name("ordersTestReader")
                        .resource(new ByteArrayResource(
                                csv.getBytes(StandardCharsets.UTF_8)))
                        .linesToSkip(1)
                        .delimited()
                        .names("order_id", "amount")
                        .fieldSetMapper(fields -> new OrderRow(
                                fields.readString("order_id"),
                                fields.readBigDecimal("amount")))
                        .build();

        reader.open(new ExecutionContext());
        try {
            OrderRow first = reader.read();

            assertEquals("A-101", first.orderId());
            assertEquals(new BigDecimal("120000"), first.amount());

            FlatFileParseException exception = assertThrows(
                    FlatFileParseException.class,
                    reader::read
            );

            assertEquals(3, exception.getLineNumber());
        } finally {
            reader.close();
        }
    }
}
```

Unit test này khẳng định reader ánh xạ dữ liệu và ném exception có thông tin dòng. Nó **chưa khẳng định Spring Batch sẽ skip**: skip/retry thuộc step fault-tolerant, nên cần integration test chạy step thực.

### 12.2. Vì sao không chỉ mock ItemReader?

Nếu chỉ mock:

```java
when(reader.read()).thenThrow(new IllegalArgumentException("bad"));
```

ta không biết reader thực có tiến cursor, đóng file, lưu checkpoint hay ném đúng loại exception khi gặp dữ liệu hỏng không. Mock hữu ích khi test step orchestration độc lập, nhưng việc đọc/parse thật cần được kiểm tra bằng reader production trên fixture có ý nghĩa.

## 13. Integration test: xác nhận skip lỗi reader trong Spring Batch

Ví dụ dưới đây tạo một job độc lập với dữ liệu `"ok"`, `"BAD"` và `"end"`. Reader minh họa đọc ba dòng từ `ByteArrayResource`; mapper cố ý ném lỗi ở dòng `"BAD"`. Ta kiểm tra cùng lúc:

- Step kết thúc `COMPLETED`.
- Hai item hợp lệ được đọc/ghi.
- Một lỗi được tính vào `readSkipCount`.
- `ItemReadListener.onReadError` và `SkipListener.onSkipInRead` được gọi từ framework.
- Writer chỉ nhận item hợp lệ.

Các dependency test cần có `spring-boot-starter-batch`, `spring-batch-test`, `spring-boot-starter-test` và H2 trong test classpath.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ItemReadListener;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = ReaderFailureIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class ReaderFailureIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    RecordedOutput output;

    @Autowired
    ReadErrorCounter readErrors;

    @Autowired
    ReadSkipCounter readSkips;

    @Test
    void malformedLineShouldBeSkippedAndValidRowsWritten()
            throws Exception {

        JobExecution execution = launcher.launchStep("readFailureStep");

        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(2L, step.getReadCount());
        assertEquals(1L, step.getReadSkipCount());
        assertEquals(2L, step.getWriteCount());

        assertEquals(List.of("ok", "end"), output.values);
        assertEquals(1, readSkips.count.get());
        assertEquals("BAD", readSkips.badInput);
        assertTrue(readErrors.count.get() >= 1);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        @StepScope
        FlatFileItemReader<String> inputReader() {
            String input = "ok\nBAD\nend\n";

            return new FlatFileItemReaderBuilder<String>()
                    .name("readFailureTestReader")
                    .resource(new ByteArrayResource(
                            input.getBytes(StandardCharsets.UTF_8)))
                    .lineMapper((line, number) -> {
                        if ("BAD".equals(line)) {
                            throw new IllegalArgumentException(
                                    "Malformed record");
                        }
                        return line;
                    })
                    .build();
        }

        @Bean
        RecordedOutput recordedOutput() {
            return new RecordedOutput();
        }

        @Bean
        ReadErrorCounter readErrorCounter() {
            return new ReadErrorCounter();
        }

        @Bean
        ReadSkipCounter readSkipCounter() {
            return new ReadSkipCounter();
        }

        @Bean
        Step readFailureStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                FlatFileItemReader<String> inputReader,
                RecordedOutput output,
                ReadErrorCounter readErrors,
                ReadSkipCounter readSkips) {

            return new StepBuilder("readFailureStep", repository)
                    .<String, String>chunk(2, transactionManager)
                    .reader(inputReader)
                    .writer(chunk -> chunk.forEach(output.values::add))
                    .faultTolerant()
                    .skip(FlatFileParseException.class)
                    .skipLimit(1)
                    .listener(readErrors)
                    .listener(readSkips)
                    .build();
        }

        @Bean
        Job readerFailureJob(
                JobRepository repository,
                Step readFailureStep) {

            return new JobBuilder("readerFailureJob", repository)
                    .start(readFailureStep)
                    .build();
        }
    }

    static class RecordedOutput {
        final List<String> values = new CopyOnWriteArrayList<>();
    }

    static class ReadErrorCounter implements ItemReadListener<String> {
        final AtomicInteger count = new AtomicInteger();

        @Override
        public void onReadError(Exception error) {
            count.incrementAndGet();
        }
    }

    static class ReadSkipCounter
            implements SkipListener<String, String> {

        final AtomicInteger count = new AtomicInteger();
        volatile String badInput;

        @Override
        public void onSkipInRead(Throwable error) {
            count.incrementAndGet();

            if (error instanceof FlatFileParseException parseError) {
                badInput = parseError.getInput();
            }
        }
    }
}
```

Trong ví dụ, một lỗi parse có thể được framework bỏ qua vì `skipLimit(1)` và `FlatFileParseException` được cho phép. Test chỉ chạy một lượt trên context đã tạo và không yêu cầu chạy song song. Nếu mở rộng nhiều test trên cùng context, nên reset sink/counter ở mỗi lượt và dùng job parameters riêng hoặc làm sạch metadata để tránh collision.

`@StepScope` giúp mỗi step execution có reader và cursor riêng. Writer `RecordedOutput` ở đây chỉ là in-memory sink để thấy item nào tới writer; nó **không chứng minh transaction database**. Nếu cần khẳng định commit/rollback, thay bằng JDBC writer và đọc bảng kết quả ở cơ sở dữ liệu thử nghiệm.

### 13.1. Nếu không cấu hình skip

Bỏ `.faultTolerant().skip(...).skipLimit(...)` hoặc cấu hình `skipLimit(0)`:

```text
Dữ liệu: "ok", "BAD", "end"
Read failure: FlatFileParseException at "BAD"

Kỳ vọng:
  BatchStatus       = FAILED
  readSkipCount     = 0
  failureExceptions = có nguyên nhân lỗi parse
  "end"             = không được xử lý trong execution thất bại đó
```

Không nên khẳng định chính xác output in-memory writer còn `"ok"` hay không nếu thay đổi chunk size hoặc ranh giới transaction, vì dữ liệu in-memory sink không rollback. Với database transactional, hãy kiểm tra dữ liệu đã commit từ **trước** chunk lỗi và xác định ranh giới rollback chính xác.

### 13.2. Trường hợp vượt skip limit

Nếu input có hai dòng `BAD` và `skipLimit(1)`, step có thể bỏ qua lỗi đầu tiên nhưng thất bại khi vượt ngưỡng cho phép. Đây là một test quan trọng để ngăn hệ thống âm thầm coi một file gần như hỏng hoàn toàn là thành công.

## 14. Kiểm thử retry reader có state

Một yêu cầu khác với parse skip: reader gọi service bên ngoài, lần đầu nhận lỗi tạm thời, lần sau trả item thành công.

Mẫu fake reader có thể dùng trong unit test:

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.batch.item.ItemReader;

public final class FlakyReader implements ItemReader<String> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public String read() throws IOException {
        if (attempts.incrementAndGet() == 1) {
            throw new IOException("Temporary network failure");
        }
        return "ORDER-101";
    }

    public int attempts() {
        return attempts.get();
    }
}
```

**Mẫu trên chỉ minh họa một lỗi tạm thời**; nó không thể dùng cho một step đầy đủ vì sau lần thành công nó vẫn tiếp tục trả `"ORDER-101"` thay vì `null`, gây đọc lặp vô hạn. Khi đưa vào integration test, cần một reader hữu hạn với state `notStarted → failedOnce → delivered → EOF`, và lưu checkpoint phù hợp.

Trường hợp test cần chứng minh:

- Lần đọc đầu ném lỗi retryable.
- Lần đọc lại trả item **cùng ý nghĩa nghiệp vụ**.
- `readSkipCount=0` nếu cuối cùng đọc được item.
- Có thể có `onReadError`, nhưng **không có `onSkipInRead`**.
- Output không bị ghi trùng khi retry.

Với client HTTP hay database thực, dùng fake server/driver hoặc mock nguồn bên ngoài để tạo lỗi có kiểm soát. Đừng phụ thuộc vào lỗi mạng ngẫu nhiên hoặc dùng `Thread.sleep(...)` chờ hết timeout để test.

## 15. Kịch bản phục hồi khi step đã FAILED

Giả sử job đọc một file 1 triệu dòng, đã commit 500.000 dòng rồi mất quyền truy cập file.

Một quy trình phục hồi có thể là:

1. **Xác định lỗi thực tế.** Kiểm tra `StepExecution.failureExceptions`, log của reader và status ở `JobRepository`. Phân biệt parse lỗi do dữ liệu, lỗi file bị xóa và lỗi mạng.
2. **Xác minh dữ liệu đã commit.** Xem counter và bảng đích. `readCount` là số item đọc, không phải bằng chứng mọi item đó đã commit vào database nghiệp vụ.
3. **Giữ nguyên đầu vào khi restart.** Khôi phục đúng file/version, checksum và identifying `JobParameters`.
4. **Sửa nguyên nhân.** Khôi phục quyền truy cập, database, đường dẫn hoặc resource; không tự tăng skip limit để che nguyên nhân.
5. **Đánh giá checkpoint.** Reader có `ItemStream` và state hợp lệ không? Writer idempotent/transactional không?
6. **Restart cùng `JobInstance`** khi phù hợp. Spring Batch tạo `JobExecution` mới và sử dụng checkpoint của step để tiếp tục phần chưa xử lý.
7. **Đối soát kết quả.** So sánh số dòng nguồn, số dòng đầu ra, số dòng bị skip và số item trùng; không chỉ dựa vào `BatchStatus.COMPLETED`.

### 15.1. Restart khác với khởi chạy job mới

```text
JobInstance: importOrders + businessDate=2025-05-12
    |
    +-- JobExecution 501: FAILED
    |       StepExecution 1001: FAILED
    |       checkpoint: đã ghi tới vị trí phù hợp
    |
    +-- JobExecution 509: COMPLETED (restart)
            StepExecution 1020: COMPLETED
            khôi phục từ checkpoint cũ
```

Nếu thay identifying parameter `businessDate` hoặc tự thêm identifying `run.id` mới, bạn có thể tạo **JobInstance khác**. Khi đó reader có thể đọc lại từ đầu, gây trùng dữ liệu nếu writer không được thiết kế chống trùng.

Không sửa trực tiếp `BATCH_STEP_EXECUTION` hoặc execution context để “đẩy vị trí đọc qua dòng hỏng” mà không có quy trình phục hồi được kiểm soát; việc đó có thể làm mất dữ liệu hoặc phá tính nhất quán khi restart.

## 16. Những lỗi thiết kế khiến reader failure trở nên nguy hiểm

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Dùng `skip(Exception.class)` cho mọi lỗi | Che lỗi hệ thống và dữ liệu bị hỏng | Chọn exception có thể bỏ qua theo hợp đồng |
| Cấu hình skip cho file không tồn tại | Job có thể diễn giải sai rằng không có dữ liệu | `strict(true)` và fail fast |
| Retry vô hạn lỗi parse | Mất thời gian, step không tiến | Skip giới hạn hoặc fail |
| Retry reader đã tăng cursor nhưng không giữ đúng item | Bỏ sót dữ liệu | Thiết kế tiến độ đọc và retry state rõ ràng |
| Reader không implement `ItemStream` nhưng lại cần restart | Restart đọc sai vị trí hoặc đọc lại từ đầu | Lưu checkpoint qua `ExecutionContext` |
| Đổi file nguồn giữa fail và restart | Offset cũ không còn đúng | Bất biến/version/checksum nguồn |
| Reader có side effect ngoài transaction | Rollback vẫn mất dữ liệu | Tách side effect, dùng inbox/outbox/idempotency |
| Dùng `readerIsTransactionalQueue()` cho mọi reader | Thay đổi buffering/retry semantics | Chỉ bật với nguồn transactional phù hợp |
| Chỉ nhìn `readCount` mà không nhìn `readSkipCount` | Không biết dữ liệu đầu vào bị bỏ qua | Theo dõi bộ đếm và audit |
| Log nguyên nội dung dòng lỗi có dữ liệu nhạy cảm | Rò rỉ dữ liệu | Redact, quarantine có kiểm soát |
| Xem `onReadError` là “đã bỏ qua bản ghi” | Đếm sai khi retry thành công | Dùng `onSkipInRead` và counter skip |
| Test bằng mock reader duy nhất | Bỏ sót lỗi parser/offset/checkpoint | Test reader thật với fixture |
| Viết item vào list in-memory rồi coi rollback đã được kiểm chứng | List không rollback theo DB transaction | Integration test với transaction/database thật |
| Dùng `Thread.sleep` để chờ lỗi mạng | Test chậm, dễ flaky | Fake server/clock/latch hoặc lỗi giả lập |
| Không kiểm tra số item bị bỏ qua trước khi phát dữ liệu | Downstream có thể hiểu dữ liệu thiếu là đủ | Đặt quality gate theo business rule |

## 17. Bài tập thực hành

Xây dựng job `importCustomerCsv` nhận `inputFile` và `businessDate` từ `JobParameters`. File có header và 1.000 dòng, trong đó có dòng thiếu email, dòng sai định dạng ngày sinh, một dòng mã hóa sai và một số dòng hợp lệ.

Yêu cầu:

1. Viết `FlatFileItemReader<CustomerRow>` với tên reader ổn định, `@StepScope`, `strict(true)` và `saveState(true)`.
2. Thiết kế `FieldSetMapper`/validator để phân biệt lỗi parse (reader) và lỗi nghiệp vụ đã đọc thành công (processor).
3. Cho phép skip tối đa 5 dòng parse lỗi, không skip lỗi thiếu file hoặc truy cập database.
4. Tạo `ItemReadListener` và `SkipListener`; ghi audit line number, file version và error category, có khóa chống trùng.
5. Viết unit test với fixture cố định: một dòng hợp lệ, một dòng sai định dạng, một dòng hợp lệ tiếp theo.
6. Viết integration test xác nhận `readCount`, `readSkipCount`, `writeCount` và nội dung bảng đích.
7. Bổ sung test 6 dòng lỗi để chứng minh step thất bại khi vượt `skipLimit(5)`.
8. Mô phỏng reader bị lỗi I/O tại một checkpoint. Giữ nguyên file và restart; kiểm tra không đọc trùng hoặc bỏ sót record đã commit.
9. Thay file nguồn bằng một version khác trước khi restart và giải thích vì sao checkpoint không còn đáng tin.
10. Bổ sung reader đọc từ dịch vụ HTTP có lỗi tạm thời; retry có giới hạn, backoff và bảo đảm không thay đổi cursor nếu response chưa nhận thành công.
11. Kiểm tra trường hợp file chỉ có header và file không tồn tại. Xác định status mong đợi cho từng trường hợp.
12. Phân biệt skip dòng CSV có lỗi và filter một khách hàng hợp lệ nhưng chưa đủ tuổi: hai trường hợp cần tăng counter nào?

**Câu hỏi ôn tập:** Một reader ném `FlatFileParseException` ở dòng số 25. Sau khi cấu hình `skip(FlatFileParseException.class)` và `skipLimit(10)`, có thể kết luận ngay job sẽ tiếp tục an toàn không?

**Trả lời:** Chưa. Cần bảo đảm reader thực sự tiến qua dòng hỏng, skip là điều nghiệp vụ cho phép, số lỗi không vượt giới hạn, checkpoint và writer giữ tính nhất quán, và các dòng còn lại vẫn được xử lý đúng. Cấu hình skip chỉ là **một phần** của chiến lược phục hồi.

## 18. Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html): skip policy, skip limit và ví dụ `FlatFileParseException`.
- [Spring Batch 5.2 — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html): retry exception và retry limit.
- [Spring Batch 5.2 — Controlling Rollback](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/controlling-rollback.html): rollback khi skip và reader transactional.
- [Spring Batch 5.2 — Item Stream](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html): `open`, `update`, `close` và `ExecutionContext`.
- [Spring Batch 5.2 — Flat Files](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/flat-files/file-item-reader.html): `FlatFileItemReader`, line mapper và `FlatFileParseException`.
- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html): `ItemReadListener` và `SkipListener`.
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils` và test step/job.
- [Spring Batch 5.2 API — StepExecution](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): bộ đếm read/skip và failure exceptions.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution` và restart semantics.
