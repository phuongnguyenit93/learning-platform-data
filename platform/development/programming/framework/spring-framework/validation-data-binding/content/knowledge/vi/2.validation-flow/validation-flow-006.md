# Thu thập lỗi binding và tiếp tục xử lý các trường khác

Trong Spring Framework, **data binding** ánh xạ dữ liệu đầu vào (thường là chuỗi từ biểu mẫu HTTP) vào thuộc tính của một đối tượng Java. Một giá trị không chuyển được kiểu không nhất thiết làm toàn bộ lượt **property binding** dừng lại: Spring có thể ghi lỗi của trường đó vào `BindingResult`, đồng thời tiếp tục bind những trường khác hợp lệ.

Bài này tập trung vào **luồng xử lý lỗi khi bind từng thuộc tính** bằng `DataBinder` / `WebDataBinder` và cách controller Spring MVC nhận, kiểm tra, phản hồi các lỗi đó. Khả năng tiếp tục được mô tả cho các lỗi binding thông thường đã được binder xử lý; không có nghĩa mọi ngoại lệ khi đọc request, tạo đối tượng hoặc chạy ứng dụng đều được tự động thu thập.

## 1. Tình huống và kết quả mong đợi

Giả sử biểu mẫu đăng ký gửi ba trường:

~~~text
name=Lan
age=abc
email=lan@example.com
~~~

Đối tượng đích có `name: String`, `age: int` và `email: String`. Spring bind được `name`, không thể chuyển `"abc"` thành số nguyên cho `age`, rồi vẫn bind được `email`. Sau lượt binding:

- `name` chứa `"Lan"` và `email` chứa `"lan@example.com"`.
- `age` không nhận giá trị không hợp lệ; nó giữ giá trị đang có trước khi gán lỗi (ví dụ 18 nếu được khởi tạo là 18).
- `BindingResult` có lỗi cho trường `age`, gồm mã lỗi, giá trị bị từ chối và thông tin đây là lỗi binding.
- **Ứng dụng phải kiểm tra lỗi trước khi dùng hoặc lưu đối tượng**. Bind được một phần không đồng nghĩa với dữ liệu nghiệp vụ hợp lệ.

Lợi ích là người dùng có thể thấy *tất cả lỗi đã thu thập* sau một lần gửi biểu mẫu và không phải nhập lại các trường đúng. Nhưng việc tiếp tục xử lý trường khác không phải quyết định “bỏ qua lỗi để lưu dữ liệu”.

## 2. Luồng xử lý từ đầu vào đến BindingResult

~~~text
Dữ liệu đầu vào (Map/property values hoặc form HTTP)
                |
                v
Tạo hoặc lấy đối tượng đích; khởi tạo DataBinder
                |
                v
Duyệt các thuộc tính được phép bind
                |
       +--------+---------+
       |                  |
 Chuyển/gán thành công   Không chuyển/gán được thuộc tính
       |                  |
 Cập nhật thuộc tính    Ghi FieldError vào BindingResult
       |                  |
       +--------+---------+
                |
                v
Tiếp tục xử lý các thuộc tính khác
                |
                v
(Theo cấu hình) kiểm tra validation trên đối tượng
                |
                v
Đọc BindingResult: lỗi binding + lỗi validation
                |
       +--------+---------+
       |                  |
   Có lỗi             Không có lỗi
       |                  |
Hiển thị/trả lỗi      Tiếp tục nghiệp vụ
Không lưu dữ liệu
chưa hợp lệ
~~~

**Các điểm cần phân biệt:**

1. **Binding** chuyển đổi và gán dữ liệu cho thuộc tính (ví dụ `String` → `int`). Lỗi chuyển kiểu thường sinh `FieldError` có mã `typeMismatch`.
2. **Validation** kiểm tra ràng buộc sau khi có dữ liệu (ví dụ tuổi phải ≥ 18, tên không rỗng). Validator có thể thêm lỗi vào **cùng** `BindingResult`; annotation `@Valid` / `@Validated` không thay thế binding.
3. **Xử lý request và tạo đối tượng** là các giai đoạn liên quan nhưng có thể gặp ngoại lệ riêng. JSON sai cú pháp với `@RequestBody` hoặc lỗi khởi tạo target không thuộc bảo đảm “một field lỗi, field sau vẫn được bind” của property binding.
4. Việc “tiếp tục” áp dụng cho các thuộc tính có thể xử lý độc lập. Không nên suy ra thứ tự gán luôn cố định, hay các setter có tác dụng phụ sẽ được rollback khi trường khác sai.

## 3. Các API chính và ý nghĩa của lỗi

| Thành phần | Trách nhiệm |
|---|---|
| `DataBinder` | Nhận target và tập giá trị cần bind; phối hợp chuyển kiểu, gán thuộc tính, thu thập lỗi. |
| `WebDataBinder` | Biến thể phục vụ môi trường web, dùng trong xử lý đối tượng biểu mẫu của Spring MVC. |
| `MutablePropertyValues` / `PropertyValues` | Đại diện các cặp tên thuộc tính và giá trị đầu vào khi dùng binder trực tiếp. |
| `BindingResult` | Kết quả của một đối tượng đích: chứa lỗi trường, lỗi toàn đối tượng và một số dữ liệu binding khác. |
| `FieldError` | Thông tin lỗi của một trường, như tên trường, mã lỗi, giá trị bị từ chối và cờ lỗi binding. |
| `ObjectError` | Lỗi ở cấp đối tượng, không nhất thiết gắn với một trường. |
| `Errors` | Interface đọc/ghi lỗi chung; `BindingResult` mở rộng nó để cung cấp thông tin binding. |

Các thao tác phổ biến:

- `result.hasErrors()`: có ít nhất một lỗi trường hoặc lỗi đối tượng?
- `result.getFieldErrors()`: lấy danh sách lỗi theo trường; một trường có thể có nhiều lỗi.
- `result.getFieldError("age")`: lấy lỗi đầu tiên của trường `age`, có thể trả `null`.
- `result.getGlobalErrors()`: các lỗi cấp đối tượng.
- `result.getAllErrors()`: cả lỗi trường lẫn lỗi đối tượng.
- `fieldError.getRejectedValue()`: giá trị đầu vào bị từ chối (cần xử lý an toàn khi hiển thị/log).
- `fieldError.getCode()`: mã lỗi tổng quát, thường là `typeMismatch` với lỗi chuyển kiểu.
- `fieldError.isBindingFailure()`: `true` khi lỗi đại diện cho thất bại binding; lỗi ràng buộc do validator tạo thường có cờ `false`.
- `result.getSuppressedFields()`: các trường bị loại khỏi binding theo quy tắc cho phép/chặn; **không mặc định đồng nghĩa với FieldError**.

`FieldError.getCodes()` có thể trả nhiều mã theo mức độ cụ thể (chẳng hạn mã gắn object/field rồi đến mã `typeMismatch`) để `MessageSource` chọn thông báo phù hợp. Không nên phụ thuộc vào toàn bộ danh sách mã hay nội dung exception message để xác định logic nghiệp vụ; ưu tiên mã/field và ràng buộc đã khai báo.

## 4. Ví dụ Java: một trường lỗi, các trường khác vẫn được gán

Ví dụ sau dùng **Java 17+** và API `org.springframework.validation.DataBinder` của Spring Framework. Mỗi thuộc tính là một JavaBean property có getter/setter; `age` được khởi tạo bằng 18 để thấy rõ điều gì xảy ra khi giá trị mới bị từ chối.

Tệp **BindingErrorsDemo.java**:

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class BindingErrorsDemo {
    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "form");
        binder.setAllowedFields("name", "age", "email");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Lan");
        input.add("age", "abc");
        input.add("email", "lan@example.com");

        // Một lỗi chuyển kiểu không ngăn các property hợp lệ được bind.
        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println("name=" + form.getName());
        System.out.println("age=" + form.getAge());
        System.out.println("email=" + form.getEmail());
        System.out.println("hasErrors=" + result.hasErrors());

        FieldError ageError = result.getFieldError("age");
        if (ageError != null) {
            System.out.println("field=" + ageError.getField());
            System.out.println("code=" + ageError.getCode());
            System.out.println("rejected=" + ageError.getRejectedValue());
            System.out.println(
                "bindingFailure=" + ageError.isBindingFailure()
            );
        }
    }

    public static final class RegistrationForm {
        private String name;
        private int age = 18;
        private String email;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }
}
~~~

**Chạy ví dụ:** cần các JAR Spring Framework tương thích, tối thiểu module `spring-context` cùng các dependency cần thiết, trong thư mục `lib/`. Đây là ví dụ dùng thư viện Spring, nên chỉ có JDK mà không có classpath Spring thì không biên dịch được.

~~~bash
# Linux/macOS: lib/ chứa các JAR Spring và dependency tương thích
javac -cp "lib/*" BindingErrorsDemo.java
java -cp ".:lib/*" BindingErrorsDemo

# Windows: dấu phân tách các mục classpath là dấu chấm phẩy
javac -cp "lib/*" BindingErrorsDemo.java
java -cp ".;lib/*" BindingErrorsDemo
~~~

Kết quả chuẩn của ví dụ với bộ chuyển kiểu mặc định:

~~~text
name=Lan
age=18
email=lan@example.com
hasErrors=true
field=age
code=typeMismatch
rejected=abc
bindingFailure=true
~~~

**Giải thích theo thời điểm binding:**

1. `name="Lan"` hợp lệ nên được gán.
2. `age="abc"` không thể chuyển sang `int`: Spring thu thập lỗi `typeMismatch` và giữ giá trị `age=18` trước đó; `"abc"` được lưu làm rejected value để báo lỗi.
3. `email="lan@example.com"` vẫn được xử lý và gán vào đối tượng.
4. `result.hasErrors()` trả `true` nên đối tượng **không được xem là hợp lệ để lưu**, dù hai trường khác đã có giá trị đúng.

Các thông báo chi tiết, danh sách mã lỗi cụ thể và thứ tự xử lý có thể phụ thuộc cấu hình converter, binder và phiên bản Spring; ví dụ chỉ dựa vào các giá trị/kiểu kết quả cốt lõi nêu trên. Không dựa vào chuỗi thông báo lỗi nội bộ để viết điều kiện nghiệp vụ.

## 5. Spring MVC: nhận lỗi ở controller mà vẫn giữ dữ liệu các trường đúng

Trong một ứng dụng Spring MVC xử lý form bằng `@ModelAttribute`, Spring tạo/lấy đối tượng form, bind tham số rồi đưa lỗi vào `BindingResult`. Đặt tham số `BindingResult` **ngay sau** tham số model attribute cần kiểm tra, không chen tham số khác ở giữa.

Đoạn sau là **mã tích hợp trong dự án Spring MVC**, không phải tệp Java độc lập. Giả sử `RegistrationForm` là JavaBean có các thuộc tính `name`, `age` và `email`, kèm các Bean Validation constraint khi cần; view `registration/form` và `registration/success` được ứng dụng cung cấp.

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/registrations")
public class RegistrationController {

    @InitBinder("form")
    void configureBinder(WebDataBinder binder) {
        // Chỉ các trường được phép sửa qua biểu mẫu.
        binder.setAllowedFields("name", "age", "email");
    }

    @PostMapping
    String submit(
            @Valid @ModelAttribute("form") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            // Spring MVC giữ form và BindingResult cho view hiển thị lỗi.
            return "registration/form";
        }

        // Chỉ chuyển đến nhánh thành công khi không có binding/validation errors.
        // Ứng dụng thực tế còn kiểm tra điều kiện nghiệp vụ trước khi lưu.
        return "registration/success";
    }
}
~~~

Với dữ liệu form `name=Lan&age=abc&email=lan%40example.com`, luồng xử lý thông thường là:

- `name` và `email` bind thành công trên đối tượng `form`.
- `age` tạo lỗi chuyển kiểu được tìm thấy qua `errors.getFieldError("age")`.
- Nếu có Bean Validation, các constraint phù hợp chạy thêm sau binding; chúng có thể thêm lỗi vào `errors`.
- `errors.hasErrors()` là `true`; controller trả về view nhập liệu để hiển thị lỗi, không đi qua nhánh thành công.
- Ở view/template, cần hiển thị cả giá trị đã nhập và thông báo lỗi một cách an toàn. Với trường sai kiểu, giá trị bị từ chối nằm trong thông tin lỗi; không giả định giá trị trong target đã trở thành chuỗi sai đó.

**Vị trí `BindingResult` là bắt buộc về mặt ngữ nghĩa**: `BindingResult` tương ứng với `@ModelAttribute` liền trước nó. Nếu bỏ tham số xử lý lỗi này, Spring MVC thường chuyển lỗi binding/validation sang cơ chế exception (ví dụ `MethodArgumentNotValidException`); khi method validation toàn phương thức được áp dụng, loại exception có thể khác. Controller khi ấy không tự động nhận kết quả để render lại form theo nhánh `errors.hasErrors()` ở trên.

## 6. Tập hợp lỗi và phân biệt các tình huống

| Đầu vào / tình huống | Điều xảy ra điển hình | Cách xử lý |
|---|---|---|
| `age=abc` nhưng `age` là `int` | Lỗi conversion/binding trên `age`; property hợp lệ khác vẫn có thể được gán. | Duyệt `getFieldErrors()`, báo `age` sai kiểu, giữ lại thông tin form. |
| `age=16` chuyển kiểu thành công nhưng yêu cầu tuổi ≥ 18 | Binding thành công; validator có thể thêm `FieldError`. | Không lưu; dùng thông báo validation phù hợp. |
| Hai trường cùng sai kiểu | Binder có thể thu thập nhiều `FieldError` trong một lượt. | Hiển thị các lỗi cho từng trường; không chỉ lấy lỗi đầu tiên toàn form. |
| Thiếu trường bắt buộc | Có thể thành lỗi validation như `@NotBlank` / `@NotNull`, hoặc lỗi binding nếu cấu hình `setRequiredFields`. | Phân biệt ràng buộc nào đang áp dụng; không mặc định “trường thiếu” là lỗi chuyển kiểu. |
| Tên thuộc tính không có trong JavaBean | Tùy cấu hình `ignoreUnknownFields`, binder có thể bỏ qua hoặc phát sinh exception. | Xác định tên trường và cấu hình; đừng mặc định được ghi thành `FieldError`. |
| Trường không nằm trong `allowedFields` | Bị ngăn gán, có thể xuất hiện trong `getSuppressedFields()`. | Xử lý theo chính sách đầu vào, không coi đó là trường đã bind thành công. |
| JSON hỏng cấu trúc khi dùng `@RequestBody` | Lỗi đọc/deserialization có thể xuất hiện trước property binding của `@ModelAttribute`. | Xử lý qua cơ chế exception của HTTP message conversion; không giả định `BindingResult` form sẽ chứa từng lỗi. |

**Một request có thể có cả lỗi binding và validation.** Ví dụ `age=abc` gây `typeMismatch`, trong khi `name=""` có thể gây lỗi `@NotBlank`. Khi trả phản hồi, gộp thông điệp theo trường/đối tượng cho người dùng; khi xử lý nghiệp vụ, vẫn phân biệt nguồn lỗi để tránh quyết định sai.

## 7. Cách duyệt và trả thông báo lỗi

Trong controller, có thể đọc danh sách lỗi thay vì chỉ gọi `hasErrors()`:

~~~java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        String field = fieldError.getField();
        String code = fieldError.getCode();
        boolean conversionFailed = fieldError.isBindingFailure();

        // Ghi nhận tên trường/mã lỗi theo danh sách cho phép.
        // Ánh xạ sang thông báo hiển thị, không trả nguyên stack trace.
    }
    return "registration/form";
}
~~~

Nếu xây API cần phản hồi JSON, nên trả cấu trúc lỗi nhất quán, ví dụ:

~~~json
{
  "message": "Dữ liệu biểu mẫu không hợp lệ",
  "errors": [
    {
      "field": "age",
      "code": "typeMismatch",
      "message": "Tuổi phải là một số nguyên hợp lệ"
    }
  ]
}
~~~

Đây là **mẫu định dạng phản hồi do ứng dụng tự thiết kế**, không phải JSON Spring MVC tự trả mặc định. Thông báo có thể được ánh xạ từ mã lỗi bằng `MessageSource` để hỗ trợ đa ngôn ngữ. Không đưa exception message, tên lớp nội bộ, stack trace hoặc dữ liệu nhạy cảm (mật khẩu, token, thông tin cá nhân) vào phản hồi/log.

Không chỉ lấy `getFieldError()` một lần rồi kết luận đã xử lý đủ lỗi: hàm đó chỉ trả lỗi đầu tiên. Với các ràng buộc toàn đối tượng như “ngày kết thúc phải sau ngày bắt đầu”, cần xét `getGlobalErrors()` cùng `getFieldErrors()`.

## 8. Các giới hạn và lưu ý khi thiết kế

**Không có rollback tự động cho các setter đã thành công.** Đối tượng có thể ở trạng thái được gán một phần. Vì vậy không chạy hành động nghiệp vụ, ghi database, gửi sự kiện hoặc gọi API bên ngoài trước khi kết luận form hợp lệ. Nên bind vào DTO/form object riêng, kiểm tra toàn diện, rồi mới ánh xạ sang domain entity trong nhánh thành công.

**Chỉ bind các trường được phép.** `setAllowedFields(...)` hoặc thiết kế constructor/DTO giới hạn bề mặt dữ liệu người dùng có thể điều khiển. Tránh bind trực tiếp lên entity có các thuộc tính nhạy cảm như `role`, `isAdmin`, `id`; việc một field bị chặn không bảo đảm nó tạo `FieldError` thông thường.

**Không đánh đồng lỗi binding với tất cả exception.** Trong property binding, lỗi chuyển đổi điển hình được thu thập; nhưng lỗi tạo object bằng constructor, lỗi custom converter/validator, setter có side effect, cấu hình binder sai hoặc lỗi hệ thống vẫn có thể làm gián đoạn luồng. Một ngoại lệ không được binder xử lý sẽ không tự động biến thành `FieldError` để tiếp tục.

**Đối tượng hiện có có thể chứa dữ liệu cũ.** Nếu trường `age` không bind được, giá trị trước đó có thể còn nguyên. Do đó không dựa vào target để suy ra giá trị người dùng vừa nhập; dùng `FieldError.getRejectedValue()` cho trường sai, với kiểm soát hiển thị/log phù hợp.

**Constructor binding có ngữ nghĩa khác property binding.** Spring cũng hỗ trợ khởi tạo đối tượng từ constructor; lỗi khởi tạo và target null có thể ảnh hưởng việc có đối tượng để tiếp tục property binding. Ví dụ trong mục 4 cố ý dùng JavaBean có sẵn để minh họa chính xác hành vi xử lý từng thuộc tính.

**`@Valid` không tự động cho phép bỏ qua lỗi.** Nó bổ sung validation; nhánh nghiệp vụ vẫn phải tôn trọng `BindingResult` hoặc cơ chế exception tương ứng.

## 9. Kiểm thử hành vi cần xác nhận

Với ví dụ `DataBinder`, một bài kiểm thử có giá trị cần kiểm tra **đồng thời**:

1. Input `name="Lan"`, `age="abc"`, `email="lan@example.com"`.
2. Sau `bind`, `name` và `email` nhận giá trị mới; `age` vẫn là 18.
3. `result.hasFieldErrors("age")` trả `true` và rejected value là `"abc"`.
4. `ageError.isBindingFailure()` trả `true`.
5. Không có bước lưu dữ liệu khi `result.hasErrors()` còn `true`.

Với Spring MVC, dùng `MockMvc` gửi `POST /registrations` với `age=abc`, rồi kiểm tra controller trả về view form, model có field error `age`, các trường hợp lệ vẫn hiện trong form và không có tác vụ lưu dữ liệu. Thêm các trường hợp `age=20`, `age=16` có validation, hai trường sai cùng lúc và tên field bị chặn để xác nhận ranh giới giữa binding, validation và field suppression.

## 10. Ghi nhớ

- **Bind từng trường, thu thập lỗi, tiếp tục xử lý trường có thể bind:** đó là mục tiêu của luồng property binding thông thường.
- **`BindingResult` giữ lỗi, target giữ những giá trị được gán thành công:** không thể dùng target làm bằng chứng rằng toàn form hợp lệ.
- **Kiểm tra mọi lỗi trước nghiệp vụ:** đưa `BindingResult` sát sau `@ModelAttribute`, hiển thị lỗi theo trường và chỉ xử lý thành công khi form thực sự hợp lệ.
- **Phân biệt các lớp lỗi:** type conversion, Bean Validation, field suppression, JSON deserialization và lỗi hệ thống không có cùng cơ chế xử lý.

### Tài liệu tham khảo chính thức

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Java Bean Validation và DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
