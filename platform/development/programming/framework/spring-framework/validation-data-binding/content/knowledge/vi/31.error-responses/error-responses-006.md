# Phân biệt lỗi đầu vào của client với lỗi giá trị trả về của server trong Spring Validation

## 1. Tại sao phải phân biệt rõ hai loại lỗi?

Validation trong ứng dụng Spring có thể kiểm tra **dữ liệu đi vào** handler/service hoặc kiểm tra **giá trị mà chính server tạo ra**. Cả hai đều có thể biểu hiện dưới dạng "vi phạm constraint", nhưng trách nhiệm và cách phản hồi HTTP rất khác nhau.

Ví dụ một API cung cấp số trang:

~~~http
GET /api/contracts/page?size=0
~~~

Nếu controller yêu cầu `size >= 1`, client đã gửi giá trị trái hợp đồng đầu vào. Với Spring MVC built-in method validation, trường hợp này thông thường dẫn tới **HTTP 400 Bad Request**.

Ngược lại, giả sử client gửi request hợp lệ:

~~~http
GET /api/contracts/report
~~~

Controller cam kết trả chuỗi không rỗng (ví dụ đặt `@NotBlank` trên **return value**), nhưng implementation lại trả `""`. **Client không thể sửa lỗi của giá trị server sinh ra**. Với Spring MVC method validation từ Spring Framework 6.1+, lỗi return value có thể tạo **`HandlerMethodValidationException` với HTTP 500 Internal Server Error**.

**Quy tắc nền tảng:**

- **Input violation**: client đã gửi tham số/đối tượng không đạt hợp đồng → mã **4xx phù hợp**; với lỗi validation thông dụng, thường **400**.
- **Return-value violation**: server không đáp ứng ràng buộc của chính đầu ra → **lỗi server, thường 500**, không đổ thành 400 hay 422.
- **Lỗi ứng dụng/phụ thuộc khác**: có thể là 404, 409, 401, 403, 503 hoặc 500 theo nguyên nhân, **không phải cứ có validation là 400**.

Bài này tập trung vào **Spring Framework validation + phản hồi lỗi**, gồm Java Bean Validation, `@Valid`, các constraint method-level, `MethodArgumentNotValidException`, `HandlerMethodValidationException`, cách giữ đúng status khi xử lý ngoại lệ và kiểm thử thực tế bằng MockMvc.

## 2. Vòng đời request: lỗi ở đâu thì trách nhiệm ở đó

~~~text
Client
  |
  | HTTP request / query / path / header / JSON / form
  v
Spring MVC argument resolution
  ├─ Đọc body, parse JSON, chuyển kiểu, data binding
  |     └─ Lỗi input/parse       -> thông thường 400
  |
  ├─ Kiểm tra input arguments
  |     ├─ @Valid DTO           -> MethodArgumentNotValidException (400)
  |     └─ @Min/@NotBlank trên
  |        method parameter     -> HandlerMethodValidationException (400)
  |
  v
Controller -> Service -> Repository/remote systems
  |                |
  |                ├─ Resource không tồn tại -> thường 404
  |                ├─ State conflict          -> thường 409
  |                └─ Server/dependency error -> 5xx phù hợp
  v
Handler method trả kết quả
  |
  ├─ Kiểm tra return-value constraint
  |     └─ Trả giá trị sai hợp đồng
  |        -> HandlerMethodValidationException (500)
  |
  v
HttpMessageConverter ghi response HTTP
  |
  └─ Lỗi serialize/ghi output    -> thường 5xx
~~~

Điểm khác biệt không nằm ở tên constraint: **`@NotBlank` có thể dùng cho input hoặc return value**. Quyết định 400/500 phụ thuộc **giai đoạn và đối tượng được kiểm tra**, không phải chỉ dựa vào tên `NotBlank` hoặc `ConstraintViolationException`.

Cần phân biệt rõ **validation** với các loại lỗi khác:

- `size=abc` không parse được thành `int` → lỗi **type conversion**, trước lúc `@Min` xét giá trị.
- JSON sai cú pháp → `HttpMessageNotReadableException` (thường 400), trước Bean Validation.
- `size=0` parse được thành `int`, nhưng vi phạm `@Min(1)` → **validation input**.
- Handler trả chuỗi `""` dù method có `@NotBlank` → **validation return value**.
- Handler trả object hợp lệ nhưng Jackson không serialize được → **response writing/serialization error**, không phải lỗi @NotNull của client.
- Service phát hiện business conflict (ví dụ username đã tồn tại) → có thể là 409, bất kể DTO đã thỏa @Valid.

## 3. Spring MVC có hai cơ chế validation quan trọng

### 3.1. Individual argument validation với `@Valid`

Khi một tham số là command object của `@ModelAttribute`, `@RequestBody` hoặc `@RequestPart` và được gắn `@Valid`/`@Validated`, Spring có thể kiểm tra đối tượng đó sau khi bind/deserialize:

~~~java
@PostMapping("/users")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateUserRequest body) {

    // Khi DTO không đạt constraint, thường chưa chạy vào đây.
    return ResponseEntity.ok().build();
}
~~~

Đoạn trên là **snippet** với DTO và imports giả định; chương trình đầy đủ ở phần 8.

Nếu DTO có `@NotBlank String username`, client gửi `{"username":""}` và không có `BindingResult` liền kề, với **individual argument validation**, Spring MVC thường ném:

~~~text
org.springframework.web.bind.MethodArgumentNotValidException
HTTP 400 Bad Request
~~~

Exception chứa `BindingResult` của **một đối tượng**. Lấy `getFieldErrors()`, `getGlobalErrors()` để xây response lỗi phù hợp. Không trực tiếp serialize `BindingResult` vì có thể mang `rejectedValue`, thông tin nội bộ hoặc dữ liệu nhạy cảm.

**`@Valid` tự nó không phải constraint**. Nó báo rằng cần kiểm tra các constraint lồng trong object. Nó **không tự khiến method validation áp dụng** nếu không có constraint trực tiếp trên method parameters/return value hoặc điều kiện khác đòi hỏi method validation.

### 3.2. Method validation với constraint trực tiếp trên tham số

Từ **Spring Framework 6.1**, Spring MVC có hỗ trợ **built-in method validation** cho handler có constraint trực tiếp trên method parameters hoặc return value:

~~~java
@GetMapping("/page")
public String page(@RequestParam("size") @Min(1) int size) {
    return "SIZE:" + size;
}
~~~

`@Min(1)` là constraint được đặt trực tiếp trên **parameter `size`**. Nếu client gửi `size=0`, method validation thất bại và thường ném:

~~~text
org.springframework.web.method.annotation.HandlerMethodValidationException
isForReturnValue() == false
getStatusCode() == 400 BAD_REQUEST
~~~

`HandlerMethodValidationException` chứa kết quả theo **các method parameters**, không phải chỉ một DTO như `MethodArgumentNotValidException`. Nếu method có cả `@Min` trên parameter và `@Valid` trên DTO khác, method validation có thể **bao phủ cả validation lồng nhau**, thay cho individual argument validation.

**Quan trọng với `@Validated` cấp class:** Khi controller có `@Validated` trên class, method validation có thể được thực hiện qua Spring AOP proxy thay vì cơ chế MVC built-in. Spring khuyến nghị **bỏ class-level `@Validated`** nếu muốn sử dụng built-in controller method validation từ 6.1. Kiểu exception và cách xử lý có thể khác với AOP, vì thế hãy kiểm thử cấu hình thực tế.

### 3.3. Method validation với constraint trên return value

Ví dụ:

~~~java
@GetMapping("/report")
@NotBlank
public String report() {
    return ""; // Server tạo ra một giá trị trái với hợp đồng.
}
~~~

Annotation `@NotBlank` ở đây được đặt **trên method**, nên áp dụng cho **giá trị trả về**. Khi handler đã chạy và trả `""`, Spring MVC built-in method validation nhận thấy return value không đạt constraint, thường ném:

~~~text
org.springframework.web.method.annotation.HandlerMethodValidationException
isForReturnValue() == true
getStatusCode() == 500 INTERNAL_SERVER_ERROR
~~~

Theo Javadoc chính thức của `HandlerMethodValidationException` (Spring Framework 6.1+): **status 400 dành cho input validation errors, status 500 dành cho validation errors trên return value**.

Lỗi return value là **server contract failure**: code, dữ liệu DB, mapping DTO hoặc logic nghiệp vụ trên server cần được kiểm tra. **Không nên yêu cầu client "sửa request"** khi request không vi phạm input contract.

### 3.4. Bảng so sánh ba trường hợp dễ nhầm

| Handler | Dữ liệu sai | Loại lỗi tiêu biểu | HTTP |
| --- | --- | --- | --- |
| `save(@Valid @RequestBody UserDto dto)` | DTO vi phạm `@NotBlank` | `MethodArgumentNotValidException` (nếu individual validation) | 400 |
| `page(@RequestParam @Min(1) int size)` | Query `size=0` | `HandlerMethodValidationException`, `isForReturnValue()=false` | 400 |
| `@NotBlank String report()` | Server trả `""` | `HandlerMethodValidationException`, `isForReturnValue()=true` | 500 |
| `save(@Valid @RequestBody UserDto dto, BindingResult result)` | DTO vi phạm Bean Validation | Lỗi được controller xử lý qua `result` nếu không có lỗi khác đòi hỏi exception | Tự chọn, thường 400 |
| `save(@NotNull @Valid @RequestBody UserDto dto)` | Constraint trực tiếp `@NotNull` cùng `@Valid` | Method validation có thể áp dụng, thay vì individual validation | Thường 400 nếu lỗi input |

Bảng giả định Spring MVC 6.1+ **không có class-level `@Validated` AOP can thiệp**, có Bean Validation provider và không có custom exception handler cố ý thay đổi status.

## 4. Vì sao kiểm tra return value không phải lỗi client?

Giả sử API nhận mã sản phẩm hợp lệ, service lấy dữ liệu rồi trả response:

~~~java
public record ProductResponse(
        @NotBlank String sku,
        @NotNull BigDecimal price) {
}
~~~

Bản thân record khai báo constraints cho dữ liệu đầu ra. Có nhiều nguồn có thể khiến response vi phạm:

- Repository trả object thiếu `sku` do dữ liệu tồn kho bị hỏng.
- Mapper ghi nhầm `sku=""` hoặc `price=null`.
- Service áp dụng nhầm business rule.
- Dữ liệu downstream có schema không đúng kỳ vọng.
- Một logic refactor bỏ sót trường cần xuất.

**Client không chịu trách nhiệm làm cho mapper của server hoạt động đúng**. Vì thế:

1. Trả 400 sẽ **phân loại sai lỗi** và khiến client cố sửa input vô ích.
2. Trả thông tin validator chi tiết có thể **lộ cấu trúc response, giá trị DB hoặc nội bộ server**.
3. Monitoring có thể thống kê sai nếu lẫn server bug vào nhóm 4xx.
4. Khách hàng có thể tưởng request bị từ chối trước khi server làm gì, trong khi validation return value có thể xảy ra **sau khi service đã thực hiện side effect**.

**Phân biệt annotation với việc kích hoạt validation:** chỉ viết `@NotBlank`/`@NotNull` bên trong `ProductResponse` không chứng minh mọi endpoint trả record ấy đều tự động validate output. Muốn đảm bảo một đường đi thực sự kiểm tra return value, phải cấu hình/đặt constraint kích hoạt **executable return-value validation** (hoặc gọi validator minh bạch) và có test. `@Valid` đơn lẻ trên một method không phải một constraint, nên không nên tự suy rằng mọi output luôn được method validator kiểm tra.

### Chuẩn hóa cách phản hồi

Với lỗi return value, có thể trả một envelope chung:

~~~json
{
  "code": "SERVER_CONTRACT_VIOLATION",
  "message": "Không thể hoàn tất yêu cầu."
}
~~~

HTTP status: **500**. Không đưa ra danh sách "field `sku` có rejected value `null`" cho client nếu chúng là chi tiết nội bộ. Log/tracing nội bộ nên lưu **mã lỗi, route template, request ID và trạng thái**, không log dữ liệu cá nhân hoặc token để "debug nhanh".

Với lỗi input:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Tham số yêu cầu không hợp lệ."
}
~~~

HTTP status: **400**. Trong ứng dụng form/REST có thể bổ sung danh sách public fields được whitelist, nhưng không trả raw `rejectedValue`. Hai schema có thể nhất quán về hình dạng, song **status và code phải bảo toàn ý nghĩa**.

## 5. Đọc đúng `HandlerMethodValidationException`

`HandlerMethodValidationException` thuộc package:

~~~java
org.springframework.web.method.annotation
        .HandlerMethodValidationException
~~~

Đường dẫn trên được xuống dòng để trình bày; **khi import vào file Java, phải viết thành một dòng**:

~~~java
import org.springframework.web.method.annotation.HandlerMethodValidationException;
~~~

Các phương thức hữu ích trong Spring Framework 6.2:

| API | Dùng để làm gì? |
| --- | --- |
| `isForReturnValue()` | `true` nếu lỗi khi validate return value; `false` nếu lỗi method arguments. |
| `getStatusCode()` | Trả `HttpStatusCode`: **400** với input; **500** với return value. |
| `getParameterValidationResults()` | Các `ParameterValidationResult`, nhóm lỗi theo method parameters. |
| `getCrossParameterValidationResults()` | Các lỗi cross-parameter trong method-level validation. |
| `getAllValidationResults()` hoặc `getAllErrors()` | Tổng hợp validation results/errors theo version API. |
| `getMethod()` | Method được validate — hữu ích cho internal diagnostics. |
| `visitResults(visitor)` | Xử lý errors theo loại annotation của parameter như `@RequestParam`, `@RequestHeader`, `@ModelAttribute`. |
| `getBody()` | `ProblemDetail` trong cơ chế `ErrorResponse`. |

**Không cần xem `getParameterValidationResults()` để quyết định 400 hay 500**. Phương thức đúng cho phân biệt này là `isForReturnValue()`, đồng thời có thể dùng `getStatusCode()` mà Spring đã chọn. Return-value violations có thể được biểu diễn bằng nhóm kết quả nội bộ; không nên suy luận rằng “parameter index = -1” là một public API contract.

Ví dụ handler:

~~~java
@ExceptionHandler(HandlerMethodValidationException.class)
ResponseEntity<?> handle(HandlerMethodValidationException ex) {
    if (ex.isForReturnValue()) {
        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of(
                        "code", "SERVER_CONTRACT_VIOLATION"));
    }

    return ResponseEntity.badRequest()
            .body(Map.of("code", "INVALID_INPUT"));
}
~~~

Đây là **snippet** trong `@RestControllerAdvice`, cần imports tương ứng. Nó không trả raw exception messages hoặc parameter values. Trong code hoàn chỉnh ở phần 8, handler dùng `ex.getStatusCode()` để **giữ nguyên phân loại 400/500 của framework**.

### `ResponseEntityExceptionHandler` cũng có extension point phù hợp

Nếu ứng dụng kế thừa `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`, Spring 6.1+ có protected hook:

~~~java
@Override
protected ResponseEntity<Object>
handleHandlerMethodValidationException(
        HandlerMethodValidationException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // Phải giữ sự phân biệt lỗi input/return value.
    return handleExceptionInternal(
            ex, sanitizedBody(ex), headers, status, request);
}
~~~

Đây là **snippet minh họa signature**, giả định class kế thừa và hàm `sanitizedBody(ex)` được tự triển khai; không phải một class chạy độc lập. Với override, dùng `status` do Spring truyền xuống (400/500), hoặc kiểm tra `ex.isForReturnValue()` nếu phải tùy biến body. **Không cứng hóa 400** cho mọi `HandlerMethodValidationException`.

Khi kế thừa `ResponseEntityExceptionHandler`, không tự khai báo thêm `@ExceptionHandler(HandlerMethodValidationException.class)` trong cùng class nếu parent đã định tuyến exception đó; điều này có thể gây handler mapping ambiguity. Chọn **một cơ chế** phù hợp cho mỗi ứng dụng.

## 6. Phân loại lỗi chính xác hơn một nhãn “validation failed”

| Tình huống | Vị trí/nguồn | Exception hoặc cơ chế thường gặp | HTTP gợi ý |
| --- | --- | --- | --- |
| Thiếu query parameter bắt buộc | Client input | `MissingServletRequestParameterException` | 400 |
| Query `count=abc`, cần `int` | Argument conversion | `MethodArgumentTypeMismatchException` | 400 |
| JSON sai cú pháp | `HttpMessageConverter` đọc body | `HttpMessageNotReadableException` | 400 |
| `@Valid @RequestBody` DTO sai | Individual Bean Validation | `MethodArgumentNotValidException` | 400 |
| `@RequestParam @Min(1)`, client gửi 0 | MVC built-in method validation trên **input** | `HandlerMethodValidationException`, return flag false | 400 |
| `@NotBlank` trên return method, server trả rỗng | MVC built-in method validation trên **output** | `HandlerMethodValidationException`, return flag true | 500 |
| Method service với `@Validated` AOP trả sai constraint | Method validation ngoài MVC | Có thể là `ConstraintViolationException` hoặc `MethodValidationException` tùy cấu hình | Server lỗi 5xx; không tự coi là 400 |
| `@ResponseBody` không serialize được | Serialization/response write | `HttpMessageNotWritableException` hoặc lỗi khác | Thường 500 |
| Không tìm thấy resource hợp lệ | Business/resource lookup | Domain exception hoặc `ResponseStatusException` được mapping | Thường 404 |
| Trùng resource/đụng trạng thái | Business conflict | Domain exception, duplicate-key mapping | Thường 409 |
| Upstream/downstream đang không sẵn sàng | Server dependency failure | Timeout/connection exception | 5xx, có thể 503 theo policy |
| Client gửi đúng định dạng nhưng vi phạm rule nghiệp vụ | Domain/application policy | Error code riêng | 400, 409 hoặc 422 tùy hợp đồng API |

**Cảnh báo quan trọng:** Không có quy tắc “cứ gặp `ConstraintViolationException` là trả HTTP 400”. Nó có thể xuất hiện ở **service-layer validation**, và bản thân nó không cho biết chắc lỗi là do client hay do server. Phải biết **đường thực thi nào được validate** và **giá trị nào vi phạm**.

### Vì sao `422` không thay thế `500` cho response contract?

HTTP 422 Unprocessable Content là lựa chọn mà một số API dùng cho input hợp cú pháp nhưng không thể xử lý theo business rules. Nó là **một loại 4xx** và vẫn diễn đạt lỗi phía request/client. Nó không phù hợp để giấu một return-value constraint failure: server vừa tạo ra kết quả trái hợp đồng thì **500** mới phản ánh đúng trách nhiệm.

### Lỗi authentication, authorization và resource

Một request có thể thất bại vì token không hợp lệ (401), thiếu quyền (403), resource không tồn tại (404) hoặc conflict (409) dù mọi Bean Validation constraint đều đạt. **Validation input là một tầng, HTTP error semantics là tầng rộng hơn**. Đừng lạm dụng `@Valid` để quyết định phân quyền hoặc existence checks.

## 7. Thời điểm validate và tác động tới side effects

### 7.1. Input validation sớm

Thông thường `@Valid`/method parameter constraints được kiểm tra trước khi controller body chạy. Với request không hợp lệ, bạn có thể từ chối trước khi gọi database hay thực hiện hành động tốn kém.

Tuy nhiên, vẫn cần guard ở service/domain boundary nếu có nhiều caller ngoài HTTP (message queue, scheduled tasks, internal services) hoặc cần kiểm tra quyền và consistency. DTO có `@Valid` không đảm bảo tài nguyên được phép cập nhật.

### 7.2. Return validation sau khi xử lý

Return-value validation chạy **sau khi controller đã trả một giá trị** (và trong đường đi built-in MVC, trước khi kết quả được xử lý thành HTTP response hoàn chỉnh). Service có thể đã thực hiện ghi DB, gửi event hoặc gọi API ngoài **trước khi exception 500 được tạo**.

Ví dụ kịch bản:

~~~text
Client POST hợp lệ
   -> MVC kiểm tra input thành công
   -> Service tạo giao dịch, ghi bản ghi thành công
   -> Controller map sai DTO, trả return value vi phạm constraint
   -> MVC phát hiện lỗi -> HTTP 500
~~~

Không nên tự kết luận giao dịch DB đã rollback chỉ vì client nhận 500. Nếu transaction đã commit trước khi return validation, hệ thống có thể cần idempotency key, transaction boundary thích hợp hoặc quy trình bù/đối soát. Đừng khuyến khích client tự retry POST không có idempotency policy: có nguy cơ tạo dữ liệu trùng.

**Kiểm tra đầu ra càng gần nơi tạo ra nó càng tốt**, nhưng đừng xem return-value annotation là phương án duy nhất bảo vệ consistency. Với service nghiệp vụ quan trọng, nên có invariant, tests và transaction boundaries rõ ràng trước khi side effect được commit.

### 7.3. Bất đồng bộ/streaming

Nếu handler trả `CompletableFuture`, `Mono`, `Flux`, stream hoặc `ResponseBodyEmitter`, thời điểm tạo và validate từng giá trị có thể khác so với handler trả một `String` đồng bộ. Khi HTTP response **đã commit headers hoặc đã gửi một phần body**, không thể tùy ý thay status thành 500 bằng exception handler. Phải thiết kế kiểm tra trong reactive pipeline, cơ chế cancel/fallback và observability phù hợp.

Vì vậy code đầy đủ phía dưới chọn controller **đồng bộ và kiểu trả về `String`** để chứng minh rõ built-in MVC method validation 400/500, không suy rộng sang mọi mô hình streaming.

## 8. Ví dụ chạy được: Spring Boot 3.2+, Java 17+, Spring MVC

Dự án mẫu nhằm kiểm chứng các tình huống khác nhau:

1. Lỗi `@Min` trên method input parameter → **400**.
2. Lỗi `@NotBlank` trên **return value** của controller → **500**.
3. `@Valid @RequestBody` DTO sai → **400** qua `MethodArgumentNotValidException`.
4. JSON body không đọc được → **400** qua `HttpMessageNotReadableException`.
5. Trường hợp input/output hợp lệ → request được xử lý bình thường.

Dùng **Spring Boot 3.2+** (Spring Framework **6.1+**), **Java 17+**, Maven. Với Spring Boot 3.x, các package validation là `jakarta.validation.*`, không phải `javax.validation.*`.

### 8.1. Maven dependencies

Trong `pom.xml` do Spring Boot parent hoặc BOM quản lý, thêm các dependency:

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

Cần đúng ba starter; chưa thêm Spring Security để tập trung vào validation pipeline. Nếu có custom `@ControllerAdvice` hoặc AOP validator của dự án thật, tests có thể cần điều chỉnh.

Tạo Java files trong package `com.example.contractvalidation`. Ở bản demo **không đặt `@Validated` trên class controller**, để Spring MVC built-in method validation được sử dụng như tài liệu Spring 6.1+ mô tả.

### 8.2. `ContractValidationApplication.java`

Đường dẫn: `src/main/java/com/example/contractvalidation/ContractValidationApplication.java`

~~~java
package com.example.contractvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ContractValidationApplication.class, args);
    }
}
~~~

### 8.3. `CreateUserRequest.java`

Đường dẫn: `src/main/java/com/example/contractvalidation/CreateUserRequest.java`

~~~java
package com.example.contractvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateUserRequest(
        @NotBlank String username,
        @NotNull @Min(18) Integer age) {
}
~~~

Record này chứa những constraint **trên dữ liệu input**. Với `username=""` hoặc `age=16`, `@Valid` trên controller argument sẽ kiểm tra và báo lỗi. Khi JSON body sai cú pháp, Jackson chưa tạo được record nên đó là lỗi **deserialize**, không phải lỗi `@Min`.

### 8.4. `ContractController.java`

Đường dẫn: `src/main/java/com/example/contractvalidation/ContractController.java`

~~~java
package com.example.contractvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/contracts")
public class ContractController {

    // Input constraint trực tiếp trên method parameter.
    @GetMapping("/page")
    public String page(
            @RequestParam("size") @Min(1) int size) {
        return "SIZE:" + size;
    }

    // Return-value constraint, kiểm tra sau khi handler chạy.
    @NotBlank
    @GetMapping("/healthy-report")
    public String healthyReport() {
        return "READY";
    }

    // Cố tình vi phạm return-value constraint để test HTTP 500.
    @NotBlank
    @GetMapping("/broken-report")
    public String brokenReport() {
        return "";
    }

    // Chỉ có @Valid trên command object -> individual argument
    // validation (không có constraint trực tiếp trên method).
    @PostMapping(path = "/users",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createUser(
            @Valid @RequestBody CreateUserRequest input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "accepted"));
    }
}
~~~

**Điểm cần quan sát:**

- `/page` có `@Min(1)` **trên method parameter**; `size=0` gây input method validation error. `size=abc` thất bại ở **type conversion** trước `@Min`.
- `/healthy-report` và `/broken-report` đặt `@NotBlank` **trực tiếp trên method**, nghĩa là constraint cho **return value `String`**.
- `/broken-report` cố tình trả chuỗi rỗng, để có regression test cho **500**; không dùng endpoint này trong ứng dụng thật.
- `/users` chỉ gắn `@Valid` cho DTO, nên với chữ ký này Spring có thể dùng individual argument validation và `MethodArgumentNotValidException`.
- Không có `@Validated` cấp class. Nếu thêm annotation đó, việc validation có thể chuyển sang AOP proxy và test về exception cụ thể cần được xem lại.

### 8.5. `ContractErrorAdvice.java`: giữ 400 và 500 chính xác

Đường dẫn: `src/main/java/com/example/contractvalidation/ContractErrorAdvice.java`

~~~java
package com.example.contractvalidation;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ContractErrorAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<PublicError> onMethodValidation(
            HandlerMethodValidationException ex) {

        boolean returnValueFailed = ex.isForReturnValue();
        String code = returnValueFailed
                ? "SERVER_CONTRACT_VIOLATION"
                : "INVALID_INPUT";
        String message = returnValueFailed
                ? "Không thể hoàn tất yêu cầu."
                : "Tham số yêu cầu không hợp lệ.";

        // Spring đã chọn 400 cho input, 500 cho return value.
        // Tuyệt đối không ép tất cả về badRequest().
        return ResponseEntity.status(ex.getStatusCode())
                .body(new PublicError(code, message));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<PublicError> onInvalidDto(
            MethodArgumentNotValidException ex) {

        // Không trả rejectedValue, BindingResult hay exception body.
        return ResponseEntity.badRequest().body(
                new PublicError(
                        "INVALID_BODY",
                        "Dữ liệu đầu vào không hợp lệ."));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<PublicError> onUnreadableBody(
            HttpMessageNotReadableException ex) {

        // JSON hỏng/thiếu body: không echo parser exception.
        return ResponseEntity.badRequest().body(
                new PublicError(
                        "MALFORMED_BODY",
                        "Không đọc được nội dung yêu cầu."));
    }

    public record PublicError(String code, String message) {
    }
}
~~~

Vì sao handler này an toàn hơn `@ExceptionHandler(Exception.class)` trả 400?

1. Nhận **đúng exception** và phân biệt bằng `isForReturnValue()`.
2. Dùng **`ex.getStatusCode()` của Spring** thay vì tự biến mọi lỗi thành 400.
3. Return-value error chỉ trả **mã chung**. Không lộ giá trị server đã tạo, internal method names, constraints hoặc entity data.
4. `MethodArgumentNotValidException` dành cho một DTO không đạt validation, khác method validation của `@Min` trên parameter.
5. `HttpMessageNotReadableException` do converter/Jackson đọc body gặp lỗi, không phải một `ConstraintViolation` của field đã deserialize.
6. Response schema là **thiết kế của ví dụ**, không phải JSON mặc định của Spring Boot.
7. Advice này **không kế thừa `ResponseEntityExceptionHandler`**, nên không đồng thời đăng ký hai handler trùng nhau trong cùng class.

Nếu có các yêu cầu quản lý lỗi phức tạp hơn, có thể chuyển sang `ProblemDetail`/RFC 9457, nhưng vẫn phải giữ đúng **status và category**. Không cần đưa danh sách mọi return-value constraint violation vào public problem detail.

## 9. Kiểm thử MockMvc: 400 cho input, 500 cho output

Tạo file `src/test/java/com/example/contractvalidation/ContractValidationApplicationTest.java`:

~~~java
package com.example.contractvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ContractValidationApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validMethodParameterIsAccepted() throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(content().string("SIZE:2"));
    }

    @Test
    void methodInputConstraintFailureIs400()
            throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_INPUT"));
    }

    @Test
    void negativeInputAlsoViolatesMinConstraint()
            throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "-5"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_INPUT"));
    }

    @Test
    void missingRequiredParameterIs400()
            throws Exception {
        mvc.perform(get("/api/contracts/page"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongParameterTypeIs400BeforeMinValidation()
            throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validReturnValueIsAccepted() throws Exception {
        mvc.perform(get("/api/contracts/healthy-report"))
                .andExpect(status().isOk())
                .andExpect(content().string("READY"));
    }

    @Test
    void invalidReturnValueIs500Not400()
            throws Exception {
        mvc.perform(get("/api/contracts/broken-report"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("SERVER_CONTRACT_VIOLATION"))
                .andExpect(jsonPath("$.message")
                        .value("Không thể hoàn tất yêu cầu."));
    }

    @Test
    void validJsonDtoCreatesResponse() throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"Lan","age":26}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }

    @Test
    void invalidJsonDtoIs400ButNotMethodReturnError()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"","age":16}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_BODY"));
    }

    @Test
    void jsonMissingAgeIsDtoValidationError()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"Lan"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_BODY"));
    }

    @Test
    void malformedJsonIs400BeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));
    }

    @Test
    void missingRequiredBodyIs400BeforeController()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));
    }
}
~~~

Từ root Maven project đã cấu hình, chạy:

~~~bash
./mvnw test -Dtest=ContractValidationApplicationTest
~~~

Trên Windows PowerShell/cmd có Maven wrapper: `mvnw.cmd test -Dtest=ContractValidationApplicationTest`. Nếu đã cài Maven toàn cục: `mvn test -Dtest=ContractValidationApplicationTest`.

**12 bài kiểm thử được thiết kế để pass** trong Spring Boot 3.2+ MVC + Validation + Test với source như trên. Kết quả cần quan sát:

| Nhóm | Input/đường gọi | Status | Mã/body trọng tâm |
| --- | --- | --- | --- |
| Method input hợp lệ | `?size=2` | 200 | `SIZE:2` |
| Method input sai constraint | `?size=0` | 400 | `INVALID_INPUT` |
| Method input âm | `?size=-5` | 400 | `INVALID_INPUT` |
| Thiếu input bắt buộc | Không có `size` | 400 | Spring xử lý missing required parameter. |
| Sai kiểu input | `size=abc` | 400 | Spring xử lý type conversion. |
| Return value hợp lệ | `/healthy-report` | 200 | `READY` |
| **Return value không hợp lệ** | `/broken-report` trả `""` | **500** | **`SERVER_CONTRACT_VIOLATION`** |
| DTO JSON hợp lệ | `username=Lan`, `age=26` | 201 | `accepted` |
| DTO JSON constraint fail | username trống, age 16 | 400 | `INVALID_BODY` |
| JSON thiếu `age` | `@NotNull` fail | 400 | `INVALID_BODY` |
| JSON sai cú pháp | Body parse fail | 400 | `MALFORMED_BODY` |
| JSON không có body | `@RequestBody(required=true)` | 400 | `MALFORMED_BODY` |

**Vì sao chỉ test status ở một số case?** Missing query param và sai kiểu thường được Spring MVC xử lý qua exception resolvers mặc định; body lỗi có thể đổi theo Spring Boot version, `ProblemDetail` config hay custom `@ControllerAdvice`. Không nên gắn test vào wording mặc định của Spring cho những trường hợp đó.

**Điều test không chứng minh:** bài kiểm thử trên chưa chạy với database, không chứng minh transaction rollback hay hiệu năng. Bộ test cũng không kiểm chứng mọi mô hình async/streaming hay service-level AOP validation. Đó là những phạm vi cần test riêng khi áp dụng dự án thật.

### 9.1. Chạy thử bằng curl

Khi ứng dụng đã chạy bằng `./mvnw spring-boot:run`:

~~~bash
curl -i "http://localhost:8080/api/contracts/page?size=0"
curl -i "http://localhost:8080/api/contracts/page?size=2"

curl -i "http://localhost:8080/api/contracts/broken-report"
curl -i "http://localhost:8080/api/contracts/healthy-report"

curl -i -X POST "http://localhost:8080/api/contracts/users" \
  -H "Content-Type: application/json" \
  -d '{"username":"","age":16}'
~~~

Dự kiến status lần lượt **400, 200, 500, 200, 400**. Lệnh dùng cú pháp shell Unix; trên Windows PowerShell, `curl.exe` và cách quoting/line continuation có thể khác. Không dùng payload chứa dữ liệu nhạy cảm thật chỉ để thử status code.

## 10. Jakarta `ExecutableValidator`: cách nhìn ở tầng Bean Validation

Ở tầng Jakarta Validation, có hai API riêng, cùng làm việc với method nhưng trên các giá trị khác nhau:

~~~java
Set<ConstraintViolation<T>> validateParameters(
        T object, Method method, Object[] parameterValues,
        Class<?>... groups);

Set<ConstraintViolation<T>> validateReturnValue(
        T object, Method method, Object returnValue,
        Class<?>... groups);
~~~

Đây là **chữ ký khái quát** của `ExecutableValidator`, không phải định nghĩa đầy đủ interface. Hai kết quả có ý nghĩa khác nhau:

- `validateParameters(...)` kiểm tra arguments mà **caller** cung cấp.
- `validateReturnValue(...)` kiểm tra giá trị mà **implementation** trả về.

Một unit test Jakarta Validation thuần, không cần mở web server:

~~~java
package com.example.contractvalidation;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ExecutableContractTest {

    static class ContractService {

        @NotBlank
        public String calculate(@Min(1) int size) {
            return "";
        }
    }

    @Test
    void inputAndOutputViolationsAreDistinct() throws Exception {
        try (var factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            var executables = validator.forExecutables();
            var service = new ContractService();
            Method method = ContractService.class
                    .getMethod("calculate", int.class);

            var inputErrors = executables.validateParameters(
                    service, method, new Object[] {0});

            var outputErrors = executables.validateReturnValue(
                    service, method, "");

            assertEquals(1, inputErrors.size());
            assertEquals(1, outputErrors.size());
        }
    }
}
~~~

**Điểm kiểm chứng:** test trên chỉ minh họa **Bean Validation phân biệt arguments và return value**; nó **không** tự gán HTTP 400/500. Quyết định HTTP nằm ở Spring MVC/mapping layer. Vì vậy không viết thư viện service với kỳ vọng rằng Jakarta `ConstraintViolation` tự có sẵn `HttpStatus`.

Nếu thêm file `ExecutableContractTest.java` vào cùng dự án, chạy:

~~~bash
./mvnw test -Dtest=ExecutableContractTest
~~~

Chú ý API `ValidatorFactory` extends `AutoCloseable` trong các Jakarta Validation versions hiện đại; nếu dùng provider/version khác cần kiểm tra đúng hợp đồng. Trong Spring Boot, thường inject `Validator` từ Spring context thay vì tự build factory trong production.

### Phân biệt method return validation với validate Bean riêng lẻ

~~~java
Set<ConstraintViolation<ProductResponse>> errors =
        validator.validate(productResponse);
~~~

Lời gọi này kiểm tra **constraints trên một bean instance**, không phải tự động trở thành `validateReturnValue(...)` trên một controller method. Nếu response DTO cần kiểm tra trước khi gửi, có thể kiểm tra chủ động trong service hoặc dùng executable validation đã cấu hình, nhưng cần rõ **khi nào** chạy và **exception** phát sinh đi đâu.

Một controller trả `ProductResponse` có record fields `@NotNull` nhưng không có return-value validation được kích hoạt vẫn có thể serialize response chưa hợp lệ. Annotation khai báo trên DTO **không thay thế** việc cấu hình/kiểm thử luồng thực thi.

## 11. Service-layer `@Validated` và những exception khác

Spring có **method validation qua AOP** với `@Validated` trên beans và constraint annotations trên methods. Ví dụ:

~~~java
@Service
@Validated
public class CatalogService {

    @NotBlank
    public String displayName(long productId) {
        return ""; // Cố ý vi phạm contract.
    }
}
~~~

Đây là snippet có imports và `@Service`, không phải file của chương trình chính. Nếu gọi qua Spring proxy và method validation được cấu hình, return value có thể bị phát hiện. Tuy nhiên exception có thể là **`ConstraintViolationException`** hoặc **`MethodValidationException`** tùy cấu hình validator/interceptor (và có thể khác khi dùng Spring `MethodValidationAdapter`).

**Không gắn `@ExceptionHandler(ConstraintViolationException.class)` trả 400 cho mọi trường hợp**. Cùng một kiểu exception có thể đến từ:

- service method nhận input từ web (có thể liên quan client nhưng còn cần phân quyền, mapping);
- service method được scheduler/queue gọi (không có client HTTP);
- **service return-value violation** (server tạo giá trị sai);
- custom constraint validator/metadata configuration bug (server bug).

Đúng hơn, hãy:

1. Đặt validation tại layer rõ ràng, hiểu nơi gọi.
2. Phân biệt input vs return value bằng ngữ cảnh method/executable validation.
3. Dùng domain errors riêng cho những lỗi mà client có thể sửa.
4. Để invariant violation/bất thường trong code trở thành server error và giám sát.
5. Không tự convert mọi `ValidationException` thành HTTP 400.

Trong Spring MVC 6.1+ nếu muốn built-in handler method validation, đừng đặt class-level `@Validated` trên controller chỉ để “bật validation”; Spring MVC đã có hỗ trợ trực tiếp và class-level `@Validated` có thể đổi cơ chế sang AOP.

## 12. Spring WebFlux: ý nghĩa 400/500 vẫn đúng, API có khác

Trong **Spring WebFlux**, individual object validation có exception điển hình **`WebExchangeBindException`** thay vì `MethodArgumentNotValidException` của Servlet MVC.

Nhưng với method validation, **`HandlerMethodValidationException`** cũng có vai trò tương tự:

- Constraint trực tiếp trên request method parameter → lỗi input, thường **400**.
- Constraint trên return value của handler → lỗi output, thường **500**.
- Spring WebFlux built-in validation và exception handling có cấu hình/đường thực thi riêng, đặc biệt với `Mono`/`Flux`.

Ví dụ ý tưởng:

~~~java
@GetMapping("/items")
Mono<String> items(@RequestParam @Min(1) int size) {
    // Ví dụ kiến trúc; cần controller WebFlux tương ứng.
    return Mono.just("count=" + size);
}
~~~

Đây là snippet, không phải ví dụ chạy độc lập và **không chứng minh** rằng một constraint đặt trên outer `Mono` sẽ tự kiểm tra tất cả giá trị phát ra. Với reactive publishers, phải hiểu cấp validation (publisher hay phần tử), timing, và response commitment.

WebFlux có thể trả `WebExchangeBindException` khi `@Valid @RequestBody Mono<Dto>` hoặc `@ModelAttribute` không hợp lệ, tùy chữ ký, argument resolving và phiên bản. Đừng import `MethodArgumentNotValidException` của MVC rồi mong nó là exception chuẩn trong mọi reactive handler.

Với cả hai stack, **lỗi server-generated return value không bao giờ được tự biến thành lỗi client chỉ vì validation xảy ra**.

## 13. Tùy biến response bằng `ProblemDetail` và message localization

Spring Framework 6.x hỗ trợ `org.springframework.http.ProblemDetail` và `org.springframework.web.ErrorResponse` để xây HTTP problem responses theo **RFC 9457**. `HandlerMethodValidationException` implements `ErrorResponse`, có `getStatusCode()` và `getBody()`.

Một API có thể dùng cùng structure cho 400 và 500:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Tham số yêu cầu không hợp lệ."
}
~~~

~~~json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Không thể hoàn tất yêu cầu."
}
~~~

Đây là **ví dụ về JSON do ứng dụng có thể chọn**, không phải cam kết response mặc định Spring Boot luôn có body giống hệt. Nếu bật `ProblemDetail`/custom handler, có thể thêm `instance`, error code hay trace ID, nhưng phải tránh đưa internal method name, DB values, raw rejected input vào response 500.

### Locale và MessageSource

- Với **input errors**, có thể hiển thị tên field công khai, mã lỗi và thông điệp đa ngữ phù hợp.
- Với **return-value errors**, nên dùng thông điệp public **chung** theo locale; lý do chi tiết cần nằm trong telemetry bảo mật nội bộ.
- Dùng `MessageSource`/message codes do server kiểm soát, không để client tự gửi key trỏ vào bundle nội bộ.
- Không đưa `FieldError#getRejectedValue()` hay `ConstraintViolation#getInvalidValue()` vào text interpolations hoặc structured error JSON.

Ví dụ message keys:

~~~properties
error.input=Tham số yêu cầu không hợp lệ.
error.body=Dữ liệu đầu vào không hợp lệ.
error.serverContract=Không thể hoàn tất yêu cầu.
~~~

Tương ứng file `messages_en.properties` có thể là:

~~~properties
error.input=Request parameters are invalid.
error.body=Request body is invalid.
error.serverContract=The request could not be completed.
~~~

Chọn mã lỗi từ server, truyền `Locale` của request đã được MVC resolve, và giữ nguyên status 400/500. **Đa ngữ không làm thay đổi trách nhiệm** của client/server.

## 14. Xử lý lỗi return value trong production

### 14.1. Monitoring

Một return-value contract failure cần được quan sát như lỗi server:

- Gắn error category `SERVER_CONTRACT_VIOLATION`.
- Theo dõi tỉ lệ 5xx, số lần theo route template, service version và release.
- Có trace/request ID không chứa token.
- Không tự serialize đầy đủ `HandlerMethodValidationException` nếu exception chứa target/parameter results nhạy cảm.
- Ghi nhận thông tin kỹ thuật đủ xử lý trong log có kiểm soát truy cập, retention và redaction.
- Cảnh báo khi tăng đột ngột sau deployment hoặc thay đổi mapper/schema.

### 14.2. Không retry mù quáng

Client có thể retry một số 5xx theo chính sách, nhưng với **POST có side effects**, return-value failure có thể xảy ra **sau khi ghi dữ liệu thành công**. Vì thế không bảo đảm retry an toàn chỉ dựa vào status 500. Cần idempotency key, reconciliation hoặc endpoint truy vấn trạng thái khi thích hợp.

### 14.3. Làm rõ hợp đồng response

Nếu endpoint yêu cầu field `status`, `id`, `amount`, hãy:

- Dùng response DTO riêng với invariants rõ.
- Không tạo response từ entity bị thiếu dữ liệu mà không kiểm tra.
- Test mapper trên cả null/empty/edge cases.
- Đặt kiểm tra contract ở tầng có thể kiểm soát transaction/side effect khi cần.
- Phân biệt các lỗi 500 do output validation với 500 do Jackson/serializer hoặc dependency.

### 14.4. Không nuốt exception để “thành công giả”

Nếu return-value validation fail, không được `catch` rồi trả `200 OK` với một DTO rỗng tùy tiện. Điều này làm client tưởng thành công và có thể phá invariants downstream. Nếu có fallback nghiệp vụ hợp lệ, phải xác định rõ trường hợp nào được fallback và đảm bảo kết quả vẫn thỏa hợp đồng.

## 15. Lỗi phổ biến khi thiết kế exception handling

| Anti-pattern | Tại sao sai | Cách làm đúng |
| --- | --- | --- |
| `@ExceptionHandler(HandlerMethodValidationException.class)` luôn trả 400 | Đổi return-value violation của server thành lỗi client. | Dùng `ex.getStatusCode()`/`isForReturnValue()`. |
| `@ExceptionHandler(ConstraintViolationException.class)` luôn trả 400 | ConstraintViolationException có thể đến từ return value/service. | Phân biệt layer/nguồn vi phạm, đừng suy diễn từ class. |
| Chỉ xử lý `MethodArgumentNotValidException` | Bỏ sót method validation trực tiếp, kể cả return value. | Xử lý thêm `HandlerMethodValidationException`. |
| Đặt `@Validated` lên controller rồi mong mọi exception giống MVC 6.1 | Chuyển sang AOP proxy path. | Hiểu và thống nhất cơ chế validation, test exception thực tế. |
| Trả `ex.getMessage()` khi return value sai | Có thể tiết lộ method/internal object/values. | Trả code/message công khai chung, log an toàn. |
| Gọi mọi 4xx là "Bean Validation error" | Conversion, missing parameter, auth, conflict khác nhau. | Phân loại theo nguồn phát sinh. |
| Dùng 422 để che return-value failure | 422 vẫn biểu thị lỗi phía request. | Trả 500 cho contract server thất bại. |
| Cho rằng `@Valid` trên DTO trả về luôn được kích hoạt | Không chắc có executable validation cho return value. | Cấu hình/đặt constraint kích hoạt và test. |
| Giả định 500 khiến transaction rollback | Exception có thể phát sinh sau commit. | Kiểm soát transaction/idempotency. |
| Bắt toàn bộ `Exception` trả 400 | Che server bugs và gây sai observability. | Handler cụ thể + fallback 5xx có kiểm soát. |
| Thay status sau khi response streaming đã commit | HTTP status có thể không thay được sau khi gửi headers. | Validate sớm/thiết kế reactive error channel. |
| Cho client raw rejected value và internal field paths | Lộ dữ liệu, thông tin nội bộ. | Redaction và allowlisted public error schema. |

## 16. Checklist kiểm thử và review

- [ ] Xác định từng constraint thuộc **request parameter**, **DTO input**, **service method**, hay **return value**.
- [ ] Với Spring MVC 6.1+, kiểm tra `HandlerMethodValidationException#isForReturnValue()` và `getStatusCode()`.
- [ ] Không cố định 400 cho mọi method validation exception.
- [ ] Có test input `@Min` vi phạm → 400; output `@NotBlank` vi phạm → **500**.
- [ ] Có test `@Valid @RequestBody` vi phạm → `MethodArgumentNotValidException` hoặc handler tương ứng.
- [ ] Có test JSON hỏng, missing required parameter và conversion failure; chúng không đồng nhất với output validation.
- [ ] Class-level `@Validated` trên controller phải có mục đích rõ và kiểm thử AOP vs built-in MVC.
- [ ] Handler return lỗi server không echo target, rejected value, response nội bộ hoặc exception cause.
- [ ] Giữ nguyên HTTP status và thông báo public chung cho 500; mã lỗi đủ ổn định cho monitoring.
- [ ] Input errors có thể trả field-level details nhưng chỉ những field/giá trị được phép công khai.
- [ ] Không tự xem service `ConstraintViolationException` là input error nếu không biết method origin.
- [ ] Thiết kế transaction boundary và idempotency cho các endpoint có side effect; 500 không chứng minh rollback.
- [ ] Với async/streaming, kiểm tra timing của return validation và khả năng response đã commit.
- [ ] Theo dõi 4xx/5xx tách biệt, có regression tests và log/telemetry được redaction.
- [ ] Không nhầm `400`, `409`, `422`, `500` và `503`; mỗi status mô tả một lớp trách nhiệm khác nhau.

**Kết luận:** Khi Spring validation phát hiện lỗi, hãy hỏi **giá trị vi phạm do ai cung cấp?** Nếu là input mà client kiểm soát, phản hồi 4xx (thường 400) giúp client sửa request. Nếu là **return value do server sinh ra**, đó là contract failure của server và phải giữ **500**. Với Spring MVC 6.1+, `HandlerMethodValidationException#isForReturnValue()` và `getStatusCode()` giúp giữ đúng ranh giới này; `MethodArgumentNotValidException` chỉ là một nhánh riêng khi validate đối tượng đầu vào.

## Tài liệu tham khảo

- Spring Framework 6.2 Reference — **Spring MVC Validation** (`MethodArgumentNotValidException` vs `HandlerMethodValidationException`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Javadoc — **HandlerMethodValidationException** (400 input, 500 return value): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Javadoc — **ResponseEntityExceptionHandler** (handler cho method validation): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework Reference — **Spring MVC Error Responses** (`ProblemDetail`/`ErrorResponse`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework Reference — **Validation with @RequestBody**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework Reference — **WebFlux Validation** (`WebExchangeBindException`, method validation): https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework Reference — **Spring Core Method Validation**: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Jakarta Bean Validation — **ExecutableValidator** contract: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator
