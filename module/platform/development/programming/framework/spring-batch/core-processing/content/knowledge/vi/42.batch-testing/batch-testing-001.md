# JobLauncherTestUtils

## Vai trò của JobLauncherTestUtils

Trong Spring Batch, một job thường được tạo từ nhiều step, có thể đọc dữ liệu, xử lý từng item, ghi kết quả, kiểm tra điều kiện và điều hướng sang các nhánh khác nhau. Khi kiểm thử, việc gọi trực tiếp một method trong reader, processor hoặc writer chỉ xác nhận được một phần nhỏ của xử lý. Nó không chứng minh rằng Spring Batch có thể khởi chạy job, tạo các execution, quản lý transaction, lưu metadata hay chuyển trạng thái đúng như dự kiến.

JobLauncherTestUtils là tiện ích thuộc module spring-batch-test, dùng để khởi chạy job hoặc một step trong test. Công cụ này kết nối với JobLauncher, JobRepository và job được cấu hình trong Spring ApplicationContext. Vì vậy, test có thể kiểm tra hành vi của batch job thông qua cơ chế thực thi thật của Spring Batch mà không cần tự viết code gọi từng thành phần.

Hai thao tác chính là:

- **launchJob(...):** khởi chạy toàn bộ job. Dùng khi cần kiểm tra luồng từ đầu đến cuối, thứ tự step, điều kiện chuyển tiếp và kết quả chung.
- **launchStep(...):** khởi chạy riêng một step được chỉ định trong môi trường test. Dùng khi muốn tập trung kiểm tra xử lý của step mà không cần chạy toàn bộ luồng job.

Kết quả trả về là một JobExecution. Từ đối tượng này, test có thể đọc trạng thái job, exit status, các StepExecution, bộ đếm đọc/ghi/bỏ qua và các exception được ghi nhận trong quá trình thực thi.

## Thêm dependency kiểm thử

JobLauncherTestUtils nằm trong artifact spring-batch-test, không nằm trong spring-batch-core. Dependency này chỉ cần có trong classpath kiểm thử.

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.batch:spring-batch-test'
}
~~~

Nếu dự án dùng Spring Boot dependency management hoặc Spring Batch BOM, hãy để BOM quản lý version để spring-batch-test tương thích với version của spring-batch-core. Nếu dự án tự quản lý version, cần khai báo các artifact Spring Batch cùng một dòng version.

## Đăng ký tiện ích trong test context

Cách thông dụng là kết hợp @SpringBatchTest với @SpringBootTest:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest
class ImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importJobCompletes() throws Exception {
        // Test được triển khai ở các phần tiếp theo.
    }
}
~~~

@SpringBootTest nạp ApplicationContext của ứng dụng, bao gồm cấu hình job, step, JobRepository, JobLauncher, datasource và các bean mà job cần. @SpringBatchTest bổ sung các tiện ích và test listener dành cho Spring Batch, trong đó có JobLauncherTestUtils, JobRepositoryTestUtils, StepScopeTestExecutionListener và JobScopeTestExecutionListener.

Nếu không dùng Spring Boot, có thể dùng cấu hình test của Spring, chẳng hạn @SpringJUnitConfig, miễn là context cung cấp các bean Spring Batch cần thiết và tiện ích test được đăng ký.

Một ứng dụng Spring Boot có thể tự động chạy job khi khởi động thông qua JobLauncherApplicationRunner. Nếu việc tự động chạy này làm job thực thi ngay khi test context được tạo, hãy tắt cơ chế tự khởi chạy trong cấu hình test, ví dụ:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportJobTest {
    // ...
}
~~~

Thuộc tính này áp dụng cho cấu hình Spring Boot Batch; với ứng dụng không dùng Boot, hãy kiểm tra cách khởi chạy job được cấu hình trong test context.

## Khởi chạy toàn bộ job bằng launchJob

Khi muốn xác nhận job hoạt động từ đầu đến cuối, gọi launchJob(). Phương thức này khởi chạy job được gắn với JobLauncherTestUtils và trả về JobExecution.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class ImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importJobCompletes() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(
                ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
        assertTrue(execution.getAllFailureExceptions().isEmpty());
    }
}
~~~

Trong ví dụ, inputFile đại diện cho tham số đầu vào mà job cần. Tên và kiểu tham số phải khớp với cách job đọc JobParameters. testRunId tạo một giá trị nhận diện riêng cho lần chạy test, giúp test độc lập không vô tình dùng lại cùng một job instance.

Nếu job không yêu cầu tham số bắt buộc, có thể gọi trực tiếp:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob();
~~~

Lời gọi không truyền tham số sử dụng bộ JobParameters duy nhất do tiện ích tạo ra. Đây là cách thuận tiện cho một lần chạy độc lập. Khi cần kiểm soát dữ liệu đầu vào, kiểm thử restart hoặc xác minh hành vi với một bộ tham số cụ thể, hãy tạo JobParameters và truyền vào launchJob(parameters).

### Đọc kết quả của JobExecution

JobExecution mô tả một lần thực thi của job. Một JobInstance có thể có nhiều JobExecution nếu job được chạy lại theo cơ chế restart. Một số thông tin thường được kiểm tra:

| Thuộc tính | Ý nghĩa khi kiểm thử |
|---|---|
| getStatus() | Trạng thái thực thi như COMPLETED, FAILED, STOPPED hoặc STARTED. |
| getExitStatus() | Mã kết thúc và mô tả kết quả do job hoặc listener thiết lập. |
| getStepExecutions() | Các step execution thuộc lần chạy job. |
| getAllFailureExceptions() | Các exception được ghi nhận trong quá trình thực thi. |
| getJobParameters() | Bộ tham số đã dùng để khởi chạy job. |
| getExecutionContext() | Execution context ở cấp job. |

BatchStatus và ExitStatus có mục đích khác nhau. BatchStatus biểu diễn trạng thái vòng đời của execution. ExitStatus biểu diễn mã kết thúc và có thể được tùy chỉnh để phục vụ điều hướng hoặc quy ước nghiệp vụ. Với job hoàn tất bình thường, thường kiểm tra cả hai là COMPLETED.

Một job kết thúc với FAILED thường vẫn trả về JobExecution có trạng thái thất bại; lỗi được phản ánh trong execution và danh sách failure exception. Những lỗi xảy ra trước khi job thực sự chạy, chẳng hạn tham số không hợp lệ hoặc job instance đang chạy, có thể được ném ra từ lời gọi khởi chạy. Test nên phân biệt lỗi nghiệp vụ trong lúc chạy với lỗi thiết lập hoặc khởi chạy.

## Khởi chạy một step bằng launchStep

Khi chỉ cần kiểm tra một step, dùng launchStep:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class NormalizeStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void normalizeStepCompletes() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", "normalize-step-test")
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchStep("normalizeStep", parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution stepExecution = execution.getStepExecutions()
                .stream()
                .filter(step -> "normalizeStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(3, stepExecution.getReadCount());
        assertEquals(3, stepExecution.getWriteCount());
    }
}
~~~

Tên normalizeStep phải trùng với tên step được khai báo trong Spring Batch context. Trong ví dụ, test giả định file fixture có ba record hợp lệ và step ghi cả ba record; số lượng thực tế cần thay theo dữ liệu và quy tắc xử lý của dự án.

launchStep chạy step được chỉ định thông qua cơ chế test của Spring Batch, tạo execution cần thiết để step có thể hoạt động. Nó hữu ích khi step có reader, processor, writer, listener hoặc bean @StepScope cần được khởi tạo trong đúng ngữ cảnh batch.

Tuy nhiên, test bằng launchStep không chứng minh toàn bộ job flow hoạt động đúng. Các step đứng trước hoặc sau step đang kiểm thử, điều kiện chuyển tiếp, quyết định của decider và cấu hình restart của toàn job không được xác nhận chỉ bằng test này. Nếu step phụ thuộc dữ liệu do step trước ghi vào ExecutionContext, hãy cung cấp context phù hợp theo API của version đang dùng hoặc kiểm thử toàn bộ job bằng launchJob.

## Chọn launchJob hay launchStep

| Nhu cầu kiểm thử | Cách khởi chạy phù hợp | Điều cần xác nhận |
|---|---|---|
| Kiểm tra luồng import từ đầu đến cuối | launchJob(...) | Tất cả step cần thiết chạy đúng thứ tự và job kết thúc đúng trạng thái. |
| Kiểm tra reader, processor và writer của một step | launchStep(...) | Dữ liệu đọc, xử lý, ghi và các bộ đếm của step. |
| Kiểm tra điều kiện chuyển step hoặc decider | launchJob(...) | Nhánh thực thi được chọn dựa trên trạng thái hoặc dữ liệu. |
| Kiểm tra xử lý skip/retry trong một step | launchStep(...) hoặc launchJob(...) | Bộ đếm skip/retry, dữ liệu đầu ra và trạng thái cuối. |
| Kiểm tra restart sau một lần chạy thất bại | launchJob(parameters) với cùng tham số nhận diện | Execution mới thuộc cùng JobInstance và tiếp tục theo chính sách restart. |

Có thể kết hợp hai loại test: test step để khoanh vùng lỗi xử lý dữ liệu và test job để xác nhận tích hợp các step cùng luồng điều khiển.

## JobParameters và tính duy nhất của JobInstance

Spring Batch xác định JobInstance dựa trên tên job và các tham số được đánh dấu là identifying. Mỗi lần thử chạy một job instance tạo ra một JobExecution. Vì vậy, hai lần gọi job với cùng tên job và cùng các identifying parameter có thể được xem là hai lần chạy của cùng một instance.

JobParametersBuilder mặc định tạo identifying parameter khi gọi các phương thức thêm tham số thông thường. Có thể chỉ rõ một tham số không tham gia nhận diện bằng overload có cờ boolean:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "src/test/resources/orders.csv", true)
        .addString("traceId", "test-trace-01", false)
        .toJobParameters();
~~~

Trong ví dụ, inputFile tham gia xác định job instance, còn traceId chỉ là thông tin bổ sung. Hãy quyết định identifying dựa trên ý nghĩa của dữ liệu nghiệp vụ. Nếu thay đổi file đầu vào tạo thành một lần xử lý batch khác, file có thể là identifying parameter. Nếu chỉ thay đổi mã trace mà dữ liệu xử lý không đổi, mã trace thường không nên làm thay đổi danh tính job instance.

Các trường hợp thường gặp:

- **Chạy độc lập giữa các test:** thêm một identifying parameter riêng, chẳng hạn UUID, để tránh trùng instance trong repository dùng chung.
- **Kiểm thử restart:** truyền lại đúng cùng identifying parameters cho lần chạy tiếp theo. Nếu thay tham số nhận diện, Spring Batch tạo một JobInstance khác và test không còn kiểm tra restart của instance ban đầu.
- **Chạy lại một job đã hoàn tất:** cùng identifying parameters thường dẫn đến JobInstanceAlreadyCompleteException nếu job không được phép chạy lại theo cấu hình hiện tại.
- **Chạy đồng thời:** không dùng chung identifying parameters cho hai lần chạy độc lập nếu mục tiêu của test là tạo hai job instance riêng.

Không nên thêm tham số ngẫu nhiên vào mọi test một cách máy móc. Với test restart hoặc test quy tắc ngăn chạy trùng, việc tái sử dụng cùng bộ tham số chính là một phần của tình huống cần kiểm tra.

## Kiểm tra StepExecution và bộ đếm

Mỗi step chạy trong một job có StepExecution riêng. Có thể lấy step execution từ JobExecution để kiểm tra chi tiết:

~~~java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> "importStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
assertEquals(10, stepExecution.getReadCount());
assertEquals(8, stepExecution.getWriteCount());
assertEquals(2, stepExecution.getFilterCount());
~~~

Các bộ đếm phổ biến:

| Bộ đếm | Diễn giải |
|---|---|
| readCount | Số item được đọc thành công. |
| writeCount | Số item được ghi thành công. |
| filterCount | Số item bị processor lọc và không chuyển sang writer. |
| readSkipCount | Số lỗi đọc được bỏ qua theo cấu hình skip. |
| processSkipCount | Số lỗi xử lý được bỏ qua. |
| writeSkipCount | Số lỗi ghi được bỏ qua. |
| commitCount | Số lần commit chunk. |
| rollbackCount | Số lần rollback được ghi nhận. |

Không phải mọi job đều cần assert tất cả các bộ đếm. Chọn các giá trị phản ánh hợp đồng của step. Ví dụ, với một file có 10 record, trong đó 2 record bị filter, có thể kiểm tra readCount bằng 10, filterCount bằng 2 và writeCount bằng 8. Nếu dữ liệu đầu ra mới là kết quả nghiệp vụ quan trọng, hãy đọc file hoặc truy vấn database để xác nhận nội dung thực tế thay vì chỉ dựa vào số đếm.

## Kiểm thử job và step có scope

Spring Batch thường dùng @StepScope hoặc @JobScope cho bean cần truy cập tham số job, step execution hoặc execution context trong lúc chạy. Những bean này không thể luôn được khởi tạo đúng nếu test gọi trực tiếp method bên ngoài ngữ cảnh batch.

Khi chạy bằng JobLauncherTestUtils, Spring Batch tạo ngữ cảnh thực thi cần thiết cho job hoặc step. @SpringBatchTest cũng đăng ký StepScopeTestExecutionListener và JobScopeTestExecutionListener, hỗ trợ các test cần ngữ cảnh scope. Điều này giúp kiểm thử các thành phần phụ thuộc @Value("#{jobParameters['inputFile']}") hoặc dữ liệu trong execution context.

Ví dụ một reader nhận đường dẫn từ job parameter:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "amount")
            .targetType(Order.class)
            .build();
}
~~~

Test job cần truyền tham số inputFile tương ứng. Nếu tham số thiếu hoặc tên key không khớp, bean có thể không tạo được hoặc reader không đọc được tài nguyên. Với test một step, bảo đảm step được chạy trong batch scope và cung cấp các tham số/context mà step yêu cầu.

## Quản lý dữ liệu test và metadata

JobRepository lưu metadata về job instance, job execution và step execution. Vì vậy, kết quả một test có thể ảnh hưởng đến test khác nếu chúng dùng chung database và cùng identifying parameters.

Một số cách giữ test độc lập:

1. Dùng database dành riêng cho test hoặc database in-memory khi phù hợp.
2. Dùng fixture đầu vào ổn định và tạo đường dẫn đầu ra riêng cho mỗi lần chạy.
3. Dùng identifying parameter riêng cho các lần chạy độc lập.
4. Kiểm tra và dọn metadata batch sau test nếu test suite cần repository sạch.

@SpringBatchTest cung cấp thêm JobRepositoryTestUtils. Có thể dùng removeJobExecutions() để xóa các job execution khỏi repository trong môi trường test:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class ImportJobTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @AfterEach
    void cleanBatchMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }
}
~~~

Phương thức này tác động đến các execution trong repository mà tiện ích đang sử dụng. Chỉ dùng cách dọn toàn bộ metadata khi repository được cô lập cho test hoặc khi test suite kiểm soát rõ phạm vi dữ liệu. Không dùng nó trên repository dùng chung với dữ liệu batch cần giữ lại.

Ngoài ra, không nên mặc định rằng @Transactional trên method test sẽ hoàn tác toàn bộ dữ liệu mà job ghi. Chunk-oriented step có transaction và commit riêng; job có thể hoàn tất commit trước khi method test kết thúc. Hãy quản lý dữ liệu đầu vào/đầu ra và metadata theo cấu hình transaction thực tế của job.

## JobLauncher đồng bộ và bất đồng bộ

Với JobLauncher đồng bộ, lời gọi khởi chạy thường chỉ trả về sau khi job kết thúc, nên test có thể kiểm tra trạng thái cuối ngay sau launchJob. Nếu ứng dụng cấu hình launcher bất đồng bộ, phương thức có thể trả về khi job vẫn đang chạy. Khi đó, JobExecution có thể đang ở trạng thái STARTING hoặc STARTED.

Trong trường hợp bất đồng bộ, test cần chờ execution đạt trạng thái kết thúc bằng cơ chế đồng bộ có giới hạn thời gian, sau đó mới assert COMPLETED hoặc FAILED. Tránh dùng Thread.sleep với thời lượng cố định vì thời gian xử lý thay đổi theo môi trường và có thể khiến test chập chờn.

## Những lỗi thường gặp

### Không tìm thấy JobLauncherTestUtils

Kiểm tra dependency spring-batch-test đã nằm trong test classpath chưa, version có tương thích với Spring Batch core không và test context đã dùng @SpringBatchTest hoặc đăng ký bean tiện ích thủ công chưa.

### Không xác định được job cần chạy

JobLauncherTestUtils phải được gắn với job cần kiểm thử. Nếu ApplicationContext có nhiều bean Job, việc chọn job có thể trở nên mơ hồ. Hãy cấu hình tiện ích để trỏ rõ đến job mục tiêu, chẳng hạn gọi setJob(...) với bean được inject bằng @Qualifier, hoặc tạo test configuration riêng cho job đó. Không giả định tiện ích sẽ tự chọn đúng job trong một context có nhiều job.

### JobParameters không hợp lệ

Đối chiếu tên key, kiểu dữ liệu và các tham số bắt buộc mà job hoặc validator yêu cầu. Đặc biệt kiểm tra tham số được đọc trong bean @StepScope có thực sự được truyền khi gọi launchJob(parameters) hoặc launchStep(...) hay không.

### JobInstanceAlreadyCompleteException

Repository đã có execution hoàn tất cho job với cùng identifying parameters. Nếu đây là test chạy độc lập, tạo identifying parameter mới. Nếu đang kiểm thử restart hoặc ngăn chạy lặp, giữ nguyên parameters và assert exception/trạng thái theo đúng kịch bản mong đợi.

### Step không tìm thấy hoặc không chạy được độc lập

Kiểm tra tên step chính xác và step có được đăng ký trong context hay không. Nếu step cần dữ liệu do step trước tạo ra, launchStep riêng lẻ có thể không cung cấp đủ execution context. Trong trường hợp đó, hãy dựng context đầu vào phù hợp hoặc dùng launchJob để kiểm thử cả luồng.

### Test nhận trạng thái STARTED thay vì COMPLETED

Kiểm tra cấu hình JobLauncher có chạy bất đồng bộ hay không. Nếu có, chờ execution kết thúc trước khi xác nhận trạng thái cuối.

## Ví dụ hoàn chỉnh: kiểm tra job và step execution

Ví dụ dưới đây kết hợp việc khởi chạy job, kiểm tra trạng thái chung và kiểm tra số item được xử lý ở step:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void ordersJobReadsAndWritesExpectedItems() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(execution.getAllFailureExceptions().isEmpty());

        StepExecution importStep = execution.getStepExecutions()
                .stream()
                .filter(step -> "importStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
        assertEquals(10, importStep.getReadCount());
        assertEquals(8, importStep.getWriteCount());
        assertEquals(2, importStep.getFilterCount());
    }
}
~~~

Đây là ví dụ minh họa với giả định job có step tên importStep, nhận inputFile, đọc 10 item, lọc 2 item và ghi 8 item. Khi áp dụng vào dự án, thay tên job/step, tham số và số lượng mong đợi theo cấu hình cùng fixture thực tế. Nên bổ sung assertion trên dữ liệu đầu ra để xác nhận nội dung đã được ghi đúng.

JobLauncherTestUtils phù hợp cho integration test của Spring Batch: nó giúp test khởi chạy job hoặc step bằng hạ tầng batch đã cấu hình và kiểm tra JobExecution/StepExecution sau khi chạy. Kết hợp nó với fixture xác định, JobParameters được thiết kế đúng mục đích và assertion trên kết quả nghiệp vụ sẽ giúp phát hiện lỗi ở cả luồng thực thi lẫn dữ liệu đầu ra.
