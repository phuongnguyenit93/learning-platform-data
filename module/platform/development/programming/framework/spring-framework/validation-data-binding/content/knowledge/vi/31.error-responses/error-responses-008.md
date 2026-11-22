# ParameterValidationResult và nhóm lỗi theo tham số trong Spring Framework

Trong Spring Framework 6.1+, khi **method validation** phát hiện nhiều ràng buộc không hợp lệ trên tham số của một phương thức, Spring không bắt buộc biến mọi vi phạm thành một chuỗi thông báo duy nhất. Thay vào đó, Spring có mô hình kết quả **`MethodValidationResult`** gồm các **`ParameterValidationResult`**: mỗi kết quả cho biết một tham số/giá trị được kiểm tra và những lỗi liên quan đến nó.

Ví dụ một HTTP request vào controller:

~~~http
GET /api/quotes/0?limit=9 HTTP/1.1
Host: localhost:8080
X-Channel: other
~~~

với handler:

~~~java
@GetMapping("/api/quotes/{id}")
public QuoteView get(
        @PathVariable("id") @Min(1) long id,
        @RequestParam("limit") @Min(1) @Max(5) int limit,
        @RequestHeader("X-Channel")
        @Pattern(regexp = "web|mobile") String channel) {
    return new QuoteView(id, limit, channel);
}
~~~

Cả ba đối số đều **chuyển thành kiểu Java thành công** nhưng vi phạm constraint: `id=0` sai `@Min(1)`, `limit=9` sai `@Max(5)`, `channel="other"` sai `@Pattern`. Trong Spring MVC 6.1+ có built-in handler method validation, trường hợp này thường tạo **một `HandlerMethodValidationException` mang ba `ParameterValidationResult`**, mỗi nhóm mô tả tham số tương ứng.

**Không nhầm ba nhóm lỗi với ba ràng buộc trong mọi tình huống.** Một tham số DTO `@Valid` có thể chứa nhiều field errors mà vẫn chỉ chiếm **một nhóm**; khi tham số là collection có các phần tử sai, lại có thể có **nhiều nhóm cho các phần tử khác nhau của cùng tham số**.

Bài này thuộc nhóm **Phản hồi lỗi** trong module Spring Framework — validation/data binding. Trọng tâm: cách đọc `ParameterValidationResult`, phân biệt lỗi trực tiếp và lỗi DTO lồng nhau qua `ParameterErrors`, số lượng nhóm/vi phạm, `List`/`Map`, lỗi cross-parameter, giá trị trả về, i18n và thiết kế HTTP error response. Phần thực hành dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x và Servlet Spring MVC**.

## 1. Mô hình lớp và thuật ngữ quan trọng

| API | Vai trò |
|---|---|
| `org.springframework.validation.method.MethodValidationResult` | Giao diện chứa kết quả validation cấp phương thức, cả danh sách nhóm và thông tin method/target |
| `org.springframework.validation.method.ParameterValidationResult` | Một nhóm lỗi liên quan một method parameter hoặc phần tử của container được validate |
| `org.springframework.validation.method.ParameterErrors` | Subclass của `ParameterValidationResult`, đồng thời implements `Errors` để biểu diễn các field/object errors của bean lồng nhau |
| `org.springframework.web.method.annotation.HandlerMethodValidationException` | Exception của built-in handler method validation ở Spring MVC/WebFlux, implements `MethodValidationResult` và mang HTTP status |
| `org.springframework.validation.method.MethodValidationException` | Exception chứa kết quả đã được adapt trong một số cấu hình method validation ngoài MVC, chẳng hạn service AOP |
| `org.springframework.context.MessageSourceResolvable` | Biểu diễn một lỗi có các mã thông báo, arguments và default message có thể dịch qua `MessageSource` |
| `org.springframework.core.MethodParameter` | Metadata của Java method parameter hoặc return-value descriptor |
| `org.springframework.validation.FieldError` / `ObjectError` | Các lỗi theo trường và toàn object, có thể truy cập qua `ParameterErrors` |

Mối quan hệ:

~~~text
MethodValidationResult
|
+-- target, method, isForReturnValue
+-- getParameterValidationResults()
|     |
|     +-- ParameterValidationResult
|     |      +-- MethodParameter
|     |      +-- argument
|     |      +-- List<MessageSourceResolvable>
|     |      +-- container / index / key nếu có
|     |
|     +-- ParameterErrors extends ParameterValidationResult
|            +-- implements Errors
|            +-- getFieldErrors()
|            +-- getGlobalErrors()
|
+-- getCrossParameterValidationResults()
      +-- lỗi của một constraint liên quan nhiều tham số

HandlerMethodValidationException
    implements MethodValidationResult
    +-- HTTP status, ErrorResponse/ProblemDetail
~~~

`ParameterValidationResult` **không phải** một `ConstraintViolation<?>` thô của Jakarta Validation. Spring đã **adapt** thông tin của provider sang cấu trúc dễ tích hợp với Spring `MessageSource` và error handling. Vì vậy đừng cast tùy tiện đối tượng trong `getResolvableErrors()` thành `ConstraintViolation<?>`.

### Ba khái niệm đếm khác nhau

1. **Số nhóm**: `ex.getParameterValidationResults().size()`. Mỗi phần tử là một `ParameterValidationResult`.
2. **Số lỗi trong nhóm**: `result.getResolvableErrors().size()`. Một tham số có thể đóng góp nhiều lỗi.
3. **Số vị trí tham số Java khác nhau**: số `getMethodParameter().getParameterIndex()` khác nhau trong danh sách; có thể **nhỏ hơn số nhóm** khi một tham số chứa nhiều phần tử `List`/`Map` sai.

Ngoài ra, `getCrossParameterValidationResults()` lưu các lỗi **cross-parameter riêng**, không được tự cộng vào “số nhóm theo tham số” nếu response field chỉ có ý nghĩa là nhóm.

## 2. Phân biệt method validation với validation từng argument

Spring MVC hỗ trợ hai đường thường gặp:

### 2.1. Validation của một DTO đơn lẻ

~~~java
@PostMapping("/accounts")
public AccountReply create(
        @Valid @RequestBody AccountRequest request) {
    return service.create(request);
}
~~~

Khi chỉ có `@Valid` trên object body và **không có constraint trực tiếp khác yêu cầu method validation**, lỗi DTO thường được ném dưới dạng **`MethodArgumentNotValidException`**. Exception này mang một `BindingResult` cho request DTO, có `getFieldErrors()` và `getGlobalErrors()`.

`@Valid` tự nó là marker yêu cầu **cascade validation**; nó không phải direct constraint annotation như `@Min` hay `@NotBlank`.

### 2.2. Validation ở cấp method

~~~java
@PostMapping("/accounts")
public AccountReply create(
        @Valid @RequestBody AccountRequest request,
        @RequestParam("source")
        @Pattern(regexp = "web|mobile") String source) {
    return service.create(request);
}
~~~

`@Pattern` trên `source` là **constraint trực tiếp trên method parameter**. Spring MVC 6.1+ có thể áp dụng **built-in method validation** cho handler, bao quát direct constraint và cascade trong `@Valid AccountRequest`. Khi sai, `HandlerMethodValidationException` mang các `ParameterValidationResult`, trong đó DTO với lỗi lồng nhau có thể được biểu diễn bằng `ParameterErrors`.

**Khuyến nghị:** nếu muốn dùng MVC built-in method validation từ Spring 6.1+, **không đặt `@Validated` cấp class trên controller**. Annotation đó có thể chuyển method validation sang **Spring AOP proxy**, dẫn đến kiểu exception và behavior khác. Dùng Spring `@Validated` ở cấp argument khi cần validation groups là một vấn đề khác.

### 2.3. Lỗi chuyển kiểu trước validation

~~~text
GET /api/quotes/not-a-number?limit=2
~~~

`@PathVariable long id` không thể nhận chuỗi `not-a-number`. Framework gặp lỗi ở **argument resolution/type conversion**, thường là `MethodArgumentTypeMismatchException`, trước khi có `long id` để chạy `@Min(1)`. Không mong đợi một `ParameterValidationResult` với `Min` cho input này.

Tương tự, JSON body sai cú pháp có thể phát `HttpMessageNotReadableException`. Phân biệt **request không đọc được** với **request đọc được nhưng vi phạm ràng buộc**.

| Trường hợp | Đường xử lý thường gặp | Lỗi có thể thấy |
|---|---|---|
| Chỉ `@Valid @RequestBody Dto` bị sai field | Argument-level validation | `MethodArgumentNotValidException` |
| `@Min @RequestParam int limit`, gửi số dưới min | Built-in MVC method validation | `HandlerMethodValidationException` |
| `@Pattern @RequestHeader String channel`, chuỗi sai pattern | Built-in MVC method validation | `HandlerMethodValidationException` |
| `@NotNull` trên method return value nhưng trả `null` | Built-in return-value validation | `HandlerMethodValidationException`, HTTP 500 |
| `@RequestParam int limit`, gửi `xyz` | Type conversion | `MethodArgumentTypeMismatchException` |
| JSON không parse được | HTTP body decoding | `HttpMessageNotReadableException` |
| Bean service `@Validated` đi qua AOP | Service method validation | Thường `ConstraintViolationException` mặc định |
| AOP bật `adaptConstraintViolations` | Adapted service method validation | `MethodValidationException` có `MethodValidationResult` |

Bảng này mô tả cấu hình điển hình. Custom `@ControllerAdvice`, global validator, proxy và phiên bản framework có thể thay đổi behavior; khi debug, xác định **đường tạo lỗi thực tế**.

## 3. Đọc `MethodValidationResult` và phiên bản API

`MethodValidationResult` cung cấp:

~~~java
Object getTarget();
Method getMethod();
boolean isForReturnValue();
List<ParameterValidationResult> getParameterValidationResults();
List<MessageSourceResolvable>
    getCrossParameterValidationResults();
~~~

Đây là chữ ký rút gọn theo Spring 6.2 để mô tả API, không phải class cần copy vào project. API còn có các method tiện ích:

- `getValueResults()` — nhóm có lỗi **trực tiếp trên giá trị parameter**.
- `getBeanResults()` — nhóm kiểu **`ParameterErrors`**, có nested bean field/object errors.
- `getAllErrors()` — tập hợp các lỗi dưới dạng `MessageSourceResolvable` theo contract của phiên bản.
- `hasErrors()` — cho biết kết quả có lỗi.
- `getParameterValidationResults()` — tập hợp value results và bean results theo từng nhóm.
- `getCrossParameterValidationResults()` — kết quả cross-parameter riêng.

**Mốc phiên bản quan trọng:** Trong **Spring Framework 6.2**, `getParameterValidationResults()` là tên API nên dùng. `getAllValidationResults()` có thể còn tồn tại nhưng **được đánh dấu deprecated, forRemoval**; tránh dùng nó cho code mới. Khi đọc code chạy trên Spring 6.1, cần đối chiếu Javadoc phiên bản vì API đã phát triển giữa 6.1 và 6.2.

Trong Spring MVC:

~~~java
HandlerMethodValidationException ex = /* đã bắt được */;

boolean returnFailure = ex.isForReturnValue();
int groupCount = ex.getParameterValidationResults().size();
int crossParameterErrorCount =
    ex.getCrossParameterValidationResults().size();
int httpStatus = ex.getStatusCode().value();
~~~

Đây là **snippet bên trong exception handler**, không phải một Java method độc lập. `ex.getStatusCode()`:

- **400 Bad Request** cho **input parameter** validation failure.
- **500 Internal Server Error** cho **return-value** validation failure.

Lý do: input sai là lỗi client, còn return value không đáp ứng cam kết là lỗi server. Khi thiết kế phản hồi, không “sửa” mọi `HandlerMethodValidationException` thành HTTP 400.

## 4. Các API của `ParameterValidationResult`

Class này cung cấp các thông tin chính:

| API | Nội dung | Cần chú ý |
|---|---|---|
| `getMethodParameter()` | `MethodParameter` đại diện tham số/method return descriptor | Có thể xem index, kiểu Java và annotations |
| `getArgument()` | Giá trị Java được kiểm tra | **Không trả thẳng** ra API vì có thể chứa dữ liệu nhạy cảm |
| `getResolvableErrors()` | Danh sách `MessageSourceResolvable` của nhóm | Một nhóm có thể chứa nhiều error entries |
| `getContainer()` | Container bao phần tử được kiểm tra, nếu có | Không serialize vào JSON công khai |
| `getContainerIndex()` | Vị trí phần tử trong `List`/array nếu có | Có thể là `null` với parameter thường |
| `getContainerKey()` | Key của phần tử trong `Map` nếu có | Có thể chứa input riêng tư; phải lọc trước khi phản hồi |
| `unwrap(...)` | Truy cập thông tin underlying validation khi thích hợp | Chỉ dùng khi thực sự cần, phụ thuộc provider/contract |

Ví dụ đọc thông tin nhóm:

~~~java
for (ParameterValidationResult result
        : ex.getParameterValidationResults()) {

    MethodParameter methodParameter =
        result.getMethodParameter();

    int javaParameterIndex =
        methodParameter.getParameterIndex();

    int errorsInGroup =
        result.getResolvableErrors().size();

    Integer elementIndex =
        result.getContainerIndex();

    Object elementKey =
        result.getContainerKey();
}
~~~

Đây là đoạn **minh họa trong nơi có `ex`**, cần imports `ParameterValidationResult` và `MethodParameter`. Không log `result.getArgument()` và `result.getContainer()` chỉ để debug; chúng có thể chứa request DTO, token hoặc object graph lớn.

### `MethodParameter` và tên tham số

`methodParameter.getParameterIndex()` cho index của Java method parameter; index thường bắt đầu từ **0**, theo thứ tự trong chữ ký. Với return-value descriptor, index có thể biểu thị return slot (quy ước Spring MethodParameter dùng **-1**). Đây là **metadata Java**, không phải index tự động trong mảng JSON của frontend.

`getParameterName()` không luôn luôn có giá trị nếu bytecode không giữ thông tin tham số hoặc chưa có `ParameterNameDiscoverer` phù hợp. Với request-facing API, nên dùng tên khai báo tường minh trong annotation:

~~~java
@RequestParam("limit")
@PathVariable("id")
@RequestHeader("X-Channel")
~~~

và mapping được kiểm soát, thay vì phụ thuộc hoàn toàn vào tên biến Java do compiler giữ.

### Annotation xác định nguồn input

Có thể phân loại method parameter qua:

~~~java
if (methodParameter.hasParameterAnnotation(
        RequestParam.class)) {
    // QUERY or form parameter tùy contract
}
~~~

Tương tự `PathVariable.class`, `RequestHeader.class`, `RequestBody.class`, `ModelAttribute.class`. Mỗi loại nguồn có cách giải thích cho client khác nhau; không gắn nhãn mọi thứ là `fieldErrors` của một body DTO.

## 5. Đếm đúng: nhóm tham số khác với số vi phạm

Xét ba chữ ký sau:

### Trường hợp A — ba tham số độc lập, mỗi tham số sai một ràng buộc

~~~java
@GetMapping("/a/{id}")
public String a(
        @PathVariable @Min(1) long id,
        @RequestParam @Max(5) int limit,
        @RequestHeader("X-Channel")
        @Pattern(regexp = "web|mobile") String channel) {
    return "ok";
}
~~~

Nếu cả ba sai, thường có **ba `ParameterValidationResult`**, mỗi nhóm một `MessageSourceResolvable`. Tổng nhóm = 3, tổng lỗi trực tiếp = 3, số Java parameter index khác nhau = 3.

### Trường hợp B — một tham số có hai constraint cùng sai

~~~java
@GetMapping("/b")
public String b(
        @RequestParam("code")
        @NotBlank
        @Size(min = 3) String code) {
    return "ok";
}
~~~

Với `code=""`, `@NotBlank` và `@Size(min=3)` đều có thể phát violation. Kết quả thường là **một nhóm** cho `code` nhưng **hai lỗi trong `getResolvableErrors()`**. Không giả định provider bảo đảm thứ tự các lỗi là NotBlank trước Size.

### Trường hợp C — một DTO có nhiều field sai

~~~java
public record CreateQuote(
    @NotBlank String code,
    @Min(1) int quantity) {
}
~~~

Nếu `code=""` và `quantity=0`, một `@Valid CreateQuote` trong một handler cần method validation có thể tạo **một `ParameterErrors`** chứa **hai `FieldError`**. `getParameterValidationResults().size()` tăng một nhóm, trong khi số field errors của DTO bằng hai.

| Tình huống | Nhóm `ParameterValidationResult` | Lỗi trong nhóm | Ghi chú |
|---|---:|---:|---|
| Ba parameters, mỗi parameter một lỗi | 3 | 1+1+1 | Các index 0/1/2 khác nhau |
| Một parameter vi phạm 2 annotations | 1 | 2 | Một argument, hai messages |
| Một DTO có 2 field errors | 1 `ParameterErrors` | 2 | Nested field errors, không phải 2 parameters |
| Một container có 2 phần tử sai | Có thể 2 | Tùy mỗi phần tử | Cùng method index, khác container index/key |
| Một cross-parameter constraint sai | Có thể 0 parameter groups | Lỗi trong danh sách cross-parameter | Không tự gắn vào một parameter |
| Return value sai | Có nhóm return value | 1 hoặc nhiều lỗi | HTTP 500, không phải input 400 |

**Không đặt tên field JSON là `violationCount` nếu bạn đang truyền `getParameterValidationResults().size()`.** Tên đúng hơn là `affectedGroups` hoặc `parameterGroups`. Nếu cần tổng lỗi, tính riêng theo từng nhóm và cộng cả cross-parameter errors theo chính sách rõ ràng.

## 6. `ParameterErrors`: lỗi lồng trong object/DTO

`ParameterErrors` thuộc:

~~~java
org.springframework.validation.method.ParameterErrors
~~~

Class này **extends `ParameterValidationResult`** và **implements `org.springframework.validation.Errors`**. Khi một method argument là bean được kiểm tra cascade bằng `@Valid`, Spring có thể biểu diễn các lỗi lồng nhau qua `ParameterErrors`.

Ví dụ:

~~~java
public record QuoteRequest(
    @NotBlank String code,
    @Min(1) int quantity) {
}

@PostMapping("/mixed")
public QuoteView mixed(
        @Valid @RequestBody QuoteRequest request,
        @RequestParam("source")
        @Pattern(regexp = "web|mobile") String source) {
    // ...
}
~~~

`@Pattern` là direct method constraint, còn `@Valid` cho phép kiểm tra nested properties của `request`. Nếu body có `{"code":"","quantity":0}` và source là `other`, có thể có:

~~~text
HandlerMethodValidationException
|
+-- ParameterErrors: Java parameter #0 (QuoteRequest)
|      +-- FieldError("code", "NotBlank")
|      +-- FieldError("quantity", "Min")
|
+-- ParameterValidationResult: Java parameter #1 (source)
       +-- MessageSourceResolvable("Pattern")
~~~

Đó là **hai nhóm**, nhưng **ba lỗi**. Không tạo một parameter group riêng cho từng field của DTO.

### API riêng của `ParameterErrors`

Vì implements `Errors`, có thể gọi:

~~~java
if (result instanceof ParameterErrors errors) {
    int all = errors.getErrorCount();
    int fields = errors.getFieldErrorCount();
    int globals = errors.getGlobalErrorCount();

    for (FieldError field : errors.getFieldErrors()) {
        String path = field.getField();
        String code = field.getCode();
    }

    for (ObjectError object : errors.getGlobalErrors()) {
        String code = object.getCode();
    }
}
~~~

Snippet nằm trong một method có biến `result` kiểu `ParameterValidationResult`. `FieldError extends ObjectError`, nhưng `getGlobalErrors()` tách lỗi toàn object khỏi field errors.

**Đừng gọi `((ParameterErrors) result).getFieldErrors()` không kiểm tra kiểu**: nhóm direct constraint thường chỉ là `ParameterValidationResult` và không triển khai `Errors`. Dùng `instanceof ParameterErrors`.

### Các lỗi trong `getResolvableErrors()` của bean

`ParameterValidationResult.getResolvableErrors()` trả các lỗi thích hợp cho `MessageSource`. Với subclass `ParameterErrors`, danh sách này tương ứng với những errors trên bean; nếu cần **đường dẫn field**, phải dùng API `Errors.getFieldErrors()`. Vì vậy:

- Dùng `getResolvableErrors()` để lấy tổng/nhóm thông báo.
- Dùng `ParameterErrors.getFieldErrors()` để biết field path.
- Dùng `ParameterErrors.getGlobalErrors()` để biết object-level errors.

Không bắt frontend suy luận field name từ chuỗi message; các cấu trúc trên là dữ liệu máy đọc được.

## 7. Container: một tham số Java có thể có nhiều nhóm

Javadoc của `ParameterValidationResult` nhấn mạnh trường hợp `@Valid` trên container chứa nhiều phần tử, như:

~~~java
List<@Valid ItemDto> items
Map<String, @Valid ItemDto> itemsByKey
ItemDto[] items
~~~

Đây là cú pháp Java/Jakarta Validation minh họa **method-parameter container**, không phải ba controller handler methods độc lập. Khi một số phần tử vi phạm, Spring có thể tạo **một `ParameterValidationResult`/`ParameterErrors` cho mỗi phần tử có lỗi**.

Ví dụ phương thức (đường method validation đã được kích hoạt phù hợp):

~~~java
public void submit(
        @Valid List<ItemDto> items) {
    // ...
}
~~~

Giả sử `items[0]` và `items[2]` sai; cả hai kết quả vẫn tham chiếu **cùng Java method parameter** index 0, nhưng:

~~~text
ParameterErrors A
  parameterIndex = 0
  containerIndex = 0
  fieldErrors = ["sku"]

ParameterErrors B
  parameterIndex = 0
  containerIndex = 2
  fieldErrors = ["quantity"]
~~~

Tổng `getParameterValidationResults().size()` có thể là 2 dù Java signature chỉ có **một** argument. Nếu code dùng `Map<String, ItemDto>`, metadata `getContainerKey()` có thể chỉ ra key của phần tử. `getContainerIndex()` chỉ có ý nghĩa khi có index phù hợp; `Set` hoặc những container không có thứ tự ổn định có thể không cung cấp index.

**Không giả định `@RequestBody List<@Valid ItemDto>` tự tạo kết quả method-level này trong mọi cấu hình MVC.** Cơ chế có được bật hay không phụ thuộc cách resolver và method validation được kích hoạt; sơ đồ nhằm giải thích **shape của `ParameterValidationResult` khi có container results**.

### Cách tạo path cho frontend

Một API có thể biểu diễn:

~~~json
{
  "parameterIndex": 0,
  "source": "BODY",
  "containerIndex": 2,
  "fieldErrors": [
    {
      "field": "sku",
      "message": "SKU không được để trống"
    }
  ]
}
~~~

Frontend có thể hiển thị lỗi tại `items[2].sku`, nhưng chỉ khi contract đã nói rõ container là `items` và index đó tương ứng thứ tự request. Không tự dựng path bằng cách nối chuỗi trong mọi trường hợp `Map`/`Set`. Map key có thể chứa dấu chấm, dấu ngoặc hoặc dữ liệu nhạy cảm; cần escaping, whitelisting và security review trước khi phản hồi.

### `getContainer()` không nên serialize

`getContainer()` có thể trả nguyên `List`/`Map` chứa DTO. Gửi thẳng ra JSON lỗi có thể làm rò rỉ dữ liệu request và khiến response rất lớn. Tốt hơn là chỉ xuất index/path đã được kiểm soát, mã lỗi, message an toàn.

## 8. Cross-parameter constraints không thuộc một nhóm cụ thể

Một constraint có thể kiểm tra **tương quan giữa các method arguments** thay vì kiểm tra một argument riêng. Ví dụ một method nhận `startDate` và `endDate`, trong đó end phải sau start.

Jakarta Validation có cơ chế **cross-parameter validation** (dựa trên `ConstraintValidator<A, Object[]>` và validation target phù hợp). Khi Spring adapt kết quả này, `MethodValidationResult.getCrossParameterValidationResults()` cho phép lấy các lỗi được gắn với **cặp/tập tham số**.

Ví dụ shape:

~~~text
MethodValidationResult
|
+-- parameterValidationResults = []
|
+-- crossParameterValidationResults
       +-- "endDate must be after startDate"
~~~

Nếu cùng request còn vi phạm direct constraint khác, cả hai danh sách có thể cùng không trống. Vì vậy không dùng:

~~~java
int errors = ex.getParameterValidationResults().size();
~~~

để kết luận **tổng số lỗi bằng 0** khi thực tế có cross-parameter violation.

Một cách tính số **error entries được adapt** theo các danh sách (không phải số field duy nhất):

~~~java
int parameterEntries = ex.getParameterValidationResults()
    .stream()
    .mapToInt(r -> r.getResolvableErrors().size())
    .sum();

int crossEntries =
    ex.getCrossParameterValidationResults().size();

int totalEntries = parameterEntries + crossEntries;
~~~

Đây là snippet trong exception handler. Khi thiết kế error contract, để cross-parameter errors trong `crossParameterErrors[]` hoặc nhóm `objectErrors[]` có scope rõ, **không gán ngẫu nhiên vào parameter #0**.

Không nhầm với **class-level Bean Validation** trên một DTO có hai fields; lỗi đó thường thuộc `ParameterErrors` của DTO (global/object error của bean), không phải Jakarta cross-parameter constraint trên toàn method.

## 9. Return-value validation: status 500 và nhóm return descriptor

Không chỉ input, Spring còn có thể validate **giá trị trả về** của controller method:

~~~java
@GetMapping("/api/broken")
@NotNull
public String broken() {
    return null;
}
~~~

Khi Spring MVC built-in method validation đang hoạt động, method chạy và trả `null`, vi phạm `@NotNull` trên return value. `HandlerMethodValidationException` có:

~~~java
ex.isForReturnValue() == true
ex.getStatusCode().value() == 500
~~~

Đây là **mô tả giá trị kiểm tra**, không phải các câu lệnh Java độc lập.

**Vì sao 500 thay vì 400?** Client không gửi giá trị trả về; server đã tự phá vỡ hợp đồng của method. Không nên trả một danh sách “request field errors” để client sửa dữ liệu khi thực tế là bug server.

### Tách response công khai và log nội bộ

Với input failure, có thể trả tên tham số, loại lỗi, message an toàn để client sửa. Với return-value failure:

- Giữ HTTP **500**.
- Không phản hồi internal method name, stack trace, object value, Java class names hoặc dữ liệu trả về nhạy cảm.
- Ghi server logs/tracing với correlation ID ở mức phù hợp.
- Trả thông báo chung như `INTERNAL_CONTRACT_VIOLATION` nếu cần, không hướng dẫn người dùng sửa một input cụ thể khi lỗi nằm ở server.

Nếu method thực hiện ghi DB trước rồi return validation thất bại, **không** mặc định mọi side effect sẽ rollback; còn phụ thuộc transaction boundaries và thời điểm commit.

### Return descriptor và index

`MethodParameter` dùng convention **-1** cho method return type/descriptor; các input parameters thông thường có index 0, 1, 2... Đừng xây public API buộc người dùng gửi một field tên `-1`. Khi `isForReturnValue()` true, nên tạo response server error riêng.

## 10. `HandlerMethodValidationException.Visitor`

Khi tạo response khác nhau cho query/path/header/body, Spring cung cấp visitor phân loại kết quả theo annotation trên handler argument:

~~~java
ex.visitResults(
    new HandlerMethodValidationException.Visitor() {

        @Override
        public void requestParam(
                RequestParam annotation,
                ParameterValidationResult result) {
            // Lỗi của @RequestParam.
        }

        @Override
        public void pathVariable(
                PathVariable annotation,
                ParameterValidationResult result) {
            // Lỗi của @PathVariable.
        }

        @Override
        public void requestHeader(
                RequestHeader annotation,
                ParameterValidationResult result) {
            // Lỗi của @RequestHeader.
        }

        @Override
        public void requestBody(
                RequestBody annotation,
                ParameterErrors errors) {
            // Có thể đọc getFieldErrors/getGlobalErrors.
        }

        @Override
        public void other(ParameterValidationResult result) {
            // Những kiểu argument khác.
        }
    }
);
~~~

Đây là **snippet minh họa dùng trong handler có biến `ex`**, không phải một class Java hoàn chỉnh. Cần imports `HandlerMethodValidationException`, `ParameterValidationResult`, `ParameterErrors` và các web binding annotations. Interface còn có những callbacks khác, ví dụ `modelAttribute`, `requestPart`. Một số annotation được truyền vào callbacks có thể `null` trong các trường hợp Spring suy ra loại argument mà không cần annotation tường minh; tránh dereference mù quáng.

Visitor hữu ích khi:

- Cần phân biệt `source = "QUERY"`, `"PATH"`, `"HEADER"`, `"BODY"`.
- DTO body/model attribute cần field errors, trong khi primitive request param chỉ cần messages.
- Có nhiều controller signatures và muốn xử lý theo annotation type.

Nếu chỉ cần **nhóm theo Java parameter index**, vòng `for` trên `getParameterValidationResults()` đơn giản và dễ kiểm thử hơn. Đừng dùng Visitor khi mọi callback chỉ copy cùng một dòng code.

## 11. Thiết kế JSON lỗi theo nhóm tham số

Một REST API có thể chọn schema minh họa:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedGroups": 3,
  "crossParameterErrorCount": 0,
  "groups": [
    {
      "parameterIndex": 0,
      "source": "PATH",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 1,
      "source": "QUERY",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 2,
      "source": "HEADER",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    }
  ]
}
~~~

Đây là **contract do ví dụ tự định nghĩa** chứ **không phải response mặc định của Spring Framework**. Trong sản phẩm thực, có thể thêm danh sách mã lỗi và message đa ngữ, hoặc dùng `ProblemDetail` RFC 9457 với extension properties.

Giải thích các trường:

| Field | Ý nghĩa |
|---|---|
| `code` | Mã phản hồi ổn định do ứng dụng định nghĩa |
| `status` | Trạng thái HTTP trong body, phải khớp status thực |
| `returnValue` | Tách input validation khỏi server return-value violation |
| `affectedGroups` | Số `ParameterValidationResult`; **không đồng nghĩa tổng violation** |
| `crossParameterErrorCount` | Số lỗi cross-parameter tách riêng |
| `groups[]` | Danh sách các nhóm kết quả |
| `parameterIndex` | Vị trí parameter Java; **không phải field path frontend** |
| `source` | Loại nguồn dữ liệu (PATH/QUERY/HEADER/BODY/...) |
| `errorCount` | Số `MessageSourceResolvable` trong nhóm |
| `fieldErrorCount` | Khi `ParameterErrors`, số field errors lồng nhau |
| `globalErrorCount` | Khi `ParameterErrors`, số object-level errors lồng nhau |
| `containerIndex` | Index của phần tử trong container, nếu có |

**Hai danh sách quan trọng chưa nằm trong schema tối giản** là field path messages và cross-parameter message details. Mẫu runnable ưu tiên một schema **đếm và phân nhóm ổn định**, tránh phụ thuộc bản dịch/locale, nhưng phần 13 giải thích cách nâng cấp để đưa messages an toàn vào API.

### Không dựa vào thứ tự nhóm khi contract không cam kết

Đừng viết frontend rằng `groups[0]` nhất định là `id`, `groups[1]` nhất định là `limit` trong mọi tình huống. Dù Spring thường trình bày kết quả theo parameter order, với containers, multiple constraints và version changes, UI nên xác định bằng `parameterIndex` và `source`, không coi vị trí JSON array là định danh.

Nếu yêu cầu một thứ tự cố định để chụp snapshot/test, hãy **chủ động sắp xếp** kết quả theo field/parameter index và container index trong mapper, với tie-breakers được tài liệu hóa.

## 12. Chương trình Spring Boot 3.5 / Java 17+ đầy đủ

Ứng dụng có bốn tình huống:

1. GET `/api/quotes/{id}`: direct constraints trên `@PathVariable`, `@RequestParam` và `@RequestHeader`.
2. POST `/api/quotes/mixed`: DTO `@Valid @RequestBody` kết hợp `@Pattern` trên `@RequestParam` để có **`ParameterErrors` và `ParameterValidationResult`** cùng một exception.
3. POST `/api/quotes/dto-only`: chỉ có `@Valid` trên DTO để so sánh **`MethodArgumentNotValidException`**.
4. GET `/api/quotes/broken`: return-value `@NotNull` cố tình vi phạm để kiểm tra **HTTP 500**.

Một `@RestControllerAdvice` sẽ override các extension points có sẵn trong `ResponseEntityExceptionHandler`. Không có class-level `@Validated` trên controller; mục tiêu là **built-in MVC method validation**, không phải AOP service validation.

Tất cả Java files đặt trong package `com.example.paramgroups`, dùng **Spring Boot 3.5.x / Spring Framework 6.2.x / Java 17+**.

### 12.1. Gradle dependencies

Trong một project Spring Boot đã cấu hình Boot Gradle plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-web` cung cấp Servlet MVC; `spring-boot-starter-validation` có Jakarta Validation provider, cần để constraints có tác dụng; test starter cung cấp JUnit và MockMvc. Không dùng `javac` thuần không có classpath Spring/Boot.

Nếu đang dùng Spring Boot 4/Spring Framework 7, phải kiểm tra lại modules/dependencies/API theo phiên bản trước khi sao chép nguyên mẫu.

### 12.2. `ParameterGroupsApplication.java`

Tạo `src/main/java/com/example/paramgroups/ParameterGroupsApplication.java`:

~~~java
package com.example.paramgroups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParameterGroupsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParameterGroupsApplication.class, args);
    }
}
~~~

### 12.3. `QuoteRequest.java`

Tạo `src/main/java/com/example/paramgroups/QuoteRequest.java`:

~~~java
package com.example.paramgroups;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record QuoteRequest(
    @NotBlank String code,
    @Min(1) int quantity
) {
}
~~~

Dữ liệu:

~~~json
{"code":"","quantity":0}
~~~

có **hai nested field errors** khi Bean Validation áp dụng, vì code rỗng vi phạm `@NotBlank` và quantity 0 vi phạm `@Min(1)`. Một object có nhiều field errors không đồng nghĩa nhiều Java method parameters.

### 12.4. `QuoteController.java`

Tạo `src/main/java/com/example/paramgroups/QuoteController.java`:

~~~java
package com.example.paramgroups;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    @GetMapping("/{id}")
    public QuoteView get(
            @PathVariable("id") @Min(1) long id,
            @RequestParam("limit")
            @Min(1) @Max(5) int limit,
            @RequestHeader("X-Channel")
            @Pattern(regexp = "web|mobile") String channel) {

        return new QuoteView(id, limit, channel);
    }

    @PostMapping("/mixed")
    public QuoteView mixed(
            @Valid @RequestBody QuoteRequest request,
            @RequestParam("source")
            @Pattern(regexp = "web|mobile") String source) {

        return new QuoteView(
            1, request.quantity(), source);
    }

    @PostMapping("/dto-only")
    public QuoteView dtoOnly(
            @Valid @RequestBody QuoteRequest request) {

        return new QuoteView(
            1, request.quantity(), "web");
    }

    @GetMapping("/broken")
    @NotNull
    public String broken() {
        return null; // Cố ý sai hợp đồng return value.
    }

    public record QuoteView(
        long id,
        int limit,
        String channel
    ) {
    }
}
~~~

Giải thích:

- Các constraints đặt **trực tiếp** lên `id`/`limit`/`channel` khiến `get` cần built-in method validation.
- Method `mixed` có một DTO `@Valid` và một direct constraint `@Pattern`; nested violations của DTO và direct violation của source có thể cùng được nhóm trong `HandlerMethodValidationException`.
- Method `dtoOnly` chỉ có cascade marker `@Valid` trên body, không có direct constraint khác. Với DTO sai, đường thông dụng là `MethodArgumentNotValidException`.
- `broken` có return constraint `@NotNull`; nếu trả `null`, đó là server contract violation **500**.
- **Không** thêm `@Validated` cấp class: điều đó có thể chuyển xử lý validation qua proxy/AOP thay vì MVC built-in handler method validation.

### 12.5. `ValidationAdvice.java` — nhóm lỗi thành JSON

Tạo `src/main/java/com/example/paramgroups/ValidationAdvice.java`:

~~~java
package com.example.paramgroups;

import java.util.List;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ValidationAdvice
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<ParameterIssue> groups =
            ex.getParameterValidationResults()
                .stream()
                .map(this::toIssue)
                .toList();

        MethodProblem body = new MethodProblem(
            "METHOD_VALIDATION",
            status.value(),
            ex.isForReturnValue(),
            groups.size(),
            ex.getCrossParameterValidationResults().size(),
            groups
        );

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object>
            handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ArgumentProblem body = new ArgumentProblem(
            "ARGUMENT_VALIDATION",
            status.value(),
            ex.getBindingResult().getFieldErrorCount(),
            ex.getBindingResult().getGlobalErrorCount()
        );

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }

    private ParameterIssue toIssue(
            ParameterValidationResult result) {

        MethodParameter method =
            result.getMethodParameter();

        int fieldErrors = 0;
        int globalErrors = 0;

        if (result instanceof ParameterErrors nested) {
            fieldErrors = nested.getFieldErrorCount();
            globalErrors = nested.getGlobalErrorCount();
        }

        return new ParameterIssue(
            method.getParameterIndex(),
            location(method),
            result.getResolvableErrors().size(),
            fieldErrors,
            globalErrors,
            result.getContainerIndex()
        );
    }

    private String location(MethodParameter parameter) {
        if (parameter.hasParameterAnnotation(
                PathVariable.class)) {
            return "PATH";
        }
        if (parameter.hasParameterAnnotation(
                RequestParam.class)) {
            return "QUERY";
        }
        if (parameter.hasParameterAnnotation(
                RequestHeader.class)) {
            return "HEADER";
        }
        if (parameter.hasParameterAnnotation(
                RequestBody.class)) {
            return "BODY";
        }
        if (parameter.hasParameterAnnotation(
                ModelAttribute.class)) {
            return "MODEL";
        }
        return "OTHER";
    }

    public record MethodProblem(
        String code,
        int status,
        boolean returnValue,
        int affectedGroups,
        int crossParameterErrorCount,
        List<ParameterIssue> groups
    ) {
    }

    public record ParameterIssue(
        int parameterIndex,
        String source,
        int errorCount,
        int fieldErrorCount,
        int globalErrorCount,
        Integer containerIndex
    ) {
    }

    public record ArgumentProblem(
        String code,
        int status,
        int fieldErrorCount,
        int globalErrorCount
    ) {
    }
}
~~~

**Giải thích thiết kế:**

1. Advice extends `ResponseEntityExceptionHandler`; framework đã có một `@ExceptionHandler` trung tâm. Ta **override protected hooks** thay vì khai báo thêm `@ExceptionHandler(HandlerMethodValidationException.class)` trùng trong cùng subclass.
2. `status.value()` do Spring cung cấp: **400** nếu input sai, **500** nếu return value sai. Không hard-code 400 cho mọi method validation exception.
3. `groups.size()` là **affectedGroups**; `result.getResolvableErrors().size()` mới là số errors trong nhóm.
4. Với `ParameterErrors`, code đọc thêm `getFieldErrorCount()` và `getGlobalErrorCount()`, không ép `ParameterValidationResult` thường thành `ParameterErrors`.
5. `getCrossParameterValidationResults().size()` được báo ở field riêng.
6. `getContainerIndex()` giữ metadata index khi có; `containerKey` không được đưa ra vì có thể chứa dữ liệu nhạy cảm.
7. `location(...)` phân loại dựa trên **annotations**, không dựa vào `getParameterName()` (có thể không có metadata compiler).
8. Advice không trả `result.getArgument()`, `result.getContainer()`, rejected value, internal method name hoặc Java stack trace.
9. Response body được ứng dụng tự thiết kế nhằm **kiểm thử grouping**. Đây không phải `ProblemDetail` chuẩn; có thể nâng cấp ở phần 14.

**Giới hạn của ví dụ:** Nó chỉ trả **counts và metadata nhóm**, chưa trả message cụ thể cho người dùng. Ở API production cần có danh sách messages/codes được dịch và mapping field paths phù hợp; có mẫu mở rộng ở phần 13.

### 12.6. Chạy thử

Từ root project Spring Boot có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Giả sử ứng dụng dùng cổng 8080 mặc định.

Request hợp lệ:

~~~bash
curl -i "http://localhost:8080/api/quotes/10?limit=2" \
  -H "X-Channel: web"
~~~

Kỳ vọng HTTP **200 OK**:

~~~json
{
  "id": 10,
  "limit": 2,
  "channel": "web"
}
~~~

Request có **ba tham số sai**:

~~~bash
curl -i "http://localhost:8080/api/quotes/0?limit=9" \
  -H "X-Channel: other"
~~~

Kỳ vọng HTTP **400 Bad Request** và JSON mang ba groups, ví dụ:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedGroups": 3,
  "crossParameterErrorCount": 0,
  "groups": [
    {
      "parameterIndex": 0,
      "source": "PATH",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 1,
      "source": "QUERY",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    },
    {
      "parameterIndex": 2,
      "source": "HEADER",
      "errorCount": 1,
      "fieldErrorCount": 0,
      "globalErrorCount": 0,
      "containerIndex": null
    }
  ]
}
~~~

Ví dụ phản ánh tình huống một nhóm cho mỗi tham số. **Không coi thứ tự phần tử trong JSON arrays là định danh API** khi code thực tế có sorting/container groups khác.

Request với DTO và một direct constraint cùng sai:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/quotes/mixed?source=other" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Kỳ vọng HTTP **400** với `code="METHOD_VALIDATION"`, thường có **hai affected groups**:

- Group của parameter index 0, `source="BODY"`, subtype `ParameterErrors` với **2 field errors** (`code` và `quantity`).
- Group của parameter index 1, `source="QUERY"` với **1 direct violation** (`Pattern`).

**Tổng groups là 2; tổng errors của hai nhóm là 3.** `affectedGroups` không thể dùng làm tổng số lỗi.

Để đối chiếu với DTO-only:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/quotes/dto-only" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Kỳ vọng HTTP **400** với:

~~~json
{
  "code": "ARGUMENT_VALIDATION",
  "status": 400,
  "fieldErrorCount": 2,
  "globalErrorCount": 0
}
~~~

Cuối cùng, return-value constraint:

~~~bash
curl -i "http://localhost:8080/api/quotes/broken"
~~~

Kỳ vọng HTTP **500 Internal Server Error**, `code="METHOD_VALIDATION"` và `returnValue=true`. Đừng ghi nhận đây là lỗi của query parameter vì request không có input sai; server đã trả giá trị vi phạm `@NotNull`.

## 13. Thêm message codes, localization và field paths

Response ở phần 12 có ích để **học grouping**, nhưng frontend thực tế thường cần biết một lỗi nói gì. `ParameterValidationResult.getResolvableErrors()` đã đưa thông tin về dạng `MessageSourceResolvable`, có thể dịch bằng:

~~~java
String message = messageSource.getMessage(
    resolvable, locale);
~~~

Ví dụ thêm vào một mapper có `MessageSource messageSource` và `Locale locale`:

~~~java
List<String> messages =
    result.getResolvableErrors()
        .stream()
        .map(error -> messageSource.getMessage(
            error, locale))
        .toList();
~~~

Đây là snippet trong một method có biến `result`. Trong Spring MVC, `Locale` có thể lấy từ request context, chẳng hạn `LocaleContextHolder.getLocale()` ở một exception handler, hoặc từ argument `Locale locale` của controller khi xử lý trực tiếp.

### Direct constraint message codes

Spring có thể tạo codes từ annotation, method, parameter name/type, chẳng hạn `@Max`:

~~~text
Max.myObject#myMethod.myParameter
Max.myParameter
Max.int
Max
~~~

Đó là ví dụ **minh họa trong Javadoc**; mã cụ thể của ứng dụng phụ thuộc object/method/parameter metadata. Đừng hard-code method signature names hoặc dựa vào message đã được nội suy bằng tiếng Anh để phân loại lỗi.

### DTO errors với `ParameterErrors`

Khi `result instanceof ParameterErrors nested`:

~~~java
List<String> fieldPaths = nested.getFieldErrors()
    .stream()
    .map(FieldError::getField)
    .toList();

List<String> objectCodes = nested.getGlobalErrors()
    .stream()
    .map(ObjectError::getCode)
    .toList();
~~~

Nếu cần nhiều lỗi cùng field, giữ **danh sách** thay vì dùng `Map<String,String>` chỉ chứa một message cho mỗi key. Với lỗi toàn object, giữ scope riêng; không gán một field giả như `"_global"` trừ khi contract công khai đã chọn rõ quy ước đó.

### Tách messages khỏi business codes

Có thể tạo:

~~~json
{
  "parameterIndex": 0,
  "source": "BODY",
  "fields": [
    {
      "field": "code",
      "code": "NotBlank",
      "message": "Mã báo giá không được để trống."
    },
    {
      "field": "quantity",
      "code": "Min",
      "message": "Số lượng phải ít nhất là 1."
    }
  ]
}
~~~

Đây là **JSON extension do ứng dụng tự thiết kế**. `FieldError.getCode()` như `NotBlank`/`Min` là mã framework hữu ích khi học, nhưng product API có thể map sang mã stable hơn (`REQUIRED_FIELD`, `VALUE_BELOW_MIN`) để client không lệ thuộc chi tiết Jakarta constraint names.

### Đừng lộ input values khi dịch message

`result.getArgument()`, `FieldError.getRejectedValue()` và các annotation arguments có thể vô tình chứa thông tin nhạy cảm. Nếu message template có placeholder chứa rejected value, hãy rà soát bản dịch trước khi đưa ra public response. Log ít thông tin cần thiết và correlation ID; không log full body/token.

## 14. ProblemDetail và thiết kế phản hồi lỗi chuẩn

`HandlerMethodValidationException` triển khai `ErrorResponse` và có dữ liệu `ProblemDetail`; `ResponseEntityExceptionHandler` hỗ trợ chuẩn **RFC 9457 Problem Details**.

Một response có thể dựa trên `ProblemDetail`:

~~~java
ProblemDetail body =
    ProblemDetail.forStatus(ex.getStatusCode());

body.setTitle(
    ex.isForReturnValue()
        ? "Server contract violation"
        : "Invalid request parameters");

body.setProperty(
    "code",
    ex.isForReturnValue()
        ? "INTERNAL_CONTRACT_ERROR"
        : "METHOD_VALIDATION");

if (!ex.isForReturnValue()) {
    body.setProperty("parameterGroups", groups);
}
~~~

Đây là snippet minh họa trong exception handler; `groups` đã được ánh xạ an toàn. Với return-value error, không tự trả raw details hoặc parameter values cho client.

Trong Spring MVC, `ResponseEntityExceptionHandler.handleHandlerMethodValidationException(...)` là protected extension point. Nó đã tích hợp các khái niệm `MessageSource`, `ErrorResponse` và `ProblemDetail`, nên nếu chỉ cần chuẩn RFC 9457, bạn có thể **mở rộng default ProblemDetail** thay vì tự thiết kế hoàn toàn một JSON schema mới.

**Không đăng ký trùng handler.** Khi subclass `ResponseEntityExceptionHandler`, ưu tiên override `handleHandlerMethodValidationException(...)`; đừng thêm một `@ExceptionHandler(HandlerMethodValidationException.class)` trong cùng subclass nếu base đã xử lý kiểu đó.

### Nên trả nhóm hay flattened errors?

Cả hai đều có chỗ dùng:

- **Grouped representation** giữ bối cảnh method parameter, nested fields và container indices, phù hợp UI có nhiều nguồn input và analytics/debug.
- **Flattened representation** như `errors:[{source,path,code,message}]` dễ tiêu thụ với nhiều frontend, nhưng cần mapping rõ để không mất object-level/cross-parameter context.

Một thiết kế tốt có thể đưa cả `parameterGroups[]` và một danh sách errors chuẩn hóa được sinh từ groups, nhưng nên tránh giữ hai nguồn dữ liệu mâu thuẫn. Unit test mapper cần xác nhận tổng/loại lỗi không bị double-count khi flatten.

## 15. `BindingResult` và quy tắc xử lý lỗi cục bộ

Spring MVC cho phép `Errors`/`BindingResult` đứng ngay sau một object method argument để controller xử lý validation errors tại chỗ, nhưng khi **method validation** cần áp dụng:

- Nếu **tất cả** lỗi thuộc các parameters có `Errors`/`BindingResult` tương ứng ngay sau, handler có thể vẫn được gọi để xử lý.
- Nếu có lỗi ở **một parameter khác** không có cơ chế `Errors` tương ứng, Spring có thể ném `HandlerMethodValidationException` và handler không được gọi.

Ví dụ **snippet minh họa**:

~~~java
@PostMapping("/preview")
public String preview(
        @Valid @ModelAttribute("form") PreviewForm form,
        BindingResult errors,
        @RequestParam("count") @Min(1) int count) {

    if (errors.hasErrors()) {
        return "preview-form";
    }
    return "preview-ok";
}
~~~

`BindingResult` đứng **ngay sau `form`** và chỉ có ý nghĩa đối với errors của form đó. Nếu `form` sai nhưng `count=2` hợp lệ, có thể xử lý lỗi form trong method. Nếu `count=0`, direct constraint `@Min(1)` trên count sai; `BindingResult` của form **không** tự thu lỗi của `count`. Framework có thể ném `HandlerMethodValidationException`.

Điều này giải thích tại sao một project có `@Valid` và `BindingResult` vẫn có thể nhận exception khi thêm một `@RequestParam @Min` vào chữ ký handler. Kiểm tra **toàn bộ method signature**, không chỉ DTO.

## 16. Kiểm thử bằng MockMvc

Để biết `ParameterValidationResult` có thật sự được tạo bởi Spring MVC pipeline, phải test qua Spring MVC, không gọi `new QuoteController().get(...)` trực tiếp. Lời gọi Java thuần không chạy argument resolver, Jakarta Validator, `HandlerMethodValidator` và exception advice.

Tạo `src/test/java/com/example/paramgroups/ParameterGroupsMvcTest.java`:

~~~java
package com.example.paramgroups;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ParameterGroupsMvcTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validDirectConstraintsPass() throws Exception {
        mvc.perform(get("/api/quotes/10")
                .param("limit", "2")
                .header("X-Channel", "web"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(10))
            .andExpect(jsonPath("$.limit").value(2))
            .andExpect(jsonPath("$.channel").value("web"));
    }

    @Test
    void threeInvalidArgumentsCreateThreeGroups()
            throws Exception {

        mvc.perform(get("/api/quotes/0")
                .param("limit", "9")
                .header("X-Channel", "other"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedGroups")
                .value(3))
            .andExpect(jsonPath("$.returnValue")
                .value(false))
            .andExpect(result -> {
                HandlerMethodValidationException ex =
                    assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());

                assertTrue(
                    ex.getParameterValidationResults()
                        .stream()
                        .allMatch(r ->
                            r.getResolvableErrors().size() == 1));
            });
    }

    @Test
    void nestedDtoAndDirectParamAreTwoGroups()
            throws Exception {

        mvc.perform(post("/api/quotes/mixed")
                .param("source", "other")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedGroups")
                .value(2))
            .andExpect(result -> {
                HandlerMethodValidationException ex =
                    assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());

                assertTrue(
                    ex.getParameterValidationResults()
                        .stream()
                        .anyMatch(r ->
                            r instanceof ParameterErrors nested
                            && nested.getFieldErrorCount() == 2));
            });
    }

    @Test
    void dtoOnlyUsesArgumentLevelValidation()
            throws Exception {

        mvc.perform(post("/api/quotes/dto-only")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("ARGUMENT_VALIDATION"))
            .andExpect(jsonPath("$.fieldErrorCount")
                .value(2))
            .andExpect(result -> assertInstanceOf(
                MethodArgumentNotValidException.class,
                result.getResolvedException()));
    }

    @Test
    void invalidReturnValueKeepsHttp500()
            throws Exception {

        mvc.perform(get("/api/quotes/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.returnValue")
                .value(true))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void typeMismatchIsNotMinViolation()
            throws Exception {

        mvc.perform(get("/api/quotes/not-a-number")
                .param("limit", "2")
                .header("X-Channel", "web"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredHeaderIsResolutionError()
            throws Exception {

        mvc.perform(get("/api/quotes/10")
                .param("limit", "2"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void validMixedDtoPasses() throws Exception {

        mvc.perform(post("/api/quotes/mixed")
                .param("source", "mobile")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\":\"ABC\",\"quantity\":2}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.limit").value(2))
            .andExpect(jsonPath("$.channel").value("mobile"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Trong Spring Boot 3.5 + Spring Framework 6.2, starter Web + Validation, không có class-level `@Validated` trên controller và không có custom advice/proxy khác, **8 tests kỳ vọng PASS**. Đây là kết quả mong đợi từ code mẫu, **không phải khẳng định đã thực thi Gradle**.

Test không dựa hoàn toàn vào JSON shape. Nó xác minh **lớp exception thực tế**:

- `HandlerMethodValidationException` cho direct method constraints.
- `ParameterErrors` khi có nested DTO errors trong method-level validation.
- `MethodArgumentNotValidException` cho DTO-only validation.
- Return-value error mang status 500.
- Type mismatch/missing header đều trả 400 nhưng không bị gộp nhầm là direct constraint violations.

Không nên khẳng định thứ tự các vi phạm trong `getResolvableErrors()` luôn ổn định giữa providers. Test chỉ kiểm tra counts/kết cấu cần thiết. Trong project có Spring Security, các POST tests có thể cần CSRF/mock authentication setup thích hợp.

## 17. Mẫu kiểm tra tổng số lỗi và nhóm trong code thật

Có thể tạo một metric trong exception handler:

~~~java
List<ParameterValidationResult> results =
    ex.getParameterValidationResults();

int groups = results.size();

long distinctJavaPositions = results.stream()
    .map(r -> r.getMethodParameter().getParameterIndex())
    .distinct()
    .count();

int adaptedErrors = results.stream()
    .mapToInt(r -> r.getResolvableErrors().size())
    .sum();

int crossParameterErrors =
    ex.getCrossParameterValidationResults().size();
~~~

Đây là snippet trong scope đã có `ex`. Những metric này **không phải một số duy nhất** và không nên đổi tên tùy tiện:

- `groups` là số nhóm theo tham số/phần tử được ghi nhận.
- `distinctJavaPositions` là số vị trí method parameter khác nhau; với return validation có ý nghĩa khác, cần tách trước khi báo.
- `adaptedErrors` là số error entries từ groups.
- `crossParameterErrors` là số lỗi không thể gắn riêng vào một parameter.
- Tổng entries theo hai danh sách là `adaptedErrors + crossParameterErrors`, nhưng không đồng nghĩa số input fields khác nhau.

### Có nên log metric nào?

Cho observability, có thể log **status**, mã lỗi, số nhóm và loại nguồn input; tránh log giá trị đối số và container key. Chỉ khi cần điều tra nội bộ có kiểm soát mới bổ sung tên constraint/method, request ID và route template.

### Có nên đưa index của method parameter ra public API?

Index rất hữu ích để debug và unit test nhưng là chi tiết implementation. Khi refactor method signature thêm tham số trước `limit`, `parameterIndex` thay đổi. Nếu API phải ổn định dài hạn, map sang các định danh đã công bố như:

~~~text
PATH:id
QUERY:limit
HEADER:X-Channel
BODY:quote.code
BODY:quote.quantity
~~~

và đặt mapping trong một layer thống nhất, không để frontend hiểu thứ tự method parameters của Java.

## 18. Lưu ý về validation groups và AOP service

### Validation groups

Jakarta Validation supports nhóm constraints. Có thể dùng `@Validated(SomeGroup.class)` trên DTO argument trong Spring, hoặc cấu hình group behavior tương ứng trong method validation. Khi một group không bao gồm một constraint, không thể mặc định nói mọi annotation đều được kiểm tra.

`ParameterValidationResult` chỉ cho thấy những errors sau khi validator thực sự chạy với groups đã chọn. Đừng suy ra từ kết quả không có lỗi rằng object hợp lệ theo **tất cả** groups.

### AOP method validation ở service

Ví dụ:

~~~java
@Service
@Validated
public class QuoteService {

    public void approve(@NotBlank String code) {
        // ...
    }
}
~~~

Đây là snippet minh họa, cần imports và một Spring bean/proxy phù hợp. `MethodValidationPostProcessor`/`MethodValidationInterceptor` có thể kiểm tra constraints khi method được gọi **qua Spring AOP proxy**. Mặc định exception thường là Jakarta `ConstraintViolationException`. Khi bật `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, Spring có thể phát `MethodValidationException` chứa mô hình `MethodValidationResult` và các `ParameterValidationResult`.

Như vậy **`ParameterValidationResult` không chỉ thuộc Spring MVC**. Nó là mô hình Spring method-validation tổng quát, được sử dụng ở MVC handler error và trong adapted service method validation. Tuy nhiên, API HTTP `HandlerMethodValidationException` và status 400/500 của nó là chuyện riêng của web handler pipeline.

**Đừng cast mọi `ConstraintViolationException` thành `HandlerMethodValidationException`.** Service AOP, proxy self-invocation, `@Validated` ở controller và method groups có thể làm đường đi khác nhau. Cần thiết kế error boundary theo layer.

## 19. Xử lý edge cases trong phản hồi

### Không có direct constraint, chỉ có `@Valid`

Một DTO-only `@Valid @RequestBody` thường dùng `MethodArgumentNotValidException`. Nếu error handler chỉ override `handleHandlerMethodValidationException`, bạn vẫn cần xử lý đường này để giữ response thống nhất.

### Có direct constraint cùng DTO `@Valid`

Khi built-in method validation áp dụng, DTO errors có thể xuất hiện dưới dạng `ParameterErrors` trong cùng danh sách groups với direct parameter errors. Tránh validate lặp rồi cộng hai lần số lỗi.

### `BindingResult` ngay sau argument

Spring MVC có quy tắc chỉ gọi handler với errors được xử lý cục bộ nếu **mọi** lỗi đều thuộc parameters có `Errors` tương ứng. Nếu một tham số khác sai, `HandlerMethodValidationException` vẫn có thể phát sinh.

### Container Map keys và index

`getContainerKey()` có thể mang key không đáng tin từ request, thậm chí nhạy cảm. Không đưa thẳng key vào public response, log hoặc JSON path nếu chưa escaping và whitelisting. `Set` thường không có stable index như `List`.

### Cross-parameter errors

Không nằm trong `getParameterValidationResults()`; luôn kiểm tra `getCrossParameterValidationResults()` nếu ứng dụng có constraint liên quan nhiều parameters. Tránh gắn một cross-error vào một field cụ thể nếu constraint không xác định rõ field.

### Return validation

`isForReturnValue()` và HTTP 500 có ý nghĩa vận hành khác input violation. Đừng trả raw return value/parameter data để “giúp client debug”.

### MessageSource và locale

`MessageSourceResolvable` có fallback codes và default message; method parameter names có thể phụ thuộc metadata compiler. Không dùng message text để xác định mã máy ổn định. Đừng phụ thuộc mặc định vào tiếng Anh/tiếng Việt của validation provider cho mọi locale.

### JSON response và ProblemDetail

Ví dụ dùng record JSON riêng; Spring có `ProblemDetail` theo RFC 9457. Nếu ứng dụng muốn cùng chuẩn lỗi với domain error, chọn một schema có tài liệu rõ. Tránh gắn claims về `application/problem+json` vào một record tùy chỉnh không thật sự triển khai ProblemDetail.

## 20. Các lỗi triển khai thường gặp

| Biểu hiện | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `affectedGroups=1` nhưng DTO có 2 field errors | Một `ParameterErrors` chứa nhiều `FieldError` | Đếm nested errors riêng |
| `affectedGroups=2` nhưng chỉ một Java parameter sai | Hai phần tử của container cùng method parameter | Xem `getContainerIndex()/getContainerKey()` |
| API thiếu cross-parameter errors | Chỉ duyệt `getParameterValidationResults()` | Đọc danh sách cross-parameter riêng |
| `ClassCastException` khi cast result sang `ParameterErrors` | Nhóm direct constraint không implements `Errors` | Dùng `instanceof ParameterErrors` |
| Không thấy `ParameterValidationResult` cho DTO-only | Argument-level validation, không phải method-level | Xử lý `MethodArgumentNotValidException` |
| `limit=abc` không có `Min` violation | Type conversion thất bại | Xử lý type mismatch riêng |
| HTTP 500 do validation nhưng advice ép 400 | Vi phạm return-value contract | Dùng `isForReturnValue()/getStatusCode()` |
| Controller có class-level `@Validated` và exception khác | AOP proxy method validation | Bỏ class-level nếu muốn built-in MVC 6.1+ |
| Dùng `getAllValidationResults()` mới trong 6.2 | API deprecated for removal | Dùng `getParameterValidationResults()` |
| Message không được dịch đúng locale | Dùng `getDefaultMessage()` thay vì MessageSource | Resolve `MessageSourceResolvable` |
| API lộ rejected password/token | Serialize `getArgument()/getContainer()` | Chỉ map các trường an toàn |
| Parameter name null trong JSON | Bytecode thiếu metadata tên parameter | Dùng explicit annotation names hoặc fallback ổn định |
| Một field path không khớp frontend | DTO nested/collection naming khác client | Định nghĩa mapping có test |
| Visitor không gọi callback mong muốn | Annotation không tường minh hoặc type khác | Dùng `other` fallback; kiểm tra visitor contract |
| Unit test gọi Java method trực tiếp không ném exception | Bỏ qua Spring MVC handler validation | Dùng MockMvc/HTTP integration |
| Thêm `@NotBlank` trên `@RequestParam` làm DTO error đổi loại | Kích hoạt method validation | Xử lý cả hai đường |
| Lỗi @Valid trên container không có index | Container không indexed hoặc cơ chế khác | Đọc metadata thực, không giả lập index |
| GET thiếu required header tạo lỗi 400 khác | Lỗi argument resolution trước method validation | Đừng gộp vào `Pattern` violation |
| API luôn chỉ trả fieldErrors | Bỏ qua direct parameter và cross errors | Thiết kế groups + scope |
| Tất cả errors bị trả raw code names | Chưa có i18n/mapping error contract | Dùng MessageSource và stable public codes |

### Checklist debug

1. Ứng dụng chạy Spring MVC 6.1+ hay WebFlux/AOP service?
2. Handler có direct constraint như `@Min`/`@Pattern` hay chỉ có `@Valid` trên DTO?
3. Argument resolution/type conversion đã thành công chưa?
4. Exception thực tế là `HandlerMethodValidationException`, `MethodArgumentNotValidException` hay loại khác?
5. `isForReturnValue()` là true hay false? HTTP status có được giữ nguyên không?
6. `getParameterValidationResults().size()` là mấy?
7. Có `ParameterErrors` trong danh sách không? Nested fields/object errors là gì?
8. Có container index/key khiến cùng Java index xuất hiện nhiều lần không?
9. Có cross-parameter errors không?
10. Mapper có serialize data nhạy cảm hoặc làm mất field errors không?
11. `@ControllerAdvice` và các override có trùng `@ExceptionHandler` không?
12. MockMvc tests có khẳng định cả exception class và response schema không?

## 21. Câu hỏi tự luyện

**1. `ParameterValidationResult` trả lời câu hỏi gì?**

Nó cho biết **method parameter hoặc container element nào** bị lỗi và các `MessageSourceResolvable` tương ứng, kèm metadata của parameter/argument/container.

**2. Một argument vi phạm hai annotations có bắt buộc tạo hai groups không?**

Không. Nó có thể tạo **một `ParameterValidationResult` chứa hai errors**.

**3. `ParameterErrors` khác `ParameterValidationResult` ở điểm gì?**

`ParameterErrors` là subclass có **`Errors`**, cho phép truy cập `getFieldErrors()`/`getGlobalErrors()` của bean được validate cascade.

**4. `getParameterValidationResults().size()` là số trường sai phải không?**

Không. Đó là số nhóm kết quả; một DTO group có thể có nhiều field errors, một container có nhiều nhóm cho cùng Java parameter.

**5. Với `List` có hai phần tử sai, có thể hai results cùng `getParameterIndex()` không?**

Có, khác `getContainerIndex()`; đó là lý do groupCount có thể lớn hơn số distinct Java parameter indices.

**6. Một cross-parameter violation nằm đâu?**

Trong `getCrossParameterValidationResults()`, không bắt buộc nằm trong một `ParameterValidationResult` của đối số đơn lẻ.

**7. HTTP status cho return-value validation failure trong `HandlerMethodValidationException` là gì?**

HTTP **500**, `isForReturnValue()==true`, vì server phá vỡ hợp đồng return value.

**8. DTO-only `@Valid @RequestBody` bị lỗi thường là exception nào?**

`MethodArgumentNotValidException` khi không có direct method constraint khác kích hoạt built-in method validation.

**9. Tại sao không nên trả `result.getArgument()` qua API?**

Nó có thể chứa dữ liệu cá nhân, mật khẩu, token hoặc object graph lớn; mapper nên chọn lọc mã, vị trí và message an toàn.

**10. Trong Spring 6.2 nên dùng `getAllValidationResults()` hay `getParameterValidationResults()`?**

Dùng `getParameterValidationResults()`; `getAllValidationResults()` được đánh dấu deprecated for removal.

**11. Vì sao `MethodArgumentTypeMismatchException` không có `@Min` error cho `id=abc`?**

Vì chưa chuyển thành kiểu Java hợp lệ, nên constraint numeric chưa thể kiểm tra.

**12. Làm gì để test grouping thực tế?**

Gửi request qua MockMvc, kiểm tra `HandlerMethodValidationException`, số groups, subtype `ParameterErrors` và HTTP status/body; không chỉ gọi Java method trực tiếp.

## 22. Checklist triển khai

- [ ] Chọn đúng Spring Framework version và web stack; hiểu built-in MVC 6.1+ vs service AOP.
- [ ] Dùng `getParameterValidationResults()` trên Spring 6.2, tránh API đã deprecated.
- [ ] Đếm riêng groupCount, errorCount trong nhóm và distinct Java parameter indices.
- [ ] Khi `result instanceof ParameterErrors`, đọc cả field/global nested errors.
- [ ] Không cast toàn bộ results thành `ParameterErrors`.
- [ ] Với container, kiểm tra index/key khi có; không giả định mỗi Java parameter chỉ tạo một group.
- [ ] Đọc `getCrossParameterValidationResults()` khi có cross-parameter constraints.
- [ ] Tách return-value error 500 khỏi input error 400.
- [ ] Xử lý cả `MethodArgumentNotValidException` của DTO-only và type conversion errors riêng.
- [ ] Không gắn class-level `@Validated` lên controller nếu cần built-in MVC method validation.
- [ ] Cân nhắc Visitor khi response cần phân biệt annotation/source.
- [ ] Nếu dùng MessageSource, resolve `MessageSourceResolvable` theo locale và ổn định mã API.
- [ ] Không lộ `getArgument()`, raw container/key, rejected values hay stack traces.
- [ ] Cho phép nhiều nested errors trong cùng một group và nhiều groups của cùng container parameter.
- [ ] Không phụ thuộc thứ tự groups/violations nếu không có contract; sort rõ khi cần.
- [ ] Dùng `ResponseEntityExceptionHandler` override đúng hook, tránh trùng exception mapping.
- [ ] Dùng `ProblemDetail` khi cần RFC 9457; đừng gọi record tự chế là ProblemDetail chuẩn.
- [ ] Kiểm thử cả valid, ba direct constraints sai, mixed nested+direct, DTO-only, return-value 500 và type mismatch.
- [ ] Khi nâng cấp Boot/Spring, kiểm tra lại javadocs và tests trước khi thay exception mapper.

**Ghi nhớ:** `ParameterValidationResult` là **đơn vị nhóm lỗi** của Spring method validation, **không phải đơn vị một constraint**. Lỗi trực tiếp xuất hiện dưới dạng `MessageSourceResolvable`; lỗi lồng trong DTO có thể được trình bày qua `ParameterErrors` với `FieldError`/`ObjectError`. Container elements và cross-parameter violations khiến việc đếm/hiển thị cần cẩn thận hơn. Khi thiết kế API, giữ **source, parameter index/path, nhóm, số lỗi, HTTP status và i18n** có cấu trúc, đồng thời không tiết lộ argument values.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — MethodValidationResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/MethodValidationResult.html)
- [Spring Framework 6.2 — ParameterValidationResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring Framework 6.2 — ParameterErrors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterErrors.html)
- [Spring Framework 6.2 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — HandlerMethodValidationException.Visitor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.Visitor.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework — Error Responses / Problem Details](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
