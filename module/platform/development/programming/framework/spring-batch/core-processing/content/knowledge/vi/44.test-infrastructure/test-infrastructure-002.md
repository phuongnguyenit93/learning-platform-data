# Embedded database cho metadata trong kiểm thử Spring Batch

## 1. Vì sao test Spring Batch cần một metadata database?

Spring Batch không chỉ đọc, xử lý và ghi dữ liệu nghiệp vụ. Framework còn quản lý **metadata của từng lần chạy** để trả lời những câu hỏi như:

- Job nào đã chạy, với bộ tham số nào?
- `JobInstance` này đã có `JobExecution` nào? Lần chạy trước thành công, thất bại hay bị dừng?
- Mỗi step chạy bao nhiêu lần, đọc/ghi bao nhiêu item và commit bao nhiêu chunk?
- Checkpoint nào đã được lưu trong `ExecutionContext` để reader/writer có thể tiếp tục khi restart?
- Có được tạo thêm một lần chạy với cùng identifying `JobParameters` hay không?

Các câu trả lời này chủ yếu được quản lý bởi **`JobRepository`**, với cơ chế JDBC thông thường lưu xuống các bảng metadata trong một relational database. `JobExplorer` cung cấp API đọc lại metadata phục vụ quan sát và kiểm tra.

Trong môi trường test, ta thường không muốn phụ thuộc vào PostgreSQL/Oracle/SQL Server đang vận hành. Một **embedded database** như H2 hoặc HSQLDB giúp tạo hệ thống metadata SQL gọn, khởi động cùng test, dễ cách ly và dọn dẹp.

Bài này tập trung vào **embedded database cho metadata** trong hạ tầng kiểm thử Spring Batch, không nhầm nó với database chứa dữ liệu khách hàng, hóa đơn hoặc dữ liệu nghiệp vụ mà batch đang xử lý.

### Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích vai trò của metadata database trong vòng đời `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`.
2. Thiết lập H2 embedded in-memory với Spring Boot và Spring Batch JDBC repository.
3. Khởi tạo đúng schema metadata và tránh các lỗi thiếu bảng, trùng schema, sai phiên bản.
4. Chạy integration test bằng `@SpringBatchTest` và `JobLauncherTestUtils`, sau đó kiểm tra metadata qua `JobExplorer` hoặc `JdbcTemplate`.
5. Cách ly dữ liệu giữa các bài test và giữa những lần tạo `ApplicationContext`.
6. Hiểu giới hạn của H2 khi kiểm thử transaction, concurrency, restart, locking và khác biệt SQL dialect so với database production.

Các ví dụ dưới đây theo **Java 17+, Spring Boot 3.x, Spring Batch 5.x, JUnit 5 và Gradle Groovy DSL**. Một số API/configuration thay đổi giữa các phiên bản; khi dùng Spring Batch 6.x cần đối chiếu bộ API kiểm thử của phiên bản đó.

---

## 2. Phân biệt database metadata với database nghiệp vụ

Hình dung một job nhập đơn hàng:

```text
                 +-------------------------+
                 |     JobLauncher         |
                 +------------+------------+
                              |
                              v
                 +-------------------------+
                 |     JobRepository       |
                 |  metadata / checkpoint  |
                 +------------+------------+
                              |
                              v
              +-------------------------------+
              | Embedded H2 (test metadata)   |
              | BATCH_JOB_INSTANCE            |
              | BATCH_JOB_EXECUTION           |
              | BATCH_STEP_EXECUTION          |
              | BATCH_*_EXECUTION_CONTEXT     |
              +-------------------------------+

               orderImportJob / orderStep
                         |
             +-----------+-----------+
             |                       |
             v                       v
     business input             business output
     CSV / API / DB             file / DB / queue
```

**Metadata database** lưu thông tin để Spring Batch vận hành và restart. **Business database** lưu dữ liệu do job xử lý. Hai vai trò có thể cùng một cơ sở dữ liệu vật lý hoặc nằm trên các data source riêng; test phải biết đang thay thế cái nào.

| Hạng mục | Metadata database | Business database |
| --- | --- | --- |
| Chủ sở hữu logic | `JobRepository` / Spring Batch | Repository, reader, writer, DAO của ứng dụng |
| Nội dung | Job instance, execution, step execution, parameters, context | Customer, order, invoice, dữ liệu đầu vào/đầu ra |
| Schema mặc định | Các bảng `BATCH_*` của Spring Batch | Schema riêng của ứng dụng |
| Test với H2 có ích khi | Kiểm tra vòng đời job, step, checkpoint, restart cơ bản | Test truy vấn/ghi dữ liệu nghiệp vụ tương thích H2 |
| Điều H2 không đảm bảo | Giống hệt locking/transaction của production DB | Giống hệt SQL dialect, stored procedure, index, kiểu dữ liệu của production DB |

Ví dụ: job đọc file CSV và ghi kết quả ra file JSON có thể dùng **một H2 duy nhất** để chứa metadata, vì dữ liệu nghiệp vụ nằm ở file. Nếu job dùng PostgreSQL với các câu SQL đặc thù, có thể vẫn dùng H2 cho **metadata** trong một số test, nhưng các bài kiểm thử tương thích truy vấn nghiệp vụ cần PostgreSQL thật hoặc Testcontainers.

### 2.1. “Embedded” và “in-memory” có phải một không?

Không hoàn toàn:

- **Embedded** nghĩa là database engine chạy cùng tiến trình ứng dụng/test, không yêu cầu database server riêng.
- **In-memory** nghĩa là database lưu dữ liệu trong RAM, thường mất khi engine đóng hoặc JVM kết thúc.
- H2 còn có **file mode**, vẫn chạy embedded nhưng lưu data xuống file trên ổ đĩa.
- H2 có thể chạy server mode, khi ấy không còn là kiểu embedded đơn giản được trình bày ở đây.

Với các test cần bắt đầu ở trạng thái trống, **embedded in-memory** là lựa chọn quen thuộc. Với test restart **ngay trong cùng JVM**, database in-memory vẫn dùng được miễn là các lần chạy cùng kết nối đến **một database instance còn sống**. Test restart sau khi dừng hẳn JVM cần một database bền vững qua tiến trình, chẳng hạn H2 file mode hoặc container database.

---

## 3. Các bảng metadata Spring Batch cần có

Spring Batch JDBC repository không tự suy ra hoặc tự tạo bảng metadata từ entity JPA. Nó dựa vào schema SQL của framework.

Những bảng chính trong Spring Batch 5.x bao gồm:

| Bảng | Lưu gì? | Phép kiểm tra thường gặp |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | Định danh logic của một job với identifying job parameters | Hai lần chạy lại có cùng `JobInstance` không? |
| `BATCH_JOB_EXECUTION` | Mỗi lần thực thi job, status, start/end time, version | Số lần chạy; trạng thái `FAILED`, `COMPLETED` |
| `BATCH_JOB_EXECUTION_PARAMS` | Các tham số của từng job execution | Tập tham số thực sự lưu có khớp khi restart không? |
| `BATCH_STEP_EXECUTION` | Mỗi lần chạy step; counts, status, version | Commit/read/write/rollback và số lần step chạy |
| `BATCH_JOB_EXECUTION_CONTEXT` | `ExecutionContext` ở cấp job | Giá trị cần truyền giữa các step |
| `BATCH_STEP_EXECUTION_CONTEXT` | `ExecutionContext` ở cấp step | Checkpoint reader/writer phục vụ restart |

Ngoài ra còn có các sequence hoặc cơ chế sinh ID tương ứng tùy database dialect, chẳng hạn `BATCH_JOB_SEQ`, `BATCH_JOB_EXECUTION_SEQ`, `BATCH_STEP_EXECUTION_SEQ`.

### 3.1. Mối quan hệ metadata

```text
BATCH_JOB_INSTANCE (1)
    |
    +---- (N) BATCH_JOB_EXECUTION
                 |
                 +---- (1) BATCH_JOB_EXECUTION_CONTEXT
                 |
                 +---- (N) BATCH_JOB_EXECUTION_PARAMS
                 |
                 +---- (N) BATCH_STEP_EXECUTION
                                  |
                                  +---- (1)
                                        BATCH_STEP_EXECUTION_CONTEXT
```

Một `JobInstance` được xác định bởi tên job và identifying parameters. Một instance có thể có nhiều `JobExecution`, ví dụ lần đầu `FAILED`, lần sau restart `COMPLETED`. Mỗi `JobExecution` có thể chứa nhiều `StepExecution`. Bảng context giữ trạng thái được lưu tại các ranh giới phù hợp với vòng đời của job và step.

**Đặc điểm phiên bản:** Spring Batch 5 đã thay đổi cấu trúc lưu job parameters so với các phiên bản 4.x. Vì vậy, không nên dùng schema SQL của Spring Batch 4 cho ứng dụng Spring Batch 5. Khi test bị lỗi cột không tồn tại hoặc insert thất bại, việc đầu tiên là đối chiếu **schema, thư viện runtime và migration** có cùng phiên bản hay không.

### 3.2. Schema cần được tạo trước khi job chạy

Lúc Spring Batch chuẩn bị tạo một `JobExecution`, `JobRepository` cần đọc/ghi metadata. Nếu bảng chưa tồn tại, test có thể thất bại ngay trước khi tasklet hoặc reader được gọi.

Lỗi thường thấy:

```text
org.h2.jdbc.JdbcSQLSyntaxErrorException:
Table "BATCH_JOB_INSTANCE" not found
```

Đây chủ yếu là lỗi **hạ tầng test**: H2 đã kết nối nhưng metadata schema chưa được khởi tạo, hoặc được khởi tạo trong một database khác với database mà `JobRepository` đang dùng.

---

## 4. Chọn H2, HSQLDB hay Derby cho metadata test

Các hệ quản trị SQL nhúng thường được dùng trong test Java:

| Engine | Dependency Gradle | Điểm nổi bật | Lưu ý |
| --- | --- | --- | --- |
| H2 | `com.h2database:h2` | Khởi động nhanh, URL in-memory dễ cấu hình, thông dụng với Spring Boot | SQL dialect, khóa và isolation có thể khác production |
| HSQLDB | `org.hsqldb:hsqldb` | Engine nhúng gọn, hỗ trợ in-memory | Dùng đúng schema script và driver phù hợp |
| Apache Derby | `org.apache.derby:derby` (có thể cần thêm `derbytools` tùy bản Java/Derby) | Database nhúng trong hệ sinh thái Java | Ma trận tương thích Java, driver và thư viện cần được kiểm tra |

Để học cơ chế metadata repository và triển khai các bài integration test chạy nhanh, ví dụ tiếp theo chọn **H2**. Khi ứng dụng production dùng PostgreSQL/Oracle/SQL Server và quan tâm đến locking, deadlock, timezone, kiểu dữ liệu, tính nhất quán giao dịch hay khác biệt SQL, nên bổ sung test chạy cùng hệ quản trị thực tế bằng Testcontainers hoặc môi trường tích hợp.

### Khi nào H2 là đủ?

H2 thường hữu ích cho:

- Test wiring giữa `JobLauncher`, `JobRepository`, `JobExplorer` và các step.
- Kiểm tra một `JobInstance` tạo ra `JobExecution`/`StepExecution` đúng kỳ vọng.
- Kiểm tra status và context được lưu rồi đọc lại.
- Kiểm tra restart qua nhiều `JobExecution` **trong cùng test process**.
- Chạy hàng loạt test độc lập trên CI mà không phải dựng database server.

H2 **chưa đủ để kết luận** thuật toán khóa, transaction isolation, vendor SQL và xử lý đồng thời sẽ tương đương production.

---

## 5. Cấu hình H2 embedded in-memory cho Spring Batch test

### 5.1. Dependency tối thiểu

Ví dụ Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.0'
    id 'io.spring.dependency-management' version '1.1.6'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'

    // Chỉ dùng H2 khi chạy test; production không phụ thuộc H2.
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong dự án Spring Boot thực tế, hãy dùng phiên bản plugin/BOM đã chuẩn hóa cho project thay vì sao chép nguyên số phiên bản ví dụ. Spring Boot dependency management sẽ căn chỉnh phiên bản Spring Batch, Spring JDBC và H2 phù hợp.

`spring-boot-starter-batch` cung cấp những thành phần nền tảng Spring Batch/JDBC; `spring-batch-test` cung cấp các test utility; H2 cung cấp JDBC driver và database engine chạy trong tiến trình test.

### 5.2. Cấu hình đơn giản nhất bằng Spring Boot

Tạo file `src/test/resources/application-batch-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  datasource:
    generate-unique-name: true
```

Sau đó kích hoạt profile `batch-test` bằng `@ActiveProfiles("batch-test")` trên integration test.

Ý nghĩa:

- `spring.batch.job.enabled=false`: tránh Spring Boot tự khởi chạy tất cả job khi application context vừa sẵn sàng; test sẽ gọi launcher một cách có chủ đích.
- `spring.batch.jdbc.initialize-schema=always`: yêu cầu Spring Boot chạy script tạo **metadata schema của Spring Batch** trên datasource được nhận diện để khởi tạo Batch JDBC.
- `spring.datasource.generate-unique-name=true`: khi Spring Boot tự tạo embedded datasource, tên database được sinh riêng cho mỗi application context, giảm nguy cơ hai test context dùng chung metadata ngoài ý muốn.
- Không đặt `spring.datasource.url`: nếu H2 có trên classpath và không có cấu hình datasource khác, Spring Boot có thể tự cung cấp embedded datasource. Đây là đường ngắn nhất cho test metadata riêng biệt.

Khi dùng cơ chế tự cấu hình tiêu chuẩn của Spring Boot, thường **không cần** viết `@EnableBatchProcessing`, `JobRepositoryFactoryBean` hoặc bean `DataSource` bằng tay. Những cấu hình hạ tầng tự khai báo có thể khiến Boot lùi bước khỏi một phần Batch auto-configuration; lúc đó việc init schema và wiring phải do project tự kiểm soát.

### 5.3. Cấu hình URL H2 rõ ràng khi cần chia sẻ database có chủ ý

Một test suite có thể muốn nhiều thành phần dùng cùng database in-memory được đặt tên:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_metadata_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
```

Ở đây:

- `jdbc:h2:mem:batch_metadata_test` tạo/đính kèm một database H2 in-memory **có tên** bên trong cùng JVM.
- Các connection cùng URL sẽ trỏ đến cùng database khi lifecycle cho phép.
- `DB_CLOSE_DELAY=-1` giữ database còn tồn tại sau khi connection cuối cùng đóng, cho tới khi JVM kết thúc hoặc database được đóng rõ ràng.
- `username=sa` và password rỗng chỉ phù hợp cho test H2 tại chỗ.

**Cẩn thận:** tên `batch_metadata_test` cố định kết hợp `DB_CLOSE_DELAY=-1` có thể khiến metadata tồn tại xuyên nhiều test context trong cùng JVM. Nếu Boot tiếp tục chạy script `CREATE TABLE` với `initialize-schema=always`, test sau có thể gặp lỗi “table already exists”. Khi cần test độc lập, ưu tiên database name duy nhất hoặc vòng đời context/database rõ ràng; khi cần cố ý tái sử dụng, khởi tạo schema đúng một lần.

Không dùng URL `jdbc:h2:mem:` *không tên* cho hạ tầng dùng connection pool rồi mặc định nhiều connection cùng nhìn thấy dữ liệu. Với H2, database in-memory không tên có phạm vi theo connection, dễ làm job tạo metadata trên một connection nhưng query trên connection khác không thấy.

### 5.4. Có nên đặt `DB_CLOSE_DELAY=-1` cho mọi test?

Không. Nếu chọn `generate-unique-name=true` và để Spring Boot quản lý H2 embedded datasource, có thể bắt đầu với mặc định để lifecycle gắn với application context. Chỉ thêm `DB_CLOSE_DELAY=-1` khi thực sự có lý do cần database tồn tại sau khi connection cuối cùng đóng. Đổi lại, phải xử lý tên database riêng biệt và cleanup để tránh test ảnh hưởng lẫn nhau.

---

## 6. Ai tạo schema metadata?

Có ba chiến lược phổ biến:

| Chiến lược | Khi phù hợp | Chủ thể tạo schema |
| --- | --- | --- |
| Spring Boot Batch JDBC auto-init | Test dùng embedded H2, schema đơn giản, muốn khởi tạo tự động | `spring.batch.jdbc.initialize-schema` |
| Chạy script Spring Batch có kiểm soát | Hạ tầng tùy biến, không dùng Boot Batch auto-config mặc định | `schema-h2.sql` tương ứng phiên bản Spring Batch |
| Flyway / Liquibase migration | Production quản lý schema qua migration; muốn test giống production | Migration versioned của ứng dụng |

### 6.1. Spring Boot auto-init

Với `initialize-schema: always`, Boot sẽ dùng script phù hợp database platform khi auto-configuration áp dụng. Ví dụ với H2, Spring Batch phân phối script `org/springframework/batch/core/schema-h2.sql` trong thư viện Spring Batch JDBC.

Đừng dùng đồng thời auto-init và một migration tạo chính những bảng `BATCH_*` trên cùng datasource mà không có chiến lược tránh trùng. Một trong hai cơ chế cần chịu trách nhiệm rõ ràng.

### 6.2. Nếu dùng Flyway hoặc Liquibase

Khi sản phẩm đã quản lý metadata schema bằng migration, test tích hợp có thể chạy cùng migrations để kiểm tra đường nâng cấp thực tế:

```yaml
spring:
  batch:
    jdbc:
      initialize-schema: never

  flyway:
    enabled: true
```

Đoạn trên chỉ mô tả **chọn Flyway làm chủ schema**. Để hoạt động, project còn phải có `flyway-core`, đúng JDBC driver và **migration tạo/cập nhật các bảng metadata của Spring Batch**. Bật Flyway mà không có migration tạo `BATCH_*` sẽ vẫn dẫn đến lỗi thiếu bảng.

Với H2, đôi khi migration production chứa cú pháp riêng cho PostgreSQL/Oracle nên không chạy được. Có thể dùng test migration phù hợp H2 để kiểm thử cơ chế Batch, nhưng cần thêm integration test trên database production để chứng minh migrations vận hành đúng ở môi trường thực.

### 6.3. Phân biệt ba cơ chế tạo schema

- `spring.batch.jdbc.initialize-schema`: dành cho **Spring Batch metadata**.
- `spring.sql.init.mode`: dành cho script SQL tổng quát của Spring Boot như `schema.sql` và `data.sql`.
- `spring.jpa.hibernate.ddl-auto`: dành cho entity JPA do Hibernate quản lý, **không thay thế** Spring Batch JDBC metadata DDL.

Đặt `spring.jpa.hibernate.ddl-auto=create` không phải cách sửa lỗi thiếu `BATCH_JOB_INSTANCE`.

### 6.4. Trường hợp có nhiều datasource

Ví dụ ứng dụng có:

- `businessDataSource` kết nối database hóa đơn.
- `batchMetadataDataSource` kết nối H2 test chỉ để lưu metadata.

Lúc này cần cấu hình rõ **datasource nào dành cho Batch**. Với các phiên bản Spring Boot phù hợp, có thể dùng `@BatchDataSource` trên bean datasource chuyên dụng và cấu hình `@Primary`/qualifier cho các hạ tầng còn lại. Nếu tự dùng `@EnableBatchProcessing` hoặc `DefaultBatchConfiguration`, phải theo cơ chế xác định datasource/transaction manager của phiên bản Spring Batch đang chạy.

Hai assertion nên có trong integration test nhiều datasource:

1. Job chạy và bảng `BATCH_*` xuất hiện tại **metadata datasource** mong đợi.
2. Database nghiệp vụ không bị tạo schema `BATCH_*` ngoài thiết kế.

Đừng suy ra rằng property `spring.datasource.url` luôn là nơi `JobRepository` ghi metadata khi ứng dụng có nhiều `DataSource` và bean cấu hình tùy biến.

---

## 7. Integration test hoàn chỉnh với H2 metadata

Ví dụ sau kiểm tra một job đơn giản tên `sampleImportJob`:

- Test khởi động Spring Boot và H2 embedded.
- Spring Batch tự khởi tạo JDBC repository và schema metadata.
- Một tasklet ghi `sample.processed=3` vào **step execution context**.
- Test gọi `JobLauncherTestUtils.launchJob(...)`.
- Test đọc lại metadata bằng `JobExplorer`, từ đó xác nhận dữ liệu được lưu và truy vấn qua repository.
- `JdbcTemplate` đọc số record ở bảng `BATCH_JOB_EXECUTION` như một kiểm tra hạ tầng bổ sung.

### 7.1. Mã Java

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = EmbeddedMetadataDatabaseTest.TestApplication.class
)
@ActiveProfiles("batch-test")
class EmbeddedMetadataDatabaseTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void savesJobAndStepMetadataInEmbeddedH2() throws Exception {
        Integer before = jdbcTemplate.queryForObject(
            "select count(*) from BATCH_JOB_EXECUTION",
            Integer.class
        );

        JobParameters parameters = new JobParametersBuilder()
            .addString("run.id", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution execution =
            jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertNotNull(execution.getId());
        assertNotNull(execution.getJobInstance().getId());

        StepExecution step = execution.getStepExecutions().stream()
            .filter(s -> s.getStepName().equals("sampleImportStep"))
            .findFirst()
            .orElseThrow();

        assertEquals(3,
            step.getExecutionContext().getInt("sample.processed"));

        // Đọc lại từ metadata repository, không chỉ nhìn object
        // do JobLauncher trả về.
        JobExecution restoredJob =
            jobExplorer.getJobExecution(execution.getId());

        assertNotNull(restoredJob);
        assertEquals(execution.getId(), restoredJob.getId());
        assertEquals(BatchStatus.COMPLETED, restoredJob.getStatus());

        StepExecution restoredStep = jobExplorer.getStepExecution(
            execution.getId(),
            step.getId()
        );

        assertNotNull(restoredStep);
        assertEquals(
            3,
            restoredStep.getExecutionContext().getInt("sample.processed")
        );

        Integer after = jdbcTemplate.queryForObject(
            "select count(*) from BATCH_JOB_EXECUTION",
            Integer.class
        );

        assertNotNull(before);
        assertNotNull(after);
        assertEquals(before + 1, after);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(BatchTestConfiguration.class)
    static class TestApplication {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BatchTestConfiguration {

        @Bean
        Step sampleImportStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager) {

            return new StepBuilder("sampleImportStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    contribution.getStepExecution()
                        .getExecutionContext()
                        .putInt("sample.processed", 3);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Job sampleImportJob(
                JobRepository jobRepository,
                Step sampleImportStep) {

            return new JobBuilder("sampleImportJob", jobRepository)
                .start(sampleImportStep)
                .build();
        }
    }
}
```

File test sử dụng cấu hình `application-batch-test.yml` ở mục 5.2. Test context chỉ có một bean `Job` nên `JobLauncherTestUtils` có thể xác định job cần chạy. Nếu project chứa nhiều `Job`, hãy gán rõ `jobLauncherTestUtils.setJob(jobUnderTest)` trước khi gọi `launchJob`.

### 7.2. Vì sao test có ý nghĩa?

**Kiểm tra repository có hoạt động.** `launchJob` sử dụng `JobLauncher` và `JobRepository` để tạo/cập nhật metadata. Job có `BatchStatus.COMPLETED` cho thấy flow đã đến trạng thái thành công.

**Kiểm tra dữ liệu trạng thái đã được lưu.** `jobExplorer.getStepExecution(jobExecutionId, stepExecutionId)` dùng API đọc metadata từ repository. Kiểm tra key `sample.processed` trên kết quả truy vấn có giá trị hơn việc chỉ đọc lại object `StepExecution` ban đầu.

**Kiểm tra schema đang được dùng.** `JdbcTemplate` có thể query được `BATCH_JOB_EXECUTION`, cho thấy datasource JDBC đã có bảng metadata. Phép so sánh trước/sau hữu ích hơn khẳng định số record bằng đúng 1 vì cùng test context có thể đã chạy job khác trước đó.

**Không kiểm tra quá phạm vi.** Test không chứng minh H2 và database production xử lý locking/serialization giống nhau. Nó xác nhận pipeline Spring Batch JDBC và các API metadata hoạt động trong cấu hình test đang chạy.

### 7.3. Vì sao không đặt `@Transactional` cho toàn bộ test?

Một số integration test nghiệp vụ thường đặt `@Transactional` để rollback dữ liệu sau test. Với Spring Batch, `JobLauncher` và `JobRepository` có transaction boundaries riêng; rollback transaction của test không nhất thiết xóa metadata như bạn nghĩ, thậm chí có thể gây tương tác khó hiểu khi cùng datasource.

Nếu cần isolation, ưu tiên **database riêng cho test context**, dọn dữ liệu rõ ràng hoặc tạo test instance mới, thay vì mặc định dựa vào `@Transactional` trên test method để hoàn nguyên toàn bộ metadata.

---

## 8. Cách kiểm tra metadata bằng API và SQL

### 8.1. Ưu tiên `JobExplorer` cho hành vi Spring Batch

`JobExplorer` phù hợp khi muốn kiểm tra mô hình nghiệp vụ của framework:

```java
JobExecution saved = jobExplorer.getJobExecution(executionId);

assertNotNull(saved);
assertEquals(BatchStatus.COMPLETED, saved.getStatus());

StepExecution savedStep =
    jobExplorer.getStepExecution(executionId, stepExecutionId);

assertNotNull(savedStep);
assertEquals(
    3,
    savedStep.getExecutionContext().getInt("sample.processed")
);
```

Không cần biết metadata được lưu thành cột SQL nào, context serialization ra sao hoặc tên sequence thay đổi thế nào khi nâng cấp.

### 8.2. Dùng `JdbcTemplate` khi muốn xác nhận cấu trúc database test

`JdbcTemplate` thích hợp cho kiểm tra hạ tầng, đếm record hoặc chẩn đoán:

```java
int instances = jdbcTemplate.queryForObject(
    "select count(*) from BATCH_JOB_INSTANCE",
    Integer.class
);

int executions = jdbcTemplate.queryForObject(
    "select count(*) from BATCH_JOB_EXECUTION",
    Integer.class
);

int stepExecutions = jdbcTemplate.queryForObject(
    "select count(*) from BATCH_STEP_EXECUTION",
    Integer.class
);

assertTrue(instances >= 1);
assertTrue(executions >= 1);
assertTrue(stepExecutions >= 1);
```

Với test kiểm tra một job cụ thể, nên lọc bằng ID hoặc so sánh thay đổi trước/sau để tránh phụ thuộc vào record không liên quan. Khi schema có table prefix tùy chỉnh, tên `BATCH_*` phải đổi tương ứng.

Không nên assert trực tiếp raw JSON, Base64 hay serialized blob trong cột context để kết luận business logic đúng. Cách Spring Batch serialize `ExecutionContext` có thể khác giữa phiên bản hoặc theo `ExecutionContextSerializer` được cấu hình.

### 8.3. Kiểm tra quan hệ JobInstance – JobExecution

Sau khi job thất bại và được restart thành công, điều cần khẳng định thường là:

- Cả hai execution thuộc **cùng `JobInstance`**.
- Có hai `JobExecution` cho một instance.
- Các step đã hoàn thành có thể được bỏ qua trong lần restart tùy chính sách step.
- Step bị lỗi được chạy lại theo trạng thái đã lưu.

Ví dụ dạng assertion, với hai kết quả do một fixture restart thực sự tạo ra:

```java
assertEquals(
    first.getJobInstance().getId(),
    restarted.getJobInstance().getId()
);

assertNotEquals(first.getId(), restarted.getId());
assertEquals(BatchStatus.FAILED, first.getStatus());
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
```

Một embedded database có lưu được metadata giữa hai lần `launchJob` trong cùng JVM mới cho phép kiểm tra mối quan hệ này.

---

## 9. Kiểm thử restart với embedded metadata database

Điểm mạnh của embedded JDBC metadata so với một mock `JobRepository` đơn giản là test có thể kiểm tra vòng đời **các execution được persist**.

### 9.1. Kịch bản hai step

Giả sử job có:

```text
reportJob
   |
   v
prepareStep   -- thành công, ghi metadata COMPLETED
   |
   v
publishStep   -- lần đầu FAIL
   |
   x  JobExecution #1: FAILED

Restart cùng JobInstance
   |
   v
prepareStep   -- thường được bỏ qua vì đã COMPLETED
   |
   v
publishStep   -- lần hai thành công
   |
   v
JobExecution #2: COMPLETED
```

Fixture có thể dùng một `AtomicBoolean` trong test để khiến `publishStep` thất bại đúng một lần. Sau đó dùng **cùng identifying `JobParameters`** để chạy lại qua `JobLauncherTestUtils`.

Khung assertion:

```java
// reportJob: prepareStep chạy thành công;
// publishStep được test fixture cấu hình fail lần đầu.
JobParameters sameParameters = new JobParametersBuilder()
    .addString("business.date", "2026-11-16")
    .toJobParameters();

failureSwitch.failNextPublish();

JobExecution first = jobLauncherTestUtils.launchJob(sameParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

failureSwitch.allowPublish();

JobExecution second = jobLauncherTestUtils.launchJob(sameParameters);
assertEquals(BatchStatus.COMPLETED, second.getStatus());

assertEquals(
    first.getJobInstance().getId(),
    second.getJobInstance().getId()
);

assertNotEquals(first.getId(), second.getId());
assertEquals(1, prepareStepCounter.get());
assertEquals(2, publishStepCounter.get());
```

Ở đây, `failureSwitch` và hai counter là fixture mà người viết test phải triển khai vào các tasklet. Mẫu trên không phải class độc lập có thể chạy ngay khi chưa có định nghĩa fixture, mà minh họa rõ **điều kiện cần quan sát**.

Trong một test suite tái sử dụng context, nên dùng bộ identifying parameters duy nhất cho từng kịch bản. Khi restart, dùng lại **chính bộ parameters đó**. Nếu thay `business.date` thành giá trị khác, bạn sẽ có `JobInstance` mới và kết luận về restart có thể sai.

### 9.2. Checkpoint của reader/writer

Nếu step xử lý theo chunk và có `ItemStream`:

```text
Execution #1:
  chunk 1 -> COMMIT -> checkpoint = 20
  chunk 2 -> COMMIT -> checkpoint = 40
  chunk 3 -> FAIL   -> không commit

Metadata H2: checkpoint cuối cùng được lưu = 40

Execution #2 (restart cùng instance):
  ItemStream.open(context) nhận checkpoint = 40
  xử lý tiếp từ vị trí tiếp theo
```

Có ba tầng cần assert:

1. Sau execution thất bại, dùng `JobExplorer` đọc lại `StepExecution` và `ExecutionContext` để lấy checkpoint đã lưu.
2. Khi restart, ghi nhận checkpoint thực tế mà `ItemStream.open` nhận; khẳng định nó bằng checkpoint đã lưu.
3. Sau khi hoàn tất, kiểm tra dữ liệu nghiệp vụ không thiếu/không nhân đôi và status metadata `COMPLETED`.

Một test chỉ assert biến offset trên object reader trong bộ nhớ **không chứng minh** dữ liệu đó đã được commit xuống metadata DB.

### 9.3. Restart giữa hai lần tạo Spring context

Nếu cả hai execution dùng chung H2 **in-memory có tên**, việc tạo context khác chỉ giữ được metadata khi database instance thực sự còn sống và lifecycle đã được chủ động quản lý. Mặc định, database embedded thường gắn với vòng đời ứng dụng/test, nên đừng mong restart test sang **JVM khác** vẫn thấy metadata cũ.

Nếu yêu cầu là kiểm tra restart qua quá trình application shutdown/startup:

- Dùng H2 **file mode** ở thư mục test tạm có lifecycle rõ ràng; hoặc
- Dùng Testcontainers với database production, volume/đời sống container phù hợp; hoặc
- Dùng một database tích hợp độc lập có khả năng giữ dữ liệu qua process.

Chỉ dùng `DB_CLOSE_DELAY=-1` không làm H2 in-memory tồn tại qua một JVM mới.

---

## 10. Test isolation: tránh metadata của bài này ảnh hưởng bài khác

### 10.1. Vì sao H2 dùng chung gây test flaky?

Metadata có ràng buộc uniqueness và quan hệ chặt giữa job name, parameters, instance và execution. Nếu hai test vô tình dùng chung H2, hoặc một test chạy lại cùng parameters của job đã `COMPLETED`, có thể phát sinh lỗi như:

```text
JobInstanceAlreadyCompleteException:
A job instance already exists and is complete
```

Hoặc hai context cùng khởi tạo schema trên database chung:

```text
JdbcSQLSyntaxErrorException:
Table "BATCH_JOB_INSTANCE" already exists
```

Hoặc một test đọc `BATCH_JOB_EXECUTION` và thấy số record lớn hơn kỳ vọng vì test khác đã tạo metadata.

### 10.2. Ba mức isolation

| Mức | Cách làm | Phù hợp với |
| --- | --- | --- |
| Mỗi lần chạy job | Tạo identifying `JobParameters` duy nhất | Nhiều test method dùng chung Spring context và H2 |
| Mỗi Spring test context | Dùng embedded database với tên duy nhất, chẳng hạn `generate-unique-name=true` | Các test class có cấu hình khác nhau |
| Mỗi test/process | Database instance riêng hoặc test resource riêng, dọn dẹp khi xong | Suite chạy song song, test restart phức tạp |

Một cách sinh tham số duy nhất:

```java
JobParameters unique = new JobParametersBuilder()
    .addString("test.run.id", UUID.randomUUID().toString())
    .toJobParameters();
```

Nhưng **không thay parameters giữa lần chạy thất bại và lần restart** trong cùng test.

### 10.3. Không dọn metadata bằng cách xóa vài bảng tùy tiện

Xóa `BATCH_JOB_INSTANCE` mà chưa xử lý các execution và context liên quan có thể vi phạm foreign key. Xóa bảng metadata bằng SQL giữa lúc job còn chạy có thể phá vỡ trạng thái và làm lỗi ngẫu nhiên.

Nếu muốn test độc lập, lựa chọn đơn giản thường là một H2 database mới. Khi thật sự cần reset, nên thực hiện qua teardown SQL có thứ tự, không còn job đang chạy, và kiểm soát sequence/identity cùng transaction; nếu không, chỉ thay đổi database name/test context sẽ ít rủi ro hơn.

### 10.4. Đừng lạm dụng `@DirtiesContext`

`@DirtiesContext` buộc Spring Test tạo context mới sau/before test theo cấu hình. Nó có thể giải quyết trạng thái bean bị chia sẻ, nhưng làm suite chậm và **không tự bảo đảm** H2 cũ đã biến mất nếu URL cố định cùng `DB_CLOSE_DELAY=-1`.

Ưu tiên thiết kế test rõ ràng: input parameters duy nhất, fixture reset có chủ ý, database name riêng. Chỉ dùng `@DirtiesContext` khi có lý do thật sự liên quan đến lifecycle của bean/context.

### 10.5. Test chạy song song

Các test chạy parallel không nên chia sẻ cùng:

- job name và identifying parameters khi chúng vô tình nhắm đến một `JobInstance`;
- cờ `AtomicBoolean` hoặc counter fixture toàn cục không được reset;
- H2 database cố định nếu mỗi test đều cố chạy init schema;
- transaction manager hoặc connection pool bị dừng trong khi test khác còn dùng.

Nếu cần kiểm tra **chủ động chạy đồng thời vào cùng `JobInstance`**, hãy thiết kế một concurrency test riêng, không cố coi lỗi cạnh tranh đó là đặc tính ngẫu nhiên của các test độc lập.

---

## 11. Những lỗi cấu hình thường gặp và cách chẩn đoán

### 11.1. `Table "BATCH_JOB_INSTANCE" not found`

Khả năng chính:

- Spring Batch schema chưa được initialize.
- `spring.batch.jdbc.initialize-schema` vẫn là `never` hoặc auto-init không được kích hoạt trong cấu hình hiện tại.
- Có nhiều datasource và schema được tạo trên datasource khác.
- Script của schema chưa chạy hoặc bị lỗi ngay lúc application context bắt đầu.
- H2 dùng database không tên, khiến connection ghi/read thuộc các database khác nhau.

Hướng xử lý:

1. Kiểm tra H2 driver trên test runtime classpath và URL datasource thực tế.
2. Xác định `JobRepository` đang dùng datasource nào.
3. Kiểm tra log khởi tạo schema và cấu hình Boot Batch JDBC initializer.
4. Query metadata table bằng `JdbcTemplate` trên **cùng datasource**.
5. Nếu hạ tầng tự khai báo, dùng migration/script phù hợp với Spring Batch thay vì trông chờ Boot initializer mặc định.

### 11.2. `Table already exists`

Nguyên nhân thường là **schema bị tạo lại trên H2 chưa dọn** hoặc cả Boot Batch auto-init và migration đều tạo cùng bảng. Xem lại `DB_CLOSE_DELAY=-1`, tên H2 cố định, context caching và cơ chế init trùng.

Đừng chữa bằng cách bắt mọi exception rồi bỏ qua; test có thể âm thầm dùng dữ liệu cũ và đưa ra kết quả không đáng tin.

### 11.3. `JobInstanceAlreadyCompleteException`

Test chạy job đã `COMPLETED` với cùng job name và identifying parameters. Hãy sinh parameters mới cho test độc lập. Chỉ giữ nguyên parameters khi **cố tình restart một JobInstance đã thất bại hoặc bị dừng và được phép restart**.

### 11.4. `BadSqlGrammarException` / lỗi cột trong bảng parameters

Nếu xảy ra ở `BATCH_JOB_EXECUTION_PARAMS`, kiểm tra script của Spring Batch 4.x có đang được dùng với runtime Spring Batch 5.x hay không. Ngoài ra, xem lại cấu hình custom table prefix, platform và migration version.

### 11.5. `Cannot determine embedded database driver class`

Lỗi xảy ra khi Spring Boot không có JDBC URL/driver được cấu hình và không tìm thấy embedded driver trên test classpath. Kiểm tra `testRuntimeOnly 'com.h2database:h2'` và quá trình chạy test có thực sự sử dụng Gradle test runtime classpath không.

### 11.6. Metadata đột nhiên biến mất giữa hai bước

Các trường hợp cần chú ý:

- Test tạo datasource mới trỏ đến một H2 database khác.
- H2 không tên được mở trên connection khác.
- Connection cuối cùng đã đóng và database bị hủy do lifecycle mặc định.
- Test chạy restart qua JVM khác nhưng vẫn dùng H2 in-memory.
- Test trước hoặc teardown đã dọn schema.

Nếu cần giữ metadata trong cùng JVM giữa các connection, dùng H2 có tên và kiểm soát connection/lifecycle. Nếu cần giữ metadata qua JVM, chọn database có persistence.

### 11.7. `JobLauncherTestUtils` không biết chạy job nào

Nếu có nhiều bean `Job`, `@SpringBatchTest` không thể tự xác định duy nhất job. Trong test, inject đúng `Job` bằng qualifier rồi gọi:

```java
jobLauncherTestUtils.setJob(jobUnderTest);

JobExecution execution =
    jobLauncherTestUtils.launchJob(uniqueParameters);
```

Điều này là vấn đề **lựa chọn job test**, không phải lỗi của H2.

### 11.8. Test pass trên H2 nhưng fail trên PostgreSQL/Oracle

Có thể do:

- Khác mức isolation khi tạo `JobExecution` đồng thời.
- SQL lock hoặc sequence sinh ID khác nhau.
- SQL dialect hoặc kiểu dữ liệu khác.
- Sai số thời gian, timezone hoặc precision của timestamp.
- Migration production chưa tương thích.
- Giới hạn connection pool, deadlock và transaction timeout khác.

H2 giúp test logic Batch nhanh, nhưng không thay thế các test tích hợp trên database mục tiêu.

---

## 12. Embedded metadata database và các kiểu test khác

Không phải mọi bài test Spring Batch đều cần một H2.

| Mục đích test | Có cần embedded metadata DB? | Công cụ phù hợp |
| --- | --- | --- |
| Test hàm xử lý dữ liệu thuần Java | Không | JUnit với object đầu vào/đầu ra |
| Test processor độc lập | Không | Unit test `ItemProcessor` |
| Test cách reader lưu offset trong `ExecutionContext` in-memory | Không nhất thiết | `ItemStream.open/update` với `ExecutionContext` giả lập |
| Test một tasklet ghi key vào `StepExecution` | Không nhất thiết | `MetaDataInstanceFactory` trong `spring-batch-test` |
| Test wiring Job/Step, repository, status sau launch | Có, nếu dùng JDBC repository | Embedded H2 + `@SpringBatchTest` |
| Test repository persisted metadata, restart trong JVM | Có | H2/HSQLDB với schema đúng phiên bản |
| Test transaction và locking giống production | H2 thường chưa đủ | Testcontainers với production DB |
| Test restart qua JVM/process | In-memory DB không đủ | File-backed DB hoặc database service |

Spring Batch mới hơn có thêm những lựa chọn repository nhẹ phục vụ use case không cần persistent restart, ví dụ `ResourcelessJobRepository` ở Spring Batch 5.2+. Tuy nhiên, nếu mục tiêu của bài test là **kiểm tra metadata JDBC, lịch sử execution hoặc restart**, hãy dùng JDBC repository với database thật, dù database đó được nhúng trong test.

### 12.1. Lựa chọn `@SpringBatchTest`, `@SpringBootTest` và test slice

- `@SpringBatchTest` đăng ký những tiện ích cho batch test, như `JobLauncherTestUtils` và các test execution listener phù hợp.
- `@SpringBootTest` nạp Spring Boot application context, cho phép test với datasource, auto-config và bean `Job`/`Step` thực.
- Các annotation test slice như `@JdbcTest` hoặc `@DataJpaTest` giới hạn phạm vi Spring context. Chúng hữu ích khi test riêng JDBC/JPA, nhưng **không mặc định nạp đầy đủ Batch infrastructure** để gọi `launchJob`.

Có thể kết hợp `@SpringBatchTest` với `@SpringBootTest` để viết integration test toàn job như ở mục 7.

### 12.2. Metadata test nên quan sát cả trạng thái và dữ liệu nghiệp vụ

Một job có thể ghi metadata `COMPLETED` nhưng kết quả nghiệp vụ vẫn không đúng nếu step xử lý sai. Ngược lại, writer có thể ghi dữ liệu xong nhưng metadata chưa commit trong cùng transaction hay bị lỗi ngoài ý muốn.

Vì vậy, thiết kế integration test tốt thường có hai nhóm assertion:

- **Batch metadata:** status, counts, execution context, số lần chạy, quan hệ instance/execution.
- **Business outcome:** số bản ghi, tập ID, checksum, file output hoặc sự kiện đã phát, tùy job.

Hai nhóm này trả lời những câu hỏi khác nhau và bổ sung cho nhau.

---

## 13. Một quy trình áp dụng trong project

Khi tạo module test cho một job Spring Batch mới, có thể thực hiện theo thứ tự sau:

### Bước 1 — Xác định trách nhiệm metadata

Xác định project dùng:

- một `DataSource` chung cho metadata và business; hay
- hai `DataSource` riêng biệt.

Quyết định test cần dùng H2 cho metadata nào, có cần test SQL nghiệp vụ hay không.

### Bước 2 — Chọn lifecycle database

Với test độc lập chạy nhanh:

```text
H2 in-memory
  -> database riêng theo Spring test context
  -> initialize schema một lần
  -> mỗi test dùng identifying parameters riêng
  -> job chạy, metadata được assert
  -> context/database được đóng khi test xong
```

Với test restart trong cùng JVM: dùng một database instance liên tục sống trong cả lần chạy thất bại và lần chạy tiếp theo.

### Bước 3 — Chọn đúng một chủ thể quản lý metadata schema

Chọn một trong:

- Spring Boot `spring.batch.jdbc.initialize-schema=always` cho môi trường test đơn giản.
- SQL initialization chủ động cho cấu hình Batch tùy biến.
- Migration versioned nếu schema được quản lý bằng Flyway/Liquibase.

### Bước 4 — Tạo integration test nền

Dùng `@SpringBatchTest` + `@SpringBootTest` để kiểm tra:

1. Job khởi chạy bằng unique identifying parameters.
2. Có `JobExecution` và `StepExecution` được tạo.
3. Status và execution context được ghi đúng.
4. `JobExplorer` đọc lại được metadata.
5. SQL metadata tables sẵn sàng khi cần kiểm tra hạ tầng.

### Bước 5 — Thêm tình huống lỗi và restart

Cho step thất bại ở thời điểm kiểm soát được; giữ nguyên identifying job parameters; assert số lần chạy, checkpoint đã persisted, khả năng tiếp tục và dữ liệu đầu ra.

### Bước 6 — Bổ sung test trên database production khi cần

Nếu job cần yêu cầu về transaction, locking, vendor SQL hoặc schema migration, chạy thêm integration test trong Testcontainers hoặc môi trường dùng database tương đương production.

---

## 14. Bài thực hành

### Bài 1 — Tạo H2 metadata và quan sát bảng

Tạo Spring Boot test với dependency `spring-batch-test` và H2. Tắt auto-run job, bật Batch JDBC schema initialization và cấu hình database name duy nhất. Tạo job một step hoàn tất, chạy qua `JobLauncherTestUtils`.

Yêu cầu: assert `COMPLETED`, số `BATCH_JOB_EXECUTION` tăng 1, `JobExplorer` đọc lại được `JobExecution` có ID và status chính xác.

### Bài 2 — Kiểm tra `ExecutionContext` được persisted

Trong tasklet, ghi hai key `sample.total=15` và `sample.stage="IMPORTED"` vào step context. Sau khi step kết thúc, đọc lại `StepExecution` bằng `JobExplorer` và assert hai key có đúng giá trị/kiểu.

Mở rộng: cấu hình `ExecutionContextPromotionListener` để chuyển riêng `sample.total` sang job context; kiểm tra key còn lại không bị chuyển.

### Bài 3 — Phát hiện xung đột test data

Chạy cùng job hai lần với cùng identifying parameters sau khi lần thứ nhất đã `COMPLETED`. Quan sát cơ chế `JobInstanceAlreadyCompleteException`. Sau đó thay parameters thành giá trị duy nhất và xác nhận tạo được `JobInstance` khác.

Giải thích: vì sao việc đổi parameters này phù hợp cho **hai test độc lập** nhưng không phù hợp để kiểm tra **restart**?

### Bài 4 — Kiểm thử restart

Tạo job hai step: `prepareStep` thành công và `publishStep` thất bại ở lần đầu. Chạy lại với cùng identifying parameters sau khi bỏ lỗi. Assert:

- Lần đầu `FAILED`, lần hai `COMPLETED`.
- Hai `JobExecution` có cùng `JobInstance`.
- `prepareStep` không xử lý lại trong cấu hình mặc định cho step đã hoàn tất.
- Metadata được đọc từ `JobExplorer` khớp với những trạng thái trên.

### Bài 5 — Tách business và metadata datasource

Cấu hình một datasource H2 cho Batch metadata, một datasource khác cho dữ liệu nghiệp vụ. Chứng minh `BATCH_*` nằm ở metadata datasource, dữ liệu nghiệp vụ nằm ở nơi được chỉ định và các test có thể khởi chạy độc lập.

---

## 15. Checklist trước khi đưa bài test vào CI

- **Đúng phiên bản:** runtime Spring Batch và metadata DDL/migration cùng thế hệ.
- **Đúng datasource:** `JobRepository` trỏ vào H2 test được mong đợi.
- **Một cơ chế init:** auto-init Batch hoặc migration được chọn rõ ràng.
- **Isolation:** test độc lập không vô tình tái sử dụng DB name/JobInstance.
- **Restart:** khi muốn test restart, hai lần chạy dùng cùng identifying parameters và repository còn metadata.
- **Assert có ý nghĩa:** đọc lại metadata bằng `JobExplorer` thay vì chỉ assert object trong bộ nhớ.
- **Bổ sung coverage phù hợp:** với SQL, concurrency và transaction phức tạp, có test trên database production hoặc tương đương.

Embedded database là công cụ tăng tốc phản hồi của integration test. Giá trị lớn nhất của nó nằm ở việc giữ **`JobRepository` và metadata lifecycle thực** hoạt động trong test: ta có thể quan sát việc Spring Batch tạo instance, ghi execution, lưu context và quyết định restart bằng các API framework, đồng thời kiểm soát được độ cô lập và vòng đời dữ liệu.

## 16. Tài liệu đọc thêm

- Spring Batch Reference: *Job Repository*, *Job Metadata*, *Unit Testing*, *Configuring and Running a Job*, *ExecutionContext*, *Batch Metadata Schema*.
- Spring Batch Javadoc: `JobRepository`, `JobExplorer`, `JobLauncherTestUtils`, `ExecutionContext`, `MetaDataInstanceFactory`.
- Spring Boot Reference: *Batch Applications* và *Database Initialization*.
- H2 Database Documentation: *In-Memory Databases* và các tham số JDBC URL như `DB_CLOSE_DELAY`.
- Testcontainers Documentation: tích hợp relational database container với Spring Boot tests.
