# BindingResult mở rộng Errors với thông tin binding trong Spring Framework

## 1. Mục tiêu và bối cảnh

Trong Spring, việc nhận dữ liệu đầu vào thường đi qua hai bước có liên quan nhưng khác nhau:

1. **Data binding**: đọc dữ liệu nguồn (ví dụ chuỗi tham số HTTP) và gán/chuyển kiểu vào thuộc tính của đối tượng Java.
2. **Validation**: kiểm tra đối tượng hoặc giá trị có thỏa các quy tắc được công bố hay không.

Ví dụ biểu mẫu đăng ký có `age` kiểu `Integer` và `email` kiểu `String`:

```text
age=abc
email=not-an-email
admin=true
```

- `age=abc` không chuyển được từ `String` thành `Integer`: lỗi **binding/type conversion**.
- `email=not-an-email` chuyển thành `String` thành công nhưng không thỏa quy tắc email: lỗi **validation** nếu có validator phù hợp.
- `admin=true` không thuộc tập thuộc tính được phép nhập: dữ liệu có thể bị **suppress** (ngăn bind). Trường bị suppress không tự động trở thành một `FieldError`.

Spring cung cấp `org.springframework.validation.Errors` để ghi và đọc lỗi theo đối tượng/trường. `org.springframework.validation.BindingResult` **kế thừa `Errors`**, giữ toàn bộ khả năng đó và bổ sung thông tin về quá trình liên kết dữ liệu: đối tượng được bind, giá trị gốc, thông tin chuyển đổi, các trường bị chặn và model dùng để dựng lại form.

Ý chính của bài: **`Errors` là hợp đồng quản lý lỗi; `BindingResult` là kết quả binding có khả năng quản lý lỗi và tra cứu ngữ cảnh binding.** Đây là quan hệ kế thừa interface, không phải hai hệ thống lỗi độc lập.

## 2. Quan hệ kế thừa và vị trí trong quá trình xử lý

```text
                  Errors (interface)
                  ├─ reject(...), rejectValue(...)
                  ├─ hasErrors(), getErrorCount()
                  ├─ getGlobalErrors(), getFieldErrors()
                  ├─ getFieldValue(...), getFieldType(...)
                  └─ getObjectName(), nested path, ...
                         ^
                         | extends
                         |
               BindingResult (interface)
                  ├─ getTarget()
                  ├─ getModel()
                  ├─ getRawFieldValue(...)
                  ├─ findEditor(...)
                  ├─ resolveMessageCodes(...)
                  ├─ getSuppressedFields()
                  ├─ addError(...)
                  └─ recordFieldValue(...), ...
                         ^
                         | implements
                         |
            AbstractBindingResult (base class)
                         ^
                         |
             BeanPropertyBindingResult
             DirectFieldBindingResult
             MapBindingResult
             ... (các cách lưu/truy cập target)
```

`BindingResult extends Errors` có hai hệ quả trực tiếp:

- Một biến kiểu `BindingResult` **dùng được mọi phương thức của `Errors`**, ví dụ `result.hasErrors()`, `result.rejectValue(...)` hay `result.getFieldErrors()`.
- Một hàm chỉ cần kiểm tra hoặc đăng ký lỗi có thể nhận kiểu `Errors`. Khi cần biết target, giá trị thô, trường bị suppress hoặc model, khai báo `BindingResult`.

Ví dụ chữ ký rút gọn:

```java
// Trích API, không phải chương trình độc lập:
public interface BindingResult extends Errors {
    Object getTarget();
    java.util.Map<String, Object> getModel();
    Object getRawFieldValue(String field);
    String[] getSuppressedFields();
    // Còn các phương thức khác.
}
```

Tùy phiên bản và chú thích nullability, chữ ký Javadoc thực tế có thêm annotation hoặc khai báo default methods. Điểm cần hiểu là quan hệ `extends Errors` và trách nhiệm của từng nhóm API.

## 3. Errors cung cấp những gì?

`Errors` không tự thực hiện binding. Nó định nghĩa cách **ghi nhận và truy vấn** lỗi của một đối tượng. Những API tiêu biểu:

| API thuộc `Errors` | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getObjectName()` | Tên đối tượng đang được kiểm tra | `"signupForm"` |
| `hasErrors()`, `getErrorCount()` | Có lỗi không, tổng bao nhiêu lỗi | `true`, `2` |
| `reject(code, ...)` | Ghi lỗi ở mức toàn đối tượng | `"registrationClosed"` |
| `rejectValue(field, code, ...)` | Ghi lỗi cho một thuộc tính | `rejectValue("email", "invalidEmail")` |
| `getGlobalErrors()` | Danh sách lỗi cấp đối tượng | Lỗi không áp vào một field cụ thể |
| `getFieldErrors()` | Danh sách lỗi theo field | Lỗi `age`, `email` |
| `getFieldError("age")` | Lỗi đầu tiên của field | Một `FieldError` hoặc `null` |
| `getFieldValue("age")` | Giá trị field hiển thị/giữ lại trong ngữ cảnh lỗi | Có thể là chuỗi nhập bị từ chối |
| `getFieldType("age")` | Kiểu field nếu xác định được | `Integer.class` |
| `setNestedPath(...)`, `pushNestedPath(...)`, `popNestedPath()` | Hỗ trợ lỗi trên đối tượng lồng nhau | `address.zipCode` |

**Hai loại đối tượng lỗi:**

- `ObjectError` mô tả lỗi ở mức đối tượng, thường không gắn với một thuộc tính cụ thể.
- `FieldError extends ObjectError` mô tả lỗi trên field, có thêm `getField()`, `getRejectedValue()` và `isBindingFailure()`.

Ví dụ: `@NotBlank` trên `email` thường tạo một lỗi field; điều kiện “ngày bắt đầu phải trước ngày kết thúc” có thể dùng lỗi toàn object nếu quy tắc liên quan nhiều trường.

**`Errors` không tương đương Bean Validation**. Một `Validator` có thể nhận `Errors` và gọi `rejectValue`. `@Valid`/`@Validated` là cơ chế kích hoạt validation trong bối cảnh thích hợp; chính `Errors` chỉ là nơi lưu/truy vấn lỗi.

## 4. BindingResult bổ sung gì so với Errors?

### 4.1. `getTarget()`: đối tượng vừa được bind

`getTarget()` trả về đối tượng đích mà kết quả binding gắn với, nếu có. Đối tượng có thể là JavaBean, `Map` hoặc một cấu trúc khác tùy implementation. Trường hợp constructor binding thất bại trong một số quy trình, không được giả định target lúc nào cũng có thể lấy được.

Có thể xem:

```java
Object boundObject = result.getTarget();
```

Trong MVC, controller thường đã có tham số `@ModelAttribute SignupForm form`, vì thế không cần gọi `getTarget()` chỉ để truy cập cùng đối tượng. API này đặc biệt hữu ích khi thao tác trực tiếp với `DataBinder` hoặc công cụ tổng quát nhận kết quả binding.

### 4.2. `getRawFieldValue(field)`: giá trị thuộc tính dạng thô

`getRawFieldValue("age")` trả về giá trị field trong đối tượng đích ở dạng thô mà implementation truy cập được, hoặc `null` nếu không xác định được. Nó khác `Errors.getFieldValue("age")`: phương thức của `Errors` có thể trả lại **giá trị bị từ chối** để hiện lại trên form khi conversion thất bại.

Ví dụ khi client gửi `age=abc` và kiểu đích là `Integer`:

- Chuyển kiểu thất bại nên `form.getAge()` vẫn có thể là `null`.
- `result.getRawFieldValue("age")` có thể là `null` vì đó là giá trị thực của thuộc tính.
- `result.getFieldValue("age")` có thể trả `"abc"` vì Spring lưu giá trị đã bị từ chối cho việc hiển thị thông báo trên form.
- `result.getFieldError("age").getRejectedValue()` chứa `"abc"`; `isBindingFailure()` bằng `true`.

Không nên nhầm “raw field value” với “chuỗi HTTP ban đầu”. Với lỗi chuyển kiểu, thông tin đầu vào bị từ chối thường nằm trong `FieldError`. Tính sẵn có của raw field value phụ thuộc kiểu target và implementation.

### 4.3. `getModel()` và `MODEL_KEY_PREFIX`: thông tin để dựng lại form

`BindingResult.getModel()` tạo một `Map<String, Object>` có **hai phần tử cốt lõi**:

1. `objectName` → chính đối tượng đã bind.
2. `BindingResult.MODEL_KEY_PREFIX + objectName` → đối tượng `BindingResult`.

Giá trị của `BindingResult.MODEL_KEY_PREFIX` là:

```text
org.springframework.validation.BindingResult.
```

Nếu tên đối tượng là `signupForm`, hai key là:

```text
signupForm
org.springframework.validation.BindingResult.signupForm
```

Framework/view template có thể sử dụng bộ đôi này để hiển thị nội dung form và lỗi tương ứng. `getModel()` **tạo map mới cho mỗi lần gọi**; sửa map vừa nhận rồi gọi lại `getModel()` sẽ không giữ các sửa đổi đó. Khi sử dụng Spring MVC thông thường, Spring đã quản lý model và BindingResult cho model attribute; bạn hiếm khi phải tự xây hai key.

### 4.4. `getSuppressedFields()`: field bị từ chối binding

Khi `DataBinder` được cấu hình `setAllowedFields(...)` hoặc chính sách field tương ứng, tên các field không được phép gán có thể được ghi nhận trong `BindingResult`. `getSuppressedFields()` trả về danh sách tên field đã bị chặn.

Ví dụ:

```java
binder.setAllowedFields("age", "email");
// Request có thêm admin=true.
String[] fields = binder.getBindingResult().getSuppressedFields();
```

Nếu field `admin` bị suppress, mảng trên có thể chứa `"admin"`. **Đừng suy luận `hasErrors() == true` chỉ vì có suppressed fields**: việc chặn field không nhất thiết tạo `FieldError`. Nếu chính sách ứng dụng cần từ chối cả request khi có field ngoài allowlist, hãy kiểm tra mảng và trả lỗi phù hợp. Đây là thông tin quan trọng bổ sung của `BindingResult` bên cạnh tập lỗi của `Errors`.

### 4.5. Các API mở rộng khác

| API thuộc `BindingResult` | Khi nào hữu ích |
| --- | --- |
| `findEditor(field, valueType)` | Tìm `PropertyEditor` đã đăng ký theo field/kiểu nếu implementation cung cấp |
| `getPropertyEditorRegistry()` | Truy cập registry editor nếu tồn tại; có thể `null` |
| `resolveMessageCodes(code)` | Lấy các mã message tương ứng lỗi cấp đối tượng |
| `resolveMessageCodes(code, field)` | Lấy mã message cụ thể hóa theo object/field/kiểu; phục vụ i18n |
| `addError(ObjectError)` | Ghi thêm `ObjectError`/`FieldError` khi chiến lược xử lý lỗi cần |
| `recordFieldValue(field, type, value)` | Giữ thông tin field trong các tình huống như chưa tạo được target |
| `recordSuppressedField(field)` | Ghi nhận field bị từ chối trong quá trình bind |

Đa phần code ứng dụng chỉ cần `hasErrors`, `getFieldErrors`, `getSuppressedFields` và đôi khi `getModel`. Các API editor/message codes thường hữu ích khi xây hạ tầng binding, formatter hoặc giao diện biểu mẫu.

## 5. Quy trình Spring DataBinder tạo và dùng BindingResult

```text
Nguồn dữ liệu (HTTP parameters / MutablePropertyValues)
                         |
                         v
                    DataBinder
               +------------------+
               | chọn allowedFields |
               | tra tên property   |
               | conversion          |
               | setter/field access |
               +------------------+
                         |
             +-----------+-----------+
             |                       |
         thành công            conversion thất bại
             |                       |
      target được gán       FieldError(typeMismatch,
                             bindingFailure=true,
                             rejectedValue="abc")
             |                       |
             +-----------+-----------+
                         |
                 Validator / @Valid
                   (nếu kích hoạt)
                         |
                FieldError/ObjectError
                về quy tắc validation
                         |
                         v
                 BindingResult
                 = Errors API
                 + binding metadata
                         |
           controller / view / API response
```

Các điểm cần phân biệt:

- `DataBinder` là **thành phần thực thi binding**, còn `BindingResult` là **kết quả** được thu thập sau khi bind. Trong code, lấy bằng `binder.getBindingResult()`.
- Việc chuyển kiểu có thể dùng `ConversionService`, các `Converter`/`Formatter`, hoặc `PropertyEditor` theo cấu hình.
- Lỗi conversion thường có mã cơ sở như `typeMismatch`; lỗi từ validator có mã do quy tắc kiểm tra đặt ra, ví dụ `invalidEmail`.
- Validator chạy **khi được gọi hoặc cấu hình kích hoạt**, không phải cứ lấy `BindingResult` là validation tự diễn ra. Với `DataBinder` thuần túy, ví dụ gọi `binder.validate()`; với Spring MVC, có thể dùng `@Valid` và Bean Validation provider.
- Khi binding thất bại cho một field, các field khác vẫn có thể được gán thành công. Vì vậy đối tượng đích có thể chứa giá trị hợp lệ một phần; không tiếp tục nghiệp vụ nếu kết quả còn lỗi.
- Không nên xem việc một field được suppress là “đã được kiểm tra an toàn toàn bộ request”. Đó là một tín hiệu để áp dụng chính sách của controller.

## 6. Ví dụ Java 17+ chạy độc lập với Spring Framework 6.2

Ví dụ chạy trên **JDK 17** và Maven, không cần web server hoặc database. Nó tạo `SignupForm`, cho `DataBinder` nhận ba input `age=abc`, `email=not-an-email`, `admin=true`, sau đó chạy một `Validator` tùy biến.

Ta dự kiến thấy:

- Một `FieldError` do không chuyển được `age` sang `Integer`.
- Một `FieldError` do `email` không chứa `@`.
- `admin` nằm trong suppressed fields vì không có trong allowlist.
- Model chứa key cho đối tượng và key cho `BindingResult`.

### 6.1. Cấu trúc tệp

```text
binding-result-demo/
├── pom.xml
└── src/main/java/demo/BindingResultDemo.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>binding-result-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BindingResultDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` kéo theo các module Spring cơ bản cần cho `DataBinder` và `Validator`. Ví dụ không cần dependency Jakarta Bean Validation vì dùng trực tiếp interface `org.springframework.validation.Validator`.

### 6.3. `src/main/java/demo/BindingResultDemo.java`

```java
package demo;

import java.util.Arrays;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public final class BindingResultDemo {

    public static final class SignupForm {
        private Integer age;
        private String email;

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }

    static final class SignupValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return SignupForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            SignupForm form = (SignupForm) target;
            if (form.getEmail() == null ||
                    !form.getEmail().contains("@")) {
                errors.rejectValue(
                        "email", "invalidEmail", "Email must contain @");
            }
        }
    }

    public static void main(String[] args) {
        SignupForm form = new SignupForm();

        DataBinder binder = new DataBinder(form, "signupForm");
        binder.setAllowedFields("age", "email");
        binder.setValidator(new SignupValidator());

        MutablePropertyValues incoming = new MutablePropertyValues();
        incoming.add("age", "abc");
        incoming.add("email", "not-an-email");
        incoming.add("admin", "true");

        binder.bind(incoming);
        binder.validate();

        BindingResult result = binder.getBindingResult();
        FieldError ageError = result.getFieldError("age");
        FieldError emailError = result.getFieldError("email");

        System.out.println("hasErrors=" + result.hasErrors());
        System.out.println("errorCount=" + result.getErrorCount());

        System.out.println("age.code=" + ageError.getCode());
        System.out.println("age.rejected=" + ageError.getRejectedValue());
        System.out.println("age.bindingFailure=" +
                ageError.isBindingFailure());

        System.out.println("email.code=" + emailError.getCode());
        System.out.println("email.bindingFailure=" +
                emailError.isBindingFailure());

        System.out.println("age.fieldValue=" +
                result.getFieldValue("age"));
        System.out.println("age.rawFieldValue=" +
                result.getRawFieldValue("age"));
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));

        Map<String, Object> model = result.getModel();
        System.out.println("sameTarget=" +
                (result.getTarget() == form));
        System.out.println("model.hasForm=" +
                model.containsKey("signupForm"));
        System.out.println("model.hasBindingResult=" +
                model.containsKey(
                        BindingResult.MODEL_KEY_PREFIX + "signupForm"));
    }
}
```

Giải thích những dòng đáng chú ý:

1. `DataBinder(form, "signupForm")` tạo binder cho đối tượng JavaBean và tên object. Tên này xuất hiện trong đường message code và key model.
2. `setAllowedFields("age", "email")` giới hạn property binding. Field `admin` bị suppress mặc dù dữ liệu nguồn có gửi.
3. `binder.bind(incoming)` thử chuyển `age` sang `Integer`. Chuỗi `"abc"` làm phát sinh lỗi kiểu `typeMismatch`; giá trị không được gán vào `form.age`.
4. `binder.validate()` chạy `SignupValidator`. Validator nhận **kiểu tham số `Errors`** nên không phụ thuộc API nâng cao của `BindingResult`, nhưng lỗi nó ghi vẫn xuất hiện trong cùng `BindingResult` cuối cùng.
5. `FieldError.isBindingFailure()` phân biệt lỗi chuyển đổi với lỗi quy tắc do validator tạo. `getFieldValue` giữ giá trị người dùng đã nhập để dựng lại form; `getRawFieldValue` lấy giá trị hiện tại của thuộc tính đích.
6. `getModel()` cho thấy `BindingResult` có thêm trách nhiệm xây dựng thông tin model, điều mà `Errors` không định nghĩa.

### 6.4. Lệnh chạy và stdout dự kiến

Tại thư mục `binding-result-demo`:

```bash
mvn -q compile exec:java
```

**Stdout chương trình:**

```text
hasErrors=true
errorCount=2
age.code=typeMismatch
age.rejected=abc
age.bindingFailure=true
email.code=invalidEmail
email.bindingFailure=false
age.fieldValue=abc
age.rawFieldValue=null
suppressed=[admin]
sameTarget=true
model.hasForm=true
model.hasBindingResult=true
```

Đây là output của chính phương thức `main`; ví dụ in giá trị logic để tránh lệ thuộc định dạng thông báo dài của Spring. `getFieldValue("age")` trả giá trị bị từ chối do conversion thất bại, còn `getRawFieldValue("age")` trả `null` vì `Integer age` chưa được gán. Spring có thể tạo nhiều mã thông báo chi tiết cho cùng một lỗi, nhưng ví dụ chỉ in mã cơ sở `typeMismatch` và `invalidEmail`.

Nếu thay `age=abc` bằng `age=21`, lỗi binding tại field `age` biến mất. Nếu thay `email=not-an-email` bằng `email=user@example.com`, lỗi validation biến mất. Tuy nhiên, **`admin` vẫn bị suppress** và `getSuppressedFields()` vẫn có thể chứa tên đó; số lỗi từ `Errors` không tự tăng vì suppressed field.

## 7. Dùng BindingResult trong Spring MVC

### 7.1. Vị trí tham số rất quan trọng

Khi controller dùng `@ModelAttribute` và kích hoạt validation, `BindingResult` (hoặc `Errors`) phải đặt **ngay sau** tham số model attribute tương ứng nếu muốn xử lý lỗi trong phương thức controller.

```java
// Đoạn minh họa controller Spring MVC, chưa phải tệp độc lập.
// Giả sử có bean SignupService và một view signup/form.
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "signup/form";
    }

    signupService.register(form);
    return "redirect:/signup/success";
}
```

Ở đây `@Valid` là `jakarta.validation.Valid`, còn `@ModelAttribute` thuộc `org.springframework.web.bind.annotation`. Một ứng dụng Spring MVC thực tế cần cấu hình validation provider (ví dụ Spring Boot starter validation) và các bean/view tương ứng.

Sai vị trí:

```java
// Không đúng vị trí BindingResult đối với signupForm:
public String submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        Model model,
        BindingResult result) {
    // ...
}
```

Ví dụ sai ở trên đặt `Model` chen giữa form và `BindingResult`; Spring MVC không thể dùng tham số kết quả đó như kết quả lỗi của model attribute liền trước theo hợp đồng controller. Nếu không có `BindingResult` phù hợp, lỗi validation/binding thông thường được đưa sang cơ chế exception của framework thay vì controller nhận trực tiếp lỗi ở tham số này.

**Một controller có nhiều form object** có thể khai báo hai cặp sát nhau, mỗi `BindingResult` thuộc về form đứng ngay trước nó. Dùng tên `@ModelAttribute("...")` rõ ràng giúp ánh xạ view và thông báo lỗi đúng đối tượng.

### 7.2. Hiển thị lỗi biểu mẫu

Cách xử lý phổ biến cho ứng dụng trả view:

- `result.hasErrors()` quyết định quay lại form.
- `result.getFieldErrors()` dùng để hiển thị lỗi theo input như `email` hoặc `age`.
- `result.getGlobalErrors()` dành cho lỗi liên quan nhiều field hoặc trạng thái đối tượng.
- `FieldError.getRejectedValue()`/`getFieldValue()` hỗ trợ giữ lại dữ liệu người dùng vừa nhập, kể cả khi conversion thất bại.
- View engine hoặc Spring form tag có thể sử dụng các key model gắn với BindingResult. Với MVC thông thường, framework cung cấp sẵn kết quả theo tên model attribute.

Không đưa nguyên `FieldError` hoặc `BindingResult` ra JSON công khai khi chưa lọc: rejected value có thể chứa thông tin nhạy cảm, chuỗi dài hay dữ liệu do client kiểm soát. Với API, tạo response lỗi có cấu trúc riêng (field, mã an toàn, thông báo đã chọn) và escape khi hiển thị lên HTML.

### 7.3. BindingResult có áp dụng cho @RequestBody JSON không?

`@RequestBody` thường đi qua `HttpMessageConverter` (ví dụ Jackson), trong khi `@ModelAttribute` dùng cơ chế data binding kiểu property/constructor của MVC. Với `@Valid @RequestBody`, lỗi Bean Validation có thể được chuyển qua cơ chế lỗi MVC và một số trường hợp controller có thể khai báo `Errors`/`BindingResult` phù hợp. **Nhưng không suy ra rằng mọi lỗi JSON đều nằm trong BindingResult**: JSON sai cú pháp, body không đọc được hay lỗi deserialize nghiêm trọng có thể phát sinh ngoại lệ trước khi có model object để validation, ví dụ `HttpMessageNotReadableException`.

Khi xử lý REST API, nên có chiến lược lỗi chung qua `@ControllerAdvice` và `@ExceptionHandler`, và phân biệt lỗi JSON không đọc được, lỗi Bean Validation và lỗi nghiệp vụ. Không dùng `DataBinder.setAllowedFields` để cho rằng đã hạn chế mọi property mà Jackson deserialize từ JSON; cơ chế đó cần được kiểm soát ở DTO và cấu hình JSON riêng.

## 8. Phân biệt lỗi binding, lỗi validation và field bị suppress

| Trường hợp | Bước phát hiện | Thông tin thường gặp | `hasErrors()` |
| --- | --- | --- | --- |
| `age=abc` khi `age` là `Integer` | Type conversion trong data binding | `FieldError("age")`, `code="typeMismatch"`, `bindingFailure=true`, `rejectedValue="abc"` | `true` |
| `email=not-an-email` bị validator bác | Validation sau binding | `FieldError("email")`, code do validator tạo, `bindingFailure=false` | `true` |
| Hai trường riêng hợp lệ nhưng sai quan hệ | Validation cấp object | `ObjectError` từ `reject(...)` | `true` |
| `admin=true` bị `allowedFields` chặn | Suppression trong data binding | `getSuppressedFields()` có `"admin"` | Không tự động chuyển thành `true` |
| Dữ liệu hợp lệ và không có lỗi validator | Bind + validation thành công | Không có `ObjectError`/`FieldError` | `false` |

Một lỗi field có thể xuất hiện nhiều lần (nhiều constraint thất bại). `getFieldError("email")` chỉ trả lỗi đầu tiên theo cách ghi nhận, trong khi `getFieldErrors("email")` trả danh sách. Nếu cần một thông báo cho mỗi loại vấn đề, hãy xem danh sách và áp dụng chính sách chọn message rõ ràng thay vì phụ thuộc thứ tự ngẫu nhiên.

Thông tin từ `getSuppressedFields()` cần được xử lý riêng. Nhiều ứng dụng muốn trả HTTP 400 khi request có trường ngoài hợp đồng, nhưng Spring không mặc nhiên làm việc đó chỉ từ `hasErrors()`.

## 9. Vai trò của message codes và quốc tế hóa

Một `ObjectError` hoặc `FieldError` có thể chứa:

- `objectName` và (với field error) `field`.
- `codes`: danh sách message code từ cụ thể đến tổng quát.
- `arguments`: tham số phục vụ nội suy thông báo.
- `defaultMessage`: thông báo dự phòng.
- Với `FieldError`: `rejectedValue` và `bindingFailure`.

Ví dụ lỗi `typeMismatch` trên field `age` của `signupForm` có thể được giải thành các biến thể như:

```text
typeMismatch.signupForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

Đây là **một ví dụ về cách `DefaultMessageCodesResolver` tạo chuỗi mã**, không phải cam kết mọi `BindingResult` dùng chính xác cùng chiến lược/cấu hình. `BindingResult.resolveMessageCodes("typeMismatch", "age")` có thể tạo các mã phù hợp; `MessageSource` sẽ chọn bản dịch từ các mã và locale. `FieldError.getCode()` chỉ cung cấp mã lỗi cơ sở, còn `getCodes()` cho toàn bộ mã ứng viên.

Ví dụ ứng dụng có thể định nghĩa thông báo:

```properties
typeMismatch.signupForm.age=Vui lòng nhập tuổi bằng số nguyên.
invalidEmail.signupForm.email=Địa chỉ email chưa hợp lệ.
```

Không nên đưa nguyên tên exception hoặc chi tiết stack trace vào thông báo trả cho người dùng. Trường hợp lỗi server, bộ lọc thông báo và bản địa hóa phải thống nhất với cách xử lý lỗi API/view của dự án.

## 10. Các lưu ý khi làm việc với BindingResult

### 10.1. Kết quả binding không phải validator

`DataBinder.bind(...)` ghi nhận quá trình chuyển/gán dữ liệu. `binder.validate()` sử dụng các validator đã cấu hình. `@Valid` và `@Validated` giúp Spring MVC kích hoạt validation trong điều kiện thích hợp. Không tự cho rằng `BindingResult` có lỗi validation nếu chưa có bước validation thực sự.

### 10.2. Một FieldError không nhất thiết là một binding failure

`FieldError.isBindingFailure()` trả `true` với lỗi trong lúc bind như type mismatch; validator ghi lỗi field thường tạo `FieldError` với `bindingFailure=false`. Đây là thông tin cần thiết nếu API muốn phân biệt thông báo “không đọc được giá trị” và “giá trị đọc được nhưng không hợp lệ”.

### 10.3. getFieldValue() không đồng nhất getRawFieldValue()

Lỗi binding có thể lưu giá trị bị từ chối khác với giá trị đích. Khi dựng lại biểu mẫu, cần giữ được chuỗi người dùng đã gửi; vì vậy không lấy raw target value để thay cho rejected value trong mọi tình huống.

### 10.4. Target có thể đã được cập nhật một phần

Một số field vẫn bind thành công dù field khác lỗi. Khi `hasErrors()`, không được tự động lưu entity hoặc thực thi nghiệp vụ nhạy cảm dựa trên đối tượng đã bị gán dở. Nên dùng DTO/form object chuyên biệt, kiểm tra lỗi đầy đủ, rồi ánh xạ sang lệnh nghiệp vụ.

### 10.5. Cẩn thận với tên field lồng nhau

Tên lỗi có thể là `address.zipCode` hoặc `items[0].quantity`. `Errors` có nested path API, còn `BindingResult` có thể đi cùng kiểu property access tương ứng. Đừng tự parse mọi dấu chấm hoặc dấu ngoặc như chuỗi đơn giản nếu cần truy cập thông tin lỗi dạng cấu trúc.

### 10.6. Không nhầm suppressed field với lỗi

Dữ liệu ngoài allowlist thường không được gán, nhưng không mặc nhiên tăng `getErrorCount()`. Nếu muốn chặn overposting, kiểm tra `getSuppressedFields()` và phản hồi lỗi/ghi log phù hợp mà không lộ dữ liệu nhạy cảm.

### 10.7. Chú ý dữ liệu người dùng trong rejected value

`FieldError.getRejectedValue()` có thể chứa input do client cung cấp. Tránh phản chiếu thẳng HTML chưa escape, tránh đưa password/token hoặc dữ liệu nhạy cảm vào log; giới hạn độ dài và chuyển thành lỗi có message code thân thiện khi trả API.

### 10.8. BindingResult được gắn với một object name

Trong MVC, key mẫu là `org.springframework.validation.BindingResult.<objectName>`. Nếu dùng sai tên object/attribute khi tự xây model hoặc khi giữ lỗi giữa các bước, view có thể không hiển thị đúng lỗi hoặc nhầm kết quả giữa hai form. Tên object phải nhất quán.

### 10.9. Đừng lạm dụng BindingResult ở tầng nghiệp vụ

Service domain có thể trả lỗi nghiệp vụ bằng kết quả chuyên biệt, exception hoặc cấu trúc lỗi được thiết kế rõ. `BindingResult` là abstraction của tầng binding/validation Spring; không nhất thiết phải mang theo nó xuyên suốt service và repository.

## 11. Tình huống thực tế: sửa lỗi và kiểm thử

### Tình huống A: Form nhập sai kiểu nhưng vẫn hiển thị lại chữ người dùng đã gõ

Client gửi `age=abc`. `form.getAge()` bằng `null`, nhưng `result.getFieldValue("age")` có thể là `"abc"` và `FieldError.getRejectedValue()` cũng là `"abc"`. View nên dùng cơ chế binding của Spring để hiện lại giá trị, không tự gán “null” vào input và làm mất thông tin người dùng vừa nhập.

### Tình huống B: Có sai định dạng email nhưng chuyển kiểu vẫn thành công

Chuỗi `email=not-an-email` là một `String` hợp lệ ở mức binding. Một validator có thể gọi `errors.rejectValue("email", "invalidEmail")` để báo lỗi; `FieldError.isBindingFailure()` sẽ phân biệt đây là lỗi validation.

### Tình huống C: Request cố thêm trường quyền hạn

Client gửi `admin=true`, nhưng binder chỉ cho phép `age` và `email`. `getSuppressedFields()` cung cấp dấu hiệu cần kiểm tra. Không có nghĩa server đã “validate” và kết luận dữ liệu an toàn; chính sách từ chối trường lạ thuộc controller/API.

### Tình huống D: Form có nhiều lỗi

Gọi `hasErrors()` để ngăn nghiệp vụ khi còn lỗi, rồi dùng `getFieldErrors()` và `getGlobalErrors()` để dựng tập thông báo. Với các trường có nhiều lỗi, không mặc định mọi field chỉ có một `FieldError`. Với API, sắp xếp kết quả và gắn mã lỗi ổn định sẽ giúp client dễ xử lý.

### Checklist kiểm thử

1. Input hợp lệ: `hasErrors=false`, đúng giá trị target, suppressed fields trống.
2. Sai kiểu (số/ngày): `FieldError.isBindingFailure=true`, `getRejectedValue` giữ giá trị sai.
3. Validation sai: `FieldError.isBindingFailure=false`, mã lỗi do validator tạo.
4. Hai field cùng lỗi: `getErrorCount` phản ánh số lỗi, truy vấn theo từng field chính xác.
5. Field ngoài allowlist: target không bị thay đổi, `getSuppressedFields` có tên field.
6. Field lồng nhau: đường dẫn field và nested error đúng.
7. Tên model attribute: `getModel` có đúng hai key theo tên object.
8. Trong MVC: `BindingResult` đứng ngay sau form object, view thấy đúng field errors và giá trị bị từ chối.
9. Thông báo lỗi: không chứa secret, không phản chiếu markup nguy hiểm, hỗ trợ locale khi cần.

## 12. Tự kiểm tra kiến thức

**Câu 1:** Nếu một hàm chỉ cần gọi `rejectValue` và `hasErrors`, nên nhận kiểu nào?

**Trả lời:** `Errors` thường đủ. Hàm vẫn nhận được instance `BindingResult` vì interface này kế thừa `Errors`.

**Câu 2:** Khi cần lấy danh sách field đã bị chặn bởi `allowedFields`, nên dùng gì?

**Trả lời:** `BindingResult.getSuppressedFields()`.

**Câu 3:** `getFieldValue("age")` có luôn bằng `getRawFieldValue("age")` không?

**Trả lời:** Không. Khi conversion thất bại, `getFieldValue` có thể ưu tiên giá trị bị từ chối để hiển thị, còn `getRawFieldValue` phản ánh giá trị thuộc tính đích.

**Câu 4:** Một `FieldError` có luôn là lỗi binding không?

**Trả lời:** Không. Validator cũng tạo lỗi theo field. Dùng `isBindingFailure()` và mã lỗi để phân biệt ngữ cảnh.

**Câu 5:** `BindingResult.getModel()` bổ sung mấy key quan trọng?

**Trả lời:** Một key cho object và một key `BindingResult.MODEL_KEY_PREFIX + objectName` cho chính kết quả binding.

**Câu 6:** Việc `getSuppressedFields().length > 0` có khiến `hasErrors()` tự động thành `true` không?

**Trả lời:** Không. Suppressed fields phải được kiểm tra theo chính sách bảo vệ đầu vào của ứng dụng.

## 13. Tài liệu chính thức

- [Spring Framework Javadoc — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/BindingResult.html): các API bổ sung, `MODEL_KEY_PREFIX`, kế thừa `Errors`.
- [Spring Framework Javadoc — Errors](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/Errors.html): `reject`, `rejectValue`, lỗi theo object/field và API truy vấn.
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/DataBinder.html): `bind`, `validate`, `getBindingResult`, `setAllowedFields`.
- [Spring Framework — Validator](https://docs.spring.io/spring-framework/reference/6.2/core/validation/validator.html): triển khai `Validator` và sử dụng `Errors`.
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): cách đặt `BindingResult` ngay sau tham số form và xử lý lỗi trong controller.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated` và các đường xử lý lỗi.