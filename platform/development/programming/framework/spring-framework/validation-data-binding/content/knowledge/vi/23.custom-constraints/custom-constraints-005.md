# Quy định hành vi khi giá trị được kiểm tra là `null` trong ràng buộc tùy chỉnh

## 1. Bối cảnh và nguyên tắc

Trong Spring Framework, một cách phổ biến để kiểm tra dữ liệu đầu vào là dùng Jakarta Bean Validation với `@Valid`, `@Validated` và các annotation như `@NotNull`, `@Pattern` hoặc constraint tự định nghĩa. Với constraint tùy chỉnh, logic nằm ở `ConstraintValidator<A, T>#isValid(T value, ConstraintValidatorContext context)`.

**Một constraint tùy chỉnh không tự động bỏ qua `null`.** Chính phương thức `isValid` quyết định trả về `true` (hợp lệ) hay `false` (không hợp lệ) khi giá trị bằng `null`. Theo khuyến nghị của Jakarta Bean Validation, các constraint kiểm tra *nội dung/định dạng khi giá trị có mặt* thường nên chấp nhận `null`; yêu cầu *bắt buộc phải có giá trị* nên được khai báo riêng bằng `@NotNull`.

Ví dụ: mã sản phẩm phải theo mẫu `ABC-1234`, nhưng chỉ khi người dùng cung cấp mã. Hai yêu cầu độc lập là:

- **Định dạng:** `@Sku` xác nhận mã đã nhập đúng mẫu và trả `true` khi `null`.
- **Tính bắt buộc:** `@NotNull` ngăn mã bị `null`. Ghép `@NotNull @Sku` nếu vừa cần có mã vừa cần đúng định dạng.

Quy tắc này giúp một `@Sku` dùng lại được cho cả trường tùy chọn và trường bắt buộc; thông báo lỗi cũng phản ánh đúng vấn đề là *thiếu dữ liệu* hay *sai định dạng*.

## 2. Phân biệt `null`, rỗng và sai định dạng

`null` là không có tham chiếu đến giá trị. Nó khác chuỗi rỗng `""` và chuỗi chỉ chứa khoảng trắng `"   "`. Bean Validation không mặc nhiên coi ba trạng thái này là một.

| Constraint | `null` | `""` | `"   "` | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `@NotNull` | Không hợp lệ | Hợp lệ | Hợp lệ | Chỉ cấm `null` |
| `@NotEmpty` (chuỗi) | Không hợp lệ | Không hợp lệ | Hợp lệ | Cấm `null` và chuỗi dài 0 |
| `@NotBlank` (chuỗi) | Không hợp lệ | Không hợp lệ | Không hợp lệ | Cần ít nhất một ký tự không phải khoảng trắng |
| `@Size`, `@Pattern` | Hợp lệ | Tùy điều kiện | Tùy điều kiện | Kiểm tra giá trị có mặt, không tự yêu cầu sự hiện diện |
| `@Sku` trong ví dụ | Hợp lệ | Không hợp lệ | Không hợp lệ | Mã tùy chọn, nhưng nếu nhập thì phải đúng mẫu |
| `@Null` | Hợp lệ | Không hợp lệ | Không hợp lệ | Chỉ chấp nhận `null` |

Đối với cùng một trường, `@NotNull @Sku` sẽ từ chối `null` bằng `@NotNull`; `@Sku` vẫn có thể trả `true` cho `null` mà không làm vô hiệu constraint còn lại. Khi nhiều constraint cùng thất bại, hệ thống có thể trả nhiều violation; không nên dựa vào thứ tự trả về của `Set<ConstraintViolation<?>>`.

## 3. Thiết kế chính sách `null` cho constraint riêng

**Chính sách A — trường có thể thiếu, nhưng nếu có phải hợp lệ (khuyến nghị cho constraint định dạng):**

```java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    if (value == null) {
        return true; // Tính bắt buộc do @NotNull quyết định
    }
    return value.matches("[A-Z]{3}-[0-9]{4}");
}
```

**Chính sách B — trường bắt buộc:** giữ nguyên validator ở chính sách A rồi đặt `@NotNull @Sku` lên trường. Cách này biểu đạt hai quy tắc riêng và tái sử dụng validator được.

**Chính sách C — chính constraint phải cấm `null` theo hợp đồng đặc thù:** có thể trả `false` với `null`, nhưng phải mô tả rõ trong tài liệu annotation và kiểm thử. Không làm điều này chỉ vì quên xử lý `null`; nếu vấn đề là "bắt buộc nhập", `@NotNull` thường rõ ràng hơn.

Không gọi `value.length()`, `value.matches(...)` hay dereference các trường con trước khi xử lý `null`. `NullPointerException` trong `isValid` không phải là một violation hợp lệ do `false` tạo ra; nó khiến quá trình validation gặp ngoại lệ. Validator cũng không được tự thay đổi giá trị đầu vào và cần an toàn khi được dùng đồng thời.

## 4. Ví dụ Java 17 chạy được với Jakarta Bean Validation

Ví dụ sau có hai trường: `requiredSku` bắt buộc, `optionalSku` tùy chọn. Chúng dùng cùng một constraint `@Sku`.

Tạo dự án Maven thông thường, Java 17+, với cấu trúc:

```text
pom.xml
src/main/java/demo/validation/Sku.java
src/main/java/demo/validation/SkuValidator.java
src/main/java/demo/validation/ProductForm.java
src/main/java/demo/validation/NullPolicyDemo.java
```

**`pom.xml`** — dùng Jakarta Bean Validation 3.x và Hibernate Validator 8.x làm provider (trong dự án Spring Boot 3.x đã có `spring-boot-starter-validation`, thường không cần khai báo trực tiếp các dependency mẫu này).

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>null-validation-policy</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
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
      </plugin>
    </plugins>
  </build>
</project>
```

**`Sku.java`** — khai báo constraint chuẩn. `message`, `groups` và `payload` là các phần bắt buộc của annotation constraint.

```java
package demo.validation;

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
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SkuValidator.class)
public @interface Sku {
    String message() default "must match AAA-1234";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

**`SkuValidator.java`** — kiểm tra định dạng, đồng thời cho phép `null`.

```java
package demo.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SkuValidator implements ConstraintValidator<Sku, String> {
    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }
        return value.matches("[A-Z]{3}-[0-9]{4}");
    }
}
```

**`ProductForm.java`** — quy định tính bắt buộc tại nơi sử dụng constraint.

```java
package demo.validation;

import jakarta.validation.constraints.NotNull;

public final class ProductForm {
    @NotNull
    @Sku
    private final String requiredSku;

    @Sku
    private final String optionalSku;

    public ProductForm(String requiredSku, String optionalSku) {
        this.requiredSku = requiredSku;
        this.optionalSku = optionalSku;
    }
}
```

**`NullPolicyDemo.java`** — chạy một ma trận đầu vào. Để stdout xác định, chương trình in tên annotation gây lỗi thay cho thông báo đã được bản địa hóa, rồi sắp xếp các lỗi.

```java
package demo.validation;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.util.List;

public final class NullPolicyDemo {
    private static void check(Validator validator, String caseName, ProductForm form) {
        List<String> errors = validator.validate(form).stream()
            .map(v -> v.getPropertyPath() + ":" +
                v.getConstraintDescriptor().getAnnotation()
                    .annotationType().getSimpleName())
            .sorted()
            .toList();

        System.out.println(caseName + " => " +
            (errors.isEmpty() ? "OK" : String.join(", ", errors)));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            check(validator, "null/null", new ProductForm(null, null));
            check(validator, "valid/null", new ProductForm("ABC-1234", null));
            check(validator, "bad/null", new ProductForm("abc-1234", null));
            check(validator, "valid/empty", new ProductForm("ABC-1234", ""));
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.validation.NullPolicyDemo
```

Stdout dự kiến (bỏ qua log Maven/provider nếu môi trường có cấu hình log riêng):

```text
null/null => requiredSku:NotNull
valid/null => OK
bad/null => requiredSku:Sku
valid/empty => optionalSku:Sku
```

**Vì sao:** trường `requiredSku = null` chỉ vi phạm `@NotNull`; `@Sku` chấp nhận `null`. Trường `optionalSku = null` hợp lệ. Khi `optionalSku = ""`, nó có mặt nhưng sai định dạng nên `@Sku` từ chối. Khi `requiredSku = "abc-1234"`, mã sai vì yêu cầu ba chữ hoa và bốn chữ số.

## 5. Áp dụng trong Spring MVC và data binding

Trong ứng dụng Spring MVC có Bean Validation provider (ví dụ dependency `spring-boot-starter-validation`), có thể khai báo DTO như sau. Đây là **đoạn mã tích hợp** vào một controller đã được cấu hình, không phải một chương trình Java chạy độc lập:

```java
public record CreateProductRequest(
    @NotNull @Sku String requiredSku,
    @Sku String optionalSku
) {}

@PostMapping("/products")
public ResponseEntity<Void> create(@Valid @RequestBody CreateProductRequest body) {
    // Chỉ xử lý khi các ràng buộc áp dụng cho body đã hợp lệ.
    return ResponseEntity.noContent().build();
}
```

Ở đây `@Valid` yêu cầu Spring kiểm tra các constraint của DTO sau khi đối tượng đã được tạo/bind thành công. Với JSON như `{"requiredSku":null,"optionalSku":null}`, `requiredSku` vi phạm `@NotNull`. Với `{"requiredSku":"ABC-1234","optionalSku":null}`, cả hai trường đều hợp lệ theo hai constraint trên.

Cần phân biệt các tầng xử lý:

1. **Đọc dữ liệu và chuyển kiểu/binding:** JSON sai cú pháp, không tạo được object hoặc chuyển chuỗi thành kiểu số thất bại có thể bị từ chối **trước khi** `ConstraintValidator` chạy. Một trường JSON bị thiếu có thể được ánh xạ thành `null` cho thuộc tính kiểu tham chiếu, nhưng kết quả cụ thể còn tùy cấu hình Jackson/constructor/default value.
2. **Bean Validation:** sau khi có DTO, `@Valid` kiểm tra các trường; `@NotNull` kiểm tra sự hiện diện, `@Sku` kiểm tra định dạng khi giá trị có mặt.
3. **Xử lý lỗi HTTP:** Spring MVC thường chuyển lỗi validation của `@Valid @RequestBody` thành phản hồi lỗi phía client khi không có `BindingResult`/handler tùy chỉnh. Cấu trúc response phụ thuộc cấu hình xử lý ngoại lệ của ứng dụng.

Đừng nhầm `@RequestBody(required = true)` với `@NotNull` trên *một thuộc tính*. `required = true` chủ yếu liên quan đến sự hiện diện của toàn bộ request body, không thay cho constraint bắt buộc của từng field.

### Liên hệ với `@Valid` trên object lồng nhau

`@Valid` chỉ yêu cầu kiểm tra lồng sâu khi object được tham chiếu tồn tại. Nếu object con bằng `null`, cascading validation bỏ qua nó. Khi một object con là bắt buộc, đặt cả hai:

```java
@NotNull
@Valid
private Address shippingAddress;
```

Tương tự, `@Valid` **không tự cấm `null`**. Việc một constraint tùy chỉnh cho `null` qua không đồng nghĩa Spring đã bỏ qua mọi kiểm tra trên field ấy: các constraint khác vẫn được đánh giá theo quy tắc của chúng.

### Nếu dùng `org.springframework.validation.Validator` thủ công

Spring còn có giao diện `Validator` riêng với `supports(Class<?>)` và `validate(Object target, Errors errors)`. Đây **không phải** `jakarta.validation.ConstraintValidator` và không có hợp đồng `isValid(value, context)` giống trên. Khi tự viết một Spring `Validator`, phải chủ động quyết định cách xử lý thuộc tính `null` và ghi lỗi bằng `errors.rejectValue(...)` hoặc các helper thích hợp; đừng giả định quy tắc `null` của Bean Validation sẽ tự áp dụng cho logic tự viết. Khi dự án đã tích hợp Jakarta Bean Validation, nên dùng annotation constraint riêng cho quy tắc định dạng tái sử dụng.

## 6. Trường hợp cần quyết định rõ chính sách

| Yêu cầu nghiệp vụ | Cách biểu diễn | Hành vi với `null` |
| --- | --- | --- |
| Mã khuyến mãi tùy chọn; nếu nhập phải đúng định dạng | `@Sku` | Hợp lệ |
| Mã sản phẩm bắt buộc và đúng định dạng | `@NotNull @Sku` | Không hợp lệ bởi `@NotNull` |
| Tên bắt buộc, không cho chỉ khoảng trắng | `@NotBlank` | Không hợp lệ |
| Trường phải luôn vắng mặt ở một bước xử lý | `@Null` | Hợp lệ |
| Object lồng nhau bắt buộc và cần kiểm tra các field con | `@NotNull @Valid` | Không hợp lệ bởi `@NotNull` |
| Giá trị tùy chọn nhưng chuỗi rỗng cần được hiểu là "không nhập" | Chuẩn hóa đầu vào rõ ràng theo hợp đồng API, hoặc thiết kế policy validator riêng | Không được mặc định coi `""` là `null` |

**Lưu ý về nhóm validation:** `@Validated(SomeGroup.class)` chọn nhóm constraint cần chạy; nó không sửa ý nghĩa `null` của từng constraint. Một `@NotNull` bị đặt vào nhóm không được kích hoạt sẽ không bảo vệ giá trị trong lượt kiểm tra đó.

## 7. Kiểm thử và lỗi thường gặp

Khi thiết kế một constraint mới, tối thiểu hãy kiểm thử `null`, chuỗi rỗng, chỉ khoảng trắng, dữ liệu sai định dạng, dữ liệu hợp lệ và tổ hợp với `@NotNull`. Với class-level validator, cũng kiểm thử object gốc bằng `null` nếu API gọi `isValid` trực tiếp; với `@Valid` lồng nhau thì phân biệt việc cascade bị bỏ qua khi tham chiếu con là `null`.

Những lỗi đáng tránh:

- **Dereference trước khi kiểm tra `null`:** `value.trim()`, `value.length()` hoặc truy cập field con gây `NullPointerException`. Hãy đặt nhánh `null` ở đầu `isValid`.
- **Cho mọi chuỗi trống đi qua chỉ vì cho `null` đi qua:** `null`, `""` và `" "` có ý nghĩa khác nhau; chính sách với từng trạng thái cần được quy định.
- **Nhét tính bắt buộc vào mọi constraint định dạng:** giảm khả năng tái sử dụng, có thể tạo thông báo lỗi khó hiểu. Dùng `@NotNull` hoặc `@NotBlank` khi chúng diễn đạt đúng yêu cầu.
- **Cho rằng `@Valid` đồng nghĩa với `@NotNull`:** annotation này kích hoạt validation/cascade ở ngữ cảnh tương ứng, không phải phép kiểm tra hiện diện.
- **Cho rằng Spring luôn gọi validator:** phải có provider, điểm kích hoạt validation thích hợp (`@Valid`, `@Validated`, `Validator#validate` hoặc cấu hình tương ứng) và dữ liệu phải qua bước binding.
- **Bỏ qua việc kiểm thử nhóm/đường xử lý lỗi:** constraint có thể không thuộc nhóm đang chạy; response thực tế cũng phụ thuộc cấu hình Spring.

**Quy tắc ghi nhớ:** Constraint kiểm tra *giá trị trông như thế nào* thường `return true` với `null`; constraint kiểm tra *giá trị có bắt buộc tồn tại hay không* phải được khai báo rõ. Hãy thiết kế hai quyết định độc lập và kiểm thử cả hai.

## Tham khảo

- Jakarta Bean Validation Specification — phần triển khai `ConstraintValidator` và khuyến nghị tách xử lý `null` khỏi constraint nội dung: https://beanvalidation.org/2.0/spec/
- Hibernate Validator Reference Guide — creating custom constraints, `isValid` và cascade validation: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework Reference — Java Bean Validation, Spring `Validator` và `DataBinder`: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC Reference — validation trên controller method: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html