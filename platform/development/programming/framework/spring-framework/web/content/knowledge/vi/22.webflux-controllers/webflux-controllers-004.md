# Binding, Bean Validation và nhận diện lỗi đầu vào trong Spring WebFlux

## 1. Mục tiêu: từ HTTP input không đáng tin đến lỗi có thể xử lý

Trong một API Spring WebFlux, client có thể gửi dữ liệu qua **JSON body, query string, path variables, headers, form fields hoặc multipart parts**. Trước khi tạo tài nguyên, hệ thống cần phân biệt rõ các bước:

1. **Route matching:** request có tới đúng handler theo path/method/content type hay không.
2. **Binding và conversion:** tham số HTTP dạng chuỗi/bytes được chuyển thành Java object, number, enum, record hay form object.
3. **Bean Validation:** giá trị Java hợp lệ về cấu trúc có thỏa `@NotBlank`, `@Size`, `@Email`, `@Min`, custom constraints và các groups hay không.
4. **Business validation:** tài nguyên có trùng hay không, người dùng có quyền tạo không, trạng thái domain có cho phép thao tác không.
5. **Error representation:** trả đúng HTTP status, error code/field, không rò rỉ rejected input, token hoặc stack trace.
6. **Reactive lifecycle:** validation trên `Mono<T>` có thể thất bại **khi subscription diễn ra**; phải hiểu lỗi lan truyền qua pipeline, không vô tình nuốt lỗi bằng `onErrorResume` sai phạm vi.

Bài này giải thích **Spring Framework 6.2 / Spring Boot 3.5, Java 17+**, module **Controller WebFlux**. API, exceptions và cách bind có thể khác với Servlet MVC. Các ví dụ dùng `org.springframework.web.bind.annotation` cho controller và **`org.springframework.web.reactive`** cho infrastructure, không dùng nhầm `HttpMessageConverter` hoặc exception `MethodArgumentNotValidException` từ MVC.

### Mục tiêu thực hành

- Ràng buộc data qua `@RequestBody`, `@RequestParam`, `@PathVariable`, `@ModelAttribute`, `@RequestPart`.
- Khai báo Jakarta Bean Validation và biết khi nào validation **thật sự chạy**.
- Phân biệt **`WebExchangeBindException`** với **`HandlerMethodValidationException`**, cùng các lỗi decode/conversion không phải Bean Validation.
- Biết lúc nào `BindingResult`/`Errors` có thể được đặt ngay sau model attribute hoặc non-reactive request body, và khi nào nên dùng `Mono<T>.onError*`.
- Định dạng error JSON/ProblemDetail nhất quán, bản địa hóa message, giữ HTTP status đúng.
- Bảo vệ mass assignment, nested validation, validation groups, input size và phản hồi lỗi không tiết lộ bí mật.
- Viết ứng dụng chạy được cùng tests WebTestClient, bao phủ cả valid/invalid/path/form/body.

## 2. Ba lớp thường bị gọi chung là “validation”

### 2.1. HTTP/body decoding: có đọc được dữ liệu hay không?

Request:

```http
POST /api/notes HTTP/1.1
Content-Type: application/json

{"title":
```

Đây là **JSON chưa hoàn chỉnh**. Jackson/HTTP codec không thể deserialize thành DTO; vấn đề xảy ra **trước** việc kiểm tra `@NotBlank` trên trường title.

Những lỗi tương tự:

- JSON syntax hỏng, trường type sai (ví dụ object thay vì string).
- `Content-Type` không phù hợp media type mà endpoint chấp nhận.
- Thiếu body bắt buộc, thiếu request parameter hoặc header.
- Query/path value không convert được sang `int`/`UUID`/`enum`.
- Body hoặc một JSON record vượt giới hạn codec `maxInMemorySize`.
- Form field sai định dạng/số, multipart syntax sai.

Không nên dồn mọi lỗi nói trên thành “Bean Validation failed”. Chúng có nguồn khác nhau và có thể được WebFlux exception infrastructure ánh xạ thành 400, 413, 415... theo tình huống/cấu hình.

### 2.2. Data binding: ghép tên field với property/constructor

Ví dụ form gửi:

```text
term=reactor&page=2
```

Spring dùng `WebDataBinder` và conversion service để tạo/điền một model attribute có các properties `term` và `page`. Nếu page là `"abc"` nhưng target type là `int`, xảy ra **binding/type mismatch** dù chưa xét `@Min(1)`.

`BindingResult` có thể chứa cả **binding errors** và **validation errors**. Những lỗi này khác domain exceptions (ví dụ note title trùng trong database).

### 2.3. Bean Validation: object đúng kiểu nhưng không thỏa constraint

Ví dụ:

```json
{
  "title": " ",
  "contact": {
    "email": "not-an-email"
  }
}
```

JSON hợp cú pháp và Jackson có thể tạo object; nhưng `@NotBlank` và `@Email` có thể tạo violation. Bean Validation dùng các annotations từ **`jakarta.validation`**, implementation phổ biến là **Hibernate Validator** qua `spring-boot-starter-validation`.

> Cần phân biệt **validation contract** và **security authorization**. Một DTO có title đúng độ dài không có nghĩa người dùng được phép tạo resource hay truy cập record của tenant khác.

## 3. Bộ dependencies và namespace cho Spring Boot 3.5

Với project Gradle đã khai báo Spring Boot 3.5 plugin, repositories và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment `build.gradle`**, không phải file build độc lập. `spring-boot-starter-validation` bổ sung Bean Validation provider mà project cần; chỉ có annotations trong code chưa chắc có runtime validator nếu dependency thiếu.

Các imports cốt lõi:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
```

Dùng **`jakarta.validation.*`** trên Boot 3/Framework 6, không copy `javax.validation.*` từ Boot 2. `jakarta.validation.Valid` là cascade marker; nó không phải một constraint trực tiếp như `@NotNull`.

### 3.1. Cách Spring tìm Validator

Khi có Bean Validation provider trên classpath, WebFlux có thể đăng ký global `LocalValidatorFactoryBean`; `WebFluxConfigurer#getValidator()` cho phép cung cấp validator khác. `@InitBinder` cho phép thiết lập validators hay binding options cho controller phạm vi hẹp.

**Không thêm `@EnableWebFlux` chỉ để bật validation trong một ứng dụng Boot.** Nó có thể làm Boot WebFlux auto-configuration không còn hoạt động như mặc định; dùng starter và cấu hình chuẩn của Boot.

## 4. Bảng phân loại dữ liệu đầu vào theo annotation

| Nguồn input | Annotation/method | Cách convert | Lỗi tiêu biểu |
| --- | --- | --- | --- |
| JSON request body | `@RequestBody DTO` hoặc `Mono<DTO>` | `HttpMessageReader` + Jackson | Decode error, `WebExchangeBindException` |
| Query parameter | `@RequestParam` | `ConversionService` | Missing value, type mismatch, method constraint |
| Path segment | `@PathVariable` | `ConversionService` | Missing/unparseable, method constraint |
| HTTP header | `@RequestHeader` | Type conversion | Missing, format error, method constraint |
| Form/query/URI/header thành object | `@ModelAttribute` | `WebDataBinder`, constructor/property binding | BindingResult hoặc `WebExchangeBindException` |
| JSON metadata của multipart | `@RequestPart` | Part reader/codec | Decode failure, `WebExchangeBindException` |
| Functional WebFlux endpoint | `ServerRequest.bodyToMono(...)` | Codecs | Decode failure; Bean Validation không tự luôn áp như controller annotations |
| Response/return value method constraint | Constraint trực tiếp trên return | Method validation | `HandlerMethodValidationException`, thường server error với invalid return |

Với **`@ModelAttribute`**, Spring WebFlux có thể bind từ **form data, query parameters, URI variables và request headers**. Form/query thường được ưu tiên khi trùng tên. Không nên dùng entity persistence có setter cho trường nhạy cảm làm public model attribute vì có nguy cơ **mass assignment**. Thiết kế DTO riêng và hạn chế `allowedFields` nếu dùng property binding.

## 5. Bean Validation annotations thường gặp

| Constraint | Ý nghĩa chính | Lưu ý quan trọng |
| --- | --- | --- |
| `@NotNull` | Giá trị khác null | Empty string vẫn có thể qua |
| `@NotEmpty` | Collection/string/map không null và không rỗng | Chuỗi chỉ whitespace vẫn có thể qua |
| `@NotBlank` | `CharSequence` không null, phải có non-whitespace | Phù hợp title, tên |
| `@Size(min,max)` | Độ dài string/collection/map/array | Không chặn null nếu không kết hợp `@NotNull` |
| `@Min` / `@Max` | Giá trị số theo giới hạn | Thích hợp page, quantity |
| `@Positive` / `@PositiveOrZero` | Số dương / không âm | Không tự ngăn null |
| `@Email` | Hình thức địa chỉ email theo validator | Không chứng minh địa chỉ tồn tại/sở hữu |
| `@Pattern` | Chuỗi phù hợp regex | Không tự chặn null; regex quá phức tạp có thể gây CPU pressure |
| `@Past` / `@Future` | Thời điểm theo constraint | Chú ý clock/time zone |
| `@Valid` | Cascade validation vào object/nested elements | Không tự cấm null |
| `@Validated(Group.class)` | Chọn validation groups | Spring-specific annotation, group semantics phải xác định |

Ví dụ DTO Java 17 dùng **record components**:

```java
record Contact(
        @NotBlank @Email String email) {}

record CreateNote(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}
```

Nếu client gửi:

```json
{"title":"  ","contact":{"email":"bad-mail"}}
```

Jackson tạo được `CreateNote`, nhưng validation có thể báo lỗi title và contact.email. Với `contact=null`, `@NotNull` báo lỗi; `@Valid` **không có nghĩa null tự vi phạm**.

### 5.1. Thứ tự field violations không phải API contract

Bean Validation provider có thể trả nhiều `ConstraintViolation`/`FieldError` theo thứ tự khác nhau giữa phiên bản. Khi test, kiểm tra **set tên field và error code**, không bắt buộc thứ tự lỗi nếu API chưa cam kết sort.

### 5.2. DTO validation và business validation

`@Email` xác minh format tương đối. Nó không tra DNS, gửi xác minh email hay kiểm tra user đang sở hữu địa chỉ. Tương tự `@Size(max=80)` không kiểm tra title có bị trùng, profanity, ký tự cấm riêng domain hoặc quyền tạo tài nguyên.

Đừng thêm thao tác network/DB vào một custom Bean Validation constraint nếu gây blocking trên Reactor Netty event loop. Với ràng buộc cần I/O, thực hiện trong **reactive service layer**, trả `Mono.error(domainException)` khi vi phạm.

## 6. `@Valid @RequestBody Mono<T>` và lỗi reactive

Spring WebFlux cho phép:

```java
@PostMapping("/api/notes")
Mono<Note> create(
        @Valid @RequestBody Mono<CreateNote> body) {
    return body.map(this::save);
}
```

Đây là fragment; `save` và DTO phải có trong controller/service. Framework đọc body qua HTTP codecs, validate decoded object khi publisher được tiêu thụ, rồi mới phát item hợp lệ tới `map`. Nếu validation thất bại, pipeline **phát `onError(WebExchangeBindException)`** và `map(this::save)` không được chạy cho item đó.

**Đặc điểm WebFlux:** controller có thể được gọi và trả publisher trước khi decode/validation hoàn tất. Do đó, đừng nghĩ mọi Bean Validation lỗi xảy ra đồng bộ tại thời điểm vào Java method.

### 6.1. Bắt lỗi cục bộ trong reactive chain

```java
return body
        .map(this::save)
        .onErrorResume(WebExchangeBindException.class, ex ->
            Mono.error(ex));
```

Fragment này chỉ minh họa type-specific handling; ở đây rethrow nên không cần trong ứng dụng thật. Nếu muốn tạo response JSON ngay trong reactive chain, hãy đổi kiểu trả phù hợp (`Mono<ResponseEntity<?>>` hoặc custom envelope), xử lý chính xác `WebExchangeBindException` và không catch mọi `Throwable` rồi biến lỗi database thành 400.

Một ví dụ có ý nghĩa hơn nếu muốn thêm audit metric:

```java
return body
        .map(this::save)
        .doOnError(WebExchangeBindException.class, ex ->
            metrics.incrementInvalidInput());
```

Đây là fragment với `metrics` đã được khai báo. Không log raw rejected body hoặc credentials. Nếu đã có `@RestControllerAdvice` trả JSON chuẩn, để exception đi qua hạ tầng xử lý lỗi thay vì lặp `onErrorResume` ở mọi endpoint.

### 6.2. `BindingResult` và reactive wrapper

Spring docs cho phép:

```java
@PostMapping("/items")
ResponseEntity<?> submit(
        @Valid @RequestBody CreateNote body,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid input");
    }
    return ResponseEntity.ok("ok");
}
```

Đây là **fragment**: khi request body là **object không bọc Mono** và `BindingResult` nằm **ngay sau** argument validated, controller có thể tự xem lỗi. Ngược lại:

```java
// Không dùng BindingResult ngay sau Mono<DTO> như thể DTO
// đã được decode đồng bộ:
void submit(
        @Valid @RequestBody Mono<CreateNote> body,
        BindingResult errors) { /* không phải pattern chuẩn */ }
```

Với `Mono<DTO>`, dùng reactive error operators hoặc global advice. **`BindingResult` không được đặt tùy ý ở cuối danh sách tham số**; phải gắn trực tiếp với đúng argument tương ứng theo support của framework.

## 7. Khi nào WebFlux ném `WebExchangeBindException`?

Đây là lỗi chủ yếu khi **validate/bind một command object đơn lẻ** (ví dụ `@RequestBody`, `@ModelAttribute`, `@RequestPart`) với `@Valid` hoặc `@Validated`, nếu:

- Đối tượng đó không phải container `Map`/`Collection` như các trường hợp docs phân biệt.
- Không khai báo `Errors`/`BindingResult` hợp lệ ngay sau tham số để xử lý cục bộ.
- Phương thức không thuộc tình huống cần **method validation** (xem phần kế).

`WebExchangeBindException` có `BindingResult`:

```java
@ExceptionHandler(WebExchangeBindException.class)
ResponseEntity<?> invalidBody(WebExchangeBindException ex) {
    List<String> fields = ex.getFieldErrors().stream()
            .map(FieldError::getField)
            .distinct()
            .toList();

    return ResponseEntity.badRequest()
            .body(Map.of(
                    "code", "INPUT_VALIDATION",
                    "fields", fields));
}
```

Fragment này cần các imports cho exception, ResponseEntity, List, FieldError. Nó chỉ trả tên field, **không phản chiếu rejected values**. Kiểu và danh sách lỗi thực có thể bao gồm object-level errors (`getGlobalErrors`) chứ không chỉ field-level errors; production nên xây error representation phù hợp.

**Không nhầm `WebExchangeBindException` với MVC `MethodArgumentNotValidException`.** Hai stack có tên exception khác nhau.

## 8. Method validation và `HandlerMethodValidationException`

Spring Framework 6.1+ có **built-in method validation** cho annotated controller methods; Spring 6.2 giữ hai cấp validation.

Ví dụ:

```java
@GetMapping("/page")
Mono<Page> page(
        @RequestParam("number") @Min(1) @Max(20) int number) {
    return Mono.just(new Page(number));
}
```

`@Min` và `@Max` áp **trực tiếp lên method parameter**, nên framework kiểm tra ở mức method. Khi thất bại, exception điển hình là **`HandlerMethodValidationException`**, không phải `WebExchangeBindException`.

### 8.1. Quy tắc phân loại

| Method signature | Cơ chế thường dùng | Lỗi |
| --- | --- | --- |
| `create(@Valid @RequestBody Mono<CreateNote> body)` | Validate object body riêng | `WebExchangeBindException` |
| `form(@Valid @ModelAttribute Form form)` | Binding/validate object riêng | `WebExchangeBindException` |
| `upload(@Valid @RequestPart("meta") Metadata meta)` | Validate part DTO riêng | `WebExchangeBindException` |
| `page(@RequestParam @Min(1) int page)` | **Method validation** | `HandlerMethodValidationException` |
| `create(@NotNull @Valid @RequestBody CreateNote body)` | Có constraint trực tiếp `@NotNull` → method validation | Có thể là `HandlerMethodValidationException` |
| Method có `@NotNull`/`@Positive` trên return value | Method return validation | `HandlerMethodValidationException`; server-side invariant |

**`@Valid` tự nó không phải constraint annotation để kích hoạt method validation**. Thêm `@NotNull` trực tiếp trên tham số có thể chuyển cả method sang nhánh method validation; khi đó framework áp cả direct constraints và nested `@Valid`.

Không viết global advice chỉ bắt một loại lỗi. Chữ ký controller thay đổi có thể khiến nhánh exception đổi dù business DTO như cũ.

### 8.2. Class-level `@Validated` trên controller: trường hợp dễ nhầm

Spring docs khuyến nghị **bỏ `@Validated` ở cấp controller class** nếu muốn sử dụng built-in controller method validation (từ Spring Framework 6.1). Lý do: class-level `@Validated` có thể bật method validation qua **AOP proxy**, với semantics/exception path khác.

Phân biệt:

- **Controller:** validation method trực tiếp có thể được WebFlux áp dụng mà **không** cần `@Validated` trên class.
- **Service bean:** muốn kích hoạt method constraint thông qua Bean Validation AOP, ví dụ `@Service @Validated`, cần hiểu proxy limitations và dependency provider.
- **Parameter DTO:** `@Validated(SomeGroup.class)` trên argument phù hợp để chọn group cho object validation.

Tránh thêm `@Validated` lên mọi controller “cho chắc” vì có thể khiến tests/error mapping thay đổi.

### 8.3. Đọc lỗi method theo parameter

`HandlerMethodValidationException` có:

```java
List<ParameterValidationResult> results =
        ex.getParameterValidationResults();
```

Mỗi `ParameterValidationResult` cho biết method parameter, argument (cẩn thận vì có thể nhạy cảm) và `getResolvableErrors()`. Khi nested object có lỗi, result có thể là `ParameterErrors`, cung cấp field-level information.

Spring còn có **visitor** `HandlerMethodValidationException.Visitor` để xử lý theo annotation types (`requestParam`, `requestHeader`, `modelAttribute`...). Đây là lựa chọn tốt hơn tự đoán index parameter khi API có nhiều tham số.

**Không trả `getArgument()` hoặc raw invalid values vào JSON/log**. Nếu method validation áp lên **return value**, đó thường là bug/invariant của server — xử lý theo server error, không đổ lỗi client.

## 9. Lỗi type conversion, JSON decode và thiếu input

Bean Validation chỉ chạy sau khi binder/decoder tạo giá trị có kiểu phù hợp. So sánh:

```http
GET /api/page?number=abc
```

`number` không convert được thành `int`; đây không phải vi phạm `@Min(1)`. Nó có thể phát lỗi input/binding trước method validator.

```http
GET /api/page?number=0
```

`number=0` convert thành int được, sau đó `@Min(1)` thất bại → **method validation**.

```http
POST /api/notes
Content-Type: application/json

{"title":
```

Đây là JSON parse error, không phải `WebExchangeBindException` do `@NotBlank`.

### 9.1. Những ngoại lệ cần nhận diện

| Nguồn lỗi | Lớp/thực tế WebFlux | HTTP status thường phù hợp |
| --- | --- | --- |
| Validate DTO | `WebExchangeBindException` | 400 |
| Method constraint | `HandlerMethodValidationException` | 400 cho parameters, 500 cho invalid return |
| JSON parse/type conversion trong body | `ServerWebInputException` hoặc codec exceptions được wrap | 400 theo contract |
| Thiếu request param/header/path variable | WebFlux input value exceptions | 400 |
| Content-Type không được hỗ trợ | `UnsupportedMediaTypeStatusException` | 415 |
| Accept không hỗ trợ | `NotAcceptableStatusException` | 406 |
| Codec body/record quá lớn | `DataBufferLimitException` có thể được wrap | Theo policy, thường 413 cho payload quá lớn |
| Resource ID đúng dạng nhưng không tồn tại | Business/domain exception | 404 |
| Domain conflict (trùng định danh) | Domain exception | 409 |
| Chưa xác thực/không đủ quyền | Spring Security | 401/403 |
| Database unavailable/internal bug | Server exception | 5xx |

**Không dựa vào mỗi class name để quyết định status tuyệt đối**. Spring có thể wrap lỗi, error handler mặc định và reverse proxy có thể thay đổi response. Thiết kế tests theo API contract.

## 10. `@ModelAttribute` trong WebFlux: data binding và BindingResult

Ví dụ một form/search request:

```http
GET /api/notes/search?term=spring&page=2
```

Một form DTO:

```java
class SearchForm {
    @NotBlank
    private String term;

    @Min(1)
    private int page = 1;

    public String getTerm() { return term; }
    public void setTerm(String term) { this.term = term; }

    public int getPage() { return page; }
    public void setPage(int page) { this.page = page; }
}
```

Trong annotated WebFlux controller:

```java
@GetMapping("/search")
ResponseEntity<?> search(
        @Valid @ModelAttribute SearchForm form,
        BindingResult binding) {

    if (binding.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "FORM_INVALID"));
    }

    return ResponseEntity.ok(
            Map.of("term", form.getTerm(), "page", form.getPage()));
}
```

Ở đây `BindingResult` nằm ngay sau **non-reactive `@ModelAttribute`**. Controller có thể chọn render lại HTML form với field errors hoặc trả 400 JSON API.

### 10.1. Binding error khác constraint violation

Ví dụ:

- `page=abc` → không convert được sang int, `BindingResult` ghi type mismatch.
- `page=0` → convert thành int thành công nhưng không đạt `@Min(1)`.
- `term=` → chuỗi rỗng, không đạt `@NotBlank`.

Cả ba cùng có thể được hiển thị dưới dạng field errors cho người dùng, nhưng **nguồn gốc và cách sửa khác nhau**. Không lặp raw exception message hoặc raw rejected value trong response.

### 10.2. Bảo vệ mass assignment

`@ModelAttribute` có thể kết hợp constructor binding và property binding. Nếu bạn dùng entity có setter:

```java
class AccountEntity {
    private boolean admin;
    private String displayName;
    // getters/setters...
}
```

Client có thể gửi `admin=true` nếu binder cho phép property binding. **Bean Validation không phải mass-assignment protection**. Giải pháp:

- Dùng **request DTO** chỉ chứa các field được phép.
- Ưu tiên constructor binding immutable DTO khi phù hợp.
- Nếu phải dùng property binding, đặt `WebDataBinder#setAllowedFields(...)` và không nhận entity trực tiếp.
- Không cho client ghi `id`, `tenantId`, `role`, `ownerId`, `isAdmin` khi business không cho phép.
- Kiểm tra quyền theo server identity, không dựa vào trường client tự khai.

### 10.3. `@InitBinder` giới hạn những field được bind

Fragment:

```java
@InitBinder("searchForm")
void initSearchBinder(WebDataBinder binder) {
    binder.setAllowedFields("term", "page");
}
```

Cần import `org.springframework.web.bind.WebDataBinder` và `@InitBinder`. Tên attribute phải khớp (ví dụ dùng `@ModelAttribute("searchForm")`); nếu không chắc convention, khai báo tên tường minh trong controller. Đặt allowed fields là defense-in-depth, vẫn cần DTO chuyên biệt.

## 11. `@RequestPart` và validate metadata của multipart

WebFlux cho phép:

```java
@PostMapping(
    path = "/uploads",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<ResponseEntity<?>> upload(
        @Valid @RequestPart("metadata") Mono<UploadMetadata> metadata,
        @RequestPart("file") FilePart file) {
    // Validate metadata trước khi lưu file.
    return metadata.map(meta ->
            ResponseEntity.accepted().build());
}
```

Đây là **method fragment**, không phải hệ thống upload production. Để bind JSON part thành `UploadMetadata`, client cần gửi part `metadata` với Content-Type phù hợp. `FilePart` cần được consume/transfer/release đúng; đoạn trên cố ý chỉ giải thích signature, **không dùng mẫu đó để lưu file**.

`@Valid`/`@Validated` trên `@RequestPart` DTO có thể dẫn đến `WebExchangeBindException`. Ngoài ra multipart có những lỗi khác: file quá lớn, part thiếu, MIME giả, disk quota, path traversal, malware. Bean Validation trên metadata **không xác minh nội dung binary file**.

Ví dụ record:

```java
record UploadMetadata(
        @NotBlank String description,
        @Min(1) int retentionDays) {}
```

Nếu metadata có `retentionDays=0`, đó là validation lỗi; nếu file là EXE ngụy trang JPG, đó là nội dung file/risk policy phải kiểm tra riêng.

## 12. Validation groups và các bước tạo/cập nhật

Mỗi operation có thể có constraints khác nhau. Ví dụ create yêu cầu password hoặc title bắt buộc, update cho phép thiếu field nhưng giới hạn length nếu có.

Khai báo marker interfaces:

```java
interface OnCreate {}
interface OnUpdate {}

record NoteCommand(
        @NotBlank(groups = OnCreate.class)
        @Size(max = 80, groups = {
                OnCreate.class, OnUpdate.class})
        String title) {}
```

Chọn group tại parameter:

```java
@PostMapping("/commands")
Mono<Void> create(
        @Validated(OnCreate.class)
        @RequestBody Mono<NoteCommand> body) {
    return body.then();
}
```

Và:

```java
@PatchMapping("/commands/{id}")
Mono<Void> update(
        @Validated(OnUpdate.class)
        @RequestBody Mono<NoteCommand> body) {
    return body.then();
}
```

Đây là **method fragments** để giải thích group selection, không phải runnable controller đầy đủ. `@Validated(Group.class)` là annotation Spring hỗ trợ chọn validation hints/groups, trong khi `@Valid` kích hoạt default cascade validation.

Lưu ý:

- Nếu chỉ validate group `OnUpdate`, các constraints thuộc group mặc định **Default** không mặc nhiên được chạy, trừ khi đã chọn/định nghĩa group sequences đúng.
- `@NotBlank` trên create sẽ không áp với update nếu không thuộc OnUpdate; nhưng nếu client **gửi title=""**, chỉ `@Size(max=80)` có thể cho qua. Khi cần ràng buộc “nếu có thì không blank”, thêm constraint/phân biệt null vs empty.
- PATCH có semantics **absent vs null vs blank** khác nhau. DTO thông thường có thể không phân biệt property không được gửi với property JSON null; cần thiết kế patch model phù hợp.
- Không dùng groups để thay authorization hoặc state machine domain.

### 12.1. Nested group conversion

Khi validate nested structures, có thể dùng `@ConvertGroup(from=Default.class,to=OnCreate.class)` trên cascade field để thay group cho nested bean. Đây là Bean Validation capability nâng cao; dùng khi có yêu cầu mô hình rõ và test nested group behavior, đừng thêm theo quán tính.

## 13. Custom Validator: khi annotation đơn lẻ không diễn đạt được

Ví dụ form có `startDate <= endDate` hoặc yêu cầu ít nhất một trong hai fields được điền. Các ràng buộc nhiều trường thường cần **class-level constraint** hoặc Spring `Validator`.

### 13.1. Spring Validator

```java
class SearchFormValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return SearchForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SearchForm form = (SearchForm) target;
        if (form.getTerm() != null
                && form.getTerm().length() > 100) {
            errors.rejectValue("term", "term.tooLong",
                    "Search term is too long");
        }
    }
}
```

Đây là **class fragment** cần `org.springframework.validation.Validator` và `Errors` cùng `SearchForm`. Có thể thêm validator qua `@InitBinder`/`WebDataBinder#addValidators` cho phù hợp. Nếu đã có `@Size(max=100)`, đừng lặp constraint trong hai nơi làm người dùng nhận hai lỗi khác nhau.

### 13.2. Jakarta custom constraint

Một custom constraint thường gồm:

1. Annotation `@Constraint(validatedBy=...)` với `@Target`, `@Retention(RUNTIME)`, `message/groups/payload`.
2. Class `ConstraintValidator<MyConstraint,T>` với `isValid`.
3. Có tests cho null, empty, boundary, nested cascade và validation groups.
4. Không giữ mutable per-request state trong singleton validator.
5. Không truy vấn blocking database hoặc gọi HTTP sync trong `isValid` trên event-loop.

Nếu cần uniqueness async, viết:

```java
return repository.existsByTitle(input.title())
        .flatMap(exists -> exists
                ? Mono.error(new NoteConflictException())
                : repository.save(new NoteEntity(input.title())));
```

Đây là **fragment**, giả định repository reactive và domain exceptions đã khai báo. Nó không giải quyết race condition “check then insert” giữa concurrent requests; cần **DB unique constraint** và map conflict phù hợp, không chỉ pre-check.

## 14. Trả lỗi validation theo contract mà không che giấu lỗi server

Khi DTO bị từ chối, client cần nhận được **status** và một **mã lỗi ổn định**, có thể thêm danh sách field lỗi đã sanitize. Hai lựa chọn hợp lý: JSON envelope do ứng dụng định nghĩa hoặc `ProblemDetail` theo RFC 9457.

```json
{
  "code": "INPUT_VALIDATION",
  "errors": [
    {"field": "title", "message": "must not be blank"}
  ],
  "requestId": "server-generated-correlation"
}
```

Đây là **mẫu contract**, không phải output mặc định của Spring. Khi dùng `WebExchangeBindException`, lấy field names/mã lỗi đã được phép công bố; đừng echo nguyên rejected value vì có thể chứa bí mật. Với `HandlerMethodValidationException`, xác định lỗi thuộc request input hay invariant ở return value trước khi chọn status; không nên chuyển bug/DB outage thành 400.

`ProblemDetail` là model có các trường chuẩn như `type`, `title`, `status`, `detail` và `instance`. Có thể thêm extension field `code` theo policy. Không tạo schema tùy tiện bằng cách ghép raw exception message hoặc stacktrace vào response; lựa chọn contract cần nhất quán qua controller, filter và gateway khi có thể.

Ví dụ **không đúng**:

```java
@ExceptionHandler(Exception.class)
ResponseEntity<String> all(Exception ex) {
    return ResponseEntity.badRequest().body("invalid input");
}
```

Nó biến cả lỗi lập trình, storage/DB hoặc upstream timeout thành HTTP 400. Bài kế tiếp về `@ExceptionHandler`, `@RestControllerAdvice` và `ProblemDetail` là nơi xử lý chi tiết Spring `ErrorResponse`, error handler precedence, security/filter boundaries và response đã commit; bài này chỉ phân biệt **dữ liệu input không hợp lệ** với **sự cố server**.

## 15. Ví dụ runnable: Java 17 + Spring Boot 3.5 WebFlux

Demo bao gồm:

- `POST /api/notes` nhận `@Valid @RequestBody Mono<CreateNote>`; validate nested contact, trả 201 với ID trong URL.
- `GET /api/notes/{id}` trả 200/404 theo ID.
- `GET /api/notes/page?number=...` áp `@Min`/`@Max` **trực tiếp vào parameter**, để minh họa method validation.
- `GET /api/notes/search?term=...&page=...` dùng `@Valid @ModelAttribute` + `BindingResult`, phân biệt form binding errors.
- `@RestControllerAdvice` map hai exception validation thành JSON riêng, map input decode errors thành 400 không lộ raw input.
- Tests dùng `WebTestClient` trên HTTP server thật (RANDOM_PORT).

Đây là ứng dụng **demo in-memory**. Không có Spring Security, persistent DB, conflict handling giữa nodes, rate limits, localization đầy đủ hay audit logs; không dùng trực tiếp trong production.

### 15.1. Cấu trúc dự án

```text
webflux-validation-demo/
├─ build.gradle                         (Spring Initializr + dependencies)
└─ src/
   ├─ main/
   │  ├─ java/demo/input/
   │  │  └─ InputValidationApplication.java
   │  └─ resources/
   │     └─ application.properties
   └─ test/
      └─ java/demo/input/
         └─ InputValidationApplicationTests.java
```

Trong `src/main/resources/application.properties` có thể để:

```properties
spring.application.name=webflux-validation-demo
# Không bật raw request-body/headers logging.
logging.level.org.springframework.web=INFO
```

Không thêm `spring-boot-starter-web` vào build của demo, vì có cả MVC và WebFlux starter có thể khiến Boot 3.x chọn Servlet MVC application type mặc định.

### 15.2. Source Java đầy đủ

Tạo **`src/main/java/demo/input/InputValidationApplication.java`**:

```java
package demo.input;

import java.net.URI;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class InputValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputValidationApplication.class, args);
    }
}

record Contact(
        @NotBlank @Email String email) {}

record CreateNote(
        @NotBlank @Size(min = 3, max = 80) String title,
        @NotNull @Valid Contact contact) {}

record Note(long id, String title, String contactEmail) {}

record PageInfo(int number) {}

record SearchResult(String term, int page) {}

record Violation(String field, String message) {}

record ApiError(String code, List<Violation> errors) {}

class SearchForm {
    @NotBlank
    private String term;

    @Min(1)
    private int page = 1;

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}

@RestController
@RequestMapping("/api/notes")
class NoteController {
    private final AtomicLong sequence = new AtomicLong(100);
    private final ConcurrentMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Note>> create(
            @Valid @RequestBody Mono<CreateNote> input) {

        return input.map(body -> {
            long id = sequence.incrementAndGet();
            Note created = new Note(
                    id, body.title().trim(),
                    body.contact().email());

            notes.put(id, created);

            URI location = URI.create("/api/notes/" + id);
            return ResponseEntity.created(location).body(created);
        });
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Note> find(@PathVariable long id) {
        return Mono.justOrEmpty(notes.get(id))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Note not found")));
    }

    @GetMapping(path = "/page",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<PageInfo> page(
            @RequestParam("number")
            @Min(1) @Max(20) int number) {
        return Mono.just(new PageInfo(number));
    }

    @GetMapping(path = "/search",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> search(
            @Valid @ModelAttribute("searchForm")
            SearchForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(new ApiError(
                        "FORM_BINDING",
                        errors.getFieldErrors().stream()
                            .map(error -> new Violation(
                                error.getField(), "invalid"))
                            .distinct()
                            .toList()));
        }

        return ResponseEntity.ok(new SearchResult(
                form.getTerm(), form.getPage()));
    }
}

@RestControllerAdvice
class InputErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ApiError> objectValidation(
            WebExchangeBindException error) {

        List<Violation> fields =
                error.getFieldErrors().stream()
                    .map(f -> new Violation(
                            f.getField(), "invalid"))
                    .distinct()
                    .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INPUT_VALIDATION", fields));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<ApiError> methodValidation(
            HandlerMethodValidationException error) {

        // Do not expose raw validated argument values.
        // If return-value validation fails, it is a server invariant,
        // not a 400 error attributed to the caller.
        if (error.isForReturnValue()) {
            return ResponseEntity.status(
                    HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError(
                    "SERVER_VALIDATION", List.of()));
        }

        return ResponseEntity.badRequest()
                .body(new ApiError(
                    "METHOD_VALIDATION",
                    List.of(new Violation(
                            "request", "invalid"))));
    }

    @ExceptionHandler(ServerWebInputException.class)
    ResponseEntity<ApiError> inputDecode(
            ServerWebInputException error) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                    "INPUT_DECODE",
                    List.of(new Violation(
                            "request", "malformed input"))));
    }
}
```

Đây là **một file Java 17 hợp lệ về cấu trúc**: chỉ `InputValidationApplication` là public; records, model, controller, advice đều package-private trong `demo.input`. Spring component scan tìm controllers/advice vì cùng package dưới application class.

Cần hiểu:

1. **`create`** nhận `Mono<CreateNote>`, validation diễn ra trong quá trình decode/publisher consume. Nếu title/email sai, body phát validation error và **`notes.put` không được chạy**.
2. `@NotNull @Valid Contact contact` bảo đảm nested contact khác null và cascade xuống email. Nếu email chỉ là whitespace, `@NotBlank` lỗi; nếu format không đúng, `@Email` lỗi.
3. `notes` là in-memory map nên GET ở node khác có thể 404. Không có transaction/DB.
4. `URI.create("/api/notes/"+id)` tạo **relative Location** phù hợp demo tại context root. Với production có context path/gateway version prefix, cần URI builder hoặc public URL strategy đáng tin để sinh Location đúng.
5. **`page`** có direct `@Min/@Max` → built-in method validation. Không gắn class-level `@Validated` lên controller.
6. **`search`** dùng non-reactive `SearchForm` + `BindingResult` ngay sau argument; WebFlux hỗ trợ cách này. Body thành công là object, không bắt buộc trả `Mono<?>` nếu xử lý không blocking.
7. `InputErrorAdvice` dùng **hai handlers tách biệt** cho WebExchangeBindException và HandlerMethodValidationException. Nếu lỗi JSON decode, handler thứ ba trả **INPUT_DECODE** theo contract, không phản chiếu parser exception.
8. `Violation.message` là static text `"invalid"` nên không lộ rejected value, nhưng UI sản phẩm có thể muốn default constraint messages được localize; xem phần 18.
9. `@Min/@Max` trên path/query không là authorization. Nếu app có Security, cần bảo vệ endpoints đúng nghiệp vụ.

### 15.3. Chạy ví dụ và kết quả dự kiến

Khởi chạy:

```bash
./gradlew bootRun
```

**POST hợp lệ:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"WebFlux validation","contact":{"email":"reader@example.org"}}'
```

Nếu đây là request tạo đầu tiên, response dự kiến:

```http
HTTP/1.1 201 Created
Location: /api/notes/101
Content-Type: application/json

{"id":101,"title":"WebFlux validation","contactEmail":"reader@example.org"}
```

ID 101 chỉ là ví dụ khi counter bắt đầu ở 100. Status Location là **relative path**, không được giả định host/proxy/port. GET `/api/notes/101` sẽ trả resource trong cùng instance nếu chưa restart.

**POST có ràng buộc sai:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":" ","contact":{"email":"not-an-email"}}'
```

Kỳ vọng **400 Bad Request**, code `INPUT_VALIDATION` và lỗi field `title`, `contact.email`; thứ tự các field không được cam kết:

```json
{
  "code": "INPUT_VALIDATION",
  "errors": [
    {"field":"title","message":"invalid"},
    {"field":"contact.email","message":"invalid"}
  ]
}
```

**Method constraint thất bại:**

```bash
curl -i 'http://localhost:8080/api/notes/page?number=0'
```

Kỳ vọng 400 và:

```json
{
  "code":"METHOD_VALIDATION",
  "errors":[{"field":"request","message":"invalid"}]
}
```

**Đúng kiểu nhưng lỗi form:**

```bash
curl -i 'http://localhost:8080/api/notes/search?term=&page=0'
```

Kỳ vọng 400 và code `FORM_BINDING`, fields `term` và `page` (thứ tự không cố định).

**Form page không parse được:**

```bash
curl -i 'http://localhost:8080/api/notes/search?term=spring&page=abc'
```

`BindingResult` có thể ghi type mismatch và trả 400 `FORM_BINDING`, thay vì controller bị lỗi không rõ ràng.

**JSON syntax hỏng:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":'
```

Kỳ vọng 400 **INPUT_DECODE** trong cấu hình demo; không kết luận là `@NotBlank` đã chạy.

Các kết quả trên là **hợp đồng dự kiến của mã mẫu đã rà soát**, **không phải kết quả kiểm thử thực tế**.

## 16. Test với WebTestClient trên HTTP server thật

Tạo **`src/test/java/demo/input/InputValidationApplicationTests.java`**:

```java
package demo.input;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InputValidationApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void validBodyCreatesResource() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "title": "Reactive API",
                  "contact": {"email": "a@example.org"}
                }
                """)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.title").isEqualTo("Reactive API")
            .jsonPath("$.contactEmail")
                .isEqualTo("a@example.org");
    }

    @Test
    void blankTitleAndBadEmailFailObjectValidation() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "title": " ",
                  "contact": {"email": "wrong-address"}
                }
                """)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INPUT_VALIDATION")
            .jsonPath("$.errors").isArray();
    }

    @Test
    void missingContactFailsNestedNotNullConstraint() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {"title":"Valid title"}
                """)
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INPUT_VALIDATION");
    }

    @Test
    void directQueryConstraintTriggersMethodValidation() {
        client.get()
            .uri("/api/notes/page?number=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("METHOD_VALIDATION");
    }

    @Test
    void validPageWorks() {
        client.get()
            .uri("/api/notes/page?number=5")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.number").isEqualTo(5);
    }

    @Test
    void formBindingAndValidationErrorsHandledLocally() {
        client.get()
            .uri("/api/notes/search?term=&page=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("FORM_BINDING");
    }

    @Test
    void malformedFormIntegerProducesBindingError() {
        client.get()
            .uri("/api/notes/search?term=reactor&page=abc")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("FORM_BINDING");
    }

    @Test
    void validFormReturnsConvertedValues() {
        client.get()
            .uri("/api/notes/search?term=reactor&page=2")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.term").isEqualTo("reactor")
            .jsonPath("$.page").isEqualTo(2);
    }

    @Test
    void malformedJsonIsDecodeErrorNotBeanValidation() {
        client.post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("INPUT_DECODE");
    }
}
```

Chạy:

```bash
./gradlew test
```

**Chín tests được thiết kế để pass** trên Spring Boot 3.5 WebFlux + Jakarta Validation provider. Đây là kỳ vọng sau khi rà soát API và flow, **chưa phải báo cáo Gradle đã chạy**.

Những điều test đo:

- Codec + Bean Validation cùng tham gia khi xử lý `@RequestBody Mono<CreateNote>`.
- Nested cascade + `@NotNull` không bị bỏ qua.
- Method-level direct `@Min` được phân loại riêng.
- `@ModelAttribute` có `BindingResult` xử lý type mismatch lẫn constraint violation.
- Malformed JSON không bị nhầm thành field validation error.
- HTTP status/body contract quan sát ở embedded Netty server, không chỉ gọi controller trực tiếp.

**Giới hạn:** tests chưa chứng minh DB persistence, Security filters, multipart parser, proxy size caps, default error serialization, race conditions hoặc localization. Khi thêm các lớp này, bổ sung integration tests tương ứng.

## 17. Những trường hợp không nên dùng Bean Validation như công cụ duy nhất

### 17.1. Uniqueness và transactions

Một controller nhận input hợp lệ có thể vẫn thất bại khi title trùng database key. Đừng truy cập DB sync trong `ConstraintValidator` trên event-loop. Dùng reactive repository, unique DB constraint và translate conflict thành HTTP 409, chống race.

### 17.2. Authorization và tenant boundary

`@NotNull Long ownerId` không chứng minh user có quyền đặt ownerId đó. Lấy owner từ authenticated principal/server-side context, validate quyền truy cập bằng security service/DB. Không tin field `role=admin` hoặc `tenantId` do client gửi.

### 17.3. Content security và upload

`@Size(max=100)` trên filename không kiểm tra path traversal, MIME, malware hoặc archive bombs. Với multipart dùng `FilePart`/`PartEvent`, đặt upload byte/disk/part limits, file format validation và quarantine/AV nếu nghiệp vụ cần.

### 17.4. Rate limits và resource exhaustion

Một JSON array gồm hàng triệu phần tử có thể gây áp lực decoder và service dù mỗi item qua `@Valid`. Hãy dùng `spring.http.codecs.max-in-memory-size` đúng Boot 3.5, body size caps, pagination, query complexity/timeouts và rate limits. Bean Validation không phải hệ thống chống DDoS.

### 17.5. Reactive cancellation

Nếu client ngắt kết nối khi validation/DB operation còn chạy, publisher có thể nhận cancel. Giải phóng resources và kiểm tra transaction cancellation semantics; `@Valid` không tự xử lý resource cleanup, rollback hoặc idempotency.

## 18. Bản địa hóa và error codes

Default Bean Validation messages có thể được Spring/Bean Validation interpolator giải quyết qua `MessageSource` và locale. Bạn có thể dùng:

```properties
# src/main/resources/messages_vi.properties
NotBlank.createNote.title=Tiêu đề không được để trống
Size.createNote.title=Tiêu đề phải có độ dài hợp lệ
```

Đây là **ví dụ cơ chế message bundles**, không khẳng định các message codes chính xác cho mọi binding object naming scheme; code thực tế cần xem `FieldError#getCodes()` để chọn keys và tests localization.

Một annotation có message template:

```java
@NotBlank(message = "{note.title.required}")
String title
```

có thể được resolve bằng message source/validator theo cấu hình. Thông báo locale cần tránh lộ rejected value hoặc template injection. Với API công khai, stable **machine-readable error code** nên độc lập ngôn ngữ, còn human message phụ thuộc locale/`Accept-Language`.

### 18.1. Có nên trả chính xác defaultMessage?

Có thể, nếu policy xác nhận message an toàn, đã escape/encode đúng và không chứa dữ liệu nhạy cảm. Với Bean Validation standard messages (`must not be blank`, `size must be between...`) thường hữu ích. Nhưng một custom validator có thể tạo message chứa raw user input; **không tự log/return mọi message một cách mù quáng**. Ví dụ runnable trả `"invalid"` cố ý để giữ ranh giới bảo mật.

## 19. ProblemDetail / RFC 9457 trong WebFlux

Spring Framework 6.2 hỗ trợ `ProblemDetail` và `ErrorResponse` để thể hiện các HTTP errors dưới dạng `application/problem+json`. Khi API phức tạp, bạn có thể tạo lỗi:

```java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
problem.setTitle("Input validation failed");
problem.setDetail("One or more fields are invalid");
problem.setProperty("code", "INPUT_VALIDATION");
```

Đây là **fragment** cần import `org.springframework.http.ProblemDetail`/`HttpStatus`; dùng trong `@ExceptionHandler` và thêm fields đã kiểm tra khi cần.

Một body kiểu:

```json
{
  "type": "about:blank",
  "title": "Input validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "code": "INPUT_VALIDATION"
}
```

là representation minh họa, **không tự mặc định mọi WebFlux app trả y như vậy**. Chọn **một** error schema nhất quán cho cùng API version hoặc có migration plan, thay vì endpoint A trả `{"code":...}` và endpoint B trả HTML/stack trace tùy lỗi.

## 20. Khác biệt với Spring MVC Servlet

| Chủ đề | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| HTTP body converter | `HttpMessageConverter` | `HttpMessageReader`/`HttpMessageWriter` |
| Input object annotation | `@RequestBody`, `@ModelAttribute` | Có cả hai, hỗ trợ reactive wrappers |
| Bean validation namespace trên Spring 6 | `jakarta.validation` | `jakarta.validation` |
| Object validation exception | `MethodArgumentNotValidException` | **`WebExchangeBindException`** |
| Method validation exception | `HandlerMethodValidationException` | **`HandlerMethodValidationException`** |
| Bind form errors | `BindingResult` sau non-reactive argument | Tương tự; có hỗ trợ reactive model attributes |
| Mono body | MVC có hỗ trợ vài reactive types nhưng Servlet writer khác | Native `Mono<DTO>` và `Flux<DTO>` pipeline |
| Error infrastructure | MVC `HandlerExceptionResolver`, advice | WebFlux reactive exception infrastructure/advice |
| Server threads | Servlet worker threads | Reactor Netty event loops/non-blocking I/O |
| Blocking DB | Thường phù hợp worker thread tùy tải | Tránh blocking trên event loop; R2DBC hoặc boundedElastic |

**Không sử dụng exception class của MVC để bắt lỗi WebFlux body binding**, và không mặc định một `@ControllerAdvice` viết cho Servlet MVC có thể dùng nguyên trong reactive app.

Spring Framework 6.1/6.2 tích hợp method validation cho controllers; nếu nâng từ Spring 5.x/Boot 2.x, cả exception types và class-level `@Validated` semantics có thể khác. Đọc migration guide và kiểm thử controller signatures.

## 21. Troubleshooting: biểu hiện → nguyên nhân → cách sửa

| Biểu hiện | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `@Valid` không chạy | Thiếu Hibernate Validator/provider trên classpath | Thêm `spring-boot-starter-validation`, test invalid DTO |
| `@Email` cho phép null | Constraint không tương đương required | Kết hợp `@NotBlank` hoặc `@NotNull` |
| Nested DTO không validate | Thiếu `@Valid` trên nested field | Thêm cascade annotation và test nested |
| POST JSON hỏng mà handler WebExchangeBindException không chạy | Lỗi decode xảy ra trước Bean Validation | Xử lý `ServerWebInputException`/codec error riêng |
| Query number=0 vào method trả 400 nhưng handler object validation không bắt | Direct `@Min` kích hoạt method validation | Xử lý `HandlerMethodValidationException` |
| Controller có class `@Validated` và method validation khác docs | AOP proxy path | Bỏ class-level `@Validated` để dùng built-in WebFlux validation |
| `BindingResult` không nhận lỗi với `Mono<DTO>` | Không đúng cách dùng reactive wrapper | Dùng `onError*`/advice, hoặc nonreactive DTO + adjacent result |
| Form có page=abc nhưng API trả 500 | Type mismatch không được xử lý như client input | Dùng BindingResult/error mapping đúng |
| Spring tự bind isAdmin=true | Mass assignment vào entity | Dùng DTO + allowedFields/constructor binding |
| Title unique constraint chỉ validate bằng pre-check | Race condition giữa requests | Database unique constraint, map 409 |
| Error body lộ mật khẩu/rejectedValue | Log/return raw BindingResult | Chỉ chọn field/code/messages an toàn |
| Validation runs nhưng service vẫn save record invalid | Validation annotations trên wrong parameter/group | Test exact signature, group and provider |
| One field reports nhiều errors theo thứ tự thay đổi | Validator/provider order không cam kết | Assert tập field/codes, sort nếu API đòi |
| `@Size` cho phép null | `@Size` không phải required | Thêm `@NotNull`/`@NotBlank` |
| Method validation báo 500 cho return value | Vi phạm server invariant | Sửa code/business, không trả 400 cho caller |
| 400 default response khác schema API | Chưa có centralized error handling | `@RestControllerAdvice`/ProblemDetail |
| Upstream HTTP call từ validator làm chậm app | Blocking trên event loop | Chuyển business rule vào reactive service |
| Validation chỉ áp JSON body, bỏ qua multipart metadata | Thiếu `@Valid @RequestPart` | Validate metadata, giới hạn file riêng |
| Unit test pass nhưng WebTestClient fail | Codec/binding khác khi qua HTTP | RANDOM_PORT integration tests |
| Giới hạn size JSON không như tưởng | Boot codec/config/total request limits khác nhau | Dùng đúng property + gateway caps và test |

## 22. Checklist trước khi công bố WebFlux API

- [ ] Tách request DTO khỏi entities; chỉ bind fields được phép.
- [ ] Dùng `jakarta.validation.*` và có implementation thực tế trong build.
- [ ] Không gắn `@Validated` lên controller class khi muốn built-in method validation.
- [ ] `@Valid` cascade nested DTOs; thêm `@NotNull` khi nested object bắt buộc.
- [ ] Phân biệt missing/invalid type/decode với Bean Validation violations.
- [ ] Cả `WebExchangeBindException` lẫn `HandlerMethodValidationException` đều có policy.
- [ ] Return-value validation error được xử lý như server invariant.
- [ ] Method parameter constraints `@Min/@Max` được test qua WebFlux handler pipeline.
- [ ] Form binding `BindingResult` luôn ngay sau non-reactive `@ModelAttribute`/body khi dùng.
- [ ] Reactive `Mono<DTO>` giữ error signaling; không “subscribe rồi bỏ qua lỗi”.
- [ ] Validation group create/update/patch rõ và có tests cho absent/null/empty.
- [ ] Validation liên quan DB/business chạy trong reactive service, không block event-loop.
- [ ] Response errors có code và status nhất quán, không lộ rejected values/stack traces.
- [ ] Content-type/Accept/malformed JSON/missing param có error contract riêng.
- [ ] Upload metadata validation không thay file content scanning/size/quota.
- [ ] Không coi CORS hay Bean Validation là authentication/authorization.
- [ ] Limit codec/max request/time/rate/multipart được cấu hình ở nhiều tầng.
- [ ] WebTestClient integration tests test cả invalid/success, nested body, form conversion và method validation.
- [ ] Có observability theo route template/error code, không log PII/token.
- [ ] Dependency/provider/Spring Framework version và Bean Validation groups đã được kiểm tra khi nâng cấp.

## 23. Bài tập tự đánh giá

1. Trong JSON `{"title":"  "}`, lỗi là JSON syntax, binding conversion hay Bean Validation? Phụ thuộc những annotations nào?
2. Vì sao `@Email` chưa chứng minh email tồn tại, và vì sao phải thêm `@NotBlank` nếu bắt buộc có giá trị?
3. Khi client gửi `page=abc` cho `int page`, `@Min` đã chạy chưa? Phân biệt conversion với method validation.
4. So sánh `@Valid @RequestBody Mono<CreateNote>` và `@Valid @RequestBody CreateNote, BindingResult`.
5. Vì sao `BindingResult` phải đứng ngay sau model attribute? Có nên thêm sau `Mono<DTO>` không?
6. Một method có `@Valid` trên DTO, sau đó thêm `@NotNull` lên cùng parameter. Kiểu validation và exception có thể đổi thế nào?
7. Vì sao global advice cho WebFlux nên xử lý cả `WebExchangeBindException` và `HandlerMethodValidationException`?
8. Class-level `@Validated` trên WebFlux controller ảnh hưởng controller method validation Spring 6.2 ra sao?
9. `@Valid` trên nested field null có tự thất bại không? Phải thêm gì?
10. Với record DTO title và contact.email, thiết kế tests assert hai field violations mà không phụ thuộc order.
11. Vì sao `@ModelAttribute` bind một entity có `isAdmin` setter có thể nguy hiểm? Dùng DTO/allowedFields thế nào?
12. Thiết kế validation groups OnCreate/OnUpdate: update cho phép omitted title nhưng không chấp nhận blank string phải làm sao?
13. Một custom ConstraintValidator gọi blocking JDBC; WebFlux event-loop gặp nguy cơ gì và chuyển sang reactive service ra sao?
14. Nếu URL path có ID không tồn tại, nên trả 400 hay 404? Nếu path ID có định dạng sai thì sao?
15. Nếu title trùng DB, phải dùng 409 và DB unique constraint vì sao, thay vì chỉ `@Pattern`?
16. Một client POST multipart kèm metadata JSON hợp lệ nhưng file chứa malware. Bean Validation đã đủ chưa?
17. Error handler trả `ex.getRejectedValue()` trong response JSON: rủi ro bảo mật gì?
18. Dùng `ProblemDetail` tạo một 400 error với field code ổn định và localized detail.
19. Khi ứng dụng chạy Boot 3.5 nhưng thiếu `spring-boot-starter-validation`, vì sao annotations có thể không enforce lúc runtime?
20. Khi đưa một `Flux<DTO>` vào controller, validation per-item và stream errors khác với một `Mono<DTO>` ở những điểm nào?
21. Tạo WebTestClient case JSON syntax sai và case JSON đúng format nhưng title blank; so sánh error codes.
22. Khi response streaming đã trả status 200 và gửi bytes, một validation/business error đến sau có còn chuyển thành HTTP 400 không?
23. Dữ liệu do user gửi chứa secret trong message; thiết kế log error/field violations mà không để lộ secret.
24. Với API trả về annotated method output constraint, vì sao invalid return value là lỗi server chứ không nên trả 400?
25. Nêu lộ trình migration Boot 2/Framework 5 sang Boot 3.5: javax→jakarta, runtime provider, method validation, WebFlux exception mapping và tests.

## 24. Tài liệu chính thức

- [Spring Framework 6.2 — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): phân biệt object validation với method validation và hai exception types.
- [Spring Framework 6.2 — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): `@Valid`, `Mono<DTO>`, `WebExchangeBindException`, `Errors`.
- [Spring Framework 6.2 — @ModelAttribute WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html): binding, `BindingResult`, security.
- [Spring Framework 6.2 — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `@RequestPart` validation và FilePart.
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, validation error messages.
- [Spring Framework 6.2 — WebFlux Config Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): global `Validator`/`WebFluxConfigurer`/`@InitBinder`.
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html): validation starter/provider, service method validation, MessageSource.
- [Spring Framework 6.2 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html): parameter results/visitor/return value errors.
- [Spring Framework 6.2 — WebExchangeBindException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html): BindingResult/field errors.
- [Spring Framework 6.2 — ParameterValidationResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html): field and method parameter errors.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): test WebFlux HTTP binding, validation status and bodies.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, nested validation, groups, Bean Validation semantics.
