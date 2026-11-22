# Response, UriInfo và xây dựng phản hồi có metadata

Client gửi **POST /v1/orders** và server tạo **o-918**. Nếu chỉ trả ID, client phải đoán URI; nếu thiếu metadata, client không biết cache, phân trang hay cập nhật đúng cách. Trong **Jakarta REST** (JAX-RS), **Response**, **UriInfo** và **UriBuilder** giúp diễn đạt hợp đồng HTTP.

Bài thuộc chương **Jakarta REST**, module **INTEGRATION_API_REST**, kết hợp URI, status, cache, idempotency, bảo mật và kiểm thử. **Metadata phải đúng ngữ nghĩa và an toàn theo người gọi**.

## 1. Mục tiêu và bản đồ trách nhiệm

Sau bài này, bạn có thể:

1. Dùng **Response.ResponseBuilder** để trả status, entity, Location, Link, media type và cache metadata.
2. Dùng **@Context UriInfo** cùng **UriBuilder** để dựng đường dẫn chi tiết, URI collection và link phân trang mà không nối chuỗi tùy tiện.
3. Phân biệt **Location, Content-Location, Link, ETag, Last-Modified, Cache-Control, Vary** và vị trí phù hợp của chúng.
4. Thiết kế các luồng **POST → 201 → GET**, **202 → job status**, **GET điều kiện → 304** và phản hồi lỗi có cấu trúc.
5. Bảo vệ URI public trước Host/Forwarded header giả mạo, dữ liệu multi-tenant và việc cache sai quyền.
6. So sánh khái niệm Jakarta REST với **Spring MVC ResponseEntity/UriComponentsBuilder** và kiểm thử hợp đồng HTTP qua runtime thực.

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Jakarta REST resource"]
    B --> C["Service: authz + business"]
    C --> D["Dữ liệu/kết quả"]
    B --> U["UriInfo / UriBuilder"]
    D --> R["Response builder"]
    U --> R
    R --> H["HTTP status + headers + entity"]
~~~

**Resource method** quyết định HTTP; **service** bảo vệ nghiệp vụ/quyền; **UriInfo** tạo URI; **Response** gói kết quả. URI đúng cú pháp **không chứng minh quyền**.

## 2. Response và ResponseBuilder: mô hình phản hồi HTTP

**jakarta.ws.rs.core.Response** biểu diễn status, headers và entity. **ok**, **created**, **accepted**, **noContent**, **status**, **seeOther** trả builder để cấu hình trước **build()**.

~~~java
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

Response response = Response.status(Response.Status.OK)
        .type(MediaType.APPLICATION_JSON_TYPE)
        .entity(new Message("ready"))
        .header("X-Request-Id", "req-42")
        .build();

record Message(String state) {}
~~~

Sau **build()**, runtime dùng **MessageBodyWriter/media type/provider** để serialize entity. **Response không tự tạo JSON** nếu thiếu provider.

### 2.1. Các builder thường dùng

| Mục tiêu | Jakarta REST | HTTP mong đợi |
|---|---|---|
| Đọc tài nguyên | **Response.ok(dto).build()** | 200 + entity |
| Tạo tài nguyên | **Response.created(uri).entity(dto).build()** | 201 + Location |
| Nhận job bất đồng bộ | **Response.accepted(job).location(jobUri).build()** | 202 + Location theo contract |
| Cập nhật/xóa thành công không trả body | **Response.noContent().build()** | 204, không có content |
| Lỗi domain có body | **Response.status(409).entity(problem).type(...).build()** | 409 + Problem Details |
| Chuyển hướng xem kết quả | **Response.seeOther(uri).build()** | 303 + Location |

**202** chỉ xác nhận đã nhận xử lý; **201** khi resource được tạo; **204** không body. POST cũng có thể trả **200** khi xử lý đồng bộ.

### 2.2. Các thuộc tính builder quan trọng

~~~java
import jakarta.ws.rs.core.CacheControl;
import jakarta.ws.rs.core.EntityTag;
import jakarta.ws.rs.core.Link;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import java.net.URI;
import java.util.Locale;

CacheControl cache = new CacheControl();
cache.setPrivate(true);
cache.setNoStore(true);

Response response = Response.ok(new Message("ready"))
        .type(MediaType.APPLICATION_JSON_TYPE)
        .language(Locale.forLanguageTag("vi"))
        .tag(new EntityTag("state-v3"))
        .cacheControl(cache)
        .link(URI.create("/v1/status/123"), "self")
        .build();
~~~

**tag** tạo ETag, **language** tạo Content-Language, **link** tạo Link. Các giá trị phải đúng representation và cache policy.

Một response có metadata nhìn “đẹp” nhưng **trỏ tới tenant khác** là lỗi bảo mật nghiêm trọng hơn response thiếu Link.

## 3. Location: URI của tài nguyên mới và đích redirect

### 3.1. POST tạo resource với 201

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{"cartId":"cart-73"}
~~~

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/orders/o-918
Content-Type: application/json
Cache-Control: no-store

{"id":"o-918","status":"PENDING"}
~~~

**Location** là URI-reference của tài nguyên chính được tạo. Theo **RFC 9110**, Location không bắt buộc ở dạng absolute URI; response cũng có thể dùng **/v1/orders/o-918** nếu client giải quyết URI tương đối theo chuẩn. Nhưng khi tích hợp bên ngoài đòi URL đầy đủ, server phải sinh **public origin hợp lệ**, không dùng host nội bộ.

**Location** và ID trong body phải khớp; GET lại URI vẫn cần authentication. Không trỏ Location tới collection khi đã tạo resource chi tiết.

### 3.2. 202: metadata để theo dõi job

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/j-88
Retry-After: 5
Content-Type: application/json

{"jobId":"j-88","status":"QUEUED"}
~~~

Location của **202** tới job là **quy ước API**, không bắt buộc. Retry-After hướng dẫn polling; POST timeout cần idempotency/đối soát.

### 3.3. Redirect không thay schema migration

**Response.seeOther(uri)** tạo **303 See Other**, thường dẫn client sang URI GET để xem kết quả một POST. **307/308** giữ method khi chuyển hướng theo semantics HTTP, nhưng không sửa body JSON, auth scope hoặc idempotency giúp client. Nếu v2 API thay đổi hợp đồng, **không redirect mù POST v1 sang v2**.

### 3.4. Location khác Content-Location

| Header | Vai trò |
|---|---|
| **Location** | Chỉ resource tạo mới/đích redirect theo status |
| **Content-Location** | URI tương ứng với representation nằm trong response |
| **Link** | Chỉ quan hệ như self, collection, next hoặc tài liệu |

**Content-Location không thay Location cho 201**. Một HTTP 200 có Content-Location không có nghĩa browser sẽ redirect. Khi trả self link, dùng quan hệ rõ nghĩa thay vì thêm Location vào mọi 200.

## 4. UriInfo: nguồn thông tin URI của request

Jakarta REST cung cấp **@Context UriInfo** để truy vấn **base URI**, path, request URI và URI builder tương ứng. Không cần ghép scheme, Host, context path, query string thủ công.

| API UriInfo | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| **getBaseUri() / getBaseUriBuilder()** | URI gốc của ứng dụng REST | Dựng URI của một resource khác |
| **getAbsolutePath() / getAbsolutePathBuilder()** | URI hiện tại **không gồm query string** | Thêm ID vào URI collection sau POST |
| **getRequestUri() / getRequestUriBuilder()** | URI hiện tại **gồm query string** | Tạo link next/prev giữ filter |
| **getPathParameters()** | Tham số URI path đã khớp template | Xem tham số routing |
| **getQueryParameters()** | Query parameter, có thể nhiều giá trị | Đọc cursor/filter theo policy |
| **getMatchedURIs()** | Các đường dẫn khớp theo chain của runtime | Diagnostic, không phải nguồn canonical ID |

Với **POST /v1/orders?dryRun=false**, dùng **getAbsolutePathBuilder()** thay vì **getRequestUriBuilder()** để tránh mang **?dryRun=false** vào URI đơn mới. Nếu tạo link next cho collection, có thể bắt đầu từ request URI, nhưng phải **loại bỏ query không được cho phép**, nhất là access token hoặc dữ liệu nhạy cảm.

### 4.1. URI template và encoding

~~~java
import jakarta.ws.rs.core.UriBuilder;
import java.net.URI;

URI detail = UriBuilder
        .fromUri("https://api.example.test")
        .path("v1")
        .path("orders")
        .path("{id}")
        .build("o-918");

URI collection = UriBuilder.fromPath("/v1/orders")
        .queryParam("status", "{status}")
        .queryParam("limit", 20)
        .build("PENDING");
~~~

**build** mở rộng template và encode theo ngữ cảnh component. Nếu ID có **/, ?, #, %, khoảng trắng hoặc Unicode**, phải hiểu quy tắc encoding của UriBuilder/implementation; **đường slash trong một biến path** có thể cần **resolveTemplate(name, value, true)** để được encode như dữ liệu, không thành delimiter. Không encode giá trị trước rồi để builder encode lần nữa nếu không chủ ý: **double encoding** sẽ làm URI sai.

Đối với ID từ server, ưu tiên **UUID/opaque ID URL-safe**. Dù builder có thể encode một slash thành **%2F**, gateway/servlet container có thể từ chối hoặc giải mã trước khi route, nên không giả định mọi encoded slash sẽ đi hết pipeline.

### 4.2. Dựng URI theo mapping của resource

Khi resource class có **@Path("/v1/orders")** và method có **@Path("/{id}")**, có thể dùng **UriBuilder.path(Class)** và **path(Class, methodName)** để lấy path annotation, tránh lặp hardcode đường dẫn ở nhiều nơi:

~~~java
URI detailUri = uriInfo.getBaseUriBuilder()
        .path(OrderResource.class)
        .path(OrderResource.class, "findById")
        .build("o-918");
~~~

Chỉ dùng cách này khi method mapping đúng tên và có path annotation phù hợp. Link mới vẫn thuộc **public API contract**: đổi @Path có thể phá client cũ đã lưu URI dù Java compile thành công.

## 5. Ví dụ Jakarta REST: tạo đơn, trả Location và Link

Thiết kế sau minh họa Jakarta REST với **jakarta.ws.rs**, **Jakarta Validation** và service riêng. Runtime có thể là Jersey, RESTEasy, Apache CXF hoặc implementation tương thích; cách bật JSON provider, CDI/security và dependency sẽ khác nhau theo môi trường triển khai. Không ghép annotation **@RestController** của Spring MVC vào cùng class rồi mặc định chúng hoạt động tương đương.

### 5.1. DTO, service contract và actor

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;

record CreateOrderRequest(
        @NotBlank String cartId,
        @Size(max = 200) String note) {}

record OrderView(
        String id, String status,
        long totalMinor, String currency) {}

record Actor(UUID tenantId, UUID userId) {}

interface ActorResolver {
    // Principal/tenant phải đến từ identity đã xác thực.
    Actor resolve(jakarta.ws.rs.core.SecurityContext context);
}

interface OrderService {
    // Commit/unique constraint/authorization thuộc service.
    OrderView create(Actor actor, CreateOrderRequest request);
    OrderView findVisible(Actor actor, String id);
}
~~~

**@NotBlank/@Size** kiểm tra cấu trúc, không bảo đảm cart tồn tại hoặc thuộc principal. **OrderService** phải kiểm tra quyền, trạng thái cart, idempotency nếu POST có thể retry và transaction ở tầng lưu trữ. ActorResolver cần kiểm chứng cách ánh xạ danh tính của môi trường thật; không lấy tenant từ body do client tự khai.

### 5.2. Resource với UriInfo và Response

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
    @Inject OrderService service;
    @Inject ActorResolver actors;

    @Context UriInfo uriInfo;
    @Context SecurityContext security;

    @POST
    public Response create(@Valid CreateOrderRequest input) {
        Actor actor = actors.resolve(security);
        OrderView created = service.create(actor, input);
        URI location = uriInfo.getBaseUriBuilder()
                .path(OrderResource.class)
                .path(OrderResource.class, "findById")
                .build(created.id());

        return Response.created(location)
                .entity(created)
                .type(MediaType.APPLICATION_JSON_TYPE)
                .link(location, "self")
                .link(uriInfo.getAbsolutePath(), "collection")
                .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
                .build();
    }

    @GET
    @Path("/{id}")
    public Response findById(@PathParam("id") String id) {
        Actor actor = actors.resolve(security);
        OrderView order = service.findVisible(actor, id);
        URI self = uriInfo.getAbsolutePath();
        URI collection = uriInfo.getBaseUriBuilder()
                .path(OrderResource.class)
                .build();

        return Response.ok(order)
                .link(self, "self")
                .link(collection, "collection")
                .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
                .build();
    }
}
~~~

**Luồng xử lý:** service commit order thành công → Jakarta REST dựng URI theo annotation mapping → **Response.created(location)** đặt 201 + Location → body là representation. GET truy cập resource riêng phải **tiếp tục kiểm tra actor/tenant**: việc biết URI không tự cấp quyền.

Hai chi tiết cần để ý:

- **UriInfo trong POST** có absolute path tới collection. **getBaseUriBuilder().path(resource).path(method)** hữu ích khi ID không đến từ current request path; tránh nhầm query của POST vào URI mới.
- Runtime phải có JSON provider để serialize record. Nếu triển khai trên phiên bản/framework không hỗ trợ Java record đầy đủ, dùng DTO dạng class/bean hoặc cấu hình JSON tương thích; phần HTTP semantics vẫn giữ nguyên.

**Transaction** thuộc service, không thuộc ResponseBuilder. Không phát **201** nếu chỉ ghi job vào queue mà order resource chưa được tạo như contract. Khi request lặp sau timeout, **Response** không ngăn tạo hai order: cần Idempotency-Key, unique operation constraint hoặc đối soát từ domain.

## 6. Link metadata và phân trang từ UriInfo

**HTTP Link** theo RFC 8288 truyền các quan hệ như **self**, **next**, **prev**, **collection**, **related**. Client đi theo relation thay vì cố đoán URI từ cấu trúc Java. Trong Jakarta REST, có thể tạo Link qua **ResponseBuilder.link** hoặc đối tượng **jakarta.ws.rs.core.Link**.

~~~java
import jakarta.ws.rs.core.Link;
import jakarta.ws.rs.core.Response;
import java.net.URI;

Link self = Link.fromUri(URI.create("/v1/orders/o-918"))
        .rel("self").build();
Link collection = Link.fromUri(URI.create("/v1/orders"))
        .rel("collection").build();

Response response = Response.ok(order)
        .links(self, collection)
        .build();
~~~

Runtime phát các giá trị **Link** dưới dạng header hợp lệ. **Link không phải Authorization**: ẩn link “cancel” không ngăn client gửi DELETE thủ công. Quyền phải được kiểm tra ở route thực thi.

### 6.1. Link next khi phân trang bằng cursor

Giả sử collection:

~~~http
GET /v1/orders?status=PENDING&limit=20&cursor=eyJwYWdlIjoxfQ HTTP/1.1
Authorization: Bearer <access-token>
~~~

Server trả một tập giới hạn và cursor tiếp theo do service tạo:

~~~java
@GET
public Response list(
        @QueryParam("status") String status,
        @DefaultValue("20") @QueryParam("limit") int limit,
        @QueryParam("cursor") String cursor) {

    Actor actor = actors.resolve(security);
    Page<OrderView> page = service.findPage(actor, status, limit, cursor);

    UriBuilder nextBuilder = uriInfo.getAbsolutePathBuilder()
            .queryParam("status", status)
            .queryParam("limit", limit)
            .queryParam("cursor", "{nextCursor}");

    Response.ResponseBuilder out = Response.ok(page.items())
            .header("Cache-Control", "private, no-store");

    if (page.nextCursor() != null) {
        out.link(nextBuilder.build(page.nextCursor()), "next");
    }
    return out.build();
}
~~~

Đây là **đoạn mở rộng OrderResource**, chưa phải class Java hoàn chỉnh: giả định **Page** và service pagination được định nghĩa. Thực tế cần **validate status/limit/cursor**, giới hạn max page size và chỉ thêm query parameter có ý nghĩa. Nếu status có thể null, chỉ thêm khi được truyền; không để một null tạo query parameter khó hiểu. Cursor phải là **opaque và được bảo vệ tính toàn vẹn/tenant/filter** theo contract, không cho user sửa cursor để xem dữ liệu tenant khác.

**Không chuyển tiếp toàn bộ query từ request một cách mù quáng**: query có thể chứa access token, ký tự bất thường hoặc tham số không được hỗ trợ. Nếu dùng **getRequestUriBuilder()**, hãy lọc/replace các key được công bố thay vì nhân bản mọi key. Link next có thể là URI tương đối hoặc tuyệt đối tùy hợp đồng và public origin.

## 7. Cache metadata: ETag, Last-Modified và yêu cầu điều kiện

**ETag** định danh phiên bản của representation; **Last-Modified** mô tả thời điểm sửa gần nhất; **Cache-Control** đặt chính sách lưu cache. Những metadata này chỉ có ích khi chúng thực sự bám theo dữ liệu và quyền truy cập.

| Metadata | Ví dụ | Câu hỏi giải đáp |
|---|---|---|
| **ETag** | ETag: "product-v7" | Representation đã thay đổi chưa? |
| **Last-Modified** | Last-Modified: Wed, 18 Nov 2026 08:00:00 GMT | Lần sửa cuối của representation? |
| **Cache-Control** | private, max-age=60 | Ai được lưu và trong bao lâu? |
| **Vary** | Accept-Language | Header request nào ảnh hưởng representation? |
| **Content-Language** | vi | Nội dung dùng ngôn ngữ nào? |
| **Content-Location** | /v1/products/p-17?lang=vi | Representation này gắn với URI nào? |

**ETag là validator của representation**, không chỉ là version của một hàng DB. Strong/weak ETag có quy tắc khác nhau; **If-Match** dùng strong comparison. ETag sai thiết kế không bảo vệ được cập nhật cạnh tranh.

### 7.1. GET với If-None-Match và 304

Để minh họa caching, dùng tài nguyên **catalog công khai**, không phải đơn hàng cá nhân. Jakarta REST có **@Context Request**, cho phép gọi **evaluatePreconditions** với validator hiện tại:

~~~java
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.*;

@Path("/v1/catalog/{id}")
public class CatalogResource {
    @Context Request request;

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response get(@PathParam("id") String id) {
        CatalogItem item = catalogService.findPublicItem(id);
        EntityTag etag = new EntityTag(item.representationVersion());

        CacheControl policy = new CacheControl();
        policy.setMaxAge(60);

        Response.ResponseBuilder conditional =
                request.evaluatePreconditions(etag);
        if (conditional != null) {
            // Runtime áp dụng precondition theo HTTP semantics.
            return conditional.tag(etag).cacheControl(policy).build();
        }

        return Response.ok(item)
                .tag(etag)
                .cacheControl(policy)
                .build();
    }
}
~~~

Mẫu code giả định **CatalogItem** và **catalogService** đã có. Với GET và **If-None-Match** phù hợp, kết quả thường là **304 Not Modified**, **không có body**. Nếu client gửi điều kiện khác, kết quả có thể khác theo RFC 9110. Đừng tự viết một nhánh 304 với JSON body. ETag phải xét **biến thể ngôn ngữ, media type, encoding và nội dung thực tế**.

~~~http
GET /v1/catalog/p-17 HTTP/1.1
If-None-Match: "product-v7"
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-v7"
Cache-Control: max-age=60
~~~

Nếu representation thay đổi thành v8, server trả **200 + body + ETag mới**. Với tài nguyên riêng theo user/tenant, cân nhắc **private/no-store** và chính sách Vary/authorization cụ thể, không dùng cache public chỉ vì có ETag.

### 7.2. Last-Modified và độ chính xác

Có thể thêm **ResponseBuilder.lastModified(Date)** và dùng **Request.evaluatePreconditions(Date)** hoặc overload nhận cả EntityTag và Date. HTTP-date có độ chính xác **giây**; nếu dữ liệu thay đổi nhiều lần mỗi giây, timestamp không đủ cho kiểm soát cạnh tranh. Với PUT/DELETE yêu cầu điều kiện chính xác, thường chọn strong ETag/If-Match cùng version check nguyên tử ở DB.

**Vary** theo các header tạo variant như **Accept-Language/Accept-Encoding**, không thay kiểm tra quyền. Kiểm thử **304** cả qua CDN/gateway.

## 8. Lỗi HTTP: Response.status, WebApplicationException và ExceptionMapper

**Response.status(...).entity(...).build()** đủ để tạo phản hồi lỗi, nhưng xử lý lặp lại trong mọi resource method làm hợp đồng thiếu nhất quán. **Jakarta REST ExceptionMapper** cho phép chuyển exception nghiệp vụ thành HTTP response có cấu trúc, ví dụ **Problem Details (RFC 9457)**.

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/cart-conflict",
  "title": "Cart is no longer open",
  "status": 409,
  "detail": "Refresh the cart before placing an order.",
  "code": "CART_CHANGED"
}
~~~

**code** là extension của ứng dụng; không phải trường bắt buộc của RFC 9457. Không trả raw exception message chứa SQL/stack trace/chi tiết nội bộ. Một mapper minh họa:

~~~java
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import java.net.URI;
import java.util.Map;

class CartConflictException extends RuntimeException {}

@Provider
public class CartConflictMapper
        implements ExceptionMapper<CartConflictException> {

    @Override
    public Response toResponse(CartConflictException ex) {
        Map<String, Object> problem = Map.of(
                "type", "https://api.example.test/problems/cart-conflict",
                "title", "Cart is no longer open",
                "status", 409,
                "detail", "Refresh the cart before placing an order.",
                "code", "CART_CHANGED");

        return Response.status(Response.Status.CONFLICT)
                .type("application/problem+json")
                .header("Cache-Control", "no-store")
                .entity(problem)
                .build();
    }
}
~~~

Mapper cần được runtime **đăng ký/quét provider** và có JSON serializer phù hợp. Không tạo mapper tổng quát biến mọi RuntimeException thành 400/409; lỗi lập trình hoặc database outage không phải lỗi nhập liệu.

| Tình huống | HTTP status thường phù hợp | Ghi chú |
|---|---|---|
| JSON/body sai hoặc validation không đạt | **400**; có trường hợp domain chọn **422** | Phân biệt sai cấu trúc và không xử lý được semantics |
| Chưa xác thực phù hợp | **401** | Có challenge WWW-Authenticate khi áp dụng |
| Đã xác thực nhưng không có quyền | **403**, hoặc **404** khi cần che resource | Không lộ owner/tenant |
| Resource ngoài scope/không tồn tại | **404** | Kiểm tra theo scope trước khi trả dữ liệu |
| Giỏ đã đóng, trạng thái xung đột | **409** | Client đọc lại resource |
| If-Match không khớp | **412** | Không tự bỏ precondition rồi ghi đè |
| Dependency tạm lỗi | **503** hoặc **502/504** theo hop | Không đánh đồng với 404 |
| Lỗi server bất ngờ | **500** | Log có trace ID, body không chứa nội bộ |

**WebApplicationException** có thể mang một Response/status sẵn, nhưng vẫn cần chính sách mapping chuẩn. Bean Validation có integration theo runtime và có thể dùng status khác theo ngữ cảnh (ví dụ validation tham số request và return value); hãy kiểm tra contract thực tế, không giả định mọi validation luôn 400. **Security filter/container** có thể trả 401/403 trước khi method resource chạy; ExceptionMapper không nhất thiết nhìn thấy tất cả lỗi tại mọi tầng.

## 9. Bảo mật và tính nhất quán metadata

URI và metadata cũng là **bề mặt tấn công**, không phải trường vô hại:

- **Host/Forwarded spoofing:** nếu proxy cho client tùy ý đặt Host, Forwarded hoặc X-Forwarded-Host, Location và Link absolute có thể trỏ tới domain attacker. Chỉ tin proxy đã xác thực/strip header, hoặc dùng public base URL allowlist.
- **BOLA/IDOR:** GET theo Location hoặc Link vẫn phải kiểm tra owner/tenant. UUID khó đoán không phải authorization. Không sinh link sang tài nguyên người dùng khác.
- **Cache rò dữ liệu:** đơn hàng cá nhân dùng **private/no-store** theo chính sách. Không dùng cache public cho response chứa dữ liệu riêng; một Vary đơn lẻ không thay kiểm tra quyền.
- **URI chứa bí mật:** không đưa JWT, API key, email, signed download URL dài hạn hoặc query nhạy cảm vào Location/Link; URI dễ lọt vào log, analytics, browser history.
- **CORS:** browser cần được phép đọc **Location, Link, ETag** qua **Access-Control-Expose-Headers** nếu frontend khác origin dùng chúng. CORS không thay xác thực/quyền; phải giới hạn origin/credentials đúng chính sách.
- **Content negotiation:** nếu JSON thay đổi theo **Accept, Accept-Language** hoặc identity, ETag, Vary và Content-Language phải tương ứng representation thực tế. Không phát cùng strong ETag cho hai byte representation khác nhau.

**Trường hợp proxy phức tạp:** kiểm thử cả request trực tiếp đến backend và request đi qua ingress/CDN thật. Một GET qua public HTTPS không được sinh Link dùng internal-service:8080 hoặc HTTP không mã hóa. Nếu dùng link self trên resource lỗi, đừng để thông báo 404 tiết lộ đường dẫn riêng của tenant khác.

## 10. Đối chiếu nhanh với Spring MVC

**Jakarta REST** và **Spring MVC** có các khái niệm tương đương ở lớp HTTP nhưng annotation/runtime không hoán đổi trực tiếp.

| Việc cần làm | Jakarta REST | Spring MVC |
|---|---|---|
| Khai báo route | **@Path, @GET, @POST** | **@RequestMapping, @GetMapping, @PostMapping** |
| Tham số path | **@PathParam** | **@PathVariable** |
| Request URI | **@Context UriInfo** | **ServletUriComponentsBuilder** |
| Dựng URI | **UriBuilder** | **UriComponentsBuilder** |
| Kết quả HTTP | **Response/ResponseBuilder** | **ResponseEntity** |
| Ánh xạ ngoại lệ | **ExceptionMapper** | **@RestControllerAdvice** |
| Conditional GET | **Request.evaluatePreconditions** | **ETag/ResponseEntity, WebRequest hoặc cơ chế MVC phù hợp** |

Ví dụ tương đương ý tưởng 201 + Location trong Spring MVC:

~~~java
@PostMapping("/v1/orders")
ResponseEntity<OrderView> create(@Valid @RequestBody CreateOrderRequest dto) {
    OrderView order = service.createForCurrentUser(dto);
    URI uri = ServletUriComponentsBuilder.fromCurrentRequestUri()
            .path("/{id}")
            .buildAndExpand(order.id())
            .toUri();
    return ResponseEntity.created(uri).body(order);
}
~~~

Đoạn Spring chỉ minh họa, cần import, service, security và transaction implementation. **@Context UriInfo không phải Spring Servlet request**, và **ResponseEntity không tự hoạt động như Jakarta REST Response** nếu runtime chỉ bật Jersey/RESTEasy; hãy chọn stack rõ ràng, không ghép annotation tùy tiện.

## 11. Kiểm thử HTTP và bài tập

Đừng chỉ unit-test builder: phải kiểm chứng response **qua runtime Jakarta REST và proxy**. Ma trận tối thiểu:

| Tình huống | Bằng chứng mong đợi |
|---|---|
| POST thành công | **201 + Location** dẫn tới GET đúng order, body ID khớp |
| POST retry sau timeout | Idempotency không tạo hai order |
| Context path hoặc gateway HTTPS | URI absolute dùng đúng public origin/prefix |
| Host/Forwarded giả mạo | Không tạo Location/Link tới miền attacker |
| GET của tenant khác | 403/404 theo policy, không rò entity/link |
| Cursor chứa ký tự reserved | Link next vẫn giữ filter và encode đúng |
| GET có If-None-Match khớp | **304 không body**, ETag và cache metadata hợp lệ |
| Đổi representation | 200 + ETag mới, không trả 304 sai |
| Resource riêng qua shared cache | Không lộ dữ liệu giữa user/tenant |
| Validation, conflict, DB lỗi | Problem Details an toàn với status phù hợp |

Trong integration test với một runtime như **JerseyTest/RESTEasy test harness**, assert status, Location, Link và GET lại URI; dùng mock/fake service chỉ cho HTTP contract, dùng DB thật cho isolation/concurrency. Có thể unit-test **UriBuilder** riêng:

~~~java
URI uri = UriBuilder.fromPath("/v1/orders/{id}").build("o-918");
assertEquals("/v1/orders/o-918", uri.toString());
~~~

Test này không chứng minh policy Host/Forwarded; tình huống đó phải chạy qua proxy tin cậy và gửi thử header bị giả mạo.

### Bài tập: API tài liệu có cache và quyền

Một dịch vụ nhận **POST /v1/documents** và tạo **doc-73**. GET trả tài liệu cá nhân có **self/collection**; GET collection dùng **cursor**; tài liệu công khai có **ETag**. Dịch vụ đứng sau proxy với prefix **/gateway/api**.

Hãy thiết kế: **(1)** Response 201 + Location; **(2)** cách lấy base URI và đường dẫn từ UriInfo; **(3)** Link next giữ filter; **(4)** metadata riêng tư so với công khai; **(5)** xử lý 304; **(6)** tối thiểu năm ca test bảo mật/URI/cache.

**Gợi ý:** dùng **getBaseUriBuilder().path(resource).path(method)** hoặc **getAbsolutePathBuilder()** đúng ngữ cảnh; không ghép URI bằng Host. Với tài liệu cá nhân đặt **private/no-store**, kiểm tra owner tại GET. Catalog công khai có thể dùng ETag + Cache-Control thích hợp; 304 không có body. Link next mang cursor đã kiểm chứng, không chứa access token.

## 12. Checklist và tham khảo

- [ ] **ResponseBuilder** trả đúng status/entity, không có body ở 204/304.
- [ ] **201 + Location** trỏ resource thật; 202 + job Location có contract riêng.
- [ ] **UriInfo/UriBuilder** dùng đúng base, path, query và encoding.
- [ ] **Link** có relation rõ nghĩa, không thay authorization.
- [ ] **ETag/Last-Modified/Vary/Cache-Control** khớp representation và quyền.
- [ ] Proxy/public origin, CORS, cross-tenant và cache được test end-to-end.
- [ ] **ExceptionMapper** không rò nội bộ; lỗi HTTP/Problem Details nhất quán.

Tham khảo: **Jakarta RESTful Web Services**, https://jakarta.ee/specifications/restful-ws/; **Jakarta REST API**, https://jakarta.ee/specifications/restful-ws/3.1/apidocs/; **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9111 HTTP Caching**, https://www.rfc-editor.org/rfc/rfc9111.html; **RFC 8288 Web Linking**, https://www.rfc-editor.org/rfc/rfc8288.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **Spring MVC**, https://docs.spring.io/spring-framework/reference/web/webmvc.html.

**Kết luận:** **Response** xác định status, entity và metadata; **UriInfo/UriBuilder** giúp tạo URI của tài nguyên và liên kết đúng ngữ cảnh. REST API tốt phải bảo đảm **Location và Link trỏ đúng tài nguyên, cache validator đúng biểu diễn, lỗi đúng semantics và mọi đường truy cập vẫn kiểm tra quyền**, kể cả sau reverse proxy hoặc khi client retry.
