# Error response MVC trong xác thực HMAC request với Spring Security

## 1. Vì sao error response là một phần của thiết kế bảo mật?

Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client ký HTTP request bằng HMAC với shared secret. Server xây dựng canonical request theo hợp đồng gồm method, URI, header và/hoặc body digest, kiểm tra chữ ký, timestamp và nonce chống replay, trạng thái key rotation rồi mới xét quyền truy cập. Khi có lỗi ở bất kỳ bước nào, API cần trả **HTTP response nhất quán, có ý nghĩa đối với client nhưng không tiết lộ dữ liệu giúp người ngoài dò credential**.

Một lỗi thiết kế thường gặp là dùng cùng một hàm `throw new RuntimeException(...)` cho tất cả vấn đề hoặc đặt `@ControllerAdvice` rồi nghĩ rằng nó sẽ bắt được cả exception phát sinh từ Spring Security filter. Hậu quả có thể là:

- Chữ ký sai bị trả **500** hoặc body HTML mặc định thay vì response JSON ổn định.
- Client có thể phân biệt “key ID không tồn tại”, “secret đúng nhưng key đã REVOKED” qua thông báo công khai, tạo **credential-enumeration oracle**.
- HMAC đúng nhưng thiếu quyền tenant bị coi là lỗi xác thực, gây khó điều tra.
- Request body quá lớn bị đọc toàn bộ vào bộ nhớ rồi mới báo lỗi, gây rủi ro DoS.
- Registry/secret manager/replay store tạm thời không khả dụng lại làm hệ thống **fail open** hoặc trả thông tin nội bộ.
- Gateway và Spring MVC trả hai định dạng lỗi khác nhau khiến client retry sai.

Đề bài **Error response MVC** thuộc chương **Spring MVC integration** nhằm xây dựng một hợp đồng lỗi thống nhất qua **Servlet filter → Spring Security → DispatcherServlet → MVC controller**, đồng thời bảo vệ thông tin nhạy cảm và tính đúng đắn của xác thực HMAC.

### Tình huống ví dụ

Đối tác `partner-a` gọi `POST /api/hmac/payments` với key `partner-a-k4`, timestamp, nonce và signature. Những kết quả sau **không tương đương**:

| Tình huống | Bản chất |
| --- | --- |
| Không có `X-Signature` hoặc HMAC sai | Xác thực không thành công |
| K4 bị REVOKED, dù HMAC còn khớp với secret cũ | Credential không còn đủ điều kiện xác thực |
| HMAC đúng nhưng nonce đã dùng | Replay, không được xác thực request |
| HMAC đúng, client hợp lệ nhưng không có quyền tạo payment ở tenant B | Phân quyền từ chối |
| Body JSON sai cấu trúc sau khi xác thực | Lỗi dữ liệu đầu vào ở tầng MVC |
| Payload vượt giới hạn buffer HMAC | Request quá lớn, bị chặn trước xử lý nghiệp vụ |
| Vault không khả dụng | Lỗi hạ tầng xác thực; không đủ cơ sở chấp nhận request |

Một API rõ ràng phải phân loại những tình huống trên để tạo response, audit và metric phù hợp.

## 2. Các lớp xử lý lỗi trong Spring MVC và Spring Security

Với **Spring Boot 3 / Spring MVC (Jakarta Servlet) / Spring Security 6**, đường đi tổng quát:

~~~mermaid
flowchart TD
    A["HTTP request từ client"] --> B["Ingress / Proxy"]
    B --> C["Servlet FilterChain / SecurityFilterChain"]
    C --> D["HmacAuthenticationFilter"]
    D --> E{"Xác thực HMAC thành công?"}
    E -->|Không| F["AuthenticationEntryPoint → 401"]
    E -->|Có| G["SecurityContext: principal tin cậy"]
    G --> H["AuthorizationFilter / policy"]
    H -->|Thiếu quyền| I["AccessDeniedHandler → 403"]
    H -->|Có quyền| J["DispatcherServlet"]
    J --> K["HandlerMapping / Controller"]
    K --> L{"Dữ liệu và nghiệp vụ hợp lệ?"}
    L -->|Không| M["@RestControllerAdvice / HandlerExceptionResolver"]
    L -->|Có| N["2xx / kết quả nghiệp vụ"]
    B --> O["Lỗi ingress như 413, 502, 503"]
~~~

Đây là **luồng khái niệm**. Trong thực tế, thứ tự các filter và việc `ExceptionTranslationFilter` có bắt được một exception hay không phụ thuộc **vị trí phát sinh** trong chain.

| Điểm phát sinh lỗi | Thành phần xử lý điển hình | Lưu ý |
| --- | --- | --- |
| Custom HMAC filter trước các filter khác | `AuthenticationEntryPoint` được custom filter chủ động gọi, hoặc failure handler của authentication filter | Exception ném trước `ExceptionTranslationFilter` không tự được filter phía sau bắt |
| Authentication exception phát sinh phía sau `ExceptionTranslationFilter` | `ExceptionTranslationFilter` điều hướng tới `AuthenticationEntryPoint` | Phụ thuộc thứ tự filter |
| Access denied trong web authorization | `AccessDeniedHandler` khi đã xác thực, entry point khi chưa xác thực | Không nên coi thiếu credential là “403 vì thiếu quyền” |
| Parse JSON, Bean Validation, MVC binding | `HandlerExceptionResolver` / `@RestControllerAdvice` | Chạy trong vòng đời `DispatcherServlet` |
| Lỗi method/service được xử lý trong MVC | Advice hoặc exception resolver có phạm vi phù hợp | Không vô tình bắt rồi đổi mọi lỗi thành 400 |
| Lỗi do proxy/container sinh trước Spring | Ingress/container/error page | Không bảo đảm đi qua MVC advice |
| Response đã commit rồi exception phát sinh | Không thể đổi status/body đã gửi | Phải log, đóng/điều khiển kết nối theo cơ chế stack |

**Điểm cốt lõi:** `@RestControllerAdvice` không phải một cơ chế toàn năng để bắt mọi exception ở lớp Servlet filter. Ngược lại, `AuthenticationEntryPoint` không phải nơi xử lý `MethodArgumentNotValidException` của controller.

## 3. Chọn HTTP status theo ngữ nghĩa, không theo độ tiện lập trình

Bảng này là **hợp đồng ví dụ** cho API HMAC máy–máy, cần được chốt theo tiêu chuẩn HTTP và yêu cầu sản phẩm:

| HTTP status | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| **400 Bad Request** | Cú pháp request, JSON hoặc validation không hợp lệ; không phải cứ HMAC sai là 400 | JSON không parse được sau khi qua auth, trường nghiệp vụ sai |
| **401 Unauthorized** | Thiếu hoặc không đạt xác thực theo cơ chế HMAC | Key không hợp lệ, signature sai, credential bị thu hồi, replay |
| **403 Forbidden** | Đã xác thực nhưng không được phép thực hiện hành động | Client A cố gọi tài nguyên tenant B mà không có grant |
| **404 Not Found** | Resource không tồn tại hoặc chính sách che giấu sự tồn tại với người không có quyền | Client không được biết ID của resource thuộc tenant khác |
| **405 Method Not Allowed** | Endpoint tồn tại nhưng method không hỗ trợ | `PUT` vào route chỉ chấp nhận `POST`; giữ `Allow` header đúng |
| **413 Content Too Large** | Payload vượt giới hạn ingress/container/filter | Body HMAC JSON vượt ngưỡng buffer |
| **415 Unsupported Media Type** | Content-Type không được endpoint hỗ trợ | Gửi `text/plain` cho endpoint JSON bắt buộc |
| **422 Unprocessable Content** | Một số hợp đồng API dùng cho lỗi ngữ nghĩa nghiệp vụ trên payload đúng cú pháp | Giá trị vi phạm quy tắc nghiệp vụ và được API quy định là 422 |
| **429 Too Many Requests** | Bị giới hạn lưu lượng | Rate limit theo client/IP; `Retry-After` nếu có lịch retry |
| **500 Internal Server Error** | Lỗi server không được phân loại chi tiết với client | Bug hoặc lỗi bất ngờ, cần alert |
| **503 Service Unavailable** | Phụ trợ bắt buộc để xác thực bị lỗi và không thể tiếp tục an toàn, theo chính sách vận hành | Registry/secret manager/replay store không khả dụng |

`401` là tên chính thức “Unauthorized” trong HTTP, nhưng về ngữ nghĩa là **chưa có xác thực hợp lệ**. Trường hợp thiếu quyền sau khi đã xác thực thường là `403`, trừ khi API cố ý che resource bằng `404` theo chính sách nhất quán. Đừng trả `403` chỉ để người gọi phân biệt “key ID tồn tại nhưng không còn active”.

**Lưu ý `WWW-Authenticate`:** phản hồi 401 theo HTTP phải mang ít nhất một challenge `WWW-Authenticate` áp dụng cho cơ chế xác thực. HMAC signing không có một định dạng challenge duy nhất do Spring Security tự cung cấp. Nếu API định nghĩa scheme `HMAC`, có thể minh họa `WWW-Authenticate: HMAC realm="api"`, nhưng phải đặc tả scheme/challenge, cách client hiểu nó và khả năng tương thích trong hợp đồng của chính API. Không tự gửi `Bearer` challenge khi endpoint chỉ chấp nhận HMAC.

**Không lạm dụng `503`:** nếu request đã xác minh được credential sai thì trả lỗi xác thực; chỉ dùng 503 khi thiếu hệ thống bắt buộc khiến server **không thể quyết định** chính xác. Dù trả 503 hay 401, không được bỏ qua phép kiểm tra vì phụ trợ đang lỗi. Không coi một request lặp lại tự động là an toàn để retry: API có thao tác ghi cần idempotency contract riêng.

## 4. Thiết kế body lỗi ổn định: Problem Details

Một lựa chọn tốt cho API JSON là cấu trúc theo **Problem Details for HTTP APIs (RFC 9457)**, thường có media type `application/problem+json`. Spring Framework 6 có lớp `ProblemDetail`; tuy nhiên filter có thể không dùng cơ chế `HttpMessageConverter` giống controller, nên cần thống nhất cả **schema** lẫn cách ghi.

Ví dụ phản hồi công khai:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED",
  "requestId": "req-78a5b"
}
~~~

Header challenge `HMAC realm="api"` chỉ hợp lệ như một phần **giao thức HMAC tự thiết kế đã được công bố**, không phải chuẩn ký tự động của Spring. Với `type: "about:blank"`, `title` nên tương ứng status HTTP; `code` và `requestId` là các **extension fields** của API.

Nên bảo đảm:

- **Ổn định:** mỗi trường có kiểu dữ liệu rõ ràng; client không phải parse chuỗi `detail` để điều khiển nghiệp vụ.
- **An toàn:** `detail` không chứa key ID bị thu hồi, shared secret, expected signature, canonical bytes, stack trace, SQL error hay tên tenant cần bảo vệ.
- **Có thể truy vết:** `requestId` do server/gateway tin cậy tạo hoặc xác minh; không phản chiếu nguyên văn một chuỗi không giới hạn từ client.
- **Không nhầm lẫn:** `status` trong JSON phải đúng mã HTTP bên ngoài.
- **Có phân loại:** client dựa vào `code` công khai (ở mức ít tiết lộ), còn log nội bộ có mã nguyên nhân chi tiết hơn.
- **Giảm lưu dấu nhạy cảm:** đặt `Cache-Control: no-store` cho lỗi xác thực/quyền và nơi có thể chứa dữ liệu người dùng; không thêm dữ liệu nhạy cảm vào path `instance` hoặc query string.
- **Content negotiation rõ ràng:** nếu `Accept` không hỗ trợ JSON problem, cần chính sách nhất quán; không ngẫu nhiên trả HTML giữa gateway và MVC.

### Một bộ mã lỗi công khai tối thiểu

| `code` công khai | HTTP | Khi nào dùng |
| --- | --- | --- |
| `AUTHENTICATION_FAILED` | 401 | Gom key không tồn tại, signature sai, hết hạn, revoked, replay |
| `ACCESS_DENIED` | 403 | Principal đã xác thực nhưng thiếu quyền |
| `INVALID_REQUEST` | 400 | JSON hoặc dữ liệu không hợp lệ |
| `PAYLOAD_TOO_LARGE` | 413 | Body vượt giới hạn |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Media type không hỗ trợ |
| `RATE_LIMITED` | 429 | Quá quota |
| `DEPENDENCY_UNAVAILABLE` | 503 | Phụ trợ bắt buộc không khả dụng |
| `INTERNAL_ERROR` | 500 | Lỗi ngoài dự kiến |

Không nhất thiết phải cung cấp từng mã nội bộ như `KEY_NOT_FOUND`, `KEY_REVOKED`, `SIGNATURE_MISMATCH`, `REPLAY_DETECTED` cho caller chưa xác thực. Có thể dùng những mã này trong **security audit/log riêng** để hỗ trợ điều tra.

## 5. Phân tách lỗi HMAC và lỗi phân quyền tenant

Một request ký bằng secret hợp lệ có thể không được phép thực hiện hành động. Điều này đặc biệt quan trọng trong hệ thống đa client/tenant.

Ví dụ client `partner-a` sở hữu `partner-a-k4` thuộc `tenant-a`, nhưng gửi HMAC đúng cho `tenant-b`. Nếu không có delegated grant phù hợp, có hai kết luận tách biệt:

1. **Authentication:** chữ ký đúng, timestamp/nonce hợp lệ, credential active; principal đã được xác nhận là `partner-a`.
2. **Authorization:** `partner-a` không có quyền `CREATE_PAYMENT` ở `tenant-b`; trả 403 hoặc 404 theo chính sách che resource.

Đừng cho `@RequestHeader("X-Tenant-Id")` thay thế authenticated tenant context, dù header đã nằm trong canonical request. Client sở hữu secret vẫn có thể tự ký request cho tenant khác; HMAC bảo vệ **tính toàn vẹn**, không tự cấp quyền.

Mô hình quyết định:

~~~mermaid
flowchart TD
    A["Request + keyId + signature + tenant"] --> B{"HMAC, key state, timestamp, nonce hợp lệ?"}
    B -->|Không| C["401 AUTHENTICATION_FAILED"]
    B -->|Có| D["Authenticated principal + owner tenant"]
    D --> E{"Có quyền với target tenant, action, resource?"}
    E -->|Không| F["403 ACCESS_DENIED hoặc 404 theo policy"]
    E -->|Có| G["Controller / business service"]
    G --> H{"Payload/nghiệp vụ hợp lệ?"}
    H -->|Không| I["400 / 422 theo hợp đồng"]
    H -->|Có| J["2xx / 201"]
~~~

**Không trả dữ liệu resource rồi mới kiểm tra quyền.** Các truy vấn cần scope bằng `effectiveTenantId` đã được xác thực và phân quyền. Một response lỗi phù hợp phải đi cùng **không có side effect trái phép**: dữ liệu tenant B không bị đọc/ghi dù client A nhận 403.

## 6. Xử lý AuthenticationException ngay tại custom HMAC filter

`OncePerRequestFilter` thường được thêm vào `SecurityFilterChain` trước `UsernamePasswordAuthenticationFilter`. Nếu nó tự gọi `AuthenticationManager.authenticate(...)` và ném `AuthenticationException` **trước khi** `ExceptionTranslationFilter` được gọi, filter phía sau không thể bắt exception phát sinh phía trước nó theo cách thông thường.

Vì vậy custom filter nên:

1. Chuẩn bị evidence từ method, URI, header và body bytes theo hợp đồng ký.
2. Gọi manager/provider; provider xác minh key state, HMAC, timestamp/nonce.
3. Nếu nhận `AuthenticationException`, **không gọi tiếp `chain.doFilter`**; dọn `SecurityContext`, gọi `AuthenticationEntryPoint` hoặc failure handler.
4. Chỉ sau thành công mới tạo `SecurityContext` và truyền wrapper giữ nguyên body cho MVC.
5. Tách lỗi kích thước body (413) và lỗi hạ tầng (503 theo chính sách) khỏi lỗi HMAC sai (401).

Một cấu trúc minh họa:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

// Các type BoundedBodyRequest, HmacRequestParser, ... là interface
// hoặc class nội bộ do dự án hiện thực, không phải API có sẵn của Spring.
final class HmacSecurityFilter extends OncePerRequestFilter {
    private final AuthenticationManager manager;
    private final HmacRequestParser parser;
    private final AuthenticationEntryPoint entryPoint;
    private final ErrorBodyWriter errors;

    HmacSecurityFilter(
            AuthenticationManager manager,
            HmacRequestParser parser,
            AuthenticationEntryPoint entryPoint,
            ErrorBodyWriter errors) {
        this.manager = manager;
        this.parser = parser;
        this.entryPoint = entryPoint;
        this.errors = errors;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest req,
            HttpServletResponse res,
            FilterChain chain) throws IOException, ServletException {

        BoundedBodyRequest buffered;
        Authentication result;
        try {
            buffered = BoundedBodyRequest.capture(req, 1024 * 1024);
            result = manager.authenticate(parser.parse(buffered));
            if (result == null || !result.isAuthenticated()) {
                throw new org.springframework.security.authentication
                    .BadCredentialsException("authentication_failed");
            }
        } catch (PayloadTooLargeException ex) {
            SecurityContextHolder.clearContext();
            errors.write(req, res, 413, "PAYLOAD_TOO_LARGE",
                "Request body is too large.");
            return;
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(req, res, ex);
            return;
        } catch (AuthenticationDependencyException ex) {
            SecurityContextHolder.clearContext();
            errors.write(req, res, 503, "DEPENDENCY_UNAVAILABLE",
                "Authentication is temporarily unavailable.");
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(buffered, res);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Đây là **mã khung**, không biên dịch độc lập vì `BoundedBodyRequest`, `PayloadTooLargeException`, `HmacRequestParser`, `AuthenticationDependencyException` và `ErrorBodyWriter` là thành phần cần hiện thực. `AuthenticationDependencyException` ở ví dụ là **runtime exception riêng, không kế thừa `AuthenticationException`**, để nhánh 503 không bị nhánh 401 bắt trước. Nếu dự án chọn kiểu ngoại lệ khác, hãy sắp xếp `catch` và cách phân loại tương ứng.

`BoundedBodyRequest` phải đọc tối đa `limit + 1` bytes, từ chối khi vượt ngưỡng và tạo stream đọc lại body cho controller. `ContentCachingRequestWrapper` **không mặc nhiên rewind** input stream đã được filter đọc. Khi thực thi async, multipart hoặc streaming, cần adapter phù hợp chứ không áp dụng bừa wrapper đồng bộ.

**Không bắt chung `Exception` rồi gọi `chain.doFilter`.** Khi không thể chứng minh xác thực thành công, hệ thống phải fail closed.

## 7. Một writer chung cho filter và Spring MVC

Để tránh filter trả JSON dạng A còn `@RestControllerAdvice` trả JSON dạng B, có thể dùng một **error representation chung**, nhưng tùy tầng sẽ có cách gửi khác nhau.

Ví dụ Java 17:

~~~java
// Các trường type/title/status/detail thuộc Problem Details;
// code và requestId là phần mở rộng do API này định nghĩa.
public record ApiProblem(
    String type,
    String title,
    int status,
    String detail,
    String code,
    String requestId
) {}
~~~

Một factory an toàn cho các trường công khai:

~~~java
import org.springframework.http.HttpStatus;

final class ApiProblemFactory {
    static ApiProblem create(
            int status,
            String code,
            String safeDetail,
            String requestId) {
        String title = HttpStatus.valueOf(status).getReasonPhrase();
        return new ApiProblem(
            "about:blank", title, status, safeDetail, code, requestId);
    }
}
~~~

**Đừng** truyền trực tiếp `exception.getMessage()` vào `safeDetail`; ngoại lệ có thể chứa key ID, endpoint, path nội bộ, lỗi DB hoặc secret. Các thông báo `safeDetail` phải được quyết định từ **bảng ánh xạ lỗi công khai**, không phản chiếu dữ liệu không tin cậy. `requestId` phải được sinh hoặc chuẩn hóa bởi thành phần đáng tin cậy và có giới hạn độ dài.

Writer ở tầng Servlet:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;

final class ErrorBodyWriter {
    private final ObjectMapper mapper;
    private final RequestIdProvider requestIds;

    ErrorBodyWriter(ObjectMapper mapper, RequestIdProvider requestIds) {
        this.mapper = mapper;
        this.requestIds = requestIds;
    }

    void write(
            HttpServletRequest request,
            HttpServletResponse response,
            int status,
            String code,
            String safeDetail) throws IOException {
        if (response.isCommitted()) {
            // Không thể ghi đè status/body đã gửi.
            return;
        }
        ApiProblem problem = ApiProblemFactory.create(
            status, code, safeDetail, requestIds.getOrCreate(request));

        response.setStatus(status);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");
        mapper.writeValue(response.getOutputStream(), problem);
    }
}

interface RequestIdProvider {
    // Trả server-generated ID hoặc ID đã được gateway kiểm chứng.
    String getOrCreate(HttpServletRequest request);
}
~~~

Trong ví dụ, `ObjectMapper` cần được cấu hình đủ để serialize record của Java 17. Khi writer gọi `response.getOutputStream()`, không nên gọi tiếp `sendError(...)`, `getWriter()` hay một bước chuyển response khác làm body bị ghi hai lần. Nếu muốn thu thập metric/alert khi response đã committed, thực hiện ngoài writer; việc return ở đây không có nghĩa lỗi được xử lý đầy đủ.

Các response 401 còn cần `WWW-Authenticate` theo scheme HMAC đã công bố, thường được entry point thiết lập **trước khi** gọi writer. `ErrorBodyWriter` không tự gán challenge cho mọi status.

### Tại sao không chỉ dùng ProblemDetail của Spring MVC trong filter?

`ProblemDetail` và `ResponseEntityExceptionHandler` thuận tiện ở MVC, nhưng **custom Servlet filter không đi qua cùng pipeline xử lý body của controller**. Filter có thể dùng `ObjectMapper` và DTO thống nhất hoặc gọi một component serializer được cấu hình; quan trọng là body/status/header phải tương thích. Nếu chọn `ProblemDetail` cho MVC và DTO cho filter, hãy kiểm thử chúng tạo cùng JSON schema và extension `code`/`requestId`, không dựa vào giả định.

## 8. AuthenticationEntryPoint: viết 401 an toàn

Một entry point dùng writer chung, không trả lý do chi tiết theo trạng thái key:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;

final class HmacAuthenticationEntryPoint implements AuthenticationEntryPoint {
    private final ErrorBodyWriter writer;

    HmacAuthenticationEntryPoint(ErrorBodyWriter writer) {
        this.writer = writer;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException failure)
            throws IOException, ServletException {

        // Scheme HMAC là ví dụ thuộc hợp đồng API này,
        // không phải challenge chuẩn mà Spring tự cung cấp.
        response.setHeader("WWW-Authenticate", "HMAC realm=\"api\"");
        writer.write(request, response, 401,
            "AUTHENTICATION_FAILED",
            "Authentication is required or invalid.");
    }
}
~~~

Những lỗi như `BadCredentialsException`, key không tồn tại, HMAC sai, key REVOKED và nonce đã dùng có thể đều ra **cùng body công khai**. Chênh lệch timing hay HTTP header vẫn có thể tạo oracle; cần rate limiting, thống nhất luồng xử lý và đo tác động. Không tuyên bố toàn bộ pipeline database/network “constant-time”; phép so sánh MAC nên dùng `MessageDigest.isEqual` trên byte arrays có format/độ dài đã kiểm tra.

Trong ứng dụng có nhiều cơ chế xác thực (ví dụ HMAC cho máy–máy, bearer token cho người dùng), entry point phải phù hợp từng `SecurityFilterChain`. Không trả `WWW-Authenticate: HMAC` từ một endpoint chỉ dùng Bearer hoặc ngược lại.

## 9. AccessDeniedHandler: viết 403 khi đã xác thực

Khi `Authentication` đã hợp lệ nhưng quyền bị từ chối, Spring Security có thể điều hướng lỗi `AccessDeniedException` tới `AccessDeniedHandler` nếu exception nằm trong vùng `ExceptionTranslationFilter` xử lý và principal được xem là đã xác thực.

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;

final class HmacAccessDeniedHandler implements AccessDeniedHandler {
    private final ErrorBodyWriter writer;

    HmacAccessDeniedHandler(ErrorBodyWriter writer) {
        this.writer = writer;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException failure)
            throws IOException, ServletException {

        writer.write(request, response, 403,
            "ACCESS_DENIED",
            "You are not permitted to perform this action.");
    }
}
~~~

**Lưu ý kiểm thử:** một `AccessDeniedException` do code nghiệp vụ ném **sau khi MVC đã xử lý bằng `HandlerExceptionResolver` riêng** có thể không đi theo cùng con đường với exception do `AuthorizationFilter` ném. Cần thiết kế và kiểm thử một chiến lược xử lý phân quyền thống nhất; không nghĩ rằng cấu hình `AccessDeniedHandler` bảo đảm tự động bắt mọi lỗi business policy trong toàn ứng dụng.

Có thể chọn trả 404 khi muốn che giấu sự tồn tại resource tenant khác; khi đó phải nhất quán ở endpoint liên quan, không để 403/404 hoặc nội dung phản hồi vô tình tiết lộ resource có tồn tại. Audit nội bộ vẫn ghi nguyên nhân thiếu quyền.

## 10. @RestControllerAdvice: xử lý lỗi thuộc vòng đời MVC

Spring MVC dùng `HandlerExceptionResolver`; `@RestControllerAdvice` giúp ánh xạ lỗi do controller, validation hoặc chuyển đổi dữ liệu phát sinh. Ví dụ:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
final class HmacApiMvcAdvice {
    private final RequestIdProvider requestIds;

    HmacApiMvcAdvice(RequestIdProvider requestIds) {
        this.requestIds = requestIds;
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiProblem> badJson(
            HttpMessageNotReadableException ex,
            HttpServletRequest request) {
        return respond(request, 400,
            "INVALID_REQUEST", "Request body is malformed.");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiProblem> invalidBody(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {
        return respond(request, 400,
            "INVALID_REQUEST", "Request validation failed.");
    }

    private ResponseEntity<ApiProblem> respond(
            HttpServletRequest request,
            int status,
            String code,
            String safeDetail) {
        ApiProblem body = ApiProblemFactory.create(
            status, code, safeDetail, requestIds.getOrCreate(request));

        return ResponseEntity.status(status)
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .header("Cache-Control", "no-store")
            .body(body);
    }
}
~~~

Hai exception handler trên bao phủ **một số** lỗi MVC, không tự xử lý hết `405`, `415`, `404`, `HandlerMethodValidationException` hoặc lỗi từ body deserialization ở các framework khác. Nếu cần một hợp đồng thống nhất cho **tất cả** lỗi MVC, có thể kế thừa `ResponseEntityExceptionHandler` và override các phương thức phù hợp với version Spring Framework đang dùng, hoặc cấu hình `HandlerExceptionResolver`/error handling chuyên biệt. Không bắt `Exception.class` rồi trả 400 cho mọi lỗi, vì bug và sự cố hạ tầng cần phản ánh đúng và được giám sát.

Đừng đưa `BindingResult` đầy đủ, rejected value, SQL exception hoặc stack trace vào response công khai. Nếu muốn trả lỗi theo field, dùng allowlist field public và thông báo đã lọc, giới hạn tổng kích thước lỗi.

### Thứ tự xác thực và validation

Với đường API HMAC được bảo vệ đúng, request phải đi qua xác thực trước khi `@Valid @RequestBody` thực hiện nghiệp vụ. Một body JSON sai nhưng chữ ký HMAC cũng sai thường được **từ chối ở xác thực**, không để lộ chi tiết validation cho bên chưa chứng minh danh tính. Khi HMAC đã đúng mà JSON vẫn sai, MVC có thể trả 400.

Trật tự thực tế có thể bị ảnh hưởng bởi gateway/filter kiểm tra body-size, media type hoặc cú pháp đơn giản trước khi tính HMAC. Hợp đồng cần xác định các lỗi tiền xác thực nào có thể công khai và tránh để chúng tiết lộ thông tin credential.

## 11. Cấu hình SecurityFilterChain cho đường HMAC stateless

Ví dụ cấu hình Spring Security 6 ở mức ý tưởng, giả sử custom filter, entry point và denied handler đã được tạo và wiring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
class HmacApiSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain hmacChain(
            HttpSecurity http,
            HmacSecurityFilter filter,
            HmacAuthenticationEntryPoint entryPoint,
            HmacAccessDeniedHandler accessDenied) throws Exception {

        return http
            .securityMatcher("/api/hmac/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(accessDenied))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .addFilterBefore(
                filter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}
~~~

Cấu hình ví dụ áp dụng cho **API máy–máy stateless không dựa vào cookie/session trình duyệt**. Không nhân rộng `csrf.disable()` sang những route dùng session/cookie. Các filter chain khác phải có matcher và thứ tự rõ ràng.

Nếu `HmacSecurityFilter` là một bean kiểu `Filter`, Spring Boot có thể còn tự đăng ký nó vào Servlet container ngoài security chain. Khi đó filter có nguy cơ chạy **hai lần**, nonce lần hai bị coi là replay, và error response có thể bị ghi hai lần. Cần kiểm tra việc đăng ký/disable auto-registration tương ứng hoặc tạo filter theo cách chỉ nằm trong chain, rồi test thực tế.

`.authenticated()` chỉ yêu cầu principal được xác thực, **không** tự kiểm tra tenant/action/resource. Authorization nghiệp vụ phải dùng principal và tenant context đáng tin cậy. Nếu sử dụng method security, phải xác nhận ngoại lệ thiếu quyền đi qua đúng chiến lược xử lý lỗi.

## 12. Replay, key rotation và nguyên tắc fail closed

Dù chủ đề bài là error response, **nội dung trả lỗi phải phản ánh đúng quyết định bảo mật**.

### Timestamp và nonce

Server kiểm tra timestamp theo đồng hồ server và cửa sổ cho phép; sau HMAC đúng, ghi nonce bằng thao tác nguyên tử nếu chưa dùng trong kho dùng chung giữa các verifier. Một `HashSet` trong một JVM không chống replay xuyên instance.

Các lỗi timestamp quá cũ, quá xa tương lai, nonce đã tồn tại và chữ ký không hợp lệ có thể cùng trả `401 AUTHENTICATION_FAILED`. Log nội bộ phân biệt `TIMESTAMP_OUT_OF_WINDOW`, `REPLAY_DETECTED`, `SIGNATURE_MISMATCH`. Khi nonce store không khả dụng, không được bỏ qua kiểm tra chỉ để client nhận 2xx; dùng phản hồi hạ tầng theo chính sách và alert.

### Key rotation và revoked key

Trong thời gian xoay khóa, client có thể chuyển K3 → K4, hai version đồng thời ACTIVE theo kế hoạch. Nhưng request khai K4 phải xác minh bằng **đúng K4**; không fallback secret K3 khi K4 sai. Sau khi K3 REVOKED, chữ ký tính bằng K3 dù chính xác cũng không còn đủ điều kiện.

Public response cho K3 REVOKED và HMAC không hợp lệ nên tránh tiết lộ khác biệt định danh secret. Trong audit bảo mật có thể phân biệt `CREDENTIAL_REVOKED`, `CLIENT_DISABLED`, `KEY_EXPIRED`. Sự kiện thu hồi phải được truyền đến tất cả gateway/verifier với độ mới phù hợp; chỉ update database không chứng minh cache đã ngừng chấp nhận K3.

### Phụ trợ không khả dụng

Registry, secret manager hoặc replay store là thành phần bắt buộc trong đường xác thực. Nếu mất khả năng kiểm tra trạng thái hoặc chữ ký, không xác thực “tạm” bằng secret cũ từ cache không đủ độ mới hay bỏ nonce. **Fail closed** nghĩa là không thực thi nghiệp vụ khi không chứng minh được điều kiện bảo mật, không nhất thiết mọi trường hợp đều trả cùng HTTP status. Cần thống nhất giữa `503`, `401` hoặc response vận hành khác theo chính sách đã thiết kế, và kiểm thử đường retry.

## 13. Gateway, error dispatch và các phản hồi không do MVC tạo

Trong kiến trúc nhiều tầng, một response 401 có thể do gateway, Spring Security hoặc ứng dụng khác trả. Một lỗi 413 có thể được ingress từ chối **trước khi request đến JVM**. Vì vậy, chỉ viết `@RestControllerAdvice` chưa đảm bảo client luôn nhận cùng body JSON.

Những trường hợp đặc biệt:

| Tình huống | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Ingress từ chối body lớn | HTML error page không cùng schema | Cấu hình ingress error response nếu có, client chấp nhận sai khác đã công bố |
| Proxy timeout/502 | Client hiểu nhầm lỗi HMAC | Phân biệt response gateway và app; correlation ID xuyên tầng |
| Servlet container tạo error page | Lộ path/stack trace hoặc HTML | Cấu hình production error handling, không dựa hoàn toàn vào MVC advice |
| `sendError()` trong filter | Container có thể thực hiện error dispatch và thay body | Nếu cần body JSON chủ động, dùng writer/status và tránh ghi lại |
| Spring Security chạy lại ở `ERROR` dispatch | Filter có thể xác thực lại, ghi nonce trùng | Kiểm tra dispatcher types và hành vi once-per-request |
| Response đã commit rồi lỗi | Không thể đổi thành 401/500 sạch | Log và xử lý kết nối; không ghi thêm JSON chồng lên |
| CORS preflight `OPTIONS` | Không có HMAC headers nên bị chặn nhầm | Cấu hình CORS và phạm vi HMAC phù hợp, không mở bypass cho request nghiệp vụ |
| HEAD hoặc bodyless response | Không được gửi payload theo cách vi phạm HTTP | Xử lý đúng method/status, không ép JSON body mọi trường hợp |

Nếu gateway định thay đổi hoặc giữ `WWW-Authenticate`, `Retry-After`, `Cache-Control` hoặc `Content-Type`, cần kiểm tra end-to-end. Đừng để gateway vô tình biến `401` thành `200` với body lỗi, hoặc mất các header cần thiết.

**Bảo vệ thông tin nội bộ:** Không phản chiếu toàn bộ URL chứa query nhạy cảm, header `Authorization`, HMAC signature, shared secret hoặc exception chain vào `detail`, `instance` hay HTML error page.

## 14. Kiểm thử response bằng MockMvc và qua gateway thật

### Ma trận kết quả

| Test ID | Dữ liệu đầu vào / trạng thái | HTTP kỳ vọng | Điều cần assert thêm |
| --- | --- | --- | --- |
| ERR-01 | Không có HMAC headers | 401 | Problem JSON an toàn, controller không chạy |
| ERR-02 | Key ID không tồn tại | 401 | Body công khai giống lỗi signature sai |
| ERR-03 | HMAC sai với key tồn tại | 401 | Không ghi nonce, không gọi nghiệp vụ |
| ERR-04 | Key REVOKED nhưng HMAC đúng | 401 | Không lộ trạng thái revoke |
| ERR-05 | Client DISABLED | 401 | Không nhận key khác cùng client |
| ERR-06 | Timestamp quá cũ/quá tương lai | 401 | Mã nội bộ timestamp, không lộ chi tiết |
| ERR-07 | Nonce trùng trên hai verifier | 401 ở lần sau | Replay store dùng chung, atomic |
| ERR-08 | HMAC đúng, thiếu quyền API | 403 | `ACCESS_DENIED`, side effect bằng 0 |
| ERR-09 | Client A ký cho tenant B không có grant | 403 hoặc 404 theo policy | Không rò dữ liệu tenant B |
| ERR-10 | JSON không parse được sau HMAC đúng | 400 | `INVALID_REQUEST`, không lộ raw body |
| ERR-11 | DTO vi phạm Bean Validation | 400 | Không lộ rejected value nhạy cảm |
| ERR-12 | Body vượt giới hạn | 413 | Filter dừng sớm, không buffer vô hạn |
| ERR-13 | Content-Type không hỗ trợ | 415 | Cấu trúc lỗi thống nhất |
| ERR-14 | Method không được phép | 405 | Header `Allow` đúng |
| ERR-15 | Client vượt rate limit | 429 | `Retry-After` nếu được hợp đồng yêu cầu |
| ERR-16 | Vault/registry/nonce store tạm không sẵn sàng | 503 theo policy | Fail closed và alert |
| ERR-17 | Filter phát sinh `AuthenticationException` trước `ExceptionTranslationFilter` | 401 | Entry point thực sự được gọi |
| ERR-18 | Controller ném `HttpMessageNotReadableException` | 400 | MVC advice hoạt động |
| ERR-19 | 401 do gateway tạo, không tới Spring | Theo gateway contract | Không giả định MVC advice xử lý |
| ERR-20 | Filter bị đăng ký hai lần | Cần phát hiện lỗi cấu hình | Không ghi nonce hai lần, không double-write |
| ERR-21 | Response đã commit rồi lỗi | Không viết body lỗi thứ hai | Log/trace nguyên nhân |
| ERR-22 | Signed URI bị gateway rewrite khác hợp đồng | 401 | Internal `SIGNATURE_MISMATCH`, không tiết lộ canonical |
| ERR-23 | Một request đúng sau request 401 trên cùng thread | 2xx nếu đủ quyền | Không còn SecurityContext của request trước |
| ERR-24 | Request dùng `Accept: application/problem+json` | Lỗi đúng media type | `status` body khớp status HTTP |
| ERR-25 | Hệ thống trả exception chi tiết trong chế độ dev | Production không làm vậy | Không lộ stack trace, SQL, secret |

Một unit test ngắn cho entry point:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import com.fasterxml.jackson.databind.ObjectMapper;

class HmacEntryPointTest {
    @Test
    void badSignatureGivesGenericProblem() throws Exception {
        RequestIdProvider ids = request -> "req-test-01";
        ErrorBodyWriter writer =
            new ErrorBodyWriter(new ObjectMapper(), ids);
        HmacAuthenticationEntryPoint entry =
            new HmacAuthenticationEntryPoint(writer);

        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/api/hmac/payments");
        MockHttpServletResponse response =
            new MockHttpServletResponse();

        entry.commence(request, response,
            new BadCredentialsException(
                "key-partner-a-k4 was rejected internally"));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentType())
            .startsWith("application/problem+json");
        assertThat(response.getContentAsString())
            .contains("AUTHENTICATION_FAILED")
            .doesNotContain("key-partner-a-k4");
        assertThat(response.getHeader("Cache-Control"))
            .isEqualTo("no-store");
    }
}
~~~

Test trên dùng Spring Test, Jackson và AssertJ. Trong ứng dụng thật, cần thêm test cho **challenges**, response JSON parse được, không duplicate status/body và thống nhất với MVC advice. `RequestIdProvider` ở ví dụ trả ID tĩnh chỉ phục vụ test; production phải tạo hoặc xác thực ID qua trust boundary, giới hạn độ dài.

### Test thực qua SecurityFilterChain

Trong `MockMvc` với Spring Security chain thực, ký HMAC bằng **test signer độc lập** với verifier. Tạo ba request:

1. HMAC không hợp lệ, có body JSON hợp lệ: kỳ vọng 401, controller không được gọi.
2. HMAC hợp lệ nhưng JSON sai: kỳ vọng 400 từ MVC, `@RestControllerAdvice` trả schema lỗi thống nhất.
3. HMAC hợp lệ và JSON hợp lệ nhưng principal thiếu quyền: kỳ vọng 403/404 theo policy, không có side effect.

Nếu chỉ mock `AuthenticationManager` luôn thành công, test không chứng minh HMAC thật đã hoạt động. Nên có lớp integration test với credential registry, secret thử nghiệm và nonce store thực hoặc implementation có tính chất nguyên tử tương đương.

### Test end-to-end qua proxy

Thực hiện cùng bộ case qua ingress/gateway để xác minh:

- Proxy có trả lỗi trước app và schema khác không?
- Header `WWW-Authenticate`, `Content-Type`, `Cache-Control`, `Retry-After` có bị bỏ không?
- URI rewritten có làm HMAC sai không, và lỗi công khai có an toàn không?
- Key revoke có lan truyền kịp đến tất cả region/verifier theo cam kết không?
- Gateway có thay mã HTTP hoặc body lỗi từ app thành HTML/200 không?

## 15. Observability: phân loại sâu trong nội bộ, đơn giản ở public API

Để vận hành HMAC, cần phân biệt lỗi thực trong telemetry mà không tạo oracle cho client.

| Internal reason | Public code | Gợi ý điều tra |
| --- | --- | --- |
| `KEY_NOT_FOUND` | `AUTHENTICATION_FAILED` | Kiểm tra key ID/client registry |
| `SIGNATURE_MISMATCH` | `AUTHENTICATION_FAILED` | Canonical request, proxy rewrite, secret/config |
| `KEY_REVOKED` | `AUTHENTICATION_FAILED` | Key rotation/thu hồi |
| `CLIENT_DISABLED` | `AUTHENTICATION_FAILED` | Chính sách khóa client |
| `TIMESTAMP_OUT_OF_WINDOW` | `AUTHENTICATION_FAILED` | Clock skew, lỗi timestamp của client |
| `NONCE_REUSED` | `AUTHENTICATION_FAILED` | Replay, retry không ký lại |
| `TENANT_PERMISSION_DENIED` | `ACCESS_DENIED` | Grant/owner/action/resource |
| `JSON_PARSE_ERROR` | `INVALID_REQUEST` | Chuyển đổi dữ liệu MVC |
| `BODY_TOO_LARGE` | `PAYLOAD_TOO_LARGE` | Giới hạn ingress/container/filter |
| `SECRET_STORE_UNAVAILABLE` | `DEPENDENCY_UNAVAILABLE` | Vault/secret manager |
| `REPLAY_STORE_UNAVAILABLE` | `DEPENDENCY_UNAVAILABLE` | Kho nonce và khả năng fail closed |

Audit nội bộ nên ghi request ID/correlation ID, route, verifier instance, trạng thái kết quả, internal reason code, thời điểm và policy/key revision khi phù hợp. Principal/key ID/tenant ID cần được xử lý như dữ liệu có thể nhạy cảm: phân quyền truy cập, giới hạn retention và tránh trở thành nhãn metric cardinality lớn.

Không log shared secret, full signature, raw body nhạy cảm, canonical request đầy đủ hay header chứa dữ liệu bảo mật. Khi cần debug HMAC mismatch, dùng **test vector không nhạy cảm** cho canonical bytes, log phiên bản contract, route và thông tin giới hạn, không dump production payload.

Có thể theo dõi latency `AuthenticationManager`, tỷ lệ 401/403/413/503, lỗi gateway canonicalization, lag event revoke và tình trạng nonce store. Những metric này cần giúp phân biệt sự cố bảo mật với lỗi tích hợp client và vận hành.

## 16. Những lỗi triển khai thường gặp

### A. Một global exception handler bắt mọi lỗi thành HTTP 200

Một API trả `HTTP 200` và body `{"success":false}` khi HMAC sai làm cache, retry policy, gateway metrics và client sai nghĩa. Dùng HTTP status phản ánh kết quả thật, có body lỗi cấu trúc ổn định.

### B. Đẩy `BadCredentialsException.getMessage()` thẳng vào `detail`

Thông báo chứa “key partner-a-k4 revoked” cho phép dò key version. Ánh xạ ra `AUTHENTICATION_FAILED` chung; giữ nguyên nhân chi tiết trong log bảo mật.

### C. Dùng `@ControllerAdvice` để bắt ngoại lệ trước DispatcherServlet

Filter ném exception khi chưa vào MVC, advice không nhất thiết chạy. Dùng entry point/failure handler của Spring Security hoặc xử lý chủ động tại filter.

### D. Trả `403` cho cả HMAC sai lẫn không đủ quyền

Mất ranh giới xác thực–phân quyền, khó xử lý client và audit. `401` dành cho thiếu/sai xác thực theo contract; `403` cho principal đã xác thực nhưng không đủ quyền.

### E. Gateway trả body HTML trong khi API cam kết JSON

Client chỉ parse JSON sẽ gặp lỗi thứ cấp; telemetry khó đối chiếu. Cấu hình tầng gateway/container phù hợp, đồng thời ghi rõ giới hạn phần nào không do ứng dụng kiểm soát.

### F. Error handler đọc request body lần nữa

Filter đã tiêu thụ stream; handler đọc lại body gây lỗi hoặc phát sinh log nhạy cảm. Error response không cần in toàn bộ request; dùng request ID/metadata không nhạy cảm.

### G. Filter tiếp tục chain sau khi gọi entry point

Controller vẫn chạy dù response đang 401, thậm chí sửa dữ liệu hoặc ném lỗi “response already committed”. Mỗi nhánh lỗi phải **return** và dọn context.

### H. Response 503 khiến client tự động retry request ghi dữ liệu không an toàn

Một sự cố mạng có thể khiến client không biết server đã xử lý nghiệp vụ chưa. API cần idempotency key/transaction semantics rõ, tránh retry vô điều kiện chỉ dựa status.

### I. Thiếu kiểm soát thông tin khi trả 404 để che resource

Dùng 404 cho một resource tenant khác nhưng trả response thời gian khác biệt nhiều hoặc thông báo nội bộ có tenant ID, vẫn có nguy cơ bị suy đoán. Cần kiểm tra cả body, header, timing và logs.

### J. Key rotation fallback làm lỗi chữ ký bị che

Khi request khai key K4 nhưng server thử K3 sau mismatch, key bị thu hồi có thể tiếp tục có hiệu lực. Xác minh đúng key ID, không fallback; nếu không hợp lệ trả 401 chung.

## 17. Bài tập thực hành

Một hệ thống Spring MVC có `HmacFilter` chạy trước `UsernamePasswordAuthenticationFilter`. Filter gọi `AuthenticationManager` để xác minh K4. Nếu signature sai, nó `throw new BadCredentialsException("key K4 revoked")` và mong `@ControllerAdvice` trả JSON. Khi client ký đúng nhưng thiếu quyền tenant B, controller trả 401. Khi nonce store lỗi, code bỏ qua nonce rồi xử lý tiếp. Một API endpoint khác trả HTML 413 từ gateway.

Hãy xác định:

1. Lỗi nào làm `@ControllerAdvice` không chắc bắt được exception HMAC?
2. Nên trả HTTP status và public code nào khi signature sai, K4 revoked, nonce trùng?
3. Khi HMAC đúng nhưng thiếu quyền tenant B, nên dùng status nào và side effect mong đợi?
4. Vì sao không được bỏ qua nonce khi replay store mất kết nối? Status nào có thể dùng cho dependency failure?
5. Làm thế nào để filter và MVC cùng dùng cấu trúc `application/problem+json`?
6. Có thể dùng `exception.getMessage()` làm public `detail` không?
7. Vì sao gateway 413 HTML không thể sửa chỉ bằng MVC advice?
8. Khi gửi HTTP 401, cần chú ý header nào theo giao thức HTTP và hợp đồng HMAC?

**Hướng giải:** custom filter phải xử lý `AuthenticationException` ở đúng vị trí bằng `AuthenticationEntryPoint`/failure handler; HMAC sai, revoked và replay có thể cùng ra 401 với `AUTHENTICATION_FAILED` chung. Thiếu quyền sau xác thực là 403/404 theo policy, không thao tác dữ liệu tenant khác. Replay store lỗi phải fail closed, có thể dùng 503 theo hợp đồng. Dùng writer/schema chung, message public cố định an toàn; cấu hình error response ở gateway và kiểm thử qua proxy. HTTP 401 cần `WWW-Authenticate` challenge phù hợp với scheme HMAC đã định nghĩa.

## 18. Checklist trước khi đưa vào production

- Có bảng ánh xạ rõ **authentication / authorization / MVC validation / payload limit / dependency failure** sang status và public code.
- HMAC filter bắt lỗi ở đúng ranh giới; không tin `@RestControllerAdvice` sẽ xử lý mọi exception trước MVC.
- `AuthenticationEntryPoint` trả 401 chung an toàn, `AccessDeniedHandler` xử lý 403 khi principal đã xác thực.
- 401 mang `WWW-Authenticate` hợp đồng phù hợp, không gửi challenge sai scheme.
- Filter và MVC dùng body lỗi chung `application/problem+json`, `status` body đúng HTTP status, extension code có phiên bản/contract rõ.
- Public `detail` không chứa secret, signature, key version bị revoke, canonical bytes, raw body, stack trace hoặc tenant nhạy cảm.
- Request ID được tạo/xác minh bởi server/gateway, có giới hạn độ dài; header/cache policy phù hợp.
- Filter dừng pipeline ngay khi lỗi, không chạy controller và không giữ `SecurityContext` cũ.
- Xử lý 413 trước khi buffer body vô hạn; không đổi hợp đồng ký khi body quá lớn.
- Timestamp/nonce và key state vẫn bắt buộc; phụ trợ hỏng thì fail closed, không tạo 2xx.
- Authorization xét principal, target tenant, action, resource và không rò dữ liệu tenant khác.
- `@RestControllerAdvice` quản lý lỗi MVC, có coverage cho 400/405/415/validation theo version framework đang dùng.
- Kiểm thử cả response do ingress/container tạo, error dispatch, committed response, bodyless method, filter chạy hai lần và proxy rewrite.
- Có unit/MockMvc/E2E tests cho 401/403/400/413/503, error schema, headers, no side effects và bảo mật thông tin.
- Audit/metrics giúp điều tra chi tiết nội bộ mà không lộ shared secret, chữ ký hoặc payload sản xuất.

**Error response MVC trong xác thực HMAC là một phần của ranh giới bảo mật, không chỉ là định dạng JSON.** Thiết kế đúng phải phân biệt lỗi ở filter, Spring Security và DispatcherServlet; trả đúng status và body an toàn, giữ nguyên quyết định fail closed, không để lỗi xác thực biến thành quyền truy cập, và xác minh hành vi xuyên gateway, nhiều client, key rotation và nhiều instance.
