# Kiểm tra phương thức và thay đổi cơ chế hỗ trợ theo phiên bản Spring

## 1. Bối cảnh: kiểm tra dữ liệu không dừng ở DTO

Trong một ứng dụng Spring Boot, kiểm tra dữ liệu đầu vào (validation) có thể diễn ra tại nhiều ranh giới: khi bind JSON vào @RequestBody, khi chuyển query string thành @RequestParam, khi nhận một đối tượng @ModelAttribute và ngay trước khi gọi một phương thức Java. Còn có trường hợp cần kiểm tra **giá trị trả về** của phương thức, đặc biệt khi service phải luôn bảo đảm bất biến của hợp đồng.

Ví dụ:

- DTO tạo đơn hàng phải có tên sản phẩm không rỗng: @NotBlank trên field hoặc record component, được kích hoạt qua @Valid @RequestBody.
- Query parameter page phải >= 1: @Min(1) đặt trực tiếp lên tham số @RequestParam của controller.
- Service transfer(amount) phải được gọi với amount dương, kể cả khi caller không phải HTTP: @Positive đặt trên tham số service và dùng method validation.
- Hàm findRequired() không được trả null: @NotNull trên **giá trị trả về** của phương thức.
- Một method có nhiều tham số cần tuân thủ một quy tắc kết hợp: cross-parameter validation hoặc kiểm tra domain rõ ràng.

Những tình huống này không được kiểm tra hoàn toàn bằng cùng một cơ chế ở mọi phiên bản Spring Framework. Đặc biệt **Spring Framework 6.1** bổ sung cơ chế **method validation tích hợp trực tiếp vào Spring MVC và WebFlux controller**. Trước đó, người phát triển thường dùng **@Validated ở cấp class để kích hoạt AOP proxy** cho validation trên tham số/return value của controller. Sự thay đổi này ảnh hưởng đến exception type, error handling và cách migrate code.

Bài học giải thích rõ sự khác biệt giữa:

1. Bean Validation trên **một đối tượng tham số**;
2. Bean Validation trên **toàn phương thức**;
3. Method validation thông qua **Spring AOP** ở service/component;
4. Method validation **built-in** trong MVC/WebFlux từ Spring Framework 6.1;
5. Hành vi thay đổi khi nâng phiên bản Spring Boot/Spring Framework.

Mục tiêu không phải thêm thật nhiều annotation, mà là đặt validation đúng tầng, biết khi nào exception được tạo và tránh vô tình trả HTTP 500 cho lỗi đầu vào đáng lẽ phải là 400.

## 2. Thuật ngữ và những lớp dễ bị nhầm

| Khái niệm | Vai trò | Điểm cần nhớ |
|---|---|---|
| Bean Validation (Jakarta Validation) | Đặc tả các constraint trên bean, tham số và return value | Annotation là hợp đồng; cần provider thực thi như Hibernate Validator |
| @NotNull, @NotBlank, @Min, @Positive, @Size | Các constraint annotation | Trực tiếp kiểm tra giá trị; null có quy tắc riêng cho từng constraint |
| @Valid | Kích hoạt validation/cascade theo đối tượng | **Không phải** một constraint tự thân |
| @Validated | Annotation của Spring hỗ trợ validation groups và phương thức theo AOP | Đặt cấp class ở service là cách phổ biến; đặt cấp class ở controller 6.1+ có thể chuyển sang cơ chế AOP |
| @RequestBody / @ModelAttribute / @RequestPart | Nguồn để bind một đối tượng đầu vào | Có cơ chế validation trên từng method argument |
| BindingResult / Errors | Cho controller xử lý binding/validation errors phù hợp | Vị trí tham số phải ngay sau đối tượng cần xử lý |
| MethodArgumentNotValidException | Ngoại lệ MVC cho validation trên một argument object | Thường đi cùng @Valid @RequestBody khi method validation không cần thiết |
| WebExchangeBindException | Ngoại lệ WebFlux cho binding/validation trên một argument object | Tương đương về mục đích với MVC MethodArgumentNotValidException |
| HandlerMethodValidationException | Ngoại lệ cho method validation tích hợp trên controller từ Framework 6.1 | Có thông tin validation results theo tham số; input thường HTTP 400, return value thường HTTP 500 |
| ConstraintViolationException | Ngoại lệ Jakarta Validation thường xuất hiện ở method validation AOP | Không tự đồng nghĩa với HTTP 400 |
| MethodValidationException | Ngoại lệ Spring dùng kết quả validation đã thích nghi, khi cấu hình áp dụng | Khác với HandlerMethodValidationException của web controller |
| MethodValidationPostProcessor | Hạ tầng tạo AOP proxy cho Spring method validation | Phù hợp với @Validated service/component |
| Validator / LocalValidatorFactoryBean | Cầu nối Spring và provider Bean Validation | Có thể được auto-configure khi provider có trên classpath |
| ResponseEntityExceptionHandler | Hỗ trợ xử lý exception ở MVC/WebFlux theo stack phù hợp | Có các hook để tùy biến response |
| @ControllerAdvice / @RestControllerAdvice | Áp dụng logic xử lý lỗi cho nhiều controller | Cần xử lý đúng exception type và HTTP status |

**Method validation** là validation ở phạm vi method invocation: kiểm tra constraints trực tiếp trên các tham số, kiểm tra nested constraints khi có cascade @Valid và có thể kiểm tra return value. Nó khác với việc chỉ validate một DTO object ở thời điểm bind request.

## 3. @Valid khác @Validated và constraint như thế nào?

### 3.1. Constraint thực sự là gì?

Các annotation như @NotNull, @NotBlank, @Min và @Positive thuộc Jakarta Validation và được meta-annotate để mô tả constraint. Một provider sẽ đánh giá chúng khi validation được kích hoạt.

Ví dụ một request DTO:

~~~java
public record CreateProduct(
        @NotBlank String name,
        @NotNull @Min(1) Integer quantity) {}
~~~

Ở đây:
- @NotBlank kiểm tra name không null, không empty và không chỉ gồm whitespace.
- @NotNull buộc quantity có mặt sau binding.
- @Min(1) từ chối quantity nhỏ hơn 1, nhưng khi đứng riêng, các constraint số học như @Min thường cho null qua. Vì thế @NotNull và @Min bổ sung cho nhau.

Đoạn record là snippet cần import jakarta.validation.constraints và đặt vào project có provider. Annotation một mình không tự động thực thi nếu không có một đường code kích hoạt validation.

### 3.2. @Valid không phải constraint trực tiếp

~~~java
@PostMapping("/products")
ProductView create(@Valid @RequestBody CreateProduct request) {
    // ...
}
~~~

@Valid báo cho Spring/validator kiểm tra nội dung object CreateProduct và các đối tượng nested được cascade phù hợp. Nó không có nghĩa rằng một tham số Java bất kỳ phải không null.

Ví dụ chỉ đặt @Valid trên String không tự yêu cầu String phải có chữ. Nếu cần String không trống, hãy dùng @NotBlank trên tham số hoặc field thích hợp.

Một minh họa về sự khác nhau:

~~~java
// Không đủ để bắt buộc term không blank:
@GetMapping("/a")
String a(@RequestParam @Valid String term) {
    return term;
}

// Có direct constraint trên method parameter:
@GetMapping("/b")
String b(@RequestParam @NotBlank String term) {
    return term;
}
~~~

Đây là hai controller method snippets. Ở Framework 6.1+, method b là tình huống kích hoạt built-in method validation cho @NotBlank trực tiếp, khi không bị chuyển sang cơ chế AOP bởi class-level @Validated.

### 3.3. @Validated của Spring có hai vai trò

- **Validation groups:** @Validated(Create.class) trên argument object giúp chọn nhóm constraints cho dữ liệu bind.
- **AOP method validation:** @Validated ở cấp bean/class như @Service khiến MethodValidationPostProcessor có điểm cắt (pointcut) để kiểm tra method parameters/return values khi lời gọi đi **qua proxy Spring**.

Cùng một annotation nhưng vị trí khác nhau sẽ dẫn đến cơ chế khác nhau. Đặc biệt, trong controller dùng Spring Framework 6.1+, nếu muốn dùng built-in validation mới, tài liệu Spring yêu cầu **loại bỏ class-level @Validated khỏi controller**. Đừng xóa @Validated khỏi mọi service, vì service vẫn thường dựa vào AOP method validation.

### 3.4. Validation group không phải cơ chế tùy chọn field tự động

Một DTO có thể có nhóm Create và Update với những constraint khác nhau, nhưng việc đặt @Validated(Create.class) không tự phân biệt JSON property thiếu với explicit null trong mọi tình huống PATCH. Validation kiểm tra object đã bind; nếu cần presence semantics, DTO phải lưu thông tin presence hoặc dùng cấu trúc như JsonNode.

## 4. Validation trên từng argument object

Spring MVC thường kiểm tra một argument object qua @Valid/@Validated khi:

1. Controller có tham số @RequestBody, @ModelAttribute hoặc @RequestPart được framework hỗ trợ.
2. Tham số đó là command object phù hợp, không phải trường hợp Map/Collection được xem như container đối với quy tắc này.
3. Không có Errors hoặc BindingResult **ngay sau** argument để controller tự nhận lỗi.
4. Không có direct method constraints khác khiến Spring chuyển sang method validation.

Ví dụ:

~~~java
@PostMapping("/products")
ResponseEntity<ProductView> create(
        @Valid @RequestBody CreateProduct request) {
    // ...
}
~~~

Khi request body có name rỗng hoặc quantity nhỏ hơn 1, MVC có thể phát sinh MethodArgumentNotValidException. Nó mang BindingResult với field errors, object errors và thông tin có ích để tạo response lỗi.

Trong WebFlux, tình huống tương đương thường phát sinh WebExchangeBindException. Hai loại exception khác nhau vì WebFlux dùng reactive request processing, không phải Servlet MVC.

### 4.1. BindingResult ngay sau argument

Trong MVC có thể xử lý lỗi trực tiếp:

~~~java
@PostMapping("/manual")
ResponseEntity<?> manual(
        @Valid @RequestBody CreateProduct request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Invalid product");
    }

    return ResponseEntity.ok("Accepted");
}
~~~

Đây là method snippet; CreateProduct và imports cần có. BindingResult phải nằm ngay sau argument liên quan. Nếu có direct method constraints trên những tham số khác và validation errors không thể được xử lý hết bằng các Errors/BindingResult theo quy tắc web framework, Spring có thể ném HandlerMethodValidationException thay vì luôn gọi method.

Vì vậy không coi việc thêm BindingResult như một “cờ tắt tất cả validation exceptions”.

### 4.2. Binding/deserialize lỗi khác Bean Validation

Trước khi provider kiểm tra @NotBlank, framework phải giải mã JSON và convert kiểu dữ liệu. JSON malformed, unsupported media type, path variable không convert được, hoặc query int chứa chữ có thể phát sinh lỗi binding/HTTP message đọc dữ liệu và không đi vào cùng loại validation exception.

Một error handler chỉ bắt MethodArgumentNotValidException sẽ không bao phủ mọi 400 Bad Request. Một API chuẩn cần thiết kế response lỗi phù hợp cho cả parsing, conversion, missing request body, missing request parameter và Bean Validation.

## 5. Validation trên method và thay đổi quan trọng của Spring Framework 6.1

### 5.1. Điều gì kích hoạt method validation trong controller 6.1+?

Khi một method của annotated MVC hoặc WebFlux controller có **direct constraint** trên tham số hoặc trên giá trị trả về, Spring Framework 6.1+ có thể kiểm tra method bằng cơ chế tích hợp của web framework, không cần AOP proxy dành riêng cho controller.

Ví dụ:

~~~java
@GetMapping("/page")
Map<String, Integer> page(
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    return Map.of("page", page);
}
~~~

@Min(1) đặt trực tiếp trên method parameter. Với GET /page?page=0, đối tượng page có giá trị int=0 hợp lệ về kiểu, nhưng vi phạm constraint. Trong controller dùng built-in method validation Framework 6.1+, hành vi thông thường là HandlerMethodValidationException và HTTP 400.

Các direct constraints thường gặp:

- @Min, @Max, @Positive, @Negative trên số.
- @NotBlank, @Size, @Pattern trên String.
- @NotNull cho tham số có thể null hoặc giá trị trả về.
- Constraint tùy chỉnh được khai báo với @Constraint.
- Các constraints trên return value của method khi hợp đồng yêu cầu.

**@Valid một mình không kích hoạt method validation.** Nó yêu cầu cascade validation của một đối tượng. Nếu thêm @NotNull trực tiếp vào cùng một argument @Valid, đó đã là direct constraint, nên cơ chế method validation có thể được chọn.

### 5.2. Method validation bao trùm nested validation

Giả sử method có một @Min đặt trực tiếp trên page và một @Valid @RequestBody DTO:

~~~java
@PostMapping("/products/check")
ResponseEntity<String> check(
        @RequestParam @Min(1) int page,
        @Valid @RequestBody CreateProduct request) {
    return ResponseEntity.ok("Accepted");
}
~~~

Ở Framework 6.1+ trong cấu hình built-in, method validation có khả năng bao trùm cả direct constraint trên page **và** nested constraints của CreateProduct. Nó supersede hình thức validation riêng lẻ của @Valid body khi method-level validation là cần thiết.

Điều này có thể làm **loại exception thay đổi** sau khi thêm một annotation vào method: trước đây method chỉ có @Valid body có thể ném MethodArgumentNotValidException; khi thêm @Min trên query param, tình huống vi phạm có thể đi qua HandlerMethodValidationException. Error handler và test không nên cứng hóa giả định rằng mọi @Valid @RequestBody đều chỉ ném một loại exception.

### 5.3. HandlerMethodValidationException cho input và output

Khi web controller method validation thất bại, HandlerMethodValidationException mang danh sách kết quả theo từng method parameter hoặc return value. Đối với input constraint violation, HTTP status theo cơ chế mặc định là **400**. Khi controller vi phạm **return-value constraint**, HTTP status mặc định là **500**, vì server đã tự vi phạm hợp đồng của nó.

Ví dụ minh họa return-value constraint:

~~~java
@GetMapping("/display")
@NotNull
public String display(@RequestParam(defaultValue = "false") boolean fail) {
    return fail ? null : "ready";
}
~~~

Đây là snippet method dùng Framework 6.1+; nếu fail=true thì method trả null, vi phạm @NotNull trên return value. Đó là lỗi triển khai/logic phía server, **không phải request validation error do client trực tiếp gây ra**. Không nên catch mọi HandlerMethodValidationException rồi ép HTTP 400.

Trong một ứng dụng thật, cần hạn chế việc trả null trái hợp đồng, test method return value và quan sát lỗi server riêng với lỗi input.

### 5.4. Validation results được nhóm theo tham số

HandlerMethodValidationException có thể cung cấp danh sách ParameterValidationResult (và ParameterErrors đối với object) cùng thông tin method parameter, constraint errors. Framework cung cấp Visitor để phân loại tham số như @RequestParam, @RequestHeader, @ModelAttribute và những loại khác.

Ưu điểm của cách này: API error handler có thể tạo cấu trúc lỗi theo từng tham số rõ ràng hơn. Không chỉ lấy ex.getMessage() để cố parse tên field từ một chuỗi có định dạng có thể thay đổi.

Cũng cần tránh đưa toàn bộ rejected value vào response/log nếu có mật khẩu, token hoặc dữ liệu cá nhân.

## 6. Cơ chế cũ: @Validated class-level và AOP

Trước khi Spring Framework 6.1 bổ sung built-in controller method validation, cách phổ biến để kiểm tra direct constraints trên controller methods là dùng @Validated ở cấp class và MethodValidationPostProcessor để gọi qua AOP proxy.

Ví dụ kiểu cũ:

~~~java
@RestController
@Validated
@RequestMapping("/legacy")
class LegacyController {

    @GetMapping("/page")
    String page(@RequestParam @Min(1) int page) {
        return "page=" + page;
    }
}
~~~

Đây là đoạn class minh họa, cần imports và môi trường hỗ trợ validation. Trước 6.1, phương pháp này giúp MethodValidationInterceptor thực hiện validation quanh lời gọi method.

Từ 6.1 trở đi, giữ @Validated ở cấp controller vẫn có thể đưa validation qua AOP proxy thay vì cơ chế web tích hợp. Spring khuyến nghị **bỏ @Validated ở cấp controller** để sử dụng hỗ trợ built-in 6.1. Nếu không, mã xử lý HandlerMethodValidationException có thể không nhận được lỗi như kỳ vọng; bạn có thể thấy ConstraintViolationException hoặc kiểu method validation exception do AOP cấu hình.

### 6.1. Vì sao AOP khác built-in controller validation?

| Tiêu chí | @Validated class-level + AOP | Web built-in từ Framework 6.1 |
|---|---|---|
| Kích hoạt | Class/bean được proxy và lời gọi đi qua proxy | Web framework xử lý annotated controller method |
| Phạm vi | Nhiều loại Spring bean: service, component, controller | Controller được MVC/WebFlux dispatch |
| Lỗi thông dụng | ConstraintViolationException; tùy cấu hình có MethodValidationException | HandlerMethodValidationException |
| Hiểu loại tham số HTTP | Không phải trọng tâm; AOP nhìn Java method | Gắn với web method parameters và HTTP error handling |
| Validation return value | Có, khi provider và interceptor hỗ trợ | Có |
| Giới hạn self-invocation | Có với proxy thông thường | Web handler invocation không phụ thuộc proxy AOP theo cơ chế mới |
| Cách bật trên controller mới | Không cần class-level @Validated | Direct constraints + provider, theo phiên bản |
| Cách bật trên service | @Validated class-level vẫn thường cần | Không thay thế service AOP method validation |

**Không xóa @Validated ở mọi class khi nâng Spring Framework 6.1.** Thay đổi được tài liệu Spring nói rõ dành cho **controller dùng built-in method validation**. Các service/component cần validation qua proxy vẫn thường phải đặt @Validated cấp type.

### 6.2. Self-invocation có thể bỏ qua proxy

Ví dụ service:

~~~java
@Service
@Validated
public class PriceService {

    public int quote(@Min(1) int quantity) {
        return quantity * 100;
    }

    public int quoteInternally() {
        // Gọi nội bộ qua this: không đi qua AOP proxy.
        return quote(0);
    }
}
~~~

Nếu một Spring bean bên ngoài gọi bean proxy PriceService.quote(0), method validation AOP có thể chặn. Nhưng khi quoteInternally() gọi quote(0) trong cùng object bằng this, lời gọi không đi qua proxy nên validator **không được kích hoạt qua interception thông thường**.

Đây là giới hạn của Spring AOP proxy, không phải bug trong @Min. Hướng xử lý tốt hơn là tách phương thức cần validate sang một bean riêng và gọi qua proxy, hoặc kiểm tra invariant tại tầng domain/code bắt buộc; đừng dựa hoàn toàn vào annotation nếu nội bộ tự gọi method.

AOP proxy còn có các giới hạn về cách gọi method, accessibility, final methods và cơ chế JDK/CGLIB. Nếu method validation không hoạt động, trước tiên kiểm tra bean có do Spring quản lý và lời gọi có thực sự đi qua proxy không.

## 7. Bảng đối chiếu phiên bản Spring và Spring Boot

**Luôn kiểm tra Spring Framework version thực chạy**, không chỉ số Spring Boot trong tài liệu hoặc hình ảnh dự án. Spring Boot quản lý dependency theo BOM; nếu nhóm đã override Framework version, hành vi có thể khác dự kiến.

| Dòng phiên bản | Điểm cần biết |
|---|---|
| Spring Framework 5.x / Spring Boot 2.x | API Bean Validation phổ biến vẫn thuộc javax.validation; validation trên controller direct method constraints thường dùng class-level @Validated/AOP |
| Spring Framework 6.0 / Spring Boot 3.0–3.1 | Chuyển sang jakarta.validation; chưa có built-in controller method validation mới của Framework 6.1; AOP vẫn thường cần cho direct constraints |
| Spring Framework 6.1 / Spring Boot 3.2–3.3 | Built-in method validation cho @RequestMapping methods ở MVC/WebFlux; HandlerMethodValidationException được giới thiệu; nên bỏ class-level @Validated ở controller muốn dùng cơ chế mới |
| Spring Framework 6.2 / Spring Boot 3.4–3.5 | Cơ chế built-in 6.1 vẫn là điểm nền tảng; chú ý docs/Javadoc chính xác và các thay đổi binding/error handling |
| Các nhánh Spring Framework mới hơn | Không suy diễn từ ví dụ 6.1; kiểm tra tài liệu phiên bản, migration notes, error handling API và test trên dependency thật |

Với project mới dùng Java 17+, Spring Boot 3.2/3.3 cùng Framework 6.1 là một mốc rõ ràng để tìm hiểu thay đổi. Các Spring Boot 3.x sử dụng namespace **jakarta.validation**; không copy import javax.validation từ một blog viết cho Boot 2.x.

### 7.1. Các lỗi thường xuất hiện ngay sau upgrade

1. Controller cũ có @Validated ở class vẫn chạy qua proxy AOP, trong khi nhóm mới muốn handle HandlerMethodValidationException.
2. Controller có @Valid @RequestBody nay thêm @Min trên @RequestParam, làm loại validation failure chuyển từ per-argument sang method validation.
3. @ControllerAdvice chỉ bắt MethodArgumentNotValidException, bỏ sót HandlerMethodValidationException.
4. Unit/integration test cứng hóa tên exception thay vì kiểm tra behavior HTTP, hoặc chưa kiểm tra cả hai loại.
5. Service có @Validated bị xóa theo một hướng dẫn dành riêng cho controller, khiến method validation service không còn được kích hoạt.
6. Các imports javax.validation còn sót sau chuyển Boot 2.x sang Boot 3.x.
7. Một return-value constraint lỗi bị quy về HTTP 400 thay vì 500.
8. Method validation AOP với self-invocation không chặn request path nội bộ như kỳ vọng.
9. Một số code cũ tự tạo MethodValidationPostProcessor hoặc Validator bean mâu thuẫn với Boot auto-configuration.
10. Test chạy cùng dependency tree khác với production, dẫn đến handler validation khác.

**Tránh giải pháp “catch Exception rồi trả 400”**: nó che cả lỗi server, lỗi persistence, lỗi code và violation trên return value. Nên phân loại rành mạch input errors và server contract errors.

## 8. Mô hình error handling trong Spring MVC

MVC có hai tình huống quan trọng:

**Trường hợp A: Validation một object argument riêng lẻ**

~~~java
@PostMapping("/products")
ProductView create(@Valid @RequestBody CreateProduct dto) {
    // ...
}
~~~

Nếu CreateProduct sai constraint và method không có direct constraints kích hoạt method validation, loại lỗi thường là **MethodArgumentNotValidException** (hoặc BindingResult nếu xử lý trực tiếp đúng vị trí).

**Trường hợp B: Method validation**

~~~java
@GetMapping("/products")
List<ProductView> list(
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    // ...
}
~~~

Với Framework 6.1+ built-in, lỗi @Min thường thành **HandlerMethodValidationException**. Đây không phải một biến thể tên của MethodArgumentNotValidException; handler phải biết cả hai.

Nếu project dùng AOP @Validated ở class controller, cần kiểm tra cả ConstraintViolationException hoặc MethodValidationException theo cấu hình AOP.

### 8.1. Xây dựng response lỗi nhất quán

Spring hỗ trợ @RestControllerAdvice và ResponseEntityExceptionHandler. Với Spring Framework 6.1.x, có thể override các method tương ứng để đưa lỗi validation về một JSON schema chung mà vẫn giữ status code phù hợp.

Ví dụ class độc lập trong project MVC:

~~~java
package dev.example.methodvalidation;

import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiValidationAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return handleExceptionInternal(
                ex,
                Map.of("error", "INVALID_BODY", "status", status.value()),
                headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        String code = ex.isForReturnValue()
                ? "INVALID_SERVER_RETURN"
                : "INVALID_METHOD_INPUT";

        return handleExceptionInternal(
                ex,
                Map.of("error", code, "status", status.value()),
                headers, status, request);
    }
}
~~~

Lớp này minh họa cách phân nhánh hai loại exception trên Spring MVC Framework 6.1+. Những JSON fields như "error" chỉ là hợp đồng tự thiết kế; không phải định dạng lỗi bắt buộc của Spring Boot.

**Lưu ý:** không ép HandlerMethodValidationException thành 400 vô điều kiện. Trong ví dụ, handleExceptionInternal nhận status được Spring truyền vào, giữ 400 khi input lỗi và 500 khi return value lỗi. Trong production, cần thiết kế thêm request correlation id, message code đã chuẩn hóa, các validation errors an toàn cho client và không để lộ dữ liệu nhạy cảm.

Nếu muốn trả chi tiết field errors, dùng BindingResult của MethodArgumentNotValidException và danh sách ParameterValidationResult của HandlerMethodValidationException. Cần chọn cách ánh xạ annotation/property names ổn định, không phụ thuộc một chuỗi ex.getMessage() có thể đổi giữa phiên bản.

### 8.2. Visitor của HandlerMethodValidationException

Framework cung cấp visitor để phân loại lỗi theo loại tham số HTTP. Ví dụ ở mức ý tưởng:

~~~text
HandlerMethodValidationException
  -> getAllValidationResults()
      -> ParameterValidationResult cho @RequestParam
      -> ParameterValidationResult cho @RequestHeader
      -> ParameterErrors cho object @ModelAttribute/@RequestBody
  -> visitResults(visitor)
      -> requestParam(...)
      -> requestHeader(...)
      -> modelAttribute(...)
      -> other(...)
~~~

Đây là sơ đồ API, không phải Java code có thể biên dịch. Khi cần tổng hợp lỗi theo field, hãy xem đúng Javadoc của phiên bản Spring đang chạy, vì kiểu annotation parameter, visitor callbacks và nullable annotations có thể thay đổi.

### 8.3. Không bắt AOP exception vào advice này rồi ép lỗi

ConstraintViolationException được sinh bởi AOP validation trên service không phải lúc nào cũng là lỗi client. Nó có thể xuất phát từ bug của controller gọi service sai, từ job nội bộ hoặc return-value violation. Nếu xử lý, cần biết bối cảnh và chỉ trả 400 khi chính sách API xác định request gây ra invalid input. Những lỗi invariant nội bộ thông thường nên được báo là lỗi server và ghi metric/alert.

## 9. Ví dụ đầy đủ Java 17+ và Spring Boot 3.3: ba chế độ validation

Ví dụ này dùng **Spring MVC**, embedded Tomcat, Spring Boot 3.3.x / Spring Framework 6.1.x, Java 17+.

Trong một project Gradle đã dùng Spring Boot plugin và repository Maven Central phù hợp, các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Dependency spring-boot-starter-validation mang Bean Validation API và provider thường dùng (Hibernate Validator). Nếu thiếu provider, đừng cho rằng annotation có mặt trên classpath là đủ để mọi constraint được thực thi.

Cấu trúc file:

~~~text
src/main/java/dev/example/methodvalidation/
    MethodValidationApplication.java
    ValidationDemoController.java
    PriceService.java
    ApiValidationAdvice.java
src/main/resources/
    application.yml
src/test/java/dev/example/methodvalidation/
    ValidationDemoControllerTest.java
~~~

### 9.1. Main class

File src/main/java/dev/example/methodvalidation/MethodValidationApplication.java:

~~~java
package dev.example.methodvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodValidationApplication.class, args);
    }
}
~~~

### 9.2. Controller: một DTO validation và một built-in method validation

File src/main/java/dev/example/methodvalidation/ValidationDemoController.java:

~~~java
package dev.example.methodvalidation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ValidationDemoController {

    public record CreateProduct(
            @NotBlank String name,
            @NotNull @Min(1) Integer quantity) {}

    public record ProductView(String name, int quantity) {}

    @PostMapping("/products")
    public ResponseEntity<ProductView> create(
            @Valid @RequestBody CreateProduct body) {

        ProductView result =
                new ProductView(body.name(), body.quantity());

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @GetMapping("/page")
    public Map<String, Integer> page(
            @RequestParam(defaultValue = "1")
            @Min(1) int page) {

        return Map.of("page", page);
    }

    @PostMapping("/products/checked")
    public ResponseEntity<ProductView> createChecked(
            @RequestParam @Min(1) int tenant,
            @Valid @RequestBody CreateProduct body) {

        ProductView result =
                new ProductView(body.name(), body.quantity());

        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @GetMapping("/contract")
    @NotNull
    public String contract(
            @RequestParam(defaultValue = "false") boolean broken) {

        return broken ? null : "valid";
    }
}
~~~

**Không đặt @Validated ở cấp class ValidationDemoController** trong ví dụ này. Đó là điểm có chủ đích để dùng built-in method validation của Framework 6.1+.

Bốn endpoints cho thấy sự khác nhau:

1. POST /api/products: chỉ có @Valid @RequestBody, nên lỗi DTO thường dẫn tới MethodArgumentNotValidException.
2. GET /api/page?page=0: direct @Min trên tham số, nên lỗi thường dẫn tới HandlerMethodValidationException.
3. POST /api/products/checked?tenant=0: direct @Min, nên method validation được chọn; nested constraints của @Valid body cũng tham gia method validation theo quy tắc 6.1+.
4. GET /api/contract?broken=true: @NotNull trên return value bị vi phạm, nên built-in method validation phát hiện lỗi phía server, thường HTTP 500.

### 9.3. Service: vẫn dùng @Validated + AOP

File src/main/java/dev/example/methodvalidation/PriceService.java:

~~~java
package dev.example.methodvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class PriceService {

    @NotNull
    public Integer quote(@Min(1) int quantity) {
        return quantity * 100;
    }
}
~~~

Service không tự nhận HTTP request. Khi một Spring bean khác inject PriceService và gọi quote(0) **qua proxy**, method validation AOP thường phát sinh ConstraintViolationException. Khi gọi quote(2), kết quả trả về là số nguyên 200.

Đoạn service dùng phép nhân int để minh họa. Trong ứng dụng tính tiền thực, không dùng int có nguy cơ overflow cho đơn giá/tiền tệ; dùng BigDecimal với currency, rounding và business rules phù hợp.

**Không thêm @Validated vào controller chỉ vì đã thêm vào service.** Hai đường validation có mục đích và cơ chế xử lý exception khác nhau.

### 9.4. application.yml và cách chạy

Tạo src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Chạy trong thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Kiểm tra request hợp lệ:

~~~bash
curl -i "http://localhost:8080/api/page?page=2"
curl -i -X POST "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","quantity":2}'
~~~

Kết quả chính cần xác nhận: GET trả HTTP 200 và JSON {"page":2}; POST trả HTTP 201 và JSON {"name":"Keyboard","quantity":2}. Date, Content-Length, các HTTP headers khác có thể khác theo environment.

Kiểm tra request không hợp lệ:

~~~bash
curl -i "http://localhost:8080/api/page?page=0"
curl -i -X POST "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"","quantity":2}'
curl -i -X POST \
  "http://localhost:8080/api/products/checked?tenant=0" \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","quantity":2}'
~~~

Cả ba trường hợp đều dự kiến HTTP 400 trong cấu hình demo, nhưng **không nhất thiết có cùng exception type**. Nếu thêm ApiValidationAdvice ở mục 8.1 vào project, response có thể chứa code riêng tương ứng INVALID_BODY hoặc INVALID_METHOD_INPUT.

Return-value validation:

~~~bash
curl -i "http://localhost:8080/api/contract?broken=true"
~~~

Dự kiến lỗi phía server và HTTP 500 theo built-in method validation. Không dùng endpoint cố tình trả sai contract này ở production; nó chỉ hỗ trợ hiểu lý do không được ép mọi validation error về HTTP 400.

## 10. Test MockMvc: kiểm tra behavior thay vì tên exception duy nhất

Với project mục 9 có spring-boot-starter-test, tạo src/test/java/dev/example/methodvalidation/ValidationDemoControllerTest.java:

~~~java
package dev.example.methodvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validQuerySucceeds() throws Exception {
        mvc.perform(get("/api/page").param("page", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(2));
    }

    @Test
    void directParameterConstraintReturns400() throws Exception {
        mvc.perform(get("/api/page").param("page", "0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void objectArgumentValidationReturns400() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\",\"quantity\":2}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void combinedMethodValidationReturns400() throws Exception {
        mvc.perform(post("/api/products/checked")
                .param("tenant", "0")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Keyboard\",\"quantity\":2}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validBodyReturnsCreatedProduct() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Keyboard\",\"quantity\":2}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.quantity").value(2));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các test trên kiểm tra public HTTP behavior và không cần dựa vào một text exception message cụ thể. Với bài kiểm thử tương thích version, có thể thêm assertions về exception type khi mục đích là **giám sát thay đổi cơ chế validation**; tuy nhiên khi nâng framework, test đó phải được cập nhật theo sự thay đổi đã chủ ý.

Để kiểm tra exception type trong Spring MVC test riêng, có thể dùng MockMvc andExpect(result -> ...) để lấy result.getResolvedException(); nhưng đừng biến toàn bộ regression suite thành test implementation detail nếu mục tiêu là HTTP contract.

### 10.1. Kiểm thử service validation đúng cách

Không đủ khi viết new PriceService().quote(0). Đối tượng do toán tử new tạo ra không phải Spring AOP proxy, nên sẽ không kích hoạt method validation interceptor.

Kiểm thử nên lấy PriceService bean được Spring inject từ ApplicationContext và gọi public method qua bean đó:

~~~java
@Autowired
PriceService service;

@Test
void serviceRejectsZeroQuantity() {
    assertThrows(
            jakarta.validation.ConstraintViolationException.class,
            () -> service.quote(0));
}
~~~

Đây là đoạn trích phải đặt trong test class có Spring test context và JUnit static import assertThrows. Nếu ứng dụng tùy chỉnh MethodValidationPostProcessor để adapt constraint violations thành MethodValidationException, cần đổi kỳ vọng exception theo cấu hình thực tế.

### 10.2. Test dữ liệu invalid không thể thay thế test missing/malformed

@Min(1) chỉ đánh giá được sau khi page đã được convert thành int. Với page=abc, binding/type conversion có thể thất bại trước method validation. Với page thiếu và required/default khác, có thể có missing parameter error. Test cả ba:

- Missing.
- Sai kiểu.
- Đúng kiểu nhưng sai constraint.

Nếu chỉ test page=0 và kết luận “validation xử lý toàn bộ lỗi request” thì chưa đủ.

## 11. WebFlux: cùng bản chất, khác exception khi validate object

Spring WebFlux cũng có built-in method validation trên @RequestMapping methods từ Framework 6.1. Nó dùng DispatcherHandler/HandlerAdapter trong reactive pipeline thay vì Servlet DispatcherServlet.

Các tình huống quan trọng:

| Trường hợp WebFlux | Loại lỗi thường gặp |
|---|---|
| @Valid @RequestBody command object, không có direct method constraints | WebExchangeBindException |
| Direct @Min/@NotBlank trên controller parameter ở Framework 6.1+ | HandlerMethodValidationException |
| Return-value method constraint vi phạm | HandlerMethodValidationException với server error |
| @Validated class-level dùng AOP proxy | ConstraintViolationException hoặc MethodValidationException tùy cấu hình |
| JSON sai cú pháp/unsupported media type | Lỗi đọc body/codec/HTTP message riêng |

### 11.1. Ví dụ WebFlux controller

Trong **một project Spring Boot WebFlux riêng** với spring-boot-starter-webflux, spring-boot-starter-validation và spring-boot-starter-test, tạo src/main/java/dev/example/reactive/ReactiveValidationController.java:

~~~java
package dev.example.reactive;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/rx")
public class ReactiveValidationController {

    public record Payload(@NotBlank String name) {}

    @GetMapping("/page")
    public Mono<Map<String, Integer>> page(
            @RequestParam(defaultValue = "1")
            @Min(1) int page) {

        return Mono.just(Map.of("page", page));
    }

    @PostMapping("/payload")
    public Mono<Map<String, String>> payload(
            @Valid @RequestBody Mono<Payload> input) {

        return input.map(
                p -> Map.of("name", p.name()));
    }
}
~~~

Không đặt @Validated ở cấp class controller khi muốn dùng built-in method validation 6.1+. Ở WebFlux, @Valid @RequestBody Mono<Payload> có thể kiểm tra nested object khi reactive body được giải mã; lỗi validation object thường biểu hiện WebExchangeBindException theo cơ chế WebFlux.

### 11.2. Kiểm thử WebTestClient

Tạo src/test/java/dev/example/reactive/ReactiveValidationControllerTest.java:

~~~java
package dev.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = ReactiveValidationController.class)
class ReactiveValidationControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void directMethodConstraintReturns400() {
        client.get().uri("/rx/page?page=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validPageReturnsJson() {
        client.get().uri("/rx/page?page=2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2);
    }

    @Test
    void invalidPayloadReturns400() {
        client.post().uri("/rx/payload")
                .bodyValue(Map.of("name", ""))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Để chạy WebFlux example, cần một @SpringBootApplication class nằm trong package cha của controller và dependencies tương ứng. @WebFluxTest dùng test slice nên không nhất thiết mở một HTTP socket thực. Với controller có injected services, cung cấp mocks/test config; không trộn hai project MVC và WebFlux của ví dụ vào cùng một build mà chưa kiểm tra Boot chọn web application type.

### 11.3. Lưu ý với reactive data và AOP method validation

AOP validation của method trên service reactive có thể liên quan đến thời điểm tạo Publisher và lúc Publisher thực sự phát dữ liệu; cách kiểm tra arguments/return value có thể phụ thuộc hỗ trợ của phiên bản/framework và phương thức proxy. Không khẳng định mọi nested Mono<T> sẽ được validate tại cùng thời điểm như một tham số Java đồng bộ.

Đối với WebFlux controller, ưu tiên cơ chế built-in của phiên bản đang dùng; khi cần validation của nội dung Publisher, kiểm tra @Valid argument binding, codec và WebFlux validation documentation. Không dùng .block() trong event loop chỉ để ép chạy validation.

## 12. Service, application layer và các entry point ngoài HTTP

Controller method validation hướng tới HTTP request. Nhưng business rules còn phải đúng nếu cùng service được gọi từ:

- Job chạy theo lịch.
- Message listener.
- CLI/batch import.
- Unit/integration test.
- GraphQL, gRPC hoặc một API không đi qua annotated Spring MVC/WebFlux handler.
- Event handler hoặc một service khác trong cùng ứng dụng.

Vì thế service có thể dùng @Validated để bảo vệ constraints trên method parameters và return value. Nó là **phòng tuyến bổ sung**, không thay thế validation ở HTTP boundary.

Ví dụ API phải từ chối request có quantity=0 ngay tại controller (HTTP 400); nếu cùng quantity=0 phát sinh do một bug logic khi service được gọi từ nội bộ, đó có thể là lỗi chương trình cần cảnh báo/500, không phải tự động chuyển thành lỗi 400 cho người dùng.

### 12.1. Các constraint cross-parameter

Một method có thể cần quy tắc “startDate <= endDate” hoặc “một trong hai identifier phải có”. Một số Bean Validation provider hỗ trợ cross-parameter constraints trên executable bằng custom @Constraint/ConstraintValidator thích hợp.

Tuy nhiên với các trường hợp đơn giản, một command object có @AssertTrue hay một custom class-level constraint thường dễ hiểu hơn, vì đặt toàn bộ dữ liệu liên quan vào một DTO. Dù dùng cách nào, vẫn cần xác định ranh giới: HTTP request validation hay invariant service/domain, và chọn error mapping theo nguồn lỗi.

### 12.2. Validation không tự thực thi nếu object không được Spring quản lý

AOP method validation cần lời gọi qua Spring proxy. new Service() trong code, new trong unit test không có context, private method hoặc self-invocation có thể tránh interception. Không vì thấy @Min trên method mà cho rằng mọi call path đều được kiểm tra.

Đối với invariant đặc biệt quan trọng, cân nhắc kiểm tra bằng code domain ngay tại phương thức hoặc value object constructor, không chỉ bằng AOP. Annotation làm hợp đồng rõ hơn, nhưng không tự xóa các giới hạn của proxy hoặc transaction boundaries.

## 13. Validation groups và nested constraints

Một API CREATE có thể yêu cầu email bắt buộc trong khi UPDATE có thể cho phép thiếu. Có thể định nghĩa marker interfaces:

~~~java
public interface CreateGroup {}
public interface UpdateGroup {}
~~~

Và DTO dùng groups trong annotations:

~~~java
public record UserInput(
        @NotBlank(groups = CreateGroup.class) String email,
        @Size(min = 3, max = 40) String displayName) {}
~~~

Đây là các Java snippets cần import jakarta.validation.constraints và đặt trong project phù hợp. Nếu @Validated(CreateGroup.class) được dùng trên @RequestBody UserInput ở controller, Spring sẽ yêu cầu group CreateGroup theo cấu hình.

**Lưu ý:** Khi chỉ chọn group CreateGroup, các constraints thuộc Default group có thể không tự được kiểm tra trừ khi nhóm được lựa chọn/sequence tương ứng. Nếu muốn @Size cùng được đánh giá trong cả create/update, cấu hình groups phù hợp thay vì giả định Default luôn tự được gộp.

Dùng @Validated trên **một argument** để chọn nhóm khác với dùng @Validated ở **cấp controller class** để kích hoạt AOP. Sau khi nâng 6.1+, không xóa group validation hợp lệ trên argument trong lúc loại bỏ class-level @Validated khỏi controller.

Với API PATCH, validation groups không tự giữ thông tin **missing vs explicit null** sau deserialization. Chọn kiểu DTO/presence representation riêng khi contract cần phân biệt.

## 14. Missing parameter, null và các constraint không thể thay nhau

### 14.1. required flag và @NotNull

@RequestParam(required=true) quyết định request parameter có bắt buộc ở tầng HTTP binding hay không. @NotNull là Bean Validation constraint trên giá trị Java.

Ví dụ:

~~~java
@GetMapping("/report")
String report(
        @RequestParam(name = "year", required = false)
        @NotNull Integer year) {
    return "year=" + year;
}
~~~

Trong built-in method validation 6.1+, @NotNull có thể đánh giá khi year không được gửi và resolver đưa null. Nhưng nếu đặt required=true, request thiếu có thể bị từ chối ngay trong argument resolver, trước khi method validation kiểm tra @NotNull.

Hai cơ chế này có thể tạo những exception types khác nhau dù đều dẫn đến HTTP 400. Do đó cần test đúng hoàn cảnh: missing, empty, invalid type và out-of-range.

### 14.2. @Valid chỉ cascade, không buộc @RequestBody hiện diện

@RequestBody có required flag riêng; mặc định required=true. Missing entire body có thể tạo lỗi trước khi @Valid kiểm tra DTO. Thêm @NotNull trực tiếp vào tham số @Valid DTO có thể làm method validation được chọn, nhưng không phải cách mặc định nên dùng để thay thế @RequestBody(required=true).

Nếu DTO có @NotBlank name và JSON field name vắng mặt, Bean Validation có thể phát hiện sau deserialization; nếu JSON malformed thì lỗi reader/codec xảy ra trước validation. Xử lý mọi tình huống qua một loại exception duy nhất là không đúng.

### 14.3. Return-value constraints không phải input validation

Một method @NotNull return nhưng thực tế trả null là vi phạm hợp đồng do server tạo ra, thường là 500 ở built-in framework. Không đưa raw stack trace cho client; báo lỗi server chung và ghi thông tin kỹ thuật vào logs/metrics có kiểm soát.

## 15. Khi thay Spring Boot version cần làm gì?

Một checklist migration đáng tin hơn tìm/replace @Validated hàng loạt:

1. Xác nhận Spring Boot version, Spring Framework version, Java baseline và provider Hibernate Validator thực tế.
2. Kiểm tra dependency spring-boot-starter-validation có hay không.
3. Với Boot 2.x -> 3.x, thay javax.validation.* thành jakarta.validation.* và rà soát thư viện tương thích Jakarta.
4. Phân loại @Validated theo vị trí: controller class, controller argument group, service class, custom interceptor.
5. Với MVC/WebFlux controller trên Framework 6.1+, thử loại bỏ **class-level @Validated** để dùng built-in validation.
6. Xác nhận direct constraints trên @RequestParam/@PathVariable và return values được thực thi.
7. Kiểm tra @Valid DTO vẫn có binding/validation bình thường khi method không có direct constraints.
8. Nếu controller có cả @Valid DTO và @Min query, kiểm tra HandlerMethodValidationException và response schema.
9. Bổ sung hoặc cập nhật @ControllerAdvice để xử lý MethodArgumentNotValidException và HandlerMethodValidationException (MVC) hoặc WebExchangeBindException và HandlerMethodValidationException (WebFlux).
10. Không xóa @Validated service nếu vẫn cần MethodValidationPostProcessor/AOP.
11. Kiểm tra các API thủ công return HTTP 400 có đang che server invariant violations không.
12. Kiểm tra self-invocation/final/private methods trong service khi thấy annotation không có tác dụng.
13. Chạy test input invalid, return invalid, nested DTO invalid, missing/malformed, các validation groups.
14. Dùng dependency thực của production để chạy integration tests; kiểm tra lỗi trong logs và metrics sau deploy.
15. Chỉ sau QA mới nâng version/dời cơ chế xử lý cũ; không suy ra behavior chỉ từ việc compile thành công.

Không nên dùng hack gọi validate() thủ công trong mọi controller khi framework đã hỗ trợ validation. Dùng cơ chế chuẩn sẽ giảm lỗi lặp, nhất quán về argument binding và có thông tin kết quả validation đầy đủ hơn.

## 16. Các lỗi thường gặp và cách chẩn đoán

### Lỗi 1 — Đặt @Validated ở controller trong Spring 6.1+ rồi thắc mắc không có HandlerMethodValidationException

Nếu class-level @Validated chuyển lời gọi qua AOP proxy, exception có thể là ConstraintViolationException/MethodValidationException thay vì built-in HandlerMethodValidationException. Xác nhận class annotation, AOP proxy và framework version; bỏ class-level @Validated ở controller khi mục tiêu là cơ chế web tích hợp.

### Lỗi 2 — Bỏ @Validated khỏi service khi sửa controller

Service method validation AOP thường dựa vào class-level @Validated. Sau khi xóa, các constraint có thể không chạy khi service được gọi. Chỉ áp dụng hướng dẫn bỏ class-level @Validated cho controller muốn dùng built-in 6.1+; giữ service configuration có chủ đích.

### Lỗi 3 — @Valid @RequestBody không ném cùng loại exception khi thêm @Min ở method

Thêm một direct constraint làm method validation được lựa chọn. HandlerMethodValidationException có thể thay cho MethodArgumentNotValidException trong tình huống vi phạm. Cập nhật advice và tests để bao phủ cả hai.

### Lỗi 4 — @Valid trên String được hiểu là bắt buộc

@Valid không phải direct constraint. @NotBlank hoặc @NotNull mới biểu diễn rule tương ứng. Chọn annotation dựa trên nội dung cần kiểm tra.

### Lỗi 5 — @Min(1) trên Integer vẫn cho null đi qua

Các constraints miền số như @Min thường coi null là hợp lệ. Nếu field cần có, thêm @NotNull hoặc required flag phù hợp. Primitive không chứa null, nhưng missing request vẫn có thể lỗi binding trước validation.

### Lỗi 6 — Không thêm provider Bean Validation

Chỉ có jakarta.validation-api chưa bảo đảm validation runtime. Trong Spring Boot 3.x, spring-boot-starter-validation thường cung cấp Hibernate Validator. Nếu annotation “không chạy”, kiểm tra dependency tree, auto-configuration và Validator bean.

### Lỗi 7 — Tạo service bằng new và mong AOP kiểm tra

new PriceService() không đi qua Spring proxy; method constraint của service có thể không chạy. Test với bean được inject từ ApplicationContext hoặc kiểm tra explicit ở domain.

### Lỗi 8 — Gọi this.quote(0) trong cùng @Validated service

Self-invocation bỏ qua proxy interception trong AOP thông thường. Refactor call path hoặc bảo vệ invariant bằng code bên trong method.

### Lỗi 9 — Bắt ConstraintViolationException và trả 400 cho mọi nguồn

Nếu exception phát sinh do service bug hoặc return contract, lỗi thuộc server. Chỉ map thành lỗi client khi xác định rõ rằng client input vi phạm hợp đồng HTTP tại boundary.

### Lỗi 10 — Vi phạm return-value bị trả 400

HandlerMethodValidationException ở built-in 6.1+ phân biệt input và return value; return violation thường 500. Error handler phải giữ status hoặc phân nhánh theo isForReturnValue().

### Lỗi 11 — Test chỉ một endpoint hợp lệ

Dữ liệu hợp lệ không chứng minh validation được kích hoạt. Viết tests cho query âm, body thiếu field, nested object lỗi, return null và service call qua proxy.

### Lỗi 12 — Nhầm MVC với WebFlux

MVC có MethodArgumentNotValidException cho argument object, WebFlux có WebExchangeBindException. Cả hai có built-in method validation từ Framework 6.1, nhưng pipeline và error handlers khác. Dùng đúng class/package của stack.

### Lỗi 13 — Nhầm @Validated group với class-level AOP

@Validated(Group.class) trên argument chọn nhóm validation, không nhất thiết kích hoạt proxy class. Không xóa group validation chỉ vì đang migrate controller class-level @Validated.

### Lỗi 14 — Gộp mọi lỗi 400 thành một message chung không có cấu trúc

Input conversion, missing field, Bean Validation và application policy vi phạm có nguồn khác nhau. Trả schema lỗi nhất quán nhưng vẫn phân loại code/field an toàn để client biết cần sửa gì.

### Lỗi 15 — Cấu hình MethodValidationPostProcessor trùng hoặc không đúng

Spring Boot đã auto-configure một số hạ tầng validation khi provider có trên classpath. Tự khai báo processor không đúng có thể gây chồng proxy hoặc thay exception type. Nếu có cấu hình custom, kiểm tra purpose và test lại sau upgrade.

### Lỗi 16 — Không kiểm tra timeout và asynchronous/reactive return value

Method validation không tự giải quyết mọi quy tắc khi Publisher phát dữ liệu sau khi handler trả về. Trong WebFlux, cần kiểm tra tài liệu validation cho reactive @RequestBody và return types, cũng như nơi xảy ra lỗi trước/sau khi response committed.

## 17. Ma trận kiểm thử tối thiểu

| Test case | Cơ chế muốn kiểm tra | Kết quả định hướng |
|---|---|---|
| GET /api/page?page=2 | Direct @Min, hợp lệ | 200 + page=2 |
| GET /api/page?page=0 | Direct @Min, 6.1+ built-in | 400, HandlerMethodValidationException |
| GET /api/page?page=abc | Type conversion | 400, không nhất thiết method validation |
| POST /api/products JSON hợp lệ | @Valid @RequestBody | 201 |
| POST /api/products name="" | @Valid DTO riêng | 400, thường MethodArgumentNotValidException |
| POST /api/products quantity=0 | @Min trên DTO | 400, thường MethodArgumentNotValidException |
| POST /api/products/checked tenant=0 | Direct method constraint và @Valid DTO | 400, thường HandlerMethodValidationException |
| GET /api/contract?broken=true | @NotNull return value | 500, server-side violation |
| PriceService bean proxy.quote(0) | Service AOP validation | ConstraintViolationException hoặc kiểu adapt theo config |
| new PriceService().quote(0) | Bỏ qua AOP | Không dùng làm test xác nhận constraint AOP |
| this.quote(0) trong cùng service | Self-invocation | Có thể bỏ qua interception |
| WebFlux GET /rx/page?page=0 | Built-in reactive controller method validation | 400 |
| WebFlux POST invalid @Valid body | Object argument validation | 400, thường WebExchangeBindException |
| Chỉ còn controller @Validated class-level | Legacy AOP behavior | Exception type có thể khác built-in |
| Thiếu Bean Validation provider | Runtime validation activation | Cần kiểm tra dependency/config, không giả định annotation chạy |
| Group CreateGroup trên DTO | Validation groups | Chỉ các constraints thuộc group(s) được chọn |

Ma trận giúp tách lỗi dữ liệu, lỗi cấu hình validation, lỗi return contract và lỗi AOP. Khi nâng phiên bản, test HTTP status/body là tiêu chí hành vi, còn test exception class là bằng chứng cơ chế cần dùng một cách có chủ đích.

## 18. Quy tắc thiết kế production

**Boundary validation:** Kiểm tra định dạng request, dữ liệu bắt buộc, length, numeric range và whitelist gần HTTP boundary để phản hồi 4xx rõ ràng. Không tin query/body chỉ vì đã convert thành Java object.

**Service validation:** Dùng @Validated/AOP ở service khi các phương thức được gọi từ nhiều entry points. Nhưng hiểu proxy limitations và không giao toàn bộ invariant quan trọng cho một annotation có thể bị bypass qua self-invocation.

**Domain validation:** Những rule bắt buộc đúng trong mọi hoàn cảnh, như amount >0, trạng thái hợp lệ hoặc ràng buộc tổng, nên được bảo vệ thêm ở domain/value object/service code.

**Error contract:** Có response schema nhất quán, phân biệt lỗi input 400 với lỗi server 500. Tránh lộ stack trace, validation rejected values nhạy cảm hoặc internal model implementation.

**Version-aware configuration:** Chọn cách dùng @Validated theo Framework version và vị trí class. Controller Framework 6.1+ ưu tiên built-in khi phù hợp; service vẫn có thể cần @Validated AOP. Rà soát classpath và Jakarta migration khi upgrade Boot.

**Test và observability:** Test invalid query, invalid body, combined constraints, missing/malformed, return validation và proxy service. Theo dõi tỷ lệ 400/500 và lỗi validation không bị phân loại nhầm.

## 19. Câu hỏi tự kiểm tra

**Câu 1. @Valid có phải annotation @Constraint không?**  
Không. @Valid kích hoạt cascade validation của object; direct constraints như @Min/@NotBlank/@NotNull mới mô tả quy tắc kiểm tra giá trị.

**Câu 2. @Valid @RequestBody sai dữ liệu luôn ném MethodArgumentNotValidException không?**  
Không. Đây là trường hợp thường gặp nếu chỉ validation một object argument ở MVC. Khi method cần direct method validation, HandlerMethodValidationException có thể được sử dụng từ Framework 6.1+.

**Câu 3. Spring Framework 6.1 thay đổi gì ở controller?**  
Nó có built-in method validation trong MVC/WebFlux cho @RequestMapping methods, không đòi hỏi AOP proxy riêng cho controller theo cách cũ; thêm HandlerMethodValidationException để báo kết quả.

**Câu 4. Có nên xóa tất cả @Validated khi nâng từ Boot 3.1 sang 3.2 không?**  
Không. Chỉ cân nhắc loại class-level @Validated ở controllers muốn dùng built-in validation. Services sử dụng AOP method validation vẫn thường cần @Validated.

**Câu 5. @Min(1) trên Integer có nghĩa field bắt buộc không?**  
Không. Null thường pass @Min; thêm @NotNull hoặc required flag nếu cần bắt buộc.

**Câu 6. Vì sao ConstraintViolationException từ service không tự là 400?**  
Vì nó có thể là bug nội bộ, không phải lỗi HTTP input. Việc map status cần căn cứ ranh giới và ngữ nghĩa lỗi.

**Câu 7. Vì sao return-value method validation có thể tạo 500?**  
Vì chính server trả giá trị trái hợp đồng của method. HandlerMethodValidationException phân biệt return violation với input violation.

**Câu 8. @Validated service có kiểm tra khi new PriceService() hoặc self-invocation không?**  
Không theo cơ chế AOP proxy thông thường, vì lời gọi không đi qua proxy.

**Câu 9. WebFlux có dùng MethodArgumentNotValidException cho DTO như MVC không?**  
Không. WebFlux dùng WebExchangeBindException cho validation trên argument object; built-in method validation có thể dùng HandlerMethodValidationException.

## 20. Tóm tắt

Để hiểu **kiểm tra phương thức và sự thay đổi hỗ trợ theo phiên bản Spring**, cần giữ bốn phân biệt:

1. **Object argument validation:** @Valid/@Validated trên một DTO, với MethodArgumentNotValidException ở MVC hoặc WebExchangeBindException ở WebFlux trong tình huống phù hợp.
2. **Built-in web method validation từ Spring Framework 6.1:** direct constraints trên controller method parameter/return value; HandlerMethodValidationException; thường 400 nếu input sai và 500 nếu return value vi phạm.
3. **AOP method validation của Spring beans:** @Validated ở cấp service/component, MethodValidationPostProcessor và proxy; thường ConstraintViolationException, có thể MethodValidationException nếu cấu hình thích nghi.
4. **Version migration:** Boot 2.x dùng javax.validation; Boot 3.x dùng jakarta.validation; trước 6.1 controller thường cần @Validated class-level/AOP, từ 6.1 controller có built-in support và nên bỏ class-level @Validated để dùng cơ chế đó.

Giải pháp bền vững không phải gắn annotation đại trà. Hãy xác định dữ liệu thuộc HTTP argument hay service contract, hiểu exception type theo Framework version, kiểm tra cả input lẫn return, và viết test để chắc chắn validation được thực thi đúng nơi, đúng thời điểm.

## 21. Tài liệu chính thức

- Spring Framework 6.2 — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Spring WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework — Jakarta Bean Validation và method validation AOP: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — AOP proxying và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Spring Framework 6.1 Javadoc — HandlerMethodValidationException: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework Javadoc — MethodValidationPostProcessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework — Web MVC controller method validation change introduced in 6.1: https://spring.io/blog/2023/07/13/spring-framework-6-1-m2-released/
