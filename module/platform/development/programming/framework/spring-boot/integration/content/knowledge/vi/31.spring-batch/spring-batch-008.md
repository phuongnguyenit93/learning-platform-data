# Điều kiện ngừng tự cấu hình khi dùng @EnableBatchProcessing hoặc cấu hình riêng

## 1. Vấn đề trong một ứng dụng tích hợp Spring Boot

Một dịch vụ nhận dữ liệu đối tác qua HTTP/SFTP, xử lý theo lô và ghi vào PostgreSQL cần quản lý tiến độ, transaction, retry và khả năng chạy tiếp sau lỗi. Spring Batch cung cấp `Job`, `Step`, `JobRepository` và `JobLauncher` để giải quyết phần batch; Spring Boot bổ sung cơ chế tự cấu hình để giảm việc khai báo các bean hạ tầng.

Một lỗi thường gặp là thêm `@EnableBatchProcessing` vào lớp `@Configuration` vì nghĩ annotation này bắt buộc để “bật Batch”. Sau đó Job không chạy lúc ứng dụng khởi động, bảng `BATCH_*` không được tạo, hoặc ứng dụng báo thiếu `DataSource`/`transactionManager`. Điều này có thể là **hành vi có chủ đích**: Spring Boot dừng tự cấu hình Batch khi phát hiện ứng dụng đã chọn cấu hình hạ tầng Spring Batch bằng tay.

Bài này tập trung vào **Spring Boot 3.x và Spring Batch 5.x (Java 17+)**: những điều kiện khiến auto-configuration không kích hoạt, hệ quả khi dùng `@EnableBatchProcessing` hoặc kế thừa `DefaultBatchConfiguration`, cách chuyển từ Boot tự cấu hình sang quản lý hạ tầng riêng, và phương pháp kiểm chứng. Các nhánh Spring Boot 4.x / Spring Batch 6.x có cơ chế repository khác, cần đọc tài liệu đúng phiên bản trước khi áp dụng.

## 2. Ai tạo hạ tầng Spring Batch?

Spring Batch định nghĩa hạ tầng nghiệp vụ: `JobRepository` ghi metadata và trạng thái Job/Step, `JobExplorer` đọc lịch sử, `JobLauncher` khởi chạy Job với `JobParameters`, còn `ItemReader`/`ItemProcessor`/`ItemWriter` xử lý dữ liệu theo chunk.

Spring Boot có thể đăng ký hạ tầng Batch theo điều kiện, tự khởi tạo các bảng metadata JDBC và tạo `JobLauncherApplicationRunner` để chạy Job khi startup. Nhưng `@EnableBatchProcessing` là một cách **Spring Batch tự tạo hạ tầng**, không phải annotation yêu cầu Boot tự cấu hình thêm.

| Hạng mục | Để Boot auto-configure | Dùng `@EnableBatchProcessing`/`DefaultBatchConfiguration` |
| --- | --- | --- |
| Tạo `JobRepository`, `JobLauncher`, `JobExplorer` | Boot chọn hạ tầng theo dependency và bean hiện có | Spring Batch cấu hình theo lựa chọn của ứng dụng |
| Chọn nguồn metadata | Có thể dùng cơ chế Boot như `@BatchDataSource` | Chỉ định `dataSourceRef` và `transactionManagerRef` hoặc override getter |
| Khởi tạo bảng `BATCH_*` | Thuộc quản lý schema initializer của Boot | Ứng dụng tự chuẩn bị schema hoặc migration |
| Chạy Job khi startup | Boot có thể tạo `JobLauncherApplicationRunner` | Cần tự tạo trigger/runner nếu muốn tự chạy |
| Kiểm soát transaction, table prefix | Properties và các điểm mở rộng của Boot | Cấu hình trực tiếp qua Spring Batch |

Không nên tạo đồng thời hai con đường cấu hình vì có thể đụng tên bean `jobRepository`, `jobLauncher` hoặc tạo các transaction manager có hành vi khó dự đoán.

## 3. Điều kiện kích hoạt và điều kiện back off của Spring Boot 3.x

Trong Spring Boot 3.x, cấu hình `BatchAutoConfiguration` có thể hiểu qua các điều kiện ở cấp lớp (đoạn dưới đây rút gọn để giải thích, không phải mã cần sao chép vào ứng dụng):

~~~java
@ConditionalOnClass({
    JobLauncher.class,
    DataSource.class,
    DatabasePopulator.class
})
@ConditionalOnBean({
    DataSource.class,
    PlatformTransactionManager.class
})
@ConditionalOnMissingBean(
    value = DefaultBatchConfiguration.class,
    annotation = EnableBatchProcessing.class
)
class BatchAutoConfiguration {
    // Các bean và cấu hình con do Spring Boot cung cấp.
}
~~~

Điều kiện mang ba ý nghĩa:

1. **Classpath:** phải có Spring Batch, JDBC và các class cần thiết.
2. **Bean tiền điều kiện:** với Boot 3.x phải có `DataSource` và `PlatformTransactionManager` phù hợp.
3. **Không có người cấu hình thay:** nếu thấy một bean thuộc `DefaultBatchConfiguration` **hoặc** cấu hình mang `@EnableBatchProcessing`, điều kiện `@ConditionalOnMissingBean` không đạt và `BatchAutoConfiguration` **back off**.

~~~mermaid
flowchart TD
    A["Boot đánh giá BatchAutoConfiguration"] --> B{"Đủ class và bean tiền điều kiện?"}
    B -->|Không| C["Auto-config Batch không kích hoạt"]
    B -->|Có| D{"Có @EnableBatchProcessing hoặc DefaultBatchConfiguration?"}
    D -->|Có| E["Boot nhường quyền cấu hình Batch"]
    D -->|Không| F["Boot áp dụng auto-config khi các điều kiện con đạt"]
    E --> G["Ứng dụng quản lý repository, schema, trigger"]
    F --> H["Boot cung cấp tiện ích cấu hình Batch"]
~~~

**Phân biệt hai nguyên nhân:** thiếu `DataSource` hoặc transaction manager là *không đạt tiền điều kiện*, còn `@EnableBatchProcessing`/`DefaultBatchConfiguration` là *điều kiện back off* do ứng dụng đã tự cấu hình. Hai trường hợp có triệu chứng giống nhau nhưng cách khắc phục khác nhau.

### So sánh tình huống dễ nhầm

| Thao tác | `BatchAutoConfiguration` back off vì thao tác này? | Giải thích |
| --- | --- | --- |
| Thêm `@EnableBatchProcessing` lên một lớp `@Configuration` | **Có** | Dấu hiệu ứng dụng tự cấu hình Batch |
| Lớp cấu hình kế thừa `DefaultBatchConfiguration` | **Có** | Cơ chế lập trình thay thế annotation |
| Chỉ khai báo `@Bean Job` và `@Bean Step` | **Không** | Boot vẫn có thể tự cấu hình hạ tầng |
| Đặt `spring.batch.job.enabled=false` | **Không** | Chỉ tắt khởi chạy Job tự động do Boot cung cấp |
| Đặt `spring.batch.jdbc.initialize-schema=never` | **Không** | Chỉ tắt việc Boot khởi tạo schema Batch |
| Định nghĩa `DataSource` hoặc `PlatformTransactionManager` riêng | **Không mặc nhiên** | Có thể ảnh hưởng các điều kiện bean và lựa chọn nguồn |
| Định nghĩa riêng `JobRepository` mà không chọn một cơ chế đầy đủ | **Không mặc nhiên** | Cần xem các điều kiện và tránh trùng hạ tầng |

Điểm quyết định: **“Tắt Job chạy khi startup” khác với “tắt Boot Batch auto-configuration”.** Không dùng `@EnableBatchProcessing` chỉ để Job ngừng chạy lúc ứng dụng khởi động.

## 4. Trường hợp nên giữ Spring Boot tự cấu hình

Ứng dụng dùng một database cho Batch metadata và muốn Boot quản lý phần mặc định có thể dùng:

~~~kotlin
// build.gradle.kts — Spring Boot 3.x
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-batch")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

~~~yaml
# application.yml — minh họa môi trường phát triển
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/integration
    username: integration_app
    password: ${DB_PASSWORD}
  batch:
    jdbc:
      initialize-schema: always
    job:
      enabled: true
~~~

`initialize-schema: always` giúp Boot tạo schema Batch trên database được cấu hình. Với production nên dùng Flyway/Liquibase hoặc quy trình migration có kiểm soát và thường đặt `initialize-schema: never`; không tùy tiện khởi tạo schema ở mỗi lần deploy.

Khi Boot tự cấu hình, có một `Job` bean và runner được bật, Boot thường chạy Job lúc startup. Nếu có nhiều Job, cần chọn Job cụ thể bằng `spring.batch.job.name` hoặc thiết kế trigger riêng phù hợp phiên bản.

Nếu chỉ muốn tạo Job nhưng đợi API, scheduler hoặc orchestration bên ngoài kích hoạt:

~~~yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Lúc này Boot vẫn có thể tạo `JobRepository`/`JobLauncher` khi đủ điều kiện. `spring.batch.job.enabled=false` **không làm Boot back off** và `JobLauncher` vẫn có thể được inject để khởi chạy theo yêu cầu.

Nếu ứng dụng có hai `DataSource` và chỉ cần metadata Batch nằm ở một nguồn riêng, hãy cân nhắc cơ chế `@BatchDataSource` của Boot trước khi quyết định tự quản lý mọi hạ tầng.

## 5. Phương án cấu hình riêng A: @EnableBatchProcessing

Khi cần kiểm soát rõ nguồn metadata và transaction manager, có thể cấu hình Spring Batch 5.x bằng annotation:

~~~java
// ManualBatchInfrastructure.java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager",
    tablePrefix = "BATCH_"
)
public class ManualBatchInfrastructure {

    // Một bean DataSource tên batchDataSource phải do ứng dụng cung cấp.
    @Bean("batchTransactionManager")
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource ds) {
        return new DataSourceTransactionManager(ds);
    }
}
~~~

`batchDataSource` là bean có sẵn, được khai báo trong phần kết nối/môi trường của ứng dụng. `dataSourceRef` và `transactionManagerRef` là **tên bean**, không phải khóa trong `application.yml`. Điều này quan trọng khi dịch vụ có một database cho metadata Batch và database khác cho nghiệp vụ.

Một Job/Step tối giản theo API Spring Batch 5.x:

~~~java
// PartnerImportJobConfiguration.java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class PartnerImportJobConfiguration {

    @Bean
    Job importPartnerData(JobRepository repository, Step importPartnerStep) {
        return new JobBuilder("importPartnerData", repository)
                .start(importPartnerStep)
                .build();
    }

    @Bean
    Step importPartnerStep(
            JobRepository repository,
            @Qualifier("batchTransactionManager")
            PlatformTransactionManager transactionManager) {
        return new StepBuilder("importPartnerStep", repository)
                .tasklet((contribution, context) -> {
                    // Minh họa wiring. Thay bằng adapter xử lý dữ liệu thật.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

Đây là ví dụ wiring, chưa phải ứng dụng import hoàn chỉnh. Với dữ liệu lớn nên dùng chunk-oriented processing và thiết kế `ItemReader`, `ItemProcessor`, `ItemWriter`, giới hạn retry/skip, commit interval và chiến lược restart.

Trong phương án thủ công, **Spring Boot không còn tự chịu trách nhiệm khởi tạo bảng `BATCH_*` hay tạo runner Batch mặc định**. Phải xử lý cả hai phần.

## 6. Phương án cấu hình riêng B: kế thừa DefaultBatchConfiguration

`DefaultBatchConfiguration` cung cấp hạ tầng Spring Batch qua lớp Java và các getter có thể override. Với Spring Batch 5.x:

~~~java
// ExplicitBatchConfiguration.java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.support.DefaultBatchConfiguration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ExplicitBatchConfiguration extends DefaultBatchConfiguration {

    private final DataSource metadataDataSource;
    private final PlatformTransactionManager metadataTransactionManager;

    public ExplicitBatchConfiguration(
            @Qualifier("batchDataSource") DataSource metadataDataSource,
            @Qualifier("batchTransactionManager")
            PlatformTransactionManager metadataTransactionManager) {
        this.metadataDataSource = metadataDataSource;
        this.metadataTransactionManager = metadataTransactionManager;
    }

    @Override
    protected DataSource getDataSource() {
        return metadataDataSource;
    }

    @Override
    protected PlatformTransactionManager getTransactionManager() {
        return metadataTransactionManager;
    }

    @Override
    protected String getTablePrefix() {
        return "BATCH_";
    }
}
~~~

Đây là **phương án thay thế** `ManualBatchInfrastructure` ở mục 5, không chạy hai phương án cùng lúc. Ứng dụng phải cung cấp bean `batchDataSource` và `batchTransactionManager`. Không thêm `@EnableBatchProcessing` vào lớp kế thừa `DefaultBatchConfiguration` vì hai đường cấu hình có thể xung đột bean.

Từ Spring Boot 4.x/Spring Batch 6.x, hạ tầng Batch và cách chọn repository (in-memory, JDBC...) thay đổi. Đặc biệt, không giả định mẫu cấu hình JDBC của Spring Batch 5.x có thể sao chép nguyên trạng sang phiên bản mới.

## 7. Hệ quả thực tế khi Boot nhường quyền

### 7.1. Schema metadata phải được quản lý rõ ràng

Spring Batch lưu trạng thái ở các bảng như:

~~~text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_STEP_EXECUTION
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION_CONTEXT
~~~

Còn có sequence/bảng sinh ID tùy database. Phải lấy **schema SQL tương ứng với phiên bản Spring Batch và loại database** thay vì tự dựng các bảng theo tên liệt kê.

Sau khi thêm `@EnableBatchProcessing`, chỉ đặt:

~~~yaml
spring:
  batch:
    jdbc:
      initialize-schema: always
~~~

sẽ **không bảo đảm** các bảng được Boot khởi tạo vì cơ chế khởi tạo schema Batch của Boot đã back off. Hãy chạy Flyway/Liquibase hoặc migration riêng trước khi Job truy cập repository, và quản lý quyền DDL, thứ tự deploy, backup/restore.

### 7.2. Cần cơ chế kích hoạt Job riêng

Nếu không còn runner của Boot, Job phải được gọi qua `JobLauncher`, scheduler, endpoint được kiểm soát quyền, CLI hoặc orchestration. Để chủ động chạy một Job lúc startup theo cờ riêng:

~~~java
// ManualJobStartupConfiguration.java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManualJobStartupConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.batch",
        name = "run-on-startup",
        havingValue = "true"
    )
    ApplicationRunner runImport(
            JobLauncher launcher,
            @Qualifier("importPartnerData") Job importJob) {
        return args -> launcher.run(importJob,
                new JobParametersBuilder()
                        .addString("partner", "partner-a")
                        .addString("businessDate", "2026-11-21")
                        .toJobParameters());
    }
}
~~~

~~~yaml
app:
  batch:
    run-on-startup: false
~~~

`businessDate` chỉ là ví dụ. Trong hệ thống thật, tham số phải xuất phát từ yêu cầu nghiệp vụ và được kiểm tra. Spring Batch xác định `JobInstance` theo **tên Job + JobParameters định danh**: khi một instance đã `COMPLETED`, chạy lại cùng tham số có thể bị từ chối. Không gắn timestamp ngẫu nhiên vào mọi retry để “chạy được”, vì điều đó có thể tạo instance mới và xử lý trùng dữ liệu từ đối tác.

### 7.3. Không nhầm transaction của JobRepository với giao dịch toàn bộ hệ thống

Transaction manager cho `JobRepository` kiểm soát metadata Batch; Step còn có transaction manager của mình. Trong luồng đọc file, cập nhật DB rồi publish Kafka, rollback JDBC **không tự thu hồi** thông điệp đã gửi hoặc thao tác HTTP đã thực hiện. Thiết kế cần có idempotency key, checkpoint, retry/backoff có giới hạn, outbox hoặc bù trừ khi cần.

Metadata giúp restart Job và theo dõi Step, nhưng không tự bảo đảm exactly-once qua HTTP, database, cache và broker. Đây là điểm quan trọng trong Spring Boot Integration: phải kiểm soát hợp đồng dữ liệu và ranh giới giao dịch ở từng adapter.

## 8. Chẩn đoán lỗi cấu hình

Chạy Boot với `--debug` để xem **Condition Evaluation Report**; hoặc dùng `/actuator/conditions` nếu đã cấu hình Actuator và giới hạn quyền truy cập thích hợp. Tìm `BatchAutoConfiguration`, rồi kiểm tra:

1. `@ConditionalOnClass`: có đúng phiên bản Batch/JDBC trên classpath?
2. `@ConditionalOnBean`: đã có `DataSource` và `PlatformTransactionManager` phù hợp chưa?
3. `@ConditionalOnMissingBean`: có annotation `@EnableBatchProcessing` hoặc bean `DefaultBatchConfiguration` khiến điều kiện không đạt?
4. Nếu không có `JobLauncherApplicationRunner`, có phải vì toàn bộ auto-configuration back off, vì `spring.batch.job.enabled=false`, hoặc vì một runner riêng đã được khai báo?

Thấy `JobRepository` hay `JobLauncher` trong ApplicationContext **không chứng minh Boot tự cấu hình**: Spring Batch ở chế độ thủ công cũng cung cấp những bean này. Nên kiểm tra nguồn tạo bean, báo cáo điều kiện, schema và hành vi chạy Job thực tế.

| Triệu chứng | Nguyên nhân cần xác minh | Xử lý |
| --- | --- | --- |
| Job không tự chạy sau khi thêm annotation | Boot không còn tạo `JobLauncherApplicationRunner` | Bỏ annotation nếu không cần cấu hình tay, hoặc tạo trigger riêng |
| Lỗi thiếu bảng `BATCH_JOB_INSTANCE` | Schema initializer của Boot không chạy | Áp dụng migration đúng DB và phiên bản |
| Lỗi thiếu `dataSource`/`transactionManager` | Spring Batch 5.x tìm tên bean mặc định | Dùng `dataSourceRef`/`transactionManagerRef` hoặc override getter |
| Bean `jobRepository`/`jobLauncher` bị trùng | Có nhiều đường đăng ký hạ tầng Batch | Chọn một chiến lược; kiểm tra component scan và bean definitions |
| Job xử lý trùng sau retry/restart | JobParameters không phản ánh đơn vị công việc, adapter thiếu idempotency | Chuẩn hóa tham số, xử lý trùng ở adapter và JobInstance |
| Upgrade Boot rồi cấu hình lỗi | API và mô hình repository đã thay đổi | Kiểm tra tài liệu phiên bản trước khi chỉnh cấu hình |

### Kịch bản kiểm chứng theo hành vi

Trên một database thử nghiệm và một Job tối giản, so sánh ba lần chạy:

1. **Chỉ starter và `@Bean Job`:** Boot tự cấu hình khi đủ điều kiện; xác nhận Job runner, bảng metadata và trạng thái thực thi.
2. **Thêm `@EnableBatchProcessing`:** xem điều kiện `BatchAutoConfiguration` đã back off; xác nhận migration tạo schema và runner tự viết kích hoạt đúng một Job.
3. **Bỏ annotation, dùng `spring.batch.job.enabled=false`:** xác nhận hạ tầng Boot vẫn có, nhưng Job không tự khởi chạy.

Với hệ thống thật, tiếp tục kiểm tra thất bại giữa Step, restart Job, giao dịch metadata so với dữ liệu nghiệp vụ, retry sự kiện broker và xác nhận không ghi trùng.

## 9. Quy tắc lựa chọn và câu hỏi tự kiểm tra

| Mục tiêu | Lựa chọn nên cân nhắc |
| --- | --- |
| Muốn chạy Job với cấu hình tiêu chuẩn | Giữ Boot tự cấu hình, không thêm `@EnableBatchProcessing` theo thói quen |
| Không muốn Job chạy khi ứng dụng khởi động | Giữ auto-configuration, dùng `spring.batch.job.enabled=false` |
| Muốn metadata ở DataSource riêng mà vẫn giữ tiện ích Boot | Xem `@BatchDataSource` và điều kiện chọn DataSource theo đúng phiên bản |
| Cần thay hẳn repository/transaction/prefix bằng Java config | Chọn `@EnableBatchProcessing` **hoặc** `DefaultBatchConfiguration` |
| Có luồng tích hợp ngoài DB cần retry và restart | Kết hợp Batch metadata với idempotency, transaction, outbox và giám sát |

**Tự kiểm tra:**

1. **Có cần `@EnableBatchProcessing` sau khi dùng `spring-boot-starter-batch`?** Không, nếu Boot đã đủ điều kiện tự cấu hình.
2. **Chỉ muốn tắt tự chạy Job thì dùng gì?** `spring.batch.job.enabled=false`.
3. **Vì sao `spring.batch.jdbc.initialize-schema=always` không tạo bảng sau khi chuyển cấu hình tay?** Vì phần khởi tạo schema Batch của Boot đã back off.
4. **Kế thừa `DefaultBatchConfiguration` đồng thời thêm `@EnableBatchProcessing` có nên không?** Không, hai cơ chế thay thế nhau.
5. **Có `JobLauncher` trong context nghĩa là auto-configuration vẫn hoạt động?** Không, bean này cũng có thể do cấu hình thủ công tạo.

Quyết định trước tiên cần làm rõ **ai sở hữu việc tạo hạ tầng Batch, khởi tạo metadata và kích hoạt Job**. Nếu ứng dụng tự nhận quyền cấu hình, phải đảm nhận đủ các trách nhiệm đó; nếu chỉ cần thay đổi lịch chạy Job, thường nên giữ cấu hình mặc định của Spring Boot.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Batch Applications](https://docs.spring.io/spring-boot/3.5/how-to/batch.html).
- [Spring Boot 3.5 — BatchAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/batch/BatchAutoConfiguration.html).
- [Spring Batch 5.2 — EnableBatchProcessing API](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/configuration/annotation/EnableBatchProcessing.html).
- [Spring Batch 5.2 — DefaultBatchConfiguration API](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/configuration/support/DefaultBatchConfiguration.html).
- [Spring Boot 4.0 — Spring Batch](https://docs.spring.io/spring-boot/4.0/reference/io/spring-batch.html) (đối chiếu khi nâng cấp).
