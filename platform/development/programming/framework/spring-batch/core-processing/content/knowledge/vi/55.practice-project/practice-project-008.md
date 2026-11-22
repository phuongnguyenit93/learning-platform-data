# Kiểm tra restart sau khi process bị dừng trong Spring Batch

Một Spring Batch job có thể hoàn thành chính xác khi chạy liên tục, nhưng vẫn bị mất hoặc ghi trùng dữ liệu nếu JVM bị dừng giữa chừng. Trong môi trường thực tế, tiến trình có thể kết thúc vì deployment, người vận hành yêu cầu dừng, Kubernetes thay Pod, hệ điều hành gửi tín hiệu hoặc máy chủ mất điện. Những tình huống này khác nhau về cách Spring Batch kịp cập nhật metadata, vì vậy phải **kiểm tra restart bằng hai process thực sự khác nhau**, không chỉ gọi job hai lần trong cùng một JUnit test.

Bài thực hành thuộc **Spring Batch Core Processing → Dự án thực hành** và tập trung vào câu hỏi:

> Sau khi process chạy job dừng giữa chừng, một process mới có thể dùng metadata đã lưu để xử lý tiếp mà **không mất, không trùng** bản ghi đã commit hay không?

Ta sẽ xây dựng một project nhỏ có input CSV, chunk-oriented step, database PostgreSQL lưu `JobRepository` và output, một cờ dừng được kiểm tra **sau mỗi chunk commit**, sau đó khởi động một JVM mới với **cùng identifying `JobParameters`**. Phần cuối thử thêm tình huống **kill process đột ngột**, để nhận ra giới hạn quan trọng: `SIGKILL` hoặc `Stop-Process -Force` có thể để lại metadata ở trạng thái `STARTED`; khi đó **không được mặc định Spring Batch tự restart như với một execution `STOPPED` hay `FAILED` đã được ghi nhận**.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau bài này, bạn cần có thể:

1. Giải thích mối liên hệ giữa `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và checkpoint.
2. Dùng một **PostgreSQL bền vững** để lưu metadata thay vì H2 in-memory sẽ mất cùng JVM.
3. Cho job commit vài chunk, yêu cầu dừng **có kiểm soát**, xác nhận trạng thái `STOPPED` và process kết thúc.
4. Khởi động JVM mới với **cùng `businessDate` và `sourceVersion`**, xác nhận restart tạo `JobExecution` mới nhưng vẫn thuộc `JobInstance` cũ.
5. Đối chiếu output cuối theo business key: đủ bản ghi, không duplicate, payload chính xác.
6. Thử hard kill và phân biệt “process chết” với “Batch đã lưu trạng thái restartable”.
7. Thiết kế runbook xử lý execution bị kẹt `STARTED` và kiểm soát tài nguyên đầu vào/đầu ra.

**Tiêu chí quan trọng nhất:** `JobExecution` có `COMPLETED` chỉ là điều kiện cần. Bài thực hành chỉ được coi là thành công khi **output vật lý** và metadata chứng minh được việc tiếp tục chính xác.

## 2. Cơ chế restart khi process kết thúc

Spring Batch xác định một `JobInstance` theo **tên job + tập `JobParameters` identifying**. Mỗi lần thực thi của instance đó có `JobExecution` riêng; mỗi lần step được thực thi có `StepExecution` riêng.

```text
Job name = importOrdersJob
Identifying parameters:
  businessDate  = 2026-11-16
  sourceVersion = orders-v1
                 |
                 v
           JobInstance #41
                 |
       +---------+----------+
       |                    |
       v                    v
JobExecution #101       JobExecution #102
    STOPPED                 COMPLETED
       |                    |
       v                    v
StepExecution #501      StepExecution #502
chunk 1..N commit       reader mở lại checkpoint
context được lưu        ghi phần còn lại
```

Một reader có khả năng restart (ví dụ `FlatFileItemReader` với `saveState=true`) sử dụng `ItemStream`:

```java
open(ExecutionContext savedState);    // Khôi phục vị trí đã lưu.
read();                               // Đọc item tiếp theo.
update(ExecutionContext state);       // Chuẩn bị checkpoint.
close();                              // Giải phóng tài nguyên.
```

Trong chunk-oriented step, reader/processor/writer xử lý một nhóm item, trạng thái được cập nhật và transaction commit. Khi chunk thất bại, các item chưa commit có thể bị đọc lại. Điều này đúng nếu writer nằm trong transaction phù hợp hoặc **idempotent** với side effect bên ngoài.

Ví dụ chunk size 10:

```text
Input: O0001 ........................................ O0200

Chunk 1:  O0001..O0010   -> COMMIT
Chunk 2:  O0011..O0020   -> COMMIT
Chunk 3:  O0021..O0030   -> COMMIT
Chunk 4:  O0031..O0040   -> STOP REQUESTED trước chunk tiếp theo

PostgreSQL:
  processed_orders có 40 dòng đã commit.
  BATCH_STEP_EXECUTION_CONTEXT lưu trạng thái sau chunk #4.

Process A thoát.
Process B khởi động với cùng JobInstance:
  Reader khôi phục checkpoint và đọc phần còn lại.
  Kết quả cuối có 200 business keys duy nhất.
```

**Không suy ra restart point chỉ từ `readCount`, dòng log item cuối hoặc vị trí cursor trong bộ nhớ.** Nguồn phục hồi là state đã persist trong `JobRepository`, cộng với tính ổn định của input và transaction/output.

## 3. Phân loại “dừng process”: khác nhau rất quan trọng

| Kiểu dừng | Điển hình | Trạng thái metadata có thể thấy | Cách kiểm tra |
| --- | --- | --- | --- |
| **Dừng có kiểm soát bởi Spring Batch** | Yêu cầu stop, step hoàn tất chunk hiện hành, framework ghi status | Thường `STOPPED` | Khởi động process mới và restart cùng instance |
| **Process kết thúc sau job `FAILED`** | Exception xảy ra, framework xử lý exception và lưu metadata | `FAILED` nếu cập nhật được | Sửa nguyên nhân, restart đúng instance |
| **OS gửi `SIGTERM`/shutdown thông thường** | Deployment, Pod terminating, `kill -TERM` | Phụ thuộc cách app xử lý shutdown và thời gian grace period | Không giả định tự động `STOPPED`; phải quan sát DB |
| **Hard kill** | Linux `kill -KILL`, Windows `Stop-Process -Force`, OOM kill, mất điện | Có thể còn `STARTED`/`STARTING` vì JVM không kịp lưu status cuối | Cần runbook phát hiện và xử lý stale execution trước khi restart |

Đây là điểm cốt lõi của bài thực hành. **Một process không còn chạy không đồng nghĩa `JobRepository` biết nó đã chết.** Nếu repository vẫn ghi execution `STARTED`, lệnh launch cùng tham số có thể bị từ chối vì Spring Batch cho rằng một execution của `JobInstance` đó vẫn đang chạy. Không tự đổi `status` bằng SQL trong một script tự động chỉ để bài test “xanh”.

Trong phần thực hành chính, ta tạo một cơ chế **yêu cầu dừng sau commit** để có một `STOPPED` đúng nghĩa, rồi tắt process và restart từ JVM khác. Phần hard kill sẽ được kiểm tra riêng, có kết quả kỳ vọng khác.

## 4. Kiến trúc project thực hành

```text
restart-lab/
  build.gradle
  docker-compose.yml
  src/main/java/com/example/restartlab/
    RestartLabApplication.java
    OrderLine.java
    StoredOrder.java
    BatchConfiguration.java
    StopAfterChunkListener.java
    RunJobOnce.java
  src/main/resources/
    application.yml
    schema.sql
  data/
    orders.csv
  control/
    stop.request              <-- chỉ xuất hiện khi yêu cầu dừng
```

Luồng:

```text
                   JVM A / JVM B
                        |
                  ApplicationRunner
                        |
               importOrdersJob
                        |
               importOrdersStep
                        |
    FlatFileItemReader (ItemStream, saveState=true)
                        |
             ItemProcessor (delay nhỏ)
                        |
               JdbcBatchItemWriter
                        |
                  PostgreSQL
            +-----------+-----------+
            |                       |
     processed_orders           BATCH_* tables
     (output nghiệp vụ)        (metadata/checkpoint)
            +-----------+-----------+
                        |
              Cùng DataSource /
              transaction manager
```

PostgreSQL được dùng **cả cho metadata Batch và bảng output** để kịch bản transaction dễ giải thích. Sau khi kiểm chứng mô hình này, bạn có thể mở rộng sang hai datasource khác nhau, file writer hoặc API bên ngoài; khi đó cần đánh giá tính nguyên tử và idempotency riêng.

Project giả định **Java 17+, Spring Boot 3.x, Spring Batch 5.x, Gradle**. Ví dụ API và package phù hợp hướng cấu hình của Spring Batch 5; nếu dùng Spring Batch 6, cần cập nhật import, builder và test utility theo phiên bản đang chạy.

## 5. Chuẩn bị PostgreSQL bền vững

Tạo `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: batch_lab
      POSTGRES_USER: batch_lab
      POSTGRES_PASSWORD: batch_lab_pw
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Khởi động database:

```bash
docker compose up -d
```

Volume `pgdata` tồn tại độc lập với JVM batch. **Không chạy `docker compose down -v` giữa hai execution**: cờ `-v` sẽ xóa volume và metadata cần cho restart. Mật khẩu minh họa chỉ dùng ở lab trên máy cá nhân, không dùng trong môi trường thật.

### 5.1. Dependency Gradle

Với project Spring Boot 3.x đã có Gradle plugin và dependency management tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Để chạy project, cấu hình plugin Spring Boot/Java và version tương ứng theo template của project. Không ghép tùy tiện Spring Boot 3 với Spring Batch 6 nếu dependency management của project chưa hỗ trợ.

### 5.2. `application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: ${BATCH_DB_URL:jdbc:postgresql://localhost:5433/batch_lab}
    username: ${BATCH_DB_USER:batch_lab}
    password: ${BATCH_DB_PASSWORD:batch_lab_pw}
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
  sql:
    init:
      mode: always

demo:
  mode: run
  business-date: "2026-11-16"
  source-version: "orders-v1"
  input-path: "./data/orders.csv"
  stop-file: "./control/stop.request"
  pause-ms: 120
```

`spring.batch.job.enabled=false` ngăn Spring Boot tự launch job ngoài lời gọi điều khiển của lab. `spring.batch.jdbc.initialize-schema=never` rất quan trọng: **mỗi lần JVM restart không được tự tạo lại schema `BATCH_*`**. Ở phần bootstrap sẽ tạm bật `always` **một lần duy nhất** để tạo schema metadata, sau đó trở về `never`.

`spring.sql.init.mode=always` làm Spring Boot thực thi `schema.sql` của demo khi startup. File SQL phải idempotent; production nên quản lý schema bằng migration thay vì lặp script tự động.

### 5.3. Schema output nghiệp vụ

Tạo `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS processed_orders (
    source_version VARCHAR(80) NOT NULL,
    order_id       VARCHAR(32) NOT NULL,
    amount         INTEGER NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (source_version, order_id)
);
```

Khóa `(source_version, order_id)` chống việc hai lần ghi cùng logical record tạo hai dòng vật lý. Đây là **lớp bảo vệ idempotency ở database**, không thay thế checkpoint. Nếu không có khóa này, một lỗi transaction hoặc rerun ngoài ý muốn có thể nhân đôi output dù job cuối cùng báo `COMPLETED`.

## 6. Viết ứng dụng Spring Boot chạy đúng một job rồi thoát

Tạo `RestartLabApplication.java`:

```java
package com.example.restartlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RestartLabApplication {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(RestartLabApplication.class, args);

        // Khi ApplicationRunner đã hoàn tất, đóng context và JVM.
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

Mục tiêu là mỗi lần gọi `java -jar` tạo **một process riêng**, kết nối repository đã có, chạy job một lần, đóng context rồi thoát. Lab không để scheduler tự khởi chạy job song song với thao tác manual.

Tạo hai record dữ liệu trong hai file Java riêng:

```java
// OrderLine.java
package com.example.restartlab;

public record OrderLine(String orderId, int amount) {}
```

```java
// StoredOrder.java
package com.example.restartlab;

public record StoredOrder(
    String sourceVersion,
    String orderId,
    int amount
) {}
```

Để thực hành dễ quan sát, input chỉ gồm `orderId` và `amount`; `sourceVersion` đến từ `JobParameters` và được đưa vào bản ghi output tại processor.

## 7. Cấu hình reader, processor, writer và step

Tạo `BatchConfiguration.java`:

```java
package com.example.restartlab;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BatchConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<OrderLine> ordersReader(
            @Value("#{jobParameters['inputPath']}") String inputPath) {

        return new FlatFileItemReaderBuilder<OrderLine>()
            .name("ordersReader")
            .resource(new FileSystemResource(inputPath))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderLine(
                fields.readString("orderId"),
                fields.readInt("amount")
            ))
            .saveState(true)
            .build();
    }

    @Bean
    @StepScope
    ItemProcessor<OrderLine, StoredOrder> ordersProcessor(
            @Value("#{jobParameters['sourceVersion']}") String sourceVersion,
            @Value("${demo.pause-ms:120}") long pauseMs) {

        return item -> {
            // Chỉ tạo độ trễ để kịp quan sát và phát tín hiệu stop.
            Thread.sleep(pauseMs);
            return new StoredOrder(
                sourceVersion, item.orderId(), item.amount());
        };
    }

    @Bean
    JdbcBatchItemWriter<StoredOrder> ordersWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<StoredOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO processed_orders (
                    source_version, order_id, amount
                ) VALUES (?, ?, ?)
                ON CONFLICT (source_version, order_id) DO NOTHING
                """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setString(1, item.sourceVersion());
                ps.setString(2, item.orderId());
                ps.setInt(3, item.amount());
            })
            // DO NOTHING có thể trả JDBC update count = 0.
            .assertUpdates(false)
            .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("ordersReader") FlatFileItemReader<OrderLine> reader,
            @Qualifier("ordersProcessor")
                ItemProcessor<OrderLine, StoredOrder> processor,
            @Qualifier("ordersWriter")
                JdbcBatchItemWriter<StoredOrder> writer,
            StopAfterChunkListener stopListener) {

        return new StepBuilder("importOrdersStep", repository)
            .<OrderLine, StoredOrder>chunk(10, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener((ChunkListener) stopListener)
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

### 7.1. Vì sao reader phải có `@StepScope` và `saveState(true)`?

`FlatFileItemReader` là reader có trạng thái: nó phải biết đã đọc tới đâu. `@StepScope` cho phép tạo reader mới với `inputPath` tương ứng từng step execution, tránh tái dùng một instance đã ở cuối file. `.name("ordersReader")` cung cấp tên ổn định cho state của reader. `.saveState(true)` cho phép framework lưu checkpoint vào `ExecutionContext` để mở lại sau restart.

**Cùng checkpoint chỉ có nghĩa khi input không thay đổi.** Nếu bạn sửa `orders.csv`, đổi thứ tự dòng hoặc thay file giữ nguyên path giữa hai lần chạy, vị trí đã lưu có thể trỏ sang dòng khác. Trong production, nên truyền `sourceVersion`, object version/checksum và giữ bản sao input bất biến tới khi kỳ xử lý kết thúc.

### 7.2. Vì sao writer dùng unique key và `ON CONFLICT`?

Chunk transaction trên cùng datasource giúp dữ liệu và metadata được phối hợp nhất quán trong lab. Nhưng khi system crash tại ranh giới commit, hoặc khi có một lần rerun, unique key còn giúp output không nhân đôi. `ON CONFLICT DO NOTHING` chỉ phù hợp khi **same source version + same order ID** phải biểu thị cùng dữ liệu; nếu hai lần ghi cùng khóa mà amount khác, ứng dụng nên có cơ chế báo conflict thay vì âm thầm bỏ qua. Trong lab, input được giữ bất biến để điều kiện đó hợp lệ.

`ON CONFLICT` là cú pháp PostgreSQL; nếu dùng H2, MySQL hoặc Oracle, cần đổi SQL theo dialect.

### 7.3. Vì sao chunk size 10?

Chunk size 10 khiến database có nhiều mốc commit khi xử lý 200 dòng. Độ trễ `Thread.sleep` trong processor chỉ giúp người thực hành kịp gửi tín hiệu dừng; trong production không thêm sleep như một phần của business processing.

Khi tăng chunk size, ít điểm checkpoint hơn nhưng mỗi lần lỗi có thể phải đọc lại nhiều item hơn. Khi giảm chunk size, số transaction và metadata update tăng. Chọn commit interval dựa trên đo lường và kiểm thử failure path, không chỉ tối ưu throughput.

## 8. Tạo tín hiệu dừng sau chunk commit

Để có một kịch bản **stop và restart được Spring Batch ghi nhận**, ta không dùng `kill -9` ở lần chạy chính. Thay vào đó, đặt một file `control/stop.request`; listener kiểm tra sau một chunk thành công và yêu cầu step dừng ở ranh giới an toàn.

Tạo `StopAfterChunkListener.java`:

```java
package com.example.restartlab;

import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StopAfterChunkListener implements ChunkListener {

    private static final Logger log =
        LoggerFactory.getLogger(StopAfterChunkListener.class);

    private final Path stopFile;

    public StopAfterChunkListener(
            @Value("${demo.stop-file:./control/stop.request}")
            String stopFilePath) {
        this.stopFile = Path.of(stopFilePath)
            .toAbsolutePath().normalize();
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();

        log.info(
            "event=chunk.committed jobExecutionId={} stepExecutionId={} "
                + "read={} write={} commits={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getCommitCount()
        );

        if (Files.exists(stopFile)) {
            // Đề nghị Batch không bắt đầu thêm chunk sau mốc này.
            step.setTerminateOnly();
            log.warn(
                "event=stop.requested stepExecutionId={} afterCommit={}",
                step.getId(), step.getCommitCount()
            );
        }
    }
}
```

Listener đọc cờ ở **`afterChunk`**, sau một chunk thành công, nên tránh yêu cầu dừng giữa lúc writer đang cập nhật dữ liệu. `setTerminateOnly()` yêu cầu step kết thúc qua cơ chế framework; với chu trình step chuẩn, Spring Batch có thể chuyển execution sang trạng thái dừng thích hợp. **Trạng thái thực tế phải được kiểm tra trong repository**, không chỉ dựa vào việc listener đã log `stop.requested`.

Cơ chế file flag này là **đồ dùng cho lab**, không phải một dịch vụ dừng job hoàn chỉnh. Với ứng dụng production, có thể dùng `JobOperator.stop(...)` và một cơ chế điều khiển được phân quyền phù hợp phiên bản/kiến trúc. Nếu tiến trình nhận `SIGKILL` thì `afterChunk` có thể không chạy; đó là kịch bản khác ở phần sau.

## 9. Chạy job theo `JobParameters` và trả exit code

Tạo `RunJobOnce.java`:

```java
package com.example.restartlab;

import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.stereotype.Component;

@Component
public class RunJobOnce implements ApplicationRunner, ExitCodeGenerator {

    private static final Logger log = LoggerFactory.getLogger(RunJobOnce.class);

    private final JobLauncher launcher;
    private final Job job;

    @Value("${demo.mode:run}")
    private String mode;

    @Value("${demo.business-date:2026-11-16}")
    private String businessDate;

    @Value("${demo.source-version:orders-v1}")
    private String sourceVersion;

    @Value("${demo.input-path:./data/orders.csv}")
    private String inputPath;

    private int exitCode = 0;

    public RunJobOnce(
            JobLauncher launcher,
            @Qualifier("importOrdersJob") Job job) {
        this.launcher = launcher;
        this.job = job;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        if ("init".equals(mode)) {
            log.info("Schema bootstrap mode: no batch job launched");
            return;
        }
        if (!"run".equals(mode)) {
            throw new IllegalArgumentException("Unknown demo.mode: " + mode);
        }

        Path input = Path.of(inputPath).toAbsolutePath().normalize();
        if (!Files.isRegularFile(input)) {
            throw new IllegalStateException("Input file does not exist");
        }

        JobParameters parameters = new JobParametersBuilder()
            // Hai tham số này IDENTIFYING: giữ nguyên khi restart.
            .addString("businessDate", businessDate)
            .addString("sourceVersion", sourceVersion)
            // Đường dẫn chỉ là thông tin bổ sung; phải giữ trỏ đúng
            // phiên bản file cũ trong suốt chuỗi execution.
            .addString("inputPath", input.toString(), false)
            .toJobParameters();

        JobExecution execution = launcher.run(job, parameters);

        log.info(
            "event=job.finished jobInstanceId={} jobExecutionId={} "
                + "status={} exitCode={}",
            execution.getJobInstance().getId(),
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus().getExitCode()
        );

        exitCode = execution.getStatus() == BatchStatus.COMPLETED ? 0
            : execution.getStatus() == BatchStatus.STOPPED ? 2
            : 1;
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
```

`ApplicationRunner` được gọi khi Spring Boot khởi động; trong cấu hình launcher đồng bộ thường dùng ở lab, nó chờ job kết thúc. Sau đó `RestartLabApplication.main` đóng Spring context và kết thúc JVM với exit code:

- `0`: job hoàn tất.
- `2`: job đã được dừng có kiểm soát.
- `1`: job trả trạng thái khác.

Nếu launcher được cấu hình **bất đồng bộ**, `run(...)` có thể trả về khi job chưa kết thúc; mẫu runner này cần điều chỉnh để chờ trạng thái cuối. Lab dùng launcher đồng bộ. Trường hợp `launcher.run` ném exception ngay khi không thể khởi chạy (ví dụ instance vẫn `STARTED`), Spring Boot có thể kết thúc startup với lỗi; cần xem exception và repository để phân loại.

**`inputPath` được đặt non-identifying vì danh tính logical input trong lab được kiểm soát bởi `sourceVersion`.** Trong production, phải đảm bảo `sourceVersion` thật sự gắn với file bất biến và có thể lưu checksum/object version. Không thay `inputPath` sang file khác trong lần restart chỉ vì nó không tham gia `JOB_KEY`.

## 10. Khởi tạo metadata schema đúng một lần

Spring Batch cần các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và các bảng params/context để lưu state. Đối với PostgreSQL, Spring Batch cung cấp script schema theo version.

Trong lab này, ta dùng Spring Boot initializer **một lần**:

```bash
# Build JAR theo cấu hình project Spring Boot đã tạo.
./gradlew bootJar

# LẦN DUY NHẤT: tạo các bảng metadata BATCH_*.
java -jar build/libs/restart-lab-0.0.1-SNAPSHOT.jar \
  --demo.mode=init \
  --spring.batch.jdbc.initialize-schema=always
```

Tên JAR trên là ví dụ; dùng tên file được Gradle thực sự tạo. Trên Windows PowerShell có thể đặt toàn bộ arguments trên một dòng. Khi `demo.mode=init`, runner không launch job, còn Batch schema initializer tạo bảng. Các lần chạy **sau đó** dùng `spring.batch.jdbc.initialize-schema=never` như `application.yml`.

Nếu schema đã tồn tại, **không chạy lại lệnh `initialize-schema=always`** một cách mù quáng: script tạo bảng theo version có thể báo lỗi do bảng tồn tại. Trong hệ thống thực, dùng Flyway/Liquibase hoặc quy trình migration có kiểm soát. Đồng thời, **không xóa schema để “reset” một bài restart đang làm**, vì như vậy mất toàn bộ lịch sử.

`schema.sql` của ứng dụng dùng `CREATE TABLE IF NOT EXISTS` nên bảng `processed_orders` có thể được kiểm tra/tạo khi startup mà không xóa dữ liệu giữa hai JVM.

## 11. Tạo input cố định và quan sát lần chạy đầu

Tạo 200 dòng dữ liệu, từ `O0001` đến `O0200`. Trên **PowerShell**:

```powershell
New-Item -ItemType Directory -Force .\data, .\control | Out-Null

$rows = @("orderId,amount") + (1..200 | ForEach-Object {
    "O{0:D4},{1}" -f $_, ($_ * 10)
})

[System.IO.File]::WriteAllLines(
    (Join-Path (Get-Location) "data\orders.csv"),
    $rows,
    (New-Object System.Text.UTF8Encoding($false))
)

# Dọn cờ stop của lần thử trước, KHÔNG dọn database.
Remove-Item .\control\stop.request -ErrorAction SilentlyContinue
```

Trên **Bash/Linux/macOS**:

```bash
mkdir -p data control
{
  echo 'orderId,amount'
  for i in $(seq 1 200); do
    printf 'O%04d,%d\n' "$i" "$((i * 10))"
  done
} > data/orders.csv

rm -f control/stop.request
```

Không sửa nội dung hoặc thứ tự file trong quá trình thử. Nếu muốn tạo test case mới, dùng **`sourceVersion` khác** và đường dẫn file/version mới thay vì ghi đè input của instance cũ.

### 11.1. Khởi chạy process A

Ở terminal thứ nhất, chạy:

```bash
java -jar build/libs/restart-lab-0.0.1-SNAPSHOT.jar \
  --demo.mode=run \
  --demo.business-date=2026-11-16 \
  --demo.source-version=orders-v1 \
  --demo.input-path=./data/orders.csv
```

Trong PowerShell 5.1, có thể viết một dòng:

```powershell
java -jar .\build\libs\restart-lab-0.0.1-SNAPSHOT.jar --demo.mode=run --demo.business-date=2026-11-16 --demo.source-version=orders-v1 --demo.input-path=.\data\orders.csv
```

Với `pause-ms=120`, mỗi chunk 10 item mất khoảng một giây cộng I/O. Log có thể có dạng:

```text
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=10 write=10 commits=1
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=20 write=20 commits=2
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=30 write=30 commits=3
```

Các ID và thời gian là **ví dụ**, không cố định trong môi trường thật. `afterChunk` là tín hiệu chu kỳ commit thành công, hữu ích để biết lúc nào gửi yêu cầu dừng. Không lấy số cuối log làm checkpoint tuyệt đối nếu process chết trước khi flush log.

### 11.2. Gửi yêu cầu dừng từ terminal thứ hai

Sau khi thấy vài lần `chunk.committed`, trong terminal thứ hai tạo file stop:

```powershell
New-Item -ItemType File -Force .\control\stop.request | Out-Null
```

Hoặc Bash:

```bash
touch control/stop.request
```

Lần `afterChunk` kế tiếp sẽ phát hiện file, gọi `step.setTerminateOnly()`, yêu cầu step dừng; framework cập nhật metadata và runner thoát. Ví dụ log:

```text
event=chunk.committed jobExecutionId=101 stepExecutionId=501 read=40 write=40 commits=4
event=stop.requested stepExecutionId=501 afterCommit=4
event=job.finished jobInstanceId=41 jobExecutionId=101 status=STOPPED exitCode=STOPPED
```

Tại đây **process A đã kết thúc**. Đừng tiếp tục cho process B chạy khi process A còn sống; restart có thể bị từ chối do execution cũ vẫn đang chạy hoặc tạo điều kiện race.

Nếu dừng quá muộn, job có thể đã xử lý hết 200 dòng và `COMPLETED`. Khi đó phải dùng một `sourceVersion` **mới** để làm lại kịch bản, hoặc tăng `demo.pause-ms`/số dòng cho lần thử mới. Không xóa metadata của instance đã hoàn tất rồi gọi đó là test restart.

## 12. Kiểm tra trạng thái sau khi process A kết thúc

Kết nối PostgreSQL, chẳng hạn:

```bash
docker compose exec postgres psql -U batch_lab -d batch_lab
```

### 12.1. Đếm output đã commit

```sql
SELECT COUNT(*) AS committed_rows
FROM processed_orders
WHERE source_version = 'orders-v1';
```

Nếu phát lệnh dừng giữa chừng, kỳ vọng:

```text
0 < committed_rows < 200
```

Ví dụ `committed_rows=40` khi dừng sau chunk thứ tư. Con số thực tế tùy thời điểm tạo cờ. Bảng `processed_orders` giữ lại kết quả đã commit qua lần JVM thoát vì dữ liệu nằm trong PostgreSQL volume.

### 12.2. Kiểm tra các `JobExecution`

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS AS JOB_STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID;
```

Kỳ vọng ở pha stop có kiểm soát: execution mới nhất của instance tương ứng `orders-v1` có `STATUS='STOPPED'`. Nếu thấy `STARTED`, **chưa được coi là bài stop chuẩn hoàn tất**: kiểm tra process còn tồn tại không và phương thức dừng thực tế đã dùng.

Để xem identifying parameters trong schema JDBC Spring Batch 5.x:

```sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE PARAMETER_NAME IN (
    'businessDate', 'sourceVersion', 'inputPath'
)
ORDER BY JOB_EXECUTION_ID, PARAMETER_NAME;
```

Đối chiếu `businessDate`, `sourceVersion` là identifying; `inputPath` là non-identifying. Nếu một test suite có nhiều instance của cùng tên job, hãy lọc/đối chiếu đầy đủ tham số để tránh đọc nhầm execution.

### 12.3. Kiểm tra step và checkpoint

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

Metadata checkpoint nằm trong `BATCH_STEP_EXECUTION_CONTEXT`, gắn với step execution. **Không sửa hoặc xóa context** ở bước này. Context có thể được framework serialize ở định dạng phụ thuộc version; để đọc có cấu trúc trong ứng dụng, có thể dùng `JobExplorer` và `StepExecution.getExecutionContext()` thay vì tự parse cột `SERIALIZED_CONTEXT` từ SQL.

Ví dụ một service đọc metadata Spring Batch 5.x:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

void showStepState(JobExplorer explorer, long executionId) {
    JobExecution execution = explorer.getJobExecution(executionId);
    if (execution == null) {
        throw new IllegalArgumentException("Unknown executionId");
    }
    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
            "step=%s status=%s context=%s%n",
            step.getStepName(),
            step.getStatus(),
            step.getExecutionContext()
        );
    }
}
```

Đây là snippet phục vụ quan sát trong **lab**, không nên log toàn bộ `ExecutionContext` trong production: context có thể chứa dữ liệu nhạy cảm hoặc state lớn. Khi dùng thực tế, chỉ xuất những key checkpoint đã được phép xem.

## 13. Khởi chạy process B và xác nhận restart

Trước tiên **xóa cờ stop**, nhưng **không xóa database hoặc file input**:

```powershell
Remove-Item .\control\stop.request -ErrorAction SilentlyContinue
```

Từ một terminal mới, chạy lại **đúng các identifying parameters**:

```powershell
java -jar .\build\libs\restart-lab-0.0.1-SNAPSHOT.jar --demo.mode=run --demo.business-date=2026-11-16 --demo.source-version=orders-v1 --demo.input-path=.\data\orders.csv
```

Ở lần này không tạo cờ dừng. Process B phải dùng **cùng database**, **cùng `sourceVersion` và `businessDate`**, **cùng input bất biến**. Spring Batch sẽ tạo một `JobExecution` mới thuộc `JobInstance` đã dừng; `FlatFileItemReader` được tạo lại và dùng state đã persist để tiếp tục. Nếu step hoàn tất, process B kết thúc với exit code `0` trong cấu hình demo.

### 13.1. Bằng chứng metadata

Truy vấn các execution của instance tương ứng và xác nhận mẫu:

```text
JobInstance #41
  ├─ JobExecution #101  STOPPED
  └─ JobExecution #102  COMPLETED
```

Điểm cần kiểm tra là `JOB_INSTANCE_ID` **giống nhau**, còn `JOB_EXECUTION_ID` **khác nhau**. Nếu hai lần chạy có `JOB_INSTANCE_ID` khác nhau, bạn đã **tạo instance mới**, không chứng minh khả năng restart từ checkpoint.

Khi query nhiều execution, hãy đọc metadata của riêng kỳ test, không chỉ nhìn dòng có ID lớn nhất của mọi job. Một `JobExecution` thành công cũng không thay thế assertions về output.

### 13.2. Bằng chứng dữ liệu output

```sql
-- Đủ 200 dòng output cho sourceVersion này.
SELECT COUNT(*) AS total
FROM processed_orders
WHERE source_version = 'orders-v1';

-- Có đủ 200 khóa nghiệp vụ duy nhất.
SELECT COUNT(DISTINCT order_id) AS distinct_orders
FROM processed_orders
WHERE source_version = 'orders-v1';

-- Không có duplicate theo business key đã chọn.
SELECT source_version, order_id, COUNT(*) AS occurrences
FROM processed_orders
WHERE source_version = 'orders-v1'
GROUP BY source_version, order_id
HAVING COUNT(*) > 1;

-- Đối chiếu giá trị đầu và cuối.
SELECT order_id, amount
FROM processed_orders
WHERE source_version = 'orders-v1'
  AND order_id IN ('O0001', 'O0100', 'O0200')
ORDER BY order_id;
```

Kỳ vọng:

| Kiểm tra | Kết quả |
| --- | --- |
| Số dòng | `200` |
| Số `order_id` khác nhau | `200` |
| Truy vấn duplicate | `0` hàng |
| `O0001` | `amount=10` |
| `O0100` | `amount=1000` |
| `O0200` | `amount=2000` |
| Job instance ID qua hai process | Không đổi |
| Execution đầu và execution restart | `STOPPED` rồi `COMPLETED` |

Vì bảng có primary key `(source_version, order_id)`, truy vấn duplicate theo khóa này sẽ luôn không có kết quả nếu constraint hoạt động. Để chứng minh **không mất item**, phải kiểm tra cả số dòng, tập khóa và payload. Một writer dùng `ON CONFLICT DO NOTHING` có thể che việc xử lý lại item đã tồn tại; chỉ `COUNT(*)=200` chưa chứng minh reader đã tiết kiệm công việc nhờ checkpoint. Muốn kiểm tra **đúng điểm khôi phục**, đối chiếu `ExecutionContext`, read count của lần restart và các mốc log.

### 13.3. Vì sao không cộng tất cả `readCount` rồi so với 200?

`StepExecution` có counters riêng theo từng lần thực thi. Chunk chưa commit có thể bị đọc rồi rollback, sau đó được đọc lại trong lần restart. Khi một step có retry, số lần gọi thực tế đến processor/writer cũng không nhất thiết bằng số item nghiệp vụ duy nhất. Vì thế tổng counters qua nhiều `JobExecution` có thể **khác số nguồn duy nhất**, tùy điểm dừng và implementation. Kết luận cuối phải dựa trên dataset và output, còn counters giúp giải thích đường thực thi.

## 14. Thử hard kill: điều gì thực sự xảy ra?

Sau khi hoàn thành bài stop chuẩn, dùng **một `sourceVersion` mới** (ví dụ `orders-hardkill-v1`) để tách kết quả. Đảm bảo file `control/stop.request` không tồn tại, rồi khởi chạy lại bằng process mới với version đó.

**Đây là thử nghiệm cố ý gây mất process. Chỉ thực hiện trong lab với database và output riêng, không làm trên job production.**

### 14.1. Linux/macOS: gửi `SIGKILL`

Khởi chạy ở terminal thứ nhất với `sourceVersion=orders-hardkill-v1`; khi log đã cho biết một vài chunk commit, tìm PID của process rồi gửi:

```bash
kill -KILL <PID_CUA_JAVA_PROCESS>
```

`<PID_CUA_JAVA_PROCESS>` là placeholder; phải thay bằng PID đúng của **JVM lab**, không phải Postgres hay ứng dụng khác.

### 14.2. Windows PowerShell: dừng cưỡng bức đúng PID

Nếu process được khởi chạy qua `Start-Process` trong môi trường lab:

```powershell
$p = Start-Process -FilePath "java" -ArgumentList @(
    "-jar",
    ".\build\libs\restart-lab-0.0.1-SNAPSHOT.jar",
    "--demo.mode=run",
    "--demo.business-date=2026-11-16",
    "--demo.source-version=orders-hardkill-v1",
    "--demo.input-path=.\data\orders.csv"
) -PassThru

# Quan sát PID và log riêng theo cấu hình khi cần.
$p.Id

# Chỉ khi đã xác nhận đây là đúng process lab:
Stop-Process -Id $p.Id -Force
```

**Không chạy ngay `Stop-Process` trước khi job commit một chunk** nếu mục đích là quan sát metadata/output còn lại giữa chừng. Dùng log hoặc truy vấn DB để xác định thời điểm; ví dụ lệnh chỉ thể hiện thao tác kỹ thuật, không tự canh mốc an toàn.

### 14.3. Kết quả cần quan sát, không nên suy đoán

Khi JVM bị kill đột ngột, Java shutdown hooks, `finally` và callback lifecycle của Spring Batch **có thể không chạy**. Metadata có thể còn:

```text
JobExecution #103: STARTED
StepExecution #503: STARTED
END_TIME: null
```

Đồng thời PostgreSQL có thể đã commit một số chunk trước khi process chết, trong khi chunk đang mở bị rollback khi connection bị ngắt. Bản ghi `STARTED` không phải bằng chứng rằng worker vẫn tồn tại; nó cũng chưa phải trạng thái terminal cho phép restart bình thường.

Nếu chạy lại **cùng identifying parameters** ngay lập tức, Spring Batch có thể từ chối với `JobExecutionAlreadyRunningException` hoặc lỗi liên quan instance vẫn được xem là running. **Đây là một kết quả có ý nghĩa của bài test**, không phải dấu hiệu repository bị mất metadata.

### 14.4. Vì sao không tự sửa trực tiếp bảng `BATCH_*`?

Một cách xử lý dễ gây mất dữ liệu là:

```text
Kill process
   ↓
UPDATE BATCH_JOB_EXECUTION SET STATUS='FAILED' ...  (không kiểm soát)
   ↓
Launch lại
```

Thay đổi trạng thái job một cách tùy tiện có thể bỏ sót trạng thái step, các trường version, `ExecutionContext`, transaction còn dang dở, hoặc nhầm một execution **thực sự vẫn đang chạy trên node khác**. Hậu quả là hai execution cùng ghi output hoặc restart từ checkpoint không nhất quán.

Khi có stale `STARTED`, quy trình vận hành cần:

1. **Xác nhận worker/process cũ đã chết thật** trên tất cả node liên quan; kiểm tra scheduler, Pod và distributed lock, không chỉ nhìn một máy.
2. **Đảm bảo tài nguyên đã được giải phóng** và không còn transaction/worker khác đang ghi cùng dataset.
3. **Đối chiếu output đã commit** với checkpoint cuối có thể xác minh và input version.
4. **Sao lưu metadata và ghi nhận incident** trước khi thực hiện bất kỳ thủ tục recovery nào.
5. **Áp dụng quy trình administrative recovery được phê duyệt, phù hợp Spring Batch version**, để đưa các execution bị kẹt về trạng thái nhất quán theo hướng dẫn vận hành của dự án. Việc này có thể đòi hỏi thao tác bảo trì metadata có kiểm soát; không nên có script “tự sửa status” chung cho mọi job.
6. Chỉ sau khi trạng thái đã an toàn, **restart hoặc rerun theo chính sách nghiệp vụ**, rồi xác minh output không mất/trùng.

`JobOperator.abandon(...)` **không phải lối tắt để restart**: một step/job được đánh dấu `ABANDONED` mang ngữ nghĩa không tiếp tục theo cách restart thông thường. Dùng sai có thể khiến step bị bỏ qua hoặc instance không thể restart như kỳ vọng. Không tự gọi `stop(...)` trên execution mà process đã biến mất rồi giả định status sẽ được cập nhật đầy đủ.

**Kết luận của hard-kill test:** JDBC metadata bền vững là điều kiện cần cho phục hồi, nhưng **không tự phát hiện mọi cái chết của process và không tự sửa mọi trạng thái stale**. Kế hoạch recovery phải bao gồm hạ tầng và sự kiện process chết đột ngột.

## 15. `SIGTERM`, graceful shutdown và Kubernetes

Trong production, một Pod thường nhận `SIGTERM` khi deployment thay thế hoặc Kubernetes scale down, sau đó có một khoảng *grace period* trước khi bị kill cưỡng bức. Nhưng:

- JVM nhận `SIGTERM` **không có nghĩa** Batch tự chuyển `JobExecution` thành `STOPPED`.
- Nếu process đang chạy job đồng bộ, Spring context shutdown và việc cập nhật metadata có thể cạnh tranh thời gian.
- Nếu quá `terminationGracePeriodSeconds`, Pod có thể bị kill trước khi chunk/step hoàn tất.
- Nếu worker không phản hồi stop hoặc đang chờ I/O lâu, status có thể vẫn là `STARTED`.
- Mỗi Pod có filesystem riêng; file input/output đặt trên vùng ephemeral sẽ mất khi Pod được thay thế.

Với batch cần restart trên Pod mới, nên dùng PostgreSQL hoặc metadata store bền vững **ngoài Pod**, input/object version bất biến và output staging có độ bền phù hợp. Thiết kế **cooperative stop** qua Batch operator, trạng thái điều phối hoặc lifecycle hook đã được thử nghiệm. Chỉ dùng `preStop`/shutdown hook khi hiểu đúng thời gian và API cần gọi; chúng không thay thế reconciliation khi Pod bị kill đột ngột.

Một kịch bản production có thể chia làm hai luồng:

```text
Luồng dừng có kiểm soát:
  request stop → hoàn tất chunk → lưu STOPPED
  → process thoát → Pod mới restart cùng JobInstance

Luồng dừng không kiểm soát:
  process chết → repository có thể còn STARTED
  → phát hiện stale + xác nhận worker chết
  → recovery có kiểm soát → restart/rerun + đối soát
```

Đừng đánh đồng hai luồng khi viết runbook hoặc đặt SLO.

## 16. Những nguồn gây duplicate hoặc mất dữ liệu sau restart

Ngay cả khi metadata đã ghi và `JobInstance` đúng, restart vẫn có thể không an toàn nếu input hoặc writer không giữ đúng hợp đồng.

| Nguyên nhân | Biểu hiện | Cách phòng ngừa |
| --- | --- | --- |
| Dùng H2 in-memory | JVM mới không thấy checkpoint cũ | Dùng PostgreSQL/RDBMS hoặc storage metadata bền vững |
| Thêm `UUID` identifying mỗi lần chạy | Tạo instance mới, đọc lại từ đầu | Giữ `businessDate` và `sourceVersion` cho cùng logical run |
| Sửa CSV khi process dừng | Offset cũ trỏ tới dòng khác | Cố định file/object version, hash/checksum |
| `.saveState(false)` | Reader không khôi phục vị trí đã lưu | Bật `saveState(true)` với reader có state |
| Đổi `reader.name` giữa restart | Context key thay đổi | Giữ contract tên và định dạng state ổn định |
| Reader không được framework quản lý như `ItemStream` | `open/update/close` không chạy đúng | Đăng ký stream hoặc delegate lifecycle đúng |
| Writer ghi API ngoài transaction | Timeout nhưng API đã xử lý, retry gửi lại | Idempotency key + outbox/reconciliation |
| Hai datasource commit độc lập | Business output và metadata lệch nhau | Xem transaction boundary, unique key và recovery |
| Truy vấn paging thiếu `ORDER BY` ổn định | Restart skip/đọc lại row | Dùng sort key duy nhất, snapshot |
| Partition range bị đổi | Worker mới quét lại vùng worker cũ | Range/name ổn định theo instance |
| Xóa file output tạm khi STOPPED | Reader tiếp tục nhưng thiếu output cũ | Cleanup theo vòng đời instance, không xóa sớm |
| Hai node chạy cùng kỳ | Ghi trùng hoặc tranh chấp output | Điều phối scheduler + identifying params + constraint |
| Hard kill để lại `STARTED` | Restart bị từ chối | Phát hiện stale và xử lý vận hành có kiểm soát |

Với mục tiêu **không duplicate**, đừng chỉ kiểm tra `writeCount`. Với JDBC upsert, cùng một item có thể được gửi tới writer hai lần nhưng bảng vẫn có một row. Để chứng minh restart đúng checkpoint, cần kết hợp context, log và số item thực sự phải xử lý lại. Đối với API, phải đối chiếu thêm lịch sử request/idempotency bên đích.

## 17. Mở rộng: test failure trong chunk thay vì stop

Bài thực hành chính dừng ở ranh giới chunk. Để kiểm tra rollback, có thể chủ động làm writer ném exception ở một item sau khi vài chunk đã commit.

Ví dụ một writer decorator **chỉ dùng trong test**:

```java
public final class FailOnceWriter<T> implements ItemWriter<T> {
    private final ItemWriter<T> delegate;
    private final java.util.concurrent.atomic.AtomicBoolean failOnce;

    public FailOnceWriter(
            ItemWriter<T> delegate,
            java.util.concurrent.atomic.AtomicBoolean failOnce) {
        this.delegate = delegate;
        this.failOnce = failOnce;
    }

    @Override
    public void write(Chunk<? extends T> items) throws Exception {
        if (failOnce.compareAndSet(true, false)) {
            throw new IllegalStateException("Injected failure before writing");
        }
        delegate.write(items);
    }
}
```

Đây là một thành phần mẫu; các import `ItemWriter` và `Chunk` từ Spring Batch 5.x cần được khai báo trong class test thực. `AtomicBoolean` còn sống trong cùng JVM không tự tồn tại qua restart process; nếu muốn gây lỗi đúng **một lần qua hai process**, dùng cấu hình external flag hoặc một trạng thái test bền vững và có kiểm soát.

Sau lỗi:

1. Execution đầu có `FAILED` nếu framework kịp lưu trạng thái.
2. Các chunk commit trước đó vẫn ở output.
3. Chunk gây lỗi được rollback nếu writer dùng cùng transaction DB.
4. Restart với identifying parameters cũ và state được lưu.
5. Kết quả cuối phải chính xác như không có lỗi.

Đặc biệt nên thử lỗi ở **trước commit** và **sau khi side effect ngoài transaction được đích xác nhận**, vì hai vị trí lỗi có hệ quả rất khác nhau.

## 18. Gợi ý tích hợp test tự động nhiều process

Khi đã làm thủ công, có thể xây một integration test harness điều khiển **process con**, database test và cờ stop. Đây là hướng tự động hóa tốt hơn việc giả lập toàn bộ trong một `@SpringBootTest`.

```text
Test harness (process cha)
       |
       +--> PostgreSQL test container / DB riêng
       |
       +--> Process A: java -jar restart-lab.jar
       |        |
       |        +-- đợi log/DB: commitCount >= 3
       |        +-- tạo stop.request
       |        +-- đợi process thoát
       |
       +--> Assert DB: STOPPED, 0 < outputCount < expected
       |
       +--> xóa stop.request
       |
       +--> Process B: java -jar restart-lab.jar
       |        |
       |        +-- đợi process thoát
       |
       +--> Assert DB: COMPLETED, same JobInstance,
                       different JobExecution,
                       output đúng/không trùng
```

Đây là **đề cương test harness**, không phải lệnh Gradle được yêu cầu chạy trong bài này. Khi hiện thực:

- Dùng database/port/volume **riêng cho test**.
- Chờ điều kiện thực từ DB hoặc log có cấu trúc, không chỉ `Thread.sleep(3000)` rồi mặc định đã commit.
- Có timeout hợp lý và cleanup mọi process test, file cờ, DB container.
- Không để test chạm database/file của production.
- Kiểm tra kết quả ngay cả khi process con thoát với exit code không như mong đợi.
- Tránh phụ thuộc vào số ID tự tăng của repository; assert quan hệ identity/status.

Ví dụ đoạn Java của harness dùng `ProcessBuilder`:

```java
Process first = new ProcessBuilder(
    "java", "-jar", jarPath,
    "--demo.mode=run",
    "--demo.business-date=2026-11-16",
    "--demo.source-version=fixture-v1",
    "--demo.input-path=" + inputPath
).inheritIO().start();

// Thực hiện polling DB cho tới khi có vài chunk đã commit.
// Tạo file stop rồi chờ process A thoát có timeout.
// Dùng database và file đúng của test fixture.

if (!first.waitFor(60, java.util.concurrent.TimeUnit.SECONDS)) {
    first.destroyForcibly();
    throw new IllegalStateException("Process A did not stop in time");
}
```

`jarPath`, `inputPath` là biến do harness chuẩn bị. Code minh họa mới chỉ thể hiện cách khởi chạy process; phần polling/stop/assertions phải được viết đầy đủ trong dự án test thật. Với process B, dùng lại chính `fixture-v1`, cùng file và cùng database.

### 18.1. Assertions cho hai execution

Sau khi lấy `firstExecution` và `restartExecution` từ `JobExplorer` hoặc query metadata:

```java
assertThat(firstExecution.getStatus())
    .isEqualTo(BatchStatus.STOPPED);

assertThat(restartExecution.getStatus())
    .isEqualTo(BatchStatus.COMPLETED);

assertThat(restartExecution.getJobInstance().getId())
    .isEqualTo(firstExecution.getJobInstance().getId());

assertThat(restartExecution.getId())
    .isNotEqualTo(firstExecution.getId());

Integer resultCount = jdbcTemplate.queryForObject(
    """
    SELECT COUNT(*) FROM processed_orders
    WHERE source_version = ?
    """,
    Integer.class,
    "fixture-v1"
);
assertThat(resultCount).isEqualTo(200);
```

Đây là phần assertions minh họa, yêu cầu các object/fixture được khởi tạo trong test harness. Nên bổ sung kiểm tra tập `order_id` và `amount`, không chỉ đếm hàng.

## 19. Cách lập một báo cáo kết quả thực hành

Sau mỗi lượt chạy, ghi lại một phiếu bằng chứng thay vì chỉ chụp ảnh thông báo `COMPLETED`:

| Trường | Kết quả cần ghi |
| --- | --- |
| `jobName` | `importOrdersJob` |
| Input | `orders.csv`, 200 dòng, source version và checksum |
| Identifying parameters | `businessDate=2026-11-16`, `sourceVersion=orders-v1` |
| Storage metadata | PostgreSQL trên Docker volume còn nguyên giữa hai JVM |
| Process A | PID, lệnh khởi chạy, thời điểm gửi stop, exit code |
| Execution A | `JobInstance ID`, `JobExecution ID`, status `STOPPED` |
| Output A | Số row đã commit nhỏ hơn 200 |
| Process B | PID/lệnh khởi chạy mới, không còn file stop |
| Execution B | Cùng `JobInstance ID`, `JobExecution ID` khác, `COMPLETED` |
| Output B | 200 row và 200 khóa duy nhất, amount đúng |
| Hard-kill case | `STARTED` stale có xuất hiện không; procedure xử lý đã áp dụng |

Không cần các ID hoặc số row của ví dụ phải khớp tuyệt đối vì thời điểm gửi stop khác nhau. Điều quan trọng là **quan hệ giữa hai execution**, tính bất biến của input, checkpoint đã persist và output cuối.

## 20. Những lỗi thường gặp khi làm lab

### 20.1. Lỗi “relation BATCH_JOB_INSTANCE already exists”

Bạn đã chạy bootstrap schema `initialize-schema=always` thêm lần nữa. Giữ `initialize-schema=never` sau lần khởi tạo đầu; nếu cần làm lab hoàn toàn mới, tạo database test khác hoặc reset có chủ đích sau khi đã lưu bằng chứng, không xóa schema của instance đang thử restart.

### 20.2. `JobInstanceAlreadyCompleteException`

Job cùng identifying parameters đã `COMPLETED`. Đó là hành vi đúng: Spring Batch không tự chạy lại một job instance đã hoàn tất. Muốn thử một **kỳ mới**, thay `sourceVersion`/business key có chủ đích; muốn thử restart thì phải bắt đầu bằng một execution thực sự `STOPPED` hoặc `FAILED`.

### 20.3. `JobExecutionAlreadyRunningException`

Có thể process trước vẫn chạy, hoặc đã bị hard kill và metadata còn `STARTED`. Kiểm tra worker/node thật và repository; không tự cập nhật status bằng lệnh SQL ngắn thiếu runbook.

### 20.4. Lần restart xử lý lại cả file

Kiểm tra identifying parameters, `@StepScope`, tên reader, `.saveState(true)`, `ExecutionContext` có tồn tại và file input có giữ nguyên không. Nếu `sourceVersion` bị đổi, đây là một **JobInstance mới**, không phải restart.

### 20.5. Lần restart không tạo đủ output

Có thể input bị đổi thứ tự, file ở Pod cũ đã mất, output path bị đổi, hoặc checkpoint và transaction khác datasource không nhất quán. So sánh tập business key giữa input và output, rồi điều tra reader state và commit boundary.

### 20.6. Database có đủ 200 dòng nhưng thực ra reader đã đọc lại từ đầu

Unique key/`ON CONFLICT DO NOTHING` có thể che lỗi đọc lại. Kiểm tra `JobInstance`, step context, log mốc chunk và số item thực sự được đọc trong execution B. Idempotency và restart đúng checkpoint là **hai thuộc tính khác nhau**, cần kiểm chứng riêng.

### 20.7. Stop file vẫn còn ở lần restart

Listener sẽ yêu cầu dừng sau chunk đầu của process B, nên job lại `STOPPED`. Xóa `control/stop.request` trước khi khởi chạy lại. Không xóa file input hoặc metadata cùng lúc.

### 20.8. `docker compose down -v` giữa hai pha

Tùy chọn `-v` xóa PostgreSQL volume, gồm `BATCH_*` và bảng output. Sau đó bài test không còn điều kiện chứng minh restart xuyên process. Dùng `docker compose stop` hoặc giữ DB chạy suốt hai pha; chỉ dọn volume khi đã hoàn thành toàn bộ lab.

### 20.9. Ném `SIGTERM` rồi tin rằng job `STOPPED`

`SIGTERM` là yêu cầu từ OS, không mặc nhiên là thao tác `JobOperator.stop`. Quan sát metadata thực tế, thời gian đóng Spring context và trạng thái các chunk; với hard kill, xử lý theo kịch bản stale metadata.

## 21. Bài tập nâng cao

1. **Đổi chunk size:** thực hiện lab với chunk size 5, 10, 25. Quan sát số checkpoint và lượng item cần xử lý lại, nhưng giữ output cuối chính xác.
2. **Giết JVM giữa chunk:** dùng hard kill, ghi lại `JobExecution.STATUS`, output đã commit và sự khác nhau với stop có kiểm soát; viết runbook xử lý.
3. **Thay input version:** thử sửa `orders.csv` giữa hai execution và chứng minh vì sao checkpoint theo dòng không còn đáng tin. Sau đó bổ sung checksum đầu vào để chặn restart khi nguồn đổi.
4. **Writer file:** thay JDBC writer bằng `FlatFileItemWriter`, lưu file trên vùng bền vững và kiểm tra trạng thái file/append/header khi restart; xuất file tạm rồi publish một lần.
5. **API không có transaction chung:** giả lập API nhận request thành công nhưng client timeout, đo duplicate khi retry; bổ sung idempotency key từ business identity.
6. **Hai instance ứng dụng:** cho hai launcher có cùng identifying parameters thử chạy đồng thời và quan sát repository; lặp với parameters khác nhau nhưng cùng output để thấy cần thêm unique constraint và scheduler coordination.
7. **Multi-process automated test:** triển khai `ProcessBuilder` + polling DB + PostgreSQL Testcontainers, chạy trên CI, báo cáo không chỉ status mà cả dữ liệu đầu ra.

## 22. Kết luận

**Kiểm tra restart sau khi process bị dừng** không chỉ là chạy lại lệnh `java -jar`. Một bài kiểm tra có giá trị phải giữ **database metadata bền vững**, dùng đúng **`JobInstance`**, bảo toàn **input version**, xác minh **checkpoint và transaction**, đồng thời chứng minh **output cuối không mất/không trùng dữ liệu**.

Dừng có kiểm soát sau chunk và **hard kill** là hai tình huống khác nhau. Với `STOPPED`/`FAILED` đã được Spring Batch ghi nhận, một process mới có thể restart theo metadata khi cấu hình cho phép. Với process chết đột ngột, metadata có thể kẹt ở `STARTED`; khi ấy cần phát hiện stale execution, xác minh worker đã chết và thực hiện recovery có kiểm soát trước khi thử tiếp tục. Thiết kế đúng gồm cả **happy path, failure path và runbook vận hành**.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobExecution`, tham số định danh và restart.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): commit interval, chunk và transaction.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close` và checkpoint trong `ExecutionContext`.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): lưu metadata bền vững và cấu hình transaction.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng `BATCH_*` dùng để tra trạng thái job/step.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử job, step, status và khả năng restart.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): auto-configuration và khởi chạy job.
- [Kubernetes Documentation — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): tín hiệu kết thúc và vòng đời của container/Pod.
