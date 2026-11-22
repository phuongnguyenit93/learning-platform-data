# Biểu thức thời gian chạy trong liên kết phản hồi

Một API thường gồm nhiều thao tác có quan hệ với nhau. Sau khi tạo đơn hàng, client cần dùng mã đơn hàng vừa nhận để gọi endpoint xem chi tiết; sau khi tạo hóa đơn, client có thể gọi endpoint tải hóa đơn tương ứng. OpenAPI Link Object mô tả mối quan hệ này ngay trong response của operation nguồn. Các biểu thức thời gian chạy (runtime expressions) cho phép lấy giá trị từ request hoặc response hiện tại rồi ánh xạ vào parameter hay request body của operation đích.

Với `springdoc-openapi`, có thể khai báo response link bằng annotation `@Link` và `@LinkParameter`. Khi tài liệu được sinh, client và công cụ đọc OpenAPI biết thao tác nào có thể được thực hiện tiếp theo và cần lấy dữ liệu từ đâu. Link chỉ mô tả quan hệ trong hợp đồng; nó không tự gọi endpoint, không thay thế authorization và không tự thêm liên kết hypermedia vào JSON response.

## 1. Link Object giải quyết vấn đề gì?

Giả sử API có hai thao tác:

- `POST /api/orders` tạo đơn hàng và trả về `id`.
- `GET /api/orders/{orderId}` lấy thông tin một đơn hàng theo ID.

Client phải đọc `id` từ response tạo đơn hàng, sau đó truyền giá trị đó vào path parameter `orderId` của thao tác GET. Nếu chỉ nhìn hai endpoint riêng lẻ, client phải tự suy luận mối quan hệ này.

OpenAPI Link Object cho phép mô tả mối quan hệ trực tiếp trong response `201` của thao tác tạo đơn hàng:

```yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      responses:
        '201':
          description: Đã tạo đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
          links:
            getCreatedOrder:
              operationId: getOrder
              parameters:
                orderId: '$response.body#/id'
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Thông tin đơn hàng
```

Sau khi nhận response của `createOrder`, biểu thức `$response.body#/id` lấy trường `id` trong response body và cung cấp giá trị đó cho parameter `orderId` của operation `getOrder`.

Link giúp tài liệu thể hiện luồng thao tác, giảm việc client phải tự đoán cách truyền dữ liệu giữa các endpoint và hỗ trợ công cụ xây dựng trải nghiệm API theo từng bước.

## 2. Link Object nằm ở đâu trong tài liệu OpenAPI?

Link Object được khai báo trong map `links` của một Response Object. Mỗi key trong map là tên link; value là Link Object mô tả operation đích và cách truyền dữ liệu.

Các trường quan trọng của Link Object:

| Trường | Ý nghĩa |
|---|---|
| `operationId` | Tên định danh của operation đích |
| `operationRef` | URI reference trỏ đến Operation Object đích |
| `parameters` | Ánh xạ tên parameter của operation đích sang giá trị hoặc runtime expression |
| `requestBody` | Giá trị hoặc runtime expression dùng làm request body của operation đích |
| `description` | Giải thích mối quan hệ và cách sử dụng link |
| `server` | Server được dùng cho operation đích nếu cần ghi đè server kế thừa |

Link Object phải xác định operation đích bằng `operationId` hoặc `operationRef`. Chỉ chọn một trong hai cách. `operationId` thường dễ đọc và thuận tiện khi các operation được đặt tên ổn định; `operationRef` hữu ích khi muốn tham chiếu trực tiếp đến vị trí operation trong tài liệu hoặc tài liệu ngoài.

Ví dụ Link Object tối giản:

```yaml
links:
  getCreatedOrder:
    operationId: getOrder
    parameters:
      orderId: '$response.body#/id'
```

`getCreatedOrder` là tên của link trong response; `getOrder` là operation đích. Hai tên này có vai trò khác nhau.

## 3. Runtime expression là gì?

Runtime expression là cú pháp tham chiếu đến thông tin có sẵn trong request hoặc response đang được xử lý. Khi client hoặc công cụ thực hiện link, biểu thức được đánh giá trong ngữ cảnh của tương tác nguồn để lấy giá trị cung cấp cho operation đích.

Các nguồn dữ liệu chính:

| Nhóm | Biểu thức | Dữ liệu được lấy |
|---|---|---|
| Request URL | `$url` | URL đầy đủ của request nguồn |
| Request method | `$method` | HTTP method của request nguồn |
| Response status | `$statusCode` | Mã trạng thái response nguồn |
| Request path | `$request.path.orderId` | Path parameter có tên `orderId` |
| Request query | `$request.query.page` | Query parameter có tên `page` |
| Request header | `$request.header.X-Request-Id` | Request header có tên tương ứng |
| Request body | `$request.body` | Toàn bộ request body |
| Một phần request body | `$request.body#/customer/id` | Giá trị tại JSON Pointer trong request body |
| Response header | `$response.header.Location` | Response header có tên `Location` |
| Response body | `$response.body` | Toàn bộ response body |
| Một phần response body | `$response.body#/id` | Giá trị tại JSON Pointer trong response body |

Biểu thức được viết dưới dạng chuỗi. Trong YAML, nên đặt runtime expression trong dấu nháy để tránh parser diễn giải các ký tự đặc biệt theo cú pháp YAML.

## 4. Lấy giá trị từ response body

Đây là trường hợp thường gặp nhất khi liên kết các thao tác tạo và đọc tài nguyên. Giả sử response `201` có cấu trúc:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "CREATED",
  "customer": {
    "id": "cus-100"
  }
}
```

Có thể lấy ID cấp cao bằng:

```text
$response.body#/id
```

Hoặc lấy ID khách hàng lồng nhau bằng:

```text
$response.body#/customer/id
```

Ví dụ ánh xạ vào operation xem chi tiết đơn hàng:

```yaml
links:
  getCreatedOrder:
    operationId: getOrder
    parameters:
      orderId: '$response.body#/id'
```

Phần sau dấu `#` là JSON Pointer tương đối với response body. Tên thuộc tính phải khớp với cấu trúc JSON thực tế được trả về sau khi Jackson serialize DTO. Nếu DTO Java có field `orderId` nhưng Jackson xuất JSON thành `id`, biểu thức cần tham chiếu `#/id`.

Với response body là array, JSON Pointer có thể truy cập phần tử theo chỉ số, ví dụ `$response.body#/items/0/id`. Tuy nhiên, chỉ dùng biểu thức như vậy khi response chắc chắn có phần tử ở vị trí đó; nếu array rỗng, giá trị không thể được lấy theo đường dẫn này.

## 5. Quy tắc JSON Pointer trong runtime expression

Runtime expression có thể kết hợp JSON Pointer để lấy thuộc tính lồng nhau. JSON Pointer dùng dấu `/` để phân tách từng token. Một số ký tự trong tên thuộc tính phải được escape:

| Ký tự trong tên thuộc tính | Cách viết trong JSON Pointer |
|---|---|
| `~` | `~0` |
| `/` | `~1` |

Ví dụ response:

```json
{
  "metadata": {
    "external/id": "ext-42",
    "display~name": "Đơn hàng thử"
  }
}
```

Các biểu thức tương ứng:

```text
$response.body#/metadata/external~1id
$response.body#/metadata/display~0name
```

Không escape dấu `/` hoặc `~` đúng cách có thể khiến JSON Pointer trỏ đến token khác và biểu thức không lấy được dữ liệu mong muốn.

## 6. Lấy giá trị từ request nguồn

Runtime expression cũng có thể lấy thông tin client đã gửi trong request nguồn. Điều này hữu ích khi operation đích cần dùng lại một filter, phiên bản hoặc định danh đã có trong request trước đó.

Ví dụ API tìm kiếm đơn hàng nhận query `customerId` và trả về một kết quả. Link đến thao tác lấy khách hàng có thể sử dụng lại query parameter đó:

```yaml
paths:
  /api/orders:
    get:
      operationId: searchOrders
      parameters:
        - name: customerId
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Danh sách đơn hàng
          links:
            getCustomer:
              operationId: getCustomer
              parameters:
                customerId: '$request.query.customerId'
```

Các nguồn request có thể dùng:

- `$request.path.{name}` cho path parameter.
- `$request.query.{name}` cho query parameter.
- `$request.header.{name}` cho request header.
- `$request.body` hoặc `$request.body#/{pointer}` cho request body.

Tên parameter ở biểu thức nguồn phải khớp với tên thực tế trong request. Đối với request body, JSON Pointer phải trỏ đến thuộc tính có trong payload đã gửi.

## 7. Lấy giá trị từ response header

Một số API trả URI tài nguyên mới trong header `Location`. Link có thể dùng header đó làm nguồn dữ liệu cho operation tiếp theo.

Ví dụ response:

```http
HTTP/1.1 201 Created
Location: https://api.example.com/api/orders/550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json
```

Biểu thức lấy header:

```text
$response.header.Location
```

Trong Link Object, biểu thức có thể được dùng cho một parameter của operation đích nếu giá trị header phù hợp với kiểu parameter đó. Nếu `Location` chứa toàn bộ URL nhưng parameter đích chỉ nhận UUID, không thể gán nguyên URL vào parameter `orderId`; khi đó nên trả thêm ID trong body và dùng `$response.body#/id`, hoặc thiết kế operation đích nhận URI theo cách phù hợp.

Ví dụ lấy header vào một header parameter của operation đích:

```yaml
links:
  followLocation:
    operationId: getResourceByLocation
    parameters:
      resourceUrl: '$response.header.Location'
```

Trong ví dụ này, operation `getResourceByLocation` phải có parameter tên `resourceUrl` với vị trí và kiểu phù hợp. Link không tự phân tích URI để tách path segment thành ID.

## 8. Truyền request body cho operation tiếp theo

Link Object có trường `requestBody`, cho phép cung cấp giá trị cho body của operation đích. Giá trị có thể là một runtime expression lấy từ request hoặc response nguồn.

Ví dụ response trả về một đối tượng chứa payload đã chuẩn hóa để gửi sang thao tác xác nhận:

```yaml
links:
  confirmOrder:
    operationId: confirmOrder
    requestBody: '$response.body#/confirmation'
```

Operation `confirmOrder` cần có request body tương thích với cấu trúc tại `confirmation`. Nếu biểu thức lấy toàn bộ response body nhưng operation đích chỉ nhận một DTO con, cần trỏ đúng JSON Pointer hoặc thay đổi hợp đồng để hai cấu trúc tương thích.

Không nên dùng `requestBody` để chuyển dữ liệu bí mật hoặc dữ liệu nội bộ ngoài dự kiến. Link là thông tin hợp đồng có thể được công cụ và client đọc; chỉ ánh xạ dữ liệu mà người tiêu dùng API được phép sử dụng.

## 9. Liên kết operation bằng `operationId` và `operationRef`

### Dùng `operationId`

Đây là cách dễ đọc nhất:

```yaml
links:
  getCreatedOrder:
    operationId: getOrder
    parameters:
      orderId: '$response.body#/id'
```

Operation đích cần khai báo `operationId` duy nhất trong tài liệu:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
```

Nên đặt operationId tường minh bằng `@Operation(operationId = "...")` thay vì phụ thuộc tên mặc định được sinh từ tên method hoặc mapping. Việc đổi operationId có thể làm hỏng liên kết trong tài liệu và ảnh hưởng client generator.

### Dùng `operationRef`

`operationRef` trỏ trực tiếp đến Operation Object bằng URI reference. Ví dụ tham chiếu nội bộ đến GET `/api/orders/{orderId}`:

```yaml
links:
  getCreatedOrder:
    operationRef: '#/paths/~1api~1orders~1{orderId}/get'
    parameters:
      orderId: '$response.body#/id'
```

Trong JSON Pointer của `operationRef`, dấu `/` thuộc path key được escape thành `~1`. `operationRef` hữu ích khi operation không có `operationId` hoặc khi cần tham chiếu một operation cụ thể. Nếu dùng tài liệu ngoài, URI reference phải trỏ đến tài liệu và vị trí hợp lệ, đồng thời công cụ tiêu thụ phải truy cập được tài liệu đó.

Không khai báo đồng thời `operationId` và `operationRef` trong cùng Link Object. Hãy chọn cách tham chiếu phù hợp và giữ ổn định khi thay đổi path hoặc tên operation.

## 10. Khai báo response link bằng annotation springdoc

Springdoc tích hợp các annotation của Swagger để mô tả Link Object. Có thể đặt `@Link` trong thuộc tính `links` của `@ApiResponse`; mỗi `@LinkParameter` ánh xạ một parameter của operation đích với một runtime expression.

Ví dụ controller tạo đơn hàng và controller đọc đơn hàng:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.links.Link;
import io.swagger.v3.oas.annotations.links.LinkParameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(operationId = "createOrder", summary = "Tạo đơn hàng")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đã tạo đơn hàng",
            links = {
                @Link(
                    name = "getCreatedOrder",
                    operationId = "getOrder",
                    description = "Lấy thông tin đơn hàng vừa tạo",
                    parameters = {
                        @LinkParameter(
                            name = "orderId",
                            expression = "$response.body#/id"
                        )
                    }
                )
            }
        )
    })
    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }

    @Operation(operationId = "getOrder", summary = "Lấy thông tin đơn hàng")
    @GetMapping("/{orderId}")
    OrderResponse getById(@PathVariable UUID orderId) {
        return orderService.getById(orderId);
    }
}
```

`CreateOrderRequest`, `OrderResponse` và `orderService` là các kiểu/thành phần minh họa của ứng dụng. Phần annotation quan trọng gồm:

- `@ApiResponse(responseCode = "201")` gắn link vào response thành công.
- `@Link(name = "getCreatedOrder")` đặt tên cho link trong response.
- `operationId = "getOrder"` xác định operation đích.
- `@LinkParameter(name = "orderId", expression = "$response.body#/id")` lấy ID từ response body và truyền vào parameter `orderId`.
- `@Operation(operationId = "getOrder")` bảo đảm operation đích có ID đúng như link tham chiếu.

Sau khi khởi động ứng dụng, kiểm tra `/v3/api-docs` hoặc `/v3/api-docs.yaml` để xác nhận `links` được sinh dưới đúng response code. Cú pháp annotation cần tương thích với phiên bản `swagger-annotations` mà springdoc đang sử dụng.

## 11. Ví dụ YAML đầy đủ: tạo đơn hàng rồi xem chi tiết

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: '1.0'
paths:
  /api/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đơn hàng đã được tạo
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
          links:
            getCreatedOrder:
              operationId: getOrder
              description: Dùng ID trong response để lấy đơn hàng vừa tạo
              parameters:
                orderId: '$response.body#/id'
        '400':
          description: Dữ liệu tạo đơn hàng không hợp lệ
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Lấy thông tin đơn hàng
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Thông tin đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Không tìm thấy đơn hàng
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - customerId
      properties:
        customerId:
          type: string
          format: uuid
    OrderResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
```

Luồng trao đổi:

1. Client gọi `POST /api/orders` với `CreateOrderRequest`.
2. Server trả `201` cùng `OrderResponse` có thuộc tính `id`.
3. Link `getCreatedOrder` lấy `id` bằng `$response.body#/id`.
4. Công cụ hiểu giá trị đó được truyền vào `orderId` của operation `getOrder`.
5. Client có thể thực hiện `GET /api/orders/{orderId}` để đọc đơn hàng.

Link không làm thay đổi response body. Nếu API muốn client nhận cả URL liên quan trong JSON, ứng dụng vẫn phải trả URL đó như một thuộc tính riêng hoặc triển khai định dạng hypermedia phù hợp.

## 12. Link Object khác HTTP `Link` header và hypermedia body

Các khái niệm có tên gần nhau nhưng nằm ở các lớp khác nhau:

| Cơ chế | Vị trí | Mục đích |
|---|---|---|
| OpenAPI Link Object | Trong tài liệu OpenAPI, dưới `responses.<code>.links` | Mô tả operation tiếp theo và cách lấy parameter/body từ request/response nguồn |
| HTTP `Link` header | Header của HTTP response | Cung cấp quan hệ liên kết giữa tài nguyên, thường theo cú pháp URI reference và relation |
| Hypermedia trong JSON (ví dụ HAL `_links`) | Trong response body | Trả URL hoặc liên kết thực tế để client khám phá tài nguyên |
| OpenAPI Callback Object | Trong tài liệu OpenAPI, dưới operation | Mô tả request mà provider có thể gửi ngược đến URL callback do client cung cấp |

Khai báo OpenAPI Link không tự thêm `Link` header, không tự sinh `_links` trong JSON và không tạo callback endpoint. Nếu API dùng hypermedia, cần triển khai payload hoặc header tương ứng ở runtime; OpenAPI Link có thể bổ sung mô tả quan hệ đó trong hợp đồng.

## 13. Link được đánh giá khi nào và ai thực hiện?

Runtime expression được đánh giá dựa trên request/response của operation nguồn khi một công cụ hoặc client sử dụng Link Object. Server không tự động chạy operation đích chỉ vì tài liệu có link.

Ví dụ, sau response `201`, một công cụ có khả năng xử lý OpenAPI Link có thể:

1. Đọc Link Object `getCreatedOrder`.
2. Xác định operation đích `getOrder`.
3. Đánh giá `$response.body#/id` từ response vừa nhận.
4. Điền giá trị vào parameter `orderId`.
5. Cho phép người dùng hoặc client gọi operation đích.

Việc một công cụ có tự động thực hiện request hay chỉ hiển thị gợi ý phụ thuộc khả năng hỗ trợ và chính sách của công cụ. Không nên giả định mọi phiên bản Swagger UI hoặc client generator đều thực thi tất cả loại Link Object.

Nếu biểu thức không lấy được giá trị, ví dụ response body không có thuộc tính `id`, operation đích có thể không được gọi đúng cách. Hãy thiết kế response schema, runtime expression và parameter đích tương thích, rồi kiểm tra bằng response thực tế.

## 14. Giới hạn và lưu ý khi thiết kế runtime expression

- Biểu thức phải tham chiếu đúng nguồn dữ liệu của operation hiện tại: request hoặc response.
- Tên path/query/header parameter phải khớp với request thực tế.
- JSON Pointer phải trỏ đến thuộc tính có thật và escape `~`/`/` đúng quy tắc.
- Giá trị lấy được phải tương thích với kiểu và vị trí parameter hoặc request body của operation đích.
- Không giả định Link Object tự phân tích URL, tách ID hoặc chuyển đổi kiểu dữ liệu.
- Không giả định mọi response đều có body; response `204` thường không có body để dùng `$response.body`.
- Với response có nhiều media type, biểu thức body phải phù hợp representation được trả thực tế.
- Nếu operationId thay đổi, phải cập nhật các link đang tham chiếu.
- Nếu dùng operationRef, thay đổi path hoặc cấu trúc tài liệu có thể làm URI reference không còn đúng.
- Không ánh xạ token, mật khẩu hoặc dữ liệu nhạy cảm vào operation đích nếu không cần thiết.

Link chỉ mô tả cách liên kết operation. Nó không bảo đảm người gọi có quyền thực hiện operation đích; authorization vẫn được kiểm tra độc lập ở endpoint đích.

## 15. Kiểm tra response links trong tài liệu được sinh

Sau khi thêm annotation hoặc cấu hình link, nên xác minh cả cấu trúc OpenAPI và dữ liệu runtime:

1. Khởi động ứng dụng với cấu hình springdoc đang dùng.
2. Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
3. Tìm operation nguồn và response code có link, ví dụ `POST /api/orders` với response `201`.
4. Kiểm tra key link, `operationId` hoặc `operationRef`, `parameters` và `requestBody`.
5. Xác nhận operation đích tồn tại và tên parameter được ánh xạ chính xác.
6. Gọi operation nguồn và xem response body/header thực tế.
7. Đánh giá thủ công từng runtime expression với payload thực tế để xác nhận giá trị có tồn tại.
8. Dùng Swagger UI hoặc công cụ hỗ trợ Link Object để kiểm tra cách link được trình bày; không giả định UI tự thực thi.
9. Chạy OpenAPI validator để phát hiện cấu trúc link không hợp lệ hoặc tham chiếu sai.
10. Kiểm tra authorization của operation đích độc lập với link.

Ví dụ, nếu schema response mô tả `id` nhưng serializer thực tế đổi tên thành `order_id`, biểu thức `$response.body#/id` sẽ không lấy đúng dữ liệu. Cần đồng bộ Jackson metadata, schema OpenAPI và runtime expression theo tên JSON được gửi ra.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Link không xuất hiện trong `/v3/api-docs` | Annotation đặt sai response hoặc phiên bản thư viện không xử lý như mong đợi | Kiểm tra `@ApiResponse.links` và dependency Swagger Annotations |
| Không tìm thấy operation đích | `operationId` sai hoặc không duy nhất | Đặt `@Operation(operationId = ...)` rõ ràng và cập nhật link |
| `operationRef` không phân giải được | URI reference hoặc JSON Pointer path sai | Escape dấu `/` thành `~1` và kiểm tra path thực tế |
| Parameter đích nhận null/không có giá trị | Runtime expression trỏ sai body/header hoặc dữ liệu không tồn tại | Đối chiếu response runtime và JSON Pointer |
| Biểu thức trỏ sai thuộc tính lồng nhau | Dùng sai token hoặc chưa escape `~`/`/` | Kiểm tra JSON Pointer theo cấu trúc JSON thực tế |
| Link truyền nguyên URL vào parameter ID | Nhầm `$response.header.Location` với giá trị path ID | Trả ID riêng trong body hoặc thiết kế parameter nhận URI |
| Swagger UI không tự gọi operation tiếp theo | UI không hỗ trợ hoặc không tự thực thi loại link đó | Kiểm tra bằng công cụ hỗ trợ Link Object; không coi link là lệnh server |
| Link sai sau khi đổi DTO/Jackson | Tên JSON trong response đã thay đổi | Cập nhật expression và schema đồng bộ |
| Client gọi operation đích bị `403` | Link không cấp quyền truy cập | Kiểm tra authentication/authorization của endpoint đích |

## 17. Nguyên tắc thiết kế

- Dùng Link Object để mô tả mối quan hệ giữa response nguồn và operation tiếp theo.
- Ưu tiên `operationId` ổn định, duy nhất và được khai báo tường minh.
- Dùng `operationRef` khi cần tham chiếu trực tiếp đến operation trong tài liệu.
- Dùng `$response.body#/...` để lấy dữ liệu từ response body và `$response.header.*` để lấy response header.
- Dùng `$request.path.*`, `$request.query.*`, `$request.header.*` hoặc `$request.body#/...` khi cần tái sử dụng dữ liệu request nguồn.
- Đảm bảo tên parameter đích và kiểu giá trị được ánh xạ tương thích.
- Kiểm tra JSON Pointer, đặc biệt với thuộc tính lồng nhau và tên chứa `~` hoặc `/`.
- Dùng `@Link` và `@LinkParameter` trên đúng response annotation của springdoc.
- Phân biệt OpenAPI Link với HTTP Link header, hypermedia body và Callback Object.
- Không xem Link Object là cơ chế tự động gọi API hoặc cấp quyền.
- Kiểm tra tài liệu được sinh cùng response thực tế sau khi thay đổi DTO, serializer hoặc operationId.

## Kết luận

OpenAPI Link Object mô tả operation tiếp theo có thể được gọi từ một response và runtime expressions xác định dữ liệu cần lấy từ request hoặc response nguồn. Các biểu thức như `$response.body#/id`, `$request.path.orderId` và `$response.header.Location` giúp nối dữ liệu giữa các thao tác mà không phải lặp lại quy tắc trong tài liệu bên ngoài. Trong Spring Boot, springdoc-openapi có thể sinh các liên kết này từ `@Link` và `@LinkParameter`. Hãy giữ operationId ổn định, kiểm tra JSON Pointer và bảo đảm biểu thức khớp payload thực tế; việc thực thi operation và kiểm tra quyền vẫn thuộc về client cùng endpoint đích.
