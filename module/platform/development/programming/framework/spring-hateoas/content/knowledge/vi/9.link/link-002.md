# href của link

## Mục tiêu

Sau bài này, bạn có thể giải thích ý nghĩa của thuộc tính `href` trong một link hypermedia, phân biệt URI tuyệt đối và URI tương đối, đọc URI template có biến truy vấn, tạo link theo mapping của Spring MVC bằng Spring HATEOAS và kiểm thử đích liên kết trong response.

## 1. href cho client biết điều gì?

Một link hypermedia thường có hai thành phần quan trọng:

- **Relation** cho biết liên kết có ý nghĩa gì trong ngữ cảnh, ví dụ `self`, `orders`, `next` hoặc `cancel`.
- **href** cho biết URI reference mà client có thể dùng để truy cập đích liên kết.

Ví dụ HAL:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    }
  }
}
```

Ở đây, `self` và `orders` là relation; các chuỗi trong `href` là đích liên kết. Client không nên suy ra URL từ tên relation. Nó đọc chính `href` do server cung cấp rồi gửi request đến đích đó.

`href` là một URI reference. Nó có thể là URI tuyệt đối như `https://api.example.com/orders/42`, hoặc URI tương đối như `/orders/42`. Điều quan trọng là client có thể phân giải URI reference theo ngữ cảnh của response để xác định đích.

## 2. URI tuyệt đối và URI tương đối

**URI tuyệt đối** chứa scheme và authority, ví dụ:

```text
https://api.example.com/orders/42
```

Nó xác định rõ giao thức và host. Dạng này hữu ích khi API cần công bố địa chỉ đầy đủ hoặc liên kết đến một dịch vụ khác.

**URI tương đối** dựa vào URI cơ sở của tài liệu hoặc ngữ cảnh đã biết:

```text
/orders/42
../orders/42
orders/42
```

Các dạng tương đối có thể giúp API hoạt động trong nhiều môi trường hoặc dưới các base path khác nhau. Client phải phân giải chúng theo quy tắc URI trước khi gửi request.

Trong response HAL, hai dạng có thể xuất hiện:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "documentation": {
      "href": "https://docs.example.com/orders"
    }
  }
}
```

Link `self` dùng đường dẫn tương đối theo host hiện tại; link `documentation` trỏ đến một host khác. Ứng dụng nên chọn cách biểu diễn nhất quán với môi trường triển khai và khả năng của client.

## 3. Tạo href từ mapping của controller

Không nên ghép chuỗi URL bằng tay khi đích liên kết đã được ánh xạ bởi Spring MVC. Spring HATEOAS có `WebMvcLinkBuilder` với `linkTo(...)` và `methodOn(...)` để tạo link dựa trên mapping controller.

Ví dụ controller:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<Order> getOrder(@PathVariable UUID id) {
        Order order = orderService.getRequired(id);

        Link self = linkTo(methodOn(OrderController.class)
                .getOrder(id))
                .withSelfRel();

        return EntityModel.of(order, self);
    }
}
```

Các import liên quan:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

`methodOn(OrderController.class).getOrder(id)` tham chiếu phương thức controller để Spring HATEOAS đọc mapping và giá trị tham số. `linkTo(...)` tạo link builder từ thông tin đó; `withSelfRel()` gắn relation `self`.

Kết quả link sẽ bám theo mapping của controller. Nếu đường dẫn thay đổi từ `/orders/{id}` sang đường dẫn khác, việc tham chiếu phương thức giúp link builder sử dụng mapping mới khi ứng dụng được cập nhật.

## 4. Tạo href tường minh khi cần

Đôi khi đích liên kết không tương ứng với một phương thức controller trong ứng dụng hiện tại, chẳng hạn tài liệu bên ngoài hoặc một URI đã được cấu hình. Khi đó có thể tạo `Link` trực tiếp:

```java
Link documentation = Link.of(
        "https://docs.example.com/orders"
).withRel("documentation");

Link self = Link.of("/orders/42")
        .withRel(IanaLinkRelations.SELF);
```

Các import:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
```

Dùng link trực tiếp khi URI thực sự là một phần cấu hình hoặc hợp đồng có chủ đích. Với endpoint nội bộ được quản lý bởi controller, link builder thường an toàn hơn vì nó theo mapping thực tế và ngữ cảnh request.

Không nên đặt URL môi trường cụ thể như `http://localhost:8080` vào assembler dùng chung. URL này có thể sai khi chạy trên staging, production, HTTPS hoặc sau reverse proxy. Nếu cần liên kết ngoài, hãy lấy base URI từ cấu hình môi trường phù hợp.

## 5. href có path variable và query parameter

Một URI có thể chứa biến đường dẫn và tham số truy vấn. Ví dụ:

```text
/orders/42
/orders?status=PENDING
/orders?page=1&size=20
/orders/42/items?sort=price,desc
```

Khi controller đã khai báo mapping, link builder có thể tạo href từ phương thức và tham số:

```java
@GetMapping("/{id}/items")
public CollectionModel<EntityModel<OrderItem>> getItems(
        @PathVariable UUID id,
        @RequestParam(required = false) String sort) {
    // Trả về danh sách item.
}
```

Một tham chiếu đến phương thức có thể cung cấp giá trị path variable và query parameter cho link builder:

```java
Link items = linkTo(methodOn(OrderController.class)
        .getItems(orderId, "price,desc"))
        .withRel("items");
```

Nếu muốn công bố một link tìm kiếm có biến mà client tự điền, có thể dùng URI template:

```java
Link search = Link.of("/orders{?status,page,size}")
        .withRel("search");
```

URI template `/orders{?status,page,size}` mô tả các biến truy vấn có thể được thay thế, ví dụ `status`, `page` và `size`. Trong HAL, một link template có thể được đánh dấu bằng thuộc tính `templated`:

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

Client hiểu cú pháp template có thể cung cấp giá trị cho các biến rồi mở rộng thành URI cụ thể, chẳng hạn `/orders?status=PENDING&page=0&size=20`. Template mô tả cách tạo URI; nó không tự gửi request và cũng không thay thế kiểm tra dữ liệu đầu vào ở server.

## 6. Mã hóa URI và tránh ghép chuỗi

Giá trị path hoặc query có thể chứa dấu cách, dấu tiếng Việt, dấu `&`, `?`, `#` hoặc các ký tự có ý nghĩa đặc biệt trong URI. Ghép chuỗi trực tiếp có thể tạo href sai hoặc làm thay đổi ý nghĩa của URI.

Ví dụ, giá trị tìm kiếm `cà phê & trà` không nên được nối thẳng vào query string:

```java
// Tránh ghép chuỗi URI bằng dữ liệu đầu vào.
String href = "/products?keyword=" + keyword;
```

Hãy dùng API xây dựng URI hoặc link builder để xử lý cấu trúc và encoding. Khi tạo link từ mapping controller bằng `methodOn`, Spring HATEOAS có thông tin về vị trí của path variable và query parameter. Khi tạo URI thủ công, dùng `UriComponentsBuilder` để thêm path segment và query parameter theo từng thành phần:

```java
URI uri = UriComponentsBuilder
        .fromPath("/products")
        .queryParam("keyword", "{keyword}")
        .encode()
        .buildAndExpand(keyword)
        .toUri();
```

Các import:

```java
import java.net.URI;

import org.springframework.web.util.UriComponentsBuilder;
```

Việc encoding cần được thực hiện đúng một lần theo vị trí của dữ liệu. Tránh tự thay dấu cách thành `%20` hoặc tự mã hóa toàn bộ URL trước khi đưa vào builder; làm vậy có thể gây double encoding hoặc mã hóa cả dấu phân cách cấu trúc.

Cũng cần phân biệt path segment và query parameter. Dấu `/` trong path phân tách các segment; dấu `&` trong query phân tách các tham số. Giá trị dữ liệu chứa những ký tự này cần được encoding để không bị hiểu nhầm là thành phần cấu trúc.

## 7. href khi ứng dụng chạy sau reverse proxy

Trong môi trường production, ứng dụng Spring có thể chạy sau load balancer hoặc reverse proxy. Client truy cập bằng host công khai và HTTPS, trong khi kết nối từ proxy đến ứng dụng có thể dùng host nội bộ hoặc HTTP.

Nếu ứng dụng tạo absolute href dựa trên request mà không xử lý thông tin proxy, link có thể chứa host hoặc scheme nội bộ. Ví dụ client truy cập `https://api.example.com` nhưng response lại tạo link `http://service-internal:8080/orders/42`.

Cần cấu hình ứng dụng và proxy để xử lý forwarded headers phù hợp với nền tảng triển khai. Spring hỗ trợ cơ chế xử lý các header như `Forwarded` hoặc `X-Forwarded-Host`, `X-Forwarded-Proto`. Chỉ tin các header này khi chúng được proxy tin cậy thiết lập và proxy đã loại bỏ giá trị do client bên ngoài tự gửi.

Nên kiểm thử href trong môi trường có cấu hình proxy tương tự production. Nếu ứng dụng chỉ dùng relative URI, cần bảo đảm base URI và cách client phân giải link cũng phù hợp với đường dẫn public, đặc biệt khi ứng dụng được triển khai dưới một context path.

## 8. href và các thuộc tính khác của Link

`href` chỉ xác định đích URI. Một `Link` của Spring HATEOAS có thể mang thêm metadata tùy nhu cầu:

| Thuộc tính | Ý nghĩa |
|---|---|
| `rel` | Vai trò của link trong representation |
| `href` | URI reference của đích |
| `title` | Tiêu đề dễ đọc cho link |
| `type` | Gợi ý media type của đích |
| `hreflang` | Ngôn ngữ của tài nguyên đích |
| `templated` | Cho biết href có chứa URI template variables |
| `deprecation` | URI cung cấp thông tin về việc link bị deprecated |

Ví dụ HAL:

```json
{
  "_links": {
    "documentation": {
      "href": "https://docs.example.com/orders",
      "title": "Tài liệu API đơn hàng",
      "type": "text/html",
      "hreflang": "vi"
    }
  }
}
```

Các thuộc tính bổ sung không thay đổi ý nghĩa của href. Client vẫn sử dụng href để truy cập đích; các metadata khác hỗ trợ hiểu và trình bày link.

## 9. Kiểm thử href trong response

Kiểm thử nên xác nhận link tồn tại, đúng relation, đúng đích và không phụ thuộc host nội bộ ngoài ý muốn. Ví dụ với MockMvc:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(org.hamcrest.Matchers.endsWith(
                    "/orders/" + orderId)));
```

Nếu test chạy trong nhiều context path hoặc host khác nhau, hãy kiểm tra phần URI cần ổn định theo hợp đồng thay vì khóa cứng toàn bộ absolute URL. Với link có query parameter, kiểm tra cả tên và giá trị tham số sau khi được encoding.

Với URI template, kiểm thử thuộc tính `templated` và các biến mà API công bố:

```java
mockMvc.perform(get("/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
            .value(org.hamcrest.Matchers.containsString("{?status,page,size}")));
```

Ngoài ra, hãy xác nhận các link quan trọng trỏ đến endpoint có thật và request theo link đó được xử lý đúng. Kiểm thử một chuỗi href khớp mong đợi chưa đủ để chứng minh đích hoạt động hoặc người dùng có quyền truy cập.

## 10. Nguyên tắc thiết kế href

- **Dùng link builder cho mapping nội bộ:** tham chiếu phương thức controller thay vì tự ghép URL.
- **Dùng URI tương đối hoặc tuyệt đối có chủ đích:** bảo đảm client có thể phân giải link trong môi trường triển khai.
- **Đặt query parameter đúng vị trí:** dùng URI template khi client cần điền biến và builder khi tạo URI cụ thể.
- **Encoding dữ liệu đúng cách:** không để ký tự đầu vào phá vỡ cấu trúc path hoặc query.
- **Xử lý forwarded headers có kiểm soát:** tránh tạo absolute href với host hoặc scheme nội bộ sau reverse proxy.
- **Kiểm thử đích link:** xác nhận relation, href, template variables và khả năng truy cập thực tế.

## Kết luận

Trong Spring HATEOAS, `href` là URI reference chỉ đích mà client có thể theo, còn relation giải thích ý nghĩa của liên kết. Dùng `linkTo(methodOn(...))` để tạo href theo mapping controller, `Link.of(...)` cho URI tường minh và URI template khi client cần cung cấp biến. Encoding, base URI và forwarded headers ảnh hưởng trực tiếp đến tính đúng đắn của link; vì vậy cần kiểm thử href trong đúng ngữ cảnh triển khai và xem chúng là một phần của hợp đồng hypermedia.

