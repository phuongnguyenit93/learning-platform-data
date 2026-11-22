# Mã lỗi theo tên đối tượng, trường và kiểu dữ liệu trong Spring: thiết kế thông báo đa ngữ

## 1. Vấn đề cần giải quyết

Khi Spring Framework bind dữ liệu HTTP vào Java object hoặc kiểm tra hợp lệ một form/DTO, cùng một loại lỗi có thể cần **câu thông báo khác nhau tùy ngữ cảnh**:

- Người dùng không nhập `name` trong form đăng ký: “Vui lòng nhập họ tên”.
- Người dùng không nhập `name` trong form nhà cung cấp: “Vui lòng nhập tên nhà cung cấp”.
- Người dùng gửi `age=abc`: “Tuổi phải là số nguyên”.
- Người dùng gửi `quantity=abc`: “Số lượng phải là số”.
- Một object có nhiều field không nhất quán: “Dữ liệu hồ sơ không hợp lệ”.

Không nên hardcode toàn bộ thông báo vào validator rồi tự viết hàng chục nhánh `if/else`. Spring cung cấp cơ chế **mã lỗi có thứ tự ưu tiên** thông qua `MessageCodesResolver`, triển khai mặc định là **`DefaultMessageCodesResolver`**, kết hợp với **`MessageSource`** để tìm thông báo theo `Locale`.

**Ý tưởng quan trọng nhất:** một lỗi có một **mã gốc** như `typeMismatch`, nhưng Spring có thể gắn nhiều **mã ứng viên** (candidate codes) cụ thể đến tổng quát:

~~~text
typeMismatch.profileForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

Khi giải quyết thông báo, Spring tìm **mã đầu tiên có bản dịch** trong message bundle thích hợp. Nhờ đó ta có thể tùy chỉnh thông báo cho một form cụ thể, một trường ở nhiều form, mọi trường cùng kiểu dữ liệu, hoặc toàn hệ thống — **không cần đổi logic binding/validation**.

Bài này thuộc nhóm **thông báo đa ngữ trong Spring validation và data binding**, tập trung vào cách mã lỗi được tạo theo **tên đối tượng**, **tên trường** và **kiểu Java**, cách chọn message, cách thử nghiệm và những trường hợp dễ gây nhầm.

## 2. Các khái niệm và API liên quan

| Thành phần | Package/interface điển hình | Trách nhiệm |
| --- | --- | --- |
| `Errors` | `org.springframework.validation.Errors` | Ghi lỗi cấp object hoặc field bằng `reject(...)`, `rejectValue(...)`. |
| `BindingResult` | `org.springframework.validation.BindingResult` | Chứa errors sau binding/validation, gồm `FieldError` và `ObjectError`. |
| `FieldError` | `org.springframework.validation.FieldError` | Mô tả lỗi tại một property: field name, rejected value, codes, arguments, default message. |
| `ObjectError` | `org.springframework.validation.ObjectError` | Mô tả lỗi cấp object, không bắt buộc gắn vào một field. |
| `MessageCodesResolver` | `org.springframework.validation.MessageCodesResolver` | Sinh danh sách mã lỗi theo ngữ cảnh (object, field, type). |
| `DefaultMessageCodesResolver` | `org.springframework.validation.DefaultMessageCodesResolver` | Thuật toán mặc định sinh mã **từ cụ thể đến tổng quát**. |
| `MessageSource` | `org.springframework.context.MessageSource` | Tìm thông báo theo code, arguments và `Locale`. |
| `MessageSourceResolvable` | `org.springframework.context.MessageSourceResolvable` | Một yêu cầu giải quyết thông báo mang mã ứng viên, arguments và default. |
| `DataBinder`/`WebDataBinder` | `org.springframework.validation`/`org.springframework.web.bind` | Bind form/query values, chuyển kiểu, tạo binding errors. |
| `@Valid`/`@Validated` | Jakarta/Spring | Kích hoạt validation tương ứng; errors có thể được Spring chuyển thành `BindingResult`. |

Hai khái niệm phải tách bạch:

1. **Lỗi là gì?** Ví dụ `typeMismatch` (chuỗi không thể chuyển thành Integer), `NotBlank` (constraint thiếu text), `reserved` (validator tự định nghĩa), `profile.invalid` (lỗi cấp object).
2. **Hiển thị thế nào?** Ví dụ tiếng Việt “Tuổi phải là số nguyên” hoặc tiếng Anh “Age must be an integer”. MessageSource chọn câu chữ bằng **mã ứng viên + Locale**.

Mã lỗi không nhất thiết là bản dịch. `FieldError#getCode()` thường là mã gốc như `typeMismatch`, trong khi `FieldError#getCodes()` trả **toàn bộ danh sách ứng viên** như bảng ưu tiên ở phần tiếp theo.

## 3. Thuật toán mặc định cho lỗi cấp trường

### 3.1. Bốn mức mã lỗi

Với `DefaultMessageCodesResolver`, một field error thường sinh bốn loại mã theo thứ tự:

| Ưu tiên | Mẫu | Ý nghĩa |
| --- | --- | --- |
| 1 — cụ thể nhất | `errorCode.objectName.fieldName` | Chỉ field này trên một object cụ thể. |
| 2 | `errorCode.fieldName` | Mọi object có cùng field name. |
| 3 | `errorCode.fieldType` | Mọi field có cùng kiểu Java. |
| 4 — chung nhất | `errorCode` | Fallback cho mọi trường hợp mang cùng mã gốc. |

Giả sử:

- Mã gốc: `typeMismatch`.
- Object name: `profileForm`.
- Property: `age`.
- Kiểu Java của `age`: `java.lang.Integer`.

Thứ tự là:

~~~text
1. typeMismatch.profileForm.age
2. typeMismatch.age
3. typeMismatch.java.lang.Integer
4. typeMismatch
~~~

Nếu message bundle có cả bốn key, key số **1** được dùng. Nếu không có key số 1, Spring thử key số **2**, rồi số **3**, cuối cùng số **4**. **Không có cơ chế lựa chọn dựa trên “dịch nào hay hơn”**; thứ tự mã ứng viên mới quyết định ưu tiên.

Lưu ý phân biệt primitive và wrapper:

~~~text
int.class       -> typeMismatch.int
Integer.class   -> typeMismatch.java.lang.Integer
String.class    -> typeMismatch.java.lang.String
LocalDate.class -> typeMismatch.java.time.LocalDate
~~~

Dòng trên minh họa **phần fieldType** cho các kiểu Java khác nhau. Một thuộc tính Java khai báo `int` không có cùng chuỗi type-code với thuộc tính `Integer`. Vì vậy hãy kiểm tra **kiểu thực tế** trong `FieldError#getCodes()`/`BindingResult` thay vì đoán dựa vào kiểu JSON hoặc ví dụ cũ.

### 3.2. Lệnh sinh mã trực tiếp, không cần web server

~~~java
DefaultMessageCodesResolver resolver =
        new DefaultMessageCodesResolver();

String[] codes = resolver.resolveMessageCodes(
        "typeMismatch",
        "profileForm",
        "age",
        Integer.class);

System.out.println(Arrays.toString(codes));
~~~

Đây là snippet, cần imports `DefaultMessageCodesResolver`/`Arrays`. Kết quả dự kiến:

~~~text
[typeMismatch.profileForm.age, typeMismatch.age, typeMismatch.java.lang.Integer, typeMismatch]
~~~

Muốn đối chiếu `int`, truyền `int.class` vào `resolveMessageCodes`. Javadoc chính thức minh họa bốn mã tương tự với object name `user`, field `age`, kiểu `int`. Kết quả khác nhau ở token type là **chính xác và có chủ ý**.

### 3.3. Vì sao object name quan trọng?

Một ứng dụng có thể có:

~~~java
@ModelAttribute("profileForm") ProfileForm profileForm
@ModelAttribute("supplierForm") SupplierForm supplierForm
~~~

Hai dòng là **khai báo tham số minh họa**, không phải toàn bộ handler. Nếu cả hai có field `name` và cùng sinh mã gốc `NotBlank` hoặc `required`, cấu hình:

~~~properties
required.profileForm.name=Vui lòng nhập tên người dùng.
required.supplierForm.name=Vui lòng nhập tên nhà cung cấp.
required.name=Vui lòng nhập tên.
required=Bắt buộc cung cấp giá trị.
~~~

cho phép dùng câu chữ khác nhau mà validator chỉ cần `rejectValue("name", "required")`. Nếu object name trong chương trình là `profile` thay vì `profileForm`, key `required.profileForm.name` **không khớp**. Có thể kiểm tra tên thật bằng `BindingResult#getObjectName()`.

Object name có thể do `@ModelAttribute("...")` chỉ định rõ, do `DataBinder(target, "name")` khi viết unit test, hoặc do framework suy ra theo argument/bean. **Đừng hardcode thông báo dựa trên một object name chưa được xác minh.**

## 4. Lỗi cấp đối tượng không có field name

Không phải lỗi nào cũng thuộc một field. Ví dụ một hồ sơ có ngày bắt đầu sau ngày kết thúc, hai field độc lập đều hợp lệ nhưng **quan hệ toàn đối tượng không hợp lệ**.

Spring `Errors#reject("profile.invalid")` tạo object/global error. `DefaultMessageCodesResolver` tạo **hai** mã ứng viên:

~~~text
profile.invalid.profileForm
profile.invalid
~~~

Không có `fieldName` hoặc `fieldType` ở đây. Bản dịch có thể được cấu hình:

~~~properties
profile.invalid.profileForm=Thông tin hồ sơ không nhất quán.
profile.invalid=Dữ liệu không hợp lệ.
~~~

Ở controller, lấy `BindingResult#getGlobalErrors()` để thấy errors cấp object, `getFieldErrors()` để thấy errors cấp field, và `getAllErrors()` khi cần cả hai.

Snippet:

~~~java
BeanPropertyBindingResult result =
        new BeanPropertyBindingResult(
                new ProfileForm(), "profileForm");

result.reject("profile.invalid");

ObjectError error = result.getGlobalError();
System.out.println(Arrays.toString(error.getCodes()));
~~~

Ví dụ kết quả:

~~~text
[profile.invalid.profileForm, profile.invalid]
~~~

Snippet cần imports Spring và `ProfileForm`. Nếu class-level Bean Validation constraint tạo global error, cách ưu tiên mã cũng có thể áp dụng khi Spring đã chuyển constraint violation sang `BindingResult`.

**Điểm phân biệt:** `FieldError#getField()` nói trường nào sai, còn `ObjectError` không có property name riêng. Đừng ép object error thành field `"global"` rồi coi đó là property thực sự trong DTO.

## 5. Với collection, array và map: Spring sinh thêm mã không có index

Khi property path chứa chỉ số, Spring mặc định hỗ trợ mã lỗi **cụ thể cho phần tử** và mã lỗi **đã bỏ chỉ số**, giúp bundle dùng chung cho toàn bộ collection.

Với:

~~~text
errorCode = typeMismatch
objectName = profileForm
field = contacts[0].email
fieldType = java.lang.String
~~~

Các mã điển hình, theo thứ tự (đối với một indexed path như trên), là:

~~~text
typeMismatch.profileForm.contacts[0].email
typeMismatch.profileForm.contacts.email
typeMismatch.contacts[0].email
typeMismatch.contacts.email
typeMismatch.email
typeMismatch.java.lang.String
typeMismatch
~~~

Ý nghĩa:

- `typeMismatch.profileForm.contacts[0].email`: đúng phần tử `[0]`, trên object `profileForm`.
- `typeMismatch.profileForm.contacts.email`: mọi phần tử `contacts` của form đó.
- `typeMismatch.contacts[0].email`: cùng path phần tử nhưng không ràng buộc object name.
- `typeMismatch.contacts.email`: mọi phần tử cùng nested path.
- `typeMismatch.email`: mọi field tên `email`.
- `typeMismatch.java.lang.String`: mọi string fields với lỗi đó.
- `typeMismatch`: toàn bộ lỗi cùng mã gốc.

Cú pháp đường dẫn có thể phức tạp hơn với `items[3].price`, map key hoặc nested collection. **Không hardcode số lượng cố định “luôn 4 codes” cho mọi field path**; với indexed paths có thể có thêm mã. Test danh sách do `DefaultMessageCodesResolver` tạo cho property thực tế.

Ví dụ bundle cho toàn bộ danh sách:

~~~properties
typeMismatch.profileForm.contacts.email=Email trong danh sách liên hệ không hợp lệ.
typeMismatch.email=Email không hợp lệ.
~~~

Nếu form có 10 contacts, không cần tạo 10 bản dịch theo `[0]`, `[1]`, ... chỉ để tái sử dụng một thông báo.

## 6. `MessageSource` chọn câu theo Locale như thế nào?

`MessageSource` là abstraction của Spring để lấy thông báo quốc tế hóa. Các overload thông dụng:

~~~java
String getMessage(String code, Object[] args,
                  String defaultMessage, Locale locale);

String getMessage(String code, Object[] args, Locale locale);

String getMessage(MessageSourceResolvable resolvable,
                  Locale locale);
~~~

`FieldError`/`ObjectError` triển khai `MessageSourceResolvable`, vì vậy cách ngắn gọn nhất là:

~~~java
String message = messageSource.getMessage(
        fieldError, Locale.forLanguageTag("vi"));
~~~

Spring thử lần lượt các `fieldError.getCodes()` để tìm key có bản dịch ở locale cần dùng. Có thể thay `Locale.forLanguageTag("vi")` bằng `Locale.ENGLISH` hoặc locale do HTTP request được resolver cung cấp.

**Đừng làm như sau** nếu muốn giữ ưu tiên object/field/type:

~~~java
// Không lý tưởng: chỉ dùng mã gốc, mất thông tin độ ưu tiên.
String text = messageSource.getMessage(
        fieldError.getCode(),
        null,
        fieldError.getDefaultMessage(),
        locale);
~~~

Lời gọi này có thể dùng nếu ứng dụng **cố ý** chỉ muốn mã tổng quát, nhưng không khai thác `getCodes()`. Trong tình huống chuẩn, truyền **cả `FieldError`** (một `MessageSourceResolvable`) để giữ chain fallback.

### 6.1. Message arguments

Một số constraints cần tham số: `@Size(min=3,max=20)`, `@Min(18)`. Spring errors/MessageSource có thể chứa arguments cho message templates. Cần kiểm tra `getArguments()` và quy tắc nội suy để dùng các placeholder như `{0}`, `{1}` đúng ý nghĩa. **Không mặc định đối số số 0 luôn là min hay tên field** trong mọi validator; phần arguments có thể gồm một resolvable hiển thị nhãn field.

Ví dụ message với arguments do ứng dụng tự kiểm soát:

~~~java
errors.rejectValue(
        "age",
        "age.minimum",
        new Object[] {18},
        "Tuổi không hợp lệ");
~~~

Với bundle:

~~~properties
age.minimum.profileForm.age=Tuổi phải từ {0} trở lên.
age.minimum=Giá trị phải từ {0} trở lên.
~~~

`MessageSource` có thể thay `{0}` bằng `18`, còn locale quyết định chuỗi còn lại. Đây là **snippet trong validator/controller** có biến `Errors errors`; không phải hàm biên dịch độc lập.

### 6.2. Không tìm thấy code: default message và fallback

`MessageSourceResolvable` có thể mang `defaultMessage`. Khi không tìm thấy bất kỳ key phù hợp nào, Spring có thể trả default nếu được cung cấp. Nếu gọi overload **không có default** và không tìm thấy message, `NoSuchMessageException` có thể xuất hiện.

Vì vậy hãy duy trì **fallback key tổng quát** trong bundle và có policy cho lỗi chưa được dịch. Không trả raw exception text/Java stack trace ra client khi thiếu message key. Cũng không giả định mọi `FieldError#getDefaultMessage()` đã dùng đúng locale của HTTP request: đặc biệt khi có Bean Validation, default message có thể đã được nội suy theo môi trường lúc validator chạy.

## 7. Nguồn mã lỗi: binding, Spring Validator và Bean Validation

Ba con đường thường gặp đều có thể dẫn đến `BindingResult`, nhưng **mã gốc** có thể khác.

### 7.1. Lỗi binding/conversion: `typeMismatch`, `required`

Khi binder nhận `age=abc` mà property Java là `Integer age`, conversion có thể thất bại và sinh `FieldError`, với `getCode()` thường là `typeMismatch`.

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profileForm");

binder.bind(new MutablePropertyValues(
        Map.of("age", "abc")));

FieldError ageError =
        binder.getBindingResult().getFieldError("age");

System.out.println(ageError.getCode());
System.out.println(Arrays.toString(ageError.getCodes()));
~~~

Đây là snippet cần imports `DataBinder`, `MutablePropertyValues`, `FieldError`, `Arrays`, `Map` và DTO `ProfileForm`. Kết quả chính, với kiểu `Integer`:

~~~text
typeMismatch
[typeMismatch.profileForm.age, typeMismatch.age, typeMismatch.java.lang.Integer, typeMismatch]
~~~

`setRequiredFields("age")` là một cấu hình khác của `DataBinder`; nó có thể tạo mã `required` khi input field cần thiết không có. Không nhầm `required` của binding với `@NotNull` của Jakarta Bean Validation — chúng có thể cùng biểu thị “thiếu dữ liệu” nhưng đến từ **hai cơ chế** khác nhau.

### 7.2. Lỗi do Spring `Validator` tự khai báo

Một custom Spring `Validator` có thể làm:

~~~java
@Override
public void validate(Object target, Errors errors) {
    ProfileForm form = (ProfileForm) target;

    if ("admin".equalsIgnoreCase(form.getName())) {
        errors.rejectValue("name", "reserved");
    }
}
~~~

Đây là method snippet, cần class implement `org.springframework.validation.Validator`. Mã gốc `reserved` được mở rộng:

~~~text
reserved.profileForm.name
reserved.name
reserved.java.lang.String
reserved
~~~

Chỉ cần viết các key phù hợp trong `messages_vi.properties`/`messages_en.properties`. Spring Validator kiểm tra điều kiện; message bundle quyết định câu chữ. Có thể thêm `defaultMessage` khi gọi `rejectValue` nếu muốn fallback hiển thị.

### 7.3. Lỗi Jakarta Bean Validation: `NotBlank`, `NotNull`, `Min`

Với:

~~~java
public class ProfileForm {
    @NotBlank
    private String name;

    @NotNull
    private Integer age;
}
~~~

Snippet chỉ nhằm diễn giải annotations; file đầy đủ có getters/setters ở phần 9. Khi Spring MVC kích hoạt Bean Validation qua `@Valid @ModelAttribute` hoặc `@Valid @RequestBody`, những `ConstraintViolation` được chuyển thành Spring errors trong `BindingResult`. Các mã gốc điển hình:

~~~text
NotBlank.profileForm.name
NotBlank.name
NotBlank.java.lang.String
NotBlank

NotNull.profileForm.age
NotNull.age
NotNull.java.lang.Integer
NotNull
~~~

**Điểm cần đặc biệt phân biệt:** `@NotBlank(message = "{profile.name.required}")` sử dụng **cơ chế message interpolation của Jakarta Bean Validation**; đây không đồng nhất về khái niệm với chiến lược bốn mã của `DefaultMessageCodesResolver`. Spring có thể tích hợp các message sources với validator tùy cấu hình, nhưng có **hai giai đoạn**: tạo/ nội suy constraint message và chọn lỗi từ `BindingResult` cho UI/API.

Nếu muốn sử dụng nhất quán message code priority của Spring, có thể cung cấp các key như `NotBlank.profileForm.name` trong `messages_vi.properties` rồi chọn message qua `MessageSource.getMessage(fieldError, locale)`. Nếu muốn dùng custom constraint template `{profile.name.required}`, cần bảo đảm message interpolation của Bean Validation được cấu hình với bundle/provider tương ứng. Không coi việc có `messages_vi.properties` là bằng chứng rằng mọi `ValidationMessages` của Jakarta đã tự cùng cấu hình nếu chưa kiểm thử integration.

## 8. Cách tổ chức bundle tiếng Việt/tiếng Anh

Với Spring Boot dùng `MessageSource` auto-configuration, tạo các file dưới `src/main/resources/`:

~~~text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_en.properties
~~~

`messages.properties` là **bundle mặc định**. Spring Boot thường chỉ tự cấu hình message source từ basename khi có bundle mặc định; vì vậy đừng chỉ tạo mỗi `messages_vi.properties` và `messages_en.properties` rồi mong mọi ứng dụng Boot đều tự nhận.

### 8.1. `application.properties`

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Ý nghĩa:

- `basename` chỉ bundle mà Spring dùng.
- `encoding=UTF-8` giữ tiếng Việt có dấu.
- `fallback-to-system-locale=false` tránh lấy ngôn ngữ máy chủ làm fallback khó dự đoán. Locale của **request** vẫn do MVC LocaleResolver hoặc handler quyết định.

### 8.2. `messages.properties` — fallback mặc định

~~~properties
NotBlank.profileForm.name=Please enter a name.
NotBlank=Text must not be blank.
NotNull.profileForm.age=Please enter an age.
NotNull=A value is required.
typeMismatch.profileForm.age=Age must be an integer.
typeMismatch.age=The age must be a number.
typeMismatch.java.lang.Integer=Please enter a whole number.
typeMismatch=Invalid input type.
reserved.profileForm.name=This name is reserved.
reserved=The value is not allowed.
required.profileForm.name=Name is required for this form.
required.name=A name is required.
required.java.lang.String=A text value is required.
required=A value is required.
profile.invalid.profileForm=The profile has inconsistent data.
profile.invalid=Invalid object.
~~~

### 8.3. `messages_vi.properties` — tiếng Việt

~~~properties
NotBlank.profileForm.name=Vui lòng nhập tên.
NotBlank=Không được để trống nội dung.
NotNull.profileForm.age=Vui lòng nhập tuổi.
NotNull=Cần nhập giá trị.
typeMismatch.profileForm.age=Tuổi phải là số nguyên.
typeMismatch.age=Tuổi phải là giá trị số.
typeMismatch.java.lang.Integer=Vui lòng nhập số nguyên.
typeMismatch=Kiểu dữ liệu không hợp lệ.
reserved.profileForm.name=Tên này không được sử dụng.
reserved=Giá trị này không được phép.
required.profileForm.name=Tên là bắt buộc cho biểu mẫu này.
required.name=Cần cung cấp tên.
required.java.lang.String=Cần nhập dữ liệu dạng chữ.
required=Cần cung cấp giá trị.
profile.invalid.profileForm=Thông tin hồ sơ không nhất quán.
profile.invalid=Dữ liệu đối tượng không hợp lệ.
~~~

### 8.4. `messages_en.properties` — tiếng Anh

~~~properties
NotBlank.profileForm.name=Please enter a name.
NotBlank=Text cannot be blank.
NotNull.profileForm.age=Please enter an age.
NotNull=This value is required.
typeMismatch.profileForm.age=Age must be an integer.
typeMismatch.age=Age must be numeric.
typeMismatch.java.lang.Integer=Please enter a whole number.
typeMismatch=Invalid value type.
reserved.profileForm.name=This name is reserved.
reserved=This value is not allowed.
required.profileForm.name=Name is required for this form.
required.name=A name is required.
required.java.lang.String=A text value is required.
required=A value is required.
profile.invalid.profileForm=Profile data is inconsistent.
profile.invalid=Invalid object data.
~~~

**Chú ý về khóa:** Spring message resolution là **theo code chính xác và có phân biệt chữ hoa/chữ thường**. `NotBlank` khác `notBlank`, `profileForm` khác `ProfileForm`, và `java.lang.Integer` khác `int`. Chỉ cần một ký tự lệch, resolver sẽ thử ứng viên khác — dễ khiến ứng dụng hiển thị một câu quá tổng quát.

Trong file `.properties`, lưu UTF-8 thực sự. Nếu dùng công cụ build/IDE cũ tự chuyển mã, hãy xác minh các ký tự tiếng Việt sau khi ứng dụng đọc file. Khi đưa thông báo ra UI/API, đừng nối thêm tên field một cách tùy tiện làm lộ property nội bộ; nên thiết kế câu thân thiện có ngữ cảnh.

## 9. Ví dụ hoàn chỉnh: Java 17+, Spring Boot 3.x, i18n theo lỗi của form

Tạo dự án Maven **Spring Boot 3.x**, **Java 17+**, sử dụng Servlet Spring MVC. Mỗi file Java có package `com.example.errormessages`.

### 9.1. Dependencies

Dự án đã có Spring Boot parent/BOM, thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các bundle ở phần 8 thuộc **chính dự án này**. Không cần tạo database hay controller view/template: response là JSON.

### 9.2. `ErrorMessagesApplication.java`

File `src/main/java/com/example/errormessages/ErrorMessagesApplication.java`:

~~~java
package com.example.errormessages;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorMessagesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorMessagesApplication.class, args);
    }
}
~~~

### 9.3. `ProfileForm.java`

File `src/main/java/com/example/errormessages/ProfileForm.java`:

~~~java
package com.example.errormessages;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ProfileForm {

    @NotBlank
    private String name;

    @NotNull
    private Integer age;

    public ProfileForm() {
    }

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

DTO có hai trường:

- `name` có `@NotBlank`, sinh mã gốc `NotBlank` khi người dùng gửi chuỗi rỗng.
- `age` có kiểu `Integer`; `age=abc` là lỗi **conversion** mã `typeMismatch`, còn thiếu `age` có thể là lỗi `@NotNull` mã `NotNull`.
- Không có field nhạy cảm như `role` hay `balance`. Production vẫn cần DTO và authorization phù hợp, không bind trực tiếp entity.

### 9.4. `ProfileController.java`

File `src/main/java/com/example/errormessages/ProfileController.java`:

~~~java
package com.example.errormessages;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {

    private final MessageSource messages;

    public ProfileController(MessageSource messages) {
        this.messages = messages;
    }

    @PostMapping(
            path = "/register",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors,
            Locale locale) {

        if ("admin".equalsIgnoreCase(form.getName())) {
            // Ví dụ quy tắc riêng dùng mã gốc "reserved".
            errors.rejectValue("name", "reserved");
        }

        if (!errors.hasErrors()) {
            return ResponseEntity.ok(Map.of(
                    "status", "accepted"));
        }

        List<Issue> issues = errors.getAllErrors().stream()
                .map(error -> new Issue(
                        error instanceof FieldError fieldError
                                ? fieldError.getField()
                                : "",
                        error.getCode(),
                        messages.getMessage(error, locale)))
                .toList();

        return ResponseEntity.badRequest()
                .body(new ValidationResponse(issues));
    }

    public record Issue(
            String field, String code, String message) {
    }

    public record ValidationResponse(List<Issue> errors) {
    }
}
~~~

Lý do thiết kế:

1. `@ModelAttribute("profileForm")` đặt **object name tường minh**. Các key bundle như `NotBlank.profileForm.name` và `typeMismatch.profileForm.age` do đó có mục tiêu rõ ràng.
2. `@Valid` kích hoạt Bean Validation sau binding, với provider từ validation starter.
3. `BindingResult errors` ở **ngay sau** form object để controller nhận field/object errors.
4. Quy tắc `admin` không dùng câu literal: `errors.rejectValue("name", "reserved")` để Spring sinh `reserved.profileForm.name`, `reserved.name`, `reserved.java.lang.String`, `reserved`.
5. `messages.getMessage(error, locale)` nhận **toàn bộ `ObjectError`**, vì `ObjectError` implements `MessageSourceResolvable`; Spring thử mọi `getCodes()` theo thứ tự.
6. `Locale locale` được Spring MVC resolve theo locale resolution đã cấu hình (ở ví dụ mặc định có thể dùng `Accept-Language`), giúp API trả message bằng ngôn ngữ mong muốn.
7. Response chứa field, **mã gốc ổn định** và câu hiển thị. Nó cố ý **không trả `FieldError#getRejectedValue()`** để tránh lộ input có thể nhạy cảm.

Ví dụ người dùng gửi form:

~~~http
POST /api/profiles/register
Content-Type: application/x-www-form-urlencoded
Accept-Language: vi

name=&age=24
~~~

Object bind thành công, nhưng `@NotBlank` fail. Với bundle ở phần 8, response dự kiến:

~~~json
{
  "errors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Vui lòng nhập tên."
    }
  ]
}
~~~

Cùng request với `Accept-Language: en` trả câu `"Please enter a name."`. Nếu gửi `name=admin&age=24`, controller thêm lỗi `reserved` và trả `"Tên này không được sử dụng."` cho locale `vi`.

**Chú ý:** HTTP status ở đây do controller chủ động chọn là **400**, không phải một quy luật rằng mọi validation error trong mọi ứng dụng đều được xử lý bằng controller nội bộ. Nếu không khai báo `BindingResult` liền kề, Spring MVC có thể ném `MethodArgumentNotValidException` để `@ControllerAdvice` xử lý.

## 10. Unit test: xác nhận thứ tự mã và lookup theo loại trường

Tạo file `src/test/java/com/example/errormessages/ErrorCodeResolutionTest.java`:

~~~java
package com.example.errormessages;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.support.ResourceBundleMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.DefaultMessageCodesResolver;
import org.springframework.validation.FieldError;

import java.util.Arrays;
import java.util.Locale;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ErrorCodeResolutionTest {

    private ResourceBundleMessageSource messageSource() {
        var source = new ResourceBundleMessageSource();
        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }

    @Test
    void fieldCodesAreOrderedFromSpecificToGeneral() {
        var resolver = new DefaultMessageCodesResolver();

        String[] actual = resolver.resolveMessageCodes(
                "typeMismatch", "profileForm", "age",
                Integer.class);

        assertArrayEquals(new String[] {
                "typeMismatch.profileForm.age",
                "typeMismatch.age",
                "typeMismatch.java.lang.Integer",
                "typeMismatch"
        }, actual);
    }

    @Test
    void primitiveFieldTypeProducesDifferentCode() {
        var resolver = new DefaultMessageCodesResolver();

        assertArrayEquals(new String[] {
                "typeMismatch.profileForm.age",
                "typeMismatch.age",
                "typeMismatch.int",
                "typeMismatch"
        }, resolver.resolveMessageCodes(
                "typeMismatch", "profileForm", "age",
                int.class));
    }

    @Test
    void globalErrorHasTwoCandidateCodes() {
        var binding = new BeanPropertyBindingResult(
                new ProfileForm(), "profileForm");

        binding.reject("profile.invalid");

        assertArrayEquals(new String[] {
                "profile.invalid.profileForm",
                "profile.invalid"
        }, binding.getGlobalError().getCodes());

        assertEquals("Thông tin hồ sơ không nhất quán.",
                messageSource().getMessage(
                        binding.getGlobalError(),
                        Locale.forLanguageTag("vi")));
    }

    @Test
    void fieldErrorUsesMostSpecificVietnameseCode() {
        var binding = new BeanPropertyBindingResult(
                new ProfileForm(), "profileForm");

        binding.rejectValue("name", "required");

        FieldError error = binding.getFieldError("name");
        assertNotNull(error);

        assertArrayEquals(new String[] {
                "required.profileForm.name",
                "required.name",
                "required.java.lang.String",
                "required"
        }, error.getCodes());

        assertEquals("Tên là bắt buộc cho biểu mẫu này.",
                messageSource().getMessage(
                        error, Locale.forLanguageTag("vi")));
    }

    @Test
    void fallbackUsesFieldNameWhenObjectSpecificCodeMissing() {
        var binding = new BeanPropertyBindingResult(
                new ProfileForm(), "otherForm");

        binding.rejectValue("name", "required");

        assertEquals("Cần cung cấp tên.",
                messageSource().getMessage(
                        binding.getFieldError("name"),
                        Locale.forLanguageTag("vi")));
    }

    @Test
    void actualDataBinderCreatesTypeMismatchForInteger() {
        var target = new ProfileForm();
        var binder = new DataBinder(target, "profileForm");

        binder.bind(new MutablePropertyValues(
                Map.of("age", "abc")));

        FieldError error = binder.getBindingResult()
                .getFieldError("age");

        assertNotNull(error);
        assertEquals("typeMismatch", error.getCode());

        assertTrue(Arrays.asList(error.getCodes())
                .contains("typeMismatch.java.lang.Integer"));

        assertEquals("Tuổi phải là số nguyên.",
                messageSource().getMessage(
                        error, Locale.forLanguageTag("vi")));
    }

    @Test
    void prefixCanNamespaceGeneratedCodes() {
        var resolver = new DefaultMessageCodesResolver();
        resolver.setPrefix("validation.");

        assertArrayEquals(new String[] {
                "validation.typeMismatch.profileForm.age",
                "validation.typeMismatch.age",
                "validation.typeMismatch.java.lang.Integer",
                "validation.typeMismatch"
        }, resolver.resolveMessageCodes(
                "typeMismatch", "profileForm", "age",
                Integer.class));
    }

    @Test
    void indexedFieldProducesIndexSpecificAndGenericCodes() {
        var resolver = new DefaultMessageCodesResolver();

        String[] codes = resolver.resolveMessageCodes(
                "typeMismatch", "profileForm",
                "contacts[0].email", String.class);

        assertArrayEquals(new String[] {
                "typeMismatch.profileForm.contacts[0].email",
                "typeMismatch.profileForm.contacts.email",
                "typeMismatch.contacts[0].email",
                "typeMismatch.contacts.email",
                "typeMismatch.email",
                "typeMismatch.java.lang.String",
                "typeMismatch"
        }, codes);
    }
}
~~~

**8 unit tests** thể hiện:

- Thứ tự **object + field → field → field type → general**.
- Wrapper `Integer.class` và primitive `int.class` sinh token type khác nhau.
- Object-level error chỉ có hai candidate codes.
- `MessageSource` chọn bản dịch tiếng Việt bằng **mã ưu tiên cao nhất tìm thấy**.
- Khi đổi object name thành `otherForm` mà chưa có `required.otherForm.name`, fallback sang `required.name`.
- `DataBinder` thực sự sinh lỗi `typeMismatch` khi `age=abc`.
- `setPrefix("validation.")` đổi tên mã sinh ra, không đổi mã gốc nghiệp vụ của validator.
- Indexed paths hỗ trợ mã theo phần tử cụ thể và phần không chỉ số.

Test `DataBinder` ở đây chỉ kiểm tra **binding/conversion**; nó không tự chạy `@Valid`. Các tests MVC tiếp theo kiểm tra **Bean Validation** và request locale.

## 11. MockMvc test: locale từ HTTP và mã lỗi thực tế

Tạo file `src/test/java/com/example/errormessages/ProfileControllerTest.java`:

~~~java
package com.example.errormessages;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("age", "25"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("accepted"));
    }

    @Test
    void vietnameseNameErrorUsesObjectAndFieldCode()
            throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .param("name", "")
                    .param("age", "25"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.errors[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Vui lòng nhập tên."));
    }

    @Test
    void englishNameErrorUsesEnglishBundle()
            throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                    .param("name", "")
                    .param("age", "25"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Please enter a name."));
    }

    @Test
    void namedBusinessCodeCanBeTranslated()
            throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .param("name", "admin")
                    .param("age", "25"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].code")
                        .value("reserved"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên này không được sử dụng."));
    }

    @Test
    void invalidIntegerUsesLocalizedTypeMismatch()
            throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .param("name", "Lan")
                    .param("age", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[*].message",
                        hasItem("Tuổi phải là số nguyên.")));
    }

    @Test
    void missingAgeIsValidationError()
            throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .param("name", "Lan"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[*].message",
                        hasItem("Vui lòng nhập tuổi.")));
    }

    @Test
    void endpointRequiresFormContentType()
            throws Exception {
        mvc.perform(post("/api/profiles/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Lan","age":25}
                            """))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Có **7 bài MockMvc tests**. Test chỉ yêu cầu đúng message khi ứng dụng đã khai báo key trong bundle; không phụ thuộc câu chữ mặc định của Hibernate Validator. Trường hợp `typeMismatch` có thể có hơn một error (tùy cách provider/binder xử lý trường không thể convert), nên test dùng Hamcrest `hasItem` để kiểm tra **có thông báo đúng** thay vì giả định chỉ có một lỗi hoặc thứ tự errors cố định.

Chạy hai test class bằng Maven wrapper:

~~~bash
./mvnw test -Dtest=ErrorCodeResolutionTest,ProfileControllerTest
~~~

Trên Windows:

~~~powershell
mvnw.cmd test -Dtest=ErrorCodeResolutionTest,ProfileControllerTest
~~~

Hoặc `mvn test` khi Maven đã được cài. Với Spring Boot 3.x Web + Validation + Test và các file như trên, **15 tests được thiết kế để chạy thành công**: 8 unit tests + 7 MockMvc tests. Không cần database. Nếu thêm Spring Security, custom `LocaleResolver`, `@ControllerAdvice` hoặc thay MessageSource/Validator, cần điều chỉnh test theo cấu hình thật.

### Kết quả HTTP tiêu biểu

| Input | Locale | HTTP | Nội dung chính |
| --- | --- | --- | --- |
| `name=Lan&age=25` | bất kỳ | 200 | `{"status":"accepted"}` |
| `name=&age=25` | `vi` | 400 | `NotBlank`, “Vui lòng nhập tên.” |
| `name=&age=25` | `en` | 400 | `NotBlank`, “Please enter a name.” |
| `name=admin&age=25` | `vi` | 400 | `reserved`, “Tên này không được sử dụng.” |
| `name=Lan&age=not-a-number` | `vi` | 400 | `typeMismatch`, “Tuổi phải là số nguyên.” |
| `name=Lan` thiếu `age` | `vi` | 400 | `NotNull`, “Vui lòng nhập tuổi.” |
| Gửi JSON đến mapping chỉ nhận form | bất kỳ | 415 | Lỗi media type trước logic controller. |

Kết quả ở đây là **hợp đồng được ví dụ thiết kế và kiểm thử**, không phải lời khẳng định mọi dự án Spring mặc định trả cùng schema JSON. Các thông báo thực tế phụ thuộc lỗi nào được sinh ra, keys trong bundle, locale resolution và custom error handling.

### Thử bằng curl

Khi ứng dụng chạy với `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/api/profiles/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  -d "name=&age=25"

curl -i -X POST "http://localhost:8080/api/profiles/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: en" \
  -d "name=&age=25"

curl -i -X POST "http://localhost:8080/api/profiles/register" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  -d "name=admin&age=25"
~~~

Lệnh trên là cú pháp shell Unix. Trên PowerShell dùng `curl.exe` với cách escape/continuation phù hợp. Ba request minh họa **một mã gốc nhưng các locale khác nhau**, và **một business code khác có cùng cơ chế i18n**.

## 12. Tùy biến chiến lược mã lỗi

### 12.1. Dùng prefix để tránh xung đột mã

Một dự án lớn có thể dùng nhiều bundles với key `required`, `invalid`, `typeMismatch`. Có thể nhóm codes bằng prefix:

~~~java
DefaultMessageCodesResolver resolver =
        new DefaultMessageCodesResolver();

resolver.setPrefix("validation.");

String[] codes = resolver.resolveMessageCodes(
        "typeMismatch", "profileForm", "age",
        Integer.class);
~~~

Kết quả:

~~~text
validation.typeMismatch.profileForm.age
validation.typeMismatch.age
validation.typeMismatch.java.lang.Integer
validation.typeMismatch
~~~

Khi dùng prefix, các file `messages*.properties` cũng phải dùng prefix tương ứng. Nếu chỉ bật prefix ở code mà quên sửa bundle, MessageSource không tìm được những key cũ nữa.

Để áp dụng **cho MVC argument binding toàn ứng dụng**, có thể cung cấp `MessageCodesResolver` qua `WebMvcConfigurer#getMessageCodesResolver()`:

~~~java
@Configuration
public class ErrorCodeMvcConfig implements WebMvcConfigurer {

    @Override
    public MessageCodesResolver getMessageCodesResolver() {
        var resolver = new DefaultMessageCodesResolver();
        resolver.setPrefix("validation.");
        return resolver;
    }
}
~~~

Đây là **snippet cấu hình thay thế**, cần imports của Spring. Không thêm class này vào ví dụ ở phần 9 khi các bundle vẫn dùng key **không có prefix**. Khi cấu hình thực tế, phải kiểm thử cả lỗi binding và validation, bảo đảm không phá các key i18n có sẵn.

### 12.2. Tùy biến format của code

`DefaultMessageCodesResolver` còn hỗ trợ `setMessageCodeFormatter(...)` và enum `DefaultMessageCodesResolver.Format`. Mặc định mã gốc nằm ở đầu, ví dụ `typeMismatch.profileForm.age`. Khi thay đổi formatter, **cách ghép mã** có thể thay đổi theo chính sách; team phải thống nhất quy ước với người quản lý bundles.

Không nên tùy tiện viết `MessageCodesResolver` custom chỉ để đổi một câu chữ; thường chỉ cần thêm key ở mức `errorCode.object.field` là đủ. Đổi quy tắc code trên diện rộng có thể khiến bản dịch cũ không tìm được và ảnh hưởng nhiều màn hình.

### 12.3. Config cục bộ trong DataBinder

Khi gọi `DataBinder` thủ công trong unit test hoặc một service không đi qua MVC, binder cũng có API `setMessageCodesResolver(...)` để chọn chiến lược. Vì vậy kết quả tests của binder có thể khác nếu bạn cấu hình resolver khác MVC. Để debug, đọc `bindingResult.getFieldError(field).getCodes()` từ **binder thực sự** đã xử lý request.

## 13. Mối liên hệ với `@ControllerAdvice` và REST error contract

Nếu handler không khai báo `BindingResult` ngay sau `@Valid @ModelAttribute` hoặc `@Valid @RequestBody`, Spring MVC có thể ném `MethodArgumentNotValidException`. Một `@RestControllerAdvice` có thể đọc `ex.getBindingResult()` và dùng cùng `MessageSource`.

Snippet:

~~~java
@RestControllerAdvice
public class GlobalValidationAdvice {

    private final MessageSource source;

    public GlobalValidationAdvice(MessageSource source) {
        this.source = source;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<?> handle(
            MethodArgumentNotValidException ex,
            Locale locale) {

        List<String> messages =
                ex.getBindingResult().getAllErrors()
                        .stream()
                        .map(error -> source.getMessage(
                                error, locale))
                        .toList();

        return ResponseEntity.badRequest()
                .body(Map.of("messages", messages));
    }
}
~~~

Đây là **class minh họa tùy chọn**, cần imports. Không phải một phần của bộ source chạy được phía trên. Lưu ý method validation cấp method của Spring MVC có thể dùng `HandlerMethodValidationException`; body JSON sai cú pháp có thể là `HttpMessageNotReadableException`. Không gom mọi exception vào `MethodArgumentNotValidException`.

**Một số thiết kế API** chỉ trả mã ổn định như `NAME_REQUIRED`, còn phần hiển thị thông báo do frontend dịch. Đó cũng là thiết kế hợp lệ, đặc biệt khi nhiều clients cần đa ngữ hoặc versioned error contracts. Trong trường hợp server dịch thông báo, hãy gửi `Locale` đúng nguồn, tránh để cache/CDN trộn response giữa `vi` và `en`.

## 14. Bảo mật và khả năng bảo trì bản dịch

### 14.1. Không để lộ rejected input

`FieldError#getRejectedValue()` có thể chứa password, token, địa chỉ email, số giấy tờ hoặc dữ liệu người dùng nhập. Dù dùng message code để dịch, **không tự thêm raw rejected value vào message/error response** nếu chưa có chính sách redaction.

Ví dụ không an toàn:

~~~java
// Không nên trả rejectedValue trực tiếp cho client.
String message = "Không hợp lệ: "
        + fieldError.getRejectedValue();
~~~

Tốt hơn: trả field identifier đã duyệt, mã lỗi và text đã kiểm soát; không đưa exception stack traces hay internal class names ra API. Các property names trong error response cũng nên là tên **public API fields**, không nhất thiết lộ đường dẫn entity nội bộ.

### 14.2. Tránh quá nhiều mã chuyên biệt

Nếu mọi màn hình có một mã riêng, bundles có thể phình to và bản dịch khó đồng bộ. Quy tắc ưu tiên phù hợp:

1. Dùng `errorCode.object.field` **chỉ khi thật sự có thông điệp đặc biệt** cho ngữ cảnh đó.
2. Dùng `errorCode.field` cho trường xuất hiện ở nhiều form với cùng ý nghĩa.
3. Dùng `errorCode.fieldType` cho thông điệp type conversion đồng nhất, ví dụ tất cả Integer fields.
4. Luôn có `errorCode` làm fallback để không hiển thị text kỹ thuật khi thiếu key.

Trong ví dụ, `typeMismatch.profileForm.age` nên cụ thể vì nói “Tuổi”; `typeMismatch.java.lang.Integer` là fallback “Vui lòng nhập số nguyên”; `typeMismatch` là fallback cuối “Kiểu dữ liệu không hợp lệ”.

### 14.3. Kiểm thử fallback và locale

Với dữ liệu đa ngữ, nên có tests cho:

- Key cụ thể nhất tồn tại.
- Key cấp object không tồn tại nhưng key cấp field tồn tại.
- Key cấp field không tồn tại nhưng key cấp type hoặc generic tồn tại.
- `Locale.forLanguageTag("vi")` và `Locale.ENGLISH` cho cùng lỗi.
- Mã global (object-level), mã có index (collection), primitive/wrapper type.
- Unicode và dấu tiếng Việt trong `.properties`.
- Message arguments `{0}` cho limit như age/size.
- Một code cố tình thiếu key để bảo đảm fallback policy không lộ stack traces.
- Các thay đổi object name/renaming field sau refactor.

Không phụ thuộc vào thứ tự của `getAllErrors()` khi có nhiều validators có thể tạo errors cùng lúc; sắp xếp output nếu cần contract ổn định. Đồng thời không coi text bản dịch là giá trị duy nhất để frontend phân nhánh nghiệp vụ: dùng mã lỗi có ngữ nghĩa riêng.

### 14.4. Phân biệt locale request và locale mặc định máy chủ

Spring MVC có thể xác định `Locale` từ HTTP `Accept-Language` bằng cấu hình mặc định, nhưng ứng dụng có thể có `LocaleResolver` riêng, cookie/session preference hoặc setting của user. `MessageSource#getMessage(...)` luôn sử dụng **Locale được truyền vào**, nên kết quả test trực tiếp không phụ thuộc request nếu gọi explicit `Locale.forLanguageTag("vi")`.

Tùy chọn `spring.messages.fallback-to-system-locale=false` điều chỉnh fallback của **resource bundles**, không có nghĩa “bất kỳ request nào cũng tự là tiếng Việt”. Khi backend có người dùng nhiều vùng, cần quyết định nguồn Locale, default, và header `Vary: Accept-Language` nếu caching phụ thuộc header.

## 15. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Cách chẩn đoán/sửa |
| --- | --- | --- |
| Luôn hiện “Invalid value” dù đã có key riêng | Object name/field name hoặc capital letters không khớp. | Log an toàn `getObjectName()`, `getField()`, `getCodes()`; so sánh bundle. |
| `typeMismatch.int` không áp dụng | Property thực tế là `Integer`, không phải primitive `int`. | Kiểm tra `getCodes()`; dùng `typeMismatch.java.lang.Integer`. |
| Lỗi có mã `NotBlank` nhưng bundle lại viết `notblank` | Message keys phân biệt hoa/thường. | Dùng `NotBlank.profileForm.name` hoặc key đúng với codes. |
| Có `messages_vi.properties` nhưng Boot không nạp | Thiếu `messages.properties` hoặc basename config sai. | Thêm default bundle, kiểm tra `spring.messages.basename`. |
| Đổi `@ModelAttribute("profileForm")` thành `("profile")` làm mất dịch cụ thể | Key có object name cũ. | Sửa key hoặc giữ tên contract ổn định; test locale. |
| Có lỗi ở array item nhưng chỉ viết key `[0]` | Các phần tử khác không có bản dịch cụ thể. | Viết code path bỏ index hoặc fallback cấp field/type. |
| Gọi `getMessage(error.getCode(), ...)` chỉ ra thông báo chung | Đã bỏ danh sách `getCodes()`. | Truyền `ObjectError`/`FieldError` trực tiếp vào `getMessage(error, locale)`. |
| Gửi JSON sai cú pháp mà mong `typeMismatch.profileForm.age` | JSON decoder fail trước Spring WebDataBinder. | Phân biệt `HttpMessageNotReadableException` và form binding errors. |
| `@NotNull` bị nhầm thành lỗi `required` | Bean Validation và DataBinder required fields là hai cơ chế. | Đọc `getCode()` và biết nguồn phát sinh. |
| Có `ValidationMessages_vi.properties` nhưng Spring key không áp dụng | Nhầm Bean Validation message interpolation với Spring error-code resolution. | Phân biệt hai giai đoạn, cấu hình validator/MessageSource có chủ đích. |
| Client nhận tiếng Anh dù `Accept-Language: vi` | LocaleResolver/bundle fallback hoặc custom handler bỏ locale. | Test controller locale, dùng `MessageSource` với Locale phù hợp. |
| Message chứa giá trị mật khẩu đã nhập | Handler echo `rejectedValue` hoặc log full exception. | Redact input, trả mã và text ổn định. |
| Mã được prefixed nhưng bundle dùng key cũ | Đã bật `setPrefix("validation.")` mà không đổi keys. | Đồng bộ resolver + bundle; thêm integration tests. |

## 16. Checklist triển khai

- [ ] Phân biệt mã gốc (`typeMismatch`, `required`, `NotBlank`, custom code) với danh sách mã ứng viên.
- [ ] Hiểu mức độ ưu tiên **object.field → field → type → general** cho field errors.
- [ ] Hiểu global error chỉ có **object → general**.
- [ ] Xác minh object name của binder/`@ModelAttribute`; field name/Java type chính xác.
- [ ] Với list/map/array, quan sát các mã thêm cho indexed và unindexed paths.
- [ ] Dùng `MessageSource#getMessage(ObjectError, Locale)` để tận dụng toàn bộ fallback codes.
- [ ] Có `messages.properties` cùng `messages_vi.properties`/`messages_en.properties` và UTF-8.
- [ ] Kiểm tra `MessageSource`/locale resolution thực sự đang được framework dùng.
- [ ] Có fallback chung và policy khi không tìm thấy message, không lộ Java stack trace.
- [ ] Đặt `BindingResult` ngay sau object được validate nếu muốn xử lý lỗi cục bộ trong MVC.
- [ ] Không nhầm binding `typeMismatch` với JSON decoding lỗi hay Jakarta Bean Validation interpolation.
- [ ] Chạy unit tests cho `DefaultMessageCodesResolver` và MockMvc tests cho request locale.
- [ ] Không trả rejected values/PII; mã lỗi public và wording cần có chiến lược versioning rõ ràng.

**Kết luận:** Spring không buộc mỗi validation error chỉ có một chuỗi mã. `DefaultMessageCodesResolver` tạo **nhiều ứng viên theo mức độ cụ thể**, còn `MessageSource` chọn **câu thông báo theo Locale**. Thiết kế đúng object name, field name và Java type cho phép dịch thông báo chính xác mà vẫn dùng lại validator/binder, đồng thời duy trì fallback đủ rộng để ứng dụng không bị vỡ bản dịch khi thêm form hoặc refactor.

## Tài liệu tham khảo

- Spring Framework Reference — Resolving Error Codes to Error Messages: https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html
- Spring Framework Javadoc 6.2 — DefaultMessageCodesResolver và thứ tự mã: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html
- Spring Framework Reference — Validation Using Spring’s Validator Interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Javadoc 6.2 — MessageCodesResolver: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/MessageCodesResolver.html
- Spring Framework Javadoc 6.2 — BindingResult, FieldError, ObjectError: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework Javadoc 6.2 — WebMvcConfigurer#getMessageCodesResolver(): https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Boot — Internationalization (`messages.properties`, `spring.messages.basename`): https://docs.spring.io/spring-boot/reference/features/internationalization.html
- Spring Framework Reference — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
