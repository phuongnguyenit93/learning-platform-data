# Định nghĩa annotation với @Constraint trong Jakarta Validation và Spring Framework

> **Module:** Spring Framework – validation-data-binding  
> **Nhóm kiến thức:** Ràng buộc tùy chỉnh (custom constraints)  
> **Trọng tâm:** Tự định nghĩa một Java annotation được Jakarta Validation nhận diện qua `@Constraint`, liên kết validator, thiết kế các phần tử `message`/`groups`/`payload`, phạm vi áp dụng, tái sử dụng và tích hợp Spring.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Giải thích tại sao `@Constraint` là metadata cốt lõi khiến một annotation trở thành **Jakarta Validation constraint** thay vì một Java annotation trang trí.
2. Viết annotation với `@Target`, `@Retention(RUNTIME)`, `@Documented`, `@Constraint(validatedBy=...)`, và ba phần tử **bắt buộc** `message()`, `groups()`, `payload()` đúng kiểu dữ liệu.
3. Phân biệt **constraint declaration** (annotation gắn lên dữ liệu), **constraint definition** (định nghĩa annotation + validator), **constraint validator** (logic) và **validation provider** (bộ máy thực thi).
4. Thiết kế các thuộc tính cấu hình như `prefix`, `digits` mà không lẫn chúng với các phần tử dành riêng của đặc tả.
5. Gắn annotation lên field, getter, tham số, class hoặc phần tử container **chỉ khi `@Target` và kiểu validator cho phép**.
6. Tạo một custom annotation + `ConstraintValidator` chạy được với Java 17, Maven và Hibernate Validator; kiểm tra null, đầu vào sai và thông báo lỗi.
7. Hiểu constraint composition, `@ReportAsSingleViolation`, repeatable constraints, groups, payload, message interpolation và metadata API.
8. Tích hợp custom constraint vào Spring MVC/Boot, xử lý injection hợp lệ và phân biệt lỗi cấu hình với lỗi dữ liệu.
9. Nhận biết thời điểm nên viết custom constraint thay vì dùng built-in constraints hoặc logic nghiệp vụ trong service.

## 2. `@Constraint` nằm ở đâu trong kiến trúc?

Jakarta Validation là **đặc tả API**: ứng dụng đặt constraint lên dữ liệu rồi yêu cầu `Validator` kiểm tra. Hibernate Validator là một **implementation/provider** phổ biến. Spring Framework tích hợp provider vào những điểm như `@Valid @RequestBody`, `@Validated`, `LocalValidatorFactoryBean` hoặc method validation.

Một custom constraint thường gồm các thành phần sau:

~~~text
   ĐỊNH NGHĨA ANNOTATION (Java)
   @Constraint(validatedBy = SkuCodeValidator.class)
   @Target(...)
   @Retention(RUNTIME)
   public @interface SkuCode { message/groups/payload/... }
                 |
                 | được sử dụng
                 v
   @SkuCode(prefix="SKU", digits=3)
   private String sku;                   [constraint declaration]
                 |
                 | Validator.validate(bean)
                 v
   Jakarta Validation provider
     - đọc metadata annotation và groups
     - chọn ConstraintValidator tương thích kiểu String
     - gọi initialize(annotation), isValid(value, context)
                 |
        +--------+---------+
        |                  |
      true                false
    hợp lệ          ConstraintViolation
                     propertyPath/message/descriptor...
~~~

**Chỉ có `@Constraint` là chưa đủ để validation tự chạy.** Cần provider và điểm kích hoạt validation. Gọi `new Product("bad")` hoặc setter bình thường không tự tạo lỗi chỉ vì field có annotation.

Một Java annotation như sau **chưa phải Jakarta Validation constraint**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface SkuHint {
    String format() default "SKU-###";
}
~~~

Nó có thể được đọc bằng reflection, nhưng provider Jakarta Validation **không coi nó là constraint**, vì không có `@Constraint` và hợp đồng phần tử cần thiết. Đừng dùng tên bắt đầu bằng `Valid...` rồi mặc định framework sẽ nhận ra.

## 3. Cấu trúc tối thiểu của một custom constraint annotation

Ví dụ annotation kiểm tra chuỗi mã sản phẩm có dạng cố định:

~~~java
package example.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = SkuCodeValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface SkuCode {

    String message() default "{example.validation.SkuCode.message}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    String prefix() default "SKU";

    int digits() default 3;
}
~~~

Đây chính là một **source file thực tế** của dự án mẫu ở mục 8; cần có class `SkuCodeValidator` và dependency Jakarta Validation phù hợp để biên dịch. Điểm đáng chú ý:

- `public @interface SkuCode` khai báo **kiểu annotation** trong Java.
- `@Constraint(validatedBy = SkuCodeValidator.class)` công bố đây là custom Jakarta constraint và nêu implementation.
- `@Retention(RUNTIME)` giữ metadata khi chương trình chạy, để provider đọc được.
- `@Target(...)` quy định annotation được phép gắn ở đâu.
- `@Documented` khiến annotation xuất hiện trong Javadoc; hữu ích nhưng không quyết định logic validation.
- `message()`, `groups()`, `payload()` là các phần tử chuẩn bắt buộc với kiểu/default đúng quy định.
- `prefix()` và `digits()` là thuộc tính **tự định nghĩa**, được đọc từ annotation khi validator khởi tạo.

### 3.1. Tại sao bắt buộc là `@Retention(RUNTIME)`?

Java hỗ trợ `SOURCE`, `CLASS` và `RUNTIME`:

| Retention | Metadata tồn tại tới đâu? | Có phù hợp custom Jakarta constraint? |
| --- | --- | --- |
| `SOURCE` | Chỉ ở mã nguồn/biên dịch | Không |
| `CLASS` | Trong class file nhưng không phải annotation runtime thông thường | Không |
| `RUNTIME` | Có thể đọc khi chạy | **Có – bắt buộc** |

Một constraint thiếu retention phù hợp có thể không được provider nhận diện. Theo đặc tả, annotation định nghĩa constraint phải có `RUNTIME` và `@Constraint`. Đừng cho rằng chỉ thêm `@Constraint` nhưng bỏ `@Retention` là đủ.

### 3.2. `@Constraint(validatedBy = ...)` là liên kết implementation

`validatedBy` nhận **mảng các lớp** triển khai `jakarta.validation.ConstraintValidator`:

~~~java
@Constraint(validatedBy = SkuCodeValidator.class)
~~~

hoặc:

~~~java
@Constraint(validatedBy = {
        StringCodeValidator.class,
        CharSequenceCodeValidator.class
})
~~~

Đoạn thứ hai chỉ minh họa cú pháp, **không phải yêu cầu tự thêm hai class có cùng chức năng**. Nếu có nhiều validator, provider tìm implementation phù hợp nhất với kiểu dữ liệu, theo quy tắc type resolution của đặc tả. Định nghĩa trùng lặp/không thể phân giải có thể gây validation exception; không đăng ký nhiều validator chỉ để “thử cả hai theo thứ tự”.

`@Constraint(validatedBy = {})` cũng hợp lệ trong **composed constraint** chỉ kết hợp các constraint khác; xem mục 11. Nó **không** có nghĩa custom annotation với logic riêng sẽ được provider tự đoán cách kiểm tra.

### 3.3. Ba phần tử bắt buộc: chính xác tên, kiểu và giá trị mặc định

| Phần tử | Chữ ký yêu cầu | Vai trò |
| --- | --- | --- |
| `message` | `String message() default "...";` | Mẫu thông báo khi vi phạm |
| `groups` | `Class<?>[] groups() default {};` | Tập validation group |
| `payload` | `Class<? extends Payload>[] payload() default {};` | Metadata mở rộng kèm constraint |

**Tên là cố định** và mặc định của `groups`/`payload` phải là mảng rỗng. Đây là một **hợp đồng của đặc tả**, không phải gợi ý style.

Ví dụ sai:

~~~java
public @interface BadConstraint {
    String error();              // không thay thế được message()
    Class<?> groups();           // sai kiểu: phải là Class<?>[]
    String[] payload() default {}; // sai kiểu payload
}
~~~

Đoạn trên là **minh họa lỗi thiết kế**, không phải custom constraint đúng. Khi một annotation gắn `@Constraint` nhưng có định nghĩa phần tử bắt buộc không hợp lệ, provider có thể báo `ConstraintDefinitionException` khi truy cập metadata hoặc validate.

Tên `message`, `groups`, `payload` và `validationAppliesTo` có vai trò dành riêng. Ngoài ra, đặc tả không cho phép tên thuộc tính custom **bắt đầu bằng `valid`**; tránh `validValue()` hoặc `validDigits()`. Dùng `prefix()`, `digits()`, `minLength()`... để diễn đạt cấu hình của constraint.

## 4. Chọn `@Target` theo nơi dữ liệu được kiểm tra

`java.lang.annotation.Target` giới hạn vị trí hợp lệ theo ngôn ngữ Java. Không có một danh sách target bắt buộc cho mọi custom constraint; phải chọn dựa vào use case.

| `ElementType` | Vị trí được phép | Ví dụ |
| --- | --- | --- |
| `FIELD` | Field trong class/record backing field | `@SkuCode private String sku;` |
| `METHOD` | Getter hoặc method return value | `@SkuCode public String getSku()` |
| `PARAMETER` | Tham số method/constructor | `void save(@SkuCode String sku)` |
| `TYPE` | Định nghĩa class/interface/record | `@ValidDateRange class Booking { ... }` |
| `ANNOTATION_TYPE` | Annotation khác | Cho phép **constraint composition** |
| `TYPE_USE` | Vị trí dùng một kiểu, đặc biệt generic container element | `List<@SkuCode String> codes` |
| `CONSTRUCTOR` | Khai báo constructor/return value thích hợp | Constraint áp dụng cho constructor khi use case yêu cầu |

Các annotation có thể được gắn trên property, class hoặc cross-parameter tuỳ kiểu target và validator. **`@Target(TYPE)` không phải là `@Target(TYPE_USE)`**: một constraint cấp class đánh giá toàn bean, còn constraint ở type argument đánh giá mỗi phần tử của container (khi provider có value extractor).

### 4.1. Nếu áp annotation lên getter

~~~java
public class Product {
    private String sku;

    @SkuCode
    public String getSku() {
        return sku;
    }
}
~~~

Đây là **class minh họa** dùng annotation đã định nghĩa. Provider có thể xem annotation trên getter như property constraint. Không vô tình đặt cùng một constraint ở cả field lẫn getter của cùng property vì có thể dẫn đến kiểm tra/violation trùng lặp.

### 4.2. Nếu áp lên class

Một rule cần so sánh hai field, ví dụ `startDate <= endDate`, phải nhận được object chứa cả hai thuộc tính:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface DateRange {
    String message() default "{example.validation.DateRange.message}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là **mảnh khai báo minh họa**, cần các import và class `DateRangeValidator` phù hợp. Validator dạng `ConstraintValidator<DateRange, Booking>` có thể đánh giá cả start/end. Không gắn kiểu constraint này vào `String` rồi kỳ vọng tự kiểm tra quan hệ giữa hai field khác nhau.

### 4.3. Nếu áp lên phần tử danh sách

~~~java
import java.util.List;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class ProductBatch {
    @NotEmpty
    private List<@NotNull @SkuCode String> skus;
}
~~~

Đây là **model fragment**. Các tầng có trách nhiệm riêng:

- `@NotEmpty` ngoài list: danh sách không null/rỗng.
- `@NotNull` trong dấu `<...>`: mỗi phần tử không được null.
- `@SkuCode` trong dấu `<...>`: mỗi phần tử chuỗi phải đúng định dạng.
- Nếu chỉ dùng `@SkuCode` và validator thiết kế cho phép null, một phần tử null được coi là hợp lệ đối với riêng constraint này.

`@Target(TYPE_USE)` làm cú pháp Java cho phép annotation ở vị trí đó; việc chạy được còn phụ thuộc provider có **`ValueExtractor`** phù hợp với container. `List` là container tiêu chuẩn được Hibernate Validator hỗ trợ.

## 5. Thuộc tính custom: thiết kế API annotation trước khi viết validator

Constraint annotation là một **API được người khác dùng trực tiếp**. Các thuộc tính cấu hình nên:

- Mang tên mô tả rõ ràng, ví dụ `prefix`, `digits` thay vì `value1`, `flag`.
- Có mặc định hợp lý nếu phần lớn trường hợp cùng quy tắc.
- Dùng kiểu annotation element mà Java hỗ trợ: primitive, `String`, `Class`, enum, annotation hoặc mảng các kiểu này.
- Không dùng giá trị runtime động như `Clock`, `Service` hay `Pattern` làm phần tử annotation: Java không cho annotation element có kiểu object tùy ý.
- Có tài liệu về null, empty, whitespace, case sensitivity và format.
- Không chứa dữ liệu nhạy cảm hay giá trị chỉ biết khi request đến.

Ví dụ:

~~~java
@SkuCode(prefix = "SKU", digits = 3)
private String primarySku;

@SkuCode(prefix = "PART", digits = 5)
private String partNumber;
~~~

Cả hai chỗ dùng cùng **định nghĩa annotation** và validator nhưng có cấu hình riêng. Trong validator, dùng `initialize(SkuCode annotation)` để đọc cấu hình và chuẩn bị regex.

Trong Java, các annotation attribute là metadata gần như bất biến tại runtime; nếu muốn ràng buộc phụ thuộc ngày giờ hiện tại, kho hàng hay database, không thể đưa một service instance vào thuộc tính annotation. Hãy dùng `ConstraintValidator` với dependency injection thích hợp hoặc chuyển logic sang service/domain layer.

### 5.1. Phân biệt `value()` và `message()`

Java cho phép annotation có phần tử tên `value` để dùng cú pháp rút gọn:

~~~java
public @interface AllowedPrefix {
    String value();
}
~~~

~~~java
@AllowedPrefix("SKU")
private String code;
~~~

Ví dụ này **chỉ minh họa cú pháp Java**; nó chưa phải Jakarta constraint vì chưa có `@Constraint` và hợp đồng bắt buộc. `value()` là tên thuộc tính thông thường, còn `message()` là phần tử Jakarta Validation dùng làm thông báo lỗi. Không đổi tên `message()` thành `value()`.

## 6. Thiết kế `ConstraintValidator` tương ứng với annotation

Với `@SkuCode` gắn lên `String`, implementation phải tương thích:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class SkuCodeValidator
        implements ConstraintValidator<SkuCode, String> {
    // initialize(...) và isValid(...)
}
~~~

- Tham số generic thứ nhất là **kiểu annotation** `SkuCode`.
- Tham số thứ hai là **kiểu dữ liệu được validate**, ở đây `String`.
- `initialize(SkuCode annotation)` đọc các thuộc tính cấu hình cho từng descriptor annotation.
- `isValid(String value, ConstraintValidatorContext context)` trả `true` nếu đạt; `false` nếu không đạt.
- Thông báo mặc định lấy từ phần tử `message()` của annotation, được provider nội suy nếu có lỗi.

Thông thường nên để custom validator chỉ kiểm tra **định dạng** coi null là hợp lệ, và dùng `@NotNull` hoặc `@NotBlank` bên ngoài khi field bắt buộc:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    return value == null || compiledPattern.matcher(value).matches();
}
~~~

Lựa chọn này có chủ đích: lỗi “thiếu mã” và “mã sai định dạng” là hai nguyên nhân khác nhau. Không phải mọi constraint đều bắt buộc cho null hợp lệ; người thiết kế phải định nghĩa rõ.

**Thread safety:** Provider có thể giữ và gọi validator nhiều lần, có thể đồng thời. Không lưu giá trị request đang validate vào field mutable của validator; cấu hình `Pattern` chuẩn bị trong `initialize` rồi được đọc trong `isValid` là kiểu thiết kế an toàn. Đừng dùng một `StringBuilder` mutable dùng chung giữa các lời gọi.

## 7. Chu trình Jakarta Validation xử lý `@Constraint`

Khi gọi:

~~~java
try (ValidatorFactory factory =
             Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    var violations = validator.validate(product);
}
~~~

Đoạn trên là **method fragment** cần class và import đúng. Các bước khái niệm:

1. Provider xây metadata về constraint của kiểu bean.
2. Provider xác định các nhóm (`Default` hoặc groups yêu cầu) và property/cascade liên quan.
3. Với mỗi constraint cần kiểm tra, tìm `ConstraintValidator` tương thích kiểu dữ liệu hiện có.
4. Provider tạo và khởi tạo validator thông qua `ConstraintValidatorFactory`; có thể cache/reuse theo chiến lược implementation.
5. Gọi `isValid(value, context)` để đánh giá.
6. Nếu `false`, tạo `ConstraintViolation` với message, path, invalid value, descriptor metadata.
7. Trả `Set<ConstraintViolation<T>>`; **không hứa thứ tự iteration**.

Không viết logic dựa vào “annotation thứ nhất trên field chắc chắn chạy trước annotation thứ hai”. Nếu cần thứ tự **group**, dùng `@GroupSequence`. `isValid` nên tránh sửa input hoặc truy cập nguồn ngoài không kiểm soát.

## 8. Ví dụ Maven/Java 17+ hoàn chỉnh: `@SkuCode`

Ví dụ sau có đủ file, có thể biên dịch bằng Maven với Hibernate Validator. Nó kiểm chứng **annotation definition**, validator implementation, resource-bundle message, kiểm tra optional null và constraint kết hợp `@NotBlank`.

### 8.1. Cấu trúc thư mục

~~~text
sku-constraint-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── validation/
        │           ├── SkuCode.java
        │           ├── SkuCodeValidator.java
        │           ├── ProductInput.java
        │           └── Demo.java
        └── resources/
            └── ValidationMessages.properties
~~~

### 8.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>sku-constraint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
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
~~~

Hibernate Validator 8 là provider triển khai Jakarta Validation 3.0, phù hợp thế hệ Spring Boot 3. `jakarta.el` ở đây cung cấp EL implementation cho hệ nội suy message. Các version này được **cố định để tái lập ví dụ**; trong dự án Spring Boot thật nên để BOM/parent quản lý các dependency tương thích.

### 8.3. `SkuCode.java`: định nghĩa annotation

~~~java
package example.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = SkuCodeValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface SkuCode {
    String message() default "{example.validation.SkuCode.message}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    String prefix() default "SKU";
    int digits() default 3;
}
~~~

Đây là định nghĩa chính. `message` trỏ tới key trong `ValidationMessages.properties`; `prefix` và `digits` là thông số mỗi nơi dùng annotation có thể tùy chỉnh.

### 8.4. `SkuCodeValidator.java`: thực thi logic

~~~java
package example.validation;

import java.util.regex.Pattern;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SkuCodeValidator
        implements ConstraintValidator<SkuCode, String> {

    private Pattern pattern;

    @Override
    public void initialize(SkuCode constraint) {
        int digits = constraint.digits();
        if (digits < 1) {
            throw new IllegalArgumentException(
                    "SkuCode.digits must be positive");
        }

        String expression = Pattern.quote(constraint.prefix())
                + "-[0-9]{" + digits + "}";
        pattern = Pattern.compile(expression);
    }

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || pattern.matcher(value).matches();
    }
}
~~~

Các điểm then chốt:

- `Pattern.quote(prefix)` tránh để một prefix chứa ký tự regex đặc biệt bị diễn giải như biểu thức chính quy.
- `[0-9]` yêu cầu chữ số ASCII; nếu dùng `\\d`, ngữ nghĩa Unicode flag có thể khác nhau theo cấu hình regex, không phù hợp khi cần mã machine-readable cố định.
- `matcher(value).matches()` yêu cầu **toàn bộ chuỗi** khớp định dạng, không chỉ có một đoạn con.
- `initialize(...)` chỉ đọc cấu hình annotation và chuẩn bị `Pattern`; `isValid(...)` không sửa state.
- Null **được chấp nhận bởi riêng `@SkuCode`**, vì quy tắc bắt buộc có mã sẽ do `@NotBlank` đảm trách.
- Không thêm `@Component` chỉ để provider tạo một validator đơn giản; khi cần injection từ Spring, hãy dùng hạ tầng factory tương thích (mục 14).

Nếu muốn kiểm soát cấu hình thiếu hợp lệ của annotation (`digits <= 0`), nên thử nó bằng test và chọn cách báo lỗi cấu hình rõ ràng. Đây **không phải** tình huống người dùng nhập SKU sai, vì cấu hình nằm trong source annotation.

### 8.5. `ProductInput.java`: áp annotation

~~~java
package example.validation;

import jakarta.validation.constraints.NotBlank;

public final class ProductInput {

    @NotBlank
    @SkuCode(prefix = "SKU", digits = 3)
    private final String sku;

    @NotBlank
    private final String title;

    @SkuCode
    private final String optionalAlternateSku;

    public ProductInput(
            String sku, String title, String optionalAlternateSku) {
        this.sku = sku;
        this.title = title;
        this.optionalAlternateSku = optionalAlternateSku;
    }
}
~~~

Không bắt buộc có getter để Hibernate Validator đọc **field-level constraints**; provider có thể đọc field qua reflection theo quy tắc JavaBean validation. `optionalAlternateSku` không có `@NotNull`/`@NotBlank`, nên null được phép theo hợp đồng ở trên.

### 8.6. `ValidationMessages.properties`: mẫu thông báo

~~~properties
example.validation.SkuCode.message=Expected {prefix}-{digits} ASCII digits
~~~

Với `@SkuCode(prefix = "SKU", digits = 3)`, provider có thể nội suy thông báo thành **`Expected SKU-3 ASCII digits`**. Thuộc tính annotation `prefix` và `digits` được dùng trong message interpolation; đây là thông điệp về **định dạng**, không phải biểu diễn một chuỗi mẫu đầy đủ. Nếu muốn thông điệp trực quan như `Expected SKU- followed by exactly 3 digits`, có thể viết lại key theo ngôn ngữ sản phẩm.

Trong bài thực hành, output chương trình bên dưới **không phụ thuộc message text**, tránh sai khác do locale và provider.

### 8.7. `Demo.java`: chạy validation

~~~java
package example.validation;

import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public final class Demo {

    private static String invalidFields(
            Validator validator, ProductInput input) {
        return validator.validate(input).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            ProductInput valid =
                    new ProductInput("SKU-007", "Coffee", null);

            ProductInput invalid =
                    new ProductInput("BAD-007", " ", null);

            ProductInput missingSku =
                    new ProductInput(null, "Coffee", null);

            ProductInput badOptional =
                    new ProductInput("SKU-007", "Coffee", "ALT-123");

            System.out.println("valid="
                    + validator.validate(valid).size());
            System.out.println("invalid="
                    + validator.validate(invalid).size());
            System.out.println("invalid-fields="
                    + invalidFields(validator, invalid));
            System.out.println("missing-sku="
                    + validator.validate(missingSku).size());
            System.out.println("bad-optional="
                    + validator.validate(badOptional).size());
        }
    }
}
~~~

Chạy từ thư mục dự án:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.validation.Demo
~~~

**Stdout do chương trình in** (không tính thông báo Maven, provider hay JVM):

~~~text
valid=0
invalid=2
invalid-fields=sku,title
missing-sku=1
bad-optional=1
~~~

Giải thích:

1. `valid`: SKU `SKU-007` đúng prefix và ba chữ số; title hợp lệ; optional code null được phép => **0** lỗi.
2. `invalid`: `BAD-007` vi phạm `@SkuCode`, `title=" "` vi phạm `@NotBlank` => **2** lỗi. Chuỗi field được sắp xếp để có thứ tự ổn định.
3. `missingSku`: `sku=null` vi phạm `@NotBlank`, nhưng `@SkuCode` **chấp nhận null** => **1** lỗi.
4. `badOptional`: `optionalAlternateSku="ALT-123"` khác null nhưng sai prefix `SKU` của annotation mặc định => **1** lỗi.
5. `validator.validate(...)` trả `Set<ConstraintViolation<ProductInput>>`; số lỗi là kết quả của provider, không phải do getter hay constructor tự kiểm tra.

Nếu bỏ dependency Hibernate Validator nhưng vẫn giữ API annotation, bootstrap có thể không tìm thấy provider. Nếu chỉ chạy `javac Demo.java` không có classpath, sẽ báo thiếu package `jakarta.validation`. Vì vậy ví dụ này **chạy bằng Maven cùng dependencies**; không tuyên bố chạy Java thuần không có JAR.

### 8.8. Kịch bản thay đổi để tự kiểm tra

Hãy thay lần lượt:

- `SKU-123` => hợp lệ.
- `SKU-12` => sai vì chỉ có hai chữ số.
- `SKU-1234` => sai vì bốn chữ số.
- `SKU-ABC` => sai vì không phải chữ số ASCII.
- `sku=""` => `@NotBlank` và `@SkuCode` đều thất bại (có thể có **2** violations trên cùng property).
- `sku=null` => chỉ `@NotBlank` thất bại (có **1** violation).
- `optionalAlternateSku=null` => `@SkuCode` chấp nhận.
- Đổi annotation sang `@SkuCode(prefix="PART", digits=5)` rồi thử `PART-00125` => hợp lệ cho cấu hình mới.
- Đặt `digits=0` => đây là **lỗi cấu hình annotation**, không phải lỗi dữ liệu nhập; validator có guard khi khởi tạo.

Nếu muốn trả về **một** lỗi khi cả `@NotBlank` và `@SkuCode` đều sai, không tự động ép hai constraint về một lỗi. Có thể chọn cơ chế tổng hợp (`@ReportAsSingleViolation`) khi thiết kế một composed constraint riêng, hoặc xử lý field errors theo API contract.

## 9. Tạo message tùy chỉnh và quốc tế hóa

Phần tử chuẩn:

~~~java
String message() default "{example.validation.SkuCode.message}";
~~~

dùng dấu ngoặc nhọn để tham chiếu key trong `ValidationMessages.properties`. Một cách dùng khác:

~~~java
@SkuCode(
    prefix = "SKU",
    digits = 3,
    message = "Mã sản phẩm phải đúng định dạng SKU-###")
private String sku;
~~~

Đây là **mảnh khai báo field**. Ghi message ngay tại nơi dùng có thể hợp lý cho một tình huống nhỏ, nhưng khi cần i18n, dùng resource bundle key thường rõ hơn.

Quá trình message interpolation có thể dùng:

- `{prefix}` và `{digits}` cho annotation attributes.
- Key trong `ValidationMessages.properties`.
- Locale từ cơ chế locale của validation provider/framework.
- Các cú pháp bổ sung theo Jakarta Validation, bao gồm expression language trong ngữ cảnh được hỗ trợ; tránh tự nối nội dung người dùng vào message template có thể được đánh giá.

**Không nhầm:** `message()` định nghĩa **message template**; `ConstraintViolation#getMessage()` trả **thông báo đã nội suy**; `getMessageTemplate()` cho phép lấy **mẫu gốc**. Với API công khai, tốt nhất có mã lỗi ổn định thay vì phân loại lỗi dựa trên câu tiếng Việt/tiếng Anh đã nội suy.

Trong Spring có thể dùng `MessageSource` cùng `LocalValidatorFactoryBean` để tích hợp thông báo; cần kiểm tra cách cấu hình resource bundle và locale để tránh mất message mặc định của provider.

## 10. `groups()`, `Default` và custom annotation

Mọi constraint Jakarta Validation có thể thuộc một hoặc nhiều group. Cú pháp trong annotation:

~~~java
Class<?>[] groups() default {};
~~~

Ví dụ dùng custom constraint khi xuất bản:

~~~java
interface OnPublish {}

class DraftDocument {
    @SkuCode(groups = OnPublish.class)
    private String externalCode;
}
~~~

Đây là **model fragment**. Nếu `OnPublish` là marker interface độc lập:

~~~java
validator.validate(document);                  // Default
validator.validate(document, OnPublish.class); // OnPublish
~~~

- Lượt `Default` **không** tự đánh giá `@SkuCode` chỉ thuộc `OnPublish`.
- Lượt `OnPublish` đánh giá constraint này.
- Các constraint không khai báo groups nằm ở `jakarta.validation.groups.Default`.
- Lời gọi `validate(document, OnPublish.class)` không tự ghép `Default` nếu không có inheritance/sequence được thiết kế.

Trong Spring:

~~~java
@Validated({Default.class, OnPublish.class})
@RequestBody DraftDocument body
~~~

Đây là **tham số controller minh họa**, cần các import `org.springframework.validation.annotation.Validated`, `jakarta.validation.groups.Default` và một method handler phù hợp. `@Validated` là annotation của Spring cho **chọn nhóm**, khác với `@Valid` chuẩn Jakarta cho cascade/validation; `groups` của custom annotation vẫn là nhóm Jakarta.

Không biến các nhóm `Admin`, `Trusted` thành cơ chế authorization. Một DTO vượt qua validation group không chứng minh người gọi có quyền thực hiện hành động.

## 11. Constraint composition: annotation chứa các constraint khác

Có những quy tắc không cần Java logic riêng. Chẳng hạn một nhãn hiển thị phải không blank và có tối đa 20 ký tự. Có thể tạo **composed constraint** gói các built-in:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import jakarta.validation.ReportAsSingleViolation;

@NotBlank
@Size(max = 20)
@ReportAsSingleViolation
@Documented
@Constraint(validatedBy = {})
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface ShortLabel {
    String message() default "Label must be nonblank and at most 20 chars";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là **một file annotation minh họa độc lập** (đặt package và tên file `ShortLabel.java` phù hợp, trong dự án có Jakarta Validation). Không cần `ShortLabelValidator` vì:

- `@NotBlank` và `@Size(max=20)` đã định nghĩa toàn bộ logic.
- `@Constraint(validatedBy={})` nói rằng không có validator bổ sung riêng.
- Provider kiểm tra các composing constraints, theo ngữ nghĩa kết hợp chuẩn **AND**: mọi quy tắc con phải đạt.
- `@ReportAsSingleViolation` yêu cầu biểu diễn việc một hay nhiều composing constraints sai thành **một violation ở constraint tổng hợp**, tránh trả đồng thời các message con cho cùng annotation.
- Nếu bỏ `@ReportAsSingleViolation`, có thể nhận violations từ các composing constraints tương ứng.

**Quan trọng:** Trong Jakarta Validation, composition mặc định là **AND**. Một extension của Hibernate Validator cho phép các kiểu kết hợp logic khác, nhưng đó **không phải API portable chuẩn**. Không viết hai constraint được gắn trên annotation rồi kết luận chúng có nghĩa “A hoặc B”.

### 11.1. `@OverridesAttribute` khi thuộc tính tổng hợp phải điều khiển constraint con

Ví dụ muốn dùng `@ShortLabel(max=32)` thì một annotation custom chỉ có `int max()` **chưa tự truyền** giá trị đó tới `@Size(max=20)` bên trong. Trong Jakarta Validation có `@OverridesAttribute(constraint=Size.class, name="max")` để cấu hình lại thuộc tính composing constraint:

~~~java
import jakarta.validation.OverridesAttribute;
import jakarta.validation.constraints.Size;

@Size(max = 20)
public @interface LabelSize {
    @OverridesAttribute(constraint = Size.class, name = "max")
    int max() default 20;

    // Khi là @Constraint hoàn chỉnh vẫn phải khai báo
    // @Constraint, @Target, @Retention, message/groups/payload.
}
~~~

Đoạn này là **mảnh cú pháp để giải thích `@OverridesAttribute`**, không phải một annotation đầy đủ có thể đưa trực tiếp vào production. Với constraint lặp lại, cần chỉ rõ vị trí constraint bị override khi cần.

### 11.2. Khi nên dùng composition thay vì viết validator

- Dùng composition nếu **tất cả quy tắc đã có sẵn** và cách kết hợp tương đương AND.
- Viết validator riêng nếu quy tắc cần thuật toán, dữ liệu phụ trợ hoặc quan hệ giữa nhiều field.
- Tránh tạo annotation chỉ để đổi tên một annotation built-in mà không mang thêm ngữ nghĩa nghiệp vụ; điều này làm API khó hiểu.
- Nếu lỗi cần một message tổng hợp duy nhất, cân nhắc `@ReportAsSingleViolation`.
- Nếu cần giữ mã lỗi riêng của từng ràng buộc, đừng tự động gộp mọi lỗi thành một thông báo.

## 12. Annotation lặp lại: `@Repeatable` và nested `List`

Có lúc muốn áp **nhiều instance cùng loại** của constraint trên một phần tử, với các thông số khác nhau. Java hỗ trợ `@Repeatable`. Một định nghĩa có thể bổ sung:

~~~java
import java.lang.annotation.Repeatable;

@Repeatable(SkuCode.List.class)
public @interface SkuCode {
    // message/groups/payload/prefix/digits như định nghĩa chuẩn

    @Target({
        ElementType.FIELD, ElementType.METHOD,
        ElementType.PARAMETER, ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    public @interface List {
        SkuCode[] value();
    }
}
~~~

Đây là **mảnh mô tả phần bổ sung**, không phải file thay thế đầy đủ: hãy giữ `@Constraint`, `@Retention`, `@Target` và các phần tử bắt buộc trên annotation bên ngoài. Container `List` phải có target/retention phù hợp.

Hai điều cần cân nhắc:

1. **Constraint lặp lại mặc định kết hợp theo AND**, không phải OR. Nếu viết hai `@SkuCode` với prefix hoàn toàn khác nhau trên một field, dữ liệu có thể không bao giờ đạt đồng thời cả hai.
2. `@Repeatable` là cơ chế khai báo cú pháp Java; provider vẫn phải đánh giá từng instance constraint với cấu hình riêng. Nếu nghiệp vụ muốn “một trong hai định dạng”, thường cần một validator tổng hợp hoặc cơ chế composition phù hợp, không chỉ gắn lặp cùng annotation.

Một số Jakarta constraints chuẩn cung cấp nested `List` để hỗ trợ nhiều khai báo; khi tạo custom constraint, chỉ thêm repeatability nếu có use case thật sự rõ ràng.

## 13. `payload()` để mang metadata mở rộng

Chữ ký chuẩn:

~~~java
Class<? extends Payload>[] payload() default {};
~~~

`Payload` là marker interface của Jakarta Validation; ứng dụng có thể dùng các kiểu triển khai để gắn metadata, ví dụ mức độ hiển thị cảnh báo:

~~~java
import jakarta.validation.Payload;

public final class Severity {
    private Severity() {}

    public static final class Warning implements Payload {}
    public static final class Error implements Payload {}
}
~~~

Dùng ở declaration:

~~~java
@SkuCode(payload = {Severity.Error.class})
private String sku;
~~~

Đây là **fragment field** cần `Severity` và `SkuCode` đã định nghĩa. Có thể lấy metadata:

~~~java
violation.getConstraintDescriptor().getPayload();
~~~

`payload` tự nó **không làm provider chuyển HTTP status, severity hay cách render UI**. Ứng dụng muốn xử lý thì phải đọc metadata và tự thực hiện chính sách. Nếu không cần, giữ mảng rỗng, đừng thiết kế hệ thống “warning” giả định provider sẽ tự bỏ qua violation.

## 14. Tích hợp vào Spring Framework / Spring Boot

Trong Spring Boot 3.x, dependency thông thường:

~~~xml
<!-- Dependency fragment trong dự án đã có Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đoạn trên **không phải pom.xml đầy đủ**. Spring 6 / Boot 3 dùng namespace **`jakarta.validation`**; mã thế hệ cũ thường dùng `javax.validation` và cần chuyển đổi dependency/import tương thích.

### 14.1. Spring MVC kích hoạt custom constraint

Khi `ProductRequest` có field:

~~~java
public record ProductRequest(
        @jakarta.validation.constraints.NotBlank
        @SkuCode String sku) {}
~~~

và controller có:

~~~java
@PostMapping("/products")
public Map<String, String> create(
        @Valid @RequestBody ProductRequest request) {
    return Map.of("sku", request.sku());
}
~~~

Hai phần này là **mảnh mã của một ứng dụng Spring MVC**; cần imports, `@RestController`, các dependency Boot và annotation `SkuCode` có trong cùng project. Spring MVC thường:

1. Dùng Jackson deserialize JSON từ request body thành `ProductRequest`.
2. Kích hoạt Jakarta Validation vì có `@Valid`/`@Validated` trên tham số.
3. Provider đọc `@SkuCode`, chọn `SkuCodeValidator` và gọi `isValid`.
4. Nếu có lỗi, với đường validation đối số thông thường, Spring MVC có thể ném `MethodArgumentNotValidException` và trả HTTP **400** mặc định.
5. Nếu hợp lệ, method controller mới xử lý nghiệp vụ.

Một JSON ví dụ:

~~~json
{"sku":"BAD-001"}
~~~

Nếu DTO đã bind thành công và validator hoạt động, SKU này sai prefix, nên không qua constraint. Payload lỗi HTTP thực tế còn tùy `@ControllerAdvice`, cấu hình Problem Details và Spring Boot; đừng khẳng định luôn có một hình dạng JSON lỗi cố định.

Nếu `@SkuCode` được đặt trên một field mà không có điểm kích hoạt validation, annotation chỉ là metadata. Nếu gửi `"sku":123` mà Jackson không thể chuyển sang String theo cấu hình hiện tại, lỗi conversion có thể xuất hiện **trước** custom validator.

### 14.2. Injection vào validator trong Spring

Có những constraint cần service, ví dụ kiểm tra mã được đăng ký trong bảng cấu hình. Spring cung cấp `LocalValidatorFactoryBean`, thường cấu hình `SpringConstraintValidatorFactory` để tạo validator và hỗ trợ Spring dependency injection.

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import org.springframework.beans.factory.annotation.Autowired;

public class RegisteredCodeValidator
        implements ConstraintValidator<RegisteredCode, String> {

    private final CodeRegistry registry;

    @Autowired
    public RegisteredCodeValidator(CodeRegistry registry) {
        this.registry = registry;
    }

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || registry.isRegistered(value);
    }
}
~~~

Đây là **fragment thiết kế**, cần `RegisteredCode`, `CodeRegistry` và cấu hình bean thích hợp, không phải file tự chạy. Nếu bootstrap Jakarta Validator **thuần** bằng `Validation.buildDefaultValidatorFactory()` ngoài Spring và không đăng ký factory tùy biến, đừng giả định `@Autowired` sẽ được xử lý.

**Lưu ý kiến trúc:** Xác minh mã với DB từ mọi lần validation có thể tạo N+1 queries, tăng độ trễ và không bảo đảm tính nhất quán ở thời điểm commit. Nếu tính duy nhất/tồn tại là bất biến dữ liệu quan trọng, vẫn cần ràng buộc DB, transaction và service policy; custom constraint không thay thế chúng.

### 14.3. Bean con và container element trong Spring

Custom constraint có thể dùng chung với `@Valid`:

~~~java
public class PurchaseRequest {
    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    private ProductRequest product;
}
~~~

Nếu `product == null`, `@Valid` **bỏ qua cascade**; `@NotNull` bắt buộc object hiện diện. Nếu object tồn tại, provider kiểm tra `@SkuCode` nằm trên field của `ProductRequest`. Với `List<@SkuCode String>`, constraint kiểm tra từng string; cần `@NotNull` trên type argument nếu muốn cấm phần tử null mà chính custom validator cho null hợp lệ.

## 15. Metadata API: introspection định nghĩa constraint

Ngoài validation, Jakarta Validation có **metadata API**. Bạn có thể hỏi provider những constraint đã khai báo:

~~~java
var beanDescriptor =
        validator.getConstraintsForClass(ProductInput.class);

var propertyDescriptor =
        beanDescriptor.getConstraintsForProperty("sku");

if (propertyDescriptor != null) {
    for (var descriptor :
            propertyDescriptor.getConstraintDescriptors()) {
        System.out.println(
                descriptor.getAnnotation()
                          .annotationType().getSimpleName());
    }
}
~~~

Đoạn trên là **fragment chạy bên trong method đã có biến `validator` và class `ProductInput`**. Trên property `sku` ví dụ có cả `NotBlank` và `SkuCode`. Thứ tự duyệt các descriptors không được cam kết.

Metadata có thể giúp:
- Xác định annotation type và groups.
- Truy cập `getAttributes()` để xem `prefix`/`digits`.
- Lấy `getPayload()` để đọc marker metadata.
- Kiểm tra danh sách implementation `ConstraintValidator` được provider nhận diện.
- Xây tooling cho tài liệu hoặc test quy ước của project.

**Không dùng reflection đơn thuần như một lời gọi validate**: `ProductInput.class.getDeclaredField("sku").getAnnotation(SkuCode.class)` chỉ đọc annotation, không tự chạy `isValid` và không tạo `ConstraintViolation`. Metadata API là một khía cạnh khác của cùng hợp đồng.

## 16. Báo lỗi theo property bằng `ConstraintValidatorContext`

Mặc định, một validator gắn trên field trả `false` sẽ tạo violation gắn vào field đó. Với **class-level constraint** kiểm tra nhiều field, đôi khi bạn muốn đặt lỗi vào một property cụ thể thay vì root object:

~~~java
@Override
public boolean isValid(Booking value,
                       ConstraintValidatorContext context) {
    if (value == null
            || value.getStart() == null
            || value.getEnd() == null) {
        return true;
    }

    boolean valid = !value.getEnd().isBefore(value.getStart());
    if (!valid) {
        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                "{example.validation.DateRange.message}")
               .addPropertyNode("end")
               .addConstraintViolation();
    }
    return valid;
}
~~~

Đây là **method fragment** trong `ConstraintValidator<DateRange, Booking>`, cần class `Booking` và các imports tương ứng.

- `disableDefaultConstraintViolation()` bỏ violation mặc định của constraint này.
- `buildConstraintViolationWithTemplate(...)` tạo violation với message template bạn chọn.
- `addPropertyNode("end")` gắn lỗi vào property `end`.
- `addConstraintViolation()` **bắt buộc** để hoàn tất definition của violation tùy chỉnh.
- `isValid` vẫn phải trả `false` cho trường hợp vi phạm.

Nếu disable default rồi không xây violation thay thế khi trả false, implementation có thể báo lỗi. Không gọi builder chỉ để trang trí khi method trả true.

**Giới hạn:** Việc xây constraint violations theo property node là tác vụ của validator; annotation definition vẫn cần `@Constraint`/`@Target(TYPE)`/mandatory members đúng như các phần trên.

## 17. Constraint trên method và cross-parameter: trường hợp nâng cao

Phần lớn custom annotation kiểm tra **một giá trị** (field/parameter/property). Nếu cần so sánh **nhiều tham số của cùng một method**, ví dụ một phương thức nhận `start` và `end`, phải tạo *cross-parameter constraint*.

Theo Jakarta Validation, validator dạng cross-parameter thường cần:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;

@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class ConsistentDatesValidator
        implements ConstraintValidator<ConsistentDates, Object[]> {

    @Override
    public boolean isValid(
            Object[] values, ConstraintValidatorContext context) {
        // Kiểm tra quan hệ giữa các tham số.
        return true;
    }
}
~~~

Đây là **fragment minh họa**, chưa có logic kiểm tra và chưa có `@ConsistentDates`; không nên sao chép như một validator nghiệp vụ hoàn chỉnh.

- Annotation cross-parameter thường có target `METHOD`/`CONSTRUCTOR`.
- Validator nhận `Object[]` chứa các tham số method và được đánh dấu `@SupportedValidationTarget(PARAMETERS)`.
- Nếu một annotation hỗ trợ **đồng thời** generic/return-value và cross-parameter, đặc tả yêu cầu thuộc tính `validationAppliesTo()` phù hợp để phân biệt khi việc suy luận đích không rõ ràng.
- Việc khai báo constraint trên method **không** làm một lời gọi Java thông thường tự validate. Cần `ExecutableValidator` hoặc tích hợp Spring method validation (proxy/AOP hoặc cơ chế MVC phù hợp).

Không đưa cross-parameter logic vào mọi custom constraint đơn giản; `@SkuCode` trên `String` là một **generic constraint** và không cần `validationAppliesTo()`.

## 18. Exception: lỗi dữ liệu khác với lỗi định nghĩa annotation

Khi người dùng nhập dữ liệu sai định dạng, một custom constraint đúng sẽ trả `false` và provider tạo `ConstraintViolation`. Nhưng khi **định nghĩa constraint sai**, hành vi là exception về **hạ tầng/cấu hình**:

| Vấn đề | Hành vi/triệu chứng thường gặp | Cách xử lý |
| --- | --- | --- |
| Annotation thiếu `@Constraint` | Provider không nhận như constraint custom | Bổ sung meta annotation đúng |
| Thiếu `@Retention(RUNTIME)` | Metadata không được nhận diện đúng | Dùng `RUNTIME` |
| Thiếu `message`/`groups`/`payload` hoặc sai kiểu | `ConstraintDefinitionException` | Sửa hợp đồng annotation |
| `validatedBy` trỏ validator không tương thích | `UnexpectedTypeException` hoặc lỗi validator resolution | Kiểm tra generic type và `@Target` |
| Hai validator đích trùng/không phân giải được | `ConstraintDefinitionException`/`UnexpectedTypeException` tùy cấu hình | Sửa danh sách `validatedBy` |
| Annotation chỉ hỗ trợ String nhưng gắn lên Long | `UnexpectedTypeException` | Đổi kiểu data hoặc validator tương thích |
| Validator dùng service chưa được inject | Injection thất bại/null dependency | Dùng SpringConstraintValidatorFactory hoặc wiring đúng |
| `isValid` ném exception do code lỗi | `ValidationException` hoặc exception được provider bao bọc | Sửa validator; không coi là dữ liệu không hợp lệ thông thường |
| Không có provider khi bootstrap | `NoProviderFoundException` | Thêm Hibernate Validator/provider tương thích |
| `@SkuCode` cho phép null nhưng field bắt buộc | null không tạo violation từ custom constraint | Ghép `@NotNull` hoặc `@NotBlank` |
| Spring thiếu `@Valid` trên request DTO | Custom constraint không được kích hoạt ở điểm đó | Đặt annotation kích hoạt validation thích hợp |
| Trộn `javax.validation` với `jakarta.validation` ở Spring 6+ | Annotation/provider không tương thích | Đồng bộ namespace và dependency |

Không tự động chuyển mọi `ValidationException` thành HTTP 400 “người dùng nhập sai”. Exception cấu hình cần xử lý như lỗi lập trình/vận hành, có logging/monitoring phù hợp, không trả stack trace cho client.

## 19. Kiểm thử custom annotation nên bao phủ những gì?

Ngoài happy path trong ví dụ, nên có các test sau:

| Test | Kỳ vọng |
| --- | --- |
| `"SKU-007"` với digits=3 | Hợp lệ |
| `"SKU-7"` với digits=3 | Vi phạm `@SkuCode` |
| `"sku-007"` | Vi phạm nếu policy phân biệt hoa/thường |
| `"SKU-ABC"` | Vi phạm vì không phải chữ số |
| `"SKU-1234"` | Vi phạm vì dư một chữ số |
| `"BAD-007"` | Vi phạm prefix |
| `null` trên field chỉ có `@SkuCode` | Hợp lệ theo hợp đồng đã thiết kế |
| `null` trên field có `@NotBlank @SkuCode` | Vi phạm `@NotBlank` |
| `""` trên field có hai annotation | Có thể có hai violations cùng property |
| `@SkuCode(prefix="PART",digits=5)` | Dùng đúng cấu hình riêng |
| `List<@SkuCode String>` | Từng phần tử được validate, với provider hỗ trợ extractor |
| `groups=Publish.class` | Chỉ chạy ở Publish hoặc nhóm liên quan |
| Đọc constraint descriptor | Có annotation và attributes mong đợi |
| Sai kiểu, ví dụ Long | Nhận diện lỗi cấu hình `UnexpectedTypeException` |
| `digits=0` | Guard báo lỗi cấu hình, không lặng lẽ chấp nhận chuỗi sai |

Thực hành tốt:

- Dùng test độc lập `ValidatorFactory` cho thuật toán thuần.
- Dùng Spring integration test nếu validator có Spring dependency injection.
- Dùng MockMvc/WebMvcTest khi cần kiểm tra HTTP status, binding, locale và mapping lỗi của controller.
- So sánh **property path/constraint annotation type/số lượng violation**, không dựa vào thứ tự của `Set` hoặc message nội suy cố định khi test không kiểm soát locale.
- Test boundary của thuộc tính cấu hình, bao gồm prefix chứa ký tự regex, chữ số Unicode, whitespace, null và strings rất dài.
- Nếu có DB hoặc network, test timeout và lỗi dependency riêng khỏi tình huống input sai.

### 19.1. Test logic không cần giả lập Spring khi không có DI

Ví dụ trong mục 8 có thể kiểm tra trực tiếp qua Jakarta `Validator`, do validator chỉ dùng `Pattern` và annotation attributes. Đó là **unit/integration test ở tầng validation provider**.

Nếu logic validator dựa vào Spring-managed collaborator, tạo `ApplicationContext`/Spring Boot test để chứng minh collaborator được inject. Đừng dùng cùng một cấu hình test thuần Jakarta rồi giả định nó phản ánh môi trường Spring.

## 20. Khi nào nên tạo annotation mới?

**Nên tạo custom constraint** khi:
- Quy tắc là một tính chất dữ liệu **tái sử dụng** tại nhiều DTO/property.
- Có ý nghĩa ngắn gọn, ổn định như `@SkuCode`, `@ValidPhoneNumber`, `@ValidDateRange`.
- Có thể mô tả ngữ nghĩa, null behavior, groups và message một cách độc lập.
- Muốn các thành phần Spring/Jakarta Validation xử lý lỗi theo cùng một cơ chế.

**Ưu tiên built-in hoặc composition** khi:
- Chỉ cần `@NotBlank`, `@Size`, `@Pattern`, `@Email`, `@Positive`...
- Rule chỉ là kết hợp AND của các constraint đã có.
- Một annotation custom sẽ chỉ làm ẩn một regex đơn giản mà không tăng khả năng đọc.

**Ưu tiên service/domain validation** khi:
- Cần dữ liệu từ DB, trạng thái transaction, authorization, race-condition handling.
- Tính hợp lệ phụ thuộc người dùng đang đăng nhập, vai trò, sự tồn tại của entity, workflow state.
- Rule cần gọi hệ thống ngoài hoặc có tác dụng phụ.
- Ràng buộc unique/integrity phải được DB bảo đảm ngay cả khi nhiều request xảy ra đồng thời.

Một custom annotation không phải ranh giới bảo mật; dữ liệu “đã qua `@Valid`” vẫn phải được kiểm tra chính sách nghiệp vụ và quyền truy cập.

## 21. Checklist định nghĩa một constraint đúng chuẩn

Trước khi dùng trong production, kiểm tra:

- [ ] Annotation có `@Constraint(validatedBy=...)` trỏ implementation hoặc `{}` hợp lý với composition.
- [ ] Có `@Retention(RUNTIME)`.
- [ ] `@Target` cho phép chính xác các vị trí cần gắn.
- [ ] Có `String message() default ...`.
- [ ] Có `Class<?>[] groups() default {}`.
- [ ] Có `Class<? extends Payload>[] payload() default {}`.
- [ ] Thuộc tính custom không dùng tên dành riêng hay prefix bị cấm.
- [ ] Mỗi `ConstraintValidator<A,T>` thực sự tương thích type gắn annotation.
- [ ] `initialize` đọc cấu hình; `isValid` không có state per-request dùng chung.
- [ ] Null behavior được diễn đạt và test rõ ràng; thêm `@NotNull`/`@NotBlank` nếu cần.
- [ ] Message key trong `ValidationMessages.properties` hợp lệ, locale được kiểm thử nếu cần.
- [ ] Bean Validation provider đã có trên classpath và đang được framework sử dụng.
- [ ] Spring dependency injection chỉ được kỳ vọng khi factory hỗ trợ.
- [ ] Có test happy path, negative path, sai cấu hình, groups, container/nested khi phù hợp.
- [ ] Không dựa vào exception cấu hình để báo input sai, không dùng constraint thay thế security/service/DB.

## 22. Câu hỏi ôn tập

**Câu 1.** Tại sao Java annotation có `@Retention(RUNTIME)` nhưng thiếu `@Constraint` vẫn không phải Jakarta Validation constraint?

**Đáp:** Vì provider chỉ coi annotation như constraint khi có định nghĩa hợp đồng Jakarta, bao gồm `@Constraint` và các phần tử chuẩn; retention chỉ cho phép metadata tồn tại khi chạy.

**Câu 2.** Ba phần tử bắt buộc là gì?

**Đáp:**

~~~java
String message() default "{my.Constraint.message}";
Class<?>[] groups() default {};
Class<? extends jakarta.validation.Payload>[] payload() default {};
~~~

**Câu 3.** `@Constraint(validatedBy={})` có luôn sai không?

**Đáp:** Không. Nó phù hợp với **composed constraint** chỉ dùng các constraint khác có sẵn và không có validator tự viết.

**Câu 4.** Muốn đặt `@SkuCode` lên `List<@SkuCode String>`, cần target nào?

**Đáp:** `TYPE_USE` cho annotation nằm trên type argument, và provider cần extractor tương thích với list; tránh nhầm với `TYPE` (class-level constraint).

**Câu 5.** Vì sao `@SkuCode` trong ví dụ chấp nhận null?

**Đáp:** Validator được thiết kế kiểm tra format khi giá trị có mặt; muốn field bắt buộc, bổ sung `@NotBlank`/`@NotNull`.

**Câu 6.** `String prefix() default "SKU"` có ý nghĩa gì?

**Đáp:** Đây là annotation attribute do người thiết kế tạo. Nó được truyền tới `initialize` qua instance annotation, cho phép tái sử dụng validator với nhiều prefix khác nhau.

**Câu 7.** `@ReportAsSingleViolation` dùng khi nào?

**Đáp:** Với composed constraint, nó yêu cầu báo một violation tổng hợp khi các constraint cấu thành thất bại, thay vì nhiều violation con.

**Câu 8.** Gắn một custom constraint trực tiếp lên tham số service có tự chạy khi gọi Java bình thường không?

**Đáp:** Không. Cần `ExecutableValidator` hoặc tích hợp method validation thực sự hoạt động; trong Spring AOP, lời gọi phải đi qua proxy phù hợp.

**Câu 9.** Một custom validator cần Spring service qua constructor. Tại sao demo `Validation.buildDefaultValidatorFactory()` không đủ?

**Đáp:** Bootstrap Jakarta thuần không mặc nhiên sử dụng SpringConstraintValidatorFactory. Cần hạ tầng Spring `LocalValidatorFactoryBean`/factory thích hợp để xử lý dependency injection.

**Câu 10.** Khi annotation gắn lên `Long` nhưng chỉ có `ConstraintValidator<SkuCode,String>`, phải sửa thế nào?

**Đáp:** Không ép provider tự chuyển Long thành String. Chọn kiểu dữ liệu đúng hoặc viết implementation tương thích nếu bài toán thật sự yêu cầu; lỗi thường là `UnexpectedTypeException`.

## 23. Tổng kết

- **`@Constraint` biến một Java annotation thành định nghĩa ràng buộc Jakarta Validation** và gắn nó với implementation qua `validatedBy`.
- Annotation phải có `RUNTIME` retention và ba phần tử chuẩn `message`, `groups`, `payload` với chữ ký đúng.
- `@Target` quyết định vị trí được gắn; `ConstraintValidator<A,T>` quyết định kiểu dữ liệu có thể kiểm tra và cách đánh giá.
- Các thuộc tính như `prefix`/`digits` làm annotation tái sử dụng được; `initialize` đọc cấu hình, `isValid` thực thi logic.
- **Constraint composition** với `validatedBy={}` phù hợp khi chỉ kết hợp các constraint sẵn có; `@ReportAsSingleViolation` kiểm soát cách báo lỗi tổng hợp.
- Null policy, groups, metadata, message bundle và Spring injection là phần quan trọng của thiết kế annotation, không phải chi tiết phụ.
- Trong Spring MVC, `@Valid`/`@Validated` kích hoạt validation sau binding; lỗi cấu hình annotation khác lỗi dữ liệu.
- Chỉ nên tạo custom constraint khi nó tăng khả năng mô tả và tái sử dụng quy tắc. Đừng dùng annotation để thay thế kiểm tra quyền, transaction hay database integrity.

### Tài liệu tham khảo chính thức

- Jakarta Validation 3.1 Specification – Constraint definition, annotation properties, implementation và composition: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 API – `@Constraint`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraint
- Jakarta Validation 3.1 API – `ConstraintValidator`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraintvalidator
- Jakarta Validation 3.1 API – `@ReportAsSingleViolation`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/reportassingleviolation
- Hibernate Validator 8 Reference Guide – Custom constraints, constraint composition và messages: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework – Configure Custom Constraints/LocalValidatorFactoryBean: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework – Validation trong Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
