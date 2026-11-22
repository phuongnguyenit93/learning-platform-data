# Dữ liệu duplicate trong kiểm thử Spring Batch

## 1. Dữ liệu duplicate là gì và tại sao phải kiểm thử?

Trong một batch job, **duplicate** là dữ liệu được xử lý nhiều lần dù quy tắc nghiệp vụ chỉ cho phép ghi nhận một lần. Duplicate có thể xuất hiện ngay trong một file đầu vào, giữa hai file khác nhau, giữa hai chunk, giữa hai lần chạy job hoặc khi một job được khởi động lại sau lỗi.

Ví dụ, hệ thống nhận các giao dịch thanh toán với mã sự kiện `eventId`. Một file có hai dòng mang `eventId=PAY-001`. Nếu `eventId` là mã sự kiện duy nhất, việc ghi cả hai dòng có thể làm số tiền được tính hai lần. Tuy nhiên, nếu mỗi dòng biểu diễn một lần điều chỉnh hợp lệ với mã giao dịch độc lập, việc loại bỏ một dòng chỉ vì trùng `customerId` lại làm mất dữ liệu đúng.

Vì vậy, **“duplicate” phải được định nghĩa theo khóa nghiệp vụ và quy tắc xử lý**, không thể xác định chỉ bằng việc hai dòng nhìn giống nhau.

Trong ngữ cảnh **Spring Batch Core Processing → Test data**, dữ liệu duplicate là một nhóm **test fixture bắt buộc** để trả lời các câu hỏi:

- Job phát hiện trùng bằng khóa nào: toàn bộ dòng, `eventId`, `orderId`, hay tổ hợp các trường?
- Dữ liệu trùng bị loại, cập nhật, gộp, chuyển sang quarantine hay làm job thất bại?
- Hai bản ghi trùng nằm ở hai chunk khác nhau có được xử lý nhất quán?
- Chạy lại cùng dữ liệu, retry chunk hoặc restart job có làm phát sinh hiệu ứng nghiệp vụ thêm một lần?
- Nếu cùng khóa nhưng nội dung khác nhau, job có phát hiện xung đột thay vì âm thầm bỏ qua?
- Số liệu `readCount`, `filterCount`, `writeCount` và số bản ghi thực tế trong database có được hiểu đúng?

Spring Batch không mặc định loại bỏ duplicate. `ItemReader` đọc các item theo cấu hình, `ItemProcessor` biến đổi/lọc nếu được lập trình như vậy, và `ItemWriter` thực hiện ghi dữ liệu. Chính yêu cầu nghiệp vụ và cách triển khai quyết định cách job phản ứng với dữ liệu trùng.

## 2. Phân loại duplicate để thiết kế test chính xác

| Loại | Ví dụ | Điều cần kiểm thử |
| --- | --- | --- |
| Trùng toàn bộ dòng (*exact duplicate*) | `PAY-001,C01,100.00` xuất hiện hai lần | Chỉ một hiệu ứng nghiệp vụ được ghi nhận nếu mỗi event chỉ được xử lý một lần |
| Trùng khóa, nội dung khác (*conflicting duplicate*) | `PAY-001,C01,100.00` và `PAY-001,C01,900.00` | Phát hiện xung đột; không âm thầm nuốt dữ liệu sai nếu nghiệp vụ không cho phép |
| Trùng sau chuẩn hóa | `pay-001` và ` PAY-001 ` | Quy tắc trim/chữ hoa chữ thường được áp dụng nhất quán |
| Trùng xuyên chunk | Dòng 1 và dòng 7 trùng nhau, chunk size = 3 | Cơ chế chống trùng vẫn hoạt động dù hai item nằm ở hai transaction khác nhau |
| Trùng giữa các file | Hai nguồn cùng gửi `PAY-001` | Khóa idempotency tồn tại xuyên qua phạm vi một file |
| Trùng giữa các lần chạy | Job hôm nay đọc lại file hôm qua | Chạy lại không tạo thêm side effect ngoài mong muốn |
| Trùng do retry/restart | Chunk đã ghi được phát lại sau failure hoặc restart | Database và hệ thống ngoài không nhận hai lần cùng một hiệu ứng |
| Trùng trong xử lý song song | Hai partition/thread cùng gặp `PAY-001` | Chống trùng vẫn đúng khi xử lý đồng thời |

Không phải mọi giá trị lặp lại đều là duplicate. `customerId=C01` có thể xuất hiện trong hàng nghìn giao dịch hợp lệ. Khóa được chọn thường là **event ID**, **mã giao dịch của nguồn**, hoặc một tổ hợp như `(sourceSystem, externalTransactionId)`. Khi không có khóa tin cậy, cần làm rõ contract dữ liệu trước khi quyết định loại bỏ dòng.

### Khác biệt giữa duplicate nghiệp vụ và metadata Spring Batch

Hai khái niệm thường bị nhầm:

1. **Duplicate của dữ liệu nghiệp vụ:** hai item đầu vào cùng đại diện cho một sự kiện cần tính đúng một lần.
2. **Trùng `JobInstance`:** khởi chạy cùng tên job với cùng các **identifying `JobParameters`**. Spring Batch có quy tắc riêng để ngăn chạy lại một instance đã hoàn tất.

Đổi `run.id` tạo `JobInstance` mới có thể giúp job được chạy lại, nhưng **không tự bảo đảm bảng nghiệp vụ sẽ tránh chèn trùng**. Ngược lại, cleanup các bảng `BATCH_*` không xóa dữ liệu nghiệp vụ đã ghi. Hai lớp trạng thái phải được kiểm thử riêng.

## 3. Mô hình dòng xử lý và điểm kiểm soát duplicate

```text
CSV/API/Queue
     |
     v
 ItemReader  ------> readCount: các item được đọc
     |
     v
 ItemProcessor
   |-- validate
   |-- chuẩn hóa business key
   |-- trả về null nếu chủ động lọc item
   |       \------> filterCount: số item bị lọc
   v
 ItemWriter   ------> writeCount: số item chuyển tới writer thành công
     |
     v
 Database / API / File
   |-- unique constraint
   |-- INSERT ... ON CONFLICT / idempotent operation
   \-- dữ liệu nghiệp vụ cuối cùng
```

Một chunk thường được ghi trong một transaction. Nếu file có 7 dòng và `chunk(3)`, các nhóm có thể là `[1,2,3]`, `[4,5,6]`, `[7]`. Trùng giữa dòng 1 và dòng 7 chỉ xuất hiện khi đã sang chunk khác. Một cấu trúc chỉ nhìn các item trong chunk hiện tại sẽ không nhận ra duplicate xuyên chunk.

Điểm đặc biệt quan trọng: **`writeCount` không nhất thiết bằng số bản ghi mới được thêm vào database**. Nếu `ItemWriter` nhận 5 item rồi thực hiện `INSERT ... ON CONFLICT DO NOTHING` để bỏ qua 2 duplicate, Spring Batch vẫn có thể ghi nhận 5 item được chuyển qua writer, trong khi bảng chỉ tăng 3 dòng. Cần assert cả metadata batch **và trạng thái output**.

## 4. Thiết kế bộ dữ liệu duplicate có kỳ vọng rõ ràng

Giả sử job `importPaymentEventsJob` đọc file CSV, mỗi sự kiện có ba trường:

| Trường | Ý nghĩa |
| --- | --- |
| `event_id` | Khóa định danh duy nhất của sự kiện do nguồn cấp |
| `customer_id` | Khách hàng liên quan; được phép lặp ở nhiều sự kiện khác nhau |
| `amount` | Số tiền của sự kiện |

Quy tắc ví dụ:

- Chuẩn hóa `event_id` bằng cách loại khoảng trắng đầu/cuối và chuyển thành chữ hoa theo `Locale.ROOT`.
- Cùng `event_id` và cùng nội dung: xử lý một lần; những lần còn lại là duplicate chính xác.
- Cùng `event_id` nhưng khác `customer_id` hoặc `amount`: xem là **xung đột dữ liệu**, cần báo lỗi hoặc chuyển vào luồng xử lý ngoại lệ theo contract nghiệp vụ.
- Cùng khách hàng nhưng khác `event_id`: là các sự kiện khác nhau và phải được giữ lại.

Fixture cơ bản tại `src/test/resources/batch/payment-events-duplicate.csv`:

```csv
event_id,customer_id,amount
PAY-001,C01,100.00
PAY-002,C02,250.00
PAY-001,C01,100.00
PAY-003,C01,75.00
PAY-002,C02,250.00
```

Với chunk size = 2, các vị trí `PAY-001` thứ nhất và thứ hai nằm ở hai chunk khác nhau. Bộ dữ liệu này giúp bắt lỗi deduplicate chỉ diễn ra trong một chunk.

Kết quả nghiệp vụ mong đợi sau một lần nạp:

| Chỉ số | Kỳ vọng | Giải thích |
| --- | ---: | --- |
| Dòng dữ liệu được reader đọc | 5 | Không tính hàng tiêu đề CSV |
| Khóa `event_id` duy nhất | 3 | `PAY-001`, `PAY-002`, `PAY-003` |
| Duplicate chính xác | 2 | Một bản sao `PAY-001` và một bản sao `PAY-002` |
| Bản ghi mới trong bảng output | 3 | Với chính sách chỉ ghi mỗi event một lần |
| Tổng tiền của các event duy nhất | 425.00 | 100 + 250 + 75 |

Để kiểm thử riêng việc **chuẩn hóa khóa**, tạo một fixture khác gồm `PAY-001`, `pay-001` và ` PAY-001 `. Đừng mặc định normalize `customerId`, ngày tháng hoặc số tiền theo cùng một quy tắc: mỗi trường có contract độc lập.

### Bộ dữ liệu xung đột

```csv
event_id,customer_id,amount
PAY-010,C01,100.00
PAY-010,C01,900.00
```

Trong ví dụ này, cả hai dòng không thể cùng được coi là một giao dịch hợp lệ. Nếu hệ thống chỉ dùng `ON CONFLICT DO NOTHING` thì dòng thứ hai sẽ bị bỏ qua mà không ai biết có sai lệch `amount`. Test cần thể hiện rõ **mong đợi**: thất bại có kiểm soát, gửi dead-letter/quarantine, hay báo cáo conflict để người vận hành đối soát.

### Ma trận test data nên có

| Mã | Đầu vào | Câu hỏi kiểm thử |
| --- | --- | --- |
| D01 | Toàn bộ ID khác nhau | Dữ liệu hợp lệ không bị lọc nhầm |
| D02 | Hai dòng giống hệt nhau, liền kề | Duplicate trong cùng chunk có bị ghi hai lần? |
| D03 | Hai dòng giống hệt nhau, cách xa | Duplicate xuyên chunk có bị ghi hai lần? |
| D04 | Chỉ khác hoa/thường/khoảng trắng | Chính sách chuẩn hóa có nhất quán? |
| D05 | Cùng event ID nhưng amount khác | Conflict có được phát hiện thay vì bỏ qua? |
| D06 | Cùng customer ID nhưng event ID khác | Có giữ đủ các sự kiện hợp lệ? |
| D07 | Chạy cùng file lần thứ hai với job parameters mới | Output có tăng sai lần nữa? |
| D08 | Fail giữa file rồi restart | Có nhân đôi hiệu ứng trước checkpoint? |
| D09 | Hai luồng cùng xử lý một event ID | Có race condition khi kiểm tra rồi insert? |
| D10 | Event ID null/trống/không hợp lệ | Validation và cơ chế skip/fail có đúng contract? |

Thiết kế dữ liệu **có thể chứng minh được kết quả bằng số liệu** (đếm bản ghi, tổng tiền, danh sách ID, bảng quarantine) giúp bài test chặt chẽ hơn việc chỉ assert `BatchStatus.COMPLETED`.

## 5. Ba chiến lược xử lý duplicate thường gặp

### 5.1. Lọc trong ItemProcessor

`ItemProcessor` có thể trả về `null` để **filter** một item; đây không phải là lỗi `skip`. Ví dụ chỉ dùng cho một step tuần tự, toàn bộ dữ liệu xử lý một lần:

```java
@Bean
@StepScope
ItemProcessor<PaymentEvent, PaymentEvent> filterDuplicatesWithinStep() {
    Set<String> seen = new HashSet<>();

    return item -> {
        String key = item.eventId().strip().toUpperCase(Locale.ROOT);
        return seen.add(key) ? item : null;
    };
}
```

Đối với fixture 5 dòng, processor ở trên trả `null` cho 2 duplicate. Nếu writer nhận các item còn lại, metadata thường phản ánh `readCount=5`, `filterCount=2` và `writeCount=3`.

Giới hạn của cách này:

- `HashSet` chỉ sống trong phạm vi step, không ghi nhận những ID được xử lý ở các lần chạy khác.
- Trạng thái `seen` **không tự rollback** khi một chunk bị rollback. Với retry, restart hoặc checkpoint, kết quả có thể không đúng nếu không thiết kế state/transaction cẩn thận.
- `HashSet` không phù hợp để chia sẻ giữa nhiều thread hoặc partition; đồng bộ collection cũng không giải quyết được tính nhất quán giữa nhiều tiến trình.
- Với hàng triệu ID, giữ toàn bộ khóa trong RAM dễ gây áp lực bộ nhớ.
- Nếu đã chuẩn hóa khóa nhưng vẫn ghi `item` gốc, output và quy tắc so khớp có thể không nhất quán; nên chuẩn hóa dữ liệu trước khi lưu.

Vì vậy, processor lọc theo `Set` chủ yếu phù hợp với **unit test, dữ liệu nhỏ, xử lý tuần tự hoặc bước tiền xử lý tạm thời** khi không cần bảo đảm idempotency giữa các execution.

### 5.2. Unique constraint và ghi có tính idempotent

Với dữ liệu nghiệp vụ quan trọng và cần chống trùng xuyên chunk, xuyên job run hoặc giữa nhiều worker, cách phổ biến là để database áp dụng **ràng buộc duy nhất** trên khóa thực sự đại diện cho event.

Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_payment_event (
    event_id     VARCHAR(80) PRIMARY KEY,
    customer_id  VARCHAR(80) NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL
);
```

Nếu ID chỉ duy nhất trong phạm vi một nguồn, dùng unique key dạng `(source_system, event_id)`, thay vì giả định `event_id` là duy nhất toàn hệ thống.

Để cho phép xử lý lại một event **mà không chèn thêm bản sao**, writer có thể dùng câu lệnh riêng của PostgreSQL:

```sql
INSERT INTO processed_payment_event(event_id, customer_id, amount)
VALUES (:eventId, :customerId, :amount)
ON CONFLICT (event_id) DO NOTHING;
```

Khi hai transaction cùng cố ghi một `event_id`, unique constraint là lớp bảo vệ cuối cùng. Tránh cách triển khai `SELECT COUNT(*)` rồi `INSERT` theo hai thao tác tách rời: giữa bước kiểm tra và chèn, transaction khác có thể chèn đúng ID đó.

**Lưu ý về business conflict:** `DO NOTHING` chỉ làm cho thao tác insert idempotent theo khóa. Nó **không phát hiện** rằng một bản ghi đến sau có cùng key nhưng `amount` khác. Nếu contract yêu cầu phát hiện trường hợp này, cần thêm logic so sánh payload/hàm băm, khóa hoặc transaction phù hợp, cùng nơi lưu lại bản ghi xung đột. Không cập nhật giá trị chỉ vì dữ liệu đến sau nếu quy tắc nghiệp vụ không cho phép.

Trong môi trường H2, MySQL hoặc Oracle, cú pháp tương đương khác nhau (ví dụ `MERGE` hoặc đặc trưng upsert của database). Test integration nên chạy trên đúng hệ quản trị database được dùng trong production, đặc biệt khi cần kiểm chứng concurrency và transaction semantics.

### 5.3. Staging và xử lý riêng duplicate

Khi phải lưu **mọi dòng gốc** để đối soát và tra cứu nguyên nhân, mô hình staging phù hợp:

```text
Raw CSV/API
    |
    v
staging_event  (lưu source file, row number, raw payload)
    |
    +-- key mới + hợp lệ ------------> processed_event
    |
    +-- trùng hoàn toàn -------------> duplicate_audit
    |
    +-- cùng key, payload khác ------> conflict_quarantine
    |
    +-- sai định dạng ---------------> validation_error
```

Với mô hình này, test phải kiểm tra cả ba đầu ra: bảng đã xử lý, nhật ký duplicate và danh sách conflict. Đặc biệt nên giữ `sourceFile`, `lineNumber`, `eventId` và lý do từ chối để người vận hành truy lại dòng nguồn.

## 6. Ví dụ cấu hình batch để test duplicate bằng PostgreSQL

Ví dụ dưới đây nhắm tới **Spring Batch 5.x / Spring Boot 3.x, Java 17 trở lên**. Lớp `PaymentEvent` là model đầu vào:

```java
import java.math.BigDecimal;

public record PaymentEvent(
        String eventId,
        String customerId,
        BigDecimal amount
) {}
```

### Reader: đọc đúng 5 dòng từ CSV

```java
@Bean
@StepScope
FlatFileItemReader<PaymentEvent> paymentEventReader() {
    return new FlatFileItemReaderBuilder<PaymentEvent>()
            .name("paymentEventReader")
            .resource(new ClassPathResource(
                    "batch/payment-events-duplicate.csv"))
            .linesToSkip(1)
            .delimited()
            .names("event_id", "customer_id", "amount")
            .fieldSetMapper(fields -> new PaymentEvent(
                    fields.readString("event_id"),
                    fields.readString("customer_id"),
                    fields.readBigDecimal("amount")
            ))
            .build();
}
```

Đường dẫn CSV tương ứng `src/test/resources/batch/payment-events-duplicate.csv`. Đặt file trong `src/test/resources` nếu job này chỉ dùng cho bài integration test; trong ứng dụng thực tế, resource có thể được truyền qua `jobParameters`.

### Processor: chuẩn hóa khóa và validate

```java
@Bean
ItemProcessor<PaymentEvent, PaymentEvent> normalizePaymentEvent() {
    return row -> {
        String eventId = row.eventId() == null
                ? ""
                : row.eventId().strip().toUpperCase(Locale.ROOT);

        if (eventId.isBlank()) {
            throw new IllegalArgumentException("event_id is required");
        }

        return new PaymentEvent(
                eventId,
                row.customerId().strip(),
                row.amount()
        );
    };
}
```

Trong ví dụ này, processor **không lọc duplicate**. Nó trả về đủ 5 item, để database chịu trách nhiệm bảo vệ khóa duy nhất. Nếu dữ liệu bắt buộc có `customer_id`/`amount`, cần validate chúng thêm theo contract đầu vào. Cách xử lý exception (`fail`, `skip` hoặc quarantine) cũng phải được cấu hình rõ ở step nếu muốn job tiếp tục khi gặp bản ghi sai.

### Writer: insert idempotent

```java
@Bean
ItemWriter<PaymentEvent> paymentEventWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (PaymentEvent row : chunk) {
            jdbcTemplate.update("""
                    INSERT INTO processed_payment_event
                        (event_id, customer_id, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    row.eventId(),
                    row.customerId(),
                    row.amount()
            );
        }
    };
}
```

`ItemWriter.write(Chunk<? extends PaymentEvent>)` nhận một chunk. Trong mỗi chunk, writer thử insert tất cả item. Dòng mới được chèn; dòng có `event_id` đã tồn tại bị PostgreSQL bỏ qua mà không tạo bản sao. Để giữ nguyên transaction semantics của chunk, `JdbcTemplate` và `JobRepository` cần cấu hình transaction manager/DataSource phù hợp; với kết quả ngoài database như HTTP hoặc message broker cần thiết kế idempotency riêng.

### Step và Job

```java
@Bean
Step importPaymentEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<PaymentEvent> paymentEventReader,
        ItemProcessor<PaymentEvent, PaymentEvent> normalizePaymentEvent,
        ItemWriter<PaymentEvent> paymentEventWriter) {

    return new StepBuilder("importPaymentEventsStep", jobRepository)
            .<PaymentEvent, PaymentEvent>chunk(2, transactionManager)
            .reader(paymentEventReader)
            .processor(normalizePaymentEvent)
            .writer(paymentEventWriter)
            .build();
}

@Bean
Job importPaymentEventsJob(
        JobRepository jobRepository,
        Step importPaymentEventsStep) {

    return new JobBuilder("importPaymentEventsJob", jobRepository)
            .start(importPaymentEventsStep)
            .build();
}
```

Đặt các bean trên trong lớp `@Configuration` thuộc Spring context của test, đồng thời bảo đảm có `DataSource`, `JdbcTemplate`, `JobRepository` và transaction manager hợp lệ. Các import chính:

```java
import java.util.Locale;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
```

**Giới hạn phiên bản:** Ví dụ trên sử dụng các package/model của Spring Batch 5.x. Spring Batch 6 thay đổi một số package và API; cần điều chỉnh import và tiện ích khởi chạy theo phiên bản thực tế của dự án. Câu lệnh `ON CONFLICT` là cú pháp PostgreSQL và phải chạy trên PostgreSQL khi dùng nguyên bản.

## 7. Integration test: xác minh kết quả khi file có duplicate

Test dùng `spring-batch-test`, JUnit Jupiter và Spring Boot Test. Cần cấu hình **database PostgreSQL dành riêng cho test** (ví dụ Testcontainers) đã tạo bảng `processed_payment_event` và các bảng metadata Spring Batch. Tắt auto-run job khi context khởi động để test điều khiển được lần chạy:

```properties
spring.batch.job.enabled=false
```

Ở môi trường test, có thể để Boot khởi tạo schema metadata bằng `spring.batch.jdbc.initialize-schema=always`, hoặc dùng migration đang có. Bảng nghiệp vụ cần có DDL riêng. **Không cho test này trỏ vào database dùng chung** vì sẽ có thao tác xóa dữ liệu fixture.

Test Spring Batch 5.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class DuplicatePaymentEventIT {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importPaymentEventsJob")
    private Job importPaymentEventsJob;

    @BeforeEach
    void resetFixture() {
        launcher.setJob(importPaymentEventsJob);
        repositoryTestUtils.removeJobExecutions();
        jdbcTemplate.update("DELETE FROM processed_payment_event");
    }

    @Test
    void ghiDungBaEventKhiFileCoHaiBanSao() throws Exception {
        var parameters = new JobParametersBuilder()
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = launcher.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(5, step.getReadCount());
        assertEquals(5, step.getWriteCount());

        Integer rows = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM processed_payment_event",
                Integer.class
        );
        assertEquals(3, rows);

        BigDecimal total = jdbcTemplate.queryForObject(
                "SELECT SUM(amount) FROM processed_payment_event",
                BigDecimal.class
        );
        assertEquals(0, new BigDecimal("425.00").compareTo(total));
    }
}
```

### Ý nghĩa của các phép assert

- `BatchStatus.COMPLETED`: bước xử lý kết thúc theo trạng thái thành công, nhưng riêng trạng thái này **không chứng minh** chống trùng đúng.
- `readCount=5`: reader nhận đủ năm item từ fixture.
- `writeCount=5`: cả năm item đã được chuyển cho writer (vì processor không lọc). Đây không phải số dòng SQL chèn thành công.
- `COUNT(*)=3`: unique constraint kết hợp lệnh insert idempotent đã giữ ba khóa duy nhất.
- `SUM(amount)=425.00`: duplicate không làm cộng tiền hai lần.

Nếu lựa chọn chính sách lọc duplicate tại processor, kỳ vọng metadata thay đổi, ví dụ `filterCount=2` và `writeCount=3` trong trường hợp không có rollback/retry. Test phải assert dựa trên **thiết kế thật**, không áp đặt một bộ đếm chung cho mọi chiến lược.

### Kiểm thử chạy lại cùng file

Với database test đã có ba dòng sau lần chạy đầu tiên, khởi chạy job lần thứ hai bằng **bộ identifying parameters khác**. Hai lần chạy đều đọc năm dòng, nhưng dữ liệu nghiệp vụ phải vẫn có ba event.

Có thể thêm method sau vào lớp test trên:

```java
@Test
void chayLaiFileKhongLamTangSoEvent() throws Exception {
    JobExecution first = launcher.launchJob(
            new JobParametersBuilder()
                    .addString("run.id", "first-" + UUID.randomUUID())
                    .toJobParameters()
    );

    JobExecution second = launcher.launchJob(
            new JobParametersBuilder()
                    .addString("run.id", "second-" + UUID.randomUUID())
                    .toJobParameters()
    );

    assertEquals(BatchStatus.COMPLETED, first.getStatus());
    assertEquals(BatchStatus.COMPLETED, second.getStatus());

    Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM processed_payment_event",
            Integer.class
    );
    assertEquals(3, count);
}
```

Trong test này, `@BeforeEach` chỉ chạy **một lần trước method**, nên dữ liệu của lần launch thứ nhất được giữ cho lần thứ hai kiểm tra khả năng idempotency. Nếu bạn xóa bảng nghiệp vụ giữa hai lần launch thì bài test đã đánh mất mục tiêu.

## 8. Kiểm thử duplicate khi retry, rollback và restart

Kiểm thử với dữ liệu trùng thường phát hiện những lỗi mà bài test happy path không thấy:

### 8.1. Retry và rollback tại ranh giới chunk

Một kịch bản:

1. Reader đọc các event `PAY-001`, `PAY-002` trong chunk.
2. Writer ghi vào database nhưng một lỗi kỹ thuật khiến transaction của chunk rollback.
3. Spring Batch retry bước xử lý theo cấu hình.
4. Các item được đọc/xử lý/ghi lại; kết quả cuối cùng vẫn phải là một bản ghi cho mỗi event.

Khi output dùng cùng transactional database với chunk và insert idempotent, rollback sẽ hoàn tác các insert của transaction chưa commit. Tuy nhiên, nếu writer đồng thời gọi HTTP API hoặc gửi message, các side effect đó **có thể đã xảy ra dù transaction JDBC rollback**. Cần idempotency key ở phía nhận hoặc outbox/transactional messaging phù hợp; chỉ nhìn `JobRepository` là chưa đủ.

### 8.2. Restart sau khi một số chunk đã commit

Một kịch bản khác:

1. Job commit thành công chunk đầu, lưu tiến độ vào `ExecutionContext`.
2. Chunk tiếp theo gặp lỗi, job dừng ở trạng thái `FAILED`.
3. Test khởi động lại **cùng `JobInstance` theo cơ chế restart thực sự**.
4. Những event đã xử lý không được tạo bản sao; phần còn lại được hoàn thành.

Cần test cả hai vấn đề: reader có resume đúng vị trí hay không, và writer có bảo đảm tính idempotent nếu một item bị phát lại hay không. Chỉ đổi `run.id` rồi launch lại là **tạo instance mới**, chưa kiểm thử restart/checkpoint. Việc xóa metadata `BATCH_*` trước khi restart cũng phá hỏng kịch bản cần đo.

Với reader có trạng thái, phải cấu hình tên reader và `saveState` phù hợp để Spring Batch lưu `ExecutionContext`. Nếu dùng processor giữ `HashSet` trong bộ nhớ, trạng thái `seen` không được phục hồi sau process restart, nên database uniqueness vẫn cần thiết.

### 8.3. Chạy nhiều thread hoặc partition

Hai thread có thể cùng thấy `PAY-001` là “chưa tồn tại”. Nếu code làm `SELECT` rồi `INSERT` mà không có cơ chế atomic, cả hai có thể cố insert. Test song song nên xác minh rằng:

- Database cuối cùng chỉ có một event `PAY-001`.
- Không có lỗi không mong đợi do unique constraint gây dừng job (hoặc lỗi được xử lý đúng contract).
- Số lần gọi API ngoại vi, số message phát hành và tổng tiền không bị nhân đôi.

Với concurrent test, các cơ chế bảo vệ phải tồn tại ở **nơi chia sẻ trạng thái thực sự** (database/consumer idempotency store), thay vì dựa vào một `Set` chỉ tồn tại trong một process.

## 9. Phân biệt filter, skip, lỗi và duplicate

Spring Batch cung cấp các cơ chế kỹ thuật khác nhau:

| Cơ chế | Dùng khi nào | Quan sát trong test |
| --- | --- | --- |
| `ItemProcessor` trả `null` | Có chủ đích loại bỏ item khỏi output | `filterCount` tăng |
| `skip` một exception được cấu hình | Item lỗi nhưng policy cho phép bỏ qua, trong giới hạn skip | Các bộ đếm `readSkipCount`, `processSkipCount`, `writeSkipCount` tùy nơi phát sinh lỗi |
| `retry` exception tạm thời | Lỗi có thể khắc phục bằng xử lý lại | Kiểm tra số lần thử, rollback và output cuối cùng |
| Unique constraint + `DO NOTHING` | Dòng duplicate hợp lệ được xử lý idempotent | Số dòng thực tế tăng 0; `writeCount` có thể vẫn tăng |
| Quarantine/conflict table | Cùng khóa nhưng payload sai lệch cần điều tra | Có bản ghi lỗi đầy đủ ID, payload, nguồn, lý do |
| Fail job | Duplicate được coi là vi phạm nghiêm trọng | `BatchStatus.FAILED` và dữ liệu được rollback/giữ lại đúng policy |

Không nên cấu hình bỏ qua mọi `DuplicateKeyException` một cách vô điều kiện. Một số lỗi “duplicate key” là dấu hiệu **xung đột thật**, sai ràng buộc dữ liệu, race condition, hoặc bug trong bước mapping. Việc skip một exception ở writer còn có thể làm chunk rollback rồi được thử lại để cô lập item lỗi; test phải kiểm tra hành vi thực tế và trạng thái database sau transaction.

## 10. Test data và tính toán kết quả mong đợi

Khi tạo fixture, luôn ghi cùng ba thành phần: **input**, **policy**, **expected output**. Chỉ nhìn một file “có dòng trùng” không đủ để xác định kết quả đúng.

Ví dụ với năm dòng của fixture cơ bản:

```text
Input             Business key    Action mong đợi
----------------------------------------------------
PAY-001 C01 100   PAY-001         INSERT
PAY-002 C02 250   PAY-002         INSERT
PAY-001 C01 100   PAY-001         DUPLICATE -> IGNORE
PAY-003 C01  75   PAY-003         INSERT
PAY-002 C02 250   PAY-002         DUPLICATE -> IGNORE
----------------------------------------------------
Đọc: 5             Key duy nhất: 3      Mới chèn: 3
Tổng tiền nghiệp vụ: 425.00
```

Khi tự sinh test data số lượng lớn, nên tạo nhiều lớp bản ghi có thể tái lập:

- `N` bản ghi có business key duy nhất.
- `D` bản sao nguyên vẹn được chèn vào các vị trí đầu, giữa và cuối file.
- `C` bản ghi cùng key nhưng payload khác, để kiểm thử conflict.
- `V` biến thể format key (hoa/thường, whitespace, Unicode nếu contract cho phép).

Kỳ vọng số khóa duy nhất là `N` **nếu** `D` chỉ sao chép key của `N` và `C` không mang key mới. Nhưng số bản ghi hợp lệ, số duplicate và số conflict cần được tính riêng theo business policy. Dùng random seed cố định khi phát sinh fixture để lỗi có thể tái hiện; nếu cần kiểm thử phân phối tải, ghi lại seed của mỗi lần chạy.

### Tách fixture khỏi trạng thái cũ

Một test đáng tin cậy phải biết trạng thái đầu:

```text
Database ban đầu: 0 events
Fixture: 5 dòng, 3 event_id duy nhất
Kết quả sau lần chạy 1: 3 events
Kết quả sau lần chạy 2: vẫn 3 events
```

Nếu database ban đầu đã có `PAY-002`, lần chạy đầu chỉ thêm hai dòng; đây có thể là bài test “duplicate với dữ liệu hiện có”, nhưng **không** nên vô tình xảy ra khi bạn đang test “duplicate trong một file”.

Các nguồn gây phụ thuộc giữa test gồm database tái sử dụng, file output chưa xóa, cache dedup chưa reset, bean `@Singleton` giữ tập `seen`, hoặc `JobParameters` tái sử dụng. Nên dùng database/schema test độc lập và fixture có ownership rõ ràng.

## 11. Những sai lầm thường gặp

### Chỉ đếm số record reader đã đọc

Reader đọc đúng năm dòng không chứng minh kết quả ghi đúng. Job có thể đã tạo năm bản ghi nghiệp vụ, làm nhân đôi số tiền. Hãy assert `COUNT(DISTINCT business_key)`, `COUNT(*)`, giá trị aggregate hoặc trạng thái API thực sự.

### Chỉ dùng DISTINCT trên toàn bộ dòng

`SELECT DISTINCT *` chỉ loại bỏ dòng giống hệt nhau. Hai dòng cùng `eventId` nhưng khác timestamp, amount hoặc mô tả sẽ vẫn được giữ lại. Nếu `eventId` là khóa, cần dùng đúng khóa và đặt policy cho payload xung đột.

### Dùng chung Set cho mọi job run

Nếu `Set` nằm trong singleton processor, việc chạy job lần hai có thể bị lọc sai vì set vẫn giữ ID từ lần thứ nhất. Nếu dùng `@StepScope`, set mới cho mỗi step execution nhưng lại không chống trùng được xuyên run/restart. Cần hiểu lifecycle của bean.

### Tin rằng chunk boundary là ranh giới của duplicate

Duplicate không bị giới hạn trong một chunk. Dữ liệu trùng ở cuối file, ở file khác hoặc từ nguồn song song đều phải tuân cùng một chính sách.

### Dùng “upsert” mà không định nghĩa xung đột

`ON CONFLICT DO NOTHING` có thể thích hợp cho event bất biến, nhưng nguy hiểm nếu payload cùng khóa có giá trị khác nhau cần báo động. `ON CONFLICT DO UPDATE` cũng không tự động đúng: có hệ thống phải giữ bản đầu tiên, có hệ thống phải giữ bản có version mới nhất, và có hệ thống phải từ chối mọi cập nhật.

### Xóa Batch metadata rồi xem là đã dọn sạch test

`JobRepository` quản lý metadata thực thi; bảng nghiệp vụ, file output và side effects bên ngoài phải được cleanup riêng. Nếu mục tiêu là restart, thậm chí không được xóa metadata trước khi restart.

### Giả định API ngoài có transaction cùng với database

HTTP request có thể được phía nhận thực hiện thành công rồi mạng timeout; retry sẽ gửi lại. Với tác vụ thanh toán, gửi email hay publish message, cần kiểm thử idempotency tại biên hệ thống. Transaction JDBC của chunk không thể tự rollback HTTP side effect.

## 12. Bài thực hành: mở rộng từ happy path đến restart

Với job `importPaymentEventsJob`, triển khai lần lượt các bài tập sau:

1. **Baseline:** tạo file ba event ID khác nhau, assert bảng output có ba dòng và tổng tiền đúng.
2. **Duplicate trong một run:** dùng fixture năm dòng ở trên; assert vẫn chỉ có ba dòng và tổng tiền `425.00`.
3. **Cross-chunk:** giữ `chunk(2)`, đặt bản sao của `PAY-001` ở cuối file; xác minh không phát sinh bản ghi thêm.
4. **Normalization:** thêm biến thể `pay-001` và ` PAY-001 `; kiểm tra chúng cùng khóa sau chuẩn hóa nếu contract cho phép.
5. **Conflict:** thêm `PAY-001,C01,900.00` và triển khai policy báo conflict; assert có thông tin lỗi để đối soát, không mất dữ liệu âm thầm.
6. **Rerun:** launch job lần nữa với job parameters mới mà không reset bảng output; assert số event và tổng tiền không đổi.
7. **Restart:** gây lỗi có kiểm soát ở chunk sau khi một chunk trước đã commit; restart đúng `JobInstance` và xác minh không ghi trùng.
8. **Concurrency:** dùng hai worker hoặc hai job execution có cùng event; xác minh unique constraint và chính sách conflict vẫn đúng.

Trong mỗi bài, ghi nhận cả metadata batch (`BatchStatus`, `readCount`, `filterCount`, `writeCount`, skip counts) và trạng thái dữ liệu thực tế. Bài thực hành có thể coi là hoàn thành khi cùng fixture chạy lặp lại vẫn cho cùng **kết quả nghiệp vụ**, ngay cả khi số lần reader/writer được gọi thay đổi do retry.

## 13. Kết luận

Dữ liệu duplicate là test case cốt lõi để xác nhận tính **đúng một lần theo nghiệp vụ** của một batch job. Spring Batch hỗ trợ các cơ chế chunk, retry, restart và metadata, nhưng không tự định nghĩa một event nào là duplicate và cũng không bảo đảm mọi side effect ngoài transaction chỉ diễn ra một lần. Muốn kiểm thử chắc chắn, hãy định nghĩa đúng business key, chuẩn hóa dữ liệu có quy tắc, tạo fixture gồm duplicate trong cùng chunk/xuyên chunk/xuyên run, rồi so sánh **output cuối cùng** với expected result. Với job cần chạy lặp lại hoặc chạy song song, unique constraint và thiết kế ghi idempotent thường là lớp bảo vệ quan trọng bên cạnh kiểm thử ở processor.

### Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — ItemProcessor](https://docs.spring.io/spring-batch/reference/processor.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [PostgreSQL — INSERT và ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
