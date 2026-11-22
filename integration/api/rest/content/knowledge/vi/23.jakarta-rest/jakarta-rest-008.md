# ExceptionMapper và định dạng lỗi thống nhất

> **Module:** `INTEGRATION_API_REST` — chương **Jakarta REST**. Bài học thiết kế lỗi cho REST API dựa trên resource, URI, phương thức, mã trạng thái HTTP và hợp đồng dữ liệu rõ ràng. Trọng tâm: `ExceptionMapper` trong Jakarta REST (JAX-RS), `@Provider`, định dạng **Problem Details (RFC 9457)**, bảo mật, kiểm thử và cách đối chiếu với Java/Spring MVC. Những nguyên tắc này cũng hữu ích khi API có phân trang, cache, idempotency hay xử lý bất đồng bộ.

## 1. Tình huống: cùng một lỗi nghiệp vụ, nhiều kiểu phản hồi

`GET /v1/orders/ord_missing` không tìm thấy đơn; `POST /v1/orders/ord_916/cancellations` muốn hủy đơn đã giao. Nếu một endpoint trả `500`, endpoint khác trả `200 {"success":false}`, consumer không biết nên retry, sửa input hay dừng thao tác.

Một hợp đồng nhất quán cho lỗi không thể hủy:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-not-cancellable",
  "title": "Order cannot be cancelled",
  "status": 409,
  "code": "ORDER_NOT_CANCELLABLE",
  "detail": "Đơn hàng đã giao, không thể yêu cầu hủy."
}
~~~

**Exception là cơ chế Java để báo lỗi; HTTP status và representation mới là hợp đồng giữa client với server.** Jakarta REST cung cấp `ExceptionMapper<E>` để đặt ranh giới rõ giữa hai lớp này.

**Sau bài học**, bạn có thể đăng ký mapper đúng loại, tạo Problem Details ổn định, phân loại status, bảo toàn HTTP headers, viết Java/Jakarta REST và so sánh Spring, kiểm thử lỗi và bảo mật.

## 2. `ExceptionMapper` đứng ở đâu trong Jakarta REST?

`ExceptionMapper<E extends Throwable>` là hợp đồng SPI:

~~~java
package jakarta.ws.rs.ext;

public interface ExceptionMapper<E extends Throwable> {
    jakarta.ws.rs.core.Response toResponse(E exception);
}
~~~

Khi lỗi phát sinh trong quá trình một runtime Jakarta REST xử lý request, runtime tìm mapper áp dụng cho loại exception đó và dùng `Response` mapper trả về. Provider thường được đăng ký bằng `@Provider` và cơ chế discovery/configuration của implementation.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Security, routing, JAX-RS runtime"]
    B --> C["Resource -> service -> persistence"]
    C --> D{"Có exception?"}
    D -- "Không" --> H["2xx/3xx HTTP response"]
    D -- "Có" --> E["Tìm ExceptionMapper phù hợp"]
    E --> F{"Có mapper?"}
    F -- "Có" --> G["Response status + headers + entity"]
    F -- "Không" --> I["Xử lý mặc định của runtime/container"]
    G --> J["MessageBodyWriter/serialization"]
~~~

`@Provider` không phải endpoint; mapper được gọi **sau khi có exception** và cần nhanh, không truy vấn nặng hoặc ném lỗi mới.

### 2.1. Kiểu exception quyết định mapper

Runtime chọn mapper phù hợp với exception, thường ưu tiên kiểu gần nhất trong cây kế thừa. Mapper quá rộng như `ExceptionMapper<Throwable>` có thể bắt cả lỗi framework. Đừng đăng ký hai mapper cạnh tranh cho cùng một kiểu hoặc dùng `@Priority` để thay thế phân loại đúng.

### 2.2. Đăng ký provider

~~~java
import jakarta.ws.rs.ApplicationPath;
import jakarta.ws.rs.core.Application;
import java.util.Set;

@ApplicationPath("/api")
public class RestApplication extends Application {
    @Override
    public Set<Class<?>> getClasses() {
        return Set.of(
            OrderResource.class,
            OrderNotFoundMapper.class,
            OrderConflictMapper.class,
            UnexpectedExceptionMapper.class
        );
    }
}
~~~

Đăng ký đủ resource/provider; `@ApplicationPath("/api")` cùng `@Path("/v1/orders")` tạo URI `/api/v1/orders`. Discovery/CDI tùy runtime; **không mặc định `@Provider` luôn tự được scan**.

### 2.3. Những lỗi không nhất thiết đi qua mapper

Một số lỗi xảy ra ở **reverse proxy, servlet container, auth filter trước JAX-RS**, hoặc lúc response đã bắt đầu stream. Chúng có thể không đi qua `ExceptionMapper`. Trước khi thiết kế error format, xác định tầng nào sở hữu lỗi:

| Nơi phát sinh | Cơ chế xử lý điển hình |
|---|---|
| Resource/service JAX-RS | `ExceptionMapper` đã đăng ký |
| Parse body / matching / Jakarta REST validation | Mapper hoặc cơ chế mặc định của runtime |
| Servlet/security filter chạy trước JAX-RS | Filter/security entry point riêng |
| API gateway từ chối payload lớn | Hợp đồng lỗi của gateway |
| Streaming đã gửi header/byte đầu tiên | Không thể tin rằng còn đổi status/body được |

Gateway hoặc security filter vẫn có thể trả định dạng lỗi khác.

## 3. Hợp đồng lỗi `application/problem+json` theo RFC 9457

Problem Details định nghĩa các member chung:

| Member | Vai trò | Lưu ý |
|---|---|---|
| `type` | URI nhận diện loại vấn đề | Giữ ổn định; nên có tài liệu tại URI |
| `title` | Nhãn ngắn để đọc | Không chứa secret/PII |
| `status` | Status HTTP cho lần gặp lỗi | Phải khớp status line ở response gốc |
| `detail` | Mô tả occurrence cụ thể | Có thể địa phương hóa; không dùng làm khóa logic |
| `instance` | URI nhận diện lần phát sinh lỗi | Không chứa token/URL nội bộ |
| `code` | Mã lỗi **mở rộng do ứng dụng định nghĩa** | Dành cho client branching ổn định |
| `errors` | Mảng field errors mở rộng, nếu cần | Giới hạn kích thước và giá trị phản hồi |
| `traceId` | Correlation ID mở rộng, nếu cần | Sinh/xác minh tại server |

`type` nên là URI ổn định; client không cần fetch nó mỗi lần. `code/errors/traceId` là extension phải được tài liệu hóa.

### 3.1. Field errors có kiểm soát

Với lỗi 400, có thể thêm `"errors":[{"field":"productId","code":"NotBlank"},{"field":"quantity","code":"Min"}]`. Không trả `rejectedValue` chứa PII; `detail` có thể dịch, còn client dựa vào `status/type/code`.

### 3.2. Status, header và body cần khớp nhau

Một mapper có thể gọi `Response.status(409).type("application/problem+json").entity(problem).build()`. Tuy nhiên:

- `401` phải có challenge phù hợp, thường là `WWW-Authenticate: Bearer ...` với OAuth 2.0 Bearer.
- `405` phải bảo toàn `Allow`; `429` hoặc `503` có thể kèm `Retry-After`.
- `406` là không thương lượng được response; đừng ép JSON body khi client chỉ chấp nhận XML. Có thể trả `406` **không body**.
- `204`, `304` và `HEAD` có quy tắc không gửi response body; không cố nhét Problem Details vào các trường hợp đó.
- Dữ liệu người dùng không nên cache công khai; với lỗi chứa chi tiết cá nhân, dùng `Cache-Control: no-store` hoặc chính sách cache đã phân tích.

Nếu response đã gửi một phần stream rồi mới lỗi, bạn thường **không thể** thay `200` thành `500` và xuất JSON lỗi mới. Thiết kế streaming protocol, checksum và log kết nối bị cắt thay vì giả rằng mapper sẽ sửa được HTTP status.

## 4. Bảng ánh xạ: lỗi nghiệp vụ và lỗi kỹ thuật

| Nguyên nhân thật | Status HTTP | Ứng xử của consumer |
|---|---|---|
| JSON malformed, query/path sai kiểu | `400 Bad Request` | Sửa request |
| DTO thiếu hoặc sai constraint | `400`, hoặc `422` nếu contract chọn | Hiển thị field error |
| Thiếu/hết hạn token | `401 Unauthorized` | Xác thực lại |
| Có danh tính nhưng thiếu quyền | `403 Forbidden` hoặc `404` để che tồn tại | Không suy đoán object khác |
| Resource không tìm thấy trong phạm vi được phép | `404 Not Found` | Kiểm tra ID/URI |
| Action mâu thuẫn trạng thái | `409 Conflict` | GET lại trạng thái |
| `If-Match` đã gửi nhưng ETag sai | `412 Precondition Failed` | Tải representation mới |
| Endpoint yêu cầu `If-Match` nhưng header thiếu | `428 Precondition Required` | Gửi precondition |
| Payload có media type không hỗ trợ | `415 Unsupported Media Type` | Đổi `Content-Type` |
| Client chỉ chấp nhận representation server không tạo được | `406 Not Acceptable` | Đổi `Accept` |
| Giới hạn body vượt quá | `413 Content Too Large` | Không retry cùng payload vô hạn |
| Vượt rate limit hoặc quota | `429 Too Many Requests` | Backoff có giới hạn |
| Lỗi DB/storage/network bất thường | `500` hoặc `503` tùy tình huống | Theo chính sách retry/alert |

**Không map exception theo tên Java một cách máy móc.** `PersistenceException` có thể do unique constraint nghiệp vụ hoặc do bug schema. `OptimisticLockException` có thể là conflict 409, nhưng chỉ dùng `412` khi thực sự là precondition HTTP thất bại. Phân loại ở tầng service hoặc adapter rồi ném **domain exception có nghĩa**, không để `ExceptionMapper<Throwable>` dò SQL message để đoán status.

### 4.1. Phân biệt request validation và lỗi server

Một request có `quantity=0` là lỗi input, nhưng kiểm tra business như “hết tồn kho” có thể là 409/422 theo hợp đồng. Trái lại, `NullPointerException`, lỗi commit hoặc mất kết nối DB không phải 400. Nếu mapper biến mọi runtime exception thành 400, client bị đổ lỗi sai và hệ thống vận hành mất tín hiệu 5xx.

## 5. Java/Jakarta REST: resource chỉ nêu happy path

Ví dụ minh họa với **Jakarta REST 3.x**, Java 17 và Jakarta Bean Validation. Resource nhận request JSON, tạo đơn và xử lý yêu cầu hủy. Phụ thuộc như CDI, JSON-B/Jackson/JSON-P provider, persistence và JWT security phải được cấu hình trong runtime thực tế.

### 5.1. DTO input tách khỏi entity

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
    @NotBlank String productId,
    @NotNull @Min(1) Integer quantity
) {}

public record OrderView(
    String id, String status, String currency, String totalAmount
) {}
~~~

Không bind entity persistence từ request: `ownerId`, `tenantId`, `isPaid` và giá phải do server kiểm soát. JSON provider phải serialize record đúng.

### 5.2. Resource và các domain exception

~~~java
import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.*;
import java.net.URI;

@Path("/v1/orders")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public class OrderResource {
    @Inject OrderService orders;
    @Context SecurityContext security;
    @Context UriInfo uriInfo;

    @GET
    @Path("{id}")
    public OrderView get(@PathParam("id") String id) {
        return orders.readVisible(principal(), id);
    }

    @POST
    public Response create(@Valid CreateOrderRequest request) {
        OrderView created = orders.createAuthorized(principal(), request);
        URI location = uriInfo.getAbsolutePathBuilder()
            .path(created.id()).build();
        return Response.created(location).entity(created).build();
    }

    @POST
    @Path("{id}/cancellations")
    public Response cancel(@PathParam("id") String id) {
        orders.cancelAuthorized(principal(), id);
        return Response.noContent().build();
    }

    private String principal() {
        if (security.getUserPrincipal() == null) {
            throw new NotAuthorizedException("Bearer");
        }
        return security.getUserPrincipal().getName();
    }
}

interface OrderService {
    OrderView readVisible(String subject, String id);
    OrderView createAuthorized(String subject, CreateOrderRequest body);
    void cancelAuthorized(String subject, String id);
}
~~~

`GET` trả 200; tạo đơn **201 Location**; hủy đồng bộ 204, hoặc 202 + operation monitor khi bất đồng bộ. `@Consumes` chi phối request body; GET không có body dùng `Accept` để yêu cầu response.

Xác thực ở security layer trước resource; `SecurityContext` và `@RolesAllowed` **không thay** kiểm tra tenant/owner/ACL tại service.

Giả sử service ném các loại exception sau:

~~~java
public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException() {
        super("Order unavailable");
    }
}

public final class OrderConflictException extends RuntimeException {
    public OrderConflictException() {
        super("Order state conflict");
    }
}
~~~

Trong dự án thật, mỗi public class được đặt trong file Java riêng. Service chỉ biểu đạt lý do domain; nó **không** hardcode `Response.status(409)` hoặc phụ thuộc trực tiếp vào HTTP. Cách này giúp cùng service được gọi từ batch, message consumer hoặc REST resource.

## 6. Xây Problem Details một lần, dùng trong nhiều mapper

Có thể dùng JSON-P `JsonObject` để tạo body không phụ thuộc vào một entity JPA. Ví dụ dưới đây **giả định runtime đã đăng ký JSON-P `MessageBodyWriter`** cho `JsonObject` và media type `application/problem+json`; nếu không có, cài JSON provider phù hợp hoặc chuyển sang một DTO/serializer đã kiểm thử.

~~~java
import jakarta.json.Json;
import jakarta.json.JsonObject;
import jakarta.ws.rs.core.Response;

public final class Problems {
    private static final String BASE =
        "https://api.example.test/problems/";

    private Problems() {}

    public static Response of(
            int status, String typeSlug, String title,
            String code, String safeDetail) {
        JsonObject body = Json.createObjectBuilder()
            .add("type", BASE + typeSlug)
            .add("title", title)
            .add("status", status)
            .add("code", code)
            .add("detail", safeDetail)
            .build();
        return Response.status(status)
            .type("application/problem+json")
            .header("Cache-Control", "no-store")
            .entity(body)
            .build();
    }
}
~~~

Ở đây `status` trong body trùng response line. `title` và `safeDetail` được **viết có chủ đích**, không lấy trực tiếp từ `exception.getMessage()`. Nếu bổ sung `traceId`, lấy giá trị do server phát sinh hoặc đã được gateway xác minh; tránh nhét URL chứa token hoặc dữ liệu tenant khác vào `instance`.

### 6.1. Mappers chuyên biệt cho domain

~~~java
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

@Provider
public final class OrderNotFoundMapper
        implements ExceptionMapper<OrderNotFoundException> {
    @Override
    public Response toResponse(OrderNotFoundException exception) {
        return Problems.of(404, "order-not-found",
            "Order not found", "ORDER_NOT_FOUND",
            "Không tìm thấy đơn hàng được phép truy cập.");
    }
}

@Provider
public final class OrderConflictMapper
        implements ExceptionMapper<OrderConflictException> {
    @Override
    public Response toResponse(OrderConflictException exception) {
        return Problems.of(409, "order-state-conflict",
            "Order state conflict", "ORDER_STATE_CONFLICT",
            "Trạng thái hiện tại không cho phép thao tác.");
    }
}
~~~

Đây là **hai public class riêng**, minh họa gộp vào một khối code cho dễ đọc. Các mapper có status cố định nên rất dễ unit test. Đừng dùng một exception chung `BusinessException` với raw message tự cung cấp bởi client làm `detail`, vì message có thể không an toàn hoặc thay đổi không kiểm soát.

### 6.2. Fallback mapper: không phá `WebApplicationException`

Một `ExceptionMapper<Exception>` dùng cho lỗi chưa có mapper chuyên biệt có thể trả 500, nhưng cần giữ nguyên các HTTP exception do runtime tạo ra:

~~~java
import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import java.util.logging.Level;
import java.util.logging.Logger;

@Provider
public final class UnexpectedExceptionMapper
        implements ExceptionMapper<Exception> {
    private static final Logger LOG =
        Logger.getLogger(UnexpectedExceptionMapper.class.getName());

    @Override
    public Response toResponse(Exception exception) {
        if (exception instanceof WebApplicationException http) {
            // Không vô tình biến 400/401/403/404/405/406/415 thành 500,
            // không làm mất các headers của response hiện có.
            return http.getResponse();
        }
        LOG.log(Level.SEVERE,
            "Unhandled REST exception", exception);
        return Problems.of(500, "internal-error",
            "Internal server error", "INTERNAL_ERROR",
            "Không thể hoàn tất yêu cầu lúc này.");
    }
}
~~~

**Đánh đổi quan trọng:** cách `return http.getResponse()` **giữ status và headers** như `Allow`, `WWW-Authenticate`, nhưng body của lỗi framework có thể **không** theo Problem Details. Muốn chuẩn hóa cả lỗi `BadRequestException`, `NotAllowedException`, `NotSupportedException` và `NotAcceptableException`, cần mapper cụ thể hoặc một adapter HTTP đã kiểm thử, bảo toàn status/header và xử lý riêng `406`/`HEAD`. Đừng gọi `Response.status(http.getResponse().getStatus())` rồi vô tình vứt hết headers.

Fallback này cũng không phải “tường lửa” cho mọi lỗi: sự cố trước JAX-RS, sau khi response commit, hoặc lỗi khi serialize body của chính mapper có thể đi theo đường khác. Không cho rằng mọi `Error` cấp JVM đều xử lý an toàn được; lỗi nghiêm trọng như hết bộ nhớ cần giới hạn tải/giám sát và chính sách khởi động lại phù hợp.

### 6.3. Lỗi 500 phải an toàn

Không trả stack trace, SQL, storage key hoặc token. Giữ `type/code` ổn định và log nội bộ với `traceId` an toàn, không xuất chi tiết hạ tầng cho client.

## 7. Lỗi do runtime: validation, JSON parsing và media type

Không phải exception nào cũng do resource chủ động ném.

### 7.1. Bean Validation

`@Valid CreateOrderRequest` có thể kích hoạt Jakarta Bean Validation khi runtime có tích hợp validation provider. Lỗi tham số đầu vào thường nên trả **400** cùng danh sách trường không hợp lệ, ví dụ `quantity: Min`. Tuy nhiên:

- Có runtime trả lỗi validation mặc định không giống mapper bạn mong đợi; kiểm thử với implementation/version đang dùng.
- `jakarta.validation.ConstraintViolationException` không phải lúc nào cũng là **lỗi đầu vào**: nếu validation thất bại trên **giá trị trả về của resource**, đây có thể là lỗi server 500. Không map tất cả `ConstraintViolationException` thành 400.
- Chỉ trả field name và mã constraint được phép công khai; giới hạn số lỗi, tránh `invalidValue` chứa PII.

Muốn đồng nhất lỗi form/DTO phức tạp, có thể validate input ở boundary và ném `RequestValidationException` chứa danh sách lỗi đã được lọc, rồi đăng ký `ExceptionMapper<RequestValidationException>` trả 400. Đồng thời cần cấu hình xử lý validation mặc định của runtime để không tạo hai kiểu body khác nhau.

### 7.2. Parse JSON, tham số và negotiated representation

| Trường hợp | Exception có thể gặp | Chính sách HTTP |
|---|---|---|
| JSON sai cú pháp hoặc không đọc được | Reader/JSON provider có thể phát `BadRequestException` hoặc exception được wrap | `400` |
| `@PathParam`/`@QueryParam` sai kiểu | Runtime conversion exception, status phụ thuộc loại và ngữ cảnh | `400` hoặc `404` theo quy định runtime |
| `Content-Type` không được resource hỗ trợ | `NotSupportedException` | `415` |
| `Accept` không chấp nhận response có thể xuất | `NotAcceptableException` | `406` |
| Method không được hỗ trợ trên URI | `NotAllowedException` | `405` và `Allow` |

Không cố bắt chính xác `JsonProcessingException` trong mọi runtime: JSON-B, JSON-P hay Jackson có thể wrap nó khác nhau. **Kiểm tra response quan sát được**, không phụ thuộc implementation detail của một thư viện.

### 7.3. Chuẩn HTTP quan trọng hơn sự đồng nhất hình thức

`Content-Type: text/plain` gửi vào `@Consumes(application/json)` → **415**, dù bytes giống JSON. `Accept: application/xml` với server chỉ trả JSON → **406**; có thể không gửi body thay vì ép `application/problem+json`. Nếu server quảng bá một format nhưng serializer lỗi, đó là lỗi server, không phải 406.

## 8. Bảo mật: mapper không thay xác thực và phân quyền

Phần lớn lỗi bảo mật phải được chặn **trước khi đọc hoặc trả dữ liệu nhạy cảm**:

- **401 Unauthorized:** thiếu/hết hạn token hoặc không thể xác thực; có `WWW-Authenticate` hợp lệ theo cơ chế đang dùng.
- **403 Forbidden:** đã xác thực nhưng không có quyền thực hiện action.
- **404 Not Found có chủ đích:** với object ngoài tenant, API có thể che sự tồn tại. Trong log nội bộ vẫn biết lý do thật.
- **429 Too Many Requests:** vượt quota/rate; kèm `Retry-After` khi có căn cứ thời gian retry.

`@RolesAllowed("ORDER_READER")` (khi runtime đã bật Jakarta Security/role checks) có thể là lớp quyền thao tác tổng quát, nhưng **không đủ** để quyết định caller được đọc đơn `ord_916`. Service phải lọc theo owner/tenant/ACL từ danh tính đã xác minh, chống **BOLA/IDOR**.

Không được dựa vào client gửi `tenantId` trong body hoặc header tùy ý để mở quyền. Nếu service không tìm thấy row trong phạm vi caller, có thể ném cùng `OrderNotFoundException` cho cả ID không tồn tại và ID ngoài quyền. Mapper chỉ trả thông báo chung, không phân biệt hai nguyên nhân với người gọi.

### 8.1. Lỗi xuất hiện trước JAX-RS

JWT validation có thể chạy tại gateway, container hoặc `ContainerRequestFilter`; filter có thể `abortWith(response)` trước khi vào resource. Xác minh chữ ký/issuer/audience/expiration/scope thực sự, không coi chuỗi Bearer là identity. Giữ `WWW-Authenticate`, kiểm object-level permission ở service, không lộ token. Có thể dùng cùng mã lỗi giữa các tầng, nhưng mapper JAX-RS không tự xử lý lỗi gateway/filter.

## 9. So sánh Jakarta REST và Spring MVC

| Mục đích | Jakarta REST (JAX-RS) | Spring MVC |
|---|---|---|
| Định nghĩa endpoint | `@Path`, `@GET`, `@POST` | `@RequestMapping`, `@GetMapping`, `@PostMapping` |
| Chuyển exception thành response | `ExceptionMapper<T>` + `@Provider` | `@ExceptionHandler` + `@RestControllerAdvice` |
| Kết quả HTTP | `jakarta.ws.rs.core.Response` | `ResponseEntity<?>` |
| Body lỗi chuẩn | Tự xây Problem Details / JSON provider | `org.springframework.http.ProblemDetail` (Spring 6+) |
| Lỗi trước controller | Container/security filter | Spring Security filter chain |
| Framework errors | JAX-RS runtime/providers | `ResponseEntityExceptionHandler` và MVC resolvers |

Ví dụ **Spring MVC tương đương** với mapper domain 409:

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class SpringOrderErrorAdvice {
    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ProblemDetail> orderConflict(
            OrderConflictException error) {
        ProblemDetail p =
            ProblemDetail.forStatus(HttpStatus.CONFLICT);
        p.setType(URI.create(
            "https://api.example.test/problems/order-state-conflict"));
        p.setTitle("Order state conflict");
        p.setDetail("Trạng thái hiện tại không cho phép thao tác.");
        p.setProperty("code", "ORDER_STATE_CONFLICT");
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Đây là **đối chiếu**, không chạy hai handler đồng thời. Với Jakarta REST/Jersey trong Spring Boot, MVC `@RestControllerAdvice` **không tự xử lý** exception JAX-RS; dùng `ExceptionMapper`. Với `@RestController` dùng MVC advice. Cả hai cần test security riêng.

## 10. OpenAPI 3.1: biến định dạng lỗi thành hợp đồng

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /v1/orders/{id}:
    get:
      security: [{bearerAuth: []}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200': {description: Đơn hàng trong phạm vi được phép}
        '401': {description: Chưa xác thực}
        '404': {$ref: '#/components/responses/Problem'}
  /v1/orders/{id}/cancellations:
    post:
      security: [{bearerAuth: []}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '204': {description: Đã hủy đơn theo hợp đồng đồng bộ}
        '403': {description: Thiếu quyền}
        '409': {$ref: '#/components/responses/Problem'}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  responses:
    Problem:
      description: Lỗi theo RFC 9457
      content:
        application/problem+json:
          schema: {$ref: '#/components/schemas/Problem'}
  schemas:
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        instance: {type: string, format: uri-reference}
        code: {type: string}
~~~

Trong hệ thống hoàn chỉnh, mô tả cả `400/405/406/415/422/429/500/503` khi có và các header như `Allow`, `WWW-Authenticate`, `Retry-After`. Tài liệu chỉ nói **contract mong đợi**, không tự khiến implementation đăng ký mapper hoặc security filter. Cần đối chiếu OpenAPI với HTTP response thực tế, đặc biệt khi có lỗi đến từ gateway.

## 11. Kiểm thử: quan sát lỗi từ HTTP thay vì chỉ gọi mapper

Test unit của `OrderConflictMapper.toResponse(...)` hữu ích, nhưng không chứng minh `@Provider` đã được đăng ký, JSON provider serialize được `JsonObject` hoặc endpoint thật trả đúng 409. Cần **integration test khởi động runtime Jakarta REST**.

Ví dụ dùng Jersey Test Framework (thêm dependency test tương ứng với Jersey/Jakarta REST phiên bản đang chạy):

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Application;
import jakarta.ws.rs.core.Response;
import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.test.JerseyTest;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderProblemHttpTest extends JerseyTest {
    @Override
    protected Application configure() {
        return new ResourceConfig()
            .register(DemoResource.class)
            .register(OrderNotFoundMapper.class)
            .register(OrderConflictMapper.class)
            .register(UnexpectedExceptionMapper.class);
        // Cần thêm JSON-P entity writer/provider tương ứng runtime.
    }

    @Path("/demo")
    public static class DemoResource {
        @GET
        @Path("/missing")
        public String missing() {
            throw new OrderNotFoundException();
        }
    }

    @Test
    void shouldMapMissingResourceToProblem() {
        try (Response response = target("demo/missing")
                .request("application/json")
                .get()) {
            assertEquals(404, response.getStatus());
            assertEquals("application/problem+json",
                response.getMediaType().toString());
            String json = response.readEntity(String.class);
            assertTrue(json.contains("ORDER_NOT_FOUND"));
            assertFalse(json.contains("java.lang."));
        }
    }
}
~~~

Đây là **lát cắt test minh họa**: cần cấu hình runtime và provider JSON-P thực, đồng thời các class exception/mapper như mục trước. Để xác minh nội dung mạnh hơn, hãy parse JSON và assert `type`, `status`, `code`; test độc lập còn nên kiểm tra cache header. Với implementation khác, dùng HTTP integration test phù hợp, không bắt buộc JerseyTest.

### 11.1. Ma trận test nên có

| Request hoặc lỗi được tạo | Status / điều kiện xác minh |
|---|---|
| ID hợp lệ nhưng không có đơn | `404`, Problem type/code ổn định |
| ID thuộc tenant khác | `404` hoặc `403` đúng policy, không lộ owner |
| Hủy đơn đã giao | `409`, không thay đổi DB |
| DTO vi phạm `@Valid` | `400` hoặc `422` theo contract, field errors an toàn |
| JSON malformed | `400`, không lộ parser stack trace |
| `Content-Type` không hỗ trợ | `415`, không chạy logic tạo đơn |
| `Accept` chỉ XML, server chỉ JSON | `406`, không ép JSON body |
| Method không hỗ trợ | `405`, giữ `Allow` |
| Token thiếu hoặc scope không đủ | `401`/`403` qua security, giữ header cần thiết |
| `If-Match` stale | `412`, không ghi đè state |
| Lỗi DB/storage bất ngờ | `5xx`, không lộ SQL/JDBC URL |
| Lỗi 429 do quota | `429`; `Retry-After` nếu có policy |

Chạy test với cả request hợp lệ về quyền và request không có token để tránh **401 che mất 415/406**. Kiểm tra DB trong integration test, không chỉ assert JSON. Đối với lỗi trong stream đã commit, assert hành vi ngắt kết nối/observability thay vì kỳ vọng mapper thay status thành 500.

## 12. Bài tập: chuẩn hóa lỗi API quản lý đơn hàng

**Bối cảnh:** ứng dụng dùng Jakarta REST/Jersey nhận JSON ở `POST /v1/orders`, đọc `GET /v1/orders/{id}`, hủy `POST /v1/orders/{id}/cancellations`. Một số resource đang viết `try/catch` trả `200 {"error":"..."}`, một số còn trả exception message từ database.

**Yêu cầu thực hiện:**

1. Định nghĩa ít nhất bốn domain exceptions: không tìm thấy, không thể hủy, vi phạm quota và stale version. Chọn status cùng lý do.
2. Viết `Problems` factory tạo `application/problem+json`, có `type`/`title`/`status`/`code` ổn định; không trả raw stack.
3. Đăng ký `@Provider ExceptionMapper<T>` chuyên biệt cho 404/409; thêm fallback mà **không biến** `WebApplicationException` thành 500.
4. Thiết kế cách xử lý 400 từ `@Valid` và JSON malformed, giải thích trường hợp return-value validation phải coi là lỗi server.
5. Cấu hình auth/tenant ACL; xác minh caller ngoài tenant không biết tên chủ đơn và 401 có challenge phù hợp.
6. Bổ sung OpenAPI cho 400/401/404/409/412/415/429; ghi rõ trường `code` là extension.
7. Tạo tối thiểu tám HTTP integration tests, gồm `Allow` khi 405, `Accept` không tương thích, lỗi SQL bị che, stale `If-Match` và transaction không thay đổi khi lỗi.

**Gợi ý:** lỗi nghiệp vụ được quyết định ở service; mapper chỉ chuyển sang HTTP. Khi xử lý 405/401/429, đừng đánh mất header; khi đã bắt đầu gửi stream, đừng cố trả Problem Details như một response mới. Nếu ứng dụng dùng Spring MVC thay Jakarta REST, chuyển cơ chế sang `@RestControllerAdvice` nhưng giữ **cùng hợp đồng HTTP**.

## 13. Ghi nhớ

`ExceptionMapper` và `@Provider` tập trung ánh xạ exception sang HTTP trong Jakarta REST. RFC 9457 giúp client dùng `status/type/code` ổn định, nhưng **không được đánh đổi ngữ nghĩa HTTP để có JSON đồng nhất**.

Chọn mapper chuyên biệt cho domain, để lỗi validation/framework đi theo chính sách được kiểm thử, giữ nguyên header thiết yếu, xử lý 401/403 ở security boundary và giấu thông tin nội bộ khi có 5xx. Một hợp đồng lỗi thực sự thống nhất phải được xác nhận **qua HTTP integration tests, quyền truy cập và trạng thái dữ liệu sau thất bại**, không chỉ bằng việc có class `ExceptionMapper`.
