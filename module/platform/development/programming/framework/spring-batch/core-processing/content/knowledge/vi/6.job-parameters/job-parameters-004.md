# Tham số đầu vào từ command line

Spring Batch cho phép truyền dữ liệu đầu vào cho Job ngay khi khởi chạy ứng dụng từ command line. Những giá trị này được chuyển thành `JobParameters` và đi cùng lần chạy của Job. Chúng có thể xác định đơn vị công việc cần xử lý, ví dụ ngày nghiệp vụ, mã lô dữ liệu hoặc đường dẫn tệp đầu vào.

Ví dụ, một Job tổng hợp doanh thu theo ngày có thể được chạy với tham số `businessDate`:

```bash
java -jar daily-sales-batch.jar businessDate=2026-11-15
```

Trong ứng dụng Spring Boot có cấu hình Spring Batch tự động khởi chạy Job, các đối số dạng `key=value` được chuyển thành JobParameters bởi `JobLauncherApplicationRunner`. Với ứng dụng tự quản lý việc launch, có thể đọc đối số qua `ApplicationRunner` hoặc `CommandLineRunner`, sau đó tạo `JobParameters` bằng `JobParametersBuilder`.

## 1. Command line parameters là gì?

Command line parameters là các giá trị được người vận hành hoặc hệ thống lập lịch truyền vào khi gọi tiến trình Java. Ví dụ:

```bash
java -jar daily-sales-batch.jar businessDate=2026-11-15 regionId=12
```

Ở đây:

- `businessDate=2026-11-15` chỉ ngày dữ liệu cần tổng hợp.
- `regionId=12` chỉ khu vực cần xử lý.

Khi được chuyển thành `JobParameters`, các giá trị này trở thành dữ liệu đầu vào gắn với một lần khởi chạy Job. Spring Batch lưu metadata của JobParameters trong `JobRepository`, nhờ đó có thể xác định JobInstance và tra cứu lịch sử thực thi.

Không nên nhầm tham số của ứng dụng với tham số của Job. Ví dụ, `--spring.batch.job.name=dailySalesJob` là một tùy chọn cấu hình Spring Boot để chọn Job cần chạy; `businessDate=2026-11-15` là JobParameter truyền cho Job.

## 2. Truyền JobParameters trong ứng dụng Spring Boot

Với ứng dụng Spring Boot có Spring Batch auto-configuration, `JobLauncherApplicationRunner` có thể tự khởi chạy Job khi ứng dụng bắt đầu. Các đối số dạng `key=value` được chuyển thành JobParameters.

Ví dụ chạy file JAR:

```bash
java -jar target/daily-sales-batch.jar businessDate=2026-11-15
```

Nếu ứng dụng có nhiều Job, có thể chỉ rõ Job cần chạy bằng thuộc tính `spring.batch.job.name`:

```bash
java -jar target/daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15
```

Trong lệnh trên, hai nhóm đối số có mục đích khác nhau:

| Đối số | Vai trò |
|---|---|
| `--spring.batch.job.name=dailySalesJob` | Thuộc tính Spring Boot chọn Job sẽ được launch. |
| `businessDate=2026-11-15` | JobParameter được truyền vào Job. |

Một ví dụ có nhiều JobParameters:

```bash
java -jar target/daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    regionId=12 \
    requestedBy=scheduler
```

Khi ứng dụng khởi động, Spring Boot đọc các thuộc tính cấu hình, chọn Job và chuyển các đối số Job phù hợp thành `JobParameters`. Job sau đó được khởi chạy thông qua `JobLauncher`.

### Phân biệt tùy chọn cấu hình và JobParameter

Thông thường, tùy chọn cấu hình Spring Boot có tiền tố `--`, còn JobParameter theo cú pháp mặc định được viết dạng `key=value`:

```bash
java -jar app.jar \
    --spring.batch.job.name=customerImportJob \
    inputFile=/data/customers.csv \
    importDate=2026-11-15
```

`spring.batch.job.name` giúp chọn bean Job. `inputFile` và `importDate` là dữ liệu nghiệp vụ mà Job nhận. Tên tham số phải tương ứng với cách Job và các thành phần bên trong đọc JobParameters.

## 3. Kiểu dữ liệu và cú pháp JobParameters

Theo cấu hình mặc định, đối số `key=value` được chuyển thành JobParameter kiểu `String`. Ví dụ:

```bash
java -jar app.jar businessDate=2026-11-15 source=ERP
```

Khi cần kiểu dữ liệu khác, `DefaultJobParametersConverter` hỗ trợ chỉ rõ kiểu Java và cờ identifying theo cú pháp:

```text
parameterName=parameterValue,fully.qualified.Type,identifying
```

Ví dụ truyền một số nguyên kiểu `Long` và đánh dấu là tham số định danh:

```bash
java -jar app.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    regionId=12,java.lang.Long,true \
    requestedBy=nightly-scheduler,java.lang.String,false
```

Trong ví dụ này:

- `businessDate` là String và theo mặc định là identifying parameter.
- `regionId` được chuyển thành `Long` và được đánh dấu định danh.
- `requestedBy` là String nhưng không tham gia định danh JobInstance.

Kiểu dữ liệu được chỉ rõ phải được converter và ConversionService của ứng dụng hỗ trợ. Nếu dùng kiểu ngày giờ hoặc kiểu tùy chỉnh, cần bảo đảm định dạng chuỗi có thể chuyển đổi sang kiểu đó. Nếu không cần kiểu đặc biệt, truyền String rồi chuyển đổi và kiểm tra trong logic ứng dụng thường đơn giản hơn.

### Identifying và non-identifying parameters

JobParameters có thể gồm tham số định danh và không định danh:

- Tham số định danh tham gia tạo khóa của `JobInstance` cùng với tên Job.
- Tham số không định danh vẫn được lưu và có thể được Job sử dụng, nhưng không làm thay đổi danh tính JobInstance.

Ví dụ, `businessDate` và `regionId` có thể xác định một đơn vị tổng hợp; `requestedBy` chỉ lưu nguồn yêu cầu:

```text
dailySalesJob
  businessDate=2026-11-15  (identifying)
  regionId=12              (identifying)
  requestedBy=scheduler    (non-identifying)
```

Nếu cùng Job được gọi lại với cùng `businessDate` và `regionId`, việc thay đổi `requestedBy` không tạo JobInstance mới. Đây là điểm quan trọng khi thiết kế lệnh chạy và quy trình restart.

## 4. Đọc command line arguments bằng ApplicationRunner

Không phải ứng dụng nào cũng dùng cơ chế tự động launch của Spring Boot. Có thể tự đọc đối số command line bằng `ApplicationRunner`, tạo JobParameters và gọi `JobLauncher` theo logic riêng.

Ví dụ sau nhận ngày nghiệp vụ từ tùy chọn `--business-date`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailySalesCommandLineConfig {

    @Bean
    public ApplicationRunner launchDailySales(
            JobLauncher jobLauncher,
            Job dailySalesJob) {

        return (ApplicationArguments args) -> {
            var values = args.getOptionValues("business-date");
            if (values == null || values.size() != 1
                    || values.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Required option: --business-date=yyyy-MM-dd");
            }

            String businessDate = values.get(0);

            JobParameters parameters = new JobParametersBuilder()
                    .addString("businessDate", businessDate, true)
                    .toJobParameters();

            jobLauncher.run(dailySalesJob, parameters);
        };
    }
}
```

Chạy ứng dụng với:

```bash
java -jar target/daily-sales-batch.jar --business-date=2026-11-15
```

`ApplicationArguments` phân biệt tùy chọn dạng `--key=value` với các đối số không có tên tùy chọn. Trong ví dụ này, ứng dụng đọc `business-date`, sau đó chủ động ánh xạ thành JobParameter tên `businessDate`. Cách ánh xạ này giúp tên option ở command line không bắt buộc phải giống tên JobParameter.

Nếu ứng dụng dùng runner tùy chỉnh như trên trong Spring Boot, cần tắt cơ chế tự động launch Job để tránh cả `JobLauncherApplicationRunner` và runner tùy chỉnh cùng khởi chạy một Job:

```properties
spring.batch.job.enabled=false
```

Có thể đặt thuộc tính này trong `application.properties` hoặc truyền qua command line:

```bash
java -jar target/daily-sales-batch.jar \
    --spring.batch.job.enabled=false \
    --business-date=2026-11-15
```

Khi đã tắt auto-run, runner tùy chỉnh chịu trách nhiệm đọc và kiểm tra đối số, tạo JobParameters rồi gọi JobLauncher.

## 5. Dùng CommandLineJobRunner trong cấu hình truyền thống

Spring Batch cũng cung cấp `CommandLineJobRunner` cho cách khởi chạy truyền thống, thường gặp ở ứng dụng cấu hình bằng XML hoặc có application context được chuẩn bị cho runner này. Lệnh cần chỉ ra đường dẫn cấu hình, tên Job và các JobParameters:

```bash
java -cp "<application-classpath>" \
    org.springframework.batch.core.launch.support.CommandLineJobRunner \
    classpath:/jobs/daily-sales-job.xml \
    dailySalesJob \
    businessDate=2026-11-15
```

Các thành phần trong lệnh:

1. `<application-classpath>` chứa Spring Batch, Spring Framework, driver cơ sở dữ liệu và các thư viện ứng dụng.
2. `CommandLineJobRunner` là lớp nhận lệnh và điều phối khởi chạy.
3. `classpath:/jobs/daily-sales-job.xml` là vị trí application context chứa cấu hình Job và các thành phần liên quan.
4. `dailySalesJob` là tên định danh của Job trong context.
5. `businessDate=2026-11-15` là JobParameter.

`CommandLineJobRunner` phù hợp với ứng dụng dùng cơ chế cấu hình mà runner có thể nạp. Với ứng dụng Spring Boot đóng gói executable JAR, cách phổ biến hơn là gọi `java -jar` và sử dụng `JobLauncherApplicationRunner`, hoặc tự viết `ApplicationRunner` khi cần kiểm soát việc phân tích đối số.

## 6. Kiểm tra tham số đầu vào

Không nên giả định người chạy luôn truyền đủ tham số và đúng định dạng. Job cần xác định rõ tham số bắt buộc, tham số tùy chọn và quy tắc hợp lệ.

### Kiểm tra ở cấp command line

Với runner tùy chỉnh, có thể kiểm tra option tồn tại, chỉ xuất hiện một lần và có giá trị không rỗng trước khi gọi JobLauncher. Nếu tham số là ngày, có thể parse bằng `LocalDate` để phát hiện ngày sai định dạng:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

String businessDate = values.get(0);
try {
    LocalDate.parse(businessDate);
} catch (DateTimeParseException ex) {
    throw new IllegalArgumentException(
            "business-date must use yyyy-MM-dd", ex);
}
```

### Kiểm tra bằng JobParametersValidator

Spring Batch cho phép gắn `JobParametersValidator` vào Job để kiểm tra bộ tham số trước khi thực thi. Ví dụ dùng `DefaultJobParametersValidator` để yêu cầu `businessDate`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersValidator;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.job.DefaultJobParametersValidator;
import org.springframework.context.annotation.Bean;

@Bean
public Job dailySalesJob(
        JobRepository jobRepository,
        Step aggregateSalesStep) {

    JobParametersValidator validator =
            new DefaultJobParametersValidator(
                    new String[] {"businessDate"},
                    new String[] {"regionId", "requestedBy"});

    return new JobBuilder("dailySalesJob", jobRepository)
            .validator(validator)
            .start(aggregateSalesStep)
            .build();
}
```

Trong cấu hình này, `businessDate` là tham số bắt buộc; `regionId` và `requestedBy` là các tham số tùy chọn được cho phép. Nếu ứng dụng có nhiều tham số hoặc quy tắc nghiệp vụ phức tạp, có thể triển khai validator riêng để kiểm tra định dạng ngày, khoảng thời gian, mã lô hoặc sự kết hợp giữa các tham số.

Kiểm tra command line giúp đưa ra thông báo lỗi sớm và dễ hiểu cho người vận hành. Validator của Job vẫn cần thiết vì Job có thể được khởi chạy từ scheduler, API hoặc thành phần Java khác, không chỉ từ command line.

## 7. Trích xuất JobParameters bên trong Step

Khi Job đã được khởi chạy, các thành phần xử lý có thể đọc JobParameters thông qua `StepExecution` hoặc `ChunkContext`. Ví dụ, một Tasklet có thể lấy ngày nghiệp vụ từ `StepContribution`:

```java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public class DailySummaryTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String businessDate = contribution.getStepExecution()
                .getJobParameters()
                .getString("businessDate");

        System.out.println("Processing business date: " + businessDate);
        return RepeatStatus.FINISHED;
    }
}
```

Nếu dùng kiểu dữ liệu khác String, cần đọc bằng kiểu tương ứng hoặc chuyển đổi rõ ràng. Nên lấy tham số từ `JobParameters` thay vì tự đọc lại `System.getProperty` hoặc biến môi trường ở mọi Step; cách này giữ dữ liệu đầu vào gắn với metadata của lần chạy và giúp truy vết chính xác.

## 8. Quy tắc quoting và cách truyền giá trị

Command line được shell phân tích trước khi Java nhận đối số. Nếu giá trị có khoảng trắng hoặc ký tự đặc biệt, cần đặt trong dấu nháy theo cú pháp của shell.

Ví dụ với Bash hoặc PowerShell:

```bash
java -jar daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    'requestedBy=nightly operations'
```

Ví dụ với Windows Command Prompt:

```bat
java -jar daily-sales-batch.jar --spring.batch.job.name=dailySalesJob businessDate=2026-11-15 "requestedBy=nightly operations"
```

Shell có thể có quy tắc escape khác nhau đối với dấu nháy, dấu cách, dấu phẩy và ký tự đặc biệt. Cần kiểm tra đối số thực tế mà ứng dụng nhận được nếu giá trị bị tách hoặc biến đổi ngoài ý muốn.

Không nên truyền mật khẩu, access token hoặc bí mật trực tiếp qua command line. Các giá trị này có thể xuất hiện trong lịch sử shell, danh sách tiến trình hoặc log của hệ thống. Hãy dùng biến môi trường, secret manager hoặc cơ chế cấu hình bảo mật, và chỉ truyền tham chiếu cần thiết vào JobParameters.

## 9. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Job không nhận được tham số | Tên key không đúng hoặc đối số được truyền dưới dạng option mà runner không đọc như JobParameter. | Kiểm tra cú pháp `key=value` và cơ chế runner đang dùng. |
| Boot chạy nhầm Job | Không chỉ rõ Job cần chạy trong ứng dụng có nhiều Job. | Dùng `--spring.batch.job.name=<jobName>` hoặc cấu hình tên Job phù hợp. |
| Job được khởi chạy hai lần | Auto runner và runner tùy chỉnh cùng hoạt động. | Tắt `spring.batch.job.enabled` khi tự quản lý launch. |
| Giá trị bị tách thành nhiều đối số | Thiếu dấu nháy khi giá trị có khoảng trắng. | Quote toàn bộ token `key=value` theo shell. |
| Không chuyển đổi được kiểu | Converter không hỗ trợ kiểu hoặc định dạng giá trị không hợp lệ. | Dùng kiểu mặc định String hoặc cấu hình converter và định dạng rõ ràng. |
| JobInstance đã hoàn tất nên launch bị từ chối | Các identifying JobParameters giống với instance đã `COMPLETED`. | Dùng restart nếu instance chưa hoàn thành; nếu cần công việc mới, tạo identifying parameter có ý nghĩa nghiệp vụ. |
| Thay đổi tham số nhưng vẫn bị coi là cùng instance | Chỉ thay đổi tham số không định danh. | Kiểm tra cờ identifying của JobParameters. |
| Lộ thông tin nhạy cảm | Bí mật được truyền trực tiếp trên command line. | Dùng biến môi trường hoặc secret manager. |

## 10. Quy trình chạy Job từ command line trong thực tế

Một quy trình vận hành thường gồm các bước sau:

1. Xác định Job cần chạy và các tham số nghiệp vụ bắt buộc.
2. Chọn identifying parameters sao cho chúng đại diện đúng đơn vị công việc cần xử lý.
3. Kiểm tra file JAR, cấu hình môi trường, database và metadata schema đã sẵn sàng.
4. Truyền Job name cùng JobParameters bằng cú pháp của runner đang dùng.
5. Kiểm tra log và `JobExecution` để xác định Job đã bắt đầu, đang chạy hay đã kết thúc.
6. Nếu launch thất bại, đọc exception và metadata để phân biệt lỗi tham số, instance đang chạy, instance đã hoàn tất hoặc lỗi xử lý trong Step.

Ví dụ một lệnh chạy theo lịch:

```bash
java -jar /opt/batch/daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    regionId=12,java.lang.Long,true \
    requestedBy=nightly-scheduler,java.lang.String,false
```

Lệnh này truyền ngày nghiệp vụ và khu vực làm dữ liệu xác định công việc, đồng thời lưu nguồn gọi là `requestedBy`. Nếu scheduler gửi lại cùng lệnh sau khi Job đã hoàn tất, Spring Batch nhận diện cùng JobInstance và từ chối launch trùng. Nếu Job thất bại, cùng identifying parameters có thể được dùng để restart khi cấu hình cho phép.

## Kết luận

Tham số command line là một cách thuận tiện để cung cấp dữ liệu đầu vào cho Job mà không cần sửa mã nguồn mỗi lần chạy. Trong Spring Boot, các đối số `key=value` có thể được `JobLauncherApplicationRunner` chuyển thành JobParameters; ứng dụng cũng có thể tự đọc `ApplicationArguments` và gọi `JobLauncher`. Cần phân biệt tùy chọn cấu hình như `spring.batch.job.name` với JobParameter, chọn đúng identifying parameters, kiểm tra kiểu và giá trị, đồng thời kiểm soát việc launch trùng. Khi các tham số được thiết kế đúng, Job có thể chạy theo ngày, lô hoặc yêu cầu nghiệp vụ và được theo dõi, restart qua metadata của Spring Batch.
