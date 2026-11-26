# URI trong hypermedia

Trong một API hypermedia, URI là địa chỉ định danh tài nguyên mà client có thể điều hướng tới thông qua các liên kết do server công bố. Client thường chỉ cần biết điểm vào ban đầu, sau đó đọc `href` từ những relation như `self`, `orders`, `next` hoặc `customer` để khám phá bước tiếp theo. Cách thiết kế này giảm sự phụ thuộc của client vào cấu trúc đường dẫn nội bộ của server.

Spring HATEOAS hỗ trợ tạo URI từ mapping của Spring MVC, biểu diễn liên kết bằng `Link` và công bố URI template khi client cần cung cấp tham số. Để sử dụng đúng, cần hiểu cấu trúc URI, sự khác nhau giữa URI cụ thể và URI template, cách mã hóa tham số và cách giữ liên kết ổn định khi API thay đổi.

## 1. URI có vai trò gì trong hypermedia?

URI (Uniform Resource Identifier) là chuỗi định danh một tài nguyên. Trong hypermedia, URI thường được đặt trong thuộc tính `href` của một liên kết. Client đọc relation để hiểu ý nghĩa liên kết, rồi dùng URI đích để truy cập tài nguyên hoặc thực hiện bước tiếp theo theo hợp đồng API.

Ví dụ một representation đơn hàng:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/customers/7"
    },
    "cancel": {
      "href": "https://api.example.com/orders/42/cancel"
    }
  }
}
```

Trong ví dụ này:

- `href` trong relation `self` định danh URI của chính đơn hàng.
- `customer` dẫn tới tài nguyên khách hàng liên quan.
- `cancel` chỉ ra một đường dẫn gắn với khả năng hủy đơn.
- Relation cho client biết ý nghĩa của link; URI cho biết đích mà client có thể truy cập.

URI không tự mô tả toàn bộ cách gọi endpoint. Client vẫn cần hợp đồng về HTTP method, request body, media type, quyền truy cập và lỗi có thể xảy ra. Một liên kết `cancel` trong HAL cơ bản chẳng hạn không tự nói rằng client phải gửi `POST` với body nào.

## 2. Cấu trúc của một URI

Một URI tuyệt đối có thể gồm scheme, authority, path, query và fragment:

```text
https://api.example.com:8443/orders/42?expand=items#details
\___/   \_________________/ \________/ \___________/ \______/
scheme       authority          path       query       fragment
```

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Scheme | Cách xác định cơ chế truy cập. | `https` |
| Authority | Host và có thể có port hoặc thông tin authority khác. | `api.example.com:8443` |
| Path | Đường dẫn tới tài nguyên. | `/orders/42` |
| Query | Tham số bổ sung cho truy vấn hoặc biểu diễn. | `?status=PENDING&page=0` |
| Fragment | Phần định vị trong biểu diễn hoặc tài liệu. | `#details` |

Trong HTTP API, server nhận scheme, authority, path và query theo request target hoặc thông tin request tương ứng. Fragment thường được xử lý ở phía client và không được gửi trong HTTP request tới server. Vì vậy, không nên dùng fragment làm tham số mà server cần đọc để xử lý request.

## 3. Phân biệt URI và URL

URL (Uniform Resource Locator) là một dạng URI có thông tin định vị tài nguyên. Trong trao đổi REST API, mọi URL đều là URI, nhưng không phải mọi URI đều là URL theo nghĩa hẹp. Trong giao tiếp hằng ngày, hai thuật ngữ đôi khi được dùng thay thế nhau; khi thiết kế API, có thể dùng từ URI để nói về định danh được đặt trong `href`.

Ví dụ:

- `https://api.example.com/orders/42` là URI tuyệt đối và cũng là URL.
- `/orders/42` là URI reference dạng đường dẫn tuyệt đối, chưa chứa scheme và authority.
- `urn:isbn:9780132350884` là URI dạng URN, dùng để định danh theo namespace chứ không chỉ vị trí HTTP.

Với Spring HATEOAS, điều quan trọng là URI hoặc URI reference trong `Link` phải có ý nghĩa rõ ràng và có thể được client giải quyết trong ngữ cảnh API. Không cần buộc mọi link phải chứa host nếu hợp đồng cho phép dùng URI tương đối.

## 4. URI tuyệt đối và URI tương đối

URI tuyệt đối chứa scheme và authority, ví dụ:

```text
https://api.example.com/orders/42
```

URI reference tương đối có thể là:

```text
/orders/42
orders/42
../customers/7
```

Client giải quyết URI reference tương đối dựa trên URI cơ sở của tài liệu chứa liên kết theo quy tắc phân giải URI. Ví dụ `/orders/42` là đường dẫn bắt đầu từ root của authority hiện tại; `orders/42` được giải quyết tương đối theo path hiện tại và có thể cho kết quả khác.

URI tuyệt đối hữu ích khi cần công bố đích rõ ràng giữa nhiều host hoặc dịch vụ. URI tương đối có thể giúp representation dùng được ở nhiều host, môi trường hoặc context path. Tuy nhiên, client và server cần thống nhất cách giải quyết URI reference.

Khi tạo link trong Spring MVC, `WebMvcLinkBuilder` thường sử dụng thông tin mapping và request hiện tại để dựng URI. Nếu ứng dụng chạy sau reverse proxy, ingress hoặc load balancer, hãy kiểm tra cấu hình forwarded headers để link được tạo ra phản ánh địa chỉ công khai mà client truy cập. Tránh công bố hostname nội bộ hoặc port chỉ tồn tại trong mạng triển khai.

## 5. Tạo URI từ mapping controller bằng Spring HATEOAS

Trong Spring MVC, cách phổ biến để tạo URI là dùng `WebMvcLinkBuilder` cùng `linkTo(...)` và `methodOn(...)`. Cách này gắn liên kết với mapping của controller, giúp giảm lỗi khi đường dẫn thay đổi.

Ví dụ controller:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        // Tải đơn hàng và tạo representation.
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(@PathVariable UUID id) {
        // Thực hiện quy tắc hủy đơn.
    }
}
```

Tạo link `self` tới method đọc đơn hàng:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();
```

Tạo link cho thao tác hủy:

```java
Link cancel = linkTo(methodOn(OrderController.class).cancel(orderId))
        .withRel("cancel");
```

`methodOn` tạo tham chiếu để Spring HATEOAS phân tích mapping và tham số. Nó không gọi method controller để thực thi nghiệp vụ. Khi `@RequestMapping` hoặc `@PathVariable` thay đổi, link được dựng dựa trên mapping mới.

Các ví dụ giả định `orderId` đã có và controller được cấu hình trong Spring MVC. Nếu ứng dụng dùng WebFlux, hãy dùng cơ chế link builder phù hợp với stack WebFlux thay vì `WebMvcLinkBuilder`.

## 6. Tạo URI có query parameter

Query parameter thường dùng cho tìm kiếm, lọc, sắp xếp và phân trang. Khi biết giá trị cụ thể ở server, có thể truyền tham số qua mapping controller hoặc dùng `UriComponentsBuilder` để tạo URI có mã hóa phù hợp.

Ví dụ tạo URI tìm kiếm đơn hàng:

```java
URI searchUri = UriComponentsBuilder.fromPath("/orders")
        .queryParam("status", "PENDING")
        .queryParam("page", 0)
        .queryParam("size", 20)
        .build()
        .encode()
        .toUri();
```

Kết quả tương đương một URI có path `/orders` và query gồm `status`, `page`, `size`. Có thể gắn URI này vào link:

```java
Link search = Link.of(searchUri.toString(), "search");
```

Khi có thể, nên tạo link dựa trên mapping controller để tránh lặp lại tên path hoặc query parameter trong nhiều nơi. `UriComponentsBuilder` hữu ích khi cần xây dựng URI động từ dữ liệu hoặc tham số mà mapping không biểu diễn thuận tiện.

Không nên nối chuỗi trực tiếp để tạo query string, ví dụ `"/orders?status=" + status`, vì giá trị có ký tự đặc biệt có thể làm URI sai hoặc thay đổi ý nghĩa. Hãy dùng API dựng URI và mã hóa tham số. Đồng thời, không đưa mật khẩu, token bí mật hoặc dữ liệu nhạy cảm vào query string vì URI thường được ghi trong log, lịch sử trình duyệt và hệ thống trung gian.

## 7. URI template là gì?

URI cụ thể chỉ tới một đích đã xác định, còn URI template mô tả một mẫu URI có biến mà client có thể điền khi cần. URI template hữu ích khi server muốn công bố một điểm tìm kiếm hoặc một tài nguyên có tham số do client lựa chọn.

Ví dụ:

```text
/orders/42
/orders/{id}
/orders{?status,page,size}
```

- `/orders/42` là URI cụ thể.
- `/orders/{id}` là template có biến path `id`.
- `/orders{?status,page,size}` là template có nhóm query parameter tùy chọn.

URI template theo RFC 6570 định nghĩa cú pháp mở rộng biến. Một số biểu thức thường gặp:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `{id}` | Mở rộng biến vào vị trí path hoặc thành phần template tương ứng. |
| `{/id}` | Thêm biến dưới dạng path segment. |
| `{?page,size}` | Thêm query string với các biến `page` và `size`. |
| `{&sort}` | Bổ sung query parameter vào query string đã có. |

Client cần mở rộng template bằng giá trị biến trước khi gửi request. Template chưa mở rộng không phải URI đích hoàn chỉnh để gọi trực tiếp.

## 8. Công bố URI template bằng Link

Spring HATEOAS hỗ trợ URI template trong `Link`. Ví dụ, API có thể công bố một link tìm kiếm với các tham số do client chọn:

```java
Link search = Link.of("/orders{?status,page,size}", "search");
```

Khi tuần tự hóa theo HAL, một link template được đánh dấu bằng thuộc tính `templated`:

```json
{
  "_links": {
    "search": {
      "href": "/orders{?status,page,size}",
      "templated": true
    }
  }
}
```

Client đọc `templated: true` để biết `href` là mẫu cần mở rộng. Client có thể điền `status=PENDING`, `page=0` và `size=20`, sau đó gọi URI cụ thể tương ứng.

URI template nên công bố đúng những biến mà endpoint hỗ trợ. Nếu API yêu cầu `status` nhưng template không mô tả biến đó, client có thể không biết cách tạo request hợp lệ. Ngược lại, không nên công bố các biến mà server không nhận hoặc không sử dụng.

## 9. Khi nào dùng URI cụ thể, khi nào dùng URI template?

| Tình huống | Cách phù hợp | Ví dụ |
| --- | --- | --- |
| Server đã biết mã tài nguyên cần trỏ tới | URI cụ thể | `/orders/42` |
| Server công bố liên kết tới tài nguyên hiện tại | URI cụ thể qua `self` | `linkTo(methodOn(...))` |
| Client tự chọn điều kiện lọc | URI template | `/orders{?status}` |
| Client tự chọn trang và kích thước trang | URI template hoặc link phân trang cụ thể | `/orders{?page,size}` hoặc `/orders?page=1&size=20` |
| Server đã xác định trang tiếp theo | URI cụ thể | `/orders?page=2&size=20` |
| Client cần cung cấp mã định danh để truy vấn | URI template | `/customers/{id}` |

Không cần dùng URI template cho mọi link. Khi server đã biết tài nguyên hoặc trang kế tiếp, một URI cụ thể thường đơn giản hơn. Template phù hợp khi client cần điền biến mà server muốn công bố rõ.

## 10. Mã hóa URI và xử lý ký tự đặc biệt

URI có quy tắc ký tự hợp lệ và mã hóa phần trăm (percent-encoding). Những giá trị chứa dấu cách, dấu tiếng Việt, dấu `&`, `?`, `#` hoặc ký tự dành riêng cần được xử lý đúng theo thành phần URI mà chúng thuộc về.

Ví dụ, nếu giá trị tìm kiếm là `cà phê & trà`, không nên nối trực tiếp vào URI. Hãy đưa giá trị vào query parameter qua builder:

```java
URI uri = UriComponentsBuilder.fromPath("/products")
        .queryParam("q", "cà phê & trà")
        .build()
        .encode()
        .toUri();
```

Khi xây path, phân biệt một path segment với toàn bộ path. Nếu mã tài nguyên là một giá trị do người dùng cung cấp, hãy dùng cơ chế thêm segment hoặc biến path có mã hóa, không để dấu `/` trong giá trị vô tình tạo thêm cấp đường dẫn.

Không mã hóa toàn bộ URI như một chuỗi đơn. Scheme, authority, path, query và fragment có quy tắc riêng. Dùng `URI`, `UriComponentsBuilder` hoặc API URI template để xử lý đúng thành phần cần mã hóa.

## 11. Ổn định URI và khả năng tiến hóa API

HATEOAS giúp client giảm phụ thuộc vào URI cụ thể nếu client thực sự đi theo các link được server công bố. Server có thể đổi mapping từ `/orders/{id}` sang một cấu trúc khác mà client vẫn hoạt động nếu relation và các quy tắc representation được giữ ổn định.

Để đạt điều đó:

- Dùng relation có ý nghĩa ổn định, ví dụ `self`, `next`, `customer` hoặc relation nghiệp vụ được định nghĩa rõ.
- Tạo link từ mapping controller hoặc một thành phần link builder dùng chung.
- Không yêu cầu client tự ghép URI từ ID và tên endpoint.
- Giữ URI template đồng bộ với tham số mà endpoint thực sự nhận.
- Kiểm thử client traversal sau khi thay đổi mapping.
- Xem thay đổi relation, media type và ngữ nghĩa dữ liệu là thay đổi hợp đồng cần quản lý.

HATEOAS không làm mọi thay đổi tự động tương thích ngược. Nếu client bỏ qua link và lưu cứng URI, client vẫn bị ảnh hưởng khi mapping đổi. Nếu server đổi relation mà client đang tìm, khả năng khám phá cũng bị phá vỡ.

## 12. Bảo mật và độ tin cậy của URI

URI được công bố trong representation là dữ liệu mà client có thể nhìn thấy. Không đưa thông tin bí mật vào URI hoặc query string. Không giả định việc ẩn một link sẽ bảo vệ endpoint; server vẫn phải xác thực, phân quyền và kiểm tra trạng thái ở mỗi request.

Với URI tuyệt đối, cần tránh công bố hostname hoặc port nội bộ. Trong môi trường proxy, cấu hình forwarded headers và trusted proxy phù hợp để Spring tạo link theo địa chỉ công khai. Không tin các header forwarded từ nguồn không đáng tin cậy vì chúng có thể làm ứng dụng sinh URI giả mạo.

Nếu một link dẫn tới tài nguyên cần quyền truy cập, việc có thể nhìn thấy URI không đồng nghĩa người dùng được phép truy cập. Endpoint đích vẫn phải áp dụng chính sách bảo mật độc lập với cách client khám phá link.

## 13. Kiểm thử URI và URI template

Kiểm thử link cần xác nhận cả relation và đích. Với model trong bộ nhớ:

```java
Link self = model.getRequiredLink("self");

assertThat(self.getRel().value()).isEqualTo("self");
assertThat(self.getHref()).endsWith("/orders/42");
assertThat(self.isTemplated()).isFalse();
```

Với link template:

```java
Link search = Link.of("/orders{?status,page,size}", "search");

assertThat(search.isTemplated()).isTrue();
assertThat(search.getHref()).contains("{?status,page,size}");
```

Với Spring MVC, MockMvc có thể xác nhận URI cuối cùng được tạo từ mapping:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").value(
            endsWith("/orders/" + orderId)));
```

Với URI template trong HAL, kiểm tra `templated: true` và các biến được công bố đúng. Nên có thêm một test client mở rộng template với giá trị thực rồi gọi URI nhận được. Khi test URI có query parameter, phân tích URI và kiểm tra từng tham số thay vì phụ thuộc thứ tự query string.

Các trường hợp nên kiểm tra gồm:

- Path variable chứa ký tự cần mã hóa.
- Query parameter có dấu cách hoặc ký tự dành riêng.
- URI tương đối được giải quyết đúng theo URI cơ sở.
- URI tuyệt đối dùng host công khai trong môi trường proxy.
- Mapping controller thay đổi nhưng relation vẫn ổn định.
- Template chỉ chứa các biến endpoint thực sự hỗ trợ.

## 14. Bài tập thực hành và tiêu chí hoàn thành

Hãy mở rộng API quản lý đơn hàng với các yêu cầu:

1. Tạo link `self` từ mapping controller cho một đơn hàng.
2. Tạo link `customer` tới tài nguyên khách hàng liên quan.
3. Tạo link `search` bằng URI template `/orders{?status,page,size}`.
4. Gửi request tìm kiếm với `status`, `page` và `size`; kiểm tra các tham số được mã hóa đúng.
5. So sánh URI tuyệt đối và URI tương đối trong response HAL, rồi xác định chính sách mà API sử dụng.
6. Thử thay đổi mapping controller và xác nhận link được tạo theo mapping mới.
7. Viết kiểm thử để client đọc relation và đi theo `href` thay vì tự ghép đường dẫn.
8. Kiểm tra không có thông tin bí mật trong URI và endpoint đích vẫn kiểm tra quyền.

Bạn đã nắm được URI trong hypermedia khi có thể phân biệt URI cụ thể với URI template, hiểu vai trò của `href` và relation, tạo URI từ mapping Spring MVC, công bố template cho tham số client cần cung cấp, mã hóa query/path đúng cách và kiểm thử khả năng client điều hướng khi cấu trúc URI thay đổi. Đây là nền tảng để xây dựng API Spring HATEOAS dễ khám phá và có thể tiến hóa theo hợp đồng hypermedia.
