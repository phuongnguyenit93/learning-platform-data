# Validation là gì và vai trò bảo vệ hợp đồng dữ liệu

Validation (kiểm tra tính hợp lệ) là quá trình đối chiếu dữ liệu với những quy tắc đã công bố trước khi hệ thống sử dụng dữ liệu đó. Trong ứng dụng Spring Framework, validation là một phần của **hợp đồng dữ liệu (data contract)** giữa bên gửi dữ liệu và bên nhận: bên nhận xác định thông tin nào bắt buộc, định dạng và miền giá trị nào được phép, và điều gì xảy ra khi yêu cầu vi phạm hợp đồng.

Ví dụ, API đăng ký tài khoản có thể quy định tên phải có 2–60 ký tự, email phải có dạng hợp lệ và tuổi ít nhất 18. Nếu thiếu kiểm tra, một yêu cầu thiếu tuổi hoặc chứa giá trị không hợp lệ có thể lọt vào tầng nghiệp vụ, gây lỗi khó hiểu hoặc khiến dữ liệu sai được lưu xuống cơ sở dữ liệu. Validation giúp phát hiện vi phạm sớm và trả về thông tin lỗi có cấu trúc.

## 1. Hợp đồng dữ liệu bảo vệ điều gì?

Hợp đồng dữ liệu không chỉ là danh sách thuộc tính của một Java class. Nó còn mô tả ý nghĩa và các bất biến mà hệ thống hứa sẽ duy trì.

| Thành phần hợp đồng | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Sự hiện diện | Trường có bắt buộc không? | `age` không được `null` |
| Kiểu và khả năng chuyển đổi | Giá trị có thể được biểu diễn đúng kiểu không? | `age` phải là số nguyên |
| Định dạng | Chuỗi có thỏa mẫu cần thiết không? | `email` có định dạng email |
| Độ dài và miền giá trị | Giá trị được phép nằm trong khoảng nào? | Tên dài 2–60 ký tự; tuổi ≥ 18 |
| Quan hệ giữa các trường | Các giá trị có nhất quán với nhau không? | `startDate` không muộn hơn `endDate` |
| Quy tắc theo ngữ cảnh | Dữ liệu có hợp lệ tại thời điểm thao tác không? | Không đăng ký trùng email đã được sử dụng |
| Phản hồi khi sai | Bên gửi sẽ biết sửa yêu cầu ra sao? | HTTP 400 và danh sách trường vi phạm |

Từ góc nhìn thiết kế API, hợp đồng cần đủ rõ để client tạo dữ liệu đúng, backend bảo vệ các giả định nghiệp vụ, và kiểm thử có thể kiểm chứng cả trường hợp hợp lệ lẫn không hợp lệ. Chỉ khai báo một kiểu Java, ví dụ `String email`, chưa tự xác lập điều kiện bắt buộc hay độ dài tối đa.

**Validation không đồng nghĩa với:**

- **Parsing/deserialization:** đọc JSON hoặc chuyển chuỗi thành số, ngày, enum. JSON sai cú pháp có thể bị từ chối trước khi Bean Validation chạy.
- **Data binding:** gán dữ liệu đầu vào vào đối tượng hoặc thuộc tính Java. Binding có thể báo lỗi chuyển kiểu; validation kiểm tra các ràng buộc trên đối tượng đã hình thành.
- **Chuẩn hóa/sanitization:** cắt khoảng trắng, chuyển chữ hoa/thường hoặc làm sạch nội dung. Những phép biến đổi này cần chính sách riêng và không được âm thầm thay đổi ý nghĩa dữ liệu.
- **Authorization:** kiểm tra người dùng có quyền thực hiện hành động hay sửa tài nguyên đó không.
- **Bảo vệ SQL injection/XSS:** vẫn cần truy vấn có tham số, mã hóa đầu ra phù hợp ngữ cảnh và các cơ chế bảo mật riêng.

Nói cách khác, dữ liệu “qua được validation” chỉ chứng minh nó thỏa **những điều kiện đã kiểm tra**, không chứng minh nó an toàn trong mọi ngữ cảnh hoặc mọi quy tắc nghiệp vụ đều đã được thỏa mãn.

## 2. Validation nằm ở đâu trong luồng xử lý Spring?

Với một REST endpoint nhận JSON trong Spring MVC, luồng khái quát là:

~~~text
HTTP request
    |
    v
Đọc HTTP body và deserialize JSON (@RequestBody / HttpMessageConverter)
    |
    v
Tạo đối tượng request DTO
    |
    v
Kiểm tra các ràng buộc (@Valid, @Validated, method validation nếu phù hợp)
    |
    +---- Không hợp lệ ---> Trả lỗi có thể xử lý, thường là HTTP 400
    |
    v
Controller -> Service -> tầng truy cập dữ liệu -> Database
~~~

Luồng thực tế phụ thuộc loại tham số, cấu hình và cơ chế validation được kích hoạt. Với dữ liệu form/query được gán bằng `@ModelAttribute`, Spring dùng cơ chế data binding; kết quả binding và validation có thể được thu qua `BindingResult`. Với `@RequestBody`, JSON thường được chuyển thành object trước khi các constraint trên object được kiểm tra.

Các lớp bảo vệ hỗ trợ lẫn nhau:

1. **Ranh giới HTTP/controller:** từ chối hình dạng, trường bắt buộc và giá trị bất hợp lệ; giúp API trả lỗi nhất quán trước khi gọi nghiệp vụ.
2. **Service/domain:** kiểm tra quy tắc phụ thuộc trạng thái hoặc nhiều tài nguyên, chẳng hạn hạn mức đặt chỗ hoặc quyền chuyển trạng thái.
3. **Persistence/database:** ràng buộc `NOT NULL`, `CHECK`, `FOREIGN KEY`, `UNIQUE` bảo đảm tính toàn vẹn khi ghi, kể cả khi dữ liệu đến từ job, queue hoặc luồng khác.
4. **Consumer khác ngoài HTTP:** phải kích hoạt validation tại điểm nhận tương ứng; annotation trên DTO không tự khiến mọi đối tượng được kiểm tra mỗi khi được khởi tạo.

Validation ở biên giúp phát hiện lỗi sớm, nhưng không thay thế kiểm tra nghiệp vụ hay ràng buộc ở database. Ví dụ, chỉ gọi “kiểm tra email chưa tồn tại” trong controller vẫn có race condition khi hai yêu cầu đồng thời tạo cùng email; ràng buộc `UNIQUE` ở database là tuyến bảo vệ cuối.

## 3. Spring cung cấp cơ chế nào?

### 3.1. Jakarta Bean Validation

Spring Framework hỗ trợ chuẩn **Jakarta Bean Validation**. Ta khai báo quy tắc bằng annotation trên field, property, record component hoặc tham số tùy trường hợp; một provider như Hibernate Validator thực thi các quy tắc đó. Với Spring Boot 3.x, thường thêm dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Các import dùng namespace `jakarta.validation.*`. Tài liệu cũ của Spring Boot 2.x có thể dùng `javax.validation.*`; không trộn hai hệ namespace khi làm việc với Boot 3.x.

| Constraint | Ý nghĩa chính | Ghi nhớ |
| --- | --- | --- |
| `@NotNull` | Giá trị khác `null` | Không cấm chuỗi rỗng hoặc toàn khoảng trắng |
| `@NotEmpty` | Chuỗi/collection/array/map không rỗng và không null | Chuỗi chỉ chứa khoảng trắng vẫn có thể đạt |
| `@NotBlank` | Chuỗi không null và có ít nhất một ký tự không phải khoảng trắng | Phù hợp cho tên, mô tả bắt buộc |
| `@Size(min, max)` | Giới hạn độ dài/kích thước | Không dùng để kiểm tra miền của một số |
| `@Min` / `@Max` | Giới hạn giá trị số | Ghép `@NotNull` nếu giá trị bắt buộc |
| `@Positive` / `@PositiveOrZero` | Số dương / số không âm | Chọn theo hợp đồng cụ thể |
| `@Email` | Kiểm tra định dạng email theo validator | Không xác nhận mailbox tồn tại hay gửi thư được |
| `@Pattern(regexp = ...)` | Chuỗi khớp biểu thức chính quy | Không thay thế parser cho cấu trúc dữ liệu phức tạp |
| `@Past` / `@Future` | Giá trị thời gian thuộc quá khứ/tương lai | Phải xét múi giờ và thời điểm đánh giá |

Đa số constraint kiểm tra nội dung như `@Email`, `@Size` hay `@Min` cho phép `null`. Nếu trường bắt buộc, thêm `@NotNull` hoặc constraint không cho phép null như `@NotBlank`. Nhờ vậy, “bắt buộc” và “hợp lệ khi có giá trị” được khai báo độc lập, dễ hiểu.

### 3.2. `@Valid`, `@Validated` và thực sự kích hoạt kiểm tra

- `@Valid` là annotation chuẩn Jakarta dùng để yêu cầu kiểm tra một object và cascade xuống đối tượng lồng nhau được đánh dấu `@Valid`. Trên tham số DTO của controller, nó là cách thông dụng để kích hoạt validation của request.
- `@Validated` là annotation của Spring hỗ trợ chọn **validation groups** và được dùng trong một số cơ chế Spring method validation. Không cần groups thì phần lớn bài toán DTO đơn giản chỉ cần `@Valid`.
- Ràng buộc trực tiếp trên **tham số hoặc giá trị trả về của method** là phạm vi method validation, có cách thực thi và ngoại lệ khác với validation của một DTO.
- Chỉ đặt `@NotBlank` lên field mà không có lần gọi validator tương ứng sẽ không đảm bảo bất kỳ kiểm tra nào xảy ra.

Trong Spring MVC từ Framework 6.1, cơ chế method validation tích hợp có thể xử lý các constraint đặt trực tiếp lên tham số method. Khi đó, lỗi thường xuất hiện qua `HandlerMethodValidationException`; còn trường hợp kiểm tra riêng DTO `@Valid @RequestBody` thường là `MethodArgumentNotValidException`. Phải chọn cách xử lý exception theo cơ chế thực sự được kích hoạt, và lưu ý `@Validated` đặt ở cấp class của controller có thể dùng cơ chế AOP khác với hỗ trợ MVC tích hợp.

Spring còn có giao diện `org.springframework.validation.Validator`, `Errors`, `BindingResult` và `DataBinder`. Đây là API validation/binding của Spring; `LocalValidatorFactoryBean` có thể làm adapter giữa nó với Jakarta Bean Validation. Hai hướng có thể phối hợp, nhưng cần phân biệt interface `org.springframework.validation.Validator` với `jakarta.validation.Validator`.

## 4. Ví dụ: bảo vệ hợp đồng đăng ký

Giả sử endpoint chỉ kiểm tra một yêu cầu đăng ký, **chưa ghi dữ liệu**. Quy tắc: tên 2–60 ký tự, email bắt buộc và đúng dạng, tuổi từ 18 trở lên. Các lớp dưới đây dùng Java 17+, Spring Boot 3.x (Spring Framework 6.x) và hai dependency ở mục 3.

Tạo `src/main/java/com/example/validationdemo/ValidationDemoApplication.java`:

~~~java
package com.example.validationdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

Tạo `src/main/java/com/example/validationdemo/RegistrationRequest.java`:

~~~java
package com.example.validationdemo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RegistrationRequest(
        @NotBlank(message = "Tên là bắt buộc")
        @Size(min = 2, max = 60, message = "Tên phải dài từ 2 đến 60 ký tự")
        String name,

        @NotBlank(message = "Email là bắt buộc")
        @Email(message = "Email không đúng định dạng")
        String email,

        @NotNull(message = "Tuổi là bắt buộc")
        @Min(value = 18, message = "Tuổi tối thiểu là 18")
        Integer age
) {}
~~~

Tạo `src/main/java/com/example/validationdemo/RegistrationController.java`:

~~~java
package com.example.validationdemo;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping("/check")
    public Map<String, String> check(@Valid @RequestBody RegistrationRequest request) {
        return Map.of("status", "accepted", "email", request.email());
    }
}
~~~

Các lớp là mã Java hoàn chỉnh trong **một dự án Spring Boot đã cấu hình plugin, Java toolchain và dependency** phù hợp. Chạy ứng dụng bằng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Khi dùng `@Valid` trên tham số `@RequestBody`, Spring yêu cầu validator kiểm tra DTO trước khi gọi thân method. Đối tượng `RegistrationRequest` chỉ được trả về “accepted” trong ví dụ này; đó **không phải** xác nhận đã đăng ký tài khoản thành công.

Gửi request hợp lệ:

~~~http
POST /registrations/check HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"name":"An","email":"an@example.com","age":21}
~~~

Kết quả: HTTP 200; response JSON có `status` là `"accepted"` và `email` là `"an@example.com"`. Thứ tự các khóa JSON không phải một phần của hợp đồng trong ví dụ.

Gửi request vi phạm đồng thời ba điều kiện:

~~~http
POST /registrations/check HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"name":" ","email":"khong-phai-email","age":16}
~~~

Kết quả: thường là HTTP 400 trong Spring MVC, không vào thân `check(...)`. Các lỗi tương ứng gồm tên trống, email sai dạng và tuổi dưới 18. **Body lỗi mặc định không cố định**: nó phụ thuộc phiên bản Spring Boot, thiết lập Problem Details và exception handler của ứng dụng; không nên viết test phụ thuộc vào một JSON lỗi mà mình chưa định nghĩa.

Để quy định hợp đồng lỗi API của chính ứng dụng, có thể bổ sung `src/main/java/com/example/validationdemo/ValidationErrorHandler.java`:

~~~java
package com.example.validationdemo;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationErrorHandler {

    public record FieldIssue(String field, String message) {}

    public record ErrorPayload(String code, List<FieldIssue> errors) {}

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorPayload> onInvalidRequest(
            MethodArgumentNotValidException exception) {

        List<FieldIssue> errors = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(), error.getDefaultMessage()))
                .toList();

        return ResponseEntity.badRequest()
                .body(new ErrorPayload("VALIDATION_FAILED", errors));
    }
}
~~~

Khi lỗi thuộc kiểu `MethodArgumentNotValidException`, handler trên trả JSON theo dạng:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "age", "message": "Tuổi tối thiểu là 18"}
  ]
}
~~~

Đây là **ví dụ hình dạng dữ liệu**, không phải khẳng định request ba lỗi sẽ chỉ có một lỗi hoặc luôn có thứ tự này. Trong hệ thống thật, nên thống nhất mã lỗi, thông điệp cho client, localization và correlation ID; không đưa stack trace, thông tin nội bộ hoặc giá trị nhạy cảm vào phản hồi. Handler trên chỉ xử lý một loại exception; lỗi parse/binding và method validation cần cơ chế xử lý tương ứng nếu muốn cùng một định dạng.

## 5. Cùng là “request sai”, vì sao có nhiều loại lỗi?

| Trường hợp | Nơi phát hiện thường gặp | Hướng xử lý |
| --- | --- | --- |
| JSON thiếu dấu ngoặc, hoặc `age` là chuỗi không thể chuyển sang `Integer` | HTTP message conversion, thường `HttpMessageNotReadableException` | HTTP 400; thông báo body/cú pháp không hợp lệ |
| DTO được deserialize nhưng `name` trắng hay `age < 18` | Bean Validation trên `@Valid @RequestBody`, thường `MethodArgumentNotValidException` | HTTP 400; trả danh sách vi phạm |
| Form `@ModelAttribute` có field binding/validation lỗi | `BindingResult`/`Errors` nếu khai báo ngay sau tham số được bind | Controller có thể tự xử lý lỗi |
| Constraint trên tham số method, ví dụ `@RequestParam @Min(18)` | Spring MVC method validation (Framework 6.1+), thường `HandlerMethodValidationException` | Phân loại lỗi đầu vào và trả lỗi phù hợp |
| Email đã đăng ký hoặc thao tác xung đột trạng thái | Service/domain và/hoặc DB constraint | Chọn phản hồi theo hợp đồng nghiệp vụ, thường HTTP 409 cho xung đột |
| Người gọi thiếu quyền | Tầng security/authorization | HTTP 401 hoặc 403 theo tình huống |

Trong một số thiết kế API, nhóm lỗi ngữ nghĩa có thể dùng HTTP 422 thay cho 400, nhưng phải có chính sách nhất quán. Không nên gộp tất cả thành “validation failed”, vì client cần phân biệt sai dữ liệu, xung đột nghiệp vụ và thiếu quyền.

Nếu muốn chủ động xử lý lỗi trên form, `BindingResult` phải đứng **ngay sau** đối tượng được bind/validate, ví dụ:

~~~java
@PostMapping("/profiles")
public String saveProfile(
        @Valid @ModelAttribute ProfileForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "profile-form";
    }
    return "profile-success";
}
~~~

Đoạn trên minh họa **chữ ký controller**, giả định đã có class `ProfileForm` và các view tương ứng; nó không phải một chương trình độc lập. Khi đã nhận `BindingResult`, code phải thật sự xử lý lỗi. Không được xem việc Spring không ném exception là dữ liệu đã hợp lệ.

## 6. Chọn vị trí và phạm vi ràng buộc đúng

**DTO đầu vào là ranh giới hợp đồng.** Ưu tiên một request DTO với các trường được phép nhận, thay vì bind trực tiếp client vào persistence entity chứa cả `id`, `role`, `status` hoặc trường nội bộ. Cách này giúp tránh cập nhật ngoài ý muốn (mass assignment), giữ API độc lập hơn với schema lưu trữ.

**Phân biệt tạo mới và cập nhật.** Tạo mới có thể yêu cầu email, nhưng PATCH có thể cho phép bỏ qua email. Không tái sử dụng mù quáng cùng `@NotNull` cho cả hai request. Dùng DTO riêng cho create/update hoặc validation groups có chủ đích; phân biệt rõ “không gửi trường” với “gửi null” khi định nghĩa PATCH.

**Đối tượng lồng nhau cần cascade khi cần.** Ví dụ, nếu `RegistrationRequest` chứa `AddressRequest address`, constraint trên `AddressRequest` chỉ được kiểm tra theo đường đi đó khi khai báo cascade `@Valid` phù hợp. Kết hợp `@NotNull` nếu chính thuộc tính `address` là bắt buộc: `@Valid` không có nghĩa “khác null”.

**Kiểm tra nhiều trường và trạng thái động cần thiết kế riêng.** Điều kiện `startDate <= endDate` có thể đặt ở class-level custom constraint hoặc domain service. “Email chưa tồn tại” là quy tắc thay đổi theo trạng thái hệ thống: xác minh tại service, kết hợp unique constraint trong database để chịu được truy cập đồng thời. Không nên tạo validator gọi database tùy tiện cho mọi DTO rồi coi kết quả đó thay thế giao dịch và cơ chế toàn vẹn dữ liệu.

**Giữ hợp đồng ổn định và có thể quan sát.** Chuẩn hóa mã lỗi, ghi log vừa đủ để chẩn đoán, không log mật khẩu/token/PII tùy tiện. Thông điệp hiển thị cho người dùng có thể dịch ngôn ngữ; mã lỗi ổn định để client xử lý lập trình. Khi thay đổi constraint, xem xét tương thích ngược vì client cũ có thể đang gửi giá trị vốn được chấp nhận trước đây.

## 7. Kiểm thử nên chứng minh điều gì?

Một bộ kiểm thử HTTP hoặc controller cần có ít nhất các kịch bản sau:

| Dữ liệu đầu vào | Kỳ vọng |
| --- | --- |
| `name="An"`, email đúng dạng, `age=21` | Thành công (200 ở endpoint kiểm tra mẫu) |
| Thiếu `name` hoặc `name="  "` | Bị từ chối do `@NotBlank` |
| `name` chỉ một ký tự | Bị từ chối do `@Size(min=2)` |
| Thiếu `email` hoặc email sai dạng | Bị từ chối theo constraint tương ứng |
| Thiếu `age` hoặc `age=17` | Bị từ chối do `@NotNull` hoặc `@Min` |
| `age="abc"` hoặc JSON không hợp lệ | Bị từ chối tại bước chuyển dữ liệu trước Bean Validation |
| Nhiều trường cùng vi phạm | Có thể quan sát đầy đủ lỗi, không phụ thuộc thứ tự danh sách |
| Request hợp lệ nhưng vi phạm quy tắc động | Service/DB vẫn từ chối đúng nghiệp vụ |

Với Spring Boot, có thể dùng `MockMvc` để xác nhận HTTP status và nội dung lỗi do **handler của ứng dụng** trả về. Ngoài ra cần kiểm thử service và database cho quy tắc nghiệp vụ; một test controller 400 không chứng minh được tính toàn vẹn khi có nhiều nguồn ghi hoặc truy cập đồng thời.

## 8. Những sai lầm phổ biến

1. **Quên dependency validator.** Có `@Valid` và annotation constraint nhưng không có provider phù hợp, dẫn đến kỳ vọng kiểm tra không được đáp ứng.
2. **Nhầm annotation với việc thực thi.** Tạo DTO bằng `new` không tự chạy Bean Validation; phải gọi `jakarta.validation.Validator` hoặc đi qua điểm tích hợp đã kích hoạt validation.
3. **Dùng sai constraint.** `@NotNull` không bác chuỗi rỗng; `@Size` không kiểm tra giá trị số; `@Email` không đảm bảo địa chỉ email thực sự sử dụng được.
4. **Dùng primitive cho trường có ý nghĩa “thiếu”.** `int` không biểu diễn null; với request có trường tùy chọn hoặc bắt buộc cần phân biệt thiếu giá trị, cân nhắc `Integer` và `@NotNull`.
5. **Không cascade validation cho dữ liệu lồng nhau.** Constraint ở object con có thể bị bỏ qua vì thiếu `@Valid` tại liên kết phù hợp.
6. **Chỉ kiểm tra ở controller.** Import, scheduled job, message consumer hoặc thao tác nội bộ có thể bỏ qua controller; service và database vẫn phải giữ bất biến quan trọng.
7. **Trả lỗi mơ hồ hoặc lộ chi tiết nội bộ.** Client cần biết trường và quy tắc nào vi phạm, nhưng không cần stack trace, SQL statement hay dữ liệu nhạy cảm.
8. **Coi dữ liệu hợp lệ là đã được cấp quyền.** Validation không chứng minh chủ thể được sửa tài nguyên, cũng không loại bỏ nhu cầu giao dịch hoặc chống cạnh tranh ghi.

## 9. Tự kiểm tra kiến thức

- Một request chứa JSON lỗi cú pháp khác gì request JSON hợp lệ nhưng vi phạm `@NotBlank`?
- Vì sao thường phải ghép `@NotNull` với `@Min`?
- `@Valid` khác gì `@Validated`, và khi nào cần method validation?
- Tại sao “email chưa tồn tại” cần service và unique constraint trong database?
- Nếu cùng DTO đi vào controller và message consumer, nơi nào thực sự kích hoạt validation?
- API nên trả thông tin nào để client sửa dữ liệu mà không lộ thông tin nội bộ?

**Ghi nhớ:** Data contract xác định điều hệ thống chấp nhận; validation thực thi phần ràng buộc kiểm tra được tại ranh giới thích hợp; nghiệp vụ, phân quyền và database tiếp tục bảo vệ những bất biến vượt quá một DTO. Một ứng dụng Spring đáng tin cậy cần cả ba lớp: **hợp đồng rõ ràng, kiểm tra ở các điểm nhận dữ liệu, và bảo vệ tính toàn vẹn khi sử dụng/lưu dữ liệu**.

### Tài liệu tham khảo

- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
