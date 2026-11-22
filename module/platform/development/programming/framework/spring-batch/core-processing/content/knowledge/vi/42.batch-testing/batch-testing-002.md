# JobRepositoryTestUtils trong kiểm thử Spring Batch

## 1. JobRepositoryTestUtils giải quyết vấn đề gì?

Khi kiểm thử một ứng dụng Spring Batch, chúng ta thường cần kiểm soát **metadata của các lần chạy job**: đã có `JobInstance` nào, có bao nhiêu `JobExecution`, những step nào được ghi nhận, và dữ liệu của lần chạy trước có ảnh hưởng đến lần chạy tiếp theo hay không. `JobRepositoryTestUtils` là tiện ích thuộc module `spring-batch-test`, được thiết kế để **tạo nhanh và dọn dẹp các bản ghi thực thi batch trong `JobRepository`**.

Lớp này nằm trong package:

```java
org.springframework.batch.test.JobRepositoryTestUtils
```

Hai công việc chính là:

1. **Chuẩn bị dữ liệu kiểm thử:** tạo các `JobExecution` và `StepExecution` mẫu, được lưu thông qua `JobRepository`, để kiểm tra những thành phần đọc hoặc xử lý metadata.
2. **Làm sạch trạng thái giữa các lần test:** xóa các bản ghi batch cũ để những lần chạy cùng tên job/cùng bộ tham số không bị ảnh hưởng bởi lịch sử trước đó.

Đây là tiện ích thao tác với **metadata**, không phải công cụ trực tiếp chạy logic `ItemReader`, `ItemProcessor`, `ItemWriter` hay toàn bộ `Job`. Gọi `createJobExecutions(...)` tạo bản ghi mô phỏng lịch sử thực thi; nó **không gọi các step thực sự**. Muốn xác minh kết quả xử lý dữ liệu từ đầu đến cuối, cần chạy job bằng tiện ích launch tương ứng và kiểm tra đầu ra.

### Mối quan hệ giữa các đối tượng batch

```text
Job (định nghĩa công việc)
  |
  +-- JobInstance (jobName + các JobParameters dùng để định danh)
        |
        +-- JobExecution #1 (một lần thử chạy)
        |     +-- StepExecution: readStep
        |     +-- StepExecution: writeStep
        |
        +-- JobExecution #2 (một lần thử chạy lại/restart)
              +-- StepExecution: readStep
              +-- StepExecution: writeStep
```

- `JobInstance` đại diện cho một công việc logic được xác định bởi tên job và **identifying job parameters**.
- `JobExecution` đại diện cho một lần thực thi của instance đó; một instance có thể có nhiều execution khi restart.
- `StepExecution` lưu trạng thái, bộ đếm và thông tin của một lần thực thi step.
- `JobRepository` quản lý việc lưu/truy xuất metadata; `JobExplorer` cung cấp các API để đọc, tra cứu metadata.

Với repository JDBC thông thường, metadata nằm trong các bảng như `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_JOB_EXECUTION_CONTEXT`, `BATCH_STEP_EXECUTION` và `BATCH_STEP_EXECUTION_CONTEXT`. Quan hệ khóa ngoại giữa những bảng này là lý do việc dọn dẹp metadata nên dùng một tiện ích hiểu cấu trúc Spring Batch, thay vì tùy tiện xóa một bảng đơn lẻ.

## 2. Các API quan trọng

| Phương thức | Chức năng | Trường hợp sử dụng |
| --- | --- | --- |
| `createJobExecutions(int count)` | Tạo `count` execution mẫu; mỗi execution có một step execution | Cần nhanh một số bản ghi metadata, không quan tâm tên job/step cụ thể |
| `createJobExecutions(String jobName, String[] stepNames, int count)` | Tạo `count` execution mẫu với tên job và danh sách tên step chỉ định | Kiểm thử truy vấn lịch sử chạy một job hoặc step cụ thể |
| `removeJobExecution(JobExecution execution)` | Xóa một execution được chỉ định cùng các step execution liên quan | Dọn riêng một lần chạy; cần cân nhắc `JobInstance` còn lại |
| `removeJobExecutions(Collection<JobExecution> executions)` | Xóa tập execution được chỉ định cùng metadata liên quan | Dọn chính xác dữ liệu do một test tạo ra |
| `removeJobExecutions()` | Xóa **toàn bộ** metadata job/step execution mà tiện ích quản lý trong repository đang dùng | Reset repository dành riêng cho môi trường test |
| `setJobParametersIncrementer(JobParametersIncrementer incrementer)` | Đặt cơ chế tăng tham số khi tạo nhiều execution mẫu | Muốn điều khiển cách phát sinh bộ tham số dùng để định danh |
| `setJobRepository(JobRepository repository)` | Gán repository được tiện ích sử dụng | Cấu hình thủ công khi không dùng bean do test context cung cấp |

**Phạm vi xóa cần được đọc kỹ:** `removeJobExecutions()` là thao tác rộng, không có điều kiện lọc theo job name trong chữ ký phương thức. Trên một repository dùng chung, nó có thể xóa metadata của các test hoặc job khác. `removeJobExecution(...)` theo tài liệu API tập trung xóa một `JobExecution` và `StepExecution` liên quan; không nên giả định phương thức đơn lẻ này luôn xóa cả `JobInstance`. Khi muốn dọn toàn bộ các đối tượng được tạo cho một bài test, `removeJobExecutions(Collection)` thường phù hợp hơn.

Các phương thức tạo execution có thể phát sinh `JobExecutionAlreadyRunningException`, `JobRestartException` hoặc `JobInstanceAlreadyCompleteException` nếu repository nhận thấy việc tạo execution không hợp lệ theo trạng thái và bộ tham số hiện có. Đây cũng là dấu hiệu cần kiểm tra cách cô lập dữ liệu test.

## 3. Thêm dependency và khởi tạo tiện ích

### Dependency

Với dự án Spring Boot dùng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2' // Chỉ cần khi dùng H2 cho test
}
```

Trong Maven, dependency trực tiếp quan trọng là:

```xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án sử dụng Spring Boot BOM hoặc một BOM Spring Batch tương ứng, để BOM quản lý phiên bản, tránh gán các phiên bản Spring Batch không tương thích với nhau.

### Đưa JobRepositoryTestUtils vào Spring TestContext

Cách thông dụng nhất là gắn `@SpringBatchTest` vào lớp kiểm thử và nạp configuration chứa các bean Spring Batch:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class BatchMetadataTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    // Các @Test đặt tại đây
}
```

`BatchTestConfiguration` trong ví dụ là lớp cấu hình của dự án; nó cần cung cấp hạ tầng batch, đặc biệt là `JobRepository` và các bean hạ tầng cần thiết. Với kiểm thử dựa trên JDBC, DataSource test phải được kết nối với một database đã khởi tạo bảng metadata Spring Batch. Ví dụ dùng `@SpringBootTest` có thể thay thế `@SpringJUnitConfig` khi cần nạp toàn bộ ứng dụng.

`@SpringBatchTest` đăng ký bean `jobRepositoryTestUtils` cho test context nên thông thường chỉ cần `@Autowired`. Nếu muốn dùng độc lập với annotation, có thể khởi tạo tiện ích bằng constructor nhận `JobRepository`:

```java
JobRepositoryTestUtils utils = new JobRepositoryTestUtils(jobRepository);
```

Constructor nhận `JobRepository` tương thích với dòng Spring Batch 5.2 và 6.x. Không nên mặc định dùng constructor không tham số khi viết code cần chạy trên Spring Batch 6.x.

### Phân biệt hai dòng phiên bản

| Nội dung | Spring Batch 5.x | Spring Batch 6.x |
| --- | --- | --- |
| Tiện ích thao tác metadata | `JobRepositoryTestUtils` | `JobRepositoryTestUtils` |
| Tiện ích thường dùng để chạy job trong test | `JobLauncherTestUtils` | `JobOperatorTestUtils` |
| Import `JobExecution` | `org.springframework.batch.core.JobExecution` | `org.springframework.batch.core.job.JobExecution` |
| Nền tảng test | JUnit Jupiter được hỗ trợ | Ưu tiên JUnit Jupiter; JUnit 4 không còn được hỗ trợ theo tài liệu 6.0 |

Vì thế, khi sao chép ví dụ từ dự án cũ, kiểm tra **version và package import** trước khi kết luận rằng `JobRepositoryTestUtils` có lỗi.

## 4. Ví dụ: tạo metadata rồi xác minh bằng JobExplorer

Giả sử muốn kiểm thử một màn hình hoặc dịch vụ hiển thị lịch sử xử lý hóa đơn. Chưa cần chạy job thực tế, ta chỉ cần có hai execution của job `invoiceImportJob`, mỗi execution ghi nhận hai step `readInvoices` và `writeInvoices`.

Ví dụ JUnit 5 bên dưới dùng `var` để phần thân test có thể áp dụng cho các version Spring Batch có package `JobExecution` khác nhau:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.repository.explore.JobExplorer;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class JobRepositoryMetadataTest {

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void taoLichSuThucThiDeKiemThuTruyVan() throws Exception {
        var created = repositoryTestUtils.createJobExecutions(
                "invoiceImportJob",
                new String[] {"readInvoices", "writeInvoices"},
                2
        );

        try {
            assertEquals(2, created.size());

            for (var execution : created) {
                assertNotNull(execution.getId());
                assertEquals(
                        "invoiceImportJob",
                        execution.getJobInstance().getJobName()
                );

                var persisted = jobExplorer.getJobExecution(execution.getId());
                assertNotNull(persisted);
                assertEquals(2, persisted.getStepExecutions().size());
            }
        } finally {
            repositoryTestUtils.removeJobExecutions(created);
        }
    }
}
```

**Trình tự diễn ra:**

1. `createJobExecutions(...)` yêu cầu repository tạo hai execution với tên job đã chỉ định và các step execution tương ứng.
2. Các đối tượng trả về có ID do repository gán, qua đó có thể kiểm tra rằng đây là metadata đã được tạo trong hạ tầng repository.
3. `JobExplorer.getJobExecution(id)` đọc lại bản ghi từ repository; đây là phép kiểm tra hữu ích cho thành phần truy vấn lịch sử.
4. Khối `finally` dọn các execution do chính test tạo ra, kể cả khi phần assert phát sinh lỗi.

Ví dụ giả định `BatchTestConfiguration` cấu hình một `JobRepository` thực sự có khả năng lưu và đọc dữ liệu, cùng `JobExplorer` trỏ tới **chính cùng nguồn metadata**. Nếu dùng repository không lưu lịch sử hoặc dùng hai DataSource khác nhau, kiểm tra đọc lại sẽ không có ý nghĩa như mong đợi.

Lưu ý rằng tên `readInvoices` và `writeInvoices` ở đây chỉ được ghi thành **tên các StepExecution mẫu**. Hai step không chạy; không có bản ghi hóa đơn nào được đọc, biến đổi hay ghi ra output chỉ vì gọi `createJobExecutions(...)`.

## 5. Ví dụ: dọn metadata trước một integration test chạy job thực tế

Giả sử `invoiceImportJob` đã chạy thành công với identifying parameters là `businessDate=2026-01-15`. Nếu test khác chạy lại **cùng job, cùng bộ tham số**, Spring Batch có thể xem đây là một `JobInstance` đã hoàn tất và không khởi chạy như một instance mới. Đây là hành vi bảo vệ tính nhất quán của framework, nhưng nó làm test phụ thuộc vào lịch sử còn sót lại.

Trong database **chỉ dành cho một test class hoặc một test suite có thứ tự kiểm soát**, có thể dọn metadata trước mỗi lần chạy:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class InvoiceJobIntegrationTest {

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @BeforeEach
    void clearBatchHistory() {
        repositoryTestUtils.removeJobExecutions();
    }

    // @Test chạy job thực sự rồi kiểm tra BatchStatus/ExitStatus/output
}
```

Nếu dùng Spring Boot và muốn ngăn job tự chạy ngay khi test context khởi động, có thể cấu hình riêng môi trường test:

```properties
spring.batch.job.enabled=false
spring.batch.jdbc.initialize-schema=always
```

Thuộc tính khởi tạo schema chỉ nên bật khi phù hợp với cách dự án quản lý database test. Ví dụ trên thường thích hợp với H2 hoặc database test tạm; nếu schema được tạo bằng Flyway/Liquibase thì dùng quy trình migration hiện có để tránh tạo hai lần.

Đối với **Spring Batch 6.x**, test chạy thật thường dùng `JobOperatorTestUtils.startJob(...)`. Ở **Spring Batch 5.x**, tài liệu và dự án cũ thường dùng `JobLauncherTestUtils.launchJob(...)`. Dù dùng cách khởi chạy nào, `JobRepositoryTestUtils` vẫn có vai trò quản lý metadata đầu vào/đầu ra của test.

**Quan trọng:** xóa metadata batch không xóa dữ liệu nghiệp vụ mà job đã ghi ra, ví dụ bảng `INVOICE`, file CSV, hàng đợi hoặc đối tượng lưu trữ. Một integration test đầy đủ phải tự chuẩn bị và dọn những tài nguyên đó. Chỉ xóa `BATCH_JOB_EXECUTION` không thể làm test độc lập nếu output cũ vẫn còn.

## 6. Chọn mức độ dọn dẹp phù hợp

### Xóa đúng những execution do test tạo ra

Khi một test chỉ tạo metadata bằng `createJobExecutions(...)`, lưu danh sách trả về và truyền lại cho `removeJobExecutions(Collection)`:

```java
var executions = repositoryTestUtils.createJobExecutions(
        "testOnlyJob",
        new String[] {"testStep"},
        3
);

try {
    // Thực hiện các truy vấn/assert trên ba execution.
} finally {
    repositoryTestUtils.removeJobExecutions(executions);
}
```

Đây là cách thể hiện rõ **ownership của dữ liệu test**. Nó thích hợp khi nhiều job cùng có metadata trong repository và ta chỉ cần dọn dữ liệu của kịch bản đang xét. Tuy nhiên, với các `JobInstance` có nhiều execution liên quan nhau, phải hiểu trạng thái các bản ghi còn lại trước khi xóa một phần lịch sử.

### Xóa một JobExecution

```java
repositoryTestUtils.removeJobExecution(oneExecution);
```

Phương thức này hữu ích khi cần dọn một lần thực thi cụ thể. API mô tả việc xóa `JobExecution` và các `StepExecution` liên quan. Không dựa vào nó như một lệnh reset toàn bộ `JobInstance`; nếu yêu cầu bài test là trạng thái repository hoàn toàn sạch, dùng một chiến lược dọn phù hợp với toàn bộ vòng đời metadata.

### Reset toàn bộ repository

```java
repositoryTestUtils.removeJobExecutions();
```

Chỉ chọn khi chắc chắn repository là của test và không dùng chung với công việc khác. Khi chạy test song song trên cùng database, test A có thể xóa metadata mà test B vừa tạo. Để tránh tình huống này, ưu tiên **database/schema độc lập cho từng test suite**, hoặc tách hẳn các integration test dùng thao tác reset.

## 7. JobParameters, tính duy nhất và mô phỏng restart

Spring Batch không phân biệt hai `JobInstance` chỉ bằng thời điểm gọi API. Điều quyết định identity là **tên job cộng với các identifying parameters**. Chẳng hạn:

| Lần gọi | Job name | Identifying parameters | Ý nghĩa |
| --- | --- | --- | --- |
| A | `invoiceImportJob` | `businessDate=2026-01-15` | JobInstance thứ nhất |
| B | `invoiceImportJob` | `businessDate=2026-01-16` | JobInstance khác |
| C | `invoiceImportJob` | `businessDate=2026-01-15` | Cùng JobInstance với A; là chạy lại/restart nếu trạng thái cho phép |

Khi tạo nhiều metadata mẫu, `JobRepositoryTestUtils` có cơ chế sử dụng `JobParametersIncrementer` để tạo các bộ tham số kế tiếp. Có thể thay cơ chế này thông qua `setJobParametersIncrementer(...)` khi kịch bản test đòi hỏi một quy tắc cụ thể. Nếu incrementer do bạn cung cấp luôn trả lại cùng identifying parameters, các execution mẫu có thể va chạm với cùng một instance hoặc gặp lỗi do trạng thái chạy/hoàn tất trước đó.

**Phân biệt hai mục tiêu kiểm thử:**

- **Kiểm thử truy vấn metadata:** tạo execution mẫu với `createJobExecutions(...)` là nhanh và đủ khi chỉ cần dữ liệu lịch sử.
- **Kiểm thử restart thực sự:** cần chạy job, làm nó dừng/thất bại ở trạng thái có kiểm soát, lưu `ExecutionContext` cần thiết rồi khởi động lại theo đúng contract của Spring Batch. Chỉ tạo vài execution mẫu không chứng minh được logic checkpoint, commit/rollback hoặc khả năng restart của reader/writer.

Xóa metadata của một run thất bại cũng có thể làm lần chạy tiếp theo bị coi là **job mới**, thay vì một lần restart; khi đó trạng thái `ExecutionContext` dùng để khôi phục tiến độ đã biến mất. Vì vậy không dùng `removeJobExecutions()` để “sửa” test restart đang thất bại: cần xác định trước đang muốn kiểm thử **chạy mới** hay **chạy tiếp từ checkpoint**.

## 8. Vòng đời transaction và mức độ cô lập

`JobRepositoryTestUtils` thực hiện thao tác thay đổi metadata thực sự; kết quả chịu ảnh hưởng của transaction manager, DataSource và phạm vi transaction của test.

Một số nguyên tắc thực tế:

1. **Cùng DataSource/schema:** `JobRepository`, `JobExplorer` và tiện ích test phải thao tác trên cùng kho metadata khi bạn muốn tạo rồi đọc lại dữ liệu.
2. **Không giả định rollback luôn dọn sạch:** với test có `@Transactional`, việc xóa/tạo có thể tham gia transaction hiện tại hoặc có propagation riêng từ cấu hình repository. Hãy chọn thời điểm setup/cleanup phù hợp và xác minh transaction boundary của ứng dụng.
3. **Không reset trong khi job khác đang chạy:** xóa metadata của job vẫn hoạt động có thể làm repository không còn phản ánh đúng các execution và ảnh hưởng logic điều phối.
4. **Không dùng database production/staging chia sẻ:** tiện ích này dành cho test và có các phương thức xóa rất rộng.
5. **Không nhầm trạng thái metadata với output:** trạng thái `COMPLETED` ở một execution không tự động xác nhận bản ghi nghiệp vụ, số dòng đã ghi hoặc chất lượng dữ liệu đầu ra.

Khi dùng database test được tạo mới cho mỗi lần chạy, cách đơn giản nhất thường là: tạo schema → nạp fixture → chạy test → hủy database. Khi database được tái sử dụng, cần một chính sách cleanup rõ ràng và tránh test chạy song song vô tình xóa dữ liệu của nhau.

## 9. So sánh với các tiện ích kiểm thử khác

| Công cụ | Trách nhiệm chính | Khi nào dùng |
| --- | --- | --- |
| `JobRepositoryTestUtils` | Tạo/xóa metadata `JobExecution` và `StepExecution` | Chuẩn bị lịch sử giả lập, dọn repository |
| `JobExplorer` | Đọc trạng thái và lịch sử repository | Assert kết quả đã được lưu, truy vấn execution |
| `JobOperatorTestUtils` (6.x) | Khởi chạy job/step trong test | Kiểm thử chạy job thật ở Spring Batch 6 |
| `JobLauncherTestUtils` (5.x) | Khởi chạy job/step trong test | Kiểm thử chạy job thật ở các dự án Spring Batch 5 |
| `StepScopeTestUtils`, `@SpringBatchTest` | Hỗ trợ ngữ cảnh `StepScope`/`JobScope` trong test | Test bean có giá trị phụ thuộc `JobParameters` hoặc `ExecutionContext` |
| Mockito hoặc stub reader/processor/writer | Cô lập đơn vị xử lý | Test logic nghiệp vụ của một thành phần |

Ví dụ, nếu yêu cầu là “khi invoice input không hợp lệ thì processor trả về lỗi”, dùng unit test cho processor. Nếu yêu cầu là “job chạy đúng 100 invoice, ghi 98, skip 2”, chạy job/step và kiểm tra các bộ đếm cùng dữ liệu output. Nếu yêu cầu là “trang quản trị đọc được ba lần chạy của `invoiceImportJob`”, `JobRepositoryTestUtils` kết hợp `JobExplorer` là một lựa chọn tự nhiên.

## 10. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` với `JobRepositoryTestUtils` | Chưa thêm `spring-batch-test` hoặc chưa đăng ký `@SpringBatchTest`/bean tiện ích | Thêm dependency test; nạp đúng Spring test context |
| Không tạo được `JobRepositoryTestUtils` | Test context thiếu `JobRepository` hoặc cấu hình hạ tầng không đầy đủ | Kiểm tra DataSource, transaction manager, repository và test configuration |
| Lỗi `BATCH_JOB_INSTANCE`/`BATCH_JOB_EXECUTION` không tồn tại | Schema metadata chưa được khởi tạo hoặc trỏ nhầm database | Khởi tạo schema theo phiên bản Spring Batch và đối chiếu connection |
| `JobInstanceAlreadyCompleteException` khi chạy lại | Cùng tên job và identifying parameters đã hoàn tất | Dùng parameters mới cho lần chạy mới; chỉ reset metadata trong test có môi trường biệt lập |
| `JobExecutionAlreadyRunningException` | Repository ghi nhận execution của cùng instance đang chạy | Kiểm tra execution cũ và transaction; không tùy tiện xóa khi job thật vẫn chạy |
| `JobExplorer` không tìm thấy execution vừa tạo | Explorer dùng nguồn dữ liệu khác, transaction chưa visible hoặc repository không lưu lịch sử | Đối chiếu DataSource và thời điểm commit |
| Test đạt khi chạy riêng nhưng thất bại khi chạy cả suite | Metadata/output còn sót hoặc test song song cùng dùng repository | Cô lập database, dùng parameters duy nhất, cleanup đúng ownership |
| Đã gọi `removeJobExecutions()` nhưng output vẫn còn | Tiện ích chỉ dọn metadata batch | Dọn bảng/file/queue nghiệp vụ bằng fixture riêng |
| Import `JobExecution` báo lỗi sau nâng version | Spring Batch 6 thay đổi cấu trúc package | Đổi import phù hợp version, đồng bộ các dependency |

## 11. Bài tập áp dụng

Giả sử bạn xây dựng API `GET /batch/history?jobName=invoiceImportJob` trả về số lần chạy và tên các step đã được ghi nhận:

1. Cấu hình một database test có schema Spring Batch và một `JobExplorer` cùng trỏ tới repository đó.
2. Dùng `createJobExecutions("invoiceImportJob", new String[]{"readInvoices", "writeInvoices"}, 3)` để tạo fixture.
3. Gọi dịch vụ/API truy vấn lịch sử của ứng dụng; kiểm tra rằng job có ba execution và mỗi execution có hai step được ghi nhận.
4. Trong `finally` hoặc hook cleanup phù hợp, gọi `removeJobExecutions(created)`.
5. Bổ sung một test chạy job thực tế bằng tiện ích launch theo version đang sử dụng và xác minh output để thấy rõ sự khác biệt giữa **metadata fixture** và **job execution thật**.

## 12. Ghi nhớ

`JobRepositoryTestUtils` là công cụ quản lý **dữ liệu lịch sử thực thi dành cho test**. Nắm chắc ba ranh giới giúp sử dụng đúng: `createJobExecutions` tạo metadata chứ không chạy step; `removeJobExecutions` xóa metadata chứ không xóa dữ liệu nghiệp vụ; và thao tác cleanup chỉ an toàn khi hiểu rõ repository/schema nào đang được dùng. Kết hợp tiện ích này với `@SpringBatchTest`, `JobExplorer`, một database test biệt lập và các công cụ launch job phù hợp version sẽ giúp viết integration test có thể lặp lại, dễ giải thích và ít phụ thuộc vào thứ tự chạy.

### Tài liệu tham khảo chính thức

- [Spring Batch 6 — JobRepositoryTestUtils API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobRepositoryTestUtils.html)
- [Spring Batch 6 — @SpringBatchTest API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/context/SpringBatchTest.html)
- [Spring Batch — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch 5.2 — JobRepositoryTestUtils API](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobRepositoryTestUtils.html)
