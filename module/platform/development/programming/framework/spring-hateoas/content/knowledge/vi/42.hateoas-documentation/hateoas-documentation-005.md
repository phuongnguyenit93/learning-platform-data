# Ví dụ response trong tài liệu Spring HATEOAS

Ví dụ response là phần cốt lõi của tài liệu API hypermedia. Chúng cho client thấy server thực sự trả về media type nào, payload nằm ở đâu, relation nào được công bố và representation thay đổi ra sao theo trang, trạng thái hoặc quyền truy cập. Một ví dụ JSON tĩnh không có request context thường chưa đủ: người đọc cần biết request headers, HTTP status, Content-Type và điều kiện tạo ra response đó.

Với Spring HATEOAS, representation có thể thay đổi theo trạng thái nghiệp vụ, quyền của người dùng, media type và dữ liệu hiện tại. Vì vậy, bộ ví dụ cần bao phủ resource đơn, collection, pagination, URI template, embedded resource, action affordance và error response. Mỗi ví dụ phải làm rõ semantics của relation, phân biệt link bắt buộc với link tùy chọn và chỉ ra client có thể làm gì tiếp theo. Bài này hướng dẫn thiết kế, chú giải, tổ chức và kiểm thử các ví dụ response đó, đồng thời kết hợp relation catalog và OpenAPI để giữ tài liệu nhất quán.

## 1. Chọn bộ ví dụ response đại diện

Không nên chỉ đưa một response thành công duy nhất rồi xem đó là tài liệu đầy đủ. Hãy chọn một tập response đại diện cho các nhánh quan trọng của API:

| Ví dụ response | Điều cần minh họa |
| --- | --- |
| Entry point | Relation gốc để client bắt đầu traversal. |
| Resource đơn | Payload, self link và association links. |
| Collection | Tên embedded relation, item links và collection links. |
| Trang đầu/trang giữa/trang cuối | Page metadata và điều kiện xuất hiện của next/prev. |
| Search template | Biến URI template, default và cách mở rộng. |
| Action khả dụng/không khả dụng | Affordance xuất hiện hoặc vắng mặt theo quyền và state. |
| Error response | HTTP status, Problem Details, mã lỗi và help links. |
| Representation theo media type | Khác biệt giữa HAL, HAL-FORMS và Problem Details nếu API hỗ trợ. |

Với mỗi ví dụ, ghi rõ request tối thiểu tạo ra nó, Accept header, HTTP status, Content-Type, response body và dữ liệu/điều kiện giả định. Nếu một link chỉ xuất hiện với chủ sở hữu hoặc khi đơn ở trạng thái PENDING, hãy nêu điều kiện ngay cạnh ví dụ. Nếu không, người đọc có thể hiểu nhầm link tùy chọn là một phần luôn có của schema.

Ví dụ trong bài dùng dữ liệu minh họa để giải thích cấu trúc. Khi áp dụng vào API thật, hãy thay bằng response lấy từ integration test hoặc môi trường mẫu, đồng thời loại bỏ token, PII và thông tin nội bộ trước khi xuất bản.

Một tài liệu tốt cũng giúp người đọc trả lời được các câu hỏi: API entry point nằm ở đâu; client tìm tài nguyên bằng relation nào; dữ liệu nằm trong payload, _embedded hay một link; action dùng method/input nào; và client xử lý thế nào khi link hoặc affordance không xuất hiện.

## 2. Bắt đầu từ entry point và hành trình của client

Tài liệu nên chỉ ra một entry point ổn định. Client bắt đầu tại đó, đọc relation được công bố rồi theo href do server trả về. Ví dụ:

~~~http
GET /api
Accept: application/hal+json
~~~

Response:

~~~json
{
  "_links": {
    "self": { "href": "/api" },
    "orders": { "href": "/api/orders" },
    "profile": { "href": "/api/profile" }
  }
}
~~~

Tài liệu cần giải thích orders dẫn tới collection đơn hàng, profile dẫn tới mô tả profile/contract nếu API hỗ trợ, còn self trỏ tới entry point hiện tại. Client nên lấy href từ response thay vì tự nối /api/orders.

Một sơ đồ traversal giúp người đọc hình dung hành trình:

~~~mermaid
flowchart TD
    A[API entry point] -->|orders| B[Order collection]
    B -->|item self| C[Order detail]
    C -->|customer| D[Customer resource]
    C -->|cancel khi đủ điều kiện| E[Cancel action]
    B -->|next| F[Trang kế tiếp]
~~~

Sơ đồ cần mô tả relation và ý nghĩa, không chỉ vẽ các URL. Nếu một relation tùy chọn, ghi rõ điều kiện xuất hiện ngay trên sơ đồ hoặc trong relation catalog.

## 3. Xây dựng relation catalog

Relation catalog là danh mục chính thức của các relation mà API công bố. Đây là một trong những phần quan trọng nhất của tài liệu hypermedia vì relation name là vocabulary mà client dùng để khám phá khả năng.

Ví dụ catalog:

| Relation | Loại | Ý nghĩa | Điều kiện xuất hiện |
| --- | --- | --- | --- |
| self | IANA | Tài nguyên hoặc representation hiện tại. | Có trên resource/collection theo contract. |
| orders | Extension relation | Collection đơn hàng của người dùng hiện tại. | Khi người dùng có quyền đọc đơn hàng. |
| customer | Extension relation | Khách hàng liên quan tới đơn hàng. | Khi association tồn tại và được phép truy cập. |
| next | IANA | Trang kế tiếp trong collection. | Khi còn trang tiếp theo. |
| prev | IANA | Trang trước trong collection. | Khi không ở trang đầu. |
| cancel | Extension relation | Hành động hủy đơn hàng. | Khi policy và trạng thái nghiệp vụ cho phép. |
| help | IANA | Tài liệu trợ giúp cho resource hoặc action. | Khi có tài liệu trợ giúp tương ứng. |

Mỗi relation nên có mô tả đầy đủ:

1. Tên relation và URI relation nếu là extension.
2. Resource hoặc representation nơi relation xuất hiện.
3. Ý nghĩa nghiệp vụ của target.
4. Relation bắt buộc hay tùy chọn.
5. Điều kiện xuất hiện hoặc biến mất.
6. Media type và phương thức client có thể dùng với target.
7. Thay đổi tương thích và chính sách deprecation.

Không tái sử dụng một relation cũ cho ý nghĩa khác. Nếu semantics mới khác với nghĩa đã công bố, hãy tạo relation mới và có kế hoạch chuyển đổi.

## 4. Phân biệt IANA relation và extension relation

Relation được đăng ký tại IANA có semantics dùng chung, ví dụ self, next, prev, first, last, collection, item, help và describedby. Khi một relation đã đăng ký phù hợp với mục đích, nên dùng relation đó để client có thể tận dụng vocabulary phổ biến.

Nếu API cần relation riêng như cancel-order hoặc approval-history, hãy dùng extension relation. Có thể dùng URI tuyệt đối do API kiểm soát:

~~~text
https://api.example.com/rels/cancel
https://api.example.com/rels/approval-history
~~~

URI relation giúp tránh xung đột tên và có thể trỏ tới trang tài liệu mô tả semantics. Tài liệu nên ghi rõ relation là extension và không yêu cầu client hiểu mọi extension mà server có thể bổ sung.

Nếu dùng CURIE trong HAL để rút gọn extension relation, giải thích prefix và cách mở rộng URI. Đừng giả định client có thể hiểu prefix nếu không đọc khai báo CURIE trong response.

## 5. Tài liệu hóa cấu trúc HAL

Khi API trả HAL JSON, hãy mô tả các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| Payload fields | Dữ liệu chính của resource. |
| _links | Các link relation và href để điều hướng. |
| _embedded | Representation được nhúng theo relation. |
| page | Metadata pagination khi response là paged model. |

Ví dụ resource đơn:

~~~http
GET /api/orders/o-42
Accept: application/hal+json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "o-42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": { "href": "/api/orders/o-42" },
    "customer": { "href": "/api/orders/o-42/customer" },
    "cancel": { "href": "/api/orders/o-42/cancel" }
  }
}
~~~

Ghi chú ngay dưới ví dụ rằng cancel chỉ xuất hiện khi policy cho phép. Customer là association link; response chưa chứa dữ liệu customer. Nếu tài liệu có ví dụ cho người không đủ quyền, nên đặt cạnh ví dụ này để cho thấy relation cancel vắng mặt trong representation của họ.

Ví dụ collection:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": { "href": "/api/orders/o-42" },
          "customer": { "href": "/api/orders/o-42/customer" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders?page=0&size=20" },
    "next": { "href": "/api/orders?page=1&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 45,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Tài liệu cần nói rõ orders là collection relation, customer là association link của từng item, còn next là relation điều hướng pagination ở cấp collection. Nếu association customer được nhúng, nó sẽ nằm dưới _embedded của item; không mô tả một link association như thể payload đã có sẵn customer.

## 6. Mô tả các thuộc tính của HAL link

Một HAL link có thể chứa nhiều thuộc tính ngoài href. Tài liệu nên mô tả những thuộc tính API thực sự sử dụng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| href | URI hoặc URI template của target. |
| templated | Cho biết href là URI template cần mở rộng. |
| type | Gợi ý media type của target. |
| deprecation | URI giải thích việc relation/link đang bị deprecated. |
| name | Tên phụ để phân biệt link cùng relation khi contract cần. |
| profile | URI profile mô tả semantics của target. |
| title | Nhãn dễ đọc cho người dùng. |
| hreflang | Ngôn ngữ của target nếu được công bố. |

Không phải mọi link đều cần mọi thuộc tính. href là thành phần cốt lõi; templated cần được giải thích khi API dùng URI template. Nếu có deprecation, tài liệu cần cho biết replacement relation và thời điểm dự kiến loại bỏ.

## 7. Tài liệu hóa URI template và tham số

Search link có thể công bố URI template:

~~~json
{
  "_links": {
    "search": {
      "href": "/api/orders/search{?status,createdAfter,page,size,sort}",
      "templated": true,
      "title": "Tìm kiếm đơn hàng"
    }
  }
}
~~~

Tài liệu cần giải thích từng biến:

| Biến | Kiểu | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| status | Enum | Không lọc | Trạng thái đơn hàng. |
| createdAfter | Date-time | Không lọc | Chỉ lấy đơn tạo sau thời điểm này. |
| page | Integer | 0 | Chỉ số trang, bắt đầu từ 0. |
| size | Integer | 20 | Số item tối đa trên trang. |
| sort | String | createdAt,desc | Trường và hướng sắp xếp. |

Nêu rõ miền giá trị, định dạng ngày giờ, quy tắc encoding và hành vi khi tham số không hợp lệ. Nếu server giới hạn size tối đa, ghi con số và cho biết server clamp giá trị hay trả lỗi.

Client nên mở rộng template bằng thư viện URI Template hoặc API client hỗ trợ; không nối query string bằng string concatenation. Tài liệu nên có ví dụ request sau khi mở rộng template để người đọc dễ kiểm chứng.

## 8. Tài liệu hóa embedded resource và association

Phân biệt ba cách biểu diễn quan hệ:

| Cách biểu diễn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Embedded resource | _embedded.customer | Payload customer có ngay trong response. |
| Association link | _links.customer.href | Client có URI để tải customer. |
| Nested property | customer.name | JSON lồng nhau thông thường, không tự mang HAL relation. |

Với mỗi embedded relation, tài liệu cần mô tả:

- Relation name trong _embedded.
- Kiểu payload và các field có sẵn.
- Link của embedded item nếu có.
- Embedded có luôn xuất hiện hay phụ thuộc projection/parameter.
- Giới hạn độ sâu và số lượng item.
- Quyền truy cập áp dụng cho dữ liệu embedded.

Nếu API hỗ trợ expansion qua query parameter, chỉ liệt kê các relation được phép mở rộng. Không mô tả rằng client có thể nhúng mọi association của domain entity.

## 9. Tài liệu hóa pagination, sorting và filtering

Đối với paged collection, cần mô tả:

- Relation self, first, prev, next, last và điều kiện xuất hiện.
- Page index bắt đầu từ 0 hay 1.
- Default page size và maximum page size.
- Metadata number, size, totalElements, totalPages.
- Sort field được hỗ trợ, thứ tự ưu tiên và hướng mặc định.
- Filter có thể kết hợp hay không, cách xử lý giá trị không hợp lệ.
- Các query parameter có được giữ trong pagination links hay không.

Ví dụ mô tả: next chỉ xuất hiện khi còn trang tiếp theo; client phải theo href được trả về. Khi thay đổi sort hoặc filter, client nên bắt đầu từ entry/search link phù hợp thay vì giữ link next cũ.

Nên đưa ví dụ cho các vị trí trang khác nhau:

| Vị trí | Link thường có | Link thường không có |
| --- | --- | --- |
| Trang đầu khi còn nhiều trang | self, first, next, last | prev |
| Trang giữa | self, first, prev, next, last | Không có relation nào bị loại chỉ vì đang ở giữa. |
| Trang cuối | self, first, prev, last | next |
| Collection chỉ có một trang | self, first, last tùy cách serializer tạo | prev và next |

Đây là mô tả điều kiện logic; response cụ thể phụ thuộc model và cấu hình pagination. Hãy lấy ví dụ thực tế từ API và không ép client giả định mọi relation đều xuất hiện ở mọi trang.

Nếu dùng Slice hoặc cursor pagination không có total count, không ghi totalElements hay totalPages như thể server luôn cung cấp. Tài liệu phải phản ánh chính xác metadata hiện có.

## 10. Tài liệu hóa affordance và HAL-FORMS

HAL link thông thường chỉ chỉ ra target. Nó không tự mô tả đầy đủ HTTP method, request body hoặc các field mà client cần gửi. Nếu API dùng affordance hoặc HAL-FORMS, tài liệu cần mô tả action metadata riêng.

Ví dụ HAL-FORMS template:

~~~json
{
  "_templates": {
    "cancel": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "target": "/api/orders/o-42/cancel",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "type": "text",
          "required": true
        }
      ]
    }
  }
}
~~~

Tài liệu cần giải thích:

- Template name và relation/action mà nó đại diện.
- HTTP method và target URI.
- Request content type.
- Tên, kiểu, required/optional và validation của từng property.
- Response thành công và các lỗi có thể xảy ra.
- Điều kiện khiến template xuất hiện hoặc biến mất.

Không giả định _templates.cancel luôn có mặt. Nếu action phụ thuộc quyền hoặc trạng thái, tài liệu phải nói rõ client chỉ được xem template là khả dụng khi nó được công bố trong representation hiện tại. Server vẫn phải kiểm tra authorization khi request được gửi.

## 11. Tài liệu hóa điều kiện xuất hiện của link

Link tùy chọn cần được mô tả bằng quy tắc dễ hiểu. Ví dụ:

| Link | Điều kiện |
| --- | --- |
| cancel | Đơn ở trạng thái PENDING và người dùng là chủ đơn hoặc có authority quản trị phù hợp. |
| pay | Đơn cần thanh toán và người dùng có quyền thanh toán. |
| refund | Đơn đã thanh toán, đáp ứng chính sách hoàn tiền và người dùng có quyền. |
| next | Collection còn trang tiếp theo. |
| customer | Đơn có customer association và người dùng được phép đọc customer. |

Tài liệu không cần tiết lộ toàn bộ chi tiết security policy nội bộ. Cần nói đủ để consumer hiểu link có thể không xuất hiện và client không nên tự tạo URL thay thế khi link vắng mặt.

Nếu một action không xuất hiện, client nên hiển thị trạng thái hoặc ẩn thao tác tương ứng. Nếu client gửi request trực tiếp, server vẫn phải áp dụng authorization và validation.

## 12. Kết hợp OpenAPI với tài liệu hypermedia

OpenAPI hữu ích để mô tả HTTP operations, parameters, request/response schemas, security schemes và status codes. Tuy nhiên, OpenAPI operation links được khai báo trong tài liệu không thay thế runtime HAL links mà server trả về.

Nên dùng hai lớp tài liệu bổ trợ nhau:

| OpenAPI | Hypermedia guide/relation catalog |
| --- | --- |
| Operation, method và path template. | Entry point và cách client khám phá relation. |
| Request parameters và schemas. | URI template được công bố trong response và semantics biến. |
| Response schemas và status codes. | Ví dụ HAL có _links, _embedded và page metadata. |
| Security schemes. | Điều kiện link/affordance xuất hiện theo quyền và trạng thái. |
| Operation-level links được mô tả tĩnh. | Link target thực tế được server trả về ở runtime. |

OpenAPI có thể mô tả schema của HAL response bằng component riêng, nhưng không nên chỉ khai báo Map<String, Object> cho _links rồi cho rằng tài liệu đã giải thích relation. Relation catalog vẫn cần mô tả ý nghĩa từng relation.

## 13. Ví dụ OpenAPI cho HAL response

Ví dụ rút gọn dưới đây mô tả một operation trả collection HAL. Schema có thể được mở rộng theo field thực tế của API:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders:
    get:
      summary: List orders
      description: >
        Returns an order collection. Follow the orders and pagination
        relations from the response instead of constructing page URLs.
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        "200":
          description: HAL order collection
          content:
            application/hal+json:
              schema:
                $ref: "#/components/schemas/OrderCollection"
components:
  schemas:
    HalLink:
      type: object
      required: [href]
      properties:
        href:
          type: string
          format: uri-reference
        templated:
          type: boolean
        title:
          type: string
    Order:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
        _links:
          type: object
          properties:
            self:
              $ref: "#/components/schemas/HalLink"
    OrderCollection:
      type: object
      properties:
        _embedded:
          type: object
          properties:
            orders:
              type: array
              items:
                $ref: "#/components/schemas/Order"
        _links:
          type: object
          properties:
            self:
              $ref: "#/components/schemas/HalLink"
            next:
              $ref: "#/components/schemas/HalLink"
        page:
          type: object
          properties:
            size:
              type: integer
            totalElements:
              type: integer
            totalPages:
              type: integer
            number:
              type: integer
~~~

Đây là schema minh họa, không phải schema HAL đầy đủ cho mọi API. Trong contract thực tế, relation có thể mở rộng, link có thể chứa thêm thuộc tính và _embedded có thể có nhiều collection. Cần giữ schema khớp response thực tế và mô tả relation semantics ở phần description hoặc relation catalog.

## 14. Dùng annotation OpenAPI trong Spring MVC

Nếu dự án dùng springdoc-openapi, annotation có thể mô tả operation và response media type:

~~~java
@Operation(
        summary = "List orders",
        description = "Returns a HAL collection. Follow relations in _links."
)
@ApiResponse(
        responseCode = "200",
        description = "Order collection",
        content = @Content(
                mediaType = "application/hal+json",
                schema = @Schema(implementation = OrderCollectionDoc.class)
        )
)
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
PagedModel<EntityModel<OrderSummary>> list(Pageable pageable) {
    // Load page and assemble hypermedia representation.
}
~~~

OrderCollectionDoc trong ví dụ là schema documentation DTO được tạo để mô tả cấu trúc JSON, không nhất thiết là kiểu controller trả về. Generic type và HAL wrapper có thể không được suy ra như mong muốn từ reflection, vì vậy hãy kiểm tra OpenAPI document được sinh ra thay vì giả định annotation đã mô tả đúng.

Không để schema documentation DTO trở thành nguồn dữ liệu nghiệp vụ thứ hai. Có thể sinh schema từ model thực tế nếu công cụ hỗ trợ tốt; nếu phải dùng DTO mô tả riêng, thêm contract test để phát hiện drift.

## 15. Tài liệu hóa media type và profile

Nêu rõ media type cho từng response:

| Media type | Mục đích |
| --- | --- |
| application/hal+json | Representation HAL có links và embedded resources. |
| application/problem+json | Problem Details theo RFC 9457. |
| application/json | JSON thông thường nếu API có hỗ trợ. |
| application/prs.hal-forms+json | HAL-FORMS representation nếu API công bố template theo media type này. |

Tài liệu cần chỉ rõ Accept header client nên gửi và Content-Type server trả về. Nếu API hỗ trợ profile URI, mô tả profile bổ sung semantics gì và client có thể dựa vào nó ở mức nào.

Không khẳng định mọi response đều là HAL chỉ vì ứng dụng cài Spring HATEOAS. Content negotiation và converter quyết định representation thực tế. Cần có ví dụ request/response cho từng media type quan trọng.

## 16. Tài liệu hóa error representation

Tài liệu lỗi nên nêu:

- HTTP status.
- Problem type URI.
- Application error code nếu có.
- Ý nghĩa và điều kiện xảy ra.
- Các field extension như errors hoặc JSON Pointer.
- Link help/describedby nếu có.
- Hành vi client nên thực hiện và khả năng retry.

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Link: <https://docs.example.com/problems/order-already-shipped>; rel="describedby"

{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Cannot cancel a shipped order",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED",
  "detail": "The order has already been shipped."
}
~~~

Tài liệu nên nhấn mạnh client dùng type hoặc code để phân loại, không phân tích title/detail. Nếu lỗi có relation trong HTTP Link header, mô tả cách đọc header; nếu API dùng HAL error model, mô tả media type và _links riêng.

## 17. Tài liệu hóa security và quyền truy cập

Phân biệt:

- Authentication: cách client chứng minh danh tính, ví dụ bearer token.
- Authorization: server quyết định client được đọc resource hoặc thực hiện action nào.
- Link visibility: relation/affordance nào server công bố trong representation hiện tại.

Ví dụ tài liệu cho relation cancel:

> Relation cancel chỉ xuất hiện khi người dùng hiện tại có quyền hủy đơn và trạng thái đơn cho phép thao tác. Việc không có relation nghĩa là client không nên hiển thị thao tác hủy trong representation hiện tại. Server vẫn xác thực và kiểm tra quyền khi nhận request trực tiếp tới action URI.

Không ghi các chi tiết bảo mật nhạy cảm như role nội bộ, rule engine expression hoặc thông tin định danh tenant. Mô tả hành vi công khai mà consumer cần hiểu.

## 18. Tài liệu hóa versioning và deprecation

Relation, field, URI template và affordance đều có thể trở thành một phần contract mà client phụ thuộc. Tài liệu cần ghi rõ:

- API version hoặc profile áp dụng.
- Relation/field/action nào được thêm mới.
- Phần tử nào deprecated và replacement được đề xuất.
- Thời gian hỗ trợ phần tử cũ nếu có cam kết.
- Thay đổi nào phá vỡ tương thích.
- Link hoặc URI tài liệu migration.

Nếu HAL link có thuộc tính deprecation, giải thích URI đó trỏ tới thông tin gì. Không xóa relation cũ ngay khi đã thêm relation mới nếu client đang dùng relation cũ còn trong thời gian hỗ trợ.

## 19. Ví dụ end-to-end cho một use case

Một ví dụ end-to-end nên có request, response và cách client tiếp tục. Ví dụ:

~~~http
GET /api
Accept: application/hal+json
~~~

Server trả root có relation orders. Client lấy href rồi gọi:

~~~http
GET /api/orders?page=0&size=20
Accept: application/hal+json
~~~

Collection response có embedded orders và link next. Client chọn item đầu tiên, đọc _links.self.href và theo link đó để mở chi tiết. Nếu representation chi tiết có relation cancel, client có thể hiển thị action. Khi người dùng kích hoạt, client đọc method/input từ affordance hoặc tài liệu action contract rồi gửi request tới target được công bố.

Tài liệu phải chỉ ra trường hợp cancel vắng mặt: client không hiển thị thao tác đó. Nếu request bị từ chối do state thay đổi sau khi GET, server trả Problem Details theo contract và client xử lý ORDER_ALREADY_SHIPPED.

Ví dụ này kết nối entry point, relation catalog, embedded data, action discovery và error contract thành một luồng có thể thực hiện được.

## 20. Cách tổ chức bộ tài liệu

Một bộ tài liệu cho API Spring HATEOAS có thể được chia thành:

| Tài liệu | Nội dung |
| --- | --- |
| Getting started | Base URL, authentication, entry point và media type. |
| Hypermedia guide | Cách traversal, link, embedded resource và URI template. |
| Relation catalog | Danh sách relation, semantics và điều kiện xuất hiện. |
| Resource reference | Payload schema và representation của từng resource. |
| Action/affordance guide | Method, input, output và điều kiện thực thi. |
| Pagination guide | Page metadata, sorting, filtering và next/prev traversal. |
| Error reference | Problem type, code, status và remediation links. |
| Security guide | Authentication, authorization và link visibility. |
| Versioning/deprecation | Chính sách tương thích và migration. |
| OpenAPI document | Operations, schemas, parameters và security schemes. |

Không cần tách mỗi mục thành một trang nếu API nhỏ. Điều quan trọng là người đọc tìm được thông tin theo nhiệm vụ của họ và relation được định nghĩa một lần làm nguồn tham chiếu thống nhất.

## 21. Tạo tài liệu từ code mà vẫn giữ semantics

Spring HATEOAS có thể tạo link động theo controller mapping, nhưng việc sinh OpenAPI từ controller không tự động giải thích đầy đủ ý nghĩa của relation. Tài liệu sinh tự động nên được bổ sung bằng metadata hoặc relation catalog được quản lý rõ.

Một số nguồn có thể dùng:

- Controller annotations cho operation, method, parameters và status.
- DTO/schema annotations cho payload fields.
- @Relation để giữ item/collection relation name ổn định.
- Constant hoặc registry cho extension relation URI.
- Test fixture HAL để minh họa response.
- Contract tests để xác nhận relation và schema được công bố.

Tránh định nghĩa cùng một relation name ở nhiều nơi mà không có kiểm tra. Nếu assembler dùng chuỗi cancel, OpenAPI description dùng cancel-order, còn tài liệu relation catalog dùng cancel, chúng có thể drift. Có thể tạo constant cho relation trong code và kiểm thử response chứa đúng relation đã tài liệu hóa.

## 22. Kiểm thử tài liệu không bị lệch implementation

Tài liệu cần được kiểm tra như một phần của contract:

1. Gọi endpoint trong test và xác nhận media type.
2. Xác nhận relation bắt buộc xuất hiện.
3. Xác nhận relation tùy chọn xuất hiện đúng điều kiện.
4. Theo các link quan trọng để bảo đảm target hoạt động.
5. So sánh payload với schema OpenAPI.
6. Xác nhận relation name trong _embedded không đổi ngoài kế hoạch.
7. Kiểm tra URI template variables và pagination links.
8. Kiểm tra affordance method/input nếu API công bố.
9. Kiểm tra Problem Details và help/describedby links.
10. Kiểm tra ví dụ tài liệu còn parse được và không chứa URL giả định đã lỗi thời.

Không nên snapshot toàn bộ response mà không chuẩn hóa host, ID hoặc timestamp. Ưu tiên assertion semantics: relation nào có mặt, href dẫn tới đâu, payload có field nào và action có điều kiện gì.

## 23. Ví dụ kiểm thử relation catalog bằng MockMvc

Giả sử API cam kết collection luôn có self, có next khi còn trang và item luôn có self. Test có thể xác nhận:

~~~java
mockMvc.perform(get("/api/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
~~~

Với fixture có nhiều hơn một trang, thêm assertion cho _links.next.href. Với trang cuối, xác nhận next không tồn tại. Nếu collection relation là một phần contract, test phải khóa chính xác _embedded.orders chứ không chỉ kiểm tra _embedded tồn tại.

## 24. Kiểm thử ví dụ và schema OpenAPI

Một quy trình CI có thể:

- Parse YAML OpenAPI để phát hiện lỗi cú pháp.
- Validate document theo OpenAPI version đã chọn.
- So sánh response thực tế với schema bằng validator phù hợp.
- Kiểm tra ví dụ JSON có thể parse.
- Chạy contract test để xác nhận relation và media type.

Schema HAL có thể dùng additional properties hoặc extension relation vì relation set có thể mở rộng. Cần cân bằng giữa schema đủ chặt để bắt lỗi payload và đủ linh hoạt để chấp nhận relation mới mà client không hiểu.

Nếu schema khai báo chỉ cho phép một danh sách relation đóng, việc thêm relation mới có thể bị validator coi là lỗi dù client hypermedia nên bỏ qua relation chưa biết. Hãy quyết định rõ schema strict hay extensible và tài liệu hóa quyết định đó.

## 25. Các lỗi thường gặp khi viết tài liệu HATEOAS

**Chỉ liệt kê endpoint và path.** Bổ sung entry point, relation catalog và traversal examples.

**Ghi relation mà không mô tả semantics.** Nêu target là gì, xuất hiện ở đâu và khi nào có mặt.

**Coi mọi link là bắt buộc.** Phân biệt relation bắt buộc và tùy chọn, đặc biệt link theo quyền/trạng thái.

**Nhầm embedded resource với association link.** Mô tả đúng vị trí _embedded và _links.

**Tài liệu URI template thiếu biến hoặc encoding.** Liệt kê kiểu, default, giới hạn và ví dụ expansion.

**Dùng OpenAPI thay cho relation catalog.** OpenAPI mô tả operations/schema; relation catalog giải thích vocabulary hypermedia runtime.

**Giả định affordance luôn tồn tại.** Nêu rõ điều kiện và cách client xử lý khi action vắng mặt.

**Không mô tả media type và Accept header.** Cung cấp request/response mẫu cho HAL, Problem Details và HAL-FORMS nếu được hỗ trợ.

**Ví dụ URL bị hard-code như contract.** Chỉ dùng URL mẫu để minh họa; nhấn mạnh client theo href thực tế từ response.

**Không kiểm thử tài liệu.** Đưa relation, schema và examples vào CI để phát hiện drift.

## 26. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng tài liệu cho API quản lý đơn hàng:

1. Viết Getting Started với base URL, authentication, entry point và media type.
2. Tạo relation catalog cho orders, self, customer, next, prev, cancel và help.
3. Mô tả HAL collection, item representation và association links.
4. Viết URI template cho search, giải thích status/page/size/sort.
5. Mô tả page metadata và cách theo pagination links.
6. Tài liệu hóa điều kiện xuất hiện của cancel theo quyền và trạng thái.
7. Nếu có affordance/HAL-FORMS, mô tả method, target, content type và properties.
8. Tạo OpenAPI document cho operation, request/response schema, media type và security.
9. Bổ sung Problem Details cho các lỗi ORDER_NOT_FOUND, ORDER_ALREADY_SHIPPED và VALIDATION_FAILED.
10. Viết ít nhất một luồng traversal end-to-end từ entry point đến action.
11. Viết MockMvc contract tests cho relation, embedded structure và pagination.
12. Thêm kiểm tra OpenAPI/YAML examples vào CI và quy trình review deprecation.

Bạn đã nắm được cách thiết kế tài liệu API hypermedia khi người đọc có thể bắt đầu từ entry point, khám phá tài nguyên bằng relation, hiểu cấu trúc HAL và URI template, biết khi nào affordance xuất hiện, xử lý lỗi theo contract và kiểm chứng các ví dụ bằng test. Tài liệu tốt mô tả semantics ổn định của API và giúp client điều hướng theo response thực tế thay vì phụ thuộc vào cấu trúc URL nội bộ.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [IANA Link Relation Types](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
