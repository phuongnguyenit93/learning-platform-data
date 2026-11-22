# Mô hình dữ liệu của BindingResult và tên đối tượng trong Spring

## 1. BindingResult giải quyết vấn đề gì?

Khi Spring nhận dữ liệu từ form, query parameter hay những giá trị request khác để gán vào một đối tượng Java, có hai kết quả cần giữ lại:

1. **Đối tượng đích** với những thuộc tính đã được gán thành công.
2. **Thông tin lỗi của lần binding/validation**: lỗi chung, lỗi ở từng thuộc tính, mã lỗi, giá trị bị từ chối và thông tin phục vụ hiển thị lại form.

`org.springframework.validation.BindingResult` là giao diện tập hợp các kết quả đó. Nó kế thừa `Errors`, đồng thời bổ sung việc truy cập target, tạo các thuộc tính model và thông tin binding cụ thể. Vì vậy `BindingResult` không phải một `Map<String, String>` đơn giản chứa thông báo lỗi; nó là **kết quả có cấu trúc gắn với một đối tượng được định danh bằng object name**.

Ví dụ, người dùng gửi một form đăng ký với:

~~~text
name=
age=abc
role=ADMIN
~~~

Giả sử đối tượng đích chỉ cho phép bind `name` và `age`, còn `age` có kiểu `Integer`:

- `name` có thể được gán thành chuỗi rỗng. Nếu ứng dụng kiểm tra “tên bắt buộc”, một `FieldError` được thêm vào sau đó.
- `age` không thể chuyển từ `"abc"` thành `Integer`, nên có thể sinh lỗi binding `typeMismatch`. Giá trị nhập sai vẫn cần được lưu dưới dạng thông tin lỗi để người dùng sửa.
- `role` nằm ngoài danh sách field được phép bind, nên bị **suppressed**. Đây không mặc nhiên là một `FieldError`.
- Nếu có quy tắc liên quan cả form, ví dụ hai giá trị không tương thích, ứng dụng có thể thêm một **global error** (`ObjectError`).

Mô hình khái niệm:

~~~text
DataBinder / WebDataBinder
├── target: RegistrationForm
├── objectName: "registrationForm"
└── BindingResult
    ├── objectName: "registrationForm"
    ├── target: cùng đối tượng RegistrationForm (khi đã tạo được)
    ├── globalErrors: List<ObjectError>
    ├── fieldErrors: List<FieldError>
    │   ├── field: "age", rejectedValue: "abc", bindingFailure: true
    │   └── field: "name", rejectedValue: "", bindingFailure: false
    ├── suppressedFields: ["role"]
    └── getModel()
        ├── "registrationForm" → đối tượng form
        └── "org.springframework.validation.BindingResult.registrationForm"
            → chính BindingResult
~~~

Tên `registrationForm` không phải trang trí: nó liên kết object, lỗi và form view. Hiểu tên đối tượng là điều kiện để đọc đúng dữ liệu của `BindingResult` và chẩn đoán lỗi Spring MVC.

## 2. Các lớp và giao diện trong mô hình lỗi

### 2.1. Errors và BindingResult

`Errors` là phần hợp đồng truy vấn và ghi nhận lỗi:

| Thành phần | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Định danh | `getObjectName()` | Tên logic của đối tượng đang được kiểm tra |
| Có lỗi không | `hasErrors()`, `getErrorCount()` | Tổng quan tình trạng lỗi |
| Lỗi cấp object | `reject(...)`, `getGlobalErrors()` | Lỗi không gắn riêng một field |
| Lỗi cấp field | `rejectValue(...)`, `getFieldErrors()` | Lỗi gắn với đường dẫn thuộc tính |
| Truy vấn một field | `getFieldError("age")`, `hasFieldErrors("age")` | Tìm lỗi của field cụ thể |
| Giá trị/kiểu | `getFieldValue("age")`, `getFieldType("age")` | Giá trị có thể gồm input bị reject; kiểu của field |
| Đường dẫn lồng nhau | `getNestedPath()`, `pushNestedPath(...)`, `popNestedPath()` | Hỗ trợ validator làm việc với object graph |

`BindingResult extends Errors`, bổ sung:

| API | Vai trò |
| --- | --- |
| `getTarget()` | Lấy đối tượng đích được bind; có thể `null` ở một số đường constructor binding chưa tạo được đối tượng |
| `getModel()` | Sinh map hai entry liên quan object và binding result để đưa vào view model |
| `MODEL_KEY_PREFIX` | Tiền tố chuẩn của khóa model dùng cho `BindingResult` |
| `getSuppressedFields()` | Danh sách tên field đã bị ngăn bind |
| `getRawFieldValue("field")` | Truy xuất giá trị thô từ target theo chiến lược binding tương ứng |
| `resolveMessageCodes(...)` | Tạo các mã lỗi ứng viên để tra thông báo |
| `getPropertyEditorRegistry()`, `findEditor(...)` | Truy cập thông tin editor nếu triển khai hỗ trợ |
| `addError(ObjectError)` | Thêm lỗi được tạo bởi chiến lược cộng tác |

Phần lớn ứng dụng dùng các API ở mức `Errors`/`BindingResult`, không cần phụ thuộc trực tiếp vào class triển khai.

Các triển khai phổ biến là `BeanPropertyBindingResult` cho thuộc tính JavaBeans (getter/setter), `DirectFieldBindingResult` cho truy cập trực tiếp field và `MapBindingResult` cho target dạng map. `DataBinder.getBindingResult()` cung cấp kết quả phù hợp với cách binder được thiết lập. Không nên tạo mới một `BindingResult` không liên quan đến binder rồi mong nó tự chứa các lỗi binding của request.

### 2.2. ObjectError và FieldError

`ObjectError` đại diện một lỗi của **toàn đối tượng**; ví dụ thời gian bắt đầu không thể lớn hơn thời gian kết thúc, hoặc mật khẩu và xác nhận mật khẩu không khớp. Nó cung cấp:

- `getObjectName()`: đối tượng chứa lỗi.
- `getCode()` và `getCodes()`: mã gốc/mã ưu tiên tra thông báo (xem chính xác Javadoc của phiên bản).
- `getArguments()` và `getDefaultMessage()`: tham số và thông báo dự phòng.
- Hợp đồng `MessageSourceResolvable` để `MessageSource` chọn thông báo được địa phương hóa.

`FieldError extends ObjectError` nên vẫn có object name, message codes và default message, đồng thời bổ sung:

- `getField()`: đường dẫn field như `age`, `address.city` hoặc `items[0].price`.
- `getRejectedValue()`: giá trị đã bị từ chối, thường cần để hiện lại input.
- `isBindingFailure()`: `true` khi lỗi được xem là **binding failure**, như không chuyển được kiểu; `false` cho lỗi validation được ghi qua `rejectValue`.

Ví dụ với object name `registrationForm`:

~~~text
ObjectError
  objectName = registrationForm
  code       = registration.invalid
  field      = (không có field)

FieldError
  objectName     = registrationForm
  field          = age
  rejectedValue  = abc
  bindingFailure = true
  code           = typeMismatch
~~~

`getAllErrors()` chứa cả lỗi global và lỗi field; `getGlobalErrors()` chỉ chứa lỗi global; `getFieldErrors()` chỉ chứa lỗi của các field. Một field có thể có nhiều lỗi, nên `getFieldError("age")` chỉ lấy **lỗi đầu tiên**; dùng `getFieldErrors("age")` nếu phải xử lý đầy đủ.

**Phân biệt ba tên:** `objectName` nói *đối tượng nào*, `field` nói *thuộc tính nào*, còn `errorCode` nói *loại lỗi nào*. Không sử dụng chúng thay thế cho nhau.

## 3. Object name được xác định như thế nào?

### 3.1. Với DataBinder thuần

Bạn có thể chỉ định tên rõ ràng trong constructor:

~~~java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
BindingResult result = binder.getBindingResult();

System.out.println(result.getObjectName()); // registrationForm
~~~

Đây là đoạn mã minh họa đặt trong một chương trình có các import `DataBinder`, `BindingResult` và class `RegistrationForm`. Đối tượng đích là `form`, còn tên logic để bind là chuỗi `"registrationForm"`. Tên này không bắt buộc trùng tên class (`RegistrationForm`) hoặc tên biến Java (`form`).

Nếu gọi `new DataBinder(form)` không truyền tên, `DataBinder.DEFAULT_OBJECT_NAME` mặc định là `"target"`. Vì vậy không được giả định rằng mọi `DataBinder` mặc định tự suy ra tên `registrationForm` từ class Java.

### 3.2. Với @ModelAttribute trong Spring MVC

Ví dụ chữ ký controller:

~~~java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "registration/form";
    }
    return "redirect:/registered";
}
~~~

Đây là đoạn tích hợp bên trong một `@Controller` dùng Spring MVC, không phải file Java độc lập. `@ModelAttribute("registrationForm")` xác định tên model attribute là **registrationForm**, và `bindingResult.getObjectName()` cho object tương ứng cũng dùng tên ấy.

Nếu không chỉ định tên:

~~~java
public String register(@ModelAttribute RegistrationForm form,
                       BindingResult bindingResult) {
    // ...
}
~~~

Spring MVC áp dụng quy ước suy ra tên model attribute từ kiểu/thông tin tham số phù hợp; đối với một class thông thường như `RegistrationForm`, tên thường là `registrationForm`. Nên **viết tên tường minh** khi form view hoặc contract code phụ thuộc tên cố định, thay vì dựa vào một phép suy tên mặc định trong mọi trường hợp.

Điểm kiểm tra quan trọng:

- `@ModelAttribute("registrationForm")` là **tên của object**; `@ModelAttribute("name")` sẽ chỉ đến một thuộc tính khác tên, không phải field `name` bên trong `registrationForm`.
- Chuỗi trong `getObjectName()` liên quan đến tên model attribute mà view dùng.
- Khai báo `BindingResult` **ngay sau** tham số `@ModelAttribute` cần xử lý. Một `BindingResult` ở sau tham số khác có thể không còn được MVC gắn với object mong muốn.
- Nếu có hai form DTO trong cùng controller/model, hãy dùng **hai tên model attribute riêng** để lỗi và trường nhập không va chạm.
- Rename `"registrationForm"` cần cập nhật cả template, key tra lỗi, và những handler thao tác model dựa vào tên đó.

### 3.3. Tên đối tượng có thay đổi khi kiểm tra nested field?

Không. Ví dụ với `registrationForm.address.city`:

- `getObjectName()` vẫn là `"registrationForm"`.
- `FieldError.getField()` là `"address.city"` nếu lỗi nằm ở field này.
- `getNestedPath()` có thể là `"address."` khi validator đang ở ngữ cảnh nested path, nhưng nó không thay object name.
- Mã thông báo có thể kết hợp cả tên đối tượng lẫn full field path.

Nhờ sự phân biệt này, một `BindingResult` có thể gom các lỗi từ nhiều cấp của object graph mà vẫn giữ một định danh object ổn định.

## 4. Hai khóa model do BindingResult.getModel() cung cấp

### 4.1. Công thức đặt tên chính xác

`BindingResult.MODEL_KEY_PREFIX` có giá trị:

~~~text
org.springframework.validation.BindingResult.
~~~

Cho `objectName = "registrationForm"`, `bindingResult.getModel()` trả một `Map<String, Object>` có hai entry chính:

| Khóa model | Giá trị |
| --- | --- |
| `registrationForm` | Target `RegistrationForm` |
| `org.springframework.validation.BindingResult.registrationForm` | Chính đối tượng `BindingResult` |

Công thức:

~~~java
String objectName = result.getObjectName();
String bindingKey = BindingResult.MODEL_KEY_PREFIX + objectName;
Map<String, Object> attrs = result.getModel();

Object target = attrs.get(objectName);
BindingResult errors = (BindingResult) attrs.get(bindingKey);
~~~

Đây là ví dụ áp dụng cho `BindingResult` đã được tạo; thay `result` bằng biến thực trong phương thức.

Không dùng `"BindingResult.registrationForm"`, `"bindingResult"` hoặc tên class của target để tra một cách tùy ý. Chỉ tiền tố chuẩn ghép với **object name thực tế** mới là khóa của binding result trong model.

Đối với hai đối tượng khác nhau:

~~~text
profileForm
org.springframework.validation.BindingResult.profileForm

shippingForm
org.springframework.validation.BindingResult.shippingForm
~~~

Mỗi cặp khóa nói về một target/binding-result khác nhau. Nếu vô tình dùng cùng object name, các map entry có thể ghi đè và template/handler dễ hiển thị nhầm lỗi.

### 4.2. getModel() tạo map mới cho mỗi lần gọi

Javadoc xác định `getModel()` tạo một map mới **mỗi khi gọi**. Vì thế:

~~~java
Map<String, Object> first = result.getModel();
first.put("additionalAttribute", "value");

Map<String, Object> second = result.getModel();
System.out.println(second.containsKey("additionalAttribute")); // false
~~~

Thêm entry vào map trả về chỉ thay đổi **map đó**; nó không thay state của `BindingResult` và không tự xuất hiện trong map của lần gọi tiếp theo.

Khi tự dựng một `ModelAndView`, nếu cần đưa cả target và errors vào view, phải thêm những entry này vào model đang sử dụng. Ví dụ logic:

~~~java
modelAndView.addAllObjects(bindingResult.getModel());
~~~

Ở đây `modelAndView` là một `ModelAndView` đã được tạo. Trong controller annotation-based thông thường, Spring MVC quản lý việc liên kết model attribute và `BindingResult`; không cần gọi `getModel()` thủ công mỗi lần trả view. Việc tự thêm một lỗi với sai tên key có thể khiến view không tìm được thông tin cần thiết.

### 4.3. Không nhầm Model và BindingResult

- `Model` hoặc `ModelMap` thuộc Spring MVC: tập hợp attributes cho view.
- `BindingResult`: chi tiết errors và binding của **một target**.
- `bindingResult.getModel()`: một cách **đóng gói hai entry liên quan** để có thể đưa vào model.
- Mỗi `BindingResult` có object name riêng; một `Model` MVC có thể chứa nhiều object và nhiều `BindingResult`.

Nói cách khác, `BindingResult` có thể sản xuất một phần model, nhưng nó không thay thế `Model` của cả request.

## 5. Một bài chạy độc lập: quan sát mô hình dữ liệu

Ví dụ này dùng **Java 17+** và Spring Framework **6.2.12** qua Gradle. Nó không cần Spring Boot, HTTP server hoặc Jakarta Bean Validation provider. Validation chủ động qua `rejectValue`/`reject` để bạn nhìn thấy rõ khác biệt giữa lỗi type mismatch, lỗi nghiệp vụ và field bị chặn. Những lệnh bên dưới phù hợp máy có JDK 17+ và Gradle được cài.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'binding-result-model-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'BindingResultModelDemo'
}
~~~

Tạo `src/main/java/BindingResultModelDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class BindingResultModelDemo {

    public static class RegistrationForm {
        private String name;
        private Integer age;
        private String role;

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

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setAllowedFields("name", "age");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "");
        input.add("age", "abc");
        input.add("role", "ADMIN");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        result.rejectValue("name", "required", null,
                "Tên không được để trống");
        result.reject("registration.invalid", null,
                "Biểu mẫu chưa hợp lệ");

        String key = BindingResult.MODEL_KEY_PREFIX
                + result.getObjectName();
        Map<String, Object> model = result.getModel();

        FieldError ageError = result.getFieldError("age");
        FieldError nameError = result.getFieldError("name");

        System.out.println("objectName=" + result.getObjectName());
        System.out.println("targetSame=" + (result.getTarget() == form));
        System.out.println("bindingKey=" + key);
        System.out.println("modelTarget=" + (model.get("registrationForm") == form));
        System.out.println("modelErrors=" + (model.get(key) == result));
        System.out.println("freshMap=" + (result.getModel() != model));

        System.out.println("fieldErrors=" + result.getFieldErrorCount());
        System.out.println("globalErrors=" + result.getGlobalErrorCount());
        System.out.println("allErrors=" + result.getErrorCount());
        System.out.println("ageField=" + ageError.getField());
        System.out.println("ageRejected=" + ageError.getRejectedValue());
        System.out.println("ageFieldValue=" + result.getFieldValue("age"));
        System.out.println("ageBindingFailure=" + ageError.isBindingFailure());
        System.out.println("nameBindingFailure=" + nameError.isBindingFailure());
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));
        System.out.println("ageOnTarget=" + form.getAge());
        System.out.println("roleOnTarget=" + form.getRole());
    }
}
~~~

Chạy bằng:

~~~bash
gradle -q run
~~~

Nếu dự án đã có Gradle Wrapper thì dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows. Lệnh sẽ tải Spring Context và các dependency cần thiết từ Maven Central khi môi trường có mạng.

**Stdout mong đợi** với dependency và đầu vào đúng như trên:

~~~text
objectName=registrationForm
targetSame=true
bindingKey=org.springframework.validation.BindingResult.registrationForm
modelTarget=true
modelErrors=true
freshMap=true
fieldErrors=2
globalErrors=1
allErrors=3
ageField=age
ageRejected=abc
ageFieldValue=abc
ageBindingFailure=true
nameBindingFailure=false
suppressed=[role]
ageOnTarget=null
roleOnTarget=null
~~~

Cách đọc từng nhóm kết quả:

1. `objectName=registrationForm` vì constructor của `DataBinder` nhận tên này; `targetSame=true` xác nhận binder gắn với chính object `form`.
2. `bindingKey` đúng bằng `BindingResult.MODEL_KEY_PREFIX + objectName`. Hai giá trị `modelTarget=true` và `modelErrors=true` xác nhận map dùng chung object và result đã có.
3. `freshMap=true` không có nghĩa target hoặc lỗi bị sao chép. Chỉ **đối tượng Map** là một instance mới mỗi khi gọi `getModel()`.
4. `fieldErrors=2` gồm type mismatch của `age` và lỗi `required` được thêm cho `name`; `globalErrors=1` là lỗi chung được thêm qua `reject`. `allErrors=3` là tổng.
5. `ageRejected=abc`, `ageFieldValue=abc` cho thấy input bị reject vẫn có thể truy xuất để hiển thị lại. Trong khi đó `ageOnTarget=null` vì phép chuyển sang `Integer` thất bại.
6. `ageBindingFailure=true` phân biệt lỗi chuyển kiểu với `nameBindingFailure=false`: lỗi `name` do ứng dụng thêm thông qua validation-style `rejectValue`.
7. `role` không nằm trong whitelist của `setAllowedFields` nên xuất hiện ở `suppressed=[role]`; target vẫn có `role=null`. **Field bị suppress không tự biến thành FieldError**.

Ví dụ không dùng `@Valid` hay constraint annotations; mục tiêu là khám phá bản thân `BindingResult`. Trong ứng dụng thực tế, validator hoặc Jakarta Bean Validation provider có thể thêm các lỗi khác theo cùng mô hình. Nếu bạn chỉnh dữ liệu hoặc cấu hình trong ví dụ, stdout có thể thay đổi; không coi đây là quy luật cố định cho mọi binder.

## 6. Giá trị đối tượng và giá trị người dùng nhập sai

Một sai lầm phổ biến là chỉ đọc field trên target và bỏ qua giá trị được ghi trong lỗi.

Giả sử property `age` là `Integer` nhưng request gửi `age=abc`. Sau binding thất bại:

~~~text
form.getAge()                    → null
result.getFieldError("age")      → FieldError tồn tại
error.getRejectedValue()        → "abc"
result.getFieldValue("age")      → "abc" (theo BindingResult của ví dụ)
error.isBindingFailure()        → true
~~~

Nếu controller trả form view sau lỗi, chỉ render `form.age` sẽ không phản ánh chính xác input người dùng vừa nhập. Cơ chế binding của view có thể dùng rejected value trong `BindingResult` để giữ lại dữ liệu nhập và cho phép chỉnh sửa.

Các cách đọc khác nhau:

| Nhu cầu | API | Điều cần biết |
| --- | --- | --- |
| Giá trị đã có trên object | `getTarget()` rồi truy cập field | Có thể chưa được gán nếu conversion thất bại |
| Giá trị field phục vụ binding/form | `getFieldValue("age")` | Có thể trả rejected value, không nhất thiết là kiểu Java đích |
| Giá trị lỗi cụ thể | `getFieldError("age").getRejectedValue()` | Cần null-check nếu field không có lỗi |
| Kiểu khai báo | `getFieldType("age")` | Có thể suy ra kiểu ngay cả khi giá trị target là null |
| Giá trị thô từ target | `getRawFieldValue("age")` | Phụ thuộc triển khai; không dùng thay cho rejected input |
| Danh sách lỗi tại field | `getFieldErrors("age")` | Có thể chứa nhiều lỗi cho một field |

Không gán ngược rejected value vào target chỉ để “giữ form”; làm vậy dễ phá ràng buộc kiểu. Đưa lỗi và value phù hợp vào view qua API của Spring. Khi xuất log hay API error response, cân nhắc che dữ liệu nhạy cảm như mật khẩu, token và thông tin cá nhân thay vì in nguyên `getRejectedValue()`.

## 7. Object name, field path và message codes

### 7.1. Một error code không phải một dòng thông báo

`rejectValue("age", "typeMismatch", ...)` (hoặc lỗi conversion sinh tự động) cung cấp **mã lỗi logic**. Spring có thể mở rộng nó thành các mã cụ thể hơn nhờ `MessageCodesResolver`.

Ví dụ với:

~~~text
objectName = registrationForm
field      = age
fieldType  = java.lang.Integer
errorCode  = typeMismatch
~~~

`DefaultMessageCodesResolver` thường xây danh sách mã ứng viên theo thứ tự từ cụ thể đến tổng quát:

~~~text
typeMismatch.registrationForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

Thực tế danh sách phụ thuộc `MessageCodesResolver` được cấu hình, kiểu field mà Spring xác định và khả năng là property dạng list/map/nested. Với field primitive `int`, phần tên kiểu có thể là `int`. Đừng giả định tất cả hệ thống luôn trả đúng bốn chuỗi trong ví dụ này.

Một `ObjectError` với mã `registration.invalid` và object name `registrationForm` có thể có các mã ứng viên:

~~~text
registration.invalid.registrationForm
registration.invalid
~~~

Cấu trúc này cho phép chọn thông báo ở từng mức:

- Riêng một field trên một form: `typeMismatch.registrationForm.age`.
- Chung cho một field bất kể form: `typeMismatch.age`.
- Chung cho một kiểu dữ liệu: `typeMismatch.java.lang.Integer`.
- Lỗi chung cho mọi form: `typeMismatch`.

### 7.2. MessageSource chọn thông báo

Ví dụ file `messages_vi.properties` trong ứng dụng có cấu hình `MessageSource` tương ứng:

~~~properties
typeMismatch.registrationForm.age=Tuổi phải là một số nguyên.
typeMismatch.age=Giá trị tuổi không hợp lệ.
required.registrationForm.name=Vui lòng nhập tên.
registration.invalid.registrationForm=Thông tin đăng ký chưa phù hợp.
~~~

`MessageSource` thử các codes để lấy thông báo theo `Locale`, sử dụng arguments và fallback khi cần. `getDefaultMessage()` là giá trị dự phòng, không phải bằng chứng Spring đã tìm và áp dụng đúng ngôn ngữ hiển thị. Nếu cần tự resolve một lỗi trong backend:

~~~java
String message = messageSource.getMessage(error, locale);
~~~

Đoạn này giả định đã có `MessageSource messageSource`, `ObjectError error` và `Locale locale`. `ObjectError` triển khai `MessageSourceResolvable`. Thông báo cuối cùng còn phụ thuộc cấu hình message bundles.

Khi đổi `objectName` từ `registrationForm` thành `signupForm`, mã cụ thể nhất cũng thay đổi thành `typeMismatch.signupForm.age`; file i18n hoặc test assertion dựa vào tên cũ có thể không còn khớp. Đó là một lý do quan trọng để xem object name như một phần của hợp đồng giữa controller và view.

### 7.3. Nested fields và chỉ mục collection

Với DTO có thuộc tính lồng nhau:

~~~text
registrationForm.address.city
registrationForm.contacts[0].email
registrationForm.items[2].quantity
~~~

Field error thường lưu tên tương đối với root object, ví dụ `address.city` hoặc `items[2].quantity`, còn object name vẫn `registrationForm`. `Errors` có API nested path để validator thao tác với các field con. Khi tạo error code, `DefaultMessageCodesResolver` có thể sinh cả mã có index cụ thể và mã tổng quát hơn cho collection.

Ví dụ:

~~~text
typeMismatch.registrationForm.items[2].quantity
typeMismatch.registrationForm.items.quantity
typeMismatch.items[2].quantity
typeMismatch.items.quantity
typeMismatch.quantity
...
typeMismatch
~~~

Dấu `...` thể hiện các mã tùy kiểu field và cấu hình resolver, không phải một mã lỗi thực tế. Để biết chính xác, kiểm tra `fieldError.getCodes()` trên phiên bản/framework configuration đang chạy.

Một vấn đề khác là thuộc tính nested chưa được khởi tạo. Binder có thể cấu hình tự tạo đường dẫn nested trong những trường hợp hỗ trợ; cũng có thể sinh lỗi truy cập thuộc tính. Đừng coi mọi nested path người dùng gửi đều hợp lệ hoặc được bind thành công. DTO và whitelist cần giới hạn các trường được phép nhận từ bên ngoài.

## 8. BindingResult trong vòng đời của Spring MVC

### 8.1. Chuỗi xử lý khi nhận form

Với controller có `@ModelAttribute("registrationForm")`:

~~~text
HTTP form/query parameters
       |
       v
Spring MVC argument resolver
       |
       v
Tìm hoặc tạo model attribute "registrationForm"
       |
       v
WebDataBinder chuyển kiểu và gán thuộc tính
       |
       +--> lỗi binding: FieldError (ví dụ typeMismatch)
       |
       v
Validator / Jakarta Bean Validation khi được kích hoạt
       |
       +--> lỗi field: FieldError
       +--> lỗi toàn object: ObjectError
       |
       v
BindingResult gắn với registrationForm
       |
       +--> Controller đọc qua tham số BindingResult liền kề
       |
       +--> View model có registrationForm và BindingResult.registrationForm
       |
       v
Render lại form nếu có lỗi, hoặc tiếp tục nghiệp vụ
~~~

Mỗi request/binding thông thường có binder và kết quả tương ứng. `BindingResult` không nên được giữ dưới dạng field mutable của singleton controller, vì dữ liệu lỗi phải gắn với **request và target cụ thể**.

### 8.2. Một controller trả HTML form

Ví dụ tích hợp trong Spring MVC 6.x/7.x với Jakarta Validation provider; những file này thuộc cùng package `com.example.registration`. Đây là thành phần của **ứng dụng web đã có Spring MVC và view engine**, không phải chương trình standalone có `main`.

File `RegistrationForm.java`:

~~~java
package com.example.registration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
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
~~~

File `RegistrationController.java`:

~~~java
package com.example.registration;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class RegistrationController {

    @GetMapping("/registrations/new")
    public String newForm(Model model) {
        model.addAttribute("registrationForm", new RegistrationForm());
        return "registration/form";
    }

    @PostMapping("/registrations")
    public String submit(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "registration/form";
        }

        return "redirect:/registrations/success";
    }
}
~~~

Để form dùng được cần cấu hình view engine phù hợp (ví dụ Thymeleaf) và có đường dẫn `/registrations/success` nếu muốn redirect thật sự thành công. `@Valid` yêu cầu Jakarta Bean Validation API cùng provider được ứng dụng cấu hình; chỉ thêm annotation mà thiếu provider có thể không thực hiện constraint như mong đợi.

Một đoạn template Thymeleaf tương ứng (ví dụ `templates/registration/form.html`) minh họa tên object và hiển thị lỗi:

~~~html
<form method="post" th:action="@{/registrations}"
      th:object="${registrationForm}">
    <label>Tên
        <input type="text" th:field="*{name}">
    </label>
    <p th:if="${#fields.hasErrors('name')}" th:errors="*{name}"></p>

    <label>Tuổi
        <input type="text" th:field="*{age}">
    </label>
    <p th:if="${#fields.hasErrors('age')}" th:errors="*{age}"></p>
    <button type="submit">Gửi</button>
</form>
~~~

Template là **một đoạn HTML tích hợp**, không phải toàn bộ trang HTML. Trong cấu hình Spring Security có CSRF, cần đảm bảo form có CSRF token theo cơ chế tích hợp đã bật. Trong template này, `th:object="${registrationForm}"` trỏ tới tên model attribute; `*{age}` chỉ tới field của target. BindingResult cho chính model attribute ấy giúp cơ chế field expression tìm giá trị/lỗi tương ứng.

Trường hợp gửi `name=` và `age=abc`:

- `name` là chuỗi rỗng: ràng buộc `@NotBlank` có thể tạo lỗi cho `name`.
- `age=abc`: conversion sang `Integer` thất bại và có thể tạo lỗi `typeMismatch` cho `age`.
- Nếu không có cấu hình đặc biệt, MVC trả lại view sau khi controller kiểm tra `result.hasErrors()`.
- Cả form và error state gắn với tên `registrationForm` để view hiển thị lỗi và giá trị nhập.

Đây là ví dụ **không khai báo thêm constraint trực tiếp trên tham số method** ngoài `@Valid` trên DTO, để làm rõ cơ chế `BindingResult` cạnh `@ModelAttribute`. Trong những chữ ký áp dụng method validation, việc phát sinh exception có thể theo nhánh khác; xem phần lỗi phổ biến phía dưới.

### 8.3. BindingResult phải đứng ngay sau tham số liên quan

Đúng:

~~~java
public String submit(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result,
        Model model) {
    // result ứng với registrationForm
    return "registration/form";
}
~~~

Sai về quan hệ liền kề:

~~~java
public String submit(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        Model model,
        BindingResult result) {
    // MVC không thể mặc nhiên gán result cho form qua vị trí này
    return "registration/form";
}
~~~

Hai đoạn trên là **chữ ký minh họa**, đặt trong controller có đầy đủ import/annotation handler phù hợp. Tham số `Errors`/`BindingResult` cần đứng ngay sau **model attribute hoặc argument được hỗ trợ tương ứng**. Không dùng một `BindingResult` bất kỳ ở cuối phương thức để gom tất cả lỗi của mọi parameter.

Nếu muốn xử lý validation cho hai đối tượng cùng lúc, cần xem cơ chế method argument resolution và điều kiện validation trên từng argument; không cố ghép lỗi của hai DTO khác nhau vào cùng một `BindingResult`.

## 9. Lỗi binding, lỗi validation và field bị suppress

Cả ba đều liên quan đầu vào không mong muốn, nhưng **khác về dữ liệu và cách xử lý**.

| Tình huống | Biểu diễn thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `age=abc` nhưng target là `Integer` | `FieldError`, mã `typeMismatch`, `bindingFailure=true` | `getFieldError("age")` và `isBindingFailure()` |
| `age=15` nhưng ràng buộc `@Min(18)` | `FieldError` của validation, thường `bindingFailure=false` | `getFieldErrors("age")`, mã constraint |
| `name=` nhưng `@NotBlank` | `FieldError` của validation | `getFieldErrors("name")` |
| Hai thuộc tính mâu thuẫn | `ObjectError` / global error | `getGlobalErrors()` |
| `role=ADMIN` nhưng `setAllowedFields("name","age")` | Field bị suppress, thường không tự tạo `FieldError` | `getSuppressedFields()` |
| Form không được tạo thành công bằng constructor binding | Có thể không có target đã khởi tạo; errors/field values vẫn được ghi | `getTarget()` có thể null, kiểm tra errors |

**Conversion và validation là các giai đoạn khác nhau.** Một giá trị không thể chuyển sang `Integer` chưa chắc đã sẵn sàng để kiểm tra `@Min(18)`; không coi `typeMismatch` là cùng loại lỗi với `Min`.

Với suppressed fields, đây là một cơ chế giới hạn quyền property binding. Nếu ứng dụng cần xem một request chứa field cấm là vi phạm nghiệp vụ/bảo mật, hãy xử lý hoặc audit theo chính sách riêng. `BindingResult.getSuppressedFields()` là tín hiệu hữu ích, nhưng bản thân nó không bảo đảm HTTP status 400 hay sinh validation message.

## 10. Đọc lỗi đúng cách trong mã ứng dụng

### 10.1. API truy vấn có ý nghĩa khác nhau

~~~java
boolean anyError = result.hasErrors();
boolean anyFieldError = result.hasFieldErrors();
boolean ageHasError = result.hasFieldErrors("age");

int allCount = result.getErrorCount();
int globalCount = result.getGlobalErrorCount();
int fieldCount = result.getFieldErrorCount();

List<ObjectError> global = result.getGlobalErrors();
List<FieldError> ageErrors = result.getFieldErrors("age");
~~~

Đây là snippet minh họa với `BindingResult result` và import `java.util.List`, `ObjectError`, `FieldError`. Nên dùng các method tương ứng với nhu cầu. `hasErrors()` có thể `true` chỉ vì global error, dù `getFieldError("age")` trả `null`.

Khi xây thông báo UI, cần kiểm tra null:

~~~java
FieldError ageError = result.getFieldError("age");
if (ageError != null) {
    String field = ageError.getField();
    Object rejectedValue = ageError.getRejectedValue();
    // Đưa field/code/message hợp lệ vào view.
}
~~~

`getRejectedValue()` là `Object` và có thể `null`; nó cũng có thể chứa thông tin cá nhân hoặc input không an toàn. Không ép kiểu trực tiếp sang `Integer` khi lỗi do không parse được. Việc escape HTML nên do template engine thực hiện; không đưa thẳng chuỗi thô vào HTML hay log.

### 10.2. Khi nhận nhiều lỗi cùng field

Ví dụ field `password` vừa thiếu độ dài vừa thiếu chữ số có thể được nhiều validator ghi lỗi, tùy cách triển khai. Khi đó:

- `result.getFieldError("password")` cho lỗi **đầu tiên**.
- `result.getFieldErrors("password")` trả tất cả lỗi của field đó.
- `result.getFieldErrorCount("password")` là số lỗi field tương ứng.
- `getDefaultMessage()` có thể thiếu, hoặc chỉ là fallback.
- `getCodes()` cho phép resolver tìm message localization theo thứ tự ưu tiên.

Đừng chỉ lấy lỗi đầu tiên rồi tuyên bố request không có lỗi nào khác. Với API JSON, nên xây cấu trúc trả lỗi ổn định có `field`, mã public và message đã được resolve; tránh xuất toàn bộ thông tin nội bộ của error object một cách máy móc.

### 10.3. Tạo lỗi field và lỗi object

Khi kiểm tra bằng Spring `Validator` thuần:

~~~java
@Override
public void validate(Object target, Errors errors) {
    RegistrationForm form = (RegistrationForm) target;

    if (form.getName() == null || form.getName().isBlank()) {
        errors.rejectValue("name", "required", null,
                "Tên không được để trống");
    }

    if (form.getAge() != null && form.getAge() < 18) {
        errors.rejectValue("age", "tooYoung", null,
                "Tuổi phải từ 18");
    }

    // Nếu cần báo lỗi toàn object:
    // errors.reject("registration.invalid", null, "Form không hợp lệ");
}
~~~

Đây là **phương thức bên trong một lớp implements org.springframework.validation.Validator**; code giả định class `RegistrationForm` như ví dụ trên và method `supports(Class<?>)` đã được triển khai. Hai lời gọi `rejectValue` ghi lỗi theo field, còn `reject` ghi lỗi global. Đừng đồng nhất Spring `Validator` với `jakarta.validation.Validator`: chúng là hai API khác package.

Đối với một đối tượng chứa field lồng nhau, tránh tự nối nhầm object name vào field trong `rejectValue`. Thông thường truyền path tương đối như `"address.city"`, và để `Errors`/resolver kết hợp với object name.

## 11. Khi nào đối tượng có thể không có target?

Trong binding thông qua property setter, target thường đã được tạo. Nhưng với **constructor binding**, binder có thể phải xây target từ các giá trị input. Nếu constructor không thể tạo được đối tượng do lỗi argument, `BindingResult.getTarget()` có thể là `null`, trong khi error information và các giá trị field đã ghi vẫn được giữ để chẩn đoán.

Điều này có hai hệ quả:

1. Không viết code xử lý lỗi theo giả định `result.getTarget()` luôn có instance sẵn sàng cho mọi trường hợp.
2. Nếu chỉ cần trả thông báo lỗi, ưu tiên `BindingResult`, `FieldError` và các field values được ghi lại, thay vì truy cập getter của target chưa chắc tồn tại.

`BindingResult.recordFieldValue(...)` hỗ trợ chiến lược constructor binding ghi các giá trị khi đối tượng chưa được dựng; đây thường là API dành cho cơ chế binder, không phải method mà controller cần tự gọi trong luồng chuẩn.

Trên các phiên bản Spring khác nhau, cơ chế constructor binding và luồng tạo target có các chi tiết khác nhau; hãy đọc Javadoc và thử trên phiên bản Spring của ứng dụng, đặc biệt khi nâng cấp major/minor. Điều bất biến là **object name và error state không phụ thuộc việc controller luôn có một target hoàn chỉnh**.

## 12. Xử lý lỗi trong Spring MVC không chỉ có BindingResult

`BindingResult` là mô hình lỗi của binding/validation tại một argument, nhưng Spring MVC có nhiều đường input:

- `@ModelAttribute` nhận form/query và đi qua binder. Đặt `BindingResult` ngay sau parameter cho phép controller đọc các lỗi được hỗ trợ trong luồng này.
- `@RequestBody` thường được đọc bằng HTTP message converter (ví dụ Jackson JSON). JSON không parse được có thể ném lỗi **trước** khi có đối tượng/`BindingResult` như trong ví dụ form.
- `@Valid @RequestBody` có thể sinh `MethodArgumentNotValidException` khi validation ở mức argument thất bại và không có `Errors`/`BindingResult` phù hợp.
- Với constraint trực tiếp trên tham số method controller (như `@RequestParam @Min(1) int page`), Spring MVC 6.1+ có **method validation tích hợp** và có thể ném `HandlerMethodValidationException`.
- `@Validated` trên class controller có thể đưa method validation qua AOP thay vì con đường MVC tích hợp. Không suy ra một exception class duy nhất cho mọi lỗi.
- `BindingResult` không phải HTTP response tự động. Status/body khi xảy ra lỗi còn phụ thuộc argument resolver, exception handlers và cách controller xây response.

Nếu mục tiêu là hiển thị lại form HTML, `BindingResult` liền kề với `@ModelAttribute` rất phù hợp. Nếu mục tiêu là REST API JSON, cần xác định trước lỗi xảy ra tại **JSON parsing**, **data binding**, **Bean Validation** hay **method validation**, rồi xử lý đúng loại ở `@ControllerAdvice` hoặc cơ chế tương ứng.

## 13. Hai form cùng tên và các vấn đề trong template

Giả sử trang checkout có hai đối tượng:

~~~text
billingForm
shippingForm
~~~

Model đúng về mặt ý tưởng:

~~~text
billingForm                                  → BillingForm
org.springframework.validation.BindingResult.billingForm
                                             → BindingResult của BillingForm

shippingForm                                 → ShippingForm
org.springframework.validation.BindingResult.shippingForm
                                             → BindingResult của ShippingForm
~~~

Nếu controller đổi cả hai thành `@ModelAttribute("form")`, những key cùng tên có thể cạnh tranh trong model. Khi biểu mẫu hiển thị sai lỗi, kiểm tra lần lượt:

1. Đối tượng controller thêm vào model có tên gì?
2. `result.getObjectName()` ở handler tương ứng là gì?
3. Template `th:object`/JSP `modelAttribute` đang trỏ tới object nào?
4. Key `BindingResult.MODEL_KEY_PREFIX + objectName` có được giữ đúng trong model không?
5. Có code nào tạo `ModelAndView` hoặc ghi đè model attribute bằng object mới sau binding không?
6. Có dùng đúng result liền kề với argument cần kiểm tra không?

Một lỗi hay gặp là tạo `new RegistrationForm()` rồi `model.addAttribute("registrationForm", ...)` **lại** trong nhánh có lỗi, thay thế target chứa dữ liệu người dùng vừa nhập. Việc này có thể làm view không giữ được input đã submit. Trong nhánh lỗi thông thường, trả lại form view với target/binding result hiện có; chỉ thay object khi có lý do được thiết kế rõ ràng.

## 14. Kiểm thử mô hình dữ liệu thay vì chỉ kiểm tra giao diện

Bộ kiểm thử nên bao phủ cả dữ liệu gốc và các key model.

| Ca | Đầu vào/thao tác | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Định danh object | `new DataBinder(form, "registrationForm")` | `getObjectName()` là `registrationForm` |
| Mặc định không đặt tên | `new DataBinder(form)` | `getObjectName()` là `target` |
| Cặp key model | `getModel()` | Có target ở key objectName và BindingResult ở key prefix + objectName |
| Đọc map nhiều lần | Gọi `getModel()` hai lần | Các instance map khác nhau; cùng target/result |
| Binding thành công | `age=21` | Target age=21, không có type mismatch |
| Binding thất bại | `age=abc` | Có field error, rejected value, bindingFailure=true |
| Validation | `name=` rồi `rejectValue`/`@NotBlank` | FieldError với bindingFailure=false trong luồng phù hợp |
| Global error | `reject(...)` | `hasGlobalErrors()` true |
| Field bị chặn | `setAllowedFields("name","age")` và input `role` | `getSuppressedFields()` chứa `role`, target không bị gán |
| Field nested | `address.city` | `getObjectName()` giữ nguyên; field path mô tả property con |
| Form MVC | `@ModelAttribute("registrationForm")` + BindingResult sát nhau | Controller đọc lỗi đúng target, view hiển thị lỗi đúng form |
| Đổi tên form | `registrationForm` → `signupForm` | View và mã i18n dùng key mới |
| Input nhạy cảm | Password/token bị reject | Không đưa giá trị thô vào log/response công khai |

Với bài thử standalone ở trên, bạn có thể thay `input.add("age","abc")` bằng `input.add("age","21")` rồi **chạy lại**, xem `ageOnTarget`, `ageRejected` và `getFieldError("age")` thay đổi ra sao. Trước khi thực hiện phép thử như vậy, hãy chỉnh phần code dùng `ageError` vì nó sẽ là `null` khi không còn lỗi; đây cũng là cách kiểm chứng ý nghĩa của `getFieldError` trong ứng dụng thật.

Trong integration test MVC, dùng MockMvc hoặc request thực để kiểm tra cả key model lẫn `BindingResult` và response view. Test nên ghi rõ phiên bản Spring/Jakarta Validation provider. Không dựa duy nhất vào một chuỗi lỗi tiếng Việt: message i18n có thể thay đổi mà dữ liệu lỗi vẫn đúng.

## 15. Lỗi phổ biến và cách sửa

**Lỗi 1: “Không tìm thấy lỗi trong view dù controller báo `hasErrors()=true`.”** Kiểm tra object name của `BindingResult`, model attribute name của controller và `th:object` trong template. Key model phải là `BindingResult.MODEL_KEY_PREFIX + objectName`.

**Lỗi 2: “Model có đối tượng form nhưng không có BindingResult.”** Nếu tự tạo `ModelAndView`/model ngoài luồng MVC thông thường, cần đưa cả hai entry từ `getModel()` vào đúng model. Nếu đã để MVC xử lý `@ModelAttribute`, kiểm tra đoạn code có vô tình ghi đè các entry hay không.

**Lỗi 3: “Thêm field vào `result.getModel()` rồi nó biến mất.”** Mỗi lần `getModel()` trả một map mới. Thay đổi map đang dùng của view bằng `Model.addAttribute(...)` hoặc giữ và gộp map đã tạo đúng cách.

**Lỗi 4: “`getFieldError("age")` có giá trị nhưng `form.getAge()` là null.”** Với `age=abc`, đây là hành vi hợp lý: conversion đã thất bại, rejected input được giữ ở `FieldError`. Dùng field error/value để hiển thị thông báo.

**Lỗi 5: “Có field bị chặn nhưng `hasErrors()` là false.”** `getSuppressedFields()` độc lập với danh sách `FieldError`; whitelist suppression không tự tạo validation error.

**Lỗi 6: “Đọc `getFieldError()` và bỏ sót lỗi khác.”** Method này chỉ trả lỗi field đầu tiên; dùng `getFieldErrors()` hoặc `getAllErrors()` khi cần danh sách đầy đủ. Đồng thời đọc `getGlobalErrors()` cho lỗi toàn form.

**Lỗi 7: “`getRejectedValue()` luôn là String.”** Không đúng. Kiểu trả về là `Object`, có thể là kiểu khác hoặc `null`. Không cast tùy tiện; xử lý theo loại input và giữ bí mật dữ liệu nhạy cảm.

**Lỗi 8: “Đặt `BindingResult` ở cuối chữ ký controller cũng được.”** Không đúng trong luồng xử lý đối tượng `@ModelAttribute` thông thường; tham số này phải đứng ngay sau argument liên quan.

**Lỗi 9: “Thấy `@Valid` là luôn có lỗi trong BindingResult.”** Cần validator/provider phù hợp và controller có cơ chế xử lý. Nếu dùng constraint trực tiếp trên method parameters hoặc request JSON parse thất bại, đường xử lý có thể khác.

**Lỗi 10: “Tên class Java quyết định mọi error key.”** Với MVC có `@ModelAttribute("customName")`, hoặc `DataBinder(target,"customName")`, object name **được gán tường minh**. Đừng tự ghép tên class để tìm error key.

**Lỗi 11: “Lỗi global và lỗi field là một.”** Một object-level rule thường dùng `reject` và trở thành `ObjectError`; một field-level rule dùng `rejectValue` và trở thành `FieldError`. UI cần hiển thị cả hai nơi phù hợp.

**Lỗi 12: “Hiển thị nguyên rejected value để debug luôn an toàn.”** Không. Rejected value xuất phát từ input chưa tin cậy và có thể chứa nội dung nhạy cảm, HTML hoặc ký tự điều khiển. Không xuất thẳng vào log, error JSON hoặc HTML không escape.

## 16. Tự kiểm tra kiến thức

1. Với `new DataBinder(form, "customerForm")`, `getObjectName()` trả gì? **customerForm**; không bắt buộc là tên class.
2. `BindingResult.MODEL_KEY_PREFIX + "customerForm"` tạo khóa nào? **`org.springframework.validation.BindingResult.customerForm`**.
3. `getModel()` có những gì? **Target dưới khóa objectName và BindingResult dưới khóa prefix + objectName**, được tạo thành một map mới mỗi lần gọi.
4. `getAllErrors()` có bao gồm `FieldError` không? **Có**, vì nó kết hợp global và field errors.
5. `getFieldErrors()` có chứa một `ObjectError` global thuần túy không? **Không**.
6. Nếu `age=abc` không chuyển được sang `Integer` thì `getTarget()` luôn có age `"abc"` không? **Không**; age có thể không được gán, còn rejected value được giữ trong lỗi.
7. Field bị suppress do `allowedFields` có mặc nhiên làm `hasErrors()` true không? **Không**.
8. `FieldError.getObjectName()` và `FieldError.getField()` khác nhau thế nào? **Tên root object** và **đường dẫn thuộc tính**.
9. Vì sao phải đặt `BindingResult` ngay sau `@ModelAttribute`? Để MVC gắn lỗi với đúng argument đang bind.
10. Nếu template chuyển `th:object` từ `customerForm` sang `orderForm`, cần kiểm tra gì? Model attribute, binding-result key, tên object, thông báo i18n và controller tương ứng.

## 17. Tài liệu gốc để đối chiếu

- [Spring Framework – BindingResult Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework – Errors Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework – ObjectError Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework – FieldError Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework – DataBinder Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework – DefaultMessageCodesResolver Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework – Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring MVC – ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)

**Nguyên tắc áp dụng:** luôn biết `BindingResult` đang nói về **object name nào**, xác định một lỗi thuộc **global** hay **field**, đọc đúng **rejected value / error codes**, và giữ đúng **cặp khóa model** khi render form. Đây là nền tảng để gỡ lỗi binding/validation mà không mất dữ liệu người dùng nhập và không hiển thị lỗi nhầm đối tượng.
