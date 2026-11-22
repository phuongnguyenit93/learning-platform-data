# Jakarta RESTful Web Services và tên gọi JAX-RS

## 1. Một công nghệ, hai cách gọi thường gặp

Khi đọc một dự án Java làm REST API, bạn có thể bắt gặp **JAX-RS**, **Jakarta REST** và tên đầy đủ **Jakarta RESTful Web Services**. Chúng liên quan trực tiếp đến nhau, nhưng **không phải ba framework riêng**:

- **JAX-RS** là tên lịch sử **Java API for RESTful Web Services** trong Java EE; vẫn thường gặp trong tên công cụ/tài liệu.
- **Jakarta RESTful Web Services** là tên đặc tả Jakarta EE hiện nay; gọi ngắn là **Jakarta REST**.
- **Jersey, RESTEasy, Apache CXF** là các runtime/implementation, **không phải** đặc tả.

Ví dụ cùng một ý tưởng xử lý request `GET /api/orders/o-42`:

~~~java
// Java EE / JAX-RS cũ
import javax.ws.rs.GET;
import javax.ws.rs.Path;

// Jakarta REST hiện đại
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
~~~

Đây là **thay đổi nhị phân/mã nguồn**, không chỉ đổi tên. Jakarta EE 9+ dùng `jakarta.ws.rs.*`; code JAX-RS 2.x cũ thường dùng `javax.ws.rs.*`. Hai namespace không tự tương thích.

Bài thuộc chương **Jakarta REST**, module **INTEGRATION_API_REST**: thiết kế resource/URI, HTTP methods/status, hợp đồng dữ liệu, cache, idempotency, OpenAPI, bảo mật và kiểm thử Java/Spring.

**Mục tiêu:** nhận diện tên/phiên bản, viết resource, phân biệt đặc tả/runtime/Spring MVC và kiểm thử bảo mật qua HTTP thật.

## 2. Dòng thời gian: JAX-RS → Jakarta REST

| Thời kỳ/phiên bản | Hệ sinh thái | Namespace API | Điều cần nhớ |
|---|---|---|---|
| **JAX-RS 1.x/2.x** | Java EE, JCP | `javax.ws.rs.*` | Tên JAX-RS xuất phát từ **Java API for RESTful Web Services** |
| **Jakarta REST 2.1** | Jakarta EE 8 | `javax.ws.rs.*` | Tên đặc tả chuyển sang Jakarta EE, **namespace chưa đổi** |
| **Jakarta REST 3.0** | Jakarta EE 9 | `jakarta.ws.rs.*` | **Đổi namespace**; mốc quan trọng khi nâng dự án |
| **Jakarta REST 3.1** | Jakarta EE 10 | `jakarta.ws.rs.*` | Bổ sung Java SE bootstrap, hỗ trợ multipart và cải tiến tích hợp |
| **Jakarta REST 4.0** | Jakarta EE 11 | `jakarta.ws.rs.*` | Điều chỉnh tích hợp, loại bỏ yêu cầu JAXB/Managed Beans; Java SE 17+ |

Tính đến thời điểm biên soạn, trang đặc tả chính thức còn liệt kê công việc **Jakarta REST 5.0 cho Jakarta EE 12**; trước khi chọn version cho sản phẩm cần kiểm tra tình trạng phát hành và implementation hỗ trợ **đúng phiên bản mong muốn**, thay vì tự đoán từ số mới nhất. Nguồn: [Danh mục Jakarta REST](https://jakarta.ee/specifications/restful-ws/), [Jakarta REST 3.0](https://jakarta.ee/specifications/restful-ws/3.0/), [3.1](https://jakarta.ee/specifications/restful-ws/3.1/) và [4.0](https://jakarta.ee/specifications/restful-ws/4.0/).

### 2.1. Ba phép nhầm cần tránh

1. **“JAX-RS là Jersey” — sai.** Jersey là một implementation; bạn cũng có thể dùng RESTEasy hoặc CXF tùy server và tổ chức.
2. **“Chuyển Jakarta chỉ cần đổi tên Maven artifact” — sai.** Package Java, server runtime, provider/extension và thư viện tích hợp phải dùng các thế hệ tương thích.
3. **“JAX-RS và JAX-WS giống nhau” — sai.** JAX-WS (nay thuộc Jakarta XML Web Services) thường liên quan SOAP/XML; JAX-RS/Jakarta REST tập trung Web resources và HTTP.

Tài liệu vẫn dùng “JAX-RS resource” ngay cả với `jakarta.ws.rs.Path`; hãy nêu rõ **Jakarta REST version, Jakarta EE version và implementation** khi phối hợp.

## 3. Đặc tả API khác runtime như thế nào?

Jakarta REST định nghĩa annotation, request mapping, content negotiation, providers, lỗi và client API, **không tạo server chỉ bằng JAR API**.

~~~mermaid
flowchart TD
    C["HTTP client"] --> S["HTTP server/container"]
    S --> R["Jakarta REST implementation: Jersey / RESTEasy / CXF"]
    R --> A["Resource classes (@Path, @GET, @POST...)"]
    R --> P["Providers: JSON, ExceptionMapper, filters"]
    A --> B["Service + transaction + repository"]
    B --> DB[("Database / downstream")]
~~~

| Thành phần | Đảm nhiệm | Không tự đảm nhiệm |
|---|---|---|
| **Jakarta REST API/spec** | `@Path`, `@GET`, `Response`, `Client`, quy tắc request/response | Server chạy, database, auth provider |
| **Runtime implementation** | Match URI, deserialize/serialize bằng provider, dispatch resource, map exception | Quy tắc nghiệp vụ đặc thù |
| **HTTP container/server** | Kết nối, network, TLS/Servlet integration theo deployment | Domain authorization từng order |
| **Ứng dụng** | Resource model, status, validation, tenant/ACL, idempotency, transaction | Không nên tự viết lại mọi việc của HTTP stack |

Jakarta EE server cung cấp runtime theo profile/cấu hình. Với Spring Boot, dùng Jersey starter; **`jakarta.ws.rs-api` đơn độc không khiến Spring MVC hiểu `@Path`**.

### 3.1. Maven API: compile-time không phải server

Với một Jakarta EE 10 application server cung cấp API/runtime, ví dụ:

~~~xml
<dependency>
    <groupId>jakarta.ws.rs</groupId>
    <artifactId>jakarta.ws.rs-api</artifactId>
    <version>3.1.0</version>
    <scope>provided</scope>
</dependency>
~~~

`provided` áp dụng khi container cung cấp đúng REST 3.1. Ứng dụng standalone còn cần runtime/server/JSON provider; tránh trộn thế hệ API/runtime.

## 4. Jakarta REST ánh xạ HTTP vào Java resource

Một URI `/api/orders/o-42` được định nghĩa bởi **đường cơ sở của ứng dụng** (ví dụ `/api`) và **resource path** (ví dụ `/orders/{id}`). Đoạn resource sau dùng import `jakarta.ws.rs.*`:

~~~java
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.inject.Inject;

@Path("/orders")
@Produces(MediaType.APPLICATION_JSON)
public class OrderResource {
    private final OrderService orders;

    @Inject
    public OrderResource(OrderService orders) {
        this.orders = orders;
    }

    @GET
    @Path("/{id}")
    public Response get(@PathParam("id") String id) {
        return orders.findVisible(id)
            .map(view -> Response.ok(view).build())
            .orElseGet(() -> Response.status(404).build());
    }

    @GET
    public Response list(
            @QueryParam("status") String status,
            @DefaultValue("20") @QueryParam("limit") int limit) {
        if (limit < 1 || limit > 100) {
            throw new BadRequestException("limit must be from 1 to 100");
        }
        return Response.ok(orders.listVisible(status, limit)).build();
    }
}
~~~

`OrderService` là lớp giả định; `@Inject` cần CDI/DI integration phù hợp. Mã chỉ minh họa **mapping**, chưa đủ bảo mật: phải kiểm tra principal/tenant và không coi ID trong path là quyền sở hữu.

### 4.1. Các annotation cốt lõi

| Jakarta REST | Ý nghĩa HTTP | Spring MVC tương ứng gần đúng |
|---|---|---|
| `@Path("/orders")` | Định tuyến resource/URI | `@RequestMapping("/orders")` |
| `@GET`, `@POST`, `@PUT`, `@PATCH`, `@DELETE` | HTTP method | `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping` |
| `@PathParam("id")` | Biến URI path | `@PathVariable("id")` |
| `@QueryParam("limit")` | Query parameter | `@RequestParam("limit")` |
| `@HeaderParam("If-Match")` | HTTP request header | `@RequestHeader("If-Match")` |
| `@CookieParam("theme")` | Cookie value | `@CookieValue("theme")` |
| `@DefaultValue("20")` | Giá trị mặc định | `defaultValue = "20"` |
| `@Consumes` / `@Produces` | Media type request / response | `consumes` / `produces` trong mapping |
| `Response` | Status, header, entity | `ResponseEntity<?>` |

Đây là bảng **so sánh mục đích**, không phải mapping một-một: dispatch, exception, injection và validation khác nhau.

### 4.2. HTTP method và representation

~~~http
GET /api/orders/o-42 HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"id":"o-42","status":"CREATED","quantity":2}
~~~

`@Produces(APPLICATION_JSON)` khai báo representation, JSON provider phải mã hóa được DTO. `@Consumes` chọn reader; request media type sai có thể dẫn đến **415**, `Accept` không phù hợp có thể dẫn đến **406**.

## 5. Ví dụ POST: DTO, Location và status đúng ngữ nghĩa

Giả sử client tạo một đơn mới với `POST /api/orders`. Thành công nên trả **201 Created** và `Location` trỏ tới resource được tạo. Bản ghi cần được tạo **một lần về mặt nghiệp vụ**, đặc biệt khi client retry do mất response.

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
Idempotency-Key: "4d1807d9-02da-4a64-bdde-2e54c569a55d"

{"productId":"sku-18","quantity":2}

HTTP/1.1 201 Created
Location: /api/orders/o-100
Content-Type: application/json

{"id":"o-100","productId":"sku-18","quantity":2,"status":"CREATED"}
~~~

Một resource method Jakarta REST có thể viết:

~~~java
@POST
@Consumes(MediaType.APPLICATION_JSON)
public Response create(CreateOrderRequest body,
                       @HeaderParam("Idempotency-Key") String key,
                       @Context UriInfo uriInfo) {
    // Service kiểm quyền, validate, khóa idempotency, tạo bản ghi trong transaction.
    OrderView created = orders.createAuthorized(body, key);

    URI location = uriInfo.getAbsolutePathBuilder()
        .path(created.id())
        .build();
    return Response.created(location)
        .entity(created)
        .build();
}
~~~

`CreateOrderRequest`/`OrderView` là DTO. Entity parameter `body` không cần `@RequestBody`: `MessageBodyReader` đọc body. `UriInfo` tạo Location; `@Context` có lộ trình giảm dùng theo hướng CDI, cần kiểm tra khi nâng cấp.

`@HeaderParam` chỉ đọc chuỗi; lũy đẳng cần **scope/key, fingerprint, unique constraint, transaction và kết quả bền vững** để retry không tạo trùng.

### 5.1. Kiểm tra và mã hóa JSON

Jakarta EE theo profile có thể cung cấp JSON-B; Jersey standalone có thể cần provider Jackson/JSON-B. `jakarta.ws.rs-api` **không tự mã hóa DTO**. Xác định required/null/default qua DTO, validation và contract.

### 5.2. Các response cốt lõi trong REST API

| Tình huống | Status thường dùng | Jakarta REST |
|---|---|---|
| GET một resource thành công | **200 OK** | `Response.ok(entity).build()` |
| Tạo resource mới | **201 Created** | `Response.created(location).entity(entity).build()` |
| Đã nhận job bất đồng bộ | **202 Accepted** | `Response.accepted(receipt).build()` |
| Cập nhật/xóa thành công không body | **204 No Content** | `Response.noContent().build()` |
| Không thấy resource trong scope truy cập | **404 Not Found** | `throw new NotFoundException()` hoặc `Response.status(404)` |
| Conflict với trạng thái nghiệp vụ | **409 Conflict** | `Response.status(409)` / `ExceptionMapper` |
| Sai `If-Match` theo HTTP precondition | **412 Precondition Failed** | Xử lý điều kiện + transaction tại điểm ghi |
| Body không đúng media type | **415 Unsupported Media Type** | `@Consumes` và provider |

Status **không được quyết định chỉ bằng annotation framework**. HTTP 201/202/204/409 có ý nghĩa khác nhau; API cần nêu rõ khi nào có Location, body, contract retry và error payload. Đặc tả Jakarta REST cung cấp công cụ trả HTTP, nhưng không thiết kế resource lifecycle thay ứng dụng.

## 6. Xử lý lỗi, filter và kiểm tra dữ liệu

### 6.1. ExceptionMapper là gì?

Jakarta REST cung cấp `ExceptionMapper<E>` để chuyển exception sang HTTP response. Đây là cơ chế gần vai trò của `@RestControllerAdvice` trong Spring MVC, nhưng thuộc **runtime Jakarta REST**:

~~~java
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

@Provider
public class OrderConflictMapper
        implements ExceptionMapper<OrderAlreadySubmittedException> {

    @Override
    public Response toResponse(OrderAlreadySubmittedException exception) {
        var problem = Map.of(
            "type", "https://api.example.com/problems/order-conflict",
            "title", "Conflict",
            "status", 409,
            "code", "ORDER_ALREADY_SUBMITTED"
        );
        return Response.status(Response.Status.CONFLICT)
            .type("application/problem+json")
            .entity(problem)
            .build();
    }
}
~~~

`OrderAlreadySubmittedException` là class domain do ứng dụng định nghĩa. Mapper phải được runtime phát hiện/đăng ký; trong Jersey `ResourceConfig` có thể `register(OrderConflictMapper.class)`. `Map.of` chỉ là representation ví dụ, cần JSON provider; production nên có DTO lỗi rõ schema. Nếu exception chứa dữ liệu DB/tenant nhạy cảm, **không trả `exception.getMessage()` nguyên văn**.

### 6.2. Binding/conversion/validation không hoàn toàn giống Spring MVC

Ví dụ `@PathParam("id") UUID id`, `@QueryParam("limit") int limit` và body JSON được runtime/reader xử lý theo quy tắc Jakarta REST. Các trạng thái lỗi do parameter conversion có thể **khác Spring MVC** và khác giữa kiểu tham số/điểm injection; một số lỗi đường dẫn/query có thể trở thành **404** theo đặc tả thay vì 400 thường gặp trong Spring MVC.

Vì vậy cần **test HTTP thực** trên implementation đang chạy; nếu API hợp đồng công bố `400 INVALID_PARAMETER` cho giới hạn sai, hãy chuẩn hóa bằng `ExceptionMapper`/validator phù hợp, nhưng tránh map toàn bộ `NotFoundException` về 400 vì sẽ biến 404 của resource không tồn tại thành sai.

**Validation có nhiều lớp:** parse JSON → convert DTO → Bean Validation như `@NotNull`/`@Min` khi runtime tích hợp Jakarta Validation → domain service kiểm điều kiện phụ thuộc trạng thái database. Không gộp “thiếu quantity”, “quantity không phải số” và “đơn đã thanh toán” thành một exception. Với content type không tương thích, server có thể trả **415** trước khi đến body validation.

### 6.3. ContainerRequestFilter và ContainerResponseFilter

Jakarta REST hỗ trợ **provider/filter** ở ranh giới request/response, ví dụ ghi correlation ID, policy metadata, chuẩn hóa header hoặc audit:

~~~java
@Provider
public class RequestIdFilter
        implements ContainerRequestFilter, ContainerResponseFilter {

    private static final String ATTR = "request-id";

    @Override
    public void filter(ContainerRequestContext req) {
        String incoming = req.getHeaderString("X-Request-Id");
        String requestId = isSafeRequestId(incoming)
            ? incoming : UUID.randomUUID().toString();
        req.setProperty(ATTR, requestId);
    }

    @Override
    public void filter(ContainerRequestContext req,
                       ContainerResponseContext res) {
        res.getHeaders().putSingle(
            "X-Request-Id", req.getProperty(ATTR));
    }
}
~~~

`isSafeRequestId` là validator do ứng dụng định nghĩa: giới hạn độ dài/ký tự, không đưa input có CRLF hoặc secrets vào log/header. Code cần import `jakarta.ws.rs.container.*`, `@Provider` và `UUID`. **Không coi request ID từ client là danh tính được xác thực.** Provider/filter chỉ giải quyết vấn đề xuyên request; domain authorization nên ở service/gateway/tenant-scoped repository.

### 6.4. Tương tác với OpenAPI và Problem Details

Jakarta REST **không tự cung cấp đặc tả OpenAPI** chỉ nhờ `@Path`. Có thể dùng các giải pháp tích hợp phù hợp (ví dụ Jakarta/MicroProfile OpenAPI hoặc thư viện runtime), nhưng cần **kiểm tra schema được sinh** và thêm mô tả auth/status/lỗi. Body `application/problem+json` theo **RFC 9457** là hợp đồng HTTP độc lập framework: nó dùng được với Jakarta REST lẫn Spring.

## 7. Xác thực, phân quyền và tài nguyên đa tenant

### 7.1. @RolesAllowed chưa phải toàn bộ hệ thống bảo mật

Trong môi trường có Jakarta Security và role mapping được cấu hình, Jakarta REST resource có thể sử dụng `jakarta.annotation.security.RolesAllowed`:

~~~java
@Path("/admin/reports")
@RolesAllowed("report-admin")
public class ReportAdminResource {
    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public List<ReportView> listReports() {
        return reports.listForAuthorizedAdministrator();
    }
}
~~~

`@RolesAllowed` cần **container/security integration có thực thi annotation**, người gọi được xác thực và role được ánh xạ đúng. Nó **không tự định nghĩa** JWT signature verification, issuer/audience, session security, CSRF hoặc cách nạp role. Với Jersey nhúng Spring Boot, thường dùng **Spring Security và servlet filter chain** cùng cấu hình bổ sung; không được giả định mọi annotation Jakarta Security sẽ tự có tác dụng nếu chưa test.

### 7.2. SecurityContext và scope resource

Trong nhiều ứng dụng Jakarta REST 3.x/4.x có thể dùng `@Context SecurityContext` để biết caller đã xác thực, hoặc dùng CDI/security principal theo môi trường:

~~~java
@GET
@Path("/{id}")
public Response getOrder(
        @PathParam("id") String id,
        @Context SecurityContext security) {
    Principal principal = security.getUserPrincipal();
    if (principal == null) {
        throw new NotAuthorizedException("Bearer");
    }
    return service.findVisibleTo(principal.getName(), id)
        .map(v -> Response.ok(v).build())
        .orElseGet(() -> Response.status(404).build());
}
~~~

Đoạn mã là minh họa **resource-level ownership**; ở production cần quy định tenant và role trong principal đáng tin, kiểm tra quyền đọc mỗi order, lọc dữ liệu ở service/repository. `NotAuthorizedException("Bearer")` mô tả một challenge thích hợp cho kiểu auth đã chọn; không sử dụng mù nếu ứng dụng dùng session hoặc loại credential khác. Không dùng `@PathParam("tenantId")` làm bằng chứng caller sở hữu tenant.

### 7.3. Vì sao 404 đôi khi tốt hơn 403?

Nếu một order không thuộc tenant đang xác thực, `403` có thể tiết lộ resource tồn tại. Nhiều API chọn **404 trung tính** khi resource nằm ngoài phạm vi được phép xem; nếu user biết resource nhưng thiếu quyền thao tác cụ thể, `403` có thể phù hợp. Cần chọn chính sách và **test cross-tenant**, không trả thông tin trạng thái khác nhau dựa trên sự tồn tại bí mật của ID.

## 8. Dùng Jakarta REST trong Spring Boot: Jersey thay vì @RestController

Spring Boot sử dụng **Spring MVC** với `spring-boot-starter-web` hoặc **Spring WebFlux** với `spring-boot-starter-webflux` theo mặc định của stack. Controller `@RestController` và mapping `@GetMapping` là API của **Spring**, không phải annotation JAX-RS. Muốn viết `@Path`/`@GET` bên trong một ứng dụng Boot, hãy chọn implementation và tích hợp nó rõ ràng.

Tài liệu Spring Boot có hướng dẫn chính thức sử dụng **Jersey** qua starter; ví dụ dưới đây tập trung **Spring Boot 3.x với Servlet stack**. Không tự lấy một version Jersey thuộc nhánh Jakarta khác rồi ép vào BOM Boot nếu chưa kiểm chứng.

### 8.1. Maven và application path

~~~xml
<!-- pom.xml: project đã dùng Spring Boot 3.x parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jersey</artifactId>
</dependency>
~~~

~~~yaml
# application.yml
spring:
  jersey:
    application-path: /api
~~~

Spring Boot giúp tạo phần Jersey server runtime và integration tương thích qua starter. Để viết JSON, phải xác nhận **message body provider** có sẵn đúng theo dependency tree/stack đã chọn (thêm JSON-B/Jackson Jersey module nếu runtime yêu cầu). Tùy setup, bạn có thể dùng Jersey ở dạng Servlet hoặc Filter; tránh lắp trùng servlet mapping với Spring MVC endpoint cùng URI.

### 8.2. ResourceConfig đăng ký endpoint/mapper/filter

~~~java
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
public class JerseyConfiguration extends ResourceConfig {
    public JerseyConfiguration() {
        register(OrderResource.class);
        register(OrderConflictMapper.class);
        register(RequestIdFilter.class);
    }
}
~~~

Khi dùng Spring injection cho resource, có thể đặt `@Component` trên `OrderResource` và constructor injection cho `OrderService`; bảo đảm resource được Spring/Jersey quản lý thống nhất theo cấu hình. Trên Jakarta EE runtime độc lập, dùng CDI `@Inject`/cấu hình thích hợp thay vì phụ thuộc vào Spring `@Component`. **Constructor injection của service không xuất hiện tự động chỉ vì resource có `@Path`**.

Nếu một resource không được đăng ký, HTTP 404 có thể đến từ **Jersey không biết resource**, không phải đơn hàng không tồn tại. Vì vậy test phải chứng minh routing và startup thành công, ngoài logic của service.

### 8.3. So sánh hai cách triển khai cùng endpoint

~~~java
// Jakarta REST / Jersey
@Path("/orders")
public class OrderResource {
    @GET @Path("/{id}")
    public Response get(@PathParam("id") String id) {
        return Response.ok(service.find(id)).build();
    }
}

// Spring MVC
@RestController
@RequestMapping("/api/orders")
public class SpringOrderController {
    @GetMapping("/{id}")
    public ResponseEntity<OrderView> get(@PathVariable String id) {
        return ResponseEntity.ok(service.find(id));
    }
}
~~~

Hai ví dụ thể hiện **mục tiêu tương đương**, không phải hướng dẫn đăng ký cả hai controller cùng lúc. `@Path("/orders")` của Jersey nằm dưới `/api` do application path đã cấu hình; `@RequestMapping("/api/orders")` thuộc Spring MVC. Nếu chúng cùng chiếm `GET /api/orders/{id}` trong một deployment, việc chọn servlet/filter/handler có thể khác kỳ vọng. Chỉ chạy một route chính hoặc tách prefix.

**Khi nào dùng cách nào?** Với dự án **Jakarta EE/Jersey/RESTEasy** đã triển khai và được đội ngũ vận hành tốt, tiếp tục Jakarta REST là hợp lý. Với dự án **Spring Boot thuần** không có nhu cầu giữ JAX-RS annotation, Spring MVC/WebFlux thường giảm nhu cầu thêm runtime thứ hai. Chọn theo integration, khả năng kiểm thử, vận hành và hệ sinh thái, **không theo định kiến bên nào “REST hơn”**.

## 9. Jakarta REST Client API: gọi REST service khác

Từ JAX-RS 2.0, hệ API đã có **Client API**. Nó **khác phía server `@Path`**, nhưng dùng cùng mô hình Jakarta REST. Ví dụ GET từ dịch vụ đối tác:

~~~java
import jakarta.ws.rs.client.Client;
import jakarta.ws.rs.client.ClientBuilder;
import jakarta.ws.rs.core.Response;

try (Client client = ClientBuilder.newClient()) {
    try (Response response = client
            .target("https://partner.example.com/api/products/p-18")
            .request("application/json")
            .header("Authorization", "Bearer " + token)
            .get()) {
        if (response.getStatus() != 200) {
            throw new PartnerApiException(response.getStatus());
        }
        String json = response.readEntity(String.class);
        // Parse thành DTO bằng JSON provider/mapper đã được kiểm chứng.
    }
}
~~~

`token` và `PartnerApiException` là giá trị/class giả định. Với runtime tương thích, `Client`, `WebTarget` và `Invocation.Builder` giúp xây request; đối với API production phải cấu hình **connect/read timeout**, connection pooling, TLS, retry có giới hạn và policy idempotency. Không truyền token thật vào log hoặc URL. Dùng `ClientBuilder.newClient()` mỗi request là lãng phí: ở production nên có client có vòng đời quản lý và đóng khi ứng dụng dừng.

**Không nhầm client với server:** `ClientBuilder` gọi một dịch vụ HTTP; nó không làm các resource `@Path` của ứng dụng tự được publish. Nếu một thư viện không có client provider/runtime tương ứng, chỉ thêm `jakarta.ws.rs-api` có thể không đủ để xây client chạy được.

## 10. Kiểm thử Jakarta REST theo hợp đồng HTTP

Không dùng `MockMvc` mặc định để khẳng định đã kiểm tra endpoint Jersey: `MockMvc` kiểm tra pipeline của **Spring MVC**, trong khi `@Path` của Jersey đi qua **Servlet/Filter và runtime khác**. Có thể dùng `JerseyTest` khi kiểm thử resource độc lập, hoặc chạy server thật với Java `HttpClient`, REST Assured hay một HTTP client test phù hợp. Điều quan trọng là **test đường request mà production thực sự sử dụng**.

### 10.1. Integration test Spring Boot + Jersey qua HTTP thật

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class JerseyHttpContractIT {
    @LocalServerPort int port;

    @Test
    void getVisibleOrderReturnsJson() throws Exception {
        // Fixture phải tạo order o-42 cho principal có quyền đọc.
        String url = "http://localhost:" + port + "/api/orders/o-42";
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
            .header("Accept", "application/json")
            .GET()
            .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.headers()
            .firstValue("Content-Type").orElse("")
            .contains("application/json"));
        assertTrue(response.body().contains("\"id\":\"o-42\""));
    }
}
~~~

Đây là **khung tích hợp**: cần JUnit 5 imports, `@LocalServerPort`, entity/JSON provider, fixture và auth hợp lệ cho môi trường test. Nếu API bắt buộc bearer token, thêm **test token do test issuer phát hành** hoặc cấu hình auth backend sandbox; không vô hiệu hóa phân quyền để cho test “xanh”. Với body JSON có cấu trúc, nên parse bằng Jackson/JSON-B rồi assert field thay vì chỉ `contains`; đoạn trên minh họa việc client gọi đúng URI/network.

### 10.2. Ma trận nên có

| Ca | Yêu cầu/tình huống | Kỳ vọng |
|---|---|---|
| J01 | GET order đã tạo, caller hợp lệ | **200**, JSON, đúng ID |
| J02 | GET order không có hoặc ngoài tenant | **404**, không tiết lộ trạng thái |
| J03 | POST JSON tạo order | **201**, `Location` hợp lệ |
| J04 | POST thiếu field, JSON hỏng | Lỗi hợp đồng, không tạo order |
| J05 | POST Content-Type khác `@Consumes` | **415** nếu không có reader/route phù hợp |
| J06 | GET `Accept` không tương thích `@Produces` | **406** khi không có representation phù hợp |
| J07 | GET collection với query invalid | Lỗi chuẩn hóa theo API, không thành 500 |
| J08 | Domain conflict | **409** Problem Details từ `ExceptionMapper` |
| J09 | Thiếu token hoặc thiếu quyền | **401/403** qua runtime/security thật |
| J10 | POST retry cùng idempotency key | Không tạo hai side effect |
| J11 | PATCH stale `If-Match` | **412**, DB không thay đổi |
| J12 | Header `X-Request-Id` độc hại | Không phản chiếu CRLF, không log bí mật |

Kiểm thử code phía resource và tầng thực thi **khác với test domain service**. Với transaction và concurrency, chạy hai request đồng thời trên database tương tự production; assert bản ghi, version và side effect. Với security, test cả route mà **người gọi không biết** và route mà **người gọi biết nhưng không được sửa**.

## 11. Bài tập: nhận diện, chọn API và nâng cấp

**Bài tập A — Nhận diện tên.** Một service đang có `import javax.ws.rs.Path;`, chạy trên Java EE server; tài liệu hướng dẫn cài Jersey. Người mới gọi tất cả là “Jersey API”. Hãy phân biệt công nghệ và lựa chọn nâng sang Jakarta EE 10.

**Đáp án:** `javax.ws.rs` là namespace JAX-RS cũ; **Jersey** là implementation. Khi nâng Jakarta EE 10, chọn Jakarta REST **3.1** với `jakarta.ws.rs.*` và implementation tương thích; cập nhật các module/providers, dependencies, server và test. Không thay `javax.` bằng `jakarta.` ở một class rồi giữ runtime cũ.

**Bài tập B — Mapping HTTP.** Viết resource xử lý `GET /api/products/p-17?includeStock=true` và `POST /api/products` với JSON. Chọn annotation và status.

**Đáp án:** resource có `@Path("/products")` dưới base path `/api`; GET item dùng `@GET @Path("/{id}")`, `@PathParam("id")` và `@QueryParam("includeStock")`; POST dùng `@POST @Consumes(APPLICATION_JSON)`, body DTO, trả **201 + Location** nếu tạo resource. `@Produces(APPLICATION_JSON)` mô tả representation JSON trả ra. Phải check quyền, giới hạn stock visibility và validation.

**Bài tập C — Migration framework.** Một dự án Spring Boot chỉ có `spring-boot-starter-web`, lập trình viên thêm `jakarta.ws.rs-api` rồi viết `@Path("/orders")`, nhưng URL vẫn 404. Vì sao?

**Đáp án:** chỉ có **API interfaces/annotations** không đủ; Spring MVC không tự nhận JAX-RS resource. Chọn **Spring MVC `@RestController`** hoặc thêm **Jersey runtime/starter + `ResourceConfig`** phù hợp, đăng ký resource và cấu hình URL.

**Bài tập D — Bảo mật.** Resource nhận `@PathParam("tenantId") String tenantId` và `@RolesAllowed("user")`. Như vậy đã ngăn user tenant A đọc order tenant B chưa?

**Đáp án:** **chưa**. Role `user` chỉ mô tả quyền rộng và phải được security runtime thực thi. Service cần lấy tenant thực từ principal đáng tin và truy vấn **trong scope đã xác thực**, kết hợp owner/ACL; test hai tenant và chính sách 404/403.

## 12. Checklist và nguồn chuẩn

- [ ] Biết **Jakarta REST là tên đặc tả hiện nay**, JAX-RS là tên lịch sử vẫn còn dùng.
- [ ] Phân biệt **spec API** với **implementation Jersey/RESTEasy/CXF** và **server/container**.
- [ ] Chọn đúng namespace `javax.ws.rs` hay `jakarta.ws.rs` theo phiên bản deployment.
- [ ] Có runtime/JSON provider tương thích; không chỉ thêm API JAR.
- [ ] Resource có URI/method, `@Consumes`/`@Produces` và response status/Location đúng.
- [ ] Dùng `ExceptionMapper`, filter và validation cho đúng mục đích; không lộ nội bộ.
- [ ] Authorization thực thi ở runtime **và** service/resource scope; có test cross-tenant.
- [ ] Đã chọn rõ **Spring MVC hay Jersey** trong Spring Boot; không đăng ký trùng route.
- [ ] Test qua HTTP thật, bao gồm 201/404/409/415/406, auth, idempotency và concurrency.
- [ ] Hợp đồng OpenAPI mô tả request/response/error/security; không mặc định JAX-RS sinh sẵn.

**Nguồn chính thức:** [Danh mục Jakarta REST](https://jakarta.ee/specifications/restful-ws/), [Jakarta REST 3.0 specification](https://jakarta.ee/specifications/restful-ws/3.0/jakarta-restful-ws-spec-3.0.html), [Jakarta REST 3.1](https://jakarta.ee/specifications/restful-ws/3.1/), [Jakarta REST 4.0 API](https://jakarta.ee/specifications/restful-ws/4.0/apidocs/), [Spring Boot 3.5 — JAX-RS and Jersey](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html), [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457).

**Kết luận:** **JAX-RS** và **Jakarta RESTful Web Services** là tên lịch sử/hiện đại của cùng dòng **đặc tả REST API cho Java**. Namespace chuyển từ `javax.ws.rs` sang `jakarta.ws.rs` là ranh giới nâng cấp quan trọng; còn Jersey, RESTEasy và CXF là các implementation thực thi đặc tả. Chọn runtime đúng, mô hình hóa HTTP rõ ràng, kiểm quyền theo resource và test **trên đường HTTP thực** để xây REST API đáng tin cậy.
