# Errors và cách thu thập kết quả kiểm tra

Khi nhập biểu mẫu trong Spring Framework, một giá trị có thể **không chuyển được sang kiểu Java**, hoặc đã chuyển và gán thành công nhưng **vi phạm quy tắc hợp lệ**. Spring cung cấp interface `org.springframework.validation.Errors` để gom các lỗi này theo **một đối tượng được kiểm tra**, thay vì buộc ứng dụng chỉ biết “thành công/thất bại”.

Bài này giải thích cách ghi, đọc và xử lý lỗi với `Errors`; mối quan hệ của nó với `Validator`, `DataBinder` và `BindingResult`; sự khác biệt giữa lỗi theo trường và lỗi toàn đối tượng; cách mã lỗi trở thành thông báo cho người dùng; và cách áp dụng trong Spring MVC. Ví dụ chính dùng Java 17+ với Spring Framework 6.2.x.

## 1. Errors nằm ở đâu trong luồng xử lý?

Xét form đăng ký gửi các giá trị:

```text
username = "   "
age      = "16"
password = "abc"
confirm  = "xyz"
```

Đối tượng đích (`target`) có `username: String`, `age: int`, `password: String` và `confirm: String`. Spring có thể bind thành công cả bốn giá trị, nhưng việc kiểm tra sau đó phát hiện tên trống, tuổi dưới mức yêu cầu và mật khẩu xác nhận không khớp.

```text
Dữ liệu đầu vào (chuỗi)
          |
          v
   DataBinder / WebDataBinder -----> ConversionService / Formatter
          |                                   |
          +---------- chuyển kiểu, gán <------+
          |
          +---- lỗi binding: ví dụ age="abc" -------------+
          |                                               |
          v                                               v
   Đối tượng Java                                    BindingResult
          |                                          (extends Errors)
          v                                               ^
  Validator / Bean Validation                             |
          |                                               |
          +---- rejectValue(...) / reject(...) ------------+
          |
          v
  hasErrors(), getFieldErrors(), getGlobalErrors()
          |
          v
  Hiển thị lỗi theo field / báo lỗi toàn form / phản hồi API
```

**Lưu ý:** `DataBinder.bind(...)` chủ yếu làm binding và có thể thu thập lỗi binding; với API `DataBinder` dùng trực tiếp, cần gọi `binder.validate()` để chạy các validator đã cấu hình. Trong Spring MVC, framework có thể kích hoạt validation khi tham số phù hợp mang `@Valid` hoặc `@Validated` và provider/validator tương ứng đã được tích hợp. Không giả định mọi lần bind đều tự kiểm tra toàn bộ ràng buộc.

Trong ví dụ trên, nếu `age="abc"`, chuyển kiểu thành `int` thất bại; đó là **binding error**. Nếu `age="16"`, chuyển kiểu thành 16 thành công, nhưng quy tắc tuổi tối thiểu 18 thất bại; đó là **validation error**. Cả hai đều có thể được truy vấn qua cùng bề mặt `Errors`/`BindingResult`.

## 2. Errors là gì và khác BindingResult như thế nào?

`Errors` là **hợp đồng ghi và truy vấn lỗi** cho một target có tên (`objectName`). Nó không phải exception, không phải một chuỗi thông báo duy nhất, cũng không tự thực hiện validation. Một đối tượng `Validator` nhận `Errors` để **đăng ký** lỗi; các lớp ở tầng xử lý nhận `Errors` để **đọc** lỗi.

`BindingResult` **extends `Errors`**, bổ sung dữ liệu gắn với quá trình binding như target, giá trị trường thô và tích hợp với Spring MVC model. Một số implementation thường gặp gồm `BeanPropertyBindingResult` và `DirectFieldBindingResult`; khi dùng `DataBinder`, truy cập kết quả qua `binder.getBindingResult()`.

| Thành phần | Vai trò | Ví dụ API |
| --- | --- | --- |
| `Validator` | Quy tắc kiểm tra, ghi lỗi | `validate(Object, Errors)` |
| `Errors` | Ghi/truy vấn lỗi theo field và toàn object | `rejectValue`, `reject`, `getAllErrors` |
| `BindingResult` | `Errors` có thêm ngữ cảnh data binding | `getTarget`, `getFieldErrors`, `getModel` |
| `FieldError` | Biểu diễn một lỗi của property | `getField`, `getRejectedValue`, `isBindingFailure` |
| `ObjectError` | Biểu diễn lỗi chung; cũng là lớp cha của `FieldError` | `getObjectName`, `getCodes`, `getDefaultMessage` |
| `DataBinder` | Bind input, điều phối chuyển kiểu và validator | `bind`, `validate`, `getBindingResult` |
| `MessageSource` | Giải mã mã lỗi ra thông báo theo ngôn ngữ | `getMessage(MessageSourceResolvable, Locale)` |

**Cấu trúc kế thừa cần nhớ:**

```text
Errors (interface)
  └── BindingResult (interface)

ObjectError
  └── FieldError
```

Do `FieldError extends ObjectError`, `getAllErrors()` trả danh sách `ObjectError` nhưng có thể chứa cả những phần tử thực tế là `FieldError`. Để hiển thị thông báo sát từng input, dùng `getFieldErrors()`/`getFieldErrors("field")`; để hiển thị cảnh báo toàn form, dùng `getGlobalErrors()`.

Mỗi `Errors` gắn với tên đối tượng đích, ví dụ `"signup"`. Tên đó tham gia tạo mã message và khi đưa kết quả vào model. Thông thường không nên chia sẻ một instance `Errors` giữa nhiều request hoặc thread; API được thiết kế cho vòng đời kiểm tra một đối tượng trong một luồng xử lý.

## 3. Hai loại lỗi: field và global

### 3.1. Field error

**Field error** gắn với một property cụ thể, ví dụ:

- `username` bị bỏ trống;
- `age` nhỏ hơn 18;
- `age="abc"` không chuyển thành số;
- `address.city` không hợp lệ;
- `items[0].quantity` có giá trị ngoài giới hạn.

Trong `Validator`, ghi lỗi bằng `errors.rejectValue(...)`:

```java
errors.rejectValue("age", "age.min", new Object[] {18},
                   "Tuổi tối thiểu là 18");
```

Các tham số lần lượt là **tên field**, **mã lỗi** phục vụ lookup message, **tham số cho thông báo** và **default message** dự phòng. `"age.min"` là mã do ứng dụng đặt; nó chưa phải bản dịch cuối cùng.

Một `FieldError` thường chứa:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `getObjectName()` | Object/form đang được kiểm tra |
| `getField()` | Đường dẫn property gây lỗi |
| `getRejectedValue()` | Giá trị bị từ chối; có thể là chuỗi gốc lúc binding thất bại |
| `getCode()` | Mã lỗi chung nhất, ví dụ `age.min` hoặc `typeMismatch` |
| `getCodes()` | Các mã ứng viên cụ thể đến tổng quát để tra thông báo |
| `getArguments()` | Tham số dùng cho mẫu thông báo |
| `getDefaultMessage()` | Thông báo dự phòng (có thể null) |
| `isBindingFailure()` | `true` nếu là lỗi binding, thường `false` với lỗi do validator tạo |

Không nên giả định `getRejectedValue()` luôn là giá trị đã lưu trong Java object. Khi `age="abc"` bind vào `int` thất bại, target có thể vẫn giữ giá trị cũ/mặc định; `FieldError` giữ nguyên input bị từ chối để thông báo hoặc render lại form.

### 3.2. Global error

**Global error** liên quan đối tượng hoặc quy tắc gồm nhiều trường, không nhất thiết quy về một property duy nhất. Ví dụ:

- `password` và `confirm` không trùng;
- `startDate` không được sau `endDate`;
- tổng phần trăm các mục không bằng 100.

Đăng ký bằng `errors.reject(...)`:

```java
errors.reject("password.mismatch",
              "Mật khẩu xác nhận không khớp");
```

Kết quả là `ObjectError` trong `getGlobalErrors()`. Nếu UI muốn hiển thị lỗi ngay cạnh một field duy nhất (ví dụ cạnh `confirm`), có thể chọn `rejectValue("confirm", ...)`. Chọn field hay global theo **trải nghiệm người dùng và ý nghĩa của quy tắc**, không theo thói quen.

**Đừng nhầm “global error” với lỗi ứng dụng toàn cục.** Trong `Errors`, global chỉ có nghĩa là lỗi ở cấp **đối tượng được bind**, không phải hệ thống lỗi production, HTTP 500 hay exception toàn chương trình.

## 4. Bảng các phương thức Errors dùng nhiều nhất

| Nhóm | Phương thức | Cách hiểu |
| --- | --- | --- |
| Xác định đối tượng | `getObjectName()` | Tên target của tập lỗi |
| Ghi lỗi toàn object | `reject(code, ...)` | Thêm `ObjectError` |
| Ghi lỗi theo property | `rejectValue(field, code, ...)` | Thêm `FieldError` |
| Có lỗi nào không? | `hasErrors()` | `true` nếu có ít nhất một lỗi |
| Tổng số | `getErrorCount()` | Tổng field + global |
| Danh sách tổng | `getAllErrors()` | Trả cả `ObjectError` và `FieldError` |
| Lỗi field | `hasFieldErrors()`, `getFieldErrorCount()` | Truy vấn lỗi thuộc các field |
| Lỗi của một field | `hasFieldErrors("age")`, `getFieldError("age")`, `getFieldErrors("age")` | `getFieldError` chỉ lấy lỗi **đầu tiên** |
| Lỗi global | `hasGlobalErrors()`, `getGlobalErrorCount()`, `getGlobalErrors()` | Truy vấn lỗi toàn đối tượng |
| Giá trị field để render | `getFieldValue("age")` | Có thể trả giá trị bị từ chối hoặc giá trị property |
| Kiểu field | `getFieldType("age")` | Kiểu field nếu xác định được |
| Path lồng nhau | `pushNestedPath("address")`, `popNestedPath()` | Tạo ngữ cảnh kiểm tra subtree |

Một số ý nghĩa dễ bỏ sót:

- `getFieldError("age")` chỉ trả một lỗi hoặc `null`; nếu một field vi phạm nhiều constraint, dùng `getFieldErrors("age")` để không bỏ sót.
- `getAllErrors()` là **collection**; không nên ép mọi phần tử sang `FieldError`.
- `hasErrors()` cho biết có lỗi trong đối tượng được kiểm tra, không nói dữ liệu đã bị rollback hay transaction đã kết thúc.
- API không tự gửi response HTTP, không tự tạo JSON error envelope và không tự thực hiện sửa giá trị.
- `Errors` có thể có nhiều lỗi cho một field. Đừng xem `getErrorCount()` là “số lượng field sai”.

## 5. Validator ghi lỗi như thế nào?

Với `org.springframework.validation.Validator`, hai method chính là:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

`supports` trả lời validator hỗ trợ kiểu target nào; `validate` kiểm tra và ghi lỗi. Đây là **hình dạng rút gọn** của interface dùng để giải thích, không phải file tự biên dịch.

Ví dụ logic của form:

```java
@Override
public void validate(Object target, Errors errors) {
    Signup form = (Signup) target;

    ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "username", "username.required",
            "Tên đăng nhập bắt buộc");

    if (!errors.hasFieldErrors("age") && form.getAge() < 18) {
        errors.rejectValue("age", "age.min", new Object[]{18},
                "Tuổi tối thiểu 18");
    }

    if (form.getPassword() != null
            && !form.getPassword().equals(form.getConfirm())) {
        errors.reject("password.mismatch",
                "Mật khẩu xác nhận không khớp");
    }
}
```

Đây là **đoạn trong một class implements `Validator`**; class `Signup` và import được trình bày ở ví dụ đầy đủ bên dưới.

Vì sao kiểm tra `!errors.hasFieldErrors("age")`? Nếu input `age="abc"` không thể chuyển thành `int`, target primitive `age` có thể còn bằng 0. Nếu chỉ kiểm tra `age < 18`, validator sẽ thêm lỗi tuổi thấp dù thực chất người dùng nhập **sai cú pháp**. Bỏ qua kiểm tra tuổi khi đã có lỗi binding cho field giúp thông báo đúng nguyên nhân chính. Đây là một chính sách validation hữu ích; với rule khác có thể cần chính sách khác.

`ValidationUtils.rejectIfEmptyOrWhitespace(...)` hỗ trợ xử lý null, chuỗi rỗng hoặc chỉ chứa khoảng trắng. Nó **ghi lỗi vào Errors**, không tự thay đổi field, không tự ném exception và không tự hiển thị thông báo.

## 6. Ví dụ Java 17+ đầy đủ: thu thập cả binding và validation errors

Ví dụ dùng **Spring Framework 6.2.12** qua Maven, chạy chương trình console. Nó minh họa hai trường hợp:

1. Bind được dữ liệu, sau đó validator tạo 2 lỗi theo field và 1 lỗi toàn object.
2. Không thể bind `age="abc"`, tạo lỗi `typeMismatch`; validator tránh bổ sung thêm lỗi tuổi không có ý nghĩa.

Cấu trúc:

```text
errors-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ErrorsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>errors-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/ErrorsDemo.java`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ErrorsDemo {
    public static class Signup {
        private String username;
        private int age;
        private String password;
        private String confirm;

        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }

        public String getConfirm() { return confirm; }
        public void setConfirm(String confirm) { this.confirm = confirm; }
    }

    public static class SignupValidator implements Validator {
        @Override
        public boolean supports(Class<?> clazz) {
            return Signup.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup form = (Signup) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "username", "username.required",
                    "Tên đăng nhập bắt buộc");

            // Không thêm lỗi tuổi nếu trước đó đã có lỗi bind field age.
            if (!errors.hasFieldErrors("age") && form.getAge() < 18) {
                errors.rejectValue(
                        "age", "age.min", new Object[]{18},
                        "Tuổi tối thiểu là 18");
            }

            // Một quy tắc liên trường được ghi thành global error.
            if (form.getPassword() != null
                    && !form.getPassword().equals(form.getConfirm())) {
                errors.reject("password.mismatch",
                        "Mật khẩu xác nhận không khớp");
            }
        }
    }

    private static BindingResult check(
            String username, String age, String password, String confirm) {
        Signup target = new Signup();
        DataBinder binder = new DataBinder(target, "signup");
        binder.setValidator(new SignupValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("username", username);
        input.add("age", age);
        input.add("password", password);
        input.add("confirm", confirm);

        binder.bind(input);    // Thu thập lỗi binding/conversion.
        binder.validate();     // Thu thập lỗi Validator.
        return binder.getBindingResult();
    }

    private static void printResult(String label, BindingResult result) {
        System.out.println("case=" + label);
        System.out.println("total=" + result.getErrorCount());
        System.out.println("field=" + result.getFieldErrorCount());
        System.out.println("global=" + result.getGlobalErrorCount());

        for (FieldError error : result.getFieldErrors()) {
            System.out.println("FIELD " + error.getField() + " "
                    + error.getCode() + " binding=" + error.isBindingFailure());
        }

        for (ObjectError error : result.getGlobalErrors()) {
            System.out.println("GLOBAL " + error.getCode());
        }
    }

    public static void main(String[] args) {
        BindingResult validation = check("   ", "16", "abc", "xyz");
        printResult("validation", validation);

        BindingResult conversion = check("An", "abc", "same", "same");
        printResult("conversion", conversion);
    }
}
```

Chạy từ thư mục `errors-demo` bằng JDK 17+ và Maven (lần đầu cần tải dependency):

```bash
mvn -q compile exec:java -Dexec.mainClass=ErrorsDemo
```

Các dòng `System.out.println` trong chương trình tạo ra:

```text
case=validation
total=3
field=2
global=1
FIELD username username.required binding=false
FIELD age age.min binding=false
GLOBAL password.mismatch
case=conversion
total=1
field=1
global=0
FIELD age typeMismatch binding=true
```

**Đọc kết quả:**

- Case `validation` bind được giá trị, nhưng `username` chỉ chứa khoảng trắng; `age=16` dưới 18; `password` khác `confirm`. Có 3 lỗi: 2 field và 1 global.
- `FieldError.isBindingFailure()` bằng `false` cho lỗi do validator đăng ký, bởi dữ liệu đã bind được và sai rule.
- Case `conversion` có `age="abc"` không trở thành `int`. `DataBinder` mặc định đưa lỗi chuyển kiểu thành `FieldError` (mã chung `typeMismatch`) với `isBindingFailure()=true`.
- Validator kiểm tra `hasFieldErrors("age")` nên không bổ sung lỗi `age.min` trên giá trị mặc định 0.
- `result.getErrorCount()` bằng tổng số `getFieldErrors().size() + getGlobalErrors().size()`.

Để xem input bị từ chối trong case lỗi chuyển kiểu (chỉ dùng trong debug an toàn), có thể đọc:

```java
FieldError error = conversion.getFieldError("age");
if (error != null) {
    System.out.println(error.getRejectedValue()); // abc
}
```

Đây là đoạn nối tiếp với biến `conversion` trong `main`; chưa được thêm vào stdout ở trên. **Không ghi ra log những rejected value chứa mật khẩu, token, dữ liệu cá nhân hoặc nội dung chưa lọc**, vì `FieldError` có thể giữ đúng giá trị nhạy cảm người dùng đã nhập.

## 7. Thu thập và truy vấn Errors theo mục đích

### 7.1. Chỉ cần biết có thể tiếp tục hay không

```java
if (errors.hasErrors()) {
    // Trả lại form, hoặc xây dựng kết quả kiểm tra thất bại.
    return;
}
```

Đây là đoạn logic đặt trong hàm có biến `Errors errors` và kiểu trả về phù hợp. Kiểm tra sớm ngăn code nghiệp vụ chạy với input không hợp lệ.

### 7.2. Hiển thị lỗi cho từng trường

```java
for (FieldError fieldError : errors.getFieldErrors()) {
    String field = fieldError.getField();
    String code = fieldError.getCode();
    String fallback = fieldError.getDefaultMessage();
    // Dùng field/code để gắn thông báo vào control tương ứng.
}
```

Nếu UI chỉ hiển thị một lỗi trên mỗi field, `getFieldError("age")` trả lỗi đầu tiên. Nếu cần đầy đủ, dùng `getFieldErrors("age")` và sắp xếp/nhóm theo nhu cầu UI. Không nên hiển thị raw `FieldError.toString()` cho người dùng vì nó chứa thông tin nội bộ và có thể chứa giá trị bị từ chối.

### 7.3. Hiển thị lỗi cho cả form

```java
for (ObjectError error : errors.getGlobalErrors()) {
    // Một thông báo cho quy tắc liên trường hoặc toàn object.
}
```

Trong form phức tạp, thường có vùng “Lỗi chung” và vùng thông báo ngay dưới mỗi ô nhập. `getAllErrors()` phù hợp cho trang tổng hợp, nhưng cần phân biệt `FieldError` nếu muốn hiển thị ở đúng control.

### 7.4. Thống kê đúng số lượng

```java
int total = errors.getErrorCount();
int fieldCount = errors.getFieldErrorCount();
int globalCount = errors.getGlobalErrorCount();

assert total == fieldCount + globalCount;
```

Đây là điều kiện đúng với cấu trúc lỗi được Spring thống kê; `assert` của Java chỉ chạy khi bật `-ea` và không thay thế kiểm thử có framework. Ví dụ một field `password` vi phạm hai rule có thể tạo hai `FieldError`, nên `fieldCount` là số **lỗi**, không phải số field khác nhau.

## 8. Mã lỗi, defaultMessage và i18n

`errors.rejectValue("age", "age.min", ...)` lưu **mã lỗi**; mã này có thể được mở rộng thành nhiều lựa chọn cụ thể hơn nhờ `MessageCodesResolver`. Với object `signup` và field `age` kiểu `int`, các ứng viên thông dụng có dạng:

```text
age.min.signup.age
age.min.age
age.min.int
age.min
```

Danh sách/chi tiết mã phụ thuộc implementation/configuration resolver; `getCodes()` là nguồn thật để kiểm tra. Spring dùng `MessageSource` với các mã và tham số để lấy thông báo đã dịch theo locale; `getDefaultMessage()` là dự phòng khi không có thông báo trong cấu hình tương ứng.

Ví dụ file thông điệp tiếng Việt:

```properties
username.required.signup.username=Vui lòng nhập tên đăng nhập.
age.min.signup.age=Tuổi phải từ {0} trở lên.
password.mismatch.signup=Mật khẩu và xác nhận không khớp.
typeMismatch.signup.age=Tuổi phải là một số nguyên.
```

Trong `MessageSource`, `{0}` được thay bởi đối số đầu tiên nếu cấu hình/nguồn message hỗ trợ. Ví dụ `age.min` truyền `new Object[]{18}` để tạo “Tuổi phải từ 18 trở lên”. Thông thường ứng dụng khai báo các bundle `messages*.properties` và cấu hình nguồn message phù hợp với `Locale`. Việc chọn `error.getDefaultMessage()` để trả thẳng ra API chỉ là cách fallback đơn giản, **không đảm bảo bản dịch** hoặc bảo đảm thông báo an toàn cho public API.

Các bước thiết kế message tốt:

1. Mã lỗi ổn định, ví dụ `age.min` hoặc `registration.age.min`, tách khỏi câu chữ.
2. Dùng field/object-specific keys khi một quy tắc cần thông báo khác nhau theo ngữ cảnh.
3. Có `defaultMessage` rõ ràng cho tình huống thiếu key.
4. Truyền tham số cho giá trị thay đổi (`18`, giới hạn kích thước, v.v.) thay vì ghép chuỗi thủ công.
5. Không đưa stack trace hoặc class name của exception vào thông báo cho người dùng cuối.

**Thông điệp và mã lỗi có vòng đời khác nhau:** cùng mã `typeMismatch` có thể có thông báo “Vui lòng nhập tuổi hợp lệ” trên UI tiếng Việt và “Enter a valid age” trên UI tiếng Anh.

## 9. Errors trong Spring MVC controller

Đối với biểu mẫu dùng `@ModelAttribute`, Spring MVC hỗ trợ tham số `BindingResult` **ngay sau** tham số form để controller nhận lỗi:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

class RegisterForm {
    @NotBlank
    private String username;

    @Min(18)
    private int age;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}

@Controller
class RegisterController {
    @PostMapping("/register")
    String register(
            @Valid @ModelAttribute("form") RegisterForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "register-form";
        }

        // Chỉ xử lý form hợp lệ theo các ràng buộc đã chạy.
        return "register-success";
    }
}
```

Đây là **đoạn tích hợp Spring MVC**, cần project đã cấu hình view resolver và Bean Validation provider (trong Spring Boot thường thêm `spring-boot-starter-validation`). Tên view chỉ minh họa; đoạn này không phải ứng dụng Spring Boot tự chạy.

Cần nhớ bốn điểm:

- **Thứ tự tham số quan trọng:** `BindingResult` (hoặc `Errors`) phải đứng ngay sau `@ModelAttribute` mà nó đi kèm. Nếu chèn tham số khác ở giữa, MVC không áp dụng kết quả lỗi cho đúng object như mong đợi.
- **`@Valid`/`@Validated` kích hoạt validation** trong cấu hình thích hợp. Chỉ nhận `BindingResult` mà không kích hoạt validation thì vẫn có thể thấy lỗi binding, nhưng không tự động chạy mọi constraint nghiệp vụ.
- **Khi có `BindingResult`**, controller có thể quyết định trả lại form thay vì để một số lỗi được xử lý bằng exception. Cách exception được phát sinh nếu không có tham số này phụ thuộc loại binding/validation, ví dụ `MethodArgumentNotValidException` cho validation của một argument hoặc `HandlerMethodValidationException` khi method validation được áp dụng.
- **`@RequestBody` khác form binding:** JSON thường được đọc bằng HTTP message converter (thường Jackson), sau đó có thể được validate; JSON cú pháp sai hay deserialize thất bại có thể gây `HttpMessageNotReadableException` trước khi có `BindingResult` theo cách form MVC. Đừng dùng một luồng xử lý chung bất chấp hai nguồn dữ liệu này.

Nếu dùng Spring `Validator` tự viết thay vì constraint Jakarta Bean Validation, cần **đăng ký validator với MVC binder** (ví dụ qua `@InitBinder`/cấu hình MVC) hoặc gọi validation thích hợp. `@Valid` không tự tìm và chạy mọi class `Validator` trong ứng dụng chỉ vì class đó tồn tại.

### Ví dụ đăng ký Validator cho model cụ thể

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("signup")
void configureSignupBinder(WebDataBinder binder) {
    binder.addValidators(new SignupValidator());
}
```

Đây là **method minh họa trong controller** khi model attribute có tên `signup`, và `SignupValidator` hỗ trợ kiểu target. `addValidators(...)` giữ các validator đã có; `setValidator(...)` đặt một validator chính theo cấu hình tương ứng. Không gọi validator cho target không được `supports(...)` chấp nhận.

## 10. Validation bằng Jakarta Bean Validation được chuyển vào Errors như thế nào?

Với `jakarta.validation`, các annotation như `@NotBlank`, `@Min`, `@Size`, `@Email` khai báo constraint ngay trên bean. Khi Spring MVC kích hoạt Bean Validation, các violation phù hợp được thích ứng thành lỗi mà `BindingResult` truy vấn được, tương tự khi Spring `Validator` gọi `errors.rejectValue(...)`.

Ví dụ:

```java
public class ProfileForm {
    @jakarta.validation.constraints.NotBlank
    private String displayName;

    @jakarta.validation.constraints.Size(max = 120)
    private String bio;

    // Getter/setter cần thiết cho cách property binding đã chọn.
}
```

Đây là trích đoạn model để đọc constraint, không phải file Java hoàn chỉnh. Nếu `displayName` trống hoặc `bio` dài quá 120 ký tự, provider có thể trả constraint violations, rồi Spring đưa chúng vào `BindingResult` nếu validation đã được kích hoạt. Mã lỗi thường liên quan tên annotation như `NotBlank`, `Size`; nên đọc `getCodes()` trong tình huống cụ thể thay vì tự đoán chuỗi đầy đủ.

**Phân biệt luồng:**

| Bước | Ai chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| Đọc input | MVC argument resolution / message conversion | `age="abc"` |
| Chuyển kiểu và bind | `DataBinder` / converter | `"20" -> int 20` |
| Kiểm tra constraint | Spring Validator / Jakarta Bean Validation | `@Min(18)` |
| Thu thập lỗi | `Errors` / `BindingResult` | `typeMismatch`, `Min` |
| Dịch mã thành thông báo | `MessageSource` và view/API layer | “Tuổi phải từ 18” |
| Quyết định xử lý tiếp | Controller/service | Render lại form hoặc tiếp tục |

Một số nghiệp vụ cần kiểm tra chéo nhiều field hoặc tra cứu database; nên đưa rule đúng tầng ứng dụng, cân nhắc chi phí truy vấn và tính nhất quán. `Errors` ghi nhận lỗi, nhưng **không thay thế** xác thực, phân quyền, transaction và bất biến domain.

## 11. Field lồng nhau và nested path

Nếu target chứa object `address` có field `city`, có thể ghi trực tiếp:

```java
errors.rejectValue("address.city", "city.required",
                   "Phải nhập thành phố");
```

Một validator riêng cho `Address` đôi khi sử dụng nested path để tái sử dụng logic:

```java
errors.pushNestedPath("address");
try {
    // Lúc này "city" được hiểu thành "address.city".
    errors.rejectValue("city", "city.required",
                       "Phải nhập thành phố");
} finally {
    errors.popNestedPath();
}
```

Đây là đoạn minh họa trong luồng validate đối tượng cha có property `address`; cần đảm bảo target và đường dẫn tồn tại theo cơ chế truy cập của implementation. `try/finally` giúp khôi phục nested path kể cả khi có exception; nếu quên `popNestedPath()`, lỗi ở các bước sau có thể bị gắn sai đường dẫn. Có thể dùng `ValidationUtils.invokeValidator(...)` để gọi một validator con với `Errors` được chuẩn bị đúng ngữ cảnh.

Trong nested collection, các path như `items[0].quantity` có thể xuất hiện trong `FieldError.getField()`. Khi đưa lên UI, cần đối chiếu field path với vị trí trong form, nhất là khi hàng được thêm/xóa hoặc sắp xếp.

## 12. Giữ lỗi cùng dữ liệu form và hiển thị an toàn

Khi MVC trả về template, `BindingResult` của model attribute có tên đặc biệt theo tiền tố `BindingResult.MODEL_KEY_PREFIX` và tên attribute. Với form tên `form`, key thường có dạng:

```text
org.springframework.validation.BindingResult.form
```

Framework hỗ trợ template/view truy cập các lỗi này thông qua cơ chế binding của form. Trong Thymeleaf có thể dùng `th:field` và `th:errors` để hiển thị lỗi gắn với field, ví dụ đoạn trong một form đã khai báo `th:object`:

```html
<input type="text" th:field="*{username}" />
<span th:errors="*{username}"></span>

<input type="text" th:field="*{age}" />
<span th:errors="*{age}"></span>
```

Đây là **trích đoạn template**, không phải trang HTML hoàn chỉnh; project cần Spring/Thymeleaf integration và model attribute phù hợp. Nếu tự xây JSON response, nên map mã lỗi/thông báo vào DTO riêng theo API contract, ví dụ `field`, `code`, `message`, thay vì serialize trực tiếp toàn bộ `BindingResult`.

**Đặc biệt với input nhạy cảm:** lỗi binding có thể mang `rejectedValue` nguyên văn (mật khẩu, số thẻ, token). Không phản hồi/log toàn bộ `BindingResult`, `FieldError.toString()` hoặc rejected value khi chưa xét kỹ khả năng lộ dữ liệu. Trả những thông tin cần thiết để người dùng sửa input; tránh echo lại bí mật.

## 13. Thử nghiệm và kiểm tra kết quả chính xác

Một bộ test cho lớp validator cần tách trường hợp **lỗi binding** với **lỗi quy tắc**. Các ca tối thiểu cho ví dụ `Signup`:

| Input | Kỳ vọng | Lý do |
| --- | --- | --- |
| username `"An"`, age `"20"`, password = confirm | 0 lỗi | Bind + rule đều đạt |
| username toàn khoảng trắng | Field error `username.required` | Bỏ trống về mặt ngữ nghĩa |
| age `"16"` | Field error `age.min` | Đã thành `int` nhưng không đạt ràng buộc |
| age `"abc"` | Field error `typeMismatch`, `isBindingFailure()=true` | Sai kiểu; tránh thêm `age.min` giả |
| password khác confirm | Global error `password.mismatch` | Quy tắc liên trường |
| Nhiều lỗi cùng lúc | `getAllErrors()` chứa đủ lỗi | Không mất lỗi do chỉ xem lỗi đầu tiên |

Nếu kiểm tra bằng JUnit, nên assert **mã lỗi + field + loại bindingFailure** thay vì so sánh nguyên văn bản dịch, vì văn bản UI có thể thay đổi theo `Locale`. Ví dụ cách kiểm tra `BindingResult` đã có:

```java
FieldError ageError = result.getFieldError("age");
org.junit.jupiter.api.Assertions.assertNotNull(ageError);
org.junit.jupiter.api.Assertions.assertEquals("typeMismatch", ageError.getCode());
org.junit.jupiter.api.Assertions.assertTrue(ageError.isBindingFailure());
```

Đây là đoạn kiểm thử cần `result` chứa lỗi chuyển kiểu của `age` và project có JUnit Jupiter dependency. Với MVC, có thể dùng `MockMvc` để gửi request form và kiểm tra lỗi model; khi chuyển sang JSON, cần thêm test riêng cho lỗi deserialize và validation.

### Tự debug khi số lỗi khác kỳ vọng

1. Đọc input gốc và **kiểu property** của target; xác nhận lỗi xảy ra trong bind hay validate.
2. Kiểm tra `binder.bind(...)` đã chạy chưa và `binder.validate()` có được gọi hay đã kích hoạt tương đương trong MVC.
3. Kiểm tra validator có hỗ trợ class target và đã được đăng ký đúng binder không.
4. Dùng `getAllErrors()`, `getFieldErrors()` và `getGlobalErrors()` để tách số lỗi.
5. Dùng `isBindingFailure()` và `getCodes()` để nhận diện lỗi chuyển kiểu/các quy tắc.
6. Nếu UI thiếu message, kiểm tra key `MessageSource`, `Locale` và cách template/API render lỗi.
7. Nếu lỗi bị gắn sai property, xem lại `nestedPath` hoặc tên field trên client.
8. Nếu một field bị báo hai lỗi không hữu ích, rà soát điều kiện tránh validation trên field đã thất bại khi binding.

## 14. Những lỗi thiết kế thường gặp

| Nhầm lẫn | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Gọi `binder.bind` rồi mặc định validator đã chạy | Có dữ liệu sai rule nhưng `Errors` chưa ghi gì | Gọi `binder.validate()` hoặc dùng luồng MVC có validation |
| Trộn `reject` và `rejectValue` | UI không biết đặt message ở field nào | Field-specific dùng `rejectValue`; rule chung dùng `reject` |
| Chỉ xem `getFieldError()` một lần | Bỏ sót nhiều field/lỗi global | Dùng `getAllErrors()` hoặc các collection tương ứng |
| Lấy `getErrorCount()` làm số field lỗi | Thống kê sai khi một field có nhiều lỗi | Đếm distinct field name nếu thực sự cần số field |
| Tự đổi tất cả lỗi thành `RuntimeException` | Khó phản hồi nhiều lỗi form cùng lúc | Thu thập qua `Errors` cho những tình huống người dùng có thể sửa |
| Validator chạy rule trên giá trị chưa bind được | Thêm lỗi đánh lạc hướng như “tuổi quá nhỏ” sau `"abc"` | Kiểm tra `hasFieldErrors("age")` trước rule liên quan |
| Hardcode thông báo trong controller | Khó quốc tế hóa và tái sử dụng | Dùng error code + `MessageSource` |
| Đặt `BindingResult` không kề tham số form | MVC không xử lý lỗi như mong đợi | Đặt ngay sau `@ModelAttribute` hoặc argument phù hợp |
| Xem `@Valid` là kiểm soát an ninh | Dữ liệu hợp lệ vẫn có thể bị gán sai quyền | DTO, allowlist và kiểm tra quyền ở backend |
| Log nguyên `rejectedValue` | Rò rỉ thông tin nhạy cảm | Log mã lỗi/field đã chọn lọc, che dữ liệu nhạy cảm |
| Chia sẻ `Errors` giữa threads | Trạng thái sai, lẫn lỗi giữa yêu cầu | Tạo kết quả theo vòng đời request/target |

## 15. Câu hỏi ôn tập

**Câu 1.** `age="abc"` gửi tới property `int age`. Validator ghi `age.min` có phải lỗi quan trọng đầu tiên?  
Không. Lỗi quan trọng trước hết là **chuyển kiểu**, thường có mã `typeMismatch` và `isBindingFailure()=true`. Validator nên tránh kết luận tuổi quá thấp từ giá trị primitive mặc định.

**Câu 2.** `startDate > endDate`; nên dùng `reject` hay `rejectValue`?  
Cả hai có thể hợp lệ tùy UI. Nếu lỗi liên quan **quan hệ giữa hai field**, `reject` tạo global error là lựa chọn tự nhiên; nếu muốn người dùng sửa trực tiếp `endDate`, có thể gắn `rejectValue("endDate", ...)`.

**Câu 3.** Có 3 `FieldError` trên cùng một field và 1 `ObjectError` toàn đối tượng. `getErrorCount()` bằng bao nhiêu?  
Bằng 4. Số field khác nhau có lỗi chỉ là 1; số lỗi không bằng số field.

**Câu 4.** `Errors` khác `BindingResult` ở đâu?  
`Errors` khai báo các thao tác ghi và truy vấn lỗi; `BindingResult` mở rộng để cung cấp thêm ngữ cảnh binding và tích hợp model. `DataBinder.getBindingResult()` trả `BindingResult`, có thể truyền dưới kiểu `Errors` khi validator cần ghi lỗi.

**Câu 5.** `getFieldError("username")` đủ để lấy tất cả lỗi username không?  
Không. Nó chỉ lấy lỗi đầu tiên hoặc `null`. Dùng `getFieldErrors("username")` nếu cần đủ danh sách.

**Câu 6.** Khi controller có `@Valid @ModelAttribute("form")`, đặt `BindingResult` ở đâu?  
Ngay sau parameter đó trong method signature; xử lý `hasErrors()` trước khi gọi nghiệp vụ.

**Câu 7.** Vì sao không nên trả trực tiếp `BindingResult` dưới dạng JSON?  
Nó là cấu trúc nội bộ của binding/validation, có thể gồm metadata và giá trị nhập nhạy cảm. Nên chuyển sang error DTO phù hợp API contract, dùng mã và thông báo đã chọn lọc.

**Ghi nhớ:** `Validator` **quyết định lỗi quy tắc**; `DataBinder` **thu thập lỗi binding**; `Errors` **là hợp đồng lưu/truy vấn lỗi**; `BindingResult` **là kết quả có thêm thông tin binding**; `FieldError` **gắn với field**, `ObjectError` **gắn với object**; `MessageSource` **chuyển mã lỗi thành lời nhắn phù hợp ngôn ngữ**.

## Tài liệu tham khảo chính thức

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — ValidationUtils API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/ValidationUtils.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
