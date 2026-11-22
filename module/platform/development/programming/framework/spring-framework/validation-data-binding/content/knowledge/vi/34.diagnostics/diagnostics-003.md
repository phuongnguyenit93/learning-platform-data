# BindingResult không đứng đúng vị trí trong chữ ký controller: chẩn đoán và sửa lỗi Spring MVC

## 1. Triệu chứng: đã khai báo BindingResult nhưng controller vẫn không nhận lỗi

Trong Spring MVC, một handler có thể nhận đối tượng được bind từ request và đọc lỗi qua `BindingResult` hoặc `Errors`. Cú pháp **đúng vị trí**:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "register-form";
    }
    return "success";
}
```

Đây là **fragment controller**, các class/imports phụ thuộc ứng dụng thực tế. `BindingResult` đứng **ngay sau** argument `form`.

Một chữ ký trông rất giống nhưng **sai**:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        Model model,
        BindingResult result) {

    if (result.hasErrors()) {
        return "register-form";
    }
    return "success";
}
```

Vấn đề là `Model model` chen vào giữa. Spring MVC **không dùng tên biến** `result` để đoán nó phải gắn với `form`, và cũng không tự di chuyển tham số đến vị trí hợp lệ. Theo tài liệu Spring MVC 6.2, `Errors`/`BindingResult` phải được khai báo **ngay sau method argument được validate/bind** mà nó mô tả.

Hậu quả có thể khác nhau theo loại argument, dữ liệu và version/config:

- Khi argument bị lỗi validation/binding và **không có** `BindingResult` ở ngay vị trí kế tiếp, Spring thường chuyển sang đường exception như `MethodArgumentNotValidException`, khiến handler không nhận điều khiển và trả HTTP 400 hoặc response do `@ControllerAdvice` xử lý.
- Khi Spring phải resolve một `BindingResult` ở vị trí bị tách khỏi argument, `ErrorsMethodArgumentResolver` có thể không tìm được binding result tương ứng ở vị trí mô hình mà nó kỳ vọng, và gây `IllegalStateException` liên quan đến việc khai báo `Errors/BindingResult` đúng ngay sau model attribute.
- Nếu chữ ký còn có **direct constraints** trên method parameters, Spring MVC 6.1+ có thể dùng **method validation** và `HandlerMethodValidationException`; đừng chẩn đoán mọi HTTP 400 là cùng một lỗi.
- Nếu request body JSON không đọc được, Jackson/HTTP message converter có thể gây `HttpMessageNotReadableException` **trước bước Bean Validation**; đặt `BindingResult` đúng cũng không biến JSON syntax error thành field error có DTO hợp lệ.

**Trọng tâm bài:** lỗi nằm ở **vị trí tham số trong chữ ký controller**, không phải thiếu dependency Jakarta Validation, không phải viết sai `@NotBlank` và không phải lỗi dịch thông báo. Để sửa, đặt `BindingResult` (hoặc `Errors`) **sát ngay sau đối tượng** mà bạn muốn nhận kết quả binding/validation.

Bài thuộc nhóm **Chẩn đoán** của module **Spring Framework — validation-data-binding**. Ví dụ dùng Java 17+, Spring Boot 3.4.5, Spring Framework 6.x, Jakarta Validation và MockMvc.

## 2. Quy tắc chính thức của Spring MVC

### Quy tắc một câu

**`Errors` hoặc `BindingResult` phải đứng ngay sau argument mà nó mô tả.**

| Argument cần nhận lỗi | Vị trí đúng | Ví dụ |
| --- | --- | --- |
| `@ModelAttribute` | Ngay sau model attribute | `@Valid @ModelAttribute("form") Form form, BindingResult result` |
| `@RequestBody` | Ngay sau body object | `@Valid @RequestBody Input input, BindingResult result` |
| `@RequestPart` | Ngay sau part object | `@Valid @RequestPart("meta") Meta meta, Errors errors` |
| Nhiều `@ModelAttribute` | Mỗi object có result riêng ở sát bên | `FormA a, BindingResult aErrors, FormB b, BindingResult bErrors` |
| Không cần đọc lỗi tại handler | Có thể không khai báo BindingResult | Để Spring exception resolver xử lý lỗi |
| Có lỗi ở method parameter `@Min`/`@NotBlank` trực tiếp | Phụ thuộc method validation | Có thể cần xử lý `HandlerMethodValidationException` |

**Không được chen giữa** một `Model`, `Locale`, `Principal`, `HttpServletRequest`, `@RequestParam`, `@RequestHeader` hay một DTO khác, dù các đối số đó đều hợp lệ khi đặt **sau** `BindingResult`.

### 2.1. Ví dụ thứ tự chính xác

Đúng:

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("account") AccountForm account,
        BindingResult errors,
        @RequestParam(defaultValue = "web") String source,
        Locale locale) {
    // ...
}
```

Sai:

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("account") AccountForm account,
        @RequestParam(defaultValue = "web") String source,
        BindingResult errors,
        Locale locale) {
    // ...
}
```

Chỉ cần chuyển `source` ra **sau** `errors`. Không cần xóa `@RequestParam` hoặc `Locale`; chỉ cần tuân thủ vị trí.

### 2.2. Errors và BindingResult khác nhau thế nào?

`org.springframework.validation.Errors` định nghĩa các thao tác xem/lưu lỗi, ví dụ:

- `hasErrors()`.
- `getAllErrors()`.
- `getFieldErrors()`.
- `getGlobalErrors()`.
- `reject(...)` / `rejectValue(...)`.

`org.springframework.validation.BindingResult` **mở rộng** `Errors`, bổ sung metadata liên quan binder, ví dụ:

- `getTarget()`.
- `getRawFieldValue(...)`.
- `getFieldValue(...)`.
- `getSuppressedFields()`.
- `getModel()`.

Một chữ ký có thể dùng:

```java
@Valid @ModelAttribute("form") Form form,
Errors errors
```

hoặc:

```java
@Valid @ModelAttribute("form") Form form,
BindingResult errors
```

Cả hai **đều phải ở vị trí liền kề**. Đổi kiểu từ `BindingResult` thành `Errors` không phải cách sửa một chữ ký sai thứ tự.

### 2.3. @Valid không làm vị trí trở nên linh hoạt

`@Valid` yêu cầu validation sau binding khi có provider/cấu hình phù hợp; nó **không chỉ định đích** cho một `BindingResult` nằm ở bất kỳ đâu trong signature. Nếu muốn handler tự xử lý lỗi, `BindingResult` vẫn phải đứng ngay sau object.

Ngược lại, ngay cả không có `@Valid`, data binding vẫn có thể tạo lỗi **chuyển kiểu** như `age=abc` đối với `Integer age`. Đặt `BindingResult` đúng vẫn quan trọng nếu handler cần xem binding failures.

## 3. Tại sao Spring yêu cầu adjacency?

Spring MVC giải quyết tham số bằng một chuỗi **HandlerMethodArgumentResolver**. Mỗi tham số được xét theo loại/annotation và vị trí trong method signature.

Với `@ModelAttribute`:

```text
HTTP request parameters
        |
        v
ModelAttributeMethodProcessor / ServletModelAttributeMethodProcessor
        |
        v
Tạo hoặc lấy command object
        |
        v
WebDataBinder bind và convert giá trị
        |
        v
@Valid / @Validated nếu được khai báo
        |
        v
BindingResult chứa binding + validation errors
        |
        +--> Tham số KẾ TIẾP là Errors/BindingResult?
                 | Có  -> truyền BindingResult vào handler
                 | Không -> lỗi có thể đi theo exception path
```

Với `@RequestBody`:

```text
HTTP JSON body
        |
        v
HttpMessageConverter / Jackson
        |
        v
Tạo DTO từ JSON (nếu parse được)
        |
        v
RequestResponseBodyMethodProcessor áp validation
        |
        +--> Tham số kế tiếp là Errors/BindingResult?
                 | Có  -> handler nhận body và errors
                 | Không -> validation failure có thể ném
                            MethodArgumentNotValidException
```

Hai pipeline **không giống nhau**: một bên dùng property/constructor binding từ request parameters, một bên có deserialization qua HTTP message converter. Nhưng quy tắc **đặt result ngay sau object** áp dụng cho các trường hợp Spring hỗ trợ local error handling.

### 3.1. Không phải Spring “tìm theo tên biến result”

Ở Java, tên biến parameter có thể bị đổi, không có hoặc được compiler giữ tùy configuration. Tên `result` không có nghĩa đặc biệt:

```java
@Valid @ModelAttribute("form") Form x,
BindingResult whateverName
```

Vẫn đúng nếu hai tham số liền nhau. Ngược lại, đặt biến có tên `formErrors` ở cuối method vẫn sai dù tên gợi rõ chủ sở hữu.

### 3.2. Thứ tự không phụ thuộc việc lỗi có xảy ra không

Một chữ ký sai có thể biểu hiện khác nhau khi:

- Request có validation errors.
- Request hoàn toàn hợp lệ.
- Request bị type conversion error.
- Controller có thêm một `@ModelAttribute` ở giữa.
- Ứng dụng bật method validation hoặc custom argument resolvers.

Vì thế không nên chỉ test “form hợp lệ trả 200”. Một test với dữ liệu lỗi là cần thiết để phát hiện sự khác biệt giữa **controller xử lý lỗi tại chỗ** và **Spring đã ném exception trước khi vào controller**.

### 3.3. BindingResult trong Model

Spring MVC lưu metadata của model attribute dưới một key quy ước:

```java
String key = BindingResult.MODEL_KEY_PREFIX + "form";
```

Đây là **fragment**; giá trị prefix do Spring công bố qua constant, tương ứng key kiểu `org.springframework.validation.BindingResult.form`.

Khi có nhiều model attributes, có thể có nhiều entry binding result. Nhưng **không được suy** rằng Spring sẽ dựa vào key trong Map để tự dò đối số `BindingResult` bị đặt lệch ở bất kỳ vị trí nào. Contract cho handler arguments vẫn là **liền kề**.

## 4. Nhận diện lỗi qua một số chữ ký sai thường gặp

### 4.1. Model chen giữa Form và BindingResult

Sai:

```java
@PostMapping("/profile")
public String update(
        @Valid @ModelAttribute("profile") ProfileForm form,
        Model model,
        BindingResult errors) {
    // ...
    return "profile";
}
```

Đúng:

```java
@PostMapping("/profile")
public String update(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors,
        Model model) {
    if (errors.hasErrors()) {
        return "profile";
    }
    return "redirect:/profile";
}
```

`Model` dùng để đưa dữ liệu ra view, không phải `Errors` của form; vị trí của `Model` có thể được đặt sau result.

### 4.2. Locale hoặc Principal chen giữa

Sai:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        Locale locale,
        BindingResult errors) {
    // ...
    return "done";
}
```

Đúng:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult errors,
        Locale locale) {
    // ...
    return "done";
}
```

Dù `Locale` là metadata ngôn ngữ và không có liên quan tới form, nó vẫn không được chen giữa object và kết quả binding.

### 4.3. @RequestParam chen giữa

Sai:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        @RequestParam String source,
        BindingResult errors) {
    // ...
    return "done";
}
```

Đúng:

```java
public String submit(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult errors,
        @RequestParam String source) {
    // ...
    return "done";
}
```

Thứ tự các thông số **không phải trường dữ liệu được validate** có thể linh hoạt, nhưng phải giữ một cặp object/result liền nhau.

### 4.4. Hai DTO, chỉ một BindingResult ở cuối

Sai:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        @Valid @ModelAttribute("contact") ContactForm contact,
        BindingResult errors) {
    // ...
    return "done";
}
```

Không nên cho rằng `errors` ở cuối gom cả hai object. Nếu `profile` có lỗi thì nó **không có result kề ngay sau**, nên Spring có thể ném exception trước khi xử lý object sau.

Đúng:

```java
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        BindingResult profileErrors,
        @Valid @ModelAttribute("contact") ContactForm contact,
        BindingResult contactErrors) {

    if (profileErrors.hasErrors() || contactErrors.hasErrors()) {
        return "edit";
    }
    return "done";
}
```

**Mỗi object có một result riêng**; không gộp hai object vào một BindingResult. Nếu cần một response chứa lỗi của cả hai, gom dữ liệu **sau khi hai BindingResults đã được Spring gán đúng**.

### 4.5. @RequestBody JSON có tham số chen giữa

Sai:

```java
@PostMapping("/api/signup")
public ResponseEntity<?> create(
        @Valid @RequestBody SignupRequest request,
        @RequestHeader("X-Client") String client,
        BindingResult errors) {
    // ...
    return ResponseEntity.ok().build();
}
```

Đúng:

```java
@PostMapping("/api/signup")
public ResponseEntity<?> create(
        @Valid @RequestBody SignupRequest request,
        BindingResult errors,
        @RequestHeader("X-Client") String client) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
```

Spring MVC hỗ trợ `BindingResult` sát sau `@RequestBody` cho **validation errors của một object đã deserialize được**. Nó không phải cách bắt **JSON sai cú pháp**, body thiếu required hoặc media type không được hỗ trợ, vì những lỗi này có thể xảy ra **trước khi có đối tượng DTO hợp lệ**.

### 4.6. @RequestPart với multipart JSON metadata

Đúng:

```java
@PostMapping(
        path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @Valid @RequestPart("metadata") UploadMetadata metadata,
        BindingResult metadataErrors,
        @RequestPart("file") MultipartFile file) {

    if (metadataErrors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
```

Đây là **fragment**, cần controller imports và class `UploadMetadata` phù hợp. `@RequestPart` sử dụng message conversion để đọc part phức tạp; lỗi validation có thể được xử lý bằng result sát ngay sau part object.

Nếu đặt `MultipartFile file` giữa `metadata` và `metadataErrors`, lại vi phạm quy tắc adjacency. Mặc dù các multipart parts theo tên có thể đến theo thứ tự bất kỳ trong request, **thứ tự Java method arguments vẫn phải đúng**.

### 4.7. Errors là parameter đầu method

Sai:

```java
public String save(
        BindingResult errors,
        @Valid @ModelAttribute("form") Form form) {
    // ...
    return "done";
}
```

Errors không đứng “ngay sau” object nào; Spring không thể dùng nó như error holder cho object phía sau. Đặt object trước, Errors ngay sau.

## 5. Những exception cần phân biệt khi chẩn đoán

| Tình huống | Exception/hành vi thường gặp | Điểm cần kiểm tra |
| --- | --- | --- |
| `@Valid @ModelAttribute` lỗi, không có result sát ngay | `MethodArgumentNotValidException` trong MVC hiện đại | Chữ ký method và handler advice |
| `@Valid @RequestBody` lỗi, không có result sát ngay | `MethodArgumentNotValidException` | Có body DTO đọc được không? |
| `@Valid @RequestPart` lỗi, không có result sát ngay | `MethodArgumentNotValidException` | Cấu trúc multipart/part JSON |
| `BindingResult` bị đặt lạc chỗ và resolver không tìm được result | Có thể `IllegalStateException` | Vị trí method parameter, các model attributes gần đó |
| Direct method constraints như `@Min` trên `@RequestParam` | `HandlerMethodValidationException` (Spring MVC 6.1+) | Có constraint trên method signature? |
| JSON syntax/type không đọc được | `HttpMessageNotReadableException` | Message converter, không phải BindingResult |
| Content-Type không được hỗ trợ | `HttpMediaTypeNotSupportedException` | Content-Type và consumes |
| Mất Bean Validation provider | Constraints có thể không chạy như mong đợi | Validation dependency/configuration |
| Không có `@Valid`/`@Validated` | Jakarta constraints có thể không được chạy | Cần kích hoạt validation |
| Lỗi binding nhưng result hiện diện đúng | Handler nhận `BindingResult` | Đọc `isBindingFailure()` và field errors |

**Không khẳng định mọi trường hợp sai vị trí sẽ ném cùng một IllegalStateException.** Đường đi phụ thuộc vào argument resolver đang xử lý, object có errors không, có method validation không, và handler/advice đã đăng ký. Một vài lỗi xảy ra **trước khi controller method được invoke**; không nên dùng breakpoint chỉ ở đầu controller để kết luận “validator không chạy”.

### 5.1. Khi nào MethodArgumentNotValidException xuất hiện?

Trong validation từng đối số của Spring MVC 6.x, một `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` có `@Valid`/`@Validated` mà không có `Errors/BindingResult` ngay sau có thể ném `MethodArgumentNotValidException` nếu validation thất bại. Thường response mặc định là **400 Bad Request**, trừ khi exception resolver/advice tùy biến.

**Sai lầm chẩn đoán:** người phát triển thấy `BindingResult result` ở cuối chữ ký và nghĩ nó chắc chắn ngăn exception. Không đúng — Spring xem **tham số kế tiếp** của argument được validate.

### 5.2. Khi nào HandlerMethodValidationException xuất hiện?

Kể từ Spring Framework 6.1, MVC hỗ trợ built-in **method validation** khi method có direct constraint annotations như:

```java
@GetMapping("/search")
public ResponseEntity<?> find(
        @RequestParam @Min(1) int page) {
    return ResponseEntity.ok().build();
}
```

Đây là fragment. Với `page=0`, `@Min(1)` nằm trực tiếp trên method parameter nên có thể kích hoạt `HandlerMethodValidationException`. Method validation có thể **thay thế** individual-argument validation và bao phủ cả nested constraints qua `@Valid`.

Spring có thể gọi controller khi **tất cả** method-validation errors đều nằm trên method parameters có `Errors` ở ngay sau và được xử lý cục bộ. Nếu có lỗi khác không được xử lý, exception vẫn được ném. Một class-level `@Validated` có thể chuyển sang cơ chế AOP method validation; cần hiểu cấu hình/phiên bản cụ thể.

**Quy tắc thực hành:** ứng dụng có cả DTO validation và direct parameter constraints nên thiết kế exception handling cho cả `MethodArgumentNotValidException` lẫn `HandlerMethodValidationException`, đồng thời vẫn đặt `BindingResult` đúng vị trí nơi sử dụng.

### 5.3. JSON sai cú pháp không có BindingResult hữu ích cho body

Ví dụ request body không hợp lệ:

```text
{"email":,}
```

Message converter không tạo được DTO hợp lệ để Jakarta Validator chạy. `BindingResult` kế sau `@RequestBody` không giúp xử lý lỗi parsing này. Dùng `@RestControllerAdvice`/`ResponseEntityExceptionHandler#handleHttpMessageNotReadable(...)` cho trường hợp đó.

### 5.4. Validation errors khác conversion errors

Với form-urlencoded:

```text
age=not-a-number
```

Nếu DTO có `Integer age`, binder có thể ghi `FieldError` với `isBindingFailure() == true`. Với body JSON có `"age":"not-a-number"`, Jackson có thể không deserialize thành Integer và ném `HttpMessageNotReadableException`.

Hai pipeline có thể tạo mã API khác nhau. Đừng mặc định mọi 400 có thể lấy từ `result.getFieldErrors()`; và đừng gán constraint `@Min` cho trường hợp chưa chuyển được kiểu dữ liệu.

## 6. Demo Java 17 chạy được: ba cách khai báo controller đúng

Project Maven sau chứng minh:

1. `@Valid @ModelAttribute` với `BindingResult` ngay sau.
2. `@Valid @RequestBody` với `BindingResult` ngay sau.
3. Hai `@ModelAttribute` trong cùng handler, mỗi object có `BindingResult` riêng.
4. Khi cố tình **không khai báo** `BindingResult` và dữ liệu sai, lỗi chuyển sang `@RestControllerAdvice`.
5. JSON không đọc được sử dụng handler riêng.
6. Dữ liệu hợp lệ đi qua, dữ liệu không hợp lệ được phân loại mà không phụ thuộc rejected values.

**Vì sao demo không đưa chữ ký sai trực tiếp vào controller chạy chính?** Một handler signature không hợp lệ có thể làm kết quả phụ thuộc thứ tự resolver và dữ liệu, gây nhiễu bài học. Ta giữ một project chạy đúng; các anti-pattern ở phần 4 là fragment so sánh, và phần 9 mô tả cách viết test hồi quy để ngăn tái phạm.

### 6.1. Cấu trúc thư mục

```text
binding-result-order-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── BindingResultOrderApplication.java
    │   ├── SignupForm.java
    │   ├── SignupJson.java
    │   ├── ProfileForm.java
    │   ├── ContactForm.java
    │   ├── InputError.java
    │   ├── SignupController.java
    │   └── InputErrorAdvice.java
    └── test/java/demo/
        └── BindingResultOrderMvcTest.java
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
    <artifactId>binding-result-order-demo</artifactId>
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

`spring-boot-starter-validation` cần thiết cho Jakarta Validation provider trong Boot 3.x. Maven parent quản lý versions phụ thuộc; `spring-boot-starter-test` cung cấp JUnit 5/MockMvc. Không cần database: bài tập trung vào **argument binding và validation routing**.

### 6.3. src/main/java/demo/BindingResultOrderApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingResultOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                BindingResultOrderApplication.class, args);
    }
}
```

### 6.4. src/main/java/demo/SignupForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Đây là JavaBean dùng cho `@ModelAttribute`. Với request `application/x-www-form-urlencoded`, `name=` gây `@NotBlank` violation, `age=abc` có thể gây type conversion error, `age=16` gây `@Min` violation.

### 6.5. src/main/java/demo/SignupJson.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SignupJson(
        @NotBlank String name,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age) {
}
```

Đây là record dành cho `@RequestBody`. Jackson deserialize JSON thành object trước khi Spring áp Bean Validation. Đặt `@Valid` trên method parameter để kích hoạt constraints trên record.

### 6.6. src/main/java/demo/ProfileForm.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public class ProfileForm {

    @NotBlank
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

### 6.7. src/main/java/demo/ContactForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class ContactForm {

    @NotBlank
    @Email
    private String contactEmail;

    public String getContactEmail() {
        return contactEmail;
    }

    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }
}
```

Hai form ở mục 6.6–6.7 có **field names khác nhau** để cùng nhận request parameters mà không mâu thuẫn. Chúng có riêng `BindingResult` tại handler; một lỗi của `profile` không bị gộp ngầm vào `contact`.

### 6.8. src/main/java/demo/InputError.java

```java
package demo;

import java.util.Comparator;
import java.util.List;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

public record InputError(
        String code,
        List<FieldIssue> fields,
        int objectErrors) {

    public record FieldIssue(String field, String kind) {
    }

    public static InputError from(
            String code, BindingResult result) {

        List<FieldIssue> issues = result.getFieldErrors()
                .stream()
                .map(e -> new FieldIssue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "TYPE_MISMATCH"
                                : "CONSTRAINT_VIOLATION"
                ))
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::kind))
                .toList();

        return new InputError(
                code, issues, result.getGlobalErrorCount());
    }
}
```

`InputError` chỉ công bố:

- `code`: mã ứng dụng như `FORM_INVALID`, `JSON_INVALID` hoặc `AUTO_VALIDATION_FAILED`.
- `fields[]`: tên field và nhóm lỗi generic.
- `objectErrors`: số lỗi toàn object, minh họa không nên bỏ qua global errors.

Không serialize nguyên `FieldError`, `getRejectedValue()`, stack trace hay thông điệp từ converter. Đối với API production có thể bổ sung mã chi tiết theo constraint, localization hoặc `ProblemDetail`; ở đây chỉ cần đủ để xác minh routing và adjacency.

### 6.9. src/main/java/demo/SignupController.java

```java
package demo;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SignupController {

    @PostMapping(
            path = "/forms/signup",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formSignup(
            @Valid @ModelAttribute("signupForm")
                    SignupForm form,
            BindingResult errors,
            @RequestParam(
                    name = "source",
                    defaultValue = "browser")
                    String source) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(InputError.from(
                            "FORM_INVALID", errors));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted",
                "source", source));
    }

    @PostMapping(
            path = "/json/signup",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> jsonSignup(
            @Valid @RequestBody SignupJson request,
            BindingResult errors,
            @RequestHeader(
                    name = "X-Client",
                    required = false)
                    String client) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(InputError.from(
                            "JSON_INVALID", errors));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }

    @PostMapping(
            path = "/forms/paired",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> pairedForms(
            @Valid @ModelAttribute("profile")
                    ProfileForm profile,
            BindingResult profileErrors,
            @Valid @ModelAttribute("contact")
                    ContactForm contact,
            BindingResult contactErrors) {

        if (profileErrors.hasErrors()
                || contactErrors.hasErrors()) {
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "PAIRED_INVALID",
                    "profileErrors",
                            profileErrors.getErrorCount(),
                    "contactErrors",
                            contactErrors.getErrorCount()
            ));
        }

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }

    // Không có local BindingResult:
    // Spring sẽ đi theo exception path khi validation lỗi.
    @PostMapping(
            path = "/forms/automatic",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formAutomatic(
            @Valid @ModelAttribute("signupForm")
                    SignupForm form) {

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }

    @PostMapping(
            path = "/json/automatic",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> jsonAutomatic(
            @Valid @RequestBody SignupJson request) {

        return ResponseEntity.ok(Map.of(
                "status", "accepted"));
    }
}
```

**Điểm cần soi trong chữ ký:**

- `formSignup`: sau `SignupForm form` là **`BindingResult errors`**, sau đó mới đến `@RequestParam source`.
- `jsonSignup`: sau `SignupJson request` là **`BindingResult errors`**, rồi đến `@RequestHeader X-Client`. Việc có thêm header không thay đổi cặp request/errors.
- `pairedForms`: hai cặp **`ProfileForm / profileErrors`** và **`ContactForm / contactErrors`** liền nhau. Các lỗi không tự nhập chung thành một.
- `formAutomatic` và `jsonAutomatic` **không có BindingResult** để cố ý minh họa Spring chuyển lỗi validation sang `MethodArgumentNotValidException`; đây là lựa chọn hợp lệ khi muốn tập trung xử lý lỗi qua advice.
- Một `ResponseEntity<?>` cho phép trả body khác nhau ở nhánh thành công và lỗi; production có thể chọn response schema mạnh kiểu hơn.

**Không lẫn hai chiến lược:** một endpoint có thể xử lý lỗi ngay trong controller qua BindingResult, hoặc để global advice xử lý validation exception. Cả hai đều hợp lệ. Lỗi là khi bạn **muốn xử lý cục bộ nhưng đặt result sai thứ tự**, khiến Spring không coi result đó là đối số trực tiếp của DTO.

### 6.10. src/main/java/demo/InputErrorAdvice.java

```java
package demo;

import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
public class InputErrorAdvice
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object>
            handleMethodArgumentNotValid(
                    MethodArgumentNotValidException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        return new ResponseEntity<>(
                InputError.from(
                        "AUTO_VALIDATION_FAILED",
                        ex.getBindingResult()),
                headers,
                status);
    }

    @Override
    protected ResponseEntity<Object>
            handleHttpMessageNotReadable(
                    HttpMessageNotReadableException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        return new ResponseEntity<>(
                Map.of("code", "UNREADABLE_BODY"),
                headers,
                status);
    }
}
```

`ResponseEntityExceptionHandler` của Spring MVC có sẵn integration cho nhiều web exceptions. Override hai method ở trên để **đặt response code/schema** cho:

- `MethodArgumentNotValidException`: DTO parse được nhưng binding/validation có lỗi và handler không có local result đúng vị trí.
- `HttpMessageNotReadableException`: request JSON không đọc/deserialize được.

Không khai báo thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` trùng với method có sẵn của `ResponseEntityExceptionHandler` trong cùng advice mà không hiểu mapping, vì có thể tạo ambiguity. Cách override là phù hợp với ví dụ.

## 7. MockMvc tests: chứng minh result gắn đúng object

### 7.1. src/test/java/demo/BindingResultOrderMvcTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BindingResultOrderMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidFormIsHandledLocally() throws Exception {
        mvc.perform(post("/forms/signup")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "")
                        .param("email", "lan@example.org")
                        .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("FORM_INVALID"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.fields[0].kind")
                        .value("CONSTRAINT_VIOLATION"));
    }

    @Test
    void formBindingTypeFailureIsAvailableLocally()
            throws Exception {
        mvc.perform(post("/forms/signup")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("email", "lan@example.org")
                        .param("age", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("FORM_INVALID"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("age"))
                .andExpect(jsonPath("$.fields[0].kind")
                        .value("TYPE_MISMATCH"));
    }

    @Test
    void validFormCanHaveRequestParamAfterBindingResult()
            throws Exception {
        mvc.perform(post("/forms/signup")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan")
                        .param("email", "lan@example.org")
                        .param("age", "22")
                        .param("source", "mobile"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"))
                .andExpect(jsonPath("$.source")
                        .value("mobile"));
    }

    @Test
    void invalidJsonIsHandledLocally() throws Exception {
        mvc.perform(post("/json/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("JSON_INVALID"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"));
    }

    @Test
    void validJsonCanHaveHeaderAfterBindingResult()
            throws Exception {
        mvc.perform(post("/json/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Client", "mobile")
                        .content("""
                            {"name":"Lan","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }

    @Test
    void malformedJsonIsHandledByConverterAdvice()
            throws Exception {
        mvc.perform(post("/json/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":,}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void eachOfTwoFormsOwnsItsBindingResult()
            throws Exception {
        mvc.perform(post("/forms/paired")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "")
                        .param("contactEmail", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("PAIRED_INVALID"))
                .andExpect(jsonPath("$.profileErrors")
                        .value(1))
                .andExpect(jsonPath("$.contactErrors")
                        .value(1));
    }

    @Test
    void bothFormsCanBeValid() throws Exception {
        mvc.perform(post("/forms/paired")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Lan")
                        .param("contactEmail", "lan@example.org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }

    @Test
    void formWithoutBindingResultUsesAdvice()
            throws Exception {
        mvc.perform(post("/forms/automatic")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "")
                        .param("email", "lan@example.org")
                        .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("AUTO_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"));
    }

    @Test
    void jsonWithoutBindingResultUsesAdvice()
            throws Exception {
        mvc.perform(post("/json/automatic")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("AUTO_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("name"));
    }

    @Test
    void automaticHandlerAlsoAcceptsValidJson()
            throws Exception {
        mvc.perform(post("/json/automatic")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"Lan","email":"lan@example.org",
                             "age":22}
                            """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }
}
```

Đây là **11 integration tests** sử dụng Spring Boot context thật:

1. Form có constraint error → `BindingResult` cục bộ trả `FORM_INVALID`.
2. Form có type conversion error → `BindingResult` cục bộ chứa `TYPE_MISMATCH`.
3. Form hợp lệ → `@RequestParam` đứng sau result vẫn được resolve bình thường.
4. JSON constraint error → `BindingResult` cục bộ trả `JSON_INVALID`.
5. JSON hợp lệ → `@RequestHeader` đứng sau result vẫn hoạt động.
6. JSON sai cú pháp → handler riêng trả `UNREADABLE_BODY`, không nhầm với constraint.
7. Hai form lỗi → mỗi object sở hữu result của nó, hai error counts độc lập.
8. Hai form hợp lệ → controller xử lý thành công.
9. Form không có BindingResult → `MethodArgumentNotValidException` được advice chuyển thành `AUTO_VALIDATION_FAILED`.
10. JSON không có BindingResult → đường advice tương tự.
11. JSON hợp lệ không có BindingResult → controller hoạt động bình thường.

**Lưu ý:** những test trên là kiểm chứng **chữ ký đúng** và sự phân biệt local/advice. Để test việc một chữ ký sai tạo lỗi cụ thể, nên dùng một isolated test controller riêng, vì loại exception và cách resolution có thể thay đổi giữa Spring versions.

### 7.2. Chạy test và server

Từ thư mục `binding-result-order-demo` trên máy có JDK 17+ và Maven:

```bash
mvn -q clean test
```

**Kết quả dự kiến:** 11 test thành công, Maven exit code 0 khi dependencies được tải đầy đủ và môi trường phù hợp. Đây là kỳ vọng đọc từ code, **không phải stdout của một build đã thực hiện**.

Khởi động server:

```bash
mvn spring-boot:run
```

Gửi form sai:

```bash
curl -i -X POST 'http://localhost:8080/forms/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=22'
```

Response HTTP 400 theo schema demo:

```json
{
  "code": "FORM_INVALID",
  "fields": [
    {
      "field": "name",
      "kind": "CONSTRAINT_VIOLATION"
    }
  ],
  "objectErrors": 0
}
```

Gửi JSON sai constraint:

```bash
curl -i -X POST 'http://localhost:8080/json/signup' \
  -H 'Content-Type: application/json' \
  --data '{"name":"","email":"lan@example.org","age":22}'
```

Response:

```json
{
  "code": "JSON_INVALID",
  "fields": [
    {
      "field": "name",
      "kind": "CONSTRAINT_VIOLATION"
    }
  ],
  "objectErrors": 0
}
```

Nếu thay `/json/signup` thành `/json/automatic` với cùng JSON, advice sẽ trả code `AUTO_VALIDATION_FAILED`. Điều đó **không chứng minh form/DTO khác nhau**, mà chứng minh **nơi xử lý lỗi** (local `BindingResult` so với exception advice) thay đổi.

### 7.3. Vì sao không assert message mặc định của validator?

Hibernate Validator có thể dùng thông điệp được nội suy theo locale/resource bundle. Kiểm thử thứ tự BindingResult nên tập trung vào:

- HTTP status.
- **Mã do ứng dụng định nghĩa**.
- Field errors chính xác.
- `isBindingFailure()` khi chuyển kiểu.
- Controller có được gọi hay không.
- Exception advice có được gọi hay không.

Việc assert câu “must not be blank” không giúp phát hiện lỗi adjacency tốt bằng việc assert `FORM_INVALID` (local) so với `AUTO_VALIDATION_FAILED` (global).

## 8. Giải thích từng vị trí trong phương thức đúng

Ví dụ:

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult errors,
        @RequestParam String source,
        Model model,
        Locale locale) {
    // ...
}
```

Vị trí 1 — `SignupForm`: Spring tạo/bind object và kiểm tra Jakarta constraints.

Vị trí 2 — `BindingResult`: Spring đưa đúng kết quả binding/validation của object **ngay trước đó** vào argument này.

Vị trí 3 — `source`: Spring resolve request parameter sau khi đã xử lý cặp form/errors.

Vị trí 4 — `Model`: Spring cung cấp model cho rendering, không chen giữa cặp form/errors.

Vị trí 5 — `Locale`: Spring resolve locale, có thể dùng để nội suy message sau khi có result.

Bạn có thể di chuyển các tham số ở vị trí 3–5 với nhau tùy các ràng buộc khác, nhưng **đừng tách vị trí 1–2**.

### 8.1. Nhiều cặp kết quả

```java
public ResponseEntity<?> save(
        @Valid @ModelAttribute("billing") BillingForm billing,
        BindingResult billingErrors,
        @Valid @ModelAttribute("shipping") ShippingForm shipping,
        BindingResult shippingErrors,
        Model model) {
    // ...
}
```

Mỗi kết quả dùng với object trực tiếp phía trước. Nếu `billing` có lỗi và `shipping` hợp lệ, handler vẫn có thể được gọi để hiển thị cả hai form, miễn cả hai kết quả được đặt đúng và không có validation errors ngoài phạm vi được local handler xử lý.

### 8.2. Đặt Model ở đầu method có được không?

Một chữ ký như:

```java
public String save(
        Model model,
        @Valid @ModelAttribute("form") Form form,
        BindingResult errors) {
    // ...
    return "view";
}
```

vẫn giữ `Form form, BindingResult errors` liền nhau nên thỏa điều kiện về thứ tự cặp này. Không phải mọi tham số `Model` phải ở cuối method. Quy tắc cụ thể là **không có bất cứ argument nào chen giữa validated object và result tương ứng**.

## 9. Chẩn đoán thực tế theo từng bước

Khi controller không vào nhánh `if (result.hasErrors())` như mong đợi:

### Bước 1 — Đọc toàn bộ signature, không chỉ tìm từ BindingResult

Hỏi:

- `@Valid`/`@Validated` gắn trên tham số nào?
- Object được bind là `@ModelAttribute`, `@RequestBody` hay `@RequestPart`?
- **Tham số tiếp theo** ngay sau object có kiểu `Errors`/`BindingResult` không?
- Có `Model`, `Locale`, `@RequestParam` hoặc `Principal` chen giữa không?
- Có nhiều DTO nhưng chỉ một BindingResult ở cuối không?

Nếu có sai thứ tự, chỉnh chữ ký trước khi đào sâu vào provider/constraints.

### Bước 2 — Xác định giai đoạn lỗi

Một request đi qua:

```text
Request mapping
 -> Argument resolution
 -> Data binding / message conversion
 -> Validation
 -> Handler invocation (nếu đủ điều kiện)
 -> Response rendering / exception handling
```

Đặt breakpoint/log ở các chỗ phù hợp:

- `@RestControllerAdvice#handleMethodArgumentNotValid`.
- `handleHttpMessageNotReadable`.
- `@InitBinder` (nếu dùng form binding).
- Đầu controller method.
- `BindingResult#getFieldErrors()` sau khi vào handler.

Nếu controller không được gọi nhưng advice nhận `MethodArgumentNotValidException`, hãy kiểm tra argument kế tiếp của DTO.

### Bước 3 — Kiểm tra exception loại nào

- `MethodArgumentNotValidException`: một validated argument có errors mà không được xử lý local theo chữ ký.
- `HandlerMethodValidationException`: method-level constraints.
- `HttpMessageNotReadableException`: parsing/deserialization.
- `IllegalStateException` liên quan Resolver/BindingResult: chữ ký/khả năng tìm đúng binding result cần được kiểm tra.
- `HttpMediaTypeNotSupportedException`: Content-Type không khớp endpoint.

Đừng fix thứ tự để chữa lỗi JSON syntax, cũng đừng đổi advice để che giấu chữ ký sai.

### Bước 4 — Kiểm tra dự định xử lý lỗi

**Muốn controller tự render form có lỗi:** dùng `@Valid @ModelAttribute form, BindingResult result` liền nhau rồi trả view form.

**Muốn REST API trả một schema chung:** có thể không cần local BindingResult và dùng `@RestControllerAdvice`; lúc đó `MethodArgumentNotValidException` là hành vi chủ đích, không phải “lỗi thiếu BindingResult”.

**Muốn phản hồi từ controller tùy tình huống lỗi:** giữ cặp đúng vị trí và xử lý result cục bộ. Không vừa mong advice bắt tất cả `MethodArgumentNotValidException` vừa mong controller luôn chạy nhánh local trên cùng request.

### Bước 5 — Kiểm tra dữ liệu, provider và converter

Nếu đã đúng adjacency nhưng không thấy lỗi:

- DTO có constraints trên field/getter/record components không?
- Method parameter có `@Valid` hoặc `@Validated` không?
- Có Bean Validation implementation (ví dụ Hibernate Validator từ `spring-boot-starter-validation`) không?
- Request là form params hay JSON body? Có dùng đúng annotation không?
- Form DTO có constructor/setter/bindable properties phù hợp không?
- Có `@InitBinder` thay validator hoặc `setAllowedFields` quá chặt không?
- JSON có parse thành đúng type không?
- Có validation groups khiến constraint không thuộc group đang chạy không?
- Controller có direct method constraints làm đường exception đổi thành `HandlerMethodValidationException` không?

Thứ tự đúng là **điều kiện cần cho local result**, không bảo đảm constraints được kích hoạt khi thiếu provider/config.

### Bước 6 — Viết một MockMvc regression test

Tạo request sai **một field duy nhất** và assert:

- HTTP 400.
- Mã **local handler** dự kiến, không phải code từ advice.
- Field name đúng.
- Không lộ rejected values.
- Request hợp lệ vẫn trả 200.

Nếu trước đó result đặt sai, test như vậy giúp phát hiện lỗi khi ai đó chèn thêm `Locale` hoặc `@RequestParam` vào giữa cặp trong tương lai.

## 10. BindingResult và field errors: đọc đúng thông tin

Khi đã vào handler với result hợp lệ:

```java
if (result.hasErrors()) {
    for (FieldError error : result.getFieldErrors()) {
        String field = error.getField();
        boolean bindingFailure = error.isBindingFailure();
        String springCode = error.getCode();
        String defaultMessage = error.getDefaultMessage();
    }
}
```

Đây là fragment. Ý nghĩa:

- `getField()`: đường dẫn property, ví dụ `email` hoặc `addresses[0].city`.
- `isBindingFailure()`: có phải lỗi gắn/chuyển kiểu dữ liệu không.
- `getCode()` và `getCodes()`: các mã tra cứu thông điệp của Spring, không nhất thiết là **stable API error codes**.
- `getDefaultMessage()`: thông điệp fallback; có thể đã được nội suy theo locale/provider.
- `getGlobalErrors()`: lỗi toàn object không có field path riêng.
- `getSuppressedFields()`: field bị WebDataBinder loại khỏi property binding, không mặc nhiên làm `hasErrors()` true.

**Tránh serializing nguyên result ra REST response.** Rejected values có thể chứa email, mật khẩu, token hoặc thông tin cá nhân. Demo chủ động chọn field name và mã generic an toàn.

### 10.1. Một field có thể có nhiều lỗi

Nếu `email=""` với `@NotBlank @Email`, số lỗi tùy provider và constraints được kích hoạt. Đừng assume `getFieldErrors()` chỉ chứa một FieldError cho mỗi field. Với những tests nhắm đến vị trí BindingResult, dùng payload chỉ vi phạm **một constraint rõ ràng** để assertion ít phụ thuộc provider.

### 10.2. Global errors không phải lỗi field

Một class-level constraint có thể tạo `ObjectError` mà không thuộc property cụ thể. Đừng suy từ `getFieldErrorCount()` bằng 0 rằng hoàn toàn không có lỗi; dùng `hasErrors()` hoặc `getErrorCount()` và xử lý cả `getGlobalErrors()`.

### 10.3. BindingResult#getModel không thay việc truyền Model

`result.getModel()` có thể cung cấp map chứa target và BindingResult metadata để thêm vào model; tuy nhiên đây không phải lý do được đặt `Model` giữa argument và result. `Model model` và `BindingResult result` là hai đối số có mục đích riêng; quy tắc adjacency vẫn được giữ.

## 11. @Valid, @Validated, groups và method validation

### 11.1. @Valid là cascade marker, không phải constraint trực tiếp

`jakarta.validation.Valid` kích hoạt validation đối với object/nested properties. Bản thân `@Valid` không phải một `Constraint` như `@Min`. Theo Spring MVC 6.1+, khi có **direct constraints** trên method parameters, method validation có thể áp dụng và thay thế individual parameter validation.

### 11.2. @Validated với groups

Ví dụ:

```java
@PostMapping("/approval")
public String approve(
        @Validated(ApprovalGroup.class)
        @ModelAttribute("request") ApprovalForm form,
        BindingResult errors) {
    // ...
    return errors.hasErrors() ? "form" : "done";
}
```

Đây là fragment; `ApprovalGroup` và `ApprovalForm` cần có trong ứng dụng. Dù dùng validation groups, `BindingResult` vẫn phải ngay sau object; group selection không nới lỏng thứ tự.

### 11.3. Class-level @Validated trong controller

Với các Spring phiên bản/config khác nhau, class-level `@Validated` có thể bật AOP method validation thay cho built-in MVC method validation. Tài liệu Spring MVC 6.2 khuyến nghị chú ý khi chuyển sang built-in method validation (Spring 6.1+). Nếu quan sát lỗi khác thường:

- Kiểm tra lớp controller có `@Validated` không.
- Kiểm tra direct constraint annotations trên method parameters.
- Kiểm tra MVC có xử lý `HandlerMethodValidationException` không.
- Không giải thích mọi validation exception là do `BindingResult` đặt sai vị trí.

### 11.4. Không nhầm BindingResult với @ExceptionHandler

`BindingResult` là local argument kết quả cho **đối tượng cụ thể**. `@ExceptionHandler`/`ResponseEntityExceptionHandler` là global hoặc controller-level exception routing. Bạn có thể chọn một trong hai cho một luồng thông thường, hoặc kết hợp ở các endpoints khác nhau, nhưng không thay thế quy tắc signature bằng advice.

## 12. Những hiểu nhầm phổ biến

### 12.1. “BindingResult cứ có trong method là được”

Sai. Nó phải ở **ngay sau** object tương ứng. Compiler Java không kiểm tra quy tắc framework này.

### 12.2. “Đặt Model trước BindingResult để render form”

Không. Đặt `BindingResult` sát object, `Model` sau đó hoặc trước cả cặp.

### 12.3. “Chỉ cần đổi tên biến thành formBindingResult”

Không. Spring không match result với object dựa trên tên biến Java.

### 12.4. “Một BindingResult gom lỗi của hai @ModelAttribute”

Không. Mỗi DTO cần một result riêng ngay sau nó nếu muốn local handling cho cả hai.

### 12.5. “@RequestBody không bao giờ dùng được BindingResult”

Sai trong Spring MVC đối với validation của object phù hợp. `@Valid @RequestBody DTO dto, BindingResult result` là mẫu được tài liệu hóa. Nhưng errors khi JSON **không decode được** vẫn không đi qua local result này.

### 12.6. “Có BindingResult thì mọi lỗi đều vào result.hasErrors()”

Không. JSON parse failure, unsupported media type, missing required body, security failures hoặc method-validation errors không được local-handled có thể được xử lý trước khi controller được gọi. `hasErrors()` chỉ mô tả binding/validation errors của object mà nó thuộc về.

### 12.7. “Không có BindingResult luôn là bug”

Không. Với REST API dùng global exception advice, có thể cố ý **không khai báo** result. Khi validation fail, Spring ném exception và advice trả schema lỗi nhất quán. Bug là **muốn local handling nhưng đặt result sai**.

### 12.8. “Lỗi HTTP 400 chứng minh result sai vị trí”

Không. 400 còn có nhiều nguyên nhân như thiếu parameter, JSON sai, type mismatch, constraint violation hoặc malformed multipart. Xem exception/log/argument signature cụ thể.

### 12.9. “Đổi result từ BindingResult sang Errors sẽ hết lỗi”

Không. `Errors` và `BindingResult` cùng chịu quy tắc adjacency.

### 12.10. “@NotBlank đã nằm trong DTO thì chắc chắn validator chạy”

Không nếu thiếu `@Valid`/`@Validated` ở boundary cần validation, provider không có, groups không khớp hoặc controller dùng argument resolver khác. Kiểm tra cấu hình trước khi kết luận constraints sai.

### 12.11. “Form binding và JSON deserialization lỗi giống hệt nhau”

Không. Form property conversion có thể tạo `FieldError.isBindingFailure()`; JSON deserialization type failure thường xảy ra trong message converter và có thể ném `HttpMessageNotReadableException`.

### 12.12. “Bổ sung @InitBinder giải quyết lỗi BindingResult sai vị trí”

Không. `@InitBinder` cấu hình WebDataBinder/validator, không tự di chuyển method arguments. Sửa chữ ký trước.

### 12.13. “Bắt IllegalStateException toàn cục là đủ”

Không nên. `IllegalStateException` còn đại diện nhiều lỗi lập trình khác. Một handler bắt rộng sẽ che dấu sai cấu hình. Sửa chữ ký controller và thêm test, chỉ map các exception đã biết sang error contract.

### 12.14. “Chỉ test request hợp lệ là đủ”

Không. Với input hợp lệ, một chữ ký sai có thể biểu hiện khác trường hợp validation fail. Luôn test ít nhất một constraint violation và một binding type failure khi form có conversion.

## 13. Ma trận chẩn đoán nhanh

| Triệu chứng | Kiểm tra đầu tiên | Cách sửa |
| --- | --- | --- |
| Có `BindingResult` nhưng handler không nhận invalid request | Result có sát `@Valid` DTO? | Chuyển result ngay sau DTO |
| Có `Model` rồi mới result | Model chen giữa? | Đặt Model sau result |
| Có `Locale`/`@RequestParam` ở giữa | Khoảng cách giữa DTO và result | Đảo thứ tự |
| Hai forms cùng method nhưng chỉ một result | DTO thứ nhất có result kề không? | Một BindingResult cho mỗi DTO |
| Invalid JSON ném `MethodArgumentNotValidException` | Có muốn local handling không? | Có: result ngay sau body; không: dùng advice |
| JSON sai cú pháp không vào local result | Converter có tạo được object? | Handle `HttpMessageNotReadableException` |
| `page=0` với direct `@Min` ném exception khác | Method validation có active? | Handle `HandlerMethodValidationException` |
| `age=abc` trong form | Có `isBindingFailure()` không? | Kiểm tra type conversion và field error |
| Đúng signature nhưng constraints không chạy | Provider và `@Valid`/groups | Sửa validation setup |
| Đúng signature, lỗi vẫn bị nuốt | Có branch `hasErrors()` không? | Kiểm tra result, response và tests |
| Result thuộc object sai | Nhiều DTO và thứ tự cặp | Gắn từng result sát DTO |
| Mất field errors trong response | Chỉ đọc global hoặc field errors? | Xử lý cả hai nhóm |

## 14. Checklist code review trước khi merge controller

- [ ] Mỗi `BindingResult`/`Errors` đứng **ngay sau** argument nó mô tả.
- [ ] Không có `Model`, `Locale`, `Principal`, `@RequestParam` hay `@RequestHeader` chen giữa.
- [ ] Nhiều `@ModelAttribute` cần xử lý local errors thì có **nhiều kết quả riêng**.
- [ ] `@Valid`/`@Validated` dùng đúng nơi; validation provider được khai báo.
- [ ] Không gọi Bean Validation trên request body chưa deserialize được.
- [ ] Phân biệt form binding error, JSON converter error và method validation exception.
- [ ] Có contract rõ: local BindingResult hay global exception advice.
- [ ] Có MockMvc test invalid form và invalid JSON.
- [ ] Có ít nhất một test type conversion failure nếu dùng `@ModelAttribute`.
- [ ] Tests kiểm tra status, code, field name và branch handler/advice mong muốn.
- [ ] Không trả raw rejected values, exception messages hoặc stack traces.
- [ ] Có xử lý global/object errors nếu sử dụng class-level constraints.
- [ ] Có test cho hai DTO trong cùng handler nếu chức năng hỗ trợ.
- [ ] Khi thêm argument mới vào method, không chèn vào giữa cặp DTO/result.
- [ ] Khi nâng Spring Framework 6.1+, xem đường `HandlerMethodValidationException` nếu có direct constraints.
- [ ] Không dùng exception handler rộng để che giấu IllegalStateException do sai chữ ký.

## 15. Kết luận

**BindingResult không đứng đúng vị trí trong chữ ký controller** là một lỗi nhỏ về cú pháp framework nhưng có thể tạo hành vi khó hiểu: controller không được gọi, validation errors chuyển sang exception advice, hoặc resolver báo không tìm thấy result đúng chỗ.

Quy tắc sửa luôn bắt đầu từ signature:

```java
@Valid @ModelAttribute("form") Form form,
BindingResult errors,
Model model
```

và tương ứng:

```java
@Valid @RequestBody RequestDto request,
BindingResult errors,
@RequestHeader("X-Client") String client
```

**Giữ object và result liền nhau**. Khi xử lý nhiều object, mỗi object cần result của riêng nó. Khi không cần local errors, bỏ result một cách chủ đích và dùng global exception handling. Đồng thời phân biệt `MethodArgumentNotValidException`, `HandlerMethodValidationException` và lỗi HTTP message converter để không chẩn đoán nhầm.

Kết hợp kiểm tra thứ tự tham số với **MockMvc regression tests** cho invalid input là cách đơn giản và có hiệu quả lâu dài nhất để ngăn lỗi này tái diễn.

## Tài liệu tham khảo

- [Spring Framework 6.2 — MVC Method Arguments: Errors và BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — @ModelAttribute và BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @RequestBody, @Valid và BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MVC Validation, MethodArgumentNotValidException và HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @RequestPart and Multipart Forms](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — ErrorsMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/ErrorsMethodArgumentResolver.html)
- [Spring Framework 6.2 — MethodArgumentNotValidException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Spring Framework 6.2 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot 3.4 — Validation](https://docs.spring.io/spring-boot/3.4/reference/io/validation.html)
