# Quan sát ApplicationRunner và CommandLineRunner

Trong chương **Quan sát** của module **SPRING_CLOUD_TASK**, việc một ứng dụng chạy hữu hạn rồi thoát không có nghĩa chúng ta có đủ thông tin để biết **nó đã thực hiện bước nào, mất bao lâu, thất bại ở đâu và dữ liệu nghiệp vụ đã được ghi thành công hay chưa**. Đặc biệt với các tác vụ chạy theo lịch hoặc theo yêu cầu, thông tin giám sát cần tiếp tục có giá trị **sau khi JVM kết thúc**.

Spring Boot có hai giao diện phổ biến để thực thi công việc một lần sau giai đoạn khởi tạo ứng dụng: `ApplicationRunner` và `CommandLineRunner`. Spring Cloud Task bổ sung `TaskExecution`, `TaskRepository` và các callback vòng đời để theo dõi việc bắt đầu/kết thúc của **cả tiến trình task**. Hai lớp này bổ trợ nhau nhưng **không giống nhau**: một `TaskExecution` hoàn tất không tự động cho biết mỗi runner mất bao nhiêu thời gian, bao nhiêu bản ghi đã xử lý hoặc runner thứ hai có thực sự được gọi hay không.

Bài học sẽ triển khai **structured logging, correlation ID, thời gian thực thi bằng Micrometer Timer và TaskExecutionListener**, đồng thời chỉ ra giới hạn của những nguồn quan sát khi task bị kill, repository chưa sẵn sàng hoặc hệ thống thu thập metrics chưa kịp đọc dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `ApplicationRunner` và `CommandLineRunner` về kiểu tham số và cách Spring Boot gọi chúng.
- Giải thích thứ tự thực thi giữa nhiều runner, hành vi khi một runner ném exception và ý nghĩa của bước chưa được gọi.
- Đo thời gian **từng runner** bằng đồng hồ đơn điệu (`System.nanoTime()`) và đưa kết quả vào `Micrometer Timer`.
- Ghi log có cấu trúc với `runId`, tên runner, trạng thái, thời lượng và mã lỗi.
- Dùng `TaskExecutionListener` để theo dõi **vòng đời task**, đồng thời phân biệt callback trước/ sau các thao tác ghi `TaskRepository`.
- Hiểu vì sao metrics trong bộ nhớ của tiến trình ngắn hạn không mặc nhiên được hệ giám sát thu thập.
- Đối soát log, metrics, `TaskExecution`, mã thoát của tiến trình và kết quả nghiệp vụ.
- Thiết kế cảnh báo và kiểm thử cho lỗi trước khởi tạo context, lỗi trong runner, JVM bị dừng và retry.

## 2. Runner chạy ở vị trí nào trong vòng đời Spring Boot?

Theo tài liệu Spring Boot, các bean triển khai `ApplicationRunner` và `CommandLineRunner` được gọi trong giai đoạn cuối của `SpringApplication.run(...)`, **sau khi context được khởi tạo** và trước khi lời gọi `run` hoàn tất. Spring Cloud Task có cơ chế tạo metadata lúc hạ tầng task đã sẵn sàng và cập nhật nó khi chạy thành công hoặc gặp lỗi theo điều kiện hoạt động.

~~~mermaid
flowchart TD
    A["JVM được launcher khởi chạy"] --> B["SpringApplication.run bắt đầu"]
    B --> C["Tạo ApplicationContext, bean, DataSource"]
    C --> D["Spring Cloud Task chuẩn bị/ghi TaskExecution khi có thể"]
    D --> E["Runner có thứ tự ưu tiên nhỏ hơn"]
    E --> F["Runner kế tiếp nếu chưa có lỗi chặn"]
    F --> G["Task lifecycle ghi nhận kết thúc khi có thể"]
    G --> H["Đóng context và kết thúc tiến trình"]
    C -. "Lỗi khởi tạo sớm" .-> I["Có thể không có TaskExecution / runner log"]
    E -. "Runner ném exception" .-> J["Runner sau có thể không được gọi"]
    F -. "JVM bị kill / mất DB" .-> K["Có thể thiếu sự kiện kết thúc"]
~~~

Sơ đồ là mô hình vận hành để quan sát, không phải cam kết thứ tự mọi callback nội bộ ở mọi phiên bản Spring Boot và Spring Cloud Task.

### 2.1. ApplicationRunner và CommandLineRunner

| Tiêu chí | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Chữ ký | `run(ApplicationArguments args)` | `run(String... args)` |
| Dữ liệu nhận vào | `ApplicationArguments` đã phân biệt option và non-option | Mảng chuỗi tham số thô |
| Lấy option `--runId=R-001` | `args.getOptionValues("runId")` | Tự parse chuỗi hoặc dùng parser |
| Được Spring Boot gọi khi nào? | Cuối giai đoạn khởi động, trước khi `SpringApplication.run` trả về | Cùng giai đoạn |
| Phù hợp | Tác vụ có tham số kiểu `--name=value` | Công việc đơn giản hoặc cần xử lý raw arguments |
| Khả năng quan sát | Cần chủ động ghi log/metric trong `run` | Cũng cần chủ động ghi log/metric trong `run` |

**Hai giao diện không tạo hai cơ chế đo lường khác nhau.** Mỗi `run` là một đoạn mã có thể được bao bởi logic chung: bắt đầu timer, log, chạy nghiệp vụ, ghi kết quả hoặc lỗi, và kết thúc timer.

### 2.2. Thứ tự giữa nhiều runner

Nếu ứng dụng có nhiều bean runner, Spring Boot hỗ trợ `Ordered` hoặc `@Order`. Giá trị order **nhỏ hơn** có độ ưu tiên cao hơn. Khi thứ tự quyết định nghiệp vụ, hãy khai báo rõ ràng thay vì phụ thuộc tên class, thứ tự tạo bean hoặc thứ tự component scan.

Ví dụ:

~~~java
@Component
@Order(10)
class ImportRunner implements ApplicationRunner { /* ... */ }

@Component
@Order(20)
class SummaryRunner implements CommandLineRunner { /* ... */ }
~~~

Ở đây `ImportRunner` được kỳ vọng chạy trước `SummaryRunner` khi cả hai được chọn trong cùng ứng dụng. Nếu `ImportRunner.run` ném exception không được xử lý, Spring Boot không tiếp tục chạy `SummaryRunner` như thể không có lỗi. Khi làm dashboard, phải phân biệt:

- `NOT_STARTED`: chưa được gọi, không có số đo thời gian thực thi runner.
- `SUCCEEDED`: đã bắt đầu và kết thúc bình thường.
- `FAILED`: đã bắt đầu nhưng ném exception.
- `UNKNOWN`: có dấu hiệu bắt đầu nhưng không có kết thúc; JVM có thể bị kill hoặc log/telemetry bị mất.

Những trạng thái trên là **quy ước quan sát tự thiết kế**, không phải enum mặc định của Spring Cloud Task.

## 3. Bốn lớp bằng chứng cần thu thập

Một hệ thống thực tế nên quan sát ít nhất bốn lớp:

| Lớp | Thông tin tiêu biểu | Nguồn |
| --- | --- | --- |
| **Runner** | `runner.start`, `runner.finish`, `runner.failure`; thời gian, số bản ghi | Log, Micrometer Timer và các metric nghiệp vụ |
| **Spring Cloud Task** | `executionId`, `taskName`, `startTime`, `endTime`, `exitCode`, `exitMessage`, `errorMessage` | `TaskExecutionListener`, `TaskRepository` |
| **Runtime / scheduler** | Thời điểm launch, PID/Pod/Job, OOM, timeout, exit code hệ điều hành | Kubernetes, SCDF, scheduler hoặc process supervisor |
| **Kết quả nghiệp vụ** | Record/file đã ghi, checksum, số bản ghi đã commit, business key | Database nghiệp vụ, object storage, hệ thống đích |

Các lớp trả lời **những câu hỏi khác nhau**. Chẳng hạn, log `runner.finish outcome=success` cho biết mã runner đi đến nhánh hoàn tất, nhưng không tự bảo đảm database chứa kết quả đúng. Tương tự, `TaskExecution` có thể đánh dấu lỗi sau khi báo cáo đã được commit vì bước cập nhật metadata hoặc hậu xử lý thất bại.

Vì vậy cần **correlation ID**: một `runId` do scheduler hoặc API tạo **trước khi khởi chạy JVM** và được truyền vào ứng dụng. Nếu một yêu cầu được retry, có thể giữ một `requestId`/business key ổn định và cấp thêm `attemptId` riêng để nhận diện từng lần thử. `TASK_EXECUTION_ID` không được xem là khóa nghiệp vụ vì có thể chưa tồn tại khi lỗi bootstrap xảy ra.

## 4. Thiết kế log có cấu trúc cho runner

### 4.1. Những trường nên có

Một log vòng đời runner nên cung cấp ít nhất:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| `event` | `runner.start` / `runner.finish` / `runner.failure` | Phân loại sự kiện |
| `runId` | `run-20261124-001` | Liên kết log của lần được điều phối |
| `runner` | `import`, `summary` | Xác định bước mã |
| `outcome` | `success`, `failure` | Kết quả thực thi bước |
| `durationMs` | `1250` | Thời gian được đo |
| `errorCode` | `INPUT_INVALID` | Nhóm lỗi ổn định, tránh phân loại theo exception text |
| `processed` / `committed` | `200` / `200` | Số liệu nghiệp vụ được đặt tên đúng |
| `taskExecutionId` | `502` nếu có | Liên kết bản ghi Spring Cloud Task |

Ví dụ một chuỗi log:

~~~text
event=runner.start runner=import runId=run-20261124-001
event=runner.finish runner=import outcome=success durationMs=1250 runId=run-20261124-001
event=runner.start runner=summary runId=run-20261124-001
event=runner.finish runner=summary outcome=success durationMs=47 runId=run-20261124-001
~~~

Đây là ví dụ diễn giải, không phải format log bắt buộc của Spring Boot. Khi dùng hệ thống thu thập log tập trung, nên xuất JSON hoặc các trường có thể parse bằng pipeline phù hợp thay vì phụ thuộc vào một chuỗi text không ổn định.

### 4.2. Không ghi thông tin nhạy cảm

`ApplicationArguments` và `String... args` có thể chứa token, mật khẩu hoặc thông tin khách hàng nếu người vận hành truyền sai cách. **Không log toàn bộ `args` mặc định.** Chỉ log các trường đã được phép, hoặc dùng `runId` để tra cứu thông tin cần thiết trong hệ thống điều phối có phân quyền.

Không đưa `runId`, user ID, mã đơn hàng hay ngày giao dịch vào **metric tags** nếu chúng tạo cardinality tăng liên tục. Đó là dữ liệu phù hợp cho log/trace, không phù hợp cho nhãn của mọi timeseries.

## 5. Ví dụ thực hành: đo hai loại runner trong cùng một task

Ví dụ dùng Spring Boot 3.x, Java 17+, Spring Cloud Task tương thích và Micrometer. Khi chạy:

~~~bash
java -jar runner-observation.jar   --runId=run-20261124-001 --businessDate=2026-11-24
~~~

hai runner thực thi theo thứ tự: `ImportRunner` rồi `SummaryRunner`. Một cờ `--fail` cho phép thử lỗi tại runner đầu để kiểm tra hành vi của runner sau và `TaskExecution`.

### 5.1. Dependency Maven

Dự án dùng Spring Boot parent/BOM và Spring Cloud BOM **đúng release train tương thích**. Các dependency cần thiết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
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
</dependencies>
~~~

Bổ sung `spring-boot-maven-plugin` trong `build` để tạo JAR thực thi. `spring-boot-starter-actuator` cung cấp hạ tầng Micrometer/MeterRegistry theo auto-configuration thích hợp; có meter được ghi nhận trong JVM **không đồng nghĩa** đã có exporter bền vững.

### 5.2. Java: ApplicationRunner, CommandLineRunner và Timer

Tạo `src/main/java/com/example/task/RunnerObservationApplication.java`:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerObservationApplication {

    private static final Logger log =
            LoggerFactory.getLogger(RunnerObservationApplication.class);

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(RunnerObservationApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Component
    @Order(10)
    static class ImportRunner implements ApplicationRunner {
        private final MeterRegistry meters;

        ImportRunner(MeterRegistry meters) {
            this.meters = meters;
        }

        @Override
        public void run(ApplicationArguments args) throws Exception {
            String runId = requiredOption(args, "runId");

            observe("import", runId, meters, () -> {
                LocalDate businessDate = LocalDate.parse(
                        requiredOption(args, "businessDate"));

                log.info("import.business_date date={}", businessDate);

                if (args.containsOption("fail")) {
                    throw new IllegalStateException(
                            "DEMO_IMPORT_FAILURE");
                }

                // Demo: trong production hãy gọi service có transaction.
                log.info("import.processed processedRows={}", 3);
            });
        }
    }

    @Component
    @Order(20)
    static class SummaryRunner implements CommandLineRunner {
        private final MeterRegistry meters;

        SummaryRunner(MeterRegistry meters) {
            this.meters = meters;
        }

        @Override
        public void run(String... args) throws Exception {
            // CommandLineRunner nhận tham số raw nên phải tự parse.
            String runId = rawOption(args, "runId");

            observe("summary", runId, meters, () -> {
                log.info("summary.completed result=READY");
            });
        }
    }

    @FunctionalInterface
    interface CheckedWork {
        void execute() throws Exception;
    }

    static void observe(
            String runnerName,
            String runId,
            MeterRegistry meters,
            CheckedWork work) throws Exception {

        long startNanos = System.nanoTime();
        String outcome = "success";

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("runId", runId)) {
            log.info("runner.start runner={}", runnerName);

            try {
                work.execute();
            } catch (Exception | Error failure) {
                outcome = "failure";
                log.error("runner.failure runner={}", runnerName, failure);
                throw failure;
            } finally {
                long elapsedNanos = System.nanoTime() - startNanos;
                long elapsedMs =
                        TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

                log.info("runner.finish runner={} outcome={} durationMs={}",
                        runnerName, outcome, elapsedMs);

                // Telemetry không được che mất lỗi nghiệp vụ.
                try {
                    Timer.builder("task.runner.duration")
                            .description("Thời gian thực thi từng runner")
                            .tag("runner", runnerName)
                            .tag("outcome", outcome)
                            .register(meters)
                            .record(elapsedNanos, TimeUnit.NANOSECONDS);
                } catch (RuntimeException metricFailure) {
                    log.warn("runner.metric_record_failed runner={}",
                            runnerName, metricFailure);
                }
            }
        }
    }

    static String requiredOption(ApplicationArguments args,
                                 String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Phải truyền một --" + name + "=<giá trị>");
        }
        return values.get(0).trim();
    }

    static String rawOption(String[] args, String name) {
        String prefix = "--" + name + "=";
        List<String> values = Arrays.stream(args)
                .filter(s -> s.startsWith(prefix))
                .map(s -> s.substring(prefix.length()))
                .toList();

        if (values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Phải truyền một --" + name + "=<giá trị>");
        }
        return values.get(0).trim();
    }

    @Bean
    TaskExecutionListener taskLifecycleLogger() {
        return new TaskExecutionListener() {
            @Override
            public void onTaskStartup(TaskExecution execution) {
                log.info("task.lifecycle event=start executionId={} taskName={}",
                        execution.getExecutionId(),
                        execution.getTaskName());
            }

            @Override
            public void onTaskFailed(TaskExecution execution,
                                     Throwable cause) {
                log.error("task.lifecycle event=failure executionId={}",
                        execution.getExecutionId(), cause);
            }

            @Override
            public void onTaskEnd(TaskExecution execution) {
                log.info("task.lifecycle event=end executionId={} exitCode={}",
                        execution.getExecutionId(),
                        execution.getExitCode());
            }
        };
    }
}
~~~

Ví dụ cố ý **không gọi lại `TaskRepository` trong từng runner**. Spring Cloud Task phụ trách metadata vòng đời; `observe(...)` phụ trách đo đoạn mã runner. `TaskExecutionListener` chỉ quan sát các mốc có thể nhận được từ framework.

**Giới hạn của ví dụ:** phương thức `requiredOption` được gọi **trước** `observe(...)` để lấy `runId`. Nếu `--runId` thiếu hoặc sai, lỗi xảy ra trước khi timer của runner được bắt đầu; log và `TaskExecutionListener` (khi hoạt động) vẫn có thể cung cấp thông tin. Ở sản phẩm thực tế, có thể thêm một tầng validation riêng có metric để phát hiện lỗi cấu hình đầu vào.

### 5.3. Cấu hình application.yml

~~~yaml
spring:
  application:
    name: runner-observation
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./runner-observation-db
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: runner-observation
      initialize-enabled: true

logging:
  pattern:
    console: '%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [runId=%X{runId:-none}] %logger{36} - %msg%n'
~~~

- `web-application-type: none` giúp ứng dụng không tạo web server chỉ để chạy một tác vụ hữu hạn.
- H2 `file:` cho phép xem metadata sau khi JVM dừng; khác với `jdbc:h2:mem:...` vốn mất dữ liệu khi process kết thúc. Khi truy vấn từ công cụ H2, phải dùng đúng đường dẫn database và tránh mở file đồng thời theo chế độ không được hỗ trợ.
- `initialize-enabled: true` chỉ thuận tiện cho bài thử nghiệm khi phiên bản Spring Cloud Task hỗ trợ schema H2; production nên dùng database bền vững được quản lý migration.
- `%X{runId:-none}` lấy `runId` từ SLF4J MDC của thread runner. MDC không tự lan sang các thread khác hoặc callback chạy ở một ngữ cảnh khác.
- `Timer` do Micrometer giữ trong registry, nhưng cấu hình trên **chưa xuất metrics sang hệ thống giám sát ngoài JVM**. Log duration vẫn hữu ích khi tập trung log.

### 5.4. Chạy hai tình huống

Đóng gói và chạy thành công:

~~~bash
./mvnw clean package
java -jar target/runner-observation-0.0.1-SNAPSHOT.jar   --runId=run-20261124-001 --businessDate=2026-11-24
~~~

Tên JAR chỉ là ví dụ; dùng artifact thực tế từ Maven. Trên Windows PowerShell, dùng `mvnw.cmd clean package` và có thể nhập lệnh `java -jar` trên một dòng.

Log sẽ có những sự kiện tương tự:

~~~text
task.lifecycle event=start executionId=101 taskName=runner-observation
runner.start runner=import
import.business_date date=2026-11-24
import.processed processedRows=3
runner.finish runner=import outcome=success durationMs=...
runner.start runner=summary
summary.completed result=READY
runner.finish runner=summary outcome=success durationMs=...
task.lifecycle event=end executionId=101 exitCode=...
~~~

`durationMs`, `executionId` và các giá trị liên quan do lần chạy thực tế quyết định. Trong log thật, `runId` được in ở prefix của những dòng do runner ghi trong scope MDC.

Chạy lỗi có chủ đích:

~~~bash
java -jar target/runner-observation-0.0.1-SNAPSHOT.jar   --runId=run-20261124-002 --businessDate=2026-11-24 --fail
~~~

Khi `ImportRunner` ném exception, kỳ vọng thấy `runner.failure runner=import`, `runner.finish outcome=failure` và callback lỗi từ Spring Cloud Task **nếu context/repository hoạt động đủ để ghi nhận**. `SummaryRunner` không được tiếp tục gọi theo đường thực thi bình thường; vì vậy **không có `runner.start runner=summary`** trong lần chạy lỗi này.

Nếu chỉ nhìn `runner.summary.duration` không có điểm dữ liệu, đừng tự kết luận SummaryRunner chạy quá nhanh: nó có thể **chưa từng được gọi**.

## 6. TaskExecutionListener quan sát toàn task, không chỉ một runner

Spring Cloud Task có `TaskExecutionListener` với ba callback:

| Callback | Thời điểm theo tài liệu | Cần hiểu đúng |
| --- | --- | --- |
| `onTaskStartup(TaskExecution)` | **Trước khi lưu** metadata ban đầu vào repository | Có callback/log khởi động không bảo đảm record đã commit |
| `onTaskFailed(TaskExecution, Throwable)` | Khi task có exception chưa xử lý, **trước** callback kết thúc | Có thể biết nguyên nhân lỗi nếu framework quan sát được |
| `onTaskEnd(TaskExecution)` | **Trước khi cập nhật** metadata kết thúc vào repository | Có callback kết thúc không bảo đảm thao tác JDBC cuối đã thành công |

Tài liệu cũng cung cấp annotation `@BeforeTask`, `@FailedTask`, `@AfterTask` khi muốn dùng phương thức có annotation thay cho interface.

~~~java
@Component
class TaskAuditHooks {

    private static final Logger log =
            LoggerFactory.getLogger(TaskAuditHooks.class);

    @BeforeTask
    public void start(TaskExecution execution) {
        log.info("task.audit.start id={}",
                execution.getExecutionId());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable error) {
        log.error("task.audit.failure id={}",
                execution.getExecutionId(), error);
    }

    @AfterTask
    public void end(TaskExecution execution) {
        log.info("task.audit.end id={}",
                execution.getExecutionId());
    }
}
~~~

Đoạn này minh họa **phương án thay thế** listener bean ở mục 5.2, không nên dùng đồng thời cả hai chỉ để log lặp. Khi tách file, cần import `Component`, `Logger`, `LoggerFactory`, `TaskExecution` và ba annotation từ package listener annotation tương ứng của Spring Cloud Task theo phiên bản đang dùng.

### Khi nào nên dùng listener, khi nào nên bọc runner?

- **Listener:** ghi nhận bắt đầu/kết thúc/thất bại của **task tổng thể**, gắn `executionId` khi có, tạo exit message ngắn hoặc tích hợp audit nhẹ.
- **Wrapper quanh runner:** đo riêng **đoạn nghiệp vụ**, phân biệt runner nào đã chạy và thời gian thực tế của nó.
- **Service instrumentation:** đo từng giai đoạn chi tiết như đọc file, gọi HTTP, ghi database, kiểm tra số hàng đã commit.

Không đẩy tác vụ mạng chậm, truy vấn nặng hoặc logic nghiệp vụ mới vào listener phục vụ quan sát. Một listener ném exception có thể ảnh hưởng đến chuỗi callback và kết quả task; observability cần hoạt động **theo khả năng tốt nhất** và không làm thay đổi nghiệp vụ một cách không mong muốn.

## 7. Đo thời gian đúng và chọn metric thích hợp

### 7.1. Vì sao dùng System.nanoTime()?

`System.nanoTime()` cung cấp thời gian đơn điệu tương đối để đo **elapsed duration**; nó phù hợp hơn việc trừ các timestamp đồng hồ tường (`LocalDateTime.now()`) khi đồng hồ hệ thống bị điều chỉnh. Nó **không** là Unix timestamp để hiển thị giờ bắt đầu.

Ví dụ:

~~~java
long started = System.nanoTime();
try {
    process();
} finally {
    long elapsed = System.nanoTime() - started;
    log.info("elapsedMs={}",
            TimeUnit.NANOSECONDS.toMillis(elapsed));
}
~~~

Với độ dài task, có thể đo thêm tổng thời gian scheduler thấy từ lúc yêu cầu launch đến khi process kết thúc. Giá trị này bao gồm **xếp lịch, tải image, JVM bootstrap và thời gian chờ**, nên không đồng nhất với timer của `ApplicationRunner`.

### 7.2. Micrometer Timer đo gì?

Trong ví dụ, meter có tên:

~~~text
task.runner.duration
~~~

và hai nhãn cardinality thấp:

~~~text
runner=import|summary
outcome=success|failure
~~~

`Timer` tích lũy số lần đo và thời gian của các lần gọi (và có thể có cấu hình histogram/phân vị). Khi xuất sang Prometheus, tên series có thể được chuyển đổi theo convention của registry; không mặc định metric tên nguyên văn `task.runner.duration` luôn xuất hiện trên Prometheus.

Nên dùng:

| Loại metric | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Timer` | `task.runner.duration` | Thời lượng từng runner |
| `Counter` | `task.runner.failures` | Số lần lỗi, nếu cần thống kê riêng |
| `DistributionSummary` | `task.records.committed` | Phân bố số record thực sự commit mỗi attempt |
| Gauge | Số job đang chạy trong **bộ điều phối lâu dài** | Trạng thái active theo thời điểm |

**Không dùng Gauge trong JVM của một task rất ngắn** làm nguồn duy nhất để biết số Job đang chạy trên cluster. Khi JVM thoát, Gauge cũng biến mất cùng registry; trạng thái active cần được lấy từ scheduler hoặc collector lâu dài.

### 7.3. Thẻ metric nên có giới hạn

Nên gắn nhãn `runner`, `outcome` hoặc `taskType` khi số giá trị cố định và ít. Tránh `runId`, `taskExecutionId`, `orderId`, user ID hoặc timestamp vì mỗi lần chạy sẽ tạo series mới, gây **high cardinality** và chi phí lưu trữ lớn.

Sử dụng ID chi tiết trong **log** và **trace span**, nơi có công cụ tìm kiếm thích hợp; không đưa chúng thành label trên mọi timeseries.

## 8. Tại sao metrics của task ngắn hạn dễ bị mất?

Ứng dụng web chạy hàng giờ có thể cho Prometheus scrape `/actuator/prometheus` định kỳ. Nhưng một Spring Cloud Task có thể chạy **vài trăm mili-giây hoặc vài giây** rồi JVM thoát. Nếu Prometheus chỉ scrape mỗi 15–30 giây, nhiều lần chạy sẽ **không có lúc nào có endpoint còn sống để scrape**.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant T as Task JVM
    participant P as Metrics collector
    S->>T: Bắt đầu task 12:00:01
    T->>T: Runner ghi Timer 12:00:02
    T--xS: JVM kết thúc 12:00:03
    P->>T: Scrape lúc 12:00:15
    Note over P,T: Task đã thoát; không còn endpoint/registry
~~~

Ngay cả khi có `spring-boot-starter-actuator`:

- Nếu `spring.main.web-application-type=none`, không có HTTP actuator server để Prometheus truy vấn như ứng dụng web.
- Không phải metrics nào ghi vào registry cũng được gửi ra ngoài; một exporter không được cấu hình thì dữ liệu chỉ nằm trong JVM.
- Registry có chu kỳ publish có thể chưa tới lần xuất đầu trước khi JVM dừng.
- Việc tắt process ngay lập tức, lỗi khởi tạo sớm hoặc `SIGKILL` có thể ngăn exporter flush dữ liệu.

### Các lựa chọn phù hợp hơn

1. **Structured logs tập trung:** mỗi runner phát log bắt đầu/kết thúc/lỗi và duration; scheduler lưu exit code. Phù hợp làm nguồn tối thiểu cho task rất ngắn.
2. **Metrics push/OTLP exporter được cấu hình đúng:** collector thu nhận trước khi process thoát; cần kiểm tra shutdown/flush, timeout, retry và giới hạn xuất dữ liệu theo phiên bản.
3. **Exporter hoặc hệ thống điều phối chạy lâu dài:** tổng hợp số lần chạy/thất bại và thời gian từ Job/TaskRepository/log thay vì trông chờ scrape từng JVM ngắn hạn.
4. **Pushgateway nếu kiến trúc Prometheus thực sự cần:** phải quy hoạch grouping key và xóa stale metrics. Không coi Pushgateway là kho lịch sử mỗi `runId` và không lạm dụng label có cardinality cao.

Không có giải pháp export nào làm cho dữ liệu **được bảo đảm 100%** khi tiến trình bị kill cưỡng bức hoặc mất mạng đúng lúc flush. Vì vậy, đừng dùng một nguồn metric in-memory để chứng minh task nghiệp vụ hoàn tất.

## 9. Quan sát exception và không che lỗi ban đầu

Một lỗi phổ biến là bắt mọi exception trong runner chỉ để ghi log rồi kết thúc bình thường:

~~~java
try {
    importService.execute();
} catch (Exception e) {
    log.error("Import failed", e);
    // Sai nếu đây là lỗi phải khiến task thất bại:
    // runner tiếp tục và không báo lỗi.
}
~~~

Nếu nghiệp vụ thất bại, phải để hạ tầng điều phối nhận tín hiệu thất bại đúng cách:

~~~java
try {
    importService.execute();
} catch (Exception e) {
    log.error("Import failed; code=IMPORT_ERROR", e);
    throw e;
}
~~~

Hai đoạn trên giả định `importService` và `log` đã được định nghĩa. Nếu lỗi có thể được xử lý hoàn toàn và kết quả đã được xác minh, service có thể trả lại một kết quả thành công có kiểm soát; nhưng **không được “nuốt” lỗi chỉ để log đẹp**.

Trong ví dụ chính, helper `observe`:

1. Log `runner.start` trước khi gọi nghiệp vụ.
2. Khi có lỗi, gán `outcome=failure`, log stack trace và **ném lại**.
3. Luôn ghi `runner.finish` trong `finally` nếu JVM còn chạy.
4. Đo duration cả khi success hoặc failure.
5. Bọc việc ghi metric để lỗi telemetry không thay thế lỗi nghiệp vụ.

**Không nên log cùng stack trace quá nhiều lần ở mỗi layer** nếu hệ thống có log tập trung; có thể log mã lỗi ở runner và stack trace tại điểm ranh giới được chọn. Ví dụ logging nhiều lớp ở đây nhằm minh họa nguồn dữ liệu quan sát, không bắt buộc production in trùng cùng exception.

## 10. Giới hạn khi ApplicationContext khởi tạo thất bại

Mọi mã nằm bên trong `ApplicationRunner.run` và `CommandLineRunner.run` chỉ hoạt động **nếu Spring Boot đã đi tới giai đoạn gọi runner**. Khi lỗi xảy ra sớm hơn:

- Thiếu class hoặc main method sai: JVM có thể chưa tạo Spring context.
- Sai profile, sai YAML, thiếu secret, lỗi tạo bean: context có thể thất bại trước khi gọi runner.
- Không tạo được `DataSource` hoặc schema `TASK_EXECUTION`: repository có thể chưa sẵn sàng.
- Lỗi tạo bean runner: object runner thậm chí chưa được tạo để bắt đầu đo.

Trong các trường hợp này, **không có `runner.start` không chứng minh rằng launcher chưa cố khởi chạy**. Nguồn bằng chứng phải nằm **bên ngoài ứng dụng**: trạng thái Kubernetes Job/Pod, exit code, stderr/bootstrap log của JVM và bản ghi yêu cầu từ scheduler.

Một `ApplicationFailedEvent`/listener Spring Boot đăng ký sớm có thể bổ sung log nếu tiến trình còn đủ khả năng phát sự kiện, nhưng nó không thể xử lý tình huống JVM chưa khởi động hoặc bị `SIGKILL`. Không hứa hẹn log cuối cho mọi dạng crash.

## 11. Đối soát TaskRepository với log runner

Khi dùng một database JDBC lưu bền vững và schema Spring Cloud Task phù hợp, có thể tra cứu:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'runner-observation'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Nên kết hợp với log có `runId` để trả lời:

- Đã có `runner.start` của runner nào?
- Runner nào có `runner.finish`? Outcome và thời lượng của từng runner?
- `TaskExecution` có `END_TIME` và `EXIT_CODE` chưa?
- Container/process có thực sự dừng, vì lý do gì?
- Kết quả nghiệp vụ đã commit/được publish đúng chưa?

| Tình huống | Log runner | TaskRepository | Kết luận vận hành |
| --- | --- | --- | --- |
| Hai runner chạy xong | Hai cặp `start/finish success` | Thường có `END_TIME` và mã thành công nếu ghi được | Kiểm tra thêm đầu ra nghiệp vụ |
| Runner đầu ném exception | `import.failure`, không có `summary.start` | Có thể ghi lỗi nếu hạ tầng sẵn sàng | Thất bại; không coi runner sau có duration 0 |
| Context lỗi sớm | Không có log runner | Có thể không có record | Xem log khởi động và runtime |
| JVM bị kill trong runner | Có `start` nhưng không có `finish` | Có thể thiếu `END_TIME` | UNKNOWN/FAILED theo runtime; đối soát dữ liệu |
| Database metadata mất kết nối | Runner có thể hoàn tất | Record thiếu/cập nhật cuối lỗi | So sánh runtime và output, không suy ra rollback |
| Lỗi xuất telemetry | Runner vẫn chạy, có warning metrics | Tùy kết quả nghiệp vụ và repository | Khắc phục exporter, không thay đổi kết quả nghiệp vụ giả tạo |

**Không nên sửa trực tiếp `TASK_EXECUTION.EXIT_CODE` hoặc `END_TIME` chỉ để dashboard trông “đã hoàn tất”**. Giữ bằng chứng lịch sử và ghi nhận kết quả đối soát ở hệ thống điều phối hoặc bảng audit riêng.

## 12. Tracing: quan sát một lần chạy nhiều bước

Nếu hệ thống có tracing phân tán, một runner có thể tạo span cho các bước như `read-source`, `transform`, `write-target`. Trace giúp nhìn chuỗi phụ thuộc và độ trễ giữa những lời gọi, nhất là khi task gọi API hoặc message broker.

Ví dụ phân tách:

~~~text
requestId=REQ-017
  └─ task attempt / JVM
      ├─ import runner
      │   ├─ read-source
      │   └─ write-database
      └─ summary runner
          └─ publish-report
~~~

Cần hiểu rõ:

- `runId` trong log là **correlation ID nghiệp vụ/điều phối**; nó không tự biến thành OpenTelemetry trace ID.
- Truyền trace context từ launcher/API tới một JVM mới thường đòi hỏi cấu hình **propagation rõ ràng** (chẳng hạn trace context qua message headers hoặc môi trường được kiểm soát). Không mặc định `traceparent` sẽ đi qua mọi loại launcher.
- Với task ngắn hạn, collector/exporter cần khả năng **flush** trước khi JVM đóng; span có thể bị mất nếu process bị kill.
- Có thể dùng sampling, nhưng không nên loại toàn bộ trace của task lỗi nếu cần điều tra; quy tắc sampling phải phù hợp chi phí và nhu cầu.
- Không dùng trace/span ID như nhãn metric cardinality cao.

Khi chưa có tracing, **structured log + runId + TaskRepository + trạng thái scheduler** vẫn là nền tảng quan sát đáng tin cậy hơn việc triển khai tracing phức tạp nhưng không xuất được dữ liệu.

## 13. Metrics và kết quả nghiệp vụ phải thống nhất

Một tác vụ import có thể in “Processed 10.000 rows” nhưng chỉ commit được 9.000. Để tránh dashboard báo thành công sai, nên đặt tên metric theo **cái thực sự được đo**:

| Chỉ số | Ý nghĩa đúng |
| --- | --- |
| `records.read` | Số record reader đã lấy |
| `records.validated` | Số record được validation chấp nhận |
| `records.attempted_write` | Số record đã thử đưa vào writer |
| `records.committed` | Số record đã xác nhận commit |
| `records.skipped` | Số record bỏ qua có chủ đích |
| `runner.duration` | Thời gian mã runner chạy, không gồm toàn bộ thời gian scheduler chờ |
| `launch_to_finish.duration` | Từ lúc điều phối yêu cầu chạy đến khi runtime kết thúc |

Các tên trên là **quy ước quan sát ví dụ**, không phải các meter mặc định Spring Cloud Task bắt buộc có.

Với JDBC, kết quả commit không rõ khi kết nối rớt là trạng thái **UNKNOWN** cho đến khi đọc lại database nghiệp vụ theo business key. Đừng cộng `records.committed` ngay sau khi gửi lệnh ghi mà chưa xác nhận commit, và đừng tự động cộng lần nữa khi retry nếu record đã tồn tại.

Nếu chạy Spring Batch, `StepExecution` có `readCount`, `writeCount`, `skipCount` và trạng thái step. Chúng có thể rất hữu ích, nhưng không thay thế tính nhất quán của hệ thống đích và việc đối soát các tác động bên ngoài transaction.

## 14. Những lỗi quan sát thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Có log khởi động Task nhưng không có log runner | Context lỗi trước runner hoặc bean runner không được đăng ký | Xem log bootstrap, kiểm tra bean và `ApplicationFailedEvent` |
| Chỉ có log ImportRunner, không có SummaryRunner | Runner đầu ném exception hoặc thứ tự gọi không như mong muốn | Xem `@Order`, exception, stack trace |
| Có `runner.start` nhưng không có `runner.finish` | JVM bị kill, mất log, lỗi cực sớm hoặc tiến trình vẫn chạy | Kiểm tra Pod/process, deadline, OOM, log backend |
| Có duration trong log, nhưng Prometheus không có metric | Registry chưa được export, task quá ngắn, không có endpoint, scrape trễ | Xem cấu hình exporter, telemetry collector và thời gian sống |
| Metrics bị bùng số series | Gắn `runId`/order ID/timestamp vào label | Đưa ID sang logs/tracing, giảm tags |
| `TaskExecution.END_TIME IS NULL` | Task đang chạy hoặc repository không cập nhật được sau crash | Đối chiếu scheduler/runtime và timeout |
| `exitCode=0` nhưng không có đầu ra nghiệp vụ | Runner báo thành công sai hoặc không xác minh commit | Kiểm tra service, business key, writer |
| Nhiều attempt cùng runId | Scheduler retry hoặc chạy chồng | Phân biệt requestId/attemptId và idempotency |
| Log không có runId ở async worker | MDC chỉ gắn với thread hiện tại | Truyền context rõ ràng qua executor hoặc task decorator |
| Metrics success có nhưng task thất bại | Runner đã success, lỗi xảy ra ở runner khác hoặc lúc kết thúc | So sánh TaskExecution và toàn bộ các runner |

## 15. Kế hoạch kiểm thử observability

Một bộ kiểm thử nên bao gồm:

1. **Thành công:** cả hai runner có `start` và `finish success`; `TaskExecution` kết thúc đúng; output nghiệp vụ hợp lệ.
2. **Lỗi runner đầu:** ImportRunner có `failure`, SummaryRunner không bắt đầu; runtime/Task báo thất bại.
3. **Lỗi tham số:** thiếu hoặc sai `--runId`, `--businessDate`; quan sát có log bootstrap/Task và xác định phần instrumentation chưa chạy.
4. **Lỗi tạo bean:** mô phỏng bean ném exception trong lúc khởi tạo context; runner metric có thể hoàn toàn vắng mặt.
5. **Dừng cưỡng bức:** trong test, kill JVM khi runner đang xử lý; kiểm tra log/metadata thiếu và nguồn giám sát ngoài.
6. **Database metadata lỗi:** task có thể không tạo/cập nhật `TaskExecution`; phải có log/runtime để điều tra.
7. **Exporter chậm hoặc không truy cập được:** runner vẫn thể hiện kết quả nghiệp vụ chính xác; không để telemetry gây thất bại giả.
8. **Nhiều attempt:** cùng business key nhưng attempt khác nhau; log/TaskExecution được nối bằng requestId và không ghi trùng dữ liệu.
9. **Metrics cardinality:** kiểm tra labels chỉ dùng giá trị hữu hạn và không chứa ID duy nhất của từng attempt.
10. **Security:** không có secret/PII trong log, metric tags, trace attributes hoặc metadata Task được phép truy vấn rộng.

Trên staging, có thể so sánh thời gian runner với thời gian tổng của Task và thời gian launcher đo được. Chênh lệch thường do bootstrap, repository, I/O, scheduling, xuất telemetry hoặc đóng tài nguyên. **Không ép ba giá trị phải bằng nhau**.

## 16. Bài tập và câu hỏi tự kiểm tra

**Câu hỏi 1.** `ApplicationRunner` khác `CommandLineRunner` ở loại tham số thế nào? Nếu cả hai có `@Order`, Spring Boot gọi theo nguyên tắc gì?

**Câu hỏi 2.** Khi ImportRunner thất bại và SummaryRunner chưa được gọi, tại sao không nên ghi duration của SummaryRunner là `0 ms`?

**Câu hỏi 3.** `onTaskStartup` và `onTaskEnd` trong `TaskExecutionListener` được gọi trước hay sau thao tác lưu/cập nhật `TaskRepository`? Vì sao cần biết điều đó khi phân tích log?

**Câu hỏi 4.** Vì sao một ứng dụng Spring Cloud Task chạy 2 giây có thể ghi Micrometer Timer nhưng Prometheus không thu được gì từ `/actuator/prometheus`?

**Câu hỏi 5.** Có nên gắn `runId`, `businessDate` và `taskExecutionId` lên mọi metric hay không? Nên đặt chúng ở đâu?

**Câu hỏi 6.** Nếu `runner.finish outcome=success` nhưng `TaskExecution.EXIT_CODE=1`, bạn sẽ tra cứu theo thứ tự nào để tìm lỗi?

**Bài tập A — Log có runId.** Mở rộng ví dụ để thêm `requestId` và `attemptId`, ghi rõ mối quan hệ giữa một yêu cầu nghiệp vụ và nhiều `TaskExecution`.

**Bài tập B — Thử lỗi thứ tự.** Đảo `@Order` của hai runner rồi chạy có `--fail`; giải thích tại sao lựa chọn thứ tự có thể làm thay đổi kết quả nghiệp vụ, số log và metric.

**Bài tập C — Xuất telemetry.** Chọn một exporter/collector dùng được với task ngắn hạn trong môi trường thử nghiệm. Kiểm tra dữ liệu sau khi JVM thoát và mô phỏng trường hợp collector mất kết nối. Ghi rõ giới hạn về flush và sampling.

**Bài tập D — Đối soát.** Dùng database H2 file hoặc PostgreSQL bền vững, chạy thành công rồi chạy lỗi. Truy vấn `TASK_EXECUTION`, đối chiếu log của hai runner và exit code hệ điều hành.

**Bài tập E — Spring Batch.** Thay ImportRunner bằng thao tác khởi động Spring Batch Job. So sánh `TaskExecution`, `JobExecution`, `StepExecution` và các chỉ số nghiệp vụ đã commit.

## 17. Ghi nhớ

- **`ApplicationRunner` và `CommandLineRunner` đều chạy trong giai đoạn cuối của Spring Boot startup**, nhưng nhận kiểu tham số khác nhau; dùng `@Order`/`Ordered` nếu cần quy định trình tự.
- **Đo runner riêng** bằng log và Timer để biết bước nào đã bắt đầu, hoàn tất hay lỗi; `TaskExecution` theo dõi **cả lần thực thi task**.
- `TaskExecutionListener` có callback `onTaskStartup`, `onTaskFailed` và `onTaskEnd`. Các callback trước khi repository ghi/cập nhật không tự chứng minh thao tác JDBC đã commit.
- **Structured log có runId**, metric tags có cardinality thấp và một nguồn quan sát từ scheduler/runtime là nền tảng quan trọng với tác vụ ngắn hạn.
- **Micrometer registry trong JVM không tự bảo đảm metrics được xuất sau khi task thoát**. Cần thiết kế collector/exporter phù hợp và hiểu giới hạn flush khi crash.
- **Không có `runner.start` hoặc thiếu `TaskExecution` không chứng minh task chưa từng được khởi chạy**; lỗi khởi tạo sớm và crash phải được phát hiện từ bên ngoài.
- Thành công kỹ thuật phải được đối chiếu **kết quả nghiệp vụ đã commit**, đặc biệt khi retry, mất kết nối hoặc phối hợp Spring Batch.

## Tài liệu tham khảo

- [Spring Boot Reference — SpringApplication, ApplicationRunner và CommandLineRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html): thời điểm runner được gọi, tham số và `@Order`.
- [Spring Cloud Task Reference — Features và Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/features.html): vòng đời `TaskExecution` và thời điểm gọi listener so với `TaskRepository`.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, meter registry và cấu hình xuất metrics.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): API `Timer` và phép đo thời lượng.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): trace/span, context propagation và cấu hình tracing.

Khi sử dụng cho production, hãy đối chiếu các API và cách cấu hình với **đúng phiên bản Spring Boot, Spring Cloud Task, Micrometer, exporter và hệ điều phối** của dự án; ví dụ log, metric, JAR và database ở đây có tính minh họa và không thay thế kiểm thử tích hợp.
