# Tạo Location, liên kết và URI qua bộ dựng URI

Client gửi **POST /v1/orders**, server tạo **o-918**. Client cần URI chuẩn để GET/cập nhật. Nối chuỗi từ Host, path và ID dễ làm **Location** sai khi có proxy, context path hoặc ký tự đặc biệt.

**UriComponentsBuilder**, **ServletUriComponentsBuilder** và **MvcUriComponentsBuilder** cùng **ResponseEntity** giúp tạo Location và link theo template/mapping. Bài thuộc chương **Spring MVC**, module **INTEGRATION_API_REST**, có HTTP, bảo mật, OpenAPI và kiểm thử.

## 1. Mục tiêu và những nguyên tắc phải giữ

Sau bài này, bạn có thể:

1. Chọn **Location** cho **201 Created**, **202 Accepted**, redirect **3xx**, và phân biệt nó với **Content-Location**, link relation trong response.
2. Tạo URI bằng template, path segment và query parameter với **UriComponentsBuilder**; hiểu sự khác biệt giữa **encode trước và sau khi expand**.
3. Dùng **ServletUriComponentsBuilder** cho context path/request hiện tại; **MvcUriComponentsBuilder** cho mapping của controller.
4. Trả **ResponseEntity.created(uri)** và cung cấp các liên kết **self/collection/next/related** rõ ngữ nghĩa.
5. Xử lý origin phía sau reverse proxy, header **Forwarded/X-Forwarded-***, context path và external hostname mà không tạo lỗ hổng Host header injection.
6. Kiểm thử URI, encoding, status, authorization, schema và các đường đi qua gateway bằng MockMvc và integration test.

Ba nguyên tắc:

- **URI mô tả tài nguyên**, không phải tên hàm Java; đường dẫn được công bố phải ổn định theo hợp đồng.
- **Bộ dựng URI xử lý cấu trúc và encoding**; nó không tự xác thực quyền, tính đúng của host hoặc nội dung dữ liệu nghiệp vụ.
- **Response header và body phải nhất quán**: Location và self phải dẫn tới đúng resource, route mới được tạo phải đọc được trong phạm vi quyền đã công bố.

## 2. Ngữ nghĩa HTTP của Location

Theo HTTP Semantics (**RFC 9110**), **Location** là response header chứa một **URI reference** để chỉ resource liên quan đến kết quả của request. Ý nghĩa phụ thuộc **status code**.

| Trường hợp | HTTP status | Ý nghĩa của Location | Client nên làm gì? |
|---|---|---|---|
| POST tạo order thành công | **201 Created** | URI của resource được tạo (primary created resource) | Lưu URI và GET khi cần |
| PUT tạo resource ở URI đã định danh | **201 Created** | Thường chính URI target được tạo | Dùng URI để GET/xác minh |
| Nhận yêu cầu chạy báo cáo | **202 Accepted** | Theo **hợp đồng API**, thường trỏ tới job/status resource | Poll GET job; chưa coi tác vụ hoàn tất |
| Redirect tới kết quả hoặc trang khác | **303 See Other** | URI để client thực hiện retrieval, thường qua GET | Theo quy tắc redirect; không gửi lại POST mù |
| Redirect tạm thời, giữ phương thức | **307 Temporary Redirect** | URI đích tạm thời | Client giữ method/body theo semantics |
| Redirect vĩnh viễn, giữ phương thức | **308 Permanent Redirect** | URI đích lâu dài | Cân nhắc tác động với client/cache |

Ví dụ tạo resource:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Authorization: Bearer <access-token>

{"cartId":"cart-73"}
~~~

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/orders/o-918
Content-Type: application/json
Cache-Control: no-store

{"id":"o-918","status":"PENDING"}
~~~

**201** xác nhận resource đã tạo; Location nếu có chỉ resource chính. Với POST tạo collection member, nên trả Location để client không phải tự ghép URI.

### 2.1. Relative Location có hợp lệ không?

Có. **Location** chấp nhận **URI-reference**, không bắt buộc absolute URI:

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/o-918
~~~

Relative Location tránh phụ thuộc hostname; client phải resolve URI-reference đúng chuẩn. Đường dẫn bắt đầu **/** là root-relative: nhớ prefix triển khai như **/api**. Khi hợp đồng cần absolute, dùng public origin đáng tin.

### 2.2. Location không phải Content-Location

| Header | Câu hỏi trả lời |
|---|---|
| **Location** | Resource hoặc đích chuyển hướng liên quan đến response nằm ở đâu? |
| **Content-Location** | Representation trong nội dung response tương ứng với URI nào? |
| **Link** | Resource này liên quan đến những resource/quan hệ nào? |

Không dùng **Content-Location** thay Location cho response **201** chỉ vì body chứa biểu diễn vừa tạo. Content-Location có ý nghĩa về **representation**, không mặc nhiên yêu cầu client chuyển hướng.

### 2.3. 202 và Location của job là một thiết kế hợp đồng

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/j-88
Retry-After: 5
Content-Type: application/json

{"jobId":"j-88","status":"QUEUED"}
~~~

**202** chưa hoàn tất xử lý; Location tới job là **quy ước API**, không bắt buộc cho mọi 202. Retry-After hỗ trợ polling. Retry POST sau timeout cần idempotency/đối soát.

## 3. Vì sao không nên nối chuỗi URI?

Một đoạn code trông đơn giản:

~~~java
String location = request.getScheme() + "://"
        + request.getHeader("Host")
        + "/v1/orders/" + orderId;
~~~

có các rủi ro:

- **Host header** có thể do client cung cấp; nếu đưa thẳng vào Location có thể tạo **link sai miền, open redirect hoặc password-reset poisoning** trong bối cảnh tương tự.
- App chạy sau proxy có thể nhìn thấy **http://internal-service:8080** thay vì **https://api.example.test**.
- Context path **/api** hoặc servlet mapping làm path thiếu/thừa prefix.
- ID có **khoảng trắng, ?, #, /, % hoặc Unicode** cần được encode theo đúng **URI component**, không phải nối nguyên văn.
- Query parameter có thể bị nối sai, lặp key hoặc mất filter khi xây link phân trang.
- Một route đổi từ **/orders/{id}** sang đường dẫn khác làm mọi đoạn nối chuỗi rải rác phải sửa.

Builder giảm lỗi chuỗi nhưng **không tự xác thực input**.

## 4. UriComponentsBuilder: path, query và URI template

**UriComponentsBuilder** không cần request HTTP hiện tại; nó phù hợp để xây URI tương đối/absolute từ template đã xác định. Ví dụ Java/Spring:

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

class UriExamples {
    URI order(String orderId) {
        return UriComponentsBuilder
                .fromPath("/v1/orders/{orderId}")
                .encode()
                .buildAndExpand(Map.of("orderId", orderId))
                .toUri();
    }

    URI list(String category, int page, int size) {
        return UriComponentsBuilder
                .fromPath("/v1/products")
                .queryParam("category", "{category}")
                .queryParam("page", page)
                .queryParam("size", size)
                .encode()
                .buildAndExpand(Map.of("category", category))
                .toUri();
    }
}
~~~

Khi `orderId` là **o-918**, kết quả là **/v1/orders/o-918**. Khi category là **camera & lens**, query parameter được encode phù hợp thay vì làm dấu **&** trở thành ký tự tách hai tham số.

### 4.1. Encode trước hay sau khi expand?

Điểm khác nhau quan trọng:

~~~java
// Khuyến nghị khi biến là dữ liệu opaque, có thể chứa ký tự reserved.
URI strict = UriComponentsBuilder
        .fromPath("/v1/orders/{id}")
        .encode()                   // encode template trước
        .buildAndExpand("o/918")
        .toUri();                   // /v1/orders/o%2F918

// Không giống hoàn toàn khi dùng UriComponents.encode() sau expand.
URI componentAware = UriComponentsBuilder
        .fromPath("/v1/orders/{id}")
        .buildAndExpand("o/918")
        .encode()
        .toUri();
~~~

**Builder.encode() trước khi expand** xử lý template và encode giá trị URI variable theo cách chặt hơn, kể cả ký tự reserved như **/** nếu đó là *dữ liệu của ID*, không phải delimiter của path. **UriComponents.encode() sau expand** làm việc theo cấu trúc component và có thể giữ lại những ký tự reserved hợp lệ trong component, nên không tương đương trong mọi trường hợp.

Đừng dùng **URLEncoder** cho toàn bộ URL; cơ chế đó hướng tới form encoding và có quy tắc dấu **+** khác với URI path. Cũng đừng encode thủ công một giá trị rồi yêu cầu builder encode lại mà không có quy ước: **double encoding** có thể biến **%2F** thành **%252F**.

Servlet container có thể từ chối/giải mã **%2F** trước routing. Với ID chứa slash, ưu tiên ID URL-safe; encoding đúng không bảo đảm server route được.

### 4.2. Path segment khác toàn bộ path

~~~java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("v1", "orders", "{id}")
        .encode()
        .buildAndExpand("o-918")
        .toUri();
~~~

**pathSegment** diễn đạt các segment riêng, giảm lỗi thiếu/thừa slash. **path** phù hợp khi có một template path hoàn chỉnh. Nếu segment đến từ input bên ngoài, vẫn cần validation nghiệp vụ và giới hạn ký tự để đảm bảo hệ thống downstream diễn giải đúng.

### 4.3. Query parameter có nhiều giá trị

~~~java
URI next = UriComponentsBuilder
        .fromPath("/v1/products")
        .queryParam("tag", "camera", "mirrorless")
        .queryParam("cursor", "{cursor}")
        .encode()
        .buildAndExpand("opaque+cursor/next")
        .toUri();
~~~

Client theo link **next** từ server, giữ filter/sort và không chỉnh cursor opaque hoặc đưa token vào URI.

## 5. ServletUriComponentsBuilder: tạo URI từ request hiện tại

**ServletUriComponentsBuilder** dùng thông tin request Spring MVC:

| Phương thức | Nội dung lấy từ request | Trường hợp phù hợp |
|---|---|---|
| **fromCurrentRequestUri()** | Scheme, host, port và path của request, **không lấy query** | POST đến collection, thêm **/{id}** cho Location |
| **fromCurrentRequest()** | URI request **có cả query** | Giữ filter/sort khi tạo link trang khác |
| **fromCurrentContextPath()** | Origin và context path của ứng dụng | Xây route khác bắt đầu từ gốc ứng dụng |
| **fromCurrentServletMapping()** | Origin, context path và servlet mapping liên quan | Ứng dụng có DispatcherServlet mapping đặc biệt |

Một POST tới **/v1/orders**:

~~~java
import java.net.URI;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

URI location = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .path("/{id}")
        .encode()
        .buildAndExpand("o-918")
        .toUri();
~~~

POST đến **https://api.example.test/v1/orders** tạo Location **https://api.example.test/v1/orders/o-918**. **fromCurrentRequest()** có thể giữ query ngoài ý định; ưu tiên **fromCurrentRequestUri()** ở tình huống này.

### 5.1. Bắt đầu từ context path

~~~java
URI uri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/v1/orders/{id}")
        .encode()
        .buildAndExpand("o-918")
        .toUri();
~~~

Context path **/shop-api** có thể tạo URI **https://api.example.test/shop-api/v1/orders/o-918**. Tránh nhân đôi prefix khi proxy đã cấu hình forwarded headers.

### 5.2. Đừng dựa vào request khi chưa tin được public origin

Builder không xác thực Host/Forwarded; proxy chuyển header giả mạo có thể khiến Location trỏ tới domain attacker.

Lựa chọn an toàn:

1. **Ưu tiên relative Location** khi hợp đồng/client cho phép, và xác định base path từ route ứng dụng.
2. Khi cần absolute URI, dùng **public base URL được cấu hình và kiểm soát**, ví dụ **https://api.example.test**, không rút từ header tùy ý.
3. Nếu phải dùng thông tin forward, cấu hình **trusted reverse proxy** để **loại bỏ/ghi lại** header do bên ngoài gửi và chấp nhận chỉ header do proxy tin cậy sinh.
4. Đặt allowlist hostname, scheme HTTPS, port/prefix hợp lệ và có integration test từ ingress tới backend.

Ví dụ có base URL tin cậy:

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

class PublicUriFactory {
    private final URI publicBaseUri;

    PublicUriFactory(String configuredBaseUri) {
        // Chỉ lấy từ cấu hình triển khai, không từ body/header client.
        this.publicBaseUri = URI.create(configuredBaseUri);
    }

    URI order(String id) {
        return UriComponentsBuilder.fromUri(publicBaseUri)
                .path("/v1/orders/{id}")
                .encode()
                .buildAndExpand(id)
                .toUri();
    }
}
~~~

Validate publicBaseUri lúc startup: HTTPS, host/prefix cho phép, không có user-info/query/fragment. Với base **https://api.example.test/shop-api**, test đường dẫn cuối.

### 5.3. Spring Boot và ForwardedHeaderFilter

Khi HTTPS được terminate ở reverse proxy, backend có thể chỉ nhận HTTP nội bộ và host nội bộ. Các header **Forwarded** (RFC 7239) và **X-Forwarded-Proto/Host/Port/Prefix** có thể mô tả URI public. Spring hỗ trợ xử lý chúng thông qua cơ chế forwarded headers của runtime và **ForwardedHeaderFilter** trong môi trường Servlet.

Ví dụ cấu hình Spring Boot minh họa:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Cấu hình framework **không tạo trust boundary**. Proxy biên phải strip/overwrite Forwarded/X-Forwarded-* của client. Có thể dùng chiến lược **native** nếu container/proxy được cấu hình tin cậy; tránh hai cơ chế xử lý trùng.

Test qua backend và public proxy: URI dùng **HTTPS**, host/prefix đúng, không lộ **internal-service:8080**.

## 6. MvcUriComponentsBuilder: liên kết theo mapping của controller

Khi đường dẫn phụ thuộc **@RequestMapping, @GetMapping và @PathVariable**, việc liên kết từ method mapping có thể giúp giảm hardcode route trong nhiều lớp.

~~~java
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.MvcUriComponentsBuilder;
import static org.springframework.web.servlet.mvc.method.annotation.MvcUriComponentsBuilder.on;

@RestController
@RequestMapping("/v1/orders")
class OrdersReadController {

    @GetMapping("/{id}")
    public ResponseEntity<String> getById(@PathVariable String id) {
        return ResponseEntity.ok(id);  // Minh họa mapping.
    }
}

class OrdersLinks {
    URI detail(String id) {
        return MvcUriComponentsBuilder
                .fromMethodCall(on(OrdersReadController.class).getById(id))
                .encode()
                .build()
                .toUri();
    }
}
~~~

**fromMethodCall** suy URI từ mapping qua proxy, **không gọi nghiệp vụ**. Đổi mapping vẫn phải đánh giá backward compatibility cho URI công khai.

Proxy có giới hạn với class/method final và một số cấu hình; kiểm thử với phiên bản Spring thật.

### 6.1. Chọn builder nào?

| Yêu cầu | Gợi ý |
|---|---|
| Xây URI từ template độc lập request | **UriComponentsBuilder** |
| POST collection, thêm ID vào request path | **ServletUriComponentsBuilder.fromCurrentRequestUri()** |
| Link bắt đầu từ context path đang triển khai | **ServletUriComponentsBuilder.fromCurrentContextPath()** |
| Link theo mapping/controller method | **MvcUriComponentsBuilder** |
| Liên kết HATEOAS theo relation và mapping | **WebMvcLinkBuilder** (Spring HATEOAS) |
| Absolute URL công khai xuyên nhiều proxy | **Configured public base URI** hoặc forwarded-header trust chain được chứng minh |

Không có builder nào thay thế **quyết định URI contract** và quy tắc authorization. Chọn kiểu dựng phù hợp với mức độ cần ổn định, phạm vi deployment và khả năng proxy.

## 7. ResponseEntity: tạo Location đúng mã trạng thái

Ví dụ resource **order** với Spring Web MVC và Java 17:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

record CreateOrderRequest(@NotBlank String cartId) {}
record OrderView(String id, String status, long totalMinor, String currency) {}

interface OrdersService {
    // Authz, validation, transaction và idempotency nằm ở service.
    OrderView createForCurrentUser(CreateOrderRequest request);
    OrderView findVisibleForCurrentUser(String id);
}

@RestController
@RequestMapping("/v1/orders")
class OrdersController {
    private final OrdersService orders;

    OrdersController(OrdersService orders) {
        this.orders = orders;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderView result = orders.createForCurrentUser(request);
        URI location = ServletUriComponentsBuilder.fromCurrentRequestUri()
                .path("/{id}")
                .encode()
                .buildAndExpand(result.id())
                .toUri();
        return ResponseEntity.created(location)
                .cacheControl(CacheControl.noStore())
                .body(result);
    }

    @GetMapping(value = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderView> get(@PathVariable String id) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(orders.findVisibleForCurrentUser(id));
    }
}
~~~

Khi chạy với POST **https://api.example.test/v1/orders**, Location phải trỏ tới resource có thể đọc bằng **GET /v1/orders/{id}**. **ResponseEntity.created(uri)** đặt **201 Created và Location**; nếu cần body, gọi **body(result)**. Với resource cá nhân, ví dụ trả **Cache-Control: no-store**; status thành công không thay việc kiểm tra quyền ở GET.

### 7.1. URI chỉ được tạo sau khi transaction nghiệp vụ thành công

Không trả **201** nếu chỉ đưa lệnh vào queue mà resource order thực tế chưa được tạo theo hợp đồng. Nếu tạo job bất đồng bộ, có thể dùng **202 + Location của job**; nếu lưu order thành công nhưng gửi email thất bại, cần xác định rõ order có được coi đã tạo hay không và cách outbox/compensation xử lý.

Với POST có nguy cơ client retry sau timeout, dùng **Idempotency-Key** hoặc unique business constraint theo contract. Builder không chống tạo hai order; nó chỉ tạo **URI đúng** cho order thực tế đã được ghi nhận.

### 7.2. PUT tạo resource tại URI đã biết

~~~http
PUT /v1/preferences/u-17 HTTP/1.1
Content-Type: application/json
If-None-Match: *

{"theme":"dark"}
~~~

Nếu được phép tạo mới và điều kiện thỏa, **201 + Location: /v1/preferences/u-17** là hợp lý; nếu đã tồn tại, precondition có thể trả **412**. Một PUT thay thế resource hiện hữu thành công thường trả **200** hoặc **204**, không tự đổi sang 201 chỉ vì vừa ghi database.

### 7.3. Không tạo Location khi phương thức chỉ đọc

GET thông thường không cần **Location** để nói “đây là URL của chính tôi”; dùng **self link** hoặc metadata có ngữ nghĩa. Location với **200 OK** không mặc định khiến browser điều hướng như một 3xx; tránh đưa tín hiệu lẫn lộn.

## 8. Tạo liên kết: self, collection, next và HATEOAS

**Location** xác định URI liên quan tới **kết quả** tạo resource/redirect. Trong khi đó, **Link header** (RFC 8288) hoặc liên kết trong representation giúp client **khám phá tài nguyên có quan hệ**, ví dụ **self, collection, next, prev, related**. Không nhất thiết trả toàn bộ liên kết có thể có trong mỗi response; chọn theo nhu cầu điều hướng và quyền.

Một GET chi tiết có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </v1/orders/o-918>; rel="self"
Link: </v1/orders>; rel="collection"

{"id":"o-918","status":"PENDING"}
~~~

**Link** là metadata có relation rõ ràng; client có thể đi theo URI trả về thay vì tự ghép đường dẫn. Quan hệ **next** đặc biệt hữu ích cho cursor pagination:

~~~java
import java.net.URI;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

URI next = ServletUriComponentsBuilder.fromCurrentRequest()
        .replaceQueryParam("cursor", "{nextCursor}")
        .encode()
        .buildAndExpand("cur+12/abc")
        .toUri();
~~~

Ví dụ giữ lại các filter khác đang có trong request và chỉ thay cursor. **Cursor là opaque**: không giải mã, tăng hay ghép lại từ số trang. Cần whitelist/sanitize các query parameter được chấp nhận trước khi phát link; không chuyển tiếp access token hoặc thông tin bí mật có trong query từ request của client.

### 8.1. Spring HATEOAS WebMvcLinkBuilder

Nếu dự án dùng **spring-boot-starter-hateoas**, có thể tạo link theo mapping:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.*;

class OrderRepresentationFactory {
    EntityModel<OrderView> toModel(OrderView order) {
        Link self = linkTo(
                methodOn(OrdersController.class).get(order.id()))
                .withSelfRel();
        return EntityModel.of(order, self);
    }
}
~~~

Đoạn này dùng **OrdersController** ở mục 7, chỉ minh họa cách dựng representation; nếu return EntityModel ở endpoint thực, cần cập nhật kiểu trả về/controller và **media type contract** nhất quán. Spring HATEOAS hỗ trợ HAL với **application/hal+json** và trường **_links** khi được cấu hình. Không trộn HAL với một JSON tự định nghĩa chỉ vì thấy cùng tên thuộc tính _links.

**Link không thay authorization:** ẩn link không ngăn client gọi trực tiếp. Server phải kiểm tra role/ownership và trạng thái. Không trả link chứa token hoặc ID bí mật.

## 9. Bảo mật và tính ổn định của Location/URI

| Rủi ro | Ví dụ lỗi | Biện pháp |
|---|---|---|
| **Host header injection** | Location trỏ tới evil.example do Host bị thay | Trusted proxy, allowlist/public base URI |
| **Forwarded header spoofing** | Client tự gửi X-Forwarded-Host | Proxy biên strip/overwrite trước Spring |
| **Path traversal/URI component** | ID chứa dấu slash, ?, # hoặc chuỗi đặc biệt | Dùng URI template + encode + validate ID |
| **Open redirect** | Redirect nhận URI tuyệt đối từ query không kiểm tra | Chỉ redirect tới route/domain được phép |
| **Thông tin cá nhân trong URI** | Link chứa email, session token hoặc chi tiết giao dịch | Dùng opaque ID; không đưa secret vào query |
| **IDOR/BOLA** | Link tới order người khác vẫn GET được | Kiểm tra tenant/owner/quyền tại endpoint đích |
| **Cache leak** | Location/self dẫn đến response riêng bị public-cache | Cache-Control phù hợp; Vary/authorization |
| **HTTP downgrade** | Link absolute dùng http khi bên ngoài HTTPS | Kiểm tra public scheme và cấu hình TLS proxy |

### 9.1. Validation đầu vào khác với URI encoding

Encoding biến một giá trị thành phần URI có cú pháp hợp lệ, **không** bảo đảm giá trị đó là **ID hợp lệ** hoặc người dùng có quyền truy cập. Ví dụ **../admin** được encode phù hợp vẫn có thể không được ứng dụng chấp nhận làm order ID. Đối với order ID, dùng định dạng server cấp, độ dài giới hạn và validation trước khi truy vấn. Với redirect tới URL do client cung cấp, **phân tích scheme/host/port theo allowlist** thay vì chỉ encode.

### 9.2. CORS và link tuyệt đối

Frontend khác origin có thể đọc **Location** hoặc **Link** bằng JavaScript chỉ khi chính sách CORS hợp lệ cho phép expose header tương ứng, ví dụ:

~~~http
Access-Control-Expose-Headers: Location, Link
~~~

Điều này **không cấp quyền** cho frontend gọi tài nguyên; request tiếp theo vẫn cần authentication/authorization. Nếu response dùng credentials, CORS phải cấu hình origin cụ thể và chính sách tương thích; không dùng wildcard thiếu kiểm soát để “cho tiện”. Redirect qua origin khác có thể phát sinh thêm yêu cầu CORS, preflight hoặc thay đổi cách browser gửi credentials.

### 9.3. Absolute URI hay relative URI?

Chọn theo client thực tế:

- **Relative**: hợp lý khi consumer và chuẩn HTTP của client hỗ trợ resolve URI-reference, tránh phụ thuộc hostname/prefix public nếu đã thiết kế đúng.
- **Absolute**: hữu ích cho callback, webhook, external link hoặc SDK cần self-contained URL; phải dựa trên origin được cấu hình tin cậy.
- **Mixed deployments**: nếu service có nhiều domain/tenant, tạo URI theo **domain đã được phê duyệt và gắn với tenant**; tuyệt đối không lấy ngẫu nhiên tenant host do requester gửi.

Đừng quyết định chỉ theo cảm giác “REST luôn cần absolute URL”: RFC cho phép URI-reference cho Location. Nhưng nếu tài liệu client yêu cầu absolute, hãy tuân hợp đồng và kiểm thử đúng hostname.

## 10. OpenAPI: công bố Location và URI của tài nguyên

Client cần biết **Location** là URI của resource nào, có thể dùng phương thức nào để truy cập và response body mang schema gì:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders:
    post:
      summary: Create an order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [cartId]
              properties:
                cartId: { type: string }
      responses:
        '201':
          description: Order created; Location points to its resource
          headers:
            Location:
              description: URI-reference of the created order
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema: { type: object }
        '400': { description: Invalid input }
        '401': { description: Unauthenticated }
        '403': { description: Forbidden }
  /v1/orders/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200': { description: Order detail }
        '404': { description: Not found or not disclosed }
~~~

Trong dự án thật, thay schema object tổng quát bằng DTO/Problem Details và bổ sung security scheme, idempotency, ví dụ response. **OpenAPI khai báo Location không tự sinh header**; controller/service phải thực hiện đúng và contract test xác minh.

## 11. Kiểm thử với MockMvc và gateway

Một integration test cho controller mục 7 (cần Spring context, fixture/stub service và principal hợp lệ):

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.hamcrest.Matchers.endsWith;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLocationTest {
    @Autowired MockMvc mvc;

    @Test
    void postReturnsCreatedResourceLocation() throws Exception {
        mvc.perform(post("/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"cartId\":\"cart-73\"}"))
           .andExpect(status().isCreated())
           .andExpect(header().string("Location",
                   endsWith("/v1/orders/o-918")));
    }
}
~~~

Test giả định service được cấu hình trả ID **o-918**. Nếu bật Spring Security, test phải cấp principal/token và quyền thật; **không tắt authorization để che lỗi**. Test trên mới kiểm tra Location; cần bổ sung:

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Tạo rồi GET URI từ Location | GET trả đúng resource, không tự ghép ID |
| ID/query chứa **&, ?, /, Unicode** | URI được encode và route xử lý theo policy |
| App có context path/forwarded prefix | Không thiếu/trùng prefix |
| Proxy HTTPS với host public | Link dùng HTTPS và domain được duyệt |
| Host/Forwarded giả mạo | Không tạo Location tới domain attacker |
| Hai tenant gọi cùng ID | Quyền tài nguyên vẫn được kiểm tra |
| JSON thiếu cartId | Không tạo order/Location giả |
| POST timeout rồi retry | Idempotency không tạo hai order |

Test controller **không chứng minh forwarded-header trust chain**; phải kiểm thử qua proxy/gateway thật với header đầu vào được kiểm soát.

## 12. Bài tập thiết kế

API quản lý hóa đơn chạy tại **https://api.example.test/shop-api**. Endpoint **POST /v1/invoices** trả **201 + Location**; endpoint **GET /v1/invoices/{id}** đọc hóa đơn. Có một client gửi tên/tài nguyên chứa ký tự đặc biệt; gateway terminate TLS và thêm path prefix. Ngoài ra danh sách hóa đơn dùng **cursor pagination**.

Hãy: (1) viết response 201 cho invoice **inv-73**; (2) dùng UriComponentsBuilder dựng URI detail; (3) dùng ServletUriComponentsBuilder đúng cách sau proxy; (4) tạo Link next giữ filter; (5) đề xuất kiểm thử giả mạo Host/Forwarded và quyền khác tenant; (6) giải thích khi nào chọn URI tương đối.

**Gợi ý:** Location là **/shop-api/v1/invoices/inv-73** (relative) hoặc absolute URI với host HTTPS được duyệt. Builder dùng template **{id}** và **encode trước expand**; Link next thay cursor nhưng giữ filter hợp lệ. Không tin Host header tùy ý, và GET invoice vẫn kiểm tra owner/tenant.

## 13. Checklist và tài liệu chuẩn

- [ ] 201 có Location trỏ resource thực; 202 trỏ job chỉ theo contract.
- [ ] Dùng template/URI builder thay nối chuỗi; kiểm tra encoding, query, context path.
- [ ] Public host/scheme được kiểm soát; Forwarded headers có proxy tin cậy.
- [ ] Link relation đúng nghĩa; không dùng link thay authorization.
- [ ] Controller và OpenAPI nhất quán; test 201 → GET, CORS, gateway và security.

Tham khảo: **RFC 9110 — HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 3986 — URI Generic Syntax**, https://www.rfc-editor.org/rfc/rfc3986.html; **RFC 7239 — Forwarded HTTP Extension**, https://www.rfc-editor.org/rfc/rfc7239.html; **RFC 8288 — Web Linking**, https://www.rfc-editor.org/rfc/rfc8288.html; **Spring Framework — URI Building**, https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html; **Spring HATEOAS**, https://docs.spring.io/spring-hateoas/reference/index.html.

**Kết luận:** **Location** truyền URI của tài nguyên được tạo hoặc đích redirect; **Link** mô tả quan hệ điều hướng. Trong Spring MVC, URI builder giúp giữ cấu trúc, biến và encoding đúng, nhưng **public origin, ranh giới proxy, quyền truy cập và contract HTTP** vẫn phải được thiết kế, bảo vệ và kiểm thử độc lập.
