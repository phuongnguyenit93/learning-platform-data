# Đồng bộ cấu hình binding giữa ứng dụng và kiểm thử trong Spring MVC

## 1. Vấn đề: test pass nhưng request thật bind khác

Một controller Spring MVC có thể hoạt động đúng trong ứng dụng thật nhưng trả kết quả khác khi chạy test. Nguyên nhân không nhất thiết nằm ở controller: **cấu hình data binding của môi trường test có thể khác runtime**.

Những trường hợp điển hình:

- Production đã đăng ký `Converter<String, MemberCode>` để chuẩn hóa mã thành chữ hoa, nhưng `MockMvcBuilders.standaloneSetup(...)` không nạp converter đó.
- Controller dùng `@InitBinder("registration")` để giới hạn `allowedFields`, nhưng test tự tạo `DataBinder` rồi không gọi initializer; kết quả là test chấp nhận một field mà request thực sẽ bị suppress.
- Bean Validation chạy qua `@Valid` ở runtime, nhưng test chỉ `new RegistrationController()` và gọi trực tiếp một phương thức Java; việc này không kiểm tra argument resolution, binder hay validation của MVC.
- `@WebMvcTest` tạo một **MVC slice** có những thành phần khác full context; một `@Configuration` riêng chứa `WebMvcConfigurer`, formatter hoặc validator có thể phải được import rõ ràng.
- Test tự tạo `ObjectMapper`, `ConversionService`, `Validator` hoặc `Locale` khác với ứng dụng, nên chuỗi số/ngày giờ, enum, thông điệp lỗi hoặc quy tắc ràng buộc cho kết quả khác.
- Một `@ControllerAdvice` trong ứng dụng chứa `@InitBinder` toàn cục, nhưng test standalone quên đăng ký advice.
- Đường dẫn code dùng `@ModelAttribute` để bind form, còn test lại gửi `@RequestBody` JSON: **hai pipeline chuyển đổi không tương đương**.

**Mục tiêu** của bài này: giữ **một nguồn cấu hình binding** cho Spring MVC, chọn đúng mức kiểm thử, tái sử dụng các thành phần thực tế thay vì sao chép cấu hình trong test, và viết những phép thử phát hiện cấu hình thiếu/khác. Ví dụ dùng **Java 17, Spring Boot 3.4.x, Spring Framework 6.x, MockMvc, JUnit 5 và Jakarta Validation**.

## 2. Binding là một pipeline, không chỉ một lệnh set property

Với request form-urlencoded và `@ModelAttribute`, đường đi tổng quát:

```text
Client POST /registrations
Content-Type: application/x-www-form-urlencoded
   |
   v
DispatcherServlet -> controller handler
   |
   v
Argument resolver tạo/tìm @ModelAttribute("registration")
   |
   v
WebDataBinder + objectName "registration"
   |
   +--> MVC ConversionService (Converter / Formatter)
   +--> @ControllerAdvice @InitBinder (nếu có)
   +--> Controller @InitBinder("registration")
   +--> allowedFields / fieldMarker / fieldDefault
   +--> BindingResult: errors + suppressedFields
   |
   v
@Valid / @Validated
   |
   +--> Jakarta Bean Validation provider
   +--> Spring Validator bổ sung qua binder
   |
   v
Controller nhận RegistrationForm và BindingResult
   |
   +--> reject request nếu binding/validation sai
   |
   v
Service / persistence / response
```

Khi kiểm thử, câu hỏi không chỉ là **“controller trả status nào?”** mà còn là:

1. Test có dùng **cùng objectName, cùng kiểu dữ liệu và cùng media type** với request thật không?
2. Nó có dùng **cùng ConversionService, formatter, validator, @InitBinder, @ControllerAdvice** với ứng dụng không?
3. Test có quan sát **BindingResult**, lỗi type conversion và field bị suppress không?
4. Những gì test bỏ qua là **chủ ý** (unit test thuần) hay **lệch cấu hình ngoài ý muốn**?

Test không cần khởi động cả ứng dụng cho mọi tình huống, nhưng mức kiểm thử phải phù hợp với khẳng định mà nó đưa ra.

## 3. Ba cách kiểm thử phổ biến và mức độ đồng bộ

| Cách kiểm thử | Spring context | Cấu hình MVC thực tế | Phù hợp |
| --- | --- | --- | --- |
| `@SpringBootTest + @AutoConfigureMockMvc` | Full application context | Phần lớn cấu hình MVC thật, cùng beans/application properties | Integration/contract tests cho binding, advice, converters và validation |
| `@WebMvcTest(Controller.class)` | MVC test slice | MVC infrastructure và một tập bean chọn lọc; custom config có thể cần `@Import` | Test nhanh web layer với các dependency cần thiết |
| `MockMvcBuilders.standaloneSetup(controller)` | Không tự nạp application context | Cần **cấu hình thủ công** những thành phần ngoài controller | Kiểm tra controller độc lập, lặp nhanh, debug behavior cụ thể |
| Gọi trực tiếp `controller.method(...)` | Không MVC infrastructure | Không argument resolution/binding tự động | Unit test logic Java, **không đủ** để khẳng định Spring binding đúng |
| `MockMvcBuilders.webAppContextSetup(wac)` | Có `WebApplicationContext` thực tế | Dùng infrastructure/context của MVC | Integration tests với cấu hình đầy đủ |

Spring Test phân biệt hai loại setup MockMvc: **web application context** và **standalone**. Standalone là một mô phỏng tập trung, không tự động được hưởng toàn bộ cấu hình ứng dụng; vì vậy test standalone phải được bổ sung integration tests để chứng minh app wiring đúng.

### 3.1. @SpringBootTest + @AutoConfigureMockMvc

```java
@SpringBootTest
@AutoConfigureMockMvc
class RegistrationApplicationTest {
    @Autowired MockMvc mvc;
}
```

Đây là fragment của class test. Spring Boot mở context (thông thường không cần lắng nghe HTTP port thật) rồi tạo MockMvc dùng các bean MVC thật. Nếu converter được đăng ký qua `WebMvcConfigurer` trong application context, test loại này thường dùng cùng converter.

Nó gần runtime hơn slice/standalone, nhưng **vẫn không phải bài test qua cổng HTTP thật**. Các bộ lọc, security, locale, profile, property overrides và mock beans của test có thể ảnh hưởng kết quả. Không đánh đồng full context với production deploy 100%.

### 3.2. @WebMvcTest

```java
@WebMvcTest(RegistrationController.class)
@Import(RegistrationBindingConfig.class)
class RegistrationSliceTest {
    @Autowired MockMvc mvc;
}
```

Đây là fragment có imports cần thiết. `@WebMvcTest` giới hạn component scan và auto-configuration vào web layer. Nó thường nhận các controller, `@ControllerAdvice`, `Converter`, `WebMvcConfigurer` và một số loại bean liên quan theo quy tắc Spring Boot, nhưng **không mặc định tải mọi @Service/@Configuration của ứng dụng**.

**Đừng khẳng định `@WebMvcTest` luôn bỏ mọi converter hoặc mọi WebMvcConfigurer**: nhiều thành phần web được include trong slice theo loại bean. Với cấu hình ứng dụng được đóng gói trong class `@Configuration` riêng, sử dụng `@Import(RegistrationBindingConfig.class)` là cách **tường minh** để test dùng đúng cấu hình, tránh phụ thuộc giả định scanning.

### 3.3. Standalone MockMvc

```java
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new RegistrationController())
        .build();
```

Đây là fragment đơn giản nhất. Nó mô phỏng infrastructure MVC cơ bản và nhận controller đã được tạo. Nhưng nó **không nạp @Configuration toàn ứng dụng**, nên nếu converter/formatter chỉ được đăng ký qua WebMvcConfigurer, test trên có thể thiếu. Một số @InitBinder local trên controller vẫn được standalone phát hiện, nhưng converter global, advice và validator cần xem xét riêng.

Kết luận: **test đúng môi trường mà bạn định chứng minh**, không “làm cho test xanh” bằng cách thêm giá trị mặc định tùy ý trong test.

## 4. Nguồn cấu hình nào phải đồng bộ?

| Cấu hình | Điểm đăng ký runtime phổ biến | Dấu hiệu bị thiếu trong test |
| --- | --- | --- |
| `Converter<S,T>` | `WebMvcConfigurer#addFormatters`, `ConversionService` bean | Binding type không đúng, code không được chuẩn hóa, `typeMismatch` |
| `Formatter<T>` | `addFormatters`, `@DateTimeFormat` | Ngày/số theo locale được parse khác |
| `@InitBinder` local | Controller | `allowedFields`, custom editor, validator khác |
| `@InitBinder` global | `@ControllerAdvice` | Rules dùng chung không chạy trong test standalone |
| Jakarta Validation | `LocalValidatorFactoryBean`/Boot validation starter | `@NotBlank`, `@Min` không tạo lỗi như production |
| Spring `Validator` | `@InitBinder#addValidators`, MVC config | Custom `rejectValue`/`reject` không xuất hiện |
| `MessageSource` và `LocaleResolver` | Boot config / MVC config | Lỗi tiếng Việt/tiếng Anh hoặc number/date khác |
| Binder security policy | `setAllowedFields` / DTO / `setDeclarativeBinding` | Field nhạy cảm bị bind trong test |
| Field marker/default | `WebDataBinder` prefix setup | Checkbox unchecked không reset như request thật |
| Global exception translation | `@ControllerAdvice` | Response status/body khác khi conversion/validation lỗi |

Mỗi hàng cần được kiểm chứng **bằng hành vi quan sát được**, không chỉ bằng việc test context có một bean cùng tên. Một converter có thể tồn tại trong context nhưng **không được MVC sử dụng** nếu wiring sai.

## 5. Thiết kế đồng bộ: tách cấu hình có thể tái sử dụng

Một nguyên tắc thực tế:

- Đặt converter/formatter dùng chung trong **class cấu hình MVC production** triển khai `WebMvcConfigurer`.
- Đặt quy tắc theo **model attribute cụ thể** trong `@InitBinder("objectName")` gần controller; nếu dùng nhiều controller, cân nhắc `@ControllerAdvice` đã giới hạn phạm vi.
- Đặt custom Spring `Validator` thành class riêng, có thể kiểm thử độc lập, rồi đăng ký **cùng implementation** ở runtime và test.
- Trong test slice, **import chính class cấu hình production**; không tự viết converter giả với behavior khác.
- Trong standalone, gọi lại **cùng method cấu hình** hoặc tạo ConversionService từ factory dùng chung, rồi vẫn có một test full-context để bảo đảm wiring.

**Không nên** copy một logic chuẩn hóa như “trim rồi uppercase” thành hai bản: một bản trong `MemberCodeConverter` của production, một bản do test tự làm trong `MockMvc` assertions. Làm thế khiến test có thể pass dù cấu hình runtime thay đổi.

### Một nguồn sự thật cho conversion

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class RegistrationBindingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new MemberCodeConverter());
    }
}
```

Khi ứng dụng chạy, Spring MVC áp cấu hình này vào `FormattingConversionService` dùng cho binding. Khi test slice, import **chính `RegistrationBindingConfig.class`**. Standalone có thể tạo conversion service rồi gọi `new RegistrationBindingConfig().addFormatters(service)`, nhưng phải tự bảo đảm những thành phần khác không bị bỏ sót.

Bài học sẽ hiện thực đầy đủ pattern đó trong dự án dưới đây.

## 6. Ví dụ Java 17 chạy được: full context, MVC slice và standalone dùng cùng quy tắc

Ta xây một endpoint `POST /registrations` nhận form-urlencoded:

- `name`: String không blank, được trim khoảng trắng khi bind.
- `age`: Integer bắt buộc và tối thiểu 18.
- `memberCode`: một value object, mã định dạng hai chữ cái + dấu gạch nối + hai chữ số, ví dụ `AB-12`. Converter chuẩn hóa chữ hoa, trim, từ chối pattern sai.
- `role`: property có setter trên form **chỉ để trình diễn nguy cơ mass assignment**, mặc định `USER`; không được phép bind từ request.
- `name=admin`: custom Spring `Validator` thêm lỗi field ngoài Jakarta constraints.
- `@InitBinder("registration")`: allowed fields, String trimmer và custom validator được áp dụng cho đúng form.
- Ba nhóm test: full-context, `@WebMvcTest` import cùng config, standalone chỉ ra cách tái sử dụng conversion config.

Mục đích không phải xây hệ thống đăng ký thật. Không có database, API security hay phân quyền thật; mọi response đều được tạo tại controller để cô lập sự khác nhau của binding và validation.

### 6.1. Cấu trúc dự án

```text
binding-parity/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── BindingParityApplication.java
    │   ├── MemberCode.java
    │   ├── MemberCodeConverter.java
    │   ├── RegistrationBindingConfig.java
    │   ├── RegistrationForm.java
    │   ├── RegistrationPolicyValidator.java
    │   └── RegistrationController.java
    └── test/java/demo/
        ├── RegistrationApplicationTest.java
        ├── RegistrationSliceTest.java
        └── RegistrationStandaloneTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>binding-parity</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` kích hoạt Spring MVC (Servlet stack). `spring-boot-starter-validation` cung cấp Jakarta Validation provider; `spring-boot-starter-test` chứa JUnit 5 và MockMvc. Spring Boot parent đồng bộ phiên bản Spring/Jackson/Validator để tránh khai báo những phiên bản không tương thích thủ công.

### 6.3. BindingParityApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingParityApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingParityApplication.class, args);
    }
}
```

Main class nằm trong package `demo`, nên component scanning tìm thấy `RegistrationBindingConfig` và `RegistrationController` cùng package trong full context.

### 6.4. MemberCode.java

```java
package demo;

public record MemberCode(String value) {}
```

Record đóng gói mã đã chuyển đổi. Ví dụ để converter đảm nhận kiểm tra format và chuẩn hóa; record không tự đổi lowercase thành uppercase. Chính vì vậy test phải quan sát kết quả sau khi đi qua MVC conversion service, thay vì chỉ kiểm tra Java class có thể được khởi tạo.

### 6.5. MemberCodeConverter.java

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class MemberCodeConverter
        implements Converter<String, MemberCode> {

    @Override
    public MemberCode convert(String source) {
        String normalized =
                source.strip().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{2}-[0-9]{2}")) {
            throw new IllegalArgumentException(
                    "memberCode must match AA-00");
        }

        return new MemberCode(normalized);
    }
}
```

Các input ví dụ:

| Chuỗi request | Giá trị `MemberCode.value()` sau conversion |
| --- | --- |
| `" ab-12 "` | `"AB-12"` |
| `"XY-09"` | `"XY-09"` |
| `"xx"` | Lỗi conversion |
| `"ABC-12"` | Lỗi conversion |
| `"AB-1"` | Lỗi conversion |

Pattern cố định chỉ phục vụ demo. Trong production, contract có thể sử dụng kiểu value object khác, kiểm tra chữ số và thông báo được localization. **Converter không thay thế authorization**, và input từ client vẫn không đáng tin cho tới khi hệ thống kiểm tra đầy đủ.

### 6.6. RegistrationBindingConfig.java

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class RegistrationBindingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new MemberCodeConverter());
    }
}
```

Đây là **nguồn cấu hình chung** dùng trong production lẫn test. `WebMvcConfigurer#addFormatters` bổ sung converter/formatter vào MVC conversion infrastructure. Không copy logic `convert(...)` vào controller hay test.

**Vì sao chọn `@Configuration`?** Full application context sẽ phát hiện nó qua component scanning. Với MVC slice, chúng ta dùng `@Import(RegistrationBindingConfig.class)` để diễn đạt rõ rằng converter đó **bắt buộc** cho contract của controller. Khi standalone, ta có thể gọi method `addFormatters(...)` trên cùng class.

### 6.7. RegistrationForm.java

```java
package demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @NotNull
    private MemberCode memberCode;

    // Cố ý có setter để chứng minh allowedFields ngăn ghi đè.
    private String role = "USER";

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public MemberCode getMemberCode() {
        return memberCode;
    }

    public void setMemberCode(MemberCode memberCode) {
        this.memberCode = memberCode;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

Dùng `Integer` để phân biệt thiếu giá trị (null, `@NotNull`) với tuổi nhỏ (`@Min`). Khi nhận `age=abc`, binder không chuyển được thành số nguyên và có thể ghi `typeMismatch` vào `BindingResult`; đó là lỗi binding, không phải Jakarta `@Min`.

Trạng thái `role="USER"` được cố ý đưa vào DTO để test việc suppress `role=ADMIN`. **Trong ứng dụng thật, tốt hơn là không có setter role trên form nhận từ Internet**; dùng DTO chuyên biệt, rồi map sang domain object sau authorization.

### 6.8. RegistrationPolicyValidator.java

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class RegistrationPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;

        if ("admin".equalsIgnoreCase(form.getName())) {
            errors.rejectValue(
                    "name",
                    "name.reserved",
                    "Name is reserved"
            );
        }
    }
}
```

`RegistrationPolicyValidator` dùng giao diện Spring `Validator`, khác với `jakarta.validation.Validator`. Nó được đăng ký vào `WebDataBinder` qua `addValidators(...)`. Validator này tạo field error; không tự xử lý HTTP.

Một số rule cần database hay I/O không nên đặt vào validator thực thi blocking trên event loop; ví dụ hiện tại là Spring MVC Servlet và kiểm tra in-memory, nên không có I/O. Với business validation phụ thuộc database, thường tốt hơn là xử lý tại service sau khi input đã qua binding/constraint cơ bản.

### 6.9. RegistrationController.java

```java
package demo;

import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    @InitBinder("registration")
    public void initRegistration(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "memberCode");
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(false));
        binder.addValidators(new RegistrationPolicyValidator());
    }

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> register(
            @Valid @ModelAttribute("registration")
                    RegistrationForm form,
            BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            List<String> names = Arrays.stream(
                    result.getSuppressedFields())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "SUPPRESSED_FIELDS",
                    "fields", names
            ));
        }

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            List<String> bindingFailures =
                    result.getFieldErrors().stream()
                            .filter(FieldError::isBindingFailure)
                            .map(FieldError::getField)
                            .distinct()
                            .sorted()
                            .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_FORM",
                    "fields", fields,
                    "bindingFailures", bindingFailures
            ));
        }

        return ResponseEntity.ok(Map.of(
                "code", "OK",
                "name", form.getName(),
                "age", form.getAge(),
                "memberCode", form.getMemberCode().value(),
                "role", form.getRole()
        ));
    }
}
```

Tại sao dùng objectName `registration`? Vì `@InitBinder("registration")` chỉ chọn đúng binder có tên đó. Nếu đổi `@ModelAttribute("registration")` thành `@ModelAttribute("form")` mà không đổi initializer, các thiết lập allowlist/editor/custom validator có thể không áp dụng nữa.

**Những bảo đảm mà test cần chứng minh:**

1. `name` được trim bởi custom `StringTrimmerEditor(false)`.
2. `memberCode` được chuyển bằng converter global của `RegistrationBindingConfig`.
3. `age` được chuyển thành `Integer`, có constraint `@Min(18)`.
4. `@Valid` kích hoạt Jakarta Validation của form; Spring `Validator` riêng thêm rule cho tên `admin`.
5. `role` không được bind, và request cố gắng gửi field đó bị controller từ chối dựa trên `getSuppressedFields()`.
6. `BindingResult` nằm ngay sau `@ModelAttribute` để controller có thể xem lỗi thay vì Spring bắt buộc trả exception mặc định.
7. Response thành công phản ánh **giá trị thực tế sau binding**, không phản ánh raw request string.

Controller trả JSON để test dễ quan sát, nhưng **request input là form-urlencoded**. Không nhầm điều này với việc Jackson deserialize JSON `@RequestBody`; `allowedFields` và `StringTrimmerEditor` ở đây tác động vào property binding của form object.

### 6.10. RegistrationApplicationTest.java — kiểm thử full context

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void productionConfigConvertsAndTrims() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "  Lan  ")
                        .param("age", "20")
                        .param("memberCode", " ab-12 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("OK"))
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.memberCode").value("AB-12"))
                .andExpect(jsonPath("$.age").value(20))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void jakartaMinConstraintIsActive() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "17")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields", hasItem("age")));
    }

    @Test
    void springValidatorIsActive() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "admin")
                        .param("age", "20")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields", hasItem("name")));
    }

    @Test
    void unknownBusinessFieldIsSuppressed() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "20")
                        .param("memberCode", "AB-12")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void wrongMemberCodeIsBindingFailure() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "20")
                        .param("memberCode", "bad"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.bindingFailures",
                        hasItem("memberCode")));
    }

    @Test
    void missingAgeViolatesNotNull() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("age")));
    }
}
```

Sáu test integration này xác nhận conversion, trimming, constraint Jakarta, custom Spring Validator, allowlist và binding failure bằng **request thực qua DispatcherServlet test infrastructure**, không gọi trực tiếp controller.

### 6.11. RegistrationSliceTest.java — cùng config trong MVC slice

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@Import(RegistrationBindingConfig.class)
class RegistrationSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void sliceUsesProductionConverterAndLocalBinder() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", " Lan ")
                        .param("age", "21")
                        .param("memberCode", " xy-09 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.memberCode").value("XY-09"));
    }

    @Test
    void sliceKeepsAllowedFieldsPolicy() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "21")
                        .param("memberCode", "AB-12")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void sliceRetainsCustomSpringValidation() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "admin")
                        .param("age", "21")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("name")));
    }

    @Test
    void sliceRetainsJakartaValidation() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "17")
                        .param("memberCode", "AB-12"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("age")));
    }
}
```

`@Import(RegistrationBindingConfig.class)` là điểm quan trọng: nó đăng ký **cùng class sản xuất converter**, thay vì một converter test-only. Test slice còn lấy được local `@InitBinder("registration")` từ controller mà nó tải, nên allowed fields, String trimming và policy validator vẫn cần hoạt động.

Slice ở đây không phụ thuộc service/repository ngoài controller; nếu project thật có constructor injection vào controller, nên dùng mock/test bean hoặc import dependency cần thiết theo đúng mục tiêu test. **Không dùng mock converter có behavior khác production** chỉ để làm test qua.

### 6.12. RegistrationStandaloneTest.java — tái sử dụng config khi cần standalone

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RegistrationStandaloneTest {

    private MockMvc mvc;

    @BeforeEach
    void createMvcUsingRealBinderRules() {
        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();

        // Tái sử dụng method production,
        // không định nghĩa lại logic convert trong test.
        new RegistrationBindingConfig()
                .addFormatters(conversionService);

        // Tạo Jakarta Validator cho standalone infrastructure.
        LocalValidatorFactoryBean validator =
                new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        mvc = MockMvcBuilders
                .standaloneSetup(new RegistrationController())
                .setConversionService(conversionService)
                .setValidator(validator)
                .build();
    }

    @Test
    void standaloneConvertsUsingProductionConfig() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", " Lan ")
                        .param("age", "20")
                        .param("memberCode", " ab-12 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.memberCode").value("AB-12"));
    }

    @Test
    void standaloneStillUsesLocalInitBinder() throws Exception {
        mvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("age", "20")
                        .param("memberCode", "AB-12")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"));
    }
}
```

Đây là một test standalone có cấu hình thiết yếu **được truyền rõ ràng**:

- Dùng `DefaultFormattingConversionService` làm cơ sở với các converter thông thường, rồi gọi lại production `addFormatters(...)` để thêm `MemberCodeConverter`.
- Dùng `LocalValidatorFactoryBean` vì standalone không tự được nạp global Jakarta Validation provider từ toàn bộ Boot context.
- Dùng `RegistrationController` thật để local `@InitBinder("registration")` vẫn chạy.
- Không nạp `@ControllerAdvice`, cấu hình security filter, custom `HandlerMethodArgumentResolver` hoặc mọi thứ khác từ runtime nếu không đăng ký thêm.

**Không coi standalone như bản sao toàn diện production**. Hai test ở đây chỉ chứng minh những đường đã tự cấu hình. Một dự án có nhiều MVC customizations phải có ít nhất một suite full-context để bắt thiếu component, annotation scan, profile và wiring. Nếu đang gặp vấn đề không xác định, nên ưu tiên `@SpringBootTest`/`@AutoConfigureMockMvc` hoặc `webAppContextSetup(wac)` thay vì tạo một standalone environment gần giống nhưng không đúng.

### 6.13. Chạy toàn bộ bài kiểm thử

Với Java 17+ và Maven tại thư mục chứa `pom.xml`:

```bash
mvn -q clean test
```

**Kỳ vọng:** tổng cộng **12 test** pass (6 full-context + 4 slice + 2 standalone), Maven kết thúc exit code 0 khi dependencies và môi trường được cung cấp đầy đủ. Đây là **kết quả dự kiến từ thiết kế kiểm thử**, không phải một stdout đã đo được trên máy; build thật cần được chạy để xác nhận. Không ràng buộc chuỗi output Maven/JUnit cố định vì version Surefire/logging có thể thay đổi.

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Gửi form hợp lệ:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name= Lan ' \
  --data-urlencode 'age=20' \
  --data-urlencode 'memberCode= ab-12 '
```

HTTP 200 body dự kiến:

```json
{
  "code": "OK",
  "name": "Lan",
  "age": 20,
  "memberCode": "AB-12",
  "role": "USER"
}
```

Thử field không được phép:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Lan' \
  --data-urlencode 'age=20' \
  --data-urlencode 'memberCode=AB-12' \
  --data-urlencode 'role=ADMIN'
```

HTTP 400 body dự kiến:

```json
{
  "code": "SUPPRESSED_FIELDS",
  "fields": ["role"]
}
```

Nếu gửi `age=abc`, Spring không chuyển thành `Integer`, controller nhận `BindingResult` có lỗi conversion và trả `INVALID_FORM`. Nếu gửi `memberCode=bad`, converter đã đăng ký sẽ ném lỗi conversion; `bindingFailures` chứa `memberCode`. Nếu gửi `name=admin`, custom Spring Validator ghi field error, cũng trả `INVALID_FORM`.

**Giữ ổn định kết quả test:** thay vì so nguyên văn message nội suy phụ thuộc locale, các test chủ yếu kiểm tra status, field name, marker `bindingFailures` và normalized value. Thứ tự keys trong JSON object không được bảo đảm.

## 7. Tại sao cùng nguồn cấu hình vẫn có thể khác hành vi?

### 7.1. Khác Spring profile / application properties

Runtime có thể bật profile `prod`, còn test dùng profile `test`. Một `@Profile("prod")` trên bean cấu hình MVC hoặc một property conditional có thể khiến converter chỉ tồn tại trong môi trường thật. Đó có thể là **sự khác biệt chủ ý**, nhưng cần một integration test chạy dưới profile tương ứng để kiểm chứng.

Nếu converter là phần của **API contract chung**, không nên tùy tiện đánh dấu nó chỉ thuộc profile test hoặc chỉ thuộc profile production. Nếu thực sự có feature flag làm thay đổi contract, hãy có test cho **cả hai nhánh**.

### 7.2. Test override một bean ConversionService

Một test có thể định nghĩa `@TestConfiguration` hoặc `@Primary ConversionService` bean khác, khiến MVC sử dụng configuration khác production. Tương tự, `@MockBean`/`@MockitoBean` có thể thay service và vô tình ảnh hưởng validator phụ thuộc service.

Nên mock **business collaborator** cần thiết, không mock chính converter/validator đang muốn chứng minh. Với conversion service, dùng cấu hình production hoặc factory dùng chung có cấu hình rõ ràng.

### 7.3. Khác Locale/TimeZone

Formatter chuyển đổi ngày, tiền tệ, số thập phân phụ thuộc `Locale` hoặc `TimeZone`. Ví dụ `1,234` có thể có nghĩa khác theo locale. Không nên dựa vào locale mặc định của máy CI.

Trong MockMvc, chỉ rõ locale khi test semantics phụ thuộc ngôn ngữ:

```java
mvc.perform(post("/amounts")
        .locale(Locale.GERMANY)
        .param("amount", "1,23"));
```

Đây là fragment, endpoint và kiểu `AmountForm` cần được định nghĩa trong ứng dụng khác. Đặt locale rõ ràng cùng với formatter production; không biến kết quả parse của máy local thành contract ngầm. Với timezone, nên dùng UTC hoặc zone tường minh khi API yêu cầu.

### 7.4. Khác request Content-Type

`@ModelAttribute` thường bind từ query/form parameters. Nếu test đang gửi:

```java
post("/registrations")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Lan\"}");
```

thì đó **không phải request tương đương** với form-urlencoded dùng `.param("name","Lan")`. Với `@RequestBody`, Jackson thực hiện JSON deserialization; `WebDataBinder#setAllowedFields` không lọc JSON property trước khi Jackson khởi tạo DTO như khi property-binding form.

Không sửa test bằng cách đổi content type ngẫu nhiên chỉ để nhận status mong muốn. Test phải có **media type đúng với API contract**.

### 7.5. Khác tên @ModelAttribute

Nếu controller dùng `@InitBinder("registration")`, test riêng tạo binder:

```java
WebDataBinder binder =
        new WebDataBinder(new RegistrationForm(), "form");
```

thì objectName là `form`, **không phải `registration`**. Nếu test chủ động gọi một initializer bằng tay rồi gắn dữ liệu, nó đang bỏ qua cơ chế chọn init-binder theo objectName của MVC. Hãy dùng handler thật với `@ModelAttribute("registration")` hoặc xác định rõ phạm vi của test đơn vị.

### 7.6. Khác controller/advice scan

`@ControllerAdvice` có thể chứa `@InitBinder` toàn cục, `@ExceptionHandler` hoặc `@ModelAttribute`. `@WebMvcTest` có thể tự đưa một số advice vào slice, nhưng standalone cần `setControllerAdvice(...)` nếu muốn dùng advice đó. Nếu test không có advice, đường HTTP status/error body có thể khác dù binding thành công hoặc thất bại theo cùng quy tắc.

Một advice cũng có **selector giới hạn controllers**: `assignableTypes`, `basePackages`, `annotations`. Nếu test cấu hình advice với controller khác, initializer có thể không chạy. Cần test cả controller được chọn và controller bị loại khi logic phụ thuộc selector.

### 7.7. Khác validators

`@Valid` không tự thực thi mọi constraint trong một test gọi trực tiếp Java method. MVC cần validator và cơ chế argument-resolution kích hoạt nó. Trong standalone, hãy cấu hình `LocalValidatorFactoryBean` hoặc một Spring `Validator` thích hợp; trong full context, `spring-boot-starter-validation` cung cấp provider được cấu hình.

Nếu test chỉ chạy controller method trực tiếp:

```java
RegistrationController controller = new RegistrationController();
// Không thể tự động dựng BindingResult / @ModelAttribute như MVC.
```

thì đây chỉ là bước khởi tạo object. Không có `DispatcherServlet`/argument resolver, không chứng minh converter hay @InitBinder hoạt động.

## 8. Kiểm thử binder riêng bằng DataBinder: lợi ích và giới hạn

Một kiểm thử trực tiếp `WebDataBinder`/`DataBinder` hữu ích khi cần cô lập một rule:

```java
RegistrationForm form = new RegistrationForm();
WebDataBinder binder =
        new WebDataBinder(form, "registration");

binder.setAllowedFields("name", "age", "memberCode");
binder.bind(new MutablePropertyValues(Map.of(
        "name", "Lan",
        "age", "20",
        "role", "ADMIN"
)));
```

Đây là fragment thử API binder, cần các imports Spring tương ứng. Vì fragment **chưa đăng ký converter, editor và validator theo cấu hình production**, nó chỉ chứng minh phần allowlist được thiết lập thủ công, **không** chứng minh toàn bộ controller binding parity.

Nếu muốn test converter độc lập, cũng có thể dùng:

```java
MemberCode result =
        new MemberCodeConverter().convert(" ab-12 ");
// result.value() == "AB-12"
```

Test này có giá trị cho **logic converter**, nhưng **không chứng minh converter đã được đăng ký vào MVC ConversionService**. Đó là lý do test integration ở phần 6 cần assert output qua endpoint.

Một chiến lược test tốt gồm:

1. Unit tests cho converter/formatter/validator khi logic phức tạp.
2. Một hoặc vài MVC slice tests xác nhận cấu hình được nối với controller.
3. Full-context integration tests cho binding contract quan trọng.
4. Nếu đặc tính liên quan browser thật, security filters hoặc reverse proxy, bổ sung HTTP end-to-end test tại môi trường thích hợp.

## 9. Đồng bộ giữa Spring Validator và Jakarta Bean Validation

Trong MVC, hai loại validation có thể cùng tham gia:

| Thành phần | Đăng ký | Mục tiêu |
| --- | --- | --- |
| Jakarta `@NotBlank`/`@Min` | Constraint trên DTO + `@Valid`/`@Validated` + provider | Quy tắc khai báo trên model |
| Spring `Validator` | `@InitBinder#addValidators(...)` hoặc global config | Quy tắc tùy chỉnh, ghi lỗi vào `Errors` |
| `BindingResult` | Được Spring tạo gắn với model attribute | Tổng hợp lỗi binding/validation, suppressed fields |
| Business policy trong service | Gọi tường minh sau input validation | Ràng buộc nghiệp vụ hoặc liên quan persistence |

`@InitBinder("registration")` gọi `addValidators(new RegistrationPolicyValidator())`, nên Spring MVC có thể chạy validator bổ sung trong quá trình validation của command object. Nên dùng **`addValidators`** để kết hợp với global validator; `setValidator` đặt validator đơn và có thể thay thế danh sách đã được cấu hình, dẫn đến lệch giữa ứng dụng và test nếu không kiểm soát.

Một sai lầm khác là dùng cùng tên `Validator` nhưng khác package:

- `org.springframework.validation.Validator`: có `supports(Class<?>)` và `validate(Object, Errors)`.
- `jakarta.validation.Validator`: có `validate(Object, Class<?>... groups)` và trả về `Set<ConstraintViolation<T>>`.

Chúng phục vụ các API khác nhau. Spring có adapter tích hợp Jakarta Validation vào MVC, nhưng không nên tự tạo lớp giả cùng interface rồi xem như toàn bộ wiring thật đã được kiểm chứng.

## 10. Đồng bộ custom binders qua @ControllerAdvice và global config

Với nhiều controller, có thể chia hai loại cấu hình:

### 10.1. Configuration áp dụng chung

Dùng `WebMvcConfigurer#addFormatters` cho converter/formatter không phụ thuộc một form cụ thể. Ví dụ `MemberCodeConverter` chuẩn hóa một value-object, nên đăng ký global là hợp lý nếu các endpoint cùng hợp đồng format.

Nếu converter chỉ có ý nghĩa cho **một field rất đặc thù**, có thể đăng ký custom editor trong `@InitBinder("objectName")`. Khi đó test phải dùng đúng binder name và bean controller/advice tương ứng.

### 10.2. Binder policy theo controller/attribute

```java
@ControllerAdvice(assignableTypes = RegistrationController.class)
public class RegistrationBinderAdvice {

    @InitBinder("registration")
    public void init(WebDataBinder binder) {
        binder.setAllowedFields("name", "age", "memberCode");
    }
}
```

Đây là **fragment minh họa phương án chuyển policy ra advice**, **không được thêm vào project runnable ở phần 6** vì sẽ trùng `@InitBinder` local của `RegistrationController`. `assignableTypes` chọn controller nhận advice, còn `@InitBinder("registration")` chọn binder có objectName đúng.

Khi chuyển config từ controller sang advice:

- Cập nhật test slice để bảo đảm advice có trong context (hoặc import nó).
- Nếu standalone, đăng ký advice bằng `.setControllerAdvice(new RegistrationBinderAdvice())`.
- Không để cả local và global cùng gọi `setAllowedFields(...)` với giá trị xung đột; global init-binder thường được áp dụng trước local binder, nên cần quy tắc sở hữu rõ ràng.
- Kiểm tra lại `BindingResult.getSuppressedFields()` và negative test cho field nhạy cảm.

Test nên **phát hiện việc thiếu advice**, không tạo bản test-specific advice có chính sách khác để “vá” lỗi.

## 11. Những hiện tượng drift nguy hiểm cần test

### 11.1. Test vô tình nới lỏng allowedFields

Trong production:

```java
binder.setAllowedFields("name", "age", "memberCode");
```

Trong một test tự tạo binder, nếu không dùng allowlist thì mặc định property binding có thể cập nhật mọi public writable property phù hợp; `role=ADMIN` trở thành nguy cơ. Chạy một **negative test** có thêm field ngoài allowlist qua endpoint thật, và khẳng định controller trả response thích hợp.

`getSuppressedFields()` cho biết field bị bỏ qua; **nó không nhất thiết làm `hasErrors()` tự trả true**. Ví dụ runnable chủ động trả `SUPPRESSED_FIELDS` nếu mảng này không rỗng.

### 11.2. Converter test pass nhưng converter không được register

Unit test:

```java
assertEquals(
        "AB-12",
        new MemberCodeConverter().convert(" ab-12 ").value()
);
```

Đây là fragment JUnit, cần static import `Assertions.assertEquals`. Nó chỉ chứng minh **hàm convert**. Nếu `RegistrationBindingConfig` không được nạp vào MVC, API có thể giữ giá trị chưa chuẩn hóa hoặc gây lỗi type conversion tùy converter mặc định. Muốn phát hiện, test MVC cần gửi input `" ab-12 "` rồi assert output `"AB-12"`.

### 11.3. Chỉ test happy path

Một form có thể cho 200 với input đúng trong cả môi trường thiếu validation. Vì vậy test phải có **các giá trị cố ý sai**:

- `age=17`: xác nhận Jakarta `@Min`.
- `age=abc`: xác nhận type conversion error.
- `name=admin`: xác nhận Spring custom Validator.
- `role=ADMIN`: xác nhận allowed-fields.
- `memberCode=bad`: xác nhận custom converter reject format.
- `name=   `: xác nhận trimming + `@NotBlank`.

Test tốt kiểm tra **trạng thái sau binding và nhánh lỗi**, không chỉ mã HTTP mặc định.

### 11.4. Dùng @WebMvcTest nhưng controller có collaborators không được import

Nếu controller cần service qua constructor, slice không tự scan đầy đủ service/repository. Nên dùng test double theo đúng Spring Boot version (ví dụ `@MockitoBean` trong bản Spring Framework/Boot hỗ trợ) hoặc import một service đơn giản. Nhưng không mock **chính binding config** đang cần được xác minh.

### 11.5. Dùng standalone test như integration proof duy nhất

Standalone thường không có filter chain, global controller advice, full MVC configuration, LocaleResolver hoặc các bean đặc thù. Đừng chỉ thấy standalone pass rồi kết luận “mọi request production đều bind đúng”. Spring Framework docs khuyến nghị kết hợp integration tests hoặc sử dụng `webAppContextSetup(wac)` khi cần chứng minh behavior cấu hình thật.

### 11.6. Dùng JSON để kiểm tra form rules

Dữ liệu `@RequestBody` được Jackson deserialize; các `setAllowedFields` property-binding rules của `@ModelAttribute` không phải JSON field whitelist. Chỉ so sánh hai kiểu khi mục tiêu là xác định **hai contract khác nhau**. Không gán trực tiếp logic `_checkbox`, `!defaultField` hoặc editor cho mọi JSON deserialization.

### 11.7. Chênh lệch timezone, định dạng ngày

Với `LocalDate`, `ZonedDateTime`, `BigDecimal`, hoặc tiền tệ, test cần kiểm tra locale, timezone và formatter. Một bài test chỉ parse `2026-01-01` trong locale mặc định có thể bỏ sót khác biệt với input địa phương hóa. Ưu tiên ISO format trong API nếu không có lý do khác, và khai báo formatter/locale rõ ràng.

## 12. Test matrix có thể dùng cho dự án thật

| Nhánh kiểm thử | Full context | MVC slice | Standalone | Điều cần xác minh |
| --- | --- | --- | --- | --- |
| Request hợp lệ | Có | Có | Có | Giá trị sau conversion và status |
| Global converter/formatter | **Bắt buộc nếu là contract** | Import thật | Tự register nếu sử dụng | ConversionService production có hiệu lực |
| Local @InitBinder | Có | Có | Có thể có | objectName và initializer đúng |
| Global @ControllerAdvice binder | Có | Import/scan theo scope | Đăng ký thủ công | Advice đúng tập controller |
| Jakarta constraints | Có | Có với provider | Set Validator | `@Valid` không bị bỏ qua |
| Custom Spring Validator | Có | Có | Có nếu binder được chọn | Rule độc lập với Jakarta |
| Suppressed fields | Có | Có | Có | Ngăn mass assignment |
| Wrong type / typeMismatch | Có | Có | Có nếu conversion đồng bộ | Phân biệt binding vs constraint |
| Message localization | Test locale | Test locale | Tự cấu hình | MessageSource/Locale |
| Security filters | Theo config | Slice có thể khác | Không tự có | Authorization/CSRF test riêng |
| Actual HTTP/network behavior | Không (MockMvc) | Không | Không | Thêm test qua port thật khi cần |

Không nhất thiết chạy mọi ô ma trận cho mọi service. Nhưng **những quy tắc mang tính bảo mật hoặc API contract** như allowlist, validation và conversion phải có ít nhất một kiểm chứng qua infrastructure gần thực tế.

## 13. Chiến lược tổ chức test để tránh trùng lặp

Một dự án lớn có thể tổ chức:

```text
src/main/java/...
  web/RegistrationBindingConfig.java
  web/RegistrationController.java
  validation/RegistrationPolicyValidator.java
  type/MemberCodeConverter.java

src/test/java/...
  conversion/MemberCodeConverterTest.java
  web/RegistrationSliceTest.java
  web/RegistrationApplicationTest.java
  web/RegistrationStandaloneTest.java
```

**Không nên** chép lại hàng chục test giống hệt vào cả ba lớp. Có thể chọn:

1. Unit test cho các quy tắc converter/validator đặc thù, nhanh.
2. Slice test cho các điều kiện controller/argument resolver cần kiểm chứng.
3. Integration test cho **wiring và parity** ở những path trọng yếu.
4. Standalone test chỉ khi nó giúp debug hoặc giảm chi phí cho các logic đơn giản.

Nếu dùng abstract test contract cho nhiều MVC setups, phải bảo đảm setup của mỗi class vẫn có một nguồn config xác định; không tạo abstract base class tự khởi tạo một ConversionService giả làm mất ý nghĩa integration test.

Một mẫu “canary test” rất hữu ích: gửi một input đòi **converter production** như mã lowercase có spaces, rồi kiểm tra response uppercase. Nếu `@WebMvcTest` bị refactor và thiếu `@Import`, test báo khác biệt ngay.

## 14. Hướng dẫn khắc phục khi test và runtime khác nhau

Đi từ request tới binder, không chỉ dò exception cuối:

1. **Xác minh request shape:** method, path, content type, body, query/form parameters, headers và locale.
2. **Xác minh controller handler:** mapping nào thật sự được chọn? Có `@ModelAttribute("registration")` cùng objectName không?
3. **Xác minh binder creation:** local `@InitBinder` hoặc global advice có được gọi không?
4. **Xác minh conversion:** MVC `ConversionService` có đúng converter/formatter production không? Hãy assert normalized values.
5. **Xác minh allowedFields:** field ngoài allowlist có bị suppress không? Controller có chủ động từ chối không?
6. **Xác minh validation provider:** `@Valid`/`@Validated` có chạy, đúng group, đúng Validator không?
7. **Xác minh custom Spring Validators:** `supports(...)` đúng class, `addValidators(...)` áp vào đúng binder không?
8. **Xác minh test slice import:** `@WebMvcTest` có import config cần thiết, advice phù hợp và collaborators không?
9. **Xác minh standalone setup:** có `setConversionService`, `setValidator`, `setControllerAdvice` khi cần không?
10. **Xác minh profiles/config overrides:** những config được conditional theo profile, property hoặc test annotation có bị thiếu không?
11. **Xác minh BindingResult:** lỗi field, lỗi global, `isBindingFailure()` và `getSuppressedFields()`; không chỉ xem `hasErrors()`.
12. **Chạy một full-context test** trên cùng payload của test slice/standalone để phân biệt “business bug” với “hạ tầng test lệch”.

### Ví dụ lỗi parse không phải constraint

Request `age=abc` trong form-urlencoded thường tạo lỗi conversion cho `Integer age`. Dù `@Min(18)` tồn tại, đây không phải “số nhỏ hơn 18”. Cần xem `FieldError#isBindingFailure`. Với JSON `@RequestBody` có field `age="abc"`, lỗi có thể phát sinh từ Jackson/HTTP message converter trước controller và không cùng loại `BindingResult`; không suy từ một pipeline sang pipeline khác.

### Gợi ý khi lỗi chỉ xuất hiện trên CI

Kiểm tra Java version, Spring Boot BOM versions, maven dependency tree, locale, timezone, profile, active environment properties và cache context. Đừng sửa độ nghiêm ngặt của validator cho “phù hợp CI” trước khi xác nhận **cùng một binding config** đang thực sự được sử dụng.

## 15. Bảo mật: binding parity là một phần của input contract

Binding không chỉ là tiện ích chuyển kiểu. Nếu production dùng allowlist nhưng test không có allowlist, test có thể bỏ sót **mass assignment** (client ghi đè field không nên được phép). Vì vậy, parity của binder config liên quan trực tiếp đến bảo mật.

Các nguyên tắc:

- Dùng DTO chuyên biệt thay vì bind trực tiếp JPA entity có setter cho `role`, `balance`, `ownerId` hoặc `status`.
- Dùng `setAllowedFields(...)` khi cần property binding để hạn chế public writable fields.
- Không dựa vào `setDisallowedFields(...)` với một blacklist không đầy đủ như bảo vệ duy nhất.
- Với constructor/record binding, chỉ cho constructor nhận các fields thuộc request contract; `allowedFields` chủ yếu giới hạn **property binding**.
- Xem `getSuppressedFields()` và có negative test gửi field không được phép.
- Validation constraint không thay thế authorization: một `role=ADMIN` hợp lệ về kiểu vẫn phải không được phép nếu caller không có quyền.
- Không log toàn bộ rejected values từ `FieldError`; chúng có thể chứa thông tin nhạy cảm.
- Nếu dùng Spring Security CSRF protection trên form, test cần thêm CSRF token theo đúng security config; không tắt bảo mật trong test chỉ để bỏ lỗi 403 rồi coi response 200 là bằng chứng binder đúng.
- Không xử lý user input lỗi bằng cách âm thầm đổi mọi exception thành 200; test cần kiểm tra status + error code.

## 16. Checklist hoàn thiện

- [ ] Có **một class production** sở hữu converter/formatter, được tái sử dụng trong test.
- [ ] `@InitBinder` nằm ở controller/advice có phạm vi rõ ràng và objectName khớp.
- [ ] `@WebMvcTest` import các cấu hình ứng dụng quan trọng không được slice tự đưa vào.
- [ ] Standalone test đăng ký MVC infrastructure cần thiết, không giả vờ có full context.
- [ ] Có ít nhất một `@SpringBootTest + @AutoConfigureMockMvc` xác nhận wiring của request quan trọng.
- [ ] Assert **giá trị sau conversion**, không chỉ status 200.
- [ ] Có test cho Jakarta constraint và Spring custom Validator.
- [ ] Có test input sai kiểu và phân biệt `isBindingFailure()`.
- [ ] Có test gửi field ngoài allowlist và kiểm tra suppressed fields.
- [ ] Không dùng JSON request để thay cho form-urlencoded contract.
- [ ] Kiểm tra locale/timezone/profiles nếu các giá trị này ảnh hưởng binding.
- [ ] Nếu chuyển cấu hình sang `@ControllerAdvice`, cập nhật test slice/standalone để dùng đúng advice.
- [ ] Giữ test độc lập với thông điệp lỗi phụ thuộc ngôn ngữ và thứ tự field không bảo đảm.
- [ ] Không sao chép production conversion logic trong test-specific mock.
- [ ] Trước khi release, chạy bộ integration tests trên profile/dependency set gần với môi trường triển khai.

## 17. Kết luận

**Đồng bộ cấu hình binding không có nghĩa mọi test phải dùng full application context.** Nó có nghĩa các test cần chứng minh input contract phải sử dụng **đúng các cấu hình production liên quan**, ở mức phù hợp:

- `@SpringBootTest + @AutoConfigureMockMvc` xác nhận wiring gần ứng dụng chạy thật.
- `@WebMvcTest + @Import` cho phép kiểm tra web slice nhanh mà vẫn dùng **cấu hình production** rõ ràng.
- `standaloneSetup` hữu ích cho logic controller độc lập nhưng phải **cấu hình thủ công** converter/validator/advice khi chúng là phần của hành vi được kiểm thử.
- Unit test riêng của converter/validator chỉ chứng minh logic component, không chứng minh component đã được MVC sử dụng.

Bằng cách duy trì một nguồn cấu hình, đặt tên `@ModelAttribute`/`@InitBinder` nhất quán, kiểm thử cả successful conversion lẫn negative cases (constraint, conversion failure, suppressed fields), ta có thể phát hiện sớm sự chênh lệch giữa ứng dụng và môi trường test — đặc biệt là những lệch cấu hình có thể gây lỗi dữ liệu hoặc bảo mật.

## Tài liệu tham khảo

- [Spring Framework 6.2 — MockMvc Setup Options: WebApplicationContext vs Standalone](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html)
- [Spring Framework 6.2 — MVC @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — MVC Data Binding / Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — MVC @ModelAttribute Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — WebMvcConfigurer API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Boot 3.4 — WebMvcTest API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html)
- [Spring Framework — WebDataBinder API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
