# HTTP method, URI template và path variable

## 1. MockMvc gửi một HTTP request như thế nào?

Trong Spring MVC, một endpoint thường được xác định bởi nhiều yếu tố: HTTP method, đường dẫn URI, các điều kiện bổ sung như `Content-Type` hoặc `Accept`, và dữ liệu request. Khi kiểm thử controller bằng MockMvc, ta cần dựng request có đúng những yếu tố đó để Spring chọn đúng handler method và bind dữ liệu vào tham số Java.

`MockMvcRequestBuilders` cung cấp các hàm dựng request tương ứng với HTTP method:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

mockMvc.perform(get("/api/orders"));
mockMvc.perform(post("/api/orders"));
mockMvc.perform(put("/api/orders/{id}", 42));
mockMvc.perform(patch("/api/orders/{id}", 42));
mockMvc.perform(delete("/api/orders/{id}", 42));
```

Mỗi builder tạo một request giả lập để MockMvc đưa qua chuỗi xử lý Spring MVC. Request không cần được gửi qua mạng đến một cổng HTTP thật. Tuy vậy, phần xử lý mapping, argument resolver, data binding, validation, controller advice và message converter vẫn có thể được kiểm tra trong cấu hình MockMvc đang sử dụng.

Một request cơ bản có thể được đọc theo cấu trúc:

```text
HTTP method + URI + headers + parameters + body
```

Ví dụ:

```text
GET /api/orders/42
Accept: application/json
```

Ở đây `GET` là HTTP method, `/api/orders/42` là URI cụ thể, còn `42` là một đoạn của path có thể được bind vào `@PathVariable`.

## 2. HTTP method và mapping của controller

Spring MVC dùng annotation mapping để kết nối request với một phương thức Java. HTTP method là một phần của điều kiện mapping.

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping
    public List<OrderResponse> findAll() {
        // ...
    }

    @GetMapping("/{orderId}")
    public OrderResponse findById(@PathVariable("orderId") UUID orderId) {
        // ...
    }

    @PostMapping
    public OrderResponse create(@RequestBody CreateOrderRequest request) {
        // ...
    }

    @PutMapping("/{orderId}")
    public OrderResponse replace(
            @PathVariable("orderId") UUID orderId,
            @RequestBody ReplaceOrderRequest request) {
        // ...
    }

    @PatchMapping("/{orderId}")
    public OrderResponse updatePartially(
            @PathVariable("orderId") UUID orderId,
            @RequestBody UpdateOrderRequest request) {
        // ...
    }

    @DeleteMapping("/{orderId}")
    public void delete(@PathVariable("orderId") UUID orderId) {
        // ...
    }
}
```

Các method thường dùng trong kiểm thử:

| HTTP method | Ý nghĩa thường gặp | MockMvc builder |
|---|---|---|
| `GET` | Đọc tài nguyên hoặc dữ liệu | `get(uriTemplate, uriVariables...)` |
| `POST` | Tạo tài nguyên hoặc thực hiện một thao tác | `post(uriTemplate, uriVariables...)` |
| `PUT` | Thay thế hoặc cập nhật tài nguyên theo hợp đồng API | `put(uriTemplate, uriVariables...)` |
| `PATCH` | Cập nhật một phần tài nguyên | `patch(uriTemplate, uriVariables...)` |
| `DELETE` | Xóa tài nguyên | `delete(uriTemplate, uriVariables...)` |
| `HEAD` | Yêu cầu headers tương tự `GET`, không lấy response body | `head(uriTemplate, uriVariables...)` |
| `OPTIONS` | Hỏi các method hoặc tùy chọn được hỗ trợ | `options(uriTemplate, uriVariables...)` |

Các builder `get`, `post`, `put`, `patch`, `delete`, `head` và `options` giúp test thể hiện rõ method đang kiểm tra. Khi cần chọn method động, có thể dùng builder tổng quát:

```java
import org.springframework.http.HttpMethod;

mockMvc.perform(request(HttpMethod.GET, "/api/orders/{orderId}", orderId));
```

`request(HttpMethod, ...)` hữu ích khi method được lấy từ dữ liệu test hoặc khi viết một helper dùng chung. Với test thông thường, builder chuyên biệt thường dễ đọc hơn.

### 2.1. Kiểm thử đúng method

Giả sử controller có `@GetMapping("/{orderId}")`. Test nên gửi `GET` đến URI tương ứng:

```java
mockMvc.perform(get("/api/orders/{orderId}", orderId))
        .andExpect(status().isOk());
```

Nếu gửi `POST` đến cùng đường dẫn trong khi chỉ có mapping `GET`, Spring MVC thường trả về `405 Method Not Allowed` khi path khớp nhưng HTTP method không được hỗ trợ:

```java
mockMvc.perform(post("/api/orders/{orderId}", orderId))
        .andExpect(status().isMethodNotAllowed());
```

Nếu không có mapping nào khớp URI, kết quả thường là `404 Not Found`. Vì vậy, khi test lỗi, hãy phân biệt trường hợp sai method với trường hợp sai path. Bộ lọc bảo mật cũng có thể từ chối request trước khi request đến handler mapping; khi đó response có thể là `401` hoặc `403` tùy cấu hình.

## 3. URI template là gì?

URI template là một URI có placeholder biểu diễn phần giá trị sẽ được thay thế khi dựng request. Placeholder thường được viết trong dấu ngoặc nhọn `{}`:

```text
/api/orders/{orderId}
/api/customers/{customerId}/orders/{orderId}
/api/products/{category}/{productCode}
```

Trong controller, các placeholder tương ứng với biến đường dẫn:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse find(@PathVariable("orderId") UUID orderId) {
    // ...
}
```

Trong MockMvc, truyền giá trị URI variable ngay sau chuỗi template:

```java
UUID orderId = UUID.fromString("8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122");

mockMvc.perform(get("/api/orders/{orderId}", orderId));
```

MockMvc mở rộng template và tạo URI cụ thể tương ứng. Request được gửi đến Spring MVC với path đã có giá trị thay cho placeholder:

```text
Template: /api/orders/{orderId}
Value:    8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122
Request:  /api/orders/8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122
```

Việc dùng template giúp test nêu rõ đâu là phần cố định của route và đâu là dữ liệu đầu vào. Nó cũng tránh phải nối chuỗi thủ công để tạo path.

### 3.1. Template có nhiều path variable

Giả sử endpoint có hai biến:

```java
@GetMapping("/api/customers/{customerId}/orders/{orderId}")
public OrderResponse findCustomerOrder(
        @PathVariable("customerId") UUID customerId,
        @PathVariable("orderId") UUID orderId) {
    // ...
}
```

Test truyền các giá trị theo thứ tự placeholder xuất hiện trong URI template:

```java
mockMvc.perform(get(
        "/api/customers/{customerId}/orders/{orderId}",
        customerId,
        orderId));
```

Giá trị đầu tiên được gắn vào `{customerId}`, giá trị thứ hai được gắn vào `{orderId}`. Nếu truyền ngược thứ tự, request vẫn có thể được tạo nhưng mỗi giá trị sẽ nằm ở vị trí không mong muốn; Spring sau đó bind theo tên placeholder trong mapping. Hãy giữ thứ tự đối số trùng với thứ tự biến trong template.

Với template dài, nên xuống dòng và đặt tên biến rõ ràng để người đọc có thể đối chiếu:

```java
mockMvc.perform(get(
        "/api/warehouses/{warehouseId}/bins/{binId}/items/{itemId}",
        warehouseId,
        binId,
        itemId));
```

### 3.2. Truyền giá trị có kiểu dữ liệu khác nhau

URI cuối cùng là chuỗi, nhưng đối số URI variable có thể là kiểu Java như `UUID`, `Long`, `Integer` hoặc `String`:

```java
mockMvc.perform(get("/api/orders/{orderId}", 42L));
mockMvc.perform(get("/api/orders/{orderId}", orderId));
mockMvc.perform(get("/api/products/{code}", "BK-2026-01"));
```

Giá trị được biểu diễn thành dữ liệu URI. Khi request đến controller, Spring MVC chuyển đổi chuỗi path variable sang kiểu tham số Java dựa trên conversion service và các converter đang cấu hình.

Ví dụ, route `/api/orders/42` có thể bind vào tham số `Long`, còn một UUID hợp lệ có thể bind vào `UUID`. Nếu chuỗi trong path không chuyển đổi được sang kiểu đích, Spring MVC thường trả về `400 Bad Request` do lỗi chuyển đổi argument.

## 4. `@PathVariable` nhận dữ liệu từ đâu?

`@PathVariable` lấy dữ liệu từ một biến được khai báo trong path pattern của mapping. Tên biến trong annotation phải khớp với placeholder của route, trừ khi tên được suy ra theo quy tắc tham số Java của ứng dụng.

Khai báo tường minh thường dễ đọc và ít phụ thuộc cấu hình biên dịch:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse find(@PathVariable("orderId") UUID orderId) {
    // ...
}
```

Cũng có thể viết:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse find(@PathVariable UUID orderId) {
    // ...
}
```

Ở dạng thứ hai, Spring cần xác định tên tham số là `orderId`. Khai báo tên trong annotation làm mối liên hệ giữa route và tham số rõ ràng hơn, đặc biệt khi đổi tên biến Java hoặc khi cấu hình biên dịch không giữ metadata tên tham số.

Với nhiều path variable:

```java
@GetMapping("/api/customers/{customerId}/orders/{orderId}")
public OrderResponse find(
        @PathVariable("customerId") UUID customerId,
        @PathVariable("orderId") UUID orderId) {
    // ...
}
```

Spring tìm từng giá trị trong URI đã match, sau đó chuyển đổi sang kiểu khai báo của tham số. Controller nhận giá trị đã bind, không cần tự cắt chuỗi URI.

### 4.1. Path variable bắt buộc và route không khớp

Path variable là một phần của cấu trúc path. Nếu mapping yêu cầu `/api/orders/{orderId}`, request `/api/orders` không có segment `orderId` nên không khớp mapping đó. Đây thường là tình huống `404`, không phải một request có path variable rỗng.

Nếu route khớp nhưng giá trị không hợp lệ với kiểu Java, ví dụ `orderId` khai báo là `UUID` nhưng request chứa `not-a-uuid`, Spring không thể chuyển đổi giá trị và thường trả về `400`.

Hai trường hợp cần được kiểm thử riêng:

```java
// Thiếu segment của path: không khớp /{orderId}.
mockMvc.perform(get("/api/orders"))
        .andExpect(status().isNotFound());

// Có segment nhưng không chuyển đổi được sang UUID.
mockMvc.perform(get("/api/orders/{orderId}", "not-a-uuid"))
        .andExpect(status().isBadRequest());
```

Kết quả cụ thể vẫn chịu ảnh hưởng của các mapping khác và exception handler của ứng dụng. Ví dụ `/api/orders` có thể là một route `GET` hợp lệ riêng, hoặc `@ControllerAdvice` có thể tùy biến response lỗi.

## 5. Path variable khác query parameter như thế nào?

Path variable và query parameter đều truyền dữ liệu từ client vào controller, nhưng chúng thuộc hai phần khác nhau của URI và có annotation tương ứng khác nhau.

| Loại dữ liệu | Ví dụ URI | Annotation phía controller | Cách dựng trong MockMvc |
|---|---|---|---|
| Path variable | `/api/orders/42` | `@PathVariable` | `get("/api/orders/{id}", 42)` |
| Query parameter | `/api/orders?page=2` | `@RequestParam` | `get("/api/orders").queryParam("page", "2")` |
| Form/request parameter | Dữ liệu form của request | `@RequestParam` | `.param("name", "value")` |
| Request body | JSON trong body | `@RequestBody` | `.contentType(...).content(...)` |

Ví dụ controller nhận cả path variable và query parameter:

```java
@GetMapping("/api/customers/{customerId}/orders")
public List<OrderResponse> findCustomerOrders(
        @PathVariable("customerId") UUID customerId,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    // ...
}
```

Test có thể dựng URI path bằng template và query string bằng `queryParam`:

```java
mockMvc.perform(get("/api/customers/{customerId}/orders", customerId)
                .queryParam("page", "2")
                .queryParam("size", "10"))
        .andExpect(status().isOk());
```

`queryParam(...)` thể hiện rõ dữ liệu được thêm vào query string. `.param(...)` đặt request parameter trực tiếp trong request giả lập và thường được dùng khi kiểm tra request parameter nói chung hoặc dữ liệu form:

```java
mockMvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("page", "0"))
        .andExpect(status().isOk());
```

Không dùng `.param("orderId", "42")` để thay thế cho path variable của route `/api/orders/{orderId}`. Request parameter tên `orderId` không tự tạo segment còn thiếu trong path. Nếu controller khai báo `@PathVariable`, hãy truyền giá trị qua URI template.

## 6. Dùng URI template với các HTTP method khác nhau

URI variable không chỉ dùng với `GET`. Các builder có thể nhận URI template và danh sách giá trị tương tự nhau.

### 6.1. GET một tài nguyên

Controller:

```java
@GetMapping("/api/orders/{orderId}")
public OrderResponse findById(@PathVariable("orderId") UUID orderId) {
    return orderService.findById(orderId);
}
```

Test:

```java
mockMvc.perform(get("/api/orders/{orderId}", orderId)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(orderId.toString()));
```

`accept(...)` đặt header `Accept` để mô tả kiểu response mà client mong muốn. Nó không thay thế HTTP method hoặc URI variable.

### 6.2. POST tạo tài nguyên

POST thường gửi dữ liệu mới trong request body. URI template vẫn có thể chứa path variable nếu API thiết kế endpoint tạo tài nguyên dưới một tài nguyên cha:

```java
@PostMapping("/api/customers/{customerId}/orders")
public OrderResponse create(
        @PathVariable("customerId") UUID customerId,
        @RequestBody CreateOrderRequest request) {
    // ...
}
```

Test:

```java
String body = """
        {
          "productCode": "BK-2026-01",
          "quantity": 2
        }
        """;

mockMvc.perform(post("/api/customers/{customerId}/orders", customerId)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isCreated());
```

Ở đây `customerId` thuộc path, còn `productCode` và `quantity` thuộc JSON body. Không nên đặt toàn bộ dữ liệu request vào URI nếu hợp đồng API xác định chúng là body.

### 6.3. PUT và PATCH cập nhật tài nguyên

PUT và PATCH thường xác định tài nguyên đích bằng path variable:

```java
mockMvc.perform(put("/api/orders/{orderId}", orderId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(replacementJson))
        .andExpect(status().isOk());

mockMvc.perform(patch("/api/orders/{orderId}", orderId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(patchJson))
        .andExpect(status().isOk());
```

Test cần dùng đúng method mà controller khai báo. Nếu endpoint là `@PatchMapping`, gửi `PUT` đến cùng path không phải là cách thay thế tương đương.

### 6.4. DELETE xóa tài nguyên

```java
mockMvc.perform(delete("/api/orders/{orderId}", orderId))
        .andExpect(status().isNoContent());
```

DELETE thường không cần request body khi định danh tài nguyên đã nằm trong path. Tuy nhiên, hãy tuân theo hợp đồng API thực tế; nếu endpoint có body hoặc query parameter bổ sung, test phải dựng đúng dữ liệu đó.

## 7. URI variable và encoding

Khi dựng URI từ template, truyền giá trị bằng đối số URI variable giúp Spring Test xử lý việc mở rộng template và encoding dữ liệu URI. Cách này rõ ràng hơn nối chuỗi:

```java
// Nên dùng URI template.
mockMvc.perform(get("/api/products/{productCode}", productCode));

// Không nên tự nối chuỗi để tạo path.
mockMvc.perform(get("/api/products/" + productCode));
```

Encoding đặc biệt quan trọng khi giá trị có khoảng trắng hoặc ký tự dành riêng của URI. Không nên giả định mọi ký tự trong một giá trị đều có thể xuất hiện nguyên trạng trong path. Hãy dùng URI variable, sau đó kiểm tra request với các giá trị biên phù hợp hợp đồng API.

Một số lưu ý:

- Path variable biểu diễn một segment hoặc một phần của path theo mapping; nó không phải cách truyền tùy ý một URL hoàn chỉnh.
- Dấu `/` có ý nghĩa phân tách segment. Nếu dữ liệu có dấu `/`, hãy xác định rõ API có cho phép dữ liệu đó trong một path variable hay nên dùng query parameter hoặc request body.
- Không tự encode giá trị rồi lại truyền qua template nếu điều đó khiến dữ liệu bị encode hai lần.
- Nếu cần kiểm tra ký tự Unicode, khoảng trắng hoặc ký tự dành riêng, hãy viết test thể hiện URI đầu vào và giá trị controller nhận được.

Ví dụ một test có thể kiểm tra mã sản phẩm có dấu gạch ngang:

```java
mockMvc.perform(get("/api/products/{productCode}", "BK-2026-01"))
        .andExpect(status().isOk());
```

Với dữ liệu phức tạp hơn, hãy xác định encoding mong muốn từ hợp đồng API và cách servlet container xử lý path. Không nên dựa vào việc nối chuỗi thủ công để suy ra hành vi encoding.

## 8. Ràng buộc path pattern và nhiều mapping gần nhau

Spring MVC có thể khai báo route với nhiều biến hoặc điều kiện pattern. Ví dụ:

```java
@GetMapping("/api/products/{category}/{productCode}")
public ProductResponse find(
        @PathVariable("category") String category,
        @PathVariable("productCode") String productCode) {
    // ...
}
```

Test phải cung cấp đủ segment:

```java
mockMvc.perform(get(
        "/api/products/{category}/{productCode}",
        "books",
        "BK-2026-01"))
        .andExpect(status().isOk());
```

Nếu mapping sử dụng pattern có biểu thức chính quy:

```java
@GetMapping("/api/orders/{orderId:[0-9]+}")
public OrderResponse find(@PathVariable("orderId") long orderId) {
    // ...
}
```

thì chỉ các path segment phù hợp biểu thức mới match route. Có thể kiểm tra một giá trị hợp lệ và một giá trị không hợp lệ:

```java
mockMvc.perform(get("/api/orders/{orderId}", 42))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/{orderId}", "ABC"))
        .andExpect(status().isNotFound());
```

Trong ví dụ thứ hai, `ABC` không khớp path pattern nên handler đó không được chọn. Điều này khác với route không có regex nhưng tham số Java không chuyển đổi được: trường hợp đó thường đi đến bước binding rồi trả về `400`.

Khi có nhiều mapping gần nhau, hãy kiểm tra cả path lẫn method. Ví dụ `GET /api/orders/{id}` và `DELETE /api/orders/{id}` cùng dùng path pattern nhưng khác HTTP method; `GET` và `DELETE` là hai request khác nhau trong quá trình chọn handler.

## 9. Kiểm tra handler được chọn

Status code cho biết kết quả HTTP, nhưng đôi khi test cần xác nhận Spring đã chọn đúng controller method. Có thể dùng các result matcher thuộc `MockMvcResultMatchers`:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

mockMvc.perform(get("/api/orders/{orderId}", orderId))
        .andExpect(status().isOk())
        .andExpect(handler().handlerType(OrderController.class))
        .andExpect(handler().methodName("findById"));
```

Các assertion này hữu ích khi nhiều mapping có path tương tự hoặc khi test muốn xác nhận một HTTP method đã dẫn đến đúng handler. Chúng cũng giúp phân biệt lỗi mapping với lỗi xảy ra bên trong logic controller.

Có thể kiểm tra method của request trong kết quả nếu cần:

```java
mockMvc.perform(delete("/api/orders/{orderId}", orderId))
        .andExpect(request().method("DELETE"));
```

Thông thường, việc dùng đúng builder như `get(...)` hoặc `delete(...)` đã thể hiện method khá rõ. Assertion bổ sung chỉ cần thiết khi nó làm rõ một yêu cầu kiểm thử cụ thể.

## 10. Một bài test controller hoàn chỉnh

Ví dụ sau kết hợp `@WebMvcTest`, MockMvc, URI template, path variable và kiểm tra JSON response. Giả sử controller nhận một UUID và gọi service để tìm đơn hàng.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void findsOrderById() throws Exception {
        UUID orderId = UUID.fromString(
                "8a2d1a4e-7a5d-4c0f-9c1a-8e0a0f7c1122");
        OrderResponse response = new OrderResponse(orderId, "CREATED");

        given(orderService.findById(orderId)).willReturn(response);

        mockMvc.perform(get("/api/orders/{orderId}", orderId)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(orderId.toString()))
                .andExpect(jsonPath("$.status").value("CREATED"));

        then(orderService).should().findById(orderId);
    }
}
```

Các import static thường dùng trong test này:

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Với Spring Boot 3.3, `@MockBean` là cách phổ biến để thay service bằng mock trong test slice. Các phiên bản Spring Boot mới hơn có thể cung cấp annotation thay thế; hãy dùng annotation phù hợp với phiên bản của dự án.

Điều quan trọng trong test là giá trị truyền vào service phải đúng UUID được mở rộng từ URI template. Nếu path variable bind sai hoặc conversion thất bại, lời gọi service có thể không xảy ra; assertion trên mock giúp phát hiện điều đó.

## 11. Những lỗi thường gặp khi dựng request

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Controller trả về `404` | URI thiếu segment, sai prefix hoặc sai path pattern | Đối chiếu URI template với `@RequestMapping` ở class và method |
| Controller trả về `405` | Path khớp nhưng HTTP method không được mapping hỗ trợ | Dùng đúng builder `get`, `post`, `put`, `patch` hoặc `delete` |
| `@PathVariable` không nhận được giá trị mong muốn | Truyền sai thứ tự URI variables hoặc tên placeholder không khớp annotation | Đối chiếu từng placeholder với đối số và `@PathVariable("...")` |
| Test có `.param(...)` nhưng path variable vẫn thiếu | Request parameter không tạo path segment | Dùng URI template và truyền URI variable |
| Request trả về `400` | Path variable không chuyển đổi được sang kiểu Java hoặc validation/binding thất bại | Kiểm tra kiểu tham số, giá trị path và exception response |
| Endpoint nhận query parameter mặc định dù test không truyền | Controller có `defaultValue` hoặc tham số là optional | Xác định rõ test đang kiểm tra mặc định hay giá trị được truyền |
| Request bị `401` hoặc `403` trước khi vào controller | Security filter từ chối request | Thiết lập authentication/authorization phù hợp cho test; với request thay đổi dữ liệu, kiểm tra cả CSRF nếu cấu hình yêu cầu |
| Giá trị path có ký tự đặc biệt không như mong đợi | Tự nối chuỗi hoặc encode dữ liệu không đúng | Dùng URI template và kiểm tra encoding theo hợp đồng API |

Khi chẩn đoán, hãy kiểm tra theo thứ tự: method, path sau khi mở rộng template, mapping ở controller, tên và kiểu của path variable, rồi mới đến service được gọi. Trình tự này giúp xác định request bị từ chối ở bước chọn handler, bước bind dữ liệu hay trong logic nghiệp vụ.

## 12. Checklist khi viết MockMvc request

- Chọn builder đúng HTTP method mà endpoint khai báo.
- Dùng URI template cho các segment động của path.
- Truyền URI variable theo đúng thứ tự placeholder xuất hiện.
- Đảm bảo tên trong `@PathVariable` khớp tên biến của mapping.
- Dùng kiểu Java phù hợp và cung cấp giá trị có thể chuyển đổi.
- Dùng `queryParam(...)` hoặc `param(...)` cho request parameter, không dùng chúng để thay thế path variable.
- Dùng `contentType(...)` và `content(...)` khi endpoint nhận request body.
- Dùng `accept(...)` khi muốn kiểm tra content negotiation.
- Phân biệt `404` do path không khớp với `405` do method không được hỗ trợ và `400` do binding/conversion.
- Khi cần xác nhận routing, kiểm tra handler type hoặc handler method.

Trong MockMvc, HTTP method quyết định loại request, URI template xác định cấu trúc đường dẫn và `@PathVariable` nhận giá trị từ các placeholder của path. Khi ba phần này được khai báo nhất quán, test có thể mô phỏng chính xác cách client gọi endpoint và phát hiện sớm lỗi route, method hoặc binding trước khi triển khai ứng dụng.
