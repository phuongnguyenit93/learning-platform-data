# Chuyển namespace `javax.validation` sang `jakarta.validation` trong Spring Framework

## 1. Vì sao cần chuyển?

Khi nâng cấp ứng dụng từ Spring Framework 5.x / Spring Boot 2.x lên Spring Framework 6.x / Spring Boot 3.x, một thay đổi nền tảng là chuyển từ các API Java EE mang tên `javax.*` sang các API Jakarta EE mang tên `jakarta.*`. Với **Bean Validation**, namespace cũ `javax.validation` được thay bằng **`jakarta.validation`**.

Ví dụ về cùng một quy tắc:

```java
// Ứng dụng cũ (Javax Bean Validation 2.x)
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
```

```java
// Ứng dụng mới (Jakarta Validation 3.x)
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
```

Ý nghĩa của `@NotBlank` hay `@Size` cơ bản vẫn là kiểm tra điều kiện trên dữ liệu, nhưng **chúng là những kiểu Java thuộc package khác nhau**. `javax.validation.Valid` và `jakarta.validation.Valid` không phải cùng một annotation; việc dự án vẫn biên dịch được khi lỡ có hai bộ thư viện trên classpath không chứng minh Spring mới sẽ chạy validation đúng.

Phạm vi bài này là **thiết lập Bean Validation** và cách di chuyển mã, dependencies, cấu hình, kiểm thử liên quan trong Spring. Chuyển namespace không tự làm thay đổi quy tắc nghiệp vụ, dữ liệu đã lưu hay biến JSON của API.

### Mốc tương thích cần nắm

| Nền tảng | Namespace Bean Validation thông dụng | Cần chú ý |
| --- | --- | --- |
| Spring Framework 5.x, Spring Boot 2.x | `javax.validation.*` | Phù hợp hệ sinh thái Java EE/Bean Validation đời cũ |
| Spring Framework 6.x, Spring Boot 3.x | `jakarta.validation.*` | Spring 6 yêu cầu Java 17+; phải dùng API/validator tương thích Jakarta |
| Jakarta Bean Validation 2.0 | `javax.validation.*` | Dù có thể dùng artifact mang tên `jakarta.validation-api:2.0.x`, package vẫn là `javax` |
| Jakarta Bean Validation 3.0 | `jakarta.validation.*` | Thay package và namespace XML; phù hợp Jakarta EE 9/10 |
| Jakarta Validation 3.1 | `jakarta.validation.*` | Thuộc hệ Jakarta EE mới hơn; cần phối hợp version theo nền tảng |

Điểm dễ bỏ sót: **artifact tên `jakarta.validation:jakarta.validation-api` phiên bản 2.0.x vẫn chứa package `javax.validation`**. Để import được `jakarta.validation.*` phải dùng Jakarta Validation 3.0+ theo bộ phiên bản mà Spring Boot/framework đang quản lý. Không suy luận package chỉ từ tên artifact.

## 2. Ba thành phần phải tương thích với nhau

Việc thay `import` là bước của source code, nhưng runtime còn phụ thuộc hai lớp khác:

1. **Validation API:** định nghĩa annotation `@Valid`, `@NotNull`, `@Size`, `Validator`, `ConstraintViolation`, `ConstraintValidator`... Trong hệ mới là `jakarta.validation:jakarta.validation-api` phiên bản Jakarta thích hợp.
2. **Validation provider:** thư viện thực thi quy tắc và tìm metadata. Thông dụng nhất là Hibernate Validator. Hibernate Validator 6.x dùng namespace `javax`; 7.x và 8.x dùng `jakarta` (phiên bản 8 phù hợp Jakarta EE 10); các đời mới hơn có thể theo bản Jakarta mới hơn.
3. **Tích hợp Spring:** Spring MVC, Spring `LocalValidatorFactoryBean`, `@Validated`, `@ModelAttribute`, `@RequestBody` kết nối binder/validator và đưa lỗi tới controller.

Trong ứng dụng **Spring Boot 3.x**, cách thông dụng là để Boot quản lý version và thêm starter validation. Không chỉ thêm file API mà quên provider; chỉ có các interface/annotation thì việc đánh giá constraint có thể không diễn ra hoặc khởi tạo `ValidatorFactory` thất bại vì thiếu implementation.

### Maven: cấu hình chuẩn cho Spring Boot 3.x

Nếu `pom.xml` đã dùng parent/BOM của Spring Boot 3.x, khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

`spring-boot-starter-validation` kéo các thư viện validation thích hợp với bản Boot do project quản lý. **Không tự ghim phiên bản `jakarta.validation-api` hoặc Hibernate Validator khác với BOM** nếu chưa có yêu cầu tương thích cụ thể. Nếu dự án chỉ cần validation ở lớp service/core, `spring-boot-starter-validation` vẫn có thể dùng độc lập với `spring-boot-starter-web`.

### Gradle: cấu hình trong project Spring Boot

Với Groovy DSL (`build.gradle`), khi project đã dùng Spring Boot plugin và quản lý dependency version:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Với Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Nếu dùng **Spring Framework thuần** không qua Boot, phải bổ sung cả Jakarta Validation API lẫn provider tương thích, cấu hình `LocalValidatorFactoryBean`/validator dùng cho MVC nếu cần. Đừng bê nguyên snippet không version của Boot sang build không có dependency management.

### Phụ thuộc cũ cần loại bỏ hoặc nâng cấp

- `javax.validation:validation-api` là Bean Validation API namespace cũ.
- `jakarta.validation:jakarta.validation-api:2.0.x` **chưa** phải namespace `jakarta.validation`.
- `org.hibernate.validator:hibernate-validator` đời 6.x thực thi `javax.validation`; với Spring Boot 3.x cần dùng đời do Boot quản lý phù hợp Jakarta.
- Các thư viện nội bộ/third-party compile với `javax.validation.ConstraintValidator`, `javax.validation.Validator` hoặc nhận `javax.validation.ConstraintViolation` trong public API phải được nâng cấp/chỉnh sửa theo namespace mới. Không thể sửa import ở lớp gọi và kỳ vọng binary cũ tương thích.

**Chỉ đổi version hoặc chỉ thay import đều chưa đủ:** cần kiểm tra toàn bộ đường đi từ annotation tới validator provider và tích hợp Spring.

## 3. Bảng ánh xạ import: sửa đúng thứ thuộc Bean Validation

| Trước (Javax) | Sau (Jakarta) | Vai trò |
| --- | --- | --- |
| `javax.validation.Valid` | `jakarta.validation.Valid` | Kích hoạt cascaded validation / validation đối số theo ngữ cảnh |
| `javax.validation.constraints.NotNull` | `jakarta.validation.constraints.NotNull` | Không cho phép `null` |
| `javax.validation.constraints.NotBlank` | `jakarta.validation.constraints.NotBlank` | Chuỗi không `null`, không rỗng hoặc toàn khoảng trắng |
| `javax.validation.constraints.NotEmpty` | `jakarta.validation.constraints.NotEmpty` | Chuỗi/collection/map/array không rỗng |
| `javax.validation.constraints.Size` | `jakarta.validation.constraints.Size` | Giới hạn kích thước |
| `javax.validation.constraints.Min`, `Max` | `jakarta.validation.constraints.Min`, `Max` | Giới hạn giá trị |
| `javax.validation.constraints.Email` | `jakarta.validation.constraints.Email` | Kiểm tra định dạng email theo provider |
| `javax.validation.Validator` | `jakarta.validation.Validator` | API gọi validate trực tiếp |
| `javax.validation.Validation` | `jakarta.validation.Validation` | Bootstrap `ValidatorFactory` |
| `javax.validation.ValidatorFactory` | `jakarta.validation.ValidatorFactory` | Nhà máy tạo validator |
| `javax.validation.ConstraintViolation` | `jakarta.validation.ConstraintViolation` | Mô tả một vi phạm |
| `javax.validation.ConstraintViolationException` | `jakarta.validation.ConstraintViolationException` | Exception vi phạm constraint |
| `javax.validation.Constraint` | `jakarta.validation.Constraint` | Định nghĩa annotation constraint tùy chỉnh |
| `javax.validation.Payload` | `jakarta.validation.Payload` | Metadata của constraint |
| `javax.validation.ConstraintValidator` | `jakarta.validation.ConstraintValidator` | Logic đánh giá constraint tùy chỉnh |
| `javax.validation.ConstraintValidatorContext` | `jakarta.validation.ConstraintValidatorContext` | Ngữ cảnh tạo violation |
| `javax.validation.groups.Default` | `jakarta.validation.groups.Default` | Nhóm validation mặc định |
| `javax.validation.executable.*` | `jakarta.validation.executable.*` | Validation method/constructor |
| `javax.validation.valueextraction.*` | `jakarta.validation.valueextraction.*` | Container element validation |

Trong khi đó những thành phần **của Spring** vẫn ở package `org.springframework.*`, ví dụ:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator; // Validator riêng của Spring
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ModelAttribute;
```

Cần phân biệt **`org.springframework.validation.Validator`** với **`jakarta.validation.Validator`**; chúng có interface/phương thức khác nhau. Spring có adapter như `LocalValidatorFactoryBean` để tích hợp giữa hai thế giới. Không tìm-thay tất cả các từ `Validator` hoặc tất cả prefix `javax.` một cách máy móc.

## 4. Quy trình nâng cấp có kiểm soát

### Bước 1 — Chốt phiên bản nền tảng

Xác nhận ứng dụng đang chạy Spring Framework/Boot nào và JDK nào. Với đích Spring Boot 3.x cần Java 17+ và Spring Framework 6.x. Nếu vẫn ở Spring Boot 2.x/Spring 5.x, chỉ đổi `javax.validation` sang `jakarta.validation` thường sẽ làm mất tương thích với framework cũ. Nâng **nền tảng và dependency** theo hướng dẫn nâng cấp trước, sau đó mới chuyển source imports.

### Bước 2 — Tìm toàn bộ điểm đang dùng namespace cũ

Tại thư mục gốc source của ứng dụng, có thể dùng `rg`:

```bash
rg -n 'javax\.validation|javax\.el|validation-api|hibernate-validator' .
```

Kiểm tra không chỉ `src/main/java` mà cả `src/test/java`, file cấu hình, module dùng chung và mã sinh ra từ tool. Đối với thư viện import công khai, lưu ý cả chữ ký public method, generic type và annotation trong các shared DTO. `javax.el` là thành phần có thể liên quan đến Hibernate Validator/message interpolation; nếu xuất hiện, xem lại tương thích với Jakarta Expression Language thay vì chỉ bỏ qua.

Đọc từng kết quả theo ngữ cảnh: các namespace `javax.crypto`, `javax.net`, `javax.xml`... vẫn thuộc Java SE và **không được đổi đại trà**.

### Bước 3 — Sửa dependencies trước khi sửa import

Với Maven:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.validation:validation-api,jakarta.validation:jakarta.validation-api,org.hibernate.validator:hibernate-validator
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency validation-api
./gradlew dependencyInsight --configuration runtimeClasspath --dependency hibernate-validator
```

Xác định dependency nào mang API/provider cũ vào classpath. Ưu tiên **upgrade thư viện gốc**. Chỉ dùng `exclude` cho dependency transitively không còn cần thiết khi đã xác minh; loại nhầm provider có thể khiến validation không hoạt động.

### Bước 4 — Chuyển import và các type phụ thuộc

Đổi `javax.validation.*` sang `jakarta.validation.*` ở controller, DTO, entity, service, validator tự viết và test. Kiểm tra riêng custom constraint, validation groups, exception handler, các API trả về `Set<ConstraintViolation<T>>`, interface thư viện chia sẻ và reflection/codegen dựa trên tên annotation.

Ví dụ cùng một record DTO:

```java
// Trước: khi dự án còn chạy Bean Validation namespace javax
import javax.validation.constraints.Email;
import javax.validation.constraints.NotBlank;

public record RegisterRequest(
        @NotBlank String username,
        @NotBlank @Email String email) {}
```

```java
// Sau: với Jakarta Validation 3.x và Spring Boot 3.x
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record RegisterRequest(
        @NotBlank String username,
        @NotBlank @Email String email) {}
```

Hai đoạn **là hai phiên bản thay thế**, không đặt chung trong một file. `RegisterRequest` phải nằm trong file `RegisterRequest.java` cùng package phù hợp; các ví dụ trên cố ý lược dòng `package` để nhấn mạnh import thay đổi.

### Bước 5 — Chỉnh XML và tích hợp đặc thù nếu có

Nếu dự án có `META-INF/validation.xml` hoặc XML constraint mapping, cần cập nhật namespace XML đúng chuẩn Jakarta, không chỉ sửa Java imports.

| Thành phần | Namespace cũ | Namespace Jakarta Validation 3.0 |
| --- | --- | --- |
| `validation.xml` | `http://xmlns.jcp.org/xml/ns/validation/configuration` | `https://jakarta.ee/xml/ns/validation/configuration` |
| Constraint mapping XML | `http://xmlns.jcp.org/xml/ns/validation/mapping` | `https://jakarta.ee/xml/ns/validation/mapping` |

Đối với schema 3.0, cấu hình tối thiểu minh họa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<validation-config xmlns="https://jakarta.ee/xml/ns/validation/configuration"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="https://jakarta.ee/xml/ns/validation/configuration https://jakarta.ee/xml/ns/validation/validation-configuration-3.0.xsd"
    version="3.0">
</validation-config>
```

Chỉ tạo `validation.xml` khi thật sự cần cấu hình provider/constraint mappings; dự án Boot đơn giản thường **không cần** file này. Với Jakarta Validation phiên bản khác, kiểm tra namespace/schema được bản đặc tả ấy hỗ trợ. Nếu dự án có tên lớp `javax.validation...` trong XML, tài nguyên SPI `META-INF/services/...` hoặc rule phân tích bytecode, cũng cần cập nhật. File `ValidationMessages.properties` có thể tiếp tục chứa các message keys hiện có; chỉ sửa những khóa/giá trị dựa vào tên type cũ.

### Bước 6 — Build sạch và kiểm chứng hành vi

Chạy compile, unit test và integration test trên **classpath thực tế của ứng dụng**, không chỉ dựa vào IDE autocomplete. Sau migration, tìm lại `javax.validation` trong source và xem dependency tree để xác minh không còn đường sử dụng cũ không mong muốn. Một thư viện legacy có thể vẫn kéo `javax.validation-api` vào classpath mà compile vẫn thành công; đây là tín hiệu cần điều tra mức độ tương thích.

## 5. Ví dụ Spring MVC chạy được sau migration

Ví dụ sau dùng Java 17+, Spring Boot 3.x, Spring MVC và Jakarta Validation. Cần có hai starter `spring-boot-starter-web` và `spring-boot-starter-validation` như ở phần 2.

Tạo file `src/main/java/example/validation/ValidationMigrationApplication.java`:

```java
package example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ValidationMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationMigrationApplication.class, args);
    }

    public record Registration(
            @NotBlank String name,
            @NotBlank @Email String email,
            @NotNull @Min(18) Integer age) {}

    @PostMapping(path = "/registrations",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> register(
            @Valid @RequestBody Registration input) {

        return ResponseEntity.ok("accepted:" + input.email());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<String> handleInvalidInput(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body("VALIDATION_FAILED");
    }
}
```

**Điều kiện chạy:** Dùng một ứng dụng Maven/Gradle Spring Boot 3.x đã khai báo hai dependencies nói trên và JDK 17+. Trong ví dụ này, chỉ có một file Java là đủ cho lớp ứng dụng/controller; provider được starter validation cung cấp. Khởi chạy bằng:

```bash
mvn spring-boot:run
```

Nếu dùng Gradle thì chạy `./gradlew bootRun`. Ứng dụng mặc định phục vụ cổng 8080 khi không cấu hình khác.

Request hợp lệ:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":24}'
```

HTTP status dự kiến: `200 OK`. Phần **response body** chính xác do controller tạo:

```text
accepted:lan@example.com
```

Request vi phạm constraint:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"not-an-email","age":15}'
```

HTTP status dự kiến: `400 Bad Request`. Phần **response body** từ handler tự viết:

```text
VALIDATION_FAILED
```

Cơ chế: Jackson đọc JSON vào `Registration`; `@Valid` yêu cầu Bean Validation đánh giá `@NotBlank`, `@Email`, `@NotNull` và `@Min`. Khi đối số `@RequestBody` không hợp lệ trong tình huống này, Spring MVC phát sinh `MethodArgumentNotValidException`, được `@ExceptionHandler` xử lý. Kết quả không dựa vào câu chữ message mặc định của provider nên ví dụ dễ kiểm tra.

**Không nhầm hai loại lỗi:** JSON sai cú pháp hoặc không chuyển được sang DTO thường gây `HttpMessageNotReadableException`; request hợp lệ về cú pháp nhưng vi phạm Bean Validation mới đi theo ví dụ `MethodArgumentNotValidException` ở trên. Exception cụ thể còn phụ thuộc cách viết handler và hình thức validation.

## 6. Sau khi đổi import, kích hoạt validation đúng chỗ

### `@RequestBody` / `@ModelAttribute`

- `@Valid` nên import từ `jakarta.validation.Valid`. Đặt `@Valid` trước DTO trong method parameter để yêu cầu validation sau binding/conversion.
- `@ModelAttribute` dùng cho form/query binding; `@RequestBody` thường dùng cho JSON/XML body. Cả hai đều có thể được Spring MVC validate.
- Nếu controller cần tự xử lý lỗi form, đặt `BindingResult` **ngay sau** tham số model/request được validate theo cách được Spring MVC hỗ trợ. `BindingResult` vẫn thuộc `org.springframework.validation`.
- Với controller có constraint trực tiếp lên method parameter, Spring MVC 6.1+ có **method validation** và có thể phát sinh `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException`. Không giả định một loại exception cho mọi chữ ký controller.

Ví dụ handler cho form trong một controller:

```java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

// Đoạn method, đặt bên trong class @Controller phù hợp:
@PostMapping("/profile")
public String save(@Valid @ModelAttribute ProfileForm form,
                   BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "profile-saved";
}
```

`ProfileForm` và các view được khai báo trong ứng dụng thật; đoạn trên là **minh họa method**, không phải file Java độc lập. Với Spring MVC, `BindingResult` phải liền sau đối tượng mà nó nhận lỗi.

### `@Validated` của Spring vẫn giữ nguyên package

`org.springframework.validation.annotation.Validated` là annotation **của Spring**, thường dùng cho validation groups hoặc kích hoạt method validation ở service do Spring quản lý. Namespace migration không biến nó thành `jakarta.validation.Validated`; không có thay thế như vậy.

```java
import jakarta.validation.constraints.Min;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class AccountService {
    public void setAge(@Min(18) int age) {
        // Chỉ thực thi khi tham số hợp lệ.
    }
}
```

Đoạn `AccountService` chỉ minh họa class trong ứng dụng có Jakarta provider và method validation của Spring được cấu hình. Để Spring áp dụng validation theo proxy/AOP cho service, phương thức phải được gọi **qua bean/proxy Spring**; tự gọi method trong cùng object có thể đi vòng qua proxy. Đừng lấy service method validation làm bằng chứng MVC request validation đã đúng: chúng là hai tuyến kích hoạt khác nhau.

### Cascaded validation với object lồng nhau

`@Valid` cần xuất hiện ở điểm muốn chạy xuống object lồng nhau. Ví dụ:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public record Address(@NotBlank String city) {}

public record CustomerInput(
        @NotBlank String name,
        @Valid Address address,
        List<@Valid Address> previousAddresses) {}
```

Đây là **hai khai báo record ở cấp top-level**, đặt trong `Address.java` và `CustomerInput.java` (hoặc đổi phạm vi khai báo cho đúng Java). Dù chuyển namespace thành công, việc quên `@Valid` trên field/nested object vẫn có thể khiến constraint của object con không được xét. Với các danh sách hay Map, cú pháp container element validation phụ thuộc bản API/provider hỗ trợ.

## 7. Migration cho custom constraint và validator

Dự án chỉ dùng `@NotBlank`, `@Size` thường đổi import tương đối nhanh. Với annotation tùy chỉnh, phải chuyển **cả giao diện custom validator**, `Payload`, `ConstraintValidatorContext` và type tham chiếu; sửa một nửa gây lỗi compile hoặc provider không tìm thấy validator.

Ví dụ annotation ở `src/main/java/example/validation/ValidSku.java`:

```java
package example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Constraint(validatedBy = SkuValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER,
         ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidSku {
    String message() default "SKU must start with SKU-";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator tại `src/main/java/example/validation/SkuValidator.java`:

```java
package example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SkuValidator
        implements ConstraintValidator<ValidSku, String> {

    @Override
    public boolean isValid(String value,
                           ConstraintValidatorContext context) {
        return value == null || value.startsWith("SKU-");
    }
}
```

Sau khi compile với Jakarta Validation API/provider, có thể gắn `@ValidSku` lên field hoặc parameter tương thích. Logic ở đây **cho phép `null`** (quy ước phổ biến của các constraint kiểm tra định dạng); muốn bắt buộc có mã thì kết hợp `@NotNull` hoặc `@NotBlank`. Với annotation custom nhiều thành phần, còn cần xem lại validation groups, composition (`@ReportAsSingleViolation`), container targets, custom messages và value extractors.

Nếu custom validation dùng annotation riêng của Hibernate Validator, kiểm tra migration guide của **đúng phiên bản provider**. Một số annotation mở rộng đã deprecated hoặc bị loại ở đời mới; không mặc định rằng mọi annotation trong `org.hibernate.validator.constraints` đều còn tồn tại y hệt.

## 8. Những lỗi thường gặp khi chuyển namespace

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `package jakarta.validation does not exist` | Chưa có API Jakarta 3.x+ hoặc classpath vẫn dùng API 2.0.x | Kiểm tra dependency tree và BOM |
| `cannot find symbol: Valid` | Còn import `javax.validation.Valid` hoặc đã xóa API mà chưa thay | Dùng `jakarta.validation.Valid` |
| Constraint có trên DTO nhưng request vẫn lọt qua | Thiếu `@Valid`, provider, cấu hình MVC, hoặc annotation còn ở namespace cũ | Kiểm tra annotation import, starter, test HTTP thực tế |
| `NoProviderFoundException` | Có API nhưng không có implementation tương thích | Thêm/sửa provider; Boot dùng starter validation |
| `NoClassDefFoundError: javax/validation/...` | Một library đã compile với Javax nhưng runtime chỉ có Jakarta | Nâng cấp/rebuild library ấy cho Jakarta |
| `ClassNotFoundException: jakarta.validation...` | API Jakarta thiếu lúc runtime hoặc dependency bị loại nhầm | Kiểm tra runtimeClasspath/packaged artifact |
| `UnexpectedTypeException` | Constraint đặt trên kiểu không được validator hỗ trợ | Xem type, constraint và custom validator implementation |
| Lỗi đọc `validation.xml` | Namespace/XSD/cấu hình provider cũ | Chuyển XML theo version Jakarta phù hợp |
| `@Validated` bị đổi import sai | Nhầm annotation riêng của Spring với Jakarta | Giữ `org.springframework.validation.annotation.Validated` |
| Unit test pass nhưng HTTP không trả 400 | Test validate DTO trực tiếp chưa đi qua MVC binding | Thêm MockMvc hoặc HTTP integration test |
| Validation bị chạy hai lần hoặc exception khác | Controller có method validation hoặc proxy configuration khác | Kiểm tra chữ ký method, Spring version và exception path |

Không nên giải quyết bằng cách giữ **cả Javax API và Jakarta API** rồi hy vọng framework tự nối hai hệ annotation. Chúng có thể xuất hiện đồng thời ở dependency graph vì thư viện cũ; mục tiêu là nhận diện nguyên nhân, nâng cấp phần liên quan và đảm bảo đường gọi production dùng cùng namespace Jakarta.

## 9. Kiểm thử sau migration: xác minh hành vi, không chỉ compile

### Các trường hợp tối thiểu

| Test case | Kết quả mong đợi |
| --- | --- |
| DTO có `@NotBlank` nhận chuỗi trống qua `@Valid @RequestBody` | HTTP 400 theo handler/exception configuration |
| DTO hợp lệ | Controller xử lý bình thường |
| `@Min(18)` nhận `age=15` | Bị từ chối bởi validation |
| `@NotNull` nhận giá trị `null` hoặc field vắng mặt | Tạo violation cho thuộc tính |
| DTO chứa object con có `@Valid` | Constraint ở object con được đánh giá |
| Custom `@ValidSku` với `"ABC"` | Tạo violation nếu validator được cấu hình đúng |
| Service `@Validated` có method constraint | Lỗi được phát hiện khi gọi qua proxy Spring |
| Old dependency reference `javax.validation` | Không còn phụ thuộc trực tiếp hoặc cần kế hoạch nâng cấp bên thứ ba rõ ràng |

### Test bằng Jakarta Validator trực tiếp

Trong dự án có provider Jakarta tương thích, có thể viết logic kiểm tra độc lập với HTTP:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;

// Đoạn đặt trong class/method Java phù hợp:
record Input(@NotBlank String name) {}

try (ValidatorFactory factory =
         Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    int count = validator.validate(new Input("")).size();
    System.out.println(count);
}
```

Với một provider đánh giá `@NotBlank` chuẩn và chỉ một constraint như trên, stdout:

```text
1
```

Đây là snippet đặt `record Input` trong phạm vi class/method và phần `try` trong **method** (Java 17+), không phải một file Java độc lập; nếu `ValidatorFactory` không khởi tạo được thì phải xem provider/dependency. Kiểm tra trực tiếp chứng minh Jakarta Validator hoạt động, còn việc Spring MVC gọi đúng validator cần integration test.

Chạy các test đã có và build đầy đủ, ví dụ:

```bash
mvn clean test
# Hoặc trong Gradle:
./gradlew clean test
```

Với ứng dụng web, kiểm tra thêm trạng thái HTTP thực tế, nội dung `BindingResult` hoặc exception handler, không lấy sự thành công của `compileJava` làm điểm kết thúc. Sau khi migrate, hãy tìm lại tất cả occurrence `javax.validation`: occurrence trong comment/tài liệu migration có thể hợp lệ, nhưng source code production, cấu hình runtime và thư viện tích hợp cần được phân loại cụ thể.

## 10. Checklist triển khai và nguyên tắc tránh lỗi

1. **Chốt Spring Boot/Framework + JDK:** Spring 6.x / Boot 3.x tương thích Jakarta Validation và Java 17+.
2. **Đồng bộ dependency:** dùng Jakarta Validation API 3.x tương thích, provider thích hợp, ưu tiên starter/BOM của Boot; loại hoặc nâng cấp các dependency Javax cũ được xác định.
3. **Đổi mã nguồn có chọn lọc:** `javax.validation.*` → `jakarta.validation.*` ở imports, generic, custom constraints, exception, shared modules và test; không đổi tùy tiện package Java SE còn mang `javax.*`.
4. **Giữ đúng tích hợp Spring:** `@Validated` và `BindingResult` vẫn thuộc `org.springframework.validation`; đảm bảo `@Valid` là annotation Jakarta.
5. **Cập nhật cấu hình đặc thù:** XML namespaces, SPI descriptors, validator bean thủ công, codegen và thư viện mở rộng (nếu có).
6. **Kiểm thử cả hai tầng:** Jakarta validator trực tiếp **và** validation qua Spring MVC/service; kiểm tra lỗi binding, lỗi constraint, cascaded validation và custom validators.
7. **Soát runtime thật:** dependency tree, JAR đóng gói và log startup; đảm bảo không có lỗi thiếu class/thiếu provider hay validation âm thầm không chạy.

Một lần chuyển thành công là khi **annotation Jakarta được provider Jakarta nhận diện và Spring áp dụng đúng vào request/service** với các test hành vi đã xác minh. Khác biệt cốt lõi nằm ở type/package và chuỗi dependency thực thi, không phải ở cách viết điều kiện `@NotBlank` hay `@Min`.

## Tài liệu chuẩn để đối chiếu

- [Jakarta Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/)
- [Jakarta Bean Validation 3.0 — namespace change và XML descriptors](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Spring Boot 3.0 Migration Guide — Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Framework 6.x Upgrade Guide](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Hibernate Validator — Migration Guide](https://hibernate.org/validator/documentation/migration-guide/)
