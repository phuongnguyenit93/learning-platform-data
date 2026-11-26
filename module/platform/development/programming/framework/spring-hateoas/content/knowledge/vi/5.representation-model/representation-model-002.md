# Model không có nội dung

## Mục tiêu

Sau bài này, bạn có thể giải thích vai trò của `RepresentationModel` khi response không cần mang dữ liệu nghiệp vụ, tạo một representation chỉ chứa các liên kết, phân biệt kiểu model này với `EntityModel`, `CollectionModel` và HTTP 204, đồng thời kiểm thử cấu trúc hypermedia được trả về.

## 1. Khi nào cần model không có nội dung?

Một API thường trả về dữ liệu của tài nguyên cùng các liên kết điều hướng. Ví dụ, khi đọc đơn hàng, client nhận được mã đơn, trạng thái và link đến các tài nguyên liên quan.

Tuy nhiên, có những endpoint chủ yếu giúp client khám phá đường đi tiếp theo. Endpoint có thể trả về một tập liên kết đến tài nguyên chính, danh sách hoặc các phần liên quan mà không cần lặp lại dữ liệu nghiệp vụ. Trong trường hợp đó, một representation chỉ có hypermedia là đủ.

Spring HATEOAS cung cấp lớp cơ sở `RepresentationModel` để biểu diễn một model có thể mang các link. Khi không cần payload domain, ta có thể dùng trực tiếp kiểu model này hoặc tạo một lớp con chuyên biệt. Response khi được tuần tự hóa theo HAL có thể chỉ chứa phần `_links`.

Ví dụ:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42/navigation"
    },
    "order": {
      "href": "/orders/42"
    },
    "orders": {
      "href": "/orders"
    }
  }
}
```

Representation vẫn có nội dung ở cấp HTTP: nó là một tài liệu hypermedia có các liên kết. Cụm từ “model không có nội dung” ở đây có nghĩa là model không bao một đối tượng nghiệp vụ hoặc các trường dữ liệu domain; không có nghĩa response hoàn toàn rỗng.

## 2. Phân biệt RepresentationModel với các kiểu model khác

Spring HATEOAS có một số kiểu model phục vụ những nhu cầu khác nhau:

| Kiểu model | Dữ liệu chính | Mục đích |
|---|---|---|
| `RepresentationModel<T>` | Không bắt buộc có payload domain; tập trung vào links | Tạo model hypermedia cơ sở hoặc model tùy chỉnh |
| `EntityModel<T>` | Một đối tượng `T` cùng links | Biểu diễn một tài nguyên |
| `CollectionModel<T>` | Một tập hợp phần tử cùng links | Biểu diễn collection |
| `PagedModel<T>` | Các phần tử và metadata trang | Biểu diễn collection có phân trang |

Ví dụ về một tài nguyên có dữ liệu:

```java
EntityModel<Order> orderModel = EntityModel.of(
        order,
        linkTo(methodOn(OrderController.class)
                .getOrder(order.getId())).withSelfRel()
);
```

Ví dụ về collection không có phần tử:

```java
CollectionModel<EntityModel<Order>> emptyOrders =
        CollectionModel.empty();
emptyOrders.add(linkTo(methodOn(OrderController.class)
        .getOrders()).withSelfRel());
```

`CollectionModel.empty(...)` biểu diễn một collection hiện không có phần tử. Nó vẫn có ngữ nghĩa collection. Một `RepresentationModel` chỉ có links phù hợp hơn khi mục tiêu response là công bố các quan hệ điều hướng mà không biểu diễn một tập hợp.

Không nên chọn kiểu model chỉ vì response hiện tại có ít trường. Nếu client cần nhận một tài nguyên với thuộc tính như mã, trạng thái hoặc thời điểm tạo, hãy dùng `EntityModel<T>` hoặc một representation tùy chỉnh có trường dữ liệu. Dùng model chỉ có links khi chính các quan hệ hypermedia là thông tin cần trả về.

## 3. Tạo model chỉ chứa links

Có thể tạo một lớp con của `RepresentationModel` để đặt tên rõ ràng cho loại response. Lớp này không khai báo trường dữ liệu domain:

```java
import org.springframework.hateoas.RepresentationModel;

public class OrderNavigationModel
        extends RepresentationModel<OrderNavigationModel> {
}
```

Tham số generic là kiểu của chính lớp con. Cách khai báo này cho phép các phương thức fluent của `RepresentationModel`, chẳng hạn `add(...)`, trả về đúng kiểu model cụ thể.

Assembler chịu trách nhiệm tạo các liên kết cho model:

```java
import java.util.UUID;

import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderNavigationAssembler {

    public OrderNavigationModel toModel(UUID id) {
        OrderNavigationModel model = new OrderNavigationModel();

        model.add(linkTo(methodOn(OrderController.class)
                .getNavigation(id)).withSelfRel());

        model.add(linkTo(methodOn(OrderController.class)
                .getOrder(id)).withRel("order"));

        model.add(linkTo(methodOn(OrderController.class)
                .getOrders()).withRel("orders"));

        return model;
    }
}
```

Trong ví dụ, model có ba liên kết:

- `self` trỏ đến endpoint đang trả về navigation model.
- `order` trỏ đến tài nguyên đơn hàng cụ thể.
- `orders` trỏ đến collection đơn hàng.

Các phương thức `getNavigation`, `getOrder` và `getOrders` là mapping của controller. `methodOn` cho Spring HATEOAS thông tin về phương thức đích để xây URL theo mapping, thay vì phải tự ghép chuỗi đường dẫn.

Import `WebMvcLinkBuilder` trong ví dụ chỉ cần thiết khi dùng Spring MVC. Với ứng dụng WebFlux, hãy sử dụng API link builder phù hợp với stack WebFlux.

## 4. Trả model từ controller

Controller có thể trả model điều hướng như một response bình thường:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderModelAssembler;
    private final OrderNavigationAssembler navigationAssembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler orderModelAssembler,
            OrderNavigationAssembler navigationAssembler) {
        this.orderService = orderService;
        this.orderModelAssembler = orderModelAssembler;
        this.navigationAssembler = navigationAssembler;
    }

    @GetMapping("/{id}")
    public EntityModel<Order> getOrder(@PathVariable UUID id) {
        return orderModelAssembler.toModel(
                orderService.getRequired(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<Order>> getOrders() {
        return orderModelAssembler.toCollectionModel(orderService.findAll());
    }

    @GetMapping(
        value = "/{id}/navigation",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    public OrderNavigationModel getNavigation(@PathVariable UUID id) {
        orderService.getRequired(id);
        return navigationAssembler.toModel(id);
    }
}
```

Đoạn controller minh họa cách tách endpoint navigation khỏi endpoint trả dữ liệu đơn hàng. Lời gọi `getRequired(id)` xác nhận đơn hàng tồn tại trước khi công bố các liên kết. Trong ứng dụng thực tế, việc kiểm tra quyền truy cập cũng cần được thực hiện theo chính sách của endpoint.

Các import chính cho controller gồm:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
```

Ví dụ rút gọn giả định ứng dụng đã có `OrderService`, `OrderModelAssembler` và phương thức tạo collection model. Trong dự án thực tế, giữ mỗi endpoint tập trung vào việc gọi service và assembler tương ứng; không đưa logic truy vấn phức tạp vào model.

## 5. Biểu diễn bằng HAL

Khi endpoint trả về `OrderNavigationModel` và client yêu cầu HAL, Spring HATEOAS tuần tự hóa các liên kết vào thuộc tính `_links`.

Client có thể gửi:

```http
GET /orders/42/navigation HTTP/1.1
Accept: application/hal+json
```

Response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42/navigation"
    },
    "order": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    }
  }
}
```

Response không có trường `id`, `status` hoặc các thuộc tính khác của đơn hàng. Client sử dụng relation để xác định liên kết nào cần đi theo. Relation chuẩn như `self` giúp mô tả quan hệ phổ biến; relation nghiệp vụ như `order` cần có ý nghĩa ổn định và được client hiểu.

Để response được tuần tự hóa đúng định dạng, ứng dụng Spring Boot thường thêm dependency:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
```

Client nên gửi `Accept` phù hợp và server cần có cấu hình message converter cho media type đó. Nếu endpoint trả model nhưng client yêu cầu một định dạng không được hỗ trợ, việc thương lượng nội dung có thể thất bại với lỗi HTTP 406.

## 6. Model chỉ có links khác gì HTTP 204?

Đây là hai lựa chọn khác nhau về hợp đồng HTTP.

| Trường hợp | Response | Ý nghĩa |
|---|---|---|
| Trả model chỉ có links | `200 OK` cùng representation HAL | Server trả về một tài liệu hypermedia để client điều hướng |
| Không trả representation | `204 No Content` | Request thành công và response không có body |

Ví dụ endpoint chỉ xác nhận thao tác đã hoàn tất và không cần cung cấp thông tin điều hướng:

```java
@DeleteMapping("/{id}")
public ResponseEntity<Void> deleteOrder(@PathVariable UUID id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
```

Nếu client cần khám phá tài nguyên tiếp theo sau thao tác, có thể trả về một representation chứa links. Nếu không có dữ liệu hay liên kết nào cần trả, `204 No Content` diễn đạt ý định rõ hơn.

Không nên trả `204` rồi kỳ vọng client đọc được `_links` trong body. Theo ngữ nghĩa HTTP, response 204 không mang nội dung response.

## 7. Kiểm thử model không có nội dung

Kiểm thử cần xác nhận response có đúng media type, có các relation dự kiến và không vô tình đưa dữ liệu domain vào payload.

Ví dụ với MockMvc:

```java
mockMvc.perform(get("/orders/{id}/navigation", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.order.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$.id").doesNotExist())
    .andExpect(jsonPath("$.status").doesNotExist());
```

Nên bổ sung kiểm thử cho các tình huống sau:

1. Đơn hàng không tồn tại thì endpoint trả về mã lỗi phù hợp, không tạo navigation model cho tài nguyên không hợp lệ.
2. Người dùng không có quyền truy cập thì server từ chối theo chính sách bảo mật.
3. Link được tạo theo mapping thực tế và chứa đúng định danh tài nguyên.
4. Các relation mà client phụ thuộc được giữ ổn định khi controller hoặc cấu trúc nội bộ thay đổi.
5. Endpoint trả `204` không có body nếu hợp đồng của thao tác quy định không có representation.

Kiểm thử các relation và trạng thái HTTP giúp xác nhận hợp đồng hypermedia. Không nên chỉ kiểm tra response là JSON hợp lệ, vì JSON hợp lệ vẫn có thể thiếu link mà client cần.

## 8. Nguyên tắc thiết kế

Khi dùng model không có nội dung, hãy giữ một số nguyên tắc:

- **Chỉ công bố link có ý nghĩa:** mỗi relation nên dẫn đến một tài nguyên hoặc bước điều hướng mà client có thể sử dụng.
- **Có link self khi phù hợp:** nếu model đại diện cho một endpoint có thể được truy cập lại, relation `self` giúp client nhận diện chính representation đó.
- **Không lặp dữ liệu không cần thiết:** nếu client cần thông tin domain, trả model có payload phù hợp thay vì buộc client gọi thêm endpoint chỉ để lấy trường cơ bản.
- **Giữ relation ổn định:** đổi tên relation có thể phá vỡ logic điều hướng của client.
- **Bảo vệ endpoint ở server:** việc không công bố link không thay thế kiểm tra xác thực, phân quyền hoặc trạng thái nghiệp vụ ở endpoint đích.

Model chỉ có links hữu ích cho các response điều hướng, entry point hoặc view siêu dữ liệu hypermedia. Dùng nó có chủ đích giúp API trả đúng thông tin mà client cần và giữ ranh giới rõ ràng giữa dữ liệu tài nguyên với khả năng điều hướng.

## Kết luận

`RepresentationModel` là nền tảng để tạo representation có hypermedia mà không cần bao một đối tượng domain. Một lớp con không khai báo trường dữ liệu có thể tập trung vào các relation như `self`, `order` và `orders`, sau đó được Spring HATEOAS tuần tự hóa thành response HAL chỉ chứa `_links`. Hãy phân biệt response điều hướng này với `EntityModel`, collection rỗng và HTTP 204, rồi kiểm thử relation, media type và trạng thái HTTP như một phần của hợp đồng API.

