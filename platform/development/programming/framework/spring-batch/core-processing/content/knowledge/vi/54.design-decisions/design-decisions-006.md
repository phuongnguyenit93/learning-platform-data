# Chọn metadata database hay cơ chế khác trong Spring Batch

Khi xây dựng một batch job, đội phát triển thường tập trung vào `ItemReader`, `ItemProcessor` và `ItemWriter`, còn nơi lưu **metadata thực thi** chỉ được xem là chi tiết cấu hình. Nhưng lựa chọn metadata là một **quyết định thiết kế có tác động trực tiếp đến restart, chạy đồng thời, vận hành nhiều node, khả năng điều tra lỗi và chi phí hạ tầng**.

Ví dụ: một job xử lý 2 triệu giao dịch thất bại sau khi đã commit 1,5 triệu giao dịch. Nếu có `JobRepository` bền vững cùng checkpoint đúng, nó có thể tiếp tục phần còn lại. Nếu chỉ dùng trạng thái tạm trong bộ nhớ và process đã chết, thông tin cần restart có thể không còn. Khi ấy hệ thống phải chạy lại từ đầu và trông cậy vào idempotency, hoặc dùng một cơ chế checkpoint khác do ứng dụng tự xây dựng.

Trong chủ đề **Quyết định thiết kế** của **Spring Batch Core Processing**, ta sẽ trả lời câu hỏi: **khi nào nên dùng database quan hệ lưu metadata Spring Batch, khi nào một repository tạm/không lưu state là đủ, và những cơ chế ngoài Spring Batch có thể thay thế phần nào — nhưng không thể thay thế phần nào — của `JobRepository`?**

## 1. Metadata trong Spring Batch là gì?

**Metadata batch** là dữ liệu mô tả quá trình thực thi: công việc nào đã chạy, với tham số nào, trạng thái ra sao, bước nào đã hoàn thành, bước nào thất bại và ngữ cảnh nào phải được khôi phục khi chạy lại.

```text
Job definition: importOrdersJob
           |
           v
JobInstance (job name + identifying JobParameters)
           |
           +-- JobExecution #101, FAILED
           |       |
           |       +-- StepExecution #501
           |               status=FAILED
           |               readCount=1500000
           |               context={reader position, ...}
           |
           +-- JobExecution #102, COMPLETED (restart)
                   |
                   +-- StepExecution #502
                           status=COMPLETED
```

Những thành phần cốt lõi:

| Thành phần | Lưu thông tin gì? | Vai trò khi khôi phục |
| --- | --- | --- |
| `JobInstance` | Danh tính công việc logic, xác định bởi tên job và identifying `JobParameters` | Nhóm các execution thuộc cùng lần xử lý logic |
| `JobExecution` | Một lần thực thi, thời gian, trạng thái, exit status, lỗi | Cho biết có thể khởi chạy lại hay không và lần nào đã thất bại |
| `StepExecution` | Trạng thái từng step, read/write/filter/skip/commit/rollback counters | Xác định step nào cần chạy tiếp, step nào đã hoàn tất |
| `ExecutionContext` | Key/value trạng thái của job hoặc step được persist | Khôi phục vị trí reader/writer, token, checkpoint và trạng thái khác |
| `JobParameters` | Tham số kỳ dữ liệu, input, tenant, version, các giá trị identifying | Xác định restart cùng instance hay khởi chạy một instance mới |

`JobRepository` là giao diện trung tâm Spring Batch dùng để quản lý metadata. `JobExplorer` thường được dùng để **đọc và tra cứu** metadata, còn `JobLauncher` hoặc `JobOperator` dùng để khởi động/vận hành job tùy phiên bản và cách cấu hình.

Điều quan trọng: metadata **không phải dữ liệu nghiệp vụ đã xử lý**. `BATCH_STEP_EXECUTION.WRITE_COUNT=1000` không có nghĩa chắc chắn có 1.000 bản ghi nghiệp vụ duy nhất ở hệ thống đích. Metadata giúp framework thực thi và restart; kiểm chứng dữ liệu đầu ra vẫn cần unique key, transaction, manifest và đối soát nghiệp vụ.

## 2. Các phương án lưu metadata cần phân biệt

Không phải tất cả lựa chọn đều là những implementation tương đương có thể hoán đổi trong production. Có phương án giữ đầy đủ hợp đồng `JobRepository`, có phương án chỉ phù hợp với **job không cần restart**, và có phương án là **bổ sung** cho repository chứ không thay thế nó.

| Phương án | Bản chất | Trạng thái qua process restart | Phù hợp nhất |
| --- | --- | --- | --- |
| **JDBC `JobRepository` trên RDBMS bền vững** | Implementation repository dùng các bảng `BATCH_*` trong PostgreSQL, MySQL, Oracle, SQL Server, v.v. | Có, nếu DB và metadata được duy trì | Batch production cần restart, truy vết, nhiều execution hoặc nhiều node |
| **JDBC `JobRepository` trên database nhúng in-memory** | Vẫn là JDBC repository, nhưng DB nằm trong RAM của process/test | Thường mất khi DB/process bị hủy | Unit/integration test, demo, job ngắn không cần giữ lịch sử sau process |
| **JDBC trên database nhúng dạng file** | DB nhúng có lưu file trên đĩa | Có thể tồn tại qua restart process nếu file còn, nhưng có hạn chế vận hành | Demo/lab hoặc bài toán rất nhỏ với chính sách sao lưu rõ ràng |
| **Resourceless repository** | Repository nhẹ không dựa trên metadata DB bền vững, hiện diện ở các phiên bản Spring Batch mới | Không có cơ sở bền vững để restart sau khi process chết | Tác vụ đơn giản, độc lập, không cần job history/restart; kiểm tra đúng version |
| **Custom `JobRepository`** | Tự triển khai hợp đồng lưu metadata | Tùy implementation | Tình huống đặc thù có nguồn lực thiết kế, kiểm thử và bảo trì lớn |
| **Scheduler/orchestrator, audit store, log** | Công cụ điều phối và ghi nhận bên ngoài | Có thể có lịch sử riêng | **Bổ sung**, không mặc nhiên thay thế metadata/checkpoint Spring Batch |

Một điểm dễ nhầm: **H2 in-memory không giống resourceless repository**. H2 in-memory vẫn dùng schema và transaction JDBC của `JobRepository`; dữ liệu chỉ không còn khi vòng đời H2 kết thúc. Ngược lại, resourceless repository được thiết kế theo hướng không cần persistence metadata JDBC, nên các tính năng dựa vào dữ liệu bền vững và restart phải được xem xét giới hạn riêng.

### Phụ thuộc phiên bản

Ví dụ trong bài dùng **Spring Boot 3.x và Spring Batch 5.x** cho cấu hình JDBC. Các phiên bản 5.x và 6.x có thay đổi về API, package, hỗ trợ repository nhẹ và cách cấu hình. Đặc biệt, không lấy ví dụ `MapJobRepositoryFactoryBean` từ tài liệu Spring Batch đời cũ rồi coi đó là lựa chọn mặc định trong Spring Batch 5/6. Khi cân nhắc resourceless/custom repository, hãy kiểm tra **phiên bản chính xác** mà ứng dụng đang dùng và giới hạn tính năng của implementation tương ứng.

## 3. Vì sao JDBC metadata database thường là lựa chọn mặc định cho production?

Một relational database dùng làm `JobRepository` cho phép Spring Batch ghi metadata với các đặc tính transaction, khóa và lưu trữ mà batch production thường cần.

```text
          Spring Batch Job
          /             \
         v               v
  Dữ liệu nghiệp vụ     JobRepository JDBC
  (orders/report)       (BATCH_* metadata)
         |               |
         +-------+-------+
                 |
          Database bền vững
          / backup / HA / audit
```

Với một RDBMS được vận hành phù hợp, ta có những lợi ích:

1. **Trạng thái còn sau khi JVM/Pod chết:** metadata execution và context đã commit không phụ thuộc bộ nhớ process.
2. **Restart có cơ sở:** step có thể khôi phục từ context do `ItemStream` cập nhật tại các điểm checkpoint.
3. **Theo dõi job history:** `JobExplorer`, dashboard vận hành và truy vấn read-only có thể xem các execution đã tồn tại.
4. **Kiểm soát một phần cạnh tranh:** repository dùng danh tính `JobInstance` và metadata cập nhật có version để giảm các trường hợp cùng instance được thực thi trái phép.
5. **Hỗ trợ nhiều node:** những process có cùng cấu hình repository bền vững có thể nhìn thấy cùng metadata; orchestration và locking bổ sung vẫn cần cho nhiều tình huống.
6. **Quản trị có thể kiểm soát:** database có chính sách backup, monitoring, phân quyền, retention, schema migration và disaster recovery.

**JDBC repository không tự bảo đảm exactly-once end-to-end.** Nếu writer gọi API bên ngoài hoặc ghi object storage nằm ngoài transaction DB, việc metadata đã commit không có nghĩa side effect ngoài đã được ghi/công nhận cùng thời điểm. Cần idempotency, outbox, manifest hoặc reconciliation theo nghiệp vụ.

## 4. Các bảng `BATCH_*` lưu những gì?

Với Spring Batch dùng JDBC schema thông dụng, các bảng chính gồm:

| Bảng | Nội dung điển hình | Câu hỏi trả lời |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | ID instance, tên job và key định danh | Kỳ dữ liệu này thuộc job instance nào? |
| `BATCH_JOB_EXECUTION` | ID execution, thời điểm, status, exit code/message | Lần chạy nào thất bại/hoàn tất? |
| `BATCH_JOB_EXECUTION_PARAMS` | Tham số, kiểu, identifying flag | Job chạy với input/kỳ/phiên bản nào? |
| `BATCH_STEP_EXECUTION` | Tên step, status, read/write/skip/commit/rollback counters | Step nào đã xử lý bao nhiêu item? |
| `BATCH_JOB_EXECUTION_CONTEXT` | Snapshot context ở phạm vi job | State nào phải khôi phục cho job? |
| `BATCH_STEP_EXECUTION_CONTEXT` | Snapshot context ở phạm vi step | Reader/writer có checkpoint gì? |

Một số schema còn sử dụng sequence/table sinh ID phục vụ metadata; tên và chi tiết phụ thuộc database và phiên bản Spring Batch. **Dùng DDL đi kèm đúng phiên bản dependency**, không tự sao chép schema giữa các major version mà không kiểm tra migration.

### Truy vấn đọc lịch sử thực thi

Ví dụ read-only SQL tổng hợp theo execution và step:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.START_TIME,
    je.END_TIME,
    je.STATUS AS JOB_STATUS,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Vì một `JobExecution` có thể có nhiều `StepExecution`, kết quả `JOIN` có thể chứa nhiều dòng cho cùng execution. Khi tổng hợp số lần chạy, không được đếm mỗi dòng step là một job execution độc lập.

Không cập nhật trực tiếp `BATCH_JOB_EXECUTION.STATUS` hoặc dữ liệu trong `BATCH_STEP_EXECUTION_CONTEXT` để “mở khóa” một lần restart. Đây là state do framework quản lý; sửa tay có thể khiến restart đọc sai vị trí, bỏ qua dữ liệu hoặc tạo duplicate output.

## 5. Ví dụ cấu hình JDBC `JobRepository` cho production

Với **Spring Boot 3.x, Spring Batch 5.x** và PostgreSQL, một cấu hình đơn giản có thể dùng cùng `DataSource` cho metadata và dữ liệu nghiệp vụ (nếu yêu cầu bảo mật/phân tách cho phép).

### 5.1. Dependency Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Không tự cố định một phiên bản Spring Batch khác với dependency management của Spring Boot nếu chưa đánh giá tương thích. Khi dùng Spring Batch 6 hoặc Spring Boot đời khác, cần điều chỉnh code/import/cấu hình theo phiên bản thực tế.

### 5.2. `application.yml`

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/batch_runtime
    username: ${BATCH_DB_USER}
    password: ${BATCH_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never

app:
  batch:
    checkpoint-enabled: true
```

`app.batch.checkpoint-enabled` là **property ứng dụng minh họa**; Spring Batch không có công tắc toàn cục cùng tên. Khả năng lưu state tùy từng `ItemStream`, cấu hình step và repository. Đừng coi property tự đặt là cách bật restart.

Ý nghĩa các cấu hình Spring Boot:

- `spring.datasource.*`: thông tin kết nối database dùng bởi Boot khi không có datasource riêng được khai báo.
- `spring.batch.jdbc.initialize-schema=never`: production không tự chạy script tạo `BATCH_*` mỗi lúc startup. Schema phải được chuẩn bị bằng migration hoặc deployment procedure phù hợp.
- `spring.batch.job.enabled=false`: tránh Spring Boot tự động launch một job được tìm thấy ngay khi application context khởi động, nếu job được khởi chạy bởi scheduler/API/CLI có chủ đích. Điều này **không tắt** job launcher khi ứng dụng gọi trực tiếp.
- Hikari pool chỉ là ví dụ; kích thước phù hợp phụ thuộc số thread/chunk/partition và đặc điểm DB. Không tăng pool vô hạn vì metadata chậm.

**Lưu ý:** schema `BATCH_*` phải tồn tại và phù hợp với phiên bản Spring Batch trước khi job chạy. Dùng Flyway/Liquibase hoặc quy trình DDL được duyệt; Spring Batch cung cấp các script schema theo database, nhưng việc tự động tạo bảng ở môi trường production có thể yêu cầu quyền DDL quá rộng và gây rủi ro khi upgrade.

### 5.3. Một job có khả năng restart theo cùng kỳ dữ liệu

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersConfiguration {

    @Bean
    Step importOrdersStep(JobRepository repository,
                          PlatformTransactionManager transactionManager) {
        return new StepBuilder("importOrdersStep", repository)
            .tasklet((contribution, context) -> {
                String businessDate = contribution.getStepExecution()
                    .getJobParameters().getString("businessDate");
                if (businessDate == null) {
                    throw new IllegalArgumentException("Missing businessDate");
                }

                // Minh họa điểm vào xử lý, không phải pipeline nhập file đầy đủ.
                System.out.println("Processing businessDate=" + businessDate);
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Job importOrdersJob(JobRepository repository, Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
            .start(importOrdersStep)
            .build();
    }
}
```

Trong ví dụ, `JobRepository` do cấu hình Spring Batch/Boot cung cấp và `StepBuilder` nhận transaction manager rõ ràng như API Spring Batch 5.x. Tasklet trên **không tự lưu vị trí dòng**, vì nó chỉ minh họa khởi chạy. Một job đọc hàng triệu dòng cần reader/writer có `ItemStream`, checkpoint và transaction được thiết kế riêng.

Khởi chạy theo một kỳ:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16") // identifying mặc định
    .addString("sourceVersion", "file-v7")   // identifying
    .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

`jobLauncher` và `importOrdersJob` trong snippet là các bean đã inject. Nếu instance cho cùng tham số đã `COMPLETED`, Spring Batch thường từ chối chạy lại. Nếu trước đó `FAILED`/`STOPPED` và job cho phép restart, một execution khác có thể thuộc **cùng `JobInstance`**. Không thêm `UUID` identifying mới cho mỗi lần restart nếu muốn dùng checkpoint cũ.

## 6. Cùng database cho metadata và nghiệp vụ hay tách riêng?

Ngay cả khi đã chọn JDBC repository, vẫn phải quyết định metadata nằm **cùng database/datasource** với bảng nghiệp vụ hay trong một database riêng.

### Phương án A: chung database và transaction phù hợp

```text
       Spring Batch Step
          /       \
         v         v
  Business tables   BATCH_* tables
         \         /
          \       /
          Transaction boundary
              cùng database
```

**Ưu điểm:** ít kết nối và hạ tầng hơn; trong các chunk được cấu hình đúng, dữ liệu nghiệp vụ và checkpoint có thể tham gia cùng local database transaction. Việc rollback chunk giúp ngăn tình trạng đã cập nhật vị trí reader nhưng thay đổi nghiệp vụ trong chunk chưa commit.

**Nhược điểm:** quyền trên metadata và dữ liệu nghiệp vụ có thể khó tách; batch gây tải lớn ảnh hưởng trực tiếp kho metadata; nâng cấp schema hoặc xử lý sự cố database liên quan cả hai lớp.

### Phương án B: database/schema riêng cho metadata

```text
          Spring Batch Step
           /           \
          v             v
  Database nghiệp vụ    Database metadata
  (orders/report)       (BATCH_* tables)
       |                     |
  Transaction A          Transaction B
```

**Ưu điểm:** dễ tách quyền và quản trị retention, backup, scale hoặc monitoring; nhiều ứng dụng có thể dùng metadata infrastructure riêng mà không trao quyền truy cập rộng vào bảng nghiệp vụ.

**Nhược điểm quan trọng:** nếu step ghi nghiệp vụ vào database A, còn repository persist checkpoint vào database B bằng hai local transactions độc lập, **không có atomic commit tự động giữa chúng**. Một bên có thể commit trước khi bên kia thất bại. Khi restart, ứng dụng có thể đọc lại dữ liệu đã ghi hoặc bỏ sót tùy cách checkpoint/transaction được tổ chức.

Có thể dùng transaction phân tán trong một số kiến trúc, nhưng tăng độ phức tạp và không luôn tương thích với mọi hệ thống. Đa số trường hợp nên thiết kế writer **idempotent**, có business key/unique constraint và cơ chế đối soát. Nếu tính nguyên tử tuyệt đối giữa metadata và dữ liệu nghiệp vụ là yêu cầu cứng, hãy kiểm tra trực tiếp transaction wiring và khả năng của datasource/transaction manager thay vì chỉ nhìn vào tên database.

### Tách `DataSource` cần làm rõ bean wiring

Spring Boot cung cấp cơ chế chọn datasource dành cho Spring Batch khi có nhiều `DataSource`, chẳng hạn sử dụng annotation/cấu hình tương ứng với phiên bản Boot đang dùng. Nhưng việc chọn datasource cho **repository** không tự chuyển transaction của **step writer** sang cùng database. Trong Spring Batch 5.x, các builder như `.chunk(size, transactionManager)` nhận transaction manager cụ thể. Nếu dùng nhiều transaction manager, cần xác định từng step ghi vào nguồn nào và checkpoint được lưu ở đâu.

Kết quả mong muốn phải được kiểm chứng bằng integration test gây lỗi **sau một chunk đã commit** chứ không chỉ bằng việc khởi động context thành công.

## 7. Database nhúng: phù hợp khi nào?

Một database nhúng như H2 rất hữu ích trong demo và kiểm thử:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
  batch:
    jdbc:
      initialize-schema: always
```

Ví dụ dùng H2 in-memory cùng schema Spring Batch tương ứng. Nó có thể hỗ trợ các bài **integration test thực sự** với `JobRepository`, transaction và checkpoint trong vòng đời database test. Nhưng khi process/DB memory bị hủy, metadata có thể biến mất.

### Khi phù hợp

- Học cách Batch lưu `JobInstance`, `JobExecution`, `StepExecution` và context.
- Integration test cần repository JDBC nhưng dữ liệu có thể được tạo/xóa cho mỗi test.
- Một công cụ/demo chạy ngắn, không hứa hẹn tiếp tục sau khi process chết.

### Khi không phù hợp

- Job production dài, cần restart sau lỗi hoặc triển khai lại Pod.
- Nhiều node phải nhìn chung một lịch sử metadata.
- Cần backup, retention và truy vết nhiều kỳ qua nhiều lần deployment.
- Cần kiểm chứng SQL/locking/isolation đặc thù của PostgreSQL, Oracle hoặc database production mà H2 không mô phỏng đầy đủ.

**H2 dạng file** có thể lưu metadata qua lần restart của process nếu volume/đường dẫn tồn tại, nhưng vẫn có giới hạn về đồng thời, HA, backup, recovery và thao tác nhiều container. Việc file DB có tồn tại **không tự biến nó thành giải pháp production tương đương một RDBMS được vận hành đúng**.

Trong CI, nếu schema, transaction hay locking production là phần quan trọng của bài test, có thể dùng Testcontainers với cùng loại database thật, thay vì dựa hoàn toàn vào H2.

## 8. Repository không lưu state (resourceless) dùng cho bài toán nào?

Một số phiên bản Spring Batch mới có **`ResourcelessJobRepository`** phục vụ trường hợp không muốn duy trì metadata database. Đây là phương án có giá trị khi job đơn giản và chấp nhận hạn chế về trạng thái.

Ví dụ các công việc có thể cân nhắc:

- Tạo một file nhỏ từ input có thể đọc lại hoàn toàn, không có side effect không đảo ngược.
- Chạy một tasklet idempotent ngắn trong một process theo lịch bên ngoài, không cần xem lịch sử của những lần chạy trước trong Spring Batch.
- Pipeline mà mỗi invocation là một đơn vị cô lập, có cơ chế retry/rerun từ đầu do hệ thống khác điều phối, và việc đọc lại/ghi lại đã được thiết kế an toàn.

### Các giới hạn cần chấp nhận tường minh

1. Không dựa vào repository này để **restart từ checkpoint sau khi process chết** như với metadata JDBC bền vững.
2. Không coi nó là nơi lưu **job history bền vững** qua các lần deployment.
3. Không dùng như một **bộ điều phối nhiều process/nhiều node** để loại trừ các job trùng kỳ.
4. Kiểm tra rõ hỗ trợ concurrency và phạm vi sử dụng của implementation trong phiên bản Spring Batch đang chạy; repository nhẹ thường có hợp đồng đơn giản hơn JDBC.
5. Nếu batch cần audit, phải chủ động lưu lịch sử nghiệp vụ vào hệ thống khác; log tạm thời trong container chưa đủ cho yêu cầu truy vết bền vững.

Đừng dùng resourceless repository chỉ vì muốn **né việc tạo bảng `BATCH_*`** trong khi job vẫn có SLA restart hoặc dữ liệu đích không idempotent. Khi ấy chi phí “tiết kiệm một database” sẽ chuyển sang logic khôi phục thủ công, giám sát kỳ thiếu và xử lý dữ liệu trùng.

### Không còn metadata DB không có nghĩa không cần state

Nếu hệ thống bên ngoài lưu tiến độ, ví dụ một bảng `processed_files` hoặc message offset, về bản chất **bạn đã chuyển trách nhiệm state sang tầng ứng dụng/hạ tầng khác**. Lúc này cần định nghĩa rõ:

- Điểm nào được coi là đã commit?
- State được ghi **trước hay sau** khi output thực sự thành công?
- Ai bảo đảm không có hai worker nhận cùng kỳ?
- Process chết giữa ghi output và cập nhật state thì làm gì?
- Có cách nào truy vết lịch sử chạy và thực hiện backfill không?

Đây là một kiến trúc có thể hợp lệ, nhưng không thể coi nó có tính năng tương đương JDBC JobRepository chỉ vì cả hai đều “chạy được job”.

## 9. Scheduler, orchestration, queue và log có thay metadata database được không?

Các thành phần này có thể cung cấp **một phần thông tin**, nhưng cần phân biệt trách nhiệm:

| Thành phần | Nhiệm vụ chính | Không tự cung cấp đầy đủ |
| --- | --- | --- |
| `@Scheduled` | Kích hoạt method theo cron/fixed interval khi process còn chạy | Checkpoint `ItemStream`, lịch sử JobExecution bền vững |
| Quartz | Lưu trigger, misfire handling, lịch, clustering nếu cấu hình đúng | Metadata chunk/step và restart context Spring Batch |
| Kubernetes CronJob | Tạo Kubernetes Job/Pod theo lịch | Vị trí reader đã commit trong một job batch |
| Airflow/Control-M/orchestrator | Theo dõi DAG, dependency, lịch và kỳ dữ liệu | Tự động hiểu mọi trạng thái bên trong chunk Spring Batch |
| Message broker | Đẩy yêu cầu và giao lại khi lỗi | Chứng minh mọi side effect downstream chỉ áp dụng một lần |
| Application logs/traces | Chẩn đoán, timeline và correlation | Trạng thái transaction/checkpoint có thể restart một cách đáng tin |
| Business audit store | Lưu sự kiện nghiệp vụ và kết quả đã được công nhận | Hoàn toàn thay API JobRepository nếu không tự triển khai hợp đồng tương ứng |

Trong hệ thống enterprise, cách phối hợp hợp lý thường là:

```text
Orchestrator / Scheduler
        |
        | businessDate, sourceVersion
        v
Spring Batch JobLauncher / JobOperator
        |
        +--> Spring Batch Job/Step
        |         |
        |         +--> Business data / output
        |         +--> JobRepository JDBC (BATCH_*)
        |
        +--> Audit store / metrics / alerts
```

Scheduler trả lời **khi nào cần khởi chạy**. `JobRepository` trả lời **job/step đã chạy đến đâu, trạng thái gì, có thể restart thế nào**. Audit store trả lời **đầu vào, quy tắc, dữ liệu đầu ra nào được công nhận và ai/cái gì đã yêu cầu**. Chúng liên kết bằng `businessDate`, `jobInstanceId`, `jobExecutionId` và correlation ID, nhưng không trùng chức năng.

## 10. Tự xây metadata repository bằng Redis/NoSQL có đáng không?

Giả sử tổ chức đã có Redis hoặc một NoSQL store và muốn tránh RDBMS. Không nên suy ra Spring Batch có sẵn một `JobRepository` production trên mọi loại store đó. Nếu không có implementation phù hợp với phiên bản, muốn thay thế JDBC repository, đội phát triển phải tự triển khai **đúng hợp đồng** quản lý `JobInstance`, `JobExecution`, `StepExecution`, version và context.

Những yêu cầu tối thiểu không đơn giản:

- Tạo `JobInstance` một cách nguyên tử theo identifying parameters, tránh hai process cùng tạo trùng.
- Đảm bảo state transition phù hợp (`STARTING`, `STARTED`, `FAILED`, `COMPLETED`, v.v.).
- Thực hiện optimistic concurrency/version check để phát hiện update xung đột.
- Persist `ExecutionContext` sau checkpoint đúng lúc; tránh trạng thái đã tiến nhưng output chưa commit.
- Phục hồi và tra cứu execution/history khi process/node chết.
- Quản lý serialization và thay đổi schema/version của context.
- Cung cấp hành vi đáng tin khi có network partition, retry và timeout không rõ kết quả.
- Đáp ứng performance, monitoring, backup, disaster recovery và security.

Nếu dùng cache có eviction/TTL cho checkpoint mà không thiết kế rõ, dữ liệu phục hồi có thể biến mất đúng khi job cần restart. Nếu dùng Redis lock chỉ để điều phối launcher, lock đó **không tự thay** metadata execution.

Custom repository chỉ đáng cân nhắc khi có ràng buộc hạ tầng thực sự đặc biệt, năng lực kiểm thử/duy trì dài hạn và quyết định kiến trúc có bằng chứng. Với đa số batch enterprise, JDBC repository đã được Spring Batch hỗ trợ rộng rãi thường có tổng chi phí sở hữu thấp hơn việc tự viết repository phi quan hệ.

## 11. Transaction consistency là tiêu chí quan trọng nhất

Giả sử job nhập đơn hàng bằng chunk size 100. Trong một lần chạy:

```text
Chunk 1: records 1..100     -> output commit + checkpoint
Chunk 2: records 101..200   -> output commit + checkpoint
Chunk 3: records 201..300   -> process chết trước commit
```

Với cơ chế checkpoint và transaction phù hợp, restart có thể tiếp tục từ mốc trước chunk 3. Nhưng nếu metadata và business output **không thuộc cùng transaction nguyên tử**, có thể xảy ra hai kiểu sai lệch:

| Tình huống | Điều có thể xảy ra | Hậu quả tiềm ẩn |
| --- | --- | --- |
| Output đã commit nhưng checkpoint chưa commit | Restart đọc lại một số item đã ghi ra đích | Duplicate nếu writer không idempotent |
| Checkpoint được cập nhật nhưng output thực tế chưa commit | Reader mở lại ở vị trí mới | Có nguy cơ bỏ sót dữ liệu |

Một repository bền vững **giúp ghi nhớ state**, nhưng không thể tự sửa sai transaction boundary của ứng dụng. Để chống hai lớp rủi ro này:

1. Đảm bảo wiring transaction manager/datasource của chunk và repository được hiểu rõ; khi cần tính nguyên tử, ưu tiên transaction boundary có thể bao phủ cả business write và metadata.
2. Dùng unique business key, upsert hoặc writer idempotent; đặc biệt cần thiết với hệ thống đích bên ngoài.
3. Với API/messaging, dùng idempotency key ổn định, transactional outbox và reconciliation khi phù hợp.
4. Chạy integration test gây lỗi **sau ít nhất một chunk commit** và xác nhận output cuối chính xác.

### `saveState` và `ItemStream` không thể bị bỏ qua

Nếu reader/writer cần khôi phục vị trí, chúng phải tham gia vòng đời `ItemStream`:

```java
// Mẫu minh họa một reader được framework quản lý.
FlatFileItemReader<OrderRow> reader =
    new FlatFileItemReaderBuilder<OrderRow>()
        .name("ordersReader")
        .resource(inputResource)
        .lineMapper(orderLineMapper)
        .saveState(true)
        .build();
```

`OrderRow`, `inputResource` và `orderLineMapper` là thành phần do ứng dụng cung cấp. `name` cần ổn định để state có key rõ ràng; `.saveState(true)` cho phép reader lưu state hỗ trợ restart. Nếu bọc một `ItemStream` trong delegate mà step không nhận diện, phải đăng ký/ủy quyền `open`, `update`, `close` đúng cách. **Chọn JDBC metadata repository chưa đủ** nếu chính reader/writer không lưu checkpoint hoặc input thay đổi giữa các lần chạy.

## 12. Khả năng chạy đồng thời và HA

Một tình huống phổ biến: có hai instance Spring Boot cùng cấu hình `@Scheduled(cron = ...)`, cả hai đến giờ và gọi `JobLauncher`.

```text
Node A 02:00 -> launch importOrdersJob(businessDate=2026-11-16)
Node B 02:00 -> launch importOrdersJob(businessDate=2026-11-16)
                   |
                   v
          Shared JDBC JobRepository
                   |
           cùng JobInstance key
```

Một JDBC repository chia sẻ có thể phát hiện/giới hạn nhiều tình huống chạy đồng thời của **cùng `JobInstance`** thông qua identity và transaction. Nhưng:

- Nếu Node A dùng `runId=A`, Node B dùng `runId=B` như **identifying** parameters, chúng có thể tạo hai instance khác nhau mà cùng xử lý dữ liệu ngày 16/11.
- Repository không phải cluster-wide scheduler leader election cho tất cả các trigger.
- Nếu hai job instance khác nhau cùng ghi một file/table, vẫn cần output policy và unique key/lock phù hợp.
- Trạng thái `STARTED` có thể bị để lại khi process chết đột ngột; cần quy trình vận hành để kiểm tra trạng thái thực tế trước khi restart.

Với yêu cầu **mỗi kỳ nghiệp vụ chỉ xử lý một lần**, thiết kế nhiều lớp: identifying parameters dựa trên kỳ/input, scheduler phân tán hoặc một nguồn trigger duy nhất, database constraint/idempotency ở đích và reconciliation khi bị lỗi.

### Lưu metadata bền vững nhưng triển khai ứng dụng stateless

Trong Kubernetes, có thể để Pod batch chạy ngắn, đọc ghi nghiệp vụ từ database/object storage và lưu metadata trên RDBMS bền vững bên ngoài Pod. Pod mới có thể truy cập `JobRepository` cũ nếu credentials, schema và network còn hợp lệ. Tuy nhiên, nếu reader lưu state là **offset vào file local của Pod cũ**, file không còn trên Pod mới sẽ làm restart thất bại. Restart thành công đòi hỏi **cả metadata và input/output resources** còn truy cập được, không chỉ repository database.

## 13. Performance: metadata database có thực sự quá tốn kém?

Trong chunk-oriented processing, `JobRepository` cần cập nhật metadata và context theo các mốc thực thi/checkpoint. Điều này tạo chi phí transaction/I/O. Tuy vậy, trước khi bỏ repository bền vững, cần đo phần overhead thực sự so với:

- Query và fetch dữ liệu nguồn.
- Processor CPU, serialization và memory allocation.
- Ghi database theo batch, network/API latency và transaction lock.
- Kích thước `ExecutionContext`/số key được serialize.
- Tần suất commit do `chunk size` quá nhỏ.
- Độ trễ kết nối metadata DB và index/locking trong các bảng `BATCH_*`.

Đừng kết luận “JobRepository chậm” chỉ vì log có nhiều câu `UPDATE BATCH_STEP_EXECUTION`. Nếu mỗi item tự commit, việc tăng chunk size có thể giảm số lần cập nhật metadata nhiều hơn so với thay toàn bộ cơ chế lưu state — nhưng chunk lớn có trade-off về lock, memory và số item phải làm lại khi lỗi.

### Gợi ý tối ưu trước khi thay storage

| Biện pháp | Lợi ích | Rủi ro cần đo |
| --- | --- | --- |
| Chọn chunk size phù hợp | Giảm commit/metadata round-trip | Transaction dài và rollback nhiều item hơn |
| Giữ `ExecutionContext` nhỏ | Giảm serialization và I/O | Không được bỏ state cần restart |
| Chỉnh index/connection pool DB | Giảm chờ connection, locking, query cost | Pool quá lớn gây overload database |
| Tách tải nghiệp vụ và metadata khi cần | Cô lập workload | Transaction chéo DB không còn atomic mặc định |
| Housekeeping metadata đã hết vòng đời | Giảm table growth/backup cost | Xóa quá sớm mất lịch sử/restart |
| Tối ưu reader/writer và SQL | Tăng throughput thực tế | Phải kiểm thử checkpoint, idempotency |

Một batch processing 100 triệu bản ghi không nhất thiết phải có 100 triệu hàng trong `BATCH_*`: metadata chủ yếu theo job/step execution và context, không lưu mỗi item như một event theo mặc định. Vấn đề hiệu năng có thể nằm ở SQL, I/O hay kích thước chunk, không ở quy mô dữ liệu nguồn trực tiếp.

## 14. Retention, audit, backup và bảo mật

### 14.1. Giữ metadata bao lâu?

Không nên giữ toàn bộ metadata mãi mãi mà không có kế hoạch, nhưng cũng không nên xóa ngay sau khi job `FAILED`. Nếu xóa context của một instance còn cần restart, khả năng phục hồi có thể mất.

Một chiến lược thường gồm:

1. **Execution còn cần restart:** giữ toàn bộ instance/execution/step/context cần thiết.
2. **Execution đã hết vòng đời vận hành:** lưu theo SLA troubleshoot và dashboard; có kế hoạch xóa/archive sau một khoảng thời gian được chấp thuận.
3. **Audit nghiệp vụ dài hạn:** lưu vào kho audit riêng, có business key, nguồn input, output manifest/checksum và người/trigger khởi chạy.
4. **Backup và phục hồi:** kiểm tra bản sao DB metadata thực sự có thể kết hợp với bản sao dữ liệu nghiệp vụ/input/output để khôi phục một lần chạy đang dở.

Việc dọn bảng `BATCH_*` cần tôn trọng quan hệ khóa ngoại và execution đang hoạt động; không chạy `DELETE` hàng loạt bằng lịch tự động thiếu điều kiện. Một báo cáo audit tổng hợp ở kho khác **không đủ để Spring Batch restart** nếu checkpoint chi tiết đã bị xóa.

### 14.2. Dữ liệu nhạy cảm trong metadata

`JobParameters`, `ExecutionContext` và `EXIT_MESSAGE` có thể chứa giá trị nhạy cảm nếu developer đưa vào. Ví dụ sau là một cấu hình **không nên dùng**:

```java
new JobParametersBuilder()
    .addString("apiToken", "secret-token-here")
    .toJobParameters();
```

Đây là cách khiến secret có thể bị persist trong bảng metadata và hiển thị qua log/dashboard. Thay vào đó, dùng secret manager, workload identity hoặc credentials ngắn hạn, chỉ truyền **tham chiếu** và business parameters không nhạy cảm.

Quyền database nên tách runtime user (DML cần thiết cho metadata) khỏi migration user (DDL). Quyền đọc các bảng metadata cũng cần phân chia: người vận hành xem trạng thái có thể không cần xem toàn bộ `ExecutionContext` và stack trace chứa dữ liệu nội bộ.

## 15. Quyết định theo nhu cầu: bảng đánh đổi

| Nhu cầu/tiêu chí | JDBC bền vững | JDBC in-memory | Resourceless/không lưu bền vững | External state tự xây |
| --- | --- | --- | --- | --- |
| Restart sau khi process chết | Phù hợp khi state/resource đúng | Không đáng tin sau DB memory mất | Không phù hợp nếu cần checkpoint bền vững | Chỉ phù hợp nếu tự xây đúng hợp đồng |
| Theo dõi job history qua deployment | Có | Thường không | Không mặc định | Tùy thiết kế |
| Nhiều node chia sẻ execution state | Hỗ trợ qua database chung và cấu hình đúng | Không phù hợp | Không phải mục tiêu | Phức tạp, phải tự xử lý concurrency |
| Setup đơn giản cho test | Có thể dùng Testcontainers | Rất phù hợp | Có thể phù hợp nếu test không cần metadata | Thường không cần |
| Transaction/checkpoint có tính nhất quán | Có thể phối hợp với business DB | Có trong phạm vi DB test | Không có checkpoint DB bền vững | Tùy khả năng atomic commit tự xây |
| Backup/DR | Theo hạ tầng DB | Không | Không có lịch sử bền vững mặc định | Phải thiết kế riêng |
| Chi phí hạ tầng | Có DB/schema/ops | Thấp | Rất thấp cho job đơn giản | Dễ tăng chi phí phát triển/bảo trì |
| Nguy cơ mất dữ liệu khi restart sai | Giảm nếu cấu hình đúng | Cao sau khi process chết | Cao nếu dựa vào state đã mất | Tùy mức hoàn thiện |

### Gợi ý chọn nhanh

```text
Job có cần tiếp tục từ checkpoint sau process/node failure không?
                     |
                  +--+--+
                  |     |
                 Có   Không
                  |     |
                  v     v
        Dùng JDBC DB    Có cần giữ lịch sử execution
        bền vững        hoặc phối hợp nhiều node không?
                        |            |
                       Có           Không
                        |            |
                        v            v
                  JDBC DB        Có thể xem xét repository
                  bền vững      nhẹ/in-memory cho job nhỏ
                                nếu chấp nhận rerun từ đầu
```

**Lưu ý:** sơ đồ là một cách ra quyết định ban đầu, không thay kiểm tra transaction, output, compliance và giới hạn của phiên bản framework. Nếu nghiệp vụ không cho phép mất hoặc nhân đôi tác động, việc không cần “checkpoint reader” vẫn **không đồng nghĩa** có thể tùy tiện bỏ durable state/idempotency.

## 16. Bốn tình huống thực tế

### Tình huống A: job đối soát thanh toán hằng đêm

Yêu cầu: 3 triệu giao dịch/ngày; có nhiều step; nếu job lỗi phải tiếp tục từ chunk đã commit; có màn hình giám sát và audit.

**Đề xuất:** JDBC `JobRepository` trên RDBMS bền vững, backup và schema được quản lý, identifying parameters theo `businessDate`/source version. Reader lưu checkpoint, writer idempotent bằng khóa giao dịch; lưu audit nghiệp vụ riêng. Nếu DB metadata và DB nghiệp vụ khác nhau, kiểm thử transaction boundary và reconciliation kỹ càng.

Tại sao không dùng in-memory/resourceless? Vì mất state sau khi process chết sẽ kéo theo nhu cầu chạy lại hàng triệu giao dịch, tăng rủi ro duplicate và khó giải trình.

### Tình huống B: tạo một báo cáo nhỏ có thể làm lại từ đầu

Yêu cầu: đọc dữ liệu bất biến, tạo file tạm trong vài giây; nếu lỗi có thể xóa file tạm và chạy lại toàn bộ; không có yêu cầu lịch sử execution bên trong Batch.

**Có thể cân nhắc:** repository nhẹ phù hợp phiên bản, hoặc JDBC in-memory trong môi trường đơn giản. Phải bảo đảm file output là tạm/versioned, publish chỉ khi kết quả hợp lệ và rerun không nối/ghi đè sai. Scheduler/orchestrator vẫn cần biết trigger nào thất bại để phát lại.

Tại sao lựa chọn này có thể đúng? Vì **chạy lại từ đầu được thiết kế là an toàn**, không cần phục hồi giữa dòng. Nhưng nếu cần audit dài hạn, vẫn phải có kho audit bên ngoài.

### Tình huống C: nhiều Pod xử lý file lớn trên object storage

Yêu cầu: CronJob tạo Pod; Pod có thể bị thay thế; reader xử lý theo partition; input nằm trên S3; cần backfill.

**Đề xuất:** JDBC repository ngoài Pod, input object version cố định trong parameters, partition key ổn định và writer idempotent. Quản lý restart với resource có thể mở lại từ Pod mới. Nếu dùng scheduler phân tán, scheduler lưu lịch riêng; đừng trông chờ `JobRepository` phát trigger đã bị lỡ.

Rủi ro lớn nhất không chỉ là DB metadata, mà là **partition range/reader state và object version** thay đổi giữa hai lần chạy, hoặc hai Pod cùng publish một output key.

### Tình huống D: kiến trúc đã có workflow engine và audit store

Yêu cầu: orchestrator giữ trạng thái DAG, có bảng `business_batch_run` và hệ thống event log. Nhóm muốn bỏ `BATCH_*` để “tránh lưu hai lần”.

**Cân nhắc:** giữ JDBC repository nếu đang sử dụng `ItemStream` checkpoint/restart của Spring Batch. Audit store chứa sự kiện nghiệp vụ và DAG engine chứa lịch/flow; chúng không thay `StepExecutionContext` một cách tự nhiên. Nếu công việc thực chất chỉ là một thao tác idempotent nguyên khối có thể retry từ đầu, có thể xem xét repository nhẹ và chuyển trách nhiệm recovery rõ ràng sang orchestrator.

Đừng xóa repository trước khi làm rõ rằng orchestrator có biết **chunk nào đã commit** hay chỉ biết “task chạy thành công/thất bại”.

## 17. Kiểm thử để chứng minh lựa chọn metadata là đúng

Một thiết kế metadata không nên chỉ được đánh giá bởi việc `ApplicationContext` khởi động thành công. Cần kiểm thử các thuộc tính mà phương án đã hứa hẹn.

### 17.1. JDBC repository + restart thật

Với Spring Batch 5.x, dùng `@SpringBatchTest`, `JobLauncherTestUtils` hoặc `JobLauncher` để chạy job trên database thử nghiệm. Kịch bản:

1. Input gồm `A001` đến `A005`, chunk size 2.
2. Chunk đầu commit `A001`, `A002`; writer/processor gây lỗi có kiểm soát ở chunk sau.
3. Kiểm tra execution đầu là `FAILED`, output nghiệp vụ đã commit chỉ có phần đầu.
4. Khởi chạy lại **cùng identifying `JobParameters`** với cùng input version và repository giữ nguyên.
5. Kiểm tra execution sau `COMPLETED`, cùng `JobInstance.id` nhưng `JobExecution.id` khác nhau, output cuối có đúng 5 business keys.
6. Kiểm tra không có duplicate, không thiếu item, context được áp dụng và dữ liệu đã commit không bị nhân đôi.

Mẫu assertions, giả định `first`, `restarted` và `jdbcTemplate` đã được chuẩn bị:

```java
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(restarted.getJobInstance().getId())
    .isEqualTo(first.getJobInstance().getId());

assertThat(restarted.getId()).isNotEqualTo(first.getId());

List<String> ids = jdbcTemplate.queryForList(
    "SELECT order_id FROM processed_orders ORDER BY order_id",
    String.class
);
assertThat(ids).containsExactly("A001", "A002", "A003", "A004", "A005");
```

Đây là **phần assert minh họa** cho một integration test, không phải class test hoàn chỉnh; `processed_orders` và fixture lỗi phải được tạo trong môi trường kiểm thử. Nếu repository đặt ở database khác với dữ liệu đích, chạy thêm test cố ý làm một trong hai phía lỗi khi commit để quan sát và chứng minh cơ chế idempotency/reconciliation.

### 17.2. Restart qua hai process/Pod khác nhau

Test trong cùng JVM chưa chứng minh khả năng khôi phục khi process chết. Với mục tiêu durable restart, cần thử:

- Execution #1 chạy trên process A, commit vài chunk rồi dừng/kill tại điểm kiểm thử.
- Giữ database metadata, input object/version và output tạm đã commit.
- Process B mới khởi động với cấu hình/credentials tương thích.
- Process B restart cùng `JobInstance` theo quy trình vận hành.
- Output được đối soát đúng, không có row/file/message bị nhân đôi.

Nếu state chỉ nằm trong H2 in-memory hoặc file local ephemeral của Pod A, test này sẽ bộc lộ khoảng trống của kiến trúc.

### 17.3. Test job chạy đồng thời

Hai launcher cố khởi động cùng identifying parameters gần như cùng lúc. Kiểm tra trạng thái metadata và xử lý exception/concurrency đúng, đồng thời đảm bảo output không trùng. Chạy thêm trường hợp hai job instance có **parameters khác nhau nhưng cùng business key**, để thấy repository không thay thế unique constraint/scheduler lock cho output.

### 17.4. Test resourceless hoặc không có state bền vững

Nếu chọn phương án nhẹ, test phải mô tả hợp đồng **rerun từ đầu**:

- Tắt process hoặc tạo invocation mới sau lỗi; không kỳ vọng checkpoint cũ tự xuất hiện.
- Input không đổi hoặc có version cố định.
- Output tạm thất bại được cách ly/cleanup đúng chính sách.
- Chạy lại từ đầu vẫn cho đúng một kết quả cuối, nhờ idempotency hoặc publish một lần.
- Hệ thống bên ngoài phát hiện kỳ chưa hoàn tất và kích hoạt lại theo SLA.

Không viết test kỳ vọng `JobExplorer` có lịch sử xuyên process nếu repository đã chọn không hỗ trợ tính năng đó.

## 18. Checklist quyết định trước khi triển khai

| Câu hỏi kiến trúc | Lý do cần làm rõ |
| --- | --- |
| Job có thể chạy vài giờ hoặc xử lý hàng triệu item không? | Chi phí chạy lại từ đầu có thể lớn |
| Có yêu cầu restart từ checkpoint sau mất điện/kill Pod không? | Đòi hỏi state bền vững và input/output ổn định |
| Có nhiều node/launcher cùng khởi chạy không? | Cần shared metadata và điều phối trùng kỳ |
| Output có idempotent không? | Chống duplicate khi retry/restart hoặc commit không nguyên tử |
| Metadata và business data có chung transaction được không? | Quyết định rủi ro sai lệch checkpoint với output |
| Có cần tra lịch sử execution và phục vụ audit không? | Chọn storage/retention/bảo mật phù hợp |
| Schema `BATCH_*` được tạo và nâng cấp thế nào? | Tránh lỗi startup và incompatibility khi update framework |
| `JobParameters` identifying được định nghĩa ra sao? | Quyết định restart đúng instance hay chạy mới |
| Input và output còn sau khi Pod được thay không? | Repository bền vững không đủ nếu resource biến mất |
| Có chính sách cleanup metadata không? | Tránh DB tăng vô hạn hoặc xóa state còn cần restart |
| Team có đủ năng lực xây custom repository không? | Đánh giá chi phí bảo trì và rủi ro consistency |
| Đã thử crash/restart và chạy đồng thời chưa? | Kiểm chứng hợp đồng thiết kế trong điều kiện lỗi thật |

## 19. Mẫu ADR cho quyết định metadata

**Architecture Decision Record (ADR)** giúp người sau hiểu tại sao dự án đã chọn một cơ chế lưu metadata và những giới hạn phải chấp nhận.

```markdown
# ADR: Metadata repository for importOrdersJob

## Context
- Job xử lý khoảng 2 triệu dòng/ngày.
- Có khả năng Pod bị restart khi đang xử lý.
- Yêu cầu tiếp tục từ chunk đã commit và lưu lịch sử 90 ngày.

## Decision
- Dùng Spring Batch JDBC JobRepository trên PostgreSQL bền vững.
- Dùng businessDate + sourceVersion làm identifying JobParameters.
- Reader dùng ItemStream với checkpoint; writer idempotent bằng business key.
- Scheduler lưu trigger riêng, audit store giữ output manifest.

## Consequences
- Cần migration/schema BATCH_*, backup, metrics và housekeeping.
- Nếu metadata và output ở hai DB khác nhau, cần reconciliation.
- Không dùng H2 in-memory hoặc repository không bền vững cho production.

## Verification
- Integration test fail/restart với cùng JobInstance.
- Kill Pod rồi restart ở Pod mới.
- Test hai launcher đồng thời và chống trùng output.
```

Các số liệu và thời hạn trong ADR là **ví dụ minh họa**, không phải yêu cầu mặc định của Spring Batch. Nội dung ADR thực tế phải bám SLA, chính sách dữ liệu và hạ tầng của tổ chức.

## 20. Kết luận

Với Spring Batch, lựa chọn metadata database là lựa chọn về **khả năng nhớ và khôi phục trạng thái thực thi**, không đơn thuần là lựa chọn một nơi ghi log. Khi job production cần restart sau lỗi, checkpoint, theo dõi nhiều execution hoặc phối hợp nhiều node, **JDBC `JobRepository` trên RDBMS bền vững thường là phương án nên ưu tiên**. Database nhúng in-memory hữu ích cho test/demo; resourceless repository có thể phù hợp với job ngắn và chấp nhận chạy lại từ đầu; custom repository là bài toán kiến trúc phức tạp cần lý do mạnh và năng lực bảo trì.

Scheduler, audit store và message broker có vai trò quan trọng nhưng **không mặc nhiên thay `JobRepository`**. Một thiết kế đúng phải gắn lựa chọn storage với transaction, `ExecutionContext`, tính ổn định của input, quyền truy cập output, idempotency, retention và kiểm thử failure/restart thực tế.

## Tài liệu tham khảo

- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): vai trò repository, cấu hình JDBC và transaction liên quan.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng `BATCH_*`, `JobInstance`, `JobExecution`, `StepExecution` và context.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobParameters`, lifecycle, trạng thái và restart.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): hợp đồng `open`, `update`, `close` và lưu checkpoint.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử execution, step, restart và Spring Batch Test.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): auto-configuration, schema initialization và khởi chạy job.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary và phối hợp các transaction manager.
