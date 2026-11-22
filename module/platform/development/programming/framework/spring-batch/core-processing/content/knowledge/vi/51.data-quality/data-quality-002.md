# Quarantine item lỗi trong Spring Batch

Trong một batch job nhập dữ liệu, không phải mọi bản ghi đều hợp lệ. Một dòng CSV có thể thiếu cột, một đơn hàng có mã không tồn tại, một số tiền có giá trị âm hoặc một mã khách hàng không khớp danh mục. Nếu mọi trường hợp như vậy đều làm cả job thất bại, phần dữ liệu hợp lệ có thể bị chặn. Nhưng nếu chỉ bỏ qua bản ghi lỗi mà không giữ bằng chứng, dữ liệu sẽ biến mất khỏi luồng xử lý và rất khó đối soát.

**Quarantine item lỗi** là đưa bản ghi không đạt quy tắc vào một khu vực cách ly có kiểm soát, kèm **nguồn gốc, nguyên nhân lỗi, trạng thái xử lý và liên kết với lần chạy batch**. Bản ghi hợp lệ có thể tiếp tục đi đến đích, còn bản ghi bị cách ly chờ kiểm tra, sửa dữ liệu nguồn hoặc tái xử lý theo quy trình riêng. Đây là kỹ thuật quan trọng của chương **Data quality** trong **Spring Batch Core Processing**.

```text
                 File / Database / Message
                            |
                            v
                     ItemReader<I>
                            |
                            v
                    ItemProcessor<I,O>
                            |
             +--------------+---------------+
             |                              |
        Item hợp lệ                    Lỗi dữ liệu đã biết
             |                              |
             v                              v
        ItemWriter<O>                SkipListener / route
             |                              |
             v                              v
      Bảng nghiệp vụ                  Quarantine store
             |                              |
             +--------------+---------------+
                            |
                            v
                  Đối soát và giám sát
                            |
                            v
                    Sửa / xử lý lại
```

Quarantine phải gắn với một **chính sách dữ liệu rõ ràng**. Không phải exception nào cũng chứng minh một item sai: database mất kết nối, hết bộ nhớ, deadlock hoặc lỗi lập trình thường là vấn đề hệ thống; tự động đưa những item liên quan vào quarantine có thể làm báo cáo “thành công” trong khi job thực tế đã bỏ sót dữ liệu hợp lệ.

## 1. Phân biệt quarantine, filter, skip, retry và fail

Các từ này thường được dùng lẫn nhau nhưng có ý nghĩa khác nhau:

| Hành vi | Khi nào dùng | Tác động trong Spring Batch | Có tự sinh quarantine record? |
| --- | --- | --- | --- |
| **Filter** | Item hợp lệ nhưng không thuộc phạm vi kết quả, ví dụ giao dịch đã đóng từ trước | `ItemProcessor.process()` trả `null`; tăng `filterCount` | Không |
| **Skip** | Item không xử lý được nhưng lỗi được chính sách cho phép bỏ qua | Fault-tolerant step bỏ qua item; tăng bộ đếm skip thích hợp | Không, trừ khi có listener hoặc cơ chế lưu riêng |
| **Retry** | Lỗi có khả năng tạm thời, ví dụ timeout/serialization conflict | Thử lại thao tác theo retry policy; nếu vẫn lỗi thì xử lý tiếp theo chính sách | Không nên mặc định quarantine như lỗi dữ liệu |
| **Fail** | Lỗi không được phép bỏ qua hoặc vượt giới hạn skip | Step/job chuyển trạng thái thất bại | Có thể có lỗi cuối để điều tra, nhưng không mặc định có bản ghi quarantine |
| **Quarantine** | Cần giữ item lỗi và nguyên nhân để review/reprocess | Ứng dụng lưu riêng bản ghi lỗi cùng metadata | Có, do ứng dụng triển khai |

**Skip là quyết định của framework về luồng xử lý; quarantine là quyết định của ứng dụng về lưu vết dữ liệu.** Hai khái niệm có thể phối hợp: cấu hình skip một nhóm exception nghiệp vụ đã biết, rồi dùng `SkipListener` lưu item đã bị bỏ qua vào quarantine store.

Ví dụ với dữ liệu đầu vào:

```text
payment_id,amount
P001,100.00
P002,-50.00
P003,20.00
P004,not-a-number
```

Nếu quy tắc là số tiền phải lớn hơn 0, thì `P002` và `P004` cần đi vào quarantine với mã lỗi cụ thể; `P001` và `P003` được ghi vào bảng đích. Job có thể hoàn tất với skip nếu số lỗi nằm trong giới hạn, nhưng vẫn phải có báo cáo **đã nhận 4 dòng, chấp nhận 2, cách ly 2**.

## 2. Phân loại lỗi trước khi quyết định cách ly

Không có một cấu hình `.skip(Exception.class)` an toàn cho mọi trường hợp. Nên tạo taxonomy lỗi với nhóm nguyên nhân, ví dụ:

| Loại lỗi | Ví dụ | Hành vi nên cân nhắc |
| --- | --- | --- |
| Sai cấu trúc dữ liệu | Thiếu cột CSV, sai kiểu ngày, JSON không parse được | Quarantine nếu còn truy xuất được dòng nguồn và định danh |
| Vi phạm quy tắc nghiệp vụ | Số tiền âm, trạng thái không hợp lệ, sai mã vùng | Quarantine có reason code và thông tin nguồn |
| Không khớp dữ liệu tham chiếu | Mã sản phẩm chưa có trong danh mục | Quarantine hoặc chờ bổ sung master data, tùy chính sách |
| Trùng dữ liệu đã xử lý | Cùng khóa nghiệp vụ được gửi hai lần | Có thể deduplicate/filter, reject hoặc quarantine tùy hợp đồng |
| Timeout/API tạm thời | Endpoint bên ngoài chậm | Retry có giới hạn, sau đó fail/điều phối lại; không gán nhãn item sai |
| Lỗi hạ tầng database | Mất kết nối, deadlock, hết connection pool | Retry nếu an toàn hoặc fail step; cần khôi phục hạ tầng |
| Lỗi lập trình/cấu hình | `NullPointerException`, SQL sai schema, thiếu bean | Fail để sửa ứng dụng; không quarantine hàng loạt |

Nên có **reason code ổn định** (`INVALID_AMOUNT`, `UNKNOWN_CURRENCY`, `INVALID_CSV_LAYOUT`) bên cạnh thông điệp lỗi. Message có thể thay đổi theo ngôn ngữ hoặc phiên bản chương trình; reason code dễ tổng hợp, lập dashboard và đặt quy trình khắc phục hơn. Nếu cần tách lỗi có thể tự sửa và lỗi cần con người xác nhận, thêm `resolution_type` hoặc nhóm severity do nghiệp vụ định nghĩa.

### Filter không đồng nghĩa bị cách ly

Trong Spring Batch, `ItemProcessor` trả `null` nghĩa là **lọc item ra khỏi output**, không phát sinh `onSkipInProcess`. Nếu yêu cầu “mọi dòng không đạt validation phải xuất hiện trong quarantine”, đừng âm thầm trả `null` cho lỗi validation. Thay vào đó, ném exception nghiệp vụ riêng và cấu hình skip, hoặc thiết kế processor trả `ProcessingResult` rồi route rõ nhánh hợp lệ/không hợp lệ đến writer phù hợp.

## 3. Các điểm phát sinh skip và dữ liệu có thể thu thập

Trong một chunk-oriented step, lỗi có thể xảy ra tại các bước khác nhau:

```text
Reader.read() -----------> onSkipInRead(Throwable)
     |
     v
Processor.process(item) --> onSkipInProcess(item, Throwable)
     |
     v
Writer.write(chunk) -----> onSkipInWrite(item, Throwable)
```

`SkipListener<I,O>` cung cấp ba callback tương ứng. Tuy nhiên **dữ liệu sẵn có khác nhau**:

- `onSkipInRead(Throwable)`: framework chưa tạo được item kiểu `I`, vì vậy chỉ có exception. Với `FlatFileParseException`, ta có thể lấy số dòng và nội dung dòng thô; với lỗi database/network thì thường không có một record lỗi cụ thể.
- `onSkipInProcess(I, Throwable)`: có input item gốc, thuận tiện lấy source ID, line number và khóa nghiệp vụ.
- `onSkipInWrite(O, Throwable)`: có output item bị bỏ qua sau xử lý, nên cần giữ source identity trong `O` nếu muốn truy ngược bản ghi đầu vào.

Một chính sách quan trọng: **chỉ cấu hình skip exception đã được xác định là lỗi dữ liệu**. Với writer SQL, chẳng hạn `DataIntegrityViolationException` có thể do dữ liệu cụ thể nhưng cũng có thể do thay đổi schema hoặc ràng buộc mới; cần hiểu lỗi trước khi đưa cả nhóm exception vào skip policy.

### `skipLimit` bảo vệ chất lượng dữ liệu

```java
.faultTolerant()
.skip(InvalidPaymentException.class)
.skip(FlatFileParseException.class)
.skipLimit(10)
```

Trong ví dụ, step được phép skip tối đa tổng cộng **10 lỗi** thuộc những loại đã khai báo. Lỗi tiếp theo làm vượt giới hạn sẽ khiến step thất bại, trừ khi có cấu hình phân loại khác. `readSkipCount`, `processSkipCount` và `writeSkipCount` giúp biết lỗi xảy ra ở khâu nào. Cần chọn giới hạn theo nhu cầu nghiệp vụ: đôi khi chỉ một item lỗi cũng phải fail; lúc khác có thể chấp nhận một ngưỡng nhỏ, ví dụ kết hợp giới hạn tuyệt đối và tỷ lệ lỗi với logic kiểm soát riêng.

## 4. Thiết kế khu vực quarantine

Quarantine không chỉ là một file có tên `bad-records.csv`. Nó cần giúp trả lời: item nào, xuất phát từ đâu, tại bước nào, lỗi vì lý do gì, đã được kiểm tra chưa và kết quả xử lý lại ra sao.

Một mô hình bảng SQL minh họa:

```sql
CREATE TABLE payment_quarantine (
    source_id         VARCHAR(160) NOT NULL,
    source_line       INTEGER NOT NULL,
    failure_stage     VARCHAR(16) NOT NULL,
    reason_code       VARCHAR(64) NOT NULL,
    payment_id        VARCHAR(100),
    job_execution_id  BIGINT NOT NULL,
    step_execution_id BIGINT NOT NULL,
    review_status     VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (source_id, source_line, failure_stage)
);

CREATE INDEX idx_payment_quarantine_review
    ON payment_quarantine (review_status, created_at);
```

Đây là bảng **do ứng dụng sở hữu**, không phải bảng metadata `BATCH_*` của Spring Batch. `source_id` cần biểu thị một phiên bản nguồn **bất biến** (ví dụ object key + version ID hoặc mã import duy nhất); `source_line` định danh vị trí dòng trong nguồn đó. `failure_stage` là `READ`, `PROCESS` hoặc `WRITE`.

Khóa duy nhất `(source_id, source_line, failure_stage)` là một ví dụ về chiến lược chống ghi lặp. Trong một pipeline mà một item có thể bị nhiều loại lỗi cùng stage hoặc bị xử lý theo nhiều phiên bản quy tắc, cần mở rộng identity, lưu lịch sử trạng thái hoặc thiết kế event ID riêng. Không mặc nhiên dùng `jobExecutionId` làm khóa duy nhất vì restart có thể tạo execution mới cho cùng một item lỗi.

### 4.1. Những trường nên có

| Nhóm | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Nguồn gốc | `sourceSystem`, `sourceId`, `sourceVersion`, `lineNumber`, `recordKey` | Truy xuất bản ghi và phiên bản input chính xác |
| Lỗi | `failureStage`, `reasonCode`, `errorCategory`, `schemaVersion` | Phân loại và khắc phục nhất quán |
| Batch | `jobName`, `jobInstanceId`, `jobExecutionId`, `stepExecutionId`, `businessDate` | Liên kết với lịch sử batch |
| Bảo toàn dữ liệu | `rawPayloadRef`, checksum, định dạng/encoding | Tái dựng dữ liệu lỗi mà không rải payload nhạy cảm |
| Quy trình xử lý | `reviewStatus`, `reviewedBy`, `reviewedAt`, `resolution`, `reprocessExecutionId` | Theo dõi từ lúc cách ly đến khi xử lý xong |
| Quản trị | `createdAt`, `retentionClass`, `tenantId` khi cần | Phân quyền, lưu trữ và xóa dữ liệu có kiểm soát |

Nếu nội dung thô chứa thông tin cá nhân hoặc tài chính, có thể chỉ lưu **tham chiếu đến object mã hóa** trong vùng lưu trữ riêng, còn bảng quarantine lưu hash, mã dòng và reason code. Không ghi toàn bộ token, mật khẩu, số tài khoản hoặc nội dung lỗi vào log và exception message.

### 4.2. Lưu file hay lưu database?

| Hình thức | Lợi ích | Rủi ro cần xử lý |
| --- | --- | --- |
| Bảng SQL riêng | Dễ query, gắn trạng thái review, transaction chung với writer khi cùng datasource | Cần schema, index, retention, quyền truy cập và chống ghi lặp |
| File CSV/JSON quarantine | Dễ bàn giao cho người xử lý dữ liệu, phù hợp luồng batch file | Flush/append và rollback không tự đồng bộ với database; phải quản lý file tạm và restart |
| Object storage (S3/MinIO...) | Hợp input lớn, lưu version/retention, có thể mã hóa | Cần manifest và liên kết record; ghi object không nhất thiết atomic với commit Batch |
| Queue hoặc event stream | Hữu ích cho luồng review tự động hoặc hệ thống khác xử lý | Có redelivery, ordering và idempotency; khó bảo đảm exactly-once end-to-end |

Chọn hình thức theo yêu cầu truy xuất, quy mô, quyền truy cập và transaction. Đối với một step JDBC đơn giản, bảng quarantine trong **cùng datasource và transaction manager** thường là điểm xuất phát dễ giải thích nhất.

## 5. Ví dụ Spring Batch 5.x: quarantine khi processor phát hiện lỗi

Ví dụ sau dùng **Spring Batch 5.x, Spring Boot 3.x, Java 17+** và PostgreSQL. Tập đầu vào là các dòng thanh toán có `sourceId`, số dòng và số tiền dạng chuỗi. Processor cho phép tiền dương; nếu số tiền sai định dạng hoặc không lớn hơn 0, nó ném exception nghiệp vụ có mã lỗi rõ ràng.

### 5.1. Model đầu vào, đầu ra và exception nghiệp vụ

```java
package com.example.batch;

import java.math.BigDecimal;

public record PaymentRow(
    String sourceId,
    int sourceLine,
    String paymentId,
    String amountText
) {}

public record AcceptedPayment(
    String sourceId,
    int sourceLine,
    String paymentId,
    BigDecimal amount
) {}
```

Các `record` trên có thể đặt trong hai file Java riêng cùng package. Một exception riêng tránh việc skip nhầm mọi `IllegalArgumentException` (một loại có thể phát sinh từ lỗi lập trình):

```java
package com.example.batch;

public final class InvalidPaymentException extends RuntimeException {
    private final String reasonCode;

    public InvalidPaymentException(String reasonCode, String message) {
        super(message);
        this.reasonCode = reasonCode;
    }

    public String getReasonCode() {
        return reasonCode;
    }
}
```

Processor:

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public final class PaymentValidationProcessor
        implements ItemProcessor<PaymentRow, AcceptedPayment> {

    @Override
    public AcceptedPayment process(PaymentRow row) {
        if (row.paymentId() == null || row.paymentId().isBlank()) {
            throw new InvalidPaymentException(
                "MISSING_PAYMENT_ID", "Payment ID is required");
        }

        final BigDecimal amount;
        try {
            amount = new BigDecimal(row.amountText().trim());
        } catch (RuntimeException ex) {
            throw new InvalidPaymentException(
                "INVALID_AMOUNT_FORMAT", "Amount is not numeric");
        }

        if (amount.signum() <= 0) {
            throw new InvalidPaymentException(
                "AMOUNT_NOT_POSITIVE", "Amount must be positive");
        }

        return new AcceptedPayment(
            row.sourceId(), row.sourceLine(), row.paymentId(), amount);
    }
}
```

Exception message ở đây chỉ chứa mô tả an toàn, còn `reasonCode` được dùng cho dashboard và quarantine. Code validation có thể được unit test độc lập với hạ tầng Batch. Trong hệ thống thực, cần xác định thêm scale, currency, giới hạn số tiền và tính hợp lệ của payment ID.

### 5.2. Bảng dữ liệu hợp lệ

```sql
CREATE TABLE accepted_payment (
    source_id   VARCHAR(160) NOT NULL,
    source_line INTEGER NOT NULL,
    payment_id  VARCHAR(100) NOT NULL,
    amount      NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (source_id, source_line)
);
```

Khóa `(source_id, source_line)` giúp tránh ghi trùng cùng một input record khi một lần chạy mới được phát sinh ngoài ý muốn. Nếu cần dùng khóa nghiệp vụ như `payment_id` để chống trùng giữa nhiều source, nên thiết kế thêm unique constraint và chính sách upsert/deduplication tương ứng.

### 5.3. Writer ghi các item hợp lệ theo batch

```java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
JdbcBatchItemWriter<AcceptedPayment> acceptedPaymentWriter(
        DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<AcceptedPayment>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO accepted_payment
                (source_id, source_line, payment_id, amount)
            VALUES (:sourceId, :sourceLine, :paymentId, :amount)
            """)
        .beanMapped()
        .build();
}
```

`beanMapped()` lấy property từ `AcceptedPayment` để bind vào named parameters. Cách ghi ở trên dùng JDBC transaction do chunk step quản lý. Để minh họa đơn giản, trường hợp một input bị trùng key sẽ làm writer ném exception và step thất bại; ta **không** cấu hình skip mọi database exception.

### 5.4. `SkipListener` ghi bản ghi quarantine

Listener bên dưới chỉ lưu khi processor ném `InvalidPaymentException`. Ví dụ sử dụng PostgreSQL `ON CONFLICT DO NOTHING` để tránh thêm hai hàng quarantine cho cùng nguồn, số dòng và stage. Câu SQL cần thay đổi nếu dùng database khác.

```java
package com.example.batch;

import java.sql.Timestamp;
import java.time.Instant;

import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.SkipListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class PaymentQuarantineListener
        implements SkipListener<PaymentRow, AcceptedPayment> {

    private final JdbcTemplate jdbc;
    private final StepExecution execution;

    public PaymentQuarantineListener(
            JdbcTemplate jdbc,
            @Value("#{stepExecution}") StepExecution execution) {
        this.jdbc = jdbc;
        this.execution = execution;
    }

    @Override
    public void onSkipInProcess(PaymentRow item, Throwable error) {
        InvalidPaymentException invalid = (InvalidPaymentException) error;

        jdbc.update("""
            INSERT INTO payment_quarantine (
                source_id, source_line, failure_stage, reason_code,
                payment_id, job_execution_id, step_execution_id,
                review_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_id, source_line, failure_stage)
            DO NOTHING
            """,
            item.sourceId(),
            item.sourceLine(),
            "PROCESS",
            invalid.getReasonCode(),
            item.paymentId(),
            execution.getJobExecutionId(),
            execution.getId(),
            "PENDING",
            Timestamp.from(Instant.now())
        );
    }
}
```

`@StepScope` giúp listener nhận `StepExecution` của lần chạy hiện tại; không dùng biến singleton mutable để giữ thông tin giữa nhiều execution. Trong cấu hình này, vì skip policy chỉ cho phép `InvalidPaymentException` từ processor nên ép kiểu trong callback `onSkipInProcess` có cơ sở. Nếu mở rộng policy, cần phân loại exception tại callback thay vì ép kiểu không kiểm tra.

**Quan hệ với transaction rất quan trọng:** Spring Batch gọi `SkipListener` vào thời điểm thích hợp trước khi transaction commit để giảm nguy cơ callback được gọi lặp cho cùng item sau rollback. Nếu `JdbcTemplate` ghi quarantine dùng **cùng datasource và transaction manager** với writer, insert quarantine có thể nằm trong cùng chunk transaction. Khi lỗi trước commit, cả dữ liệu hợp lệ của chunk và quarantine record chưa commit được rollback; điều này giúp giữ tính nhất quán.

Không tự thêm `@Transactional(propagation = REQUIRES_NEW)` vào phương thức ghi quarantine chỉ vì muốn “bảo đảm vẫn ghi được log lỗi”. Transaction riêng có thể commit quarantine ngay cả khi chunk bị rollback, khiến một item vừa được coi là cách ly vừa được xử lý lại ở lần retry/restart. Nếu cần giữ mọi attempt đã thất bại, hãy tách **audit event về attempt** khỏi **quarantine record của item thực sự bị loại**, với hai hợp đồng rõ ràng.

### 5.5. Cấu hình `Step` với skip policy

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentRow> paymentReader,
        JdbcBatchItemWriter<AcceptedPayment> acceptedPaymentWriter,
        PaymentQuarantineListener quarantineListener) {

    return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentRow, AcceptedPayment>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(new PaymentValidationProcessor())
        .writer(acceptedPaymentWriter)
        .faultTolerant()
        .skip(InvalidPaymentException.class)
        .skipLimit(10)
        .listener(quarantineListener)
        .build();
}
```

Ví dụ giả định `paymentReader` được cấu hình từ file/database test và trả `PaymentRow` kèm định danh nguồn. `faultTolerant()`, `skip(...)` và `skipLimit(...)` là cơ chế Spring Batch 5.x. Mỗi item bị skip trong processor tạo một sự kiện `onSkipInProcess`; listener lưu item kèm `reasonCode`.

Một điểm không nên bỏ sót: **không phải chỉ cần `.skipLimit(10)` là hoàn tất chính sách chất lượng dữ liệu**. Nghiệp vụ có thể cần fail khi tỷ lệ lỗi vượt 1%, khi có bất kỳ lỗi thuộc loại `UNKNOWN_ACCOUNT`, hoặc khi thiếu dữ liệu đầu vào bắt buộc. Những quy tắc tổng hợp này cần được thiết kế ở mức step/job và được kiểm tra bằng fixture tương ứng.

## 6. Cách ly dòng lỗi ngay ở `ItemReader`

Một dòng CSV sai cấu trúc có thể làm `FlatFileItemReader` không tạo được `PaymentRow`. Khi đó `onSkipInProcess` không chạy; cần dùng `onSkipInRead` để lấy thông tin từ exception.

### 6.1. Reader lấy source identity và line number

Ví dụ cấu hình reader theo Spring Batch 5.x:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<PaymentRow> paymentReader(
        @Value("#{jobParameters['inputPath']}") String inputPath,
        @Value("#{jobParameters['sourceId']}") String sourceId) {

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setNames("paymentId", "amount");
    tokenizer.setStrict(true);

    FlatFileItemReader<PaymentRow> reader = new FlatFileItemReader<>();
    reader.setName("paymentReader");
    reader.setResource(new FileSystemResource(inputPath));
    reader.setLinesToSkip(1); // header
    reader.setLineMapper((line, lineNumber) -> {
        var fields = tokenizer.tokenize(line);
        return new PaymentRow(
            sourceId,
            lineNumber,
            fields.readString("paymentId"),
            fields.readString("amount")
        );
    });
    return reader;
}
```

Mẫu này dành cho CSV đơn giản gồm hai trường, không xét đầy đủ tình huống dấu phẩy nằm trong chuỗi trích dẫn, nhiều dòng logic hoặc escape phức tạp. Dữ liệu CSV thực tế cần tokenizer/reader được cấu hình đúng định dạng nguồn. `FlatFileItemReader` có khả năng bọc lỗi mapping thành `FlatFileParseException`, cung cấp số dòng và nội dung thô của dòng gây lỗi.

Khi chạy step, bổ sung:

```java
.skip(FlatFileParseException.class)
```

Với trường hợp read skip, listener có thể kiểm tra exception:

```java
@Override
public void onSkipInRead(Throwable error) {
    if (!(error instanceof FlatFileParseException parse)) {
        return;
    }

    // sourceId được inject qua JobParameters trong listener @StepScope.
    // parse.getLineNumber() là dòng trong file gốc.
    // Lưu reasonCode = INVALID_CSV_LAYOUT, failureStage = READ.
    // Chỉ lưu raw line khi chính sách bảo mật cho phép.
}
```

Với listener ở phần 5, để triển khai callback này cần inject thêm `sourceId` vào constructor, rồi dùng cùng một hàm `saveQuarantine(sourceId, parse.getLineNumber(), "READ", ...)`. Ở lỗi đọc trước khi mapping, `PaymentRow` chưa tồn tại nên không có `paymentId` đáng tin để lưu. Nếu cần giữ raw input, có thể tính checksum hoặc lưu trữ mã hóa theo `sourceId`/line number; đừng mặc định in `parse.getInput()` vào log.

**Không nên skip mọi exception của reader.** Lỗi resource không tồn tại, mất kết nối hoặc file bị đổi đột ngột có thể làm mất tính đầy đủ của dữ liệu; nên fail job để vận hành kiểm tra. Quarantine đọc chỉ phù hợp khi xác định được một record lỗi và reader có thể tiếp tục an toàn tới record kế tiếp.

## 7. Quarantine khi writer lỗi: cần thận trọng hơn

`onSkipInWrite(O item, Throwable)` có thể cung cấp item đầu ra bị bỏ qua. Tuy nhiên, lỗi writer thường xảy ra **ở cấp batch/chunk** hoặc transaction, không nhất thiết là lỗi của một item. Spring Batch có thể phải thử chia nhỏ batch hoặc lặp lại ghi để xác định item gây lỗi, tùy loại writer và cơ chế fault tolerance.

Ví dụ:

- `DuplicateKeyException` do một payment ID đã tồn tại có thể là lỗi dữ liệu theo hợp đồng, nhưng cũng có thể là **item đã được ghi thành công ở lần chạy trước**. Nếu đẩy thẳng vào quarantine, có thể biến một restart đúng thành false rejection.
- `DataAccessResourceFailureException`, timeout hoặc deadlock là lỗi hệ thống; bỏ qua một item không giải quyết nguyên nhân và có thể khiến thiếu dữ liệu.
- Writer gọi API bên ngoài có thể đã tạo side effect nhưng trả timeout; quarantine item và gửi lại sau đó có nguy cơ tạo giao dịch trùng.

Chỉ áp dụng skip ở writer nếu có thể nhận diện lỗi theo **đúng item**, có transaction/rollback đáng tin và chính sách nghiệp vụ cho phép. Với sai mã tham chiếu hay amount, thường tốt hơn là **validation trong processor** trước khi writer thực thi. Khi không chắc lỗi phát sinh từ dữ liệu, hãy để step fail, giữ `JobRepository` và tiến hành restart sau khi xử lý hạ tầng.

## 8. Transaction, rollback và tính nhất quán giữa hai đích

Giả sử trong một chunk có 3 payment:

```text
P001 (hợp lệ)
P002 (số tiền âm)
P003 (hợp lệ)
```

Với `skip(InvalidPaymentException.class)` và listener ghi quarantine vào **cùng database, cùng chunk transaction**:

```text
BEGIN TRANSACTION
  process P001 -> valid
  process P002 -> skip, đánh dấu cần quarantine
  process P003 -> valid

  INSERT accepted_payment(P001)
  INSERT accepted_payment(P003)
  INSERT payment_quarantine(P002, AMOUNT_NOT_POSITIVE)
  ghi checkpoint/metadata theo cơ chế Spring Batch
COMMIT
```

Kết quả mong đợi khi transaction commit thành công: bảng đích có `P001`, `P003`; quarantine có `P002`; step có `readCount=3`, `processSkipCount=1`, `writeCount=2` trong điều kiện fixture này.

Nếu transaction rollback trước commit, các insert cùng transaction không trở thành dữ liệu bền vững. Khi framework xử lý lại, listener có thể được gọi trong lần xử lý thành công sau đó. Chính sách giao dịch của `SkipListener` và datasource cần được kiểm thử bằng failure injection chứ không dựa vào giả định listener luôn chạy đúng một lần trong mọi cấu hình tùy chỉnh.

### 8.1. Khi quarantine nằm ở datasource khác

Nếu dữ liệu hợp lệ được ghi vào database A còn quarantine được gửi qua REST hoặc ghi vào object storage B, **không có transaction JDBC cục bộ nào bảo đảm cả hai đích commit đồng thời**. Một bên có thể thành công và bên kia thất bại.

Các phương án kiến trúc:

1. **Transactional outbox:** trong transaction nghiệp vụ, lưu record hợp lệ và outbox event về item cần cách ly; một publisher phát ra kho quarantine/queue sau commit. Publisher phải idempotent và có retry.
2. **Staging + reconciliation:** ghi cả kết quả và trạng thái reject vào một khu vực staging có kiểm soát rồi phát tán sang các đích sau khi đã đối soát.
3. **Quarantine độc lập có audit:** khi yêu cầu lưu mọi attempt, chấp nhận eventual consistency nhưng gắn `eventId`, source identity và trạng thái `PENDING/CONFIRMED` để tránh hiểu nhầm event chưa commit là reject cuối cùng.

Quarantine theo kiểu “fire-and-forget” gửi message bất đồng bộ trong `onSkipInProcess()` đặc biệt rủi ro: callback có thể chạy nhưng message gửi lỗi, hoặc message được gửi trước khi transaction chunk cuối cùng commit. Nếu phải gửi message, nên dùng outbox hoặc cơ chế transaction phù hợp.

### 8.2. Ghi file quarantine

Khi ghi quarantine ra file, cần tính tới buffer, flush, append và restart. File không tự rollback như transaction JDBC. Một writer có thể cần quản lý `ItemStream.open/update/close`, trạng thái vị trí cuối đã ghi và đường dẫn output riêng theo job instance. Nếu xuất file cho người xử lý, có thể ghi file tạm theo source version, rồi chỉ publish manifest/quarantine file sau khi step/job hoàn tất và đối soát số lượng.

## 9. Không ghi quarantine trùng khi retry và restart

Trong Spring Batch, một `JobInstance` thất bại có thể có nhiều `JobExecution` khi restart. Item có thể được xử lý lại nếu chunk trước chưa commit. Vì vậy cần khóa idempotency theo **danh tính bản ghi nguồn**, không chỉ theo execution của lần chạy.

```text
sourceId = bank-feed-20261116-object-version-v4
sourceLine = 875
stage = PROCESS

Lần chạy #1: item bị lỗi, transaction chunk rollback
Lần chạy #2: restart, item lại sai

=> chỉ một quarantine record cuối cùng được công nhận
   cho (sourceId, sourceLine, stage)
```

Khóa duy nhất như ví dụ SQL và câu `INSERT ... ON CONFLICT DO NOTHING` giúp idempotent trong PostgreSQL, nhưng vẫn phải có chính sách với bản ghi lỗi được sửa hoặc business rule thay đổi. Nếu source đã chỉnh nội dung, hãy cấp source version mới hoặc lưu *correction event*, không âm thầm thay đổi nội dung thô của bản ghi đã được cách ly.

**Đừng tự động coi một bản ghi đã có trong quarantine là được phép bỏ qua mãi mãi.** Sau khi sửa dữ liệu nguồn, nó có thể trở thành hợp lệ và cần xử lý lại. Cách xử lý phải dựa trên trạng thái review, source version và run policy, không chỉ sự tồn tại của khóa.

### 9.1. `JobInstance` khác `JobExecution`

```text
Job: importPaymentsJob
Identifying JobParameters: sourceId=feed-v4

JobInstance 220
  +-- JobExecution 801  FAILED
  +-- JobExecution 805  COMPLETED (restart)
```

Nếu scheduler thêm UUID identifying mới mỗi lần, có thể tạo `JobInstance` khác cho cùng `sourceId`, khiến import chạy lại từ đầu. Chống trùng bằng business key/quarantine key vẫn cần thiết, nhưng tốt hơn là thiết kế `JobParameters` đúng ngữ nghĩa kỳ xử lý và sử dụng restart chính thức khi phù hợp.

### 9.2. Skip listener và at-least-once

Spring Batch cố gắng gọi skip listener một lần cho mỗi item được skip tại vị trí thích hợp trong transaction. Tuy vậy, hệ thống phân tán hoặc external side effect không bảo đảm **exactly-once** chỉ nhờ callback. Phần lưu quarantine vẫn cần idempotency, và event audit của từng attempt cần có `eventId` riêng nếu muốn giữ lịch sử retry.

## 10. Vòng đời bản ghi đã quarantine

Quarantine chỉ có ý nghĩa nếu có người hoặc tiến trình xử lý tiếp. Một vòng đời gợi ý:

```text
PENDING
   |
   +-- REVIEWING
          |
          +-- READY_FOR_REPROCESS
          |       |
          |       +-- REPROCESSED
          |       +-- REPROCESS_FAILED -> REVIEWING
          |
          +-- REJECTED_PERMANENTLY
          |
          +-- DUPLICATE / NOT_ACTIONABLE
```

Trạng thái chỉ là ví dụ; tên và điều kiện transition cần do nghiệp vụ định nghĩa. Mỗi lần chuyển trạng thái nên lưu ai thực hiện, thời gian, lý do, phiên bản dữ liệu đã sửa và `reprocessExecutionId` khi có. Không chỉ update một cột `status` mà mất hết lịch sử phê duyệt.

### 10.1. Tái xử lý bằng input đã sửa

Một quy trình an toàn:

1. Đọc quarantine record ở trạng thái cho phép sửa; người có quyền xem lỗi và xác định dữ liệu nguồn.
2. Tạo phiên bản input **đã sửa** hoặc một correction payload riêng, không ghi đè bằng chứng nguồn gốc.
3. Gán nguồn mới có `sourceVersion`/correction ID và yêu cầu xử lý rõ kỳ nghiệp vụ.
4. Chạy một job/step tái xử lý có cùng validation như luồng nhập chính; dùng idempotency key để không tạo output trùng.
5. Xác minh kết quả ở đích và cập nhật trạng thái `REPROCESSED` cùng execution ID mới.

Tái xử lý record được quarantine thường là **một nghiệp vụ xử lý lại có chủ đích**, không nhất thiết là `restart` của batch job cũ. Restart Spring Batch chủ yếu tiếp tục `JobInstance` thất bại từ checkpoint; còn reprocess sau khi dữ liệu đã được sửa có thể cần tạo phiên bản input và run mới để giữ audit minh bạch.

### 10.2. Đối soát số lượng

Với quy trình một input record sinh tối đa một output record, có thể kỳ vọng:

```text
Số record input đã đọc thành công
  = số record hợp lệ đã ghi
  + số record bị filter có chủ đích
  + số record bị skip trong processor
  + số record bị skip trong writer

Số dòng lỗi parse trước khi tạo item
  được theo dõi riêng bằng readSkipCount
```

Đây là công thức **minh họa cho pipeline 1:1 không có retry chưa commit và không có các phép biến đổi mở rộng/gộp item**. Trong thực tế, skip ở writer, rollback, một-to-many transformation và nhiều step có thể khiến đối chiếu theo counter đơn giản không chính xác. Khi đối soát quan trọng, hãy tính số input duy nhất, output nghiệp vụ đã commit và quarantine record đã xác nhận theo business key/source version.

Ví dụ một file có bốn dòng dữ liệu trong đó ba dòng parse thành `PaymentRow`, một dòng sai cấu trúc; trong ba dòng đã parse, một dòng amount âm. Nếu step hoàn tất với skip thì `readCount=3`, `readSkipCount=1`, `processSkipCount=1`, `writeCount=2` là một kết quả hợp lý cho fixture đó; số dòng nguồn không tính header là `4`.

## 11. Monitoring và SLA cho dữ liệu cách ly

Đưa item lỗi vào quarantine chưa đủ nếu không có giám sát. Nên theo dõi **theo kỳ dữ liệu và nguồn**:

| Metric | Ý nghĩa | Gợi ý xử lý |
| --- | --- | --- |
| `quarantine_count` | Tổng record bị cách ly | Cảnh báo khi tăng đột biến |
| `quarantine_ratio` | Tỷ lệ record bị cách ly trên input | Phát hiện lỗi chất lượng dữ liệu diện rộng |
| `quarantine_by_reason` | Phân bố mã lỗi | Phân biệt thay đổi schema, thiếu master data, sai business rule |
| `oldest_pending_age` | Tuổi bản ghi chưa được review lâu nhất | Theo dõi SLA xử lý |
| `reprocess_success_rate` | Tỷ lệ tái xử lý thành công | Đánh giá hiệu quả sửa dữ liệu |
| `duplicate_quarantine_attempts` | Số attempt trùng idempotency key | Phát hiện retry/rerun bất thường |
| `skipped_items` của StepExecution | Skip ở read/process/write | Đối chiếu với số quarantine thực đã persist |

Khi xuất metrics sang Prometheus/Micrometer, chỉ dùng label có **cardinality thấp** như `jobName`, `reasonCode`, `stage` hoặc nhóm nguồn. Không gắn `paymentId`, `sourceLine` hay `jobExecutionId` của từng item vào metric label, vì số chuỗi giá trị quá lớn có thể làm hệ monitoring quá tải. Các định danh chi tiết thuộc database audit/quarantine hoặc log có cấu trúc với retention phù hợp.

`BatchStatus.COMPLETED` với skip có thể vẫn là **thành công kỹ thuật**, nhưng nghiệp vụ có thể coi kỳ dữ liệu ở trạng thái `COMPLETED_WITH_REJECTIONS` hoặc `NEEDS_REVIEW`. Hãy định nghĩa trạng thái đó trong báo cáo/quy trình riêng; không tự đồng nhất `COMPLETED` với “100% dữ liệu đã được chấp nhận”.

## 12. Kiểm thử quarantine item lỗi

Cần kết hợp unit test cho classification và integration test cho transaction/skip behavior. Một test chỉ gọi `PaymentValidationProcessor.process()` không chứng minh quarantine record thực sự được lưu, cũng không bảo đảm restart không tạo trùng.

### 12.1. Unit test processor

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class PaymentValidationProcessorTest {
    private final PaymentValidationProcessor processor =
        new PaymentValidationProcessor();

    @Test
    void acceptsPositiveAmount() {
        AcceptedPayment result = processor.process(
            new PaymentRow("feed-v4", 2, "P001", "100.00"));

        assertThat(result.amount()).isEqualByComparingTo("100.00");
    }

    @Test
    void rejectsNonPositiveAmountWithReasonCode() {
        assertThatThrownBy(() -> processor.process(
            new PaymentRow("feed-v4", 3, "P002", "-50.00")))
            .isInstanceOf(InvalidPaymentException.class)
            .extracting("reasonCode")
            .isEqualTo("AMOUNT_NOT_POSITIVE");
    }
}
```

Unit test này xác nhận lỗi nghiệp vụ và reason code. Nó không cần Spring context hay `JobRepository`.

### 12.2. Integration test step với dữ liệu lỗi

Chuẩn bị database thử nghiệm có hai bảng `accepted_payment`, `payment_quarantine` và một file input:

```csv
paymentId,amount
P001,100.00
P002,-50.00
P003,20.00
```

Trong Spring Batch 5.x, với `@SpringBatchTest`, có thể dùng `JobLauncherTestUtils.launchStep(...)` và `JobParameters` mang `sourceId` cùng `inputPath` tới reader:

```java
JobParameters params = new JobParametersBuilder()
    .addString("sourceId", "feed-test-v1")
    .addString("inputPath", input.toAbsolutePath().toString(), false)
    .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchStep(
    "importPaymentsStep", params);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .iterator().next();

assertThat(step.getReadCount()).isEqualTo(3);
assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getWriteCount()).isEqualTo(2);

Integer accepted = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM accepted_payment", Integer.class);
Integer quarantined = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM payment_quarantine", Integer.class);

assertThat(accepted).isEqualTo(2);
assertThat(quarantined).isEqualTo(1);
```

Đây là **phần test minh họa**, giả định các bean, schema, database và `input` đã được chuẩn bị trong test fixture. Đối với test production, không chỉ đếm hàng; nên assert `source_id`, `source_line`, `reason_code`, số tiền của các bản ghi hợp lệ và absence của dữ liệu sai. Mỗi test cần nguồn và schema/transaction được cô lập để tránh phụ thuộc lần chạy trước.

### 12.3. Các failure path cần kiểm chứng

1. **Sai cấu trúc khi đọc:** một dòng CSV thiếu cột phải tăng `readSkipCount`; nếu được phép skip và đã cấu hình `onSkipInRead`, quarantine có đúng `sourceId`/line number.
2. **Lỗi validation:** amount âm hoặc mã thiếu làm tăng `processSkipCount`; dữ liệu hợp lệ vẫn được ghi.
3. **Vượt `skipLimit`:** job/step thất bại theo cấu hình, không âm thầm chấp nhận một lô có quá nhiều lỗi.
4. **Quarantine insert thất bại:** khi cùng datasource/transaction, kiểm tra chunk không bị commit lệch giữa accepted và quarantine.
5. **Rollback rồi retry:** không có quarantine row bền vững thuộc một attempt đã rollback; khi item cuối cùng bị skip thành công, xuất hiện đúng record.
6. **Restart sau lỗi:** giữ cùng identifying parameters, xác nhận output/quarantine không trùng và `JobInstance` không bị tạo mới ngoài ý muốn.
7. **Gửi lại cùng source version:** unique key hoặc cơ chế upsert chặn duplicate không mong muốn, nhưng test vẫn báo đúng chất lượng input.
8. **Hệ thống ngoài gặp timeout:** không classify nhầm là `INVALID_PAYMENT`; batch phải retry/fail đúng như thiết kế.
9. **Reprocess sau correction:** một phiên bản dữ liệu đã sửa được ghi vào bảng đích và quarantine record cũ chuyển trạng thái rõ ràng.

Nếu test cả tình huống reader parse và processor validation trong một file bốn dòng, có thể kỳ vọng `readSkipCount=1`, `processSkipCount=1`, `writeCount=2` với cấu hình cho phép skip cả `FlatFileParseException` và `InvalidPaymentException`. Cần bảo đảm **listener thực tế ghi cả hai loại lỗi** trước khi assert hai hàng quarantine.

## 13. Quản trị dữ liệu quarantine

Quarantine thường chứa dữ liệu “xấu” nhưng vẫn có thể là thông tin nhạy cảm. Nên tổ chức quyền và retention ngay từ đầu:

- **Giới hạn quyền đọc:** người review có thể xem những trường cần thiết; truy cập raw payload cần quyền riêng và lý do rõ ràng.
- **Không log toàn bộ input:** ngoại lệ parser có thể chứa dòng CSV gốc; chỉ ghi reason code, source reference, line number hoặc nội dung đã redact.
- **Mã hóa và phân tách lưu trữ:** object raw nên được mã hóa tại nơi lưu và trên đường truyền, có kiểm soát truy cập độc lập với bảng summary.
- **Audit thao tác sửa:** lưu người sửa, thời điểm, reason, phiên bản dữ liệu đã cập nhật và execution tái xử lý.
- **Retention và xóa:** thời hạn giữ quarantine phụ thuộc nghiệp vụ/pháp lý; tránh giữ payload vô hạn chỉ vì “có thể cần debug”.
- **Không xóa metadata batch quá sớm:** giữ `JobRepository` đủ cho các execution còn cần restart, đồng thời có audit/quarantine retention phù hợp.

Một bản ghi quarantine không nên được chỉnh trực tiếp thành “dữ liệu tốt” bằng cách xóa reason code. Dấu vết nguồn gốc và quyết định xử lý cần được giữ để giải thích vì sao dữ liệu đầu vào từng bị từ chối.

## 14. Những lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| `.skip(Exception.class)` | Che lỗi lập trình/hạ tầng, bỏ qua cả dữ liệu hợp lệ | Chỉ skip exception nghiệp vụ đã phân loại |
| Processor trả `null` cho mọi item sai | Filter count tăng nhưng không có quarantine record | Dùng exception riêng + skip listener hoặc route result có cấu trúc |
| Không giữ `sourceId` và line/record key | Không biết item lỗi đến từ đâu | Đưa source identity/version vào input model và audit |
| Ghi quarantine bằng transaction riêng trong callback | Có thể tồn tại reject từ chunk đã rollback | Ưu tiên transaction chung hoặc outbox có hợp đồng rõ |
| Quarantine cùng dữ liệu nhiều lần khi restart | Tạo danh sách lỗi trùng và sai số lượng | Unique key theo nguồn/record/stage, idempotent insert |
| Skip mọi lỗi writer | Có thể bỏ qua lỗi database hoặc API tạm thời | Retry/fail theo loại lỗi; validation trước writer nếu có thể |
| Chỉ kiểm tra job `COMPLETED` | Không biết có bao nhiêu record bị cách ly | Assert counts, bảng đích, quarantine và nghiệp vụ |
| Reprocess bằng cách thay dữ liệu gốc tại chỗ | Mất dấu vết và khó đối soát | Lưu correction version, event và execution tái xử lý |
| Lưu raw exception/payload vào log | Rò rỉ dữ liệu nhạy cảm | Redaction, reference, checksum và phân quyền |
| Không có người xử lý quarantine | Dữ liệu tồn đọng vô hạn | Workflow review, SLA, cảnh báo và retention |
| Hiểu `readSkipCount` là số item có `PaymentRow` | Read skip thường xảy ra trước mapping | Dùng parse exception/source line để truy nguyên |
| Dùng UUID identifying mới cho mọi restart | Tạo instance mới, có nguy cơ ghi trùng | Giữ identifying parameters cho restart đúng nghĩa |

## 15. Chiến lược lựa chọn quarantine theo tình huống

Một quyết định thực tế có thể đi theo các câu hỏi sau:

```text
Phát hiện một item có vấn đề
            |
            v
Lỗi do dữ liệu cụ thể, có thể nhận diện item?
       |                         |
      Có                       Không
       |                         |
       v                         v
Lỗi có được phép bỏ qua?      Retry/fail/điều tra
       |                         hạ tầng hoặc code
       |
   +---+---+
   |       |
  Có      Không
   |       |
   v       v
Skip có   Fail step/job
giới hạn
   |
   v
Lưu quarantine đúng nguồn + reason
trong transaction/outbox phù hợp
   |
   v
Đối soát số liệu + review + reprocess
```

Với một batch nhập đơn hàng, có thể quarantine `UNKNOWN_PRODUCT` và `INVALID_AMOUNT`, nhưng dừng toàn bộ job khi thiếu file đầu vào hoặc database không kết nối. Với một batch tài chính quan trọng, thậm chí một record sai cũng có thể cần fail job và yêu cầu phê duyệt; quarantine vẫn có thể được ghi để phục vụ điều tra, nhưng policy **cho phép hoàn tất với lỗi** phải được xác định riêng.

## Kết luận

Quarantine item lỗi là một phần của kiến trúc **chất lượng dữ liệu và khả năng vận hành**, không chỉ là một `SkipListener`. Một thiết kế tốt phải **phân loại lỗi đúng**, giữ source identity bất biến, lưu reason code và trạng thái review, bảo đảm consistency giữa output hợp lệ và khu vực cách ly, hạn chế lỗi bị skip, đồng thời hỗ trợ restart và reprocess mà không nhân đôi kết quả.

Khi Spring Batch báo `COMPLETED` có skip, hệ thống vẫn cần trả lời được: **bao nhiêu item được chấp nhận, bao nhiêu bị cách ly, vì sao bị loại, ai sẽ xử lý và làm thế nào đưa dữ liệu đã sửa trở lại luồng xử lý một cách có kiểm soát**.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): cách cấu hình `faultTolerant`, `.skip(...)` và `.skipLimit(...)`.
- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `SkipListener`, các callback và vòng đời step/chunk.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): phân biệt lỗi tạm thời cần retry với item không hợp lệ.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): quản lý `ExecutionContext` và restart reader/writer.
- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): parsing, line mapping và `FlatFileItemReader`.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử job/step, skip và dữ liệu đầu ra.
