# Thiết kế phản hồi JSON hoặc ProblemDetail trong thành phần xử lý lỗi Spring Security Servlet

## 1. Mục tiêu: lỗi bảo mật cũng là một phần của hợp đồng API

Khi xây REST API bằng **Spring Boot 3.x, Spring Security 6.x, Java 17+ trên Servlet stack**, một endpoint có thể bị từ chối **trước khi controller được gọi**. Vì vậy, chỉ cấu hình `@RestControllerAdvice` để biến exception thành JSON thường **không đủ** nếu muốn định dạng nhất quán cho lỗi authentication và authorization.

Hai tình huống quan trọng nhất:

- **401 Unauthorized**: request cần authentication hợp lệ, nhưng chưa có credentials, credentials sai/hết hạn hoặc chưa xác thực được theo chính sách. Với HTTP Basic phải trả challenge `WWW-Authenticate` phù hợp; với Bearer có quy tắc challenge khác.
- **403 Forbidden**: request đã được nhận diện nhưng không có quyền thực hiện thao tác, hoặc một cơ chế bảo vệ khác như CSRF từ chối. Không nên coi mọi 403 đều do thiếu role.

Trong Spring Security Servlet:

- `AuthenticationEntryPoint` **khởi phát quá trình xác thực hoặc phản hồi khi chưa xác thực**. Với REST, nó có thể trả 401 JSON/ProblemDetail thay cho redirect tới trang login.
- `AccessDeniedHandler` **xử lý AccessDeniedException** theo đường đi phù hợp, thường trả 403 cho principal đã được xác thực nhưng thiếu quyền.
- `ExceptionTranslationFilter` kết nối các security exceptions từ các filter sau nó đến entry point hoặc denied handler, nhưng **không bắt mọi exception từ mọi vị trí trong filter chain**.
- `BasicAuthenticationFilter` cũng có thể dùng một entry point riêng khi HTTP Basic credentials không hợp lệ; nếu muốn response đồng nhất phải cấu hình đúng điểm này.
- `@RestControllerAdvice` chủ yếu xử lý lỗi phát sinh trong **Spring MVC handler processing**. Một lỗi do security filter chặn **trước DispatcherServlet** không mặc nhiên đi qua advice.

Mục tiêu bài là thiết kế **một hợp đồng lỗi ổn định, đúng HTTP semantics, ít lộ dữ liệu**, áp dụng được cho frontend và client API, đồng thời phân biệt **JSON tùy chỉnh** với **ProblemDetail theo RFC 9457**.

## 2. Luồng request và vị trí xử lý lỗi

~~~text
HTTP Client
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy / FilterChainProxy
    |
    +-- Authentication filters (Basic, Bearer, form, ...)
    |       |
    |       +-- Credentials invalid?
    |             -> AuthenticationEntryPoint (được filter sử dụng)
    |
    +-- CsrfFilter, CORS, request constraints, ...
    |       |
    |       +-- Một số lỗi có handler riêng
    |
    +-- ExceptionTranslationFilter
    |       |
    |       +-- Bắt các AuthenticationException/AccessDeniedException
    |           từ thành phần ở phía downstream khi thuộc phạm vi
    |       |
    |       +-- Chưa xác thực -> AuthenticationEntryPoint
    |       +-- Đã xác thực, thiếu quyền -> AccessDeniedHandler
    |
    +-- AuthorizationFilter
    |       |
    |       +-- Authorized -> DispatcherServlet -> Controller
    |       +-- Denied     -> ExceptionTranslationFilter
    |
    v
Spring MVC / Controller / Service
    |
    +-- Lỗi thuộc MVC handler pipeline
    |      -> @ExceptionHandler / @RestControllerAdvice
    |
    v
HTTP Response
~~~

Sơ đồ có chủ đích **không trình bày thứ tự của tất cả filter**: vị trí cụ thể tùy phiên bản/cấu hình. Ý chính là lỗi trong security filter chain và lỗi trong MVC **không mặc định dùng cùng một trình xử lý**.

### 2.1. Thành phần nào trả lỗi nào?

| Tình huống | Điểm xử lý điển hình | HTTP status thường gặp |
| --- | --- | --- |
| Không gửi credentials cho API yêu cầu đăng nhập | `AuthenticationEntryPoint` qua `ExceptionTranslationFilter` | 401 với HTTP Basic/Bearer |
| Username/password Basic sai | Entry point do `BasicAuthenticationFilter` dùng | 401 |
| Đã đăng nhập nhưng thiếu `ROLE_ADMIN` | `AccessDeniedHandler` qua `ExceptionTranslationFilter` | 403 |
| Session hết hạn | Authentication entry point / redirect tùy flow | 401 hoặc 302 |
| Browser gửi unsafe request thiếu CSRF token | CSRF filter/handler của nó | Thường 403; body có thể khác |
| Resource không tồn tại trong controller | MVC exception handler | 404 |
| JSON body sai định dạng | MVC validation/message-converter handler | 400 |
| Business rule thất bại | Service/MVC exception handler | 4xx hoặc 5xx theo hợp đồng |
| Unexpected server exception | Xử lý lỗi ứng dụng/container | 500 |

**Không dùng một thông báo “Access denied” cho tất cả tình huống**. Client cần phân biệt có nên yêu cầu login, hiển thị “không đủ quyền”, sửa input hay thử lại sau.

### 2.2. 401 khác 403, nhưng không chỉ nhìn status

Ví dụ với Basic:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/problem+json

{"type":"urn:demo:problem:authentication-required","title":"Authentication required","status":401,"detail":"Authentication is required to access this resource."}
~~~

Đã có authentication nhưng thiếu quyền:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{"type":"urn:demo:problem:access-denied","title":"Access denied","status":403,"detail":"You do not have permission to access this resource."}
~~~

Các header/JSON được trình bày để minh họa; thứ tự thuộc tính JSON không có ý nghĩa, và server có thể thêm security/cache headers.

Một tình huống cùng endpoint:

- Anonymous gọi `GET /api/admin` với HTTP Basic → 401 và challenge.
- User `alice` xác thực đúng nhưng không có `ROLE_ADMIN` → 403.
- User `admin` có `ROLE_ADMIN` → 200.
- Nếu đổi sang form login, anonymous có thể nhận **302 redirect** thay vì 401.
- Nếu dùng OAuth2 Resource Server, challenge theo Bearer và thông tin `error`/`scope` phụ thuộc chuẩn tương ứng.

**Đừng thay đổi entry point để trả 403 cho mọi request chưa đăng nhập**: client sẽ mất khả năng biết cần authentication. Ngược lại, không trả 401 cho user đã login mà chỉ thiếu quyền, trừ khi có chính sách đặc thù được xác định rõ.

## 3. JSON tùy chỉnh và ProblemDetail: chọn kiểu nào?

Có hai cách hợp lệ, miễn là API có **hợp đồng thống nhất** và client hiểu cách diễn giải.

### 3.1. JSON tùy chỉnh

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền truy cập tài nguyên này.",
  "status": 403,
  "requestId": "req-demo-123"
}
~~~

Ưu điểm: kiểm soát tên trường, code lỗi và localization, dễ tương thích với API đã có.

Nhược điểm: các team có thể tự đặt các trường `error`, `message`, `code`, `status`, `traceId` không nhất quán; client phải biết schema nội bộ. Nếu thiết kế mới, nên cân nhắc chuẩn Problem Details thay vì phát minh một định dạng riêng mà không có lý do rõ.

**Không** trả stack trace, thông tin SQL, nguyên exception message, password, Bearer token, cookie session hoặc chi tiết xác thực cho client. `requestId` nếu có nên được tạo/kiểm soát bởi hệ thống hoặc middleware đáng tin; không phản chiếu header tùy ý mà chưa kiểm tra.

### 3.2. ProblemDetail của Spring Framework 6

`org.springframework.http.ProblemDetail` đại diện một response body theo **Problem Details for HTTP APIs (RFC 9457)**. Kiểu media thường dùng là:

~~~http
Content-Type: application/problem+json
~~~

Các trường chuẩn:

| Trường | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `type` | URI tham chiếu xác định **loại vấn đề** | Nếu không cung cấp, chuẩn có mặc định `about:blank` |
| `title` | Tóm tắt ngắn, ổn định theo loại lỗi | Không đưa dữ liệu nhạy cảm |
| `status` | Mã HTTP gắn với problem | Phải nhất quán với HTTP response status |
| `detail` | Diễn giải cụ thể cho lần xảy ra lỗi | Dùng mô tả an toàn, không phát tán exception |
| `instance` | URI tham chiếu chỉ lần xảy ra cụ thể | Có thể bỏ khi không có URI an toàn |

`type` có thể là một URL tài liệu hóa công khai hoặc một URI/URN ổn định do tổ chức định nghĩa. Ví dụ `urn:demo:problem:access-denied` ở bài **chỉ là namespace minh họa**, không phải mã hệ thống toàn cầu. Hãy dùng type URI ổn định và có tài liệu trong sản phẩm thật; client dựa vào `type` hoặc một extension error code để phân biệt lỗi, không phụ thuộc văn bản tự nhiên của `detail`.

Spring tạo object:

~~~java
ProblemDetail p = ProblemDetail.forStatusAndDetail(
    HttpStatus.FORBIDDEN,
    "You do not have permission to access this resource."
);
p.setTitle("Access denied");
p.setType(URI.create("urn:demo:problem:access-denied"));
~~~

Đây là snippet Java cần imports `ProblemDetail`, `HttpStatus` và `URI`. `ProblemDetail` **không tự viết response trong security filter**: bạn phải chọn serializer, status, headers và output stream; project hoàn chỉnh ở phần 9 làm rõ việc đó.

### 3.3. Ví dụ ProblemDetail cho 401 và 403

~~~json
{
  "type": "urn:demo:problem:authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "Authentication is required to access this resource."
}
~~~

~~~json
{
  "type": "urn:demo:problem:access-denied",
  "title": "Access denied",
  "status": 403,
  "detail": "You do not have permission to access this resource."
}
~~~

Không bắt buộc `instance` hoặc extension trong mọi trường hợp. Khi có `instance`, tránh để URL path/query chứa token, email, mã bí mật hoặc resource ID mà người gọi không được biết. `type/title` thường được giữ ổn định, `detail` có thể thay đổi theo ngôn ngữ hoặc tình huống. **Client không nên so sánh nguyên văn detail để quyết định logic.**

### 3.4. Khi nào nên chọn JSON riêng?

| Tình huống | Hướng chọn |
| --- | --- |
| API mới và chưa có error contract | Thường ưu tiên `ProblemDetail` để có cấu trúc chung |
| API đã có JSON schema ổn định nhiều client dùng | Giữ tương thích, cân nhắc versioning khi chuyển |
| Nội bộ yêu cầu `code` riêng, UI đa ngôn ngữ | Có thể dùng JSON riêng hoặc extension trong ProblemDetail |
| API chỉ dùng HTML/form login | Có thể dùng redirect/error page thay vì ép JSON |
| Machine-to-machine REST với Bearer | ProblemDetail phù hợp nhưng vẫn phải giữ đúng Bearer challenge |
| Legacy gateway yêu cầu schema cụ thể | Đồng bộ contract gateway và backend, không tự đổi response |

Chọn một định dạng cho một API version và test từ đầu đến cuối. **Đừng trộn `application/json` với body ProblemDetail và `application/problem+json` với JSON không theo chuẩn** nếu chưa có chủ đích tương thích rõ.

## 4. AuthenticationEntryPoint: trả 401 đúng cách

### 4.1. Giao diện

~~~java
public interface AuthenticationEntryPoint {
    void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException, ServletException;
}
~~~

Đây là trích chữ ký chính để học, không phải file source framework đầy đủ. Trên Spring Boot 3 sử dụng `jakarta.servlet.*`, không dùng `javax.servlet.*` của hệ sinh thái cũ.

REST entry point thường cần:

1. Đảm bảo response chưa được commit.
2. Đặt `status = 401`.
3. Đặt đúng `Content-Type` cho JSON/ProblemDetail.
4. Giữ **`WWW-Authenticate` challenge bắt buộc/phù hợp với auth scheme**.
5. Không đưa `authException.getMessage()` ra response vì có thể lộ username, token, cấu hình hoặc nguyên nhân nội bộ.
6. Serialize một body hợp lệ bằng JSON library có sẵn.
7. Đảm bảo không write thêm body sau response đã committed.

### 4.2. HTTP Basic cần WWW-Authenticate

Header:

~~~http
WWW-Authenticate: Basic realm="demo-api"
~~~

cho biết client có thể cung cấp Basic credentials cho protection space. Nếu bạn tự thay một `BasicAuthenticationEntryPoint` bằng handler JSON nhưng **bỏ header này**, một số client HTTP sẽ không hiểu cách xác thực hoặc không kích hoạt luồng đăng nhập Basic đúng cách.

Một cách thiết kế entry point:

~~~text
Chưa đăng nhập / Basic password sai
   |
   +-- 401 Unauthorized
   +-- WWW-Authenticate: Basic realm="demo-api"
   +-- Content-Type: application/problem+json
   +-- body ProblemDetail an toàn
~~~

**Không ép mọi kiểu authentication dùng header Basic.** API Bearer cần challenge `Bearer` theo RFC 6750/OAuth2; login form cần entry point kiểu redirect, và CSRF state có cách xử lý riêng. Nếu ứng dụng trộn Basic + Bearer + session, hãy chọn entry point theo request matcher hoặc chain phù hợp thay vì hard-code một format/header toàn cục.

### 4.3. Tại sao cần cấu hình cả httpBasic và exceptionHandling?

Với HTTP Basic:

~~~java
http
    .httpBasic(basic -> basic.authenticationEntryPoint(problemEntryPoint))
    .exceptionHandling(ex -> ex
        .authenticationEntryPoint(problemEntryPoint)
        .accessDeniedHandler(problemDeniedHandler));
~~~

Đây là snippet thuộc cấu hình `HttpSecurity`. Cách này nêu rõ:

- Khi Basic filter xử lý credentials không hợp lệ, nó dùng entry point đã chọn.
- Khi `ExceptionTranslationFilter` cần khởi phát authentication cho request protected, nó cũng dùng entry point đó.
- Khi một authenticated principal bị từ chối trong phạm vi handler, nó dùng denied handler.

Không phải mọi security exception đều đi qua `ExceptionTranslationFilter`: một filter khác có thể xử lý lỗi trực tiếp hoặc lỗi xảy ra trước phạm vi filter đó. Test cả **không gửi credentials** và **gửi credentials sai**, không chỉ một ca.

## 5. AccessDeniedHandler: trả 403 không để lộ chính sách

### 5.1. Giao diện

~~~java
public interface AccessDeniedHandler {
    void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException, ServletException;
}
~~~

Các object `Authentication` và `GrantedAuthority` có thể tồn tại khi handler chạy, nhưng **không cần** đưa chúng vào JSON trả người dùng. Ví dụ một user không thuộc tenant B có thể biết ít hơn về tài liệu B; body nên ngắn gọn và trung tính.

~~~json
{
  "type": "urn:demo:problem:access-denied",
  "title": "Access denied",
  "status": 403,
  "detail": "You do not have permission to access this resource."
}
~~~

Tránh:

~~~json
{
  "status": 403,
  "debug": "alice missing ROLE_INTERNAL_BILLING_MANAGER on tenant-x/document-9981",
  "stackTrace": "..."
}
~~~

Thông tin role, tenant, document ID và stack trace có thể tiết lộ dữ liệu nhạy cảm hoặc làm lộ cấu trúc chính sách. Backend có thể log sự kiện deny một cách có kiểm soát, tách khỏi nội dung client nhận.

### 5.2. AccessDeniedHandler không đồng nghĩa mọi 403

Một request POST sai CSRF token có thể bị `CsrfFilter` từ chối trước khi `AuthorizationFilter` đánh giá quyền. Một số cấu hình sử dụng **handler riêng của CsrfFilter**, không mặc nhiên gọi custom `AccessDeniedHandler` đã gắn vào `ExceptionTranslationFilter`.

Do đó, để đảm bảo **mọi 403 đều là ProblemDetail**, bạn cần kiểm toán **toàn bộ điểm phát lỗi**: CSRF, CORS, firewall, application, gateway, container, servlet error dispatch… Không nên tuyên bố một bean handler duy nhất đã giải quyết tất cả.

Trong project demo, test CSRF chỉ khẳng định **status 403**, không khẳng định body luôn cùng schema với authorization 403. Đây là giới hạn được trình bày chủ động, không phải bỏ sót test.

### 5.3. Method security exception và HTTP status

Nếu `@PreAuthorize` ở service ném `AccessDeniedException` trong quá trình controller xử lý, kết quả 403 có thể đi qua security exception translation/handler hoặc MVC exception resolution tùy cấu hình và xử lý đã đăng ký. Cần **integration test thực tế** trên đường đi HTTP. Không tạo một `@ExceptionHandler(AccessDeniedException.class)` chung trả 200 hoặc nuốt lỗi, vì có thể tạo trạng thái sai và phá contract.

## 6. Khác biệt giữa security filter errors và @RestControllerAdvice

### 6.1. @RestControllerAdvice làm gì?

Trong MVC, bạn có thể viết:

~~~java
@RestControllerAdvice
class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> invalidInput(
            IllegalArgumentException exception) {

        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, "Request data is invalid.");
        p.setTitle("Invalid request");
        return ResponseEntity.badRequest().body(p);
    }
}
~~~

Đây là snippet nằm trong cùng package/cấu hình với MVC app; cần imports `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, `HttpStatus`. Nó áp dụng cho các exceptions mà **MVC exception resolver** được trao cơ hội xử lý.

Một anonymous request có thể bị Spring Security chặn ở filter chain **trước khi controller/advice xử lý**. Vì vậy nếu chỉ tạo Advice trên, 401 Basic có thể vẫn là text/HTML mặc định hoặc response không đúng schema bạn muốn.

### 6.2. Không nên dùng sendError để bảo đảm JSON

Trong một servlet response, `response.sendError(403)` có thể kích hoạt container error dispatch tới `/error` hoặc error page, với body khác dự kiến. Nếu đã quyết định trả JSON ở handler, hãy **đặt status và tự serialize một body**, tránh việc vừa gửi error dispatch vừa ghi JSON.

Trong project:

~~~java
response.setStatus(HttpStatus.FORBIDDEN.value());
response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
mapper.writeValue(response.getOutputStream(), problem);
~~~

Đây là snippet rút gọn; project hoàn chỉnh còn set charset/cache và kiểm response đã commit. Nếu response đã commit, việc đổi status/header hoặc ghi body mới có thể không có tác dụng hoặc gây lỗi. Không viết đè response committed từ nhiều nơi.

### 6.3. Có thể dùng HandlerExceptionResolver từ filter không?

Có thể ủy quyền tới `HandlerExceptionResolver` để tái sử dụng cơ chế MVC cho một số exception, nhưng cần cân nhắc:

- Resolver nào đang được cấu hình và có xử lý đúng `AuthenticationException`/`AccessDeniedException` không?
- Có đang chạy **trước DispatcherServlet**, không có controller handler hay MVC context đầy đủ?
- Có vô tình dùng một handler cho lỗi 401 nhưng bỏ `WWW-Authenticate` không?
- Có khả năng double-write hoặc forward/error dispatch không?
- Có đảm bảo lỗi CSRF, Bearer, CORS, proxy và container đều đi qua resolver không?

Với lỗi authentication/authorization của security filter, **định nghĩa entry point và denied handler rõ ràng** thường dễ kiểm soát hơn. Nếu cần thống nhất schema, tách **lớp writer/factory** dùng chung cho MVC và security thay vì ép mọi error vào cùng một ExceptionHandler.

## 7. Quy tắc HTTP và bảo mật khi xuất lỗi JSON

### 7.1. Status phải nhất quán với body

Không trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/problem+json

{"status":403,"title":"Access denied"}
~~~

Một client/cache/monitor nhìn HTTP 200 có thể coi request thành công. Giữ **status ở HTTP response và `ProblemDetail.status` trùng nhau**, ví dụ cả hai là 403.

### 7.2. Content-Type rõ ràng

- JSON tùy chỉnh: `application/json`.
- ProblemDetail: `application/problem+json`.
- Charset: UTF-8; nên dùng serializer, không tự nối JSON string dễ hỏng escape/Unicode.
- `Content-Length` có thể để container tính; đừng tính bằng số ký tự Java khi output có UTF-8 tiếng Việt.
- Trả body chỉ một lần, tránh ghi message từ exception qua `response.getWriter()` rồi lại ghi stream.

### 7.3. Cache và dữ liệu nhạy cảm

Response authentication/authorization có thể chứa ID hoặc thông tin về quyền. Dùng chính sách cache phù hợp, ví dụ:

~~~http
Cache-Control: no-store
~~~

Các security headers khác như `X-Content-Type-Options: nosniff`, HSTS hoặc CSP phụ thuộc chain/proxy và loại response. Không dùng cache công khai/shared cho lỗi có thông tin cá nhân nếu không có chính sách hợp lệ.

### 7.4. Không gửi raw exception

Không đặt trực tiếp:

~~~java
problem.setDetail(authException.getMessage());
~~~

vì message có thể bao gồm tên account, nguyên nhân login failure, stack details hoặc dữ liệu nhạy cảm từ provider. Hãy dùng các thông báo có chủ ý, ví dụ:

~~~text
401: Authentication is required to access this resource.
403: You do not have permission to access this resource.
~~~

Thông tin chi tiết hơn (error class, request correlation, user ID, source of policy) thuộc **structured logs được kiểm soát**, không mặc định thuộc public response. Đối với failed login, không phân biệt “username không tồn tại” và “password sai” trong body nếu điều đó tạo user enumeration.

### 7.5. XSS và reflected input

Nếu có thêm `instance`/`path`/`requestId` từ client vào JSON, tránh trực tiếp echo query parameters hoặc URL có token. Jackson sẽ escape chuỗi JSON, nhưng **escape không thay việc hạn chế thông tin phản chiếu**. Không xây HTML error pages bằng cách chèn nguyên URL/exception text chưa xử lý.

### 7.6. Problem type như API contract

Nên định nghĩa danh sách type ổn định:

| Type URI minh họa | HTTP status | Ý nghĩa |
| --- | --- | --- |
| `urn:demo:problem:authentication-required` | 401 | Cần cung cấp authentication hợp lệ |
| `urn:demo:problem:access-denied` | 403 | Không được phép |
| `urn:demo:problem:invalid-request` | 400 | Input không hợp lệ |
| `urn:demo:problem:not-found` | 404 | Không tìm thấy hoặc không tiết lộ resource |
| `urn:demo:problem:internal-error` | 500 | Lỗi nội bộ chung, không tiết lộ chi tiết |

Đây là **các type ví dụ**, chưa có URL tài liệu thực. Trong sản phẩm thật, công bố tài liệu lỗi, ownership và versioning. Có thể thêm extension `code` hoặc `traceId` nếu schema/lifecycle của chúng được định nghĩa; đừng thay đổi ý nghĩa của một type cũ mà không thông báo client.

## 8. Chọn biểu diễn theo người gọi và authentication mechanism

### 8.1. API và trang HTML có nhu cầu khác nhau

Một ứng dụng Servlet có thể phục vụ:
- `/api/**`: client JSON, lỗi 401/403 là ProblemDetail.
- `/web/**`: người dùng browser, chưa login thì redirect tới form.
- `/assets/**`: static resources công khai theo quyết định bảo mật.
- `/actuator/**`: quản lý riêng với policy chặt chẽ.

Nếu bạn gắn một entry point trả JSON cho mọi URL, người dùng web có thể mất luồng redirect mà UI cần. Dùng nhiều `SecurityFilterChain` với `securityMatcher` hoặc một `DelegatingAuthenticationEntryPoint` có request matchers để chọn entry point đúng.

**Thứ tự SecurityFilterChain quan trọng:** `FilterChainProxy` chọn chain đầu tiên có matcher khớp. Không có catch-all chain có thể để URL ngoài các chain không được Spring Security bảo vệ. `anyRequest().denyAll()` bên trong một chain hẹp **không** bảo vệ URL nằm ngoài chain ấy.

### 8.2. Basic, Bearer và form login không cùng WWW-Authenticate

- HTTP Basic: `WWW-Authenticate: Basic realm="..."` khi 401.
- OAuth2 Bearer: `WWW-Authenticate: Bearer ...` theo tiêu chuẩn Bearer token; có thể gồm `error="invalid_token"` hoặc `insufficient_scope` trong những trường hợp phù hợp.
- Form login: có thể 302 redirect tới `/login` và HTML thay vì JSON.
- Session API: tùy contract có thể 401 JSON khi hết session, nhưng không tự assume browser form login hoạt động giống vậy.

Nếu dùng `oauth2ResourceServer().jwt()`, framework có `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` để hỗ trợ semantics Bearer. **Không thay chúng bằng header Basic giả** chỉ để giữ body chung. Có thể tùy biến body nếu đảm bảo challenge và HTTP semantics.

### 8.3. CORS và error responses

Nếu frontend ở origin khác gọi API bằng JavaScript, request có thể cần CORS headers cả trên responses 401/403. Một error body đúng định dạng **không có nghĩa frontend được đọc body** nếu CORS policy không cho phép.

Cấu hình CORS tại Spring Security và nguồn policy đáng tin, không đưa `Access-Control-Allow-Origin: *` với credentials để “sửa” lỗi auth. Nếu preflight OPTIONS bị chặn, kiểm tra filter order/configuration; đừng vội cho `anyRequest().permitAll()`.

### 8.4. CSRF và HTTP Basic

CSRF là chính sách riêng cho unsafe methods (POST/PUT/PATCH/DELETE). Project mẫu giữ CSRF mặc định. Một `POST` hợp lệ về authentication và authorization vẫn có thể trả 403 **vì thiếu CSRF token**. Do đó:

- Test positive write với token CSRF hợp lệ.
- Test thiếu CSRF nhận 403.
- **Không khẳng định body của CSRF denial chắc chắn do custom AccessDeniedHandler tạo**.
- Nếu API dùng Bearer header và không dựa vào cookie do browser tự gửi, cần đánh giá CSRF theo threat model; không tắt chỉ vì API trả JSON.
- Khi muốn thống nhất JSON cho CSRF, phải cấu hình/test **handler thực của CsrfFilter** trên phiên bản bạn sử dụng.

### 8.5. Proxy và error pages

Ingress, API Gateway, CDN hoặc reverse proxy có thể tự trả 401/403/404/5xx. Các body đó **không đi qua Spring Security**. Muốn hợp đồng response thống nhất toàn đường đi, cần kiểm tra từng lớp mạng và cấu hình gateway tương ứng. Không thể bảo đảm gateway trả ProblemDetail chỉ bằng một Spring bean.

## 9. Project chạy được: Java 17, Spring Boot 3.3.13, Security 6, ProblemDetail

Ví dụ hoàn chỉnh dưới đây áp dụng **HTTP Basic** và **một filter chain** cho demo REST. Mục tiêu là thiết kế ProblemDetail 401/403 qua hai security handlers, đồng thời kiểm tra public, authenticated, role, password sai, fallback deny và CSRF.

### 9.1. Cấu trúc thư mục

~~~text
security-problem-detail/
├── pom.xml
└── src/
    ├── main/java/com/example/securityerrors/
    │   ├── SecurityErrorsApplication.java
    │   ├── SecurityConfig.java
    │   ├── SecurityProblemWriter.java
    │   ├── ProblemAuthenticationEntryPoint.java
    │   ├── ProblemAccessDeniedHandler.java
    │   └── DemoController.java
    └── test/java/com/example/securityerrors/
        └── SecurityErrorResponseTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>security-problem-detail</artifactId>
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
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
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
~~~

### 9.2. Main application

**`src/main/java/com/example/securityerrors/SecurityErrorsApplication.java`**

~~~java
package com.example.securityerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityErrorsApplication.class, args);
    }
}
~~~

### 9.3. Writer dùng chung cho hai security handlers

**`src/main/java/com/example/securityerrors/SecurityProblemWriter.java`**

~~~java
package com.example.securityerrors;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;

@Component
public class SecurityProblemWriter {

    private final ObjectMapper mapper;

    public SecurityProblemWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(
            HttpServletResponse response,
            HttpStatus status,
            String type,
            String title,
            String detail) throws IOException {

        // Một response đã commit thì không thể viết lỗi mới an toàn.
        if (response.isCommitted()) {
            return;
        }

        ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(status, detail);

        problem.setType(URI.create(type));
        problem.setTitle(title);

        response.setStatus(status.value());
        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding(
            StandardCharsets.UTF_8.name());
        response.setHeader(
            HttpHeaders.CACHE_CONTROL, "no-store");

        mapper.writeValue(response.getOutputStream(), problem);
    }
}
~~~

**Giải thích:**

- Spring Boot `spring-boot-starter-web` cung cấp `ObjectMapper` qua Jackson auto-configuration khi chưa tùy chỉnh loại bỏ nó.
- `ProblemDetail` có các trường chuẩn `type/title/status/detail`, được serialize bằng Jackson. Ví dụ không phụ thuộc custom extension properties.
- `response.setStatus(...)` đồng nhất với `ProblemDetail.status`.
- `application/problem+json` phân biệt rõ Problem Details với JSON riêng.
- UTF-8 hỗ trợ tiếng Việt; không tự tính Content-Length theo Java String length.
- `Cache-Control: no-store` giảm rủi ro lưu lỗi có ngữ cảnh quyền.
- Không gửi `instance` theo request URI để tránh vô tình phản chiếu path/query nhạy cảm.
- Khi response đã commit, writer không cố write thêm; trong production nên có logging/metric an toàn để phát hiện tình huống committed-response, không hiển thị raw exception cho caller.

**Writer không tự gắn `WWW-Authenticate`.** Header đó là trách nhiệm của **entry point theo từng authentication scheme**. Tách trách nhiệm giúp writer có thể được dùng cho Basic, Bearer hoặc error handling khác mà không phát sai challenge.

### 9.4. Entry point trả 401, giữ challenge của Basic

**`src/main/java/com/example/securityerrors/ProblemAuthenticationEntryPoint.java`**

~~~java
package com.example.securityerrors;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

@Component
public class ProblemAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final SecurityProblemWriter writer;

    public ProblemAuthenticationEntryPoint(
            SecurityProblemWriter writer) {
        this.writer = writer;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        if (response.isCommitted()) {
            return;
        }

        // HTTP Basic cần challenge. Với Bearer phải dùng Bearer,
        // KHÔNG sao chép header Basic này sang JWT API.
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"demo-api\"");

        // Không đưa exception.getMessage() vào public response.
        writer.write(
            response,
            HttpStatus.UNAUTHORIZED,
            "urn:demo:problem:authentication-required",
            "Authentication required",
            "Authentication is required to access this resource.");
    }
}
~~~

Cả request thiếu Basic credentials và Basic credentials sai cần dùng cùng **entry point** để giữ body đồng nhất. Việc cấu hình entry point bên trong `httpBasic(...)` và `exceptionHandling(...)` ở phần kế tiếp làm rõ điều này.

Không trả lỗi chi tiết như `"User alice not found"` hoặc `"Password expired for account ..."` cho caller; đó có thể là user enumeration. Với lỗi cần support, trả một request correlation ID an toàn và giữ thông tin chi tiết trong logs có kiểm soát.

### 9.5. AccessDeniedHandler trả 403

**`src/main/java/com/example/securityerrors/ProblemAccessDeniedHandler.java`**

~~~java
package com.example.securityerrors;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

@Component
public class ProblemAccessDeniedHandler
        implements AccessDeniedHandler {

    private final SecurityProblemWriter writer;

    public ProblemAccessDeniedHandler(SecurityProblemWriter writer) {
        this.writer = writer;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException {

        writer.write(
            response,
            HttpStatus.FORBIDDEN,
            "urn:demo:problem:access-denied",
            "Access denied",
            "You do not have permission to access this resource.");
    }
}
~~~

`AccessDeniedException` **không** được serialize ra body. Response vẫn cung cấp một mã lỗi máy đọc được (`type`) và thông báo trung tính. Nếu dùng 403 để tránh lộ tài nguyên, không thêm resource title, owner name hay danh sách role cần có.

### 9.6. SecurityConfig nối đúng handler vào Spring Security

**`src/main/java/com/example/securityerrors/SecurityConfig.java`**

~~~java
package com.example.securityerrors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ProblemAuthenticationEntryPoint entryPoint,
            ProblemAccessDeniedHandler deniedHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(entryPoint))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            // CSRF không bị tắt; request POST cần token.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String encoded = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoded)
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoded)
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Điểm cần đọc kỹ:**

1. `/api/public` được `permitAll`, nhưng vẫn đi qua security filter chain. Nó không cần Authentication.
2. `/api/admin` yêu cầu `ROLE_ADMIN`. User `alice` có `ROLE_USER` sẽ bị 403.
3. `/api/profile` yêu cầu authenticated. Anonymous sẽ bị 401 và Basic challenge.
4. `/api/notes` dùng POST; mặc định Spring Security CSRF bảo vệ unsafe method. Test riêng với CSRF token và không có token.
5. `anyRequest().denyAll()` chặn request không được đưa vào chính sách, kể cả authenticated ADMIN.
6. `httpBasic(...authenticationEntryPoint(entryPoint))` bảo đảm đường lỗi Basic credentials sai dùng writer của demo.
7. `exceptionHandling(...authenticationEntryPoint(entryPoint))` bảo đảm đường request protected chưa authentication do ExceptionTranslationFilter sử dụng cùng entry point.
8. `accessDeniedHandler(deniedHandler)` xử lý authorization denial trong phạm vi ExceptionTranslationFilter, **không khẳng định bắt mọi 403 từ CSRF/container**.
9. Không dùng `web.ignoring()` hoặc `anyRequest().permitAll()` như một cách chữa lỗi JSON, vì sẽ vô tình bỏ authorization.

### 9.7. Controller tối thiểu

**`src/main/java/com/example/securityerrors/DemoController.java`**

~~~java
package com.example.securityerrors;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicPage() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("status", "admin-ok");
    }

    @PostMapping("/api/notes")
    public Map<String, String> createNote() {
        return Map.of("status", "created");
    }
}
~~~

Controller không xử lý trực tiếp security exceptions. Spring Security sẽ chặn unauthorized/forbidden request trước khi nó đến controller. Trong thực tế, resource-level permissions và ownership phải được kiểm thêm ở service/method; một user authenticated không tự có quyền trên mọi record.

### 9.8. MockMvc integration tests kiểm tra body, headers và HTTP semantics

**`src/test/java/com/example/securityerrors/SecurityErrorResponseTests.java`**

~~~java
package com.example.securityerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityErrorResponseTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public-ok"));
    }

    @Test
    void missingCredentialsGet401ProblemAndBasicChallenge()
            throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.status").value(401))
            .andExpect(jsonPath("$.title")
                .value("Authentication required"))
            .andExpect(jsonPath("$.type")
                .value("urn:demo:problem:authentication-required"));
    }

    @Test
    void invalidBasicCredentialsUseSame401Contract()
            throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403Problem()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.title").value("Access denied"))
            .andExpect(jsonPath("$.type")
                .value("urn:demo:problem:access-denied"));
    }

    @Test
    void authenticatedUserMayAccessOwnAllowedRoute()
            throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-ok"));
    }

    @Test
    void fallbackDeniedEvenForAdminGets403Problem()
            throws Exception {
        mvc.perform(get("/not-listed")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(403));
    }

    @Test
    void csrfIsIndependentOfAuthorizationErrorWriter()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Token hợp lệ giúp request đi qua CSRF filter.
        mvc.perform(post("/api/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("created"));
    }
}
~~~

**Vì sao cần đúng bộ tests này?**

- `GET /api/profile` anonymous: kiểm đường đi ExceptionTranslationFilter và 401 response.
- Basic password sai: kiểm đường đi lỗi của BasicAuthenticationFilter, tránh quên cấu hình entry point ở `httpBasic`.
- User thường vào admin: kiểm `AccessDeniedHandler` trả body ProblemDetail 403.
- Admin vào endpoint không liệt kê: kiểm fallback deny, không vì “ADMIN” mà bỏ rule.
- Kiểm nội dung `status` bên trong body **trùng HTTP status**.
- Kiểm `Content-Type: application/problem+json` thay vì text/html hoặc JSON custom sai media type.
- Kiểm `WWW-Authenticate` còn tồn tại với 401 HTTP Basic.
- Kiểm thiếu CSRF nhận 403 **nhưng không khẳng định body sẽ do denied handler tạo**.
- Kiểm request có token CSRF hợp lệ vẫn đi đến controller.
- Dùng `httpBasic(...)` từ `spring-security-test` để thực sự gửi Basic credentials qua filter chain thay vì bypass bằng `@WithMockUser`.

Nếu công ty sử dụng Browser/SPAs, ngoài MockMvc cần **end-to-end tests với browser** để xác nhận CORS, cookie, redirect và credential handling. MockMvc không mô phỏng mọi hành vi của browser hoặc reverse proxy.

### 9.9. Chạy dự án và quan sát

Cần cài **JDK 17+**, Maven, khả năng tải dependencies và tạo file đúng đường dẫn trong phần 9.1:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Kết quả dự kiến:** test suite pass và Maven in `BUILD SUCCESS` nếu cấu hình/môi trường tương thích. Mã đã được mô tả và kiểm tra tĩnh trong bài; **không khẳng định đã thực thi Maven**.

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
# Dự kiến 200 OK, body {"status":"public-ok"}

curl -i http://localhost:8080/api/profile
# Dự kiến 401, WWW-Authenticate: Basic realm="demo-api"
# Content-Type: application/problem+json, status=401

curl -i -u alice:wrong-password \
  http://localhost:8080/api/profile
# Dự kiến 401 ProblemDetail, Basic challenge

curl -i -u alice:demo-pass \
  http://localhost:8080/api/profile
# Dự kiến 200 OK, body {"username":"alice"}

curl -i -u alice:demo-pass \
  http://localhost:8080/api/admin
# Dự kiến 403, ProblemDetail type access-denied

curl -i -u admin:demo-pass \
  http://localhost:8080/api/admin
# Dự kiến 200 OK, body {"status":"admin-ok"}

curl -i -u admin:demo-pass \
  http://localhost:8080/not-listed
# Dự kiến 403, ProblemDetail do fallback denyAll

curl -i -u alice:demo-pass -X POST \
  http://localhost:8080/api/notes
# Dự kiến 403 vì thiếu CSRF token (body có thể khác)
~~~

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là alias của cmdlet khác. **Chỉ thử HTTP Basic trên localhost với credentials demo.** Basic credentials được mã hóa Base64, **không được bảo mật bằng Base64**; production phải dùng HTTPS và chính sách authentication thật.

## 10. Phương án JSON tùy chỉnh thay cho ProblemDetail

Nếu API đã có contract như sau:

~~~json
{
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "Authentication is required.",
    "status": 401
  }
}
~~~

có thể thay writer tạo `ProblemDetail` bằng DTO tự định nghĩa. Phần quan trọng **không đổi**: EntryPoint/DeniedHandler phải giữ HTTP status và headers chính xác; chỉ có body và Content-Type khác.

Ví dụ một DTO rõ ràng:

~~~java
public record ApiError(
    String code,
    String message,
    int status
) {
}
~~~

Snippet này đặt trong file `ApiError.java` nếu chọn phương án JSON riêng. Response:

~~~java
response.setStatus(HttpStatus.UNAUTHORIZED.value());
response.setContentType(MediaType.APPLICATION_JSON_VALUE);
response.setCharacterEncoding(StandardCharsets.UTF_8.name());

ApiError error = new ApiError(
    "AUTHENTICATION_REQUIRED",
    "Authentication is required.",
    HttpStatus.UNAUTHORIZED.value()
);

mapper.writeValue(response.getOutputStream(), error);
~~~

Đoạn trên là snippet trong writer đã có `response`, `mapper` và các imports phù hợp; nó **không thay thế toàn bộ project ở phần 9** cho tới khi bạn thực sự chọn phương án JSON riêng. Nếu muốn cấu trúc nested `{"error": {...}}` như ví dụ đầu đoạn, cần wrapper DTO, không dùng `ApiError` đơn lẻ mà lại khẳng định JSON đã lồng.

Một API nên chọn **một** schema công khai cho error contract, định nghĩa versioning và test. Nếu chuyển từ JSON cũ sang ProblemDetail, client có thể hỏng khi đọc `$.error.code` thay cho `$.type`; hãy hỗ trợ migration hoặc versioning thay vì đổi ngầm.

## 11. Vấn đề localization, request ID và observability

### 11.1. Dùng error code ổn định hơn message tự nhiên

`title`/`detail` có thể được dịch sang tiếng Việt/Anh dựa trên `Accept-Language` nếu sản phẩm yêu cầu, nhưng **type URI hoặc code** nên ổn định để client không phụ thuộc nội dung dịch.

Ví dụ 403:

~~~json
{
  "type": "urn:demo:problem:access-denied",
  "title": "Không có quyền truy cập",
  "status": 403,
  "detail": "Bạn không có quyền thực hiện thao tác này."
}
~~~

Nếu localize, cần đánh giá cả response `Content-Language`, cache policy, fallback locale và trách nhiệm của frontend; không đưa message nội bộ của authentication provider ra chỉ vì muốn có chi tiết cho người dùng.

### 11.2. Correlation ID an toàn

Khi cần hỗ trợ sự cố, có thể trả extension `requestId` hoặc `traceId` đã qua kiểm soát. Mục đích là để support tìm được log nội bộ mà không phơi bày exception.

- Sinh ID tại trusted gateway/server, hoặc xác minh chặt ID client gửi.
- Không đưa token, password, session ID, full request body vào ID.
- Không trả nguyên stack trace, database query hoặc tên hệ thống nội bộ.
- Thống nhất ID với distributed tracing/logging khi có.
- Kiểm soát quyền đọc logs và retention.

Nếu không có tracing infrastructure, tốt hơn **bỏ extension** còn hơn trả một ID ngẫu nhiên mà hệ thống không thể tra cứu.

### 11.3. Những chỉ số nên theo dõi

- Tỷ lệ 401 theo endpoint/API client và nguyên nhân nhóm (không ghi password).
- Tỷ lệ 403 theo route/policy đã chọn.
- Các request có CORS preflight failures.
- Lỗi CSRF nếu app dùng cookie/session.
- Số lần response đã committed trước khi error handler viết body.
- Tỷ lệ 5xx / gateway errors, phân biệt với 4xx.
- Bất thường tăng 401 trên login/resource, có rate limiting phù hợp.

**Không đặt username/email chưa được làm sạch làm metric label cardinality cao** hoặc rò rỉ dữ liệu. Dùng tags ổn định như route template, status và error type.

## 12. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ có `@RestControllerAdvice` cho lỗi filter | 401/403 không đi qua advice | Cấu hình AuthenticationEntryPoint, AccessDeniedHandler |
| Trả 200 với JSON `status=401` | Client/cache hiểu nhầm thành công | HTTP status và body.status phải trùng |
| Trả 401 không có `WWW-Authenticate` khi dùng Basic | Vi phạm semantics HTTP Basic | Giữ challenge Basic |
| Copy challenge Basic sang JWT Bearer API | Client OAuth2 hiểu sai | Dùng Bearer entry point/handler đúng scheme |
| Đặt `authException.getMessage()` trong body | Lộ thông tin auth/username/internal | Dùng message cố định an toàn |
| `response.sendError(403)` rồi viết JSON | Container error dispatch hoặc double-write | setStatus + serialize một lần |
| Ghi JSON trực tiếp bằng nối chuỗi | Escaping/Unicode lỗi, injection risk | Dùng ObjectMapper/serializer |
| Gắn handler 403 rồi nghĩ đã bắt cả CSRF 403 | CSRF filter có handler khác | Test và cấu hình CSRF riêng nếu cần |
| Tắt CSRF chỉ vì API trả JSON | Rủi ro với cookie-based auth | Đánh giá theo credentials/threat model |
| Cho `anyRequest().permitAll()` để tránh 403 | Mở endpoint nhạy cảm | Giữ fallback deny và khai rule đúng |
| Đưa path/query vào `instance` bất kể privacy | Phản chiếu token/resource ID | Giữ instance an toàn hoặc bỏ |
| Luôn trả full stack trace cho frontend | Lộ chi tiết triển khai | Giữ log riêng, response trung tính |
| Dùng `application/json` nhưng tuyên bố ProblemDetail | Media contract không chuẩn | Dùng `application/problem+json` |
| Thay đổi type/error code tùy ngôn ngữ | Client phải parse message | Giữ type/code ổn định |
| Không test password sai | BasicFilter có thể dùng entry point khác | Test cả missing và invalid credentials |
| Không test frontend qua CORS | Browser không đọc được body | E2E test CORS và credentials |
| Nghĩ Spring handler kiểm soát lỗi gateway | Gateway tự tạo response ngoài app | Cấu hình contract tại gateway |
| Không kiểm response committed | Handler ghi lỗi lần hai | Kiểm committed, log và điều tra flow |
| Dùng một entry point JSON cho tất cả web form pages | Mất redirect/UX login | Chia chain hoặc delegating entry points |

## 13. Checklist kiểm thử hợp đồng lỗi trước production

1. **Unauthenticated GET** vào endpoint cần bảo vệ → HTTP 401 với auth scheme phù hợp; không tiết lộ credentials.
2. **Bad credentials** → cùng schema với missing credentials; không phân biệt user tồn tại.
3. **Authenticated thiếu role** → HTTP 403, body không lộ role/user/tenant của resource khác.
4. **Authenticated có quyền** → 200/201 bình thường; error writer không can thiệp.
5. **Fallback deny** với route không liệt kê → không tự cho phép ADMIN vượt rule.
6. **CSRF missing/invalid token** → từ chối theo policy; kiểm body thực của handler tương ứng thay vì giả định.
7. **CORS preflight và cross-origin error response** → frontend đọc được status/body khi origin được phép.
8. **Cache headers** và các security headers không bị xóa khi xử lý lỗi.
9. **Body JSON parse được**, UTF-8 hợp lệ, Content-Type đúng, không double-write.
10. **HTTP status trùng ProblemDetail.status** và `type` ổn định.
11. **Không log/serialize raw exception** hoặc token vào response.
12. **Test form login và Bearer riêng** nếu nhiều auth schemes, đặc biệt `WWW-Authenticate`.
13. **Kiểm Method Security** với `@PreAuthorize`/`@PostAuthorize` và lỗi object-level.
14. **Kiểm error dispatch** của `/error`, servlet filters và proxy.
15. **Kiểm session hết hạn**, account disabled/locked theo authentication provider, refresh-token failure nếu có.
16. **Kiểm gateway/CDN 4xx/5xx** ngoài Spring Security.
17. **Contract tests của frontend/mobile** dùng code/type thay vì parse message.
18. **Load/security tests** để không bị error storms khiến log/storage quá tải.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@RestControllerAdvice` không đủ để chuẩn hóa toàn bộ 401/403?

**Đáp:** Security filters có thể từ chối request trước khi vào Spring MVC. Cần xử lý tại AuthenticationEntryPoint/AccessDeniedHandler hoặc điểm xử lý filter tương ứng.

**Câu 2.** Khi nào nên trả 401, khi nào 403?

**Đáp:** 401 khi cần authentication hợp lệ theo flow API; 403 khi đã xác thực nhưng thiếu quyền hoặc bị chặn bởi policy khác. Status còn phụ thuộc auth scheme/filter cụ thể, không suy luận mọi denial đều 403.

**Câu 3.** Vì sao 401 HTTP Basic cần `WWW-Authenticate`?

**Đáp:** Để phát challenge chỉ rõ Basic scheme/realm cho client, phù hợp HTTP authentication semantics.

**Câu 4.** Có nên trả Basic challenge khi API dùng JWT Bearer không?

**Đáp:** Không. Cần Bearer challenge theo cơ chế resource server/OAuth2 tương ứng.

**Câu 5.** ProblemDetail dùng Content-Type gì?

**Đáp:** `application/problem+json` với JSON representation theo RFC 9457.

**Câu 6.** Những field chuẩn của ProblemDetail là gì?

**Đáp:** `type`, `title`, `status`, `detail`, `instance`; một số là tùy chọn, và có thể có extensions được thiết kế rõ.

**Câu 7.** `type` hay `detail` nên dùng làm mã lỗi ổn định?

**Đáp:** `type` (hoặc một extension code ổn định) phù hợp hơn. Detail là mô tả có thể thay đổi/localize.

**Câu 8.** Vì sao không dùng `authException.getMessage()` làm response detail?

**Đáp:** Nó có thể lộ username existence, token, password-policy, metadata nội bộ hoặc chi tiết provider. Dùng thông báo công khai đã được review.

**Câu 9.** Custom AccessDeniedHandler có chắc format toàn bộ CSRF 403 không?

**Đáp:** Không. CsrfFilter có thể sử dụng handler khác; phải test và cấu hình chính điểm xử lý CSRF nếu muốn cùng schema.

**Câu 10.** Trong ví dụ, Basic password sai đi qua đâu?

**Đáp:** Qua HTTP Basic authentication filter sử dụng entry point được cấu hình ở `httpBasic(...)`. Vì vậy cần test password sai ngoài ca thiếu credentials.

**Câu 11.** Vì sao nên dùng `setStatus` thay `sendError` khi tự viết JSON?

**Đáp:** `sendError` có thể kích hoạt servlet error page/dispatch, dẫn tới HTML/double-write. Khi chủ động serialize, đặt status và viết body một lần.

**Câu 12.** HTTP 200 với body `{"status":403}` có hợp lý không?

**Đáp:** Không đối với thông báo lỗi HTTP thông thường. Status thực phải phản ánh thất bại để client/monitor/cache hoạt động đúng.

**Câu 13.** Một response lỗi không có `instance` có sai chuẩn không?

**Đáp:** Không. Instance là trường tùy chọn; nếu URL có thể làm lộ thông tin, bỏ trường có thể an toàn hơn.

**Câu 14.** Tại sao 403 từ gateway có thể không giống body trong Spring Security?

**Đáp:** Gateway tạo response trước khi request đến Spring app, nên handler trong ứng dụng không chạy.

**Câu 15.** Có thể dùng cả JSON custom và ProblemDetail trong cùng hệ thống không?

**Đáp:** Có, theo các version/loại client/endpoint đã được thiết kế rõ; không thay đổi ngầm schema mà client đang phụ thuộc.

**Câu 16.** Khi login form được thiết kế cho trình duyệt, anonymous thường nhận gì?

**Đáp:** Có thể nhận 302 redirect tới trang login thay vì 401 JSON; cần bảo vệ UX đúng flow, không ép tất cả endpoint về một response.

**Câu 17.** Vì sao phân quyền theo role không thay kiểm quyền trên từng resource?

**Đáp:** User có ROLE_USER vẫn có thể không được xem tài liệu của user/tenant khác. Service/method policy cần kiểm owner/tenant/permission riêng.

**Câu 18.** Làm thế nào kiểm tra writer không phá lỗi bảo mật?

**Đáp:** Test HTTP status, content type, body fields, 401 challenge, 403 permission denial, missing/invalid credentials, CSRF, CORS, fallback deny và case response committed theo hệ thống thực.

**Ghi nhớ:** **Lỗi từ Spring Security Servlet không tự động đi qua MVC advice. Dùng AuthenticationEntryPoint cho luồng yêu cầu đăng nhập, AccessDeniedHandler cho access denied thuộc phạm vi xử lý của nó; giữ đúng HTTP status và `WWW-Authenticate`, thiết kế JSON/ProblemDetail ổn định, tránh lộ thông tin, và kiểm tra CSRF/Bearer/gateway như các đường lỗi riêng.**