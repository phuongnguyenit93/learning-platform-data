# Thiết kế phản hồi lỗi theo trường mà không lộ dữ liệu đầu vào nhạy cảm

## 1. Mục tiêu và bối cảnh

Một API Spring Boot thường nhận JSON có dữ liệu cá nhân, token, địa chỉ, thông tin giao dịch và các trường lồng nhau. Khi validation thất bại, trả về lỗi theo từng trường giúp client biết chính xác cần sửa phần nào. Tuy nhiên, trả nguyên giá trị bị từ chối, thông điệp exception hoặc object request ra HTTP response có thể làm rò rỉ password, payment token, email, địa chỉ, định danh nội bộ và thông tin liên quan bảo mật.

Ví dụ request không hợp lệ:

~~~json
{
  "email": "private_input_not_an_email",
  "paymentToken": "tok_PRIVATE_example_314",
  "shipping": {
    "city": "",
    "postalCode": "private_bad_zip_314"
  },
  "items": [
    {"sku": "", "quantity": 0}
  ]
}
~~~

Client cần biết email sai định dạng, city trống và quantity phải lớn hơn 0. Client **không cần** nhận lại email đang nhập, paymentToken, postalCode, stack trace hoặc class name của server.

Bài học hướng tới một response có cấu trúc, ổn định, giới hạn thông tin và có thể kiểm thử:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "errorId": "c8b3913d-5ea7-4a6e-85ed-f2b24fc75ef0",
  "errors": [
    {
      "field": "email",
      "code": "FORMAT",
      "message": "Định dạng không hợp lệ."
    },
    {
      "field": "items[0].quantity",
      "code": "RANGE",
      "message": "Giá trị nằm ngoài phạm vi cho phép."
    },
    {
      "field": "shipping.city",
      "code": "REQUIRED",
      "message": "Trường bắt buộc."
    }
  ]
}
~~~

UUID ở đây là ví dụ minh họa; ứng dụng phải tạo giá trị errorId mới, không hard-code. Trường paymentToken có thể không xuất hiện trong danh sách nếu nó vẫn hợp lệ; ngay cả khi không hợp lệ, chỉ trả tên trường, mã lỗi và thông điệp an toàn, **không bao giờ echo giá trị token**.

Sau bài học, người học có thể phân biệt binding/validation/business errors; đọc FieldError an toàn; tạo @RestControllerAdvice cho Spring MVC, hiểu khác biệt với Spring WebFlux; xử lý nested paths và danh sách; thiết kế mã lỗi ổn định, giới hạn số lỗi; viết integration tests kiểm tra không rò rỉ dữ liệu; và áp dụng nguyên tắc log/observability phù hợp.

**Phạm vi ví dụ:** Java 17+, Spring Boot 3.3.x và Spring MVC, sử dụng Jakarta Bean Validation. Các ý tưởng bảo vệ dữ liệu cũng áp dụng cho WebFlux, nhưng exception type và cơ chế error handling không giống hoàn toàn. Spring Boot 4.x thay đổi baseline/framework/dependency; hãy đối chiếu API theo phiên bản trước khi dùng lại mã nguồn.

## 2. Tách ba lớp kiểm tra dữ liệu

Ở phía web-runtime, một request thường đi qua các bước:

~~~text
HTTP request JSON
   |
   v
HTTP body reader / Jackson
   |
   +--> JSON syntax sai, enum không hợp lệ, type mismatch
   |         -> lỗi đọc body / mapping
   |
   v
Java request DTO
   |
   v
Jakarta Bean Validation
   |
   +--> @NotBlank, @Email, @Min, @Pattern, @Valid
   |         -> lỗi theo field / object
   |
   v
Application service
   |
   +--> Quy tắc nghiệp vụ, quyền, trạng thái, tính duy nhất
   |         -> lỗi domain / authorization
   |
   v
Kết quả nghiệp vụ / response
~~~

**JSON parsing và data binding:** nội dung không đọc được hoặc không chuyển thành kiểu Java. Ví dụ quantity nhận một object thay vì Integer hoặc deliveryMethod nhận enum lạ. Những lỗi này thường xảy ra trước Bean Validation.

**Bean Validation:** DTO được tạo nhưng ràng buộc sai. Ví dụ @Email, @NotBlank, @Min(1) hoặc nested object có field rỗng.

**Business validation:** dữ liệu đúng kiểu nhưng không được phép thực hiện. Ví dụ coupon hết hạn, sản phẩm đã ngừng bán, user không có quyền. Lỗi nghiệp vụ cần mã và HTTP status theo API contract; không ép mọi lỗi domain thành VALIDATION_FAILED.

Với mục tiêu bảo mật, cả ba lớp đều không nên gửi raw input, stack trace hoặc exception.getMessage() ra client.

## 3. Vì sao trả rejectedValue rất nguy hiểm?

Khi MVC binding/validation gặp lỗi, FieldError có thể cung cấp:

- getField(): tên/path trường, ví dụ email hoặc items[0].quantity.
- getCode(): một mã do binding/validator tạo, ví dụ NotBlank, Email, Min, typeMismatch.
- getCodes(): nhiều candidate message codes để resolve thông điệp.
- getDefaultMessage(): default message của validation hoặc binding.
- getRejectedValue(): **giá trị input bị từ chối**, đôi khi là dữ liệu nhạy cảm.
- getObjectName(): tên target object trong binding.

Phản mẫu:

~~~java
Map<String, Object> details = Map.of(
        "field", fieldError.getField(),
        "rejectedValue", fieldError.getRejectedValue(),
        "message", fieldError.getDefaultMessage()
);
~~~

Đoạn minh họa trên có nhiều vấn đề: getRejectedValue có thể là token/email/địa chỉ; Map.of không chấp nhận null nếu rejectedValue rỗng; getDefaultMessage có thể chứa tham số từ custom validator, tên internal hoặc thông tin được interpolated.

Phản mẫu khác:

~~~java
return ResponseEntity.badRequest()
        .body(exception.getMessage());
~~~

Thông điệp của Jackson, binding, database hoặc validation exception là dữ liệu nội bộ, không phải hợp đồng API. Một số exception chứa path, payload fragment, Java type và stack context. Gửi thẳng chúng sang client có thể vi phạm nguyên tắc data minimization.

**Nguyên tắc:** error response chỉ gồm trường đã được cho phép công khai, mã lỗi ổn định, câu giải thích an toàn, error ID, và metadata không nhạy cảm thực sự cần thiết. Không lấy rejected value để tạo response.

## 4. Phân loại dữ liệu nhạy cảm trong validation

Không chỉ password/token mới cần bảo vệ:

| Nhóm | Ví dụ | Rủi ro khi echo trong lỗi |
| --- | --- | --- |
| Authentication secrets | password, access token, refresh token, API key | Chiếm quyền truy cập |
| Payment | paymentToken, thẻ, số tài khoản, mã giao dịch | Gian lận, lộ dữ liệu tài chính |
| PII | email, số điện thoại, ngày sinh, địa chỉ | Vi phạm quyền riêng tư |
| Identity | số giấy tờ, mã định danh, userId nội bộ | Kết hợp dữ liệu để định danh |
| Security metadata | OTP, recovery code, session ID | Bypass/xâm nhập |
| Business secrets | giá vốn, coupon nội bộ, tenant ID nhạy cảm | Lộ thông tin tổ chức |
| Free text | ghi chú khách hàng, mô tả bệnh lý, nội dung form | Có thể chứa dữ liệu bất kỳ |
| Uploaded data | tên file, đường dẫn, nội dung, MIME metadata | Lộ nội dung hoặc hạ tầng |

Không có quy tắc đơn giản "chỉ ẩn những field có tên password". Một trường note có thể chứa bí mật do người dùng tự nhập. Nếu response hoặc log echo raw JSON, rủi ro vẫn tồn tại dù DTO không có trường secret chuyên dụng.

Đối với tên field, cũng cần chọn lọc. Một field path như account.internalRiskScore hoặc một index rất dài có thể tiết lộ cấu trúc backend. Vì thế nên allowlist **public field paths**, không tự động tin mọi tên field đến từ reflection hoặc binding.

## 5. Hợp đồng phản hồi lỗi đề xuất

Một schema đơn giản:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "errorId": "c8b3913d-5ea7-4a6e-85ed-f2b24fc75ef0",
  "errors": [
    {
      "field": "shipping.city",
      "code": "REQUIRED",
      "message": "Trường bắt buộc."
    }
  ]
}
~~~

### 5.1. Ý nghĩa từng trường

- code (root): loại lỗi ở cấp request, ví dụ VALIDATION_FAILED, INVALID_JSON.
- message (root): mô tả ngắn, không tiết lộ dữ liệu.
- errorId: ID được ứng dụng tạo cho sự kiện lỗi. Có thể dùng để đối chiếu logs nếu log cùng ID; bản thân UUID mới tạo không tự động là distributed trace ID.
- errors: danh sách lỗi theo trường hoặc lỗi mức request.
- field: path public đã allowlist, ví dụ shipping.city, items[0].quantity.
- code (field): mã ổn định như REQUIRED, FORMAT, RANGE, TYPE, INVALID.
- message (field): thông điệp đã biết từ dictionary tĩnh hoặc MessageSource có kiểm soát; không copy raw exception.

### 5.2. Những trường không nên xuất hiện

- inputValue, rejectedValue, rawRequest, originalBody, rawHeaders.
- exception, stackTrace, internalType, SQL, parameter value.
- access token, password, payment token hoặc nội dung field đang bị từ chối.
- thông tin về người dùng khác, tài khoản khác, chính sách bảo mật nội bộ.
- thông tin server hostname hoặc đường dẫn hệ thống từ exception.

Tên JSON field không tự tạo tính bảo mật; quan trọng là **nguồn dữ liệu** được phép đưa vào.

## 6. HTTP status và mã lỗi không nên trộn lẫn

| Tình huống | HTTP status điển hình | Mã ứng dụng |
| --- | --- | --- |
| JSON sai cú pháp | 400 | INVALID_JSON |
| JSON mapping không hợp lệ | 400 | INVALID_JSON |
| DTO @Valid thất bại | 400 | VALIDATION_FAILED |
| Query/path/type conversion thất bại | 400 | INVALID_PARAMETER |
| Content-Type không hỗ trợ | 415 | UNSUPPORTED_MEDIA_TYPE |
| Body quá lớn | 413 | PAYLOAD_TOO_LARGE |
| Request không xác thực | 401 | UNAUTHENTICATED |
| Có danh tính nhưng không đủ quyền | 403 | FORBIDDEN |
| Resource không tồn tại | 404 | NOT_FOUND |
| Xung đột trạng thái nghiệp vụ | 409 | CONFLICT |
| Server/lỗi dependency | 5xx | INTERNAL_ERROR |

Một số tổ chức chọn 422 Unprocessable Content cho semantic validation. Điều đó có thể hợp lý nếu API contract thống nhất; **Spring MVC mặc định với @Valid @RequestBody thường sử dụng 400**. Không đổi 400 sang 422 tùy tiện chỉ vì đó là lỗi field.

Đặc biệt, lỗi authorization không được giả làm validation error. Việc trả "userId không tồn tại" hay "tài khoản đó đã đăng ký" có thể làm lộ thông tin định danh; cân nhắc thông điệp chung để tránh user enumeration tùy bối cảnh.

## 7. Mã lỗi cho field: ưu tiên mã ổn định thay vì raw validator code

Jakarta Bean Validation có @NotBlank, @NotNull, @Min, @Email, @Pattern và nhiều constraint tùy biến. Tên annotation hoặc Spring binding code có thể thay đổi khi refactor, vì vậy response không nhất thiết phải phản ánh nguyên tên code nội bộ.

Ví dụ mapping:

| Internal code | Public code | Public message |
| --- | --- | --- |
| NotBlank, NotNull, NotEmpty | REQUIRED | Trường bắt buộc. |
| Email, Pattern | FORMAT | Định dạng không hợp lệ. |
| Min, Max, Positive, Negative | RANGE | Giá trị nằm ngoài phạm vi cho phép. |
| typeMismatch | TYPE | Kiểu dữ liệu không hợp lệ. |
| Mã khác không nằm trong allowlist | INVALID | Giá trị không hợp lệ. |

Không dùng trực tiếp FieldError.getDefaultMessage() khi không kiểm soát template. Custom message có thể đưa tham số như "{value}" hoặc "{validatedValue}" vào; dù là lỗi validation hợp lệ, công khai giá trị lại gây lộ.

Nếu cần đa ngôn ngữ, có thể resolve **public code** qua MessageSource với message templates an toàn. Không interpolate giá trị input vào template.

## 8. Allowlist tên field và nested path

Spring có thể biểu diễn field path lồng nhau:

~~~text
email
shipping.city
shipping.postalCode
items[0].sku
items[0].quantity
items[3].quantity
~~~

Để bảo vệ cấu trúc DTO nội bộ, chỉ trả những path trong hợp đồng API. Ví dụ:

~~~java
private static String publicField(String path) {
    if (Set.of(
            "email",
            "paymentToken",
            "shipping.city",
            "shipping.postalCode",
            "items").contains(path)) {
        return path;
    }

    if (path.matches("items\\[[0-9]{1,3}\\]\\.(sku|quantity)")) {
        return path;
    }

    return "request";
}
~~~

Đoạn này cần import java.util.Set. Nó chỉ cho phép các field cụ thể và các chỉ số list từ 0 tới ba chữ số; những path khác được gộp vào request. Đây là cách giảm khả năng lộ field name không được công bố, không phải một JSON Schema validator.

### 8.1. Có nên trả tên paymentToken?

Một tên field đã công khai trong API request có thể được trả để người dùng sửa input; **nhưng không được trả value**. Trong hệ thống cần giảm khả năng suy luận về sự tồn tại/định dạng token, có thể nhóm lỗi về payment hoặc request thay vì nêu tên chi tiết. Đây là quyết định API/security contract, không có đáp án chung.

### 8.2. Giới hạn chỉ số và độ sâu

Không trả vô hạn path từ payload hàng nghìn phần tử. Một client có thể cố tình gửi list rất dài gây hàng nghìn validation errors. Chọn:

- Số phần tử tối đa được xử lý ở request layer.
- Số lỗi tối đa được trả, ví dụ 20.
- Độ dài path tối đa và những pattern được phép.
- Thứ tự ổn định để tests không chập chờn.
- Cơ chế báo còn lỗi khác nhưng không cần trả mọi field.

Nếu trả tổng số lỗi, cân nhắc liệu số đó có tiết lộ cấu trúc/metadata nhạy cảm; với nhiều API public chỉ cần báo lỗi đã được giới hạn.

## 9. Lỗi global/object-level không có field cụ thể

Không phải ràng buộc nào cũng có tên field. Ví dụ rule "ngày bắt đầu phải trước ngày kết thúc" có thể là class-level constraint, hoặc validation logic kết hợp nhiều field.

Khi getGlobalErrors() có ObjectError, có thể trả:

~~~json
{
  "field": "request",
  "code": "INVALID",
  "message": "Dữ liệu yêu cầu không hợp lệ."
}
~~~

Không tự phát minh tên field cụ thể nếu constraint không chỉ ra field nào sai. Với frontend, có thể hiển thị lỗi tổng quát ở đầu form.

**Tránh trả objectName**, tên Java class, danh sách chi tiết field nội bộ hoặc raw message của ObjectError. Nếu muốn quy tắc nghiệp vụ "date range" có mã riêng, định nghĩa public code có chủ đích và test.

## 10. Spring MVC: lỗi @RequestBody + @Valid

Một controller điển hình:

~~~java
@PostMapping("/api/checkouts")
public ResponseEntity<Map<String, String>> create(
        @Valid @RequestBody CheckoutRequest request) {
    return ResponseEntity.accepted()
            .body(Map.of("status", "accepted"));
}
~~~

Đoạn trên là snippet. Với DTO có Bean Validation, Spring MVC thông thường:

1. Chọn route.
2. Dùng Jackson HttpMessageConverter đọc body thành DTO.
3. Chạy validation cho request body @Valid nếu đã có validation provider.
4. Nếu có lỗi, ném MethodArgumentNotValidException (khi không có BindingResult tương ứng để controller tự xử lý).
5. @RestControllerAdvice hoặc ResponseEntityExceptionHandler xử lý exception.
6. Nếu hợp lệ, controller được gọi.

Không thêm tham số BindingResult sau @Valid @RequestBody chỉ để bỏ qua exception mà không xử lý nó: khi tự nhận BindingResult, controller phải tự bảo đảm validation đã được kiểm tra và không chạy nghiệp vụ với input sai.

Spring MVC từ Spring Framework 6.1 còn có built-in method validation; khi dùng constraint trực tiếp trên controller method parameters, có thể gặp HandlerMethodValidationException thay vì MethodArgumentNotValidException. Cần xét cả hai dạng nếu dự án dùng method-level constraints.

## 11. Spring MVC: phân biệt exception nào được phép dùng field details

- MethodArgumentNotValidException: có BindingResult, có thể lấy FieldError/ObjectError và **sanitize** trước khi trả.
- HandlerMethodValidationException: xảy ra khi method validation được áp dụng; cần chính sách response tương ứng, có thể trả lỗi mức request nếu chưa có mapping public parameter.
- HttpMessageNotReadableException: JSON/body không đọc được; không trả raw cause hoặc JSON fragment.
- HttpMediaTypeNotSupportedException: request media type không hỗ trợ; thường 415.
- MissingServletRequestParameterException: thiếu request parameter; nếu muốn nêu tên, phải allowlist tên public.
- MethodArgumentTypeMismatchException: path/query type mismatch; tránh trả getValue() vì có thể là dữ liệu nhạy cảm.
- ConstraintViolationException: thường liên quan method/service validation; cần phân biệt lỗi client với lỗi lập trình/server và không gán 400 cho mọi trường hợp.

Một exception handler cho tất cả Exception rồi trả 400 là phản mẫu: nó che lỗi máy chủ và làm metrics sai. Xử lý rõ những loại lỗi đầu vào đã biết; giữ 5xx cho những lỗi còn lại.

## 12. Java 17+ và Spring Boot 3.3: project thực hành

Project hoàn chỉnh sau minh họa:

- DTO chứa email, paymentToken, địa chỉ và items lồng nhau.
- Jakarta Bean Validation dùng @Valid để validate nested object và từng phần tử list.
- @RestControllerAdvice chọn field/code/message từ allowlist.
- Không bao giờ gọi getRejectedValue()/getDefaultMessage() khi xây response.
- Có response ổn định, giới hạn 20 lỗi, sắp xếp và loại trùng.
- Có tests xác minh status, mã lỗi và sự **vắng mặt của secret** trong response.

Ví dụ không thực hiện thanh toán thật, không lưu paymentToken và không kết nối database. Tất cả giá trị trong tests là dữ liệu giả dùng để chứng minh chính sách chống rò rỉ. Cần JDK 17+, Gradle Wrapper tương thích Spring Boot 3.3 và tải dependencies từ Maven Central.

Cấu trúc:

~~~text
safe-validation-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/validation/
        SafeValidationApplication.java
        CheckoutRequest.java
        ShippingAddress.java
        CheckoutItem.java
        CheckoutController.java
        FieldIssue.java
        ApiError.java
        ValidationAdvice.java
      resources/
        application.yml
    test/
      java/example/validation/
        CheckoutApiTests.java
~~~

### 12.1. settings.gradle

~~~groovy
rootProject.name = 'safe-validation-demo'
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

spring-boot-starter-web kích hoạt Spring MVC + embedded Tomcat trong cấu hình thông thường. spring-boot-starter-validation cung cấp Hibernate Validator và Jakarta Bean Validation implementation phù hợp. Tương thích phiên bản Gradle/JDK phải theo matrix của Spring Boot 3.3.

### 12.3. application.yml

~~~yaml
spring:
  application:
    name: safe-validation-demo

server:
  port: 8080
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
~~~

Các setting server.error ở Boot 3.3 giúp tránh đưa message/binding details/stack trace vào các error responses mặc định do Boot quản lý. **Chúng không tự vô hiệu hóa một @ExceptionHandler do ứng dụng tự viết trả raw exception message.** Vì thế chính sách sanitize ở code vẫn bắt buộc.

### 12.4. SafeValidationApplication.java

~~~java
package example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeValidationApplication.class, args);
    }
}
~~~

### 12.5. ShippingAddress.java

~~~java
package example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record ShippingAddress(
        @NotBlank String city,
        @NotBlank
        @Pattern(regexp = "[0-9]{5,6}") String postalCode
) {
}
~~~

postalCode cần gồm 5–6 chữ số trong bài demo. Đây là hợp đồng ví dụ, không phải quy tắc chính thức cho mọi quốc gia/vùng. Cả null/blank và format sai cần được kiểm tra; có thể có nhiều FieldError cho cùng một trường, bộ xử lý error phía sau sẽ giới hạn và sắp xếp.

### 12.6. CheckoutItem.java

~~~java
package example.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CheckoutItem(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {
}
~~~

Dùng Integer thay vì int để phân biệt quantity thiếu/null với số 0. @Min(1) không tự từ chối null, nên @NotNull là cần thiết.

### 12.7. CheckoutRequest.java

~~~java
package example.validation;

import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CheckoutRequest(
        @NotBlank @Email String email,
        @NotBlank String paymentToken,
        @NotNull @Valid ShippingAddress shipping,
        @NotEmpty List<@NotNull @Valid CheckoutItem> items
) {
}
~~~

@Valid trên shipping và list elements kích hoạt cascade để kiểm tra các trường lồng nhau. @NotEmpty yêu cầu items không null/rỗng. @NotNull ở mỗi element từ chối phần tử null. Trong ứng dụng có payment flow thật, không đưa raw card number hoặc secret khác vào DTO/response/log nếu không thuộc thiết kế bảo mật và phạm vi tuân thủ phù hợp.

### 12.8. FieldIssue.java

~~~java
package example.validation;

public record FieldIssue(
        String field,
        String code,
        String message
) {
}
~~~

### 12.9. ApiError.java

~~~java
package example.validation;

import java.util.List;

public record ApiError(
        String code,
        String message,
        String errorId,
        List<FieldIssue> errors
) {
}
~~~

Không có field value trong hai record này, vì vậy không thể vô tình serialize rejectedValue chỉ bằng cách đưa Error DTO vào body.

### 12.10. CheckoutController.java

~~~java
package example.validation;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/checkouts")
public class CheckoutController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody CheckoutRequest request) {

        // Chỉ xác nhận đã nhận request hợp lệ; không xử lý payment thật.
        return ResponseEntity.accepted()
                .body(Map.of("status", "accepted"));
    }
}
~~~

Nếu hợp lệ, endpoint trả 202 Accepted với body chỉ có status, **không trả request DTO**. API production cần quyết định 201/202/200 dựa vào nghiệp vụ và xử lý idempotency, không nhất thiết chọn 202 như ví dụ.

### 12.11. ValidationAdvice.java

~~~java
package example.validation;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    private static final int MAX_ERRORS = 20;

    private static final Set<String> PUBLIC_FIELDS = Set.of(
            "email",
            "paymentToken",
            "shipping.city",
            "shipping.postalCode",
            "items"
    );

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> validation(
            MethodArgumentNotValidException ex) {

        List<FieldIssue> issues = new ArrayList<>();

        for (FieldError fieldError
                : ex.getBindingResult().getFieldErrors()) {

            String code = publicCode(fieldError.getCode());

            issues.add(new FieldIssue(
                    publicField(fieldError.getField()),
                    code,
                    publicMessage(code)));
        }

        for (ObjectError ignored
                : ex.getBindingResult().getGlobalErrors()) {
            issues.add(new FieldIssue(
                    "request",
                    "INVALID",
                    "Dữ liệu yêu cầu không hợp lệ."));
        }

        List<FieldIssue> result = issues.stream()
                .distinct()
                .sorted(Comparator.comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .limit(MAX_ERRORS)
                .toList();

        return response(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                result);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException ignored) {
        return response(
                HttpStatus.BAD_REQUEST,
                "INVALID_JSON",
                List.of());
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiError> unsupportedMediaType(
            HttpMediaTypeNotSupportedException ignored) {
        return response(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_MEDIA_TYPE",
                List.of());
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiError> methodValidation(
            HandlerMethodValidationException ex) {

        if (ex.isForReturnValue()) {
            return response(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "INTERNAL_ERROR",
                    List.of());
        }

        return response(
                HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED",
                List.of(new FieldIssue(
                        "request",
                        "INVALID",
                        "Dữ liệu yêu cầu không hợp lệ.")));
    }

    private static String publicField(String raw) {
        if (raw != null && PUBLIC_FIELDS.contains(raw)) {
            return raw;
        }

        if (raw != null
                && raw.matches(
                        "items\\[[0-9]{1,3}\\]\\.(sku|quantity)")) {
            return raw;
        }

        return "request";
    }

    private static String publicCode(String internal) {
        if (internal == null) {
            return "INVALID";
        }

        return switch (internal) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email", "Pattern" -> "FORMAT";
            case "Min", "Max", "Positive", "Negative" -> "RANGE";
            case "typeMismatch" -> "TYPE";
            default -> "INVALID";
        };
    }

    private static String publicMessage(String code) {
        return switch (code) {
            case "REQUIRED" -> "Trường bắt buộc.";
            case "FORMAT" -> "Định dạng không hợp lệ.";
            case "RANGE" -> "Giá trị nằm ngoài phạm vi cho phép.";
            case "TYPE" -> "Kiểu dữ liệu không hợp lệ.";
            default -> "Giá trị không hợp lệ.";
        };
    }

    private static ResponseEntity<ApiError> response(
            HttpStatus status,
            String code,
            List<FieldIssue> issues) {

        String errorId = UUID.randomUUID().toString();

        return ResponseEntity.status(status)
                .cacheControl(CacheControl.noStore())
                .body(new ApiError(
                        code,
                        "Dữ liệu yêu cầu không hợp lệ.",
                        errorId,
                        issues));
    }
}
~~~

### 12.12. Đánh giá bảo mật của code

1. Không gọi getRejectedValue() hoặc getDefaultMessage() khi tạo response.
2. Không trả MethodArgumentNotValidException, ObjectError hoặc FieldError trực tiếp trong body.
3. Tên field được lọc qua PUBLIC_FIELDS và pattern cho chỉ số list.
4. Internal error code được map sang một tập public codes cố định.
5. Message được lấy từ dictionary tĩnh, không có input interpolation.
6. Global error không phản ánh Java objectName hoặc exception message.
7. Kết quả được sort, distinct và limit tối đa 20 để giảm mức độ phình response.
8. HTTP 400, 415 và 500 được phân biệt theo loại exception đã biết.
9. @ExceptionHandler không bắt mọi Exception rồi chuyển thành 400.
10. Header Cache-Control: no-store giúp giảm khả năng error body bị cache, nhưng không thay thế chính sách CDN/proxy log và client-side storage.
11. errorId có thể dùng để đối chiếu vận hành **nếu** hệ thống log cùng ID; ví dụ chỉ sinh ID, chưa cấu hình distributed tracing.
12. Không echo request body trong response thành công.

**Giới hạn chủ đích:** Với HandlerMethodValidationException, project trả một lỗi request-level generic để không cần chuyển tên method parameters nội bộ. Nếu cần per-field cho method validation, hãy dùng visitor API mà Spring Framework cung cấp, ánh xạ từng parameter sang public contract và tuyệt đối không phản ánh rejected values. Khi có exception từ validation của return value, đây là lỗi máy chủ nên handler trả 500 thay vì đổ lỗi cho client.

## 13. Kiểm thử MockMvc: assert không có dữ liệu nhạy cảm

Test quan trọng nhất không chỉ hỏi status 400, mà còn kiểm tra **response body không chứa chuỗi bí mật đã gửi**. Dùng dữ liệu giả nhưng có marker khó trùng.

Tệp src/test/java/example/validation/CheckoutApiTests.java:

~~~java
package example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CheckoutApiTests {

    @Autowired
    MockMvc mvc;

    @Test
    void nestedFieldErrorsDoNotEchoSensitiveValues()
            throws Exception {

        String sensitiveToken = "tok_PRIVATE_example_314";
        String sensitiveEmailInput = "private_input_not_an_email";
        String sensitiveZip = "private_bad_zip_314";

        String json = """
                {
                  "email":"private_input_not_an_email",
                  "paymentToken":"tok_PRIVATE_example_314",
                  "shipping":{
                    "city":"",
                    "postalCode":"private_bad_zip_314"
                  },
                  "items":[
                    {"sku":"","quantity":0}
                  ]
                }
                """;

        MvcResult result = mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors[*].field",
                        hasItem("email")))
                .andExpect(jsonPath("$.errors[*].field",
                        hasItem("shipping.city")))
                .andExpect(jsonPath("$.errors[*].field",
                        hasItem("items[0].quantity")))
                .andReturn();

        String response = result.getResponse()
                .getContentAsString();

        assertFalse(response.contains(sensitiveToken));
        assertFalse(response.contains(sensitiveEmailInput));
        assertFalse(response.contains(sensitiveZip));
        assertFalse(response.contains("rejectedValue"));
        assertFalse(response.contains("stackTrace"));
        assertTrue(response.contains("errorId"));
    }

    @Test
    void validRequestDoesNotEchoPaymentToken()
            throws Exception {

        String json = """
                {
                  "email":"sample@example.test",
                  "paymentToken":"tok_PRIVATE_VALID_159",
                  "shipping":{
                    "city":"Da Nang",
                    "postalCode":"550000"
                  },
                  "items":[
                    {"sku":"BOOK-1","quantity":2}
                  ]
                }
                """;

        MvcResult result = mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status")
                        .value("accepted"))
                .andReturn();

        String response = result.getResponse()
                .getContentAsString();

        assertFalse(response.contains("tok_PRIVATE_VALID_159"));
        assertFalse(response.contains("sample@example.test"));
    }

    @Test
    void malformedJsonHasOnlyGenericError()
            throws Exception {

        String broken = """
                {"email":"private_example",
                 "paymentToken":"tok_PRIVATE_42",
                 "shipping":
                """;

        MvcResult result = mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(broken))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"))
                .andReturn();

        String response = result.getResponse()
                .getContentAsString();

        assertFalse(response.contains("tok_PRIVATE_42"));
        assertFalse(response.contains("private_example"));
    }

    @Test
    void unsupportedMediaTypeRetainsStatus415()
            throws Exception {

        mvc.perform(
                        post("/api/checkouts")
                                .contentType(MediaType.TEXT_PLAIN)
                                .content("secret-forbidden-input"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code")
                        .value("UNSUPPORTED_MEDIA_TYPE"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Khi chạy thật, bộ test phải PASS rồi mới có bằng chứng rằng response không chứa marker. Nội dung bài chỉ cung cấp source và kỳ vọng kiểm thử; không khẳng định Gradle đã được chạy ở môi trường hiện tại.

### 13.1. Vì sao kiểm tra cả valid response?

Rò dữ liệu không chỉ ở error handler. Một controller có thể trả lại request DTO khi thành công, vô tình serialize paymentToken hay các trường nội bộ. Test valid request phải khẳng định response chỉ chứa dữ liệu public cần thiết.

### 13.2. Vì sao test từng nested field?

Nếu chỉ test email, một validator xử lý list có thể tạo error với rejectedValue của items[0].sku. Khi có nested collections, hãy test cả object con, list element và field dùng mật khẩu/token.

## 14. Kiểm thử phản hồi HTTP thực và giới hạn của MockMvc

MockMvc kiểm tra Spring MVC routing, validation, exception handler và serialization trong test application context, nhưng **không mở TCP port thật**. Đối với rủi ro liên quan reverse proxy, header và error handling ở connector, cần thêm integration test với @SpringBootTest(webEnvironment = RANDOM_PORT) và HTTP client thật.

Các mức:

- Unit test publicCode/publicField/publicMessage: nhanh, xác minh dictionary/allowlist.
- @WebMvcTest: kiểm tra controller slice và advice được import đúng.
- @SpringBootTest + @AutoConfigureMockMvc: kiểm tra web layer với context rộng.
- @SpringBootTest(RANDOM_PORT): kiểm tra HTTP listener/connector thật.
- Staging test qua ingress/gateway: kiểm tra proxy cache, logging, WAF và những header lộ dữ liệu.

Với một policy bảo mật, chỉ có unit test cho helper là không đủ; cần **black-box HTTP test** xác nhận không có dữ liệu nhạy cảm trong body, header và các đường lỗi quan trọng.

## 15. Nested paths và danh sách: không để chỉ số thành vector lộ thông tin

Các field paths như items[0].quantity có ích cho form, nhưng chúng cũng có thể làm lộ độ dài danh sách hoặc cấu trúc backend nếu trả quá chi tiết.

Để giảm rủi ro:

1. Chỉ hỗ trợ các tên trường API đã công khai.
2. Giới hạn index, ví dụ 0–999, và số lượng errors trả về.
3. Với path ngoài allowlist, trả field=request.
4. Không dùng regex từ raw input mà không giới hạn độ dài trước đó.
5. Không trả mọi nested object name hoặc inner class name.
6. Nếu API có trường đa hình, định nghĩa public path mapping riêng cho từng variant.
7. Xác minh thứ tự error ổn định để frontend không phụ thuộc vào thứ tự Hibernate Validator trả về.

Trong các form có nhiều items, frontend có thể cần index để tô đỏ đúng dòng. Khi đó index public là một phần hợp đồng API; cần cân nhắc privacy tradeoff thay vì ẩn toàn bộ hoặc xuất vô hạn.

## 16. Field-level error khác lỗi tham số query/path

Ngoài JSON body, một API có thể nhận:

~~~http
GET /api/orders?page=abc&size=2000 HTTP/1.1
Host: localhost:8080
~~~

Khi page yêu cầu int, lỗi type conversion có thể được xử lý bởi MethodArgumentTypeMismatchException. Khi size có @Min/@Max, method validation có thể ném HandlerMethodValidationException trên Spring Framework 6.1+.

Đừng lấy exception.getValue(), raw query string hoặc message rồi trả ra client. Thiết kế public code như INVALID_PARAMETER, field allowlist như page/size và message tĩnh "Tham số không hợp lệ." Nếu không có public mapping đáng tin, trả field=request.

Trường path variable cũng có thể mang dữ liệu nhạy cảm; tránh in raw URL vào response, logs hoặc metrics label. Với những URL chứa token legacy, cần thay design để token không nằm ở path/query khi có thể.

## 17. Thông điệp lỗi và i18n

Frontends thường yêu cầu nhiều ngôn ngữ. Cách an toàn là map public code qua từ điển:

~~~properties
validation.REQUIRED=Trường bắt buộc.
validation.FORMAT=Định dạng không hợp lệ.
validation.RANGE=Giá trị nằm ngoài phạm vi cho phép.
validation.TYPE=Kiểu dữ liệu không hợp lệ.
validation.INVALID=Giá trị không hợp lệ.
~~~

Đây là **ví dụ file messages_vi.properties** cho chiến lược i18n, không phải file phải thêm vào project demo để hoạt động. Trong production, có thể dùng MessageSource để lấy đúng language, nhưng phải:

- Resolve key từ public code cố định.
- Không interpolate rejectedValue hoặc raw exception parameters.
- Giới hạn Locale được phép/khả dụng; có fallback an toàn.
- Không để client tùy ý chọn một expression template phải evaluate từ input.
- Test bản dịch không chứa giá trị đầu vào.

Để client hiển thị câu phù hợp theo UI, cũng có thể trả chỉ code và để frontend dùng dictionary riêng. Khi đó code phải ổn định và được version hóa.

## 18. ProblemDetail và RFC 9457

Spring Framework 6.x hỗ trợ ProblemDetail, ErrorResponse và ResponseEntityExceptionHandler, giúp chuẩn hóa lỗi HTTP theo RFC 9457. Có thể dùng type/title/status/detail/instance và mở rộng properties với danh sách field errors đã được sanitize.

Một cấu trúc minh họa:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request validation failed",
  "errorId": "c8b3913d-5ea7-4a6e-85ed-f2b24fc75ef0",
  "errors": [
    {
      "field": "shipping.city",
      "code": "REQUIRED"
    }
  ]
}
~~~

Không tự động cho rằng ProblemDetail hoặc ResponseEntityExceptionHandler bảo đảm bảo mật. Nếu detail chứa raw exception message, hoặc extensions có rejectedValue, response vẫn có thể làm lộ dữ liệu. Cần lọc dữ liệu trước khi đặt vào ProblemDetail.

**Chọn schema:** ApiError riêng như project mẫu hoặc ProblemDetail đều hợp lý; điều quan trọng là nhất quán với API contract và kiểm thử không rò rỉ.

## 19. WebFlux: cùng nguyên tắc nhưng exception type khác

Trên Spring WebFlux annotated controllers, validation binding cho @Valid @RequestBody thường dẫn tới WebExchangeBindException; method validation có thể dẫn tới HandlerMethodValidationException. Với WebFlux.fn, bodyToMono(Dto.class) chủ yếu decode, và bạn cần chạy Validator.validate(...) rõ ràng nếu muốn validate DTO; exception handler của MVC không được bê nguyên sang WebFlux.fn.

Một đoạn handler WebFlux.fn minh họa:

~~~java
return request.bodyToMono(CreateCheckoutRequest.class)
        .flatMap(dto -> {
            Set<ConstraintViolation<CreateCheckoutRequest>> violations =
                    validator.validate(dto);

            if (!violations.isEmpty()) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(sanitizeViolations(violations));
            }

            return service.process(dto)
                    .flatMap(result -> ServerResponse.ok()
                            .bodyValue(result));
        });
~~~

Snippet này cần CreateCheckoutRequest, validator, sanitizeViolations và service có thật. Nó **không phải source độc lập**. sanitizeViolations phải chỉ trả public field/code/message; không lấy ConstraintViolation.getInvalidValue() hay ConstraintViolation.getMessage() một cách không kiểm soát.

Tương tự, WebExchangeBindException có field errors giống ý tưởng BindingResult, nhưng response nên được tạo bằng cơ chế reactive phù hợp. Khi xử lý JSON decoder errors như ServerWebInputException, không gửi raw cause/Jackson message ra ngoài.

### 19.1. Vì sao không dùng một advice giống hệt cho MVC và WebFlux?

- Class exception và threading/request type khác nhau.
- Reactor Context không phải Servlet ThreadLocal request context.
- MVC dùng HttpMessageConverter cho @RequestBody; WebFlux dùng reactive codecs.
- WebFlux.fn không có @Valid parameter resolver giống annotated controller.
- HTTP response có lifecycle reactive, nên không block()/subscribe() thủ công khi tạo response lỗi.

Có thể chia sẻ **schema ApiError, field allowlist và public-code dictionary** qua common library, nhưng để từng web stack có adapter xử lý exception riêng.

## 20. Security, privacy và việc log lỗi

### 20.1. HTTP response không phải điểm rò duy nhất

Dữ liệu có thể lọt vào:

- Servlet access logs (đặc biệt query string).
- Application log nếu log request DTO.toString().
- APM/tracing tags nếu ghi request body, headers hoặc URL raw.
- HTTP reverse proxy/WAF logs.
- Error tracking software tự thu thập exception context.
- Browser console, analytics và screenshots.
- HTTP response caches ở proxy/client.
- Dead-letter queues hoặc event payloads không kiểm soát.

Ngay cả khi ApiError đã sạch, một global filter bật request/response body logging vẫn có thể làm lộ token. Hãy audit toàn pipeline.

### 20.2. Logging tối thiểu

Một event log an toàn có thể ghi:

~~~text
event=request_validation_failed errorId=<uuid> route=/api/checkouts status=400 code=VALIDATION_FAILED count=4
~~~

Không log email, paymentToken, raw body, rejectedValue hoặc stack trace đối với những 4xx input bình thường. Với 5xx, có thể ghi stack trace nội bộ theo chính sách bảo mật nhưng không gửi cho client.

Ví dụ project tạo errorId nhưng không tự log. Để correlation thực, ứng dụng nên ghi cùng errorId trong log và, nếu đã có hệ thống tracing, gắn nó với traceId/spanId do infrastructure tạo, không tin request header tự gửi là bằng chứng đáng tin.

### 20.3. Cache và proxy

Cache-Control: no-store là lớp phòng vệ hợp lý cho error responses có metadata request, nhưng không bảo đảm proxy/SDK sẽ xóa bản đã log. Cần kiểm soát cấu hình reverse proxy/CDN và các công cụ quan sát.

### 20.4. Quyền riêng tư theo chính sách hệ thống

Dữ liệu đầu vào có thể thuộc chính sách nội bộ hoặc luật bảo vệ dữ liệu áp dụng. Cần tuân thủ retention, access controls, consent/lawful basis và data minimization theo bối cảnh. Kỹ thuật sanitize giảm rủi ro nhưng không tự tạo sự tuân thủ pháp lý.

## 21. Hạn chế lỗi quá nhiều và tấn công làm cạn tài nguyên

Một client có thể gửi request với 50.000 items, mỗi item có nhiều lỗi. Nếu ứng dụng tạo/serialize mọi FieldError, response lớn vừa tốn CPU/memory vừa có thể lộ cấu trúc.

Lớp phòng vệ:

1. Giới hạn request body size ở proxy/server và web framework.
2. Giới hạn collection length, nesting depth và field lengths trước hoặc trong validation theo hợp đồng.
3. Giới hạn lỗi công khai, ví dụ tối đa 20.
4. Sắp xếp/deduplicate để phản hồi ổn định.
5. Dùng rate limits/throttling cho endpoints bị spam lỗi.
6. Hạn chế số field path và độ dài nội dung message.
7. Không log đầy đủ tất cả lỗi và raw values của request quá lớn.
8. Có metrics tổng hợp (count/rate) không dùng raw input làm label.
9. Không biến lỗi 4xx bình thường thành một exception stack log lớn cho mọi request.

Giới hạn số errors trả ra **không nhất thiết giới hạn số constraint violations được validator tính toán**. Nếu cần chống payload cực lớn, phải giới hạn dữ liệu sớm hơn, trước khi deserialize và validate toàn bộ.

## 22. Tránh rò rỉ qua custom validation messages

Các annotation chuẩn có defaultMessage tương đối chung, nhưng một custom constraint có thể tạo thông điệp:

~~~java
context.buildConstraintViolationWithTemplate(
        "Giá trị " + inputValue + " không được chấp nhận")
        .addConstraintViolation();
~~~

Đoạn này minh họa một thiết kế **không an toàn**; cần các biến/context của một ConstraintValidator thật. Nếu error handler trả getDefaultMessage() ra client, inputValue lập tức bị lộ.

Thay vì dùng thông điệp chứa giá trị:

- Custom validator nên phát code ổn định, ví dụ FORMAT_INVALID.
- Public error handler map code sang câu thông báo tĩnh.
- Log sanitized metadata để biết loại lỗi.
- Nếu frontend cần giới hạn như min/max để hiển thị, chỉ đưa **tham số cấu hình không nhạy cảm** đã allowlist, không đưa dữ liệu user đang nhập.
- Test với marker secret để phát hiện thông điệp bị interpolate không mong muốn.

Không cho rằng getDefaultMessage() an toàn ở mọi team, vì nhiều developer có thể định nghĩa validator khác nhau theo thời gian.

## 23. Tránh user enumeration và lộ logic phân quyền

Ngay cả một phản hồi không chứa rejectedValue vẫn có thể làm lộ dữ liệu qua **sự khác nhau về mã hoặc thông điệp**.

Ví dụ:

- "Email này đã tồn tại" chỉ trả khi user có tài khoản.
- "Mã khôi phục không đúng" khác "Tài khoản không tồn tại".
- "Số thẻ này thuộc người khác" tiết lộ liên kết tài khoản.
- "Bạn không có quyền tenant X" tiết lộ một tenant nội bộ.

Với các endpoint nhạy cảm, có thể cần cùng status/message, rate limiting và timing policy để tránh enumeration. Đó là quyết định theo threat model; đừng áp dụng quy tắc công khai field-level lỗi quá chi tiết cho login, recovery hay authorization.

Một API thông thường có thể chỉ rõ field email sai format, nhưng không nhất thiết xác nhận email đã đăng ký. Phân biệt **format validation** với **xác thực danh tính hoặc sự tồn tại của tài khoản**.

## 24. Những sai lầm thường gặp

| Sai lầm | Nguy cơ | Cách sửa |
| --- | --- | --- |
| Trả FieldError trực tiếp | Lộ rejectedValue, codes, objectName | Map sang FieldIssue public |
| Trả getRejectedValue() | Lộ token/PII | Tuyệt đối không echo input |
| Trả getDefaultMessage() vô điều kiện | Custom validator có thể chứa giá trị | Dictionary public code cố định |
| Trả exception.getMessage() | Lộ JSON fragment/class/path | Trả thông điệp chung |
| Trả request DTO khi validation fail | Lộ mọi trường | Tạo ApiError độc lập |
| Trả stackTrace để frontend debug | Lộ internals | Chỉ log nội bộ có bảo vệ |
| Dùng field path thô | Lộ tên property backend | Allowlist public fields |
| Không giới hạn errors | Phình response, quá tải | Limit/sort/dedup |
| Một advice bắt mọi Exception -> 400 | Che lỗi máy chủ | Phân loại exceptions và status |
| Ép 415 thành INVALID_JSON 400 | Sai media type contract | Giữ 415 |
| Trả tất cả ConstraintViolation.getInvalidValue() | Lộ dữ liệu lồng nhau | Không lấy invalidValue |
| Log raw request body | Dữ liệu vẫn lộ qua logs | Redaction/disable raw-body logging |
| Tạo errorId nhưng không log tương ứng | Khó điều tra | Kết nối logs/traces theo policy |
| Chỉ test status 400 | Không phát hiện secret bị echo | Assert không chứa markers |
| @Valid thiếu cascade | Bỏ lọt nested errors | @Valid ở object/list element |
| Test một trường top-level | Bỏ sót lỗi nested list | Test shipping/items/missing/null |
| Dùng 422/400 tùy hứng | Client khó xử lý | Định nghĩa API contract thống nhất |
| Phản hồi login quá chi tiết | User enumeration | Generic error và rate limit |

## 25. Checklist review trước production

Một API validation response được xem là đáng tin hơn khi đáp ứng các kiểm tra:

- [ ] Mỗi endpoint có documented request DTO và public fields.
- [ ] Không serializer nào nhận raw BindingResult/FieldError/ObjectError trong error response.
- [ ] Không dùng rejectedValue/invalidValue trong response hay public logs.
- [ ] getDefaultMessage/exception.getMessage không được xuất trực tiếp ra client.
- [ ] Public error codes và messages chỉ đến từ allowlist/dictionary.
- [ ] Nested field paths có allowlist, giới hạn index và max errors.
- [ ] 400/401/403/404/409/413/415/5xx được phân biệt hợp đồng.
- [ ] Method validation và JSON decoding errors có safe fallback.
- [ ] Response không chứa raw request, email, token, password hoặc address markers.
- [ ] Response thành công cũng không echo nhầm credential.
- [ ] Proxy/CDN/ingress và observability không log request/response nhạy cảm.
- [ ] Có rate limits và payload size constraints cho validation abuse.
- [ ] errorId/log correlation thực sự hoạt động theo trace/metadata an toàn.
- [ ] Có regression tests cho các lỗi top-level, nested, list và malformed JSON.
- [ ] Nếu dùng ProblemDetail, mọi extension properties đều được sanitize.
- [ ] Nếu dùng i18n, template không interpolate raw input.
- [ ] Security review xem xét user enumeration, không chỉ dữ liệu trong body.

Không một checklist nào thay thế được threat modeling và test trên deployment thực, nhưng các mục trên tạo một ranh giới kỹ thuật rõ giữa dữ liệu request và dữ liệu được phép công khai.

## 26. Bài thực hành tổng hợp

**Bài 1 — Thử lỗi nested:** Dùng project phần 12. Gửi paymentToken giả, email sai, shipping.city rỗng và items[0].quantity=0. Chụp status, danh sách field và xác nhận không có token/email/zip markers trong response.

**Bài 2 — Tên field không công khai:** Bổ sung một field nội bộ chỉ dùng trong validation, cố tình tạo FieldError; xác minh publicField trả request thay vì internal name.

**Bài 3 — Đổi message:** Tạo custom constraint với message có input giả, kiểm tra handler vẫn chỉ trả dictionary message tĩnh. Sau đó sửa constraint để chính nội bộ cũng không đưa value vào message.

**Bài 4 — Giới hạn errors:** Tạo request có nhiều list elements sai; xác minh tối đa 20 lỗi trong response, không vượt body-size budget. Phân biệt giới hạn response với giới hạn payload validation.

**Bài 5 — JSON lỗi:** Gửi JSON syntax lỗi, enum không hợp lệ, contentType text/plain và body quá lớn. So sánh HTTP 400/415/413; nếu môi trường xử lý khác, điều chỉnh layer mapping đúng cách.

**Bài 6 — Query validation:** Thêm endpoint GET có @Min/@Max trên parameters, xác minh behavior của HandlerMethodValidationException; không trả rejected parameter value.

**Bài 7 — ProblemDetail:** Thay ApiError bằng ProblemDetail chuẩn RFC 9457, thêm errors đã sanitize và test JSON không có raw exception messages.

**Bài 8 — WebFlux:** Viết endpoint tương đương dùng WebFlux annotated controller hoặc WebFlux.fn, xử lý WebExchangeBindException/Validator phù hợp, giữ cùng public error contract.

**Bài 9 — Logs:** Kiểm tra cấu hình gateway, tracing và application logs khi gửi marker nhạy cảm; không để marker xuất hiện trong bất kỳ log output được sử dụng cho vận hành.

**Bài 10 — Quy trình triển khai:** Chạy trên staging và integration tests với HTTP thật, ghi version Spring Boot, body error chuẩn, chính sách rate limiting và hành vi khi client cũ gửi thêm field.

Đạt yêu cầu khi có mã nguồn, bộ test thành công, HTTP responses thực tế và một bản đối chiếu bằng chứng không rò rỉ. Không báo test PASS nếu chưa chạy lệnh kiểm thử trên môi trường tương ứng.

## 27. Câu hỏi tự đánh giá

1. FieldError.getRejectedValue() có thể chứa những nhóm thông tin gì?
2. Tại sao getDefaultMessage() không mặc nhiên an toàn?
3. Lỗi JSON mapping và Bean Validation khác nhau ở tầng nào?
4. Khi nào MethodArgumentNotValidException xuất hiện trên MVC?
5. HandlerMethodValidationException liên quan trường hợp gì?
6. Vì sao phải phân biệt lỗi method return-value validation với lỗi client?
7. Khi nào một lỗi nên được trả ở field=request thay vì path cụ thể?
8. Vì sao cần whitelist field paths, nhất là nested arrays?
9. Code và message trong response cần ổn định ra sao khi đổi implementation validator?
10. Vì sao chỉ test HTTP status 400 là chưa đủ?
11. Vì sao cần test cả response thành công với paymentToken?
12. Cache-Control: no-store có giải quyết hoàn toàn rò dữ liệu qua logs không?
13. Lỗi 415 khác lỗi 400 thế nào?
14. Vì sao không dùng catch(Exception) để chuyển mọi exception thành validation failure?
15. ProblemDetail có tự sanitize extension properties không?
16. Nếu một custom validator nhúng value vào message, tầng response nên xử lý thế nào?
17. Việc trả "email đã tồn tại" có thể lộ thông tin gì dù không echo email?
18. Khi nào WebFlux cần WebExchangeBindException thay vì MVC advice?
19. Tại sao WebFlux.fn bodyToMono không đủ để thay thế explicit validation?
20. Nếu danh sách chứa hàng nghìn items sai, cần bảo vệ resource ở những tầng nào?
21. errorId khác traceId và có cần liên hệ chúng không?
22. Làm sao bảo vệ cả response body, headers, app logs và reverse proxy logs?

## 28. Tài liệu chính thức

- [Spring Framework 6.1 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-validation.html): @Valid, binding, MethodArgumentNotValidException và method validation.
- [Spring Framework — MVC Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ErrorResponse, ProblemDetail, ResponseEntityExceptionHandler và MessageSource.
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): @RestControllerAdvice và @ExceptionHandler.
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/validation/BindingResult.html): field/global errors và nguy cơ rejected values.
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): WebExchangeBindException và HandlerMethodValidationException.
- [Spring Boot 3.3 — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): tích hợp Jakarta Bean Validation.
- [Jakarta Bean Validation 3.0](https://jakarta.ee/specifications/bean-validation/3.0/): constraints, cascaded validation và property paths.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): mẫu error representation nhất quán.

**Kết luận:** phản hồi lỗi theo trường là một hợp đồng công khai, không phải bản sao BindingResult. Hãy đọc dữ liệu validation từ framework, **chỉ xuất các field path/code/message đã được cho phép**, loại bỏ mọi rejected input, giới hạn kích thước và kiểm thử không rò rỉ. Khi tách rõ ranh giới này, API vừa hữu ích cho frontend vừa an toàn hơn trước các nguy cơ lộ dữ liệu.
