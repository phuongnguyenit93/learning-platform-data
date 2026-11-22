# Không biến skip thành mất dữ liệu im lặng trong Spring Batch

Một job Spring Batch có thể kết thúc với trạng thái `COMPLETED`, nhưng dữ liệu được xuất ra lại **thiếu hàng trăm hoặc hàng nghìn bản ghi**. Nguyên nhân đôi khi không phải một lỗi nghiêm trọng: step đã được cấu hình `faultTolerant().skip(...)` và bỏ qua những item không thể xử lý. Nếu không có báo cáo reject, đối soát đầu vào–đầu ra và cơ chế chặn publish, người dùng downstream chỉ nhìn thấy tập dữ liệu thiếu mà không biết đã có bản ghi bị loại.

Trong **Spring Batch Core Processing → Data quality**, bài học này giải thích cách sử dụng skip như một cơ chế chịu lỗi **có chủ đích, có giới hạn và có thể kiểm toán**, thay vì một cách che giấu dữ liệu lỗi. Nội dung đi từ mô hình `skip`/`filter`/`retry`, các bộ đếm trong `StepExecution`, ghi nhận reject an toàn, kiểm tra tỷ lệ và tính đầy đủ, đến thiết kế **quality gate** trước khi xuất bản dữ liệu. Ví dụ sử dụng **Java 17, Spring Boot 3.x, Spring Batch 5.x, JUnit 5 và JDBC**.

## 1. Vấn đề: `COMPLETED` không luôn đồng nghĩa “không mất dữ liệu”

Giả sử một job nhập 100.000 đơn hàng mỗi đêm, yêu cầu kết quả có thể được hệ thống báo cáo sử dụng vào sáng hôm sau:

```text
Input: 100.000 đơn hàng
       |
       v
FlatFileItemReader
       |
       v
ItemProcessor
       |-- 450 item invalid --> SKIP
       |-- 100 item cancelled -> FILTER (trả null)
       v
ItemWriter
       |
       v
Output: 99.450 đơn hàng

Step status: COMPLETED
```

Nếu chính sách cho phép skip 500 item, step trên có thể `COMPLETED`: Spring Batch đã làm đúng cấu hình **kỹ thuật**. Nhưng nếu nghiệp vụ chỉ cho phép tối đa 50 item lỗi thì **kết quả này không được phép publish**. Nếu 100 đơn hàng bị filter mà không có quy tắc nghiệp vụ được phê duyệt, đó cũng có thể là mất dữ liệu.

Vì vậy cần phân biệt:

- **Technical success:** job/step đã thực hiện xong theo flow và fault-tolerance policy của framework.
- **Data quality success:** kết quả đáp ứng ngưỡng lỗi, quy tắc đầy đủ, đối soát, uniqueness, giá trị tổng và điều kiện nghiệp vụ.
- **Publication success:** chỉ một kết quả đã được xác nhận mới được công bố để downstream sử dụng.

Ba điều kiện này không thay thế cho nhau. Một batch “chạy hết” không có nghĩa dữ liệu “đủ và đúng”.

## 2. Skip, filter, retry và rollback khác nhau như thế nào?

### 2.1. `skip`: bỏ qua một item lỗi

Trong chunk-oriented step có `.faultTolerant()`, Spring Batch có thể bỏ qua item khi exception thuộc nhóm được cấu hình skip và số lượng skip chưa vượt ngưỡng.

Ví dụ:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
```

Với chính sách này, step có thể tiếp tục xử lý sau tối đa 20 item bị skip theo quy tắc hiện hành. Nếu item thứ 21 cần skip, step thường thất bại do vượt giới hạn. **`skipLimit` là giới hạn tổng skip ở các pha read/process/write**, không phải 20 cho từng pha.

**Hệ quả:** item bị skip không xuất hiện trong output thông thường của writer. Nếu output có yêu cầu đầy đủ, việc bỏ qua phải được chấp thuận và có dấu vết để sửa hoặc phát hành bù.

### 2.2. `filter`: processor chủ động không chuyển item xuống writer

Một `ItemProcessor` có thể trả `null`:

```java
@Override
public Order process(RawOrder item) {
    if ("CANCELLED".equals(item.status())) {
        return null; // Filter có chủ đích.
    }
    return map(item);
}
```

Đây là **filter**, không phải skip. Nó tăng `filterCount` chứ không tăng `skipCount`. Nếu code vô tình `return null` khi gặp lỗi mapping, dữ liệu có thể biến mất mà không chạm `skipLimit`.

Vì vậy phải đặt câu hỏi: **loại bản ghi nào được filter, vì sao và có cần đối soát số lượng filter không?** Không dùng `return null` như giải pháp mặc định cho exception.

### 2.3. `retry`: thử lại trước khi quyết định kết quả

Một API có thể timeout lần đầu rồi thành công ở lần kế tiếp. Nếu exception được retry, lỗi ban đầu **không đồng nghĩa item bị skip**:

```text
order-010:
    attempt 1 -> TemporaryServiceException
    attempt 2 -> TemporaryServiceException
    attempt 3 -> SUCCESS -> writer

Kết quả: 1 item được ghi, 0 item bị skip.
```

Ngược lại, một ngày sai định dạng thường không tự đúng lên nhờ retry. Cần phân biệt **lỗi tạm thời** với **lỗi dữ liệu vĩnh viễn** để không retry/skip tùy tiện.

### 2.4. `rollback` và `restart` không hoàn tác mọi dữ liệu đã ghi

Khi một chunk thất bại, transaction của chunk có thể rollback. Nhưng các **chunk trước đã commit** không tự bị rollback chỉ vì job sau đó `FAILED`. Khi restart, Spring Batch sử dụng `JobRepository` và checkpoint để quyết định phần việc cần tiếp tục; writer phải được thiết kế idempotent.

```text
Chunk 1 -> COMMITTED (100 rows)
Chunk 2 -> COMMITTED (100 rows)
Chunk 3 -> FAILED

JobExecution -> FAILED
Nhưng 200 rows của chunk 1 và 2 có thể vẫn nằm trong database.
```

Điều này đặc biệt quan trọng khi kết quả được ghi thẳng vào bảng production: người đọc có thể nhìn thấy dữ liệu dở dang. **Staging + quality gate + publish có điều kiện** giúp ngăn nguy cơ đó.

## 3. Định nghĩa “mất dữ liệu im lặng” thành những tình huống cụ thể

Không phải mọi record không tới writer đều là lỗi. Nhưng **mỗi đường đi của record** phải có lý do và số lượng có thể đối soát.

| Đường đi của item | Ví dụ | Cách nhận diện | Điều phải kiểm soát |
| --- | --- | --- | --- |
| Accepted | Đơn hàng hợp lệ | `writeCount`, output count | Đã ghi đúng một lần, giá trị đúng |
| Skipped in read | Dòng CSV sai cấu trúc | `readSkipCount` | Có định danh nguồn để sửa, không che schema lỗi |
| Skipped in process | Dữ liệu sai nghiệp vụ | `processSkipCount` | Có reason code và reject record |
| Skipped in write | DB từ chối item được phép bỏ qua | `writeSkipCount` | Không biến lỗi DB hệ thống thành dữ liệu mất |
| Filtered | Giao dịch đã hủy theo quy tắc | `filterCount` | Tiêu chí filter được duyệt, thống kê rõ |
| Retried then succeeded | API timeout rồi phục hồi | Retry metric riêng | Không đếm như reject cuối |
| Read failed fatally | File/header sai toàn nguồn | Job/step `FAILED` | Không publish kết quả thiếu |
| Lost before reader | File bị cắt, thiếu partition | Preflight/manifest | `skipCount` có thể bằng 0 mà vẫn thiếu dữ liệu |
| Duplicated on restart | Chunk đã ghi bị phát lại | Business key/reconciliation | Không chỉ đếm dòng, phải kiểm tra unique |

**Kết luận quan trọng:** `skipCount=0` không chứng minh dữ liệu đầy đủ. Source có thể thiếu record, reader có thể dừng sớm hoặc processor có thể filter item. Ngược lại, `skipCount>0` cũng không tự động có nghĩa kết quả phải bị loại: quyết định là do **data-quality contract** của từng batch.

## 4. Xây dựng hợp đồng chất lượng dữ liệu trước khi cấu hình skip

Một hợp đồng đầu vào nên mô tả rõ những nội dung sau:

1. **Nguồn và phiên bản:** `sourceBatchId`, `businessDate`, file version/snapshot ID và schema version.
2. **Completeness:** số bản ghi dự kiến, danh sách partition hoặc file cần có, manifest và checksum.
3. **Validation:** field bắt buộc, kiểu dữ liệu, khoảng giá trị, tham chiếu và uniqueness.
4. **Allowed rejects:** loại lỗi được skip, số lượng tối đa, tỷ lệ tối đa, quy tắc critical.
5. **Allowed filters:** item nào được loại theo chủ đích, số lượng/tỷ lệ có giới hạn không.
6. **Reconciliation:** số record, tổng số tiền, số khóa duy nhất hoặc checksum được so sánh thế nào.
7. **Publication:** điều kiện để đánh dấu batch `PUBLISHED` và cho downstream đọc.
8. **Recovery:** cách sửa item, replay reject, thay phiên bản nguồn, restart và audit.

Ví dụ quy tắc cho một lô 20.000 đơn:

```yaml
sourceBatchId: orders-20261116-v1
schemaVersion: 2
expectedRecords: 20000
quality:
  rejectAbsoluteMax: 25
  rejectRatioMax: 0.001
  criticalErrorCodes:
    - MISSING_ORDER_ID
    - DUPLICATE_BUSINESS_KEY
  allowedFilters:
    - CANCELLED_BY_SOURCE
  publishRequires:
    - manifestValid
    - sourceToOutputReconciled
    - quarantineDurable
    - totalsMatched
```

Đây là **mẫu hợp đồng nghiệp vụ**, không phải cấu hình YAML được Spring Batch tự hiểu. `rejectRatioMax: 0.001` là 0,1%; trong 20.000 record tương đương tối đa 20 reject. Khi vừa có ngưỡng tuyệt đối 25 vừa có tỷ lệ 0,1%, **cả hai phải đúng** nên giới hạn hiệu lực ở quy mô này là 20.

Nếu `MISSING_ORDER_ID` được coi là lỗi critical, chỉ **một** item có mã lỗi này cũng có thể làm batch không được publish, dù tổng reject vẫn dưới ngưỡng 20.

### 4.1. Phân loại lỗi theo mức cho phép

| Nhóm lỗi | Ví dụ | Chính sách |
| --- | --- | --- |
| Row-level recoverable data issue | Trường không bắt buộc có định dạng sai nhưng được phép sửa sau | Skip/quarantine trong ngân sách |
| Business-critical invalidity | Thiếu khóa định danh, tổng tiền âm trong đối soát tài chính | Fail hoặc chặn publish |
| Source-wide error | Header sai, schema version không hỗ trợ, checksum sai | Fail ở preflight trước khi ghi |
| Infrastructure transient | Database deadlock, API 503 | Retry có giới hạn, không coi item là invalid |
| Programmer/configuration error | Null pointer không dự kiến, thiếu bảng, sai mapping | Fail; không `.skip(Exception.class)` |

Không cấu hình skip chỉ để tăng tỷ lệ job `COMPLETED`. Một lô có 90% item bị bỏ qua mà vẫn đạt `COMPLETED` thường là vấn đề **quality policy**, không phải thành công về dữ liệu.

## 5. Cấu hình skip có giới hạn trong Spring Batch 5

Giả sử job nhập CSV đơn hàng, reader đọc các trường dưới dạng chuỗi, processor validate và writer ghi vào **bảng staging**. Khi có record sai số tiền, processor ném exception nghiệp vụ đã phân loại.

### 5.1. Model dữ liệu và exception

```java
package com.example.batch;

import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String status,
        String amountText) {}

public record AcceptedOrder(
        String orderId,
        BigDecimal amount) {}

public class InvalidOrderException extends RuntimeException {
    private final String reasonCode;

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
```

Trong Java thật, mỗi `public` top-level type được đặt vào một file riêng tương ứng (`RawOrder.java`, `AcceptedOrder.java`, `InvalidOrderException.java`). Chúng được gom trong một đoạn code ở đây để thấy đầy đủ dữ liệu liên quan. `reasonCode` phải thuộc tập mã an toàn đã phê duyệt, không chứa nguyên nội dung dòng CSV hoặc giá trị thông tin cá nhân.

### 5.2. Processor: filter có chủ đích, lỗi phải ném exception

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderValidationProcessor
        implements ItemProcessor<RawOrder, AcceptedOrder> {

    @Override
    public AcceptedOrder process(RawOrder row) {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("MISSING_ORDER_ID");
        }

        // Quy tắc filter được phê duyệt và phải được đối soát.
        if ("CANCELLED".equals(row.status())) {
            return null;
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(row.amountText());
        } catch (NumberFormatException | NullPointerException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT");
        }

        if (amount.signum() <= 0) {
            throw new InvalidOrderException("NON_POSITIVE_AMOUNT");
        }

        return new AcceptedOrder(row.orderId(), amount);
    }
}
```

Processor trên không “nuốt exception” rồi trả `null` cho mọi item lỗi. Nó chỉ filter khi `status=CANCELLED`, theo một quy tắc nghiệp vụ rõ ràng. Những bản ghi sai amount phát sinh `InvalidOrderException` để framework thống kê skip và cơ chế reject biết lý do.

Một quyết định nghiệp vụ khác có thể là **không được filter đơn hàng hủy** mà phải ghi chúng với trạng thái hủy. Khi đó cần thay processor và quality contract, không tùy tiện sao chép quy tắc filter của ví dụ.

### 5.3. Reader CSV và preflight riêng

Giả sử file có header:

```csv
order_id,status,amount
o-001,ACTIVE,150.00
o-002,ACTIVE,BAD
o-003,CANCELLED,200.00
o-004,ACTIVE,50.00
```

Reader dùng `@StepScope` để lấy đường dẫn đã được validate từ `JobParameters`:

```java
@Bean
@StepScope
FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("order_id", "status", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("order_id"),
                    fields.readString("status"),
                    fields.readString("amount")))
            .build();
}
```

Đoạn bean cần import các class từ `org.springframework.batch.item.file.*`, `org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder`, `org.springframework.batch.core.configuration.annotation.StepScope`, Spring `@Bean`, `@Value` và `FileSystemResource`.

**Điểm quan trọng:** `.linesToSkip(1)` chỉ bỏ qua header, **không chứng minh header đúng**. Trong job thật, nên có `validateSourceStep` kiểm tra manifest, schema version, danh sách cột, checksum, số file/partition và tính bất biến của nguồn. Lỗi toàn file phải fail trước khi xử lý hoặc publish; không biến 20.000 lỗi parse thành 20.000 record được skip.

`inputFile` từ tham số cũng phải nằm trong thư mục/nguồn được phép, không sử dụng đường dẫn do người dùng không tin cậy tùy ý cung cấp.

### 5.4. Step chỉ cho skip exception đã biết

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> reader,
        OrderValidationProcessor processor,
        ItemWriter<AcceptedOrder> stagingWriter,
        SkipListener<RawOrder, AcceptedOrder> rejectListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, AcceptedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(stagingWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(25)
            .listener(rejectListener)
            .build();
}
```

Các bean reader, processor, writer và reject listener là thành phần được cấu hình bởi dự án. Với Spring Batch 5, `StepBuilder` dùng `JobRepository` và transaction manager được truyền vào bước chunk. Writer ở đây **phải ghi staging**, không đưa ngay dữ liệu được skip một phần cho downstream.

Cấu hình trên:

- Cho phép skip tối đa **25 item** khi `InvalidOrderException` xuất hiện trong phạm vi policy.
- Không tự skip `SQLException`, lỗi kết nối, `NullPointerException` bất ngờ hay mọi exception nói chung.
- Không tự biết ngưỡng **tỷ lệ** 0,1% hoặc mã lỗi critical: cần quality gate ở các phần tiếp theo.
- Không tự bảo đảm ghi reject bền vững: listener phải được kết hợp với kho quarantine/audit phù hợp.

Ví dụ được viết cho kịch bản lỗi validation tại processor. Nếu cần cho phép một số `FlatFileParseException` tại reader, phải bổ sung **có chủ đích**, sau khi định nghĩa cách ghi nhận và xác định nguồn lỗi. Không bao giờ mặc định cho skip tất cả lỗi read.

## 6. Đọc đúng các counter của `StepExecution`

Spring Batch có nhiều counter; mỗi counter có ý nghĩa riêng:

| Counter | Ý nghĩa cơ bản | Không nên suy diễn thành |
| --- | --- | --- |
| `getReadCount()` | Số item reader đọc thành công theo step | Tổng dòng vật lý của file trong mọi trường hợp |
| `getReadSkipCount()` | Số skip khi đọc | Số file đầu vào bị lỗi |
| `getProcessSkipCount()` | Số skip khi process | Mọi lần processor ném exception |
| `getWriteSkipCount()` | Số skip khi write | Mọi lỗi ghi hoặc rollback |
| `getSkipCount()` | Tổng số skip | Số lần retry |
| `getFilterCount()` | Item bị processor filter (`null`) | Số item invalid được skip |
| `getWriteCount()` | Số item được writer ghi theo step | Số hàng DB thực sự tồn tại hoặc đã publish trong mọi thiết kế |
| `getRollbackCount()` | Số lần rollback ghi nhận | Số item lỗi |
| `getCommitCount()` | Số lần commit ghi nhận | Số chunk logic nguồn |

Với ví dụ CSV bốn record ở phần 5, nếu step được cấu hình cho phép skip:

```text
Input records: 4
readCount: 4
processSkipCount: 1   (o-002 INVALID_AMOUNT)
filterCount: 1        (o-003 CANCELLED)
writeCount: 2         (o-001 và o-004)
skipCount: 1
```

Trong tình huống **một input tạo tối đa một output**, không có duplicate, không có output ghi ra bên ngoài transaction và reader/processor/writer hoạt động theo giả định chuẩn, có thể đối chiếu:

```text
input_count = accepted_count + rejected_count + filtered_count
4 = 2 + 1 + 1
```

Đừng áp dụng phép cộng đó mù quáng nếu processor sinh nhiều output, reader xử lý multi-line record, writer ghi nhiều bảng, job dùng upsert, dữ liệu bị loại trước reader hoặc `JobExecution` bị restart qua nhiều lần. **Báo cáo quality phải định nghĩa đơn vị đo một cách tường minh**.

### 6.1. Ghi summary sau step

Có thể dùng `StepExecutionListener` để log tổng hợp:

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class QualitySummaryListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(QualitySummaryListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "event=batch_step_quality step={} execution_id={} "
                + "status={} read={} write={} filter={} skip={} "
                + "read_skip={} process_skip={} write_skip={}",
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount());

        return null; // Giữ ExitStatus của step nếu không muốn đổi.
    }
}
```

Listener này giúp **nhìn thấy** sự khác biệt giữa `COMPLETED` và “không có reject”. Tuy vậy, log summary không phải source of truth cho việc publish. Quyết định publish phải dựa trên các số liệu và bằng chứng bền vững đã được xác nhận, thay vì parse một dòng log.

## 7. Ghi nhận từng item bị skip mà không lộ dữ liệu

Một item bị skip phải có **lý do, nguồn gốc và đường quay lại để sửa**. Nhưng logging nguyên object để dễ tìm là rủi ro:

```java
log.warn("Skipped item={} cause={}", item, error);
```

`item.toString()` hoặc exception message có thể chứa email, số tài khoản, nội dung CSV, câu SQL và các field nhạy cảm. Thay vào đó, nên dùng một mã tham chiếu an toàn cùng reason code được kiểm duyệt:

```text
event=batch_item_skipped
job=importOrdersJob
step=importOrdersStep
source_batch_ref=orders-20261116-v1
stage=process
item_ref=7e12d3cf18c51a9b
reason_code=INVALID_AMOUNT
```

`item_ref` có thể được tạo từ business ID ổn định bằng **HMAC-SHA-256 với khóa bí mật**, hoặc dùng một token ngẫu nhiên có mapping được bảo vệ. Không nên dùng `hashCode()`, MD5 hoặc SHA-256 không khóa trên email/order ID dễ đoán rồi nghĩ rằng đã ẩn danh. Nếu chính sách không cho phép log item-level reference, log cấp step với counter và đưa chi tiết vào quarantine có phân quyền.

### 7.1. `SkipListener` để ghi nhận skip cuối, không phải mọi retry

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SafeRejectListener
        implements SkipListener<RawOrder, AcceptedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeRejectListener.class);

    private final SafeReferenceFactory references;

    public SafeRejectListener(SafeReferenceFactory references) {
        this.references = references;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        // Không có RawOrder đáng tin cậy ở pha read.
        log.warn("event=batch_item_skipped stage=read "
                + "item_ref=unavailable reason_code=READ_REJECTED");
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        log.warn(
                "event=batch_item_skipped stage=process "
                + "item_ref={} reason_code={}",
                references.forOrder(item.orderId()),
                safeReason(error));
    }

    @Override
    public void onSkipInWrite(AcceptedOrder item, Throwable error) {
        log.warn(
                "event=batch_item_skipped stage=write "
                + "item_ref={} reason_code=WRITE_REJECTED",
                references.forOrder(item.orderId()));
    }

    private String safeReason(Throwable error) {
        if (error instanceof InvalidOrderException e) {
            return switch (e.reasonCode()) {
                case "INVALID_AMOUNT" -> "INVALID_AMOUNT";
                case "NON_POSITIVE_AMOUNT" -> "NON_POSITIVE_AMOUNT";
                case "MISSING_ORDER_ID" -> "MISSING_ORDER_ID";
                default -> "INVALID_ORDER";
            };
        }
        return "UNCLASSIFIED_FAILURE";
    }
}
```

Trong ví dụ, `SafeReferenceFactory` là một **dịch vụ được dự án triển khai riêng**, có phương thức `forOrder(String)` trả token đã được bảo vệ. Đây là hợp đồng placeholder, **không phải class có sẵn của Spring Batch**. Với `orderId` rỗng hoặc `null`, dịch vụ nên trả `"unavailable"` thay vì in ID gốc hay ném lỗi khiến listener gây thêm exception ngoài ý muốn.

Các mã `READ_REJECTED`, `WRITE_REJECTED` chỉ là ví dụ mức tổng quát; trong ứng dụng cần phân loại cụ thể theo exception đã duyệt mà không log `getMessage()` nguyên văn.

Spring Batch gọi `SkipListener` khi một item **thực sự bị skip** theo fault-tolerant step. Trong khi đó, `ItemProcessListener.onProcessError()` có thể được gọi ở một lần thử lỗi sau đó retry thành công. **Không dựa vào số event `onProcessError` để tính số reject cuối cùng.**

### 7.2. Quarantine khác log

Để đội dữ liệu sửa được item, cần có **kho reject/quarantine bền vững**, với các thuộc tính:

| Trường | Công dụng |
| --- | --- |
| `source_batch_id` | Lô nguồn đã gửi record |
| `source_version` | Phiên bản file/snapshot bất biến |
| `record_locator` | Khóa nguồn hoặc vị trí record theo phiên bản |
| `stage` | Read/process/write |
| `reason_code` | Mã lỗi cố định để phân nhóm |
| `rejected_at` | Thời điểm ghi nhận |
| `job_execution_id` | Truy vết lần chạy |
| `payload_pointer` | Vị trí payload gốc đã mã hóa/phân quyền |
| `review_status` | NEW, CORRECTED, REPLAYED, DISMISSED ... |

Không nhất thiết phải lưu payload nhạy cảm ở cùng bảng log/audit: có thể lưu **pointer** tới file gốc bất biến hoặc object storage được bảo vệ và chỉ cho phép công cụ nghiệp vụ có quyền truy cập.

`SkipListener` có thể ghi nhận thông tin reject, nhưng cần chú ý **transaction boundary**. Log gửi sang hệ thống logging không rollback theo chunk. Ghi vào một datasource khác cũng không tự tham gia transaction của writer. Nếu yêu cầu kiểm toán chính xác, cần thiết kế reject store/outbox có idempotency key và giao dịch phù hợp, đồng thời kiểm tra lỗi ghi quarantine. Đừng để quarantine thất bại nhưng batch vẫn báo xuất bản thành công.

### 7.3. Không làm mất khả năng truy vết khi parse lỗi

`onSkipInRead(Throwable)` không nhận item, vì reader có thể chưa tạo được object. Với file CSV, có thể lưu `source_file_version` và `line_number` **nếu reader hỗ trợ xác định an toàn**. Tuy nhiên exception parse có thể chứa nguyên dòng đầu vào; không nên in toàn bộ exception hoặc gọi `FlatFileParseException.getInput()` trong log phổ thông.

Nếu file có thể thay đổi khi restart, một số dòng không đủ xác định record. Hãy dùng phiên bản file/checksum và vị trí kỹ thuật, hoặc một ID record có trong nguồn được bảo vệ.

## 8. Quality gate: kiểm tra trước khi publish

`skipLimit(25)` chỉ bảo vệ chống vượt **25 item skip trong một StepExecution**; nó không tự kiểm tra tỷ lệ reject, mã lỗi critical, độ đầy đủ từ manifest hay data freshness. Vì thế nên có bước **quality gate tách biệt** giữa import và publish:

```text
Validate source / manifest
        |
        v
Import to staging
        |        \
        |         \--> Rejected items --> Quarantine
        v
Reconcile + Quality gate
        |
        +-- reject > allowed ----------> FAILED / NOT_PUBLISHED
        +-- critical reject -----------> FAILED / NOT_PUBLISHED
        +-- manifest mismatch ---------> FAILED / NOT_PUBLISHED
        +-- output totals mismatch ----> FAILED / NOT_PUBLISHED
        |
        v
Publish approved snapshot
        |
        v
Downstream readers
```

Ở đây bảng staging mang `source_batch_id` hoặc version để downstream **không đọc nhầm dữ liệu đang xử lý**. Chỉ khi pass gate, job mới xuất bản một snapshot hoặc cập nhật `published_version` có tính nguyên tử theo thiết kế. Một job `FAILED` ở bước gate không tự rollback các chunk đã commit trước đó; chúng vẫn nằm trong staging để điều tra hoặc làm sạch theo chính sách.

### 8.1. Mô hình kết quả quality độc lập với batch status

```java
package com.example.batch.quality;

public record QualitySnapshot(
        long sourceExpected,
        long accepted,
        long rejected,
        long filtered,
        long criticalRejected,
        boolean sourceVerified,
        boolean quarantineVerified,
        boolean businessTotalsMatched) {}

public record QualityDecision(
        boolean publishAllowed,
        String reasonCode) {}
```

Ở đây `accepted`, `rejected`, `filtered` là **số liệu đã được đối soát theo hợp đồng**, không nhất thiết lấy nguyên từ một `StepExecution` duy nhất. Điều này quan trọng khi job đã restart qua nhiều executions, có nhiều step/partition hoặc writer dùng upsert.

### 8.2. Policy thuần Java dễ kiểm thử

Ví dụ policy cho phép tối đa 25 reject và tỷ lệ không quá 0,1%, đồng thời không chấp nhận lỗi critical:

```java
package com.example.batch.quality;

public final class QualityPolicy {

    private static final long ABSOLUTE_MAX_REJECTED = 25;
    private static final long MAX_REJECT_PER_MILLION = 1_000;
    // 1.000 / 1.000.000 = 0,001 = 0,1%.

    public QualityDecision evaluate(QualitySnapshot s) {
        if (!s.sourceVerified()) {
            return new QualityDecision(false, "SOURCE_NOT_VERIFIED");
        }
        if (!s.quarantineVerified()) {
            return new QualityDecision(false, "REJECT_AUDIT_INCOMPLETE");
        }
        if (!s.businessTotalsMatched()) {
            return new QualityDecision(false, "BUSINESS_TOTAL_MISMATCH");
        }
        if (s.sourceExpected() <= 0) {
            return new QualityDecision(false, "INVALID_EXPECTED_COUNT");
        }
        if (s.accepted() < 0 || s.rejected() < 0
                || s.filtered() < 0 || s.criticalRejected() < 0) {
            return new QualityDecision(false, "INVALID_COUNTS");
        }
        if (s.criticalRejected() > 0) {
            return new QualityDecision(false, "CRITICAL_REJECT");
        }
        if (s.rejected() > ABSOLUTE_MAX_REJECTED) {
            return new QualityDecision(false, "REJECT_COUNT_EXCEEDED");
        }

        // Tránh số thực khi so ngưỡng tỷ lệ.
        // BigInteger tránh overflow khi nhân các long rất lớn.
        var rejectsScaled = java.math.BigInteger
                .valueOf(s.rejected())
                .multiply(java.math.BigInteger.valueOf(1_000_000L));
        var allowedScaled = java.math.BigInteger
                .valueOf(s.sourceExpected())
                .multiply(java.math.BigInteger.valueOf(
                        MAX_REJECT_PER_MILLION));

        if (rejectsScaled.compareTo(allowedScaled) > 0) {
            return new QualityDecision(false, "REJECT_RATIO_EXCEEDED");
        }

        var accounted = java.math.BigInteger.valueOf(s.accepted())
                .add(java.math.BigInteger.valueOf(s.rejected()))
                .add(java.math.BigInteger.valueOf(s.filtered()));

        if (!accounted.equals(
                java.math.BigInteger.valueOf(s.sourceExpected()))) {
            return new QualityDecision(false, "COUNT_MISMATCH");
        }

        return new QualityDecision(true, "QUALITY_APPROVED");
    }
}
```

Tất cả các `record` và class ở ví dụ được đặt trong file tương ứng, cùng package `com.example.batch.quality`. `QualityPolicy` là code nghiệp vụ, không phải API có sẵn của Spring Batch.

Phép so sánh ratio dùng nhân số nguyên để tránh làm tròn sớm. Với `sourceExpected=20.000`, tỷ lệ 0,1% cho phép tối đa **20 reject**; `rejected=21` phải bị chặn dù chưa tới ngưỡng tuyệt đối 25.

**Điều kiện đếm:** `accepted + rejected + filtered == sourceExpected` phù hợp với trường hợp một record đầu vào được phân loại vào **đúng một** trong ba nhóm. Nếu job gom nhiều record thành một output, tách một record thành nhiều output, deduplicate hoặc dùng upsert, phải xây một phép đối soát tương đương khác dựa trên business keys và quy tắc chuyển đổi. Không sửa policy để “cho qua” mismatch mà chưa giải thích vì sao.

### 8.3. Đưa quality gate vào flow của job

Có thể thực hiện gate trong một tasklet sau bước import, rồi chỉ chạy publish nếu gate thành công:

```java
@Bean
Step qualityGateStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        QualityReportRepository reports,
        QualityPolicy policy) {

    return new StepBuilder("qualityGateStep", repository)
            .tasklet((contribution, chunkContext) -> {
                String sourceBatchId =
                        (String) chunkContext.getStepContext()
                                .getJobParameters()
                                .get("sourceBatchId");

                QualitySnapshot snapshot =
                        reports.loadFinalSnapshot(sourceBatchId);
                QualityDecision decision = policy.evaluate(snapshot);

                if (!decision.publishAllowed()) {
                    throw new IllegalStateException(
                            "QUALITY_GATE_FAILED:" + decision.reasonCode());
                }
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

`QualityReportRepository` trong đoạn này là **interface nghiệp vụ do dự án tự xây dựng**, có `loadFinalSnapshot(String)` trả số liệu bền vững đã đối soát từ manifest, staging, quarantine và các nguồn kiểm tra khác. Nó **không phải** một repository có sẵn trong Spring Batch; ví dụ tập trung vào điểm tích hợp gate.

Khi bước gate ném exception, step/job có thể `FAILED` và bước publish phía sau **không được chạy trong flow tuyến tính mặc định**. Cần tránh cấu hình transition kiểu “bất kể FAILED vẫn chạy publish”. Tên mã lý do trong exception đã được kiểm duyệt để không lộ dữ liệu nhạy cảm.

Với cấu hình đã có các bean `validateSourceStep`, `importOrdersStep`, `qualityGateStep`, `publishStep`, flow tổng quát:

```java
@Bean
Job importOrdersJob(
        JobRepository repository,
        Step validateSourceStep,
        Step importOrdersStep,
        Step qualityGateStep,
        Step publishStep) {

    return new JobBuilder("importOrdersJob", repository)
            .start(validateSourceStep)
            .next(importOrdersStep)
            .next(qualityGateStep)
            .next(publishStep)
            .build();
}
```

Trong code thật cần import `org.springframework.batch.core.Job`, `org.springframework.batch.core.Step`, `JobBuilder`, `StepBuilder`, `JobRepository`, `RepeatStatus`, `PlatformTransactionManager`, `@Bean`, và các class quality của dự án. Job flow được viết dạng mẫu; reader, writer, preflight và publish step phải được triển khai thêm.

## 9. Dữ liệu nguồn, staging và quarantine phải đối soát được

### 9.1. Ví dụ bảng kết quả theo batch

Một hệ thống có thể lưu các bảng nghiệp vụ:

```sql
CREATE TABLE import_batch (
    source_batch_id VARCHAR(100) PRIMARY KEY,
    business_date DATE NOT NULL,
    expected_count BIGINT NOT NULL,
    source_verified BOOLEAN NOT NULL,
    quality_status VARCHAR(30) NOT NULL,
    publish_status VARCHAR(30) NOT NULL
);

CREATE TABLE staging_order (
    source_batch_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (source_batch_id, order_id)
);

CREATE TABLE rejected_record (
    source_batch_id VARCHAR(100) NOT NULL,
    record_locator VARCHAR(200) NOT NULL,
    reason_code VARCHAR(60) NOT NULL,
    payload_pointer VARCHAR(500),
    review_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (source_batch_id, record_locator)
);
```

DDL trên là ví dụ đơn giản, không bao gồm mọi index, audit timestamp, khóa ngoại, partitioning hoặc encryption. Nếu một record có thể bị reject nhiều lần vì nhiều lý do, khóa của `rejected_record` cần được mở rộng hoặc có bảng lịch sử riêng. Nên dùng `source_batch_id` gắn với **phiên bản nguồn bất biến** thay vì chỉ đường dẫn file.

### 9.2. Reconciliation không chỉ là count

Ví dụ cùng có 99.990 record đầu ra nhưng hai tình huống khác nhau:

```text
Case A: thiếu 10 record, không có duplicate.
Case B: thiếu 20 record, lặp 10 record.

Output count đều có thể là 99.990.
```

Vì vậy cần kiểm tra nhiều chiều:

| Phép đối soát | Phát hiện |
| --- | --- |
| Tổng record nguồn và tổng accepted/rejected/filtered | Record chưa có trạng thái rõ ràng |
| Unique business key count | Ghi trùng hoặc duplicate |
| Tổng tiền/tổng theo nhóm | Bản ghi hoặc giá trị bị thiếu/sai |
| Checksum/manifest | Nguồn không đủ hoặc bị thay đổi |
| Tập source key trừ accepted/rejected/filtered | Record thất lạc chưa phân loại |
| Trạng thái publish theo `source_batch_id` | Downstream đọc nhầm dữ liệu chưa duyệt |

Khi source là event stream không có “số dòng dự kiến” từ manifest, có thể dùng **offset range, watermark, snapshot token hoặc input partition contract** làm cơ sở đối soát. “Reader trả về hết dữ liệu hiện có” không chứng minh upstream đã phát đủ sự kiện.

### 9.3. Publish có tính nguyên tử

Sau quality gate, một cách an toàn là cập nhật **con trỏ tới version đã được duyệt** trong transaction:

```text
staging snapshot v1  --> QUALITY_FAILED, không publish
staging snapshot v2  --> QUALITY_APPROVED
                             |
                             v
                   published_version = v2
                             |
                             v
                    downstream đọc v2
```

Nếu publish file, có thể tạo file hoàn chỉnh trong vùng tạm rồi **đổi tên/đánh dấu ready theo cơ chế atomic phù hợp** với filesystem/object store. Nếu publish database, dùng transaction và khóa duy nhất để không công bố snapshot chưa đầy đủ. Quy tắc chính xác phụ thuộc loại storage.

Không nên để downstream `SELECT * FROM staging_order` mà không lọc `publish_status`; khi job `FAILED`, các chunk staging đã commit vẫn tồn tại nhưng chưa được chấp nhận.

## 10. Restart và replay: skip phải có đường phục hồi

Giả sử lô `orders-20261116-v1` có 12 reject; hệ thống cho phép tạm thời publish nếu 12 reject nằm trong ngưỡng, đồng thời cần sửa chúng:

1. Lưu rejected record trong quarantine với `sourceBatchId` và `recordLocator`.
2. Giao danh sách reason code cho bộ phận sở hữu nguồn qua kênh có phân quyền.
3. Tạo phiên bản dữ liệu sửa hoặc gói replay của những record bị reject.
4. Thực hiện replay với khóa business ổn định; writer dùng unique constraint/upsert/idempotency tương ứng.
5. Đối soát tổng sau replay và cập nhật trạng thái quarantine `REPLAYED`.
6. Nếu report trước đó đã phát hành, xác định có cần phát hành một **phiên bản kết quả mới** và thông báo downstream hay không.

Không mặc định “skip rồi quên”. Nếu nghiệp vụ cho phép mất tối đa một tỷ lệ nhỏ tạm thời, phải có **SLA sửa reject** hoặc chính sách ghi nhận kết quả cuối cùng được chấp nhận.

### 10.1. Restart cùng instance khác với replay lô mới

- **Restart:** job `FAILED` hoặc `STOPPED` và có thể chạy lại với **cùng identifying `JobParameters`** cùng metadata/checkpoint; Spring Batch tạo một `JobExecution` mới của cùng `JobInstance` khi được phép.
- **Replay/version mới:** nguồn đã được sửa hoặc thay bằng `sourceBatchId=v2`; thường tạo `JobInstance` mới để xử lý nguồn bất biến mới với rules chống duplicate.

**Không thay file nguồn dưới cùng đường dẫn/checkpoint rồi mong restart luôn đúng.** Vị trí đã lưu của reader có thể không còn trỏ tới cùng record khi file bị sửa. Giữ nguồn bất biến hoặc dùng versioning, rồi chọn restart/replay có chủ đích.

### 10.2. Quan sát số liệu khi restart

Counter trong `StepExecution` thường thuộc **một lần thực thi step**. Nếu restart bỏ qua step đã `COMPLETED` từ lần trước, không thể dựa vào `jobExecution.getStepExecutions()` của lần chạy mới để suy ra toàn bộ số record của lô. Một quality gate đáng tin cậy cần đọc số liệu bền vững theo `sourceBatchId` từ manifest, staging, quarantine và lịch sử execution thích hợp. Đây là lý do phần 8 dùng `QualityReportRepository` thay vì chỉ đọc `skipCount` của step gần nhất.

## 11. Khi dữ liệu lỗi hàng loạt, phải fail sớm

Một lỗi validation phân tán không giống hàng nghìn record cùng sai vì schema nguồn thay đổi:

```text
09:00: New source schema deployed
01:00: Nightly import starts
01:01: First 200 records cannot be parsed
01:02: Skip count keeps rising
```

Nếu job dùng `.skip(Exception.class).skipLimit(1000000)`, nó có thể tốn hàng giờ bỏ qua gần hết file. Một chiến lược tốt hơn:

- **Preflight** header, schema, file completeness và manifest.
- Dùng skip allowlist chỉ cho một số lỗi record được phép.
- Chặn ngay với các reason code nghiêm trọng (`MISSING_ORDER_ID`, incompatibility).
- Cấu hình `skipLimit` như **cầu chì kỹ thuật** để dừng khi lỗi vượt mức.
- Dùng **quality gate** kiểm tra thêm tỷ lệ reject và tính đầy đủ.
- Có alert khi tỷ lệ lỗi trong một cửa sổ tăng nhanh, không đợi job kết thúc.

Ngoài ra, lỗi hạ tầng như HTTP 503 hoặc database unavailable **không nên được biến thành dữ liệu invalid để skip hàng loạt**. Dùng retry có giới hạn, backoff, giới hạn concurrency và chiến lược stop/restart khi hệ thống phụ thuộc phục hồi.

## 12. Quan sát và cảnh báo để không mất dữ liệu im lặng

Các metric cấp lô nên được ghi nhận:

| Metric | Công dụng |
| --- | --- |
| `source.expected` | Số record/đơn vị nguồn dự kiến |
| `source.verified` | Trạng thái xác minh nguồn |
| `batch.accepted` | Số item được nghiệp vụ chấp nhận |
| `batch.rejected` | Số item bị loại có reject record |
| `batch.filtered` | Số item được filter có chủ đích |
| `batch.unaccounted` | Số item chưa có kết quả hoặc chưa đối soát |
| `batch.reject.ratio` | Tỷ lệ reject trên tổng nguồn |
| `batch.critical.rejected` | Số reject thuộc nhóm critical |
| `quarantine.pending` | Số item chưa được sửa/replay |
| `publish.approved` | Batch đã qua quality gate hay chưa |
| `publish.age` | Độ trễ của snapshot được publish mới nhất |

Log nên chứa `job_name`, `step_name`, `job_execution_id`, `source_batch_ref`, `reason_code` và trạng thái tổng hợp đã được phép. Tránh log toàn bộ `JobParameters`, payload, email hoặc stack trace có dữ liệu nguồn. ID của từng item/quarantine phù hợp làm trường tìm kiếm có kiểm soát trong log, **không phù hợp làm metric label** vì có cardinality rất cao.

Một chính sách alert mẫu:

```text
WARN:
  reject_ratio > 0.05% trong 5.000 record gần nhất

CRITICAL:
  reject_ratio > 0.1%
  OR critical_rejected > 0
  OR source_expected != accounted_records
  OR quality_gate = FAILED
  OR quarantine_write_failed
```

Các tỷ lệ trên là **ngưỡng minh họa**, cần được hiệu chỉnh theo dữ liệu nghiệp vụ. Với lô nhỏ, tỷ lệ tính trên vài record đầu dễ dao động; nếu muốn alert sớm, cần thiết kế min sample size và tránh nhầm một spike ngắn với lỗi hệ thống.

## 13. Kiểm thử skip và chất lượng dữ liệu với JUnit 5

Kiểm thử không nên chỉ assert job `COMPLETED` rồi dừng. Cần test rõ số item đi qua từng nhánh, ngưỡng lỗi và điều kiện được publish.

### 13.1. Bộ fixture

Tạo các file test:

```text
src/test/resources/orders/
  ├── all-valid.csv
  ├── one-rejected.csv
  ├── filter-and-reject.csv
  ├── reject-limit-exceeded.csv
  ├── invalid-header.csv
  └── truncated-source.csv
```

Ví dụ `filter-and-reject.csv`:

```csv
order_id,status,amount
o-001,ACTIVE,150.00
o-002,ACTIVE,BAD
o-003,CANCELLED,200.00
o-004,ACTIVE,50.00
```

Kết quả dự kiến theo processor ở phần 5: accepted 2, rejected 1, filtered 1. Tập dữ liệu thật của integration test phải có bảng staging, audit và `JobRepository` dành riêng cho test, tránh xóa dữ liệu của môi trường khác.

### 13.2. Test policy chất lượng độc lập

Vì `QualityPolicy` chỉ nhận một snapshot và trả decision, có thể test mà không khởi chạy toàn bộ Spring context:

```java
package com.example.batch.quality;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class QualityPolicyTest {

    private final QualityPolicy policy = new QualityPolicy();

    @Test
    void approvesReconciledSmallRejectCount() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_975, 20, 5, 0,
                true, true, true);

        QualityDecision result = policy.evaluate(snapshot);

        assertThat(result.publishAllowed()).isTrue();
        assertThat(result.reasonCode()).isEqualTo("QUALITY_APPROVED");
    }

    @Test
    void rejectsTooManyRelativeToSource() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_974, 21, 5, 0,
                true, true, true);

        QualityDecision result = policy.evaluate(snapshot);

        assertThat(result.publishAllowed()).isFalse();
        assertThat(result.reasonCode())
                .isEqualTo("REJECT_RATIO_EXCEEDED");
    }

    @Test
    void rejectsCriticalProblemEvenUnderLimit() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_994, 1, 5, 1,
                true, true, true);

        assertThat(policy.evaluate(snapshot).reasonCode())
                .isEqualTo("CRITICAL_REJECT");
    }

    @Test
    void rejectsMissingRecordsEvenWithZeroSkips() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_900, 0, 0, 0,
                true, true, true);

        assertThat(policy.evaluate(snapshot).reasonCode())
                .isEqualTo("COUNT_MISMATCH");
    }

    @Test
    void rejectsMissingQuarantineEvidence() {
        QualitySnapshot snapshot = new QualitySnapshot(
                20_000, 19_975, 20, 5, 0,
                true, false, true);

        assertThat(policy.evaluate(snapshot).reasonCode())
                .isEqualTo("REJECT_AUDIT_INCOMPLETE");
    }
}
```

Các test phân biệt: **đúng tỷ lệ**, **vượt tỷ lệ**, **critical error**, **record không có kết quả** và **thiếu bằng chứng quarantine**. Chúng không thay thế integration test của step, nhưng cho phép kiểm tra nhanh logic publish gate.

### 13.3. Tích hợp với `@SpringBatchTest`

Trong một dự án dùng Spring Boot và Gradle, có thể thêm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Một integration test điển hình cần:

1. Khởi chạy job bằng `JobLauncherTestUtils` với `sourceBatchId` và `inputFile` riêng.
2. Kiểm tra `StepExecution.getReadCount()`, `getFilterCount()`, `getProcessSkipCount()`, `getWriteCount()`.
3. Đọc bảng staging để xác nhận số record và giá trị nghiệp vụ thực tế.
4. Đọc quarantine để xác nhận mỗi reject được lưu bền vững với reason code và locator phù hợp.
5. Kiểm tra quality gate **không chạy publish** khi ratio/count/critical rule vi phạm.
6. Với dữ liệu hợp lệ trong ngưỡng, kiểm tra bản published version và checksum/tổng số liệu.
7. Chạy restart sau một lỗi có chủ đích bằng **cùng identifying parameters**; xác nhận không ghi trùng.

Ví dụ đoạn assertion sau khi một job test được khởi chạy (các bean và fixture được chuẩn bị theo ứng dụng):

```java
JobExecution execution =
        jobLauncherTestUtils.launchJob(testParameters);

StepExecution importStep = execution.getStepExecutions().stream()
        .filter(step -> "importOrdersStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

assertThat(importStep.getReadCount()).isEqualTo(4);
assertThat(importStep.getProcessSkipCount()).isEqualTo(1);
assertThat(importStep.getFilterCount()).isEqualTo(1);
assertThat(importStep.getWriteCount()).isEqualTo(2);
```

Đây là **đoạn assertion**, không phải một file test chạy độc lập; `jobLauncherTestUtils`, `testParameters`, `assertThat` và cấu hình job phải có trong test class. Với flow có quality gate và publish, kiểm tra thêm trạng thái kết quả, bảng dữ liệu và metadata publish. Một test restart cần tính đến step `COMPLETED` ở execution trước, thay vì giả định mọi step đều xuất hiện trong execution mới.

### 13.4. Ma trận test quan trọng

| Kịch bản | Kỳ vọng về skip/quality/publish |
| --- | --- |
| 100% item hợp lệ | Không skip, không filter ngoài policy; publish |
| 1 invalid item được phép | Skip được ghi nhận, quarantine bền vững; publish nếu qua gate |
| 1 item có `status=CANCELLED` | `filterCount` tăng; được tính riêng với skip |
| 21 reject / 20.000 item, ngưỡng 0,1% | Có thể chưa vượt `skipLimit(25)` nhưng gate từ chối publish |
| 26 reject / 20.000 item với `skipLimit(25)` | Step vượt giới hạn skip và fail |
| Một reason code critical | Gate từ chối dù reject rất ít |
| Header sai cả file | Fail ở preflight; không xử lý như nhiều row skip |
| Manifest khai báo 20.000 nhưng chỉ có 19.900 record | Chặn publish dù `skipCount=0` |
| Quarantine không ghi được | Không chấp nhận kết quả làm dữ liệu thiếu dấu vết |
| Retry hai lần rồi thành công | Không tính là skip cuối |
| Lỗi ở writer khiến rollback | Không tính sai output đã commit; staging/idempotency được kiểm tra |
| Restart hoặc replay | Không ghi trùng, quality snapshot phản ánh toàn bộ lô |

## 14. Lỗi triển khai thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách phòng tránh |
| --- | --- | --- |
| `.skip(Exception.class)` và `skipLimit` cực lớn | Che lỗi dữ liệu diện rộng và lỗi hạ tầng | Chỉ skip exception đã phân loại |
| Chỉ kiểm tra `BatchStatus.COMPLETED` | Không thấy bao nhiêu item bị loại | Kiểm tra skip, filter, reconciliation và publish status |
| Processor `catch(Exception)` rồi `return null` | Lỗi bị biến thành filter không có reject | Chỉ filter theo business rule; lỗi phải đi qua exception |
| Không có manifest/preflight | File thiếu record nhưng skip vẫn bằng 0 | Xác minh nguồn/partition/checksum |
| Log toàn bộ item reject | Rò rỉ dữ liệu nhạy cảm | Mã lý do cố định và token an toàn |
| Không lưu quarantine | Không biết record nào cần sửa | Reject store có locator, version, reason |
| Quarantine viết bất đồng bộ nhưng không xác nhận | Job có thể publish khi evidence bị mất | Outbox/ack/reconciliation trước publish |
| Ghi thẳng bảng production | Job fail sau nhiều chunk đã commit, downstream thấy thiếu | Ghi staging rồi publish có điều kiện |
| Dùng `skipCount` làm số lỗi tuyệt đối toàn lô | Restart/partition có nhiều execution và counter khác phạm vi | Tổng hợp theo source batch và audit bền vững |
| Chỉ đối soát số dòng | Có thể vừa thiếu vừa trùng nhưng count vẫn khớp | Kiểm tra khóa, tổng nghiệp vụ, checksum |
| Tạo `run.id` mới khi muốn restart | Mất cơ chế tiếp tục cùng `JobInstance` | Giữ identifying parameters khi restart |
| Sửa file nguồn nhưng dùng checkpoint cũ | Reader tiếp tục sai vị trí | Phiên bản nguồn bất biến, replay v2 |
| Đưa item ID vào metric labels | Cardinality quá cao, lộ quan hệ dữ liệu | Label theo job/step/reason code |

## 15. Bài thực hành áp dụng

Hãy xây dựng `importOrdersJob` có `validateSourceStep`, `importOrdersStep`, `qualityGateStep` và `publishStep`, với lô đầu vào 20.000 record, `skipLimit=25`, giới hạn reject 0,1% và không chấp nhận `MISSING_ORDER_ID`.

1. Tạo fixture 20.000 record hợp lệ. Chạy job và xác nhận số record nguồn, staging, quarantine, published đều đối soát được.
2. Thêm 10 record có amount sai. Xác nhận chúng bị skip/quarantine, job chỉ publish nếu cả tỷ lệ và phép đối soát đều đạt.
3. Tăng số lỗi lên 21 record. Chỉ ra sự khác nhau giữa `skipLimit=25` (step có thể hoàn thành) và ngưỡng 0,1% (gate phải từ chối).
4. Tăng lên 26 lỗi. Kiểm tra step dừng do vượt `skipLimit`, và dữ liệu staging chưa được công bố.
5. Tạo một item thiếu khóa order ID. Gắn mã `MISSING_ORDER_ID`, xác nhận gate từ chối dù số reject rất nhỏ.
6. Thêm 50 item `CANCELLED` và cho processor filter đúng policy. Xác nhận chúng tăng `filterCount` nhưng không tăng `skipCount`.
7. Cho manifest khai báo 20.000 item nhưng file chỉ chứa 19.900 item. Xác minh job từ chối publish ngay cả khi không có exception nào bị skip.
8. Tạo lỗi ghi quarantine hoặc outbox. Kiểm tra job không thể thông báo một batch đủ điều kiện publish nếu reject evidence chưa bền vững.
9. Mô phỏng writer thất bại sau hai chunk đã commit. Restart job theo cùng identifying parameters, đối soát staging và unique key để tránh duplicate.
10. Tạo phiên bản nguồn v2 chứa các record đã sửa. Replay theo chính sách đã định, cập nhật trạng thái quarantine và phát hành snapshot mới nếu cần.

**Nguyên tắc cốt lõi:** `skip` là một **quyết định xử lý item lỗi**, không phải giấy phép làm thiếu dữ liệu mà không ai biết. Mọi item nguồn phải có kết quả được giải thích bằng **accepted, rejected hoặc filtered** theo một hợp đồng rõ ràng; reject phải có bằng chứng và đường phục hồi; dữ liệu chỉ được publish khi đã vượt qua kiểm tra số lượng, tỷ lệ, tính đầy đủ và quy tắc nghiệp vụ. Khi đó Spring Batch có thể chịu lỗi ở mức item mà vẫn giữ được niềm tin vào dữ liệu đầu ra.
