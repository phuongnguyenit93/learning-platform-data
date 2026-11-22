# Viết unit và integration test cho dự án Spring Batch

Một batch job có thể chạy xong với trạng thái `COMPLETED` nhưng vẫn ghi thiếu bản ghi, xử lý trùng khi restart, bỏ qua lỗi dữ liệu quá mức hoặc để lại những chunk đã commit khi step phía sau thất bại. Vì vậy, kiểm thử Spring Batch không nên dừng ở việc gọi `jobLauncher.run(...)` rồi kiểm tra rằng ứng dụng không ném exception. Cần kiểm tra **quy tắc xử lý từng item**, **hành vi thực tế của reader/processor/writer**, **transaction, metadata, skip/retry, restart** và cuối cùng là **dữ liệu đầu ra**.

Bài học thuộc **Spring Batch Core Processing → Dự án thực hành**, hướng dẫn viết **unit test và integration test** qua một dự án nhập đơn hàng từ CSV vào database. Ví dụ dùng **Java 17, Spring Boot 3.x, Spring Batch 5.x, JUnit 5, AssertJ, Spring Batch Test và H2**. Các test riêng cho đặc tính của PostgreSQL/MySQL có thể được thực hiện với Testcontainers thay vì giả định H2 mô phỏng hoàn toàn database sản xuất.

## 1. Phân biệt unit test và integration test trong batch

**Unit test** kiểm tra một thành phần nhỏ với đầu vào xác định, không cần khởi động toàn bộ Spring context hoặc dùng `JobRepository` thật. **Integration test** kiểm tra nhiều thành phần phối hợp với Spring Batch runtime, datasource, transaction và metadata.

| Phạm vi | Mục tiêu | Ví dụ assertion |
| --- | --- | --- |
| Unit test `ItemProcessor` | Validation, mapping, filter theo business rule | Dữ liệu hợp lệ tạo output; invalid ném exception; filter trả `null` |
| Unit test reader hoặc mapper | Parsing và lifecycle của reader | Đọc đúng field; tới EOF trả `null`; giải phóng resource |
| Unit test policy | Quyết định skip, chất lượng, ngày nghiệp vụ | Mã lỗi và ngưỡng chính xác ở các trường hợp biên |
| Integration test step | Reader + processor + writer + transaction | `readCount`, `writeCount`, `filterCount`, skip count, dữ liệu DB |
| Integration test job | Job flow, `JobRepository`, trạng thái cuối | Job `COMPLETED`/`FAILED`, step theo thứ tự, output đúng |
| Restart/failure test | Tính nhất quán khi lỗi và chạy lại | Cùng instance tạo execution mới; không ghi trùng |
| Contract/test với dependency thật | SQL, isolation, locking, API contract | Unique key, rollback, retry và idempotency hoạt động đúng |

Mục tiêu không phải viết mọi test dưới dạng `@SpringBootTest`. Unit test ngắn, dễ đọc và chạy nhanh nên chiếm phần lớn; integration test xác nhận những điều unit test không chứng minh được.

```text
Business rules                        Spring Batch infrastructure
      |                                           |
      v                                           v
Unit tests                                Integration tests
      |                                           |
      +-- Processor / mapper                     +-- Reader -> Processor -> Writer
      +-- Error classifier                       +-- Transaction / chunk
      +-- Filtering policy                       +-- JobRepository metadata
      +-- Quality thresholds                     +-- Skip / restart / status
      |                                           |
      +----------------+--------------------------+
                       |
                       v
               Release confidence
```

## 2. Dự án thực hành: `importOrdersJob`

Giả sử mỗi ngày hệ thống nhận một file CSV đơn hàng. Pipeline:

```text
CSV input
   |
   v
FlatFileItemReader<RawOrder>
   |
   v
OrderProcessor
   |-- ACTIVE + amount hợp lệ ---> AcceptedOrder
   |-- CANCELLED ---------------> null (FILTER)
   |-- amount không hợp lệ ------> InvalidOrderException (SKIP có hạn)
   v
JdbcBatchItemWriter<AcceptedOrder>
   |
   v
accepted_orders (database)
   |
   v
JobRepository: JobExecution / StepExecution / counts
```

Hợp đồng minh họa:

- Một record `ACTIVE` có mã đơn hợp lệ và `amount > 0` được ghi.
- Record `CANCELLED` được loại theo **filter rule** đã duyệt, không tính là skip.
- Record thiếu `order_id` hoặc có `amount` không hợp lệ ném `InvalidOrderException`.
- Một step được phép skip tối đa **2 item** thuộc loại trên. Item lỗi thứ ba khiến step thất bại.
- Bảng đích có khóa chính `(source_batch_id, order_id)` để xác định một đơn hàng trong một phiên bản dữ liệu.
- Test xác nhận cả **metadata Spring Batch** và **dữ liệu thật trong database**.

Đây là dự án học tập, chưa bao gồm preflight kiểm tra checksum và publish gate cho downstream. Nếu triển khai dữ liệu nghiệp vụ quan trọng, cần bổ sung kiểm tra nguồn, quarantine và staging/publish có điều kiện.

### 2.1. Cấu trúc thư mục

```text
src/
├── main/
│   └── java/com/example/batch/
│       ├── OrdersBatchApplication.java
│       ├── RawOrder.java
│       ├── AcceptedOrder.java
│       ├── InvalidOrderException.java
│       ├── OrderProcessor.java
│       └── OrdersJobConfig.java
└── test/
    ├── java/com/example/batch/
    │   ├── OrderProcessorTest.java
    │   ├── OrderReaderTest.java
    │   └── ImportOrdersJobIT.java
    └── resources/
        ├── application-test.properties
        ├── schema.sql
        └── fixtures/
            ├── orders-mixed.csv
            ├── orders-valid.csv
            └── orders-too-many-invalid.csv
```

Tên file và class bên dưới khớp với cấu trúc trên. Mỗi `public` class/record nằm trong một file `.java` riêng.

## 3. Dependency và môi trường test

Ví dụ `build.gradle` cho dự án Spring Boot 3, dùng một phiên bản Boot 3.x cụ thể để minh họa (không phải khuyến nghị dùng bản cũ trong production):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý phiên bản Spring Batch và các dependency tương thích thông qua dependency management. Khi tích hợp vào dự án đã có phiên bản Boot riêng, hãy dùng phiên bản và BOM của dự án; tránh tự trộn các phiên bản Spring Batch, Spring Framework và Spring Retry không tương thích.

Các thư viện chính:

| Dependency | Vai trò trong test |
| --- | --- |
| `spring-boot-starter-test` | JUnit 5, AssertJ, Mockito, hạ tầng Spring Boot Test |
| `spring-batch-test` | `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, tiện ích step scope |
| H2 | Database nhúng cho test JDBC và các bảng metadata `BATCH_*` |
| `spring-boot-starter-batch` | Job, step, reader/writer, `JobRepository`, transaction integration |
| `spring-boot-starter-jdbc` | Datasource, `JdbcTemplate`, JDBC transaction |

H2 phù hợp để chạy bài học và kiểm tra nhiều quy tắc batch chung. Những đặc tính riêng của PostgreSQL/MySQL như khóa, transaction isolation, deadlock, cú pháp `ON CONFLICT` và hiệu năng query nên được kiểm tra thêm trên đúng database engine bằng Testcontainers hoặc một môi trường test cô lập.

### 3.1. Application entry point

`OrdersBatchApplication.java`:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersBatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersBatchApplication.class, args);
    }
}
```

Với Spring Boot 3 và cơ chế batch auto-configuration thông thường, không cần tự thêm `@EnableBatchProcessing`. Annotation đó có thể làm thay đổi cách Boot tự cấu hình hạ tầng, nên chỉ sử dụng khi dự án thực sự cần cấu hình batch infrastructure thủ công.

## 4. Implement phần nghiệp vụ để kiểm thử

### 4.1. Dữ liệu đầu vào và đầu ra

`RawOrder.java`:

```java
package com.example.batch;

public record RawOrder(
        String orderId,
        String status,
        String amountText) {}
```

`AcceptedOrder.java`:

```java
package com.example.batch;

import java.math.BigDecimal;

public record AcceptedOrder(
        String sourceBatchId,
        String orderId,
        BigDecimal amount) {}
```

`sourceBatchId` là định danh của phiên bản dữ liệu nguồn. Khi một job chạy lại hoặc replay, định danh này giúp đối chiếu output với lô cụ thể. Không thêm `run.id` ngẫu nhiên vào business key của writer vì nó có thể vô hiệu hóa cơ chế chống trùng.

`InvalidOrderException.java`:

```java
package com.example.batch;

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

Exception dùng **mã lý do cố định**, không đưa nguyên dữ liệu CSV, email hoặc thông tin nhạy cảm vào message.

### 4.2. Processor độc lập với Spring context

`OrderProcessor.java`:

```java
package com.example.batch;

import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<RawOrder, AcceptedOrder> {

    private final String sourceBatchId;

    public OrderProcessor(String sourceBatchId) {
        if (sourceBatchId == null || sourceBatchId.isBlank()) {
            throw new IllegalArgumentException(
                    "sourceBatchId is required");
        }
        this.sourceBatchId = sourceBatchId;
    }

    @Override
    public AcceptedOrder process(RawOrder row) {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("MISSING_ORDER_ID");
        }

        if ("CANCELLED".equals(row.status())) {
            return null; // Filter được cho phép bởi business rule.
        }

        if (!"ACTIVE".equals(row.status())) {
            throw new InvalidOrderException("UNSUPPORTED_STATUS");
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

        return new AcceptedOrder(
                sourceBatchId, row.orderId(), amount);
    }
}
```

Processor không phụ thuộc datasource, logger hay `JobRepository`, nên có thể kiểm thử trực tiếp bằng `new OrderProcessor(...)`. Trong chương trình thật, quy tắc `CANCELLED` phải được xác nhận từ hợp đồng nghiệp vụ: filter có chủ đích không đồng nghĩa dữ liệu bị lỗi.

## 5. Wiring reader, processor, writer và job

`OrdersJobConfig.java`:

```java
package com.example.batch;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersJobConfig {

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

    @Bean
    @StepScope
    OrderProcessor orderProcessor(
            @Value("#{jobParameters['sourceBatchId']}")
            String sourceBatchId) {
        return new OrderProcessor(sourceBatchId);
    }

    @Bean
    JdbcBatchItemWriter<AcceptedOrder> orderWriter(
            DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<AcceptedOrder>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO accepted_orders
                         (source_batch_id, order_id, amount)
                     VALUES (:sourceBatchId, :orderId, :amount)
                     """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("sourceBatchId",
                                        item.sourceBatchId())
                                .addValue("orderId", item.orderId())
                                .addValue("amount", item.amount()))
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> reader,
            OrderProcessor processor,
            JdbcBatchItemWriter<AcceptedOrder> writer) {

        return new StepBuilder("importOrdersStep", repository)
                .<RawOrder, AcceptedOrder>chunk(2, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .skip(InvalidOrderException.class)
                .skipLimit(2)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository repository,
            @Qualifier("importOrdersStep") Step step) {

        return new JobBuilder("importOrdersJob", repository)
                .start(step)
                .build();
    }
}
```

Trong cấu hình trên:

- `@StepScope` cho reader và processor giúp nhận `JobParameters` của lần thực thi cụ thể; không cố đọc tham số quá sớm khi tạo singleton.
- Chunk size là **2** để test dễ quan sát commit/rollback trên các nhóm nhỏ; production phải được chọn dựa trên tải thực.
- `.skipLimit(2)` chỉ áp dụng cho `InvalidOrderException`. Không dùng `.skip(Exception.class)` vì nó có thể che lỗi JDBC và lỗi lập trình.
- Writer dùng `MapSqlParameterSource` rõ ràng để ánh xạ **Java record accessor** tới tham số SQL.
- Trong ứng dụng test chỉ có một `Job` là `importOrdersJob`; nếu nhiều job, test cần chỉ định bean đúng.

`FlatFileItemReader.linesToSkip(1)` **không xác thực header**. Test cần bổ sung preflight/header validation nếu dự án yêu cầu kiểm soát phiên bản schema đầu vào. Một job thực tế cũng cần xác định cách ghi reject/quarantine khi cho phép skip.

## 6. Chuẩn bị database test và fixture

`src/test/resources/application-test.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:orders_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Test tự chủ động chạy job; không cho Boot auto-launch khi nạp context.
spring.batch.job.enabled=false
spring.batch.jdbc.initialize-schema=always

# Chạy schema.sql của ứng dụng trong test database.
spring.sql.init.mode=always
```

`src/test/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS accepted_orders (
    source_batch_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL,
    PRIMARY KEY (source_batch_id, order_id)
);
```

Schema `BATCH_*` do Spring Boot khởi tạo khi cấu hình `spring.batch.jdbc.initialize-schema=always` với H2 trong ví dụ. Bảng `accepted_orders` do `schema.sql` tạo. Các bảng dữ liệu test cần **cô lập hoàn toàn khỏi production**.

### 6.1. Fixture đủ trường hợp để tính counter

`src/test/resources/fixtures/orders-mixed.csv`:

```csv
order_id,status,amount
o-001,ACTIVE,120.00
o-002,ACTIVE,BAD
o-003,CANCELLED,50.00
o-004,ACTIVE,75.00
o-005,ACTIVE,10.00
```

Kỳ vọng:

| Record | Xử lý | Kết quả |
| --- | --- | --- |
| `o-001` | Valid `ACTIVE` | Ghi 120.00 |
| `o-002` | `BAD` không parse thành số | Skip với `INVALID_AMOUNT` |
| `o-003` | `CANCELLED` | Filter, không ghi |
| `o-004` | Valid `ACTIVE` | Ghi 75.00 |
| `o-005` | Valid `ACTIVE` | Ghi 10.00 |

Với một lần chạy thành công, mô hình đếm mong đợi:

```text
readCount          = 5
processSkipCount   = 1
filterCount        = 1
writeCount         = 3
skipCount          = 1

5 input = 3 accepted + 1 rejected + 1 filtered
```

`src/test/resources/fixtures/orders-valid.csv`:

```csv
order_id,status,amount
o-101,ACTIVE,15.00
o-102,ACTIVE,24.00
```

`src/test/resources/fixtures/orders-too-many-invalid.csv`:

```csv
order_id,status,amount
o-201,ACTIVE,BAD
o-202,ACTIVE,BAD
o-203,ACTIVE,BAD
o-204,ACTIVE,20.00
```

Với `skipLimit(2)`, input thứ ba cần skip sẽ vượt ngưỡng, khiến step thất bại; không được coi đây là một lượt import thành công.

## 7. Unit test cho `ItemProcessor`

`OrderProcessorTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class OrderProcessorTest {

    private final OrderProcessor processor =
            new OrderProcessor("fixture-batch");

    @Test
    void activeOrderProducesAcceptedOrder() throws Exception {
        RawOrder input = new RawOrder(
                "o-001", "ACTIVE", "120.50");

        AcceptedOrder actual = processor.process(input);

        assertThat(actual).isEqualTo(new AcceptedOrder(
                "fixture-batch",
                "o-001",
                new BigDecimal("120.50")));
    }

    @Test
    void cancelledOrderIsFiltered() throws Exception {
        RawOrder input = new RawOrder(
                "o-002", "CANCELLED", "999.00");

        assertThat(processor.process(input)).isNull();
    }

    @ParameterizedTest
    @CsvSource({
        "o-003, ACTIVE, abc, INVALID_AMOUNT",
        "o-004, ACTIVE, -1, NON_POSITIVE_AMOUNT",
        "o-005, ACTIVE, 0, NON_POSITIVE_AMOUNT",
        "o-006, UNKNOWN, 10, UNSUPPORTED_STATUS"
    })
    void invalidOrdersHaveStableReasonCodes(
            String id, String status, String amount, String expectedCode) {

        assertThatThrownBy(() -> processor.process(
                new RawOrder(id, status, amount)))
                .isInstanceOf(InvalidOrderException.class)
                .hasMessage(expectedCode);
    }

    @Test
    void missingIdIsNotSilentlyFiltered() {
        assertThatThrownBy(() -> processor.process(
                new RawOrder("", "ACTIVE", "10")))
                .isInstanceOf(InvalidOrderException.class)
                .hasMessage("MISSING_ORDER_ID");
    }
}
```

Tại sao đây là unit test?

- Không dùng `@SpringBootTest` hoặc database.
- Input cố định, không lệ thuộc đồng hồ/mạng.
- Kiểm tra cả **happy path** và các nhánh lỗi có ý nghĩa nghiệp vụ.
- Chỉ kiểm tra **behavior của processor**: test này không chứng minh Spring Batch sẽ tăng `skipCount` khi exception xuất hiện, vì skip là cơ chế của fault-tolerant step.

Đừng gọi `processor.process(...)` rồi giả định mình đã test `JobRepository`, retry hay transaction. Những phần đó cần integration test.

## 8. Unit test vòng đời của `FlatFileItemReader`

Reader có trạng thái mở/đóng và phụ thuộc resource. Có thể test reader mà không tạo Spring context bằng cách xây reader trực tiếp và cấp `ExecutionContext`.

`OrderReaderTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

class OrderReaderTest {

    @TempDir
    Path tempDir;

    @Test
    void readsRowsThenReturnsNullAtEndOfFile() throws Exception {
        Path csv = tempDir.resolve("orders.csv");
        Files.writeString(csv, """
                order_id,status,amount
                o-001,ACTIVE,10.00
                o-002,CANCELLED,20.00
                """, StandardCharsets.UTF_8);

        FlatFileItemReader<RawOrder> reader =
                new FlatFileItemReaderBuilder<RawOrder>()
                        .name("readerUnderTest")
                        .resource(new FileSystemResource(csv))
                        .linesToSkip(1)
                        .delimited()
                        .names("order_id", "status", "amount")
                        .fieldSetMapper(f -> new RawOrder(
                                f.readString("order_id"),
                                f.readString("status"),
                                f.readString("amount")))
                        .build();

        try {
            reader.open(new ExecutionContext());

            assertThat(reader.read()).isEqualTo(
                    new RawOrder("o-001", "ACTIVE", "10.00"));
            assertThat(reader.read()).isEqualTo(
                    new RawOrder("o-002", "CANCELLED", "20.00"));
            assertThat(reader.read()).isNull();
        } finally {
            reader.close();
        }
    }
}
```

`@TempDir` tạo thư mục cô lập cho test và giúp không phụ thuộc file được đặt ở một đường dẫn tuyệt đối trên máy phát triển. Khi dùng reader có trạng thái, không quên **`open(...)` và `close()`**, và với restart test phải kiểm tra thêm `update(ExecutionContext)`/checkpoint theo reader thực tế.

Với `FlatFileItemReader` và `linesToSkip(1)`, test này chỉ xác nhận cơ chế parse hai dòng sau header. Nếu muốn bảo đảm tên cột đúng, cần test riêng cho **header validation** ở bước preflight; việc bỏ qua một dòng không tự kiểm tra nội dung dòng đó.

## 9. Integration test chạy toàn bộ job

`@SpringBatchTest` cung cấp công cụ tiện lợi để khởi chạy job/step và làm việc với test scope của Spring Batch. Kết hợp với `@SpringBootTest` để nạp application context, datasource, transaction manager và `JobRepository`.

Ví dụ `ImportOrdersJobIT.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class ImportOrdersJobIT {

    @Autowired
    private JobLauncherTestUtils jobs;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void prepare() {
        jobs.setJob(importOrdersJob);
        // Chỉ xóa dữ liệu ứng dụng trong database test cô lập.
        jdbc.update("DELETE FROM accepted_orders");
    }

    private JobParameters params(String fixture) throws Exception {
        Path file = Path.of(new ClassPathResource(
                "fixtures/" + fixture).getURI());

        return new JobParametersBuilder()
                .addString("inputFile", file.toString(), true)
                .addString("sourceBatchId",
                        "test-" + UUID.randomUUID(), true)
                .toJobParameters();
    }

    @Test
    void importsAcceptedRowsAndCountsSkipsAndFilters() throws Exception {
        JobExecution execution =
                jobs.launchJob(params("orders-mixed.csv"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        StepExecution step = execution.getStepExecutions()
                .stream()
                .filter(s -> "importOrdersStep".equals(s.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(step.getReadCount()).isEqualTo(5);
        assertThat(step.getProcessSkipCount()).isEqualTo(1);
        assertThat(step.getFilterCount()).isEqualTo(1);
        assertThat(step.getSkipCount()).isEqualTo(1);
        assertThat(step.getWriteCount()).isEqualTo(3);

        Integer saved = jdbc.queryForObject(
                "SELECT COUNT(*) FROM accepted_orders",
                Integer.class);
        assertThat(saved).isEqualTo(3);

        Double sum = jdbc.queryForObject(
                "SELECT SUM(amount) FROM accepted_orders",
                Double.class);
        assertThat(sum).isEqualTo(205.0);
    }

    @Test
    void failsWhenSkipLimitIsExceeded() throws Exception {
        JobExecution execution =
                jobs.launchJob(params("orders-too-many-invalid.csv"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);

        // Không coi các chunk đã commit trước khi FAILED là bản
        // dữ liệu hoàn chỉnh để downstream sử dụng.
    }

    @Test
    void completedInstanceCannotBeLaunchedAgainWithSameParameters()
            throws Exception {

        JobParameters sameParams = params("orders-valid.csv");

        JobExecution first = jobs.launchJob(sameParams);
        assertThat(first.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        assertThatThrownBy(() -> jobs.launchJob(sameParams))
                .isInstanceOf(
                        JobInstanceAlreadyCompleteException.class);
    }
}
```

**Giải thích về helper `params(...)`:**

- Mỗi test nhận `sourceBatchId` ngẫu nhiên để không trùng với `JobInstance` đã hoàn thành của test khác.
- Trong test *chạy lại cùng instance*, ta giữ nguyên đối tượng `sameParams`. Nếu tạo một bộ tham số mới, kết quả không còn kiểm tra đúng quy tắc duplicate instance.
- `ClassPathResource.getURI()` có thể chuyển thành `Path` trong môi trường test khi resource là file trên filesystem. Với executable JAR có resource đóng gói, cần cơ chế khác (ví dụ copy ra `@TempDir` hoặc đọc qua `Resource`).
- Test dùng `@BeforeEach` để xóa bảng đầu ra trong **database H2 test chuyên dụng**. Không thực hiện điều đó trên datasource chia sẻ với môi trường khác.

**Vì sao phải kiểm tra cả DB?** `BatchStatus.COMPLETED` và `writeCount=3` là metadata kỹ thuật. Truy vấn bảng xác nhận writer đã đưa đúng số record vào database. Với nghiệp vụ tài chính hoặc tổng hợp, nên so thêm **tổng tiền, khóa duy nhất, checksum và dữ liệu từng dòng**, thay vì chỉ số lượng.

Trong ví dụ, `120.00 + 75.00 + 10.00 = 205.00`. Kiểu `Double` được dùng để minh họa truy vấn tổng đơn giản; với ứng dụng tài chính nên lấy và so sánh **`BigDecimal`** để tránh sai số floating point.

### 9.1. Tên test và cấu hình Gradle

Gradle `test` mặc định thường phát hiện class có tên `*Test`, `*Tests` hoặc pattern được framework hỗ trợ; đối với lớp mang hậu tố `IT`, **cần bảo đảm cấu hình test task thực sự bao gồm nó** (hoặc đổi tên thành `ImportOrdersJobTest`). Nếu dùng một task riêng `integrationTest`, hãy cấu hình source set và classpath theo dự án. Không nên cho rằng hậu tố `IT` luôn được mọi Gradle setup tự động chạy.

Lệnh dùng trong dự án sau khi đã cấu hình phù hợp:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Các lệnh này được trình bày cho người học; khi thực hiện một lượt STEP 4 soạn Markdown, không cần chạy build hoặc Content QA.

## 10. Test riêng một step với `JobLauncherTestUtils`

Khi job có nhiều step như `validateSourceStep -> importOrdersStep -> publishStep`, đôi khi chỉ muốn tập trung vào `importOrdersStep`:

```java
JobExecution execution = jobs.launchStep(
        "importOrdersStep",
        params("orders-mixed.csv"));
```

`launchStep(...)` cho phép chạy một step trong ngữ cảnh kiểm thử do Spring Batch Test tạo, thay vì luôn chạy toàn bộ flow production. Nhưng cần nhớ:

1. Nó **không chứng minh** các step trước/sau đã được điều phối đúng.
2. Nếu step phụ thuộc vào `ExecutionContext` được step trước tạo, test phải cung cấp đúng dữ liệu ngữ cảnh tương ứng.
3. Kiểm tra step `COMPLETED` không thay cho test của toàn bộ job, đặc biệt khi có quality gate/publish.
4. Test step scope và tham số vẫn cần `JobParameters` hợp lệ.

Với `@SpringBatchTest`, Spring Batch Test còn cung cấp `StepScopeTestUtils` và `JobScopeTestUtils` để kiểm thử scoped beans trong ngữ cảnh giả lập. Chúng hữu ích khi bean dùng `@Value("#{jobParameters[...] }")`, `StepExecutionContext` hoặc `JobExecutionContext`. Tuy nhiên, unit test business rule thường **không cần** dựng một StepScope: hãy tách logic nghiệp vụ thành class thuần Java như `OrderProcessor` rồi khởi tạo trực tiếp.

## 11. Kiểm thử lỗi, rollback và `FAILED` đúng cách

Với chunk size 2, một exception ở cuối file có thể xảy ra **sau khi các chunk trước đã commit**:

```text
Chunk #1 -> COMMIT
Chunk #2 -> COMMIT
Chunk #3 -> FAIL

JobExecution = FAILED
DB có thể vẫn giữ output từ Chunk #1 và #2.
```

Không viết test dựa trên giả định “job `FAILED` thì bảng đích phải rỗng” nếu application đang ghi theo từng chunk transaction. Đó là kỳ vọng sai về transaction boundary.

Thay vào đó, test cần quyết định rõ:

- Nếu output là **staging**, các chunk đã commit có thể tồn tại nhưng không được publish.
- Nếu writer phải **idempotent**, retry/restart không được tạo thêm duplicate.
- Nếu policy đòi **all-or-nothing ở cấp batch**, cần một publish gate hoặc snapshot version; không thể chỉ dựa vào transaction của một chunk.
- Nếu skip được cấu hình, exception ở reader/processor/writer có thể dẫn tới `COMPLETED` với `skipCount > 0`, không tự động là `FAILED`.

Một cách tạo kịch bản lỗi có kiểm soát là dùng một test double chỉ ném exception ở một item/call cụ thể. Không phụ thuộc vào việc tắt database ngẫu nhiên hoặc dùng `Thread.sleep(...)` để “chờ lỗi”, vì test dễ flaky và khó tái hiện.

### 11.1. Tránh chỉ assert số lượng exception

Trong fault-tolerant step, rollback và retry có thể làm callback processor/writer được gọi nhiều lần. Ví dụ một `ItemProcessListener.onProcessError()` có thể ghi event cho một attempt lỗi dù item sau đó retry thành công. `SkipListener` phản ánh item thực sự được skip theo cơ chế framework. Do đó:

```text
Retry attempts != Skip count
Process error callback count != Number of finally rejected items
Rollback count != Number of invalid records
```

Test nên khẳng định **outcome cuối** bằng `StepExecution` counters, DB state và reject/audit store; nếu cần đo từng attempt, sử dụng counter riêng trong test double hoặc listener.

## 12. Kiểm thử restart cùng `JobInstance`

Restart là tình huống quan trọng hơn nhiều so với chỉ gọi lại một job thành công.

```text
JobInstance(importOrdersJob, sourceBatchId=v1)
  ├── JobExecution #1: FAILED
  └── JobExecution #2: COMPLETED (restart)
```

Nguyên tắc:

- Giữ **cùng identifying `JobParameters`** khi restart. Đổi `run.id` hoặc `sourceBatchId` identifying tạo instance mới.
- Giữ metadata của `JobRepository` và nguồn dữ liệu không thay đổi theo checkpoint.
- Kiểm tra writer/side effect có thể được thực hiện lại mà không tạo duplicate.
- Nếu file nguồn đã sửa từ v1 thành v2, thường nên dùng **phiên bản nguồn mới** và một quy trình replay, không áp checkpoint cũ lên file khác.

### 12.1. Kịch bản test fail-once

Một fixture nhỏ có thể ném lỗi trong lần chạy đầu rồi thành công ở lần restart:

```java
AtomicBoolean firstAttempt = new AtomicBoolean(true);

Tasklet failOnceTasklet = (contribution, chunkContext) -> {
    if (firstAttempt.getAndSet(false)) {
        throw new IllegalStateException("SIMULATED_TRANSIENT_FAILURE");
    }
    return RepeatStatus.FINISHED;
};
```

Đây là đoạn **fixture** để đăng ký vào một `Step` riêng trong test configuration, không phải một file Java độc lập. Cần import `AtomicBoolean`, `Tasklet`, `RepeatStatus`. Không dùng boolean trạng thái trong JVM để kiểm soát recovery thật; test double chỉ mô phỏng hai kết quả xác định.

Một test launch với cùng parameters có dạng:

```java
JobParameters sameParams = new JobParametersBuilder()
        .addString("sourceBatchId", "restart-fixture-v1", true)
        .toJobParameters();

JobExecution first = launcher.run(failOnceJob, sameParams);
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);

JobExecution second = launcher.run(failOnceJob, sameParams);
assertThat(second.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(second.getJobInstance().getId())
        .isEqualTo(first.getJobInstance().getId());
assertThat(second.getId()).isNotEqualTo(first.getId());
```

Đây là **trích đoạn integration test**: `launcher`, `failOnceJob` và bean `failOnceTasklet` phải được cấu hình trong một test application context dùng `JobRepository` bền vững suốt hai lượt chạy. Cần cô lập bộ parameters/metadata giữa các lần thực thi test, tránh `JobInstanceAlreadyCompleteException` từ test cũ.

Với job đọc file có checkpoint và writer JDBC, test restart đầy đủ phải kiểm tra thêm:

1. Một phần dữ liệu đã được commit trong execution đầu.
2. Execution đầu `FAILED` tại điểm xác định.
3. Execution mới chỉ tiếp tục phần cần làm, theo cơ chế checkpoint thực tế.
4. Không có duplicate business key và tổng output cuối được đối soát.
5. Bản dữ liệu được publish (nếu có) chỉ xuất hiện sau khi job hoàn tất và quality gate đạt.

## 13. Test `@StepScope`, `JobParameters` và metadata

Một số lỗi chỉ xuất hiện khi Spring tạo scoped bean ở thời điểm step chạy:

```java
@StepScope
@Bean
OrderProcessor orderProcessor(
        @Value("#{jobParameters['sourceBatchId']}")
        String sourceBatchId) { ... }
```

Nếu viết unit test trực tiếp `new OrderProcessor("fixture-batch")`, ta đã kiểm tra business rule nhưng **chưa** xác nhận biểu thức SpEL lấy đúng tên tham số. Integration test ở phần 9 kiểm tra luồng đó vì nó launch job với `sourceBatchId`.

Các ca test nên có:

| Tình huống | Điều mong đợi |
| --- | --- |
| Có đủ `inputFile` và `sourceBatchId` | Step tạo scoped beans và chạy được |
| Thiếu `sourceBatchId` | Step không xử lý âm thầm với key rỗng; báo lỗi rõ |
| `inputFile` không tồn tại | Reader mở resource thất bại và job/step không báo success |
| Lặp lại identifying params sau `COMPLETED` | Không tự tạo execution mới cho cùng instance |
| Dùng params khác cho ngày hoặc phiên bản mới | Tạo `JobInstance` mới khi quy tắc nhận diện thay đổi |
| `StepExecution` có exception | Lưu được status, counts và thông tin failure thích hợp |

`JobRepository` không nên được xóa bừa để “test dễ pass”. Nếu cần làm sạch metadata trong H2 test riêng, có thể dùng `JobRepositoryTestUtils` do `spring-batch-test` cung cấp và đảm bảo không có execution đang chạy. Với nhiều test chạy song song chia sẻ context/database, việc cleanup toàn bộ repository của một test có thể ảnh hưởng test khác; thường dễ hơn là **dùng identifying params riêng cho từng test** hoặc database/context cô lập.

## 14. Kiểm thử các dependency và điều kiện production

### 14.1. DB-specific integration bằng Testcontainers

H2 không mô phỏng chính xác mọi đặc tính của PostgreSQL/MySQL. Nếu production dùng PostgreSQL, các test quan trọng cần chạy trên PostgreSQL thật hoặc container tương đương để kiểm tra:

- Unique constraint và upsert trong writer.
- Transaction isolation, lock, deadlock, timeout và rollback.
- SQL dialect, kiểu dữ liệu, precision/scale và timezone.
- Paging query có `ORDER BY` ổn định khi restart.
- Hành vi connection pool dưới concurrency.

Testcontainers giúp khởi chạy database cô lập; cấu hình phụ thuộc phiên bản thư viện và môi trường CI có quyền dùng container. Không cần chuyển **mọi unit test** sang Testcontainers: chỉ các integration test phụ thuộc ngữ nghĩa database mới cần.

### 14.2. API dependency: mock để kiểm thử logic, stub server để kiểm tra contract

Nếu `ItemProcessor` gọi API đối tác:

- Unit test: mock gateway để kiểm tra request, mapping và exception classification.
- Integration test HTTP adapter: dùng stub server với response `200`, `400`, `429`, `503`, timeout và payload giới hạn.
- Test job: kiểm tra retry policy có giới hạn, không retry lỗi validation/permanent, không skip outage diện rộng.
- Test side effect: dùng **idempotency key ổn định**, xác minh retry/restart không tạo giao dịch trùng.

Không mock `JobRepository` trong integration test nếu mục tiêu là kiểm tra restart hoặc metadata thực. Một mock repository không cho thấy transaction, khóa đồng thời hay checkpoint thực tế.

### 14.3. Test kết quả nghiệp vụ, không chỉ trạng thái framework

Với data pipeline quan trọng, cần thêm đối soát:

```text
expected_source_count
  = accepted_count + rejected_count + filtered_count
```

Phép đếm chỉ đúng nếu một record nguồn được phân loại vào đúng một nhóm và không có nghiệp vụ tách/gộp record. Với upsert, aggregation hoặc nhiều bảng đầu ra, dùng một công thức đối soát khác phù hợp với business contract. Kiểm tra thêm tổng tiền, unique key và phiên bản nguồn.

Một job có thể `COMPLETED` dù đã skip một số item trong `skipLimit`. Nếu downstream yêu cầu không được thiếu, phải test **quality gate từ chối publish** khi reject vượt ngưỡng, mặc dù import step có thể hoàn tất theo fault-tolerance policy.

## 15. Tính độc lập và độ ổn định của test

Các nguồn gây flaky test thường gặp:

| Vấn đề | Vì sao hỏng | Cách xử lý |
| --- | --- | --- |
| Dùng cùng identifying params trong nhiều test | `JobInstanceAlreadyCompleteException` ngoài ý muốn | Tạo params riêng, giữ nguyên chỉ trong test duplicate/restart |
| Test chia sẻ database và cleanup toàn cục | Test này xóa metadata/output của test khác | DB/schema riêng, không chạy song song khi chưa cô lập |
| Dùng `Thread.sleep()` chờ async job | CI có thể nhanh/chậm khác nhau | `CountDownLatch` hoặc polling có timeout hữu hạn |
| So trạng thái `STARTING` chính xác ngay sau async launch | Race condition; job có thể đã `STARTED` | Kiểm tra tập trạng thái hợp lệ hoặc chờ final status |
| Dựa vào thứ tự record khi step multi-thread | Thứ tự completion không được bảo đảm | So kết quả theo key/tập dữ liệu |
| Test writer bằng mock nhưng muốn kiểm tra commit | Mock không có transaction | Integration test với DB thật |
| Không `close()` reader | Rò resource giữa các test | `try/finally`, lifecycle rõ ràng |
| Coi H2 giống PostgreSQL | Khác dialect/lock/isolation | Testcontainers cho SQL/transaction quan trọng |
| Assert exception message chứa raw input | Dễ lộ dữ liệu trong log/test artifacts | Mã lỗi an toàn và field đã thẩm định |
| Chỉ kiểm tra `COMPLETED` | Bỏ sót skip/filter/duplicate | Kiểm tra `StepExecution` và output |

### 15.1. Nếu job được launch bất đồng bộ

`JobLauncher.run(...)` với `ThreadPoolTaskExecutor` có thể trả về khi job còn `STARTING` hoặc `STARTED`. Test không nên lập tức assert `COMPLETED`. Có thể poll `JobExplorer.getJobExecution(executionId)` tới trạng thái cuối với timeout rõ, và fail test nếu quá hạn.

```text
launch async
    |
    v
JobExecution id
    |
    +--> poll / JobExplorer
             |
             +-- STARTING / STARTED -> tiếp tục theo dõi
             +-- COMPLETED ---------> xác minh output
             +-- FAILED / STOPPED --> kiểm tra error path
```

Khi test job bằng `JobLauncherTestUtils`, cấu hình launcher đồng bộ thường đơn giản hơn và làm kết quả xác định. Chỉ dùng async test khi **hành vi asynchronous** thật sự là yêu cầu cần kiểm chứng.

## 16. Quy trình chạy test trong CI

Một workflow đơn giản của dự án:

```text
Pull request
  |
  v
Compile + unit tests
  |
  +-- OrderProcessorTest
  +-- OrderReaderTest
  |
  v
Integration tests
  |
  +-- ImportOrdersJob test
  +-- Skip-limit failure test
  +-- Restart/idempotency test
  |
  v
Quality / security checks
  |
  v
Build artifact
```

Với dự án lớn, có thể tách `test` và `integrationTest` thành hai Gradle tasks để test nhanh chạy trước, test database/container chạy sau. Dù tách task thế nào, cần **kiểm tra report của CI thực sự có tên các integration test**, tránh tình huống đặt hậu tố `IT` nhưng task `test` không phát hiện class.

Không commit credentials thật hoặc dữ liệu người dùng vào fixture. Chỉ sử dụng dữ liệu tổng hợp; nếu cần kiểm tra redaction/logging, dùng marker giả được thiết kế cho test và kiểm tra marker không xuất hiện trong log output.

## 17. Bài thực hành mở rộng

Sau khi chạy được ví dụ CSV → DB, hãy mở rộng bài tập:

1. **Unit test processor:** bổ sung kiểm tra `null`, chuỗi rỗng, trạng thái không hỗ trợ, amount rất lớn và decimal precision theo quy tắc nghiệp vụ.
2. **Unit test reader:** dùng `@TempDir` tạo file thiếu cột, file rỗng, line có ký tự Unicode và xác nhận parse/EOF/resource lifecycle.
3. **Integration test skip:** chạy fixture có một invalid record và so sánh `readCount`, `processSkipCount`, `filterCount`, `writeCount` với bảng output.
4. **Integration test vượt ngưỡng:** ba invalid records với `skipLimit(2)` phải khiến step/job `FAILED`; xác nhận không publish dữ liệu dở.
5. **Duplicate instance:** launch lại cùng identifying parameters sau `COMPLETED`, quan sát exception của `JobRepository`.
6. **Restart:** tạo fail-once writer/tasklet, giữ nguyên identifying params, xác nhận execution ID mới và output không trùng.
7. **Transaction:** cố tình làm writer lỗi sau một số chunk đã commit, kiểm tra dữ liệu staging và cơ chế rollback từng chunk.
8. **Quarantine:** gắn `SkipListener` ghi reject có reason code; so khớp số reject bền vững với skip metadata.
9. **Data quality gate:** thêm ngưỡng tỷ lệ lỗi, yêu cầu tổng record từ manifest và chỉ publish khi đối soát đạt.
10. **SQL integration:** chạy cùng job với PostgreSQL Testcontainers; kiểm tra unique constraint, transaction và restart ngoài H2.
11. **Concurrency:** thử multi-threaded step với reader/writer thread-safe, xác nhận mỗi business key được ghi đúng một lần, không dựa vào thứ tự log.
12. **Async launch:** nếu ứng dụng dùng REST API, test `202 Accepted` chỉ là submission; poll tới trạng thái cuối và kiểm tra cả failure outcome.

## 18. Tổng kết

Khi viết test cho Spring Batch, hãy chọn **mức kiểm thử khớp với điều cần chứng minh**:

- **Unit test** xác nhận business rules của processor, mapper và policy nhanh, độc lập, dễ tái hiện.
- **Integration test** xác nhận hành vi thực của step/job, metadata, transaction, skip, restart và JDBC writer.
- **Dữ liệu đầu ra** phải được kiểm tra bằng business key, tổng và điều kiện chất lượng, không chỉ bằng `BatchStatus`.
- **Restart/replay** phải được test bằng identifying parameters ổn định, nguồn bất biến và writer có idempotency.
- **Test environment** phải cô lập, không xóa metadata dùng chung hoặc phụ thuộc timing ngẫu nhiên.

Một bộ test tốt không chỉ trả lời “job có chạy hay không”, mà còn trả lời **mỗi item đã đi đâu, dữ liệu nào được commit, khi lỗi thì có thể khôi phục thế nào và khi nào output đủ tin cậy để downstream sử dụng**.
