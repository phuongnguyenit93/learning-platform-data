# Kiểm tra tùy chọn thiếu, kiểu sai và ràng buộc chéo

Một command Spring Shell nhận dữ liệu từ dòng lệnh qua nhiều bước: phân tích cú pháp, ánh xạ option, chuyển đổi kiểu, kiểm tra constraint rồi mới gọi method. Khi kiểm thử, cần phân biệt các bước này để xác định lỗi xuất hiện ở đâu và bảo đảm command không gọi nghiệp vụ khi đầu vào chưa hợp lệ.

Bài học dùng Spring Shell 3.3.x và mô hình annotation legacy `@ShellMethod`/`@ShellOption`. Ví dụ kiểm thử sử dụng `@ShellTest`, `ShellTestClient` và `ShellAssertions`. Các nguyên tắc về parser, conversion và Bean Validation cũng áp dụng cho command được đăng ký bằng `CommandRegistration`.

## 1. Phân biệt các lớp lỗi đầu vào

Giả sử có command tạo báo cáo theo khoảng số thứ tự:

~~~text
report range --from 10 --to 20
~~~

Đầu vào phải đi qua các bước sau:

~~~text
Dòng lệnh người dùng
        |
        v
1. Parser
   - Tìm command
   - Nhận diện option
   - Kiểm tra option bắt buộc và arity
        |
        v
2. Type conversion
   - Chuyển chuỗi "10" thành Integer
   - Chuyển chuỗi "20" thành Integer
        |
        v
3. Bean Validation
   - Kiểm tra từng tham số
   - Kiểm tra quan hệ giữa nhiều tham số
        |
        v
4. Command method
        |
        v
5. Service / nghiệp vụ
~~~

Mỗi lớp có một loại lỗi riêng:

| Lớp | Ví dụ đầu vào sai | Kết quả mong đợi |
|---|---|---|
| Parser | Thiếu `--to` bắt buộc | Báo thiếu option; method không chạy |
| Parser | Dùng option không được khai báo hoặc sai arity | Báo lỗi cú pháp; method không chạy |
| Conversion | `--from abc` trong khi kiểu là `int` | Báo không chuyển đổi được; method không chạy |
| Validation từng tham số | `--from 0` khi có `@Min(1)` | Báo vi phạm constraint; method không chạy |
| Validation chéo | `--from 20 --to 10` | Báo quan hệ giữa hai tham số không hợp lệ |
| Nghiệp vụ | Khoảng hợp lệ về cú pháp nhưng không có dữ liệu | Service trả kết quả nghiệp vụ tương ứng |

Đừng kiểm tra tất cả các lỗi bằng một test duy nhất. Mỗi test nên tạo đúng một điều kiện sai để chỉ ra lớp chịu trách nhiệm.

## 2. Khai báo option bắt buộc và tùy chọn

Trong mô hình legacy annotation của Spring Shell 3.x, option không có default value là bắt buộc theo mặc định:

~~~java
@ShellMethod(key = "report range", value = "Tạo báo cáo theo khoảng.")
public String range(
        @ShellOption(value = "from") int from,
        @ShellOption(value = "to") int to) {
    return "Đã tạo báo cáo từ " + from + " đến " + to + ".";
}
~~~

Nếu người dùng bỏ qua `--to`, Spring Shell từ chối command trước khi gọi method. Thông báo theo tài liệu 3.1.6 có dạng:

~~~text
Missing mandatory option --to.
~~~

Nếu muốn option tùy chọn trong mô hình legacy, dùng sentinel `ShellOption.NULL`:

~~~java
@ShellMethod(key = "report preview")
public String preview(
        @ShellOption(value = "format",
                defaultValue = ShellOption.NULL) String format) {
    String selectedFormat = format == null ? "text" : format;
    return "Format: " + selectedFormat;
}
~~~

Một option có default value sẽ được gán giá trị mặc định khi người dùng không truyền. Khi test option thiếu, hãy kiểm tra đúng hợp đồng:

- Option bắt buộc: phải báo thiếu khi không được truyền.
- Option tùy chọn: command nhận `null` hoặc giá trị mặc định theo khai báo.
- Option có default: không được nhầm việc bỏ qua option với lỗi parser.

Trong mô hình annotation mới, có thể khai báo rõ `@Option(required = true)` hoặc `@Option(required = false)`. Với programmatic model, dùng `.required()` hoặc `.required(false)` trên option spec.

## 3. Kiểm tra chuyển đổi kiểu

Parser nhận token đầu vào dưới dạng chuỗi. Spring Shell dùng ConversionService để chuyển chuỗi sang kiểu Java của tham số command.

Ví dụ tham số kiểu số:

~~~java
@ShellMethod(key = "stock reserve")
public String reserve(
        @ShellOption(value = "quantity") int quantity) {
    return "Đã nhận số lượng: " + quantity;
}
~~~

Các đầu vào:

~~~text
stock reserve --quantity 12
~~~

`12` được chuyển thành `int` và command có thể chạy.

~~~text
stock reserve --quantity twelve
~~~

`twelve` không thể chuyển thành số nguyên. Lỗi xảy ra trước khi gọi method command; service không được phép thực thi.

Các kiểu thường cần kiểm tra:

| Kiểu Java | Đầu vào hợp lệ | Đầu vào sai thường gặp |
|---|---|---|
| `int` / `Integer` | `12`, `-4` | `twelve`, `1.5` |
| `long` / `Long` | Số nguyên trong phạm vi | Chuỗi chữ, số vượt phạm vi |
| `boolean` / `Boolean` | `true`, `false` | Giá trị không được hỗ trợ |
| `enum` | Tên hằng enum hợp lệ | Giá trị không khớp hằng nào |
| `String` | Chuỗi bất kỳ | Thường không có lỗi chuyển đổi |
| `Path` | Đường dẫn có thể chuyển đổi | Giá trị sai định dạng theo converter |

Kiểm thử conversion nên xác nhận hai điều: shell hiển thị lỗi phù hợp và command/service không bị gọi. Không nên chỉ kiểm tra output; một handler lỗi tùy chỉnh có thể thay đổi thông báo nhưng không được để nghiệp vụ chạy với dữ liệu sai.

## 4. Kiểm tra constraint trên từng tham số

Spring Shell tích hợp Bean Validation. Các annotation constraint trên tham số command được kiểm tra trước khi method thực thi.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ReportExportCommands {

    @ShellMethod(key = "report export", value = "Xuất báo cáo.")
    public String export(
            @ShellOption(value = "name") @NotBlank String name,
            @ShellOption(value = "limit") @Min(1) @Max(500) int limit) {
        return "Xuất " + limit + " dòng cho báo cáo " + name + ".";
    }
}
~~~

Một số constraint thường dùng:

| Constraint | Ý nghĩa | Ví dụ |
|---|---|---|
| `@NotNull` | Giá trị không được null | Đối tượng bắt buộc |
| `@NotBlank` | Chuỗi không được null, rỗng hoặc chỉ có khoảng trắng | Tên báo cáo |
| `@NotEmpty` | Chuỗi/collection/array không được rỗng | Danh sách ID |
| `@Min(1)` | Số phải từ 1 trở lên | Số lượng |
| `@Max(500)` | Số không vượt quá 500 | Giới hạn bản ghi |
| `@Positive` | Số phải dương | Số trang |
| `@Size(min=3, max=40)` | Giới hạn độ dài hoặc kích thước | Tên người dùng |
| `@Pattern(...)` | Chuỗi phải khớp biểu thức chính quy | Mã SKU |

Ví dụ, `--limit 0` vi phạm `@Min(1)`. Spring Shell hiển thị thông báo constraint và không gọi method. Trong môi trường chạy thực tế, thông báo có thể bao gồm tên option, constraint bị vi phạm và giá trị đầu vào.

Để Bean Validation hoạt động, ứng dụng cần có implementation của Jakarta Bean Validation trên classpath. Với Spring Boot, dependency phổ biến là:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-validation")
~~~

Nếu chỉ có API mà không có provider, các annotation có thể không được thực thi như mong đợi. Hãy xác nhận dependency validation của ứng dụng trước khi kết luận test của Spring Shell sai.

## 5. Kiểm tra ràng buộc chéo giữa nhiều option

Constraint trên từng tham số không thể diễn đạt đầy đủ mọi quy tắc. Ví dụ, cả `--from` và `--to` đều có thể là số dương nhưng khoảng vẫn sai nếu `from > to`.

Spring Shell 3.x hỗ trợ các annotation Bean Validation ở cấp method và thực hiện validation trước khi command method chạy. Có thể tạo cross-parameter constraint để kiểm tra quan hệ giữa các tham số.

### 5.1. Tạo annotation ValidRange

Annotation được đặt trên method command:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = ValidRangeValidator.class)
@Target({ElementType.METHOD, ElementType.CONSTRUCTOR, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidRange {

    String message() default "from phải nhỏ hơn hoặc bằng to";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

### 5.2. Viết cross-parameter validator

Validator nhận mảng các tham số theo thứ tự khai báo trong method. Ví dụ command dưới đây khai báo `from` trước `to`, nên `values[0]` là `from` và `values[1]` là `to`.

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;

@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class ValidRangeValidator
        implements ConstraintValidator<ValidRange, Object[]> {

    @Override
    public boolean isValid(
            Object[] values,
            ConstraintValidatorContext context) {

        if (values == null || values.length != 2) {
            return false;
        }

        if (values[0] == null || values[1] == null) {
            return true;
        }

        if (!(values[0] instanceof Integer from)
                || !(values[1] instanceof Integer to)) {
            return false;
        }

        if (from <= to) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                "from phải nhỏ hơn hoặc bằng to")
                .addConstraintViolation();
        return false;
    }
}
~~~

Cross-parameter validator chỉ kiểm tra quan hệ giữa các giá trị. Các constraint riêng như `@Min(1)` vẫn chịu trách nhiệm kiểm tra từng giá trị. Nếu giá trị không đúng kiểu hoặc không có mặt, parser/conversion/parameter constraint phải báo lỗi tương ứng; validator chéo không nên ép kiểu mù hoặc ném exception.

### 5.3. Gắn constraint vào command

~~~java
import jakarta.validation.constraints.Min;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ReportCommands {

    private final ReportService reportService;

    public ReportCommands(ReportService reportService) {
        this.reportService = reportService;
    }

    @ValidRange
    @ShellMethod(key = "report range", value = "Tạo báo cáo theo khoảng.")
    public String range(
            @ShellOption(value = "from") @Min(1) int from,
            @ShellOption(value = "to") @Min(1) int to) {

        reportService.generate(from, to);
        return "Đã tạo báo cáo từ " + from + " đến " + to + ".";
    }
}
~~~

Các trường hợp:

| Lệnh | Kết quả |
|---|---|
| `report range --from 10 --to 20` | Hợp lệ |
| `report range --from 20 --to 10` | Vi phạm ràng buộc chéo |
| `report range --from 0 --to 10` | Vi phạm `@Min(1)` |
| `report range --from abc --to 10` | Lỗi chuyển đổi kiểu |
| `report range --from 10` | Thiếu option bắt buộc `--to` |

Không đặt logic ghi dữ liệu trong validator. Validator nên là hàm kiểm tra thuần, không gọi repository, không gửi request và không thay đổi trạng thái.

## 6. Chuẩn bị Spring Shell test support

Spring Shell cung cấp hai module test:

- `spring-shell-test` chứa client, screen và assertion cho shell.
- `spring-shell-test-autoconfigure` cung cấp annotation `@ShellTest` và cấu hình test tự động.

Ví dụ dependency Gradle:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.shell:spring-shell-test")
    testImplementation("org.springframework.shell:spring-shell-test-autoconfigure")
}
~~~

Dùng Spring Shell BOM tương ứng với phiên bản ứng dụng để các module có cùng phiên bản. Không trộn module test 3.x với runtime 4.x.

`@ShellTest` dựng Spring test context tập trung vào các thành phần shell. Có thể dùng `@ContextConfiguration` để chỉ định cấu hình ứng dụng và inject `ShellTestClient`:

~~~java
@ShellTest
@ContextConfiguration(classes = ReportTestApplication.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReportCommandTests {

    @Autowired
    ShellTestClient client;
}
~~~

`@DirtiesContext` giúp mỗi test có context riêng, hữu ích khi shell client hoặc trạng thái command được giữ lại giữa các lần chạy.

## 7. Kiểm tra option bắt buộc bị thiếu

Dùng non-interactive session để gửi command và đọc màn hình sau khi chạy:

~~~java
@Test
void missingToOptionDoesNotCallService() {
    var session = client.nonInterative(
            "report", "range", "--from", "10").run();

    await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                    .containsText("Missing mandatory option --to"));

    verifyNoInteractions(reportService);
}
~~~

Test này kiểm tra hai điều:

1. Người dùng nhận được thông báo thiếu option bắt buộc.
2. Service không được gọi khi parser chưa tạo được bộ tham số hợp lệ.

Trong Spring Shell 3.3.x, tên API của non-interactive session là `nonInterative(...)`. Tên có lỗi chính tả này được đổi thành `nonInteractive(...)` từ Spring Shell 3.4.2. Khi viết test cho phiên bản khác, kiểm tra API của đúng version thay vì sao chép tên phương thức từ bản mới.

## 8. Kiểm tra giá trị sai kiểu

Gửi chuỗi không thể chuyển sang kiểu số:

~~~java
@Test
void invalidIntegerDoesNotCallService() {
    var session = client.nonInterative(
            "report", "range",
            "--from", "abc",
            "--to", "20").run();

    await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
            assertThat(session.screen().lines()).isNotEmpty());

    verifyNoInteractions(reportService);
}
~~~

Thông báo conversion có thể khác theo converter, JDK và phiên bản Spring Shell. Nếu ứng dụng có thông báo lỗi chuẩn hóa riêng, hãy kiểm tra đúng chuỗi đó. Trong mọi trường hợp, test phải xác nhận method/service không được chạy.

Có thể mở rộng với enum:

~~~java
enum OutputFormat {
    CSV, JSON
}

@ShellMethod(key = "report export")
public String export(
        @ShellOption(value = "format") OutputFormat format) {
    return "Format: " + format;
}
~~~

Test với `--format XML` phải xác nhận conversion thất bại và không gọi phần xuất báo cáo. Với các converter tùy chỉnh, nên có unit test riêng cho converter và integration test cho đường đi qua shell.

## 9. Kiểm tra constraint đơn và constraint chéo

Một test cho `@Min(1)`:

~~~java
@Test
void zeroFromViolatesParameterConstraint() {
    var session = client.nonInterative(
            "report", "range",
            "--from", "0",
            "--to", "10").run();

    await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                    .containsText("The following constraints were not met"));

    verifyNoInteractions(reportService);
}
~~~

Test cho cross-parameter constraint:

~~~java
@Test
void reversedRangeViolatesCrossParameterConstraint() {
    var session = client.nonInterative(
            "report", "range",
            "--from", "20",
            "--to", "10").run();

    await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                    .containsText("from phải nhỏ hơn hoặc bằng to"));

    verifyNoInteractions(reportService);
}
~~~

Và test đường đi hợp lệ:

~~~java
@Test
void validRangeCallsService() {
    var session = client.nonInterative(
            "report", "range",
            "--from", "10",
            "--to", "20").run();

    await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                    .containsText("Đã tạo báo cáo từ 10 đến 20"));

    verify(reportService).generate(10, 20);
}
~~~

Các ví dụ dùng `await()` vì terminal emulator cập nhật màn hình bất đồng bộ. Không nên giả định ngay sau `run()` thì mọi ký tự đã xuất hiện trên screen; hãy đợi điều kiện cần kiểm tra.

## 10. Ví dụ cấu trúc test đầy đủ

Một cấu hình test có thể import command cần kiểm tra và thay service bằng mock:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
@Import(ReportCommands.class)
class ReportTestApplication {
}

@ShellTest
@ContextConfiguration(classes = ReportTestApplication.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReportCommandTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ReportService reportService;

    @Test
    void missingRequiredOptionDoesNotCallService() {
        var session = client.nonInterative(
                "report", "range", "--from", "10").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Missing mandatory option --to"));

        verifyNoInteractions(reportService);
    }

    @Test
    void invalidTypeDoesNotCallService() {
        var session = client.nonInterative(
                "report", "range",
                "--from", "abc", "--to", "20").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                assertThat(session.screen().lines()).isNotEmpty());

        verifyNoInteractions(reportService);
    }

    @Test
    void invalidRangeDoesNotCallService() {
        var session = client.nonInterative(
                "report", "range",
                "--from", "20", "--to", "10").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("from phải nhỏ hơn hoặc bằng to"));

        verifyNoInteractions(reportService);
    }

    @Test
    void validRangeCallsService() {
        var session = client.nonInterative(
                "report", "range",
                "--from", "10", "--to", "20").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Đã tạo báo cáo từ 10 đến 20"));

        verify(reportService).generate(10, 20);
    }
}
~~~

Đây là cấu trúc minh họa. Trong dự án thực tế, đặt `ReportCommands`, `ReportService`, `ValidRange` và `ValidRangeValidator` ở package phù hợp; import đúng các lớp JUnit, Mockito, Spring Boot Test, Awaitility và Jakarta Validation.

## 11. Khi nào dùng ShellTestClient và khi nào dùng unit test?

Không phải mọi quy tắc đều cần khởi chạy shell:

| Phạm vi kiểm thử | Công cụ phù hợp | Điều cần xác nhận |
|---|---|---|
| Hàm kiểm tra khoảng | JUnit thuần | `from <= to` |
| Cross-parameter validator | Jakarta Validator hoặc JUnit | Validator trả violation đúng khi khoảng đảo ngược |
| Converter tùy chỉnh | Unit test | Chuỗi được chuyển thành đúng kiểu hoặc bị từ chối |
| Parser và option binding | `ShellTestClient` | Thiếu option, option thừa, arity và cú pháp |
| Type conversion qua shell | `ShellTestClient` | Chuỗi sai kiểu không đi vào command |
| Bean Validation qua shell | `ShellTestClient` | Constraint được hiển thị và method không chạy |
| Command và service integration | `@ShellTest` + mock/spy | Request đúng được chuyển sang service |
| Chạy artifact từ tiến trình OS | Spring Boot integration test | Output và exit code của tiến trình |

Unit test nhanh và tập trung vào logic. Integration test với `ShellTestClient` chứng minh parser, conversion, validation và result handler được nối đúng trong ứng dụng.

## 12. Ma trận kiểm thử đầu vào

Với command `report range`, nên có ít nhất các trường hợp:

| Nhóm | Đầu vào | Kết quả mong đợi | Service |
|---|---|---|---|
| Hợp lệ | `--from 10 --to 20` | Thành công | Gọi một lần |
| Thiếu option | Chỉ có `--from 10` | Báo thiếu `--to` | Không gọi |
| Thiếu giá trị option | Có `--to` nhưng không có giá trị | Lỗi cú pháp/arity | Không gọi |
| Sai kiểu | `--from abc --to 20` | Lỗi conversion | Không gọi |
| Sai kiểu enum | `--format XML` | Lỗi conversion | Không gọi |
| Sai constraint đơn | `--from 0 --to 20` | Vi phạm `@Min(1)` | Không gọi |
| Sai constraint chéo | `--from 20 --to 10` | Vi phạm `@ValidRange` | Không gọi |
| Giá trị biên hợp lệ | `--from 1 --to 1` | Thành công nếu nghiệp vụ cho phép | Gọi một lần |
| Giá trị biên không hợp lệ | `--to 0` | Vi phạm `@Min(1)` | Không gọi |
| Option không tồn tại | `--form 10` | Báo option không hợp lệ hoặc cú pháp sai | Không gọi |

Nếu command có default value, hãy thêm test khi option được bỏ qua để xác nhận giá trị mặc định được áp dụng. Nếu option optional, kiểm tra cả trường hợp `null` và trường hợp được truyền rõ ràng.

## 13. Kiểm tra không có side effect khi đầu vào sai

Một lỗi phổ biến là test chỉ kiểm tra thông báo lỗi. Điều đó chưa chứng minh service không chạy trước khi lỗi được hiển thị.

Với command có ghi dữ liệu, gửi email, gọi API hoặc xóa tài nguyên, hãy dùng mock/spy để kiểm tra:

- `verifyNoInteractions(service)` khi parser, conversion hoặc validation thất bại.
- `verify(service).execute(expectedRequest)` khi đầu vào hợp lệ.
- Không có repository write hoặc external call trong nhánh lỗi.
- Không có bản ghi một phần khi validation thất bại.

Với nghiệp vụ nhiều bước, kiểm tra transaction rollback ở tầng service bằng integration test riêng. `ShellTestClient` xác nhận đường đi qua CLI; nó không thay thế kiểm thử transaction hoặc persistence.

## 14. Kiểm tra thông báo lỗi mà không làm test mong manh

Thông báo lỗi của parser và converter có thể thay đổi giữa các phiên bản Spring Shell, Spring Framework và JDK. Nên ưu tiên:

1. Kiểm tra thông báo nghiệp vụ do ứng dụng tự định nghĩa khi đó là contract công khai.
2. Với lỗi framework, kiểm tra một phần ổn định của thông báo thay vì toàn bộ stack trace.
3. Xác nhận command method hoặc service không được gọi.
4. Không so sánh toàn bộ terminal screen nếu thứ tự dòng, màu ANSI hoặc prompt có thể thay đổi.
5. Nếu dùng custom exception resolver, kiểm tra cả mã lỗi và thông báo do resolver tạo.

Ví dụ, với cross-parameter validator do ứng dụng sở hữu, có thể kiểm tra nguyên văn `from phải nhỏ hơn hoặc bằng to`. Với lỗi conversion, kiểm tra screen có nội dung chẩn đoán và service không có tương tác; không phụ thuộc vào toàn bộ câu exception của converter.

## 15. Lỗi thường gặp khi kiểm thử

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ gọi trực tiếp command method | Bỏ qua parser và conversion | Gửi dòng lệnh qua `ShellTestClient` |
| Không khai báo option bắt buộc rõ ràng | Test thiếu option không phản ánh hợp đồng | Dùng `@ShellOption` không có default hoặc khai báo required |
| Dùng primitive cho option tùy chọn | Không phân biệt rõ giá trị vắng mặt và giá trị mặc định | Dùng wrapper như `Integer` và quy định default |
| Không có Bean Validation provider | Constraint không chạy | Thêm `spring-boot-starter-validation` |
| Chỉ test từng tham số | Bỏ sót quy tắc giữa nhiều tham số | Dùng method-level cross-parameter constraint |
| Validator ép kiểu không an toàn | Input lỗi gây exception trong validator | Kiểm tra null, số lượng và kiểu trước khi cast |
| Validator gọi service | Test validation tạo side effect | Giữ validator thuần, không truy cập hệ thống |
| Chỉ kiểm tra thông báo lỗi | Service vẫn có thể đã được gọi | Dùng Mockito verifyNoInteractions |
| Đọc screen ngay lập tức | Test chập chờn do terminal cập nhật bất đồng bộ | Dùng Awaitility hoặc chờ điều kiện |
| Dùng sai tên API theo version | Test không biên dịch | 3.3.x dùng `nonInterative`; từ 3.4.2 dùng `nonInteractive` |
| So sánh toàn bộ màn hình | Test dễ hỏng do prompt, màu và format | Kiểm tra đoạn text ổn định |

## 16. Quy trình kiểm thử đề xuất

1. Xác định option nào bắt buộc, option nào tùy chọn và option nào có default.
2. Ghi rõ kiểu Java của từng option và converter được sử dụng.
3. Xác định constraint riêng cho từng tham số.
4. Xác định quan hệ giữa nhiều tham số, ví dụ `from <= to`.
5. Viết unit test cho validator và converter tùy chỉnh.
6. Dùng `@ShellTest` và `ShellTestClient` để gửi command như người dùng.
7. Kiểm tra lỗi thiếu option, thiếu giá trị, sai kiểu, vi phạm constraint đơn và constraint chéo.
8. Dùng mock/spy xác nhận service không được gọi khi đầu vào sai.
9. Kiểm tra command hợp lệ gọi service đúng một lần với dữ liệu đúng.
10. Chạy thêm integration test cho transaction hoặc side effect cần bảo vệ.

## 17. Tổng kết

Kiểm thử đầu vào của Spring Shell cần phân biệt lỗi parser, lỗi chuyển đổi kiểu, constraint trên từng tham số và ràng buộc chéo. Option bắt buộc bị thiếu phải bị từ chối trước khi method chạy; chuỗi sai kiểu phải thất bại ở ConversionService; constraint Bean Validation phải được đánh giá trước khi gọi command method.

Spring Shell 3.x hỗ trợ Bean Validation trên tham số và annotation ở cấp method. Với quy tắc như `from <= to`, có thể tạo cross-parameter constraint bằng `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`. Dùng `@ShellTest` và `ShellTestClient` để kiểm tra toàn bộ đường đi qua shell, sau đó xác nhận service không có tương tác khi đầu vào sai. Khi test command hợp lệ, kiểm tra service nhận đúng giá trị và được gọi đúng số lần.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 — Optional Value and Mandatory Options](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html) — option bắt buộc, option tùy chọn và thông báo thiếu option.
- [Spring Shell 3.1.6 — Validation](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html) — Bean Validation trên tham số và method trước khi command thực thi.
- [Spring Shell 3.3.4 — Validation](https://docs.spring.io/spring-shell/reference/3.3/options/validation.html) — tích hợp Bean Validation cho command parameters.
- [Spring Shell 3.3.4 — Testing Basics](https://docs.spring.io/spring-shell/reference/3.3/testing/basics.html) — test interactive/non-interactive bằng `@ShellTest` và `ShellTestClient`.
- [ShellTest API 3.3.0](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/autoconfigure/ShellTest.html) — annotation cấu hình shell test context.
- [ShellTestClient API 3.3.0](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html) — tạo interactive và non-interactive test session.
- [ShellAssertions API 3.3.0](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellAssertions.html) — assertion cho nội dung hiển thị trên shell screen.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html) — tích hợp Bean Validation và method validation trong Spring.
