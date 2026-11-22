# `@OverridesAttribute` khi tùy chỉnh constraint thành phần

## 1. Mục tiêu và bối cảnh

Trong Spring Framework, việc kiểm tra dữ liệu theo annotation thường sử dụng **Jakarta Validation (Bean Validation)** cùng một provider như Hibernate Validator. Khi nhiều quy tắc luôn đi cùng nhau, ta có thể định nghĩa một **composed constraint** (constraint tổng hợp): một annotation mới mang sẵn các annotation ràng buộc thành phần như `@Size`, `@Pattern`, `@NotNull`.

Bài này tập trung vào **`jakarta.validation.OverridesAttribute`**: cách đưa thuộc tính của annotation tổng hợp xuống thuộc tính của từng constraint thành phần để người sử dụng cấu hình chúng ngay tại vị trí khai báo. Sau bài học, bạn có thể:
- Tạo một annotation tổng hợp không cần tự viết `ConstraintValidator` khi các constraint có sẵn đã diễn đạt đủ quy tắc.
- Ánh xạ thuộc tính như `min`, `max`, `regexp` và `message` bằng `@OverridesAttribute`.
- Chọn đúng một constraint trong nhiều lần khai báo cùng loại bằng `constraintIndex`.
- Phân biệt override cấu hình thành phần với thông báo lỗi tổng hợp và dùng annotation trong Spring MVC.
- Kiểm chứng giá trị override bằng kết quả validation và metadata.

**Phân biệt tên:** `@OverridesAttribute` thuộc Jakarta Validation, khác `org.springframework.core.annotation.AliasFor` của Spring. `@AliasFor` xử lý quan hệ thuộc tính giữa annotation trong cơ chế đọc annotation của Spring; nó không thay cho quy tắc override của Bean Validation.

## 2. Constraint composition hoạt động thế nào?

Ví dụ cùng một mã người dùng cần dài 4–12 ký tự và chỉ có chữ in hoa, chữ số, dấu gạch dưới:

```java
@Size(min = 4, max = 12)
@Pattern(regexp = "[A-Z0-9_]+")
private String userCode;
```

Nếu quy tắc này lặp lại tại nhiều DTO, ta đặt `@Size` và `@Pattern` lên annotation `@UserCode`, rồi đặt `@UserCode` lên các trường. Theo chuẩn Jakarta Validation, các composing constraints được kết hợp theo phép **AND**: giá trị phải thỏa mãn tất cả quy tắc thì mới hợp lệ. Mỗi constraint thành phần vẫn có logic validation và thông báo riêng.

Vấn đề: nếu thành phần luôn khai báo `@Size(min = 4, max = 12)`, làm thế nào tại một chỗ sử dụng lại yêu cầu độ dài 5–8 mà không tạo annotation khác? `@OverridesAttribute` giải quyết bằng cách liên kết một phương thức thuộc tính của `@UserCode` với thuộc tính của `@Size`. Giá trị cung cấp khi dùng `@UserCode(min = 5, max = 8)` sẽ được chuyển xuống `@Size.min` và `@Size.max`.

**Phạm vi cơ chế:** Đây là phép ánh xạ *giá trị thuộc tính*, không phải ghi đè phương thức Java bằng `@Override`; nó cũng không làm thay đổi định nghĩa toàn cục của `@Size` hay `@Pattern`.

## 3. Cú pháp và nguyên tắc ánh xạ

```java
@OverridesAttribute(constraint = Size.class, name = "min")
int min() default 4;
```

`@OverridesAttribute` phải đặt trên **phương thức khai báo thuộc tính trong một annotation tổng hợp** (ví dụ `min()`), không đặt lên một trường DTO hay phương thức nghiệp vụ. Ba thành phần xác định đích ánh xạ là:

| Tham số | Ý nghĩa |
| --- | --- |
| `constraint` | Lớp annotation của constraint thành phần trực tiếp, ví dụ `Size.class` hoặc `Pattern.class`; bắt buộc. |
| `name` | Tên thuộc tính đích, ví dụ `"min"`, `"max"`, `"regexp"`, `"message"`. Nếu bỏ qua, mặc định trùng tên phương thức bên ngoài. |
| `constraintIndex` | Chỉ số bắt đầu từ `0` để phân biệt nhiều constraint cùng loại; mặc định `-1` dùng cho một khai báo duy nhất. |

Các điều kiện quan trọng:
1. Kiểu trả về của thuộc tính bên ngoài phải **trùng chính xác** kiểu của thuộc tính đích; chẳng hạn `@Size.min` là `int`, `@Pattern.regexp` là `String`. `long` không thay thế được `int`.
2. Constraint được chỉ định phải là **composing constraint trực tiếp** của annotation chứa quy tắc override. Nếu nhiều lớp composition lồng nhau, mỗi lớp áp dụng forwarding tại cấp trực tiếp của nó; không nhảy xuyên nhiều cấp bằng một annotation override.
3. Với mỗi thuộc tính đích, ánh xạ phải rõ ràng, không mơ hồ hoặc mâu thuẫn. Cấu hình composition sai có thể gây `ConstraintDefinitionException` khi provider đọc metadata hoặc thực hiện validation.
4. Giá trị mặc định của thuộc tính bên ngoài cũng có hiệu lực: nếu người dùng không truyền đối số, chính `default` đó là giá trị chuyển xuống constraint thành phần.

Ví dụ cùng tên thuộc tính thì có thể bỏ `name`:

```java
@OverridesAttribute(constraint = Pattern.class)
String regexp() default "[A-Z0-9_]+";
```

Ở đây `regexp()` của annotation tổng hợp ánh xạ tới `Pattern.regexp()`. Ngược lại, nếu đặt tên thân thiện hơn như `formatMessage()`, bắt buộc ghi `name = "message"` để ánh xạ đúng.

## 4. Thực hành chạy được: tùy chỉnh `@Size` và `@Pattern`

Ví dụ độc lập dưới đây dùng **Java 17**, **Jakarta Validation 3.0** và **Hibernate Validator 8.0.6.Final**. Nó chạy bằng Maven, không cần khởi động Spring; phần sau sẽ nối lại với Spring MVC. Cấu trúc:

```text
validation-demo/
├── pom.xml
└── src/main/java/demo/
    ├── UserCode.java
    └── Main.java
```

### 4.1. Khai báo dependency

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` cung cấp provider và Jakarta Validation API theo dependency bắc cầu. `expressly` cung cấp Jakarta Expression Language để nội suy thông báo; ứng dụng Spring Boot thường được quản lý dependency qua starter.

### 4.2. Tạo composed constraint

Tạo `src/main/java/demo/UserCode.java`:

```java
package demo;

import jakarta.validation.Constraint;
import jakarta.validation.OverridesAttribute;
import jakarta.validation.Payload;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = {})
@Size(min = 4, max = 12)
@Pattern(regexp = "[A-Z0-9_]+")
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface UserCode {

    String message() default "User code is invalid";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    @OverridesAttribute(constraint = Size.class, name = "min")
    int min() default 4;

    @OverridesAttribute(constraint = Size.class, name = "max")
    int max() default 12;

    @OverridesAttribute(constraint = Pattern.class)
    String regexp() default "[A-Z0-9_]+";

    @OverridesAttribute(constraint = Size.class, name = "message")
    String lengthMessage() default "length must be between {min} and {max}";

    @OverridesAttribute(constraint = Pattern.class, name = "message")
    String formatMessage() default "invalid characters";
}
```

Giải thích từng phần:
- `@Constraint(validatedBy = {})` báo rằng `@UserCode` là một constraint hợp lệ, nhưng không có validator riêng: `@Size` và `@Pattern` đảm nhận kiểm tra.
- `@Retention(RUNTIME)` giúp provider đọc annotation khi chạy. `@Target(ANNOTATION_TYPE)` cho phép dùng tiếp `@UserCode` như thành phần của một annotation tổng hợp khác.
- `message()`, `groups()`, `payload()` là các thuộc tính quy ước bắt buộc của constraint annotation thông thường.
- `min()` và `max()` chuyển đến hai thuộc tính số nguyên khác nhau của `@Size`.
- `regexp()` minh họa quy tắc mặc định `name`: tên phương thức bên ngoài và đích trùng nhau.
- `lengthMessage()` và `formatMessage()` tùy biến **thông báo của từng constraint thành phần**; `{min}`, `{max}` được nội suy từ các giá trị thực tế đã override.

Đừng nhầm `UserCode.message()` với `Size.message()` hay `Pattern.message()`: chúng là ba thuộc tính trên ba annotation khác nhau. Chỉ khai báo `UserCode.message()` **không tự động** chuyển thông báo xuống thành phần.

### 4.3. Đặt annotation lên dữ liệu và kiểm tra

Tạo `src/main/java/demo/Main.java`:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import java.util.TreeSet;

public class Main {

    static final class UserRequest {
        @UserCode(min = 5, max = 8, regexp = "[A-Z][A-Z0-9_]*")
        private final String code;

        UserRequest(String code) {
            this.code = code;
        }
    }

    private static void check(Validator validator, String value) {
        TreeSet<String> messages = new TreeSet<>();

        for (ConstraintViolation<UserRequest> violation
                : validator.validate(new UserRequest(value))) {
            messages.add(violation.getMessage());
        }

        System.out.println(String.valueOf(value) + " -> " + messages);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            check(validator, "AB");
            check(validator, "Abc_12");
            check(validator, "ABC_12");
            check(validator, null);
        }
    }
}
```

Chạy tại thư mục `validation-demo` (cần JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
```

Các dòng do `Main` in ra trên stdout (các log Maven/provider nếu có là riêng):

```text
AB -> [length must be between 5 and 8]
Abc_12 -> [invalid characters]
ABC_12 -> []
null -> []
```

- `AB` có đúng định dạng nhưng chỉ dài 2 ký tự nên vi phạm `@Size(min=5,max=8)`.
- `Abc_12` dài 6 ký tự nhưng chứa chữ thường `b` và `c`; giá trị `regexp` tại nơi sử dụng đã thay cấu hình của `@Pattern`.
- `ABC_12` hợp lệ với cả hai thành phần.
- `null` được `@Size` và `@Pattern` coi là hợp lệ; nếu bắt buộc có giá trị, thêm `@NotNull` hoặc `@NotBlank` tùy mục tiêu. Không coi `@OverridesAttribute` là cơ chế tự động kiểm tra null.

Lưu ý: mã này là một **annotation thật, có tác dụng thực tế**. Việc ghi trực tiếp `@Size(min=5,max=8)` và `@Pattern(regexp="...")` tại mọi trường sẽ cho ý nghĩa kiểm tra tương tự, nhưng không cung cấp API annotation gọn, tái sử dụng được.

## 5. Một thuộc tính bên ngoài override nhiều thuộc tính bên trong

Đôi khi cần độ dài **chính xác**: số ký tự tối thiểu và tối đa phải bằng nhau. Một phương thức của annotation tổng hợp có thể mang **nhiều `@OverridesAttribute`**, vì annotation này là repeatable.

Đoạn sau minh họa một annotation **khác** (cần đặt trong tệp riêng và thêm import Jakarta Validation/Java annotation tương tự ví dụ trước):

```java
@Documented
@Constraint(validatedBy = {})
@Size(min = 6, max = 6)
@Target({ElementType.FIELD, ElementType.METHOD,
         ElementType.PARAMETER, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ExactLength {

    String message() default "Length is invalid";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    @OverridesAttribute(constraint = Size.class, name = "min")
    @OverridesAttribute(constraint = Size.class, name = "max")
    int length() default 6;
}
```

Khi dùng `@ExactLength(length = 8)`, provider nhận `@Size(min = 8, max = 8)`. Với Jakarta Validation 3.0, hai annotation repeatable đặt trực tiếp trên cùng phương thức được phép; trong mã cũ có thể gặp cú pháp bao `@OverridesAttribute.List({...})`. Đây là một kỹ thuật riêng, **không liên quan** đến `constraintIndex` vì ta chỉ có **một** `@Size`.

## 6. Có nhiều constraint thành phần cùng loại: `constraintIndex`

Khi một annotation tổng hợp chứa hai `@Pattern`, chỉ `constraint = Pattern.class` và `name = "message"` là **chưa đủ** để chọn một bản. Dùng `constraintIndex = 0` cho `@Pattern` đầu tiên, `1` cho bản thứ hai. Ví dụ sau là đoạn khai báo annotation (thêm các import như phần 4):

```java
@Documented
@Constraint(validatedBy = {})
@Pattern(regexp = "[A-Z].*", message = "Must start with uppercase")
@Pattern(regexp = ".*[0-9]", message = "Must end with digit")
@Target({ElementType.FIELD, ElementType.METHOD,
         ElementType.PARAMETER, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface StartUpperEndDigit {

    String message() default "Invalid code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    @OverridesAttribute(
            constraint = Pattern.class,
            name = "message",
            constraintIndex = 0
    )
    String firstMessage() default "First character must be uppercase";

    @OverridesAttribute(
            constraint = Pattern.class,
            name = "message",
            constraintIndex = 1
    )
    String secondMessage() default "Last character must be a digit";
}
```

Dùng `@StartUpperEndDigit(secondMessage = "Missing trailing digit")` sẽ thay thông báo **chỉ của `@Pattern` thứ hai**. Chuỗi `"Abc"` đạt điều kiện đầu nhưng không kết thúc bằng số nên nhận thông báo mới. Chuỗi `"abc4"` vi phạm điều kiện đầu.

Quy tắc đếm chỉ số:
- Với hai annotation repeatable khai báo trực tiếp, chỉ số theo **thứ tự từ trái sang phải trong khai báo**, bắt đầu `0`.
- Với container `@Pattern.List({@Pattern(...), @Pattern(...)})`, chỉ số theo phần tử của mảng `value`.
- Không khai báo đồng thời constraint trực tiếp và qua `@Pattern.List` cho cùng kiểu trên một annotation tổng hợp; đặc tả quy định trường hợp đó có thể gây `ConstraintDeclarationException`.
- Khi chỉ có một `@Pattern`, không cần truyền `constraintIndex`; mặc định `-1` chỉ đúng bản duy nhất.

`constraintIndex` là chỉ số trong **các composing constraints cùng kiểu**, không phải số thứ tự của mọi annotation trên lớp.

## 7. Thông báo lỗi: nhiều violation hay một violation?

Mặc định, các constraint thành phần vẫn báo lỗi riêng. Nếu một giá trị vừa sai độ dài vừa sai định dạng, tập `ConstraintViolation` có thể chứa **hai violation** với các message của `@Size` và `@Pattern`. Thứ tự duyệt các violation không được đảm bảo; ví dụ `Main` sử dụng `TreeSet` để có thứ tự in ổn định.

Nếu API muốn trả **một** lỗi đại diện cho toàn bộ constraint tổng hợp, thêm `@ReportAsSingleViolation` lên **khai báo annotation tổng hợp**:

```java
@ReportAsSingleViolation
@Constraint(validatedBy = {})
@Size(min = 4, max = 12)
@Pattern(regexp = "[A-Z0-9_]+")
// ... @Target, @Retention và các thuộc tính như UserCode ở trên
public @interface UserCode {
    String message() default "User code is invalid";
    // ...
}
```

Đây là **đoạn minh họa vị trí annotation**, không phải file Java đầy đủ thay thế ví dụ 4. Lúc này, khi composition thất bại, provider báo một lỗi ở mức `@UserCode` với `UserCode.message()`. `@OverridesAttribute` vẫn truyền cấu hình xuống thành phần; `@ReportAsSingleViolation` thay cách tổng hợp báo lỗi. Hai cơ chế phục vụ hai việc khác nhau.

Chọn chiến lược theo hợp đồng API:
- Cần chỉ ra chính xác lỗi độ dài hay định dạng: giữ các violation thành phần và tùy biến `lengthMessage`/`formatMessage`.
- Cần che chi tiết quy tắc và trả một thông điệp đơn giản: dùng `@ReportAsSingleViolation`, cấu hình `message` ở annotation ngoài.

## 8. Tích hợp vào Spring Framework / Spring Boot

`@OverridesAttribute` được provider Jakarta Validation xử lý. Spring chuyển kết quả vào quy trình validation/binding khi DTO được đánh dấu đúng và có provider trên classpath. Với ứng dụng Spring Boot 3.x, thường khai báo các starter sau (đoạn `build.gradle` minh họa, giả sử dự án Boot đã cấu hình plugin và repositories):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

DTO có thể sử dụng `@UserCode` đã định nghĩa:

```java
public class CreateUserRequest {
    @UserCode(min = 5, max = 8, regexp = "[A-Z][A-Z0-9_]*")
    private String code;

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }
}
```

Một handler Spring MVC minh họa (đoạn mã nằm trong một dự án Boot, cần các import Spring MVC và `jakarta.validation.Valid`):

```java
@RestController
@RequestMapping("/users")
class UserController {

    @PostMapping
    ResponseEntity<Void> create(@Valid @RequestBody CreateUserRequest request) {
        // Xử lý dữ liệu đã qua validation ở tầng đầu vào.
        return ResponseEntity.noContent().build();
    }
}
```

Đối với DTO dạng `@RequestBody` có `@Valid`, Spring MVC kích hoạt Bean Validation, và khi các field constraint không đạt thường phát sinh `MethodArgumentNotValidException` (mặc định HTTP 400). Nếu chỉ đặt `@UserCode` lên trường mà không kích hoạt validation cho đối tượng, việc bind JSON tự nó không phải lúc nào cũng gọi provider. Với `@Validated`, ứng dụng còn có thể chọn group; với method validation trực tiếp, cơ chế/ngoại lệ có thể khác tùy chữ ký handler.

**Đặt ranh giới đúng:** override thuộc tính không tùy biến `WebDataBinder` và không thay đổi thời điểm Spring chạy validation. Nó chỉ điều chỉnh metadata mà Bean Validation provider dùng khi được gọi.

## 9. Xác minh metadata đã override

Nếu nghi ngờ giá trị chưa được chuyển xuống, đọc `ConstraintDescriptor` từ provider thay vì chỉ suy đoán từ thông báo. Đoạn sau dùng `validator` và `Main.UserRequest` của ví dụ 4, nên không phải chương trình độc lập:

```java
var property = validator.getConstraintsForClass(Main.UserRequest.class)
        .getConstraintsForProperty("code");

var outer = property.getConstraintDescriptors().iterator().next();

for (var component : outer.getComposingConstraints()) {
    System.out.println(component.getAnnotation().annotationType().getSimpleName()
            + " -> " + component.getAttributes());
}
```

Bạn sẽ tìm thấy `Size` với `min=5`, `max=8` và `Pattern` với `regexp=[A-Z][A-Z0-9_]*` (cùng các message override tương ứng). Thứ tự các descriptor và thứ tự các khóa thuộc tính **không được bảo đảm**; hãy kiểm tra theo tên constraint/attribute thay vì so khớp chuỗi stdout cố định.

`ConstraintDescriptor.getAttributes()` phản ánh giá trị hiệu lực sau quá trình override; đây là cách kiểm chứng rất hữu ích khi có nhiều annotation composition lồng nhau hoặc nhiều `@Pattern`.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Giá trị `min`/`max` truyền ngoài không có hiệu lực | Thiếu `@OverridesAttribute` hoặc chỉ khai báo method cùng tên mà không map | Đặt annotation lên chính method, trỏ đúng `Size.class` và `name`. |
| Provider báo lỗi định nghĩa constraint | Sai tên thuộc tính, sai kiểu, target không phải composing constraint trực tiếp, mapping mơ hồ | Đối chiếu API của constraint đích; kiểm tra `ConstraintDefinitionException` và descriptor. |
| Có hai `@Pattern` nhưng override nhầm bản | Thiếu hoặc sai `constraintIndex` | Ghi chỉ số `0`/`1` theo thứ tự khai báo, hoặc thứ tự mảng trong `@Pattern.List`. |
| Chỉ thấy một thông báo tổng quát | Có `@ReportAsSingleViolation` | Bỏ annotation đó nếu muốn xem lỗi riêng của từng thành phần. |
| Nhập `null` mà vẫn hợp lệ | `@Size`/`@Pattern` cho phép `null` | Kết hợp thêm `@NotNull` hoặc `@NotBlank` theo nghiệp vụ. |
| Spring không bắt lỗi của request body | Thiếu provider hoặc chưa kích hoạt validation của DTO | Thêm starter validation, dùng `@Valid @RequestBody`, kiểm tra handler và test. |
| Import không tìm thấy `jakarta.validation` | Trộn dependency `javax.validation` cũ với Spring Boot 3 / Jakarta | Thống nhất dependency và import theo thế hệ Spring/Jakarta đang dùng. |
| Muốn override constraint sâu hai cấp | `@OverridesAttribute` chỉ forward đến composing constraint trực tiếp | Thiết kế forwarding ở mỗi cấp composition cần thiết. |

Ngoài ra, không dùng `@OverridesAttribute` để đổi kiểu giá trị mà constraint không hỗ trợ, chẳng hạn chuyển `int` sang `String`. Với ràng buộc hoàn toàn mới không biểu diễn được bằng các constraint sẵn có, hãy cân nhắc viết `ConstraintValidator` riêng thay vì cố composition.

## 11. Tự kiểm tra hiểu bài

1. Đổi `@UserCode(min = 5, max = 8)` thành `@UserCode(min = 3, max = 6)`; đoán kết quả của `"AB"`, `"ABC_12"` rồi chạy để đối chiếu.
2. Thêm `@NotBlank` làm composing constraint của `@UserCode`. Kiểm tra lại đầu vào `null` và `""`; phân tích việc số lượng violation thay đổi.
3. Chuyển `@UserCode` sang `@ReportAsSingleViolation`, rồi gửi giá trị sai cả độ dài lẫn định dạng. So sánh số lượng violation và loại message.
4. Với `@StartUpperEndDigit`, đổi `firstMessage` và `secondMessage` khi sử dụng; kiểm chứng mỗi thay đổi chỉ tác động lên một `@Pattern`.
5. Dùng `ConstraintDescriptor` kiểm tra `min`, `max`, `regexp` thực tế: nếu truyền ở annotation ngoài khác default, metadata thành phần phải phản ánh giá trị mới.

Một cách ghi nhớ: **annotation ngoài cung cấp API cấu hình; `@OverridesAttribute` nối từng thuộc tính của API đó đến constraint thành phần; provider dùng giá trị đã nối để validate; `@ReportAsSingleViolation` quyết định cách gộp thông báo khi composition thất bại.**

## Tài liệu chuẩn để tra cứu

- [Jakarta Bean Validation 3.0 — Constraint composition](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintcomposition)
- [Jakarta Validation API — `@OverridesAttribute`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/overridesattribute)
- [Hibernate Validator 8 — Reference Guide, Constraint composition](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-constraint-composition)
- [Spring Framework — Java Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)