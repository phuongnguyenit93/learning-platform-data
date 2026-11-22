# Quốc tế hóa thông báo cùng mã lỗi ổn định

## 1. Một lỗi, nhiều ngôn ngữ nhưng chỉ một ý nghĩa nghiệp vụ

API tạo khách hàng có hai nhóm client: ứng dụng tiếng Việt và một đối tác dùng tiếng Anh. Khi email đã thuộc một khách hàng trong cùng tenant, cả hai client cần nhận ra **cùng một tình huống nghiệp vụ** để hiển thị cảnh báo, dừng retry hoặc chuyển sang quy trình xử lý khác. Nhưng thông báo cho con người nên phù hợp với ngôn ngữ người dùng.

~~~http
POST /api/customers HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json, application/problem+json
Accept-Language: vi-VN,vi;q=0.9,en;q=0.7
Content-Type: application/json

{"email":"existing@example.test","displayName":"Nguyễn An"}
~~~

Server trả **409 Conflict**, với `code: CUSTOMER_ALREADY_EXISTS` bất kể ngôn ngữ. Nếu client gửi `Accept-Language: en`, server có thể đổi `title/detail` sang tiếng Anh nhưng **không đổi mã lỗi, HTTP status hoặc định danh loại vấn đề**.

Trong chương **Dữ liệu và lỗi Spring** của module **INTEGRATION_API_REST**, bài này kết hợp thiết kế resource/URI, HTTP methods/status, hợp đồng dữ liệu, Problem Details, validation, xác thực/phân quyền, OpenAPI và kiểm thử bằng Java/Spring Boot.

Sau bài học, bạn có thể:

1. Thiết kế mã lỗi ổn định để client xử lý theo **máy trạng thái**, không phân tích câu chữ.
2. Quốc tế hóa `title`, `detail` và lỗi từng trường qua **`MessageSource`**.
3. Đàm phán ngôn ngữ với **`Accept-Language`**, phản hồi `Content-Language` và fallback dự đoán được.
4. Ánh xạ lỗi Spring MVC, Bean Validation, ràng buộc dữ liệu và security sang HTTP status/Problem Details đúng ngữ nghĩa.
5. Công bố OpenAPI, kiểm thử nhiều locale, bảo vệ dữ liệu nhạy cảm và quản trị vòng đời mã lỗi.

> **Nguyên tắc:** **Mã lỗi là hợp đồng cho chương trình; thông báo là nội dung cho con người.** Đổi ngôn ngữ hoặc cải thiện lời giải thích không được khiến client rơi sang một nhánh xử lý nghiệp vụ khác.

## 2. Hợp đồng lỗi: thành phần ổn định và bản dịch

| Trường | Ví dụ | Khi đổi locale |
|---|---|---|
| **HTTP status** | `409` | **Không đổi** |
| **`type`** | `.../customer-already-exists` | **Không đổi** |
| **`code`** *(extension của API)* | `CUSTOMER_ALREADY_EXISTS` | **Không đổi** |
| **`title/detail`** | “Khách hàng đã tồn tại” | **Dịch được** |
| **`violations[].field/code`** | `displayName/FIELD_REQUIRED` | **Không đổi** |
| **`violations[].message`** | “Trường bắt buộc.” | **Dịch được** |
| `traceId` nếu có | Correlation ID | Không đổi, dùng để tra log |

**RFC 9457** quy định `type/title/status/detail/instance` của `application/problem+json`; **`code/violations` không phải trường chuẩn** mà do API tự bổ sung và phải có trong OpenAPI. `title` là tóm tắt vấn đề, chỉ nên thay đổi giữa các lần xuất hiện khi **localization**; `detail` có thể mô tả hoàn cảnh cụ thể.

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Content-Language: vi-VN
Cache-Control: no-store

{"type":"https://api.example.test/problems/customer-already-exists",
 "title":"Khách hàng đã tồn tại","status":409,
 "detail":"Đã có khách hàng với thông tin định danh này.",
 "code":"CUSTOMER_ALREADY_EXISTS"}
~~~

Với `Accept-Language: en`, status/type/code giữ nguyên, nhưng `title="Customer already exists"` và `detail="A customer with this identifier already exists."`. **SDK không được phân nhánh bằng cách so sánh title/detail đã dịch**.

## 3. HTTP status và mã lỗi nghiệp vụ phải nhất quán

| HTTP | Khi nào | Code tham khảo |
|---|---|---|
| **400** | Body/field không hợp lệ theo policy | `REQUEST_VALIDATION_FAILED` |
| **401/403** | Thiếu credential / thiếu quyền | `AUTHENTICATION_REQUIRED` / `ACCESS_DENIED` |
| **404** | Resource không có hoặc không được tiết lộ | `RESOURCE_NOT_FOUND` |
| **409** | Xung đột trạng thái/unique business rule | `CUSTOMER_ALREADY_EXISTS` |
| **412** | `If-Match` không thỏa | `PRECONDITION_FAILED` |
| **422** | Nội dung hợp cú pháp nhưng không xử lý được theo policy | `BUSINESS_RULE_VIOLATION` |
| **429/503** | Vượt hạn mức / tạm không khả dụng | `RATE_LIMIT_EXCEEDED` / `SERVICE_UNAVAILABLE` |
| **500** | Lỗi không dự kiến | `INTERNAL_ERROR` |

Quyết định **400/422** cho semantic validation cần nhất quán trong contract. **401 phải giữ `WWW-Authenticate` challenge** khi phương thức authentication yêu cầu; 429 có thể kèm `Retry-After`. Không trả **200 OK** chứa mã `ERROR` cho request thất bại, và không biến mọi database exception thành 409: phải phân loại nguyên nhân thực.

## 4. `Accept-Language`, `Content-Language` và fallback

~~~http
Accept-Language: vi-VN,vi;q=0.9,en;q=0.6
~~~

Giả sử API hỗ trợ `vi-VN/vi/en`, mặc định `vi-VN`:

| Request | Ngôn ngữ phản hồi |
|---|---|
| `vi-VN` | `vi-VN` |
| `en` | `en` |
| `fr-FR` không hỗ trợ hoặc không gửi | `vi-VN` |

Dùng **`Content-Language`** chỉ ngôn ngữ thực tế. Response cache được theo locale cần **`Vary: Accept-Language`**; với lỗi cá nhân, chọn **`Cache-Control: no-store`**. `Accept-Language` không phải nguồn xác định quyền, tenant, business state hay giá. Không đưa raw header vào metric labels.

**Dữ liệu máy không dịch:** JSON `amountMinor:150000`, `currency:"VND"`, timestamp UTC/ISO 8601 và enum/error codes phải giữ định dạng hợp đồng. Thông báo cho người có thể định dạng số/ngày theo locale, nhưng chỉ chèn tham số đã chọn lọc, tránh echo input nhạy cảm, token hoặc SQL. Locale không hỗ trợ phải fallback **dự đoán được**, không khiến API ném 500.

## 5. Catalog thông báo khác với public error code

~~~text
CUSTOMER_ALREADY_EXISTS                  # public stable machine code
  HTTP 409, type: .../customer-already-exists
  title key: error.customer.exists.title
  detail key: error.customer.exists.detail
    vi: Khách hàng đã tồn tại
    en: Customer already exists
~~~

**`error.customer.exists.title`** là key của **bundle nội bộ**, có thể đổi cấu trúc khi refactor. **`CUSTOMER_ALREADY_EXISTS`** thuộc contract công khai, phải giữ ý nghĩa ổn định.

Nên quản lý registry `(code, HTTP status, type URI, message keys, client action)`. Ví dụ `REQUEST_VALIDATION_FAILED` yêu cầu sửa input; `VERSION_CONFLICT` yêu cầu đọc lại resource; `RATE_LIMIT_EXCEEDED` dùng backoff/`Retry-After`; `INTERNAL_ERROR` chỉ trả chi tiết an toàn. **Không tái sử dụng code cho ý nghĩa khác**, không lấy class name hoặc `Exception.getMessage()` làm public code.

## 6. Spring Boot 3: `MessageSource` và `LocaleResolver`

Dùng resource bundles trong `src/main/resources/i18n/`. `errors.properties` làm catalog tiếng Anh mặc định, `errors_vi.properties` có bản dịch Việt:

~~~yaml
spring:
  messages:
    basename: i18n/errors
    encoding: UTF-8
~~~

~~~properties
# errors.properties (fallback English)
error.customer.exists.title=Customer already exists
error.customer.exists.detail=A customer with this identifier already exists.
error.validation.title=Invalid request
error.validation.detail=Please correct the indicated fields.
error.field.required=This field is required.
error.field.format=Invalid field format.
error.field.length=Invalid field length.
error.field.invalid=Invalid field value.
~~~

~~~properties
# errors_vi.properties
error.customer.exists.title=Khách hàng đã tồn tại
error.customer.exists.detail=Đã có khách hàng với thông tin định danh này.
error.validation.title=Yêu cầu không hợp lệ
error.validation.detail=Hãy sửa các trường được chỉ ra.
error.field.required=Trường bắt buộc.
error.field.format=Định dạng trường không hợp lệ.
error.field.length=Độ dài trường không hợp lệ.
error.field.invalid=Giá trị trường không hợp lệ.
~~~

REST API thường dùng `AcceptHeaderLocaleResolver` thay vì session/cookie:

~~~java
import java.util.List;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
class ApiLocaleConfiguration {
    @Bean
    LocaleResolver localeResolver() {
        var resolver = new AcceptHeaderLocaleResolver();
        resolver.setSupportedLocales(List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("vi"),
            Locale.ENGLISH));
        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }
}
~~~

Trong advice, `messages.getMessage(key, null, locale)` tra theo locale. Khi thiếu key, phương thức này có thể ném `NoSuchMessageException`; cần **kiểm tra catalog/placeholder ở CI** và fallback an toàn ở runtime, không lộ raw key/stack. `MessageFormat` có placeholder `{0}`, lưu ý quote và locale, không đưa input nguy hiểm vào message.

`AcceptHeaderLocaleResolver` không cho đổi locale qua `setLocale`; tránh ghép với `LocaleChangeInterceptor` dựa trên query parameter nếu không đổi chiến lược resolver.

## 7. Domain exception không được gắn sẵn bản dịch

~~~java
import java.net.URI;
import java.util.UUID;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record CreateCustomerRequest(
    @NotBlank @Email String email,
    @NotBlank String displayName) {}
record CustomerView(UUID id, String displayName) {}

class CustomerAlreadyExistsException extends RuntimeException {}

interface CustomerService {
    CustomerView createForCaller(
        Authentication caller, CreateCustomerRequest request);
}

@RestController
@RequestMapping("/api/customers")
class CustomerController {
    private final CustomerService service;
    CustomerController(CustomerService service) { this.service = service; }

    @PostMapping
    ResponseEntity<CustomerView> create(
        Authentication principal,
        @Valid @RequestBody CreateCustomerRequest request) {
        CustomerView customer = service.createForCaller(principal, request);
        return ResponseEntity.created(
            URI.create("/api/customers/" + customer.id())).body(customer);
    }
}
~~~

**Service** kiểm tra business rule theo tenant từ principal đã xác thực, ném **domain exception ổn định**; **advice** quyết định HTTP status, mã và bản dịch. Không nên để domain/service phụ thuộc locale hoặc tự tạo câu thông báo. Đây là skeleton, chưa có DB/security config và không phải mã đã chạy.

## 8. `@RestControllerAdvice`: ánh xạ lỗi domain và Bean Validation

Ví dụ dưới đây minh họa Spring 6 / Spring Boot 3. `ProblemDetail` là kiểu hỗ trợ RFC 9457, còn `code`/`violations` là **extension của ứng dụng**.

~~~java
import java.net.URI;
import java.util.List;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record Violation(String field, String code, String message) {}

@RestControllerAdvice
class ApiProblemAdvice {
    private static final String BASE =
        "https://api.example.test/problems/";
    private final MessageSource messages;

    ApiProblemAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(CustomerAlreadyExistsException.class)
    ResponseEntity<ProblemDetail> customerExists(
            CustomerAlreadyExistsException ex, Locale locale) {
        return problem(HttpStatus.CONFLICT,
            "customer-already-exists", "CUSTOMER_ALREADY_EXISTS",
            "error.customer.exists.title",
            "error.customer.exists.detail", locale);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> requestInvalid(
            MethodArgumentNotValidException ex, Locale locale) {
        ResponseEntity<ProblemDetail> response = problem(
            HttpStatus.BAD_REQUEST,
            "request-validation-failed", "REQUEST_VALIDATION_FAILED",
            "error.validation.title", "error.validation.detail", locale);

        List<Violation> violations = ex.getBindingResult()
            .getFieldErrors().stream()
            .map(error -> violation(error, locale))
            .toList();
        response.getBody().setProperty("violations", violations);
        return response;
    }

    private Violation violation(FieldError error, Locale locale) {
        // Spring validation codes có thể theo thứ tự:
        // NotBlank.createCustomerRequest.displayName, ... , NotBlank
        String[] codes = error.getCodes();
        String rule = (codes == null || codes.length == 0)
            ? "Invalid" : codes[codes.length - 1];
        String code = switch (rule) {
            case "NotBlank", "NotNull", "NotEmpty" -> "FIELD_REQUIRED";
            case "Email", "Pattern" -> "FIELD_FORMAT_INVALID";
            case "Size" -> "FIELD_LENGTH_INVALID";
            default -> "FIELD_INVALID";
        };
        String messageKey = switch (code) {
            case "FIELD_REQUIRED" -> "error.field.required";
            case "FIELD_FORMAT_INVALID" -> "error.field.format";
            case "FIELD_LENGTH_INVALID" -> "error.field.length";
            default -> "error.field.invalid";
        };

        // Chỉ dùng các tên trường công khai trong request DTO.
        String field = switch (error.getField()) {
            case "email", "displayName" -> error.getField();
            default -> "request";
        };
        return new Violation(field, code,
            messages.getMessage(messageKey, null, locale));
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus httpStatus, String typeSuffix, String code,
            String titleKey, String detailKey, Locale locale) {
        ProblemDetail body = ProblemDetail.forStatus(httpStatus);
        body.setType(URI.create(BASE + typeSuffix));
        body.setTitle(messages.getMessage(titleKey, null, locale));
        body.setDetail(messages.getMessage(detailKey, null, locale));
        body.setProperty("code", code);
        return ResponseEntity.status(httpStatus)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .header(HttpHeaders.CONTENT_LANGUAGE, locale.toLanguageTag())
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

### Điều mã trên bảo đảm và điều chưa bảo đảm

- Mã **`CUSTOMER_ALREADY_EXISTS`** luôn gắn với HTTP 409/type cố định, dù `title/detail` đổi theo locale.
- Với `@Valid @RequestBody`, lỗi Bean Validation thông thường tạo **`MethodArgumentNotValidException`**; `violations` sử dụng **field/code ổn định** và message đã dịch.
- **Không trả `rejectedValue`**, raw exception message hoặc internal property path. `FieldError.getCodes()` chứa nhiều mức mã; ví dụ lấy phần tử cuối theo convention Spring và **fallback** `FIELD_INVALID` cho custom constraint chưa được map.
- Chỉ xử lý **hai loại exception minh họa**. Lỗi parse JSON, type conversion của query/path, method parameter validation, 404, 405 và lỗi bảo mật có **đường xử lý riêng**; không mặc định chúng đều đi qua method này.
- Chưa có common logger, trace ID, catalog fallback khi thiếu key, hay translation tests. Với code production cần logging có correlation ID, ánh xạ lỗi ở mọi boundary và xử lý exception an toàn.

Ví dụ JSON validation với `displayName` rỗng:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Content-Language: vi-VN

{
  "type": "https://api.example.test/problems/request-validation-failed",
  "title": "Yêu cầu không hợp lệ",
  "status": 400,
  "detail": "Hãy sửa các trường được chỉ ra.",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {"field":"displayName","code":"FIELD_REQUIRED","message":"Trường bắt buộc."}
  ]
}
~~~

**Lưu ý Bean Validation:** `@NotBlank`, `@Email`, `@Size` kiểm tra những điều khác nhau; ràng buộc đặt trên DTO phải tương ứng hợp đồng. Trong Spring Framework 6.1+, validation của method parameters cũng có thể tạo `HandlerMethodValidationException`; `@RequestParam` sai kiểu có thể tạo `MethodArgumentTypeMismatchException`. Để toàn bộ API đồng nhất, xây mapping/handler riêng cho các exception này thay vì chỉ kiểm tra `MethodArgumentNotValidException`.

## 9. Lỗi Spring Data: phân loại trước khi dịch

Ví dụ database bảo đảm email duy nhất **trong tenant**:

~~~sql
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_customer_tenant_email
        UNIQUE (tenant_id, normalized_email)
);
~~~

Hai request đồng thời có thể đều đọc “chưa tồn tại”, nhưng một `INSERT` vẫn vi phạm constraint. Spring Data/JPA có thể báo `DataIntegrityViolationException`; **không được ánh xạ mọi exception này sang CUSTOMER_ALREADY_EXISTS** vì nó còn bao gồm foreign key, CHECK và not-null violations.

**Quy trình:** xác định đúng `uq_customer_tenant_email` qua cơ chế phù hợp DB → ném domain `CustomerAlreadyExistsException` → advice trả **409 + stable code + localized text**. Nếu không chứng minh được nguyên nhân, dùng lỗi server **an toàn** và correlation ID; không lộ SQL, tên bảng, rejected values. Lỗi constraint có thể xuất hiện lúc **flush/commit**, nên đặt exception translation ở ranh giới transaction phù hợp, không chỉ bọc `repository.save`.

## 10. Bảo mật: lỗi 401/403 có thể phát sinh trước MVC Advice

Spring Security thường xử lý thiếu credential và cấm truy cập **trong filter chain**, trước controller. Cần thống nhất schema bản địa hóa qua `AuthenticationEntryPoint` và `AccessDeniedHandler`, không chỉ `@RestControllerAdvice`:

~~~java
// Mảnh cấu hình HttpSecurity, chưa phải SecurityFilterChain đầy đủ.
http.exceptionHandling(errors -> errors
    .authenticationEntryPoint((request, response, ex) ->
        securityProblemWriter.write(request, response,
            401, "AUTHENTICATION_REQUIRED"))
    .accessDeniedHandler((request, response, ex) ->
        securityProblemWriter.write(request, response,
            403, "ACCESS_DENIED")));
~~~

`securityProblemWriter` là thành phần ứng dụng: dùng cùng registry, MessageSource, **supported-locale resolver**, Problem Details, `Content-Language` và serializer an toàn. **401 Bearer phải giữ `WWW-Authenticate` challenge đúng theo auth mechanism**; không thay entry point của OAuth2 Resource Server rồi làm mất header quan trọng.

- **Account enumeration:** endpoint đăng ký công khai không nên báo chi tiết “email đã tồn tại”; ví dụ quản lý customer giả định caller có quyền trong tenant.
- **BOLA:** lỗi 403/404 không được vô tình tiết lộ resource của tenant khác qua bản dịch.
- **Không echo:** tránh password, token, SQL, stack trace, `rejectedValue` và PII trong `detail`/`violations`.
- **Client rendering:** coi title/detail là text, escape khi đưa lên UI; không chèn như HTML.
- **Locale và code không cấp quyền:** backend vẫn xác thực và kiểm tra authorization từng request.

## 11. OpenAPI 3.1: công bố code và bản địa hóa

~~~yaml
openapi: 3.1.0
info: {title: Customers API, version: 1.0.0}
paths:
  /api/customers:
    post:
      security:
        - BearerAuth: []
      parameters:
        - name: Accept-Language
          in: header
          description: Hỗ trợ vi-VN, vi, en; fallback vi-VN
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [email, displayName]
              properties:
                email: {type: string, format: email}
                displayName: {type: string, minLength: 1}
      responses:
        '201': {description: Tạo khách hàng thành công}
        '400':
          description: Validation không hợp lệ
          headers:
            Content-Language:
              schema: {type: string}
          content:
            application/problem+json:
              schema: {$ref: '#/components/schemas/ApiProblem'}
        '401':
          description: Thiếu credential hợp lệ
          headers:
            WWW-Authenticate:
              schema: {type: string}
        '403': {description: Không có quyền}
        '409':
          description: Khách hàng đã tồn tại
          headers:
            Content-Language:
              schema: {type: string}
          content:
            application/problem+json:
              schema: {$ref: '#/components/schemas/ApiProblem'}
components:
  securitySchemes:
    BearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}
  schemas:
    ApiProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        instance: {type: string, format: uri-reference}
        code: {type: string, description: Mã máy không dịch}
        violations:
          type: array
          items: {$ref: '#/components/schemas/Violation'}
    Violation:
      type: object
      required: [field, code, message]
      properties:
        field: {type: string}
        code: {type: string}
        message: {type: string}
~~~

**`code` và `violations` là extension riêng**, không được RFC 9457 bảo đảm; `required` ở đây cũng là profile API chặt hơn quy tắc tổng quát. Trong production, bổ sung Problem schema cho 401/403/404/422/429/500, header `Retry-After` khi 429, `Vary: Accept-Language` nếu cache theo locale, cùng **bảng registry code/type/client action**. OpenAPI chỉ mô tả, không tự thực thi security hay dịch text.

## 12. Kiểm thử locale và hợp đồng lỗi

### MockMvc: text thay đổi nhưng machine code giữ nguyên

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiErrorI18nTest {
    @Autowired MockMvc mvc;
    private static final String INVALID_BODY =
        "{\"email\":\"valid@example.test\",\"displayName\":\"\"}";

    @Test @WithMockUser
    void viValidation() throws Exception {
        mvc.perform(post("/api/customers")
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INVALID_BODY))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(HttpHeaders.CONTENT_LANGUAGE, "vi-VN"))
            .andExpect(jsonPath("$.code").value("REQUEST_VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].code").value("FIELD_REQUIRED"))
            .andExpect(jsonPath("$.violations[0].message")
                .value("Trường bắt buộc."));
    }

    @Test @WithMockUser
    void enValidationKeepsCode() throws Exception {
        mvc.perform(post("/api/customers")
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INVALID_BODY))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(HttpHeaders.CONTENT_LANGUAGE, "en"))
            .andExpect(jsonPath("$.code").value("REQUEST_VALIDATION_FAILED"))
            .andExpect(jsonPath("$.violations[0].code").value("FIELD_REQUIRED"))
            .andExpect(jsonPath("$.violations[0].message")
                .value("This field is required."));
    }
}
~~~

Đây là **skeleton**, cần controller/advice, bundle, principal đúng quyền và `spring-security-test`; không khẳng định đã chạy. `@NotBlank` chặn request trước khi gọi service, trong khi business 409 cần fixture/service hoặc DB thật.

| Test cần bổ sung | Bất biến |
|---|---|
| Không header / `fr-FR` | Fallback `vi-VN`, không lỗi thiếu bundle |
| q-values | Chọn locale trong supported list đúng policy |
| `@Email/@Size`, JSON malformed, query type mismatch | Code ổn định, Problem Details, không lộ input |
| Insert trùng dưới concurrency | Unique DB bảo vệ; mapped 409 đúng business rule |
| 401 Bearer, 403/404 cross-tenant | Challenge đúng; không lộ PII/resource |
| 429, 500 | Retry-After/HTTP semantics; chi tiết 500 an toàn |
| Catalog thiếu key / placeholder lỗi | CI fail hoặc fallback an toàn |
| OpenAPI/schema/client SDK | `status/type/code` khớp runtime |

**Ưu tiên assert status/type/code**, kiểm tra một số bản dịch và `Content-Language`; không biến việc sửa dấu câu thành breaking change. Có thể kiểm tra **catalog completeness** và placeholder bằng test riêng. MockMvc không thay thế database-concurrency/security integration tests.

## 13. Quản trị lỗi và quan sát bằng code ổn định

- **Đổi wording/tiếng Việt/tiếng Anh** hoặc thêm locale không được đổi `status/type/code`.
- **Không tái sử dụng code cũ cho ý nghĩa mới.** Tách một lỗi thành nhiều mã cần compatibility plan, SDK tests và changelog.
- Đổi HTTP status, Problem schema, extension `violations` hoặc public type URI là **thay đổi hợp đồng**, không chỉ sửa bản dịch.
- Catalog có owner/review, kiểm tra key và placeholders; trang tài liệu của problem type nên giữ URI ổn định.
- Ghi metrics theo **code + HTTP status + route template**, correlation/trace ID có quyền phù hợp; **không dùng localized detail, token, email hoặc rejected value làm labels**.

Khi cần điều tra, log nội bộ giữ stack/constraint có kiểm soát, response cho client chỉ chứa text an toàn và trace ID nếu được phép. Không có tính năng Spring tự bảo đảm lifecycle của public error codes — tổ chức phải quản trị registry đó.

## 14. Bài tập: cùng lỗi, ba ngôn ngữ

API **POST /api/members** nhận `email`, `displayName`, `inviteCode`, chỉ admin tenant được gọi. Client A chọn `vi-VN`, B chọn `en`, C chọn `ja-JP` (chưa hỗ trợ). Email phải duy nhất theo tenant; inviteCode sai bị từ chối trước ghi DB.

**Yêu cầu:** (1) Chọn status/type/code/text cho email trùng ở A/B; (2) xử lý C; (3) mô tả validation cho displayName rỗng; (4) nói vì sao không dịch nguyên DB exception; (5) xử lý 401; (6) đề xuất sáu tests có concurrency/security.

### Đáp án gợi ý

1. A/B đều **409 + `type=.../member-already-exists` + `MEMBER_ALREADY_EXISTS`**; chỉ title/detail đổi ngôn ngữ. Với đăng ký công khai cần chống enumeration.
2. C fallback **vi-VN**, phản hồi `Content-Language: vi-VN`.
3. **400 `REQUEST_VALIDATION_FAILED`**, `violations: [{field:"displayName",code:"FIELD_REQUIRED",message:"Trường bắt buộc."}]`. Invite code không hợp lệ có thể dùng 400/422 với `INVITE_CODE_INVALID` theo contract và không lộ thông tin khác tenant.
4. DB error có thể chứa SQL/PII, không ổn định giữa DB/version; phải xác định constraint rồi ánh xạ domain code.
5. 401 có thể phát ở Spring Security Filter; cần entry point và **`WWW-Authenticate`** đúng chuẩn.
6. Test vi/en/fallback, catalog completeness, validation, unique constraint hai request cạnh tranh, 401 challenge, cross-tenant 403/404, không lộ PII và OpenAPI schema.

## 15. Checklist production

- [ ] HTTP status, `type`, `code`, field names và enum máy **không dịch**; title/detail/field messages có locale rõ.
- [ ] `Accept-Language` có supported list/fallback; response báo `Content-Language`; caching/privacy đúng policy.
- [ ] MessageSource bundles UTF-8, key/placeholder được kiểm tra; không trả raw key khi thiếu bản dịch.
- [ ] Domain + Spring Data constraint được **phân loại đúng trước khi dịch**, không map mọi DB exception thành conflict.
- [ ] `@Valid`/request body, type conversion, method validation và business exceptions có mapping thống nhất.
- [ ] Security 401/403 từ filter chain dùng error contract, **401 giữ auth challenge**, không lộ resource/tenant.
- [ ] RFC 9457 và extension `code/violations` có OpenAPI; SDK rẽ nhánh bằng code chứ không parse thông báo.
- [ ] MockMvc và integration tests bao phủ locale, concurrency, fallback, auth, 429/500, schema và dữ liệu nhạy cảm.
- [ ] Dashboard theo error code/status, không dùng lời văn hay PII làm metric labels; code có owner và compatibility plan.

**Kết luận:** REST API đa ngôn ngữ cần **một lớp mã lỗi cho máy ổn định** và **một lớp thông báo cho người có thể bản địa hóa**. `MessageSource`, `LocaleResolver`, `ProblemDetail` và `@RestControllerAdvice` trong Spring hỗ trợ triển khai; tính đúng phụ thuộc vào **phân loại domain, DB constraints, security và contract tests**.

### Tài liệu nền

- **RFC 9457, RFC 9110:** Problem Details, HTTP status, language negotiation và authentication challenge.
- **Spring Framework/Boot:** MessageSource, AcceptHeaderLocaleResolver, Bean Validation, ProblemDetail, MVC Advice.
- **Spring Data, Spring Security, Jakarta Validation:** constraint translation, authentication và validation.
- **OpenAPI 3.1:** schema application/problem+json và security schemes.

