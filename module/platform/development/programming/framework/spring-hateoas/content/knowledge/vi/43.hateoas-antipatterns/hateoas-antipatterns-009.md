# Bỏ qua content negotiation

## Mục tiêu

Sau bài này, bạn có thể nhận diện lỗi bỏ qua content negotiation trong REST API Spring HATEOAS, phân biệt vai trò của `Accept` và `Content-Type`, khai báo representation được hỗ trợ bằng `produces` và `consumes`, xử lý HAL, HAL-FORMS và Problem Details theo đúng media type, hiểu phản hồi 406/415, cấu hình cache variation và viết kiểm thử MockMvc để bảo vệ hợp đồng media type.

## 1. Content negotiation là gì?

Content negotiation là quá trình client và server thống nhất representation được trao đổi trong một HTTP request. Cùng một tài nguyên có thể được biểu diễn theo nhiều định dạng. Ví dụ, endpoint order có thể cung cấp HAL JSON cho client cần hypermedia và HAL-FORMS cho client cần khám phá form template.

Client thể hiện định dạng response có thể xử lý bằng request header `Accept`:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
```

Server chọn một representation được endpoint và bộ chuyển đổi nội dung hỗ trợ, sau đó công bố định dạng thực tế bằng response header `Content-Type`:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
```

Content negotiation giúp client biết cách diễn giải body trước khi xử lý các field và link. Đây là một phần của hợp đồng API, không phải chi tiết trình bày có thể bỏ qua.

Trong Spring HATEOAS, bỏ qua negotiation có thể dẫn đến các lỗi như:

- Client yêu cầu HAL nhưng nhận JSON DTO không có `_links`.
- Client yêu cầu HAL-FORMS nhưng server trả HAL JSON.
- Client gửi request body bằng media type không được endpoint chấp nhận.
- Cache dùng nhầm representation giữa các request có `Accept` khác nhau.
- Tài liệu API công bố một media type nhưng runtime lại trả định dạng khác.

## 2. Phân biệt Accept và Content-Type

Hai header này mô tả hai hướng khác nhau của trao đổi HTTP:

| Header | Nằm ở đâu? | Ý nghĩa |
|---|---|---|
| `Accept` | Request | Client cho biết các media type response mà nó có thể xử lý |
| `Content-Type` | Request hoặc response | Media type của body đang được gửi |

Ví dụ client gửi JSON để tạo order và muốn nhận HAL:

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": "customer-7",
  "note": "Giao sau 17 giờ"
}
```

Server nhận body `application/json`, xử lý dữ liệu rồi trả response `application/hal+json`. Không có yêu cầu hai header phải cùng giá trị.

Một anti-pattern phổ biến là chỉ nhìn `Content-Type` của request rồi dùng nó để quyết định định dạng response. Cách đó bỏ qua `Accept`, khiến client không thể yêu cầu representation mà nó hỗ trợ.

Một lỗi khác là dùng `Accept` để mô tả định dạng body gửi lên. Nếu client gửi JSON, header mô tả body đó phải là `Content-Type: application/json`.

## 3. Media type là một phần của hợp đồng hypermedia

JSON chỉ mô tả cú pháp dữ liệu. Media type cho biết cách diễn giải representation và các quy ước được áp dụng.

Các media type thường gặp trong Spring HATEOAS:

| Media type | Mục đích | Đặc điểm |
|---|---|---|
| `application/hal+json` | HAL JSON | Links trong `_links`, tài nguyên nhúng trong `_embedded` |
| `application/prs.hal-forms+json` | HAL-FORMS | HAL links và form templates trong `_templates` |
| `application/json` | JSON thông thường | Data properties theo schema ứng dụng |
| `application/problem+json` | Problem Details | Mô tả lỗi theo RFC 9457 |
| `application/vnd.acme.order-v2+json` | Vendor-specific representation | Hợp đồng riêng do API định nghĩa |

Ví dụ hai body đều là JSON nhưng không cùng hợp đồng:

**JSON thông thường**

```json
{
  "id": "order-42",
  "status": "PENDING"
}
```

**HAL JSON**

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "cancel": {
      "href": "/orders/42/cancel"
    }
  }
}
```

Nếu endpoint được tài liệu hóa là HAL, client có quyền mong đợi cấu trúc HAL khi server trả `application/hal+json`. Trả JSON thuần nhưng gắn nhãn HAL là vi phạm hợp đồng; trả HAL nhưng gắn nhãn `application/json` cũng khiến client và công cụ trung gian không thể dựa vào metadata chính xác.

Đừng chỉ kiểm tra body parse được thành JSON. Hãy kiểm tra `Content-Type` và cấu trúc hypermedia cùng nhau.

## 4. Anti-pattern: luôn trả một media type bất kể Accept

Một controller có thể ép response về `application/hal+json`:

```java
@GetMapping("/orders/{id}")
public ResponseEntity<OrderModel> getOrder(@PathVariable UUID id) {
    OrderModel model = assembler.toModel(orderService.getRequired(id));

    return ResponseEntity.ok()
            .contentType(MediaTypes.HAL_JSON)
            .body(model);
}
```

Cách này bỏ qua `Accept`. Nếu client chỉ chấp nhận `application/problem+json`, XML hoặc một representation khác mà endpoint không cung cấp, server vẫn cố trả HAL. Client có thể không đọc được body dù request đã khai báo khả năng hỗ trợ.

Khi endpoint chỉ hỗ trợ một media type, hãy công bố điều đó bằng `produces` và để Spring MVC thực hiện mapping theo `Accept`. Khi endpoint hỗ trợ nhiều media type, chỉ khai báo những format mà converter thực sự có thể ghi.

Không tự đặt `Content-Type` tùy ý để che giấu việc converter chưa hỗ trợ media type đó.

## 5. Khai báo response media type bằng produces

`produces` xác định media type response mà handler hỗ trợ. Spring MVC dùng điều kiện này khi chọn handler dựa trên `Accept`.

Ví dụ endpoint chỉ trả HAL JSON:

```java
import java.util.UUID;

import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(
            value = "/orders/{id}",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public OrderModel getOrder(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }
}
```

Client yêu cầu `application/hal+json` sẽ được xử lý bởi handler phù hợp. Nếu client yêu cầu `application/xml` trong khi endpoint chỉ hỗ trợ HAL, Spring MVC thường trả 406 Not Acceptable.

`produces` làm rõ hợp đồng ngay tại mapping, dễ đọc và dễ kiểm thử. Tuy vậy, annotation không tự tạo converter. Ứng dụng vẫn cần cấu hình Spring HATEOAS và message converter tương ứng.

Nếu endpoint thực sự hỗ trợ cả HAL và HAL-FORMS, có thể khai báo:

```java
@GetMapping(
        value = "/orders/{id}",
        produces = {
                MediaTypes.HAL_JSON_VALUE,
                MediaTypes.HAL_FORMS_JSON_VALUE
        }
)
public OrderModel getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Ví dụ trên chỉ đúng khi ứng dụng đã đăng ký hypermedia support và converter có thể serialize model thành từng format được công bố. Hãy xác minh bằng integration test cho mỗi `Accept` được hỗ trợ. Đừng thêm media type vào mảng `produces` chỉ để tài liệu trông phong phú hơn.

## 6. Khai báo request media type bằng consumes

`consumes` xác định media type của request body mà handler chấp nhận. Ví dụ endpoint nhận JSON và trả HAL:

```java
import jakarta.validation.Valid;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
        value = "/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<OrderModel> createOrder(
        @Valid @RequestBody CreateOrderRequest request) {

    Order created = orderService.create(request);
    OrderModel model = assembler.toModel(created);

    return ResponseEntity
            .created(model.getRequiredLink(IanaLinkRelations.SELF).toUri())
            .body(model);
}
```

Ví dụ giả định các lớp `Order`, `OrderModel`, `OrderModelAssembler`, `OrderService` và `CreateOrderRequest` đã được định nghĩa. `consumes` giới hạn định dạng body đầu vào; `produces` giới hạn định dạng body đầu ra.

Nếu client gửi `Content-Type: text/plain`, handler không chấp nhận body đó và Spring MVC thường trả 415 Unsupported Media Type.

Đừng bỏ `consumes` khi endpoint có hợp đồng request body rõ ràng và ứng dụng cần từ chối media type ngoài dự kiến. Tuy nhiên, cũng đừng khai báo quá hẹp nếu API thực sự hỗ trợ nhiều định dạng đầu vào, ví dụ JSON và vendor JSON media type.

## 7. Đọc quality factor trong Accept

Client có thể gửi nhiều media type kèm quality factor `q` để thể hiện mức ưu tiên:

```http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json;q=1.0, application/hal+json;q=0.8
```

Giá trị `q` nằm trong khoảng từ 0 đến 1. Giá trị cao hơn thể hiện mức ưu tiên cao hơn. `q=0` có nghĩa client không chấp nhận media type đó.

Ví dụ:

```http
Accept: application/hal+json;q=0.9, application/json;q=0.5
```

Client ưu tiên HAL JSON hơn JSON thông thường. Nếu server hỗ trợ cả hai, negotiation có thể chọn HAL theo mức ưu tiên đó, miễn là mapping và converter đáp ứng.

Các dạng wildcard thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| `*/*` | Chấp nhận mọi media type |
| `application/*` | Chấp nhận mọi subtype trong nhóm application |
| `application/hal+json` | Chỉ định cụ thể HAL JSON |
| `application/hal+json;q=0` | Không chấp nhận HAL JSON |

Khi `Accept` bị bỏ qua, HTTP mặc định xem client không đưa ra giới hạn định dạng cụ thể; trong nhiều trường hợp, request tương đương chấp nhận mọi media type. Server sẽ chọn representation mặc định theo mapping và cấu hình của nó. Nếu client cần một format cụ thể, nên gửi `Accept` rõ ràng.

Không tự parse chuỗi `Accept` bằng `contains("hal")` hoặc so sánh chuỗi thủ công. Header có thể chứa nhiều media type, wildcard, parameter và quality factor. Hãy để Spring MVC và `ContentNegotiationManager` xử lý quy tắc HTTP.

## 8. Cấu hình hypermedia format thực sự được hỗ trợ

Spring HATEOAS cung cấp cấu hình cho các hypermedia format. Ví dụ đăng ký HAL và HAL-FORMS:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = {
        HypermediaType.HAL,
        HypermediaType.HAL_FORMS
})
public class HypermediaConfiguration {
}
```

Trong ứng dụng Spring Boot, một số cấu hình HAL có thể đã được auto-configuration đăng ký. Hãy kiểm tra cấu hình thực tế và phiên bản Spring HATEOAS trước khi thêm cấu hình tường minh để tránh đăng ký converter trùng lặp.

Nguyên tắc cần nhớ:

- `produces` công bố media type mà handler hỗ trợ.
- Hypermedia configuration đăng ký format và converter cần thiết.
- Representation model phải chứa đúng metadata cho format được chọn.
- Response `Content-Type` phải khớp format thực tế được serialize.

Một endpoint không thực sự hỗ trợ HAL-FORMS thì không nên quảng bá `application/prs.hal-forms+json`. Nếu model không có affordance hoặc template, response có thể không mang lại khả năng mà client HAL-FORMS kỳ vọng.

## 9. Phân biệt 406 và 415

Hai lỗi negotiation thường bị nhầm:

| Status | Nguyên nhân | Header cần xem |
|---|---|---|
| 406 Not Acceptable | Server không thể cung cấp response representation phù hợp với `Accept` | `Accept` |
| 415 Unsupported Media Type | Server không chấp nhận media type của request body | `Content-Type` |

Ví dụ 406:

```http
GET /orders/42 HTTP/1.1
Accept: application/xml
```

Nếu endpoint chỉ cung cấp HAL JSON, Spring MVC thường không tìm được handler/converter phù hợp và trả 406.

Ví dụ 415:

```http
POST /orders HTTP/1.1
Content-Type: text/plain
Accept: application/hal+json

order-42
```

Endpoint chỉ nhận `application/json`, nên request body `text/plain` không phù hợp.

Đừng trả 400 cho mọi lỗi negotiation. 400 mô tả request không hợp lệ nói chung; 406 và 415 chỉ ra cụ thể vấn đề lựa chọn representation hoặc media type body.

Hành vi lỗi cuối cùng còn phụ thuộc cấu hình exception handling, message converter và security filter. Nếu API chuẩn hóa lỗi bằng Problem Details, hãy kiểm thử cả status lẫn error body thực tế.

## 10. Problem Details cũng cần content negotiation rõ ràng

API HATEOAS thường trả HAL cho thành công và Problem Details cho lỗi. Đây là hai loại representation khác nhau:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Đơn hàng được yêu cầu không tồn tại."
}
```

Đừng gắn `application/hal+json` cho Problem Details chỉ vì toàn bộ API sử dụng Spring HATEOAS. `application/problem+json` là media type riêng với schema riêng.

Cần quyết định và tài liệu hóa cách API trả lỗi khi request có `Accept: application/hal+json` nhưng lỗi được biểu diễn bằng `application/problem+json`. Tùy cấu hình, ứng dụng có thể chủ động phát Problem Details như error format đã định nghĩa, hoặc negotiation có thể khiến body lỗi không được trả như dự kiến. Không giả định `@RestControllerAdvice` tự xử lý mọi trường hợp, đặc biệt lỗi từ Spring Security filter chain.

Các test nên xác nhận:

- HTTP status đúng.
- `Content-Type` của error response đúng với hợp đồng.
- Body có `type`, `title`, `status`, `detail` cần thiết.
- `status` trong body khớp HTTP status.
- Error handler không làm mất các header HTTP quan trọng như `WWW-Authenticate` đối với 401.

## 11. Không dùng query parameter để thay thế Accept

Một số API dùng query parameter như `?format=hal` hoặc `?format=json` để chọn response. Cách này có thể tồn tại trong một hệ thống legacy, nhưng nếu dùng làm cơ chế duy nhất thì nó bỏ qua content negotiation chuẩn của HTTP.

Ví dụ cách làm dễ tạo hai nguồn sự thật:

```http
GET /orders/42?format=hal
Accept: application/json
```

Client gửi `Accept: application/json` nhưng query parameter lại yêu cầu HAL. Server có thể không biết header hay query parameter được ưu tiên. Cache cũng phải tính đến query string và cấu hình cache key chính xác.

Nếu API cần hỗ trợ query parameter vì lý do tương thích, hãy định nghĩa rõ precedence, giá trị mặc định, status lỗi và tác động đến cache. Với API mới, ưu tiên dùng `Accept` để thương lượng response media type.

Tương tự, đừng dùng phần mở rộng `.json` hoặc `.hal` trong URI làm cơ chế duy nhất nếu API đã có thể dùng header negotiation. URI nên định danh tài nguyên; `Accept` lựa chọn representation của tài nguyên đó.

## 12. Không nhầm versioning với content negotiation

Một media type có thể mang vendor-specific version:

```http
Accept: application/vnd.acme.order-v2+json
```

Đây là một chiến lược versioning qua media type. Tuy nhiên, không phải mọi media type đều là version. `application/hal+json` xác định format HAL; nó không có nghĩa API đang ở version 1.

Nếu API version bằng URI (`/v1/orders`) nhưng format là HAL, request có thể là:

```http
GET /v1/orders/42 HTTP/1.1
Accept: application/hal+json
```

Version nằm trong URI, representation format nằm trong `Accept`. Tài liệu phải mô tả rõ hai khái niệm để client không suy diễn version từ media type.

Nếu response thay đổi theo vendor media type được gửi trong `Accept`, cache cần phân biệt các variant theo `Vary: Accept`.

## 13. Vary: Accept và cache

Khi cùng một URI có thể trả HAL hoặc HAL-FORMS tùy `Accept`, response cần công bố `Vary: Accept` để cache biết response phụ thuộc request header đó.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Vary: Accept
```

Nếu thiếu `Vary: Accept`, shared cache có thể lưu HAL response rồi trả lại cho request khác yêu cầu HAL-FORMS, hoặc ngược lại.

Trong Spring MVC, có thể thêm header qua `ResponseEntity`:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

return ResponseEntity.ok()
        .varyBy(HttpHeaders.ACCEPT)
        .body(model);
```

Chỉ thêm header thực sự ảnh hưởng lựa chọn representation. Nếu response còn phụ thuộc `Accept-Language` hoặc một header version, hãy đưa các header đó vào `Vary` theo đúng thiết kế.

`Vary` không thay thế chính sách bảo mật cache. Representation phụ thuộc người dùng vẫn cần `Cache-Control: private` hoặc `no-store` theo yêu cầu bảo mật. Không dùng `Vary: Authorization` như giải pháp duy nhất để bảo vệ dữ liệu cá nhân.

## 14. Content negotiation trong kiểm thử MockMvc

Kiểm thử phải xác nhận cả request header, status, response `Content-Type` và cấu trúc body. Ví dụ test endpoint trả HAL:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@Test
void returnsHalWhenClientAcceptsHal() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists());
}
```

Test client yêu cầu XML:

```java
import org.springframework.http.MediaType;

@Test
void rejectsUnsupportedAcceptHeader() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
}
```

Test request body có media type sai:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void rejectsUnsupportedRequestContentType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaTypes.HAL_JSON)
                    .content("order-42"))
            .andExpect(status().isUnsupportedMediaType());
}
```

Các ví dụ giả định controller khai báo `produces`/`consumes`, converter đã được cấu hình và test context có service/assembler cần thiết. Nếu exception advice chuyển 406 hoặc 415 thành Problem Details, test nên bổ sung assertion về `Content-Type` và các member của Problem Details.

## 15. Kiểm thử nhiều media type và quality factor

Nếu endpoint công bố HAL và HAL-FORMS, hãy kiểm tra từng representation được chấp nhận:

```java
@Test
void returnsHalFormsWhenClientRequestsHalForms() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_FORMS_JSON));
}
```

Có thể kiểm tra lựa chọn theo quality factor bằng cách gửi nhiều media type:

```java
import org.springframework.http.HttpHeaders;

@Test
void honorsClientMediaTypePreference() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .header(
                            HttpHeaders.ACCEPT,
                            "application/prs.hal-forms+json;q=1.0, "
                                    + "application/hal+json;q=0.5"
                    ))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_FORMS_JSON));
}
```

Test quality factor chỉ có ý nghĩa khi cả hai format thực sự được hỗ trợ, converter và mapping đều được cấu hình, và không có server-side preference khác làm thay đổi kết quả. Hãy xem response thực tế là bằng chứng, không suy luận từ annotation.

Nếu endpoint chỉ hỗ trợ HAL, một request `Accept` chứa HAL-FORMS với `q=1.0` và HAL với `q=0.5` có thể chọn HAL vì đó là lựa chọn được hỗ trợ có chất lượng phù hợp. Nếu mọi media type được hỗ trợ đều bị loại bởi `q=0`, request không có representation phù hợp.

## 16. Kiểm thử response header và cấu trúc nhất quán

Một contract test tốt không chỉ xác nhận response có status 200. Hãy xác nhận:

- `Content-Type` đúng media type đã yêu cầu hoặc được thương lượng.
- Body tuân theo cấu trúc của media type đó.
- HAL response có `_links` theo hợp đồng.
- HAL-FORMS response có `_templates` khi API công bố affordance tương ứng.
- `Vary: Accept` có mặt khi representation phụ thuộc `Accept`.
- Lỗi 406/415 có status và error representation phù hợp với chính sách API.

Ví dụ:

```java
import org.springframework.http.HttpHeaders;

mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string(
            HttpHeaders.VARY,
            org.hamcrest.Matchers.containsString("Accept")
    ))
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu response có thể chứa links tùy theo quyền, test thêm các principal khác nhau và xác nhận link tương ứng chỉ xuất hiện đúng ngữ cảnh. Content negotiation và authorization là hai phần độc lập của hợp đồng.

## 17. Những lỗi thường gặp khi bỏ qua negotiation

**Luôn trả `application/hal+json`.** Server bỏ qua `Accept`. Dùng `produces` và chỉ công bố format được hỗ trợ.

**Dùng `Accept` để mô tả request body.** Server không kiểm tra đúng media type đầu vào. Dùng `Content-Type` và `consumes`.

**Gắn nhãn HAL cho JSON thuần.** Client tìm `_links` nhưng không có. Kiểm tra cả `Content-Type` và body.

**Công bố HAL-FORMS nhưng không có converter.** Runtime không thể serialize format đã cam kết. Kiểm thử converter trong ứng dụng thực.

**Parse `Accept` bằng chuỗi con.** Bỏ qua wildcard, quality factor và parameters. Dùng content negotiation của Spring MVC.

**Trả 400 cho cả 406 và 415.** Client mất thông tin nguyên nhân. Trả status phù hợp với negotiation failure.

**Chỉ kiểm tra response body parse được.** JSON hợp lệ vẫn có thể sai media type hoặc thiếu hypermedia semantics. Kiểm tra header và cấu trúc.

**Không công bố `Vary: Accept`.** Cache có thể trả HAL cho request HAL-FORMS hoặc ngược lại. Đánh dấu header làm thay đổi response variant.

**Dùng query parameter để chọn format mà không có quy tắc ưu tiên.** Header và query có thể mâu thuẫn. Ưu tiên negotiation theo HTTP hoặc tài liệu hóa rõ cơ chế legacy.

**Nhầm format với version.** Client gửi sai media type khi API version nằm trong URI. Tài liệu hóa riêng version và representation format.

**Cho rằng mọi lỗi đều đi qua `@RestControllerAdvice`.** Security filter hoặc lỗi negotiation có thể phát sinh ngoài controller. Kiểm thử toàn bộ filter chain và exception handling.

## 18. Nguyên tắc thiết kế

- Dùng `Accept` để thương lượng response representation.
- Dùng `Content-Type` để mô tả request body đang gửi.
- Dùng `produces` và `consumes` để công bố media type của handler.
- Chỉ khai báo HAL, HAL-FORMS hoặc vendor media type khi converter thực sự hỗ trợ.
- Tôn trọng wildcard và quality factor; không tự parse `Accept` bằng chuỗi con.
- Phân biệt 406 với 415.
- Trả đúng `Content-Type` cho HAL, HAL-FORMS và Problem Details.
- Xác định chính sách error representation khi negotiation thất bại.
- Thêm `Vary: Accept` khi cùng URI trả nhiều representation theo `Accept`.
- Không nhầm API version với media type.
- Kiểm thử status, response header, cấu trúc body và cache variation bằng MockMvc/integration test.
- Giữ tài liệu OpenAPI đồng bộ với behavior runtime.

## Kết luận

Bỏ qua content negotiation khiến client không thể tin cậy vào media type để diễn giải representation và có thể nhận sai định dạng dù request đã khai báo rõ khả năng hỗ trợ. Trong Spring HATEOAS, hãy phân biệt `Accept` với `Content-Type`, dùng `produces` và `consumes`, cấu hình converter cho HAL hoặc HAL-FORMS, xử lý 406/415 đúng nghĩa và công bố `Vary: Accept` khi cần. MockMvc contract tests phải kiểm tra cả response header lẫn cấu trúc hypermedia để bảo đảm tài liệu và runtime luôn khớp nhau.

## Tài liệu tham khảo

- [Spring Framework Reference – Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework Reference – Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring HATEOAS Reference – Hypermedia formats](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring HATEOAS API – MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [RFC 9110 – HTTP Semantics, Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#section-12)
- [RFC 9110 – 406 Not Acceptable](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.7)
- [RFC 9110 – 415 Unsupported Media Type](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.16)
- [RFC 9111 – HTTP Caching, Vary](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1)

