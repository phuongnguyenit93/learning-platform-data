# bindingFailure: phân biệt lỗi chuyển kiểu và lỗi validation trong Spring

Khi ứng dụng Spring nhận dữ liệu từ request, có hai câu hỏi khác nhau:

1. **Binding có chuyển và gán được dữ liệu vào đối tượng Java hay không?** Ví dụ, chuỗi `"abc"` không thể chuyển thành `Integer` cho thuộc tính `age`.
2. **Giá trị sau khi binding có thỏa quy tắc kiểm tra hay không?** Ví dụ, `age=16` chuyển thành số nguyên thành công nhưng vi phạm yêu cầu tuổi tối thiểu 18.

Cả hai có thể được lưu dưới dạng `FieldError` trong `Errors`/`BindingResult`. Thuộc tính `FieldError.isBindingFailure()` giúp phân biệt **lỗi phát sinh ở bước binding** với **lỗi phát sinh ở bước validation** khi xử lý các đối tượng lỗi chuẩn của Spring.

## 1. Hai giai đoạn: chuyển kiểu trước, kiểm tra ràng buộc sau

Với một model có field `Integer age`, request gửi dữ liệu dạng chuỗi; binder phải chuyển sang kiểu Java trước khi kiểm tra các quy tắc như tuổi tối thiểu.

~~~text
Dữ liệu gửi đến ("age")
              |
              v
       DataBinder / WebDataBinder
              |
       Chuyển kiểu và gán field
           /          \
          /            \
    "abc" -> lỗi      "16" -> 16
        |                  |
   FieldError               v
   bindingFailure=true   Validator / Bean Validation
   code=typeMismatch        |
                        16 < 18
                            |
                        FieldError
                        bindingFailure=false
                        code=age.tooYoung / Min
          \                  /
           \                /
            BindingResult (Errors)
                      |
              hasErrors(), getFieldErrors()
                      |
                view / API response
~~~

Cần phân biệt: **lỗi binding không đồng nghĩa với mọi lỗi ở form**. Spring cũng có thể tạo binding error khi thiếu một field được cấu hình là bắt buộc (`required`) hoặc khi setter gây lỗi lúc gán (`methodInvocation`), tùy cấu hình binder. `typeMismatch` là trường hợp tiêu biểu, dễ quan sát nhất.

| Tiêu chí | Lỗi chuyển kiểu / binding | Lỗi validation |
| --- | --- | --- |
| Giai đoạn phát hiện | Khi binder đọc và gán dữ liệu vào property Java | Sau binding, khi áp dụng quy tắc kiểm tra |
| Ví dụ | `age="abc"` đối với `Integer age` | `age="16"` đã thành `Integer 16` nhưng nhỏ hơn 18 |
| Lỗi chuẩn của Spring | `FieldError`, thường có code tổng quát `typeMismatch` | `FieldError` hoặc `ObjectError`, có thể có code `Min`, `NotBlank` hoặc mã tùy chỉnh |
| `FieldError.isBindingFailure()` | `true` | `false` với các lỗi validation thông thường |
| Giá trị đã gán thành công? | Có thể chưa gán được field bị lỗi | Thường đã chuyển và gán được kiểu đích |
| Việc cần làm | Sửa định dạng/kiểu đầu vào, hoặc logic conversion | Sửa giá trị cho đúng constraint/nghiệp vụ |

Lưu ý `isBindingFailure()` là thuộc tính trên **`FieldError`**, không phải phương thức trên mọi `ObjectError`. Lỗi validation ở cấp đối tượng, ví dụ ngày bắt đầu lớn hơn ngày kết thúc, có thể chỉ là `ObjectError` do `errors.reject(...)` tạo ra.

## 2. Các API cần đọc trong `Errors` và `BindingResult`

`org.springframework.validation.Errors` cho phép hỏi có lỗi hay chưa và đọc chi tiết:

~~~java
if (errors.hasErrors()) {
    int total = errors.getErrorCount();
    for (FieldError fieldError : errors.getFieldErrors()) {
        String field = fieldError.getField();
        String code = fieldError.getCode();
        boolean bindingFailed = fieldError.isBindingFailure();
        // Dùng dữ liệu này để phân loại hoặc tạo response.
    }
}
~~~

Đây là đoạn minh họa bên trong nơi đã có biến `Errors errors` và import `org.springframework.validation.FieldError`.

Các phương thức hữu ích:

| API | Ý nghĩa |
| --- | --- |
| `hasErrors()` / `getErrorCount()` | Có bất kỳ lỗi nào hay đếm tổng số lỗi |
| `hasFieldErrors("age")` / `getFieldErrors("age")` | Kiểm tra hoặc lấy **tất cả** lỗi của field `age` |
| `getFieldError("age")` | Lấy một lỗi field đầu tiên (có thể bỏ sót lỗi khác) |
| `getFieldErrors()` | Lấy các lỗi gắn với field |
| `getGlobalErrors()` | Lấy các lỗi ở cấp đối tượng |
| `getAllErrors()` | Lấy cả `FieldError` lẫn `ObjectError` |
| `FieldError.getField()` | Tên field bị lỗi |
| `FieldError.getRejectedValue()` | Giá trị bị từ chối, có thể là chuỗi thô khi binding hỏng |
| `FieldError.getCode()` | Mã mặc định/tổng quát, tức **mã cuối** trong danh sách codes |
| `FieldError.getCodes()` | Các khóa thông báo được thử theo thứ tự, từ cụ thể đến tổng quát |
| `FieldError.isBindingFailure()` | Cờ phân biệt lỗi binding với validation |

`BindingResult` mở rộng `Errors` và được Spring MVC/DataBinder sử dụng để mang thêm thông tin binding. Một `BindingResult` có thể chứa **nhiều loại lỗi cùng lúc**. Do đó:

~~~java
for (ObjectError error : result.getAllErrors()) {
    if (error instanceof FieldError fieldError) {
        if (fieldError.isBindingFailure()) {
            // Lỗi của bước binding (ví dụ typeMismatch).
        } else {
            // Lỗi validation được gắn với một field.
        }
    } else {
        // ObjectError ở cấp object: không có isBindingFailure().
    }
}
~~~

Đoạn trên cần import `org.springframework.validation.ObjectError`, `FieldError`; biến `result` là một `BindingResult` đã được cung cấp. Không ép kiểu trực tiếp `(FieldError) error` với mọi phần tử của `getAllErrors()` vì object-level error không phải `FieldError`.

**Quan trọng:** `isBindingFailure()` chỉ mô tả **nguồn gốc của đối tượng lỗi đó**, không cho biết request có hợp lệ về nghiệp vụ hay không. Một form có thể có lỗi chuyển kiểu ở `age` và lỗi validation ở `name` cùng lúc. Muốn quyết định form có được xử lý tiếp hay không, dùng `result.hasErrors()`.

## 3. Spring sinh lỗi `typeMismatch` như thế nào?

Với JavaBean:

~~~java
public class RegistrationForm {
    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Nếu binder nhận `age=abc`, bộ chuyển đổi mặc định không thể biến chữ cái thành số nguyên. Thông thường, Spring ghi `FieldError` có:

~~~text
objectName          = registrationForm
field               = age
rejectedValue       = "abc"
bindingFailure      = true
code (getCode())    = typeMismatch
~~~

Dưới cấu hình `DefaultMessageCodesResolver` thường dùng, `getCodes()` có các ứng viên như:

~~~text
typeMismatch.registrationForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

Danh sách chính xác phụ thuộc object name, kiểu field, nested path và cấu hình resolver. `getCode()` trả mã **cuối** trong danh sách (ví dụ `typeMismatch`); `getCodes()` giữ các ứng viên để dịch thông báo theo context. Không xem `getCode()` là mã cụ thể đầu tiên.

Với `age=16`, conversion thành `Integer 16` thành công. Khi `@Min(18)` hoặc custom validator từ chối giá trị, `FieldError` tương ứng có `bindingFailure=false`. Nếu dùng `Errors.rejectValue("age", "age.tooYoung")`, mã tổng quát cuối sẽ là `age.tooYoung`; Bean Validation `@Min` thường dùng mã tổng quát `Min`. Mã validation phản ánh **quy tắc**, mã binding phản ánh **khó khăn trong chuyển/gán dữ liệu**.

Không phải mọi dữ liệu nhập sai dạng đều tạo `FieldError` ở đây. Ví dụ payload JSON sai cú pháp hoặc không deserialize được qua Jackson có thể bị Spring MVC báo `HttpMessageNotReadableException` **trước khi hình thành đối tượng để validate**. Lỗi `@RequestParam Integer age` cũng có đường xử lý conversion/exception riêng. Khi thiết kế handler, cần biết loại tham số của endpoint.

## 4. Ví dụ chạy được: `DataBinder` tạo hai loại `FieldError`

Ví dụ sau sử dụng **Java 17+ và Spring Framework 6.x**. `DataBinder` cho phép tái hiện luồng binding + validation mà không cần HTTP server.

Mã hoàn chỉnh cho file `src/main/java/BindingFailureDemo.java` trong một dự án Maven đã có `spring-context`:

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public final class BindingFailureDemo {

    public static class RegistrationForm {
        private Integer age;

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

    public static class AgeValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            // Nếu age đã bị lỗi chuyển kiểu, không báo thêm lỗi tuổi.
            boolean conversionFailed = errors.getFieldErrors("age")
                    .stream()
                    .anyMatch(FieldError::isBindingFailure);
            if (conversionFailed) {
                return;
            }

            RegistrationForm form = (RegistrationForm) target;
            Integer age = form.getAge();
            if (age != null && age < 18) {
                errors.rejectValue(
                        "age",
                        "age.tooYoung",
                        "Tuổi phải từ 18 trở lên.");
            }
        }
    }

    private static void inspect(String rawAge) {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setAllowedFields("age");
        binder.addValidators(new AgeValidator());

        MutablePropertyValues properties = new MutablePropertyValues();
        properties.add("age", rawAge);

        binder.bind(properties);      // 1. Chuyển kiểu và gán age.
        binder.validate();            // 2. Chạy AgeValidator.

        BindingResult result = binder.getBindingResult();

        System.out.println("input=" + rawAge);
        System.out.println("boundAge=" + form.getAge());
        System.out.println("errors=" + result.getErrorCount());

        for (FieldError error : result.getFieldErrors()) {
            System.out.println(error.getField()
                    + " | " + error.getCode()
                    + " | bindingFailure=" + error.isBindingFailure());
        }
    }

    public static void main(String[] args) {
        inspect("abc"); // Không đổi được sang Integer.
        inspect("16");  // Đổi thành Integer nhưng < 18.
        inspect("20");  // Binding và validation đều thành công.
    }
}
~~~

Trong Maven, `spring-context` kéo theo các module Spring liên quan, trong đó có `spring-beans` và `spring-core`. Ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>6.2.0</version>
</dependency>
~~~

Sau khi có `pom.xml` cấu hình Java 17+ và dependency trên, đặt file đúng đường dẫn rồi chạy:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=BindingFailureDemo
~~~

Dữ liệu in ra từ chương trình:

~~~text
input=abc
boundAge=null
errors=1
age | typeMismatch | bindingFailure=true
input=16
boundAge=16
errors=1
age | age.tooYoung | bindingFailure=false
input=20
boundAge=20
errors=0
~~~

**Vì sao từng trường hợp cho kết quả như vậy?**

1. **`"abc"`:** `binder.bind(...)` không gán được cho `Integer age` nên thêm một `FieldError` với `bindingFailure=true`. Field vẫn `null` trong form mới. `AgeValidator` thấy lỗi conversion ở chính field đó và không tạo lỗi tuổi tối thiểu giả.
2. **`"16"`:** binder chuyển thành `Integer 16`, không có binding error. `AgeValidator` thấy `age < 18`, gọi `errors.rejectValue(...)` và tạo `FieldError` với `bindingFailure=false`.
3. **`"20"`:** binder chuyển thành `Integer 20` và validator không phát hiện vi phạm; `getErrorCount()==0`.

Đặt `binder.setAllowedFields("age")` để ví dụ chỉ cho phép binding đúng field cần dùng; trong ứng dụng web, giới hạn các property có thể gán từ input là một biện pháp quan trọng khi sử dụng model binding. Trong chương trình này, **chính `binder.bind(...)` tạo lỗi chuyển kiểu, còn `binder.validate()` chạy custom validator**. Nếu chỉ tạo `BeanPropertyBindingResult` rồi gọi `validate()` mà không có quá trình binding lỗi, bạn sẽ không tự nhiên nhận được `typeMismatch`.

Ví dụ cố ý bỏ qua lỗi validation tuổi tối thiểu khi `age` đã có lỗi conversion. Spring **không bảo đảm mọi custom validator sẽ tự bỏ qua field không bind được**; `binder.validate()` vẫn là lời gọi yêu cầu chạy các validator đã đăng ký. Tác giả validator phải xử lý `null`, lỗi binding trước đó và nguy cơ ghi hai thông báo khó hiểu cho cùng input.

## 5. Phân loại lỗi mà không dựa vào chuỗi thông báo

Trong tầng giao diện hoặc API, nên phân loại dựa vào metadata thay vì so sánh văn bản lỗi:

~~~java
for (FieldError error : result.getFieldErrors()) {
    String kind = error.isBindingFailure()
            ? "BINDING"
            : "VALIDATION";

    System.out.println(kind + ": "
            + error.getField() + " - " + error.getCode());
}
~~~

Ví dụ, một API có thể chuẩn hóa hai nhóm thành:

~~~json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "age",
      "kind": "BINDING",
      "code": "typeMismatch",
      "message": "Tuổi phải là số nguyên."
    }
  ]
}
~~~

Đây là **response do ứng dụng thiết kế**, không phải định dạng `BindingResult` tự serialize. Khi request khác có `age=16`, API có thể giữ cấu trúc nhưng dùng `kind="VALIDATION"`, `code="age.tooYoung"` và thông báo yêu cầu đủ 18 tuổi.

Nếu nghiệp vụ cần mã lỗi công khai ổn định theo thời gian, hãy xây lớp ánh xạ riêng từ các mã Spring sang mã API. `getCode()` của Spring có ích để xử lý, nhưng các mã có thể thay đổi khi thay validator, resolver hoặc quy tắc. Không để client phụ thuộc vào chuỗi tiếng Việt/tiếng Anh của `getDefaultMessage()`.

### Không phải cứ `typeMismatch` là phải kiểm tra text

Có thể nhận biết lỗi chuyển kiểu thường thấy qua `"typeMismatch"` hoặc danh sách `getCodes()`. Tuy nhiên, để phân biệt **nguồn gốc binding/validation của một `FieldError`**, ưu tiên `isBindingFailure()`. Mã lỗi do cấu hình hoặc lập trình viên đặt có thể thay đổi; khi viết custom validator, thậm chí có thể dùng trùng tên một mã binding cho một vi phạm validation. **Mã lỗi diễn đạt loại vi phạm; cờ `bindingFailure` ghi nhận bản chất lỗi theo Spring.**

### Giá trị bị từ chối có ý nghĩa khác nhau

`FieldError.getRejectedValue()` có thể chứa:

- `"abc"` (chuỗi chưa chuyển được) trong trường hợp `age=abc`.
- Giá trị Java `Integer 16` trong trường hợp đã bind được nhưng fail validation.

Đừng vội dùng `getRejectedValue()` làm giá trị đã được gán cho bean: khi conversion thất bại, giá trị bean có thể vẫn `null` hoặc giữ giá trị trước đó. Cũng không tự động log hoặc trả giá trị bị từ chối nếu field có password, token, thông tin cá nhân hay dữ liệu nhạy cảm.

## 6. Dùng `BindingResult` trong Spring MVC

Với một form dùng `@ModelAttribute`, Spring MVC thực hiện data binding, kiểm tra ràng buộc khi được yêu cầu, rồi cung cấp `BindingResult`. Đoạn minh họa dưới đây giả định `RegistrationForm` và `AgeValidator` là bean/class được tích hợp trong ứng dụng Spring MVC, có import phù hợp:

~~~java
@Controller
class RegistrationController {

    private final AgeValidator ageValidator;

    RegistrationController(AgeValidator ageValidator) {
        this.ageValidator = ageValidator;
    }

    @InitBinder("registrationForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("age");
        binder.addValidators(ageValidator);
    }

    @PostMapping("/registrations")
    String register(
            @Validated @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult result,
            Model model) {

        if (result.hasErrors()) {
            model.addAttribute("fieldErrors", result.getFieldErrors());
            return "registration-form";
        }

        return "redirect:/registrations/success";
    }
}
~~~

Các class và annotation tương ứng thuộc Spring MVC/Spring Validation: `@Controller`, `@InitBinder`, `@PostMapping`, `@Validated`, `@ModelAttribute`, `WebDataBinder`, `BindingResult` và `Model`. `AgeValidator` cần được tạo dưới dạng bean (hoặc đăng ký theo cơ chế khác) để inject. Đây là **đoạn tích hợp với view/template**, không phải ứng dụng đầy đủ tự chạy từ một file.

Những điểm quan trọng:

- `BindingResult result` phải đứng **ngay sau** tham số model được binding/validate trong chữ ký handler. Khi thiếu `BindingResult` phù hợp, Spring MVC có thể chuyển lỗi thành exception qua tuyến xử lý khác.
- `@Validated` (hoặc trong trường hợp phù hợp `@Valid`) báo Spring cần chạy validation. `@InitBinder` chỉ đăng ký/configure binder, bản thân việc đăng ký không đủ để mặc định chạy validator trong mọi tình huống.
- Khi request form gửi `age=abc`, `result.getFieldErrors("age")` thường có lỗi binding với `isBindingFailure()==true`; gửi `age=16` có thể có lỗi validation tương ứng với `false`.
- `BindingResult` có thể chứa cả lỗi conversion lẫn validation của các field khác nhau. Controller nên dựa vào `hasErrors()` để từ chối xử lý và trình bày đầy đủ các lỗi liên quan.
- Khi xử lý nhiều field, không nhất thiết hủy bỏ mọi validation chỉ vì một field lỗi binding; hãy để validator kiểm tra các field đã chuyển thành công và tránh tạo lỗi lặp trên field hỏng.

Trường hợp JSON request body khác về đường đi. Ví dụ:

~~~http
POST /registrations
Content-Type: application/json

{"age":"abc"}
~~~

Nếu Jackson không chuyển được `"abc"` thành `Integer` khi deserialize `@RequestBody`, Spring có thể ném `HttpMessageNotReadableException` trước khi chạy validator của model. **Không được giả định** exception này sẽ sinh `FieldError.isBindingFailure()==true` trong một `BindingResult` giống `@ModelAttribute`. Với `@RequestBody @Valid`, lỗi constraint trên đối tượng đã deserialize thành công thường đi qua `MethodArgumentNotValidException`. API cần exception handler riêng cho JSON không đọc được, field constraint và tham số URL chuyển kiểu lỗi khi cần.

## 7. Chuyển lỗi thành thông báo thân thiện theo locale

`FieldError` vừa giữ mã để máy xử lý, vừa triển khai `MessageSourceResolvable`. Có thể truyền trực tiếp vào `MessageSource` để chọn thông báo theo `Locale` và chuỗi mã dự phòng:

~~~java
for (FieldError fieldError : result.getFieldErrors()) {
    String translated = messageSource.getMessage(fieldError, locale);
    // Gắn translated vào view hoặc API response.
}
~~~

Giả sử object tên `registrationForm`:

~~~properties
# messages_vi.properties
typeMismatch.registrationForm.age=Tuổi phải là số nguyên hợp lệ.
typeMismatch=Giá trị nhập không đúng kiểu.
age.tooYoung.registrationForm.age=Bạn phải từ 18 tuổi trở lên.
age.tooYoung=Giá trị không đạt yêu cầu tuổi tối thiểu.
~~~

Khi `age=abc`, message source có thể chọn `typeMismatch.registrationForm.age`; khi `age=16`, có thể chọn `age.tooYoung.registrationForm.age`. `getCodes()` cho biết danh sách candidate chính xác. Nên có bundle mặc định (ví dụ `messages.properties`) và bản dịch cho locale hỗ trợ. Không dựa hoàn toàn vào `getDefaultMessage()` của lỗi binding: đôi khi nó chứa nội dung kỹ thuật của converter/exception.

`Locale` của request có thể đến từ resolver hoặc header `Accept-Language` theo cấu hình Spring MVC. **Ngôn ngữ thông báo không làm thay đổi `isBindingFailure()`, mã lỗi hay quy tắc validation.** Nếu dự án cần mã API riêng, hãy chuẩn hóa song song với việc dịch nội dung hiển thị.

## 8. Lỗi đồng thời và điều cần thận trọng

Một request có thể khiến nhiều lỗi cùng tồn tại:

- `age=abc` không chuyển kiểu được → `FieldError(age, typeMismatch, true)`.
- `email=""` đã bind thành chuỗi nhưng vi phạm `@NotBlank` → `FieldError(email, NotBlank, false)`.
- `startDate > endDate` vi phạm quy tắc kết hợp → có thể là `ObjectError` tạo bởi `reject(...)`.

Vì vậy không nên đánh dấu toàn bộ request là “BINDING” chỉ vì nhìn thấy một lỗi conversion. **Phân loại theo từng lỗi**, sau đó dùng `result.hasErrors()` cho quyết định tổng thể. Có thể chọn HTTP 400 cho toàn bộ input không hợp lệ trong ứng dụng web; nhưng cách đóng gói lỗi, HTTP status và mã công khai là hợp đồng của API do ứng dụng quyết định.

Một custom validator cần phòng lỗi thứ cấp:

~~~java
@Override
public void validate(Object target, Errors errors) {
    RegistrationForm form = (RegistrationForm) target;

    boolean conversionFailed = errors.getFieldErrors("age")
            .stream()
            .anyMatch(FieldError::isBindingFailure);

    if (!conversionFailed && form.getAge() != null
            && form.getAge() < 18) {
        errors.rejectValue("age", "age.tooYoung");
    }
}
~~~

Nếu một bộ kiểm tra bắt buộc có `@NotNull`, cân nhắc liệu lỗi thiếu input có cần hiện đồng thời với lỗi không chuyển được input hay không. Quy tắc bỏ qua duplicate nên được thiết kế rõ, tránh giấu một lỗi khác có ích cho người dùng.

**Phân biệt với suppressed field:** `BindingResult.getSuppressedFields()` phản ánh những field bị binder ngăn binding (ví dụ không thuộc allowlist). Đó là thông tin an toàn/binding policy riêng, không phải danh sách `FieldError` có `bindingFailure=true`. Không dùng `isBindingFailure()` để suy ra mọi field đã bị chặn hay request đã bị từ chối vì mass assignment.

## 9. Cách kiểm thử

Với chương trình mục 4, kiểm thử ba input `"abc"`, `"16"` và `"20"` đảm bảo đồng thời hai lớp hành vi. Những assertion quan trọng:

~~~java
// Trường hợp type mismatch sau binder.bind("age" = "abc"):
FieldError mismatch = bindingResult.getFieldError("age");
assert mismatch != null;
assert mismatch.isBindingFailure();
assert "typeMismatch".equals(mismatch.getCode());

// Trường hợp "16" được bind, nhưng bị AgeValidator loại:
FieldError invalidAge = validationResult.getFieldError("age");
assert invalidAge != null;
assert !invalidAge.isBindingFailure();
assert "age.tooYoung".equals(invalidAge.getCode());
~~~

Đây là **đoạn assertion minh họa trong test**, với hai `BindingResult` đã được tạo từ các ca kiểm thử tương ứng. Nếu dùng Java `assert`, nhớ bật `-ea` khi chạy. Trong dự án thực tế, JUnit `assertNotNull`/`assertTrue`/`assertFalse` sẽ thuận tiện hơn vì luôn đánh giá điều kiện.

Bảng kịch bản để kiểm tra endpoint:

| Dữ liệu và đường vào | Kỳ vọng |
| --- | --- |
| Form `age=abc` → `@ModelAttribute` | `BindingResult` có lỗi `typeMismatch`, `bindingFailure=true` |
| Form `age=16` → `@ModelAttribute` + validator | `bindingFailure=false`, mã quy tắc `age.tooYoung` |
| Form `age=20` | Không có lỗi ở field `age` |
| Form nhiều field, một conversion lỗi và một constraint lỗi | Giữ đủ lỗi; phân loại riêng từng `FieldError` |
| JSON không deserialize được | Handler dành cho parse/deserialization exception; không giả định có cùng `BindingResult` |
| Lỗi object-level | Đọc `getGlobalErrors()`, không ép thành `FieldError` |
| Thiếu message key cụ thể | Hiển thị thông báo dự phòng phù hợp, không lộ stack trace hoặc thông báo nội bộ |

## 10. Những nhầm lẫn thường gặp

1. **Dùng `errors.hasErrors()` để kết luận tất cả lỗi đều do validation.** Cách này gộp cả conversion và quy tắc; hãy kiểm tra `FieldError.isBindingFailure()` theo từng field error.
2. **Kiểm tra `error.getCode().equals("typeMismatch")` là đủ cho mọi loại lỗi binding.** `typeMismatch` là trường hợp phổ biến, còn có `required`, `methodInvocation`, và mã có thể tùy biến; hãy đọc thêm cờ `isBindingFailure()`.
3. **Cho rằng validation chỉ chạy khi binding hoàn toàn thành công.** `DataBinder.validate()` là lời gọi riêng; các validator được đăng ký có thể tiếp tục kiểm tra khi `BindingResult` đã chứa lỗi. Custom validator cần bảo vệ trước `null` và kết quả binding lỗi.
4. **Hiển thị `getRejectedValue()` trực tiếp cho người dùng.** Nó có thể chứa dữ liệu thô chưa chuyển được và thông tin nhạy cảm; nên chuyển thành thông báo thân thiện, log có kiểm soát.
5. **Nhầm `getCode()` với candidate cụ thể đầu tiên.** `getCode()` là mã cuối/tổng quát; dùng `getCodes()` hoặc `MessageSource.getMessage(error, locale)` để tận dụng thứ tự tra cứu.
6. **Ép toàn bộ `getAllErrors()` thành `FieldError`.** Các lỗi cấp đối tượng cũng nằm trong đó; dùng `instanceof FieldError`.
7. **Áp dụng logic của form binding cho JSON body và query parameter.** Chúng có thể dùng exception khác; handler cần thiết kế theo loại tham số và nguồn lỗi.
8. **Ghi lỗi trùng cho field chưa chuyển được.** Nếu field đã có `bindingFailure=true`, validator nghiệp vụ không nên suy đoán từ giá trị `null` rồi báo thêm “tuổi quá nhỏ”. Hãy chọn chính sách lỗi rõ ràng.

## 11. Nguyên tắc áp dụng

Khi cần giải thích hoặc trả về lỗi input, hãy giữ nguyên ranh giới xử lý: **binder chuyển kiểu và ghi lỗi binding, validator kiểm tra quy tắc và ghi lỗi validation, `BindingResult` tập hợp cả hai**. Phân tích từng `FieldError` bằng `isBindingFailure()`; kiểm tra toàn bộ `BindingResult` bằng `hasErrors()`; và chỉ tạo thông báo hiển thị từ mã lỗi/thông tin phù hợp với locale.

Nguồn API chính thức: [`FieldError` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/FieldError.html), [`DataBinder` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html), [`DefaultMessageSourceResolvable` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/DefaultMessageSourceResolvable.html).
