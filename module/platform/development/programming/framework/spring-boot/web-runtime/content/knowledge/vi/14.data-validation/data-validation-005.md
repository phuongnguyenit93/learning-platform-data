# Phân biệt lỗi binding, lỗi Bean Validation và lỗi nghiệp vụ trong Spring Boot

## 1. Ba tầng xử lý dữ liệu không giống nhau

Một HTTP request đi vào Spring Boot có thể thất bại ở ba tầng độc lập:

1. **Binding, conversion, deserialization:** framework không lấy hoặc chuyển được dữ liệu từ HTTP thành giá trị Java mà controller yêu cầu. Ví dụ query seats=abc nhưng tham số có kiểu int, hoặc JSON chứa seats="many" nhưng DTO yêu cầu Integer.
2. **Bean Validation:** framework đã tạo được dữ liệu theo kiểu phù hợp, nhưng dữ liệu vi phạm constraints như @NotBlank, @NotNull, @Min, @Size hoặc custom constraint. Ví dụ seats=0 chuyển thành Integer thành công nhưng vi phạm @Min(1).
3. **Lỗi nghiệp vụ:** dữ liệu đúng kiểu và đúng constraints, nhưng không thỏa trạng thái hiện tại của domain. Ví dụ sự kiện hết chỗ, email đã tồn tại, không đủ tồn kho, hoặc đơn hàng đã hủy.

Luồng tổng quát:

~~~text
HTTP request
    |
    v
Route, method, Content-Type, HTTP body
    |
    v
Binding / type conversion / JSON deserialization
    |---- thất bại ----> thường 400
    v
Bean Validation / method validation
    |---- thất bại ----> thường 400
    v
Service / domain rules
    |---- xung đột ---> 409 hoặc status khác theo API contract
    v
Transaction / persistence / response
~~~

**Không phải mọi HTTP 400 đều là Bean Validation.** JSON sai cú pháp không thể đi tới @Min nếu chưa tạo được DTO; còn số 0 là Integer hợp lệ nhưng có thể vi phạm constraint. Tương tự, đầu vào đáp ứng @Min vẫn có thể không được chấp nhận vì số lượng tồn kho không đủ.

Bài này sử dụng **Spring Boot 3.5.x, Spring Framework 6.2.x, Jakarta Validation và Java 17+**. Ví dụ hoàn chỉnh dùng Spring MVC/Servlet, cuối bài có bảng đối chiếu với WebFlux.

## 2. So sánh ba loại lỗi theo tình huống

Giả sử POST /api/bookings nhận JSON:

~~~json
{"eventId":"EVENT-10","seats":2}
~~~

DTO yêu cầu eventId không được để trống và seats ít nhất 1. Service quy định eventId "sold-out" không còn ghế.

| Input / tình trạng | Loại lỗi | Nguyên nhân | HTTP trong API ví dụ |
|---|---|---|---|
| seats="many" | JSON decode/type conversion | Chuỗi không đổi được thành Integer | 400 |
| Body thiếu dấu ngoặc JSON | JSON parse | Cú pháp body sai | 400 |
| seats=0 | Bean Validation | Vi phạm @Min(1) | 400 |
| seats=null hoặc không gửi | Bean Validation | Vi phạm @NotNull | 400 |
| eventId="" | Bean Validation | Vi phạm @NotBlank | 400 |
| eventId="sold-out", seats=2 | Business rule | Dữ liệu hợp lệ nhưng hết chỗ | 409 |
| eventId="EVENT-10", seats=2 | Thành công | Qua cả ba tầng | 201 |

Đừng chỉ dựa vào status để suy ra tầng lỗi. Cùng là 400, nhưng client phải sửa kiểu hoặc định dạng với binding error, trong khi validation error yêu cầu sửa giá trị trường theo constraint.

**Ngoại lệ quan trọng:** Một BindingResult có thể chứa cả FieldError do không bind được và FieldError do constraint. Vì vậy, không thể phân loại toàn bộ error response chỉ từ tên exception mà không xem chi tiết lỗi bên trong.

## 3. Binding, conversion và deserialization

Spring lấy HTTP input từ @PathVariable, @RequestParam, @RequestHeader, @CookieValue, @ModelAttribute hoặc @RequestBody. Sau đó framework chuyển kiểu theo ConversionService, PropertyEditor, HttpMessageConverter hoặc HttpMessageReader phù hợp.

Ví dụ:

~~~java
@GetMapping("/estimate")
public Map<String, Integer> estimate(@RequestParam int seats) {
    return Map.of("estimatedCost", seats * 100);
}
~~~

GET /estimate?seats=abc không thể chuyển "abc" sang int. Với Spring MVC và @RequestParam đơn giản, tình huống này thường dẫn đến MethodArgumentTypeMismatchException rồi HTTP 400. Controller method không được gọi.

GET /estimate?seats=-1 lại khác: "-1" chuyển sang int thành công. Nếu không có @Min hoặc logic kiểm tra riêng, tham số vẫn có thể đến method body. Giá trị âm **không phải lỗi binding** chỉ vì không phù hợp ý định nghiệp vụ.

### Những lỗi HTTP input cần phân biệt

| Tình huống | MVC exception thường gặp | HTTP thường gặp |
|---|---|---|
| @RequestParam không chuyển kiểu | MethodArgumentTypeMismatchException | 400 |
| Thiếu @RequestParam bắt buộc | MissingServletRequestParameterException | 400 |
| JSON syntax sai, field không decode được | HttpMessageNotReadableException | 400 |
| @RequestBody required nhưng body thiếu | HttpMessageNotReadableException | 400 |
| Content-Type không được hỗ trợ | HttpMediaTypeNotSupportedException | 415 |
| HTTP method không được hỗ trợ | HttpRequestMethodNotSupportedException | 405 |
| Không thể tạo response theo Accept | HttpMediaTypeNotAcceptableException | 406 |

Các trường hợp này phát sinh trước logic nghiệp vụ. Tuy nhiên chúng cũng không phải cùng một loại validation. Không nên bắt tất cả rồi trả một câu "Invalid data" nếu API client cần thông tin cụ thể để sửa.

### @ModelAttribute có thể ghi lỗi chuyển kiểu vào BindingResult

Với form/query object, WebDataBinder gán từng field và thu thập lỗi. Ví dụ class:

~~~java
public class SearchForm {
    private Integer minSeats;

    public Integer getMinSeats() {
        return minSeats;
    }

    public void setMinSeats(Integer minSeats) {
        this.minSeats = minSeats;
    }
}
~~~

Controller minh họa:

~~~java
@GetMapping("/search")
public ResponseEntity<?> search(
        @ModelAttribute SearchForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
                result.getFieldErrors().stream()
                        .map(error -> error.getField())
                        .toList());
    }
    return ResponseEntity.ok(form);
}
~~~

Đây là hai snippet minh họa cần imports và class trong ứng dụng, không phải file Java độc lập. Với /search?minSeats=abc, lỗi typeMismatch có thể được ghi trong BindingResult; handler có thể chủ động trả HTTP 400.

**BindingResult phải đặt ngay sau tham số mà nó theo dõi.** Đặt sau một tham số không liên quan không bảo đảm Spring sử dụng nó cho target mong muốn.

## 4. Phân biệt FieldError từ binding và từ validation

Spring FieldError lưu thông tin về field gặp lỗi. Các phương thức hữu ích:

- getField(): tên trường.
- getCode()/getCodes(): mã lỗi theo cơ chế Spring MessageCodesResolver.
- getDefaultMessage(): thông báo mặc định.
- isBindingFailure(): **true** khi lỗi là binding failure như typeMismatch; **false** khi lỗi do validation.
- getRejectedValue(): dữ liệu bị từ chối, có thể nhạy cảm, **không đưa thẳng vào HTTP response hoặc log**.

Ví dụ:

~~~java
for (FieldError error : result.getFieldErrors()) {
    String kind = error.isBindingFailure()
            ? "binding"
            : "constraint";
    System.out.println(error.getField() + ": " + kind);
}
~~~

Mã cần import org.springframework.validation.FieldError. Đây là cách phân biệt chi tiết đáng tin cậy khi BindingResult chứa nhiều loại lỗi.

**Một MethodArgumentNotValidException không nhất thiết chỉ chứa lỗi Bean Validation.** Trong một số đường xử lý binding đối tượng, các lỗi chuyển kiểu và constraint đều nằm trong kết quả. Ngược lại, @RequestBody sai JSON syntax thường không tạo được DTO và dẫn đến HttpMessageNotReadableException ngay ở bước giải mã.

## 5. Bean Validation là gì?

Jakarta Bean Validation cho phép khai báo constraints trên DTO, method parameter, property và return value. Với Spring Boot 3.5, thêm starter validation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Sử dụng package jakarta.validation, không phải javax.validation trên Spring Boot 3.x.

Ví dụ DTO:

~~~java
public record CreateBookingRequest(
        @NotBlank String eventId,
        @NotNull @Min(1) Integer seats
) {}
~~~

- @NotBlank dành cho CharSequence, kiểm tra null, rỗng hoặc chỉ có whitespace.
- @NotNull buộc reference không null.
- @Min(1) kiểm tra số ít nhất 1; null riêng lẻ thường không vi phạm @Min, nên thêm @NotNull nếu field bắt buộc.
- @Size kiểm tra độ dài hoặc số phần tử của kiểu được hỗ trợ; **không đồng nghĩa kích thước request theo byte**.
- @Email kiểm tra định dạng, không chứng minh email có thể nhận thư hoặc chưa tồn tại trong database.
- @Valid kích hoạt cascade validation cho object con khi phù hợp; **@Valid tự nó không phải constraint**.

Bean Validation phù hợp với những điều kiện có thể xác minh từ input/DTO: bắt buộc, length, range, format, nested constraints và quan hệ giữa field nếu viết custom constraint đúng cách.

Nó không tự biết trạng thái kho hàng, số dư ngân hàng, sự kiện hết chỗ hay giao dịch cạnh tranh đang cập nhật cùng dữ liệu. Những rule này cần service/domain và thường phải có transaction hoặc database constraint.

## 6. Object validation và method validation trong Spring MVC 6.2

Spring MVC hiện đại có hai đường validation chính:

**Object validation** thường được kích hoạt khi một @ModelAttribute, @RequestBody hoặc @RequestPart dùng @Valid/@Validated phù hợp, và không có direct method constraint làm thay đổi đường validation. Lỗi thường là MethodArgumentNotValidException (hoặc được cung cấp qua BindingResult nếu khai báo đúng chỗ).

~~~java
@PostMapping("/bookings")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateBookingRequest request) {
    return ResponseEntity.ok().build();
}
~~~

**Method validation** áp dụng khi có @Min, @NotBlank hoặc constraint khác trực tiếp trên tham số controller method hay return value. Spring MVC 6.1+ có built-in support. Lỗi thường là HandlerMethodValidationException.

~~~java
@GetMapping("/guarded-estimate")
public Map<String, Integer> guardedEstimate(
        @RequestParam @Min(1) int seats) {
    return Map.of("estimatedCost", seats * 100);
}
~~~

GET /guarded-estimate?seats=0 chuyển kiểu int thành công, sau đó vi phạm method constraint.

**Hai điểm dễ sai:**

1. @Valid trên một DTO không tự có nghĩa tất cả lỗi sẽ là MethodArgumentNotValidException. Nếu method có direct constraints khác, method validation có thể bao phủ cả nested constraints.
2. @Validated ở class-level controller có thể kích hoạt AOP-based method validation của cách cũ, làm exception path khác built-in controller validation. Khi muốn dùng built-in 6.2 method validation, hãy đọc hướng dẫn nâng cấp và bỏ class-level @Validated ở controller nếu phù hợp.

HandlerMethodValidationException.getStatusCode() thường là **400 cho input constraint violation** và **500 cho return-value constraint violation**. Server trả response sai constraint của chính mình không phải lỗi của request client.

## 7. Lỗi nghiệp vụ thuộc tầng service/domain

Một request có eventId và seats đúng format vẫn có thể bị từ chối:

- Sự kiện hết chỗ.
- Khách hàng đã đặt chỗ trùng.
- Đơn hàng bị hủy hoặc đã giao.
- Số dư không đủ.
- Kho hàng không đủ khi có nhiều giao dịch cùng chạy.
- Voucher hợp lệ về ký tự nhưng đã hết hạn.
- Trạng thái của resource không cho phép thao tác.

Ví dụ:

~~~java
if (event.isSoldOut()) {
    throw new BookingConflictException(
            "Event is fully booked");
}
~~~

Đây là snippet minh họa cần event và class exception do domain định nghĩa. Đừng biến mọi rule stateful thành custom @Constraint truy vấn database. Một rule có thể thay đổi giữa bước validate và bước commit, tạo race condition.

**Phân tầng khuyến nghị:** request DTO và Bean Validation bảo vệ input contract; service/domain bảo vệ invariants; database unique constraint, locking hoặc transaction bảo vệ trước cạnh tranh. ControllerAdvice chuyển domain exception thành HTTP status được contract API quy định.

Một lỗi database không phải luôn là business conflict. Chỉ map một unique constraint violation sang 409 khi có căn cứ đúng constraint và domain context; không catch toàn bộ DataIntegrityViolationException rồi mặc định báo "trùng dữ liệu".

## 8. HTTP status: không phải một công thức cứng

| Vấn đề | Status thường hợp lý | Ghi chú |
|---|---|---|
| Binding/query/path không chuyển kiểu | 400 Bad Request | Client sửa format/type |
| JSON malformed hoặc không deserialize được | 400 Bad Request | DTO chưa được validate |
| Bean Validation input thất bại | 400 Bad Request | Có thể trả fieldErrors |
| Thiếu auth | 401 Unauthorized | Không phải validation |
| Không đủ quyền | 403 Forbidden | Security/permission |
| Không tìm thấy resource | 404 Not Found | Phân biệt API route và domain entity |
| HTTP method không hỗ trợ | 405 Method Not Allowed | Không biến thành validation 400 |
| Conflict do state/unique | 409 Conflict | Client cần thay đổi hoặc refresh state |
| Semantic request không xử lý được theo API contract | 422 Unprocessable Content | Không bắt buộc dùng cho mọi business rule |
| Lỗi server nội bộ không mong đợi | 500 | Không đổ lỗi cho client |

**Business error không mặc định là HTTP 422.** Status 409 hợp lý cho trạng thái resource xung đột, 422 cho trường hợp nội dung hợp lệ về syntax/media type nhưng không thực hiện được theo semantic rule mà contract đã chọn, 403 cho permission, 404 khi resource không tồn tại. Cần một chính sách nhất quán, được tài liệu hóa.

Không catch RuntimeException rồi trả 400 để "thống nhất định dạng". Việc đó che lỗi lập trình/DB và làm monitoring sai lệch.

## 9. ProblemDetail và mã lỗi ổn định

Spring Framework 6.x cung cấp org.springframework.http.ProblemDetail, biểu diễn HTTP problem response theo mô hình Problem Details. Có thể bổ sung extension fields, chẳng hạn code và fieldErrors.

Ví dụ JSON minh họa:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request violates input constraints",
  "code": "VALIDATION_ERROR",
  "fieldErrors": [
    {"field": "eventId", "kind": "constraint", "message": "must not be blank"},
    {"field": "seats", "kind": "constraint", "message": "must be greater than or equal to 1"}
  ]
}
~~~

Các message phụ thuộc locale/validation provider. Client nên xử lý code ổn định và field names thay vì parse một chuỗi tiếng Anh.

Ví dụ conflict:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Event is fully booked",
  "code": "BOOKING_CONFLICT"
}
~~~

Đây là **API contract tự định nghĩa**, không phải body mặc định Spring chắc chắn trả trong mọi ứng dụng.

| Code của API ví dụ | Phân loại | Client có thể làm |
|---|---|---|
| BINDING_ERROR | Query/path parameter sai | Sửa type hoặc bổ sung parameter |
| BODY_PARSE_ERROR | JSON sai syntax/type | Gửi lại body đúng schema |
| VALIDATION_ERROR | DTO constraint | Sửa fieldErrors |
| METHOD_VALIDATION_ERROR | Direct method parameter constraint | Sửa tham số |
| BOOKING_CONFLICT | Domain conflict | Refresh trạng thái hoặc chọn resource khác |
| INTERNAL_ERROR | Lỗi server | Không coi là input invalid |

Đừng đưa raw rejectedValue, password, token, SQL exception, Java stacktrace hoặc root cause từ JSON decoder vào body gửi client.

## 10. Dự án Spring Boot 3.5.x / Java 17+ chạy được

### 10.1. Dependencies và cấu trúc

Tạo Maven project đã có parent/BOM Spring Boot, thêm:

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

Đây là phần dependencies trong pom.xml đã cấu hình Spring Boot dependency management, không phải pom.xml đầy đủ.

Các file:

~~~text
src/main/java/example/validation/
    DemoApplication.java
    CreateBookingRequest.java
    BookingResponse.java
    BookingConflictException.java
    BookingService.java
    BookingController.java
    BookingErrorAdvice.java
src/test/java/example/validation/
    BookingControllerTest.java
~~~

### 10.2. Application

Tệp DemoApplication.java:

~~~java
package example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. Request và response DTO

Tệp CreateBookingRequest.java:

~~~java
package example.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateBookingRequest(
        @NotBlank String eventId,
        @NotNull @Min(1) Integer seats
) {}
~~~

Tệp BookingResponse.java:

~~~java
package example.validation;

public record BookingResponse(
        String bookingId,
        String eventId,
        int seats
) {}
~~~

Sử dụng Integer để phân biệt missing/null với số 0, nhờ @NotNull và @Min. @NotBlank đảm bảo eventId có ký tự khác whitespace nhưng chưa đảm bảo event tồn tại trong domain.

### 10.4. Domain exception và service

Tệp BookingConflictException.java:

~~~java
package example.validation;

public class BookingConflictException extends RuntimeException {

    public BookingConflictException(String message) {
        super(message);
    }
}
~~~

Tệp BookingService.java:

~~~java
package example.validation;

import org.springframework.stereotype.Service;

@Service
public class BookingService {

    public BookingResponse create(CreateBookingRequest request) {
        if ("sold-out".equalsIgnoreCase(request.eventId())) {
            throw new BookingConflictException(
                    "Event is fully booked");
        }

        // Demo không lưu database; bookingId chỉ là hằng mẫu.
        return new BookingResponse(
                "BKG-DEMO-001",
                request.eventId(),
                request.seats());
    }
}
~~~

Ở đây business conflict được ném sau khi controller đã nhận input hợp lệ. Trong sản phẩm thật, service còn cần kiểm tra invariants độc lập với controller, transaction, concurrency và database constraints.

### 10.5. Controller thể hiện ba đường đi

Tệp BookingController.java:

~~~java
package example.validation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookingResponse> create(
            @Valid @RequestBody CreateBookingRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request));
    }

    @GetMapping("/estimate")
    public Map<String, Integer> estimate(
            @RequestParam int seats) {
        return Map.of("estimatedCost", seats * 100);
    }

    @GetMapping("/guarded-estimate")
    public Map<String, Integer> guardedEstimate(
            @RequestParam @Min(1) int seats) {
        return Map.of("estimatedCost", seats * 100);
    }
}
~~~

POST /api/bookings kiểm tra DTO, sau đó gọi service và có thể phát sinh business conflict. GET /estimate?seats=abc thất bại khi conversion. GET /guarded-estimate?seats=0 conversion thành công nhưng vi phạm direct constraint. Không đặt @Validated ở class-level controller này nếu muốn đi theo built-in MVC method validation của Spring Framework 6.2.

## 11. @RestControllerAdvice phân loại exception và sinh ProblemDetail

Tệp BookingErrorAdvice.java:

~~~java
package example.validation;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class BookingErrorAdvice {

    private static ResponseEntity<ProblemDetail> problem(
            HttpStatusCode status, String code, String detail) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(status, detail);
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }

    @ExceptionHandler({
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestParameterException.class
    })
    public ResponseEntity<ProblemDetail> binding(Exception ex) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "BINDING_ERROR",
                "A required request parameter is missing or has an invalid type");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> bodyParse(
            HttpMessageNotReadableException ex) {
        return problem(
                HttpStatus.BAD_REQUEST,
                "BODY_PARSE_ERROR",
                "Request body is missing, malformed, or incompatible with the expected type");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> dtoValidation(
            MethodArgumentNotValidException ex) {

        List<Map<String, String>> fields =
                ex.getBindingResult().getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message", error.getDefaultMessage() == null
                                        ? "Invalid value"
                                        : error.getDefaultMessage(),
                                "kind", error.isBindingFailure()
                                        ? "binding"
                                        : "constraint"))
                        .toList();

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request violates input constraints");
        body.setProperty("code", "VALIDATION_ERROR");
        body.setProperty("fieldErrors", fields);
        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> methodValidation(
            HandlerMethodValidationException ex) {

        HttpStatusCode status = ex.getStatusCode();
        boolean serverError = status.is5xxServerError();

        return problem(
                status,
                serverError
                        ? "INTERNAL_ERROR"
                        : "METHOD_VALIDATION_ERROR",
                serverError
                        ? "Server response contract failed"
                        : "Request method parameter constraints failed");
    }

    @ExceptionHandler(BookingConflictException.class)
    public ResponseEntity<ProblemDetail> conflict(
            BookingConflictException ex) {
        return problem(
                HttpStatus.CONFLICT,
                "BOOKING_CONFLICT",
                ex.getMessage());
    }
}
~~~

Chú ý các đường đi:

- Query sai kiểu hoặc thiếu parameter: BINDING_ERROR / 400.
- HTTP body không giải mã được: BODY_PARSE_ERROR / 400.
- DTO @Valid thất bại: VALIDATION_ERROR / 400, chứa FieldErrors. Cờ isBindingFailure phân biệt lỗi binding và constraint bên trong kết quả.
- Direct method parameter constraint: METHOD_VALIDATION_ERROR / 400 khi input không hợp lệ.
- Return-value constraint bị vi phạm: status có thể là 500; ví dụ giữ 5xx và không đổ lỗi cho client.
- Domain BookingConflictException: BOOKING_CONFLICT / 409.

Trong API thật, nên bổ sung getGlobalErrors() nếu DTO có class-level/cross-field constraints. Ví dụ chỉ chuyển các FieldError để tập trung vào lỗi ba tầng. Những exception khác như HTTP 415, 405 hoặc 406 có thể được infrastructure mặc định xử lý nếu không khai báo handler riêng.

Không dùng global @ExceptionHandler(Exception.class) trả 400 cho tất cả. Nó che lỗi lập trình và làm sai HTTP semantics. Không đưa rejectedValue hoặc nguyên văn ex.getCause() vào response; chúng có thể chứa dữ liệu nhạy cảm.

## 12. Kiểm thử bằng MockMvc

Tệp src/test/java/example/validation/BookingControllerTest.java:

~~~java
package example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryTypeMismatchIsBindingError() throws Exception {
        mvc.perform(get("/api/bookings/estimate")
                        .param("seats", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"));
    }

    @Test
    void wrongJsonFieldTypeIsBodyParseError() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"EVENT-10\",\"seats\":\"many\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_PARSE_ERROR"));
    }

    @Test
    void invalidDtoConstraintsAreValidationError() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"\",\"seats\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fieldErrors").isArray());
    }

    @Test
    void directParameterConstraintUsesMethodValidation()
            throws Exception {
        mvc.perform(get("/api/bookings/guarded-estimate")
                        .param("seats", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION_ERROR"));
    }

    @Test
    void soldOutEventIsBusinessConflict() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"sold-out\",\"seats\":2}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("BOOKING_CONFLICT"));
    }

    @Test
    void validRequestIsCreated() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"eventId\":\"EVENT-10\",\"seats\":2}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.bookingId")
                        .value("BKG-DEMO-001"))
                .andExpect(jsonPath("$.seats").value(2));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

MockMvc thực thi request trong Spring MVC test context, không cần mở HTTP socket. Từng test kiểm tra code cụ thể, chứ không chỉ kiểm tra tất cả đều 400. Nếu ứng dụng có Spring Security, cần cấu hình test user và policy; 401/403 do Filter không chứng minh validation mapping hỏng.

Một số dự án tùy chỉnh Jackson ProblemDetail serialization sẽ cần cập nhật JSONPath theo API contract thực. Với Boot 3.5 thông thường, extension property code được serialize vào problem response.

## 13. Thử nhanh bằng curl

Sau khi chạy ứng dụng bằng ./mvnw spring-boot:run, nếu cổng mặc định là 8080:

~~~bash
# Conversion: query không chuyển thành int.
curl -i "http://localhost:8080/api/bookings/estimate?seats=abc"

# JSON decode: seats là chuỗi không thể chuyển thành Integer.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"EVENT-10","seats":"many"}'

# Bean Validation: seats có kiểu hợp lệ nhưng giá trị nhỏ hơn 1.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"EVENT-10","seats":0}'

# Business: event hết chỗ.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"sold-out","seats":2}'

# Thành công.
curl -i -X POST http://localhost:8080/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"eventId":"EVENT-10","seats":2}'
~~~

Status tương ứng: 400, 400, 400, 409 và 201. Đây là dự kiến theo code; không phải stdout cố định của mọi Spring Boot version. Log, headers và thứ tự JSON fields thay đổi theo runtime.

## 14. Validation ở service và nguy cơ phân loại sai

Spring có thể thực thi method validation ở service khi áp dụng @Validated và cơ chế tương ứng:

~~~java
@Service
@Validated
public class PaymentService {

    public void transfer(@NotNull TransferCommand command) {
        // Giữ invariant của phương thức khi service được gọi.
    }
}
~~~

Đây là đoạn minh họa, cần TransferCommand và imports. @NotNull trên reference không tự cascade nested fields nếu không có @Valid.

**Lỗi method constraint trong service không luôn là input error của HTTP client.** Một scheduled job hoặc class nội bộ có thể gọi service sai contract. Spring có thể phát ConstraintViolationException hoặc MethodValidationException tùy configuration, và không tự buộc exception đó phải map thành HTTP 400.

Không catch mọi ConstraintViolationException ở tầng global rồi mặc định trả 400. Hãy xác định ai vi phạm contract, lớp phát sinh và liệu client có thể sửa được hay không.

Điều tương tự áp dụng cho lỗi @NotNull trên return value hoặc service trả null trái kỳ vọng: thường là lỗi server, không phải lỗi query parameter của client.

## 15. Trạng thái nghiệp vụ, transaction và race condition

Bean Validation thường không cần truy cập external state. Business checks như "còn 2 ghế không?" phải xét dữ liệu tại thời điểm thực thi và có thể cần transaction.

Ví dụ:

~~~text
Request A kiểm tra còn 1 ghế
Request B kiểm tra còn 1 ghế
Request A đặt 1 ghế
Request B đặt 1 ghế
~~~

Nếu không có locking hoặc transactional invariant, cả hai cùng có thể thấy còn một ghế rồi oversell. Việc gắn một custom @AvailableSeats constraint trên DTO không tự giải quyết cuộc đua.

Các cách xử lý phù hợp tùy domain:

- Optimistic locking với version và retry policy rõ.
- Pessimistic locking khi cần.
- Atomic update kiểm tra số lượng.
- Unique index để bảo vệ uniqueness.
- Idempotency key để tránh nhân đôi thao tác khi client retry.
- Tách conflict dự kiến khỏi hạ tầng DB bất ngờ.

Sau khi transaction phát hiện conflict, service có thể chuyển thành exception domain rõ ràng; tầng web map theo API contract. Không cần để controller biết SQL constraint name, deadlock code hoặc database vendor.

## 16. Đối chiếu với Spring WebFlux

WebFlux có cùng ba lớp khái niệm nhưng dùng reactive pipeline và exception types khác:

| Vấn đề | Spring MVC | Spring WebFlux |
|---|---|---|
| Query/path conversion | MethodArgumentTypeMismatchException hoặc lỗi conversion tương ứng | ServerWebInputException / input resolution error |
| JSON không decode được | HttpMessageNotReadableException | ServerWebInputException / decoding error |
| @Valid object trong @RequestBody | MethodArgumentNotValidException | WebExchangeBindException |
| Direct method constraint | HandlerMethodValidationException | HandlerMethodValidationException |
| Domain rule | Exception domain, xử lý qua advice | Exception domain trong Mono/Flux, xử lý qua advice/handler |
| Error pipeline | HandlerExceptionResolver / ResponseEntityExceptionHandler | Reactive exception handling / WebExceptionHandler |

Đây là các đường đi **thường gặp**, không phải bảo đảm mọi method signature hoặc phiên bản đều phát cùng một exception class.

Ví dụ reactive signature:

~~~java
@PostMapping("/bookings")
public Mono<BookingResponse> create(
        @Valid @RequestBody Mono<CreateBookingRequest> body) {
    return body.flatMap(reactiveService::create);
}
~~~

Đây chỉ là minh họa; reactiveService.create cần trả Mono<BookingResponse>. Không dùng nguyên BookingService đồng bộ phía MVC rồi gọi nó "reactive". Trong WebFlux, object validation của request body có thể phát WebExchangeBindException; khi dùng direct method constraints còn có HandlerMethodValidationException.

Không import HttpMessageNotReadableException của Servlet MVC như giải pháp tổng quát cho WebFlux. Nếu exception phát trong Mono/Flux, việc xử lý cần giữ error signal trong reactive chain. Đừng dùng block() trên event-loop để bắt exception theo kiểu imperative.

Khi custom constraint hoặc business rule gọi JDBC blocking, việc đó có thể chặn event-loop; dùng reactive I/O hoặc cô lập blocking work phù hợp và đặt timeout.

## 17. I18n, bảo mật và thông điệp lỗi

Spring có MessageSource và MessageCodesResolver để tạo các mã như NotBlank.createBookingRequest.eventId, Min.createBookingRequest.seats hoặc typeMismatch.searchForm.minSeats. Tên object chính xác phụ thuộc DTO và cách binding.

Ví dụ messages_vi.properties:

~~~properties
NotBlank.createBookingRequest.eventId=Mã sự kiện không được để trống
Min.createBookingRequest.seats=Số ghế phải từ 1 trở lên
typeMismatch.searchForm.minSeats=Số ghế tối thiểu phải là số nguyên
~~~

Đây là ví dụ resource bundle. Hãy kiểm tra getCodes() thực tế trước khi cố định key, vì object name có thể khác theo configuration.

Một error response tốt có status, code ổn định, field, thông báo thân thiện và correlation ID phù hợp. Không đưa raw rejectedValue, password, token, stacktrace, SQL syntax hay exception cause thô ra client.

Cũng không nên chốt logic client dựa trên chuỗi tiếng Anh "must not be blank". Localized text có thể đổi; client nên dựa vào code và field list.

## 18. Retry policy theo loại lỗi

- **400 binding:** thường phải sửa kiểu, format, query hoặc JSON; retry y hệt không giúp ích.
- **400 validation:** sửa field vi phạm constraint; UI có thể hiển thị lỗi cạnh trường tương ứng.
- **409 business:** refresh trạng thái, chọn resource khác hoặc đợi state thay đổi; retry tự động có thể vẫn conflict.
- **422 semantic:** theo contract, client cần đổi nội dung/quy trình chứ không chỉ lặp request.
- **500/503:** có thể do server, chỉ retry khi method/idempotency policy cho phép và có backoff.

Một HTTP 409 do resource state xung đột khác hoàn toàn với HTTP 400 do seats không phải số. Việc phân loại đúng cải thiện UX và giảm retry vô ích.

## 19. Checklist QA trước khi đưa API vào production

1. Có test cho query/path type mismatch.
2. Có test cho JSON malformed hoặc field không deserialize được.
3. Có test cho missing required parameter và missing request body.
4. Có test cho @NotBlank, @NotNull, @Min và nested @Valid nếu dùng.
5. Có test cho direct method constraint và exception mapping tương ứng.
6. Nếu dùng BindingResult, kiểm tra vị trí ngay sau argument và FieldError.isBindingFailure().
7. Có test cho domain conflict và success response.
8. Có test cho database uniqueness/concurrency nếu đó là invariant thật.
9. Error response có code ổn định, không lộ rejectedValue/stacktrace.
10. Không catch-all 400 cho mọi exception.
11. Nếu API hỗ trợ WebFlux, test WebExchangeBindException và reactive exception pipeline.
12. Có document 400/409/422, retry và idempotency contract rõ ràng.

## 20. Tài liệu chính thức

- [Spring MVC 6.2 – Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring WebFlux 6.2 – Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 – Data Binding, Type Conversion and Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring Framework – FieldError Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring MVC 6.2 – Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring WebFlux 6.2 – Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Boot 3.5 – Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)

**Kết luận:** Binding giải quyết việc chuyển đầu vào HTTP thành kiểu Java. Bean Validation kiểm tra constraints trên đối tượng và method. Lỗi nghiệp vụ phản ánh trạng thái và chính sách domain. Hãy phân loại theo nguyên nhân, không chỉ nhìn HTTP status hay tên exception; tách domain rules khỏi DTO validation, giữ mã lỗi ổn định và kiểm thử exception-to-response mapping.