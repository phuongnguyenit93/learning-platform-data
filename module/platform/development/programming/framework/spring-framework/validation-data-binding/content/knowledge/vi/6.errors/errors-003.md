# ObjectError và FieldError trong Spring Framework

## 1. Vai trò của hai kiểu lỗi

Khi Spring thực hiện **data binding** (gắn dữ liệu request vào đối tượng Java) hoặc **validation** (kiểm tra dữ liệu hợp lệ), kết quả có thể chứa nhiều lỗi. Spring biểu diễn chúng bằng hai lớp trong package `org.springframework.validation`:

- **`ObjectError`:** mô tả lỗi liên quan tới **toàn bộ đối tượng** (global/object-level error), chẳng hạn một quy tắc nghiệp vụ cần xét nhiều thuộc tính cùng lúc.
- **`FieldError`:** mô tả lỗi của **một thuộc tính cụ thể** (field-level error), chẳng hạn `age` không chuyển được thành số hoặc `email` không đạt điều kiện `@Email`.

Điểm quan trọng về quan hệ kế thừa:

```text
org.springframework.context.support.DefaultMessageSourceResolvable
              |
              v
org.springframework.validation.ObjectError
              |
              v
org.springframework.validation.FieldError
```

**`FieldError extends ObjectError`.** Vì vậy mọi `FieldError` cũng là một `ObjectError` theo nghĩa **kiểu Java**, nhưng nó mang thêm thông tin về trường bị lỗi. Khi nói *global error* trong `BindingResult`, Spring đang nói tới lỗi **không gắn với field**; không nên suy luận rằng mọi phần tử có kiểu `ObjectError` đều là global error.

Ví dụ một form đặt hàng:

```text
productCode = ""
quantity    = "abc"
currency    = "USD"
country     = "VN"
```

- `productCode` rỗng, vi phạm `@NotBlank` → thường tạo `FieldError` cho `productCode`.
- `quantity=abc` không thể đổi thành `Integer` → tạo `FieldError` cho `quantity` với cờ `bindingFailure=true`.
- Cả đơn hàng không đáp ứng một quy tắc phối hợp, chẳng hạn “loại đơn này không được dùng với quốc gia đó” → validator có thể đăng ký `ObjectError` toàn cục.

Một quy tắc liên quan nhiều field không **bắt buộc** phải là global error: người viết validator có thể chủ động gắn vi phạm vào một field được chọn. Cách lỗi xuất hiện phụ thuộc nơi validator báo lỗi.

## 2. So sánh cấu trúc và API

| Thuộc tính/phương thức | `ObjectError` | `FieldError` |
| --- | --- | --- |
| Package | `org.springframework.validation` | `org.springframework.validation` |
| Mục tiêu | Đối tượng/model tổng thể | Một trường/đường dẫn thuộc tính |
| Kế thừa | `DefaultMessageSourceResolvable` | `ObjectError` |
| `getObjectName()` | Có | Có (kế thừa) |
| `getCodes()`, `getCode()` | Có | Có (kế thừa) |
| `getArguments()`, `getDefaultMessage()` | Có | Có (kế thừa) |
| `getField()` | Không | Có |
| `getRejectedValue()` | Không | Có |
| `isBindingFailure()` | Không | Có |
| Nguồn sinh điển hình | `errors.reject(...)` hoặc object-level constraint | `errors.rejectValue(...)`, type mismatch, field constraint |
| Truy xuất thuận tiện | `errors.getGlobalErrors()` | `errors.getFieldErrors()` |

### Ý nghĩa của từng trường dữ liệu

**`objectName`** là tên đối tượng đang được validate/bind, ví dụ `"registration"`; không nhất thiết trùng tên class Java. Trong MVC, nó thường đến từ tên model attribute; trong `new DataBinder(target, "registration")`, lập trình viên truyền tên trực tiếp.

**`codes`** là danh sách khóa thông báo có thứ tự ưu tiên, dùng để tìm bản dịch hoặc câu thông báo phù hợp. **`defaultMessage`** là thông báo dự phòng nếu không tìm thấy khóa thích hợp; nó không bảo đảm đã được dịch sang ngôn ngữ của người dùng.

**`field`** là tên thuộc tính bị lỗi, ví dụ `"age"`, `"address.zipCode"` hoặc `"items[0].quantity"`. **`rejectedValue`** là giá trị bị từ chối theo ngữ cảnh binding/validation; giá trị này có thể là dữ liệu nhạy cảm, nên không in nguyên văn ra log hoặc API công khai.

**`bindingFailure`** phân biệt lỗi gắn/chuyển kiểu (`true`) với lỗi validation thông thường (`false`). Cần biết *lỗi ở field nào* và *lý do loại lỗi* thay vì chỉ nhìn thông điệp.

### Phương thức cơ bản

```java
ObjectError objectError = ...; // Lấy từ BindingResult.getGlobalError()
String objectName = objectError.getObjectName();
String[] messageCodes = objectError.getCodes();
String defaultMessage = objectError.getDefaultMessage();

FieldError fieldError = ...; // Lấy từ BindingResult.getFieldError("age")
String field = fieldError.getField();
Object rejected = fieldError.getRejectedValue();
boolean conversionOrBindingFailed = fieldError.isBindingFailure();
```

Đây là đoạn minh họa dùng khi đã có hai biến lỗi khác `null`, **không phải một file Java độc lập**. `getGlobalError()` và `getFieldError(...)` có thể trả `null`; code thực tế phải kiểm tra trước khi gọi phương thức.

## 3. Nơi lưu lỗi: `Errors` và `BindingResult`

`ObjectError`/`FieldError` là **các bản ghi lỗi**. Đối tượng giữ tập hợp lỗi trong luồng Spring là interface `Errors` và interface con `BindingResult`:

```text
HTTP form/query
      |
      v
WebDataBinder / DataBinder
      |
      +--> chuyển kiểu hoặc gán sai ------> FieldError (binding failure)
      |
      +--> chạy Validator / Bean Validation
                 |
                 +--> lỗi thuộc tính ------> FieldError
                 |
                 +--> lỗi toàn object ----> ObjectError
      |
      v
BindingResult extends Errors
      |
      +--> getFieldErrors()  : List<FieldError>
      +--> getGlobalErrors() : List<ObjectError> (global only)
      +--> getAllErrors()    : List<ObjectError> (cả hai loại)
```

Trong lập trình MVC, controller thường khai báo `BindingResult` ngay sau đối tượng `@ModelAttribute` hoặc `@RequestBody` cần được validate. Khi chỉ viết một validator độc lập, tham số thường dùng interface `Errors`. Khi cần truy xuất giá trị field, metadata binding, danh sách field bị chặn hoặc `getModel()`, `BindingResult` cung cấp thêm phương thức.

Các phương thức truy xuất quan trọng:

| API trên `Errors` / `BindingResult` | Kết quả |
| --- | --- |
| `hasErrors()` | Có ít nhất một lỗi thuộc loại bất kỳ |
| `hasGlobalErrors()` | Có ít nhất một global error |
| `hasFieldErrors()` | Có ít nhất một field error |
| `hasFieldErrors("email")` | Có lỗi ở field `email` |
| `getErrorCount()` | Tổng số bản ghi lỗi |
| `getGlobalErrorCount()` | Số global errors |
| `getFieldErrorCount()` | Số field errors |
| `getGlobalError()` | Global error đầu tiên hoặc `null` |
| `getFieldError("email")` | Field error đầu tiên của `email` hoặc `null` |
| `getGlobalErrors()` | Danh sách global errors |
| `getFieldErrors()` | Danh sách field errors |
| `getFieldErrors("email")` | Danh sách mọi lỗi của `email` |
| `getAllErrors()` | Cả global errors và field errors |
| `getFieldValue("email")` | Giá trị field để hiển thị lại, có thể là giá trị bị từ chối |
| `getSuppressedFields()` | Tên những field bị chặn trong quá trình binding (API `BindingResult`) |

**Một field có thể có nhiều lỗi**, nên `getFieldErrorCount()` đếm số **bản ghi**, không phải số tên field khác nhau. Ví dụ cùng một field có thể vi phạm hai constraint. Không dùng `getFieldError("email")` nếu yêu cầu là hiển thị **tất cả** lỗi của field đó; cần `getFieldErrors("email")`.

Quan trọng: `getAllErrors()` trả về kiểu khai báo `List<ObjectError>`, vì `FieldError` kế thừa `ObjectError`. Muốn phân nhóm khi duyệt danh sách đó, kiểm tra `instanceof FieldError` hoặc dùng riêng hai phương thức `getFieldErrors()` / `getGlobalErrors()`.

## 4. Tạo lỗi bằng `reject` và `rejectValue`

Spring cung cấp hai thao tác trực tiếp qua `Errors` và `BindingResult`:

```java
// Lỗi liên quan toàn bộ đối tượng:
errors.reject("order.inconsistent",
              "Thông tin đơn hàng không nhất quán");

// Lỗi liên quan một field cụ thể:
errors.rejectValue("quantity",
                   "quantity.invalid",
                   "Số lượng không hợp lệ");
```

Đây là hai lời gọi **trong method đã có biến `errors` hợp lệ**. Khi gọi `reject(...)`, Spring thêm global error; với `rejectValue("quantity",...)`, nó thêm field error. Các overload khác cho phép cung cấp `Object[] errorArgs` để tạo thông điệp có tham số.

Ví dụ quy tắc nhiều thuộc tính:

```java
// Trong method Validator.validate(Object target, Errors errors):
OrderForm form = (OrderForm) target;

if ("INTERNATIONAL".equals(form.getShippingMethod())
        && "DOMESTIC_ONLY".equals(form.getProductType())) {
    errors.reject("shipping.product.conflict",
                  "Sản phẩm không hỗ trợ cách giao hàng này");
}

if (form.getQuantity() != null && form.getQuantity() <= 0) {
    errors.rejectValue("quantity", "quantity.positive",
                       "Số lượng phải lớn hơn 0");
}
```

Đoạn trên là ví dụ minh họa cho class `OrderForm` do ứng dụng định nghĩa, cần đặt trong phương thức `validate` phù hợp. Trong ví dụ, lỗi đầu là object-level vì nó mô tả quan hệ giữa hai thuộc tính; lỗi thứ hai được gắn với field `quantity` để UI có thể hiện ngay cạnh ô nhập.

### Không chỉ có lỗi từ validator

`DataBinder` tự ghi nhận một số lỗi binding mà không cần gọi `rejectValue(...)`:

- `typeMismatch`: không đổi được chuỗi sang kiểu đích, ví dụ `"abc"` → `Integer`.
- `required`: thiếu field được binder cấu hình là bắt buộc với `setRequiredFields(...)`.
- `methodInvocation`: lỗi gọi setter/property theo cơ chế xử lý lỗi của binder.

Các mã trên là các mã lỗi thông dụng do `DefaultBindingErrorProcessor` tạo; phiên bản/configuration khác có thể dùng strategy khác. Cần phân biệt lỗi binding xảy ra khi **chuyển/gán dữ liệu** và lỗi validation xảy ra khi **đánh giá quy tắc**. `@NotBlank`, `@Size`, `@Min` hoặc Spring `Validator` thường thêm validation errors sau binding khi được kích hoạt.

## 5. Ví dụ Java 17+ hoàn chỉnh: xem cả ba lỗi

Ví dụ dưới đây chạy ngoài web server, dùng Spring Framework 6.2.x và Maven. Mục tiêu là chứng minh cách `DataBinder` tạo `FieldError` cho lỗi chuyển kiểu, cách bổ sung một `FieldError` kiểm tra dữ liệu và cách bổ sung một global `ObjectError`. Ví dụ này không cần Jakarta Bean Validation provider vì ta đăng ký hai lỗi thủ công.

Tạo `pom.xml` tại thư mục project Maven:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-errors-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo file `src/main/java/demo/ErrorsDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public class ErrorsDemo {

    public static class Signup {
        private String username;
        private Integer age;

        public Signup() {}

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }

        public Integer getAge() { return age; }
        public void setAge(Integer age) {
            this.age = age;
        }
    }

    public static void main(String[] args) {
        Signup signup = new Signup();
        DataBinder binder = new DataBinder(signup, "signup");
        binder.setAllowedFields("username", "age");

        // Dữ liệu vào là chuỗi. "abc" không đổi thành Integer.
        binder.bind(new MutablePropertyValues(
                Map.of("username", "A", "age", "abc")));

        BindingResult errors = binder.getBindingResult();

        // Giả lập một lỗi validation của field và một lỗi toàn object.
        errors.rejectValue("username",
                "username.tooShort", "Tên đăng nhập quá ngắn");
        errors.reject("signup.blocked",
                "Không thể tạo tài khoản");

        FieldError ageError = errors.getFieldError("age");
        FieldError usernameError = errors.getFieldError("username");
        ObjectError globalError = errors.getGlobalError();

        System.out.println("total=" + errors.getErrorCount());
        System.out.println("global=" + errors.getGlobalErrorCount());
        System.out.println("field=" + errors.getFieldErrorCount());
        System.out.println("age.field=" + ageError.getField());
        System.out.println("age.rejected=" + ageError.getRejectedValue());
        System.out.println("age.bindingFailure="
                + ageError.isBindingFailure());
        System.out.println("username.rejected="
                + usernameError.getRejectedValue());
        System.out.println("username.bindingFailure="
                + usernameError.isBindingFailure());
        System.out.println("global.object="
                + globalError.getObjectName());
        System.out.println("global.defaultMessage="
                + globalError.getDefaultMessage());
    }
}
```

Chạy với Java 17+ và Maven được cài đặt:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.ErrorsDemo
```

Stdout do phương thức `main` tạo (không tính log của Maven):

```text
total=3
global=1
field=2
age.field=age
age.rejected=abc
age.bindingFailure=true
username.rejected=A
username.bindingFailure=false
global.object=signup
global.defaultMessage=Không thể tạo tài khoản
```

Giải thích:

1. `Map.of("username","A","age","abc")` chứa các **chuỗi** giống một input form. `DataBinder` gán `username=A` thành công.
2. `age` kiểu `Integer` không nhận `"abc"`, nên binder tạo `FieldError` với `isBindingFailure() == true` và rejected value là chuỗi `"abc"`.
3. `rejectValue("username",...)` thêm một lỗi field, nhưng đây là validation rule thủ công, nên `isBindingFailure() == false`.
4. `reject("signup.blocked",...)` thêm một global `ObjectError`. `getObjectName()` là `"signup"`, tên truyền cho `DataBinder`.
5. Tổng cộng ba lỗi gồm hai field errors và một global error. Việc `Map.of` không bảo đảm thứ tự phần tử không ảnh hưởng kết quả bởi ta truy vấn từng field theo tên, không dựa vào thứ tự danh sách.

Đoạn Java trên **biên dịch thành một class độc lập trong project Maven đã khai báo dependency**; không cần web server hay kết nối cơ sở dữ liệu.

## 6. Đọc lỗi đúng cách trong controller Spring MVC

Trong một controller nhận form, đặt `BindingResult` **liền sau** đối số được bind/validate:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

// Các method nằm trong class @Controller hoặc @RestController phù hợp.
@PostMapping("/signup")
public ResponseEntity<String> signup(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (form.getPassword() != null
            && form.getPassword().equals(form.getUsername())) {
        errors.reject("signup.passwordSameAsUsername",
                "Mật khẩu không được trùng tên đăng nhập");
    }

    if (errors.hasErrors()) {
        for (FieldError error : errors.getFieldErrors()) {
            // Có thể ánh xạ field + code + thông điệp sang UI/API.
            // Tránh log trực tiếp rejectedValue của field nhạy cảm.
        }
        for (ObjectError error : errors.getGlobalErrors()) {
            // Hiển thị lỗi toàn form một lần.
        }
        return ResponseEntity.badRequest().body("INVALID_SIGNUP");
    }

    return ResponseEntity.ok("ACCEPTED");
}
```

Đây là **đoạn method minh họa**, chưa phải file độc lập: ứng dụng cần định nghĩa `SignupForm` với các getter, validator/constraint tương ứng và có Spring MVC + Bean Validation provider. `@Valid` là `jakarta.validation.Valid` trong Spring Framework 6 / Spring Boot 3; `BindingResult` vẫn là interface của Spring. Với JSON `@RequestBody`, xử lý validation thường cũng dùng `BindingResult` hoặc exception handler tùy chữ ký.

Dù lỗi do framework tự ghi hoặc do `errors.reject(...)` bổ sung, chúng cùng xuất hiện trong `BindingResult`. Một response có thể chứa **nhiều** lỗi; controller nên trả toàn bộ danh sách phù hợp thay vì chỉ kiểm tra một lỗi đầu tiên nếu giao diện cần hướng dẫn người dùng sửa nhiều field.

### Khi không khai báo `BindingResult`

Trong MVC, validation thất bại ở tham số `@Valid @RequestBody`/`@Valid @ModelAttribute` thường được xử lý bằng exception (chẳng hạn `MethodArgumentNotValidException` trong các trường hợp tương ứng). Spring MVC hiện đại còn có **method validation** với `HandlerMethodValidationException` đối với chữ ký có ràng buộc trực tiếp trên tham số/phương thức. Không giả định mọi lỗi validation đều đi qua cùng một exception; nhưng khi có `BindingResult` tương ứng, việc đọc `getFieldErrors()` và `getGlobalErrors()` vẫn tuân theo mô hình này.

Đối với Spring WebFlux, có các kiểu exception/luồng reactive riêng, ví dụ `WebExchangeBindException`; không sao chép nguyên các handler MVC vào ứng dụng reactive.

## 7. Xây dựng response API và hiển thị lỗi cho người dùng

Một API có thể trả cấu trúc như sau (đây là **thiết kế ứng dụng**, không phải JSON mặc định được Spring cam kết):

```json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "age",
      "code": "typeMismatch",
      "message": "Tuổi phải là số hợp lệ"
    },
    {
      "field": "username",
      "code": "username.tooShort",
      "message": "Tên đăng nhập quá ngắn"
    }
  ],
  "globalErrors": [
    {
      "code": "signup.blocked",
      "message": "Không thể tạo tài khoản"
    }
  ]
}
```

Các trường `code` ngắn ở ví dụ trên có thể là mã nghiệp vụ do ứng dụng **chọn công bố**. Trong `ObjectError`/`FieldError`, `getCodes()` thường chứa các **message codes đã được Spring mở rộng** với tên object, field và kiểu dữ liệu. Vì thế, không thể mặc định `error.getCode()` bằng nguyên chuỗi đã đưa vào `errors.reject(...)`; khi cần contract API ổn định, ứng dụng nên định nghĩa bộ mã lỗi công khai riêng.

Gợi ý thực thi:

- UI form: hiển thị `FieldError` bên cạnh input có `field` tương ứng; hiển thị `ObjectError` trong vùng thông báo chung.
- API: trả thông điệp an toàn, có thể kèm `field` và mã lỗi ổn định. Việc trả nhiều lỗi giúp client sửa tất cả vấn đề trong một lần.
- Logging: có thể ghi tên field/mã lỗi; tránh đưa `rejectedValue` chứa mật khẩu, token, dữ liệu cá nhân hoặc payload quá lớn vào log/response.
- Bảo mật: ngay cả tên field cũng cần cân nhắc nếu nó để lộ cấu trúc nội bộ; dùng DTO công khai làm ranh giới giữa request và model nghiệp vụ.

**Không phụ thuộc bản thân `toString()` của `ObjectError`/`FieldError` làm định dạng phản hồi**: đây không phải contract JSON dành cho ứng dụng client, và có thể mang thông tin không nên công khai.

### Truy xuất phần tử trong `getAllErrors()`

```java
for (ObjectError error : errors.getAllErrors()) {
    if (error instanceof FieldError fieldError) {
        System.out.println("field=" + fieldError.getField());
    } else {
        System.out.println("global=" + error.getObjectName());
    }
}
```

Đoạn này cần đặt trong method có biến `errors` kiểu `Errors` hoặc `BindingResult`. Pattern matching `instanceof` được hỗ trợ từ Java 16 (dùng tốt với Java 17+). Trong ứng dụng xử lý input thật, code `System.out.println` chỉ phục vụ minh họa; tránh in giá trị nhạy cảm.

## 8. Message codes, `MessageSource` và bản địa hóa

`ObjectError` triển khai `MessageSourceResolvable` thông qua lớp cha, nên có thể đưa thẳng vào Spring `MessageSource` để tìm thông điệp theo `Locale`.

Giả sử code:

```java
errors.reject("order.invalidTotal", "Tổng đơn hàng không hợp lệ");
errors.rejectValue("quantity", "quantity.nonPositive",
                   "Số lượng phải lớn hơn 0");
```

Với `objectName="order"`, `field="quantity"` kiểu `Integer`, `DefaultMessageCodesResolver` **thông thường** tạo danh sách ưu tiên:

```text
Global error:
  order.invalidTotal.order
  order.invalidTotal

Field error:
  quantity.nonPositive.order.quantity
  quantity.nonPositive.quantity
  quantity.nonPositive.java.lang.Integer
  quantity.nonPositive
```

Thứ tự có thể bị ảnh hưởng bởi chiến lược `MessageCodesResolver` đã cấu hình, đặc biệt khi dùng prefix hoặc formatter khác. Với property thuộc collection/map, resolver còn có thể tạo mã ứng với cả chỉ số phần tử lẫn field tổng quát.

Ví dụ tài nguyên `src/main/resources/messages_vi.properties`:

```properties
order.invalidTotal.order=Tổng đơn hàng không nhất quán.
quantity.nonPositive.order.quantity=Số lượng phải lớn hơn 0.
typeMismatch.order.quantity=Số lượng phải là số.
```

Trong ứng dụng cấu hình message bundle thích hợp (ví dụ Spring Boot cấu hình `spring.messages.basename=messages`), có thể giải quyết thông điệp:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.validation.FieldError;

FieldError error = errors.getFieldError("quantity");
if (error != null) {
    String message = messageSource.getMessage(
            error, Locale.forLanguageTag("vi"));
    System.out.println(message);
}
```

Đoạn trên nằm trong method có sẵn `errors` và `messageSource` (do Spring inject) và không phải class độc lập. Spring tìm khóa thông điệp từ danh sách `error.getCodes()` theo thứ tự rồi dùng `defaultMessage` nếu không có khóa phù hợp. Việc giao diện hiển thị ngôn ngữ nào phải dựa vào locale phù hợp với request/người dùng, không hardcode `Locale` trong sản phẩm đa ngôn ngữ.

**Phân biệt `getDefaultMessage()` với thông điệp đã resolve.** `getDefaultMessage()` không tự truy cập file `messages_vi.properties`. Nếu hiển thị thẳng giá trị này, những khóa dịch cấu hình sẽ không được dùng.

## 9. Các tình huống thực tế dễ gây nhầm

### 9.1. Một field có hai lỗi

Nếu một field vừa cần `@NotBlank` vừa phải đúng định dạng, có thể xuất hiện nhiều thông báo trên cùng field. `getFieldError("email")` chỉ lấy lỗi đầu tiên. Dùng `getFieldErrors("email")` để nhận toàn bộ. Không giả định luôn có đúng một lỗi/field hoặc thứ tự thông báo luôn cố định giữa các provider/validator.

### 9.2. Lỗi chuyển kiểu và lỗi rule có ý nghĩa khác nhau

- Input `quantity=abc` và field `Integer quantity`: đó là lỗi binding; `isBindingFailure()` thường `true` và giá trị đã nhập được giữ trong `getRejectedValue()`.
- Input `quantity=-2`, có `@Min(1)`: chuyển kiểu thành công nhưng validation thất bại; `isBindingFailure()` thường `false`.
- Input `quantity=5` nhưng các field phối hợp sai: validator có thể ghi `ObjectError` nếu dùng `reject(...)` hoặc class-level Bean Validation constraint.

**Không nên chạy tiếp kiểm tra nghiệp vụ dựa vào field chưa bind hợp lệ** mà không kiểm tra lỗi hoặc xử lý null/giá trị mặc định.

### 9.3. Đường dẫn field lồng nhau

Với `address.zipCode`, `FieldError.getField()` có thể mang đường dẫn như `"address.zipCode"`. Trên form có collection, field có thể là `"lines[0].quantity"`. Tên này hữu ích để nối thông báo với input, nhưng cần map theo contract của UI, không ghép trực tiếp vào câu SQL hoặc biểu thức không kiểm soát.

Spring `Errors` còn có `pushNestedPath(...)`/`popNestedPath()` để validator con tạo lỗi theo ngữ cảnh. Nếu viết custom `Validator`, luôn khôi phục nested path trong `finally` để những lỗi tiếp theo không bị mang sai tiền tố.

### 9.4. Bean Validation không đồng nghĩa chỉ tạo `FieldError`

Các constraint đặt trên field/property thường dẫn tới field error. Constraint ở cấp class có thể dẫn tới global error; validator tự viết cũng có thể định tuyến violation của class-level constraint vào một property bằng cách cấu hình đường dẫn vi phạm. Vì thế nên dựa vào **API trả kết quả** (`getFieldErrors()`/`getGlobalErrors()`) khi trình bày, thay vì suy diễn tuyệt đối từ loại annotation.

### 9.5. `FieldError` không phải lúc nào cũng có rejected value dạng String

`getRejectedValue()` trả `Object`. Trong type mismatch của input form, nó có thể là chuỗi gốc; với Bean Validation, nó có thể là giá trị Java đã được chuyển kiểu (ví dụ `Integer -2`); cũng có thể là `null`. Code xử lý không nên ép kiểu thành `String` mà chưa kiểm tra.

### 9.6. `BindingResult` phải đứng đúng vị trí

Trong controller MVC:

```java
public String submit(
        @Valid @ModelAttribute("order") OrderForm form,
        BindingResult result) {
    // ...
}
```

Đây là thứ tự đúng cho đối tượng được validate. Đặt tham số không liên quan xen giữa có thể làm Spring không nhận `BindingResult` tương ứng. Ví dụ chỉ biểu diễn chữ ký method, cần đặt trong controller và định nghĩa `OrderForm` đầy đủ.

### 9.7. Global errors và field errors không phải HTTP status

`ObjectError` và `FieldError` **không tự quyết định** HTTP 400, 422 hay status khác. Chúng chứa thông tin validation/binding. Controller hoặc exception handler quyết định cách chuyển tập lỗi thành response theo contract của ứng dụng. Tương tự, `@Valid` không tự gắn ý nghĩa nghiệp vụ cho một error code công khai.

## 10. Kiểm thử và debug các lỗi

### Kiểm thử trực tiếp bằng `BindingResult`

Một unit test dùng Spring API có thể tạo `BeanPropertyBindingResult` để thử validator mà không cần khởi chạy web server:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;

OrderForm form = new OrderForm(); // DTO do project định nghĩa
BindingResult result =
        new BeanPropertyBindingResult(form, "order");

result.rejectValue("quantity", "quantity.positive",
                   "Số lượng phải lớn hơn 0");
result.reject("order.inconsistent",
              "Đơn hàng không nhất quán");

// Các assertion tương ứng có thể là:
// result.hasErrors() == true
// result.getErrorCount() == 2
// result.getFieldErrorCount() == 1
// result.getGlobalErrorCount() == 1
```

Đây là **snippet để đặt trong method test**, cần class `OrderForm` của project. Không cần `DataBinder` nếu chỉ muốn kiểm tra logic đăng ký lỗi; nếu muốn kiểm tra type mismatch, cần test đường `DataBinder.bind(...)` như ví dụ hoàn chỉnh ở phần 5.

### Checklist kiểm chứng

1. Với input sai kiểu, xem `getFieldError("quantity").isBindingFailure()` có đúng `true` và không mất giá trị nhập hay không.
2. Với lỗi constraint, xác minh `FieldError` đúng tên field và có codes/message thích hợp.
3. Với quy tắc liên trường, xác minh lỗi xuất hiện đúng nhóm `getGlobalErrors()` hoặc field cụ thể theo quyết định của validator.
4. Kiểm tra `getErrorCount() == getFieldErrorCount() + getGlobalErrorCount()` trên cùng `Errors`.
5. Kiểm tra trường có nhiều errors để UI không bỏ qua các bản ghi sau lỗi đầu.
6. Kiểm tra localization qua `MessageSource` bằng ít nhất hai `Locale` nếu ứng dụng đa ngôn ngữ.
7. Test đường MVC thật với request hợp lệ, field constraint thất bại, lỗi chuyển kiểu và global error; xác nhận status/JSON theo API của project.
8. Test log và response không công khai `getRejectedValue()` của password/token hoặc dữ liệu cần bảo vệ.

Trong debugger, quan sát `errors.getAllErrors()` và mở từng phần tử để thấy type thực tế (`FieldError` hay `ObjectError`), `codes`, `defaultMessage`, `field`, `rejectedValue` và `bindingFailure`. Không cần đoán nguồn lỗi chỉ từ thông báo hiển thị.

## 11. Lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `getAllErrors()` rồi xem mọi phần tử như global error | Field errors bị phân loại sai | Dùng riêng `getGlobalErrors()` và `getFieldErrors()` hoặc `instanceof` |
| Chỉ dùng `getFieldError()` | Mất các lỗi field còn lại | Dùng `getFieldErrors()` |
| Chỉ hiển thị `getDefaultMessage()` | Không ưu tiên bản dịch theo locale | Resolve qua `MessageSource` |
| Giả định `getRejectedValue()` luôn là `String` | Cast sai hoặc lộ dữ liệu | Xử lý như `Object`, lọc dữ liệu nhạy cảm |
| Hiểu `isBindingFailure() == false` là “không có lỗi” | Bỏ qua lỗi validation | Vẫn kiểm tra `hasErrors()` và danh sách lỗi |
| Không xử lý `getGlobalErrors()` | Người dùng không biết quy tắc toàn form bị vi phạm | Hiển thị lỗi chung ở vị trí dễ thấy |
| Đặt `BindingResult` không liền tham số được bind | Binding/validation không đi tới result như mong muốn | Sắp chữ ký đúng thứ tự |
| Coi mọi `ObjectError` là không có field | Bỏ qua subclass `FieldError` | Hiểu quan hệ kế thừa |
| Gửi nguyên error object qua API | Coupling vào cấu trúc Spring, nguy cơ lộ dữ liệu | Map sang DTO lỗi công khai với mã ổn định |
| Xử lý tất cả validation bằng `MethodArgumentNotValidException` | Bỏ sót đường method validation hoặc WebFlux | Phân loại theo chữ ký và stack thực tế |

## 12. Tóm lược kỹ thuật

- **`ObjectError`** mô tả một vấn đề đối với object; nó mang `objectName`, message codes, arguments và default message.
- **`FieldError`** kế thừa `ObjectError` và bổ sung `field`, `rejectedValue`, `bindingFailure`; nó dành cho trường cụ thể.
- **`BindingResult`/`Errors`** giữ và phân loại tập lỗi. `getGlobalErrors()` chỉ gồm lỗi toàn đối tượng; `getFieldErrors()` chỉ gồm lỗi theo trường; `getAllErrors()` gồm cả hai.
- **`reject(...)`** đăng ký global error; **`rejectValue(...)`** đăng ký field error; `DataBinder` còn có thể tự tạo field error khi binding thất bại.
- **`MessageSource`** giải quyết mã lỗi thành thông báo theo ngôn ngữ; `defaultMessage` chỉ là fallback, còn API công khai nên có mã lỗi riêng.
- Khi xử lý request thật, phải kiểm tra cả global và field errors, lưu ý dữ liệu nhạy cảm trong rejected values và kiểm thử cả binding lẫn validation.

## Tài liệu tham khảo chính thức

- [Spring Framework API — ObjectError](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework API — FieldError](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework API — Errors](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework API — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework API — DefaultMessageCodesResolver](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework Reference — Validation and Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring Framework Reference — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
