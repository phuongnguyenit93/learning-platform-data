# ValidationUtils.rejectIfEmpty và rejectIfEmptyOrWhitespace trong Spring Validator

Khi viết một `org.springframework.validation.Validator`, ta thường cần báo lỗi nếu người dùng bỏ trống một trường bắt buộc. Spring Framework cung cấp hai phương thức tiện ích dạng `static` trong `org.springframework.validation.ValidationUtils`:

- `ValidationUtils.rejectIfEmpty(...)`: từ chối giá trị `null` hoặc chuỗi rỗng `""`.
- `ValidationUtils.rejectIfEmptyOrWhitespace(...)`: từ chối thêm cả chuỗi **chỉ có các ký tự khoảng trắng**, chẳng hạn `"   "`, tab hoặc xuống dòng.

Cả hai phương thức đưa lỗi của **một field** vào đối tượng `Errors`; chúng không trả về `boolean`, không tự ném ngoại lệ validation, không tự sửa dữ liệu và không thay thế toàn bộ quy trình validate một object. Đây là các helper đơn giản nhưng rất hữu ích để viết quy tắc bắt buộc nhập trong một Spring `Validator`.

## 1. Phân biệt chính xác hai phương thức

Giả sử một form có trường `name` kiểu `String`. Bảng sau xét **cùng một giá trị** với mỗi phương thức:

| Giá trị của `name` | `rejectIfEmpty` có báo lỗi? | `rejectIfEmptyOrWhitespace` có báo lỗi? | Lý do |
| --- | :---: | :---: | --- |
| `null` | Có | Có | Không có giá trị |
| `""` | Có | Có | Chuỗi dài 0 ký tự |
| `" "` | Không | Có | Có độ dài nhưng chỉ là khoảng trắng |
| `"   "` | Không | Có | Không chứa ký tự có nội dung |
| `"\t\n"` | Không | Có | Chỉ có tab và xuống dòng |
| `" An "` | Không | Không | Có các ký tự chữ |
| `"0"` | Không | Không | Chuỗi có ký tự `0` |

**Chọn nhanh:** nếu trường văn bản cần có nội dung thật, thường dùng `rejectIfEmptyOrWhitespace`. `rejectIfEmpty` phù hợp khi chỉ muốn cấm `null`/`""`, còn giá trị chứa khoảng trắng có ý nghĩa riêng trong bài toán hoặc sẽ được xử lý ở bước khác.

Với hai helper này, giá trị `" An "` **không bị cắt khoảng trắng**: chúng chỉ kiểm tra và đăng ký lỗi, không gọi `strip()` hay `trim()` để ghi ngược vào object.

### Cơ chế so sánh bên trong

Ở mức ý tưởng, hành vi tương đương:

~~~java
// Minh họa điều kiện; không phải toàn bộ mã nguồn Spring.
Object value = errors.getFieldValue(field);

boolean empty = value == null
        || !org.springframework.util.StringUtils.hasLength(value.toString());

boolean emptyOrWhitespace = value == null
        || !org.springframework.util.StringUtils.hasText(value.toString());
~~~

- `hasLength` kiểm tra có **ít nhất một ký tự**; `"   "` vẫn có độ dài.
- `hasText` kiểm tra có **ít nhất một ký tự không phải whitespace**.
- `Errors#getFieldValue(field)` lấy giá trị thông qua thông tin binding/đối tượng mà `Errors` đang quản lý. Vì vậy chỉ cần truyền `Errors` và tên field; không cần truyền đối tượng mục tiêu thêm lần nữa.

Trong implementation thực tế, khi điều kiện bị vi phạm, Spring gọi `errors.rejectValue(field, errorCode, errorArgs, defaultMessage)`. Cách xác định whitespace dựa trên hành vi `StringUtils.hasText` / `Character.isWhitespace` của Java; một số ký tự Unicode đặc biệt như **non-breaking space** không nhất thiết được coi là whitespace. Nếu dữ liệu quốc tế cần quy tắc làm sạch nghiêm ngặt, hãy xác định và kiểm thử chính sách Unicode riêng.

## 2. Các tham số và overload

Cả hai nhóm phương thức có cùng cấu trúc overload chủ yếu:

~~~java
ValidationUtils.rejectIfEmpty(errors, field, errorCode);
ValidationUtils.rejectIfEmpty(errors, field, errorCode, defaultMessage);
ValidationUtils.rejectIfEmpty(errors, field, errorCode, errorArgs);
ValidationUtils.rejectIfEmpty(errors, field, errorCode, errorArgs, defaultMessage);

ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode);
ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode, defaultMessage);
ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode, errorArgs);
ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode, errorArgs, defaultMessage);
~~~

Đây là **các dạng gọi minh họa**, trong đó `errors` là `Errors`, `field` và `errorCode` là `String`, `defaultMessage` là `String`, còn `errorArgs` là `Object[]`. Chúng không phải một chương trình Java hoàn chỉnh.

| Tham số | Chức năng | Ví dụ |
| --- | --- | --- |
| `Errors errors` | Nơi Spring ghi nhận lỗi field | `errors` được truyền vào `Validator#validate` |
| `String field` | Tên property cần kiểm tra, theo đường dẫn field của object | `"name"`, `"address.street"` |
| `String errorCode` | Mã lỗi để phân loại hoặc tra cứu thông điệp | `"required"`, `"name.blank"` |
| `Object[] errorArgs` | Tham số cho thông điệp định dạng | `new Object[]{"Họ tên"}` |
| `String defaultMessage` | Thông điệp dự phòng nếu chưa tra cứu được mã lỗi | `"Họ tên không được để trống"` |

Ví dụ hai cách gọi thực tế trong `validate`:

~~~java
ValidationUtils.rejectIfEmpty(
        errors, "referenceCode", "referenceCode.empty");

ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "displayName", "displayName.required",
        "Tên hiển thị không được để trống");
~~~

**Lưu ý về overload:** tham số thứ tư có cả dạng `String` và `Object[]`. Viết `rejectIfEmpty(errors, "name", "required", null)` có thể dẫn đến lỗi **ambiguous method call** trong Java vì `null` khớp cả hai overload. Hãy bỏ tham số thứ tư, ép kiểu rõ ràng hoặc dùng overload năm tham số nếu thật sự cần.

`errorCode` không phải trực tiếp là chuỗi thông báo cho người dùng. Spring có thể chuyển mã này thành các mã chi tiết hơn theo tên object/field và tra cứu qua `MessageSource`; `defaultMessage` chỉ là phương án dự phòng.

## 3. Ví dụ Java 17+ có thể chạy: cùng giá trị, hai kết quả khác nhau

Ví dụ sau sử dụng **Spring Framework thuần**, không yêu cầu Spring Boot hay máy chủ web. Ta định nghĩa JavaBean `InputForm` với hai field:

- `referenceCode` dùng `rejectIfEmpty`, cho phép chuỗi toàn khoảng trắng.
- `displayName` dùng `rejectIfEmptyOrWhitespace`, yêu cầu ít nhất một ký tự có nội dung.

Để tái hiện được kết quả, mỗi lần kiểm tra sẽ gán **cùng giá trị thử nghiệm** vào hai field.

### 3.1. Maven dependency

Tạo project Maven với file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>validation-utils-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phiên bản `6.2.5` được **ghim để ví dụ dễ tái hiện**, không hàm ý đó là bản Spring mới nhất. `spring-context` chứa các lớp validation cần dùng và kéo theo các Spring dependency liên quan. Ví dụ không cần `jakarta.validation-api` hay Hibernate Validator vì nó sử dụng interface `org.springframework.validation.Validator` thuần.

### 3.2. Mã chương trình

Lưu đúng đường dẫn `src/main/java/example/ValidationUtilsDemo.java`:

~~~java
package example;

import java.util.stream.Collectors;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ValidationUtilsDemo {

    // JavaBean: BeanPropertyBindingResult đọc giá trị qua getter.
    public static class InputForm {
        private String referenceCode;
        private String displayName;

        public InputForm(String referenceCode, String displayName) {
            this.referenceCode = referenceCode;
            this.displayName = displayName;
        }

        public String getReferenceCode() {
            return referenceCode;
        }

        public void setReferenceCode(String referenceCode) {
            this.referenceCode = referenceCode;
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }

    public static class InputFormValidator implements Validator {

        @Override
        public boolean supports(Class<?> clazz) {
            return InputForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmpty(
                    errors, "referenceCode", "referenceCode.empty");

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "displayName", "displayName.blank");
        }
    }

    private static void check(String label, String value) {
        InputForm form = new InputForm(value, value);
        BindingResult errors =
                new BeanPropertyBindingResult(form, "inputForm");

        new InputFormValidator().validate(form, errors);

        String errorSummary = errors.getFieldErrors().stream()
                .map(error -> error.getField() + "=" + error.getCode())
                .collect(Collectors.joining(", "));

        System.out.println(label + " -> " +
                (errorSummary.isEmpty() ? "OK" : errorSummary));
    }

    public static void main(String[] args) {
        check("null", null);
        check("empty", "");
        check("spaces", " \t ");
        check("text", " An ");
    }
}
~~~

`FieldError` được Spring tạo và giữ trong `BindingResult`; ở đây phương thức `getCode()` trả mã lỗi gốc đã gửi vào `rejectValue`. Biến `target` trong `validate` là object cần kiểm tra; helper dùng `Errors` để lấy property value nên không cần tự cast target cho hai điều kiện trên.

**Cấu trúc thư mục:**

~~~text
validation-utils-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ValidationUtilsDemo.java
~~~

### 3.3. Biên dịch và chạy

Cài JDK 17+ và Maven, rồi tại thư mục chứa `pom.xml` chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ValidationUtilsDemo
~~~

**Phần stdout do chương trình in**, khi chương trình và dependency được khởi chạy bình thường:

~~~text
null -> referenceCode=referenceCode.empty, displayName=displayName.blank
empty -> referenceCode=referenceCode.empty, displayName=displayName.blank
spaces -> displayName=displayName.blank
text -> OK
~~~

Giải thích từng trường hợp:

1. `null`: hai field không có giá trị, cả hai helper đăng ký lỗi.
2. `""`: chuỗi dài 0 ký tự, cả hai helper đăng ký lỗi.
3. `" \t "`: chuỗi có ký tự (dài hơn 0) nên `rejectIfEmpty` **không** báo lỗi; toàn bộ chỉ là khoảng trắng/tab nên `rejectIfEmptyOrWhitespace` báo lỗi cho `displayName`.
4. `" An "`: chuỗi có chữ nên cả hai helper chấp nhận; chúng **không** tự cắt khoảng trắng ở đầu/cuối.

Nếu chạy trên Windows, lệnh Maven vẫn là `mvn -q compile exec:java -Dexec.mainClass=example.ValidationUtilsDemo` trong Command Prompt/PowerShell khi Maven đã có trên PATH. Output logging của Maven có thể khác nhau; bốn dòng trên là kết quả do chương trình `System.out.println` tạo ra.

## 4. Vì sao cần Errors và BindingResult?

`ValidationUtils` **không biết** đối tượng mà ta muốn kiểm tra chỉ nhờ tên field. Đối tượng `Errors` đã chứa thông tin ngữ cảnh, tên object và khả năng truy cập field.

Trong ví dụ:

~~~java
InputForm form = new InputForm("", "  ");
BindingResult errors = new BeanPropertyBindingResult(form, "inputForm");
new InputFormValidator().validate(form, errors);

boolean failed = errors.hasErrors(); // true
int fieldErrorCount = errors.getFieldErrorCount(); // 2
~~~

`BeanPropertyBindingResult` phù hợp cho đối tượng tuân theo quy ước JavaBean, có các property đọc được. `BindingResult` mở rộng `Errors` và cung cấp thêm thông tin cho cơ chế binding. Giao diện `Errors` có các thao tác quan trọng:

- `errors.rejectValue("name", "required")`: trực tiếp đăng ký lỗi ở một field.
- `errors.reject("form.invalid")`: đăng ký lỗi ở mức toàn object.
- `errors.hasErrors()`: xem có lỗi nào hay không.
- `errors.getFieldErrors()` / `getFieldError("name")`: xem lỗi theo từng field.
- `errors.getFieldValue("name")`: lấy giá trị field trong ngữ cảnh binding.

Hai helper làm việc gần giống một câu `if` rồi gọi `errors.rejectValue(...)`. Chúng **không trả về lỗi** cho caller; caller đọc từ `Errors`/`BindingResult` sau khi gọi.

### Lỗi field và lỗi object khác nhau

Nếu `name` bỏ trống, lỗi nên gắn vào field `name` để giao diện hiển thị cạnh ô nhập. Nếu một điều kiện liên quan **nhiều field cùng lúc**, chẳng hạn `startDate` phải trước `endDate`, có thể sử dụng `errors.reject(...)` để tạo lỗi tổng thể hoặc chọn field phù hợp để gắn lỗi. Không nên ép mọi quy tắc nghiệp vụ phức tạp vào hai helper kiểm tra trống.

## 5. Sử dụng trong một Spring Validator

Mẫu thường gặp:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public final class RegistrationValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "email", "email.required");

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "fullName", "fullName.required");

        RegistrationForm form = (RegistrationForm) target;

        // Chỉ kiểm tra định dạng nếu email thực sự có nội dung.
        if (form.getEmail() != null
                && !form.getEmail().isBlank()
                && !form.getEmail().contains("@")) {
            errors.rejectValue("email", "email.invalid");
        }
    }
}
~~~

Đây là **đoạn code minh họa trong một ứng dụng Spring**, cần thêm class `RegistrationForm` với các property `email` và `fullName`, cùng các import/dependency phù hợp. Không thể chạy độc lập như chương trình ở phần 3.

`supports(Class<?>)` cho biết validator xử lý loại object nào; `validate(Object, Errors)` áp dụng quy tắc rồi ghi lỗi. Việc kiểm tra email bằng `contains("@")` ở trên chỉ minh họa cách **tránh báo lặp lỗi định dạng khi trường đã rỗng**, không phải thuật toán xác thực địa chỉ email đầy đủ.

Lợi ích của việc tách một `RegistrationValidator`: controller/service có thể tái sử dụng quy tắc, kiểm thử không cần HTTP và không lặp lại điều kiện `if (name == null || ...)` ở nhiều nơi.

### Tích hợp với Spring MVC

Khi dùng Spring MVC, một controller có thể đăng ký custom validator thông qua `@InitBinder` và yêu cầu validation khi bind một `@ModelAttribute`:

~~~java
// Đoạn trích trong một @Controller; cần có RegistrationForm,
// RegistrationValidator, import các annotation và cấu hình MVC.
@InitBinder("registrationForm")
void initRegistrationBinder(WebDataBinder binder) {
    binder.addValidators(new RegistrationValidator());
}

@PostMapping("/register")
String register(
        @Validated @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
~~~

Trong Spring MVC, `@Validated` (hoặc annotation validation thích hợp) là tín hiệu để binder thực hiện validation đã cấu hình; `BindingResult` đặt **ngay sau** model attribute để đọc các lỗi. `ValidationUtils` chỉ chạy khi code trong custom validator thực sự được gọi. Việc tồn tại một class implementing `Validator` trong source **không đồng nghĩa** mọi request sẽ tự động được kiểm tra.

Cần phân biệt:

1. **Data binding:** chuyển tham số HTTP vào Java object.
2. **Spring Validator:** kiểm tra object, ví dụ hai phương thức `ValidationUtils`.
3. **Hiển thị lỗi:** đọc `BindingResult` và thông báo cho người dùng.

Một lỗi chuyển kiểu trong quá trình binding cũng có thể được giữ trong `BindingResult`. Đừng nhầm loại lỗi đó với lỗi “required/blank” do `ValidationUtils` tạo ra.

## 6. Tùy biến errorCode, thông điệp và đa ngôn ngữ

Hai helper nhận `errorCode` để **phân loại lỗi**, không để in text trực tiếp. Ví dụ:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "fullName", "required",
        new Object[]{"Họ tên"},
        "{0} không được để trống");
~~~

Ở đây `"required"` là mã lỗi; `errorArgs` cung cấp giá trị để chèn trong thông điệp theo cơ chế `MessageFormat`; `defaultMessage` là chuỗi dự phòng. Khi sử dụng `MessageSource` trong Spring MVC, có thể cung cấp file `messages.properties` như:

~~~properties
required.registrationForm.fullName=Vui lòng nhập họ tên
required.fullName=Họ tên là bắt buộc
required=Trường này không được để trống
~~~

Những key này là ví dụ về các **mã thông điệp** có thể được sinh từ mã `required`, tên object `registrationForm` và tên field `fullName` theo `MessageCodesResolver` của Spring. Độ ưu tiên và danh sách mã được tạo phụ thuộc cấu hình resolver; `messages.properties` không bị `ValidationUtils` tự động đọc trực tiếp. Phần hiển thị hoặc `MessageSource` sẽ tra cứu mã lỗi để quyết định nội dung thông điệp.

Nên đặt mã lỗi nhất quán (`required`, `invalid.email`, `range.exceeded`...), dùng thông điệp cho người dùng và tránh dùng nội dung hiển thị làm mã lỗi nghiệp vụ.

## 7. Field lồng nhau và nested path

Với JavaBean:

~~~text
Customer
  ├── name
  └── address
       └── street
~~~

Nếu `Customer` có `Address`, ta có thể kiểm tra tên property lồng nhau:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "address.street", "street.required");
~~~

Spring có thể đọc đường dẫn field này nếu property chain tương thích và giá trị lồng nhau truy cập được.

Khi đang tái sử dụng `AddressValidator`, có thể quản lý nested path:

~~~java
errors.pushNestedPath("address");
try {
    ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "street", "street.required");
} finally {
    errors.popNestedPath();
}
~~~

Khi đó lỗi gắn với field `address.street`; khối `finally` bảo đảm khôi phục context dù validation thất bại. **Đường dẫn property phải tồn tại**, và object lồng nhau có thể cần được khởi tạo/được hỗ trợ bởi binder. Nếu `address` là `null` mà cấu hình không thể truy cập field con, helper không tự tạo toàn bộ cây object một cách vô điều kiện.

Đối với trường hợp kiểm tra nguyên object `address == null`, có thể dùng `errors.rejectValue("address", "address.required")` hoặc quy tắc validation phù hợp hơn.

## 8. Không nhầm với @NotEmpty, @NotBlank và jakarta.validation

Trong dự án có Jakarta Bean Validation và provider như Hibernate Validator, các annotation:

- `@NotNull`: không cho `null`, nhưng với chuỗi vẫn chấp nhận `""`.
- `@NotEmpty`: không cho `null` hoặc chuỗi/collection/array/map rỗng; với `String`, `"   "` vẫn được chấp nhận.
- `@NotBlank`: áp dụng cho `CharSequence`, yêu cầu có nội dung khác khoảng trắng; gần với `rejectIfEmptyOrWhitespace` cho trường văn bản.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;

public class RegistrationForm {
    @NotBlank
    private String fullName;
    // Getter, setter và các field khác...
}
~~~

Đây là **mẫu class không hoàn chỉnh**; cần provider Jakarta Validation để constraint được thực thi trong runtime tích hợp.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Custom validator thuần Spring, một field chuỗi không được `null`/`""` | `ValidationUtils.rejectIfEmpty` |
| Custom validator thuần Spring, field phải chứa chữ/ký tự có nội dung | `ValidationUtils.rejectIfEmptyOrWhitespace` |
| DTO dùng Jakarta Bean Validation để khai báo ràng buộc | `@NotBlank` hoặc `@NotEmpty`, tùy kiểu và quy tắc |
| Danh sách phải có phần tử | `@NotEmpty` hoặc kiểm tra collection chuyên biệt |
| Số phải lớn hơn 0 | `@Positive`, `@Min(1)` hoặc validator kiểm tra số |
| Kiểm tra điều kiện giữa nhiều field | Custom `Validator`, constraint tùy biến hoặc validation nghiệp vụ |

Điểm khác biệt: `ValidationUtils` sử dụng **Spring `Errors`** và hoạt động độc lập với Jakarta Bean Validation provider; annotation như `@NotBlank` phải được một hệ thống validation phù hợp thực thi. Trong cùng ứng dụng, hai cách tiếp cận có thể cùng tồn tại.

## 9. Lỗi hay gặp và các tình huống biên

### Nhầm “empty” với “blank”

~~~java
ValidationUtils.rejectIfEmpty(errors, "name", "required");
~~~

Nếu `name = "   "`, câu lệnh này **không báo lỗi**. Khi dữ liệu là tên người, tiêu đề, địa chỉ, mật khẩu cần tránh nhập toàn khoảng trắng, hãy cân nhắc `rejectIfEmptyOrWhitespace` với chính sách chuẩn hóa phù hợp.

### Tưởng rằng helper tự trim dữ liệu

Với `name = " Lan "`, cả hai helper đều chấp nhận, và object vẫn giữ `" Lan "`. Nếu nghiệp vụ cần bỏ khoảng trắng, phải định nghĩa **bước chuẩn hóa riêng** (chẳng hạn trên DTO, binder hoặc trong service) và quyết định rõ lúc nào việc chuẩn hóa diễn ra. Không nên tự ý trim mật khẩu hoặc dữ liệu mà khoảng trắng có ý nghĩa.

### Áp dụng cho số, boolean, list hoặc array

Hai helper dùng `value.toString()` cho giá trị khác `null`. Ví dụ:

- `Integer.valueOf(0)` -> `"0"`: **không** bị xem là rỗng.
- `Boolean.FALSE` -> `"false"`: **không** bị xem là rỗng.
- `new ArrayList<>()` -> `"[]"`: **không** bị xem là rỗng.

Do đó, chúng chủ yếu hữu ích cho **field văn bản**. Để kiểm tra list/array/map không rỗng, hãy kiểm tra cấu trúc tương ứng hoặc dùng `@NotEmpty`; để kiểm tra số, dùng constraint/validator về khoảng giá trị. Với primitive như `int`, giá trị mặc định `0` cũng không thể đại diện cho tình trạng `null`.

### Đường dẫn property không đúng

Nếu DTO chỉ có `getFullName()` mà lại kiểm tra `"name"`, `Errors` có thể không truy cập được property và phát sinh exception khi đọc field. Đảm bảo tên field phù hợp với JavaBean hoặc cơ chế binding đã cấu hình; không kỳ vọng helper tự ánh xạ tên từ JSON khác biệt.

### Đăng ký lỗi rồi vẫn tiếp tục xử lý như không có lỗi

Các helper trả về `void`. Sau khi chạy validator, phải kiểm tra `errors.hasErrors()` hoặc `result.hasFieldErrors("name")` và quyết định trả form, response 400 hoặc dừng xử lý nghiệp vụ. Nếu bỏ qua `BindingResult`, lỗi đã được ghi nhận không tự bảo vệ service khỏi đầu vào không hợp lệ.

### Gọi validation nhiều lần

Mỗi lần điều kiện trống đúng và helper được gọi, nó có thể **đăng ký thêm** một `FieldError`. Không giả định Spring sẽ tự loại bỏ lỗi trùng; nên thiết kế flow không lặp validate không cần thiết và tránh kiểm tra cùng một điều kiện ở nhiều nơi mà không có mục đích.

### Khoảng trắng Unicode và chuẩn hóa

`StringUtils.hasText` sử dụng tiêu chí whitespace của Java. Ký tự “trông như khoảng trắng” không phải lúc nào cũng cho kết quả giống ASCII space hoặc tab, và sự khác biệt chuẩn Unicode có thể quan trọng với dữ liệu quốc tế. Hãy thêm test riêng cho các ký tự đặc thù nếu nghiệp vụ yêu cầu; đừng tuyên bố helper phát hiện mọi ký tự vô hình.

### Dùng errorCode như thể đã là thông điệp

`"name.blank"` là mã lỗi dành cho chương trình. Nếu API cần trả thông điệp tiếng Việt hoặc các ngôn ngữ khác, tích hợp `MessageSource` và xử lý `FieldError` ở tầng trình bày; không giả định `getCode()` sẽ là câu thông báo cho người dùng.

## 10. Checklist khi dùng trong dự án

1. Xác định field là **chuỗi**, và quy tắc cấm `null`/rỗng hay cấm cả whitespace-only.
2. Đặt tên property chính xác trong `field`, phù hợp với getter hoặc cấu hình binder.
3. Đặt `errorCode` ổn định để dễ map ra thông điệp và dễ kiểm thử.
4. Implement `Validator#supports` và `validate` đúng đối tượng; gọi validator hoặc đăng ký nó với binder thật sự.
5. Sau validation, xử lý `BindingResult`/`Errors`; trong MVC, đặt `BindingResult` ngay sau model attribute tương ứng.
6. Kiểm thử các trường hợp `null`, `""`, `" "`, `"\t"`, `"a"`, `" a "` và các ký tự Unicode quan trọng với nghiệp vụ.
7. Không dùng hai helper để thay thế ràng buộc độ dài, format, giá trị số, collection hay phân quyền.

### Câu hỏi tự kiểm tra

1. Vì sao `rejectIfEmpty` cho phép `"   "` nhưng `rejectIfEmptyOrWhitespace` lại báo lỗi?
2. Trong `validate(Object, Errors)`, vì sao helper không cần nhận tham số `target`?
3. Với `InputForm(referenceCode=" ", displayName=" ")`, hai helper trong ví dụ sinh bao nhiêu lỗi và lỗi thuộc field nào?
4. Nếu gọi `ValidationUtils.rejectIfEmpty(errors, "age", "required")` khi `age` là `int` có giá trị `0`, điều gì xảy ra và nên dùng cách nào khác?
5. Làm sao hiển thị thông báo tiếng Việt khi chỉ có mã lỗi `"displayName.blank"`?

**Điểm nhớ:** `rejectIfEmpty` kiểm tra **không có ký tự**; `rejectIfEmptyOrWhitespace` kiểm tra **không có ký tự mang nội dung**. Cả hai là cách ngắn gọn để thêm `FieldError` vào Spring `Errors`, và logic xử lý lỗi vẫn thuộc về validator/controller.

## Tài liệu chính thức

- Spring Framework Reference — Validation using Spring's Validator Interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Javadoc — ValidationUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/ValidationUtils.html
- Spring Framework Javadoc — Errors: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html
- Spring Framework Javadoc — BeanPropertyBindingResult: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html
- Spring Framework Javadoc — StringUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/StringUtils.html
- Spring Framework source — ValidationUtils.java: https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/validation/ValidationUtils.java