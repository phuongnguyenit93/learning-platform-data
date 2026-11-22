# Đăng ký binder bằng @InitBinder trong Spring WebFlux

## 1. Mục tiêu: điều chỉnh binding cho đúng form, đúng controller

Trong Spring WebFlux, handler kiểu annotation thường nhận dữ liệu từ query string, form URL-encoded hoặc multipart qua `@ModelAttribute`. Framework tạo hoặc lấy đối tượng đích, trích xuất dữ liệu từ `ServerWebExchange`, rồi dùng `WebExchangeDataBinder` để chuyển kiểu, đi vào các property, ghi nhận lỗi binding và phối hợp với validation.

Nhưng mỗi form có quy tắc riêng:
- Chỉ cho người dùng sửa một vài property, không cho gán `admin` hoặc `approved`.
- Ngày sự kiện của một form phải có dạng `dd/MM/yyyy`.
- Danh sách input không được tự phát triển tới hàng nghìn phần tử.
- Ngoài `@NotBlank` và `@Min`, một form còn có quy tắc nghiệp vụ được kiểm tra bằng Spring `Validator`.
- Các controller khác có thể dùng quy tắc binding chung, nhưng không nên sao chép cùng cấu hình vào mọi endpoint.

**`@InitBinder` là điểm mở rộng (hook) để cấu hình `WebDataBinder` ngay trước khi binder được dùng cho một request argument/model attribute.** Nó không phải annotation đánh dấu handler URL; method `@InitBinder` thường nhận `WebDataBinder`, có kiểu trả về `void` và được framework gọi để đăng ký editor, formatter, validator hoặc chính sách cho phép binding.

Ví dụ ngắn:

~~~java
@RestController
class SignupController {

    @InitBinder("signupForm")
    void configureSignup(WebDataBinder binder) {
        binder.setAllowedFields("fullName", "age", "eventDate");
        binder.setAutoGrowCollectionLimit(5);
    }

    @PostMapping("/signups")
    String signup(@Valid @ModelAttribute("signupForm") SignupForm form,
                  BindingResult errors) {
        return errors.hasErrors() ? "invalid" : "accepted";
    }
}
~~~

Đoạn trên **minh họa** và cần thêm `SignupForm`, imports, các thành phần khác để chạy. Đặt tên `"signupForm"` ở cả `@InitBinder` và `@ModelAttribute` là chủ đích: binder chỉ nhận cấu hình local ấy khi object name khớp. Với DTO có setter `setAdmin(boolean)`, một trường request `admin=true` **không được property-bind** vì không nằm trong `allowedFields`.

Bài này tập trung vào **WebFlux 6.1/6.2** và ví dụ hoàn chỉnh dùng **Spring Boot 3.5.7, Spring Framework 6.2, Java 17**. Không nhầm với `@InitBinder` trên Servlet MVC dù API có điểm tương đồng.

## 2. Chuỗi xử lý: `ServerWebExchange` đến `@InitBinder` rồi tới handler

~~~text
Request đến WebFlux
   |
   v
DispatcherHandler -> RequestMappingHandlerAdapter
   |
   v
Tìm phương thức controller, phân giải tham số @ModelAttribute
   |
   +-- Tìm/tạo target object (constructor binding nếu áp dụng)
   |
   +-- Tạo WebExchangeDataBinder cho model attribute
   |      |
   |      +-- @ControllerAdvice @InitBinder (áp dụng trước)
   |      |
   |      +-- @Controller @InitBinder (áp dụng sau, có thể giới hạn tên)
   |      |
   |      +-- allowedFields, formatter/editor, validators, limits
   |
   +-- Tập hợp query/form/multipart và nguồn bổ sung phù hợp
   |
   +-- Property binding + conversion + BindingResult
   |
   +-- @Valid / @Validated: chạy validation nếu được yêu cầu
   |
   +-- Có BindingResult ngay sau đối tượng -> handler xử lý lỗi
   |    Không có -> thường WebExchangeBindException nếu object invalid
   |
   v
Gọi controller method, trả giá trị/MONO/HTTP response
~~~

Đây là biểu đồ **khái quát**. Với immutable object, Spring có thể thực hiện constructor binding trong quá trình khởi tạo target; cấu hình `allowedFields` áp dụng cho **property binding**, không tự động biến mọi tham số constructor thành danh sách bị chặn. Nếu method có direct Bean Validation constraints trên các tham số hoặc return value, Spring WebFlux 6.1+ có thể chuyển sang *method validation*, báo loại exception khác. Các chi tiết đó được phân biệt ở mục 9.

### Phân vai các thành phần

| Thành phần | Vai trò |
| --- | --- |
| `ServerWebExchange` | Context của một HTTP request/response; có query, `getFormData()`, `getMultipartData()`, attributes, session |
| `WebExchangeDataBinder` | Binder biết cách trích dữ liệu từ exchange theo reactive contract |
| `WebDataBinder` | Superclass/kiểu tham số thường dùng trong `@InitBinder`, có API register editor/formatter/validators |
| `DataBinder` | Nền tảng property/constructor binding, conversions, allowlist và `BindingResult` |
| `@ModelAttribute` | Khai báo handler argument là form/model object cần bind |
| `@InitBinder` | Phương thức cấu hình binder, không trực tiếp nhận request body làm dữ liệu nghiệp vụ |
| `@ControllerAdvice` | Cho phép tái sử dụng `@InitBinder` ở nhiều controller, có thể thu hẹp phạm vi |
| `@Valid` / `@Validated` | Yêu cầu kiểm tra constraints sau binding theo tích hợp thích hợp |
| `BindingResult` | Chứa binding/conversion/validation errors của model attribute tương ứng |

**Điều thường bị nhầm:** `@InitBinder` không buộc bạn tự gọi `binder.bind(exchange)`. Với một annotated controller, Spring đã quản lý bước đó. Nếu tự xây custom argument resolver thì mới cần chủ động tạo `WebExchangeDataBinder` và compose publisher trả từ `bind(exchange)`.

## 3. Khai báo `@InitBinder`: cú pháp, phạm vi, ràng buộc

### 3.1. Local binder trên controller

~~~java
@Controller
class FormController {

    @InitBinder
    void initAll(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(16);
    }

    // Các handler methods...
}
~~~

`@InitBinder` không có tên áp dụng cho các binder tương ứng trong phạm vi controller này. Khi chỉ muốn áp dụng cho một model attribute, truyền tên:

~~~java
@InitBinder("signupForm")
void initSignup(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "age", "eventDate");
}
~~~

Tên trong `value` là tên **command/form attribute hoặc request parameter** mà binder được dùng cho. Với `@ModelAttribute("signupForm")`, tên khớp một cách tường minh; **không dựa vào tên parameter Java ngầm định** khi có nhiều DTO cùng loại hoặc tên khác nhau.

Có thể đặt nhiều tên:

~~~java
@InitBinder({"signupForm", "profileForm"})
void initTheseForms(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(16);
}
~~~

Đây là các **phương án minh họa độc lập**; không chép tất cả vào cùng controller rồi vô tình ghi đè các thuộc tính binder. Trong code thực, mỗi `@InitBinder` nên có trách nhiệm dễ hiểu và tên đích nhất quán.

### 3.2. Chữ ký `@InitBinder` nên đơn giản và đồng bộ

Phương thức `@InitBinder` thường nhận `WebDataBinder`, kiểu trả về `void`:

~~~java
@InitBinder("signupForm")
void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "age", "eventDate", "topics[*]");
}
~~~

Không khai báo `Mono<Void>` trả từ `@InitBinder` và kỳ vọng Spring subscribe để hoàn tất cấu hình. Đây là điểm **đăng ký/cấu hình đồng bộ**; tính reactive nằm ở việc framework đọc dữ liệu HTTP, gọi binder và xử lý handler return type. Khi cần logic bất đồng bộ như truy vấn database, hãy thực hiện ở service/reactive pipeline, không nhét blocking I/O vào `@InitBinder`.

Theo hợp đồng của `@InitBinder`, phương thức không có giá trị trả về và không dùng command/form model objects hoặc `BindingResult` làm arguments. Các parameter kiểu request context có thể được hỗ trợ tùy handler argument resolvers, nhưng để dễ bảo trì nên dùng `WebDataBinder` và cấu hình phụ thuộc request đã được chứng minh là cần thiết; tránh dựa vào một kiểu `HttpServletRequest` của Servlet stack trong WebFlux.

### 3.3. Đăng ký ở `@ControllerAdvice`

~~~java
@ControllerAdvice
class SharedBindingAdvice {

    @InitBinder
    void common(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(8);
    }
}
~~~

Cấu hình này có thể áp dụng cho nhiều controllers. Spring WebFlux thực thi các `@InitBinder` từ **`@ControllerAdvice` trước**, rồi mới tới binder methods khai báo **local** trong controller. Nếu nhiều cấu hình cùng ghi một thuộc tính, thứ tự đó có thể ảnh hưởng kết quả; đừng dựa vào “ai sửa cuối cùng” như một chiến lược quản trị policy.

Thu hẹp advice:

~~~java
@ControllerAdvice(assignableTypes = SignupController.class)
class SignupOnlyAdvice {
    @InitBinder
    void common(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(8);
    }
}
~~~

`assignableTypes` chỉ áp dụng advice cho nhóm controller tương ứng; có thể chọn `basePackages`, `basePackageClasses` hoặc `annotations` theo kiến trúc. Selector của `@ControllerAdvice` là **phạm vi controller**; còn `@InitBinder("signupForm")` là **phạm vi object name**. Hai khái niệm độc lập.

### 3.4. Binder mỗi request, validator và state

Spring tạo binder phục vụ quá trình binding cụ thể, vì vậy cấu hình editor/formatter trên binder không yêu cầu chia sẻ một `SimpleDateFormat` mutable giữa nhiều threads. Tuy vậy, **instance `@ControllerAdvice`/controller có thể là singleton**, nên không lưu trạng thái của từng request vào fields của class advice.

Validator dùng lại có thể là bean singleton nếu thực sự stateless và thread-safe; ví dụ runnable bên dưới dùng class validator stateless.

## 4. Những API cần biết trên `WebDataBinder`

| API | Tác dụng | Ghi chú quan trọng |
| --- | --- | --- |
| `setAllowedFields("name", "items[*].code")` | Cho phép property binding theo path pattern | Case-sensitive; ưu tiên allowlist |
| `setDisallowedFields(...)` | Chặn một số fields | Dễ bỏ sót khi DTO tăng thuộc tính; không thay thế allowlist |
| `setDeclarativeBinding(true)` | Chỉ constructor binding theo mặc định, và property binding nếu có `allowedFields` | Không biến constructor args thành đối tượng đã được authorization |
| `setAutoGrowCollectionLimit(int)` | Giới hạn array/list auto-growth | Không phải HTTP size limit hay Map entry quota |
| `setAutoGrowNestedPaths(boolean)` | Điều chỉnh auto-grow nested properties | Áp dụng property binding, không áp chung mọi constructor binding |
| `registerCustomEditor(type, editor)` | Dùng `PropertyEditor` khi chuyển giá trị | Editor thường là per-binder, tránh share mutable instance |
| `addCustomFormatter(formatter)` | Bổ sung `Formatter` với parse/print | Có thể giới hạn theo field khi cần |
| `addValidators(Validator...)` | Bổ sung Spring validators | Không thay toàn bộ global validator một cách tùy tiện |
| `setValidator(validator)` | Đặt validator | Có thể thay validator khác; cân nhắc trước khi dùng |
| `setRequiredFields(...)` | Đánh dấu field phải xuất hiện trong property values | Khác `@NotNull` trên model sau khi binding |
| `getBindingResult()` | Kết quả binding/validation | Có `FieldError`, `ObjectError`, `getSuppressedFields()` |

### `setAllowedFields` và tên property path

~~~text
fullName
age
eventDate
topics[0]
topics[1]
addresses[0].city
settings[timezone]
~~~

Nếu muốn cho phép một số fields mà không cho phép toàn bộ object graph, dùng:

~~~java
binder.setAllowedFields(
    "fullName", "age", "eventDate", "topics[*]"
);
~~~

Pattern `*` là wildcard của Spring dùng cho tên field; `topics[*]` khớp các index như `topics[0]`. Với nested form có thể viết `addresses[*].city`, và với Map có thể viết `settings[timezone]`. Những patterns quá rộng như `*`, `addresses*` hoặc `settings*` có thể làm lộ property không mong đợi.

Các fields bị từ chối vì allowlist thường được ghi trong `BindingResult#getSuppressedFields()`, **không nhất thiết là `FieldError`**. Nếu request có `admin=true` nhưng controller chỉ cho phép các fields trên, `admin` sẽ bị suppress, không tự động làm `errors.hasErrors()` thành `true`.

### `setRequiredFields` so với `@NotNull`

~~~java
binder.setRequiredFields("fullName");
~~~

Lệnh này kiểm tra sự hiện diện/khả dụng của field trong **property values** ở giai đoạn binding. Nó không thay thế `@NotBlank`, vì một field có thể tồn tại nhưng chứa khoảng trắng. `@NotNull` là constraint trên object sau conversion/validation, và với nested data có semantics khác. Đừng vừa đặt rule required trên binder vừa đặt Jakarta constraints trùng nhau mà không có chủ đích; response có thể chứa nhiều mã lỗi khác nhau.

### `setDeclarativeBinding(true)`

~~~java
@InitBinder
void secureBinding(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Theo Spring Framework 6.1+, cấu hình này đảm bảo **constructor binding** vẫn được dùng, còn **property binding** chỉ được dùng nếu `allowedFields` được chỉ rõ. Đây là lựa chọn mạnh để giới hạn setter/property binding, nhưng không phải “tự động bảo mật” khi constructor nhận các tham số mà client không nên kiểm soát. Thiết kế request DTO nhỏ, khai báo constructor đúng hợp đồng và kiểm tra authorization vẫn là nền tảng.

## 5. Formatter, PropertyEditor và Validator: nên đăng ký gì?

### 5.1. `PropertyEditor`: đơn giản và hướng về một kiểu

Với input `eventDate=25/12/2026`, không muốn dùng dạng ISO `2026-12-25` mặc định của converter, có thể đăng ký một editor cho `LocalDate`:

~~~java
private static final DateTimeFormatter DATE =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

@InitBinder("signupForm")
void init(WebDataBinder binder) {
    binder.registerCustomEditor(LocalDate.class,
            new PropertyEditorSupport() {
                @Override
                public void setAsText(String text) {
                    setValue(LocalDate.parse(text, DATE));
                }

                @Override
                public String getAsText() {
                    LocalDate value = (LocalDate) getValue();
                    return value == null ? "" : value.format(DATE);
                }
            });
}
~~~

Đoạn trên **chưa phải class độc lập**: import `java.beans.PropertyEditorSupport`, `java.time.LocalDate`, `java.time.format.DateTimeFormatter`/`ResolverStyle`, và `WebDataBinder`, đặt trong controller. DateTimeFormatter là immutable, có thể dùng chung; `PropertyEditorSupport` là mutable nên tạo instance mới trên binder thay vì giữ một global static instance.

Với `DateTimeFormatter.ofPattern("dd/MM/uuuu")` và `ResolverStyle.STRICT`, `25/12/2026` được parse, còn `31/02/2026` không hợp lệ. Khi conversion sai trong form, Spring ghi lỗi type mismatch vào `BindingResult`; nếu không có `BindingResult` cạnh model attribute, error có thể làm WebFlux ném `WebExchangeBindException`.

### 5.2. `Formatter<T>`: giải pháp idiomatic khi cần parse và print

~~~java
// Đoạn phương thức minh họa, giả định có FORMAT và các imports.
@InitBinder("signupForm")
void initFormatter(WebDataBinder binder) {
    binder.addCustomFormatter(new Formatter<LocalDate>() {
        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text, FORMAT);
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return FORMAT.format(value);
        }
    });
}
~~~

`Formatter<T>` cung cấp `parse(String, Locale)` và `print(T, Locale)`. Dùng khi muốn cùng một biểu diễn nhất quán cho input và rendered forms. Với nhiều controllers cùng cần ISO date/time format, ưu tiên đăng ký toàn cục qua `WebFluxConfigurer#addFormatters(FormatterRegistry)` hoặc `@DateTimeFormat` ở field nếu đủ đơn giản, không copy một anonymous formatter vào tất cả controller.

Chỉ sử dụng **một** trong hai phương án editor/formatter cho cùng kiểu và phạm vi nếu muốn tránh tranh chấp conversion rules. Ví dụ runnable sau dùng `PropertyEditorSupport` để hành vi parse date được nhìn thấy rõ.

### 5.3. Spring `Validator` và Jakarta Bean Validation

`@InitBinder` cũng có thể bổ sung một Spring Validator:

~~~java
@InitBinder("signupForm")
void initValidator(WebDataBinder binder) {
    binder.addValidators(new SignupPolicyValidator());
}
~~~

Đây là **đoạn minh họa**, chưa tạo object validator. Interface `org.springframework.validation.Validator` gồm `supports(Class<?>)` và `validate(Object, Errors)`. `@Valid` kích hoạt validator phù hợp theo lifecycle của controller và Bean Validation provider có trên classpath. Các custom validations từ `addValidators` có thể chạy **cùng** Jakarta `@NotBlank`, `@Min` nếu không thay thế validator toàn cục.

Không nhầm `binder.addValidators(...)` với `binder.setValidator(...)`: thêm validator là phép hợp nhất có chủ đích; thay validator có thể làm mất Jakarta validation đang được cung cấp sẵn. Validator cần chỉ hỗ trợ target type thích hợp qua `supports(...)`.

### 5.4. Khi nào dùng global `WebFluxConfigurer`?

Nếu mọi controller đều cần cùng converter hoặc formatter:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Đăng ký các Formatter/Converter dùng chung.
    }
}
~~~

Đoạn minh họa này cần imports của `Configuration`, `WebFluxConfigurer` và `FormatterRegistry`. Với Spring Boot application được tự động cấu hình, không cần `@EnableWebFlux` chỉ để đăng ký một formatter. Lợi thế của global `ConversionService` là logic nhất quán cho nhiều nơi; lợi thế của `@InitBinder` là tùy chỉnh trong phạm vi controller/attribute. Hai lựa chọn nên bổ sung cho nhau, không ghi đè không kiểm soát.

## 6. Ví dụ runnable: WebFlux registration form có local và global binder

Ví dụ dùng Spring Boot **3.5.7**, Java **17**, Maven, và chỉ `spring-boot-starter-webflux` để tránh Web MVC được chọn khi thêm đồng thời Servlet starter. Bộ test dùng `WebTestClient` chứ không dùng `MockMvc`.

### 6.1. Cấu trúc project

~~~text
pom.xml
src/main/java/com/example/binder/
  BinderApplication.java
  SignupForm.java
  SignupPolicyValidator.java
  SignupBindingAdvice.java
  SignupController.java
src/test/java/com/example/binder/
  SignupControllerTest.java
  SignupBinderTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-initbinder-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
</project>
~~~

`spring-boot-starter-validation` đưa Jakarta Bean Validation implementation vào classpath; `spring-boot-starter-test` mang JUnit 5 và WebFlux test infrastructure. Không có database, security dependencies hoặc persistence layer trong demo.

### 6.3. Main class

~~~java
// src/main/java/com/example/binder/BinderApplication.java
package com.example.binder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderApplication {
    public static void main(String[] args) {
        SpringApplication.run(BinderApplication.class, args);
    }
}
~~~

### 6.4. `SignupForm`: dành riêng cho web input

~~~java
// src/main/java/com/example/binder/SignupForm.java
package com.example.binder;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class SignupForm {

    @NotBlank(message = "Họ tên không được trống")
    private String fullName;

    @NotNull(message = "Tuổi là bắt buộc")
    @Min(value = 18, message = "Tuổi phải từ 18")
    private Integer age;

    @NotNull(message = "Ngày sự kiện là bắt buộc")
    private LocalDate eventDate;

    @Size(max = 3, message = "Tối đa 3 chủ đề")
    private List<@NotBlank String> topics = new ArrayList<>();

    // Chỉ để chứng minh over-posting; không đặt trong public DTO thật.
    private boolean admin;

    public SignupForm() {}

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public LocalDate getEventDate() { return eventDate; }
    public void setEventDate(LocalDate eventDate) {
        this.eventDate = eventDate;
    }

    public List<String> getTopics() { return topics; }
    public void setTopics(List<String> topics) { this.topics = topics; }

    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean admin) { this.admin = admin; }
}
~~~

Bean có default constructor/getters/setters để mô tả **property binding**. Nó nhận object-name `signupForm` do `@ModelAttribute("signupForm")` chỉ định, không cần tên class trùng tên biến trong handler.

Ràng buộc:
- `@NotBlank` trên `fullName` từ chối cả `null`, rỗng và khoảng trắng.
- `@NotNull`/`@Min(18)` trên `age` kiểm tra có giá trị và ngưỡng tối thiểu.
- `@NotNull` trên `eventDate` yêu cầu một ngày hợp lệ sau conversion.
- `@Size(max=3)` giới hạn độ dài list, và type-use `@NotBlank` kiểm tra từng phần tử.
- `admin` là ví dụ property nhạy cảm mà client **không được bind**. Trong sản phẩm thật cần loại bỏ property này khỏi request DTO và thiết kế authorization ở server.

### 6.5. Custom Spring Validator

~~~java
// src/main/java/com/example/binder/SignupPolicyValidator.java
package com.example.binder;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class SignupPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("blocked".equalsIgnoreCase(form.getFullName())) {
            errors.rejectValue("fullName", "reserved.name",
                    "Tên này không được sử dụng");
        }
    }
}
~~~

Validator trên là stateless: không gọi API ngoài, không có side effects. Với `fullName=blocked`, `@NotBlank` của Jakarta coi chuỗi hợp lệ về hình thức, còn rule riêng `SignupPolicyValidator` sẽ báo một `FieldError` có code `reserved.name`. Nhờ vậy có thể thấy rõ **hai lớp kiểm tra** bổ sung cho nhau.

`supports(Class<?>)` bảo đảm validator chỉ nhận `SignupForm` và subclass; không nên thêm validator không hỗ trợ target vào một global binder. Khi cần custom business rule truy vấn database bất đồng bộ, không làm blocking repository call bên trong `validate` đồng bộ; đặt quy tắc đó ở reactive service pipeline sau binding.

### 6.6. Global `@ControllerAdvice`: trim strings

~~~java
// src/main/java/com/example/binder/SignupBindingAdvice.java
package com.example.binder;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice(assignableTypes = SignupController.class)
public class SignupBindingAdvice {

    @InitBinder
    void trimStrings(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

Advice chỉ nhắm controller `SignupController` nhờ `assignableTypes`; trong đó `@InitBinder` không giới hạn object name nên áp dụng cho các binder phù hợp với controller ấy. `StringTrimmerEditor(true)` trim khoảng trắng đầu/cuối, đồng thời đổi chuỗi trống sau trim thành null. Ví dụ `"  Lan  "` thành `"Lan"`, `"    "` thành `null`.

Không nên dùng `StringTrimmerEditor` để sửa tùy tiện mọi chuỗi nếu nghiệp vụ cần bảo toàn whitespace (mật khẩu, văn bản đã ký, token hoặc nội dung định dạng). Chỉ sử dụng khi các input fields thực sự có semantics như vậy. **Global advice chạy trước local binder methods** theo Spring WebFlux; trong demo, global tạo editor cho `String`, local tạo editor cho `LocalDate` nên không xung đột.

### 6.7. Controller: local `@InitBinder("signupForm")`

~~~java
// src/main/java/com/example/binder/SignupController.java
package com.example.binder;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/signups")
public class SignupController {

    private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("dd/MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @InitBinder("signupForm")
    void configureSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "fullName", "age", "eventDate", "topics[*]");
        binder.setAutoGrowCollectionLimit(5);

        binder.registerCustomEditor(
                LocalDate.class, new PropertyEditorSupport() {
                    @Override
                    public void setAsText(String text) {
                        setValue(LocalDate.parse(text, DATE));
                    }

                    @Override
                    public String getAsText() {
                        LocalDate date = (LocalDate) getValue();
                        return date == null ? "" : date.format(DATE);
                    }
                });

        binder.addValidators(new SignupPolicyValidator());
    }

    @PostMapping(consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> register(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            Map<String, Object> response =
                    Map.of("invalidFields", fields);
            return Mono.just(ResponseEntity.badRequest().body(response));
        }

        Map<String, Object> response = Map.of(
                "name", form.getFullName(),
                "age", form.getAge(),
                "eventDate", form.getEventDate().toString(),
                "topics", form.getTopics(),
                "admin", form.isAdmin()
        );
        return Mono.just(ResponseEntity.ok(response));
    }

    @PostMapping(path = "/strict", consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> registerStrict(
            @Valid @ModelAttribute("signupForm") SignupForm form) {
        return Mono.just("accepted:" + form.getFullName());
    }
}
~~~

**Đường hoạt động của code trên:**
1. Spring WebFlux nhận URL-encoded form, tìm `@ModelAttribute("signupForm")` và tạo target `SignupForm`.
2. `SignupBindingAdvice.trimStrings` đăng ký editor cho `String` (advice-scope).
3. `SignupController.configureSignupBinder` chạy cho đúng binder có object name `signupForm`; đăng ký allowlist, growth limit, editor cho `LocalDate` và custom Spring Validator.
4. Binder gán các fields được phép, thực hiện chuyển kiểu. `admin=true` sẽ bị suppress vì không thuộc allowlist.
5. `@Valid` kích hoạt Bean Validation và các validators được đăng ký phù hợp. `BindingResult` giữ thông tin lỗi conversion và constraints.
6. Với `register`, nếu có lỗi thì trả 400 và chỉ nêu **tên field**. Nếu hợp lệ, trả JSON tóm tắt form.
7. Với `registerStrict`, không có `BindingResult` liền sau model attribute: lỗi object binding/validation có thể thành `WebExchangeBindException` với HTTP 400 trước khi method chạy.

`Mono.just(...)` ở đây chỉ là return type reactive của handler. Nó không nói rằng `@InitBinder` chạy bất đồng bộ hay `BindingResult` có thể đọc trước khi việc binding hoàn tất; Spring giải quyết arguments trước khi gọi thân controller.

### 6.8. HTML form và curl

Một HTML form đơn giản gửi đúng tên fields:

~~~html
<form action="/signups" method="post">
  <input name="fullName" value="  Lan  ">
  <input name="age" type="number" value="21">
  <input name="eventDate" value="25/12/2026">
  <input name="topics[0]" value="webflux">
  <button type="submit">Đăng ký</button>
</form>
~~~

Khi trình duyệt gửi form, các ký tự như `[`, `]`, `/` có thể được URL-encode. Spring WebFlux nhận tên field logic `topics[0]` và giá trị `25/12/2026` sau khi đọc/giải mã request.

Thử từ terminal hỗ trợ dấu `\` nối dòng (Linux/macOS/Git Bash):

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i -X POST http://localhost:8080/signups \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=  Lan  " \
  --data-urlencode "age=21" \
  --data-urlencode "eventDate=25/12/2026" \
  --data-urlencode "topics[0]=webflux" \
  --data-urlencode "admin=true"
~~~

JSON response kỳ vọng, bỏ qua thứ tự property:

~~~json
{
  "name": "Lan",
  "age": 21,
  "eventDate": "2026-12-25",
  "topics": ["webflux"],
  "admin": false
}
~~~

`name` được trim do global advice; `eventDate` được parse `dd/MM/uuuu` rồi xuất bằng `LocalDate#toString()` dạng ISO; `topics[0]` được gán nhờ indexed property binding; `admin` vẫn false do allowlist. Điều đó **không đồng nghĩa** server đã thực hiện xác thực/authorization cho tài khoản, mà chỉ minh họa ngăn property binding trái phép.

Nếu dùng PowerShell, một chuỗi `curl.exe` một dòng hoặc dấu nối dòng PowerShell là phù hợp hơn việc sao chép trực tiếp dấu `\` của shell Unix.

## 7. Kiểm thử `@InitBinder` bằng WebTestClient và JUnit

### 7.1. HTTP-level integration tests

~~~java
// src/test/java/com/example/binder/SignupControllerTest.java
package com.example.binder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@AutoConfigureWebTestClient
@SpringBootTest
class SignupControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void localAndAdviceBindersWorkTogether() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", "  Lan  ")
                        .with("age", "21")
                        .with("eventDate", "25/12/2026")
                        .with("topics[0]", "webflux")
                        .with("admin", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan")
                .jsonPath("$.age").isEqualTo(21)
                .jsonPath("$.eventDate").isEqualTo("2026-12-25")
                .jsonPath("$.topics[0]").isEqualTo("webflux")
                .jsonPath("$.admin").isEqualTo(false);
    }

    @Test
    void jakartaConstraintsAreApplied() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", " ")
                        .with("age", "16")
                        .with("eventDate", "25/12/2026"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields").isArray()
                .jsonPath("$.invalidFields[0]").isEqualTo("age")
                .jsonPath("$.invalidFields[1]").isEqualTo("fullName");
    }

    @Test
    void customSpringValidatorIsApplied() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", "blocked")
                        .with("age", "21")
                        .with("eventDate", "25/12/2026"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]").isEqualTo("fullName");
    }

    @Test
    void wrongDateFormatIsBindingError() {
        client.post()
                .uri("/signups")
                .body(BodyInserters.fromFormData("fullName", "Lan")
                        .with("age", "21")
                        .with("eventDate", "2026-12-25"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]").isEqualTo("eventDate");
    }

    @Test
    void strictHandlerWithoutBindingResultReturns400() {
        client.post()
                .uri("/signups/strict")
                .body(BodyInserters.fromFormData("fullName", " ")
                        .with("age", "16")
                        .with("eventDate", "25/12/2026"))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Những assert này kiểm tra **hành vi thật của WebFlux handler**, không chỉ việc controller method có annotation:
- Test 1 xác minh advice và local `@InitBinder` cùng có hiệu lực: trim, custom date parser, allowlist, indexed List và field `admin` bị chặn.
- Test 2 xác minh Bean Validation (`@NotBlank`/`@Min`). Controller chủ động `sorted()` field errors nên index 0 là `age`, index 1 là `fullName`.
- Test 3 chứng minh custom Spring Validator gắn qua `addValidators` được gọi.
- Test 4 xác minh editor date không chấp nhận định dạng ISO trong form thuộc controller này; lỗi thuộc binding/conversion.
- Test 5 xác minh model attribute không có `BindingResult` liền sau sẽ được xử lý bằng error path của framework (400).

Không assert nguyên văn thông điệp lỗi hoặc response JSON khi framework tự xử lý lỗi; những nội dung đó phụ thuộc locale, message source và error handler. Ở các test có `BindingResult`, response đã được controller định nghĩa nên có thể assert danh sách field.

### 7.2. Unit test cấu hình binder trực tiếp

`@InitBinder` được Spring gọi khi request tới controller. Khi cần kiểm tra riêng cấu hình conversion/allowlist, có thể tạo `WebDataBinder` thủ công và gọi method cấu hình (test đặt cùng package):

~~~java
// src/test/java/com/example/binder/SignupBinderTest.java
package com.example.binder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.time.LocalDate;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class SignupBinderTest {

    @Test
    void localBinderConfigCanBeVerifiedWithoutHttp() {
        SignupForm form = new SignupForm();
        WebDataBinder binder = new WebDataBinder(form, "signupForm");
        new SignupController().configureSignupBinder(binder);

        binder.bind(new MutablePropertyValues(Map.of(
                "fullName", "blocked",
                "age", "21",
                "eventDate", "25/12/2026",
                "admin", "true"
        )));
        binder.validate();

        assertEquals(LocalDate.of(2026, 12, 25),
                form.getEventDate());
        assertEquals(21, form.getAge());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[]{"admin"},
                binder.getBindingResult().getSuppressedFields());

        // Validator custom ở local binder, không phụ thuộc HTTP.
        assertNotNull(
                binder.getBindingResult().getFieldError("fullName"));
    }
}
~~~

Test này **không** gọi `@ControllerAdvice` và cũng không tự đăng ký Jakarta Bean Validation provider. Nó chỉ kiểm tra local binder method, property editors, allowlist và custom Spring validator. Do đó `fullName` vẫn là chuỗi `"blocked"` và custom validator tạo lỗi cho field; test không dựa vào global StringTrimmerEditor.

Chạy tất cả:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** 6 JUnit tests PASS (5 WebTestClient, 1 WebDataBinder unit test) khi dependencies và Spring Boot 3.5.7 như bài đã chỉ định. Đây là kết quả dự kiến theo API/luồng được mô tả, **không phải khẳng định đã thực thi Maven**. Để chạy một class test:

~~~bash
mvn -Dtest=SignupControllerTest test
~~~

## 8. Phân biệt `@InitBinder` và `@RequestBody` JSON

Đây là lỗi kiến trúc phổ biến nhất khi dùng allowlist: developer thêm `@InitBinder` với `allowedFields` rồi tin rằng mọi input từ client đã được lọc. Điều đó **không đúng** đối với JSON deserialization.

### Dạng form, có property names

~~~http
POST /signups HTTP/1.1
Content-Type: application/x-www-form-urlencoded

fullName=Lan&age=21&eventDate=25%2F12%2F2026&admin=true
~~~

Spring WebFlux `@ModelAttribute` đi qua model binding, nơi `WebDataBinder#setAllowedFields(...)` có thể chặn `admin`.

### Dạng JSON

~~~http
POST /api/signups HTTP/1.1
Content-Type: application/json

{"fullName":"Lan","age":21,"admin":true}
~~~

Với handler `@Valid @RequestBody SomeInputDto`, WebFlux thường dùng JSON `HttpMessageReader`/Jackson deserialize trực tiếp thành object. `@InitBinder` có thể tham gia cấu hình validation/binder ở các điểm framework cho phép, nhưng **`setAllowedFields` không phải bộ lọc JSON properties của Jackson**. Nếu DTO JSON có setter nhạy cảm thì client vẫn có thể đưa giá trị vào trước bước validation.

**Cách đúng:** DTO input chỉ chứa field người dùng được phép kiểm soát; tránh expose `admin`/`role`/`ownerId`. Có thể cấu hình Jackson annotations khi cần, nhưng authorization và domain validation phải ở server. Không dùng allowlist của form làm cơ chế security chung cho JSON.

Nếu một endpoint vừa nhận form vừa nhận JSON, hãy thiết kế hai contracts hoặc xử lý Content-Type rõ ràng, và test từng nhánh riêng. Đừng giả định query/form/multipart và JSON có cùng vòng đời binder.

## 9. Validation, BindingResult và exception trong WebFlux

### 9.1. Conversion error khác validation error

~~~text
age=abc
  -> không chuyển được String thành Integer
  -> binding error; code thường là typeMismatch

age=16
  -> chuyển được thành Integer 16
  -> vi phạm @Min(18), nếu @Valid/@Validated chạy
  -> validation error; code thường là Min

fullName=blocked
  -> String hợp lệ theo @NotBlank
  -> custom SignupPolicyValidator báo reserved.name

admin=true
  -> field không nằm trong allowedFields
  -> suppressed field, thường không thành FieldError
~~~

Đây là bốn tình huống khác nhau. `BindingResult` có `getFieldErrors()` và `getSuppressedFields()` để phân biệt. Không trả raw `FieldError#getRejectedValue()` trong API responses vì có thể lộ dữ liệu cá nhân hoặc token.

### 9.2. `@Valid` cùng `BindingResult`

~~~java
@PostMapping("/forms")
public Mono<String> submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult result) {

    return Mono.just(result.hasErrors() ? "invalid" : "ok");
}
~~~

Đây là một **handler minh họa**, không nằm trong project runnable. `BindingResult` phải đứng **ngay sau** tham số `@ModelAttribute` không bọc reactive type để handler xử lý lỗi. Nếu không đặt, khi object-only validation thất bại, Spring WebFlux thường ném `WebExchangeBindException` và ánh xạ HTTP 400.

Nếu dùng `@ModelAttribute Mono<SignupForm>`, không khai báo một `BindingResult` liền sau như với object thường; xử lý lỗi trong reactive chain bằng các toán tử `onErrorResume`/`onErrorMap` hoặc error handler thích hợp.

### 9.3. Method validation từ Spring 6.1+

Một handler với constraint trực tiếp trên tham số như:

~~~java
@GetMapping("/search")
public Mono<String> search(
        @RequestParam @Min(1) int page) {
    return Mono.just("page:" + page);
}
~~~

có thể kích hoạt **method validation** tích hợp (Spring WebFlux 6.1+) và ném `HandlerMethodValidationException` nếu `page` không đạt yêu cầu. Đây là cơ chế khác với object-only validation của `@ModelAttribute`, và có thể bao phủ các nested constraints của `@Valid` khi cần.

`@InitBinder` là nơi tùy biến binder/validator cho arguments; nó **không tự biến mọi `@ModelAttribute` thành method validation** và không thay thế `@Valid`. Nếu controller có `@Validated` ở class-level, validation method có thể đi theo AOP proxy thay vì cơ chế tích hợp; cần test theo chiến lược đã chọn.

### 9.4. Thêm validator có rủi ro gì?

Nếu dùng:

~~~java
binder.setValidator(new SignupPolicyValidator());
~~~

bạn có thể vô tình **thay thế** validator toàn cục; những `@NotBlank` và `@Min` do Jakarta provider hỗ trợ có thể không còn được áp dụng như dự kiến. Vì vậy, trong demo dùng:

~~~java
binder.addValidators(new SignupPolicyValidator());
~~~

Nhiều validators có thể cùng đóng góp lỗi. Hãy viết test rằng cả custom rule lẫn Jakarta constraints đều hoạt động khi tích hợp. Khi một validator phụ thuộc database hoặc external API, đừng chạy blocking I/O trong `validate` của binder; lựa chọn reactive service validation sau binding mới phù hợp.

## 10. Thực hành mở rộng: policies, converters, formatter scopes

### 10.1. Tổ chức config cho dự án nhiều controller

Một cấu trúc dễ bảo trì:

~~~text
web/
  SignupController.java
  ProfileController.java
  binding/
    CommonBindingAdvice.java
    SignupPolicyValidator.java
    SignupDateFormatter.java
config/
  WebFluxFormattingConfig.java
~~~

Có thể dùng:
- Local `@InitBinder("signupForm")` cho rules chỉ thuộc signup.
- `@ControllerAdvice(basePackageClasses = ...)` cho common binding policy trong một phần ứng dụng.
- `WebFluxConfigurer#addFormatters` cho converters dùng trên toàn WebFlux.
- DTO tách biệt theo request/use case.
- Spring Security/service layer cho authorization; binder chỉ lo biến input thành object.

Đừng đặt toàn bộ policy trong một advice “global” rồi phụ thuộc vào thứ tự override giữa nhiều controllers. Khi đổi một policy, test ít nhất một controller ở đúng phạm vi và một controller ngoài phạm vi để bảo đảm không lan rộng.

### 10.2. Field-specific formatter

Có thể giới hạn formatter theo tên field:

~~~java
@InitBinder("signupForm")
void configure(WebDataBinder binder) {
    binder.addCustomFormatter(
            new DateFormatter("dd/MM/yyyy"), "legacyDate");
}
~~~

Ví dụ này áp dụng cho **`java.util.Date`** field `legacyDate`, không phải `LocalDate`. Cần import `org.springframework.format.datetime.DateFormatter`, và DTO chứa field `Date legacyDate` thì mới phù hợp. Đừng nhầm `DateFormatter` xử lý `java.util.Date` với formatter `LocalDate` của `java.time`; code runnable phía trên cố ý dùng editor cho `LocalDate`.

Với `LocalDate` dùng chung nhiều endpoints, `@DateTimeFormat(pattern = "dd/MM/uuuu")` trên field hoặc custom `Formatter<LocalDate>` đăng ký trong ConversionService có thể gọn hơn. Tránh các format phụ thuộc locale mơ hồ như `01/02/2026` khi client không biết ngày–tháng hay tháng–ngày.

### 10.3. Nested/list/map fields

Một form có `List<Item> items` hoặc `Map<String, Contact> contacts` có thể bind từ:

~~~text
items[0].code=PEN
items[0].quantity=2
items[1].code=BOOK
contacts[support].email=help@example.com
~~~

Với property binding, `allowedFields` nên liệt kê paths cụ thể thay vì `items*` quá rộng:

~~~java
binder.setAllowedFields(
    "items[*].code",
    "items[*].quantity",
    "contacts[support].email"
);
binder.setAutoGrowCollectionLimit(10);
~~~

Nếu collection ban đầu rỗng, auto-grow và nested target instantiation phải có kiểu/constructor phù hợp. Với `Map` value là object, để chắc chắn binder biết nơi gán nested property, có thể khởi tạo các key/value dự kiến trên DTO trước khi bind. `autoGrowCollectionLimit` không tự giới hạn số Map keys, request body size hoặc quyền sửa nested entities.

### 10.4. Giới hạn đầu vào

Ngoài binder allowlist, cần cấu hình:
- Giới hạn HTTP body size, max in-memory data size và multipart options ở WebFlux/server.
- Maximum số request fields/list items/map entries.
- Index tối đa, độ sâu nested properties, độ dài key/value.
- Validation constraints về dữ liệu (length, min/max, pattern).
- Authorization/ownership theo authenticated principal.

`setAutoGrowCollectionLimit(5)` trong demo giảm nguy cơ tạo list với index tùy ý lớn, **không đảm bảo mọi invalid index đều được chuyển thành `BindingResult`/HTTP 400**. Với endpoint public, test boundary cases và xử lý exceptions ở tầng phù hợp.

## 11. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `@InitBinder` không chạy | Method không ở controller/advice được scan, model object name không khớp | Kiểm tra class scanning, `@ModelAttribute("signupForm")` và `@InitBinder("signupForm")` |
| Binder chạy nhưng field không đổi | `allowedFields` loại field, setter không tồn tại, conversion thất bại | Xem `BindingResult#getSuppressedFields()` và `getFieldErrors()` |
| Input có dấu cách không được trim | Advice không áp dụng cho controller hoặc editor không đăng ký cho kiểu String | Xem selector `@ControllerAdvice` và signature init method |
| `eventDate=25/12/2026` không parse | Không đăng ký LocalDate editor hoặc dùng formatter sai type | Đăng ký đúng `LocalDate`/field và test format |
| Dùng `DateFormatter` nhưng field là `LocalDate` | Formatter dành cho `java.util.Date` | Dùng `@DateTimeFormat`/`Formatter<LocalDate>`/editor LocalDate |
| `@NotBlank`/`@Min` không chạy | Chưa dùng `@Valid` hoặc thay global validator | Gắn `@Valid`, dùng `addValidators` thay cho thay thế không chủ đích |
| `BindingResult` không nhận lỗi | Đặt sai vị trí hoặc model attribute bọc reactive type | Đặt ngay sau non-reactive `@ModelAttribute` |
| JSON vẫn bind property `admin` | `allowedFields` không kiểm soát Jackson `@RequestBody` | Tách JSON DTO, cấu hình deserialization và authorization |
| `setAutoGrowCollectionLimit` không chặn Map | Limit chỉ giải quyết phần auto-grow list/array | Kiểm soát số entries/map keys và request size riêng |
| `@ControllerAdvice` áp dụng quá rộng | Không có selector, selector package/type sai | Dùng `assignableTypes`/`basePackageClasses`/`annotations` |
| Có nhiều `@InitBinder` cùng sửa config | Thứ tự/advice-local override khó theo dõi | Phân trách nhiệm rõ, tránh ghi đè cùng thuộc tính |
| `@InitBinder` cố làm reactive DB lookup | Hook đồng bộ, blocking I/O trong event loop | Di chuyển sang reactive service sau binding |
| Missing field bị xem là valid | Không có `@NotNull` hoặc `setRequiredFields` khi thích hợp | Phân biệt field presence và semantic constraints |
| Method-level violation thành exception khác | Có direct constraints và built-in method validation | Xử lý `HandlerMethodValidationException` cùng `WebExchangeBindException` |
| Test dùng `MockMvc` cho WebFlux | Nhầm Servlet MVC với reactive WebFlux | Dùng `WebTestClient` |
| Spring Boot chạy MVC thay vì WebFlux | Có cả servlet web và webflux starters | Chỉ thêm WebFlux starter hoặc cấu hình app type đúng chủ ý |

### Checklist debug có thể lặp lại

1. Kiểm tra project chạy WebFlux thật và có các dependencies/version cần thiết.
2. Bắt đầu với một request có `Content-Type: application/x-www-form-urlencoded`, field names đúng và body nhỏ.
3. Đảm bảo `@ModelAttribute("...")` khớp `@InitBinder("...")`, và controller/advice được scan.
4. Đặt breakpoint/trace tại init binder hoặc viết integration test cho hiệu ứng của config; không dùng log chứa dữ liệu nhạy cảm.
5. Phân biệt field bị **suppressed** với field **typeMismatch** và field **invalid** bởi validation.
6. Kiểm tra `@Valid` và `BindingResult` liền kề; nếu dùng reactive wrapper, xử lý error trong publisher.
7. Rà soát custom editor/formatter type, format và locale; thử input hợp lệ/không hợp lệ.
8. Nếu có global advice, xác nhận phạm vi và thứ tự trước local init; tránh cấu hình mâu thuẫn.
9. Kiểm tra request body JSON có đi qua Jackson hay không, đừng mong allowlist form áp dụng.
10. Test boundary index, số lượng fields, request size và authorization bên cạnh happy path.

## 12. Bài tập tự luyện

1. Tạo thêm `FeedbackController` với `@ModelAttribute("feedbackForm")`. Kiểm chứng `@InitBinder("signupForm")` của `SignupController` không tự áp đặt rules vào feedback, và advice với `assignableTypes` cũng chỉ nhắm đúng controller.
2. Bổ sung `@Size(max=80)` cho `fullName` và một custom validator cấm tên trùng trong danh sách tĩnh. Tách việc tra cứu dữ liệu bất đồng bộ ra service.
3. Viết `Formatter<LocalDate>` thay `PropertyEditorSupport`, rồi so sánh parse/print của `25/12/2026` và `2026-12-25`.
4. Thử `topics[3]`, `topics[10]` và `topics[100000]`; xác định hành vi của property binder và chính sách giới hạn HTTP endpoint của mình, không mặc định tất cả trả cùng HTTP status.
5. Gửi JSON với property `admin` vào một DTO khác chỉ có field hợp lệ; đối chiếu cơ chế Jackson với `allowedFields` của form.
6. Thử `binder.setDeclarativeBinding(true)` trên một immutable record và giải thích vì sao constructors cần được thiết kế như một public input contract.
7. Đăng ký một validator global qua `WebFluxConfigurer#getValidator()`, rồi thêm local validator bằng `@InitBinder`. Test bảo đảm cả hai đóng góp errors ở đúng trường hợp.

## 13. Kết luận

`@InitBinder` trong WebFlux là nơi **đăng ký cấu hình binding** cho annotated controller arguments, chứ không phải nơi tự đọc toàn bộ HTTP body hay xử lý nghiệp vụ. Dùng local `@InitBinder("attributeName")` khi policy thuộc một form, dùng `@ControllerAdvice` khi muốn chia sẻ theo nhóm controllers, và dùng `WebFluxConfigurer` cho formatting/validation thật sự toàn ứng dụng.

Một triển khai vững chắc cần cùng lúc:
- DTO web dành riêng cho request, không expose fields nhạy cảm.
- `setAllowedFields(...)` để giới hạn property binding và ``etDeclarativeBinding(true)` nếu cần contract constructor-binding rõ hơn.
- Formatter/editor đúng kiểu dữ liệu, được test cả input hợp lệ và input sai.
- `addValidators(...)` để bổ sung Spring validators mà không vô tình loại bỏ Bean Validation.
- `@Valid`/`@Validated`, `BindingResult` và exception handlers đúng WebFlux lifecycle.
- WebTestClient tests bao phủ cả scope của binder và bảo mật, không chỉ happy path.

## 14. Tài liệu tham khảo

- Spring Framework 6.2, **WebFlux DataBinder / @InitBinder**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Framework 6.2, **WebFlux Model Attribute**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2, **WebFlux Data Binding**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/data-binding.html
- Spring Framework 6.2, **WebFlux Controller Advice**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-advice.html
- Spring Framework 6.2, **WebFlux Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2, **WebFlux Configuration – formatters and validators**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework 6.2, **DataBinder Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2, **@InitBinder Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/annotation/InitBinder.html
- Spring Boot 3.5, **Testing Spring Boot Applications with WebTestClient**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
