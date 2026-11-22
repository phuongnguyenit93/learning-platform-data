# Hợp đồng org.springframework.validation.Validator trong Spring Framework

**org.springframework.validation.Validator** là hợp đồng kiểm tra tính hợp lệ của một đối tượng Java theo các quy tắc do ứng dụng định nghĩa. Nó độc lập với HTTP: cùng một validator có thể được gọi trong Spring MVC, trong service, một tiến trình batch hoặc một đoạn Java thông thường. Thay vì trả về **true/false**, validator ghi các vi phạm vào đối tượng **Errors** mà bên gọi cung cấp.

Cốt lõi của hợp đồng gồm hai câu hỏi: **“Validator này hỗ trợ loại đối tượng nào?”** và **“Đối tượng đang xét vi phạm những quy tắc nào?”**. Hai phương thức **supports(Class<?>)** và **validate(Object, Errors)** trả lời tương ứng. Đây là điểm phân biệt với Data Binding: bind chuyển dữ liệu thành đối tượng; validator kiểm tra đối tượng và ghi lỗi.

## 1. Chữ ký và ý nghĩa của hợp đồng

Hai phương thức trừu tượng cần hiện thực:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);

    // Spring Framework 6.1+ còn có default method validateObject(Object).
}
~~~

Đoạn trên trình bày **hai phương thức bắt buộc**, không phải bản sao đầy đủ source của interface. Bắt đầu từ Spring Framework 6.1 còn có phương thức mặc định **validateObject(Object)** giúp kiểm tra một đối tượng độc lập; ứng dụng cũ vẫn có thể dùng **validate(Object, Errors)**.

| Thành phần | Đầu vào | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| **supports(Class<?> clazz)** | Lớp được đề nghị kiểm tra | **boolean** | **true** nếu validator có thể kiểm tra các instance của lớp đó |
| **validate(Object target, Errors errors)** | Đối tượng đích và nơi thu thập lỗi | **void** | Kiểm tra và đăng ký lỗi trong **Errors**, không trả về kết quả boolean |
| **Errors** | Trạng thái kiểm tra, tên đối tượng, đường dẫn thuộc tính và các lỗi hiện có | Có thể xem **hasErrors()**, lỗi field/global | Đích lưu kết quả validation |
| **validateObject(Object target)**, từ Spring 6.1 | Đối tượng cần kiểm tra | **Errors** | Phương thức tiện ích mặc định để kiểm tra ngoài DataBinder |

**supports(...)** thường được viết như sau:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return EventPeriod.class.isAssignableFrom(clazz);
}
~~~

Biểu thức trên đúng khi **clazz** là **EventPeriod** hoặc lớp con của nó. Với **String.class** hoặc một loại không tương thích, kết quả là **false**. Nếu validator chỉ cho phép chính xác một class và cố ý không nhận subclass, có thể dùng **EventPeriod.class.equals(clazz)**. Nên chọn cách nhất quán với phép ép kiểu và phạm vi quy tắc thực tế.

**validate(...)** có các trách nhiệm quan trọng:

1. Nhận một **target** thuộc kiểu được **supports(...)** chấp nhận; bên gọi phải đảm bảo kiểu phù hợp. Nếu gọi trực tiếp với kiểu sai, phép ép kiểu trong implementation có thể gây **ClassCastException**. Tiện ích **ValidationUtils.invokeValidator(...)** kiểm tra **supports** trước khi gọi.
2. Đánh giá tất cả quy tắc liên quan; ghi lỗi bằng **errors.rejectValue(...)** (lỗi thuộc tính) hoặc **errors.reject(...)** (lỗi toàn đối tượng).
3. Giữ nguyên thông tin lỗi đã có trong **Errors**. Trong một luồng binding, **Errors** có thể đã chứa **typeMismatch** trước khi validator chạy. Không tạo một **Errors** mới để làm mất những lỗi đó.
4. Không coi giá trị sai thông thường là ngoại lệ chương trình. Giá trị đầu vào không hợp lệ cần trở thành **ObjectError/FieldError** để lớp gọi quyết định cách phản hồi. Ngoại lệ nên dành cho lỗi lập trình, cấu hình hoặc lỗi hệ thống thực sự.
5. Hạn chế thay đổi **target**, tránh cập nhật database, gọi API hoặc thực hiện side effect trong phương thức kiểm tra. Validator thường được tái sử dụng nên tránh giữ trạng thái request trong field của validator.

**Hợp đồng không tự chạy** chỉ vì một class có triển khai **Validator**. Phải có bên gọi **validate(...)**, **validateObject(...)**, hoặc một cơ chế đã cấu hình để Spring gọi nó.

## 2. Hiểu đúng Errors, FieldError và ObjectError

Interface **Errors** là kênh trao đổi kết quả giữa validator và bên gọi. Nó có thể mang cả lỗi từ bước binding lẫn lỗi do validator chủ động thêm.

- **errors.rejectValue("title", "title.required", "Title is required")**: thêm lỗi cho thuộc tính **title**, với mã lỗi và thông báo mặc định.
- **errors.reject("period.invalid", "Start date must not follow end date")**: thêm lỗi toàn đối tượng; dùng khi ràng buộc liên quan nhiều thuộc tính hoặc không thuộc về riêng một field.
- **errors.hasErrors()** và **errors.getErrorCount()**: xác định có lỗi và tổng số lỗi.
- **errors.getFieldErrors()**, **errors.getGlobalErrors()**, **errors.getFieldError("title")**: lấy những loại lỗi cần thiết.
- **errors.getObjectName()**: tên logic của đối tượng đang được kiểm tra, ví dụ **eventPeriod**.

**FieldError** biểu diễn lỗi một thuộc tính, có thể mang field name, rejected value, error codes và binding-failure flag. **ObjectError** biểu diễn lỗi cấp đối tượng; **FieldError** là một dạng chuyên biệt của **ObjectError**. **BindingResult** kế thừa **Errors** và bổ sung thông tin về target/binding để Spring MVC có thể render form, kiểm tra raw values hoặc các field bị suppress.

Ví dụ với một kỳ sự kiện có **title** là chuỗi trắng, **startDate** muộn hơn **endDate**:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "title", "title.required", "Title is required");

errors.reject(
        "period.invalid", "Start date must not follow end date");
~~~

Lỗi **title.required** là **field error**. Lỗi **period.invalid** là **global error**. Một đối tượng có thể đồng thời có cả hai. **ValidationUtils.rejectIfEmptyOrWhitespace** kiểm tra giá trị **null**, chuỗi rỗng hoặc chỉ có whitespace thông qua **Errors**; nó không thay thế các kiểm tra kiểu hay logic khác.

**Mã lỗi** như **title.required** là khóa thông điệp để ứng dụng có thể quốc tế hóa qua **MessageSource** và các tệp **messages*.properties**. Spring có thể phát sinh các mã cụ thể hơn có tiền tố object/field rồi fallback về mã tổng quát, tùy **MessageCodesResolver**. **defaultMessage** là lựa chọn dự phòng; không nên hard-code toàn bộ câu tiếng Việt/tiếng Anh vào mọi nơi nếu sản phẩm cần đa ngôn ngữ.

Ví dụ tệp **messages_vi.properties** trong ứng dụng:

~~~properties
title.required=Vui lòng nhập tiêu đề.
period.invalid=Ngày bắt đầu không được muộn hơn ngày kết thúc.
~~~

Từng lớp hiển thị/API có thể ánh xạ mã lỗi thành thông điệp theo locale. **validate(...)** chỉ đăng ký lỗi; nó không quyết định template HTML, JSON response hoặc HTTP status.

## 3. Ví dụ Java 17+ chạy độc lập với Spring MVC

Ví dụ kiểm tra một **EventPeriod** gồm tiêu đề, ngày bắt đầu và ngày kết thúc. Quy tắc:

- Tiêu đề không được thiếu hoặc chỉ chứa khoảng trắng.
- Hai ngày phải có giá trị.
- Ngày bắt đầu không được sau ngày kết thúc; đây là lỗi cấp đối tượng vì liên quan cả hai thuộc tính.

Chương trình gọi **ValidationUtils.invokeValidator** trực tiếp để minh họa hợp đồng mà không cần khởi động web server. Tạo cấu trúc:

~~~text
spring-validator-contract/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ContractDemo.java
~~~

**pom.xml** (Spring Framework 6.2.10, JDK 17 trở lên):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-validator-contract</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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

**src/main/java/demo/ContractDemo.java**:

~~~java
package demo;

import java.time.LocalDate;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public final class ContractDemo {

    public static void main(String[] args) {
        Validator validator = new EventPeriodValidator();

        EventPeriod invalid = new EventPeriod(
                "   ",
                LocalDate.of(2026, 11, 20),
                LocalDate.of(2026, 11, 10));

        Errors errors = new BeanPropertyBindingResult(invalid, "eventPeriod");
        ValidationUtils.invokeValidator(validator, invalid, errors);

        System.out.println("supports(EventPeriod) = "
                + validator.supports(EventPeriod.class));
        System.out.println("supports(String) = "
                + validator.supports(String.class));
        System.out.println("invalid.hasErrors = " + errors.hasErrors());
        System.out.println("invalid.fieldErrorCount = "
                + errors.getFieldErrorCount());
        System.out.println("invalid.globalErrorCount = "
                + errors.getGlobalErrorCount());

        EventPeriod valid = new EventPeriod(
                "Workshop",
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 20));
        Errors validErrors = new BeanPropertyBindingResult(valid, "eventPeriod");
        ValidationUtils.invokeValidator(validator, valid, validErrors);
        System.out.println("valid.hasErrors = " + validErrors.hasErrors());
    }

    public static final class EventPeriod {
        private String title;
        private LocalDate startDate;
        private LocalDate endDate;

        public EventPeriod() {
        }

        public EventPeriod(String title, LocalDate startDate, LocalDate endDate) {
            this.title = title;
            this.startDate = startDate;
            this.endDate = endDate;
        }

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public LocalDate getStartDate() {
            return startDate;
        }

        public void setStartDate(LocalDate startDate) {
            this.startDate = startDate;
        }

        public LocalDate getEndDate() {
            return endDate;
        }

        public void setEndDate(LocalDate endDate) {
            this.endDate = endDate;
        }
    }

    public static final class EventPeriodValidator implements Validator {

        @Override
        public boolean supports(Class<?> clazz) {
            return EventPeriod.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            EventPeriod period = (EventPeriod) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "title", "title.required", "Title is required");

            if (period.getStartDate() == null) {
                errors.rejectValue(
                        "startDate", "start.required", "Start date is required");
            }
            if (period.getEndDate() == null) {
                errors.rejectValue(
                        "endDate", "end.required", "End date is required");
            }

            if (period.getStartDate() != null
                    && period.getEndDate() != null
                    && period.getStartDate().isAfter(period.getEndDate())) {
                errors.reject(
                        "period.invalid",
                        "Start date must not follow end date");
            }
        }
    }
}
~~~

Tại thư mục chứa **pom.xml**, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContractDemo
~~~

Sáu dòng do **System.out.println** của chương trình tạo ra, theo thứ tự:

~~~text
supports(EventPeriod) = true
supports(String) = false
invalid.hasErrors = true
invalid.fieldErrorCount = 1
invalid.globalErrorCount = 1
valid.hasErrors = false
~~~

Giải thích: object **invalid** vi phạm hai quy tắc độc lập: **title** toàn khoảng trắng sinh một field error; **startDate > endDate** sinh một global error. Object **valid** không sinh lỗi. Phương thức **validate(...)** không trả **false** hay ném exception cho hai vi phạm thông thường này; người gọi quan sát **Errors**. Lưu ý dòng stdout là kết quả của mã ví dụ, không bao gồm thông báo phụ thuộc môi trường của Maven.

Có thể gọi trực tiếp **validator.validate(invalid, errors)** thay **ValidationUtils.invokeValidator(...)** khi đã bảo đảm target có kiểu phù hợp. Tuy nhiên, **invokeValidator** kiểm tra tính tương thích qua **supports(...)** và là lựa chọn thuận tiện khi ứng dụng có nhiều validator.

### Gọi ngắn bằng validateObject(...) trong Spring 6.1+

Với Spring Framework 6.1 trở lên, interface **Validator** cung cấp **default method**:

~~~java
Errors result = new ContractDemo.EventPeriodValidator()
        .validateObject(new ContractDemo.EventPeriod(
                "Workshop",
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 20)));

System.out.println(result.hasErrors()); // false
~~~

Đây là đoạn dùng trong một method Java có import **Errors** và **LocalDate**. Cách này hữu ích khi không cần gắn validator với DataBinder; các codebase Spring cũ hơn 6.1 phải tiếp tục cung cấp đối tượng **Errors** theo hợp đồng hai tham số.

## 4. Validator được kích hoạt bởi DataBinder như thế nào?

**DataBinder** có nhiệm vụ ánh xạ giá trị từ nguồn dữ liệu vào target và có thể gọi validator đã đăng ký. Phân biệt hai việc:

~~~text
Nguồn dữ liệu (form / Map thuộc tính / HTTP request)
    |
    v
DataBinder.bind(...)              --> chuyển/điền thuộc tính, có thể tạo lỗi binding
    |
    v
DataBinder.validate(...)          --> chạy những validator đã cấu hình
    |
    v
BindingResult / Errors            --> lưu cả lỗi binding và validation
    |
    v
Bên gọi kiểm tra hasErrors()       --> quyết định phản hồi hoặc xử lý tiếp
~~~

Nếu chỉ gọi **bind(...)** mà chưa gọi **validate(...)** hoặc chưa dùng cơ chế MVC kích hoạt validation, không thể suy ra custom validator đã chạy.

Ví dụ gọi không có HTTP, giả sử **period** là một instance **EventPeriod** từ ví dụ trên:

~~~java
DataBinder binder = new DataBinder(period, "eventPeriod");
binder.addValidators(new EventPeriodValidator());
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    result.getAllErrors().forEach(System.out::println);
}
~~~

Đây là **đoạn minh họa đặt trong mã ứng dụng**; cần import **DataBinder**, **BindingResult** và class của ví dụ. **setValidator(...)** đặt validator chính, còn **addValidators(...)** bổ sung validator. Khi có một validator toàn cục (ví dụ adapter của Bean Validation), dùng **addValidators(...)** tại phạm vi controller thường phù hợp nếu muốn kết hợp với các kiểm tra sẵn có; tránh vô tình thay thế validator đã được cấu hình.

**BindingResult** là interface mở rộng **Errors**, do đó custom **validate(...)** nhận được đối tượng tương thích và có thể ghi thêm lỗi vào cùng kết quả mà controller xử lý. Lỗi do chuyển kiểu, ví dụ form gửi chữ vào thuộc tính số, có thể tồn tại trong **BindingResult** trước khi bước custom validator chạy.

## 5. Tích hợp Spring Validator trong Spring MVC

Trong Spring MVC, một cách đăng ký validator cho **@ModelAttribute** là dùng **@InitBinder**. Dưới đây là **đoạn minh họa trong một ứng dụng Spring MVC có sẵn**, tái sử dụng **EventPeriod** và **EventPeriodValidator** từ ví dụ trước; đây không phải một web server độc lập:

~~~java
@Controller
class PeriodController {

    @InitBinder("eventPeriod")
    void initBinder(WebDataBinder binder) {
        binder.addValidators(new ContractDemo.EventPeriodValidator());
    }

    @PostMapping("/periods")
    String create(
            @Valid @ModelAttribute("eventPeriod")
                    ContractDemo.EventPeriod input,
            BindingResult result) {

        if (result.hasErrors()) {
            return "period-form";
        }

        // Khi qua validation, chuyển cho service xử lý nghiệp vụ.
        return "redirect:/periods";
    }
}
~~~

Trong project thực tế cần các import **jakarta.validation.Valid**, **org.springframework.stereotype.Controller**, **org.springframework.web.bind.annotation.InitBinder**, **PostMapping**, **ModelAttribute**, **org.springframework.web.bind.WebDataBinder**, **org.springframework.validation.BindingResult**; thêm dependency MVC và Bean Validation nếu dùng các thành phần tương ứng.

- **@InitBinder("eventPeriod")** giới hạn đăng ký theo model attribute có tên **eventPeriod**. **binder.addValidators(...)** ghép custom validator vào binder của thuộc tính đó.
- **@Valid** đánh dấu yêu cầu validation đối tượng đã bind. Spring MVC dùng validators cấu hình cho binder, bao gồm custom Spring Validator đã đăng ký; nếu Bean Validation có mặt và được cấu hình, các constraint annotation cũng có thể được đánh giá.
- **BindingResult** phải đứng ngay sau tham số đang được validate để nhận các lỗi phù hợp. **hasErrors()** có thể là lỗi binding hoặc validation, vì vậy đừng đặt tên biến **bindingFailed** để suy đoán mọi nguyên nhân.
- Nếu không có **BindingResult/Errors** phù hợp để controller tự xử lý, Spring MVC có thể báo lỗi validation theo cơ chế exception tương ứng, thường **MethodArgumentNotValidException** cho object validation trong trường hợp thông thường.

Với **@RequestBody** JSON, body được đọc bởi **HttpMessageConverter** trước khi DTO được validate. JSON sai cú pháp hoặc không deserialize được có thể báo **HttpMessageNotReadableException** trước khi custom validator chạy. Cấu hình binder và validator cho **@RequestBody** khác với việc bind tham số form vào **@ModelAttribute**; phải kiểm tra cách ứng dụng đăng ký validator và chữ ký handler thực tế, không mặc nhiên cho rằng lỗi parse JSON đi vào cùng một nhánh **BindingResult**.

Nếu có cả Bean Validation và Spring Validator, hãy phân biệt phạm vi mỗi cơ chế: **@NotBlank**, **@Min** là Jakarta Bean Validation constraint; phương thức **supports/validate** thuộc Spring; **LocalValidatorFactoryBean** là adapter giúp Bean Validation tham gia vào cơ chế của Spring. Điều này không biến **org.springframework.validation.Validator** thành **jakarta.validation.Validator**.

## 6. Validator cho đối tượng lồng nhau và đường dẫn thuộc tính

Giả sử **Customer** có thuộc tính **address** với các field **street** và **zipCode**. Có thể tái sử dụng **AddressValidator** nhưng cần duy trì đường dẫn **address** để lỗi tạo ra mang tên field đúng: **address.street** hoặc **address.zipCode**.

~~~java
// Đoạn minh họa bên trong validate(Object target, Errors errors)
// của CustomerValidator; các class Customer/AddressValidator là của ứng dụng.
Customer customer = (Customer) target;
if (customer.getAddress() == null) {
    errors.rejectValue("address", "address.required");
} else {
    errors.pushNestedPath("address");
    try {
        ValidationUtils.invokeValidator(
                addressValidator, customer.getAddress(), errors);
    } finally {
        errors.popNestedPath();
    }
}
~~~

**pushNestedPath(...)** đổi ngữ cảnh lỗi cho validator con; **popNestedPath()** khôi phục ngữ cảnh gốc. Dùng **try/finally** để bảo đảm đường dẫn luôn được khôi phục kể cả khi code phát sinh ngoại lệ ngoài dự kiến. Kiểm tra đối tượng lồng nhau có null trước khi gọi validator con; **supports(...)** cần phù hợp với kiểu con. Với Jakarta Bean Validation, trường hợp nested object thường dùng **@Valid** trên field lồng nhau nhưng đó là cơ chế tương ứng khác, không có nghĩa Spring tự lần theo mọi nested object của custom Validator.

## 7. Khác biệt với SmartValidator và Jakarta Bean Validation

| Cơ chế | Đặc điểm chính | Khi nào dùng |
| --- | --- | --- |
| **Spring Validator** | Hai phương thức cốt lõi **supports** và **validate(Object, Errors)**; tự viết logic và ghi lỗi qua **Errors** | Quy tắc tùy chỉnh, kiểm tra chéo field, logic được tái dùng trong Spring |
| **Spring SmartValidator** | Mở rộng Spring Validator, hỗ trợ **validate(target, errors, Object... validationHints)** | Cần truyền hints/nhóm kiểm tra vào cơ chế validation |
| **Jakarta Bean Validation** | Annotation như **@NotNull**, **@NotBlank**, **@Size**; API **jakarta.validation.Validator** trả về tập **ConstraintViolation** | Ràng buộc khai báo, sử dụng provider như Hibernate Validator |
| **LocalValidatorFactoryBean** | Adapter giữa Jakarta Bean Validation và hợp đồng Spring | Tích hợp annotation constraint vào Spring MVC/DataBinder |

**SmartValidator** vẫn thuộc họ **org.springframework.validation**, nhưng truyền thêm **validationHints** cho implementer. Nếu cần Bean Validation groups từ **@Validated(Group.class)**, xem cơ chế hỗ trợ nhóm của adapter tương ứng. Một implementation chỉ có hai phương thức cơ bản của Spring Validator không tự hiểu mọi group/hint theo nghiệp vụ.

**validateObject(Object)** không tương đương phương thức **jakarta.validation.Validator.validate(...)**: đối tượng trả về là **org.springframework.validation.Errors**, trong khi Jakarta Bean Validation cung cấp một tập constraint violations. Cần đọc đúng package khi import hai interface cùng tên.

## 8. Thiết kế lỗi và trách nhiệm nghiệp vụ

Một validator tốt nên xác định rõ mình kiểm tra điều gì:

**Phù hợp để đặt trong Spring Validator:** tiêu đề bắt buộc, thứ tự ngày tháng, giới hạn độ dài và điều kiện chéo trường vốn xác định được từ đối tượng đầu vào. Những quy tắc này có thể chạy nhanh, tái lập, kiểm thử đơn vị dễ và thường không yêu cầu database.

**Nên cân nhắc đặt trong service/domain:** người dùng có quyền sở hữu tài nguyên không; một suất học có còn chỗ không; một mã đã được dùng chưa; chuyển trạng thái có hợp lệ với dữ liệu hiện tại không. Đặt validation trên DTO không thay thế kiểm tra ngữ cảnh và ràng buộc giao dịch. Nếu cần kiểm tra tính duy nhất, vẫn phải có biện pháp bảo vệ đồng thời ở cơ sở dữ liệu, không chỉ dựa vào một lần query trong validator.

**Mẫu quy tắc rõ ràng:** nếu **startDate == null** thì thêm lỗi field tương ứng; nếu cả hai ngày đã có và **startDate.isAfter(endDate)** thì thêm lỗi object. Kiểm tra null trước khi so sánh ngày để không tạo **NullPointerException** rồi biến sai dữ liệu bình thường thành lỗi hệ thống.

Không nên cho validator quyết định HTTP status hoặc trực tiếp render response. Trong MVC, lớp controller và tầng xử lý lỗi quyết định trả form với thông báo hoặc phản hồi API; trong service, lớp gọi quyết định có tiếp tục thao tác không. **Errors** là hợp đồng thu thập vi phạm, không phải hợp đồng thực thi nghiệp vụ.

## 9. Các lỗi triển khai thường gặp

**supports(...) viết ngược chiều isAssignableFrom.** Muốn chấp nhận lớp **EventPeriod** và các subclass, phải dùng **EventPeriod.class.isAssignableFrom(clazz)**. Viết ngược sẽ cho kết quả sai khi có kế thừa.

**validate(...) chỉ ném IllegalArgumentException khi dữ liệu rỗng.** Điều đó bỏ qua hợp đồng ghi lỗi và cản trở việc hiển thị nhiều lỗi cùng lúc. Dùng **rejectValue** hoặc **reject** cho dữ liệu đầu vào không hợp lệ.

**Ghi global error cho mọi lỗi.** Nếu thiếu riêng **title**, dùng **rejectValue("title", ...)** để UI có thể liên kết thông báo với đúng trường. Dùng **reject(...)** cho điều kiện toàn đối tượng.

**Gọi validate nhưng bỏ qua Errors.** Vì **validate(...)** trả **void**, bên gọi phải đọc **hasErrors()** hoặc danh sách lỗi. Không được suy luận “không có exception nghĩa là valid”.

**Chỉ khai báo một bean Validator rồi mong @Valid tự sử dụng ở mọi nơi.** Việc phát hiện validator phụ thuộc cấu hình MVC, DataBinder và phạm vi đăng ký. Cần xác nhận validator được gắn vào binder hoặc được gọi tường minh; một bean có mặt trong ApplicationContext không đồng nghĩa mọi DTO đều tự chạy validator đó.

**Dùng setValidator thay vì addValidators mà không xem cấu hình cũ.** Có thể thay mất validator toàn cục vốn xử lý các annotation; khi cần kết hợp nhiều luật, kiểm tra danh sách validator của binder trước khi chọn cách đăng ký.

**Truy cập field lồng nhau khi giá trị null hoặc quên popNestedPath.** Trường hợp đầu có thể gây exception, trường hợp sau làm path của lỗi tiếp theo bị nối sai. Kiểm tra null và dùng **try/finally**.

**Dùng validator singleton với field mutable chứa request hiện tại.** Validator có thể được gọi đồng thời bởi nhiều request. Nên giữ implementation stateless và truyền toàn bộ thông tin riêng của một lượt qua **target/Errors** hoặc kiến trúc thích hợp.

**Đồng nhất binding lỗi với validation lỗi.** **BindingResult** có thể chứa **FieldError.isBindingFailure() == true** do không chuyển được kiểu. Tất cả lỗi chỉ được xử lý như validation format khi không phân biệt sẽ làm khó chẩn đoán.

## 10. Kiểm thử hợp đồng

Nên kiểm thử riêng lớp validator trước khi ghép vào controller:

| Test | Dữ liệu | Kết quả mong đợi |
| --- | --- | --- |
| Hỗ trợ kiểu | **EventPeriod.class** và **String.class** | **true** và **false** tương ứng |
| Thiếu tiêu đề | **title = "   "**; hai ngày hợp lệ | 1 **FieldError** tại **title** |
| Thiếu ngày bắt đầu | **startDate = null** | 1 **FieldError** tại **startDate** |
| Ngày đảo thứ tự | **startDate > endDate**, title hợp lệ | 1 **ObjectError** cấp toàn đối tượng |
| Nhiều vi phạm | title trắng, ngày đảo thứ tự | 1 lỗi field và 1 lỗi global |
| Dữ liệu hợp lệ | title có nội dung, đủ hai ngày, start không sau end | **hasErrors() == false** |
| Khả năng tái sử dụng | Gọi cùng một instance validator cho các object khác nhau | Không rò lỗi/trạng thái giữa các lần gọi |

Với tích hợp Spring MVC, có thể dùng **MockMvc** để kiểm tra rằng custom validator đã thực sự được đăng ký qua **@InitBinder**; request sai constraint phải làm controller nhận lỗi và không gọi service ghi dữ liệu. Đối với form có lỗi type conversion, xác minh lỗi binding vẫn hiện diện trong **BindingResult** cùng với lỗi validation nếu có.

Câu hỏi tự kiểm tra:

1. Tại sao **supports(Class<?>)** cần có dù **validate(Object, Errors)** đã nhận target? Vì framework hoặc code gọi cần xác định validator tương thích với loại đối tượng trước khi sử dụng.
2. Khi title rỗng và khoảng ngày không hợp lệ, **validate(...)** nên trả về gì? Không trả giá trị (**void**); nó ghi hai lỗi vào **Errors**.
3. Khi nào dùng **rejectValue** thay **reject**? Khi lỗi gắn với một field cụ thể thay vì toàn đối tượng.
4. Có gọi **@Valid** mà không tạo custom Spring Validator được không? Có thể dùng các Jakarta Bean Validation constraint khi hệ thống có provider và cấu hình tương ứng; nếu muốn logic custom từ Spring Validator thì phải đăng ký/gọi implementation đó.
5. Validation qua DataBinder có đảm bảo thao tác lưu database thành công không? Không; nghiệp vụ, nhất quán và cạnh tranh đồng thời vẫn thuộc các tầng tiếp theo.

## Tài liệu chính thức để đối chiếu

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework API — Validator, hai phương thức hợp đồng và validateObject (6.2.10)](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/Validator.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — Cấu hình validator trong MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
