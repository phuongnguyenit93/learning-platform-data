# @Value từ jobParameters

Trong Spring Batch, JobParameters là các giá trị đầu vào được truyền khi khởi chạy một Job. Một Step có thể cần đọc tên file, ngày nghiệp vụ, mã tenant, giới hạn số bản ghi hoặc chế độ xử lý. Có thể lấy các giá trị này bằng biểu thức SpEL trong annotation `@Value`, ví dụ `@Value("#{jobParameters['inputFile']}")`.

Vì JobParameters chỉ có khi JobExecution bắt đầu, bean nhận các giá trị này cần được tạo trong đúng phạm vi thực thi. Cách thông dụng là khai báo bean `@StepScope`. Spring tạo scoped proxy khi khởi động application context và chỉ khởi tạo target bean khi Step bắt đầu, lúc đó JobParameters đã có sẵn.

## 1. JobParameters là gì?

`JobParameters` là tập tham số đầu vào bất biến gắn với một JobInstance/JobExecution. Chúng cho biết một lần chạy cần xử lý dữ liệu nào và với điều kiện nào.

Ví dụ một Job import đơn hàng có thể nhận:

| Parameter | Ví dụ | Mục đích |
|---|---|---|
| `inputFile` | `/data/in/orders.csv` | File đầu vào cần đọc. |
| `businessDate` | `2026-11-15` | Ngày nghiệp vụ của lô. |
| `tenantId` | `42` | Phạm vi khách hàng/tenant cần xử lý. |
| `maxRows` | `10000` | Giới hạn số dòng trong lần chạy. |
| `importMode` | `INCREMENTAL` | Chế độ import. |

Các tham số được truyền vào Job khi launch, thường qua `JobParametersBuilder`. Ví dụ:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addLong("tenantId", 42L, true)
        .addLong("maxRows", 10_000L, false)
        .addString("importMode", "INCREMENTAL", true)
        .toJobParameters();
```

Tham số được đánh dấu `true` là identifying parameter, tham gia xác định JobInstance. Tham số `false` không tham gia định danh. Việc lựa chọn identifying parameters ảnh hưởng đến restart: cùng tên Job và cùng identifying parameters sẽ trỏ đến cùng JobInstance; thay đổi một identifying parameter có thể tạo JobInstance mới.

## 2. Đọc JobParameters bằng @Value và SpEL

Spring Batch cung cấp các biến ngữ cảnh trong SpEL. Để đọc một JobParameter theo tên, dùng biểu thức:

```java
@Value("#{jobParameters['inputFile']}")
```

Trong đó:

- `#{...}` là cú pháp biểu thức SpEL.
- `jobParameters` là map chứa các tham số của JobExecution hiện tại.
- `['inputFile']` lấy giá trị theo key `inputFile`.

Ví dụ đọc ngày nghiệp vụ:

```java
@Value("#{jobParameters['businessDate']}") String businessDate
```

Tên key phải khớp với tên được dùng khi tạo JobParameters. Nếu key không tồn tại, biểu thức có thể trả về `null`; khi đó ứng dụng cần xác định tham số là bắt buộc hay tùy chọn và xử lý phù hợp.

## 3. Vì sao cần @StepScope?

Các bean Spring thông thường có scope singleton và được khởi tạo khi application context được tạo. Tại thời điểm đó, chưa có JobExecution cụ thể nên các biến `jobParameters`, `stepExecutionContext` hoặc `jobExecutionContext` chưa có giá trị cho một lần chạy.

`@StepScope` trì hoãn việc tạo target bean cho đến khi Step bắt đầu. Bean được gắn với một StepExecution và có thể truy cập các giá trị thuộc lần chạy đó.

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Khi Step bắt đầu, Spring tạo reader với đúng `inputFile` của JobExecution hiện tại. Nếu một Job khác chạy đồng thời với file khác, mỗi StepExecution có target bean được khởi tạo trong scope tương ứng.

Không nên bỏ `@StepScope` khỏi bean có `@Value` tham chiếu JobParameters rồi mong Spring biết phải lấy tham số của lần chạy nào. Bean singleton không gắn với một JobExecution cụ thể.

## 4. Đọc nhiều JobParameters trong cùng bean

Một bean Step-scoped có thể nhận nhiều tham số qua constructor hoặc tham số của phương thức `@Bean`:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") Long tenantId) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Ví dụ nhận `businessDate` và `tenantId` để minh họa việc inject nhiều tham số; nếu reader không cần dùng các giá trị đó, nên bỏ chúng khỏi chữ ký bean. Không giữ tham số không sử dụng chỉ để làm cấu hình dài hơn.

Có thể inject bằng field hoặc constructor trong một class `@Component @StepScope`. Constructor injection thường giúp phụ thuộc rõ ràng và dễ kiểm thử hơn.

## 5. Chuyển đổi kiểu dữ liệu

JobParameters có thể chứa các kiểu dữ liệu được Spring Batch hỗ trợ. Khi dùng `@Value`, giá trị được đưa qua cơ chế chuyển đổi của Spring để gán vào kiểu đích nếu có converter phù hợp.

Ví dụ tham số số nguyên:

```java
@Bean
@StepScope
public Tasklet processTenantTasklet(
        @Value("#{jobParameters['tenantId']}") Long tenantId) {

    return (contribution, chunkContext) -> {
        // Dùng tenantId để giới hạn phạm vi xử lý.
        return RepeatStatus.FINISHED;
    };
}
```

Với ngày nghiệp vụ, cách dễ kiểm soát là truyền chuỗi ISO-8601 và parse rõ ràng:

```java
import java.time.LocalDate;

@Bean
@StepScope
public Tasklet dailyTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate date = LocalDate.parse(businessDate);

    return (contribution, chunkContext) -> {
        // Xử lý dữ liệu cho ngày date.
        return RepeatStatus.FINISHED;
    };
}
```

Nếu muốn inject trực tiếp kiểu `LocalDate`, cần bảo đảm ConversionService của application có converter phù hợp với cách biểu diễn JobParameter. Không nên giả định mọi phiên bản Spring Batch/Spring đều tự chuyển mọi kiểu ngày tháng theo cùng một quy tắc.

Đối với tham số số, hãy dùng kiểu tương ứng với kiểu JobParameter được tạo. Nếu truyền `Long` nhưng inject `Integer`, cần có chuyển đổi hợp lệ và kiểm soát overflow. Cách rõ ràng nhất là thống nhất kiểu ở nơi tạo JobParameters và nơi inject.

## 6. Tham số bắt buộc và tham số tùy chọn

Nếu một tham số bắt buộc, hãy kiểm tra rõ ràng khi target bean được khởi tạo. Ví dụ:

```java
@Bean
@StepScope
public Tasklet importTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "Required JobParameter 'inputFile' is missing");
    }

    return (contribution, chunkContext) -> {
        // Thực hiện import.
        return RepeatStatus.FINISHED;
    };
}
```

Việc kiểm tra tại bean factory giúp lỗi cấu hình được phát hiện khi Step khởi tạo, với thông báo rõ ràng. Có thể kiểm tra sớm hơn trong một validation Step nếu muốn Job thất bại với trạng thái và audit nghiệp vụ cụ thể trước khi tạo reader.

Với tham số tùy chọn, SpEL hỗ trợ toán tử Elvis `?:` để dùng giá trị mặc định khi biểu thức bên trái là null:

```java
@Value("#{jobParameters['maxRows'] ?: 1000}") Integer maxRows
```

Ví dụ trên dùng 1000 khi `maxRows` không được truyền. Hãy dùng default chỉ khi giá trị đó thực sự là chính sách nghiệp vụ. Không nên tự đặt default cho tham số bắt buộc như file nguồn, tenant hoặc ngày chốt dữ liệu vì có thể khiến Job xử lý nhầm dữ liệu.

Có thể dùng giá trị mặc định chuỗi:

```java
@Value("#{jobParameters['importMode'] ?: 'INCREMENTAL'}") String importMode
```

Giá trị mặc định phải phù hợp với quy tắc định danh và restart của Job. Nếu chế độ import làm thay đổi ý nghĩa đơn vị công việc, nên truyền nó như một identifying parameter thay vì âm thầm dùng default khác giữa các lần chạy.

## 7. Dùng JobParameters trong Processor

Processor có thể cần tham số để áp dụng quy tắc theo tenant, ngày nghiệp vụ hoặc chế độ xử lý. Khi đó, khai báo Processor là Step-scoped:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class TenantOrderProcessor
        implements ItemProcessor<Order, ProcessedOrder> {

    private final Long tenantId;

    public TenantOrderProcessor(
            @Value("#{jobParameters['tenantId']}") Long tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public ProcessedOrder process(Order order) {
        if (!tenantId.equals(order.tenantId())) {
            return null;
        }
        return ProcessedOrder.from(order);
    }
}
```

Trong ví dụ, Processor chỉ giữ item thuộc tenant được yêu cầu; item của tenant khác bị filter vì phương thức trả về `null`. Nếu khác tenant là lỗi dữ liệu thay vì điều kiện lọc, cần ném exception nghiệp vụ và cấu hình skip/fail policy phù hợp.

`@StepScope` cũng hữu ích khi cùng một Job chạy đồng thời với nhiều tenant. Mỗi StepExecution nhận giá trị `tenantId` riêng, thay vì lưu tham số của một lần chạy vào field của singleton Processor dùng chung.

## 8. Dùng JobParameters trong Writer hoặc Tasklet

Writer có thể cần tham số để ghi vào bảng đích theo kỳ dữ liệu. Tasklet có thể cần tham số để gọi thủ tục hoặc tạo file đầu ra.

Ví dụ Tasklet nhận ngày nghiệp vụ:

```java
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public Tasklet closeBusinessDayTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate date = LocalDate.parse(businessDate);

    return (contribution, chunkContext) -> {
        // Gọi service đóng kỳ cho date.
        return RepeatStatus.FINISHED;
    };
}
```

Không nên inject JobParameters trực tiếp vào một singleton Writer/Tasklet nếu bean đó được chia sẻ giữa nhiều execution. Dùng scope phù hợp để mỗi lần chạy nhận đúng giá trị.

## 9. Phân biệt jobParameters với các ExecutionContext

SpEL trong Spring Batch có thể đọc nhiều loại dữ liệu ngữ cảnh. Cần chọn đúng nguồn:

| Biểu thức | Nguồn dữ liệu | Khi nào dùng |
|---|---|---|
| `#{jobParameters['inputFile']}` | JobParameters | Giá trị đầu vào được truyền khi launch Job. |
| `#{jobExecutionContext['batchId']}` | Job ExecutionContext | Giá trị nhỏ được chia sẻ giữa các Step trong cùng JobExecution. |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext | Checkpoint hoặc phạm vi dữ liệu riêng của Step/partition. |
| `#{stepExecution.stepName}` | StepExecution | Metadata của Step hiện tại. |
| `#{jobExecution.id}` | JobExecution | ID của lần chạy hiện tại, thường dùng cho trace/audit. |

Ví dụ reader của một partition nhận phạm vi ID từ Step ExecutionContext:

```java
@Bean
@StepScope
public JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {
    // Tạo reader truy vấn minId..maxId.
}
```

`minId` và `maxId` ở đây được tạo bởi Partitioner, không phải tham số launch trực tiếp. Nếu lấy nhầm từ `jobParameters`, worker có thể không nhận được phạm vi riêng của partition.

JobParameters nên chứa input và lựa chọn của người gọi. ExecutionContext nên chứa trạng thái thực thi hoặc dữ liệu trung gian được lưu để Step tiếp tục/chia sẻ.

## 10. JobParameters là bất biến và ảnh hưởng đến restart

JobParameters gắn với JobInstance/JobExecution và không nên được xem như một map mutable để thay đổi trong lúc Job đang chạy. Nếu cần lưu kết quả tính toán hoặc trạng thái trung gian, hãy dùng ExecutionContext hoặc database nghiệp vụ.

Ví dụ Job được launch với:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
```

Nếu Job thất bại và cần restart, hãy dùng lại cùng identifying parameters. Khi đó, Step-scoped bean sẽ được tạo cho JobExecution mới nhưng nhận cùng giá trị đầu vào, giúp restart xử lý đúng file và ngày nghiệp vụ ban đầu.

Nếu đổi `businessDate` hoặc `inputFile` trong lần gọi tiếp theo và chúng là identifying parameters, Spring Batch tạo JobInstance mới. Đây là một lần chạy logic mới, không phải restart instance cũ.

Không nên dùng `@Value` để đọc `run.id` mới tạo mỗi lần nếu mục tiêu là tiếp tục JobInstance cũ. `RunIdIncrementer` có thể tạo identifying parameter mới và do đó tạo JobInstance mới.

## 11. Ví dụ cấu hình Job hoàn chỉnh

Ví dụ sau kết hợp JobParameters, Step-scoped Reader và chunk Step trong Spring Batch 5 trở lên:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportJobConfig {

    @Bean
    @StepScope
    public FlatFileItemReader<Order> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Order> orderReader,
            ItemProcessor<Order, ProcessedOrder> orderProcessor,
            ItemWriter<ProcessedOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, ProcessedOrder>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

Trong cấu hình trên, Spring inject scoped proxy của `orderReader` vào Step. Khi Step thực thi, proxy lấy target reader của StepExecution hiện tại với `inputFile` từ JobParameters. `Order`, `ProcessedOrder`, Processor và Writer là các kiểu ứng dụng đã được khai báo ở nơi khác.

Khi launch:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.csv", true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

`inputFile` là identifying parameter trong ví dụ. Khi restart cùng JobInstance, hãy dùng lại đúng giá trị này.

## 12. Kiểm thử bean có @StepScope

Một bean Step-scoped không thể được tạo target bình thường bên ngoài Step vì các biến ngữ cảnh chưa tồn tại. Khi unit test cần kiểm tra late binding, có thể dùng `StepScopeTestUtils` để mở một Step scope giả lập với `StepExecution` và JobParameters cụ thể.

Ví dụ class settings nhỏ:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class ImportSettings {

    private final String inputFile;

    public ImportSettings(
            @Value("#{jobParameters['inputFile']}") String inputFile) {
        this.inputFile = inputFile;
    }

    public String inputFile() {
        return inputFile;
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ImportSettingsTest {

    @Autowired
    private ImportSettings importSettings;

    @Test
    void injectsInputFileFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "/tmp/orders.csv")
                .toJobParameters();
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        String inputFile = StepScopeTestUtils.doInStepScope(
                stepExecution,
                importSettings::inputFile);

        assertEquals("/tmp/orders.csv", inputFile);
    }
}
```

Test context cần có Spring Batch test support và component scan hoặc bean definition cho `ImportSettings`. `StepScopeTestUtils.doInStepScope()` mở scope trong thời gian callback thực thi, nhờ đó `jobParameters` có giá trị. Ngoài unit test này, integration test với `@SpringBatchTest` và `JobLauncherTestUtils` có thể xác nhận Job thật nhận đúng tham số khi launch.

## 13. Các lỗi thường gặp khi dùng @Value từ jobParameters

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `jobParameters` không tồn tại khi tạo bean | Bean singleton được khởi tạo ngoài Step scope. | Đặt `@StepScope` cho bean cần late binding. |
| Giá trị inject là `null` | Tên key sai hoặc caller không truyền tham số. | Kiểm tra JobParameters và xác thực tham số bắt buộc. |
| Không chuyển được kiểu | Kiểu JobParameter và kiểu đích không tương thích hoặc thiếu converter. | Thống nhất kiểu; parse rõ ràng hoặc đăng ký converter. |
| Đổi tham số khi restart | Tạo JobInstance mới nếu tham số là identifying. | Giữ nguyên identifying parameters khi restart. |
| Dùng JobParameters làm nơi lưu tiến độ | Tham số đầu vào không phải checkpoint mutable. | Dùng Step/Job ExecutionContext hoặc database. |
| Dùng field mutable trong singleton để lưu tham số | Nhiều JobExecution đồng thời có thể ghi đè dữ liệu. | Dùng StepScope hoặc JobScope phù hợp. |
| Dùng default cho tham số bắt buộc | Job có thể xử lý nhầm nguồn hoặc kỳ dữ liệu. | Kiểm tra và báo lỗi rõ ràng khi thiếu tham số. |
| Nhầm JobParameters với StepExecutionContext | Giá trị partition/checkpoint không nằm trong JobParameters. | Dùng đúng biến SpEL theo nguồn dữ liệu. |
| Đưa secret vào JobParameters | Metadata và log có thể lưu/hiển thị tham số. | Dùng secret manager hoặc cấu hình bảo mật riêng. |

## Kết luận

`@Value("#{jobParameters['...']}")` cho phép inject tham số đầu vào của Job vào Reader, Processor, Writer hoặc Tasklet. Vì JobParameters chỉ tồn tại theo một lần thực thi, bean cần late binding nên được khai báo `@StepScope` (hoặc scope phù hợp khác) để target bean được tạo khi Step bắt đầu. Hãy thống nhất kiểu tham số, xác thực giá trị bắt buộc, dùng default chỉ khi có ý nghĩa nghiệp vụ và giữ nguyên identifying parameters khi restart. Phân biệt JobParameters với Job/Step ExecutionContext sẽ giúp cấu hình rõ ràng và giữ checkpoint đúng qua các lần thực thi.
