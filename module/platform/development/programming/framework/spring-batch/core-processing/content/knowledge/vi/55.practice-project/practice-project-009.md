# Tạo job flow nhiều step — dự án thực hành Spring Batch Core Processing

## 1. Bài toán và sản phẩm cần xây dựng

Một doanh nghiệp nhận file CSV đơn hàng từ đối tác mỗi ngày. File có thể chứa đơn hàng hợp lệ lẫn dữ liệu thiếu/sai. Đội vận hành cần một batch job có quy trình **rõ từng giai đoạn**, chỉ xuất bản dữ liệu khi đã vượt qua bước kiểm tra chất lượng, đồng thời có khả năng dừng và tiếp tục khi dữ liệu được sửa.

Thay vì để một step làm tất cả, ta thiết kế **job flow nhiều step**:

1. **Prepare** — xác nhận kỳ nghiệp vụ và tạo một dấu vết vận hành.
2. **Import** — đọc CSV, kiểm tra dữ liệu từng item và ghi vào bảng staging theo chunk.
3. **Quality gate** — đếm bản ghi sai, kiểm tra trùng mã đơn, quyết định PASS hoặc HOLD.
4. **Publish** — nếu PASS, chuyển dữ liệu hợp lệ từ staging sang bảng chính.
5. **Summary** — ghi nhận batch đã được xuất bản.
6. **Hold** — nếu HOLD, ghi nhận lý do, dừng Job để vận hành xử lý rồi restart tại quality gate.

Đây là một bài thực hành về **luồng điều khiển job (flow)**, không chỉ bài đọc/ghi CSV.

```text
                        orderFlowJob
                             |
                             v
                       prepareStep
                             |
                             v
                        importStep
                   (reader / processor /
                     writer theo chunk)
                             |
                             v
                       qualityGateStep
                         /          \
                    PASS /            \ HOLD
                        v              v
                   publishStep       holdStep
                        |              |
                        v              v
                   summaryStep      STOPPED
                        |          restart tại
                        v          qualityGateStep
                    COMPLETED
```

**Kết quả cần đạt:**

- Chạy lần đầu với một file có số record lỗi nằm trong ngưỡng: `JobExecution` kết thúc `COMPLETED` và dữ liệu hợp lệ xuất hiện trong bảng chính.
- Chạy với ngưỡng nghiêm ngặt hơn: `JobExecution` kết thúc `STOPPED`, không xuất bản dữ liệu.
- Sau khi sửa bản ghi staging có lỗi, **restart đúng `JobInstance`**: quality gate chạy lại và job đi tiếp tới publish/summary, không nhập lại file không cần thiết.
- Nếu step import gặp lỗi kỹ thuật thật, job chuyển `FAILED`, có thể điều tra và restart từ metadata.
- Không tạo `JobInstance` mới bằng timestamp tùy tiện để né lỗi restart.

Bài sử dụng **Java 17+, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, H2 và JUnit 5**. Đây là dự án mẫu quy mô nhỏ; mục sản xuất sẽ chỉ ra các thay đổi cần thiết cho PostgreSQL, file lớn, nhiều worker và audit chính thức.

---

## 2. Từ chuỗi step đơn giản đến flow có điều kiện

### 2.1. `Job` và `Step` có nhiệm vụ khác nhau

**`Job`** là định nghĩa công việc logic: gồm các step, thứ tự thực thi và luật chuyển nhánh.

**`Step`** là một đơn vị xử lý có transaction/lifecycle/metadata riêng. Step có thể là:

- **Tasklet step:** thực hiện một thao tác như chuẩn bị, kiểm tra điều kiện, di chuyển file, cập nhật audit.
- **Chunk-oriented step:** lặp `read → process → write` với ranh giới commit theo nhóm item.
- Một bước kỹ thuật khác phù hợp với Spring Batch, tùy nhu cầu và phiên bản.

Mỗi lần chạy job tạo một **`JobExecution`**, trong đó có các **`StepExecution`**. Một `JobInstance` có thể có nhiều `JobExecution` khi cần restart sau `FAILED` hoặc `STOPPED`.

### 2.2. Flow tuần tự

Job đơn giản chỉ đi theo một đường:

```java
return new JobBuilder("simpleJob", jobRepository)
    .start(stepA)
    .next(stepB)
    .next(stepC)
    .build();
```

Nếu step A hoàn thành, framework tiến đến B, rồi C. Nếu một step thất bại và không có chuyển tiếp đặc biệt, job thường thất bại thay vì chạy các step tiếp theo.

### 2.3. Flow có nhánh

Một flow nhiều step thực tế cần **đánh giá `ExitStatus`** của step để quyết định đường đi:

```text
qualityGateStep
   |
   +-- ExitStatus=PASS --> publishStep --> summaryStep
   |
   +-- ExitStatus=HOLD --> holdStep ----> STOPPED
   |
   +-- lỗi kỹ thuật ----> FAILED
```

Ở Spring Batch, **`BatchStatus`** và **`ExitStatus`** không giống nhau:

| Thuộc tính | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| `BatchStatus` | Trạng thái vòng đời của step/job | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |
| `ExitStatus` | Kết quả dùng để xây flow transition | `COMPLETED`, `FAILED`, hoặc custom `PASS`, `HOLD` |
| Pattern `on(...)` | So khớp với **exit code**, không phải trực tiếp BatchStatus | `on("PASS")`, `on("HOLD")` |
| `to(step)` | Chuyển đến step tiếp theo | `to(publishStep)` |
| `stopAndRestart(step)` | Dừng flow với điểm restart đã định | `stopAndRestart(qualityGateStep)` |

Một quality-gate tasklet có thể chạy thành công về mặt kỹ thuật (BatchStatus `COMPLETED`) nhưng đặt ExitStatus là `HOLD` vì dữ liệu chưa đủ chất lượng. Flow chọn nhánh HOLD và JobExecution được dừng có chủ đích.

### 2.4. Flow không phải vòng lặp Java

Đừng dùng một `while(true)` trong tasklet để “chờ dữ liệu được sửa” hoặc tự gọi một step như method Java. Flow transition giúp Spring Batch lưu metadata, cho phép operator hiểu job đang ở đâu, và cung cấp restart semantics.

---

## 3. Kiến trúc dự án mẫu

### 3.1. Cấu trúc thư mục

Tạo một project Spring Boot Gradle cơ bản:

```text
order-flow-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/com/example/orderflow/
    │   │   ├── OrderFlowApplication.java
    │   │   ├── RawOrder.java
    │   │   ├── StagedOrder.java
    │   │   ├── OrderRuleProcessor.java
    │   │   ├── OrderFlowConfiguration.java
    │   │   └── DemoRunner.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── orders-demo.csv
    └── test/
        └── java/com/example/orderflow/
            └── OrderFlowIntegrationTest.java
```

Các đoạn code được trình bày theo từng file. Để thử nghiệm, bạn có thể đặt chung các record/class trong cùng package theo cấu trúc trên.

### 3.2. Gradle dependencies

Ví dụ `build.gradle` dùng Spring Boot 3.3.x làm mẫu cấu hình tương thích Java 17/Spring Batch 5.x. Khi thực hiện trên dự án thật, chọn bản Spring Boot 3.x đã được nhóm của bạn duy trì và được phép dùng.

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`settings.gradle`:

```groovy
rootProject.name = 'order-flow-demo'
```

Không cần `@EnableBatchProcessing` khi để Spring Boot quản lý Batch auto-configuration như ví dụ này. Trong một số cấu hình, thêm annotation đó khiến auto-configuration của Boot nhường quyền cho cấu hình Batch thủ công; lúc đó datasource/JobOperator/JobRepository cần được xem lại.

### 3.3. `application.yml`

Dùng H2 **in-memory** để dễ chạy demo:

```yaml
spring:
  application:
    name: order-flow-demo

  datasource:
    url: jdbc:h2:mem:orderflow;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  sql:
    init:
      mode: always

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

logging:
  level:
    org.springframework.batch: INFO
    com.example.orderflow: INFO
```

Giải thích:

- `spring.batch.job.enabled=false`: không để Boot tự chạy mọi job lúc startup; ta chủ động launch từ demo runner hoặc test.
- `spring.batch.jdbc.initialize-schema=always`: khởi tạo bảng metadata `BATCH_*` trong H2 cho môi trường demo.
- `spring.sql.init.mode=always`: chạy `schema.sql` để tạo bảng nghiệp vụ.
- H2 in-memory **không giữ được metadata khi JVM chết**. Nếu cần chứng minh restart sau process crash, hãy dùng PostgreSQL hoặc H2 file-based với schema migration an toàn.

**Production không nên bật các schema initialization settings vô điều kiện** lên database có lịch sử Batch quan trọng. Hãy dùng Flyway/Liquibase và version schema đúng.

---

## 4. Dữ liệu đầu vào và các bảng nghiệp vụ

### 4.1. CSV có cả record hợp lệ và bị từ chối

`src/main/resources/orders-demo.csv`:

```csv
orderId,customerId,amount,status
O-100,C-01,120.00,READY
O-101,C-02,50.50,READY
O-102,C-03,-9.00,READY
O-103,C-04,70.00,READY
O-104,C-05,0.00,READY
```

Ta có:

- **5** dòng dữ liệu.
- **3** đơn hợp lệ: O-100, O-101, O-103.
- **2** đơn lỗi amount không dương: O-102, O-104.
- Không có mã đơn trùng trong danh sách hợp lệ.

Để bài học chủ yếu tập trung vào flow, record lỗi không làm step import thất bại: processor chuyển nó thành một record `REJECTED` trong staging. Nếu CSV sai cấu trúc hoặc reader không thể mở file, import step vẫn `FAILED`.

### 4.2. Bảng staging

`schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS STG_ORDER (
    BUSINESS_DATE DATE NOT NULL,
    SOURCE_LINE INTEGER NOT NULL,
    ORDER_ID VARCHAR(64),
    CUSTOMER_ID VARCHAR(64),
    AMOUNT DECIMAL(18, 2),
    RECORD_STATUS VARCHAR(12) NOT NULL,
    REJECT_REASON VARCHAR(64),
    PRIMARY KEY (BUSINESS_DATE, SOURCE_LINE)
);
```

Khóa `(BUSINESS_DATE, SOURCE_LINE)` phù hợp cho một file mỗi ngày trong demo. Nó tránh việc một dòng có `ORDER_ID` rỗng khiến không thể lưu reject. Trong hệ thống nhiều file/tenant, khóa nên mở rộng thành `(TENANT_ID, SOURCE_FILE_ID, SOURCE_LINE)` hoặc khóa nguồn có ý nghĩa tương đương.

### 4.3. Bảng dữ liệu chính

Cũng trong `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS PUBLISHED_ORDER (
    BUSINESS_DATE DATE NOT NULL,
    ORDER_ID VARCHAR(64) NOT NULL,
    CUSTOMER_ID VARCHAR(64) NOT NULL,
    AMOUNT DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (BUSINESS_DATE, ORDER_ID)
);
```

Business key trong demo là `(BUSINESS_DATE, ORDER_ID)`. Unique constraint ngăn xuất bản hai bản sao của cùng đơn trong một ngày. Khi áp dụng thực tế, khóa phải tuân theo hợp đồng nghiệp vụ: một order ID có thể cần thêm tenant/source/version.

### 4.4. Bảng trạng thái của flow

Cuối file `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS FLOW_AUDIT (
    BUSINESS_DATE DATE PRIMARY KEY,
    FLOW_STATE VARCHAR(32) NOT NULL,
    NOTE VARCHAR(512)
);
```

Bảng `FLOW_AUDIT` chỉ là audit đơn giản của bài thực hành. `JobRepository` vẫn là nguồn dữ liệu để biết chính xác `JobExecution`, `StepExecution` và checkpoint. Không thay thế bảng `BATCH_*` bằng audit table này.

### 4.5. Tại sao dùng staging rồi mới publish?

Nếu ghi trực tiếp vào bảng chính trong import step, đến khi quality gate phát hiện hai đơn lỗi, các chunk trước có thể đã commit. Job `FAILED` hoặc `STOPPED` **không tự rollback tất cả chunk của toàn job**.

Staging cho phép:

```text
Import chunks -> COMMITTED vào STG_ORDER
                          |
                          v
                    Quality gate
                          |
                  +-------+--------+
                  |                |
                PASS              HOLD
                  |                |
                  v                v
         PUBLISHED_ORDER     Không publish
```

Như vậy dữ liệu đã được nạp để kiểm tra nhưng chưa trở thành dữ liệu được công bố. Đây là cơ chế phổ biến khi yêu cầu **data quality gate**.

---

## 5. Domain model: raw input và staged result

### 5.1. `RawOrder.java`

```java
package com.example.orderflow;

public record RawOrder(
    int sourceLine,
    String orderId,
    String customerId,
    String amountText,
    String statusText
) {
}
```

Ta giữ `amountText` dưới dạng `String` để processor chủ động quyết định lỗi dữ liệu; reader không tự ném lỗi khi amount âm hoặc không parse được thành số.

`sourceLine` là vị trí dòng từ CSV, giúp định danh record staging kể cả khi `orderId` thiếu. Với file có header ở dòng 1, dữ liệu đầu bắt đầu dòng 2.

### 5.2. `StagedOrder.java`

```java
package com.example.orderflow;

import java.math.BigDecimal;
import java.time.LocalDate;

public record StagedOrder(
    LocalDate businessDate,
    int sourceLine,
    String orderId,
    String customerId,
    BigDecimal amount,
    String recordStatus,
    String rejectReason
) {
}
```

Hai trạng thái `recordStatus` trong ví dụ:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `VALID` | Đơn đủ điều kiện xuất bản |
| `REJECTED` | Đơn không đạt business rule; giữ thông tin lỗi |

Trạng thái này là **domain status trong bảng staging**, không phải `BatchStatus` của Spring Batch.

---

## 6. Processor phân loại dữ liệu

### 6.1. `OrderRuleProcessor.java`

```java
package com.example.orderflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.batch.item.ItemProcessor;

public final class OrderRuleProcessor
        implements ItemProcessor<RawOrder, StagedOrder> {

    private final LocalDate businessDate;

    public OrderRuleProcessor(LocalDate businessDate) {
        this.businessDate = businessDate;
    }

    @Override
    public StagedOrder process(RawOrder raw) {
        String orderId = clean(raw.orderId());
        String customerId = clean(raw.customerId());
        String status = clean(raw.statusText())
            .toUpperCase(Locale.ROOT);

        String reason = null;
        BigDecimal amount = null;

        if (orderId.isBlank()) {
            reason = "ORDER_ID_REQUIRED";
        } else if (customerId.isBlank()) {
            reason = "CUSTOMER_ID_REQUIRED";
        } else if (!"READY".equals(status)) {
            reason = "STATUS_UNSUPPORTED";
        } else {
            try {
                amount = new BigDecimal(
                    clean(raw.amountText())
                ).setScale(2, RoundingMode.UNNECESSARY);

                if (amount.signum() <= 0) {
                    reason = "AMOUNT_NON_POSITIVE";
                }
            } catch (NumberFormatException
                    | ArithmeticException exception) {
                reason = "AMOUNT_INVALID";
            }
        }

        String decision =
            reason == null ? "VALID" : "REJECTED";

        return new StagedOrder(
            businessDate,
            raw.sourceLine(),
            orderId,
            customerId,
            amount,
            decision,
            reason
        );
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim();
    }
}
```

**Các điểm thiết kế:**

- Mỗi input luôn tạo một `StagedOrder` — kể cả khi rejected. Processor không `return null` vì bài toán yêu cầu ghi nhận record lỗi.
- Processor không truy cập database và không gửi side effects, nên có thể được gọi lại khi rollback/restart mà không tạo hiệu ứng ngoài transaction.
- `LocalDate businessDate` được truyền khi step bắt đầu, không dùng `LocalDate.now()` mỗi lần process; như vậy rerun/restart hôm sau không đổi kỳ dữ liệu.
- `BigDecimal` dùng cho tiền; `setScale(2, RoundingMode.UNNECESSARY)` không làm tròn ngầm số tiền có quá nhiều chữ số thập phân.
- Rule code cố định, dễ tổng hợp báo cáo và remediation.

### 6.2. Tại sao không ném exception cho hai record amount âm?

Bởi hợp đồng của dự án là **nhập tất cả record vào staging và để quality gate quyết định**. Nếu processor ném exception rồi `skip`, record lỗi có thể biến mất khỏi luồng writer và cần cơ chế skip listener/quarantine riêng.

Với thiết kế này, import step có thể `COMPLETED` với 5 staged rows, nhưng gate không tự cho xuất bản. Tách kết quả kỹ thuật của import khỏi quyết định nghiệp vụ của publish giúp flow dễ hiểu.

### 6.3. Giới hạn của ví dụ

Một số yêu cầu production chưa nằm trong processor:

- Currency, tenant ownership, định dạng order ID, JSON payload, schema version.
- Trùng ID trong toàn file (giải quyết ở gate bằng truy vấn tổng hợp).
- Reference data của customer (cần snapshot/query được kiểm soát).
- Rule version theo ngày hiệu lực và audit đa phiên bản.

Các phần này là hướng mở rộng; không nên chuyển business rules liên record vào một `HashSet` mutable trong processor rồi giả định nó an toàn khi partition/restart.

---

## 7. Reader CSV với `FlatFileItemReader`

### 7.1. Cấu hình trong `OrderFlowConfiguration`

Ta khai báo reader theo `@StepScope` để có thể lấy `inputFile` từ JobParameters ngay khi step được chạy.

```java
@Bean
@StepScope
FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}")
        String inputFile,
        ResourceLoader resourceLoader) {

    DelimitedLineTokenizer tokenizer =
        new DelimitedLineTokenizer();

    tokenizer.setNames(
        "orderId",
        "customerId",
        "amount",
        "status"
    );

    return new FlatFileItemReaderBuilder<RawOrder>()
        .name("orderCsvReader")
        .resource(resourceLoader.getResource(inputFile))
        .linesToSkip(1)
        .strict(true)
        .lineMapper((line, lineNumber) -> {
            FieldSet fields = tokenizer.tokenize(line);

            return new RawOrder(
                lineNumber,
                fields.readString("orderId"),
                fields.readString("customerId"),
                fields.readString("amount"),
                fields.readString("status")
            );
        })
        .build();
}
```

Đây là method bean được đặt trong class cấu hình hoàn chỉnh ở mục 9; các imports tương ứng xuất hiện tại đó.

### 7.2. Reader có checkpoint

`FlatFileItemReader` implement contract `ItemStream`. Với tên `orderCsvReader` ổn định và `saveState` mặc định phù hợp, Spring Batch có thể lưu vị trí đọc vào `ExecutionContext` tại commit boundaries.

Khi import step `FAILED` sau một vài chunk, lần restart **cùng `JobInstance`** có thể mở reader tại vị trí đã được persist thay vì bắt đầu từ dòng đầu.

Để restart đúng, cần:

- File input vẫn tồn tại ở cùng nguồn dữ liệu logic.
- Nội dung file không bị thay đổi giữa executions, hoặc có versioning/snapshot rõ ràng.
- Reader được đăng ký đúng lifecycle `open/update/close`.
- JobRepository còn metadata `BATCH_STEP_EXECUTION_CONTEXT`.
- Không thay identifying parameters bằng timestamp mới.

### 7.3. Khi reader gặp lỗi cấu trúc

Nếu một dòng CSV thiếu cột hoặc file không mở được, reader có thể ném exception và step import chuyển `FAILED` theo cấu hình này. Đây là hành vi **fail fast với lỗi định dạng kỹ thuật**; còn amount âm đã được processor ghi thành `REJECTED`.

Nếu dự án muốn skip một số dòng không parse được và ghi quarantine, cần thêm `faultTolerant().skip(...)`, skip limit và cơ chế lưu raw line. Không nên bỏ qua tất cả exceptions của reader vì sẽ che lỗi file missing/encoding/schema.

---

## 8. Writer staging theo chunk

### 8.1. `JdbcBatchItemWriter`

Writer ghi toàn bộ `StagedOrder` vào bảng `STG_ORDER`. Để ví dụ có thể restart/replay an toàn, ta sử dụng `MERGE INTO ... KEY (...)` của **H2** thay vì insert vô điều kiện:

```java
@Bean
JdbcBatchItemWriter<StagedOrder> stagingWriter(
        DataSource dataSource) {

    String sql = """
        MERGE INTO STG_ORDER (
            BUSINESS_DATE,
            SOURCE_LINE,
            ORDER_ID,
            CUSTOMER_ID,
            AMOUNT,
            RECORD_STATUS,
            REJECT_REASON
        )
        KEY (BUSINESS_DATE, SOURCE_LINE)
        VALUES (
            :businessDate,
            :sourceLine,
            :orderId,
            :customerId,
            :amount,
            :recordStatus,
            :rejectReason
        )
        """;

    return new JdbcBatchItemWriterBuilder<StagedOrder>()
        .dataSource(dataSource)
        .sql(sql)
        .itemSqlParameterSourceProvider(item ->
            new MapSqlParameterSource()
                .addValue("businessDate",
                    java.sql.Date.valueOf(item.businessDate()))
                .addValue("sourceLine", item.sourceLine())
                .addValue("orderId", item.orderId())
                .addValue("customerId", item.customerId())
                .addValue("amount", item.amount())
                .addValue("recordStatus", item.recordStatus())
                .addValue("rejectReason", item.rejectReason()))
        .build();
}
```

**Lưu ý dialect:** cú pháp `MERGE ... KEY (...)` ở trên dành cho H2. Trong PostgreSQL, thường dùng `INSERT ... ON CONFLICT (...) DO UPDATE` với business key và semantics đã phê duyệt. Đừng copy cú pháp H2 sang PostgreSQL/Oracle mà không chuyển đổi.

### 8.2. Vì sao SQL dựa trên `SOURCE_LINE`?

Nếu một record có mã đơn sai hoặc rỗng, ta vẫn cần lưu nó vào staging để sửa. Khóa `SOURCE_LINE` cùng business date giúp giữ bản ghi từ nguồn dù không có orderId hợp lệ.

Khi input file có thể sửa sau khi import, row number có thể không còn đại diện cho cùng record; sản phẩm thật nên dùng **source file version + line number** hoặc stable external record ID. Bài mẫu giả định file không đổi trong cùng `JobInstance`.

### 8.3. Chunk commit

Chunk size 2 giúp dễ quan sát:

```text
input 1, 2 -> process -> write [1, 2] -> COMMIT
input 3, 4 -> process -> write [3, 4] -> COMMIT
input 5    -> process -> write [5]    -> COMMIT
```

Nếu writer lỗi ở chunk thứ ba, hai chunk trước có thể đã commit. Spring Batch không rollback toàn job theo cách một SQL transaction bao trùm tất cả chunk.

---

## 9. Cấu hình đầy đủ nhiều step

### 9.1. `OrderFlowConfiguration.java` — các imports và cấu hình

Các method bên dưới tạo đủ steps và job. Những bean demo dùng chung datasource H2 cho `JobRepository` và dữ liệu nghiệp vụ; production cần xem riêng transaction manager/resource boundaries.

```java
package com.example.orderflow;

import java.sql.Date;
import java.time.LocalDate;

import javax.sql.DataSource;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ResourceLoader;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderFlowConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}")
            String inputFile,
            ResourceLoader resourceLoader) {

        DelimitedLineTokenizer tokenizer =
            new DelimitedLineTokenizer();
        tokenizer.setNames(
            "orderId", "customerId", "amount", "status");

        return new FlatFileItemReaderBuilder<RawOrder>()
            .name("orderCsvReader")
            .resource(resourceLoader.getResource(inputFile))
            .linesToSkip(1)
            .strict(true)
            .lineMapper((line, lineNumber) -> {
                FieldSet fields = tokenizer.tokenize(line);

                return new RawOrder(
                    lineNumber,
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readString("amount"),
                    fields.readString("status"));
            })
            .build();
    }

    @Bean
    @StepScope
    OrderRuleProcessor orderRuleProcessor(
            @Value("#{jobParameters['businessDate']}")
            String businessDate) {

        return new OrderRuleProcessor(
            LocalDate.parse(businessDate));
    }

    @Bean
    JdbcBatchItemWriter<StagedOrder> stagingWriter(
            DataSource dataSource) {

        String sql = """
            MERGE INTO STG_ORDER (
                BUSINESS_DATE, SOURCE_LINE, ORDER_ID,
                CUSTOMER_ID, AMOUNT, RECORD_STATUS, REJECT_REASON
            )
            KEY (BUSINESS_DATE, SOURCE_LINE)
            VALUES (
                :businessDate, :sourceLine, :orderId,
                :customerId, :amount, :recordStatus, :rejectReason
            )
            """;

        return new JdbcBatchItemWriterBuilder<StagedOrder>()
            .dataSource(dataSource)
            .sql(sql)
            .itemSqlParameterSourceProvider(item ->
                new MapSqlParameterSource()
                    .addValue("businessDate",
                        Date.valueOf(item.businessDate()))
                    .addValue("sourceLine", item.sourceLine())
                    .addValue("orderId", item.orderId())
                    .addValue("customerId", item.customerId())
                    .addValue("amount", item.amount())
                    .addValue("recordStatus", item.recordStatus())
                    .addValue("rejectReason", item.rejectReason()))
            .build();
    }

    @Bean
    Step prepareStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("prepareStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                jdbc.update("""
                    MERGE INTO FLOW_AUDIT (
                        BUSINESS_DATE, FLOW_STATE, NOTE
                    ) KEY (BUSINESS_DATE)
                    VALUES (?, ?, ?)
                    """,
                    Date.valueOf(day),
                    "PREPARED",
                    "Input is ready for staging"
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Step importStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            OrderRuleProcessor orderRuleProcessor,
            JdbcBatchItemWriter<StagedOrder> stagingWriter) {

        return new StepBuilder("importStep", repository)
            .<RawOrder, StagedOrder>chunk(
                2, transactionManager)
            .reader(orderReader)
            .processor(orderRuleProcessor)
            .writer(stagingWriter)
            .build();
    }

    @Bean
    Step qualityGateStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("qualityGateStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);
                Date sqlDay = Date.valueOf(day);

                long total = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM STG_ORDER
                    WHERE BUSINESS_DATE = ?
                    """,
                    Long.class, sqlDay);

                long rejected = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM STG_ORDER
                    WHERE BUSINESS_DATE = ?
                      AND RECORD_STATUS = 'REJECTED'
                    """,
                    Long.class, sqlDay);

                long duplicateIds = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT ORDER_ID
                        FROM STG_ORDER
                        WHERE BUSINESS_DATE = ?
                          AND RECORD_STATUS = 'VALID'
                        GROUP BY ORDER_ID
                        HAVING COUNT(*) > 1
                    ) duplicated
                    """,
                    Long.class, sqlDay);

                Long configured =
                    contribution.getStepExecution()
                        .getJobParameters()
                        .getLong("maxRejected");

                if (configured == null || configured < 0) {
                    throw new IllegalArgumentException(
                        "maxRejected must be >= 0");
                }

                boolean pass =
                    total > 0 &&
                    rejected <= configured &&
                    duplicateIds == 0;

                String message =
                    "total=" + total
                    + ", rejected=" + rejected
                    + ", duplicateIds=" + duplicateIds
                    + ", limit=" + configured;

                contribution.setExitStatus(
                    new ExitStatus(
                        pass ? "PASS" : "HOLD",
                        message
                    )
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            // Khi STOPPED tại HOLD, restart phải đánh giá
            // lại quality gate sau khi data steward sửa staging.
            .allowStartIfComplete(true)
            .build();
    }

    @Bean
    Step publishStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("publishStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                // H2: set-based MERGE, không nhân đôi
                // business key khi cần thực thi lại.
                jdbc.update("""
                    MERGE INTO PUBLISHED_ORDER (
                        BUSINESS_DATE,
                        ORDER_ID,
                        CUSTOMER_ID,
                        AMOUNT
                    )
                    KEY (BUSINESS_DATE, ORDER_ID)
                    SELECT
                        BUSINESS_DATE,
                        ORDER_ID,
                        CUSTOMER_ID,
                        AMOUNT
                    FROM STG_ORDER
                    WHERE BUSINESS_DATE = ?
                      AND RECORD_STATUS = 'VALID'
                    """,
                    Date.valueOf(day)
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Step summaryStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("summaryStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                jdbc.update("""
                    MERGE INTO FLOW_AUDIT (
                        BUSINESS_DATE, FLOW_STATE, NOTE
                    ) KEY (BUSINESS_DATE)
                    VALUES (?, ?, ?)
                    """,
                    Date.valueOf(day),
                    "PUBLISHED",
                    "Quality gate passed; output published"
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Step holdStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("holdStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                jdbc.update("""
                    MERGE INTO FLOW_AUDIT (
                        BUSINESS_DATE, FLOW_STATE, NOTE
                    ) KEY (BUSINESS_DATE)
                    VALUES (?, ?, ?)
                    """,
                    Date.valueOf(day),
                    "HOLD",
                    "Fix staging records then restart the same instance"
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .allowStartIfComplete(true)
            .build();
    }

    private static LocalDate businessDate(
            org.springframework.batch.core.StepContribution contribution) {

        String text = contribution.getStepExecution()
            .getJobParameters()
            .getString("businessDate");

        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                "businessDate is required");
        }
        return LocalDate.parse(text);
    }

    // Bean orderFlowJob được trình bày ở mục 10.
}
```

Đây là class chứa infrastructure/step definitions. Trong code thật, có thể tách từng step thành các `@Configuration` nhỏ hơn, nhưng cùng một file giúp người học thấy toàn bộ dependency của flow.

### 9.2. Vì sao quality gate đặt `allowStartIfComplete(true)`?

`qualityGateStep` được thực thi thành công về mặt kỹ thuật cả khi đặt `ExitStatus.HOLD`. Vì thế `BatchStatus` của step có thể là `COMPLETED`. Khi job `STOPPED` rồi restart, nếu không cho quality gate chạy lại, Spring Batch có thể bỏ qua completed step; kết quả cũ không được đánh giá lại sau khi staging được sửa.

Cấu hình:

```java
.allowStartIfComplete(true)
```

trong demo thể hiện chủ ý **re-evaluate gate khi restart**. Không nên đặt thuộc tính này cho mọi step một cách mặc định: một step đã completed có thể tạo side effect không an toàn nếu chạy lại.

### 9.3. Vì sao không dùng `LocalDate.now()` cho businessDate?

Một job được launch ngày 16 nhưng phải restart ngày 17 vẫn xử lý **cùng kỳ**. `businessDate` phải lấy từ identifying `JobParameters`, không từ thời gian runtime hiện tại. Nếu đổi identifying parameters, Spring Batch có thể tạo `JobInstance` mới và không dùng checkpoint/flow state cũ.

---

## 10. Khai báo conditional Job flow

Trong class `OrderFlowConfiguration` ở mục 9, thêm method bean sau trước dấu `}` cuối của class:

```java
@Bean
Job orderFlowJob(
        JobRepository repository,
        Step prepareStep,
        Step importStep,
        Step qualityGateStep,
        Step publishStep,
        Step summaryStep,
        Step holdStep) {

    return new JobBuilder("orderFlowJob", repository)
        .start(prepareStep)
        .next(importStep)
        .next(qualityGateStep)
            .on("PASS").to(publishStep)
        .from(qualityGateStep)
            .on("HOLD").to(holdStep)
        .from(holdStep)
            .on("COMPLETED")
            .stopAndRestart(qualityGateStep)
        .from(publishStep)
            .on("COMPLETED").to(summaryStep)
        .end()
        .build();
}
```

### 10.1. Diễn giải từng phần

```java
.start(prepareStep)
.next(importStep)
.next(qualityGateStep)
```

Xác định thứ tự chung của mọi lần chạy: chuẩn bị → import → đánh giá chất lượng.

```java
.on("PASS").to(publishStep)
```

Khi exit code của quality gate là `PASS`, đi đến publish.

```java
.from(qualityGateStep)
    .on("HOLD").to(holdStep)
```

Thêm nhánh xuất phát **cũng từ quality gate** cho trường hợp dữ liệu chưa đạt yêu cầu.

```java
.from(holdStep)
    .on("COMPLETED")
    .stopAndRestart(qualityGateStep)
```

Sau khi hold step ghi audit thành công, JobExecution được dừng có chủ ý với **điểm restart là qualityGateStep**. Khi vận hành sửa dữ liệu staging và restart cùng instance, flow có thể kiểm tra lại, không cần chạy lại import từ đầu.

```java
.from(publishStep)
    .on("COMPLETED").to(summaryStep)
```

Sau khi publish thành công, ghi summary. Nếu publish lỗi không có transition `COMPLETED`, job không tự đi qua summary như một success path.

```java
.end()
.build();
```

Kết thúc khai báo flow và tạo job object.

### 10.2. `on("*")` phải dùng có chủ đích

Spring Batch hỗ trợ pattern matching theo exit code, ví dụ `on("*")` là wildcard. Nhưng:

```java
.from(publishStep).on("*").to(summaryStep)
```

có thể vô tình coi một exit code ngoài `COMPLETED` là lý do để bước summary chạy. Với pipeline quan trọng, hãy đặt đường thành công rõ và để lỗi không mong muốn khiến job thất bại, hoặc khai báo error transition chuyên dụng.

Tương tự, không nên viết `.on("*").end()` tại gate nếu nó có thể **che lỗi kỹ thuật**. Một step `FAILED` nên dẫn đến trạng thái job fail, trừ khi nghiệp vụ thiết kế recovery branch rõ và an toàn.

### 10.3. `.end()`, `.fail()` và `.stopAndRestart()` không tương đương

Trong flow builder của Spring Batch:

| Transition | Ý nghĩa | Khi nào hợp lý |
| --- | --- | --- |
| `.end()` | Kết thúc flow bằng trạng thái hoàn tất cho path đó | Đường kết thúc hợp lệ |
| `.fail()` | Kết thúc flow thất bại | Khi contract yêu cầu JobExecution FAILED |
| `.stopAndRestart(step)` | Dừng job với bước được chỉ định khi restart | Tạm giữ dữ liệu chờ thao tác rồi tiếp tục |
| `.to(step)` | Đi tới step khác | Chạy xử lý kế tiếp |

Đặc biệt, `.end()` trên một transition **không có nghĩa rollback các chunk trước đó**, và nếu dùng để kết thúc một đường lỗi có thể khiến Job `COMPLETED` theo cách không mong muốn. Phải kiểm thử **BatchStatus cuối của JobExecution**, không chỉ exit code của một step.

### 10.4. Khi nào nên dùng `JobExecutionDecider`?

Với điều kiện dựa trên nhiều step, external system hoặc kết quả audit phức tạp, Spring Batch có `JobExecutionDecider` để trả về `FlowExecutionStatus` và điều hướng flow.

Ví dụ minh họa:

```java
JobExecutionDecider decider = (jobExecution, stepExecution) -> {
    String flag = jobExecution.getExecutionContext()
        .getString("approvalFlag", "PENDING");

    return new FlowExecutionStatus(
        "APPROVED".equals(flag) ? "PASS" : "HOLD"
    );
};
```

Trong một flow sử dụng decider, có thể khai báo `.next(decider)` và `.from(decider).on("PASS").to(...)` theo DSL tương ứng của Spring Batch 5.

Dự án mẫu chọn **custom ExitStatus ngay tại qualityGateStep** vì quyết định phát sinh ở chính step kiểm tra; như vậy không cần thêm decider chỉ để minh họa một nhánh.

---

## 11. Điểm vào ứng dụng và cách chạy demo

### 11.1. `OrderFlowApplication.java`

```java
package com.example.orderflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            OrderFlowApplication.class, args);
    }
}
```

### 11.2. `DemoRunner.java`

Runner chỉ kích hoạt khi profile `demo` đang bật, tránh vô tình chạy job trong integration tests hoặc môi trường khác.

```java
package com.example.orderflow;

import java.util.List;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class DemoRunner {

    @Bean
    @Profile("demo")
    ApplicationRunner runDemo(
            JobLauncher launcher,
            @Qualifier("orderFlowJob") Job job) {

        return args -> {
            String date = option(
                args, "businessDate", "2026-11-16");

            String file = option(
                args, "inputFile",
                "classpath:orders-demo.csv");

            long maxRejected = Long.parseLong(
                option(args, "maxRejected", "2"));

            JobParameters parameters =
                new JobParametersBuilder()
                    .addString("businessDate", date, true)
                    .addString("inputFile", file, false)
                    .addLong("maxRejected", maxRejected, false)
                    .toJobParameters();

            JobExecution execution =
                launcher.run(job, parameters);

            System.out.println(
                "JobExecution ID=" + execution.getId()
                + ", status=" + execution.getStatus()
                + ", exitStatus=" + execution.getExitStatus()
            );
        };
    }

    private static String option(
            ApplicationArguments args,
            String name,
            String defaultValue) {

        List<String> values = args.getOptionValues(name);

        return values == null || values.isEmpty()
            ? defaultValue
            : values.get(0);
    }
}
```

`businessDate` là **identifying parameter**, vì kỳ ngày khác phải là một `JobInstance` khác. `inputFile` và `maxRejected` được đánh dấu non-identifying để chúng không vô ý tạo identity mới khi cùng kỳ được retry; chúng vẫn cần được **giữ nguyên theo contract của instance trong restart**. Ở môi trường thật, nên ghi lại policy version/input checksum và không thay nguồn dữ liệu sau khi import đã commit.

### 11.3. Chạy đường PASS

Từ thư mục project:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo --businessDate=2026-11-16 --maxRejected=2'
```

Trên Windows nếu dùng Gradle wrapper:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=demo --businessDate=2026-11-16 --maxRejected=2"
```

Với file demo có đúng 2 rejected rows, điều kiện:

```text
total = 5
rejected = 2
duplicateIds = 0
maxRejected = 2

=> quality gate PASS
=> publishStep
=> summaryStep
=> JobExecution COMPLETED
```

### 11.4. Chạy đường HOLD

Dùng business date khác để tạo một instance độc lập trong demo:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo --businessDate=2026-11-17 --maxRejected=1'
```

Dự kiến:

```text
total = 5
rejected = 2
duplicateIds = 0
maxRejected = 1

=> quality gate HOLD
=> holdStep
=> JobExecution STOPPED
=> không gọi publishStep
```

**Giới hạn H2 in-memory:** nếu chạy hai lệnh `bootRun` ở hai JVM khác nhau với cấu hình ở trên, database được tạo mới. Muốn quan sát cả hai instances trong một database bền vững qua process restart, chuyển sang PostgreSQL/H2 file và migration đúng; hoặc chạy hai scenarios qua integration test trong cùng Spring context ở mục 14.

---

## 12. Kiểm tra kết quả bằng SQL và Batch metadata

### 12.1. Bảng staging

Sau đường PASS hoặc HOLD:

```sql
SELECT
    BUSINESS_DATE,
    SOURCE_LINE,
    ORDER_ID,
    AMOUNT,
    RECORD_STATUS,
    REJECT_REASON
FROM STG_ORDER
WHERE BUSINESS_DATE = DATE '2026-11-16'
ORDER BY SOURCE_LINE;
```

Kỳ vọng:

| SOURCE_LINE | ORDER_ID | AMOUNT | RECORD_STATUS | REJECT_REASON |
| ---: | --- | ---: | --- | --- |
| 2 | O-100 | 120.00 | VALID | null |
| 3 | O-101 | 50.50 | VALID | null |
| 4 | O-102 | -9.00 | REJECTED | AMOUNT_NON_POSITIVE |
| 5 | O-103 | 70.00 | VALID | null |
| 6 | O-104 | 0.00 | REJECTED | AMOUNT_NON_POSITIVE |

`SOURCE_LINE` tính cả header tại dòng 1.

### 12.2. Bảng published

Với business date PASS:

```sql
SELECT ORDER_ID, CUSTOMER_ID, AMOUNT
FROM PUBLISHED_ORDER
WHERE BUSINESS_DATE = DATE '2026-11-16'
ORDER BY ORDER_ID;
```

Dự kiến có đúng 3 records: O-100, O-101, O-103.

Với ngày HOLD (17/11):

```sql
SELECT COUNT(*)
FROM PUBLISHED_ORDER
WHERE BUSINESS_DATE = DATE '2026-11-17';
```

Dự kiến bằng **0** vì flow không đi qua publishStep.

### 12.3. Bảng audit

```sql
SELECT BUSINESS_DATE, FLOW_STATE, NOTE
FROM FLOW_AUDIT
ORDER BY BUSINESS_DATE;
```

Một kỳ thành công có `FLOW_STATE=PUBLISHED`; kỳ giữ lại có `FLOW_STATE=HOLD`.

### 12.4. Metadata Spring Batch

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'orderFlowJob'
ORDER BY je.JOB_EXECUTION_ID;
```

Khi cần xem status của từng step:

```sql
SELECT
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY JOB_EXECUTION_ID, STEP_EXECUTION_ID;
```

Bảng metadata và tên cột phụ thuộc schema Spring Batch. Truy vấn trên hướng đến schema JDBC Spring Batch 5.x thông dụng.

### 12.5. Phân biệt hai kết quả quan trọng

```text
qualityGateStep:
  BatchStatus = COMPLETED
  ExitStatus  = PASS hoặc HOLD

JobExecution sau HOLD:
  BatchStatus = STOPPED
  ExitStatus  = STOPPED / theo flow
```

Một step thực thi thành công không nhất thiết khiến cả job `COMPLETED`: flow transition quyết định liệu job tiếp tục, dừng hay thất bại.

---

## 13. Restart từ HOLD sau khi sửa dữ liệu

### 13.1. Vì sao không launch JobInstance mới?

Giả sử job ngày 17 đã import vào staging rồi dừng tại quality gate. Nếu thêm identifying `runAt=System.currentTimeMillis()` để tạo instance mới, import step có thể đọc lại file, làm mất lợi ích của restart và tạo nguy cơ duplicate side effects.

Thay vào đó, điều cần làm:

1. Giữ cùng `businessDate`/`JobInstance`.
2. Sửa lỗi được xác minh trong `STG_ORDER`.
3. Gọi restart với execution đã `STOPPED`.
4. Để qualityGateStep chạy lại và chọn nhánh PASS nếu đạt.
5. Xác minh published output.

### 13.2. Sửa một dòng staging trong H2 demo

Với ngày 17, có 2 rejected rows; ngưỡng cho phép là 1. Sau khi người vận hành xác minh giá trị đúng của O-102 từ nguồn, sửa record tương ứng:

```sql
UPDATE STG_ORDER
SET
    AMOUNT = 90.00,
    RECORD_STATUS = 'VALID',
    REJECT_REASON = NULL
WHERE BUSINESS_DATE = DATE '2026-11-17'
  AND ORDER_ID = 'O-102'
  AND RECORD_STATUS = 'REJECTED';
```

Đây là **ví dụ remediation có chủ đích**. Không tự ý đổi `-9.00` thành `90.00` trong production nếu không có chứng cứ từ nguồn và audit người phê duyệt.

Sau sửa:

```text
total=5
rejected=1
duplicateIds=0
limit=1

=> PASS
```

### 13.3. Gọi `JobOperator.restart(...)`

Trong Spring Batch 5.x, khi `JobOperator` đã được cấu hình với `JobRepository`, `JobExplorer` và job registry phù hợp:

```java
Long restartedExecutionId =
    jobOperator.restart(stoppedExecutionId);
```

`stoppedExecutionId` là **`JobExecution ID`**, không phải JobInstance ID. Kết quả trả về là execution ID mới trong cùng JobInstance, nếu điều kiện restart được đáp ứng.

Với job sử dụng `stopAndRestart(qualityGateStep)`, framework lưu điểm tiếp tục của flow; `qualityGateStep` còn được đặt `allowStartIfComplete(true)` để re-evaluate sau khi dữ liệu staging được sửa.

### 13.4. Vì sao import step không chạy lại?

Trong lần đầu, `importStep` đã `COMPLETED` và commit dữ liệu staging. Sau STOPPED, flow restart từ quality gate theo cấu hình. Import không thuộc phần phải chạy lại.

Nếu trước đó import step `FAILED` vì file lỗi, không có transition HOLD; job đi vào error/restart path thông thường, và **import step** cần được khôi phục từ checkpoint nếu khả thi. Đó là hai kiểu recovery khác nhau.

### 13.5. Đọc trạng thái sau restart

```java
JobExecution restarted =
    jobExplorer.getJobExecution(restartedExecutionId);

if (restarted != null) {
    System.out.println(restarted.getStatus());
    System.out.println(restarted.getJobInstance().getId());
}
```

Khi `JobLauncher` có executor bất đồng bộ, ID trả về chưa có nghĩa execution đã kết thúc. Cần poll/tracking đến trạng thái terminal trước khi khẳng định `COMPLETED`.

---

## 14. Integration test cho cả PASS, HOLD và restart

Một bài thực hành flow nhiều step cần kiểm thử **đường đi thực**, không chỉ unit test processor.

### 14.1. Cấu hình test

Với `spring.batch.job.enabled=false` và H2 in-memory ở `application.yml`, integration test có thể dùng `@SpringBootTest` và `@SpringBatchTest`.

`src/test/java/com/example/orderflow/OrderFlowIntegrationTest.java`:

```java
package com.example.orderflow;

import java.sql.Date;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class OrderFlowIntegrationTest {

    @Autowired
    JobLauncher launcher;

    @Autowired
    JobExplorer explorer;

    @Autowired
    @Qualifier("orderFlowJob")
    Job job;

    @Autowired
    JdbcTemplate jdbc;

    private static JobParameters params(
            String date, long maxRejected) {

        return new JobParametersBuilder()
            .addString("businessDate", date, true)
            .addString("inputFile",
                "classpath:orders-demo.csv", false)
            .addLong("maxRejected", maxRejected, false)
            .toJobParameters();
    }

    @Test
    void passPublishesOnlyValidRows() throws Exception {
        JobExecution execution =
            launcher.run(job, params("2026-11-16", 2L));

        assertEquals(
            BatchStatus.COMPLETED,
            execution.getStatus());

        assertEquals(5L, count(
            "STG_ORDER", "2026-11-16"));

        assertEquals(3L, count(
            "PUBLISHED_ORDER", "2026-11-16"));

        assertTrue(hasStep(
            execution, "prepareStep"));
        assertTrue(hasStep(
            execution, "importStep"));
        assertTrue(hasStep(
            execution, "qualityGateStep"));
        assertTrue(hasStep(
            execution, "publishStep"));
        assertTrue(hasStep(
            execution, "summaryStep"));
        assertFalse(hasStep(
            execution, "holdStep"));

        assertEquals("PUBLISHED",
            state("2026-11-16"));
    }

    @Test
    void holdAndRestartReevaluateGate()
            throws Exception {

        JobParameters parameters =
            params("2026-11-17", 1L);

        JobExecution first =
            launcher.run(job, parameters);

        assertEquals(
            BatchStatus.STOPPED,
            first.getStatus());

        assertEquals("HOLD",
            state("2026-11-17"));

        assertEquals(0L, count(
            "PUBLISHED_ORDER", "2026-11-17"));

        assertTrue(hasStep(
            first, "qualityGateStep"));
        assertTrue(hasStep(
            first, "holdStep"));
        assertFalse(hasStep(
            first, "publishStep"));

        // Test giả định data steward đã xác minh số đúng.
        int updated = jdbc.update("""
            UPDATE STG_ORDER
            SET AMOUNT = 90.00,
                RECORD_STATUS = 'VALID',
                REJECT_REASON = NULL
            WHERE BUSINESS_DATE = ?
              AND ORDER_ID = 'O-102'
              AND RECORD_STATUS = 'REJECTED'
            """, Date.valueOf("2026-11-17"));

        assertEquals(1, updated);

        // Dùng cùng JobInstance, không tạo identifying timestamp.
        JobExecution restarted =
            launcher.run(job, parameters);

        assertEquals(
            BatchStatus.COMPLETED,
            restarted.getStatus());

        assertNotEquals(
            first.getId(),
            restarted.getId());

        assertEquals(
            first.getJobInstance().getId(),
            restarted.getJobInstance().getId());

        assertTrue(hasStep(
            restarted, "qualityGateStep"));
        assertTrue(hasStep(
            restarted, "publishStep"));
        assertTrue(hasStep(
            restarted, "summaryStep"));

        assertFalse(hasStep(
            restarted, "importStep"));

        assertEquals(4L, count(
            "PUBLISHED_ORDER", "2026-11-17"));

        assertEquals("PUBLISHED",
            state("2026-11-17"));

        JobExecution persisted =
            explorer.getJobExecution(restarted.getId());

        assertNotNull(persisted);
        assertEquals(
            BatchStatus.COMPLETED,
            persisted.getStatus());
    }

    private long count(String table, String day) {
        // 'table' chỉ do test gọi với hằng số cố định,
        // không lấy tên bảng từ input bên ngoài.
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table
                + " WHERE BUSINESS_DATE = ?",
            Long.class,
            Date.valueOf(day));

        return count == null ? 0 : count;
    }

    private String state(String day) {
        return jdbc.queryForObject("""
            SELECT FLOW_STATE
            FROM FLOW_AUDIT
            WHERE BUSINESS_DATE = ?
            """,
            String.class,
            Date.valueOf(day));
    }

    private static boolean hasStep(
            JobExecution execution,
            String stepName) {

        return execution.getStepExecutions().stream()
            .map(StepExecution::getStepName)
            .anyMatch(stepName::equals);
    }
}
```

### 14.2. Những assertion quan trọng

- Với `maxRejected=2`, quality gate PASS, job `COMPLETED`, chỉ có 3 rows published.
- Với `maxRejected=1`, quality gate HOLD, job `STOPPED`, không gọi publish.
- Sửa staging, restart bằng cùng parameters: **JobInstance ID không đổi**, JobExecution ID mới.
- Import step không được chạy lại khi restart từ HOLD; qualityGate, publish, summary có execution tương ứng.
- Tổng published ngày 17 là 4 rows sau khi một reject được remediation.
- `JobExplorer` đọc metadata bền vững trong cùng JVM.

Trong test, thứ tự hai methods không cần cố định vì chúng dùng hai business dates khác nhau. Nếu chạy cùng testcase nhiều lần trên một H2 instance không reset, `JobInstanceAlreadyCompleteException` có thể xuất hiện; test fixture nên dùng database riêng/context reset hoặc business key dành riêng cho từng test run.

### 14.3. Một giả định quan trọng của test

Test trên sử dụng `JobLauncher` đồng bộ mặc định. Nếu ứng dụng cấu hình `TaskExecutor` bất đồng bộ cho launcher, `launcher.run(...)` có thể trả về khi job chưa kết thúc. Khi đó cần chờ/poll terminal status theo một timeout hợp lý thay vì assert ngay.

### 14.4. Cách thử nhánh lỗi kỹ thuật

Tạo input file không tồn tại:

```text
inputFile=classpath:missing.csv
```

Expected:

- `orderReader` không thể mở resource.
- `importStep` `FAILED`.
- `qualityGateStep` và `publishStep` không chạy.
- `JobExecution` `FAILED`.
- Sau khi sửa file và xác minh cùng business input logic, restart instance cũ để đọc lại.

Không được tự cấu hình `.on("*").to(publishStep)` sau import lỗi, vì như vậy dữ liệu staging chưa hoàn chỉnh vẫn có thể đi vào publish.

---

## 15. Flow status và restart: các bẫy cần hiểu

### 15.1. Step `COMPLETED` có thể không được chạy lại

Spring Batch thường bỏ qua step đã `COMPLETED` khi restart cùng JobInstance, trừ khi `allowStartIfComplete(true)` hoặc flow restart semantics yêu cầu và cho phép.

Với flow này:

| Step | Khi PASS lần đầu | Khi HOLD lần đầu | Sau sửa và restart |
| --- | --- | --- | --- |
| prepareStep | chạy | chạy | không chạy lại |
| importStep | chạy | chạy | không chạy lại |
| qualityGateStep | PASS | HOLD | chạy lại |
| publishStep | chạy | không chạy | chạy |
| summaryStep | chạy | không chạy | chạy |
| holdStep | không chạy | chạy | không chạy nếu gate PASS |

Nếu không đặt `allowStartIfComplete(true)` cho gate, restart sau HOLD dễ không thực hiện đánh giá mới theo mong muốn.

### 15.2. STOPPED khác FAILED

`FAILED` thường biểu thị step/job không hoàn tất do exception hoặc failure transition. `STOPPED` là trạng thái dừng có thể là kết quả của một flow transition được thiết kế sẵn.

Dù vậy, `STOPPED` không phải lúc nào cũng an toàn để restart tự động. Với flow này, chỉ restart sau khi một record đã được sửa và output được kiểm tra; nếu chưa sửa, quality gate vẫn HOLD và job lại STOPPED.

### 15.3. `end()` có thể che lỗi nếu dùng sai

Ví dụ:

```java
.from(qualityGateStep).on("HOLD").end()
```

Nếu dùng một transition kết thúc thành công cho đường HOLD, JobExecution có thể được xem `COMPLETED` dù không có dữ liệu published. Instance completed thường không restart được theo cách thông thường, khiến quá trình remediation khó hơn.

Trong bài thực hành, `stopAndRestart(qualityGateStep)` thể hiện chính xác contract “chờ sửa dữ liệu rồi đánh giá lại”.

### 15.4. Thay đổi flow giữa executions

Khi deploy phiên bản mới, nếu xóa/đổi tên step, thay cấu trúc flow hoặc thay JobParameters rules, việc restart một instance cũ có thể không còn tương thích.

Production cần:

- Giữ tên step và `ExecutionContext` keys ổn định khi các job cũ còn restartable.
- Có migration/change plan cho breaking changes.
- Gắn version flow/rule với business run nếu cần.
- Không sửa tên `qualityGateStep` giữa HOLD và restart mà không đánh giá tác động.
- Kiểm thử restart qua phiên bản mới trước khi deploy.

---

## 16. Chunk processing và tasklet: ranh giới transaction

### 16.1. Import chunk

`importStep` dùng:

```java
.<RawOrder, StagedOrder>chunk(2, transactionManager)
```

Trong mỗi chunk:

1. Reader đọc input.
2. Processor tạo staged item.
3. Writer gửi JDBC batch.
4. Transaction commit và `ExecutionContext` được cập nhật phù hợp.

Nếu chunk thứ ba thất bại, hai chunk trước có thể đã commit. Khi restart, reader dùng checkpoint từ `JobRepository` để tiếp tục.

### 16.2. Tasklet step

`prepareStep`, `qualityGateStep`, `publishStep`, `summaryStep` và `holdStep` đều là tasklet steps. Chúng thực hiện một đơn vị công việc rồi trả:

```java
return RepeatStatus.FINISHED;
```

Nếu cần tasklet lặp nhiều lượt, có thể trả `RepeatStatus.CONTINUABLE` theo contract, nhưng bài này không dùng vòng lặp tasklet để giữ logic điều khiển flow đơn giản.

### 16.3. Vì sao publish trong một SQL statement?

Với H2 demo nhỏ, publish dùng `MERGE ... SELECT` để chuyển tất cả rows VALID trong một bước. Ưu điểm:

- Code dễ đọc.
- Ít round trips.
- Không cần nạp toàn bộ rows vào Java.
- SQL có thể tham gia transaction của tasklet step nếu datasource/transaction manager được cấu hình đúng.

Nhưng production vài chục triệu rows có thể cần chia thành các batch nhỏ, partition, set-based SQL được tối ưu, transaction window hoặc versioned output để tránh lock và timeout. Khi tách publish thành nhiều chunk, cần thêm idempotency và gate/publish semantics rõ.

### 16.4. Metadata và business datasource có thể khác nhau

Ví dụ dùng cùng H2 database để giảm sự phức tạp. Nếu `JobRepository` ở DB A và bảng staging/published ở DB B, hai transaction resources không tự có atomic commit xuyên database. Có thể xuất hiện:

```text
DB B: published rows đã COMMIT
DB A: StepExecution/checkpoint chưa update kịp
Process chết
```

Khi restart, publish có thể được gọi lại. Vì vậy unique business key/`MERGE` hoặc quy trình reconciliation vẫn cần thiết.

### 16.5. Side effect ngoài database

Nếu publish đồng thời gửi HTTP/email/Kafka event, việc tasklet thất bại sau khi gửi có thể khiến restart gửi lại. Cân nhắc transactional outbox, idempotency key hoặc audit/dedup phía consumer. Flow nhiều step giúp biểu diễn thứ tự, **không tự tạo exactly-once** cho mọi hệ thống ngoài.

---

## 17. JobParameters và nhận diện kỳ nghiệp vụ

### 17.1. Chọn identifying parameter

Trong demo:

```java
.addString("businessDate", date, true)
.addString("inputFile", file, false)
.addLong("maxRejected", maxRejected, false)
```

Cùng ngày có cùng `JobInstance`; ngày khác là kỳ xử lý độc lập. Đó là lựa chọn **đơn giản hóa để học**.

Trong production, nếu có nhiều file cho cùng ngày hoặc nhiều tenant, `businessDate` một mình không đủ. Có thể cần:

```java
.addString("tenantId", tenantId, true)
.addString("sourceFileId", sourceFileId, true)
.addString("businessDate", date.toString(), true)
.addString("flowVersion", flowVersion, false)
```

Nếu `flowVersion` thay đổi khiến cùng data phải được xử lý như một job mới, cân nhắc nhận diện bằng một business revision có contract rõ, không tự ý đổi parameters trong một restart.

### 17.2. Không dùng thời gian hiện tại để luôn tạo instance mới

Đây là một anti-pattern:

```java
.addLong("runAt", System.currentTimeMillis())
```

Trong các overload thường dùng của Spring Batch 5.x, tham số mặc định có thể là **identifying=true**. Khi restart với timestamp mới, framework tạo một `JobInstance` khác; checkpoint của importStep và vị trí stop/restart flow cũ không được tận dụng.

Để tiếp tục HOLD hoặc FAILED, phải restart **instance cũ** bằng execution ID hoặc cùng identifying parameters theo contract.

### 17.3. Non-identifying không có nghĩa được tự do đổi khi restart

Với một instance HOLD vì `maxRejected=1`, người vận hành không nên “lách” bằng cách restart cùng business date nhưng đổi threshold thành 10 rồi cho publish. `JobOperator.restart(executionId)` dùng parameters/metadata cũ; nếu thực sự muốn thay policy, đó là quyết định nghiệp vụ cần được audit và có thể yêu cầu reprocess flow revision riêng.

Bài này chọn **sửa dữ liệu staging đã được xác minh**, sau đó restart quality gate với cùng policy.

---

## 18. Tổ chức flow production: vấn đề và phương án

### 18.1. Chạy nhiều tenant hoặc nhiều file

Nếu một ngày có 100 tenants, nên định nghĩa identity:

```text
jobName=orderFlowJob
tenantId=tenant-001
sourceFileId=orders-2026-11-16-v1
businessDate=2026-11-16
```

Bảng staging/target cũng cần tenant và source version khi phù hợp; tránh để jobs khác tenant ghi đè cùng một khóa `(businessDate, sourceLine)`.

### 18.2. Input bất biến

Nếu file bị sửa sau khi import step completed, flow restart từ quality gate **không reread** file. Đây là chủ đích của flow. Muốn áp dụng file đã sửa, cần quyết định:

- Sửa staging có audit.
- Chạy job remediation riêng.
- Tạo một import revision mới.
- Hoặc reset/restart pipeline bằng một workflow được phê duyệt.

Không âm thầm đổi path file trong non-identifying parameters và kỳ vọng import step tự đọc lại.

### 18.3. Quality gate đa điều kiện

Production gate có thể đánh giá:

- Số rejected / tổng eligible.
- Tỷ lệ lỗi theo rule code.
- Trùng business key.
- Sum amount so với manifest file.
- Reference data completeness.
- Tenant ownership.
- Ngưỡng SLA/độ mới dữ liệu.
- Approval của Data Steward.

Có thể trả custom exit codes như `PASS`, `HOLD_REVIEW`, `REJECT_BATCH`. Khi nhiều nhánh, dùng `JobExecutionDecider` hoặc tách các validation steps để flow dễ duy trì.

### 18.4. Audit không chỉ là một dòng trạng thái

Bảng `FLOW_AUDIT` demo lưu trạng thái cuối. Production có thể cần append-only audit:

```text
jobInstanceId
jobExecutionId
stepName
timestamp
actor
action
policyVersion
sourceFileVersion
beforeStatus
afterStatus
reasonCode
correlationId
```

Khi operator sửa một record staging, lưu nguồn xác minh/approval, không chỉ sửa SQL trực tiếp không có lịch sử.

### 18.5. Chạy các steps độc lập để dễ bảo trì?

Spring Batch cho phép chạy/kiểm thử step riêng, nhưng một step có thể phụ thuộc dữ liệu đầu ra của step trước. Ví dụ `publishStep` không được chạy độc lập trên staging chưa vượt gate. Production nên bảo vệ invariants bên trong publish hoặc bằng bảng publication-approval, không chỉ tin rằng mọi caller đều chạy qua Job flow chuẩn.

### 18.6. Chống trùng ở tầng scheduler và API

Một request launch có thể được gửi lại sau network timeout. Dùng stable identifying params, `JobRepository` bền vững và business request ledger/unique key nếu cần để quyết định launch/restart. Hai request khác JobInstance nhưng cùng ghi một bảng vẫn có thể gây contention; cần kiểm soát tenant/slot ownership và idempotency của writer.

---

## 19. Những lỗi thường gặp khi tạo job flow nhiều step

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Job không đi vào nhánh PASS | `ExitStatus` không khớp `on("PASS")` | Kiểm tra code thực của StepExecution, set custom ExitStatus đúng |
| Gate HOLD nhưng Job báo COMPLETED | Dùng `.end()` trên nhánh HOLD | Dùng `stopAndRestart` hoặc fail theo contract |
| Restart HOLD nhưng gate không chạy lại | Gate đã `COMPLETED`, thiếu `allowStartIfComplete(true)` | Cho phép re-evaluate gate, test lại |
| Import chạy lại không mong muốn | Tạo JobInstance mới bằng timestamp | Dùng stable identifying params, restart existing instance |
| Dữ liệu publish dù gate lỗi | Wildcard transition quá rộng hoặc publish chạy độc lập | Guard branch và quyền gọi publish |
| H2 mất dữ liệu sau restart JVM | Dùng in-memory database | Dùng persistent DB cho recovery qua process crash |
| Step bean bị gọi khi chưa có JobParameters | Truy cập parameter ngoài step scope | Dùng `@StepScope` hoặc đọc trong Tasklet execution |
| Reader không khôi phục vị trí | Mất `ItemStream`, tên reader đổi hoặc metadata mất | Giữ lifecycle/checkpoint và input immutable |
| Dữ liệu staging trùng khi retry | Writer insert không có business key/idempotency | Unique constraint + upsert đúng semantics |
| Publisher ném duplicate key sau restart | Publish đã commit nhưng metadata chưa cập nhật | Set-based idempotent write và reconciliation |
| Quality gate đếm rejected sai | Query không lọc đúng kỳ/tenant hoặc job overlap | Stable business keys, predicate đầy đủ |
| Thay file input trên restart nhưng output không đổi | Import step đã COMPLETED và bị bỏ qua | Remediation/revision rõ ràng |
| `JobOperator.restart` không tìm thấy Job | JobRegistry chưa đăng ký hoặc cấu hình sai | Kiểm tra JobOperator/registry và job definition |
| Quên phân biệt ExitStatus và BatchStatus | Chỉ xem Step status COMPLETED | Kiểm tra custom exit code và job flow status |
| Flow giữ lỗi trong staging nhưng vẫn publish | Nhánh không bắt duplicate/critical rule | Bổ sung gate và publication guard |
| Dùng một transaction cho hàng triệu rows | Lock, log growth, timeout | Chunk/partition hoặc publish theo version có kiểm soát |

### 19.1. Một cách debug có thứ tự

Khi flow không đi đúng đường:

1. Xem job name, identifying parameters và JobInstance ID.
2. Đọc `BATCH_JOB_EXECUTION` để biết BatchStatus/ExitStatus của execution.
3. Đọc `BATCH_STEP_EXECUTION` theo thứ tự để biết step nào thực sự chạy.
4. Kiểm tra exit code mà `qualityGateStep` đã trả.
5. Đối chiếu mapping `on(...)` trong JobBuilder.
6. Đọc staging/quality metrics và kiểm tra job đang dùng đúng businessDate.
7. Nếu restart, kiểm tra last execution có `STOPPED`/`FAILED` và có worker khác còn chạy hay không.
8. Đối chiếu metadata checkpoint và output trước khi chạy lại.

Đừng cố sửa flow bằng cách đặt `.on("*").to(publishStep)` để “không bị kẹt”, vì đó có thể biến lỗi dữ liệu/hạ tầng thành bản ghi published sai.

---

## 20. Bài tập mở rộng dự án

### Bài 1 — Bổ sung nhánh REJECT_BATCH

Thêm một loại vi phạm nghiêm trọng: order thuộc tenant khác. Gate phải trả `REJECT_BATCH` nếu có bất kỳ vi phạm loại này. Tạo branch:

```text
qualityGateStep
  PASS         -> publishStep
  HOLD         -> holdStep -> STOPPED
  REJECT_BATCH -> rejectBatchStep -> FAILED
```

Yêu cầu: không publish; audit ghi rule code và tổng record ảnh hưởng.

### Bài 2 — Quality gate theo tỷ lệ

Thay `maxRejected` tuyệt đối bằng cả giới hạn tuyệt đối và tỷ lệ trên eligible rows. Ví dụ rejectRate không quá 0,5% và số rejected không quá 100.

Yêu cầu: định nghĩa mẫu số, test boundary tại đúng threshold và lớn hơn threshold một record.

### Bài 3 — Dữ liệu nguồn có nhiều file và tenant

Mở rộng CSV/file manifest để có `tenantId` và `sourceFileId`. Sửa primary keys staging, published và identifying JobParameters.

Yêu cầu: hai tenants cùng ngày không ghi đè staging của nhau; restart mỗi tenant giữ đúng JobInstance.

### Bài 4 — Nhánh cảnh báo sau publish

Thêm `notificationStep` sau `summaryStep` nếu cần gửi thông báo hoàn tất. Dùng transactional outbox hoặc idempotency key để không gửi thông báo trùng nếu job crash sau khi message được gửi nhưng trước khi metadata update.

Yêu cầu: test tình huống restart và chứng minh tối đa một thông báo nghiệp vụ theo key.

### Bài 5 — Fail import và restart checkpoint

Tạo CSV 100 records, chunk size 10 và writer giả lập lỗi khi ghi chunk thứ tư. Sau khi lỗi được sửa, restart cùng instance.

Yêu cầu: test `importStep` khôi phục từ checkpoint, các rows đã commit không bị nhân đôi và gate chỉ chạy sau khi import thành công.

### Bài 6 — Thử `JobExecutionDecider`

Thay quality gate custom exit code bằng một step chỉ tính metrics và `JobExecutionDecider` đánh giá decision dựa trên dữ liệu persisted.

Yêu cầu: flow PASS/HOLD vẫn đúng, không phụ thuộc vào mutable in-memory singleton.

### Bài 7 — Tách publish cho dữ liệu lớn

Đổi publish tasklet thành chunk-oriented step hoặc SQL set-based publish theo partition; xử lý hàng triệu records.

Yêu cầu: so sánh commit duration, restart cost, idempotency và transaction boundaries.

### Bài 8 — Runbook remediation

Viết một runbook dành cho vận hành:

1. Truy vấn các record REJECTED.
2. Xác minh giá trị đúng từ nguồn.
3. Cập nhật staging có audit.
4. Kiểm tra rejected count.
5. Gọi restart đúng JobExecution ID.
6. Theo dõi đến COMPLETED.
7. Đối soát published output.

Yêu cầu: không sử dụng timestamp nhận diện để mở JobInstance mới thay cho restart.

---

## 21. Checklist tự hoàn thành dự án

Một flow nhiều step được coi là thực hành đạt mục tiêu khi:

- [ ] Project khởi động và các bảng `BATCH_*` cùng staging/published/audit được tạo.
- [ ] Job có các step `prepare → import → quality gate`.
- [ ] Reader có `@StepScope` và lấy inputFile từ JobParameters.
- [ ] Processor phân loại VALID/REJECTED với rule code.
- [ ] Writer ghi staging theo chunk và có khóa tránh ghi trùng.
- [ ] Gate kiểm tra số rejected và duplicate business keys.
- [ ] Nhánh PASS chỉ publish records VALID.
- [ ] Nhánh HOLD ghi audit và JobExecution ở STOPPED.
- [ ] Restart cùng JobInstance quay lại qualityGateStep sau remediation.
- [ ] Import step không chạy lại không cần thiết khi restart từ HOLD.
- [ ] Có output queries và assertions cho cả hai nhánh.
- [ ] Có test đường FAILED khi reader/file không sẵn sàng.
- [ ] Có phân biệt `BatchStatus`, `ExitStatus`, checkpoint và flow transition.
- [ ] Không tự thêm `runAt=System.currentTimeMillis()` làm identifying JobParameter mỗi lần chạy.
- [ ] Production plan xác định datasource, schema migration, idempotency, version và audit.

## 22. Tổng kết kiến trúc

Một **job flow nhiều step** không chỉ làm code đẹp hơn. Nó còn phân tách trách nhiệm, giúp Spring Batch ghi nhận trạng thái từng giai đoạn, thực hiện chuyển nhánh theo `ExitStatus` và hỗ trợ restart đúng nơi khi có sự cố hoặc dữ liệu cần can thiệp.

Trong dự án này:

- **Chunk step** đảm nhiệm import có checkpoint.
- **Tasklet steps** đảm nhiệm chuẩn bị, đánh giá và xuất bản.
- **`on("PASS")` / `on("HOLD")`** quyết định nhánh.
- **`stopAndRestart(qualityGateStep)`** cho phép dừng có chủ đích và đánh giá lại sau remediation.
- **`allowStartIfComplete(true)`** ở quality gate là lựa chọn cố ý để step được chạy lại trong restart.
- **Staging và unique keys** giúp giữ dữ liệu lỗi, kiểm soát publish và giảm rủi ro trùng khi phải chạy lại.
- **Stable JobParameters** giúp cả job giữ đúng logical identity của một kỳ nghiệp vụ.

Nắm vững các điểm này là nền tảng để xây dựng pipeline nhiều bước có branch, gate, audit và khả năng phục hồi trong các hệ thống batch production.

## 23. Tài liệu tham khảo

- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobBuilder`, JobInstance, JobExecution, restartability.
- [Spring Batch — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): `on`, `to`, `from`, `end`, `fail` và `stopAndRestart`.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): reader, processor, writer và transaction boundaries.
- [Spring Batch — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html): tasklet semantics và transaction.
- [Spring Batch — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` và JobParameters.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint và restart.
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobExplorer` và `JobOperator`.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/testing.html): integration test và `@SpringBatchTest`.
- [Spring Boot — Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): Batch auto-configuration và schema.
- [H2 Database Documentation](https://h2database.com/html/commands.html): `MERGE INTO` và SQL behavior của demo.
