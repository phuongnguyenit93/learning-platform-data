# MessageSourceResolvable và phân giải ObjectError hoặc FieldError

## 1. Tại sao lỗi validation cần được phân giải thông báo?

Một ứng dụng Spring Framework thường dùng cùng một tập quy tắc validation cho nhiều người dùng, nhưng câu thông báo lỗi phải phù hợp ngôn ngữ và ngữ cảnh.

Ví dụ cùng một lỗi “tên đăng nhập bắt buộc” có thể hiển thị:

- Tiếng Việt: **Tên đăng nhập không được để trống**.
- Tiếng Anh: **Username must not be blank**.

Không nên viết trực tiếp tiếng Việt vào mọi `@NotBlank(message="...")` hoặc ghép chuỗi từ `FieldError#getField()`. Nếu làm vậy, sẽ khó dùng chung một validator cho nhiều ngôn ngữ, khó tùy chỉnh nội dung theo từng form, và API dễ phụ thuộc thông báo mà provider đang sử dụng.

Spring có ba lớp vai trò quan trọng:

1. **`MessageSourceResolvable`**: *mô tả một yêu cầu dịch thông báo*: các mã ứng viên, các đối số của mẫu và câu mặc định.
2. **`ObjectError` / `FieldError`**: *mô tả lỗi của một đối tượng hay một thuộc tính*, đồng thời triển khai `MessageSourceResolvable` để có thể dịch.
3. **`MessageSource`**: *bộ giải quyết thông báo* dựa trên mã và `Locale`, ví dụ đọc `messages.properties` và `messages_vi.properties`.

Dòng quan trọng nhất khi muốn biến một lỗi thành thông báo cho người dùng là:

```java
String text = messageSource.getMessage(error, locale);
```

Ở đây `error` là `ObjectError` hoặc `FieldError` (hoặc bất kỳ `MessageSourceResolvable` nào). Lời gọi này ưu tiên tra cứu bằng những code mà lỗi đã mang, dùng arguments khi format và chỉ dùng default message nếu cần.

## 2. MessageSourceResolvable gồm những gì?

Giao diện nằm tại `org.springframework.context.MessageSourceResolvable`. Ba method chính:

```java
// Chữ ký API minh họa, không phải interface cần tự định nghĩa.
String[] getCodes();
Object[] getArguments();
String getDefaultMessage();
```

Trong API hiện hành các giá trị trên có thể là `null`. Bảng dưới đây chỉ rõ vai trò:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `getCodes()` | Danh sách mã thông báo theo thứ tự thử, từ đặc thù tới tổng quát | `NotBlank.signupForm.username`, `NotBlank.username`, `NotBlank.java.lang.String`, `NotBlank` |
| `getArguments()` | Giá trị chèn vào placeholder theo `MessageFormat`, có thể chứa một resolvable khác | Tên trường đã bản địa hóa, giá trị giới hạn, tham số constraint |
| `getDefaultMessage()` | Thông báo dự phòng nếu không tìm thấy mã phù hợp | `must not be blank` |

**Không phải mã đầu tiên luôn tồn tại trong bundle.** `MessageSource` thử từng code theo thứ tự; một mã chung hơn có thể là kết quả cuối cùng.

Một số lớp triển khai/quan hệ kế thừa:

```text
MessageSourceResolvable (interface)
      │
      └── DefaultMessageSourceResolvable
                 │
                 └── ObjectError (global/object-level error)
                          │
                          └── FieldError (field-level error)
```

`DefaultMessageSourceResolvable` là triển khai có thể tự tạo cho một thông báo bất kỳ. `ObjectError` là lỗi của object, `FieldError` là kiểu con của `ObjectError` nhưng thêm metadata riêng cho property.

### getCode() khác getCodes()

`DefaultMessageSourceResolvable#getCode()` thường trả **mã cuối cùng** trong danh sách, tức mã tổng quát nhất, ví dụ `NotBlank`. Trái lại, `getCodes()[0]` thường là mã ưu tiên cao nhất như `NotBlank.signupForm.username`.

Đừng dùng `getCode()` làm tiêu chí chọn bản dịch rồi bỏ qua các mã cụ thể. Nếu đã có `MessageSourceResolvable`, hãy truyền **cả object** cho `MessageSource#getMessage(resolvable, locale)` để giữ được thứ tự thử mã.

## 3. ObjectError và FieldError khác nhau ra sao?

### 3.1. ObjectError: lỗi của toàn đối tượng

`org.springframework.validation.ObjectError` mô tả lỗi không gắn với một thuộc tính cụ thể. Ví dụ form đăng ký có `password` và `confirmPassword` đều hợp lệ nếu xét riêng, nhưng hai giá trị không giống nhau.

Trong Spring `Validator`, có thể ghi lỗi tổng thể:

```java
if (!Objects.equals(form.getPassword(), form.getConfirmPassword())) {
    errors.reject(
        "passwordMismatch",
        new Object[]{"Mật khẩu"},
        "Hai mật khẩu không khớp");
}
```

Đây là **đoạn minh họa trong method `validate`**, cần `form`, `errors` và import `Objects`. `errors.reject(...)` ghi **global error**.

Một `ObjectError` quan trọng có:

- `getObjectName()`: ví dụ `signupForm`.
- `getCodes()`, `getArguments()`, `getDefaultMessage()` do cơ chế resolvable cung cấp.
- `getCode()`: thường mã tổng quát cuối danh sách.
- `contains(Class<?>)` và `unwrap(Class<?>)`: tùy trường hợp có thể truy xuất source exception hoặc `ConstraintViolation` đã được bao bọc bằng `wrap(...)`.

Với `errorCode=passwordMismatch` và `objectName=signupForm`, `DefaultMessageCodesResolver` thường tạo:

```text
passwordMismatch.signupForm
passwordMismatch
```

Nếu `messages_vi.properties` chứa `passwordMismatch.signupForm`, Spring ưu tiên câu riêng của biểu mẫu trước `passwordMismatch` chung.

### 3.2. FieldError: lỗi của một thuộc tính

`org.springframework.validation.FieldError` mở rộng `ObjectError` và thêm thông tin:

- `getField()`: trường bị lỗi, ví dụ `username` hoặc `shippingAddress.zipCode`.
- `getRejectedValue()`: giá trị bị từ chối (không nên tùy tiện log hoặc trả về client).
- `isBindingFailure()`: cho biết lỗi phát sinh từ binding/type conversion thay vì một lần kiểm tra validation thông thường.
- `getObjectName()`, `getCodes()`, `getArguments()`, `getDefaultMessage()` như `ObjectError`.

Ví dụ custom Spring validator:

```java
if (form.getUsername() == null || form.getUsername().isBlank()) {
    errors.rejectValue(
        "username",
        "required",
        new Object[]{"Tên đăng nhập"},
        "Tên đăng nhập là bắt buộc");
}
```

Đây là đoạn minh họa dùng `Errors.rejectValue`. Spring tạo `FieldError` có field `username` và dãy codes theo object name/field type. Với object tên `signupForm`, kiểu String và code `required`, danh sách điển hình là:

```text
required.signupForm.username
required.username
required.java.lang.String
required
```

Tương tự, lỗi `typeMismatch` khi binder không chuyển được `"abc"` sang `Integer` có thể được biểu diễn bằng `FieldError` với `isBindingFailure() == true`.

**Phân biệt nguồn gốc:** `FieldError` không chỉ đến từ Jakarta Bean Validation; nó có thể xuất phát từ `WebDataBinder`, Spring `Validator` hoặc code chủ động `rejectValue(...)`.

### 3.3. Các hàm truy xuất lỗi trên BindingResult

`BindingResult` kế thừa `Errors` và cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `hasErrors()` | Có bất kỳ lỗi nào không |
| `getAllErrors()` | Mọi `ObjectError` gồm cả `FieldError` |
| `getGlobalErrors()` | Chỉ lỗi object-level |
| `getFieldErrors()` | Chỉ lỗi thuộc tính |
| `getFieldErrors("username")` | Danh sách lỗi của một thuộc tính |
| `getFieldError("username")` | Lỗi đầu tiên của thuộc tính, có thể `null` |
| `getErrorCount()` | Tổng số lỗi |
| `getObjectName()` | Tên đối tượng được bind |

Cách hiển thị thường dùng:

```java
for (ObjectError error : result.getAllErrors()) {
    String text = messageSource.getMessage(error, locale);

    if (error instanceof FieldError fieldError) {
        System.out.println(
            fieldError.getField() + ": " + text);
    } else {
        System.out.println("form: " + text);
    }
}
```

Đây là **fragment tích hợp**, với `result` là `BindingResult` và `messageSource`, `locale` đã có. Kiểu `ObjectError` bao gồm cả `FieldError`; do đó dùng `instanceof FieldError` để phân nhánh, thay vì ngầm coi mọi `ObjectError` là global error.

## 4. DefaultMessageCodesResolver sinh thứ tự mã ra sao?

Spring dùng `MessageCodesResolver`, mặc định thường là `DefaultMessageCodesResolver`, để tạo dãy mã dự phòng từ error code nguyên thủy, object name, field name và Java field type.

### 4.1. Object-level

Giả sử `errors.reject("invalidCombination")` với tên object `checkout`:

```text
invalidCombination.checkout
invalidCombination
```

### 4.2. Field-level

Giả sử `errors.rejectValue("quantity","Min")`, object name `orderForm` và field type `java.lang.Integer`:

```text
Min.orderForm.quantity
Min.quantity
Min.java.lang.Integer
Min
```

Thứ tự từ *cụ thể nhất* tới *tổng quát nhất*:

1. Mã riêng cho một field trong một form.
2. Mã dùng cho mọi field có cùng tên.
3. Mã dùng cho Java type tương ứng.
4. Mã chung cho mọi trường có cùng constraint/error code.

Lưu ý: lỗi do một provider Bean Validation đưa vào `BindingResult` có thể có arguments cấu trúc riêng của provider/adapter. **Không được đoán vị trí argument** chỉ bằng tên `Min` hay `NotBlank`; hãy kiểm tra mã/arguments ở tình huống thực tế trước khi viết template có `{0}`, `{1}`.

### 4.3. Nested properties và collection indices

Với field như `addresses[0].zipCode`, resolver có thể tạo các mã cho index cụ thể và cả dạng đường dẫn đã bỏ index, ví dụ:

```text
typeMismatch.orderForm.addresses[0].zipCode
typeMismatch.orderForm.addresses.zipCode
typeMismatch.addresses[0].zipCode
typeMismatch.addresses.zipCode
typeMismatch.zipCode
typeMismatch.java.lang.String
typeMismatch
```

Đây là dạng minh họa trường hợp field type String. Số mã, tên đường dẫn và Java type phụ thuộc cấu trúc property thực tế. Ý tưởng là có thể dịch riêng lỗi ở phần tử chỉ định hoặc dùng mã tổng quát cho mọi phần tử.

### 4.4. Có thể tùy biến resolver

`DefaultMessageCodesResolver` cho phép cấu hình prefix hoặc format mã, ví dụ prefix `validation.`. Trong MVC, nếu muốn chọn resolver tùy biến cho binding, có thể sử dụng hạ tầng WebBindingInitializer hoặc callback cấu hình MVC phù hợp, nhưng chỉ nên làm khi đã thống nhất naming convention trên toàn codebase.

Mọi thay đổi cách sinh mã phải đi kèm cập nhật message bundles và tests; nếu đổi prefix mà quên cập nhật `messages_vi.properties`, lỗi có thể rơi về default message hoặc `NoSuchMessageException`.

## 5. MessageSource phân giải theo thứ tự nào?

Giao diện `org.springframework.context.MessageSource` có ba overload thông dụng:

```java
String getMessage(
    String code, Object[] args, String defaultMessage, Locale locale);

String getMessage(
    String code, Object[] args, Locale locale);

String getMessage(
    MessageSourceResolvable resolvable, Locale locale);
```

Đây là **chữ ký API giản lược**; bản thật có nullable annotations và kiểu param tương ứng.

Khi gọi `messageSource.getMessage(fieldError, locale)`, Spring về cơ bản:

1. Lấy các codes của `fieldError.getCodes()` theo thứ tự.
2. Thử tra mã thứ nhất trong nguồn thông báo phù hợp `locale`.
3. Nếu không thấy, thử mã tiếp theo và các bước fallback của message source.
4. Khi tìm được mẫu, giải quyết arguments và dùng `java.text.MessageFormat` khi cần để thay `{0}`, `{1}`, v.v.
5. Nếu không mã nào được tìm thấy, dùng `getDefaultMessage()` nếu khả dụng.
6. Nếu thiếu cả mã tìm thấy lẫn default message, overload nhận resolvable có thể ném `NoSuchMessageException`.

**Không phải `MessageSourceResolvable` tự đi đọc file translations.** Nó là dữ liệu mô tả yêu cầu; `MessageSource` mới thực hiện lookup.

Ví dụ bundle:

```properties
# messages_vi.properties
required.signupForm.username=Ten dang nhap khong duoc de trong
required=Truong nay la bat buoc
passwordMismatch.signupForm=Hai mat khau khong khop
```

Và:

```properties
# messages_en.properties
required.signupForm.username=Username must not be blank
required=This field is required
passwordMismatch.signupForm=Passwords do not match
```

Các khối trên dùng nội dung ASCII để minh họa key/value; ứng dụng thật có thể ghi tiếng Việt đầy đủ dấu với UTF-8. Trong `.properties`, khóa bao gồm dấu chấm là một chuỗi key bình thường, không phải cú pháp truy cập thuộc tính Java.

Nếu Bundle có đồng thời `required.signupForm.username` và `required`, lỗi của `signupForm.username` chọn khóa đầu tiên. Một field khác như `signupForm.email` nếu không có key cụ thể có thể rơi về `required`.

## 6. Ví dụ độc lập, Java 17 + Spring Framework 6.2.6

Ví dụ này không cần chạy HTTP server. Nó tạo một `BeanPropertyBindingResult` cho form, chủ động ghi hai `FieldError` và một `ObjectError`, cấu hình `StaticMessageSource` cho tiếng Việt và tiếng Anh, sau đó gọi `getMessage(error, locale)`.

Nhờ sử dụng `StaticMessageSource`, chương trình kiểm chứng **chính xác** thứ tự lookup mà không phụ thuộc file trên classpath hay request locale.

### 6.1. Cấu trúc file

```text
message-resolution-demo/
├── pom.xml
└── src/main/java/demo/MessageResolutionDemo.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>message-resolution-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.6</version>
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

`spring-context` kéo theo những Spring modules cần thiết cho `StaticMessageSource` và `BeanPropertyBindingResult`. Java 17 đủ cho mẫu này, không cần `spring-boot-starter-web`, Servlet container hoặc Jakarta Validation provider vì các lỗi được tạo trực tiếp qua Spring `Errors` API.

### 6.3. MessageResolutionDemo.java

```java
package demo;

import java.util.Locale;

import org.springframework.context.support.DefaultMessageSourceResolvable;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public class MessageResolutionDemo {

    private static final Locale VI = Locale.forLanguageTag("vi-VN");
    private static final Locale EN = Locale.ENGLISH;

    // Không chạy HTTP binding: DTO chỉ để cung cấp metadata field type.
    public static class SignupForm {
        private String username;
        private String email;

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }

    private static void printError(
            String label,
            ObjectError error,
            StaticMessageSource messages) {

        System.out.println(
            label + " codes=" + String.join(" > ", error.getCodes()));

        System.out.println(
            label + " vi=" + messages.getMessage(error, VI));

        System.out.println(
            label + " en=" + messages.getMessage(error, EN));
    }

    public static void main(String[] args) {
        StaticMessageSource messages = new StaticMessageSource();

        messages.addMessage("label.username", VI, "Tên đăng nhập");
        messages.addMessage("label.username", EN, "Username");
        messages.addMessage("label.email", VI, "Email");
        messages.addMessage("label.email", EN, "Email");

        // Bản dịch cụ thể cho một field của một form.
        messages.addMessage("required.signupForm.username", VI,
                "{0} không được để trống");
        messages.addMessage("required.signupForm.username", EN,
                "{0} must not be blank");

        // Bản dịch chung làm fallback cho email và các field khác.
        messages.addMessage("required", VI, "{0} là bắt buộc");
        messages.addMessage("required", EN, "{0} is required");

        // Lỗi object-level.
        messages.addMessage("profileMismatch.signupForm", VI,
                "Hồ sơ không nhất quán");
        messages.addMessage("profileMismatch.signupForm", EN,
                "Profile is inconsistent");

        SignupForm form = new SignupForm();
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(form, "signupForm");

        // Arguments cũng có thể là resolvable => dịch tên field.
        errors.rejectValue(
                "username",
                "required",
                new Object[] {
                    new DefaultMessageSourceResolvable("label.username")
                },
                "Username missing");

        errors.rejectValue(
                "email",
                "required",
                new Object[] {
                    new DefaultMessageSourceResolvable("label.email")
                },
                "Email missing");

        errors.reject(
                "profileMismatch", new Object[0], "Profile mismatch");

        FieldError username = errors.getFieldError("username");
        FieldError email = errors.getFieldError("email");
        ObjectError global = errors.getGlobalError();

        printError("USERNAME", username, messages);
        printError("EMAIL", email, messages);
        printError("GLOBAL", global, messages);

        // Mã không có trong bundle: sử dụng defaultMessage.
        DefaultMessageSourceResolvable missing =
                new DefaultMessageSourceResolvable(
                    new String[] {"missing.code"},
                    null,
                    "Thông báo dự phòng");

        System.out.println(
                "FALLBACK vi=" + messages.getMessage(missing, VI));
    }
}
```

Phần code gọi `getFieldError(...)` và `getGlobalError()` sau khi chính chương trình đã thêm ba lỗi, nên trong luồng này không có giá trị `null` cần xử lý. Khi dùng trong controller thật, luôn kiểm tra `null` hoặc lặp qua danh sách.

### 6.4. Chạy chương trình

Mở terminal tại thư mục có `pom.xml`, cài Java 17+ và Maven 3.x:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.MessageResolutionDemo
```

Phần output do `System.out.println` in (không bao gồm log plugin/Maven nếu môi trường có log riêng):

```text
USERNAME codes=required.signupForm.username > required.username > required.java.lang.String > required
USERNAME vi=Tên đăng nhập không được để trống
USERNAME en=Username must not be blank
EMAIL codes=required.signupForm.email > required.email > required.java.lang.String > required
EMAIL vi=Email là bắt buộc
EMAIL en=Email is required
GLOBAL codes=profileMismatch.signupForm > profileMismatch
GLOBAL vi=Hồ sơ không nhất quán
GLOBAL en=Profile is inconsistent
FALLBACK vi=Thông báo dự phòng
```

Giải thích kết quả:

- `USERNAME` có một mã riêng trong `StaticMessageSource` là `required.signupForm.username`. Vì đó là code đầu tiên và có translation, nó thắng mã tổng quát `required`.
- `EMAIL` không có translation riêng, vì vậy Spring thử mã đặc thù rồi dùng mã chung `required`.
- `getArguments()` của hai field errors chứa một `DefaultMessageSourceResolvable` để tra `label.username` hoặc `label.email` bằng đúng locale hiện tại. Vì thế tên hiển thị cũng được dịch.
- `GLOBAL` là `ObjectError` nên có hai mã ứng viên, không thêm field name/field type.
- `FALLBACK` minh họa `getDefaultMessage()` chỉ được dùng khi không tìm thấy `missing.code`.

Đây là một chương trình **minh họa cơ chế phân giải thông báo**, không khởi tạo Spring MVC controller, không tự chạy Jakarta `@Valid` và không dùng HTTP status. Khi tích hợp với MVC, các lỗi do `WebDataBinder` hoặc Bean Validation sinh ra có thể có chi tiết arguments và default message khác ví dụ.

## 7. Dùng MessageSource trong ứng dụng Spring Boot / Spring MVC

Ví dụ độc lập sử dụng `StaticMessageSource` để kiểm chứng logic. Trong web app thật, cách phổ biến là cấu hình message bundles.

### 7.1. Tạo tài nguyên theo locale

Với ứng dụng Spring Boot, thông thường đặt dưới `src/main/resources`:

```text
src/main/resources/
├── messages.properties
├── messages_vi.properties
└── messages_en.properties
```

Ví dụ `messages.properties` có thể chứa bản mặc định không phụ thuộc locale:

```properties
required=Value is required
profileMismatch=Profile information is inconsistent
```

Trong `messages_vi.properties` (lưu UTF-8):

```properties
NotBlank.signupForm.username=Tên đăng nhập không được để trống
NotBlank.username=Giá trị này không được để trống
NotBlank=Không được để trống
typeMismatch.signupForm.age=Tuổi phải là một số hợp lệ
profileMismatch.signupForm=Thông tin hồ sơ chưa nhất quán
```

Trong `messages_en.properties`:

```properties
NotBlank.signupForm.username=Username must not be blank
NotBlank.username=This value must not be blank
NotBlank=Must not be blank
typeMismatch.signupForm.age=Age must be a valid number
profileMismatch.signupForm=Profile information is inconsistent
```

Khóa `NotBlank.signupForm.username` chỉ áp dụng khi object name đúng `signupForm`, field name đúng `username` và error code đúng `NotBlank`. Nếu controller dùng `@ModelAttribute("registration")` thì tên object đổi, cần cập nhật bundle hoặc dùng fallback `NotBlank.username`/`NotBlank`.

Đây là **ví dụ thông báo i18n tích hợp**, không cần đưa trực tiếp vào project Java standalone ở mục 6.

### 7.2. MessageSource bean và encoding

Spring Boot thông thường tự cấu hình `MessageSource` dựa trên `messages*.properties` khi có file bundle phù hợp. Có thể dùng:

```properties
# application.properties (nếu muốn tường minh)
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

Đừng khai báo thêm một bean `MessageSource` thứ hai thiếu chủ đích vì có thể làm thay đổi cơ chế resolution/parent source. Với Spring Framework thuần, có thể khai báo bean tên `messageSource` kiểu `ResourceBundleMessageSource` hoặc `ReloadableResourceBundleMessageSource` và cấu hình basename/encoding tương ứng.

`MessageSource` là **backend lấy thông báo**; nó không thay thế `Validator`. Có bundle nhưng controller không bật validation thì chưa chắc lỗi được tạo, cũng giống có `@NotBlank` nhưng thiếu Jakarta Validation provider thì không có ràng buộc được thực thi theo đường mong đợi.

### 7.3. Chọn Locale

Trong Spring MVC, `Locale` thường được lấy từ resolver của request, ví dụ header `Accept-Language`. Trong một handler hoặc advice, có thể nhận tham số `Locale` hoặc dùng `LocaleContextHolder.getLocale()` khi đang ở đúng request context.

Ví dụ:

```java
@GetMapping("/locale-demo")
public String localeDemo(Locale locale, MessageSource messages) {
    // Cú pháp minh họa: MessageSource không nên mặc định
    // được giả định là method argument resolver trực tiếp.
    return messages.getMessage(
        "welcome", null, "Hello", locale);
}
```

**Lưu ý:** Đoạn trên chỉ minh họa ý tưởng chứ **không phải chữ ký Spring MVC khuyến nghị**, vì `MessageSource` cần được inject vào controller như dependency thông thường. Ví dụ đúng thiết kế là:

```java
@RestController
public class LocaleDemoController {

    private final MessageSource messageSource;

    public LocaleDemoController(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @GetMapping("/locale-demo")
    public String demo(Locale locale) {
        return messageSource.getMessage(
            "welcome", null, "Hello", locale);
    }
}
```

Đây là fragment tích hợp, cần imports và bean `MessageSource`. Tránh dùng `Locale.getDefault()` của server để chọn bản dịch cho HTTP client; nó có thể không trùng ngôn ngữ người dùng.

### 7.4. ControllerAdvice để trả lỗi có thông báo dịch

Khi `@Valid @RequestBody` DTO không hợp lệ, MVC thường ném `MethodArgumentNotValidException` nếu không có `BindingResult` liền kề và không có yếu tố làm bật whole-method validation.

Một advice minh họa:

```java
@RestControllerAdvice
public class ValidationAdvice {

    private final MessageSource messages;

    public ValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<List<ApiError>> handle(
            MethodArgumentNotValidException ex,
            Locale locale) {

        List<ApiError> body = ex.getBindingResult()
            .getAllErrors()
            .stream()
            .map(error -> {
                String field = (error instanceof FieldError fe)
                    ? fe.getField() : "";
                String code = error.getCode();
                String text = messages.getMessage(error, locale);
                return new ApiError(field, code, text);
            })
            .toList();

        return ResponseEntity.badRequest().body(body);
    }

    public record ApiError(String field, String code, String message) {}
}
```

Đây là **fragment tích hợp**, cần import các annotation, `ResponseEntity`, `List`, `MessageSource`, `MethodArgumentNotValidException` và các error classes. Khi dùng thật, cần cân nhắc cách phân loại lỗi global, HTTP contract, localization fallback, và giữ `code` ổn định cho client.

Điểm quan trọng của fragment:

- Truyền **chính `ObjectError`/`FieldError`** cho `messages.getMessage(error, locale)`, không chỉ gửi `error.getCode()`.
- Mã lỗi public có thể dựa trên `error.getCode()` hoặc mã ứng dụng ổn định, nhưng không cần đưa mọi mã nội bộ vào JSON.
- Bản dịch **phù hợp request locale**.
- Không trả trực tiếp `FieldError#getRejectedValue()` vì có thể lộ password, token, số giấy tờ hoặc dữ liệu nhạy cảm.

### 7.5. Method validation và Spring WebFlux

Trong Spring MVC 6.1+, constraint trực tiếp trên method parameter hoặc return value có thể kích hoạt built-in method validation và phát `HandlerMethodValidationException`. Nó dùng các abstraction kết quả validation như `MethodValidationResult`, `ParameterValidationResult` với các `MessageSourceResolvable` có thể được dịch theo cùng `MessageSource`.

Với `@Validated` trên Spring service bean, AOP method validation có thể phát `ConstraintViolationException` hoặc `MethodValidationException` tùy `MethodValidationPostProcessor#setAdaptConstraintViolations(...)`; đừng bắt một loại exception rồi cho rằng tất cả validation paths đều trùng nhau.

Trong Spring WebFlux, các exception của argument validation và method validation có ngữ cảnh khác với MVC, nhưng ý tưởng dùng `MessageSourceResolvable` để biểu diễn lỗi và dùng `MessageSource` để dịch vẫn giữ nguyên. Bài này tập trung vào ý nghĩa và resolution của `ObjectError`/`FieldError`, không áp đặt một exception handler duy nhất cho mọi web stack.

## 8. Cách xử lý default message và NoSuchMessageException

Có ba tình huống:

| Trạng thái lookup | Kết quả |
| --- | --- |
| Có translation cho code ưu tiên cao nhất | Dùng translation đó |
| Không có translation cụ thể nhưng có mã chung | Thử mã tiếp theo và dùng mã chung |
| Không có translation nào, có `getDefaultMessage()` | Dùng thông báo dự phòng |
| Không có translation và không có default message | Có thể ném `NoSuchMessageException` |

Ví dụ hai overload:

```java
// Có defaultMessage trực tiếp: không tìm thấy code thì trả fallback.
String text = messageSource.getMessage(
    "unknown.code", null, "Thông báo dự phòng", locale);

// Không cung cấp default: có thể ném NoSuchMessageException.
String strict = messageSource.getMessage(
    "unknown.code", null, locale);
```

Đây là fragment, `messageSource` và `locale` đã được inject/xác định.

Có tùy chọn `AbstractMessageSource#setUseCodeAsDefaultMessage(true)` cho phép dùng chính code làm fallback khi phát triển. Tuy nhiên **không nên lệ thuộc vào đó trong production**, vì người dùng có thể nhìn thấy key kỹ thuật thay vì thông báo thân thiện và thiếu message bundle có thể bị bỏ sót trong tests.

**Default message không đồng nghĩa bản dịch.** Ví dụ provider có thể đặt default message tiếng Anh; nếu không tìm thấy bản dịch tiếng Việt, hiển thị lại default tiếng Anh là fallback được phép, nhưng chưa đạt yêu cầu đa ngữ. Hãy kiểm thử đầy đủ bundle của các locale được hỗ trợ và có quyết định fallback rõ ràng.

## 9. Arguments, MessageFormat và tên field có thể dịch tiếp

Một mẫu thông báo có placeholder:

```properties
required={0} là bắt buộc
size.invalid={0} phải có từ {1} đến {2} ký tự
```

Khi arguments được cung cấp:

```java
new Object[] {
    new DefaultMessageSourceResolvable("label.username"),
    3,
    20
}
```

thì một nguồn thông báo hỗ trợ `MessageSourceResolvable` lồng nhau có thể:

1. Dịch `label.username` thành `Tên đăng nhập` cho locale `vi-VN`.
2. Đưa `Tên đăng nhập`, `3` và `20` vào mẫu bằng `MessageFormat`.
3. Cho kết quả: `Tên đăng nhập phải có từ 3 đến 20 ký tự`.

**Không nhất thiết mọi lỗi Bean Validation tạo arguments theo cùng thứ tự.** Các adapter có thể thêm field label, annotation attributes, constraint values hoặc các kiểu argument khác. Kiểm tra `error.getArguments()` trong integration test trước khi thiết kế message templates có nhiều placeholder.

### Dấu nháy đơn trong MessageFormat

Khi message có arguments, `MessageFormat` dùng dấu nháy đơn để escape cú pháp. Nếu thông báo có dấu `'` thật, có thể cần viết thành `''` trong pattern. Điều này đặc biệt quan trọng với thông báo tiếng Anh chứa `don't` hoặc tên có apostrophe; nếu không, pattern có thể mất ký tự nháy hoặc xử lý placeholder sai.

### Ngữ nghĩa của getDefaultMessage()

Nếu một resolvable không có mã khớp, default message có thể cũng được format với arguments. Vì thế đừng đặt mẫu dự phòng có placeholder sai số lượng/thứ tự, đặc biệt khi nó được provider/adapter sinh ra. Với nội dung do ứng dụng tự kiểm soát, chọn default đơn giản, an toàn và có test.

## 10. Phân biệt mã lỗi với tên field và thông điệp

Trong thiết kế API, các trường dữ liệu thường bị nhầm:

| Dữ liệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `FieldError#getField()` | `username` | Tên property phía server, không phải lời nói cho người dùng |
| `ObjectError#getObjectName()` | `signupForm` | Tên object trong binding context |
| `getCodes()[0]` | `NotBlank.signupForm.username` | Mã ưu tiên cao cho translation lookup |
| `getCode()` | `NotBlank` | Mã tổng quát, thường cuối danh sách |
| `getDefaultMessage()` | `must not be blank` | Mẫu/câu dự phòng |
| `messageSource.getMessage(error, vi)` | `Tên đăng nhập không được để trống` | Thông điệp đã phân giải theo locale |
| `FieldError#getRejectedValue()` | Giá trị client nhập | Dữ liệu có thể nhạy cảm, không phải thông báo |

**Không dùng bản dịch làm error code public.** Client không nên phải parse chuỗi tiếng Việt để phân nhánh xử lý. Hãy trả về mã máy đọc ổn định (ví dụ `VALIDATION_REQUIRED`) kèm text đã được dịch để hiển thị; server vẫn có thể dùng các mã `NotBlank.*` nội bộ để tìm message.

Ở mức form HTML, view engine như Thymeleaf có thể sử dụng model attribute và binding result để hiển thị lỗi với các tag/expressions tương ứng. Tuy nhiên phải để framework escape nội dung không tin cậy, không ghép HTML từ rejected value.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân phổ biến | Cách khắc phục |
| --- | --- | --- |
| `error.getDefaultMessage()` luôn hiện tiếng Anh | Không dùng `MessageSource`/không tìm thấy bản dịch | Gọi `getMessage(error, locale)` và tạo bundles phù hợp |
| `NotBlank.username` không được sử dụng | Có mã cụ thể hơn được tìm thấy trước | Kiểm tra toàn bộ `error.getCodes()` theo thứ tự |
| `@NotBlank` trên DTO không phát sinh lỗi | Thiếu provider hoặc chưa kích hoạt `@Valid`/`@Validated` | Kiểm tra starter-validation, validator/group và đường MVC |
| Không dịch được field name trong placeholder | Argument chỉ là raw String hoặc thiếu `label.*` | Dùng nested `MessageSourceResolvable` khi phù hợp |
| `NoSuchMessageException` | Không có key và không có default message | Cung cấp bundle/fallback và test locale |
| Chuỗi có apostrophe hiển thị sai | Mẫu có `MessageFormat` nhưng quote chưa escape | Dùng nháy đơn kép khi mẫu có arguments |
| Không thấy lỗi toàn object | Handler chỉ duyệt `getFieldErrors()` | Dùng `getAllErrors()` hoặc thêm `getGlobalErrors()` |
| Lỗi type conversion bị coi là `@Min` | Nhầm binding failure với validation failure | Kiểm tra `FieldError#isBindingFailure()` |
| Thông báo vi sai ngôn ngữ | Locale lấy từ JVM/server thay vì request | Dùng request locale qua resolver/advice |
| Response lộ mật khẩu người dùng | Serialize nguyên `FieldError` hoặc `getRejectedValue()` | Tạo error DTO an toàn, kiểm tra field exposure |
| Hardcode mã theo tên tham số Java | Object name/field name thay đổi khi refactor | Test mã, chuẩn hóa error code nếu là public contract |
| Bundle không tìm thấy dù file có tồn tại | basename, encoding, path hoặc locale suffix không khớp | Kiểm tra cấu hình `spring.messages.*` và file resources |
| Client phụ thuộc thông báo tiếng Việt | Không tách machine code khỏi localized display | Trả cả code ổn định và message đã dịch |

## 12. Checklist kiểm thử

Để kiểm thử tính đúng đắn của i18n validation:

1. Với `FieldError` cụ thể, xác nhận `getCodes()` chứa tên object, tên field, type và fallback theo resolver thực tế.
2. Khi có key cụ thể và key chung, xác nhận key cụ thể được chọn.
3. Khi bỏ key cụ thể, xác nhận lookup rơi về key chung.
4. Với `ObjectError`, xác nhận không gắn thêm field code sai ngữ cảnh.
5. Với `getArguments()` chứa nested resolvable, xác nhận cả field label và thông báo chính được dịch cùng locale.
6. Với `NoSuchMessageException`, xác định default/fallback policy phù hợp.
7. Kiểm thử `vi-VN` và `en`, đồng thời một locale chưa hỗ trợ.
8. Kiểm tra placeholder số, ngày và apostrophe theo `MessageFormat`.
9. Với form thực tế, kiểm tra `BindingResult#getGlobalErrors()` và `getFieldErrors()`.
10. Với request API, xác nhận response không chứa rejected value nhạy cảm hay stack trace.
11. Khi thay tên `@ModelAttribute`, refactor property hoặc đổi validation groups, chạy lại contract tests cho message codes.
12. Phân biệt lỗi parse JSON/type conversion, validation field, method validation để advice bắt đúng loại exception.

Unit test trên `StaticMessageSource` phù hợp để hiểu độ ưu tiên và fallback. Integration test với `MockMvc`/Spring context cần thiết để xác nhận những mã do binder/validator thực sự sinh ra, locale được chọn và message bundles được nạp đúng.

## 13. Tổng kết

**`MessageSourceResolvable` là mô tả “cần giải quyết thông báo nào”, còn `MessageSource` là dịch vụ tra cứu bản dịch theo `Locale`.** `ObjectError` và `FieldError` triển khai hợp đồng resolvable, vì thế có thể truyền trực tiếp lỗi cho `messageSource.getMessage(error, locale)`.

**`ObjectError`** đại diện lỗi toàn object; **`FieldError`** thêm tên field, giá trị bị từ chối và cờ binding failure. Spring thường sinh nhiều mã thông báo từ cụ thể đến tổng quát bằng `DefaultMessageCodesResolver`. Bằng cách định nghĩa bundles đúng thứ tự ưu tiên và bảo đảm arguments/default messages nhất quán, bạn có thể dùng chung một hệ thống validation cho nhiều ngôn ngữ mà không làm client phụ thuộc trực tiếp vào câu thông báo.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Internationalization using `MessageSource`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 Javadoc — `MessageSourceResolvable`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/MessageSourceResolvable.html
- Spring Framework 6.2 Javadoc — `MessageSource`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/MessageSource.html
- Spring Framework 6.2 Javadoc — `DefaultMessageSourceResolvable`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/support/DefaultMessageSourceResolvable.html
- Spring Framework 6.2 Javadoc — `ObjectError`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/ObjectError.html
- Spring Framework 6.2 Javadoc — `FieldError`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 Javadoc — `DefaultMessageCodesResolver`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html
- Spring Framework 6.2 Javadoc — `Errors` và `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/Errors.html
- Spring MVC 6.2 — Validation và lỗi form: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — Error responses & internationalization: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html