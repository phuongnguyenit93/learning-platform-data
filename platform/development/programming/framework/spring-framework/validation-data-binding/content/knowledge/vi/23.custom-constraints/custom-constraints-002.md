# `message`, `groups` và `payload` của custom constraint trong Jakarta Bean Validation và Spring

## 1. Mục tiêu và bức tranh tổng thể

Khi viết một ràng buộc tùy chỉnh (custom constraint), bạn thường tạo **một annotation** như `@AllowedRegion` và **một lớp kiểm tra** triển khai `ConstraintValidator`. Theo Jakarta Validation, **mọi constraint annotation** phải có đủ ba phần tử cấu hình với kiểu và giá trị mặc định đúng quy định:

```java
String message() default "{demo.AllowedRegion.message}";
Class<?>[] groups() default {};
Class<? extends Payload>[] payload() default {};
```

Chúng trả lời ba câu hỏi khác nhau:

| Thuộc tính | Vai trò | Ai sử dụng? |
| --- | --- | --- |
| `message` | Mẫu thông báo khi constraint bị vi phạm | Message interpolator của Bean Validation và tầng trình bày |
| `groups` | Tập nhóm mà constraint thuộc về; quyết định **khi nào** ràng buộc được chọn | Validation engine khi gọi `validate(bean, groups...)` hoặc Spring `@Validated` |
| `payload` | Metadata mở rộng gắn với **constraint declaration** | Client tích hợp, code đọc `ConstraintDescriptor`; mặc định không chi phối kết quả đúng/sai |

Còn **logic đúng/sai** nằm trong `ConstraintValidator.isValid(...)`, không nằm trong ba thuộc tính này. Giá trị `false` từ `isValid` sinh ra `ConstraintViolation` với message và descriptor tương ứng; nhóm quyết định constraint có được chạy ở lượt đó hay không.

Điểm quan trọng: **annotation chỉ là metadata**. Một object mang annotation chưa tự được kiểm tra khi gọi `new`, constructor hay setter. Phải có một lượt validation như `jakarta.validation.Validator.validate(...)`, Spring MVC `@Valid`/`@Validated` tại entry point hỗ trợ, hoặc cơ chế service method validation đã cấu hình.

## 2. Định nghĩa annotation custom constraint hợp lệ

Ví dụ annotation kiểm tra mã vùng bắt đầu bằng tiền tố được cấu hình:

```java
package demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = AllowedRegionValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface AllowedRegion {

    String message() default "{demo.validation.AllowedRegion.message}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    String prefix() default "VN-";
}
```

Đây là mã cho file **`src/main/java/demo/validation/AllowedRegion.java`**; cần có lớp `AllowedRegionValidator` đúng package được trình bày tiếp theo. Những thành phần đáng chú ý:

1. `@Constraint(validatedBy = AllowedRegionValidator.class)` đánh dấu annotation là Bean Validation constraint và đăng ký implementation.
2. `@Retention(RUNTIME)` bảo đảm provider có thể đọc annotation lúc thực thi.
3. `@Target` giới hạn vị trí Java hợp lệ: field, getter/method, parameter, type argument hoặc annotation khác để composition. Chỉ khai báo những `ElementType` thực sự có ngữ nghĩa cho constraint của bạn.
4. `@Documented` để annotation hiện diện trong Javadoc của phần tử được gắn; hữu ích nhưng không phải phần thay thế cho `@Constraint`.
5. `message`, `groups`, `payload` có chữ ký **bắt buộc** theo specification.
6. `prefix` là tham số riêng của constraint; nó không phải phần tử bắt buộc do Jakarta định nghĩa. Giá trị `prefix` có thể được dùng trong validator và nội suy vào thông báo bằng `{prefix}`.

Không được đổi tên `message` thành `errorMessage` hay `payload` thành `severity` rồi bỏ ba phần tử chuẩn. Provider tìm đúng chữ ký mà đặc tả yêu cầu.

### Lớp xử lý constraint

```java
package demo.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class AllowedRegionValidator
        implements ConstraintValidator<AllowedRegion, CharSequence> {

    private String prefix;

    @Override
    public void initialize(AllowedRegion annotation) {
        prefix = annotation.prefix();
    }

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {
        return value == null || value.toString().startsWith(prefix);
    }
}
```

Lưu vào **`src/main/java/demo/validation/AllowedRegionValidator.java`**. Provider:

- Tìm validator thích hợp cho kiểu Java ở điểm đặt constraint. `String` triển khai `CharSequence`, nên được hỗ trợ.
- Gọi `initialize(annotation)` để truyền tham số bất biến của **constraint declaration** này.
- Gọi `isValid(value, context)` để kiểm tra giá trị. Ở đây `null` được chấp nhận theo quy ước của constraint kiểm tra định dạng; muốn bắt buộc có giá trị, kết hợp `@NotNull` hoặc `@NotBlank`.
- Nếu `isValid` trả `false`, dùng `message` của constraint để tạo violation.

**Không làm ba việc sai:** đừng lưu dữ liệu riêng từng request trong field mutable dùng chung của validator; đừng ném exception nghiệp vụ chỉ để báo “giá trị không hợp lệ” khi `false` là đủ; đừng cho rằng `payload` tự được truyền thành tham số `isValid`.

## 3. `message`: mẫu thông báo, không phải chính logic validation

### Kiểu bắt buộc và giá trị mặc định

Định nghĩa chuẩn:

```java
String message() default "{demo.validation.AllowedRegion.message}";
```

Giá trị là **message template**, có thể là chuỗi chữ trực tiếp hoặc key đặt trong cặp ngoặc nhọn để tra resource bundle.

Ví dụ trên model:

```java
@AllowedRegion(prefix = "VN-")
private String code1;

@AllowedRegion(
    prefix = "EU-",
    message = "Code phải bắt đầu bằng {prefix}"
)
private String code2;
```

`code1` dùng template mặc định trên annotation; `code2` ghi đè message tại **nơi sử dụng constraint**. Cả hai vẫn dùng cùng implementation `AllowedRegionValidator`, chỉ khác cấu hình/violation message.

### Resource bundle cho thông báo

Tạo file **`src/main/resources/ValidationMessages.properties`**:

```properties
demo.validation.AllowedRegion.message=Code must start with {prefix}
```

Khi `code1="US-123"`, provider thông thường:

1. Lấy message template `{demo.validation.AllowedRegion.message}`.
2. Tìm key trong `ValidationMessages.properties` của application classpath.
3. Nhận chuỗi `Code must start with {prefix}`.
4. Thay `{prefix}` bằng giá trị thuộc tính annotation `"VN-"`.
5. Sinh message cuối: `Code must start with VN-`.

Nếu `code2="US-456"`, message override có thể nội suy thành `Code phải bắt đầu bằng EU-`.

Nên dùng key đặt tên theo convention **tên đầy đủ của constraint annotation + `.message`**, ví dụ `demo.validation.AllowedRegion.message`. Khi thay package/đổi tên annotation, cập nhật key tương ứng nếu dùng convention này.

### `getMessageTemplate()` khác `getMessage()`

Với đối tượng `ConstraintViolation<?> v`:

```java
String template = v.getMessageTemplate();
String resolved = v.getMessage();
```

- `template` giữ **mẫu thông báo** của constraint declaration, ví dụ `{demo.validation.AllowedRegion.message}`.
- `resolved` là chuỗi đã qua bộ nội suy, ví dụ `Code must start with VN-`.

Sự phân biệt này giúp trả thông điệp cho người dùng đồng thời giữ key/template phục vụ log, phân loại lỗi hoặc phản hồi API có `code` riêng.

### Thông báo và quốc tế hóa

Jakarta Validation hỗ trợ giải quyết message theo locale và `MessageInterpolator`; provider thường lấy `ValidationMessages.properties`, `ValidationMessages_vi.properties`, `ValidationMessages_en.properties` theo quy tắc bundle. Khi cần locale ổn định trong một request/test, kiểm tra cách provider và Spring chọn locale thực tế. Không mặc định mọi cấu hình ứng dụng tự chuyển sang tiếng Việt chỉ vì HTTP header chứa `Accept-Language: vi`; luồng cấu hình locale/message interpolator phải tương thích.

Với Spring, `LocalValidatorFactoryBean` có thể dùng `setValidationMessageSource(MessageSource)` để tích hợp thông báo constraint với hệ thống message của Spring trong những cấu hình/provider hỗ trợ. Đừng gọi cùng lúc setter này và `setMessageInterpolator(...)` theo cách xung đột. Đồng thời phân biệt:

- **Provider interpolation:** tạo `ConstraintViolation.getMessage()` từ `message`.
- **Spring `MessageSource` / `BindingResult` error codes:** cho phép màn hình/API quyết định thông điệp và mã lỗi theo trường hoặc object.

Tức là `message` là một phần của contract Bean Validation; HTTP response hay UI mapping là tầng riêng.

### Tham số trong message và EL

`{prefix}` là tham chiếu tới **annotation attribute**, tương tự các ví dụ chuẩn với `{min}`, `{max}` của `@Size`. Một số provider hỗ trợ cú pháp Expression Language `\${...}` và tham số nội suy động; khả năng cho phép EL, đặc biệt trong **custom violation messages**, phụ thuộc provider và mức bảo vệ bảo mật. Không nối trực tiếp dữ liệu người dùng không tin cậy vào message template để bắt provider đánh giá biểu thức. Ưu tiên các key/attribute cố định và việc escape thông điệp khi hiển thị HTML.

## 4. `groups`: chọn constraint cho tình huống kiểm tra

### Chữ ký bắt buộc

```java
Class<?>[] groups() default {};
```

Array rỗng trong **định nghĩa annotation** mang ý nghĩa: khi người dùng **không ghi `groups`** tại một constraint declaration, constraint đó thuộc `jakarta.validation.groups.Default`.

Nhưng:

```java
@AllowedRegion(prefix = "VN-")
private String generalCode;
```

không phải “constraint này thuộc tất cả nhóm”. Nó thuộc **Default**, không tự chạy khi chỉ yêu cầu một group tùy chỉnh không có quan hệ kế thừa với Default.

### Khai báo marker group

```java
public interface OnCreate {}
public interface OnUpdate {}
```

Group là interface Java; không phải Spring bean, không cần `@Component`. Tại nơi áp dụng constraint:

```java
@AllowedRegion(prefix = "VN-", groups = OnCreate.class)
private String primaryCode;

@AllowedRegion(prefix = "EU-", groups = OnUpdate.class)
private String backupCode;
```

Nếu một object mang hai field này:

```java
validator.validate(object, OnCreate.class); // Chỉ chọn OnCreate.
validator.validate(object, OnUpdate.class); // Chỉ chọn OnUpdate.
validator.validate(object);                 // Chỉ Default, nếu không có cấu hình khác.
```

Hai lời gọi đầu là **đoạn trích**, giả sử `validator` là `jakarta.validation.Validator`, `object` có các field, và class/interface đã được khai báo đúng.

Một constraint có thể thuộc nhiều nhóm:

```java
@AllowedRegion(
    prefix = "VN-",
    groups = {OnCreate.class, OnUpdate.class}
)
private String serviceCode;
```

Khi yêu cầu OnCreate hoặc OnUpdate, constraint trên `serviceCode` có thể được đánh giá. Đây là cơ chế **chọn một tập ràng buộc**; không có nghĩa property được sửa đổi hoặc validation chạy tự động lúc gán field.

### Chọn nhiều group trong một lượt

```java
validator.validate(object, Default.class, OnCreate.class);
```

Đây là lời gọi **chủ động** yêu cầu cả constraint Default và OnCreate. Không giả định provider bắt buộc thực thi Default trước OnCreate; với nhóm thông thường, thứ tự kiểm tra không được bảo đảm. Nếu cần **thứ tự và dừng sớm ở cấp group**, dùng `@GroupSequence`, không dùng thứ tự tham số `validate(...)`.

### Kế thừa group

```java
public interface FullCreate extends OnCreate, Default {}
```

`validator.validate(object, FullCreate.class)` sẽ chọn constraint của `FullCreate` và các nhóm cha `OnCreate`, `Default`. Chiều ngược không đúng: gọi Default không tự chọn constraint chỉ thuộc FullCreate hoặc OnCreate.

Khi thiết kế nhóm, đặt tên theo **hành vi cần kiểm tra** (`OnCreate`, `OnUpdate`, `PublishChecks`) thay vì đặt một interface riêng cho mọi field. Một cây group quá nhiều tầng khó đọc và dễ khiến rule bị bỏ qua vì caller chọn sai nhóm.

### `@GroupSequence` không phải `groups`

```java
@GroupSequence({Default.class, OnCreate.class})
public interface OrderedCreate {}
```

`validator.validate(object, OrderedCreate.class)` chạy Default trước; nếu Default có violation, nhóm OnCreate không được chạy trong sequence. Không dùng interface sequence làm group gắn trực tiếp vào `groups` của constraint. Một sequence có luật tránh vòng và một số quy tắc đặc biệt khi redefinition Default ở cấp class.

Đối với validation bình thường, `groups` giải thích **quy tắc nào được chọn**; `GroupSequence` giải thích **thứ tự nào được thực thi**.

## 5. `payload`: metadata mở rộng, không thay đổi kết quả `isValid`

### Chữ ký bắt buộc

```java
Class<? extends Payload>[] payload() default {};
```

`Payload` là interface marker `jakarta.validation.Payload`. Ứng dụng định nghĩa các loại metadata riêng bằng interface/class thực thi `Payload`.

Ví dụ phân loại mức độ:

```java
public final class Severity {
    private Severity() {}

    public interface Info extends Payload {}
    public interface Warning extends Payload {}
    public interface Error extends Payload {}
}
```

Đây là class minh họa, cần import `jakarta.validation.Payload`. Gắn vào constraint declaration:

```java
@AllowedRegion(
    prefix = "VN-",
    groups = OnCreate.class,
    payload = Severity.Error.class
)
private String primaryCode;
```

**Lưu ý cú pháp:** `payload` nhận **class**, ví dụ `Severity.Error.class`, không phải `new Severity.Error()` và không phải một string như `"ERROR"`. Có thể truyền nhiều payload marker bằng `payload = {Severity.Warning.class, Severity.Error.class}`.

### Đọc payload qua `ConstraintDescriptor`

Một violation `v` có metadata:

```java
Set<Class<? extends Payload>> payloadTypes =
        v.getConstraintDescriptor().getPayload();

boolean isError = payloadTypes.contains(Severity.Error.class);
```

Đây là đoạn trích giả định các import, marker và `v` đã có. Các thông tin khác từ descriptor:

```java
String annotationName =
        v.getConstraintDescriptor()
         .getAnnotation()
         .annotationType()
         .getSimpleName();

Object configuredPrefix =
        v.getConstraintDescriptor()
         .getAttributes()
         .get("prefix");
```

`ConstraintDescriptor.getAttributes()` cung cấp metadata phần tử annotation tại declaration; `getPayload()` trả **tập các class payload**, không phải payload object thay đổi theo từng lượt validation.

Các mục đích client có thể dùng payload: quyết định severity trong UI; đánh dấu lỗi mang tính khuyến nghị; phân loại cho logging/audit; chọn hình thức xử lý downstream theo chính sách đã thiết kế. Tuy nhiên **Bean Validation chuẩn không tự diễn giải `Severity.Error` thành HTTP 400, `Severity.Info` thành warning hay bỏ qua violation**.

### Phân biệt payload metadata và hành vi nghiệp vụ

| Trường hợp | Có tự diễn ra vì `payload` không? |
| --- | --- |
| `Severity.Error` làm `isValid()` chạy thêm một lần | Không |
| `Severity.Info` biến một `false` thành `true` | Không |
| `Severity.Warning` tự bỏ lỗi khỏi `Validator.validate()` | Không |
| `Severity.Error` tự sinh HTTP 422 trong Spring MVC | Không |
| Client đọc severity qua `getPayload()` rồi áp policy riêng | Có, **nếu ứng dụng tự viết code đó** |
| Provider trả payload của constraint declaration trong descriptor | Có, theo metadata API |

Ngay cả khi ứng dụng gọi một lỗi là “warning”, nó vẫn là `ConstraintViolation` khi validator trả `false`. Nếu muốn cảnh báo không chặn request, bạn phải thiết kế cơ chế riêng hoặc dùng logic khác; **không** nên dựa vào payload để tin rằng Hibernate Validator sẽ tự thay đổi kết quả.

### Payload chuẩn đặc biệt: `Unwrapping.Unwrap` và `Unwrapping.Skip`

Một ngoại lệ đối với tính “metadata chỉ do client xử lý” là hai payload được Jakarta Validation định nghĩa để kiểm soát **value unwrapping**:

```java
@NotBlank(payload = Unwrapping.Unwrap.class)
private Optional<String> code;
```

Đoạn này cần import `java.util.Optional`, `jakarta.validation.constraints.NotBlank` và `jakarta.validation.valueextraction.Unwrapping`; với extractor thích hợp, `Unwrap` yêu cầu kiểm tra phần tử trong container. `Unwrapping.Skip` buộc không unwrap trong những trường hợp có unwrap ngầm.

Đừng gắn nhầm loại payload này như severity bình thường: nó có ngữ nghĩa chuẩn do validation engine hiểu. Đồng thời đừng nhầm `payload()` của constraint annotation với các khả năng “dynamic payload” riêng của Hibernate Validator hoặc với Spring `Payload` trong những thư viện khác. Chúng không phải cùng một contract.

## 6. Phân biệt ba giá trị được khai báo và những gì provider thực thi

Giả sử một DTO có:

```java
@NotBlank(message = "name is required")
private String name;

@AllowedRegion(
    prefix = "VN-",
    groups = OnCreate.class,
    payload = Severity.Error.class
)
private String primaryCode;

@AllowedRegion(
    prefix = "EU-",
    message = "backup needs {prefix}",
    groups = OnUpdate.class,
    payload = Severity.Info.class
)
private String backupCode;
```

Giả sử cả ba giá trị đều sai:

| Group yêu cầu | Constraint được chọn | Message dự kiến |
| --- | --- | --- |
| `Default` | `@NotBlank` trên `name` | `name is required` |
| `OnCreate` | `@AllowedRegion` trên `primaryCode` | Từ bundle cho prefix `VN-` |
| `OnUpdate` | `@AllowedRegion` trên `backupCode` | `backup needs EU-` |
| `Default, OnCreate` | Cả `name` và `primaryCode` | Hai violation độc lập |
| `FullCreate extends Default, OnCreate` | Hai constraint như trên | Hai violation độc lập |

Vì `payload` chỉ là metadata, việc một declaration được gắn `Severity.Info` không loại nó khỏi tập vi phạm khi OnUpdate được kiểm tra.

## 7. Ví dụ hoàn chỉnh chạy bằng Java 17 và Spring Boot

Ví dụ dùng **một source Java** cho annotation, validator, model và runner để có thể sao chép thử nghiệm nhanh, và một `ValidationMessages.properties` để kiểm tra thật việc nội suy message. Ngoài ví dụ học tập, dự án production nên tách annotation/validator/DTO ra các class riêng.

Cấu trúc:

```text
custom-constraint-demo/
├── pom.xml
└── src/main/
    ├── java/demo/ConstraintMetadataDemo.java
    └── resources/ValidationMessages.properties
```

### 7.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>custom-constraint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` cung cấp Jakarta Validation integration và provider Hibernate Validator tương thích qua dependency management của Spring Boot. Ví dụ này không cần Spring MVC; `ApplicationRunner` gọi `jakarta.validation.Validator` trực tiếp.

### 7.2. `src/main/resources/ValidationMessages.properties`

```properties
demo.AllowedRegion.message=code must start with {prefix}
```

Giữ nguyên key và chữ thường như ví dụ để các dòng output dễ kiểm tra. Key ở đây được lựa chọn **tường minh**; nếu chuyển annotation sang package/class khác, bạn có thể đổi nó về convention FQN của annotation và cập nhật resource tương ứng.

### 7.3. `src/main/java/demo/ConstraintMetadataDemo.java`

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.Default;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConstraintMetadataDemo {

    public interface OnCreate {}
    public interface OnUpdate {}

    public interface FullCreate extends Default, OnCreate {}

    public static final class Severity {
        private Severity() {}

        public interface Info extends Payload {}
        public interface Error extends Payload {}
    }

    @Documented
    @Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = AllowedRegionValidator.class)
    public @interface AllowedRegion {
        String message() default "{demo.AllowedRegion.message}";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
        String prefix() default "VN-";
    }

    public static final class AllowedRegionValidator
            implements ConstraintValidator<AllowedRegion, CharSequence> {

        private String prefix;

        @Override
        public void initialize(AllowedRegion annotation) {
            prefix = annotation.prefix();
        }

        @Override
        public boolean isValid(
                CharSequence value, ConstraintValidatorContext context) {
            return value == null || value.toString().startsWith(prefix);
        }
    }

    public static final class Registration {
        @NotBlank(message = "name required")
        private final String name;

        @AllowedRegion(
            prefix = "VN-",
            groups = OnCreate.class,
            payload = Severity.Error.class
        )
        private final String primaryCode;

        @AllowedRegion(
            prefix = "EU-",
            groups = OnUpdate.class,
            message = "backup needs {prefix}",
            payload = Severity.Info.class
        )
        private final String backupCode;

        public Registration(
                String name, String primaryCode, String backupCode) {
            this.name = name;
            this.primaryCode = primaryCode;
            this.backupCode = backupCode;
        }
    }

    public static void main(String[] args) {
        SpringApplication.run(ConstraintMetadataDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(Validator validator) {
        return args -> {
            Registration invalid =
                    new Registration("", "US-101", "US-202");

            show("Default", validator, invalid, Default.class);
            show("Create", validator, invalid, OnCreate.class);
            show("Update", validator, invalid, OnUpdate.class);
            show("FullCreate", validator, invalid, FullCreate.class);

            ConstraintViolation<Registration> createViolation =
                    validator.validate(invalid, OnCreate.class)
                             .iterator()
                             .next();

            System.out.println("Message template: "
                    + createViolation.getMessageTemplate());

            System.out.println("Prefix attribute: "
                    + createViolation.getConstraintDescriptor()
                                     .getAttributes()
                                     .get("prefix"));

            System.out.println("Severity Error: "
                    + createViolation.getConstraintDescriptor()
                                     .getPayload()
                                     .contains(Severity.Error.class));

            System.out.println("Severity Info: "
                    + createViolation.getConstraintDescriptor()
                                     .getPayload()
                                     .contains(Severity.Info.class));
        };
    }

    static void show(
            String label, Validator validator,
            Registration value, Class<?>... groups) {

        Set<ConstraintViolation<Registration>> violations =
                validator.validate(value, groups);

        String details = violations.stream()
                .map(v -> v.getPropertyPath().toString()
                        + "=" + v.getMessage())
                .sorted()
                .collect(Collectors.joining("; "));

        System.out.println(label + " (" + violations.size() + "): "
                + (details.isEmpty() ? "OK" : details));
    }
}
```

Các class/annotation được khai báo **`static` bên trong public class** và các import đều đủ, nên ví dụ chỉ cần một file Java. `AllowedRegionValidator` có public no-arg constructor ngầm định và có thể được provider/Spring tạo ra.

### 7.4. Chạy và kết quả

Với JDK 17+ và Maven đã cài, chạy:

```bash
mvn spring-boot:run
```

Bên cạnh log khởi động thông thường của Spring Boot, chương trình in các dòng sau:

```text
Default (1): name=name required
Create (1): primaryCode=code must start with VN-
Update (1): backupCode=backup needs EU-
FullCreate (2): name=name required; primaryCode=code must start with VN-
Message template: {demo.AllowedRegion.message}
Prefix attribute: VN-
Severity Error: true
Severity Info: false
```

**Vì sao?**

- `name=""` không đạt `@NotBlank`, nhưng constraint đó chỉ thuộc Default, nên kết quả `Default` có 1 lỗi.
- `primaryCode="US-101"` không bắt đầu bằng `VN-`. Nó thuộc nhóm OnCreate, nên kết quả `Create` có 1 lỗi. Message mặc định được nội suy qua file `ValidationMessages.properties`.
- `backupCode="US-202"` không bắt đầu bằng `EU-`. Nó thuộc nhóm OnUpdate; annotation override `message = "backup needs {prefix}"`, nên kết quả `Update` dùng thông điệp khác.
- `FullCreate extends Default, OnCreate` chọn cả constraint Default và OnCreate, tạo 2 lỗi. Kết quả được sort nên phần hiển thị ổn định dù `Set<ConstraintViolation>` không bảo đảm thứ tự.
- `getMessageTemplate()` trả nguyên mẫu khai báo của constraint trên `primaryCode`; `getMessage()` đã được nội suy ra thông điệp thực.
- `getAttributes().get("prefix")` lấy tham số riêng `"VN-"` của annotation.
- `getPayload()` chứa marker `Severity.Error.class` do chính declaration trên `primaryCode` ghi, không chứa `Severity.Info.class`.

**Nếu đổi `primaryCode` thành `"VN-101"`**, Create không còn violation. Khi không có violation, ví dụ không được phép gọi `iterator().next()` trên tập rỗng; trong production, luôn kiểm tra `violations.isEmpty()` trước khi đọc phần tử. Tập violation cũng không có thứ tự ổn định; ở đây việc dùng `next()` an toàn vì nhóm OnCreate chỉ tạo đúng một violation với input mẫu.

### 7.5. Điểm đáng học từ chương trình

Chỉ một annotation `@AllowedRegion` có thể được tái sử dụng nhiều lần với các giá trị `prefix`, `message`, `groups`, `payload` khác nhau. Implementation `isValid` không cần biết nhóm hiện tại hoặc severity. Provider lựa chọn **declaration đang tham gia lượt validation**, tạo validator phù hợp rồi gắn descriptor của declaration vào violation khi kiểm tra thất bại.

Lưu ý demo minh họa hành vi đúng theo Jakarta Validation/Spring Boot và có thể chạy bằng các lệnh nêu trên; khi chuyển sang project khác, hãy kiểm tra version, dependency, classpath và application configuration thực tế.

## 8. `groups` trong Spring MVC: `@Valid` khác `@Validated`

Một phương thức REST minh họa:

```java
@PostMapping("/registrations")
public ResponseEntity<?> register(
        @Validated(OnCreate.class)
        @RequestBody RegistrationRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                errors.getFieldErrors().stream()
                      .map(e -> e.getField() + ": "
                              + e.getDefaultMessage())
                      .toList());
    }
    return ResponseEntity.ok().build();
}
```

Đây là **method minh họa trong Spring MVC**, không phải class standalone. Cần `@RestController`, các import `org.springframework.validation.annotation.Validated`, `org.springframework.validation.BindingResult`, `@PostMapping`, `@RequestBody`, `ResponseEntity`, DTO có constraint và group `OnCreate`.

Ở những entry point Spring MVC hỗ trợ, `@Validated(OnCreate.class)` yêu cầu validation DTO với **OnCreate**. Nếu DTO có constraint thuộc Default nhưng không thuộc OnCreate, nó **không tự được chọn**, trừ khi group được yêu cầu kế thừa Default hoặc có quy tắc đặc biệt khác.

Nếu chỉ viết:

```java
public ResponseEntity<?> register(
        @Valid @RequestBody RegistrationRequest request) {
    // ...
}
```

thì `@Valid` thông thường yêu cầu validation của **Default group**, không tương đương `@Validated(OnCreate.class)`. `BindingResult` phải nằm ngay sau tham số cần nhận lỗi trong chữ ký có hỗ trợ; nếu không, Spring MVC thường chuyển lỗi validation của object argument thành exception (ví dụ `MethodArgumentNotValidException`). Method-level validation với constraint trực tiếp trên tham số có thể có cơ chế/exception khác theo Spring version.

**Không kỳ vọng Spring MVC tự chọn group theo HTTP method.** POST không tự chọn `OnCreate`, PUT không tự chọn `OnUpdate`. Bạn phải định nghĩa contract và annotation/validator call phù hợp.

### Trả payload ra JSON?

Spring `BindingResult` thường mang `FieldError`, error code và message đã thích ứng từ Bean Validation. Không giả định Spring tự chuyển `payload = Severity.Error.class` thành field `severity` trong response.

Nếu API cần severity, xây dựng một cơ chế mapping tường minh từ `ConstraintViolation.getConstraintDescriptor().getPayload()` hoặc từ error contract của riêng ứng dụng. Đặc biệt, không dùng payload tùy ý để tự quyết định HTTP status ở cấp toàn request khi một response có thể chứa nhiều violation thuộc các mức severity khác nhau mà chưa có chính sách ưu tiên được định nghĩa.

## 9. `groups` với Spring service method validation

Có hai cách nhìn:

- **Validate object trực tiếp:** inject `jakarta.validation.Validator`, gọi `validator.validate(bean, OnCreate.class)`. Chủ động và dễ test.
- **Validate method parameters:** dùng Spring method-validation infrastructure cho Spring-managed bean, thường với `@Validated` ở cấp type và `MethodValidationPostProcessor`/auto-configuration tương ứng. Interceptor sẽ yêu cầu provider kiểm tra constraint theo nhóm được cấu hình.

Ví dụ service minh họa:

```java
@Service
@Validated(OnCreate.class)
public class RegistrationService {
    public void register(@Valid RegistrationRequest request) {
        // ...
    }
}
```

Đoạn này cần import Spring và Jakarta cùng các class liên quan. Nó không chạy tự động khi `new RegistrationService()`, khi Spring method validation chưa được bật hoặc khi lời gọi nội bộ `this.register(...)` bỏ qua proxy. Đừng xem annotation như một biện pháp duy nhất để bảo vệ nghiệp vụ khỏi mọi code path.

Tại service boundary, có thể tốt hơn nếu validate explicit để kiểm soát rõ nhóm nào áp dụng, đặc biệt với batch jobs, message consumers, scheduled tasks hoặc code không đi qua MVC.

## 10. `payload` và phân loại severity trong quy trình kiểm thử

Giả sử ứng dụng dùng hai marker:

```java
public interface Warning extends Payload {}
public interface Error extends Payload {}
```

Một field thuộc constraint `@AllowedRegion(..., payload=Warning.class)` mà sai dữ liệu **vẫn** sinh `ConstraintViolation`. Code xử lý phía client có thể đọc:

```java
for (ConstraintViolation<?> v : violations) {
    var p = v.getConstraintDescriptor().getPayload();
    String level = p.contains(Error.class) ? "ERROR"
                 : p.contains(Warning.class) ? "WARNING"
                 : "UNSPECIFIED";
    System.out.println(level + ": " + v.getMessage());
}
```

Đây là đoạn minh họa dựa trên `violations`, `Error`, `Warning` đã khai báo và import phù hợp. Logic chọn severity nằm **trong ứng dụng**, không được API Jakarta Validation thực hiện thay.

Với audit/logging, chỉ log dữ liệu cần thiết; hạn chế in trực tiếp `getInvalidValue()` vì có thể chứa token, email, thông tin tài chính hoặc bí mật. Severity không phải bảo đảm rằng một giá trị sai có thể được xử lý an toàn; chính sách tiếp nhận/từ chối dữ liệu phải được xác định riêng.

Để test payload không bị mất, dùng assertion trên descriptor:

```java
assertTrue(violation.getConstraintDescriptor()
        .getPayload().contains(Severity.Error.class));
```

Đây là JUnit snippet, cần `assertTrue` và `violation` hợp lệ. Nếu chỉ muốn kiểm tra metadata mà không cần tạo dữ liệu sai, dùng metadata API `Validator.getConstraintsForClass(...)` để tìm `PropertyDescriptor` và các `ConstraintDescriptor` của property tương ứng, sau đó đọc `getPayload()` và `getAttributes()`.

## 11. Tùy chỉnh thông báo ngay trong `ConstraintValidatorContext`

`message` trên annotation là **mẫu mặc định**. Khi một trường hợp lỗi có thông tin chi tiết mà không thể diễn đạt chỉ bằng `prefix`, implementation có thể tạo custom violation:

```java
@Override
public boolean isValid(
        String value, ConstraintValidatorContext context) {

    if (value == null || value.startsWith(prefix)) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
                "Invalid region prefix")
           .addConstraintViolation();

    return false;
}
```

Đây là **phần method minh họa** dùng trong một class `ConstraintValidator<AllowedRegion, String>` có field `prefix` đã khởi tạo. Nó thay thông điệp mặc định bằng một thông điệp riêng. Nếu bạn gọi `disableDefaultConstraintViolation()`, phải xây dựng ít nhất một violation tùy chỉnh trước khi trả `false`; nếu không, provider có thể ném `ValidationException` do không còn violation nào được mô tả.

Có thể thêm property node qua `addPropertyNode("field")` đối với **class-level constraint** để gắn lỗi vào field cụ thể. Điều đó là một bước khác với thay đổi `message`, và phải bảo đảm đường dẫn property đúng, không bịa field không tồn tại.

Trong Hibernate Validator có API bổ sung như `HibernateConstraintValidatorContext.addMessageParameter(...)`; đó là extension của provider, không phải lúc nào cũng di động giữa các Jakarta Validation provider. Với message template từ input không tin cậy, chú ý khả năng EL injection; mặc định một số provider hạn chế EL trong custom violations vì lý do an toàn.

## 12. Khi nào nên tạo `message` key thay vì literal?

| Bối cảnh | Cách phù hợp | Lý do |
| --- | --- | --- |
| Hệ thống đa ngôn ngữ | `message() default "{app.constraint.SomeRule.message}"` | Định tuyến qua resource bundle theo locale |
| Library dùng lại nhiều dự án | Key theo FQN annotation + `.message` | Ít va chạm và dễ ghi đè |
| Demo nội bộ ngắn | Literal như `"must start with {prefix}"` | Dễ hiểu mà không cần tài nguyên |
| Một use case cần message khác | Ghi đè `message = "..." ` tại vị trí constraint | Không phải tạo annotation mới |
| Client cần mã lỗi ổn định | Thiết kế `errorCode` riêng hoặc mapping từ constraint | Message dịch theo locale không nên đóng vai trò error code duy nhất |
| Test message | Truyền/chọn locale hoặc dùng chuỗi cố định có chủ đích | Tránh test thất bại do locale/bundle thay đổi |

Thông báo lỗi nên mô tả **vi phạm** chứ không lộ dữ liệu nhạy cảm. Nếu rule mang tham số (min/max/prefix), dùng tham số nội suy có kiểm soát thay vì nhân bản hàng chục message giống nhau.

## 13. Metadata API: đọc cả `message`, `groups`, `payload` mà chưa validate

`Validator` có API metadata để inspect constraint declarations. Ví dụ với class `Registration` trong demo:

```java
var beanDescriptor =
        validator.getConstraintsForClass(Registration.class);

var propertyDescriptor =
        beanDescriptor.getConstraintsForProperty("primaryCode");

for (var descriptor : propertyDescriptor.getConstraintDescriptors()) {
    System.out.println(descriptor.getMessageTemplate());
    System.out.println(descriptor.getGroups());
    System.out.println(descriptor.getPayload());
    System.out.println(descriptor.getAttributes().get("prefix"));
}
```

Đây là đoạn minh họa với `validator` đã khởi tạo. Trong môi trường production cần null-check `propertyDescriptor` nếu property không có constraint. `ConstraintDescriptor` cho phép phân tích tập nhóm, payload, phần tử đặc biệt, annotation thực và metadata constraint.

**Một khác biệt kỹ thuật:** đọc descriptor không thực thi `isValid` và không tạo `ConstraintViolation`. Metadata API hữu ích cho tài liệu hóa quy tắc, hỗ trợ tạo UI từ constraint hoặc kiểm tra cấu hình, nhưng không thay thế bước validation dữ liệu thực tế.

Với custom constraint, `getAttributes()` chứa `prefix`, `message`, `groups`, `payload` và các phần tử annotation tùy chỉnh theo quy tắc API. Đối với `ConstraintDescriptor.getGroups()`, giá trị thuộc `Default` theo contract có thể được phản ánh ngay cả khi `groups()` tại annotation definition mặc định là array rỗng. Không tự suy luận rằng `groups() default {}` nghĩa là constraint thuộc “không có group nào”.

## 14. Vì sao không được thay chữ ký bắt buộc?

Theo Jakarta Validation specification, các phần tử `message`, `groups`, `payload` là **reserved names** với kiểu/default chuẩn; `validationAppliesTo` là reserved name bổ sung cho trường hợp constraint vừa generic vừa cross-parameter. Tên phần tử annotation bắt đầu bằng `valid` cũng bị cấm.

Bảng lỗi khai báo:

| Khai báo | Vấn đề |
| --- | --- |
| Không có `message()` | Thiếu phần tử bắt buộc |
| `int message() default 0;` | Sai kiểu; phải là `String` |
| `Class<?> groups() default Default.class;` | Sai kiểu; phải là mảng `Class<?>[]` |
| `Class<?>[] groups() default {OnCreate.class};` | Sai default của phần tử group; theo chuẩn phải là `{}` |
| `Class<? extends Payload>[] payload() default {Severity.Error.class};` | Sai default; theo chuẩn phải là `{}` |
| `String payload() default "ERROR";` | Sai kiểu và ý nghĩa |
| `@Retention(CLASS)` | Metadata không được lưu với retention RUNTIME theo yêu cầu |
| Bỏ `@Constraint` | Không còn được coi là Bean Validation constraint |
| Dùng `String validReason()` | Tên phần tử bắt đầu `valid` bị cấm theo constraint definition |
| `@Constraint(validatedBy=...) ` trỏ đến validator sai type | Có thể phát sinh lỗi chọn validator, ví dụ `UnexpectedTypeException` |

Trong Java, một số khai báo annotation sai kiểu không compile ngay (ví dụ default trả class không tương thích); nhưng một số lỗi là **lỗi định nghĩa constraint ở runtime**, thường thấy dưới dạng `ConstraintDefinitionException`. Đừng chỉ dựa vào việc `javac` thành công để kết luận ràng buộc hợp lệ. Thêm integration test gọi `validator.validate(...)` hoặc đọc metadata của custom constraint để phát hiện lỗi cấu hình sớm.

## 15. Đừng gắn `groups` hoặc `payload` lên `ConstraintValidator`

Một lỗi thiết kế thường gặp là nghĩ provider sẽ dùng class validator để quyết định group/severity:

```java
// Không phải cơ chế lựa chọn nhóm theo Jakarta Validation:
public class RegionValidator
        implements ConstraintValidator<AllowedRegion, String> {
    // Không có annotation groups/payload bắt buộc trên class này.
}
```

Đây là đoạn minh họa, không cần áp dụng `@Validated` hay marker severity lên `ConstraintValidator` để hoạt động. **Group và payload nằm tại constraint declaration**, tức annotation được gắn vào field/getter/type/parameter cụ thể.

Nếu custom logic cần biết `prefix`, dùng `initialize(annotation)` để đọc tham số riêng đã được khai báo. Nếu logic cần biết một policy nghiệp vụ phức tạp, nên inject service hoặc chọn constraint phù hợp với policy đó. Không dựa vào `payload` để tự động điều khiển hành vi provider: API chuẩn không bảo đảm rằng `ConstraintValidator.isValid` được truyền severity payload như một tham số.

## 16. Constraint composition: ba thuộc tính của constraint bao ngoài

Jakarta Validation cho phép tạo **composed constraint** từ nhiều constraint khác. Ví dụ:

```java
@NotBlank
@Size(min = 3, max = 16)
@Constraint(validatedBy = {})
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE,
    ElementType.PARAMETER,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface ShortDisplayName {

    String message() default "invalid display name";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Đây là **annotation minh họa**, cần import `jakarta.validation.Constraint`, `@NotBlank`, `@Size`, `Payload`, `java.lang.annotation.*` và đặt thành file `ShortDisplayName.java`. Composed constraint với `validatedBy={}` vẫn hợp lệ vì logic đến từ các composing constraints.

**Quy tắc quan trọng:** khi các constraint lồng được cấu thành từ annotation bao ngoài, `groups` và `payload` của composing constraints được kế thừa từ **main constraint declaration** theo quy tắc composition, không thể đơn giản đặt group khác lên từng annotation con để mong chúng chạy độc lập.

Nếu thêm `@ReportAsSingleViolation` vào annotation bao ngoài, một lỗi trong composing constraints có thể được báo thành **một violation mang message của main constraint**, thay vì nhiều violation riêng; đây là cách chủ động thay đổi hình thức báo lỗi, không phải chức năng của `payload`.

Đối với composed constraints phức tạp, các `@OverridesAttribute` và `value()` cho phép chuyển tham số xuống constraint thành phần, nhưng nên chỉ sử dụng khi việc tái sử dụng mang lại lợi ích rõ ràng. Không ép một constraint đơn giản trở thành composition khó debug.

## 17. Kết hợp `message`, `groups`, `payload` với kiểm tra lồng nhau

Xét DTO:

```java
public final class CheckoutRequest {
    @NotNull
    @Valid
    private Address deliveryAddress;

    @AllowedRegion(
        prefix = "VN-",
        groups = OnCreate.class,
        payload = Severity.Error.class
    )
    private String regionCode;
}
```

Đây là model minh họa, cần class `Address`, imports và các group/marker như phần trước. Nếu `Address` có field `@NotBlank String city`, thì:

- `@Valid` **không phải constraint**; nó bảo provider cascade vào object con nếu validation thực sự diễn ra.
- Nếu `Address` null, `@NotNull` trên field `deliveryAddress` phát hiện giá trị thiếu trong nhóm Default.
- Nếu yêu cầu chỉ `OnCreate` mà không có quan hệ kế thừa/sequence tới Default, constraint `@NotNull` mặc định ở `deliveryAddress` có thể không được chọn.
- Payload gắn trên `regionCode` không tự “lan” sang constraints của `Address`. Mỗi constraint declaration có metadata riêng của nó.
- Group `OnCreate` có thể được truyền qua cascade theo quy tắc Jakarta Validation; khi cần đổi group ở đường cascade, dùng `@ConvertGroup` hợp lệ, không lạm dụng `payload`.

Khi lồng collection hoặc `Optional`, type-use annotations và value extractors quyết định giá trị nào được kiểm tra. Nhóm được chọn vẫn điều khiển constraint, còn payload vẫn mô tả declaration. Ba trục này độc lập nhưng cùng xuất hiện trên một lượt validation.

## 18. Kiểm thử từng trục một cách độc lập

Viết test riêng giúp biết lỗi ở đâu:

| Test | Ý định | Điều cần xác nhận |
| --- | --- | --- |
| Message default | Không override `message` | `getMessageTemplate()` là key; `getMessage()` là kết quả nội suy |
| Message override | Ghi `message` tại field | Provider dùng template override |
| Attribute interpolation | Đổi `prefix` | Nội dung `{prefix}` thay đúng theo từng declaration |
| Default group | `validate(bean)` | Chỉ constraint mặc định và các quy tắc group liên quan |
| OnCreate group | `validate(bean, OnCreate.class)` | Chỉ các constraint thuộc group được chọn/kế thừa |
| Multiple groups | `validate(bean, Default.class, OnCreate.class)` | Tập violation là hợp nhất phù hợp, không dựa vào thứ tự |
| Payload | `getConstraintDescriptor().getPayload()` | Marker `Severity.Error.class` có trong tập nếu declaration ghi nó |
| Payload independence | Chuyển severity Error thành Info | `isValid` vẫn kiểm tra giá trị như trước |
| Unsupported type | Gắn constraint chuỗi lên `Integer` | Phát hiện lỗi cấu hình/validator resolution |
| Spring MVC | `@Validated(OnCreate.class)` ở DTO parameter | MVC kích hoạt đúng group và phản hồi lỗi theo contract |
| Spring service | Gọi qua managed bean/interceptor | Method validation thực sự chạy |
| Locale | Tra resource bundle `_vi`/`_en` | Message đúng locale, không nhầm với error code |

Ví dụ JUnit 5 snippet với model trong chương trình:

```java
@Test
void onCreateKeepsErrorPayload() {
    var input = new Registration("Mai", "US-101", "EU-123");

    var errors = validator.validate(input, OnCreate.class);

    assertEquals(1, errors.size());
    var v = errors.iterator().next();

    assertEquals("primaryCode", v.getPropertyPath().toString());
    assertEquals("code must start with VN-", v.getMessage());
    assertTrue(v.getConstraintDescriptor()
                .getPayload()
                .contains(Severity.Error.class));
}
```

Đây là **method test minh họa**, không phải file test độc lập. Cần JUnit 5, instance `validator` từ Spring context, các static imports cho assertions, và class `Registration`, `OnCreate`, `Severity` đúng package/import. Để dùng với class nested trong demo, tham chiếu qua `ConstraintMetadataDemo.Registration`, `ConstraintMetadataDemo.OnCreate`, `ConstraintMetadataDemo.Severity` hoặc static imports thích hợp.

`Set<ConstraintViolation>` **không bảo đảm thứ tự**. Với nhiều lỗi, assert bằng tập path/message hoặc sort trước khi so sánh. Test không nên so sánh thứ tự hai nhóm nếu không có group sequence tương ứng.

## 19. Quy trình xử lý sự cố

Khi custom constraint không hoạt động đúng, kiểm tra theo thứ tự:

1. **Định nghĩa có đúng chuẩn?** Annotation có `@Constraint`, `@Retention(RUNTIME)`, `message`/`groups`/`payload` đúng kiểu và default `{}`?
2. **Validator match kiểu?** Nếu class `AllowedRegionValidator` hỗ trợ `CharSequence`, đừng gắn lên `Integer` rồi kỳ vọng tự chuyển thành chuỗi.
3. **Provider đã có chưa?** Chỉ API mà không có implementation sẽ không thực thi đúng. Với Boot thường dùng starter validation tương thích.
4. **Có lượt validation thật chưa?** Annotation không tự chạy lúc gọi constructor hoặc setter.
5. **Đúng group chưa?** `@Valid` thường chọn Default, `@Validated(OnCreate.class)` chọn OnCreate; group không mặc định chứa Default.
6. **Message bundle tồn tại?** Key phải đúng, file ở classpath, locale hợp lệ; phân biệt `getMessageTemplate()` và `getMessage()`.
7. **Attribute có tên đúng?** `{prefix}` phải khớp element `prefix()` được khai báo, không phải tên field Java bất kỳ.
8. **Payload được đọc ở nơi phù hợp?** `getPayload()` trên descriptor; Spring `FieldError` không mặc nhiên phơi severity ra JSON.
9. **Custom message override?** Nếu `isValid` xây một violation riêng và disable default, kiểm tra builder, node và message template của violation đã tạo.
10. **Spring DI có được dùng?** Với `LocalValidatorFactoryBean`, `SpringConstraintValidatorFactory` thường cho phép inject dependency vào `ConstraintValidator`; một `Validation.buildDefaultValidatorFactory()` độc lập có thể không dùng cùng factory.
11. **Có cấu hình XML/composition ghi đè không?** Metadata có thể bị thay đổi/compose theo quy tắc provider; đọc `ConstraintDescriptor` để biết declaration thực tế.
12. **Message là nội dung để hiển thị, không phải security boundary:** escaping và xử lý lỗi HTTP vẫn là trách nhiệm ứng dụng.

### Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `ConstraintDefinitionException` | Thiếu/sai chữ ký của `message`, `groups`, `payload` | Làm đúng định nghĩa chuẩn |
| `UnexpectedTypeException` | Không có validator hỗ trợ kiểu field | Đổi kiểu/constraint hoặc viết validator phù hợp |
| Message hiện `{app...message}` | Không có key trong bundle hoặc key sai | Kiểm tra `ValidationMessages.properties`, classpath, locale |
| `{prefix}` không thay | Mẫu/key/thuộc tính không khớp hoặc custom interpolator | Kiểm tra annotation element và cấu hình interpolation |
| `@Valid` không kiểm tra OnCreate | OnCreate không phải Default | Dùng `@Validated(OnCreate.class)`/explicit validator |
| Payload không xuất hiện trong HTTP response | Spring không tự serialize marker metadata | Ánh xạ lỗi theo contract API riêng |
| Gắn Warning mà request vẫn fail | Warning vẫn là violation khi `isValid` trả false | Định nghĩa lại policy tại tầng ứng dụng |
| Provider không gọi validator | Không có trigger hoặc group không được chọn | Kiểm tra entry point và group |
| Có hai lỗi giống nhau do tự viết composition | Đặt constraint trùng, compose không mong muốn | Rà composing constraints và `@ReportAsSingleViolation` |
| Method validation service không chạy | Thiếu proxy/integration, gọi self-invocation hoặc dùng `new` | Kiểm tra Spring-managed bean và post-processor |
| Test bị khác message sau đổi locale | Test phụ thuộc locale mặc định | Cố định locale/message hoặc assert template/code |

## 20. Câu hỏi tự kiểm tra

**1. Custom constraint annotation phải có ba element nào?**  
`String message() default ...`, `Class<?>[] groups() default {}`, `Class<? extends Payload>[] payload() default {}`.

**2. `groups() default {}` nghĩa là constraint không thuộc group nào?**  
Không. Nếu không chỉ định group tại declaration, constraint thuộc `Default`.

**3. `@AllowedRegion(groups=OnCreate.class)` tự chạy lúc tạo DTO không?**  
Không. Phải gọi validation với OnCreate hoặc có integration point chọn nhóm phù hợp.

**4. `message()` mặc định là `"{demo.AllowedRegion.message}"`: text trong ngoặc nhọn là gì?**  
Thông thường là key được tìm trong resource bundle và nội suy theo quy tắc của provider.

**5. `getMessage()` và `getMessageTemplate()` có giống nhau không?**  
Không. Một cái là message đã nội suy, một cái là template gốc của violation.

**6. `payload=Severity.Warning.class` có tự làm constraint trở thành non-blocking không?**  
Không. Nó là metadata; `isValid` và group quyết định violation, ứng dụng quyết định cách xử lý.

**7. Muốn đọc severity từ một violation nên gọi đâu?**  
`violation.getConstraintDescriptor().getPayload()`.

**8. `Severity.Warning` có phải interface group dùng với `@Validated` không?**  
Không. Group và payload là hai contract độc lập; một marker `extends Payload` không tự là group nghiệp vụ được chọn.

**9. `prefix()` có thể được tham chiếu trong message thế nào?**  
Đặt `{prefix}` trong template; provider nội suy từ annotation attribute tương ứng.

**10. `@GroupSequence` và `payload` có thay nhau được không?**  
Không. Group sequence sắp thứ tự đánh giá nhóm; payload mô tả metadata.

**11. Payload nào trong chuẩn có ảnh hưởng trực tiếp đến việc unwrap container?**  
`Unwrapping.Unwrap` và `Unwrapping.Skip`, theo hợp đồng value extraction của Jakarta Validation.

**12. Vì sao cần tách test cho group, message và payload?**  
Vì một constraint có thể chạy đúng nhưng chọn sai group, nội suy message sai hoặc thiếu marker metadata; mỗi trục có nguyên nhân lỗi khác nhau.

## 21. Kết luận

Khi thiết kế custom constraint, **`message` cho biết sẽ thông báo thế nào**, **`groups` chỉ định lượt kiểm tra nào chọn constraint**, và **`payload` mang metadata cho client tích hợp**. Ba phần tử có kiểu và giá trị mặc định cố định theo Jakarta Validation, trong khi `ConstraintValidator.isValid` giữ trách nhiệm kiểm tra dữ liệu.

Một constraint tốt cần có hợp đồng type rõ, thông báo có thể nội suy/quốc tế hóa, nhóm được chọn có chủ đích, payload chỉ được diễn giải ở tầng mong muốn, và các test xác minh **từng trục riêng biệt**. Trong Spring, hãy kiểm tra integration point dùng `@Valid`, `@Validated`, `LocalValidatorFactoryBean` hoặc lời gọi `jakarta.validation.Validator`; không đánh đồng “đã có annotation” với “đã thực hiện validation”.

## Tài liệu tham khảo chính thức

- Jakarta Validation 3.1 — Constraint definition, mandatory `message`/`groups`/`payload`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 API — `@Constraint`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/Constraint.html
- Jakarta Validation 3.1 API — `ConstraintDescriptor`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ConstraintDescriptor.html
- Jakarta Validation 3.1 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ConstraintViolation.html
- Hibernate Validator Reference Guide — Custom constraints and payloads: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/
- Spring Framework Reference — Java Bean Validation và custom constraint: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring MVC validation configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Framework Reference — Controller validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
