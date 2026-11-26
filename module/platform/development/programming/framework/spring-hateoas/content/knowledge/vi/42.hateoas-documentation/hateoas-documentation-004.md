# Tài liệu media type

## Mục tiêu

Sau bài này, bạn có thể lập tài liệu media type cho REST API dùng Spring HATEOAS, mô tả representation mà endpoint cung cấp và chấp nhận, phân biệt HAL, HAL-FORMS, JSON thông thường và Problem Details, giải thích content negotiation qua `Accept` và `Content-Type`, công bố profile và link metadata, đồng thời viết ví dụ OpenAPI và kiểm thử hợp đồng media type bằng MockMvc.

## 1. Vì sao media type cần được tài liệu hóa?

Media type cho client biết cách diễn giải nội dung HTTP body. Một response JSON thông thường và một response HAL đều có thể được parse thành JSON object, nhưng cấu trúc và semantics của chúng khác nhau.

Ví dụ JSON thông thường:

```json
{
  "id": "order-42",
  "status": "PENDING"
}
```

Representation HAL:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "collection": {
      "href": "/orders"
    }
  }
}
```

Nếu server trả HAL nhưng tài liệu chỉ nói endpoint trả `application/json`, client có thể không biết `_links` là thành phần hợp đồng và không biết phải theo relation nào. Ngược lại, nếu tài liệu mô tả HAL nhưng server thực tế trả JSON thuần, client có thể tìm `_links` và thất bại.

Tài liệu media type cần trả lời được:

- Endpoint trả representation nào?
- Client có thể yêu cầu representation đó bằng `Accept` nào?
- Request body được gửi bằng media type nào?
- Response `Content-Type` thực tế là gì?
- Body tuân theo cấu trúc HAL, HAL-FORMS hay schema JSON riêng?
- Link relation, affordance và profile nào được công bố?
- Server phản hồi thế nào khi client gửi media type không hỗ trợ?
- Các phiên bản client có thể dựa vào media type nào để phân biệt representation?

Với Spring HATEOAS, media type là một phần của hợp đồng hypermedia. Tài liệu phải mô tả cả cấu trúc body lẫn cách client khám phá tài nguyên và hành động.

## 2. Phân biệt media type, Accept và Content-Type

Ba khái niệm thường xuất hiện cùng nhau nhưng có vai trò khác nhau.

| Khái niệm | Vị trí | Ý nghĩa |
|---|---|---|
| Media type | Hợp đồng định dạng | Tên loại nội dung như `application/hal+json` |
| `Accept` | Request header | Client khai báo các media type response có thể xử lý |
| `Content-Type` | Request hoặc response header | Media type của body đang được gửi |

Ví dụ client yêu cầu representation HAL:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
```

Server trả:

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

Ở đây, `Accept` nói client muốn nhận HAL; `Content-Type` xác nhận server thực sự trả HAL.

Với request tạo đơn hàng, body có thể là JSON thông thường trong khi response là HAL:

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": "customer-7",
  "note": "Giao sau 17 giờ"
}
```

Hai header mô tả hai hướng khác nhau:

- `Content-Type: application/json` mô tả body request client gửi.
- `Accept: application/hal+json` mô tả response client muốn nhận.

Không nên ghi một media type chung cho cả request và response nếu hai body có định dạng khác nhau.

## 3. Các media type thường gặp trong API Spring HATEOAS

Một API có thể sử dụng nhiều media type tùy loại representation.

| Media type | Mục đích | Cấu trúc nổi bật |
|---|---|---|
| `application/hal+json` | Hypermedia JSON theo HAL | `_links`, `_embedded` |
| `application/prs.hal-forms+json` | Hypermedia JSON có form template theo HAL-FORMS | `_links`, `_templates` |
| `application/json` | JSON thông thường, thường dùng cho request DTO hoặc dữ liệu không hypermedia | Các field theo schema API |
| `application/problem+json` | Problem Details cho HTTP API errors | `type`, `title`, `status`, `detail`, `instance` |
| `application/vnd.acme.order-v2+json` | Ví dụ vendor-specific media type do API định nghĩa | Phụ thuộc hợp đồng riêng |

Trong Spring HATEOAS, có thể dùng các hằng số:

- `MediaTypes.HAL_JSON` và `MediaTypes.HAL_JSON_VALUE`.
- `MediaTypes.HAL_FORMS_JSON` và `MediaTypes.HAL_FORMS_JSON_VALUE`.

Với Problem Details, Spring Framework cung cấp `MediaType.APPLICATION_PROBLEM_JSON`.

Không nên coi mọi JSON là cùng một representation. Media type phải mô tả semantics và cấu trúc mà client cần hiểu, không chỉ mô tả cú pháp serialization.

## 4. Tài liệu HAL representation

HAL định nghĩa quy ước để biểu diễn links và embedded resources trong JSON. Hai khu vực quan trọng là:

- `_links`: các link relation dẫn đến tài nguyên hoặc khả năng khác.
- `_embedded`: tài nguyên được nhúng trong representation hiện tại.

Ví dụ tài liệu một order resource:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "collection": {
      "href": "/orders"
    },
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel"
    }
  }
}
```

Khi mô tả representation này, tài liệu cần nêu:

1. Media type response là `application/hal+json`.
2. `id`, `status` và `total` là data properties của order.
3. `self` dẫn đến chính order hiện tại.
4. `collection` dẫn đến tập order.
5. Relation extension `https://api.example.com/rels/cancel` mô tả khả năng hủy đơn hàng khi link xuất hiện.
6. Link `cancel` có thể vắng mặt khi trạng thái hoặc quyền của principal không cho phép.

Không chỉ liệt kê tên relation. Cần mô tả semantics, target, phương thức HTTP nếu client cần thực hiện thao tác, điều kiện xuất hiện và response dự kiến.

### 4.1. Mô tả `_embedded`

Collection HAL có thể nhúng các item:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "/orders/order-42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders"
    },
    "next": {
      "href": "/orders?page=1"
    }
  }
}
```

Tài liệu cần định nghĩa relation `orders` dùng trong `_embedded`, schema của item, links có trên mỗi item và cách pagination hoạt động. Đừng giả định tên embedded relation luôn giống tên Java class hoặc tên repository.

### 4.2. Mô tả link metadata

Một HAL link có thể chứa metadata ngoài `href`, ví dụ `type`, `title`, `hreflang`, `templated` hoặc `deprecation` tùy quy ước và thư viện.

Ví dụ:

```json
{
  "_links": {
    "invoice": {
      "href": "/orders/order-42/invoice",
      "type": "application/pdf",
      "title": "Hóa đơn PDF"
    }
  }
}
```

`type` trên link là gợi ý media type của target. Nó không phải `Content-Type` của response hiện tại và cũng không chứng minh target thực tế luôn trả PDF. Tài liệu nên mô tả media type target hỗ trợ và client cần xác nhận `Content-Type` khi gọi link.

## 5. Tài liệu HAL-FORMS representation

HAL-FORMS mở rộng cách mô tả hypermedia bằng form templates. Client có thể khám phá các trường và phương thức cần dùng để gửi một request.

Ví dụ representation có template cập nhật order:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    }
  },
  "_templates": {
    "default": {
      "title": "Cập nhật đơn hàng",
      "method": "PATCH",
      "contentType": "application/merge-patch+json",
      "properties": [
        {
          "name": "note",
          "prompt": "Ghi chú giao hàng",
          "required": false
        }
      ]
    }
  }
}
```

Khi tài liệu hóa HAL-FORMS, hãy mô tả:

- Response media type là `application/prs.hal-forms+json`.
- Tên template như `default` có ý nghĩa gì.
- `method` là phương thức HTTP client phải gửi.
- `contentType` là media type của request body được tạo từ template.
- Mỗi property có `name`, `prompt`, `required`, kiểu dữ liệu và validation rules nào.
- Điều kiện template xuất hiện hoặc bị ẩn.
- Response thành công hoặc lỗi sau khi submit.

Đừng giả định mọi HAL-FORMS representation đều có `_templates`. Template chỉ xuất hiện khi API công bố affordance tương ứng. Nếu client chỉ nhận HAL JSON, không nên yêu cầu nó tìm `_templates`.

## 6. Khai báo media type trong Spring MVC

Spring MVC cho phép mô tả media type response bằng `produces` và media type request body bằng `consumes`.

Ví dụ endpoint trả HAL:

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

`produces` giúp Spring chọn handler phù hợp với `Accept`. Nó cũng thể hiện rõ trong source code rằng endpoint cam kết trả HAL JSON.

Ví dụ endpoint nhận JSON và trả HAL:

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

Ví dụ giả định `OrderModel`, `OrderModelAssembler`, `OrderService` và `CreateOrderRequest` đã được định nghĩa. `consumes` và `produces` mô tả hai phần body độc lập của request/response.

Nếu một endpoint hỗ trợ nhiều representation, có thể khai báo nhiều media type:

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

Mapping nhiều `produces` chỉ đúng khi ứng dụng thực sự có converter và cấu hình hypermedia để ghi từng media type. Đừng công bố HAL-FORMS chỉ vì đã thêm hằng số vào annotation.

## 7. Cấu hình hỗ trợ hypermedia formats

Spring HATEOAS có cơ chế đăng ký hỗ trợ các hypermedia format. Một cấu hình tường minh có thể như sau:

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

Cấu hình thực tế phụ thuộc phiên bản Spring Boot, Spring HATEOAS và các message converter được đăng ký. Một số ứng dụng Boot đã tự cấu hình HAL. Trước khi thêm `@EnableHypermediaSupport`, hãy xác định những converter đang hoạt động để tránh cấu hình trùng hoặc xung đột.

Tài liệu API nên ghi rõ format nào được hỗ trợ trong môi trường triển khai. Annotation trong controller không đủ để chứng minh converter có thể serialize representation thành media type đó.

## 8. Content negotiation và các kết quả có thể xảy ra

Client có thể gửi nhiều media type trong `Accept`, kèm quality factor:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json, application/prs.hal-forms+json;q=0.8
```

Server chọn một representation mà endpoint và converter cùng hỗ trợ, theo quy tắc content negotiation. Tài liệu cần mô tả:

- Media type mặc định nếu client không gửi `Accept` hoặc gửi `*/*`.
- Các media type được hỗ trợ và thứ tự ưu tiên nếu API có quy tắc cụ thể.
- Hành vi khi không có representation phù hợp.
- Các request header làm thay đổi response variant.

Nếu client yêu cầu XML trong khi endpoint chỉ cung cấp HAL, server thường trả `406 Not Acceptable`.

```http
GET /orders/42 HTTP/1.1
Accept: application/xml
```

Nếu endpoint chỉ nhận JSON nhưng client gửi body `text/plain`, server thường trả `415 Unsupported Media Type`.

```http
POST /orders HTTP/1.1
Content-Type: text/plain
Accept: application/hal+json

order-42
```

Tài liệu cần phân biệt rõ:

| Status | Nguyên nhân |
|---|---|
| 406 Not Acceptable | Server không cung cấp representation phù hợp với `Accept` |
| 415 Unsupported Media Type | Server không chấp nhận media type của request body qua `Content-Type` |

Nếu API chuẩn hóa lỗi bằng Problem Details, hãy mô tả cả error media type `application/problem+json` và cách nó được thương lượng khi request `Accept` chỉ liệt kê HAL. Không nên hứa rằng mọi lỗi đều trả Problem Details nếu error negotiation hoặc security filter chưa được cấu hình để làm điều đó.

## 9. Profile và semantics của representation

Media type mô tả định dạng representation; profile có thể mô tả thêm semantics hoặc quy ước áp dụng cho representation đó.

RFC 6906 định nghĩa link relation `profile` và cách dùng profile để chỉ ra một profile URI. Ví dụ response có thể công bố profile qua HTTP Link header:

```http
Content-Type: application/hal+json
Link: <https://api.example.com/profiles/order>; rel="profile"
```

Profile có thể định nghĩa:

- Ý nghĩa của các data properties.
- Relation vocabulary mà API sử dụng.
- Các quy tắc xử lý links và embedded resources.
- Các trạng thái hoặc affordances có thể xuất hiện.
- Những ràng buộc bổ sung của representation.

Profile không thay thế media type. `application/hal+json` vẫn mô tả cú pháp và quy ước HAL; profile URI bổ sung ngữ nghĩa của domain order.

Một số hệ thống dùng tham số `profile` trên media type theo RFC 6906. Chỉ công bố dạng này nếu server, converter, proxy và client thực sự hỗ trợ cách thương lượng đó. Nếu không, dùng Link header `rel="profile"` là cách công bố rõ ràng mà không tự tạo biến thể media type chưa được xử lý.

Client không hiểu profile cần có hành vi fallback an toàn. Tài liệu profile nên có URI ổn định, nội dung có thể truy cập và quy tắc tương thích khi profile được mở rộng.

## 10. Vendor-specific media type và versioning

Một API có thể định nghĩa media type riêng để biểu thị representation theo domain hoặc phiên bản:

```http
Accept: application/vnd.acme.order-v2+json
```

Nếu chọn cách này, tài liệu cần xác định:

- Tên media type chính xác và cách đăng ký hoặc quản lý vocabulary.
- Cấu trúc body và semantics của từng field.
- Hypermedia format nền tảng có phải HAL hay không.
- Converter nào serialize và deserialize representation.
- Hành vi khi client gửi media type version không được hỗ trợ.
- Cách kết hợp versioning với `Accept`, URI hoặc request header.

Không nên tự đặt vendor media type rồi giả định HAL converter mặc định sẽ nhận diện nó. Converter của Spring HATEOAS thường được cấu hình cho các hypermedia media type đã biết. Media type mới có thể cần converter hoặc cấu hình riêng.

Nếu phiên bản được chọn bằng URI như `/v1/orders` và `/v2/orders`, cả hai endpoint vẫn có thể trả `application/hal+json`. Version nằm trong URI; media type mô tả format. Tài liệu phải làm rõ hai chiều này để client không nhầm version với representation format.

## 11. Công bố media type trong OpenAPI

OpenAPI mô tả media type của request và response trong thuộc tính `content`. Ví dụ rút gọn:

```yaml
paths:
  /orders/{id}:
    get:
      summary: Lấy đơn hàng
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Representation HAL của đơn hàng
          content:
            application/hal+json:
              schema:
                $ref: "#/components/schemas/OrderHal"
              examples:
                pendingOrder:
                  value:
                    id: order-42
                    status: PENDING
                    _links:
                      self:
                        href: /orders/order-42
                      collection:
                        href: /orders
        "404":
          description: Không tìm thấy đơn hàng
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
components:
  schemas:
    OrderHal:
      type: object
      properties:
        id:
          type: string
        status:
          type: string
        _links:
          type: object
          additionalProperties: true
    Problem:
      type: object
      required:
        - type
        - title
        - status
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
```

Đây là ví dụ khung. Schema HAL thực tế cần mô tả rõ link object, embedded relation và extension properties theo API. `additionalProperties: true` giúp ví dụ ngắn nhưng không thay thế schema đủ chi tiết cho client generator hoặc validator.

Với endpoint tạo order, khai báo request và response riêng:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateOrderRequest"
responses:
  "201":
    description: Đã tạo đơn hàng
    headers:
      Location:
        description: URI của tài nguyên vừa tạo
        schema:
          type: string
          format: uri-reference
    content:
      application/hal+json:
        schema:
          $ref: "#/components/schemas/OrderHal"
```

OpenAPI `content` ghi rõ media type cho tooling và client generator. Còn OpenAPI Link Object mô tả mối liên hệ giữa các operation trong tài liệu OpenAPI; nó không thay thế HAL `_links` được server trả về runtime. Tài liệu nên phân biệt hai khái niệm này.

## 12. Tài liệu relation và affordance cùng media type

Media type cho biết cách đọc representation, còn relation và affordance cho biết client có thể điều hướng hoặc thực hiện điều gì.

Với mỗi relation quan trọng, hãy lập bảng:

| Relation | Target | Khi xuất hiện | Ý nghĩa |
|---|---|---|---|
| `self` | Order hiện tại | Khi tài nguyên được trả | Đọc representation của order |
| `collection` | `/orders` | Khi collection có thể khám phá | Truy cập tập order |
| `cancel` | Endpoint hủy order | Khi order còn được phép hủy và principal có quyền | Thực hiện yêu cầu hủy |
| `invoice` | Tài nguyên hóa đơn | Khi hóa đơn đã được phát hành và principal có quyền xem | Tải hoặc xem hóa đơn |

Nếu relation là URI extension, hãy công bố URI relation và tài liệu semantics. Không chỉ ghi một tên ngắn như `cancel` nếu nó có thể gây trùng nghĩa giữa các API.

Nếu API công bố affordance qua HAL-FORMS hoặc metadata khác, tài liệu cần ghi rõ method, request media type, field, validation và điều kiện xuất hiện. Client vẫn phải xử lý status response thực tế vì trạng thái và quyền có thể thay đổi giữa lúc đọc representation và lúc gọi action.

## 13. Ví dụ tài liệu một endpoint hoàn chỉnh

Một mục tài liệu endpoint nên gom thông tin để developer client có thể triển khai mà không phải suy luận.

### GET /orders/{id}

**Mục đích:** Lấy một order và các quan hệ hypermedia hiện có.

**Request headers:**

| Header | Giá trị | Bắt buộc |
|---|---|---|
| `Accept` | `application/hal+json` | Khuyến nghị |
| `Authorization` | Bearer token theo security scheme của API | Theo chính sách endpoint |

**Response 200:**

- `Content-Type: application/hal+json`.
- Body tuân theo HAL.
- `self` luôn trỏ đến order hiện tại.
- `cancel` chỉ xuất hiện khi trạng thái và quyền cho phép.
- `invoice` chỉ xuất hiện khi hóa đơn có sẵn và principal được phép xem.

**Response lỗi:**

| Status | Media type | Ý nghĩa |
|---|---|---|
| 401 | `application/problem+json` | Chưa xác thực |
| 403 | `application/problem+json` | Không đủ quyền |
| 404 | `application/problem+json` | Không tìm thấy order |
| 406 | Theo error negotiation contract | Không hỗ trợ `Accept` được yêu cầu |

**Ví dụ request:**

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
Authorization: Bearer <access-token>
```

**Ví dụ response:**

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "collection": {
      "href": "/orders"
    },
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel"
    }
  }
}
```

**Quy tắc client:** Tìm relation theo tên đã tài liệu hóa; không tự dựng URI từ ID; bỏ qua relation chưa biết; xử lý link tùy chọn có thể không xuất hiện; luôn kiểm tra response khi theo link.

## 14. Tài liệu media type cho client và SDK

Tài liệu dành cho client cần giải thích cả cú pháp lẫn hành vi.

Với mỗi media type, hãy cung cấp:

- Tên media type đầy đủ, gồm suffix và parameter nếu có.
- Vai trò: request body, response body hay cả hai.
- Endpoint hỗ trợ và header cần gửi.
- Schema và ví dụ JSON thực tế.
- Các relation quan trọng cùng semantics.
- Quy tắc embedded resources và pagination.
- Các affordance hoặc template có thể xuất hiện.
- Cách xử lý relation hoặc extension chưa biết.
- Lỗi negotiation như 406 và 415.
- Profile URI, version hoặc vocabulary liên quan.

SDK nên cho phép cấu hình `Accept` rõ ràng và không mặc định mọi response đều là JSON thuần. Nếu SDK chỉ hỗ trợ một media type, tài liệu phải nói rõ giới hạn đó. Nếu client dùng generated model, cần xác định cách xử lý các link và relation mở rộng mà code generator có thể không biết trước.

Không yêu cầu client hard-code URI của từng tài nguyên khi API đã công bố relation để điều hướng. Tài liệu có thể đưa ví dụ URI để minh họa, nhưng phải nói rõ URI thực tế được lấy từ `href` của response.

## 15. Kiểm thử tài liệu media type bằng MockMvc

Tài liệu chỉ có giá trị khi response thực tế khớp với những gì đã công bố. MockMvc có thể kiểm tra mapping, media type và cấu trúc representation.

Ví dụ kiểm tra HAL:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@Test
void documentsAndReturnsHalRepresentation() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").exists())
            .andExpect(jsonPath("$._links.self.href").exists());
}
```

Kiểm tra HAL-FORMS nếu endpoint cam kết hỗ trợ:

```java
@Test
void returnsHalFormsForSupportedAcceptHeader() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_FORMS_JSON));
}
```

Chỉ kiểm tra `_templates` khi fixture và endpoint thực sự công bố form template. Nếu endpoint không có affordance, HAL-FORMS response có thể không chứa `_templates`.

Kiểm tra media type không hỗ trợ:

```java
import org.springframework.http.MediaType;

@Test
void rejectsUnsupportedResponseMediaType() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
}
```

Kiểm tra request body không được hỗ trợ:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void rejectsUnsupportedRequestMediaType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaTypes.HAL_JSON)
                    .content("order-42"))
            .andExpect(status().isUnsupportedMediaType());
}
```

Các test trên giả định controller đã khai báo `produces` và `consumes` đúng, converter tương ứng được đăng ký, và test context có đủ service/assembler. Nếu API chuẩn hóa lỗi 406/415 thành Problem Details, có thể bổ sung assertion `Content-Type` và body theo error contract.

## 16. Kiểm thử media type và cache variation

Nếu cùng URI có thể trả HAL hoặc HAL-FORMS tùy `Accept`, response cần công bố `Vary: Accept` để cache phân biệt các biến thể.

Ví dụ:

```http
Vary: Accept
```

Nếu response còn phụ thuộc header version hoặc ngôn ngữ, `Vary` cần chứa các header đó theo chính sách content negotiation. Với version nằm trong URI path, URI đã phân biệt phiên bản nên không cần thêm header version vào `Vary` chỉ vì path versioning.

Test có thể kiểm tra:

```java
import org.springframework.http.HttpHeaders;

mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string(
            HttpHeaders.VARY,
            org.hamcrest.Matchers.containsString("Accept")
    ));
```

`Vary` chỉ phân biệt cache variant. Nó không thay thế `Cache-Control: private` hoặc `no-store` khi representation phụ thuộc principal hay chứa dữ liệu nhạy cảm.

## 17. Những lỗi thường gặp khi tài liệu hóa media type

**Ghi tất cả response là `application/json`.** Client không biết representation có HAL links hay HAL-FORMS templates. Ghi media type chính xác cho từng response.

**Nhầm `Accept` với `Content-Type`.** Client gửi sai header hoặc server mapping không khớp. Tài liệu request body và response negotiation riêng.

**Công bố HAL-FORMS nhưng không có converter.** Endpoint không thể serialize đúng media type đã cam kết. Kiểm tra converter và test response thực tế.

**Mô tả `_links` mà không giải thích relation.** Client thấy URI nhưng không biết semantics. Định nghĩa relation, target, điều kiện xuất hiện và thao tác.

**Coi `Link.type` là `Content-Type` của response hiện tại.** Client có thể xử lý sai representation. Ghi rõ `type` trên link là hint của target.

**Nhầm Problem Details với HAL.** `application/problem+json` không tự có `_links`. Tài liệu error representation và HAL resource riêng.

**Dùng vendor media type nhưng không cấu hình converter.** Header có thể được khai báo trong mapping nhưng body không được serialize như mong đợi. Kiểm thử converter.

**Bỏ qua 406 và 415.** Client không biết lỗi khi negotiation thất bại. Công bố status và error media type thực tế.

**Không công bố profile.** Client không hiểu semantics domain mở rộng. Cung cấp profile URI ổn định và tài liệu vocabulary.

**Không khai báo `Vary: Accept`.** Cache có thể trả HAL cho request HAL-FORMS hoặc ngược lại. Kiểm tra cache variation.

**Chỉ cập nhật OpenAPI mà không kiểm tra runtime.** Spec và server có thể lệch nhau. Dùng contract tests để đối chiếu.

**Nhầm OpenAPI Link Object với HAL link.** Một cái mô tả quan hệ operation trong tài liệu OpenAPI, một cái được server gửi trong representation runtime. Ghi rõ vai trò của mỗi loại.

## 18. Nguyên tắc thiết kế

- Ghi chính xác media type cho từng request body và response body.
- Dùng `Accept` cho response negotiation và `Content-Type` cho body đang gửi.
- Dùng `produces` và `consumes` để làm rõ hợp đồng Spring MVC.
- Mô tả riêng cấu trúc HAL, HAL-FORMS và Problem Details.
- Tài liệu hóa relation semantics, embedded relation, affordance và link metadata.
- Phân biệt `Link.type` của target với response `Content-Type`.
- Chỉ công bố media type khi converter thực sự hỗ trợ.
- Công bố profile URI và vendor-specific media type cùng semantics và quy tắc tương thích.
- Mô tả 406, 415 và error media type.
- Dùng `Vary` khi request header làm thay đổi representation.
- Đồng bộ OpenAPI với response runtime.
- Kiểm thử media type, cấu trúc body, relation và cache headers bằng MockMvc hoặc integration test.

## Kết luận

Tài liệu media type xác định cách client yêu cầu, nhận và diễn giải representation của API. Với Spring HATEOAS, cần mô tả rõ HAL, HAL-FORMS, JSON request và Problem Details; phân biệt `Accept` với `Content-Type`; giải thích relation, embedded resources, affordances và profile; đồng thời công bố các trường hợp 406/415. `produces`, `consumes`, OpenAPI và MockMvc giúp giữ tài liệu đồng bộ với runtime. Khi media type và semantics được mô tả chính xác, client có thể khám phá API qua hypermedia mà không phải dựa vào URI hoặc cấu trúc JSON tự suy đoán.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Hypermedia formats](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring HATEOAS API – MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [JSON Hypertext Application Language (HAL) – Internet-Draft](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal-11)
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/)
- [RFC 6906 – The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 9110 – HTTP Semantics, Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#section-12)
- [OpenAPI Specification – Media Types](https://spec.openapis.org/oas/latest.html#media-type-object)

