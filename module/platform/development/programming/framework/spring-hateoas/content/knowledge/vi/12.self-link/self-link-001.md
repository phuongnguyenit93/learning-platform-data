# Ý nghĩa self link

Trong một API REST có hypermedia, mỗi tài nguyên nên có một liên kết cho biết địa chỉ đại diện của chính nó. Spring HATEOAS biểu diễn quan hệ này bằng relation chuẩn `self`. Một `self link` giúp client nhận diện và truy cập lại tài nguyên hiện tại thông qua URI do server công bố, thay vì phải tự ghép đường dẫn từ ID hoặc đoán cấu trúc URL.

Trong Spring HATEOAS, có thể tạo self link bằng `withSelfRel()` hoặc dùng hằng số `IanaLinkRelations.SELF`. Khi làm việc với Spring MVC, `WebMvcLinkBuilder.linkTo(methodOn(...))` giúp tạo URI dựa trên mapping của controller. Self link có thể được gắn vào `EntityModel`, lớp con `RepresentationModel`, từng phần tử trong collection hoặc chính mô hình collection.

Bài học này thuộc chương **Self link** trong module **SPRING_HATEOAS**, tập trung vào ý nghĩa của relation `self`, vị trí của nó trong biểu diễn tài nguyên, cách tạo link theo controller và cách kiểm thử hợp đồng hypermedia.

Sau bài học, bạn có thể:

- Giải thích self link và phân biệt nó với các relation điều hướng khác.
- Tạo self link bằng `withSelfRel()` hoặc `IanaLinkRelations.SELF`.
- Dùng `linkTo(methodOn(...))` để gắn URI của tài nguyên theo mapping Spring MVC.
- Phân biệt self link của một item với self link của collection hoặc trang dữ liệu.
- Hiểu cách self link xuất hiện trong HAL và cách client sử dụng nó.
- Tránh các lỗi thường gặp liên quan đến URL cố định, proxy và kiểm thử.

## 1. Self link là gì?

Một link trong hypermedia gồm URI đích (`href`) và quan hệ (`rel`). Relation `self` có nghĩa là URI đích xác định chính tài nguyên đang được biểu diễn. Ví dụ, phản hồi của `GET /orders/42` có thể chứa:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    }
  }
}
```

Trong ví dụ, `/orders/42` là URI của chính đơn hàng số 42. Client có thể lưu hoặc theo link này để truy cập lại tài nguyên, chẳng hạn khi cần làm mới dữ liệu sau một thao tác.

Self link có ba vai trò quan trọng:

- **Định danh tài nguyên qua URI:** phản hồi công bố địa chỉ mà server dùng để truy cập tài nguyên hiện tại.
- **Tách client khỏi cấu trúc URL:** client không cần tự nối `/orders/` với ID hoặc suy ra đường dẫn từ tên thuộc tính.
- **Tạo điểm tham chiếu cho biểu diễn:** các thành phần client có thể dùng relation `self` để nhận biết link đại diện cho tài nguyên hiện tại.

Relation `self` là relation chuẩn của IANA. Trong Spring HATEOAS, có thể tham chiếu nó bằng `IanaLinkRelations.SELF` thay vì viết chuỗi `"self"` ở nhiều nơi.

## 2. Self link khác các relation điều hướng như thế nào?

Self link trỏ tới chính tài nguyên hiện tại. Các relation khác mô tả quan hệ tới tài nguyên hoặc bước tiếp theo:

| Relation | Ý nghĩa | Ví dụ |
|---|---|---|
| `self` | Chính tài nguyên hiện tại | Đơn hàng `/orders/42`. |
| `collection` hoặc relation nghiệp vụ như `orders` | Tập hợp chứa hoặc liên quan tới tài nguyên | Danh sách đơn hàng. |
| `next` | Trang tiếp theo | Trang thứ hai của danh sách. |
| `prev` | Trang trước | Trang ngay trước trang hiện tại. |
| `customer` | Tài nguyên khách hàng liên quan | Khách hàng của đơn hàng. |
| `cancel` | Đích của hành động hủy theo hợp đồng API | Endpoint hủy đơn hàng. |

Ví dụ, một đơn hàng có thể có nhiều relation cùng lúc:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "https://api.example.com/orders/42" },
    "orders": { "href": "https://api.example.com/orders" },
    "customer": { "href": "https://api.example.com/customers/7" },
    "cancel": { "href": "https://api.example.com/orders/42/cancellation" }
  }
}
```

Client dùng `self` để truy cập lại đơn hàng, `customer` để khám phá khách hàng liên quan và `cancel` để biết thao tác hủy được cung cấp. Không nên dùng `self` cho link tới collection hoặc endpoint hành động, vì như vậy làm sai ngữ nghĩa relation và khiến client khó diễn giải phản hồi.

## 3. Tạo self link bằng withSelfRel()

Spring HATEOAS cung cấp `withSelfRel()` trên API xây dựng link. Ví dụ đơn giản nhất:

```java
import org.springframework.hateoas.Link;

Link selfLink = Link.of("/orders/42").withSelfRel();
```

Nếu đã có `Link` với relation khác, có thể tạo một link mới với relation `self`:

```java
Link selfLink = Link.of("/orders/42", "self");
```

Tuy nhiên, `withSelfRel()` thể hiện ý định rõ hơn và tránh phải lặp chuỗi relation. Khi cần dùng hằng số chuẩn:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link selfLink = Link.of("/orders/42", IanaLinkRelations.SELF);
```

Ba cách trên đều tạo link mang relation `self`. Trong ứng dụng Spring MVC, thường nên tạo URI dựa trên mapping của controller thay vì viết đường dẫn thủ công.

## 4. Tạo self link từ mapping controller

`WebMvcLinkBuilder` cho phép tạo link từ controller hoặc phương thức controller. `linkTo(...)` xác định mapping đích, còn `methodOn(...)` tạo proxy để Spring HATEOAS đọc mapping và tham số của phương thức.

Đoạn sau giả định ứng dụng đã có `orderService.findResponseById(...)` để lấy DTO `OrderResponse` theo ID.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Long orderId = 42L;
OrderResponse orderResponse = orderService.findResponseById(orderId);

Link selfLink = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();

EntityModel<OrderResponse> model = EntityModel.of(orderResponse, selfLink);
```

Giả sử controller có mapping:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable Long id) {
        OrderResponse response = service.findResponseById(id);
        return EntityModel.of(response,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel());
    }
}
```

Spring HATEOAS dùng mapping `/{id}` cùng giá trị `orderId` để dựng URI của tài nguyên. Nếu đường dẫn controller đổi, code tạo link vẫn tham chiếu phương thức `one(...)`; bạn không phải tìm và sửa các chuỗi `/orders/{id}` rải rác trong assembler.

Lời gọi trong `methodOn(...)` không thực thi logic nghiệp vụ như gọi trực tiếp controller. Nó tạo proxy để framework đọc mapping và tham số phục vụ dựng URI. Vì vậy, không nên đặt truy vấn cơ sở dữ liệu hoặc side effect trong phần biểu thức dùng để tạo link.

## 5. Gắn self link trong RepresentationModelAssembler

Khi nhiều endpoint cùng trả biểu diễn đơn hàng, nên tập trung logic tạo content và link trong `RepresentationModelAssembler`. Mỗi item sẽ nhận self link riêng theo ID của nó.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
                order.getId(), order.getStatus(), order.getTotal());

        return EntityModel.of(
                content,
                linkTo(methodOn(OrderController.class).one(order.getId()))
                        .withSelfRel(),
                linkTo(methodOn(OrderController.class).all())
                        .withRel("orders")
        );
    }
}
```

Trong ví dụ, `self` được tạo cho từng `Order` và trỏ tới endpoint chi tiết của đúng đơn hàng đó. Relation `orders` trỏ tới collection. Assembler giúp các endpoint dùng cùng quy tắc biểu diễn và giảm nguy cơ một endpoint quên thêm self link.

Controller có thể dùng assembler để trả một tài nguyên:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable Long id) {
        Order order = service.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

        return assembler.toModel(order);
    }
}
```

Ví dụ giả định `OrderService.findById` trả về `Optional<Order>`, còn `OrderResponse` là DTO chứa dữ liệu cần công bố. Controller chịu trách nhiệm lấy dữ liệu và xử lý trường hợp không tìm thấy; assembler chịu trách nhiệm chuyển đổi thành biểu diễn hypermedia.

## 6. Self link của item và self link của collection

Self link không chỉ dành cho tài nguyên đơn. Một collection cũng là một tài nguyên có URI riêng, vì vậy phản hồi collection có thể chứa self link trỏ tới chính collection.

Ví dụ collection đơn hàng:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "_links": {
          "self": { "href": "https://api.example.com/orders/42" }
        }
      },
      {
        "id": 43,
        "_links": {
          "self": { "href": "https://api.example.com/orders/43" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "https://api.example.com/orders" }
  }
}
```

Ở đây có ba self link: một cho collection và một cho từng item. Chúng có ý nghĩa khác nhau vì mỗi link nằm trong ngữ cảnh của một tài nguyên khác nhau.

Với collection không phân trang, có thể tạo mô hình như sau:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

import java.util.List;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

List<EntityModel<OrderResponse>> items = orders.stream()
        .map(orderAssembler::toModel)
        .toList();

CollectionModel<EntityModel<OrderResponse>> collection = CollectionModel.of(
        items,
        linkTo(methodOn(OrderController.class).all()).withSelfRel()
);
```

Self link cấp collection trỏ tới endpoint danh sách; self link của từng item trỏ tới endpoint chi tiết. Client có thể theo link collection để tải lại danh sách hoặc theo self link của item để tải lại một đơn hàng cụ thể.

Với collection có filter hoặc sort, self link cần phản ánh đúng URI của tập kết quả hiện tại, bao gồm các query parameter liên quan. Nếu dùng Spring Data và phân trang, nên dùng `PagedResourcesAssembler` để tạo self link cùng các link điều hướng trang dựa trên request hiện tại.

## 7. Self link trong PagedModel

Một trang kết quả cũng là một biểu diễn tài nguyên. Self link của `PagedModel` trỏ tới chính trang hiện tại, bao gồm page, size, sort và các điều kiện lọc của request.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;

// Đây là phương thức bên trong OrderController; repository và orderAssembler
// được inject qua constructor như ví dụ ở phần assembler.
@GetMapping
public PagedModel<EntityModel<OrderResponse>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = repository.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
```

`PagedResourcesAssembler` tạo self link cho trang hiện tại và các link điều hướng như `first`, `prev`, `next`, `last` tùy dữ liệu và cấu hình. Client không cần tự ghép `?page=...&size=...`; nó theo link `self` hoặc relation điều hướng mà server trả về.

Không nên nhầm self link của trang với self link của từng phần tử. Link ở cấp `PagedModel` trỏ tới tập kết quả có phân trang; link trong mỗi `EntityModel` trỏ tới tài nguyên đơn tương ứng.

## 8. Self link trong HAL

HAL dùng thuộc tính `_links` để nhóm các liên kết theo relation. Relation `self` thường được tuần tự hóa thành khóa `self`:

```json
{
  "id": 42,
  "status": "PENDING",
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

Client có thể yêu cầu HAL JSON bằng header:

```http
Accept: application/hal+json
```

Khi nhận phản hồi, client tìm `_links.self.href` để truy cập lại tài nguyên. Cấu trúc `_links` là phần của định dạng HAL; với media type khác, cách tuần tự hóa relation có thể khác. Vì vậy, client cần xử lý theo media type đã thương lượng.

Self link cũng có thể chứa metadata bổ sung như `title`, `type`, `hreflang` hoặc `profile` nếu có ý nghĩa với client. Không nên thêm metadata chỉ để làm phản hồi dài hơn; hãy đưa vào những thuộc tính thực sự giúp client hiểu cách sử dụng link.

## 9. Self link và affordance

Self link xác định tài nguyên hiện tại. Nó không tự động công bố mọi thao tác mà server hỗ trợ trên tài nguyên. Nếu client cần biết cách chỉnh sửa hoặc hủy tài nguyên, có thể gắn affordance vào self link để mô tả các thao tác liên quan.

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

// orderId và model là các biến đã có trong ngữ cảnh tạo biểu diễn.
Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class).cancel(orderId)));

model.add(self);
```

Affordance có thể cung cấp thông tin về HTTP method, kiểu nội dung hoặc dữ liệu đầu vào tùy media type hỗ trợ. HAL JSON cơ bản chủ yếu biểu diễn các link; nếu cần biểu diễn form tương tác, có thể dùng HAL-FORMS. Dù có affordance, server vẫn phải kiểm tra quyền và trạng thái khi request được gửi.

## 10. URL self link, request context và reverse proxy

Self link phải trỏ tới địa chỉ mà client thực sự có thể truy cập. Với `WebMvcLinkBuilder`, Spring HATEOAS thường dựng URI từ request hiện tại và mapping của controller. Trong môi trường triển khai qua reverse proxy, load balancer hoặc API gateway, server có thể nhận request nội bộ với host, scheme hoặc prefix khác địa chỉ công khai.

Ví dụ client truy cập:

```text
https://api.example.com/platform/orders/42
```

nhưng ứng dụng phía sau proxy chỉ nhìn thấy:

```text
http://orders-service:8080/orders/42
```

Nếu header forwarded không được xử lý đúng, self link được tạo có thể chứa host, scheme hoặc path nội bộ mà client bên ngoài không truy cập được. Hãy cấu hình forwarded headers theo hạ tầng triển khai và chỉ tin header từ proxy đáng tin cậy. Với Spring Boot, xem xét `server.forward-headers-strategy` hoặc cấu hình `ForwardedHeaderFilter` phù hợp phiên bản và kiến trúc.

Self link có thể là URI tuyệt đối hoặc URI tương đối tùy hợp đồng và media type. Với API công khai, URI tuyệt đối thường thuận tiện cho client ở nhiều origin. Dù dùng dạng nào, link cần ổn định trong ngữ cảnh triển khai và phải trỏ tới đúng tài nguyên.

Không nên hard-code host và port trong assembler. Nếu cần tạo URI ngoài mapping Spring MVC, dùng cấu hình môi trường hoặc một link builder tập trung thay vì đặt chuỗi URL trong nhiều nơi.

## 11. Kiểm thử self link

Kiểm thử nên xác nhận phản hồi có relation `self`, URI trỏ đúng tài nguyên và media type phù hợp. Ví dụ dùng MockMvc và JSONPath:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSelfLinkTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderResponseContainsSelfLink() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.self.href", containsString("/orders/42")));
    }
}
```

Ví dụ giả định fixture có đơn hàng `42`. Kiểm thử dùng `containsString` để tránh phụ thuộc host và port cụ thể của môi trường. Nếu API có context path hoặc prefix công khai, hãy xác nhận self link chứa prefix client cần truy cập.

Với collection, cần kiểm tra self link cấp collection và self link của từng item ở các đường dẫn JSONPath tương ứng. Với `PagedModel`, kiểm tra self link giữ nguyên `page`, `size`, `sort` và filter của request. Nên có thêm kiểm thử cho resource không tồn tại, URI sau reverse proxy và phản hồi ở media type được hỗ trợ.

## 12. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `self` cho link tới collection hoặc thao tác | Client hiểu sai ngữ nghĩa link. | Chỉ dùng `self` cho chính tài nguyên đang được biểu diễn. |
| Không thêm self link | Client phải dựa vào URL hoặc ID để truy cập lại tài nguyên. | Thêm self link trong assembler hoặc controller. |
| Ghép URI bằng chuỗi | Mapping thay đổi nhưng self link cũ không được cập nhật. | Dùng `linkTo(methodOn(...))`. |
| Chỉ tạo self link cho collection | Các item không có URI riêng để client truy cập. | Thêm self link cho từng item qua assembler. |
| Nhầm self link của trang với self link của item | Client điều hướng sai cấp tài nguyên. | Kiểm tra vị trí relation trong HAL và dùng assembler phù hợp. |
| Hard-code host nội bộ | Client bên ngoài nhận URI không thể truy cập. | Cấu hình forwarded headers và base URI theo triển khai. |
| Cho rằng self link tự mô tả HTTP method | Client không biết cách gửi thao tác cập nhật. | Dùng affordance hoặc tài liệu media type phù hợp. |
| Cho rằng self link là cơ chế phân quyền | Client vẫn có thể gọi URI trực tiếp. | Kiểm tra authentication và authorization ở server. |

## 13. Quy trình tạo self link

Khi xây dựng một representation, hãy thực hiện theo trình tự:

1. Xác định tài nguyên nào đang được biểu diễn: item, collection hay trang kết quả.
2. Xác định URI chuẩn mà client có thể dùng để truy cập tài nguyên đó.
3. Nếu endpoint thuộc Spring MVC, tạo link từ mapping bằng `linkTo(methodOn(...))`.
4. Gắn relation `self` bằng `withSelfRel()` hoặc `IanaLinkRelations.SELF`.
5. Với collection hoặc trang, thêm self link ở cấp collection và link riêng cho từng item nếu cần.
6. Kiểm tra URI trong môi trường có context path, proxy hoặc gateway.
7. Kiểm thử relation, đích URI và media type; hướng dẫn client theo `self` thay vì tự dựng URL.

Self link là điểm tham chiếu cho chính tài nguyên trong một biểu diễn hypermedia. Khi relation được dùng đúng ngữ nghĩa, URI được tạo theo mapping và phản ánh đúng địa chỉ công khai, client có thể truy cập lại tài nguyên mà không cần biết cách server tổ chức đường dẫn nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS – Building links](https://docs.spring.io/spring-hateoas/reference/server/links.html)
- [Spring HATEOAS – Representation models](https://docs.spring.io/spring-hateoas/reference/server/representation-models.html)
- [Spring HATEOAS – HAL media type](https://docs.spring.io/spring-hateoas/reference/mediatypes.html)
- [IANA – Link Relation Types registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
