# Parameter không tồn tại

Trong Spring Batch, một bean có thể nhận JobParameters thông qua late binding, ví dụ bằng biểu thức SpEL trong @Value. Nhưng tham số được yêu cầu có thể không được truyền khi Job khởi chạy. Khi key không tồn tại, biểu thức truy cập thường trả về null; nếu bean yêu cầu một giá trị không nullable hoặc code giả định giá trị luôn có mặt, Step có thể thất bại khi tạo bean hoặc khi sử dụng tham số.

Cần phân biệt ba trường hợp:

- **Parameter không tồn tại**: JobParameters không có key được yêu cầu.
- **Parameter tồn tại nhưng rỗng hoặc blank**: key có mặt, nhưng giá trị là chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- **Parameter tồn tại với giá trị mặc định hoặc giá trị nghiệp vụ**: key được truyền rõ ràng và có giá trị.

Cách xử lý phụ thuộc ý nghĩa của tham số. Nếu tham số bắt buộc, hãy xác thực trước khi Job chạy và báo lỗi rõ ràng. Nếu tham số tùy chọn, hãy dùng kiểu nullable hoặc default có chủ đích. Không nên để một key thiếu âm thầm biến thành giá trị sai rồi làm Job xử lý nhầm dữ liệu.

## 1. Parameter không tồn tại nghĩa là gì?

JobParameters là tập key-value được truyền vào JobLauncher khi khởi chạy Job. Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

jobLauncher.run(importJob, parameters);
~~~

Trong lần chạy này, Job có hai key:

- inputFile
- businessDate

Nếu bean cố đọc thêm key mode:

~~~java
@Value("#{jobParameters['mode']}")
String mode
~~~

thì key mode không có trong JobParameters. Trong biểu thức map access, giá trị được resolve là null.

Việc thiếu key không giống với việc truyền chuỗi "null", chuỗi rỗng hoặc giá trị "FULL". Đây là các trạng thái khác nhau và nên được xử lý riêng.

Một lỗi thường gặp là code giả định parameter luôn có mặt:

~~~java
String mode = jobParameters.getString("mode");
String normalized = mode.trim();
~~~

Nếu mode không tồn tại, mode là null và lời gọi trim() gây NullPointerException. Vấn đề bắt đầu từ việc chưa xác định rõ parameter là bắt buộc hay tùy chọn.

## 2. SpEL truy cập JobParameters

Spring Batch đưa JobParameters vào execution context để scoped bean có thể truy cập bằng SpEL.

Ví dụ:

~~~java
@Bean
@StepScope
public ItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    // ...
}
~~~

Các điểm cần nhớ:

- jobParameters['inputFile'] truy cập key theo tên.
- Tên key phân biệt chữ hoa và chữ thường.
- Key không có thường trả về null.
- Giá trị được chuyển đổi sang kiểu tham số Java nếu Spring có conversion phù hợp.
- Việc resolve diễn ra khi scoped bean được tạo trong Job/Step execution, không phải lúc ApplicationContext khởi động.

Có thể truy cập JobParameters từ cả JobScope và StepScope. StepScope cũng có thể truy cập Job ExecutionContext và Step ExecutionContext.

Nếu lỗi là scope chưa active, đó là vấn đề khác với key không tồn tại. Scope chưa active thường xuất hiện khi bean được truy cập ngoài lifecycle của Job/Step. Khi scope đã active nhưng key thiếu, biểu thức vẫn có thể resolve thành null.

## 3. Missing khác với empty và blank

Giả sử parameter tên mode:

| Trạng thái | Ví dụ khi launch | Ý nghĩa |
|---|---|---|
| Không tồn tại | Không thêm key mode | Không có giá trị được truyền |
| Empty | mode = "" | Có key nhưng chuỗi rỗng |
| Blank | mode = "   " | Có key nhưng không có nội dung hữu ích |
| Có giá trị | mode = "FULL" | Có giá trị rõ ràng |

Với chuỗi, chỉ kiểm tra null là chưa đủ nếu chuỗi rỗng hoặc khoảng trắng cũng không hợp lệ.

Ví dụ:

~~~java
if (mode == null) {
    throw new IllegalArgumentException("mode is required");
}
~~~

Điều kiện này vẫn chấp nhận chuỗi rỗng. Có thể dùng Spring StringUtils:

~~~java
if (!StringUtils.hasText(mode)) {
    throw new IllegalArgumentException(
            "Parameter 'mode' must contain text");
}
~~~

StringUtils.hasText trả false với null, chuỗi rỗng và chuỗi chỉ có whitespace.

Hãy quyết định rõ liệu empty/blank có được xem như missing hay có ý nghĩa riêng. Đừng để các thành phần khác nhau trong Job diễn giải không thống nhất.

## 4. Tham số bắt buộc nên được xác thực trước khi Job chạy

Nếu thiếu parameter khiến Job không thể thực hiện đúng nghiệp vụ, hãy từ chối JobParameters trước khi Step bắt đầu. Spring Batch cung cấp JobParametersValidator cho mục đích này.

Ví dụ custom validator:

~~~java
public class ImportJobParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");

        if (!StringUtils.hasText(inputFile)) {
            throw new JobParametersInvalidException(
                    "Required parameter 'inputFile' is missing or blank");
        }

        String businessDate =
                parameters.getString("businessDate");

        if (!StringUtils.hasText(businessDate)) {
            throw new JobParametersInvalidException(
                    "Required parameter 'businessDate' is missing or blank");
        }
    }
}
~~~

Gắn validator vào Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step importStep,
        JobParametersValidator importJobParametersValidator) {

    return new JobBuilder("customerImportJob", jobRepository)
            .validator(importJobParametersValidator)
            .start(importStep)
            .build();
}
~~~

Nếu thiếu inputFile hoặc businessDate, Job bị từ chối với JobParametersInvalidException. Step không cần chờ tới lúc reader được tạo mới phát hiện lỗi.

Đây là lựa chọn tốt cho các tham số xác định tập dữ liệu hoặc cách xử lý bắt buộc. Thông báo lỗi nên nêu tên parameter và yêu cầu cụ thể, không chỉ ghi "invalid parameters".

## 5. Dùng DefaultJobParametersValidator

Với quy tắc đơn giản, Spring Batch cung cấp DefaultJobParametersValidator để khai báo key bắt buộc và key tùy chọn.

Ví dụ:

~~~java
@Bean
public JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
            new String[] {"inputFile", "businessDate"},
            new String[] {"mode", "encoding"});
}
~~~

Trong ví dụ:

- inputFile và businessDate là key bắt buộc.
- mode và encoding là key tùy chọn được chấp nhận.
- Các key ngoài danh sách được xử lý theo quy tắc của validator.

Có thể gắn validator này vào Job bằng phương thức validator(...) như ví dụ ở phần trước.

Nếu cần kiểm tra chuỗi blank, định dạng ngày, miền giá trị hoặc quan hệ giữa nhiều parameter, custom JobParametersValidator thường rõ ràng hơn. Ví dụ mode chỉ được phép là FULL hoặc DELTA; businessDate phải đúng định dạng; inputFile phải được cung cấp khi mode là FULL.

## 6. Parameter tùy chọn có thể nhận null

Nếu parameter thực sự tùy chọn, có thể inject vào kiểu tham chiếu như String, Long, Integer hoặc Boolean và xử lý null rõ ràng.

Ví dụ:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return input -> {
        if (tenantId == null) {
            return convertWithoutTenant(input);
        }

        return convertForTenant(input, tenantId);
    };
}
~~~

Khi tenantId không được truyền, bean nhận null và xử lý theo nhánh mặc định của nghiệp vụ.

Với kiểu số, dùng wrapper:

~~~java
@Value("#{jobParameters['maxRows']}")
Integer maxRows
~~~

Nếu maxRows thiếu, giá trị có thể là null. Không dùng primitive int nếu tham số có thể không tồn tại vì primitive không biểu diễn được null và việc chuyển đổi có thể thất bại.

Tương tự, dùng Boolean thay cho boolean nếu cần phân biệt "không được truyền" với false.

## 7. Dùng default value trong SpEL

Với parameter tùy chọn có default hợp lý, có thể dùng toán tử Elvis của SpEL:

~~~java
@Bean
@StepScope
public ItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['encoding'] ?: 'UTF-8'}")
        String encoding,

        @Value("#{jobParameters['pageSize'] ?: 500}")
        Integer pageSize) {

    return buildReader(encoding, pageSize);
}
~~~

Nếu key không có hoặc giá trị biểu thức là null, default được dùng:

- encoding mặc định là UTF-8.
- pageSize mặc định là 500.

Default value nên phản ánh quy tắc nghiệp vụ hoặc kỹ thuật được xác định rõ. Không nên đặt default tùy tiện cho một parameter xác định tập dữ liệu, tenant hoặc ngày nghiệp vụ vì Job có thể chạy trên một tập dữ liệu khác với ý định của người gọi.

Với chuỗi, hãy kiểm tra thêm blank. Không giả định mọi chuỗi chỉ có khoảng trắng đều tương đương null trong mọi biểu thức. Có thể inject giá trị rồi chuẩn hóa và xác thực bằng StringUtils.hasText.

## 8. Default trong SpEL không thêm parameter vào JobParameters

Đây là khác biệt quan trọng.

Giả sử Job được launch mà không có encoding:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .toJobParameters();
~~~

Bean dùng:

~~~java
@Value("#{jobParameters['encoding'] ?: 'UTF-8'}")
String encoding
~~~

Trong bean, encoding nhận UTF-8. Tuy nhiên, JobParameters vẫn không có key encoding. Default chỉ được áp dụng lúc inject; nó không sửa JobParameters và không tự trở thành identifying parameter.

Điều này có hệ quả:

- JobInstance identity không thay đổi vì default được inject.
- JobRepository không coi default là một parameter đã được người gọi truyền.
- Một lần restart dùng code mới với default khác có thể xử lý khác lần chạy trước.
- Log JobParameters có thể không hiển thị giá trị default đã được áp dụng.

Nếu default ảnh hưởng kết quả nghiệp vụ, hãy cân nhắc chuẩn hóa tham số trước khi launch, truyền giá trị tường minh hoặc lưu cấu hình đã resolve vào ExecutionContext để restart nhất quán.

## 9. Phân biệt parameter tùy chọn với non-identifying parameter

Non-identifying parameter vẫn là parameter có mặt trong JobParameters. Nó chỉ không tham gia xác định JobInstance.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("mode", "FULL", false)
        .toJobParameters();
~~~

mode tồn tại và có thể inject bình thường:

~~~java
@Value("#{jobParameters['mode']}")
String mode
~~~

Nếu không truyền mode, key mới thực sự bị thiếu. Cờ identifying=false không có nghĩa parameter là optional; nó chỉ điều khiển danh tính JobInstance.

Một parameter có thể là:

- Bắt buộc và identifying.
- Bắt buộc nhưng non-identifying.
- Tùy chọn và identifying khi được cung cấp.
- Tùy chọn và non-identifying.

Đây là hai trục thiết kế khác nhau: tính bắt buộc thuộc validation nghiệp vụ; identifying thuộc danh tính JobInstance và restart.

Nếu mode làm thay đổi tập dữ liệu hoặc kết quả nghiệp vụ, hãy cân nhắc đưa nó vào identifying parameters. Nếu mode không identifying, phải bảo đảm nó không thay đổi giữa các lần restart theo cách làm kết quả thiếu nhất quán.

## 10. Kiểm tra parameter trực tiếp trong JobParameters

Ngoài SpEL, có thể đọc JobParameters trong code thông qua JobParameters API.

Ví dụ trong validator:

~~~java
String inputFile = parameters.getString("inputFile");
Long maxRows = parameters.getLong("maxRows");
Double threshold = parameters.getDouble("threshold");
~~~

Các getter trả về null khi key tương ứng không có giá trị phù hợp. Hãy kiểm tra null trước khi sử dụng.

Nếu cần phân biệt key không tồn tại với key tồn tại nhưng có giá trị rỗng, có thể kiểm tra map parameters:

~~~java
boolean supplied =
        parameters.getParameters().containsKey("mode");

String mode = parameters.getString("mode");
~~~

Sau đó xử lý từng trạng thái:

~~~java
if (!supplied) {
    // Người gọi không truyền mode.
} else if (!StringUtils.hasText(mode)) {
    // Có key nhưng giá trị rỗng hoặc blank.
} else {
    // Có giá trị.
}
~~~

API map và kiểu JobParameter có thể khác nhau giữa các phiên bản Spring Batch. Hãy dùng getter phù hợp với kiểu dữ liệu của parameter trong phiên bản dự án.

## 11. Parameter sai tên cũng giống như không tồn tại

Một lỗi phổ biến là sai chính tả hoặc khác chữ hoa/thường giữa nơi launch và nơi inject.

Ví dụ caller truyền:

~~~java
.addString("inputFile", "/data/orders.csv", true)
~~~

nhưng bean đọc:

~~~java
@Value("#{jobParameters['inputfile']}")
String inputFile
~~~

Tên key khác nhau nên biểu thức không tìm thấy giá trị. Kết quả tương tự trường hợp parameter bị bỏ quên.

Nên khai báo tên key thành constant để dùng thống nhất:

~~~java
public final class ImportParameterNames {

    public static final String INPUT_FILE = "inputFile";
    public static final String BUSINESS_DATE = "businessDate";
    public static final String MODE = "mode";

    private ImportParameterNames() {
    }
}
~~~

Khi tạo JobParameters và viết validator, hãy dùng cùng tên key. SpEL annotation vẫn cần chuỗi literal, nên có thể bổ sung test để phát hiện tên không đồng nhất.

## 12. Parameter tồn tại nhưng sai kiểu

Một key có thể tồn tại nhưng giá trị không chuyển được sang kiểu Java mà bean yêu cầu.

Ví dụ caller truyền:

~~~java
.addString("pageSize", "many", false)
~~~

nhưng bean inject:

~~~java
@Value("#{jobParameters['pageSize']}")
Integer pageSize
~~~

Spring cần chuyển giá trị sang Integer. Chuỗi "many" không phải số hợp lệ, vì vậy việc tạo scoped bean có thể thất bại do lỗi conversion.

Cách tốt hơn là dùng đúng kiểu JobParameter ngay khi launch:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addLong("pageSize", 500L, false)
        .toJobParameters();
~~~

Hoặc validate chuỗi trước khi chuyển đổi nếu parameter được nhận từ nguồn văn bản. Thông báo lỗi nên nêu tên parameter và kiểu mong đợi.

Không nên bắt mọi conversion exception rồi âm thầm thay bằng 0. Giá trị 0 có thể có ý nghĩa khác với việc thiếu parameter hoặc truyền dữ liệu sai.

## 13. Dùng giá trị mặc định có kiểm soát

Nếu default là hợp lý, hãy gom logic chuẩn hóa vào một cấu hình rõ ràng thay vì rải toán tử Elvis ở nhiều bean.

Ví dụ:

~~~java
public record ImportOptions(
        String encoding,
        int pageSize,
        boolean dryRun) {
}
~~~

Bean tạo options:

~~~java
@Bean
@JobScope
public ImportOptions importOptions(
        @Value("#{jobParameters['encoding'] ?: 'UTF-8'}")
        String encoding,

        @Value("#{jobParameters['pageSize'] ?: 500}")
        Integer pageSize,

        @Value("#{jobParameters['dryRun'] ?: false}")
        Boolean dryRun) {

    if (pageSize == null || pageSize < 1) {
        throw new IllegalArgumentException(
                "pageSize must be greater than zero");
    }

    return new ImportOptions(
            encoding,
            pageSize,
            dryRun);
}
~~~

Các Step có thể dùng chung ImportOptions trong cùng JobExecution.

Ví dụ trên cho thấy default có thể được áp dụng khi inject, sau đó vẫn cần validate miền giá trị. Default không thay thế validation: pageSize = -1 vẫn không hợp lệ dù key tồn tại.

Nếu các tùy chọn này cần giữ nguyên qua restart, hãy bảo đảm giá trị resolve được lưu hoặc có quy tắc default ổn định qua các phiên bản ứng dụng.

## 14. Không dùng default để che giấu parameter bắt buộc

Ví dụ không nên làm:

~~~java
@Value("#{jobParameters['tenantId'] ?: 'DEFAULT_TENANT'}")
String tenantId
~~~

Nếu tenantId xác định dữ liệu khách hàng cần truy cập, việc tự động dùng DEFAULT_TENANT có thể làm Job đọc hoặc ghi dữ liệu của tenant sai.

Với parameter bắt buộc:

- Không cung cấp default giả.
- Dùng JobParametersValidator.
- Báo lỗi rõ ràng trước khi Step chạy.
- Không tiếp tục khi thiếu thông tin xác định phạm vi dữ liệu.

Default chỉ phù hợp khi có giá trị mặc định được nghiệp vụ phê duyệt và mọi lần chạy không truyền parameter đều phải dùng đúng giá trị đó.

## 15. Kiểm tra ExecutionContext key không tồn tại

Cơ chế tương tự cũng áp dụng cho Job ExecutionContext và Step ExecutionContext.

Ví dụ:

~~~java
@Value("#{jobExecutionContext['reportId']}")
Long reportId
~~~

Nếu key reportId chưa được Step trước ghi hoặc chưa được promote, giá trị có thể là null.

Với Step ExecutionContext:

~~~java
@Value("#{stepExecutionContext['fromId']}")
Long fromId
~~~

Nếu Partitioner không tạo fromId, worker không có giá trị cận dưới. Đừng dùng default tùy tiện vì worker có thể đọc sai phạm vi dữ liệu.

Khi đọc context key được tạo bởi Step trước:

- Xác nhận Step trước đã ghi key.
- Xác nhận promotion listener đã chạy nếu key cần chuyển lên Job context.
- Kiểm tra điều kiện flow để Step tiêu thụ chỉ chạy sau khi producer thành công.
- Validate key trước khi tạo reader hoặc writer.

Nếu key bắt buộc, hãy fail rõ ràng thay vì mặc định 0 hoặc chuỗi rỗng.

## 16. Lỗi missing parameter xảy ra ở thời điểm nào?

Thời điểm phát hiện phụ thuộc cách inject và validation:

| Cách xử lý | Thời điểm phát hiện |
|---|---|
| JobParametersValidator | Trước khi Step bắt đầu |
| Inject reference type rồi kiểm tra trong factory method | Khi scoped bean được tạo |
| Dùng null rồi gọi method mà không kiểm tra | Khi code sử dụng giá trị |
| Inject primitive hoặc kiểu không chuyển đổi được | Khi Spring resolve/conversion giá trị |
| Đọc ExecutionContext key chưa được tạo | Khi scoped bean được resolve hoặc code truy cập |

Nên phát hiện sớm. Với inputFile, tenantId hoặc businessDate bắt buộc, validator giúp người vận hành thấy lỗi ngay khi launch thay vì chờ reader khởi tạo.

Nếu parameter phụ thuộc kết quả của Step trước, validator ở cấp Job không thể xác nhận một key chưa được tạo tại thời điểm launch. Khi đó cần validate sau khi Step trước hoàn tất, trước khi Step tiêu thụ key bắt đầu.

## 17. Phân biệt lỗi scope chưa active và parameter thiếu

Hai lỗi có nguyên nhân khác nhau:

**Scope chưa active**: Spring không có JobExecution hoặc StepExecution gắn với thread hiện tại để resolve target bean. Thường xảy ra khi truy cập scoped bean ngoài lifecycle batch hoặc từ thread không mang context phù hợp.

**Parameter thiếu**: Scope đã hoạt động, nhưng key được truy cập không có trong JobParameters hoặc ExecutionContext. Biểu thức có thể trả về null hoặc gây lỗi conversion nếu target yêu cầu kiểu không phù hợp.

Cách chẩn đoán:

1. Xác định lỗi xuất hiện khi ApplicationContext khởi động hay khi Step chạy.
2. Kiểm tra bean có @JobScope/@StepScope phù hợp không.
3. Kiểm tra scope đã active trên thread hiện tại chưa.
4. In danh sách tên parameter được phép log, tránh log giá trị nhạy cảm.
5. So sánh chính xác tên key ở caller và biểu thức.
6. Kiểm tra parameter có được truyền trong lần launch này không.
7. Kiểm tra kiểu JobParameter và kiểu Java đích.

Không khắc phục lỗi scope bằng cách thêm default parameter. Cũng không khắc phục missing key bằng cách thay đổi thread hoặc scope nếu scope vốn đã hoạt động đúng.

## 18. Kiểm thử parameter bắt buộc và tùy chọn

Nên kiểm thử validator độc lập:

~~~java
@Test
void rejectsMissingInputFile() {
    JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters));
}
~~~

Kiểm thử giá trị blank:

~~~java
@Test
void rejectsBlankInputFile() {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "   ", true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters));
}
~~~

Kiểm thử parameter tùy chọn:

~~~java
@Test
void acceptsMissingOptionalMode() {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "/data/orders.csv", true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    assertDoesNotThrow(
            () -> validator.validate(parameters));
}
~~~

Ngoài validator, cần kiểm thử scoped bean thực tế để xác nhận:

- Parameter có mặt được inject đúng.
- Parameter thiếu nhận null hoặc default theo thiết kế.
- Parameter blank được xử lý đúng.
- Parameter sai kiểu tạo lỗi dễ hiểu.
- SpEL key viết sai bị phát hiện.
- Job không chạy Step khi parameter bắt buộc thiếu.

## 19. Kiểm thử default value trong StepScope

Có thể dùng Spring Batch test support hoặc chạy Job bằng JobLauncherTestUtils để kích hoạt scope đúng lifecycle.

Ví dụ test ở cấp Job:

~~~java
@Test
void usesDefaultEncodingWhenParameterIsMissing() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", testFile.toString(), true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    JobExecution execution =
            jobLauncherTestUtils.launchJob(parameters);

    assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    // Xác nhận reader được tạo với encoding UTF-8
}
~~~

Để xác nhận giá trị được inject, có thể kiểm tra hành vi reader hoặc một component test probe. Tránh chỉ gọi constructor bean trực tiếp vì cách đó không kiểm thử late binding.

Cũng nên test trường hợp caller truyền encoding khác UTF-8 và trường hợp encoding là chuỗi blank.

## 20. Parameter thiếu trong lần restart

Job restart thường dùng cùng JobInstance, được xác định bởi tên Job và identifying JobParameters. Khi restart, caller cần cung cấp đúng identifying parameters để Spring Batch tìm JobInstance cũ.

Nếu một parameter identifying bị thiếu, JobLauncher có thể tìm một JobInstance khác hoặc không tìm được instance cần restart. Nếu một parameter non-identifying bị thiếu hoặc thay đổi, danh tính JobInstance có thể vẫn giữ nguyên nhưng hành vi của Job có thể thay đổi.

Ví dụ lần đầu:

~~~java
JobParameters firstRun = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("encoding", "UTF-8", false)
        .toJobParameters();
~~~

Khi restart, nếu encoding không được truyền và code dùng default khác, reader có thể đọc file khác cách lần đầu. Vì vậy, tham số tùy chọn vẫn cần ổn định nếu ảnh hưởng kết quả.

Với giá trị default có ảnh hưởng đến kết quả, cân nhắc:

- Truyền giá trị tường minh ngay từ đầu.
- Chuẩn hóa JobParameters trước khi launch.
- Lưu giá trị đã resolve trong Job ExecutionContext.
- Giữ default tương thích qua phiên bản ứng dụng.
- Ghi nhận cấu hình hiệu lực trong log/audit để điều tra restart.

## 21. Ghi log khi parameter thiếu

Thông báo lỗi nên cho biết key nào thiếu và nó bắt buộc hay tùy chọn. Không nên log toàn bộ JobParameters nếu có token, mật khẩu hoặc dữ liệu nhạy cảm.

Ví dụ:

~~~java
if (!StringUtils.hasText(inputFile)) {
    log.error("Required JobParameter 'inputFile' is missing");
    throw new JobParametersInvalidException(
            "Required JobParameter 'inputFile' is missing");
}
~~~

Với parameter tùy chọn, có thể ghi nhận giá trị mặc định được áp dụng:

~~~java
if (!StringUtils.hasText(encoding)) {
    log.info("No encoding supplied; using UTF-8");
    encoding = "UTF-8";
}
~~~

Nếu cần truy vết, ghi JobExecution ID, Job name và tên parameter. Chỉ ghi giá trị parameter khi chính sách dữ liệu cho phép.

## 22. Những lỗi thường gặp

### Giả định mọi JobParameters đều tồn tại

Key không được truyền có thể resolve thành null. Hãy xác định bắt buộc hay tùy chọn và validate tương ứng.

### Dùng primitive cho parameter tùy chọn

int, long và boolean không biểu diễn null. Dùng Integer, Long hoặc Boolean khi cần phân biệt thiếu với giá trị 0/false.

### Chỉ kiểm tra null cho chuỗi

Chuỗi rỗng hoặc whitespace vẫn có thể không hợp lệ. Dùng StringUtils.hasText hoặc quy tắc chuẩn hóa tương ứng.

### Dùng default cho parameter xác định tenant hoặc dữ liệu

Job có thể xử lý sai phạm vi. Parameter xác định dữ liệu nên được xác thực bắt buộc.

### Nhầm non-identifying với optional

Non-identifying parameter vẫn có thể được truyền và inject. Cờ identifying chỉ quyết định JobInstance identity.

### Nhầm default SpEL với JobParameters đã lưu

Default chỉ áp dụng cho bean lúc inject. Nó không thêm key vào JobParameters hoặc metadata.

### Viết sai tên key

Tên key phân biệt chữ hoa/thường. Dùng constants và test validator để phát hiện.

### Inject sai kiểu

Giá trị có thể tồn tại nhưng conversion thất bại. Dùng JobParameter đúng kiểu và validate miền giá trị.

### Dùng property placeholder thay cho SpEL

JobParameters được truy cập bằng SpEL execution context. Cú pháp property placeholder dùng cho cấu hình ứng dụng có ý nghĩa khác.

### Để lỗi phát sinh sâu trong reader

Thiếu inputFile có thể chỉ lộ ra khi reader mở resource. Dùng JobParametersValidator để fail sớm.

### Thay đổi default giữa các lần restart

JobInstance có thể giữ nguyên nhưng hành vi thay đổi. Giữ cấu hình hiệu lực nhất quán hoặc lưu giá trị đã resolve.

## 23. Quy trình xử lý parameter không tồn tại

Khi một bean cần parameter, hãy xác định:

1. Key có bắt buộc theo nghiệp vụ không?
2. Caller có luôn truyền key trong JobParameters không?
3. Key có thể tồn tại nhưng rỗng hoặc blank không?
4. Key có tham gia identifying JobInstance không?
5. Kiểu JobParameter có phù hợp kiểu Java được inject không?
6. Nếu tùy chọn, default có được nghiệp vụ phê duyệt không?
7. Default có làm thay đổi tập dữ liệu hoặc kết quả khi restart không?
8. Có thể kiểm tra key bằng JobParametersValidator trước khi Step chạy không?
9. Nếu key đến từ ExecutionContext, Step producer đã ghi và promote đúng chưa?
10. Log có chỉ rõ tên key mà không làm lộ dữ liệu nhạy cảm không?

Parameter không tồn tại là tình huống bình thường cần được thiết kế có chủ đích. Với tham số bắt buộc, JobParametersValidator giúp từ chối lần chạy sớm và đưa ra lỗi rõ ràng. Với tham số tùy chọn, dùng kiểu tham chiếu, default có kiểm soát và kiểm tra blank/type conversion. Luôn phân biệt tính bắt buộc với identifying parameter, vì hai thuộc tính này giải quyết hai vấn đề khác nhau: validation đầu vào và danh tính JobInstance.
