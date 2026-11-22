# Tổ hợp constraint và `@ReportAsSingleViolation` trong Jakarta Bean Validation

## 1. Mục tiêu và bối cảnh

Trong Spring Framework, một quy tắc nghiệp vụ thường có nhiều điều kiện cùng áp dụng cho một giá trị. Ví dụ, tên đăng nhập phải khác `null`/không trắng, dài từ 4 đến 12 ký tự, bắt đầu bằng chữ thường và chỉ chứa chữ thường, chữ số hoặc dấu gạch dưới. Có thể gắn trực tiếp `@NotBlank`, `@Size`, `@Pattern` trên từng trường; nhưng khi cùng một quy tắc xuất hiện ở nhiều DTO, tham số và model, việc lặp lại khiến cấu hình và thông điệp lỗi dễ thiếu nhất quán.

**Constraint composition** (tổ hợp ràng buộc) cho phép định nghĩa một annotation ràng buộc cấp cao từ các constraint có sẵn hoặc tự tạo. `@ReportAsSingleViolation` điều khiển **cách báo lỗi** của một constraint tổ hợp: nếu thành phần nào thất bại, kết quả có thể được báo bằng **một vi phạm của annotation cấp cao**, thay vì nhiều vi phạm của từng thành phần.

Hai mục đích cần tách biệt:

- **Tổ hợp:** tái sử dụng một bộ điều kiện và gom ý nghĩa nghiệp vụ dưới một tên, ví dụ `@SafeUsername`.
- **Báo một lỗi:** cung cấp một thông điệp tổng quát, ổn định cho người dùng hoặc API consumer bằng `@ReportAsSingleViolation`.

Phần trình bày sử dụng **Jakarta Validation** (package `jakarta.validation.*`), phù hợp với Spring Framework 6 / Spring Boot 3. Với dự án Spring 5 / Boot 2, API cũ mang package `javax.validation.*`; không trộn hai hệ import trong cùng ví dụ.

## 2. Cơ chế tổ hợp constraint

Một annotation tùy chỉnh trở thành constraint khi được khai báo với `@Constraint`. Để **chỉ tổ hợp** các constraint khác mà không có logic kiểm tra riêng, dùng `@Constraint(validatedBy = {})`. Đặt các annotation thành phần, như `@NotBlank`, `@Size`, `@Pattern`, **trên chính khai báo annotation** mới.

Mặc định, các thành phần có quan hệ logic **AND**: giá trị hợp lệ chỉ khi **tất cả** thành phần đều hợp lệ. Nếu có `ConstraintValidator` riêng ở annotation cấp cao, validator đó cũng tham gia kiểm tra. Các thành phần không bị thay thế bằng validator của annotation cấp cao.

Với một constraint tổ hợp thông thường, các thành phần thất bại có thể tạo ra **các `ConstraintViolation` riêng**. Chẳng hạn chuỗi rỗng vi phạm cả `@NotBlank`, `@Size(min = 4)` và mẫu `@Pattern` bắt buộc có chữ đầu tiên, nên có thể nhận ba lỗi trên cùng thuộc tính.

Với `@ReportAsSingleViolation` đặt **trên định nghĩa annotation tổ hợp**:

1. Điều kiện được chấp nhận vẫn là phép **AND** của các thành phần (trong Jakarta Validation chuẩn).
2. Khi một thành phần không hợp lệ, báo cáo lỗi riêng của các thành phần bị bỏ qua; một lỗi đại diện cho **constraint cấp cao** được trả về với `message()` của annotation cấp cao.
3. Theo đặc tả, quá trình đánh giá thành phần dừng khi gặp thất bại đầu tiên. **Không dựa vào thứ tự chạy** của thành phần để thực hiện side effect hay chọn thông điệp riêng.
4. Quy tắc “một lỗi” áp dụng cho **một lần khai báo constraint tổ hợp trên một vị trí**. Một bean có các trường khác lỗi hoặc cùng trường có constraint độc lập khác vẫn có thể trả về nhiều lỗi.

`@ReportAsSingleViolation` **không** làm cho dữ liệu sai thành đúng, không tự động biến tập điều kiện thành OR, và không phải annotation đặt trực tiếp lên field để gom các annotation rời rạc.

## 3. Ví dụ Java 17+: từ ba lỗi thành một lỗi

Ví dụ dưới đây chạy độc lập bằng Maven, Jakarta Validation API và Hibernate Validator 8. Tạo cấu trúc:

```text
constraint-composition-demo/
├── pom.xml
└── src/main/java/
    ├── SafeUsername.java
    └── Demo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>constraint-composition-demo</artifactId>
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
                <configuration>
                    <mainClass>Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` cung cấp implementation của Jakarta Validation; `jakarta.el` hỗ trợ cơ chế nội suy thông điệp mặc định. Ví dụ chọn các phiên bản tương thích với Java 17.

**`src/main/java/SafeUsername.java`**

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import jakarta.validation.ReportAsSingleViolation;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@NotBlank
@Size(min = 4, max = 12)
@Pattern(regexp = "[a-z][a-z0-9_]*")
@ReportAsSingleViolation
@Constraint(validatedBy = {})
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface SafeUsername {
    String message() default
        "Invalid username: use 4-12 chars, start with a-z, then a-z/0-9/_";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Ý nghĩa của từng phần:

- `@NotBlank` loại bỏ `null`, chuỗi rỗng và chuỗi chỉ có ký tự trắng.
- `@Size(min = 4, max = 12)` giới hạn độ dài. Với `CharSequence`, `@Size` tự nó chấp nhận `null`.
- `@Pattern(regexp = "[a-z][a-z0-9_]*")` yêu cầu ký tự đầu là `a-z`; phần còn lại là `a-z`, `0-9` hoặc `_`. `@Pattern` kiểm tra toàn chuỗi theo biểu thức chính quy và tự nó chấp nhận `null`.
- `@Constraint(validatedBy = {})` nghĩa là không viết một `ConstraintValidator` thừa để lặp lại ba điều kiện; các constraint thành phần thực hiện việc kiểm tra.
- `@Target` xác định vị trí sử dụng; `ANNOTATION_TYPE` cho phép constraint này lại được dùng để tổ hợp ở tầng khác. `@Retention(RUNTIME)` cần thiết để provider đọc annotation khi chạy.
- `message`, `groups` và `payload` là những thuộc tính theo hợp đồng khai báo constraint. `groups` cho phép chọn nhóm xác thực; `payload` dành cho metadata ứng dụng.

**`src/main/java/Demo.java`**

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.Set;

public class Demo {
    static final class Direct {
        @NotBlank
        @Size(min = 4, max = 12)
        @Pattern(regexp = "[a-z][a-z0-9_]*")
        String username;

        Direct(String username) {
            this.username = username;
        }
    }

    static final class Composed {
        @SafeUsername
        String username;

        Composed(String username) {
            this.username = username;
        }
    }

    public static void main(String[] args) {
        ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
        try {
            Validator validator = factory.getValidator();

            Set<ConstraintViolation<Direct>> direct =
                validator.validate(new Direct(""));
            Set<ConstraintViolation<Composed>> composed =
                validator.validate(new Composed(""));
            Set<ConstraintViolation<Composed>> valid =
                validator.validate(new Composed("alice_01"));

            System.out.println("Direct violations: " + direct.size());
            System.out.println("Composed violations: " + composed.size());
            System.out.println(
                "Message: " + composed.iterator().next().getMessage()
            );
            System.out.println("Valid violations: " + valid.size());
        } finally {
            factory.close();
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**stdout của chương trình** (không tính log của Maven/provider ghi ở luồng khác):

```text
Direct violations: 3
Composed violations: 1
Message: Invalid username: use 4-12 chars, start with a-z, then a-z/0-9/_
Valid violations: 0
```

`Direct` và `Composed` áp dụng **cùng ba điều kiện** lên chuỗi rỗng; chỉ **cách biểu diễn lỗi** khác nhau. Khi hợp lệ (`alice_01`), cả ba điều kiện đều qua và tập vi phạm rỗng. Trong ví dụ này, thông điệp của annotation cấp cao là chuỗi cố định nên kết quả hiển thị ổn định; với thông điệp lấy từ resource bundle, locale có thể thay đổi câu chữ.

### Một số đầu vào cần thử

| `username` | Lý do | `@SafeUsername` |
| --- | --- | --- |
| `""` | Trống, quá ngắn, sai biểu thức | 1 lỗi tổng hợp |
| `"abc"` | Dưới 4 ký tự | 1 lỗi tổng hợp |
| `"Abcd"` | Chữ đầu viết hoa | 1 lỗi tổng hợp |
| `"alice-01"` | Có dấu `-` ngoài tập cho phép | 1 lỗi tổng hợp |
| `"alice_01"` | Đúng độ dài và mẫu | 0 lỗi |
| `null` | Vi phạm `@NotBlank` | 1 lỗi tổng hợp |

Số lỗi của ví dụ không có `@ReportAsSingleViolation` tùy **số thành phần** thất bại; số lỗi của ví dụ có annotation này là **một trên mỗi lần áp dụng `@SafeUsername` thất bại**.

## 4. Tùy biến thuộc tính thành phần với `@OverridesAttribute`

Nếu mọi nơi đều bắt buộc độ dài 4–12, có thể giữ các tham số cố định như ví dụ. Nếu nhiều nơi dùng cùng cấu trúc tên nhưng yêu cầu độ dài khác nhau, cho phép người dùng annotation thay đổi giá trị của `@Size` qua `@OverridesAttribute`.

Trong **định nghĩa `@SafeUsername` ở ví dụ trên**, giữ `@Size(min = 4, max = 12)` và thêm import `jakarta.validation.OverridesAttribute` cùng hai phần tử dưới đây (đây là **đoạn bổ sung**, không phải file Java độc lập):

```java
@OverridesAttribute(constraint = Size.class, name = "min")
int min() default 4;

@OverridesAttribute(constraint = Size.class, name = "max")
int max() default 12;
```

Khi đó có thể sử dụng `@SafeUsername(min = 6, max = 20)`; giá trị `min`/`max` của annotation cấp cao sẽ ghi đè thuộc tính tương ứng trong `@Size`. Nếu muốn thông báo phản ánh số thực tế, sửa `message()`, chẳng hạn `"Username must have {min}-{max} characters and match the allowed pattern"`: cơ chế nội suy thông điệp thay `{min}` và `{max}` bằng thuộc tính của constraint cấp cao.

Cần nhớ:

- Tên thuộc tính và kiểu dữ liệu khi ghi đè phải tương thích; ví dụ `int` cho `Size.min`.
- Với nhiều thành phần cùng loại (chẳng hạn nhiều `@Pattern`), dùng `constraintIndex` để nhắm đúng khai báo khi cần; không giả định một thuộc tính sẽ tự ghi đè tất cả.
- `groups`, `payload` và `validationAppliesTo` của constraint thành phần không phải thông số tùy biến theo cách thông thường: giá trị/ngữ cảnh được kế thừa từ constraint cấp cao theo đặc tả.
- Nếu sửa điều kiện độ dài mà giữ thông điệp cố định “4–12”, kết quả sẽ gây hiểu lầm; đồng bộ thông điệp và logic.

## 5. Áp dụng trong Spring MVC

Với Spring Boot 3, dự án web thường thêm dependency `spring-boot-starter-validation`. Spring dùng Jakarta Validation provider để xác thực DTO khi một tham số `@RequestBody` được đánh dấu `@Valid`.

Ví dụ **chỉ minh họa phần tích hợp trong dự án Spring Boot có Spring Web và Validation starter**; dùng lại `SafeUsername.java` đã định nghĩa ở trên:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

class CreateUserRequest {
    @SafeUsername
    public String username;
}

@RestController
class UserController {
    @PostMapping("/users")
    ResponseEntity<String> create(@Valid @RequestBody CreateUserRequest request) {
        return ResponseEntity.ok(request.username);
    }
}
```

Khi client gửi `{"username": ""}`, xác thực `CreateUserRequest.username` thất bại. Với xử lý MVC mặc định, trường hợp `@Valid @RequestBody` không hợp lệ thường dẫn đến phản hồi HTTP 400 qua `MethodArgumentNotValidException` (nếu ứng dụng có handler riêng thì cấu trúc phản hồi có thể khác). Thông điệp của `@SafeUsername` có thể xuất hiện như **một field error** cho constraint này, giúp API trả mã và nội dung lỗi nhất quán hơn.

Đối với xác thực tham số phương thức controller hoặc service, cách kích hoạt method validation phụ thuộc phiên bản Spring và cấu hình (chẳng hạn `@Validated` ở một số kịch bản). Đừng nhầm `@ReportAsSingleViolation` với cơ chế kích hoạt validation: nó **chỉ quyết định cách báo lỗi của constraint tổ hợp sau khi validation được thực thi**.

Với các quy tắc đầu vào quan trọng, cần nhớ Bean Validation chỉ là một lớp kiểm tra dữ liệu. Hệ thống vẫn phải kiểm tra điều kiện nghiệp vụ ở đúng ranh giới xử lý và bảo vệ tính nhất quán dữ liệu ở tầng lưu trữ nếu cần.

## 6. Các lựa chọn thiết kế và lỗi thường gặp

### Khi nào nên tổ hợp, khi nào nên tạo validator riêng?

**Nên tổ hợp** khi quy tắc hoàn toàn diễn đạt được bằng các constraint có sẵn và được tái sử dụng: mã bưu chính, mã sản phẩm, username, tổ hợp định dạng và giới hạn độ dài. **Viết `ConstraintValidator` riêng** khi quy tắc cần thuật toán hoặc trạng thái khác mà các thành phần không diễn đạt được (ví dụ điều kiện phụ thuộc nhiều trường hoặc luật kiểm tra nghiệp vụ phức tạp). Có thể dùng cả validator riêng lẫn các constraint thành phần trong cùng annotation nếu cần; mặc định chúng cùng tham gia theo AND.

### Các hiểu nhầm cần tránh

1. **Đặt `@ReportAsSingleViolation` trên field:** không đúng đích dùng; nó được khai báo trên **annotation constraint tổ hợp** (meta-annotation có target `ANNOTATION_TYPE`).
2. **Cho rằng annotation này thực hiện phép OR:** trong chuẩn Jakarta Validation, composition là **AND**. Hibernate Validator có mở rộng riêng `@ConstraintComposition` cho OR/NOT; phụ thuộc mở rộng đó làm code kém portable sang provider khác.
3. **Quên `@Constraint(validatedBy = {})`:** một annotation được ghép bởi các annotation khác vẫn cần khai báo là constraint; mảng rỗng cho biết không có validator bổ sung.
4. **Quên `@Retention(RUNTIME)`, `@Target` hoặc ba thuộc tính bắt buộc:** có thể gây lỗi khai báo, lỗi biên dịch hoặc provider không nhận diện đúng.
5. **Tổ hợp constraint không hỗ trợ cùng kiểu dữ liệu:** `@Pattern` phù hợp `CharSequence`, không áp dụng tùy ý lên `Integer`; các thành phần và constraint cấp cao phải có kiểu đích tương thích.
6. **Nghĩ `@Size` hoặc `@Pattern` tự cấm `null`:** các constraint này thường coi `null` là hợp lệ; thêm `@NotNull` hoặc `@NotBlank` theo ý nghĩa cần kiểm tra.
7. **Mong đúng một lỗi trên toàn bộ object:** chỉ gom các lỗi thuộc **một constraint tổ hợp**. Các field khác, phần tử danh sách khác, hoặc constraint độc lập khác vẫn có thể sinh lỗi.
8. **Phụ thuộc vào thứ tự duyệt `ConstraintViolation`:** giá trị trả về là `Set`; thứ tự thông điệp không được đảm bảo. Khi đã dùng `@ReportAsSingleViolation`, hãy trình bày thông điệp cấp cao thay vì dựa vào “lỗi con đầu tiên”.
9. **Lẫn `javax.validation` và `jakarta.validation`:** chọn hệ API phù hợp với thế hệ Spring; tránh dependency trùng và import sai.
10. **Dùng thông điệp tổng quát khi API cần hướng dẫn khắc phục chi tiết:** báo một lỗi giúp ngắn gọn nhưng che thông tin về thành phần nào thất bại. Với form nhập liệu cần hướng dẫn theo từng điều kiện, có thể **không** dùng `@ReportAsSingleViolation`, hoặc tạo cơ chế trả mã lỗi/phần hướng dẫn phù hợp ở tầng API.

### Checklist khi xây constraint tổ hợp

- Mỗi điều kiện thành phần có thật sự thuộc cùng một quy tắc nghiệp vụ, và kiểu dữ liệu được hỗ trợ có nhất quán không?
- Mặc định AND có đáp ứng bài toán không?
- Muốn trả từng lỗi thành phần để sửa input hay một lỗi nghiệp vụ tổng hợp?
- `message` có chính xác khi cấu hình thuộc tính được ghi đè bằng `@OverridesAttribute` không?
- Có thử dữ liệu hợp lệ, `null`, rỗng, quá ngắn, quá dài và ký tự sai mẫu chưa?
- Có thử trên DTO/parameter và đúng phiên bản Spring/Jakarta Validation của dự án chưa?

## 7. Kết luận thực hành

Với nhu cầu “một bộ điều kiện có ý nghĩa nghiệp vụ, được dùng lặp lại”, hãy định nghĩa một constraint tổ hợp rồi gắn trực tiếp vào field/parameter. Mặc định hệ thống kiểm tra **tất cả điều kiện theo AND** và có thể hiển thị nhiều lỗi thành phần. Khi chỉ muốn người dùng/API nhìn thấy **một lỗi cấp cao cho một constraint tổ hợp**, đặt `@ReportAsSingleViolation` trên định nghĩa annotation, viết `message` rõ ràng và kiểm thử cả số lỗi lẫn thông điệp.

Tài liệu tham khảo:

- [Jakarta Bean Validation specification – Constraint composition](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation API – ReportAsSingleViolation](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ReportAsSingleViolation.html)
- [Hibernate Validator Reference Guide – Constraint composition](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
