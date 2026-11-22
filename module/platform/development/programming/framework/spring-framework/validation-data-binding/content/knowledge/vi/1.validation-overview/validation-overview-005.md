# Quan hệ giữa DataBinder, BindingResult và Validator trong Spring Framework

## 1. Ba thành phần giải quyết ba trách nhiệm khác nhau

Khi ứng dụng nhận dữ liệu từ bên ngoài (ví dụ các trường của một biểu mẫu), cần **đưa dữ liệu vào đối tượng Java**, **kiểm tra dữ liệu có hợp lệ không**, rồi **trả lỗi cho nơi gọi**. Spring Framework phân tách các việc đó thành ba vai trò:

| Thành phần | Trách nhiệm chính | Điều cần nhớ |
| --- | --- | --- |
| **DataBinder** (`org.springframework.validation.DataBinder`) | Gắn các giá trị đầu vào vào đối tượng đích, thực hiện chuyển kiểu, cấu hình các `Validator` và quản lý kết quả | `bind(...)` không tự động gọi `validate()` trong cách dùng thủ công |
| **Validator** (`org.springframework.validation.Validator`) | Kiểm tra quy tắc hợp lệ của đối tượng và ghi nhận vi phạm qua giao diện `Errors` | Không tự chuyển kiểu, không trực tiếp xử lý HTTP, không tự tạo `BindingResult` |
| **BindingResult** (`org.springframework.validation.BindingResult`) | Chứa các lỗi từ **binding/chuyển kiểu** và **validation**, cùng thông tin trường và giá trị bị từ chối | `BindingResult` mở rộng `Errors`; có thể truy vấn `FieldError`, `ObjectError`, `hasErrors()` |

Hiểu theo quan hệ sở hữu: **DataBinder điều phối binding và validation; Validator đánh giá đối tượng; BindingResult là nơi tích lũy kết quả lỗi của cả hai giai đoạn.** `Validator.validate(target, errors)` nhận một `Errors` do bên gọi cung cấp; trong luồng thông thường của `DataBinder`, đối tượng `Errors` đó chính là `BindingResult` của binder.

~~~text
Dữ liệu đầu vào (tên thuộc tính -> giá trị)
                 |
                 v
          DataBinder.bind(...)
                 |  - tìm thuộc tính / chuyển kiểu
                 |  - cập nhật đối tượng đích
                 |  - ghi lỗi binding nếu có
                 v
         Đối tượng Java (target)
                 |
          DataBinder.validate()  [khi được gọi]
                 |
                 v
          Validator.validate(target, Errors)
                 |  - kiểm tra quy tắc
                 |  - reject(...) / rejectValue(...)
                 v
       DataBinder.getBindingResult()
                 |
                 v
        BindingResult: lỗi binding + lỗi validation
                 |
                 v
     Controller / service / form view / phản hồi API
~~~

Điểm quan trọng: sơ đồ là **luồng logic**, không có nghĩa mọi ứng dụng đều tự tạo `DataBinder`. Trong Spring MVC, framework dùng `WebDataBinder` (mở rộng `DataBinder`) để thực hiện phần lớn công việc này.

## 2. DataBinder làm gì trong từng giai đoạn?

### 2.1. Binding và chuyển kiểu

Với đối tượng JavaBean có các thuộc tính `name` (String) và `age` (Integer), đầu vào có thể là `name=Lan` và `age=20` ở dạng chuỗi. `DataBinder.bind(PropertyValues)` tìm đường dẫn thuộc tính tương ứng, dùng cơ chế chuyển kiểu được cấu hình để đổi `"20"` thành `Integer(20)`, rồi gọi setter. Nó cũng có thể làm việc với đường dẫn lồng nhau nếu cấu hình và mô hình đối tượng cho phép.

Nếu `age=abc`, lỗi chuyển kiểu thường được ghi thành `FieldError` với mã cơ sở như `typeMismatch`; giá trị đích không trở thành một số hợp lệ. **Binding không đồng nghĩa với validation**: ngay cả khi chuyển kiểu thành công, `age=-5` vẫn có thể vi phạm quy tắc nghiệp vụ. Hơn nữa, lỗi ở một trường không nhất thiết ngăn các trường khác được gắn thành công; đối tượng có thể đã được cập nhật một phần.

Ngoài cách gắn qua setter (property binding), các bản Spring hiện đại còn hỗ trợ **constructor binding** để tạo đối tượng từ tham số constructor. Hai kiểu binding có cùng ý tưởng cốt lõi: chuyển dữ liệu đầu vào thành đối tượng và ghi lỗi vào `BindingResult`; cơ chế tạo đối tượng và thuộc tính có thể ghi được thì khác nhau.

### 2.2. Cấu hình validator và chủ động chạy validation

Với cách sử dụng `DataBinder` trực tiếp:

1. Tạo binder cho đối tượng đích: `new DataBinder(target, "objectName")`.
2. Giới hạn các trường được phép gắn khi nhận dữ liệu không tin cậy: `setAllowedFields(...)`.
3. Cấu hình bộ kiểm tra: `setValidator(...)` hoặc `addValidators(...)`.
4. Thực hiện binding: `bind(propertyValues)`.
5. **Gọi rõ ràng** `validate()` để chạy các validator đã cấu hình.
6. Lấy cùng một bộ kết quả: `getBindingResult()`.

`setValidator(...)` chỉ thiết lập validator, không phải lệnh chạy validation. Ngược lại, `validate()` không có nhiệm vụ đọc request hoặc chuyển chuỗi thành số. Một binder có thể có nhiều validator tương thích với kiểu đối tượng. Cần hiểu quy tắc cụ thể của từng validator để tránh ghi hai lỗi trùng ý cho cùng một trường.

## 3. Validator ghi lỗi vào đâu?

Spring `Validator` định nghĩa hai phương thức:

- `supports(Class<?> clazz)`: xác định validator có áp dụng được cho kiểu đối tượng đó hay không. Có thể dùng `TargetClass.class.isAssignableFrom(clazz)` khi muốn hỗ trợ lớp con.
- `validate(Object target, Errors errors)`: áp dụng các quy tắc và ghi lỗi, ví dụ `errors.rejectValue("name", "name.required")` hoặc `errors.reject("order.invalid")`.

`rejectValue` ghi lỗi ở một trường cụ thể; `reject` ghi lỗi mức đối tượng khi điều kiện liên quan nhiều trường. `ValidationUtils.rejectIfEmptyOrWhitespace` là tiện ích cho kiểm tra trường trống. Không nên ném exception cho mọi sai sót nhập liệu thông thường nếu luồng gọi cần trả lỗi chi tiết qua `BindingResult`.

**Errors** là giao diện ghi/đọc lỗi mà validator phụ thuộc vào. **BindingResult** kế thừa `Errors` và bổ sung thông tin phục vụ binding, chẳng hạn đối tượng đích, giá trị trường, giá trị nhập bị từ chối, các trường bị loại khỏi quá trình binding và khả năng tạo model cho form. Vì vậy validator thường nhận kiểu `Errors`, còn code xử lý kết quả thường dùng kiểu `BindingResult`.

Phân biệt hai nhóm lỗi phổ biến:

| Tình huống | Nguồn phát hiện | Cách thể hiện |
| --- | --- | --- |
| `age=abc` nhưng trường là `Integer` | DataBinder / chuyển kiểu | `FieldError`, thường mang mã `typeMismatch` |
| `age=16` chuyển thành số thành công nhưng yêu cầu tuổi ít nhất 18 | Validator | `FieldError` do `rejectValue("age", "age.min")` |
| Tên bị bỏ trống hoặc chỉ có dấu cách | Validator | `FieldError` do `rejectIfEmptyOrWhitespace` |
| Hai trường có quan hệ không hợp lệ (ví dụ ngày bắt đầu sau ngày kết thúc) | Validator | Có thể dùng lỗi mức đối tượng qua `reject(...)` |

Cả lỗi binding và lỗi validation đều đọc được từ **cùng `BindingResult`**. `getFieldErrors("age")` lấy các lỗi của trường; `getGlobalErrors()` lấy lỗi mức đối tượng; `hasErrors()` và `getErrorCount()` cho biết tình trạng tổng thể. `FieldError.getRejectedValue()` giúp hiển thị giá trị bị từ chối khi phù hợp, nhưng dữ liệu đó có thể chứa thông tin nhạy cảm và không nên ghi log tùy tiện. Các mã lỗi có thể được giải quyết thành thông điệp theo ngôn ngữ qua `MessageSource`.

## 4. Ví dụ Java 17+: binding thất bại và validation cùng góp lỗi

Ví dụ sau chạy **không cần web server**. Nó mô phỏng một form đăng ký: tên không được trống, tuổi phải từ 18. Đầu vào cố ý cung cấp tuổi sai kiểu và một thuộc tính không được phép cập nhật để thấy đủ vai trò của ba thành phần.

Tạo cấu trúc:

~~~text
binding-demo/
  pom.xml
  src/main/java/BindingFlowDemo.java
~~~

**pom.xml** (Spring Framework 6.2.x; dự án Spring Boot đang quản lý phiên bản Spring thì dùng dependency management của Boot thay vì ép phiên bản thủ công):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>binding-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/BindingFlowDemo.java**:

~~~java
import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class BindingFlowDemo {

    public static final class RegistrationForm {
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

    public static final class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required");

            // Nếu age đã lỗi chuyển kiểu, tránh ghi thêm lỗi tuổi.
            if (!errors.hasFieldErrors("age")
                    && (form.getAge() == null || form.getAge() < 18)) {
                errors.rejectValue("age", "age.min");
            }
        }
    }

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registrationForm");

        binder.setAllowedFields("name", "age");
        binder.setValidator(new RegistrationValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "  ");
        input.add("age", "not-a-number");
        input.add("isAdmin", "true");

        binder.bind(input);     // Chuyển kiểu/gắn thuộc tính và ghi lỗi binding.
        binder.validate();      // Chạy RegistrationValidator, ghi lỗi validation.

        BindingResult result = binder.getBindingResult();
        System.out.println("nameBlank=" + form.getName().isBlank());
        System.out.println("age=" + form.getAge());
        System.out.println("hasErrors=" + result.hasErrors());
        System.out.println("errorCount=" + result.getErrorCount());
        System.out.println("nameError=" + result.hasFieldErrors("name"));
        System.out.println("ageError=" + result.hasFieldErrors("age"));
        System.out.println("suppressed="
                + Arrays.toString(result.getSuppressedFields()));
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` (cần Java 17+ và Maven đã cài):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=BindingFlowDemo
~~~

Kết quả chuẩn của chương trình (không tính thông báo riêng của Maven):

~~~text
nameBlank=true
age=null
hasErrors=true
errorCount=2
nameError=true
ageError=true
suppressed=[isAdmin]
~~~

Giải thích **từng nguyên nhân**, thay vì chỉ nhìn `hasErrors=true`:

1. `name` được gắn thành chuỗi gồm hai khoảng trắng; quy tắc của `RegistrationValidator` phát hiện tên rỗng về mặt nội dung và tạo một lỗi.
2. `age` không chuyển được từ `"not-a-number"` sang `Integer`; binder tạo một lỗi `typeMismatch` và thuộc tính `age` vẫn `null`.
3. Validator kiểm tra `errors.hasFieldErrors("age")` trước khi đánh giá tuổi, nên không tạo lỗi `age.min` trùng cho một giá trị đã sai kiểu. Tổng cộng có **hai lỗi**.
4. `isAdmin` bị bỏ qua vì không có trong `setAllowedFields`. Tên trường xuất hiện trong `getSuppressedFields()`; việc một trường bị chặn **không mặc nhiên** là một `FieldError`. Ứng dụng có thể chủ động quyết định có từ chối toàn bộ request khi gặp suppressed field hay không.
5. Nếu chỉ thay đầu vào bằng `name=Lan`, `age=20` và không gửi `isAdmin`, rồi chạy cả `bind()` và `validate()`, kết quả sẽ không có lỗi theo các quy tắc trong ví dụ.

Ví dụ dùng JavaBean mutable vì dễ thấy bước setter binding. Khi dùng constructor binding, cách đối tượng được tạo khác đi nhưng cùng nguyên tắc tách **binding → validation → kết quả lỗi** vẫn áp dụng.

## 5. Quan hệ trong Spring MVC

Với `@ModelAttribute`, Spring MVC thường tạo hoặc lấy model object, dùng `WebDataBinder` đưa dữ liệu request vào đối tượng, chạy validation khi có điều kiện kích hoạt phù hợp (chẳng hạn `@Valid` hoặc `@Validated`), rồi cung cấp `BindingResult` cho controller. `WebDataBinder` là biến thể dành cho web của `DataBinder`, còn `BindingResult` và `Validator` vẫn giữ vai trò tương tự.

Đoạn sau **minh họa bên trong một controller** (giả sử `RegistrationForm` và `RegistrationValidator` là các lớp đã định nghĩa, cùng một form view có tên `register-form`; đây không phải một ứng dụng MVC độc lập):

~~~java
@InitBinder("registrationForm")
void configureRegistration(WebDataBinder binder) {
    binder.setAllowedFields("name", "age");
    binder.addValidators(new RegistrationValidator());
}

@PostMapping("/register")
String register(
        @Validated @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
~~~

Ở đây:

- `@InitBinder` cấu hình binder cho model attribute: whitelist trường và thêm validator. Trong ứng dụng thật, có thể cần cấu hình thêm `ConversionService`, formatter hoặc converter để dữ liệu request chuyển kiểu đúng.
- `@Validated` kích hoạt validation trên model attribute sau binding trong luồng MVC. `@Valid` (Jakarta Validation) cũng được Spring MVC hỗ trợ; việc thực thi Bean Validation cần provider phù hợp trên classpath. `@Valid` tự thân không thay thế việc cấu hình hoặc gọi `validate()` khi tự dùng `DataBinder` bên ngoài MVC.
- **Tham số `BindingResult` phải đứng ngay sau model attribute mà nó mô tả.** Nếu đặt `Model`, `HttpServletRequest` hoặc tham số khác xen vào giữa, Spring không ghép kết quả theo cách mong muốn.
- Nếu không khai báo `BindingResult` để xử lý lỗi tại controller, Spring MVC hiện đại thường báo lỗi qua exception như `MethodArgumentNotValidException`; các kịch bản method validation có thể dùng `HandlerMethodValidationException`. Chi tiết tùy loại tham số và phiên bản Spring.
- Với `@RequestBody` JSON, phần đọc JSON thường do `HttpMessageConverter`/Jackson đảm nhiệm trước; không nên giả định nó đi qua cùng cơ chế gắn từng trường biểu mẫu của `@ModelAttribute`.

### Spring Validator và Jakarta Bean Validation

Hai cách validation thường gặp có thể phối hợp, nhưng không phải một API:

| Spring Validator | Jakarta Bean Validation |
| --- | --- |
| Viết lớp triển khai `supports(...)` và `validate(Object, Errors)` | Khai báo ràng buộc như `@NotBlank`, `@Min`, `@Size` trên model |
| Ghi lỗi thông qua `Errors` của Spring | Provider (ví dụ Hibernate Validator) đánh giá constraint; Spring có adapter tích hợp lỗi vào quá trình MVC |
| Thuận tiện cho quy tắc phụ thuộc nhiều trường hoặc kiểm tra tùy biến | Thuận tiện cho ràng buộc khai báo, có thể tái sử dụng ở nhiều nơi |

Trong Spring MVC, validator toàn cục hoặc validator thêm qua `@InitBinder` có thể cùng tham gia. Cần tránh chạy lặp cùng một quy tắc và nhớ rằng lỗi chuyển kiểu đã có thể tồn tại **trước** lúc validator xử lý đối tượng.

## 6. Đọc BindingResult để phản hồi chính xác

Các truy vấn thường dùng:

~~~java
if (result.hasErrors()) {
    for (var fieldError : result.getFieldErrors()) {
        System.out.println(fieldError.getField()
                + " -> " + fieldError.getCode());
    }
    for (var globalError : result.getGlobalErrors()) {
        System.out.println(globalError.getCode());
    }
}
~~~

Đây là đoạn **minh họa cần biến `result` đã có trong phạm vi**, không phải chương trình chạy độc lập. Với form view, giữ `BindingResult` cùng model attribute để hiển thị lỗi theo trường. Với REST API, ánh xạ các `FieldError` và `ObjectError` thành cấu trúc phản hồi rõ ràng; tránh gửi stack trace hoặc dữ liệu nhạy cảm. Đừng đồng nhất `getDefaultMessage()` với thông điệp đã được bản địa hóa ở mọi trường hợp: Spring có hệ thống mã lỗi và `MessageSource` để giải quyết thông điệp.

## 7. Lỗi phổ biến và nguyên tắc an toàn

1. **Chỉ gọi `bind()` rồi cho rằng đã validate:** binding chủ yếu giải quyết gắn giá trị và chuyển kiểu. Khi dùng binder thủ công, hãy gọi `validate()` nếu cần kiểm tra quy tắc.
2. **Chỉ gọi validator mà bỏ qua binding error:** đối tượng có thể chưa nhận được một số trường vì lỗi chuyển kiểu. Luôn xét toàn bộ `BindingResult`, và cân nhắc `hasFieldErrors(field)` để tránh báo lỗi trùng hoặc tạo logic sai.
3. **Đồng nhất `BindingResult` với `Validator`:** validator quyết định vi phạm, BindingResult tích lũy vi phạm; gọi `getBindingResult()` không tự chạy validation.
4. **Dùng `@Valid` nhưng đặt `BindingResult` sai vị trí:** trong Spring MVC, kết quả phải đi ngay sau tham số được validate nếu muốn xử lý lỗi trong cùng phương thức.
5. **Gắn request trực tiếp vào entity chứa trường nhạy cảm:** setter binding có thể cập nhật thuộc tính ngoài mong đợi (mass assignment). Ưu tiên DTO chuyên dụng hoặc constructor binding, và giới hạn `setAllowedFields(...)` khi cần property binding; không xem `setDisallowedFields(...)` như biện pháp phòng thủ chính.
6. **Bỏ qua trường bị chặn:** kiểm tra `getSuppressedFields()` nếu chính sách yêu cầu từ chối dữ liệu gửi vượt whitelist; suppressed field không nhất thiết làm `hasErrors()` thành true.
7. **Cho rằng mọi lỗi đều do validator:** `typeMismatch` và các lỗi gắn/chuyển kiểu có thể được tạo bởi binder. Phân biệt nguồn lỗi khi hiển thị gợi ý sửa dữ liệu và khi viết test.
8. **Gắn `Validator` chặt vào HTTP:** hợp đồng Spring `Validator` không cần request hoặc controller; nên kiểm tra trên object và `Errors` để tái sử dụng, kiểm thử độc lập.

Để tự kiểm tra luồng, hãy đặt breakpoint lần lượt tại `bind(...)`, `validate(...)`, `getBindingResult()`. Quan sát đối tượng trước/sau binding và danh sách lỗi trước/sau validation; nếu chỉ có lỗi `typeMismatch` sau `bind()`, đó là bằng chứng rõ nhất về sự phân chia trách nhiệm.

## Tài liệu tham khảo

- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Configuring a DataBinder: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring MVC — @InitBinder: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
