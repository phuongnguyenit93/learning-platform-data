# Phân biệt lỗi giải mã, chuyển kiểu và lỗi ràng buộc trong Spring WebFlux

## 1. Mục tiêu: xác định lỗi xảy ra ở tầng nào

Khi một request đi vào controller Spring WebFlux, dữ liệu phải đi qua một số bước trước khi nghiệp vụ có thể chạy. Với JSON body, Spring đọc bytes rồi giải mã thành object. Với query parameter, path variable hoặc header, Spring thường nhận chuỗi và chuyển chuỗi đó sang kiểu Java. Sau khi object được tạo và bind, Bean Validation có thể kiểm tra các quy tắc như `@NotBlank`, `@Email`, `@Min`. Cuối cùng, service có thể áp dụng quy tắc nghiệp vụ.

Ba loại lỗi trong đề bài khác nhau ở **thời điểm**, **cơ chế** và **cách sửa**:

1. **Lỗi giải mã (decoding/deserialization)**: bytes hoặc nội dung body không thể được codec/`HttpMessageReader` đọc thành kiểu đích.
2. **Lỗi chuyển kiểu (type conversion)**: một giá trị request dạng chuỗi không thể chuyển thành kiểu Java của argument/property.
3. **Lỗi ràng buộc (binding/validation)**: dữ liệu đã được đọc hoặc chuyển kiểu nhưng không thể bind đúng vào object, hoặc object vi phạm constraint.

Không nên gộp tất cả thành “JSON lỗi”. Một request có thể gửi JSON hoàn toàn hợp lệ nhưng query parameter `page=abc` vẫn lỗi chuyển kiểu; ngược lại, body có thể decode thành DTO thành công nhưng `email` vẫn không hợp lệ.

Bài này tập trung vào annotation-based controller của Spring WebFlux, cách phân biệt lỗi, exception/status thường gặp, cách xử lý thống nhất bằng `@ControllerAdvice`/`ProblemDetail` và cách kiểm thử với `WebTestClient`.

## 2. Toàn bộ pipeline từ HTTP bytes tới nghiệp vụ

```text
HTTP request
    |
    +--> Content-Type / body bytes
    |          |
    |          v
    |    HttpMessageReader / codec
    |          |
    |          v
    |    Decode / deserialize thành DTO
    |          |
    |          v
    +--> Query / path / header / cookie strings
               |
               v
         ConversionService
               |
               v
         Java argument / property
               |
               v
       Data binding vào command object
               |
               v
       Bean Validation (@Valid, @Min...)
               |
               v
       Controller method / service
               |
               v
       Business validation / persistence
```

Đây là mô hình khái niệm. Với một controller cụ thể, các argument resolver có thể xử lý từng tham số theo các nhánh khác nhau; ví dụ body và query parameter có thể được giải quyết độc lập. Điểm cốt lõi là lỗi decode không giống lỗi convert, và cả hai đều xảy ra trước hoặc trong giai đoạn đưa dữ liệu vào method. Bean Validation kiểm tra object/argument sau khi các giá trị đã có kiểu phù hợp.

### Một ví dụ duy nhất, ba lỗi khác nhau

Giả sử API nhận:

```http
POST /accounts?page=abc
Content-Type: application/json

{"name":"","email":"not-an-email","age":16}
```

Với controller mong đợi:

- `page` là `int`.
- Body là `CreateAccount`.
- `name` phải không rỗng, `email` phải đúng định dạng, `age` phải từ 18 trở lên.

Có thể xảy ra:

- `page=abc` không thể chuyển thành `int`: **type conversion failure**.
- Nếu body là `{"name":` thì JSON không hoàn chỉnh: **decoding failure**.
- Nếu body là JSON hợp lệ như ví dụ nhưng các giá trị vi phạm constraint: **validation failure**.

Trong request thực tế, lỗi đầu tiên được phát hiện có thể ngăn những bước sau chạy; không nhất thiết server trả đồng thời tất cả lỗi.

## 3. Lỗi giải mã: bytes/body không thể thành object

### 3.1. Vai trò của `HttpMessageReader` và codec

Với `@RequestBody`, Spring WebFlux dùng một `HttpMessageReader` tương thích với media type và kiểu đích để đọc body. Các codec thường gặp:

- Jackson JSON decoder: đọc JSON thành Java object.
- String decoder: đọc nội dung text thành `String`.
- Byte array decoder: đọc nội dung thành `byte[]`.
- Form reader: phân tích `application/x-www-form-urlencoded`.
- Multipart reader: phân tích các phần multipart.

Ví dụ:

```java
@PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Account> create(@RequestBody Mono<Account> body) {
    return body;
}
```

Request body phải là JSON có thể decode thành `Account`, và ứng dụng phải có codec hỗ trợ kiểu đó.

### 3.2. Các trường hợp lỗi decode

**JSON sai cú pháp**

```json
{"name":"Lan","age":
```

Parser không thể hoàn tất cấu trúc JSON. Body không thể được chuyển thành object.

**JSON có cấu trúc không tương thích kiểu đích**

Giả sử `age` là `int`:

```json
{"name":"Lan","age":"many"}
```

Nếu cấu hình Jackson không thể coercion chuỗi `"many"` sang số, decoder phát lỗi. Một số giá trị chuỗi số có thể được Jackson coercion tùy cấu hình, nên không nên dựa vào một ví dụ duy nhất để khẳng định mọi string-number đều thất bại.

**JSON shape không phù hợp**

Nếu method mong đợi một object `Account` nhưng body là một array hoặc scalar, decoder có thể không tạo được kiểu đích. Hành vi cụ thể phụ thuộc codec và cấu hình.

**Body rỗng trong khi argument bắt buộc**

Nếu request không gửi body nhưng method yêu cầu `@RequestBody` bắt buộc, WebFlux báo lỗi input thay vì tự tạo object mặc định. Nếu body có thể vắng mặt, khai báo `required=false` hoặc kiểu/contract phù hợp.

**Không có codec đọc media type hoặc media type không hỗ trợ**

Đây là trường hợp cần phân biệt: `Content-Type` không được hỗ trợ thường dẫn tới **415 Unsupported Media Type** ở bước chọn reader, không phải lỗi cú pháp JSON. Nếu media type được hỗ trợ nhưng nội dung sai, đó mới là lỗi decoding.

**Payload vượt giới hạn**

Nếu body vượt giới hạn bộ nhớ/đọc của codec hoặc multipart reader, server có thể trả **413 Payload Too Large** hoặc lỗi tương ứng theo cấu hình. Đây là giới hạn kích thước, không phải lỗi validation của field.

### 3.3. Exception và HTTP status

Trong WebFlux, lỗi đọc/giải mã body thường được đưa ra dưới dạng exception input 400, chẳng hạn `ServerWebInputException` với nguyên nhân bên dưới là lỗi codec/decoder. Exception cụ thể và cause phụ thuộc loại `HttpMessageReader`, codec và phiên bản.

Cần phân biệt:

| Tình huống | Kết quả HTTP thường gặp |
|---|---|
| JSON sai cú pháp | 400 Bad Request |
| JSON không thể decode thành kiểu đích | 400 Bad Request |
| Body bắt buộc bị thiếu | 400 Bad Request |
| `Content-Type` không được hỗ trợ | 415 Unsupported Media Type |
| Payload vượt giới hạn | 413 Payload Too Large |

Không bắt `DecodingException` ở mọi nơi rồi trả 400 theo cách thủ công. Hãy để WebFlux xử lý exception chuẩn hoặc chuẩn hóa response tại tầng `@ControllerAdvice`, đồng thời giữ nguyên nguyên nhân để log/trace nội bộ.

## 4. Lỗi chuyển kiểu: request string không thành kiểu Java

### 4.1. Những argument nào cần conversion?

Nhiều request value được nhận ban đầu dưới dạng chuỗi. Nếu argument không khai báo `String`, Spring tự áp dụng type conversion qua `ConversionService` và converter/formatter đã đăng ký.

Các ví dụ thường gặp:

- `@RequestParam("page") int page`
- `@PathVariable UUID id`
- `@RequestHeader("X-Region") Locale region`
- `@CookieValue("expires") LocalDate expires`
- `@MatrixVariable("count") long count`

Trong WebFlux, `@RequestParam` bind query parameters. Form data và multipart được truy cập qua cơ chế riêng hoặc data binding vào command object; không nên nhầm mô hình Servlet request parameter với WebFlux.

### 4.2. Ví dụ query parameter không chuyển được

```java
@GetMapping("/search")
public Mono<String> search(@RequestParam int page) {
    return Mono.just("page=" + page);
}
```

Request hợp lệ:

```http
GET /search?page=3
```

Spring chuyển chuỗi `"3"` thành `int 3`.

Request không hợp lệ:

```http
GET /search?page=three
```

Converter số không thể chuyển `"three"` thành `int`. Controller method không chạy với giá trị `page` sai. Đây là **lỗi chuyển kiểu**, không phải lỗi decode JSON, vì request không có body JSON nào cần parse.

Một ví dụ với `LocalDate`:

```java
@GetMapping("/events")
public Flux<Event> events(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate from) {
    return eventService.from(from);
}
```

Giá trị `from=2026-03-21` có thể được chuyển thành `LocalDate`. Giá trị `from=tomorrow` không đúng định dạng ISO date nên conversion thất bại.

### 4.3. Missing value khác conversion failure

Hai request này khác nhau:

```text
GET /search
GET /search?page=abc
```

Nếu `page` là required và không có giá trị, Spring có thể phát `MissingRequestValueException` (một loại `ServerWebInputException`). Nếu có giá trị nhưng không parse được, đó là lỗi conversion, thường được bọc trong exception input/type mismatch tương ứng.

Giá trị rỗng cũng cần chú ý. Khi một empty string được converter biến thành `null`, Spring có thể coi kết quả như giá trị bị thiếu. Điều này hay gặp với `Long`, `UUID` hoặc kiểu không nhận `null`. Nếu argument thật sự optional, dùng `required=false`, `Optional<T>` hoặc `@Nullable` theo contract.

### 4.4. Cấu hình Converter và Formatter

Khi định dạng request không phải định dạng mặc định, có thể đăng ký converter/formatter toàn cục:

```java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                OrderCode.class,
                OrderCode::parse
        );
    }
}
```

Đây là snippet: `OrderCode` phải là kiểu domain của ứng dụng và có static method `parse(String)`. Sau khi đăng ký, Spring có thể chuyển query/path/header string sang `OrderCode` khi argument resolver yêu cầu kiểu đó.

Với tùy chỉnh theo controller hoặc theo attribute, có thể dùng `@InitBinder` để cấu hình `WebDataBinder`. Tránh đặt logic nghiệp vụ phức tạp trong converter; converter nên tập trung vào cú pháp/biểu diễn. Ví dụ, chuyển `"PENDING"` thành enum là conversion; kiểm tra đơn hàng có được phép chuyển sang trạng thái PENDING hay không là business rule.

### 4.5. Exception và HTTP status

Conversion failure từ request value thường được ánh xạ thành **400 Bad Request**. Tên exception/cause có thể khác giữa named-value argument resolver và data binding vào object. Khi debug, xem `MethodParameter`, tên argument, target type và cause thay vì chỉ đọc message.

Không đổi mọi conversion failure thành 422 chỉ vì dữ liệu “không hợp lệ”. Nếu giá trị không thể biểu diễn thành kiểu argument đã khai báo, 400 là lựa chọn mặc định phù hợp với request syntax/type.

## 5. Lỗi binding: giá trị không thể gán vào object

**Data binding** là bước gắn các request value vào property hoặc constructor parameter của một command object. Đây thường là cách xử lý form/search criteria:

```java
public class SearchForm {
    private int page;
    private LocalDate from;

    public int getPage() { return page; }
    public void setPage(int page) { this.page = page; }

    public LocalDate getFrom() { return from; }
    public void setFrom(LocalDate from) { this.from = from; }
}
```

```java
@GetMapping("/search-form")
public Mono<String> search(@ModelAttribute SearchForm form) {
    return Mono.just("page=" + form.getPage());
}
```

Spring tạo/bind object từ các request values. Nếu `page=abc`, conversion của property thất bại. `BindingResult` có thể giữ `FieldError` cùng rejected value và thông tin field. Tùy controller signature, binding error có thể được xử lý ngay tại method hoặc được ném thành `WebExchangeBindException`.

### Dùng `BindingResult` ngay sau `@ModelAttribute`

```java
@GetMapping("/search-form")
public Mono<ResponseEntity<?>> search(
        @Valid @ModelAttribute SearchForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body("Invalid search fields"));
    }

    return Mono.just(ResponseEntity.ok(form));
}
```

Đây là snippet minh họa. `BindingResult` phải nằm ngay sau argument được bind/validate. Nếu lỗi được thu vào `BindingResult`, controller method vẫn được gọi để tự quyết định response. Nếu không có `Errors`/`BindingResult` ở vị trí thích hợp, Spring có thể phát `WebExchangeBindException`.

Binding error không nhất thiết là Bean Validation error. Ví dụ, `page=abc` có thể tạo field conversion error trong `BindingResult`; còn `page=-1` có thể chuyển thành số thành công nhưng vi phạm `@Min(0)` ở bước validation.

## 6. Lỗi ràng buộc: object đã có kiểu nhưng vi phạm constraint

Bean Validation kiểm tra giá trị/đối tượng sau khi chúng đã được decode hoặc bind. Những annotation phổ biến:

| Constraint | Kiểm tra |
|---|---|
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi không null, không rỗng và có ký tự không phải whitespace |
| `@NotEmpty` | Chuỗi/collection/map/array không rỗng |
| `@Size(min, max)` | Độ dài hoặc kích thước trong khoảng |
| `@Email` | Chuỗi phù hợp quy tắc email của validator |
| `@Min` / `@Max` | Giới hạn số |
| `@Positive` | Số dương |
| `@Past` / `@Future` | Mốc thời gian ở quá khứ/tương lai |

Ví dụ DTO:

```java
public record CreateAccount(
        @NotBlank String name,
        @Email String email,
        @Min(18) int age
) {}
```

Body sau là JSON hợp lệ và decode thành record được:

```json
{
  "name": "",
  "email": "not-an-email",
  "age": 16
}
```

Nhưng object vi phạm ba constraint. Đây là **lỗi validation**, không phải lỗi decoding. JSON parser không chịu trách nhiệm quyết định email có hợp lệ theo nghiệp vụ hay age có đủ 18 hay không.

### `@Valid` và `@Validated`

Trong WebFlux, có thể dùng:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccount> body) {
    return body.map(accountService::create);
}
```

`@Valid` yêu cầu Bean Validation áp dụng cho object được đọc. Với validation từng method parameter như `@RequestBody`, WebFlux có thể phát `WebExchangeBindException` nếu object vi phạm constraint. Đây là lỗi 400 mặc định.

`@Valid` không phải constraint annotation. Nó yêu cầu cascade validation cho object/nested object. `@NotNull`, `@Min`, `@NotBlank` mới là constraint.

### Method validation khác validation một object

Khi constraint được đặt trực tiếp trên method parameter, ví dụ:

```java
@GetMapping("/pages")
public Mono<String> pages(@RequestParam @Min(1) @Max(100) int page) {
    return Mono.just("page=" + page);
}
```

Spring Framework 6.1+ có method validation tích hợp. Lỗi constraint trên method parameter có thể tạo `HandlerMethodValidationException`, trong khi validation riêng một `@RequestBody` hoặc `@ModelAttribute` thường tạo `WebExchangeBindException`.

Ứng dụng nên chuẩn bị xử lý cả hai loại exception. Nếu controller có class-level `@Validated`, method validation có thể được áp dụng qua AOP proxy; để dùng built-in controller method validation của Spring Framework 6.1+, cần xem lại việc đặt `@Validated` ở cấp class.

### Nested validation

```java
public record Address(
        @NotBlank String city,
        @NotBlank String country
) {}

public record CreateAccount(
        @NotBlank String name,
        @Valid Address address
) {}
```

`@Valid` trên `address` yêu cầu validator đi sâu vào object lồng nhau. Nếu bỏ `@Valid`, các constraint bên trong `Address` có thể không được cascade từ `CreateAccount`.

## 7. Bảng phân biệt nhanh ba nhóm lỗi

| Đặc điểm | Decode | Type conversion | Binding / validation |
|---|---|---|---|
| Dữ liệu đầu vào | Body bytes/stream | Chuỗi request value | Các property/argument của object |
| Cơ chế | `HttpMessageReader`, codec, Jackson | `ConversionService`, `Converter`, `Formatter` | `WebDataBinder`, `BindingResult`, Bean Validation |
| Ví dụ | JSON thiếu dấu `}` | `page=abc` nhưng argument là `int` | `age=16` vi phạm `@Min(18)` |
| Controller method chạy? | Thường không nếu body argument không resolve được | Thường không nếu argument không convert được | Có thể chạy nếu có `BindingResult`; nếu không thường phát exception |
| Exception thường gặp | `ServerWebInputException` với codec cause | `ServerWebInputException`/input type mismatch hoặc binding field error | `WebExchangeBindException`, `HandlerMethodValidationException` |
| HTTP status mặc định | Thường 400 | Thường 400 | Thường 400 |
| Cách sửa | Sửa JSON/codec/target type | Sửa giá trị/format hoặc đăng ký converter | Sửa field/constraint hoặc xử lý lỗi theo contract |

Một số lỗi không nằm trong ba nhóm:

- Media type request không hỗ trợ: 415.
- Payload vượt giới hạn: 413.
- Thiếu request value bắt buộc: thường 400 với `MissingRequestValueException`.
- Vi phạm quy tắc nghiệp vụ như tài khoản đã tồn tại: do ứng dụng quyết định, thường có thể là 409 Conflict hoặc 422 Unprocessable Content tùy API contract.
- Lỗi server/dependency: không được giả dạng thành lỗi input 400.

## 8. Cách đọc exception và tìm nguyên nhân gốc

Khi nhận một HTTP 400, không nên chỉ log `exception.getMessage()`. Cần xem:

1. Exception top-level thuộc loại nào?
2. Có `MethodParameter` nào được liên kết không?
3. Argument/property tên gì, target type là gì?
4. `BindingResult` có field error nào?
5. Cause chain có lỗi codec, Jackson, conversion hoặc validator nào?
6. Lỗi xảy ra trước khi controller chạy, trong binding, trong validation hay trong service?

Ví dụ log an toàn:

```java
log.warn(
        "Request input failed: exceptionType={}, message={}",
        error.getClass().getSimpleName(),
        error.getMessage()
);
```

Trong log nội bộ có thể ghi cause chain theo chính sách. Không trả stack trace, SQL, file path, tên class nội bộ hoặc rejected value nhạy cảm cho client.

### `WebExchangeBindException`

`WebExchangeBindException` là một loại `ServerWebInputException` và chứa `BindingResult`. Có thể đọc:

- `getFieldErrors()` để lấy lỗi theo property.
- `getGlobalErrors()` để lấy lỗi cấp object.
- `getBindingResult()` để truy cập toàn bộ lỗi binding/validation.
- `getField()` và `getCode()` của từng `FieldError` để xây response có cấu trúc.

### `HandlerMethodValidationException`

Exception này đại diện cho validation áp dụng trên method và nhóm kết quả theo method parameter. Spring cung cấp `visitResults(...)` để phân loại parameter như request param, header, model attribute và các loại khác. Dùng API này nếu cần tạo lỗi nhất quán cho từng argument.

### Lỗi decode và conversion

Lỗi decode thường có cause từ codec/decoder (ví dụ `DecodingException` hoặc exception Jackson). Lỗi conversion có thể có cause từ `ConversionService`, `ConversionFailedException`, `IllegalArgumentException` hoặc một loại input exception. Không nên dựa duy nhất vào tên exception lồng nhau như một public API ổn định; cách bọc có thể thay đổi theo resolver/codec/phiên bản.

## 9. Chuẩn hóa lỗi bằng `ProblemDetail` và `@ControllerAdvice`

Một API tốt trả lỗi có cấu trúc ổn định, nhưng không tiết lộ nội bộ. Spring Framework hỗ trợ RFC 9457 qua `ProblemDetail` và `ErrorResponse`. Trong WebFlux, có thể dùng `@RestControllerAdvice` hoặc mở rộng `ResponseEntityExceptionHandler`.

Ví dụ xây response validation:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ProblemDetail> handleBinding(
            WebExchangeBindException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid."
        );
        problem.setTitle("Validation failed");

        List<Map<String, String>> errors =
                exception.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "code", error.getCode() == null
                                        ? "invalid"
                                        : error.getCode()
                        ))
                        .toList();

        problem.setProperty("errors", errors);
        return ResponseEntity.badRequest().body(problem);
    }
}
```

Đây là snippet cần import `ProblemDetail`, `HttpStatus`, `ResponseEntity`, `WebExchangeBindException`, `RestControllerAdvice`, `ExceptionHandler`, `List` và `Map`.

Trong ứng dụng đầy đủ, cũng cần xử lý `HandlerMethodValidationException`, lỗi input/conversion và lỗi domain theo chính sách. Không trả rejected value trực tiếp nếu có thể chứa password, token, số giấy tờ hoặc dữ liệu cá nhân.

Ví dụ response:

```json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "errors": [
    {"field": "name", "code": "NotBlank"},
    {"field": "email", "code": "Email"}
  ]
}
```

`ProblemDetail` giúp client nhận status, title, detail và field errors một cách nhất quán. Message hiển thị nên được kiểm soát và có thể quốc tế hóa qua `MessageSource`; message exception gốc không phải lúc nào cũng phù hợp để gửi trực tiếp.

### Không gom mọi lỗi thành 400

Một exception handler tổng quát kiểu `@ExceptionHandler(Exception.class)` rồi trả 400 có thể che lỗi NullPointerException, bug lập trình hoặc lỗi database thành “request sai”. Hãy phân loại exception input, validation, domain và server; lỗi không biết nên giữ 5xx để điều tra.

## 10. Kiểm thử từng nhóm lỗi với `WebTestClient`

Một bộ test nên có tối thiểu các trường hợp:

| Test input | Nhóm cần xác minh | Kết quả dự kiến |
|---|---|---|
| JSON sai cú pháp | Decode | 400 |
| JSON field có kiểu không thể coercion | Decode | 400 |
| `?page=abc` cho argument `int` | Type conversion | 400 |
| `?from=not-a-date` cho `LocalDate` | Type conversion | 400 |
| JSON hợp lệ nhưng `name` blank | Bean Validation | 400 |
| `page=0` với `@Min(1)` | Method validation | 400 |
| JSON hợp lệ và đủ constraint | Thành công | 200 |

Đừng chỉ assert status nếu mục tiêu là xác định chính xác nhóm lỗi. Trong unit/integration test, có thể kiểm tra `ProblemDetail.title`, field error code hoặc trace nội bộ. Tuy nhiên, không phụ thuộc vào một message mặc định của Jackson vì nội dung đó có thể thay đổi theo phiên bản.

## 11. Dự án Java 17+ chạy được: Spring Boot WebFlux

Ví dụ tạo một API nhỏ có ba đường input độc lập:

- `POST /accounts`: decode JSON rồi validate DTO.
- `GET /lookup?page=...&from=...`: convert query string thành `int` và `LocalDate`.
- `GET /pages?page=...`: method validation cho giới hạn page.

Dùng Java 17+, Maven và Spring Boot 3.3.5.

### 11.1. Cấu trúc thư mục

```text
webflux-input-errors/
├── pom.xml
└── src/
    ├── main/java/edu/demo/
    │   ├── InputErrorsApplication.java
    │   ├── AccountController.java
    │   └── CreateAccount.java
    └── test/java/edu/demo/
        └── InputErrorsTest.java
```

### 11.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-input-errors</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 11.3. `InputErrorsApplication.java`

```java
package edu.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(InputErrorsApplication.class, args);
    }
}
```

### 11.4. `CreateAccount.java`

```java
package edu.demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateAccount(
        @NotBlank String name,
        @Email String email,
        @Min(18) int age
) {
}
```

### 11.5. `AccountController.java`

```java
package edu.demo;

import java.time.LocalDate;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class AccountController {

    @PostMapping(
            path = "/accounts",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<CreateAccount> create(
            @Valid @RequestBody Mono<CreateAccount> body) {
        return body;
    }

    @GetMapping("/lookup")
    public Mono<String> lookup(
            @RequestParam int page,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate from) {

        return Mono.just("page=" + page + ",from=" + from);
    }

    @GetMapping("/pages")
    public Mono<String> pages(
            @RequestParam @Min(1) @Max(100) int page) {
        return Mono.just("page=" + page);
    }
}
```

Controller không khai báo class-level `@Validated`; ví dụ dùng method validation tích hợp của Spring Framework 6.1+ cho `@Min` và `@Max` trên argument `page`.

### 11.6. `InputErrorsTest.java`

```java
package edu.demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class InputErrorsTest {

    @Autowired
    WebTestClient client;

    @Test
    void validJsonAndValidFieldsReturn200() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "email": "lan@example.com",
                          "age": 22
                        }
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan");
    }

    @Test
    void malformedJsonReturns400() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void nonCoercibleJsonFieldReturns400() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "email": "lan@example.com",
                          "age": "many"
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidPageStringReturns400() {
        client.get()
                .uri("/api/lookup?page=abc&from=2026-03-21")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidDateStringReturns400() {
        client.get()
                .uri("/api/lookup?page=2&from=not-a-date")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void beanValidationFailureReturns400() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "",
                          "email": "not-an-email",
                          "age": 16
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void methodConstraintFailureReturns400() {
        client.get()
                .uri("/api/pages?page=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validQueryArgumentsReturn200() {
        client.get()
                .uri("/api/lookup?page=3&from=2026-03-21")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("page=3,from=2026-03-21");
    }
}
```

Chạy ở thư mục dự án:

```bash
mvn test
```

Khi tải được dependencies và môi trường test hoạt động, có tám test. Kết quả mong đợi là `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`. Đây là dự án ví dụ để người học tự chạy; trạng thái pass chỉ được xác nhận sau khi thực thi Maven trong môi trường thật.

### 11.7. Đọc ý nghĩa từng test

| Test | Điều được chứng minh |
|---|---|
| `validJsonAndValidFieldsReturn200` | JSON decode được, các constraint hợp lệ |
| `malformedJsonReturns400` | Decoder không parse được body |
| `nonCoercibleJsonFieldReturns400` | Decoder không thể gán token `age` vào kiểu `int` |
| `invalidPageStringReturns400` | Conversion từ query string sang `int` thất bại |
| `invalidDateStringReturns400` | Formatter không parse được ISO date |
| `beanValidationFailureReturns400` | DTO được tạo nhưng vi phạm Bean Validation |
| `methodConstraintFailureReturns400` | Argument có kiểu đúng nhưng vi phạm `@Min` |
| `validQueryArgumentsReturn200` | Conversion query string thành công |

Lưu ý: các test trên xác nhận status HTTP và hành vi endpoint, không khẳng định một tên exception/cause nội bộ duy nhất. Nếu cần test loại exception cụ thể, viết unit test cho resolver/converter hoặc kiểm tra `ProblemDetail` do ứng dụng tự chuẩn hóa.

## 12. Cách xử lý từng loại lỗi trong thực tế

### 12.1. Decode error

- Xác nhận request `Content-Type` đúng.
- Kiểm tra JSON syntax, shape và kiểu đích.
- Kiểm tra codec/Jackson module và custom decoder.
- Không nới lỏng coercion cho mọi trường hợp nếu điều đó làm API chấp nhận payload mơ hồ.
- Giới hạn payload và tránh buffer toàn bộ stream không cần thiết.

### 12.2. Conversion error

- Xác định argument name và target type.
- Kiểm tra format hợp đồng: số, UUID, ngày, enum, locale.
- Dùng `@DateTimeFormat`/`@NumberFormat` khi phù hợp.
- Đăng ký `Converter`/`Formatter` ở `WebFluxConfigurer` hoặc `@InitBinder` cho kiểu domain.
- Quy định rõ empty/missing/nullable thay vì phụ thuộc ngẫu nhiên vào null coercion.

### 12.3. Binding và validation error

- Dùng `@Valid` cho command object/DTO.
- Đặt constraint ở đúng field và nested object.
- Dùng `@Valid` ở nested property để cascade.
- Với `@ModelAttribute`, dùng `BindingResult` ngay sau argument nếu muốn xử lý tại controller.
- Xử lý cả `WebExchangeBindException` và `HandlerMethodValidationException`.
- Trả field errors có cấu trúc, không gửi stack trace hoặc rejected value nhạy cảm.

### 12.4. Business validation

Bean Validation phù hợp cho constraint độc lập với trạng thái hệ thống như email có hình thức hợp lệ, tuổi trong khoảng hoặc field bắt buộc. Quy tắc phụ thuộc dữ liệu hiện tại cần nằm ở service/domain:

- Username đã được sử dụng.
- Số dư không đủ.
- Đơn hàng đã chuyển sang trạng thái không thể sửa.
- Ngày giao hàng không còn chỗ.

Không truy vấn database trong custom validator cho mọi field nếu điều đó tạo nhiều I/O ẩn. Quy tắc phụ thuộc trạng thái nên có luồng service rõ ràng và mapping lỗi domain theo API contract.

## 13. Chuẩn hóa status và response

Một bảng định hướng:

| Lỗi | Status thường phù hợp | Ví dụ |
|---|---:|---|
| Body decode sai cú pháp | 400 | JSON thiếu dấu ngoặc |
| Request value không convert được | 400 | `page=abc` cho `int` |
| Binding/Bean Validation | 400 | `name` blank |
| Thiếu input bắt buộc | 400 | thiếu query param/header/body bắt buộc |
| Media type không hỗ trợ | 415 | gửi `text/plain` vào JSON-only endpoint |
| Payload quá lớn | 413 | vượt giới hạn body |
| Quy tắc domain xung đột | 409 | username đã tồn tại |
| Nội dung có kiểu/format hợp lệ nhưng không thể xử lý theo nghiệp vụ | 422 có thể phù hợp | trạng thái yêu cầu không thể thực hiện theo contract |
| Lỗi không mong đợi của server | 500 | bug hoặc dependency lỗi không được phân loại |

400 là mặc định thường gặp cho input parsing/conversion/validation trong WebFlux. 409 và 422 là quyết định API/domain, không phải Spring tự động suy ra mọi lỗi business.

### `ResponseEntityExceptionHandler` và `ErrorResponse`

Spring WebFlux có các exception framework triển khai `ErrorResponse`, cung cấp status, headers và body theo Problem Details. `ResponseEntityExceptionHandler` là base class tiện lợi để xử lý các exception WebFlux và `ErrorResponseException` theo cách tập trung.

Trong ứng dụng, nên:

1. Dùng response schema ổn định.
2. Map lỗi field thành mã lỗi/field path.
3. Giữ cause và trace ID trong log nội bộ.
4. Không gửi exception message nguyên bản cho client nếu có thể lộ chi tiết.
5. Phân biệt input errors với lỗi server và lỗi domain.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi mọi lỗi 400 là “validation error” | Không phân biệt parse, conversion và constraint | Ghi nhận loại exception/cause và tầng phát sinh |
| Dùng Bean Validation để parse chuỗi thành số | Validation chạy sau conversion | Dùng target type/Converter/Formatter |
| Dùng `@Email` để xử lý JSON sai cú pháp | Codec không thể tạo DTO nên validator chưa chạy | Sửa payload hoặc decoder |
| Cho rằng Content-Type đúng đồng nghĩa JSON hợp lệ | Body vẫn có thể sai syntax/shape | Kiểm tra decode và validation riêng |
| Gộp decode failure và unsupported media type | Trả sai status hoặc thông báo | 400 cho parse; 415 cho media type không hỗ trợ |
| Dùng `@Valid` nhưng bỏ `@Valid` ở nested object | Constraint lồng nhau không được cascade | Đặt `@Valid` trên nested property |
| Quên `HandlerMethodValidationException` | Một số lỗi method constraint không được xử lý thống nhất | Xử lý cả exception method validation và bind validation |
| Chỉ xử lý `WebExchangeBindException` | Bỏ sót conversion hoặc method validation | Có handler input tổng quát và handler validation cụ thể |
| Trả rejected value không mask | Có thể rò password/token/PII | Trả field + error code, bỏ raw value |
| Bắt `Exception` và luôn trả 400 | Che bug và lỗi server thành client error | Xử lý exception cụ thể, để lỗi không mong đợi là 5xx |
| Đặt business rule trong Converter | Conversion trở thành logic phụ thuộc DB/trạng thái | Giữ converter thuần cú pháp, kiểm tra nghiệp vụ ở service |
| Chỉ test happy path | Không phát hiện các tầng input failure | Test decode, conversion, binding, validation riêng |

## 15. Checklist chẩn đoán request lỗi

Khi endpoint trả 400, kiểm tra theo thứ tự:

1. **Request có tới đúng endpoint không?** Xác nhận path, method và mapping.
2. **Media type có được hỗ trợ không?** Nếu không, lỗi thường là 415.
3. **Body bytes có parse được không?** Kiểm tra JSON syntax và shape.
4. **Kiểu DTO có tương thích token không?** Kiểm tra number/string/array/object, custom codec và Jackson configuration.
5. **Query/path/header có convert được không?** Xác nhận target Java type và format.
6. **Giá trị bắt buộc có bị thiếu hoặc rỗng không?** Phân biệt missing với invalid.
7. **BindingResult có field error không?** Kiểm tra property path, rejected type và error code.
8. **Bean Validation có chạy không?** Xác nhận `@Valid`, nested `@Valid` và validator dependency.
9. **Có method validation không?** Xử lý `HandlerMethodValidationException` nếu constraint nằm trực tiếp trên parameter/return.
10. **Có business validation sau controller không?** Không nhầm conflict domain với malformed input.
11. **Response error có được chuẩn hóa không?** Kiểm tra ProblemDetail, status và correlation ID.
12. **Log có bảo vệ dữ liệu nhạy cảm không?** Không log raw body/rejected value tùy tiện.

## 16. Bài tập tự kiểm tra

**Bài 1.** Endpoint nhận `@RequestBody CreateAccount`. Request gửi JSON thiếu dấu `}`. Lỗi thuộc nhóm nào?

**Đáp án:** Decode/deserialization failure. JSON chưa thể được parse thành DTO; Bean Validation chưa có object để kiểm tra.

**Bài 2.** Endpoint nhận `@RequestParam int page`. Client gửi `page=abc`. Lỗi thuộc nhóm nào?

**Đáp án:** Type conversion failure. Chuỗi query không chuyển được thành `int`.

**Bài 3.** JSON `{"name":"","email":"bad","age":17}` parse thành record thành công nhưng DTO có `@NotBlank`, `@Email`, `@Min(18)`. Lỗi thuộc nhóm nào?

**Đáp án:** Bean Validation failure. Dữ liệu đã có kiểu nhưng vi phạm constraint.

**Bài 4.** `Content-Type: text/plain` gửi tới endpoint chỉ nhận JSON. Có phải lỗi decode JSON không?

**Đáp án:** Không. Đây là unsupported media type, thường trả 415 trước khi JSON decoder xử lý body.

**Bài 5.** `@Valid @RequestBody Mono<Dto>` vi phạm constraint thường phát exception nào trong WebFlux?

**Đáp án:** `WebExchangeBindException` cho validation từng method parameter; nếu method validation áp dụng do constraint trực tiếp trên parameter, có thể là `HandlerMethodValidationException`.

**Bài 6.** `@Valid` có phải constraint annotation không?

**Đáp án:** Không. Nó yêu cầu cascade validation. `@NotNull`, `@Min`, `@NotBlank` mới là constraint.

**Bài 7.** Query `from=` thành empty string nhưng target là `UUID` hoặc `Long`. Vì sao có thể bị coi như missing?

**Đáp án:** Converter có thể biến empty string thành `null`; Spring có thể coi kết quả null như giá trị request bị thiếu nếu argument bắt buộc.

**Bài 8.** Username đã tồn tại trong database là lỗi conversion hay Bean Validation?

**Đáp án:** Thông thường là business/domain validation vì nó phụ thuộc trạng thái hệ thống hiện tại; service/domain kiểm tra và map theo API contract.

## 17. Ghi nhớ

- **Decode**: body bytes/stream → Java object qua `HttpMessageReader`/codec. JSON sai cú pháp hoặc shape không tương thích thường 400.
- **Conversion**: request string → kiểu Java qua `ConversionService`/`Converter`/`Formatter`. Ví dụ `page=abc` cho `int`, thường 400.
- **Binding**: gắn request values vào object/property; lỗi có thể nằm trong `BindingResult`.
- **Bean Validation**: object đã có kiểu nhưng vi phạm constraint; WebFlux dùng `WebExchangeBindException` hoặc `HandlerMethodValidationException` tùy cơ chế.
- **Business validation**: quy tắc phụ thuộc trạng thái hệ thống, nên nằm trong service/domain.
- **415** là media type không hỗ trợ; **413** là payload vượt giới hạn; chúng không phải lỗi Bean Validation.
- Hãy chuẩn hóa error response nhưng vẫn giữ nguyên nguyên nhân nội bộ để debug.

Khi phân loại lỗi, hỏi ba câu: **body có đọc thành object được không; request value có chuyển thành kiểu Java được không; object có thỏa constraint không?** Trả lời đúng thứ tự sẽ chỉ ra tầng cần sửa.

## Tài liệu chính thức

- Spring Framework 6.2, **WebFlux Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2, **WebFlux `@RequestBody`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework 6.2, **WebFlux `@RequestParam`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework 6.2, **WebFlux Type Conversion**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/typeconversion.html
- Spring Framework 6.2, **WebFlux Data Binding**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/data-binding.html
- Spring Framework 6.2, **WebFlux Error Responses and Problem Details**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2, **WebFlux `ServerWebInputException` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/ServerWebInputException.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html