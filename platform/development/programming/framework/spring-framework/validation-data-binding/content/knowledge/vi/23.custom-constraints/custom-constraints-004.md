# ConstraintValidator<A,T>: vai trò của initialize() và isValid()

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích cách Jakarta Bean Validation gắn một annotation ràng buộc tùy chỉnh với lớp kiểm tra, phân biệt cấu hình một lần trong `initialize()` với việc đánh giá giá trị trong `isValid()`, tự xây dựng constraint có tham số, và tích hợp nó với Spring Framework. Trọng tâm là hợp đồng của `ConstraintValidator<A,T>` và những sai sót thường gặp khi thực thi validator trong ứng dụng thật.

## 1. ConstraintValidator nằm ở đâu?

Jakarta Bean Validation cho phép khai báo quy tắc ngay trên mô hình dữ liệu, chẳng hạn `@NotNull`, `@Size` hoặc một annotation do ứng dụng tự định nghĩa. Để tạo constraint mới, thông thường cần hai thành phần:

1. **Annotation constraint** định nghĩa tên quy tắc, thuộc tính cấu hình, thông điệp lỗi và nơi có thể áp dụng.
2. **Lớp triển khai `ConstraintValidator`** chứa logic kiểm tra kiểu dữ liệu cụ thể.

Ví dụ, ứng dụng muốn kiểm tra mã đơn hàng có dạng `ORD-1234`: tiền tố có thể cấu hình, phía sau là đúng bốn chữ số ASCII. Annotation `@OrderCode(prefix = "ORD-", digits = 4)` mô tả yêu cầu; `OrderCodeValidator` thực hiện kiểm tra.

Luồng cơ bản:

~~~text
Đối tượng/giá trị cần kiểm tra
    -> @OrderCode trên thuộc tính
    -> Bean Validation provider tìm validator phù hợp
    -> tạo/lấy ConstraintValidator và gọi initialize(annotation)
    -> gọi isValid(value, context)
    -> true: hợp lệ; false: tạo ConstraintViolation
    -> caller nhận tập lỗi hoặc framework xử lý lỗi
~~~

**Phân biệt:** annotation tự nó không chạy logic. Phải có một điểm kích hoạt validation, ví dụ `Validator.validate(bean)`, `@Valid @RequestBody` trong Spring MVC, hoặc method validation đã được cấu hình.

Trong Spring Framework 6 / Spring Boot 3 dùng namespace **`jakarta.validation.*`**. Các ví dụ cũ sử dụng `javax.validation.*` thuộc hệ sinh thái trước đó; không trộn hai namespace trong cùng ví dụ.

## 2. Đọc đúng hai tham số generic và hợp đồng phương thức

Giao diện có cấu trúc:

~~~java
public interface ConstraintValidator<A extends Annotation, T> {
    default void initialize(A constraintAnnotation) { }

    boolean isValid(T value, ConstraintValidatorContext context);
}
~~~

- **`A`**: kiểu annotation ràng buộc mà validator xử lý, ví dụ `OrderCode`. Đối số truyền vào `initialize(A)` là instance annotation cụ thể đã gắn trên thuộc tính.
- **`T`**: kiểu giá trị được kiểm tra, ví dụ `String`. Vì vậy `ConstraintValidator<OrderCode, String>` dùng cho `@OrderCode` trên giá trị có kiểu tương thích với `String`.
- **`initialize(A)`**: phương thức mặc định rỗng; chỉ cần override khi phải đọc/cài đặt cấu hình của annotation hoặc chuẩn bị dữ liệu bất biến dùng chung.
- **`isValid(T, ConstraintValidatorContext)`**: phương thức bắt buộc; trả `true` khi giá trị đáp ứng constraint, `false` khi vi phạm. `context` cho phép điều khiển thông điệp và đường dẫn lỗi.

Chẳng hạn, nếu muốn cùng một annotation kiểm tra `String` và một kiểu miền riêng, có thể đăng ký những validator tương ứng trong `@Constraint(validatedBy = {...})`. Không dùng một validator nhận kiểu không phù hợp rồi ép kiểu tùy tiện. Đối với generic của `T`, quy tắc type resolution của Jakarta Validation cũng có hạn chế: không khai báo trực tiếp kiểu parameterized như `List<String>` làm kiểu `T`; nếu cần validation cả tập hợp, cân nhắc `List<?>` hoặc constraint trên từng phần tử.

## 3. Lifecycle: initialize một lần cho instance, isValid nhiều lần

Provider (chẳng hạn Hibernate Validator) điều phối vòng đời:

1. Tìm khai báo constraint và kiểu giá trị.
2. Tạo hoặc lấy instance `ConstraintValidator` qua `ConstraintValidatorFactory`.
3. **Bảo đảm gọi `initialize()` trước khi dùng instance đó cho validation.**
4. Gọi `isValid()` khi cần kiểm tra giá trị; provider được phép giữ và tái sử dụng instance.

Không được suy diễn rằng mỗi request/đối tượng đều có validator mới, hay `initialize()` được gọi đúng một lần cho toàn ứng dụng. Số lượng instance và chính sách cache phụ thuộc provider. Hãy hiểu `initialize()` là **khởi tạo cho từng instance và cấu hình constraint**, còn `isValid()` là **đánh giá cho từng lần kiểm tra**.

Điều này dẫn đến một quy tắc thiết kế quan trọng: **`isValid()` phải an toàn khi nhiều thread gọi đồng thời**. Các trường được gán trong `initialize()` nên trở thành trạng thái cấu hình chỉ đọc sau khởi tạo. Không lưu `value`, `context`, lỗi của request hoặc bộ đếm thay đổi vào field của validator. Không sửa trạng thái đối tượng đầu vào trong `isValid()`.

## 4. Ví dụ đầy đủ: @OrderCode có prefix và digits

Ta xây dựng bốn file Java trong package `com.example.validation`. Đây là ví dụ độc lập dùng Java 17+, Jakarta Validation API và một provider như Hibernate Validator.

### 4.1. Khai báo annotation: OrderCode.java

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = OrderCodeValidator.class)
public @interface OrderCode {
    String prefix() default "ORD-";
    int digits() default 4;

    String message() default
            "phải bắt đầu bằng {prefix} và có đúng {digits} chữ số";

    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Ý nghĩa từng phần:

- `@Constraint(validatedBy = OrderCodeValidator.class)` nối annotation với lớp triển khai. Thiếu liên kết hoặc trỏ sai validator sẽ khiến provider không thể thực hiện quy tắc như mong đợi.
- `@Retention(RUNTIME)` giữ annotation tại runtime để validation engine đọc được.
- `@Target` giới hạn nơi sử dụng: ở đây là field, parameter, annotation composition và record component.
- `message` cung cấp thông điệp mặc định. `{prefix}` và `{digits}` được nội suy từ attribute của annotation.
- `groups` và `payload` là các phần tử chuẩn của một constraint annotation. `groups` hỗ trợ nhóm validation; `payload` mang metadata tùy chọn, không phải dữ liệu đầu vào cần kiểm tra.
- `prefix` và `digits` là cấu hình riêng của quy tắc, được chuyển đến `initialize()`.

Với annotation được dùng cho những loại phần tử khác (getter, type-use...), phải mở rộng `@Target` một cách có chủ đích. Nếu định nghĩa constraint lặp được, cần thêm cơ chế `@Repeatable` hoặc danh sách container phù hợp; ví dụ này chỉ cần một annotation trên mỗi field.

### 4.2. Triển khai validator: OrderCodeValidator.java

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class OrderCodeValidator
        implements ConstraintValidator<OrderCode, String> {

    private String prefix;
    private int digits;

    @Override
    public void initialize(OrderCode annotation) {
        prefix = annotation.prefix();
        digits = annotation.digits();

        if (prefix.isBlank() || digits < 1) {
            throw new IllegalArgumentException(
                    "Invalid @OrderCode configuration");
        }
    }

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        if (!value.startsWith(prefix)) {
            return false;
        }

        String suffix = value.substring(prefix.length());
        if (suffix.length() != digits) {
            return false;
        }

        for (int i = 0; i < suffix.length(); i++) {
            char c = suffix.charAt(i);
            if (c < '0' || c > '9') {
                return false;
            }
        }
        return true;
    }
}
~~~

**Phân tích `initialize()`:** nó đọc hai attribute từ annotation và lưu cấu hình cần thiết cho các lần validation sau. Thao tác kiểm tra `prefix`/`digits` tại đây bảo vệ người viết annotation khỏi cấu hình bất hợp lý. Nếu cấu hình sai, đây là lỗi định nghĩa constraint (được báo thông qua lỗi validation runtime), **không phải** một giá trị người dùng nhập không hợp lệ. Không cần tạo dữ liệu request hay thực hiện truy vấn mạng ở bước này.

**Phân tích `isValid()`:** giá trị `null` trả về `true` theo tập quán tách kiểm tra định dạng và kiểm tra sự hiện diện; `@NotNull` sẽ đảm nhiệm yêu cầu bắt buộc. Với giá trị khác `null`, validator xác minh lần lượt tiền tố, độ dài phần hậu tố và từng ký tự số từ `'0'` đến `'9'`. Cách kiểm tra ký tự tường minh này có chủ đích: định dạng mã là số ASCII, không chấp nhận mọi ký tự Unicode được xem là chữ số.

Giả sử cấu hình `prefix = "ORD-"`, `digits = 4`:

| Giá trị | Kết quả riêng của `isValid()` | Lý do |
| --- | --- | --- |
| `ORD-1234` | `true` | Đúng tiền tố và bốn chữ số |
| `ORD-12A4` | `false` | Có ký tự A |
| `PAY-1234` | `false` | Sai tiền tố |
| `ORD-12345` | `false` | Thừa một chữ số |
| `ORD-` | `false` | Thiếu phần số |
| `null` | `true` | Việc bắt buộc không-null thuộc `@NotNull` |

Cách dùng `String.startsWith` phân biệt chữ hoa/chữ thường. Nếu nghiệp vụ cho phép mã không phân biệt hoa thường, cần thiết kế quy tắc rõ ràng và bảo đảm cách so sánh nhất quán; không tự chuẩn hóa bằng cách **sửa** đối tượng truyền vào validator.

### 4.3. Áp dụng cho model: OrderRequest.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotNull;

public final class OrderRequest {
    @NotNull
    @OrderCode(prefix = "ORD-", digits = 4)
    private final String code;

    public OrderRequest(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

Hai annotation giải quyết hai vấn đề độc lập:

- `@NotNull`: mã không được thiếu.
- `@OrderCode`: nếu có mã, định dạng phải hợp lệ.

Đừng nhầm kết quả `isValid(null) == true` với kết quả tổng thể của validation model. Khi `code == null`, ràng buộc `@OrderCode` cho qua, nhưng `@NotNull` vẫn tạo lỗi và toàn bộ model là không hợp lệ.

Nếu còn muốn từ chối chuỗi trắng, thêm `@NotBlank` hoặc thiết kế constraint đúng với yêu cầu; đừng mặc định mọi trường hợp `null`, chuỗi rỗng và chuỗi trắng có chung ý nghĩa.

### 4.4. Chạy thử không cần Spring container: Demo.java

~~~java
package com.example.validation;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public final class Demo {
    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            String[] samples = {
                "ORD-1234", "ORD-12A4",
                "PAY-1234", "ORD-12345", null
            };

            for (String code : samples) {
                OrderRequest request = new OrderRequest(code);
                boolean valid = validator.validate(request).isEmpty();

                System.out.println(
                        String.valueOf(code) + " -> " +
                        (valid ? "VALID" : "INVALID"));
            }
        }
    }
}
~~~

Đặt các file Java vào `src/main/java/com/example/validation/`. Một `pom.xml` tối thiểu cho demo Maven độc lập:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>custom-validation-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
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

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

Các **dòng do `Demo` in ra** (không tính log khởi tạo hoặc log Maven/provider nếu môi trường có):

~~~text
ORD-1234 -> VALID
ORD-12A4 -> INVALID
PAY-1234 -> INVALID
ORD-12345 -> INVALID
null -> INVALID
~~~

Ở đây `null -> INVALID` là kết quả **tổng hợp trên `OrderRequest`**, vì `@NotNull` thất bại. Bản thân `OrderCodeValidator.isValid(null, ...)` vẫn trả `true`.

Một dự án Spring Boot 3 đã có dependency `spring-boot-starter-validation` thường được cung cấp cả API và provider; không cần sao chép nguyên `pom.xml` demo ở trên vào ứng dụng Spring Boot. Demo Maven độc lập dùng phiên bản cố định để ví dụ tái lập được.

## 5. ConstraintValidatorContext: khi cần thông điệp chi tiết

Nếu chỉ trả `false`, provider dùng `message` mặc định của annotation. Khi cần thông điệp riêng cho từng nhánh, có thể dùng `ConstraintValidatorContext`.

Đoạn sau minh họa việc **thay riêng nhánh sai tiền tố** trong `isValid()`; đây là một đoạn thay thế, không phải lớp Java độc lập:

~~~java
if (!value.startsWith(prefix)) {
    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            "Mã phải bắt đầu bằng " + prefix)
           .addConstraintViolation();
    return false;
}
~~~

Ý nghĩa:

1. `disableDefaultConstraintViolation()` tắt violation mặc định của lần đánh giá này.
2. `buildConstraintViolationWithTemplate(...).addConstraintViolation()` tạo violation mới.
3. Sau khi tắt thông điệp mặc định, **phải thêm ít nhất một violation** nếu kết quả là `false`.
4. Chỉ tạo thông điệp lỗi khi thật sự không hợp lệ; đừng lưu `context` vào biến instance.

Đối với constraint đặt trên cả object (class-level), `context` còn cho phép gắn lỗi vào một property cụ thể bằng `addPropertyNode("fieldName")` trước `addConstraintViolation()`. Trường hợp này khác với ví dụ field-level `@OrderCode`.

## 6. Tích hợp Spring Framework

Trong ứng dụng Spring MVC có Bean Validation provider trên classpath, `@Valid` hoặc `@Validated` có thể kích hoạt việc kiểm tra object nhận từ HTTP request:

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class OrderController {
    @PostMapping("/orders")
    public ResponseEntity<Void> create(
            @Valid @RequestBody OrderRequest request) {
        return ResponseEntity.accepted().build();
    }
}
~~~

Khi request được deserialise thành `OrderRequest` và validation chạy, `@OrderCode` gọi đến validator đã đăng ký. Với trường hợp validation thông thường của một `@RequestBody` object trong Spring MVC, lỗi dẫn đến `MethodArgumentNotValidException` và thông thường được trả về HTTP 400. Chữ ký method có ràng buộc trực tiếp trên tham số có thể đi qua cơ chế method validation với loại exception khác (ví dụ `HandlerMethodValidationException`), vì vậy handler lỗi cần xét đúng trường hợp.

Đối với lời gọi method của Spring bean ở tầng service, method validation là một cơ chế riêng: cần cấu hình và điểm kích hoạt phù hợp (thường qua `@Validated` và hạ tầng validation của Spring). Chỉ viết `@OrderCode` trên tham số của một method Java thông thường không khiến mọi lời gọi trực tiếp tự động được kiểm tra.

**So sánh nhanh các thành phần dễ nhầm:**

| Thành phần | Vai trò |
| --- | --- |
| `jakarta.validation.ConstraintValidator<A,T>` | Triển khai một constraint annotation trên kiểu `T` |
| `jakarta.validation.Validator` | API gọi validation cho bean và lấy `Set<ConstraintViolation<T>>` |
| `jakarta.validation.Valid` | Kích hoạt/cascade validation tại những điểm hỗ trợ, không tự là quy tắc kiểm tra |
| `org.springframework.validation.Validator` | Giao diện validation riêng của Spring, làm việc với `Errors`; khác API Jakarta |
| `org.springframework.validation.annotation.Validated` | Hỗ trợ validation groups và cơ chế method validation trong Spring khi được tích hợp đúng |

Spring có thể hỗ trợ dependency injection trong custom validator nhờ factory tích hợp, nhưng **không nên giả định** rằng cùng lớp validator được khởi tạo bằng Java SE `Validation.buildDefaultValidatorFactory()` cũng luôn được Spring inject. Nếu logic phụ thuộc service, phải kiểm tra chiến lược khởi tạo validator của runtime thực tế.

## 7. Ranh giới trách nhiệm và các lỗi thường gặp

**Đặt việc nào ở initialize?** Đọc annotation attribute, kiểm tra cấu hình, chuẩn bị pattern hoặc cấu trúc dữ liệu dùng chung. Ví dụ có thể biên dịch `Pattern` từ một biểu thức regex cấu hình và lưu thành field chỉ đọc sau khởi tạo. Tránh những thao tác phụ thuộc một request cụ thể.

**Đặt việc nào ở isValid?** Quyết định giá trị hiện tại có đạt quy tắc hay không. Các kiểm tra nên có kết quả xác định theo giá trị và cấu hình. Các giá trị sai định dạng bình thường nên trả `false`; không lạm dụng exception để biểu thị input sai. Nếu có exception bất ngờ từ validator, provider thường bọc nó thành `ValidationException`, khác lỗi ràng buộc thông thường.

Những tình huống cần lưu ý:

- **Nhầm `A` và `T`:** `ConstraintValidator<OrderCode, String>` nhận annotation `OrderCode` và dữ liệu `String`; đảo ngược generic khiến code không đúng hợp đồng.
- **Không có implementation/provider:** có API Jakarta trên classpath chưa chắc đã đủ; cần một provider Bean Validation. Nếu không có provider, việc xây dựng `ValidatorFactory` có thể thất bại.
- **Khai báo annotation sai kiểu field:** ví dụ `@OrderCode` trên `Integer` nhưng chỉ có validator cho `String` có thể tạo `UnexpectedTypeException`; không được xem là `false` bình thường.
- **Quên kích hoạt validation:** tạo `new OrderRequest("BAD")` không tự gọi `isValid()`; cần `validator.validate(...)` hoặc integration phù hợp.
- **Coi `initialize()` là mỗi lần validate:** nó có thể chỉ chạy một lần cho instance được cache. Logic dựa vào số lần gọi sẽ sai.
- **Dùng field mutable cho dữ liệu lần gọi:** giữ trạng thái của request trong validator có thể gây lỗi khi chạy đồng thời; `isValid()` phải thread-safe.
- **Xử lý `null` sai kỳ vọng:** tách validation hiện diện (`@NotNull`) khỏi validation định dạng; thống nhất rõ yêu cầu nếu có ngoại lệ.
- **Thay đổi giá trị đầu vào:** chuẩn hóa hay sửa DTO ngay trong `isValid()` vi phạm hợp đồng; hãy làm ở lớp chuyển đổi/chuẩn hóa trước validation nếu nghiệp vụ cần.
- **Thông điệp tùy chỉnh nhưng không thêm violation:** sau `disableDefaultConstraintViolation()` cần tạo ít nhất một violation khi trả `false`.
- **Validation nặng hoặc có side effect:** truy vấn DB, HTTP, ghi log dữ liệu nhạy cảm, hoặc ghi trạng thái nghiệp vụ trong mỗi `isValid()` có thể làm tăng độ trễ, gây bất định và khó kiểm thử. Với điều kiện liên quan trạng thái hệ thống, cần xác định rõ tầng nào chịu trách nhiệm và cơ chế nhất quán dữ liệu.
- **Đọc nhầm namespace:** Spring Boot 3+/Spring Framework 6+ dùng `jakarta.validation`; ví dụ `javax.validation` từ tài liệu cũ không tương thích trực tiếp nếu trộn API.

## 8. Cách kiểm thử một custom constraint

Ít nhất nên kiểm tra: giá trị hợp lệ, sai tiền tố, sai độ dài, ký tự không hợp lệ, `null`, và cấu hình annotation không hợp lệ. Tách hai cấp kiểm thử:

1. **Unit test logic validator:** khởi tạo validator bằng cấu hình thử nghiệm rồi kiểm tra logic. Nếu trực tiếp gọi `isValid()`, việc dựng đúng `ConstraintValidatorContext` có thể phức tạp; thường tiện hơn khi dùng provider thật.
2. **Integration test Bean Validation:** dùng `Validator.validate(bean)` để xác minh annotation được đọc, validator được chọn, thông điệp được nội suy, và các constraint kết hợp như `@NotNull` hoạt động đúng. Ví dụ `Demo` phía trên chính là một smoke test của đường đi này.

Nếu test nội dung cụ thể của `ConstraintViolation`, đừng giả định thứ tự các violation trong `Set`; lấy theo `propertyPath`/`messageTemplate` hoặc sắp xếp ổn định trước khi đối chiếu. Khi kiểm thử trong Spring MVC, xác minh thêm response HTTP và handler exception theo phiên bản/cơ chế validation thực tế.

## 9. Ghi nhớ và tự kiểm tra

Hãy tự trả lời ba câu hỏi:

1. Vì sao `initialize()` phù hợp để đọc `prefix`, còn `isValid()` mới phù hợp để kiểm tra `ORD-1234`? Vì cấu hình thuộc annotation của instance validator, còn giá trị đầu vào thay đổi giữa các lần gọi.
2. Vì sao `isValid(null)` có thể trả `true` mà `Validator.validate(new OrderRequest(null))` vẫn có lỗi? Vì `@NotNull` là một constraint độc lập.
3. Vì sao không lưu `lastValidatedCode` vào field để dùng ở lần tiếp theo? Vì provider có thể cache validator và gọi `isValid()` đồng thời từ nhiều thread.

**Mô hình cần nhớ:** `ConstraintValidator<A,T>` gắn *constraint annotation A* với *kiểu dữ liệu T*; `initialize(A)` chuẩn bị cấu hình cho instance; `isValid(T, context)` kiểm tra từng giá trị, an toàn với concurrent calls và không làm thay đổi input. Kết quả `false` được provider chuyển thành violation để caller hoặc Spring xử lý.

## Tài liệu tham khảo

- [Jakarta Validation 3.1 specification – Constraint validation implementation](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.pdf)
- [Jakarta ConstraintValidator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintValidator.html)
- [Hibernate Validator reference guide – Custom constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
