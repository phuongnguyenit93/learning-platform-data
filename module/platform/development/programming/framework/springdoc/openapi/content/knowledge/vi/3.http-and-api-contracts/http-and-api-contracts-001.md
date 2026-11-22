# Đường dẫn, phương thức HTTP và định danh một operation

Khi mô tả API bằng OpenAPI, mỗi thao tác được xác định bởi một **đường dẫn (path)** và một **phương thức HTTP (HTTP method)**. Ví dụ, `GET /api/v1/products/{productId}` là thao tác đọc một sản phẩm, còn `DELETE /api/v1/products/{productId}` là thao tác xóa sản phẩm đó. Hai thao tác dùng cùng đường dẫn nhưng khác phương thức nên là hai operation riêng.

Trong ứng dụng Spring Boot, các mapping của controller quyết định request được chuyển đến phương thức Java nào. Springdoc-openapi đọc những mapping và metadata liên quan để tạo `paths` cùng các operation trong tài liệu OpenAPI. Vì vậy, hiểu mối quan hệ giữa URL, HTTP method, Spring mapping và `operationId` là nền tảng để tạo hợp đồng API rõ ràng, nhất quán và có thể dùng cho các công cụ sinh client hoặc kiểm thử hợp đồng.

## 1. Operation trong OpenAPI là gì?

Một **operation** là mô tả cho một thao tác HTTP cụ thể trên một path. Trong tài liệu OpenAPI, mỗi path có thể chứa nhiều operation tương ứng với các HTTP method được hỗ trợ.

Ví dụ, cùng một tài nguyên sản phẩm có thể cung cấp:

| HTTP method và path | Ý nghĩa |
|---|---|
| `GET /api/v1/products` | Liệt kê sản phẩm |
| `POST /api/v1/products` | Tạo sản phẩm |
| `GET /api/v1/products/{productId}` | Lấy một sản phẩm |
| `PUT /api/v1/products/{productId}` | Thay thế thông tin sản phẩm |
| `PATCH /api/v1/products/{productId}` | Cập nhật một phần thông tin sản phẩm |
| `DELETE /api/v1/products/{productId}` | Xóa một sản phẩm |

Trong đó, `/api/v1/products/{productId}` là một path. Các thao tác GET, PUT, PATCH và DELETE trên path này là những operation khác nhau. Không cần tạo một URL riêng cho từng hành động nếu tài nguyên và ngữ nghĩa HTTP đã đủ để phân biệt chúng.

Trong OpenAPI, cấu trúc tổng quát có dạng:

```yaml
openapi: 3.0.3
info:
  title: Product API
  version: 1.0.0
paths:
  /api/v1/products:
    get:
      summary: Liệt kê sản phẩm
    post:
      summary: Tạo sản phẩm
  /api/v1/products/{productId}:
    get:
      summary: Lấy một sản phẩm
    put:
      summary: Thay thế một sản phẩm
    patch:
      summary: Cập nhật một phần sản phẩm
    delete:
      summary: Xóa một sản phẩm
```

`paths` là nơi khai báo các path. Bên dưới mỗi path là các operation được đặt theo tên HTTP method viết thường. Các trường như `summary`, `description`, `parameters`, `requestBody`, `responses`, `tags` và `operationId` mô tả chi tiết từng operation.

## 2. Thiết kế đường dẫn tài nguyên

Đường dẫn là phần xác định tài nguyên hoặc tập tài nguyên mà client muốn tương tác. Một thiết kế dễ hiểu thường dùng danh từ để biểu diễn tài nguyên, dùng số nhiều cho collection và đặt tài nguyên con theo quan hệ sở hữu hoặc phân cấp.

Ví dụ:

- `/api/v1/customers` biểu diễn tập khách hàng.
- `/api/v1/customers/{customerId}` biểu diễn một khách hàng.
- `/api/v1/customers/{customerId}/orders` biểu diễn các đơn hàng của khách hàng.
- `/api/v1/orders/{orderId}` biểu diễn một đơn hàng.

Các hành động phổ biến được thể hiện bằng HTTP method. Nhờ vậy, `/products/42` không cần đổi thành `/getProduct/42`, `/updateProduct/42` hoặc `/deleteProduct/42`.

### 2.1. Path parameter và query parameter

Path parameter là một phần của đường dẫn, thường dùng để định danh tài nguyên:

`GET /api/v1/products/42`

Query parameter xuất hiện sau dấu `?`, thường dùng để lọc, sắp xếp, phân trang hoặc điều chỉnh cách truy vấn:

`GET /api/v1/products?category=keyboard&page=0&size=20`

Hai loại tham số có vai trò khác nhau:

| Tiêu chí | Path parameter | Query parameter |
|---|---|---|
| Vị trí | Nằm trong path | Nằm sau dấu ? |
| Mục đích thường gặp | Định danh tài nguyên hoặc phần tài nguyên | Lọc, tìm kiếm, sắp xếp, phân trang |
| Ví dụ | `/products/{productId}` | `/products?category=keyboard` |
| Trong OpenAPI | `in: path` | `in: query` |

Một path parameter cần có tên rõ ràng và phải được khai báo trong tài liệu. Theo OpenAPI, tham số có `in: path` luôn bắt buộc, do đó `required` phải là `true`. Query parameter có thể bắt buộc hoặc tùy chọn tùy theo hợp đồng.

Ví dụ khai báo:

```yaml
paths:
  /api/v1/products/{productId}:
    get:
      operationId: getProductById
      parameters:
        - name: productId
          in: path
          required: true
          description: Mã định danh sản phẩm
          schema:
            type: integer
            format: int64
        - name: includeDetails
          in: query
          required: false
          description: Có lấy thêm thông tin chi tiết hay không
          schema:
            type: boolean
            default: false
      responses:
        '200':
          description: Lấy sản phẩm thành công
```

Tên placeholder trong path phải khớp với tên path parameter. Chẳng hạn, path dùng `{productId}` thì operation phải có tham số `productId` với `in: path`. Không nên khai báo path `{productId}` nhưng parameter lại mang tên `id`.

### 2.2. Quy tắc đặt tên path

Một số nguyên tắc giúp path ổn định và dễ đọc:

1. Dùng danh từ để biểu diễn tài nguyên; dùng HTTP method để biểu diễn thao tác thông thường.
2. Dùng một quy ước nhất quán cho chữ thường, dấu gạch nối và tên tài nguyên.
3. Đặt tên placeholder có ý nghĩa, chẳng hạn `{orderId}` thay vì `{x}`.
4. Dùng query parameter cho bộ lọc và phân trang thay vì tạo path riêng cho từng tổ hợp giá trị.
5. Tránh tạo nhiều path chỉ khác nhau ở dấu gạch chéo cuối hoặc cách viết hoa/thường.
6. Chọn một cách biểu diễn phiên bản API nhất quán. Nếu dùng version trong path, ví dụ `/api/v1/products`, hãy giữ quy ước đó trong toàn bộ API.

Path trong URL phân biệt chữ hoa và chữ thường theo quy tắc URI. Khả năng xử lý dấu gạch chéo cuối còn phụ thuộc cấu hình và phiên bản framework. Vì vậy, nên công bố một dạng URL chuẩn và dùng đúng dạng đó trong controller, tài liệu, client và kiểm thử.

### 2.3. Path template phải rõ ràng và không mơ hồ

OpenAPI cho phép dùng biểu thức trong ngoặc nhọn để biểu diễn phần biến đổi của path, ví dụ `/users/{userId}`. Hai template `/users/{userId}` và `/users/{name}` có cùng cấu trúc đường dẫn; việc đổi tên placeholder không tạo ra hai path khác nhau. Không khai báo chúng như hai path riêng để phân biệt hai tài nguyên.

Nếu có một path cụ thể và một path template cùng khớp, path cụ thể được ưu tiên theo quy tắc của OpenAPI. Ví dụ, `/users/me` cụ thể hơn `/users/{userId}`. Khi thiết kế route Spring, cũng cần kiểm tra thứ tự và điều kiện mapping để tránh các route cạnh tranh hoặc khó hiểu.

## 3. Ý nghĩa của các HTTP method

HTTP method thể hiện ý định của client đối với tài nguyên. Chọn đúng method giúp người đọc hiểu hợp đồng, giúp proxy/cache và công cụ kiểm thử áp dụng đúng ngữ nghĩa HTTP.

| Method | Mục đích thường gặp | Safe | Idempotent |
|---|---|---:|---:|
| `GET` | Đọc tài nguyên hoặc collection | Có | Có |
| `HEAD` | Lấy metadata tương tự GET nhưng không có response body | Có | Có |
| `POST` | Tạo tài nguyên trong collection hoặc thực hiện xử lý | Không | Không mặc định |
| `PUT` | Tạo hoặc thay thế trạng thái tài nguyên tại URI đã biết | Không | Có |
| `PATCH` | Áp dụng thay đổi một phần lên tài nguyên | Không | Không mặc định |
| `DELETE` | Xóa tài nguyên | Không | Có |
| `OPTIONS` | Hỏi các tùy chọn giao tiếp được hỗ trợ | Có | Có |
| `TRACE` | Chẩn đoán đường đi của request qua các proxy | Có | Có |

**Safe** có nghĩa thao tác được định nghĩa là chỉ đọc, không yêu cầu server thay đổi trạng thái tài nguyên. **Idempotent** có nghĩa gửi cùng một request nhiều lần có hiệu quả dự kiến trên trạng thái server giống như gửi một lần. Idempotent không có nghĩa mọi lần gọi phải trả về response giống hệt nhau: ví dụ lần DELETE đầu có thể trả 204, lần sau có thể trả 404, nhưng trạng thái cuối vẫn là tài nguyên đã bị xóa.

### 3.1. GET và HEAD: đọc dữ liệu

GET dùng để lấy biểu diễn của tài nguyên. Tham số lọc, sắp xếp và phân trang thường được truyền qua query string:

`GET /api/v1/products?category=keyboard&size=20`

GET nên không mang ý định thay đổi trạng thái nghiệp vụ. Tránh thiết kế endpoint mà GET lại tạo đơn hàng, trừ tiền hoặc thay đổi dữ liệu. Request body của GET không có ngữ nghĩa chung được xác định rộng rãi và có thể không được một số thành phần trung gian hỗ trợ; hãy dùng query parameter hoặc một thiết kế request khác khi cần truyền điều kiện tìm kiếm phức tạp.

HEAD tương tự GET nhưng server không gửi response body. Nó hữu ích khi client chỉ cần kiểm tra metadata như header hoặc sự tồn tại của tài nguyên. Nếu framework tự hỗ trợ HEAD thông qua GET, cần kiểm tra mapping thực tế và tài liệu được sinh ra để bảo đảm hành vi công bố phù hợp.

### 3.2. POST: tạo mới hoặc xử lý

POST thường được dùng để tạo một phần tử mới trong collection:

`POST /api/v1/products`

Request body có thể chứa dữ liệu cần tạo:

```json
{
  "name": "Bàn phím cơ",
  "price": 1250000
}
```

Nếu tạo thành công, API thường trả `201 Created`; response có thể kèm biểu diễn tài nguyên mới hoặc header `Location` trỏ đến URI của tài nguyên. POST cũng có thể dùng cho các thao tác xử lý mà không phù hợp với ngữ nghĩa GET, PUT hay PATCH.

POST không mặc định idempotent. Nếu client gửi lại request do timeout, server có thể tạo thêm một tài nguyên khác. Với nghiệp vụ cần chống tạo trùng, có thể thiết kế cơ chế idempotency key hoặc một quy trình xác nhận phù hợp.

### 3.3. PUT: thay thế trạng thái tài nguyên

PUT thường cập nhật hoặc thay thế biểu diễn tài nguyên tại URI đã biết:

`PUT /api/v1/products/42`

Request thể hiện trạng thái mà client muốn đặt cho tài nguyên theo hợp đồng của API. PUT có ngữ nghĩa idempotent: gửi lại cùng request nhiều lần không làm thay đổi kết quả trạng thái dự kiến sau lần đầu. Cần định nghĩa rõ API yêu cầu toàn bộ biểu diễn hay hỗ trợ trường tùy chọn, để client không vô tình làm mất dữ liệu khi bỏ sót field.

### 3.4. PATCH: cập nhật một phần

PATCH dùng để áp dụng một tập thay đổi lên tài nguyên:

`PATCH /api/v1/products/42`

Nội dung request phụ thuộc định dạng patch mà API công bố, chẳng hạn JSON Merge Patch hoặc JSON Patch, hoặc một DTO cập nhật riêng được mô tả rõ. Không nên mặc định PATCH luôn có cùng cấu trúc với DTO tạo mới.

PATCH không mặc định idempotent. Một bản patch đặt `price` thành một giá trị cố định có thể idempotent, nhưng một thao tác tăng giá thêm 10% mỗi lần gửi sẽ không idempotent. Hãy xác định hành vi theo định dạng và quy tắc nghiệp vụ cụ thể.

### 3.5. DELETE: xóa tài nguyên

DELETE dùng để yêu cầu xóa tài nguyên tại URI:

`DELETE /api/v1/products/42`

API thường trả `204 No Content` nếu xóa thành công mà không cần body, hoặc `200 OK` nếu trả kết quả mô tả. DELETE có ngữ nghĩa idempotent về hiệu quả dự kiến, dù response giữa các lần gọi có thể khác nhau. Tránh yêu cầu request body cho DELETE vì ngữ nghĩa body không được định nghĩa chung và hỗ trợ của các thành phần trung gian có thể khác nhau.

### 3.6. OPTIONS và TRACE

OPTIONS cho phép client hỏi các tùy chọn giao tiếp được hỗ trợ. Nó cũng có vai trò trong quy trình CORS preflight của trình duyệt. TRACE phục vụ chẩn đoán đường đi request và thường bị vô hiệu hóa trong ứng dụng công khai nếu không có nhu cầu rõ ràng.

OpenAPI Path Item định nghĩa các operation cho GET, PUT, POST, DELETE, OPTIONS, HEAD, PATCH và TRACE. Không phải mọi API đều cần công bố mọi method. Chỉ mô tả những thao tác ứng dụng thực sự hỗ trợ và có chủ đích cung cấp cho client.

## 4. Từ Spring MVC mapping đến OpenAPI path và operation

Trong Spring MVC, mapping thường được tạo từ hai cấp:

- Mapping trên class xác định tiền tố hoặc phạm vi chung của controller.
- Mapping trên method xác định phần path còn lại, HTTP method và các điều kiện nhận request.

Các annotation như `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping` và `@DeleteMapping` là dạng rút gọn của `@RequestMapping` với method tương ứng.

Ví dụ:

```java
@RestController
@RequestMapping("/api/v1/products")
@Tag(name = "Products", description = "API quản lý sản phẩm")
public class ProductController {

    @GetMapping("/{productId}")
    @Operation(
        operationId = "getProductById",
        summary = "Lấy thông tin một sản phẩm"
    )
    public ProductResponse getById(
        @PathVariable("productId") Long productId
    ) {
        // Gọi service để lấy sản phẩm.
        return productService.getById(productId);
    }

    @GetMapping
    @Operation(
        operationId = "listProducts",
        summary = "Liệt kê sản phẩm"
    )
    public List<ProductResponse> list(
        @RequestParam(required = false) String category
    ) {
        return productService.findAll(category);
    }

    @PostMapping
    @Operation(
        operationId = "createProduct",
        summary = "Tạo sản phẩm"
    )
    public ProductResponse create(
        @RequestBody CreateProductRequest request
    ) {
        return productService.create(request);
    }
}
```

Trong ví dụ, tiền tố `/api/v1/products` từ class được kết hợp với `/{productId}` trên method, tạo thành path `/api/v1/products/{productId}`. Method `getById` tạo operation GET. Method `list` tạo operation GET trên collection `/api/v1/products`, còn `create` tạo operation POST trên cùng path collection.

Springdoc thu thập mapping của Spring và metadata OpenAPI để đưa các operation vào tài liệu. Annotation `@Operation` có thể bổ sung `summary`, `description`, `operationId`, `tags`, `deprecated` và nhiều thuộc tính mô tả khác. Annotation `@Parameter`, `@RequestBody`, `@ApiResponse` và `@Schema` giúp mô tả chi tiết hơn các thành phần của hợp đồng.

### 4.1. Các điều kiện mapping bổ sung

`@RequestMapping` của Spring có thể giới hạn request bằng nhiều điều kiện, ngoài path và method:

- `params`: yêu cầu query parameter có mặt hoặc có giá trị cụ thể.
- `headers`: yêu cầu một HTTP header có mặt hoặc thỏa giá trị.
- `consumes`: giới hạn Content-Type của request.
- `produces`: giới hạn kiểu nội dung response có thể tạo.

Ví dụ:

```java
@PostMapping(
    path = "/imports",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ImportResult importFile(
    @RequestPart("file") MultipartFile file
) {
    return importService.process(file);
}
```

Các điều kiện `consumes` và `produces` liên quan trực tiếp đến media type của request body và response, vì vậy cần được phản ánh trong `requestBody.content` hoặc `responses.content` của OpenAPI. Springdoc có thể suy ra nhiều thông tin từ kiểu tham số, kiểu trả về và annotation, nhưng mô tả nghiệp vụ vẫn cần được kiểm tra.

Một giới hạn quan trọng của OpenAPI là mỗi cặp **path + HTTP method** chỉ có một operation. Spring có thể phân biệt nhiều handler cùng path và method bằng điều kiện `params` hoặc `headers`, nhưng OpenAPI không thể tạo hai operation độc lập có cùng cặp path và method. Khi gặp trường hợp này, hãy cân nhắc gộp các biến thể vào một operation và mô tả tham số/response tương ứng, hoặc thiết kế các path riêng biệt để hợp đồng không mơ hồ. Không dựa vào `operationId` để phân biệt hai route trùng cặp path + method.

### 4.2. Tách path parameter khỏi query parameter trong controller

Ví dụ controller dưới đây thể hiện rõ hai loại tham số:

```java
@GetMapping("/{productId}")
public ProductResponse getById(
    @PathVariable("productId") Long productId,
    @RequestParam(defaultValue = "false") boolean includeDetails
) {
    return productService.getById(productId, includeDetails);
}
```

`@PathVariable` liên kết với placeholder trong path. `@RequestParam` nhận giá trị từ query string. Springdoc thường có thể nhận biết vị trí tham số từ annotation Spring; có thể dùng `@Parameter` để bổ sung tên, mô tả, ví dụ hoặc ràng buộc schema khi cần.

Nên ghi rõ tên trong `@PathVariable("productId")` nếu muốn mapping thể hiện rõ ràng và tránh phụ thuộc vào việc compiler có lưu tên tham số hay không. Tên trong OpenAPI phải khớp placeholder của path.

## 5. Định danh operation bằng operationId

Trong OpenAPI, `operationId` là một chuỗi tùy chọn dùng để định danh operation. Nếu được cung cấp, giá trị này phải duy nhất trong toàn bộ tài liệu OpenAPI. Nó thường được các công cụ sinh client SDK dùng làm cơ sở đặt tên phương thức.

Ví dụ:

```yaml
paths:
  /api/v1/products/{productId}:
    get:
      operationId: getProductById
      summary: Lấy thông tin một sản phẩm
    delete:
      operationId: deleteProduct
      summary: Xóa một sản phẩm
```

Hai operation có cùng path nhưng method khác nhau cần `operationId` khác nhau nếu cùng được khai báo. Các operation ở path khác nhau cũng không được dùng trùng `operationId`.

### 5.1. Quy ước đặt operationId

Một quy ước thực tế là dùng tên hàm theo camelCase, thể hiện hành động và tài nguyên:

| Operation | operationId gợi ý |
|---|---|
| GET `/products` | `listProducts` |
| GET `/products/{productId}` | `getProductById` |
| POST `/products` | `createProduct` |
| PUT `/products/{productId}` | `replaceProduct` |
| PATCH `/products/{productId}` | `updateProduct` |
| DELETE `/products/{productId}` | `deleteProduct` |

Nên chọn tên có nghĩa, ổn định và không phụ thuộc vào tên class controller. Một số lưu ý:

1. Dùng một quy ước đặt tên thống nhất trong toàn bộ API.
2. Bảo đảm mỗi operationId duy nhất trong một tài liệu, kể cả giữa các tag hoặc nhóm path.
3. Tránh tên quá chung như `get`, `save` hoặc `process`.
4. Không xem operationId là URL hay tên route; đổi operationId không làm thay đổi endpoint HTTP.
5. Hạn chế đổi operationId tùy tiện sau khi đã phát hành SDK sinh tự động, vì client có thể phụ thuộc vào tên phương thức được sinh ra.

### 5.2. Khai báo operationId bằng Springdoc

Có thể khai báo trực tiếp bằng `@Operation`:

```java
@GetMapping("/{productId}")
@Operation(
    operationId = "getProductById",
    summary = "Lấy thông tin một sản phẩm",
    description = "Tìm sản phẩm theo mã định danh."
)
public ProductResponse getById(
    @PathVariable("productId") Long productId
) {
    return productService.getById(productId);
}
```

Nếu không khai báo tường minh, Springdoc có thể tạo operationId dựa trên thông tin method theo cấu hình và phiên bản thư viện. Với API công khai hoặc tài liệu được dùng để sinh SDK, khai báo tường minh giúp kiểm soát tên ổn định hơn. Sau khi sinh tài liệu, cần kiểm tra không có operationId trùng.

## 6. Ví dụ tài liệu OpenAPI cho một nhóm operation

Ví dụ sau kết hợp path collection, path item có parameter dùng chung và nhiều HTTP method:

```yaml
openapi: 3.0.3
info:
  title: Product API
  version: 1.0.0
paths:
  /api/v1/products:
    get:
      operationId: listProducts
      tags:
        - Products
      summary: Liệt kê sản phẩm
      parameters:
        - name: category
          in: query
          required: false
          schema:
            type: string
        - name: page
          in: query
          required: false
          schema:
            type: integer
            minimum: 0
            default: 0
      responses:
        '200':
          description: Danh sách sản phẩm
    post:
      operationId: createProduct
      tags:
        - Products
      summary: Tạo sản phẩm
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Sản phẩm đã được tạo
        '400':
          description: Dữ liệu không hợp lệ
  /api/v1/products/{productId}:
    parameters:
      - name: productId
        in: path
        required: true
        description: Mã định danh sản phẩm
        schema:
          type: integer
          format: int64
    get:
      operationId: getProductById
      tags:
        - Products
      summary: Lấy thông tin sản phẩm
      responses:
        '200':
          description: Sản phẩm được tìm thấy
        '404':
          description: Không tìm thấy sản phẩm
    put:
      operationId: replaceProduct
      tags:
        - Products
      summary: Thay thế thông tin sản phẩm
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ReplaceProductRequest'
      responses:
        '200':
          description: Sản phẩm đã được cập nhật
        '404':
          description: Không tìm thấy sản phẩm
    delete:
      operationId: deleteProduct
      tags:
        - Products
      summary: Xóa sản phẩm
      responses:
        '204':
          description: Đã xóa sản phẩm
        '404':
          description: Không tìm thấy sản phẩm
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
      properties:
        name:
          type: string
        price:
          type: number
          format: double
    ReplaceProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
        price:
          type: number
          format: double
```

Trong ví dụ, parameter `productId` được khai báo ở cấp Path Item nên áp dụng cho tất cả operation của path đó. Nếu một operation cần bổ sung parameter riêng, khai báo trong operation. Nếu cùng tên và cùng vị trí `in` được khai báo ở cả hai cấp, parameter ở operation có thể ghi đè parameter cấp path theo quy tắc OpenAPI.

Lưu ý: ví dụ tập trung vào cấu trúc path và operation, nên response chưa khai báo schema chi tiết. Trong tài liệu thực tế, hãy bổ sung `content` và `$ref` đến schema response để client biết chính xác cấu trúc dữ liệu trả về.

## 7. Các lỗi thiết kế và mô tả thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng GET để thay đổi dữ liệu | Cache, crawler hoặc client có thể gọi nhầm thao tác ghi | Chọn POST, PUT, PATCH hoặc DELETE theo ngữ nghĩa |
| Đặt động từ vào mọi URL | Route dài, lặp ý nghĩa của HTTP method | Dùng danh từ tài nguyên và HTTP method |
| Placeholder không khớp parameter | Tài liệu OpenAPI không hợp lệ hoặc khó sinh client | Đồng bộ tên `{productId}` với parameter `productId` |
| Path parameter không có `required: true` | Vi phạm yêu cầu mô tả path parameter | Đặt `required: true` |
| Hai path chỉ khác tên placeholder | Tài liệu có path template trùng cấu trúc | Gộp thành một path và thống nhất tên biến |
| Hai handler Spring cùng path và method, chỉ khác điều kiện params/headers | OpenAPI không có hai operation riêng để biểu diễn | Gộp thành một operation hoặc thiết kế path riêng |
| operationId trùng | Công cụ sinh client có thể báo lỗi hoặc tạo tên phương thức xung đột | Đặt operationId duy nhất trên toàn tài liệu |
| Đổi operationId sau khi phát hành SDK | Mã client được sinh có thể thay đổi tên hàm | Quản lý operationId như một phần hợp đồng công khai |
| Path khác nhau chỉ bởi dấu / cuối | Client có thể gọi không nhất quán; mapping phụ thuộc cấu hình | Công bố một dạng canonical path |
| Công bố method không được triển khai | Client gọi operation nhận 404/405 hoặc lỗi khác | Đối chiếu tài liệu với mapping thực tế |

## 8. Phân biệt lỗi path và lỗi method khi gọi API

Khi request không đi đến handler mong muốn, cần kiểm tra cả path lẫn HTTP method. Một số trạng thái HTTP thường giúp khoanh vùng:

- **404 Not Found:** không có tài nguyên hoặc route phù hợp với path theo cách ứng dụng xử lý. Cần xem ứng dụng có cố ý trả 404 khi không tìm thấy tài nguyên hay không.
- **405 Method Not Allowed:** path được nhận diện nhưng HTTP method gửi lên không được hỗ trợ cho tài nguyên đó. Response thường có thể chứa header `Allow` liệt kê các method được phép.
- **400 Bad Request:** request có thể đã khớp route nhưng tham số hoặc nội dung không hợp lệ, ví dụ không chuyển đổi được `productId` sang kiểu số.
- **406 Not Acceptable:** server không thể tạo response theo media type mà client yêu cầu qua `Accept`.
- **415 Unsupported Media Type:** `Content-Type` của request không phù hợp với nội dung mà endpoint nhận.

Không phải mọi ứng dụng đều ánh xạ lỗi giống nhau; exception handler, gateway và cấu hình bảo mật có thể thay đổi response quan sát được. Hãy đối chiếu log Spring, mapping đã đăng ký và tài liệu OpenAPI thay vì chỉ dựa vào mã trạng thái.

Có thể kiểm tra route bằng curl:

```bash
# Đọc một sản phẩm
curl -i -X GET http://localhost:8080/api/v1/products/42

# Gửi POST để tạo sản phẩm
curl -i -X POST http://localhost:8080/api/v1/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Bàn phím cơ","price":1250000}'

# Gửi method không được route hỗ trợ để quan sát phản hồi
curl -i -X PATCH http://localhost:8080/api/v1/products/42
```

Request PATCH cuối chỉ có ý nghĩa kiểm tra nếu endpoint thực tế không khai báo PATCH hoặc yêu cầu body. Trong hệ thống thật, hãy dùng dữ liệu thử nghiệm và môi trường phù hợp.

## 9. Quy trình đối chiếu Spring mapping với tài liệu OpenAPI

Sau khi thêm hoặc sửa controller, nên kiểm tra hợp đồng theo các bước:

1. **Xác định path hoàn chỉnh:** ghép mapping cấp class với mapping cấp method và kiểm tra placeholder.
2. **Xác định method:** ghi rõ endpoint hỗ trợ GET, POST, PUT, PATCH, DELETE hay method khác.
3. **Phân loại tham số:** xác định từng tham số nằm trong path, query, header hay cookie; kiểm tra tên và tính bắt buộc.
4. **Kiểm tra request body:** xác định method có nhận body hay không, schema và media type nào được hỗ trợ.
5. **Kiểm tra response:** mô tả mã trạng thái, response body, schema và header có ý nghĩa.
6. **Đặt operationId:** bảo đảm duy nhất, dễ hiểu và ổn định.
7. **Đọc tài liệu sinh ra:** mở endpoint JSON/YAML của springdoc, tìm path và xác minh từng operation.
8. **Thử request:** dùng Swagger UI hoặc curl để xác nhận URL, method, parameter và nội dung request khớp với hành vi ứng dụng.

Với ứng dụng dùng springdoc, endpoint mặc định thường là `/v3/api-docs` cho JSON và `/v3/api-docs.yaml` cho YAML. Nếu dự án đã tùy chỉnh `springdoc.api-docs.path`, hãy dùng đường dẫn đã cấu hình. Swagger UI giúp quan sát các operation theo tag, nhưng tài liệu JSON/YAML vẫn cần được kiểm tra trực tiếp khi dùng làm đầu vào cho công cụ khác.

Khi đưa tài liệu vào CI, có thể bổ sung kiểm tra tự động để phát hiện operationId trùng, path parameter thiếu, thay đổi method ngoài dự kiến hoặc sai lệch hợp đồng. Việc so sánh đặc tả giữa các phiên bản cũng giúp phát hiện thay đổi có thể ảnh hưởng đến client hiện hữu.

## 10. Ghi nhớ

- Một operation trong OpenAPI được xác định bởi cặp **path + HTTP method**.
- Nhiều method có thể cùng tồn tại trên một path; mỗi method mô tả một thao tác riêng.
- Path parameter định danh phần tài nguyên trong URL; query parameter thường dùng cho lọc, sắp xếp và phân trang.
- GET và HEAD dành cho thao tác đọc; POST thường tạo hoặc xử lý; PUT thay thế; PATCH cập nhật một phần; DELETE xóa.
- Spring kết hợp mapping cấp class và method để định tuyến request; Springdoc dùng mapping và metadata để tạo operation.
- `operationId` là tên định danh tùy chọn nhưng phải duy nhất trong tài liệu nếu được khai báo; nó không thay đổi URL.
- Tài liệu OpenAPI cần phản ánh đúng route, method, tham số và hành vi thực tế của controller.

Khi thiết kế endpoint cho Spring Boot, hãy bắt đầu từ tài nguyên và hợp đồng HTTP, sau đó khai báo mapping cùng metadata OpenAPI tương ứng. Cách làm này giúp tài liệu do springdoc sinh ra dễ đọc, ổn định cho client và thuận tiện để kiểm thử trong suốt vòng đời API.
