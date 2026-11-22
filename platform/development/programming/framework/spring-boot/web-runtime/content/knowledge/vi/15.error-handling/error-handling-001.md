# Phân tầng lỗi mạng, máy chủ, bộ lọc, Controller và nghiệp vụ trong Spring Boot

Một HTTP request thất bại không đồng nghĩa controller đã chạy và ném exception. Trong ứng dụng **Spring Boot web runtime**, lỗi có thể xảy ra từ lúc client tìm địa chỉ DNS, thiết lập kết nối TCP/TLS, đi qua gateway hoặc reverse proxy, vào Servlet container, chạy Servlet filters/Spring Security, được `DispatcherServlet` điều phối, gọi controller, cho đến khi service thực hiện quy tắc nghiệp vụ hay truy cập hệ thống bên ngoài.

Đặt xử lý lỗi ở **đúng tầng** là nền tảng để trả HTTP status nhất quán, tránh lộ dữ liệu nội bộ, giảm log trùng lặp và chẩn đoán sự cố chính xác.

**Phân loại cốt lõi:**

- **Lỗi mạng/transport:** DNS, TCP, TLS, kết nối bị ngắt, timeout mạng. Có trường hợp **không tồn tại HTTP response**.
- **Lỗi proxy/web server/Servlet container:** request không hợp lệ, kích thước hoặc giới hạn kết nối, routing ở hạ tầng, servlet mapping. Có thể được xử lý **trước controller**, thậm chí trước filter.
- **Lỗi Servlet Filter / Spring Security:** request bị chặn bởi authentication, authorization, CORS, rate limit hoặc chính sách HTTP trước Spring MVC.
- **Lỗi Spring MVC / Controller:** route không khớp, HTTP method không hỗ trợ, body decode thất bại, binding/validation lỗi, hoặc controller ném exception.
- **Lỗi nghiệp vụ / service / downstream:** tài nguyên không tồn tại, xung đột trạng thái, vi phạm quy tắc, DB hoặc dịch vụ bên ngoài không sẵn sàng. Cần chuyển thành response phù hợp ở ranh giới HTTP, không đưa mọi exception thành 500.

Bài này chủ yếu mô tả **Spring Boot 3.x, Java 17+, Spring MVC trên Servlet stack**, và chỉ rõ điểm khác khi sử dụng **Spring WebFlux**. Các ví dụ độc lập dùng một dự án Spring Boot 3.x. Khi nâng major version, cần đối chiếu API và cấu hình Spring Security, Servlet container và Spring Framework tương ứng.

## 1. Sơ đồ các tầng trên đường đi của request

~~~text
HTTP client
    |
    | DNS / TCP / TLS / HTTP
    v
Network / Load Balancer / Reverse Proxy
    |
    | Kết nối upstream, header, URL rewrite, timeout, size limit
    v
Embedded Servlet container (Tomcat, Jetty hoặc Undertow)
    |
    | Phân tích HTTP, context path, servlet mapping, lỗi server
    v
Servlet FilterChain
    |
    +---- Logging/correlation filter
    +---- Spring Security filters
    +---- CORS/rate-limit/custom filter
    |
    v
DispatcherServlet (Spring MVC)
    |
    +---- HandlerMapping: xác định route/handler
    +---- HandlerAdapter: binding + validation + gọi handler
    +---- HttpMessageConverter: đọc/ghi body
    |
    v
@RestController / @Controller
    |
    v
Service (domain/business rules)
    |
    +---- Repository/Database
    +---- HTTP client/Message broker/Cache
    |
    v
Response đi ngược trở lại qua MVC -> Filter -> Container -> Proxy
~~~

Sơ đồ là trường hợp Servlet MVC thông dụng. Một số request không đi hết đường: reverse proxy có thể trả lỗi ngay, Servlet container có thể từ chối request malformed, filter có thể kết thúc response, hoặc DispatcherServlet không tìm thấy handler.

### 1.1. Tầng nào có quyền tạo HTTP response?

| Tầng | Ví dụ lỗi | Có thể tạo response? | Có đi qua ControllerAdvice? |
|---|---|---|---|
| DNS/TCP/TLS phía client | Không resolve DNS, connection refused | Không nhất thiết có HTTP response | Không |
| Proxy/gateway | Upstream timeout, backend không kết nối được | Có thể trả 502/503/504 | Không nếu request chưa tới app |
| Servlet container | Request line/header quá lớn, parse HTTP hỏng | Có thể trả 400/413/431 hoặc đóng connection | Thường không |
| Servlet Filter | Chặn request, auth/security | Có thể trả 401/403/429 | Không tự động |
| Spring MVC mapping/binding | Sai method, JSON hỏng, validation fail | Thường 400/404/405/406/415 | Có thể, tùy exception và cơ chế xử lý MVC |
| Controller | Ném exception khi xử lý request | Có nếu được xử lý bởi MVC error resolver | Có thể |
| Service nghiệp vụ | Not found, conflict, business rule | Controller/Advice chuyển thành HTTP | Có thể nếu exception đi qua MVC |
| Downstream | DB timeout, HTTP client exception | App có thể chuyển thành 5xx/503, hoặc request timeout | Có thể nếu exception được chuyển qua MVC và response chưa commit |

**Không nên kết luận** một status code luôn xác định được một tầng duy nhất. HTTP 400 có thể xuất phát từ proxy, container hoặc MVC; HTTP 403 có thể xuất phát từ security filter hoặc logic nghiệp vụ. Cần đối chiếu log và trace theo đường đi thực tế.

## 2. Tầng mạng: DNS, TCP, TLS và connection failure

Các lỗi xảy ra **trước khi có HTTP message hợp lệ** không thể được xử lý bằng `@RestControllerAdvice` của ứng dụng.

Ví dụ:

- **DNS failure:** client không phân giải được hostname thành địa chỉ để kết nối.
- **TCP connection refused:** không có service lắng nghe địa chỉ/cổng được gọi, hoặc hệ thống từ chối kết nối.
- **TCP connect timeout:** mạng, firewall hoặc điểm đích không phản hồi trong thời hạn kết nối.
- **TLS handshake failure:** chứng chỉ không tin cậy, hostname không khớp, protocol/cipher không tương thích, SNI hoặc mTLS configuration sai.
- **Connection reset / premature close:** kết nối bị đóng đột ngột trước hoặc trong lúc truyền response.
- **Client-side read/response timeout:** client chờ response quá lâu và từ bỏ, dù server có thể vẫn đang xử lý.

Ở các tình huống này, client có thể chỉ có **exception ở HTTP client library**, không có status code 500/503 do ứng dụng phát ra.

### 2.1. Phân biệt kết nối thất bại với HTTP error response

~~~text
A. DNS fail -> TCP chưa thiết lập -> không có HTTP response
B. TLS fail -> HTTP request chưa vào ứng dụng -> không có response HTTP thông thường
C. Gateway gửi 504 -> có HTTP response 504 từ gateway
D. App trả 503 -> có HTTP response 503 từ ứng dụng
~~~

Không được biến mọi network exception thành “HTTP 500 từ server”. Khi chưa nhận được HTTP response, cần giữ thông tin về **loại lỗi transport** và địa chỉ đích, thời điểm, retry count, timeout; chỉ gắn HTTP status khi thực sự có response.

### 2.2. Timeout không khẳng định nghiệp vụ đã thất bại

Giả sử client gửi yêu cầu thanh toán, server đã xử lý thành công nhưng response bị ngắt trên đường về. Client nhìn thấy timeout, nhưng lệnh thanh toán **có thể đã được thực hiện**.

Không nên tự động retry mọi yêu cầu POST có tác dụng phụ. Với các nghiệp vụ không an toàn khi lặp, cần **idempotency key**, trạng thái giao dịch bền vững, cơ chế kiểm tra lại kết quả và quy tắc retry rõ ràng.

## 3. Reverse proxy, ingress và load balancer có thể là nguồn lỗi

Trong triển khai thực tế, client thường không gọi trực tiếp embedded server. Nhiều hệ thống có API gateway, Nginx, ingress controller, load balancer hoặc service mesh:

~~~text
Client -> Gateway/Ingress -> Spring Boot Pod
                |
                +-- Route/rewrite URL
                +-- TLS termination
                +-- Request header/body size limits
                +-- Upstream connect/read timeout
                +-- Rate-limit hoặc auth policy
~~~

Những mã lỗi thường thấy:

| Status | Ý nghĩa thường gặp tại proxy/gateway | Cần kiểm tra |
|---|---|---|
| 400 | Request không hợp lệ ở proxy | Header, URL, HTTP syntax |
| 401/403 | Auth/chính sách tại gateway | Gateway auth policy |
| 413 | Body vượt giới hạn ở proxy | Request body size limit |
| 429 | Rate limit | Quota và rule ở ingress/gateway |
| 502 | Gateway nhận upstream response không hợp lệ/không kết nối được | Backend health, protocol, reset |
| 503 | Không có upstream sẵn sàng hoặc overload | Endpoints, service discovery, readiness |
| 504 | Gateway đợi upstream quá lâu | Upstream timeout, downstream latency |

Đây là **mẫu thường gặp**, không phải chứng cứ chắc chắn về nguồn gốc status. Cùng 503 có thể do ứng dụng chủ động phát ra, hoặc do gateway không tìm thấy backend khỏe.

Một số proxy dùng status **499** để ghi nhận client đã đóng request; đó là mã phi chuẩn HTTP, không phải mã mà mọi server đều hỗ trợ.

**Dấu hiệu quan trọng:** nếu proxy trả lỗi trước khi chuyển tiếp request, Spring Boot **không có log/controller trace** tương ứng. Hãy kiểm tra access logs tại từng hop và correlation/request ID của cả proxy và ứng dụng thay vì chỉ tìm controller exception.

## 4. Tầng Servlet container: lỗi xảy ra trước FilterChain

Trong Spring MVC Servlet stack, embedded Tomcat/Jetty/Undertow tiếp nhận HTTP, kiểm tra phần cú pháp cần thiết và xác định web application/servlet mapping.

Các trường hợp có thể bị container xử lý sớm:

- HTTP request line hoặc header không hợp lệ.
- Header quá lớn, request target không được chấp nhận.
- Kết nối quá nhiều, worker/connector quá tải.
- Giới hạn kích thước body hoặc upload cụ thể của container.
- Sai context path, servlet mapping hoặc listener/connector.
- Lỗi TLS/HTTP protocol ở connector.

Khi request **chưa đi tới FilterChain**, custom servlet filter hay `@RestControllerAdvice` của bạn không thể bắt lỗi đó.

### 4.1. Cổng mở không đảm bảo ứng dụng sẵn sàng

Một ứng dụng có thể đã mở socket HTTP nhưng còn chưa đủ điều kiện trả traffic theo yêu cầu nghiệp vụ, hoặc container đang quá tải. Vì vậy, cần phân biệt:

- **Liveness:** tiến trình còn sống và có thể phục hồi bằng restart nếu mắc kẹt.
- **Readiness:** instance có sẵn sàng nhận request theo điều kiện vận hành không.
- **Business health:** kết nối hoặc năng lực của các dependency quan trọng.

Có thể cấu hình Spring Boot Actuator health/readiness probe khi thích hợp, nhưng chỉ dùng được khi dependency/config tương ứng đã được bật. Không coi “port TCP bắt tay được” là bằng chứng endpoint/controller đã hoạt động bình thường.

### 4.2. Lỗi container không nhất thiết có JSON chuẩn hóa

Container có thể đóng connection hoặc trả một error page/body khác định dạng JSON của API. Nếu contract yêu cầu JSON lỗi nhất quán, cần chuẩn hóa tại ingress/proxy và ứng dụng trong giới hạn từng tầng; **không thể dùng ControllerAdvice để bắt mọi lỗi HTTP trước Servlet container**.

## 5. Servlet FilterChain và lỗi phát sinh trước DispatcherServlet

`Filter` được Servlet container gọi trước khi đi vào `DispatcherServlet`, có thể được dùng cho tracing, HTTP policy, request wrapping, rate limit hoặc security.

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
) throws IOException, ServletException {
    // Logic trước Servlet/DispatcherServlet
    chain.doFilter(request, response);
    // Logic trên đường response quay trở ra
}
~~~

Đây là fragment của class `implements Filter`, cần imports từ `jakarta.servlet.*` trong Spring Boot 3.x.

Nếu filter **không gọi `chain.doFilter`**, request dừng trước khi tới controller. Một filter có thể tự trả 403 hoặc 429, nhưng điều đó không có nghĩa controller tương ứng đã chạy.

### 5.1. Vì sao @RestControllerAdvice không tự bắt exception của filter?

`@RestControllerAdvice` là cơ chế xử lý exception trong đường đi MVC do `DispatcherServlet`/`HandlerExceptionResolver` điều phối. Filter chạy **ở bên ngoài** đường đi ấy.

~~~text
Filter
  |
  +--- exception ném trước chain.doFilter -> không qua MVC exception resolver
  |
  +--- chain.doFilter -> DispatcherServlet -> Controller -> MVC resolver
  |
  +--- code sau chain.doFilter cũng ở bên ngoài MVC resolver
~~~

Nếu filter ném exception trước khi vào DispatcherServlet hoặc sau khi nó trả về, `@ExceptionHandler` trong ControllerAdvice thông thường **không có cơ hội** bắt trực tiếp exception đó.

Cần xử lý lỗi filter tại filter, security framework hoặc Servlet error-handling pipeline. Có thể có thiết kế chuyển lỗi sang resolver theo chủ đích, nhưng không nên giả định một global advice tự xử lý toàn bộ HTTP pipeline.

### 5.2. Filter response phải được tạo có trách nhiệm

Nếu muốn chặn request:

~~~java
if ("true".equalsIgnoreCase(request.getHeader("X-Block-Request"))) {
    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    return;
}
filterChain.doFilter(request, response);
~~~

Đây là fragment dùng trong `OncePerRequestFilter#doFilterInternal`, nơi request/response đã có kiểu HttpServletRequest/HttpServletResponse. Với cách viết trên, filter trả **403**, không cung cấp JSON body. Nếu API cần chuẩn JSON, filter hoặc security handler phải tự xây dựng response an toàn và kiểm tra content type/status.

Không gọi `response.getWriter()` rồi tiếp tục `chain.doFilter` nếu không có chủ đích. Có thể ghi response lặp, trộn body hoặc khiến response đã commit, không thể đổi status.

## 6. Spring Security nằm trong tầng filter nhưng có xử lý lỗi riêng

Trong Spring Security Servlet stack, `DelegatingFilterProxy` và `FilterChainProxy` liên kết Servlet FilterChain với các `SecurityFilterChain` của Spring Security. Authentication và authorization thường được quyết định **trước khi controller thực thi**.

Một số thành phần:

- **AuthenticationEntryPoint:** thường bắt đầu quy trình phản hồi khi request chưa được xác thực mà cần authentication; có thể trả 401 hoặc redirect tùy loại ứng dụng.
- **AccessDeniedHandler:** xử lý yêu cầu bị từ chối truy cập theo policy, thường 403 với người dùng đã xác thực.
- **ExceptionTranslationFilter:** chuyển một số `AuthenticationException` và `AccessDeniedException` trong security filter chain thành phản hồi do các handler tương ứng tạo.
- **SecurityFilterChain:** định nghĩa các security filters áp dụng cho một tập request và thứ tự của chúng.

Không phải mọi ứng dụng có Spring Security đều trả chính xác 401/403 cho mọi trường hợp: browser login có thể redirect, custom policy có thể khác, và CORS preflight cũng cần cấu hình hợp lý.

**Không giải quyết 401/403 ở security filter bằng cách thêm `@ExceptionHandler(AuthenticationException.class)` rồi kỳ vọng controller advice nhận được tất cả.** Thay vào đó, cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` (nếu muốn chuẩn hóa API error body) cùng security policy, sau đó kiểm thử riêng.

Lỗi authorization **trong controller/service** khi dùng method-level security cũng cần xem cách exception lan truyền trong framework; không đánh đồng với việc filter chặn request trước MVC.

## 7. Tầng DispatcherServlet: route, binding, validation và converter

Sau FilterChain, `DispatcherServlet` chọn handler qua `HandlerMapping` và gọi handler thông qua `HandlerAdapter`. Request có thể lỗi **trước khi vào thân controller**, dù đã tới Spring MVC.

Các trường hợp:

| Giai đoạn MVC | Lỗi | HTTP status điển hình |
|---|---|---|
| HandlerMapping | Không có route phù hợp | 404 |
| Method mapping | URL đúng, method không được hỗ trợ | 405 |
| Content negotiation | Accept không tương thích với produces | 406 |
| Request media type | Content-Type không thỏa consumes / reader | 415 |
| Argument resolution | Path variable không đổi được sang long | 400 |
| Request body decoder | JSON không hợp lệ hoặc không parse được DTO | 400 |
| Bean Validation | DTO không thỏa `@Valid` | 400 hoặc theo rule riêng |
| Handler invocation | Controller ném exception | Theo exception resolver / fallback |
| Response serialization | Không ghi được response body | 5xx hoặc lỗi khác, tùy trạng thái response |

Ví dụ controller nhận ID kiểu long:

~~~java
@GetMapping("/api/products/{id}")
Product product(@PathVariable long id) {
    return productService.find(id);
}
~~~

Đây là fragment dùng trong controller có service/domain đã định nghĩa. Request `GET /api/products/abc` không thể bind `abc` thành `long`. Spring MVC có thể trả 400 trước khi chạy `productService.find`.

**Ý nghĩa:** Nếu controller không có log, không nhất thiết request đã bị proxy/filter chặn; nó có thể thất bại trong mapping, argument resolution hoặc validation của MVC.

### 7.1. ControllerAdvice có thể xử lý những gì?

`@RestControllerAdvice` kết hợp `@ControllerAdvice` với `@ResponseBody` cho các `@ExceptionHandler`; được Spring MVC dùng để xử lý nhiều exception trong chuỗi điều phối của DispatcherServlet, gồm cả exception từ controller/service và nhiều exception của MVC framework.

Có thể kế thừa `ResponseEntityExceptionHandler` để chuẩn hóa nhiều lỗi framework thuộc phạm vi MVC, nhưng phải hiểu các phương thức override và cấu trúc body của Spring Framework version đang dùng.

**Đừng viết một handler quá rộng cho `Exception.class` rồi trả 400/422 cho tất cả.** Lỗi lập trình, DB downtime và bug serializer không thể bị “làm đẹp” thành lỗi client. Khi cần fallback 500, giữ response chung chung và log exception nội bộ một lần tại tầng hợp lý.

## 8. Lỗi nghiệp vụ: domain exception cần được chuyển thành HTTP ở ranh giới API

Service nên nói bằng ngôn ngữ nghiệp vụ: sản phẩm không tồn tại, số lượng tồn không đủ, thao tác không hợp lệ trong trạng thái hiện tại, quyền sở hữu không đúng, phiên bản tài nguyên đã thay đổi.

Không nên để mọi service trực tiếp biết `HttpStatus` hoặc `ResponseEntity`. Một cách tổ chức:

~~~text
Controller  ---- gọi ----> Service
   |                       |
   |                       +--> BusinessRuleException
   |                       +--> ProductNotFoundException
   |                       +--> DownstreamFailureException
   |
@RestControllerAdvice / Exception mapping
   |
   +--> HTTP 422 / 404 / 503 hoặc 500 theo chính sách API
~~~

### 8.1. Bảng mapping điển hình

| Tình huống | Status nên cân nhắc | Lưu ý |
|---|---|---|
| Body malformed, param kiểu sai | 400 Bad Request | Lỗi cú pháp/định dạng request |
| Authentication chưa hợp lệ | 401 Unauthorized | Có thể do security filter |
| Không đủ quyền | 403 Forbidden | Cần tránh lộ thông tin nhạy cảm |
| Tài nguyên không tồn tại | 404 Not Found | Có thể 404 dù tài nguyên tồn tại khi cố ý ẩn quyền |
| Trạng thái/version xung đột | 409 Conflict | Ví dụ optimistic locking/duplicate state |
| Preconditions HTTP không thỏa | 412 Precondition Failed | Khi dùng If-Match/If-Unmodified-Since |
| Quy tắc nghiệp vụ không thỏa | 422 Unprocessable Content | Tùy thiết kế API; không phải bắt buộc |
| Quá nhiều request | 429 Too Many Requests | Có thể do gateway/filter |
| Dependency tạm ngừng | 503 Service Unavailable | Có thể có Retry-After khi có chính sách |
| Lỗi server không mong đợi | 500 Internal Server Error | Không tiết lộ stack trace/DB details |

Đây là **gợi ý thiết kế**, không phải quy định mọi nghiệp vụ phải dùng chính xác status ấy. API có thể dùng 400 thay 422 theo contract thống nhất; khách hàng cần hiểu mã lỗi và khả năng retry.

### 8.2. Điều gì nên xuất hiện trong error response?

Trong Spring Framework 6 / Spring Boot 3, `ProblemDetail` là mô hình thể hiện error response dựa trên chuẩn Problem Details (RFC 9457, kế thừa RFC 7807). Các thuộc tính cốt lõi gồm:

- `type`: URI hoặc định danh loại lỗi.
- `title`: mô tả ngắn, ổn định của loại lỗi.
- `status`: HTTP status.
- `detail`: mô tả phù hợp cho client, không tiết lộ thông tin nhạy cảm.
- `instance`: tài nguyên/request instance liên quan, khi thích hợp.

Có thể thêm extension fields như `code` (mã lỗi ứng dụng), `traceId` hoặc `requestId`. Những giá trị trace ID nếu thêm cần lấy từ cơ chế tracing/propagation thực tế, không tạo bừa một mã mới không tương quan với log.

**Không đưa vào response công khai:** SQL query, credentials, access token, stack trace, filesystem path nội bộ, raw upstream response nhạy cảm hoặc exception message không được kiểm duyệt.

## 9. Ví dụ chạy được: phân biệt Filter, Controller và Service

Ví dụ dùng **Java 17+**, **Spring Boot 3.x**, embedded Tomcat mặc định của `spring-boot-starter-web`. Tệp Java có một public class ứng dụng và những class package-private trong cùng package để dễ theo dõi.

Dependency trong `build.gradle` của dự án đã cấu hình Spring Boot plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Tạo tệp **src/main/java/demo/errors/ErrorLayersApplication.java**:

~~~java
package demo.errors;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class ErrorLayersApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorLayersApplication.class, args);
    }
}

record Product(long id, String name) {
}

class InvalidProductIdException extends RuntimeException {

    InvalidProductIdException(String message) {
        super(message);
    }
}

class ProductNotFoundException extends RuntimeException {

    ProductNotFoundException(String message) {
        super(message);
    }
}

class DemoInfrastructureException extends RuntimeException {

    DemoInfrastructureException(String message) {
        super(message);
    }
}

@Component
class RequestGateFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        if ("true".equalsIgnoreCase(
                request.getHeader("X-Demo-Block"))) {
            // Filter trả 403 và không chuyển request tới MVC.
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        chain.doFilter(request, response);
    }
}

@Service
class ProductService {

    Product find(long id) {
        if (id <= 0) {
            throw new InvalidProductIdException(
                    "Product id must be positive");
        }
        if (id == 42) {
            throw new ProductNotFoundException(
                    "Requested product was not found");
        }
        if (id == 99) {
            // Tái hiện một lỗi ứng dụng/hạ tầng giả lập.
            throw new DemoInfrastructureException(
                    "Simulated internal dependency failure");
        }
        return new Product(id, "product-" + id);
    }
}

@RestController
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/api/products/{id}")
    Product getProduct(@PathVariable long id) {
        return productService.find(id);
    }
}

@RestControllerAdvice
class ProductErrorAdvice {

    @ExceptionHandler(InvalidProductIdException.class)
    ProblemDetail invalidId(InvalidProductIdException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.UNPROCESSABLE_ENTITY, ex.getMessage());
        problem.setTitle("Business rule rejected");
        problem.setProperty("code", "INVALID_PRODUCT_ID");
        return problem;
    }

    @ExceptionHandler(ProductNotFoundException.class)
    ProblemDetail missing(ProductNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
        problem.setTitle("Product not found");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(DemoInfrastructureException.class)
    ProblemDetail internal(DemoInfrastructureException ex) {
        // Không trả ex.getMessage() cho client.
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Internal server error");
        problem.setTitle("Server error");
        problem.setProperty("code", "INTERNAL_ERROR");
        return problem;
    }
}
~~~

### 9.1. Vì sao đây là ví dụ về phân tầng?

- `RequestGateFilter` chạy **trước DispatcherServlet**. Nếu client có header `X-Demo-Block: true`, filter đặt status 403 và dừng chain. Controller và service **không chạy**.
- `ProductController` phụ trách HTTP routing và gọi service, không chứa quy tắc tìm sản phẩm.
- `ProductService` phân loại ba tình huống nghiệp vụ/lỗi giả lập qua exception riêng, không import `HttpStatus`.
- `ProductErrorAdvice` chuyển exception từ MVC request handling thành `ProblemDetail`; lỗi nghiệp vụ được trả 404/422, lỗi nội bộ 500 có detail an toàn.
- Exception từ **Filter** ở đoạn trước khi gọi `chain.doFilter` không được ProductErrorAdvice tự động xử lý. Trong ví dụ filter chủ động trả 403 nên không cần ném exception.
- Nếu client gọi `/api/products/not-a-number`, việc chuyển `@PathVariable` sang `long` có thể thất bại ở MVC argument binding **trước khi thân controller chạy**, thường trả 400 theo cơ chế framework.

**Không hiểu `id=99` là lỗi DB thật.** Đây chỉ là một tình huống giả lập để minh họa service phát sinh lỗi 5xx và response không lộ nội dung exception.

### 9.2. Chạy và kiểm tra thủ công

Từ dự án Gradle có Spring Boot plugin và wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Giả sử server lắng nghe `localhost:8080`, context path mặc định và không có Spring Security khác can thiệp, các request:

~~~bash
curl -i http://localhost:8080/api/products/1
curl -i http://localhost:8080/api/products/0
curl -i http://localhost:8080/api/products/42
curl -i http://localhost:8080/api/products/99
curl -i -H 'X-Demo-Block: true' http://localhost:8080/api/products/1
curl -i http://localhost:8080/api/products/not-a-number
~~~

Kỳ vọng:

| Request | Status | Tầng quyết định |
|---|---|---|
| GET `/api/products/1` | 200 | Controller → service |
| GET `/api/products/0` | 422 | Service exception → ControllerAdvice |
| GET `/api/products/42` | 404 | Service exception → ControllerAdvice |
| GET `/api/products/99` | 500 | Service exception giả lập → ControllerAdvice |
| GET kèm `X-Demo-Block: true` | 403 | Servlet filter, chưa vào MVC |
| GET `/api/products/not-a-number` | 400 điển hình | MVC path-variable conversion |

Body của response 200 là JSON tương đương:

~~~json
{"id":1,"name":"product-1"}
~~~

Response 404 từ `ProductErrorAdvice` có thể có dạng Problem Details tương đương:

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Requested product was not found",
  "instance": "/api/products/42",
  "code": "PRODUCT_NOT_FOUND"
}
~~~

`instance` có thể được Spring bổ sung hoặc khác tùy Spring Framework/Boot config; không nên assert cứng field này khi ví dụ chỉ cấu hình `code`, `title` và `detail`. JSON fields và thứ tự key cũng có thể khác.

**Response 403 của filter chỉ đặt status**. Đừng kỳ vọng có tự động body `ProblemDetail` hoặc error code từ `ProductErrorAdvice` cho trường hợp ấy.

## 10. Kiểm thử tự động bằng MockMvc

Để bảo vệ hợp đồng phân tầng, cần test cả HTTP status và dấu hiệu cho biết nguồn xử lý, chứ không chỉ gọi trực tiếp `ProductService.find`.

Thêm `spring-boot-starter-test` trong `build.gradle`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tệp **src/test/java/demo/errors/ErrorLayersApplicationTest.java**:

~~~java
package demo.errors;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorLayersApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulRequestReturnsProduct() throws Exception {
        mvc.perform(get("/api/products/1"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.id").value(1))
           .andExpect(jsonPath("$.name").value("product-1"));
    }

    @Test
    void businessRuleMapsTo422() throws Exception {
        mvc.perform(get("/api/products/0"))
           .andExpect(status().is(422))
           .andExpect(jsonPath("$.code").value("INVALID_PRODUCT_ID"));
    }

    @Test
    void missingProductMapsTo404() throws Exception {
        mvc.perform(get("/api/products/42"))
           .andExpect(status().isNotFound())
           .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void internalFailureHidesPrivateMessage() throws Exception {
        mvc.perform(get("/api/products/99"))
           .andExpect(status().isInternalServerError())
           .andExpect(jsonPath("$.detail").value("Internal server error"));
    }

    @Test
    void servletFilterCanStopRequestBeforeController() throws Exception {
        mvc.perform(get("/api/products/1")
                .header("X-Demo-Block", "true"))
           .andExpect(status().isForbidden());
    }

    @Test
    void mvcBindingErrorIsNotBusinessRule() throws Exception {
        mvc.perform(get("/api/products/not-a-number"))
           .andExpect(status().isBadRequest());
    }
}
~~~

Tệp test này dùng đúng `@AutoConfigureMockMvc` của Spring Boot Test 3.x và `MockMvc` từ Spring Test. Với cấu hình demo, không có security filter và custom error handling khác, các test xác minh:

1. Controller/service thành công.
2. Exception nghiệp vụ được chuyển thành status/codes phù hợp.
3. Response cho lỗi nội bộ không tiết lộ exception message.
4. Filter chặn request với 403 trước MVC.
5. Lỗi type conversion được Spring MVC xử lý khác với service exception.

Chạy:

~~~bash
./gradlew test
~~~

**Giới hạn của MockMvc:** nó thực thi servlet/MVC test infrastructure mà **không mở TCP socket thực**. Vì vậy test này không chứng minh DNS, TLS, reverse proxy 502/504 hoặc giới hạn header của Tomcat hoạt động. Muốn kiểm tra container/proxy phải dùng integration test qua HTTP thật hoặc môi trường triển khai gần production.

## 11. Spring Boot fallback /error và Servlet ERROR dispatch

Khi exception không được `@ExceptionHandler` hoặc MVC exception resolver xử lý, Spring Boot có cơ chế error handling dự phòng. Với ứng dụng Spring MVC Servlet điển hình, `/error` và `BasicErrorController` có thể tham gia tùy auto-configuration và error dispatch của container.

Những tình huống cần phân biệt:

- **Đã xử lý tại ControllerAdvice:** MVC tạo response xong; không cần chuyển sang fallback cho cùng lỗi.
- **Exception chưa xử lý:** lỗi có thể được đưa tới error handling của container/Spring Boot; response fallback phụ thuộc `Accept`, cấu hình và trạng thái response.
- **Servlet filter gọi `response.sendError(...)`:** có thể kích hoạt cơ chế error dispatch của Servlet container.
- **Filter chỉ gọi `response.setStatus(...)` rồi return:** không tự động tương đương với `sendError`; không giả định fallback `/error` luôn chạy.
- **Response đã committed:** status/headers/body có thể không còn sửa được thành JSON lỗi mới.

Với `ERROR dispatch`, một số filter có thể chạy lại nếu được đăng ký cho dispatcher type ERROR. `OncePerRequestFilter` có các quy tắc liên quan async/error dispatch; tên class không bảo đảm một đoạn logic chỉ chạy một lần tuyệt đối trong mọi request lifecycle.

**Đừng thay controller advice bằng một catch-all filter bắt mọi exception.** Bắt và biến tất cả exception thành JSON tại filter có thể làm hỏng logic xử lý của MVC, Spring Security và container, cũng như gây ghi response sau khi đã commit.

## 12. Lỗi từ service gọi DB/API bên ngoài

Một service có thể gọi repository/JDBC hoặc HTTP client. Tại đây cần phân biệt **lỗi business** và **lỗi hạ tầng**:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Không tìm thấy đối tượng nghiệp vụ | Product ID không tồn tại | Domain exception → 404 |
| Business rule không hợp lệ | Đơn hàng đã đóng, không thể sửa | 409/422 tùy contract |
| Optimistic locking | Version từ client đã lỗi thời | 409 hoặc 412 tùy HTTP preconditions |
| DB connection timeout | Pool cạn, DB không phản hồi | Internal error/dependency unavailable, thường 5xx |
| Remote API trả HTTP 400 | Request gửi đến downstream không hợp lệ | Điều tra contract; không tự trả y nguyên 400 cho client nếu lỗi do app |
| Remote API trả HTTP 503 | Downstream unavailable | Có thể map 503 và retry policy phù hợp |
| Remote network timeout | Không chắc downstream đã nhận và xử lý hay chưa | Timeout, idempotency, circuit breaker |
| Serialization error | DTO/ObjectMapper không ghi được body | Lỗi kỹ thuật, thường 5xx |

**Không chuyển máy móc** một `WebClientResponseException.NotFound` của hệ thống khác thành 404 cho API hiện tại. Downstream trả 404 có thể nghĩa là URL upstream bị cấu hình sai, chứ không có nghĩa domain resource của client không tồn tại. Service phải hiểu ngữ nghĩa lỗi của dependency.

### 12.1. Lỗi WebClient: status vs transport

Khi Spring dùng `WebClient`, có hai nhóm tình huống:

- Downstream **trả HTTP response với status lỗi**: trong một số kiểu gọi như `retrieve()`, WebClient có thể phát `WebClientResponseException` cho 4xx/5xx mặc định; hoặc code có thể tự xử lý response status có chủ đích.
- HTTP request **thất bại do kết nối/transport**: có thể thấy `WebClientRequestException` hoặc exception network được bọc bên trong. Chưa chắc có HTTP response/status từ downstream.

Đừng chỉ catch `Exception` rồi trả 503 cho mọi thứ. Timeout, authentication failure, request malformed và domain conflict có ý nghĩa khác nhau, đặc biệt đối với retry.

### 12.2. Retry cần kiểm soát

- Chỉ retry những lỗi có khả năng tạm thời và thao tác được phép lặp.
- Có số lần retry tối đa, backoff và jitter nếu phù hợp.
- Quan sát tổng deadline của request; không làm retry kéo dài mãi.
- Tránh retry storm khi DB/downstream đang sập.
- Với POST/payment, dùng idempotency key hoặc reconciliation.
- Có circuit breaker/bulkhead khi workload và thư viện hỗ trợ; không buộc mọi dự án phải có một cơ chế cụ thể.

## 13. Phân biệt 4xx, 5xx và lỗi không có HTTP status

Một cách phân tầng có trách nhiệm:

| Nhóm | Ý nghĩa | Người thường phải hành động |
|---|---|---|
| 4xx do client request | Request sai định dạng, unauthorized, forbidden, conflict | Client/người dùng hoặc contract |
| 4xx do app business policy | Quy tắc nghiệp vụ không thỏa | Client điều chỉnh yêu cầu hoặc xử lý business state |
| 5xx của ứng dụng | Bug, dependency lỗi, resource server không đủ | Nhóm vận hành/ứng dụng |
| 5xx của proxy | Backend unavailable hoặc timeout ở gateway | Hạ tầng và backend |
| Transport exception, không có HTTP response | DNS/TCP/TLS/reset/timeout | Điều tra cả client/network/server |

**Không nên viết rule “4xx không log, 5xx luôn alert”.** Có thể cần theo dõi 401 brute force, 403 abuse, 429 spike và 400 tăng đột biến do regression. Ngược lại, một số 404 tài nguyên tùy chọn là tình huống nghiệp vụ bình thường. Logging/alert phụ thuộc threat model và SLO.

## 14. Thiết kế một Error Contract nhất quán mà không lộ thông tin

Một error response nên có ý nghĩa ổn định với client, chẳng hạn:

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Requested product was not found",
  "code": "PRODUCT_NOT_FOUND"
}
~~~

Các điều cần cân nhắc:

- `code` là **mã nghiệp vụ có tính ổn định**, client có thể xử lý bằng code thay vì parse text detail.
- `title` nên dễ hiểu và không đổi tùy tiện.
- `detail` nên an toàn; có thể localization theo thiết kế API.
- HTTP status là phần của protocol; không đóng gói tất cả lỗi thành status 200 rồi để code trong JSON.
- `requestId` hoặc `traceId` có thể giúp hỗ trợ điều tra, nhưng phải lấy từ tracing/logging thực tế.
- Không trả tên bảng SQL, mật khẩu, filesystem path, internal hostnames hay stack trace.
- Đối với request không tới ứng dụng, proxy/gateway có thể trả body khác; contract “một JSON cho mọi lỗi” đòi hỏi cấu hình nhiều tầng, không chỉ một @RestControllerAdvice.

### 14.1. CORS và security có thể làm client hiểu nhầm

Browser JavaScript có thể chỉ thấy lỗi CORS hoặc “network error” nếu preflight bị chặn hoặc response không có CORS headers cần thiết. Backend có thể đã trả 403/500 nhưng frontend không đọc được nội dung.

Hãy kiểm tra **Network tab, preflight OPTIONS, origin, CORS config và filter ordering**, không khẳng định API không gửi response chỉ vì fetch bị reject.

## 15. Quan sát lỗi: request ID, trace và log theo tầng

Để chẩn đoán một lỗi production, cần liên kết được:

~~~text
client request id
      |
      v
gateway access log / upstream status
      |
      v
container access log
      |
      v
security/filter decision
      |
      v
MVC handler + exception resolver
      |
      v
service/downstream span
~~~

Các điểm thực hành:

1. **Correlation ID:** dùng header do hệ thống tin cậy phát/validate hoặc tracing tiêu chuẩn; không mặc định tin mọi request ID client gửi nếu dùng làm định danh có quyền.
2. **Request context:** ghi HTTP method, route template, status, duration, dependency, trace/span ID; hạn chế path/raw query chứa thông tin nhạy cảm.
3. **Log một lỗi một cách có trách nhiệm:** một exception có thể đi qua service, controller advice và gateway. Không in full stack trace lặp lại ở mọi tầng.
4. **4xx có thể là tín hiệu vận hành:** tăng 401/403/429 hoặc validation failures có thể báo regression/abuse.
5. **5xx phải có context điều tra nội bộ:** log exception an toàn cùng trace, không trả stack trace cho client.
6. **Đo timeout tại từng hop:** client deadline, proxy upstream timeout, server/controller timeout, DB/client timeout; phải biết tầng nào kết thúc trước.
7. **Dùng metrics/Actuator khi bật:** theo dõi request status distribution, p95/p99, route, downstream latency, pool saturation; không giả định mọi metric tự có nếu chưa cấu hình.

**Lưu ý:** trong async processing hoặc WebFlux, request có thể đi qua nhiều thread. Một `ThreadLocal`/MDC thông thường không tự được truyền qua mọi scheduler boundary; dùng context propagation phù hợp với framework.

## 16. Spring WebFlux khác gì khi xử lý lỗi?

Các nguyên tắc phân tầng vẫn áp dụng nhưng pipeline khác:

~~~text
Client -> Netty/TCP/TLS -> WebFilter -> DispatcherHandler
       -> HandlerMapping / HandlerAdapter
       -> Reactive controller -> Mono/Flux -> downstream
~~~

- Với **Reactor Netty**, không có Servlet FilterChain/DispatcherServlet như MVC Servlet.
- `WebFilter` xử lý request ở tầng web reactive trước reactive handler.
- `@RestControllerAdvice` / `@ExceptionHandler` vẫn có thể xử lý lỗi thuộc annotated WebFlux controller theo cơ chế resolver tương ứng.
- WebFlux còn có các `WebExceptionHandler` và error handling của Spring Boot (ví dụ `ErrorWebExceptionHandler`) cho những lỗi không được xử lý ở tầng handler.
- Với **functional WebFlux routes**, cần xem cách xử lý lỗi bằng reactive pipeline/router và global error handler; không giả định `@ExceptionHandler` của annotated controller bao phủ mọi functional handler.
- Một lỗi sau khi streaming response đã gửi một phần body có thể không đổi được status/headers thành response ProblemDetail mới.
- Một `Mono.error(...)` chỉ là tín hiệu lỗi trong reactive pipeline; việc biến nó thành HTTP status phụ thuộc handler/error resolver đang bao quanh publisher ấy.

Trong WebFlux, tránh `block()` ở Netty event loop. Nếu fallback error handler gọi JDBC hoặc file I/O blocking, chính quá trình xử lý lỗi cũng có thể làm nghẽn server. Các nghiệp vụ blocking phải được offload phù hợp hoặc kiến trúc nên sử dụng MVC.

## 17. Bộ test cần có cho từng tầng

Một chiến lược kiểm thử đầy đủ không nên chỉ có unit test cho ControllerAdvice:

| Tầng | Cách kiểm thử hợp lý | Điều cần xác nhận |
|---|---|---|
| Network/TLS | Integration test với client thực, certificate/cổng sai | Exception transport, không giả HTTP status |
| Proxy/gateway | Staging qua ingress, cấu hình timeout/size | 502/503/504/413 và access logs |
| Servlet container | Test server thật, request malformed/header lớn | Request có bị từ chối trước filter không |
| Filter | MockMvc/Servlet integration | Response bị chặn, controller không thực thi |
| Spring Security | Security test qua filter chain | 401/403, anonymous/authenticated, body/header |
| MVC mapping/binding | MockMvc | 400/404/405/406/415 với request cụ thể |
| Controller/Service | MockMvc + service tests | 200, 404, 409/422, 500 safe detail |
| DB/HTTP downstream | Integration stub/fault injection | timeout, retry, cancellation, pool limits |
| Async/Streaming | Server/client integration | Client abort, response already committed |

**Không trộn các loại test:** `MockMvc` không kết nối TCP/TLS thật, nên không thể xác nhận lỗi DNS/TLS hoặc reverse proxy. Cần chạy HTTP test qua container/ingress đối với những đường xử lý đó.

### 17.1. Một số câu hỏi khi phân loại incident

1. **Client có nhận HTTP status hay chỉ exception network?** Nếu không có response, bắt đầu từ DNS/TCP/TLS/client timeout.
2. **Gateway có access log và upstream status không?** Nếu gateway trả lỗi trước app, đừng tìm controller exception.
3. **Container có nhận request không?** Nếu không, xem ingress, port, listener, routing.
4. **Servlet FilterChain có được chạy không?** Nếu request bị chặn bởi security/filter, controller không được gọi.
5. **HandlerMapping tìm thấy controller không?** Nếu method/path/header sai, xem 404/405/406/415.
6. **Controller đã vào thân method chưa?** Binding và JSON decode có thể lỗi trước đó.
7. **Service ném lỗi nghiệp vụ hay dependency failure?** Cần mapping status đúng ngữ nghĩa.
8. **Response đã committed chưa?** Streaming error có thể không sửa được status.
9. **Có trace ID để đi xuyên các hop không?** Dùng correlation để tránh nhầm hai request khác nhau.
10. **Lỗi có tái hiện được với test đúng tầng không?** Không xem một MockMvc test là bằng chứng của gateway/network behavior.

## 18. Các sai lầm thường gặp

**Sai lầm 1 — Đổ mọi lỗi cho Controller.** Nhiều lỗi xảy ra trước controller: proxy, container, security, routing hoặc body binding. Kiểm tra call path trước khi sửa nghiệp vụ.

**Sai lầm 2 — Dùng ControllerAdvice để bắt DNS/TLS/filter errors.** Không thể vì lời gọi đó nằm ngoài MVC exception resolution. Xử lý theo tầng tương ứng.

**Sai lầm 3 — Xem mọi timeout là server không xử lý yêu cầu.** Request có thể được thực hiện rồi mất response. Cần idempotency/reconciliation, đặc biệt ở thanh toán.

**Sai lầm 4 — Bắt Exception và trả HTTP 200 với "success=false".** Làm mất ý nghĩa protocol, cản monitoring, caching và client retry. Dùng HTTP status phù hợp và error code ổn định.

**Sai lầm 5 — Trả exception.getMessage() cho mọi 500.** Có nguy cơ lộ SQL, internal hostname, path hoặc secret. Với lỗi nội bộ, trả message an toàn và log riêng.

**Sai lầm 6 — Trả 500 cho mọi lỗi nghiệp vụ.** Tài nguyên không tồn tại, version conflict hoặc business precondition có mã 4xx phù hợp hơn tùy contract.

**Sai lầm 7 — Biến mọi downstream 404/400 thành lỗi của client.** Cần hiểu downstream contract; một upstream 404 có thể do app gọi sai URL.

**Sai lầm 8 — Viết filter catch-all bao toàn request.** Có thể nuốt exception mà MVC/Security/container cần xử lý, sửa response đã commit hoặc làm mất trace.

**Sai lầm 9 — Cho rằng Spring Security 401/403 sẽ qua @RestControllerAdvice.** Security xử lý nhiều tình huống trong filter chain; dùng entry point/denied handler phù hợp.

**Sai lầm 10 — Test chỉ happy path.** Cần test filter short-circuit, type conversion 400, domain not found/conflict, lỗi 500 safe detail, proxy timeout và request size.

**Sai lầm 11 — Luôn retry khi thấy 503.** Có thể tăng tải lên dịch vụ đang lỗi. Retry phải hữu hạn, có deadline, idempotency và backoff.

**Sai lầm 12 — Không kiểm tra error dispatch và response committed.** Lỗi streaming hoặc filter chạy lại ở ERROR dispatch có thể tạo log trùng và body không hợp lệ.

## 19. Checklist trước khi triển khai

- Xác định rõ mô hình Spring MVC Servlet hay WebFlux Reactive.
- Vẽ đường đi client → gateway → container → filter/security → MVC/WebFlux → service → downstream.
- Gắn HTTP status với **tầng thực sự tạo response**, không suy luận từ status đơn lẻ.
- Với network failure chưa có HTTP response, giữ transport exception thay vì tạo 500 giả.
- Đặt auth/authz response ở Spring Security đúng chỗ.
- Đặt validation/mapping error ở Spring MVC, nghiệp vụ ở service, status translation ở API boundary.
- Dùng `ProblemDetail` hoặc error contract thống nhất cho các lỗi thuộc phạm vi ứng dụng.
- Không công khai stack trace, raw DB/network exception, token hay thông tin nội bộ.
- Kiểm tra fallback `/error` và ERROR dispatch thay vì giả định một global advice bắt tất cả.
- Chỉ retry thao tác idempotent hoặc có cơ chế kiểm soát side effects.
- Có correlation ID, metrics và logs từ cả proxy tới ứng dụng/downstream.
- Test riêng từng tầng, gồm cả network/proxy/Servlet, không chỉ MockMvc.
- Kiểm chứng HTTP status/error body khi response đã bắt đầu streaming hoặc client đã ngắt kết nối.
- Theo dõi p95/p99 latency, 4xx/5xx distribution, client timeouts và dependency failures theo route/hop.

**Kết luận:** Lỗi web không có một tầng duy nhất. **Mạng/proxy** có thể thất bại trước HTTP hoặc trước ứng dụng; **Servlet container** có thể từ chối request trước filter; **Filter/Spring Security** có thể dừng request trước DispatcherServlet; **Spring MVC** có thể lỗi khi matching, binding hoặc gọi controller; **service** có thể phát hiện business rule hoặc hạ tầng không đáp ứng. Thiết kế đúng là xử lý và ghi nhận lỗi ở **tầng có đủ ngữ cảnh**, chỉ chuyển thành HTTP status/body tại ranh giới phù hợp, và dùng test/trace để chứng minh đường đi thực tế.