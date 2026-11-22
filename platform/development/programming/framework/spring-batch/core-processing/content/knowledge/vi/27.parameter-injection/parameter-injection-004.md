# Tên key và kiểu dữ liệu

Trong Spring Batch, JobParameters là tập hợp các tham số đầu vào được đặt tên cho một lần chạy Job. Mỗi tham số có một key, một value và một kiểu dữ liệu. Khi inject tham số vào reader, processor, writer hoặc Tasklet, tên key trong SpEL phải khớp với key đã tạo; kiểu dữ liệu của value cũng cần tương thích với kiểu Java mà bean nhận.

Đặt tên key rõ ràng và chọn kiểu dữ liệu phù hợp giúp Job dễ cấu hình, kiểm thử, vận hành và restart. Một key như `business.date` có thể biểu diễn ngày nghiệp vụ; `tenant.id` có thể là số nguyên; `input.file` có thể là đường dẫn tệp. Nếu dùng tên không nhất quán hoặc inject sai kiểu, Job có thể không khởi tạo được bean, parse sai dữ liệu hoặc vô tình tạo một JobInstance khác.

## 1. JobParameters gồm key, value và type

Mỗi JobParameter có ba thành phần quan trọng:

- **Key:** tên định danh của tham số, ví dụ `input.file`.
- **Value:** giá trị đầu vào, ví dụ `/data/orders.csv`.
- **Type:** kiểu Java của value, ví dụ `String`, `Long`, `Double` hoặc một kiểu được hỗ trợ bởi cơ chế conversion/serialization đã cấu hình.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/orders.csv", true)
        .addLong("tenant.id", 42L, true)
        .addString("business.date", "2026-11-15", true)
        .addString("requested.by", "scheduler", false)
        .toJobParameters();
```

Các tham số trên có key và kiểu như sau:

| Key | Value minh họa | Type | Identifying |
|---|---|---|---|
| `input.file` | `/data/orders.csv` | `String` | Có |
| `tenant.id` | `42` | `Long` | Có |
| `business.date` | `2026-11-15` | `String` | Có |
| `requested.by` | `scheduler` | `String` | Không |

Key dùng để truy cập giá trị trong JobParameters hoặc SpEL. Type xác định cách value được lưu, chuyển đổi và inject. Cờ identifying quyết định tham số có tham gia xác định JobInstance hay không.

## 2. Quy tắc đặt tên key

Tên key nên mô tả ý nghĩa nghiệp vụ hoặc kỹ thuật của giá trị. Người vận hành nhìn vào JobParameters phải hiểu tham số dùng để làm gì mà không cần đọc code.

Ví dụ tên rõ nghĩa:

| Nên dùng | Tránh dùng | Lý do |
|---|---|---|
| `input.file` | `f1` | Nói rõ đây là file đầu vào. |
| `business.date` | `date` | Phân biệt ngày nghiệp vụ với ngày hệ thống hoặc ngày tạo execution. |
| `tenant.id` | `id` | Cho biết ID thuộc đối tượng nào. |
| `source.system` | `source` | Nêu rõ đây là hệ thống nguồn. |
| `dry.run` | `flag` | Mô tả hành vi bật/tắt. |
| `batch.sequence` | `n` | Cho biết số thứ tự batch. |
| `requested.by` | `user` | Diễn đạt rõ nguồn yêu cầu. |

### Dùng quy ước nhất quán

Một quy ước phổ biến là dùng chữ thường và phân tách từ bằng dấu chấm:

```text
input.file
input.encoding
business.date
business.time-zone
tenant.id
source.system
target.table
batch.sequence
dry.run
requested.by
```

Cũng có thể dùng camelCase nếu dự án đã thống nhất, ví dụ `inputFile`, `businessDate`, `tenantId`. Điều quan trọng là chọn một quy ước và dùng nhất quán trong JobParameters, SpEL, test và tài liệu vận hành.

### Key phân biệt chữ hoa/chữ thường

Không nên coi `input.file`, `input.File` và `INPUT.FILE` là cùng một key. Hãy dùng đúng một cách viết ở nơi tạo tham số và nơi inject.

### Tránh key quá chung hoặc trùng ý nghĩa

Các key như `id`, `type`, `date`, `mode` có thể gây nhầm lẫn khi Job phát triển. Nếu một Job cần cả ngày tạo file và ngày nghiệp vụ, hãy dùng `file.created-at` và `business.date` thay vì hai key đều tên `date` ở các lớp khác nhau.

Không dùng cùng một key cho hai ý nghĩa khác nhau chỉ vì chúng tình cờ có cùng kiểu dữ liệu. Key là hợp đồng đầu vào của Job; thay đổi ý nghĩa của key có thể làm các lệnh scheduler cũ truyền sai dữ liệu.

## 3. Truy cập key bằng SpEL

Trong bean có scope Batch, có thể inject JobParameters bằng biểu thức:

```java
@Value("#{jobParameters['input.file']}")
private String inputFile;
```

Hoặc inject qua tham số của bean factory method:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

`jobParameters['input.file']` tra cứu đúng key có dấu chấm. Cú pháp bracket notation đặc biệt hữu ích với key chứa dấu chấm hoặc ký tự không phù hợp với property notation.

Không viết `jobParameters.input.file` để truy cập key `input.file`; SpEL có thể hiểu đó là truy cập property lồng nhau. Dùng `jobParameters['input.file']` để key được xem là một chuỗi duy nhất.

## 4. Vì sao bean cần StepScope hoặc JobScope?

JobParameters chỉ có giá trị khi một JobExecution cụ thể được tạo. Nếu một bean singleton được khởi tạo ngay khi application context start, JobParameters của lần chạy chưa tồn tại để inject.

`@StepScope` tạo bean trong phạm vi StepExecution và cho phép đánh giá SpEL khi Step bắt đầu. Đây là lựa chọn thường dùng cho reader, processor hoặc writer phụ thuộc tham số của một Step.

```java
@Bean
@StepScope
ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return input -> new Order(
            input.orderId(),
            tenantId,
            input.amount());
}
```

`@JobScope` tạo bean trong phạm vi JobExecution. Nó phù hợp khi một bean cần dùng chung tham số ở cấp Job trong nhiều Step. Cần cân nhắc concurrency và vòng đời bean; không lưu state mutable của từng Step trong một Job-scoped singleton nếu nhiều Step/worker có thể truy cập đồng thời.

Các nguyên tắc:

- Reader thường dùng `@StepScope` khi phụ thuộc JobParameters hoặc Step ExecutionContext.
- Processor/writer chỉ cần scope khi cần inject tham số động hoặc state theo execution.
- Bean không phụ thuộc execution có thể vẫn là singleton.
- Không inject JobParameters vào một singleton rồi kỳ vọng nó tự thay đổi theo từng lần launch.

## 5. Kiểu dữ liệu phổ biến

Kiểu dữ liệu cần phản ánh đúng bản chất giá trị. Không nên lưu mọi thứ thành String nếu ứng dụng cần tính toán số học hoặc so sánh ngày tháng.

| Dữ liệu | Kiểu thường dùng | Ví dụ key |
|---|---|---|
| Đường dẫn, tên file, mã nguồn | `String` | `input.file`, `source.system` |
| ID, số lượng, sequence | `Long` | `tenant.id`, `batch.sequence` |
| Tỷ lệ hoặc ngưỡng số thực | `Double` | `quality.threshold` |
| Cờ bật/tắt | `Boolean` | `dry.run` |
| Ngày nghiệp vụ | `LocalDate` hoặc chuỗi ISO date | `business.date` |
| Thời điểm tuyệt đối | `Instant` hoặc chuỗi ISO-8601 có offset | `requested.at` |
| Múi giờ | `ZoneId` hoặc chuỗi timezone ID | `business.time-zone` |
| Tập lựa chọn nhỏ | Enum hoặc `String` | `import.mode` |

Spring Batch 5 sử dụng JobParameter có kiểu dữ liệu. Những kiểu phổ biến có convenience method trong `JobParametersBuilder`; các kiểu khác cần được hỗ trợ bởi conversion service/JobParametersConverter đang cấu hình để lưu và khôi phục metadata. Nếu dùng kiểu tùy chỉnh, hãy kiểm tra khả năng chuyển đổi sang/khỏi dạng lưu trữ và bảo đảm tương thích khi restart.

## 6. Tạo tham số với JobParametersBuilder

Các convenience method giúp khai báo rõ kiểu:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/orders.csv", true)
        .addLong("tenant.id", 42L, true)
        .addDouble("quality.threshold", 0.98, false)
        .addString("import.mode", "FULL", true)
        .addString("requested.by", "scheduler", false)
        .toJobParameters();
```

Tham số `identifying` là đối số cuối cùng trong các overload có cờ identifying:

- `true`: value tham gia xác định JobInstance.
- `false`: value không tham gia xác định JobInstance.

Với Spring Batch 5, có thể tạo JobParameter có kiểu cụ thể bằng API generic `addJobParameter`:

```java
JobParameters parameters = new JobParametersBuilder()
        .addJobParameter(
                "dry.run",
                Boolean.TRUE,
                Boolean.class,
                false)
        .toJobParameters();
```

Việc dùng kiểu tùy chỉnh cần conversion service hỗ trợ chuyển đổi value khi metadata được lưu và đọc lại. Với kiểu phổ biến, ưu tiên convenience method hoặc kiểu được framework hỗ trợ mặc định. Đừng đưa một object tùy ý vào JobParameters mà chưa xác minh serialization/conversion.

## 7. Inject String, Long và Boolean

Ví dụ inject các kiểu đơn giản:

```java
@Bean
@StepScope
Tasklet importTasklet(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobParameters['dry.run']}") Boolean dryRun) {

    return (contribution, chunkContext) -> {
        if (Boolean.TRUE.equals(dryRun)) {
            log.info("Dry run for tenant {} using {}", tenantId, inputFile);
            return RepeatStatus.FINISHED;
        }

        importService.importFile(inputFile, tenantId);
        return RepeatStatus.FINISHED;
    };
}
```

Kiểu đích phải tương thích với kiểu thực tế của JobParameter. Nếu tham số được tạo bằng `addLong`, inject vào `Long` hoặc kiểu tương thích. Nếu tạo bằng `addString`, không nên mặc định rằng mọi nơi đều tự chuyển chuỗi thành kiểu số; hãy cấu hình conversion rõ ràng hoặc parse có validation.

Với Boolean, tránh so sánh chuỗi như `"true"` nếu JobParameter đã có kiểu Boolean. Dùng `Boolean.TRUE.equals(dryRun)` để tránh NullPointerException khi tham số có thể vắng mặt.

## 8. Ngày, giờ và múi giờ

Ngày nghiệp vụ thường không cần giờ và timezone. Dùng `LocalDate` hoặc chuỗi ISO date `yyyy-MM-dd` để biểu diễn rõ:

```java
LocalDate businessDate = LocalDate.parse("2026-11-15");
```

Nếu Job cần một thời điểm tuyệt đối, dùng `Instant` hoặc chuỗi ISO-8601 có offset, ví dụ `2026-11-15T09:30:00+07:00`. Nếu cần lịch chạy theo múi giờ nghiệp vụ, truyền thêm `business.time-zone` như `Asia/Ho_Chi_Minh`.

Ví dụ dùng String để giữ định dạng rõ ràng rồi parse trong bean:

```java
@Bean
@StepScope
Tasklet dailyTasklet(
        @Value("#{jobParameters['business.date']}") String dateValue,
        @Value("#{jobParameters['business.time-zone']}") String zoneValue) {

    LocalDate businessDate = LocalDate.parse(dateValue);
    ZoneId businessZone = ZoneId.of(zoneValue);

    return (contribution, chunkContext) -> {
        reportService.createDailyReport(businessDate, businessZone);
        return RepeatStatus.FINISHED;
    };
}
```

Đoạn code minh họa parse tại thời điểm tạo bean StepScope; trong ứng dụng thực tế nên validate tham số trước khi bắt đầu side effect và xử lý `DateTimeParseException`/`ZoneRulesException` thành lỗi đầu vào có thông báo rõ ràng.

Không nên dùng `LocalDateTime` để biểu diễn thời điểm tuyệt đối nếu không biết timezone. Cùng một LocalDateTime có thể tương ứng với những instant khác nhau ở các múi giờ khác nhau. Với dữ liệu cần so sánh xuyên hệ thống, ưu tiên Instant hoặc offset rõ ràng.

## 9. Key thiếu, giá trị null và giá trị mặc định

Không phải Job nào cũng có mọi tham số là bắt buộc. Cần phân biệt:

- Tham số bắt buộc: thiếu là lỗi cấu hình/đầu vào và Job nên fail sớm.
- Tham số tùy chọn: có thể dùng giá trị mặc định đã định nghĩa.
- Tham số có thể rỗng: phải xác định rõ rỗng khác với không truyền hay không.

Có thể dùng Elvis operator trong SpEL cho giá trị mặc định đơn giản:

```java
@Value("#{jobParameters['import.mode'] ?: 'INCREMENTAL'}")
String importMode
```

Tuy nhiên, không nên dùng default cho một tham số bắt buộc như `input.file`. Nếu thiếu file, Job nên báo lỗi rõ ràng thay vì âm thầm chạy với một đường dẫn mặc định không đúng.

Một cách khác là kiểm tra tham số trong validator/Tasklet đầu Job:

```java
public void validateRequiredParameters(JobParameters parameters) {
    String inputFile = parameters.getString("input.file");
    Long tenantId = parameters.getLong("tenant.id");

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("Missing JobParameter: input.file");
    }

    if (tenantId == null || tenantId <= 0) {
        throw new IllegalArgumentException("Invalid JobParameter: tenant.id");
    }
}
```

`JobParametersValidator` là nơi phù hợp để kiểm tra hợp đồng tham số ở cấp Job trước khi các Step thực hiện công việc chính:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return parameters -> {
        String inputFile = parameters.getString("input.file");
        Long tenantId = parameters.getLong("tenant.id");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "Parameter input.file is required");
        }

        if (tenantId == null || tenantId <= 0) {
            throw new JobParametersInvalidException(
                    "Parameter tenant.id must be positive");
        }
    };
}
```

Gắn validator vào Job builder hoặc cấu hình Job tương ứng để kiểm tra trước khi chạy Step. Validator nên kiểm tra tính hợp lệ của value, không thực hiện side effect như di chuyển file hoặc ghi dữ liệu nghiệp vụ.

## 10. Identifying và non-identifying parameters

Không phải mọi JobParameter đều có vai trò giống nhau khi xác định JobInstance.

- **Identifying parameter:** tham gia vào định danh JobInstance cùng Job name.
- **Non-identifying parameter:** được lưu trong JobExecution nhưng không làm thay đổi định danh JobInstance.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("business.date", "2026-11-15", true)
        .addLong("tenant.id", 42L, true)
        .addString("requested.by", "scheduler", false)
        .addString("notification.email", "ops@example.com", false)
        .toJobParameters();
```

Ngày nghiệp vụ và tenant có thể xác định một lần import cụ thể. Người yêu cầu hoặc địa chỉ nhận thông báo có thể chỉ là metadata vận hành và không nhất thiết tạo JobInstance mới. Quyết định identifying phải dựa trên ý nghĩa nghiệp vụ, không chỉ dựa trên việc tham số có thay đổi hay không.

### Thay đổi type cũng là thay đổi hợp đồng

Nếu lần trước `tenant.id` được tạo là `Long`, còn phiên bản mới tạo cùng key bằng `String`, JobParameters không còn cùng kiểu dữ liệu. Điều này có thể ảnh hưởng định danh, conversion, metadata và restart. Hãy giữ kiểu ổn định qua các phiên bản Job.

Tương tự, thay đổi cách chuẩn hóa value có thể tạo JobInstance khác: `"2026-11-15"` và `"15/11/2026"` là hai String khác nhau dù có thể diễn đạt cùng ngày. Hãy dùng một định dạng canonical, ví dụ ISO-8601.

## 11. Đọc JobParameters trực tiếp trong code

Ngoài SpEL, có thể lấy JobParameters từ `StepExecution` hoặc `JobExecution` khi code đang có execution context:

```java
public class ParameterAwareTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StepExecution stepExecution = contribution.getStepExecution();
        JobParameters parameters = stepExecution
                .getJobExecution()
                .getJobParameters();

        String inputFile = parameters.getString("input.file");
        Long tenantId = parameters.getLong("tenant.id");

        // Thực hiện công việc dựa trên tham số đã được validate.
        return RepeatStatus.FINISHED;
    }
}
```

Cách này hữu ích khi cần đọc nhiều tham số hoặc thực hiện validation có cấu trúc. Với bean được tạo bằng `@StepScope`, SpEL thường ngắn gọn hơn. Không nên truy cập static/global state để lấy tham số của Job hiện tại; dùng execution object được framework truyền vào.

## 12. Phân biệt JobParameters với ExecutionContext

Hai đối tượng thường cùng xuất hiện khi inject dữ liệu nhưng có mục đích khác nhau:

| Đặc điểm | JobParameters | ExecutionContext |
|---|---|---|
| Vai trò | Đầu vào của JobInstance/JobExecution | State của Job/Step trong quá trình chạy |
| Tính chất | Bất biến sau khi Job được tạo | Có thể cập nhật trong execution |
| Nguồn | Scheduler, command line, API launch hoặc ứng dụng gọi | Reader, writer, Tasklet, listener và framework |
| Ví dụ | `business.date`, `input.file`, `tenant.id` | `orders.reader.current.index`, `last.processed.id` |
| Restart | Giữ định danh và đầu vào của lần nghiệp vụ | Lưu checkpoint để tiếp tục phần chưa hoàn tất |

Không ghi checkpoint thay đổi liên tục vào JobParameters. JobParameters mô tả đầu vào; ExecutionContext lưu tiến độ và state cần khôi phục.

Có thể inject Step ExecutionContext bằng SpEL khác với JobParameters:

```java
@Value("#{stepExecutionContext['minIdInclusive']}") Long minId
```

Và Job ExecutionContext:

```java
@Value("#{jobExecutionContext['staging.batch.id']}") String stagingBatchId
```

Các key này không phải key trong JobParameters. Dùng đúng scope để tránh đọc nhầm nguồn dữ liệu.

## 13. Tên key trong reader, processor và writer

Một Job thường có nhiều thành phần cùng cần tham số. Hãy đặt key theo hợp đồng chung của Job và chỉ inject những key mà component cần.

Ví dụ:

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobParameters['business.date']}") String businessDate) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, tenant_id, amount
                    FROM orders
                    WHERE tenant_id = ?
                      AND business_date = ?
                    ORDER BY order_id
                    """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, tenantId);
                statement.setDate(2, Date.valueOf(businessDate));
            })
            .rowMapper(new OrderRowMapper())
            .saveState(true)
            .build();
}
```

Ví dụ dùng `tenant.id` và `business.date` nhất quán ở JobParameters và SQL. Trong ứng dụng thực tế, nên parse `business.date` thành `LocalDate` sau validation, rồi bind bằng kiểu JDBC phù hợp với schema. Dùng prepared statement để bind value; không nối chuỗi JobParameter trực tiếp vào SQL.

Không đặt tên key theo tên biến cục bộ của một class nếu key đó được dùng như hợp đồng giữa scheduler, Job và nhiều component. Hãy đặt tên theo ý nghĩa nghiệp vụ ổn định.

## 14. Chuẩn hóa định dạng value

Ngay cả khi kiểu dữ liệu là String, giá trị nên có định dạng chuẩn để các hệ thống tạo JobParameters giống nhau.

Ví dụ:

| Loại dữ liệu | Định dạng nên dùng | Ví dụ |
|---|---|---|
| Ngày | ISO-8601 date | `2026-11-15` |
| Thời điểm có timezone | ISO-8601 offset datetime | `2026-11-15T09:30:00+07:00` |
| Instant UTC | ISO-8601 instant | `2026-11-15T02:30:00Z` |
| Enum/mode | Giá trị canonical chữ hoa hoặc chữ thường theo quy ước | `FULL`, `INCREMENTAL` |
| Mã tenant | Chuỗi canonical hoặc số nguyên tùy domain | `42` |
| Boolean | `true` hoặc `false` chữ thường nếu dùng String | `true` |

Không dùng nhiều cách viết cho cùng một giá trị nếu key là identifying. Canonical format giúp hai lần launch cùng một nghiệp vụ tạo cùng JobInstance.

## 15. Tránh đưa bí mật vào JobParameters

JobParameters thường được lưu trong JobRepository để hỗ trợ định danh và restart. Vì vậy, không nên truyền password, access token, private key hoặc credential nhạy cảm dưới dạng JobParameter.

Thay vào đó:

- Dùng secret manager hoặc credential provider của môi trường.
- Truyền tên credential/profile hoặc secret reference không nhạy cảm nếu cần chọn cấu hình.
- Dùng Spring configuration để inject secret vào client theo cơ chế bảo mật của ứng dụng.
- Không log toàn bộ JobParameters nếu chúng có thể chứa dữ liệu nhạy cảm.
- Kiểm soát quyền truy cập database metadata và màn hình vận hành.

Ví dụ, có thể truyền `source.profile=partner-a` rồi để ứng dụng lấy credential tương ứng từ secret store. Không truyền `source.password=...` vào JobParameters.

## 16. Tham số tùy chỉnh và conversion

Spring Batch 5 cho phép JobParameter có kiểu dữ liệu cụ thể hơn các kiểu primitive truyền thống. Tuy nhiên, JobRepository cần chuyển value thành dạng lưu trữ và khôi phục lại khi đọc metadata.

Nếu dùng custom type:

1. Xác nhận conversion service/JobParametersConverter hỗ trợ kiểu đó.
2. Cấu hình converter có thể chuyển đổi hai chiều nếu metadata cần đọc lại.
3. Dùng một định dạng lưu trữ ổn định, có thể parse qua các lần nâng cấp.
4. Tránh lưu object phụ thuộc class implementation hoặc thư viện dễ thay đổi.
5. Kiểm thử launch, lưu metadata, đọc lại JobParameters và restart.

Ví dụ, thay vì lưu object `BusinessPeriod` tùy chỉnh nếu chưa có converter, có thể truyền hai key đơn giản:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("period.start", "2026-11-01", true)
        .addString("period.end", "2026-11-30", true)
        .toJobParameters();
```

Ứng dụng parse hai giá trị thành `LocalDate` và tạo `BusinessPeriod` sau khi validate. Cách này giúp hợp đồng JobParameters rõ ràng và dễ vận hành từ scheduler hoặc API.

## 17. Kiểm thử tên key và kiểu dữ liệu

Kiểm thử parameter injection nên xác nhận cả key và type. Một key sai chính tả có thể trả về null; một type không tương thích có thể làm bean không tạo được hoặc lỗi khi thực hiện Step.

Ví dụ test bean StepScope với JobParameters:

```java
@SpringBatchTest
class OrderReaderParameterTest {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void readerReceivesInputFileParameter() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "classpath:orders.csv", true)
                .addLong("tenant.id", 42L, true)
                .toJobParameters();

        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(parameters);

        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            ItemReader<OrderInput> reader = applicationContext.getBean(
                    "orderReader", ItemReader.class);
            assertThat(reader).isNotNull();
            return null;
        });
    }
}
```

Đoạn test minh họa cách tạo StepExecution với JobParameters và truy cập bean trong StepScope. Test thực tế nên đọc item đầu tiên hoặc kiểm tra cấu hình reader để xác nhận đúng resource và query, không chỉ assert bean khác null.

Các trường hợp nên kiểm tra:

- Key đúng và value đúng type.
- Key thiếu đối với tham số bắt buộc.
- Giá trị rỗng hoặc sai định dạng ngày.
- `Long` không hợp lệ hoặc giá trị ngoài miền cho phép.
- Boolean không được truyền hoặc có giá trị mặc định.
- Identifying parameter giữ nguyên khi restart.
- Custom type có thể serialize/convert và đọc lại từ JobRepository.

## 18. Những lỗi thường gặp

### Sai tên key trong SpEL

JobParameters có `input.file` nhưng bean inject `inputFile`. Kết quả có thể là null hoặc lỗi khởi tạo. Giữ key tập trung và dùng thống nhất trong builder, SpEL, validator và test.

### Dùng property notation cho key có dấu chấm

`jobParameters.input.file` không phải cách truy cập an toàn cho key `input.file`. Dùng `jobParameters['input.file']`.

### Inject vào singleton bean

Singleton được tạo trước khi Job chạy nên không có JobParameters của execution cụ thể. Dùng `@StepScope` hoặc `@JobScope` khi cần inject tham số động.

### Tạo Long nhưng inject String hoặc ngược lại

Kiểu tham số và kiểu bean không tương thích có thể gây conversion error. Chọn type rõ ràng và kiểm thử conversion.

### Dùng String cho mọi giá trị

Điều này đẩy lỗi parse về sâu trong Step và khiến validation kém rõ ràng. Dùng kiểu số cho số, hoặc parse String sớm theo định dạng chuẩn.

### Đổi kiểu identifying parameter giữa các phiên bản

`tenant.id` từ Long sang String có thể ảnh hưởng JobInstance identity và restart. Giữ kiểu ổn định hoặc có kế hoạch migration/compatibility.

### Thêm timestamp ngẫu nhiên vào identifying parameters

Mỗi lần launch có thể tạo JobInstance mới, khiến restart không tiếp tục lần nghiệp vụ cũ. Chỉ dùng identifying value phản ánh định danh business run.

### Dùng default cho tham số bắt buộc

Job có thể chạy nhầm input nếu thiếu `input.file` mà không báo lỗi. Dùng validator để từ chối tham số thiếu hoặc sai.

### Truyền password/token trong JobParameters

Metadata có thể được lưu và hiển thị cho người vận hành. Dùng secret store và chỉ truyền reference không nhạy cảm.

### Lưu custom object không có converter

Job có thể chạy lần đầu nhưng lỗi khi lưu/đọc metadata hoặc restart. Kiểm tra conversion/serialization hai chiều trước khi dùng custom type.

## 19. Quy trình thiết kế key và type

Khi thêm một JobParameter mới, có thể thực hiện theo trình tự:

1. Xác định ý nghĩa nghiệp vụ hoặc kỹ thuật của giá trị.
2. Chọn tên key ổn định, dễ đọc và không trùng ý nghĩa.
3. Chọn kiểu Java phản ánh đúng bản chất value.
4. Chọn định dạng canonical cho ngày, giờ, enum và mã định danh.
5. Quyết định tham số có identifying hay không dựa trên định danh JobInstance.
6. Tạo parameter bằng `JobParametersBuilder` hoặc cơ chế launch đã chuẩn hóa.
7. Inject bằng `@Value("#{jobParameters['key']}")` trong bean có scope Batch.
8. Validate tham số bắt buộc, miền giá trị và định dạng trước side effect.
9. Kiểm tra custom type có conversion/serialization tương thích JobRepository.
10. Bảo đảm kiểu và ý nghĩa key ổn định qua restart và nâng cấp.
11. Không đưa secret vào JobParameters; dùng secret reference hoặc credential provider.
12. Viết test cho key đúng/sai, thiếu value, conversion và JobInstance identity.

| Nhu cầu | Thiết kế gợi ý |
|---|---|
| Đường dẫn file đầu vào | `input.file` kiểu `String`, validate file trước khi đọc. |
| ID tenant | `tenant.id` kiểu `Long` hoặc kiểu ID domain được hỗ trợ. |
| Ngày nghiệp vụ | `business.date` dạng ISO `LocalDate` hoặc String canonical. |
| Chế độ chạy | `import.mode` dạng enum/String với tập giá trị cho phép. |
| Bật chế độ thử | `dry.run` kiểu Boolean, non-identifying nếu không đổi định danh nghiệp vụ. |
| Mã người yêu cầu | `requested.by` kiểu String, thường non-identifying. |
| Secret kết nối | Truyền `source.profile`/secret reference; không truyền password/token. |

## Kết luận

Tên key và kiểu dữ liệu là hợp đồng đầu vào của Job. Hãy dùng key có ý nghĩa và nhất quán như `input.file`, `business.date`, `tenant.id`; truy cập key có dấu chấm bằng `jobParameters['key']`; và inject tham số động trong bean `@StepScope` hoặc `@JobScope`. Chọn type phù hợp với value, chuẩn hóa định dạng ngày/giờ, validate tham số bắt buộc và giữ identifying flag cùng kiểu dữ liệu ổn định để JobInstance/restart hoạt động đúng. Với kiểu tùy chỉnh, xác nhận conversion/serialization hai chiều; không lưu secret trong JobParameters và phân biệt rõ JobParameters đầu vào với ExecutionContext dùng để lưu tiến độ.
