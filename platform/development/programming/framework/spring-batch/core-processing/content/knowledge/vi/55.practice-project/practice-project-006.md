# Dự án thực hành: Xử lý skip dữ liệu lỗi với báo cáo trong Spring Batch

## 1. Bối cảnh và kết quả cần đạt

Một job nhập dữ liệu không phải lúc nào cũng được phép dừng vì **một** dòng CSV sai. Ví dụ, nhà cung cấp gửi 100.000 đơn hàng vào cuối ngày: 99.990 dòng hợp lệ, một số dòng có số tiền âm, một số dòng ghi số tiền bằng chữ. Nếu toàn bộ job bị hủy vì vài bản ghi không quan trọng, hệ thống chậm cập nhật dữ liệu tốt. Ngược lại, nếu “bỏ qua cho xong” mà không ghi lại lỗi, dữ liệu sẽ âm thầm thiếu và khó đối soát.

Bài **Xử lý skip dữ liệu lỗi với báo cáo** là một dự án thực hành thuộc *Spring Batch Core Processing → Dự án thực hành*. Ta sẽ triển khai một pipeline có thể chạy và kiểm thử:

- Nhận file CSV đơn hàng đã sẵn sàng và có định danh bất biến.
- Đọc từng dòng bằng `FlatFileItemReader`, gắn số dòng vào item.
- Phân biệt lỗi **đọc/parse** với lỗi **kiểm tra nghiệp vụ**.
- Chỉ skip những exception đã được phép, với tổng ngưỡng skip hữu hạn.
- Ghi những item hợp lệ vào database bằng `JdbcBatchItemWriter`.
- Ghi từng sự kiện skip vào bảng **batch_rejects** cùng database transaction với chunk.
- Khi bước import thành công, tạo báo cáo văn bản gồm thống kê read/write/skip và danh sách dòng bị loại.
- Nếu vượt skip limit, job phải **FAILED**; không cố tạo một báo cáo nói rằng nhập thành công.
- Kiểm thử chính xác số bản ghi, số skip, báo cáo và các tình huống restart.

Các ví dụ sử dụng **Java 17, Spring Boot 3.x, Spring Batch 5.2.x, H2 và JUnit Jupiter**. Ở Spring Batch 6.x, API hoặc package của một số thành phần có thể thay đổi; cần xem tài liệu đúng phiên bản trước khi áp dụng.

### Sau bài này, bạn có thể

1. Hiểu sự khác biệt giữa `readSkipCount`, `processSkipCount`, `writeSkipCount` và `filterCount`.
2. Dùng `.faultTolerant().skip(...).skipLimit(...)` an toàn.
3. Dùng `SkipListener` để thu thập thông tin lỗi nhưng không lưu payload nhạy cảm.
4. Thiết kế báo cáo dựa trên `StepExecution` và dữ liệu reject đã commit.
5. Giải thích vì sao report ở file hệ thống và commit của `JobRepository` không có chung transaction.
6. Xây chiến lược restart/reconciliation không sinh report trùng và không mất thông tin lỗi.
7. Phân biệt lỗi dữ liệu có thể skip với lỗi hạ tầng, transaction hay lỗi bắt buộc phải dừng.

---

## 2. Yêu cầu nghiệp vụ của dự án

### 2.1. File đầu vào

Mỗi file đại diện một snapshot đã được chốt, có ID riêng như `orders-2026-11-15-v1`. Định dạng CSV:

```csv
order_id,customer_id,amount,currency
101,1001,120.50,USD
102,1002,-5.00,USD
103,1003,not_number,USD
104,1004,50.00,USD
105,1005,0.00,USD
106,1006,80.75,USD
107,1007,25.00,VND
108,1008,10.00,USD
```

Đánh số dòng theo file vật lý bắt đầu từ 1. Dòng 1 là header, tám dòng tiếp theo là dữ liệu:

| Dòng | order_id | Tình trạng | Hành động |
|---:|---:|---|---|
| 2 | 101 | Hợp lệ | Ghi vào bảng đích |
| 3 | 102 | `amount=-5.00`, không dương | Skip ở processor |
| 4 | 103 | `amount=not_number`, không parse được | Skip ở reader |
| 5 | 104 | Hợp lệ | Ghi vào bảng đích |
| 6 | 105 | `amount=0.00`, không dương | Skip ở processor |
| 7 | 106 | Hợp lệ | Ghi vào bảng đích |
| 8 | 107 | Hợp lệ | Ghi vào bảng đích |
| 9 | 108 | Hợp lệ | Ghi vào bảng đích |

**Kỳ vọng:** 5 record hợp lệ, 3 record bị skip.

### 2.2. Quy tắc validation

Một dòng hợp lệ phải đáp ứng:

- `order_id > 0`.
- `customer_id > 0`.
- `amount > 0`.
- `currency` nằm trong danh sách cho phép: `USD` hoặc `VND`.

Trong dự án, lỗi chuyển kiểu số được phát hiện tại **reader** và ánh xạ thành `FlatFileParseException`. Lỗi business rule được phát hiện tại **processor** và ánh xạ thành `InvalidOrderException`.

Nếu reader không đọc được cả file, database không kết nối được hoặc writer không ghi được dữ liệu, job **không** được skip lỗi đó theo policy của dự án.

### 2.3. Chính sách skip

- `skipLimit=3`: tổng cộng tối đa ba item lỗi thuộc các loại được phép.
- Những lỗi được phép: `FlatFileParseException` khi parse dòng và `InvalidOrderException` khi kiểm tra nghiệp vụ.
- Không skip lỗi JDBC writer, mất connection, schema database sai hoặc exception bất ngờ.
- Nếu có item lỗi thứ tư thuộc loại được phép, step phải thất bại vì đã vượt ngưỡng.
- Chỉ những lỗi đã đi qua cơ chế skip thành công mới được ghi là **reject đã commit**.
- Khi step import `COMPLETED`, tạo báo cáo cho snapshot tương ứng.
- Nếu import `FAILED`, giữ metadata và reject events đã commit để điều tra; không phát hành báo cáo thành công sai lệch.

### 2.4. Report cần có

Một file báo cáo đơn giản:

```text
SPRING BATCH IMPORT QUALITY REPORT
fileId=orders-2026-11-15-v1
importStatus=COMPLETED
readCount=7
writeCount=5
filterCount=0
readSkipCount=1
processSkipCount=2
writeSkipCount=0
totalSkipCount=3
persistedRejectCount=3

lineNumber,orderId,stage,errorCode,errorClass
3,102,PROCESS,NON_POSITIVE_AMOUNT,InvalidOrderException
4,,READ,PARSE_ERROR,FlatFileParseException
6,105,PROCESS,NON_POSITIVE_AMOUNT,InvalidOrderException
```

Vì một dòng lỗi parse **không tạo ra `RawOrder`**, `orderId` ở sự kiện READ có thể không biết; không tự trích ID bằng cách parse thủ công trên input đã được đánh dấu là không hợp lệ. Báo cáo vẫn xác định được dòng vật lý để đối chiếu với file gốc được giữ theo chính sách bảo mật.

Trong ví dụ, `readCount=7` vì Spring Batch chỉ đếm những item reader đã đọc thành công; dòng parse lỗi được đếm riêng ở `readSkipCount=1`. Hai item không qua validation vẫn đã được reader trả về, nên thuộc readCount nhưng không được writer ghi.

---

## 3. Kiến trúc ứng dụng

```text
Immutable CSV / JobParameters
     │ fileId, inputFile
     ▼
FlatFileItemReader<RawOrder>
     │
     ├── Parse exception ──────┐
     │                         │
     ▼                         │
OrderValidationProcessor       │
     │                         │
     ├── InvalidOrderException ┤
     │                         │
     ▼                         ▼
JdbcBatchItemWriter       SkipListener
     │                         │
     ▼                         ▼
imported_orders           batch_rejects
     │                         │
     └────────────┬────────────┘
                  │
          cùng JDBC DataSource
          cùng chunk transaction
                  │
                  ▼
          Step importOrdersStep
          read / write / skip counts
                  │
             COMPLETED?
           ┌──────┴───────┐
           │              │
          Có            Không
           │              └──► Job FAILED;
           ▼                    metadata và reject
      reportStep                đã commit vẫn tra cứu được
           │
           ▼
  *.report.txt (publish atomic)
           │
           ▼
      Job COMPLETED
```

**Tại sao không ghi reject thẳng ra file CSV trong `SkipListener`?** Vì callback có thể được gọi trong ngữ cảnh transaction đang commit; write vào filesystem không tự rollback cùng database. Nếu DB rollback nhưng file reject đã thêm dòng, báo cáo sẽ chứa “lỗi đã skip” mà thực tế chunk chưa commit. Ghi reject vào bảng cùng transaction trước, rồi xuất report sau khi import step hoàn tất giúp quản lý nhất quán hơn.

### 3.1. Ranh giới giao dịch

Trong demo, `imported_orders`, `batch_rejects` và metadata Spring Batch dùng **cùng H2 DataSource và transaction manager**. Dữ liệu reject được ghi thông qua `JdbcTemplate`, nên tham gia Spring-managed transaction hiện tại khi dùng cùng `DataSource`.

Nếu triển khai production dùng database A cho `JobRepository` và database B cho business output, hoặc dùng API/file/object storage để ghi reject, **không được tự giả định commit nguyên tử trên các hệ thống đó**. Khi đó cần transactional outbox, staging có khóa idempotency, reconciliation hoặc cơ chế giao dịch phân tán nếu thật sự cần và được hỗ trợ.

---

## 4. Cấu trúc dự án

Một cấu trúc tham khảo:

```text
batch-quality-demo/
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/batch/
│   │   │   ├── BatchQualityApplication.java
│   │   │   └── quality/
│   │   │       ├── RawOrder.java
│   │   │       ├── ValidatedOrder.java
│   │   │       ├── InvalidOrderException.java
│   │   │       ├── OrderValidationProcessor.java
│   │   │       ├── OrderRejectSkipListener.java
│   │   │       ├── RejectReportTasklet.java
│   │   │       └── OrderQualityJobConfiguration.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── schema.sql
│   │       └── input/orders-demo.csv
│   └── test/
│       └── java/com/example/batch/
│           └── OrderQualityJobIT.java
└── build/reports/batch-quality/  (được sinh khi chạy)
```

Trong thực tế, tệp input là một resource ngoài ứng dụng (SFTP, object storage, shared storage), được gửi qua `JobParameters`. File ở `resources` chỉ để học tập và tạo fixture test.

### 4.1. Dependency Gradle

Khi dự án đã dùng Spring Boot dependency management tương thích với Spring Batch 5.2:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.4'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'
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

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Version plugin trong ví dụ minh họa một nhánh Boot 3.x. Khi tạo dự án thực, chọn bộ phiên bản đang được hỗ trợ và tương thích; nếu dependency management quyết định Spring Batch khác 5.2, đối chiếu Javadoc của API đang dùng. Không ghép tùy ý Spring Batch 6.x với Boot 3.x.

### 4.2. Entry point

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchQualityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchQualityApplication.class, args);
    }
}
```

Annotation `@SpringBootApplication` quét các cấu hình trong package con `com.example.batch.quality`.

### 4.3. application.yml

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:quality;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
    driver-class-name: org.h2.Driver

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  sql:
    init:
      mode: always

app:
  batch:
    report-directory: "./build/reports/batch-quality"
```

Giải thích:

- `spring.batch.job.enabled=false` tránh tự chạy job tại startup; demo/test chủ động gọi `JobLauncher`.
- Spring Batch metadata schema được khởi tạo cho H2 demo.
- `schema.sql` dùng để tạo hai bảng business/reject.
- H2 in-memory chỉ phù hợp demo/test; restart sau khi JVM chết **không còn DB state**, nên production cần database metadata và business bền vững.
- Report directory được cấu hình; nên là đường dẫn thuộc vùng được kiểm soát quyền và không public.
- Các mục tạo schema tự động thuận tiện cho demo, không phải chính sách migration production.

### 4.4. schema.sql

```sql
CREATE TABLE IF NOT EXISTS imported_orders (
    file_id      VARCHAR(100) NOT NULL,
    order_id     BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    amount       DECIMAL(18, 2) NOT NULL,
    currency     VARCHAR(3) NOT NULL,
    PRIMARY KEY (file_id, order_id)
);

CREATE TABLE IF NOT EXISTS batch_rejects (
    file_id      VARCHAR(100) NOT NULL,
    line_number  INTEGER NOT NULL,
    order_id     BIGINT,
    stage        VARCHAR(20) NOT NULL,
    error_code   VARCHAR(50) NOT NULL,
    error_class  VARCHAR(100) NOT NULL,
    PRIMARY KEY (file_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_batch_rejects_file
    ON batch_rejects (file_id);
```

`PRIMARY KEY (file_id, line_number)` giúp một dòng của cùng snapshot không có nhiều reject record ngay cả khi listener được gọi lại ở một retry/restart. `PRIMARY KEY (file_id, order_id)` ở output tránh hai dòng hợp lệ cùng file và cùng order ID được ghi vào bảng như hai record.

Lưu ý: nếu có hai dòng CSV hợp lệ trùng `order_id`, writer sẽ nhận database constraint error; **demo chủ ý không skip lỗi writer**. Muốn xem duplicate input là lỗi dữ liệu có thể skip, nên tạo validation/dedup stage riêng trước writer hoặc xác định chính sách nghiệp vụ rồi kiểm thử, không chỉ thêm `.skip(DuplicateKeyException.class)` một cách mù quáng.

SQL `MERGE INTO ... KEY(...)` sử dụng ở listener bên dưới là cú pháp **H2**. Nếu đổi sang PostgreSQL, MySQL hoặc Oracle, cần thay bằng UPSERT tương ứng và giữ unique constraint/idempotency semantics.

---

## 5. Model và loại exception

### 5.1. RawOrder.java

```java
package com.example.batch.quality;

import java.math.BigDecimal;

public record RawOrder(
        int lineNumber,
        long orderId,
        long customerId,
        BigDecimal amount,
        String currency) {
}
```

`lineNumber` không phải một trường trong CSV, mà là số dòng vật lý do `LineMapper` nhận từ Spring Batch. Nhờ vậy, khi processor phát hiện lỗi, ta vẫn biết item xuất phát từ dòng nào.

### 5.2. ValidatedOrder.java

```java
package com.example.batch.quality;

import java.math.BigDecimal;

public record ValidatedOrder(
        int lineNumber,
        long orderId,
        long customerId,
        BigDecimal amount,
        String currency) {
}
```

Việc tách `RawOrder` và `ValidatedOrder` giúp phân biệt item **đã parse nhưng chưa xác nhận nghiệp vụ** với item **đã đi qua validation**. Trong dự án lớn có thể chuyển đổi sang entity/DTO khác; quan trọng là writer không được nhận item chưa hợp lệ theo contract.

### 5.3. InvalidOrderException.java

```java
package com.example.batch.quality;

public class InvalidOrderException extends RuntimeException {

    private final String code;

    public InvalidOrderException(String code) {
        super(code);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Dùng mã lỗi ổn định như `NON_POSITIVE_AMOUNT`, `INVALID_CUSTOMER_ID`, `UNSUPPORTED_CURRENCY` giúp báo cáo, thống kê và đối soát dễ hơn việc đưa toàn bộ exception message vào file.

Exception này đại diện cho **một item bị vi phạm quy tắc**. Nó không được dùng để che giấu lỗi hệ thống như `NullPointerException` trong processor, database timeout hay bug thuật toán.

---

## 6. Reader: parse CSV và giữ số dòng

Một `FlatFileItemReader` thông thường có thể cấu hình `.delimited().names(...)`. Nhưng nếu cần báo cáo số dòng khi processor phát hiện lỗi, ta phải giữ thông tin `lineNumber` trong model. Interface `LineMapper<T>` nhận cả chuỗi dòng và số dòng vật lý.

Đặt trong `OrderQualityJobConfiguration.java`:

```java
@Bean
@StepScope
FlatFileItemReader<RawOrder> rawOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "inputFile JobParameter is required");
    }

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer(",");
    tokenizer.setNames(
            "order_id", "customer_id", "amount", "currency");
    tokenizer.setStrict(true);

    LineMapper<RawOrder> lineMapper = (line, lineNumber) -> {
        FieldSet fs = tokenizer.tokenize(line);

        return new RawOrder(
                lineNumber,
                fs.readLong("order_id"),
                fs.readLong("customer_id"),
                fs.readBigDecimal("amount"),
                fs.readString("currency"));
    };

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("rawOrderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1)
            .lineMapper(lineMapper)
            .build();
}
```

Imports chính:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.LineMapper;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
```

### 6.1. Lỗi parse diễn ra thế nào?

Khi `fs.readBigDecimal("amount")` gặp `not_number`, mapping không tạo ra `RawOrder`. `FlatFileItemReader` bao lỗi trong `FlatFileParseException`, kèm số dòng và raw input. Ta cho phép skip **đúng loại lỗi** này, nên reader có thể chuyển sang dòng tiếp theo.

**Không log `FlatFileParseException.getInput()` khi file chứa PII/secret.** Dù API cung cấp raw input để chẩn đoán, báo cáo demo chỉ lưu số dòng và mã lỗi. Khi cần xem dữ liệu gốc, người có quyền có thể truy cập phiên bản file được lưu bảo mật.

### 6.2. CSV có dấu phẩy trong quoted field

`DelimitedLineTokenizer` hỗ trợ nhiều tình huống CSV thông thường, nhưng dữ liệu thực có thể có quoted newline, BOM, alternate encoding hoặc đặc tả khác. Nếu file có record nhiều dòng vật lý, `lineNumber` từ reader có thể là mốc dòng logic theo chính sách `RecordSeparatorPolicy`; cần quy định rõ thế nào là “dòng lỗi” trong report.

Với hợp đồng phức tạp, dùng parser/record separator phù hợp và thêm test cho quoted comma, escaped quote, nhiều dòng, header và encoding. Đừng thay bằng `String.split(",")` chỉ để tiết kiệm vài dòng code.

### 6.3. Vì sao strict(true)?

`strict(true)` khiến file input bắt buộc không tồn tại gây lỗi lúc mở reader. Đó là lỗi ở mức **dataset**, không phải một dòng dữ liệu lỗi được phép skip.

`strict(false)` có thể khiến file thiếu được coi là nguồn rỗng; với job nhập dữ liệu bắt buộc, như vậy có thể khiến job `COMPLETED` với zero record, che mất sự cố nhận file.

### 6.4. File phải bất biến khi restart

Một reader có state lưu vị trí đọc theo checkpoint. Nếu file bị sửa, chèn/xóa dòng trước checkpoint rồi restart, cùng `lineNumber` có thể trỏ sang record khác.

Trong project thực tế nên lưu:

```text
fileId           = orders-2026-11-15-v1
fileVersion      = version-id-from-storage
inputSha256      = ...
expectedRows     = ...
businessDate     = 2026-11-15
schemaVersion    = 1
```

Chỉ xử lý file đã READY và không thay đổi. Validation file-level cần chạy trước khi import, không coi `FlatFileParseException` là cách thay thế checksum/manifest.

---

## 7. Processor: validation phân biệt với filter

Tạo `OrderValidationProcessor.java`:

```java
package com.example.batch.quality;

import java.util.Set;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public class OrderValidationProcessor
        implements ItemProcessor<RawOrder, ValidatedOrder> {

    private static final Set<String> ALLOWED_CURRENCIES =
            Set.of("USD", "VND");

    @Override
    public ValidatedOrder process(RawOrder item) {

        if (item.orderId() <= 0) {
            throw new InvalidOrderException("INVALID_ORDER_ID");
        }

        if (item.customerId() <= 0) {
            throw new InvalidOrderException("INVALID_CUSTOMER_ID");
        }

        if (item.amount() == null
                || item.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "NON_POSITIVE_AMOUNT");
        }

        if (!ALLOWED_CURRENCIES.contains(item.currency())) {
            throw new InvalidOrderException(
                    "UNSUPPORTED_CURRENCY");
        }

        return new ValidatedOrder(
                item.lineNumber(),
                item.orderId(),
                item.customerId(),
                item.amount(),
                item.currency());
    }
}
```

Processor cố ý **throw exception có chủ đích** cho dữ liệu sai. Có một khác biệt rất quan trọng:

| Hành vi trong ItemProcessor | Spring Batch hiểu là | Counter |
|---|---|---|
| Trả item hợp lệ | Tiếp tục gửi writer | Có thể tăng writeCount sau commit |
| Trả `null` | **Filter**, không coi là lỗi | `filterCount` |
| Ném `InvalidOrderException` được cấu hình skip | **Skip** sau khi fault tolerance chấp nhận | `processSkipCount` |
| Ném exception không được phép skip | Step fail hoặc retry theo policy | Không tự tăng skipCount cho lỗi không được skip |
| Ném exception retryable | Retry theo cấu hình, có thể thành công hoặc hết retry | Retry attempt không đồng nhất với skipCount |

**Vì sao không trả `null` cho số tiền âm?** Vì trong yêu cầu dự án, dữ liệu sai phải có **báo cáo lỗi theo từng dòng**. Nếu trả `null`, Spring Batch coi là filter bình thường; `SkipListener.onSkipInProcess` không được gọi để ghi reject.

Filter phù hợp khi việc loại bỏ là nghiệp vụ bình thường và không cần xem nó là lỗi: ví dụ bỏ qua đơn hàng thuộc trạng thái không cần xuất báo cáo. Nếu vẫn cần theo dõi filtered item, phải có cơ chế riêng thay vì dùng skip report.

---

## 8. Writer: chỉ ghi item hợp lệ

Ví dụ `JdbcBatchItemWriter` đưa `ValidatedOrder` vào bảng `imported_orders`:

```java
@Bean
JdbcBatchItemWriter<ValidatedOrder> validOrderWriter(
        DataSource dataSource,
        @Value("#{null}") Object ignored) {

    return new JdbcBatchItemWriterBuilder<ValidatedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_orders
                    (file_id, order_id, customer_id, amount, currency)
                VALUES (?, ?, ?, ?, ?)
                """)
            .itemPreparedStatementSetter((item, ps) -> {
                // fileId được thiết kế là immutable theo job run.
                // Xem phiên bản writer @StepScope ở ngay bên dưới.
                throw new UnsupportedOperationException(
                        "Use step-scoped writer configuration");
            })
            .build();
}
```

**Trong project, hãy dùng phiên bản thật sau đây** (thay cho minh họa khung phía trên) để nhận `fileId` từ `JobParameters`. Không triển khai cả hai bean trùng tên.

```java
@Bean
@StepScope
JdbcBatchItemWriter<ValidatedOrder> validOrderWriter(
        DataSource dataSource,
        @Value("#{jobParameters['fileId']}") String fileId) {

    validateFileId(fileId);

    return new JdbcBatchItemWriterBuilder<ValidatedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_orders
                    (file_id, order_id, customer_id, amount, currency)
                VALUES (?, ?, ?, ?, ?)
                """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setString(1, fileId);
                ps.setLong(2, item.orderId());
                ps.setLong(3, item.customerId());
                ps.setBigDecimal(4, item.amount());
                ps.setString(5, item.currency());
            })
            .build();
}
```

Các import cần thiết:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
```

Hàm validate file ID:

```java
private static void validateFileId(String fileId) {
    if (fileId == null
            || !fileId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,99}")) {
        throw new IllegalArgumentException(
                "Invalid fileId JobParameter");
    }
}
```

Đối với sản phẩm thực tế, nên gom validation này vào một utility hoặc value object riêng để reader, listener và reporter dùng chung. `fileId` là ID logical do hệ thống cấp phát, không phải file path do người dùng gửi tùy ý.

**Chính sách lỗi writer trong demo:** các lỗi như mất DB connection, duplicate key, constraint violation, schema lỗi **không** được đánh dấu skip. Việc skip lỗi writer cần thiết kế riêng bởi writer có thể gửi batch SQL hoặc tác động hệ thống khác; một lỗi trong `write(Chunk)` không tự chỉ ra item nào có thể bỏ qua an toàn.

---

## 9. SkipListener: ghi reject bền vững vào database

### 9.1. Vì sao dùng SkipListener?

Spring Batch có callback:

- `onSkipInRead(Throwable t)`: item không thể đọc/parse nhưng được skip.
- `onSkipInProcess(I item, Throwable t)`: item đọc thành công nhưng processor lỗi và được skip.
- `onSkipInWrite(O item, Throwable t)`: item writer lỗi và được skip theo policy.

`SkipListener` được gọi sau khi framework quyết định một lỗi **thực sự là skip**, khác với mỗi lần retry bị lỗi. Với chunk-oriented step, Spring Batch cố gắng đảm bảo callback skip cho item được gọi một lần và **ngay trước khi transaction commit**. Điều đó cho phép một callback ghi reject qua JDBC cùng transaction được commit/rollback với dữ liệu của chunk.

Lưu ý “một lần” ở đây là contract trong một lần xử lý item/transaction theo framework, **không phải exactly-once toàn hệ thống qua crash/restart/remote side effect**. Vì thế bảng reject vẫn nên có unique key và UPSERT idempotent.

### 9.2. OrderRejectSkipListener.java

```java
package com.example.batch.quality;

import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.jdbc.core.JdbcTemplate;

public class OrderRejectSkipListener
        implements SkipListener<RawOrder, ValidatedOrder> {

    private final JdbcTemplate jdbc;
    private final String fileId;

    public OrderRejectSkipListener(
            JdbcTemplate jdbc, String fileId) {
        this.jdbc = jdbc;
        this.fileId = fileId;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        if (!(error instanceof FlatFileParseException parse)) {
            // Theo cấu hình demo, read skip chỉ cho lỗi parse.
            throw new IllegalStateException(
                    "Unexpected read skip type", error);
        }

        persist(
                parse.getLineNumber(),
                null,
                "READ",
                "PARSE_ERROR",
                error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            RawOrder item, Throwable error) {

        String code =
                error instanceof InvalidOrderException invalid
                    ? invalid.code()
                    : "UNKNOWN_PROCESS_ERROR";

        persist(
                item.lineNumber(),
                item.orderId(),
                "PROCESS",
                code,
                error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(
            ValidatedOrder item, Throwable error) {

        // Project không cấu hình skip lỗi ghi.
        // Nếu chính sách thay đổi, cần xác định item-level
        // idempotency và trạng thái side effect trước khi lưu.
        throw new IllegalStateException(
                "Write skip is not supported by this project", error);
    }

    private void persist(
            int lineNumber,
            Long orderId,
            String stage,
            String errorCode,
            String errorClass) {

        // MERGE ... KEY(...) là cú pháp H2 cho demo.
        // Viết qua JdbcTemplate để tham gia Spring transaction
        // khi cùng DataSource/transactionManager với step.
        jdbc.update("""
                MERGE INTO batch_rejects (
                    file_id, line_number, order_id,
                    stage, error_code, error_class
                )
                KEY (file_id, line_number)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                fileId,
                lineNumber,
                orderId,
                stage,
                errorCode,
                errorClass);
    }
}
```

Bean listener theo step:

```java
@Bean
@StepScope
OrderRejectSkipListener rejectSkipListener(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['fileId']}") String fileId) {

    validateFileId(fileId);

    return new OrderRejectSkipListener(
            jdbcTemplate, fileId);
}
```

**Giải thích:**

- `onSkipInRead` nhận exception, không có item; `FlatFileParseException.getLineNumber()` là khóa để báo dòng bị lỗi.
- `onSkipInProcess` có `RawOrder` nên biết cả số dòng và order ID.
- Không ghi raw CSV line hoặc exception message có thể chứa dữ liệu nhạy cảm.
- Chỉ persist `stage`, `errorCode`, `errorClass` thuộc các giá trị có kiểm soát.
- `MERGE` giúp ghi lặp với cùng `(fileId, lineNumber)` không tạo thêm record.
- Bean step-scoped nhận đúng `fileId` cho lần chạy, tránh field mutable singleton bị xung đột giữa các job song song.
- `batch_rejects` phải nằm ở cùng datasource/transaction cần thiết; nếu chuyển sang một hệ thống khác, phải đánh giá lại atomicity.
- Những lỗi của chính `JdbcTemplate.update` trong listener **không được nuốt**. Nếu không thể lưu reject bắt buộc, tốt hơn là thất bại thay vì âm thầm skip mà không có dấu vết.

### 9.3. Vì sao không ghi raw input?

`FlatFileParseException.getInput()` có thể trả nguyên dòng chứa tên, email, số tài khoản hoặc dữ liệu định danh. Một report gửi qua email/chat nội bộ rộng có thể trở thành điểm rò rỉ.

Báo cáo demo dùng file ID và line number để người có quyền tìm lại record gốc trong snapshot được lưu an toàn. Nếu nghiệp vụ bắt buộc lưu raw rejected payload, phải mã hóa, phân quyền, retention, audit và masking theo chính sách dữ liệu.

### 9.4. Report khi retry và rollback

Giả sử processor của item 103 đã lỗi hai lần vì retry, rồi đến lần thứ ba thành công. Nó **không phải skipped item**, nên không có reject record. Nếu một lần skip nằm trong chunk cuối cùng nhưng transaction rollback, reject ghi cùng transaction cũng rollback.

Với cấu hình chỉ có `.skip(...)` và không có `.retry(...)`, hai lỗi của dự án thuộc nhóm skip được xử lý trực tiếp. Với lỗi transient về sau, cần phân biệt rõ retry attempts, eventual skip và permanent failure.

---

## 10. Cấu hình Step chính xác

Trong `OrderQualityJobConfiguration.java`, khai báo step import:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> rawOrderReader,
        OrderValidationProcessor orderValidationProcessor,
        JdbcBatchItemWriter<ValidatedOrder> validOrderWriter,
        OrderRejectSkipListener rejectSkipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, ValidatedOrder>chunk(
                    3, transactionManager)
            .reader(rawOrderReader)
            .processor(orderValidationProcessor)
            .writer(validOrderWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(3)
            .listener(rejectSkipListener)
            .build();
}
```

Imports:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.transaction.PlatformTransactionManager;
```

### 10.1. Tại sao chunk size = 3?

Chỉ để nhìn thấy nhiều commit trên fixture tám dòng. Chunk size **không** quyết định skip limit. Với production, chunk size cần được benchmark dựa trên throughput, DB transaction, memory và rollback cost.

### 10.2. Skip limit có cộng dồn không?

Có. `skipLimit(3)` là tổng giới hạn lỗi read/process/write skip của **StepExecution**, không phải ba lỗi mỗi giai đoạn.

```text
readSkipCount    = 1
processSkipCount = 2
writeSkipCount   = 0
-----------------------
totalSkipCount   = 3
```

Một lỗi thứ tư thuộc những loại được phép sẽ vượt limit và khiến step thất bại. Nếu file có 100 lỗi format nhưng chỉ cấu hình skipLimit 3, job **không** tự bỏ qua toàn bộ 100 lỗi.

### 10.3. Đừng cấu hình skip(Exception.class)

Sai:

```java
.faultTolerant()
.skip(Exception.class)
.skipLimit(1000000)
```

Cấu hình này dễ che khuất lỗi DB, lỗi parser không dự đoán trước, cấu hình sai, lỗi lập trình và lỗi tài nguyên. Project chỉ cho phép skip `FlatFileParseException` và `InvalidOrderException`.

Với quy trình có lỗi nghiêm trọng không được skip ngay cả khi thuộc một superclass rộng, Spring Batch còn có chính sách `noSkip(...)`. Tốt nhất vẫn là khai báo whitelist cụ thể và có test cho từng nhóm lỗi.

### 10.4. Phân biệt skip, retry và filter

| Cơ chế | Khi nào dùng | Hành vi |
|---|---|---|
| Filter | Item không thuộc phạm vi nghiệp vụ, hoàn toàn bình thường | Processor trả `null`; tăng `filterCount` |
| Skip | Dữ liệu item lỗi nhưng được phép bỏ và có báo cáo | Exception thuộc whitelist; tăng skip count |
| Retry | Lỗi tạm thời có thể hồi phục | Thử lại trong giới hạn, có thể về success hoặc fail/skip |
| Fail | Lỗi vượt ngưỡng, không cho skip, lỗi hệ thống | Step/job dừng với trạng thái thất bại |
| Quarantine | Bản ghi lỗi cần xử lý sau hoặc tái nhập | Lưu item ID/dữ liệu có kiểm soát và trạng thái |

Một item retry thành công không nên xuất hiện trong report rejected items. Một item filter bình thường không được coi là reject, trừ khi nghiệp vụ muốn audit filter bằng một kênh riêng.

---

## 11. Tạo báo cáo sau khi import thành công

### 11.1. Vì sao dùng Step riêng?

Tạo report trực tiếp trong `SkipListener` là cách dễ gặp inconsistency. Cách của dự án:

1. `importOrdersStep` xử lý và commit các chunk, ghi bảng đích cùng bảng reject.
2. Nếu import `COMPLETED`, chạy `reportStep`.
3. `reportStep` lấy các counter từ metadata của import step, lấy reject rows từ database, đối chiếu tổng skip với số reject, rồi viết file tạm.
4. Chỉ sau khi file hoàn tất mới chuyển sang tên report chính thức.
5. Nếu report step thất bại, job `FAILED` dù import đã hoàn tất; restart cùng JobInstance có thể chạy lại phần report mà không phải chạy lại import step đã `COMPLETED`.

Chính sách này làm **báo cáo trở thành đầu ra bắt buộc** của job, không chỉ là log best-effort.

### 11.2. Định dạng báo cáo

Report text chứa summary `key=value` và danh sách rejected lines dạng CSV ở cuối, như mục 2.4. Dữ liệu trong dòng reject đã được whitelist để không có raw PII. Report file name lấy từ `fileId` hợp lệ:

```text
build/reports/batch-quality/orders-2026-11-15-v1.report.txt
```

Không đưa giá trị path tùy ý từ JobParameters vào tên file report, tránh path traversal hoặc ghi đè file hệ thống.

### 11.3. RejectReportTasklet.java

```java
package com.example.batch.quality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.jdbc.core.JdbcTemplate;

public class RejectReportTasklet implements Tasklet {

    private final JobExplorer explorer;
    private final JdbcTemplate jdbc;
    private final Path reportRoot;
    private final String fileId;

    public RejectReportTasklet(
            JobExplorer explorer,
            JdbcTemplate jdbc,
            Path reportRoot,
            String fileId) {

        this.explorer = Objects.requireNonNull(explorer);
        this.jdbc = Objects.requireNonNull(jdbc);
        this.reportRoot = Objects.requireNonNull(reportRoot);
        this.fileId = Objects.requireNonNull(fileId);

        if (!fileId.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,99}")) {
            throw new IllegalArgumentException("Invalid fileId");
        }
    }

    public record RejectedLine(
            int lineNumber,
            Long orderId,
            String stage,
            String errorCode,
            String errorClass) {}

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        JobInstance jobInstance = chunkContext
                .getStepContext()
                .getStepExecution()
                .getJobExecution()
                .getJobInstance();

        // Không chỉ đọc JobExecution hiện tại:
        // reportStep có thể restart sau khi importStep đã
        // COMPLETED ở một JobExecution trước đó.
        StepExecution importStep = explorer
                .getJobExecutions(jobInstance)
                .stream()
                .flatMap(job -> job.getStepExecutions().stream())
                .filter(step ->
                        step.getStepName().equals("importOrdersStep"))
                .filter(step ->
                        step.getStatus() == BatchStatus.COMPLETED)
                .max(Comparator.comparing(
                        step -> step.getId() == null
                                ? -1L : step.getId()))
                .orElseThrow(() -> new IllegalStateException(
                        "No completed importOrdersStep for jobInstance"));

        List<RejectedLine> rejects = jdbc.query("""
                SELECT line_number, order_id, stage,
                       error_code, error_class
                FROM batch_rejects
                WHERE file_id = ?
                ORDER BY line_number
                """,
                (rs, n) -> new RejectedLine(
                        rs.getInt("line_number"),
                        rs.getObject("order_id", Long.class),
                        rs.getString("stage"),
                        rs.getString("error_code"),
                        rs.getString("error_class")),
                fileId);

        if (rejects.size() != importStep.getSkipCount()) {
            throw new IllegalStateException(
                    "Reject count does not match StepExecution skipCount");
        }

        StringBuilder report = new StringBuilder(2048);
        report.append("SPRING BATCH IMPORT QUALITY REPORT\n");
        report.append("fileId=").append(fileId).append('\n');
        report.append("generatedAtUtc=")
                .append(Instant.now()).append('\n');
        report.append("importStatus=")
                .append(importStep.getStatus()).append('\n');
        report.append("readCount=")
                .append(importStep.getReadCount()).append('\n');
        report.append("writeCount=")
                .append(importStep.getWriteCount()).append('\n');
        report.append("filterCount=")
                .append(importStep.getFilterCount()).append('\n');
        report.append("readSkipCount=")
                .append(importStep.getReadSkipCount()).append('\n');
        report.append("processSkipCount=")
                .append(importStep.getProcessSkipCount()).append('\n');
        report.append("writeSkipCount=")
                .append(importStep.getWriteSkipCount()).append('\n');
        report.append("totalSkipCount=")
                .append(importStep.getSkipCount()).append('\n');
        report.append("persistedRejectCount=")
                .append(rejects.size()).append("\n\n");

        report.append(
                "lineNumber,orderId,stage,errorCode,errorClass\n");
        for (RejectedLine reject : rejects) {
            // Các chuỗi stage/code/class do ứng dụng sinh,
            // không đưa raw input/message vào file report.
            report.append(reject.lineNumber()).append(',');
            if (reject.orderId() != null) {
                report.append(reject.orderId());
            }
            report.append(',')
                    .append(reject.stage()).append(',')
                    .append(reject.errorCode()).append(',')
                    .append(reject.errorClass()).append('\n');
        }

        Path directory = reportRoot.toAbsolutePath().normalize();
        Files.createDirectories(directory);

        Path target =
                directory.resolve(fileId + ".report.txt").normalize();

        // fileId được whitelist; vẫn kiểm tra không thoát root.
        if (!target.getParent().equals(directory)) {
            throw new IOException("Report path escapes root");
        }

        Path temporary = Files.createTempFile(
                directory, ".quality-report-", ".tmp");

        try {
            Files.writeString(
                    temporary,
                    report.toString(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            // Demo nhắm filesystem hỗ trợ atomic move.
            // Nếu không hỗ trợ, fail để tránh publish nửa file.
            Files.move(temporary, target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }

        return RepeatStatus.FINISHED;
    }
}
```

### 11.4. Những ranh giới của report step

- `ATOMIC_MOVE` cho phép consumer tránh đọc file đang ghi dở **nếu filesystem thực sự hỗ trợ**. Hành vi khi đích tồn tại tùy provider/filesystem; production nên kiểm chứng atomic replacement hoặc dùng immutable report object + manifest.
- Report file nằm ngoài transaction database. Nếu file publish thành công nhưng transaction của `reportStep` commit metadata thất bại, restart có thể ghi lại report. Việc tạo lại **cùng tên** giúp quản lý idempotency của report bản minh họa, nhưng nếu report được phát cho bên ngoài, cần manifest/version/conditional publish.
- `generatedAtUtc` thay đổi khi report được tạo lại. Nếu cần byte-identical report, lấy timestamp từ một mốc lưu bền vững thay vì `Instant.now()`, hoặc phiên bản hóa report.
- Với skip limit rất lớn, `StringBuilder` giữ toàn bộ report trong memory; production nên ghi bằng `BufferedWriter`/stream từng reject row, không tải tất cả vào list. Bản demo có `skipLimit=3` nên report bounded.
- Nếu filesystem không cho phép atomic move, tasklet fail; không âm thầm fallback sang publish không atomic khi đây là yêu cầu nghiệp vụ.
- Sau khi report step hoàn tất nhưng notification (email/message) thất bại, notification cũng cần idempotency hoặc outbox; không mặc định khởi chạy lại toàn bộ import.

### 11.5. Bean report step

```java
@Bean
@StepScope
RejectReportTasklet rejectReportTasklet(
        JobExplorer explorer,
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['fileId']}") String fileId,
        @Value("${app.batch.report-directory}")
                String reportDirectory) {

    return new RejectReportTasklet(
            explorer,
            jdbcTemplate,
            Path.of(reportDirectory),
            fileId);
}

@Bean
Step reportStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        RejectReportTasklet rejectReportTasklet) {

    return new StepBuilder("reportStep", repository)
            .tasklet(rejectReportTasklet, transactionManager)
            .build();
}
```

Các import:

```java
import java.nio.file.Path;

import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.jdbc.core.JdbcTemplate;
```

### 11.6. Nếu import thất bại trước report thì sao?

Với flow tuần tự mặc định, `reportStep` **không chạy** khi `importOrdersStep` `FAILED`. Đây là quyết định rõ ràng: **không xuất báo cáo hoàn tất cho một lần nhập thất bại**.

Tuy nhiên vẫn có:

- `JobExecution`/`StepExecution` metadata, status, exit description.
- Các bản ghi trong `batch_rejects` đã commit ở những chunk trước.
- Các record hợp lệ đã commit ở `imported_orders` trước khi failure.

Runbook có thể chạy truy vấn để lập **incident report** riêng. Nếu yêu cầu luôn tạo file báo cáo kể cả khi failed, hãy thiết kế flow điều kiện với bước báo cáo riêng và bảo đảm **job cuối vẫn FAILED**; không vô tình biến failure thành `COMPLETED` vì report step đã thành công. Có thể chuyển trách nhiệm này sang một workflow báo cáo độc lập đọc `JobExplorer` và dữ liệu reject đã commit.

---

## 12. Ghép Job: import rồi report

Trong `OrderQualityJobConfiguration.java`:

```java
@Bean
Job ordersQualityJob(
        JobRepository repository,
        Step importOrdersStep,
        Step reportStep) {

    return new JobBuilder("ordersQualityJob", repository)
            .start(importOrdersStep)
            .next(reportStep)
            .build();
}
```

Các bean đã được trình bày theo từng phần. Phần đầu file cấu hình:

```java
package com.example.batch.quality;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.file.LineMapper;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class OrderQualityJobConfiguration {
    // Đặt các @Bean ở mục 6, 8, 9, 10, 11 và 12 tại đây.
    // Chỉ dùng MỘT phiên bản của mỗi bean.
}
```

### 12.1. Vòng đời chạy

```text
Start ordersQualityJob
          │
          ▼
    importOrdersStep
          │
    ┌─────┴──────┐
    │            │
 COMPLETED      FAILED
    │            │
    ▼            ▼
 reportStep     Stop Job
    │          status FAILED
 ┌──┴─────┐
 │        │
COMPLETED FAILED
 │        │
 ▼        ▼
Job       Job
COMPLETED FAILED
```

Tại lần restart cùng `JobInstance`, một step đã `COMPLETED` theo repository thông thường được **bỏ qua** trừ khi cấu hình bắt chạy lại. Vì vậy nếu report step thất bại sau khi import thành công, việc chạy lại có thể chỉ cần chạy report step. Trong dự án, reporter đọc metadata import từ các JobExecution trước cùng JobInstance để hỗ trợ trường hợp đó.

---

## 13. Chạy thử với fixture CSV

### 13.1. JobParameters

Để tự gọi job từ một controller, command runner hoặc integration test:

```java
JobParameters params = new JobParametersBuilder()
        .addString(
                "fileId",
                "orders-2026-11-15-v1",
                true)
        .addString(
                "inputFile",
                "/data/ready/orders-2026-11-15-v1.csv",
                false)
        .toJobParameters();

JobExecution execution =
        jobLauncher.run(ordersQualityJob, params);
```

Ý nghĩa:

- `fileId` là identifying parameter: một snapshot logic tương ứng một `JobInstance`.
- `inputFile` là vị trí đọc đã được kiểm soát; không tham gia định danh ở demo.
- Trong production, `fileId` phải gắn với immutable object version và checksum, không cho một fileId trỏ tới nội dung khác khi restart.
- Không thêm timestamp ngẫu nhiên làm identifying parameter chỉ để “chạy lại cho xong”: điều đó tạo một JobInstance khác và không sử dụng lịch sử restart của snapshot cũ.

Đối với bài tập muốn chạy lại với một bộ input mới, phải cấp fileId mới hoặc reset môi trường test theo quy trình được phép. Nếu instance đã `COMPLETED`, gọi lại cùng identifying parameters thông thường bị từ chối bằng `JobInstanceAlreadyCompleteException`.

### 13.2. Kết quả kỳ vọng

Sau khi job `COMPLETED`:

```sql
SELECT file_id, order_id, customer_id, amount, currency
FROM imported_orders
WHERE file_id = 'orders-2026-11-15-v1'
ORDER BY order_id;
```

Kết quả logic:

| order_id | customer_id | amount | currency |
|---:|---:|---:|---|
| 101 | 1001 | 120.50 | USD |
| 104 | 1004 | 50.00 | USD |
| 106 | 1006 | 80.75 | USD |
| 107 | 1007 | 25.00 | VND |
| 108 | 1008 | 10.00 | USD |

Truy vấn reject:

```sql
SELECT file_id, line_number, order_id, stage, error_code
FROM batch_rejects
WHERE file_id = 'orders-2026-11-15-v1'
ORDER BY line_number;
```

Kết quả logic:

| line_number | order_id | stage | error_code |
|---:|---:|---|---|
| 3 | 102 | PROCESS | NON_POSITIVE_AMOUNT |
| 4 | null | READ | PARSE_ERROR |
| 6 | 105 | PROCESS | NON_POSITIVE_AMOUNT |

`StepExecution` của `importOrdersStep` sẽ có:

```text
readCount        = 7
writeCount       = 5
filterCount      = 0
readSkipCount    = 1
processSkipCount = 2
writeSkipCount   = 0
skipCount        = 3
BatchStatus      = COMPLETED
```

Các con số này đúng cho **fixture không có lỗi khác và không có retry/skip thêm**. Không nên suy ra readCount của mọi project bằng “số dòng trừ lỗi”, vì reader có thể bỏ comment/header, filter, custom record separation hoặc có logic đọc khác.

### 13.3. Bảo vệ tính đúng của báo cáo

Report step đối chiếu `rejects.size()` với `importStep.getSkipCount()`. Nếu hai số khác, tasklet fail thay vì xuất một báo cáo không nhất quán. Điều đó giúp phát hiện listener không ghi được reject, sai fileId, dữ liệu reject bị can thiệp hoặc transaction configuration sai.

Bản production có thể còn đối chiếu:

```text
expectedDataRows =
    successfulReadItems
  + readParseRejectedItems
  + những loại record bị bỏ theo hợp đồng (comment/header...)

successfulReadItems =
    writeCount
  + processSkipCount
  + filterCount
  + các loại item không ghi theo thiết kế
```

Tùy retry, writer skip, multiple outputs và custom processor, phép đối chiếu phải được định nghĩa đúng cho từng job. Không biến một công thức minh họa thành invariant phổ quát của Spring Batch.

---

## 14. Kiểm thử tích hợp bằng spring-batch-test

### 14.1. Vì sao cần test cả job?

Unit test riêng `OrderValidationProcessor` xác nhận số tiền âm tạo exception, nhưng không chứng minh Spring Batch đã:

- Bắt `FlatFileParseException` tại read phase.
- Gọi `onSkipInRead` với line number đúng.
- Skip đúng ba lần trên toàn StepExecution.
- Commit các record tốt và reject trong cùng transaction.
- Chạy `reportStep` sau khi import completed.
- Làm job failed khi vượt skipLimit.
- Giữ metadata và restart semantics.

`spring-batch-test` cung cấp `@SpringBatchTest` và `JobLauncherTestUtils` để chạy test với JobRepository thật.

### 14.2. Ví dụ integration test

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

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
@SpringBootTest(
        classes = BatchQualityApplication.class)
class OrderQualityJobIT {

    @Autowired
    JobLauncherTestUtils jobs;

    @Autowired
    JdbcTemplate jdbc;

    @TempDir
    Path temporaryDirectory;

    @Test
    void skipsThreeInvalidRowsAndWritesReport() throws Exception {

        String fileId = "test-" + UUID.randomUUID();

        Path csv = temporaryDirectory.resolve("orders.csv");
        Files.writeString(csv, """
                order_id,customer_id,amount,currency
                101,1001,120.50,USD
                102,1002,-5.00,USD
                103,1003,not_number,USD
                104,1004,50.00,USD
                105,1005,0.00,USD
                106,1006,80.75,USD
                107,1007,25.00,VND
                108,1008,10.00,USD
                """, StandardCharsets.UTF_8);

        JobParameters params = new JobParametersBuilder()
                .addString("fileId", fileId, true)
                .addString("inputFile", csv.toString(), false)
                .toJobParameters();

        JobExecution execution = jobs.launchJob(params);

        assertEquals(
                BatchStatus.COMPLETED, execution.getStatus());

        StepExecution importStep = execution
                .getStepExecutions()
                .stream()
                .filter(s -> s.getStepName()
                        .equals("importOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(7L, importStep.getReadCount());
        assertEquals(5L, importStep.getWriteCount());
        assertEquals(0L, importStep.getFilterCount());

        assertEquals(1L, importStep.getReadSkipCount());
        assertEquals(2L, importStep.getProcessSkipCount());
        assertEquals(0L, importStep.getWriteSkipCount());
        assertEquals(3L, importStep.getSkipCount());

        Long imported = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM imported_orders
                WHERE file_id = ?
                """,
                Long.class, fileId);

        Long rejected = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM batch_rejects
                WHERE file_id = ?
                """,
                Long.class, fileId);

        assertEquals(5L, imported);
        assertEquals(3L, rejected);

        Path report = Path.of(
                "build/reports/batch-quality",
                fileId + ".report.txt");

        String content = Files.readString(
                report, StandardCharsets.UTF_8);

        assertTrue(content.contains("writeCount=5"));
        assertTrue(content.contains("totalSkipCount=3"));
        assertTrue(content.contains(
                "4,,READ,PARSE_ERROR,FlatFileParseException"));
    }
}
```

**Chú ý test environment:**

- `@SpringBatchTest` tạo các tiện ích test; để `JobLauncherTestUtils` biết job nào phải chạy, context demo chỉ có một job chính. Nếu có nhiều job, chọn job cụ thể trong setup.
- `spring.batch.job.enabled=false` ngăn job tự chạy khi application context khởi động.
- Report path trong assertion khớp `app.batch.report-directory` của YAML demo. Trong CI thực tế, nên dùng report directory riêng cho từng test (có thể qua dynamic property), tránh xung đột khi chạy song song.
- `fileId` khác nhau mỗi test để không đụng unique keys/`JobInstance` của các lần thử.
- Bài học minh họa test, không phải kết quả đã chạy trong môi trường này.

### 14.3. Test vượt skip limit

Thêm một dòng sai nghiệp vụ thứ tư, ví dụ:

```csv
109,1009,-1.00,USD
```

Kỳ vọng:

- Bước import `FAILED` vì có quá nhiều lỗi được phép skip.
- Job `FAILED`.
- `reportStep` không chạy theo flow tuần tự mặc định.
- Reject rows đã được commit ở chunk trước vẫn có thể tồn tại; không giả định cả bốn lỗi đều có trong bảng reject.
- Những record tốt ở chunk đã commit trước failure cũng có thể còn trong bảng đích.
- Metadata thể hiện nguyên nhân giới hạn skip bị vượt; runbook phải xử lý phiên bản file lỗi.

**Không assert cứng rằng reject count bằng 4 khi job FAILED.** Sự kiện vượt limit có thể khiến chunk bị rollback; số lỗi đã được commit trong những chunk trước mới là nguồn tin cậy cho bảng `batch_rejects`.

### 14.4. Test writer exception không được skip

Cố ý tạo hai dòng hợp lệ nhưng cùng `order_id` trong một file hoặc dùng writer ném `DataIntegrityViolationException`. Vì policy chỉ cho skip parse/business validation, mong đợi:

- Job `FAILED`.
- Không có sự kiện `WRITE` reject “giả vờ bỏ qua”.
- Không xuất report thành công.
- Không bỏ qua lỗi DB nghiêm trọng để lấy status completed.

Trong production, duplicate business key có thể được coi là lỗi dữ liệu có thể xử lý; khi đó nên xác định xử lý duplicate **trước writer** hoặc xây writer idempotent có luật rõ, thay vì coi mọi database constraint error đều skippable.

---

## 15. Test unit cho processor và listener

### 15.1. Processor

```java
class OrderValidationProcessorTest {

    private final OrderValidationProcessor processor =
            new OrderValidationProcessor();

    @Test
    void rejectsNonPositiveAmount() {
        RawOrder input = new RawOrder(
                3, 102L, 1002L,
                new BigDecimal("-5.00"), "USD");

        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));

        assertEquals("NON_POSITIVE_AMOUNT", error.code());
    }

    @Test
    void rejectsUnknownCurrency() {
        RawOrder input = new RawOrder(
                5, 104L, 1004L,
                new BigDecimal("10.00"), "XXX");

        assertEquals(
                "UNSUPPORTED_CURRENCY",
                assertThrows(
                        InvalidOrderException.class,
                        () -> processor.process(input)).code());
    }

    @Test
    void acceptsValidOrder() throws Exception {
        RawOrder input = new RawOrder(
                2, 101L, 1001L,
                new BigDecimal("120.50"), "USD");

        ValidatedOrder output = processor.process(input);

        assertEquals(101L, output.orderId());
        assertEquals(2, output.lineNumber());
    }
}
```

Imports chính từ JUnit Jupiter, `BigDecimal` và các model cùng package. Các test này bảo đảm business validation, nhưng không thay cho integration test của skip limit.

### 15.2. Listener

Có thể mock `JdbcTemplate` và gọi `onSkipInProcess` bằng `RawOrder`, assert câu SQL được gọi với `fileId` và `lineNumber` đúng. Với `onSkipInRead`, tạo `FlatFileParseException` giả lập có line number, kiểm tra payload báo cáo không bao giờ lấy trực tiếp từ `getInput()`.

Cần test bằng database thật để xác nhận `MERGE` hoạt động và reject write tham gia transaction. Mockito chỉ chứng minh code gọi API, không chứng minh atomicity.

### 15.3. Transaction rollback test

Một test integration có thể cho writer fail trong chunk đã có skip callback. Sau rollback, kiểm tra các bản ghi reject thuộc chunk đó không bị persist khi transaction chung rollback. Sau đó khởi chạy lại với lỗi đã được sửa và kiểm tra không sinh duplicate reject rows.

Cần xác định chunk boundary và thời điểm skip callback theo Spring Batch version đang test. Không viết test dựa trên giả định `SkipListener` được gọi ngay đúng thời điểm exception đầu tiên ném ra.

---

## 16. Restart và idempotency

### 16.1. Completed step và failed step

Trong flow của demo:

- Nếu `importOrdersStep` hoàn tất, `reportStep` fail: restart cùng `JobInstance` thường bỏ qua import đã completed, chạy lại report. Reporter dùng `JobExplorer` tra metadata import của các JobExecution trước thuộc cùng instance.
- Nếu `importOrdersStep` fail vì vượt skip limit: không thể chỉ restart với cùng nội dung và cùng policy rồi mong job hoàn tất; cần sửa dữ liệu hoặc thay đổi quyết định nghiệp vụ có kiểm soát.
- Nếu `importOrdersStep` fail vì database tạm thời không sẵn sàng: sửa dependency rồi restart có thể tiếp tục từ checkpoint, theo trạng thái reader/writer.
- Nếu input file thay đổi trong lúc downtime: reader checkpoint có thể không còn tương ứng, nên không được âm thầm restart bằng phiên bản mới.

### 16.2. Unique key cho báo cáo reject

`batch_rejects` dùng `(file_id, line_number)`. Với một file snapshot bất biến, cùng dòng có cùng ý nghĩa qua restart. Nếu giữ fileId nhưng thay nội dung file, unique key này sẽ **ghi đè hoặc trộn báo cáo của hai snapshot**. Vì vậy file ID/version/checksum là contract bắt buộc, không chỉ lựa chọn đặt tên.

### 16.3. Unique key cho output

`imported_orders` dùng `(file_id, order_id)`. Nếu một chunk đã ghi database nhưng client không nhận kết quả commit trước khi crash, lần restart có thể gặp duplicate key. Tính đúng đắn cần transaction boundary và writer idempotency phù hợp:

- Nếu business key trùng là lỗi, fail và điều tra.
- Nếu cho phép replay cùng record, triển khai UPSERT/conditional write có kiểm tra dữ liệu không đổi.
- Không tự skip tất cả `DuplicateKeyException` vì có thể che giấu hai record khác nhau dùng cùng ID.
- Với remote API hoặc file output, phải thiết kế outbox/atomic publish và reconciliation riêng.

### 16.4. Báo cáo cũng phải idempotent

`RejectReportTasklet` ghi file tạm, sau đó atomic move vào một tên dựa trên fileId. Nếu DB đã commit import nhưng report chưa được ghi, restart có thể tạo lại report mà không nhập dữ liệu lần hai.

Tuy nhiên việc phát email/upload report cho bên thứ ba có thể thành công rồi client timeout. Khi đó dù file report nội bộ chỉ có một bản, bên nhận có thể nhận hai thông báo. Cần correlation ID, unique report version hoặc outbox để điều phối thông báo.

### 16.5. Chính sách retention

Không xóa CSV gốc ngay sau khi job completed nếu còn cần đối soát reject lines, audit, reprocess hoặc điều tra. Cần lưu:

- fileId/object version/checksum;
- schema version;
- businessDate và giờ timezone áp dụng;
- kết quả JobExecution;
- report và rejected lines;
- thời gian retention/cleanup;
- ai được quyền xem file gốc hoặc error report.

Với dữ liệu cá nhân, báo cáo chỉ nên lưu metadata cần thiết và tuân thủ phân quyền.

---

## 17. Bảng thống kê và SQL đối soát

### 17.1. Số record output theo file

```sql
SELECT file_id, COUNT(*) AS imported_count
FROM imported_orders
GROUP BY file_id
ORDER BY file_id;
```

### 17.2. Lỗi theo giai đoạn và mã lỗi

```sql
SELECT file_id, stage, error_code,
       COUNT(*) AS rejected_count
FROM batch_rejects
GROUP BY file_id, stage, error_code
ORDER BY file_id, stage, error_code;
```

Với fixture:

```text
READ    PARSE_ERROR         1
PROCESS NON_POSITIVE_AMOUNT 2
```

### 17.3. Truy vấn sự kiện reject theo dòng

```sql
SELECT line_number, order_id, stage, error_code
FROM batch_rejects
WHERE file_id = ?
ORDER BY line_number;
```

### 17.4. Không đồng nhất mọi count

Các counter có phạm vi khác nhau:

| Metric | Nghĩa |
|---|---|
| `readCount` | Item reader trả về thành công và được ghi nhận đã đọc |
| `readSkipCount` | Lỗi khi đọc được skip |
| `processSkipCount` | Lỗi khi xử lý được skip |
| `writeSkipCount` | Lỗi khi ghi được skip |
| `filterCount` | Processor trả `null` theo logic filter |
| `writeCount` | Item được writer ghi nhận đã viết |
| `rollbackCount` | Số rollback được ghi nhận |
| `commitCount` | Số lần commit được ghi nhận |
| `skipCount` | Tổng các skip count read/process/write |

Một job có `writeCount=5` và `skipCount=3` **không** chứng minh input chỉ có tám dòng nếu reader còn bỏ header, comment, filter hoặc có quy tắc đặc biệt. Vì thế cần manifest/expected count và các phép đối soát theo hợp đồng dữ liệu.

### 17.5. Tổng skip rate

Nếu KPI cần tỷ lệ lỗi:

```text
skipRate = committedSkipCount /
           (successfulInputItems + readRejectedItems)
```

Trong demo:

```text
successfulInputItems = readCount = 7
readRejectedItems    = readSkipCount = 1

skipRate = 3 / (7 + 1) = 37.5%
```

Đây là tỷ lệ lỗi trên tổng số **data records được thử đọc**, khác tỷ lệ lỗi chỉ trên số record được writer ghi. Với pipeline có filter, streaming hay nhiều resource, cần định nghĩa denominator rõ. Nếu input source có manifest count, nên đối chiếu trực tiếp expected count từ manifest.

---

## 18. Giám sát và cảnh báo

### 18.1. Metrics nên có

| Chỉ số | Nguồn | Tác dụng |
|---|---|---|
| Job status/duration | Spring Batch metadata/Micrometer | Job completed/failed và thời gian |
| `readSkipCount` | StepExecution | Lỗi parse/reader |
| `processSkipCount` | StepExecution | Lỗi business validation |
| `writeSkipCount` | StepExecution | Lỗi writer được skip theo policy |
| `filterCount` | StepExecution | Item loại theo filter |
| Rejects by errorCode | Query `batch_rejects` | Top lỗi nhập dữ liệu |
| Report status | JobExecution/reportStep | Báo cáo đã publish hay chưa |
| Input count/checksum | Manifest/validation | File đủ dữ liệu không |
| Quarantine backlog | Bảng/ticket/workflow | Lỗi còn phải sửa |
| Skip rate theo partner | Custom metric (low-cardinality) | Chất lượng dữ liệu nguồn |

Không đưa fileId/customerId/orderId từng bản ghi vào metric label mỗi item vì tạo time-series cardinality lớn và có thể lộ dữ liệu. Giữ các ID cụ thể trong audit store có quyền truy cập và gắn link nội bộ tới incident.

### 18.2. Ngưỡng cảnh báo

Ví dụ chính sách:

- **Warning:** skipRate lớn hơn 1% trong một kỳ, nhưng job vẫn completed.
- **Critical:** skipRate lớn hơn 5%, ảnh hưởng SLA hoặc báo cáo bắt buộc.
- **Critical:** job FAILED vì vượt skip limit hoặc writer/database error.
- **Warning/Critical:** reportStep failed hoặc report chưa được publish trước deadline.
- **Critical:** manifest count và tổng data records không khớp.

Các số 1% và 5% chỉ để minh họa. Ngưỡng đúng phải xuất phát từ chất lượng dữ liệu nguồn, loại dữ liệu và cam kết nghiệp vụ. Với dữ liệu thanh toán, chỉ một dòng bị skip có thể đã cần xử lý khẩn cấp.

### 18.3. Log an toàn

Log có cấu trúc:

```text
event=BATCH_RECORD_REJECTED
fileId=orders-2026-11-15-v1
jobExecutionId=701
step=importOrdersStep
lineNumber=4
stage=READ
errorCode=PARSE_ERROR
```

Không log toàn bộ raw CSV, credential, account number hoặc serialized `ExecutionContext`. Nếu cần debug raw line, cung cấp công cụ truy vấn file gốc theo role và audit phù hợp.

### 18.4. Runbook khi skip tăng bất thường

1. Xác định fileId/snapshot/partner/businessDate và tổng số record kỳ vọng.
2. Xem `StepExecution`, `readSkipCount`/`processSkipCount`/`writeSkipCount`.
3. Query reject events theo errorCode và dòng.
4. Kiểm tra có thay đổi schema, encoding, upstream mapping hoặc chính sách validation không.
5. Nếu lỗi nằm ở source, yêu cầu cung cấp file mới có version khác hoặc quy trình correction được kiểm soát.
6. Không xóa reject rows hay tăng skipLimit chỉ để đạt completed.
7. Đối soát output theo business keys, số tiền, trạng thái report và tác động downstream.
8. Ghi nhận kết quả incident, correction và reprocess nếu cần.

---

## 19. Khi nào được skip một record?

Đây là một **quyết định nghiệp vụ**, không phải chỉ là cấu hình Spring Batch.

| Loại dữ liệu | Ví dụ lỗi | Chính sách thường cân nhắc |
|---|---|---|
| Import marketing tùy chọn | Thiếu số điện thoại không bắt buộc | Skip và báo cáo |
| Log phân tích thống kê | Một vài dòng format sai | Skip với threshold và audit |
| Dữ liệu tham khảo | Unknown optional field | Filter/skip theo hợp đồng |
| Lương/thuế | Sai số tiền/tài khoản nhận | Có thể fail/quarantine, cần sửa và đối soát |
| Thanh toán/settlement | Một giao dịch không parse được | Thường không được silent skip |
| Identity/authorization | Mã khách hàng không khớp | Tùy rủi ro, thường cần ngăn nhập sai |
| Source DB bị lỗi | Deadlock/connection timeout | Retry/fail; không coi là dữ liệu item lỗi |
| Writer gặp lỗi unique key | Có thể duplicate do replay hoặc input thực | Phân tích trước khi quyết định idempotent write/skip |

Bài demo cho phép skip ba lỗi để học framework. Với dữ liệu phải đủ 100%, thiết kế có thể chọn `skipLimit(0)` hoặc fail với bất kỳ dữ liệu sai, đồng thời tạo incident report ở workflow riêng.

### 19.1. Tại sao không nên tăng skipLimit theo tỷ lệ đơn giản?

Một file 1 triệu dòng và 1% lỗi nghĩa là 10.000 record bị bỏ. Con số đó có thể quá lớn về giá trị tiền hoặc số khách hàng. Cần cân nhắc đồng thời:

- Giới hạn tuyệt đối, ví dụ không quá N lỗi.
- Giới hạn tỷ lệ trên tổng số dòng.
- Loại lỗi có mức độ nghiêm trọng khác nhau.
- Giá trị nghiệp vụ tổng thể của những record lỗi.
- Khả năng sửa và reprocess kịp SLA.

`skipLimit` của Spring Batch là giới hạn tổng số item skip, không phải phần trăm. Nếu cần tỷ lệ, có thể thêm policy/validation step hoặc custom `SkipPolicy`; phải tránh tạo logic dựa trên denominator chưa biết cho đến cuối file.

---

## 20. Mở rộng: SkipPolicy theo mã lỗi

Khi có nhiều loại lỗi, `.skip(ExceptionClass.class)` có thể quá thô. Ví dụ chỉ một số `InvalidOrderException` được phép skip, còn `INVALID_ORDER_ID` phải fail ngay.

Một `SkipPolicy` tùy biến:

```java
public final class OrderSkipPolicy implements SkipPolicy {

    private final int maximum;

    public OrderSkipPolicy(int maximum) {
        this.maximum = maximum;
    }

    @Override
    public boolean shouldSkip(
            Throwable error, long skipCount) {

        // Framework có thể gọi với skipCount âm khi phân loại.
        boolean eligible = false;

        if (error instanceof FlatFileParseException) {
            eligible = true;
        } else if (error instanceof InvalidOrderException invalid) {
            eligible = !invalid.code()
                    .equals("INVALID_ORDER_ID");
        }

        return eligible
                && (skipCount < 0 || skipCount < maximum);
    }
}
```

Dùng:

```java
.faultTolerant()
.skipPolicy(new OrderSkipPolicy(3))
```

**Quan trọng:** khi dùng custom `SkipPolicy`, cần kiểm tra Javadoc và behavior của Spring Batch version tương ứng, nhất là cách framework gọi `shouldSkip` với `skipCount < 0` khi chỉ muốn phân loại exception. Policy phải tách kiểm tra **loại lỗi có thể skip** với **ngưỡng đã skip**, tránh trả false trong lần phân loại khiến behavior khác mong đợi.

Không kết hợp nhiều policy mà chưa hiểu thứ tự ưu tiên giữa `skip(...)`, `noSkip(...)` và `skipPolicy(...)`. Giữ một nguồn policy chính, test đủ ngưỡng và lỗi không hợp lệ.

### 20.1. Nhiều mức severity

Một cách cải tiến:

```text
InvalidOrderException
  ├─ UNSUPPORTED_CURRENCY  → SKIP + report
  ├─ NON_POSITIVE_AMOUNT   → SKIP + report (demo)
  ├─ INVALID_CUSTOMER_ID   → FAIL nếu dữ liệu định danh quan trọng
  └─ INVALID_ORDER_ID      → FAIL
```

Những quyết định này phải được business owner phê duyệt. Đừng tự cho rằng mọi validation error là minor.

---

## 21. Mở rộng: Retry với timeout và writer failure

### 21.1. Không đồng nhất retry với skip

Lỗi API remote hoặc DB bị timeout có thể tạm thời, khác với dữ liệu `amount=-5.00` không tự đúng hơn sau vài lần thử.

Ví dụ minh họa nguyên tắc:

```java
.faultTolerant()
.retry(TransientRemoteException.class)
.retryLimit(3)
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skipLimit(3)
```

`TransientRemoteException` ở đây là exception của một integration khác, **không thuộc project demo hiện tại**. Nếu bổ sung remote call, cần timeout, backoff, rate limiting và idempotency phù hợp. Không retry tất cả `RuntimeException`.

### 21.2. Skip trong ItemWriter phức tạp hơn

Một `JdbcBatchItemWriter` gửi nhiều dòng SQL trong chunk. Khi batch insert thất bại vì constraint, framework có thể thực hiện rollback/retry để xác định item lỗi theo fault-tolerant algorithm, nhưng kết quả phụ thuộc transaction, driver, business rule và writer design.

Nếu writer gửi email hoặc HTTP POST trước khi exception:

- Side effect có thể đã xảy ra.
- Local database rollback không thu hồi email/HTTP transaction.
- Retry/skip có thể tạo duplicate side effect.
- Không có cơ chế “skip một item” nào tự bảo đảm exactly-once.

Vì vậy demo **không cấu hình skip lỗi writer**. Nếu cần xử lý duplicate orders, nên pre-validate, dùng business unique key và upsert/idempotent writer theo hợp đồng.

### 21.3. Backoff và retry budget

Với lỗi transient, cần giới hạn attempts, total elapsed time và backoff. Nếu mỗi HTTP request timeout sau 5 giây, retry ba attempts kèm backoff, một item có thể mất hơn 15 giây. Với chunk size 1.000, giữ transaction trong nhiều phút có thể làm chậm DB và mất SLA. Hãy tách retry vào đúng tầng và tránh các retry policy lồng nhau nhân số requests.

---

## 22. Bộ test và tình huống lỗi nên có

| Kịch bản | Kỳ vọng |
|---|---|
| File hợp lệ 100% | Không reject, report skip=0, job COMPLETED |
| Một dòng amount không parse được | `readSkipCount=1`, có reject READ |
| Một dòng amount âm | `processSkipCount=1`, có reject PROCESS |
| Ba lỗi, limit 3 | COMPLETED, reject=3, report đúng |
| Bốn lỗi, limit 3 | FAILED, không publish success report |
| File không tồn tại | FAILED tại open reader, không skip |
| File empty có header | Theo contract: read=0; cần alert input rỗng nếu bất thường |
| Duplicate order ID ở writer | FAILED theo policy demo |
| Bảng reject không ghi được | FAILED; không tiếp tục import im lặng |
| Report directory không ghi được | import COMPLETED, report FAILED, job FAILED |
| Report step restart sau lỗi | Import đã completed không bị đọc lại; report tạo lại |
| File bị sửa giữa restart | Block nhờ snapshot/checksum validation |
| Retry item thành công | Không tạo reject giả |
| Processor trả null | Filter, không xuất reject skip |
| Schema CSV đổi cột | Validation/parser fail theo policy; cần file-level validation |
| File chứa ký tự Unicode | Encoding UTF-8 đúng |
| Record chứa dữ liệu nhạy cảm | Report chỉ chứa metadata được phép |
| Nhiều job song song | fileId và report target độc lập |
| Listener chạy lại khi rollback | Unique key/transaction kiểm soát duplicate |
| Output side effect ngoài DB | Có outbox/idempotency/reconciliation |

### 22.1. Lỗi tại một chunk cụ thể

Khi thử lỗi writer, phải biết chunk size và thứ tự fixture để dự đoán commit nào đã thành công. Một step FAILED sau ba chunk không đồng nghĩa bảng output rỗng; các chunk đã commit trước đó thường vẫn còn dữ liệu.

### 22.2. Trường hợp report file đã tồn tại

Nếu report cũ đã được publish nhưng job crash trước khi cập nhật metadata, lần restart có thể viết lại file theo cùng tên. Việc overwrite atomic trong demo là idempotency của **đầu ra nội bộ**, nhưng nếu file đã được consumer bên ngoài tải xuống thì phiên bản mới phải có quy tắc publish/version/notification riêng. Không âm thầm gửi hai báo cáo có nội dung khác nhau cho cùng fileId.

### 22.3. Source input chưa hoàn chỉnh

Trước khi chạy `FlatFileItemReader`, cần ready marker/manifest hoặc quy ước publish an toàn. Một producer còn đang upload có thể làm batch thấy EOF sớm, rồi hoàn tất với ít dòng và không có parse error. Skip report không tự phát hiện missing tail; checksum/expected record count mới bảo vệ dataset integrity.

---

## 23. Hiệu năng và vận hành

### 23.1. Tác động của SkipListener lên throughput

Mỗi skip trong demo thực hiện một `MERGE` vào database. Với skipLimit=3, overhead nhỏ. Nếu nguồn có hàng triệu dòng lỗi và được phép skip hàng chục nghìn record, per-item SQL sẽ tăng network/transaction overhead.

Các hướng tối ưu:

- Tập hợp reject theo chunk trong cùng transaction qua một buffer có giới hạn và flush đúng thời điểm.
- Dùng bulk insert/UPSERT với unique key.
- Đưa quarantine ra bảng riêng có partition/index thích hợp.
- Giữ metadata report nhỏ, không chứa payload.
- Chọn skip limit theo yêu cầu dữ liệu, không theo hiệu năng.
- Theo dõi reject write latency để phát hiện bottleneck.

Cần lưu ý callback SkipListener có thứ tự quanh commit của framework; một buffer tùy biến phải được flush trước commit đúng transaction và rollback an toàn. Không tự gom reject trong singleton list vô hạn và flush ở `afterJob`.

### 23.2. Memory của report

Bản demo dùng `List<RejectedLine>` và `StringBuilder` vì skipLimit=3. Nếu limit có thể lên 100.000 lỗi, report có thể dùng hàng trăm MiB heap.

Thiết kế production:

```text
JdbcTemplate streaming/row callback
             │
             ▼
BufferedWriter vào report.tmp
             │
             ▼
flush/close
             │
             ▼
atomic move / conditional publish
```

Cần áp giới hạn kích thước file/report, quyền truy cập và retention; nếu báo cáo phải được phân tích bằng BI, có thể giữ reject trong database rồi xuất theo trang thay vì một file lớn.

### 23.3. Chunk size và rollback

Chunk nhỏ làm checkpoint thường xuyên, giúp giảm số record phải xử lý lại khi lỗi, nhưng tăng commit overhead. Chunk lớn giảm số lần commit, nhưng rollback chứa nhiều item và có thể tiêu tốn memory.

Với dự án thực hành, chunk size 3 dễ quan sát. Trong production, thử 100/500/1000 tùy kích thước record, đo throughput, transaction time, GC, DB load và thời gian restart. Không thay đổi skip limit chỉ vì thay chunk size.

### 23.4. Multi-threaded hoặc partitioned step

Khi nhiều worker chạy song song, bảo đảm:

- Mỗi reader có state độc lập hoặc được đồng bộ đúng.
- `fileId + lineNumber` vẫn xác định duy nhất record ở từng partition, hoặc thêm `resourceId` nếu mỗi partition là file riêng.
- `SkipListener` stateless hoặc có scope đúng; không giữ mutable shared counter không an toàn.
- Không có hai worker ghi cùng report target đồng thời.
- Tổng skip limit theo từng StepExecution có thể không tương đương giới hạn **toàn job** khi chia partition; cần aggregate và enforce global policy nếu nghiệp vụ yêu cầu.

### 23.5. Report theo đối tác và thời gian

Ở hệ thống nhiều đối tác, có thể thêm `partnerId` và `businessDate` nhưng phải phân quyền truy cập, chọn nơi giữ dữ liệu và tách schema. Không nên trộn rejected rows của các đối tác trong một file report công khai, hoặc dùng tên file tùy ý từ input để tạo đường dẫn.

---

## 24. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dòng sai vẫn làm job FAILED | Chưa `faultTolerant`, exception chưa trong whitelist | Cấu hình skip đúng loại và test |
| Job COMPLETED nhưng không có reject report | Processor dùng `return null` nên chỉ filter | Throw exception được skip nếu đó là lỗi cần báo cáo |
| `readSkipCount` khác số dòng lỗi | Reader bỏ header/comment, parse behavior khác | Định nghĩa line semantics và kiểm tra fixture |
| SkipListener không nhận item ở onSkipInRead | Item chưa parse được | Dùng `FlatFileParseException.getLineNumber()` |
| Ghi raw input vào log | Dùng `getInput()`/`toString()` tùy tiện | Lưu line number + error code |
| Report có reject nhưng DB output rollback | Reject ghi ra file ngoài transaction | Persist reject qua JDBC cùng transaction |
| Job vượt skip limit mà report vẫn báo success | Flow/report không kiểm tra import status | Dừng flow khi FAILED hoặc phát incident report riêng |
| Report step thất bại sau khi import success | File permission/storage/atomic rename | Sửa report storage, restart cùng JobInstance |
| Restart đọc nhầm record | File thay giữa hai lần | Pin file version, checksum, immutable snapshot |
| Bản ghi tốt bị duplicate khi restart | Writer không idempotent hoặc output external | Unique key, upsert/reconciliation phù hợp |
| Skip writer làm mất dữ liệu quan trọng | Skip quá rộng, JDBC side effect không rõ | Không skip writer nếu chưa có policy rõ |
| Mọi exception đều bị skip | `skip(Exception.class)` quá rộng | Whitelist exception chuyên biệt |
| Báo cáo missing một vài reject | Listener write DB thất bại hoặc sai DataSource | Cùng transaction, reconcile reject count |
| H2 giữ dữ liệu sau restart JVM? | H2 in-memory không durable | Dùng DB production bền vững |
| Report file chứa tên/path bất thường | fileId chưa validate | Whitelist fileId và directory cố định |
| Tốc độ chậm khi nhiều lỗi | MERGE mỗi skip + index/IO | Bounded bulk reject writes trong transaction |
| Chạy cùng fileId nhiều JobInstance | Identifying params không chuẩn | Business fileId/snapshotId làm identity |
| Report generatedAt đổi sau restart | Dùng đồng hồ hiện tại ở report step | Dùng mốc lưu trong metadata nếu cần byte-identical |

---

## 25. Bài tập mở rộng

### Bài 1 — Thêm lỗi currency

Thêm dòng:

```csv
109,1009,12.00,XYZ
```

Đặt skipLimit=4 và kiểm tra `processSkipCount`, reject row `UNSUPPORTED_CURRENCY` và report mới. Sau đó giữ limit=3 để xác nhận job FAILED đúng ngưỡng.

### Bài 2 — Chính sách fail nghiêm trọng

Thay policy để `INVALID_ORDER_ID` làm step fail ngay, còn `NON_POSITIVE_AMOUNT` được skip. Viết test riêng cho cả hai loại error. Giải thích tại sao cùng là lỗi nghiệp vụ nhưng có mức độ rủi ro khác nhau.

### Bài 3 — Báo cáo CSV hai file

Tạo `summary.json` và `rejects.csv` thay vì một file text. Giữ cơ chế staging/atomic publish, đảm bảo consumer chỉ nhận **cả bộ report** sau khi hai file hoàn chỉnh và có manifest.

### Bài 4 — Quarantine có workflow sửa lỗi

Thêm bảng `reject_resolution` ghi `fileId`, `lineNumber`, `status`, người sửa, thời gian và phiên bản dữ liệu được sửa. Tạo job reprocess riêng chỉ xử lý lỗi đã được phê duyệt, không âm thầm thay snapshot ban đầu.

### Bài 5 — Validation tỷ lệ

Ngoài `skipLimit=100`, thêm chính sách job fail nếu tỷ lệ lỗi vượt 2%. Định nghĩa mẫu số rõ, xử lý trường hợp input rỗng và xác định khi nào kiểm tra (trước report, sau khi đọc hết, hoặc fail sớm khi đủ bằng chứng).

### Bài 6 — Idempotent writer

Thay `INSERT` bằng UPSERT có kiểm soát phù hợp database mục tiêu. Nếu cùng `fileId+orderId` nhưng amount khác, phải fail hoặc ghi incident chứ không âm thầm ghi đè. Test crash/restart.

### Bài 7 — Report khi import FAILED

Thiết kế workflow tạo **incident report** sau step import FAILED nhưng giữ trạng thái cuối Job FAILED. Dữ liệu incident report phải phân biệt counter đã persist và phần chunk rollback; không được công bố nó như báo cáo hoàn tất.

### Bài 8 — Chạy nhiều file

Dùng `MultiResourceItemReader` với manifest bất biến. Thêm `resourceId` vào reject key vì cùng `lineNumber` có thể xuất hiện ở nhiều file. Test restart không đổi thứ tự file.

### Bài 9 — Bảo mật dữ liệu nhạy cảm

Giả định CSV có số tài khoản và email. Thiết kế report chỉ chứa hashed/business reference, error code, line number. Phân quyền người vận hành, đặt retention cho file gốc và quarantine, tránh PII trong log.

### Bài 10 — Monitoring

Xuất metric số skip theo giai đoạn và tổng skip rate theo đối tác. Viết alert nếu skipRate vượt ngưỡng hoặc reportStep không hoàn thành trước deadline. Dùng label có cardinality thấp.

---

## 26. Tài liệu tham khảo

- [Spring Batch — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): `faultTolerant`, `skip` và `skipLimit`.
- [Spring Batch — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): phân biệt retry và skip.
- [Spring Batch — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listener và callback.
- [Spring Batch — SkipListener API 5.2](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/SkipListener.html): `onSkipInRead`, `onSkipInProcess` và `onSkipInWrite`.
- [Spring Batch — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): `FlatFileItemReader`, `LineMapper` và parse errors.
- [Spring Batch — JdbcBatchItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC writer và database I/O.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): transaction, commit và chunk.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, counters.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint và restart.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` và `JobLauncherTestUtils`.
- [Spring Boot — JDBC / SQL Initialization](https://docs.spring.io/spring-boot/reference/data/sql.html): tự khởi tạo schema trong môi trường demo.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction cho JDBC và giới hạn giữa các resource.

## 27. Tổng kết

Xử lý skip dữ liệu lỗi **không phải** đặt `.skip(Exception.class)` rồi để job chạy đến cuối. Thiết kế tốt cần phân loại rõ **lỗi parse**, **lỗi nghiệp vụ**, **lỗi tạm thời cần retry** và **lỗi bắt buộc fail**; đặt skip limit hữu hạn; ghi rejected items bằng khóa ổn định; đối chiếu số liệu từ `StepExecution` và reject store; và chỉ phát hành báo cáo hoàn tất khi import thành công.

Dự án trên minh họa một cách thực tế: `FlatFileItemReader` giữ số dòng, `ItemProcessor` ném exception chuyên biệt, fault-tolerant step skip đúng whitelist, `SkipListener` lưu reject trong cùng transaction database, còn một report step riêng kiểm tra số liệu và publish file. Khi thêm restart, input immutable, writer idempotency, alert và phân quyền báo cáo, pipeline có thể vừa tiếp nhận dữ liệu hợp lệ kịp thời vừa **không che giấu dữ liệu sai**, bảo đảm rằng mọi dòng bị loại đều có lý do và có đường xử lý tiếp theo.
