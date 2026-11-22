# Kiểm thử input/output resource trong Spring Batch

## 1. Mục tiêu và phạm vi

Trong Spring Batch, dữ liệu thường đi từ một **resource đầu vào** (CSV, TXT, JSON, XML, tệp từ hệ thống khác...) qua `ItemReader`, `ItemProcessor` rồi đến một **resource đầu ra**. Một job kết thúc với trạng thái `COMPLETED` chưa đủ chứng minh nội dung tệp đúng: có thể đọc thiếu dòng, bỏ qua dữ liệu sai ngoài dự kiến, ghi sai encoding, tạo header trùng hoặc ghi đè nhầm tệp.

Bài học này tập trung vào **kiểm thử tài nguyên đầu vào/đầu ra** trong chủ đề *Spring Batch Core Processing*, thuộc phần *Testing batch*. Sau khi học, bạn có thể:

- Chọn cách tạo input fixture và nơi lưu output phù hợp cho từng cấp độ test.
- Kiểm thử `FlatFileItemReader`: parse dữ liệu, bỏ qua header, kết thúc tệp, báo lỗi khi thiếu/hỏng resource.
- Kiểm thử `FlatFileItemWriter`: định dạng từng dòng, thứ tự bản ghi, header, encoding, khả năng tạo/ghi lại tệp.
- Chạy một `Step` hoặc `Job` thật để xác nhận cả **dữ liệu đầu ra** lẫn **thống kê thực thi**.
- Thiết kế tình huống kiểm thử cho `@StepScope`, lỗi I/O, nhiều resource và restart.

Phạm vi ví dụ: **Java 17+, JUnit Jupiter, Spring Boot 3.x và Spring Batch 5.2.x**. Một mục riêng ở cuối nêu các khác biệt quan trọng khi sử dụng Spring Batch 6.x. Không trộn import của hai dòng phiên bản trong cùng một project.

## 2. Resource là gì và vì sao cần kiểm thử riêng?

Spring dùng abstraction `org.springframework.core.io.Resource` để biểu diễn nơi lấy dữ liệu. `FlatFileItemReader` cần một `Resource` có thể đọc; `FlatFileItemWriter` cần `WritableResource` có thể ghi.

```text
                   Input resource                    Output resource
                    (orders.csv)                     (report.csv)
                          │                                ▲
                          ▼                                │
                   FlatFileItemReader               FlatFileItemWriter
                          │                                ▲
                          ▼                                │
                      ItemProcessor ────────────────────────┘
                              │
                      Step / Job metadata
                   (readCount, writeCount,
                    skipCount, BatchStatus...)
```

Có hai lớp hợp đồng cần xác nhận:

1. **Hợp đồng nội dung:** tệp đọc có đúng số dòng/cột, kiểu dữ liệu, thứ tự và giá trị? Tệp ghi có đúng cấu trúc, encoding, số dòng và nội dung mong đợi?
2. **Hợp đồng vận hành:** tệp thiếu thì job thất bại hay được bỏ qua? Input được đóng sau khi dùng chưa? Ghi lại cùng một đường dẫn sẽ xóa, append hay khôi phục theo `ExecutionContext`? Metadata ghi nhận đúng số bản ghi không?

### Chọn loại resource cho test

| Resource | Cách dùng trong test | Lưu ý |
|---|---|---|
| `ClassPathResource` | Đọc fixture cố định ở `src/test/resources` | Tốt cho input chỉ đọc; không ghi output vào classpath. |
| `ByteArrayResource` | Tạo input nhỏ trực tiếp từ chuỗi/byte trong bộ nhớ | Không tạo file thật; thích hợp unit test reader cần dữ liệu có thể mở lại. |
| `FileSystemResource` | Trỏ vào file trong thư mục tạm của test | Cần cho writer và các bài test xác nhận file được tạo trên đĩa. |
| `InputStreamResource` | Bọc một `InputStream` sẵn có | Nhiều stream chỉ đọc một lần; hạn chế dùng cho test reopen/restart. |
| `UrlResource` hoặc resource từ dịch vụ ngoài | Integration test có kiểm soát hoặc test bằng adapter giả lập | Tính sẵn sàng, quyền truy cập và độ ổn định phụ thuộc môi trường ngoài. |

Ví dụ tạo fixture nhỏ trong bộ nhớ:

```java
byte[] csv = "id,amount\n101,10.00\n102,20.50\n"
        .getBytes(StandardCharsets.UTF_8);
Resource resource = new ByteArrayResource(csv);
// Gắn resource này vào FlatFileItemReader qua builder.resource(resource).
```

Ví dụ tạo file thật, cô lập giữa các lần test:

```java
@TempDir
Path tempDir;

@Test
void resourceExample() throws IOException {
    Path input = tempDir.resolve("input.csv");
    Path output = tempDir.resolve("output.csv");

    Files.writeString(input, "id,amount\n101,10.00\n",
            StandardCharsets.UTF_8);

    Resource inputResource = new FileSystemResource(input);
    WritableResource outputResource = new FileSystemResource(output);
}
```

`@TempDir` do JUnit Jupiter cấp phát, giúp tránh ghi chung vào `./data/output.csv` hoặc phụ thuộc vào file còn sót từ lượt chạy trước. Đối với môi trường Windows, việc đóng stream đúng cách cũng ngăn lỗi khóa file khi thư mục tạm được dọn dẹp.

## 3. Chọn mức kiểm thử phù hợp

| Mức kiểm thử | Chạy những gì? | Cần khẳng định điều gì? | Khi nào dùng? |
|---|---|---|---|
| Unit test cho reader | `open → read → close` của reader | Mapping, header, EOF, lỗi format, file thiếu | Khi xử lý input phức tạp hoặc cần phản hồi nhanh |
| Unit test cho writer | `open → write → close` của writer | Header, từng dòng, thứ tự, encoding, quy tắc ghi đè | Khi cấu trúc output là hợp đồng nghiệp vụ |
| Step integration test | Step thật với input/output tạm | Số lượng đọc/ghi/lọc/bỏ qua và output | Khi cần kiểm tra chunk, processor, reader, writer phối hợp |
| Job integration test | Toàn bộ job với `JobParameters` | Trạng thái cuối, kết quả file, luồng nhiều step | Khi xác minh hành vi từ đầu đến cuối |
| Restart/error test | Lỗi có chủ đích rồi chạy lại | Vị trí tiếp tục, thiếu/trùng bản ghi, cách xử lý file | Khi job phải chạy lại an toàn sau sự cố |

Một chiến lược hiệu quả là viết **vài unit test có chủ đích** cho hai đầu I/O và **ít nhất một integration test** chạy qua pipeline thật. Assertion chỉ so sánh `BatchStatus.COMPLETED` sẽ bỏ sót nhiều lỗi nội dung.

## 4. Bài toán xuyên suốt: đọc CSV và tạo CSV

Giả sử hệ thống nhận danh sách thanh toán. Mỗi thanh toán có `id` và `amount`; xử lý cộng thêm phí cố định `1.00` rồi ghi `id,total`.

**Input — `payments.csv`**

```csv
id,amount
101,10.00
102,20.50
103,0.00
```

**Output mong đợi — `invoices.csv`**

```csv
id,total
101,11.00
102,21.50
103,1.00
```

Quy ước cho ví dụ:

- Input có header một dòng; output cũng luôn có header.
- Mỗi bản ghi hợp lệ tạo đúng một bản ghi đầu ra theo thứ tự input.
- Dùng `BigDecimal` để tránh sai số kiểu dấu phẩy động khi tính số tiền.
- Thiếu input là lỗi; test cần nhận diện lỗi sớm.
- Encoding là UTF-8; mỗi lượt test có thư mục input/output riêng.

### 4.1. Dependency cho kiểm thử

Với project dùng Spring Boot Gradle và dependency management của Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    runtimeOnly 'com.h2database:h2' // Metadata JobRepository trong demo cục bộ

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Spring Boot quản lý version tương thích. Một ứng dụng production có thể dùng PostgreSQL/MySQL thay H2; ví dụ chỉ cần một `DataSource` và các bảng metadata Spring Batch để chạy integration test.

### 4.2. Cấu hình batch mẫu

Đặt class sau trong package `com.example.batch`. Các import dưới đây dành cho **Spring Batch 5.2.x**.

```java
package com.example.batch;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class PaymentBatchConfig {

    public record Payment(long id, BigDecimal amount) {}
    public record Invoice(long id, BigDecimal total) {}

    @Bean
    @StepScope
    public FlatFileItemReader<Payment> paymentReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<Payment>()
                .name("paymentReader")
                .resource(new FileSystemResource(inputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .linesToSkip(1)
                .strict(true)
                .delimited()
                .delimiter(",")
                .names("id", "amount")
                .fieldSetMapper(fs -> new Payment(
                        fs.readLong("id"),
                        fs.readBigDecimal("amount")))
                .build();
    }

    @Bean
    @StepScope
    public FlatFileItemWriter<Invoice> invoiceWriter(
            @Value("#{jobParameters['outputFile']}") String outputFile) {

        return new FlatFileItemWriterBuilder<Invoice>()
                .name("invoiceWriter")
                .resource(new FileSystemResource(outputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .headerCallback(w -> w.write("id,total"))
                .lineAggregator(invoice ->
                        invoice.id() + "," + invoice.total().toPlainString())
                .shouldDeleteIfExists(true)
                .build();
    }

    @Bean
    public Step paymentStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Payment> paymentReader,
            FlatFileItemWriter<Invoice> invoiceWriter) {

        return new StepBuilder("paymentStep", jobRepository)
                .<Payment, Invoice>chunk(2, transactionManager)
                .reader(paymentReader)
                .processor(payment -> new Invoice(
                        payment.id(),
                        payment.amount().add(new BigDecimal("1.00"))))
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    public Job paymentJob(JobRepository jobRepository, Step paymentStep) {
        return new JobBuilder("paymentJob", jobRepository)
                .start(paymentStep)
                .build();
    }
}
```

Dùng application entry point thông thường trong cùng package:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoBatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoBatchApplication.class, args);
    }
}
```

Ở đây, `@StepScope` giúp reader và writer nhận đường dẫn từ `JobParameters` vào thời điểm step chạy. Reader và writer là `ItemStream`: khi Spring Batch chạy thật, framework phụ trách vòng đời `open`, `update` và `close`. Trong unit test gọi trực tiếp, người viết test phải điều khiển vòng đời này.

**Lưu ý:** `shouldDeleteIfExists(true)` phù hợp ví dụ tạo output mới. Với job cần restart hoặc append, phải kiểm thử chính sách file và `ExecutionContext` theo đúng yêu cầu nghiệp vụ; tuyệt đối không giả định ghi file và giao dịch cơ sở dữ liệu là một giao dịch nguyên tử.

## 5. Unit test cho input resource và FlatFileItemReader

Test đầu tiên xác nhận: bỏ qua header, map đúng `id/amount`, đọc theo thứ tự và `read()` trả `null` tại EOF.

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.ItemStreamException;

import com.example.batch.PaymentBatchConfig.Payment;

class PaymentInputResourceTest {

    @TempDir
    Path tempDir;

    private final PaymentBatchConfig config = new PaymentBatchConfig();

    @Test
    void readsHeaderAndAllRecordsInOrder() throws Exception {
        Path input = tempDir.resolve("payments.csv");
        Files.writeString(input,
                "id,amount\n101,10.00\n102,20.50\n103,0.00\n",
                StandardCharsets.UTF_8);

        FlatFileItemReader<Payment> reader =
                config.paymentReader(input.toString());
        reader.open(new ExecutionContext());
        try {
            assertEquals(new Payment(101L, new BigDecimal("10.00")),
                    reader.read());
            assertEquals(new Payment(102L, new BigDecimal("20.50")),
                    reader.read());
            assertEquals(new Payment(103L, new BigDecimal("0.00")),
                    reader.read());
            assertNull(reader.read()); // EOF
        } finally {
            reader.close();
        }
    }

    @Test
    void failsWhenInputResourceDoesNotExist() {
        Path missing = tempDir.resolve("missing.csv");

        FlatFileItemReader<Payment> reader =
                config.paymentReader(missing.toString());

        try {
            assertThrows(ItemStreamException.class,
                    () -> reader.open(new ExecutionContext()));
        } finally {
            reader.close();
        }
    }

    @Test
    void reportsMalformedCsvLine() throws Exception {
        Path input = tempDir.resolve("invalid.csv");
        Files.writeString(input,
                "id,amount\n101,10.00\n102,INVALID\n",
                StandardCharsets.UTF_8);

        FlatFileItemReader<Payment> reader =
                config.paymentReader(input.toString());
        reader.open(new ExecutionContext());
        try {
            assertNotNull(reader.read());

            FlatFileParseException error = assertThrows(
                    FlatFileParseException.class, () -> reader.read());
            assertEquals(3, error.getLineNumber());
            assertEquals("102,INVALID", error.getInput());
        } finally {
            reader.close();
        }
    }
}
```

Cách viết `config.paymentReader(path)` ở trên gọi **phương thức factory bằng Java thuần**, nên không cần khởi động Spring context chỉ để kiểm thử parse file. Trường hợp muốn kiểm thử biểu thức `@Value("#{jobParameters[...]}")` và proxy `@StepScope` thì dùng integration test ở phần sau.

### Những trường hợp cần bổ sung cho reader

| Trường hợp input | Assertion nên có |
|---|---|
| File chỉ có header | `read() == null` ngay từ lần đầu; step đọc 0 item. |
| File rỗng | Kết quả theo hợp đồng đã chọn: EOF hoặc lỗi xác thực dữ liệu ở tầng ứng dụng. |
| Dư/thiếu cột | Parser báo lỗi nếu tokenizer được cấu hình strict về số trường. |
| Số tiền âm, giá trị 0, số lớn | Mapping sang `BigDecimal` và quy tắc nghiệp vụ xử lý đúng. |
| Header sai tên/thứ tự | Nếu schema phải được kiểm chứng, bổ sung bước xác thực header (`linesToSkip(1)` chỉ bỏ qua dòng, **không xác nhận tên cột**). |
| Dấu phẩy trong dữ liệu có quote | Đảm bảo tokenizer và fixture phản ánh định dạng CSV thực tế. |
| Ký tự tiếng Việt, Unicode, BOM | Đọc đúng UTF-8; kiểm tra và xử lý BOM nếu nguồn có BOM. |
| File bị xóa hoặc không thể đọc | Nhận lỗi phù hợp, không báo thành công giả. |

Phân biệt hai cấu hình `strict` dễ nhầm:

- `FlatFileItemReaderBuilder.strict(true)`: yêu cầu input resource tồn tại, fail khi không mở được input.
- `DelimitedLineTokenizer.strict(true)`: yêu cầu số token của bản ghi khớp cấu trúc cột đã khai báo. Đây là một cấu hình khác; không tự động kiểm tra nội dung header.

Nếu bật `reader.strict(false)`, thiếu file có thể dẫn đến không có item nào được đọc. Chỉ chọn hành vi này khi thiếu input thật sự là tình huống hợp lệ của hệ thống.

## 6. Unit test cho output resource và FlatFileItemWriter

Reader có thể dùng resource chỉ đọc trong bộ nhớ; writer thường cần một `WritableResource` thực sự. Ta dùng `FileSystemResource` trỏ đến file bên trong `@TempDir`, gọi `write(Chunk)`, đóng writer rồi đọc lại output.

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemWriter;

import com.example.batch.PaymentBatchConfig.Invoice;

class PaymentOutputResourceTest {

    @TempDir
    Path tempDir;

    private final PaymentBatchConfig config = new PaymentBatchConfig();

    @Test
    void writesExpectedCsvHeaderAndRows() throws Exception {
        Path output = tempDir.resolve("invoices.csv");
        FlatFileItemWriter<Invoice> writer =
                config.invoiceWriter(output.toString());

        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                    new Invoice(101L, new BigDecimal("11.00")),
                    new Invoice(102L, new BigDecimal("21.50")),
                    new Invoice(103L, new BigDecimal("1.00")))));
        } finally {
            writer.close();
        }

        assertTrue(Files.exists(output));
        assertEquals(List.of(
                "id,total",
                "101,11.00",
                "102,21.50",
                "103,1.00"),
                Files.readAllLines(output, StandardCharsets.UTF_8));
    }

    @Test
    void replacesAnOldOutputFileOnFreshRun() throws Exception {
        Path output = tempDir.resolve("invoices.csv");
        Files.writeString(output, "OLD_DATA\n",
                StandardCharsets.UTF_8);

        FlatFileItemWriter<Invoice> writer =
                config.invoiceWriter(output.toString());
        writer.open(new ExecutionContext());
        try {
            writer.write(new Chunk<>(List.of(
                    new Invoice(201L, new BigDecimal("6.00")))));
        } finally {
            writer.close();
        }

        assertEquals(List.of("id,total", "201,6.00"),
                Files.readAllLines(output, StandardCharsets.UTF_8));
    }
}
```

Nên so sánh **từng dòng theo danh sách có thứ tự** nếu thứ tự là một phần hợp đồng. `Files.readAllLines` loại bỏ khác biệt ký tự kết thúc dòng `\n` / `\r\n` giữa Linux và Windows; nếu yêu cầu chính xác byte-for-byte thì dùng `Files.readAllBytes` và đối chiếu byte theo encoding/line ending đã quy định.

Đừng bỏ `close()`: writer có thể đang giữ buffer và file handle. Test đọc output trước khi đóng có thể thấy nội dung chưa được flush hết hoặc thất bại vì file bị khóa trên Windows.

### Các trường hợp đầu ra quan trọng

- **Không có item:** xác nhận có tạo file header-only, file rỗng hay xóa file bằng `shouldDeleteIfEmpty` đúng hợp đồng.
- **Đã có file:** xác nhận xóa/ghi mới, append hoặc từ chối; không để kết quả phụ thuộc file cũ.
- **Bản ghi chứa delimiter, dấu quote hoặc newline:** `lineAggregator` kiểu nối chuỗi thủ công trong ví dụ chỉ an toàn vì cả hai trường là số. Với text có dấu phẩy, cần một bộ sinh CSV có escaping đúng và test cho nó.
- **Quyền ghi/đường dẫn không hợp lệ:** xác nhận step báo lỗi và không công bố output chưa hoàn chỉnh như file thành công.
- **Định dạng số/ngày giờ:** quy định locale, múi giờ, thang đo thập phân và format đầu ra rõ ràng; không phụ thuộc locale của máy chạy CI.
- **Thứ tự:** nếu step xử lý song song hoặc phân vùng, chỉ assert thứ tự khi pipeline có cam kết duy trì thứ tự.

## 7. Integration test: chạy Job, kiểm tra cả file lẫn metadata

Unit test reader/writer có thể đều qua, nhưng job vẫn sai nếu gắn nhầm bean, truyền nhầm `JobParameters` hoặc cấu hình processor/chunk sai. `spring-batch-test` cung cấp `@SpringBatchTest` và `JobLauncherTestUtils` ở Spring Batch 5.2.

Ví dụ dưới đây giả định có một `paymentJob` trong context (class `DemoBatchApplication` quét `PaymentBatchConfig` ở cùng package).

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(
    classes = DemoBatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class PaymentJobIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path tempDir;

    @Test
    void transformsInputCsvIntoExpectedOutputCsv() throws Exception {
        Path input = tempDir.resolve("payments.csv");
        Path output = tempDir.resolve("invoices.csv");

        Files.writeString(input,
                "id,amount\n101,10.00\n102,20.50\n103,0.00\n",
                StandardCharsets.UTF_8);

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", input.toString())
                .addString("outputFile", output.toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(List.of(
                "id,total",
                "101,11.00",
                "102,21.50",
                "103,1.00"),
                Files.readAllLines(output, StandardCharsets.UTF_8));

        StepExecution step = execution.getStepExecutions().stream()
                .filter(s -> s.getStepName().equals("paymentStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(3L, step.getReadCount());
        assertEquals(3L, step.getWriteCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(0L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
    }
}
```

Điểm cần hiểu:

1. `spring.batch.job.enabled=false` ngăn Boot tự khởi chạy job trước khi test cung cấp đường dẫn; test sẽ chủ động gọi `launchJob(params)`.
2. Input và output nằm trong `@TempDir` nên mỗi test có dữ liệu độc lập. Trong cùng một `JobRepository`, nếu chạy lại **cùng** `JobParameters` cho một `JobInstance` đã hoàn tất, Spring Batch có thể báo `JobInstanceAlreadyCompleteException`; cần tạo tham số định danh lượt chạy phù hợp khi thực sự muốn khởi tạo instance mới.
3. `@StepScope` nhận `inputFile/outputFile` khi step thực thi, không phải lúc Spring dựng context.
4. Assertion trạng thái kết hợp với **output thật** và **read/write/skip count** giúp phát hiện job chạy thành công kỹ thuật nhưng sai nghiệp vụ.
5. Nếu test có nhiều bean `Job`, gọi `jobLauncherTestUtils.setJob(paymentJob)` (inject đúng `Job` theo qualifier) để tránh test khởi chạy nhầm job.

### Chỉ chạy một step

Khi job gồm nhiều step, có thể kiểm thử riêng step xử lý file bằng:

```java
JobExecution execution =
        jobLauncherTestUtils.launchStep("paymentStep", params);
```

`launchStep` cũng tạo ngữ cảnh chạy step và thực thi reader/processor/writer thực; phù hợp khi không cần chạy các step chuẩn bị, nhưng vẫn muốn xác thực input/output resource ở mức tích hợp.

Nếu step dùng dữ liệu được step khác đưa vào `JobExecutionContext`, overload `launchStep` có nhận `ExecutionContext` để cung cấp dữ liệu cần thiết.

## 8. Kiểm thử @StepScope và job parameter gắn resource

Đường dẫn input/output thường được truyền khi chạy job, ví dụ:

```java
@StepScope
@Bean
FlatFileItemReader<Payment> reader(
        @Value("#{jobParameters['inputFile']}") String file) {
    // Cấu hình reader với FileSystemResource(file)
}
```

Test bằng `new PaymentBatchConfig().paymentReader(path)` chỉ xác nhận logic dựng reader. Muốn kiểm tra **late binding** của Spring, phải kích hoạt step scope. Có hai cách:

- **Cách thực tế nhất:** chạy integration test bằng `launchStep`/`launchJob` với `JobParameters` thực, rồi đối chiếu file.
- **Cách cô lập bean:** dùng `StepScopeTestUtils.doInStepScope(stepExecution, callable)`, hoặc `@SpringBatchTest` kết hợp listener `StepScopeTestExecutionListener`, để cấp `StepExecution` cho bean step-scoped.

Phác thảo cách thứ hai:

```java
StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(
                new JobParametersBuilder()
                        .addString("inputFile", input.toString())
                        .toJobParameters());

// Reader được inject từ Spring context là bean @StepScope:
Payment first = StepScopeTestUtils.doInStepScope(stepExecution, () -> {
    stepScopedReader.open(new ExecutionContext());
    try {
        return stepScopedReader.read();
    } finally {
        stepScopedReader.close();
    }
});
```

Ở đây `stepScopedReader` phải được lấy **từ ApplicationContext** có kích hoạt `StepScope`, không được tạo bằng `new`. Khi đang kiểm thử binding, điều quan trọng là giá trị `JobParameters` thực sự được truyền đến resource. Với các bài test đơn giản, chạy step thật thường dễ hiểu và ít cấu hình hơn.

## 9. Thiết kế test case cho lỗi input/output

Không nên chỉ dùng một file hợp lệ. Hãy xây dựng ma trận tình huống dựa trên hợp đồng cụ thể của hệ thống.

| Tình huống | Kết quả mong đợi | Điều cần kiểm tra |
|---|---|---|
| Input tồn tại, 3 dòng hợp lệ | `COMPLETED` | Output đúng 3 dòng dữ liệu, đúng header và giá trị. |
| Input thiếu | `FAILED` khi `strict(true)` | Không coi số item đọc bằng 0 là thành công. |
| Input chỉ có header | Tùy hợp đồng, thường `COMPLETED` | `readCount=0`; output theo chính sách file rỗng. |
| Dòng CSV sai kiểu số | Mặc định fail nếu chưa cấu hình fault tolerance | Lỗi parse kèm số dòng và dữ liệu hỏng; `BatchStatus` và file đầu ra nhất quán. |
| Lỗi parse có cấu hình `skip` | Có thể `COMPLETED` trong giới hạn cho phép | `readSkipCount`, số dòng output, danh sách bản ghi bị loại đúng quy tắc. |
| Processor trả `null` | Item bị filter, không phải lỗi | Kiểm tra `filterCount` và `writeCount`. |
| Writer không mở được file | `FAILED` | Không tồn tại output sai được phát hành như thành công; log/error được quan sát. |
| Output đã tồn tại | Theo chính sách delete/append/restart | File mới không lẫn dữ liệu cũ; số header chính xác. |
| File UTF-8 chứa dấu tiếng Việt | Đọc/ghi nguyên vẹn | Không xuất hiện ký tự thay thế hoặc lỗi BOM. |
| Nhiều input resource | Mọi file được đọc theo thứ tự đã quy định | Không thiếu, trùng hoặc đổi thứ tự bất ngờ. |

Nếu job cấu hình `faultTolerant().skip(...).skipLimit(...)`, hãy chứng minh cả ba phần: loại exception được cho phép skip, số lượng skip giới hạn, và output sau skip vẫn đúng. Chỉ assert “job hoàn tất” có thể che giấu mất dữ liệu.

### Kiểm tra header thực sự

`linesToSkip(1)` chỉ bỏ qua dòng đầu của input. Nếu hợp đồng yêu cầu header đúng `id,amount`, có thể dùng `skippedLinesCallback` để kiểm tra, hoặc một bước kiểm tra schema riêng trước khi xử lý. Sau đó có test input như `amount,id` để xác nhận job từ chối file sai schema.

### Kiểm tra lỗi dữ liệu và lỗi resource khác nhau

- Lỗi **resource**: không tồn tại, không có quyền đọc/ghi, đường dẫn trỏ tới thư mục thay vì file, file bị hệ thống khác giữ.
- Lỗi **format**: sai delimiter, thiếu cột, số không parse được, ký tự không hợp lệ, header sai.
- Lỗi **nghiệp vụ**: mã trùng, giá trị âm không được phép, thiếu tham chiếu dữ liệu.

Phân loại lỗi giúp cấu hình retry/skip đúng: không nên tùy tiện retry một dòng dữ liệu sai format vô hạn; tương tự, không nên skip cả file nguồn bắt buộc chỉ vì có lỗi I/O.

## 10. Kiểm thử restart và tính nhất quán output

Spring Batch lưu trạng thái của các `ItemStream` qua `ExecutionContext` để hỗ trợ restart. Với reader theo dòng, trạng thái có thể cho phép quay lại vị trí cuối đã checkpoint; với writer, cần bảo toàn trạng thái tệp khi chạy lại.

### Minh họa reader lưu vị trí

Ý tưởng test độc lập:

```java
ExecutionContext context = new ExecutionContext();

FlatFileItemReader<Payment> firstReader =
        config.paymentReader(input.toString());
firstReader.open(context);
Payment first = firstReader.read();  // 101
firstReader.update(context);         // Mô phỏng lưu checkpoint
firstReader.close();

// Dùng reader mới, cùng name và resource, với context đã lưu.
FlatFileItemReader<Payment> resumedReader =
        config.paymentReader(input.toString());
resumedReader.open(context);
try {
    Payment next = resumedReader.read(); // Mong đợi 102
    assertEquals(102L, next.id());
} finally {
    resumedReader.close();
}
```

Ví dụ minh họa một phần cơ chế checkpoint; trong job thật, `JobRepository` lưu trạng thái cùng ranh giới commit. Khi kiểm thử restart ở cấp job, nên chủ động tạo lỗi sau một số chunk rồi chạy lại **cùng JobInstance** với điều kiện restart hợp lệ. Cần xác minh **output cuối cùng không thiếu, không trùng**, thay vì chỉ nhìn `COMPLETED` sau lần thứ hai.

Một số điểm quan trọng:

- `saveState(false)` làm mất khả năng tiếp tục từ vị trí đã lưu; không phù hợp nếu kỳ vọng restart chính xác.
- Thay đổi tên reader/writer hoặc thay đổi input giữa hai lần chạy có thể làm checkpoint không còn phù hợp.
- `shouldDeleteIfExists`, `append` và trạng thái writer phải được thử trên cả **lượt chạy mới** lẫn **lượt restart**; hai tình huống có quy tắc khác nhau.
- File output không tự có tính nguyên tử với commit database. Khi kết hợp ghi file, ghi DB và phát sự kiện, cần chính sách xuất bản file hoàn chỉnh (ví dụ ghi vào file tạm rồi đổi tên ở bước cuối) và test các điểm lỗi.

## 11. Nhiều resource, định dạng khác và môi trường test

### Nhiều file đầu vào

Với `MultiResourceItemReader`, test nên tạo nhiều file nhỏ và kiểm chứng: số lượng item được gom từ tất cả file, thứ tự file được định nghĩa rõ (cấu hình comparator nếu cần), và ranh giới chuyển từ file A sang file B không làm mất hoặc đọc trùng bản ghi. Nếu writer dùng `MultiResourceItemWriter`, hãy kiểm tra cả số lượng file được tạo, tên file, giới hạn item mỗi file và nội dung hợp nhất.

### JSON, XML, JDBC hoặc resource bên ngoài

Tư duy test vẫn tương tự:

- **JSON/XML reader:** chuẩn bị fixture tối giản nhưng có cấu trúc đúng, thử node/property thiếu, giá trị không hợp lệ và input rỗng; xác nhận mapping về object.
- **JSON/XML writer:** parse output bằng parser tương ứng để so sánh cấu trúc và dữ liệu, tránh so chuỗi thô nếu thứ tự property/whitespace không phải hợp đồng.
- **JDBC input/output:** dùng schema và dữ liệu test cô lập; kiểm tra số dòng trong DB và transaction, không chỉ kiểm tra status.
- **HTTP/object storage:** cô lập adapter/resource khi unit test; integration test chỉ kết nối môi trường thử nghiệm có kiểm soát. Tránh test phụ thuộc network/dịch vụ production.

### Làm cho test ổn định

- Mỗi test có input và output riêng; không dùng chung đường dẫn cố định.
- Ghi rõ encoding và chuẩn hóa line ending trước khi so sánh.
- Đóng reader/writer bằng `finally` hoặc cơ chế tương đương.
- Cố định clock, locale, timezone nếu logic tạo dữ liệu phụ thuộc chúng.
- Nếu test chạy song song, không dùng chung tên file hay trạng thái `JobRepository`.
- Không assert thông điệp lỗi nguyên văn quá chặt khi chỉ cần khẳng định loại exception, dòng lỗi và tác động nghiệp vụ.
- Với tệp lớn, kiểm tra thêm count/checksum và một số record đại diện; với fixture nhỏ, so sánh toàn bộ output rõ ràng hơn.

## 12. Ghi chú phiên bản Spring Batch 5.x và 6.x

Ví dụ Java ở trên dùng các API của **Spring Batch 5.2.x**. Trong **Spring Batch 6.x** có hai thay đổi đáng chú ý:

| Nội dung | Spring Batch 5.2.x | Spring Batch 6.x |
|---|---|---|
| Test utility chạy Job/Step | `JobLauncherTestUtils.launchJob()/launchStep()` | `JobOperatorTestUtils.startJob()/startStep()`; utility cũ được đánh dấu deprecated |
| Package của API item/file | `org.springframework.batch.item...` | Chuyển phần lớn sang `org.springframework.batch.infrastructure.item...`, ví dụ `...infrastructure.item.file.builder.FlatFileItemReaderBuilder` |
| JUnit | JUnit Jupiter được hỗ trợ | JUnit 4 không còn được hỗ trợ |

Ví dụ lời gọi test tương ứng trên Spring Batch 6.x:

```java
@Autowired
JobOperatorTestUtils jobOperatorTestUtils;

// Dùng startJob thay cho launchJob.
JobExecution execution = jobOperatorTestUtils.startJob(params);

// Hoặc kiểm thử riêng step:
JobExecution stepExecution =
        jobOperatorTestUtils.startStep("paymentStep");
```

Khi nâng cấp, điều chỉnh import theo **Javadoc đúng phiên bản đang dùng** và giữ dependency của Spring Boot/Spring Batch tương thích; không thay mỗi tên utility trong khi vẫn giữ các import item từ dòng 5.x.

## 13. Bài tập thực hành

**Bài 1 — Input hỏng:** thay dòng `102,20.50` thành `102,abc`. Viết unit test reader để kiểm tra `FlatFileParseException` và số dòng lỗi. Tiếp theo chạy job để chứng minh `BatchStatus` theo cấu hình lỗi đã chọn.

**Bài 2 — Output chính xác:** thêm một input với giá trị `999999999999.99`. Chứng minh kết quả tăng `1.00` là chính xác và không xuất hiện ký hiệu khoa học ngoài quy ước CSV của hệ thống.

**Bài 3 — Header không hợp lệ:** tạo CSV có header `amount,id`, nhưng giữ dữ liệu như cũ. Bổ sung bước xác minh header và test để job từ chối input sai thứ tự cột.

**Bài 4 — Thiếu resource:** tạo test với input không tồn tại. So sánh hành vi khi `reader.strict(true)` và khi chủ động đặt `strict(false)`, sau đó giải thích lựa chọn đúng cho một file thanh toán bắt buộc.

**Bài 5 — Restart:** tạo một processor phát sinh lỗi ở bản ghi thứ ba sau khi chunk đầu đã commit, sửa điều kiện gây lỗi rồi restart cùng JobInstance. Đối chiếu file kết quả cuối cùng, số dòng và header, đảm bảo không mất/trùng dữ liệu.

## 14. Tài liệu tham khảo

- [Spring Batch 5.2 – Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, kiểm thử step/job và step scope.
- [Spring Batch 6 – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): API kiểm thử hiện hành với `JobOperatorTestUtils`.
- [Spring Batch – FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): `Resource`, `LineMapper`, tokenizer, xử lý lỗi parse.
- [Spring Batch – FlatFileItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-writer.html): output resource, line aggregator, header và chính sách file đã tồn tại.
- [Spring Batch – Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): dùng `@StepScope` và `JobParameters` để chọn resource theo từng lần chạy.

Khi kiểm thử input/output resource, mục tiêu cuối cùng là chứng minh **dữ liệu nào đã được đọc, dữ liệu nào đã được ghi và ứng dụng phản ứng thế nào trước các tình huống bất thường**. Trạng thái job, metadata và nội dung resource là ba góc nhìn bổ sung cho nhau.
