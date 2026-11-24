# Triển khai Kubernetes Job hoặc CronJob và quan sát kết quả

## 1. Mục tiêu bài thực hành

Trong **Spring Cloud Task**, một ứng dụng Spring Boot được thiết kế để chạy trong thời gian hữu hạn, thực hiện công việc và kết thúc. Spring Cloud Task ghi nhận mỗi lần thực thi bằng một `TaskExecution` trong `TaskRepository`: ID, tên task, thời điểm bắt đầu/kết thúc, exit code và các tham số. Kubernetes có hai loại workload phù hợp để triển khai:

- **Job**: yêu cầu Kubernetes thực hiện một công việc đến khi đạt điều kiện hoàn thành hoặc thất bại.
- **CronJob**: yêu cầu Kubernetes **tạo các Job** theo lịch; CronJob không trực tiếp chạy mã Java.

Bài thực hành sẽ xây một ứng dụng `daily-close-task` giả lập thao tác chốt doanh thu theo tenant và ngày nghiệp vụ, đóng gói container, chạy một lần bằng Job, rồi cấu hình chạy hằng ngày bằng CronJob. Mỗi lần chạy phải kiểm tra **ba lớp kết quả**: Kubernetes, Spring Cloud Task và dữ liệu thực sự đã ghi.

Sau bài này, người học có thể:

1. Viết một `ApplicationRunner` không mở web server và trả mã thoát phù hợp.
2. Chuẩn bị PostgreSQL cho `TaskRepository` và bảng kết quả có khóa idempotency.
3. Đóng gói JAR thành Docker image, truyền config bằng environment/Secret.
4. Tạo Job hoặc CronJob bằng manifest `batch/v1`, cấu hình deadline, retry, quota và lịch.
5. Dùng `kubectl` để kiểm tra Job, Pod, logs, exit code và nguyên nhân lỗi.
6. Đối chiếu `TaskExecution` với business output để phân biệt **launch thành công**, **process thành công** và **nghiệp vụ đã commit**.
7. Diễn tập retry sau khi commit, chứng minh dữ liệu không bị ghi trùng.
8. Hiểu giới hạn của `concurrencyPolicy: Forbid`, `backoffLimit` và việc tự động dọn Job.

Đây là **lab hướng dẫn**. Các code block mô tả file và lệnh cần tạo/chạy **trong dự án thực hành của người học**; bài viết không tự triển khai lên một cluster hay tạo secret thật.

## 2. Kiến trúc tổng thể và ba nguồn trạng thái

~~~mermaid
flowchart TD
    U["Người vận hành / CronJob Controller"] --> J["Kubernetes Job"]
    J --> P["Pod chạy container task"]
    P --> A["Spring Boot + Spring Cloud Task"]
    A --> R["ApplicationRunner"]
    R --> S["DailyCloseService"]
    A --> TR["PostgreSQL: TaskRepository"]
    S --> BD["PostgreSQL: daily_close_result"]
    P --> L["Pod status + container exit code + logs"]
    J --> K["Job conditions Complete / Failed"]
    TR --> Q["Tra TaskExecution"]
    BD --> Q
    K --> Q
    L --> Q
~~~

Ba loại dữ liệu phải được kiểm tra độc lập:

| Nguồn | Câu hỏi cần trả lời | Điều chưa được bảo đảm |
|---|---|---|
| Kubernetes Job / Pod | Container đã chạy chưa, kết thúc mã nào, có retry hoặc bị OOMKill không? | Dữ liệu nghiệp vụ chắc chắn đúng |
| Spring Cloud TaskRepository | Có bao nhiêu `TaskExecution`, thời gian và exit code từng lần là gì? | Side effect ngoài repository đã xử lý đúng một lần |
| Bảng kết quả nghiệp vụ | Có kết quả đúng cho tenant/ngày/revision, có trùng lặp không? | Toàn bộ hệ thống downstream đã nhận dữ liệu nếu có gọi API/message |

Ví dụ một worker có thể **commit dữ liệu rồi bị kill** trước khi TaskRepository được cập nhật trạng thái cuối. Kubernetes báo Pod Failed, TaskExecution có thể còn thiếu `END_TIME`, nhưng bảng nghiệp vụ đã có bản ghi. Nếu retry không có idempotency, kết quả sẽ bị tạo lặp.

Vì vậy bài lab cố ý cho bảng `daily_close_result` một **primary key theo business key**, không dùng `taskExecutionId` làm khóa nghiệp vụ.

## 3. Chọn Kubernetes Job hay CronJob?

| Yêu cầu | Đề xuất | Lý do |
|---|---|---|
| Chạy bù cho một ngày xác định | **Job** | Truyền `--date=yyyy-MM-dd` cố định, kiểm soát một lần chạy |
| Chạy lúc 02:00 mỗi ngày | **CronJob** | Tự tạo Job theo lịch và timezone đã khai báo |
| API nhận yêu cầu và tạo task | Job thông qua Kubernetes API hoặc task launcher | Một workload hữu hạn cho mỗi yêu cầu |
| Web server phải chạy 24/7 | Deployment / service riêng | Đây không phải mô hình task hữu hạn |
| Cần chia hàng nghìn partition | Spring Batch/remote partitioning hoặc Indexed Job nếu phù hợp | Đòi hỏi thiết kế riêng cho concurrency/checkpoint |

Đối với task hữu hạn, **không dùng Deployment chỉ để chạy `ApplicationRunner` một lần rồi thoát**. Deployment controller muốn duy trì các replica luôn sẵn sàng và có thể khởi chạy lại ứng dụng đã kết thúc, gây lặp công việc.

Kubernetes Job cũng **không cam kết exactly-once**: ngay cả với `parallelism: 1`, `completions: 1` và `restartPolicy: Never`, tài liệu Kubernetes cảnh báo chương trình có thể được khởi động nhiều lần trong một số tình huống. Thiết kế idempotent là bắt buộc.

## 4. Điều kiện chuẩn bị

Lab cần:

- JDK phù hợp với Spring Boot đã chọn; ví dụ này dùng **Java 17** và stack Spring Boot 3.5.
- Gradle hoặc Maven; các ví dụ build phía dưới dùng **Gradle Groovy DSL**.
- Docker hoặc công cụ build OCI image tương đương, quyền push lên registry mà cluster pull được.
- Kubernetes cluster hỗ trợ `batch/v1` và `CronJob.spec.timeZone` (ổn định từ Kubernetes v1.27).
- `kubectl` đã cấu hình quyền làm việc trong namespace thử nghiệm.
- PostgreSQL có khả năng được các Pod kết nối tới, với schema TaskRepository của đúng Spring Cloud Task version.
- Một cơ chế cung cấp Kubernetes Secret an toàn cho JDBC URL, username, password.
- Quyền tạo `Job`/`CronJob` trong namespace và xem Pod/log/status.

Không có cluster riêng? Có thể dùng Kubernetes local như kind, minikube hoặc môi trường staging của tổ chức. Nhưng registry, PostgreSQL networking và Secret cần được chuẩn bị tương ứng; **không mặc định container tự kết nối được `localhost:5432` của máy phát triển**.

Để giới hạn phạm vi:

~~~bash
kubectl create namespace task-lab
kubectl config current-context
kubectl get nodes
kubectl -n task-lab get jobs
~~~

Kiểm tra `current-context` **trước** khi tạo tài nguyên để tránh vô tình làm việc trên cluster production. Nếu namespace đã có, không cần tạo lại.

## 5. Chọn cặp Spring Boot và Spring Cloud tương thích

Một **cặp version minh họa đã được Spring công bố** là:

| Thành phần | Version dùng trong ví dụ | Ghi chú |
|---|---|---|
| Spring Boot | `3.5.13` | Bản Boot mà Spring Cloud 2025.0.2 dựa trên |
| Spring Cloud BOM | `2025.0.2` | Spring Cloud Northfields |
| Spring Cloud Task | Do BOM chọn | **Không** tự đặt version riêng |
| Java | 17 | Kiểm yêu cầu thực tế của stack target |
| PostgreSQL driver | Do Boot BOM chọn | Không hardcode version nếu không cần |

Cặp trên dùng để bài lab có ví dụ nhất quán, **không phải lời khuyên chọn bản cũ cho production năm 2026**. Khi tạo hệ thống mới, chọn release train còn được hỗ trợ theo ma trận chính thức và chỉnh cặp Boot/Cloud đồng bộ, ví dụ một dòng Boot 4.x/Cloud 2026.x có API tương ứng. Đừng phối Boot 4.x với Cloud 2025.0.x chỉ để lấy một thành phần mới.

Nguồn đối chiếu: [Spring Cloud release compatibility](https://spring.io/projects/spring-cloud/) và [thông báo Spring Cloud 2025.0.2](https://spring.io/blog/2026/04/02/spring-cloud-2025-0-2-aka-northfields-has-been-released/).

## 6. Tạo project và khai báo dependency

Cấu trúc học tập:

~~~text
daily-close-task/
├── build.gradle
├── settings.gradle
├── Dockerfile
└── src/main/
    ├── java/example/task/
    │   ├── DailyCloseTaskApplication.java
    │   └── DailyCloseService.java
    └── resources/
        └── application.yml

# Các manifest Kubernetes sẽ được mô tả ở các bước sau.
~~~

Ví dụ `settings.gradle`:

~~~groovy
rootProject.name = 'daily-close-task'
~~~

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2025.0.2'
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName = 'app.jar'
}
~~~

Không thêm `spring-boot-starter-web` vì task không cần HTTP server inbound. Dependency `spring-boot-starter-jdbc` được dùng cho `JdbcTemplate` và giao dịch PostgreSQL; starter Task quản lý lifecycle của TaskExecution. Bản build thực tế vẫn cần Gradle wrapper tương thích và test phù hợp.

Nếu ứng dụng dùng Spring Batch, có thể thêm starter Batch đúng version và thiết kế riêng Job/Step/JobRepository. Bài lab này cố ý chỉ dùng **Spring Cloud Task + JDBC** để làm rõ Kubernetes Job/CronJob trước.

## 7. Cấu hình task không web và TaskRepository

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: daily-close-task

  main:
    web-application-type: none

  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      maximum-pool-size: 3

  cloud:
    task:
      name: daily-close-task
      initialize-enabled: false

logging:
  level:
    root: INFO
~~~

Ở đây:

- `web-application-type: none` ngăn Spring Boot bật embedded HTTP server.
- `TASK_DB_URL`, `TASK_DB_USER`, `TASK_DB_PASSWORD` được cung cấp từ environment/Secret khi deploy.
- `initialize-enabled: false` yêu cầu bảng **TaskRepository đã được migration trước**; JVM runtime không tự tạo DDL.
- Pool nhỏ phù hợp với một task ngắn hạn; khi có nhiều Pod đồng thời, tổng connection pool vẫn có thể lớn.

**Tách schema migration khỏi task runtime** giúp DB credential trong Pod chỉ cần DML, không cần `CREATE TABLE` hay `ALTER TABLE`.

## 8. Tạo bảng kết quả nghiệp vụ có khóa idempotency

Bảng này là **schema do dự án tự quản lý**, không phải bảng mặc định của Spring Cloud Task:

~~~sql
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE IF NOT EXISTS finance.daily_close_result (
    tenant_id      VARCHAR(64) NOT NULL,
    business_date  DATE NOT NULL,
    revision       INTEGER NOT NULL,
    total_amount   NUMERIC(19, 2) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (tenant_id, business_date, revision)
);
~~~

Trước khi chạy task, cần tạo **metadata schema của Spring Cloud Task cho PostgreSQL** bằng DDL từ đúng version artifact/tài liệu Spring Cloud Task. Những bảng thông dụng gồm `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, cơ chế cấp ID và các bảng bổ sung nếu tính năng tương ứng được bật. Không tự dùng DDL H2 cho PostgreSQL.

Với môi trường production:

1. Role `task_migrator` tạo bảng TaskRepository và bảng nghiệp vụ.
2. Role `task_runtime` chỉ được cấp `USAGE` trên schema liên quan và `SELECT/INSERT/UPDATE` trên những bảng cần thiết, cộng quyền sequence/table cấp ID phù hợp.
3. Secret trong namespace chứa connection URL và credential của **runtime role**, không phải migrator.
4. Schema TaskRepository phải được tạo đúng `tablePrefix`/search path mà runtime sử dụng.

Ví dụ SQL cấp quyền cho bảng nghiệp vụ:

~~~sql
GRANT USAGE ON SCHEMA finance TO task_runtime;

GRANT SELECT, INSERT
ON TABLE finance.daily_close_result
TO task_runtime;
~~~

Đây chưa phải toàn bộ GRANT cho TaskRepository; phải cấp riêng quyền trên các bảng/sequence metadata theo DDL thực tế. Nếu migration và runtime chạy trong hai database khác nhau, cấu hình nhiều DataSource/TaskConfigurer cần được thiết kế rõ, không tự giả định một DataSource đủ cho mọi repository.

## 9. Viết ApplicationRunner hữu hạn và có thể thử lỗi sau commit

`DailyCloseTaskApplication.java`:

~~~java
package example.task;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyCloseTaskApplication {

    private static final Logger log =
        LoggerFactory.getLogger(DailyCloseTaskApplication.class);

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(DailyCloseTaskApplication.class, args);

        int code = SpringApplication.exit(context);
        System.exit(code);
    }

    @Bean
    ApplicationRunner dailyCloseRunner(DailyCloseService service) {
        return args -> {
            String tenant = required(args, "tenant");
            String revisionValue = optional(args, "revision", "1");
            int revision = Integer.parseInt(revisionValue);

            String dateArgument = optional(args, "date", null);
            boolean previousDay = args.containsOption("previous-day");

            if ((dateArgument == null) == (!previousDay)) {
                throw new IllegalArgumentException(
                    "Use exactly one: --date=yyyy-MM-dd OR --previous-day");
            }

            LocalDate businessDate =
                dateArgument != null
                    ? LocalDate.parse(dateArgument)
                    : LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))
                        .minusDays(1);

            boolean inserted =
                service.closeDay(tenant, businessDate, revision);

            log.info(
                "daily-close tenant={} businessDate={} revision={} result={}",
                tenant, businessDate, revision,
                inserted ? "APPLIED" : "ALREADY_APPLIED");

            // Dùng riêng trong lab để mô phỏng lỗi sau COMMIT.
            if (args.containsOption("fail-after-commit")) {
                throw new IllegalStateException(
                    "Simulated failure after business commit");
            }
        };
    }

    private static String required(
            ApplicationArguments args, String key) {
        String value = optional(args, key, null);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing required --" + key + "=...");
        }
        return value;
    }

    private static String optional(
            ApplicationArguments args,
            String key,
            String fallback) {

        List<String> values = args.getOptionValues(key);
        if (values == null) {
            return fallback;
        }

        if (values.size() != 1 || values.get(0) == null) {
            throw new IllegalArgumentException(
                "Expected one value for --" + key);
        }

        return values.get(0);
    }
}
~~~

**Giải thích quan trọng:**

- Trong một lần chạy chỉ dùng `--date` **hoặc** `--previous-day`, không truyền cả hai.
- `--date` phù hợp với Job chạy bù. `--previous-day` phù hợp với ví dụ CronJob thường lệ.
- Timezone được khai báo **ngay trong Java** khi tính ngày trước đó. `CronJob.spec.timeZone` chỉ xác định timezone của lịch; không tự đổi timezone của JVM.
- `DailyCloseService.closeDay(...)` phải là lời gọi đồng bộ và hoàn tất transaction trước khi runner trở về.
- `fail-after-commit` cố ý ném exception **sau khi service đã commit** để kiểm thử rủi ro retry.
- Không nuốt exception. Khi runner thất bại trong startup, `SpringApplication.run(...)` có thể ném trước khi trả context; Spring Boot xử lý failure/exit code theo lifecycle. Phải kiểm tra mã thoát của Pod trên cluster thật.
- `SpringApplication.exit(context)` cộng `System.exit(code)` ở nhánh thành công giúp JVM kết thúc với mã tường minh sau khi các runner hoàn tất. Không gọi `System.exit(0)` bên trong service.

### Chú ý đến giá trị boolean của option

Trong ví dụ, `containsOption("fail-after-commit")` hoặc `containsOption("previous-day")` kiểm tra **sự tồn tại** của option. Vì vậy **`--fail-after-commit=false` vẫn được xem là bật**. Để tắt, hãy **không truyền option**. Nếu sản phẩm cần giá trị true/false, phải parse và validate bằng `getOptionValues(...)`.

## 10. Viết service với transaction và unique key

`DailyCloseService.java`:

~~~java
package example.task;

import java.math.BigDecimal;
import java.sql.Date;
import java.time.LocalDate;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DailyCloseService {

    private final JdbcTemplate jdbc;

    public DailyCloseService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean closeDay(
            String tenant, LocalDate businessDate, int revision) {

        int inserted = jdbc.update(
            """
            INSERT INTO finance.daily_close_result
                (tenant_id, business_date, revision, total_amount)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, revision)
            DO NOTHING
            """,
            tenant,
            Date.valueOf(businessDate),
            revision,
            new BigDecimal("123.45")
        );

        return inserted == 1;
    }
}
~~~

`123.45` là **giá trị giả để kiểm thử**, không phải công thức chốt doanh thu. Trong dự án thực, service phải đọc dữ liệu nguồn theo snapshot/cutoff, tính toán, validate và commit nhất quán. Khi cùng khóa nghiệp vụ đã tồn tại, `ON CONFLICT DO NOTHING` giúp lần retry không chèn bản ghi thứ hai.

### Vì sao cần unique constraint ở database?

~~~mermaid
sequenceDiagram
    participant J as Job Pod A
    participant K as Job Pod B (retry/duplicate)
    participant DB as PostgreSQL
    J->>DB: INSERT tenant-A, date=23, revision=1
    DB-->>J: 1 row inserted / committed
    J--xJ: JVM lỗi sau commit
    K->>DB: INSERT cùng business key
    DB-->>K: ON CONFLICT DO NOTHING (0 row)
    K-->>K: ALREADY_APPLIED, không ghi trùng
~~~

Kubernetes có thể tạo Pod thay thế hoặc thậm chí khởi chạy trùng trong một số cửa sổ sự cố. Một câu `SELECT` kiểm tra trước rồi `INSERT` **không đủ** chống race nếu thiếu unique constraint/transaction; hai Pod có thể cùng đọc “chưa tồn tại”. Unique index ở database là lớp bảo vệ cuối cùng.

**Giới hạn của demo:** nếu retry cùng key nhưng dữ liệu nguồn khác hoặc tổng tiền đã thay đổi, chỉ bỏ qua conflict có thể che sự bất nhất. Production cần fingerprint/snapshot, revision hoặc chính sách trả `CONFLICT` rõ ràng. Nếu side effect đi sang API/message broker, áp dụng idempotency key ở hệ thống nhận hoặc transactional outbox.

## 11. Đóng gói JAR thành OCI image

Dùng Gradle wrapper của dự án:

~~~bash
./gradlew clean bootJar
~~~

Build đã cấu hình tạo `build/libs/app.jar`.

Ví dụ `Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY build/libs/app.jar /app/app.jar

USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là image không mở HTTP port; không cần `EXPOSE 8080`. Với workload hữu hạn, **exec-form ENTRYPOINT** giúp JVM nhận signal trực tiếp. Tránh dùng shell wrapper chạy Java trong background mà không `wait` hoặc forward signal.

Build và push image thử nghiệm:

~~~bash
docker build -t registry.example.org/training/daily-close-task:1.0.0 .
docker push registry.example.org/training/daily-close-task:1.0.0
~~~

`registry.example.org` là **địa chỉ minh họa**: phải thay bằng registry thật và bảo đảm cluster có quyền pull image. Trong production, ưu tiên image tag bất biến hoặc **digest**, scan lỗ hổng, chọn base image được hỗ trợ và test kiến trúc CPU của node.

## 12. Chuẩn bị namespace, Secret và quyền database

Các manifest phía dưới giả định:

- Namespace `task-lab` đã tồn tại.
- PostgreSQL đã có schema metadata Spring Cloud Task và bảng `finance.daily_close_result`.
- Kubernetes Secret `daily-close-db` đã được tạo **trong cùng namespace**, có ba key: `url`, `username`, `password`.
- Runtime DB role có đủ DML trên TaskRepository và quyền `SELECT/INSERT` ở bảng nghiệp vụ.
- NetworkPolicy, DNS và firewall cho phép Pod kết nối tới PostgreSQL.

Kiểm tra sự hiện diện của Secret mà không in giá trị:

~~~bash
kubectl -n task-lab get secret daily-close-db
kubectl -n task-lab get serviceaccounts
~~~

Không viết password thật vào manifest mẫu, không đưa `--password=...` vào args, không in toàn bộ environment hoặc Secret base64 ra terminal/log. Một giải pháp thực tế là External Secrets Operator, CSI Secret Store hoặc bộ quản lý bí mật của nền tảng.

**Dùng `automountServiceAccountToken: false`** nếu task không cần gọi Kubernetes API. Quyền đọc Job/Pod/log là quyền của người vận hành hoặc hệ monitoring, không có nghĩa Pod task phải có các quyền đó.

## 13. Manifest Kubernetes Job chạy một ngày xác định

Ví dụ một manifest `job.yaml` hoàn chỉnh ở mức cơ bản:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-close-20261123
  namespace: task-lab
  labels:
    app: daily-close-task
    exercise: manual
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 2
  activeDeadlineSeconds: 900
  ttlSecondsAfterFinished: 86400

  template:
    metadata:
      labels:
        app: daily-close-task
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 30
      automountServiceAccountToken: false

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: daily-close
          image: registry.example.org/training/daily-close-task:1.0.0
          imagePullPolicy: IfNotPresent
          args:
            - "--tenant=tenant-A"
            - "--date=2026-11-23"
            - "--revision=1"

          env:
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: password

          resources:
            requests:
              cpu: 250m
              memory: 384Mi
            limits:
              cpu: "1"
              memory: 768Mi

          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}
~~~

### Ý nghĩa các trường quan trọng

| Field | Ý nghĩa | Không đồng nghĩa |
|---|---|---|
| `completions: 1` | Cần một Pod hoàn tất để Job được xem hoàn tất | Chỉ có đúng một lần thực thi JVM trong mọi sự cố |
| `parallelism: 1` | Mục tiêu số Pod chạy song song | Bảo đảm exactly-once |
| `restartPolicy: Never` | Pod lỗi không restart container trong chính Pod đó; Job có thể tạo Pod mới | Kubernetes không retry |
| `backoffLimit: 2` | Giới hạn lỗi/retry trước khi Job thất bại | Mọi lỗi chắc chắn retry đúng hai lần |
| `activeDeadlineSeconds: 900` | Giới hạn tổng thời gian hoạt động của Job | Timeout của từng SQL statement |
| `ttlSecondsAfterFinished: 86400` | Cho phép dọn Job sau khi hoàn tất/thất bại khoảng 1 ngày | Tự xóa TaskRepository hoặc dữ liệu nghiệp vụ |
| `terminationGracePeriodSeconds: 30` | Cho JVM cơ hội shutdown có kiểm soát | Bảo đảm callback chạy khi SIGKILL |
| `requests/limits` | Dự trù/giới hạn CPU/RAM của Pod | Cấu hình heap Java đầy đủ |
| `automountServiceAccountToken: false` | Không tự mount token API vào Pod | Chặn mọi truy cập mạng |
| `readOnlyRootFilesystem: true` | Hạn chế ghi filesystem của image | Không cần tmp filesystem |
| `emptyDir /tmp` | Cho runtime một nơi ghi tạm | Dữ liệu bền vững sau Pod chết |

Dùng `activeDeadlineSeconds` và `backoffLimit` cùng nhau: **active deadline có thể kết thúc Job trước khi dùng hết số retry**. OOMKill, image pull failure, node loss và lỗi JDBC có cách hiện diện khác nhau trên Pod/Job; cần xem Events và container status để phân loại.

## 14. Áp dụng Job và quan sát tiến trình

Tại thư mục chứa manifest:

~~~bash
kubectl -n task-lab apply -f job.yaml

kubectl -n task-lab get job daily-close-20261123
kubectl -n task-lab describe job daily-close-20261123

kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-20261123 \
  -o wide
~~~

Label chuẩn `batch.kubernetes.io/job-name` được Kubernetes thêm vào Pod của Job trong các cluster hiện hành; nếu không thấy Pod, kiểm tra `kubectl describe job` và label thực tế.

Chờ Job hoàn thành:

~~~bash
kubectl -n task-lab wait \
  --for=condition=complete \
  job/daily-close-20261123 \
  --timeout=15m
~~~

**Nếu Job thất bại**, điều kiện `Complete` không xảy ra và lệnh `wait` có thể hết timeout. Đừng kết luận “ứng dụng vẫn chạy” chỉ vì lệnh wait không thành công; cần xem các **conditions, Pod status và Events**.

Xem log trong trường hợp một Pod chính:

~~~bash
kubectl -n task-lab logs \
  job/daily-close-20261123 \
  --all-containers=true \
  --timestamps=true
~~~

Khi Job đã retry tạo **nhiều Pod**, `kubectl logs job/...` có thể chỉ hiển thị log của một Pod. Hãy liệt kê Pod và xem log từng Pod, đặc biệt là Pod đã Failed.

~~~bash
kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-20261123

kubectl -n task-lab logs pod/POD_NAME --timestamps=true
kubectl -n task-lab describe pod POD_NAME
~~~

`POD_NAME` là placeholder cần thay bằng tên Pod thực. Với `restartPolicy: Never`, mỗi lần retry của Job thường có Pod riêng; `kubectl logs --previous` chỉ hữu ích khi **một container đã restart trong cùng Pod**, không phải cách lấy log của Pod retry khác.

## 15. Phân biệt Job Complete, Pod Succeeded và mã thoát container

Kubernetes có nhiều cấp trạng thái:

| Quan sát | Ý nghĩa | Cần kiểm thêm |
|---|---|---|
| Job `Complete=True` | Job controller xác nhận đủ số hoàn tất | TaskRepository và business output |
| Job `Failed=True` | Job đã vượt chính sách lỗi/deadline hoặc gặp điều kiện thất bại | Pod/container termination reason, logs, data |
| Pod `Succeeded` | Các container liên quan trong Pod hoàn tất thành công | Logic nghiệp vụ/TaskExecution |
| Pod `Failed` | Có container lỗi hoặc Pod bị chấm dứt không thành công | Exit code, `OOMKilled`, `DeadlineExceeded` |
| Container `exitCode=0` | JVM/container hoàn tất theo exit policy | Không chứng minh đủ dữ liệu nghiệp vụ |
| Container `exitCode≠0` | Container báo lỗi | Có thể đã commit một phần hoặc toàn bộ dữ liệu |
| TaskExecution `exitCode=0` | Spring Cloud Task ghi lần chạy hoàn tất theo policy | Không thay unique key/transaction |
| TaskExecution không có `endTime` | Framework chưa ghi kết thúc | Có thể process còn sống hoặc chết đột ngột |

Lệnh lấy Pod phase và tên:

~~~bash
kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-20261123 \
  -o wide
~~~

Lấy một số thông tin termination từ Pod JSON (ví dụ Linux/macOS shell):

~~~bash
kubectl -n task-lab get pod POD_NAME \
  -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}{" "}{.status.containerStatuses[0].state.terminated.exitCode}{"\n"}'
~~~

Nếu `state.terminated` chưa có, container có thể vẫn Running/Waiting. Nếu Job có sidecar hoặc nhiều container, phải chọn **đúng container `daily-close`**, không mặc định index 0 luôn là task chính.

### Những tình huống khiến Job thất bại mà không có TaskExecution

- Image chưa pull được (`ImagePullBackOff` hoặc `ErrImagePull`).
- Pod không schedule được do thiếu CPU/RAM/quota.
- Secret không tồn tại hoặc thiếu key.
- JVM không khởi động được (JAR sai, Java version không tương thích).
- Spring ApplicationContext lỗi trước khi TaskRepository bắt đầu lưu.
- Database/schema chưa sẵn sàng khi task khởi động.

Trong các trường hợp này, **không có TaskExecution không có nghĩa Kubernetes chưa thử launch**. Hãy kiểm tra `kubectl describe job/pod`, Events và log/container status.

## 16. Đối chiếu TaskRepository bằng SQL

Sau khi Job chạy, kết nối PostgreSQL bằng tài khoản có quyền **đọc metadata**, không dùng tài khoản migrator/superuser cho mọi truy vấn vận hành.

Với schema Task mặc định và table prefix `TASK_`:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-close-task'
ORDER BY TASK_EXECUTION_ID DESC
LIMIT 20;
~~~

Đọc tham số của một lần chạy (không in dữ liệu nhạy cảm):

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_PARAM
FROM TASK_EXECUTION_PARAMS
WHERE TASK_EXECUTION_ID = :task_execution_id;
~~~

**Lưu ý DDL:** tên cột của `TASK_EXECUTION_PARAMS` và các bảng phụ khác có thể thay theo version/dialect, vì thế hãy đối chiếu schema thật trước khi dùng câu SQL. Mẫu trên dùng `TASK_PARAM` như một cột tham khảo ở schema Task thông dụng; nếu khác, điều chỉnh theo DDL đã migration.

Cần chú ý:

- `TaskExecutionId` khác `Job name` và khác business key.
- Một lần Job retry tạo Pod mới có thể tạo **TaskExecution mới**.
- Khi tiến trình chết bất thường, bản ghi TaskExecution có thể không có `END_TIME`.
- `ERROR_MESSAGE`/arguments có thể chứa dữ liệu nhạy cảm, chỉ cấp quyền xem theo nhu cầu.
- Nếu runtime dùng schema/prefix riêng, thêm schema hoặc đổi tên bảng tương ứng, ví dụ `task_meta.TASK_EXECUTION`.

### Nếu ứng dụng sử dụng Spring Batch

Khi task thực thi Batch Job, **JobRepository** chứa `JobInstance`, `JobExecution`, `StepExecution` và checkpoint riêng. Đừng đọc `TaskRepository` rồi kết luận một Batch Job chắc chắn đã `COMPLETED`. Cần kiểm metadata `BATCH_*` và business output; đặc biệt nếu có nhiều Job hoặc remote partitioning.

## 17. Đối chiếu bảng kết quả nghiệp vụ

Truy vấn bản ghi chốt ngày:

~~~sql
SELECT
    tenant_id,
    business_date,
    revision,
    total_amount,
    created_at
FROM finance.daily_close_result
WHERE tenant_id = 'tenant-A'
  AND business_date = DATE '2026-11-23'
  AND revision = 1;
~~~

Kỳ vọng sau lần chạy đầu:

~~~text
tenant_id   | business_date | revision | total_amount
------------+---------------+----------+-------------
tenant-A    | 2026-11-23    | 1        | 123.45
~~~

Vì `PRIMARY KEY(tenant_id, business_date, revision)`, không thể có hai hàng có **cùng business key**. Nếu Job bị retry với cùng input, service ghi log `ALREADY_APPLIED` và trả thành công theo demo, thay vì cố ghi bản mới.

Để kiểm xem có nhiều hàng cho cùng khóa (chỉ phục vụ điều tra; khóa PRIMARY KEY đã chặn trùng):

~~~sql
SELECT tenant_id, business_date, revision, COUNT(*) AS rows_for_key
FROM finance.daily_close_result
GROUP BY tenant_id, business_date, revision
HAVING COUNT(*) > 1;
~~~

Kỳ vọng: **0 hàng**. Kết quả này **không chứng minh** nghiệp vụ thực ngoài lab hoàn toàn exactly-once nếu hệ thống có API/message side effect. Khi triển khai thật, cần idempotency ở cả những hệ thống ngoài.

## 18. Diễn tập lỗi sau commit và tự động retry

Đây là phần quan trọng nhất để hiểu sự khác biệt giữa **Kubernetes Job failure** và **business outcome**.

### Bước A — tạo Job lỗi có chủ đích

Lấy `job.yaml` làm mẫu **trong dự án học tập** và thay:

- `metadata.name: daily-close-failure-20261122`.
- `spec.backoffLimit: 1`, để dễ quan sát.
- Arguments `--date=2026-11-22` và thêm `--fail-after-commit`.
- Giữ nguyên tenant/revision và cấu hình database.

Không sửa `spec.template` của một Job đã tồn tại bằng `kubectl apply` rồi kỳ vọng Kubernetes cho thay mọi trường: **Pod template của Job thường là immutable**. Tạo **Job có tên mới** cho lần diễn tập.

~~~yaml
# Chỉ là phần args cần đổi trong manifest Job mới:
args:
  - "--tenant=tenant-A"
  - "--date=2026-11-22"
  - "--revision=1"
  - "--fail-after-commit"
~~~

Sau đó:

~~~bash
kubectl -n task-lab apply -f job-failure.yaml
kubectl -n task-lab get job daily-close-failure-20261122
kubectl -n task-lab get pods \
  -l batch.kubernetes.io/job-name=daily-close-failure-20261122
~~~

### Bước B — quan sát kết quả

Mỗi lần JVM thực sự chạy tới `DailyCloseService`, nó:

1. Insert bản ghi business key và commit.
2. Ném `IllegalStateException` sau khi commit.
3. Kết thúc lỗi, để Kubernetes Job controller quyết định retry theo `backoffLimit`.

Sau retry, kiểm log từng Pod. Có thể thấy:

~~~text
Lần đầu:  result=APPLIED
Lần sau:  result=ALREADY_APPLIED
Cả hai:   Simulated failure after business commit
~~~

Mặc dù Job có thể kết thúc **Failed**, bảng `finance.daily_close_result` vẫn có **một** bản ghi của `tenant-A, 2026-11-22, revision=1`.

**Không giả định chính xác số Pod được tạo** chỉ từ một giá trị `backoffLimit`: controller có chính sách đếm lỗi, backoff và điều kiện thay thế Pod; kiểm thực tế `status.failed` và danh sách Pod. Một lỗi ở image pull/DB trước khi commit cũng cho dấu vết khác.

### Bước C — chạy lại sau khi đã sửa lỗi

Tạo **một Job mới có tên khác**, cùng `tenant/date/revision`, nhưng **bỏ `--fail-after-commit`**. Nó sẽ thấy kết quả đã tồn tại, log `ALREADY_APPLIED` và hoàn thành thành công theo thiết kế demo.

Đây là một mô hình **idempotent retry**, không phải “mỗi lần retry phải xử lý lại từ đầu”. Trong production, phải còn kiểm fingerprint/snapshot đầu vào và các side effect ngoài database.

## 19. Tạo CronJob chạy tự động hằng ngày

Kubernetes CronJob tạo Job theo lịch. Để thực hành mà không chờ đến hôm sau, có thể tạo CronJob trước rồi sinh Job thủ công từ template.

Ví dụ `cronjob.yaml`:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-close-nightly
  namespace: task-lab
  labels:
    app: daily-close-task

spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 2

  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 900
      ttlSecondsAfterFinished: 86400

      template:
        spec:
          restartPolicy: Never
          terminationGracePeriodSeconds: 30
          automountServiceAccountToken: false

          securityContext:
            runAsNonRoot: true
            runAsUser: 10001

          containers:
            - name: daily-close
              image: registry.example.org/training/daily-close-task:1.0.0
              imagePullPolicy: IfNotPresent
              args:
                - "--tenant=tenant-A"
                - "--previous-day"
                - "--revision=1"

              env:
                - name: TASK_DB_URL
                  valueFrom:
                    secretKeyRef:
                      name: daily-close-db
                      key: url
                - name: TASK_DB_USER
                  valueFrom:
                    secretKeyRef:
                      name: daily-close-db
                      key: username
                - name: TASK_DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: daily-close-db
                      key: password

              resources:
                requests:
                  cpu: 250m
                  memory: 384Mi
                limits:
                  cpu: "1"
                  memory: 768Mi
~~~

Manifest CronJob ngắn hơn Job ở mục 13 để tập trung vào lịch. Với production, áp dụng cùng các biện pháp `securityContext`, read-only filesystem, /tmp và network/secret access nếu cần. Đừng để bản mẫu ngắn hơn trở thành lý do hạ chuẩn bảo mật.

### Ý nghĩa các trường CronJob

| Field | Ý nghĩa | Giới hạn |
|---|---|---|
| `schedule: "0 2 * * *"` | Tạo Job theo lịch 02:00 mỗi ngày | Không tự xác định business date của Java |
| `timeZone: "Asia/Ho_Chi_Minh"` | Diễn giải cron schedule theo timezone này | Không tự cấu hình `ZoneId` của JVM |
| `concurrencyPolicy: Forbid` | Bỏ qua lịch kế tiếp khi **Job trước của cùng CronJob** chưa xong | Không chặn Job tạo thủ công hoặc CronJob khác |
| `startingDeadlineSeconds: 600` | Bỏ qua lịch trễ quá khoảng 10 phút | Có thể làm mất một kỳ chạy, cần phát hiện |
| `successfulJobsHistoryLimit: 3` | Giữ tối đa một số Job đã thành công | Không thay chính sách retention log |
| `failedJobsHistoryLimit: 2` | Giữ một số Job đã thất bại | Không đảm bảo có thể đọc Pod log mãi |
| `jobTemplate` | Mẫu Job do CronJob tạo | Mọi Job sinh ra vẫn có lifecycle/retry riêng |

`Forbid` không phải khóa phân tán cho nghiệp vụ: nếu hai CronJob khác nhau hoặc một operator tạo Job thủ công cùng kỳ, các Pod vẫn có thể xử lý đồng thời. Trong một số trường hợp controller cũng có thể tạo hai Job cho một lịch hoặc bỏ lỡ lịch; do đó vẫn cần **idempotency**. 

### Vấn đề tính business date

Ví dụ dùng `--previous-day` theo `Asia/Ho_Chi_Minh` trong Java để tính ngày trước đó tại thời điểm khởi chạy. Với Job thường chạy đúng 02:00, điều này hợp lý cho demo. Nhưng nếu **lịch bị trễ qua ngày khác**, `previous-day` có thể cho ra ngày nghiệp vụ không tương ứng với lịch gốc.

Trong production nên có **một cách lấy business date ổn định theo scheduled run**: scheduler truyền `--date=yyyy-MM-dd` đã tính, hoặc ứng dụng dùng scheduled timestamp/metadata do orchestrator cung cấp với quy tắc rõ ràng và được kiểm thử. Không dùng thời điểm Pod bắt đầu như business key nếu cần chạy bù một kỳ cũ.

## 20. Áp dụng, kiểm lịch và chạy thử CronJob ngay

Tạo CronJob:

~~~bash
kubectl -n task-lab apply -f cronjob.yaml

kubectl -n task-lab get cronjobs
kubectl -n task-lab describe cronjob daily-close-nightly
~~~

Tạo Job ngay từ template mà **không cần chờ 02:00**:

~~~bash
kubectl -n task-lab create job daily-close-ad-hoc-001 \
  --from=cronjob/daily-close-nightly

kubectl -n task-lab get job daily-close-ad-hoc-001
kubectl -n task-lab logs job/daily-close-ad-hoc-001
~~~

`kubectl create job --from=cronjob/...` sao chép **jobTemplate** tại thời điểm gọi. Nó **không tự tính lại arguments từ lịch gốc**, nên trong demo sẽ vẫn dùng `--previous-day` của JVM theo thời gian chạy ad-hoc.

Khi cần tạm dừng lịch, dùng `spec.suspend: true` trong manifest rồi apply. Việc suspend **không dừng những Job đã bắt đầu**. Khi bật lại, kiểm `startingDeadlineSeconds` và cơ chế lịch bị lỡ để tránh bất ngờ chạy bù.

### Đọc Job do CronJob tạo

~~~bash
kubectl -n task-lab get cronjob daily-close-nightly
kubectl -n task-lab get jobs -l app=daily-close-task
kubectl -n task-lab get pods -l app=daily-close-task
~~~

Kubernetes tự gắn ownerReferences/labels cho các Job liên quan; để phân biệt Jobs của các CronJob khác nhau, dùng labels riêng trong `jobTemplate.metadata.labels` hoặc truy vấn ownerReferences. Không suy ra Job nào thuộc lịch nào chỉ từ chuỗi tên nếu có nhiều lịch trùng prefix.

## 21. Quan sát bằng logs, events và SQL theo một quy trình

Một lần chạy đáng tin cậy cần qua bốn bước điều tra:

~~~mermaid
flowchart TD
    A["Job được tạo"] --> B{"Pod chạy được?"}
    B -- "Không" --> C["Events: scheduling, image, Secret, quota"]
    B -- "Có" --> D["Logs và container exit code"]
    D --> E{"TaskExecution tồn tại?"}
    E -- "Không" --> F["Bootstrap, DataSource, schema, JVM"]
    E -- "Có" --> G["End time, exit code, error message"]
    G --> H["Kiểm kết quả nghiệp vụ theo business key"]
    H --> I{"Kết quả đúng và không trùng?"}
    I -- "Có" --> J["Đánh giá completed theo policy"]
    I -- "Không" --> K["Điều tra transaction/idempotency/retry"]
~~~

### Trình tự vận hành đề xuất

1. `kubectl get cronjobs/jobs/pods`: xác định Job và các lần Pod retry.
2. `kubectl describe job/pod`: kiểm Events, deadline, OOMKill, image pull, Secret, quota.
3. `kubectl logs` từng Pod: xem ngày/tenant/revision, `APPLIED` hoặc `ALREADY_APPLIED`.
4. Query `TaskRepository`: đối chiếu TaskExecution ID, start/end, exit code.
5. Query bảng nghiệp vụ: xác nhận một bản ghi đúng business key.
6. Nếu có Spring Batch, query JobRepository và StepExecution/checkpoint.
7. Chỉ retry thủ công sau khi biết có worker/Job khác còn chạy hay không và business state đã commit đến đâu.

**Một Pod Failed không chứng minh business transaction đã rollback.** Đặc biệt, mạng lỗi sau khi server nhận request hoặc JVM chết sau commit có thể khiến caller thấy thất bại nhưng dữ liệu đã đổi.

## 22. Observability không dùng HTTP health endpoint

Ứng dụng `WebApplicationType.NONE` không cần `/actuator/health` để làm task hữu hạn. Với Kubernetes Job, theo dõi:

| Nguồn quan sát | Cách thu thập |
|---|---|
| Job/Pod status | Kubernetes API, metrics của Job controller, events |
| Exit code | Container `terminated.exitCode` |
| Task lifecycle | TaskRepository, TaskExplorer |
| Logs | Central log collector và `kubectl logs` khi Pod còn |
| Metrics duration/failure | Micrometer/OTLP hoặc metric được push/flush khi JVM kết thúc |
| Business output | Query theo khóa tenant/date/revision |
| Trace | OpenTelemetry/Micrometer, correlation qua TaskExecution ID khi có |

Vì Job có thể chạy rất ngắn, một hệ thống **pull metrics** có thể không kịp scrape. Nếu dùng exporter bất đồng bộ, phải đảm bảo telemetry được flush/close theo lifecycle có kiểm soát và chấp nhận rằng `SIGKILL` không bảo đảm callback.

Những metric cảnh báo hữu ích:

- Job mới bị Failed hoặc vượt `activeDeadlineSeconds`.
- Không có Job thành công cho một business date bắt buộc trước deadline.
- Job/Pod retry bất thường nhiều lần.
- TaskExecution có thời gian mở quá dài hoặc exit code lỗi.
- Business result thiếu cho tenant/ngày hoặc bị báo conflict.
- PostgreSQL connection pool/quota quá tải.

Không gửi toàn bộ tenant ID, transaction ID hoặc TaskExecution ID vào **low-cardinality metric labels** khi số lượng lớn; ưu tiên structured logs/trace attributes được kiểm soát.

## 23. Tài nguyên, bảo mật và dọn dẹp

### Bảo mật

- Dùng image đã scan và cố định version/digest.
- Chạy container non-root, cấm privilege escalation, hạn chế filesystem write.
- Không mount Kubernetes API token nếu worker không cần.
- Secret qua `secretKeyRef`/secret manager, không truyền password bằng CLI.
- Database runtime role chỉ có DML cho TaskRepository và bảng nghiệp vụ cần thiết.
- NetworkPolicy giới hạn outbound tới PostgreSQL/API thực sự cần.
- Không log raw TaskExecution arguments nếu chúng có dữ liệu nhạy cảm.
- Phân biệt quyền của **người chạy `kubectl`** và quyền của service account **trong Pod**.

### Tài nguyên

- `requests` đủ để Pod được schedule, `limits` phù hợp heap + native memory của JVM.
- Nhiều Pod retry/parallelism có thể cộng dồn connection pool DB.
- `activeDeadlineSeconds` nên lớn hơn thời gian xử lý thông thường cộng overhead khởi tạo, nhưng vẫn có giới hạn.
- `terminationGracePeriodSeconds` phải cân đối với thời gian commit/cleanup có thể chấp nhận.
- `parallelism: 1` không thay business lock hay unique constraint.

### Retention

`ttlSecondsAfterFinished` cho phép tự xóa Job/Pod sau khi kết thúc. Sau khi bị xóa, `kubectl logs` có thể không còn dữ liệu cần điều tra. Vì vậy nên lưu logs và TaskRepository bên ngoài vòng đời Job/Pod, có retention/backup đúng chính sách.

Không xóa hàng loạt bảng `TASK_EXECUTION` hoặc `TASK_EXECUTION_PARAMS` chỉ vì Kubernetes đã dọn Job. Những bảng đó phục vụ audit và có thể liên quan các quy trình vận hành khác. Nếu cần cleanup metadata, dùng một maintenance workflow có kiểm soát.

## 24. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán |
|---|---|---|
| Job Pending lâu | Thiếu quota, CPU/RAM, node selector hoặc taint | `kubectl describe pod` và Events |
| `ImagePullBackOff` | Image/registry/credentials sai | Pod Events, imagePullSecrets, image digest |
| `CreateContainerConfigError` | Secret hoặc key không tồn tại | Pod describe và Secret metadata |
| JVM báo `UnsupportedClassVersionError` | JRE trong image không phù hợp JAR | Java version build/runtime |
| Task không thấy DB | DNS, NetworkPolicy, URL, Secret, TLS | Kết nối và lỗi JDBC |
| `relation TASK_EXECUTION does not exist` | Schema metadata chưa migrate/sai prefix | TaskRepository DDL và datasource |
| `permission denied for sequence` | Runtime role thiếu quyền cấp TaskExecution ID | DDL, loại sequence/table và grants |
| Job Completed nhưng không có output | Runner trả về trước async work hoặc logic sai | Logs, TaskExecution, business SQL |
| Pod Failed nhưng output tồn tại | Crash sau commit, external side effect đã xảy ra | Business key/idempotency và TaskRepository |
| Có nhiều Pod cho một Job | Retry hoặc duplicate start hợp lệ trong failure window | Pod list, backoffLimit và điều kiện Job |
| CronJob không tạo Job | Suspend, lịch chưa tới, missed deadline, controller/scheduling lỗi | Describe CronJob, schedule/timeZone |
| CronJob chạy trễ sai ngày | Dùng `LocalDate.now()` lúc Pod bắt đầu | Truy business date có nguồn ổn định |
| CronJob chạy trùng | `Allow`, nhiều CronJob, manual Job hoặc controller edge case | Job owner/labels và business key |
| `kubectl wait` timeout | Job Failed hoặc chưa Complete | Get/describe Job, conditions, Pod statuses |
| Logs mất sau ít ngày | TTL/history cleanup | Central logging và retention |
| Exit code 0 khi nghiệp vụ lỗi | Exception bị nuốt/không chờ future | ApplicationRunner, exit-code mapping |
| Pod OOMKilled | Heap/native memory quá limits | Resources, GC logs, container termination |
| Không thể sửa args Job cũ | Pod template immutable | Tạo Job tên mới với args mới |
| Batch Job FAILED nhưng task success | Chưa nối Batch status với task exit policy | `fail-on-job-failure` hoặc custom runner |

## 25. Checklist nghiệm thu bài thực hành

- [ ] Dùng đúng cặp Spring Boot/Spring Cloud BOM tương thích, build JAR thành công trên máy người học.
- [ ] Ứng dụng có `web-application-type: none`, runner xử lý và kết thúc JVM.
- [ ] PostgreSQL có **đúng DDL Spring Cloud Task** và bảng business result có unique key.
- [ ] Secret được cấp trong namespace, không có credential thật trong manifests/logs.
- [ ] Image đã push và có thể pull từ cluster.
- [ ] Job `daily-close-20261123` tạo Pod, log `APPLIED` và hoàn thành.
- [ ] TaskRepository có TaskExecution với start/end/exit code phù hợp.
- [ ] Bảng `daily_close_result` chỉ có một row theo `tenant/date/revision`.
- [ ] CronJob có `schedule`, `timeZone`, `concurrencyPolicy` và `startingDeadlineSeconds` phù hợp.
- [ ] Có thể tạo Job ngay từ CronJob bằng `kubectl create job --from=cronjob`.
- [ ] Diễn tập `--fail-after-commit`: Job báo lỗi nhưng dữ liệu không nhân đôi khi retry.
- [ ] Retry thủ công sau khi bỏ flag thất bại trả kết quả `ALREADY_APPLIED`.
- [ ] Biết tra Pod Events, exit code và logs cho **từng Pod** của một Job.
- [ ] Biết phân biệt Job/Pod state với TaskExecution state và business state.
- [ ] Có kế hoạch backup/retention cho TaskRepository và central logs.
- [ ] Đã kiểm tra time zone, business-date calculation và chính sách chạy bù sau missed schedule.
- [ ] Không coi `backoffLimit`, `Forbid` hoặc `parallelism: 1` là cơ chế exactly-once.

## 26. Kết luận

**Kubernetes Job** phù hợp khi cần chạy một ứng dụng Spring Cloud Task hữu hạn theo yêu cầu; **CronJob** phù hợp khi muốn tạo các Job theo lịch. Điểm mấu chốt không chỉ là làm cho Pod chạy được: một lần launch cần được quan sát từ **Job/Pod**, qua **TaskExecution**, đến **kết quả nghiệp vụ**. Các tầng này có thể cho trạng thái khác nhau khi xảy ra timeout, crash hoặc retry.

Với một `ApplicationRunner` đồng bộ, PostgreSQL TaskRepository bền vững, khóa nghiệp vụ duy nhất và manifest Kubernetes có deadline/retry/resource/security phù hợp, có thể xây dựng tác vụ theo lịch hoặc yêu cầu **có thể theo dõi, vận hành và chạy lại an toàn**. Khi chuyển từ lab sang production, hãy bổ sung migration chính thức, quyền ít nhất, nguồn ngày nghiệp vụ ổn định, telemetry và quy trình xử lý crash windows.

### Tài liệu tham khảo

- [Spring Cloud Task — Reference](https://docs.spring.io/spring-cloud-task/reference/)
- [Spring Cloud Task — Features, DataSource và schema initialization](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud — release train compatibility](https://spring.io/projects/spring-cloud/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes — CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes — Job API reference](https://kubernetes.io/docs/reference/kubernetes-api/batch/job-v1/)
- [Kubernetes — CronJob API reference](https://kubernetes.io/docs/reference/kubernetes-api/batch/cron-job-v1/)
- [kubectl wait](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_wait/)
