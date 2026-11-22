# Không đưa dữ liệu nhạy cảm vào thông báo hoặc biểu thức nội suy trong Spring Validation

## 1. Mục tiêu: lỗi phải hữu ích nhưng không tiết lộ dữ liệu người dùng

Thông báo validation không chỉ xuất hiện trên màn hình. Chúng còn có thể đi qua JSON API, `BindingResult`, exception handler, log, tracing, monitoring, email thông báo lỗi, hệ thống phân tích hoặc bộ nhớ đệm. Nếu message chứa **giá trị người dùng đã nhập**, dữ liệu nhạy cảm rất dễ bị lộ ngoài nơi được phép sử dụng.

Ví dụ một endpoint nhận:

- `secret` hoặc `password`: mật khẩu/mã bí mật;
- `accessToken`: token xác thực;
- `recoveryCode`: mã khôi phục;
- `nationalId`: số định danh;
- `email`, địa chỉ, số điện thoại, thông tin cá nhân.

Một lỗi hợp lệ về nghiệp vụ là “Mật khẩu không đáp ứng quy tắc”. Một lỗi **không an toàn** là “Mật khẩu `user-entered-secret` không đạt yêu cầu”, vì dù request bị từ chối, chính response hoặc log đã làm lộ bí mật.

Hai nguồn rủi ro có liên hệ nhưng khác nhau:

1. **Lộ thông tin qua nội dung message:** chương trình nối thẳng `rejectedValue`/input vào thông báo hoặc log. Ngay cả khi không có expression engine, điều này vẫn làm lộ dữ liệu.
2. **Đưa input không tin cậy vào *template* nội suy:** một số Jakarta Bean Validation providers, ví dụ Hibernate Validator, hỗ trợ message parameters và Jakarta Expression Language (EL). Tạo message template bằng cách nối input có thể dẫn đến **biểu thức được diễn giải không chủ đích**, phụ thuộc cấu hình/feature level.

**Quy tắc xuyên suốt:** xây thông báo từ **mã lỗi/key cố định do server kiểm soát**, lựa chọn locale và metadata không nhạy cảm; **không** đưa raw input, target object, token hoặc secret vào message template hay các biến nội suy. Kiểm tra giá trị là nhiệm vụ của validator; phản hồi người dùng nên mô tả **quy tắc bị vi phạm**, không đọc lại dữ liệu đã nhập.

## 2. Bản đồ nơi dữ liệu có thể bị lộ

| Nơi dữ liệu đi qua | Dấu hiệu rủi ro | Nguyên tắc an toàn |
| --- | --- | --- |
| `ConstraintValidator#isValid` | Nối `value` vào `message` hoặc custom violation template. | Template cố định và không chứa giá trị nhạy cảm. |
| `ConstraintViolation#getMessage()` | Message có thể chứa giá trị đã được nội suy. | Chỉ sử dụng message đã kiểm soát; không tự đưa input vào template. |
| `ConstraintViolation#getInvalidValue()` | Trả trực tiếp giá trị bị từ chối. | Không serialize hoặc log giá trị này. |
| `FieldError#getRejectedValue()` | Giữ giá trị field không hợp lệ sau data binding. | Không đưa vào JSON, HTML, log, tracing. |
| `BindingResult` / `BindException` | In toàn bộ object/exception có thể kéo theo field errors và rejected values. | Chỉ chọn metadata an toàn; không log nguyên result. |
| `HttpMessageNotReadableException` | Có cause/chi tiết JSON parse chứa input hoặc cấu trúc nội bộ. | Trả thông báo đọc body chung, không echo exception message. |
| `MessageSource#getMessage(...)` | Message arguments chứa secret, hoặc key do client tự chọn. | Chỉ truyền key từ allowlist và tham số không nhạy cảm. |
| `@ControllerAdvice` | Trả nguyên `ex.getMessage()`, `toString()`, stack trace hoặc target. | Dùng response schema public ổn định, mapping theo loại lỗi. |
| Logs/telemetry | `logger.warn("{}", request)` hoặc gắn body vào span. | Loại bỏ, che hoặc hạn chế dữ liệu; log mã lỗi, path đã chuẩn hóa, request ID. |
| Frontend HTML | Dùng `innerHTML` cho message hoặc raw rejected value. | Hiển thị như **text**; encode theo ngữ cảnh đầu ra. |

**Lưu ý về mức độ nhạy cảm:** tên field hay mã lỗi không nhất thiết là thông tin công khai. Một property nội bộ như `internalRiskScore`, `passwordHash` hoặc cấu trúc entity sâu cũng có thể tiết lộ thiết kế hệ thống. Khi tạo API lỗi public, nên **whitelist tên field hiển thị**, không tự xuất mọi property path.

## 3. Phân biệt *message template*, *interpolated message* và *response công khai*

### 3.1. Jakarta Bean Validation có hai khái niệm riêng

Với constraint:

~~~java
@NotBlank(message = "{signup.email.required}")
private String email;
~~~

`"{signup.email.required}"` là một **message template/descriptor** được khai báo bởi ứng dụng. `MessageInterpolator` của Jakarta Validation dùng resource bundle và các quy tắc interpolation để chuyển nó thành thông báo, ví dụ “Vui lòng nhập email”.

Khi có `ConstraintViolation`:

- `violation.getMessageTemplate()` trả template gốc, ví dụ `"{signup.email.required}"`.
- `violation.getMessage()` trả câu chữ **đã nội suy**.
- `violation.getInvalidValue()` có thể trả **giá trị thực đã bị từ chối**, bao gồm bí mật, và **không an toàn để đưa vào phản hồi/log**.
- `violation.getPropertyPath()` giúp biết vị trí vi phạm, nhưng cần quyết định phần nào của path có thể công khai.
- `violation.getConstraintDescriptor()` có metadata về constraint; không có lý do tự serialize toàn bộ descriptor vào JSON response.

Template **không phải** dữ liệu người dùng. Nên giữ key và template được viết, review, quản lý version trong source hoặc resources của server.

### 3.2. Spring `MessageSource` là một lớp giải quyết thông báo khác

Trong Spring MVC, lỗi Bean Validation và binding có thể được đưa vào `BindingResult` dưới dạng `FieldError` hoặc `ObjectError`. Một `FieldError` thường có:

- `getCode()`: mã gốc như `NotBlank`, `Size`, `typeMismatch`.
- `getCodes()`: các mã ứng viên theo object/field/type.
- `getDefaultMessage()`: thông báo fallback (có thể đã qua Bean Validation interpolation).
- `getArguments()`: arguments cho message resolution.
- `getRejectedValue()`: giá trị bị từ chối, **không hiển thị/ghi log trực tiếp**.

`MessageSource` có thể dùng `getMessage(error, locale)` để thử các mã lỗi theo thứ tự. Nhưng ngay cả khi Spring chọn một message key có vẻ an toàn, **arguments và default message cũng phải được kiểm soát**. Nếu đưa secret vào message arguments hoặc tự serialize `FieldError`, thông tin vẫn có thể bị lộ.

**Không nhầm hai tầng:** Jakarta Bean Validation **nội suy constraint message**, còn Spring `MessageSource` **giải quyết thông báo theo code/locale**. Chúng có thể được tích hợp trong Spring Boot nhưng không đồng nghĩa mọi bundle đều có cùng phạm vi, cú pháp và chính sách bảo mật.

## 4. Ngôn ngữ nội suy: `{...}` khác `${...}`

Hibernate Validator, một Jakarta Validation provider phổ biến, hỗ trợ:

1. **Message parameters** dạng `{min}`, `{max}` hoặc `{signup.secret.invalid}`. Chúng có thể tham chiếu attribute của constraint, tham số do validator thêm hoặc key trong `ValidationMessages.properties`.
2. **Jakarta Expression Language** dạng `${...}`, cho phép một số phép biểu thức trên metadata, biến và, tùy feature level, validated object.

Ví dụ nội suy **metadata không nhạy cảm**:

~~~java
@Size(min = 12, max = 128,
      message = "Độ dài phải từ {min} đến {max} ký tự")
private String secret;
~~~

Trong ví dụ này, `min=12` và `max=128` là **giới hạn được server khai báo**, không phải nội dung secret. Truyền các con số giới hạn vào thông báo có thể chấp nhận được nếu chính sách sản phẩm cho phép tiết lộ độ dài yêu cầu. Không nên gán `secret` vào một biến `{userValue}` rồi yêu cầu template in nó ra.

Một ví dụ EL quen thuộc là `${validatedValue}`. Hibernate Validator có thể cung cấp giá trị đang được kiểm tra dưới tên này khi ngữ cảnh EL cho phép. Với mật khẩu, token, PII hoặc nội dung riêng tư, **không dùng biểu thức đó để hiển thị giá trị**. Thông báo không cần nhắc lại người dùng đã nhập gì để giải thích lỗi.

### Cú pháp escape

Theo tài liệu Hibernate Validator, nếu muốn dùng các ký tự cú pháp nội suy **như văn bản literal** trong message descriptor, có quy tắc escape cho `\{`, `\}`, `\$` và `\\`. Tuy nhiên, **escape cú pháp không phải chiến lược chính để xử lý dữ liệu không tin cậy**. Với secret, tốt nhất là **không đưa secret vào descriptor/arguments**; tránh phải đoán tất cả ngữ cảnh escape trong nhiều thư viện.

### Không dùng EL để thiết kế câu thông báo cho bí mật

Hai thông điệp có ích mà không cần EL:

~~~properties
signup.secret.invalid=Mật khẩu không đáp ứng yêu cầu bảo mật.
signup.email.invalid=Email không hợp lệ.
~~~

Thay vì cố tạo câu “Giá trị X có Y ký tự, thiếu Z điều kiện”, ứng dụng có thể đưa ra hướng dẫn **không chứa input**: “Dùng ít nhất 12 ký tự, gồm chữ hoa, chữ thường và chữ số”. Cách này thường dễ dịch, dễ kiểm thử và ít rủi ro hơn.

## 5. Hibernate Validator: các mức quyền Expression Language

Từ Hibernate Validator 6.2, `ExpressionLanguageFeatureLevel` cung cấp những mức khả năng cho EL:

| Mức | Khả năng | Gợi ý bảo mật |
| --- | --- | --- |
| `NONE` | Không nội suy EL. | Ưu tiên cho custom violations không cần EL. |
| `VARIABLES` | Cho phép expression variables được thêm, formatter và resource bundles theo cấu hình. | Chỉ nếu thực sự cần, không thêm secret vào variables. |
| `BEAN_PROPERTIES` | Thêm quyền truy cập các bean properties. | Cần cân nhắc nguy cơ nhìn thấy thuộc tính không nên hiển thị. |
| `BEAN_METHODS` | Thêm khả năng gọi bean methods. | Nguy cơ bảo mật rất cao nếu template chịu ảnh hưởng input; **không bật chỉ để tạo lời nhắn động**. |

Ở Hibernate Validator 8/9, **mặc định của standard constraint message** có thể cho phép `BEAN_PROPERTIES`, trong khi **EL cho custom violations tạo qua `ConstraintValidatorContext` mặc định là `NONE`**; nếu chủ động bật EL cho từng custom violation, mức mặc định an toàn hơn là `VARIABLES`. Đây là chi tiết **của provider và version**, không nên áp thành quy tắc cho mọi Bean Validation implementation.

Tài liệu Hibernate Validator cảnh báo đặc biệt về việc nối input trực tiếp thành template và mở quyền EL mạnh; có thể dẫn đến thực thi biểu thức không mong muốn, lộ thông tin hoặc hậu quả nghiêm trọng. Không dùng `BEAN_METHODS` cho các template có bất kỳ nguồn nào không tin cậy.

**Quan trọng:** EL bị tắt **không ngăn** một message cố tình nối thêm secret dưới dạng chuỗi literal. Đây là hai lớp bảo vệ khác nhau:

- Tránh **lộ dữ liệu**: không bao giờ đưa secret vào message/response.
- Tránh **expression injection**: không tạo template từ input và không nới quyền EL tùy tiện.

### Những mẫu cần tránh

~~~java
// SAI: message chứa raw input, làm lộ giá trị.
String message = "Giá trị không hợp lệ: " + secret;

// SAI: nội dung người dùng đi vào *message template*.
context.buildConstraintViolationWithTemplate(
        "Không hợp lệ: " + secret)
        .addConstraintViolation();

// SAI: một biến EL mang secret nếu sau đó được in ra message.
// hibernateContext.addExpressionVariable("entered", secret);

// SAI: log toàn bộ giá trị bị từ chối.
// logger.warn("Rejected secret={}", secret);
~~~

Đoạn trên là **anti-patterns để nhận diện khi review**, không phải chương trình nên chạy. Một người tấn công không cần quyền đọc database nếu API hoặc log tự in ra secret. Với EL, không nên dựa vào việc provider đã hạn chế feature level để hợp thức hóa một template do client kiểm soát.

### Mẫu an toàn cho custom violation

~~~java
@Override
public boolean isValid(String secret,
                       ConstraintValidatorContext context) {
    if (secret == null || secret.isBlank()) {
        return true; // @NotBlank có thể xử lý riêng.
    }

    if (isAllowedByLocalPolicy(secret)) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            "{signup.secret.invalid}")
            .addConstraintViolation();

    return false;
}
~~~

Đây là **snippet** trong `ConstraintValidator` có helper `isAllowedByLocalPolicy` giả định. Template `"{signup.secret.invalid}"` là key **cố định trong source**, không chứa secret. Với default custom EL của Hibernate Validator, cũng không cần bật EL cho trường hợp này.

Nếu chỉ cần một thông báo duy nhất, đơn giản hơn là khai báo `message = "{signup.secret.invalid}"` trên annotation custom constraint rồi để `isValid(...)` **trả `false`**, không cần tự tạo custom violation. Bản chạy đầy đủ ở phần 9 dùng cách đơn giản này.

### Khi buộc phải truyền tham số vào message

Một số ứng dụng muốn hiển thị giới hạn như `12` hoặc `128`. Với Hibernate Validator, có API riêng `HibernateConstraintValidatorContext#addMessageParameter(name, value)` để bổ sung message parameter mà **không cần** tự nối chuỗi từ user input. Ví dụ **chỉ truyền metadata không nhạy cảm**:

~~~java
HibernateConstraintValidatorContext hibernate =
        context.unwrap(HibernateConstraintValidatorContext.class);

hibernate.addMessageParameter("policyMin", 12);

hibernate.disableDefaultConstraintViolation();
hibernate.buildConstraintViolationWithTemplate(
        "{signup.secret.min}")
        .addConstraintViolation();
~~~

Với key do server kiểm soát:

~~~properties
signup.secret.min=Giá trị cần có ít nhất {policyMin} ký tự.
~~~

Đây là snippet **dành riêng cho Hibernate Validator**, cần import `org.hibernate.validator.constraintvalidation.HibernateConstraintValidatorContext` và không phải file độc lập. Với một constraint bị fail, code caller phải trả `false`; default violation đã được tắt nên phải thêm ít nhất một custom violation. Không truyền secret vào `addMessageParameter` dù API có hỗ trợ escaping; **escaping không ngăn chính giá trị được hiển thị**.

Tương tự, `addExpressionVariable(...)` **không tự đồng nghĩa an toàn về riêng tư**. Dù cách truyền biến có thể giảm nguy cơ injection so với nối trực tiếp, một template có quyền đọc/in biến đó vẫn có thể làm lộ dữ liệu. Chỉ dùng EL nếu điều kiện sản phẩm thực sự yêu cầu và đã giới hạn feature level/inputs.

## 6. Tránh lộ dữ liệu qua `BindingResult` và Spring MVC

`BindingResult` có nhiệm vụ giúp UI xử lý lỗi và giữ lại dữ liệu form khi cần. Đây vừa là tính năng hữu ích, vừa là lý do **không thể serialize thẳng đối tượng lỗi**:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<?> onInvalid(MethodArgumentNotValidException ex) {
    // SAI: không trả trực tiếp BindingResult/FieldError ra JSON.
    return ResponseEntity.badRequest()
            .body(ex.getBindingResult());
}
~~~

Đoạn này là anti-pattern minh họa. `FieldError#getRejectedValue()` có thể là password/token/PII. Nhiều đối tượng còn mang internal object name, class name, constraint metadata và property path mà client không cần biết.

Các thao tác cũng cần tránh:

~~~java
// Không làm thế này khi input có thể nhạy cảm:
logger.warn("Validation exception: {}", ex);
logger.warn("All errors: {}", ex.getBindingResult());
logger.warn("Rejected value: {}", fieldError.getRejectedValue());
return ResponseEntity.badRequest()
        .body(Map.of("details", ex.getMessage()));
~~~

Cả `Exception#toString()`, `getMessage()`, `BindingResult#toString()` và thông báo do converter/validator tạo **có thể** chứa dữ liệu/chi tiết ngoài ý muốn; không khẳng định tất cả phiên bản luôn in cùng nội dung. Quy tắc bảo mật là **không dựa vào cấu trúc string nội bộ để làm API/log contract**.

### Trả message theo mã lỗi đã kiểm soát

Ví dụ an toàn hơn:

~~~java
List<String> publicFields =
        ex.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .map(field -> switch (field) {
                    case "email" -> "email";
                    case "secret" -> "secret";
                    default -> "request";
                })
                .distinct()
                .sorted()
                .toList();
~~~

Đây là snippet trong handler (đầy đủ ở phần 9). Chỉ **whitelist tên field công khai**; không trả `rejectedValue`, template, target object, parser exception hoặc message tùy ý. Sau đó ánh xạ mỗi field vào **message code do server quyết định**, ví dụ `signup.email.invalid` hoặc `signup.secret.invalid`.

Điểm tế nhị: `FieldError#getDefaultMessage()` cũng không nên được xem là an toàn 100% nếu custom validator/bundle của ứng dụng có thể chứa raw input. Với API cần chính sách redaction mạnh, dùng **mapping code/field đã audit** thay vì sao chép mọi default message.

### Lỗi toàn object và các exception khác

- `getGlobalErrors()` trả object-level errors, có thể phát sinh từ class-level constraints. Không tự xuất `ObjectError#getObjectName()` nếu là tên nội bộ; map sang public error type.
- `HttpMessageNotReadableException` có thể phát sinh khi JSON không parse/deserialize được, **trước Bean Validation**. Không echo `ex.getMostSpecificCause().getMessage()`.
- `HandlerMethodValidationException` là một kiểu lỗi khác trong MVC 6.1+ khi method validation chạy. Nếu ứng dụng sử dụng, cần handler riêng nhưng vẫn áp dụng **cùng chính sách không lộ giá trị**.
- `ConstraintViolationException` do một tầng executable/service validation khác ném cũng có `ConstraintViolation#getInvalidValue()`; không serialize nguyên set violations.
- `@ModelAttribute` và `@RequestBody` đi qua các pipeline binding/conversion khác nhau nhưng đều xử lý **input không đáng tin cậy**; không nên cho phép chỗ này redaction còn chỗ kia lộ raw values.

## 7. Spring `MessageSource`: dịch **code**, không dịch **secret**

Một thiết kế đa ngữ an toàn thường có ba tầng:

~~~text
User input -> binding / validation -> public error category
                                        |
                                        v
                          Allowlisted message key
                           /                 \
                    Locale vi             Locale en
                       |                      |
           "Mật khẩu không..."     "Secret does not..."
                       \                      /
                        v                    v
                  JSON/HTML thông báo chung
                  (không có raw input)
~~~

Một bundle đơn giản:

~~~properties
signup.secret.invalid=Mật khẩu không đáp ứng yêu cầu bảo mật.
signup.email.invalid=Email không hợp lệ.
signup.request.invalid=Yêu cầu không hợp lệ.
~~~

Các key là giá trị do **server định nghĩa**. Chỉ lựa chọn key từ tập đã xác định:

~~~java
String key = switch (field) {
    case "email" -> "signup.email.invalid";
    case "secret" -> "signup.secret.invalid";
    default -> "signup.request.invalid";
};

String publicMessage =
        messageSource.getMessage(key, null, locale);
~~~

Đây là snippet trong handler có biến `field`, `messageSource` và `locale`. **Không** xây key từ tên tùy ý do client truyền rồi cho client truy vấn mọi key nội bộ của bundle.

### Cẩn thận cả với `MessageFormat` arguments

Spring `MessageSource` có thể định dạng thông điệp với placeholders như `{0}`, `{1}`. Đây **không phải** cùng cú pháp/engine với Hibernate Validator EL `${...}`, nhưng giá trị argument được **hiển thị** sau khi format.

Ví dụ hợp lý:

~~~java
messageSource.getMessage(
        "signup.secret.minimum",
        new Object[] {12},  // metadata không nhạy cảm
        locale);
~~~

Với bundle:

~~~properties
signup.secret.minimum=Mật khẩu cần ít nhất {0} ký tự.
~~~

Ví dụ không phù hợp:

~~~java
messageSource.getMessage(
        "signup.secret.rejected",
        new Object[] {secret}, // SAI: message có thể in secret.
        locale);
~~~

Nếu message có `{0}`, nội dung `secret` sẽ trở thành một phần câu trả về. Dù message code được whitelist, **argument vẫn có thể làm lộ dữ liệu**. Khi không thật sự cần thông tin động, truyền `null` arguments và dùng text tĩnh.

### Locale và cache

Cùng một lỗi có thể cần tiếng Việt hoặc tiếng Anh. Backend có thể nhận `Locale` từ `Accept-Language` hoặc chính sách locale khác của ứng dụng. Chọn locale khác **không** cho phép trả thêm dữ liệu:

~~~text
vi: "Mật khẩu không đáp ứng yêu cầu bảo mật."
en: "Secret does not meet the security requirements."
~~~

Nếu response public thay đổi theo `Accept-Language`, cân nhắc `Vary: Accept-Language` hoặc cache policy thích hợp để tránh trả nhầm ngôn ngữ qua CDN. Không cache request body chứa secrets, và không dùng raw validation response như một kho lưu giá trị đã nhập.

## 8. Phân loại rủi ro: nội suy, logging, HTML và observability

### 8.1. Message interpolation không phải HTML escaping

Giả sử client nhập text có ký tự HTML vào một trường có thể hiển thị. Ngay cả khi message interpolation không thực thi EL, nếu frontend hiển thị raw message bằng `innerHTML`, chuỗi chứa markup có thể tạo rủi ro XSS. **Đừng trộn hai loại bảo vệ**:

1. Không đưa giá trị nhạy cảm/user-controlled vào error message ngay từ backend.
2. Khi hiển thị message/field data được phép hiển thị, escape/encode đúng **ngữ cảnh đầu ra**.
3. Với frontend, ưu tiên DOM `textContent`, React text rendering hoặc component tương đương, không dùng HTML injection APIs cho thông điệp lỗi.

Một phản hồi JSON được serialize đúng vẫn có thể bị xử lý sai nếu frontend lấy property `message` rồi gán vào `innerHTML`. JSON escaping và HTML output encoding là **hai ngữ cảnh khác nhau**.

### 8.2. Logging phải giảm thiểu dữ liệu

OWASP khuyến nghị tránh ghi trực tiếp passwords, access tokens, session identifiers và nhiều loại thông tin cá nhân nhạy cảm vào log. Thay vì:

~~~java
logger.warn("Invalid sign up: {}", signupRequest);
logger.warn("Field errors: {}", bindingResult.getAllErrors());
~~~

Hãy log **metadata đủ điều tra nhưng không chứa input**:

~~~java
logger.info("Validation failed: route={}, code={}, count={}",
        "/api/signup",
        "VALIDATION_FAILED",
        errorCount);
~~~

Đây là snippet có `logger` và `errorCount` giả định. Trong production, thông tin bổ sung phù hợp gồm timestamp, request ID ngẫu nhiên, route template, status và error category. Nếu có correlation ID, phải kiểm soát nguồn và định dạng; không dùng access token làm request ID.

**Cẩn thận** với thư viện logging/observability middleware: body logging filter, request/response capture, APM span attribute, automatic exception reporting hoặc `toString()` của DTO có thể làm lộ giá trị **ngoài đoạn controller**. Cần kiểm tra cấu hình infrastructure, không chỉ tìm `logger.info` trong source business.

### 8.3. Đừng dựa vào hash để “ẩn” bí mật trong log

Hash trực tiếp mật khẩu/token rồi log có thể vẫn tạo giá trị có thể liên kết, hỗ trợ dò đoán hoặc tái nhận diện tùy dữ liệu. **Mặc định không log secret, cũng không log hash của secret**. Nếu có yêu cầu kiểm toán đặc biệt, phải thiết kế theo chính sách dữ liệu/retention và threat model độc lập; không thêm “hash(password)” vào log chỉ vì nhìn có vẻ an toàn.

### 8.4. Thông báo quá chi tiết cũng có thể lộ trạng thái hệ thống

Trong form login, thông điệp “email không tồn tại” và “mật khẩu sai” khác nhau có thể giúp suy đoán tài khoản. Tùy use case, một mã chung `AUTH_FAILED` sẽ an toàn hơn. Với signup, thông báo username/email đã dùng cũng có thể cho phép enumeration, nên cân nhắc product/security policy, rate limiting và thiết kế UX. **Không phải mọi thông tin không chứa password đều vô hại.**

## 9. Ví dụ chạy được: Spring Boot 3.x, Java 17+ và thông báo lỗi an toàn

Demo sau có mục tiêu **không in raw secret vào validation message/JSON/log**. Nó dùng:

- Jakarta Bean Validation: `@NotBlank`, `@Email` và một constraint `@SecretPolicy`.
- Hibernate Validator (qua `spring-boot-starter-validation`) làm provider phổ biến của Spring Boot 3.x.
- `@Valid @RequestBody` để kiểm tra DTO JSON.
- `@RestControllerAdvice` trả **error code, field name đã whitelist và message được dịch** bằng `MessageSource`.
- `ValidationMessages.properties` để giữ template cố định của constraint, còn `messages*.properties` dùng cho response public.
- MockMvc và JUnit 5 để kiểm thử chính sách không tiết lộ input.

Để có thể chạy độc lập mà không cần database, endpoint chỉ mô phỏng chấp nhận input hợp lệ; **không lưu hoặc ghi log secret**.

### 9.1. Maven dependencies

Tạo dự án Spring Boot 3.x với parent/BOM quản lý versions, Java 17+, Maven. Thêm:

~~~xml
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
~~~

Các file Java thuộc package `com.example.safevalidation`. Các tài nguyên nằm trong `src/main/resources/`. Dùng chung các starter như trên, **không tự thêm một bản Hibernate Validator khác version** với Spring Boot BOM.

### 9.2. File `SafeValidationApplication.java`

Đường dẫn: `src/main/java/com/example/safevalidation/SafeValidationApplication.java`

~~~java
package com.example.safevalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeValidationApplication.class, args);
    }
}
~~~

### 9.3. File `SecretPolicy.java`: message template cố định

Đường dẫn: `src/main/java/com/example/safevalidation/SecretPolicy.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SecretPolicyValidator.class)
public @interface SecretPolicy {

    String message() default "{signup.secret.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

**Điểm bảo mật:** `message()` chỉ chứa **một key cố định**. Nó không nhận giá trị secret và không sử dụng `${validatedValue}`. Trường hợp cần nhiều locale, provider giải quyết key qua cấu hình message interpolation; response public vẫn được quyết định bằng mapping khác.

### 9.4. File `SecretPolicyValidator.java`: chỉ kiểm tra, không lặp lại input

Đường dẫn: `src/main/java/com/example/safevalidation/SecretPolicyValidator.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SecretPolicyValidator
        implements ConstraintValidator<SecretPolicy, String> {

    @Override
    public boolean isValid(
            String secret, ConstraintValidatorContext context) {

        // @NotBlank trong DTO xử lý null hoặc blank.
        if (secret == null || secret.isBlank()) {
            return true;
        }

        // Chính sách đơn giản, cục bộ, không I/O.
        if (secret.length() < 12 || secret.length() > 128) {
            return false;
        }

        boolean upper = false;
        boolean lower = false;
        boolean digit = false;

        for (int i = 0; i < secret.length(); i++) {
            char c = secret.charAt(i);
            upper |= Character.isUpperCase(c);
            lower |= Character.isLowerCase(c);
            digit |= Character.isDigit(c);
        }

        return upper && lower && digit;
    }
}
~~~

Validator không log, không gọi network/database, không lưu state theo request và không đặt `secret` vào message. Provider sẽ tạo violation với template `"{signup.secret.invalid}"` nếu `isValid` trả `false`.

**Giới hạn chính sách:** đây là ví dụ học tập về an toàn thông báo, không phải hướng dẫn hoàn chỉnh để lựa chọn chính sách mật khẩu hiện đại. Với production, tuân theo quy tắc authentication đã được tổ chức phê duyệt; cân nhắc độ dài, blocklist, rate limiting và các yêu cầu như NIST SP 800-63. Tránh tự xây dựng quy tắc phức tạp chỉ vì ví dụ có chữ hoa/chữ số. Phân biệt độ dài Java UTF-16 và số ký tự theo người dùng nếu hỗ trợ Unicode; demo dùng quy tắc độ dài đơn giản.

### 9.5. File `SignupRequest.java`: DTO không có `toString` tự ghi log

Đường dẫn: `src/main/java/com/example/safevalidation/SignupRequest.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public final class SignupRequest {

    @NotBlank
    @Email
    private String email;

    @NotBlank
    @SecretPolicy
    private String secret;

    public SignupRequest() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getSecret() {
        return secret;
    }

    public void setSecret(String secret) {
        this.secret = secret;
    }
}
~~~

DTO này không khai báo `toString` để tránh vô tình xây dựng một chuỗi tiết lộ secret. Tuy vậy, **không có nghĩa object an toàn để log bằng mọi serializer/reflection logger**. Tránh các công cụ tự động dump tất cả fields. Cũng không dùng Lombok `@Data` hoặc Java record chứa secret rồi log object một cách vô thức, vì `toString()` tự sinh có thể chứa field values.

### 9.6. File `SignupController.java`

Đường dẫn: `src/main/java/com/example/safevalidation/SignupController.java`

~~~java
package com.example.safevalidation;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class SignupController {

    @PostMapping(path = "/signup",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> signup(
            @Valid @RequestBody SignupRequest request) {

        // Demo: chỉ chấp nhận request hợp lệ.
        // Không log hoặc echo request.getSecret().
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "accepted"));
    }
}
~~~

`@Valid` kích hoạt kiểm tra trên `SignupRequest` sau khi JSON deserialize thành công. Nếu secret không đạt constraint, method body thường **chưa được gọi**; `MethodArgumentNotValidException` được advice xử lý ở bước tiếp theo. Nếu JSON hỏng cú pháp, converter có thể ném `HttpMessageNotReadableException` **trước cả validation**.

Endpoint này **không lưu tài khoản thật** và dùng HTTP 201 chỉ để minh họa status của request hợp lệ; một hệ thống sản xuất chỉ nên trả Created sau khi resource đã được tạo bền vững và có chính sách xử lý bảo mật phù hợp.

### 9.7. File `SignupValidationAdvice.java`: một hợp đồng lỗi đã kiểm soát

Đường dẫn: `src/main/java/com/example/safevalidation/SignupValidationAdvice.java`

~~~java
package com.example.safevalidation;

import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;
import java.util.Locale;

@RestControllerAdvice
public class SignupValidationAdvice {

    private final MessageSource messages;

    public SignupValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<PublicError> invalidArgument(
            MethodArgumentNotValidException ex, Locale locale) {

        // Chỉ chọn tên field từ allowlist công khai.
        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .map(field -> switch (field) {
                    case "email" -> "email";
                    case "secret" -> "secret";
                    default -> "request";
                })
                .distinct()
                .sorted()
                .toList();

        List<FieldIssue> issues = fields.stream()
                .map(field -> {
                    String code = switch (field) {
                        case "email" -> "signup.email.invalid";
                        case "secret" -> "signup.secret.invalid";
                        default -> "signup.request.invalid";
                    };

                    return new FieldIssue(
                            field,
                            "INVALID_FIELD",
                            messages.getMessage(code, null, locale));
                })
                .toList();

        // Không serialize ex, BindingResult hoặc rejectedValue.
        return ResponseEntity.badRequest().body(
                new PublicError("VALIDATION_FAILED", issues));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<PublicError> unreadableBody(
            HttpMessageNotReadableException ex, Locale locale) {

        // Không trả ex.getMessage(), parser cause hoặc body thô.
        return ResponseEntity.badRequest().body(
                new PublicError(
                        "MALFORMED_BODY",
                        List.of(new FieldIssue(
                                "request",
                                "INVALID_BODY",
                                messages.getMessage(
                                        "signup.request.invalid",
                                        null,
                                        locale)))));
    }

    public record FieldIssue(
            String field, String code, String message) {
    }

    public record PublicError(
            String error, List<FieldIssue> fields) {
    }
}
~~~

Phân tích bảo mật:

1. `FieldError#getField()` được **map qua switch**. Chỉ `email`, `secret` hoặc `request` được xuất ra; không tự đưa nested/internal property path ra API.
2. Message key cũng được chọn bằng **switch do server viết**, không do query parameter/body cung cấp.
3. Không gọi `FieldError#getRejectedValue()`, `ex.getMessage()`, `BindingResult#toString()` hoặc `ConstraintViolation#getInvalidValue()`.
4. `MessageSource#getMessage(code, null, locale)` dùng **không có arguments**, vì response không cần giá trị động.
5. `HttpMessageNotReadableException` có handler riêng và trả câu chung, không đưa lỗi decoder/Jackson ra client.
6. `distinct()` + `sorted()` tạo thứ tự field ổn định cho test/client, kể cả khi `@NotBlank` và `@SecretPolicy` cùng báo lỗi.
7. Các record `FieldIssue`/`PublicError` chỉ có metadata công khai; không chứa secret/target object.

**Giới hạn:** handler minh họa chỉ xử lý lỗi field và JSON unreadable. Trong ứng dụng thật có thể cần mapping riêng cho global/object-level errors, `HandlerMethodValidationException`, media type, security và service/domain exceptions. Tất cả các nhánh đó phải tuân thủ **cùng một chính sách redaction**. Không bắt toàn bộ `Exception` rồi trả 400 vì có thể che lỗi server.

### 9.8. Bundle Spring: `messages.properties`, `messages_vi.properties`, `messages_en.properties`

Tạo `src/main/resources/application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Tạo `src/main/resources/messages.properties`:

~~~properties
signup.email.invalid=Email address is invalid.
signup.secret.invalid=Secret does not meet the security requirements.
signup.request.invalid=Request body is invalid.
~~~

Tạo `src/main/resources/messages_en.properties`:

~~~properties
signup.email.invalid=Email address is invalid.
signup.secret.invalid=Secret does not meet the security requirements.
signup.request.invalid=Request body is invalid.
~~~

Tạo `src/main/resources/messages_vi.properties`:

~~~properties
signup.email.invalid=Email không hợp lệ.
signup.secret.invalid=Mật khẩu không đáp ứng yêu cầu bảo mật.
signup.request.invalid=Dữ liệu yêu cầu không hợp lệ.
~~~

Trong Spring Boot, bundle mặc định `messages.properties` giúp auto-configuration nhận basename. Locale từ request có thể được Spring MVC xác định theo `Accept-Language` nếu ứng dụng không thay đổi LocaleResolver; `messages_vi` và `messages_en` tạo thông báo public tương ứng.

### 9.9. Bundle Jakarta Validation: `ValidationMessages.properties`

Tạo `src/main/resources/ValidationMessages.properties`:

~~~properties
signup.secret.invalid=Secret does not meet the configured policy.
~~~

Tùy mục tiêu i18n của Bean Validation provider, có thể tạo `ValidationMessages_vi.properties`:

~~~properties
signup.secret.invalid=Mật khẩu không đáp ứng quy tắc được cấu hình.
~~~

**Tại sao hai nhóm bundle?** `ValidationMessages*` thuộc message interpolation của Jakarta Bean Validation; `messages*` ở ví dụ là Spring `MessageSource` để tạo response public. Trong Spring Boot, `LocalValidatorFactoryBean` và MessageSource có thể được tích hợp, nhưng **không dựa vào tình cờ trùng ngôn ngữ của default constraint message** để quyết định response. Dù provider nội suy ra tiếng Anh hay tiếng Việt, advice chỉ trả message **đã whitelist** bằng `messages.getMessage(code,null,locale)`.

Với hệ thống có i18n phức tạp, có thể thống nhất bundle/message source cho cả hai lớp **nếu đã kiểm soát đầy đủ các key, interpolation context và version**, nhưng đó là một quyết định cấu hình riêng. Việc demo dùng hai bundle rõ ràng khiến ranh giới bảo mật dễ kiểm thử.

### 9.10. Ví dụ phản hồi HTTP

Request chứa secret ngắn:

~~~http
POST /api/signup
Content-Type: application/json
Accept-Language: vi

{"email":"lan@example.com","secret":"tiny"}
~~~

HTTP 400 dự kiến:

~~~json
{
  "error": "VALIDATION_FAILED",
  "fields": [
    {
      "field": "secret",
      "code": "INVALID_FIELD",
      "message": "Mật khẩu không đáp ứng yêu cầu bảo mật."
    }
  ]
}
~~~

Response không chứa chuỗi `"tiny"`, không chứa `rejectedValue`, không mô tả internal constraint expressions và không lộ target object.

Với `Accept-Language: en`, cùng lỗi trả:

~~~json
{
  "error": "VALIDATION_FAILED",
  "fields": [
    {
      "field": "secret",
      "code": "INVALID_FIELD",
      "message": "Secret does not meet the security requirements."
    }
  ]
}
~~~

Hai message có cùng error code, khác locale. Nếu một tổ chức yêu cầu che cả việc trường nào sai (ví dụ login), có thể trả một mã public chung thay vì liệt kê `secret`; chính sách cụ thể phải phù hợp threat model.

## 10. Kiểm thử JUnit 5 và MockMvc: bảo đảm input không bị lặp lại

Tạo `src/test/java/com/example/safevalidation/SafeValidationApplicationTest.java`:

~~~java
package com.example.safevalidation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Set;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SafeValidationApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Validator validator;

    @Test
    void validRequestReturnsOnlyPublicStatus() throws Exception {
        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "email":"lan@example.com",
                              "secret":"StrongSecret123"
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("accepted"))
                .andExpect(content().string(
                        not(containsString("StrongSecret123"))));
    }

    @Test
    void vietnameseValidationMessageDoesNotEchoSecret()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("""
                            {
                              "email":"lan@example.com",
                              "secret":"tiny"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("secret"))
                .andExpect(jsonPath("$.fields[0].message")
                        .value(
                            "Mật khẩu không đáp ứng yêu cầu bảo mật."))
                .andExpect(content().string(
                        not(containsString("tiny"))));
    }

    @Test
    void englishMessageUsesControlledTranslation()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                    .content("""
                            {
                              "email":"lan@example.com",
                              "secret":"tiny"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].message")
                        .value(
                            "Secret does not meet the security requirements."))
                .andExpect(content().string(
                        not(containsString("tiny"))));
    }

    @Test
    void invalidEmailIsMappedToPublicFieldAndMessage()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                    .content("""
                            {
                              "email":"invalid-address",
                              "secret":"StrongSecret123"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.fields[0].message")
                        .value("Email address is invalid."))
                .andExpect(content().string(
                        not(containsString("invalid-address"))));
    }

    @Test
    void multipleErrorsAreDeduplicatedAndSorted()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("""
                            {
                              "email":"invalid-address",
                              "secret":"tiny"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("email"))
                .andExpect(jsonPath("$.fields[1].field")
                        .value("secret"))
                .andExpect(content().string(
                        not(containsString("invalid-address"))))
                .andExpect(content().string(
                        not(containsString("tiny"))));
    }

    @Test
    void missingSecretIsRejectedWithoutEcho()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("""
                            {"email":"lan@example.com"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("secret"))
                .andExpect(jsonPath("$.fields[0].code")
                        .value("INVALID_FIELD"));
    }

    @Test
    void brokenJsonGetsOnlyGenericMessage()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                    .content("{\"email\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("MALFORMED_BODY"))
                .andExpect(jsonPath("$.fields[0].message")
                        .value("Dữ liệu yêu cầu không hợp lệ."));
    }

    @Test
    void missingBodyIsGenericRequestError()
            throws Exception {

        mvc.perform(post("/api/signup")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ACCEPT_LANGUAGE, "en"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("MALFORMED_BODY"));
    }

    @Test
    void constraintTemplateIsFixedAndDoesNotContainInput() {
        SignupRequest input = new SignupRequest();
        input.setEmail("lan@example.com");
        input.setSecret("tiny");

        Set<ConstraintViolation<SignupRequest>> violations =
                validator.validate(input);

        assertEquals(1, violations.size());

        ConstraintViolation<SignupRequest> violation =
                violations.iterator().next();

        assertEquals("{signup.secret.invalid}",
                violation.getMessageTemplate());
        assertFalse(violation.getMessage().contains("tiny"));
        assertEquals("secret",
                violation.getPropertyPath().toString());
    }
}
~~~

Với các file và starters đã liệt kê, **9 tests được thiết kế để pass**. Chúng xác minh:

- JSON hợp lệ trả trạng thái public, không echo secret.
- Lỗi secret có bản dịch tiếng Việt/tiếng Anh đúng, không chứa `"tiny"`.
- Email invalid không bị trả lại nguyên chuỗi.
- Hai field lỗi được deduplicate và sắp xếp.
- Secret thiếu được kiểm tra nhưng không xuất giá trị nhạy cảm.
- JSON sai cú pháp và thiếu body trả lỗi chung.
- `ConstraintViolation#getMessageTemplate()` là một **key cố định**, không chứa user input.

Chạy từ root dự án Maven:

~~~bash
./mvnw test -Dtest=SafeValidationApplicationTest
~~~

Trên Windows dùng `mvnw.cmd test -Dtest=SafeValidationApplicationTest`. Nếu đã cài Maven toàn cục, dùng `mvn test -Dtest=SafeValidationApplicationTest`.

**Giới hạn:** bài học cung cấp bộ source/test nhất quán theo Spring Boot 3.x + Java 17+; việc test thực tế phụ thuộc phiên bản/build và configuration. Đây không phải bằng chứng rằng **mọi middleware** đang chạy đã loại bỏ raw body khỏi logs. Với production phải kiểm tra thêm reverse proxy, request logging filters, security events, APM/tracing và chính sách dữ liệu.

### Thử thủ công bằng curl

Khi ứng dụng đang chạy bằng `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/api/signup" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"email":"lan@example.com","secret":"tiny"}'

curl -i -X POST "http://localhost:8080/api/signup" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"email":"lan@example.com","secret":"tiny"}'
~~~

Hai lệnh dùng giá trị **giả lập, không phải bí mật thật**. Không gửi password/token sản xuất vào shell history chỉ để thử API; dữ liệu truyền bằng `-d` có thể xuất hiện trong lịch sử terminal, process monitoring hoặc file log của môi trường test. Khi kiểm thử hệ thống thật, dùng secret giả chuyên dụng và quy trình bảo vệ phù hợp.

## 11. Khi cần dùng `@ModelAttribute`/form: lưu ý riêng về binding

Với HTML form:

~~~java
@PostMapping(path = "/signup-form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<?> signupForm(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult result) {
    // Dùng mã/field đã whitelist;
    // không serialize result hoặc form.
    return result.hasErrors()
            ? ResponseEntity.badRequest().build()
            : ResponseEntity.ok().build();
}
~~~

Đây là **snippet** cho controller khác, chưa có `SignupForm`/imports đầy đủ. Trong Spring MVC, form-urlencoded/query values được bind qua `WebDataBinder`, và `BindingResult` ngay sau object cho phép xử lý errors cục bộ.

Ví dụ người dùng gửi:

~~~text
email=lan@example.com
secret=example-only-secret
age=not-a-number
~~~

Binder có thể tạo `FieldError` mã `typeMismatch` cho `age`, và `getRejectedValue()` có thể giữ `"not-a-number"`. Với field secret cũng có thể có rejected value khi validation fail. **Đừng phụ thuộc một field “không nhạy cảm” để thay đổi chính sách chung**; logging serializer không tự biết field nào cần che khi DTO mới được thêm.

Nếu muốn giữ người dùng khỏi nhập lại form sau lỗi, **backend không bắt buộc phải gửi lại secret**. Frontend có thể giữ trạng thái input trong bộ nhớ UI theo chính sách sản phẩm, hoặc yêu cầu nhập lại trường nhạy cảm. Không lưu secret vào server-side session/message bundle chỉ để re-render form.

### `setAllowedFields` và redaction là hai việc khác nhau

`WebDataBinder#setAllowedFields(...)` giới hạn **property binding** để chống mass assignment; nó **không tự động redaction giá trị** trong `FieldError`, log hay các message do validator tạo. Ngược lại, việc không echo secret cũng **không thay thế** kiểm tra quyền và whitelist các trường có thể cập nhật.

Với JSON `@RequestBody`, Jackson deserialize theo JSON mapping rules; `setAllowedFields` của form binder không phải giải pháp chung để ngăn JSON overposting. Nên dùng request DTO riêng, validation, authentication/authorization và response schema đã kiểm soát.

## 12. Bảo vệ dữ liệu ở các tầng khác

### 12.1. Không dùng thông báo để tiết lộ trạng thái authentication

Một lỗi login không nên trở thành kênh phân biệt “username tồn tại” và “password sai” khi threat model không cho phép. Dùng mã/chữ chung như `AUTHENTICATION_FAILED`. Với đặt lại mật khẩu hoặc đăng ký, cân nhắc anti-enumeration, rate limiting và UX phù hợp.

### 12.2. Không serialize exception gốc

Các lớp như `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `ConstraintViolationException` và `HttpMessageNotReadableException` thường mang metadata/causes cho developer. Chúng **không phải response DTO**. Dùng `@RestControllerAdvice`/`ResponseEntityExceptionHandler` để tách lỗi kỹ thuật và payload public; response phải kiểm soát fields, codes, messages, status.

### 12.3. Log redaction tập trung

Tổ chức nên đặt policy chung ở logging/telemetry middleware: tránh body logging cho login/signup, lọc `Authorization`/`Cookie` headers, không log token, cấu hình trace sampling/retention, review APM integrations và quyền truy cập log. Redaction tại controller là cần thiết nhưng chưa đủ nếu reverse proxy đã ghi body trước đó.

### 12.4. Không dùng dữ liệu chưa được kiểm soát như error code

Kể cả khi không echo password, một endpoint cho client truyền key bundle trực tiếp rồi giải quyết qua `MessageSource` có thể tiết lộ các thông điệp nội bộ. Public error code phải xuất phát từ **enum/allowlist ở server**, không từ `request.getParameter("messageCode")` hay JSON field `code` không đáng tin.

### 12.5. An toàn của giới hạn payload và đầu vào

Ngoài việc không lộ dữ liệu, validation pipeline còn cần giới hạn size/complexity của JSON, form, multipart; tránh regex backtracking quá mức; không chạy DB/network blocking trong custom validators trên reactive event loop; không cho client tạo lượng lỗi khổng lồ khiến response/log quá lớn. Cân nhắc giới hạn số field errors trả về, nhưng đừng âm thầm bỏ qua các lỗi có ý nghĩa mà không có contract rõ ràng.

## 13. Test bảo mật bổ sung cho dự án thực tế

Các test ở phần 10 kiểm tra một số secret mẫu. Một bộ security regression tests mạnh hơn nên có:

1. **Canary marker test:** gửi chuỗi test duy nhất vào field nhạy cảm, xác nhận nó **không xuất hiện** trong HTTP response, logs test, tracing attributes và error reporting collector (với dữ liệu thử giả).
2. **Locale matrix:** `vi`, `en`, fallback locale, và locale không hỗ trợ đều không echo input.
3. **Binding errors:** `@ModelAttribute`, form-urlencoded, `typeMismatch`, nested field errors và `getRejectedValue()` không bị serialize.
4. **JSON parser errors:** body sai cú pháp, sai kiểu, thiếu body, không in raw JSON hoặc parser-specific detail.
5. **Bean Validation custom violations:** `getMessageTemplate()` cố định, không có dữ liệu untrusted; EL feature level không bị nâng vô lý.
6. **Multiple errors/global errors:** mapping theo allowlist và giới hạn số lượng, không để lộ các property paths nội bộ.
7. **Internationalization arguments:** message key và arguments được kiểm soát; không có `secret` hoặc user PII trong `Object[] args`.
8. **Logging integration:** middleware request logging, access logs, tracing/APM, exception reporters đều tuân thủ redaction.
9. **Frontend rendering:** message được render như text, không tạo markup/script qua `innerHTML`.
10. **Authentication/error uniformity:** lỗi liên quan đăng nhập/khôi phục không cho phép suy đoán trạng thái tài khoản ngoài policy.

Khi test logging, không tạo và sử dụng secret thật. Test dữ liệu giả cố định có thể kiểm tra bằng tooling phù hợp trong CI. **Đừng coi một test response pass là bằng chứng log/telemetry đã an toàn**; cần kiểm tra độc lập những nơi nhận dữ liệu.

## 14. Các lỗi thường gặp và cách sửa

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `"Invalid: " + value` trong `ConstraintValidator` | In nguyên input, có thể lộ secret. | Cố định key/message, không chứa raw value. |
| `buildConstraintViolationWithTemplate(prefix + input)` | Template có thể bị ảnh hưởng bởi input và EL, đồng thời lộ dữ liệu. | Template literal do server kiểm soát, ví dụ `"{signup.secret.invalid}"`. |
| Dùng `${validatedValue}` cho mật khẩu | Giá trị được in ra khi EL cho phép. | Không sử dụng giá trị validated trong message. |
| Bật `BEAN_METHODS` cho custom violations | Tăng bề mặt expression evaluation nguy hiểm. | Giữ EL tắt hoặc mức tối thiểu cần thiết; ưu tiên không dùng EL. |
| Truyền secret vào `addMessageParameter` | Escaping không ngăn thông tin được hiển thị. | Chỉ truyền metadata không nhạy cảm, ví dụ min/max. |
| Trả `ex.getBindingResult()` làm JSON | Có thể serialize rejected values/metadata nội bộ. | Ánh xạ sang DTO lỗi public có allowlist. |
| Dùng `FieldError#getDefaultMessage()` cho mọi lỗi | Custom message có thể đã chứa raw input. | Dùng code/field đã audit + `MessageSource`. |
| `logger.warn("{}", request)` | DTO/record `toString()` có thể chứa bí mật. | Log loại lỗi, status, request ID; tránh raw body. |
| Log `ConstraintViolationException` nguyên object | Có thể chứa invalid values qua toString/cause. | Chọn metadata an toàn, không log value. |
| JSON parser exception được đưa thẳng lên client | Có thể tiết lộ body fragment và chi tiết nội bộ. | Fixed generic 400, log có kiểm soát. |
| `MessageSource` nhận key/arguments trực tiếp từ request | Có thể lộ key nội bộ hoặc in giá trị nhạy cảm. | Server-side allowlist + arguments an toàn. |
| Frontend dùng `innerHTML=message` | Có thể thực thi HTML không tin cậy. | Text rendering/encoding theo context. |
| Chỉ che secret ở Controller | Filter/APM/reverse proxy vẫn có thể capture body. | Review toàn bộ chuỗi observability. |
| Hash secret rồi ghi log | Có thể tạo fingerprint/tín hiệu dò đoán. | Mặc định không log secret hay hash của secret. |
| Lỗi đăng nhập quá chi tiết | Có thể tạo kênh enumeration. | Thiết kế mã/chữ chung theo threat model. |

## 15. Checklist review trước production

- [ ] Không có `value`, `rejectedValue`, `getInvalidValue()` hoặc DTO chứa secret trong message template, JSON lỗi hay logs.
- [ ] Custom `ConstraintValidator` dùng key/descriptor cố định; không nối input vào `buildConstraintViolationWithTemplate(...)`.
- [ ] Không dùng `${validatedValue}` hoặc biến EL chứa secret; không bật `BEAN_METHODS`/feature level mạnh nếu không có lý do được review.
- [ ] Khi dùng `addMessageParameter`, chỉ truyền giới hạn/metadata không nhạy cảm; không coi escaping là redaction.
- [ ] `MessageSource` dùng key từ allowlist và không có user secrets trong formatting arguments.
- [ ] Spring `BindingResult` và `FieldError` chỉ được đọc metadata cần thiết; không serialize/log toàn bộ object.
- [ ] Có handler cho validation, parser, method validation và business errors với schema public thống nhất.
- [ ] Field name public được whitelist; error messages không tiết lộ property names/class names nội bộ.
- [ ] i18n bundles tiếng Việt/tiếng Anh không chứa placeholder lấy giá trị bí mật.
- [ ] Lỗi JSON/body parse không echo raw request, exception cause hoặc stack trace.
- [ ] Frontend render thông báo dưới dạng text; output encoding đúng context.
- [ ] Logging/APM/proxy không capture request body, Authorization/Cookie hoặc token theo mặc định.
- [ ] Test marker giả trong response, logs, tracing; test nhiều locale và nhiều loại lỗi.
- [ ] Quy tắc login/signup không tạo enumeration ngoài chính sách.
- [ ] Có retention, access control, incident response phù hợp cho log/monitoring nếu vẫn cần lưu một số metadata.

**Tóm tắt:** **Thông báo lỗi chỉ nên giải thích điều kiện nào không đạt, không đọc lại dữ liệu người dùng.** Trong Spring và Jakarta Validation, điều này đòi hỏi **template/key cố định**, **message arguments không nhạy cảm**, **kiểm soát EL**, **không serialize `BindingResult`/`FieldError` trực tiếp**, và **i18n bằng `MessageSource` trên allowlist server-side**. An toàn của thông báo phải được kiểm tra cả ở API, log, telemetry và frontend, không chỉ trong custom validator.

## Tài liệu tham khảo

- Hibernate Validator 8 Reference Guide — Message Interpolation, EL feature levels và custom violation messages: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation
- Hibernate Validator 8 API — `ExpressionLanguageFeatureLevel`: https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/messageinterpolation/ExpressionLanguageFeatureLevel.html
- Hibernate Validator 8 API — `BaseHibernateValidatorConfiguration` (EL và validated values logging): https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/BaseHibernateValidatorConfiguration.html
- Spring Framework Reference — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework Javadoc — `FieldError#getRejectedValue()`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework Javadoc — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Boot Reference — Internationalization: https://docs.spring.io/spring-boot/reference/features/internationalization.html
- OWASP Logging Cheat Sheet — loại trừ dữ liệu nhạy cảm khỏi log: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Cross Site Scripting Prevention Cheat Sheet — output encoding và xử lý ngữ cảnh HTML: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
