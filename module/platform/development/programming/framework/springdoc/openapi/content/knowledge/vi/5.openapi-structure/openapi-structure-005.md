# Paths, Path Item và Operation Object

Trong tài liệu OpenAPI, phần `paths` mô tả các địa chỉ API mà client có thể gọi. Mỗi địa chỉ được biểu diễn bằng một **Path Item Object**; bên trong Path Item, từng HTTP method như `get`, `post` hoặc `delete` được mô tả bằng một **Operation Object**. Ba cấp này tạo nên cấu trúc trung tâm để công cụ hiểu API có endpoint nào, endpoint nhận dữ liệu gì và trả về kết quả nào.

Với `springdoc-openapi`, các cấu trúc đó được tạo từ mapping của controller Spring, chữ ký phương thức, DTO và metadata bổ sung. Hiểu mối quan hệ giữa `Paths`, `Path Item` và `Operation Object` giúp đọc tài liệu được sinh, kiểm tra endpoint có bị thiếu hoặc mô tả sai, và bổ sung annotation đúng vị trí.

## 1. Nhìn tổng thể cấu trúc `paths`

Một tài liệu OpenAPI có thể chứa nhiều path. Mỗi path là một khóa trong object `paths`; giá trị của khóa là Path Item Object. Bên trong Path Item, các thuộc tính HTTP method trỏ đến Operation Object tương ứng.

```yaml
paths:
  /api/orders/{orderId}:
    get:
      summary: Lấy thông tin đơn hàng
      operationId: getOrderById
      responses:
        '200':
          description: Tìm thấy đơn hàng
    delete:
      summary: Hủy đơn hàng
      operationId: cancelOrder
      responses:
        '204':
          description: Đã hủy đơn hàng
```

Trong ví dụ:

- `paths` là tập hợp các đường dẫn được công bố.
- `/api/orders/{orderId}` là một path. Phần `{orderId}` là biến đường dẫn, được thay bằng giá trị cụ thể khi client gửi request.
- Giá trị của path là Path Item Object, chứa hai thao tác `get` và `delete`.
- Mỗi `get` hoặc `delete` là một Operation Object, mô tả một cách tương tác riêng với tài nguyên.

Một path có thể có nhiều operation. Cùng một địa chỉ `/api/orders/{orderId}` có thể hỗ trợ lấy thông tin, cập nhật hoặc xóa đơn hàng thông qua các HTTP method khác nhau.

```mermaid
flowchart TD
    A[OpenAPI Document] --> B[paths]
    B --> C[Path: /api/orders/{orderId}]
    C --> D[Path Item Object]
    D --> E[GET Operation Object]
    D --> F[PUT Operation Object]
    D --> G[DELETE Operation Object]
    E --> H[Parameters, Request Body, Responses]
    F --> I[Parameters, Request Body, Responses]
    G --> J[Parameters, Responses]
```

## 2. Paths Object và quy tắc đặt path

`Paths Object` ánh xạ các path đến Path Item Object. Mỗi khóa path là một đường dẫn tương đối so với URL server được khai báo trong `servers`. Path phải bắt đầu bằng dấu `/`.

Ví dụ:

```yaml
servers:
  - url: https://api.example.com/v1
paths:
  /orders:
    get:
      responses:
        '200':
          description: Danh sách đơn hàng
```

Địa chỉ mà client gọi được ghép từ server URL và path, trong ví dụ là `https://api.example.com/v1/orders`. Không đưa toàn bộ hostname vào khóa `paths` nếu hostname đã được khai báo trong `servers`.

Các path có thể chứa biến trong dấu ngoặc nhọn:

```yaml
paths:
  /customers/{customerId}/orders/{orderId}:
    get:
      responses:
        '200':
          description: Chi tiết đơn hàng của khách hàng
```

Khi gọi endpoint, client thay `customerId` và `orderId` bằng giá trị thực. Mỗi biến trong path phải có một Path Parameter tương ứng và parameter đó phải có `required: true`. Tên parameter phải khớp chính xác với tên biến trong path.

```yaml
parameters:
  - name: customerId
    in: path
    required: true
    schema:
      type: string
      format: uuid
  - name: orderId
    in: path
    required: true
    schema:
      type: string
      format: uuid
```

Không dùng query parameter thay cho path parameter khi biến đã nằm trong path template. Ví dụ `/orders/{orderId}` cần parameter `in: path`; còn `/orders?status=PAID` dùng query parameter `status`.

Path template cần được thiết kế nhất quán. Hai path chỉ khác tên biến nhưng có cùng cấu trúc, chẳng hạn `/users/{id}` và `/users/{userId}`, được xem là cùng một mẫu path trong OpenAPI và không nên khai báo như hai endpoint riêng. Nếu cần phân biệt tài nguyên, hãy thiết kế cấu trúc đường dẫn rõ ràng hơn.

## 3. Path Item Object mô tả một địa chỉ API

Path Item Object là giá trị tương ứng với một khóa trong `paths`. Nó gom các operation cùng sử dụng một đường dẫn và có thể chứa metadata dùng chung cho các operation đó.

Các trường thường gặp của Path Item:

| Trường | Ý nghĩa |
|---|---|
| `$ref` | Tham chiếu đến một Path Item được định nghĩa ở nơi khác |
| `summary` | Tóm tắt ý nghĩa của path |
| `description` | Mô tả chi tiết path, có thể hỗ trợ CommonMark |
| `get`, `put`, `post`, `delete`, `options`, `head`, `patch`, `trace` | Các Operation Object theo HTTP method |
| `servers` | Danh sách server áp dụng cho các operation trong path item |
| `parameters` | Các parameter dùng chung cho những operation trong path item |

Ví dụ một Path Item có mô tả và parameter dùng chung:

```yaml
paths:
  /api/orders/{orderId}:
    summary: Các thao tác trên một đơn hàng
    description: Endpoint thao tác với đơn hàng đã được tạo.
    parameters:
      - name: orderId
        in: path
        required: true
        description: Mã định danh đơn hàng
        schema:
          type: string
          format: uuid
    get:
      summary: Lấy đơn hàng
      responses:
        '200':
          description: Tìm thấy đơn hàng
    delete:
      summary: Xóa đơn hàng
      responses:
        '204':
          description: Đã xóa đơn hàng
```

Trong cấu trúc này, `orderId` được khai báo một lần ở cấp Path Item và áp dụng cho cả `get` lẫn `delete`. Cách tổ chức này giúp biểu diễn thông tin thực sự dùng chung. Tài liệu do springdoc sinh có thể đặt parameter trong từng operation tùy cách phân tích và cấu hình; cả cách đặt ở Path Item lẫn Operation đều có thể biểu diễn hợp đồng hợp lệ.

Path Item cũng có thể khai báo `servers` để thay đổi server cho toàn bộ operation trong path đó. Nếu không khai báo, operation kế thừa server ở cấp tài liệu. Operation có thể tiếp tục chỉ định server riêng khi cần.

## 4. Operation Object mô tả một thao tác HTTP

Operation Object mô tả một thao tác cụ thể trên path. Ví dụ, `GET /api/orders/{orderId}` và `DELETE /api/orders/{orderId}` là hai operation khác nhau, có thể có mô tả, bảo mật, tham số và response khác nhau.

Các trường quan trọng:

| Trường | Mục đích |
|---|---|
| `tags` | Nhóm operation trong tài liệu và Swagger UI |
| `summary` | Tóm tắt chức năng |
| `description` | Mô tả cách sử dụng, quy tắc và điều kiện nghiệp vụ |
| `externalDocs` | Liên kết đến tài liệu bổ sung |
| `operationId` | Định danh duy nhất của operation trong tài liệu |
| `parameters` | Tham số path, query, header hoặc cookie |
| `requestBody` | Nội dung request và các media type được hỗ trợ |
| `responses` | Các phản hồi có thể được trả về |
| `callbacks` | Các callback liên quan đến operation nếu có |
| `deprecated` | Đánh dấu operation đã ngừng khuyến nghị |
| `security` | Yêu cầu bảo mật áp dụng cho operation |
| `servers` | Server riêng của operation |

Trong OpenAPI, `responses` là trường bắt buộc của Operation Object. Tài liệu cần mô tả ít nhất một phản hồi, thường có phản hồi thành công và các phản hồi lỗi quan trọng. `operationId`, nếu được khai báo, phải duy nhất trong toàn bộ tài liệu; client generator thường dùng giá trị này để đặt tên phương thức trong mã client.

Ví dụ một operation đầy đủ hơn:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      tags:
        - Orders
      summary: Lấy thông tin đơn hàng
      description: Trả về đơn hàng theo mã định danh.
      operationId: getOrderById
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        '200':
          description: Tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Không tìm thấy đơn hàng
```

## 5. Parameter ở cấp Path Item và Operation

OpenAPI cho phép khai báo parameter ở hai cấp:

- **Path Item level:** parameter được chia sẻ bởi tất cả operation thuộc path đó.
- **Operation level:** parameter chỉ áp dụng cho operation đang mô tả.

Parameter được xác định duy nhất bởi cặp `name` và `in`. Vị trí `in` có thể là `path`, `query`, `header` hoặc `cookie`. Nếu cùng cặp `name` và `in` xuất hiện ở cả hai cấp, khai báo ở Operation sẽ ghi đè khai báo ở Path Item. Operation không thể dùng cơ chế này để loại bỏ parameter đã được khai báo ở cấp Path Item.

Ví dụ, mọi operation trên `/orders/{orderId}` đều cần `orderId`, nhưng chỉ thao tác GET mới nhận query `includeItems`:

```yaml
paths:
  /orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        schema:
          type: string
    get:
      parameters:
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        '200':
          description: OK
    delete:
      responses:
        '204':
          description: No Content
```

Khi kiểm tra parameter, hãy chú ý một số quy tắc:

- Path parameter luôn bắt buộc (`required: true`).
- Query parameter thường dùng cho bộ lọc, phân trang, sắp xếp hoặc tùy chọn biểu diễn.
- Header parameter mô tả header tùy chỉnh. Những header chuẩn như `Accept`, `Content-Type` và `Authorization` có cơ chế mô tả riêng trong OpenAPI; không khai báo chúng như header parameter thông thường.
- Cookie parameter dùng khi API thực sự nhận dữ liệu qua cookie.
- Schema của parameter thể hiện kiểu, định dạng, miền giá trị và giới hạn của dữ liệu.

## 6. Request Body và Responses thuộc Operation

`requestBody` mô tả nội dung mà client gửi đến operation. Nó có thể có `description`, `required` và `content`. Trong `content`, khóa là media type, ví dụ `application/json`, `application/xml` hoặc `multipart/form-data`; giá trị chứa schema và ví dụ tương ứng.

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
```

`responses` ánh xạ mã trạng thái HTTP hoặc nhóm mã mặc định đến Response Object. Mỗi response có `description` và có thể có `headers`, `content` hoặc `links`.

```yaml
responses:
  '201':
    description: Đơn hàng đã được tạo
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
  '400':
    description: Request không hợp lệ
  '409':
    description: Xung đột trạng thái đơn hàng
  default:
    description: Lỗi chưa được mô tả cụ thể
```

Không nên mô tả một response chỉ vì muốn tài liệu trông đầy đủ; mã trạng thái và schema phải phù hợp với hành vi ứng dụng. Với các method `GET`, `HEAD` và `DELETE`, ngữ nghĩa của request body không được định nghĩa rõ ràng trong HTTP và một số công cụ có thể bỏ qua hoặc xử lý không nhất quán. Chỉ sử dụng body cho các method này khi hệ thống có yêu cầu cụ thể và các client liên quan hỗ trợ rõ ràng.

## 7. Ánh xạ từ controller Spring sang Path và Operation

Spring MVC định nghĩa route bằng annotation mapping. Springdoc đọc các mapping này để tạo path và operation tương ứng.

| Mã Spring | Thành phần OpenAPI thường được tạo |
|---|---|
| `@RequestMapping("/api/orders")` trên controller | Prefix path chung |
| `@GetMapping("/{orderId}")` | Operation `get` trên `/api/orders/{orderId}` |
| `@PostMapping` | Operation `post` trên `/api/orders` |
| `@PutMapping("/{orderId}")` | Operation `put` trên `/api/orders/{orderId}` |
| `@DeleteMapping("/{orderId}")` | Operation `delete` trên `/api/orders/{orderId}` |
| `@PathVariable` | Parameter có `in: path` |
| `@RequestParam` | Parameter có `in: query` |
| `@RequestHeader` | Parameter có `in: header` |
| `@RequestBody` | Request Body Object |
| Kiểu trả về và `ResponseEntity` | Schema response có thể suy ra từ kiểu nội dung |
| `@Operation`, `@ApiResponse` | Metadata cho Operation và Responses |

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(
        operationId = "getOrderById",
        summary = "Lấy thông tin đơn hàng",
        description = "Tra cứu đơn hàng theo mã định danh."
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Tìm thấy đơn hàng"),
        @ApiResponse(responseCode = "404", description = "Không tìm thấy đơn hàng")
    })
    @GetMapping("/{orderId}")
    OrderResponse getById(
            @PathVariable UUID orderId,
            @RequestParam(required = false) Boolean includeItems) {
        // Gọi service và trả về dữ liệu thực tế.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }

    @Operation(summary = "Tạo đơn hàng")
    @ApiResponse(responseCode = "201", description = "Đơn hàng đã được tạo")
    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        // Gọi service và trả về đơn hàng vừa tạo.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}
```

Từ controller này, springdoc có thể tạo hai path operation chính:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Lấy thông tin đơn hàng
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        '200':
          description: Tìm thấy đơn hàng
        '404':
          description: Không tìm thấy đơn hàng
  /api/orders:
    post:
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
```

Đây là output rút gọn để minh họa quan hệ giữa annotation và OpenAPI; schema đầy đủ, response content và các trường khác phụ thuộc DTO, cấu hình, phiên bản springdoc và các annotation được khai báo.

## 8. Bổ sung metadata cho Operation Object

Springdoc có thể suy ra path, method, parameter và schema từ mã Spring. Tuy nhiên, mô tả nghiệp vụ, `operationId`, response lỗi hoặc liên kết tài liệu thường cần khai báo tường minh.

Các annotation thường dùng:

- `@Operation`: khai báo summary, description, operationId, tags và metadata khác của thao tác.
- `@Parameter`: bổ sung mô tả, ví dụ, schema hoặc thuộc tính cho parameter.
- `@ApiResponses` và `@ApiResponse`: mô tả các mã trạng thái cùng nội dung phản hồi.
- `@RequestBody` của OpenAPI: bổ sung mô tả hoặc ví dụ cho request body khi cần; phân biệt annotation này với `org.springframework.web.bind.annotation.RequestBody` dùng để binding request trong Spring MVC.
- `@Tag`: tổ chức các operation thành nhóm.
- `@SecurityRequirement`: thể hiện yêu cầu bảo mật cho operation hoặc controller.

Ví dụ phân biệt hai annotation có tên `RequestBody`:

```java
@org.springframework.web.bind.annotation.PostMapping("/orders")
@io.swagger.v3.oas.annotations.Operation(summary = "Tạo đơn hàng")
public OrderResponse create(
        @jakarta.validation.Valid
        @org.springframework.web.bind.annotation.RequestBody
        CreateOrderRequest request) {
    // Xử lý tạo đơn hàng.
    throw new UnsupportedOperationException("Ví dụ minh họa");
}
```

Trong mã thực tế, nên dùng import để tránh viết tên đầy đủ như ví dụ. Annotation Spring đảm nhiệm việc nhận dữ liệu request; annotation OpenAPI bổ sung mô tả hợp đồng.

## 9. Security và servers ở cấp Operation

Operation có thể khai báo `security` riêng khi endpoint có yêu cầu xác thực khác với phần còn lại của tài liệu. Ví dụ, tài liệu cấp cao có thể yêu cầu bearer token, còn một endpoint tra cứu công khai không cần xác thực. Cần đảm bảo metadata này khớp với cấu hình Spring Security đang chạy.

Operation cũng có thể khai báo `servers` riêng. Điều này hữu ích khi một thao tác được phục vụ tại host hoặc base path khác, chẳng hạn endpoint upload được đưa qua một dịch vụ lưu trữ riêng. Nếu không có cấu hình riêng, operation kế thừa server ở cấp Path Item hoặc cấp tài liệu theo thứ tự áp dụng của OpenAPI.

Không dùng `servers` để thay thế path. Server mô tả URL cơ sở; path mô tả phần tài nguyên sau URL cơ sở. Việc tách hai phần giúp cùng một hợp đồng có thể được sử dụng ở nhiều môi trường như local, staging và production.

## 10. Những điểm cần kiểm tra khi review Paths và Operations

Khi đọc tài liệu OpenAPI được springdoc sinh ra, có thể dùng danh sách kiểm tra sau:

1. **Path:** mọi URL công khai đều bắt đầu bằng `/`, dùng path template nhất quán và không có hai template trùng cấu trúc.
2. **HTTP method:** operation phản ánh đúng mapping Spring; không thiếu method hoặc xuất hiện method ngoài dự kiến.
3. **Path parameter:** mọi biến `{...}` đều có parameter cùng tên, `in: path` và `required: true`.
4. **Parameter dùng chung:** parameter ở Path Item được áp dụng cho các operation liên quan; parameter ở Operation không vô tình tạo cặp `name`/`in` trùng lặp.
5. **Operation metadata:** summary, description, tags và operationId rõ ràng; operationId không bị trùng trong toàn tài liệu.
6. **Request body:** required, media type và schema đúng với dữ liệu Spring nhận vào.
7. **Responses:** có trường `responses`, mô tả đủ mã trạng thái quan trọng và schema khớp với dữ liệu thực tế.
8. **Security và servers:** yêu cầu xác thực cùng URL cơ sở đúng với môi trường và chính sách triển khai.
9. **Khả năng tái sử dụng:** `$ref` trỏ đến thành phần hợp lệ và schema dùng chung không gây mâu thuẫn.
10. **Runtime:** gọi thử endpoint để đối chiếu hợp đồng với status code và payload thực tế.

Một tài liệu có thể hợp lệ về cú pháp nhưng vẫn sai về ý nghĩa. Ví dụ, path `/api/orders/{orderId}` thiếu path parameter `orderId`, `operationId` bị trùng hoặc response khai báo `200` trong khi controller thực tế trả `204` đều là vấn đề cần xử lý.

## 11. Kết luận

`Paths` xác định các địa chỉ API, `Path Item Object` gom các thao tác và metadata dùng chung trên một địa chỉ, còn `Operation Object` mô tả từng tương tác HTTP cụ thể. Springdoc-openapi chuyển mapping và metadata từ controller Spring thành các cấu trúc này trong tài liệu OpenAPI. Khi đọc đúng ba cấp, người phát triển có thể lần theo đường đi từ route trong mã nguồn đến parameter, request body, response và security của hợp đồng, từ đó phát hiện sai lệch và duy trì tài liệu API nhất quán.
