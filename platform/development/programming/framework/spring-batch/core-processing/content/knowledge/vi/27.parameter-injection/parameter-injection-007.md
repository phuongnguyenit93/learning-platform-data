# Default parameter

Trong Spring Batch, Job thường nhận dữ liệu đầu vào qua `JobParameters`, chẳng hạn ngày nghiệp vụ, đường dẫn file, mã nguồn hoặc kích thước page. Không phải tham số nào cũng bắt buộc người gọi phải truyền. Với tham số tùy chọn, ứng dụng có thể cung cấp **giá trị mặc định** để Step vẫn chạy khi JobParameters không có key đó.

Khi inject tham số vào bean theo `@StepScope`, có thể dùng SpEL để đọc JobParameters và toán tử Elvis `?:` để chọn giá trị thay thế khi tham số bị thiếu hoặc có giá trị `null`:

```java
@Bean
@StepScope
public ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Nếu caller không truyền `inputFile`, reader dùng `data/orders.csv`. Nếu caller truyền một giá trị, giá trị được truyền sẽ được dùng. Default parameter giúp giảm cấu hình lặp lại, nhưng cần được thiết kế cẩn thận để không làm Job đọc nhầm dữ liệu hoặc thay đổi kết quả khi restart.

## 1. JobParameters và tham số tùy chọn

`JobParameters` là tập các tham số đầu vào gắn với một JobExecution. Một số tham số xác định công việc logic (`identifying`), một số chỉ cung cấp thông tin bổ sung (`non-identifying`).

Ví dụ một Job nhập đơn hàng:

| Tham số | Bắt buộc? | Ví dụ | Vai trò |
|---|---|---|---|
| `businessDate` | Có | `2026-11-15` | Xác định kỳ nghiệp vụ cần nhập |
| `inputFile` | Không | `data/orders.csv` | File đầu vào; có thể có default |
| `pageSize` | Không | `500` | Số dòng đọc mỗi page |
| `sourceSystem` | Tùy nghiệp vụ | `ERP` | Xác định hệ thống nguồn |

Một tham số tùy chọn có thể được xử lý theo hai cách:

- Người khởi chạy truyền giá trị cụ thể; Step sử dụng giá trị đó.
- Người khởi chạy bỏ qua key; Step sử dụng default được cấu hình trong biểu thức inject hoặc trong lớp tạo JobParameters.

Default chỉ nên áp dụng cho tham số thực sự có giá trị mặc định an toàn. Những tham số như ngày nghiệp vụ, tenant hoặc tài khoản nguồn thường không nên tự suy đoán nếu chọn sai sẽ làm dữ liệu được xử lý nhầm.

## 2. Dùng SpEL Elvis operator để đặt default

Trong `@Value`, biểu thức `#{...}` là SpEL. Có thể dùng toán tử Elvis `?:` để chọn giá trị mặc định khi biểu thức bên trái không có giá trị:

```java
@Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}")
String inputFile
```

Ý nghĩa:

- `jobParameters['inputFile']`: đọc JobParameter có key `inputFile`.
- `?:`: nếu biểu thức bên trái không có giá trị, dùng biểu thức bên phải.
- `'data/orders.csv'`: chuỗi default.

Một số ví dụ khác:

```java
@Value("#{jobParameters['pageSize'] ?: 500}") Integer pageSize

@Value("#{jobParameters['delimiter'] ?: ','}") String delimiter

@Value("#{jobParameters['includeInactive'] ?: false}") Boolean includeInactive

@Value("#{jobParameters['maxRetries'] ?: 3}") Integer maxRetries
```

Nên đặt default đúng kiểu dữ liệu. Ví dụ `500` là số nguyên, `false` là boolean và `','` là chuỗi. Spring thực hiện chuyển đổi kiểu khi inject vào tham số method nếu có converter phù hợp.

Không dùng default kiểu chuỗi cho giá trị số nếu không cần thiết. Viết `?: 500` rõ kiểu số hơn `?: '500'`, đặc biệt khi biểu thức được dùng trong phép toán hoặc so sánh.

## 3. Ví dụ đầy đủ với @StepScope

Giả sử Job nhập đơn hàng có hai tham số tùy chọn: `inputFile` và `pageSize`. File mặc định là `data/orders.csv`; page size mặc định là 500.

```java
@Configuration
public class OrderImportConfiguration {

    @Bean
    @StepScope
    public JdbcPagingItemReader<Order> orderReader(
            DataSource dataSource,
            PagingQueryProvider queryProvider,
            RowMapper<Order> orderRowMapper,
            @Value("#{jobParameters['pageSize'] ?: 500}") Integer pageSize,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        return new JdbcPagingItemReaderBuilder<Order>()
                .name("orderReader")
                .dataSource(dataSource)
                .queryProvider(queryProvider)
                .parameterValues(Map.of("businessDate", businessDate))
                .rowMapper(orderRowMapper)
                .pageSize(pageSize)
                .saveState(true)
                .build();
    }
}
```

Trong ví dụ, `pageSize` có default 500, còn `businessDate` là bắt buộc nên không có default tùy tiện. `@StepScope` cho phép SpEL được đánh giá khi StepExecution hiện tại đã tồn tại.

Nếu dùng `FlatFileItemReader`, có thể áp dụng cùng cách cho `inputFile`:

```java
@Bean
@StepScope
public ItemStreamReader<Order> fileOrderReader(
        @Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("fileOrderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Khai báo kiểu trả về là `ItemStreamReader<Order>` để thể hiện reader cũng hỗ trợ lifecycle `open()`, `update()` và `close()` cho checkpoint/restart.

## 4. Giá trị được truyền sẽ ưu tiên hơn default

Default chỉ được dùng khi JobParameter không cung cấp giá trị. Nếu caller truyền giá trị hợp lệ, giá trị đó được ưu tiên.

Ví dụ biểu thức:

```java
@Value("#{jobParameters['pageSize'] ?: 500}") Integer pageSize
```

| JobParameters | Giá trị inject |
|---|---:|
| Không có key `pageSize` | 500 |
| `pageSize=100` | 100 |
| `pageSize=1000` | 1000 |
| Key có giá trị null | 500 |

Đừng nhầm default với việc ghi đè giá trị caller đã truyền. Nếu caller yêu cầu `pageSize=1000`, Step phải dùng 1000 thay vì ép về 500.

Với tham số chuỗi, cần xác định cách xử lý chuỗi rỗng hoặc chỉ chứa khoảng trắng. Elvis operator xử lý trường hợp không có giá trị/null; không nên dựa vào nó để thay thế validation cho chuỗi rỗng hoặc dữ liệu không hợp lệ. Có thể kiểm tra rõ trong factory method, validator hoặc service:

```java
if (inputFile == null || inputFile.isBlank()) {
    throw new IllegalArgumentException("inputFile must not be blank");
}
```

Nếu muốn coi chuỗi rỗng là không truyền, hãy chuẩn hóa input ở tầng khởi chạy hoặc dùng logic SpEL/Java rõ ràng có kiểm thử cho trường hợp đó.

## 5. Phân biệt SpEL default với Spring property placeholder

Trong Spring có hai kiểu cú pháp default thường gặp, nhưng chúng lấy giá trị từ hai nguồn khác nhau.

**SpEL đọc JobParameters:**

```java
@Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}")
String inputFile
```

Biểu thức này đọc tham số của JobExecution hiện tại. Đây là cách đặt default cho JobParameter trong bean batch có scope phù hợp.

**Property placeholder đọc cấu hình ứng dụng:**

```java
@Value("${batch.input-file:data/orders.csv}")
String inputFile
```

Biểu thức này đọc property `batch.input-file` từ Spring Environment, ví dụ `application.yml`, biến môi trường hoặc nguồn cấu hình khác. Phần sau dấu `:` là default cho property placeholder.

| Cú pháp | Nguồn | Khi nào dùng? |
|---|---|---|
| `#{jobParameters['inputFile'] ?: 'data/orders.csv'}` | JobParameters | Giá trị thay đổi theo lần chạy Job |
| `${batch.input-file:data/orders.csv}` | Spring Environment | Giá trị cấu hình ứng dụng/môi trường |

Không thay `${...}` bằng `#{...}` hoặc ngược lại nếu chưa xác định đúng nguồn dữ liệu. Property thường mô tả cấu hình triển khai; JobParameter mô tả đầu vào của một lần chạy batch.

Có thể kết hợp hai nguồn nếu nghiệp vụ cần ưu tiên JobParameter rồi đến application property, sau cùng mới dùng fallback. Tuy nhiên, biểu thức dài khó đọc; thường nên tính giá trị trong một factory/service hoặc materialize default trước khi launch để quy tắc ưu tiên rõ ràng.

## 6. Đặt default ngay khi tạo JobParameters

Một lựa chọn khác là bổ sung default trước khi khởi chạy Job. Cách này tạo ra JobParameters hoàn chỉnh ngay từ đầu:

```java
public JobParameters buildParameters(
        String businessDate,
        String requestedInputFile,
        Integer requestedPageSize) {

    String inputFile = requestedInputFile != null && !requestedInputFile.isBlank()
            ? requestedInputFile
            : "data/orders.csv";

    int pageSize = requestedPageSize != null
            ? requestedPageSize
            : 500;

    return new JobParametersBuilder()
            .addString("businessDate", businessDate, true)
            .addString("inputFile", inputFile, true)
            .addLong("pageSize", (long) pageSize, false)
            .toJobParameters();
}
```

Ở đây, `inputFile` và `pageSize` được tính trước khi gọi `JobLauncher`. Step chỉ inject các key đã có trong JobParameters:

```java
@Value("#{jobParameters['inputFile']}") String inputFile
@Value("#{jobParameters['pageSize']}") Long pageSize
```

Lợi ích của cách materialize default:

- JobParameters lưu lại giá trị thực sự đã dùng cho lần chạy.
- Metadata thể hiện rõ file và page size được chọn.
- Restart cùng JobInstance nhận lại đúng giá trị đã lưu.
- Log, audit và màn hình vận hành dễ giải thích hơn.
- Tránh việc default thay đổi giữa hai lần deploy làm cùng một JobInstance chạy với cấu hình khác.

Đây thường là lựa chọn tốt cho default có ảnh hưởng đến dữ liệu nghiệp vụ, nguồn đầu vào hoặc kết quả restart.

## 7. Default parameter và identifying JobParameters

JobInstance được xác định bởi tên Job và các JobParameters được đánh dấu identifying. Khi bổ sung default, cần quyết định tham số đó có tham gia định danh công việc logic hay không.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders.csv", true)
        .addLong("pageSize", 500L, false)
        .toJobParameters();
```

Trong ví dụ:

- `businessDate` là identifying vì nó xác định kỳ nghiệp vụ.
- `inputFile` là identifying nếu hai file khác nhau đại diện cho hai công việc logic khác nhau.
- `pageSize` là non-identifying vì đây là tham số hiệu năng và không thay đổi tập dữ liệu nghiệp vụ.

Quyết định identifying hay non-identifying phải theo nghiệp vụ, không theo việc tham số có default hay không. Nếu thay đổi một tham số làm thay đổi dữ liệu cần xử lý, thường cần xem xét đưa nó vào identity. Nếu chỉ thay đổi cách thực thi mà không thay đổi công việc logic, có thể để non-identifying.

Restart cần giữ nguyên identifying parameters để tiếp tục cùng JobInstance. Nếu default được tính lại và một identifying value khác đi, Spring Batch có thể tạo JobInstance khác thay vì restart execution cũ.

## 8. Default được inject không tự động trở thành JobParameter đã lưu

Đây là khác biệt quan trọng giữa default trong `@Value` và default được materialize trước khi launch.

Giả sử JobParameters không có key `inputFile`, bean inject:

```java
@Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}")
String inputFile
```

Target bean dùng `data/orders.csv`, nhưng điều đó không có nghĩa JobParameters trong JobRepository đã được bổ sung key `inputFile`. Giá trị default chỉ được dùng khi evaluate biểu thức để tạo bean.

Nếu phiên bản ứng dụng sau đổi default thành `data/orders-v2.csv`, một execution được restart mà trước đó không lưu `inputFile` có thể nhận default mới. Cùng JobInstance có thể vô tình xử lý một file khác.

Với default ảnh hưởng đến dữ liệu, hãy thêm giá trị vào JobParameters trước khi launch hoặc lưu lựa chọn vào metadata bền vững. Đừng dựa vào một fallback trong code có thể thay đổi qua deployment để xác định lại nguồn dữ liệu cho execution đang dở.

## 9. Default động và rủi ro khi restart

Một default động là giá trị được tính tại thời điểm Job chạy, ví dụ ngày hiện tại hoặc timestamp:

```java
@Value("#{jobParameters['businessDate'] ?: T(java.time.LocalDate).now().toString()}")
String businessDate
```

Biểu thức này có vẻ tiện khi caller không truyền ngày. Nhưng nếu Job chạy lần đầu vào ngày 15 rồi thất bại, restart vào ngày 16 có thể evaluate default thành ngày 16. Job có thể xử lý dữ liệu khác với lần chạy đầu.

Với default động:

- Tính giá trị một lần ở tầng khởi chạy.
- Đưa giá trị đó vào JobParameters, thường là identifying nếu nó xác định kỳ nghiệp vụ.
- Khi restart, dùng lại đúng JobInstance và parameters cũ.
- Không gọi `now()` hoặc tạo UUID mới trong mỗi lần tạo target bean nếu giá trị phải ổn định qua restart.

Ví dụ tạo ngày mặc định trước khi launch:

```java
LocalDate effectiveDate = requestedDate != null
        ? requestedDate
        : LocalDate.now(clock);

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", effectiveDate.toString(), true)
        .toJobParameters();
```

Inject `businessDate` từ JobParameters giúp mọi lần restart dùng cùng một ngày nghiệp vụ.

## 10. Default không thay thế validation

Default chỉ giải quyết trường hợp tham số không được cung cấp. Nó không chứng minh giá trị hợp lệ.

Ví dụ, `pageSize` có default 500 nhưng caller có thể truyền `-1`. Reader vẫn nhận giá trị caller truyền nếu biểu thức chỉ kiểm tra null. Cần kiểm tra range:

```java
if (pageSize == null || pageSize < 1 || pageSize > 10_000) {
    throw new IllegalArgumentException("pageSize must be between 1 and 10000");
}
```

Với `inputFile`, cần kiểm tra file tồn tại và có thể đọc. Với `businessDate`, cần parse theo format đã quy định và xác nhận kỳ nghiệp vụ có được phép chạy hay không.

Có thể validate JobParameters trước khi Job chạy bằng `JobParametersValidator`. Ví dụ, `DefaultJobParametersValidator` kiểm tra danh sách key bắt buộc và key tùy chọn. Tuy nhiên, **optional key không đồng nghĩa có default value**: validator chỉ kiểm tra tính hợp lệ của tập tham số; nó không tự thêm giá trị còn thiếu vào JobParameters.

Nếu cần default được lưu trong metadata, hãy bổ sung nó bằng `JobParametersBuilder` trước khi launch. Nếu cần kiểm tra tham số bắt buộc, dùng validator. Hai nhiệm vụ này có thể phối hợp nhưng không thay thế nhau.

## 11. Ví dụ dùng JobParametersValidator với default

Một cách tổ chức rõ ràng là materialize default trước, sau đó validate bộ JobParameters hoàn chỉnh:

```java
@Bean
public JobParametersValidator orderImportParametersValidator() {
    return new DefaultJobParametersValidator(
            new String[] {"businessDate", "inputFile"},
            new String[] {"pageSize", "sourceSystem"}
    );
}
```

Trong flow khởi chạy, ứng dụng có thể:

1. Nhận tham số từ API, scheduler hoặc command line.
2. Bổ sung `inputFile`/`pageSize` nếu người gọi bỏ qua và nghiệp vụ cho phép default.
3. Chuẩn hóa ngày, đường dẫn và giá trị chuỗi.
4. Tạo JobParameters hoàn chỉnh.
5. Gọi validator để kiểm tra required/optional keys và các quy tắc liên quan.
6. Gọi JobLauncher.

`DefaultJobParametersValidator` kiểm tra key bắt buộc và tùy chọn theo cấu hình. Nếu cần validate giá trị như page size dương, ngày đúng định dạng hoặc file tồn tại, hãy dùng validator tùy chỉnh hoặc kiểm tra ở tầng thích hợp.

## 12. Default parameter cho nhiều kiểu dữ liệu

Khi inject default, cần quan tâm kiểu dữ liệu và chuyển đổi:

| Kiểu | Ví dụ SpEL | Kiểu method parameter |
|---|---|---|
| String | `#{jobParameters['delimiter'] ?: ','}` | `String` |
| Integer | `#{jobParameters['pageSize'] ?: 500}` | `Integer` |
| Long | `#{jobParameters['maxRows'] ?: 100000L}` | `Long` |
| Boolean | `#{jobParameters['enabled'] ?: true}` | `Boolean` |
| BigDecimal | `#{jobParameters['minimumAmount'] ?: 0.00}` | `BigDecimal` |

Với số thực hoặc tiền tệ, cần kiểm soát scale/rounding theo nghiệp vụ. Không dùng kiểu floating-point cho phép tính tiền nếu cần độ chính xác thập phân; dùng `BigDecimal` và quy tắc làm tròn rõ ràng.

Với ngày giờ, thường nên truyền chuỗi theo định dạng ISO hoặc một JobParameter kiểu phù hợp với phiên bản Spring Batch, sau đó parse và validate tường minh. Nếu default là ngày hiện tại, materialize trước khi launch để restart không đổi ngày.

## 13. Dùng default trong @StepScope và @JobScope

`@StepScope` phù hợp khi bean cần tham số ở phạm vi StepExecution, ví dụ reader nhận `minId`/`maxId` của từng partition. `@JobScope` phù hợp khi bean cần dữ liệu ở phạm vi JobExecution và được nhiều Step sử dụng.

Ví dụ step-scoped reader:

```java
@Bean
@StepScope
public ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}") String inputFile) {
    // Khởi tạo reader với inputFile đã có default.
    return createOrderReader(inputFile);
}
```

Ví dụ job-scoped coordinator:

```java
@Bean
@JobScope
public ImportCoordinator importCoordinator(
        @Value("#{jobParameters['sourceSystem'] ?: 'ERP'}") String sourceSystem) {
    return new ImportCoordinator(sourceSystem);
}
```

Scope quyết định thời điểm evaluate biểu thức và vòng đời target bean. Default expression không làm bean singleton trở thành step-scoped; nếu cần late binding từ JobParameters, hãy dùng scope phù hợp.

## 14. Những nhầm lẫn thường gặp

**Cho rằng default trong `@Value` được thêm vào JobParameters.** Nó chỉ là giá trị inject vào bean. Nếu cần lưu/audit/restart ổn định, materialize default trước khi launch.

**Nhầm `${property:default}` với `#{jobParameters['key'] ?: default}`.** Một cú pháp đọc Spring Environment, cú pháp kia đọc JobParameters.

**Cho rằng optional key trong validator tự có giá trị mặc định.** Optional chỉ có nghĩa key được phép vắng mặt; validator không tự bổ sung giá trị.

**Dùng ngày hiện tại làm default trong bean và kỳ vọng restart ổn định.** Restart ở ngày khác có thể dùng ngày khác. Tính default một lần rồi lưu trong JobParameters.

**Cho rằng default bảo đảm dữ liệu hợp lệ.** Caller vẫn có thể truyền giá trị sai. Hãy validate kiểu, range, format và sự tồn tại của resource.

**Dùng default cho tham số nghiệp vụ bắt buộc.** Một giá trị suy đoán sai có thể làm Job xử lý nhầm tenant, kỳ hoặc file. Chỉ đặt default khi có quy tắc nghiệp vụ rõ ràng.

**Cho rằng `@StepScope` tự lưu default qua restart.** Scope quản lý lifecycle; JobRepository lưu JobParameters và ExecutionContext. Default inject động không tự trở thành metadata.

## 15. Kiểm thử default parameter

Nên kiểm thử cả trường hợp có tham số, thiếu tham số và giá trị không hợp lệ:

1. Không truyền `inputFile`: bean nhận default `data/orders.csv`.
2. Truyền `inputFile=custom.csv`: bean nhận `custom.csv`.
3. Không truyền `pageSize`: bean nhận 500.
4. Truyền `pageSize=1000`: bean nhận 1000.
5. Truyền `pageSize=-1`: validation từ chối giá trị.
6. Truyền chuỗi rỗng hoặc whitespace: ứng dụng xử lý theo quy tắc đã định, không vô tình coi là đường dẫn hợp lệ.
7. Khởi chạy Job không có tham số tùy chọn rồi restart sau khi thay đổi default trong code: xác nhận chiến lược metadata ngăn nguồn đầu vào thay đổi ngoài ý muốn.
8. Chạy hai JobExecution với các JobParameters khác nhau đồng thời: xác nhận step-scoped bean không chia sẻ giá trị runtime.

Test late binding cần có Step context đang hoạt động. Có thể dùng Spring Batch Test utilities để tạo `StepExecution` và thực thi code trong step scope. Với integration test, kiểm tra cả JobParameters được lưu trong JobRepository và giá trị thực tế bean nhận.

## 16. Cách thiết kế default parameter an toàn

Trước khi đặt default, xác định tham số đó có thực sự tùy chọn hay không và giá trị thay thế có an toàn về nghiệp vụ không. Với giá trị cấu hình theo môi trường, dùng Spring property placeholder. Với giá trị theo từng lần chạy, đọc JobParameters bằng SpEL trong bean có `@StepScope` hoặc `@JobScope` phù hợp.

Nếu default ảnh hưởng đến dữ liệu đầu vào, kỳ nghiệp vụ hoặc kết quả restart, hãy tính default ở tầng khởi chạy và lưu nó vào JobParameters để metadata thể hiện đúng giá trị đã dùng. Dùng validator để kiểm tra tham số bắt buộc/tùy chọn và kiểm tra riêng format, range, resource. Tránh default động như ngày hiện tại được tính lại mỗi lần tạo bean.

Default parameter giúp Job dễ sử dụng và giảm cấu hình lặp lại. Khi kết hợp đúng late binding, validation, identifying parameters và restart, ứng dụng có thể hỗ trợ tham số tùy chọn mà vẫn giữ đầu vào rõ ràng, có thể truy vết và ổn định qua các lần thực thi.
