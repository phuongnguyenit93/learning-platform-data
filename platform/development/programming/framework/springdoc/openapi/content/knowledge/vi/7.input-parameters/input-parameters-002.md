# Mô tả `@PathVariable` và yêu cầu bắt buộc của path parameter

Trong API REST, path parameter là giá trị nằm ngay trong đường dẫn, thường dùng để xác định tài nguyên cụ thể. Ví dụ `/api/orders/8f...` có thể biểu diễn một đơn hàng có mã định danh tương ứng. Trong Spring MVC, annotation `@PathVariable` liên kết phần biến trong URL với tham số của phương thức controller. Springdoc-openapi đọc mapping và chữ ký phương thức để mô tả biến đó thành path parameter trong hợp đồng OpenAPI.

Điểm quan trọng là path parameter luôn bắt buộc trong OpenAPI. Nếu URL có dạng `/orders/{orderId}`, client phải cung cấp giá trị cho `orderId` để khớp đường dẫn. Đây là yêu cầu của cấu trúc path và chuẩn OpenAPI, đồng thời phù hợp với mặc định `required = true` của `@PathVariable` trong Spring.

## 1. Path parameter là gì?

Path parameter là một phần biến trong path template. Biến được đặt trong cặp dấu ngoặc nhọn `{}` và thay bằng giá trị thực khi client gửi request.

Ví dụ:

```text
GET /api/orders/{orderId}
GET /api/customers/{customerId}/orders/{orderId}
GET /api/products/{productId}/reviews/{reviewId}
```

Khi gọi API, client thay biến bằng giá trị cụ thể:

```text
GET /api/orders/125
GET /api/customers/cus-42/orders/125
GET /api/products/sku-900/reviews/rv-17
```

Path parameter thường dùng để xác định một tài nguyên hoặc một tài nguyên con trong quan hệ phân cấp. Ví dụ:

- `/orders/{orderId}` xác định một đơn hàng.
- `/customers/{customerId}/orders` xác định danh sách đơn hàng của một khách hàng.
- `/customers/{customerId}/orders/{orderId}` xác định một đơn hàng thuộc khách hàng đó.

Path parameter khác query parameter. `/orders/125` dùng path parameter để chỉ đơn hàng 125; `/orders?status=PAID` dùng query parameter `status` để lọc danh sách đơn hàng. Hai loại có vị trí, ý nghĩa và cách khai báo khác nhau trong OpenAPI.

## 2. Khai báo path variable trong Spring MVC

Spring MVC sử dụng các annotation mapping để khai báo path template. `@PathVariable` lấy giá trị của biến trong path và gán vào tham số phương thức controller.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getById(
            @PathVariable("orderId") Long id) {
        return orderService.findById(id);
    }
}
```

Trong ví dụ:

1. `@RequestMapping("/api/orders")` khai báo prefix chung của controller.
2. `@GetMapping("/{orderId}")` khai báo path có biến `orderId` và HTTP method `GET`.
3. `@PathVariable("orderId")` yêu cầu Spring lấy giá trị từ đúng biến `orderId` trong URL.
4. Spring chuyển giá trị chuỗi trong URL sang kiểu `Long` trước khi gọi phương thức controller.

Khi client gọi `GET /api/orders/125`, tham số `id` trong phương thức nhận giá trị số `125`. Tên biến Java `id` có thể khác tên biến trên URL vì tên được liên kết tường minh bằng `@PathVariable("orderId")`.

### Tên của path variable

`@PathVariable` có thuộc tính `value` và `name` là các alias của nhau. Có thể viết:

```java
@PathVariable("orderId") Long id
```

hoặc:

```java
@PathVariable(name = "orderId") Long id
```

Nếu bỏ tên trong annotation, Spring cần xác định tên tham số từ metadata của mã biên dịch. Cách suy luận này phụ thuộc cấu hình biên dịch, chẳng hạn tùy chọn giữ tên tham số `-parameters`. Để tránh lỗi khi thay đổi build hoặc tên biến Java, nên chỉ định rõ tên path variable trong annotation.

```java
@GetMapping("/{orderId}")
OrderResponse getById(@PathVariable("orderId") UUID id) {
    return orderService.findById(id);
}
```

Tên `orderId` phải khớp với placeholder trong mapping. Nếu URL khai báo `{orderId}` nhưng annotation chỉ đến `id` mà không có placeholder tương ứng, Spring không thể liên kết đúng biến và request có thể thất bại khi xử lý.

## 3. Nhiều path variable trong một endpoint

Một endpoint có thể chứa nhiều biến đường dẫn. Mỗi biến cần một tham số `@PathVariable` tương ứng.

```java
@GetMapping("/customers/{customerId}/orders/{orderId}")
OrderResponse getCustomerOrder(
        @PathVariable("customerId") UUID customerId,
        @PathVariable("orderId") UUID orderId) {
    return orderService.findCustomerOrder(customerId, orderId);
}
```

Mapping này có hai placeholder: `customerId` và `orderId`. Spring liên kết từng giá trị vào đúng tham số dựa trên tên được khai báo. Hợp đồng OpenAPI cũng phải mô tả cả hai path parameter.

```yaml
paths:
  /customers/{customerId}/orders/{orderId}:
    get:
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
      responses:
        '200':
          description: Tìm thấy đơn hàng
```

Không nên gộp hai biến thành một tham số nếu ứng dụng cần xử lý chúng riêng biệt. Việc khai báo rõ ràng giúp Spring binding chính xác và giúp client generator tạo chữ ký phương thức phù hợp.

## 4. Kiểu dữ liệu và chuyển đổi giá trị

Giá trị trên URL được truyền qua HTTP dưới dạng văn bản. Spring MVC sử dụng cơ chế conversion để chuyển giá trị đó sang kiểu tham số mà controller khai báo.

| Kiểu tham số Java | Ví dụ path segment | Kiểu schema OpenAPI thường gặp |
|---|---|---|
| `String` | `ORD-001` | `type: string` |
| `Long` hoặc `Integer` | `125` | `type: integer`, định dạng phù hợp như `int64` hoặc `int32` |
| `UUID` | `550e8400-e29b-41d4-a716-446655440000` | `type: string`, `format: uuid` |
| `BigDecimal` | `1250.50` | `type: number` |
| `Boolean` | `true` hoặc `false` | `type: boolean` |
| `Enum` | `PENDING` | `type: string` cùng tập `enum` nếu được nhận diện |

Ví dụ dùng UUID:

```java
@GetMapping("/{orderId}")
OrderResponse getById(@PathVariable("orderId") UUID orderId) {
    return orderService.findById(orderId);
}
```

Spring chuyển chuỗi UUID trong path thành đối tượng `UUID`. Springdoc có thể suy ra schema dạng chuỗi với `format: uuid` từ kiểu tham số.

Nếu client gửi giá trị không thể chuyển đổi, chẳng hạn `/api/orders/abc` trong khi tham số là `Long`, Spring thường trả lỗi binding/conversion trước khi gọi phương thức controller. Status code và nội dung lỗi cụ thể phụ thuộc exception handler và cấu hình xử lý lỗi của ứng dụng. Hãy mô tả response lỗi tương ứng nếu API công khai cam kết hành vi đó.

Với kiểu tùy chỉnh, enum hoặc converter riêng, cần kiểm tra YAML được sinh có phản ánh đúng định dạng URL mà API chấp nhận. Có thể bổ sung metadata OpenAPI khi kiểu Java không đủ diễn đạt quy tắc công khai.

## 5. Vì sao path parameter luôn bắt buộc?

Trong OpenAPI, một parameter có `in: path` bắt buộc phải có `required: true`. Path template xác định cấu trúc URL; nếu placeholder `{orderId}` xuất hiện, client phải cung cấp giá trị thay thế để tạo thành URL hợp lệ.

Ví dụ:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Tìm thấy đơn hàng
```

`required: true` không phải một tùy chọn trang trí. Đây là yêu cầu của OpenAPI đối với path parameter. Một tài liệu đặt `required: false` cho parameter có `in: path` là không hợp lệ theo đặc tả.

Trong Spring, `@PathVariable` có thuộc tính `required` với giá trị mặc định là `true`:

```java
@GetMapping("/{orderId}")
OrderResponse getById(
        @PathVariable(value = "orderId", required = true) Long id) {
    return orderService.findById(id);
}
```

Thông thường không cần ghi `required = true`, vì đó đã là mặc định:

```java
@PathVariable("orderId") Long id
```

Springdoc hiểu path variable từ mapping và `@PathVariable`, sau đó mô tả nó thành path parameter bắt buộc trong OpenAPI. Kể cả khi một cấu hình hoặc metadata bổ sung cố gắng đánh dấu path parameter là không bắt buộc, yêu cầu của OpenAPI vẫn là `required: true`.

## 6. `required = false` không làm placeholder biến mất khỏi URL

Không nên dùng `@PathVariable(required = false)` với kỳ vọng endpoint `/orders/{orderId}` tự động chấp nhận cả `/orders` và `/orders/125`. Việc route có khớp hay không do path mapping quyết định. Khi placeholder không có trong URL, mapping `/orders/{orderId}` thông thường không khớp request `/orders`.

Nếu API cần hỗ trợ cả hai dạng URL, hãy khai báo hai mapping hoặc thiết kế endpoint sao cho giá trị thực sự tùy chọn được truyền bằng query parameter.

Ví dụ khai báo hai mapping riêng bằng hai phương thức controller:

```java
@GetMapping
List<OrderResponse> findAll() {
    return orderService.findAll();
}

@GetMapping("/{orderId}")
OrderResponse findById(@PathVariable("orderId") Long orderId) {
    return orderService.findById(orderId);
}
```

Trong tài liệu OpenAPI, hai phương thức này trở thành hai path riêng: `/api/orders` không có path parameter và `/api/orders/{orderId}` có path parameter `orderId` bắt buộc. Cách khai báo này làm rõ hai hành vi mà không tạo một path parameter tùy chọn.

Nếu mục tiêu là lọc danh sách theo một giá trị có thể bỏ qua, query parameter thường phù hợp hơn:

```java
@GetMapping
List<OrderResponse> findOrders(
        @RequestParam(name = "customerId", required = false) UUID customerId) {
    return orderService.findByCustomer(customerId);
}
```

Hợp đồng khi đó mô tả `customerId` là query parameter có thể không gửi:

```yaml
parameters:
  - name: customerId
    in: query
    required: false
    schema:
      type: string
      format: uuid
```

Quy tắc lựa chọn:

- Dùng path parameter khi giá trị là một phần cấu trúc để định danh tài nguyên hoặc tài nguyên con.
- Dùng query parameter khi giá trị là bộ lọc hoặc tùy chọn có thể được bỏ qua.
- Nếu có hai cấu trúc URL riêng biệt, mô tả chúng bằng các path/operation phù hợp thay vì biến path parameter thành tùy chọn trong OpenAPI.

## 7. Mô tả path parameter bằng springdoc-openapi

Springdoc thường suy ra tên, vị trí và kiểu dữ liệu từ `@PathVariable` cùng path mapping. Để hợp đồng hữu ích hơn với client, có thể bổ sung mô tả, ví dụ và metadata bằng annotation `@Parameter` của Swagger/OpenAPI.

```java
@Operation(summary = "Lấy thông tin đơn hàng")
@GetMapping("/{orderId}")
OrderResponse getById(
        @PathVariable("orderId")
        @Parameter(
            description = "Mã UUID của đơn hàng",
            example = "550e8400-e29b-41d4-a716-446655440000"
        )
        UUID orderId) {
    return orderService.findById(orderId);
}
```

Spring annotation điều khiển việc binding request; `@Parameter` bổ sung thông tin cho hợp đồng. Không nhầm `@Parameter` với `@PathVariable`: annotation OpenAPI không tạo route và không thay thế cơ chế nhận giá trị của Spring.

Vì path parameter bắt buộc theo OpenAPI, không cần khai báo `required = false` trong `@Parameter`. Nếu có đặt thuộc tính `required`, giá trị phải phù hợp với quy tắc bắt buộc của path parameter.

Một phần YAML được sinh có thể có dạng:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      summary: Lấy thông tin đơn hàng
      parameters:
        - name: orderId
          in: path
          description: Mã UUID của đơn hàng
          required: true
          example: 550e8400-e29b-41d4-a716-446655440000
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy đơn hàng
```

Tên trường và vị trí `example` trong output có thể khác tùy phiên bản thư viện hoặc cách cấu hình schema, nhưng `name`, `in: path` và `required: true` là các thuộc tính quan trọng cần kiểm tra.

## 8. Validation trên path variable

Path parameter không chỉ cần đúng kiểu mà đôi khi còn có miền giá trị cụ thể. Ví dụ, mã số đơn hàng phải dương hoặc một chuỗi phải có độ dài giới hạn. Có thể dùng Bean Validation để kiểm tra giá trị sau khi Spring chuyển đổi.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getById(
            @PathVariable("orderId") @Positive Long orderId) {
        return orderService.findById(orderId);
    }
}
```

Việc thực thi method validation phụ thuộc phiên bản Spring, cách cấu hình validation và các annotation áp dụng. Cần kiểm tra runtime để xác nhận ràng buộc thực sự được kích hoạt. Springdoc có thể phản ánh một số constraint được hỗ trợ thành giới hạn schema, nhưng không phải mọi quy tắc nghiệp vụ hoặc validator tùy chỉnh đều chuyển đổi đầy đủ thành OpenAPI.

Nếu `orderId` phải lớn hơn 0, hợp đồng có thể mô tả giới hạn tương ứng:

```yaml
parameters:
  - name: orderId
    in: path
    required: true
    schema:
      type: integer
      format: int64
      minimum: 1
```

Response khi giá trị sai định dạng hoặc vi phạm validation cần khớp với cách ứng dụng xử lý lỗi. Ví dụ, chuỗi không chuyển được sang `Long` có thể phát sinh lỗi binding; số âm có thể bị validation từ chối. Hai trường hợp này có thể có status code hoặc error body khác nhau.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không lấy được giá trị path variable | Tên trong `@PathVariable` không khớp placeholder | Dùng cùng tên hoặc khai báo tên tường minh |
| Lỗi không xác định được tên tham số | Dựa vào tên tham số nhưng build không giữ metadata tên | Khai báo `@PathVariable("orderId")` |
| Request `/orders` không khớp `/orders/{orderId}` | Placeholder là một phần bắt buộc của route | Khai báo route riêng hoặc dùng query parameter |
| Giá trị UUID/Long không hợp lệ | Chuỗi URL không chuyển đổi được sang kiểu Java | Kiểm tra định dạng đầu vào và mô tả response lỗi |
| Tài liệu đánh dấu path parameter là optional | Metadata OpenAPI bị tùy biến sai hoặc tài liệu bị chỉnh sửa thủ công | Đảm bảo `required: true` |
| Swagger UI hiển thị sai tên parameter | Tên path placeholder và metadata parameter không đồng bộ | Kiểm tra mapping, annotation và YAML được sinh |
| Parameter thiếu format hoặc giới hạn | Kiểu tùy chỉnh hoặc constraint không được suy ra đầy đủ | Bổ sung `@Parameter`/`@Schema` hoặc customizer |

## 10. Checklist khi review path parameter

- [ ] Mỗi placeholder trong path template có một parameter cùng tên.
- [ ] Parameter được mô tả với `in: path`.
- [ ] `required` luôn là `true`.
- [ ] `@PathVariable` tham chiếu đúng tên placeholder.
- [ ] Tên được khai báo tường minh khi không muốn phụ thuộc metadata tên tham số lúc biên dịch.
- [ ] Kiểu Java tương thích với định dạng giá trị client gửi trong URL.
- [ ] Schema OpenAPI có `type`, `format`, giới hạn và ví dụ phù hợp khi cần.
- [ ] Validation runtime và response lỗi được kiểm tra thực tế.
- [ ] Nếu giá trị có thể bỏ qua, cân nhắc query parameter hoặc path riêng thay vì path parameter tùy chọn.
- [ ] Tài liệu OpenAPI được sinh lại và kiểm tra sau khi thay đổi controller.

## Kết luận

`@PathVariable` liên kết placeholder trong Spring path mapping với tham số phương thức controller. Spring chuyển giá trị URL sang kiểu Java tương ứng, còn springdoc-openapi mô tả biến đó thành path parameter trong hợp đồng. Theo OpenAPI, path parameter luôn bắt buộc vì nó là thành phần của cấu trúc URL. Hãy đặt tên placeholder và annotation nhất quán, kiểm tra chuyển đổi kiểu cùng validation, và dùng query parameter hoặc route riêng khi giá trị thực sự có thể bỏ qua.
