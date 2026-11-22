# Phân biệt bind với validate: hai thao tác riêng biệt trong Spring DataBinder

Một biểu mẫu có thể được **gắn dữ liệu thành công** vào đối tượng Java nhưng vẫn chứa dữ liệu không hợp lệ theo quy tắc ứng dụng. Ngược lại, một trường không chuyển được từ chuỗi sang số sẽ sinh lỗi ngay trong quá trình gắn dữ liệu, trước khi các quy tắc như “tuổi phải từ 18 trở lên” được áp dụng.

Trong Spring Framework, **binding (`bind`)** và **validation (`validate`)** là hai hoạt động có trách nhiệm riêng:

- **Bind**: đọc các giá trị đầu vào, chọn thuộc tính đích, chuyển kiểu khi cần và cố gắng gán giá trị vào đối tượng.
- **Validate**: xem xét đối tượng và đánh giá các quy tắc hợp lệ, ghi nhận những vi phạm.

`org.springframework.validation.DataBinder` cho phép gọi hai thao tác này **riêng rẽ**: `binder.bind(propertyValues)` rồi `binder.validate()`. Cả lỗi binding và lỗi validation đều được tập hợp trong **`BindingResult`** của binder.

## 1. Bức tranh tổng thể

```text
Dữ liệu thô (form/query parameters hoặc PropertyValues)
          |
          v
   binder.bind(values)
          |
          +-- Lựa chọn trường được phép gắn
          +-- Chuyển kiểu: "20" -> Integer(20)
          +-- Gọi setter/cập nhật đối tượng đích
          +-- Ghi lỗi binding nếu chuyển kiểu/gắn giá trị thất bại
          |
          v
Đối tượng Java đã gắn được các giá trị có thể chuyển đổi
          |
          v
     binder.validate()
          |
          +-- Gọi Spring Validator đã đăng ký
          +-- Kiểm tra quy tắc trên các giá trị Java hiện có
          +-- Ghi lỗi validation nếu quy tắc bị vi phạm
          |
          v
   binder.getBindingResult()
          |
          +-- Các FieldError từ binding
          +-- Các FieldError/ObjectError từ validation
          |
          v
Ứng dụng xử lý kết quả, trả lỗi hoặc tiếp tục nghiệp vụ
```

Điểm cốt lõi là **`bind()` không mặc định gọi `validate()`**, và **`validate()` không tự đọc hay gắn lại dữ liệu thô**. Khi sử dụng `DataBinder` trực tiếp trong mã Java, người lập trình quyết định khi nào gọi từng thao tác. Spring MVC có thể điều phối cả hai bước tự động theo kiểu đối số và annotation, nhưng hai trách nhiệm vẫn khác nhau.

### Ví dụ rất ngắn

Giả sử lớp `RegistrationForm` có hai thuộc tính: `name: String` và `age: Integer`.

| Đầu vào | Sau `bind` | Sau `validate` |
| --- | --- | --- |
| `name=Lan`, `age=20` | `name="Lan"`, `age=20`; không lỗi chuyển kiểu | Không lỗi nếu tên bắt buộc và tuổi tối thiểu 18 |
| `name="  "`, `age=17` | Cả hai giá trị đều gắn được; chưa có lỗi ràng buộc | Lỗi tên trống và tuổi dưới 18 |
| `name=Lan`, `age=abc` | Chuyển `abc` thành `Integer` thất bại; lỗi binding ở `age` | Lỗi binding vẫn còn; validator có thể kiểm tra các trường đã gắn được |
| `name=Lan`, thiếu `age` | `age` có thể còn `null` nếu chưa có thiết lập “required fields” | Validator phải khai báo quy tắc bắt buộc nếu ứng dụng yêu cầu tuổi |

Trong bảng trên, quy tắc “tên bắt buộc” và “tuổi từ 18 trở lên” là quy tắc kiểm tra minh họa. Chúng không tự xuất hiện chỉ nhờ khai báo các thuộc tính Java.

## 2. Chính xác thì bind làm gì?

### 2.1. Nguồn dữ liệu và đối tượng đích

`DataBinder` nhận một **đối tượng đích** và các cặp tên–giá trị dưới dạng `PropertyValues`. `MutablePropertyValues` là một cách phổ biến để tạo đầu vào khi lập trình hoặc kiểm thử:

```java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registration");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Lan");
values.add("age", "20");

binder.bind(values);
```

Đây là **đoạn trích**, các lớp `RegistrationForm`, imports và dự án hoàn chỉnh được trình bày ở ví dụ bên dưới. Khi property binding, Spring tìm các thuộc tính JavaBean tương ứng, chuyển chuỗi `"20"` thành `Integer` rồi gán vào `age` qua setter.

`DataBinder` hỗ trợ đường dẫn thuộc tính lồng nhau, ví dụ `address.city`, cùng các thiết lập về trường được phép gắn, trường bắt buộc và chuyển đổi kiểu. Trong Spring Framework 6.x, ngoài property binding còn có cơ chế constructor binding bằng `construct(...)`. Bài này dùng **property binding qua `bind(...)`** để nhìn rõ hai thao tác.

### 2.2. Chuyển kiểu là một phần của binding

Trên HTTP, giá trị `age=20` thường xuất hiện dưới dạng chuỗi. Với thuộc tính `Integer`, cơ chế chuyển đổi của Spring cố gắng tạo giá trị số. Với `age=abc`, chuyển đổi không thực hiện được. `DataBinder` thường ghi một `FieldError` với mã cơ sở `typeMismatch` vào `BindingResult` thay vì coi `abc` là một tuổi hợp lệ.

Tùy ngữ cảnh, việc chuyển đổi có thể dùng `PropertyEditor`, `ConversionService` hoặc `Formatter` đã được cấu hình. `DataBinder` tự tạo trong chương trình console không đương nhiên có cùng bộ formatter như `WebDataBinder` trong một ứng dụng Spring MVC đã cấu hình.

Cần phân biệt hai câu:

- “`abc` có chuyển thành `Integer` không?” là **câu hỏi về binding/chuyển kiểu**.
- “`17` có đạt quy tắc tuổi tối thiểu 18 không?” là **câu hỏi về validation**.

### 2.3. BindingResult đã có ích trước khi validate

Ngay sau `bind(...)`, có thể gọi:

```java
BindingResult result = binder.getBindingResult();
boolean hadBindingProblem = result.hasErrors();
```

`BindingResult` có thể chứa lỗi chuyển kiểu hoặc lỗi trường bắt buộc do binder được cấu hình. Vì vậy `hasErrors()` **không đồng nghĩa** với “đã chạy Bean Validation”. Để biết lỗi trường có xuất phát từ quá trình binding không, `FieldError` cung cấp `isBindingFailure()`.

Nếu cần chỉ định tên các trường được phép nhận từ bên ngoài, dùng `binder.setAllowedFields("name", "age")` hoặc dùng constructor binding/DTO đầu vào phù hợp. Việc gắn dữ liệu từ nguồn không đáng tin cậy thẳng vào entity có thuộc tính nhạy cảm như `role`, `status` hay `id` có thể dẫn tới việc gắn quá nhiều trường ngoài ý muốn.

## 3. Chính xác thì validate làm gì?

### 3.1. Validator kiểm tra đối tượng Java đã có

Với giao diện Spring `org.springframework.validation.Validator`:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

Đây là **chữ ký rút gọn để giải thích**. `supports` cho biết kiểu nào được kiểm tra; `validate` đánh giá điều kiện và ghi lỗi vào `Errors`. Các cách ghi lỗi phổ biến gồm:

- `errors.rejectValue("age", "age.min", "Age must be at least 18")`: vi phạm tại một trường, tạo `FieldError`.
- `errors.reject("registration.invalid", "Registration is invalid")`: vi phạm cấp đối tượng, tạo lỗi toàn cục.
- `ValidationUtils.rejectIfEmptyOrWhitespace(errors, "name", ...)`: tiện ích kiểm tra giá trị rỗng hoặc chỉ gồm khoảng trắng.

Nếu dùng `DataBinder` trực tiếp, bạn phải đăng ký validator bằng `binder.setValidator(...)`, `binder.addValidators(...)` hoặc cơ chế cấu hình thích hợp, **sau đó** gọi `binder.validate()`. Khi chưa gọi `validate()`, các ràng buộc của validator tùy chỉnh chưa tự chạy.

### 3.2. Validate không tự sửa hoặc chuyển đổi giá trị

`validate()` không tự làm cho `age=abc` trở thành số hợp lệ, không tự thay `name="  "` bằng tên đúng, và không đọc lại `MutablePropertyValues`. Validator bình thường ghi lỗi; nó không chịu trách nhiệm chuẩn hóa hay sửa dữ liệu.

Nếu binding thất bại tại một trường, trường đó có thể giữ giá trị cũ hoặc `null` tùy trạng thái trước đó và cách binder được thiết lập. Validator không nên giả định tất cả thuộc tính chắc chắn đã được gắn thành công; hãy kiểm tra `null` phù hợp và phân biệt lỗi binding với lỗi quy tắc để tránh báo lỗi gây hiểu nhầm.

### 3.3. Spring Validator và Jakarta Bean Validation liên hệ thế nào?

`DataBinder` hỗ trợ Spring `Validator`. Một Bean Validation provider như Hibernate Validator có thể được kết nối thông qua `LocalValidatorFactoryBean`, lớp đóng vai trò adapter giữa `jakarta.validation.Validator` và Spring `Validator`. Khi đó các annotation `@NotBlank`, `@Min`, `@Email` cùng `@Valid`/`@Validated` có thể tham gia bước **validation**.

Điều quan trọng là **annotation ràng buộc không thay đổi trách nhiệm của `bind()`**. `@Min(18)` kiểm tra giá trị sau khi chuyển được thành số, không biến chuỗi `abc` thành số. Trong Spring 6 và Boot 3, các annotation thuộc namespace `jakarta.validation.*`.

## 4. Ví dụ thực hành hoàn chỉnh: quan sát hai thời điểm

Ví dụ Java 17 dưới đây minh họa ba trường hợp trên **Spring Framework 6.2**, chạy từ dòng lệnh, không cần Spring Boot, máy chủ web hay Jakarta Bean Validation provider. Nó dùng Spring `Validator` viết tay để tách riêng trách nhiệm.

Cấu trúc dự án:

```text
bind-vs-validate/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/binder/BindVsValidateDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'bind-vs-validate'
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
    mainClass = 'demo.binder.BindVsValidateDemo'
}
```

Dependency `spring-context` kéo theo các module Spring cần thiết cho `DataBinder`, `Validator` và `MutablePropertyValues`. Khi tích hợp vào dự án Spring Boot hiện có, nên dùng hệ thống quản lý phiên bản Spring của Boot thay vì gắn phiên bản thư viện thủ công như dự án console này.

Tệp `src/main/java/demo/binder/BindVsValidateDemo.java`:

```java
package demo.binder;

import java.util.Comparator;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class BindVsValidateDemo {

    // Đối tượng đích có getter/setter theo quy ước JavaBean.
    public static class RegistrationForm {
        private String name;
        private Integer age;

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
    }

    // Chỉ kiểm tra quy tắc hợp lệ trên các giá trị Java.
    public static class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required",
                    "Name is required");

            Integer age = form.getAge();
            if (age != null && age < 18) {
                errors.rejectValue("age", "age.min",
                        "Age must be at least 18");
            }
        }
    }

    private static void show(String scenario, String name, String age) {
        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registration");

        // Chỉ hai trường này được gắn từ dữ liệu đầu vào.
        binder.setAllowedFields("name", "age");
        binder.setValidator(new RegistrationValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", name);
        input.add("age", age);

        // BƯỚC 1: binding + conversion, CHƯA gọi Validator.
        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println(scenario);
        System.out.println("  bind: age=" + form.getAge()
                + ", errors=" + result.getErrorCount());

        // BƯỚC 2: chạy Validator trên đối tượng đã được gắn.
        binder.validate();

        System.out.println("  validate: errors="
                + result.getErrorCount());

        // Phân loại lỗi bằng isBindingFailure(), không đoán từ message.
        result.getFieldErrors().stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .forEach(error -> System.out.println(
                        "    " + error.getField() + " ("
                        + (error.isBindingFailure()
                                ? "binding" : "validation")
                        + ")"));
    }

    public static void main(String[] args) {
        show("valid", "Lan", "20");
        show("rule-invalid", "  ", "17");
        show("conversion-invalid", "Lan", "abc");
    }
}
```

Chạy từ thư mục dự án bằng Gradle đã cài đặt:

```bash
gradle -q run
```

Nếu dự án có Gradle Wrapper, lệnh tương đương là `./gradlew -q run` (Unix/macOS) hoặc `gradlew.bat -q run` (Windows). Phần **stdout của `main`** dự kiến:

```text
valid
  bind: age=20, errors=0
  validate: errors=0
rule-invalid
  bind: age=17, errors=0
  validate: errors=2
    age (validation)
    name (validation)
conversion-invalid
  bind: age=null, errors=1
  validate: errors=1
    age (binding)
```

Giải thích từng trường hợp:

1. **`valid`**: chuỗi `"20"` chuyển được thành `Integer 20`, tên có nội dung. `bind()` và `validate()` đều không sinh lỗi.
2. **`rule-invalid`**: `"17"` hoàn toàn chuyển được thành `Integer 17`, `name` vẫn nhận chuỗi hai khoảng trắng. Sau `bind()` chưa có lỗi. Chỉ khi gọi `validate()`, quy tắc tuổi và tên mới ghi **hai lỗi validation**. Đây là bằng chứng trực tiếp rằng binding thành công không bảo đảm dữ liệu hợp lệ.
3. **`conversion-invalid`**: chuỗi `"abc"` không chuyển được thành `Integer`. `bind()` ghi ngay **một lỗi binding**, thuộc tính `age` của đối tượng mới vẫn `null`. Validator trong ví dụ chỉ kiểm tra ngưỡng tuổi nếu `age != null`, nên không tạo thêm lỗi tuổi giả tạo; sau `validate()` bộ kết quả vẫn có một lỗi binding.

**Quyết định thiết kế của ví dụ:** validator chưa áp dụng quy tắc “tuổi bắt buộc” với `null` để làm nổi bật sự khác biệt giữa lỗi chuyển kiểu và lỗi ngưỡng tuổi. Trong ứng dụng thật, nếu `age` bắt buộc thì cần thêm quy tắc `null`, song phải xem xét cách hiển thị kết quả khi cùng một trường đã có lỗi chuyển kiểu. Không nên hiểu rằng `null` mặc nhiên là tuổi hợp lệ.

## 5. Một BindingResult, hai nguồn lỗi

`BindingResult` mở rộng `Errors` và giữ kết quả kiểm tra gắn với một đối tượng đích. Khi cùng một binder chạy `bind(...)` và `validate()`, các lỗi được cộng dồn vào cùng bộ kết quả:

```java
binder.bind(input);
BindingResult result = binder.getBindingResult();
int errorsAfterBind = result.getErrorCount();

binder.validate();
int errorsAfterValidate = result.getErrorCount();
```

| Thông tin | Cách lấy | Cách hiểu |
| --- | --- | --- |
| Có bất kỳ lỗi nào | `result.hasErrors()` | Bao gồm lỗi binding và validation đã được ghi |
| Số lỗi tổng cộng | `result.getErrorCount()` | Bao gồm `FieldError` và lỗi toàn cục |
| Danh sách lỗi trường | `result.getFieldErrors()` | Có đường dẫn trường, mã lỗi, thông báo |
| Lỗi tại một trường | `result.getFieldError("age")` | Có thể là lỗi conversion hoặc constraint |
| Lỗi cấp đối tượng | `result.getGlobalErrors()` | Dùng cho quy tắc liên quan toàn đối tượng |
| Phân biệt nguyên nhân | `fieldError.isBindingFailure()` | `true` thường là lỗi binding; `false` là lỗi do `rejectValue`/validator |

Ví dụ, `FieldError` do lỗi kiểu thường có nhóm mã lỗi dựa trên `typeMismatch` (có thể được mở rộng theo object name, field name và kiểu Java). Lỗi thủ công `rejectValue("age", "age.min", ...)` có mã xuất phát từ `age.min`. Khi cần hiển thị cho người dùng, có thể giải quyết các mã đó thông qua `MessageSource`; không nên hiển thị trực tiếp stack trace hoặc ép phía client phân tích thông báo tiếng Anh mặc định.

Kết quả `BindingResult` có thể chứa giá trị bị từ chối. Ví dụ với `age=abc`, thông tin lỗi có thể giữ chuỗi người dùng đã nhập để hiển thị lại form. Không đưa `rejectedValue` vào log hoặc phản hồi tùy tiện khi đó có thể là mật khẩu, token hay dữ liệu nhạy cảm.

**Lưu ý:** gọi lại `binder.validate()` nhiều lần không đồng nghĩa với “kiểm tra mới hoàn toàn”. Validator có thể thêm lại lỗi vào cùng `BindingResult`, tạo kết quả trùng lặp. Mỗi lần xử lý request nên có một quy trình rõ ràng và bộ kết quả riêng.

## 6. Những cấu hình binder dễ nhầm với validate

`DataBinder` có thể kiểm tra một số điều kiện **ngay trong binding**. Điều đó không biến hai thao tác thành một.

### 6.1. Trường bắt buộc ở mức binder

Có thể cấu hình:

```java
binder.setRequiredFields("name", "age");
```

Khi gắn dữ liệu, binder kiểm tra các trường được yêu cầu và có thể ghi lỗi mã cơ sở `required` nếu trường không được cung cấp hoặc không có giá trị cần thiết theo chính sách của binder. Đây là **kiểm tra sự có mặt của trường khi bind**, không phải kiểm tra các quy tắc miền như độ tuổi tối thiểu, độ dài tên hay tính hợp lệ của email.

Đừng nhầm `setRequiredFields` với Jakarta `@NotNull` hoặc Spring `ValidationUtils.rejectIfEmptyOrWhitespace`. Chúng được thực thi ở những nơi khác nhau và có thể khác nhau về xử lý chuỗi trống/khoảng trắng. Thiết kế hợp đồng rõ ràng, tránh tạo nhiều thông báo lỗi trùng lặp cho một điều kiện.

### 6.2. Trường được phép và trường bị loại

`setAllowedFields(...)` hạn chế những tên trường được phép gắn. Dữ liệu không được gắn có thể được ghi nhận qua `result.getSuppressedFields()`. Đây là **quyết định về phạm vi binding và bảo vệ đối tượng**, không phải quy tắc “giá trị hợp lệ”.

Trong API công khai, nên dùng DTO đầu vào với những trường client được phép gửi, chỉ định các trường được bind khi cần và để service quyết định cách ánh xạ sang mô hình nghiệp vụ. Không cho client tự ghi `role`, `accountStatus` hoặc khóa định danh chỉ vì entity có setter.

### 6.3. Converter, formatter và validator

- `Converter<String, Integer>` hoặc cơ chế chuyển kiểu chuẩn trả lời câu hỏi dữ liệu có chuyển được sang kiểu cần dùng không.
- `Formatter` giúp đọc/định dạng kiểu có liên quan locale, chẳng hạn ngày hoặc số theo vùng.
- `Validator` trả lời đối tượng sau chuyển đổi có đáp ứng quy tắc đầu vào không.

Một converter không nên “âm thầm sửa” một chuỗi không phải số thành `0` chỉ để né lỗi. Một validator cũng không nên chịu trách nhiệm giải mã chuỗi đầu vào.

## 7. Giao diện Spring MVC có tự chạy cả hai không?

**Có thể có**, tùy loại tham số và annotation; nhưng bên dưới vẫn là hai trách nhiệm khác nhau.

Với biểu mẫu dùng `@ModelAttribute`, Spring MVC tạo hoặc lấy đối tượng, dùng `WebDataBinder` để gắn các tham số thích hợp, rồi có thể gọi validation khi gặp `@Valid`/`@Validated`. Controller có thể nhận `BindingResult` ngay sau đối tượng để quyết định cách trả lỗi.

Đoạn sau là **minh họa tích hợp MVC**, giả sử `RegistrationForm` là bean có getter/setter như ở ví dụ và có `RegistrationValidator` được Spring quản lý hoặc được tiêm vào controller:

```java
@InitBinder("registration")
void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "age");
    binder.addValidators(registrationValidator);
}

@PostMapping(path = "/registrations",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<?> submit(
        @Validated @ModelAttribute("registration") RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
                result.getFieldErrors().stream()
                        .map(FieldError::getField)
                        .distinct()
                        .toList());
    }

    return ResponseEntity.ok().body("accepted");
}
```

Để đưa đoạn trích trên vào controller hoàn chỉnh, cần khai báo controller, tiêm `registrationValidator` và thêm imports tương ứng (`WebDataBinder`, `@InitBinder`, `@PostMapping`, `MediaType`, `@Validated`, `@ModelAttribute`, `BindingResult`, `ResponseEntity`, `FieldError`). Đây không phải tệp Java độc lập. `@Validated` báo Spring MVC rằng đối tượng cần được validate sau khi binding, còn `@InitBinder` cấu hình binder riêng cho tên đối tượng `registration`.

**Quy tắc quan trọng:** tham số `BindingResult` phải đứng **ngay sau** tham số được bind/validate mà nó mô tả. Controller có thể nhận và hiển thị cả lỗi binding lẫn lỗi validation. Nếu thiếu `BindingResult` hoặc có cơ chế xử lý ngoại lệ khác, Spring MVC có thể chuyển lỗi sang ngoại lệ/HTTP 400 tùy kiểu handler và cấu hình.

### 7.1. @RequestBody JSON có giống DataBinder.bind không?

Không nên đồng nhất hai đường xử lý:

- `@ModelAttribute` thường gắn các cặp tham số từ query/form vào object qua cơ chế WebDataBinder.
- `@RequestBody` dùng `HttpMessageConverter`, thường là Jackson với JSON, để **đọc và giải mã body thành đối tượng**. Quá trình này không đơn thuần là gọi `DataBinder.bind(MutablePropertyValues)` trên từng trường JSON.
- Sau khi tạo được đối tượng, Spring MVC có thể áp dụng validation qua `@Valid`/`@Validated`. JSON sai cú pháp hoặc không thể chuyển giá trị vào kiểu DTO có thể thất bại **trước** validation với lỗi đọc thông điệp như `HttpMessageNotReadableException`.
- Vi phạm constraint trên DTO `@Valid @RequestBody` thường được phản ánh qua `MethodArgumentNotValidException` và HTTP 400 trong Spring MVC thông thường; với method validation trực tiếp trên tham số, đường xử lý có thể khác.

Vì thế, khi nói “binding trước, validation sau”, hãy hiểu đây là **quan hệ logic giữa bước tạo/gắn dữ liệu và bước đánh giá ràng buộc**; các chi tiết kỹ thuật phụ thuộc nguồn dữ liệu và kiểu đối số controller.

## 8. Khi nào nên validate sau một binding có lỗi?

Một ứng dụng có thể muốn trả nhiều lỗi cùng lúc để người dùng sửa một lần. Tuy nhiên, không thể coi tất cả thuộc tính đều đã đúng kiểu nếu binder có lỗi chuyển đổi.

Một cách tổ chức thận trọng:

1. Bind dữ liệu và lấy `BindingResult`.
2. Xem lỗi conversion và xác định trường nào chưa có giá trị hợp lệ.
3. Nếu validator có thể kiểm tra an toàn phần đã bind (kiểm tra null, không giả định field đã được gắn), có thể chạy validation và gom lỗi.
4. Nếu validation phụ thuộc bắt buộc vào một thuộc tính đã chuyển đổi thất bại, bỏ qua quy tắc phụ thuộc đó hoặc phản hồi lỗi binding trước.
5. Chỉ tiếp tục tạo/lưu đối tượng nghiệp vụ khi không còn lỗi cần chặn và các bước xác thực, phân quyền, kiểm tra nghiệp vụ khác đều đạt.

Ví dụ `age=abc` phải nhận lỗi kiểu dữ liệu. Nếu validator không kiểm tra null mà gọi `form.getAge() < 18`, mã có thể ném `NullPointerException` do tự mở hộp `Integer`. Kiểm tra `age != null` trong ví dụ chính giúp không biến lỗi đầu vào thành lỗi máy chủ.

Không dùng mỗi `result.hasErrors()` **trước** `validate()` làm bằng chứng dữ liệu đã hợp lệ: đó mới chỉ là trạng thái sau binding. Tương tự, trả HTTP thành công ngay khi `bind()` xong bỏ qua các ràng buộc đã đăng ký.

## 9. Thiết kế kiểm thử để chứng minh hai bước độc lập

Bộ kiểm thử nên chia dữ liệu thành nhiều nhóm thay vì chỉ kiểm thử một request “thành công”:

| Trường hợp | Kiểm tra ngay sau bind | Kiểm tra sau validate |
| --- | --- | --- |
| `age=20`, tên hợp lệ | `age == 20`, không lỗi binding | Không lỗi |
| `age=17`, tên hợp lệ | `age == 17`, không lỗi binding | Lỗi `age.min` |
| `age=abc`, tên hợp lệ | Có lỗi kiểu của `age` | Vẫn nhìn thấy lỗi binding, không có exception từ validator |
| `name="  "`, `age=20` | Tên vẫn là chuỗi khoảng trắng | Lỗi tên rỗng |
| Thiếu `age` với quy tắc bắt buộc | `age` có thể `null` hoặc bị binder ghi lỗi `required` nếu cấu hình | Kiểm tra `null` khi chính sách validation yêu cầu |
| Dữ liệu có `role=ADMIN` nhưng chỉ cho phép `name` và `age` | `role` không được gắn; có thể xuất hiện ở `getSuppressedFields()` | Validation không thay thế chính sách cho phép field |

Với unit test không cần HTTP, tạo `DataBinder` và `MutablePropertyValues` như ví dụ để khẳng định lỗi xuất hiện ở đúng chặng. Với integration test MVC, dùng `MockMvc` để gửi form/query/JSON tương ứng và kiểm tra HTTP status cùng phản hồi lỗi mà API cam kết.

Trong test, không phụ thuộc vào thứ tự các `FieldError` trừ khi chính ứng dụng đã sắp xếp. Khi cần khẳng định nguồn gốc lỗi, dùng `FieldError.isBindingFailure()` và mã lỗi ở mức phù hợp, thay vì so sánh nguyên văn thông báo mặc định của thư viện.

## 10. Những sai lầm dễ gặp

1. **Cho rằng `bind()` tự chạy mọi constraint:** `DataBinder.bind(...)` chủ yếu gắn và chuyển kiểu. Muốn chạy Spring `Validator` đã đăng ký trong mã thủ công, gọi `validate()`.
2. **Cho rằng `validate()` sẽ sửa dữ liệu không chuyển được:** validator kiểm tra đối tượng hiện tại; chuyển kiểu thuộc bước binding/đọc body.
3. **Kiểm tra `hasErrors()` chỉ sau binding rồi trả thành công:** có thể bỏ qua lỗi tên rỗng, tuổi dưới ngưỡng và các quy tắc khác.
4. **Nhầm lỗi `typeMismatch` với `@Min`:** chuỗi không phải số và số nhỏ hơn ngưỡng là hai trường hợp khác nhau, thường cần thông báo khác nhau.
5. **Không kiểm tra `null` sau khi chuyển kiểu thất bại:** validator có thể ném exception thay vì ghi lỗi dễ hiểu.
6. **Cho rằng mọi lỗi trong `BindingResult` đều do `@Valid`:** binding có thể tạo lỗi ngay cả khi không có Bean Validation provider hoặc không gọi `validate()`.
7. **Lẫn lộn `setRequiredFields` và `@NotNull`:** trường bắt buộc khi bind và ràng buộc giá trị thuộc hai cơ chế khác nhau.
8. **Cho phép gắn mọi setter trên entity:** dữ liệu bên ngoài có thể thay đổi các trường không nên phơi bày; dùng DTO và phạm vi trường được phép.
9. **Gọi `validate()` lặp lại trên cùng binder và giả định lỗi được xóa:** có nguy cơ tích lũy lỗi trùng; quản lý vòng đời bộ kết quả rõ ràng.
10. **Đặt `BindingResult` sai vị trí trong chữ ký MVC:** Spring yêu cầu nó đứng sát đối tượng được bind/validate.
11. **Dùng `@RequestBody` và tưởng Jackson đang gọi `DataBinder.bind(...)`:** JSON được đọc qua message converter; lỗi giải mã có thể xảy ra trước Bean Validation.
12. **Tưởng DTO không lỗi là đã được phép lưu:** tầng service/domain vẫn phải kiểm tra nghiệp vụ, trạng thái hệ thống và quyền truy cập.

## 11. Bài tập tự kiểm tra

**Bài tập 1:** Với đầu vào `age="x"` và validator chỉ kiểm tra `age >= 18`, hãy giải thích lỗi gì xuất hiện ở bước bind, vì sao không nên so sánh trực tiếp `form.getAge() < 18` và phần nào chịu trách nhiệm phản hồi cho người dùng.

**Bài tập 2:** Thêm vào `RegistrationValidator` một ràng buộc `age != null`, rồi chạy lại ba kịch bản. Khi `age=abc` gây lỗi binding, quyết định xem có hiển thị thêm lỗi “age required” hay chỉ hiển thị lỗi chuyển kiểu; giải thích lựa chọn của bạn.

**Bài tập 3:** Gọi `binder.bind(input)` nhưng bỏ dòng `binder.validate()`. So sánh số lỗi của cả ba kịch bản với kết quả gốc. Sau đó đặt lại `validate()` và xác nhận hai lỗi của `rule-invalid` xuất hiện.

**Bài tập 4:** Thêm một trường `role` có setter vào form, nhưng vẫn giữ `setAllowedFields("name", "age")`. Gửi `role=ADMIN` trong `MutablePropertyValues`, kiểm tra rằng thuộc tính đó không được gắn và quan sát `getSuppressedFields()`.

**Bài tập 5:** Thiết kế một endpoint biểu mẫu `@ModelAttribute` có `BindingResult`, phân loại lỗi chuyển kiểu và lỗi validation thành hai loại thông báo nhưng vẫn trả một phản hồi thống nhất.

Nếu có thể giải thích vì sao **`"17"` bind thành công nhưng validate thất bại**, còn **`"abc"` thất bại ngay ở binding**, bạn đã nắm được ranh giới quan trọng nhất của `DataBinder`.

## Tham khảo chính thức

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Java Bean Validation và cấu hình DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
