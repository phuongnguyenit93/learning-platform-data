# BindException và việc kết thúc DataBinder bằng close

## 1. Mục tiêu bài học

Khi sử dụng Spring Framework để bind dữ liệu vào một đối tượng Java, kết quả không chỉ là các giá trị được gán thành công. Quá trình binding có thể gặp lỗi chuyển kiểu, thiếu trường bắt buộc, hoặc các lỗi được phát hiện khi validation. Spring tập hợp các lỗi đó trong một đối tượng `BindingResult`. Phương thức `DataBinder.close()` cung cấp một cách **chuyển từ kết quả lưu trong `BindingResult` sang kết quả thành công hoặc ngoại lệ `BindException`**.

Sau bài học, bạn có thể:

- Mô tả chính xác vai trò của `DataBinder`, `Errors`, `BindingResult` và `BindException`.
- Biết khi nào `bind()`, `validate()`, `getBindingResult()` và `close()` được gọi.
- Giải thích tại sao `close()` trả về `Map<?, ?>` nếu không có lỗi, nhưng ném `BindException` khi đã có lỗi.
- Phân biệt lỗi binding (chuyển kiểu, thiếu trường cấu hình bắt buộc) và lỗi validation do `Validator` đăng ký.
- Kiểm tra `FieldError`, `ObjectError` và model map mà không dựa vào thông điệp exception dạng chuỗi.
- Sử dụng API phù hợp với chương trình độc lập và với cơ chế xử lý request của Spring MVC.

**Điều quan trọng nhất:** tên `close()` ở đây **không có nghĩa đóng kết nối, giải phóng tài nguyên, gọi `AutoCloseable.close()` hoặc tự động chạy validation**. Nó kiểm tra các lỗi đã được tích lũy trong `BindingResult` và kết thúc luồng thao tác ở mức kết quả của lần binding mà người gọi quyết định.

## 2. Bốn thành phần và quan hệ giữa chúng

| Thành phần | Package | Vai trò |
| --- | --- | --- |
| `DataBinder` | `org.springframework.validation.DataBinder` | Nhận `PropertyValues`, gán vào đối tượng đích, chuyển đổi kiểu và phối hợp validation |
| `Errors` | `org.springframework.validation.Errors` | Hợp đồng ghi và truy vấn lỗi theo object/field |
| `BindingResult` | `org.springframework.validation.BindingResult` | Mở rộng `Errors` bằng thông tin binding, ví dụ `getTarget()`, `getModel()`, `getSuppressedFields()` |
| `BindException` | `org.springframework.validation.BindException` | Ngoại lệ được dùng khi coi các lỗi trong `BindingResult` là điều kiện thất bại cần ném ra caller |

`BindException` trong Spring Framework 6.x là **checked exception** (kế thừa `Exception`) và triển khai `BindingResult`. Vì thế có thể bắt bằng `catch (BindException ex)` rồi trực tiếp kiểm tra `ex.hasErrors()`, `ex.getFieldErrors()` hoặc `ex.getErrorCount()`. Nó bọc một `BindingResult` đã có, chứ không phải mỗi lỗi riêng tạo một exception độc lập.

Sự khác biệt quan trọng:

- **`BindingResult` là dữ liệu lỗi có cấu trúc.** Có thể tồn tại cùng đối tượng đích và được kiểm tra dù có hoặc không có lỗi.
- **`BindException` là tín hiệu điều khiển luồng.** Nó hữu ích khi caller muốn chuyển các lỗi đã tập hợp thành một trường hợp thất bại cần bắt hoặc xử lý ở biên.
- **`close()` là quyết định chuyển đổi.** Nó không tạo ra các ràng buộc validation; nó chỉ xem `getBindingResult().hasErrors()` tại thời điểm gọi.

Phần cốt lõi của hợp đồng `DataBinder.close()` là:

~~~java
// Pseudocode tương đương hành vi công khai của Spring 6.2;
// đây là minh họa, không phải mã bạn cần chép vào DataBinder.
public Map<?, ?> close() throws BindException {
    if (getBindingResult().hasErrors()) {
        throw new BindException(getBindingResult());
    }
    return getBindingResult().getModel();
}
~~~

Như vậy `close()` có hai nhánh rõ ràng và không có bước ngầm gọi `validate()`.

## 3. Trình tự chuẩn: bind → validate → kiểm tra → close

~~~text
Dữ liệu nguồn (PropertyValues)
         |
         v
DataBinder.bind(...) ----------> BindingResult nhận lỗi binding
         |                       (required, typeMismatch, ...)
         v
DataBinder.validate() ---------> BindingResult có thêm lỗi validation
         |                       (rejectValue, reject, ...)
         v
DataBinder.getBindingResult()
         |
         +--> hasErrors() = false --> close() trả Map model
         |
         +--> hasErrors() = true  --> close() ném BindException
~~~

### 3.1. Giai đoạn bind

`binder.bind(propertyValues)` thử gắn các property được cho phép vào target. Các lỗi có thể được ghi thành `FieldError`, ví dụ:

- `typeMismatch`: chuỗi đầu vào không chuyển được sang kiểu đích (chẳng hạn `"abc"` sang `Integer`).
- `required`: thiếu giá trị đối với field được đăng ký qua `setRequiredFields(...)`.
- `methodInvocation`: một lỗi từ lời gọi setter hoặc phương thức có liên quan được bộ xử lý lỗi binding ghi nhận.

Các mã lỗi cụ thể và danh sách mã thông điệp có thể được tinh chỉnh bởi `BindingErrorProcessor` và `MessageCodesResolver`. Một lỗi khi gán thuộc tính không nhất thiết làm `bind()` ném ngay `BindException`; `DataBinder` thường tích lũy những lỗi được thiết kế để ghi nhận trong `BindingResult`.

Lỗi Java nghiêm trọng ngoài cơ chế thu thập lỗi này vẫn có thể ném exception riêng. Không giả định mọi exception đều được hoãn cho đến `close()`.

### 3.2. Giai đoạn validate

`binder.setValidator(myValidator)` đăng ký một Spring `Validator`; `binder.validate()` yêu cầu validator chạy để bổ sung lỗi.

Ví dụ, một tuổi `17` có thể được parse thành `Integer` hợp lệ ở bước bind, nhưng không đáp ứng quy tắc tuổi tối thiểu `18` ở bước validate. Validator có thể gọi:

~~~java
errors.rejectValue("age", "age.tooYoung");
~~~

Đây là **mảnh logic trong `Validator.validate(Object, Errors)`**. Nó đăng ký một `FieldError` mà không tự ném `BindException`.

`setValidator(...)` **không** có nghĩa `bind()` hoặc `close()` tự chạy validator. Người gọi dùng `DataBinder` trực tiếp phải chủ động gọi `validate()` đúng lúc. Trong Spring MVC, framework có thể điều phối validation bằng `@Valid`/`@Validated` tùy tham số, nên không nên tự suy diễn vòng đời web từ ví dụ binder độc lập.

### 3.3. Đọc lỗi và chọn cách xử lý

`binder.getBindingResult()` cho phép quan sát lỗi trước khi quyết định ném:

~~~java
BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    for (FieldError fieldError : result.getFieldErrors()) {
        System.out.println(fieldError.getField());
    }
}
~~~

Mảnh code trên cần các import `org.springframework.validation.BindingResult` và `FieldError`. Nếu muốn trả về lỗi cho người dùng thay vì ném exception, hoàn toàn có thể xử lý `BindingResult` trực tiếp mà không gọi `close()`.

## 4. Ví dụ Java 17 chạy độc lập: thành công, lỗi validation, lỗi chuyển kiểu

Ví dụ sau dùng Spring Framework **6.2.0**, Java 17 và Maven, **không yêu cầu Spring Boot, servlet, controller hay Bean Validation provider**. Để các kết quả có thể dự đoán, chương trình định nghĩa một Spring `Validator` đơn giản và in ra tổng số lỗi cùng thuộc tính `isBindingFailure()`.

Tạo tệp `pom.xml` tại thư mục dự án:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>bind-close-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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

Tạo `src/main/java/BindCloseDemo.java`:

~~~java
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class BindCloseDemo {

    public static class RegistrationForm {
        private String email;
        private Integer age;

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

    public static class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;

            if (form.getEmail() == null
                    || form.getEmail().isBlank()) {
                errors.rejectValue("email", "email.required");
            }
            if (form.getAge() != null && form.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung");
            }
        }
    }

    private static void runCase(
            String label, String email, String ageInput) {

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registration");
        binder.setAllowedFields("email", "age");
        binder.setValidator(new RegistrationValidator());

        binder.bind(new MutablePropertyValues(Map.of(
            "email", email,
            "age", ageInput
        )));

        BindingResult result = binder.getBindingResult();
        System.out.println("CASE " + label);
        System.out.println("afterBind=" + result.getErrorCount());

        binder.validate();
        System.out.println("afterValidate=" + result.getErrorCount());

        try {
            Map<?, ?> model = binder.close();

            boolean targetKeyPresent =
                model.get("registration") == form;
            boolean resultKeyPresent =
                model.get(
                    BindingResult.MODEL_KEY_PREFIX + "registration"
                ) == result;

            System.out.println("close=OK");
            System.out.println(
                "modelKeysPresent=" +
                (targetKeyPresent && resultKeyPresent)
            );
        } catch (BindException ex) {
            FieldError ageError = ex.getFieldError("age");

            System.out.println("close=BindException");
            System.out.println(
                "caughtErrorCount=" + ex.getErrorCount()
            );
            System.out.println(
                "ageBindingFailure=" +
                (ageError != null && ageError.isBindingFailure())
            );
        }
    }

    public static void main(String[] args) {
        runCase("valid", "lan@example.com", "20");
        runCase("invalid", " ", "17");
        runCase("badAgeType", "lan@example.com", "abc");
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` (Java 17+ và Maven đã cài):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=BindCloseDemo
~~~

Stdout từ chính chương trình (không tính thông báo ngoài chương trình của Maven/môi trường):

~~~text
CASE valid
afterBind=0
afterValidate=0
close=OK
modelKeysPresent=true
CASE invalid
afterBind=0
afterValidate=2
close=BindException
caughtErrorCount=2
ageBindingFailure=false
CASE badAgeType
afterBind=1
afterValidate=1
close=BindException
caughtErrorCount=1
ageBindingFailure=true
~~~

### Diễn giải chính xác từng ca

**Ca `valid`:** Dữ liệu `age="20"` được chuyển thành `Integer 20`, email không blank, validator không thêm lỗi. `close()` trả về model map. Hai khóa được kiểm bằng cách truy cập trực tiếp thay vì in ra thứ tự các phần tử của map.

**Ca `invalid`:** `age="17"` có kiểu hợp lệ, do đó `afterBind=0`. Validator phát hiện email chỉ có dấu cách và tuổi nhỏ hơn 18; `afterValidate=2`. `close()` thấy `hasErrors() == true` rồi ném `BindException`. Lỗi tuổi là **validation failure**, không phải **binding failure**, nên `ageBindingFailure=false`.

**Ca `badAgeType`:** `age="abc"` không chuyển được thành `Integer`. `DataBinder` ghi một `FieldError` của bước bind với thuộc tính `isBindingFailure()==true`. Validator minh họa đã xử lý null an toàn và không thêm lỗi tuổi khi chuyển kiểu thất bại, nên cả trước và sau `validate()` vẫn có một lỗi. `close()` ném `BindException` và `ageBindingFailure=true`.

Đây là **một chương trình đầy đủ có `main`**. Các ví dụ `@ModelAttribute` hay `@ExceptionHandler` ở phần sau là mảnh code thuộc ứng dụng Spring MVC, cần project web riêng.

## 5. BindException chứa những gì?

`BindException` triển khai `BindingResult` và có thể truy cập đối tượng `BindingResult` được bọc qua `getBindingResult()`. Trong nhánh catch bạn có thể dùng:

~~~java
catch (BindException ex) {
    BindingResult result = ex.getBindingResult();

    int total = result.getErrorCount();
    boolean hasAgeError = result.hasFieldErrors("age");

    for (FieldError error : result.getFieldErrors()) {
        String field = error.getField();
        boolean fromBinding = error.isBindingFailure();
        Object rejected = error.getRejectedValue();

        // Quyết định mã lỗi và thông báo phù hợp với caller.
    }
}
~~~

Đây là **mảnh catch** dùng trong một phương thức có lệnh gọi `binder.close()`. Biến `total` và `hasAgeError` phục vụ phân tích; `rejected` có thể chứa dữ liệu do người dùng gửi và cần tránh log các bí mật.

Các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `hasErrors()` | Có ít nhất một lỗi field hoặc object |
| `getErrorCount()` | Tổng số lỗi |
| `getFieldErrors()` / `getFieldError("age")` | Các lỗi gắn với field cụ thể |
| `getGlobalErrors()` | Lỗi ở cấp object (ví dụ quy tắc liên quan nhiều field) |
| `FieldError.isBindingFailure()` | Phân biệt lỗi đến từ quá trình bind với lỗi logic validation thông thường |
| `FieldError.getRejectedValue()` | Giá trị đã bị từ chối khi ghi lỗi; cần xử lý an toàn vì có thể nhạy cảm |
| `ObjectError.getCodes()` | Các mã có thứ tự ưu tiên để tra cứu thông điệp qua `MessageSource` |
| `getObjectName()` | Tên đối tượng đích, ví dụ `registration` |
| `getBindingResult()` | Lấy holder có cấu trúc đã được `BindException` bọc |

Một `FieldError` thuộc nhóm `ObjectError` nhưng có thêm thông tin field; lỗi do `Errors.reject(...)` thường là global error, còn `Errors.rejectValue(...)` là field error. Tên mã lỗi, danh sách `getCodes()` và thông điệp cuối cùng do resolver/message catalog quyết định; không nên kiểm thử dựa vào toàn bộ chuỗi `exception.getMessage()` vì nó có thể bao gồm nhiều chi tiết và biến động theo phiên bản.

`BindException` là **ngoại lệ checked** trong ví dụ Spring 6.x, nên mã Java gọi `close()` phải `catch` hoặc khai báo `throws BindException` theo quy tắc Java. Nó không giống `ConstraintViolationException` được dùng trong một số luồng Jakarta method validation.

## 6. Vì sao close() trả về Map và model này gồm những khóa nào?

Trong trường hợp thành công, `close()` trả kết quả tương đương `getBindingResult().getModel()`. Với binder khởi tạo như sau:

~~~java
DataBinder binder = new DataBinder(registrationForm, "registration");
~~~

model có hai entry quan trọng:

| Key | Value |
| --- | --- |
| `"registration"` | Đối tượng target `registrationForm` |
| `BindingResult.MODEL_KEY_PREFIX + "registration"` | Chính `BindingResult` tương ứng |

Hằng `BindingResult.MODEL_KEY_PREFIX` có giá trị `"org.springframework.validation.BindingResult."` trong Spring Framework; vì vậy key thứ hai là `"org.springframework.validation.BindingResult.registration"`. Sự có mặt của cả target và kết quả lỗi rất hữu ích khi một view cần hiển thị lại dữ liệu form và các thông báo validation.

Ví dụ mã dùng trực tiếp, không phụ thuộc vào thứ tự các entry:

~~~java
Map<?, ?> model = binder.close();

Object target = model.get("registration");
Object errors = model.get(
    BindingResult.MODEL_KEY_PREFIX + "registration"
);
~~~

Khi có lỗi, `close()` **không trả map** mà ném ngoại lệ. Nếu caller vẫn muốn lấy model để tái hiển thị form dù có lỗi, có thể gọi `binder.getBindingResult().getModel()` trực tiếp. `BindingResult.getModel()` tạo một map kết quả mới cho mỗi lần gọi; sửa map đã nhận rồi gọi lại `getModel()` không có nghĩa thay đổi đó được lưu vào kết quả kế tiếp.

Đừng hiểu `close()` như phương thức ghi vào database, commit transaction, huỷ binder hoặc thay đổi target theo nghĩa “chỉ chấp nhận khi hợp lệ”. Việc bind đã có thể gán **một phần** thuộc tính vào target trước khi lỗi được ghi nhận; ném `BindException` không tự rollback target về trạng thái ban đầu.

## 7. Những ngộ nhận về từ “close”

### 7.1. close() không phải đóng resource

`DataBinder` không được dùng như một `AutoCloseable`. Mã kiểu:

~~~java
// SAI: DataBinder không phải AutoCloseable.
try (DataBinder binder = new DataBinder(form, "form")) {
    // ...
}
~~~

sẽ không đáp ứng hợp đồng try-with-resources, bởi `DataBinder` không triển khai `AutoCloseable`. Không cần gọi `close()` trong khối `finally` như khi đóng stream, connection hay file. Nếu không muốn chuyển lỗi thành exception, bạn được phép chỉ dùng `getBindingResult()`.

### 7.2. close() không tự validate

~~~java
binder.setValidator(myValidator);
binder.bind(values);
binder.close();  // Chỉ thấy lỗi đã có, chưa chạy myValidator.
~~~

Đây là **mảnh code minh họa** với các biến đã khởi tạo. Nếu dữ liệu bind hoàn toàn đúng kiểu nhưng vi phạm nghiệp vụ, `close()` có thể trả thành công vì `validate()` chưa được gọi. Thứ tự đúng khi cần validator là:

~~~java
binder.setValidator(myValidator);
binder.bind(values);
binder.validate();
Map<?, ?> model = binder.close();
~~~

### 7.3. close() không tạo ngoại lệ cho mỗi field

Một `BindException` thường mang **toàn bộ** tập lỗi đã thu thập. Đây là ưu điểm của `BindingResult`: bạn có thể hiển thị đồng thời lỗi `email`, `age` và lỗi object nếu cùng phát sinh.

### 7.4. Không phải mọi lỗi đều làm close() thất bại

Các field không được phép bind và bị suppression được ghi trong `getSuppressedFields()`, nhưng **không mặc nhiên được thêm vào danh sách lỗi khiến `hasErrors()` trả true**. Ví dụ:

~~~java
binder.setAllowedFields("email", "age");
binder.bind(new MutablePropertyValues(Map.of("role", "ADMIN")));
String[] suppressed = binder.getBindingResult().getSuppressedFields();
~~~

Đây là mảnh code với binder đã tạo và object name phù hợp. Trường `role` bị loại vì không trong whitelist; nên **không** coi việc `close()` không ném exception là bằng chứng chắc chắn rằng request không có trường thừa hoặc không được phép. Nếu contract yêu cầu từ chối field bị suppression, caller cần tự kiểm `suppressed.length > 0` và xử lý phù hợp.

Tương tự, `setIgnoreUnknownFields(true)` là cấu hình mặc định cho property binding và có thể bỏ qua field không khớp object thay vì sinh error. Để bảo vệ dữ liệu, nên dùng DTO/command object riêng và whitelist field cho phép; tránh bind thẳng entity có thuộc tính nhạy cảm.

## 8. Required field, lỗi chuyển kiểu và lỗi validation khác nhau thế nào?

Bộ xử lý lỗi mặc định của `DataBinder` có thể ghi lỗi `required` khi bạn cấu hình field bắt buộc đối với property binding:

~~~java
DataBinder binder = new DataBinder(form, "registration");
binder.setRequiredFields("email");
binder.bind(new MutablePropertyValues(Map.of("age", "20")));
BindingResult errors = binder.getBindingResult();
~~~

Mảnh code này phụ thuộc class `form` có thuộc tính `email` và `age`; `email` không có trong dữ liệu nguồn. `errors` sẽ chứa lỗi required đối với `email`. Đây là **kiểm tra ở lúc binding**, không phải Jakarta `@NotBlank` hay Spring custom validator.

Để so sánh:

| Loại lỗi | Nguồn phát sinh | Ví dụ | Cách quan sát |
| --- | --- | --- | --- |
| Missing required field | `DataBinder` với `setRequiredFields(...)` | Thiếu `email` | `FieldError` mã `required` |
| Type mismatch | Converter/PropertyEditor khi bind | `age="abc"` cho `Integer` | `FieldError` có `isBindingFailure() == true` |
| Field validation | `Validator.validate(...)`/Bean Validation khi được gọi | `age=17` nhỏ hơn 18 | `FieldError` của field `age` |
| Cross-field validation | Validator kiểm quan hệ các field | `startDate` sau `endDate` | `ObjectError` qua `reject(...)` hoặc field error có chủ đích |
| Suppressed field | Whitelist bảo vệ binding | `role` không được phép bind | `getSuppressedFields()`; không mặc nhiên là error |

Ngoài mã `required` và `typeMismatch`, Spring còn có thể sinh `methodInvocation` trong ngữ cảnh setter/method. Không nên tự tạo các chuỗi thông báo dựa hoàn toàn vào một mã cụ thể khi ứng dụng cấu hình custom `BindingErrorProcessor`/`MessageCodesResolver`.

**Điểm thực hành:** Khi convert tuổi thất bại, đừng vừa truy cập giá trị tuổi như đã hợp lệ vừa thêm lỗi validation trên cùng giả định sai. Validator cần chịu được giá trị còn null/không được set, hoặc thiết kế trình tự/điều kiện gọi thích hợp. `close()` không giải quyết thay việc này.

## 9. Khi nào dùng BindException trong ứng dụng web Spring MVC?

Có thể có hai tình huống rất khác nhau:

**A. Bạn tự tạo `DataBinder` và gọi `close()`:** đây là thao tác lập trình tường minh, giống ví dụ độc lập phía trên. Bạn hoàn toàn có thể làm vậy trong service/adapter nếu muốn, rồi bắt `BindException` ở biên tương ứng. Nhưng thường không cần tự tạo binder trong một controller đã sử dụng cơ chế MVC.

**B. Spring MVC tự bind và validate tham số handler:** framework điều phối việc đọc request, chuyển kiểu và validation. Với `@ModelAttribute`, lỗi có thể được truyền cho tham số `BindingResult`/`Errors` đứng ngay sau object. Với `@RequestBody` JSON, body thông thường được deserialize bởi `HttpMessageConverter` (ví dụ Jackson), không phải mọi thứ đều là lời gọi `DataBinder.bind(...)` như với form field.

Ví dụ một **mảnh method thuộc Spring MVC controller**:

~~~java
@PostMapping("/register")
ResponseEntity<?> register(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
            errors.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getCode())
                .toList()
        );
    }
    return ResponseEntity.ok("accepted");
}
~~~

Method này cần import `jakarta.validation.Valid`, `org.springframework.validation.BindingResult`, các annotation MVC và `ResponseEntity`; `RegistrationForm` phải có các constraint phù hợp và ứng dụng có Bean Validation provider nếu muốn `@Valid` tác động. Mã là ví dụ trong controller, **không phải program có `main`**.

Trong Spring MVC 6.2, khi dùng `@Valid`/`@Validated` cho một object handler parameter và không có `Errors`/`BindingResult` để xử lý cục bộ, lỗi validation ở cấp argument thường được báo bằng `MethodArgumentNotValidException`. Class này kế thừa `BindException` trong Spring 6.2, nhưng còn mang hợp đồng HTTP-specific `ErrorResponse`. Khi ràng buộc trực tiếp trên tham số/method khiến method validation được áp dụng, Spring MVC 6.1+ có thể phát sinh `HandlerMethodValidationException`. Lỗi parse body có thể là `HttpMessageNotReadableException`.

Đừng mô tả **mọi** lỗi web là kết quả của một lệnh `DataBinder.close()` do lập trình viên gọi, hoặc cứ bắt `BindException` là xử lý được mọi trường hợp. `@ControllerAdvice` hoặc `ResponseEntityExceptionHandler` có thể ánh xạ từng dạng lỗi thành response thống nhất, đồng thời giữ mã trường, thông điệp, status và thông tin cần thiết.

Trong Spring WebFlux, lỗi validation của binding có thể đi qua `WebExchangeBindException` và vòng đời reactive khác MVC. Khi gọi `DataBinder` độc lập, không có HTTP status mặc định được tạo ra từ `BindException`: caller tự chọn cách phản hồi.

## 10. Xử lý lỗi: exception hay trả về kết quả?

Không phải mọi caller đều nên nhận checked exception. Chọn theo hợp đồng ứng dụng:

| Tình huống | Lựa chọn hợp lý |
| --- | --- |
| Một batch CSV cần ghi lỗi cho từng dòng và tiếp tục | Đọc `getBindingResult()`, lưu lỗi theo dòng; tránh exception như luồng thường xuyên |
| API/form cần trả về nhiều lỗi field cùng lúc | Dùng `BindingResult` của framework/controller, chuyển lỗi thành response rõ ràng |
| Một bước bind phải thất bại ngay khi dữ liệu đầu vào không hợp lệ | Gọi `validate()` khi cần, sau đó `close()` và xử lý `BindException` tại ranh giới |
| Một service đã nhận DTO đúng kiểu, không cần property binding | Dùng `Validator`/Jakarta Validation trực tiếp thay vì tạo `DataBinder` chỉ để được `BindException` |
| Cần tạo model cho form/view | Dùng `BindingResult.getModel()` hoặc kết quả `close()` khi không lỗi |
| Dữ liệu có field bị cấm bind | Kiểm `getSuppressedFields()` và áp quy tắc từ chối riêng; `close()` không tự đảm bảo |

**Bảo mật và log:** lỗi có thể chứa tên field, giá trị bị từ chối, tên object, chuỗi đầu vào. Tránh đưa dữ liệu nhạy cảm (password, token, thông tin cá nhân) vào log hoặc body HTTP. Dùng mã lỗi ổn định, thông điệp qua `MessageSource` khi phù hợp và cấu trúc field/path rõ ràng; không phản hồi toàn bộ `BindException.toString()` cho client.

## 11. Kiểm thử các ranh giới hành vi của close()

Một bộ test có ý nghĩa nên kiểm tra:

1. **Không có lỗi:** gọi bind, validate, `close()`; xác nhận model có target và key `BindingResult.MODEL_KEY_PREFIX + objectName`.
2. **Validation failure:** input chuyển kiểu thành công nhưng custom `Validator` gọi `rejectValue(...)`; xác nhận `close()` ném `BindException` với số lỗi đúng và `isBindingFailure()==false` cho lỗi validator.
3. **Binding failure:** input sai kiểu cho property; xác nhận trước validate đã có `FieldError` và `isBindingFailure()==true`.
4. **Chưa gọi validate:** đăng ký validator rồi chỉ bind + close; xác nhận `close()` chỉ kiểm lỗi có sẵn, không tự chạy `Validator`.
5. **Missing required:** dùng `setRequiredFields(...)` rồi bỏ field; xác nhận lỗi `required` được ghi từ giai đoạn bind.
6. **Global error:** validator gọi `reject("invalidCombination")`; xác nhận `getGlobalErrors()` và `hasErrors()` phản ánh lỗi object.
7. **Suppressed field:** whitelist không cho bind một property; kiểm `getSuppressedFields()` vì không nhất thiết khiến `close()` ném.
8. **Target chỉ được bind một phần:** gây `typeMismatch` ở một field và hợp lệ ở field khác; xác nhận ngoại lệ không tự rollback các property đã gán thành công.

Các phép kiểm này trực tiếp bảo vệ hợp đồng của `DataBinder.close()`. Nếu test chỉ so sánh toàn bộ chuỗi `BindException.getMessage()` hoặc dựa vào thứ tự `Map.keySet()` thì dễ gặp test giòn khi framework/message resolver thay đổi.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `binder.setValidator(v)` rồi `binder.close()` có chắc đã chạy `v.validate()` chưa?  
**Trả lời:** Chưa. Với `DataBinder` dùng tường minh, cần gọi `binder.validate()` hoặc cơ chế khác thực sự kích hoạt validator.

**Câu 2.** Input `age="abc"` cho field `Integer age` sinh lỗi ở đâu?  
**Trả lời:** Trong quá trình binding/chuyển kiểu, thường được ghi thành `FieldError` `typeMismatch`. `close()` sau đó có thể ném `BindException` vì kết quả đã có lỗi.

**Câu 3.** Tại sao `close()` có thể thất bại dù target object đã chứa một số property hợp lệ?  
**Trả lời:** Binding không phải transaction. Spring có thể gán các property hợp lệ và ghi lỗi ở property khác; `close()` chỉ đánh giá tập lỗi hiện tại, không rollback.

**Câu 4.** Khi có hai lỗi field, `close()` ném mấy `BindException`?  
**Trả lời:** Một ngoại lệ chứa `BindingResult` tập hợp các lỗi, không phải hai ngoại lệ riêng.

**Câu 5.** Khi cần hiển thị form đã bind dù có lỗi, phải gọi `close()` không?  
**Trả lời:** Không. Dùng `getBindingResult()` và `getModel()` nếu muốn giữ dữ liệu để hiển thị lỗi mà không chuyển sang ngoại lệ.

**Câu 6.** Có thể thay `try/catch BindException` bằng `try-with-resources(DataBinder)` không?  
**Trả lời:** Không. `DataBinder` không phải `AutoCloseable`.

**Câu 7.** Field bị suppression có được `close()` tự phát hiện như lỗi validation không?  
**Trả lời:** Không mặc nhiên. Kiểm `BindingResult.getSuppressedFields()` và áp chính sách xử lý field không được phép.

## 13. Tổng hợp luồng xử lý để sử dụng đúng

~~~text
Tạo DataBinder(target, objectName)
    |
    +-- thiết lập allowedFields / requiredFields / conversion / Validator
    |
    +-- bind(PropertyValues)
    |       |
    |       +-- FieldError từ lỗi binding (nếu có)
    |
    +-- validate()   <-- chỉ khi cần, không được close() gọi ngầm
    |       |
    |       +-- FieldError / ObjectError từ validator (nếu có)
    |
    +-- getBindingResult()
    |       |
    |       +-- có lỗi?
    |              |
    |              +-- đọc và trả lỗi (không cần close)
    |              |
    |              +-- close() -> ném BindException nếu muốn throw
    |
    +-- không lỗi -> close() trả Map chứa target + BindingResult
~~~

`DataBinder.close()` là **điểm đưa quyết định “có lỗi hay không” thành ngoại lệ hoặc model trả về**. Chỉ nên dùng nó khi kiểu xử lý đó thực sự phù hợp với caller. Với form MVC và API HTTP, ưu tiên sử dụng cơ chế `BindingResult`/exception handling đã được framework tích hợp; với service/CLI/batch, quyết định trả lỗi hay ném lỗi dựa trên contract của tầng đó.

## Tài liệu chính thức

- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/BindException.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring MVC 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
