# Errors, BindingResult và vị trí tham số nhận lỗi trong Spring MVC

## 1. Vấn đề cần giải quyết

Giả sử một trang đăng ký nhận dữ liệu sau:

```text
name=
age=abc
email=ada@example.com
```

Controller mong đợi `age` là số nguyên và `name` không được rỗng. Nếu thiếu cơ chế xử lý, request có thể kết thúc bằng lỗi 400 mà người dùng không biết nên sửa trường nào. Spring MVC cung cấp `Errors` và `BindingResult` để controller xem **những lỗi đã được ghi nhận khi gắn dữ liệu và kiểm tra một đối tượng request**.

Bài này tập trung vào bốn vấn đề:

1. `Errors` khác `BindingResult` ở đâu; cách đọc `FieldError`, `ObjectError`, mã lỗi, giá trị bị từ chối và tên đối tượng.
2. Vì sao tham số `Errors`/`BindingResult` phải **đứng ngay sau** `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` mà nó gắn với.
3. Khi có/không có tham số nhận lỗi, Spring gọi controller hay ném exception; phân biệt lỗi chuyển kiểu, lỗi Bean Validation, lỗi giải mã JSON và method validation.
4. Cách trả lỗi HTTP rõ ràng, trình bày lỗi ở form HTML và kiểm chứng bằng `MockMvc`.

**Bối cảnh:** Spring MVC trên Servlet stack, Spring Framework **6.x** / Spring Boot **3.x**, Java **17+**. Các ví dụ `@Valid` sử dụng `jakarta.validation.Valid` của Jakarta Bean Validation (không dùng package `javax.validation` của dự án cũ).

## 2. Từ request đến đối tượng và danh sách lỗi

Khi controller khai báo một form object:

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form,
                BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
```

*Đây là minh họa chữ ký controller trả về tên view; ví dụ REST chạy được nằm ở mục 8.*

Luồng xử lý tổng quát:

```text
Request: name="", age="abc", email="ada@example.com"
  │
  ▼
RequestMappingHandlerAdapter / method argument resolver
  │
  ├── Tạo hoặc lấy SignupForm trong model
  ├── WebDataBinder nhận các giá trị theo tên property
  │     ├── name="" → String (bind được)
  │     ├── age="abc" → Integer (chuyển kiểu THẤT BẠI)
  │     └── email="ada@example.com" → String (bind được)
  │
  ├── BindingResult ghi lỗi typeMismatch của age
  ├── @Valid yêu cầu Bean Validation
  │     └── @NotBlank trên name → lỗi NotBlank
  │
  ├── Tham số BindingResult đứng ngay sau SignupForm?
  │     ├── Có → controller có thể đọc result.hasErrors()
  │     └── Không → lỗi được xử lý theo nhánh exception thích hợp
  ▼
Controller hoặc cơ chế xử lý exception
```

**Binding lỗi** khi dữ liệu không chuyển được sang kiểu mong đợi (ví dụ `"abc"` → `Integer`). **Validation lỗi** khi dữ liệu đã được xử lý nhưng vi phạm quy tắc (ví dụ `age=15` với `@Min(18)`). Cả hai có thể được quan sát thông qua `BindingResult` đối với form object.

`@Valid` không thực hiện chuyển kiểu; nó yêu cầu chạy các constraint tương ứng sau khi đối tượng được bind/deserialized. Muốn Bean Validation hoạt động trong một project Spring Boot 3, thêm `spring-boot-starter-validation`, hoặc cung cấp Jakarta Validation provider tương đương. Chỉ có `spring-boot-starter-web` không nên được coi là đã bao gồm provider validation.

Đối với `@RequestBody` JSON, việc giải mã được thực hiện trước bởi `HttpMessageConverter` (thường Jackson), **không phải** property binding của một HTML form. Nếu JSON không thể parse hoặc giá trị không deserialize được, lỗi có thể xuất hiện **trước khi tạo đối tượng và BindingResult để controller xử lý**. `Errors` đặt sau `@RequestBody` dùng hữu ích cho lỗi validation của đối tượng đã deserialize thành công.

## 3. Errors và BindingResult: quan hệ và API

### 3.1. Quan hệ kế thừa

`Errors` và `BindingResult` là hai **interface** trong package `org.springframework.validation`:

```text
org.springframework.validation.Errors
                   ▲
                   │ extends
org.springframework.validation.BindingResult
```

`BindingResult extends Errors`. Vì vậy, object triển khai `BindingResult` cũng có đầy đủ phương thức của `Errors`.

- **`Errors`**: xem, đăng ký và tra cứu lỗi theo object hoặc field; dùng khi code chỉ cần làm việc với lỗi.
- **`BindingResult`**: bổ sung thông tin đặc thù quá trình binding như target object, raw field value, danh sách suppressed fields và cách đưa binding result vào model.

Có thể dùng `Errors` thay cho `BindingResult` khi chỉ cần `hasErrors()`, `getFieldErrors()` hoặc `rejectValue(...)`. Chọn `BindingResult` khi bạn cần `getTarget()`, `getSuppressedFields()`, `getModel()` hoặc các thông tin binding chi tiết khác.

### 3.2. Các phương thức nên nhớ

| API | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `errors.hasErrors()` | Có bất kỳ lỗi object/field nào | Quyết định xử lý tiếp hay trả lỗi |
| `errors.getErrorCount()` | Tổng số lỗi đã ghi nhận | Thống kê lỗi |
| `errors.hasFieldErrors("age")` | Có lỗi riêng của field `age` | Đánh dấu input cần sửa |
| `errors.getFieldError("age")` | Một lỗi đầu tiên của field `age`, có thể `null` | Lấy code/message của lỗi |
| `errors.getFieldErrors()` | Danh sách tất cả `FieldError` | Trả lỗi theo field |
| `errors.getGlobalErrors()` | Lỗi của object, không thuộc một field riêng | Quy tắc liên trường |
| `errors.getAllErrors()` | Gồm lỗi global và field | Xử lý chung |
| `errors.getObjectName()` | Tên object được bind, như `signup` | Biết lỗi thuộc form nào |
| `errors.reject("code")` | Đăng ký lỗi global theo mã | Quy tắc cả object |
| `errors.rejectValue("age", "code")` | Đăng ký lỗi ở một field | Validator tùy chỉnh |
| `bindingResult.getTarget()` | Object được bind, có thể `null` | Debug/kiểm tra mục tiêu |
| `bindingResult.getRawFieldValue("age")` | Giá trị raw bên dưới theo binding implementation | Debug binding |
| `bindingResult.getSuppressedFields()` | Tên các trường bị chặn trong binding | Phát hiện yêu cầu gán ngoài allowlist |
| `bindingResult.getModel()` | Map gồm object và binding result của object đó | Phục vụ model/view và binding state |

Không phải mọi lỗi đều chỉ có một `FieldError`. Một field có thể vi phạm nhiều constraint, như `@NotNull` và `@Min`, tùy tình huống. Vì thế `getFieldError("age")` lấy một lỗi nhưng `getFieldErrors("age")` có thể có nhiều lỗi.

### 3.3. FieldError và ObjectError

`FieldError` mở rộng `ObjectError`. Chúng thực thi ý tưởng hai phạm vi lỗi:

- **`FieldError`:** gắn với property cụ thể, ví dụ `age` không phải số hoặc nhỏ hơn 18. Các thông tin thường cần: `getField()`, `getRejectedValue()`, `getCode()`, `getCodes()`, `getDefaultMessage()` và `isBindingFailure()`.
- **`ObjectError` (global):** gắn với toàn bộ object, ví dụ khoảng thời gian bắt đầu phải trước kết thúc, nhưng lỗi cần xét nhiều thuộc tính. Xem `getObjectName()`, `getCode()` và `getDefaultMessage()`.

Ví dụ đoạn xử lý lỗi, dùng trong controller/validator nơi đã có `BindingResult result`:

```java
for (FieldError e : result.getFieldErrors()) {
    System.out.println(
        e.getField() + ": " + e.getCode()
        + ", rejected=" + e.getRejectedValue());
}

for (ObjectError e : result.getGlobalErrors()) {
    System.out.println(
        "object=" + e.getObjectName()
        + ", code=" + e.getCode());
}
```

*Đoạn này minh họa cách đọc lỗi; để biên dịch riêng cần import `FieldError`, `ObjectError` và biến `result` có kiểu `BindingResult`. Khi đưa vào production, **không log tùy tiện** `getRejectedValue()` vì có thể chứa dữ liệu cá nhân, token hoặc bí mật.*

### 3.4. Mã lỗi và thông điệp hiển thị

Mã lỗi như `typeMismatch`, `NotBlank`, `Min` là **khóa tra thông điệp**, không phải văn bản cuối bắt buộc phải hiển thị. `MessageCodesResolver` có thể sinh dãy mã từ chi tiết đến tổng quát. Chẳng hạn với form tên `signup`, field `age` không đổi được sang `Integer`, một số mã có thể gồm:

```text
typeMismatch.signup.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

*Các mã là ví dụ của cơ chế phân giải mặc định; kiểm tra `FieldError#getCodes()` để biết chính xác cấu hình/loại field hiện hành.*

Khi render thông điệp, dùng `MessageSource` hoặc tích hợp form rendering của Spring để tra theo locale và mã lỗi. `getDefaultMessage()` hữu ích như fallback nhưng không cam kết luôn được bản địa hóa/ổn định cho hợp đồng API. API thực tế nên tạo cấu trúc phản hồi có `field` và `code` ổn định; tránh trả nguyên exception message.

## 4. Quy tắc then chốt: đặt tham số Errors/BindingResult sát bên đối tượng nhận lỗi

Spring MVC ánh xạ `Errors`/`BindingResult` vào kết quả của **tham số request được resolve ngay trước nó**. Vì vậy, nó **phải đứng ngay sau** đối tượng `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` có binding/validation cần xử lý.

### 4.1. Đúng: BindingResult ngay sau @ModelAttribute

```java
@PostMapping("/save")
String save(@Valid @ModelAttribute("profile") ProfileForm profile,
            BindingResult errors,
            Model model) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "profile-saved";
}
```

Ở đây `BindingResult errors` nói về `profile`. Tham số `Model model` có thể đặt **sau** BindingResult, không phá cặp.

### 4.2. Sai: một tham số khác chen giữa

```java
// SAI: Model nằm giữa object cần bind và kết quả nhận lỗi.
@PostMapping("/save")
String save(@Valid @ModelAttribute("profile") ProfileForm profile,
            Model model,
            BindingResult errors) {
    return "profile-saved";
}
```

Lỗi có thể biểu hiện bằng exception về thứ tự `Errors/BindingResult` hoặc thất bại trong quá trình giải quyết argument. Không dựa vào việc “Spring sẽ dò ngược đến object đầu tiên có lỗi”. Đưa `BindingResult` sát ngay sau `profile` là cách đúng.

**Không đặt** `BindingResult` ở đầu method và không đặt sau một `@RequestParam` khác nếu nó thuộc `@ModelAttribute` trước đó. Tên biến Java là `errors` hay `bindingResult` không ảnh hưởng; **vị trí** và đối tượng liền trước mới quan trọng.

### 4.3. Hai đối tượng input: mỗi đối tượng có BindingResult riêng

```java
@PostMapping("/compose")
String compose(@Valid @ModelAttribute("shipping") ShippingForm shipping,
               BindingResult shippingErrors,
               @Valid @ModelAttribute("billing") BillingForm billing,
               BindingResult billingErrors) {
    if (shippingErrors.hasErrors() || billingErrors.hasErrors()) {
        return "compose-form";
    }
    return "composed";
}
```

*Đây là chữ ký minh họa cho controller có hai DTO và view tương ứng; không phải chương trình độc lập.* Kết quả thứ nhất thuộc `shipping`, kết quả thứ hai thuộc `billing`. Nếu gom hai `BindingResult` xuống cuối method, mapping có thể sai hoặc ném lỗi. Cặp argument theo từng object quan trọng hơn cách đặt tên biến.

### 4.4. @RequestBody và @RequestPart

Cặp đúng cho JSON đã deserialize:

```java
@PostMapping("/json")
ResponseEntity<?> json(@Valid @RequestBody CreateOrderRequest request,
                       Errors errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
```

Đối với part JSON trong multipart, có thể dùng cặp `@Valid @RequestPart("metadata") Metadata metadata, BindingResult errors` tương tự. **Lưu ý:** file part `MultipartFile` là dữ liệu upload; không đồng nhất việc validate file với Bean Validation của một DTO deserialize từ part.

Điểm khác biệt cần nhớ:

- Với `@ModelAttribute`, lỗi **binding/conversion** và lỗi validation của form object thường cùng vào `BindingResult`.
- Với `@RequestBody`/`@RequestPart`, JSON/XML được đọc bằng message converter trước. `Errors`/`BindingResult` ngay sau có thể cho bạn **lỗi Bean Validation** của object đã đọc thành công; **không** thu được mọi lỗi JSON cú pháp, thiếu request body, multipart parse hay không hỗ trợ media type.
- `@RequestParam Integer age` và `@PathVariable Long id` là trường hợp tham số đơn; lỗi chuyển kiểu của chúng thường đi qua exception resolver như `MethodArgumentTypeMismatchException`, không phải bằng cách thêm một `BindingResult` ngay sau chúng.

## 5. @Valid, @Validated và hành vi khi không có tham số nhận lỗi

### 5.1. Không có Errors/BindingResult sát bên

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form) {
    return "saved";
}
```

Nếu input vi phạm validation hoặc binding thất bại, Spring MVC mặc định không tiếp tục vào method như thể form hợp lệ. Với validation/binding của một object xử lý ở mức tham số, `MethodArgumentNotValidException` là nhánh ngoại lệ phổ biến; MVC có thể chuyển nó thành HTTP 400.

Đối với `@Valid @RequestBody SignupForm form` không có `Errors`, object JSON đã được deserialize nhưng vi phạm constraint cũng thường gây `MethodArgumentNotValidException` và mặc định HTTP 400.

**Có tham số ngay sau:**

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form,
                Errors errors) {
    if (errors.hasErrors()) {
        return "register-form";
    }
    return "saved";
}
```

Spring có thể gọi method để bạn xử lý lỗi ngay trong controller. Bản thân `@Valid` **không** tự trả HTML hoặc JSON lỗi cho bạn; controller phải dùng `hasErrors()` hoặc các API tương ứng. Không bỏ qua lỗi rồi chạy service lưu dữ liệu.

### 5.2. Không phải mọi validation đều là một tham số riêng

Từ Spring MVC **6.1**, nếu controller method có constraint trực tiếp trên method parameter, như `@Min(1) @RequestParam int page`, validation có thể áp dụng ở **mức method** thay vì mức một object. Khi đó có thể gặp `HandlerMethodValidationException`, khác với `MethodArgumentNotValidException`.

```java
@GetMapping("/search")
String search(@RequestParam @Min(1) int page) {
    return "page:" + page;
}
```

*Đoạn minh họa yêu cầu Jakarta Validation provider, import của MVC và constraint `@Min`.* Khi client gửi `page=0`, validation mức method không có một form object `@ModelAttribute` để đặt `BindingResult` thông thường. Khi thêm constraint trực tiếp trên một parameter vào một method đã có `@Valid @ModelAttribute`, quy tắc xử lý lỗi có thể đổi vì method validation bao phủ cả nested constraints.

Trong cơ chế method validation tích hợp của MVC 6.1+, controller có thể được gọi khi **mọi lỗi validation liên quan đến những tham số đã có `Errors` ngay sau chúng**. Nếu còn lỗi method parameter khác không có nơi nhận tương ứng, Spring ném `HandlerMethodValidationException`. Không giả định một `BindingResult` của form sẽ bắt mọi lỗi ở những parameter khác trong cùng method.

`@Validated` có thể dùng chọn validation groups. Nhưng class-level `@Validated` trên controller có thể kích hoạt AOP method validation; với Spring MVC 6.1+, nếu muốn dùng method validation tích hợp của MVC, tài liệu Spring khuyến nghị bỏ `@Validated` ở cấp class trong trường hợp đó. Cần kiểm tra cả cấu hình và phiên bản trước khi giải thích kết quả exception.

### 5.3. Bảng chẩn đoán

| Tình huống | Controller có nhận kết quả bằng Errors ngay sau? | Phản ứng điển hình |
| --- | --- | --- |
| `@Valid @ModelAttribute Form`, dữ liệu sai | Có | Controller chạy và kiểm tra `errors.hasErrors()` |
| `@Valid @ModelAttribute Form`, dữ liệu sai | Không | `MethodArgumentNotValidException` / 400 (nếu không có method validation khác) |
| `@Valid @RequestBody Dto`, JSON hợp lệ nhưng vi phạm constraint | Có | Controller nhận lỗi validation |
| `@Valid @RequestBody Dto`, JSON hợp lệ nhưng vi phạm constraint | Không | `MethodArgumentNotValidException` / 400 |
| `@RequestBody`, JSON sai cú pháp hoặc không deserialize được | Có hoặc không | `HttpMessageNotReadableException` / thường 400, trước khi controller chạy |
| `@RequestParam Integer age` nhận `age=abc` | Không dùng BindingResult cho param đơn | Thường `MethodArgumentTypeMismatchException` / 400 |
| Method-level `@Min(1) @RequestParam int page` | Không có result riêng cho param này | `HandlerMethodValidationException` trong cơ chế MVC tích hợp |
| Client gửi field bị cấm bởi `allowedFields` | Có `BindingResult` | Đọc `getSuppressedFields()`, có thể không xuất hiện trong `hasErrors()` |

Các trạng thái HTTP ở đây là mặc định phổ biến, có thể thay đổi qua `@ExceptionHandler`, `@ControllerAdvice`, security và cấu hình exception resolvers. Phân biệt **exception trước khi controller chạy** với **lỗi đã ghi vào BindingResult được controller xử lý**.

## 6. Lỗi theo field, lỗi global và thông điệp đưa về giao diện

### 6.1. Field errors

Ví dụ request có `age=abc`, `name=""`:

```text
objectName: signup
FieldError(field=age, code=typeMismatch, rejectedValue=abc)
FieldError(field=name, code=NotBlank, rejectedValue="")
```

*Đây là mô tả logic, không phải chuỗi `toString()` được đảm bảo nguyên văn; số lượng/mã chi tiết có thể đổi theo constraint và resolver.* `errors.hasFieldErrors("age")` trả `true`, `errors.getFieldErrors()` trả danh sách những lỗi tương ứng.

### 6.2. Global errors

Một quy tắc như “ngày bắt đầu phải trước ngày kết thúc” phụ thuộc vào **cặp** field. Validator hoặc controller có thể đăng ký lỗi toàn object:

```java
if (!startDate.isBefore(endDate)) {
    errors.reject("dateRange.invalid", "Ngày bắt đầu phải trước ngày kết thúc");
}
```

*Đoạn này là phần logic minh họa; các biến `startDate`, `endDate` phải lấy từ object request trong một validator hoặc controller.* Lỗi global xuất hiện trong `getGlobalErrors()`. Nếu muốn lỗi hiện dưới một trường nhất định, có thể dùng `rejectValue("endDate", "dateRange.invalid", "...")` khi field đó có mặt trong binding target. Phương án hiển thị thuộc về UX, còn việc kiểm tra rule nên nằm ở lớp phù hợp và được kiểm thử.

### 6.3. Dùng lại lỗi trong trang HTML

Với controller trả view (không phải `@RestController`), một `@ModelAttribute("signup")` và `BindingResult` thường được Spring đưa vào model cho render lại form. Key tương ứng của BindingResult có dạng:

```text
org.springframework.validation.BindingResult.signup
```

Đây là tiền tố `BindingResult.MODEL_KEY_PREFIX` ghép với object name `signup`. Một engine template như Thymeleaf và Spring form tags sử dụng binding state để đánh dấu input lỗi và hiển thị thông điệp.

Khi form sai, thông thường **return tên view** để giữ trạng thái form và errors trong cùng request:

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("signup") SignupForm form,
                BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "redirect:/registered";
}
```

*Đây là ví dụ chữ ký controller có view resolver; không áp vào `@RestController`.* Nếu redirect ngay khi lỗi, request mới không còn `BindingResult` cũ trừ khi chủ động dùng flash attributes theo đúng cấu trúc. Tránh redirect lỗi một cách vô tình khiến input và thông báo biến mất.

### 6.4. JSON API: trả lỗi có cấu trúc

Khi làm REST API, có thể tạo response kiểu:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    { "field": "age", "code": "typeMismatch", "message": "Tuổi phải là số" },
    { "field": "name", "code": "NotBlank", "message": "Tên không được trống" }
  ]
}
```

Schema trên là **gợi ý hợp đồng API**, không phải response mặc định của Spring Boot. Có thể tổng hợp từ `FieldError` và resolve thông điệp theo `Locale`. Đừng phát tán stack trace, SQL, chi tiết nội bộ của converter, hoặc rejected value nhạy cảm. Tránh coi `getDefaultMessage()` là mã API ổn định; frontend nên dựa trên `code`/`field` đã chuẩn hóa nếu cần tương thích lâu dài.

## 7. Ba chữ ký cần nhớ trước khi thực hành

```java
// 1. Form binding + Bean Validation: nhận lỗi ngay tại method.
@PostMapping("/form")
ResponseEntity<?> form(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {
    // ...
}

// 2. JSON deserialize thành công + Bean Validation: nhận lỗi tại method.
@PostMapping("/json")
ResponseEntity<?> json(
        @Valid @RequestBody SignupForm form,
        Errors errors) {
    // ...
}

// 3. SAI: Errors bị tách khỏi đối tượng cần validation.
@PostMapping("/wrong")
ResponseEntity<?> wrong(
        @Valid @ModelAttribute("signup") SignupForm form,
        @RequestParam(required = false) String trace,
        BindingResult errors) {
    // ...
}
```

*Đây là đoạn chữ ký minh họa, không tự biên dịch độc lập; xem ứng dụng đầy đủ ngay sau.* Trong hai chữ ký đúng, dù tên biến là `errors`, kiểu interface có thể là `Errors` hoặc `BindingResult`. Với JSON, nhớ rằng lỗi parse xảy ra ở layer khác.

## 8. Ví dụ Spring Boot 3 và Java 17 chạy được

Ứng dụng minh họa cả `@ModelAttribute`, `@RequestBody`, `Errors`, `BindingResult`, lỗi field, lỗi global và test chính xác HTTP status/body. Dùng Spring Boot **3.3.13**, JDK **17+** và Maven.

Cấu trúc:

```text
mvc-binding-errors/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── BindingErrorsApplication.java
    │   ├── SignupForm.java
    │   └── SignupController.java
    └── test/java/example/
        └── SignupControllerTest.java
```

### 8.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>mvc-binding-errors</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
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

Starter validation cung cấp Bean Validation implementation như Hibernate Validator trong môi trường Spring Boot 3. Mã import `jakarta.validation.*` và `jakarta.validation.constraints.*`.

### 8.2. File BindingErrorsApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingErrorsApplication.class, args);
    }
}
```

### 8.3. File SignupForm.java

```java
package example;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {
    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @NotBlank
    @Email
    private String email;

    public SignupForm() {}

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

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Giải thích:

- `@NotBlank` từ chối `null`, chuỗi rỗng hoặc chỉ có whitespace.
- `@NotNull` đảm bảo `age` phải có giá trị sau binding.
- `@Min(18)` áp dụng cho giá trị số đã chuyển kiểu thành công; `"abc"` là lỗi `typeMismatch` chứ không phải so sánh số nhỏ hơn 18.
- `@Email` kiểm tra chuỗi theo quy tắc email của provider; ví dụ `not-an-email` bị từ chối.

### 8.4. File SignupController.java

```java
package example;

import java.util.stream.Collectors;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/signup")
public class SignupController {

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        // Ví dụ quy tắc nghiệp vụ toàn object.
        if (!errors.hasErrors() && "admin".equalsIgnoreCase(form.getName())) {
            errors.reject("signup.nameReserved", "Tên đã được dành riêng");
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(describe(errors));
        }

        return ResponseEntity.ok(describeSuccess(form));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> json(
            @Valid @RequestBody SignupForm form,
            Errors errors) {

        // Đây là lỗi validation trên DTO JSON đã deserialize.
        // JSON sai cú pháp có thể bị từ chối trước khi method này được gọi.
        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(describe(errors));
        }

        return ResponseEntity.ok(describeSuccess(form));
    }

    private static String describe(Errors errors) {
        String fields = errors.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));

        if (!fields.isEmpty()) {
            return "invalid:" + fields;
        }

        if (errors.hasGlobalErrors()) {
            return "invalid:global";
        }

        return "invalid:unknown";
    }

    private static String describeSuccess(SignupForm form) {
        return "created:" + form.getName()
                + "|" + form.getAge()
                + "|" + form.getEmail();
    }
}
```

Vì `Errors` chứa các API `hasErrors`, `getFieldErrors` và `hasGlobalErrors` nên helper `describe(Errors)` sử dụng được cho cả `BindingResult` ở form và `Errors` ở JSON. Chỉ controller form minh họa `reject(...)` cho lỗi global; đây là ví dụ giúp hiểu API, còn hệ thống thật thường đặt rule nhiều bước vào custom `Validator` hoặc service.

Helper trong ví dụ chỉ trả **tên field** sau khi sắp xếp để đầu ra ổn định; nó không phơi `rejectedValue`. Một API production nên trả thêm mã và thông điệp an toàn, như cấu trúc ở mục 6.

### 8.5. Lệnh chạy và output có thể kiểm chứng

Ở thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Từ terminal khác, gọi bốn request form sau (trên Linux/macOS hoặc shell hỗ trợ cách nối dòng bằng `\`; với PowerShell, dùng `curl.exe` và đặt lệnh thành một dòng nếu cần):

```bash
curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Ada" \
  --data-urlencode "age=21" \
  --data-urlencode "email=ada@example.com"

curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=" \
  --data-urlencode "age=abc" \
  --data-urlencode "email=ada@example.com"

curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Ada" \
  --data-urlencode "age=15" \
  --data-urlencode "email=ada@example.com"

curl -s -X POST http://localhost:8080/signup/form \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=admin" \
  --data-urlencode "age=22" \
  --data-urlencode "email=admin@example.com"
```

Body kỳ vọng tương ứng (mỗi body không tự thêm newline):

```text
created:Ada|21|ada@example.com
invalid:age,name
invalid:age
invalid:global
```

Vì sao?

1. Form hợp lệ tạo object có `age=21` dạng số và trả HTTP **200**.
2. `name` rỗng vi phạm `NotBlank`, `age=abc` gây lỗi chuyển kiểu; cả hai được ghi vào `BindingResult` và trả **400** với hai tên field.
3. `age=15` chuyển kiểu thành công nhưng vi phạm `Min(18)`; trả **400** với field `age`.
4. `name=admin` hợp lệ theo Bean Validation nhưng controller đăng ký lỗi toàn object bằng `reject`; trả **400** `invalid:global`.

Gửi JSON hợp lệ và JSON đã parse được nhưng vi phạm email:

```bash
curl -s -X POST http://localhost:8080/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada","age":21,"email":"ada@example.com"}'

curl -s -X POST http://localhost:8080/signup/json \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada","age":21,"email":"not-an-email"}'
```

Body kỳ vọng:

```text
created:Ada|21|ada@example.com
invalid:email
```

Request JSON với `"age":"abc"` không thể deserialize thành `Integer` sẽ thường nhận HTTP **400** qua `HttpMessageNotReadableException` **trước** lời gọi `SignupController.json`. Không kỳ vọng body `invalid:age` từ helper `describe` cho lỗi đó: đây là khác biệt quan trọng giữa JSON deserialize và form property binding.

### 8.6. MockMvc test: chứng minh hành vi chứ không đoán exception

File `src/test/java/example/SignupControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Ada")
                    .param("age", "21")
                    .param("email", "ada@example.com"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "created:Ada|21|ada@example.com"));
    }

    @Test
    void bindingAndBeanValidationErrorsAreCollected() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "")
                    .param("age", "abc")
                    .param("email", "ada@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:age,name"));
    }

    @Test
    void numericConstraintIsDifferentFromConversionError() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Ada")
                    .param("age", "15")
                    .param("email", "ada@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:age"));
    }

    @Test
    void globalErrorCanBeAddedToBindingResult() throws Exception {
        mvc.perform(post("/signup/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "admin")
                    .param("age", "22")
                    .param("email", "admin@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:global"));
    }

    @Test
    void requestBodyValidationCanBeHandledLocally() throws Exception {
        mvc.perform(post("/signup/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"name\":\"Ada\",\"age\":21,"
                        + "\"email\":\"not-an-email\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("invalid:email"));
    }

    @Test
    void malformedJsonConversionFailsBeforeControllerErrors() throws Exception {
        mvc.perform(post("/signup/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"name\":\"Ada\",\"age\":\"abc\","
                        + "\"email\":\"ada@example.com\"}"))
            .andExpect(status().isBadRequest());
    }
}
```

Dùng `mvn test` chạy sáu test. Những test này kiểm tra: nhận lỗi tại controller khi có `BindingResult` sát argument, phân biệt type mismatch với constraint, object error tự thêm, Bean Validation sau deserialize JSON và JSON parse/type conversion failure ở layer message converter. Test cuối chỉ kiểm tra HTTP status vì body error mặc định tùy Spring Boot error handling, không phải chuỗi do `describe()` tạo.

Không đưa các chữ ký **cố ý sai** ở mục 4 vào project demo: chúng được trình bày để học cách xác định lỗi, không phải code ứng dụng nên triển khai.

## 9. Cách kiểm tra lỗi trong code production

Mẫu xử lý tối thiểu đúng:

```java
if (bindingResult.hasErrors()) {
    // Với form HTML: render lại view kèm input và messages.
    // Với API: chuẩn hóa FieldError/ObjectError thành body an toàn.
    return ...; // Chọn kiểu trả về phù hợp controller thực tế.
}

// Chỉ gọi service khi DTO đã qua binding/validation.
```

*Đây là pseudocode minh họa, không phải Java độc lập; dấu `...` cần thay bằng giá trị trả về hợp lệ.*

Nên tuân thủ thứ tự:

1. **Bind** dữ liệu sang DTO chuyên dụng. Tránh bind trực tiếp entity nhiều thuộc tính nhạy cảm.
2. **Validate** bằng `@Valid`/`@Validated` hoặc validator được cấu hình; với quy tắc nhiều field, ghi global/field error một cách chủ đích.
3. **Kiểm tra lỗi** trước khi gọi service. `hasErrors()` bao gồm field và global errors.
4. **Kiểm tra suppressed fields** khi đã dùng `allowedFields`: `getSuppressedFields()` là thông tin riêng trong `BindingResult`, có thể cần xử lý như request không hợp lệ ngay cả khi `hasErrors()` là false.
5. **Tạo response/view** với mã và thông điệp phù hợp; không công khai rejected values nhạy cảm và không dựa vào thứ tự tự nhiên của danh sách lỗi để làm API contract.
6. **Xử lý exception ngoài binding result** ở nơi thích hợp: JSON sai cú pháp, mismatch của tham số đơn, lỗi method-level validation, content type không phù hợp, v.v.

Với response lỗi kiểu RFC Problem Details, có thể chuẩn hóa thông qua `ProblemDetail`, `ResponseEntityExceptionHandler` và `@RestControllerAdvice`. Nếu tự viết `@ExceptionHandler` cho `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException`, hãy giữ định dạng thống nhất với errors trả từ controller; mỗi ngoại lệ có cấu trúc dữ liệu hơi khác.

## 10. Các lỗi phổ biến khi học Errors và BindingResult

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Đặt `Model` hoặc `@RequestParam` giữa form và `BindingResult` | Không gắn đúng binding result | Đặt `BindingResult` **ngay sau** form DTO |
| Hai form nhưng chỉ một `BindingResult` cuối method | Không có kết quả nhận lỗi riêng cho từng form | Ghép từng cặp object/result liền nhau |
| Chỉ gọi `@Valid` nhưng bỏ qua `errors.hasErrors()` | Có thể tiếp tục lưu DTO sai | Kiểm tra trước nghiệp vụ |
| Tưởng `Errors` và `BindingResult` là hai object hoàn toàn độc lập | Dùng API rườm rà hoặc sai | `BindingResult extends Errors`; chọn interface theo nhu cầu |
| Dùng `getFieldError("x")` rồi gọi method không kiểm tra null | `NullPointerException` khi field hợp lệ | Kiểm tra `hasFieldErrors` hoặc `null` |
| Cho rằng `getFieldErrors()` bao gồm lỗi global | Bỏ sót quy tắc liên trường | Kiểm tra thêm `getGlobalErrors()`/`getAllErrors()` |
| Tưởng `BindingResult` bắt mọi lỗi từ JSON | Bỏ sót parse failure | Xử lý riêng `HttpMessageNotReadableException` |
| Tưởng `BindingResult` bắt lỗi `@RequestParam int` sai định dạng | Đặt receiver sai vị trí | Dùng exception handling cho mismatch tham số đơn |
| Không thêm validation starter | Constraint không được thực thi như dự kiến | Cài provider Bean Validation, kiểm thử bằng MockMvc |
| Trả `getRejectedValue()` trong lỗi public | Rò rỉ dữ liệu input | Chỉ trả metadata/message đã chuẩn hóa |
| Dùng `hasErrors()` để phát hiện suppressed fields | Không thấy field bị chặn | Gọi `getSuppressedFields()` nếu có allowlist |
| Redirect ngay khi form HTML lỗi | Mất binding state/messages ở request mới | Render lại form hoặc dùng flash attributes đúng cách |
| Dựa trên thứ tự `getFieldErrors()` để kiểm thử response | Test dễ thay đổi theo provider/cấu hình | Sắp xếp và/hoặc chuẩn hóa error code |

## 11. Tình huống luyện tập

**Tình huống A.** Method:

```java
@PostMapping("/register")
String register(@Valid @ModelAttribute("form") Form form,
                @RequestParam(required = false) String campaign,
                BindingResult result) {
    // ...
}
```

Vấn đề là gì? **Đáp án:** `BindingResult` bị tách khỏi `Form` bởi `campaign`. Chuyển `BindingResult result` lên ngay sau `Form form`, sau đó mới tới `@RequestParam`.

**Tình huống B.** Form gửi `age=seventeen`, DTO có `Integer age` và `@Min(18)`. Đây là lỗi gì? **Đáp án:** conversion/type mismatch khi chuyển `String` thành `Integer`, xảy ra trước khi có thể so `Min` trên số hợp lệ.

**Tình huống C.** DTO JSON có `@Email`; JSON `{"email":"invalid"}` vẫn deserialize thành `String`. Nếu method có `@Valid @RequestBody Dto dto, Errors errors` thì sao? **Đáp án:** method có thể nhận lỗi Bean Validation qua `Errors`. Nếu thiếu `Errors`, có thể có `MethodArgumentNotValidException` mặc định.

**Tình huống D.** JSON `{"age":"not-number"}` đi vào DTO có `Integer age`. `BindingResult` ngay sau `@RequestBody` có chắc bắt được không? **Không.** Jackson có thể thất bại khi deserialize và Spring ném `HttpMessageNotReadableException` trước khi method chạy.

**Tình huống E.** Không có field error nhưng `errors.reject("dateRange")` đã chạy. `hasErrors()` trả gì? **`true`**, vì global error cũng là một lỗi. `getFieldErrors()` vẫn có thể rỗng.

**Tình huống F.** `@Min(1) @RequestParam int page` vi phạm trong Spring MVC 6.1+. Có nên thêm `BindingResult` sau `page` như một form object? **Không.** Đây là constraint mức method parameter; cần hiểu `HandlerMethodValidationException` và cơ chế xử lý method validation.

## 12. Ghi nhớ và nguồn tra cứu

- `Errors` là API làm việc với lỗi; `BindingResult extends Errors`, bổ sung thông tin quá trình binding.
- Trong chữ ký controller, **mỗi `Errors`/`BindingResult` phải đặt sát ngay sau argument mà nó nhận lỗi**.
- Form property binding và JSON HTTP message conversion là hai luồng đầu vào khác nhau; lỗi xuất hiện trước khi controller chạy không mặc nhiên chảy vào `BindingResult` của controller.
- `@Valid` yêu cầu constraint validation; `BindingResult` quyết định cách nhận lỗi tại controller trong các tình huống được hỗ trợ; controller phải kiểm tra lỗi.
- Dùng `FieldError` cho field, `ObjectError` cho object; thiết kế response ổn định, an toàn và có thể bản địa hóa.

Tài liệu chính thức để tham khảo theo phiên bản Spring Framework 6.2:

1. [Spring MVC — Supported Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html): ràng buộc vị trí `Errors`/`BindingResult` đối với đối tượng cần validation.
2. [Spring MVC — @ModelAttribute Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding và xử lý lỗi của command object.
3. [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): message converter, Bean Validation và Errors.
4. [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException`, `HandlerMethodValidationException` và method validation từ 6.1.
5. [Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html): các API `hasErrors`, `getFieldErrors`, `reject` và `rejectValue`.
6. [BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html): `getTarget`, `getSuppressedFields`, `getModel`.
