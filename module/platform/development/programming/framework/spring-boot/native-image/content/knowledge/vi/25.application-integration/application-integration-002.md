# Jackson, Bean Validation và xử lý lỗi với các kiểu chỉ xuất hiện lúc chạy

Ứng dụng Spring Boot thường nhận JSON từ HTTP, chuyển JSON thành DTO, kiểm tra dữ liệu rồi mới gọi nghiệp vụ. Với GraalVM Native Image, chuỗi xử lý này cần được xem xét kỹ khi một kiểu dữ liệu chỉ được chọn sau khi chương trình đọc payload, khi một subtype được xác định bằng discriminator, hoặc khi ứng dụng gọi Jackson thông qua RestClient hay WebClient trong thân method.

Có ba bước độc lập:

1. **Jackson binding:** phân tích JSON và tạo đúng object graph. Nếu JSON sai cú pháp, thiếu type id hoặc chọn subtype không được hỗ trợ, object chưa được tạo hoàn chỉnh.
2. **Bean Validation:** kiểm tra các constraint trên object đã bind. @Valid kích hoạt kiểm tra lồng nhau; constraint như @NotBlank hoặc @Positive xác định điều kiện hợp lệ.
3. **HTTP error handling:** chuyển lỗi parse, lỗi validation và lỗi nghiệp vụ thành response có status và cấu trúc ổn định.

Native Image thêm một yêu cầu: mọi kiểu mà ứng dụng có thể cần truy cập động phải được nhận diện và giữ lại khi build. **Kiểu được chọn lúc runtime vẫn có thể dùng trong native nếu nó đã có trong classpath lúc build và được AOT/reachability metadata hỗ trợ.** Một class mới được cài vào sau khi executable đã tạo không tự trở thành kiểu có thể deserialize.

Bài này dùng một API tạo đơn hàng có nhiều phương thức thanh toán để minh họa Jackson polymorphic binding, Bean Validation lồng nhau, ProblemDetail, runtime hints và kiểm thử cả JVM lẫn native.

## 1. Luồng xử lý request và ranh giới giữa các loại lỗi

Một request đi qua các bước theo thứ tự:

~~~mermaid
flowchart TD
    A["HTTP JSON request"] --> B["Jackson đọc JSON"]
    B --> C{"Tạo được DTO và subtype?"}
    C -->|Không| D["HttpMessageNotReadableException"]
    C -->|Có| E["Bean Validation"]
    E --> F{"Các constraint hợp lệ?"}
    F -->|Không| G["MethodArgumentNotValidException hoặc HandlerMethodValidationException"]
    F -->|Có| H["Controller và nghiệp vụ"]
    H --> I{"Nghiệp vụ thành công?"}
    I -->|Không| J["Domain exception / ErrorResponse"]
    I -->|Có| K["Response DTO -> Jackson JSON"]
    D --> L["ProblemDetail HTTP 400"]
    G --> L
    J --> M["ProblemDetail theo lỗi nghiệp vụ"]
    K --> N["HTTP response"]
~~~

Không nên gộp mọi lỗi thành “validation failed”:

| Giai đoạn | Ví dụ | Kết quả thường gặp |
| --- | --- | --- |
| JSON parsing | Thiếu dấu ngoặc, sai kiểu dữ liệu | HttpMessageNotReadableException |
| Polymorphic deserialization | kind không nằm trong danh sách subtype | HttpMessageNotReadableException |
| Bean Validation trên request object | name trống, số lượng âm | MethodArgumentNotValidException |
| Method validation | Constraint đặt trực tiếp trên tham số method | HandlerMethodValidationException trong Spring MVC hiện đại |
| Validation ở service qua AOP | Service @Validated bị vi phạm constraint | Thường là ConstraintViolationException |
| Nghiệp vụ | Đơn hàng đã tồn tại, hạn mức bị vượt | Domain exception, có thể ánh xạ HTTP 409 hoặc status phù hợp |

Jackson phải tạo được object trước khi Bean Validation có thể kiểm tra object đó. Ví dụ JSON có kind là crypto nhưng ứng dụng chỉ khai báo card và bank-transfer: Jackson không thể chọn subtype, vì vậy controller không nhận được DTO để validate.

## 2. Khai báo Jackson và Bean Validation

Trong Spring Boot MVC, spring-boot-starter-web cung cấp hạ tầng HTTP và JSON mapping. Thêm Bean Validation provider bằng dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Dùng các annotation jakarta.validation.* trong ứng dụng Spring Boot hiện đại. Không trộn javax.validation.* của hệ sinh thái cũ với jakarta.validation.*.

Spring Boot tự cấu hình Jackson khi thư viện JSON tương ứng có trong classpath và cung cấp Validator khi có Bean Validation provider. Nếu cần kiểm tra hoặc tùy chỉnh trực tiếp, Spring có thể cung cấp jakarta.validation.Validator qua LocalValidatorFactoryBean.

### DTO nên mô tả hợp đồng dữ liệu

DTO HTTP nên biểu diễn dữ liệu mà client được phép gửi. Không nên nhận trực tiếp entity JPA hoặc object nội bộ có nhiều field nhạy cảm. Việc tách request DTO giúp kiểm soát rõ:

- Field nào được client gửi.
- Field nào phải có giá trị.
- Field nào được phép chọn theo subtype.
- Field nào chỉ được tạo bởi server.
- Những dữ liệu nào không được đưa vào error response hoặc log.

## 3. Dùng discriminator an toàn cho các subtype được chọn lúc runtime

Giả sử đơn hàng có thể thanh toán bằng thẻ hoặc chuyển khoản. JSON có field kind để chỉ ra subtype:

~~~json
{
  "orderId": "ORD-1001",
  "payment": {
    "kind": "card",
    "token": "tok_test_123",
    "lastFour": "4242"
  }
}
~~~

Hoặc:

~~~json
{
  "orderId": "ORD-1002",
  "payment": {
    "kind": "bank-transfer",
    "accountReference": "BANK-REF-88"
  }
}
~~~

Khai báo interface và danh sách subtype:

~~~java
package com.example.orders.api;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPaymentDetails.class,
                name = "card"
        ),
        @JsonSubTypes.Type(
                value = BankTransferDetails.class,
                name = "bank-transfer"
        )
})
public sealed interface PaymentDetails
        permits CardPaymentDetails, BankTransferDetails {
}
~~~

Hai implementation:

~~~java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CardPaymentDetails(
        @NotBlank String token,
        @NotBlank
        @Pattern(regexp = "\\d{4}")
        String lastFour
) implements PaymentDetails {
}
~~~

~~~java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;

public record BankTransferDetails(
        @NotBlank String accountReference
) implements PaymentDetails {
}
~~~

Request DTO:

~~~java
package com.example.orders.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String orderId,
        @NotNull @Valid PaymentDetails payment
) {
}
~~~

Ví dụ response DTO được dùng trong chữ ký controller:

~~~java
public record OrderResponse(String orderId, String status) {
}
~~~

Ở đây Id.NAME ánh xạ một tên logic như card vào một class cụ thể đã khai báo. Client không gửi tên class Java đầy đủ. Đây là cách phù hợp hơn cho API public so với bật default typing hoặc dùng JsonTypeInfo.Id.CLASS trên dữ liệu không tin cậy.

### Runtime selection không phải runtime class definition

Hai khái niệm cần tách biệt:

- **Runtime selection:** chương trình chọn một trong các class CardPaymentDetails hoặc BankTransferDetails dựa trên kind. Cả hai class đã có trong classpath lúc build nên Native Image có thể đưa chúng vào executable.
- **Runtime class definition:** chương trình nhận một JAR hoặc bytecode mới sau khi build rồi cố tạo class chưa tồn tại lúc native-image compilation. Đây là mô hình khác và không được bảo đảm bởi việc đăng ký reflection hints.

Với Native Image, hãy dùng danh sách subtype hữu hạn, được kiểm soát và kiểm thử. Không biến dữ liệu do client gửi thành class name rồi gọi Class.forName tùy ý.

## 4. Bean Validation trên object graph lồng nhau

@Valid yêu cầu validator đi tiếp vào object được tham chiếu để kiểm tra constraint của object đó. Nó không tự tạo ra một constraint “bắt buộc khác null”; vì vậy request dùng cả @NotNull và @Valid:

~~~java
public record CreateOrderRequest(
        @NotBlank String orderId,
        @NotNull @Valid PaymentDetails payment
) {
}
~~~

Ý nghĩa:

- @NotBlank yêu cầu orderId có nội dung sau khi trim.
- @NotNull yêu cầu payment có giá trị.
- @Valid kích hoạt cascade validation trên object thực tế được Jackson tạo ra.
- Nếu payment là CardPaymentDetails, các constraint của record đó được kiểm tra.
- Nếu payment là BankTransferDetails, các constraint của subtype chuyển khoản được kiểm tra.

Nếu bỏ @Valid, validator có thể kiểm tra payment không null nhưng không đi sâu để kiểm tra token, lastFour hoặc accountReference.

### Constraint trên collection và map

Với danh sách item, có thể kết hợp container element constraint và cascade validation:

~~~java
public record BulkOrderRequest(
        @NotEmpty
        List<@NotNull @Valid CreateOrderRequest> orders
) {
}
~~~

Mỗi phần tử phải khác null và được validate theo constraint của CreateOrderRequest. Với map, có thể áp dụng constraint cho key/value và cascade validation cho value nếu value là object lồng nhau.

### Validation theo nhóm

Khi một DTO có các quy tắc khác nhau theo thao tác tạo mới/cập nhật, có thể dùng validation groups. Hãy khai báo group rõ ràng, kích hoạt đúng group tại điểm gọi và test từng chế độ. Không nên dùng group chỉ để né constraint trong native; metadata cho constraint và validator vẫn cần được hỗ trợ trong executable.

## 5. Custom constraint và ConstraintValidator

Bean Validation cho phép định nghĩa constraint riêng. Ví dụ, một mã tham chiếu thanh toán phải tuân theo định dạng nghiệp vụ:

~~~java
package com.example.orders.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PaymentReferenceValidator.class)
public @interface ValidPaymentReference {

    String message() default "Payment reference is invalid";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
package com.example.orders.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class PaymentReferenceValidator
        implements ConstraintValidator<ValidPaymentReference, String> {

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        if (value == null || value.isBlank()) {
            return true;
        }

        return value.matches("[A-Z0-9-]{6,40}");
    }
}
~~~

Dùng constraint trên DTO:

~~~java
public record BankTransferDetails(
        @NotBlank
        @ValidPaymentReference
        String accountReference
) implements PaymentDetails {
}
~~~

Trong Spring, LocalValidatorFactoryBean tích hợp SpringConstraintValidatorFactory, cho phép custom ConstraintValidator nhận dependency injection như bean Spring. Validator nên có logic xác định, không gọi network hoặc database cho mỗi field nếu không có yêu cầu rõ ràng.

### Khi validator hoặc constraint được phát hiện động

Nếu validator được tham chiếu trực tiếp trong @Constraint(validatedBy = ...) và DTO nằm trong mô hình AOT, framework có cơ sở để phân tích mối quan hệ đó. Nhưng nếu ứng dụng nạp mapping từ validation.xml, file properties, plugin hoặc tên class đọc từ môi trường runtime, AOT có thể không suy ra toàn bộ class/resource cần dùng.

Trong trường hợp đó:

- Bảo đảm file mapping có trong image bằng resource hint nếu được đọc từ classpath.
- Bảo đảm validator implementation có mặt trên classpath khi build.
- Đăng ký reflection cho kiểu thực sự được gọi qua reflection nếu framework không tự cung cấp hint.
- Test từng constraint trên native executable.

Không mặc định rằng chỉ cần thêm @Valid là mọi custom validator và mapping động đều được xử lý.

## 6. Spring AOT tự suy ra hints trong trường hợp nào?

Spring AOT có thể suy ra nhiều reflection hints từ cấu trúc ứng dụng. Đặc biệt, khi kiểu request/response xuất hiện trực tiếp trong chữ ký method của @RestController, Spring thường nhận diện được các kiểu cần cho JSON binding.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @PostMapping
    OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        // ...
    }
}
~~~

Trong trường hợp này, CreateOrderRequest và OrderResponse xuất hiện rõ trong chữ ký controller. Spring AOT có thể suy ra metadata cần thiết cho binding.

Tuy nhiên, các kiểu có thể không xuất hiện trong chữ ký controller, chẳng hạn:

- DTO được serialize/deserialze bằng RestClient hoặc WebClient trực tiếp trong thân method.
- Concrete subtype chỉ được chọn qua discriminator hoặc custom deserializer.
- DTO được truyền qua một thư viện bên thứ ba thực hiện reflection.
- Kiểu được đọc từ cấu hình hoặc mapping mà Spring không thể phân tích ở build time.

Khi đó cần xác minh hints thực tế thay vì giả định AOT luôn nhìn thấy mọi class.

## 7. Đăng ký reflection hints cho DTO và subtype

Spring cung cấp @RegisterReflectionForBinding để đăng ký reflection metadata phục vụ binding. Annotation này bao gồm constructor, field, property và record component của kiểu được chỉ định; nó cũng đăng ký các kiểu được tham chiếu transitively qua property/record component.

Ví dụ đăng ký root DTO và các subtype được chọn qua discriminator:

~~~java
package com.example.orders.config;

import com.example.orders.api.BankTransferDetails;
import com.example.orders.api.CardPaymentDetails;
import com.example.orders.api.CreateOrderRequest;
import com.example.orders.api.OrderResponse;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        CreateOrderRequest.class,
        CardPaymentDetails.class,
        BankTransferDetails.class,
        OrderResponse.class
})
public class OrderJsonBindingConfiguration {
}
~~~

Nếu các kiểu chỉ được sử dụng trong @RestController, annotation này có thể dư thừa vì Spring đã suy ra hints. Ví dụ trên có chủ đích khai báo các subtype cụ thể để làm rõ tập kiểu polymorphic mà API hỗ trợ.

### Trường hợp dùng RestClient hoặc WebClient trực tiếp

Ví dụ client gọi dịch vụ đối tác và bind response vào DTO:

~~~java
@Component
@RegisterReflectionForBinding({
        PartnerCommand.class,
        PartnerResult.class
})
public class PartnerClient {

    private final RestClient restClient;

    public PartnerClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://partner.example.test")
                .build();
    }

    public PartnerResult submit(PartnerCommand command) {
        return restClient.post()
                .uri("/commands")
                .body(command)
                .retrieve()
                .body(PartnerResult.class);
    }
}
~~~

DTO không xuất hiện trong chữ ký của controller nên Spring AOT không nhất thiết suy ra được mọi nhu cầu binding từ luồng HTTP inbound. Annotation đặt gần component cần hints giúp metadata gắn với đúng phần ứng dụng.

Nếu dùng custom RuntimeHintsRegistrar thay annotation, có thể đăng ký reflection theo RuntimeHints rồi kích hoạt registrar bằng @ImportRuntimeHints. Chọn một cách có chủ đích; tránh đăng ký toàn bộ package nếu chỉ có vài DTO cần binding.

## 8. Kiểm tra hints và metadata được tạo ra

Có hai việc cần xác minh:

1. Spring AOT đã thu nhận các hints mà ứng dụng đóng góp.
2. Native Image đã nhận metadata và giữ được các kiểu cần thiết cho runtime.

@RegisterReflectionForBinding chỉ có tác dụng khi phần tử được annotate tham gia Spring context/AOT processing. Đặt annotation trên một class không được Spring phát hiện hoặc không được import có thể khiến kỳ vọng hints không thành hiện thực.

Nếu tự đóng góp hints bằng API chương trình, có thể dùng BindingReflectionHintsRegistrar để tạo binding hints và RuntimeHintsPredicates để kiểm tra chúng:

~~~java
import org.springframework.aot.hint.BindingReflectionHintsRegistrar;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

@Test
void registersBindingHintsForPaymentSubtypes() {
    RuntimeHints hints = new RuntimeHints();

    new BindingReflectionHintsRegistrar().registerReflectionHints(
            hints.reflection(),
            CardPaymentDetails.class
    );

    assertThat(
            RuntimeHintsPredicates.reflection()
                    .onType(CardPaymentDetails.class)
    ).accepts(hints);
}
~~~

Đây là kiểm tra đóng góp hints ở mức unit. Nó không chứng minh metadata đã được đưa vào native executable hoặc mọi đường Jackson runtime đều hoạt động. Cần kiểm thử end-to-end trên binary native.

### Reachability metadata JSON

Native Image cũng có thể nhận metadata JSON trong META-INF/native-image/<groupId>/<artifactId>/. Với định dạng reachability metadata hiện đại, phần reflection có thể khai báo kiểu và các member cần thiết. Ví dụ minh họa:

~~~json
{
  "reflection": [
    {
      "type": "com.example.orders.api.CardPaymentDetails",
      "allDeclaredConstructors": true,
      "allDeclaredFields": true,
      "allDeclaredMethods": true
    },
    {
      "type": "com.example.orders.api.BankTransferDetails",
      "allDeclaredConstructors": true,
      "allDeclaredFields": true,
      "allDeclaredMethods": true
    }
  ]
}
~~~

Không sao chép metadata rộng này nếu Spring đã sinh đủ hints. Các member category cần thiết phụ thuộc cách Jackson/validator truy cập DTO và phiên bản thư viện. Ưu tiên @RegisterReflectionForBinding cho binding DTO; chỉ dùng JSON metadata khi có lý do cụ thể và review theo schema GraalVM version đang dùng.

## 9. Phân biệt lỗi Jackson, lỗi validation và lỗi nghiệp vụ

### JSON không deserialize được

Các trường hợp:

- JSON sai cú pháp.
- Giá trị string không chuyển được sang kiểu số/ngày.
- Thiếu hoặc sai discriminator kind.
- Subtype không nằm trong danh sách được phép.
- Custom deserializer ném exception.

Spring MVC thường chuyển lỗi đọc request body thành HttpMessageNotReadableException. Bean Validation chưa chạy vì object chưa được bind thành công.

### Object bind được nhưng constraint không hợp lệ

Ví dụ orderId trống hoặc lastFour không đúng bốn chữ số. Controller nhận được DTO, nhưng validation thất bại trước khi gọi method body. Spring MVC có thể ném MethodArgumentNotValidException cho validation từng object parameter.

### Method-level validation

Nếu constraint được đặt trực tiếp trên tham số method hoặc giá trị trả về, Spring MVC hiện đại có thể áp dụng method validation và ném HandlerMethodValidationException. Đây là ngoại lệ khác với MethodArgumentNotValidException.

Nếu dùng Spring-driven method validation cho service được đánh dấu @Validated, cơ chế thường dựa trên AOP proxy và có thể ném ConstraintViolationException. Hãy xác định validation được kích hoạt ở controller hay service trước khi viết exception handler.

### Lỗi nghiệp vụ

Ví dụ đơn hàng trùng mã hoặc phương thức thanh toán bị từ chối. Đây không phải lỗi Jackson hay Bean Validation. Dùng exception nghiệp vụ riêng và ánh xạ sang status phù hợp, chẳng hạn 409 Conflict hoặc 422 Unprocessable Content theo hợp đồng API.

## 10. Trả lỗi có cấu trúc bằng ProblemDetail

Spring hỗ trợ ProblemDetail theo RFC 9457 cho HTTP API. Một response lỗi có thể có các trường chuẩn như type, title, status, detail, instance, cùng extension properties.

Ví dụ @RestControllerAdvice:

~~~java
package com.example.orders.api;

import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ProblemDetail handleUnreadableBody(
            HttpMessageNotReadableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body is malformed or contains an unsupported value."
        );
        problem.setTitle("Invalid JSON request");
        problem.setProperty("code", "REQUEST_BODY_INVALID");
        return problem;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleInvalidBody(
            MethodArgumentNotValidException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid."
        );
        problem.setTitle("Request validation failed");
        problem.setProperty(
                "errors",
                exception.getBindingResult().getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "code", Objects.toString(error.getCode(), "invalid"),
                                "message", Objects.toString(
                                        error.getDefaultMessage(),
                                        "Invalid value"
                                )
                        ))
                        .toList()
        );
        return problem;
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ProblemDetail> handleMethodValidation(
            HandlerMethodValidationException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                exception.getStatusCode(),
                "One or more method parameters failed validation."
        );
        problem.setTitle("Method validation failed");

        return ResponseEntity
                .status(exception.getStatusCode())
                .body(problem);
    }
}
~~~

Cấu trúc response lỗi validation có thể như sau:

~~~json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "errors": [
    {
      "field": "payment.token",
      "code": "NotBlank",
      "message": "must not be blank"
    }
  ]
}
~~~

Với lỗi discriminator không hợp lệ, response chỉ nên nói request chứa type không được hỗ trợ. Không trả nguyên stack trace, class name nội bộ, token thanh toán hoặc nội dung nhạy cảm từ payload cho client.

### Tránh xử lý trùng built-in exceptions

Spring Boot có thể bật Problem Details cho các lỗi MVC tích hợp bằng cấu hình:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Nếu tự viết @ControllerAdvice để xử lý cùng exception, cần hiểu thứ tự advice và tránh hai handler cạnh tranh. Có thể mở rộng ResponseEntityExceptionHandler khi cần tùy chỉnh nhiều exception MVC built-in; hoặc giữ advice riêng chỉ xử lý những lỗi mà ứng dụng thật sự muốn sở hữu.

## 11. Jackson 2, Jackson 3 và khác biệt phiên bản

Spring Boot 3.x thường dùng Jackson 2, trong đó các API databind nằm dưới package com.fasterxml.jackson.databind.

Spring Boot 4 chuyển Jackson 3 thành lựa chọn mặc định. Jackson 3 đổi group/package chính từ com.fasterxml.jackson sang tools.jackson, nhưng jackson-annotations vẫn giữ package com.fasterxml.jackson.annotation để tương thích. Vì vậy, các annotation trong ví dụ như @JsonTypeInfo và @JsonSubTypes vẫn dùng package com.fasterxml.jackson.annotation; custom serializer/deserializer và mapper API cần đối chiếu version đang dùng.

Một số lưu ý khi nâng cấp:

- Không trộn Jackson 2 và Jackson 3 module một cách vô tình.
- Kiểm tra thư viện bên thứ ba có yêu cầu đúng major version hay không.
- Nếu viết custom serializer/deserializer, dùng API của major version được Spring Boot quản lý.
- Kiểm thử lại default behavior, coercion, unknown properties và polymorphic handling sau khi nâng cấp.
- Đừng dùng một ví dụ ObjectMapper từ Jackson 2 rồi giả định package/API vẫn giống trong Boot 4.

Metadata Native Image cũng phụ thuộc integration và phiên bản. Spring AOT có thể tự suy ra hints cho đường binding tiêu chuẩn, nhưng thư viện JSON bổ sung hoặc custom module có thể cần metadata riêng.

## 12. Kiểm thử cả payload hợp lệ, lỗi validation và native runtime

Nên có test cho từng nhánh discriminator. Một test chỉ gửi kind là card không chứng minh bank-transfer hoạt động.

### Bộ ca kiểm thử tối thiểu

| Payload/kịch bản | Kết quả mong đợi | Tầng được kiểm tra |
| --- | --- | --- |
| kind là card với token hợp lệ | Tạo CardPaymentDetails | Jackson subtype binding |
| kind là bank-transfer với account reference hợp lệ | Tạo BankTransferDetails | Jackson subtype binding |
| Không có kind | Từ chối nếu cấu hình yêu cầu type id | Jackson |
| kind là unknown | HTTP 400, không gọi nghiệp vụ | Jackson |
| orderId trống | HTTP 400 với field error | Bean Validation |
| card.lastFour sai định dạng | HTTP 400 với nested field error | Cascade validation |
| bank.accountReference trống | HTTP 400 với nested field error | Cascade validation |
| JSON sai cú pháp | HTTP 400 | Message conversion |
| Business rule từ chối đơn | Status nghiệp vụ đã quy định | Exception mapping |
| Gọi RestClient/WebClient với DTO | Request/response bind thành công | Programmatic JSON binding |

### Kiểm thử trên JVM

Dùng MockMvc hoặc integration test để kiểm tra:

- Cả hai subtype.
- Discriminator không hợp lệ.
- Constraint ở root DTO và nested DTO.
- JSON malformed.
- Error response có status và extension field đúng.
- Không có token hoặc secret trong error response.

### Kiểm thử trên native executable

Build native theo toolchain của dự án:

~~~bash
# Maven project đã cấu hình native profile.
./mvnw -Pnative native:compile

# Gradle project đã cấu hình Native Build Tools.
./gradlew nativeCompile
~~~

Chạy executable native và gửi lại cùng các payload ở bảng trên. Đặc biệt kiểm tra subtype được chọn qua discriminator và DTO dùng qua RestClient/WebClient.

Nếu native báo thiếu reflection registration:

1. Xác định class/member cụ thể mà Jackson hoặc validator đang truy cập.
2. Kiểm tra class đó có nằm trong classpath lúc build không.
3. Kiểm tra Spring AOT có nhận diện controller/client/DTO không.
4. Bổ sung @RegisterReflectionForBinding cho root DTO và các subtype chưa được suy ra.
5. Build lại native và chạy đúng test đã thất bại.

Tracing Agent có thể chạy ứng dụng trên JVM với -Dspring.aot.enabled=true để thu các dynamic access mà static analysis hoặc Spring chưa nhận diện. Hãy chạy cả các nhánh subtype và client call, review metadata rồi mới đưa vào build.

Không kết luận thành công chỉ từ việc native executable khởi động. Phải gọi các endpoint và nhánh polymorphic thực tế.

## 13. Bảo mật khi deserialize và xử lý lỗi

JSON polymorphism là ranh giới đầu vào. Hãy giới hạn subtype theo danh sách logic rõ ràng:

- Dùng JsonTypeInfo.Id.NAME và JsonSubTypes hoặc registry allowlist tương đương.
- Không bật Jackson default typing rộng cho payload không tin cậy.
- Không lấy tên class từ JSON rồi nạp bằng Class.forName.
- Không cho phép client chọn implementation nội bộ, validator hoặc plugin bằng class name.
- Giới hạn kích thước request body và độ sâu object graph theo nhu cầu API.
- Kiểm tra dữ liệu nhạy cảm trước khi log; không đưa token vào ProblemDetail.
- Tách lỗi validation có thể hiển thị cho client khỏi lỗi hệ thống cần log nội bộ.

Native Image không làm mất các rủi ro deserialization của ứng dụng. Reachability metadata chỉ giúp giữ các thành phần cần thiết cho runtime; nó không biến một deserialization policy nguy hiểm thành an toàn.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| JVM deserialize được nhưng native báo thiếu registration | DTO/subtype cần reflection chưa được giữ lại | Kiểm tra AOT hints, thêm @RegisterReflectionForBinding |
| REST controller chạy native nhưng RestClient lỗi | DTO chỉ dùng trong method body, Spring không suy ra từ controller signature | Đăng ký request/response DTO ở bean client |
| Chỉ một subtype lỗi | Concrete subtype chưa được khai báo hoặc không có metadata | Đăng ký và test riêng subtype đó |
| Jackson báo invalid type id | kind thiếu hoặc không khớp logical name | Kiểm tra JSON và danh sách @JsonSubTypes |
| Controller không nhận request, validation không chạy | Jackson parse/binding đã thất bại trước đó | Đọc root cause của HttpMessageNotReadableException |
| Nested field sai nhưng request vẫn qua | Thiếu @Valid ở field/parameter cha | Bổ sung cascade validation và test lại |
| Custom validator không được gọi | Constraint chưa gắn đúng field/type, provider thiếu hoặc mapping không được nạp | Kiểm tra annotation, starter và validator provider |
| Validator hoạt động JVM nhưng lỗi native | Validator/mapping được nạp động hoặc thiếu metadata/resource | Xác định class/resource và đăng ký hints cụ thể |
| Method validation trả exception khác dự kiến | MVC method validation và service AOP validation là hai cơ chế khác nhau | Xác định nơi đặt constraint và xử lý đúng exception |
| Error response để lộ chi tiết nội bộ | Handler trả exception message/stack trace trực tiếp | Ánh xạ sang ProblemDetail với thông điệp ổn định |

## 15. Bài thực hành: API đơn hàng với hai phương thức thanh toán

Tạo Spring Boot REST API có endpoint POST /orders. Dùng các class CreateOrderRequest, PaymentDetails, CardPaymentDetails, BankTransferDetails và OrderResponse như các ví dụ phía trên.

Thực hiện:

1. Thêm spring-boot-starter-validation.
2. Khai báo subtype bằng @JsonTypeInfo(use = Id.NAME) và @JsonSubTypes.
3. Dùng @NotBlank, @NotNull, @Pattern và @Valid để kiểm tra cả root lẫn nested DTO.
4. Tạo controller nhận @Valid @RequestBody CreateOrderRequest.
5. Tạo @RestControllerAdvice trả ProblemDetail cho lỗi JSON và validation.
6. Thêm @RegisterReflectionForBinding cho subtype nếu chúng không được Spring AOT suy ra trong luồng thực tế.
7. Nếu có client gọi API đối tác bằng RestClient, đăng ký riêng DTO request/response của client.
8. Chạy test JVM với card hợp lệ, bank transfer hợp lệ, subtype không hỗ trợ và nested field sai.
9. Build native executable và gửi lại cùng các payload.
10. Xác minh error response không chứa stack trace, class name nội bộ hoặc payment token.
11. Ghi lại class nào được Spring AOT suy ra tự động, class nào cần hint bổ sung và vì sao.

### Câu hỏi tự kiểm tra

1. Vì sao Jackson phải tạo được object trước khi Bean Validation kiểm tra nested fields?
2. @Valid khác @NotNull ở điểm nào?
3. Vì sao JsonTypeInfo.Id.NAME với danh sách subtype rõ ràng phù hợp hơn việc cho client gửi class name?
4. Spring AOT thường suy ra hints cho DTO của @RestController từ đâu?
5. Khi nào DTO dùng với RestClient hoặc WebClient cần @RegisterReflectionForBinding?
6. Vì sao phải đăng ký concrete subtype nếu chúng chỉ xuất hiện qua discriminator?
7. MethodArgumentNotValidException khác HandlerMethodValidationException như thế nào?
8. Vì sao lỗi JSON malformed và lỗi Bean Validation cần được phân loại riêng?
9. Native Image có thể deserialize class được cài thêm sau khi executable đã build không?
10. Vì sao JVM test pass chưa chứng minh polymorphic binding hoạt động trên native?

**Tiêu chí đạt:** xây dựng được DTO polymorphic với danh sách subtype có kiểm soát; cascade Bean Validation đúng trên object graph; phân loại lỗi Jackson, validation và nghiệp vụ; trả ProblemDetail ổn định; xác định đúng khi nào Spring AOT tự sinh hints và khi nào cần @RegisterReflectionForBinding; cuối cùng kiểm thử được mọi subtype và nhánh lỗi trên native executable.

## Tài liệu chính thức

- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — JSON support: https://docs.spring.io/spring-boot/reference/features/json.html
- Spring Framework — Ahead-of-Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Error Responses and ProblemDetail: https://docs.spring.io/spring/reference/7.0/web/webmvc/mvc-ann-rest-exceptions.html
- GraalVM — Reachability Metadata: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
