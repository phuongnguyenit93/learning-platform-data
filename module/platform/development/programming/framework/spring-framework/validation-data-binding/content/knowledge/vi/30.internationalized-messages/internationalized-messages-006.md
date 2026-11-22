# ValidationMessages.properties và message template của Bean Validation

## 1. Mục tiêu: tách ràng buộc khỏi câu thông báo

Trong Jakarta Bean Validation, các annotation như `@NotBlank`, `@NotNull`, `@Size`, `@Min`, `@Pattern` kiểm tra tính hợp lệ của đối tượng, tham số và kết quả phương thức. Một quy tắc có thể áp dụng cho nhiều ngôn ngữ, ví dụ:

- Tiếng Việt: **Mã phải dài từ 3 đến 8 ký tự**.
- Tiếng Anh: **Code length must be between 3 and 8 characters**.

Thay vì hardcode một câu cố định trên annotation, hãy khai báo **message template** bằng khóa trong resource bundle:

```java
@Size(min = 3, max = 8, message = "{app.code.size}")
private String code;
```

Và tạo file:

```text
src/main/resources/
├── ValidationMessages.properties
├── ValidationMessages_vi.properties
└── ValidationMessages_en.properties
```

Ví dụ bản tiếng Việt:

```properties
app.code.size=Mã phải dài từ {min} đến {max} ký tự
```

Provider Jakarta Bean Validation đọc message template, tìm khóa `app.code.size`, chọn bản dịch phù hợp `Locale`, rồi thay `{min}`/`{max}` bằng giá trị từ annotation.

**Phân biệt:**

1. `{app.code.size}` là **khóa bundle**.
2. `{min}`, `{max}`, `{value}` có thể là **constraint attributes** được nội suy.
3. `ConstraintViolation#getMessageTemplate()` giữ mẫu gốc.
4. `ConstraintViolation#getMessage()` chứa câu đã được nội suy.
5. `ValidationMessages.properties` của Bean Validation **khác cơ chế mặc định** `messages.properties` của Spring `MessageSource`.

## 2. Cấu trúc resource bundle

Tên cơ sở của bundle theo chuẩn là `ValidationMessages`, với chữ V và M viết hoa. Các file thông dụng được đặt **tại gốc classpath**, ví dụ `src/main/resources/ValidationMessages_vi.properties` trong Maven.

| Locale mục tiêu | Tên file được ưu tiên | Ý nghĩa |
| --- | --- | --- |
| `vi-VN` | `ValidationMessages_vi_VN.properties` nếu có | Bản tiếng Việt dành cho Việt Nam |
| `vi` | `ValidationMessages_vi.properties` | Bản tiếng Việt tổng quát |
| `en-US` | `ValidationMessages_en_US.properties` nếu có | Bản tiếng Anh dành cho Mỹ |
| `en` | `ValidationMessages_en.properties` | Bản tiếng Anh tổng quát |
| Không có bản locale riêng | `ValidationMessages.properties` và các fallback theo ResourceBundle | Thông điệp dự phòng |

Java `ResourceBundle` còn có quy tắc candidate locale và fallback liên quan default locale của JVM. Vì thế cần kiểm tra cả locale thực tế lẫn các file có trong artifact, không chỉ suy luận theo suffix của file.

Nên có `ValidationMessages.properties` gốc chứa các key dùng làm fallback, nhất là các khóa tự định nghĩa như `app.account.username.required`. Provider có bundle thông báo riêng cho các constraint chuẩn, nhưng không tự biết câu dịch của tất cả custom keys.

### 2.1. Ví dụ hai ngôn ngữ

```properties
# ValidationMessages_vi.properties, lưu UTF-8
app.username.required=Tên đăng nhập không được để trống
app.code.size=Mã phải dài từ {min} đến {max} ký tự
app.age.minimum=Tuổi phải từ {value} trở lên
```

```properties
# ValidationMessages_en.properties, lưu UTF-8
app.username.required=Username must not be blank
app.code.size=Code length must be between {min} and {max} characters
app.age.minimum=Age must be at least {value}
```

Cấu trúc khóa có prefix `app.` giúp tránh trùng với tên attribute ngắn như `min`, `max`, `value`. Dùng UTF-8 và xác nhận các file thực sự được đóng gói vào classpath khi build. Java 9+ hỗ trợ UTF-8 cho property resource bundles với cơ chế tương thích; một số provider/loader có cấu hình riêng, vì vậy vẫn phải test tiếng Việt có dấu.

### 2.2. Không nhầm đường dẫn file

Đúng theo convention mặc định:

```text
src/main/resources/ValidationMessages.properties
```

Không giống:

```text
src/main/resources/messages/ValidationMessages.properties
```

Đường dẫn thứ hai chỉ được tìm nếu bạn tùy biến bundle locator hoặc classpath configuration tương ứng. Tên file không phải tên package Java.

## 3. Message template và ConstraintViolation

Xét:

```java
@NotBlank(message = "{app.username.required}")
String username;
```

Khi trường không hợp lệ, provider tạo `ConstraintViolation<?>`:

| API | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `getMessageTemplate()` | `{app.username.required}` | Chuỗi descriptor gốc ở annotation |
| `getMessage()` | `Tên đăng nhập không được để trống` | Kết quả interpolation tại thời điểm validation |
| `getPropertyPath()` | `username` | Vị trí vi phạm |
| `getConstraintDescriptor()` | Metadata của `@NotBlank` | Annotation, attributes, groups... |
| `getInvalidValue()` | `"   "` | Dữ liệu bị từ chối, có thể nhạy cảm |

Không dùng `getMessageTemplate()` làm câu hiển thị. Ngược lại, không dùng `getMessage()` làm machine-readable code vì nó thay đổi theo locale, wording và translation bundle.

Trong REST API, bạn có thể tạo DTO lỗi như:

```json
{
  "field": "username",
  "code": "USERNAME_REQUIRED",
  "message": "Tên đăng nhập không được để trống"
}
```

Đây là hợp đồng API minh họa; mã nghiệp vụ `USERNAME_REQUIRED` do ứng dụng lựa chọn, không nhất thiết giống khóa interpolation.

## 4. Thuật toán nội suy của Jakarta Bean Validation

Jakarta Bean Validation 3.0 mô tả thứ tự resolution trong mục 6.3.1.1. Với descriptor `{app.code.size}`:

1. Tìm các tham số `{key}` trong resource bundle **người dùng** `ValidationMessages` theo locale; thay bằng value tìm thấy và tiếp tục **đệ quy** nếu value lại chứa tham số.
2. Tra các tham số còn lại trong bundle **built-in** của Jakarta Bean Validation provider. Bước provider không được mở rộng đệ quy như bước người dùng.
3. Nếu bước provider tìm được thay thế, chạy lại bước tra bundle người dùng; điều này đảm bảo bundle người dùng ưu tiên khi có khóa trùng.
4. Thay tham số trùng tên **annotation attributes**, như `{min}`, `{max}` của `@Size` hoặc `{value}` của `@Min`.
5. Đánh giá biểu thức Jakarta Expression Language dạng `${...}`, với khả năng và giới hạn của interpolator/provider.

Ví dụ:

```text
{app.code.size}
  |
  v  tra ValidationMessages_vi.properties
Mã phải dài từ {min} đến {max} ký tự
  |
  v  thay @Size(min=3,max=8)
Mã phải dài từ 3 đến 8 ký tự
```

**Đây không phải thuật toán MessageFormat của Spring `MessageSource`.** Bean Validation dùng cả tra cứu bundle, nội suy constraint attributes và có thể đánh giá EL.

### 4.1. Ưu tiên bundle ứng dụng

Constraint chuẩn như `@NotNull` thường có template mặc định:

```text
{jakarta.validation.constraints.NotNull.message}
```

Hibernate Validator có bản dịch built-in. Bạn có thể ghi đè bằng file của ứng dụng:

```properties
# ValidationMessages_vi.properties
jakarta.validation.constraints.NotNull.message=Giá trị bắt buộc
```

Vì lookup người dùng diễn ra trước provider, câu này được ưu tiên. Tuy nhiên nó ảnh hưởng **mọi `@NotNull` dùng default template**, không chỉ một trường riêng.

Để viết câu riêng cho một property, hãy khai báo:

```java
@NotNull(message = "{app.account.region.required}")
String region;
```

và đặt key tương ứng thay vì thay key built-in toàn hệ thống.

### 4.2. Đệ quy trong bundle người dùng

Bạn có thể dùng tham chiếu key:

```properties
app.username.required={app.common.required}
app.common.required=Giá trị không được để trống
```

Bước tra bundle ứng dụng lặp đệ quy để cho ra câu cuối. Nhưng đừng tạo vòng tham chiếu như `a={b}`, `b={a}`; nó không mang lại giá trị và có thể gây hành vi không như dự kiến.

### 4.3. Tránh va chạm với tên thuộc tính

Nếu tự tạo một bundle key tên `min`, nó có thể được áp dụng trước khi `{min}` được thay từ annotation attribute. Với custom messages, hãy ưu tiên namespace như `app.checkout.amount.minimum` thay vì key chung `min` hoặc `value`.

## 5. Nội suy constraint attribute

Một literal message như:

```java
@Min(value = 18, message = "Tuổi phải từ {value} trở lên")
Integer age;
```

có thể tạo câu **Tuổi phải từ 18 trở lên**, vì `{value}` là annotation attribute. Nhưng câu literal tiếng Việt này **không tự đa ngữ**. Tốt hơn:

```java
@Min(value = 18, message = "{app.age.minimum}")
Integer age;
```

với:

```properties
# tiếng Việt
app.age.minimum=Tuổi phải từ {value} trở lên
```

```properties
# tiếng Anh
app.age.minimum=Age must be at least {value}
```

Tương tự:

```java
@Size(min = 3, max = 8, message = "{app.code.size}")
String code;
```

Các giá trị `3` và `8` do annotation khai báo, không nên được hardcode vào cả hai file nếu muốn dễ đổi quy tắc.

### Các attribute thường gặp

| Constraint | Placeholder | Ví dụ |
| --- | --- | --- |
| `@Min(18)` | `{value}` | `18` |
| `@Max(100)` | `{value}` | `100` |
| `@Size(min=3,max=8)` | `{min}`, `{max}` | `3`, `8` |
| `@DecimalMin(value="10.5")` | `{value}`, có thể kết hợp EL theo `inclusive` | `10.5` |
| `@Pattern(regexp="...")` | `{regexp}` nếu thật sự cần | Regex, nhưng hiển thị nguyên regex thường không thân thiện |

Không phải mọi constraint có `min` hoặc `value` giống nhau; hãy xem metadata của annotation đang dùng.

## 6. Message expressions: ${...} khác {..}

Jakarta Bean Validation hỗ trợ hai kiểu nội suy:

- `{...}`: message parameter, bundle key hoặc constraint attribute.
- `${...}`: Jakarta Expression Language (EL).

Ví dụ:

```java
@DecimalMin(
    value = "10.5",
    inclusive = true,
    message = "Giá trị phải lớn hơn ${inclusive == true ? 'hoặc bằng ' : ''}{value}"
)
BigDecimal amount;
```

Đây là đoạn khai báo minh họa; cần import `BigDecimal` và `@DecimalMin`. Với `inclusive=true`, EL chọn đoạn “hoặc bằng”; `{value}` cho ra `10.5`. EL cho phép truy cập những tên chuẩn như:

- Attributes của constraint, ví dụ `inclusive`.
- `validatedValue`: giá trị đang được kiểm tra.
- `formatter`: helper format số theo locale, ví dụ `${formatter.format('%1$.2f', validatedValue)}`.

Theo đặc tả, nội suy tham số `{...}` có **ưu tiên trước** đánh giá EL. Vì thế biểu thức chứa tên giống attribute cần được test thực tế; không mặc định rằng mọi `${value}` đều còn nguyên đến giai đoạn EL.

EL có thể đòi hỏi Jakarta EL implementation trên classpath. Hibernate Validator có giới hạn an toàn và các thiết lập riêng cho EL trong constraint message mặc định so với vi phạm tạo thủ công qua `ConstraintValidatorContext`. Không tạo EL template bằng cách ghép trực tiếp nội dung do client gửi.

## 7. Escape ký tự đặc biệt

Trong message descriptor của Jakarta Bean Validation:

| Runtime template chứa | Ý nghĩa |
| --- | --- |
| `\{` | Dấu `{` literal, không bắt đầu message parameter |
| `\}` | Dấu `}` literal |
| `\$` | Dấu `$` literal, không bắt đầu EL expression |
| `\\` | Dấu `\` literal |

**Phân biệt nhiều tầng escape:** Java string literal, định dạng `.properties` và MessageInterpolator đều xử lý dấu `\`. Ví dụ một runtime template cần dấu `\{` thì source Java phải escape dấu slash theo cú pháp Java; trong file `.properties` dấu slash lại có ngữ nghĩa khác. Hãy viết test nhỏ với nội dung literal đặc biệt, không copy số lượng slash giữa các tầng mà không xác minh.

Để đơn giản hóa, nên giữ template chính là một key như `{app.reference.format}` và để bundle chứa lời giải thích thân thiện thay vì nhét regex/JSON phức tạp vào descriptor.

## 8. Ví dụ chạy đầy đủ: Java 17 + Maven + Hibernate Validator 8

Bài thực hành tạo một object có năm lỗi, dùng `ValidationMessages*.properties` để dịch và in cả `getMessageTemplate()` lẫn `getMessage()`. Không cần Spring context hay HTTP server.

**Để output ổn định**, ví dụ sử dụng Hibernate Validator extension `defaultLocale(...)`; đây là API provider-specific, không thuộc `jakarta.validation.Configuration<?>` chung. Nó tạo factory riêng cho hai locale để thể hiện lựa chọn ngôn ngữ rõ ràng.

### 8.1. Cấu trúc project

```text
validation-messages-demo/
├── pom.xml
└── src/main/
    ├── java/demo/ValidationMessagesDemo.java
    └── resources/
        ├── ValidationMessages.properties
        ├── ValidationMessages_vi.properties
        └── ValidationMessages_en.properties
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>validation-messages-demo</artifactId>
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

Hibernate Validator là provider, Jakarta EL hỗ trợ EL interpolation. Java 17 cho phép dùng record để trình bày constraints ngắn gọn.

### 8.3. ValidationMessages.properties (root fallback)

```properties
app.username.required=Username must not be blank
app.code.size=Code length must be between {min} and {max} characters
app.age.minimum=Age must be at least {value}
app.reference.format=Reference must have format ACCT-nnn
jakarta.validation.constraints.NotNull.message=Region must not be null
```

### 8.4. ValidationMessages_vi.properties

```properties
app.username.required=Tên đăng nhập không được để trống
app.code.size=Mã phải dài từ {min} đến {max} ký tự
app.age.minimum=Tuổi phải từ {value} trở lên
app.reference.format=Mã tham chiếu phải có dạng ACCT-nnn
jakarta.validation.constraints.NotNull.message=Khu vực không được để trống
```

### 8.5. ValidationMessages_en.properties

```properties
app.username.required=Username must not be blank
app.code.size=Code length must be between {min} and {max} characters
app.age.minimum=Age must be at least {value}
app.reference.format=Reference must have format ACCT-nnn
jakarta.validation.constraints.NotNull.message=Region must not be null
```

Chú ý `NotNull` dùng **mặc định của constraint annotation**, nhưng bản dịch bị ghi đè bằng khóa chuẩn `jakarta.validation.constraints.NotNull.message`.

### 8.6. ValidationMessagesDemo.java

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.hibernate.validator.HibernateValidator;

public class ValidationMessagesDemo {

    private static final Locale VI = Locale.forLanguageTag("vi-VN");
    private static final Locale EN = Locale.ENGLISH;

    public record Account(
        @NotBlank(message = "{app.username.required}")
        String username,

        @Size(min = 3, max = 8, message = "{app.code.size}")
        String code,

        @Min(value = 18, message = "{app.age.minimum}")
        Integer age,

        @Pattern(
            regexp = "ACCT-[0-9]{3}",
            message = "{app.reference.format}"
        )
        String reference,

        @NotNull String region
    ) {}

    private static void check(Locale locale, Account account) {
        try (ValidatorFactory factory =
                Validation.byProvider(HibernateValidator.class)
                    .configure()
                    .locales(VI, EN)
                    .defaultLocale(locale)
                    .buildValidatorFactory()) {

            Validator validator = factory.getValidator();
            Set<ConstraintViolation<Account>> violations =
                    validator.validate(account);

            List<ConstraintViolation<Account>> sorted =
                violations.stream()
                    .sorted(Comparator.comparing(
                        v -> v.getPropertyPath().toString()))
                    .toList();

            System.out.println("LOCALE=" + locale.toLanguageTag());
            for (ConstraintViolation<Account> violation : sorted) {
                System.out.println(
                    violation.getPropertyPath()
                    + " | " + violation.getMessageTemplate()
                    + " | " + violation.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        Account invalid = new Account(
            "   ",  // NotBlank
            "ab",   // Size(min=3)
            17,     // Min(18)
            "bad",  // Pattern
            null    // NotNull
        );
        check(VI, invalid);
        check(EN, invalid);
    }
}
```

`ValidatorFactory` được đóng bằng try-with-resources để giải phóng tài nguyên provider. Trong production nên tái sử dụng factory thay vì khởi tạo lại mỗi HTTP request. Mẫu này cố ý tạo hai factory để minh họa sự lựa chọn locale, không phải kiến trúc tối ưu cho web server.

### 8.7. Lệnh chạy và output dự kiến

Yêu cầu Java 17+ và Maven 3.x. Tại thư mục có `pom.xml`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.ValidationMessagesDemo
```

Các dòng từ `System.out.println`, không tính log Maven hoặc provider:

```text
LOCALE=vi-VN
age | {app.age.minimum} | Tuổi phải từ 18 trở lên
code | {app.code.size} | Mã phải dài từ 3 đến 8 ký tự
reference | {app.reference.format} | Mã tham chiếu phải có dạng ACCT-nnn
region | {jakarta.validation.constraints.NotNull.message} | Khu vực không được để trống
username | {app.username.required} | Tên đăng nhập không được để trống
LOCALE=en
age | {app.age.minimum} | Age must be at least 18
code | {app.code.size} | Code length must be between 3 and 8 characters
reference | {app.reference.format} | Reference must have format ACCT-nnn
region | {jakarta.validation.constraints.NotNull.message} | Region must not be null
username | {app.username.required} | Username must not be blank
```

Cả hai lần validation cùng phát hiện năm lỗi, nhưng câu hiển thị khác nhau. `getMessageTemplate()` giữ nguyên các khóa, còn `getMessage()` đổi theo locale và thay các attributes. `Set<ConstraintViolation<?>>` không bảo đảm thứ tự, vì vậy ví dụ sắp xếp theo property path trước khi in. Output được phân tích từ mã nguồn và bundles; nếu tùy biến provider/version/configuration, cần chạy test xác nhận.

## 9. Custom constraint với default template

Khi viết constraint riêng, convention hay dùng là tên đủ của annotation + `.message`. Ví dụ:

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = AllowedCategoryValidator.class)
public @interface AllowedCategory {
    String message() default "{demo.AllowedCategory.message}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Đây là **đoạn khai báo minh họa**, cần thêm class `AllowedCategoryValidator` hiện thực `ConstraintValidator<AllowedCategory,String>`. File top-level public annotation phải tên `AllowedCategory.java`; đoạn này không thuộc chương trình ở mục 8.

Trong bundles:

```properties
# ValidationMessages_vi.properties
demo.AllowedCategory.message=Loại hàng không được hỗ trợ
```

```properties
# ValidationMessages_en.properties
demo.AllowedCategory.message=Unsupported product category
```

Một custom validator có thể dùng `ConstraintValidatorContext#buildConstraintViolationWithTemplate(...)` để tạo template riêng khi vi phạm. Hãy dùng key/constant được kiểm soát; đừng ghép raw user input thành EL expression rồi yêu cầu interpolator xử lý.

## 10. Locale: Jakarta thuần và Spring khác nhau thế nào?

### 10.1. Jakarta Validator thuần

Khi gọi:

```java
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();
Set<ConstraintViolation<Account>> errors = validator.validate(account);
```

đây là fragment, giả định `Account` và `account` đã tồn tại. Với interpolator mặc định, nếu không chủ động truyền locale hoặc cấu hình provider, Jakarta sử dụng locale mặc định của JVM theo đặc tả. **Header HTTP `Accept-Language` không tự tác động tới một factory thuần được xây như trên.**

Không gọi `Locale.setDefault(...)` theo từng request để đổi ngôn ngữ vì nó ảnh hưởng global state và có rủi ro cạnh tranh giữa requests.

### 10.2. Spring LocalValidatorFactoryBean

Spring tích hợp Bean Validation qua `LocalValidatorFactoryBean`. Factory này thường bọc provider interpolator bằng `LocaleContextMessageInterpolator`, sử dụng `LocaleContextHolder.getLocale()`. Trong Spring MVC, request locale được xác định bằng `LocaleResolver`; vì vậy validation qua Spring-managed factory có thể dùng locale hiện tại của request.

Điều đó không có nghĩa mọi validator do ứng dụng tự tạo đều dùng locale request. Nếu gọi `Validation.buildDefaultValidatorFactory()` trong service hoặc sử dụng custom interpolator, bạn phải kiểm tra chiến lược locale tương ứng. Với xử lý bất đồng bộ, cũng phải chú ý cách truyền context phù hợp, không suy luận rằng một ThreadLocal tự đi theo mọi reactive stream.

### 10.3. Khi thông báo đã được tạo

`ConstraintViolation#getMessage()` là câu đã được nội suy **ở thời điểm validation**. Đổi locale sau khi đã gọi `validate(...)` không khiến một `ConstraintViolation` cũ tự nội suy lại. Hãy chọn locale trước validation, hoặc thiết kế giải quyết lại template có chủ đích nếu cần.

## 11. ValidationMessages.properties khác Spring messages.properties

Hai hệ thống đều có thể dùng file `.properties` nhưng khác nguồn message và cú pháp:

| Khía cạnh | Jakarta Bean Validation | Spring MessageSource |
| --- | --- | --- |
| Bundle mặc định | `ValidationMessages.properties` | `messages.properties` thường dùng |
| Chọn câu | `message="{app.code.size}"` | `getMessage(code,args,locale)` |
| Placeholder đặc trưng | `{min}`, `{value}`, `${...}` | `{0}`, `{1}` theo `MessageFormat` |
| Kết quả | `ConstraintViolation#getMessage()` | Chuỗi giải quyết từ Spring `MessageSource` |
| Locale | MessageInterpolator / provider config | Locale truyền cho MessageSource |
| Dùng chung bundle mặc định? | Không | Không |

Trong Spring MVC, `FieldError` và `ObjectError` triển khai `MessageSourceResolvable`. Khi gọi:

```java
String message = messageSource.getMessage(fieldError, locale);
```

Spring thử các codes như `NotBlank.signupForm.username`, `NotBlank.username` và `NotBlank`; default message có thể chứa câu do Bean Validation đã nội suy. Đây là tầng resolution **khác** với việc provider đọc `ValidationMessages.properties`.

### 11.1. spring.messages.basename chưa đổi tên bundle Jakarta

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

Cấu hình Spring Boot này điều khiển Spring `MessageSource`. Nó không mặc nhiên thay resource bundle tiêu chuẩn mà provider Bean Validation dùng. Nếu có cả hai tầng, hãy giữ hai bundle hoặc kết nối có chủ đích.

### 11.2. Dùng Spring MessageSource thay ValidationMessages

Spring `LocalValidatorFactoryBean` có API:

```java
setValidationMessageSource(MessageSource messageSource)
```

Ví dụ cấu hình tích hợp:

```java
@Configuration
public class ValidationConfig {

    @Bean
    public LocalValidatorFactoryBean validator(MessageSource messages) {
        LocalValidatorFactoryBean result = new LocalValidatorFactoryBean();
        result.setValidationMessageSource(messages);
        return result;
    }
}
```

Đây là **fragment Spring**, cần imports và Spring context, không là một phần của demo thuần Hibernate Validator ở mục 8. Nếu dùng trong Spring Boot, cần xác nhận đây là validator thực sự được MVC/service dùng và không tạo các bean cạnh tranh ngoài ý muốn.

Theo Spring API:

- `setValidationMessageSource(...)` kết nối một Spring MessageSource để giải quyết các constraint messages thay vì chỉ dựa vào `ValidationMessages` mặc định.
- Điểm tích hợp này yêu cầu Hibernate Validator classes liên quan tới ResourceBundleMessageInterpolator có thể truy cập.
- Không cấu hình đồng thời `setValidationMessageSource(...)` và `setMessageInterpolator(...)` rồi kỳ vọng chúng tự kết hợp.
- Spring MessageSource được dùng ở đây nên cho phép lookup **không tìm thấy key** một cách bình thường. Tránh `useCodeAsDefaultMessage=true` nếu nó biến key không tồn tại thành bản dịch và cản fallback provider.
- Template dành cho Bean Validation vẫn phải dùng cú pháp phù hợp, ví dụ `{min}` chứ không mặc nhiên `{0}` của Spring MessageFormat.

Giữ hai bộ messages riêng có thể là phương án dễ hiểu hơn nếu các yêu cầu của hệ thống không cần chia sẻ mọi key.

## 12. Tích hợp controller và message lỗi đa ngữ

Spring MVC có nhiều đường validation:

- `@Valid @RequestBody DTO` khi không có result liền sau có thể phát `MethodArgumentNotValidException`.
- `@Valid @ModelAttribute Form` có `BindingResult` ngay sau cho phép controller nhận lỗi tại chỗ.
- Direct constraints trên controller method parameters/return value ở Spring MVC 6.1+ có thể phát `HandlerMethodValidationException`.
- Service bean `@Validated` qua Spring AOP có thể phát `ConstraintViolationException` hoặc `MethodValidationException` tùy cấu hình.

Không nên format API errors bằng cách parse `exception.getMessage()`. Hãy lấy `FieldError`/`ObjectError` hoặc `ConstraintViolation` có cấu trúc, giữ machine code ổn định và dùng locale đã quyết định trước khi nội suy thông báo.

Ví dụ controller advice minh họa:

```java
@RestControllerAdvice
public class ApiValidationAdvice {

    private final MessageSource messages;

    public ApiValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<List<ApiError>> handle(
            MethodArgumentNotValidException ex, Locale locale) {

        List<ApiError> body = ex.getBindingResult()
            .getAllErrors().stream()
            .map(error -> {
                String field = error instanceof FieldError fe
                    ? fe.getField() : "";
                return new ApiError(
                    field,
                    error.getCode(),
                    messages.getMessage(error, locale));
            })
            .toList();

        return ResponseEntity.badRequest().body(body);
    }

    public record ApiError(String field, String code, String message) {}
}
```

Đây là fragment tích hợp, không phải chương trình độc lập; cần imports. Nó chỉ bắt một nhánh validation, vì vậy ứng dụng thật có thể cần xử lý các exception khác ở API boundary. Không serialize `FieldError#getRejectedValue()` khi dữ liệu có thể là password/token/PII.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thấy nguyên `{app.key}` trong message | Không tìm được key, sai bundle hoặc classpath | Kiểm tra `ValidationMessages*.properties` |
| Chỉ tạo `messages_vi.properties` nhưng không có câu từ Bean Validation | Nhầm Spring MessageSource với Jakarta bundle | Tạo `ValidationMessages_vi.properties` hoặc tích hợp chủ động |
| Luôn hiện tiếng Anh | Validator dùng default JVM locale | Kiểm tra interpolator, request Locale, Spring factory |
| Dấu tiếng Việt lỗi | Sai file encoding, resource loader hoặc artifact build | Lưu UTF-8 và test end-to-end |
| `{min}` không được thay | Sai annotation attribute hoặc interpolation không phải Jakarta | Xem descriptor và provider |
| Override key `min` làm giá trị khác 3 | Trùng key với annotation attribute | Namespace lại custom keys |
| EL hiện nguyên `${...}` | EL dependency thiếu, expression sai hoặc hạn chế provider | Kiểm tra Jakarta EL và cấu hình |
| Sau khi đổi locale, violation vẫn câu cũ | Message đã được nội suy khi validate | Chọn locale trước validation |
| Spring error code thay đổi khi đổi tên form | Tên `@ModelAttribute` thay đổi | Thiết kế fallback code/contract ổn định |
| Trả thông tin nhạy cảm trong message | Ghép raw input hoặc serialize toàn bộ lỗi | Chỉ xuất mã và thông báo an toàn |
| Mẫu `{0}` không hoạt động như mong muốn | Nhầm MessageFormat với Bean Validation params | Dùng đúng cú pháp của từng hệ thống |
| Test so sánh thứ tự Set không ổn định | Set violations không bảo đảm thứ tự | Sắp xếp theo property path trước assert |

## 14. Checklist QA

1. Kiểm tra tên bundle `ValidationMessages` viết đúng chữ hoa.
2. Xác nhận file `ValidationMessages.properties` và bản `_vi`/`_en` có trong runtime classpath.
3. Xác nhận encoding UTF-8 bằng message tiếng Việt có dấu.
4. Test `getMessageTemplate()` và `getMessage()` cho ít nhất hai locale.
5. Test `{min}`/`{max}`/`{value}` trong template.
6. Test user bundle override key built-in `jakarta.validation.constraints.NotNull.message`.
7. Nếu có custom constraint, test key `message()` mặc định.
8. Nếu dùng EL, test dependency, feature level, literal escape và tránh input không tin cậy trong template.
9. Nếu là MVC, test request `Accept-Language` qua Spring-managed validator thực.
10. Xác nhận `messages.properties` và `ValidationMessages.properties` không bị đánh đồng.
11. Nếu kết nối Spring MessageSource vào LocalValidatorFactoryBean, test key không tồn tại và fallback.
12. Không tạo một ValidatorFactory mới cho mọi request trên production.
13. Kiểm tra response không chứa raw rejected values hoặc dữ liệu nhạy cảm.
14. Giữ các translation keys nhất quán giữa mọi locale đã hỗ trợ.

## 15. Tóm tắt

**`ValidationMessages.properties` là bundle mặc định cho message interpolation của Jakarta Bean Validation.** Constraint dùng `message="{app.key}"` để lấy bản dịch theo `Locale`; nội dung bundle có thể sử dụng `{min}`, `{max}`, `{value}` hoặc EL `${...}` khi cần. `getMessageTemplate()` cung cấp descriptor ban đầu, còn `getMessage()` là câu đã nội suy.

Trong Spring, cần phân biệt Bean Validation bundle với Spring `MessageSource` và kiểm tra locale resolution của `LocalValidatorFactoryBean`. Thiết kế thông báo theo key, xử lý lỗi có cấu trúc và kiểm thử hai ngôn ngữ giúp tránh hardcode, thiếu bản dịch và không nhất quán giữa các đường validation.

## Tài liệu tham khảo

- Jakarta Bean Validation 3.0 — Message interpolation, mục 6.3: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API — `MessageInterpolator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/messageinterpolator
- Jakarta Validation API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintviolation
- Hibernate Validator 8 — Reference Guide, message interpolation, mục 4: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8 — Locale resolution (provider extension): https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-custom-locale-resolution
- Spring Framework 6.2 — `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework 6.2 — `LocaleContextMessageInterpolator`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/beanvalidation/LocaleContextMessageInterpolator.html
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot — Internationalization: https://docs.spring.io/spring-boot/reference/features/internationalization.html