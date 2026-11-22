# `consumes`, `produces` và lỗi thương lượng nội dung

> **Module:** `INTEGRATION_API_REST` — chương **Spring MVC**. Bài này giải thích cách REST API dựa trên resource/URI và ngữ nghĩa HTTP sử dụng `Content-Type`, `Accept`, `consumes`, `produces` và `HttpMessageConverter` để trao đổi JSON hoặc các định dạng khác. Người học triển khai Java/Spring MVC, phân biệt lỗi **415/406/400**, tài liệu hóa OpenAPI, bảo vệ endpoint và kiểm thử hành vi ở HTTP boundary.

## 1. Tình huống mở đầu: URI đúng nhưng vẫn nhận lỗi

Giả sử cửa hàng có endpoint `POST /v1/orders`. Client gửi:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: text/plain
Accept: application/json

{"productId":"p_17","quantity":2}
~~~

Body trông giống JSON, nhưng client **tự khai** đó là `text/plain`. Controller chỉ nhận `application/json` nên Spring có thể trả **`415 Unsupported Media Type`** trước khi gọi phương thức tạo đơn. Đổi `Content-Type` sang `application/json`, request có thể qua bước kiểm tra định dạng đầu vào.

Ngược lại, khi client gửi đúng JSON nhưng yêu cầu XML:

~~~http
GET /v1/orders/ord_916 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/xml
~~~

Nếu API chỉ có JSON representation, kết quả phù hợp là **`406 Not Acceptable`**: server không thể cung cấp representation theo các loại nội dung client chấp nhận.

**Hai header độc lập:** `Content-Type` mô tả **body client đang gửi**; `Accept` mô tả **response client muốn nhận**. Sai chiều là nguyên nhân phổ biến của lỗi tích hợp.

### Mục tiêu học tập

- Đọc đúng `Content-Type`, `Accept`, media range, wildcard và hệ số ưu tiên `q`.
- Hiểu `consumes`/`produces` hạn chế chọn handler và vai trò **message converter** ở Spring MVC.
- Phân biệt `415`, `406` với `400`, `422`, `401/403` và lỗi server.
- Viết controller Java/Spring xử lý JSON, có response `201 Location` và Problem Details phù hợp.
- Kiểm tra content negotiation, bảo mật và khả năng tương thích bằng MockMvc/OpenAPI.

## 2. Cú pháp HTTP: loại nội dung gửi và loại nội dung nhận

| Header | Ai gửi? | Ý nghĩa | Ví dụ |
|---|---|---|---|
| `Content-Type` | Client trong request có body; server trong response có body | Media type của **representation đang truyền** | `Content-Type: application/json` |
| `Accept` | Thường là client | Media types mà client chấp nhận ở **response** | `Accept: application/json` |
| `Accept-Encoding` | Client | Content codings chấp nhận, ví dụ gzip; **không phải** JSON/XML | `Accept-Encoding: gzip` |
| `Content-Encoding` | Bên gửi body | Content coding đã áp dụng | `Content-Encoding: gzip` |
| `Accept-Language` | Client | Ngôn ngữ mong muốn, không quyết định JSON/XML | `Accept-Language: vi` |
| `Vary` | Server/caches | Các request headers ảnh hưởng việc chọn representation | `Vary: Accept` |

Một `GET` không có request body **không cần** `Content-Type`. Thêm `Content-Type: application/json` vào GET không giúp server trả JSON; header thích hợp để yêu cầu response là `Accept: application/json`.

### 2.1. Media type và suffix `+json`

Media type gồm type/subtype, có thể kèm parameter:

~~~http
Content-Type: application/json
Content-Type: application/merge-patch+json
Content-Type: application/vnd.example.order+json
Content-Type: multipart/form-data; boundary=abc123
~~~

- `application/json`: JSON thông thường.
- `application/merge-patch+json`: JSON Merge Patch, **ngữ nghĩa cập nhật** khác JSON document thông thường.
- `application/vnd.example.order+json`: vendor media type dùng structured syntax suffix `+json`.
- `multipart/form-data`: dùng boundary để chia các form part; không giống JSON body.

Không suy ra mọi `*+json` đều có **cùng ý nghĩa nghiệp vụ**, dù nhiều message converter có thể dùng Jackson để đọc/ghi chúng.

### 2.2. Media range, wildcard và `q` trong Accept

~~~http
Accept: application/json
Accept: application/json, application/xml;q=0.5
Accept: application/*;q=0.8, text/plain;q=0.2
Accept: */*
~~~

`q` là mức ưu tiên tương đối từ 0 đến 1 (mặc định 1); `q=0` nghĩa là **không chấp nhận** loại nội dung đó theo phạm vi tương ứng. Wildcard có thể khớp nhiều media type; quy tắc chọn còn phụ thuộc mức cụ thể của media range và khả năng thực tế của server.

Ví dụ, với controller chỉ `produces="application/json"`:

| `Accept` của client | Hành vi kỳ vọng |
|---|---|
| Không có `Accept` hoặc `*/*` | Có thể trả JSON |
| `application/json` | JSON được chấp nhận |
| `application/json;q=0.8, application/xml;q=1` | JSON vẫn chấp nhận vì `q>0` và server không hỗ trợ XML |
| `application/xml` | `406` nếu không có representation XML |
| `application/json;q=0`, không có range khác cho JSON | Không chọn JSON, thường `406` |

**Accept là yêu cầu về định dạng, không phải lệnh buộc server phải hỗ trợ nó.** Tương tự, client không thể gửi `Content-Type: application/xml` vào endpoint JSON rồi yêu cầu server tự đoán body.

## 3. Trong Spring MVC, `consumes` và `produces` làm gì?

~~~java
@PostMapping(
    path = "/v1/orders",
    consumes = "application/json",
    produces = "application/json"
)
public OrderView create(@RequestBody CreateOrderRequest request) {
    // ...
}
~~~

- `consumes` là điều kiện media type của **request representation**. Body phải phù hợp với loại input handler chấp nhận.
- `produces` là điều kiện media type của **response representation**. Spring đối chiếu với `Accept` để quyết định handler có thể phục vụ loại response yêu cầu hay không.
- `@RequestBody` yêu cầu Spring dùng một `HttpMessageConverter` phù hợp để **đọc body** thành Java object.
- Khi trả object từ `@RestController` hoặc `@ResponseBody`, Spring tìm converter để **ghi response** theo media type đã thương lượng.

Nếu đường dẫn và method khớp nhưng `Content-Type` không thỏa `consumes`, thường nhận **415**; nếu `Accept` không thỏa `produces`, thường nhận **406**. Đây là lỗi xảy ra **trước hoặc trong quá trình chọn/ghi handler**, không cần service nghiệp vụ đã chạy.

### 3.1. Luồng chọn handler và chuyển đổi dữ liệu

~~~mermaid
flowchart TD
    A["HTTP request: URI, method, headers, body"] --> B["Spring MVC handler mapping"]
    B --> C{"Request media type phù hợp consumes?"}
    C -- "Không" --> X["415 Unsupported Media Type"]
    C -- "Có" --> D{"Accept phù hợp produces?"}
    D -- "Không" --> Y["406 Not Acceptable"]
    D -- "Có" --> E["HttpMessageConverter đọc @RequestBody"]
    E --> F{"Body parse/validate được?"}
    F -- "Sai JSON" --> Z["400 Bad Request"]
    F -- "Hợp lệ" --> G["Controller -> service -> DTO"]
    G --> H["HttpMessageConverter ghi response"]
    H --> I["2xx + Content-Type phù hợp"]
~~~

Sơ đồ là **mô hình học tập**: Spring MVC có nhiều bước như security filters, argument resolvers, validation, exception resolvers và các điều kiện mapping khác. Nếu request cùng lúc sai nhiều điều kiện, thứ tự lỗi cụ thể phụ thuộc quá trình chọn handler và converter; khi kiểm thử nên **cố định các điều kiện còn lại** để xác định nguyên nhân.

### 3.2. Mapping và converter là hai “cửa” khác nhau

Spring có thể có Jackson converter hỗ trợ `application/json` lẫn `application/*+json`, nhưng handler:

~~~java
@PostMapping(consumes = "application/json")
~~~

**không tự nhiên** nhận mọi `application/vnd.example.order+json` chỉ vì Jackson biết parse JSON. Điều kiện `consumes` của handler được xét **trước** converter. Nếu muốn hỗ trợ vendor type, phải công bố rõ, ví dụ:

~~~java
@PostMapping(
    path = "/v1/orders",
    consumes = {
        "application/json",
        "application/vnd.example.order+json"
    },
    produces = "application/json"
)
~~~

Tương tự, khai báo `produces="application/xml"` không làm Spring tự sinh XML nếu chưa có converter và kiểu dữ liệu thích hợp. Nếu thiếu converter phù hợp khi ghi, có thể gặp lỗi server-side (ví dụ lỗi ghi representation), chứ không nên tự kết luận chỉ cần đổi annotation là hỗ trợ định dạng.

## 4. Ma trận lỗi: 415, 406 và các lỗi dễ nhầm

| Tình huống | Ví dụ | HTTP status thường phù hợp |
|---|---|---|
| Body có media type không được hỗ trợ | POST gửi `text/plain` vào handler chỉ `consumes=application/json` | **415 Unsupported Media Type** |
| Client không chấp nhận response có thể tạo | GET `Accept: application/xml` khi API chỉ JSON | **406 Not Acceptable** |
| Media type đúng nhưng JSON hỏng cú pháp | `Content-Type: application/json`, body `{"id":` | **400 Bad Request** |
| JSON parse được nhưng thiếu field bắt buộc/sai validation | `quantity=0`; phụ thuộc hợp đồng | **400** hoặc **422 Unprocessable Content** |
| Request không có quyền | Token thiếu/hết hạn hoặc thiếu scope | **401** hoặc **403** |
| Resource đúng media type nhưng trạng thái nghiệp vụ không cho thay đổi | Hủy đơn đã giao | **409 Conflict** |
| `If-Match` không còn khớp | Client chỉnh từ ETag lỗi thời | **412 Precondition Failed** |
| Server không ghi được representation do lỗi converter/cấu hình | Chỉ khai báo XML nhưng không có converter phù hợp | Lỗi **5xx** do server, không che bằng 406 vô điều kiện |

`415` nói về **loại nội dung request**; `406` nói về **loại nội dung response**. `400` nói về request không đọc/hiểu được dù media type đã phù hợp. Validation có thể được quy ước trả `400` hoặc `422`; API cần định nghĩa và kiểm thử thống nhất.

### 4.1. Cách cô lập lỗi

Với `POST` có JSON hợp lệ và `Accept: application/json`, thay **chỉ Content-Type** sang `text/plain` → 415. Giữ Content-Type JSON nhưng thay **chỉ Accept** sang `application/xml` → 406 khi API chỉ trả JSON. Giữ hai header đúng nhưng làm JSON malformed → 400. Thử từng thay đổi riêng để biết lỗi ở tầng nào.

### 4.2. Header thiếu, sai cú pháp và body rỗng

- POST có body nhưng không có `Content-Type`: nếu `consumes` yêu cầu JSON, request thường không khớp và có thể nhận `415`; không giả định server tự sniff JSON.
- `Content-Type: application/json` nhưng body rỗng trong khi `@RequestBody` là bắt buộc: thường là `400` do thiếu body có thể đọc.
- `Content-Type: application/json; charset=UTF-8`: có parameter charset nhưng vẫn là JSON; các parser UTF-8 chuẩn xử lý bình thường. Không dùng một danh sách charset không được hỗ trợ để che khác biệt về media type.
- Body nén bằng `Content-Encoding` sai/không được hỗ trợ cần xử lý ở tầng tương ứng; **không** đánh đồng cơ chế nén với `Accept` hoặc `consumes`.

Không gửi `406` chỉ vì **request payload sai kiểu**. Và không gửi `415` vì client muốn một **response format** mà server không tạo được.

## 5. Triển khai controller Java/Spring MVC

Ví dụ dùng Spring Boot 3.x/Spring MVC 6.x, Java 17+, Bean Validation và Spring Security. Resource là đơn hàng, request đầu vào chỉ chứa thông tin client được phép cung cấp; response là DTO độc lập. Các class được trình bày theo lát cắt, không phải một ứng dụng hoàn chỉnh có sẵn database/configuration.

### 5.1. DTO: tách request, response và domain

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
    @NotBlank String productId,
    @NotNull @Min(1) Integer quantity
) {}

public record OrderView(
    String id,
    String status,
    String currency,
    String totalAmount
) {}
~~~

DTO không cho client đặt `ownerId`, `tenantId`, `status=PAID` hoặc `totalAmount`. Service tính giá và kiểm tra quyền tại backend. `@Valid` kiểm tra các điều kiện đã được khai báo, nhưng **không biến dữ liệu đầu vào thành đáng tin**: vẫn phải kiểm tra product tồn tại, quota, tenant và nghiệp vụ.

### 5.2. Controller cho GET và POST JSON

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public ResponseEntity<OrderView> read(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt caller) {
        OrderView order = orders.readVisible(caller.getSubject(), id);
        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .body(order);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public ResponseEntity<OrderView> create(
            @AuthenticationPrincipal Jwt caller,
            @Valid @RequestBody CreateOrderRequest request) {
        OrderView created = orders.createAuthorized(
            caller.getSubject(), request);

        // ID do server cấp và đã bảo đảm là path-segment an toàn.
        URI location = URI.create("/v1/orders/" + created.id());
        return ResponseEntity.created(location)
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .body(created);
    }
}

interface OrderService {
    OrderView readVisible(String subject, String id);
    OrderView createAuthorized(
        String subject, CreateOrderRequest request);
}
~~~

**Hành vi cần ghi nhớ:**

- `GET` có `produces` nhưng **không có `consumes`** vì không cần request body.
- `POST` có cả hai điều kiện: input JSON, output JSON.
- Khi tạo thành công, `201 Created` và `Location` trỏ resource mới. URI tương đối như ví dụ được phép; hệ thống có thể cung cấp URI tuyệt đối qua cấu hình public base URL đáng tin nếu hợp đồng yêu cầu.
- Với `@RestController`, Java object được serialize thành response; không phải trả một chuỗi JSON viết tay.
- `@PreAuthorize` cần cấu hình **method security** hoạt động, JWT đã được Resource Server xác minh; service phải kiểm tra quyền trên object/tenant. `consumes`/`produces` **không** phải cơ chế authentication/authorization.
- Không trả entity JPA trực tiếp: nó có thể lộ field nội bộ, gây lazy-loading/N+1 hoặc thay đổi schema khi DB đổi.

### 5.3. Muốn hỗ trợ nhiều định dạng thì phải công bố rõ

Có thể khai báo `produces={"application/json","application/vnd.example.order+json"}` nếu cả hai thực sự có cùng schema/semantics và converter hỗ trợ. Nếu định dạng khác nhau, cần handler/DTO/converter phù hợp, không chỉ thêm chuỗi media type. Khi có nhiều handler chung path+method, kiểm thử `Accept: */*` và trường hợp thiếu Accept để tránh mapping mơ hồ; API chỉ có JSON thường dùng một `produces`.

### 5.4. Dùng media type có ngữ nghĩa đúng

Với `PATCH` theo JSON Merge Patch, hãy khai báo `consumes="application/merge-patch+json"` và áp dụng đúng RFC 7396, `If-Match`, allowlist field, authorization. Một converter parse được JSON **không** tự thực thi quy tắc merge: trong Merge Patch, `null` thường có nghĩa xóa property.

## 6. Vai trò của `HttpMessageConverter` và cấu hình thương lượng nội dung

`@RequestBody` và `@ResponseBody` đi qua cơ chế message converters. Thông thường, ứng dụng có Jackson trên classpath sẽ có converter JSON; `StringHttpMessageConverter` có thể xử lý văn bản; converter cho XML cần dependency/configuration riêng nếu API hỗ trợ.

| Thành phần | Nó giải quyết | Nó **không** giải quyết |
|---|---|---|
| `consumes` | Handler có nhận media type đầu vào này không? | Không tự parse JSON hay kiểm tra schema |
| `produces` | Handler có thể phục vụ media type response được yêu cầu không? | Không tự thêm serializer XML/CSV |
| `HttpMessageConverter` | Chuyển bytes ↔ Java object theo media type/kiểu Java | Không thay security, validation và business semantics |
| `@Valid` | Kiểm tra Bean Validation đã khai báo | Không xác thực quyền hoặc ngữ nghĩa nghiệp vụ |
| `@RestControllerAdvice` | Xử lý exception/Problem Details | Không bảo đảm response error có định dạng client chấp nhận nếu Accept không tương thích |

### 6.1. Không bật XML chỉ bằng annotation

Khai báo `produces={"application/json","application/xml"}` mà thiếu XML converter có thể khiến bước ghi response **thất bại**; annotation không tự cung cấp XML serialization.

### 6.2. Cấu hình không nên tự động đoán định dạng từ URL

Ưu tiên `Accept` và media type đã công bố. Nếu hỗ trợ `?format=xml` hoặc suffix `.xml`, phải cấu hình rõ độ ưu tiên với Accept, kiểm tra converter và cách trả 406. Không dựa vào extension từ người dùng để quyết định kiểu nội dung có thể gây hại.

### 6.3. `Content-Type` của response và cache

Server phải đặt `Content-Type` theo representation thực tế. Nếu cùng URI có JSON và CSV/XML tùy `Accept`, dùng `Vary: Accept` khi phù hợp để các cache phân biệt phiên bản representation. Nếu representation cũng thay theo ngôn ngữ, cân nhắc `Vary: Accept-Language`; nếu thay theo quyền người dùng, phân vùng cache/`Cache-Control: private` hoặc `no-store` theo chính sách, **không chỉ dựa vào Vary để bảo vệ dữ liệu**.

Nếu có strong `ETag`, validator phải phản ánh representation được chọn, không tái sử dụng sai một strong ETag cho JSON và CSV có byte khác. Không dùng cùng mã cache công khai cho kết quả cá nhân có chứa thông tin đơn hàng.

## 7. Trả lỗi đúng khi client và server không thỏa thuận được

### 7.1. Cấu trúc lỗi bằng Problem Details

Khi client chấp nhận JSON và server có thể tạo Problem Details, phản hồi 415 có thể như sau:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/unsupported-media-type",
  "title": "Unsupported Media Type",
  "status": 415,
  "code": "REQUEST_MEDIA_TYPE_NOT_SUPPORTED",
  "detail": "Endpoint này nhận application/json."
}
~~~

Với 406, cần thận trọng: nếu client nói `Accept: application/xml` và server **không thể tạo XML**, việc cố ép một error body `application/problem+json` có thể lại trái với lựa chọn định dạng của client. Một phản hồi `406` **không có body** hoặc một representation lỗi được client chấp nhận là cách đơn giản, hợp lệ.

~~~http
HTTP/1.1 406 Not Acceptable
Cache-Control: no-store
Content-Length: 0
~~~

Không bắt một JSON exception handler phải serialize JSON dưới mọi giá. Trong HTTP, body lỗi vẫn là representation và cần tuân theo quy tắc tương thích khi có thể; trong một số bối cảnh server có thể chọn giải thích lỗi thay vì tuân chính xác Accept, nhưng chính sách phải rõ và không gây vòng lặp lỗi converter.

### 7.2. Spring `@RestControllerAdvice` minh họa

~~~java
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotAcceptableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class MediaTypeErrorAdvice {
    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    ResponseEntity<Void> unsupportedRequestMediaType() {
        // Body rỗng tránh ép một response type không được chấp nhận.
        return ResponseEntity.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
            .cacheControl(CacheControl.noStore())
            .build();
    }

    @ExceptionHandler(HttpMediaTypeNotAcceptableException.class)
    ResponseEntity<Void> unacceptableResponseType() {
        return ResponseEntity.status(HttpStatus.NOT_ACCEPTABLE)
            .cacheControl(CacheControl.noStore())
            .build();
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ProblemDetail> unreadableJson() {
        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setType(URI.create(
            "https://api.example.test/problems/malformed-body"));
        problem.setTitle("Invalid request body");
        problem.setProperty("code", "MALFORMED_REQUEST_BODY");
        // Không trả exception.getMessage(): có thể lộ payload.
        return ResponseEntity.badRequest()
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }
}
~~~

Snippet chọn `415` và `406` **không body** để tránh ép response type. Với `400`/`ProblemDetail`, nếu `Accept` không tương thích, cần kiểm thử fallback. Spring có thể hỗ trợ Problem Details qua `ResponseEntityExceptionHandler`/cấu hình Boot; tránh các handler chồng chéo.

`HttpMessageNotWritableException` là lỗi **server ghi representation**, không tự đổi thành 406 khi client đã chấp nhận media type. Với `400` do malformed body, không phản chiếu nguyên body hay stack trace.

## 8. Bảo mật: media type không phải ranh giới tin cậy

`Content-Type: application/json` **không bảo đảm** body hợp lệ/đáng tin. Validate DTO, giới hạn size/depth và không bind thẳng JPA entity hay nhận `isAdmin`/`tenantId` từ caller.

Các tình huống cần kiểm tra:

- **Authentication/authorization:** kiểm tra token, scope, owner/tenant và quyền trên resource; 401/403 không phải lỗi negotiation. Bảo vệ endpoint ở security filter và service, không chỉ dùng `produces` để che response.
- **Cross-origin:** `application/json` trong một số request trình duyệt có thể dẫn tới CORS preflight; CORS không phải cơ chế xác thực. Với cookie/session, cấu hình CSRF phù hợp; không dựa vào Content-Type để thay CSRF protection.
- **Content-type confusion:** không “đoán” JSON từ một `text/plain` tùy ý; với tệp tải xuống, phát `Content-Type` và `X-Content-Type-Options: nosniff` khi thích hợp. Không render dữ liệu chưa làm sạch như HTML chỉ vì client yêu cầu `text/html`.
- **Giới hạn tài nguyên:** kiểm soát `Content-Length`/kích thước byte thực, decompression và số request; payload JSON hợp kiểu nhưng quá lớn vẫn có thể gây cạn bộ nhớ.
- **Log và Problem Details:** log mã lỗi/endpoint template/correlation ID; không ghi token hoặc body chứa PII để giải thích lỗi 415/400.

Không trả cùng một response chứa dữ liệu riêng tư cho mọi caller chỉ vì họ cùng gửi `Accept: application/json`. Content negotiation **chọn biểu diễn**, còn security **chọn dữ liệu được phép công bố**.

## 9. OpenAPI 3.1 mô tả input/output media types

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders:
    post:
      summary: Tạo đơn, nhận và trả JSON
      security: [{bearerAuth: []}]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
      responses:
        '201':
          description: Đã tạo đơn
          headers:
            Location:
              required: true
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400': {description: JSON hoặc dữ liệu đầu vào không hợp lệ}
        '401': {description: Chưa xác thực}
        '403': {description: Không có quyền tạo}
        '406': {description: Không thể tạo response phù hợp Accept}
        '415': {description: Request media type không được hỗ trợ}
  /v1/orders/{id}:
    get:
      summary: Đọc đơn ở định dạng JSON
      security: [{bearerAuth: []}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Representation đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404': {description: Không tìm thấy hoặc không công bố}
        '406': {description: Không hỗ trợ response media type yêu cầu}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    CreateOrder:
      type: object
      required: [productId, quantity]
      additionalProperties: false
      properties:
        productId: {type: string, minLength: 1}
        quantity: {type: integer, minimum: 1}
    Order:
      type: object
      required: [id, status, currency, totalAmount]
      properties:
        id: {type: string}
        status: {type: string}
        currency: {type: string}
        totalAmount: {type: string}
~~~

Trong OpenAPI 3.x, `requestBody.content` công bố các **media type request** mà endpoint hỗ trợ; `responses.*.content` công bố **media type response**. Đây là mặt hợp đồng tương ứng với `consumes`/`produces`. Header `Accept` và `Content-Type` là phần của HTTP negotiation; không cần thêm chúng như các parameter thông thường chỉ để mô tả JSON.

Tài liệu không tự cài converter hoặc bảo đảm Spring trả status mong muốn: cần test controller thật, đặc biệt `406/415`. Đừng tuyên bố hỗ trợ `application/xml` trong OpenAPI khi runtime chỉ có JSON converter; các lỗi có thể trả `application/problem+json` **khi client chấp nhận được**, hoặc không có body theo policy.

## 10. Kiểm thử với Spring MockMvc

Ví dụ assertion dưới đây giả định `@WebMvcTest` hoặc integration test đã bật Spring Security, có `spring-security-test`, mock `OrderService` và thiết lập fixture; đây **không phải test class độc lập**.

~~~java
// Static imports từ MockMvcRequestBuilders, MockMvcResultMatchers,
// SecurityMockMvcRequestPostProcessors.jwt, Mockito, MediaType...

mockMvc.perform(get("/v1/orders/ord_916")
        .with(jwt().authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.read")))
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON));

mockMvc.perform(get("/v1/orders/ord_916")
        .with(jwt().authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.read")))
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isNotAcceptable()); // 406

mockMvc.perform(post("/v1/orders")
        .with(jwt().authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.write")))
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaType.APPLICATION_JSON)
        .content("{\"productId\":\"p_17\",\"quantity\":2}"))
    .andExpect(status().isUnsupportedMediaType()); // 415

mockMvc.perform(post("/v1/orders")
        .with(jwt().authorities(new SimpleGrantedAuthority(
            "SCOPE_orders.write")))
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("{\"productId\":"))
    .andExpect(status().isBadRequest()); // 400
~~~

Các bài test cần thêm: POST hợp lệ → `201` + Location + JSON; GET thiếu Accept → JSON; GET `Accept: application/json;q=0` → `406` nếu không có media range khác; POST vendor `+json` → `415` nếu `consumes` chỉ nhận JSON thường; POST `Content-Type: application/json` và `Accept: application/xml` → `406` nếu chỉ tạo JSON.

**Quan trọng:** khi kiểm tra `406/415`, assert **service tạo đơn không được gọi** để tránh side effect trước lúc nhận ra không thể đáp ứng content negotiation. Test với auth hợp lệ để không nhầm 401/403 với 406/415. Test body malformed phải dùng `Content-Type` và `Accept` đúng, nếu không request có thể bị chặn trước bước parse.

## 11. Bài thực hành

**Bối cảnh:** Hệ thống có `POST /v1/products` nhận JSON và `GET /v1/products/{id}` trả JSON. Một đối tác muốn gửi YAML, một browser gửi `Accept: text/html`, client khác gửi JSON có field sai kiểu. Nhóm API dự định bổ sung vendor JSON `application/vnd.example.product+json`.

**Nhiệm vụ:**

1. Thiết kế controller Spring với `consumes=application/json` và `produces=application/json`; POST tạo resource trả `201 Location`.
2. Viết bốn request HTTP: JSON hợp lệ, `Content-Type: text/plain`, `Accept: application/xml` và JSON malformed; dự đoán **201/415/406/400** khi xác thực hợp lệ.
3. Giải thích tại sao có Jackson JSON converter không đồng nghĩa `consumes=application/json` nhận mọi `*+json`, và tại sao `produces=application/xml` chưa đủ để ghi XML.
4. Thêm vendor JSON có chủ đích: điều chỉnh mapping, converter/test và OpenAPI cho đúng contract; kiểm tra response khi `Accept: */*`.
5. Viết ít nhất tám MockMvc cases, gồm body rỗng, `q=0`, thiếu Accept, 401/403 và kiểm tra service **không chạy khi 406/415**.
6. Đề xuất chính sách Problem Details, `Vary: Accept` nếu có nhiều representation, cùng biện pháp bảo vệ đầu vào và tenant.

**Gợi ý:** Chỉ đổi `Accept` thành XML không làm server tự có XML converter. Không dùng 415 cho lỗi JSON malformed, cũng không dùng 406 vì request Content-Type sai. Đầu ra phải đúng với kiểu thực sự serialize và chỉ xuất hiện sau khi authorization/validation thành công.

## 12. Ghi nhớ

- `Content-Type` mô tả body **đang gửi**, `Accept` mô tả response **muốn nhận**.
- `consumes` xét media type đầu vào; `produces` xét khả năng response. Converter chịu trách nhiệm biến bytes ↔ object.
- **415** cho request media type không hỗ trợ; **406** cho response không thể đáp ứng Accept; **400** cho body không đọc được dù media type đúng.
- Annotation không thay serializer, authorization, validation, cache policy hay OpenAPI contract.
- Kiểm thử 406/415 cùng request hợp lệ về các mặt còn lại; bảo đảm side effect chưa xảy ra.

Nắm vững các ranh giới này giúp REST API Spring MVC **thương lượng nội dung nhất quán**, chẩn đoán lỗi chính xác và phát triển định dạng mới mà không vô tình phá hợp đồng hoặc mở rộng quyền truy cập.
