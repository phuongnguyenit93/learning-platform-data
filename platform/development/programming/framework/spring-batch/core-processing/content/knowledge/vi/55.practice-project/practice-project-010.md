# Thêm listener và metric cho dự án Spring Batch

## 1. Mục tiêu dự án thực hành

Một Job Spring Batch chạy thành công không có nghĩa người vận hành biết nó đã làm gì. Trong production, cần trả lời được các câu hỏi:

- Job nào đang chạy, Job nào hoàn thành hoặc thất bại?
- Step đọc, ghi, filter hoặc skip bao nhiêu item?
- Mỗi chunk thường hoàn thành hay gặp lỗi?
- Thời gian thực thi Job/Step có tăng bất thường?
- Dữ liệu đầu ra có đúng không, hay Job chỉ báo `COMPLETED` nhưng xử lý sai?
- Có thể đưa metric vào Prometheus/Grafana để giám sát mà không làm lộ thông tin nhạy cảm hay không?

Bài **“Thêm listener và metric”** thuộc phần **Dự án thực hành** trong *Spring Batch Core Processing*. Bạn sẽ nâng cấp một Job nhập CSV vào database bằng ba nhóm listener và Micrometer:

1. `JobExecutionListener` theo dõi kết quả của cả Job.
2. `StepExecutionListener` ghi số item đọc/ghi/filter/skip.
3. `ChunkListener` theo dõi chunk thành công hoặc lỗi.
4. `MeterRegistry` lưu và xuất custom counters; Spring Batch/Micrometer cung cấp những metric thời lượng tích hợp.
5. `@SpringBatchTest` kiểm trạng thái, kết quả dữ liệu và custom metric.

Ví dụ chính nhắm tới **Java 17+, Spring Boot 3.x và Spring Batch 5.2.x** với H2 để chạy local. Phần cuối giải thích sự khác biệt khi chuyển sang Spring Batch 6.x. Các API giữa hai dòng phiên bản có thể khác, vì vậy không sao chép import một cách máy móc.

### Kết quả mong đợi

Với file đầu vào có 6 dòng dữ liệu, trong đó 2 dòng có amount bằng 0 bị filter:

| Kết quả | Giá trị |
| --- | ---: |
| Số item đọc | 6 |
| Số item filter | 2 |
| Số item ghi vào database | 4 |
| Tổng amount hợp lệ | 850 |
| BatchStatus cuối | `COMPLETED` |
| Job completion metric | Tăng 1 |
| Step read/write/filter metrics | Tăng lần lượt 6/4/2 |

Đây là **giá trị của fixture minh họa**, không phải ngưỡng chung cho mọi Job.

## 2. Listener là gì và nằm ở đâu?

Listener là callback chạy tại một điểm trong vòng đời Job/Step hoặc quanh thao tác xử lý item/chunk. Nó cho phép tách **quan sát, audit, thống kê** khỏi logic đọc/xử lý/ghi dữ liệu.

~~~text
         Spring Batch Job
                |
     JobExecutionListener.beforeJob
                |
                v
         importOrdersStep
                |
     StepExecutionListener.beforeStep
                |
                v
     +--------------------------+
     | Chunk: read -> process   |
     |        -> write -> commit|
     +--------------------------+
              |         |
         success       error
              |         |
              v         v
      afterChunk   afterChunkError
                |
     StepExecutionListener.afterStep
                |
                v
     JobExecutionListener.afterJob
                |
                v
           MeterRegistry
                |
                v
      Actuator / Prometheus
                |
                v
          Grafana / Alert
~~~

Trong Spring Batch 5.2, một số callback chính:

| Listener | Callback | Thông tin quan sát |
| --- | --- | --- |
| `JobExecutionListener` | `beforeJob`, `afterJob` | Job name, execution ID, BatchStatus, ExitStatus, lỗi cuối. |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Step name, read/write/filter/skip, commit/rollback, trạng thái. |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Chu kỳ chunk, hoàn thành hay lỗi chunk. |
| `ItemReadListener` | `beforeRead`, `afterRead`, `onReadError` | Lỗi và hoạt động reader. |
| `ItemProcessListener` | `beforeProcess`, `afterProcess`, `onProcessError` | Processor, filter và lỗi xử lý. |
| `ItemWriteListener` | `beforeWrite`, `afterWrite`, `onWriteError` | Writer và lỗi ghi. |
| `SkipListener` | Các callback `onSkip...` | Những item đã bị skip theo policy. |

**Không nên gắn quá nhiều callback cho từng item trong Job rất lớn** chỉ để ghi log INFO mỗi lần đọc: một triệu item có thể tạo một triệu dòng log. Với mục tiêu dashboard, ưu tiên số liệu tổng hợp hoặc sampling.

### Listener không thay thế business logic

- ItemProcessor vẫn chịu trách nhiệm chuyển đổi/filter.
- ItemWriter vẫn chịu trách nhiệm ghi dữ liệu.
- JobRepository vẫn lưu metadata và checkpoint.
- Listener chỉ quan sát, tạo metric/log, hoặc thực hiện hoạt động bổ sung được kiểm soát.

Nếu một lỗi trong listener khiến Job không thể tiếp tục, bạn có thể làm hỏng một lô dữ liệu chỉ vì hệ thống metrics tạm thời trục trặc. Với telemetry không quan trọng về nghiệp vụ, listener nên **không ném exception ra ngoài** nếu có thể xử lý lỗi quan sát an toàn.

## 3. Phân biệt metric sẵn có và metric tự định nghĩa

Spring Batch 5.2 tích hợp Micrometer và có một số metric dùng tiền tố `spring.batch`:

| Metric Micrometer tích hợp | Loại | Dùng để |
| --- | --- | --- |
| `spring.batch.job` | Timer | Thời lượng Job. |
| `spring.batch.job.active` | LongTaskTimer | Những Job đang hoạt động. |
| `spring.batch.step` | Timer | Thời lượng Step. |
| `spring.batch.step.active` | LongTaskTimer | Những Step đang hoạt động. |
| `spring.batch.item.read` | Timer | Thời gian đọc item. |
| `spring.batch.item.process` | Timer | Thời gian xử lý item. |
| `spring.batch.chunk.write` | Timer | Thời gian ghi chunk. |

Trong Spring Batch **5.2.x**, các metric tích hợp này được đăng ký qua Micrometer **global registry**. Khi dùng Spring Boot Actuator và Micrometer, cần chắc chắn registry được kết nối với backend quan sát. Tên metric xuất ở Prometheus được chuyển theo naming convention (ví dụ timer có thể mang suffix `_seconds`).

Chúng ta sẽ bổ sung các metric riêng:

| Metric ứng dụng | Loại | Ý nghĩa |
| --- | --- | --- |
| `app.batch.job.executions` | Counter | Số JobExecution đi tới callback `afterJob`, theo Job và BatchStatus. |
| `app.batch.step.items` | Counter | Số item theo operation `read`, `write`, `filter`, `skip`, cộng ở cuối StepExecution. |
| `app.batch.chunk.events` | Counter | Số callback chunk `success` hoặc `error` mà listener thấy. |

**Đây là metric do dự án tự tạo**, không phải metric built-in của Spring Batch. Những tên trên khi xuất qua Prometheus thường thành `app_batch_job_executions_total`, `app_batch_step_items_total` và `app_batch_chunk_events_total`.

Không đặt một custom timer y hệt timer built-in nếu không có mục đích riêng; làm vậy dễ tạo dashboard trùng nội dung và gây khó so sánh.

## 4. Cấu trúc dự án mẫu

~~~text
batch-observability-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/batch/
    │   │   ├── BatchObservabilityApplication.java
    │   │   ├── OrderRow.java
    │   │   ├── ImportJobConfiguration.java
    │   │   ├── JobMetricsListener.java
    │   │   ├── StepMetricsListener.java
    │   │   └── ChunkMetricsListener.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── orders.csv
    └── test/
        ├── java/com/example/batch/ImportJobIT.java
        └── resources/application-test.yml
~~~

Ví dụ dùng một Job `importOrdersJob`, một Step `importOrdersStep`, một CSV reader và một JDBC writer. Chúng ta lọc các bản ghi có `amount <= 0` bằng ItemProcessor, sau đó đo kết quả qua listener.

### 4.1. Dependency

Trong dự án Spring Boot 3.x tương thích Spring Batch 5.2.x, thêm các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    runtimeOnly 'com.h2database:h2'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các version của dependency trong đoạn trên được **Spring Boot dependency management** điều phối. Nếu dự án cần cố định Spring Batch 5.2, chọn release Spring Boot 3.x quản lý dòng đó hoặc cấu hình dependency management rõ ràng; không trộn ngẫu nhiên thư viện của Batch 5.x với API của 6.x.

`spring-boot-starter-actuator` cung cấp hạ tầng monitoring, `micrometer-registry-prometheus` cung cấp exporter, còn `spring-boot-starter-web` giúp ứng dụng demo tiếp tục chạy và phục vụ HTTP endpoint Actuator.

## 5. Chuẩn bị input và database

### 5.1. CSV đầu vào

File `src/main/resources/orders.csv`:

~~~csv
id,amount
1,100
2,0
3,200
4,150
5,0
6,400
~~~

Hai dòng có amount bằng 0 sẽ bị ItemProcessor filter. Bốn dòng hợp lệ có ID `1,3,4,6`, tổng amount `100 + 200 + 150 + 400 = 850`.

### 5.2. Schema nghiệp vụ

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

`PRIMARY KEY (id)` giúp bài thực hành phát hiện việc writer vô tình ghi trùng. Trong production, khóa này cần dựa trên business key và chính sách idempotency phù hợp; một khóa primary key không tự xử lý tất cả side effect ngoài transaction.

### 5.3. Cấu hình ứng dụng

File `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_observability;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
  batch:
    jdbc:
      initialize-schema: always
    job:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    prometheus:
      access: unrestricted
~~~

Đây là cấu hình **demo local**. Trong môi trường production:

- Không mở công khai `/actuator/prometheus` hoặc các endpoint quản trị nhạy cảm.
- Dùng authentication, network policy và quyền đọc phù hợp.
- H2 in-memory không phục vụ restart xuyên JVM; dùng database bền vững cho JobRepository cần phục hồi sau crash.
- Schema của bảng `BATCH_*` phải do cơ chế khởi tạo/migration phù hợp quản lý.
- Job được Boot auto-launch khi app bắt đầu vì `spring.batch.job.enabled=true`; demo chỉ có một Job. Production nên chủ động dùng scheduler/launcher với identifying JobParameters ổn định.

Lưu ý các thuộc tính Actuator thay đổi một phần giữa các bản Spring Boot 3.x. Nếu một bản Boot không hỗ trợ `management.endpoint.prometheus.access`, hãy dùng cấu hình endpoint tương ứng của đúng bản Boot. Quy tắc bảo vệ HTTP endpoint vẫn giữ nguyên.

## 6. Application và model

File `BatchObservabilityApplication.java`:

~~~java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchObservabilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            BatchObservabilityApplication.class, args);
    }
}
~~~

File `OrderRow.java`:

~~~java
package com.example.batch;

public class OrderRow {

    private final Long id;
    private final Long amount;

    public OrderRow(Long id, Long amount) {
        this.id = id;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public Long getAmount() {
        return amount;
    }
}
~~~

Chọn một JavaBean với getter để `JdbcBatchItemWriterBuilder.beanMapped()` có thể lấy giá trị các thuộc tính `id` và `amount`.

## 7. Listener ở cấp Job

File `JobMetricsListener.java`:

~~~java
package com.example.batch;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobMetricsListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobMetricsListener.class);

    private final MeterRegistry registry;

    public JobMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        log.info(
            "batch_job_started job={} executionId={}",
            execution.getJobInstance().getJobName(),
            execution.getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        String jobName = execution.getJobInstance().getJobName();
        String status = execution.getStatus().name();

        log.info(
            "batch_job_finished job={} executionId={} " +
            "batchStatus={} exitCode={}",
            jobName,
            execution.getId(),
            status,
            execution.getExitStatus().getExitCode());

        try {
            Counter.builder("app.batch.job.executions")
                    .description(
                        "Finished JobExecution callbacks observed")
                    .tag("job", jobName)
                    .tag("status", status)
                    .register(registry)
                    .increment();
        } catch (RuntimeException metricsError) {
            // Telemetry không nên khiến Job thất bại.
            log.warn(
                "Could not record job metric for job={}",
                jobName);
        }
    }
}
~~~

Điểm quan trọng:

- `afterJob` đếm **JobExecution được listener quan sát**, không đếm JobInstance. Một JobInstance có thể có nhiều JobExecution sau restart.
- `status` có tập giá trị hữu hạn như `COMPLETED`, `FAILED`, `STOPPED`, phù hợp làm metric tag.
- `executionId` chỉ nằm trong log để điều tra, **không** dùng làm Prometheus label vì cardinality tăng theo mỗi lần chạy.
- Listener được đăng ký khi tạo Job; chỉ đặt `@Component` không tự bảo đảm mọi Job đều gọi listener.
- Không log toàn bộ JobParameters, access token hoặc những exception message có thể chứa secret.

`try/catch` minh họa cách không để lỗi metric ghi đè outcome nghiệp vụ. Ở hệ thống có chính sách nghiêm ngặt, bạn có thể giám sát tình trạng lỗi exporter/registry riêng, nhưng không làm sai ý nghĩa trạng thái Job.

## 8. Listener ở cấp Step

File `StepMetricsListener.java`:

~~~java
package com.example.batch;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class StepMetricsListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepMetricsListener.class);

    private final MeterRegistry registry;

    public StepMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info(
            "batch_step_started step={} stepExecutionId={}",
            stepExecution.getStepName(),
            stepExecution.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        String job = execution.getJobExecution()
                .getJobInstance().getJobName();
        String step = execution.getStepName();

        log.info(
            "batch_step_finished job={} step={} status={} " +
            "read={} write={} filter={} skip={} " +
            "commit={} rollback={}",
            job, step, execution.getStatus(),
            execution.getReadCount(),
            execution.getWriteCount(),
            execution.getFilterCount(),
            execution.getSkipCount(),
            execution.getCommitCount(),
            execution.getRollbackCount());

        try {
            count(job, step, "read", execution.getReadCount());
            count(job, step, "write", execution.getWriteCount());
            count(job, step, "filter", execution.getFilterCount());
            count(job, step, "skip", execution.getSkipCount());
        } catch (RuntimeException metricsError) {
            log.warn(
                "Could not record step metrics job={} step={}",
                job, step);
        }

        // null có nghĩa không chỉnh sửa ExitStatus của Step.
        return null;
    }

    private void count(
            String job, String step, String operation, long amount) {
        Counter.builder("app.batch.step.items")
                .description("Item counts from completed StepExecutions")
                .tag("job", job)
                .tag("step", step)
                .tag("operation", operation)
                .register(registry)
                .increment(amount);
    }
}
~~~

Ở Spring Batch 5.2, `StepExecutionListener.afterStep` có return type `ExitStatus`. Trả `null` giúp giữ nguyên ExitStatus; nếu chủ đích sửa mã kết thúc, phải thực hiện rõ theo hợp đồng Job/flow, không dùng metric listener để vô tình thay đổi kết quả nghiệp vụ.

### Đọc các chỉ số StepExecution đúng ngữ nghĩa

| Giá trị | Ý nghĩa |
| --- | --- |
| `getReadCount()` | Số item reader đã đọc theo semantics Step. |
| `getWriteCount()` | Số item writer đã ghi theo semantics Step. |
| `getFilterCount()` | Số item được processor filter bằng cách trả `null`. |
| `getSkipCount()` | Tổng số item skip ở read/process/write theo policy. |
| `getCommitCount()` | Số commit mà StepExecution ghi nhận. |
| `getRollbackCount()` | Số rollback mà StepExecution ghi nhận. |

**Không đồng nhất `rollbackCount` với retry count**, và không coi `readCount` là số lần vật lý gọi `ItemReader.read()`. Khi có rollback/retry, một item có thể được đọc hoặc xử lý lại.

Counter trong ví dụ ghi nhận các count của mỗi StepExecution ở callback `afterStep`. Đây là số liệu tổng hợp **được quan sát**, không phải audit exactly-once bền vững qua JVM crash. Nếu process chết trước `afterStep`, metric có thể không được phát dù database đã commit một phần dữ liệu.

## 9. Listener ở cấp Chunk

File `ChunkMetricsListener.java`:

~~~java
package com.example.batch;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class ChunkMetricsListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkMetricsListener.class);

    private final MeterRegistry registry;

    public ChunkMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void afterChunk(ChunkContext context) {
        record(context, "success");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        record(context, "error");
    }

    private void record(ChunkContext context, String event) {
        String job = context.getStepContext()
                .getStepExecution()
                .getJobExecution()
                .getJobInstance()
                .getJobName();
        String step = context.getStepContext().getStepName();

        try {
            Counter.builder("app.batch.chunk.events")
                    .description("Chunk listener events")
                    .tag("job", job)
                    .tag("step", step)
                    .tag("event", event)
                    .register(registry)
                    .increment();
        } catch (RuntimeException metricsError) {
            log.warn(
                "Could not record chunk metric job={} step={}",
                job, step);
        }
    }
}
~~~

Trong Spring Batch 5.2, `afterChunk(ChunkContext)` được gọi sau chunk thành công, bên ngoài transaction, còn `afterChunkError(ChunkContext)` thông báo chunk gặp lỗi/rollback. Một lần `afterChunkError` **không nhất thiết khiến toàn Job FAILED**: framework có thể retry hoặc skip và tiếp tục.

Với fault-tolerant Step, callback chunk có thể xuất hiện ở các tình huống quét/chạy lại item sau lỗi writer. Vì thế metric này nên được định nghĩa là **số sự kiện callback quan sát được**, không phải số dòng đã commit hoặc số business transactions chính xác.

Chunk listener không nên ném exception. Logging tại mỗi chunk cũng có thể rất dày nếu chunk size nhỏ; ví dụ chỉ ghi metric, không ghi log success trên từng chunk.

## 10. Cấu hình Job, Step, reader, processor và writer

File `ImportJobConfiguration.java`:

~~~java
package com.example.batch;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ImportJobConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<OrderRow> ordersReader() {
        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("ordersReader")
                .resource(new ClassPathResource("orders.csv"))
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fields -> new OrderRow(
                        fields.readLong("id"),
                        fields.readLong("amount")))
                .build();
    }

    @Bean
    ItemProcessor<OrderRow, OrderRow> ordersProcessor() {
        return row -> row.getAmount() > 0 ? row : null;
    }

    @Bean
    JdbcBatchItemWriter<OrderRow> ordersWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderRow>()
                .dataSource(dataSource)
                .sql(
                    "INSERT INTO imported_orders(id, amount) " +
                    "VALUES (:id, :amount)")
                .beanMapped()
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<OrderRow> ordersReader,
            ItemProcessor<OrderRow, OrderRow> ordersProcessor,
            JdbcBatchItemWriter<OrderRow> ordersWriter,
            StepMetricsListener stepMetricsListener,
            ChunkMetricsListener chunkMetricsListener) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrderRow, OrderRow>chunk(2, transactionManager)
                .reader(ordersReader)
                .processor(ordersProcessor)
                .writer(ordersWriter)
                .listener(stepMetricsListener)
                .listener(chunkMetricsListener)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep,
            JobMetricsListener jobMetricsListener) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .listener(jobMetricsListener)
                .start(importOrdersStep)
                .build();
    }
}
~~~

### Giải thích các lựa chọn

- `@StepScope` cấp reader riêng theo StepExecution và cho phép reader có trạng thái restart phù hợp.
- `FlatFileItemReaderBuilder` đọc CSV theo tên cột; `linesToSkip(1)` bỏ header.
- Processor trả `null` cho amount bằng 0; đây là **filter**, không phải skip do exception.
- `JdbcBatchItemWriter` nhận `OrderRow` có getter và ghi những dòng hợp lệ.
- `chunk(2, transactionManager)` thiết lập ranh giới xử lý/transaction theo hai input item; chunk cuối có thể ít hơn.
- `.listener(stepMetricsListener)` và `.listener(chunkMetricsListener)` gắn callback cho Step.
- `.listener(jobMetricsListener)` gắn callback cho Job.
- Không tạo state metric trong `ExecutionContext`; metrics do Micrometer quản lý, còn repository lưu metadata/chế độ restart.

Đối với hệ thống thật, hãy đưa tên file, businessDate và output resource vào JobParameters hợp lệ hoặc cấu hình được kiểm soát. Không truyền raw secret qua JobParameters, và phải đảm bảo input snapshot không thay đổi giữa các lần restart.

## 11. Chạy ứng dụng và xem metric

Với ứng dụng demo có một Job và `spring.batch.job.enabled=true`, khởi động bằng:

~~~bash
./gradlew bootRun
~~~

Trên Windows, có thể dùng Gradle wrapper tương ứng (`gradlew.bat bootRun`). Ví dụ giả định Gradle plugin và Java toolchain đã được cấu hình đúng cho dự án.

Khi Boot auto-launch Job, CSV có sáu input item, Step hoàn thành và writer lưu bốn dòng vào H2. Logger thường sẽ ghi sự kiện bắt đầu/kết thúc của Job và Step; các giá trị ID cụ thể phụ thuộc database/sequence.

Vì demo có web starter và Actuator, có thể mở:

~~~text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/metrics
http://localhost:8080/actuator/prometheus
~~~

Trong môi trường production, không công khai endpoint quản trị hoặc Prometheus ra Internet. Một số endpoint cần bật exposure và đặt authentication/reverse proxy/network policy phù hợp.

### Kết quả Prometheus dự kiến

Tên Micrometer `app.batch.job.executions` thường được export theo dạng:

~~~text
app_batch_job_executions_total{
    job="importOrdersJob",
    status="COMPLETED"
} 1
~~~

Các event/item counts:

~~~text
app_batch_step_items_total{
    job="importOrdersJob",
    step="importOrdersStep",
    operation="read"
} 6

app_batch_step_items_total{
    job="importOrdersJob",
    step="importOrdersStep",
    operation="write"
} 4

app_batch_step_items_total{
    job="importOrdersJob",
    step="importOrdersStep",
    operation="filter"
} 2
~~~

Các đoạn trên mô tả **series kỳ vọng**, không phải stdout được ghi lại từ một lần chạy thực tế của dự án. Tên metric và việc export còn phụ thuộc version/configuration của Micrometer và backend.

### Có cần viết riêng duration timer?

Không nhất thiết. Spring Batch 5.2 đã có `spring.batch.job` và `spring.batch.step` dạng Timer. Nên dùng chúng cho latency chung; listener tự định nghĩa hữu ích hơn với các business/operational counts chưa có metric sẵn.

Nếu cần đo một tác vụ nghiệp vụ cụ thể bên trong ItemProcessor/Tasklet, bạn có thể dùng `Timer.Sample` hoặc `Timer.record` với tên metric **khác** và tag có cardinality thấp.

## 12. Query Prometheus và dashboard Grafana

Giả sử một ứng dụng nhiều lần chạy, các metric counter sẽ cộng dồn trong vòng đời registry. Có thể truy vấn:

**Số JobExecution hoàn thành trong giờ qua:**

~~~promql
sum by (job) (
  increase(
    app_batch_job_executions_total{status="COMPLETED"}[1h]
  )
)
~~~

**Số JobExecution thất bại trong một giờ:**

~~~promql
sum by (job) (
  increase(
    app_batch_job_executions_total{status="FAILED"}[1h]
  )
)
~~~

**Số item đã ghi trong 15 phút:**

~~~promql
sum by (job, step) (
  increase(
    app_batch_step_items_total{operation="write"}[15m]
  )
)
~~~

**Tốc độ lỗi chunk:**

~~~promql
sum by (job, step) (
  rate(
    app_batch_chunk_events_total{event="error"}[5m]
  )
)
~~~

**Tỉ trọng item bị filter trong một cửa sổ:**

~~~promql
sum by (job, step) (
  increase(
    app_batch_step_items_total{operation="filter"}[1h]
  )
)
/
clamp_min(
  sum by (job, step) (
    increase(
      app_batch_step_items_total{operation="read"}[1h]
    )
  ),
  1
)
~~~

Đây là tỉ trọng **theo số count được StepExecution tổng hợp trong khoảng quan sát**, không phải phần trăm callback processor filter trực tiếp theo thời gian thực. Với Job chỉ chạy mỗi đêm, cần chọn cửa sổ đủ rộng và tránh giải thích series bằng 0 khi Job không hoạt động.

Dashboard gợi ý:

| Ô | Nguồn | Câu hỏi |
| --- | --- | --- |
| Job completions/failures | Custom `app.batch.job.executions` | Lịch batch có thất bại không? |
| Job/Step duration | Built-in timers | Có chậm hơn bình thường không? |
| Read/write/filter | Custom `app.batch.step.items` | Có giảm throughput hoặc tăng filter? |
| Chunk error rate | Custom `app.batch.chunk.events` | Chunk có lỗi tăng đột biến không? |
| Job status gần nhất | JobRepository | Lần chạy cụ thể ở trạng thái gì? |
| Step read/write/skip counts theo execution | JDBC metadata | Một execution đã xử lý những gì? |
| Business totals | Database nghiệp vụ | Dữ liệu cuối có thực sự đúng không? |

Micrometer counter **không thay thế JobRepository**. Khi JVM restart, counter trong process có thể reset; Prometheus xử lý counter reset trong `rate`/`increase`. Nếu cần audit chính xác một JobInstance qua nhiều lần crash, phải dùng metadata/bảng audit bền vững phù hợp.

## 13. Integration test: vừa kiểm metric, vừa kiểm dữ liệu

Nếu test chỉ xác nhận Job `COMPLETED` hoặc metric `job.executions` tăng một đơn vị, vẫn có thể bỏ qua lỗi đọc/ghi dữ liệu. Vì vậy, bài test phải kiểm cả:

1. JobExecution `COMPLETED`.
2. StepExecution read = 6, write = 4, filter = 2, skip = 0.
3. Bảng `imported_orders` chứa đúng các ID `1,3,4,6` và tổng amount = 850.
4. Metric tùy chỉnh tăng tương ứng.

File `src/test/resources/application-test.yml`:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

Test tắt Boot auto-launch để tự khởi chạy Job bằng `JobLauncherTestUtils`. Trong ví dụ chỉ có một Job, nhưng ta vẫn set Job rõ ràng.

File `ImportJobIT.java`:

~~~java
package com.example.batch;

import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class ImportJobIT {

    @Autowired JobLauncherTestUtils launcher;
    @Autowired JobRepositoryTestUtils repositoryUtils;
    @Autowired JdbcTemplate jdbc;
    @Autowired MeterRegistry metrics;

    @Autowired
    @Qualifier("importOrdersJob")
    Job job;

    @BeforeEach
    void prepare() {
        launcher.setJob(job);

        // Chỉ thực hiện trên H2/test DB cô lập.
        repositoryUtils.removeJobExecutions();
        jdbc.update("DELETE FROM imported_orders");
    }

    @Test
    void recordsMetricsAndCorrectBusinessData() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("caseId", "case-725", true)
                .toJobParameters();

        JobExecution execution = launcher.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
                .filter(se -> "importOrdersStep".equals(
                        se.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(6, step.getReadCount());
        assertEquals(4, step.getWriteCount());
        assertEquals(2, step.getFilterCount());
        assertEquals(0, step.getSkipCount());

        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM imported_orders ORDER BY id",
                Long.class);
        assertEquals(List.of(1L, 3L, 4L, 6L), ids);

        Long amount = jdbc.queryForObject(
                "SELECT SUM(amount) FROM imported_orders",
                Long.class);
        assertEquals(850L, amount);

        assertEquals(1.0,
            metrics.get("app.batch.job.executions")
                .tags("job", "importOrdersJob",
                      "status", "COMPLETED")
                .counter().count(),
            0.001);

        assertEquals(6.0,
            metrics.get("app.batch.step.items")
                .tags("job", "importOrdersJob",
                      "step", "importOrdersStep",
                      "operation", "read")
                .counter().count(),
            0.001);

        assertEquals(4.0,
            metrics.get("app.batch.step.items")
                .tags("job", "importOrdersJob",
                      "step", "importOrdersStep",
                      "operation", "write")
                .counter().count(),
            0.001);

        assertEquals(2.0,
            metrics.get("app.batch.step.items")
                .tags("job", "importOrdersJob",
                      "step", "importOrdersStep",
                      "operation", "filter")
                .counter().count(),
            0.001);
    }
}
~~~

### Vì sao test này có giá trị?

- Nếu processor filter nhầm dòng hợp lệ, kết quả ID/amount hoặc read/write/filter count thay đổi và test thất bại.
- Nếu writer map sai giá trị, count có thể vẫn đúng nhưng SUM(amount) sai.
- Nếu listener không được gắn với Step hoặc Job, metric mong đợi không được tạo và test thất bại.
- Nếu Job không chạy, dữ liệu đích không thể thỏa các assertion.
- Nếu Job gặp exception, BatchStatus sẽ khác `COMPLETED`.

**Isolation của metric trong test:** ví dụ trên có một test đơn lẻ và Boot auto-launch được tắt. Trong một test suite có nhiều test dùng chung ApplicationContext/MeterRegistry, counter sẽ tích lũy. Khi đó nên đo **delta trước/sau**, dùng registry/test context riêng hoặc thiết kế mỗi test không phụ thuộc thứ tự. Không mặc định counter luôn bắt đầu từ 0.

Không xóa bảng `BATCH_*` trong production; `JobRepositoryTestUtils.removeJobExecutions()` chỉ dùng trong database test biệt lập. Khi kiểm restart, **không** xóa metadata giữa execution lỗi và execution phục hồi.

## 14. Khi listener và metric khác với số liệu metadata

Một câu hỏi thường gặp: “Vì sao số lần callback khác `COMMIT_COUNT` trong database?”

Lý do là chúng đo **các đối tượng khác nhau**:

- `app.batch.chunk.events{event="success"}` đếm callback `afterChunk` mà listener đã quan sát.
- `StepExecution.getCommitCount()` là counter transaction do framework lưu trong metadata, có thể bao gồm những điểm commit nội bộ tùy đường chạy.
- `StepExecution.getWriteCount()` là số item writer được ghi theo Step semantics, không nhất thiết là số JDBC statement gửi qua mạng.
- `ItemWriteListener` có thể được gọi lại sau retry/rollback, dù cuối cùng chỉ có một chunk commit.
- Một JobExecution có thể lỗi sau khi đã commit các chunk trước; listener cuối Job có thể không chạy nếu JVM bị kill cưỡng bức.

Vì vậy, khi thiết kế metric:

| Bạn muốn đo | Điểm instrumentation |
| --- | --- |
| Job hoàn tất/lỗi theo framework | JobExecutionListener sau Job hoặc truy vấn repository. |
| Read/write/filter/skip per StepExecution | StepExecutionListener sau Step. |
| Sự kiện callback chunk | ChunkListener. |
| Retry callback failures | RetryListener của retry subsystem, với tên metric mô tả rõ đơn vị. |
| HTTP requests vật lý | HTTP client instrumentation. |
| Dữ liệu business đã commit | Database/output audit và truy vấn nghiệp vụ. |
| Restart của một JobInstance | JobRepository và lịch sử JobExecution. |

Không ghép tất cả vào một biến tên `retryCount` hoặc `processedCount` nếu chúng có unit khác nhau.

## 15. Trường hợp lỗi: listener nào phát tín hiệu?

Giả sử processor ném exception không được cấu hình retry/skip:

~~~text
Input item #3
    |
    v
ItemProcessor throws
    |
    v
Chunk error / rollback
    |
    v
StepExecution FAILED
    |
    v
JobExecution FAILED
~~~

Trong tình huống này, bạn có thể quan sát:

- `ChunkListener.afterChunkError` được gọi khi chunk bị rollback và listener vẫn hoạt động.
- `StepExecutionListener.afterStep` nhìn thấy status FAILED, read/write/filter/skip counts theo Step.
- `JobExecutionListener.afterJob` đếm một JobExecution FAILED nếu framework thực hiện được callback.
- Built-in timers ghi nhận thời gian đã dùng nếu hệ thống observability hoạt động.

Tuy nhiên, **không được đảm bảo mọi callback đều chạy khi JVM chết đột ngột**. Metrics trong memory cũng có thể bị mất trước lần scrape Prometheus tiếp theo. Với phục hồi sự cố, JobRepository và dữ liệu nghiệp vụ là nguồn đối soát quan trọng hơn một số counter runtime.

### Có nên phát cảnh báo trực tiếp từ listener?

Có thể gửi một sự kiện/notification từ `afterJob` khi FAILED, nhưng không nên gọi API cảnh báo đồng bộ và để lỗi API này làm Job thất bại thêm. Ưu tiên listener phát log/metric, còn alert manager/Grafana/Prometheus dựa trên rule gửi cảnh báo.

Nếu nghiệp vụ đòi hỏi **audit chính xác, bền vững**, viết một bảng audit/outbox và kiểm transaction/retry riêng; không biến một Counter Micrometer thành nguồn duy nhất chứng minh một giao dịch đã diễn ra.

## 16. Tag, cardinality và dữ liệu nhạy cảm

Metric tag nên có số lượng giá trị hữu hạn:

~~~text
job=importOrdersJob
step=importOrdersStep
status=COMPLETED|FAILED|STOPPED
operation=read|write|filter|skip
event=success|error
environment=test|staging|production
~~~

Những giá trị **không nên** làm Prometheus labels:

~~~text
jobExecutionId=123456789
orderId=100012399
customerEmail=sample@example.org
fileName=/private/tenant/acme/2026-11-16/orders.csv
exceptionMessage=token=...
accessToken=...
~~~

Một label mới cho từng item/execution tạo cardinality quá cao, chiếm RAM và có thể làm lộ thông tin nhạy cảm. Đặt execution ID trong **structured logs** và dùng quyền/retention thích hợp; chỉ dùng tên Job/Step/status ổn định ở metrics.

Nếu muốn phân nhóm exception, dùng một allowlist như `transient_db`, `timeout`, `invalid_input`, `other` thay vì dùng full exception message hoặc path/file cụ thể làm tag.

### Log cũng cần kiểm soát

Ví dụ listener chỉ log:

~~~text
job=importOrdersJob
executionId=42
status=FAILED
exitCode=FAILED
```

Không log nguyên `JobParameters` nếu có khả năng chứa secret; tốt hơn nên thiết kế JobParameters **không chứa raw credential từ đầu**.

## 17. Monitoring đa luồng, partitioning và remote processing

Khi mở rộng batch:

- Nhiều StepExecution có thể cùng ghi metric của một tên Step; counter Micrometer là aggregate, không phải bảng chi tiết từng execution.
- Partitioning tạo các execution cấp worker khác nhau; nếu muốn tổng Job, cần tổng hợp các partition đúng ngữ nghĩa và tránh cộng trùng manager/worker.
- Remote chunking có process worker riêng; mỗi process có MeterRegistry riêng, cần thu thập và aggregate qua metrics backend.
- Listener ở thread worker có thể không có một số ThreadLocal context mà listener ở manager quen dùng.
- Timer/Counter runtime có thể reset khi Pod restart; dùng `rate`/`increase` với counter để quan sát.
- Không dùng biến `static int retryCount`/`processedCount` không đồng bộ làm metric tổng quan trong hệ thống đa luồng.

Một dashboard cần phân biệt **throughput toàn hệ thống** với từng JobInstance. Muốn xem chi tiết một instance cụ thể, dùng JobRepository và log/trace có execution ID, không tạo metric label theo mỗi ID.

## 18. Bổ sung metric cho lỗi nghiệp vụ

Có những dữ liệu **không thể suy ra chỉ từ read/writeCount**. Ví dụ processor loại record vì amount không hợp lệ:

~~~java
@Bean
ItemProcessor<OrderRow, OrderRow> ordersProcessor(
        MeterRegistry metrics) {

    return row -> {
        if (row.getAmount() <= 0) {
            Counter.builder("app.batch.orders.rejected")
                    .description("Orders rejected by validation rule")
                    .tag("reason", "non_positive_amount")
                    .register(metrics)
                    .increment();
            return null;
        }

        return row;
    };
}
~~~

Đây là ví dụ **thay thế** bean processor ở phần 10, không thêm một bean trùng tên trong cùng cấu hình. Nó giúp ghi nguyên nhân filter do nghiệp vụ, nhưng cần lưu ý:

- Callback processor có thể được gọi lại khi chunk rollback hoặc Step restart.
- Counter được tăng ngay trong processor **không rollback** cùng transaction JDBC.
- Vì vậy số counter này đếm **lần gọi processor phát hiện record không hợp lệ**, không bảo đảm có đúng một event cho mỗi business item.
- Nếu cần đếm từng item bị loại duy nhất, hãy ghi kết quả vào bảng quarantine/audit có business key và transaction/idempotency phù hợp.

Đặt tên metric theo đơn vị đếm thực sự và ghi chú semantics trong dashboard.

## 19. Spring Batch 6.x khác gì?

Các khái niệm JobExecutionListener, StepExecutionListener, ChunkListener và Micrometer vẫn có, nhưng API được tổ chức lại:

| Chủ đề | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Packages | Nhiều type nằm trong `org.springframework.batch.core` | Các type được tổ chức vào package con theo job/step; một số listener signature đổi. |
| Step chunk builder | `chunk(size, transactionManager)` | `chunk(size).transactionManager(transactionManager)` theo builder 6.x. |
| Testing utility | `JobLauncherTestUtils` | `JobOperatorTestUtils` |
| Built-in metrics | Thường hoạt động qua Micrometer global registry | Cần cấu hình `ObservationRegistry` để bật quan sát tích hợp theo tài liệu 6.x. |
| Custom metric | `MeterRegistry`/Micrometer | Vẫn có thể dùng `MeterRegistry`; xem API listener đúng bản 6.x. |

Trong Spring Batch 6.x, một cấu hình quan sát tích hợp có thể dùng `ObservationRegistry` và handler ghi vào MeterRegistry:

~~~java
@Bean
ObservationRegistry observationRegistry(MeterRegistry meterRegistry) {
    ObservationRegistry registry = ObservationRegistry.create();
    registry.observationConfig().observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
    return registry;
}
~~~

Các import tương ứng thuộc Micrometer Observation và Meter handler; kiểm dependency/version của dự án đang dùng. Không nhầm custom counters (được listener tự gọi MeterRegistry) với việc bật built-in Spring Batch observations.

**Lưu ý:** các chữ ký `ChunkListener` và builder ở 6.x không nhất thiết giống Spring Batch 5.2; hãy chuyển code theo Javadoc 6.x thay vì chỉ đổi version dependency.

## 20. Những sai lầm thường gặp

**Chỉ thêm `@Component` nhưng quên `.listener(...)`.** Listener không được gắn vào Job/Step cần theo dõi.

**Chỉ đọc BatchStatus.COMPLETED.** Không kiểm dữ liệu đầu ra và read/write/filter counts nên có thể bỏ sót lỗi nghiệp vụ.

**Tưởng `rollbackCount` là retry count.** Rollback, retry và skip là những khái niệm riêng.

**Ghi metric cho từng item kèm orderId label.** Tạo cardinality không kiểm soát.

**Đếm metric trong processor rồi coi là số item duy nhất đã commit.** Rollback/retry/restart có thể làm processor chạy lại.

**Ném exception vì không gọi được metrics backend.** Hệ thống quan sát không nên làm sai outcome nghiệp vụ.

**In toàn bộ JobParameters trong log.** Có thể lộ credential hoặc thông tin nhạy cảm.

**Đếm JobExecution như JobInstance.** Một instance có thể restart nhiều lần.

**Assert custom counter luôn bằng 1 trong test suite chung.** Registry tồn tại qua nhiều test; phải isolate hoặc tính delta.

**Chỉ kiểm metric mà không kiểm dữ liệu.** Metrics đã ghi có thể báo 4 writeCount nhưng amount vẫn sai.

**Đọc metric runtime thay cho JobRepository khi phục hồi sau crash.** Listener không luôn chạy nếu JVM chết đột ngột.

**Dùng API Spring Batch 6 với import của 5.2.** Builder/listener signatures và hạ tầng observability có thay đổi theo version.

## 21. Bài tập mở rộng

### Bài 1 — Theo dõi Step sai dữ liệu

Đổi processor cho lọc thêm item `id=3`, chạy lại integration test. Xác nhận test đỏ ở `writeCount` hoặc output IDs, dù Job vẫn `COMPLETED`.

### Bài 2 — Metric phân loại lỗi

Gây một exception không retryable ở processor. Bổ sung `ItemProcessListener` để đếm lỗi theo category được allowlist. Kiểm counter lỗi và JobStatus FAILED, nhưng tránh label theo item ID.

### Bài 3 — Retry và skip

Cấu hình fault-tolerant Step với `retryLimit` và `skipLimit` phù hợp, sau đó đo callback errors. Giải thích vì sao một item có thể phát nhiều error event nhưng chỉ bị skip một lần.

### Bài 4 — Duration timer

Sử dụng built-in `spring.batch.step` để so sánh thời gian chạy khi tăng số item hoặc giảm chunk size. Nếu tạo custom timer, đặt tên rõ và so sánh xem nó có đang đo trùng built-in timer không.

### Bài 5 — Prometheus và Grafana

Dựng một dashboard gồm Job completions/failures, thời lượng Step, read/write/filter throughput, chunk error rate và JobStatus gần nhất. Chọn cửa sổ thời gian phù hợp với lịch batch.

### Bài 6 — Restart

Cố ý cho JobExecution đầu FAILED sau một chunk commit, sau đó restart cùng JobInstance. Kiểm dữ liệu cuối không trùng và metric JobExecution tăng hai lần theo outcome; không kết luận có hai JobInstance.

### Bài 7 — Multi-thread và cardinality

Mở rộng Step sang partition hoặc worker song song. Bảo đảm tổng hợp metric đúng về mặt scope, không dùng ID từng item làm label và không dùng một biến mutable singleton để lưu trạng thái theo execution.

### Bài 8 — Observability failure

Giả lập lỗi khi custom metrics listener ghi metric. Kiểm rằng ứng dụng vẫn giữ outcome của Job và log lỗi telemetry ở mức phù hợp, không làm phát sinh side effect nghiệp vụ mới.

## 22. Tài liệu tham khảo chính thức

- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)
- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 5.2 — JobExecutionListener API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobExecutionListener.html)
- [Spring Batch 5.2 — StepExecutionListener API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecutionListener.html)
- [Spring Batch 5.2 — ChunkListener API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/ChunkListener.html)
- [Spring Batch 6 — Micrometer Support](https://docs.spring.io/spring-batch/reference/spring-batch-observability/micrometer.html)
- [Spring Batch 6 — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Prometheus — Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)

