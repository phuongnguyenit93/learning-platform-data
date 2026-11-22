# Không ghép chuỗi expression quá phức tạp

Trong Spring Batch, `@StepScope` và `@JobScope` thường dùng SpEL để lấy giá trị từ `JobParameters`, `ExecutionContext` hoặc metadata của execution. Những expression ngắn như `#{jobParameters['input.file']}` rất hữu ích vì chúng thể hiện rõ bean cần nhận giá trị nào khi step hoặc job bắt đầu.

Khi expression bắt đầu chứa nhiều phép nối chuỗi, nested ternary, điều kiện lồng nhau, chuyển kiểu hoặc truy cập nhiều nguồn dữ liệu, cấu hình trở nên khó đọc và khó kiểm thử. SpEL khi đó đang gánh logic nghiệp vụ mà Java code hoặc một thành phần chuyên trách có thể biểu diễn rõ ràng hơn.

Nguyên tắc nên áp dụng là giữ expression ở mức tra cứu và giá trị mặc định đơn giản. Hãy chuyển việc phân tích, chuẩn hóa, ghép đường dẫn, chọn strategy và xác thực tham số sang Java method, factory hoặc validator có thể kiểm thử độc lập.

## 1. Parameter injection trong Spring Batch

Parameter injection cho phép một scoped bean nhận giá trị chỉ có khi job được launch. Ví dụ, reader cần tên file được truyền trong `JobParameters`, hoặc worker cần khoảng ID được đặt trong `StepExecution` context.

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .resource(new FileSystemResource(inputFile))
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(OrderRow.class)
        .build();
}
```

Expression `#{jobParameters['input.file']}` chỉ truy cập một key. Nó dễ hiểu, dễ kiểm tra và không cần người đọc phải mô phỏng nhiều bước đánh giá SpEL.

Giá trị được resolve khi scoped target được tạo trong scope đang hoạt động. Vì vậy, bean cần late binding thường được khai báo với `@StepScope` hoặc `@JobScope`; một singleton thông thường không thể nhận giá trị riêng cho từng JobExecution bằng cách đọc JobParameters tại thời điểm startup.

## 2. Khi nào expression trở nên quá phức tạp?

Expression có thể trở nên khó bảo trì khi chứa một hoặc nhiều đặc điểm sau:

- Nhiều phép nối chuỗi để tạo path, URL, tên file hoặc câu query.
- Nhiều toán tử điều kiện lồng nhau (`?:`) để chọn mode hoặc strategy.
- Kiểm tra null, giá trị rỗng, format và default ở nhiều tầng.
- Chuyển đổi enum, ngày giờ, số hoặc collection ngay trong annotation.
- Đọc nhiều key từ JobParameters và ExecutionContext rồi kết hợp chúng.
- Gọi method của bean để thực hiện logic nghiệp vụ.
- Biểu diễn quy tắc phân quyền hoặc lựa chọn dữ liệu trong một chuỗi khó đọc.

Ví dụ expression khó bảo trì:

```java
@Value("#{jobParameters['mode'] == 'FULL' ?
    (jobParameters['region'] == 'ALL' ?
        jobParameters['baseDir'] + '/full/all-' + jobParameters['date'] + '.csv' :
        jobParameters['baseDir'] + '/full/' + jobParameters['region'] + '-' + jobParameters['date'] + '.csv') :
    jobParameters['baseDir'] + '/delta/' + jobParameters['region'] + '-' + jobParameters['date'] + '.csv'}")
String inputFile
```

Người đọc phải hiểu cấu trúc điều kiện, quy tắc đặt tên file, cách xử lý region và mode ngay bên trong annotation. Khi quy tắc thay đổi, expression dễ bị sửa sai dấu ngoặc hoặc tạo ra path không hợp lệ.

Thay vì mở rộng expression, hãy inject từng giá trị đơn giản rồi xử lý bằng Java.

## 3. Giữ SpEL ở mức truy cập một giá trị

Những expression thường dễ đọc và phù hợp cho parameter injection:

| Nhu cầu | Expression đơn giản |
|---|---|
| Lấy input file | `#{jobParameters['input.file']}` |
| Lấy ngày nghiệp vụ | `#{jobParameters['businessDate']}` |
| Lấy tenant | `#{jobParameters['tenantId']}` |
| Lấy khóa bắt đầu của partition | `#{stepExecutionContext['minId']}` |
| Lấy watermark đã lưu ở cấp job | `#{jobExecutionContext['watermark']}` |
| Lấy tên step hiện tại | `#{stepExecution.stepName}` |

Các expression trên thể hiện nguồn của dữ liệu và giữ logic xử lý bên ngoài cấu hình. Nếu cần default đơn giản, có thể dùng toán tử Elvis của SpEL:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['delimiter'] ?: ','}") String delimiter) {
    return new OrderReader(delimiter);
}
```

Chỉ dùng default trong expression khi quy tắc thật sự đơn giản và giá trị mặc định hợp lệ về nghiệp vụ. Với tham số bắt buộc, nên báo lỗi rõ ràng qua validator thay vì âm thầm thay bằng một giá trị mặc định.

## 4. Chuyển logic tạo cấu hình sang Java

Ví dụ sau tách việc đọc parameters khỏi việc tạo options. Scoped bean chỉ inject các giá trị thô; factory thực hiện chuẩn hóa và kiểm tra quy tắc.

```java
public record ImportOptions(
        Path inputPath,
        ImportMode mode,
        int pageSize,
        String region) {
}

public enum ImportMode {
    FULL,
    INCREMENTAL
}

@Component
public class ImportOptionsFactory {

    public ImportOptions create(
            String inputFile,
            String modeValue,
            Integer pageSizeValue,
            String regionValue) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("input.file is required");
        }

        ImportMode mode = ImportMode.valueOf(
            modeValue == null ? "INCREMENTAL" : modeValue.toUpperCase(Locale.ROOT));

        int pageSize = pageSizeValue == null ? 500 : pageSizeValue;
        if (pageSize < 1 || pageSize > 5000) {
            throw new IllegalArgumentException("pageSize must be between 1 and 5000");
        }

        String region = regionValue == null || regionValue.isBlank()
            ? "GLOBAL"
            : regionValue.trim().toUpperCase(Locale.ROOT);

        return new ImportOptions(
            Path.of(inputFile).normalize(), mode, pageSize, region);
    }
}
```

Scoped reader nhận các tham số riêng rẽ và gọi factory:

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['mode']}") String mode,
        @Value("#{jobParameters['pageSize']}") Integer pageSize,
        @Value("#{jobParameters['region']}") String region,
        ImportOptionsFactory optionsFactory) {

    ImportOptions options =
        optionsFactory.create(inputFile, mode, pageSize, region);

    return new FlatFileItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .resource(new FileSystemResource(options.inputPath().toFile()))
        .delimited()
        .delimiter(";")
        .names("orderId", "customerId", "amount")
        .targetType(OrderRow.class)
        .build();
}
```

Trong ứng dụng thực tế, nếu delimiter cũng là một option thì truyền nó vào `ImportOptions` và builder. Điểm chính là việc parse enum, chuẩn hóa region, kiểm tra page size và tạo `Path` nằm trong Java, nơi IDE hỗ trợ refactor và unit test.

## 5. Dùng JobParametersValidator cho dữ liệu đầu vào

Không nên nhét validation phức tạp vào SpEL. Job parameters nên được xác thực trước khi các step thực hiện công việc. Spring Batch hỗ trợ `JobParametersValidator` để kiểm tra tham số ở cấp job.

Ví dụ dùng validator mặc định để yêu cầu một số key:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
        new String[] { "input.file", "businessDate" },
        new String[] { "requestedBy", "traceId" }
    );
}
```

Đăng ký validator trên job:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importOrdersJob", jobRepository)
        .validator(importParametersValidator)
        .start(importOrdersStep)
        .build();
}
```

Nếu cần kiểm tra format ngày, giới hạn page size, quan hệ giữa `fromDate` và `toDate` hoặc quy tắc theo tenant, hãy viết validator tùy chỉnh. Validator có thể dùng Java `LocalDate`, enum và service nghiệp vụ; không cần biểu diễn các quy tắc đó thành SpEL.

## 6. Ví dụ validator tùy chỉnh

```java
public class ImportParametersValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("input.file");
        String businessDate = parameters.getString("businessDate");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException("input.file is required");
        }

        if (businessDate == null) {
            throw new JobParametersInvalidException("businessDate is required");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                "businessDate must use ISO-8601 format");
        }
    }
}
```

Validator chạy trước khi job đi vào các step, giúp lỗi tham số được báo ở đúng ranh giới. Không cần để reader bắt đầu mở file rồi mới phát hiện ngày nghiệp vụ không hợp lệ.

## 7. Phân biệt SpEL #{...} và placeholder ${...}

Trong `@Value`, hai cú pháp này thường xuất hiện cạnh nhau nhưng có mục đích khác nhau:

| Cú pháp | Nguồn giá trị thường dùng | Ví dụ |
|---|---|---|
| `#{...}` | Spring Expression Language, có thể truy cập JobParameters, ExecutionContext và bean | `#{jobParameters['input.file']}` |
| `${...}` | Property placeholder từ application properties, environment hoặc property source | `${batch.import.default-page-size:500}` |

Ví dụ, giá trị mặc định của ứng dụng có thể nằm trong `application.yml`:

```yaml
batch:
  import:
    default-page-size: 500
    archive-directory: /var/batch/archive
```

Scoped bean có thể nhận cả parameter của job và property cấu hình ứng dụng:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("${batch.import.default-page-size:500}") Integer defaultPageSize) {

    return new OrderReader(inputFile, defaultPageSize);
}
```

`input.file` thay đổi theo JobExecution; `defaultPageSize` là cấu hình triển khai của ứng dụng. Không dùng JobParameters cho mọi giá trị cấu hình tĩnh, và không dùng property placeholder để giả lập tham số riêng của từng lần chạy.

## 8. Không ghép path hoặc URL bằng SpEL

Việc nối chuỗi path trong expression dễ gây lỗi dấu phân cách, xử lý đường dẫn Windows/Linux không nhất quán và khó áp dụng kiểm tra bảo mật. Hãy dùng API Java phù hợp.

Không nên:

```java
@Value("#{jobParameters['baseDir'] + '/' + jobParameters['fileName']}")
String path
```

Nên inject hai giá trị riêng rồi dùng `Path.resolve`:

```java
@Bean
@StepScope
FileSystemResource inputResource(
        @Value("#{jobParameters['baseDir']}") String baseDir,
        @Value("#{jobParameters['fileName']}") String fileName) {

    Path path = Path.of(baseDir).resolve(fileName).normalize();
    return new FileSystemResource(path);
}
```

Trong code production, nếu `fileName` đến từ người gọi bên ngoài, cần xác nhận nó không thoát khỏi thư mục được phép bằng path traversal. Có thể resolve base directory thành absolute path rồi kiểm tra `path.startsWith(base)` trước khi mở file.

Đối với URL, dùng `URI`/`UriComponentsBuilder` và các thành phần đã được encode đúng thay vì nối chuỗi trong SpEL.

## 9. Không dùng nested ternary để chọn business mode

Nested ternary trong SpEL khiến biểu thức khó đọc, đặc biệt khi có nhiều chế độ nhập:

```java
@Value("#{jobParameters['mode'] == 'FULL' ?
    (jobParameters['region'] == 'NORTH' ? 'N1' :
        (jobParameters['region'] == 'SOUTH' ? 'S1' : 'ALL')) : 'DELTA'}")
String route
```

Thay vào đó, chuyển lựa chọn sang Java:

```java
public ImportRoute resolveRoute(ImportMode mode, Region region) {
    if (mode == ImportMode.FULL && region == Region.NORTH) {
        return ImportRoute.FULL_NORTH;
    }
    if (mode == ImportMode.FULL && region == Region.SOUTH) {
        return ImportRoute.FULL_SOUTH;
    }
    if (mode == ImportMode.FULL) {
        return ImportRoute.FULL_ALL;
    }
    return ImportRoute.DELTA;
}
```

Logic Java có thể dùng enum, switch expression hoặc strategy pattern. Có thể viết unit test cho mọi tổ hợp mode/region mà không cần khởi chạy Spring context.

## 10. Dùng resolver hoặc factory khi nhiều bean cần cùng quy tắc

Nếu reader, writer và tasklet đều cần cách chuẩn hóa cùng một parameter, không sao chép expression hoặc logic ở nhiều bean. Tạo một resolver/factory dùng chung.

```java
@Component
public class BatchParameterResolver {

    public LocalDate requiredBusinessDate(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }
        return LocalDate.parse(value);
    }

    public Path requiredInputPath(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("input.file is required");
        }
        return Path.of(value).toAbsolutePath().normalize();
    }
}
```

Scoped bean inject giá trị đơn giản rồi gọi resolver:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        BatchParameterResolver resolver) {

    Path path = resolver.requiredInputPath(inputFile);
    LocalDate date = resolver.requiredBusinessDate(businessDate);
    return new OrderReader(path, date);
}
```

Resolver nên là stateless singleton nếu chỉ thực hiện chuyển đổi/validation thuần. Không lưu JobParameters hoặc state của execution vào field mutable của resolver.

## 11. Inject kiểu dữ liệu phù hợp

Không nên biến mọi parameter thành String rồi parse thủ công trong SpEL. Spring có cơ chế chuyển đổi kiểu cho các giá trị inject được hỗ trợ; cũng có thể truyền JobParameters với kiểu dữ liệu phù hợp ngay từ lúc launch.

Ví dụ tạo typed parameters:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("input.file", "data/orders.csv", true)
    .addLong("pageSize", 500L, false)
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();
```

Inject giá trị vào scoped bean:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['pageSize']}") Long pageSize) {

    int effectivePageSize = pageSize == null ? 500 : Math.toIntExact(pageSize);
    return new OrderReader(Path.of(inputFile), effectivePageSize);
}
```

Chọn kiểu Java phù hợp với kiểu JobParameter đã tạo. Nếu cần default hoặc kiểm tra range, xử lý trong Java hoặc validator. Việc dùng `Long` thay vì `long` cũng cho phép biểu diễn key không được cung cấp bằng `null`, tùy conversion và cấu hình.

## 12. Giữ expression độc lập với business logic

SpEL phù hợp để lấy dữ liệu từ context hoặc gọi một bean method đơn giản trong một số trường hợp, nhưng gọi service phức tạp từ expression làm dependency khó nhìn thấy và khó kiểm thử.

Không nên để expression thực hiện truy vấn database, gọi HTTP, phân quyền hoặc chọn workflow nghiệp vụ. Những hành động đó có thể chạy vào thời điểm target được tạo, khiến thời điểm side effect khó nhận ra và lỗi khó chẩn đoán.

Nếu cần tra cứu dữ liệu, hãy inject service vào scoped bean và gọi nó trong một method có tên rõ ràng, hoặc thực hiện trong tasklet/processor phù hợp với lifecycle. Cấu hình bean nên cho thấy rõ dependency qua constructor hoặc method parameters.

## 13. Khi nào dùng JobScope và StepScope cho parameter injection?

Chọn scope theo phạm vi của dữ liệu và state:

| Scope | Phù hợp khi | Ví dụ |
|---|---|---|
| `@StepScope` | Giá trị hoặc state riêng của một StepExecution | Reader nhận `minId`, `maxId`, file path hoặc cursor |
| `@JobScope` | Giá trị dùng chung trong một JobExecution | Policy hoặc tên output chung cho các step tuần tự |
| Singleton | Cấu hình tĩnh, stateless và dùng chung toàn ứng dụng | Resolver, validator hoặc factory thuần |

Không đưa mutable state riêng của một worker vào singleton. Với partitioning, `stepExecutionContext` kết hợp `@StepScope` thường là cách rõ ràng để mỗi worker nhận tham số riêng.

## 14. Default đơn giản và tham số bắt buộc

SpEL có thể dùng default đơn giản, nhưng cần phân biệt hai tình huống:

- Tham số tùy chọn có default hợp lệ: dùng Elvis operator hoặc xử lý null trong Java.
- Tham số bắt buộc: xác thực và báo lỗi rõ ràng trước khi step bắt đầu.

Ví dụ tham số tùy chọn:

```java
@Value("#{jobParameters['delimiter'] ?: ','}") String delimiter
```

Ví dụ tham số bắt buộc nên được kiểm tra bằng validator thay vì lồng nhiều toán tử để trả về một chuỗi lỗi hoặc giá trị thay thế:

```java
if (parameters.getString("input.file") == null) {
    throw new JobParametersInvalidException("input.file is required");
}
```

Không dùng default để âm thầm biến một parameter thiếu thành phạm vi dữ liệu rộng hơn, ví dụ mặc định `tenantId` thành `ALL`, trừ khi đó là quy tắc nghiệp vụ được xác định và được phép.

## 15. Kiểm thử parameter injection

Kiểm thử nên xác nhận cả việc resolve expression lẫn logic Java được gọi sau khi inject.

Các trường hợp hữu ích:

1. JobParameters hợp lệ tạo reader với đúng file và option.
2. Parameter tùy chọn không có mặt nhận default đã định nghĩa.
3. Parameter bắt buộc bị thiếu làm validator từ chối job trước khi đọc dữ liệu.
4. Giá trị enum không hợp lệ được báo bằng lỗi tham số rõ ràng.
5. Hai JobExecution với input khác nhau nhận target scoped riêng.
6. Hai partition nhận các giá trị riêng từ StepExecution context.
7. Restart cùng JobInstance dùng lại identifying parameters và checkpoint mong đợi.
8. Thay đổi message hoặc cách viết Java không ảnh hưởng đến SpEL lookup.

Unit test cho factory/resolver có thể kiểm tra path, enum, ngày, default và giới hạn số. Integration test với JobRepository và scope thật xác nhận late binding hoạt động khi step bắt đầu.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nested ternary trong `@Value` | Expression khó đọc và dễ sai khi sửa | Chuyển lựa chọn sang Java method hoặc strategy |
| Ghép path/URL bằng SpEL | Sai dấu phân cách, encoding hoặc xử lý path không an toàn | Dùng `Path`, `URI` hoặc builder chuyên dụng |
| Parse enum/ngày/số trong expression | Lỗi conversion khó chẩn đoán | Inject giá trị thô rồi parse trong factory/validator |
| Dùng SpEL để validate nhiều parameter | Quy tắc nghiệp vụ bị giấu trong annotation | Dùng `JobParametersValidator` |
| Gọi service phức tạp từ expression | Dependency và side effect khó nhận biết | Inject service rõ ràng và gọi từ Java |
| Dùng `${...}` cho JobParameters | Nhầm property cấu hình với dữ liệu từng execution | Dùng `#{jobParameters[...]}` |
| Dùng `#{...}` cho cấu hình tĩnh của ứng dụng | Cấu hình bị gắn sai nguồn | Dùng property placeholder hoặc `@ConfigurationProperties` |
| Default cho parameter bắt buộc | Job có thể chạy với phạm vi sai | Validate và fail sớm |
| Inject JobParameters vào singleton | Không có giá trị riêng cho từng execution | Dùng scoped bean/proxy |
| Lặp cùng expression ở nhiều bean | Quy tắc bị lệch khi thay đổi | Dùng factory/resolver dùng chung |

## 17. Quy trình thiết kế expression dễ bảo trì

Khi khai báo một scoped bean, hãy làm theo trình tự:

1. Xác định giá trị lấy từ JobParameters, Step ExecutionContext, Job ExecutionContext hay application properties.
2. Dùng một expression ngắn để lấy từng giá trị.
3. Xác định parameter nào bắt buộc và parameter nào có default hợp lệ.
4. Đưa parse, chuẩn hóa, kết hợp giá trị và business rule vào Java.
5. Dùng `JobParametersValidator` cho điều kiện cần kiểm tra trước khi step chạy.
6. Dùng factory/resolver nếu nhiều bean cần cùng quy tắc chuyển đổi.
7. Chọn `@StepScope` hoặc `@JobScope` theo vòng đời target cần thiết.
8. Viết unit test cho Java logic và integration test cho late binding.

Expression nên ngắn đến mức người đọc có thể hiểu nguồn dữ liệu mà không phải giải mã cả một thuật toán.

## Kết luận

Không ghép chuỗi SpEL quá phức tạp trong `@Value` của Spring Batch. Giữ expression ở mức tra cứu đơn giản như `#{jobParameters['input.file']}` hoặc `#{stepExecutionContext['minId']}`; chuyển việc ghép path, parse enum/ngày, chọn mode, áp dụng default phức tạp và validation sang Java factory, resolver hoặc `JobParametersValidator`.

Cách tách này làm cấu hình reader/writer dễ đọc, business rule có thể unit test và lỗi tham số được phát hiện sớm. Hãy phân biệt `#{...}` cho SpEL với `${...}` cho application properties, dùng scoped bean để late-bind giá trị theo execution và không để expression trở thành nơi ẩn logic hoặc side effect.
