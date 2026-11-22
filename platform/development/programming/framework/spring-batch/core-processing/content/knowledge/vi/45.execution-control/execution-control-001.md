# Start job từ command line trong Spring Batch

Trong hệ thống xử lý theo lô, một job thường được kích hoạt theo lịch, bởi công cụ điều phối, từ pipeline vận hành hoặc bằng lệnh thủ công khi cần xử lý dữ liệu cho một ngày cụ thể. **Start job từ command line** là cách khởi chạy không cần giao diện web: tiến trình nhận tham số đầu vào, kết nối `JobRepository`, thực thi các step, ghi nhận trạng thái và trả kết quả cho hệ điều hành.

Bài học thuộc **Spring Batch Core Processing → Execution control**, dùng **Java 17, Spring Boot 3.x và Spring Batch 5.x** để trình bày cách đóng gói ứng dụng, chạy job qua `java -jar`, chọn job, truyền `JobParameters`, xử lý khởi chạy trùng/restart và tích hợp với scheduler. Cuối bài giới thiệu `CommandLineJobRunner` của Spring Batch cho những hệ thống không dùng cơ chế startup mặc định của Spring Boot.

## 1. Command line điều khiển những gì?

Một câu lệnh gọi batch nên trả lời rõ:

1. **Chạy ứng dụng nào?** Đường dẫn JAR hoặc classpath.
2. **Chạy job nào?** Tên `Job` được đăng ký trong Spring context.
3. **Xử lý dữ liệu nào?** Các `JobParameters`, ví dụ ngày nghiệp vụ và khu vực.
4. **Dựa trên lần chạy nào?** Tạo `JobInstance` mới hay restart instance đã thất bại.
5. **Báo kết quả ra sao?** Trạng thái `JobExecution`, log và mã thoát của tiến trình.

Luồng với một Spring Boot batch application:

```text
Shell / Cron / Kubernetes Job / CI
        |
        | java -jar report-batch.jar ... businessDate=2026-11-16
        v
Spring Boot application
        |
        +-- Application properties: --spring.*
        +-- Job parameters: name=value
        v
JobLauncherApplicationRunner
        |
        v
JobLauncher --> JobRepository
        |           |
        |           +-- JobInstance / JobExecution / StepExecution
        v
Job --> Step --> Tasklet hoặc Reader/Processor/Writer
        |
        v
JobExecution: COMPLETED / FAILED / STOPPED ...
        |
        v
Log, metadata, process exit code
```

Cần phân biệt **`BatchStatus`/`ExitStatus` của job** với **exit code của tiến trình Java**. Chúng đều có ích nhưng không phải một đối tượng; cách liên kết chúng được giải thích ở phần 7.

## 2. Hai phương án chạy từ command line

| Phương án | Cách gọi | Trường hợp phù hợp |
| --- | --- | --- |
| Spring Boot executable JAR | `java -jar app.jar ...` | Ứng dụng Spring Boot hiện đại, triển khai bằng Docker, cron hoặc scheduler |
| `CommandLineJobRunner` | `java -cp ... org.springframework.batch.core.launch.support.CommandLineJobRunner ...` | Spring Batch truyền thống, cần tự chọn Spring context, thường dùng cấu hình XML |

Hai phương án đều dùng hạ tầng Spring Batch nhưng có **cú pháp và hành vi khởi động riêng**. Nội dung chính của bài dùng `java -jar` với Spring Boot vì đó là đường triển khai thường gặp trong dự án Spring Boot 3.

## 3. Chuẩn bị ứng dụng batch có thể chạy bằng JAR

Giả sử job `dailyReportJob` tạo báo cáo cho `businessDate=2026-11-16` và `region=VN`.

### 3.1. Dependency và cấu hình ứng dụng

Ví dụ `build.gradle` của dự án đã dùng plugin Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    runtimeOnly 'com.h2database:h2'
}
```

H2 ở đây dùng để minh họa metadata của Spring Batch; nếu chạy job cần **restart xuyên qua nhiều tiến trình JVM**, nên dùng database bền vững như PostgreSQL hoặc MySQL và quản lý schema phù hợp. H2 in-memory thường mất lịch sử sau khi JVM kết thúc.

`src/main/resources/application.properties`:

```properties
spring.application.name=report-batch

# Chỉ dùng cho ví dụ H2: tạo bảng metadata BATCH_*.
spring.batch.jdbc.initialize-schema=always

# Cho phép Spring Boot chạy job khi ứng dụng bắt đầu.
spring.batch.job.enabled=true
```

Đối với Spring Boot 3 và batch auto-configuration thông thường, không cần thêm `@EnableBatchProcessing` để tạo hạ tầng mặc định. Việc bật annotation này có thể làm thay đổi cơ chế auto-configuration mà Boot đang quản lý, nên chỉ dùng khi thực sự tự cấu hình hạ tầng batch.

### 3.2. Entry point cho executable JAR

File `src/main/java/com/example/batch/ReportBatchApplication.java`:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportBatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportBatchApplication.class, args);
    }
}
```

`SpringApplication.run(...)` nạp cấu hình, tạo các bean, và gọi startup runner của Spring Boot. Khi có `Job` phù hợp và runner không bị vô hiệu hóa, Spring Boot sẽ khởi chạy job trong quá trình startup.

### 3.3. Tạo một job nhận tham số từ command line

File `src/main/java/com/example/batch/DailyReportJobConfig.java`:

```java
package com.example.batch;

import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailyReportJobConfig {

    @Bean
    public Job dailyReportJob(
            JobRepository jobRepository, Step reportStep) {

        return new JobBuilder("dailyReportJob", jobRepository)
                .start(reportStep)
                .build();
    }

    @Bean
    public Step reportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet reportTasklet) {

        return new StepBuilder("reportStep", jobRepository)
                .tasklet(reportTasklet, transactionManager)
                .build();
    }

    @Bean
    @StepScope
    public Tasklet reportTasklet(
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['region']}") String region) {

        return (contribution, chunkContext) -> {
            if (businessDate == null || businessDate.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing parameter: businessDate");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing parameter: region");
            }

            LocalDate date = LocalDate.parse(businessDate);
            System.out.printf(
                    "Generating report: businessDate=%s, region=%s%n",
                    date, region
            );

            // Ứng dụng thực: đọc dữ liệu, xử lý và ghi báo cáo.
            return RepeatStatus.FINISHED;
        };
    }
}
```

Trong ví dụ:

- `dailyReportJob` là **tên job** mà Spring Batch dùng khi xác định `JobInstance`.
- `reportStep` là step thực hiện công việc; ở đây dùng tasklet nhỏ để dễ quan sát.
- `@StepScope` cho phép tạo tasklet với **giá trị tham số của lần thực thi step**, thay vì cố đọc job parameters khi ứng dụng đang tạo bean.
- `#{jobParameters['businessDate']}` và `#{jobParameters['region']}` lấy dữ liệu từ `JobParameters`. Tên tham số phân biệt chữ hoa, chữ thường.
- `LocalDate.parse(...)` ở đây nhận định dạng ISO `yyyy-MM-dd`. Nhập ngày sai làm step thất bại; trong hệ thống thật nên có validation rõ ràng trước khi xử lý dữ liệu tốn kém.

## 4. Build JAR và start job

### 4.1. Đóng gói

Trên Linux/macOS:

```bash
./gradlew bootJar
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootJar
```

Sau khi build, file executable JAR thường nằm trong `build/libs/`. Giả sử file vừa tạo là `report-batch-0.0.1-SNAPSHOT.jar` (đây là **tên ví dụ**, cần thay bằng tên file thực tế).

### 4.2. Chạy job với ngày nghiệp vụ

Trên Linux/macOS:

```bash
java -jar build/libs/report-batch-0.0.1-SNAPSHOT.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 \
  region=VN
```

Trên Windows PowerShell, cách dễ sao chép nhất là dùng một dòng:

```powershell
java -jar "build/libs/report-batch-0.0.1-SNAPSHOT.jar" --spring.batch.job.name=dailyReportJob businessDate=2026-11-16 region=VN
```

Tasklet dự kiến in:

```text
Generating report: businessDate=2026-11-16, region=VN
```

Sau đó Spring Batch ghi nhận kết quả thực thi trong `JobRepository`. Job thành công thông thường có `BatchStatus.COMPLETED`. Muốn khẳng định xử lý nghiệp vụ chính xác, ngoài trạng thái thành công còn cần kiểm tra file hoặc dữ liệu đầu ra.

### 4.3. Phân biệt application option và job parameter

Đây là chỗ thường xảy ra lỗi nhất khi gọi batch qua shell:

```text
--spring.batch.job.name=dailyReportJob    Application property
--spring.profiles.active=prod             Application property
businessDate=2026-11-16                  JobParameter
region=VN                                JobParameter
```

Với cơ chế `JobLauncherApplicationRunner` mặc định của Spring Boot 3, các **non-option arguments** dạng `name=value` được chuyển thành job parameters. Đối số bắt đầu bằng `--` được Spring Boot coi là application property.

| Truyền trên command line | Cách dùng |
| --- | --- |
| `--spring.batch.job.name=dailyReportJob` | Chọn job được Boot tự chạy |
| `--spring.profiles.active=prod` | Chọn profile cấu hình |
| `businessDate=2026-11-16` | Truyền tham số `businessDate` cho job |
| `region=VN` | Truyền tham số `region` cho job |
| `--businessDate=2026-11-16` | Tạo property `businessDate`, **không tự động truyền thành JobParameter** qua runner mặc định |

Ví dụ dễ nhầm:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  --businessDate=2026-11-16 \
  --region=VN
```

Ở ví dụ trên, tasklet dùng `#{jobParameters['businessDate']}` sẽ không nhận giá trị như mong đợi. Cách sửa là **bỏ `--` trước các tham số nghiệp vụ**:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 \
  region=VN
```

Khi giá trị chứa dấu cách, nên đặt toàn bộ đối số trong dấu nháy:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  'businessDate=2026-11-16' \
  'region=South East Asia'
```

Quy tắc nháy chuỗi tùy shell. Với PowerShell có thể dùng `"region=South East Asia"`. Đối với vận hành thật, nên ưu tiên mã khu vực ổn định như `VN` hoặc `SG`.

## 5. Chọn job và điều khiển startup runner

### 5.1. Khi ứng dụng có một `Job`

Nếu Spring context chỉ có một bean `Job`, Spring Boot có thể tự chạy job đó khi ứng dụng khởi động với `spring.batch.job.enabled=true`. Trong script vận hành, vẫn nên ghi rõ `--spring.batch.job.name=dailyReportJob` để tránh mơ hồ nếu sau này dự án có thêm job.

### 5.2. Khi ứng dụng có nhiều `Job`

Giả sử context có `dailyReportJob` và `monthEndJob`:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
```

Để chạy job khác:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=monthEndJob \
  accountingMonth=2026-11
```

Không dựa vào thứ tự tạo bean hoặc tên class để quyết định job. `spring.batch.job.name` phải trùng với tên job được cấu hình; các tham số nghiệp vụ của từng job có thể khác nhau.

### 5.3. Khi cần tắt tự động chạy job

Nếu ứng dụng dùng REST API, scheduler nội bộ hoặc tự gọi `JobLauncher`, có thể tắt startup runner:

```properties
spring.batch.job.enabled=false
```

Hoặc trên command line:

```bash
java -jar report-batch.jar --spring.batch.job.enabled=false
```

Lúc này `java -jar` **chỉ khởi động ứng dụng**. Các non-option arguments như `businessDate=...` không tự kích hoạt job khi runner đã bị tắt; phải có mã ứng dụng chủ động gọi `JobLauncher`.

## 6. `JobParameters` quyết định job mới, chạy lại hay restart

Spring Batch phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| `Job` | Định nghĩa luồng xử lý, ví dụ `dailyReportJob` |
| `JobInstance` | Công việc logic được định danh bởi **tên job + identifying parameters** |
| `JobExecution` | Một lần thử thực thi instance, có trạng thái và metadata riêng |

Ví dụ lệnh:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
```

Giả sử hai tham số là identifying, lần chạy đầu có thể tạo:

```text
JobInstance A (dailyReportJob, 2026-11-16, VN)
└── JobExecution #1: COMPLETED
```

Chạy lại đúng lệnh đó trên repository vẫn giữ metadata:

```text
JobInstance A
└── JobExecution #1: COMPLETED
    └── yêu cầu chạy thêm → JobInstanceAlreadyCompleteException
```

Một instance đã hoàn thành thông thường không được chạy lại. `JobInstanceAlreadyCompleteException` là cơ chế kiểm soát của Spring Batch, không phải lỗi Java JAR.

### 6.1. Chạy cho ngày khác

Thay đổi identifying parameter:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-17 region=VN
```

Khi `businessDate` là identifying, giá trị mới tạo một `JobInstance` khác.

### 6.2. Chạy một instance độc lập dù cùng ngày

Có thể cung cấp `run.id` identifying riêng cho từng lần chạy:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN run.id=001
```

Lần kế tiếp:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN run.id=002
```

Hai lệnh có `run.id` khác nhau sẽ tạo instance khác nhau **khi `run.id` là identifying**. Điều đó không tự ngăn ghi dữ liệu trùng; job vẫn cần logic idempotency, ràng buộc unique key hoặc quy tắc xử lý lại phù hợp.

Việc cấu hình `RunIdIncrementer` trong định nghĩa job **không có nghĩa** mọi lệnh `java -jar` đều tự tăng `run.id`. Incrementer thường được sử dụng bởi cơ chế chủ động lấy “next instance”, không mặc nhiên thay thế các tham số cố định người dùng đã truyền trong startup runner.

### 6.3. Restart job đã thất bại

Nếu `JobExecution #1` bị `FAILED` và job được phép restart:

```text
JobInstance B (dailyReportJob, 2026-11-16, VN)
└── JobExecution #1: FAILED
```

Có thể khởi chạy lại **bằng cùng identifying parameters** trên một `JobRepository` bền vững:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
```

Spring Batch có thể tạo `JobExecution #2` thuộc cùng instance B:

```text
JobInstance B
├── JobExecution #1: FAILED
└── JobExecution #2: COMPLETED
```

Khả năng tiếp tục từ checkpoint tùy reader/writer, `ExecutionContext`, trạng thái các step và cấu hình restart. **Không đổi `run.id` identifying khi muốn restart cùng một instance**; đổi tham số nhận diện khiến yêu cầu trở thành một instance mới.

### 6.4. Cú pháp tham số có kiểu trong Spring Batch 5

Spring Batch 5 hỗ trợ `DefaultJobParametersConverter` với cú pháp tham số đầy đủ:

```text
name=value,type,identifying
```

Ví dụ:

```text
businessDate=2026-11-16,java.lang.String,true
region=VN,java.lang.String,true
traceId=trace-123,java.lang.String,false
```

Lệnh có thể viết:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  'businessDate=2026-11-16,java.lang.String,true' \
  'region=VN,java.lang.String,true' \
  'traceId=trace-123,java.lang.String,false'
```

`businessDate` và `region` tham gia nhận diện instance; `traceId` không tham gia. Nếu chỉ thay `traceId`, Spring Batch vẫn xét đó là cùng instance theo hai identifying parameters. Với ví dụ tasklet nhận `String`, đặt `java.lang.String` giúp giá trị tương thích với code hiện tại.

**Lưu ý phiên bản:** các converter và cú pháp tham số đã thay đổi qua các phiên bản Spring Batch. Ví dụ ở đây dành cho Spring Batch 5; các dự án cũ dùng `LegacyJobParametersConverter` có thể dùng cú pháp khác. Khi có converter tùy biến, cần tuân thủ hợp đồng của chính converter được cấu hình.

## 7. Theo dõi trạng thái job và exit code tiến trình

### 7.1. Xem `JobExecution` trong metadata

Khi hạ tầng Spring Batch dùng một database lưu lịch sử, có thể tra cứu:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailyReportJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

| `BatchStatus` | Ý nghĩa |
| --- | --- |
| `STARTING` / `STARTED` | Đang chuẩn bị hoặc đang thực thi |
| `COMPLETED` | Đã hoàn thành theo cơ chế Spring Batch |
| `FAILED` | Có lỗi ngăn job hoàn thành |
| `STOPPING` / `STOPPED` | Đang dừng hoặc đã dừng |
| `ABANDONED` | Execution đã bị bỏ dở theo quản trị batch |

`ExitStatus` có thể chứa mã hoặc mô tả cụ thể hơn `BatchStatus`, chẳng hạn mã được listener/flow trả về. Hai trạng thái này vẫn **khác** process exit code của JVM.

Ngoài trạng thái tổng thể, nên theo dõi tên step, số lượng item đọc/ghi/bỏ qua, thông tin lỗi và output nghiệp vụ. Một job có skip được cho phép có thể vẫn `COMPLETED`, nên kiểm tra trạng thái đơn thuần chưa đủ để kết luận mọi dữ liệu đều được xử lý.

### 7.2. Vì sao scheduler cần exit code?

Shell, cron, Task Scheduler, Kubernetes và công cụ CI thường sử dụng quy ước:

```text
0    → tiến trình thành công
!= 0 → tiến trình lỗi
```

Không nên mặc định `BatchStatus.FAILED` sẽ trở thành exit code khác 0 trong **mọi cách triển khai**. Cần hiểu runner và vòng đời ứng dụng. Một cách chủ động cho ứng dụng batch đồng bộ là đăng ký `JobExecutionListener` đồng thời triển khai Spring Boot `ExitCodeGenerator`.

Ví dụ class `BatchExitCodeListener.java`:

```java
package com.example.batch;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.boot.ExitCodeGenerator;

public class BatchExitCodeListener
        implements JobExecutionListener, ExitCodeGenerator {

    private volatile int exitCode = 0;

    @Override
    public void afterJob(JobExecution jobExecution) {
        exitCode = jobExecution.getStatus() == BatchStatus.COMPLETED
                ? 0
                : 1;
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
```

Đăng ký thành bean và gắn listener vào job:

```java
@Bean
public BatchExitCodeListener batchExitCodeListener() {
    return new BatchExitCodeListener();
}

@Bean
public Job dailyReportJob(
        JobRepository jobRepository,
        Step reportStep,
        BatchExitCodeListener exitCodes) {

    return new JobBuilder("dailyReportJob", jobRepository)
            .listener(exitCodes)
            .start(reportStep)
            .build();
}
```

Đoạn bean `dailyReportJob(...)` vừa nêu **thay thế** định nghĩa cùng tên ở phần 3; không khai báo hai bean trùng tên cùng lúc.

Đổi entry point để trả exit code cho hệ điều hành:

```java
public static void main(String[] args) {
    var context = SpringApplication.run(
            ReportBatchApplication.class, args);
    System.exit(SpringApplication.exit(context));
}
```

`SpringApplication.exit(context)` đọc các `ExitCodeGenerator` trong context. Với một job chạy **đồng bộ**, listener cập nhật `exitCode` khi job kết thúc: `0` nếu `COMPLETED`, `1` nếu không. Ứng dụng có nhiều job hoặc launcher bất đồng bộ cần cơ chế tổng hợp kết quả và chờ kết thúc rõ ràng, không sử dụng trực tiếp biến trạng thái đơn giản trên.

### 7.3. Kiểm tra mã thoát từ shell

Linux/macOS:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
echo "Exit code: $?"
```

PowerShell:

```powershell
java -jar "report-batch.jar" --spring.batch.job.name=dailyReportJob businessDate=2026-11-16 region=VN
$LASTEXITCODE
```

Trong script nên ghi nhận trạng thái ngay sau khi `java` kết thúc, tránh để các lệnh shell tiếp theo làm mất exit code gốc.

## 8. Đóng gói command line thành script vận hành

Một script giúp người vận hành truyền ngày chính xác và giữ cách chạy nhất quán giữa các môi trường.

Ví dụ `run-daily-report.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_JAR="/opt/batch/report-batch.jar"
REGION="${REPORT_REGION:-VN}"

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 yyyy-MM-dd" >&2
  exit 2
fi

BUSINESS_DATE="$1"

exec java -jar "$APP_JAR" \
  --spring.profiles.active=prod \
  --spring.batch.job.name=dailyReportJob \
  "businessDate=$BUSINESS_DATE" \
  "region=$REGION"
```

Gọi script:

```bash
chmod +x run-daily-report.sh
./run-daily-report.sh 2026-11-16
```

Với `exec`, shell được thay bằng tiến trình Java nên scheduler nhận trực tiếp exit code của Java. Truyền ngày nghiệp vụ một cách tường minh giúp tránh nhầm giữa ngày theo múi giờ máy chủ, thời điểm scheduler kích hoạt và ngày nghiệp vụ cần xử lý.

Ví dụ `run-daily-report.ps1` cho PowerShell:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string] $BusinessDate,
    [string] $Region = "VN"
)

$jarPath = "C:\batch\report-batch.jar"

& java -jar $jarPath `
  --spring.profiles.active=prod `
  --spring.batch.job.name=dailyReportJob `
  "businessDate=$BusinessDate" `
  "region=$Region"

$batchExitCode = $LASTEXITCODE
exit $batchExitCode
```

Gọi:

```powershell
.\run-daily-report.ps1 -BusinessDate "2026-11-16" -Region "VN"
```

Trong PowerShell, dấu backtick nối dòng phải nằm ở cuối dòng, không có khoảng trắng sau nó. Nếu không cần xuống dòng, viết câu lệnh Java trên một dòng sẽ dễ tránh lỗi hơn.

Khi sử dụng scheduler:

- **Cron:** cấu hình đường dẫn JAR tuyệt đối, biến môi trường và timezone rõ ràng.
- **Windows Task Scheduler:** kiểm tra chương trình chạy, thư mục làm việc, tài khoản có quyền với file và database.
- **Kubernetes Job/CronJob:** để tiến trình Java là main process; chọn chính sách retry/concurrency tương thích với định danh instance và khả năng restart của Spring Batch.
- **CI/CD:** ghi lại job name, ngày nghiệp vụ, process exit code và liên kết tới log/metadata của lần chạy.

Không cho phép hai tiến trình chạy chồng lấn trên cùng dữ liệu trừ khi job đã thiết kế cho concurrency. `JobExecutionAlreadyRunningException` có thể xuất hiện nếu cùng instance đang chạy, nhưng ngay cả hai instance khác nhau vẫn có thể tranh chấp hoặc ghi trùng dữ liệu ở tầng nghiệp vụ.

## 9. `CommandLineJobRunner` của Spring Batch

Trong các ứng dụng Spring Batch không dựa vào Spring Boot startup runner, class truyền thống là:

```text
org.springframework.batch.core.launch.support.CommandLineJobRunner
```

Cú pháp khái quát:

```text
java -cp <classpath> \
  org.springframework.batch.core.launch.support.CommandLineJobRunner \
  <context-location> <job-name> [job-parameters...]
```

Ví dụ với một Spring context XML **đã tồn tại trong ứng dụng**:

```bash
java -cp "target/classes:target/dependency/*" \
  org.springframework.batch.core.launch.support.CommandLineJobRunner \
  classpath:jobs/report-job.xml \
  dailyReportJob \
  businessDate=2026-11-16 \
  region=VN
```

Trong lệnh mẫu:

- `-cp` chứa các class của dự án và thư viện cần thiết; thư mục `target/dependency` phải được bước build chuẩn bị riêng, không tự xuất hiện từ mọi lệnh Maven.
- `classpath:jobs/report-job.xml` chỉ đường dẫn tới XML tạo Spring context chứa job. Đây là **file giả định** của ví dụ truyền thống, không được tạo trong dự án Boot mẫu phần 3.
- `dailyReportJob` là tên job, còn các tham số phía sau là `JobParameters` được runner chuyển đổi.
- Windows sử dụng dấu `;` làm classpath separator; Unix sử dụng `:`.

Không lấy một **Spring Boot executable fat JAR** chứa nested dependencies rồi mặc nhiên coi nó là classpath phẳng cho `java -cp`. Nếu dự án đã đóng gói và vận hành theo cơ chế Boot, `java -jar` là lựa chọn phù hợp hơn. `CommandLineJobRunner` có cơ chế chuyển exit status sang process exit code thông qua các thành phần của runner, nhưng cách cấu hình cụ thể phụ thuộc ứng dụng và phiên bản Spring Batch.

## 10. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Unable to access jarfile` | Tên JAR sai, chưa build hoặc đường dẫn không đúng | Xác nhận file trong `build/libs` và quyền đọc |
| App chạy nhưng job không start | `spring.batch.job.enabled=false`, bean `Job` thiếu, runner bị cấu hình lại | Kiểm tra cấu hình Boot và log khởi động |
| Chọn sai job | Tên job không khớp bean thực tế | Truyền `--spring.batch.job.name` chính xác |
| `businessDate` là `null` | Dùng `--businessDate=...` hoặc sai key | Truyền non-option `businessDate=...`, kiểm tra tên key trong SpEL |
| `JobInstanceAlreadyCompleteException` | Instance theo identifying parameters đã hoàn thành | Dùng instance mới nếu muốn chạy độc lập, không xóa metadata tùy tiện |
| `JobExecutionAlreadyRunningException` | Một execution của instance vẫn đang chạy | Kiểm tra tiến trình đang hoạt động và chính sách concurrency |
| Không restart được job | Metadata bị mất hoặc step/job không hỗ trợ restart | Dùng database bền vững, giữ identifying parameters và rà soát state |
| Thiếu bảng `BATCH_*` | Metadata schema chưa được tạo | Tạo schema đúng phiên bản bằng migration hoặc cấu hình test phù hợp |
| Job `FAILED` nhưng scheduler thấy success | Process exit code chưa được ánh xạ theo trạng thái batch | Dùng exit-code handling phù hợp và kiểm tra `$?`/`$LASTEXITCODE` |
| JVM không tự thoát | Ứng dụng còn web server hoặc thread nền | Dùng tiến trình batch không web hoặc đóng context có kiểm soát |
| Chạy lại ghi dữ liệu trùng | Instance mới xử lý lại đầu vào, writer không idempotent | Dùng khóa nghiệp vụ, unique constraint hoặc cơ chế chống trùng |

**Lưu ý về bảo mật:** `JobParameters` thường được lưu trong metadata `JobRepository`, đồng thời đối số command line có thể xuất hiện trong lịch sử shell, process listing hoặc log. Không đưa password, token hay secret vào `JobParameters` để tiện gọi lệnh. Dùng biến môi trường được bảo vệ, secret manager hoặc cấu hình triển khai tương ứng.

## 11. Bài thực hành

1. Tạo ứng dụng Boot với `dailyReportJob`, đóng gói bằng `bootJar` và chạy với `businessDate=2026-11-16 region=VN`.
2. Quan sát log, `JobExecution` và các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` để thấy job hoàn thành.
3. Trên **repository bền vững**, chạy lại cùng identifying parameters sau khi job đã `COMPLETED`. Giải thích vì sao phát sinh lỗi nhận diện instance.
4. Đổi `businessDate` để chạy instance mới. Thử thêm `run.id` identifying với giá trị mới để chạy một instance độc lập cho cùng ngày.
5. Truyền `--businessDate=2026-11-16` và so sánh với `businessDate=2026-11-16`. Kiểm tra giá trị mà tasklet thực sự nhận.
6. Truyền `businessDate=not-a-date`, quan sát step/job `FAILED` và process exit code. Nếu cần, bổ sung `ExitCodeGenerator` từ phần 7.
7. Đưa lệnh vào script nhận ngày làm tham số, chạy bằng scheduler mô phỏng và xác nhận script trả đúng exit code.
8. Tạo tình huống `FAILED` có khả năng restart, chạy lại với **cùng identifying parameters** và quan sát execution mới trong cùng instance.

Khi triển khai start job từ command line, hãy kiểm soát toàn bộ đường đi **câu lệnh → application configuration → job name → `JobParameters` → `JobInstance`/`JobExecution` → kết quả nghiệp vụ → process exit code**. Việc xác định rõ từng phần giúp lệnh chạy nhất quán, dễ giám sát và có thể khôi phục khi batch gặp sự cố.
