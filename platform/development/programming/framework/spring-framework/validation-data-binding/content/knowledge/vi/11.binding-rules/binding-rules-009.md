# DefaultBindingErrorProcessor và các mã lỗi required, typeMismatch, methodInvocation

Trong Spring Framework, một thao tác **data binding** không chỉ đưa giá trị đầu vào vào đối tượng Java. Nó còn có thể phát hiện trường bắt buộc bị thiếu, giá trị không chuyển được sang kiểu đích, hoặc phương thức setter thất bại. `DefaultBindingErrorProcessor` là thành phần mặc định giúp chuyển các tình huống đó thành lỗi có cấu trúc trong `BindingResult`.

Ba mã lỗi trọng tâm:

- `required` — trường được `DataBinder` khai báo là bắt buộc nhưng không được cung cấp theo quy tắc kiểm tra trường đầu vào.
- `typeMismatch` — có giá trị cho một thuộc tính nhưng không chuyển/ép được sang kiểu Java phù hợp.
- `methodInvocation` — gọi phương thức truy cập thuộc tính, thường là setter của JavaBean, gây exception trong quá trình binding.

Đây là các **mã lỗi của bước binding**, không phải mặc định là lỗi của `@NotNull`, `@Min` hay một `Validator` tùy chỉnh. Bài học giải thích vị trí của bộ xử lý lỗi, nguyên nhân tạo từng mã, cách lấy `FieldError`, cách ánh xạ mã sang thông báo, cách tùy biến và ví dụ Java 17 chạy từ dòng lệnh.

## 1. Bối cảnh: DataBinder ghi lỗi như thế nào?

Ở chế độ gắn thuộc tính JavaBean, `DataBinder` nhận đối tượng đích cùng các `PropertyValues` đầu vào. Một chuỗi giá trị như `"25"` có thể được chuyển thành `Integer 25`, còn `"abc"` thì không.

```text
Dữ liệu đầu vào (MutablePropertyValues)
                  |
                  v
           DataBinder.bind(...)
                  |
             kiểm tra các
             required fields
                  |
                  +-- thiếu trường bắt buộc
                  |       |
                  |       v
                  | DefaultBindingErrorProcessor
                  | processMissingFieldError(...)
                  |       |
                  |       +--> FieldError: required
                  |
                  v
     gắn thuộc tính / chuyển kiểu
                  |
                  +-- TypeMismatchException
                  |       |
                  |       +--> processPropertyAccessException(...)
                  |               +--> FieldError: typeMismatch
                  |
                  +-- MethodInvocationException
                  |       |
                  |       +--> processPropertyAccessException(...)
                  |               +--> FieldError: methodInvocation
                  |
                  v
      binder.getBindingResult()
                  |
                  +--> FieldError / ObjectError
                  |
                  v
      (tùy chọn) binder.validate()
                  |
                  +--> lỗi do Validator kiểm tra quy tắc
```

**Phân chia trách nhiệm:**

| Thành phần | Trách nhiệm |
| --- | --- |
| `DataBinder` | Điều phối property binding; quản lý trường bắt buộc, allowed fields, chuyển kiểu và thu thập lỗi. |
| `BindingErrorProcessor` | Giao diện chiến lược chuyển lỗi binding thành lỗi trong `BindingResult`. |
| `DefaultBindingErrorProcessor` | Triển khai mặc định, sử dụng các mã `required`, `typeMismatch`, `methodInvocation`. |
| `PropertyAccessException` | Nhóm exception về truy cập/gắn thuộc tính, gồm `TypeMismatchException` và `MethodInvocationException`. |
| `BindingResult` | Tập hợp lỗi, mã lỗi, đường dẫn trường và giá trị bị từ chối; được dùng cả ở binding và validation. |
| `MessageCodesResolver` | Từ mã cơ sở và tên trường sinh danh sách mã cụ thể hơn để tra thông báo. |
| `MessageSource` | Giải quyết các mã lỗi thành thông báo phù hợp ngôn ngữ/locale. |
| `Validator` | Kiểm tra quy tắc trên đối tượng đã có; nếu không được gọi thì không tự thêm lỗi validation. |

`DefaultBindingErrorProcessor` không quyết định tất cả dữ liệu hợp lệ hay không. Nó chỉ chuyển những **tình huống lỗi binding mà `DataBinder` gửi đến** thành dạng lỗi mà phần còn lại của Spring hiểu được.

## 2. Hai điểm mở rộng của BindingErrorProcessor

Giao diện `org.springframework.validation.BindingErrorProcessor` có hai phương thức quan trọng:

```java
void processMissingFieldError(
        String missingField,
        BindingResult bindingResult);

void processPropertyAccessException(
        PropertyAccessException ex,
        BindingResult bindingResult);
```

Đoạn này là **chữ ký API rút gọn**, không phải một class chạy độc lập.

### 2.1. processMissingFieldError(...)

`DataBinder` gọi chiến lược này khi phát hiện một trường bắt buộc bị thiếu trong `PropertyValues` đầu vào. Triển khai mặc định tạo `FieldError` với mã cơ sở `required` và đăng ký nó vào `BindingResult`.

Đặc điểm cần nhớ: `required` ở đây là **yêu cầu có mặt khi binding**, ví dụ do gọi `binder.setRequiredFields("name")`. Nó không đồng nghĩa với Jakarta `@NotNull` hoặc Spring `ValidationUtils.rejectIfEmptyOrWhitespace`. Những quy tắc sau thuộc lớp validation khác.

### 2.2. processPropertyAccessException(...)

`DataBinder` gọi chiến lược này cho một `PropertyAccessException` được tạo trong quá trình gắn property. Triển khai mặc định dùng:

```java
String baseErrorCode = ex.getErrorCode();
```

Với các subclass thường gặp:

- `TypeMismatchException#getErrorCode()` cung cấp `typeMismatch`.
- `MethodInvocationException#getErrorCode()` cung cấp `methodInvocation`.

`DefaultBindingErrorProcessor` tạo `FieldError` dựa trên loại lỗi và tên thuộc tính gây ra lỗi, sau đó dùng `BindingResult.resolveMessageCodes(...)` để xây danh sách mã phục vụ hiển thị thông báo.

**Không nên cho rằng mọi exception trong binding đều được bộ xử lý này chuyển thành `FieldError`.** Ví dụ, thuộc tính hoàn toàn không tồn tại khi `setIgnoreUnknownFields(false)`, hoặc đường dẫn lồng nhau không truy cập được, có thể ném exception khác mà không trở thành `typeMismatch` hoặc `methodInvocation`.

## 3. Mã required: thiếu trường đầu vào mà binder yêu cầu

Ví dụ đối tượng `AccountForm` có `name` và `age`; phía server muốn trường `name` xuất hiện khi bind:

```java
DataBinder binder = new DataBinder(form, "account");
binder.setRequiredFields("name");
```

Nếu `PropertyValues` chỉ cung cấp `age=20`, không có khóa `name`, bước binding ghi một `FieldError` cho `name` với mã cơ sở `required`.

Một số lưu ý:

1. Không tự động có mã `required` cho mọi thuộc tính Java có giá trị `null`. Phải có cấu hình binder (hoặc xử lý tương đương) yêu cầu trường đó khi bind.
2. `setRequiredFields(...)` kiểm tra dữ liệu tham gia **lần binding hiện tại**, không chỉ nhìn giá trị cuối cùng của bean. Một bean có giá trị khởi tạo từ trước vẫn có thể bị báo thiếu trường nếu request không gửi trường mà binder yêu cầu.
3. Khi trường bắt buộc thiếu, `DataBinder` cũng có thể loại bỏ giá trị tương ứng khỏi danh sách cần tiếp tục áp dụng để tránh xử lý lặp.
4. Chuỗi rỗng hoặc chỉ có khoảng trắng có thể được coi là không cung cấp giá trị phù hợp với kiểm tra required của binder; khi cần ràng buộc nội dung tên thật sự, hãy thiết kế thêm quy tắc validation rõ ràng.
5. Cấu hình required fields ở property binding khác với yêu cầu tham số constructor và khác với annotation `@RequestParam(required = true)` của MVC.

Ví dụ:

```text
PropertyValues: age = "20"
Required fields: name
       |
       v
Không có name trong dữ liệu cần bind
       |
       v
processMissingFieldError("name", bindingResult)
       |
       v
FieldError(field="name", baseCode="required")
```

Không được kết luận `required` tự động nghĩa là HTTP 400 trong mọi bối cảnh. `DataBinder` có thể chạy trong ứng dụng console; khi tích hợp MVC, cách trả HTTP còn phụ thuộc handler, `BindingResult` và exception handling.

## 4. Mã typeMismatch: giá trị không chuyển được sang kiểu đích

Giả sử bean khai báo:

```java
private Integer age;

public void setAge(Integer age) {
    this.age = age;
}
```

Khi client gửi `age=20`, Spring có thể chuyển chuỗi `"20"` thành `Integer 20`. Khi client gửi `age=abc`, chuyển đổi thất bại và một `TypeMismatchException` có thể được tạo trong quá trình gắn property.

`DefaultBindingErrorProcessor` nhận exception đó thông qua `processPropertyAccessException(...)` và ghi `FieldError` với mã cơ sở `typeMismatch`.

```text
age = "abc"  (String)
      |
      v
Chuyển sang java.lang.Integer
      |
      +-- không chuyển được
               |
               v
     TypeMismatchException
               |
               v
     DefaultBindingErrorProcessor
               |
               v
     FieldError("age", "typeMismatch")
```

Mã `typeMismatch` **không phải là** `@Min`, `@Max` hay một custom validator. `age=16` vẫn có thể bind thành công vì đây là số nguyên hợp lệ; chỉ khi gọi validation với quy tắc “tuổi từ 18” mới phát sinh lỗi quy tắc.

Thông tin về giá trị bị từ chối thường được giữ trong `FieldError#getRejectedValue()` để có thể hiển thị lại biểu mẫu. Tránh trả nguyên vẹn giá trị này cho client hoặc ghi vào log nếu trường có thể chứa bí mật.

## 5. Mã methodInvocation: setter/getter ném exception

Xem setter:

```java
public void setStatus(String status) {
    if ("LOCKED".equals(status)) {
        throw new IllegalArgumentException(
                "Status cannot be set to LOCKED through this form");
    }
    this.status = status;
}
```

`status=LOCKED` **đã đúng kiểu `String`**. Lỗi không nằm ở chuyển đổi kiểu. Vấn đề xuất hiện khi Spring gọi setter và setter ném exception. Trong property binding qua JavaBean accessor, tình huống điển hình được biểu diễn bằng `MethodInvocationException` và được `DefaultBindingErrorProcessor` chuyển thành `FieldError` mã cơ sở `methodInvocation`.

```text
status = "LOCKED" (String, đúng kiểu)
       |
       v
  setStatus("LOCKED")
       |
       +-- IllegalArgumentException từ setter
                    |
                    v
          MethodInvocationException
                    |
                    v
          DefaultBindingErrorProcessor
                    |
                    v
          FieldError("status", "methodInvocation")
```

Điểm cần phân biệt:

- **`typeMismatch`**: không tạo được giá trị đúng kiểu để gán cho thuộc tính.
- **`methodInvocation`**: việc gọi accessor của bean thất bại trong quá trình gắn giá trị, thường là setter.
- **Lỗi validation**: một validator chạy riêng ghi lỗi sau khi xem xét trạng thái đối tượng.

Cần thận trọng khi ném exception từ setter. Một setter có điều kiện phụ thuộc nghiệp vụ phức tạp sẽ khiến binding trở nên khó đoán và thường khó kiểm thử hơn. Trong thiết kế DTO/API, setter nên đơn giản; để các quy tắc nghiệp vụ quan trọng trong service/domain phù hợp. Ví dụ setter ném lỗi ở đây nhằm **minh họa chính xác mã `methodInvocation`**, không phải khuyến nghị đặt toàn bộ nghiệp vụ vào setter.

## 6. Ví dụ chạy được với Java 17 và Spring Framework 6.2

Dự án console dưới đây lần lượt tạo các lỗi `required`, `typeMismatch` và `methodInvocation`. Mỗi kịch bản có **một `DataBinder` mới**, tránh lỗi của lần trước làm nhiễu kết quả. Sau đó, một kịch bản validation riêng làm rõ rằng mã lỗi quy tắc không phải mã lỗi binding.

Cấu trúc:

```text
binding-error-codes/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/binding/BindingErrorCodesDemo.java
```

### 6.1. Cấu hình Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'binding-error-codes'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.binding.BindingErrorCodesDemo'
}
```

`spring-context` kéo theo các dependency liên quan mà `DataBinder` và `Validator` cần trong ví dụ. Khi dùng dự án Spring Boot hiện có, để Spring Boot quản lý các phiên bản module Spring tương thích thay vì khai báo cứng một phiên bản Spring bên ngoài dependency management.

### 6.2. Mã Java đầy đủ

Tệp `src/main/java/demo/binding/BindingErrorCodesDemo.java`:

```java
package demo.binding;

import java.util.Comparator;
import java.util.List;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class BindingErrorCodesDemo {

    public static class AccountForm {
        private String name;
        private Integer age;
        private String status;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            if ("LOCKED".equals(status)) {
                throw new IllegalArgumentException(
                        "Status cannot be set to LOCKED through this form");
            }
            this.status = status;
        }
    }

    // Validator này minh họa lỗi quy tắc, KHÔNG thuộc ba mã binding.
    public static class AccountValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return AccountForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            AccountForm form = (AccountForm) target;
            if (form.getAge() != null && form.getAge() < 18) {
                errors.rejectValue(
                        "age", "age.min", "Age must be at least 18");
            }
        }
    }

    private static MutablePropertyValues values(String... pairs) {
        if (pairs.length % 2 != 0) {
            throw new IllegalArgumentException("Expected key/value pairs");
        }

        MutablePropertyValues input = new MutablePropertyValues();
        for (int i = 0; i < pairs.length; i += 2) {
            input.add(pairs[i], pairs[i + 1]);
        }
        return input;
    }

    // Với DefaultMessageCodesResolver, mã cuối là mã cơ sở.
    private static String baseCode(FieldError error) {
        String[] codes = error.getCodes();
        if (codes == null || codes.length == 0) {
            return "(none)";
        }
        return codes[codes.length - 1];
    }

    private static void printErrors(BindingResult result) {
        List<FieldError> fieldErrors = result.getFieldErrors()
                .stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .toList();

        for (FieldError error : fieldErrors) {
            System.out.println("  " + error.getField()
                    + " -> " + baseCode(error)
                    + ", bindingFailure=" + error.isBindingFailure());
        }
    }

    private static void bindingCase(
            String label, MutablePropertyValues input) {

        AccountForm form = new AccountForm();
        DataBinder binder = new DataBinder(form, "account");

        // Chỉ định name phải có trong dữ liệu dùng để bind.
        binder.setRequiredFields("name");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        System.out.println(label + ": "
                + result.getErrorCount() + " error(s)");
        printErrors(result);
    }

    private static void validationCase() {
        AccountForm form = new AccountForm();
        DataBinder binder = new DataBinder(form, "account");
        binder.setRequiredFields("name");
        binder.setValidator(new AccountValidator());

        binder.bind(values(
                "name", "Lan", "age", "16", "status", "ACTIVE"));

        System.out.println("validation-before: "
                + binder.getBindingResult().getErrorCount()
                + " error(s)");

        binder.validate();

        BindingResult result = binder.getBindingResult();
        System.out.println("validation-after: "
                + result.getErrorCount() + " error(s)");
        printErrors(result);
    }

    public static void main(String[] args) {
        bindingCase("missing-required",
                values("age", "20"));

        bindingCase("type-mismatch",
                values("name", "Lan", "age", "abc"));

        bindingCase("setter-throws",
                values("name", "Lan", "status", "LOCKED"));

        bindingCase("valid",
                values("name", "Lan", "age", "20", "status", "ACTIVE"));

        validationCase();
    }
}
```

Để chạy, từ thư mục gốc dự án dùng Gradle đã cài:

```bash
gradle -q run
```

Nếu có Gradle Wrapper, dùng `./gradlew -q run` trên Unix/macOS hoặc `gradlew.bat -q run` trên Windows. Đầu ra do `main` in ra, với cấu hình mặc định của Spring 6.2:

```text
missing-required: 1 error(s)
  name -> required, bindingFailure=true
type-mismatch: 1 error(s)
  age -> typeMismatch, bindingFailure=true
setter-throws: 1 error(s)
  status -> methodInvocation, bindingFailure=true
valid: 0 error(s)
validation-before: 0 error(s)
validation-after: 1 error(s)
  age -> age.min, bindingFailure=false
```

Lệnh Gradle có thể in thêm thông báo riêng của công cụ nếu bỏ cờ `-q`; bảng trên chỉ thể hiện các dòng từ chương trình Java.

### 6.3. Vì sao các kết quả khác nhau?

**`missing-required`:** `name` đã được khai báo qua `setRequiredFields("name")` nhưng không xuất hiện trong `MutablePropertyValues`. `processMissingFieldError` tạo lỗi `required`. Dù bean `AccountForm` có thể tồn tại với `name == null`, đây là lỗi thiếu trường ở *đầu vào binding*, không phải kết quả từ `AccountValidator`.

**`type-mismatch`:** `name` được gửi hợp lệ. `age="abc"` không chuyển thành `Integer`, tạo lỗi `typeMismatch`. Vì chưa gọi `binder.validate()`, lỗi này phải đến từ binding.

**`setter-throws`:** `name` có mặt, `status` là chuỗi hợp kiểu, nhưng setter ném exception vì `"LOCKED"`. `DefaultBindingErrorProcessor` chuyển lỗi gọi phương thức thành `methodInvocation`. Không cần có `AccountValidator` để nhận mã này.

**`valid`:** các trường có mặt và gắn thành công. Không có validator được gọi; kết quả là không có lỗi binding. Điều này **không tự chứng minh** dữ liệu đã đạt mọi quy tắc nghiệp vụ.

**`validation-before/after`:** dữ liệu `age=16` chuyển được sang `Integer`, nên trước `validate()` chưa có lỗi. `AccountValidator` ghi `age.min` sau đó. `FieldError.isBindingFailure()` trả `false`, đúng với nguồn gốc lỗi.

## 7. Mã cơ sở khác gì danh sách mã FieldError?

Một `FieldError` không nhất thiết chỉ mang đúng chuỗi `"typeMismatch"`. `DefaultBindingErrorProcessor` thường gọi:

```java
bindingResult.resolveMessageCodes(baseErrorCode, fieldName)
```

`DefaultMessageCodesResolver` của Spring tạo **danh sách mã từ cụ thể đến tổng quát** để có thể dùng một thông báo riêng cho từng trường và có fallback.

Ví dụ với object name là `account`, field name là `age`, kiểu `java.lang.Integer` và mã cơ sở `typeMismatch`, danh sách thường có dạng:

```text
typeMismatch.account.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

Với `name` thiếu, mã cơ sở `required` có thể tạo:

```text
required.account.name
required.name
required.java.lang.String
required
```

Với `status` bị lỗi setter, mã cơ sở `methodInvocation` có thể tạo:

```text
methodInvocation.account.status
methodInvocation.status
methodInvocation.java.lang.String
methodInvocation
```

Các danh sách minh họa giả định **`DefaultMessageCodesResolver`, chế độ property binding JavaBean và loại trường đúng như ví dụ**. Cấu hình `MessageCodesResolver` tùy chỉnh, cách xác định field type hoặc đường dẫn index/collection có thể tạo mã khác.

Cần phân biệt những API sau:

- `FieldError.getCodes()`: trả về **toàn bộ các mã** có thể dùng để tra thông báo.
- `FieldError.getCode()`: mã đầu tiên theo `MessageSourceResolvable` (thường là mã cụ thể nhất, ví dụ `typeMismatch.account.age`), **không nhất thiết là mã cơ sở**.
- `BindingResult.resolveMessageCodes("typeMismatch", "age")`: sinh danh sách mã từ mã cơ sở và field.
- `MessageSource.getMessage(fieldError, locale)`: tra theo thứ tự ưu tiên các mã; nếu không có bản dịch phù hợp sẽ thử thông báo dự phòng hoặc xử lý theo cấu hình `MessageSource`.

Trong ví dụ ở mục 6, hàm `baseCode(...)` đọc **phần tử cuối** của `getCodes()` chỉ để in mã cơ sở theo cấu hình resolver mặc định. Nếu bạn thay resolver, không nên dựa vào cách chọn phần tử cuối để phân loại lỗi.

## 8. Ánh xạ required, typeMismatch, methodInvocation thành thông báo

Các mã lỗi kỹ thuật cần được chuyển thành thông báo rõ ràng. Ví dụ một bundle `messages.properties`:

```properties
required.account.name=Vui lòng nhập tên
required=Trường bắt buộc chưa được cung cấp

typeMismatch.account.age=Tuổi phải là một số nguyên
typeMismatch=Giá trị không đúng kiểu dữ liệu

methodInvocation.account.status=Trạng thái đã chọn không thể áp dụng
methodInvocation=Không thể gán giá trị cho trường
```

Ở ứng dụng Spring quản lý bean `MessageSource`, có thể khai báo (ví dụ cấu hình Java Spring Framework):

```java
@Configuration
public class MessagesConfiguration {
    @Bean
    public MessageSource messageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");
        return source;
    }
}
```

Đây là một **tệp cấu hình trích đoạn**, cần imports `org.springframework.context.annotation.*`, `org.springframework.context.MessageSource`, `org.springframework.context.support.ResourceBundleMessageSource` và đặt `messages.properties` trên classpath. Nó không phải chương trình độc lập có `main`. Trong Spring Boot, có thể dùng `messages.properties` và bean `messageSource` được cấu hình sẵn khi phù hợp; đừng khai báo bean trùng tên không cần thiết.

Giả sử ta có `BindingResult result` và `MessageSource source`:

```java
for (FieldError error : result.getFieldErrors()) {
    String userMessage =
            source.getMessage(error, Locale.forLanguageTag("vi"));
    System.out.println(error.getField() + ": " + userMessage);
}
```

Đoạn tích hợp trên cần imports `FieldError` và `Locale`. `FieldError` chứa danh sách mã theo thứ tự ưu tiên: mã cụ thể `typeMismatch.account.age` được tìm trước mã chung `typeMismatch`. Với hệ thống công khai, trả thêm mã lỗi API ổn định để frontend phân loại; thông báo dịch theo locale không nên trở thành khóa logic phía client.

### 8.1. Mã và thông báo mặc định có phải giống nhau?

Không. **Error code** là giá trị có tính máy đọc được, chẳng hạn `required`. **Message code** là một hoặc nhiều biến thể được `MessageCodesResolver` mở rộng. **User message** là nội dung được `MessageSource` tìm ra, chẳng hạn “Vui lòng nhập tên”. Còn **default message** trong `FieldError` là thông báo dự phòng hoặc nội dung mặc định gắn với lỗi; nó không nhất thiết giống thông báo đã dịch.

Khi tạo API chuẩn, nên tách chúng trong thiết kế nội bộ và không làm lộ thông tin nhạy cảm từ exception hoặc giá trị bị từ chối.

## 9. Tùy biến BindingErrorProcessor: khi nào và bằng cách nào?

`DataBinder` cho phép thay thế chiến lược mặc định:

```java
binder.setBindingErrorProcessor(customProcessor);
```

Điều này hữu ích khi muốn thay đổi mã lỗi, thông báo dự phòng hoặc cách biểu diễn lỗi binding. Tuy nhiên, phần lớn ứng dụng chỉ cần cấu hình `MessageSource`, `MessageCodesResolver` hoặc một lớp chuyển lỗi API mà **không cần** thay bộ xử lý binding.

Một tùy biến tối thiểu là chỉ đổi mã lỗi dành cho trường bắt buộc và giữ nguyên xử lý type mismatch/method invocation bằng cách kế thừa `DefaultBindingErrorProcessor`:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.DefaultBindingErrorProcessor;
import org.springframework.validation.FieldError;

public final class FriendlyBindingErrorProcessor
        extends DefaultBindingErrorProcessor {

    @Override
    public void processMissingFieldError(
            String missingField, BindingResult result) {

        String[] codes =
                result.resolveMessageCodes("input.required", missingField);

        FieldError error = new FieldError(
                result.getObjectName(),
                missingField,
                null,
                true,
                codes,
                null,
                "Missing required input");

        result.addError(error);
    }
}
```

Đây là **một lớp Java độc lập về cấu trúc**, cần được đặt vào source set của dự án có Spring dependency. Nó không có `main`. Khi đăng ký instance bằng `setBindingErrorProcessor(new FriendlyBindingErrorProcessor())`, trường thiếu sẽ dùng mã cơ sở `input.required` thay cho `required`, còn các lỗi property access vẫn được xử lý bằng cách triển khai mặc định được kế thừa.

Trong constructor `FieldError` ở trên:

- `result.getObjectName()` giữ tên đối tượng của binder.
- `missingField` giữ đường dẫn trường.
- `null` là rejected value minh họa cho trường không được cung cấp.
- `true` đánh dấu **binding failure**; đừng dùng `result.rejectValue(...)` một cách tùy tiện rồi làm mất phân loại này khi định nghĩa bộ xử lý binding tùy chỉnh.
- `codes` là danh sách mã được mở rộng theo `MessageCodesResolver`.
- `null` là message arguments của ví dụ; nếu muốn formatter/message source có tên trường dưới dạng argument, cần bổ sung đúng dữ liệu.
- Chuỗi cuối là thông báo dự phòng.

Khi kế thừa và chỉ thay một phương thức, hãy kiểm thử cả ba nhóm lỗi: đổi cách xử lý `required` không được làm biến mất hoặc thay đổi sai `typeMismatch`, `methodInvocation`.

### 9.1. Không lẫn setBindingErrorProcessor và setMessageCodesResolver

| Điểm cấu hình | Thay đổi điều gì? | Ví dụ |
| --- | --- | --- |
| `setBindingErrorProcessor(...)` | Cách chuyển sự kiện lỗi binding thành `FieldError`, mã cơ sở và dữ liệu lỗi | Đổi `required` thành `input.required` |
| `setMessageCodesResolver(...)` | Cách tạo các biến thể mã cụ thể từ mã cơ sở + object/field/type | Đổi thứ tự/mẫu `typeMismatch.account.age` |
| `MessageSource` | Nội dung văn bản/locale tương ứng với mã | `typeMismatch.account.age=Tuổi phải là số` |
| `setValidator(...)` / `addValidators(...)` | Quy tắc kiểm tra giá trị/đối tượng sau binding | `age.min` cho tuổi dưới 18 |
| `setRequiredFields(...)` | Những trường phải có trong đầu vào property binding | Yêu cầu khóa `name` xuất hiện |

Chỉ dùng cách can thiệp thấp nhất đáp ứng mục tiêu. Nếu mong muốn chỉ là thông báo thân thiện, trước tiên sử dụng `MessageSource`; không cần viết một `BindingErrorProcessor` chỉ để đổi chuỗi hiển thị.

## 10. Các giới hạn và tình huống biên

### 10.1. Required fields chỉ áp dụng cho đúng cơ chế binding

`setRequiredFields(...)` được thiết kế cho `DataBinder.bind(PropertyValues)`. Constructor binding bằng `construct(...)` là đường xử lý khác, chọn các giá trị cần thiết để xây đối tượng. Không áp dụng một cách máy móc cơ chế thiếu trường của property binding cho constructor binding.

Cũng cần phân biệt `required` từ `DefaultBindingErrorProcessor` với lỗi `@NotNull`/`@NotBlank` của Jakarta Bean Validation: một request có thể có nhiều cơ chế kiểm tra, nhưng mã cơ sở và thời điểm ghi lỗi không giống nhau.

### 10.2. Setter ném exception không phải là chiến lược validation lý tưởng

Một số setter nhận dữ liệu và ném `IllegalArgumentException` để bảo vệ bất biến. Điều đó có thể sinh `methodInvocation` trong property binding, nhưng việc lạm dụng khiến client nhận lỗi khó hiểu và khó tái sử dụng bean. DTO đầu vào nên chỉ chứa và tiếp nhận dữ liệu; quy tắc validation rõ ràng nên nằm ở Spring/Jakarta Validator hoặc service/domain tùy bản chất.

Không phải mọi lỗi setter đều được biến thành `methodInvocation`: nếu exception xảy ra ngoài quá trình property binding, hoặc chưa đến được bước gọi setter do đường dẫn không hợp lệ, phải xử lý theo cơ chế thực tế.

### 10.3. Unknown/invalid path khác ba mã chính

Khi input có tên thuộc tính không tồn tại, `DataBinder` có thể bỏ qua nó theo cấu hình mặc định, hoặc ném `NotWritablePropertyException` nếu yêu cầu strict. Khi một đường dẫn lồng nhau không đi qua được nhánh null, có thể xảy ra `NullValueInNestedPathException`. Chúng **không mặc nhiên** biến thành `typeMismatch` hay `methodInvocation`.

Vì vậy, không thiết kế hệ thống lỗi API theo giả định rằng `DefaultBindingErrorProcessor` tự động xử lý mọi ngoại lệ phát sinh khi nhận dữ liệu ngoài.

### 10.4. Phân biệt lỗi của binding với lỗi của validation

Nếu gọi:

```java
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();

binder.validate();
```

các lỗi trước và sau validation cùng nằm trong `BindingResult`. Một `FieldError` có `isBindingFailure() == true` thường đến từ binding; lỗi được tạo qua `Errors.rejectValue(...)` của một validator thường có `isBindingFailure() == false`. Nếu hệ thống dùng `BindingErrorProcessor` tùy chỉnh, kiểm thử cờ này thay vì giả định.

Lưu ý `BindingResult` không phải công cụ lưu trạng thái dùng chung giữa các request. Tạo binder/đối tượng kết quả mới theo mỗi lần binding và tránh gọi validator nhiều lần lên cùng kết quả khiến lỗi tích lũy trùng.

### 10.5. Cơ chế @RequestBody JSON không giống property binding

Trong Spring MVC, `@ModelAttribute` thường đi qua `WebDataBinder` để gắn query/form parameters. Còn `@RequestBody` được xử lý bằng `HttpMessageConverter` như Jackson để giải mã JSON thành object. Các lỗi JSON sai kiểu có thể phát sinh trong message conversion trước validation và **không nhất thiết** tạo ra `FieldError` mã `typeMismatch` của `DefaultBindingErrorProcessor`.

Không lấy ví dụ `DataBinder.bind(MutablePropertyValues)` làm bằng chứng rằng mọi lỗi JSON đều chạy qua `DefaultBindingErrorProcessor`. Hãy kiểm thử đúng kiểu endpoint.

## 11. Kết hợp với Spring MVC và BindingResult

Với biểu mẫu Spring MVC, một controller có thể dùng `BindingResult` ngay sau đối số `@ModelAttribute` để trả thông báo lỗi:

```java
@PostMapping("/accounts")
public String submit(
        @ModelAttribute("account") AccountForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "account-form";
    }

    return "account-success";
}
```

Đây là **đoạn trích từ controller** có imports MVC tương ứng, không phải chương trình console độc lập. Với property binding, lỗi `required`, `typeMismatch` hay `methodInvocation` (nếu được tạo trong binding) có thể xuất hiện trong `result`. Việc controller có chạy thêm Bean Validation hay Spring Validator phụ thuộc `@Valid`/`@Validated`, `@InitBinder` và cấu hình MVC.

Nếu ứng dụng muốn yêu cầu `name` ngay ở bước bind, có thể cấu hình binder tại controller:

```java
@InitBinder("account")
void configure(WebDataBinder binder) {
    binder.setRequiredFields("name");
    binder.setAllowedFields("name", "age", "status");
}
```

Đoạn này cũng chỉ là **một phương thức trong controller**, không có `main`. `setAllowedFields` giúp giới hạn những trường client có thể ghi; không nên bind trực tiếp toàn bộ entity có thuộc tính nhạy cảm như `role`, `approved` hoặc `accountId`.

Khi muốn trả JSON lỗi ổn định, hãy lấy đường dẫn trường, danh sách mã lỗi và thông báo đã giải quyết từ `BindingResult`. Đừng trả nguyên `FieldError#getRejectedValue()` hoặc thông điệp exception nội bộ khi dữ liệu có thể nhạy cảm.

## 12. Kiểm thử đầy đủ ba mã binding

Một bộ test tốt nên kiểm tra cả **mã gốc**, **cờ binding failure**, **giá trị bean sau bind** và **đúng thời điểm lỗi xuất hiện**.

| Test | Đầu vào / cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| Missing required | `setRequiredFields("name")`, không gửi `name` | `FieldError` ở `name`, mã cơ sở `required` |
| Required present | Gửi `name=Lan` | Không có lỗi `required` |
| Type mismatch | `age=abc` với `Integer age` | `FieldError` ở `age`, mã `typeMismatch` |
| Numeric age | `age=20` | Bind thành công, không lỗi kiểu |
| Setter failure | `status=LOCKED` và setter ném exception | `FieldError` ở `status`, mã `methodInvocation` |
| Setter success | `status=ACTIVE` | Không có lỗi gọi setter |
| Validation failure | `age=16` và gọi `validate()` với rule `age >= 18` | `FieldError` mã `age.min`, `isBindingFailure=false` |
| Message resolution | Có bundle cho `typeMismatch.account.age` | Lấy được thông báo trường cụ thể |
| Custom processor | `FriendlyBindingErrorProcessor` được đăng ký | Missing field dùng `input.required`; hai loại property access vẫn hoạt động |
| API form | Spring MVC `@ModelAttribute` + `BindingResult` | Giao diện/API trả lỗi có cấu trúc và không lộ thông tin nội bộ |

### 12.1. Kiểm thử bằng mã

Nếu muốn xác nhận mã cơ sở từ `FieldError` trong môi trường dùng resolver mặc định:

```java
FieldError error = result.getFieldError("age");
if (error == null) {
    throw new AssertionError("Expected an age error");
}

String[] codes = error.getCodes();
boolean typeMismatch = codes != null
        && java.util.Arrays.asList(codes).contains("typeMismatch");

if (!typeMismatch || !error.isBindingFailure()) {
    throw new AssertionError("Expected typeMismatch binding error");
}
```

Đoạn kiểm tra này giả định biến `result` đã có từ quá trình bind `age=abc`. Nó không phải tệp độc lập. Kiểm tra bằng mã thay vì so sánh toàn bộ chuỗi thông báo mặc định giúp test ít phụ thuộc locale và phiên bản.

### 12.2. Có nên unit test DefaultBindingErrorProcessor trực tiếp?

Có, khi bạn tự viết bộ xử lý lỗi hoặc muốn bảo đảm mã tùy chỉnh. Có thể tạo `BindingResult` và gọi `processMissingFieldError(...)` để kiểm tra `FieldError`, hoặc tạo exception thích hợp cho `processPropertyAccessException(...)`. Nhưng để xác minh **tích hợp thực tế**, dễ hiểu nhất vẫn là đưa dữ liệu qua `DataBinder.bind(...)` như ví dụ: như vậy bạn kiểm tra cả nguồn gốc lỗi và đường xử lý mặc định.

Với Spring MVC, cần test riêng bằng `MockMvc` hoặc một client HTTP tương đương, vì các loại input khác nhau (`@ModelAttribute`/`@RequestBody`) có thể đi qua các cơ chế tạo đối tượng khác nhau.

## 13. Sai lầm thường gặp

1. **Cho rằng `required` là lỗi `@NotNull`:** mã `required` ở đây sinh bởi chính sách required field của binder. `@NotNull` là Bean Validation và được kích hoạt theo cơ chế validation riêng.
2. **Cho rằng mọi giá trị không hợp lệ đều `typeMismatch`:** chuỗi `"16"` chuyển thành `Integer 16` thành công; nếu sai ngưỡng tuổi, đó là validation failure.
3. **Hiểu `methodInvocation` là “gọi controller method thất bại”:** mã này nói về accessor của thuộc tính trong quá trình bean property binding, thường là setter.
4. **Đọc `FieldError.getCode()` rồi khẳng định luôn bằng `typeMismatch`:** với resolver mặc định, mã đầu có thể là `typeMismatch.account.age`; xem cả `getCodes()`.
5. **Tự bắt mọi `PropertyAccessException` và trả HTTP 500:** những exception được binder thu thập phù hợp có thể trở thành `FieldError` của dữ liệu đầu vào; exception khác cần phân loại riêng.
6. **Bật `setIgnoreUnknownFields(false)` và kỳ vọng mọi lỗi tên trường thành `typeMismatch`:** unknown property có đường xử lý khác.
7. **Chỉ cấu hình `MessageSource` và tưởng thay đổi lúc nào FieldError được tạo:** message source đổi nội dung hiển thị, không thay cơ chế phát hiện lỗi.
8. **Tự viết BindingErrorProcessor chỉ để đổi câu chữ:** thường có thể giải quyết bằng bundle và quy tắc tra mã mà không cần thay chiến lược.
9. **Dùng `rejectValue(...)` khi tùy biến lỗi binding rồi quên cờ nguồn gốc:** lỗi tự tạo thường không đánh dấu `bindingFailure=true`; nếu cần chính xác, tạo `FieldError` thích hợp.
10. **Khai báo `setRequiredFields` nhưng không xét các chính sách gắn dữ liệu:** required fields, allowed fields, formatter và conversion có thể tương tác; kiểm thử các đầu vào quan trọng.
11. **Trả nguyên exception message khi setter ném lỗi:** thông điệp có thể chứa dữ liệu nội bộ hoặc rò rỉ thông tin. Ánh xạ sang thông báo phù hợp cho client.
12. **Áp dụng kết luận của property binding lên JSON deserialization:** `@RequestBody` thường có cơ chế chuyển đổi khác, không bắt buộc đi qua `DefaultBindingErrorProcessor`.

## 14. Bài tập tự luyện

**Bài 1.** Với `setRequiredFields("name")`, hãy gửi chỉ `age=20`. Xác định giá trị của `FieldError.getField()`, mã cơ sở và `isBindingFailure()`. Sau đó thêm `name=Lan` và xem lỗi còn không.

**Bài 2.** Lần lượt bind `age=abc` và `age=16` vào bean có `Integer age`. Giải thích vì sao kịch bản đầu có `typeMismatch`, còn kịch bản sau chỉ có lỗi quy tắc khi đã đăng ký và gọi validator.

**Bài 3.** Đổi setter `setStatus` để ném `IllegalArgumentException` khi nhận `"LOCKED"`. Giải thích tại sao mã `methodInvocation` xuất hiện ngay trong binding dù `status` đã đúng kiểu `String`.

**Bài 4.** Tạo `messages.properties` chứa `typeMismatch.account.age` và `typeMismatch`. Với lỗi `age=abc`, giải thích thứ tự tìm thông báo và cách fallback nếu thiếu khóa cụ thể.

**Bài 5.** Đăng ký `FriendlyBindingErrorProcessor` rồi kiểm tra `input.required` và bảo đảm `typeMismatch`/`methodInvocation` vẫn tồn tại. Nhận xét vì sao phải bảo toàn `bindingFailure=true` cho lỗi binding.

**Bài 6.** Thiết kế endpoint `@ModelAttribute` trả HTTP 400 với mã lỗi ổn định khi có lỗi đầu vào, không để lộ rejected value nhạy cảm. Phân biệt test cho form/query với test cho JSON `@RequestBody`.

**Tóm lược:** `DefaultBindingErrorProcessor` chuyển **thiếu trường bắt buộc** thành `required` và **ngoại lệ truy cập thuộc tính trong binding** thành mã tương ứng từ `PropertyAccessException`: `typeMismatch` hoặc `methodInvocation`. `BindingResult` lưu kết quả; `MessageCodesResolver` tạo mã ưu tiên; `MessageSource` biến chúng thành thông báo; `Validator` thực hiện quy tắc riêng sau đó khi được gọi.

## Tham khảo chính thức

- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — DefaultBindingErrorProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html)
- [Spring Framework — BindingErrorProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/BindingErrorProcessor.html)
- [Spring Framework — DefaultMessageCodesResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework — MethodInvocationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/MethodInvocationException.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
