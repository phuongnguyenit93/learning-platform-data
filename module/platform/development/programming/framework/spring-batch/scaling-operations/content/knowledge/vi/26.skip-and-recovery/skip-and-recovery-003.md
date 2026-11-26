# Skip limit và giới hạn an toàn trong Spring Batch

> **Chương:** Skip và recovery
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán phù hợp. Bài này hướng dẫn **giới hạn số lỗi có thể bỏ qua**, cách tránh mất dữ liệu âm thầm và cách giữ an toàn khi retry, restart hoặc chạy nhiều worker cùng lúc.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `skipLimit` hoạt động thế nào đối với lỗi đọc (`read`), xử lý (`process`) và ghi (`write`) trong một `StepExecution`.
2. Phân biệt **skip**, **retry**, **filter** và **rollback**; xác định vì sao một lỗi không nhất thiết được phép skip.
3. Cấu hình `faultTolerant()`, `skip(...)`, `noSkip(...)`, `skipLimit(...)` và `SkipListener` bằng API Spring Batch 5.x.
4. Đặt giới hạn an toàn theo mức độ rủi ro nghiệp vụ, tỷ lệ lỗi, partition, toàn job và các lần restart.
5. Thiết kế kiểm thử ở ngưỡng skip, đối soát item nguồn–đích và runbook xử lý sự cố khi một worker vượt ngưỡng.

## 1. Skip là gì, và tại sao cần giới hạn?

Trong chunk-oriented processing, không phải lỗi nào cũng buộc dừng cả job. Ví dụ một tệp chứa 100.000 bản ghi khách hàng, nhưng ba dòng có ngày sinh sai định dạng. Nếu hợp đồng nghiệp vụ cho phép **cách ly bản ghi lỗi để kiểm tra sau**, job có thể bỏ qua các dòng đó và tiếp tục phần còn lại.

Đó là **skip**: Spring Batch chấp nhận một exception thuộc nhóm được cấu hình là *skippable* và bỏ qua đơn vị item tương ứng theo cơ chế xử lý lỗi của step. Tuy nhiên, bỏ qua item vẫn đồng nghĩa item đó **chưa đạt kết quả nghiệp vụ mong đợi**. Không thể coi skip là “sửa lỗi”.

Nếu không có ngưỡng an toàn, một thay đổi schema hoặc lỗi cấu hình có thể khiến **mọi item đều bị skip** mà job vẫn cố tiếp tục. `skipLimit` là hàng rào để **ngừng step khi số lần skip đã vượt mức chấp nhận**.

~~~mermaid
flowchart TD
    A["Đọc / xử lý / ghi item"] --> B{"Có lỗi?"}
    B -- "Không" --> C["Tiếp tục chunk"]
    B -- "Có" --> D{"Exception có được phép skip?"}
    D -- "Không" --> F["Lỗi step hoặc nhánh retry đã cấu hình"]
    D -- "Có" --> E{"Còn ngân sách skip?"}
    E -- "Có" --> G["Bỏ item lỗi<br/>tăng counter skip phù hợp"]
    E -- "Hết" --> H["Vượt giới hạn → step FAILED"]
    G --> C
~~~

Sơ đồ là mô hình khái niệm; ở runtime, **retry**, rollback giao dịch và cơ chế cô lập item lỗi trong writer có thể diễn ra trước khi kết luận skip. Không suy rằng một exception luôn chuyển thẳng đến skip.

### Khi nào skip hợp lý?

| Tình huống | Có thể xem xét skip? | Điều kiện |
| --- | --- | --- |
| Một dòng CSV hỏng định dạng, có thể lưu bản gốc để sửa | Có | Dữ liệu lỗi được cách ly, có lý do và kế hoạch xử lý lại |
| Email không hợp lệ trong bản ghi marketing không bắt buộc | Có thể | Hợp đồng dữ liệu cho phép, có ngưỡng và đối soát |
| Lỗi định dạng của một trường tài chính bắt buộc | Thường **không** | Có thể phải dừng để tránh kết quả tài chính thiếu |
| Database mất kết nối trong vài giây | Thường **retry**, không skip | Lỗi hạ tầng có thể ảnh hưởng cả lô, không phải một item cá biệt |
| Unique constraint bất ngờ hoặc sai schema DB | Thường **fail/điều tra** | Có thể là lỗi thiết kế, duplicate hoặc dữ liệu không nhất quán |
| Lỗi lập trình `NullPointerException` | **Không** theo mặc định | Không nên che lỗi code bằng skip rộng |
| Gửi thanh toán không rõ thành công hay thất bại | **Không tự động skip** | Cần xác nhận trạng thái từ hệ thống nhận và idempotency |

**Quy tắc:** Chỉ skip exception **được xác định rõ là lỗi của item**, có thể giải thích, ghi nhận và xử lý bù sau. Lỗi hạ tầng hoặc lỗi hệ thống cần chính sách riêng, không nên dùng skip như một cách làm job “xanh”.

## 2. skipLimit đếm gì?

Một `StepExecution` có ba counter quan trọng:

- `readSkipCount`: số item/lần lỗi đọc được chấp nhận bỏ qua theo xử lý đọc.
- `processSkipCount`: số item lỗi trong `ItemProcessor` được skip.
- `writeSkipCount`: số item bị bỏ qua do lỗi tại `ItemWriter`.

Tổng số skip ở cấp step được xem qua `StepExecution.getSkipCount()`, về mặt khái niệm là:

~~~text
skipCount = readSkipCount + processSkipCount + writeSkipCount
~~~

**`skipLimit(10)` cho phép tối đa 10 skip được chấp nhận trong một step execution; lần skip thứ 11 sẽ khiến step không tiếp tục theo chính sách skip đó.** Limit này **không** phải 10 lỗi đọc cộng 10 lỗi xử lý cộng 10 lỗi ghi.

Ví dụ:

| Thời điểm | readSkipCount | processSkipCount | writeSkipCount | Tổng | Kết quả |
| --- | ---: | ---: | ---: | ---: | --- |
| Sau chunk 1 | 1 | 2 | 0 | 3 | Còn ngân sách |
| Sau chunk 2 | 1 | 6 | 1 | 8 | Còn ngân sách |
| Sau chunk 3 | 2 | 7 | 1 | 10 | Vẫn ở ngưỡng được phép |
| Item lỗi tiếp theo thuộc loại được skip | 2 | 8 (dự kiến) | 1 | 11 (dự kiến) | **Vượt ngưỡng → thất bại** |

Lần skip vượt giới hạn không được coi là một skip thành công để job tiếp tục; counter và cách exception được ghi nhận tại thời điểm failure phụ thuộc luồng transaction và implementation. Quan trọng là **không thể xử lý thêm bằng cơ chế skip** khi đã hết ngân sách.

### Những con số không thuộc skipLimit

| Counter hoặc sự kiện | Có tiêu thụ ngân sách skip? | Ghi chú |
| --- | --- | --- |
| Processor trả `null` theo quy tắc filter | **Không** | Tăng `filterCount`; đây là lọc chủ động, không phải exception |
| Một lỗi transient được retry rồi thành công | **Không tạo skip** | Có thể tăng retry/rollback-related metrics tùy giai đoạn |
| Transaction rollback, item được xử lý lại thành công | **Không mặc nhiên** | Rollback count không đồng nghĩa skip count |
| Writer thành công nhưng `ON CONFLICT DO NOTHING` không insert | **Không** | Đây là kết quả SQL/logic writer, không phải skip framework |
| Exception không nằm trong nhóm skippable | **Không được bỏ qua** | Step có thể fail dù còn nhiều ngân sách |
| Skip được chấp nhận ở read/process/write | **Có** | Thuộc cùng ngân sách của `StepExecution` |

`skipLimit(0)` là một lựa chọn hợp lệ khi nghiệp vụ **không cho phép skip bất kỳ item nào**. Không thay thế quy tắc fail-fast bằng một ngưỡng thật lớn chỉ để job không dừng.

## 3. Skip, filter, retry và recovery khác nhau ở đâu?

### Filter: item không thuộc tập cần ghi

`ItemProcessor.process(item)` trả về `null` là **filter**. Ví dụ bỏ qua đơn hàng đã hủy theo quy tắc đã biết. Filter có thể là một phần nghiệp vụ bình thường, không phải lỗi dữ liệu.

~~~java
@Override
public OutputOrder process(InputOrder item) {
    if ("CANCELLED".equals(item.status())) {
        return null; // Filter: không tiêu thụ skip limit.
    }
    return transform(item);
}
~~~

### Retry: thử lại lỗi có thể tạm thời

Retry phù hợp với lỗi transient như timeout có khả năng phục hồi. Khi retry thành công, item không cần bị skip. Khi số lần retry đã dùng hết, exception tiếp tục được xử lý theo policy hiện hành: có thể fail hoặc được skip **nếu loại lỗi và giới hạn cho phép**. Không mặc định mọi lỗi retry được cũng nên skip.

### Skip: chấp nhận loại item lỗi ra khỏi kết quả

Ví dụ `InvalidOrderRecordException` cho trường dữ liệu không hợp lệ. Sau khi giới hạn cho phép, step tiếp tục với item khác; item lỗi cần có đường audit/quarantine/reprocess.

### Rollback: hoàn tác giao dịch chưa commit

Một writer exception có thể làm rollback cả chunk trước khi framework xác định item gây lỗi. Việc một chunk rollback **không** có nghĩa tất cả item trong chunk đều được skip. Các item hợp lệ có thể được thử ghi lại; writer phải được thiết kế để xử lý transaction và retry/replay đúng.

~~~text
Exception
    ├─ Không cho retry/skip → có thể fail step
    ├─ Retry được → thử lại trong giới hạn
    │     ├─ Thành công → không skip item
    │     └─ Hết retry → xét chính sách skip/fail
    └─ Skippable và còn ngân sách → skip item phù hợp
              └─ Ghi nhận/audit rồi tiếp tục
~~~

Đây là mô hình quyết định đơn giản hóa; thứ tự retry/skip trên từng giai đoạn phụ thuộc cấu hình fault-tolerant step, loại exception và tình trạng transaction.

## 4. Cấu hình skipLimit trong Spring Batch 5.x

Giả sử reader đọc một file CSV, processor kiểm tra dữ liệu và writer ghi database. Chỉ hai loại lỗi được chấp nhận bỏ qua:

1. `FlatFileParseException`: một dòng input không parse được.
2. `InvalidOrderRecordException`: một item sai quy tắc kiểm tra dữ liệu đã được định nghĩa.

Ví dụ cấu hình:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileParseException;
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
            .noSkip(IllegalStateException.class)
            .skipLimit(10)
            .listener(skipListener)
            .build();
}
~~~

`InputOrder`, `OutputOrder` và `InvalidOrderRecordException` là kiểu do dự án tự định nghĩa. `SkipListener` thuộc `org.springframework.batch.core.SkipListener`; ví dụ đã lược bỏ khai báo `@Configuration` và các import Spring bean annotation.

Giải thích các cấu hình:

- `faultTolerant()` bật builder hỗ trợ retry/skip cho chunk step.
- `skip(...)` chỉ định **loại exception** cho phép cân nhắc skip.
- `noSkip(...)` xác định exception **không được skip**, kể cả khi một lớp cha có thể được cấu hình skippable; nên dùng cho các trường hợp phải fail-fast.
- `skipLimit(10)` là **ngưỡng tổng** của read/process/write skip đối với execution của step.
- `listener(skipListener)` cho phép quan sát các item được skip, phục vụ audit/quarantine.

**Không nên cấu hình `skip(Exception.class)` hoặc `skip(Throwable.class)` bừa bãi.** Điều đó có thể biến lỗi runtime, lỗi database, bug lập trình và các lỗi nghiêm trọng thành item bị bỏ qua. Nên xây exception chuyên biệt cho validation và cho phép skip **theo danh sách rõ ràng**.

### Ví dụ exception nghiệp vụ chuyên biệt

~~~java
public class InvalidOrderRecordException extends RuntimeException {
    public InvalidOrderRecordException(String message) {
        super(message);
    }
}
~~~

Processor có thể ném exception này cho lỗi input được phép cách ly, trong khi các exception khác vẫn làm step thất bại hoặc qua nhánh retry riêng:

~~~java
public OutputOrder process(InputOrder input) {
    if (input.orderCode() == null || input.orderCode().isBlank()) {
        throw new InvalidOrderRecordException(
                "Thiếu mã đơn hàng cho source record " + input.sourceId());
    }
    return mapToOutput(input);
}
~~~

Hãy tránh chứa PII hoặc dữ liệu bí mật trong exception message; source ID có thể được băm hoặc thay bằng mã tham chiếu an toàn theo chính sách log.

## 5. Kết hợp retry và skip mà không che giấu sự cố

Khi cần chịu lỗi transient, cấu hình retry cho nhóm lỗi được xác định:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderRecordException.class)
.skip(FlatFileParseException.class)
.skipLimit(10)
~~~

Đây là **đoạn builder bổ sung**; `TransientDataAccessException` thuộc Spring DAO. Nó biểu thị chiến lược:

- Lỗi validation/parse thuộc nhóm được skip, **không cần retry vô ích** nếu input không thay đổi.
- Lỗi database transient có cơ hội retry.
- Khi retry transient vẫn thất bại mà không thuộc nhóm `skip(...)`, **đừng tự động bỏ item**; step nên dừng để vận hành xử lý vấn đề hạ tầng.

`retryLimit(3)` là giới hạn áp dụng theo cơ chế retry của Spring Batch (bao gồm lần thử đầu trong các diễn giải API phổ biến); khi thiết kế test, hãy xác nhận số lần method được gọi ở phiên bản cụ thể thay vì đoán theo tên tham số.

### Vì sao write skip phức tạp hơn process skip?

Nếu processor ném validation exception cho một item đã biết, framework có thể xác định item gây lỗi tương đối rõ. Nhưng khi writer nhận cả chunk và báo exception, không phải lúc nào nó cũng chỉ ra **item nào** bị lỗi.

Ví dụ một chunk có 100 item; writer `INSERT` batch thất bại do một unique constraint. Hạ tầng fault-tolerant có thể rollback rồi thử ghi theo cách giúp phân lập item lỗi, tùy khả năng transaction và writer. Những item hợp lệ trong chunk có thể được xử lý nhiều lần trước khi commit.

Điều này dẫn tới yêu cầu:

- Processor không tạo tác dụng phụ không thể rollback; xử lý lại một item phải an toàn.
- Writer phải an toàn khi được gọi lại và tuân thủ ranh giới transaction.
- Không `skip(DataIntegrityViolationException.class)` một cách rộng rãi: constraint failure có thể thể hiện bug, input sai hoặc xung đột nghiệp vụ cần giải quyết.
- Nếu writer ghi sang HTTP/API hoặc message broker không tham gia transaction, phải có **idempotency key** và cơ chế đối soát trạng thái bên ngoài.

## 6. Skip limit là ngân sách của StepExecution, không phải toàn job

Đây là điểm đặc biệt quan trọng trong module **SPRING_BATCH_SCALING_OPERATIONS** khi scale từ một step sang nhiều partition.

Với partitioning, một manager step có thể tạo 8 worker `StepExecution`. Giả sử mỗi worker step đều cấu hình:

~~~java
.faultTolerant().skip(InvalidOrderRecordException.class).skipLimit(10)
~~~

Mỗi worker có **bộ đếm skip và chính sách step** của riêng execution đó. Nếu tám worker đều sử dụng hết 10 skip, toàn bộ job có thể có tới **80 bản ghi lỗi đã được skip trong các execution ấy**, dù mỗi worker vẫn nằm trong giới hạn.

| Partition | read skip | process skip | write skip | Tổng skip worker | Đạt ngưỡng 10? |
| --- | ---: | ---: | ---: | ---: | --- |
| `range-0000` | 1 | 9 | 0 | 10 | Có |
| `range-0001` | 0 | 5 | 0 | 5 | Chưa |
| `range-0002` | 0 | 10 | 0 | 10 | Có |
| `range-0003` | 2 | 4 | 1 | 7 | Chưa |
| **Tổng bốn worker** | **3** | **28** | **1** | **32** | Không có “limit 10 toàn job” |

**Không có một `skipLimit` mặc định áp lên tổng tất cả worker của cùng job.** Với parallel steps cũng phải phân biệt budget của từng step. Tại remote partitioning, worker ở JVM khác vẫn mang ý nghĩa budget cấp `StepExecution`; broker không tự tính ngưỡng lỗi nghiệp vụ toàn cục.

### Ví dụ yêu cầu nghiệp vụ “tối đa 15 item lỗi toàn job”

Nếu nghiệp vụ chỉ cho phép tối đa 15 item hỏng trên toàn bộ dữ liệu, đặt `skipLimit(15)` ở mỗi worker là **không đủ**. Có vài chiến lược:

1. **Bước validation trước khi chia partition:** Quét và phân loại input; chỉ triển khai load chính thức khi tổng lỗi nằm trong giới hạn. Phù hợp khi input snapshot/manifest cố định và cần fail-fast.
2. **Ghi bảng quarantine/ledger dùng chung:** Mỗi item lỗi có business key và mã lỗi riêng; kiểm đếm tổng **item lỗi duy nhất**, không chỉ raw callbacks.
3. **Bộ điều phối giới hạn toàn cục:** Dùng một cơ chế lưu bền vững, có thao tác kiểm tra/tăng quota atomic để chặn vượt ngưỡng trước khi chấp nhận skip; cần xử lý tính nhất quán với rollback và worker chết giữa giao dịch.
4. **Đối soát hậu kiểm:** Sau khi worker hoàn thành, nếu tổng lỗi vượt ngưỡng thì **đánh dấu job/bước kiểm toán không đạt** và ngăn publish dữ liệu ra downstream. Chỉ phù hợp nếu kết quả tạm được cách ly, vì dữ liệu có thể đã được ghi trước khi kiểm tra.

Không dùng một biến `static AtomicInteger` trong manager để làm ngưỡng lỗi toàn cục: nó không bảo đảm đúng khi có nhiều JVM, crash/restart hoặc job chạy trên nhiều pod.

### Tỷ lệ lỗi cũng quan trọng

Một skip limit tuyệt đối không cân bằng giữa partition có 50 item và partition có 5 triệu item.

Ví dụ:

~~~text
Partition A: 10 skip / 50 item        = 20% lỗi
Partition B: 10 skip / 5.000.000 item = 0,0002% lỗi
~~~

Cùng một số skip, mức độ chất lượng dữ liệu khác hẳn. Một chính sách an toàn có thể đặt đồng thời **mức tuyệt đối** và **tỷ lệ**, ví dụ “không quá 10 lỗi/worker, tổng lỗi toàn job không quá 100, tỷ lệ lỗi cuối cùng không quá 0,1%” (đây là các con số **minh họa**, không phải khuyến nghị mặc định).

Lưu ý tỷ lệ phải có **mẫu số nghiệp vụ xác định**: tổng bản ghi input ở snapshot, tổng record đủ điều kiện, hay tổng item đã được reader trả về? `readCount` có thể không bao gồm các dòng bị lỗi ngay trong quá trình đọc; vì vậy không tùy tiện tính phần trăm từ `readCount` mà bỏ qua `readSkipCount` và các filter.

## 7. Custom SkipPolicy: khi quy tắc không chỉ là một con số

Spring Batch cho phép thay cách quyết định item có được bỏ qua bằng `SkipPolicy`. Một policy có thể phân loại exception và kiểm tra số lần đã skip.

~~~java
import org.springframework.batch.core.step.skip.SkipPolicy;
import org.springframework.batch.item.file.FlatFileParseException;

public final class StrictInputSkipPolicy implements SkipPolicy {
    private final long limit;

    public StrictInputSkipPolicy(long limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("limit không được âm");
        }
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable failure, long skipCount) {
        boolean eligible =
                failure instanceof InvalidOrderRecordException
                || failure instanceof FlatFileParseException;

        if (!eligible) {
            return false; // Lỗi hệ thống không nằm trong whitelist.
        }

        // Framework có thể dùng skipCount âm khi kiểm tra phân loại
        // mà chưa quyết định chấp nhận skip thực tế.
        if (skipCount < 0) {
            return true;
        }

        return skipCount < limit; // Lần skip làm vượt limit bị từ chối.
    }
}
~~~

Với chiến lược này, thay phần `skip(...)`/`skipLimit(...)` bằng:

~~~java
.faultTolerant()
.skipPolicy(new StrictInputSkipPolicy(10))
~~~

Đây là ví dụ **thay thế**, không yêu cầu cấu hình thêm `skipLimit(10)` bên cạnh policy tự viết. Khi custom policy được sử dụng, phải tự kiểm thử đầy đủ các điều kiện giới hạn và exception classification; đừng mặc định hai cơ chế limit hoạt động cộng dồn theo cách mong muốn.

**Thận trọng:** `SkipPolicy.shouldSkip(...)` quyết định việc skip dựa trên exception và số lần skip do framework đưa vào; nó không tự cung cấp **tỷ lệ lỗi toàn job**, tổng số business record duy nhất hay transaction phân tán. Muốn policy theo tỷ lệ/tổng job phải thiết kế thêm nguồn đếm đáng tin cậy và kiểm thử cạnh tranh/restart. Với trường hợp đơn giản, ưu tiên builder `skip(...).skipLimit(...)` vì dễ hiểu và vận hành.

## 8. Ghi nhận item bị skip: SkipListener và quarantine

Một step “thành công nhưng skip 9 item” chỉ chấp nhận được khi hệ thống có khả năng **trả lời chín item đó là gì, vì sao lỗi và ai sẽ xử lý**.

Spring Batch cung cấp `SkipListener<I,O>` với các callback:

~~~java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
~~~

Ví dụ listener ghi log ở mức định danh kỹ thuật:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipLogger
        implements SkipListener<InputOrder, OutputOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipLogger.class);

    @Override
    public void onSkipInRead(Throwable failure) {
        // Có thể không có đối tượng item khi reader không parse được.
        log.warn("Read skip: type={}",
                failure.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(InputOrder item, Throwable failure) {
        log.warn("Process skip: sourceId={} type={}",
                item.sourceId(),
                failure.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(OutputOrder item, Throwable failure) {
        log.warn("Write skip: sourceId={} type={}",
                item.sourceId(),
                failure.getClass().getSimpleName());
    }
}
~~~

`InputOrder` và `OutputOrder` là các kiểu minh họa có `sourceId()`; cần thay theo model thực tế. Log không phải một **quarantine store bền vững**. Nếu lỗi cần sửa và chạy lại, nên lưu nguồn/bản gốc hoặc tham chiếu an toàn trong hệ thống riêng.

### Audit/quarantine đáng tin cậy cần gì?

| Trường | Vai trò |
| --- | --- |
| JobInstance/JobExecution/StepExecution hoặc partition key | Truy dấu lần chạy và phạm vi |
| Business/source ID (hoặc file + line number) | Nhận diện **item lỗi duy nhất** |
| Loại lỗi/mã validation | Phân nhóm để sửa |
| Input version/snapshot | Tránh sửa nhầm phiên bản dữ liệu |
| Trạng thái xử lý lỗi | New, triaged, fixed, replayed, rejected |
| Dấu thời gian và phiên bản xử lý | Audit và theo dõi SLA |

Nếu cùng item có thể được gặp lại khi rollback/restart, record quarantine nên có **unique key/idempotency key** để không tạo bản lỗi trùng lặp. Việc callback được gọi trong vòng đời transaction không đồng nghĩa ghi sang dịch vụ HTTP hoặc queue bên ngoài sẽ rollback được. Ưu tiên lưu audit bằng transaction phù hợp hoặc outbox với cơ chế phát lại an toàn.

Đối với lỗi đọc từ CSV, reader không nhất thiết tạo được `InputOrder`. Có thể lưu file ID, số dòng và mã lỗi từ `FlatFileParseException` theo cách **không lộ nội dung nhạy cảm**; không tùy tiện log toàn bộ raw line.

## 9. Giới hạn an toàn: không chỉ skipLimit

Một production policy cần nhiều “hàng rào” bổ sung.

### 9.1. Whitelist loại lỗi được bỏ qua

Không skip exception hạ tầng, lỗi schema, lỗi bảo mật, lỗi số dư/tài chính, lỗi vi phạm bất biến nghiệp vụ cốt lõi. Dùng exception phân biệt rõ **bad record** với **system failure**.

### 9.2. Giới hạn tuyệt đối và tỷ lệ

Chốt mức tối đa theo:

- **Một worker StepExecution:** `skipLimit`.
- **Một tập dữ liệu/JobInstance:** bảng audit hoặc bước validation/đối soát.
- **Một nhóm nghiệp vụ quan trọng:** ví dụ “không bỏ qua bất kỳ giao dịch thanh toán bắt buộc nào”, dù tổng lỗi chung rất nhỏ.
- **Tỷ lệ theo phân đoạn:** tenant, loại file, ngày giao dịch, vùng dữ liệu; tránh để lỗi tập trung ở một partition bị che trong tổng toàn job.

### 9.3. Ranh giới publish dữ liệu

Nếu output sau xử lý có thể được downstream tiêu thụ ngay, hậu kiểm skip limit **không thể thu hồi tác dụng phụ đã xảy ra**. Với pipeline quan trọng, cân nhắc ghi vào staging, kiểm tra tổng lỗi và chất lượng dữ liệu rồi **publish theo một bước riêng**.

### 9.4. Theo dõi lỗi liên tiếp

Một chuỗi 20 item lỗi liên tiếp có thể thể hiện thay đổi format đầu vào hơn là 20 trường hợp độc lập. `skipLimit` không phải cơ chế mặc định theo dõi **số lỗi liên tiếp**. Nếu cần, triển khai guardrail trong validation/giai đoạn đọc hoặc policy bổ sung có state được quản lý an toàn, có kiểm thử rollback/restart và partitioning.

### 9.5. Không tự động “skip cho xanh dashboard”

Ngưỡng nên được duyệt theo **mức độ thiệt hại khi mất một item** và khả năng xử lý bù. Một job có `BatchStatus.COMPLETED` nhưng 100 item quan trọng bị bỏ qua không nhất thiết là kết quả nghiệp vụ thành công.

## 10. Skip limit khi partitioning, retry và restart

Trong partitioned step, mỗi worker có `StepExecution` và `ExecutionContext` riêng. Khi một worker fail vì vượt skip limit, các worker khác có thể đã commit nhiều chunk hoặc thậm chí đã `COMPLETED`.

~~~mermaid
flowchart TD
    M["Manager PartitionStep"] --> A["Worker A: 2 skips<br/>COMPLETED"]
    M --> B["Worker B: 11th candidate skip<br/>FAILED"]
    M --> C["Worker C: 0 skips<br/>COMPLETED"]
    A --> R[("JobRepository")]
    B --> R
    C --> R
    R --> D["Restart cùng JobInstance<br/>sau khi sửa lỗi"]
    D --> E["Splitter chọn worker cần chạy lại"]
    E --> F["Worker B: checkpoint/context phù hợp"]
~~~

**Điểm cần nhớ khi restart:**

1. Lịch sử và skip counters của các `StepExecution` trước đây vẫn hữu ích cho audit; lần restart có thể tạo `StepExecution` mới cho phần việc cần chạy lại.
2. Không giả định một `skipLimit` cấu hình ở worker tạo ra **ngân sách lỗi tích lũy của toàn JobInstance qua mọi attempt**. Nếu nghiệp vụ có budget xuyên lần chạy, dùng ledger/quy tắc tập trung được thiết kế rõ.
3. Partition key → phạm vi input phải ổn định; nếu đổi kế hoạch, checkpoint và đối soát skip có thể chỉ tới phần việc khác.
4. Những partition đã `COMPLETED` thường không phải chạy lại theo chính sách restart thông thường. Các partition chưa hoàn tất được lựa chọn theo metadata và cấu hình.
5. Quarantine record phải chịu được replay; không cộng callback audit của nhiều lần chạy rồi coi là số **item lỗi duy nhất** nếu chưa dedupe.
6. Nếu skip làm mất item nghiệp vụ quan trọng, sau khi sửa dữ liệu có thể cần một **job replay có kiểm soát**; restart job cũ không mặc nhiên xử lý lại những item đã được skip ở các partition `COMPLETED`.

### Ví dụ cần đặc biệt cảnh giác

Job đầu tiên có bốn partition, mỗi worker `skipLimit(5)`. Worker A và B `COMPLETED` sau khi skip tổng 10 item; worker C fail vì vượt limit, worker D hoàn tất không có lỗi. Sau khi sửa dữ liệu của C và restart, splitter có thể chỉ chạy lại C. **Mười item đã skip trong A/B không tự quay lại được xử lý** chỉ vì toàn job được restart. Cần quy trình quản lý danh sách lỗi và replay các item đó riêng.

## 11. Đo nút thắt và hậu quả hiệu năng

Skip không miễn phí. Khi tỷ lệ lỗi tăng:

- Parse/validation exception và stack trace có thể tiêu tốn CPU.
- Logging quá nhiều có thể tạo I/O và tăng chi phí lưu trữ.
- Write skip có thể gây rollback/retry chunk, làm tăng write latency và số transaction.
- Nhiều worker cùng lỗi có thể gây “exception storm”, tạo áp lực lên log pipeline, database và audit/quarantine store.
- Metadata repository và monitor cần đọc counters của nhiều `StepExecution`.

### Các metric nên theo dõi

| Phạm vi | Chỉ số | Giúp trả lời |
| --- | --- | --- |
| Worker | `readSkipCount`, `processSkipCount`, `writeSkipCount` | Lỗi xảy ra ở giai đoạn nào? |
| Worker | `skipCount`, mức dùng budget (%) | Có gần vượt `skipLimit` không? |
| Worker | `readCount`, `writeCount`, `filterCount`, `rollbackCount` | Lượng dữ liệu đi qua và giao dịch có ổn định không? |
| Manager/job | Số partition `FAILED`/`COMPLETED` và tổng skip | Chất lượng toàn workload ra sao? |
| Nguồn/đích | Số business key unique, số item quarantine, missing/duplicate | Dữ liệu có đúng không? |
| Hạ tầng | CPU, DB connection pool, transaction latency, log throughput | Lỗi có trở thành bottleneck khi scale không? |

Không dùng `writeCount` để suy ra số hàng mới trong database nếu writer có upsert/no-op. Không dùng tổng `skipCount` qua mọi attempt để kết luận số bản ghi lỗi duy nhất mà không loại trùng.

### Một ngưỡng kỹ thuật và một ngưỡng nghiệp vụ

Ví dụ vận hành (số **minh họa**):

- `skipLimit(10)` cho mỗi worker: ngừng phần việc sớm nếu dữ liệu lỗi quá nhiều.
- Cảnh báo khi worker có ≥ 5 skip để điều tra trước khi chạm trần.
- Bước reconciliation cuối job: chỉ chấp nhận ≤ 20 **business key lỗi duy nhất** trong snapshot và tỷ lệ ≤ 0,05%.
- Nếu vượt ngưỡng, chặn bước publish hoặc đánh dấu chất lượng job không đạt dù các worker độc lập có thể đã `COMPLETED`.

Phải xác định nơi lưu số liệu và cách xử lý **cạnh tranh giữa các worker**, đặc biệt với remote partitioning. Không chỉ dùng metric có độ trễ hoặc `AtomicInteger` trong một JVM để thực hiện quyết định có tính giao dịch.

## 12. Kiểm thử ở ngưỡng và ở tình huống lỗi thực

### 12.1. Kiểm tra đúng biên skipLimit

Với `skipLimit(3)` và ba item ném `InvalidOrderRecordException`:

| Số item skippable lỗi | Kỳ vọng |
| ---: | --- |
| 0 | Step xử lý bình thường |
| 1 | Skip được chấp nhận |
| 2 | Skip được chấp nhận |
| 3 | Vẫn được chấp nhận, ở đúng ngưỡng |
| 4 | Step thất bại vì **vượt ngưỡng** |

Nên test cả **exception không được skip ở item đầu tiên**: step phải fail ngay theo policy dù budget còn ba. Nếu processor trả `null` cho 20 item hợp lệ cần filter, `filterCount` tăng nhưng không tiêu thụ skip limit.

### 12.2. Khung integration test bằng JobLauncherTestUtils

~~~java
@SpringBatchTest
@SpringJUnitConfig(classes = ImportOrdersTestConfig.class)
class SkipLimitIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void lanSkipThuTuLamStepFailed() throws Exception {
        // Fixture: một input snapshot cố định có bốn item
        // ném InvalidOrderRecordException;
        // test job sử dụng skipLimit(3).
        JobParameters params = new JobParametersBuilder()
                .addString("testRunId", "skip-limit-004")
                .toJobParameters();

        JobExecution result = jobLauncherTestUtils.launchJob(params);

        assertEquals(BatchStatus.FAILED, result.getStatus());

        // Hoàn thiện assertion:
        // - kiểm tra worker StepExecution FAILED;
        // - kiểm tra skip counters và exception theo policy;
        // - đối soát output/quarantine;
        // - bảo đảm item thứ tư không bị coi là skip thành công.
    }
}
~~~

Đây là **khung test**, cần dự án định nghĩa `ImportOrdersTestConfig`, fixture dữ liệu, job, repository, transaction manager và imports `org.springframework.batch.test.context.SpringBatchTest`, `JobLauncherTestUtils`, JUnit 5. Không coi đoạn code là test độc lập có thể chạy ngay không cần môi trường.

### 12.3. Ma trận test nên có

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Đúng 10 skip với limit 10 | Không fail chỉ vì chạm ngưỡng |
| Lần skip thứ 11 | Step fail; không tiếp tục âm thầm |
| Lỗi không nằm trong whitelist | Fail dù ngân sách còn |
| Processor trả `null` | Tăng filter, không tăng skip |
| Lỗi transient retry rồi thành công | Không tính thành một skip |
| Read/process/write skip trộn nhau | Tổng cùng tiêu thụ một ngân sách cấp step |
| Write error làm rollback chunk | Item hợp lệ không mất/nhân đôi dữ liệu |
| Hai partition, mỗi worker limit 3 | Không có “limit 3 toàn job” mặc định |
| Remote message được giao lại | Quarantine/idempotency không tạo side effect trùng |
| Worker fail rồi restart | Partition identity, checkpoint và budget nghiệp vụ xuyên attempt đúng |
| Worker `COMPLETED` đã skip item | Các item đó chỉ được reprocess qua đường có chủ đích |
| Audit callback lỗi | Chính sách failure, transaction và điều tra phải rõ ràng |

**Điểm khó:** Test không chỉ assert `BatchStatus`. Một integration test đáng tin cậy nên so sánh **tập business key nguồn**, **tập đã ghi**, **tập quarantine** và **tập filter hợp lệ**, bảo đảm không có item nào biến mất không giải thích được.

## 13. Runbook khi vượt skip limit trên production

Khi một partition thất bại vì vượt ngưỡng:

1. **Xác định đối tượng:** Ghi nhận `JobInstance`, `JobExecution`, `StepExecutionId`, partition key, tên step và snapshot/manifest input.
2. **Đọc lỗi gốc:** Exception loại nào, phát sinh ở read/process/write, có sự cố chung của parser/schema/DB hay không?
3. **Phân loại dữ liệu lỗi:** Lấy business ID hoặc file/line number từ audit store, tránh log dữ liệu nhạy cảm.
4. **Kiểm tra phạm vi:** Lỗi chỉ xuất hiện ở một partition/tenant hay nhiều worker đồng loạt?
5. **Kiểm tra giao dịch:** Bao nhiêu chunk đã commit, bao nhiêu rollback, writer có side effect ngoài transaction không?
6. **Đối soát phần đã xử lý:** Dựa vào business key, không chỉ cộng `readCount`/`writeCount`.
7. **Khắc phục nguyên nhân:** Sửa dữ liệu/snapshot đúng quy trình hoặc khắc phục parser, code, schema, hạ tầng. Không tăng limit ngay như phản xạ đầu tiên.
8. **Đánh giá ngân sách:** Nếu nghiệp vụ chấp nhận thêm lỗi, thay đổi policy phải được phê duyệt và tính đến tổng job, partition và các lần chạy.
9. **Restart có kiểm soát:** Giữ partition key → input và checkpoint ổn định; kiểm tra worker cũ thực sự đã dừng, đặc biệt trong remote partitioning.
10. **Đối soát sau khi hoàn thành:** Kiểm tra dữ liệu nguồn–đích, quarantine, duplicate, tổng giao dịch; chỉ publish khi đạt tiêu chuẩn chất lượng.

### Khi nào nên dừng thay vì tăng limit?

Nên ưu tiên dừng khi lỗi tăng đồng loạt sau deploy, một loại dữ liệu tài chính quan trọng bị mất, parser nhận sai schema, writer có thể tạo side effect không kiểm soát, hoặc tổng số item bị loại đã vượt cam kết chất lượng. Trong các tình huống này, việc sửa `skipLimit(10)` thành `skipLimit(1000000)` chỉ che dấu lỗi và có thể khiến hậu quả nặng hơn.

## 14. Bài tập tình huống

**Bối cảnh:** Một import job chia 2 triệu đơn hàng thành 8 partition. Mỗi worker có `skipLimit(10)` và processor bỏ qua `InvalidOrderRecordException`. Đợt chạy đầu:

- Sáu partition `COMPLETED`, mỗi partition đã skip 7 item.
- Một partition `COMPLETED`, skip 10 item.
- Partition cuối vượt ngưỡng ở item lỗi thứ 11 và `FAILED`.
- Hệ thống downstream đã đọc dữ liệu commit từ bảy partition đầu.

Trưởng nhóm nói: “Limit là 10, vậy tối đa chỉ có 10 bản ghi lỗi toàn job. Chỉ việc nâng skipLimit lên 20 và restart là xong”.

**Câu hỏi:**

1. Vì sao nhận định “chỉ 10 bản ghi lỗi toàn job” sai?
2. Khi restart, những partition đã `COMPLETED` có tự xử lý lại item đã skip hay không?
3. Vì sao thay `skipLimit` không tự giải quyết chất lượng dữ liệu hoặc side effect đã phát hành downstream?
4. Nếu nghiệp vụ yêu cầu tổng lỗi unique toàn job ≤ 20, cần bổ sung gì?
5. Bạn sẽ kiểm thử ở những biên nào để bảo đảm không có mất dữ liệu âm thầm?

**Định hướng trả lời:** Limit là **theo `StepExecution`**, không phải tổng job. Bảy partition hoàn tất đã skip tổng `6 × 7 + 10 = 52` item, chưa kể worker lỗi. Restart thường chỉ chọn phần việc chưa hoàn tất; item đã skip ở worker hoàn tất không tự được xử lý lại. Cần quarantine, đối soát theo business key, giới hạn toàn JobInstance và ranh giới staging/publish để có thể chặn kết quả không đạt. Test đúng limit, vượt limit, lỗi non-skippable, filter, retry, rollback writer, restart và remote replay.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): `skip`, `skipLimit` và ví dụ cấu hình.
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): cơ chế retry cho lỗi transient.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listener và lifecycle của step.
- [Spring Batch API — SkipPolicy](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/step/skip/SkipPolicy.html): chính sách tùy biến quyết định skip.
- [Spring Batch API — SkipListener](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/SkipListener.html): callback khi skip ở read/process/write.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning và remote processing.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint/restart và ý nghĩa của `StepExecution`.

> **Ghi nhớ:** `skipLimit` là **ngưỡng chấp nhận lỗi có chọn lọc trong một `StepExecution`**. Nó cộng các skip của read/process/write, **không** tính filter hay retry thành công. Khi scale qua nhiều partition hoặc nhiều lần restart, cần thêm **giới hạn nghiệp vụ toàn job, quarantine, đối soát, idempotency và ranh giới publish**; tuyệt đối không dùng skip rộng để che lỗi hệ thống.
