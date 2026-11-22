# BindingResult, validation error và tên trường

Khi Spring MVC nhận dữ liệu từ form hoặc request body, framework phải chuyển dữ liệu đầu vào thành object Java rồi kiểm tra các ràng buộc của object đó. Nếu có lỗi, `BindingResult` lưu thông tin để controller hoặc tầng xử lý lỗi có thể trả phản hồi phù hợp. Trong kiểm thử MVC, cần xác nhận lỗi gắn với đúng object, đúng trường và đúng loại lỗi; chỉ kiểm tra HTTP status thường chưa đủ.

`BindingResult` là interface thuộc `org.springframework.validation`, kế thừa `Errors`. Nó chứa các lỗi phát sinh trong quá trình bind dữ liệu và validate object. Một lỗi có thể gắn với một field cụ thể (`FieldError`) hoặc với toàn bộ object (`ObjectError`). Việc phân biệt hai loại này giúp ứng dụng hiển thị lỗi cạnh đúng input hoặc trả lỗi nghiệp vụ ở cấp biểu mẫu.

## Luồng binding và validation trong Spring MVC

Với một tham số controller được bind từ request, Spring thường thực hiện các bước:

1. Đọc dữ liệu từ query parameter, form field, path variable hoặc request body tùy annotation.
2. Chuyển đổi giá trị đầu vào sang kiểu Java và bind vào object đích.
3. Nếu tham số được đánh dấu `@Valid` hoặc `@Validated`, chạy validation tương ứng.
4. Tạo hoặc cập nhật `BindingResult` để lưu các lỗi binding và validation.
5. Nếu controller khai báo `BindingResult` hoặc `Errors` ngay sau tham số cần kiểm tra, Spring chuyển quyền xử lý lỗi cho controller. Nếu không, một số loại lỗi validation sẽ được chuyển thành exception như `MethodArgumentNotValidException`.

Ví dụ, form gửi `age=abc` cho thuộc tính kiểu `Integer` có thể tạo lỗi chuyển đổi/binding. Form gửi `age=-2` có thể bind thành công thành số nguyên nhưng vi phạm `@Min(0)`. Hai lỗi có nguồn gốc khác nhau, dù đều có thể xuất hiện trong `BindingResult`.

| Loại lỗi | Ví dụ | Thông tin thường thấy |
|---|---|---|
| Binding/conversion error | `age=abc` nhưng field là `Integer` | `FieldError` với `isBindingFailure() == true` |
| Field validation error | `age=-2` vi phạm `@Min(0)` | `FieldError` với `isBindingFailure() == false` |
| Object/global validation error | Hai trường `startDate` và `endDate` không tạo thành khoảng thời gian hợp lệ | `ObjectError`, không gắn riêng vào một field |

## Vị trí của BindingResult trong chữ ký controller

`BindingResult` hoặc `Errors` phải đứng ngay sau tham số cần nhận lỗi. Spring dùng vị trí liền kề này để xác định kết quả bind/validate thuộc về object nào.

```java
@PostMapping("/registrations")
String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "registration/form";
    }

    registrationService.register(form);
    return "redirect:/registrations/success";
}
```

Trong ví dụ, `BindingResult` đứng ngay sau `RegistrationForm`. Nếu đặt một tham số khác ở giữa, chẳng hạn:

```java
String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        Locale locale,
        BindingResult bindingResult) {
    // ...
}
```

Spring không còn xem `BindingResult` này là kết quả cho `form`; request có thể dẫn đến lỗi xử lý tham số thay vì cho controller đọc lỗi như mong đợi. Hãy đặt `BindingResult` ngay sau object được bind và validate.

`@Valid` yêu cầu Spring chạy Bean Validation trên object. Nếu bỏ `@Valid`/`@Validated`, các constraint như `@NotBlank` hoặc `@Email` không tự chạy chỉ vì controller khai báo `BindingResult`. Tuy nhiên, lỗi chuyển đổi khi bind dữ liệu vẫn có thể xuất hiện.

## FieldError và ObjectError

`BindingResult` phân biệt lỗi ở cấp field và lỗi ở cấp object:

- `FieldError` mô tả lỗi của một thuộc tính. Nó có `field`, `rejectedValue`, `bindingFailure` và thông tin message code.
- `ObjectError` mô tả lỗi của toàn bộ object, ví dụ quy tắc cần so sánh nhiều thuộc tính. `FieldError` là một loại `ObjectError` chuyên biệt.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `hasErrors()` | Có ít nhất một lỗi hay không |
| `hasFieldErrors()` | Có lỗi ở bất kỳ field nào hay không |
| `hasFieldErrors("email")` | Field được chỉ định có lỗi hay không |
| `getFieldError("email")` | Lấy lỗi đầu tiên của field đó hoặc `null` |
| `getFieldErrors("email")` | Lấy danh sách lỗi của field đó |
| `getGlobalErrors()` | Lấy lỗi không gắn với một field cụ thể |
| `getAllErrors()` | Lấy toàn bộ lỗi, gồm field và object errors |
| `getFieldValue("email")` | Lấy giá trị hiện tại/rejected value của field trong binding result |
| `rejectValue("email", "email.invalid")` | Thêm lỗi vào một field bằng message code |
| `reject("registration.date.range")` | Thêm lỗi cấp object bằng message code |

Ví dụ đọc lỗi trong controller:

```java
if (bindingResult.hasFieldErrors("email")) {
    FieldError error = bindingResult.getFieldError("email");
    String rejectedValue = String.valueOf(error.getRejectedValue());
    // Có thể ghi log hoặc xây dựng phản hồi theo chính sách ứng dụng.
}

if (!bindingResult.getGlobalErrors().isEmpty()) {
    // Hiển thị lỗi áp dụng cho toàn bộ biểu mẫu.
}
```

Không nên trả `rejectedValue` một cách mặc định cho client. Giá trị bị từ chối có thể chứa dữ liệu nhạy cảm hoặc chuỗi không an toàn để render. Chỉ đưa nó vào response khi hợp đồng API cho phép và đã xử lý việc che dữ liệu phù hợp.

## Tạo field error và global error bằng validation

Các constraint Bean Validation thông thường tạo field errors. Ví dụ:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class RegistrationForm {

    @NotBlank(message = "{registration.name.required}")
    private String name;

    @NotBlank(message = "{registration.email.required}")
    @Email(message = "{registration.email.invalid}")
    private String email;

    @Min(value = 0, message = "{registration.age.positive}")
    private Integer age;

    // Constructor, getter và setter.
}
```

Nếu cần kiểm tra quan hệ giữa nhiều field, có thể dùng class-level constraint. Ví dụ `startDate` phải đứng trước `endDate`:

```java
@ValidDateRange
public class BookingForm {

    private LocalDate startDate;
    private LocalDate endDate;

    // Getter và setter.
}
```

Validator của `@ValidDateRange` có thể báo lỗi ở cấp object bằng `ConstraintValidatorContext`, hoặc chỉ định một property node nếu ứng dụng muốn gắn lỗi vào field cụ thể. Khi class-level constraint báo lỗi thông thường, Spring đưa nó vào danh sách global errors trong `BindingResult`.

Trong controller, có thể thêm lỗi nghiệp vụ sau khi validation annotation đã chạy:

```java
if (bookingService.isUnavailable(form.getStartDate(), form.getEndDate())) {
    bindingResult.reject(
            "booking.period.unavailable",
            "The selected period is unavailable");
}
```

`reject(...)` tạo object error; `rejectValue(...)` tạo field error. Nên dùng message code ổn định để giao diện hoặc API có thể dịch thông báo thông qua `MessageSource`.

## Kiểm thử BindingResult với form và ModelAttribute

Với `@ModelAttribute`, Spring bind các request parameters vào object. Khi controller trả về view, `BindingResult` được đưa vào model cùng với object đích. Tên model attribute và tên binding result có quy ước rõ ràng: với attribute tên `registration`, binding result được lưu dưới key bắt đầu bằng `org.springframework.validation.BindingResult.registration`.

MockMvc có thể xác nhận lỗi theo tên attribute và tên field:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsFormWithFieldErrorsWhenEmailIsInvalid() throws Exception {
        mockMvc.perform(post("/registrations")
                        .param("name", "Mai")
                        .param("email", "not-an-email")
                        .param("age", "20"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "registration", "email"));
    }
}
```

`model().attributeHasFieldErrors("registration", "email")` kiểm tra rằng model attribute tên `registration` có lỗi gắn với field `email`. Matcher này kiểm tra kết quả validation/binding mà controller trả về, thay vì chỉ kiểm tra HTML có chứa một đoạn text tình cờ giống thông báo lỗi.

Các matcher liên quan gồm:

```java
andExpect(model().attributeHasErrors("registration"));
andExpect(model().attributeHasFieldErrors("registration", "email"));
andExpect(model().attributeHasNoErrors("registration"));
andExpect(model().attributeHasFieldErrorCode(
        "registration", "email", "Email"));
```

Tên attribute truyền vào matcher phải trùng với tên mà controller dùng trong `@ModelAttribute`. Nếu dùng `@ModelAttribute("form")`, hãy assert với `"form"`; đừng mặc định lấy tên class hoặc tên biến Java.

Có thể kiểm tra giá trị và kiểu của lỗi bằng cách lấy `BindingResult` từ model:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

MvcResult result = mockMvc.perform(post("/registrations")
                .param("name", "Mai")
                .param("email", "not-an-email")
                .param("age", "20"))
        .andExpect(status().isOk())
        .andReturn();

BindingResult errors = (BindingResult) result.getModelAndView()
        .getModel()
        .get(BindingResult.MODEL_KEY_PREFIX + "registration");

FieldError emailError = errors.getFieldError("email");
assertThat(emailError).isNotNull();
assertThat(emailError.getField()).isEqualTo("email");
assertThat(emailError.isBindingFailure()).isFalse();
```

Đoạn code trên cần import `MvcResult` và AssertJ. `getModelAndView()` phù hợp khi controller trả về view; với controller REST trả response body, không có `ModelAndView` để đọc theo cách này.

## Phân biệt lỗi binding và lỗi validation

Một test nên kiểm tra hai tình huống khác nhau để tránh nhầm lẫn:

**Giá trị không thể chuyển đổi:** `age=abc` không thể chuyển thành `Integer`. Spring tạo `FieldError` cho `age` và đánh dấu đó là binding failure.

```java
mockMvc.perform(post("/registrations")
                .param("name", "Mai")
                .param("email", "mai@example.test")
                .param("age", "abc"))
        .andExpect(status().isOk())
        .andExpect(model().attributeHasFieldErrors(
                "registration", "age"));
```

**Giá trị chuyển đổi được nhưng vi phạm constraint:** `age=-1` là số nguyên hợp lệ về kiểu dữ liệu nhưng vi phạm `@Min(0)`.

```java
MvcResult result = mockMvc.perform(post("/registrations")
                .param("name", "Mai")
                .param("email", "mai@example.test")
                .param("age", "-1"))
        .andExpect(status().isOk())
        .andExpect(model().attributeHasFieldErrors(
                "registration", "age"))
        .andReturn();

BindingResult errors = (BindingResult) result.getModelAndView()
        .getModel()
        .get(BindingResult.MODEL_KEY_PREFIX + "registration");

assertThat(errors.getFieldError("age").isBindingFailure()).isFalse();
```

Trong test thực tế, cần bảo đảm controller có `@Valid` để constraint chạy và `BindingResult` nằm đúng vị trí. Cả hai tình huống đều có thể trả lại form, nhưng thông báo và cách người dùng sửa lỗi khác nhau.

## Kiểm thử BindingResult với JSON request body

Với `@RequestBody`, Spring dùng `HttpMessageConverter` để đọc JSON thành object. Có thể đặt `BindingResult` ngay sau tham số `@Valid @RequestBody` để controller tự xử lý lỗi validation:

```java
@RestController
@RequestMapping("/api/registrations")
class RegistrationApiController {

    @PostMapping
    ResponseEntity<?> create(
            @Valid @RequestBody RegistrationRequest request,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            List<ApiFieldError> errors = bindingResult.getFieldErrors()
                    .stream()
                    .map(error -> new ApiFieldError(
                            error.getField(), error.getCode(),
                            error.getDefaultMessage()))
                    .toList();
            return ResponseEntity.badRequest()
                    .body(new ValidationErrorResponse(errors));
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(registrationService.create(request));
    }
}

record ApiFieldError(String field, String code, String message) {}
record ValidationErrorResponse(List<ApiFieldError> errors) {}
```

MockMvc kiểm tra status và tên field trong JSON response:

```java
mockMvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "name": "Mai",
                          "email": "invalid",
                          "age": 20
                        }
                        """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("email"));
```

Thứ tự lỗi trong danh sách không nên được xem là hợp đồng ổn định trừ khi ứng dụng chủ động sắp xếp. Nếu có nhiều field errors, hãy kiểm tra sự tồn tại theo nội dung hoặc field bằng matcher thích hợp, hoặc sắp xếp danh sách trong response trước khi assert thứ tự.

### Khi JSON không thể deserialize

Không phải mọi lỗi request body đều đi vào `BindingResult`. Nếu JSON sai cú pháp, thiếu dấu ngoặc hoặc không thể deserialize thành kiểu Java, `HttpMessageConverter` thất bại trước khi object hoàn chỉnh được chuyển cho controller. Spring thường ném `HttpMessageNotReadableException`; controller không được gọi và `BindingResult` liền kề không thể xử lý lỗi parse đó.

```java
mockMvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\": "))
        .andExpect(status().isBadRequest());
```

Hãy xử lý lỗi parse/deserialize trong `@RestControllerAdvice` hoặc cơ chế exception handling phù hợp. Đừng viết test kỳ vọng controller đọc được `BindingResult` khi request body chưa thể chuyển thành object.

## Xác nhận tên field và nested property

Tên field trong `FieldError` là property path mà Spring dùng khi bind và validate. Với object lồng nhau, tên field có thể bao gồm dấu chấm; với phần tử collection, tên field có thể chứa chỉ số hoặc khóa map.

Ví dụ DTO:

```java
class OrderForm {
    @Valid
    private CustomerForm customer;

    @Valid
    private List<OrderLineForm> lines;

    // Getter và setter.
}

class CustomerForm {
    @NotBlank
    private String email;
    // Getter và setter.
}

class OrderLineForm {
    @Min(1)
    private Integer quantity;
    // Getter và setter.
}
```

Nếu email khách hàng rỗng, lỗi thường có field path `customer.email`. Nếu quantity của dòng thứ hai không hợp lệ, field path có thể là `lines[1].quantity`.

```java
andExpect(model().attributeHasFieldErrors(
        "orderForm", "customer.email"));
```

Đối với collection, hãy dùng chỉ số theo đúng dữ liệu test đã gửi. Nếu response API công khai tên field theo quy ước khác, ví dụ `lines[1].quantity` hoặc `lines.1.quantity`, hãy xác định rõ quy ước đó trong lớp mapping lỗi của ứng dụng và assert đúng hợp đồng response.

Tên field trong lỗi là một phần quan trọng của giao diện người dùng và API. Nếu DTO đổi tên thuộc tính hoặc dùng `@JsonProperty` để đổi tên JSON, đường dẫn field trong `BindingResult` có thể khác tên key JSON bên ngoài. Đừng mặc định hai tên này luôn giống nhau; hãy kiểm tra output thực tế của ứng dụng.

## Message code và thông báo lỗi

`FieldError` và `ObjectError` chứa message codes, arguments và default message. `MessageSource` có thể phân giải message code theo locale hiện tại để trả thông báo bản địa hóa. Khi test chỉ quan tâm logic validation, nên assert field và error code thay vì phụ thuộc vào toàn bộ câu dịch:

```java
andExpect(model().attributeHasFieldErrorCode(
        "registration", "email", "Email"));
```

Khi kiểm thử hợp đồng hiển thị, hãy assert message cuối cùng bằng `content().string(...)`, `jsonPath(...)` hoặc model attribute tương ứng. Với nhiều locale, gửi locale qua MockMvc và kiểm tra nội dung đã dịch.

Thông thường Spring tạo một danh sách message codes theo nhiều mức cụ thể đến tổng quát. Ví dụ lỗi email có thể có code dựa trên tên object, field và loại lỗi trước khi fallback về code chung. Do đó, nếu test cần xác nhận code chính xác, hãy dùng matcher `attributeHasFieldErrorCode` với code được cấu hình trong ứng dụng, hoặc lấy `FieldError#getCodes()` để kiểm tra danh sách code phù hợp với mục tiêu test.

## Object-level error trong MockMvc

Lỗi toàn biểu mẫu không gắn với một field cụ thể. Với view, có thể kiểm tra `BindingResult` không có field error nhưng có global error bằng cách lấy binding result từ model:

```java
MvcResult result = mockMvc.perform(post("/bookings")
                .param("startDate", "2030-06-10")
                .param("endDate", "2030-06-01"))
        .andExpect(status().isOk())
        .andExpect(view().name("booking/form"))
        .andReturn();

BindingResult errors = (BindingResult) result.getModelAndView()
        .getModel()
        .get(BindingResult.MODEL_KEY_PREFIX + "booking");

assertThat(errors.hasErrors()).isTrue();
assertThat(errors.getFieldErrors()).isEmpty();
assertThat(errors.getGlobalErrors()).isNotEmpty();
```

Đoạn test giả định `BookingForm` có class-level validator và controller đặt tên model attribute là `booking`. Nếu validator cố ý gắn lỗi vào `endDate`, lỗi đó sẽ là `FieldError`; khi đó assertion cần thay đổi theo thiết kế validator.

Với API JSON, nên chuyển global errors thành một phần tử trong response có định danh rõ, chẳng hạn `field: null` hoặc `scope: "object"`. Đừng gán tùy tiện lỗi toàn biểu mẫu vào field đầu tiên chỉ để thuận tiện hiển thị.

## Các matcher và cách lấy kết quả cần nhớ

| Mục tiêu | Cách kiểm tra |
|---|---|
| Model attribute có lỗi | `model().attributeHasErrors("registration")` |
| Một field có lỗi | `model().attributeHasFieldErrors("registration", "email")` |
| Một field có error code cụ thể | `model().attributeHasFieldErrorCode("registration", "email", "Email")` |
| Attribute không có lỗi | `model().attributeHasNoErrors("registration")` |
| Kiểm tra response JSON có field error | `jsonPath("$.errors[0].field").value("email")` |
| Đọc toàn bộ lỗi trong controller/test | `BindingResult#getAllErrors()` |
| Chỉ đọc lỗi của field | `BindingResult#getFieldErrors("email")` |
| Phân biệt lỗi binding với validation | `FieldError#isBindingFailure()` |

Khi cần kiểm tra sâu, lấy `MvcResult` từ `.andReturn()` rồi đọc model hoặc response body. Với controller trả view, dùng `getModelAndView()`; với controller REST, đọc `getResponse().getContentAsString()` hoặc dùng JSONPath matcher trực tiếp.

## Lỗi thường gặp khi viết test

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Controller không nhận được `BindingResult` | `BindingResult` không đứng ngay sau object cần bind/validate | Đặt `BindingResult` hoặc `Errors` liền sau tham số đó |
| Không có validation error dù constraint sai | Thiếu `@Valid`/`@Validated` hoặc thiếu validation provider | Kiểm tra annotation và dependency Bean Validation |
| Matcher không tìm thấy model attribute | Tên truyền vào matcher khác `@ModelAttribute` | Dùng đúng tên attribute được khai báo trong controller |
| Field error có tên khác mong đợi | DTO dùng nested property, collection index hoặc JSON alias | Kiểm tra `FieldError#getField()` và quy ước tên field của ứng dụng |
| Giá trị `abc` gây lỗi trước khi validate | Lỗi chuyển đổi kiểu dữ liệu | Kiểm tra `FieldError#isBindingFailure()` và thông báo type mismatch |
| JSON sai cú pháp không vào controller | Message converter không deserialize được request body | Xử lý `HttpMessageNotReadableException` ở exception handler |
| Test phụ thuộc thứ tự field errors | Thứ tự lỗi có thể thay đổi theo validator hoặc cấu trúc object | Assert theo field/code, hoặc sắp xếp response một cách có chủ đích |
| Global error bị nhầm thành field error | Validator gắn sai property node hoặc test chỉ đọc `getFieldErrors()` | Kiểm tra thêm `getGlobalErrors()` và thiết kế constraint |

Một test MVC có ý nghĩa nên xác nhận cả trạng thái HTTP, nơi lỗi được lưu và tên field mà client hoặc view cần biết. Khi kiểm tra đúng `BindingResult`, `FieldError`, `ObjectError` và message code, test có thể phát hiện lỗi từ khâu chuyển đổi dữ liệu, validation annotation, quy tắc nghiệp vụ cho đến cách controller trả lỗi cho người dùng.
