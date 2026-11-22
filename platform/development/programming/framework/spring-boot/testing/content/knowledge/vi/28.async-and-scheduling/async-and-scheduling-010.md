# Kiểm thử Spring Batch job, step và tham số khi ứng dụng có sử dụng

## 1. Bài toán: Spring Batch không chỉ là gọi một hàm rồi assert

Khi một ứng dụng Spring Boot sử dụng **Spring Batch** để nhập dữ liệu, tổng hợp báo cáo, xuất tệp, đối soát hoặc chạy công việc theo lịch, việc test khác đáng kể so với một service method thông thường. Một `Job` có thể gồm nhiều `Step`, mỗi step có transaction riêng, mỗi lần chạy được ghi vào `JobRepository`, và việc chạy lại phụ thuộc **JobParameters**.

Các lỗi thực tế mà bộ test phải phát hiện gồm:

- Ứng dụng vừa khởi động để test thì Spring Boot đã **tự chạy job** trước khi test chuẩn bị dữ liệu.
- Test gọi một `Step` riêng nhưng vô tình chạy cả `Job`, gây các side effects không cần thiết.
- `@StepScope` cố đọc `jobParameters` khi application context chưa có `StepExecution`, gây lỗi SpEL/scope.
- Chạy lại job cùng tham số định danh sau khi đã `COMPLETED` thì nhận `JobInstanceAlreadyCompleteException`.
- Dùng timestamp/random parameter vô điều kiện khiến bài test không còn kiểm tra đúng cơ chế restart.
- Kiểm tra `BatchStatus.COMPLETED` mà bỏ qua output, `StepExecution`, read/write/skip counts hoặc dữ liệu nghiệp vụ.
- Job fail nhưng test chỉ assert không có exception; `JobLauncher` có thể trả `JobExecution` trạng thái `FAILED` thay vì ném chính lỗi trong step.
- Một `@Transactional` trên test method không tự rollback các transaction được batch step commit ở một thread/transaction boundary khác.
- Một test đọc trạng thái `STARTING` khi job launcher bất đồng bộ, rồi kết luận job thất bại.
- Nhiều tests tái sử dụng cùng metadata database, job name và identifying parameters, tạo kết quả phụ thuộc thứ tự.

Bài học trong nhóm **Bất đồng bộ và lịch chạy** này tập trung chính xác vào **“Kiểm thử Spring Batch job, step và tham số khi ứng dụng có sử dụng”**. Ta xây một project **Java 17+ / Spring Boot 3.3.5 / Spring Batch 5.1.x** với hai steps, tham số định danh `batchId`, tham số không định danh `attempt`, `@StepScope`, H2 JobRepository và test bằng `@SpringBatchTest`.

**Phạm vi điều kiện:** chỉ dùng các kỹ thuật bên dưới khi ứng dụng thật sự có Spring Batch. Nếu project chỉ dùng `@Async`, `@Scheduled` hoặc một thread executor mà không có Job/Step của Batch thì không cần thêm `spring-batch-test` chỉ để thử lịch chạy.

### Kết quả học tập

1. Hiểu `Job`, `JobInstance`, `JobExecution`, `Step`, `StepExecution`, `JobParameters`, `ExecutionContext`, `BatchStatus` và `ExitStatus`.
2. Tắt auto-launch khi test bằng `spring.batch.job.enabled=false`, không vô tình chuyển mọi lần chạy test thành một batch run.
3. Khai báo job/step kiểu Spring Batch 5 với `new JobBuilder(name, jobRepository)` và `new StepBuilder(name, jobRepository)`, kèm `PlatformTransactionManager` cho tasklet.
4. Dùng `@SpringBatchTest`, `JobLauncherTestUtils.launchJob(params)` và `launchStep(name, params)`.
5. Kiểm tra toàn bộ flow, chạy riêng step, các tham số bắt buộc/định danh, step scope late binding và trạng thái thực thi.
6. Xác định đúng sự khác nhau giữa việc job trả `FAILED` và trường hợp job launcher ném exception.
7. Tránh nhầm `launchStep` là full job, tránh tin metadata rollback nếu step đã commit side effect.
8. Biết khi nào cần `JobRepositoryTestUtils`, `StepScopeTestUtils` hoặc test mức chunk/item reader/writer.
9. Phân biệt test job business logic với test scheduler và real asynchronous launcher.

## 2. Mô hình thực thi: Job → Instance → Execution → StepExecution

```text
Job: exportReportJob (định nghĩa cố định)
   |
   +-- JobInstance A
   |     identifying JobParameters: batchId = "BATCH-A"
   |        |
   |        +-- JobExecution #1 (COMPLETED hoặc FAILED)
   |        |      |
   |        |      +-- StepExecution collectStep
   |        |      +-- StepExecution publishStep
   |        |
   |        +-- JobExecution #2 (chỉ khi restart hợp lệ)
   |
   +-- JobInstance B
         identifying JobParameters: batchId = "BATCH-B"
            |
            +-- JobExecution #3
                   |
                   +-- StepExecution collectStep
                   +-- StepExecution publishStep
```

- **`Job`** là định nghĩa flow, ví dụ `exportReportJob` gồm `collectStep` rồi `publishStep`.
- **`JobInstance`** được nhận diện bằng **job name + tập JobParameters có `identifying=true`**. Đây là danh tính một lần xử lý logic, không đơn giản là mỗi lần bấm nút chạy.
- **`JobExecution`** là một lần cố gắng thực thi một instance; một JobInstance có thể có nhiều executions khi restart sau khi failed/stopped.
- **`Step`** là định nghĩa một pha xử lý.
- **`StepExecution`** lưu kết quả của một step trong một lần chạy, gồm status, exit status, counters, execution context và timestamps.
- **`JobParameters`** là tập tham số typed có flag identifying.
- **`ExecutionContext`** là state có thể checkpoint/khôi phục trong batch metadata; có job-level và step-level contexts.
- **`BatchStatus`** phản ánh trạng thái lifecycle: `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`...
- **`ExitStatus`** là mã kết quả phục vụ điều khiển transition/flow: `COMPLETED`, `FAILED`, mã tùy biến hoặc description.

### Ví dụ cùng instance và khác instance

```java
JobParameters first = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-01", true)
        .addLong("attempt", 1L, false)
        .toJobParameters();

JobParameters retryMetadataChanged = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-01", true)
        .addLong("attempt", 2L, false)
        .toJobParameters();

JobParameters anotherInstance = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-02", true)
        .addLong("attempt", 1L, false)
        .toJobParameters();
```

Đây là **snippet**, dùng imports `org.springframework.batch.core.JobParameters` và `JobParametersBuilder`; code project đầy đủ ở các mục sau. Hai đối tượng đầu có **cùng identifying set** nên nhận diện cùng một JobInstance dù giá trị `attempt` đổi. Đối tượng thứ ba có batchId mới nên tạo JobInstance khác.

**Lưu ý:** thêm một tham số `run.id`/timestamp với `identifying=true` vào mỗi lần launch **luôn tạo instance mới**; điều đó hữu ích khi muốn chạy lần mới, nhưng sẽ che hành vi restart nếu test cần chạy lại cùng một instance.

## 3. Chọn mức kiểm thử cho đúng trách nhiệm

| Mức test | Chạy gì? | Công cụ/khẳng định cần có |
| --- | --- | --- |
| Unit test business rule | Service hoặc processor không cần Spring Batch | JUnit + Mockito, không cần context Batch |
| Reader/processor/writer riêng | Một component, có thể cần step scope | Spring test + `StepScopeTestUtils`, test fixtures |
| **Một Step** | Chỉ một step có JobRepository metadata | `JobLauncherTestUtils.launchStep(...)`; assert StepExecution + side effect |
| **Cả Job** | Flow qua mọi step, flow transition, job parameters | `launchJob(...)`; assert JobExecution/step statuses và business output |
| Restart test | Same JobInstance sau failure, step skip/retry | JobRepository trên DB test + controlled failure |
| Full integration | Batch job cùng DB/file/API/message infrastructure | `@SpringBootTest` + DB/Testcontainers/file fixtures |
| Scheduler integration | Ai khởi động job và khi nào | Test `@Scheduled`/Quartz/controller riêng, mock job launcher khi cần |
| Performance/volume | Chunk size, commits, throughput, memory | Test data lớn và metrics; không thay unit tests |

Một chiến lược cân bằng thường là có nhiều unit tests rẻ cho processor/validation, một vài step tests cho I/O và một số job-level tests kiểm tra flow. Không cần `@SpringBootTest` với một H2 database cho mọi phép cộng/trừ trong ItemProcessor.

## 4. Những annotation và API cốt lõi

```java
@SpringBootTest
@SpringBatchTest
@ActiveProfiles("test")
class ExportBatchJobTest {
    @Autowired JobLauncherTestUtils jobs;
}
```

Đây là **snippet cấu trúc**, ví dụ đầy đủ ở mục 13.

- `@SpringBootTest` tải Boot application context chứa job, steps, repository và dependencies.
- `@SpringBatchTest` từ `spring-batch-test` đăng ký `JobLauncherTestUtils`, `JobRepositoryTestUtils` và listeners hỗ trợ step/job scope.
- `JobLauncherTestUtils.launchJob(parameters)` chạy toàn job.
- `JobLauncherTestUtils.launchStep(stepName, parameters)` chạy **chỉ một step** trong một surrogate single-step job do test utility tạo.
- `JobRepositoryTestUtils.removeJobExecutions()` dọn **Spring Batch metadata executions/instances** trong DB test khi cần; không dọn business table hoặc file/message side effects.
- `StepScopeTestUtils.doInStepScope(...)` giúp kích hoạt step context trong unit test một component cần late binding.

Tài liệu Spring Batch 5.1 quy định nếu có **một** `Job` trong context, `JobLauncherTestUtils` có thể nhận đúng job tự động; nếu có nhiều jobs, cần chọn rõ job under test, không phụ thuộc bean ambiguity.

## 5. Spring Boot auto-configuration và điểm dễ hỏng test

Với `spring-boot-starter-batch`, Spring Boot có thể cấu hình JDBC-backed `JobRepository`, `JobLauncher`, batch scopes và các beans cần thiết.

**Mặc định, nếu có một Job bean, Boot thường tự chạy job lúc startup.** Điều này hợp lý với command-line batch app nhưng không phù hợp khi integration test phải chuẩn bị fixture/job parameters trước.

Trong test profile đặt:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
```

- `spring.batch.job.enabled=false` tắt **Boot startup job runner**; không ngăn test chủ động gọi `launchJob` hay scheduler/service khác tự gọi JobLauncher.
- `spring.batch.jdbc.initialize-schema=always` yêu cầu Boot khởi tạo các bảng **BATCH_JOB_INSTANCE**, **BATCH_JOB_EXECUTION**, **BATCH_STEP_EXECUTION**... từ scripts Spring Batch trên H2 test database.
- Metadata schema khác business schema; có batch metadata không có nghĩa application data table đã được tạo.
- H2 là DB test; production dùng PostgreSQL/MySQL/... thường cần migration để quản lý schema chính thức và batch metadata tương thích vendor.

### Có nên thêm @EnableBatchProcessing?

**Không thêm `@EnableBatchProcessing` vào project ví dụ.** Trong Spring Boot 3.3, việc tự bật `@EnableBatchProcessing` hoặc extend `DefaultBatchConfiguration` có thể khiến Boot Batch auto-configuration **back off**, kéo theo thay đổi cách tự cấu hình JobRepository/khởi tạo JDBC schema. Chỉ dùng khi bạn thật sự muốn tự sở hữu toàn bộ Batch infrastructure và biết cần tạo những beans nào.

Cũng tránh áp dụng tutorial rất cũ dùng `JobBuilderFactory`, `StepBuilderFactory` mà không đối chiếu Spring Batch 5.1. Ví dụ bên dưới dùng constructors nhận `JobRepository` và `PlatformTransactionManager` hiện đại.

## 6. Project mẫu chạy được với Java 17+

Để tập trung vào Job/Step/Parameters, ta dùng **hai TaskletStep** thay vì tạo một job CSV/DB phức tạp. Một `JobProbe` thread-safe ghi lại thứ tự các bước **chỉ phục vụ quan sát trong test/demo**; Spring Batch metadata được lưu thật vào H2. Việc ghi lên `JobProbe` **không transactional**, nên đây không phải production transactional business writer.

Cấu trúc project:

```text
batch-job-testing-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/batch/
│   ├── BatchLabApplication.java
│   ├── JobProbe.java
│   ├── CollectTasklet.java
│   ├── PublishTasklet.java
│   └── ExportJobConfiguration.java
└── src/test/
    ├── java/com/example/batch/
    │   └── ExportBatchJobTest.java
    └── resources/
        └── application-test.yml
```

Project dùng `spring-boot-starter-batch`, `spring-batch-test` và H2; không có REST controller, Docker, external broker hoặc file input. Tên package/file được sử dụng nhất quán xuyên suốt.

### 6.1. settings.gradle

```groovy
rootProject.name = 'batch-job-testing-lab'
```

### 6.2. build.gradle

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
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Giải thích:**

- `spring-boot-starter-batch`: Spring Batch runtime, Boot autoconfiguration, JDBC infrastructure.
- `com.h2database:h2`: in-memory JDBC database chứa Spring Batch metadata; `runtimeOnly` đủ cho Boot test/runtime.
- `spring-boot-starter-test`: JUnit Jupiter và Spring TestContext.
- `spring-batch-test`: `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, `StepScopeTestUtils`.
- `junit-platform-launcher`: hỗ trợ môi trường Gradle dùng JUnit Platform.

**Nếu dự án chưa có Gradle Wrapper**, lệnh `./gradlew` sẽ không tồn tại. Dùng Gradle tương thích đã cài bằng `gradle test` hoặc tạo wrapper theo quy trình nhóm trước khi chạy các lệnh minh họa.

## 7. Boot application root

`src/main/java/com/example/batch/BatchLabApplication.java`:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchLabApplication.class, args);
    }
}
```

`@SpringBootApplication` đặt tại package cha để component scan tìm `JobProbe`, hai Tasklet classes và `ExportJobConfiguration`. Không có `@EnableBatchProcessing`: để Boot 3.3 tự cấu hình Batch infrastructure.

Khi chạy ứng dụng ngoài tests, bạn cần cung cấp DataSource, batch schema và job parameters phù hợp. Trong ví dụ này **chỉ bảo đảm kịch bản test profile với H2**; không tuyên bố `bootRun` không cấu hình là một production batch deployment hợp lệ.

## 8. JobProbe: ghi nhận step nào đã chạy

`src/main/java/com/example/batch/JobProbe.java`:

```java
package com.example.batch;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class JobProbe {

    private final Map<String, List<String>> stages =
            new ConcurrentHashMap<>();

    public void record(String batchId, String stage) {
        stages.computeIfAbsent(
                batchId,
                key -> new CopyOnWriteArrayList<>()
        ).add(stage);
    }

    public List<String> stagesFor(String batchId) {
        List<String> stored = stages.get(batchId);
        return stored == null ? List.of() : List.copyOf(stored);
    }

    public void clear() {
        stages.clear();
    }
}
```

Đây là một simple **in-memory observation probe**, không phải database transaction resource, production file writer hoặc message publisher. Nó giúp tests chứng minh:

- Chạy **cả Job** → quan sát hai stages theo thứ tự `collect` rồi `publish`.
- Chạy riêng `collectStep` → chỉ có stage `collect`.
- Chạy riêng `publishStep` → chỉ có stage `publish`.
- Khi `batchId` khác, các kết quả được cô lập theo key.

`ConcurrentHashMap` và `CopyOnWriteArrayList` giúp recorder tránh những data races đơn giản khi các components có thể chạy khác thread. Nhưng `probe.clear()` trong test vẫn giả định test methods không chạy parallel trên cùng context; nếu bật JUnit parallel, phải thiết kế isolate theo mỗi test/job ID hoặc tách application context.

**Cảnh báo quan trọng:** Tasklet có thể ghi vào `JobProbe` rồi fail; transaction rollback của Spring Batch không undo `CopyOnWriteArrayList.add`. Vì vậy không dùng probe làm bằng chứng database rollback hay exactly-once behavior. Với production, đo side effect thật (JDBC, S3, Kafka...) trong tests tương ứng.

## 9. CollectTasklet: @StepScope đọc JobParameters lúc step chạy

`src/main/java/com/example/batch/CollectTasklet.java`:

```java
package com.example.batch;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class CollectTasklet implements Tasklet {

    private final String batchId;
    private final JobProbe probe;

    public CollectTasklet(
            @Value("#{jobParameters['batchId']}") String batchId,
            JobProbe probe) {
        this.batchId = batchId;
        this.probe = probe;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException(
                    "batchId is required");
        }

        probe.record(batchId, "collect");

        contribution.getStepExecution()
                .getExecutionContext()
                .putString("observedBatchId", batchId);

        return RepeatStatus.FINISHED;
    }
}
```

### Giải thích sâu

`@StepScope` làm bean được tạo theo lifecycle của **StepExecution** thay vì khi application context startup. Nhờ vậy Spring Expression Language có thể đọc `jobParameters['batchId']` khi job thực sự chạy.

Nếu bỏ `@StepScope` và vẫn inject `@Value("#{jobParameters['batchId']}")` vào singleton, Spring chưa có `StepContext` tại lúc khởi tạo bean và thường báo lỗi scope/expression. **Step chính nó không cần và không nên được đánh dấu `@StepScope`** cho ví dụ này; component phụ thuộc parameter mới cần scope.

`RepeatStatus.FINISHED` báo với `TaskletStep` rằng Tasklet xong và không cần gọi tiếp. Nếu trả `CONTINUABLE` mà không có termination condition, step có thể lặp nhiều lần.

`StepExecution.getExecutionContext().putString(...)` lưu giá trị quan sát của parameter trong **step execution context**. Test không chỉ kiểm tra probe stage mà còn xác nhận **late-bound parameter** đã tới đúng step. Khi context được persist, nó thuộc Spring Batch metadata; với job thật cần chọn giá trị serializable và checkpoint strategy hợp lệ.

### Phân biệt jobParameters và application.properties

`batchId` là **tham số mỗi lần chạy job** (JobParameters), không phải một property như `app.batch.batch-id` từ Spring Environment. Hệ thống thật có thể cấu hình datasource/feature flags qua application config, còn input cụ thể của một run nên được truyền qua JobParameters và kiểm tra identifying/nonidentifying policy.

## 10. PublishTasklet: đọc parameter qua StepExecution

`src/main/java/com/example/batch/PublishTasklet.java`:

```java
package com.example.batch;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.stereotype.Component;

@Component
public class PublishTasklet implements Tasklet {

    private final JobProbe probe;

    public PublishTasklet(JobProbe probe) {
        this.probe = probe;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String batchId = contribution
                .getStepExecution()
                .getJobExecution()
                .getJobParameters()
                .getString("batchId");

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException(
                    "batchId is required");
        }

        probe.record(batchId, "publish");
        return RepeatStatus.FINISHED;
    }
}
```

`PublishTasklet` không cần `@StepScope`: nó không yêu cầu constructor-time late binding. Khi step chạy, `StepContribution` có `StepExecution` và job parameters của execution hiện tại. Hai cách này đều hợp lệ, giúp thấy khi nào thật sự cần scoped component.

Không đặt `@JobScope` trên mọi bean chỉ vì class có chữ “job” trong tên. Chỉ dùng job scope khi muốn một instance per job execution và cần context late binding ở mức đó; đặc biệt cẩn thận khi job chạy multi-thread/partitioned.

## 11. Job và Step definitions kiểu Spring Batch 5

`src/main/java/com/example/batch/ExportJobConfiguration.java`:

```java
package com.example.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ExportJobConfiguration {

    @Bean("collectStep")
    Step collectStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            CollectTasklet tasklet) {

        return new StepBuilder("collectStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean("publishStep")
    Step publishStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            PublishTasklet tasklet) {

        return new StepBuilder("publishStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean("exportReportJob")
    Job exportReportJob(
            JobRepository jobRepository,
            @Qualifier("collectStep") Step collectStep,
            @Qualifier("publishStep") Step publishStep) {

        return new JobBuilder("exportReportJob", jobRepository)
                .validator(parameters -> {
                    String batchId =
                            parameters.getString("batchId");

                    if (batchId == null || batchId.isBlank()) {
                        throw new JobParametersInvalidException(
                                "batchId is required");
                    }
                })
                .start(collectStep)
                .next(publishStep)
                .build();
    }
}
```

### Quan trọng về syntax và bean wiring

- `JobBuilder("exportReportJob", jobRepository)` và `StepBuilder("collectStep", jobRepository)` là kiểu API Spring Batch **5.1**.
- `.tasklet(tasklet, transactionManager)` cung cấp transaction manager cho `TaskletStep`.
- `.start(collectStep).next(publishStep)` là flow tuần tự; nếu `collectStep` fail và không có transition đặc biệt, job thường không chạy `publishStep`.
- `.validator(...)` gắn **JobParametersValidator ở cấp Job**: yêu cầu `batchId` khác null/rỗng trước full job launch.
- `@Qualifier` bảo đảm job dùng đúng Step beans, không phụ thuộc thứ tự autowire khi có hai beans type `Step`.
- `@Configuration(proxyBeanMethods=false)` phù hợp vì config không tự gọi trực tiếp những `@Bean` methods khác.
- Chỉ **một Job bean** được khai báo, giúp `JobLauncherTestUtils` nhận job cần kiểm tra qua Spring Batch test autowiring.

**Lưu ý:** `launchStep(...)` tạo một **surrogate test job**, không chạy Job-level validator của `exportReportJob` theo cách full job chạy. Vì thế cả hai Tasklets cũng tự kiểm tra `batchId` trước side effects. Đừng tin rằng test `launchStep` đã chứng minh JobParametersValidator của full job.

### Tasklet và transaction boundary

Spring Batch `TaskletStep` gọi `Tasklet.execute(...)` trong transaction do step quản lý. Với JDBC business writes, DB transaction có thể rollback nếu lỗi xảy ra trước commit và DataSource/transaction manager được cấu hình đúng. Nhưng `JobProbe`, file I/O, external APIs và message publish **không tự được rollback** bởi JDBC transaction.

Nếu ứng dụng thật có hai DataSources (JobRepository metadata và business database), phải xác định `@BatchDataSource`, `@BatchTransactionManager` hoặc wiring tương đương; không mặc định repository transaction bao trùm business DB.

## 12. Cấu hình H2 chỉ dành cho test

`src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_lab;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
```

Đặt `@ActiveProfiles("test")` trên test class để file được tải.

### Tại sao chọn named in-memory DB?

`jdbc:h2:mem:batch_lab;DB_CLOSE_DELAY=-1` giữ database H2 trong cùng JVM khi connection đóng/mở lại, giúp JobRepository metadata tồn tại qua nhiều repository calls trong test context. Không chia sẻ H2 này với ứng dụng thật; production phải dùng datasource/migration phù hợp.

### Các bảng metadata thường gặp

```text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_STEP_EXECUTION
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION_CONTEXT
BATCH_JOB_SEQ
BATCH_JOB_EXECUTION_SEQ
BATCH_STEP_EXECUTION_SEQ
```

Tên/schema chính xác phụ thuộc vendor và Spring Batch version; mục đích ở đây là thấy **JobRepository lưu lịch sử**. Không tự sửa metadata trực tiếp để ép một JobInstance restart; dùng JobRepository/JobOperator APIs và migration policy của hệ thống thật.

### Vì sao không cho job tự chạy khi context load?

Với `spring.batch.job.enabled=false`, Boot không chạy `exportReportJob` thông qua startup runner; tests sẽ chủ động gọi `launchJob(params)`. Nếu quên flag, application startup có thể cố chạy job **không có batchId**, bị JobParametersValidator từ chối, khiến test context fail trước khi test method chạy.

**Không lạm dụng `@EnableBatchProcessing` để “sửa” vấn đề auto-launch**: nó thay đổi phạm vi auto-config; một property `spring.batch.job.enabled=false` mới là cơ chế thích hợp ở ví dụ này.

## 13. Test class runnable: @SpringBatchTest và JobLauncherTestUtils

`src/test/java/com/example/batch/ExportBatchJobTest.java`:

```java
package com.example.batch;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@SpringBatchTest
@ActiveProfiles("test")
class ExportBatchJobTest {

    @Autowired
    JobLauncherTestUtils jobs;

    @Autowired
    JobProbe probe;

    @BeforeEach
    void resetProbe() {
        probe.clear();
    }

    private JobParameters params(String batchId, long attempt) {
        return new JobParametersBuilder()
                .addString("batchId", batchId, true)
                .addLong("attempt", attempt, false)
                .toJobParameters();
    }

    private String freshBatchId(String suffix) {
        return suffix + "-" + UUID.randomUUID();
    }

    @Test
    void wholeJobRunsBothStepsInOrder() throws Exception {
        String id = freshBatchId("whole");

        JobExecution execution =
                jobs.launchJob(params(id, 1L));

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
        assertEquals(ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
        assertEquals("exportReportJob",
                execution.getJobInstance().getJobName());
        assertEquals(id,
                execution.getJobParameters().getString("batchId"));

        Set<String> stepNames = execution.getStepExecutions()
                .stream()
                .map(StepExecution::getStepName)
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("collectStep", "publishStep"),
                stepNames);

        assertTrue(execution.getStepExecutions().stream()
                .allMatch(step ->
                        step.getStatus() == BatchStatus.COMPLETED));

        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(id));
    }

    @Test
    void launchCollectStepDoesNotRunPublishStep()
            throws Exception {
        String id = freshBatchId("collect-only");

        JobExecution execution =
                jobs.launchStep("collectStep", params(id, 1L));

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
        assertEquals(1, execution.getStepExecutions().size());
        assertEquals(
                "collectStep",
                execution.getStepExecutions().iterator()
                        .next().getStepName());
        assertEquals(
                List.of("collect"),
                probe.stagesFor(id));
    }

    @Test
    void launchPublishStepDoesNotRunCollectStep()
            throws Exception {
        String id = freshBatchId("publish-only");

        JobExecution execution =
                jobs.launchStep("publishStep", params(id, 1L));

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
        assertEquals(1, execution.getStepExecutions().size());
        assertEquals(
                "publishStep",
                execution.getStepExecutions().iterator()
                        .next().getStepName());
        assertEquals(
                List.of("publish"),
                probe.stagesFor(id));
    }

    @Test
    void stepScopeReadsTheCurrentJobParameter()
            throws Exception {
        String id = freshBatchId("scoped");

        JobExecution execution =
                jobs.launchStep("collectStep", params(id, 1L));

        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(
                id,
                step.getExecutionContext()
                        .getString("observedBatchId"));
        assertEquals(
                List.of("collect"),
                probe.stagesFor(id));
    }

    @Test
    void completedInstanceRejectsRerunWithOnlyNoteChanged()
            throws Exception {
        String id = freshBatchId("same-instance");

        JobExecution first = jobs.launchJob(params(id, 1L));
        assertEquals(BatchStatus.COMPLETED, first.getStatus());

        assertThrows(
                JobInstanceAlreadyCompleteException.class,
                () -> jobs.launchJob(params(id, 2L)));

        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(id));
    }

    @Test
    void changedIdentifyingBatchIdCreatesNewInstance()
            throws Exception {
        String firstId = freshBatchId("run-A");
        String secondId = freshBatchId("run-B");

        JobExecution first =
                jobs.launchJob(params(firstId, 1L));
        JobExecution second =
                jobs.launchJob(params(secondId, 1L));

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertNotEquals(
                first.getJobInstance().getInstanceId(),
                second.getJobInstance().getInstanceId());
        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(firstId));
        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(secondId));
    }

    @Test
    void jobValidatorRejectsMissingBatchId() {
        JobParameters missing = new JobParametersBuilder()
                .addLong("attempt", 1L, false)
                .toJobParameters();

        assertThrows(
                JobParametersInvalidException.class,
                () -> jobs.launchJob(missing));
    }

    @Test
    void launchStepRejectsUnknownStepName() {
        String id = freshBatchId("unknown-step");

        assertThrows(
                IllegalStateException.class,
                () -> jobs.launchStep(
                        "noSuchStep", params(id, 1L)));
    }

    @Test
    void parametersExposeTheirIdentifyingFlags() {
        JobParameters parameters =
                params("fixed-business-key", 77L);

        assertTrue(
                parameters.getParameters().get("batchId")
                        .isIdentifying());
        assertFalse(
                parameters.getParameters().get("attempt")
                        .isIdentifying());
        assertEquals(
                "fixed-business-key",
                parameters.getString("batchId"));
        assertEquals(
                77L,
                parameters.getLong("attempt"));
    }
}
```

**Bộ mã ở class này có 9 phương thức `@Test`.** `@BeforeEach` là setup, không được tính là test. Dùng `UUID` làm phần suffix **chỉ để các JobInstances của test không trùng** khi chia sẻ H2 metadata, chứ không dùng random data cho expected business outcomes.

Để nhắc lại giới hạn: các method trên là code mẫu **được thiết kế để chạy** với đúng dependencies/config; chưa có Gradle execution report thực tế trong bài học. Khi thực hành phải chạy bộ tests và đối chiếu kết quả, không suy “9 PASS” chỉ vì source có 9 annotations.

## 14. Đọc kết quả test job đúng cách

Test `wholeJobRunsBothStepsInOrder` khẳng định **bốn lớp kết quả**:

1. **Lifecycle status**: `JobExecution.getStatus() == BatchStatus.COMPLETED`.
2. **Exit code**: `getExitStatus().getExitCode()` là `COMPLETED`.
3. **Flow structure**: hai `StepExecution` có names `collectStep` và `publishStep`, đều completed.
4. **Outcome**: probe quan sát đúng thứ tự `collect` → `publish` cho batchId hiện tại.

Chỉ gọi:

```java
assertEquals(BatchStatus.COMPLETED, execution.getStatus());
```

là cần nhưng chưa đủ. Ví dụ một Tasklet có thể return FINISHED mà không ghi file/DB row nào; nếu behavior nghiệp vụ yêu cầu output, test phải assert output đó. Bài mẫu dùng `JobProbe` để minh họa điều này, không thay thế kiểm tra business tables/CSV/S3 trong project thật.

### StepExecution và read/write counts

`StepExecution` cung cấp các counters `getReadCount()`, `getWriteCount()`, `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`, `getCommitCount()` và `getRollbackCount()`, tùy kiểu step.

**Với TaskletStep demo không dùng chunk reader/writer**, đừng assert `readCount=10` hay `writeCount=10` vì không có item-level processing. Với chunk-oriented job, các counters rất hữu ích, ví dụ:

```java
StepExecution step = execution.getStepExecutions()
        .stream()
        .filter(s -> "importCsvStep".equals(s.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(10, step.getReadCount());
assertEquals(9, step.getWriteCount());
assertEquals(1, step.getProcessSkipCount());
```

Đây là **snippet cho một job chunk khác**, không thuộc runnable demo. Nó chỉ đúng nếu job fixture thật có 10 rows đầu vào, một item bị skip và chín items được ghi, cùng skip policy tương ứng. Không bịa các counters trong output của Tasklet demo.

## 15. launchJob và launchStep không giống nhau

| API | Job đang thực thi | Số steps | Job-level validator/flow? |
| --- | --- | --- | --- |
| `jobs.launchJob(params)` | `exportReportJob` thật | Collect rồi Publish | **Có** |
| `jobs.launchStep("collectStep", params)` | Single-step **surrogate job** của Spring Batch test utility | Chỉ Collect | **Không chạy toàn bộ job validator/flow** |
| `jobs.launchStep("publishStep", params)` | Single-step surrogate job | Chỉ Publish | Không chạy Collect |
| `jobs.launchStep("missing", params)` | Không tìm được step | Không chạy | Báo `IllegalStateException` |

Trong job demo, `PublishTasklet` không phụ thuộc output của Collect; do đó ta có thể chạy riêng `publishStep`. Trong ứng dụng thực, nếu Publish cần `jobExecutionContext` do Collect tạo, test step riêng phải **setup context** thích hợp bằng `launchStep(stepName, params, jobExecutionContext)` hoặc test dependency ở mức full job. Đừng chạy một step standalone rồi assert theo precondition chỉ được tạo bởi step trước mà không mô phỏng nó.

**Cảnh báo về metadata:** khi dùng `launchStep`, `execution.getJobInstance().getJobName()` có thể là tên job tạm do `StepRunner` tạo, **không phải `exportReportJob`**. Test runnable chỉ assert step names và behavior, không assert tên full job trong step-only test.

### Chọn lệnh đúng trong từng tình huống

- Flow transition, validator, order giữa nhiều steps → `launchJob`.
- Input/processing/output của một step có thể chuẩn bị độc lập → `launchStep`.
- Custom step-scoped bean/reader không muốn mở JobRepository → `StepScopeTestUtils` hoặc test fixture scope.
- Scheduler khi nào kích hoạt job → test scheduler logic riêng, không cố dùng `launchJob` làm phép đo thời gian.

## 16. @StepScope, JobParameters và late binding

Spring Batch sẽ chưa biết `batchId` tại application context startup. Vì thế constructor injection:

```java
@Value("#{jobParameters['batchId']}")
String batchId
```

chỉ có nghĩa khi bean ở `@StepScope` (hoặc job scope phù hợp) và một StepExecution đang active.

### Vì sao @StepScope không nên đặt lên Step bean?

`Step` là cấu trúc định nghĩa luồng và được Job graph tham chiếu khi context startup. Late-bound data nên đi vào **Tasklet, ItemReader, ItemProcessor, ItemWriter** hoặc những collaborators có scope, không ép chính `Step` thành một scoped proxy một cách tùy tiện.

### Có thể test @StepScope không cần chạy job không?

Có. Spring Batch test cung cấp:

- `StepScopeTestExecutionListener`: tạo/sử dụng `StepExecution` giả cho mỗi test method.
- `StepScopeTestUtils.doInStepScope(stepExecution, callable)`: chạy một đoạn code khi step scope được bind.
- `MetaDataInstanceFactory.createStepExecution(params)`: xây execution test với JobParameters chỉ định.

Ví dụ conceptual snippet (không phải file trong project):

```java
JobParameters params = new JobParametersBuilder()
        .addString("batchId", "SCOPE-EXAMPLE", true)
        .toJobParameters();

StepExecution mockStep =
        MetaDataInstanceFactory.createStepExecution(params);

String result = StepScopeTestUtils.doInStepScope(
        mockStep,
        () -> scopedReader.read());
```

Snippet giả định có `scopedReader` đã được inject và implements `ItemReader<String>`. Để chạy độc lập cần cấu hình bean reader cụ thể, `@SpringBatchTest` hoặc test context đã có step-scoped infrastructure, và imports:
`org.springframework.batch.test.MetaDataInstanceFactory` và `StepScopeTestUtils`. Không suy ra method `read()` trả `SCOPE-EXAMPLE` nếu reader implementation chưa được xác định.

### Job scope trong multi-threaded steps

`@JobScope` có thể late-bind job-level parameters/context. Tuy nhiên, Spring Batch docs cảnh báo job-scoped beans trong multi-threaded hoặc partitioned steps vì context không tự được truyền tới các worker threads mà framework không quản lý đầy đủ. Cần xác định thread/partition ownership thay vì copy một scoped bean setup từ single-thread demo.

## 17. JobParameters: identifying và nonidentifying ảnh hưởng restart

Trong project:

```java
new JobParametersBuilder()
        .addString("batchId", "BATCH-001", true)
        .addLong("attempt", 1L, false)
        .toJobParameters();
```

Ý nghĩa:

- `batchId` là business identity của một batch run, **identifying=true**.
- `attempt` chỉ là metadata phụ trợ, **identifying=false**.
- Đổi `attempt` từ 1 sang 2 không làm đổi JobInstance.
- Sau khi JobInstance đã `COMPLETED`, launch lại với cùng identifying params thường ném `JobInstanceAlreadyCompleteException`.
- Đổi `batchId` sẽ tạo JobInstance khác (nếu job name giữ nguyên), có thể chạy từ đầu.
- Với failed instance có thể restart khi job restartable và metadata/step state cho phép; không có nghĩa mọi failed job tự resume hoàn hảo.

### Bẫy hiểu sai hoàn thành job

Nếu job đã completed và bạn muốn “chạy lại dữ liệu của ngày hôm qua”, chỉ thêm `attempt` nonidentifying **không đủ** để tạo JobInstance mới. Bạn cần policy reprocessing rõ ràng: một identifying `runId`/revision parameter, job name/version mới hoặc cách replay chuyên biệt theo nghiệp vụ. Ngược lại, khi muốn **restart từ checkpoint**, phải giữ **identifying parameters giống nhau**.

### Kiểm chứng bằng test

Test `completedInstanceRejectsRerunWithOnlyNoteChanged` khởi chạy lần một thành công, rồi thay `attempt` nonidentifying và kỳ vọng exception. Test `changedIdentifyingBatchIdCreatesNewInstance` thay `batchId` và kiểm tra instance IDs khác nhau.

**Không gọi `jobs.getUniqueJobParameters()` trong test đang cố chứng minh restart same-instance**: utility đó sinh random identifying parameter để tránh collision, làm mất precondition. Khi muốn demo fresh-run đơn giản không phụ thuộc params, utility này hữu ích; nhưng với semantics của job, hãy tạo parameters tường minh.

## 18. Job-level parameter validation và step-level preconditions

`ExportJobConfiguration` gắn `.validator(...)` yêu cầu `batchId` hợp lệ. Test:

```java
JobParameters missing = new JobParametersBuilder()
        .addLong("attempt", 1L, false)
        .toJobParameters();

assertThrows(
        JobParametersInvalidException.class,
        () -> jobs.launchJob(missing));
```

cho thấy **full Job** kiểm tra tham số trước khi chạy.

Nhưng `launchStep("collectStep", params)` thực hiện step trong surrogate test job, không dùng full Job-level validator. Vì vậy `CollectTasklet` tự kiểm tra `batchId` trước khi ghi probe, còn `PublishTasklet` cũng làm tương tự. Bảo vệ ngay tại component boundary có ích ngay cả khi job được khởi động từ một nhánh khác.

### Khi nào parameter validation nên phức tạp hơn?

Hệ thống xử lý theo ngày có thể yêu cầu:

- `businessDate` theo ISO-8601, parse được bằng `LocalDate.parse`.
- `tenantId` thuộc allowlist và người khởi chạy có quyền phù hợp.
- `inputPath` không trỏ đường dẫn ngoài thư mục/namespace được phép.
- `dryRun` boolean có default rõ.
- `maxRows` là số dương trong giới hạn.
- `outputPath` là nonidentifying nếu không nên quyết định danh tính JobInstance.
- Mọi identifying flags được review vì thay đổi chúng làm khác restart semantics.

Không dùng tên tham số chung `time` rồi ngầm lấy `System.currentTimeMillis()` mỗi lần mà không ghi rõ policy. Và đừng dùng raw user input làm file path/SQL query ở Tasklet mà không validate.

## 19. Failure của job: khi nào ném exception, khi nào trả FAILED?

Hai trường hợp:

**A. Launcher từ chối khởi tạo một execution:** sai JobParameters, instance đã completed, job đang chạy hoặc repository lỗi nghiêm trọng. Một API launch có thể **ném exception** như `JobParametersInvalidException`, `JobInstanceAlreadyCompleteException` hoặc `JobExecutionAlreadyRunningException`.

**B. Job/Step đã bắt đầu nhưng Tasklet/Reader/Writer ném lỗi trong lúc xử lý:** với launcher đồng bộ thông thường, nhiều trường hợp `launchJob(...)` **trả về `JobExecution` có `BatchStatus.FAILED`**; exception gốc được ghi trong failure exceptions/exit description. Vì vậy chỉ viết:

```java
assertDoesNotThrow(() -> jobs.launchJob(params));
```

**không đủ** để chứng minh job thành công. Phải assert `execution.getStatus()`, `getExitStatus()`, `getAllFailureExceptions()` khi cần và dữ liệu kết quả.

**Không khẳng định mọi lỗi trong Batch được biến thành FAILED:** validator/repository/start exceptions có thể được ném ra khỏi `launchJob`. Kiểu lỗi và phase quyết định cách test.

### Ví dụ failure step (snippet bổ sung)

Một Tasklet cố ý ném exception:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext context) {
    throw new IllegalStateException(
            "simulated downstream failure");
}
```

Là **snippet**, không thuộc runnable project chính. Khi đặt trong một Job/Step test có transaction manager và repository thật, kiểm tra JobExecution/StepExecution failed, exit status, failure exception và **đúng side effect** đã rollback hay chưa. Đừng chỉ assert exception được ném bởi test runner.

## 20. Restartability, checkpoints và idempotency

Một failed JobInstance có thể được restart với cùng identifying JobParameters nếu job cho phép restart. Nhưng resume chính xác tới đâu phụ thuộc Step:

- Một step `COMPLETED` trong execution cũ thường bị **skip** khi restart, trừ khi cấu hình `allowStartIfComplete(true)` hoặc flow rules khác.
- Một chunk-oriented reader/writer có `ItemStream` và `ExecutionContext` có thể khôi phục offset/count theo checkpoint.
- Một Tasklet có side effect ngoài transaction và thất bại giữa chừng phải **idempotent** hoặc có cơ chế compensation/recovery.
- Khi input file đã thay đổi sau failure, restart có thể tạo kết quả khác; cần pin input revision/hash.
- Gọi job với identifying parameter mới tạo instance mới, **không phải restart**.

### Test restart tốt cần có hai phase

```text
Phase 1:
  Launch JobInstance X
  -> Step A COMPLETED
  -> Step B FAILED có kiểm soát
  -> Assert metadata và side effect phase 1

Phase 2:
  Sửa condition lỗi nhưng giữ identifying parameters của X
  -> Launch lại X (new JobExecution)
  -> Assert Step A được skip theo policy,
     Step B chạy tiếp theo checkpoint/logic
  -> Assert dữ liệu không duplicate và JobInstance identity giữ nguyên
```

Đây là **sơ đồ chiến lược**, không phải một test chạy trong project demo (bởi demo không có configurable failing step). Để thực hành, thêm một fail-once Tasklet hoặc chunk Reader có checkpoint, rồi test execution statuses và exact output. Không viết kết quả expected “resume từ record thứ 11” nếu reader chưa lưu position.

### Idempotency không đến từ Batch metadata một mình

JobRepository biết tiến độ step, nhưng không thể rollback upload S3 đã thành công hoặc Kafka message đã publish khi DB transaction fail. Với external side effects, cần idempotency key theo JobInstance/batchId/record ID, outbox pattern, hoặc checkpoint/compensation được thiết kế thực tế.

## 21. Chunk-oriented job: phần phải kiểm tra ngoài Tasklet

Nhiều batch jobs thật dùng:

```text
ItemReader<T> -> ItemProcessor<T,R> -> ItemWriter<R>
            [chunk size N, transaction boundary]
```

Một test chunk nên bảo vệ:

- `readCount` đúng số input records (gồm records đọc thực).
- `filterCount` nếu processor trả null để lọc items.
- `writeCount` đúng số items đã ghi.
- `readSkipCount`/`processSkipCount`/`writeSkipCount` theo policy.
- `commitCount`/`rollbackCount` phù hợp transaction/step semantics.
- Output rows/file records có giá trị đúng, không chỉ count.
- Restart với `ItemStream` khôi phục offsets/checkpoint.
- Skip/retry limit; đúng exception type mới được skip/retry.
- Không duplicate writes khi một chunk retry.

### Ví dụ kiểm tra một processor thuần

```java
record RawOrder(String id, int amountCents) {}
record ReportLine(String id, int netCents) {}

ItemProcessor<RawOrder, ReportLine> processor =
        order -> order.amountCents() < 0
                ? null
                : new ReportLine(
                        order.id(), order.amountCents());

assertEquals(
        new ReportLine("A", 100),
        processor.process(new RawOrder("A", 100)));

assertNull(processor.process(
        new RawOrder("INVALID", -1)));
```

Đây là **snippet unit test**, cần imports `org.springframework.batch.item.ItemProcessor` và JUnit assertions. Nếu muốn test runnable độc lập, phải đặt record types và test method vào một test class. Nó cho thấy logic dễ kiểm tra không cần JobRepository. Khi processor trả null, Spring Batch hiểu là **filter item**, không phải skip do exception; đừng gộp filterCount và processSkipCount.

### Mốc chunk size không nói toàn bộ commitCount

Với chunk size 10, đọc 25 records không nhất thiết có `commitCount==3` trong mọi job/reader/setup vì có chunk cuối, initialization, retries hoặc rollback. Hãy dùng metric thực từ StepExecution/fixture rõ thay vì công thức tưởng tượng. Ưu tiên assert output và quan hệ counters, sau đó mới assert exact counts khi behavior đã xác định.

## 22. JobRepositoryTestUtils và isolation

`@SpringBatchTest` còn tạo `JobRepositoryTestUtils`, có `removeJobExecutions()` và các helpers. Ví dụ method-level cleanup:

```java
@Autowired
JobRepositoryTestUtils repositoryTestUtils;

@BeforeEach
void clearBatchMetadata() {
    repositoryTestUtils.removeJobExecutions();
}
```

Đây là **snippet thêm vào một test class**, không đưa vào project chính vì bộ mẫu dùng batch IDs riêng để kiểm tra instance identity. `removeJobExecutions()` xóa batch job executions/instances được repository test quản lý; nếu dùng trên DB shared/production, có thể phá metadata của công việc thật.

**Nó không dọn:**

- Business tables mà steps đã insert/update.
- CSV/export files đã tạo.
- S3 objects.
- Kafka messages/HTTP calls.
- In-memory `JobProbe`.
- External counters/caches.

Với test restart hoặc kiểm tra duplicate key, **đừng dọn metadata giữa hai phases của cùng một test** vì đó là state cần giữ để xác minh restart. Sau test, có thể reset toàn bộ test database/schema/container theo ownership.

### Tại sao project này không cần deleteAll metadata?

`freshBatchId(...)` sinh identifying parameter khác nhau giữa test scenarios. Mỗi test tạo JobInstance độc lập, nên không cần xóa lịch sử trước mọi method. Probe được clear trong `@BeforeEach`; metadata H2 vẫn còn nhưng không đổi kết quả của từng scenario.

**Không đồng nghĩa UUID là phương án duy nhất:** với từng test method chạy trong DB riêng, có thể dùng IDs deterministic như `FULL-001`, `STEP-COLLECT-001`. Dù vậy khi context/database được reuse xuyên tests hoặc repeated invocations, phải bảo đảm uniqueness/collision policy rõ.

## 23. @Transactional trên test không thay thế batch cleanup

Một lỗi phổ biến:

```java
@SpringBatchTest
@SpringBootTest
@Transactional
class MyBatchTest {
    // ...
}
```

Developer kỳ vọng tất cả business DB writes trong job được rollback theo test transaction. Thực tế Spring Batch điều khiển **Step-level transactions** và có thể chạy qua JobLauncher/threads riêng; test-managed transaction không mặc nhiên bao trùm các commits của step.

Một trường hợp khác: JobRepository tạo JobExecution qua một transaction khác, trong khi test mở transaction bao ngoài và chưa commit fixture rows. Step có thể không thấy input chưa commit hoặc metadata update có lock/conflict. Vì vậy nên:

1. Dùng test-specific database/schema.
2. Chuẩn bị fixture với transaction visibility đúng cho step.
3. Gọi job/step launcher.
4. Kiểm tra outputs đã commit và batch metadata.
5. Cleanup/reset theo DB ownership.
6. Đừng dùng `@Rollback` trên test thread như “bảo hành” mọi side effect của job.

Trong project demo, `@SpringBootTest` test class **không** đánh dấu `@Transactional` để tránh giả định transaction bao trùm toàn job.

## 24. Test dữ liệu đầu vào và SQL fixtures

Một ETL batch job thường đọc dữ liệu từ DB hoặc file. Cần chuẩn bị fixture có purpose rõ:

- Hàng hợp lệ để test success path.
- Hàng invalid để test filtering/skip policy.
- Duplicate business keys để test idempotency.
- Dữ liệu boundary (0, max, nullable) theo nghiệp vụ.
- Thứ tự/sorting explicit nếu output cần stable ordering.
- Một dữ liệu lỗi ở giữa chunk để test rollback/retry.
- Empty input để kiểm tra job hoàn thành với 0 records hay fail theo contract.

Dùng `@Sql` trước job run nếu script cần insert DB rows; **lưu ý transaction mode** vì step có thể chạy ở transaction/thread khác. Với full integration test, test database/schema riêng và committed test setup thường ít bất ngờ hơn uncommitted fixture trong test transaction.

### Không phụ thuộc seed data của ứng dụng

Nếu production app có demo seed toàn cục, job test không nên dùng dữ liệu đó trừ khi nó là reference data được versioned. Fixtures nên ở `src/test/resources`, tách khỏi production scripts. Điều này giúp job tests deterministic và không fail vì người khác thêm một demo record.

## 25. Nhiều jobs trong cùng ApplicationContext

`@SpringBatchTest` có thể tự chọn `Job` khi context chỉ có một. Nếu production app có ba Job beans:

```text
importUsersJob
monthlyBillingJob
expireSessionsJob
```

hãy chọn job cần test tường minh, không dựa vào injection ngẫu nhiên. Ví dụ một test configuration hoặc setup gắn `JobLauncherTestUtils.setJob(targetJob)` khi utilities được cấu hình phù hợp:

```java
@Autowired
JobLauncherTestUtils jobs;

@Autowired
@Qualifier("monthlyBillingJob")
Job targetJob;

@BeforeEach
void selectJob() {
    jobs.setJob(targetJob);
}
```

Đây là **snippet**: với nhiều Job beans, phải đảm bảo test utility được tạo/autowired thành công, ví dụ chỉ import target job config hoặc đăng ký test-specific JobLauncherTestUtils bean thay vì để auto-injection yêu cầu một Job duy nhất. Không khẳng định snippet tự khắc phục một `NoUniqueBeanDefinitionException` đã xảy ra **trước** @BeforeEach.

Tốt hơn, tách các job configurations thành modules dễ import/test độc lập; tránh `@ComponentScan` toàn enterprise app cho một step test.

## 26. Scheduler và JobLauncher là hai việc khác nhau

Ứng dụng có thể dùng `@Scheduled` hoặc Quartz để quyết định lúc nào gọi job:

```java
@Scheduled(cron = "0 0 2 * * *")
public void runDaily() throws Exception {
    jobLauncher.run(job, parametersForToday());
}
```

Đây là **snippet kiến trúc** thiếu class/injection; không thuộc project runnable. `@SpringBatchTest` kiểm tra **Job khi được launch**, không tự chứng minh lịch cron đúng, timezone đúng hay scheduler chỉ gọi một lần trên cluster.

Chia test thành:

- **Scheduler unit test**: clock fixed, verify service/JobLauncher được gọi với tham số đúng, không chờ 02:00 thật.
- **Batch job integration test**: gọi `launchJob` và kiểm tra steps/output/metadata.
- **Production scheduler integration**: Quartz persistence/distributed lock/misfire/retry nếu yêu cầu.

**Không dùng Thread.sleep chờ lịch cron thực** để kiểm tra job ở unit/integration test. Với scheduling, test logic xác định ngày, parameter và trigger rõ ràng.

### Chống chạy trùng ở nhiều app instances

Hai schedulers trên hai nodes có thể khởi chạy cùng identifying JobParameters. JobRepository có cơ chế từ chối một số concurrent/duplicate job instances, nhưng không thay thế distributed scheduling policy, DB constraints, fencing hoặc idempotent business writes. Cần test concurrency/recovery riêng nếu hệ thống thật chạy cluster.

## 27. Nếu JobLauncher chạy bất đồng bộ

Project mẫu dùng Boot-managed launcher đồng bộ theo cấu hình đơn giản. Một số hệ thống cấu hình `TaskExecutorJobLauncher` với asynchronous `TaskExecutor`. Khi đó:

```java
JobExecution execution = jobLauncher.run(job, parameters);

// Trạng thái ở thời điểm trả về có thể STARTING/STARTED.
```

**Không assert `COMPLETED` ngay sau run** trong trường hợp launcher bất đồng bộ. Phải poll JobExplorer/JobRepository hoặc một business-visible state tới terminal status (`COMPLETED`, `FAILED`, `STOPPED`) với timeout.

Pseudo-test:

```text
Launch job
  -> nhận executionId
  -> repeat tới deadline:
       refresh JobExecution từ JobExplorer
       nếu status terminal: stop waiting
       nếu quá deadline: FAIL
  -> assert JobExecution, StepExecutions và output
```

Có thể dùng Awaitility khi dự án thêm dependency:

```java
await()
    .atMost(Duration.ofSeconds(20))
    .untilAsserted(() -> {
        JobExecution current =
                jobExplorer.getJobExecution(executionId);
        assertEquals(
                BatchStatus.COMPLETED,
                current.getStatus());
    });
```

Đây là **snippet** cần `await()` từ Awaitility, `jobExplorer`/`executionId` đã khai báo và library phụ thuộc; không có trong runnable project. Không busy-spin không deadline, không hardcode một `Thread.sleep(5000)` rồi đoán job đã hoàn thành.

**Lưu ý:** Test utilities và job scopes trong async/multithreaded jobs cần kiểm soát context/transaction/timeouts; không suy tính thread-safe của writer từ một test tasklet đơn luồng.

## 28. Giám sát và xử lý lỗi

Một kiểm thử production-grade batch nên quan sát thêm:

- Tên JobInstance/identifying params đã run.
- JobExecution ID và terminal status.
- Thời điểm bắt đầu/kết thúc và thời lượng.
- StepExecution statuses, read/write/skip/rollback counts.
- Error cause/ExitStatus description (không chứa PII/secrets).
- Business output đã ghi vào DB/files/outbox.
- Retry và restart policy.
- Cách xử lý partial files, rollback chunks, orphaned artifacts.
- Thời gian chạy/tài nguyên trên dữ liệu lớn.

Khi job FAIL, trước tiên kiểm tra **failure exceptions và step name**; không đổ mọi lỗi vào batch metadata schema. Nếu `getAllFailureExceptions()` trống nhưng job FAILED theo flow/ExitStatus custom, xem step transitions, listeners và exit descriptions.

### BatchStatus và ExitStatus có thể khác

Một step có `BatchStatus.COMPLETED` nhưng `ExitStatus` custom như `COMPLETED_WITH_WARNINGS` để điều khiển flow. Đừng assert status và exit code là cùng một loại/string trong mọi ứng dụng. Trong demo không có custom transitions nên cả hai là COMPLETED.

## 29. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Không tắt Boot auto-run trong test | Job chạy trước khi có fixture/params | `spring.batch.job.enabled=false` |
| Thêm `@EnableBatchProcessing` tùy tiện trong Boot 3.3 | Boot auto-config/schema init back off | Dùng Boot starter/auto-config, tự cấu hình chỉ khi cần |
| Dùng JobBuilderFactory từ tutorial cũ không đối chiếu Batch 5 | API lỗi hoặc deprecated | `new JobBuilder(name, jobRepository)` |
| Chạy `launchJob()` mà không truyền job params cần thiết | Missing params/validator fail | `launchJob(explicitParams)` |
| Luôn thêm random identifying timestamp | Restart test không còn cùng JobInstance | Kiểm soát identifying flags |
| Đổi nonidentifying param để re-run completed instance | `JobInstanceAlreadyCompleteException` | New identifying identity nếu muốn run mới |
| Xem `launchStep` là full job | Bỏ qua flow/validator/predecessors | Dùng `launchJob` cho flow |
| `@Value("#{jobParameters[...]}"` trên singleton | Step scope không active lúc startup | `@StepScope` trên component cần late binding |
| Đặt `@StepScope` lên cả Step bean vô cớ | Wiring/proxy phức tạp | Scope Tasklet/Reader/Writer |
| Chỉ assert không ném exception | Job có thể trả `FAILED` | Assert JobExecution và output |
| Chỉ assert `COMPLETED` | Tasklet rỗng vẫn completed | Assert business side effect và step metadata |
| Test `@Transactional` và nghĩ mọi batch writes rollback | Step commits nằm ngoài transaction test | Dedicated DB + cleanup/reset |
| Xóa batch metadata giữa hai phases restart test | Không còn checkpoint/history | Giữ metadata tới khi assertions hoàn tất |
| Dùng JobRepositoryTestUtils trên shared DB | Xóa lịch sử jobs của người khác | Test DB/schema riêng |
| Dùng fixed Thread.sleep cho async job | Flaky/slow tests | Bounded polling JobExplorer |
| Assert ordering trên parallel steps | Race do concurrency | Assert DAG/dependencies hoặc controlled ordering |
| Dùng in-memory probe làm proof JDBC rollback | Probe không transactional | Query business DB |
| Đếm read/write cho Tasklet demo như chunk | Sai loại metrics | Assert counts ở chunk tests |
| Dùng fake credentials/PII từ production snapshot | Rò dữ liệu nhạy cảm | Synthetic fixtures và secrets riêng |

## 30. Cách debug theo thứ tự

1. Kiểm tra có Spring Batch thật không; project chỉ có scheduler thì test scheduler, không cần Batch.
2. Xác nhận Spring Boot 3.3.5, Spring Batch 5.1.x, `spring-boot-starter-batch`, `spring-batch-test`, H2 driver.
3. Xác nhận test profile active, `spring.batch.job.enabled=false`.
4. Xác nhận các bảng BATCH_* tồn tại, không bị quản lý bởi hai schema mechanisms xung đột.
5. Nếu JobRepository bean thiếu, xem `@EnableBatchProcessing`/`DefaultBatchConfiguration` có làm Boot back off.
6. Nếu `JobLauncherTestUtils` thiếu Job, kiểm tra số lượng Job beans hoặc bean selection.
7. Nếu StepScope không active, kiểm tra `@StepScope` và đang chạy trong StepExecution thật.
8. Nếu `launchStep` báo không tìm thấy step, kiểm tra step name trong Job graph và bean wiring.
9. Nếu job bị `JobInstanceAlreadyCompleteException`, kiểm tra identifying params và lịch sử JobRepository.
10. Nếu launcher trả `JobExecution FAILED`, xem failure exceptions/ExitStatus và step logs.
11. Nếu job STATUS COMPLETED nhưng không có output, kiểm tra Tasklet/Writer hoặc transaction/commit.
12. Nếu test pass riêng nhưng fail cả suite, kiểm tra reused JobRepository, test IDs, context cache, parallel runs.
13. Nếu async test fail, đọc JobExecution status theo polling/deadline thay vì assert lập tức.
14. Nếu production job không restart đúng, kiểm tra ItemStream/ExecutionContext checkpoint và external idempotency.

## 31. Kết quả mong đợi từ project mẫu

| Test method | Điều được bảo vệ | Kết quả nguồn code dự kiến |
| --- | --- | --- |
| `wholeJobRunsBothStepsInOrder` | Cả Job, status, exit code, flow, output | COMPLETED; collect → publish |
| `launchCollectStepDoesNotRunPublishStep` | Chỉ Collect step | Một StepExecution; stage collect |
| `launchPublishStepDoesNotRunCollectStep` | Chỉ Publish step | Một StepExecution; stage publish |
| `stepScopeReadsTheCurrentJobParameter` | Late binding từ JobParameters | Context chứa batchId đúng |
| `completedInstanceRejectsRerunWithOnlyNoteChanged` | Nonidentifying param không đổi instance | JobInstanceAlreadyCompleteException |
| `changedIdentifyingBatchIdCreatesNewInstance` | Identifying param đổi instance | Hai instance IDs khác |
| `jobValidatorRejectsMissingBatchId` | Job-level validation | JobParametersInvalidException |
| `launchStepRejectsUnknownStepName` | Step lookup failure | IllegalStateException |
| `parametersExposeTheirIdentifyingFlags` | Params typed + identifying flag | batchId=true, attempt=false |

**Đây là expected assertions từ 9 test methods, không phải console output đã quan sát**. Nếu thực hành, chạy Gradle rồi đọc test report trước khi tuyên bố 9 PASS.

### Lệnh chạy

Nếu project đã có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.batch.ExportBatchJobTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu không có Wrapper nhưng máy đã cài Gradle phù hợp:

```bash
gradle test
```

Kết quả JUnit/Gradle sau khi chạy thường nằm ở:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

Không có stdout nghiệp vụ cố định: Spring Batch và H2 có thể log chi tiết khác nhau tùy cấu hình logging. Dấu hiệu PASS đáng tin là Gradle test task thành công và report ghi số tests passed đúng, không phải một dòng console tự viết trong tài liệu.

## 32. Bài tập thực hành

1. Chạy `ExportBatchJobTest` rồi xem hai step names trong `JobExecution.getStepExecutions()`.
2. Bỏ `spring.batch.job.enabled=false` trong test profile: phân tích vì sao startup runner có thể cố chạy Job không có batchId.
3. Đổi thứ tự `.start(collectStep).next(publishStep)` và xem probe stages/order assertion phát hiện thay đổi.
4. Thử bỏ `@StepScope` trên CollectTasklet rồi đọc lỗi late-binding ở context startup.
5. Chạy riêng `publishStep` và giải thích vì sao `collectStep` không được gọi.
6. Thử một step phụ thuộc JobExecutionContext do step trước tạo; dùng `launchStep(step, params, context)` để set fixture context.
7. Gọi full job hai lần với cùng batchId nhưng `attempt` khác; xác nhận exception không được sửa bằng cách catch rồi trả 200.
8. Đổi `batchId` khi chạy lại, kiểm tra JobInstance ID khác và cả hai executions hoàn thành.
9. Thêm JobParametersValidator kiểm tra `businessDate` ISO; viết cases invalid/missing.
10. Đổi `batchId` từ identifying=true sang false để xem nguy cơ mọi runs trở thành cùng instance.
11. Thêm fail-once Tasklet ở publishStep, viết test restart cùng identifying parameters.
12. Thêm chunk-oriented step đọc 10 rows và filter 1; assert read/write/filter counts từ data fixture thật.
13. Viết ItemProcessor unit test mà không mở Batch context.
14. Thử sử dụng `JobRepositoryTestUtils.removeJobExecutions()` chỉ trên H2 test; phân biệt metadata và business effects.
15. Thêm một Job khác trong context, xử lý JobLauncherTestUtils selection rõ ràng.
16. Biến launcher thành async để luyện bounded polling terminal status.
17. Viết test scheduler tạo đúng JobParameters cho ngày kinh doanh cố định.
18. Thử chạy hai test classes song song trên một shared H2 DB; cô lập batchId/database để tránh collision.
19. Thay H2 bằng PostgreSQL Testcontainers và chạy batch metadata migrations đúng version.
20. Bổ sung assertion rằng file/output idempotent sau restart, không duplicate.

## 33. Checklist QA dành cho code review

- [ ] Ứng dụng thật có sử dụng Spring Batch, không thêm Batch test framework vô cớ?
- [ ] Boot/Batch API imports khớp phiên bản Java17+/Boot3.3.5/Batch5.1?
- [ ] Job không auto-run khi test context khởi tạo?
- [ ] Batch metadata JDBC schema được tạo bằng đúng initializer/migration?
- [ ] JobRepository và PlatformTransactionManager có trỏ đúng DataSource?
- [ ] `@SpringBatchTest` đăng ký đúng JobLauncherTestUtils/JobRepositoryTestUtils?
- [ ] Job under test được chọn tường minh khi context có nhiều Jobs?
- [ ] JobParameters có tên/type/default/identifying flags đã review?
- [ ] Có test missing/invalid required parameters?
- [ ] Có test full job flow, không chỉ step riêng?
- [ ] Có test step riêng bằng `launchStep` và không hiểu lầm surrogate job?
- [ ] Step-scoped components được late-bind đúng trong runtime context?
- [ ] Không scope chính Step bean vô cớ?
- [ ] Có kiểm tra BatchStatus, ExitStatus và StepExecutions?
- [ ] Với chunk job, có assertions read/write/filter/skip/rollback counts hợp lệ?
- [ ] Có assert output thực, không chỉ COMPLETED?
- [ ] Test restart giữ identifying parameters giống nhau và metadata không bị xóa?
- [ ] Test fresh run dùng identifying parameters khác nhau?
- [ ] Không mặc định `@Transactional` trên test rollback mọi step effects?
- [ ] DB/fixtures/side effects được cô lập và cleanup trong test ownership?
- [ ] Có phân biệt asynchronous launcher với synchronous launcher?
- [ ] Có tránh Thread.sleep không giới hạn/không điều kiện?
- [ ] Scheduler timezone/trigger logic được test riêng nếu ứng dụng có lịch?
- [ ] Không dùng production credentials, PII, file path thật trong fixtures?
- [ ] Đã chạy Gradle/CI test suite và đọc report thật, không suy PASS từ code?
- [ ] Một test chạy độc lập và cả suite cho kết quả nhất quán?

## 34. Tài liệu tham khảo

- [Spring Batch 5.1 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.1/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, `launchJob`, `launchStep`, `StepScopeTestUtils`. Nếu URL minor version thay đổi, tra mục “Testing” trong [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/testing.html).
- [JobLauncherTestUtils 5.1 Javadoc](https://docs.spring.io/spring-batch/docs/5.1.1-SNAPSHOT/org/springframework/batch/test/JobLauncherTestUtils.html): signatures `launchJob(JobParameters)` và `launchStep(name, params)`, surrogate job.
- [SpringBatchTest 5.1 Javadoc](https://docs.spring.io/spring-batch/docs/5.1.1-SNAPSHOT/org/springframework/batch/test/context/SpringBatchTest.html): test utility registrations, step/job scope listeners.
- [Spring Batch 5.1 — TaskletStep](https://docs.spring.io/spring-batch/reference/5.1/step/tasklet.html): Tasklet, RepeatStatus và transactions.
- [Spring Batch 5.1 — Late Binding](https://docs.spring.io/spring-batch/reference/5.1/step/late-binding.html): `@StepScope` và JobParameters SpEL.
- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring-job.html): JobInstance, restartability và flow.
- [Spring Batch — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.1/step/chunk-oriented-processing/configuring.html): StepBuilder, transaction manager, chunk semantics.
- [Spring Boot 3.3 — Batch Applications](https://docs.spring.io/spring-boot/3.3/how-to/batch.html): `spring.batch.job.enabled`, `@EnableBatchProcessing`, Batch DataSource.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `spring.batch.jdbc.initialize-schema` và SQL initialization.
- [JobRepositoryTestUtils 5.1 Javadoc](https://docs.spring.io/spring-batch/docs/5.1.0/org/springframework/batch/test/JobRepositoryTestUtils.html): cleanup metadata, utility semantics.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, assertions và independent methods.

## 35. Kết luận

Kiểm thử Spring Batch không dừng ở việc gọi `JobLauncher` và kiểm tra không có exception. **Job** là flow, **Step** là đơn vị xử lý, **JobParameters** quyết định cả dữ liệu đầu vào lẫn `JobInstance identity`, còn **JobRepository** lưu execution history để điều khiển restart.

Với Spring Boot 3.3 / Spring Batch 5.1, đặt `spring.batch.job.enabled=false` trong test profile, để Boot quản lý JDBC Batch infrastructure phù hợp, dùng `@SpringBatchTest` cùng `JobLauncherTestUtils.launchJob(params)` để kiểm tra toàn flow và `launchStep(name, params)` để thử riêng từng step. Dùng `@StepScope` cho components cần late-bound parameters, xác minh `StepExecution`/`BatchStatus`/`ExitStatus` **và output**, không xem completed là đủ.

Những bài kiểm thử nâng cao phải xử lý đúng identifying flags, cùng instance vs instance mới, failed-job restart, chunk checkpoints, transaction boundaries, asynchronous launcher và scheduler trigger riêng. **Không khẳng định dữ liệu/side effect đã rollback chỉ vì test method có `@Transactional`**, và không tuyên bố Gradle tests đã PASS khi chưa thực thi. Cách tổ chức này tạo nền tảng test Batch rõ ràng, có thể tái hiện và bảo vệ hành vi khi ứng dụng thật sự dùng batch jobs.
