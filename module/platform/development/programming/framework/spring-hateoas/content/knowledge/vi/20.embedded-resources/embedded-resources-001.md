# Embedded resource là gì?

**Embedded resource** là biểu diễn của một tài nguyên liên quan được nhúng trực tiếp bên trong response của tài nguyên hiện tại. Thay vì chỉ cung cấp một URI để client gửi request riêng, server đưa dữ liệu biểu diễn của tài nguyên liên quan vào response, thường kèm các liên kết của chính tài nguyên được nhúng.

Trong HAL JSON, embedded resource được đặt trong thuộc tính **_embedded** và được nhóm theo link relation. Ví dụ, response collection đơn hàng có thể nhúng các biểu diễn đơn hàng dưới relation **orders**. Mỗi đơn hàng vẫn có thể mang self link riêng trong **_links**.

Spring HATEOAS sử dụng các model như **CollectionModel**, **EntityModel** và **RepresentationModel** để xây dựng response hypermedia. Khi serialize theo HAL, collection model được biểu diễn bằng cấu trúc embedded resources; các relation giúp client nhận biết loại tài nguyên được nhúng.

Trong module SPRING_HATEOAS, embedded resource là một cách tổ chức representation để client khám phá dữ liệu liên quan qua hypermedia. Bài học này giải thích khái niệm embedded resource, cấu trúc _embedded của HAL, sự khác nhau giữa embed và link, cách Spring HATEOAS tạo collection representation, cách đặt tên relation và những đánh đổi khi nhúng dữ liệu.

Sau bài học, bạn có thể:

- Giải thích embedded resource và vai trò của nó trong hypermedia.
- Phân biệt embedded resource với link và object lồng nhau thông thường.
- Đọc cấu trúc _embedded và _links trong HAL JSON.
- Dùng CollectionModel và model của từng item để tạo embedded resources.
- Tùy chỉnh tên relation bằng @Relation và hiểu vai trò của LinkRelationProvider.
- Quyết định khi nào nên embed dữ liệu và khi nào nên chỉ cung cấp link.
- Kiểm thử relation, nội dung và link của embedded resources.

## Embedded resource giải quyết vấn đề gì?

Giả sử API trả về danh sách đơn hàng. Nếu response chỉ chứa các ID hoặc link đến từng đơn hàng, client cần gửi thêm request để lấy chi tiết từng item. Với một trang có nhiều item, số lần gọi mạng có thể tăng lên đáng kể.

Response chỉ có link:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    },
    "orders": [
      { "href": "/orders/42" },
      { "href": "/orders/43" }
    ]
  }
}
~~~

Client phải gọi từng URI nếu cần nội dung của từng đơn hàng. Với embedded resources, server có thể trả nội dung item ngay trong response collection:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "description": "Bàn phím cơ",
        "status": "PAID",
        "_links": {
          "self": { "href": "/orders/42" }
        }
      },
      {
        "id": 43,
        "description": "Chuột không dây",
        "status": "PENDING_PAYMENT",
        "_links": {
          "self": { "href": "/orders/43" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
~~~

Client có thể đọc dữ liệu cần thiết ngay trong response, đồng thời vẫn có self link để truy cập lại từng item khi cần. Cách này giảm các request tuần tự và tạo một representation collection giàu thông tin.

## Embedded resource là một khái niệm hypermedia

Embedded resource là một representation của tài nguyên được đặt bên trong representation khác. Nó có định danh ngữ nghĩa thông qua relation và có thể có các link riêng. Nó không nhất thiết tương ứng với một object được lưu lồng trong cùng một bản ghi cơ sở dữ liệu.

Ví dụ, một đơn hàng có thể tham chiếu đến khách hàng. API có thể trả đơn hàng cùng một biểu diễn khách hàng được nhúng. Khách hàng vẫn là tài nguyên độc lập, có thể có URI và vòng đời riêng; việc nhúng chỉ là cách response hiện tại cung cấp thêm biểu diễn của khách hàng.

### Embedded resource khác object lồng nhau thông thường

JSON có thể chứa object lồng nhau mà không dùng hypermedia:

~~~json
{
  "id": 42,
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  }
}
~~~

Trong ví dụ, shippingAddress có thể chỉ là một value object thuộc đơn hàng. Nó không nhất thiết là một tài nguyên có URI độc lập hoặc có link relation.

Embedded resource trong HAL có ngữ nghĩa tài nguyên rõ ràng và được đặt dưới _embedded:

~~~json
{
  "id": 42,
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Nguyễn An",
      "_links": {
        "self": { "href": "/customers/7" }
      }
    }
  },
  "_links": {
    "self": { "href": "/orders/42" }
  }
}
~~~

Ở đây customer là một tài nguyên liên quan được nhúng, có relation customer và self link riêng. Dữ liệu được nhúng có thể được tải độc lập thông qua URI của chính nó.

### Embedded resource không phải JPA @Embedded

Không nhầm embedded resource trong hypermedia với annotation @Embedded của JPA:

| Khái niệm | Tầng | Ý nghĩa |
| --- | --- | --- |
| Embedded resource | HTTP representation / hypermedia | Nhúng biểu diễn của tài nguyên liên quan vào response |
| JPA @Embedded | Persistence | Ánh xạ một embeddable value object vào entity |
| JSON nested object | Cấu trúc dữ liệu | Object nằm trong object khác; không tự có semantics hypermedia |

Một tài nguyên được nhúng trong HAL có thể được lấy từ một bảng khác, dịch vụ khác hoặc projection tổng hợp. Ngược lại, một JPA embeddable value object có thể chỉ được serialize thành thuộc tính JSON bình thường.

## _embedded và _links trong HAL JSON

HAL JSON dùng hai thuộc tính quan trọng:

- **_links** chứa các liên kết đến tài nguyên hoặc đích điều hướng khác.
- **_embedded** chứa các representation tài nguyên được nhúng trong response hiện tại.

Hai phần này bổ sung cho nhau. _embedded mang nội dung; _links cung cấp khả năng điều hướng. Một embedded resource cũng có thể chứa _links của riêng nó.

Ví dụ:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": { "href": "/orders/42" },
          "customer": { "href": "/customers/7" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" },
    "profile": { "href": "/profiles/order-list" }
  }
}
~~~

Trong response này:

- _embedded.orders xác định các tài nguyên đơn hàng được nhúng trong collection.
- _links.self ở cấp ngoài trỏ đến collection đơn hàng.
- _links.self bên trong item trỏ đến chính đơn hàng đó.
- _links.customer bên trong item cung cấp đường dẫn đến khách hàng liên quan.

Relation orders là tên quan hệ của tài nguyên nhúng, không phải URI. URI của từng item được tìm trong self link bên trong embedded representation.

### Relation trong _embedded

Mỗi embedded resource hoặc nhóm embedded resources được đặt dưới một relation. Relation giúp client nhận biết loại tài nguyên mà key đại diện.

Ví dụ:

| Relation | Nội dung được nhúng | Ý nghĩa |
| --- | --- | --- |
| orders | Danh sách đơn hàng | Các đơn hàng trong collection |
| customer | Một khách hàng | Khách hàng liên quan đến tài nguyên hiện tại |
| items | Danh sách dòng hàng | Các dòng hàng thuộc đơn hàng |
| reviews | Danh sách đánh giá | Các đánh giá của sản phẩm |

Tên relation nên có semantics rõ ràng, nhất quán và được giữ ổn định. Client nên chọn nội dung theo relation thay vì phụ thuộc vào thứ tự thuộc tính JSON.

## Embedded resource trong Spring HATEOAS

Spring HATEOAS dùng các model để biểu diễn tài nguyên và collection:

| Kiểu | Vai trò |
| --- | --- |
| RepresentationModel<T> | Model tùy chỉnh có thể mang links |
| EntityModel<T> | Bọc một content object cùng links |
| CollectionModel<T> | Bọc một tập hợp phần tử cùng links ở cấp collection |
| PagedModel<T> | Biểu diễn trang kết quả, gồm content, metadata và links |

Khi trả một CollectionModel theo HAL, các phần tử của collection được serialize thành embedded resources dưới _embedded. Kiểu của từng phần tử quyết định nội dung được nhúng:

- CollectionModel<OrderResponse> nhúng các DTO đơn hàng. DTO không tự có link riêng nếu nó không phải representation model.
- CollectionModel<EntityModel<OrderResponse>> nhúng từng EntityModel, do đó mỗi item có thể có links riêng.
- CollectionModel<OrderModel> nhúng các model tùy chỉnh kế thừa RepresentationModel, mỗi item có thể chứa dữ liệu và links.

Nếu client cần truy cập độc lập từng item, nên cung cấp self link cho từng embedded resource.

## Tạo embedded resources bằng CollectionModel

Giả sử API có domain object Order và DTO công khai OrderResponse:

~~~java
public record OrderResponse(
    Long id,
    String description,
    String status
) {}
~~~

Assembler chuyển từng đơn hàng thành EntityModel:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
            order.id(), order.description(), order.status());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
    }
}
~~~

Controller tạo collection:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderResponse>> all() {
        List<EntityModel<OrderResponse>> items = orderService.findAll().stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
~~~

Ví dụ giả định OrderService.findAll() trả về List<Order>, Order có các accessor id(), description() và status(), còn OrderController.one(id) là endpoint chi tiết.

CollectionModel chứa các EntityModel. Khi serialize theo HAL, mỗi EntityModel được nhúng dưới relation của collection và mang self link riêng. CollectionModel có self link ở cấp ngoài.

Response HAL có thể có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "description": "Bàn phím cơ",
        "status": "PAID",
        "_links": {
          "self": { "href": "https://api.example.com/orders/42" }
        }
      },
      {
        "id": 43,
        "description": "Chuột không dây",
        "status": "PENDING_PAYMENT",
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
~~~

Tên relation orders phụ thuộc relation provider và kiểu representation được nhúng. Có thể tùy chỉnh tên này để giữ hợp đồng công khai ổn định.

## Tùy chỉnh tên embedded relation bằng @Relation

Spring HATEOAS dùng LinkRelationProvider để xác định relation cho representation model và collection. Provider mặc định có thể suy ra tên relation từ kiểu model. Khi API cần tên ổn định theo hợp đồng, có thể dùng annotation @Relation trên lớp model tùy chỉnh.

Ví dụ model đơn hàng:

~~~java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(value = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private final Long id;
    private final String description;
    private final String status;

    public OrderModel(Long id, String description, String status) {
        this.id = id;
        this.description = description;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Hai thuộc tính annotation có ý nghĩa:

- value chỉ định relation dùng cho một representation item.
- collectionRelation chỉ định relation dùng khi một collection các item được nhúng.

Với cấu hình trên, collection của OrderModel có thể được biểu diễn dưới relation orders. Việc khai báo rõ tên relation giúp tránh để tên lớp Java hoặc quy tắc pluralization trở thành một phần ngoài ý muốn của hợp đồng API.

Assembler có thể trả trực tiếp OrderModel:

~~~java
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
            order.id(), order.description(), order.status());

        model.add(linkTo(methodOn(OrderController.class)
            .one(order.id())).withSelfRel());

        return model;
    }
}
~~~

Controller có thể trả:

~~~java
@GetMapping
CollectionModel<OrderModel> all() {
    return assembler.toCollectionModel(orderService.findAll())
        .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
~~~

RepresentationModelAssembler cung cấp toCollectionModel để chuyển từng entity thành model rồi bọc thành CollectionModel. Relation collection được dùng khi HAL serializer đặt các model trong _embedded.

### Collection rỗng và fallback type

Khi collection không có phần tử, serializer không thể dựa vào item thực tế để suy luận relation của kiểu embedded. Nếu tên relation cần ổn định giữa response có phần tử và response rỗng, cung cấp fallback type:

~~~java
CollectionModel<OrderModel> empty = CollectionModel.<OrderModel>empty()
    .withFallbackType(OrderModel.class)
    .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
~~~

Fallback type cho serializer biết loại representation dự kiến ngay cả khi collection rỗng. Hãy kiểm thử response rỗng trên phiên bản Spring HATEOAS mà ứng dụng sử dụng để bảo đảm relation trong _embedded hoặc cấu trúc collection được tạo đúng theo hợp đồng.

## Embedded resource và link: nên chọn cách nào?

Embed và link phục vụ hai nhu cầu khác nhau:

- **Embed:** client cần dữ liệu của tài nguyên liên quan ngay trong response hiện tại.
- **Link:** client cần biết tài nguyên liên quan ở đâu và có thể tải nó khi cần.

| Tiêu chí | Embedded resource | Link |
| --- | --- | --- |
| Nội dung response | Có biểu diễn của tài nguyên liên quan | Có URI đích |
| Số request của client | Có thể giảm request tiếp theo | Client có thể cần request riêng |
| Kích thước payload | Thường lớn hơn | Thường nhỏ hơn |
| Tính độc lập | Response cha chứa bản sao biểu diễn tại thời điểm tạo | Tài nguyên được tải độc lập |
| Cập nhật dữ liệu | Có thể cũ khi tài nguyên liên quan thay đổi | Request mới lấy biểu diễn mới |
| Phù hợp khi | Dữ liệu liên quan nhỏ, thường được đọc cùng nhau | Dữ liệu lớn, độc lập hoặc ít khi cần |

Không cần embed mọi tài nguyên liên quan. Một response lớn có thể làm tăng thời gian truyền, bộ nhớ và chi phí serialize. Nếu client chỉ cần một số thông tin nhỏ, có thể embed projection gọn; nếu cần dữ liệu đầy đủ, công bố link để client tải khi cần.

### Ví dụ kết hợp embed và link

Một collection đơn hàng có thể nhúng các trường tóm tắt của từng đơn hàng, nhưng vẫn công bố link đến chi tiết:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": { "href": "/orders/42" },
          "invoice": { "href": "/orders/42/invoice" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
~~~

Client có thể dùng status ngay mà không cần tải lại item. Khi cần hóa đơn, client theo relation invoice. Khi cần representation chi tiết hơn, client theo self.

## Lợi ích và chi phí của embedded resources

### Lợi ích

- Giảm số request khi client thường xuyên cần dữ liệu liên quan cùng lúc.
- Giảm độ trễ do nhiều request nối tiếp.
- Cung cấp representation giàu ngữ cảnh trong một response.
- Cho phép client hiển thị danh sách hoặc màn hình tổng quan nhanh hơn.
- Vẫn giữ khả năng điều hướng nếu mỗi embedded resource có links riêng.

### Chi phí và rủi ro

- Payload lớn hơn, tăng băng thông và chi phí serialize/deserialize.
- Có thể gây truy vấn N+1 nếu server tải từng tài nguyên liên quan riêng lẻ.
- Dữ liệu nhúng có thể cũ so với tài nguyên độc lập.
- Response cha bị gắn chặt hơn với cấu trúc của tài nguyên con.
- Quan hệ vòng có thể tạo response đệ quy hoặc quá sâu.
- Dữ liệu nhạy cảm có thể bị lộ nếu không áp dụng quyền ở cấp embedded resource.

Embed giúp giảm request từ client nhưng không tự làm server truy vấn hiệu quả. Hãy dùng projection, batch query, fetch strategy hoặc cache phù hợp để tránh N+1.

## Thiết kế embedded resources có kiểm soát

### Chỉ nhúng dữ liệu client thực sự cần

Trước khi embed, hãy xác định màn hình hoặc luồng client đang phục vụ. Nếu collection chỉ cần ID, trạng thái và ngày tạo, đừng nhúng toàn bộ hồ sơ khách hàng, địa chỉ và lịch sử giao dịch.

DTO hoặc projection giúp kiểm soát các trường được công bố:

~~~java
import java.time.Instant;

public record OrderSummary(
    Long id,
    String status,
    Instant createdAt
) {}
~~~

Có thể dùng OrderSummary làm content của item representation. Khi client cần chi tiết, cung cấp self link đến endpoint item.

### Tránh collection nhúng không giới hạn

Không nên nhúng toàn bộ lịch sử giao dịch hoặc hàng nghìn phần tử vào một response. Dùng CollectionModel hoặc PagedModel để phân trang, hoặc chỉ embed một tập con có giới hạn cùng link đến collection đầy đủ.

### Tránh vòng lặp tài nguyên

Giả sử Order embed Customer, trong khi Customer lại embed toàn bộ Orders. Nếu cả hai hướng đều mở rộng đầy đủ, response có thể lặp vô hạn hoặc tăng kích thước rất lớn.

Hãy xác định độ sâu embed:

~~~text
Order
  └── customer (embedded summary)
        └── self link

Customer
  └── orders (link to collection)
~~~

Một hướng nhúng có thể dùng representation tóm tắt; chiều ngược lại chỉ cung cấp link. Điều này giữ response dễ dự đoán và tránh lặp graph tài nguyên.

### Tôn trọng quyền truy cập

Việc người dùng được đọc tài nguyên cha không đồng nghĩa họ được đọc mọi dữ liệu của tài nguyên con. Trước khi embed:

- Kiểm tra quyền truy cập của tài nguyên liên quan.
- Chỉ đưa các trường mà người dùng hiện tại được phép xem.
- Không nhúng token, thông tin xác thực hoặc dữ liệu nội bộ.
- Xem xét ranh giới tenant và quyền sở hữu.
- Không dựa vào việc ẩn link hoặc không embed để thay thế kiểm tra quyền ở endpoint.

Server phải áp dụng cùng chính sách bảo mật cho request tải độc lập và cho dữ liệu được nhúng trong response khác.

### Xem xét cache và độ mới dữ liệu

Embedded resource là một phần của response cha tại thời điểm response được tạo. Nếu tài nguyên con thay đổi, bản nhúng trong cache của tài nguyên cha có thể chưa cập nhật.

Hãy xác định:

- Thời gian cache của response cha.
- Tần suất thay đổi của dữ liệu con.
- Có cần ETag hoặc cache validator để phát hiện thay đổi không.
- Khi dữ liệu con thay đổi, có cần làm mới hoặc vô hiệu cache của tài nguyên cha không.

Nếu dữ liệu con thay đổi thường xuyên và cần độ mới cao, chỉ cung cấp link có thể phù hợp hơn để client tải representation mới.

## Embedded resource trong controller và assembler

Controller thường không nên tự xây JSON _embedded bằng cách thao tác map. Hãy trả model Spring HATEOAS để serializer tạo cấu trúc HAL.

Ví dụ đầy đủ hơn:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
            order.id(), order.description(), order.status());

        return EntityModel.of(content,
            linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel());
    }
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderAssembler assembler;

    OrderController(OrderService orderService, OrderAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderResponse>> all() {
        List<EntityModel<OrderResponse>> items = orderService.findAll().stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> one(@PathVariable Long id) {
        Order order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return assembler.toModel(order);
    }
}
~~~

Ví dụ giả định OrderService cung cấp findAll() và findById(), OrderResponse là DTO công khai, và các import cho Order, OrderService, HttpStatus, PathVariable cùng ResponseStatusException được khai báo trong ứng dụng. Controller trả CollectionModel chứa các EntityModel; serializer HAL tạo _embedded cho collection và giữ links của từng item.

## Kiểm thử embedded resources

Kiểm thử cần xác minh cả relation của collection, dữ liệu item được nhúng và link của từng item. Chỉ kiểm tra HTTP 200 hoặc số phần tử không đủ để bảo đảm hợp đồng hypermedia.

Ví dụ với Spring MVC Test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderEmbeddedResourcesTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void collectionEmbedsOrdersWithSelfLinks() throws Exception {
        mockMvc.perform(get("/orders").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath("$._embedded.orders[0].id").exists())
            .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
    }
}
~~~

Test giả định dữ liệu kiểm thử có ít nhất một đơn hàng và relation collection được đặt tên orders. Nếu ứng dụng dùng @Relation hoặc LinkRelationProvider tùy chỉnh, JSONPath phải khớp với relation thực tế.

Nên có thêm test cho:

1. Collection có nhiều item và mỗi item có đúng các trường được phép công bố.
2. Relation _embedded ổn định và không phụ thuộc tên class Java ngoài ý muốn.
3. Self link của từng embedded resource trỏ đến đúng endpoint item.
4. Collection rỗng vẫn có response hợp lệ và relation được xác định đúng nếu hợp đồng yêu cầu.
5. Tài nguyên con bị giới hạn quyền không bị lộ qua embedded representation.
6. Dữ liệu nhúng không chứa các trường nội bộ hoặc nhạy cảm.
7. Kích thước collection và payload được giới hạn hoặc phân trang.
8. Client vẫn có thể dùng link để tải tài nguyên độc lập khi cần.

## Những sai lầm thường gặp

**Nhầm _embedded với _links.** _embedded chứa representation của tài nguyên liên quan; _links chứa URI để điều hướng. Embedded resource có thể có links riêng.

**Nghĩ mọi object JSON lồng nhau đều là embedded resource.** Object lồng nhau có thể chỉ là value object. Embedded resource trong HAL được đặt dưới _embedded và có relation xác định.

**Nhầm embedded resource với JPA @Embedded.** Một khái niệm thuộc hypermedia response, khái niệm kia thuộc persistence mapping.

**Embed toàn bộ dữ liệu liên quan.** Payload lớn, truy vấn N+1 và rò rỉ dữ liệu có thể xảy ra. Chỉ embed phần client cần.

**Bỏ self link của item.** Client có thể đọc item nhưng không có URI chuẩn để tải lại tài nguyên độc lập. Thêm self link khi item có endpoint riêng.

**Không ổn định tên relation.** Tên relation trong _embedded là một phần hợp đồng API. Dùng @Relation khi cần kiểm soát tên item và collection relation.

**Không xử lý collection rỗng.** Khi không có item, serializer có thể thiếu thông tin để suy ra relation. Cân nhắc fallback type và kiểm thử response rỗng.

**Tạo vòng lặp embed.** Quan hệ hai chiều có thể làm response quá sâu hoặc phình lớn. Giới hạn độ sâu và chọn một hướng dùng link.

**Coi embed là quyền truy cập.** Dữ liệu nhúng vẫn phải tuân thủ xác thực, phân quyền và quy tắc lọc trường như endpoint độc lập.

## Kết luận

Embedded resource là biểu diễn của tài nguyên liên quan được nhúng trong response hiện tại. Trong HAL JSON, nó nằm dưới _embedded và được nhận diện bằng relation; _links cung cấp khả năng điều hướng, còn từng embedded resource có thể mang links riêng. Spring HATEOAS dùng CollectionModel để biểu diễn collection và EntityModel hoặc RepresentationModel tùy chỉnh để mỗi item có dữ liệu cùng links.

Hãy embed khi client thường cần dữ liệu liên quan ngay cùng response và kích thước payload vẫn hợp lý. Dùng link khi tài nguyên độc lập, lớn, thay đổi thường xuyên hoặc chỉ được truy cập khi cần. Kiểm soát relation bằng @Relation khi cần hợp đồng ổn định, giới hạn độ sâu và kích thước, tránh N+1, bảo vệ dữ liệu nhúng và kiểm thử cả nội dung lẫn links.
