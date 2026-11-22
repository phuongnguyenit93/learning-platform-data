# Phân biệt tính năng chuẩn với mở rộng riêng của provider trong Spring Validation

## 1. Vì sao cần phân biệt?

Trong ứng dụng Spring, hai đoạn mã sau đều có thể chạy khi dự án sử dụng **Hibernate Validator**:

```java
@NotNull
@Min(18)
private Integer age;
```

và:

```java
@Range(min = 18, max = 65)
private Integer age;
```

Nhưng chúng **không có cùng mức độ độc lập với thư viện**:

- `@NotNull`, `@Min` là constraint thuộc **Jakarta Validation**; mọi provider tương thích với phiên bản Jakarta Validation đang sử dụng phải hỗ trợ hợp đồng chuẩn của chúng.
- `@Range` nằm trong package `org.hibernate.validator.constraints`; đó là **mở rộng của Hibernate Validator**, không được Jakarta Validation đặc tả. Nếu đổi sang provider khác, code có thể không biên dịch vì thiếu annotation, hoặc provider mới không biết cách thực thi ràng buộc đó.
- Spring Framework đứng ở **lớp tích hợp**: nhận dữ liệu, kích hoạt validation, chuyển các violation thành lỗi binding/API. Spring không biến một tính năng riêng của Hibernate Validator thành tính năng chuẩn của Jakarta Validation.

Sự phân biệt này quan trọng khi thiết kế thư viện dùng chung, module có nhiều consumer, nâng cấp Spring Boot hoặc đổi provider. Đối với ứng dụng đã chọn Hibernate Validator lâu dài, sử dụng extension có chủ đích có thể hợp lý; điều cần tránh là **hiểu nhầm extension thành hợp đồng có tính di động**.

Bài học tập trung vào ba câu hỏi:

1. Phần nào được Jakarta Validation chuẩn hóa?
2. Phần nào chỉ hoạt động nhờ một provider cụ thể?
3. Spring liên kết hai phần đó như thế nào và làm sao kiểm tra mức độ phụ thuộc?

Các ví dụ sử dụng Java 17+, Jakarta Validation 3.0, Spring Framework 6 / Spring Boot 3 và Hibernate Validator 8.x. Với dự án mới dùng phiên bản khác, kiểm tra lại ma trận tương thích trước khi áp dụng.

## 2. Ba tầng cần tách rõ

```text
Ứng dụng / Spring MVC / Spring Service
        |
        | @Valid, @Validated, BindingResult, LocalValidatorFactoryBean
        v
Jakarta Validation API / specification
        |
        | Validator, ValidatorFactory, @Constraint,
        | @NotNull, @Size, @Valid, ConstraintValidator...
        v
Provider thực thi hợp đồng
        |
        +-- Hibernate Validator
        |     + tính năng tiêu chuẩn
        |     + extension riêng: fail-fast, @Range, DSL mapping...
        |
        +-- Provider tương thích khác
              + tính năng tiêu chuẩn
              + có thể có extension riêng khác
```

### 2.1. Specification/API: quy ước chung

**Jakarta Validation** định nghĩa annotation, interface, hành vi phải tuân thủ và cơ chế bootstrap. Những package điển hình:

- `jakarta.validation`: `Validation`, `Validator`, `ValidatorFactory`, `ConstraintValidator`, `ConstraintViolation`, `Valid`, `GroupSequence`.
- `jakarta.validation.constraints`: `NotNull`, `NotBlank`, `NotEmpty`, `Size`, `Min`, `Max`, `Pattern`, `Email`, `Positive`, `Past`, v.v.
- `jakarta.validation.metadata`: metadata constraint.
- `jakarta.validation.executable`: kiểm tra tham số, kết quả phương thức và constructor.
- `jakarta.validation.valueextraction`: SPI trích xuất giá trị bên trong container.

Import từ các package này thường thể hiện rằng đoạn mã dựa vào **hợp đồng chuẩn**. Tuy nhiên, một annotation do ứng dụng tự viết trong package riêng vẫn có thể là **portable custom constraint** nếu chỉ dùng các interface chuẩn và một logic kiểm tra portable.

### 2.2. Provider: hiện thực hóa hợp đồng

**Hibernate Validator** là một implementation của Jakarta Validation, có thư viện và package riêng như:

```java
org.hibernate.validator.HibernateValidator
org.hibernate.validator.HibernateValidatorConfiguration
org.hibernate.validator.constraints.Range
org.hibernate.validator.constraints.Length
org.hibernate.validator.constraints.UniqueElements
org.hibernate.validator.constraintvalidation.HibernateConstraintValidatorContext
```

Provider chịu trách nhiệm tìm constraint, khởi tạo validator, kiểm tra object graph, nội suy thông báo và tạo `ConstraintViolation`. Jakarta Validation cho phép chọn provider qua SPI; dùng `Validation.buildDefaultValidatorFactory()` không có nghĩa là provider chắc chắn là Hibernate Validator nếu classpath có nhiều implementation.

Một thư viện có thể vừa là **implementation đúng chuẩn**, vừa cung cấp **API mở rộng**. Do đó đừng đồng nhất tên “Hibernate Validator” với “chỉ tính năng riêng”: phần lớn những gì nó làm là thực thi Jakarta Validation.

**Hibernate Validator và Hibernate ORM là hai thành phần khác nhau.** Không bắt buộc dùng Hibernate ORM/JPA mới chạy được Hibernate Validator; API validation có thể dùng trong ứng dụng web, CLI hoặc job xử lý dữ liệu.

### 2.3. Spring: lớp tích hợp, không phải một Jakarta Validation provider khác

Spring có các thành phần như:

- `@Valid`: annotation **chuẩn Jakarta** dùng để yêu cầu validation/cascade ở các điểm tích hợp.
- `@Validated`: annotation **của Spring** (`org.springframework.validation.annotation.Validated`), thường hỗ trợ nhóm validation và các điểm tích hợp Spring.
- `org.springframework.validation.Validator`: giao diện validator **của Spring**, khác với `jakarta.validation.Validator` dù cùng tên đơn giản.
- `BindingResult`, `FieldError`, `ObjectError`: biểu diễn lỗi ở lớp Spring binding.
- `LocalValidatorFactoryBean`: adapter/bridge giữa Jakarta Validation và hệ sinh thái Spring.
- `spring-boot-starter-validation`: dependency tiện dụng của Spring Boot, thường đưa Hibernate Validator lên classpath.

Tích hợp của Spring có thể chọn/cấu hình provider; nó không định nghĩa ý nghĩa mới cho `@Min`, cũng không bảo đảm mọi extension Hibernate Validator sẽ chạy với provider khác.

## 3. Bảng nhận diện: chuẩn, provider, Spring

| Tính năng/API | Thuộc về | Khả năng chuyển provider | Ghi chú |
| --- | --- | --- | --- |
| `@NotNull`, `@Size`, `@Min`, `@Max`, `@Email` | Jakarta Validation | Cao | Hợp đồng được đặc tả; kiểm thử các trường hợp biên |
| `@NotBlank`, `@NotEmpty` | Jakarta Validation 2.0+ | Cao trên provider tương thích | Tài liệu cũ có thể mô tả chúng là extension |
| `@Valid` và cascading validation | Jakarta Validation | Cao | Phải có điểm kích hoạt validation |
| `List<@NotBlank String>` và container element constraints | Jakarta Validation 2.0+ | Cao nếu provider hỗ trợ đúng phiên bản | Custom container có thể cần `ValueExtractor` |
| `@GroupSequence`, validation groups | Jakarta Validation | Cao | Trình tự nhóm tĩnh có chuẩn |
| `@ReportAsSingleViolation` | Jakarta Validation | Cao | Một báo cáo cho composed constraint; **không phải** extension Hibernate |
| `@Constraint`, `ConstraintValidator` | Jakarta Validation | Cao | Portable nếu logic/metadata chỉ dùng chuẩn |
| `ValidatorFactory`, `Validator`, `ConstraintViolation` | Jakarta Validation | Cao | Implementation thực tế đến từ provider |
| `MessageInterpolator`, `ClockProvider`, `ValueExtractor` | Jakarta Validation | Cao | SPI chuẩn, provider có thể có implementation riêng |
| `@Range`, `@Length`, `@UniqueElements` | Hibernate Validator | Thấp | Constraint bổ sung của provider |
| `@ConstraintComposition(OR)` | Hibernate Validator | Thấp | Toán tử OR/ALL_FALSE là extension |
| `@GroupSequenceProvider` | Hibernate Validator | Thấp | Chọn Default group sequence động |
| `failFast(true)`, `hibernate.validator.fail_fast` | Hibernate Validator | Thấp | Dừng sau vi phạm đầu tiên; thứ tự không bảo đảm |
| Fluent `ConstraintMapping` | Hibernate Validator | Thấp | Khai báo constraint bằng DSL chương trình |
| `HibernateConstraintValidatorContext` | Hibernate Validator | Thấp | Message parameter, expression variable, dynamic payload |
| `@Validated`, `BindingResult`, `LocalValidatorFactoryBean` | Spring | Phụ thuộc Spring | Là integration API, không phải provider extension |

“Khả năng chuyển provider cao” **không có nghĩa mọi implementation sẽ phát sinh message và thứ tự vi phạm giống hệt**. Nội dung bản dịch, thứ tự của `Set<ConstraintViolation<?>>`, chi tiết thuật toán `@Email` hoặc tối ưu hiệu năng có thể khác; test nghiệp vụ nên dựa vào điều kiện, đường dẫn và mã lỗi ổn định.

## 4. Cách nhận diện ngay trong code và dependency

### 4.1. Xem import thay vì đoán theo tên annotation

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.ConstraintValidator;
```

Đây là API chuẩn Jakarta. Đoạn dưới sử dụng extension:

```java
import org.hibernate.validator.constraints.Range;
import org.hibernate.validator.constraints.UniqueElements;
import org.hibernate.validator.HibernateValidator;
```

Import `org.springframework.validation.annotation.Validated` là **phụ thuộc Spring**, không phải Jakarta và cũng không phải một API extension của Hibernate Validator.

Không đủ để kết luận dựa trên chữ “Hibernate” trong tên dependency: ứng dụng có thể dùng Hibernate Validator hoàn toàn qua API Jakarta và không bị khóa vào extension nào.

### 4.2. Tìm cấu hình riêng

Cấu hình có khóa như:

```properties
hibernate.validator.fail_fast=true
```

là vendor-specific. Phương thức `Configuration#addProperty(String, String)` là **cơ chế tiêu chuẩn** nhưng ý nghĩa khóa `hibernate.validator.fail_fast` là hợp đồng của **Hibernate Validator**. Khi đổi provider, provider mới có thể bỏ qua hoặc không hiểu khóa này; không thể mặc nhiên cho rằng nó có cơ chế tương đương.

Tương tự, `Validation.byProvider(HibernateValidator.class)` chọn provider cụ thể. Trong khi đó, `Validation.buildDefaultValidatorFactory()` và `Validation.byDefaultProvider()` là API bootstrap chuẩn.

### 4.3. Kiểm tra classpath và phiên bản

Ví dụ với Gradle, `spring-boot-starter-validation` thường tự mang Hibernate Validator và Jakarta Validation API. Khi cần thêm riêng Hibernate Validator:

- Giữ version do Spring Boot BOM quản lý trừ khi có lý do kiểm chứng để override.
- Tránh kéo đồng thời các phiên bản Jakarta API không tương thích hoặc trộn `javax.validation.*` với `jakarta.validation.*`.
- Nếu package extension xuất hiện trong source, hãy ghi rõ dependency và version baseline, đừng giả định mọi module tiêu thụ đều có nó.

Đối với Spring Boot 3.x, source sử dụng `jakarta.validation.*`. Các tutorial thời Spring Boot 2.x dùng `javax.validation.*` có thể sai namespace trên classpath mới.

## 5. Ví dụ runnable: cùng quy tắc, hai cách bootstrap

Ví dụ này dùng **cùng một DTO khai báo toàn annotation chuẩn**, sau đó validation bằng:

1. `Validation.buildDefaultValidatorFactory()` — bootstrap API chuẩn.
2. `Validation.byProvider(HibernateValidator.class).configure().failFast(true)` — bật một extension Hibernate Validator.

Điều muốn quan sát là **hợp đồng dữ liệu không đổi**, nhưng số lỗi thu được có thể khác do cấu hình của provider.

### 5.1. Gradle và môi trường

Tạo Spring Boot 3.3.x với Java 17. Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` đưa API và implementation Hibernate Validator vào dự án. Ví dụ chủ động sử dụng Hibernate Validator 8.x theo dependency management của Spring Boot 3.3; để dùng provider khác sẽ phải điều chỉnh runtime dependencies.

### 5.2. Ứng dụng hoàn chỉnh

Tệp `src/main/java/com/example/validationdemo/ValidationComparisonApplication.java`:

```java
package com.example.validationdemo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.hibernate.validator.HibernateValidator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationComparisonApplication implements CommandLineRunner {

    public record Candidate(
            @NotNull String name,
            @Min(18) int age
    ) {}

    public static void main(String[] args) {
        SpringApplication.run(ValidationComparisonApplication.class, args);
    }

    @Override
    public void run(String... args) {
        Candidate invalid = new Candidate(null, 16);

        // Chỉ sử dụng API chuẩn để bootstrap và validate.
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            int count = factory.getValidator()
                    .validate(invalid)
                    .size();

            System.out.println("Standard API violations: " + count);
        }

        // Chọn Hibernate Validator và dùng API failFast riêng.
        try (ValidatorFactory factory =
                Validation.byProvider(HibernateValidator.class)
                        .configure()
                        .failFast(true)
                        .buildValidatorFactory()) {

            int count = factory.getValidator()
                    .validate(invalid)
                    .size();

            System.out.println("Hibernate fail-fast violations: " + count);
        }
    }
}
```

Chạy:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Ngoài banner và log Spring Boot, hai dòng do chương trình `println` tạo ra sẽ là:

```text
Standard API violations: 2
Hibernate fail-fast violations: 1
```

Giải thích:

- `Candidate.name == null` vi phạm `@NotNull`.
- `Candidate.age == 16` vi phạm `@Min(18)`.
- Mặc định, validator trong ví dụ báo **hai violation**.
- Với `failFast(true)`, Hibernate Validator dừng sau **vi phạm đầu tiên**, báo một violation. **Không được dựa vào việc đó là lỗi `name` hay `age`** vì provider không cam kết thứ tự đánh giá constraint.
- Mặc dù dùng API chuẩn ở nhánh đầu, provider thực tế trong classpath ví dụ vẫn thường là **Hibernate Validator**. Tên “Standard API” nói về **hợp đồng gọi**, không chứng minh ứng dụng đang chạy bằng provider khác.
- Lớp demo cố ý import `HibernateValidator` để trình diễn extension. Nếu mục tiêu là module độc lập với provider, chỉ phần DTO và nhánh bootstrap chuẩn nên nằm trong core module; phần Hibernate-specific phải ở adapter/config riêng.

**Không tạo `ValidatorFactory` trong mỗi HTTP request.** Ví dụ mở/đóng hai factory để so sánh; trong ứng dụng Spring thực tế, sử dụng validator factory/`LocalValidatorFactoryBean` do container quản lý. Factory thường cache metadata và có thể chia sẻ giữa các luồng.

## 6. Tự viết constraint portable thay cho annotation riêng

Giả sử cần một mã SKU chỉ gồm chữ in hoa ASCII và chữ số. Hibernate Validator có nhiều constraint bổ sung, nhưng một custom constraint dùng API Jakarta chuẩn giúp chia sẻ quy tắc mà không phụ thuộc annotation provider.

### 6.1. Annotation `@UppercaseSku`

Tệp `src/main/java/com/example/validationdemo/UppercaseSku.java`:

```java
package com.example.validationdemo;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target({ElementType.FIELD, ElementType.PARAMETER,
         ElementType.ANNOTATION_TYPE, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = UppercaseSkuValidator.class)
public @interface UppercaseSku {
    String message() default "SKU chỉ gồm chữ A-Z và số 0-9";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Annotation chỉ dùng `jakarta.validation.Constraint` và `Payload`. Ba thuộc tính `message`, `groups`, `payload` là hợp đồng chuẩn cho custom constraint; có thể gắn trên field, parameter hoặc record component.

### 6.2. Logic `ConstraintValidator`

Tệp `src/main/java/com/example/validationdemo/UppercaseSkuValidator.java`:

```java
package com.example.validationdemo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class UppercaseSkuValidator
        implements ConstraintValidator<UppercaseSku, String> {

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        // Để @NotNull hoặc @NotBlank xử lý trường thiếu.
        return value == null || value.matches("[A-Z0-9]+");
    }
}
```

Có thể dùng trên DTO:

```java
package com.example.validationdemo;

import jakarta.validation.constraints.NotBlank;

public record ProductRequest(
        @NotBlank @UppercaseSku String sku
) {}
```

Ví dụ hành vi:

| Giá trị | `@UppercaseSku` | `@NotBlank` | Hợp lệ tổng thể |
| --- | --- | --- | --- |
| `"ABC12"` | Đạt | Đạt | Có |
| `"ab12"` | Không đạt | Đạt | Không |
| `""` | Không đạt | Không đạt | Không |
| `null` | Đạt | Không đạt | Không |

Validator này **portable ở mức API Jakarta**, bởi nó không import các kiểu `org.hibernate.validator.*`. Việc bảo đảm chạy được trên provider khác còn phụ thuộc provider đó hỗ trợ đúng spec và các kiểu/annotation mà ứng dụng khai báo.

Lưu ý quan trọng: chuỗi regex trên chỉ chấp nhận bảng chữ **ASCII**, phù hợp với giả định SKU ở ví dụ; không tự mở rộng thành “mọi chữ hoa Unicode”. Nếu nghiệp vụ cần một chuẩn mã phức tạp hơn, điều chỉnh regex/thuật toán và test rõ ràng.

### 6.3. Custom violation cấp field cũng có API chuẩn

Nếu annotation đặt cấp lớp và muốn gắn lỗi vào một trường, dùng cơ chế Jakarta:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "{booking.checkOut.invalid}")
    .addPropertyNode("checkOut")
    .addConstraintViolation();
return false;
```

Đây là đoạn **minh họa bên trong `ConstraintValidator#isValid`**, không phải chương trình độc lập. `buildConstraintViolationWithTemplate`, `addPropertyNode` và `addConstraintViolation` là API Jakarta; không cần ép kiểu sang `HibernateConstraintValidatorContext` chỉ để đặt đường dẫn lỗi.

**Thực hành:** Nếu một yêu cầu được giải quyết trọn vẹn bằng `ConstraintValidatorContext` chuẩn, hãy chọn API chuẩn trước. Chỉ dùng extension khi cần khả năng thực sự không có trong chuẩn.

## 7. Những extension Hibernate Validator hay gặp

### 7.1. Constraint có sẵn nhưng không chuẩn

Ví dụ:

```java
import org.hibernate.validator.constraints.Length;
import org.hibernate.validator.constraints.Range;
import org.hibernate.validator.constraints.UniqueElements;

public class VendorRequest {

    @Length(min = 4, max = 20)
    String nickname;

    @Range(min = 18, max = 65)
    int age;

    @UniqueElements
    java.util.List<String> tags;
}
```

Đây là **đoạn minh họa để nhận diện API**, không phải lời khuyên thay mọi ràng buộc chuẩn bằng extension.

So sánh:

- `@Length(min = 4, max = 20)` có thể thay bằng `@Size(min = 4, max = 20)` trên `CharSequence` nếu đúng cùng ý nghĩa nghiệp vụ.
- `@Range(min = 18, max = 65)` có thể biểu diễn bằng `@Min(18)` và `@Max(65)` cho những kiểu số được các annotation chuẩn hỗ trợ. **Số thông báo và metadata** có thể khác khi đổi cách viết.
- `@UniqueElements` kiểm tra các phần tử trong collection không trùng theo `equals()`. Jakarta Validation không có annotation chuẩn cùng tên; cần custom constraint portable hoặc kiểm tra nghiệp vụ riêng nếu muốn bỏ phụ thuộc.

Không thể đánh giá khả năng thay thế chỉ bằng tên annotation: phải xét **null semantics, kiểu được hỗ trợ, thông báo, groups, phản hồi API và behavior trên giá trị biên**.

### 7.2. Fail-fast

Hibernate Validator hỗ trợ:

```java
ValidatorFactory factory =
        Validation.byProvider(HibernateValidator.class)
                .configure()
                .failFast(true)
                .buildValidatorFactory();
```

Cũng có thể cấu hình qua `hibernate.validator.fail_fast=true` (khóa riêng của Hibernate Validator). Fail-fast giúp dừng sớm khi chỉ quan tâm “có lỗi hay không”; không phù hợp nếu frontend cần **toàn bộ lỗi của biểu mẫu** để người dùng sửa trong một lần.

**Phân biệt với group sequence chuẩn:** `@GroupSequence` cho phép chạy nhóm theo trình tự xác định và dừng trước nhóm kế tiếp khi nhóm hiện tại có vi phạm. Nó **không tương đương fail-fast**, vì trong một nhóm vẫn có thể có nhiều violation; đổi một tính năng thành tính năng kia sẽ thay đổi logic báo lỗi.

### 7.3. Constraint composition: AND chuẩn, OR riêng

Jakarta Validation cho phép tạo composed constraint bằng cách gắn nhiều constraint lên annotation mới. Theo hợp đồng chuẩn, các thành phần được kết hợp theo logic **AND**. `@ReportAsSingleViolation` cũng thuộc Jakarta và dùng để gom kết quả báo lỗi.

Hibernate Validator cung cấp thêm:

```java
import org.hibernate.validator.constraints.ConstraintComposition;
import org.hibernate.validator.constraints.CompositionType;

@ConstraintComposition(CompositionType.OR)
```

Đây chỉ là các dòng then chốt của một composed constraint, **không phải annotation hoàn chỉnh**. `CompositionType.OR` cho phép một trong các điều kiện thỏa; `CompositionType.ALL_FALSE` diễn đạt logic khác theo extension. Provider khác không bắt buộc hiểu chúng. Đừng nhầm `@ReportAsSingleViolation` (chuẩn) với `@ConstraintComposition` (Hibernate-specific) chỉ vì chúng thường xuất hiện cạnh nhau.

### 7.4. Default group sequence động

Chuẩn Jakarta cung cấp `@GroupSequence` cho **thứ tự nhóm được khai báo tĩnh**. Hibernate Validator bổ sung `@GroupSequenceProvider` và `DefaultGroupSequenceProvider<T>` để chọn trình tự nhóm mặc định theo **trạng thái của object**.

Ví dụ nghiệp vụ: hồ sơ ở trạng thái nháp chỉ cần nhóm kiểm tra tối thiểu; khi chuyển sang gửi duyệt phải thêm nhóm kiểm tra chi tiết. Hãy cân nhắc:

- Nếu danh sách nhóm được quyết định từ **luồng gọi**, có thể dùng `validator.validate(bean, SomeGroup.class)` hoặc `@Validated(SomeGroup.class)` tại boundary.
- Nếu bắt buộc định nghĩa sequence động dựa vào trạng thái object và dùng extension Hibernate, bọc logic và viết test rõ ràng.
- Khi di chuyển sang provider khác, `@GroupSequenceProvider` không được Jakarta bảo đảm; cần thiết kế lại cách chọn nhóm.

### 7.5. Programmatic constraint mapping

Jakarta Validation hỗ trợ annotation, XML mapping chuẩn và các hook bootstrap qua `jakarta.validation.Configuration`. Hibernate Validator có thêm fluent DSL:

```java
import jakarta.validation.Validation;
import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.HibernateValidatorConfiguration;
import org.hibernate.validator.cfg.ConstraintMapping;
import org.hibernate.validator.cfg.defs.NotNullDef;

HibernateValidatorConfiguration configuration =
        Validation.byProvider(HibernateValidator.class).configure();

ConstraintMapping mapping = configuration.createConstraintMapping();
mapping.type(Product.class)
       .field("sku")
       .constraint(new NotNullDef());

try (var factory =
        configuration.addMapping(mapping).buildValidatorFactory()) {
    var validator = factory.getValidator();
    // validator.validate(new Product(...))
}
```

Đây là **đoạn cấu hình minh họa**, giả sử project đã khai báo class `Product` với field `sku`. Không phải chương trình độc lập. Các class `ConstraintMapping`, `NotNullDef` và API `createConstraintMapping()`/`addMapping(ConstraintMapping)` là extension Hibernate Validator.

Fluent mapping hữu ích khi constraint phụ thuộc metadata/cấu hình ứng dụng hay khi muốn bổ sung rule bên ngoài source DTO. Đổi provider có thể buộc chuyển sang annotation, XML mapping chuẩn, custom provider adapter hoặc cách cấu hình riêng khác.

### 7.6. Dynamic payload, message parameter và context mở rộng

Jakarta Validation chuẩn có:

```java
ConstraintValidatorContext context;
context.buildConstraintViolationWithTemplate(
        "{app.invalid}").addConstraintViolation();
```

Hibernate Validator cung cấp thêm:

```java
import org.hibernate.validator.constraintvalidation
        .HibernateConstraintValidatorContext;

HibernateConstraintValidatorContext hvContext =
        context.unwrap(HibernateConstraintValidatorContext.class);

hvContext.addMessageParameter("limit", 5);
hvContext.disableDefaultConstraintViolation();
hvContext.buildConstraintViolationWithTemplate(
        "Giá trị vượt ngưỡng {limit}")
    .addConstraintViolation();
```

Đây là **đoạn bên trong `isValid` của custom validator**. `{limit}` ở ví dụ không đến từ annotation mà được extension `addMessageParameter` bổ sung. Nếu dùng provider khác, `unwrap(HibernateConstraintValidatorContext.class)` có thể không thành công.

Hibernate Validator còn có:

- `addExpressionVariable(...)` để đưa biến vào Expression Language (EL) khi cơ chế EL phù hợp được bật;
- `withDynamicPayload(...)` để gắn dữ liệu tùy ý vào violation; bên đọc phải dùng API Hibernate Validator để lấy payload;
- `getConstraintValidatorPayload(...)` để đọc cấu hình payload được truyền vào validator. **Constraint-validator payload** dùng để điều khiển việc kiểm tra khác với **dynamic payload** đi kèm violation;
- điều khiển EL cho custom violation; các tính năng này yêu cầu hiểu giới hạn an toàn của EL.

Đừng nhầm `payload()` kiểu `Class<? extends jakarta.validation.Payload>[]` trên annotation **chuẩn Jakarta** với dynamic payload extension của Hibernate Validator. Chúng giải quyết các mục tiêu khác nhau.

## 8. Spring sử dụng provider như thế nào?

Trong Spring MVC, cách kích hoạt thông dụng:

```java
@PostMapping("/candidates")
public ResponseEntity<Void> create(
        @Valid @RequestBody CandidateRequest request) {
    return ResponseEntity.noContent().build();
}
```

Đoạn trên là **minh họa phương thức controller** với các import `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.*` và `org.springframework.http.ResponseEntity`. Nếu DTO chứa `@NotNull`, `@Size` và custom constraint portable, controller không cần biết provider bên dưới. Spring MVC/Jakarta Validation thực hiện kiểm tra sau khi binding; lỗi có thể được biểu diễn qua `BindingResult` hoặc xử lý exception tùy kiểu tham số/phương thức.

### 8.1. LocalValidatorFactoryBean là điểm tích hợp

`LocalValidatorFactoryBean` trong Spring Framework là cầu nối giữa:

- `jakarta.validation.Validator`/`ValidatorFactory` ở phía Jakarta;
- `org.springframework.validation.Validator` và các cơ chế binding của Spring.

Nó cho phép cấu hình provider, message interpolator, constraint validator factory và một số SPI tiêu chuẩn. Điều đó **không biến** `@Range` hay `failFast(true)` thành Jakarta API.

Nếu dự án Spring Boot đã có `spring-boot-starter-validation` và không cần tùy chỉnh, phần lớn trường hợp nên dùng cấu hình tự động. Tạo thêm một `LocalValidatorFactoryBean` hoặc factory độc lập tùy tiện có thể khiến controller và service sử dụng **hai validator khác cấu hình**.

### 8.2. Hai interface tên Validator không giống nhau

```java
jakarta.validation.Validator
org.springframework.validation.Validator
```

- `jakarta.validation.Validator#validate(bean, groups...)` trả `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.Validator#validate(Object, Errors)` ghi lỗi vào `Errors`/`BindingResult` và có `supports(Class<?>)`.
- `LocalValidatorFactoryBean` tích hợp hai thế giới đó.

Đừng đặt tên biến `validator` rồi mặc nhiên áp dụng method của interface còn lại. Khi debug, dùng **fully-qualified package** để xác minh loại instance được inject.

### 8.3. @Validated của Spring và groups của Jakarta

`@Validated` là annotation Spring, nhưng concept **validation groups** là Jakarta Validation. Ví dụ:

```java
public interface OnCreate {}

public record CandidateRequest(
    @NotNull(groups = OnCreate.class)
    String name
) {}
```

Ở boundary Spring, `@Validated(OnCreate.class)` có thể kích hoạt nhóm đó trong ngữ cảnh phù hợp. Nếu gọi Jakarta API thuần, dùng `validator.validate(bean, OnCreate.class)`. Hai cách cùng dựa vào groups **chuẩn**; chỉ cách kích hoạt qua Spring annotation là Spring-specific.

Một lưu ý về method validation: Spring MVC hiện đại và AOP method validation có thể đi qua các cơ chế khác nhau. Không giả định mọi lỗi đều xuất hiện dưới cùng một exception hoặc luôn được validate chỉ vì có annotation trên DTO.

### 8.4. Cấu hình property riêng trong Spring

Nếu muốn bật `hibernate.validator.fail_fast` qua Spring/Jakarta configuration, cần coi đó là một quyết định gắn với **Hibernate Validator**. `LocalValidatorFactoryBean` có thể nhận validation properties từ ứng dụng; **tên và ý nghĩa property không thuộc Jakarta spec**.

Nếu thay provider, phải xem lại khóa cấu hình, loại exception, bản dịch message, các nhóm và logic phản hồi. Không dựa vào việc ứng dụng vẫn khởi động để suy ra provider mới đã áp dụng cài đặt tương đương.

## 9. Bootstrap, unwrap và khả năng thay provider

### 9.1. Bootstrap chuẩn

```java
try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {
    var validator = factory.getValidator();
    var violations = validator.validate(bean);
}
```

Đây là đoạn minh họa giả sử có biến `bean`. Những kiểu `Validation`, `ValidatorFactory` và method `validate` thuộc chuẩn Jakarta. Provider được phát hiện bằng cơ chế SPI, thường qua `META-INF/services/jakarta.validation.spi.ValidationProvider`.

Nếu **không có provider**, `buildDefaultValidatorFactory()` có thể ném `NoProviderFoundException`. Nếu có nhiều provider trên classpath, đừng dựa vào một thứ tự chọn provider không được bảo đảm; hãy chọn provider tường minh khi hành vi thực thi phải cố định.

### 9.2. Chọn provider cụ thể

```java
try (ValidatorFactory factory =
        Validation.byProvider(HibernateValidator.class)
                .configure()
                .buildValidatorFactory()) {
    // Provider được chọn rõ là Hibernate Validator.
}
```

Bản thân method `Validation.byProvider(...)` là cơ chế bootstrap **chuẩn**; tham số `HibernateValidator.class` là class cụ thể của provider. Đây là điểm coupling có chủ đích.

### 9.3. Unwrap là cơ chế chuẩn nhưng kết quả có thể không portable

```java
var hvFactory = factory.unwrap(
        org.hibernate.validator.HibernateValidatorFactory.class);
```

Method `unwrap(Class<T>)` thuộc Jakarta. Kiểu đích `HibernateValidatorFactory` là Hibernate-specific. Khi đang chạy provider không hỗ trợ kiểu đó, `unwrap` có thể ném `ValidationException`. Vì thế “dùng qua `unwrap`” **không tự làm extension portable**.

Mẫu thiết kế có ích là:

- Core/domain: dữ liệu và constraint chỉ dùng API Jakarta.
- Adapter/framework: xử lý Spring MVC, ánh xạ lỗi cho client.
- Provider configuration: phần cần `HibernateValidatorConfiguration`, `ConstraintMapping` hoặc custom context.
- Test: khóa lại hành vi ở những ranh giới có thể ảnh hưởng người dùng.

Không bắt buộc tách module vật lý cho mọi ứng dụng nhỏ, nhưng ranh giới dependency phải dễ nhận ra khi đọc code.

## 10. Bài kiểm thử để phát hiện khóa vào provider

Với demo ở mục 5, có thể kiểm thử số violation thay vì kiểm tra “lỗi nào xuất hiện đầu tiên”.

Tệp `src/test/java/com/example/validationdemo/ValidationPortabilityTest.java`:

```java
package com.example.validationdemo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.hibernate.validator.HibernateValidator;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ValidationPortabilityTest {

    private final ValidationComparisonApplication.Candidate invalid =
            new ValidationComparisonApplication.Candidate(null, 16);

    @Test
    void standardBootstrapReportsBothViolations() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            assertEquals(
                    2,
                    factory.getValidator().validate(invalid).size()
            );
        }
    }

    @Test
    void hibernateFailFastReportsExactlyOneViolation() {
        try (ValidatorFactory factory =
                Validation.byProvider(HibernateValidator.class)
                        .configure()
                        .failFast(true)
                        .buildValidatorFactory()) {
            assertEquals(
                    1,
                    factory.getValidator().validate(invalid).size()
            );
        }
    }
}
```

Chạy:

```bash
./gradlew test
```

Kỳ vọng hai test đều PASS với dependency đã cấu hình ở mục 5. Chúng xác minh **hành vi trên Hibernate Validator hiện tại**. Chúng **chưa phải** bằng chứng rằng module thật sự hỗ trợ provider khác vì runtime test vẫn đang dùng Hibernate Validator.

Để kiểm chứng portability thực tế:

1. Chỉ build **module lõi** với Jakarta Validation API, không compile dependency đến package `org.hibernate.validator.*` (tách demo extension ra khỏi module lõi).
2. Thay runtime provider bằng một implementation tương thích với đúng Jakarta Validation version; chạy lại các test custom constraint, groups, cascading, message và exception mapping.
3. Tách các test phụ thuộc Hibernate-specific sang profile/module riêng.
4. So sánh **nghiệp vụ**, không chỉ chuỗi message hoặc thứ tự `Set<ConstraintViolation<?>>`; đừng giả định mọi provider có cùng default message.
5. Đặt test cho những tính năng dễ khác nhau: container element validation, thời gian với `ClockProvider`, mapping XML, custom validator factory và EL.
6. Với extension được chấp nhận, ghi rõ phiên bản provider tối thiểu và chính sách nâng cấp trong tài liệu module.

Nếu ứng dụng buộc phải chọn Hibernate Validator và hưởng lợi từ extension, kết quả kiểm thử đúng nên là **khóa dependency minh bạch**, không phải xóa mọi API riêng bất chấp lợi ích.

## 11. Những sai lầm phổ biến

**Sai lầm 1 — Gọi tất cả các annotation trong Hibernate Validator là riêng của Hibernate.** `@NotNull`, `@Size`, `@NotBlank`, `@Email` đều là Jakarta Validation trong thế hệ hiện nay. Dùng Hibernate Validator làm provider không làm chúng mất tính tiêu chuẩn.

**Sai lầm 2 — Nhìn thấy package `jakarta.validation` rồi khẳng định runtime độc lập với provider.** Config có thể vẫn gọi `hibernate.validator.fail_fast`, custom validator có thể `unwrap` sang Hibernate context, hoặc module phụ thuộc vào hành vi mặc định riêng của implementation. Phải kiểm tra cả source lẫn bootstrap/config/test.

**Sai lầm 3 — Xem Spring `@Validated` là extension Hibernate.** Đây là một điểm tích hợp của Spring; provider cụ thể chỉ xử lý validation dưới tầng API Jakarta. Annotation có thể sử dụng groups chuẩn nhưng bản thân annotation không thuộc Jakarta.

**Sai lầm 4 — Nghĩ `@ReportAsSingleViolation` là riêng Hibernate.** Đây là annotation Jakarta; ngược lại `@ConstraintComposition(OR)` là extension Hibernate Validator.

**Sai lầm 5 — Bật fail-fast rồi phụ thuộc thứ tự lỗi.** Không có bảo đảm constraint nào được đánh giá trước. Nếu cần thứ tự các giai đoạn, sử dụng groups và `@GroupSequence` chuẩn theo ý nghĩa của chúng, không dựa vào fail-fast.

**Sai lầm 6 — Thay `@Range` bằng `@Min`/`@Max` mà không kiểm tra phản hồi API.** Kết quả đạt/sai về miền giá trị có thể tương đương, nhưng số violation, message key, path và metadata có thể thay đổi. Cần test lại tương thích contract phía client.

**Sai lầm 7 — Trộn `javax.validation` và `jakarta.validation`.** Spring Boot 3 sử dụng Jakarta; nhiều ví dụ lịch sử từ Spring Boot 2 dùng javax. Hai namespace không thể thay thế chỉ bằng rename import nếu dependency/provider chưa đúng.

**Sai lầm 8 — Tạo `ValidatorFactory` trong vòng lặp request.** Provider cần đọc metadata, cấu hình, cache. Dùng factory quản lý vòng đời ứng dụng; ví dụ bootstrap thủ công trong bài chỉ nhằm minh họa sự khác biệt.

**Sai lầm 9 — Dùng class `org.hibernate.validator.internal.*`.** Những API nội bộ không cam kết tính tương thích khi nâng cấp; ngay cả khi đã chấp nhận extension, ưu tiên API public được tài liệu hóa.

**Sai lầm 10 — Dùng dynamic payload/EL để đưa dữ liệu nhạy cảm vào message.** Extension này mạnh nhưng không cần thiết cho mọi lỗi. Giữ template tĩnh, dùng parameter có kiểm soát và không đưa giá trị bí mật vào response client.

**Sai lầm 11 — Coi validation API thay cho invariant nghiệp vụ.** Validation ở boundary hữu ích cho lỗi input; điều kiện cần transaction, quyền truy cập, dữ liệu hiện tại trong database vẫn phải được bảo đảm tại tầng domain/service và lưu trữ khi thích hợp.

## 12. Checklist chọn giải pháp

Khi thêm một quy tắc hoặc cấu hình validation:

1. **Tìm phương án Jakarta trước.** `@NotNull`, `@Size`, `@Min`/`@Max`, groups, `@Valid`, custom `@Constraint`, `ValueExtractor` và SPI chuẩn có đáp ứng không?
2. **Nếu phải dùng extension**, xác định chính xác class/property của provider; giải thích lợi ích cụ thể như fail-fast, DSL mapping, constraint đặc biệt.
3. **Kiểm tra code và dependency.** Package `jakarta.validation` vs `org.hibernate.validator` vs `org.springframework.validation`; đừng suy luận chỉ từ tên gọi.
4. **Định nghĩa ranh giới phụ thuộc.** Core logic có thể chia sẻ riêng hay toàn ứng dụng chấp nhận Hibernate Validator?
5. **Bảo vệ contract phía ngoài.** Error code, property path, status và điều kiện hợp lệ quan trọng hơn thứ tự message hoặc chi tiết provider.
6. **Kiểm thử cả ca tốt/xấu, dữ liệu biên và cấu hình.** Fail-fast, groups, message interpolation, container elements, custom validators và Spring binding.
7. **Khi nâng cấp/đổi provider**, đối chiếu bảng tương thích Jakarta Validation–provider–Spring Boot; chạy test trước khi chuyển production.

### Quy tắc quyết định nhanh

| Nhu cầu | Hướng chọn mặc định |
| --- | --- |
| Bắt buộc, độ dài, số trong khoảng | Constraint Jakarta (`@NotNull`, `@Size`, `@Min`/`@Max`) |
| Quan hệ nhiều trường, quy tắc SKU | Custom `@Constraint` + `ConstraintValidator` dùng Jakarta |
| Muốn trả tất cả lỗi cùng lúc | Hành vi thông thường của validator, chuẩn hóa danh sách vi phạm |
| Muốn dừng ở lỗi đầu tiên để tối ưu | Hibernate `failFast(true)`, ghi nhận coupling và thứ tự không bảo đảm |
| Muốn kiểm tra nhóm theo thứ tự | `@GroupSequence` chuẩn |
| Muốn thay đổi Default groups theo trạng thái bean | Hibernate `@GroupSequenceProvider` hoặc thiết kế lại flow kiểm tra |
| Muốn khai báo constraint mà không sửa annotation | Mapping XML chuẩn; nếu cần fluent DSL thì dùng Hibernate `ConstraintMapping` |
| Muốn message có property path | `ConstraintValidatorContext` chuẩn |
| Muốn message parameter/dynamic payload nâng cao | Hibernate context, chỉ khi thực sự cần |
| Muốn tích hợp request/body/form vào Spring | `@Valid`, `@Validated`, `LocalValidatorFactoryBean` và error handling của Spring |

**Điểm cốt lõi:** `jakarta.validation.*` là **hợp đồng chuẩn**; Hibernate Validator là **provider thực thi** hợp đồng đó và cung cấp thêm tính năng riêng; Spring Framework là **lớp tích hợp** giữa validation và ứng dụng. Hãy cố định boundary này trong thiết kế, chỉ phụ thuộc extension khi lợi ích đáng giá và có test bảo vệ hành vi.

## Tài liệu tham khảo

- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html) — hợp đồng chuẩn, bootstrap, constraints, groups, metadata và SPI.
- [Jakarta Validation API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/package-summary) — tra đúng package/interface tiêu chuẩn.
- [Hibernate Validator 8 Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/) — chương “Hibernate Validator Specifics”, fail-fast, programmatic mapping, composition, context extension.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html) — tích hợp Jakarta Validation.
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html) — adapter và hook cấu hình.
