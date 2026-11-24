# Đối chiếu BOM, API và thuộc tính giữa các phiên bản Spring Cloud Task

## 1. Vì sao nâng cấp Spring Cloud Task cần đối chiếu nhiều lớp?

**Spring Cloud Task** giúp xây dựng ứng dụng Spring Boot **chạy hữu hạn**: nhập file, đối soát, xuất báo cáo, xử lý theo lịch hoặc theo yêu cầu. Mỗi lần chạy có thể được ghi thành **TaskExecution** trong **TaskRepository**; khi kết hợp **Spring Batch**, ứng dụng còn có JobRepository, StepExecution và checkpoint.

Nâng cấp chỉ bằng cách sửa một dòng version là chưa đủ. Có những trường hợp code biên dịch thành công nhưng khi JVM chạy lại:

- Spring Boot và Spring Cloud thuộc hai **release train không tương thích**.
- JAR runtime chứa Spring Framework, Spring Batch hoặc Spring Integration lệch version so với BOM.
- API, constructor, package hoặc cơ chế auto-configuration đã thay đổi.
- Property cũ không còn được bind, hoặc default thay đổi, làm task ghi metadata sai, không thoát hoặc không trả exit code thích hợp.
- Cấu trúc bảng/sequence của TaskRepository hoặc JobRepository chưa được migration.
- Scheduler retry sau crash, nhưng business data đã commit và bị xử lý lặp.

Vì thế một quy trình nâng cấp an toàn phải kiểm tra chuỗi **BOM → resolved dependencies → API → configuration properties → schema → runtime behavior → rollback**.

Ví dụ, `daily-close-task` chốt doanh thu ngày `2026-11-23`. Bản mới phải tiếp tục ghi TaskExecution, phản ánh chính xác khi Spring Batch Job thất bại, và không ghi thêm doanh thu nếu một lần chạy trước đã commit nhưng JVM chết trước khi repository ghi trạng thái cuối.

## 2. Sáu trục phiên bản cần quản lý

| Trục | Ví dụ | Vai trò |
|---|---|---|
| **Java/JDK** | JDK 17 hoặc bản Java được stack hỗ trợ | Bytecode, runtime, JDBC driver, image |
| **Spring Boot** | `3.5.x`, `4.2.0` | Auto-configuration, dependency management, lifecycle |
| **Spring Cloud release train** | `2025.0.x`, `2025.1.x`, `2026.0.0` | BOM điều phối các project Spring Cloud |
| **Spring Cloud Task** | `3.x`, `5.x` | TaskRepository, TaskExecution, listener, integration |
| **Spring Batch** | `5.x`, `6.x` | Job/Step, JobRepository, API launch/restart |
| **Database/platform** | PostgreSQL, JDBC, SCDF, Kubernetes | DDL metadata, quyền và điều phối tiến trình |

**Spring Cloud release train không phải version Spring Cloud Task.** Version `2026.0.0` là release train/BOM, còn version của module Task trong đó có thể là `5.1.0`.

Không suy ra version Java hoặc Batch chỉ từ version Spring Cloud. **Ma trận hỗ trợ chính thức**, BOM thực sự được import và dependency graph sau resolve là ba nguồn quan trọng nhất.

## 3. Bảng đối chiếu Spring Boot và Spring Cloud

Theo tài liệu phát hành của Spring tại thời điểm biên soạn **24/11/2026**:

| Spring Cloud train | Spring Boot tương thích được công bố | Ghi chú |
|---|---|---|
| `2026.0.0` / Paddington | **4.2.0** | Bao gồm Spring Cloud Task **5.1.0** |
| `2025.1.x` / Oakwood | **4.0.x**; **4.1.x từ 2025.1.2** | Ví dụ train `2025.1.4` dùng Task `5.0.2` |
| `2025.0.x` / Northfields | **3.5.x** | Xác minh patch Task cụ thể trong BOM |
| `2024.0.x` / Moorgate | **3.4.x** | Kiểm tra support/EOL trước khi chọn |
| `2023.0.x` / Leyton | **3.2.x**; **3.3.x từ 2023.0.2** | Dòng cũ, cần lập kế hoạch thay thế |

Ngày **20/11/2026**, Spring công bố Spring Cloud `2026.0.0` dựa trên Spring Boot `4.2.0`; danh sách module của train xác nhận Spring Cloud Task `5.1.0`. Bảng trên chỉ là **ảnh chụp tại một thời điểm**, không bảo đảm mọi patch Spring Boot đều tương thích với mọi service release của cùng train. Khi quyết định nâng cấp, phải xem matrix và release notes của **đúng patch target**.

Nguồn chính thức:

- [Spring Cloud: release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud release train documentation](https://docs.spring.io/spring-cloud-release/reference/)

### Bảng baseline và target cho một dự án

Trước khi thay dependency, lập bảng:

| Thành phần | Baseline | Target | Bằng chứng |
|---|---|---|---|
| JDK build/runtime | `...` | `...` | `java -version` và image digest |
| Boot | `...` | `...` | Plugin/parent POM |
| Cloud train | `...` | `...` | Imported Cloud BOM |
| Task, Batch | `...` | `...` | Resolved dependency graph |
| Framework/Integration | `...` | `...` | Transitive dependencies |
| PostgreSQL driver/DB | `...` | `...` | Driver JAR và server version |
| Task/Batch schema | `...` | `...` | DDL và migration history |

Dấu `...` là chỗ người học điền từ build thật; không phải dữ liệu đã được xác minh. Phân biệt **version được khai báo** và **version được resolve**; cả hai có thể khác khi có override hoặc transitive dependency.

## 4. BOM là gì, Boot BOM khác Cloud BOM ra sao?

**BOM (Bill of Materials)** chứa tập ràng buộc hoặc quản lý version được kiểm thử phối hợp. Import BOM **không tự thêm** tất cả các thư viện vào ứng dụng.

~~~mermaid
flowchart TD
    B["Spring Boot parent/plugin/BOM"]
    C["Spring Cloud dependencies BOM"]
    B --> D["Spring Boot, Framework và nhiều dependency được Boot quản lý"]
    C --> E["Spring Cloud Task và các project Spring Cloud"]
    D --> G["Resolved runtimeClasspath"]
    E --> G
    G --> R["Spring Cloud Task JVM"]
    R --> T["TaskRepository / Batch JobRepository"]
~~~

- **Boot BOM** quản lý dependency trong hệ Spring Boot, gồm nhiều thư viện core, logging, JDBC, Spring Batch tùy version.
- **Cloud BOM** điều phối Spring Cloud modules (Task, Config, Stream, v.v.) theo release train.
- **Custom version override** có thể thắng BOM hoặc gây conflict. Dù ứng dụng chạy được ở máy phát triển, runtime image chưa chắc giống development graph.
- **Force/enforcedPlatform** trong Gradle có thể thay cơ chế chọn version. Không bật để “chắc chắn có bản mới” nếu chưa phân tích tác động.

Với Spring Batch, tránh tự ép phiên bản major không thuộc stack Boot/Cloud mục tiêu. Khi cần version đặc biệt vì CVE, ghi rõ lý do, kiểm ma trận hỗ trợ và chạy integration tests đầy đủ.

## 5. Ví dụ Maven import Cloud BOM

Ví dụ cho một **đích đã được công bố**: Spring Boot `4.2.0` và Spring Cloud `2026.0.0`. Đây là POM học tập, chưa có test plugins hoặc cấu hình deployment riêng:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>daily-close-task</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>${spring-cloud.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
</project>
~~~

`java.version=17` là **tham số ví dụ**, không thay thế kiểm tra JDK minimum của Boot và các dependency trong build thật. Khi nâng target, xem yêu cầu Java release trước khi chọn build/runtime image.

Không khai báo version trực tiếp cho `spring-cloud-starter-task` nếu muốn Cloud BOM quản lý. Nếu buộc override, phải ghi rõ artifact nào và vì sao, đồng thời lưu dependency tree chứng minh kết quả.

### Kiểm tra version đã resolve với Maven

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn dependency:tree -Dincludes=org.springframework.batch
mvn dependency:tree -Dincludes=org.springframework
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

Các lệnh là hướng dẫn cho dự án, không phải bằng chứng đã chạy trên workspace này. `effective-pom` giúp xem cấu hình sau kế thừa; `dependency:tree` kiểm tra version được chọn. Tìm `spring-cloud-task-core`, `spring-batch-core` và `spring-core` thay vì chỉ nhìn starter.

## 6. Ví dụ Gradle Groovy DSL: hai cách quản lý BOM

**Cách 1 — Spring dependency-management plugin:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2026.0.0'
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Cách 2 — Gradle native platforms:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.2.0')
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2026.0.0')

    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Mục tiêu là một **resolved graph tương thích**, không phải chọn cách import nào “mới hơn”. Nếu có version catalog hoặc multi-module build, kiểm tra constraints ở **mọi module** thực sự đóng gói JAR cuối.

Kiểm tra:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-task-core \
  --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-batch-core \
  --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core \
  --configuration runtimeClasspath
~~~

Trên Windows có thể chạy `gradlew.bat`. Không chỉ kiểm `compileClasspath` vì driver và thư viện runtimeOnly có thể gây `NoClassDefFoundError` hoặc `NoSuchMethodError` khi tiến trình khởi động.

## 7. Phân tích API: không chỉ compile mà còn phải chạy thử lifecycle

Các API đáng chú ý của Spring Cloud Task:

| Nhóm API | Chức năng | Kiểm tra giữa baseline/target |
|---|---|---|
| `TaskExecution` | Metadata một lần chạy | Kiểu getter, nullability, thời gian và exit code |
| `TaskRepository` và `TaskExplorer` | Lưu/đọc TaskExecution | DataSource/transaction, SQL, paging/lookup |
| `TaskExecutionListener` | Callback startup, failed, end | Chữ ký, thời điểm và exception behavior |
| `@BeforeTask`/`@AfterTask`/`@FailedTask` | Annotation listener | Package, auto-registration, bean lifecycle |
| `TaskConfigurer`/`DefaultTaskConfigurer` | Tùy chỉnh repository/schema | Constructor, bean wiring, table prefix |
| `ApplicationRunner`/`CommandLineRunner` | Đơn vị công việc hữu hạn | Order, lỗi, async, shutdown |
| `ExitCodeGenerator`/`ExitCodeExceptionMapper` | Mã thoát process/task | Exception có ra mã ngoài 0 không |
| `JobOperator`/`JobLauncher` | Spring Batch | API, đồng bộ/bất đồng bộ, restart |

**Source compatibility** có nghĩa code còn biên dịch được. **Behavior compatibility** có nghĩa task vẫn ghi TaskExecution, chốt `END_TIME`, trả mã thoát phù hợp và thoát JVM đúng. Một thay đổi lớn ở auto-configuration có thể **không gây lỗi compile** nhưng làm TaskRepository không còn dùng đúng DataSource.

### Đừng mở Javadoc latest cho một JAR cũ

Luôn so **Javadoc/reference của baseline** với **Javadoc/reference của target**. Mẫu audit:

~~~text
API                           Baseline       Target        Evidence / action
TaskExecution.getExitCode     X              ?             compile + nullable test
TaskExecutionListener         X              ?             callback integration test
TaskConfigurer constructor    X              ?             compile + context test
JobLauncher / JobOperator     Batch 5.x      Batch 6.x?    migration + restart test
~~~

Dấu `?` nghĩa là **phải xác minh**; đừng suy đoán đã có breaking change nếu chỉ thấy major version mới.

## 8. Ví dụ API dễ gặp: Spring Batch 5 sang Spring Batch 6

Ứng dụng Task thường chứa một hoặc nhiều Spring Batch Job. Khi nâng Boot/Batch major, cần kiểm tra cơ chế launch.

Javadoc **Spring Batch 6** đánh dấu `org.springframework.batch.core.launch.JobLauncher` là **`@Deprecated(since="6.0", forRemoval=true)`**, và khuyến nghị chuyển sang `JobOperator`. API chính xác của target patch phải được đọc trước khi refactor.

Một đoạn code quen thuộc trong Batch 5:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

if (execution.getStatus() != BatchStatus.COMPLETED) {
    throw new IllegalStateException(
        "Job did not complete: " + execution.getStatus());
}
~~~

Đoạn này **chỉ chính xác như cách quan sát kết quả cuối khi JobLauncher là synchronous**. Nếu chạy async, `run` có thể trả về khi Job còn `STARTING`/`STARTED`. Với Batch 6, không chỉ đổi import `JobLauncher` thành `JobOperator` rồi giữ giả định cũ; phải xem method signature và completion contract của release.

Những tình huống cần test:

1. Batch Job hoàn tất, task trả mã thoát đúng.
2. Job `FAILED` nhưng caller có thể vẫn nhận một `JobExecution`; task không được lặng lẽ exit 0 nếu yêu cầu báo lỗi.
3. Restart với **cùng identifying JobParameters** tiếp tục JobInstance cũ khi hợp lệ.
4. Chạy lại JobInstance đã `COMPLETED` bị từ chối hoặc được wrapper xử lý `ALREADY_COMPLETED` theo chính sách.
5. Step ExecutionContext/checkpoint cũ còn đọc được sau schema migration.

Tài liệu: [Spring Batch JobLauncher API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobLauncher.html) và [JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html).

## 9. Configuration properties: đối chiếu key, default và behavior

Các property của Spring Cloud Task có thể được **giữ nguyên**, **deprecated/renamed** hoặc **thay đổi behavior/default** giữa các dòng phiên bản.

| Property/nhóm | Ý nghĩa | Cần kiểm |
|---|---|---|
| `spring.cloud.task.autoconfiguration.enabled` | Bật/tắt auto-configuration Task theo phiên bản hỗ trợ | Bean TaskRepository có còn tự tạo không |
| `spring.cloud.task.initialize-enabled` | Bật/tắt khởi tạo bảng metadata | Runtime có cố chạy DDL không |
| `spring.cloud.task.initialize.enable` | Legacy được tài liệu cũ đánh dấu deprecated | Thay bằng `initialize-enabled` khi target hỗ trợ |
| `spring.cloud.task.tablePrefix` / `table-prefix` | Prefix bảng TaskRepository | SQL và DDL có khớp không |
| `spring.cloud.task.closecontextEnabled` | Đóng context sau task | Binding/default và ảnh hưởng executor |
| `spring.cloud.task.single-instance-enabled` | Giới hạn task cùng tên chạy song song | Lock table, transaction và timeout |
| `spring.cloud.task.single-instance-lock-ttl` | TTL lock single-instance | Đơn vị thời gian, xử lý crash |
| `spring.cloud.task.parent-execution-id` | Liên kết task cha–con | Truyền/nhận ID đúng namespace |
| `spring.cloud.task.external-execution-id` | Correlation với orchestrator | Không nhầm TaskExecutionId |
| `spring.cloud.task.batch.fail-on-job-failure` | Batch Job FAILED làm task exit khác 0 | Đúng runner/integration và exit code |
| `spring.cloud.task.batch.applicationRunnerOrder` | Thứ tự runner tích hợp Batch | Không nhầm order của các Step |
| `spring.batch.job.name` | Chọn Job của Spring Boot | Không nhầm key cũ hoặc custom launcher |

Bảng này là **danh sách kiểm tra**, không cam kết mọi property có cùng default trong mọi phiên bản. Tài liệu có thể viết **camelCase**; Spring Boot có **relaxed binding** để nhận dạng kebab-case tương ứng. Nhưng **relaxed binding không bảo đảm alias đã bị xóa vẫn hoạt động**.

Với mỗi key phải kiểm ba điều:

- **Key/type:** target release có nhận không, tên/kiểu có đổi không?
- **Default:** khi không set, giá trị cuối là gì? Profile nào ghi đè?
- **Runtime:** kết quả thực tế có đúng không, chẳng hạn schema init, lock hoặc exit policy?

Property chưa được bind có thể **bị bỏ qua mà không gây lỗi startup** trong một số cấu hình. Đó là lý do cần smoke test.

## 10. Diff properties bằng metadata và reference docs

Nhiều JAR của Spring Boot/Cloud chứa metadata:

~~~text
META-INF/spring-configuration-metadata.json
META-INF/additional-spring-configuration-metadata.json
~~~

Metadata có thể cung cấp key, type, default, deprecation và replacement hints. Nó hữu ích để so baseline/target, nhưng không phải mọi property custom hoặc điều kiện auto-configuration đều được mô tả đầy đủ.

Quy trình:

1. Resolve hai bộ artifact theo BOM **baseline/target**.
2. Lấy metadata từ JAR **đúng version** của Spring Cloud Task, Spring Boot và Batch.
3. Diff `added/removed/deprecated/type/default`.
4. So với các key được dùng trong config thực tế, không chỉ với mọi key của framework.
5. Đọc target reference/migration notes để hiểu ý nghĩa.
6. Test binding và hành vi có hiệu lực trong một tiến trình Spring Cloud Task.

Ví dụ mẫu audit:

| Property | Baseline | Target | Hành động |
|---|---|---|---|
| `spring.cloud.task.initialize-enabled` | Có | Xác minh có | Giữ `false` nếu migration ngoài quản lý |
| `spring.cloud.task.initialize.enable` | Legacy | Deprecated/removed? | Xác minh, đổi sang key mới |
| `spring.cloud.task.table-prefix` | Có | Xác minh có | Kiểm DDL và SQL prefix |
| `spring.cloud.task.batch.fail-on-job-failure` | Có khi dùng integration | Xác minh có | Test Job FAILED và JVM code |
| `spring.batch.job.names` | Cấu hình cũ | Có thể không phù hợp | Kiểm `spring.batch.job.name` của target |
| `myapp.batch.timeout` | Custom | Custom | Test `@ConfigurationProperties` |

Dấu `?` là hạng mục kiểm tra, không phải thông báo API/property đã bị xóa.

### Ví dụ chuyển cấu hình có kiểm chứng

Config legacy:

~~~properties
spring.cloud.task.initialize.enable=false
spring.cloud.task.tablePrefix=OPS_TASK_
spring.cloud.task.batch.jobNames=closeDayJob
~~~

Một cấu hình đích **đề xuất để kiểm thử**:

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
      table-prefix: OPS_TASK_
  batch:
    job:
      name: closeDayJob
~~~

Nếu dự án tự gọi Batch Job từ `ApplicationRunner`, có thể cần tắt auto-launch bằng `spring.batch.job.enabled=false` **khi property đó được target hỗ trợ**. Không bật cả auto-launch và custom runner nếu chỉ muốn chạy một lần.

## 11. Bean graph và auto-configuration có thể đổi dù tên API không đổi

Sau khi nâng version, kiểm tra những điều kiện làm Spring Boot tự tạo bean:

- Starter/dependency có mặt không?
- `@EnableTask`, custom `TaskConfigurer` hoặc cấu hình cũ có can thiệp?
- `TaskRepository` dùng DataSource nào khi có nhiều DataSource?
- Bean transaction manager cho TaskRepository, Batch JobRepository và business service có đúng không?
- Có thêm `@EnableBatchProcessing` làm thay đổi trách nhiệm auto-config không?
- Có dependency legacy dùng `javax.*` trong một stack yêu cầu `jakarta.*` hay không?

Cần ba lớp test:

| Lớp | Kiểm chứng |
|---|---|
| **Compile** | API Java/constructor/method còn hợp lệ |
| **ApplicationContext** | Các bean và property được bind như dự kiến |
| **End-to-end process** | Task runner chạy hữu hạn, ghi TaskExecution, thoát với mã đúng |

Trong một JVM task, lỗi phổ biến chỉ xuất hiện **khi đóng context** hoặc khi repository cập nhật kết quả cuối. Vì vậy một test chỉ load context mà không chạy runner không đủ.

## 12. DDL TaskRepository có thể thay đổi giữa các bản

Các đối tượng metadata quen thuộc:

~~~text
TASK_EXECUTION
TASK_EXECUTION_PARAMS
TASK_TASK_BATCH        (khi có tích hợp Task–Batch)
TASK_LOCK              (khi dùng single-instance)
TASK_SEQ hoặc cơ chế cấp ID tương ứng
~~~

Tên và cơ chế thực tế phụ thuộc DDL của **đúng version và database dialect**. Một release có thể thay cột, index, sequence hoặc SQL. Khi table prefix giữ nguyên `TASK_`, cũng **không thể kết luận schema hoàn toàn không đổi**.

| Hạng mục DDL | Phải so |
|---|---|
| Tables/columns | Tên, kiểu, nullability, độ dài, default |
| Keys và indexes | PK/FK/unique, hiệu suất/khóa |
| Sequence/table cấp ID | Kiểu object, tên, giá trị hiện tại |
| Timestamp và message | Kiểu thời gian, serialization, độ dài error |
| Table prefix/schema | Tên runtime DAO tham chiếu có khớp migration? |
| Permissions | `SELECT`/`INSERT`/`UPDATE`/quyền sequence |
| Migration history | Bản DDL nào đã chạy, có chạy một phần không? |

PostgreSQL có thể dùng để kiểm loại đối tượng metadata:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'task_meta'
ORDER BY c.relname;
~~~

`relkind='S'` là native sequence; `relkind='r'` là table. `TASK_SEQ` không mặc định là native sequence: phải đọc DDL/incrementer thực tế trước khi cấp quyền hoặc sửa cấu trúc.

**Không xóa metadata cũ để “cho startup chạy được”.** Xóa TaskExecution/JobExecution có thể phá audit, lineage cha–con và restart checkpoint.

## 13. Spring Batch JobRepository là một schema khác

Nếu ứng dụng có Spring Batch, phải đối chiếu cả hai nhóm:

~~~text
task_meta/
  TASK_EXECUTION
  TASK_EXECUTION_PARAMS
  TASK_TASK_BATCH

batch_meta/
  BATCH_JOB_INSTANCE
  BATCH_JOB_EXECUTION
  BATCH_JOB_EXECUTION_PARAMS
  BATCH_STEP_EXECUTION
  BATCH_STEP_EXECUTION_CONTEXT
  ...
~~~

Spring Batch cần so **identifying JobParameters**, `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, transaction và serializer.

Một JobInstance được định danh theo **tên Job + bộ identifying parameters**. Nếu retry mà đưa timestamp ngẫu nhiên vào `run.id` identifying, Batch sẽ tạo JobInstance mới, **không phải restart đúng nghĩa** của kỳ cũ.

Kiểm thử theo bảng:

| Kịch bản | Batch metadata | Task metadata |
|---|---|---|
| Job hoàn tất | `COMPLETED` | TaskExecution kết thúc thành công theo policy |
| Step thất bại | `FAILED`, checkpoint đã commit | Exit code phản ánh lỗi khi cấu hình |
| Restart same key | Cùng JobInstance, JobExecution mới khi hợp lệ | TaskExecution mới |
| Job đã completed | Không tự chạy lại cùng JobInstance | Có thể có Task attempt bị từ chối |
| JVM bị SIGKILL | Có thể còn `STARTED` | Có thể chưa có `END_TIME` |

**Nâng Batch mà không kiểm restart từ checkpoint thật** là rủi ro lớn, đặc biệt với task xử lý dữ liệu dài hoặc phát side effect ra ngoài CSDL.

## 14. Migration: chạy DDL riêng, rồi mới chạy Task

Khi schema do Flyway/Liquibase/DBA quản lý, không nên để mọi JVM task tự chạy `CREATE/ALTER TABLE` tại startup.

~~~mermaid
sequenceDiagram
    participant P as CI/CD
    participant M as Schema Migrator
    participant DB as Database
    participant S as Scheduler
    participant T as Spring Cloud Task

    P->>DB: Backup/snapshot + kiểm migration version
    P->>M: Chạy bằng migration role
    M->>DB: DDL, sequence, index, GRANT
    DB-->>M: Commit migration
    M-->>P: Thành công
    P->>S: Cho chạy artifact mới
    S->>T: Launch task bằng runtime role
    T->>DB: TaskRepository/Batch/business DML
    T-->>S: Exit code
~~~

Ví dụ trên những release có hỗ trợ các property:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-close-task
      initialize-enabled: false
  batch:
    jdbc:
      initialize-schema: never
  sql:
    init:
      mode: never
~~~

`spring.cloud.task.initialize-enabled` thuộc Task; `spring.batch.jdbc.initialize-schema` thuộc Spring Batch auto-init do Boot quản lý; `spring.sql.init.mode` là initializer SQL chung của Boot. Chúng **không thay thế nhau**. Phải xác minh version target, đặc biệt khi có các starter Flyway/Liquibase khác.

Các nguyên tắc:

- Migration chạy bằng role có DDL privilege; runtime chỉ có quyền DML cần thiết.
- Diff DDL phiên bản cũ và mới theo **dialect**, không dùng script của H2 cho PostgreSQL production.
- Có backup và **restore rehearsal**, không chỉ cách rollback application artifact.
- Nếu worker cũ và mới cùng hoạt động, thiết kế DDL **expand → migrate → contract** khi cần.
- Smoke test TaskRepository và Batch JobRepository bằng credential runtime sau migration.

## 15. Mã thoát và single-instance là những behavior dễ thay đổi

### 15.1. Exit code của Batch Job

Trong tích hợp Spring Cloud Task/Batch có property:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Nếu Job Batch ở trạng thái `FAILED`, tính năng này có thể khiến task trả mã thoát khác 0. Phải kiểm phiên bản, integration và runner thực tế. Không chỉ tin vào một dòng log có chữ `FAILED`.

### 15.2. Đóng context

Property `spring.cloud.task.closecontextEnabled` có thể điều khiển đóng context sau task theo phiên bản. Khi ứng dụng tự dùng `SpringApplication.exit(context)`, kiểm tra tránh close hai lần gây hành vi không mong muốn. Nếu có executor, telemetry exporter hoặc message consumer, phải chờ/đóng tài nguyên đúng lifecycle.

### 15.3. Single-instance

Các key có trong nhiều bản tài liệu:

~~~properties
spring.cloud.task.single-instance-enabled=true
spring.cloud.task.single-instance-lock-ttl=60000
spring.cloud.task.single-instance-lock-check-interval=500
~~~

Giá trị **chỉ minh họa**, cần xác minh đơn vị thời gian, TTL/default và thuật toán lock của phiên bản đích. Test hai JVM cùng tên task, worker bị kill và lease/lock timeout.

Single-instance theo task name **không thay thế unique business key**. Một task khác tên vẫn có thể chốt cùng ngày, hoặc retry có thể lặp side effect trước khi TaskRepository chốt trạng thái.

## 16. Quy trình nâng cấp an toàn theo từng pha

~~~mermaid
flowchart TD
    A["Chụp baseline"] --> B["Chọn Boot + Cloud train tương thích"]
    B --> C["So release notes, API, properties"]
    C --> D["Đổi BOM, kiểm resolved dependencies"]
    D --> E["Compile + context + config tests"]
    E --> F{"Đạt?"}
    F -- "Không" --> X["Sửa trên staging"]
    F -- "Có" --> G["Migration schema staging"]
    G --> H["Integration Task/Batch + crash tests"]
    H --> I{"Đạt?"}
    I -- "Không" --> X
    I -- "Có" --> J["Canary bằng business key an toàn"]
    J --> K["Quan sát kết quả, error, latency"]
    K --> L{"Đạt tiêu chí?"}
    L -- "Có" --> M["Rollout có kiểm soát"]
    L -- "Không" --> N["Stop/rollback hoặc forward-fix"]
~~~

### A. Inventory trước nâng cấp

- Boot plugin/parent, Cloud BOM, Task/Batch/Framework đã resolve.
- Java build/runtime, Docker image digest, JDBC driver và database server.
- Các `spring.cloud.task.*` và `spring.batch.*` đang được dùng; không lưu giá trị secret.
- TaskRepository/JobRepository DDL, migration version và trạng thái sequence.
- Mẫu TaskExecution thành công, lỗi và Batch JobExecution/StepExecution.
- Scheduler concurrency, pool connection, resource/timeout, mã thoát OS.

### B. Thực hiện dependency upgrade

- Đổi Boot/Cloud **theo ma trận**, không ép từng Spring artifact lên latest tùy ý.
- Xóa version override không còn cần; lưu lý do cho override bắt buộc.
- Kiểm runtimeClasspath, không chỉ compileClasspath.
- Nếu major upgrade, đọc migration guide của **Boot, Cloud Task, Batch** và JDK.

### C. Test API, config và database

- Compile những phần dùng `TaskExecutionListener`, `TaskConfigurer`, JobOperator và custom DAO.
- Diff configuration metadata, thử key mới/cũ và kiểm default.
- Kiểm auto-configuration bean graph khi có nhiều DataSource.
- Chạy migration bằng role riêng, smoke test bằng runtime role.
- Chạy test thành công, thất bại, retry, concurrent và SIGKILL.

### D. Canary và rollout

- Chạy một workload có business key rõ và an toàn.
- Đối chiếu logs, TaskExecution, JobExecution, business output và exit code.
- Nếu có mismatch schema hoặc error tăng, dừng rollout, kích hoạt rollback/forward-fix theo kế hoạch.

## 17. Bảng test bắt buộc trước khi duyệt upgrade

| Bài kiểm thử | Tiêu chí đạt |
|---|---|
| Dependency graph | Không có Spring Cloud/Batch/Framework lệch version ngoài dự kiến |
| Boot context | TaskRepository/TaskExplorer/DataSource/TransactionManager đúng bean |
| Task thành công | Có start/end và exit code đúng |
| Task thất bại | Exception được quan sát, mã thoát theo policy |
| Task ID allocation | Nhiều task không trùng ID, sequence/table cấp ID hoạt động |
| Runtime DML-only | Startup không cố DDL nếu migration ngoài quản lý |
| Batch thất bại | `JobExecution.status=FAILED`, task exit phản ánh lỗi khi yêu cầu |
| Batch restart | Identifying parameters ổn định, checkpoint tiếp tục đúng |
| Single-instance | Hai JVM cùng tên xử lý lock như thiết kế |
| Async work | Runner chờ future, không thoát sớm/treo vô hạn |
| Crash sau commit | Retry không nhân đôi dữ liệu |
| Parent/child | Task lineage và Batch mapping đúng khi có worker |
| Security | Secret không lộ qua TaskExecution arguments/log |
| Observability | Trace/log/metrics và repository correlation đúng |

**Không dừng ở test “task chạy một lần thành công”.** Nhiều regression chỉ lộ ở `onTaskFailed`, transaction rollback, Batch restart, shutdown và JVM exit code.

## 18. Chẩn đoán lỗi phổ biến sau nâng cấp

| Triệu chứng | Nghi vấn | Cách kiểm |
|---|---|---|
| `NoSuchMethodError` / `NoClassDefFoundError` | Binary API/dependency lệch | Dependency tree/Insight trong runtime image |
| `UnsupportedClassVersionError` | Java runtime thấp | `java -version` ngay trong container |
| TaskRepository bean không xuất hiện | Auto-config hoặc TaskConfigurer đổi | Condition report, starter và bean graph |
| Property không hiệu lực | Key deprecated/removed hoặc bị override | Metadata diff, active profiles, target docs |
| Runtime cố `CREATE TABLE` | Init property/bean khác trước | SQL logs, migration config |
| `relation TASK_EXECUTION does not exist` | DDL/schema/tablePrefix sai | Kiểm catalog, search path, DataSource |
| `permission denied for sequence` | ID allocator hoặc grants khác | Loại sequence/table và quyền runtime |
| Job Batch bị lỗi launch | API/schema/params chưa tương thích | JobOperator, JobRepository, identifying params |
| Batch FAILED nhưng process exit 0 | Mapping Batch failure không bật | Test `fail-on-job-failure` và exit code thật |
| Task vẫn Running sau khi runner xong | Web server/executor giữ JVM | `WebApplicationType.NONE`, thread/shutdown |
| Lock single-instance bị kẹt | TTL/lock dao/schema thay đổi | Kiểm Task lock config và crash test |
| Retry nhân đôi dữ liệu | Business idempotency hoặc JobInstance identity sai | Unique business key, checkpoint, outbox |
| Không đọc được checkpoint cũ | DDL/serializer/Batch migration | So ExecutionContext với schema target |

**Đừng “sửa” bằng cách xóa bảng metadata hoặc cấp quyền database quá rộng.** Điều đó có thể che lỗi, mất lịch sử task/job và phá khả năng restart.

## 19. Thực hành: xây bảng đối chiếu cho một đợt nâng cấp

Giả sử dự án ở Spring Boot `3.5.x` + Spring Cloud `2025.0.x`, muốn đánh giá nâng lên Boot `4.2.0` + Cloud `2026.0.0`. Đây là **kịch bản học tập**; việc nhảy major trực tiếp có thể không phù hợp mọi ứng dụng, nên phải đọc migration guides và cân nhắc bước trung gian.

1. **Lưu baseline**: JDK/image, BOM, Task/Batch version, runtime graph, DDL và property keys.
2. **Chọn target**: kiểm matrix, security support, JDK và JDBC driver.
3. **Đổi BOM** trong một nhánh riêng, không override Task version theo cảm tính.
4. **Phân tích API**: TaskExecutionListener, TaskConfigurer, Spring Batch JobLauncher/JobOperator.
5. **Diff property**: initialization, table prefix, Batch job name, exit policy, closecontext, single instance.
6. **Migration staging**: đối chiếu schema TaskRepository/JobRepository và checkpoint cũ.
7. **Smoke test** với ứng dụng non-web hữu hạn:

~~~bash
java -jar daily-close-task.jar \
  --spring.main.web-application-type=none \
  --date=2026-11-23
~~~

8. **Gây lỗi** ở runner và một Batch Step, kiểm metadata và OS exit code.
9. **Retry cùng business key**, xác minh không ghi dữ liệu trùng; test JobInstance restart.
10. **Canary** bằng dữ liệu an toàn, theo dõi logs/metrics/TaskRepository/JobRepository trước rollout.

Bảng bàn giao một đợt nâng cấp:

| Hạng mục | Bằng chứng |
|---|---|
| Ma trận Boot/Cloud | Link train và target patch |
| Dependency đã resolve | Maven/Gradle report |
| API/migration notes | Danh sách call sites và thay đổi |
| Property diff | Key/type/default và binding test |
| Schema | Migration version, DDL diff, permissions |
| Runtime | TaskExecution + process exit code |
| Batch | JobExecution/StepExecution restart result |
| Business state | Unique key và test idempotency |
| Rollback | Image digest, backup/restore rehearsal |

## 20. Các ngộ nhận thường gặp

### “Cloud train 2026.0.0 thì Task cũng là 2026.0.0”

**Sai.** BOM train có version riêng; Spring Cloud Task trong train `2026.0.0` là `5.1.0`.

### “Build pass là đã tương thích”

**Chưa đủ.** Runtime repository, SQL, exit code và Batch checkpoint còn phải được kiểm chứng.

### “Tên property giống nhau nghĩa là default và behavior giống”

**Không chắc.** Property binder, profile, bean condition và default có thể thay đổi.

### “Chuyển camelCase sang kebab-case sẽ giữ mọi property cũ”

**Không đúng với key đã xóa.** Relaxed binding không thay thế migration notes.

### “Spring Batch restart tự bảo đảm exactly-once”

**Không.** Checkpoint chỉ có tác dụng trong ranh giới đã cấu hình; side effect ngoài transaction và khóa nghiệp vụ vẫn cần idempotency.

### “Rollback JAR là đủ khi schema mới lỗi”

**Sai nếu migration không tương thích ngược.** Phải có kế hoạch rollback/forward-fix cả database, worker cũ và mới.

## 21. Checklist trước production

- [ ] Đã xác định baseline và target cho Java, Boot, Cloud, Task, Batch, driver và DB.
- [ ] Boot/Cloud release train tương thích theo nguồn chính thức.
- [ ] BOM và dependency graph đã resolve, không có override ngoài ý muốn.
- [ ] API public/customization đã compile và kiểm deprecated/removed methods.
- [ ] Đã đối chiếu property keys, default, type, aliases và binding behavior.
- [ ] TaskRepository/JobRepository DDL đúng version, đúng dialect, có migration.
- [ ] Runtime role chỉ có quyền cần, sequence và tablePrefix khớp schema.
- [ ] Test task thành công, lỗi, mã thoát, context shutdown và async.
- [ ] Test Batch Job failure, identifying parameters, restart/checkpoint.
- [ ] Test concurrent task, single-instance lock và crash recovery.
- [ ] Business idempotency/unique key bảo vệ retry.
- [ ] Secret không xuất hiện trong command-line arguments/TaskRepository/log.
- [ ] Đã chạy canary có tiêu chí đánh giá và kế hoạch rollback/forward-fix.

**Kết luận:** Để nâng cấp **Spring Cloud Task** đáng tin cậy, hãy bắt đầu từ cặp **Spring Boot ↔ Spring Cloud BOM** được hỗ trợ, xác nhận **artifact versions thực tế**, đối chiếu **API và cấu hình còn hiệu lực**, rồi kiểm chứng **DDL, lifecycle, exit code, Spring Batch và retry**. Chỉ khi một task hữu hạn thực sự chạy, ghi trạng thái, khôi phục và hoàn tất nghiệp vụ đúng mới có thể xem nâng cấp đạt về mặt vận hành.

### Tài liệu tham khảo

- [Spring Cloud — release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Release reference](https://docs.spring.io/spring-cloud-release/reference/)
- [Spring Cloud Task reference](https://docs.spring.io/spring-cloud-task/reference/)
- [Spring Cloud Task 3.2 versioned reference](https://docs.spring.io/spring-cloud-task/reference/3.2/)
- [Spring Cloud Task Batch integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Boot dependency management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot database initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Batch JobLauncher API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobLauncher.html)
- [Spring Batch metadata schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
