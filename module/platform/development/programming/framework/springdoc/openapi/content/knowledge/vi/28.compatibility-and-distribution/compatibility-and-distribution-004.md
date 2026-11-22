# Khác biệt giữa tương thích đầu vào và đầu ra

Khi thay đổi API, một thay đổi có thể an toàn ở phía request nhưng lại gây lỗi ở phía response, hoặc ngược lại. Vì vậy, không thể đánh giá tương thích chỉ bằng câu hỏi chung “API có còn tương thích không?”. Cần tách hai hướng:

- **Tương thích đầu vào (input compatibility):** server mới có tiếp tục chấp nhận request mà client cũ gửi hay không?
- **Tương thích đầu ra (output compatibility):** client cũ có tiếp tục đọc và xử lý response mà server mới trả về hay không?

Trong Spring Boot, request thường được ánh xạ vào DTO, kiểm tra bằng Bean Validation rồi chuyển tới service. Response được serialize từ DTO hoặc kiểu trả về của controller. springdoc-openapi tạo tài liệu mô tả hai phía này thông qua requestBody, parameters, responses và Schema Object.

Bài này giúp đánh giá thay đổi theo góc nhìn provider và consumer, đọc đúng schema request/response, kiểm thử hành vi thực tế, và quyết định khi nào có thể phát hành phiên bản tương thích hoặc cần tạo phiên bản API mới.

## 1. Hai hướng tương thích trả lời hai câu hỏi khác nhau

Một API có ít nhất hai luồng dữ liệu:

~~~text
Client  ---- Request ---->  Server
Client  <--- Response ----  Server
~~~

Ở luồng request, client gửi dữ liệu và server phải phân tích, xác thực, chấp nhận hoặc từ chối dữ liệu đó. Ở luồng response, server gửi dữ liệu và client phải deserialize, kiểm tra và sử dụng nó.

| Hướng | Câu hỏi | Thành phần cần bảo vệ |
|---|---|---|
| Input compatibility | Server mới còn nhận request cũ không? | Client đang gọi API |
| Output compatibility | Client cũ còn đọc response mới không? | Ứng dụng tiêu thụ API |
| Contract compatibility | OpenAPI mới có còn mô tả đúng hành vi và kỳ vọng của consumer không? | Cả provider và consumer |

Ví dụ, thêm một property tùy chọn vào request thường không làm client cũ hỏng vì client cũ vẫn có thể bỏ qua property đó. Nhưng thêm một property mới vào response có thể làm một client dùng strict deserialization từ chối payload nếu client không cho phép field chưa biết.

Ngược lại, thêm một giá trị enum mà server chấp nhận ở request có thể an toàn cho client cũ, nhưng thêm một giá trị enum mà server trả trong response có thể làm client cũ không xử lý được.

## 2. Phân biệt backward và forward compatibility theo hướng triển khai

Hai thuật ngữ backward và forward thường bị dùng không thống nhất. Để tránh hiểu nhầm, hãy ghi rõ phiên bản client và server:

| Client | Server | Câu hỏi tương thích |
|---|---|---|
| Client cũ | Server mới | Server mới có tương thích ngược với client cũ không? |
| Client mới | Server cũ | Client mới có tương thích tiến với server cũ không? |
| Client mới | Server mới | Hai phía có cùng hiểu contract mới không? |

Trong bài này:

- **Backward compatibility của provider** là server mới vẫn hỗ trợ request và kỳ vọng response của client cũ.
- **Forward compatibility của consumer** là client mới vẫn hoạt động khi gặp server cũ chưa có các thay đổi mới.

Không có một quy tắc chung bảo đảm cả hai hướng. Ví dụ, thêm response property có thể an toàn cho client cũ nếu client bỏ qua field lạ, nhưng client mới lại có thể thất bại khi gọi server cũ vì server cũ chưa gửi property mà client mới mong đợi.

Khi review API change, hãy nêu rõ cần bảo đảm hướng nào. Với API public, thường phải duy trì server mới tương thích với các client đã phát hành.

## 3. Input compatibility: server chấp nhận request

Input compatibility tập trung vào request mà provider nhận:

- Path parameter.
- Query parameter.
- Header và cookie.
- Request body.
- Media type và encoding.
- Kiểu dữ liệu, format và constraint.
- Required/optional.
- Enum và giá trị được phép.
- Cơ chế authentication và authorization.

Một thay đổi an toàn thường mở rộng tập request hợp lệ mà server chấp nhận. Một thay đổi rủi ro thường thu hẹp tập request đó hoặc thay đổi cách server diễn giải dữ liệu cũ.

Ví dụ:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "CUS-1001",
  "items": [
    {
      "productId": "SKU-01",
      "quantity": 2
    }
  ]
}
~~~

Client cũ gửi customerId và items. Nếu server mới thêm một property note tùy chọn, request cũ vẫn có thể hợp lệ. Nếu server mới yêu cầu note bắt buộc, client cũ không gửi field đó và request có thể bị từ chối.

## 4. Output compatibility: client đọc response

Output compatibility tập trung vào response mà consumer nhận:

- Status code.
- Response body và schema.
- Property name và type.
- Required/optional.
- Nullability.
- Enum.
- Format ngày giờ, số và định danh.
- Content-Type và media type.
- Response headers.
- Error representation.
- Cấu trúc phân trang hoặc streaming.

Một thay đổi an toàn thường giữ nguyên dữ liệu mà client cũ cần, hoặc chỉ bổ sung dữ liệu mà client có thể bỏ qua. Một thay đổi rủi ro thường xóa, đổi kiểu hoặc đổi ý nghĩa dữ liệu cũ.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "ORD-1001",
  "status": "PAID",
  "createdAt": "2026-11-20T10:00:00Z"
}
~~~

Nếu server mới thêm property optional source, client cũ có thể tiếp tục đọc id, status và createdAt. Nếu server đổi status từ string sang object, client cũ có thể không deserialize được.

## 5. Ma trận thay đổi request và response

Bảng sau là hướng dẫn đánh giá ban đầu. Kết quả cuối cùng còn phụ thuộc strictness của server, serializer, client runtime và quy ước contract của tổ chức.

| Thay đổi | Input compatibility: server nhận request | Output compatibility: client đọc response |
|---|---|---|
| Thêm property optional | Thường tương thích ngược | Thường tương thích nếu client bỏ qua field lạ |
| Thêm property required | Có thể phá client cũ | Client mới có thể không chạy với server cũ nếu server cũ không gửi field |
| Xóa property | Có thể phá client cũ đang gửi field hoặc dựa vào nó | Thường phá client đang đọc field |
| Đổi tên property | Phá nếu server không còn nhận tên cũ | Phá nếu client vẫn đọc tên cũ |
| Đổi kiểu dữ liệu | Thường phá | Thường phá |
| Thu hẹp constraint | Có thể phá request trước đây hợp lệ | Có thể phá nếu response không còn thỏa contract cũ |
| Mở rộng constraint | Thường an toàn cho request cũ | Có thể thay đổi tập response hợp lệ; cần xem client |
| Thêm giá trị enum | Server nhận thêm giá trị thường an toàn với client cũ | Client cũ có thể không xử lý giá trị mới |
| Xóa giá trị enum | Có thể phá client còn gửi giá trị bị xóa | Server không còn phát giá trị cũ; thường client cũ vẫn hiểu các giá trị còn lại |
| Đổi media type | Có thể phá cách gửi request | Có thể phá decoder của client |
| Đổi status code | Có thể ảnh hưởng cách gọi hoặc retry | Có thể phá nhánh xử lý response của client |

Không đánh giá thay đổi chỉ bằng tên “additive”. Thêm field vào request và thêm field vào response là hai trường hợp khác nhau vì một phía là dữ liệu server nhận, phía kia là dữ liệu client nhận.

## 6. Thêm property tùy chọn vào request

Giả sử request ban đầu:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderLineRequest> items
) {}
~~~

Phiên bản mới thêm note tùy chọn:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderLineRequest> items,
    String note
) {}
~~~

Client cũ vẫn gửi customerId và items. Nếu server mới không yêu cầu note và không thay đổi cách xử lý các field cũ, request cũ vẫn được chấp nhận.

OpenAPI request schema có thể thể hiện:

~~~yaml
CreateOrderRequest:
  type: object
  required:
    - customerId
    - items
  properties:
    customerId:
      type: string
    items:
      type: array
      items:
        $ref: '#/components/schemas/CreateOrderLineRequest'
    note:
      type: string
~~~

note không nằm trong danh sách required nên client có thể bỏ qua.

Tuy nhiên, cần kiểm tra DTO binding và validation thật. Nếu custom deserializer hoặc business validation yêu cầu note ở runtime, schema tài liệu không đủ để bảo đảm input compatibility.

## 7. Thêm property bắt buộc vào request

Giả sử phiên bản mới thêm field:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderLineRequest> items,
    @NotBlank String channel
) {}
~~~

Nếu channel bắt buộc, client cũ không gửi field này. Server mới có thể trả 400 do validation hoặc từ chối request theo logic nghiệp vụ.

OpenAPI sẽ biểu diễn channel trong required:

~~~yaml
required:
  - customerId
  - items
  - channel
~~~

Đây thường là breaking change đối với input compatibility.

Cách triển khai an toàn hơn có thể là:

1. Thêm channel dưới dạng optional.
2. Đặt default cho client cũ hoặc xác định cách suy ra channel.
3. Công bố field mới trong OpenAPI.
4. Cho client có thời gian gửi field.
5. Theo dõi request thiếu channel.
6. Chỉ chuyển thành required trong một phiên bản breaking change nếu thực sự cần.

Không đánh dấu property là required chỉ để tài liệu trông đầy đủ nếu server vẫn có thể xử lý request thiếu field.

## 8. Xóa hoặc đổi tên request property

Xóa một property khỏi DTO có thể khiến Jackson bỏ qua field cũ hoặc từ chối request tùy cấu hình. Ngay cả khi server không lỗi, logic nghiệp vụ có thể không còn nhận giá trị mà client gửi.

Đổi tên property cũng có rủi ro tương tự:

~~~json
{
  "customerId": "CUS-1001"
}
~~~

đổi thành:

~~~json
{
  "customer": "CUS-1001"
}
~~~

Client cũ vẫn gửi customerId. Nếu server mới chỉ đọc customer, dữ liệu có thể bị thiếu hoặc validation thất bại.

Nếu cần đổi tên, có thể duy trì alias trong giai đoạn chuyển tiếp bằng Jackson:

~~~java
public record CreateOrderRequest(
    @JsonAlias("customerId")
    @JsonProperty("customer")
    String customer
) {}
~~~

Ví dụ trên cần được kiểm tra với Jackson version và record binding của dự án. Đặc biệt, OpenAPI phải mô tả tên property mà client được yêu cầu gửi. Nếu server nhận cả tên cũ và tên mới, hãy công bố rõ thời hạn ngừng hỗ trợ tên cũ.

## 9. Thay đổi request constraint

Constraint là một phần của input contract. Các annotation Bean Validation có thể được springdoc phản ánh vào schema:

~~~java
public record SearchRequest(
    @Size(min = 2, max = 50)
    String keyword,

    @Positive
    Integer pageSize
) {}
~~~

OpenAPI có thể mô tả minLength, maxLength, minimum hoặc exclusiveMinimum tùy constraint.

Nếu server mới đổi maxLength từ 50 xuống 20, một request cũ có keyword dài 30 ký tự trước đây hợp lệ nhưng nay bị từ chối. Đây là thu hẹp input domain và thường là breaking change.

Nếu server tăng maxLength từ 50 lên 100, server chấp nhận thêm request. Với client cũ, thay đổi này thường tương thích ngược.

Cần kiểm tra cả hai lớp:

- OpenAPI schema phản ánh constraint mới.
- Runtime validation thực sự chấp nhận hoặc từ chối đúng dữ liệu.

Không giả định mọi annotation tùy chỉnh đều được springdoc chuyển thành schema keyword. Nếu constraint đến từ validator riêng, hãy mô tả bằng schema annotation và test contract tương ứng.

## 10. Thêm và xóa giá trị enum trong request

Giả sử request có enum:

~~~java
public enum OrderChannel {
    WEB,
    MOBILE
}
~~~

Server mới thêm PARTNER:

~~~java
public enum OrderChannel {
    WEB,
    MOBILE,
    PARTNER
}
~~~

Server mới có thể chấp nhận thêm một giá trị. Client cũ vẫn gửi WEB hoặc MOBILE nên thường không bị ảnh hưởng.

Tuy nhiên, client mới được sinh từ spec mới có thể gửi PARTNER. Nếu client đó gọi server cũ chỉ biết WEB và MOBILE, request có thể bị từ chối. Đây là khác biệt giữa server mới nhận request cũ và server cũ nhận request mới.

Nếu server xóa MOBILE, các client cũ còn gửi MOBILE sẽ bị lỗi. Do đó, xóa enum value trong request thường là breaking change.

Trong OpenAPI:

~~~yaml
OrderChannel:
  type: string
  enum:
    - WEB
    - MOBILE
    - PARTNER
~~~

Không chỉ cập nhật enum trong tài liệu. Hãy kiểm tra parser, Jackson enum deserializer, validation và business logic.

## 11. Thêm property vào response

Giả sử response ban đầu:

~~~java
public record OrderResponse(
    String id,
    String status
) {}
~~~

Phiên bản mới thêm createdAt:

~~~java
public record OrderResponse(
    String id,
    String status,
    Instant createdAt
) {}
~~~

OpenAPI response schema mới:

~~~yaml
OrderResponse:
  type: object
  required:
    - id
    - status
  properties:
    id:
      type: string
    status:
      type: string
    createdAt:
      type: string
      format: date-time
~~~

createdAt không required nên tài liệu cho phép property vắng mặt. Nếu server luôn gửi field, có thể cân nhắc required theo chính sách schema. Nhưng khi thêm property vào response, cần kiểm tra client có chấp nhận field chưa biết hay không.

Nhiều JSON deserializer bỏ qua property không biết theo mặc định, nhưng một số cấu hình bật strict unknown-property handling. Client được sinh từ schema đóng hoặc dùng validation nghiêm ngặt cũng có thể từ chối field mới.

Vì vậy, thêm response property thường được xem là compatible với consumer linh hoạt, nhưng không phải bảo đảm tuyệt đối cho mọi client.

## 12. Thêm property required vào response

Khi server mới luôn trả thêm một field, OpenAPI có thể đánh dấu field đó required:

~~~yaml
OrderResponse:
  type: object
  required:
    - id
    - status
    - fulfillmentMode
  properties:
    id:
      type: string
    status:
      type: string
    fulfillmentMode:
      type: string
~~~

Client cũ thường có thể bỏ qua fulfillmentMode nếu deserializer cho phép field lạ. Nhưng client mới được sinh từ schema này có thể coi fulfillmentMode luôn tồn tại.

Nếu client mới gọi server cũ, server cũ chưa gửi fulfillmentMode. Client mới có thể nhận null, giá trị mặc định hoặc lỗi tùy generated model và runtime.

Đây là ví dụ cho thấy một thay đổi có thể:

- Tương thích với client cũ khi server mới gửi thêm field.
- Không tương thích với client mới khi client đó gọi server cũ.

Nếu client và server được triển khai độc lập, hãy cân nhắc rollout theo thứ tự: triển khai server hỗ trợ field mới trước, sau đó mới triển khai client bắt buộc sử dụng field.

## 13. Xóa hoặc đổi kiểu response property

Xóa một property response thường phá client đang sử dụng field đó:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Nếu server mới chỉ trả:

~~~json
{
  "id": "ORD-1001"
}
~~~

Client đọc status có thể nhận null, lỗi validation hoặc lỗi logic.

Đổi type cũng có rủi ro:

| Cũ | Mới | Rủi ro |
|---|---|---|
| string | integer | Deserializer hoặc code consumer không tương thích |
| integer | string | Kiểu model và phép toán thay đổi |
| string | object | Cấu trúc response thay đổi |
| date-time string | epoch number | Client phải đổi parser |
| array | object | Hình dạng payload thay đổi |
| object | array | Hình dạng payload thay đổi |

Ngay cả khi giá trị có thể chuyển đổi về mặt nghiệp vụ, contract vẫn thay đổi. Không dựa vào khả năng coercion của một client cụ thể để tuyên bố tương thích với tất cả consumer.

Nếu cần đổi kiểu, hãy tạo field mới hoặc version API mới, duy trì field cũ trong giai đoạn chuyển tiếp và có kế hoạch deprecation.

## 14. Thêm giá trị enum trong response

Server có thể bắt đầu trả một giá trị enum mới:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Nếu client cũ chỉ biết PENDING, PAID và CANCELLED, giá trị SHIPPED có thể gây:

- Enum deserialization failure.
- Fallback thành null hoặc unknown.
- Lỗi trong switch expression.
- Bỏ qua nhánh nghiệp vụ.
- Hiển thị sai trạng thái.

Do đó, mở rộng enum ở response có thể phá output compatibility của consumer cũ, dù schema chỉ thêm một giá trị.

Một client bền vững nên có nhánh xử lý giá trị chưa biết nếu domain cho phép. Tuy nhiên, không thể giả định mọi client đã được viết theo hướng đó.

Nếu enum response có thể mở rộng, hãy ghi rõ trong API guidelines rằng consumer phải xử lý unknown value. Với client generator, kiểm tra cấu hình enum extensibility và behavior của runtime ngôn ngữ đích.

## 15. Thay đổi status code và response header

Response contract không chỉ có body. Status code và headers cũng là output.

Ví dụ endpoint ban đầu trả 200:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Server mới chuyển sang 204 No Content. Client đang deserialize body thành OrderResponse có thể gặp lỗi vì body không còn.

Một số thay đổi status khác:

- 200 thành 201 có thể ảnh hưởng client chỉ xử lý 200.
- Thêm 202 có thể thay đổi semantics từ hoàn tất sang xử lý bất đồng bộ.
- Thêm 409 có thể yêu cầu client xử lý conflict.
- 404 thành 204 có thể làm mất thông tin “không tìm thấy”.
- Thêm redirect có thể thay đổi hành vi client nếu redirect không được follow.

Headers cũng có thể là contract:

- Location.
- ETag.
- Retry-After.
- Link.
- RateLimit hoặc X-RateLimit-*.
- Content-Disposition.

Nếu client dựa vào header, hãy mô tả trong OpenAPI và kiểm thử runtime. Không đánh giá tương thích chỉ bằng response schema.

## 16. Thay đổi media type và content negotiation

Request media type xác định cách client gửi body. Response media type xác định cách client giải mã body.

Ví dụ request JSON:

~~~java
@PostMapping(
    value = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Nếu server mới chỉ nhận application/vnd.example.order+json, client cũ gửi application/json có thể bị 415 Unsupported Media Type.

Response tương tự: nếu client cũ mong application/json nhưng server trả application/xml hoặc application/x-ndjson, decoder có thể không xử lý được.

Trong OpenAPI, media type nằm dưới content của requestBody hoặc responses:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
~~~

Nếu API hỗ trợ nhiều media type, hãy kiểm tra từng nhánh Accept và Content-Type. Đừng đổi produces hoặc consumes chỉ để chuẩn hóa code nếu chưa đánh giá consumer.

## 17. Required, optional và nullable là ba điều cần phân biệt

Một property có thể:

- Required và non-null.
- Required nhưng nullable.
- Optional và non-null nếu xuất hiện.
- Optional và nullable.

Ví dụ trong OpenAPI 3.1:

~~~yaml
type: object
required:
  - id
  - note
properties:
  id:
    type: string
  note:
    type:
      - string
      - "null"
  comment:
    type: string
  nickname:
    type:
      - string
      - "null"
~~~

Trong ví dụ:

- id bắt buộc và không null.
- note bắt buộc nhưng có thể null.
- comment không bắt buộc; nếu xuất hiện phải là string.
- nickname không bắt buộc và có thể null.

Client generator có thể ánh xạ các trường này thành kiểu khác nhau theo ngôn ngữ. Nếu chuyển schema 3.0 sang 3.1, hãy kiểm tra nullable mapping của generator và runtime.

Không dùng required như một từ đồng nghĩa với non-null. Hai khái niệm này độc lập.

## 18. Read-only và write-only trong Schema Object

OpenAPI hỗ trợ readOnly và writeOnly để phân biệt property chỉ đọc trong response hoặc chỉ ghi trong request.

Ví dụ:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
      readOnly: true
    accessToken:
      type: string
      writeOnly: true
    name:
      type: string
~~~

id chỉ được server trả về; accessToken chỉ được gửi trong request. Các tool có thể dùng metadata này để tạo model request/response hoặc validation phù hợp.

Trong Java:

~~~java
public record OrderView(
    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    String id,
    String name
) {}
~~~

~~~java
public record CreateOrderRequest(
    String name,
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    String accessToken
) {}
~~~

Dùng DTO riêng cho request và response thường rõ ràng hơn nếu hai hình dạng dữ liệu khác nhau đáng kể. readOnly/writeOnly là metadata schema; hãy kiểm tra Jackson serialization và deserialization thực tế để bảo đảm runtime không gửi hoặc nhận property trái với ý định.

Theo quy tắc OpenAPI, required property có readOnly được hiểu là required trong response; required property có writeOnly được hiểu là required trong request. Cần kiểm tra cách parser và generator đang dùng xử lý quy tắc này.

## 19. Dùng DTO riêng để bảo vệ hai hướng contract

Một cách thiết kế dễ kiểm soát là tách request DTO và response DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<@Valid CreateOrderLineRequest> items
) {}
~~~

~~~java
public record OrderResponse(
    String id,
    String customerId,
    String status,
    Instant createdAt
) {}
~~~

Controller:

~~~java
@PostMapping("/api/orders")
public Mono<ResponseEntity<OrderResponse>> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request)
        .map(order -> ResponseEntity
            .created(URI.create("/api/orders/" + order.id()))
            .body(order));
}
~~~

DTO riêng giúp:

- Thêm field response mà không vô tình yêu cầu client gửi field đó.
- Giới hạn dữ liệu client được phép ghi.
- Không trả token hoặc secret trong response.
- Định nghĩa required/optional độc lập.
- Version request và response có thể được review riêng.

Dùng chung một entity hoặc DTO cho cả request và response có thể khiến property như id, status hoặc internal flag xuất hiện sai phía. Nếu vẫn dùng một model chung, hãy khai báo readOnly/writeOnly rõ ràng và test schema hai chiều.

## 20. Validation runtime và schema tài liệu phải đồng bộ

springdoc có thể suy ra một số constraint từ Bean Validation:

~~~java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Email
    String email
) {}
~~~

Tài liệu có thể mô tả required, maxLength hoặc format phù hợp. Nhưng không phải mọi validator tùy chỉnh đều có thể tự chuyển thành OpenAPI schema.

Có hai lỗi đối nghịch:

- OpenAPI nói field optional nhưng runtime trả 400 nếu thiếu.
- OpenAPI nói maxLength 80 nhưng runtime cho phép hoặc từ chối theo giới hạn khác.

Hãy kiểm tra cả hai:

1. Lấy request schema từ /v3/api-docs.
2. Gửi payload hợp lệ theo schema.
3. Gửi payload thiếu required field.
4. Gửi payload có null.
5. Gửi payload vượt min/max.
6. So sánh status và error body với tài liệu.

Một tài liệu đúng phải mô tả hành vi server thực tế, không chỉ phản ánh annotation ở mức hình thức.

## 21. springdoc mô tả request và response như thế nào?

springdoc phân tích mapping, kiểu tham số, request body, kiểu trả về và annotation để tạo OpenAPI.

Ví dụ:

~~~java
@PostMapping("/api/orders")
@Operation(summary = "Tạo đơn hàng")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng đã được tạo",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu request không hợp lệ"
    )
})
public Mono<ResponseEntity<OrderResponse>> createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request)
        .map(order -> ResponseEntity
            .created(URI.create("/api/orders/" + order.id()))
            .body(order));
}
~~~

springdoc có thể suy ra request schema từ CreateOrderRequest và response schema từ OrderResponse hoặc annotation response.

Khi cần kiểm soát chính xác, dùng @RequestBody, @Parameter, @Schema, @ApiResponse và @Content. Nhưng annotation chỉ mô tả tài liệu; nó không tự thay đổi validation, serialization hoặc business logic.

Sau khi thay đổi annotation, luôn kiểm tra JSON OpenAPI cuối cùng. Không giả định annotation đã tạo đúng schema chỉ vì ứng dụng compile thành công.

## 22. Đánh giá tương thích khi thêm query parameter

Giả sử endpoint ban đầu:

~~~java
@GetMapping("/api/orders")
public Flux<OrderResponse> listOrders() {
    return orderService.findAll();
}
~~~

Phiên bản mới thêm query parameter optional:

~~~java
@GetMapping("/api/orders")
public Flux<OrderResponse> listOrders(
    @RequestParam(required = false) OrderStatus status
) {
    return orderService.findByStatus(status);
}
~~~

Client cũ không gửi status. Nếu server mới vẫn xử lý trường hợp thiếu parameter, input compatibility thường được giữ.

Nếu khai báo required=true hoặc không có default trong một cách binding khiến thiếu parameter bị từ chối, client cũ có thể nhận 400.

OpenAPI cần thể hiện:

~~~yaml
parameters:
  - name: status
    in: query
    required: false
    schema:
      $ref: '#/components/schemas/OrderStatus'
~~~

Thêm optional parameter thường an toàn cho request cũ. Xóa parameter hoặc đổi tên parameter thường phá client đang sử dụng nó.

## 23. Đánh giá tương thích khi thêm response field

Một response field mới có thể được thêm vào schema:

~~~yaml
properties:
  id:
    type: string
  status:
    type: string
  estimatedDelivery:
    type: string
    format: date
~~~

Nếu estimatedDelivery là optional, client mới cần xử lý trường hợp field không có khi gọi server cũ. Client cũ cần xử lý field lạ nếu server mới gửi.

Đây là hai điều kiện khác nhau:

- Server mới với client cũ: client có bỏ qua estimatedDelivery không?
- Server cũ với client mới: client có chấp nhận response không có estimatedDelivery không?

Nếu cả hai hướng đều cần hoạt động trong rollout độc lập, đừng làm client mới phụ thuộc ngay vào field chỉ có ở server mới. Triển khai server trước, sau đó mới bật logic client dựa vào field.

## 24. Thay đổi error response cũng là thay đổi output contract

Error response thường bị bỏ qua khi đánh giá tương thích, nhưng client có thể dựa vào code và message để xử lý.

Ví dụ schema lỗi:

~~~yaml
ApiError:
  type: object
  required:
    - code
    - message
  properties:
    code:
      type: string
    message:
      type: string
    traceId:
      type: string
~~~

Nếu server đổi code từ ORDER_NOT_FOUND sang RESOURCE_MISSING, client có nhánh xử lý theo code cũ có thể không hoạt động.

Nếu server đổi response body từ ApiError thành Problem Details, client cần hỗ trợ schema mới.

Khi chuẩn hóa error format, có thể giữ field cũ trong giai đoạn chuyển tiếp hoặc phát hành version mới. Hãy mô tả các status code và body lỗi bằng @ApiResponse và test bằng WebTestClient.

Không đưa stack trace, SQL detail hoặc secret vào error response chỉ để giúp client debug. Error schema nên chứa thông tin an toàn và ổn định.

## 25. Tương thích của pagination và collection response

Thay đổi từ array sang envelope là thay đổi lớn:

Phiên bản cũ:

~~~json
[
  {"id": "ORD-1"},
  {"id": "ORD-2"}
]
~~~

Phiên bản mới:

~~~json
{
  "items": [
    {"id": "ORD-1"},
    {"id": "ORD-2"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2
}
~~~

Client cũ mong array sẽ không đọc được object envelope. Dù envelope mới cung cấp metadata hữu ích, đây là breaking change đối với output contract.

Nếu cần thêm pagination metadata, có thể tạo endpoint mới, version mới hoặc một giai đoạn chuyển đổi có thỏa thuận rõ. Không đổi response shape của endpoint đang dùng rộng rãi mà không kiểm tra consumer.

## 26. Tương thích của streaming response

Streaming cũng là output contract. Thay đổi từ JSON array sang SSE hoặc NDJSON có thể phá client:

| Representation | Client cần xử lý |
|---|---|
| application/json | Một JSON document, thường là object hoặc array |
| text/event-stream | SSE event framing và kết nối kéo dài |
| application/x-ndjson | Nhiều JSON record phân tách bằng newline |
| application/stream+json | Các JSON value theo framing mà codec/client hỗ trợ |

Đổi Flux<T> không tự động quyết định representation. Media type, codec và mapping mới quyết định cách client nhận dữ liệu.

Nếu đổi media type, hãy xem đó là thay đổi contract. Mô tả response content đúng trong OpenAPI và test client thực tế, không chỉ test server phát publisher.

## 27. Phân biệt schema compatibility với semantic compatibility

Schema có thể giữ nguyên nhưng ý nghĩa dữ liệu vẫn thay đổi.

Ví dụ status vẫn là string nhưng trước đây PAID có nghĩa đã thu tiền, sau đó lại được dùng cho đơn đã xác nhận thanh toán một phần. Type không đổi, nhưng business semantics đã đổi.

Các thay đổi semantic cần review:

- Đơn vị tiền tệ hoặc số đo.
- Múi giờ và ý nghĩa timestamp.
- Quy tắc làm tròn.
- Trạng thái nghiệp vụ.
- Thứ tự phần tử trong danh sách.
- Tính ổn định của identifier.
- Quy tắc phân trang.
- Idempotency và retry behavior.
- Ý nghĩa của null hoặc field bị bỏ qua.

OpenAPI có thể mô tả format, description và enum, nhưng không thể tự chứng minh toàn bộ business semantics. Cần contract documentation, example và test nghiệp vụ.

## 28. Kiểm tra compatibility bằng OpenAPI diff

Sau khi springdoc sinh tài liệu mới:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi-new.json
~~~

So sánh với bản đã phát hành bằng công cụ OpenAPI diff hoặc parser-aware tool. Review riêng:

- Request parameters và required flag.
- Request body schema.
- Request enum và constraints.
- Response status code.
- Response content type.
- Response schema và required fields.
- Enum response.
- Security requirements.
- Server URL và path.
- Error response.

Diff dạng text có thể báo nhiều thay đổi do thứ tự key. Dùng semantic diff để phân loại contract changes. Nhưng không tự động bỏ qua thay đổi server URL hoặc security vì chúng có thể ảnh hưởng trực tiếp client.

## 29. Kiểm tra request compatibility bằng WebTestClient

Ví dụ client cũ không gửi property mới optional:

~~~java
@Test
void acceptsLegacyCreateOrderRequest() {
    webTestClient.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
            {
              "customerId": "CUS-1001",
              "items": [
                {
                  "productId": "SKU-01",
                  "quantity": 2
                }
              ]
            }
            """)
        .exchange()
        .expectStatus().isCreated();
}
~~~

Test này chứng minh server mới vẫn nhận payload cũ trong trường hợp cụ thể. Cần mock service hoặc chuẩn bị fixture phù hợp với test context.

Bổ sung test cho:

- Field mới bị bỏ qua.
- Field mới là null.
- Giá trị enum cũ.
- Parameter cũ.
- Header cũ.
- Payload không có field optional.
- Constraint cũ vẫn hợp lệ.

Nếu server mới cố ý ngừng nhận một request cũ, test nên thể hiện rõ response và phiên bản API tương ứng.

## 30. Kiểm tra output compatibility bằng response fixture

Có thể giữ fixture response của phiên bản cũ và kiểm tra client mới đọc được nó.

Ví dụ JSON fixture:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Test deserialize:

~~~java
@Test
void newClientModelReadsLegacyResponse() throws Exception {
    OrderResponse response = objectMapper.readValue(
        legacyResponseFixture,
        OrderResponse.class
    );

    assertThat(response.id()).isEqualTo("ORD-1001");
    assertThat(response.status()).isEqualTo("PAID");
}
~~~

Nếu DTO mới có field required hoặc constructor không chấp nhận giá trị thiếu, test này có thể phát hiện client mới không tương thích với server cũ.

Với client được sinh từ OpenAPI, nên chạy fixture qua chính model và deserializer được sinh. Không thay bằng DTO viết tay vì hành vi có thể khác.

## 31. Contract test phải kiểm tra cả hai phía

Một quy trình kiểm tra thực tế:

1. Export OpenAPI từ ứng dụng.
2. Validate document và reference.
3. So sánh với contract đã phát hành.
4. Kiểm tra request cũ với server mới.
5. Kiểm tra response mới với client cũ hoặc fixture client cũ.
6. Kiểm tra client mới với response của server cũ nếu rollout cần hỗ trợ.
7. Kiểm tra generated SDK.
8. Chạy WebTestClient cho status, header, body và validation.
9. Review semantic change.
10. Lưu kết quả cùng artifact.

Không chỉ dùng OpenAPI validator. Validator kiểm tra cấu trúc spec, không biết client cũ thực sự xử lý unknown enum hay field lạ như thế nào.

Không chỉ dùng runtime test. Runtime test cho một phiên bản server không chứng minh mọi client đang phát hành đều tương thích.

## 32. Chiến lược triển khai khi contract thay đổi

Khi thêm field mới:

1. Cập nhật server để chấp nhận field mới nhưng vẫn hỗ trợ request cũ.
2. Công bố field optional trong OpenAPI.
3. Triển khai server.
4. Cập nhật client gửi field khi cần.
5. Theo dõi mức sử dụng field cũ.
6. Nếu cần loại bỏ field cũ, công bố deprecation và thời điểm ngừng hỗ trợ.
7. Chỉ xóa trong major/breaking release theo policy.

Khi thêm response field mà client mới cần:

1. Triển khai server gửi field mới nhưng vẫn giữ response cũ.
2. Cập nhật OpenAPI.
3. Đợi server mới sẵn sàng trên toàn bộ fleet.
4. Triển khai client đọc field mới với fallback.
5. Sau khi toàn bộ consumer đã chuyển đổi, mới cân nhắc yêu cầu field ở client.
6. Giữ khả năng đọc response cũ trong thời gian rollout nếu cần.

Trình tự triển khai phụ thuộc hệ thống có rolling deployment, nhiều phiên bản server chạy song song hay không. Contract phải hỗ trợ giai đoạn mà client và server không cùng release.

## 33. Deprecation và thời gian chuyển tiếp

OpenAPI có thể đánh dấu operation hoặc parameter deprecated:

~~~yaml
parameters:
  - name: customerId
    in: query
    required: false
    deprecated: true
    schema:
      type: string
    description: Dùng customerRef thay thế.
~~~

Đánh dấu deprecated giúp consumer biết field vẫn còn tồn tại nhưng không nên dùng cho tích hợp mới.

Một kế hoạch deprecation cần nêu:

- Thành phần sắp bị loại bỏ.
- Thành phần thay thế.
- Phiên bản hoặc ngày dự kiến ngừng hỗ trợ.
- Cách migration.
- Thời gian hai cách cùng hoạt động.
- Cách liên hệ khi consumer cần hỗ trợ.

Không xóa property ngay sau khi đánh dấu deprecated. Deprecation là thông báo chuyển tiếp; removal là thay đổi contract cần được quản lý riêng.

## 34. Versioning API và versioning OpenAPI document

Cần phân biệt:

- API version: phiên bản contract nghiệp vụ.
- OpenAPI version: phiên bản format đặc tả.
- springdoc version: phiên bản thư viện sinh tài liệu.
- Application version: phiên bản artifact server.

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 2.4.0
~~~

Ở đây 3.1.0 là phiên bản đặc tả, còn 2.4.0 là phiên bản API được công bố.

Có thể version API qua URL:

~~~text
/api/v1/orders
/api/v2/orders
~~~

Hoặc dùng header/media type versioning theo policy của hệ thống. Dù chọn cách nào, OpenAPI cần mô tả rõ cách consumer chọn phiên bản và tài liệu phải được phân phối đúng version.

Không tăng OpenAPI version chỉ vì API contract thay đổi. Cũng không tăng API version chỉ vì nâng springdoc.

## 35. Khi nào nên tạo major API version mới?

Cân nhắc major version mới khi thay đổi không thể triển khai theo cách tương thích với consumer hiện tại, ví dụ:

- Xóa hoặc đổi tên request field đang được sử dụng.
- Biến request field optional thành required.
- Thu hẹp constraint khiến request cũ không còn hợp lệ.
- Xóa response field.
- Đổi response type hoặc structure.
- Đổi media type hoặc streaming protocol.
- Loại bỏ status code hoặc error format mà client đang dùng.
- Đổi security scheme hoặc yêu cầu scope mới làm client cũ không gọi được.
- Thay đổi semantic làm client cũ xử lý sai.

Không cần tạo major version chỉ vì thêm operation mới hoặc thêm request property optional, nếu các thay đổi đó thực sự tương thích với consumer đang được hỗ trợ.

Quyết định versioning nên dựa trên compatibility policy đã công bố và dữ liệu sử dụng API, không chỉ dựa vào cảm nhận của người viết endpoint.

## 36. Phân phối contract và generated SDK

Sau khi kiểm tra tương thích, phân phối OpenAPI artifact theo phiên bản bất biến:

~~~text
contracts/
  orders/
    1.0.0/
      openapi.json
      openapi.yaml
      checksum.txt
    1.1.0/
      openapi.json
      openapi.yaml
      checksum.txt
~~~

Mỗi artifact nên gắn với:

- API version.
- Commit hoặc release revision.
- OpenAPI specification version.
- Phiên bản springdoc và toolchain tạo file.
- Kết quả validation.
- Compatibility report.
- Ngày phát hành hoặc release metadata ở ngoài contract nếu cần.

Không ghi đè artifact đã phát hành mà không có policy. Client SDK cần biết được sinh từ contract version nào. Nếu contract thay đổi, hãy sinh SDK mới và phát hành theo versioning policy của package.

## 37. Ma trận kiểm tra trước khi phát hành

Có thể dùng ma trận sau trong pull request:

| Kiểm tra | Input | Output |
|---|---|---|
| Required/optional | Server còn nhận request cũ? | Client có thể thiếu field mới? |
| Type/format | Server parse payload cũ? | Client deserialize payload mới? |
| Enum | Server còn chấp nhận giá trị cũ? | Client xử lý giá trị mới chưa biết? |
| Constraint | Request cũ còn hợp lệ? | Response có luôn thỏa schema? |
| Media type | Server còn nhận Content-Type cũ? | Client còn đọc Content-Type mới? |
| Status code | Request và auth flow không đổi ngoài ý muốn? | Client xử lý status mới? |
| Security | Credential/scope cũ còn được chấp nhận? | Client có thể xử lý challenge/error mới? |
| Generated SDK | Request serializer tạo đúng payload? | Response deserializer xử lý field/enum đúng? |

Đánh dấu PASS chỉ sau khi có bằng chứng từ spec, runtime test hoặc generated client test phù hợp.

## 38. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Thêm request field nhưng client cũ bị 400 | Field mới bị đánh dấu required hoặc validator yêu cầu |
| Thêm response field nhưng client cũ lỗi | Client strict deserialization hoặc schema đóng |
| Client mới lỗi khi gọi server cũ | Client phụ thuộc field response mới chưa có |
| Thêm enum request gây lỗi trên server cũ | Client mới gửi giá trị server cũ không nhận |
| Thêm enum response làm client cũ lỗi | Enum deserializer hoặc switch không có unknown case |
| Đổi type nhưng tài liệu vẫn compile | OpenAPI chỉ là metadata, không kiểm tra runtime payload |
| Request schema đúng nhưng runtime từ chối | Bean Validation hoặc custom validator khác tài liệu |
| Response schema đúng nhưng body sai | Serializer hoặc mapping thực tế khác DTO/annotation |
| Thay JSON array bằng envelope | Client cũ không còn đọc được response shape |
| Đổi 200 thành 204 | Client vẫn cố deserialize body |
| Đổi media type | Decoder client không hỗ trợ representation mới |
| Đánh dấu deprecated rồi xóa ngay | Consumer chưa có thời gian migration |
| Chỉ chạy validator nhưng không test SDK | Tool đọc spec được nhưng generated client có thể sai |
| Tăng OpenAPI version khi API thay đổi | Nhầm format version với API contract version |

## 39. Quy trình review thay đổi API

Khi review một pull request làm thay đổi controller, DTO hoặc annotation:

1. Xác định thay đổi thuộc request, response hay cả hai.
2. So sánh OpenAPI trước và sau.
3. Với request, kiểm tra server mới còn chấp nhận payload cũ.
4. Với response, kiểm tra client cũ còn đọc payload mới.
5. Kiểm tra required, optional, nullable, enum và constraints.
6. Kiểm tra status, headers và media type.
7. Kiểm tra security và authorization.
8. Chạy WebTestClient hoặc integration test.
9. Sinh và compile client SDK nếu dự án phân phối SDK.
10. Quyết định thay đổi tương thích, deprecation hay major version.
11. Lưu artifact OpenAPI và compatibility report.

Nếu không có consumer fixture, hãy tạo fixture từ các contract đã phát hành hoặc từ test của SDK. Đừng dựa vào DTO hiện tại để đại diện cho mọi client cũ.

## 40. Checklist

- [ ] Đã xác định rõ input compatibility và output compatibility.
- [ ] Đã ghi rõ hướng old client/new server hoặc new client/old server.
- [ ] Request property mới optional nếu cần giữ client cũ.
- [ ] Required flag khớp với runtime validation.
- [ ] Request enum cũ vẫn được chấp nhận.
- [ ] Constraint không vô tình thu hẹp input domain.
- [ ] Response field cũ không bị xóa hoặc đổi type ngoài kế hoạch.
- [ ] Client cũ có thể xử lý property response mới.
- [ ] Client mới có fallback khi server cũ chưa gửi field mới.
- [ ] Enum response có chính sách unknown value.
- [ ] Status code và error body được kiểm tra.
- [ ] Content-Type và media type không đổi ngoài ý muốn.
- [ ] readOnly/writeOnly được mô tả và test đúng.
- [ ] Request/response DTO tách riêng khi cần.
- [ ] OpenAPI schema khớp Bean Validation và serialization.
- [ ] Có contract test cho payload cũ và mới.
- [ ] Generated SDK được compile và kiểm thử.
- [ ] Deprecation có thời gian migration.
- [ ] API version không bị nhầm với OpenAPI version.
- [ ] Artifact và compatibility report được lưu theo release.

## 41. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object)
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jackson – Annotations](https://github.com/FasterXML/jackson-annotations)
- [OpenAPI Generator – Documentation](https://openapi-generator.tech/docs/)

Tương thích đầu vào là khả năng server mới tiếp tục nhận request cũ; tương thích đầu ra là khả năng client cũ tiếp tục đọc response mới. Thêm một request property optional thường an toàn cho client cũ, trong khi thêm response enum value có thể làm client cũ lỗi. Hãy đánh giá riêng required, type, constraint, enum, status, media type và semantic, rồi kiểm chứng bằng OpenAPI diff, WebTestClient và generated client trước khi phân phối contract.
