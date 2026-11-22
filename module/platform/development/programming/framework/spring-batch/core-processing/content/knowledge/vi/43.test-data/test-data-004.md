# Dữ liệu lỗi cho skip trong Spring Batch

## 1. Mục đích của dữ liệu lỗi trong kiểm thử skip

Trong Spring Batch, **skip** cho phép một Step bỏ qua item gặp lỗi đã được phân loại là có thể chấp nhận, tiếp tục xử lý các item còn lại và ghi nhận số lượng bị bỏ qua. Cơ chế này thường được cấu hình trong chunk-oriented processing qua \`faultTolerant()\`, \`skip(...)\` hoặc \`skipPolicy(...)\`, cùng giới hạn \`skipLimit(...)\`.

Khi kiểm thử skip, điều quan trọng không phải chỉ tạo vài dòng dữ liệu “sai”, mà là tạo **fixture có lỗi được kiểm soát**: biết chính xác dòng nào phải thất bại, lỗi xuất hiện ở pha nào, exception nào được ném ra, số item hợp lệ được ghi, và job nên **COMPLETED** hay **FAILED**.

Ví dụ, một job nhập đơn hàng từ CSV có thể gặp ba dạng dữ liệu lỗi:

- \`quantity = abc\`: không chuyển thành số nguyên được khi đọc CSV; đây là lỗi tại **read**.
- \`quantity = 0\`: parse được nhưng vi phạm quy tắc nghiệp vụ; đây là lỗi tại **process** nếu processor kiểm tra số lượng.
- \`order_id\` trùng khóa duy nhất của bảng đích: đọc và xử lý được nhưng không ghi được; đây là lỗi tại **write**.

Ba trường hợp có thể cùng dẫn đến skip, nhưng cần **fixture, cấu hình, cách quan sát và kỳ vọng khác nhau**. Nếu cấu hình quá rộng như \`skip(Exception.class)\`, test dễ “đạt” bằng cách bỏ qua cả lỗi hệ thống đáng lẽ phải làm job thất bại.

Luồng cần hiểu:

~~~text
CSV / database / message
        |
        v
      Reader  --- lỗi parse/đọc ------> read skip
        |
        v
     Processor --- lỗi nghiệp vụ -----> process skip
        |
        v
      Writer  --- lỗi ghi được phép --> write skip
        |
        v
     Output hợp lệ

          Các skip được phép
                   |
                   v
      Cộng vào giới hạn skip của Step
                   |
          <= skipLimit ? 
             /       \
           Có        Không
            |          |
         Tiếp tục   Step FAILED
~~~

**Skip không giống filter.** Nếu \`ItemProcessor.process(item)\` trả về \`null\` một cách chủ đích, item được **filter** và tăng \`filterCount\`, không tăng \`processSkipCount\`. Nếu processor ném exception được cấu hình skip, item mới được tính là process skip.

## 2. Những trường hợp dữ liệu lỗi nên chuẩn bị

| Vị trí | Dữ liệu/hành vi tạo lỗi | Exception thường gặp hoặc được định nghĩa | Counter cần quan sát |
|---|---|---|---|
| Read | Chuỗi ký tự tại cột số: \`quantity=abc\` | \`FlatFileParseException\` khi lỗi mapping dòng được \`FlatFileItemReader\` bọc lại | \`readSkipCount\` |
| Read | Thiếu cột bắt buộc, số cột không hợp lệ | \`FlatFileParseException\` nếu tokenizer/mapper cấu hình strict phù hợp | \`readSkipCount\` |
| Process | Số lượng bằng 0 hoặc âm | \`InvalidOrderException\` do ứng dụng tự định nghĩa | \`processSkipCount\` |
| Process | Mã khách hàng không thuộc danh sách chấp nhận | Exception kiểm tra nghiệp vụ cụ thể | \`processSkipCount\` |
| Write | Khóa trùng khi insert DB | \`DuplicateKeyException\` hoặc ngoại lệ DB đã được dịch phù hợp | \`writeSkipCount\` nếu cho phép skip |
| Write | Vi phạm constraint được nghiệp vụ chấp nhận | \`DataIntegrityViolationException\` hoặc kiểu cụ thể do hệ thống phát ra | \`writeSkipCount\` nếu cho phép skip |
| Filter | Đơn ở trạng thái chủ đích không xuất | Processor trả \`null\` | \`filterCount\`, **không phải skip** |
| Lỗi hệ thống | DB mất kết nối, filesystem hỏng, cấu hình thiếu | Exception vận hành cụ thể | Thường phải retry có giới hạn hoặc FAILED |

Tên exception trong thực tế phụ thuộc reader, mapper, driver JDBC và phiên bản thư viện. **Kiểm thử cần xác nhận exception thực sự được phát ra**, không giả định mọi dữ liệu CSV sai đều thành cùng một exception, hoặc mọi lỗi JDBC đều là \`DuplicateKeyException\`.

### Những thuộc tính của một fixture tốt

1. **Cố định:** cùng input, cùng điều kiện test thì cùng item lỗi ở cùng pha.
2. **Có nhãn kỳ vọng:** ghi rõ item nào hợp lệ, lỗi parse, lỗi nghiệp vụ, lỗi ghi.
3. **Phân biệt lỗi độc lập:** một item chỉ mang một nguyên nhân lỗi chính trong mỗi test để tránh kết quả phụ thuộc thứ tự kiểm tra.
4. **Có cả dữ liệu tốt:** job phải tiếp tục và ghi các item hợp lệ sau khi skip.
5. **Có ca ranh giới:** bằng \`skipLimit\` và vượt \`skipLimit\`.
6. **Có baseline đầu ra:** xác nhận tập khóa và giá trị được ghi, không chỉ kiểm tra status.
7. **Có khả năng chạy lại:** dọn dữ liệu test, tạo tham số JobInstance duy nhất, không dựa vào thứ tự các lần chạy trước.

Nên dùng dữ liệu giả lập; không đưa thông tin khách hàng thật, token hoặc nội dung nhạy cảm vào fixture lỗi hay log skip.

## 3. Bộ dữ liệu CSV mẫu cho read skip và process skip

Giả sử job \`importOrdersJob\` đọc file CSV, ánh xạ thành \`RawOrder\`, kiểm tra \`quantity > 0\` và \`unitPrice > 0\`, tính tổng tiền rồi ghi mỗi đơn hợp lệ vào bảng \`processed_order\`.

File \`orders-with-skips.csv\`:

~~~csv
orderId,customerId,quantity,unitPrice
O001,C001,2,10.00
O002,C002,abc,7.00
O003,C003,0,25.00
O004,C004,1,11.50
O005,C005,3,4.00
~~~

Giải thích từng bản ghi:

| \`orderId\` | Dữ liệu | Kết quả kỳ vọng |
|---|---|---|
| O001 | Số lượng và đơn giá hợp lệ | Ghi output, \`totalAmount=20.00\` |
| O002 | \`quantity=abc\` không parse được | Read skip |
| O003 | \`quantity=0\` parse được nhưng không hợp lệ | Process skip |
| O004 | Hợp lệ | Ghi output, \`totalAmount=11.50\` |
| O005 | Hợp lệ | Ghi output, \`totalAmount=12.00\` |

Với một reader đọc thành công bốn item, processor không filter và mỗi item hợp lệ tạo đúng một output, ta kỳ vọng:

| Chỉ số | Giá trị kỳ vọng | Ý nghĩa |
|---|---:|---|
| Số dòng dữ liệu trong file, không tính header | 5 | Input vật lý |
| \`readCount\` | 4 | O001, O003, O004, O005 đọc thành công |
| \`readSkipCount\` | 1 | O002 |
| \`processSkipCount\` | 1 | O003 |
| \`writeSkipCount\` | 0 | Writer không gặp lỗi |
| \`filterCount\` | 0 | Không có processor trả \`null\` |
| \`writeCount\` | 3 | O001, O004, O005 |
| \`BatchStatus\` khi \`skipLimit(2)\` | \`COMPLETED\` | Hai skip được cho phép |

Tập khóa output phải là **O001, O004, O005**, tổng \`totalAmount\` là **43.50** (chỉ có ý nghĩa nếu tất cả cùng đơn vị tiền tệ). Một test chỉ so sánh \`writeCount=3\` vẫn có thể bỏ sót trường hợp ghi sai đơn hoặc sai số tiền.

**Lưu ý về \`readCount\`:** đây là thống kê item được framework đọc thành công, không nhất thiết bằng tổng số dòng vật lý trừ header. Khi parse một dòng thất bại, nó có thể được tính vào read skip thay vì readCount.

## 4. Cấu hình Step cho phép bỏ qua đúng lỗi

Ví dụ dưới đây dùng phong cách Spring Batch 5+ với \`JobRepository\` và \`PlatformTransactionManager\`. Ứng dụng cần cấu hình Spring Batch infrastructure, \`JdbcTemplate\` và bảng đích; snippet tập trung vào cơ chế đọc dữ liệu lỗi và skip.

### 4.1. Các kiểu dữ liệu và lỗi nghiệp vụ

~~~java
import java.math.BigDecimal;

record RawOrder(
        String orderId,
        String customerId,
        int quantity,
        BigDecimal unitPrice) {
}

record ProcessedOrder(
        String orderId,
        int quantity,
        BigDecimal totalAmount) {
}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String message) {
        super(message);
    }
}
~~~

\`InvalidOrderException\` là exception riêng của ứng dụng. Chỉ ném exception này cho các vi phạm dữ liệu đã được chính sách nghiệp vụ cho phép bỏ qua.

### 4.2. Reader tạo lỗi parse có thể quan sát được

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("orderId", "customerId", "quantity", "unitPrice");
    tokenizer.setStrict(true);

    DefaultLineMapper<RawOrder> lineMapper = new DefaultLineMapper<>();
    lineMapper.setLineTokenizer(tokenizer);
    lineMapper.setFieldSetMapper(fields -> new RawOrder(
            fields.readString("orderId"),
            fields.readString("customerId"),
            fields.readInt("quantity"),
            fields.readBigDecimal("unitPrice")));

    FlatFileItemReader<RawOrder> reader = new FlatFileItemReader<>();
    reader.setName("orderReader");
    reader.setResource(new FileSystemResource(inputFile));
    reader.setLinesToSkip(1);
    reader.setLineMapper(lineMapper);
    return reader;
}
~~~

Ở dòng O002, \`fields.readInt("quantity")\` không thể chuyển \`abc\` thành \`int\`. Khi \`FlatFileItemReader\` gọi line mapper, lỗi mapping dòng được bọc bằng \`FlatFileParseException\`; cấu hình skip có thể nhận diện và bỏ qua dòng đó.

\`setStrict(true)\` trên tokenizer kiểm soát số token theo schema; nó **không tự xác minh header đúng tên** vì \`linesToSkip(1)\` chỉ bỏ qua dòng đầu. Test header sai cần một quy tắc xác minh header riêng.

### 4.3. Processor tạo lỗi nghiệp vụ và writer ghi DB

~~~java
import java.math.BigDecimal;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
public ItemProcessor<RawOrder, ProcessedOrder> orderProcessor() {
    return raw -> {
        if (raw.quantity() <= 0) {
            throw new InvalidOrderException(
                    "Invalid quantity for orderId=" + raw.orderId());
        }
        if (raw.unitPrice() == null
                || raw.unitPrice().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderException(
                    "Invalid unitPrice for orderId=" + raw.orderId());
        }

        BigDecimal total = raw.unitPrice()
                .multiply(BigDecimal.valueOf(raw.quantity()));
        return new ProcessedOrder(raw.orderId(), raw.quantity(), total);
    };
}

@Bean
public ItemWriter<ProcessedOrder> orderWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (ProcessedOrder order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO processed_order
                        (order_id, quantity, total_amount)
                    VALUES (?, ?, ?)
                    """,
                    order.orderId(),
                    order.quantity(),
                    order.totalAmount());
        }
    };
}
~~~

Ví dụ schema SQL cho môi trường kiểm thử:

~~~sql
CREATE TABLE processed_order (
    order_id VARCHAR(50) PRIMARY KEY,
    quantity INTEGER NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL
);
~~~

Writer này dùng \`JdbcTemplate\` và sẽ tham gia transaction của chunk khi datasource và transaction manager được cấu hình nhất quán. Trong ứng dụng thực tế, cần bổ sung \`batchId\`, quản lý khóa nghiệp vụ phù hợp và quy tắc idempotency để tránh ghi trùng trên restart.

### 4.4. Step và Job với skipLimit

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, ProcessedOrder>chunk(2, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(2)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

\`skipLimit(2)\` có nghĩa tối đa **hai skip trong Step này**, tính tổng các loại read, process và write skip. Đây **không phải giới hạn riêng cho từng pha**. Khi gặp lỗi có thể skip thứ ba, Step sẽ thất bại vì vượt ngưỡng. Giới hạn của Step khác không tự cộng dồn vào Step này.

Job vẫn có thể hoàn tất ở trạng thái \`COMPLETED\` dù có skip hợp lệ. Vì vậy, hệ thống downstream nên quan sát thêm các skip counter và chính sách chất lượng dữ liệu, không đồng nhất COMPLETED với “không có bản ghi lỗi”.

## 5. Viết test tích hợp với dữ liệu lỗi cố định

Một test skip hữu ích phải chạy **Step hoặc Job thực**, truyền file fixture và kiểm tra ba lớp: **trạng thái thực thi**, **counter** và **output thực tế**. Ví dụ sau minh họa JUnit 5, Spring Batch Test và ứng dụng Spring Boot đã nạp cấu hình Job ở mục 4.

Trong môi trường test cần:

- Dependency \`spring-batch-test\` và thư viện test của Spring Boot/JUnit.
- Database test đã tạo các bảng metadata Spring Batch và bảng \`processed_order\` phía trên.
- Tắt tự khởi chạy batch khi dựng context, chẳng hạn \`spring.batch.job.enabled=false\`, để test tự điều khiển việc launch.
- Chỉ có một Job phù hợp để \`JobLauncherTestUtils\` tự nhận diện, hoặc cấu hình Job cho utility một cách tường minh.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
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
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderSkipIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @TempDir
    Path workDir;

    @BeforeEach
    void clearOutput() {
        // Dọn bảng của DB riêng dành cho bộ test này.
        jdbcTemplate.update("DELETE FROM processed_order");
    }

    @Test
    void skipsOneReadErrorAndOneProcessError() throws Exception {
        String csv = """
                orderId,customerId,quantity,unitPrice
                O001,C001,2,10.00
                O002,C002,abc,7.00
                O003,C003,0,25.00
                O004,C004,1,11.50
                O005,C005,3,4.00
                """;

        JobExecution execution = launchWithCsv(csv);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(4L, step.getReadCount());
        assertEquals(1L, step.getReadSkipCount());
        assertEquals(1L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(0L, step.getFilterCount());
        assertEquals(3L, step.getWriteCount());

        List<String> actualIds = jdbcTemplate.queryForList(
                "SELECT order_id FROM processed_order ORDER BY order_id",
                String.class);
        assertEquals(List.of("O001", "O004", "O005"), actualIds);
    }

    private JobExecution launchWithCsv(String content) throws Exception {
        Path file = workDir.resolve("orders.csv");
        Files.writeString(file, content, StandardCharsets.UTF_8);

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", file.toAbsolutePath().toString())
                .addString("testRun", UUID.randomUUID().toString())
                .toJobParameters();

        return jobLauncherTestUtils.launchJob(parameters);
    }
}
~~~

Đoạn test sử dụng \`@TempDir\` để tránh chia sẻ file đầu vào giữa các test và tham số \`testRun\` khác nhau để tạo JobInstance riêng. Việc \`DELETE FROM processed_order\` chỉ phù hợp với **database test cô lập**, không áp dụng cho môi trường dùng chung hoặc production.

Để kiểm tra dữ liệu kỹ hơn, bổ sung assertion trên \`total_amount\` bằng \`BigDecimal\` và kiểm tra không có \`O002\`, \`O003\`. Nếu job có nhiều Step, chọn StepExecution theo tên \`importOrdersStep\` thay vì lấy phần tử đầu tiên.

## 6. Test biên của skipLimit: đúng ngưỡng và vượt ngưỡng

Với cấu hình \`skipLimit(2)\`:

| Fixture | Lỗi được phép skip | Kỳ vọng |
|---|---:|---|
| Không có lỗi | 0 | \`COMPLETED\`, tất cả item hợp lệ được ghi |
| 1 dòng sai kiểu số | 1 | \`COMPLETED\`, \`readSkipCount=1\` |
| 1 dòng sai kiểu số + 1 đơn quantity bằng 0 | 2 | \`COMPLETED\`, tổng skip bằng 2 |
| 2 lỗi trên + 1 đơn giá âm | 3 | \`FAILED\` vì vượt \`skipLimit\` |
| 1 lỗi không có trong danh sách skippable | Có thể mới là lỗi đầu tiên | \`FAILED\` ngay, dù \`skipLimit\` còn dư |

Ví dụ fixture **vượt ngưỡng**:

~~~csv
orderId,customerId,quantity,unitPrice
O001,C001,2,10.00
O002,C002,abc,7.00
O003,C003,0,25.00
O004,C004,1,11.50
O005,C005,2,-4.00
O006,C006,3,4.00
~~~

O002 gây read skip, O003 và O005 gây process skip: tổng cộng ba lỗi có thể bỏ qua, trong khi Step cho phép hai. **Step phải FAILED**. Vì chunk có thể đã commit một phần trước khi lỗi thứ ba, không nên tùy tiện khẳng định mọi output trong DB đều rỗng khi job FAILED.

Có thể bổ sung một test trong cùng class tích hợp:

~~~java
@Test
void failsWhenSkipLimitIsExceeded() throws Exception {
    String csv = """
            orderId,customerId,quantity,unitPrice
            O001,C001,2,10.00
            O002,C002,abc,7.00
            O003,C003,0,25.00
            O004,C004,1,11.50
            O005,C005,2,-4.00
            O006,C006,3,4.00
            """;

    JobExecution execution = launchWithCsv(csv);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    StepExecution step = execution.getStepExecutions()
            .iterator().next();
    assertEquals(BatchStatus.FAILED, step.getStatus());
    // Không công bố output của lần chạy thất bại.
}
~~~

Nếu job được thiết kế có thêm Step kiểm tra output, marker READY hoặc bản ghi trạng thái xuất bản, hãy assert rằng **không có dấu hiệu công bố thành công** khi Step nhập liệu FAILED.

## 7. Tạo dữ liệu lỗi riêng cho write skip

Write skip khó kiểm thử hơn read/process skip vì writer có thể đã thao tác trên nhiều item trong cùng một chunk. Nhiều writer JDBC phát lỗi trong lúc thực hiện batch; framework phải xác định item gây lỗi, có thể thử ghi lại từng item trong quá trình xử lý lỗi. Vì vậy, test write skip cần cơ sở dữ liệu và transaction behavior gần với triển khai thật.

### 7.1. Fixture trùng khóa

Chuẩn bị DB test trước khi launch:

~~~sql
INSERT INTO processed_order(order_id, quantity, total_amount)
VALUES ('O004', 1, 11.50);
~~~

File nhập:

~~~csv
orderId,customerId,quantity,unitPrice
O001,C001,2,10.00
O004,C004,1,11.50
O005,C005,3,4.00
~~~

Khi writer \`INSERT\` vào \`processed_order\`, O004 vi phạm khóa chính. Với driver/dialect và Spring JDBC phù hợp, lỗi có thể được dịch thành \`DuplicateKeyException\`. **Cấu hình ở mục 4 chưa cho phép write skip**, do đó phép thử này theo cấu hình mặc định phải làm Step FAILED.

Để chủ đích cho phép bỏ qua duplicate, cần một cấu hình test/policy riêng đã được nghiệp vụ chấp nhận, ví dụ bổ sung:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(org.springframework.dao.DuplicateKeyException.class)
.skipLimit(2)
~~~

Đoạn trên thay phần \`faultTolerant()\` trong Step, **không nối thêm một đoạn \`faultTolerant()\` thứ hai**. Nếu thực tế driver trả về \`DataIntegrityViolationException\` hoặc exception khác, hãy xác định loại lỗi thực và xây chính sách cụ thể; tránh \`skip(Exception.class)\`.

Trong test write skip, kiểm tra \`writeSkipCount\`, tập output cuối và tính duy nhất khóa. Nếu đã có O004 trong bảng từ trước, kết quả cuối có thể vẫn chứa O004; vì vậy **không lấy COUNT(*) của toàn bảng để kết luận số item writer đã ghi trong lần chạy**. Phân biệt bản ghi pre-seed với bản ghi mới bằng batchId, audit hoặc nguồn expected riêng.

### 7.2. Vấn đề rollback của writer

Khi writer dùng cùng transaction với Step, lỗi ghi thường kéo theo rollback của chunk rồi framework xử lý theo chính sách retry/skip. Nếu writer gọi API ngoài, ghi file không giao dịch hoặc tự quản lý transaction khác, những thao tác đã thành công trước khi lỗi **không chắc được rollback**. Một writer không idempotent có thể tạo duplicate trong lúc framework thử xác định item lỗi.

Vì vậy:

- Với lỗi ghi DB, dùng database test thật hoặc môi trường tích hợp có behavior transaction sát thực tế.
- Nếu cho phép skip ở writer, kiểm tra idempotency, khóa duy nhất và dữ liệu cuối sau rollback/retry.
- Không dùng một \`List.add(item)\` đơn giản trong writer giả để kết luận cơ chế rollback/skip của writer production an toàn.
- Nếu lỗi DB là lỗi tạm thời (deadlock, mất kết nối), cân nhắc retry có giới hạn thay vì coi bản ghi là dữ liệu xấu.

## 8. Phân biệt skip, retry, filter và fail khi thiết kế test

| Cơ chế | Khi nào dùng | Dữ liệu/hành vi để test | Chỉ số hoặc kết quả |
|---|---|---|---|
| Skip | Bản ghi lỗi vĩnh viễn nhưng được phép loại bỏ | Số không hợp lệ, lỗi parse được cho phép | \`readSkipCount\`, \`processSkipCount\` hoặc \`writeSkipCount\` |
| Retry | Lỗi có thể hết khi thử lại | Timeout mô phỏng, dịch vụ tạm unavailable | Số attempt, thành công sau retry hoặc FAILED/recover theo policy |
| Filter | Chủ đích không đưa item sang writer, không phải lỗi | Đơn có trạng thái bỏ qua theo quy tắc | \`filterCount\` |
| Fail | Lỗi làm kết quả không còn đáng tin hoặc không được phép bỏ qua | Sai cấu hình, thiếu file, lỗi hạ tầng nghiêm trọng | \`StepExecution.status=FAILED\` |

Ví dụ processor lọc đơn có \`status=CANCELLED\`:

~~~java
return raw -> {
    if ("CANCELLED".equals(raw.status())) {
        return null; // Filter: không phải process skip
    }
    if (raw.quantity() <= 0) {
        throw new InvalidOrderException("Invalid quantity");
    }
    return convert(raw);
};
~~~

Đây là ví dụ với mô hình \`RawOrder\` có thêm trường \`status\` và hàm \`convert\`; nó minh họa sự khác nhau, **không phải phương thức có thể chèn nguyên xi vào record ở mục 4**.

Khi cần kết hợp retry rồi skip, chẳng hạn một lỗi writer được phép bỏ qua **chỉ sau khi đã retry hết số lần**, test nên kiểm tra riêng số attempt và kết quả cuối. Skip count chỉ phản ánh việc item bị bỏ qua; nó không cho biết đã retry bao nhiêu lần.

**Không coi tất cả exception từ writer là lỗi dữ liệu.** Một \`SQLException\` do mất kết nối, một timeout mạng hoặc thiếu quyền truy cập là tín hiệu vận hành; bỏ qua hàng loạt item có thể làm job báo COMPLETED trong khi dữ liệu mất nhiều.

## 9. Dùng SkipListener để thu thập bằng chứng

Để biết item nào bị skip và tại sao, Spring Batch cung cấp \`SkipListener<T, S>\`:

~~~java
import org.springframework.batch.core.SkipListener;

class OrderSkipLogger implements SkipListener<RawOrder, ProcessedOrder> {

    @Override
    public void onSkipInRead(Throwable error) {
        // Chưa có RawOrder vì đọc/parse thất bại.
        // Với FlatFileParseException có thể lấy số dòng
        // và thông tin lỗi ở mức an toàn.
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        // Ghi orderId, reason code, exception class.
    }

    @Override
    public void onSkipInWrite(ProcessedOrder item, Throwable error) {
        // Ghi orderId và lý do ghi thất bại.
    }
}
~~~

Gắn listener vào fault-tolerant Step qua \`.listener(orderSkipLogger)\` hoặc bean listener phù hợp. Khi read skip, chưa có item đối tượng để lấy khóa nghiệp vụ; thông tin số dòng từ \`FlatFileParseException\` có thể hữu ích hơn.

Trong hệ thống thật, nên lưu audit theo cấu trúc:

~~~text
jobExecutionId = 12034
stepName       = importOrdersStep
inputFile      = orders-with-skips.csv
phase          = PROCESS
lineOrItemKey  = O003
reasonCode     = INVALID_QUANTITY
exceptionType  = InvalidOrderException
action         = SKIPPED
~~~

Đối với read skip, key có thể là số dòng/record index thay vì \`orderId\`. Không log nguyên dòng raw nếu nó chứa dữ liệu cá nhân hoặc bí mật. Nếu ghi audit đến nơi ngoài transaction, cần tính đến rollback và việc callback được gọi lại trong các tình huống lỗi, tránh tạo sự kiện trùng hoặc báo sai.

## 10. Ma trận dữ liệu lỗi có thể tái sử dụng

Một bộ fixture riêng theo từng ca giúp test nhanh và rõ nguyên nhân:

| File/ca test | Cách tạo lỗi | Kết quả mong đợi |
|---|---|---|
| \`all-valid.csv\` | Tất cả bản ghi hợp lệ | Không skip; output đủ |
| \`bad-integer.csv\` | \`quantity=abc\` | Read skip nếu exception được cho phép |
| \`missing-column.csv\` | Thiếu \`unitPrice\` | Read skip với tokenizer strict |
| \`bad-decimal.csv\` | \`unitPrice=12x\` | Read skip |
| \`zero-quantity.csv\` | \`quantity=0\` | Process skip |
| \`negative-price.csv\` | \`unitPrice=-1.00\` | Process skip |
| \`one-bad-after-good.csv\` | Dòng lỗi nằm sau nhiều dòng hợp lệ | Job không mất dữ liệu đã xử lý hợp lệ |
| \`one-good-after-bad.csv\` | Dòng hợp lệ ngay sau dòng lỗi | Reader/processor tiếp tục đúng |
| \`exact-skip-limit.csv\` | Đúng N lỗi có thể skip | Job COMPLETED với \`skipLimit(N)\` |
| \`over-skip-limit.csv\` | N+1 lỗi có thể skip | Job FAILED |
| \`non-skippable.csv\` | Exception không trong policy | Job FAILED ngay |
| \`duplicate-key.csv\` | Input va chạm khóa đã có trong DB test | Write skip nếu được cấu hình, nếu không FAILED |
| \`filtered.csv\` | Bản ghi đúng điều kiện filter | Tăng \`filterCount\`, không tăng skip |
| \`header-only.csv\` | Không có dòng dữ liệu | Không tự tạo skip; xác minh chính sách có cho phép output rỗng |

Nên có ít nhất một fixture có **hai lỗi khác pha** để chứng minh giới hạn skip được tính chung. Những file lỗi riêng biệt giúp khoanh vùng nếu test thất bại, còn một file hỗn hợp giúp xác nhận hành vi thực tế khi nhiều loại lỗi xuất hiện trong cùng Step.

### Test lỗi tại vị trí ranh giới chunk

Với \`chunk(2)\`, hãy thử đặt item lỗi:

- Ở **đầu file** và ngay trước lần commit đầu tiên.
- Ở **cuối chunk** để quan sát xử lý khi chuẩn bị ghi.
- Ở **đầu chunk kế tiếp**, sau khi chunk trước đã commit.
- **Liền nhau**, để bảo đảm iterator/reader không vô tình bỏ qua thêm record tốt.
- Gần **EOF**, để xác minh không tạo thêm item giả hoặc lặp item cuối.

Không nên assert chính xác số lần gọi processor/writer nếu fault-tolerant processing có thể chạy lại sau rollback; khi đó các counter chuẩn của Step và **output cuối cùng** là tín hiệu phù hợp hơn.

## 11. Thiết kế kiểm thử restart với dữ liệu có skip

Một bài test restart nên mô phỏng hai giai đoạn:

1. Chạy lần đầu với fixture cố định, cho phép skip lỗi dữ liệu, nhưng gây một lỗi **không được skip** ở phía sau để job FAILED sau khi một số chunk đã commit.
2. Loại bỏ nguyên nhân lỗi vận hành theo cách được phép (ví dụ service mock hoạt động trở lại) và restart **cùng JobInstance** theo cơ chế Spring Batch; không tự thay đổi fixture input giữa hai lần nếu reader dựa trên checkpoint của file đó.
3. Xác nhận lần restart chỉ tạo đúng tập output cuối, không trùng khóa, và trạng thái skip/audit phù hợp thiết kế.

Phân biệt \`JobInstance\` và \`JobExecution\`: restart cùng JobInstance thường sinh thêm JobExecution. Không sử dụng tham số nhận diện mới chỉ để gọi đó là restart; cách đó có thể tạo một JobInstance hoàn toàn mới và làm mất ý nghĩa kiểm tra checkpoint.

Đối với file input, dữ liệu **phải giữ bất biến** trong cùng một JobInstance khi sử dụng checkpoint theo vị trí đọc. Nếu thay đổi, chèn hoặc xóa dòng giữa hai attempt, vị trí khôi phục có thể trỏ vào bản ghi khác. Dùng fixture/version mới và JobInstance mới khi thật sự cần xử lý nguồn đã sửa.

Với writer ra hệ thống ngoài transaction, test phải kiểm tra **at-least-once effect** có thể xảy ra, không chỉ tổng số skip. Thiết kế idempotent cho writer hoặc key chống trùng trước khi tin vào kết quả restart.

## 12. Những bẫy thường gặp khi tạo dữ liệu lỗi cho skip

**Dữ liệu lỗi không đi tới đúng pha cần kiểm thử.** Ví dụ đặt \`quantity=abc\` rồi muốn kiểm tra process skip, nhưng reader đã lỗi trước. Khắc phục: dùng \`quantity=0\` để qua parse và lỗi ở processor.

**Chỉ có item lỗi, không có item tốt phía sau.** Test xác nhận skip nhưng không chứng minh job tiếp tục xử lý. Khắc phục: đặt item hợp lệ cả trước và sau item lỗi.

**Không phân biệt header và dòng dữ liệu.** \`linesToSkip(1)\` bỏ qua header mà không tự validate nội dung header. Khắc phục: kiểm tra schema/header riêng khi contract yêu cầu.

**Dùng \`skip(Exception.class)\` trong test.** Có thể vô tình bỏ qua lỗi hệ thống và khiến test cho kết quả sai về mức độ chịu lỗi. Khắc phục: giới hạn exception cụ thể và có ca non-skippable.

**Nhầm skip limit là mỗi loại lỗi được N lần.** Trong một Step, read/process/write skip cùng dùng tổng giới hạn. Khắc phục: test hỗn hợp nhiều pha.

**Dùng \`filterCount\` để khẳng định skip.** Processor trả \`null\` không phải exception. Khắc phục: quan sát đúng \`processSkipCount\`.

**Chỉ assert status COMPLETED.** Job có thể hoàn tất dù bỏ qua dữ liệu sai, thậm chí vượt ngưỡng chất lượng nghiệp vụ nếu cấu hình cho phép. Khắc phục: assert counter, output key, giá trị và ngưỡng nghiệp vụ.

**Giả định write skip luôn rollback sạch ở mọi đích.** File, API và writer tự quản transaction có thể giữ lại side effect. Khắc phục: kiểm tra transaction và idempotency.

**Chạy lại fixture với cùng tham số identifying trên JobInstance đã COMPLETED.** Spring Batch có thể từ chối chạy lại instance hoàn tất thay vì chạy test. Khắc phục: dùng JobParameters nhận diện duy nhất cho các lần chạy độc lập; giữ nguyên identifying parameters khi thực sự kiểm thử restart.

**Dùng dữ liệu test từ production.** Thông tin nhạy cảm có thể lọt vào fixture, exception message hoặc báo cáo CI. Khắc phục: tạo dữ liệu tổng hợp với mã, số tiền và khách hàng giả.

## 13. Cách đánh giá một bài kiểm thử dữ liệu lỗi cho skip

Một test được coi là có ích khi nó trả lời rõ các câu hỏi sau bằng assertion hoặc bằng chứng quan sát được:

1. **Item nào bị lỗi và vì sao?** Khóa item, loại lỗi, pha phát sinh phải biết trước.
2. **Exception nào thực sự được ném?** Reader/processor/writer có phát ra kiểu mà policy xử lý không?
3. **Policy xử lý đúng không?** Lỗi có trong danh sách được bỏ qua; lỗi khác làm job thất bại.
4. **Các counter đúng không?** Read/process/write skip và filter không bị nhầm lẫn.
5. **Tập output đúng không?** Item hợp lệ đã được ghi chính xác, item lỗi không gây dữ liệu bẩn hoặc trùng lặp.
6. **Ngưỡng skip đúng không?** Bằng ngưỡng thì tiếp tục, vượt ngưỡng thì FAILED.
7. **Job có thể được vận hành an toàn không?** Output của job thất bại không được công bố nhầm; restart không nhân đôi dữ liệu.

Trong Spring Batch, **dữ liệu lỗi cho skip là một phần của hợp đồng kiểm thử khả năng chịu lỗi**. Fixture rõ ràng, exception được phân loại chặt, skip limit có ca biên và output được đối soát giúp chứng minh rằng job bỏ qua đúng những bản ghi được phép, vẫn xử lý dữ liệu tốt và thất bại khi chất lượng dữ liệu hoặc điều kiện vận hành không còn được bảo đảm.
