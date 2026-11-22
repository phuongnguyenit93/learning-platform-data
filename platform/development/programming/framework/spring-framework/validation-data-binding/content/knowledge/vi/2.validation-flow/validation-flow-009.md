# Chuyển mã lỗi thành thông báo theo ngôn ngữ người dùng trong Spring MVC

Khi Spring binding hoặc validation thất bại, ứng dụng nhận được **thông tin lỗi có cấu trúc** (mã lỗi, trường bị lỗi, tham số, thông báo mặc định). Người dùng cuối cần thấy câu dễ hiểu bằng ngôn ngữ họ đang sử dụng, còn API vẫn có thể giữ một mã lỗi ổn định để máy xử lý. Bước chuyển đổi này thường đi qua **`BindingResult` → `FieldError`/`ObjectError` → `MessageSource` + `Locale` → thông báo hiển thị**.

## 1. Phân biệt mã lỗi, thông báo mặc định và thông báo được địa phương hóa

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Mã lỗi (error code) | Khóa kỹ thuật để tra cứu thông báo, có thể có nhiều mã theo thứ tự ưu tiên | `NotBlank.registrationRequest.email`, `NotBlank.email`, `NotBlank` |
| Đối tượng lỗi | Giữ tên object/field, giá trị bị từ chối (nếu có), danh sách mã, arguments, default message | `FieldError`, `ObjectError` |
| `MessageSource` | Tra khóa trong các bundle như `messages_vi.properties` và `messages_en.properties` | `Vui lòng nhập email.` |
| `Locale` | Chỉ định quy ước ngôn ngữ/vùng của request | `vi-VN`, `en-US` |
| Thông báo mặc định | Phương án dự phòng nếu mã không tra được; có thể đến từ bộ kiểm tra Bean Validation | `must not be blank` |

**Điểm mấu chốt:** Không dịch bằng cách so sánh văn bản tiếng Anh, chẳng hạn `if (message.equals("must not be blank"))`. Hãy dịch dựa trên **mã lỗi**; văn bản của validator có thể thay đổi theo provider, ngôn ngữ và phiên bản.

`BindingResult` thu thập lỗi từ hai nguồn phổ biến:

- **Data binding/conversion:** dữ liệu request không chuyển được sang kiểu đích. Ví dụ form gửi `age=abc` trong khi property `age` có kiểu `Integer`; Spring tạo lỗi có mã chung `typeMismatch`.
- **Validation:** dữ liệu đã được gắn vào đối tượng nhưng vi phạm ràng buộc. Ví dụ `@NotBlank` với `email=""` hoặc `@Min(18)` với `age=16`.

`FieldError` diễn tả lỗi của một field; `ObjectError` có thể diễn tả lỗi ở cấp đối tượng, ví dụ quy tắc kiểm tra liên quan nhiều trường. Cả hai triển khai `MessageSourceResolvable` nên có thể truyền trực tiếp cho `MessageSource.getMessage(error, locale)`.

## 2. Spring tạo danh sách mã lỗi để tra cứu như thế nào?

Với lỗi `typeMismatch` ở field `age` thuộc model attribute tên `registrationForm`, `DefaultMessageCodesResolver` thường tạo chuỗi ứng viên theo thứ tự từ riêng đến chung:

1. `typeMismatch.registrationForm.age`
2. `typeMismatch.age`
3. `typeMismatch.java.lang.Integer` (phụ thuộc kiểu field thực tế)
4. `typeMismatch`

Với Bean Validation `@NotBlank` trên `email`, các ứng viên thường bắt đầu bằng `NotBlank.registrationRequest.email`, rồi đến `NotBlank.email`, `NotBlank.java.lang.String` và `NotBlank`. Tên object, tên field, kiểu field, đường dẫn lồng nhau và cấu hình resolver có thể làm danh sách thực tế khác đi. Có thể kiểm tra chính xác bằng `error.getCodes()`.

`MessageSource` thử các code theo thứ tự cho locale đã chọn. Vì vậy, một key rất cụ thể dùng để diễn đạt đúng ngữ cảnh; một key chung làm fallback cho nhiều màn hình. Ví dụ:

~~~properties
# messages_vi.properties
typeMismatch.registrationForm.age=Tuổi phải là số nguyên hợp lệ.
typeMismatch=Giá trị nhập vào có kiểu không hợp lệ.
~~~

Nếu người dùng nhập `age=abc` và lỗi có các mã trên, thông báo đầu tiên được tìm thấy sẽ là `Tuổi phải là số nguyên hợp lệ.`. Khi khóa cụ thể chưa khai báo, Spring có thể rơi xuống `typeMismatch`. Nếu không tìm thấy mã nào, overload nhận `MessageSourceResolvable` có thể dùng `defaultMessage`; nếu vẫn không có fallback, `NoSuchMessageException` có thể xuất hiện. Đừng dựa vào việc hiển thị tự động tên code cho người dùng.

## 3. Khai báo MessageSource và tài nguyên ngôn ngữ

Trong ứng dụng **Spring Boot 3.x / Spring Framework 6.x với Java 17+**, đặt các file sau trên classpath:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
~~~

`messages.properties` cũng giúp Spring Boot nhận diện basename và cung cấp thông báo mặc định. Ví dụ nội dung tối thiểu:

~~~properties
# messages.properties: fallback, dùng tiếng Anh
NotBlank=This field is required.
NotNull=A value is required.
Min=The value is below the minimum.
typeMismatch=Invalid input type.
~~~

~~~properties
# messages_vi.properties
NotBlank.registrationRequest.email=Vui lòng nhập email.
NotNull.registrationRequest.age=Vui lòng nhập tuổi.
Min.registrationRequest.age=Bạn phải từ 18 tuổi trở lên.
typeMismatch.registrationForm.age=Tuổi phải là số nguyên hợp lệ.
NotBlank=Trường này không được để trống.
typeMismatch=Giá trị nhập vào không đúng kiểu.
~~~

~~~properties
# messages_en.properties
NotBlank.registrationRequest.email=Please enter your email.
NotNull.registrationRequest.age=Please enter your age.
Min.registrationRequest.age=You must be at least 18 years old.
typeMismatch.registrationForm.age=Age must be a valid integer.
NotBlank=This field is required.
typeMismatch=Invalid input type.
~~~

Mỗi dòng `key=value` tương ứng với một mã lỗi. Khi Spring tra locale `vi-VN`, bundle tiếng Việt như `messages_vi.properties` có thể cung cấp giá trị; với `en-US`, dùng bundle tiếng Anh tương ứng. Nếu không có bản dịch cụ thể, hệ thống có thể fallback về bundle gốc hoặc cơ chế fallback đã cấu hình.

Với Spring Boot, mặc định basename là `messages`; có thể đặt rõ:

~~~properties
# application.properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
~~~

Trong dự án **Spring Framework không dùng Boot**, cần tự đăng ký bean `MessageSource`, chẳng hạn `ResourceBundleMessageSource` với basename `messages` và UTF-8. Không cần thêm bean trùng tên trong Boot khi auto-configuration đã hoạt động.

Lưu ý: **dịch thông báo từ `BindingResult` bằng `MessageSource`** và **nội suy thông báo Bean Validation** là hai khâu liên quan nhưng khác nhau. `@NotBlank(message="{some.key}")` được validator nội suy theo cấu hình Bean Validation (thường có `ValidationMessages.properties`; có thể tích hợp Spring `MessageSource`). Cách trong bài này lấy mã từ `FieldError.getCodes()` và gọi `MessageSource` khi chuẩn bị hiển thị, nhờ đó kiểm soát rõ locale của response.

## 4. Ví dụ REST API: một mã lỗi, hai ngôn ngữ

Ví dụ dưới đây là mã đặt trong một dự án Spring Boot 3 đã có `spring-boot-starter-web` và `spring-boot-starter-validation`. Các class/record có thể được đặt cùng package `com.example.demo`; đây là **mã thuộc ứng dụng Spring**, không phải chương trình độc lập chỉ cần `javac` không có dependencies.

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record RegistrationRequest(
        @NotBlank String email,
        @NotNull @Min(18) Integer age) {}

@RestController
class RegistrationController {
    @PostMapping("/registrations")
    ResponseEntity<Void> register(@Valid @RequestBody RegistrationRequest request) {
        // Xử lý đăng ký khi input hợp lệ.
        return ResponseEntity.noContent().build();
    }
}

record ValidationDetail(String field, String code, String message) {}
record ValidationResponse(String code, List<ValidationDetail> errors) {}

@RestControllerAdvice
class RegistrationValidationAdvice {
    private final MessageSource messageSource;

    RegistrationValidationAdvice(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationResponse> handle(
            MethodArgumentNotValidException exception, Locale locale) {

        List<ValidationDetail> details = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> new ValidationDetail(
                        error instanceof FieldError fieldError
                                ? fieldError.getField() : null,
                        error.getCode() == null ? "invalid" : error.getCode(),
                        messageSource.getMessage(error, locale)))
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationResponse("VALIDATION_FAILED", details));
    }
}
~~~

**Luồng xử lý của ví dụ:**

1. Spring/Jackson đọc JSON thành `RegistrationRequest`. `@Valid` kích hoạt Bean Validation.
2. Trường rỗng vi phạm `@NotBlank`; tuổi 16 vi phạm `@Min(18)`. Với đối số request body dạng này, Spring MVC phát sinh `MethodArgumentNotValidException` chứa `BindingResult`.
3. `@RestControllerAdvice` lấy `getAllErrors()` để không bỏ sót `ObjectError` cấp đối tượng. Mỗi lỗi được truyền trực tiếp cho `messageSource.getMessage(error, locale)`.
4. Spring MVC cung cấp đối số `Locale` theo cơ chế locale resolution đã cấu hình cho request. Với cấu hình thông thường dùng header, `Accept-Language: vi-VN` chọn tiếng Việt và `Accept-Language: en-US` chọn tiếng Anh.
5. Response vẫn có `VALIDATION_FAILED` và `code` kỹ thuật cho client; `message` là phần văn bản dành cho con người.

Gửi request minh họa:

~~~http
POST /registrations HTTP/1.1
Content-Type: application/json
Accept-Language: vi-VN

{"email":"","age":16}
~~~

Response dự kiến (thứ tự các lỗi có thể khác):

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "email", "code": "NotBlank", "message": "Vui lòng nhập email."},
    {"field": "age", "code": "Min", "message": "Bạn phải từ 18 tuổi trở lên."}
  ]
}
~~~

Đổi header thành `Accept-Language: en-US` thì hai thông báo tương ứng là `Please enter your email.` và `You must be at least 18 years old.`. Mã API `VALIDATION_FAILED`, mã `NotBlank`/`Min` và tên field vẫn ổn định theo ví dụ. `error.getCode()` trả một code mặc định chung; **đây không nhất thiết là code cụ thể đầu tiên** trong `error.getCodes()`. Nếu client cần định danh lỗi ổn định hơn qua nhiều endpoint, hãy thiết kế mã ứng dụng riêng và ánh xạ công khai có chủ đích.

Không giả định mọi lỗi request đều đi qua `MethodArgumentNotValidException`. Ví dụ JSON sai cú pháp hoặc không deserialize được kiểu dữ liệu thường đi qua `HttpMessageNotReadableException`; lỗi chuyển kiểu của `@RequestParam` có thể là `MethodArgumentTypeMismatchException`; method validation trong những trường hợp Spring MVC mới hơn có thể dùng `HandlerMethodValidationException`. Tùy API, cần handler riêng và cùng một chính sách locale/thông báo cho các loại lỗi đó.

## 5. Form HTML: lấy thông báo trực tiếp từ BindingResult

Với `@ModelAttribute`, Spring có thể giữ lỗi conversion/validation trong `BindingResult` để controller trả lại form thay vì ném exception. Chữ ký method nên có `BindingResult` **ngay sau** tham số model đang được validate:

~~~java
@PostMapping("/registration-form")
String submitForm(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result,
        Locale locale,
        Model model) {

    if (result.hasErrors()) {
        List<String> ageMessages = result.getFieldErrors("age").stream()
                .map(error -> messageSource.getMessage(error, locale))
                .toList();
        model.addAttribute("ageMessages", ageMessages);
        return "registration-form";
    }

    return "redirect:/registration/success";
}
~~~

Đoạn method này nằm trong controller có sẵn `MessageSource`, cùng một class `RegistrationForm` có property `age` với khả năng binding phù hợp (ví dụ getter/setter); thêm imports `@Valid`, `@ModelAttribute`, `BindingResult`, `Locale`, `Model` và `List` tương ứng. Đây là đoạn **minh họa tích hợp**, chưa phải cả controller hoặc template có thể chạy riêng.

Giả sử field `age` kiểu `Integer` nhưng người dùng gửi chuỗi `abc`, lỗi `typeMismatch` sẽ đi qua chuỗi mã ở mục 2. Gọi `messageSource.getMessage(fieldError, locale)` cho phép hiển thị thông báo thân thiện thay cho stack trace hoặc thông báo kỹ thuật về type conversion.

Với form, có thể gắn danh sách lỗi vào `Model` như trên, hoặc dùng cơ chế hiển thị lỗi của template engine và Spring MVC. Nếu cần hiển thị nhiều lỗi ở một field, giữ **danh sách** thay vì lấy duy nhất lỗi đầu tiên. Với lỗi cấp đối tượng, đọc thêm `result.getGlobalErrors()`. Template phải escape nội dung do người dùng nhập; không đưa `rejectedValue` vào thông báo theo cách lộ dữ liệu nhạy cảm.

## 6. Chọn Locale và chiến lược fallback

- Trình duyệt thường gửi `Accept-Language`, chẳng hạn `vi-VN,vi;q=0.9,en;q=0.8`. Spring MVC lấy locale qua `LocaleResolver`/cấu hình i18n, và có thể inject `Locale` vào handler. Đừng tự parse header bằng `split(",")` vì còn độ ưu tiên `q` và quy tắc khớp locale.
- Nếu ứng dụng cho phép chọn ngôn ngữ bằng tài khoản, URL hoặc session, hãy cấu hình resolver/phương án lưu lựa chọn nhất quán. Header chỉ là một nguồn lựa chọn locale, không phải chân lý duy nhất.
- Nên có bundle gốc chứa thông báo fallback an toàn. Với mã mới, thêm dịch cho các locale được hỗ trợ và kiểm tra behavior khi thiếu key. Tránh để lộ `NoSuchMessageException`, tên class, package, đường dẫn hoặc giá trị từ chối vào UI.
- Nội dung lỗi có thể nhận tham số thông qua `MessageSourceResolvable.getArguments()` và cú pháp `MessageFormat` như `{0}`, `{1}`. Muốn dùng tham số (ví dụ giới hạn số ký tự), kiểm tra thật sự các arguments của loại validator/binding đó, không mặc định chỉ số giống nhau cho mọi constraint. Với `MessageFormat`, dấu nháy đơn có quy tắc escape riêng.
- Locale ảnh hưởng **ngôn ngữ thông báo**; không nên làm thay đổi mã lỗi API, HTTP status hay điều kiện nghiệp vụ. Ngôn ngữ cũng không thay thế việc định dạng ngày, số, tiền tệ hoặc kiểm tra timezone khi cần.

## 7. Kiểm tra end-to-end và các lỗi thường gặp

Một kiểm thử đủ ý nghĩa cần chạy ứng dụng có đủ `messages*.properties`, gửi cùng payload lỗi với các locale khác nhau và so sánh cả **mã kỹ thuật** lẫn **message**:

| Tình huống | Điều mong đợi |
| --- | --- |
| `email=""`, `age=16`, header `vi-VN` | HTTP 400, key API giữ nguyên, thông báo tiếng Việt |
| Cùng payload, header `en-US` | HTTP 400, cùng trường/mã lỗi, thông báo tiếng Anh |
| `age=abc` qua **form binding** | `typeMismatch` được ánh xạ thành thông báo thân thiện, không hiện tên exception |
| Thiếu key cụ thể cho field | Resolver dùng key tổng quát hoặc fallback đã cấu hình |
| Một lỗi global và nhiều lỗi field | Response/template không bỏ sót lỗi cấp object hoặc các lỗi cùng field |
| Locale chưa hỗ trợ hoặc không có bundle tương ứng | Có fallback dễ hiểu, không phát mã nội bộ ra client |

Những vấn đề phổ biến và cách tránh:

1. **Lấy `error.getDefaultMessage()` làm thông báo cuối cùng:** chuỗi đó có thể đã được nội suy bằng ngôn ngữ khác, hoặc mang tính kỹ thuật. Hãy ưu tiên `MessageSource.getMessage(error, locale)` với key rõ ràng; dùng default message như fallback có kiểm soát.
2. **Chỉ tra `error.getCode()`:** dễ bỏ mất key cụ thể theo object/field. Truyền cả `FieldError`/`ObjectError` cho `MessageSource` để dùng toàn bộ danh sách mã theo thứ tự.
3. **Khai báo key sai tên object:** `NotBlank.registrationForm.email` sẽ không khớp key `NotBlank.registrationRequest.email`. Log có kiểm soát `getObjectName()`/`getCodes()` trong môi trường phát triển để biết key thực tế.
4. **Nhầm API validation với conversion:** `@NotBlank` không xử lý được payload JSON sai cấu trúc, và lỗi `typeMismatch` trong form có thể xuất hiện trước khi kiểm tra constraint. Mỗi loại lỗi cần tuyến xử lý phù hợp.
5. **Thiếu base bundle hoặc cấu hình locale:** Boot có thể không tạo `MessageSource` theo kỳ vọng nếu không có bundle phù hợp; resolver có thể chọn locale khác với ngôn ngữ giao diện. Kiểm tra cả cấu hình lẫn request header.
6. **Gộp lỗi vào chuỗi nối thủ công hoặc hardcode tiếng Việt trong controller:** khó thay ngôn ngữ, khó kiểm thử và không tái sử dụng được. Đặt nội dung trong bundle, controller chỉ quyết định ngữ cảnh và cấu trúc response.
7. **Trả thẳng rejected value hoặc chi tiết nội bộ:** thông báo lỗi nên đủ rõ để sửa input nhưng không làm lộ mật khẩu, token, exception, tên class hay biểu thức truy vấn.

**Nguyên tắc áp dụng:** để Spring tạo và giữ mã lỗi trong `BindingResult`, dùng `MessageSource` dịch trên **toàn bộ đối tượng lỗi** với `Locale` của request, định nghĩa thông báo theo cấp cụ thể → tổng quát trong resource bundles, rồi xuất response có mã kỹ thuật ổn định và thông báo dễ đọc.
