# Thiết kế lỗi theo trường và lỗi toàn đối tượng trong Spring Framework

Trong một biểu mẫu hoặc REST API, dữ liệu có thể sai ở **một trường cụ thể** hoặc sai do **quan hệ giữa nhiều trường**. Hai tình huống cần được biểu diễn khác nhau:

- **Lỗi theo trường (*field error*)**: một giá trị đầu vào không đúng kiểu hoặc không thỏa constraint của trường. Ví dụ `seats=0` vi phạm `@Min(1)`, `customer=""` vi phạm `@NotBlank`, `startDate=abc` không chuyển được sang `LocalDate`.
- **Lỗi toàn đối tượng (*object-level/global error*)**: một object không hợp lệ khi xét đồng thời nhiều trường, dù từng trường có thể hợp lệ riêng lẻ. Ví dụ `endDate` phải **sau** `startDate`; một khoảng ngày từ 20/12 đến 19/12 là sai về nghiệp vụ.

Spring có các kiểu lỗi riêng: `FieldError` và `ObjectError`, được gom trong `Errors`/`BindingResult`. Khi thiết kế phản hồi lỗi JSON, cần **giữ được phân biệt này**, để frontend biết lỗi nào đặt ngay dưới input và lỗi nào nên hiển thị ở phần chung của form.

Ví dụ response được ứng dụng tự thiết kế:

~~~json
{
  "type": "https://example.org/problems/invalid-booking",
  "title": "Invalid booking request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "seats",
      "code": "Min",
      "message": "Số chỗ phải ít nhất là 1."
    }
  ],
  "objectErrors": [
    {
      "code": "booking.range.invalid",
      "message": "Ngày kết thúc phải sau ngày bắt đầu."
    }
  ],
  "suppressedFieldCount": 0
}
~~~

Đây **không phải JSON mặc định của Spring**; đó là contract đề xuất, sẽ được triển khai trong ứng dụng Spring Boot ở phần 9. Nó sử dụng một số trường quen thuộc của Problem Details và hai danh sách extension `fieldErrors`/`objectErrors`, nhưng code ví dụ trả một Java `record`, không tự khẳng định đang dùng `ProblemDetail` chuẩn RFC 9457.

Bài học thuộc chủ đề **Phản hồi lỗi** của module Spring Framework — validation/data binding; tập trung vào Spring MVC (Servlet stack), Jakarta Validation, Spring `Validator`, i18n, tính nhất quán của HTTP response và các tình huống thường gặp. Ví dụ thực hành dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x**.

## 1. Nền tảng: `ObjectError`, `FieldError` và `BindingResult`

Spring định nghĩa:

~~~java
org.springframework.validation.ObjectError
org.springframework.validation.FieldError
org.springframework.validation.Errors
org.springframework.validation.BindingResult
~~~

`FieldError` **kế thừa** `ObjectError`, nhưng mang thêm thông tin của một field. `BindingResult` mở rộng `Errors` để kết hợp kết quả data binding với validation.

| API | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `errors.hasErrors()` | Có ít nhất một field hoặc global error | Xác định request đã qua bước binding/validation chưa |
| `errors.hasFieldErrors()` | Có lỗi gắn với field | Hiển thị bên dưới input |
| `errors.hasGlobalErrors()` | Có lỗi toàn đối tượng | Hiển thị phần tổng quan của form |
| `errors.getFieldErrors()` | Danh sách `FieldError` | Tạo `fieldErrors` trong JSON |
| `errors.getGlobalErrors()` | Danh sách `ObjectError` chỉ ở cấp object | Tạo `objectErrors` trong JSON |
| `errors.getAllErrors()` | Tất cả object/field errors | Thống kê hoặc log an toàn |
| `errors.getFieldError("seats")` | Lỗi đầu tiên của field chỉ định | UI đơn giản, nhưng có thể bỏ sót các lỗi khác |
| `errors.getFieldErrors("seats")` | Tất cả lỗi của một field | Khi có nhiều constraint trên một field |
| `errors.getFieldErrorCount()` | Số **error entries** theo field | Không phải luôn là số field khác nhau |
| `errors.getGlobalErrorCount()` | Số global error entries | Số lỗi object-level |
| `errors.getObjectName()` | Tên root object đang bind | Ảnh hưởng message codes |
| `bindingResult.getSuppressedFields()` | Tên field bị binding policy chặn | Kiểm tra over-posting/mass assignment |

**Chú ý:** `getAllErrors()` trả cả `FieldError` vì `FieldError extends ObjectError`. Nếu bạn đưa **tất cả** `getAllErrors()` vào `objectErrors`, bạn đã **đếm lẫn lỗi theo trường**, khiến UI khó phân loại.

### Cấu trúc dữ liệu khái quát

~~~text
BindingResult("booking")
|
+-- FieldError(field="seats", code="Min")
|       |
|       +-- objectName = "booking"
|       +-- field = "seats"
|       +-- rejectedValue = 0 (không nên đưa ra public API)
|       +-- codes = ["Min.booking.seats", ... , "Min"]
|
+-- FieldError(field="customer", code="NotBlank")
|       |
|       +-- field = "customer"
|
+-- ObjectError(code="booking.range.invalid")
        |
        +-- objectName = "booking"
        +-- không có một field duy nhất
~~~

Đây là **một tình huống tổng hợp**, không phải mọi request đều có cả ba lỗi. Lỗi toàn đối tượng có thể do validator đặt bằng `errors.reject(...)` hoặc constraint Jakarta Validation gắn ở cấp class.

## 2. Khi nào dùng field error, khi nào dùng object error?

**Dùng field error** nếu người dùng có thể sửa một input cụ thể mà không cần xem trạng thái trường khác. Ví dụ:

- `customer` trống → `NotBlank`.
- `seats` bằng 0 → `Min`.
- `seats=abc` → `typeMismatch`.
- `contact.email` sai định dạng → `Email` hoặc custom field validator.
- `travellers[0].passportNumber` thiếu → lỗi theo field path lồng nhau.

**Dùng object error** khi invariant liên quan nhiều field hoặc chính object:

- `endDate` phải muộn hơn `startDate`.
- Chỉ được điền **một trong hai** trường `companyTaxId` và `personalId`.
- `discountAmount` không được lớn hơn `orderTotal`.
- Một trong `email` hoặc `phone` bắt buộc phải hiện diện.
- `minimumPrice` không được lớn hơn `maximumPrice`.

Quy tắc thực tiễn: **đặt lỗi theo vị trí sửa hợp lý**, không theo việc code validator tình cờ nằm ở class hay field. Một cross-field constraint có thể quyết định gắn vi phạm vào `endDate` nếu đó là UI policy được thiết kế chủ ý, nhưng khi lỗi thực sự thuộc quan hệ hai trường, một **global error** thường diễn đạt rõ hơn.

| Điều kiện | Kênh lỗi phù hợp | Vì sao |
|---|---|---|
| `seats=0`, tối thiểu 1 | Field `seats` | Input này trực tiếp vi phạm |
| `startDate=not-a-date` | Field `startDate` | Không parse được giá trị |
| `startDate=2026-12-20`, `endDate=2026-12-19` | Object `booking` | Hai ngày riêng lẻ đều đúng kiểu |
| `customer=""` | Field `customer` | Người dùng biết ngay ô cần sửa |
| Cả `email` và `phone` đều trống | Object `contactForm` | Điều kiện liên quan hai trường |
| Quy tắc quyền người dùng không cho đặt chỗ | Lỗi domain/security riêng | Không đánh đồng mọi lỗi authorization với form validation |
| Request chứa field `admin` ngoài allowlist | Binding policy/suppressed fields | **Không tự động** là một global error |

Không ép mọi lỗi miền vào Bean Validation: kiểm tra tồn kho, quyền sở hữu hoặc trạng thái giao dịch có thể cần service/domain exception và status HTTP riêng. `BindingResult` đặc biệt phù hợp lỗi đã phát hiện tại ranh giới **data binding và object validation**.

## 3. Các bước tạo lỗi trong Spring MVC

Với handler:

~~~java
@PostMapping("/preview")
public ResponseEntity<?> preview(
        @Valid @ModelAttribute("booking") BookingForm form,
        BindingResult errors) {
    // ...
}
~~~

Spring MVC thực hiện quy trình khái quát:

~~~text
HTTP request (form/query)
        |
        v
HandlerMethodArgumentResolver
        |
        v
WebDataBinder
  - tạo/nhận BookingForm
  - gắn request parameters
  - chuyển kiểu qua ConversionService
  - ghi typeMismatch / binding errors
        |
        v
Bean Validation / Spring Validator
  - @NotBlank trên customer
  - @Min(1) trên seats
  - custom rule: endDate > startDate
        |
        v
BindingResult
  +-- getFieldErrors(): field issues
  +-- getGlobalErrors(): object issues
  +-- getSuppressedFields(): rejected binding keys
        |
        v
Controller tạo HTTP response
  - 200 nếu hợp lệ và policy cho phép
  - 400 nếu lỗi input
        |
        v
Client / frontend
  - lỗi theo ô nhập
  - lỗi chung của form
~~~

**`BindingResult` phải đứng ngay sau** method argument mà nó mô tả. Nếu không có `BindingResult` tại đúng vị trí, Spring MVC có thể ném `MethodArgumentNotValidException` thay vì cho handler xử lý trực tiếp. Nếu method còn có constraint trực tiếp trên parameters, Spring MVC 6.1+ có thể dùng **`HandlerMethodValidationException`**; không suy ra loại exception chỉ từ `@Valid`.

### Phân biệt lỗi chuyển kiểu với lỗi constraint

~~~text
seats=abc
     |
     +-- Integer conversion FAILED
     |
     +-- FieldError(code="typeMismatch")
~~~

so với:

~~~text
seats=0
     |
     +-- Integer conversion SUCCESS
     |
     +-- @Min(1) FAILED
     |
     +-- FieldError(code="Min")
~~~

Hai lỗi có thể cùng nằm trong `fieldErrors` nhưng **mã gốc khác nhau**. Khi giá trị không chuyển kiểu được, không nên đổ thêm các lỗi nghiệp vụ trên một số chưa tồn tại. Validator cross-field nên bỏ qua trường hợp input liên quan đang `null`/không hợp lệ về kiểu để tránh những thông báo chồng chéo, khó sửa.

## 4. Tạo lỗi toàn đối tượng bằng Spring Validator

Spring `Validator` có hai method cốt lõi:

~~~java
boolean supports(Class<?> clazz);

void validate(Object target, Errors errors);
~~~

Để tạo lỗi **cấp object**:

~~~java
errors.reject(
    "booking.range.invalid",
    "End date must be after start date");
~~~

Còn để tạo lỗi **cấp field**:

~~~java
errors.rejectValue(
    "endDate",
    "booking.endDate.invalid",
    "End date is invalid");
~~~

Hai snippet giả định đã có biến `errors` trong `Validator.validate(...)`; không phải file Java độc lập. `reject(...)` tạo `ObjectError`. `rejectValue(...)` tạo `FieldError` (trừ những trường hợp đặc biệt với nested path trống được Spring xử lý theo hợp đồng `Errors`).

### Minh họa validator kiểm tra hai ngày

~~~java
public void validate(Object target, Errors errors) {
    BookingForm form = (BookingForm) target;

    if (form.getStartDate() == null ||
            form.getEndDate() == null) {
        return; // Lỗi thiếu ngày được @NotNull xử lý.
    }

    if (!form.getEndDate().isAfter(form.getStartDate())) {
        errors.reject(
            "booking.range.invalid",
            "End date must be after start date");
    }
}
~~~

Đoạn trên là method minh họa; class hoàn chỉnh ở phần 9. Khi start và end đều là `LocalDate` hợp lệ nhưng end không sau start, Spring ghi **một global error**. Không tự sinh `FieldError` cho cả hai ngày nếu điều đó chỉ lặp một thông báo.

**Vấn đề thứ tự:** validation chạy sau conversion/binding; nếu `startDate` không chuyển được, field error `typeMismatch` đã có. Code validator kiểm tra null để tránh báo một lỗi “end before start” không có ý nghĩa khi chưa có ngày bắt đầu.

### `@InitBinder` đăng ký validator ở scope phù hợp

Trong controller:

~~~java
@InitBinder("booking")
public void init(WebDataBinder binder) {
    binder.addValidators(new BookingDatesValidator());
}
~~~

Với model attribute được đặt tên `booking`, Spring WebDataBinder có thể chạy validator custom cùng những validators đã cấu hình, khi validation được kích hoạt bằng `@Valid` hoặc `@Validated`. Không dùng `setValidator(...)` tùy tiện để thay thế toàn bộ validator mặc định nếu bạn còn cần Jakarta Bean Validation cho `@Min`/`@NotBlank`. `addValidators(...)` có ý nghĩa **bổ sung**.

Không tự suy luận rằng mọi `@RequestBody` JSON sẽ gọi y nguyên logic của một `@ModelAttribute` form trong mọi hoàn cảnh. Handler resolver, message decoding, validation phase và loại exception cần được xác nhận theo chính web stack.

## 5. Tạo lỗi toàn đối tượng bằng Jakarta Bean Validation

Một cách khác là định nghĩa **class-level constraint**. Ví dụ annotation tùy chỉnh:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidBookingRangeValidator.class)
public @interface ValidBookingRange {
    String message() default "Invalid date range";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là **minh họa**; cần imports `java.lang.annotation.*` và `jakarta.validation.Constraint`, `Payload`. Một `ConstraintValidator<ValidBookingRange, BookingForm>` sẽ đọc hai ngày, trả `false` khi chúng không tạo thành khoảng hợp lệ.

Theo mặc định, vi phạm từ một constraint đặt ở **cấp class** có property path trỏ vào bean, nên khi Spring adapter chuyển sang `BindingResult`, nó thường được biểu diễn thành **object-level error**. Nếu trong `ConstraintValidatorContext` bạn chủ động dùng `addPropertyNode("endDate")`, violation có thể được gắn vào **field `endDate`** thay vì object.

Điểm cần nhớ:

- **Nơi gắn constraint** và **property path của violation** ảnh hưởng việc chuyển thành `FieldError` hay `ObjectError`.
- `@AssertTrue` đặt trên một getter `isRangeValid()` có thể sinh lỗi cho **property `rangeValid`**, không nhất thiết là global error như một class-level constraint.
- Một class-level constraint không thay thế việc giải thích cho frontend nên hiển thị message ở vùng nào. Hãy thiết kế API contract trước, rồi chọn kiểu violation hợp lý.
- Không đặt một validator đi truy vấn database đồng bộ hoặc một HTTP service cho mỗi lần binding nếu chỉ cần kiểm tra cấu trúc hai ngày.

Bài thực hành dùng Spring `Validator` để người học nhìn rõ sự khác nhau giữa `reject(...)` và `rejectValue(...)`, không bắt buộc tạo toàn bộ class-level annotation.

## 6. Cấu trúc JSON phản hồi lỗi nên có gì?

Một API phục vụ frontend có thể chọn cấu trúc:

~~~json
{
  "type": "https://example.org/problems/invalid-booking",
  "title": "Invalid booking request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "customer",
      "code": "NotBlank",
      "message": "Vui lòng nhập tên khách."
    },
    {
      "field": "seats",
      "code": "Min",
      "message": "Số chỗ phải ít nhất là 1."
    }
  ],
  "objectErrors": [
    {
      "code": "booking.range.invalid",
      "message": "Ngày kết thúc phải sau ngày bắt đầu."
    }
  ],
  "suppressedFieldCount": 0
}
~~~

Các trường mang trách nhiệm khác nhau:

| Trường | Ý nghĩa | Khuyến nghị |
|---|---|---|
| `type` | URI định danh loại vấn đề | Dùng URI ổn định do hệ thống định nghĩa |
| `title` | Tên loại lỗi ngắn gọn | Có thể đa ngữ nếu API contract cho phép |
| `status` | HTTP status tương ứng | Khớp status thực tế, không gắn cứng 400 cho mọi exception |
| `code` | Mã machine-readable của phản hồi | Ổn định, độc lập với câu dịch |
| `fieldErrors[]` | Lỗi có vị trí field | Cho phép một field xuất hiện nhiều lần khi vi phạm nhiều constraints |
| `objectErrors[]` | Lỗi quan hệ giữa các fields hoặc toàn object | Không tự gán một field giả |
| `field` | Đường dẫn trường Java/request DTO | Ánh xạ có kiểm soát tới tên input frontend |
| `message` | Câu đã dịch cho người đọc | Locale do request/context quyết định |
| `suppressedFieldCount` | Số field bị binding policy chặn | Có thể báo lỗi request ngoài allowlist mà không công khai input |

**`fieldErrors[]` và `objectErrors[]` nên luôn có mặt**, kể cả khi là mảng trống. Điều đó giúp frontend xử lý đồng nhất: không cần phân biệt property bị thiếu, `null` và mảng rỗng.

**Không dùng thứ tự phần tử làm định danh.** Jakarta validator có thể trả errors theo thứ tự khác nhau khi constraint set/provider thay đổi. Frontend nên đọc `field` và `code`, không giả định `fieldErrors[0]` mãi là `customer` khi một request có nhiều errors.

### Mã kỹ thuật và mã API ổn định

`FieldError.getCode()` có thể trả `Min`/`NotBlank`/`typeMismatch`. Các mã này rất hữu ích để **học cơ chế và định tuyến thông báo**. Với API công khai và client tồn tại lâu dài, bạn có thể map sang mã nghiệp vụ ổn định:

| Mã nội bộ | Mã API đề xuất | Ý nghĩa cho client |
|---|---|---|
| `NotBlank` / `NotNull` | `REQUIRED_FIELD` | Bắt buộc nhập |
| `Min` | `VALUE_BELOW_MIN` | Giá trị dưới giới hạn |
| `typeMismatch` | `INVALID_FORMAT` | Dữ liệu sai kiểu/định dạng |
| `booking.range.invalid` | `BOOKING_DATE_RANGE_INVALID` | Khoảng ngày không hợp lệ |

Mẫu thực hành sẽ giữ nguyên `getCode()` trong từng issue để dễ nhìn đường Spring; hệ thống production có thể ánh xạ sang mã công khai riêng. Tránh để frontend phụ thuộc vào tên class, constraint provider hoặc message đã dịch.

### Có nên trả rejectedValue?

`FieldError` có `getRejectedValue()`, nhưng **không bao giờ serialize nguyên cả `FieldError` từ request vào response** một cách vô điều kiện. Trường sai có thể là password, token, email, dữ liệu cá nhân hoặc một chuỗi input lớn. Chỉ trả `field`, mã và message an toàn; giới hạn nội dung log.

### Lỗi global có cần "field": null không?

Không cần. Thiết kế hai danh sách giúp type/schema rõ:

- `fieldErrors[]` có `field`.
- `objectErrors[]` không có `field`.

Như vậy UI có thể hiển thị `objectErrors` ở banner hoặc phía trên form, còn `fieldErrors` ngay dưới trường tương ứng. Nếu dùng một danh sách duy nhất, nên thêm discriminator như `scope: "FIELD" | "OBJECT"`, chứ không biến mọi global error thành một field giả.

## 7. Phản hồi lỗi chuẩn Problem Details (RFC 9457)

Spring Framework hỗ trợ `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler` cho RFC 9457. Thông thường `ProblemDetail` có các trường:

- `type` — URI định danh loại vấn đề.
- `title` — mô tả ngắn.
- `status` — HTTP status.
- `detail` — giải thích cụ thể (nếu có).
- `instance` — URI của occurrence (nếu có).

Có thể thêm extension properties như `fieldErrors` và `objectErrors`. Với Jackson trong Spring, các entries trong `ProblemDetail.properties` thường được unwrap thành top-level JSON fields.

Ví dụ **snippet minh họa** trong một method tạo response:

~~~java
ProblemDetail detail = ProblemDetail.forStatus(
    HttpStatus.BAD_REQUEST);

detail.setType(URI.create(
    "https://example.org/problems/invalid-booking"));
detail.setTitle("Invalid booking request");
detail.setDetail("One or more fields or form rules are invalid.");
detail.setProperty("code", "VALIDATION_FAILED");
detail.setProperty("fieldErrors", fieldIssues);
detail.setProperty("objectErrors", objectIssues);

return ResponseEntity.badRequest().body(detail);
~~~

Cần imports và các biến `fieldIssues`/`objectIssues` trong scope; đây không phải class độc lập. Nếu muốn trả **application/problem+json** và sử dụng đúng mô hình RFC 9457, `ProblemDetail` là lựa chọn mạnh. Mẫu runnable phần 9 cố ý trả Java record với JSON rõ ràng để người học có thể đối chiếu chính xác từng field; có thể đổi sang `ProblemDetail` trong project thật.

**Cảnh báo status:** một số lỗi business/domain có status 409, lỗi không tìm thấy có 404, lỗi authorization có 403, còn return-value method validation có thể là 500. Đừng catch mọi exception rồi trả "VALIDATION_FAILED" với HTTP 400. Ví dụ bài này trả 400 **chỉ cho input validation/binding failure** của form.

## 8. I18n: message theo locale, code ổn định

Spring cho phép biến `FieldError`/`ObjectError` thành câu đa ngữ bằng `MessageSource`:

~~~java
String translated = messageSource.getMessage(
    error, locale);
~~~

Hai loại error đều hỗ trợ `MessageSourceResolvable` với `getCodes()`, `getArguments()` và `getDefaultMessage()`. `DefaultMessageCodesResolver` tạo các ứng viên fallback, chẳng hạn:

~~~text
Min.booking.seats
Min.seats
Min.java.lang.Integer
Min
~~~

và với global error:

~~~text
booking.range.invalid.booking
booking.range.invalid
~~~

`MessageSource` thử các mã có thứ tự để tìm message hợp lệ trong `messages.properties`/`messages_vi.properties`. Không lấy `error.getDefaultMessage()` làm bằng chứng đã dùng đúng bản dịch của ứng dụng, vì default message có thể do Jakarta Validation provider nội suy sẵn.

Một request có:

~~~http
Accept-Language: vi
~~~

có thể nhận:

~~~json
{"field":"seats","code":"Min","message":"Số chỗ phải ít nhất là 1."}
~~~

Cùng lỗi với:

~~~http
Accept-Language: en
~~~

có thể nhận:

~~~json
{"field":"seats","code":"Min","message":"Seats must be at least 1."}
~~~

**Mã `Min` không đổi theo locale; câu `message` mới đổi.** Điều này cho phép frontend xử lý logic bằng code trong khi vẫn hiển thị nội dung đa ngữ.

Nếu resource bundle không có key, Spring có thể dùng default message khi có, hoặc ném `NoSuchMessageException` trong một số overload. Ứng dụng thực nên có bản dịch dự phòng an toàn, kiểm thử cả locale chính và trường hợp key bị thiếu.

## 9. Ví dụ Spring Boot 3.5 hoàn chỉnh: field error + object error

Ta xây một endpoint **xem trước đặt chỗ** (không ghi database):

- Form fields: `customer`, `seats`, `startDate`, `endDate`.
- `customer` phải không trống (`@NotBlank`).
- `seats` không được null, và tối thiểu 1 (`@NotNull`, `@Min(1)`).
- Hai ngày phải có giá trị (`@NotNull`).
- `endDate` phải **sau** `startDate` — kiểm tra bằng **Spring `Validator` cấp đối tượng**.
- Unknown/không được phép bind field bị ghi nhận trong `getSuppressedFields()`.
- Endpoint trả HTTP 200 khi hợp lệ; HTTP 400 kèm **hai danh sách tách biệt** khi sai.

Sử dụng Spring MVC Servlet, Java 17+, Spring Boot 3.5.x/Spring Framework 6.2.x. Tất cả Java files trong package `com.example.bookingerrors`. Project được tạo từ Spring Initializr có Spring Web + Validation.

### 9.1. Gradle dependencies

Trong project đã có Spring Boot Gradle plugin, repositories và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không thể biên dịch các class import Spring/Jakarta bằng JDK thuần nếu không có classpath thư viện. Chạy qua Gradle wrapper của project Spring Boot hợp lệ.

### 9.2. `BookingErrorsApplication.java`

Tệp `src/main/java/com/example/bookingerrors/BookingErrorsApplication.java`:

~~~java
package com.example.bookingerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookingErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookingErrorsApplication.class, args);
    }
}
~~~

`@SpringBootApplication` quét package hiện tại và các package con, nên controller cùng package được tìm thấy.

### 9.3. `BookingForm.java`

Tệp `src/main/java/com/example/bookingerrors/BookingForm.java`:

~~~java
package com.example.bookingerrors;

import java.time.LocalDate;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {

    @NotBlank
    private String customer;

    @NotNull
    @Min(1)
    private Integer seats;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;

    public BookingForm() {
    }

    public String getCustomer() {
        return customer;
    }

    public void setCustomer(String customer) {
        this.customer = customer;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }

    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
    }
}
~~~

`@DateTimeFormat(ISO.DATE)` cho phép WebDataBinder chuyển chuỗi ISO như `2026-12-20` thành `LocalDate`. Nếu client gửi `20/12/2026` nhưng formatter đang chờ ISO, conversion có thể thất bại thành field error.

`Integer seats` thay vì primitive `int` cho phép phân biệt giá trị thiếu (`null`) với số 0. `@NotNull` kiểm tra thiếu, `@Min(1)` kiểm tra giá trị dưới 1 khi số hợp lệ. Những quyết định này giúp lỗi rõ nghĩa hơn.

DTO cố ý không có trường `admin`. Khi client cố gửi `admin=true`, allowed-fields policy của binder sẽ ghi suppressed field, để ta chủ động từ chối input không nằm trong contract.

### 9.4. `BookingDatesValidator.java` — tạo global error

Tệp `src/main/java/com/example/bookingerrors/BookingDatesValidator.java`:

~~~java
package com.example.bookingerrors;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class BookingDatesValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return BookingForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        // Khi không có đủ ngày, để @NotNull xử lý field lỗi.
        if (form.getStartDate() == null ||
                form.getEndDate() == null) {
            return;
        }

        if (!form.getEndDate().isAfter(form.getStartDate())) {
            errors.reject(
                "booking.range.invalid",
                "End date must be after start date");
        }
    }
}
~~~

**Vì sao dùng `reject`?** Một ngày kết thúc “đúng” chỉ có thể xác định khi biết ngày bắt đầu. Việc cả hai ngày có kiểu dữ liệu hợp lệ chưa đảm bảo cả **BookingForm** hợp lệ. `errors.reject(...)` tạo `ObjectError`; `errors.rejectValue(...)` mới tạo `FieldError` cho một field cụ thể.

Method `supports(...)` thông báo validator có thể kiểm tra `BookingForm`. Class không lưu state request, nên an toàn nếu dùng lại. Ví dụ tạo instance mới trong `@InitBinder` để đơn giản; production có thể inject một bean stateless.

**Không duplicate lỗi:** nếu ngày thiếu hoặc parse thất bại, validator không sinh thêm lỗi quan hệ ngày. `@NotNull`/binding xử lý vấn đề cụ thể trước.

### 9.5. `BookingController.java` — map sang hai danh sách JSON

Tệp `src/main/java/com/example/bookingerrors/BookingController.java`:

~~~java
package com.example.bookingerrors;

import java.util.List;
import java.util.Locale;

import jakarta.validation.Valid;

import org.springframework.context.MessageSource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final MessageSource messages;

    public BookingController(MessageSource messages) {
        this.messages = messages;
    }

    @InitBinder("booking")
    public void configureBookingBinder(WebDataBinder binder) {
        binder.setAllowedFields(
            "customer", "seats", "startDate", "endDate");
        binder.addValidators(new BookingDatesValidator());
    }

    @PostMapping(
        path = "/preview",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> preview(
            @Valid @ModelAttribute("booking") BookingForm form,
            BindingResult binding,
            Locale locale) {

        int suppressedCount =
            binding.getSuppressedFields().length;

        if (!binding.hasErrors() && suppressedCount == 0) {
            return ResponseEntity.ok(
                new PreviewAccepted("VALID"));
        }

        List<FieldIssue> fieldIssues =
            binding.getFieldErrors()
                .stream()
                .map(error -> toFieldIssue(error, locale))
                .toList();

        List<ObjectIssue> objectIssues =
            binding.getGlobalErrors()
                .stream()
                .map(error -> toObjectIssue(error, locale))
                .toList();

        ValidationProblem problem = new ValidationProblem(
            "https://example.org/problems/invalid-booking",
            "Invalid booking request",
            400,
            "VALIDATION_FAILED",
            fieldIssues,
            objectIssues,
            suppressedCount
        );

        return ResponseEntity.badRequest().body(problem);
    }

    private FieldIssue toFieldIssue(
            FieldError error, Locale locale) {

        return new FieldIssue(
            error.getField(),
            error.getCode(),
            messages.getMessage(error, locale)
        );
    }

    private ObjectIssue toObjectIssue(
            ObjectError error, Locale locale) {

        return new ObjectIssue(
            error.getCode(),
            messages.getMessage(error, locale)
        );
    }

    public record PreviewAccepted(String result) {
    }

    public record FieldIssue(
        String field,
        String code,
        String message
    ) {
    }

    public record ObjectIssue(
        String code,
        String message
    ) {
    }

    public record ValidationProblem(
        String type,
        String title,
        int status,
        String code,
        List<FieldIssue> fieldErrors,
        List<ObjectIssue> objectErrors,
        int suppressedFieldCount
    ) {
    }
}
~~~

### 9.6. Phân tích các quyết định quan trọng

1. **`@InitBinder("booking")`** giới hạn scope cho model attribute `booking`. `setAllowedFields(...)` áp allowlist cho property binding, phòng một phần rủi ro mass assignment; DTO riêng là tuyến bảo vệ chính.
2. **`binder.addValidators(...)`** bổ sung Spring validator kiểm tra hai ngày, đồng thời vẫn có thể sử dụng validator Jakarta mặc định cho những annotation trong DTO.
3. **`@Valid @ModelAttribute("booking")`** kích hoạt validation. **`BindingResult` đặt ngay sau DTO**, cho phép handler nhận kết quả và chủ động tạo JSON 400.
4. **`binding.getFieldErrors()`** chỉ dùng để tạo `fieldErrors`. Mỗi entry có `field`, mã gốc và message đã dịch; không bao gồm rejected value.
5. **`binding.getGlobalErrors()`** chỉ dùng để tạo `objectErrors`. Không tự gán global error vào một field giả.
6. **`getSuppressedFields()`** là thông tin về các key bị chặn, không mặc nhiên là Bean Validation errors. Controller vẫn trả 400 nếu client gửi field ngoài allowlist, kể cả `hasErrors() == false`.
7. **`MessageSource.getMessage(error,locale)`** dùng cùng cơ chế đa ngữ cho cả FieldError và ObjectError.
8. **`ResponseEntity<?>`** cho phép handler trả success record và error record khác nhau; trong API production có thể chuẩn hóa kiểu response/ProblemDetail riêng.
9. Ứng dụng demo không ghi database và không trả dữ liệu customer, ngay cả trong response thành công. Lỗi trên các trường có thể chứa dữ liệu nhạy cảm nên không xuất nguyên object `BindingResult`.

**Quan trọng:** một Spring `Validator` phải thực sự được gọi; chỉ tạo class `BookingDatesValidator` không đủ. Trong demo, `@InitBinder` gắn nó vào `WebDataBinder` và `@Valid` kích hoạt validation. Nếu bỏ `@Valid`, đừng mặc định custom validator vẫn chạy.

### 9.7. Message bundles và i18n

Tạo `src/main/resources/messages.properties`:

~~~properties
NotBlank.booking.customer=Customer name is required.
NotBlank.customer=This field is required.
NotBlank=Required text is missing.
NotNull.booking.seats=Number of seats is required.
NotNull.booking.startDate=Start date is required.
NotNull.booking.endDate=End date is required.
NotNull=Required value is missing.
Min.booking.seats=Seats must be at least 1.
Min.seats=Value is below the minimum.
Min=Value is too small.
typeMismatch.booking.seats=Seats must be a whole number.
typeMismatch.booking.startDate=Start date must use yyyy-MM-dd.
typeMismatch.booking.endDate=End date must use yyyy-MM-dd.
typeMismatch=Invalid value format.
booking.range.invalid.booking=End date must be after start date.
booking.range.invalid=Invalid booking date range.
~~~

Tạo `src/main/resources/messages_vi.properties` (UTF-8):

~~~properties
NotBlank.booking.customer=Vui lòng nhập tên khách.
NotBlank.customer=Trường này bắt buộc.
NotBlank=Không được để trống.
NotNull.booking.seats=Vui lòng nhập số chỗ.
NotNull.booking.startDate=Vui lòng nhập ngày bắt đầu.
NotNull.booking.endDate=Vui lòng nhập ngày kết thúc.
NotNull=Thiếu dữ liệu bắt buộc.
Min.booking.seats=Số chỗ phải ít nhất là 1.
Min.seats=Giá trị nhỏ hơn mức tối thiểu.
Min=Giá trị quá nhỏ.
typeMismatch.booking.seats=Số chỗ phải là số nguyên.
typeMismatch.booking.startDate=Ngày bắt đầu phải theo định dạng yyyy-MM-dd.
typeMismatch.booking.endDate=Ngày kết thúc phải theo định dạng yyyy-MM-dd.
typeMismatch=Giá trị sai định dạng.
booking.range.invalid.booking=Ngày kết thúc phải sau ngày bắt đầu.
booking.range.invalid=Khoảng ngày không hợp lệ.
~~~

Tạo `src/main/resources/application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

`messages.properties` là base bundle; `messages_vi.properties` chứa bản dịch tiếng Việt. `Locale` do Spring MVC resolve từ request (thông thường `Accept-Language` trong cấu hình mặc định) được truyền vào controller.

`DefaultMessageCodesResolver` tạo các mã cụ thể hơn trước. Ví dụ `Min.booking.seats` đứng trước `Min.seats` và `Min`; `booking.range.invalid.booking` đứng trước `booking.range.invalid`. Nếu có bản dịch cụ thể, nó được chọn. Với một ứng dụng đa ngữ, giữ đủ keys quan trọng cho các locales được hỗ trợ.

**Không nhầm:** `@Min(message="...")` của Jakarta Validation và `MessageSource` của Spring là hai cơ chế có thể phối hợp. Mã Spring `Min.booking.seats` giúp ứng dụng override thông báo theo model/field mà không nhét tiếng Việt cứng vào annotation.

### 9.8. Chạy và gọi HTTP bằng curl

Trong root project Spring Boot có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Với server port mặc định là 8080, request hợp lệ:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-22"
~~~

Kỳ vọng HTTP **200 OK**:

~~~json
{
  "result": "VALID"
}
~~~

Request có **một field error và một object error cùng lúc**:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=0" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-19"
~~~

Kỳ vọng HTTP **400 Bad Request** với JSON:

~~~json
{
  "type": "https://example.org/problems/invalid-booking",
  "title": "Invalid booking request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "seats",
      "code": "Min",
      "message": "Số chỗ phải ít nhất là 1."
    }
  ],
  "objectErrors": [
    {
      "code": "booking.range.invalid",
      "message": "Ngày kết thúc phải sau ngày bắt đầu."
    }
  ],
  "suppressedFieldCount": 0
}
~~~

Hai ngày vẫn parse đúng `LocalDate`, nhưng quan hệ `endDate > startDate` sai. Spring validator phát **một object error**; `@Min` trên `seats` phát **một field error**. Không xem đây là hai lần ném exception riêng: handler đọc các lỗi đã được gom trong `BindingResult`.

Nếu thay `Accept-Language: vi` bằng `en`, message tương ứng trở thành:

~~~text
Seats must be at least 1.
End date must be after start date.
~~~

Mã `Min` và `booking.range.invalid` vẫn giữ nguyên; chỉ câu text thay đổi.

Request chỉ thiếu tên khách:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "customer=" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-22"
~~~

Kỳ vọng 400 với `fieldErrors` chứa `customer`/`NotBlank`; `objectErrors` là mảng rỗng.

Request ngày sai kiểu:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=20/12/2026" \
  --data-urlencode "endDate=2026-12-22"
~~~

Kỳ vọng HTTP 400 do conversion lỗi ở `startDate`. Error code thường là `typeMismatch` và message được chọn từ `typeMismatch.booking.startDate`. Không kỳ vọng validator phạm vi ngày ném thêm global error, vì trong code validator nó bỏ qua khi một ngày không có giá trị hợp lệ.

Request cố đưa trường ngoài allowlist:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-22" \
  --data-urlencode "admin=true"
~~~

Kỳ vọng HTTP 400, `fieldErrors=[]`, `objectErrors=[]` và `suppressedFieldCount=1`. Nó là **binding policy rejection**, không phải tự nhiên xuất hiện một FieldError với mã `NotBlank` hay một ObjectError.

## 10. Kiểm thử MockMvc: hai loại lỗi thật sự tách biệt

Với `spring-boot-starter-test`, tạo file `src/test/java/com/example/bookingerrors/BookingControllerTest.java`:

~~~java
package com.example.bookingerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validRequestIsAccepted() throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-22"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("VALID"));
    }

    @Test
    void fieldErrorAndObjectErrorStaySeparate()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("customer", "Lan")
                .param("seats", "0")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-19"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.fieldErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.fieldErrors[0].field")
                .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                .value("Min"))
            .andExpect(jsonPath("$.fieldErrors[0].message")
                .value("Số chỗ phải ít nhất là 1."))
            .andExpect(jsonPath("$.objectErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.objectErrors[0].code")
                .value("booking.range.invalid"))
            .andExpect(jsonPath("$.objectErrors[0].message")
                .value("Ngày kết thúc phải sau ngày bắt đầu."));
    }

    @Test
    void onlyFieldErrorHasNoGlobalError() throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("customer", "")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.fieldErrors[0].field")
                .value("customer"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                .value("NotBlank"))
            .andExpect(jsonPath("$.objectErrors").isEmpty());
    }

    @Test
    void onlyGlobalErrorHasNoFieldError()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-20"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors").isEmpty())
            .andExpect(jsonPath("$.objectErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.objectErrors[0].message")
                .value("End date must be after start date."));
    }

    @Test
    void invalidDateIsFieldBindingError()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "not-a-date")
                .param("endDate", "2026-12-22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors").isNotEmpty());
    }

    @Test
    void unapprovedInputIsNotSilentlyAccepted()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-22")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors").isEmpty())
            .andExpect(jsonPath("$.objectErrors").isEmpty())
            .andExpect(jsonPath("$.suppressedFieldCount")
                .value(1));
    }

    @Test
    void twoFieldErrorsAndOneObjectError()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "")
                .param("seats", "0")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-19"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()")
                .value(2))
            .andExpect(jsonPath("$.objectErrors.length()")
                .value(1));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Với Spring Boot 3.5, Spring MVC, validation provider và bundles đã trình bày, **bảy tests kỳ vọng PASS**. Chúng xác nhận HTTP status, JSON, bản dịch và đặc biệt là việc **fieldErrors** và **objectErrors** không bị nhập làm một.

Các test có một loại lỗi duy nhất sẽ kiểm tra index `[0]` tương đối ổn định. Test có hai field errors chỉ kiểm tra **độ dài** để không giả định thứ tự constraint violations giữa các trường. Trong project có Spring Security/CSRF hoặc custom advice/filter, cần bổ sung cấu hình test tương ứng.

**Không chỉ gọi trực tiếp `new BookingController(...).preview(...)`**: cách đó bỏ qua WebDataBinder, conversion, `@Valid`, `@InitBinder`, locale resolution và quá trình tạo `BindingResult` của Spring MVC.

## 11. Nếu endpoint nhận JSON `@RequestBody` thì sao?

REST API thường dùng JSON thay vì form URL-encoded. Với:

~~~java
@PostMapping("/bookings")
public ResponseEntity<?> create(
        @Valid @RequestBody BookingRequest request) {
    // ...
}
~~~

nếu không có `BindingResult` ngay sau DTO, Spring MVC thường phát **`MethodArgumentNotValidException`** khi một object argument không hợp lệ. Exception này cho phép đọc `ex.getBindingResult().getFieldErrors()` và `getGlobalErrors()` tương tự ví dụ form.

Nếu cần response thống nhất cho nhiều controllers, có thể kế thừa `ResponseEntityExceptionHandler` trong `@RestControllerAdvice` rồi override:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    BindingResult result = ex.getBindingResult();

    // Duyệt result.getFieldErrors()
    // và result.getGlobalErrors()
    // để dựng response lỗi theo contract của ứng dụng.

    return handleExceptionInternal(
        ex,
        ex.getBody(),
        headers,
        status,
        request);
}
~~~

Đây là **snippet minh họa** cho một subclass `ResponseEntityExceptionHandler` với imports Spring phù hợp, **không** thuộc project runnable phía trên. `ex.getBody()` là `ProblemDetail` mặc định; để đưa field/object issue arrays vào response, cần xây hoặc bổ sung các properties tương ứng trước khi gọi `handleExceptionInternal(...)`.

**Tránh đăng ký trùng `@ExceptionHandler(MethodArgumentNotValidException.class)` trong cùng subclass `ResponseEntityExceptionHandler`** nếu base class đã map loại exception đó. Dùng override của protected handler đúng cơ chế để tránh ambiguous handler mapping.

### Khi có method validation trực tiếp

Nếu handler có constraint đặt **trực tiếp** trên `@RequestParam`/`@PathVariable` hoặc return value, Spring MVC 6.1+ có thể phát **`HandlerMethodValidationException`**. Kết quả của exception này được nhóm theo **method parameters**, không phải luôn là một `BindingResult` của một form. Cần xử lý `ParameterValidationResult` và `ParameterErrors` có liên quan, thay vì ép tất cả lỗi vào `ex.getBindingResult()`.

Một lỗi trên **return value** có thể mang HTTP 500, trong khi lỗi input có HTTP 400. Không dùng một advice catch-all biến cả hai thành 400.

### Nếu đang dùng Spring WebFlux

WebFlux `@Valid @RequestBody Mono<Dto>` thường báo `WebExchangeBindException` theo reactive flow. Nó khác với `MethodArgumentNotValidException` trên Servlet MVC. Dù có thể thiết kế JSON `fieldErrors`/`objectErrors` giống nhau ở biên API, cách lấy thông tin lỗi, loại exception và thời điểm xử lý cần phù hợp web stack.

## 12. UI hiển thị field errors và object errors

Frontend có thể xử lý response như sau (pseudocode):

~~~javascript
const fieldMessages = new Map();

for (const issue of response.fieldErrors ?? []) {
  const messages = fieldMessages.get(issue.field) ?? [];
  messages.push(issue.message);
  fieldMessages.set(issue.field, messages);
}

const formBannerMessages =
  (response.objectErrors ?? []).map(issue => issue.message);
~~~

Đây là pseudocode frontend, không phải API Spring. Ý tưởng:

- Gắn messages từ `fieldErrors` vào đúng input hoặc nhóm input tương ứng.
- Hiển thị `objectErrors` ở đầu form/toast/banner vì một field đơn lẻ không mô tả đầy đủ lỗi.
- Giữ **nhiều lỗi trên cùng field** thay vì dùng object map `field -> single string` khiến lỗi trước bị ghi đè.
- Nếu một field path là `participants[0].email`, UI cần ánh xạ tên trường server với tên trường thực tế trong form; không tự đoán index có còn phù hợp sau khi người dùng thêm/bớt rows.
- Đừng hiển thị raw `code` thay cho `message` cho người dùng cuối; code là hợp đồng máy.

Nếu UI muốn lỗi khoảng ngày xuất hiện ngay cạnh cặp date inputs, nó có thể đọc global error code `booking.range.invalid` rồi hiển thị trong **form group**, không nhất thiết phải yêu cầu backend tạo hai lỗi field trùng nhau.

### Thiết kế accessibility

Lỗi theo trường nên liên kết với input bằng `aria-describedby` hoặc cơ chế tương đương, và thông báo chung nên được đọc bởi screen reader khi submit không thành công. Không chỉ dùng màu đỏ để phân biệt lỗi. Một danh sách lỗi đầu trang có thể dẫn người dùng tới các fields tương ứng.

Lỗi global như “Ngày kết thúc phải sau ngày bắt đầu” nên nói **cần sửa điều gì**, không chỉ “Form không hợp lệ”.

## 13. Trường lồng nhau, collection và nhiều object errors

Một form có collection:

~~~text
travellers[0].email
travellers[1].passportNumber
contact.address.postalCode
~~~

có thể tạo `FieldError.getField()` theo **property path**, bao gồm index. API public cần quyết định liệu có dùng y nguyên paths này hay ánh xạ sang naming convention khác, ví dụ JSON Pointer hoặc field names đã được công bố.

**Với nested list**, một field có thể sinh nhiều errors nếu vi phạm nhiều constraints; `getFieldErrorCount()` đếm **error entries**, không phải số unique field paths. Đừng tự chuyển `List<FieldIssue>` sang `Map<String,String>` rồi làm mất những lỗi sau.

**Với object-level nested bean**, một class-level constraint trên child object có thể được biểu diễn như object/global error hoặc path liên quan nested bean tùy cách Spring adapter biểu diễn violation. Nếu frontend cần vị trí chính xác trong cây form, hãy kiểm tra property path thực tế từ `BindingResult`/validator thay vì giả định mọi `ObjectError` luôn chỉ ở root.

Đối với API lớn, có thể chuẩn hóa một thuộc tính `path` theo một chuẩn như JSON Pointer, nhưng việc này cần quy tắc mapping rõ và integration tests. Tránh để khách hàng phụ thuộc trực tiếp vào internal Java property names khi domain DTO có thể refactor.

## 14. Nhiều lỗi trên cùng một trường: chọn cách hiển thị

Một field có thể vừa `@NotBlank`, vừa `@Size(min=8)`, vừa `@Pattern(...)`. Với input rỗng, provider có thể tạo nhiều constraint violations khác nhau. Các cách thể hiện:

1. **Trả đầy đủ danh sách**: frontend chọn hiển thị tất cả hoặc một phần.
2. **Ưu tiên một lỗi** theo thứ tự do ứng dụng quyết định: ví dụ required trước, format sau.
3. **Phân nhóm theo field và rule**: giữ data đủ chi tiết để UI có thể xử lý.

Không nên dựa vào **thứ tự iteration của violations** để chọn lỗi ưu tiên. Nếu cần ưu tiên, map codes thành rank rõ ràng và unit test selection logic. Đối với một field cùng lúc thiếu và sai format, có thể cấu hình validation groups/sequence hoặc validator bỏ qua khi đầu vào trống để giảm message chồng chéo.

Một `FieldError` có thể có danh sách message codes fallback theo `DefaultMessageCodesResolver`; đó là **nhiều mã ứng viên cho một lỗi**, không phải **nhiều FieldError entries**. Phân biệt hai trục:

- **Số FieldError entries**: số lần một constraint/binding rule báo lỗi.
- **Số message codes trên mỗi FieldError**: số keys mà MessageSource có thể thử cho **cùng lỗi**.

## 15. Lỗi policy, security và rejected fields

`DataBinder.setAllowedFields(...)` giúp giới hạn writable properties cho form binding. Nếu client gửi một key ngoài allowlist, `BindingResult.getSuppressedFields()` có thể chứa key đó. **Nhưng suppressed field không tự xuất hiện trong `getFieldErrors()` hay `getGlobalErrors()`.**

Vì vậy code quan trọng là:

~~~java
int suppressed = binding.getSuppressedFields().length;

if (binding.hasErrors() || suppressed > 0) {
    // Trả một response lỗi phù hợp.
}
~~~

Nếu chỉ kiểm tra `hasErrors()`, endpoint có thể vô tình chấp nhận request chứa những keys bị chặn. Nếu business policy muốn reject thay vì ignore, kiểm tra suppressed fields là cần thiết.

Không trả toàn bộ tên rejected keys hoặc values cho client nếu chúng có thể bao gồm dữ liệu nhạy cảm, dữ liệu đầu vào quá dài hoặc các chuỗi có khả năng tạo log injection. Demo chỉ trả **số lượng**, giúp minh họa mà không tiết lộ input.

**Quan trọng hơn:** thiết kế DTO chuyên dụng không có `admin`/`ownerId`/`price` mà client không được sửa; kiểm tra authorization ở service; không trông chờ allowlist giải quyết mọi rủi ro nghiệp vụ.

## 16. Vì sao không nên serialize BindingResult trực tiếp?

`BindingResult` là dữ liệu **nội bộ của Spring**, không phải public API schema. Một số thông tin của nó có thể bao gồm:

- Target object và trạng thái binding.
- Rejected values, có thể là password, token, số tài chính hoặc thông tin cá nhân.
- Java type/property path và message arguments nội bộ.
- Details phụ thuộc phiên bản Spring/validator.
- Nhiều codes fallback không phải public machine-readable contract.

Nếu trả trực tiếp `BindingResult`, Jackson có thể serialize sâu, tiết lộ thông tin không cần thiết hoặc có vòng object không phù hợp. Nên **map thủ công sang DTO lỗi an toàn**, chỉ bao gồm những thuộc tính đã định nghĩa.

Có thể thiết kế converter:

~~~java
List<FieldIssue> mapFields(
        BindingResult result, Locale locale) {
    return result.getFieldErrors().stream()
        .map(e -> new FieldIssue(
            e.getField(),
            e.getCode(),
            messageSource.getMessage(e, locale)))
        .toList();
}
~~~

Đây là snippet minh họa có `FieldIssue` và `messageSource` trong scope. Việc xây response tại controller hay global advice tùy quy mô dự án, nhưng **mapping logic nên thống nhất** để mọi endpoint cùng cách phân biệt field/object.

## 17. Khi nào cần `@RestControllerAdvice` chung?

Với một form đơn giản, `BindingResult` ngay sau `@ModelAttribute` giúp render lại view/response ngay tại handler. Với nhiều REST controllers dùng `@RequestBody`, tạo global error mapper để nhất quán thường tốt hơn.

Một kiến trúc có thể là:

~~~text
Validation failure
    |
    +-- @ModelAttribute + BindingResult
    |       |
    |       +-- shared ErrorResponseMapper
    |
    +-- @RequestBody + MethodArgumentNotValidException
    |       |
    |       +-- @RestControllerAdvice
    |               |
    |               +-- shared ErrorResponseMapper
    |
    +-- handler method constraints
    |       |
    |       +-- HandlerMethodValidationException mapper
    |               |
    |               +-- parameter-group aware conversion
    |
    +-- service/domain exception
            |
            +-- domain-specific HTTP response/status
~~~

Phần ánh xạ lỗi từ `BindingResult` có thể tái sử dụng, nhưng **không ép** mọi exception vào cấu trúc giả định rằng chúng đều có một `BindingResult`. Khi method validation diễn ra ở cấp method, lỗi có thể nằm trong `ParameterValidationResult`/`ParameterErrors`. Với lỗi service/domain, cần mã và status riêng.

### MessageSource/ProblemDetail trong ControllerAdvice

`ResponseEntityExceptionHandler` hỗ trợ các extension points của `ErrorResponse`/`ProblemDetail`, và Spring có cơ chế i18n cho các trường `type`, `title`, `detail`. Khi đổi response thành `ProblemDetail`, có thể thêm:

~~~java
problem.setProperty("fieldErrors", fieldIssues);
problem.setProperty("objectErrors", objectIssues);
~~~

Ở đây `problem` là `ProblemDetail` đã khởi tạo, các danh sách issue đã được map. Spring Jackson module thường mở rộng properties ở top-level JSON. Đây là snippet bổ sung, không cần đưa cả một hệ thống global advice vào chương trình demo chỉ để chứng minh field/object errors.

## 18. Độ ổn định của error contract

Một contract lỗi tốt cần kiểm soát:

- **HTTP status**: phản ánh đúng lỗi client/server.
- **Mã API**: ổn định, có tài liệu.
- **Field path**: quy ước rõ cho nested fields và array indices.
- **Global/object issues**: không giấu thành field giả.
- **Thứ tự**: không dựa vào provider-dependent ordering; nếu cần, sắp xếp chủ động.
- **Đa ngữ**: code ổn định, message theo locale hoặc API trả codes để frontend tự dịch theo product policy.
- **Bảo mật**: không xuất rejected values, internal class names, stack traces.
- **Khả năng truy vết**: correlation/request id phù hợp nếu được cung cấp; không đưa token nhạy cảm vào logs.
- **Khả năng mở rộng**: cho phép nhiều errors trên cùng field và nhiều object errors.
- **Tính nhất quán**: validation, JSON decoding, type conversion và domain policies có response phù hợp nhưng không bị đánh đồng.

### HTTP 400 hay 422?

Cả **400 Bad Request** và **422 Unprocessable Content** có thể xuất hiện trong những thiết kế API khác nhau. Spring MVC validation failure mặc định thường dùng HTTP 400, nhưng một tổ chức có thể lựa chọn 422 cho semantic validation theo contract đã công bố. Quan trọng là **nhất quán, có tài liệu và test**, không tự giả định Spring chuyển mọi `@Valid` violation thành 422.

### Không bao phủ lỗi 404, 403, 500 bằng "validation"

Resource không tồn tại, không đủ quyền, timeout hay server bug khác lỗi field/object. Nếu service ném một exception vì không tìm thấy booking, đừng gắn một `FieldError` giả chỉ để reuse error response. Có thể dùng chung top-level Problem Details structure, nhưng mỗi loại có `type/code/status` phù hợp.

## 19. Những lỗi triển khai thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lỗi ngày không đúng thứ tự xuất hiện dưới cả hai fields | Validator gọi `rejectValue` lặp cho mỗi field | Dùng `reject(...)` nếu lỗi thuộc quan hệ giữa hai ngày |
| `getAllErrors()` tạo hai danh sách bị lẫn | `FieldError` kế thừa `ObjectError` | Dùng `getFieldErrors()` và `getGlobalErrors()` riêng |
| Global error không có field path | Theo thiết kế, nó thuộc toàn object | Hiển thị ở form banner/group, không tạo field giả |
| Có `@NotBlank` nhưng không báo lỗi | Thiếu validation provider hoặc `@Valid`, validator chưa được chạy | Kiểm tra starter/annotation/BindingResult |
| Custom Spring Validator không chạy | Chưa đăng ký qua `@InitBinder`/global validator | Dùng `addValidators(...)` và test qua MockMvc |
| Cross-field validator tạo lỗi khi một ngày sai kiểu | Validator không bỏ qua null/invalid input | Kiểm tra trước các giá trị và để typeMismatch xử lý |
| Message trong JSON hiện tiếng Anh dù Accept-Language vi | Không gọi MessageSource hoặc thiếu bundle | Dùng `getMessage(error,locale)`, tạo bundles vi/en |
| `getDefaultMessage()` chưa được i18n như mong muốn | Default message không phải Spring code-based localization | Resolve `MessageSourceResolvable` qua MessageSource |
| Một field có hai violations nhưng UI chỉ hiện một | Map `field -> String` ghi đè entries | Dùng array/list messages cho mỗi field |
| Tests đổi thứ tự fieldErrors làm fail | Phụ thuộc thứ tự provider | Test theo field/code hoặc ổn định thứ tự trong mapper |
| Type mismatch báo `Min` một cách sai | Gộp lỗi trước/sau type conversion | Phân biệt binding error `typeMismatch` |
| `BindingResult` không nhận lỗi tại handler | Đặt sai vị trí hoặc method validation path khác | Đặt ngay sau validated argument |
| `@RequestBody` JSON lỗi nhưng controller không chạy | Argument validation ném exception trước handler | Dùng `@RestControllerAdvice`/handler phù hợp |
| Advice luôn trả HTTP 400 cho mọi method validation | Bỏ qua return-value violation status 500 | Tôn trọng `getStatusCode()` |
| Unknown field không tạo FieldError | Nó được suppress bởi allowed-fields policy | Kiểm tra `getSuppressedFields()` |
| API phản hồi rejected password | Serialize `FieldError`/BindingResult trực tiếp | Map sang DTO an toàn, loại rejected value |
| Frontend không biết hiển thị lỗi cấp object ở đâu | Contract không có danh sách global issues | Tách `objectErrors[]`/form-level banner |
| Dùng ví dụ MVC trong WebFlux | Exception/argument resolver khác | Xác nhận web stack trước khi triển khai |

### Quy trình debug nhanh

1. Controller đang dùng `@ModelAttribute`, `@RequestBody` hay direct method constraints?
2. Input đã decode/bind thành đúng kiểu chưa, hay là `typeMismatch`?
3. Validator nào phát lỗi? `@NotBlank`/`@Min` hay Spring `Validator.reject(...)`?
4. Có `BindingResult` đúng vị trí và đã bật validation chưa?
5. `getFieldErrors()` và `getGlobalErrors()` thật sự chứa gì?
6. `getSuppressedFields()` có tên bị chặn không?
7. `MessageSource` đang sử dụng locale và message codes nào?
8. Mapper có lộ rejected values hoặc gộp hai loại lỗi không?
9. Test MockMvc/HTTP có kiểm tra status, shape và i18n không?
10. Những errors đến từ service có bị trả sai mã/status do catch-all handler không?

## 20. Bài tập tự kiểm tra

**Câu 1.** `seats=0` vi phạm `@Min(1)`. Nên là field hay object error?

Field error trên `seats`, vì người dùng có thể sửa đúng trường đó.

**Câu 2.** `startDate=2026-12-20`, `endDate=2026-12-19`, cả hai đều là ngày hợp lệ. Lỗi thuộc đâu?

Object-level/global error trên `booking`, vì quan hệ giữa hai trường sai.

**Câu 3.** `errors.reject("booking.range.invalid")` và `errors.rejectValue("endDate","booking.range.invalid")` khác nhau thế nào?

`reject` tạo global error, còn `rejectValue` tạo field error. Chọn một trong hai theo UI/domain semantics.

**Câu 4.** Tại sao `getAllErrors()` không nên dùng để dựng riêng `objectErrors`?

Vì nó bao gồm cả `FieldError`, khiến field errors bị nhầm vào global errors.

**Câu 5.** Một field có hai constraints sai; có thể có hai `FieldError` không?

Có. Đừng ép xuống map chỉ giữ một message.

**Câu 6.** `FieldError.getRejectedValue()` có nên trả cho client không?

Không mặc định. Dữ liệu có thể nhạy cảm; chỉ xuất fields/codes/messages đã chọn lọc.

**Câu 7.** Nếu client gửi `admin=true` nhưng binder dùng allowedFields chặn, `hasErrors()` có bắt buộc là true không?

Không. Phải kiểm tra `getSuppressedFields()` riêng khi policy yêu cầu reject input.

**Câu 8.** Hai request cùng `Min` nhưng locale khác nhau có cần mã kỹ thuật khác nhau không?

Không. Codes có thể giữ nguyên; `MessageSource` trả message phù hợp với locale.

**Câu 9.** Một handler `@Valid @RequestBody` không có `BindingResult` ở ngay sau và DTO sai; controller có luôn chạy không?

Không. Spring MVC có thể phát `MethodArgumentNotValidException` trước khi gọi method.

**Câu 10.** Tại sao dùng MockMvc tốt hơn gọi trực tiếp `validator.validate` để kiểm tra toàn bài?

MockMvc đi qua Spring MVC binding, conversion, `@InitBinder`, Bean Validation, locale và response rendering. Gọi validator trực tiếp chỉ kiểm tra một thành phần.

## 21. Checklist thiết kế phản hồi lỗi

- [ ] Phân biệt field error và object/global error ngay từ mô hình dữ liệu.
- [ ] Dùng `getFieldErrors()` và `getGlobalErrors()` riêng, không phân loại bằng cách đoán từ message text.
- [ ] Đặt `BindingResult` ngay sau validated argument khi handler muốn xử lý tại chỗ.
- [ ] Dùng `errors.rejectValue(...)` cho lỗi một field; `errors.reject(...)` cho invariant toàn object.
- [ ] Cross-field validator bỏ qua input thiếu/không parse được để tránh thông báo trùng.
- [ ] Xác định rõ HTTP status, type/code, field path, message, i18n policy.
- [ ] Cho phép nhiều lỗi trên cùng một field; không dựa vào thứ tự không được cam kết.
- [ ] Có mảng `fieldErrors[]` và `objectErrors[]` rõ ràng, kể cả khi rỗng.
- [ ] Kiểm tra `getSuppressedFields()` nếu dùng allowed fields.
- [ ] Không serialize BindingResult/FieldError và rejected values trực tiếp cho client.
- [ ] Dùng MessageSource cho tiếng Việt/tiếng Anh và test fallback message codes.
- [ ] Khi dùng JSON `@RequestBody`, xử lý `MethodArgumentNotValidException` đúng phạm vi.
- [ ] Khi dùng method validation, xử lý `HandlerMethodValidationException` với trạng thái phù hợp.
- [ ] Khi cần RFC 9457, cân nhắc `ProblemDetail` thay vì chỉ mô phỏng tên fields.
- [ ] Viết MockMvc tests cho success, field-only, object-only, mixed, type mismatch, locale và suppressed fields.
- [ ] Giữ business authorization và lỗi server tách khỏi lỗi dữ liệu đầu vào.

**Ghi nhớ:** **`FieldError` trả lời “trường nào sai?”**, còn **`ObjectError` trả lời “đối tượng hoặc quan hệ giữa các trường sai ở đâu?”**. Một `BindingResult` có thể chứa cả hai. Khi tạo REST error response, cần tách thành hai danh sách rõ ràng, dịch message bằng `MessageSource`, không lộ rejected values và trả HTTP status/mã lỗi nhất quán.

## Tài liệu tham khảo chính thức

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — ObjectError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework — MVC @ModelAttribute and BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Error Responses and Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
