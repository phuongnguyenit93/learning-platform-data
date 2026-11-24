# Đọc CSV và tệp độ rộng cố định

## 1. Bài toán và mục tiêu

Trong một ứng dụng **Spring Cloud Task**, một lần chạy thường nhận tham số, xử lý một khối dữ liệu hữu hạn rồi kết thúc. Ví dụ, mỗi đêm doanh nghiệp nhận tệp thông tin khách hàng từ đối tác, đọc từng dòng, kiểm tra dữ liệu và cập nhật cơ sở dữ liệu. Spring Cloud Task theo dõi **lần thực thi ứng dụng** bằng `TaskRepository`; khi việc nhập dữ liệu có nhiều bản ghi, **Spring Batch** cung cấp các thành phần đọc, ghi, transaction và khả năng khởi động lại.

Chương **Job một bước** tập trung vào công việc có luồng xử lý đơn giản: **đọc một tệp → ánh xạ thành đối tượng → ghi kết quả**, được tổ chức thành **một `Job` có một `Step` kiểu chunk-oriented**. Bài này xét hai dạng tệp đầu vào phổ biến:

- **CSV (Comma-Separated Values):** các cột được phân tách bằng dấu phẩy; chuỗi có dấu phẩy có thể đặt trong dấu nháy kép.
- **Tệp độ rộng cố định (fixed-width file):** không cần ký tự phân cách; mỗi trường chiếm số vị trí đã quy định.

Sau bài học, bạn có thể:

1. Định nghĩa hợp đồng dữ liệu cho CSV và fixed-width.
2. Phân biệt `FlatFileItemReader`, `LineTokenizer`, `FieldSetMapper` và `LineMapper`.
3. Dùng `DelimitedLineTokenizer` để đọc CSV và `FixedLengthTokenizer` để đọc bản ghi theo khoảng cột.
4. Lắp cả hai lựa chọn vào **một Spring Batch Job có một Step**, chọn định dạng theo `JobParameters`.
5. Đọc log, kiểm tra kết quả trong database, xử lý dòng lỗi và restart sau khi một chunk thất bại.
6. Phân biệt `TaskRepository` của Spring Cloud Task với `JobRepository` và `ExecutionContext` của Spring Batch.

> Các đoạn Java chính trong bài sử dụng kiểu API của **Spring Boot 3.x và Spring Batch 5.x**, với ví dụ kết quả lưu vào PostgreSQL. Spring Batch 6 có thay đổi một số package/API; hãy dùng mã mẫu và BOM tương ứng với phiên bản thực tế thay vì trộn import từ các phiên bản khác nhau.

## 2. Một Job, một Step và hai định dạng đầu vào

Một Spring Batch `Job` có thể chứa nhiều step, nhưng trường hợp này chỉ cần **một step**. Cùng cấu hình step đó sẽ nhận một `ItemReader` được tạo theo định dạng tệp của lần chạy.

~~~mermaid
flowchart LR
    A["Tham số: inputFile, inputFormat"] --> B["Job: importCustomerFileJob"]
    B --> C["Step: importCustomersStep"]
    C --> D{"inputFormat?"}
    D -->|csv| E["DelimitedLineTokenizer"]
    D -->|fixed| F["FixedLengthTokenizer"]
    E --> G["FieldSetMapper → CustomerRow"]
    F --> G
    G --> H["ItemWriter / database nghiệp vụ"]
    C --> I[("JobRepository: trạng thái chunk, step, job")]
    B --> J[("TaskRepository: vòng đời ứng dụng task")]
~~~

**Hai repository khác nhau:**

| Spring Cloud Task | Spring Batch |
| --- | --- |
| `TaskRepository` ghi mỗi lần khởi chạy ứng dụng task | `JobRepository` ghi `JobInstance`, `JobExecution`, `StepExecution` |
| Quan tâm thời gian bắt đầu/kết thúc và mã thoát của process | Quan tâm số item đã đọc/ghi, trạng thái step và điểm restart |
| Lần chạy lại tạo `TaskExecution` mới | Job có thể restart theo nhận diện `JobInstance` và `JobParameters` |
| Không tự lưu vị trí dòng trong tệp | `ItemStream` và `ExecutionContext` có thể lưu vị trí đọc ở điểm commit |

Nếu thêm **`spring-cloud-task-batch`** cùng `Job`, Spring Cloud Task có thể tự cấu hình `TaskBatchExecutionListener` để liên kết một JobExecution với TaskExecution tương ứng. Việc liên kết giúp tra cứu, nhưng **không thay thế** hai kho metadata riêng biệt.

## 3. Hợp đồng dữ liệu của ví dụ

Ta nhập dữ liệu khách hàng với ba trường:

| Trường Java | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `customerId` | Mã khách hàng | Chuỗi 5 ký tự, ví dụ `C0001` |
| `customerName` | Tên khách hàng | Không rỗng; tối đa 20 ký tự đối với fixed-width |
| `monthlyFee` | Phí hàng tháng | Số thập phân không âm; ví dụ `120000` |

Đối tượng dữ liệu:

~~~java
import java.math.BigDecimal;

public record CustomerRow(
        String customerId,
        String customerName,
        BigDecimal monthlyFee
) {}
~~~

### 3.1. Tệp CSV

Nội dung `customers.csv` (UTF-8):

~~~csv
customer_id,customer_name,monthly_fee
C0001,"Nguyen, An",120000
C0002,Tran Binh,95000
C0003,Le Minh,150000
~~~

**Điểm cần chú ý:**

- Dòng đầu là **header**, không phải bản ghi khách hàng. Reader sẽ bỏ qua một dòng.
- `"Nguyen, An"` chứa dấu phẩy bên trong dấu nháy kép, nên vẫn là **một** trường.
- Tên cột trong header được người dùng định nghĩa; `DelimitedLineTokenizer` sẽ sử dụng danh sách tên nội bộ theo **vị trí**. Bỏ qua header **không tự kiểm tra** tên cột có đúng hay không.
- Những dòng có số cột không đủ hoặc nhiều hơn dự kiến sẽ bị coi là lỗi nếu tokenizer ở chế độ **strict**.

### 3.2. Tệp độ rộng cố định

Nội dung `customers.fw` **không có header** và mỗi dòng dài **35 ký tự**:

| Trường | Vị trí ký tự (bắt đầu từ 1) | Độ rộng | Cách biểu diễn |
| --- | ---: | ---: | --- |
| `customerId` | 1–5 | 5 | Căn trái |
| `customerName` | 6–25 | 20 | Căn trái, thêm khoảng trắng bên phải |
| `monthlyFee` | 26–35 | 10 | Số nguyên không âm, bổ sung số 0 bên trái |

Để tạo tệp chính xác, dùng đoạn Java sau (dữ liệu tên viết dạng ASCII để tránh nhầm giữa số byte và số ký tự):

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

public class FixedWidthSampleGenerator {

    public static void main(String[] args) throws Exception {
        String one = String.format(
                Locale.ROOT, "%-5s%-20s%010d",
                "C0001", "Nguyen, An", 120000);

        String two = String.format(
                Locale.ROOT, "%-5s%-20s%010d",
                "C0002", "Tran Binh", 95000);

        Files.write(
                Path.of("customers.fw"),
                List.of(one, two),
                StandardCharsets.UTF_8);
    }
}
~~~

Cả hai dòng `customers.fw` được tạo đều có đúng 35 ký tự. **Không có ký tự `|` hoặc dấu phẩy phân cách**; dấu phẩy nằm trong tên `Nguyen, An` chỉ là một ký tự nội dung.

Nếu một đối tác mô tả trường theo **số byte** thay vì vị trí ký tự, phải xét encoding trước khi dùng `FixedLengthTokenizer`. Ví dụ UTF-8 mã hóa một số ký tự tiếng Việt bằng nhiều byte; vị trí byte và vị trí ký tự không luôn giống nhau. Hãy thống nhất hợp đồng encoding và cách tính độ rộng với đối tác.

## 4. Chuỗi chuyển đổi: từ dòng văn bản thành CustomerRow

Spring Batch `FlatFileItemReader` đọc một `Resource` và chuyển từng bản ghi văn bản thành đối tượng. Các vai trò:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Resource` | Xác định tệp cần đọc (ví dụ `FileSystemResource`) |
| `FlatFileItemReader<CustomerRow>` | Quản lý mở/đóng tệp, đọc từng record, lưu trạng thái đọc phục vụ restart |
| `LineTokenizer` | Chia một dòng thành các trường |
| `DelimitedLineTokenizer` | Chia theo dấu phân cách, có quy tắc xử lý trường được trích dẫn |
| `FixedLengthTokenizer` | Chia theo các khoảng vị trí được khai báo |
| `FieldSet` | Biểu diễn tập giá trị đã tách theo tên hoặc chỉ số cột |
| `FieldSetMapper<CustomerRow>` | Đổi các giá trị đã tách thành đối tượng Java |
| `DefaultLineMapper<CustomerRow>` | Ghép tokenizer và field set mapper thành `LineMapper` |

~~~mermaid
flowchart TD
    A["Một record dạng String"] --> B["LineTokenizer"]
    B --> C["FieldSet gồm id, name, fee"]
    C --> D["FieldSetMapper"]
    D --> E["CustomerRow"]
    E --> F["ItemWriter"]
~~~

Với định dạng CSV và fixed-width, **chỉ tokenizer khác nhau**. Mapping từ `FieldSet` sang `CustomerRow` có thể dùng chung nếu tên các trường trong tokenizer đồng nhất.

### 4.1. Cấu hình tokenizer cho CSV

~~~java
DelimitedLineTokenizer csv = new DelimitedLineTokenizer();
csv.setDelimiter(",");
csv.setNames("customerId", "customerName", "monthlyFee");
csv.setStrict(true);
~~~

Trong ví dụ CSV, dấu nháy kép bao quanh tên chứa dấu phẩy giúp tokenizer nhận đúng ba trường. Không tự tách dòng bằng `line.split(",")`, vì cách đó làm sai những giá trị như `"Nguyen, An"`.

### 4.2. Cấu hình tokenizer cho fixed-width

~~~java
FixedLengthTokenizer fixed = new FixedLengthTokenizer();
fixed.setNames("customerId", "customerName", "monthlyFee");
fixed.setColumns(
        new Range(1, 5),
        new Range(6, 25),
        new Range(26, 35)
);
fixed.setStrict(true);
~~~

`Range(1, 5)` có **cả hai đầu mút** và chỉ số bắt đầu từ **1** theo Spring Batch. Khi bật strict, chiều dài record phải đáp ứng định dạng đã định; tệp thiếu/thừa ký tự có thể gây `IncorrectLineLengthException`. Nếu hợp đồng tệp có trường cuối không cố định chiều dài, cách thiết kế tokenizer phải được điều chỉnh theo hợp đồng đó.

### 4.3. Mapping kết quả đọc

~~~java
DefaultLineMapper<CustomerRow> mapper = new DefaultLineMapper<>();
mapper.setLineTokenizer(tokenizer);
mapper.setFieldSetMapper(fields -> new CustomerRow(
        fields.readString("customerId").trim(),
        fields.readString("customerName").trim(),
        new BigDecimal(fields.readString("monthlyFee").trim())
));
mapper.afterPropertiesSet();
~~~

Sau bước này, cả hai định dạng đều tạo ra đối tượng Java giống nhau:

~~~text
CustomerRow(
    customerId="C0001",
    customerName="Nguyen, An",
    monthlyFee=120000
)
~~~

**Chuyển đổi dữ liệu khác với kiểm tra nghiệp vụ.** `BigDecimal` từ chuỗi không hợp lệ sẽ ném lỗi parse; các quy tắc như “mã đủ 5 ký tự”, “tên không rỗng” và “phí không âm” nên được kiểm tra thêm trong mapper hoặc `ItemProcessor`. Khi file có nhiều định dạng ngày/số tiền theo locale, hãy khai báo quy tắc rõ ràng thay vì dựa vào locale mặc định.

## 5. Cấu hình đầy đủ một Job có một Step

Ví dụ tiếp theo dùng **Spring Batch 5.x**; Spring Boot tự cung cấp cấu hình Batch khi dùng starter và không chủ động vô hiệu hóa auto-configuration. Chúng ta tạo **một bean Job, một bean Step**, và tạo reader theo `JobParameters` của lần chạy.

### 5.1. Dependency chính

Ví dụ Maven với phiên bản do BOM của Spring Boot và Spring Cloud tương thích quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-task-batch</artifactId>
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
~~~

`spring-cloud-task-batch` hữu ích khi muốn **liên kết lịch sử Batch job với task execution**; các chức năng đọc tệp cơ bản thuộc Spring Batch. Không tự thêm `@EnableBatchProcessing` nếu đang dựa trên cơ chế auto-configuration Spring Boot, vì annotation đó có thể thay đổi những phần Spring Boot tự cấu hình. Nếu dự án chủ động tự cấu hình Batch, cần thống nhất toàn bộ `JobRepository`, `JobLauncher` và transaction manager.

### 5.2. Ứng dụng Spring Boot Task

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class CustomerFileTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerFileTaskApplication.class, args);
    }
}
~~~

Ứng dụng chỉ cần một job được Spring Boot tự khởi chạy. Không thêm một `ApplicationRunner` khác tự gọi `JobLauncher.run(...)`, vì như vậy có thể **khởi chạy job hai lần**. Trong trường hợp có nhiều job, phải chỉ rõ job cần chạy hoặc quản lý launcher theo một cơ chế duy nhất.

### 5.3. Bean reader chọn tokenizer theo JobParameters

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FixedLengthTokenizer;
import org.springframework.batch.item.file.transform.LineTokenizer;
import org.springframework.batch.item.file.transform.Range;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class FileReaderConfiguration {

    @Bean
    @StepScope
    public FlatFileItemReader<CustomerRow> customerFileReader(
            @Value("#{jobParameters['inputFile']}") String inputFile,
            @Value("#{jobParameters['inputFormat']}") String inputFormat) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("Missing inputFile");
        }
        if (inputFormat == null) {
            throw new IllegalArgumentException("Missing inputFormat");
        }

        String format = inputFormat.toLowerCase(Locale.ROOT);
        LineTokenizer tokenizer;

        if ("csv".equals(format)) {
            DelimitedLineTokenizer csv = new DelimitedLineTokenizer();
            csv.setDelimiter(",");
            csv.setNames(
                    "customerId", "customerName", "monthlyFee");
            csv.setStrict(true);
            tokenizer = csv;
        }
        else if ("fixed".equals(format)) {
            FixedLengthTokenizer fixed = new FixedLengthTokenizer();
            fixed.setNames(
                    "customerId", "customerName", "monthlyFee");
            fixed.setColumns(
                    new Range(1, 5),
                    new Range(6, 25),
                    new Range(26, 35));
            fixed.setStrict(true);
            tokenizer = fixed;
        }
        else {
            throw new IllegalArgumentException(
                    "Supported formats: csv, fixed");
        }

        DefaultLineMapper<CustomerRow> mapper =
                new DefaultLineMapper<>();
        mapper.setLineTokenizer(tokenizer);
        mapper.setFieldSetMapper(fields -> new CustomerRow(
                fields.readString("customerId").trim(),
                fields.readString("customerName").trim(),
                new BigDecimal(
                        fields.readString("monthlyFee").trim())
        ));
        mapper.afterPropertiesSet();

        return new FlatFileItemReaderBuilder<CustomerRow>()
                .name("customerFileReader")
                .resource(new FileSystemResource(inputFile))
                .encoding("UTF-8")
                .linesToSkip("csv".equals(format) ? 1 : 0)
                .strict(true)
                .lineMapper(mapper)
                .saveState(true)
                .build();
    }
}
~~~

**Tại sao dùng `@StepScope`?** `inputFile` và `inputFormat` là **JobParameters** chỉ biết khi job được khởi chạy. Nếu tạo reader quá sớm ở singleton scope rồi lấy hai giá trị đó, chúng có thể chưa tồn tại. Step scope tạo reader đúng lúc step thực thi và giữ trạng thái cho lần chạy.

**Các lựa chọn cấu hình có chủ đích:**

- `.name("customerFileReader")` cấp tên ổn định để lưu các khóa trạng thái reader trong `ExecutionContext`.
- `.resource(new FileSystemResource(inputFile))` đọc tệp từ filesystem mà process nhìn thấy. Nếu chạy trong container, đường dẫn phải tồn tại **bên trong container**.
- `.encoding("UTF-8")` đặt rõ encoding của ví dụ.
- `.linesToSkip(1)` chỉ cho CSV vì tệp có header; fixed-width mẫu không có header.
- `.strict(true)` của reader khiến tệp không tồn tại trở thành lỗi thay vì im lặng chạy với dữ liệu rỗng. `setStrict(true)` của tokenizer kiểm tra số trường/độ rộng theo định dạng.
- `.saveState(true)` cho phép lưu trạng thái đọc trong `ExecutionContext` khi step commit, phục vụ restart.

**Lưu ý:** `linesToSkip(1)` không xác minh header có đúng tên và thứ tự không. Với dữ liệu quan trọng, hãy dùng `skippedLinesCallback` để xác nhận header kỳ vọng, và xử lý BOM/encoding có chủ đích nếu đối tác xuất tệp theo định dạng khác.

### 5.4. Tạo bảng kết quả và writer

Ví dụ dùng PostgreSQL, bảng đích:

~~~sql
CREATE TABLE import_customer (
    customer_id   VARCHAR(5) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    monthly_fee   NUMERIC(18, 2) NOT NULL
);
~~~

Một `ItemWriter<CustomerRow>` đơn giản sử dụng `JdbcTemplate`, trong transaction của chunk:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class CustomerWriterConfiguration {

    @Bean
    public ItemWriter<CustomerRow> customerWriter(JdbcTemplate jdbc) {
        return chunk -> {
            for (CustomerRow row : chunk) {
                jdbc.update("""
                    INSERT INTO import_customer
                        (customer_id, customer_name, monthly_fee)
                    VALUES (?, ?, ?)
                    ON CONFLICT (customer_id)
                    DO UPDATE SET
                        customer_name = EXCLUDED.customer_name,
                        monthly_fee = EXCLUDED.monthly_fee
                    """,
                    row.customerId(),
                    row.customerName(),
                    row.monthlyFee());
            }
        };
    }
}
~~~

`ON CONFLICT` giúp ghi lại một khách hàng theo cùng khóa mà không tạo hàng trùng; đó là **một ví dụ idempotency đơn giản**. Ở hệ thống thật, chỉ nên ghi đè khi chính sách nghiệp vụ cho phép. Nếu cần phân biệt dữ liệu từ các lần nhập khác nhau, khóa duy nhất nên bao gồm `sourceVersion` hoặc `importId` phù hợp. Nếu dữ liệu lớn, cân nhắc `JdbcBatchItemWriter` / batch update để giảm chi phí lệnh SQL từng hàng.

### 5.5. Ghép một Step và một Job

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class CustomerBatchJobConfiguration {

    @Bean
    public Step importCustomersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<CustomerRow> customerFileReader,
            ItemWriter<CustomerRow> customerWriter) {

        return new StepBuilder("importCustomersStep", jobRepository)
                .<CustomerRow, CustomerRow>chunk(50, transactionManager)
                .reader(customerFileReader)
                .writer(customerWriter)
                .build();
    }

    @Bean
    public Job importCustomerFileJob(
            JobRepository jobRepository,
            Step importCustomersStep) {

        return new JobBuilder("importCustomerFileJob", jobRepository)
                .start(importCustomersStep)
                .build();
    }
}
~~~

Đây là **Job một bước** dù có hai định dạng tệp: `inputFormat` chỉ chọn cách đọc; Job luôn gồm step `importCustomersStep`.

Với `chunk(50, transactionManager)`, framework thường đọc tối đa 50 item, chuyển cho writer, rồi commit. Trạng thái step/reader được lưu ở các điểm commit phù hợp để có thể restart. Điều kiện là JobRepository và transaction manager được cấu hình đáng tin cậy. Nếu database của metadata Batch khác database ghi kết quả, hai phạm vi commit có thể **không nguyên tử**; khi đó bắt buộc xem xét idempotency và khả năng ghi lại an toàn.

## 6. Cấu hình ứng dụng và cách khởi chạy

Ví dụ `application.yml` với PostgreSQL đã được tạo schema bằng migration:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://localhost:5432/task_batch_db
    username: import_task
    # Cấp SPRING_DATASOURCE_PASSWORD qua secret môi trường.
  batch:
    jdbc:
      initialize-schema: never
    job:
      enabled: true
  cloud:
    task:
      name: customer-file-import-task
      initialize-enabled: false
~~~

Cần có đầy đủ schema của **Spring Batch** (chẳng hạn `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION_CONTEXT`) và **Spring Cloud Task** (chẳng hạn `TASK_EXECUTION`) tương thích với version. `initialize-schema: never` và `initialize-enabled: false` chỉ nên dùng khi đã có schema đúng; nếu database trống, ứng dụng có thể không khởi động được job.

Spring Boot thường **tự chạy Job duy nhất** trong context khi bắt đầu ứng dụng, trừ khi bạn tắt chức năng này hoặc có cấu hình launcher riêng. Với trường hợp đã có một `Job`, không cần tự tạo scheduler bên trong task.

### 6.1. Chạy CSV

~~~bash
java -jar customer-import-task.jar inputFile=/data/customers.csv inputFormat=csv
~~~

### 6.2. Chạy fixed-width

~~~bash
java -jar customer-import-task.jar inputFile=/data/customers.fw inputFormat=fixed
~~~

**Phân biệt tham số Boot với JobParameters:** khi Spring Boot tự chạy Batch job, các tham số **không có tiền tố `--`** như `inputFile=...` được chuyển thành `JobParameters`. Ngược lại, `--spring.profiles.active=prod` là thuộc tính của môi trường Spring Boot, không phải tham số nghiệp vụ tự động truyền vào job.

Lệnh có thể phối hợp:

~~~bash
java -jar customer-import-task.jar \
  --spring.profiles.active=prod \
  inputFile=/data/customers.csv inputFormat=csv
~~~

Trên PowerShell, có thể đặt toàn bộ lệnh trên **một dòng**; cú pháp nối dòng bằng dấu gạch chéo ngược ở ví dụ trên dành cho shell Linux/macOS.

### 6.3. Cẩn thận với nhận diện JobInstance

Spring Batch phân biệt `JobInstance` theo **job name và các identifying JobParameters**. Nếu một JobInstance đã `COMPLETED`, việc gọi lại với **cùng bộ tham số định danh** có thể bị từ chối bằng `JobInstanceAlreadyCompleteException`.

Nếu muốn chạy một phiên bản đầu vào mới, dùng **JobParameters mô tả đúng phiên bản dữ liệu** (ví dụ source version hoặc run ID hợp lệ) thay vì xóa metadata Batch. Nếu muốn **restart một JobExecution FAILED**, thông thường chạy lại cùng identifying parameters và giữ nguyên tệp đầu vào; các giá trị non-identifying cũng cần được truyền lại khi sử dụng launcher dòng lệnh.

Trong demo, đường dẫn tệp và định dạng thường là identifying parameters. Nếu sử dụng cùng path nhưng **nội dung file đã đổi**, checkpoint Batch từ lần thất bại có thể không còn chỉ tới đúng bản ghi. Nên dùng file/snapshot **bất biến** hoặc checksum cùng version để bảo đảm restart đúng dữ liệu.

## 7. Kiểm chứng log và kết quả thực tế

Sau khi chạy một lần nhập CSV thành công, có thể đọc kết quả:

~~~sql
SELECT customer_id, customer_name, monthly_fee
FROM import_customer
ORDER BY customer_id;
~~~

Kỳ vọng với CSV mẫu: có ba khách hàng, trong đó `C0001` có tên `Nguyen, An` và phí `120000`.

Spring Batch lưu metadata từng lần chạy trong `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION`. Ví dụ:

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE, START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

~~~sql
SELECT STEP_EXECUTION_ID, STEP_NAME, STATUS,
       READ_COUNT, WRITE_COUNT, READ_SKIP_COUNT,
       PROCESS_SKIP_COUNT, WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID DESC;
~~~

Chỉ kiểm tra **`TaskRepository`** là chưa đủ để biết số item đã đọc/ghi vì các bộ đếm thuộc **Spring Batch StepExecution**. Với `spring-cloud-task-batch` và kết nối schema phù hợp, bảng liên kết `TASK_TASK_BATCH` có thể hỗ trợ truy từ TaskExecution sang JobExecution:

~~~sql
SELECT TASK_EXECUTION_ID, JOB_EXECUTION_ID
FROM TASK_TASK_BATCH
ORDER BY TASK_EXECUTION_ID DESC;
~~~

**Cần đọc cùng lúc:** exit code của tiến trình, trạng thái job/step trong JobRepository, bản ghi TaskExecution và dữ liệu khách hàng thực tế. Một chuỗi log “Started” không tự chứng minh đã nhập đủ file; một mã thoát bằng 0 cũng không thay việc kiểm tra điều kiện nghiệp vụ.

## 8. Xử lý tệp lỗi và chọn chính sách skip

Các lỗi thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| CSV có 4 cột thay vì 3 | Dấu phẩy chưa được trích dẫn đúng hoặc tệp sai schema | Kiểm tra dòng nguồn và quy tắc quoting |
| CSV có dấu xuống dòng trong trường được trích dẫn | Bản ghi trải nhiều dòng, reader cần chính sách record separator phù hợp | Cấu hình `RecordSeparatorPolicy` hoặc dùng parser xử lý đa dòng theo hợp đồng |
| Fixed-width thiếu 2 ký tự | Record không đủ 35 vị trí | Báo lỗi định dạng; không tự dịch ranh giới |
| Phí không phải số | Lỗi parse `BigDecimal` hoặc định dạng locale | Xác định chuẩn decimal/currency; thông báo dòng lỗi |
| Ký tự tiếng Việt bị sai | Encoding nguồn khác UTF-8 hoặc có BOM | Kiểm tra charset, BOM, quy tắc byte/character width |
| Không tìm thấy tệp | Path bên trong container sai, chưa mount volume | Kiểm tra `Resource`, quyền đọc, đường dẫn tuyệt đối |
| Job chạy lại bị từ chối | Cùng JobInstance đã hoàn tất | Xác định đang restart FAILED hay chạy dữ liệu mới |
| Retry đọc lại dòng sai | File thay đổi hoặc trạng thái reader/JobRepository không bền vững | Cố định đầu vào, bảo đảm `saveState` và schema Batch đúng |

### 8.1. Thất bại hay bỏ qua dòng lỗi?

Ở ví dụ cơ bản, **lỗi parse sẽ làm step thất bại**. Đây là lựa chọn tốt khi file nhỏ hoặc hợp đồng dữ liệu chặt: dữ liệu sai cần được sửa rồi chạy lại.

Nếu nghiệp vụ cho phép bỏ qua tối đa một số dòng sai đã được xác định rõ, Spring Batch hỗ trợ `faultTolerant()` với `skipLimit(...)` và `skip(...)`. Ví dụ **chỉ minh họa phần cấu hình step thay thế**:

~~~java
return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerRow, CustomerRow>chunk(50, transactionManager)
        .reader(customerFileReader)
        .writer(customerWriter)
        .faultTolerant()
        .skipLimit(3)
        .skip(org.springframework.batch.item.file.FlatFileParseException.class)
        .build();
~~~

**Đừng tự động skip mọi exception.** Nếu bỏ qua dòng lỗi, cần ghi nhận **số dòng, lý do và đường dẫn/quy trình xử lý dữ liệu bị loại** để có thể đối soát. `READ_SKIP_COUNT` trong Batch giúp đếm nhưng không thay thế báo cáo lỗi chi tiết. Không dùng skip cho lỗi hệ thống như database mất kết nối hoặc lỗi ghi kết quả nếu chúng có thể dẫn đến dữ liệu thiếu.

### 8.2. Header phải được kiểm tra, không chỉ bỏ qua

`linesToSkip(1)` đơn thuần bỏ qua dòng đầu. Nếu đối tác đổi thứ tự cột trong CSV, reader vẫn ánh xạ theo thứ tự đã khai báo và **có thể đọc nhầm dữ liệu**.

Ví dụ kiểm tra header khi tạo reader CSV:

~~~java
// Bổ sung vào FlatFileItemReaderBuilder cho định dạng csv:
.skippedLinesCallback(line -> {
    if (!line.equals("customer_id,customer_name,monthly_fee")) {
        throw new IllegalArgumentException(
                "Unexpected CSV header: " + line);
    }
})
~~~

Chỉ áp dụng callback này cho CSV có header như hợp đồng, không áp dụng cho fixed-width không có header. Với CSV thực tế có BOM, hãy xử lý BOM đúng quy tắc trước khi so sánh.

## 9. Restart sau khi một chunk thất bại

Giả sử CSV có 250 item, chunk size là 50:

1. Step đọc/ghi 50 item đầu và **commit**.
2. Step tiếp tục xử lý chunk 51–100, nhưng gặp lỗi ở dòng thứ 80.
3. Nếu lỗi gây rollback chunk, kết quả từ chunk 51–100 **chưa được commit**.
4. `JobRepository` lưu metadata step và `ExecutionContext` ở các điểm commit thích hợp. Khi restart cùng JobInstance, reader có thể khôi phục vị trí sau chunk đã commit.
5. Nếu file giữ nguyên và writer có idempotency thích hợp, step có thể tiếp tục mà không tạo kết quả trùng.

**Tính chất quan trọng của `FlatFileItemReader`:** đây là thành phần `ItemStream` có khả năng lưu trạng thái khi `saveState(true)` và có tên ổn định. Việc mở lại reader ở lần restart phụ thuộc `ExecutionContext` của Spring Batch, **không phụ thuộc** `TASK_EXECUTION_ID` của Spring Cloud Task.

~~~mermaid
flowchart TD
    A["JobExecution #1: bắt đầu đọc CSV"] --> B["Commit chunk 1–50"]
    B --> C["Lỗi trong chunk 51–100"]
    C --> D["JobExecution FAILED"]
    D --> E["JobExecution #2: restart cùng JobInstance"]
    E --> F["Đọc checkpoint đã commit từ ExecutionContext"]
    F --> G["Xử lý từ ranh giới an toàn"]
    G --> H["COMPLETED"]
~~~

**Điều kiện restart an toàn:**

- File đầu vào **không đổi** giữa hai lần chạy cùng JobInstance, kể cả thứ tự dòng và header.
- `JobRepository` và `ExecutionContext` được lưu ở database bền vững.
- Reader và Step giữ **tên phù hợp** để nạp trạng thái đã lưu.
- Writer có transaction và chính sách idempotent khi cần, nhất là khi dữ liệu nghiệp vụ và metadata Batch không ở cùng transaction resource.
- Không kết thúc `ApplicationRunner` sớm trong khi Batch job vẫn chạy bất đồng bộ rồi coi TaskExecution là kết quả của toàn bộ import.

Nếu cần đối soát theo từng bản ghi, retry phức tạp, partition hoặc nhiều bước, cần tiếp tục nghiên cứu các cơ chế checkpoint, skip và restart của Spring Batch. Với bài này, một `Job` một `Step` đủ để minh họa cách đọc và nhập tệp hữu hạn.

## 10. CSV và fixed-width: chọn thế nào?

| Tiêu chí | CSV | Tệp độ rộng cố định |
| --- | --- | --- |
| Cách phân trường | Dấu phân cách và quoting | Vị trí ký tự đã định trước |
| Schema | Header tùy chọn; số cột có thể kiểm tra | Quy định chính xác thứ tự và độ rộng |
| Giá trị chứa dấu phẩy | Có thể trích dẫn bằng dấu nháy kép | Dấu phẩy là nội dung bình thường |
| Dữ liệu thiếu | Có thể là trường rỗng, cần validate | Có thể gây sai độ dài hoặc đệm khoảng trắng |
| Khó khăn thường gặp | Quote escape, delimiter, dấu xuống dòng trong trường, encoding | Padding, ranh giới trường, ký tự nhiều byte, độ dài thực tế |
| Tokenizer Spring Batch | `DelimitedLineTokenizer` | `FixedLengthTokenizer` |
| Phù hợp | Dữ liệu xuất nhập thông dụng và tích hợp dễ đọc | Hệ thống legacy, chuẩn đối tác cố định về layout |

Cả hai đều có thể xử lý bằng **`FlatFileItemReader`**; chọn tokenizer theo **hợp đồng nguồn**, không theo phần mở rộng tên file. Nếu file có nhiều loại record, ví dụ dòng header, detail và trailer khác schema, cần cơ chế nhận diện loại record như `PatternMatchingCompositeLineMapper` hoặc tách thành các bước có kiểm soát.

## 11. Bài thực hành tự kiểm tra

### Thực hành A — CSV

Tạo `customers.csv` như ví dụ đầu bài rồi chạy job với `inputFormat=csv`. Xác nhận:

- Đọc được ba item; dòng header không tính là item.
- Tên `"Nguyen, An"` được ánh xạ thành một chuỗi chứa dấu phẩy.
- Bảng `import_customer` có ba dòng và phí được lưu đúng.
- StepExecution có `READ_COUNT=3` và `WRITE_COUNT=3` khi không có skip hoặc lọc item.

### Thực hành B — Fixed-width

Chạy chương trình tạo tệp `customers.fw` rồi gọi job với `inputFormat=fixed`. Xác nhận:

- Reader không bỏ qua dòng đầu vì file không có header.
- Ba khoảng 1–5, 6–25, 26–35 được phân đúng.
- Hai item được ghi; nếu chạy trên cùng bảng, các khách hàng trùng ID được **cập nhật**, không tạo thêm ID trùng.
- Khi sửa một dòng thành 34 ký tự, job phải phát hiện lỗi nếu tokenizer strict.

### Thực hành C — Khởi động lại

Tạo file 120 bản ghi và gây lỗi có kiểm soát trong một chunk sau chunk đầu đã commit. Dùng lại **cùng identifying JobParameters** và **tệp bất biến** để restart. Xác nhận số bản ghi cuối đúng, không bị tăng thêm do tác động trùng, và metadata Batch thể hiện một JobInstance với nhiều JobExecution khi restart phù hợp.

### Checklist hoàn thành bài

- [ ] Phân biệt `TaskRepository` và `JobRepository`.
- [ ] Biết sự khác nhau giữa `DelimitedLineTokenizer` và `FixedLengthTokenizer`.
- [ ] Đã xác định encoding, header, schema, quoting và độ rộng theo hợp đồng nguồn.
- [ ] Dùng `@StepScope` để nhận `inputFile`, `inputFormat` khi job khởi chạy.
- [ ] Job chỉ có **một Step**, reader thay đổi theo format của lần chạy.
- [ ] Đã kiểm tra lỗi số cột CSV và lỗi độ dài fixed-width.
- [ ] Không trộn tham số Spring Boot `--...` với Batch JobParameters `name=value`.
- [ ] Đã đọc `READ_COUNT`, `WRITE_COUNT` và các skip count từ `BATCH_STEP_EXECUTION`.
- [ ] File bất biến khi restart và reader lưu trạng thái `ExecutionContext`.
- [ ] Writer có transaction và chiến lược idempotency phù hợp.
- [ ] Không ghi secret vào JobParameters, TaskRepository hoặc log.
- [ ] Có cách kiểm tra kết quả nghiệp vụ trước khi coi job đã thành công.

## 12. Ghi nhớ

**Một Spring Batch Job một bước** có thể đọc cả CSV và tệp độ rộng cố định bằng cùng một luồng xử lý. `FlatFileItemReader` phụ trách đọc record; `DelimitedLineTokenizer` và `FixedLengthTokenizer` xác định cách tách trường; `FieldSetMapper` chuyển dữ liệu thành đối tượng; `ItemWriter` ghi kết quả. `JobRepository` quản lý tiến độ và restart của Step, còn **Spring Cloud Task TaskRepository** theo dõi vòng đời của ứng dụng khởi chạy job.

Khi vận hành, bảo đảm **hợp đồng tệp rõ ràng**, tệp đầu vào **ổn định giữa các lần restart**, dữ liệu lỗi được xử lý theo chính sách và kết quả ghi có **tính nhất quán/idempotent**. Những điều này quan trọng hơn việc chỉ nhìn thấy log “Job completed”.

### Tài liệu tham khảo

- [Spring Batch 5.2 — FlatFileItemReader, CSV và fixed-length](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch 5.2 — Configuring a Chunk-Oriented Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html)
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html)
- [Spring Boot — Running Batch Jobs from the Command Line](https://docs.spring.io/spring-boot/how-to/batch.html)
- [Spring Cloud Task — Spring Batch integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
