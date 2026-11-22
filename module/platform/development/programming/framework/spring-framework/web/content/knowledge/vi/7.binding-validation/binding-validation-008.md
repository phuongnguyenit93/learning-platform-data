# Phân biệt lỗi chuyển đổi kiểu, lỗi binding và lỗi kiểm tra dữ liệu trong Spring MVC

## 1. Mục tiêu và bức tranh tổng thể

Khi một request gửi dữ liệu tới controller, **lỗi chuyển đổi kiểu (type conversion)**, **lỗi binding (data binding)** và **lỗi kiểm tra dữ liệu (validation)** mô tả các vấn đề ở **những công đoạn liên quan nhưng khác nhau**. Một response `400 Bad Request` không tự cho biết công đoạn nào thất bại. Bạn cần đọc loại tham số controller, exception, `BindingResult` và cấu hình để chẩn đoán chính xác.

Sau bài này, bạn có thể:

- Mô tả luồng nhận request từ chuỗi đầu vào, chuyển kiểu, gắn vào object rồi áp constraint nghiệp vụ.
- Phân biệt conversion error của `@RequestParam`/`@PathVariable` với field binding error của `@ModelAttribute`.
- Phân biệt lỗi parse/deserialization JSON của `@RequestBody` với lỗi Jakarta Bean Validation xảy ra *sau khi* tạo object.
- Hiểu `BindingResult`, `FieldError`, `ObjectError`, `typeMismatch`, `@Valid`, `@Validated` và cơ chế báo lỗi mặc định.
- Chọn cách trả lỗi HTTP, kiểm thử theo giai đoạn và tránh để dữ liệu lỗi đi vào nghiệp vụ.

**Phạm vi:** Spring MVC trên Servlet stack, Java 17+, Spring Framework 6.1+/Spring Boot 3.x với Jakarta Validation. Một số chi tiết exception thay đổi giữa phiên bản hoặc phụ thuộc handler tùy chỉnh; bài sẽ chỉ rõ các trường hợp phổ biến và ngoại lệ quan trọng. Đây không phải mô tả riêng cho Spring WebFlux.

## 2. Ba lớp xử lý: conversion, binding, validation

### 2.1. Luồng tư duy

```text
HTTP request
  |
  +--> Tìm handler và resolver phù hợp
  |       (@RequestParam / @PathVariable / @ModelAttribute / @RequestBody)
  |
  +--> Đọc dữ liệu đầu vào
  |       query/form/header/path thường là chuỗi;
  |       JSON body là byte -> JSON token
  |
  +--> Chuyển đổi dữ liệu
  |       "42" -> Integer(42)
  |       "2026-10-21" -> LocalDate
  |       JSON -> object Java qua HttpMessageConverter/Jackson
  |
  +--> Binding nếu là model attribute
  |       gắn các property vào target object;
  |       ghi lỗi property trong BindingResult
  |
  +--> Validation nếu được kích hoạt
  |       @NotBlank, @Min, @NotNull, custom validator,
  |       constraint cho nhiều field hoặc method parameter
  |
  +--> Handler controller và business logic khi hợp lệ
```

Đây là sơ đồ **khái niệm**, không phải mọi loại tham số đều trải qua đủ tất cả các bước. Ví dụ `@RequestParam Integer` được một argument resolver chuyển kiểu trực tiếp, không cần một object form để bind; `@RequestBody` dùng `HttpMessageConverter`/Jackson để deserialize JSON, không bind JSON bằng cùng cơ chế property của `@ModelAttribute`.

### 2.2. Định nghĩa chính xác

**Chuyển đổi kiểu (conversion)**: biến một giá trị nguồn thành kiểu Java đích, thường qua `ConversionService`, `Converter`, `Formatter` hoặc `PropertyEditor`. Ví dụ `"abc"` không đổi được thành `Integer`, còn chuỗi ngày sai format không đổi được thành `LocalDate`. Conversion là một **bước** có thể xảy ra trong binding.

**Data binding**: nối các giá trị request với các tham số constructor/thuộc tính của object, thường do `WebDataBinder` thực hiện với `@ModelAttribute`. Binding bao gồm việc xác định property, áp conversion và ghi nhận các vấn đề phát sinh. Vì thế **một conversion error có thể được biểu diễn như một binding error** ở field cụ thể, chứ không phải hai lỗi loại trừ nhau.

**Validation**: xét dữ liệu đã có kiểu Java theo các ràng buộc hợp lệ. Ví dụ `Integer age = 0` là giá trị hoàn toàn chuyển kiểu được nhưng vi phạm `@Min(1)`; `name = ""` vẫn là `String` hợp lệ theo Java nhưng vi phạm `@NotBlank`. Spring hỗ trợ Jakarta Bean Validation qua `@Valid`/`@Validated` và Spring `Validator`.

### 2.3. So sánh nhanh

| Tình huống | Bước thất bại thường gặp | Minh họa | Kết quả HTTP thường gặp |
| --- | --- | --- | --- |
| Query `?age=abc` gắn vào `@RequestParam Integer age` | Type conversion của method argument | Chuỗi không thể thành Integer | `400`, thường `MethodArgumentTypeMismatchException` |
| Form `age=abc` gắn vào `@ModelAttribute Form.age` | Field conversion **trong data binding** | `BindingResult` có `FieldError` và mã `typeMismatch` | Controller tự xử lý nếu có `BindingResult`; nếu không, thường `400` |
| Form có property không thể ghi hoặc constructor không bind được | Binding/khởi tạo object | Setter, constructor, field không khớp | Tùy kiểu lỗi/cấu hình; có thể thành lỗi binding hoặc exception khác |
| Form `age=0` và `@Min(1)` | Validation | Giá trị Integer hợp lệ nhưng sai constraint | Có `FieldError` mã `Min`, hoặc mặc định `400` |
| JSON `{"age":"oops"}` với `Integer age` | JSON deserialization | Jackson không tạo được object | Thường `400`, `HttpMessageNotReadableException` |
| JSON `{"age":0}` với `@Min(1)` | Validation sau deserialize | Object được tạo nhưng vi phạm constraint | `400`, thường `MethodArgumentNotValidException` |
| Query `?age=0` với constraint `@Min(1)` trực tiếp trên tham số | Handler **method validation** | Giá trị chuyển kiểu được, vi phạm constraint method | Spring MVC 6.1+ thường `HandlerMethodValidationException`, `400` cho lỗi đầu vào |

**Không nên viết quy tắc “conversion = một exception, binding = một exception, validation = một exception” cho mọi kiểu controller argument.** Exception phụ thuộc *nguồn dữ liệu* và *giai đoạn*.

## 3. Conversion: lỗi biến chuỗi thành kiểu Java

### 3.1. Tham số đơn giản: `@RequestParam` và `@PathVariable`

```java
@GetMapping("/products")
public String products(@RequestParam("page") int page) {
    return "page=" + page;
}
```

| Request | Diễn giải | Kết quả phổ biến |
| --- | --- | --- |
| `GET /products?page=3` | `"3"` chuyển thành `int 3` | Controller chạy |
| `GET /products?page=abc` | Không parse được số | `400`: conversion error |
| `GET /products` | Thiếu parameter required | `400`: thiếu parameter, **không phải conversion** |
| `GET /products?page=` | Rỗng có thể chuyển thành null; `int` không nhận null | `400`, có thể được mô tả là thiếu sau conversion |
| `GET /products?page=-1` | Chuyển số `-1` thành công | Controller chạy nếu chưa bật constraint `@Min(1)` |

Các exception thường gặp:

- `MethodArgumentTypeMismatchException`: conversion thất bại cho một method argument như `@RequestParam` hoặc `@PathVariable`.
- `MissingServletRequestParameterException`: thiếu tham số bắt buộc; Spring cũng có cơ chế phân biệt trường hợp **có tên parameter nhưng trở thành null sau conversion**.
- `MissingPathVariableException`: một URI template variable bắt buộc không resolve được; cần phân biệt với URL không match handler.
- `TypeMismatchException` của Spring là loại nền tảng cho lỗi chuyển kiểu; không nên mặc định ngoại lệ quan sát được tại tất cả tầng luôn là một subclass cố định.

Một URL `/products/abc` với `@PathVariable Long id` thường thất bại lúc convert thành Long; ngược lại `/products` có thể không khớp mapping `/products/{id}` và trả **404**, trước khi method argument conversion xảy ra.

### 3.2. Ngày giờ, enum và formatter

```java
@GetMapping("/reports")
public String report(
        @RequestParam
        @org.springframework.format.annotation.DateTimeFormat(iso =
                org.springframework.format.annotation.DateTimeFormat.ISO.DATE)
        java.time.LocalDate from) {
    return from.toString();
}
```

`?from=2026-10-21` hợp lệ; `?from=tomorrow` hoặc `?from=2026-99-99` không đúng định dạng/giá trị ngày và thường gây 400 trước khi gọi controller. Với enum, tên giá trị thường phân biệt hoa/thường theo converter mặc định, trừ khi bạn đăng ký converter tùy chỉnh.

Chỉnh cách chuyển kiểu bằng `FormattingConversionService`/`Converter`/`Formatter` toàn cục hoặc `@InitBinder`/`WebDataBinder` cho phạm vi controller. Không viết custom converter để “nuốt lỗi” rồi trả `null` nếu ứng dụng cần biết input không hợp lệ; việc đó dễ biến conversion error thành missing.

### 3.3. Lỗi kiểu dữ liệu và lỗi nghiệp vụ khác nhau

`?amount=abc` không thể parse thành `BigDecimal` là **conversion error**. `?amount=-50` chuyển thành số thành công; nếu giao ước yêu cầu amount dương thì đây là **validation error**. `?currency=VND` parse thành enum hợp lệ nhưng tài khoản không hỗ trợ VND có thể là **business rule error**, nằm ngoài hai loại trên. Không suy ra mọi `400` là Bean Validation.

## 4. Data binding: gắn form/query vào object

### 4.1. `@ModelAttribute` đi qua `WebDataBinder`

```java
public class RegisterForm {
    private String email;
    private Integer age;

    public RegisterForm() {}

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
}
```

```java
@PostMapping("/register-form")
public String register(
        @ModelAttribute("form") RegisterForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "INVALID";
    }
    return "OK";
}
```

Đây là **hai đoạn minh họa**, giả định các import Spring cần thiết. Request form với `email=lan@example.com&age=abc` có thể tạo object `RegisterForm`, gắn `email` thành công, nhưng conversion sang `Integer age` lỗi. `BindingResult` chứa `FieldError` cho `age`, thường có code chính `typeMismatch`; handler trên vẫn được gọi vì đã đặt `BindingResult` **ngay sau** `@ModelAttribute`.

Nếu form có `age=20`, binder gắn vào `Integer` thành công; **không có validation ràng buộc tuổi** chỉ vì field tên là `age`. Cần khai báo constraint và kích hoạt validation nếu muốn giới hạn.

Trường `BindingResult` bao gồm dữ liệu quan trọng:

- `hasErrors()`, `getErrorCount()`: có lỗi hay không, số lỗi.
- `getFieldErrors()`: các `FieldError` liên quan property, ví dụ `age`.
- `getGlobalErrors()`: `ObjectError` ở mức toàn object, ví dụ mối quan hệ giữa hai field.
- `FieldError.getField()`: tên property như `"age"`.
- `FieldError.getCode()`: mã lỗi tổng quát, ví dụ `typeMismatch` hoặc `Min`; `getCodes()` có danh sách mã có độ ưu tiên từ cụ thể tới chung.
- `FieldError.getRejectedValue()`: giá trị bị từ chối; **không tự đưa nguyên giá trị này vào log/response** vì có thể chứa dữ liệu nhạy cảm.
- `FieldError.isBindingFailure()`: đánh dấu lỗi liên quan binding; lỗi constraint validation thường có `isBindingFailure() == false`. Đây là dấu hiệu hữu ích, nhưng đừng dùng một flag đơn độc để quyết định tất cả lỗi hạ tầng.
- `getSuppressedFields()`: danh sách field bị bỏ qua do không được phép bind; **không nhất thiết tạo FieldError**. Kiểm tra khi có cơ chế allowlist để tránh mass assignment.

### 4.2. Binding gồm nhiều hơn lỗi parse số

Một data binding failure còn có thể liên quan tên property không hợp lệ, setter/constructor, nested field, indexed property, required field do `WebDataBinder` cấu hình hoặc conversion/formatting. Với `ignoreUnknownFields` mặc định của `DataBinder`, field lạ có thể bị bỏ qua thay vì thành `FieldError`. Tùy chính sách `allowedFields`/`disallowedFields`, field không được bind có thể bị suppressed mà **không được xem là validation error**.

Nếu request là API nhận form, nên dùng DTO input riêng với những field được phép sửa. Đừng bind trực tiếp vào JPA entity chứa `id`, `role`, `isAdmin` hoặc các field nhạy cảm mà client không được đổi; kết hợp allowlist và kiểm tra `getSuppressedFields()` nếu cần.

### 4.3. `BindingResult` phải nằm ngay sau argument tương ứng

Đúng:

```java
@PostMapping("/save")
public String save(@Valid @ModelAttribute("form") RegisterForm form,
                   BindingResult result) {
    return result.hasErrors() ? "INVALID" : "SAVED";
}
```

Sai vì không đặt cạnh đối tượng được binding/validation:

```java
// Ví dụ KHÔNG hợp lệ: đừng sao chép vào controller thực tế.
@PostMapping("/save")
public String save(@Valid @ModelAttribute("form") RegisterForm form,
                   @RequestParam String source,
                   BindingResult result) {
    return "UNRELIABLE";
}
```

Spring yêu cầu `Errors` hoặc `BindingResult` **ngay sau** tham số được bind/validate tương ứng. Nếu có nhiều model attribute, mỗi `BindingResult` phải theo ngay sau đúng đối tượng. Khi đặt sai, có thể gặp `IllegalStateException` liên quan đến BindingResult/Errors hoặc framework ném exception thay vì đưa lỗi vào argument mong muốn.

### 4.4. Không có `BindingResult` thì sao?

Với Spring MVC hiện đại, binding/validation error của một `@ModelAttribute` có thể dẫn đến `MethodArgumentNotValidException` và thường status 400 khi không có `BindingResult`/`Errors` phù hợp. Trong tài liệu cũ hoặc đường xử lý đặc thù, bạn có thể gặp `BindException`. **Đừng tự cố định một lớp exception cho mọi phiên bản Spring và mọi kiểu argument.** Với ứng dụng dùng template MVC, việc thêm `BindingResult` cho phép hiển thị lỗi bên cạnh form thay vì nhận 400 mặc định.

## 5. Validation: dữ liệu có kiểu hợp lệ nhưng vi phạm constraint

### 5.1. Cần khai báo và kích hoạt ràng buộc

Ví dụ dùng Jakarta Bean Validation:

```java
public record CreateUser(
        @jakarta.validation.constraints.NotBlank String name,
        @jakarta.validation.constraints.NotNull
        @jakarta.validation.constraints.Min(18) Integer age) {}
```

- `name=""` hoặc `name="   "`: chuyển thành String được, nhưng `@NotBlank` thất bại.
- `age=17`: chuyển thành Integer được, nhưng `@Min(18)` thất bại.
- `age=null`: vi phạm `@NotNull`. Riêng `@Min` thường coi null là hợp lệ; cần phối hợp `@NotNull` nếu bắt buộc phải có tuổi.
- `age="abc"` trong JSON: có thể thất bại lúc Jackson deserialize, **trước** khi `@Min` đánh giá được một số nguyên.
- `@Valid` kích hoạt kiểm tra constraint ở argument thích hợp; đặt annotation constraint lên DTO nhưng không kích hoạt validation đúng cách có thể khiến request sai vẫn qua controller.

Dependency thường cần trong Spring Boot 3: `spring-boot-starter-validation`. Spring MVC Web dependency không mặc định đảm bảo mọi provider validation đã sẵn sàng. Khi dùng Jakarta Validation trong Boot 3, import `jakarta.validation.*`, không dùng `javax.validation.*` từ các ví dụ Boot 2 cũ.

### 5.2. `@NotNull`, `@NotEmpty`, `@NotBlank`

| Constraint | null | Chuỗi `""` | Chuỗi `"   "` |
| --- | --- | --- | --- |
| `@NotNull` | Không hợp lệ | Hợp lệ | Hợp lệ |
| `@NotEmpty` | Không hợp lệ | Không hợp lệ | Hợp lệ |
| `@NotBlank` | Không hợp lệ | Không hợp lệ | Không hợp lệ |

`@NotEmpty` áp dụng cho những kiểu container/`CharSequence` được hỗ trợ, trong khi `@NotBlank` dùng cho chuỗi. `@Size(min=1)` riêng lẻ không có nghĩa “không null”; thông thường null vẫn qua constraint `@Size`.

### 5.3. Field-level và object-level errors

Một constraint trên property thường tạo `FieldError` với code như `NotBlank` hoặc `Min`. Constraint ở mức class, chẳng hạn “ngày kết thúc phải sau ngày bắt đầu”, có thể tạo `ObjectError`/global error. Giao diện API nên có khả năng biểu diễn cả **field errors** và **global errors**, tránh giả định mọi lỗi có một tên field.

### 5.4. Validation groups

`@Validated(Create.class)`/`@Validated(Update.class)` cho phép áp những nhóm constraint phù hợp với thao tác tạo/cập nhật. Tránh ép yêu cầu “tạo mới phải có mọi field” lên PATCH vốn cho phép bỏ qua field. Groups không thay thế việc phân biệt trường JSON **vắng mặt** và **explicit null**: khi DTO đã deserialize thành cùng Java null, validator không thể tự khôi phục sự hiện diện của field.

## 6. `@RequestBody`: deserialization là một đường xử lý khác

Ví dụ:

```java
@PostMapping(path = "/users", consumes = "application/json")
public String create(@Valid @RequestBody CreateUser input) {
    return "OK";
}
```

Khi có Jackson, `MappingJackson2HttpMessageConverter` đọc JSON rồi chuyển thành `CreateUser`. Quá trình này **không đồng nhất** với việc `WebDataBinder` gắn `age` từ form parameter.

| JSON body | Giai đoạn | Kết quả thường thấy |
| --- | --- | --- |
| `{"name":"Lan","age":25}` | Deserialize và validate đều thành công | Handler chạy |
| `{"name":"Lan","age":"oops"}` | Jackson không chuyển `"oops"` thành Integer | `HttpMessageNotReadableException`, 400 |
| `{"name":"Lan","age":17}` | Deserialize thành công, `@Min(18)` lỗi | `MethodArgumentNotValidException`, 400 |
| `{"name":"","age":25}` | Deserialize thành công, `@NotBlank` lỗi | `MethodArgumentNotValidException`, 400 |
| `{"name":"Lan","age":25` | JSON sai cú pháp | `HttpMessageNotReadableException`, 400 |
| Không gửi body với `@RequestBody` bắt buộc | Thiếu nội dung request body | Thường `HttpMessageNotReadableException`, 400 |
| Gửi `text/plain` tới endpoint chỉ `consumes="application/json"` | Media type không được hỗ trợ | `415 Unsupported Media Type`, **không phải validation** |

Nếu ứng dụng cấu hình Jackson custom coercion (ví dụ đổi chuỗi số thành số, hay coi chuỗi rỗng là null), kết quả có thể khác. Hãy kiểm tra ObjectMapper thực tế. Không bắt `HttpMessageNotReadableException` rồi mô tả mọi trường hợp là “vi phạm `@Min`”; validation chưa chắc đã chạy.

**`@Valid @RequestBody DTO, BindingResult`** được Spring MVC hỗ trợ nếu đặt `BindingResult` ngay sau DTO, cho phép controller nhận lỗi validation của object đã đọc thành công. Nhưng khi JSON không deserialize được, controller thường **không có object** để kèm `BindingResult`; request vẫn lỗi trước khi tới method.

## 7. Method validation: điểm khác biệt từ Spring MVC 6.1+

Có hai chế độ quan trọng:

1. **Argument validation**: `@Valid` hoặc `@Validated` trên đối tượng `@RequestBody`, `@ModelAttribute`, `@RequestPart`, và không cần method validation do constraint trực tiếp trên tham số. Lỗi mặc định thường là `MethodArgumentNotValidException` nếu không có `BindingResult` ngay sau đối tượng.
2. **Method validation**: constraint như `@Min`, `@NotBlank`, `@NotNull` đặt **trực tiếp** trên controller method parameter (hoặc return value) khiến Spring MVC 6.1+ xác thực ở mức phương thức. Lỗi đầu vào thường là `HandlerMethodValidationException`, thường HTTP 400. Method validation bao gồm cả các ràng buộc lồng qua `@Valid` khi cần.

Ví dụ:

```java
@GetMapping("/min-page")
public String minPage(
        @RequestParam("page")
        @jakarta.validation.constraints.Min(1) int page) {
    return "page=" + page;
}
```

- `?page=abc`: conversion thất bại **trước validation**.
- `?page=0`: conversion thành int thành công rồi `@Min(1)` lỗi; Spring MVC 6.1+ thường ném `HandlerMethodValidationException`.
- `?page=2`: hợp lệ.

`@Valid` **không phải** constraint trực tiếp để tự kích hoạt method validation; nó dùng để cascade constraint bên trong object. Ngược lại `@NotNull` là một constraint. Đặc biệt, nếu controller đặt `@Validated` ở **mức class**, một số phiên bản/config sẽ dùng AOP method validation qua proxy thay vì cơ chế built-in của Spring MVC 6.1+, dẫn đến exception khác (ví dụ `ConstraintViolationException`) và cách mapping HTTP khác. Khi muốn dùng cơ chế MVC 6.1+, hãy kiểm tra việc bỏ `@Validated` class-level theo tài liệu phiên bản đang chạy. Không gộp mọi lỗi validation vào một `@ExceptionHandler(MethodArgumentNotValidException.class)` rồi cho rằng đã bao phủ hết.

## 8. Ví dụ Spring Boot 3 + Java 17+ có thể chạy

Ứng dụng ví dụ phân biệt ba đường xử lý trong một controller:

- `GET /input-errors/query?age=abc`: conversion lỗi ở method argument.
- `POST /input-errors/form` với `age=abc`: binding error được giữ trong `BindingResult`.
- `POST /input-errors/form` với `age=0`: validation error (`@Min`), binder đã chuyển kiểu thành công.
- `POST /input-errors/json` với JSON không chuyển được kiểu: deserialize lỗi.
- `POST /input-errors/json` với tuổi `0`: Bean Validation lỗi.
- `GET /input-errors/method?age=0`: direct method constraint lỗi trên Spring MVC 6.1+.

Cấu trúc Maven Spring Boot 3.x, package `com.example.demo`; cần `spring-boot-starter-web` và `spring-boot-starter-validation`.

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tạo `src/main/java/com/example/demo/InputErrorController.java`:

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/input-errors")
public class InputErrorController {

    @GetMapping("/query")
    public Map<String, Integer> query(@RequestParam("age") Integer age) {
        return Map.of("age", age);
    }

    @GetMapping("/method")
    public Map<String, Integer> method(
            @RequestParam("age") @Min(1) int age) {
        return Map.of("age", age);
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("form") FormInput input,
            BindingResult binding) {

        if (binding.hasErrors()) {
            List<FieldIssue> issues = binding.getFieldErrors()
                    .stream()
                    .map(this::toIssue)
                    .toList();
            return ResponseEntity.badRequest()
                    .body(new ErrorPayload("INVALID_FORM", issues));
        }

        return ResponseEntity.ok(Map.of("status", "ACCEPTED"));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> json(
            @Valid @RequestBody JsonInput input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "CREATED"));
    }

    private FieldIssue toIssue(FieldError error) {
        // Không đưa rejectedValue hoặc thông tin nhạy cảm ra client.
        return new FieldIssue(error.getField(), error.getCode());
    }

    public record FieldIssue(String field, String code) {}
    public record ErrorPayload(String error, List<FieldIssue> fields) {}

    public static class FormInput {
        @NotBlank
        private String name;

        @NotNull
        @Min(1)
        private Integer age;

        public FormInput() {}

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public Integer getAge() { return age; }
        public void setAge(Integer age) { this.age = age; }
    }

    public record JsonInput(
            @NotBlank String name,
            @NotNull @Min(1) Integer age) {}
}
```

Giải thích code:

- `@RequestParam Integer age`: Spring chuyển String parameter thành Integer **trước khi** gọi `query`.
- `@ModelAttribute FormInput`: binder gắn các property; với `age=abc`, `FieldError` thường có `getCode() == "typeMismatch"`. Với `age=0`, lỗi validation thường có code `Min`.
- `@Valid` được áp trên object form; `BindingResult` ngay sau object cho phép tự trả JSON lỗi có cấu trúc. `ResponseEntity.badRequest()` là lựa chọn của **ứng dụng**, không phải hành vi bắt buộc khi nhận `BindingResult`.
- `@Valid @RequestBody JsonInput`: nếu Jackson đọc được body nhưng Bean Validation thất bại, chưa có `BindingResult` ngay sau nên framework xử lý thành 400.
- `@Min(1)` gắn trực tiếp lên parameter `age` ở `method` kích hoạt method validation trên Spring MVC 6.1+ với cấu hình mặc định.

Cần lưu ý `ErrorPayload` trên chỉ biểu diễn **field errors** cho demo. Sản phẩm thực nên còn hỗ trợ `getGlobalErrors()`, mã theo hợp đồng API, message được nội địa hóa và một request correlation id; không expose nguyên exception hay dữ liệu bí mật.

Chạy từ thư mục dự án Maven có wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Cổng mặc định là 8080 nếu không cấu hình khác. Lớp controller không thể biên dịch bằng lệnh `javac InputErrorController.java` độc lập vì cần Spring/Jakarta dependencies. Mã minh họa được viết để biên dịch trong dự án Boot có đúng dependency nêu trên.

## 9. Dùng curl để thấy ranh giới các lỗi

Các lệnh `curl` dưới đây chạy khi ứng dụng đã khởi động ở `http://localhost:8080`.

### 9.1. Conversion ở `@RequestParam`

```bash
curl -i "http://localhost:8080/input-errors/query?age=abc"
```

Thường nhận **400 Bad Request**, method `query` không chạy; Spring thường báo `MethodArgumentTypeMismatchException` ở phía server.

```bash
curl -i "http://localhost:8080/input-errors/query?age=20"
```

Nhận **200 OK**, body JSON chứa `"age":20`.

### 9.2. Conversion bên trong form binding

```bash
curl -i "http://localhost:8080/input-errors/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "name=Lan&age=abc"
```

Controller `form` chạy vì có `BindingResult` ngay sau `FormInput`; ví dụ trả **400** cùng JSON có ý nghĩa như:

```json
{
  "error": "INVALID_FORM",
  "fields": [
    {"field": "age", "code": "typeMismatch"}
  ]
}
```

**Ví dụ body có thể chứa thêm lỗi field khác** tùy cách validation chạy và cấu hình; test nên tìm mã `typeMismatch`, không bắt số lượng/thứ tự lỗi tuyệt đối. `age=abc` không có cách nào thành Integer; đây là conversion failure được ghi trong `BindingResult`.

### 9.3. Validation của form đã bind được

```bash
curl -i "http://localhost:8080/input-errors/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "name=Lan&age=0"
```

`age=0` chuyển kiểu **thành công**; `@Min(1)` lỗi. Ví dụ trả **400** với field code `Min`. Tương tự `name=` gây code `NotBlank`. Hai lỗi này không được gọi là `typeMismatch`.

### 9.4. JSON không deserialize được

```bash
curl -i "http://localhost:8080/input-errors/json" \
  -H "Content-Type: application/json" \
  --data '{"name":"Lan","age":"abc"}'
```

Thường **400 Bad Request**, `HttpMessageNotReadableException`, không có `FieldError` của form trong `form`. Nếu body JSON **sai cú pháp**, cùng nhánh đọc dữ liệu có thể báo lỗi trước validation.

### 9.5. JSON hợp lệ nhưng constraint sai

```bash
curl -i "http://localhost:8080/input-errors/json" \
  -H "Content-Type: application/json" \
  --data '{"name":"Lan","age":0}'
```

Thường **400 Bad Request**, `MethodArgumentNotValidException`. JSON đọc được, nhưng `@Min(1)` lỗi.

```bash
curl -i "http://localhost:8080/input-errors/json" \
  -H "Content-Type: application/json" \
  --data '{"name":"Lan","age":20}'
```

Nhận **201 Created** và JSON:

```json
{"status":"CREATED"}
```

### 9.6. Method validation

```bash
curl -i "http://localhost:8080/input-errors/method?age=0"
```

Trên Spring MVC 6.1+ với cơ chế built-in, constraint `@Min(1)` của method parameter thất bại: thường 400 với `HandlerMethodValidationException`. Nếu gửi `age=abc`, đây lại là **type conversion error**, chưa tới constraint.

Gợi ý Windows: dùng `curl.exe` một dòng khi PowerShell cũ ánh xạ `curl` thành alias; dấu `\` ở cuối dòng trong các ví dụ là cú pháp nối dòng của bash/zsh.

## 10. Kiểm thử MockMvc để nhận diện đúng loại lỗi

Đặt `src/test/java/com/example/demo/InputErrorControllerTest.java` với dependency `spring-boot-starter-test` và `spring-boot-starter-validation`. Test không giả định body lỗi Spring Boot mặc định giống nhau trên mọi phiên bản. Khi form có nhiều lỗi, dùng matcher tìm theo code thay vì phụ thuộc thứ tự.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InputErrorController.class)
class InputErrorControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryConversionFailsBeforeController() throws Exception {
        mvc.perform(get("/input-errors/query").param("age", "abc"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/input-errors/query").param("age", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.age").value(20));
    }

    @Test
    void formConversionFailureAppearsAsBindingError() throws Exception {
        mvc.perform(post("/input-errors/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Lan")
                .param("age", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("INVALID_FORM"))
            .andExpect(jsonPath("$.fields[*].code",
                    hasItem("typeMismatch")));
    }

    @Test
    void formValidationHasDifferentCode() throws Exception {
        mvc.perform(post("/input-errors/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Lan")
                .param("age", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[*].code", hasItem("Min")));
    }

    @Test
    void jsonDeserializationErrorIs400() throws Exception {
        mvc.perform(post("/input-errors/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\",\"age\":\"abc\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void jsonValidationErrorIs400() throws Exception {
        mvc.perform(post("/input-errors/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\",\"age\":0}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void directParameterConstraintRejectsZero() throws Exception {
        mvc.perform(get("/input-errors/method").param("age", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void validJsonRequestCanCreate() throws Exception {
        mvc.perform(post("/input-errors/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\",\"age\":20}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Windows: `.\mvnw.cmd test`. Đây là kiểm thử **đề xuất để chạy trong dự án mẫu có dependency phù hợp**; status có thể bị Spring Security/filter/controller advice tùy chỉnh thay đổi. Nếu ứng dụng có security bắt buộc xác thực/CSRF, cấu hình test security hoặc mock user hợp lệ trước khi diễn giải lỗi input.

Muốn kiểm chứng chính xác exception class trong một phiên bản, có thể kết hợp `andExpect(result -> ...)` trên `MvcResult.getResolvedException()` trong một test riêng, nhưng chỉ khi exception do MockMvc resolver xử lý. Với ví dụ production, nên kiểm tra **mã lỗi công khai của API** thay vì ràng buộc client vào Java class nội bộ.

## 11. Exception, status và xử lý tập trung

Các exception thường đáng nhận biết trong Spring MVC:

| Loại | Nguyên nhân điển hình | Phân loại hữu ích |
| --- | --- | --- |
| `MissingServletRequestParameterException` | Thiếu query/form parameter required | Thiếu input |
| `MethodArgumentTypeMismatchException` | `@RequestParam`/`@PathVariable` không convert được | Conversion |
| `MethodArgumentNotValidException` | Validation của `@RequestBody`, `@ModelAttribute` hoặc binding/validation argument không có `BindingResult` | Binding/argument validation |
| `HandlerMethodValidationException` | Constraint trực tiếp trên handler method parameter, Spring MVC 6.1+ | Method validation |
| `HttpMessageNotReadableException` | JSON body parse/deserialize lỗi hoặc body bắt buộc không đọc được | Message conversion |
| `HttpMediaTypeNotSupportedException` | Request `Content-Type` không được endpoint/converter hỗ trợ | HTTP content type, thường `415` |
| `BindException` / `TypeMismatchException` | Binding/conversion theo đường xử lý cụ thể, đặc biệt khi làm việc với binder riêng hoặc phiên bản khác | Xem vị trí và phiên bản |

**Không tất cả đều là 400**: `415` là vấn đề media type; lỗi phân quyền có thể là `401`/`403`; handler không tồn tại có thể là `404`. Một `ConstraintViolationException` từ service hoặc database cũng không tự động có nghĩa HTTP 400: có thể là lỗi nghiệp vụ/hệ thống, cần phân loại theo nguồn gốc.

Spring MVC có `DefaultHandlerExceptionResolver` và `ResponseEntityExceptionHandler` hỗ trợ xử lý nhiều exception mặc định. Với API REST, có thể mở rộng `ResponseEntityExceptionHandler` trong `@RestControllerAdvice` và override handler phù hợp để xuất dạng lỗi nhất quán (ví dụ `ProblemDetail` theo RFC 9457). Nhưng chữ ký override thay đổi theo phiên bản Spring; đọc đúng Javadoc release trước khi sao chép. Khi dùng `@ExceptionHandler` tùy chỉnh, phải đảm bảo không trả 200 cho input lỗi và không vô tình nuốt exception hạ tầng thành 400.

Một response lỗi hợp lý có thể chứa mã lỗi ổn định, loại lỗi, path field, thông điệp đã kiểm soát và request id; **không** đưa stack trace, tên class nội bộ, giá trị mật khẩu, access token hoặc raw SQL ra client. Dùng `MessageSource`/validation message bundles nếu ứng dụng cần nhiều ngôn ngữ. Phân biệt giữa code dùng để xử lý (như `INVALID_FIELD`) và message dành cho người dùng.

### 11.1. Đọc `BindingResult` chuẩn hơn chỉ nhìn status

```java
if (binding.hasErrors()) {
    for (org.springframework.validation.FieldError field :
            binding.getFieldErrors()) {
        String name = field.getField();
        String code = field.getCode();
        boolean conversionOrBinding = field.isBindingFailure();

        // Ghi log/định tuyến bằng name + code ở mức an toàn.
        // Không log giá trị người dùng nhập nếu có dữ liệu nhạy cảm.
    }

    for (org.springframework.validation.ObjectError global :
            binding.getGlobalErrors()) {
        String code = global.getCode();
        // Lỗi liên quan toàn object (ví dụ hai ngày không hợp lệ cùng nhau).
    }
}
```

Đây là đoạn minh họa **bên trong method đã khai báo `BindingResult binding`**, không phải một chương trình Java độc lập. `FieldError.getCode()` thường là mã ngắn (ví dụ `Min`), còn `getCodes()` cung cấp những mã cụ thể kèm object/field/type để phục vụ `MessageSource`.

## 12. Các bẫy thực tế

1. **Lỗi conversion không nhất thiết nằm ngoài binding.** Trong `@ModelAttribute`, conversion thành Integer thất bại được ghi nhận như field binding error, thường với `typeMismatch`.
2. **Không bật `@Valid` thì không nên mong constraint chạy.** Đối tượng có annotation `@Min` không tự bị từ chối trong mọi ngữ cảnh nếu không có validation được kích hoạt.
3. **Validation không sửa lỗi JSON không đọc được.** Nếu Jackson thất bại trước khi có object, `@NotBlank`/`@Min` chưa có điều kiện đánh giá.
4. **`BindingResult` nằm sai vị trí gây sai hành vi.** Đặt ngay sau argument được validation/binding tương ứng.
5. **Một field có thể có nhiều lý do lỗi.** Đừng giả định chỉ có một `FieldError` cho mỗi field hoặc thứ tự lỗi cố định.
6. **`@NotNull` khác `@NotBlank`.** Nếu muốn chặn tên toàn dấu cách, dùng `@NotBlank`; `@NotNull` chỉ chặn null.
7. **Chuỗi rỗng có thể thành null sau conversion.** Với `Integer`/`Long`, `?age=` có thể bị xem là missing sau conversion; không tự suy ra typeMismatch cho mọi empty input.
8. **Đừng nuốt lỗi conversion thành giá trị mặc định âm thầm.** Nếu client gửi `age=abc`, trả về `age=0` có thể gây lỗi nghiệp vụ kín đáo.
9. **Đừng bind JPA entity trực tiếp từ request tùy ý.** Dùng input DTO, allowlist field và phân quyền ở service; binder có thể chạm tới nested properties nếu cho phép.
10. **`required=false` không có nghĩa dữ liệu hợp lệ.** Nó chỉ thay đổi yêu cầu có/không đầu vào; giá trị có mặt vẫn phải chuyển kiểu và validation phù hợp.
11. **Các annotation thuộc đúng tầng.** `@RequestBody` dùng Jackson/message converter, `@ModelAttribute` dùng binding của Spring, constraint của Bean Validation được chạy theo ngữ cảnh; sửa một converter không nhất thiết sửa cả ba tầng.
12. **Không dùng exception class làm API contract.** Framework có thể đổi wrapper exception; contract nên dùng status, error code và cấu trúc lỗi của ứng dụng.
13. **Chú ý cơ chế method validation mới.** Nếu thêm một constraint trực tiếp lên parameter, exception có thể đổi từ `MethodArgumentNotValidException` sang `HandlerMethodValidationException` trong Spring MVC 6.1+.
14. **Dữ liệu hợp lệ về cú pháp vẫn có thể sai nghiệp vụ.** Age 20 có thể hợp lệ về chuyển kiểu và `@Min` nhưng không đủ điều kiện đăng ký một sản phẩm; business validation riêng vẫn cần thiết.

## 13. Quy trình debug một request 400

Dùng chuỗi câu hỏi thay vì đoán:

1. **Handler đã match?** Nếu chưa match, kiểm tra URL/method/content negotiation trước.
2. **Dữ liệu đến từ đâu?** Query/path/header/form → Spring argument conversion/data binder; JSON/XML body → HTTP message converter.
3. **Input có đúng syntax/kiểu không?** `abc` → Integer, JSON lỗi dấu ngoặc, ngày không đúng format đều cần xem conversion/deserialize.
4. **Object đã được tạo và property bind chưa?** Với form, xem `BindingResult.getFieldErrors()` và `getSuppressedFields()`.
5. **Validation đã chạy chưa?** Xem `@Valid`/`@Validated`, dependency và constraint, hoặc trực tiếp constraint trên method.
6. **Lỗi đến từ method validation hay argument validation?** Xem exception và vị trí annotation.
7. **Ai tạo HTTP response cuối cùng?** `@ControllerAdvice`, custom exception resolver, security filter hoặc gateway có thể thay mặc định.
8. **Nên sửa gì?** Chỉnh HTTP client khi sai kiểu dữ liệu; chỉnh DTO/converter nếu hợp đồng định dạng khác; chỉnh constraint nếu quy tắc nghiệp vụ sai; không tắt toàn bộ validation để “hết 400”.

## 14. Bài tập tự kiểm tra

**Bài 1.** `GET /input-errors/query?age=xyz` gặp lỗi gì?

**Đáp án:** Lỗi chuyển kiểu String → Integer trong argument resolver; thường `MethodArgumentTypeMismatchException` và HTTP 400. Controller không chạy.

**Bài 2.** `POST /input-errors/form` với `age=xyz` và `BindingResult` ngay sau `@ModelAttribute`?

**Đáp án:** Lỗi chuyển kiểu **bên trong binding**, được thể hiện trong `BindingResult` dưới dạng `FieldError` với code thường là `typeMismatch`. Controller có cơ hội xem lỗi và trả response.

**Bài 3.** `age=0` bind vào `Integer`, có `@Min(1)` và validation đã bật?

**Đáp án:** Chuyển kiểu thành công; validation fail. Code lỗi field thường `Min`, không phải `typeMismatch`.

**Bài 4.** JSON `{"age":"xyz"}` vào DTO `Integer age` có chắc tạo `FieldError` ở `BindingResult` không?

**Đáp án:** Không. Jackson có thể không deserialize được object và ném `HttpMessageNotReadableException` trước Bean Validation.

**Bài 5.** JSON `{"age":0}` vào `@Valid @RequestBody` với `@Min(1)`?

**Đáp án:** Deserialize được object; Bean Validation fail; mặc định thường `MethodArgumentNotValidException` và 400 (khi không có `BindingResult` ngay sau).

**Bài 6.** Vì sao handler có `@RequestParam @Min(1) int age` khi gọi `?age=0` có thể không ném `MethodArgumentNotValidException`?

**Đáp án:** Đây là constraint trực tiếp của **method parameter**; Spring MVC 6.1+ thường xử lý qua method validation và `HandlerMethodValidationException`.

**Bài 7.** `@ModelAttribute` đã áp allowed fields nhưng client gửi property ngoài danh sách; `hasErrors()` luôn thành true?

**Đáp án:** Không. Field bị chặn có thể nằm trong `BindingResult.getSuppressedFields()` mà không tạo field error; cần thiết kế kiểm tra riêng.

## Tài liệu tham khảo

- Spring Framework — Spring MVC Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — `@ModelAttribute` và `BindingResult`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — Validation, `MethodArgumentNotValidException`, `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@InitBinder` và `WebDataBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — MVC Error Responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
