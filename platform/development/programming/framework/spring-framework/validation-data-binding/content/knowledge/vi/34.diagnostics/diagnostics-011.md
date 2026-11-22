# Log có mã đối tượng, đường dẫn và giai đoạn lỗi mà không lộ dữ liệu trong Spring Framework

## 1. Mục tiêu và tư duy chẩn đoán

Khi Spring MVC xử lý một HTTP request bị lỗi, thông báo “400 Bad Request” hoặc “Validation failed” chưa đủ để người vận hành biết lỗi đến từ **binding**, **validation**, **deserialization** hay **nghiệp vụ**. Tuy nhiên, việc ghi thẳng toàn bộ request body, rejected value và stack trace vào log để dễ debug có thể làm lộ mật khẩu, token, email, thông tin tài chính và dữ liệu riêng tư.

Một bản ghi chẩn đoán hữu ích nên trả lời **đúng những câu hỏi có thể trả lời an toàn**:

- **Mã đối tượng (object code):** thành phần dữ liệu nào đang được xử lý, ví dụ `SIGNUP_FORM` hoặc `ORDER_COMMAND`?
- **Đường dẫn (path):** field/property nào bị lỗi, ví dụ `email`, `seats` hoặc `shippingAddress.postalCode`? Nếu nói tới HTTP path, hãy dùng **route template** như `POST /orders/{id}`, không tự động dùng URL nguyên bản có ID, query và token.
- **Giai đoạn lỗi (stage):** lỗi xảy ra khi **BIND**, **VALIDATE**, **DESERIALIZE**, **ARGUMENT** hay **POLICY**?
- **Mã lỗi (code):** `typeMismatch`, `NotBlank`, `Email`, `INVALID_JSON`, `POLICY_DENIED`…?
- **Kết quả (status):** ví dụ HTTP 400, 409, 422 hay 500?
- **Mã tương quan (request ID):** một mã do server tạo hoặc đã xác minh theo chính sách để liên kết các sự kiện cùng request, **không dùng session ID hay access token làm request ID**.

Ví dụ bản ghi **an toàn về nội dung**:

```text
event=INPUT_FAILURE route=SIGNUP_FORM object=SIGNUP_FORM field=seats stage=BIND code=typeMismatch status=400 requestId=9adac0b5-0e34-411b-ab9c-4e92e8da7f61
```

Chuỗi UUID trên chỉ để minh họa, mỗi request thật sinh một ID khác. Bản ghi này đủ để phân loại vấn đề nhưng **không tiết lộ** giá trị đã bị từ chối, địa chỉ email, nội dung JSON, IP, cookie hoặc mã định danh khách hàng.

Ví dụ không nên ghi:

```text
ERROR /users/123456?token=very-secret password="hunter2"
Rejected value for email: private.person@example.test
Exception: JSON body {"accessToken":"secret", ...}
```

**Nguyên tắc:** Ghi **metadata đáng tin cậy, có giới hạn, đủ để chẩn đoán**; không sao chép dữ liệu người dùng/exception vào log chỉ vì framework đã cung cấp một `getMessage()` hoặc `getRejectedValue()`.

## 2. Năm tầng thông tin trong một sự kiện lỗi

| Trường | Giá trị nên ghi | Không nên ghi trực tiếp |
| --- | --- | --- |
| `object_code` | Mã nội bộ cố định như `SIGNUP_FORM`, `BOOKING_FORM` | Toàn bộ entity hoặc dữ liệu của đối tượng |
| `field_path` | `email`, `seats`, `recipient.name` sau allowlist/sanitization | Input value, map key tự do có thể chứa PII |
| `route` | Tên route hoặc template tĩnh như `SIGNUP_JSON` | `request.getRequestURI()` kèm ID/secret, query string |
| `stage` | Enum BIND/VALIDATE/DESERIALIZE/ARGUMENT/POLICY | Free-text do client tự gửi |
| `error_code` | `typeMismatch`, `NotBlank`, `INVALID_JSON`, `POLICY_DENIED` | Thông báo mặc định chứa giá trị input, nested exception message |
| `status` | 400, 403, 409, 422, 500 | Response body có PII |
| `request_id` | UUID hoặc trace ID do hạ tầng kiểm soát | Session ID, bearer token, raw `X-Request-Id` của client không kiểm tra |
| `time` | Timestamp chuẩn do logger thêm | Timestamp bất kỳ từ client không xác minh |
| `service` | Tên component/service phiên bản public đủ dùng | Secret config, môi trường nhạy cảm |
| `count` | Số lỗi, có giới hạn/bucket nếu cần | Toàn bộ `BindingResult`/exception object |

Một số field names cũng có thể nhạy cảm (ví dụ tên trường nội bộ biểu lộ bệnh án, giao dịch, tên nhân sự). Nếu việc tiết lộ schema là rủi ro, mapping field path sang một **error path code** cố định sẽ an toàn hơn.

### 2.1. “Mã đối tượng” không phải mặc định là database ID

Cần phân biệt:

- **Mã loại object**: `SIGNUP_FORM`, `ORDER_INPUT`; thường phù hợp để đưa vào log.
- **Spring object name**: `BindingResult#getObjectName()`, ví dụ `signupForm`; là thông tin về target validation, nhưng vẫn nên giới hạn theo allowlist.
- **Database primary key**: `accountId=12345`; có thể là dữ liệu cá nhân hoặc dùng để link danh tính, nên không tự log mặc định.
- **Business identifier**: email, số điện thoại, đơn hàng, mã khách; có thể nhạy cảm ngay cả khi không phải secret theo nghĩa mật mã.
- **Request/correlation ID**: mã nhận diện một lần xử lý; dùng để liên kết với hệ thống theo dõi, không thay thế các business identifiers.

Trong bài thực hành, `object=SIGNUP_FORM` là **mã loại đối tượng**, không phải ID tài khoản. Nếu ứng dụng cần liên kết sự kiện với resource thực, hãy cân nhắc mã opaque từ server, HMAC có khóa quản lý và chính sách retention/authorization; tránh hash thường cho email hay số điện thoại có entropy thấp vì có thể đoán ngược.

## 3. Giai đoạn lỗi: đừng gọi tất cả là “validation”

Một hệ thống nhận request có nhiều bước, tương ứng các nguồn dữ liệu khác nhau:

```text
HTTP request
   |
   +--> Filter / security / correlation
   |
   v
DispatcherServlet
   |
   +--> Route matching + argument resolution
   |        |
   |        +--> ARGUMENT: sai path/query parameter type
   |
   +--> Body parsing / HttpMessageConverter
   |        |
   |        +--> DESERIALIZE: JSON sai cú pháp, field không đọc được
   |
   +--> WebDataBinder cho @ModelAttribute
   |        |
   |        +--> BIND: sai kiểu, thiếu required field, suppressed field
   |
   +--> Jakarta Bean Validation / Spring Validator
   |        |
   |        +--> VALIDATE: @NotBlank, @Email, @Min, custom constraint
   |
   v
Controller -> service -> domain policy
   |
   +--> POLICY: không hợp lệ theo business/domain rule
   |
   +--> PERSIST: database/repository/transaction failure
   |
   v
HTTP response / error handler
```

Sơ đồ này minh họa **phân loại trách nhiệm**, không phải cam kết mỗi request đi tuần tự y hệt. Spring MVC 6.1+ có thêm whole-method validation; exception có thể khác theo annotations. Spring Security filter chain còn có các exception được xử lý ngoài `@ControllerAdvice`.

### 3.1. BIND: lỗi gán property

Với form submit:

```text
Content-Type: application/x-www-form-urlencoded

username=Alice&email=alice@example.test&seats=not-an-integer
```

Nếu DTO có `Integer seats`, `WebDataBinder` có thể tạo:

```text
object=SIGNUP_FORM field=seats stage=BIND code=typeMismatch
```

Bạn có thể dựa vào:

```java
FieldError error = bindingResult.getFieldError("seats");
boolean failure = error != null && error.isBindingFailure();
String code = error == null ? null : error.getCode();
```

Đây là fragment, cần DTO/bindingResult. `FieldError#isBindingFailure()` giúp phân biệt lỗi convert/binding với lỗi do Validator reject.

**Không dùng** `error.getRejectedValue()`, `error.toString()` hoặc `bindingResult.toString()` làm nội dung log. Các API này có thể chứa giá trị client đã gửi.

### 3.2. VALIDATE: dữ liệu parse được nhưng sai constraint

Với `seats=0`, Spring có thể parse được Integer 0 nhưng `@Min(1)` không chấp nhận. Khi đó:

```text
object=SIGNUP_FORM field=seats stage=VALIDATE code=Min
```

`@NotBlank` và `@Email` là các mã constraint khác. Trong Spring MVC, lỗi DTO từ `@Valid @RequestBody` khi không có `BindingResult` liền kề thường gây `MethodArgumentNotValidException`.

Một lỗi `@Valid` không nhất thiết là dữ liệu “độc hại”; chỉ biết nó không phù hợp contract. Đừng log nguyên object cho một lỗi validation chỉ vì bạn cho rằng nó chưa được lưu.

### 3.3. DESERIALIZE: không đọc được body

Với JSON không hoàn chỉnh:

```text
{"username":"Alice",
```

Jackson/HTTP message converter có thể ném lỗi trước khi Bean Validation chạy; trong MVC thường bọc vào `HttpMessageNotReadableException`. Một log an toàn:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=body stage=DESERIALIZE code=INVALID_JSON status=400
```

Không ghi `ex.getMostSpecificCause().getMessage()` hoặc nguyên chuỗi `ex.getMessage()`: tùy parser và cấu hình, message có thể chứa JSON token, field value, vị trí input hoặc kiểu nội bộ.

### 3.4. ARGUMENT: path/query conversion thất bại

Ví dụ:

```text
GET /api/signups/lookup?limit=abc
```

Controller cần `Integer limit`, nên `MethodArgumentTypeMismatchException` có thể xuất hiện và được xử lý qua `ResponseEntityExceptionHandler#handleTypeMismatch(...)`.

Chẩn đoán an toàn:

```text
route=LOOKUP object=LOOKUP_ARGUMENT field=limit stage=ARGUMENT code=TYPE_MISMATCH status=400
```

Đừng log toàn bộ query string. Header Authorization hoặc query token có thể bị ghi ngoài ý muốn nếu log raw request URL.

### 3.5. POLICY: quy tắc nghiệp vụ từ chối

Nếu application từ chối một đăng ký theo trạng thái hiện tại:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=object stage=POLICY code=POLICY_DENIED status=409
```

Đây là ví dụ **mã lỗi cố định**, không phải exception message được ghép từ username hoặc dữ liệu khách hàng. Phân quyền bảo mật (403) và business conflict (409) là hai loại quyết định khác nhau; không phải mọi POLICY error đều nên trả 409.

### 3.6. PERSIST: lỗi tại database

Với `DataIntegrityViolationException`, không log nguyên SQL, params hoặc chuỗi connection/constraint exception nếu chúng có khả năng tiết lộ dữ liệu. Có thể phân loại một mã nội bộ như `UNIQUE_CONSTRAINT` hoặc `PERSISTENCE_FAILURE` và log SQLState/constraint identifier **chỉ khi** các giá trị đó được allowlist và chính sách bảo mật cho phép. Nhiều lỗi DB cần HTTP 500; đừng ép mọi exception xuống 400.

Ví dụ runnable ở mục 9 **không có database**, nên PERSIST là kiến thức mở rộng chứ không phải một nhánh đã được kiểm thử trong ứng dụng mẫu.

## 4. Thông tin từ BindingResult: dùng gì và tránh gì?

`BindingResult` và `ObjectError`/`FieldError` có cả metadata an toàn tiềm năng lẫn dữ liệu có thể nhạy cảm.

| API | Giá trị | Mức độ an toàn mặc định |
| --- | --- | --- |
| `BindingResult#getObjectName()` | Tên object do MVC/binder đặt | Chỉ log sau mapping/allowlist |
| `FieldError#getField()` | Đường dẫn property như `email` hoặc `addresses[0].zip` | Cần lọc hoặc mapping, đặc biệt dynamic indexes/keys |
| `FieldError#getCode()` | Mã tổng quát như `NotBlank`/`typeMismatch` | Tốt nếu mapping thành mã cố định |
| `FieldError#getCodes()` | Dãy mã i18n có tên object/field | Không log toàn bộ nếu tiết lộ schema |
| `FieldError#isBindingFailure()` | Boolean chỉ nguồn lỗi binding | Hữu ích để chọn stage |
| `FieldError#getRejectedValue()` | Giá trị input bị từ chối | **Không log** |
| `FieldError#getDefaultMessage()` | Câu lỗi từ provider/custom validator | **Không log bừa bãi**; có thể chứa value |
| `ObjectError#getArguments()` | Các tham số message | Có thể chứa value/schema, cần tránh |
| `ObjectError#toString()` | Representation kỹ thuật | Không dùng trực tiếp làm log |
| `BindingResult#getTarget()` | Object đã bind | **Không serialize/log** |
| `BindingResult#getSuppressedFields()` | Danh sách tên field bị suppress | Log count hoặc mã cố định; names phải được lọc |

Để xác định stage cho field:

```java
Stage stage = error.isBindingFailure()
    ? Stage.BIND
    : Stage.VALIDATE;
```

Đây là fragment Java, dùng enum Stage của bài mẫu. Với global `ObjectError` (không có field), bạn có thể log `field=object` và code đã allowlist, thay vì truy cập một `rejectedValue` không tồn tại.

### 4.1. Vì sao field path cũng cần lọc?

`FieldError#getField()` thường đến từ cấu trúc server-side, nhưng property binding có thể hỗ trợ nested/indexed paths hoặc Map keys mà client tác động đến:

```text
items[100000].price
settings[private-user@example.test].value
metadata[Authorization].value
```

Các đường dẫn này có thể rất dài, chứa dữ liệu có ý nghĩa định danh, hoặc ký tự xuống dòng nếu input/metadata cho phép. Không tự động coi toàn bộ field path là an toàn chỉ vì nó nằm trong `FieldError`.

Trong demo, chỉ cho phép một tập field cố định: `username`, `email`, `seats`, `body`, `limit`, `object`, `suppressed`. Các tên khác được ánh xạ thành `other`, thay vì in nguyên văn. Với hệ thống lớn, nên tạo danh sách mã field/schema tĩnh theo từng DTO và mapping đường dẫn nested theo cấu trúc đã xác nhận.

### 4.2. Nếu thật sự cần biết object ID cụ thể

Có ba hướng:

1. **Không log ID:** giữ object type, route template và request ID; điều tra chi tiết qua truy vấn được kiểm soát quyền sau.
2. **Opaque public reference:** dùng ID không thể suy ra PII, có scope quyền và thời hạn giữ log.
3. **HMAC pseudonymization:** tạo dấu vết ổn định bằng khóa bí mật có rotation và access controls; tránh plain SHA-256 của email/số điện thoại vì chúng có không gian đoán được.

Pseudonymized identifier vẫn có thể là dữ liệu cá nhân theo nhiều chính sách pháp lý; áp dụng retention, access control và mục đích sử dụng minh bạch. Không tự động log luôn domain ID chỉ vì nó là số nguyên.

## 5. Request ID, Trace ID và MDC

### 5.1. Tại sao cần correlation?

Một HTTP request có thể gây nhiều log lines từ controller, validation advice và service. Nếu chỉ có timestamp, khó xác định chúng thuộc cùng request khi hệ thống có nhiều luồng chạy đồng thời. Correlation ID giúp liên kết các sự kiện mà không cần ghi tên người dùng hay payload.

Trong một ứng dụng Spring MVC Servlet đơn giản, có thể tạo UUID ở `OncePerRequestFilter` rồi lưu tạm trong SLF4J `MDC`:

```java
String requestId = UUID.randomUUID().toString();
MDC.put("requestId", requestId);
try {
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
}
```

Đây là fragment; class chạy đầy đủ ở mục 9. **MDC thường là ThreadLocal**; trong xử lý bất đồng bộ, thread pool, `@Async`, CompletableFuture hoặc Reactor, context có thể không tự truyền qua threads. Khi cần, dùng tracing/context propagation do framework hỗ trợ và kiểm thử lifecycle. Không dựa vào một ThreadLocal không được quản lý cho toàn distributed trace.

### 5.2. Không tin ngay X-Request-Id từ client

Header do client gửi có thể chứa ký tự xuống dòng, giá trị quá dài, chuỗi truy vấn hoặc thông tin cá nhân. Trong demo, server **luôn tạo UUID mới**, không đọc inbound header. Hệ thống có trusted gateway có thể xác minh và giữ correlation ID, nhưng phải validate format/length/issuer và chính sách trust boundary.

Không dùng session ID, access token, cookie hay email làm correlation ID; các giá trị đó tồn tại lâu hơn request và có rủi ro liên kết danh tính.

### 5.3. Request ID không thay authorization

Có một ID hợp lệ không có nghĩa người gửi có quyền đọc log liên quan tới ID đó. Khi trả request ID qua response header, cho phép người dùng hỗ trợ cung cấp nó nhưng phải yêu cầu nhân viên hỗ trợ có quyền phù hợp trước khi tra log. Mã tương quan không nên chứa nội dung người dùng và không phải khóa bảo mật.

### 5.4. Spring Boot/Micrometer Tracing

Khi tích hợp Micrometer Tracing/Actuator, Spring Boot có thể cung cấp `traceId`/`spanId` trong logging context và correlation pattern. Nếu đã có distributed tracing, ưu tiên tái sử dụng các IDs do hạ tầng kiểm soát thay vì tự phát minh nhiều mã xung đột. Tuy vậy không đưa `baggage` chứa PII vào MDC/log chỉ vì chúng nằm trong trace context.

**Demo dùng request ID đơn giản**, không bật Micrometer Tracing và không quảng cáo đó là distributed tracing.

## 6. Structured logging và chống log injection

OWASP Logging Cheat Sheet khuyến nghị các sự kiện có cấu trúc, nguồn dữ liệu rõ, filtering dữ liệu nhạy cảm, giới hạn kích thước và chống log injection.

Một attacker có thể gửi:

```text
x=bad\r\nWARN event=ADMIN_LOGIN_SUCCESS user=admin
```

Nếu ứng dụng nối input raw vào một dòng log text, ký tự CR/LF có thể tạo dòng giả hoặc làm hỏng parser. Đối với dữ liệu không tin cậy:

- Ưu tiên **schema cố định**: stage enum, object code enum, route enum, field/code đã allowlist.
- Dùng **parameterized logging**, không nối message template bằng input string.
- Dùng **JSON structured encoder** có escaping đúng ngữ cảnh log, không chỉ dựa vào placeholder.
- Giới hạn độ dài, ký tự và cardinality; thay giá trị không hợp lệ bằng sentinel như `other`.
- Không log stack trace/exception object mặc định cho lỗi client input.
- Tránh raw request logging ở servlet filters, HTTP clients, API gateways, reverse proxies hoặc APM payload capture; một logger application an toàn không làm các logger khác tự an toàn.

Ví dụ nguy hiểm:

```java
log.warn("Invalid value: " + rejectedValue);
log.warn("Request failed: {}", exception.getMessage());
log.warn("Request body: {}", rawBody);
```

Các dòng này là **minh họa không nên dùng**, không có biến khai báo độc lập. Dùng `{...}` placeholders **không tự xóa bí mật** khỏi biến nếu bạn vẫn truyền `rejectedValue`; bí mật chỉ được trình bày theo format khác.

Ví dụ an toàn hơn:

```java
log.warn(
    "event=INPUT_FAILURE object={} field={} stage={} code={} status={}",
    ObjectCode.SIGNUP_FORM,
    SafeField.EMAIL,
    Stage.VALIDATE,
    "Email",
    400
);
```

Các giá trị này đều do code server quyết định hoặc được mapping vào tập giới hạn.

### 6.1. JSON logs không phải một biện pháp bảo mật đầy đủ

Spring Boot 3.5 hỗ trợ structured logging formats như ECS/Logstash/GELF. Chọn `logging.structured.format.console=ecs` có thể giúp output mỗi event thành JSON một dòng và escape các trường đúng cách.

Nhưng nếu bạn đưa `password` vào thuộc tính JSON, log **vẫn chứa password**. Structured format chủ yếu giúp parser và chống log injection; **data minimization và redaction phải được thực hiện trước**. Ngoài ra lưu log tập trung phải có access control, retention, encryption và audit riêng.

### 6.2. Thông điệp cố định và fields riêng

Trong bài thực hành, logger dùng một message template cố định:

```text
event=INPUT_FAILURE route={} object={} field={} stage={} code={} status={} requestId={}
```

Vì mọi placeholder đều là enum/allowlisted tokens/số nguyên/UUID do server tạo, không có raw input. ECS console writer bọc thông điệp thành JSON. Với hệ thống lớn, có thể dùng SLF4J fluent API `logger.atWarn().addKeyValue("stage", stage)...` để từng field thành JSON attribute riêng; vẫn phải lọc chính những values đó.

## 7. Quy tắc mapping metadata an toàn

### 7.1. Object code

Một Spring error có `getObjectName()="signupForm"`. Ứng dụng có thể mapping:

```text
signupForm -> SIGNUP_FORM
other      -> UNKNOWN_OBJECT
```

Không log tất cả object names bằng cách gọi `String.valueOf(error.getObjectName())` nếu chúng có thể được xây từ request hoặc dữ liệu runtime không kiểm soát.

### 7.2. Field path

Trong DTO cố định:

```text
username -> username
email    -> email
seats    -> seats
anything else -> other
```

Nếu muốn nested paths như `shippingAddress.zip`, thêm chúng vào mapping một cách có chủ đích. Với paths có index, cân nhắc biến `items[137].price` thành `items[].price` thay vì giữ index quá lớn hoặc key chứa PII; mapping phải parse theo schema, không làm regex replace mù quáng trên arbitrary string.

### 7.3. Error code

Lấy `FieldError#getCode()` rồi mapping qua tập mã mà ứng dụng đã duyệt. Với Spring/Bean Validation thông thường có thể gặp `typeMismatch`, `required`, `NotBlank`, `Email`, `Min`, `Size`, `NotNull`. Custom code mới phải được thêm vào allowlist sau khi review.

Không log toàn bộ `getCodes()` nếu không cần, vì dãy đó có thể bộc lộ model names, field paths hoặc kiểu dữ liệu nội bộ. Không ghép rejectedValue vào errorCode.

### 7.4. Stage

Stage được quyết định từ **API/layer nơi phát hiện lỗi**, không phải một string `stage` do client gửi. Một `FieldError#isBindingFailure()` là dấu hiệu hữu ích cho BIND; lỗi từ `HttpMessageNotReadableException` thuộc DESERIALIZE; lỗi direct method argument thuộc ARGUMENT; business rule exception thuộc POLICY.

Đừng log `VALIDATE` cho JSON malformed chỉ vì client cuối cùng nhận HTTP 400.

## 8. Ví dụ đầu ra mong muốn

Một request form sai kiểu:

```text
POST /api/signups/form
Content-Type: application/x-www-form-urlencoded

username=Alice&email=alice@example.test&seats=SECRET_SENTINEL_42
```

Log application mong muốn chứa **chỉ metadata**:

```text
event=INPUT_FAILURE route=SIGNUP_FORM object=SIGNUP_FORM field=seats stage=BIND code=typeMismatch status=400 requestId=<server-generated-uuid>
```

Không được xuất chuỗi `SECRET_SENTINEL_42`. Tại HTTP response, có thể trả `ProblemDetail` chứa `status=400`, `title="Request rejected"` và `code="INVALID_INPUT"`, không đưa toàn bộ `BindingResult` vào JSON.

Nếu form gửi một địa chỉ email sai định dạng, log field `email` và mã `Email`; tuyệt đối không ghi địa chỉ cụ thể. Đây là cách tách **vị trí lỗi** khỏi **giá trị lỗi**.

Với một tài khoản hay hồ sơ nhạy cảm, không nên mặc định ghi raw ID trong URL. Dùng route enum `SIGNUP_FORM` hoặc template `POST /api/signups/form` cho phép nhóm vận hành hiểu loại request mà không biết danh tính.

## 9. Dự án mẫu hoàn chỉnh: Java 17 + Spring Boot 3.5.6

Bài lab tạo một REST API nhỏ với:

- JSON request và form request cho cùng `SignupForm`.
- `@Valid` trên request DTO để tạo validation errors.
- `BindingResult` trong form handler để phân biệt BIND/VALIDATE.
- `ResponseEntityExceptionHandler` override hooks cho lỗi JSON, argument và validation.
- Exception nghiệp vụ với mã cố định, không chứa raw input.
- `OncePerRequestFilter` tạo request ID từ server và dọn MDC trong `finally`.
- Logger với mã object, field path, stage, error code, route và status đã được allowlist.
- Spring Boot ECS console JSON logging.
- Test MockMvc kiểm tra **không có dữ liệu nhạy cảm giả lập** trong các log do ứng dụng tạo.

Đây là **demo local**, không lưu dữ liệu hoặc xử lý xác thực thật. Nó không phải API production; production cần authentication/authorization, privacy review, rate limiting, audit/retention, cơ chế tracing chính thức và logging filters cho toàn bộ hạ tầng.

### 9.1. Cấu trúc thư mục

```text
safe-validation-logs/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/safelogs/
    │   │   ├── SafeLogsApplication.java
    │   │   ├── CorrelationFilter.java
    │   │   ├── SignupForm.java
    │   │   ├── FailureEvents.java
    │   │   ├── SafeProblem.java
    │   │   ├── PolicyDeniedException.java
    │   │   ├── SignupController.java
    │   │   └── GlobalErrorAdvice.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/safelogs/SafeLogsTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>safe-validation-logs</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

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

`spring-boot-starter-web` mang Spring MVC và logging starter (thường Logback) qua transitive dependencies. `spring-boot-starter-validation` cung cấp Bean Validation provider. Test starter có MockMvc/JUnit và `OutputCaptureExtension`.

### 9.3. application.properties

```properties
# Chỉ nghe local để thử nghiệm.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.5: log JSON theo Elastic Common Schema.
logging.structured.format.console=ecs

# Không bật DEBUG/TRACE cho framework request/body mặc định.
logging.level.org.springframework.web=INFO
logging.level.demo.safelogs=INFO

spring.application.name=safe-validation-logs
```

Định dạng ECS giúp mỗi log event thành JSON thay vì nhiều dòng text không cấu trúc. Trong các bước phía dưới, ta chủ yếu kiểm tra nội dung trường `message` và danh sách token có/không có, không cố gắng so sánh từng thuộc tính ECS do Boot tự sinh.

### 9.4. SafeLogsApplication.java

```java
package demo.safelogs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeLogsApplication.class, args);
    }
}
```

### 9.5. CorrelationFilter.java

```java
package demo.safelogs;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // UUID được server tạo; không nhận raw X-Request-Id.
        String requestId = UUID.randomUUID().toString();

        MDC.put("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            // Tránh lẫn request ID khi servlet thread được tái sử dụng.
            MDC.remove("requestId");
        }
    }
}
```

Có thể mở rộng thành tracing context chuyên dụng trong hệ thống async/distributed. Ví dụ này chỉ cho sync servlet request; filter không tự giải quyết MDC propagation qua worker pool.

### 9.6. SignupForm.java

```java
package demo.safelogs;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class SignupForm {

    @NotBlank
    @Size(max = 40)
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(1)
    private Integer seats;

    public SignupForm() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }
}
```

DTO chỉ chứa những fields cần thiết; không có password, token, role hay internal tenant ID. Với test log, ta vẫn coi tất cả field **values** là không tin cậy và không được log.

### 9.7. FailureEvents.java — chỉ ghi metadata allowlisted

```java
package demo.safelogs;

import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

@Component
public class FailureEvents {

    private static final Logger LOG =
        LoggerFactory.getLogger(FailureEvents.class);

    public enum Route {
        SIGNUP_JSON,
        SIGNUP_FORM,
        LOOKUP
    }

    public enum ObjectCode {
        SIGNUP_FORM,
        LOOKUP_ARGUMENT,
        UNKNOWN_OBJECT
    }

    public enum Stage {
        BIND,
        VALIDATE,
        DESERIALIZE,
        ARGUMENT,
        POLICY
    }

    private static final Set<String> SAFE_FIELDS = Set.of(
        "username", "email", "seats", "body",
        "limit", "object", "suppressed"
    );

    private static final Set<String> SAFE_CODES = Set.of(
        "typeMismatch", "required",
        "NotBlank", "Email", "NotNull", "Min", "Size",
        "INVALID_JSON", "TYPE_MISMATCH",
        "POLICY_DENIED", "SUPPRESSED_FIELDS", "OTHER"
    );

    private static String safeField(String field) {
        return SAFE_FIELDS.contains(field) ? field : "other";
    }

    private static String safeCode(String code) {
        return SAFE_CODES.contains(code) ? code : "OTHER";
    }

    private static ObjectCode objectCode(
            BindingResult errors) {

        // Không tự log raw getObjectName().
        return "signupForm".equals(errors.getObjectName())
            ? ObjectCode.SIGNUP_FORM
            : ObjectCode.UNKNOWN_OBJECT;
    }

    public void event(
            Route route,
            ObjectCode object,
            String field,
            Stage stage,
            String code,
            int status) {

        String requestId = MDC.get("requestId");
        if (requestId == null) {
            requestId = "none";
        }

        // Mọi biến là enum/allowlisted token, số hoặc UUID server tạo.
        LOG.warn(
            "event=INPUT_FAILURE route={} object={} field={} "
                + "stage={} code={} status={} requestId={}",
            route.name(),
            object.name(),
            safeField(field),
            stage.name(),
            safeCode(code),
            status,
            requestId
        );
    }

    public void fromBindingResult(
            Route route,
            BindingResult errors,
            int status) {

        ObjectCode object = objectCode(errors);

        for (FieldError error : errors.getFieldErrors()) {
            Stage stage = error.isBindingFailure()
                ? Stage.BIND
                : Stage.VALIDATE;

            event(
                route, object, error.getField(),
                stage, error.getCode(), status);
        }

        for (ObjectError error : errors.getGlobalErrors()) {
            event(
                route, object, "object",
                Stage.VALIDATE, error.getCode(), status);
        }
    }
}
```

Vì `Set.of(...).contains(null)` trong Java immutable set có thể ném `NullPointerException`, khi áp dụng với API có thể trả `null` code, ta cần xử lý cẩn thận. Trong Spring `FieldError#getCode()` có thể null nếu tạo `ObjectError` custom không có code. **Sửa hai helper trong code thực hành bằng guard trước `contains`**:

```java
private static String safeField(String field) {
    return field != null && SAFE_FIELDS.contains(field)
        ? field : "other";
}

private static String safeCode(String code) {
    return code != null && SAFE_CODES.contains(code)
        ? code : "OTHER";
}
```

Hai helper trên là **phiên bản chính xác cần sử dụng** trong `FailureEvents.java`: khi copy file hoàn chỉnh, **thay hai method cùng tên bằng bản đã có null guard này**. Các method còn lại của file giữ nguyên. Tránh bỏ qua chi tiết đó vì mục tiêu của bài là lỗi request không được gây ra một lỗi logging mới.

Điểm quan trọng của logger:

- `Route`, `ObjectCode` và `Stage` là enum nội bộ, không nhận giá trị tùy ý từ client.
- `safeField` cho phép log đường dẫn property **đã duyệt**; unknown field thành `other`.
- `safeCode` chỉ giữ lỗi có trong danh sách; custom code chưa duyệt thành `OTHER`.
- `fromBindingResult` dùng `isBindingFailure()` để phân biệt BIND với VALIDATE.
- Không chạm `getRejectedValue()`, `getDefaultMessage()`, `getTarget()` hay raw request body.
- Không truyền exception vào vị trí tham số cuối logger, do đó không vô tình ghi stack trace của lỗi input.

### 9.8. SafeProblem.java — response an toàn

```java
package demo.safelogs;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;

public final class SafeProblem {

    private SafeProblem() {
    }

    public static ProblemDetail of(
            HttpStatusCode status, String publicCode) {

        ProblemDetail problem =
            ProblemDetail.forStatus(status);

        problem.setTitle("Request rejected");
        problem.setDetail(
            "The request could not be processed");
        problem.setProperty("code", publicCode);

        return problem;
    }
}
```

`publicCode` được caller truyền **từ constant của server**. Không đưa error message chi tiết, stack trace hoặc rejected value vào `ProblemDetail`. Khi Spring MVC serialize `ProblemDetail` qua Jackson, các trường chuẩn có thể gồm `type/title/status/detail/instance` và property mở rộng `code`; HTTP media type có thể là `application/problem+json`.

### 9.9. PolicyDeniedException.java

```java
package demo.safelogs;

public class PolicyDeniedException extends RuntimeException {

    private final FailureEvents.Route route;

    public PolicyDeniedException(FailureEvents.Route route) {
        super("Operation rejected by policy");
        this.route = route;
    }

    public FailureEvents.Route route() {
        return route;
    }
}
```

Exception này chỉ mang route enum an toàn. Không xây message từ username/email/ID của client. Đây là business conflict giả lập, **không thay thế authorization layer** của ứng dụng thật.

### 9.10. SignupController.java

```java
package demo.safelogs;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/signups")
public class SignupController {

    private final FailureEvents events;

    public SignupController(FailureEvents events) {
        this.events = events;
    }

    @InitBinder("signupForm")
    void restrictForm(WebDataBinder binder) {
        binder.setAllowedFields("username", "email", "seats");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> json(
            @Valid @RequestBody SignupForm form) {

        checkPolicy(form, FailureEvents.Route.SIGNUP_JSON);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("state", "accepted"));
    }

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            events.event(
                FailureEvents.Route.SIGNUP_FORM,
                FailureEvents.ObjectCode.SIGNUP_FORM,
                "suppressed",
                FailureEvents.Stage.BIND,
                "SUPPRESSED_FIELDS",
                400
            );
            return ResponseEntity.badRequest()
                .body(SafeProblem.of(
                    HttpStatus.BAD_REQUEST, "INVALID_INPUT"));
        }

        if (errors.hasErrors()) {
            events.fromBindingResult(
                FailureEvents.Route.SIGNUP_FORM, errors, 400);

            return ResponseEntity.badRequest()
                .body(SafeProblem.of(
                    HttpStatus.BAD_REQUEST, "INVALID_INPUT"));
        }

        checkPolicy(form, FailureEvents.Route.SIGNUP_FORM);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("state", "accepted"));
    }

    @GetMapping("/lookup")
    public Map<String, String> lookup(
            @RequestParam("limit") Integer limit) {
        return Map.of("state", "checked");
    }

    private static void checkPolicy(
            SignupForm form,
            FailureEvents.Route route) {

        if ("blocked".equalsIgnoreCase(form.getUsername())) {
            throw new PolicyDeniedException(route);
        }
    }
}
```

Một số điểm cốt lõi:

- JSON đi qua Jackson deserialization và `@Valid`, không qua property allowlist của `@ModelAttribute`.
- Form được bind bằng `@ModelAttribute("signupForm")` rồi nhận `BindingResult` **ngay sau** argument để tự phân loại binding/validation errors.
- Nếu có suppressed fields, handler từ chối và log **một mã cố định**, không log tên/giá trị field bất hợp lệ.
- Nếu validation không đạt, gọi logger với metadata rồi trả `ProblemDetail` tổng quát.
- Nếu data hợp lệ nhưng chính sách giả lập không cho, ném exception riêng; không log username.
- Endpoint lookup chỉ để minh họa lỗi convert query `limit=abc`. Biến `limit` không được phản hồi/log raw.
- `@Valid` không phải authorization; project không có Spring Security nên chỉ dùng local để học logging.

### 9.11. GlobalErrorAdvice.java

```java
package demo.safelogs;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.method.MethodValidationException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class GlobalErrorAdvice extends ResponseEntityExceptionHandler {

    private final FailureEvents events;

    public GlobalErrorAdvice(FailureEvents events) {
        this.events = events;
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        events.fromBindingResult(
            FailureEvents.Route.SIGNUP_JSON,
            ex.getBindingResult(),
            status.value());

        return handleExceptionInternal(
            ex,
            SafeProblem.of(status, "INVALID_INPUT"),
            headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        events.event(
            FailureEvents.Route.SIGNUP_JSON,
            FailureEvents.ObjectCode.SIGNUP_FORM,
            "body",
            FailureEvents.Stage.DESERIALIZE,
            "INVALID_JSON",
            status.value()
        );

        return handleExceptionInternal(
            ex,
            SafeProblem.of(status, "INVALID_INPUT"),
            headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        events.event(
            FailureEvents.Route.LOOKUP,
            FailureEvents.ObjectCode.LOOKUP_ARGUMENT,
            "limit",
            FailureEvents.Stage.ARGUMENT,
            "TYPE_MISMATCH",
            status.value()
        );

        return handleExceptionInternal(
            ex,
            SafeProblem.of(status, "INVALID_INPUT"),
            headers, status, request);
    }

    @ExceptionHandler(PolicyDeniedException.class)
    public ResponseEntity<ProblemDetail> handlePolicy(
            PolicyDeniedException ex) {

        events.event(
            ex.route(),
            FailureEvents.ObjectCode.SIGNUP_FORM,
            "object",
            FailureEvents.Stage.POLICY,
            "POLICY_DENIED",
            409
        );

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(SafeProblem.of(
                HttpStatus.CONFLICT, "POLICY_DENIED"));
    }
}
```

**Kiểm tra import:** `org.springframework.validation.method.MethodValidationException` không dùng trong file và có thể bỏ import này. Đây là ví dụ đầy đủ về các hooks **thực sự dùng** trong controller demo, không có whole-method validation. Khi viết Java source trong IDE, nên xóa import không dùng để giữ code sạch.

**Không thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` vào subclass** của `ResponseEntityExceptionHandler`: base class đã đăng ký mapping framework. Override `handleMethodArgumentNotValid(...)` và `handleHttpMessageNotReadable(...)` đúng chữ ký với `HttpStatusCode` của Spring 6.2. Business exception `PolicyDeniedException` không nằm trong danh sách base, nên dùng `@ExceptionHandler` riêng.

Trong application thật, phương thức global advice có thể xử lý nhiều routes chứ không chỉ hai routes của lab. **Không được hardcode `Route.SIGNUP_JSON` cho mọi HTTP exception trong một ứng dụng nhiều endpoints.** Hãy map handler/route metadata server-side (ví dụ request mapping pattern đã được Spring xác định và allowlist) hoặc tạo advice chuyên theo loại controller. Demo hardcode vì toàn bộ JSON POST và lookup đều thuộc một API lab có phạm vi cố định.

### 9.12. Chạy ứng dụng

Yêu cầu JDK 17+, Maven 3.x. Trong thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run
```

Ứng dụng nghe tại `http://127.0.0.1:8080` theo cấu hình lab. Trong terminal khác thử từng case.

**A. JSON hợp lệ:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups' \
  -H 'Content-Type: application/json' \
  -d '{"username":"Alice","email":"alice@example.test","seats":2}'
```

HTTP **201 Created**, response body:

```json
{"state":"accepted"}
```

Không có `event=INPUT_FAILURE` do app tạo cho request này. Header `X-Request-Id` có UUID do server sinh; không cần đưa user input vào log để có request ID.

**B. Form sai kiểu:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Alice' \
  --data-urlencode 'email=alice@example.test' \
  --data-urlencode 'seats=PRIVATE_SENTINEL_42'
```

HTTP **400 Bad Request**, log application chứa token:

```text
event=INPUT_FAILURE
route=SIGNUP_FORM
object=SIGNUP_FORM
field=seats
stage=BIND
code=typeMismatch
status=400
requestId=<UUID generated by server>
```

Đoạn trên trình bày các **token cần quan sát trong message**, không phải một JSON ECS log line đầy đủ. Không có `PRIVATE_SENTINEL_42` trong event message do `FailureEvents` tạo. Các trường `timestamp`, `logger`, `level` do Boot bổ sung riêng.

**C. Form sai validation:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Alice' \
  --data-urlencode 'email=PRIVATE_SENTINEL_NOT_EMAIL' \
  --data-urlencode 'seats=2'
```

HTTP **400 Bad Request**, có event:

```text
route=SIGNUP_FORM object=SIGNUP_FORM field=email stage=VALIDATE code=Email status=400
```

Không có địa chỉ email hoặc sentinel trong message log.

**D. Body JSON không đọc được:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups' \
  -H 'Content-Type: application/json' \
  -d '{"username":"PRIVATE_SENTINEL"'
```

HTTP **400 Bad Request**, logger ghi:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=body stage=DESERIALIZE code=INVALID_JSON status=400
```

Không ghi raw JSON, parser token hoặc exception chain.

**E. Query argument sai kiểu:**

```bash
curl -i 'http://127.0.0.1:8080/api/signups/lookup?limit=PRIVATE_SENTINEL'
```

HTTP **400 Bad Request**, logger ghi:

```text
route=LOOKUP object=LOOKUP_ARGUMENT field=limit stage=ARGUMENT code=TYPE_MISMATCH status=400
```

**F. Business policy từ chối:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups' \
  -H 'Content-Type: application/json' \
  -d '{"username":"blocked","email":"a@example.test","seats":1}'
```

HTTP **409 Conflict**, logger ghi:

```text
route=SIGNUP_JSON object=SIGNUP_FORM field=object stage=POLICY code=POLICY_DENIED status=409
```

Response có extension `code="POLICY_DENIED"` mà không lộ username.

**G. Extra field không được phép trong form:**

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Alice' \
  --data-urlencode 'email=alice@example.test' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'internalToken=PRIVATE_SENTINEL'
```

HTTP **400 Bad Request** và event:

```text
route=SIGNUP_FORM object=SIGNUP_FORM field=suppressed stage=BIND code=SUPPRESSED_FIELDS status=400
```

Tên `internalToken` và giá trị `PRIVATE_SENTINEL` không được đưa vào event. Lưu ý `getSuppressedFields()` **không tự là FieldError**; controller kiểm tra và ghi event có mã riêng.

## 10. Kiểm thử log an toàn bằng MockMvc

Chỉ nhìn HTTP status chưa đủ. Bài này cần kiểm tra **log thực sự không chứa input marker**. Với Spring Boot Test, có thể dùng `OutputCaptureExtension` để thu stdout/stderr trong quá trình chạy test. Vì logging được cấu hình JSON ECS, test nên assert các token quan trọng thay vì toàn bộ JSON byte-for-byte.

### 10.1. SafeLogsTest.java

```java
package demo.safelogs;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeLogsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void wrongFormTypeLogsFieldAndStageButNotValue(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_42";

        mvc.perform(post("/api/signups/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "Alice")
                .param("email", "alice@example.test")
                .param("seats", marker))
            .andExpect(status().isBadRequest())
            .andExpect(header().exists("X-Request-Id"))
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("route=SIGNUP_FORM"));
        assertTrue(logs.contains("field=seats"));
        assertTrue(logs.contains("stage=BIND"));
        assertTrue(logs.contains("code=typeMismatch"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void invalidEmailLogsValidationCodeWithoutValue(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_NOT_EMAIL";

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"Alice\","
                    + "\"email\":\"" + marker + "\","
                    + "\"seats\":2}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("route=SIGNUP_JSON"));
        assertTrue(logs.contains("field=email"));
        assertTrue(logs.contains("stage=VALIDATE"));
        assertTrue(logs.contains("code=Email"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void malformedJsonLogsStageNotPayload(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_JSON";

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"" + marker + "\""))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("stage=DESERIALIZE"));
        assertTrue(logs.contains("code=INVALID_JSON"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void queryTypeMismatchLogsArgumentStage(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_QUERY";

        mvc.perform(get("/api/signups/lookup")
                .param("limit", marker))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        String logs = output.getAll();
        assertTrue(logs.contains("route=LOOKUP"));
        assertTrue(logs.contains("field=limit"));
        assertTrue(logs.contains("stage=ARGUMENT"));
        assertFalse(logs.contains(marker));
    }

    @Test
    void policyFailureLogsOnlyBusinessCode(
            CapturedOutput output) throws Exception {

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"blocked\","
                    + "\"email\":\"a@example.test\","
                    + "\"seats\":1}"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("POLICY_DENIED"));

        String logs = output.getAll();
        assertTrue(logs.contains("stage=POLICY"));
        assertTrue(logs.contains("code=POLICY_DENIED"));
        assertFalse(logs.contains("a@example.test"));
    }

    @Test
    void suppressedFormFieldDoesNotLeakItsNameOrValue(
            CapturedOutput output) throws Exception {

        final String marker = "PRIVATE_SENTINEL_EXTRA";

        mvc.perform(post("/api/signups/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "Alice")
                .param("email", "alice@example.test")
                .param("seats", "2")
                .param("internalToken", marker))
            .andExpect(status().isBadRequest());

        String logs = output.getAll();
        assertTrue(logs.contains("field=suppressed"));
        assertTrue(logs.contains("code=SUPPRESSED_FIELDS"));
        assertFalse(logs.contains(marker));
        assertFalse(logs.contains("internalToken"));
    }

    @Test
    void validRequestGetsServerGeneratedCorrelationId()
            throws Exception {

        mvc.perform(post("/api/signups")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"Alice\","
                    + "\"email\":\"alice@example.test\","
                    + "\"seats\":2}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("X-Request-Id"))
            .andExpect(jsonPath("$.state").value("accepted"));
    }
}
```

Bộ test gồm **7 methods**: binding error, validation error, JSON parse error, query type mismatch, business rejection, suppressed field và request ID.

**Lưu ý khi dùng OutputCaptureExtension:** nó thu console output từ nhiều loggers. Một `assertFalse(output.getAll().contains(marker))` là một bài test smoke tốt cho cấu hình lab, nhưng trong project lớn cần chọn logger/application events cần quan sát hoặc dùng Logback `ListAppender`/in-memory appender có giới hạn để tránh log bootstrap từ framework hoặc tests khác. Chạy test tuần tự/cô lập khi cần vì console capture và logger có thể chia sẻ state; đừng nhầm một test “pass” với chứng minh hệ thống log collector, proxy, APM và reverse-proxy đều không capture input.

### 10.2. Chạy tests

```bash
mvn -q test
```

Thành công được xác định bằng **exit code 0**, không phải một dòng stdout Maven cố định (vì có `-q`). Chi tiết báo cáo Surefire nằm ở `target/surefire-reports/`.

Các assertions trên được thiết kế để quan sát metadata và vắng mặt của marker; runtime compilation/tests **chưa được thực thi trong bài học này**, nên cần chạy ở môi trường có JDK/Maven đúng phiên bản và cập nhật nếu framework/logging pipeline thay đổi.

### 10.3. Bổ sung test CRLF log injection

Trong một hệ thống thật, thêm test cố gắng đưa:

```text
Alice\r\nFAKE_EVENT=ADMIN_GRANTED
```

vào `username`, field name động, header hoặc request ID. Kỳ vọng **không có một event log giả** do ứng dụng tạo. Với demo, những giá trị đó không được pass cho `FailureEvents`; JSON encoder còn giúp bảo vệ log format.

Không giả định chỉ dùng placeholder `{}` đã chống mọi log injection — nếu placeholder được truyền raw string có CRLF và log là text thuần, nguy cơ vẫn có thể tồn tại.

## 11. Liên hệ các đường validation khác trong Spring MVC 6.2

### 11.1. MethodArgumentNotValidException

Với `@Valid @RequestBody SignupForm` và không có `BindingResult` liền sau, lỗi Bean Validation argument-level thường được Spring MVC nâng thành `MethodArgumentNotValidException`. Exception có `BindingResult` để bạn duyệt field errors theo object name và path.

Đừng in nguyên exception trong handler:

```java
// Không khuyến nghị nếu log tự động in rejected values.
LOG.warn("Invalid payload: {}", ex.getBindingResult());
```

Thay bằng `events.fromBindingResult(...)` dùng danh sách field/code đã allowlist.

### 11.2. HandlerMethodValidationException

Spring MVC 6.1+ hỗ trợ direct method constraints, ví dụ `@Min(1)` trên `@RequestParam int page`. Khi whole-method validation kích hoạt, exception có thể là `HandlerMethodValidationException` với các `ParameterValidationResult` chứ không phải một `BindingResult` duy nhất.

Để log an toàn:

- Dùng **route code** và parameter name do server định nghĩa, có allowlist.
- Duyệt `ParameterValidationResult` hoặc `visitResults(...)` để biết parameter nào vi phạm.
- Không log `getArgument()` hoặc chính `ConstraintViolation#getInvalidValue()`.
- Mã constraint lấy từ `ConstraintDescriptor`/error code được mapping; không dùng localized message làm code.
- Return-value validation failure có thể mang HTTP **500** thay vì 400; giữ status thực tế.

Ví dụ lab cố ý không khai báo direct constraint trên method parameter; endpoint lookup dùng **type conversion** để phân biệt ARGUMENT.

### 11.3. @ModelAttribute + BindingResult

Với form:

```java
public ResponseEntity<?> form(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

`BindingResult` đứng ngay sau form argument, nên controller có thể kiểm tra lỗi tại chỗ thay vì ném exception. Nếu `errors.hasErrors()` mà code vẫn gọi save, logger dù tốt cũng không chặn được side effect. Logging là công cụ quan sát, **không thay validation/authorization/transaction**.

### 11.4. @RequestBody JSON khác form binding

JSON body có thể bị Jackson từ chối trước Bean Validation; lỗi do `HttpMessageNotReadableException` không có một danh sách `FieldError` hoàn chỉnh để “đoán field nào”. Trong trường hợp ấy, log `field=body` và `code=INVALID_JSON` thay vì cố trích text từ parser exception.

Một JSON property sai kiểu có thể có nested Jackson path; dù path hữu ích, không log tự do bất kỳ map key hoặc array index nếu chưa lọc.

### 11.5. Spring Security errors

Authentication/authorization exceptions phát sinh trong Spring Security filter chain có thể được xử lý bởi `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`, không phải MVC advice này. Nếu cần cùng event schema, dùng một logging adapter có chính sách cho Security boundary; không đưa credentials hay access token vào log.

### 11.6. Exception đã được xử lý ở tầng khác

Nếu `@ControllerAdvice` không chạy, đừng tự kết luận “logger không hoạt động”. Request có thể bị chặn trước MVC bởi proxy, CORS/filter/security hoặc trả lỗi do server/container. Cần đặt điểm ghi log ở boundary tương ứng, tránh double-count cùng event.

## 12. Khi nào log code, khi nào log message?

Với validation, **code ổn định** tốt hơn message:

| Nguồn | Mã máy | Message cho người dùng | Ghi vào log |
| --- | --- | --- | --- |
| `@NotBlank` | `NotBlank` | “Không được bỏ trống” | Mã + field, không value |
| `@Min(1)` | `Min` | “Phải lớn hơn hoặc bằng 1” | Mã + field, không value |
| Binding sai kiểu | `typeMismatch` | “Giá trị không đúng kiểu” | Mã + stage BIND |
| JSON malformed | `INVALID_JSON` | “Body không hợp lệ” | Mã tổng quát + stage DESERIALIZE |
| Domain rule | `POLICY_DENIED` | “Yêu cầu không thể thực hiện” | Mã do ứng dụng kiểm soát |
| Lỗi nội bộ | `INTERNAL_ERROR` | “Đã xảy ra lỗi” | Mã + request ID, thông tin chi tiết ở kênh được kiểm soát |

Một custom constraint message có thể nội suy `{validatedValue}` hoặc chính dữ liệu đầu vào. Do đó **không** log `ConstraintViolation#getMessage()` mặc định. Khi cần điều tra, dùng annotation type, property path đã mapping và mã code.

Log mã lỗi cũng phải có schema/version: một team có thể đổi tên constraint hoặc model field làm dashboards vỡ. Nếu log contract là API dùng cho vận hành, duy trì mapping có version và tests như với HTTP API.

## 13. Log levels và độ ưu tiên

Không phải mọi lỗi client là một sự kiện khẩn cấp:

- **INFO:** sự kiện thông thường, ít nguy cơ, có ích cho business monitoring.
- **WARN:** input lạ, request bị từ chối, dấu hiệu abuse hoặc mismatch đáng điều tra; kiểm soát tần suất.
- **ERROR:** lỗi server/persistence không dự kiến cần cảnh báo; đừng log nguyên dữ liệu nhạy cảm.
- **DEBUG/TRACE:** chỉ bật ngắn hạn có phê duyệt cho phạm vi cụ thể; không mặc định ghi body, headers và rejected values.

Trong bài demo, `FailureEvents` dùng `WARN` cho các tình huống lỗi có kiểm soát để dễ tìm. Production phải tránh noise, ví dụ nếu một bot gửi hàng triệu request sai sẽ gây log flooding/chi phí lớn. Dùng sampling, rate limit, counters và cơ chế cảnh báo cho các patterns nguy hiểm, nhưng **đừng tắt toàn bộ security events quan trọng**.

Một log code `typeMismatch` ở API public có thể nhiều và không phải 500. Mức log nên dựa trên mục tiêu vận hành, không chỉ HTTP status.

## 14. Privacy và security của toàn log pipeline

Ứng dụng có thể không ghi input nhưng log collector khác vẫn capture dữ liệu. Khi review bảo mật, kiểm tra toàn đường:

```text
Client
  -> CDN / WAF / API Gateway / Reverse proxy
  -> Application / Spring MVC
  -> SLF4J / Logback
  -> stdout / log file
  -> agent / collector / SIEM / APM
  -> dashboards / alerts / tickets / exports
  -> backups / retention / deletion
```

Những điểm cần kiểm soát:

1. Không bật HTTP request/response body logging vô điều kiện.
2. Không thêm Authorization/Cookie/Set-Cookie headers vào MDC hoặc event metadata.
3. Tránh raw query string/path parameter trong route field.
4. Tài khoản đọc log phải có quyền tối thiểu, có audit truy cập.
5. Log transport nên được mã hóa; collectors không nhận data nhạy cảm không cần thiết.
6. Retention giới hạn theo pháp luật và mục đích; rotation/backup/export cũng phải tuân thủ.
7. Có quy trình xóa/sửa dữ liệu log khi chính sách yêu cầu, xem xét tính bất biến/retention của SIEM.
8. Dashboard và alert payload cũng không lộ values; đừng đính kèm raw event object từ một nguồn không đáng tin.
9. Test log injection với CRLF/JSON special characters và các field path động.
10. Kiểm tra các logger framework/third-party ở DEBUG/TRACE khi có incident; tắt rồi khôi phục cấu hình an toàn.
11. Không ghi database credentials, SQL parameter bindings, JWT, refresh token, session IDs.
12. Dùng HMAC/opaque IDs nếu phải liên kết user/resource, với rotation và access restrictions.

**Privacy by design không chỉ là regex thay password bằng dấu sao.** Redaction sau khi lỡ log có thể bỏ sót alias của secrets, encoded values hoặc nested objects. Hạn chế **tạo ra dữ liệu nhạy cảm trong log ngay từ nguồn** hiệu quả hơn.

## 15. Lỗi thường gặp khi áp dụng

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Log có mật khẩu sau validation lỗi | In `getRejectedValue()` hoặc nguyên `BindingResult` | Chỉ log object/field/code đã mapping |
| Log lộ cả raw JSON | In `HttpMessageNotReadableException#getMessage()` | Ghi `DESERIALIZE/INVALID_JSON`, không ghi exception detail |
| Stage luôn là VALIDATE | Không xét `FieldError#isBindingFailure()` | Tách BIND và VALIDATE |
| Không xác định được lỗi thuộc request nào | Không có correlation ID | UUID/traceId do server kiểm soát, dọn MDC |
| Log có nhiều dòng giả | Raw CRLF trong input/token | Structured JSON, allowlist, length bounds |
| Mỗi request ID giống nhau hoặc bị lẫn | Quên `MDC.remove()` trong thread pool | Dọn context bằng `finally` |
| @Async logs không có requestId | MDC ThreadLocal không propagate | Dùng framework context propagation/tracing |
| Object name vô tình chứa PII | Ghi raw model object name | Mapping sang mã loại object cố định |
| Field path chứa email/map key | Log `getField()` không lọc | Mapping paths theo schema hoặc token `other` |
| Có log application an toàn nhưng proxy vẫn lộ URL | Proxy access log lưu query raw | Kiểm soát toàn pipeline |
| Test chỉ assert HTTP 400 | Không kiểm tra event/log leak | Kiểm tra stage/code và marker không xuất hiện |
| Log vô tình chứa exception stack | Truyền `ex` làm cuối logger | Chỉ log metadata; controlled diagnostics riêng |
| Log có mã enum không ổn định | Trộn tên class với public error code | Định nghĩa schema log tường minh |
| Form fields bị suppress mà không log gì | `hasErrors()` có thể false | Kiểm tra `getSuppressedFields()` riêng |
| Tất cả lỗi bị trả 500 | Catch-all generic exception handler | Phân loại input vs server error, giữ status |
| Log thành quá tải | WARN cho mỗi invalid request trong API public | Điều chỉnh level, sampling và monitoring |
| JSON logging được bật nhưng vẫn lộ token | Truyền raw input vào JSON fields | Data minimization trước serializer |
| Lỗi logging làm request thất bại thêm | Helper nhận null hoặc dữ liệu lạ không xử lý | Null guard, allowlist, resilient logger |

## 16. Checklist triển khai thực tế

1. Mỗi event có **tên sự kiện ổn định** (ví dụ `INPUT_FAILURE`).
2. Route được ghi bằng **tên route/template do server kiểm soát**, không raw request URI.
3. Object code là một mã loại object, không tự động là database ID.
4. Field path được allowlist; nested path/map key/index có quy tắc canonicalization riêng.
5. Stage chỉ có enum xác định: BIND/VALIDATE/DESERIALIZE/ARGUMENT/POLICY.
6. Mã lỗi có danh sách được duyệt và fallback `OTHER`.
7. Không ghi `rejectedValue`, validation message nội suy, raw body, HTTP authorization headers, session ID, cookies, SQL parameters.
8. Correlation ID có format/ownership rõ; từ server hoặc trusted gateway.
9. MDC được dọn trong `finally`; có strategy cho async/thread hopping.
10. HTTP status và error body được trả nhất quán nhưng **không chứa dữ liệu nhạy cảm**.
11. Với form binding, check cả `hasErrors()` và `getSuppressedFields()`.
12. Với JSON, phân biệt lỗi parsing và Bean Validation.
13. Với Spring MVC 6.1+, tính đến `HandlerMethodValidationException`.
14. Với Spring Security, ghi events ở đúng filter/security boundary.
15. Dùng structured logger/JSON encoder, kiểm thử CRLF/log injection.
16. Có tests cho marker không xuất hiện trong logs, và tests cho stage/field/code đúng.
17. Xác minh không có logging body/header ở reverse proxy, gateway, APM và logging agent.
18. Có retention/access/audit phù hợp cho tập log đã tạo.
19. Có kế hoạch thay đổi log schema/version mà không phá dashboards.
20. Chỉ bật verbosity cao tạm thời theo quy trình, không để DEBUG/TRACE chạy mãi trong production.

## 17. Tổng kết

Để chẩn đoán lỗi Spring MVC mà vẫn bảo vệ quyền riêng tư, hãy lưu **mã loại đối tượng**, **đường dẫn field đã được phép công bố**, **giai đoạn lỗi**, **mã lỗi ổn định**, **HTTP status**, **route template** và **request ID** do hệ thống kiểm soát. Các metadata này trả lời được “lỗi ở đâu và vì sao” mà không cần in dữ liệu khách hàng.

Trong Spring, `BindingResult` cung cấp `getObjectName()`, `FieldError#getField()`, `getCode()` và `isBindingFailure()`; nhưng `getRejectedValue()`, `getDefaultMessage()`, `getTarget()` và exception messages có thể chứa dữ liệu nhạy cảm. Dùng allowlist, enum, structured logging và correlation filter có lifecycle rõ ràng. Kiểm thử cả các trường hợp binding, validation, JSON parsing, argument conversion và business rejection, rồi xác minh các input marker không xuất hiện trong **application log messages**.

**Ghi đủ để vận hành, không ghi quá mức cần thiết.** Một logging event tốt là event có cấu trúc, truy vết được, được bảo vệ quyền truy cập và không biến một lỗi người dùng thành sự cố rò rỉ dữ liệu.

## Tài liệu tham khảo

- OWASP Logging Cheat Sheet — thiết kế event attributes, data to exclude, log injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Sensitive Data Exposure / Security Logging principles: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude
- Spring Framework 6.2 — MVC validation, MethodArgumentNotValidException và HandlerMethodValidationException: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC error responses / RFC 9457: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — `ResponseEntityExceptionHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 — `BindingResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 — `FieldError` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/FieldError.html
- Spring Boot 3.5 — Logging (structured ECS, SLF4J and Logback): https://docs.spring.io/spring-boot/3.5/reference/features/logging.html
- Spring Boot 3.5 — Tracing and correlation IDs: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- SLF4J manual — parameterized logging and MDC: https://www.slf4j.org/manual.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457