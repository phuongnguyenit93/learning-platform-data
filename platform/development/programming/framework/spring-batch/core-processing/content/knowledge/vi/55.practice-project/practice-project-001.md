# Dự án thực hành: Tạo job đọc file CSV và ghi database bằng Spring Batch

## 1. Mục tiêu và kết quả cần đạt

Trong bài thực hành này, chúng ta xây dựng một ứng dụng **Spring Boot + Spring Batch** hoàn chỉnh để đọc đơn hàng từ file CSV, kiểm tra dữ liệu và ghi các record hợp lệ vào database bằng một **chunk-oriented step**. Đây là ví dụ đầu-cuối từ cấu trúc project đến cách khởi chạy, kiểm tra output, xử lý lỗi và thử nghiệm khả năng restart.

Sau khi hoàn thành, bạn có thể:

1. Tạo một project Spring Boot với dependency Spring Batch, JDBC và H2.
2. Định nghĩa bảng nghiệp vụ và bảng metadata của Spring Batch.
3. Đọc CSV theo từng item bằng `FlatFileItemReader`.
4. Kiểm tra và chuyển đổi dữ liệu bằng `ItemProcessor`.
5. Ghi theo lô vào database bằng `JdbcBatchItemWriter`.
6. Tạo `Step` với `chunk(size, transactionManager)` và ghép thành `Job`.
7. Nhận `inputFile`, `businessDate` qua `JobParameters`, không hardcode input.
8. Chạy thử job, kiểm tra `BatchStatus`, các bộ đếm và dữ liệu trong bảng output.
9. Viết test với `spring-batch-test`, xử lý tình huống sai schema hoặc sai nghiệp vụ.
10. Giải thích restart, checkpoint và idempotency để mở rộng demo thành hệ thống vận hành thực tế.

**Phạm vi kỹ thuật:** ví dụ sử dụng Java 17, Spring Boot 3.x, Spring Batch 5.x và Maven. Phiên bản Maven parent được nêu cụ thể như một phiên bản minh họa của nhánh Boot 3; nếu dự án sử dụng bản Boot/Spring Batch khác, hãy giữ bộ dependency và API tương thích. H2 in-memory được dùng để học và chạy test, **không phải cấu hình lưu trữ metadata bền vững cho production**.

## 2. Bài toán nghiệp vụ

Hệ thống nhận file đơn hàng của một ngày:

```text
inbound/orders-2026-11-16.csv
```

Nội dung CSV:

```csv
order_id,customer_code,amount,order_date
ORD-001,C001,120.50,2026-11-16
ORD-002,C002,45.00,2026-11-16
ORD-003,C001,399.90,2026-11-16
ORD-004,C003,12.75,2026-11-16
ORD-005,C004,80.00,2026-11-16
```

Quy tắc xử lý:

- Header phải khớp đúng `order_id,customer_code,amount,order_date`.
- File nằm trong thư mục inbound được cấu hình phía server, không cho truy cập đường dẫn tùy ý.
- `order_id` và `customer_code` không được rỗng.
- `amount` phải lớn hơn 0.
- `order_date` phải bằng `businessDate` của job.
- Mỗi `order_id` chỉ xuất hiện một lần trong bảng đích; database bảo vệ bằng khóa chính.
- Khi có lỗi validation, phiên bản đầu tiên của bài thực hành **fail fast**, không âm thầm bỏ qua item.
- Với dữ liệu hợp lệ, job kết thúc `COMPLETED` và ghi đúng năm dòng.

Output mong muốn:

| order_id | customer_code | amount | order_date |
| --- | --- | ---: | --- |
| ORD-001 | C001 | 120.50 | 2026-11-16 |
| ORD-002 | C002 | 45.00 | 2026-11-16 |
| ORD-003 | C001 | 399.90 | 2026-11-16 |
| ORD-004 | C003 | 12.75 | 2026-11-16 |
| ORD-005 | C004 | 80.00 | 2026-11-16 |

## 3. Kiến trúc tổng thể của job

```text
                 CLI / Scheduler
                       |
                       v
             JobParametersValidator
             - inputFile required
             - businessDate yyyy-MM-dd
                       |
                       v
                  importOrdersJob
                       |
                       v
                preflightStep
                   (Tasklet)
              - approved input root
              - file exists/readable
              - header/size checks
                       |
                       v
               importOrdersStep
              (chunk-oriented)
                       |
               FlatFileItemReader
                       |
                OrderCsvRow
                       |
                 ItemProcessor
           - validate order fields
           - validate businessDate
                       |
                 ImportedOrder
                       |
                JdbcBatchItemWriter
                       |
                  H2 database
                       |
                 commit mỗi chunk
```

Đây là ví dụ cố ý kết hợp **tasklet** và **chunk**:

- `preflightStep` kiểm tra một file trước khi xử lý. Công việc có phạm vi rõ ràng nên dùng tasklet.
- `importOrdersStep` lặp qua từng record, cần transaction theo nhóm và checkpoint nên dùng chunk.

Nếu preflight thất bại, step import không được chạy trong flow thành công thông thường. Khi một chunk import thất bại, các chunk đã commit trước đó có thể vẫn tồn tại; vì vậy **khóa chính, snapshot input và trạng thái repository** sẽ quan trọng khi restart.

## 4. Chuẩn bị môi trường và cấu trúc project

Yêu cầu:

- JDK 17 hoặc một JDK được Spring Boot 3.x hỗ trợ.
- Maven 3.9 hoặc Maven Wrapper tương ứng.
- Một IDE hỗ trợ Java và Spring Boot.
- Không cần cài PostgreSQL cho phiên bản H2 in-memory.

Cấu trúc thư mục:

```text
orders-csv-batch/
├── pom.xml
├── inbound/
│   └── orders-2026-11-16.csv
├── src/
│   ├── main/
│   │   ├── java/com/example/ordersbatch/
│   │   │   ├── OrdersBatchApplication.java
│   │   │   ├── BatchCommandRunner.java
│   │   │   ├── config/
│   │   │   │   └── OrderImportConfiguration.java
│   │   │   ├── input/
│   │   │   │   └── ApprovedInputResolver.java
│   │   │   ├── model/
│   │   │   │   ├── OrderCsvRow.java
│   │   │   │   └── ImportedOrder.java
│   │   │   └── validation/
│   │   │       ├── InvalidOrderException.java
│   │   │       └── ImportParametersValidator.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── schema.sql
│   └── test/
│       ├── java/com/example/ordersbatch/
│       │   ├── OrderImportJobIT.java
│       │   └── ImportParametersValidatorTest.java
│       └── resources/inbound/
│           ├── orders-test.csv
│           └── orders-bad-header.csv
```

Các tên class và file trong bài là một project mẫu độc lập; chúng không yêu cầu bạn đọc hoặc sửa các project Spring Batch khác.

## 5. Khai báo dependency trong pom.xml

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-csv-batch</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>orders-csv-batch</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-batch</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.batch</groupId>
            <artifactId>spring-batch-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Vai trò các thư viện:

| Dependency | Mục đích |
| --- | --- |
| `spring-boot-starter-batch` | Spring Batch runtime, Job/Step, JobRepository, reader/writer builders |
| `spring-boot-starter-jdbc` | `DataSource`, `JdbcTemplate`, transaction JDBC |
| `h2` | Database nhúng cho demo và test |
| `spring-boot-starter-test` | JUnit 5, assertions và công cụ test Spring Boot |
| `spring-batch-test` | `@SpringBatchTest`, `JobLauncherTestUtils` và tiện ích kiểm thử batch |

Parent Boot quản lý version của các dependency thông qua dependency management. Không tự gắn một phiên bản Spring Batch không tương thích vào starter mà chưa kiểm tra compatibility. Trong dự án production, dùng một bản Boot 3.x còn được hỗ trợ theo chính sách của tổ chức; phiên bản `3.3.5` ở đây chỉ là mốc ví dụ để mô tả API Spring Batch 5.x.

## 6. Cấu hình DataSource, Spring Batch và schema

### 6.1. application.yml

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: orders-csv-batch
  datasource:
    url: jdbc:h2:mem:orders_demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  batch:
    input-root: ./inbound

logging:
  level:
    org.springframework.batch: INFO
    com.example.ordersbatch: INFO
```

Giải thích:

- `jdbc:h2:mem:orders_demo` tạo database trong bộ nhớ. Khi JVM kết thúc, metadata và bảng output **không còn**. Điều này đơn giản cho tutorial nhưng không phải lựa chọn của job production cần restart qua process.
- `DB_CLOSE_DELAY=-1` giúp database in-memory còn sống khi kết nối cuối cùng đóng trong quá trình JVM còn tồn tại.
- `spring.sql.init.mode=always` cho phép Spring Boot chạy `schema.sql` để tạo bảng nghiệp vụ.
- `spring.batch.jdbc.initialize-schema=always` tạo các bảng metadata `BATCH_*` trên database demo mới.
- `spring.batch.job.enabled=false` ngăn Boot tự launch job bằng cách mặc định; trong bài này chúng ta dùng một `ApplicationRunner` để chủ động nhận tham số CLI và chạy đúng một job.
- `app.batch.input-root` định nghĩa root nhập liệu phía server. Người gọi chỉ được cung cấp **tên file tương đối** bên trong root.

Không đặt `initialize-schema=always` như trên cho database production đang có metadata nếu cơ chế schema init có thể xung đột. Ở production, dùng schema migration (Flyway/Liquibase hoặc quy trình DBA) cho cả bảng nghiệp vụ lẫn bảng metadata Spring Batch.

### 6.2. schema.sql

Tạo `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS imported_order (
    order_id       VARCHAR(80) PRIMARY KEY,
    customer_code  VARCHAR(80) NOT NULL,
    amount         DECIMAL(18, 2) NOT NULL,
    order_date     DATE NOT NULL,
    imported_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

`order_id` là khóa chính để chặn việc ghi cùng mã đơn nhiều lần. `DECIMAL(18,2)` phù hợp số tiền chính xác hai chữ số thập phân; ứng dụng Java sử dụng `BigDecimal`, không dùng `double` để tính tiền.

**Hai nhóm bảng khác nhau:**

1. `imported_order` là **bảng nghiệp vụ** do `schema.sql` định nghĩa.
2. `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, bảng `ExecutionContext` và các sequence liên quan là **metadata Spring Batch**, do schema của framework khởi tạo.

Không sửa/xóa metadata batch tùy tiện để “chạy lại”, vì nó phục vụ nhận diện `JobInstance`, lịch sử status và restart.

## 7. Tạo lớp main của Spring Boot

`src/main/java/com/example/ordersbatch/OrdersBatchApplication.java`:

```java
package com.example.ordersbatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersBatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersBatchApplication.class, args);
    }
}
```

`@SpringBootApplication` tự phát hiện `@Configuration` và các component trong package con `com.example.ordersbatch`. Bạn không cần tự xây `JobRepository` nếu auto-configuration đã cung cấp phù hợp với `DataSource` và Spring Batch version đang dùng.

## 8. Model: tách record CSV với đối tượng ghi database

### 8.1. OrderCsvRow.java

```java
package com.example.ordersbatch.model;

import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderCsvRow(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDate orderDate
) {}
```

`OrderCsvRow` đại diện cho dữ liệu đã được parser chuyển từ CSV sang Java. Nó không nhất thiết là entity JPA và không cần annotation ORM. Việc dùng `record` giúp tạo object dữ liệu ngắn gọn, bất biến.

### 8.2. ImportedOrder.java

```java
package com.example.ordersbatch.model;

import java.math.BigDecimal;
import java.time.LocalDate;

public record ImportedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDate orderDate
) {}
```

Trong ví dụ đơn giản, hai kiểu có cùng trường nhưng **khác vai trò**:

- `OrderCsvRow`: dữ liệu đầu vào từ file, có thể chưa qua kiểm tra.
- `ImportedOrder`: record đã được processor xác thực và chuẩn hóa, đủ điều kiện chuyển cho writer.

Trong ứng dụng thực tế, kiểu output có thể thêm source ID, phiên bản, timestamp nghiệp vụ hoặc thông tin tra cứu khách hàng.

## 9. Định nghĩa lỗi dữ liệu cho processor

`src/main/java/com/example/ordersbatch/validation/InvalidOrderException.java`:

```java
package com.example.ordersbatch.validation;

public final class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Sử dụng exception riêng giúp phân biệt lỗi **dữ liệu** với lỗi **hạ tầng/bug**. Ở phiên bản đầu của project, mọi lỗi validation sẽ làm step `FAILED`; phần mở rộng sẽ minh họa cách cho phép skip có kiểm soát.

## 10. Xác thực JobParameters trước khi khởi chạy

Một batch nhập file phải được biết nó xử lý **file nào và thuộc kỳ nghiệp vụ nào**. Hai tham số:

```text
inputFile=orders-2026-11-16.csv
businessDate=2026-11-16
```

Trong Spring Batch 5.x, ta có thể triển khai `JobParametersValidator`.

`src/main/java/com/example/ordersbatch/validation/ImportParametersValidator.java`:

```java
package com.example.ordersbatch.validation;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class ImportParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters == null) {
            throw new JobParametersInvalidException(
                    "JobParameters must not be null");
        }

        String inputFile = parameters.getString("inputFile");
        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFile is required");
        }

        String dateText = parameters.getString("businessDate");
        if (dateText == null || dateText.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        try {
            LocalDate.parse(dateText);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use yyyy-MM-dd");
        }
    }
}
```

Validator này kiểm tra **định dạng tham số**, chưa mở file. Đó là chủ ý: hoạt động I/O như kiểm tra file và schema nên nằm trong `preflightStep` để xuất hiện như một `StepExecution` với status có thể theo dõi.

Job parameters có thể chứa cả thông tin nhận diện instance và tham số bổ sung. Chỉ những tham số đánh dấu **identifying** mới tạo identity của `JobInstance`; giữ chúng ổn định khi cần restart cùng instance.

## 11. Giới hạn đường dẫn input trong thư mục inbound

Không nên tạo `FileSystemResource` trực tiếp từ một đường dẫn tuyệt đối do người gọi tùy ý truyền vào. Trong project này, caller chỉ được truyền tên tương đối. `ApprovedInputResolver` đưa đường dẫn về root đã cấu hình và kiểm tra symlink không trỏ ra ngoài root.

`src/main/java/com/example/ordersbatch/input/ApprovedInputResolver.java`:

```java
package com.example.ordersbatch.input;

import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class ApprovedInputResolver {

    private final Path inputRoot;

    public ApprovedInputResolver(
            @Value("${app.batch.input-root}") String configuredRoot)
            throws IOException {

        inputRoot = Path.of(configuredRoot).toRealPath();
        if (!Files.isDirectory(inputRoot)) {
            throw new IllegalStateException(
                    "Input root must be a directory");
        }
    }

    public Path resolve(String inputFile) throws IOException {
        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("inputFile is required");
        }

        Path supplied = Path.of(inputFile);
        if (supplied.isAbsolute()) {
            throw new SecurityException(
                    "Absolute input path is not allowed");
        }

        Path candidate = inputRoot.resolve(supplied).normalize();
        if (!candidate.startsWith(inputRoot)) {
            throw new SecurityException("Input path escapes inbound root");
        }

        Path realFile = candidate.toRealPath();
        if (!realFile.startsWith(inputRoot)) {
            throw new SecurityException("Input symlink escapes inbound root");
        }
        if (!Files.isRegularFile(realFile)) {
            throw new IllegalArgumentException(
                    "Input is not a regular file");
        }
        if (!Files.isReadable(realFile)) {
            throw new AccessDeniedException(realFile.toString());
        }
        return realFile;
    }
}
```

**Vì sao cần bảo vệ input root?** Một job thường chạy với service account có quyền trên nhiều file nội bộ. Nếu người gọi được cung cấp `../../secrets/file`, việc đọc input có thể biến thành path traversal.

**Giới hạn của ví dụ:** `toRealPath()` và `Files.isReadable()` kiểm tra ở thời điểm hiện tại. Nếu người khác có quyền thay file/symlink trước khi reader mở, có thể xảy ra *time of check vs time of use* (TOCTOU). Trong production, dùng staging snapshot bất biến, giới hạn quyền ghi của producer và gắn version/hash vào source identity.

Tạo thư mục `inbound/` trước khi chạy application vì resolver kiểm tra nó ngay lúc khởi tạo bean.

## 12. OrderImportConfiguration: tạo Job và hai Step

Đây là file cấu hình trung tâm của bài thực hành:

```text
config/OrderImportConfiguration.java
    ├── preflightTasklet(...)
    ├── preflightStep(...)
    ├── orderReader(...)
    ├── orderProcessor(...)
    ├── orderWriter(...)
    ├── importOrdersStep(...)
    └── importOrdersJob(...)
```

Để dễ theo dõi, các đoạn dưới đây cùng thuộc một lớp `@Configuration`; khi tạo file thật, ghép chúng **vào một class** với những import chung.

### 12.1. Khung class và import

`src/main/java/com/example/ordersbatch/config/OrderImportConfiguration.java`:

```java
package com.example.ordersbatch.config;

import com.example.ordersbatch.input.ApprovedInputResolver;
import com.example.ordersbatch.model.ImportedOrder;
import com.example.ordersbatch.model.OrderCsvRow;
import com.example.ordersbatch.validation.ImportParametersValidator;
import com.example.ordersbatch.validation.InvalidOrderException;
import java.io.BufferedReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import javax.sql.DataSource;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportConfiguration {
    // Dán các method @Bean ở các mục tiếp theo vào đây.
}
```

Các ví dụ tiếp theo là **method code bên trong class**, không phải các file Java độc lập. Không tạo nhiều class `OrderImportConfiguration` trùng tên.

### 12.2. preflightTasklet: kiểm tra file trước khi nhập

Thêm vào `OrderImportConfiguration`:

```java
@Bean
@StepScope
public Tasklet preflightTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) {

    return (contribution, context) -> {
        Path file = resolver.resolve(inputFile);

        if (Files.size(file) == 0) {
            throw new IllegalStateException("Input file is empty");
        }

        try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {

            String header = reader.readLine();
            if (!"order_id,customer_code,amount,order_date".equals(header)) {
                throw new IllegalStateException("Unexpected CSV header");
            }
            if (reader.readLine() == null) {
                throw new IllegalStateException("CSV contains no data rows");
            }
        }

        return RepeatStatus.FINISHED;
    };
}
```

Preflight:

- Nhận tên file từ job parameters khi step thực thi.
- Đưa file qua resolver để giới hạn phạm vi đọc.
- Từ chối file rỗng hoặc header không đúng.
- Yêu cầu ít nhất một dòng sau header.
- Trả `RepeatStatus.FINISHED` để cho phép flow tiếp tục khi hợp lệ.

Đoạn code dùng so sánh header chính xác theo contract demo. File có UTF-8 BOM hoặc header với khoảng trắng khác sẽ bị từ chối; nếu nghiệp vụ cho phép, có thể chuẩn hóa BOM hoặc dùng CSV parser để validate schema nâng cao. Điều kiện “có dòng sau header” chưa bảo đảm dòng ấy chứa dữ liệu hợp lệ; validation từng record sẽ do reader/processor đảm nhiệm.

### 12.3. preflightStep

```java
@Bean
public Step preflightStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet preflightTasklet) {

    return new StepBuilder("preflightStep", jobRepository)
            .tasklet(preflightTasklet, transactionManager)
            .build();
}
```

Tasklet phù hợp vì nó kiểm tra **một resource**, không cần lặp từng item. Nếu exception phát sinh trong preflight, step thường kết thúc `FAILED` và import step không chạy theo flow mặc định.

### 12.4. FlatFileItemReader: đọc CSV thành OrderCsvRow

```java
@Bean
@StepScope
public FlatFileItemReader<OrderCsvRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) throws Exception {

    Path approved = resolver.resolve(inputFile);

    return new FlatFileItemReaderBuilder<OrderCsvRow>()
            .name("orderCsvReader")
            .resource(new FileSystemResource(approved))
            .strict(true)
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("order_id", "customer_code", "amount", "order_date")
            .fieldSetMapper(fields -> new OrderCsvRow(
                    fields.readString("order_id"),
                    fields.readString("customer_code"),
                    fields.readBigDecimal("amount"),
                    LocalDate.parse(fields.readString("order_date"))
            ))
            .build();
}
```

**Cách hoạt động:**

1. `FlatFileItemReader` mở resource khi step bắt đầu.
2. `linesToSkip(1)` bỏ qua header đã được preflight xác nhận.
3. Delimited tokenizer tách các trường CSV theo cấu hình.
4. `FieldSetMapper` chuyển từng dòng thành `OrderCsvRow`.
5. Reader cung cấp một item mỗi lần `read()` cho Spring Batch, đến cuối file sẽ trả `null`.

`name("orderCsvReader")` giúp lưu state của reader trong `ExecutionContext` khi restart. `strict(true)` yêu cầu báo lỗi khi resource thiếu; không nên tắt chế độ nghiêm ngặt chỉ để job “không fail” nếu mất file.

**Lỗi parser khác lỗi processor:** nếu `amount` chứa chuỗi `abc` hoặc ngày không parse được, lỗi có thể xuất hiện từ `FieldSetMapper` trong quá trình đọc, **trước khi processor nhận item**. Vì vậy khi phân tích metadata, cần phân biệt `readSkipCount` với `processSkipCount`.

### 12.5. ItemProcessor: validation và chuẩn hóa

```java
@Bean
@StepScope
public ItemProcessor<OrderCsvRow, ImportedOrder> orderProcessor(
        @Value("#{jobParameters['businessDate']}") String businessDateText) {

    LocalDate businessDate = LocalDate.parse(businessDateText);

    return row -> {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("order_id is required");
        }
        if (row.customerCode() == null
                || row.customerCode().isBlank()) {
            throw new InvalidOrderException(
                    "customer_code is required for " + row.orderId());
        }
        if (row.amount() == null
                || row.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderException(
                    "amount must be positive for " + row.orderId());
        }
        if (!businessDate.equals(row.orderDate())) {
            throw new InvalidOrderException(
                    "order_date does not match businessDate for "
                            + row.orderId());
        }

        return new ImportedOrder(
                row.orderId().strip(),
                row.customerCode().strip(),
                row.amount().setScale(2),
                row.orderDate()
        );
    };
}
```

Vì processor trả `ImportedOrder`, item sẽ đến writer. Nếu trả `null`, Spring Batch hiểu đó là **filter có chủ đích**, không phải failure. Trong project này, dữ liệu vi phạm contract sẽ ném `InvalidOrderException` để job fail, tránh âm thầm mất record.

`setScale(2)` dùng chế độ làm tròn mặc định `UNNECESSARY`: nếu amount có hơn hai chữ số thập phân và không thể biểu diễn chính xác ở scale 2, Java có thể ném `ArithmeticException`. Đây là lựa chọn có chủ đích cho demo cần độ chính xác tiền tệ; khi hợp đồng nghiệp vụ cho phép làm tròn, hãy chỉ định `RoundingMode` rõ ràng.

### 12.6. JdbcBatchItemWriter: ghi nhiều item trong transaction

```java
@Bean
public JdbcBatchItemWriter<ImportedOrder> orderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ImportedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order
                    (order_id, customer_code, amount, order_date)
                VALUES
                    (:orderId, :customerCode, :amount, :orderDate)
                """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                            .addValue("orderId", row.orderId())
                            .addValue("customerCode", row.customerCode())
                            .addValue("amount", row.amount())
                            .addValue("orderDate", row.orderDate()))
            .build();
}
```

Writer dùng `MapSqlParameterSource` thay vì trông chờ ánh xạ JavaBeans của `record`. Cách viết này cho thấy rõ trường nào được bind vào SQL, phù hợp khi tên cột database khác tên field của model.

`JdbcBatchItemWriter` có thể gom các statement thành JDBC batch để tối ưu round-trip. Với `order_id` trùng, database sẽ báo lỗi khóa chính; chunk tương ứng có thể rollback. **Khóa chính không tự tạo chính sách upsert**: muốn nhận file lặp hoặc xử lý theo version, cần thiết kế riêng.

### 12.7. Chunk Step

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderCsvRow> orderReader,
        ItemProcessor<OrderCsvRow, ImportedOrder> orderProcessor,
        JdbcBatchItemWriter<ImportedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderCsvRow, ImportedOrder>chunk(3, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Chọn `chunk(3)` để dễ quan sát trong bài thực hành. Với năm item hợp lệ:

```text
Chunk 1: ORD-001, ORD-002, ORD-003 -> COMMIT
Chunk 2: ORD-004, ORD-005          -> COMMIT
```

Trong production, chunk size thường cần lớn hơn và được đo với throughput, transaction latency, memory và mức độ rollback; không có một giá trị tối ưu chung.

**Transaction quan trọng:** nếu item thứ tư gây lỗi và không có skip policy, chunk thứ nhất đã commit có thể vẫn tồn tại. Khi chạy lại, cần restart đúng `JobInstance` và giữ metadata; không đơn giản tạo job mới trên cùng bảng với primary key rồi mong hệ thống tự bỏ qua dữ liệu cũ.

### 12.8. Ghép Job và đăng ký validator

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step preflightStep,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(new ImportParametersValidator())
            .start(preflightStep)
            .next(importOrdersStep)
            .build();
}
```

Job chạy preflight trước, rồi import khi preflight thành công. `validator(...)` kiểm tra `inputFile`/`businessDate` theo contract, còn `StepExecution` của preflight ghi nhận việc kiểm tra resource thật.

## 13. Cách khởi chạy job từ command line

Vì `spring.batch.job.enabled=false`, Spring Boot không tự động chạy job. Chúng ta bổ sung `ApplicationRunner` để nhận hai option của ví dụ này, chuyển thành `JobParameters` và gọi `JobLauncher`.

`src/main/java/com/example/ordersbatch/BatchCommandRunner.java`:

```java
package com.example.ordersbatch;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class BatchCommandRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(BatchCommandRunner.class);

    private final JobLauncher launcher;
    private final Job importOrdersJob;

    public BatchCommandRunner(
            JobLauncher launcher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.launcher = launcher;
        this.importOrdersJob = importOrdersJob;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        // Trong SpringBootTest không truyền các option này:
        // chỉ dựng context, không tự launch job.
        if (!args.containsOption("inputFile")
                && !args.containsOption("businessDate")) {
            return;
        }

        String inputFile = required(args, "inputFile");
        String businessDate = required(args, "businessDate");

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", inputFile, true)
                .addString("businessDate", businessDate, true)
                .toJobParameters();

        JobExecution execution = launcher.run(importOrdersJob, params);
        log.info("Job execution id={}, status={}",
                execution.getId(), execution.getStatus());

        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                    "Import job did not complete: "
                            + execution.getStatus());
        }
    }

    private static String required(
            ApplicationArguments args, String name) {

        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0) == null
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Required CLI option --" + name + "=value");
        }
        return values.get(0);
    }
}
```

Hai tham số được đánh dấu `true` là **identifying parameters**. Tên job cùng tập identifying parameters xác định `JobInstance`. Khi cần restart một instance thất bại, phải dùng cùng identity; nếu đổi `businessDate` hoặc `inputFile`, bạn đang khởi chạy công việc logic khác.

**Giả định launcher synchronous:** runner trên kiểm tra `JobExecution.getStatus()` ngay sau `launch(...)`. Trong cấu hình Spring Batch thông thường với launcher đồng bộ, call trả về khi job đã kết thúc. Nếu dự án đổi sang launcher bất đồng bộ, runner cần chờ/quan sát execution qua `JobExplorer` hoặc cơ chế điều phối phù hợp trước khi kết luận status; không được kiểm tra trạng thái chưa kết thúc rồi báo fail sai.

Trong production, job có thể được gọi qua `JobOperator`, scheduler, orchestration platform hoặc message trigger. CLI runner ở đây phục vụ bài học và giữ điều kiện khởi chạy rõ ràng.

## 14. Chạy thử dự án

### 14.1. Chuẩn bị file

Tạo thư mục `inbound` ở thư mục gốc của project và lưu:

```text
inbound/orders-2026-11-16.csv
```

với đúng nội dung CSV trong mục 2. File nên dùng UTF-8, dấu phẩy làm delimiter và không có BOM trong ví dụ này. Root `./inbound` được resolve tương đối với working directory của process.

### 14.2. Build và chạy

Các lệnh dưới đây là hướng dẫn cho người học thực hiện trong project mẫu (không phải kết quả build đã được thực thi trong bài viết):

```bash
mvn clean package
java -jar target/orders-csv-batch-0.0.1-SNAPSHOT.jar \
  --inputFile=orders-2026-11-16.csv \
  --businessDate=2026-11-16
```

Trên PowerShell, có thể viết một dòng:

```powershell
java -jar target/orders-csv-batch-0.0.1-SNAPSHOT.jar --inputFile=orders-2026-11-16.csv --businessDate=2026-11-16
```

Đừng truyền `/srv/...` hoặc một đường dẫn ngoài `inbound` vì `ApprovedInputResolver` cố ý từ chối đường dẫn tuyệt đối và traversal.

### 14.3. Kết quả kỳ vọng

Khi file và cấu hình hợp lệ:

```text
importOrdersJob
  preflightStep      COMPLETED
  importOrdersStep   COMPLETED

JobExecution status = COMPLETED
readCount  = 5
writeCount = 5
filterCount = 0
skipCount  = 0
```

Các dòng log cụ thể có thể khác theo phiên bản và logging pattern. Đừng kiểm thử bằng việc so sánh nguyên văn toàn bộ log framework; tập trung vào trạng thái, metadata và nội dung database.

Vì H2 đang chạy trong bộ nhớ, sau khi process `java -jar` kết thúc thì database demo biến mất. Muốn quan sát row bằng SQL, hãy thêm một integration test dùng `JdbcTemplate`, hoặc mở H2 console/query **trong cùng JVM** với cơ chế phù hợp. Không nên kỳ vọng kết nối từ một process H2 mới sẽ nhìn thấy lại dữ liệu sau khi JVM cũ đã tắt.

## 15. Kiểm tra dữ liệu và metadata

Sau khi job chạy thành công trong một JVM đang hoạt động, query:

```sql
SELECT order_id, customer_code, amount, order_date
FROM imported_order
ORDER BY order_id;
```

Kỳ vọng có năm dòng ở mục 2. Có thể kiểm tra số lượng:

```sql
SELECT COUNT(*) AS total_orders
FROM imported_order;
```

Kỳ vọng `total_orders = 5`.

### 15.1. Metadata Spring Batch

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Và trạng thái các step:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

Với `preflightStep`, các bộ đếm read/write thường không đại diện cho số record CSV vì đó là tasklet. Các bộ đếm 5 read / 5 write thuộc `importOrdersStep`.

### 15.2. Vì sao cần cả metadata lẫn bảng nghiệp vụ?

`BatchStatus.COMPLETED` cho biết step/job đã hoàn tất theo flow, nhưng không tự chứng minh dữ liệu nghiệp vụ đúng. Reader có thể filter/skip item, writer có thể upsert hoặc database có trigger. Do đó cần cả:

- **Job/Step metadata:** status, thời gian, read/write/skip/filter counts.
- **Dữ liệu bảng đích:** số row thực tế, khóa nghiệp vụ, giá trị số tiền/ngày.
- **Đối soát:** số record theo manifest và tổng tiền nếu hợp đồng input yêu cầu.

## 16. Unit test validator của job

Tạo `src/test/java/com/example/ordersbatch/ImportParametersValidatorTest.java`:

```java
package com.example.ordersbatch;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.ordersbatch.validation.ImportParametersValidator;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

class ImportParametersValidatorTest {

    private final ImportParametersValidator validator =
            new ImportParametersValidator();

    @Test
    void acceptsCorrectParameters() {
        var params = new JobParametersBuilder()
                .addString("inputFile", "orders-2026-11-16.csv")
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        assertDoesNotThrow(() -> validator.validate(params));
    }

    @Test
    void rejectsMissingInputFile() {
        var params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        assertThrows(JobParametersInvalidException.class,
                () -> validator.validate(params));
    }

    @Test
    void rejectsWrongDateFormat() {
        var params = new JobParametersBuilder()
                .addString("inputFile", "orders.csv")
                .addString("businessDate", "16/11/2026")
                .toJobParameters();

        assertThrows(JobParametersInvalidException.class,
                () -> validator.validate(params));
    }
}
```

Đây là unit test thuần Java; không cần tạo database hoặc chạy Spring context. Nó xác định contract JobParameters trước khi chạy job.

## 17. Integration test: chạy job và kiểm tra database

Để test thật sự qua reader, processor, writer, JobRepository và transaction, sử dụng `@SpringBatchTest` với `@SpringBootTest`.

### 17.1. Chuẩn bị fixture

Tạo file `src/test/resources/inbound/orders-test.csv`:

```csv
order_id,customer_code,amount,order_date
TEST-001,C001,100.00,2026-11-16
TEST-002,C002,250.50,2026-11-16
TEST-003,C003,30.25,2026-11-16
```

Tạo file `src/test/resources/inbound/orders-bad-header.csv`:

```csv
order_id,wrong_customer_column,amount,order_date
BAD-001,C001,100.00,2026-11-16
```

`@SpringBootTest` sẽ dùng `app.batch.input-root=src/test/resources/inbound` cho test, thay vì file ở thư mục production/demo. Không cần sửa resource của main khi kiểm thử.

### 17.2. Lớp integration test

`src/test/java/com/example/ordersbatch/OrderImportJobIT.java`:

```java
package com.example.ordersbatch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "app.batch.input-root=src/test/resources/inbound",
        "spring.datasource.url=jdbc:h2:mem:orders_test;DB_CLOSE_DELAY=-1"
})
class OrderImportJobIT {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void clearBusinessOutput() {
        jdbc.update("DELETE FROM imported_order");
    }

    private JobParameters params(String file) {
        return new JobParametersBuilder()
                .addString("inputFile", file)
                .addString("businessDate", "2026-11-16")
                .addString("testExecution", UUID.randomUUID().toString())
                .toJobParameters();
    }

    @Test
    void importsThreeCsvOrders() throws Exception {
        JobExecution execution =
                launcher.launchJob(params("orders-test.csv"));

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
                .filter(s -> s.getStepName().equals("importOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(3, step.getReadCount());
        assertEquals(3, step.getWriteCount());
        assertEquals(0, step.getSkipCount());

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_order", Long.class);
        assertEquals(3L, count);

        String amount = jdbc.queryForObject(
                "SELECT CAST(amount AS VARCHAR) "
                        + "FROM imported_order WHERE order_id = ?",
                String.class,
                "TEST-002");
        assertTrue(amount.startsWith("250.5"));
    }

    @Test
    void badHeaderStopsJobBeforeImport() throws Exception {
        JobExecution execution =
                launcher.launchJob(params("orders-bad-header.csv"));

        assertEquals(BatchStatus.FAILED, execution.getStatus());
        assertTrue(execution.getStepExecutions().stream()
                .anyMatch(s -> s.getStepName().equals("preflightStep")
                        && s.getStatus() == BatchStatus.FAILED));
        assertTrue(execution.getStepExecutions().stream()
                .noneMatch(s -> s.getStepName().equals("importOrdersStep")));

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM imported_order", Long.class);
        assertEquals(0L, count);
    }
}
```

**Giải thích các lựa chọn test:**

- `@SpringBatchTest` tạo hạ tầng hỗ trợ khởi chạy và đọc metadata test.
- `@SpringBootTest` dựng ứng dụng thật với cấu hình database test và input root test.
- `spring.batch.job.enabled=false` ngăn Spring Boot auto-run mọi job khi context khởi động.
- `BatchCommandRunner` cũng không tự khởi chạy vì test không truyền hai option CLI của demo.
- `testExecution` ngẫu nhiên tạo identity riêng cho từng **bài test độc lập**, tránh va chạm `JobInstance` giữa những lần test. **Không dùng tham số ngẫu nhiên này khi kiểm thử restart cùng instance**, vì restart phải giữ đúng identity cũ.
- `DELETE FROM imported_order` dọn **bảng nghiệp vụ** trước mỗi bài test. Bảng metadata vẫn giữ các execution khác nhau; đây là tình huống kiểm thử độc lập, không phải restart.

Đoạn assert số tiền chuyển `DECIMAL` sang chuỗi chỉ để minh họa một phép đối chiếu output. Trong hệ thống thật, nên dùng `BigDecimal` qua JDBC và `compareTo(...)` hoặc `assertEquals` sau khi chuẩn hóa scale để kiểm tra giá trị tiền một cách rõ ràng hơn.

**Lưu ý về Maven Surefire:** Maven Surefire mặc định nhận các tên như `*Test.java`, nhưng class kết thúc bằng `*IT.java` có thể không được chạy bởi `mvn test` nếu chưa cấu hình plugin Failsafe hoặc include pattern. Để `mvn test` chạy lớp tích hợp này ngay trong demo, có thể đổi tên file/class thành `OrderImportJobTest`. Nếu giữ hậu tố `IT`, cấu hình `maven-failsafe-plugin` và chạy phase `verify`.

Ví dụ cấu hình Failsafe trong `pom.xml` (đặt bên trong `<plugins>`):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Sau đó người học có thể chạy `mvn verify` để thực thi cả unit và integration tests theo vòng đời Maven. Không cần chạy các lệnh build này để hiểu contract của bài.

## 18. Thử các tình huống failure

Hãy tạo các file test khác nhau và kiểm tra chính xác trạng thái:

| Dữ liệu đầu vào | Nơi lỗi xuất hiện | Kết quả kỳ vọng |
| --- | --- | --- |
| File không tồn tại | Resolver hoặc preflight | Step `preflightStep FAILED`, không có output |
| Header sai | Preflight | Job `FAILED`, import không chạy |
| File chỉ có header | Preflight | Bị từ chối vì không có dòng data |
| `amount=abc` | Reader/FieldSetMapper | `importOrdersStep FAILED` khi parse |
| `amount=-1` | Processor | `InvalidOrderException`, step fail |
| `order_date` sai định dạng | Reader | Parse error, step fail |
| `order_date` khác businessDate | Processor | Validation fail |
| `order_id` trùng trong một file | Writer/database | Khóa chính conflict, chunk fail |
| Đường dẫn `../secret.txt` | Resolver | Security rejection trước khi đọc |
| Tất cả record hợp lệ | Reader → processor → writer | `COMPLETED`, output khớp input |

### 18.1. Lỗi processor ở chunk thứ hai

Với `chunk(3)`, file năm record:

```text
1: ORD-001 OK
2: ORD-002 OK
3: ORD-003 OK
4: ORD-004 amount=-10
5: ORD-005 OK
```

Hành vi tổng quát trong cấu hình fail-fast, transaction JDBC thông thường:

```text
Chunk 1: ORD-001..003 -> COMMIT
Chunk 2: ORD-004     -> processor throws InvalidOrderException
         transaction của chunk không hoàn tất
Step: FAILED
```

Khi kiểm tra bảng đích, thường vẫn thấy ba dòng thuộc chunk đầu. Tuy nhiên, không nên suy đoán chỉ từ tên `FAILED` rằng luôn có đúng ba row trong mọi cấu hình: datasource, transaction manager, side effect của writer hoặc chiến lược retry có thể thay đổi kết quả. Kiểm tra database và `StepExecution` thật.

### 18.2. Phân biệt filter, skip và failure

- `processor.process(...)` trả object: item được chuyển cho writer.
- `processor.process(...)` trả `null`: item bị **filter**, tăng `filterCount`.
- Processor ném exception và không được xử lý: step có thể **FAILED**.
- Processor ném exception được phép skip: tăng `processSkipCount` theo policy fault-tolerant.

Đừng catch tất cả exception rồi `return null`: cách đó che giấu lỗi dữ liệu và làm job báo thành công dù record biến mất.

## 19. Mở rộng: cho phép skip có kiểm soát

Trong phiên bản đầu tiên, một record sai làm job fail. Nếu hợp đồng dữ liệu cho phép nhận phần hợp lệ và loại những dòng sai, hãy cấu hình **fault-tolerant step**.

Ví dụ thay đoạn builder của `importOrdersStep`:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderCsvRow, ImportedOrder>chunk(3, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(2)
        .build();
```

Khi còn hạn mức, một item bị `InvalidOrderException` có thể được skip và step tiếp tục. **Chỉ lỗi đúng loại được cấu hình mới được phép skip**. `skipLimit(2)` là giới hạn của step, không phải mỗi chunk. Nếu gặp nhiều lỗi hơn giới hạn, step fail.

Nếu reader parse sai `amount=abc`, exception có thể không phải `InvalidOrderException` nên vẫn fail. Muốn skip lỗi đọc phải thiết kế policy tương ứng, và tốt hơn nên có `SkipListener`/quarantine để không bỏ dữ liệu mà không có dấu vết.

Ví dụ listener:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipListener
        implements SkipListener<OrderCsvRow, ImportedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInProcess(OrderCsvRow item, Throwable error) {
        log.warn("Skipping orderId={}, reason={}",
                item.orderId(), error.getClass().getSimpleName());
    }
}
```

Đăng ký bằng `.listener(new OrderSkipListener())` trong cấu hình step. Khi audit dữ liệu thật, không ghi full payload nhạy cảm hoặc exception message chứa dữ liệu cá nhân; dùng error category và business key được phép.

**Quan trọng:** skip không phù hợp cho mọi nghiệp vụ. Với đối soát tài chính yêu cầu không thiếu một giao dịch nào, chính sách đúng có thể là **fail toàn lô**, đưa lô vào trạng thái cần sửa rồi xử lý lại sau khi được phê duyệt.

## 20. Retry và lỗi hạ tầng

Một lỗi dữ liệu như amount âm hoặc date sai thường không tự trở thành hợp lệ nếu retry cùng item. Nhưng network timeout hoặc database deadlock tạm thời có thể cần retry có giới hạn.

Đối với một dependency bên ngoài được processor sử dụng, có thể tạo exception loại:

```java
public final class TemporaryCatalogException extends RuntimeException {
    public TemporaryCatalogException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Sau đó cấu hình chunk:

```java
.faultTolerant()
.retry(TemporaryCatalogException.class)
.retryLimit(3)
```

Đoạn trên là phần nối tiếp của builder, không phải một statement độc lập. Chọn loại exception cụ thể, timeout và backoff theo downstream. Không cấu hình `retry(Exception.class)` cho mọi lỗi: retry bug hoặc input sai có thể gây lặp vô ích và tăng tải hệ thống.

**Tính lặp lại của processor:** rollback/retry có thể làm một item được process nhiều lần. Vì vậy tránh cho processor gọi API tạo thanh toán, gửi email hoặc ghi trạng thái không idempotent. Trong demo, processor chỉ kiểm tra và chuyển đổi dữ liệu, còn writer JDBC thực hiện ghi trong transaction của chunk.

## 21. Restart và xử lý lô đã commit một phần

### 21.1. JobInstance khác JobExecution

```text
Job: importOrdersJob
  |
  +-- JobInstance(inputFile=A, businessDate=D)
         |
         +-- JobExecution #101 FAILED
         |      preflightStep COMPLETED
         |      importOrdersStep FAILED
         |
         +-- JobExecution #102 COMPLETED (restart)
                importOrdersStep COMPLETED
```

Một `JobInstance` được nhận diện bằng tên job và identifying `JobParameters`. Một instance có thể có nhiều `JobExecution` khi fail rồi restart. Các StepExecution được tạo cho những step thực sự chạy lại.

Trong demo H2 in-memory, metadata **mất khi JVM dừng**. Bạn chỉ có thể thử restart trong **cùng vòng đời database còn tồn tại** hoặc đổi sang database bền vững. Trong production, database metadata phải giữ qua process restart.

### 21.2. Làm sao để restart an toàn?

1. Giữ đúng identifying parameters `inputFile` và `businessDate` của instance thất bại.
2. Giữ metadata `JobRepository` và `ExecutionContext` của lần chạy trước.
3. Giữ nội dung, thứ tự record và schema của input file đã checkpoint.
4. Cho reader lưu trạng thái với tên ổn định `orderCsvReader`.
5. Đảm bảo writer không tạo hiệu ứng ngoài ý muốn khi một chunk được xử lý lại.
6. Không xóa bảng metadata chỉ để chạy job mới.

**Sửa file trong lúc restart rất nguy hiểm.** Nếu processor fail vì dòng thứ tư amount âm, việc chỉnh file in-place có thể làm thay đổi byte stream hoặc thứ tự record đã được checkpoint. Với yêu cầu production nghiêm ngặt, dùng file bất biến theo version, đánh dấu lô bị reject và nhận một version mới để xử lý lại theo quy trình.

### 21.3. Chạy lại một job đã COMPLETED

Với cùng tên job và cùng identifying parameters, một `JobInstance` đã `COMPLETED` không được launch như một run mới thông thường. Spring Batch có thể ném `JobInstanceAlreadyCompleteException`.

Đổi `run.id` hoặc `businessDate` để cố chạy lại có thể tạo `JobInstance` khác, nhưng **không bảo đảm an toàn về dữ liệu**. Bảng `imported_order` vẫn có primary key; chạy lại cùng order IDs sẽ gây duplicate conflict nếu writer vẫn là `INSERT`.

Nếu nghiệp vụ cần rerun, hãy quyết định rõ:

- Chỉ ghi record chưa tồn tại (**idempotent insert/upsert**).
- Cho phép overwrite theo source version sau khi đối soát.
- Xóa/rebuild một partition hoặc một nguồn đã được phê duyệt.
- Từ chối xử lý lô lặp dựa trên `sourceId`/checksum.

Chính sách rerun là quyết định nghiệp vụ; không nên dựa vào việc xóa `BATCH_*`.

## 22. Chuyển từ H2 demo sang PostgreSQL production

H2 giúp học API, nhưng job production cần:

- Database bền vững cho nghiệp vụ và metadata Spring Batch.
- Schema migration có version.
- Quản lý transaction, connection pool và timeout.
- Chính sách khóa duy nhất và xử lý duplicate rõ ràng.
- Index phù hợp với query/reporting.
- Bảo mật connection, least privilege, secret management.
- Backup/retention và giám sát metadata.

Ví dụ các dependency cần thay đổi:

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Cấu hình production minh họa:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_batch_user
    password: <provided-by-secret-management>
  batch:
    jdbc:
      initialize-schema: never
  sql:
    init:
      mode: never
```

Đoạn YAML sử dụng placeholder **mang tính giải thích**, không phải password thật hoặc file cấu hình nên commit vào repository. Triển khai thực tế cần inject credential qua môi trường hoặc secret manager, cấu hình TLS theo yêu cầu, và tạo schema qua migration. Không chạy project production với quyền DBA chỉ để Spring Batch tạo các bảng metadata.

Trong PostgreSQL, một chiến lược tránh insert trùng khi rerun có thể dùng `INSERT ... ON CONFLICT` theo business key. Tuy nhiên, `DO NOTHING` sẽ bỏ qua duplicate; nếu duplicate khác nội dung so với dữ liệu cũ, việc bỏ qua có thể làm mất một thay đổi quan trọng. Phải xác định rõ contract dữ liệu trước khi chọn upsert.

Ví dụ SQL cho trường hợp **được phép bỏ qua bản ghi đã tồn tại**:

```sql
INSERT INTO imported_order
    (order_id, customer_code, amount, order_date)
VALUES
    (:orderId, :customerCode, :amount, :orderDate)
ON CONFLICT (order_id) DO NOTHING;
```

Khi dùng `DO NOTHING`, các số đếm `writeCount` ở Spring Batch không tự nhiên đồng nghĩa với số dòng mới thêm; cần query hoặc audit nếu muốn đo **inserted count** thực tế.

## 23. Vận hành, logging và quan sát

Những trường log hữu ích cho job nhập CSV:

```text
jobName
jobInstanceId
jobExecutionId
stepName
stepExecutionId
businessDate
sourceId / inputFile (đã kiểm soát)
batchStatus
readCount
writeCount
filterCount
readSkipCount
processSkipCount
writeSkipCount
rollbackCount
errorCategory
```

Không log raw CSV chứa dữ liệu nhạy cảm, credential hoặc đường dẫn bí mật. Có thể đưa `jobExecutionId`/`stepExecutionId` vào MDC của SLF4J để mọi log trong một execution có khóa correlation; nếu step chạy multi-thread, phải truyền MDC qua worker thread có kiểm soát.

Một số metric nên theo dõi:

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| Job success/failure theo ngày | Biết import có hoàn tất theo lịch |
| Duration của import step | Phát hiện batch chậm hoặc database bị quá tải |
| Read/write count | Theo dõi throughput và đối soát số dòng |
| Read/process/write skip | Phát hiện chất lượng dữ liệu xuống cấp |
| Rollback/retry | Phát hiện xung đột DB hoặc lỗi phụ thuộc |
| Last successful completion | Phát hiện job không chạy hoặc không hoàn tất |
| Input source age | Biết dữ liệu được nhận muộn |

Không dùng `orderId`, `sourceId` hoặc `stepExecutionId` có cardinality cao làm nhãn metric. Lưu ID chi tiết ở log/trace và tổng hợp metrics theo `jobName`, `stepName`, `status` hoặc các error category có số lượng hữu hạn.

## 24. Lỗi thường gặp khi làm dự án

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Application startup lỗi vì không thấy inbound | Chưa tạo thư mục `./inbound` hoặc working directory khác dự kiến | Tạo thư mục hoặc đặt root tuyệt đối từ cấu hình |
| Job không tự chạy | `spring.batch.job.enabled=false` và không truyền option CLI | Truyền cả `--inputFile` lẫn `--businessDate` |
| Job bị từ chối vì không thấy file | File ngoài approved input root hoặc tên file sai | Đặt file dưới `inbound` và truyền đường dẫn tương đối |
| CSV sai header | Tên hoặc thứ tự cột khác contract | Sửa nguồn/contract; không bỏ preflight tùy tiện |
| Error tại reader khi amount là chữ | Mapping `BigDecimal` không parse được | Chỉnh dữ liệu hoặc thiết kế quarantine/read skip |
| Error tại processor do amount âm | Vi phạm rule `amount > 0` | Sửa dữ liệu hoặc chọn skip policy có kiểm soát |
| Job FAILED ở chunk thứ hai nhưng DB có record | Chunk trước đã commit | Restart đúng instance và giữ checkpoint |
| Duplicate primary key | Rerun cùng business key hoặc input chứa trùng | Thiết kế idempotency/upsert và đối soát |
| `JobInstanceAlreadyCompleteException` | Chạy lại cùng identity đã hoàn thành | Không xóa repository; thiết kế rerun/version policy |
| Không thấy bảng `BATCH_*` | Batch schema init/migration thiếu | Khởi tạo schema phù hợp với DB và version |
| H2 không còn dữ liệu sau khi tắt app | Database là in-memory | Dùng test trong cùng JVM hoặc DB bền vững |
| `@StepScope` resolution fail | Gọi bean bên ngoài step context hoặc thiếu job parameters | Để framework chạy step và truyền tham số đúng |
| Reader báo không đọc được source | Quyền OS/volume/IAM, source biến mất | Kiểm tra danh tính process, mount, snapshot |
| Test integration không chạy khi `mvn test` | Class có hậu tố `IT` nhưng chưa cấu hình Failsafe | Dùng tên `*Test` hoặc cấu hình Failsafe và chạy `verify` |
| Job báo COMPLETED nhưng output sai | Filter/skip/write logic khác kỳ vọng | Assert dữ liệu bảng đích, không chỉ BatchStatus |

## 25. Bài tập mở rộng sau khi chạy demo

**Bài 1 — Validation nhiều trường.** Thêm `currency` và `country_code` vào CSV. Bắt buộc currency hợp lệ, amount dương và order date đúng kỳ. Đưa lỗi nghiệp vụ vào exception riêng.

**Bài 2 — Skip dữ liệu invalid.** Cho phép tối đa hai record lỗi validation, thêm `SkipListener` ghi quarantine/audit. Assert `processSkipCount` và xác nhận dữ liệu bị skip không xuất hiện trong bảng đích.

**Bài 3 — Duplicate source.** Chạy import với file có hai dòng cùng `order_id`. Quan sát unique constraint và transaction rollback. Sau đó thiết kế chính sách xử lý duplicate rõ ràng.

**Bài 4 — Restart thực sự.** Đổi H2 in-memory sang PostgreSQL hoặc H2 file-based có schema migration ổn định. Gây lỗi ở chunk thứ hai, giữ metadata, khôi phục nguyên nhân rồi restart cùng instance. Kiểm tra output không thiếu và không trùng.

**Bài 5 — File snapshot.** Tạo manifest chứa file name, businessDate, recordCount và checksum. Chặn job khi file khác checksum hoặc chưa được công bố READY.

**Bài 6 — Tối ưu chunk size.** Đưa input lên 100.000 dòng, so sánh `chunk(10)`, `chunk(100)` và `chunk(500)`. Ghi throughput, thời gian transaction và memory thay vì chỉ so thời gian tổng.

**Bài 7 — Đối soát.** Thêm tasklet cuối để kiểm tra số dòng và tổng tiền giữa nguồn và bảng staging. Không cho publish khi kết quả không khớp.

**Bài 8 — Scheduled job.** Thay CLI bằng scheduler hoặc orchestration. Định nghĩa expected schedule, businessDate theo timezone rõ ràng và cách phát hiện lô chưa tới.

**Bài 9 — Multi-source ingestion.** Thêm `sourceId` và `schemaVersion`; kiểm tra quyền truy cập source của từng tenant, lưu version và xác định policy rerun.

**Bài 10 — Quan sát và cảnh báo.** Thêm log correlation theo `jobExecutionId`/`stepExecutionId`, đo read/write/skip counts và cảnh báo khi import không hoàn tất đúng hạn.

## 26. Tóm lược luồng dự án

| Thành phần | Trách nhiệm |
| --- | --- |
| `JobParametersValidator` | Từ chối thiếu/sai `inputFile` hoặc `businessDate` |
| `ApprovedInputResolver` | Giới hạn input trong thư mục được cho phép |
| `preflightStep` | Kiểm tra file, header và điều kiện tối thiểu trước import |
| `FlatFileItemReader` | Đọc và parse từng CSV record |
| `ItemProcessor` | Kiểm tra rule nghiệp vụ, chuẩn hóa đầu ra |
| `JdbcBatchItemWriter` | Ghi các item hợp lệ vào database |
| `importOrdersStep` | Tổ chức reader → processor → writer theo transaction chunk |
| `importOrdersJob` | Điều phối flow và áp dụng validator |
| `JobRepository` | Lưu metadata JobInstance/JobExecution/StepExecution và checkpoint |
| `JobLauncher` | Khởi chạy job với bộ tham số xác định |
| Integration tests | Kiểm tra kết quả end-to-end, dữ liệu DB và lỗi preflight |

Trong thực tế, một ứng dụng Spring Batch tốt không chỉ “đọc được file và insert được row”. Nó còn cần **kiểm soát phiên bản đầu vào, lỗi dữ liệu, transaction, khả năng restart, quyền truy cập, chất lượng output và khả năng quan sát**. Dự án trên tạo nền tảng để mở rộng những yêu cầu đó mà vẫn giữ luồng xử lý rõ ràng.

### Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch Reference — JDBC Item Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html)
- [Spring Batch Reference — JobParameters và JobInstance](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — Late Binding và StepScope](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Boot Reference — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html)
