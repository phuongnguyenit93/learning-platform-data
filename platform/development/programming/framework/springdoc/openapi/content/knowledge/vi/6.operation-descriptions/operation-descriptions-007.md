# Mô tả nhiều phương thức HTTP hoặc nhiều mapping trên một handler

Trong Spring Boot, một handler method có thể được gắn với nhiều phương thức HTTP hoặc nhiều đường dẫn bằng `@RequestMapping`. Cách khai báo này hữu ích khi cần duy trì endpoint tương thích cũ, cung cấp nhiều alias URL hoặc dùng chung một cách xử lý cho các request có cùng ý nghĩa. Khi sinh OpenAPI, cần nhớ rằng một operation được xác định bởi cặp **đường dẫn và phương thức HTTP**. Vì vậy, một handler Spring có thể tương ứng với nhiều operation trong tài liệu.

springdoc-openapi đọc các mapping của Spring và chuyển chúng thành cấu trúc `paths` của OpenAPI. Mỗi path có thể chứa các operation như `get`, `post`, `put`, `delete`, `patch`, `head`, `options` hoặc `trace`. Nếu một handler được ánh xạ đến nhiều cặp path/method, tài liệu cần thể hiện từng cặp rõ ràng để client biết request nào được hỗ trợ.

## 1. Phân biệt handler method, mapping và OpenAPI operation

Ba khái niệm này liên quan với nhau nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Handler method | Phương thức Java xử lý request trong controller | `searchOrders(...)` |
| Spring request mapping | Tập điều kiện để Spring chọn handler: path, HTTP method, params, headers, consumes, produces | `/api/orders/search`, `GET` hoặc `POST` |
| OpenAPI operation | Mô tả một thao tác HTTP cụ thể tại một path | `GET /api/orders/search` |

Trong OpenAPI, một Path Item có thể chứa tối đa một operation cho mỗi phương thức HTTP. Ví dụ, cùng path `/api/orders` có thể có `get` để đọc danh sách, `post` để tạo đơn hàng và `delete` để xóa tài nguyên nếu thiết kế API cho phép. Hai operation này có thể gọi đến cùng một handler Spring trong trường hợp đặc biệt, nhưng vẫn là hai operation riêng trong hợp đồng.

Một handler cũng có thể được đăng ký ở nhiều path. Khi đó, mỗi path cần xuất hiện thành một Path Item trong OpenAPI. Ví dụ `/api/orders/{id}` và `/legacy/orders/{id}` có thể cùng được xử lý bởi một phương thức Java, nhưng client nhìn thấy hai URL riêng.

## 2. Một handler xử lý nhiều phương thức HTTP

`@RequestMapping` hỗ trợ thuộc tính `method` nhận một hoặc nhiều giá trị `RequestMethod`. Ví dụ sau minh họa một endpoint tìm kiếm cũ chấp nhận cả GET và POST để tương thích với hai nhóm client. Cả hai phương thức dùng cùng query parameter và cùng kết quả:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderSearchController {

    @Operation(
        summary = "Tìm kiếm đơn hàng theo khách hàng",
        description = "Endpoint tương thích cũ, chấp nhận GET và POST với cùng tham số customerId."
    )
    @RequestMapping(
        path = "/search",
        method = { RequestMethod.GET, RequestMethod.POST },
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public List<OrderSummary> search(
            @Parameter(description = "Mã khách hàng", example = "CUS-100")
            @RequestParam("customerId") String customerId) {
        return orderService.searchByCustomer(customerId);
    }
}
```

Với mapping trên, Spring đăng ký hai phương thức HTTP cho cùng handler và cùng path. Về mặt cấu trúc, OpenAPI biểu diễn hai operation riêng:

```yaml
paths:
  /api/orders/search:
    get:
      summary: Tìm kiếm đơn hàng theo khách hàng
      description: Endpoint tương thích cũ, chấp nhận GET và POST với cùng tham số customerId.
      parameters:
        - name: customerId
          in: query
          required: true
          schema:
            type: string
    post:
      summary: Tìm kiếm đơn hàng theo khách hàng
      description: Endpoint tương thích cũ, chấp nhận GET và POST với cùng tham số customerId.
      parameters:
        - name: customerId
          in: query
          required: true
          schema:
            type: string
```

Đoạn YAML trên rút gọn các response và metadata khác để tập trung vào hai operation. Metadata đặt trên một handler dùng chung có thể được áp dụng cho các operation tương ứng. Vì vậy, chỉ dùng một handler nhiều phương thức khi các phương thức có cùng mục đích, cách nhận dữ liệu, kết quả và chính sách bảo mật.

Nếu GET và POST có ý nghĩa khác nhau, chẳng hạn GET đọc dữ liệu còn POST tạo hoặc cập nhật dữ liệu, nên tách thành hai handler:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã"
    )
    public OrderResponse getById(@PathVariable long id) {
        return orderService.getById(id);
    }

    @PostMapping
    @Operation(
        operationId = "createOrder",
        summary = "Tạo đơn hàng"
    )
    @ApiResponse(responseCode = "201", description = "Đơn hàng đã được tạo")
    public OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

Khi tách handler, mỗi operation có thể có `summary`, `description`, `operationId`, request body, response, mã trạng thái và yêu cầu bảo mật riêng. Đây thường là cách rõ ràng hơn khi hợp đồng của các phương thức HTTP khác nhau.

## 3. Một handler được ánh xạ đến nhiều đường dẫn

Thuộc tính `path` hoặc `value` của `@RequestMapping` có thể nhận một mảng đường dẫn. Spring gọi cùng handler khi request khớp với một trong các đường dẫn đó.

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping({ "/{id}", "/legacy/{id}" })
    @Operation(summary = "Lấy thông tin đơn hàng")
    public OrderResponse getById(@PathVariable long id) {
        return orderService.getById(id);
    }
}
```

Mapping này tạo hai đường dẫn truy cập:

```text
GET /api/orders/{id}
GET /api/orders/legacy/{id}
```

Trong OpenAPI, hai đường dẫn được biểu diễn thành hai Path Item, mỗi Path Item có operation `get`. Đây là cách có thể dùng trong giai đoạn chuyển đổi URL hoặc khi cần giữ alias tương thích cho client cũ.

Nếu mỗi URL cần nội dung mô tả, tag hoặc `operationId` khác nhau, một handler duy nhất sẽ không đủ linh hoạt vì annotation trên method được dùng chung. Có thể tách thành các handler nhỏ gọi cùng service:

```java
@GetMapping("/{id}")
@Operation(operationId = "getOrderById", summary = "Lấy đơn hàng theo mã")
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}

@GetMapping("/legacy/{id}")
@Operation(operationId = "getLegacyOrderById", summary = "Lấy đơn hàng qua URL cũ")
public OrderResponse getLegacyById(@PathVariable long id) {
    return orderService.getById(id);
}
```

Trong OpenAPI, `operationId` phải duy nhất trong toàn bộ tài liệu. Nếu khai báo cùng một `operationId` cho các path alias, tài liệu có thể vi phạm quy tắc này và gây nhầm lẫn cho công cụ sinh client. Hãy kiểm tra output và validator; nếu cần định danh riêng cho từng operation, dùng các handler riêng với `operationId` riêng.

## 4. Kết hợp mapping cấp lớp và cấp phương thức

Spring cho phép đặt `@RequestMapping` ở cấp controller để khai báo phần path chung, sau đó đặt mapping ở từng handler để khai báo phần path và điều kiện cụ thể. Spring kết hợp hai cấp để tạo đường dẫn đầy đủ.

```java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    @GetMapping
    @Operation(operationId = "listOrders", summary = "Liệt kê đơn hàng")
    public List<OrderSummary> list() {
        return orderService.findAll();
    }

    @GetMapping("/{id}")
    @Operation(operationId = "getOrderById", summary = "Lấy đơn hàng theo mã")
    public OrderResponse get(@PathVariable long id) {
        return orderService.getById(id);
    }

    @PostMapping
    @Operation(operationId = "createOrder", summary = "Tạo đơn hàng")
    public OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

Kết quả là ba operation tại `/api/v1/orders` và `/api/v1/orders/{id}`. Phần prefix cấp lớp giúp tránh lặp đường dẫn và làm cho cấu trúc controller dễ đọc. Khi tài liệu OpenAPI được sinh, đường dẫn đầy đủ cần được kiểm tra trong `paths`, không chỉ dựa vào path ghi ở annotation method.

Không nên đặt nhiều annotation mapping độc lập trên cùng một phần tử, ví dụ:

```java
// Không nên: hai annotation mapping cùng nằm trên một method.
@GetMapping("/search")
@PostMapping("/search")
public List<OrderSummary> search() {
    return orderService.search();
}
```

Spring cảnh báo khi phát hiện nhiều `@RequestMapping` hoặc annotation kết hợp như `@GetMapping`, `@PostMapping` trên cùng phần tử; chỉ mapping đầu tiên được dùng. Nếu thực sự cần nhiều HTTP method trên cùng handler, hãy khai báo một `@RequestMapping` với mảng `method`. Nếu các method có ý nghĩa khác nhau, tạo handler riêng.

## 5. Nhiều điều kiện mapping trên cùng path và HTTP method

Ngoài path và HTTP method, Spring có thể phân biệt handler bằng các điều kiện:

| Thuộc tính mapping | Mục đích | Cách thể hiện liên quan trong OpenAPI |
| --- | --- | --- |
| `params` | Điều kiện theo query parameter có mặt, vắng mặt hoặc có giá trị cụ thể | Khai báo parameter, `required`, `enum` và mô tả điều kiện |
| `headers` | Điều kiện theo request header | Khai báo header parameter và mô tả giá trị cần gửi |
| `consumes` | Giới hạn `Content-Type` của request | Các media type trong `requestBody.content` |
| `produces` | Giới hạn kiểu response theo `Accept` | Các media type trong `responses.content` |
| `path` | Một hoặc nhiều URL pattern | Các Path Item riêng trong `paths` |
| `method` | Một hoặc nhiều phương thức HTTP | Operation riêng theo từng method trong Path Item |

Ví dụ, một controller có thể nhận nhiều định dạng request:

```java
@PostMapping(
    path = "/import",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(summary = "Nhập đơn hàng")
public OrderResponse importOrder(@Valid @RequestBody ImportOrderRequest request) {
    return orderService.importOrder(request);
}
```

Nếu các converter của ứng dụng thực sự hỗ trợ cả JSON và XML cho kiểu `ImportOrderRequest`, OpenAPI có thể mô tả một request body với nhiều media type. Trong cấu trúc OpenAPI, chúng nằm dưới cùng operation:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/ImportOrderRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/ImportOrderRequest'
```

Đây vẫn là một operation `POST`, không phải hai operation khác nhau. `consumes` và `produces` mô tả loại nội dung được chấp nhận hoặc trả về; chúng không làm tăng số HTTP method trong OpenAPI.

Điều kiện `params` hoặc `headers` có thể được Spring dùng để chọn một trong nhiều handler cùng path và method. Tuy nhiên, OpenAPI chỉ có một operation cho một cặp path/method. Nếu nhiều handler có cùng `GET /api/orders` nhưng khác `params` hoặc `headers`, không thể biểu diễn chúng thành hai operation `get` độc lập. Hãy mô tả các tham số và giá trị hợp lệ trong một operation, hoặc thiết kế path/method riêng nếu chúng thực sự là hai hành vi API khác nhau.

## 6. Overloaded handler cùng path và HTTP method

Java cho phép overload nhiều method cùng tên nhưng khác danh sách tham số. Spring cũng có thể đăng ký nhiều handler cho cùng path và HTTP method nếu có điều kiện phân biệt như `consumes`, `params` hoặc `headers`. Dù vậy, OpenAPI không cho phép hai operation `post` riêng biệt tại cùng một path.

Ví dụ, hai handler sau nhận hai kiểu body khác nhau nhưng cùng `POST /api/orders/import`:

```java
@PostMapping(path = "/import", consumes = MediaType.APPLICATION_JSON_VALUE)
public ImportResult importJson(@RequestBody JsonImportRequest request) {
    return orderService.importJson(request);
}

@PostMapping(path = "/import", consumes = MediaType.APPLICATION_XML_VALUE)
public ImportResult importXml(@RequestBody XmlImportRequest request) {
    return orderService.importXml(request);
}
```

springdoc xử lý các handler overload cùng class, cùng HTTP method và cùng path như một endpoint OpenAPI. Với các biến thể tham số khác nhau, tài liệu có thể biểu diễn schema kết hợp bằng `oneOf`; với nhiều consuming media type, request body có thể chứa nhiều content type. Hãy kiểm tra tài liệu thực tế để xác nhận schema và media type được hợp nhất như mong đợi.

Nếu dùng `@Operation` trên nhiều method overload, metadata có thể bị ghi đè khi springdoc hợp nhất chúng. FAQ của springdoc khuyến nghị đặt `@Operation` ở một trong các method overload. Nếu mỗi biến thể cần summary, response, bảo mật hoặc quy tắc nghiệp vụ độc lập, nên xem xét đổi thiết kế để tạo các operation có path hoặc method khác nhau.

## 7. Operation metadata khi handler được dùng chung

`@Operation` mô tả operation mà springdoc sinh ra. Khi một handler được ánh xạ đến nhiều method hoặc nhiều path, các annotation trên handler là metadata dùng chung. Các trường thường cần quan tâm gồm:

- `summary`: câu ngắn cho biết thao tác làm gì;
- `description`: điều kiện sử dụng, khác biệt giữa phương thức hoặc URL alias;
- `operationId`: tên duy nhất của operation trong tài liệu;
- `tags`: nhóm operation trong Swagger UI;
- `deprecated`: đánh dấu operation cũ không còn được khuyến nghị;
- `security`: yêu cầu xác thực nếu khác với cấu hình chung;
- `responses`: mã trạng thái và nội dung trả về.

Với endpoint tương thích cũ, có thể dùng `deprecated = true` để báo cho client biết cần chuyển sang endpoint mới. Tuy nhiên, khi một handler dùng chung cho cả URL mới và URL cũ, `deprecated` sẽ áp dụng cho operation được sinh từ handler đó. Nếu chỉ muốn đánh dấu URL cũ, hãy tách thành hai handler để có metadata riêng.

Ví dụ tách alias cũ và mới:

```java
@GetMapping("/{id}")
@Operation(
    operationId = "getOrderById",
    summary = "Lấy đơn hàng theo mã"
)
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}

@GetMapping("/legacy/{id}")
@Operation(
    operationId = "getLegacyOrderById",
    summary = "Lấy đơn hàng qua URL cũ",
    description = "Duy trì để hỗ trợ client cũ; hãy chuyển sang GET /api/orders/{id}.",
    deprecated = true
)
public OrderResponse getLegacyById(@PathVariable long id) {
    return orderService.getById(id);
}
```

## 8. HEAD, OPTIONS và mapping không khai báo method

Spring xử lý một số phương thức HTTP theo quy ước của framework:

- Mapping `GET` cũng hỗ trợ `HEAD` một cách tự động trong Spring MVC; thông thường không cần tạo handler `HEAD` riêng chỉ để lấy headers mà không có response body.
- Với `OPTIONS`, Spring MVC mặc định có thể trả header `Allow` chứa các phương thức được khai báo cho URL phù hợp. Không cần tạo operation `OPTIONS` riêng nếu chỉ dùng hành vi tự động này.
- Nếu API có hành vi `HEAD` hoặc `OPTIONS` riêng cần công bố cho client, hãy xác định rõ handler và kiểm tra OpenAPI output.

`@RequestMapping` không khai báo `method` có nghĩa là Spring có thể nhận mọi HTTP method phù hợp với các điều kiện mapping còn lại. Điều này thường quá rộng cho API công khai và khiến hợp đồng khó hiểu. Nên khai báo method rõ ràng bằng `@GetMapping`, `@PostMapping` hoặc `@RequestMapping(method = ...)` để giới hạn hành vi và làm tài liệu OpenAPI dễ kiểm tra.

## 9. Cách kiểm tra mapping sau khi sinh OpenAPI

Sau khi ứng dụng Spring Boot khởi động, mở endpoint tài liệu mặc định `/v3/api-docs` hoặc đường dẫn đã tùy chỉnh. Tìm path cần kiểm tra và xác nhận:

1. Mọi path pattern dự kiến đều xuất hiện dưới `paths`.
2. Mỗi path có đúng operation theo HTTP method đã khai báo.
3. `summary`, `description`, `tags`, `deprecated` và `operationId` phản ánh đúng ý nghĩa của operation.
4. `parameters` chứa path, query và header parameter cần thiết; thuộc tính `required` và schema phù hợp.
5. `requestBody.content` chứa các media type mà controller thực sự nhận.
6. `responses` mô tả đúng mã trạng thái và media type được trả về.
7. Không có `operationId` trùng lặp và không có operation bị ghi đè do handler overload.

Ví dụ kiểm tra nhanh một phần tài liệu bằng `curl`:

```bash
curl -s http://localhost:8080/v3/api-docs
```

Với tài liệu lớn, có thể lưu response JSON rồi dùng JSONPath hoặc công cụ kiểm tra OpenAPI để xem riêng `paths`. Sau đó kiểm thử runtime từng tổ hợp path, HTTP method, query/header condition và content type để xác nhận Spring chọn đúng handler. Tài liệu sinh ra cho biết hợp đồng được công bố; chỉ request thực tế mới xác nhận được các điều kiện định tuyến và xử lý có hoạt động như mong muốn.

## 10. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy một HTTP method trong OpenAPI | `@RequestMapping` chỉ khai báo một method hoặc output bị lọc/ghi đè | Kiểm tra `method` trong mapping và `paths` của `/v3/api-docs` |
| Đặt `@GetMapping` và `@PostMapping` trên cùng method nhưng chỉ một mapping hoạt động | Spring không hỗ trợ nhiều mapping annotation trên cùng phần tử; chỉ mapping đầu tiên được dùng | Dùng một `@RequestMapping(method = {...})` hoặc tách handler |
| Alias path không xuất hiện | Path pattern chưa được khai báo trong mảng `path` hoặc bị lọc bởi cấu hình group | Kiểm tra mapping và `springdoc.paths-to-match` |
| Hai handler cùng path/method cho ra một operation | OpenAPI chỉ có một operation cho mỗi path/method; springdoc hợp nhất overload | Mô tả các biến thể trong cùng operation hoặc tách API thành path/method riêng |
| `operationId` trùng lặp | Nhiều path alias dùng chung giá trị `operationId` | Dùng handler riêng với ID khác nhau hoặc điều chỉnh metadata sau khi sinh |
| `consumes` có nhiều loại nhưng tài liệu chỉ có một schema | Converter hoặc annotation content chưa mô tả đủ media type | Kiểm tra converter thực tế và khai báo `@Content` cho từng media type nếu cần |
| Mô tả bị ghi đè giữa các handler overload | Nhiều `@Operation` cùng áp dụng cho một endpoint đã được hợp nhất | Chỉ đặt metadata operation ở một overload hoặc tách handler |
| Mapping không khai báo HTTP method gây tài liệu thiếu hoặc khó hiểu | Spring nhận nhiều method; không xác định rõ hợp đồng mong muốn | Khai báo method cụ thể và xác minh với phiên bản springdoc đang dùng |

## 11. Nguyên tắc thiết kế

Hãy dùng một handler cho nhiều HTTP method khi các phương thức thực sự có cùng mục đích và có thể chia sẻ request, response, mô tả và bảo mật. Dùng một handler cho nhiều path khi các URL chỉ là alias của cùng một thao tác. Với các phương thức hoặc URL có hành vi khác nhau, tách handler và dùng chung service ở tầng nghiệp vụ để mỗi operation có metadata chính xác.

Đặc biệt, hãy kiểm tra `operationId`, vì nhiều công cụ sinh client dựa vào trường này để tạo tên hàm. Đảm bảo mỗi operation có định danh duy nhất, mô tả rõ method/path, request và response. Đừng dựa vào việc code Java biên dịch thành công để kết luận tài liệu OpenAPI đã mô tả đúng mapping.

## 12. Tài liệu tham khảo chính thức

- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — cách kết hợp class-level/method-level mapping, mảng path, HTTP method và các điều kiện request; quy tắc không đặt nhiều mapping annotation trên cùng phần tử; hành vi HEAD và OPTIONS.
- [Springdoc-openapi — FAQ](https://springdoc.org/faq.html) — cách springdoc xử lý handler overload cùng path và HTTP method, nhiều consuming media type và tham số được hợp nhất.
- [OpenAPI Specification 3.1.1 — Path Item Object](https://spec.openapis.org/oas/v3.1.1.html#path-item-object) — cấu trúc path và các operation theo HTTP method.
- [OpenAPI Specification 3.1.1 — Operation Object](https://spec.openapis.org/oas/v3.1.1.html#operation-object) — metadata của từng operation và yêu cầu duy nhất của `operationId`.

Khi một handler có nhiều mapping, hãy xem output OpenAPI như bản đồ các cặp path/method mà client thực sự được phép gọi. Đối chiếu bản đồ này với mapping của Spring và kiểm thử từng điều kiện request giúp tài liệu phản ánh chính xác hành vi của ứng dụng.
