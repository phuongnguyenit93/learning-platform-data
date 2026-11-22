# Trùng `operationId`, path hoặc handler cho cùng HTTP method

Khi nhiều controller cùng khai báo một đường dẫn, cùng HTTP method hoặc cùng `operationId`, ứng dụng Spring Boot có thể không khởi động được, request có thể chọn handler không như mong đợi, hoặc OpenAPI document do Springdoc sinh ra không hợp lệ. Những lỗi này có liên quan nhưng thuộc các lớp khác nhau: Spring MVC đăng ký và chọn handler ở runtime, còn OpenAPI mô tả mỗi cặp path và HTTP method bằng một operation duy nhất.

Muốn xử lý đúng, trước tiên phải xác định lỗi xuất hiện ở đâu:

- **Ứng dụng không khởi động**: thường là xung đột mapping được phát hiện khi Spring đăng ký handler.
- **Ứng dụng chạy nhưng request bị ambiguous**: nhiều mapping cùng khớp một request và không có mapping nào được ưu tiên rõ ràng.
- **Ứng dụng chạy nhưng `/v3/api-docs` có lỗi hoặc document không hợp lệ**: cần kiểm tra operation, path, `operationId` và các customizer.
- **OpenAPI document trả 200 nhưng code generator/linter báo lỗi**: document có thể chứa `operationId` trùng, path template tương đương hoặc cấu trúc bị ghi đè khi merge.

Không nên sửa tất cả trường hợp bằng cách đổi tên method Java. Cần tìm đúng định danh bị trùng và đúng lớp chịu trách nhiệm.

## 1. Phân biệt ba loại xung đột

| Loại xung đột | Định danh cần kiểm tra | Hậu quả thường gặp |
|---|---|---|
| Trùng handler mapping | Path pattern + HTTP method + các điều kiện mapping | Spring báo `Ambiguous mapping` khi khởi động hoặc khi xử lý request |
| Trùng path operation | Path Item và HTTP method trong `paths` | Hai handler muốn chiếm cùng một operation; document có thể bị hợp nhất, ghi đè hoặc không biểu diễn được cả hai |
| Trùng `operationId` | Giá trị `operationId` giữa tất cả operation trong một document | OpenAPI validator hoặc client generator báo operation identifier không duy nhất; tên method client có thể bị xung đột |

Ví dụ, hai operation `GET /orders/{id}` và `POST /orders/{id}` không trùng nhau vì HTTP method khác nhau. Nhưng hai operation `GET /orders/{id}` và `GET /orders/{orderId}` có path template tương đương theo OpenAPI; đổi tên biến path không tạo endpoint thứ hai.

`operationId` là định danh logic riêng. Hai operation ở hai path khác nhau vẫn bị lỗi nếu cùng `operationId`, dù Spring MVC đăng ký và xử lý cả hai bình thường.

## 2. Spring MVC xác định handler như thế nào?

Spring MVC dùng `@RequestMapping` và các annotation rút gọn như `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping` để đăng ký handler. Mapping có thể xét nhiều điều kiện:

- URL path hoặc path pattern.
- HTTP method.
- Query parameter qua thuộc tính `params`.
- Request header qua thuộc tính `headers`.
- Media type của request qua `consumes`.
- Media type có thể trả về qua `produces`.
- Custom request condition nếu ứng dụng tự mở rộng.

Mapping ở cấp class thường tạo prefix chung; mapping ở cấp method bổ sung path và điều kiện cụ thể. Ví dụ:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse getById(@PathVariable Long id) {
        return orderService.getById(id);
    }

    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

Hai mapping hoàn chỉnh là `GET /api/orders/{id}` và `POST /api/orders`. Chúng không xung đột vì path hoặc method khác nhau.

Nếu hai handler được đăng ký với cùng mapping conditions, Spring thường từ chối đăng ký mapping thứ hai và báo `Ambiguous mapping`. Nếu các điều kiện khác nhau, Spring có thể giữ cả hai; khi request đến, mapping phù hợp nhất được chọn. Nếu một request khớp nhiều mapping mà không có mapping thắng rõ ràng, Spring có thể báo ambiguous handler ở thời điểm xử lý request.

## 3. Lỗi `Ambiguous mapping` khi ứng dụng khởi động

Một lỗi thường thấy trong log là:

```text
IllegalStateException: Ambiguous mapping. Cannot map ...
There is already ... mapped.
```

Thông báo thường chỉ ra:

- Handler method đang được đăng ký.
- Handler method đã chiếm mapping trước đó.
- Path pattern và HTTP method trùng nhau.

Ví dụ lỗi:

```java
@RestController
@RequestMapping("/api/orders")
class PublicOrderController {

    @GetMapping("/{id}")
    OrderResponse getOrder(@PathVariable Long id) {
        return orderService.getById(id);
    }
}

@RestController
@RequestMapping("/api/orders")
class InternalOrderController {

    @GetMapping("/{orderId}")
    OrderResponse findOrder(@PathVariable Long orderId) {
        return internalOrderService.find(orderId);
    }
}
```

Hai method cùng nhận `GET /api/orders/{...}`. Tên biến `{id}` và `{orderId}` không tạo ra hai tài nguyên khác nhau về mặt URL. Tùy cách Spring phân tích path pattern và điều kiện mapping, chúng có thể bị phát hiện là mapping trùng khi đăng ký hoặc tạo ra request khớp nhiều handler.

### Cách sửa

Nếu hai method thực sự truy cập cùng một tài nguyên, hợp nhất thành một handler và đưa khác biệt vào service hoặc authorization logic:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse getOrder(@PathVariable Long id) {
        return orderService.getById(id);
    }
}
```

Nếu hai hành vi khác nhau về nghiệp vụ, hãy thiết kế path khác nhau, ví dụ `/api/orders/{id}` và `/api/internal/orders/{id}`, rồi mô tả mỗi operation rõ ràng trong OpenAPI.

Không chỉ đổi tên method Java từ `getOrder` thành `findOrder`; tên method không làm thay đổi path, HTTP method hoặc điều kiện mapping.

## 4. Phân biệt mapping trùng hoàn toàn và mapping có điều kiện

Spring MVC cho phép cùng path và HTTP method nếu các điều kiện mapping phân biệt được request.

Ví dụ theo query parameter:

```java
@GetMapping(value = "/search", params = "status")
List<OrderResponse> searchByStatus(@RequestParam String status) {
    return orderService.searchByStatus(status);
}

@GetMapping(value = "/search", params = "owner")
List<OrderResponse> searchByOwner(@RequestParam String owner) {
    return orderService.searchByOwner(owner);
}
```

Hai mapping cùng `GET /search` nhưng điều kiện `params` khác nhau. Spring có thể phân biệt request có `status` và request có `owner`.

Tương tự, mapping có thể được phân biệt bằng `headers`, `consumes` hoặc `produces`. Tuy nhiên, OpenAPI `Paths Object` chỉ có một field cho mỗi path và `Path Item Object` chỉ có một operation cho mỗi HTTP method. Vì thế, hai handler cùng path và method không thể được biểu diễn thành hai operation độc lập chỉ bằng cách dựa vào điều kiện Spring MVC.

Khi hai mapping là hai biến thể của cùng một thao tác, hãy biểu diễn chúng trong một OpenAPI operation:

- Các query/header parameter được khai báo trong `parameters`.
- Nhiều request media type được biểu diễn trong `requestBody.content`.
- Nhiều response media type được biểu diễn trong `responses[*].content`.
- Các cấu trúc payload khác nhau có thể được mô tả bằng `oneOf` hoặc schema phù hợp.

Nếu hai hành vi không thể được giải thích rõ trong một operation, cân nhắc tách thành hai path khác nhau. Không tạo hai operation cùng path/method rồi mong Swagger UI hoặc client generator tự phân biệt bằng điều kiện nội bộ của Spring.

## 5. Nhiều `consumes` hoặc `produces` trên cùng endpoint

Một tình huống đặc biệt là cùng endpoint nhận nhiều loại request body. Spring MVC có thể dùng nhiều handler method cùng path và method, phân biệt bằng `consumes`. Springdoc FAQ mô tả rằng các method overload trong cùng class, cùng HTTP method và path để hỗ trợ nhiều consuming media type có thể tạo thành một OpenAPI operation, thay vì một operation riêng cho từng method.

Với OpenAPI, request body có thể chứa nhiều media type:

```yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
          application/x-www-form-urlencoded:
            schema:
              $ref: '#/components/schemas/CreateOrderForm'
      responses:
        '201':
          description: Đã tạo đơn hàng
```

Nếu hai handler cùng path/method được phân biệt bởi `consumes`, kiểm tra OpenAPI output để bảo đảm tất cả media type cần thiết được mô tả trong cùng operation. Đừng giả định mỗi method Java sẽ luôn trở thành một operation riêng.

Với `produces`, cùng một operation có thể mô tả nhiều response media type trong `content`. Nếu hai handler khác nhau chỉ vì `produces`, hãy xác minh Springdoc đã tổng hợp đúng nội dung và tránh hai định nghĩa operation cho cùng path/method.

## 6. Trùng `operationId` giữa các operation khác path

OpenAPI yêu cầu `operationId` duy nhất trong toàn bộ API document. Công cụ sinh client có thể dùng giá trị này làm tên method, nên giá trị không duy nhất dễ tạo ra method trùng hoặc tên tự động bị thay đổi.

Ví dụ lỗi:

```yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getById
  /api/customers/{id}:
    get:
      operationId: getById
```

Hai path khác nhau nhưng `operationId` trùng. Spring MVC không bị ảnh hưởng vì mapping vẫn khác path; lỗi nằm trong OpenAPI contract.

### Đặt operationId tường minh

Với Springdoc, dùng `@Operation(operationId = "...")`:

```java
@GetMapping("/api/orders/{id}")
@Operation(operationId = "getOrderById", summary = "Lấy đơn hàng theo ID")
OrderResponse getOrder(@PathVariable Long id) {
    return orderService.getById(id);
}

@GetMapping("/api/customers/{id}")
@Operation(operationId = "getCustomerById", summary = "Lấy khách hàng theo ID")
CustomerResponse getCustomer(@PathVariable Long id) {
    return customerService.getById(id);
}
```

Đặt tên theo tài nguyên và hành động, ví dụ `getOrderById`, `searchOrders`, `createOrder`, `cancelOrder`. Tên nên ổn định qua các lần build vì client generator có thể tạo method từ `operationId`.

Không dùng tên quá chung như `getById`, `create`, `update` nếu document có nhiều resource. Cũng không dùng timestamp hoặc số ngẫu nhiên để “làm cho khác nhau”; cách đó khiến tên client thay đổi qua mỗi lần generate.

## 7. Vì sao Springdoc tự sinh operationId có thể gây bất ngờ?

Nếu không đặt `operationId`, Springdoc có thể suy ra từ tên handler method và phải xử lý trường hợp nhiều method có cùng tên. Ví dụ nhiều controller đều có method `getById` có thể dẫn đến các identifier được bổ sung hậu tố để tránh trùng.

Hậu tố tự động có thể phụ thuộc thứ tự phát hiện handler hoặc thay đổi khi thêm operation mới. Client được generate từ các tên này có thể đổi method name dù API path không đổi.

Với API public hoặc SDK được chia sẻ, nên đặt `operationId` tường minh cho operation quan trọng và kiểm tra tính duy nhất sau khi Springdoc sinh document. Đừng dựa vào thuật toán hậu tố tự động như một hợp đồng tên ổn định.

## 8. Trùng path template trong OpenAPI

OpenAPI coi hai path template có cùng cấu trúc là tương đương, dù tên biến khác nhau.

Ví dụ không hợp lệ:

```yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrder
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
```

Hai path đều biểu diễn một segment thay thế sau `/api/orders/`. Đổi `{id}` thành `{orderId}` không tạo endpoint mới. OpenAPI quy định không được có hai templated path cùng hierarchy nhưng khác tên biến.

### Cách sửa

Chọn một path canonical và một tên path parameter:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: integer
            format: int64
```

Nếu cần một hành vi khác, dùng path literal hoặc một cấu trúc URL khác, ví dụ `/api/orders/recent` hoặc `/api/orders/by-reference/{reference}`.

OpenAPI cho phép path cụ thể và path template cùng tồn tại. Ví dụ `/api/orders/recent` được ưu tiên khi khớp URL cụ thể trước `/api/orders/{orderId}`. Nhưng hai template tương đương như `/{id}` và `/{name}` không được khai báo song song.

## 9. Path cụ thể và path template có thể chồng lấn

Ví dụ:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
  /api/orders/recent:
    get:
      operationId: getRecentOrders
```

Đây là hai path hợp lệ. Khi khớp URL, path cụ thể `/api/orders/recent` được ưu tiên trước path template `/api/orders/{orderId}`.

Tuy nhiên, các mẫu phức tạp như:

```text
/{entity}/me
/books/{id}
```

có thể dẫn đến cách resolve không rõ ràng với một số URL. Hãy tránh thiết kế nhiều path template có vùng khớp chồng lấn khó phân biệt. Nếu tooling cảnh báo ambiguous path, cân nhắc thêm prefix cố định như `/api/books/{id}` hoặc `/api/users/me`.

## 10. Trùng path do ghép class-level và method-level mapping

Path cuối cùng không chỉ nằm trong annotation trên method. Spring kết hợp path ở cấp class và method.

Ví dụ:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable Long id) {
        return orderService.getById(id);
    }
}
```

Path hoàn chỉnh là `/api/orders/{id}`. Nếu class khác cũng có `@RequestMapping("/api/orders")` và một method `@GetMapping("/{orderId}")`, hai mapping có thể chồng lấn.

Khi chẩn đoán, luôn ghi lại path đã ghép, không chỉ nhìn path trong annotation method. Kiểm tra cả meta-annotation, interface controller, inherited method và custom composed annotation có mang `@RequestMapping`.

Spring Framework cũng lưu ý không đặt nhiều annotation thuộc họ `@RequestMapping` trên cùng một element rồi kỳ vọng chúng được cộng dồn. Nếu nhiều mapping annotation được phát hiện trên cùng class hoặc method, chỉ mapping đầu tiên được dùng và framework ghi warning. Hãy dùng một mapping annotation rõ ràng trên mỗi element.

## 11. Không dùng `@Hidden` để sửa xung đột handler runtime

`@Hidden` có tác dụng ẩn operation hoặc controller khỏi OpenAPI document. Nó không xóa `RequestMappingInfo`, không thay đổi Spring MVC handler registry và không giải quyết hai handler cùng nhận một request.

Ví dụ:

```java
@Hidden
@RestController
@RequestMapping("/api/internal/orders")
class InternalOrderController {
    // ...
}
```

Điều này chỉ điều khiển tài liệu. Nếu controller vẫn có mapping xung đột với controller khác, ứng dụng vẫn có thể không khởi động hoặc request vẫn ambiguous.

Tương tự, `springdoc.paths-to-match`, `packages-to-scan` hoặc `GroupedOpenApi` lọc phạm vi document; chúng không thay đổi handler mapping của Spring MVC. Chỉ dùng chúng khi mục tiêu là phân chia tài liệu, không dùng như cách chữa lỗi routing.

## 12. Xung đột do `OpenApiCustomizer` hoặc quá trình merge document

Không phải mọi path trùng đều xuất phát từ controller. Một `OpenApiCustomizer`, plugin hoặc script merge nhiều OpenAPI file có thể thêm Path Item đã tồn tại.

Ví dụ logic cần tránh:

```java
// Pseudocode: ghi đè Path Item đã tồn tại mà không kiểm tra
openAPI.getPaths().put("/api/orders/{id}", generatedPathItem);
```

`Map.put` có thể thay thế Path Item trước đó. Kết quả là operation cũ biến mất mà không có lỗi routing ở Spring MVC.

Khi customizer thêm path:

- Kiểm tra path key đã tồn tại chưa.
- Nếu cùng path nhưng method khác, hợp nhất method vào Path Item hiện tại.
- Nếu cùng path và method, quyết định rõ operation nào là nguồn chuẩn; không ghi đè âm thầm.
- Kiểm tra `operationId` sau khi merge.
- Không merge document từ nhiều nguồn chỉ bằng cách chép map `paths` mà không validate.

`OperationCustomizer` chủ yếu tùy biến một operation đã được tạo từ handler. `OpenApiCustomizer` có thể tác động toàn bộ OpenAPI model, bao gồm `paths`; hãy kiểm tra các customizer có cùng thao tác trên path hoặc operation.

## 13. Nhiều `GroupedOpenApi` có nhất thiết là trùng không?

Không. Mỗi group tạo một OpenAPI document riêng, ví dụ:

```text
/v3/api-docs/public
/v3/api-docs/admin
```

Một operation có thể xuất hiện trong cả hai document nếu filter của hai group giao nhau. Điều đó không tự động là lỗi, vì uniqueness của `operationId` được kiểm tra trong phạm vi từng document.

Tuy nhiên, nếu một group chứa hai handler khác nhau cùng path và method hoặc chứa hai operation có cùng `operationId`, document của group đó vẫn có vấn đề. Kiểm tra từng URL group riêng, không chỉ document mặc định.

## 14. Kiểm tra danh sách handler đã đăng ký

Khi ứng dụng khởi động được, có thể dùng Actuator mappings để xem endpoint đã đăng ký:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,mappings
```

Truy cập trong môi trường phát triển:

```bash
curl http://localhost:8080/actuator/mappings
```

Endpoint `mappings` có thể tiết lộ path nội bộ và thông tin handler. Chỉ expose trong môi trường được kiểm soát hoặc bảo vệ bằng Spring Security; không mở công khai trong production chỉ để debug.

Một cách khác là inject `RequestMappingHandlerMapping` trong test và kiểm tra `getHandlerMethods()`:

```java
@SpringBootTest
class HandlerMappingInventoryTest {

    @Autowired
    RequestMappingHandlerMapping handlerMapping;

    @Test
    void printsRegisteredMappings() {
        handlerMapping.getHandlerMethods().forEach((mapping, handler) ->
            System.out.println(mapping + " -> " + handler)
        );
    }
}
```

Test inventory này chỉ chạy được khi ApplicationContext đã khởi động. Nếu lỗi ambiguous mapping làm context không khởi động, lấy hai handler từ exception stack trace hoặc tạm cô lập controller nghi vấn để khởi động context kiểm tra.

## 15. Kiểm tra OpenAPI document bằng `jq`

Sau khi ứng dụng chạy, lưu document:

```bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json
```

Liệt kê các operation cùng path, method và `operationId`:

```bash
jq -r '
  .paths | to_entries[] as $path
  | $path.value | to_entries[]
  | select(.key == "get" or .key == "put" or .key == "post" or .key == "delete" or .key == "options" or .key == "head" or .key == "patch" or .key == "trace")
  | [(.value.operationId // "<missing>"), $path.key, .key]
  | @tsv
' openapi.json
```

Tìm các `operationId` xuất hiện nhiều lần:

```bash
jq -r '
  .paths[] | to_entries[]
  | select(.key == "get" or .key == "put" or .key == "post" or .key == "delete" or .key == "options" or .key == "head" or .key == "patch" or .key == "trace")
  | .value.operationId // empty
' openapi.json | sort | uniq -d
```

Nếu lệnh thứ hai in ra giá trị, document có `operationId` trùng theo nội dung đã parse. Nếu không in gì, điều đó chỉ cho thấy không tìm thấy duplicate operationId trong file JSON đã đọc; nó không chứng minh path template, YAML duplicate key hoặc mọi quy tắc OpenAPI đều hợp lệ.

Kiểm tra một path cụ thể:

```bash
jq '.paths["/api/orders/{id}"]' openapi.json
```

Nếu path/method biến mất, so sánh output với controller và các customizer. Parser JSON thường chỉ giữ một giá trị khi input có duplicate object key, vì vậy kiểm tra raw YAML/JSON bằng linter có hỗ trợ duplicate key khi nghi ngờ document đã bị ghi đè.

## 16. Chạy OpenAPI linter và validator

Có thể dùng Redocly CLI để lint document:

```bash
npx @redocly/cli lint openapi.yaml
```

Linter có thể phát hiện operationId trùng, cấu trúc path, parameter hoặc các vấn đề contract khác tùy ruleset đang dùng. Để CI có kết quả nhất quán, khóa phiên bản CLI và cấu hình ruleset trong repository.

Nếu dùng Swagger Parser hoặc validator khác, bảo đảm parser hỗ trợ đúng phiên bản `openapi` trong document. Một parser cũ có thể báo lỗi hoặc bỏ qua cấu trúc mới; không hạ phiên bản `openapi` chỉ để làm validator im lặng.

Linter không thay thế kiểm tra Spring MVC runtime. Một document hợp lệ vẫn có thể không khớp mapping thực tế; ngược lại, ứng dụng có thể route request được nhưng document vi phạm quy tắc uniqueness.

## 17. Quy trình chẩn đoán theo thứ tự

Thực hiện từng bước để tìm đúng lớp lỗi:

1. **Đọc exception đầu tiên**: xác định lỗi xảy ra trong quá trình tạo ApplicationContext, khi xử lý request hay khi gọi `/v3/api-docs`.
2. **Nếu là startup error**: lấy hai handler method và mapping đầy đủ từ thông báo `Ambiguous mapping`.
3. **Nếu là runtime ambiguity**: ghi lại request cụ thể, bao gồm method, path, query, headers và content type; kiểm tra mapping nào cùng khớp.
4. **Nếu ứng dụng chạy nhưng OpenAPI sai**: tải JSON/YAML raw và kiểm tra `paths`, HTTP method, `operationId` và diagnostics của parser.
5. **Kiểm tra path sau khi ghép**: kết hợp class-level và method-level mapping; chuẩn hóa path template và tên biến.
6. **Kiểm tra điều kiện mapping**: `params`, `headers`, `consumes`, `produces` và custom conditions.
7. **Kiểm tra extension points**: `OperationCustomizer`, `OpenApiCustomizer`, `GroupedOpenApi` và script merge.
8. **Sửa nguồn mapping hoặc metadata**: hợp nhất handler, đổi path, hoặc đặt operationId duy nhất theo đúng nguyên nhân.
9. **Khởi động lại và xác minh runtime**: request đến từng endpoint phải chọn đúng handler.
10. **Tải lại mọi OpenAPI group và chạy lint**: bảo đảm không còn duplicate path/operationId trong từng document.

## 18. Bảng triệu chứng và cách sửa nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| App dừng khi khởi động với `Ambiguous mapping` | Hai handler có mapping conditions giống nhau | Hợp nhất handler hoặc đổi path/HTTP method/điều kiện có ý nghĩa |
| App chạy nhưng một request báo ambiguous handler | Một request khớp nhiều mapping có điều kiện khác nhau | Kiểm tra query/header/content type; làm điều kiện phân biệt rõ hoặc hợp nhất handler |
| `/v3/api-docs` có hai path template khác tên biến | `/resource/{id}` và `/resource/{name}` | Chọn một path canonical |
| Linter báo `operationId` duplicate | Nhiều operation dùng cùng identifier | Đặt `@Operation(operationId=...)` duy nhất |
| Client generator tạo tên method có hậu tố bất ngờ | Springdoc phải phân biệt operationId tự sinh | Đặt operationId tường minh và ổn định |
| Hai method cùng path/method khác `consumes` chỉ sinh một operation | Springdoc tổng hợp biến thể media type vào một operation | Kiểm tra `requestBody.content` có đủ media type |
| Operation biến mất sau customizer | `OpenApiCustomizer` ghi đè Path Item trong map | Hợp nhất có kiểm tra, tránh `put` ghi đè mù |
| `@Hidden` không giải quyết startup error | Annotation chỉ ẩn khỏi document | Sửa Spring MVC mapping thực tế |
| Chỉ một group bị duplicate | Filter của group đưa nhiều handler vào cùng document | Kiểm tra group filters và từng group output |
| JSON parser không báo duplicate key nhưng file nguồn có lặp | Parser đã giữ một key và bỏ giá trị còn lại | Dùng YAML/JSON linter có duplicate-key detection và xem raw source |

## 19. Ví dụ thiết kế lại API khi có hai hành vi khác nhau

Giả sử hai chức năng ban đầu cùng dùng `GET /api/orders/{id}`: một chức năng lấy đơn hàng theo ID, chức năng còn lại tìm đơn hàng theo mã tham chiếu. Nếu cả hai có semantics khác nhau, không nên để hai handler cùng path rồi hy vọng tên biến phân biệt.

Thiết kế rõ ràng hơn:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    @Operation(operationId = "getOrderById")
    OrderResponse getById(@PathVariable Long id) {
        return orderService.getById(id);
    }

    @GetMapping("/by-reference/{reference}")
    @Operation(operationId = "getOrderByReference")
    OrderResponse getByReference(@PathVariable String reference) {
        return orderService.getByReference(reference);
    }
}
```

Giờ đây path và operationId đều khác nhau. API consumer có thể hiểu chính xác cách tìm tài nguyên; Spring MVC không cần đoán handler dựa trên hai template tương đương.

## 20. Phòng ngừa tái diễn trong CI

Để lỗi uniqueness được phát hiện trước khi deploy:

- Sinh OpenAPI document từ đúng profile build.
- Parse document bằng parser tương thích phiên bản.
- Lint `operationId`, path template, parameter và response.
- So sánh document mới với baseline để phát hiện breaking change.
- Kiểm tra tất cả `GroupedOpenApi` được phát hành.
- Có integration test xác nhận endpoint quan trọng được ánh xạ đến đúng handler.
- Không merge OpenAPI file từ nhiều module nếu chưa kiểm tra duplicate path/method/operationId.
- Đặt `operationId` tường minh cho API public hoặc API dùng để sinh SDK.

Ví dụ một job CI tối giản:

```bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output target/openapi.json

npx @redocly/cli lint target/openapi.json
```

Trong CI thực tế, khóa Redocly CLI và parser version; lưu artifact OpenAPI sau khi lint đạt. Nếu service có nhiều group, tải và lint từng URL group thay vì chỉ lint document mặc định.

## 21. Checklist xử lý duplicate mapping và operation

- [ ] Đã xác định lỗi xảy ra ở Spring startup, request routing hay OpenAPI generation.
- [ ] Đã ghi lại path hoàn chỉnh sau khi ghép class-level và method-level mapping.
- [ ] Đã kiểm tra HTTP method và các điều kiện `params`, `headers`, `consumes`, `produces`.
- [ ] Không có hai handler cùng mapping conditions nếu chúng không thể được phân biệt.
- [ ] Không có hai OpenAPI path template cùng hierarchy chỉ khác tên biến.
- [ ] Mỗi path/method được biểu diễn bằng một OpenAPI operation.
- [ ] Các biến thể media type được mô tả trong `requestBody.content` hoặc response `content`.
- [ ] `operationId` duy nhất trong từng OpenAPI document.
- [ ] `operationId` public được đặt tường minh và ổn định.
- [ ] `@Hidden` hoặc path filter không bị dùng nhầm để chữa lỗi routing.
- [ ] `OpenApiCustomizer` không ghi đè Path Item hoặc operation ngoài ý muốn.
- [ ] Đã kiểm tra từng document group sau khi generate.
- [ ] Đã chạy parser/linter và kiểm tra raw JSON/YAML.
- [ ] Đã chạy request integration test để xác nhận handler thực tế.

Trùng handler, trùng path và trùng `operationId` là ba lỗi khác nhau. Spring MVC cần mapping đủ rõ để chọn một handler cho mỗi request; OpenAPI chỉ có một operation cho mỗi path và HTTP method; `operationId` phải duy nhất trong toàn bộ document. Hãy bắt đầu từ exception hoặc OpenAPI output để xác định lớp lỗi, sau đó hợp nhất handler hoặc thiết kế path phù hợp, đặt operationId tường minh và chạy lại runtime test cùng OpenAPI linter. `@Hidden` chỉ thay đổi tài liệu, không sửa mapping thực tế.

## Tài liệu tham khảo

- [Spring Framework – Mapping Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [OpenAPI Specification 3.0 – Paths Object and Path Templating](https://spec.openapis.org/oas/v3.0.3.html#paths-object)
- [OpenAPI Specification 3.1 – Paths Object and Path Templating](https://spec.openapis.org/oas/v3.1.1.html#paths-object)
- [OpenAPI Specification 3.2 – Paths Object](https://spec.openapis.org/oas/v3.2.0.html#paths-object)
- [Springdoc OpenAPI v2 – FAQ: Multiple consuming media types](https://springdoc.org/v2/#how-are-endpoints-with-multiple-consuming-media-types-supported)
- [Springdoc OpenAPI – Customization](https://springdoc.org/#how-can-i-customise-the-openapi-description)
- [Redocly CLI – Lint an API description](https://redocly.com/docs/cli/commands/lint)
