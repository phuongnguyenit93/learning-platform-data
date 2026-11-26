# Relation collection

Trong hypermedia, một tài nguyên có thể cần chỉ ra collection mà nó thuộc về, còn collection có thể công bố các tài nguyên thành viên. IANA đăng ký hai link relation `collection` và `item` để diễn đạt hai chiều liên kết này. Relation `collection` cho biết đích của link là một tài nguyên đại diện cho collection; relation `item` cho biết đích là một thành viên của collection được biểu diễn bởi tài nguyên chứa link.

Spring HATEOAS cung cấp `IanaLinkRelations.COLLECTION` và `IanaLinkRelations.ITEM` để tạo các link này mà không phải tự gõ tên relation. Khi serialize HAL, chúng xuất hiện trong `_links`. Cần phân biệt link relation IANA `collection`/`item` với relation dùng làm khóa `_embedded`, chẳng hạn `orders`, do `@Relation` hoặc `LinkRelationProvider` xác định.

## Ý nghĩa của collection trong IANA registry

`collection` và `item` được định nghĩa trong RFC 6573, *The Item and Collection Link Relations*. Chúng là link relation chuẩn được đăng ký trong IANA Link Relation Type Registry.

| Relation | Ý nghĩa | Hướng liên kết thường gặp |
| --- | --- | --- |
| `collection` | Target IRI trỏ đến resource đại diện cho một collection. | Từ một resource đến collection liên quan, thường là collection chứa item đó. |
| `item` | Target IRI trỏ đến resource là thành viên của collection được biểu diễn bởi context IRI. | Từ collection đến từng item thành viên. |

Ví dụ một đơn hàng riêng lẻ có thể liên kết đến collection đơn hàng:

```http
GET /api/orders/o-42 HTTP/1.1
Host: shop.example

HTTP/1.1 200 OK
Content-Type: application/json
Link: </api/orders>; rel="collection"

{
  "id": "o-42",
  "status": "PAID"
}
```

Trong response trên, context là representation của `/api/orders/o-42`; target của relation `collection` là `/api/orders`, resource đại diện cho tập hợp đơn hàng. Relation chỉ khẳng định target là collection; việc collection đó có chứa context resource hay không cần được xác định bởi semantics của API.

Ở chiều ngược lại, collection có thể liên kết đến từng item:

```http
GET /api/orders HTTP/1.1
Host: shop.example

HTTP/1.1 200 OK
Content-Type: application/json
Link: </api/orders/o-42>; rel="item"
Link: </api/orders/o-43>; rel="item"

{
  "count": 2
}
```

Ở đây, context là collection `/api/orders`; mỗi target `item` là một resource thành viên. Một collection có thể có nhiều link cùng relation `item`.

## Phân biệt collection với self, up và các relation khác

Các relation này có ý nghĩa riêng, dù chúng có thể cùng xuất hiện trên một representation:

| Relation | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `self` | URI định danh chính representation hiện tại. | Order `o-42` tự liên kết đến `/api/orders/o-42`. |
| `collection` | URI của resource đại diện cho collection. | Order `o-42` liên kết đến `/api/orders`. |
| `item` | URI của một member trong collection. | Collection orders liên kết đến `/api/orders/o-42`. |
| `up` | URI của resource cấp trên trong cấu trúc phân cấp. | Item lồng trong order liên kết lên order cha. |
| `next` / `prev` | URI của trang kế tiếp hoặc trang trước trong điều hướng phân trang. | Trang 0 liên kết `next` đến trang 1. |

Không thay `collection` bằng `up` chỉ vì collection nằm ở cấp trên trong URL. `up` biểu diễn quan hệ phân cấp; `collection` xác định target là resource collection theo semantics của RFC 6573. Tương tự, `next` không phải link đến collection nói chung mà là link điều hướng đến trang kế tiếp.

Một resource có thể có cả `self` và `collection`:

```json
{
  "id": "o-42",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "collection": {
      "href": "https://shop.example/api/orders"
    }
  }
}
```

`self` giúp client nhận diện URI của order; `collection` cho client biết nơi có resource collection liên quan. Client có thể theo link này mà không phải tự suy ra `/api/orders` từ URI item.

## Relation collection trong HAL

Trong HAL, link relation được đặt dưới `_links`. Một order có thể công bố `collection` như sau:

```json
{
  "id": "o-42",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "collection": {
      "href": "https://shop.example/api/orders"
    }
  }
}
```

Collection có thể công bố các link `item`:

```json
{
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders"
    },
    "item": [
      {
        "href": "https://shop.example/api/orders/o-42"
      },
      {
        "href": "https://shop.example/api/orders/o-43"
      }
    ]
  }
}
```

HAL cho phép một relation có nhiều link; khi có nhiều target cùng relation, giá trị của relation được serialize thành mảng link. Tuy nhiên, không bắt buộc collection phải công bố mọi item bằng `_links.item` nếu các item đã được nhúng trong `_embedded` và có link riêng. Hãy chọn cách biểu diễn phù hợp với kích thước collection và nhu cầu điều hướng của client.

## Phân biệt IANA item link với embedded relation

Đây là điểm dễ nhầm khi dùng Spring HATEOAS:

- `IanaLinkRelations.ITEM` là link relation trong `_links`, có nghĩa target là một member của collection hiện tại.
- `@Relation(itemRelation = "order", collectionRelation = "orders")` đặt tên cho embedded item và collection trong `_embedded`.
- `_embedded.orders` là một mảng representation được nhúng; tên `orders` không tự động trở thành IANA relation `item`.

Ví dụ một collection HAL có thể có cả hai cấu trúc:

```json
{
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders"
    },
    "item": [
      { "href": "https://shop.example/api/orders/o-42" },
      { "href": "https://shop.example/api/orders/o-43" }
    ]
  },
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "_links": {
          "self": { "href": "https://shop.example/api/orders/o-42" }
        }
      },
      {
        "id": "o-43",
        "_links": {
          "self": { "href": "https://shop.example/api/orders/o-43" }
        }
      }
    ]
  }
}
```

Trong nhiều API, chỉ `_embedded.orders` cùng self link của từng item đã đủ để client duyệt collection. Các link `item` tường minh có thể hữu ích cho client chỉ muốn khám phá URI thành viên mà không cần đọc embedded payload. Không nên thêm cả hai một cách máy móc nếu chúng không đem lại lợi ích cho client.

## Dùng IanaLinkRelations trong Spring HATEOAS

Spring HATEOAS cung cấp `IanaLinkRelations` trong package `org.springframework.hateoas`. Dùng các hằng chuẩn giúp tránh lỗi chính tả và làm rõ ý nghĩa relation trong code:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link collectionLink = linkTo(methodOn(OrderController.class)
        .all()).withRel(IanaLinkRelations.COLLECTION);

Link itemLink = linkTo(methodOn(OrderController.class)
        .one(order.getId())).withRel(IanaLinkRelations.ITEM);
```

`methodOn(...)` mô tả mapping của controller để Spring HATEOAS tạo URI theo route đang khai báo. Nó không gọi endpoint thật. `withRel(...)` gắn relation IANA vào link; serializer HAL đưa link vào `_links`.

Không nên viết `withRel("orders")` rồi cho rằng đó là relation IANA `collection`. `orders` có thể là một relation mở rộng theo hợp đồng API hoặc là collection relation của embedded model, còn relation chuẩn IANA là token `collection`.

## Công bố collection và item links trong CollectionModel

`CollectionModel<T>` biểu diễn một collection resource trong Spring HATEOAS. Các item có thể là `RepresentationModel` riêng, mỗi item có self link; collection có self link và có thể thêm các link `item` tường minh.

Khai báo model cho một order:

```java
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderResource extends RepresentationModel<OrderResource> {

    private final UUID id;
    private final String status;

    public OrderResource(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

Assembler cho item thêm self link và link về collection:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.stereotype.Component;

@Component
class OrderResourceAssembler {

    OrderResource toModel(Order order) {
        OrderResource resource = new OrderResource(
                order.getId(), order.getStatus().name());

        resource.add(linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());
        resource.add(linkTo(methodOn(OrderController.class)
                .all()).withRel(IanaLinkRelations.COLLECTION));

        return resource;
    }
}
```

Controller tạo collection model:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService service;
    private final OrderResourceAssembler assembler;

    OrderController(OrderService service, OrderResourceAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/api/orders", produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<OrderResource> all() {
        List<OrderResource> resources = service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        CollectionModel<OrderResource> collection = CollectionModel.of(
                resources,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());

        for (OrderResource resource : resources) {
            collection.add(resource.getRequiredLink(IanaLinkRelations.SELF)
                    .withRel(IanaLinkRelations.ITEM));
        }

        return collection;
    }
}
```

Ví dụ trên chủ động thêm một link `item` cho mỗi item dựa trên self link của resource. Với collection lớn hoặc đã phân trang, việc lặp và công bố mọi item link có thể làm response nặng; thường chỉ cần `_embedded.orders` với self link trên từng embedded resource, hoặc dùng link phân trang. `Order`, `OrderService` và truy vấn `findAll()` là thành phần domain của ứng dụng.

Nếu chỉ cần `CollectionModel` với embedded item, không cần thêm `_links.item` cho mọi item. `@Relation` xác định khóa `_embedded.orders`; `IanaLinkRelations.ITEM` chỉ cần dùng khi muốn công bố quan hệ link chuẩn đó một cách tường minh.

## Collection trong API phân trang

Collection lớn thường được chia thành nhiều trang. Trong trường hợp đó, resource trang có thể có:

- `self`: URI của trang hiện tại.
- `first` và `last`: trang đầu và cuối nếu API cung cấp.
- `prev` và `next`: trang liền trước và kế tiếp khi tồn tại.
- `collection`: link đến resource collection tổng thể nếu API có một collection URI riêng.
- `_embedded.orders`: các item thuộc trang hiện tại.

Không dùng `item` để thay `next`. `item` dẫn đến một thành viên của collection; `next` dẫn đến một trang khác. Nếu client cần mở một order cụ thể, theo link `item` hoặc self link của embedded order. Nếu cần tiếp tục duyệt trang, theo `next`.

Với `PagedResourcesAssembler`, các link phân trang được tạo dựa trên `Page` và request hiện tại. Có thể bổ sung relation `collection` nếu hợp đồng của API định nghĩa một URI collection ổn định ngoài URI của trang. Không gán relation `collection` cho mọi link `self` của trang nếu điều đó làm mờ ý nghĩa của resource đích.

## Collection relation và tiến hóa API

Relation chuẩn có lợi thế là client có thể nhận biết semantics mà không cần học một tên mở rộng riêng. Nếu một resource công bố `collection`, client hiểu target đại diện cho collection. Nếu collection công bố `item`, client hiểu target là một member.

Khi thay đổi route hoặc cấu trúc backend, server có thể giữ nguyên relation nhưng đổi `href`:

```json
{
  "_links": {
    "collection": {
      "href": "https://shop.example/api/v2/orders"
    }
  }
}
```

Client tiếp tục theo relation `collection` mà không cần tự tạo đường dẫn. Nếu ý nghĩa target thay đổi, hãy chọn relation phù hợp khác hoặc một relation mở rộng có định nghĩa rõ; không tái sử dụng `collection` cho một resource không đại diện collection.

Với association domain đặc thù như `ordersForCustomer`, có thể dùng relation mở rộng nếu semantics khác với collection tổng quát. Relation mở rộng nên được tài liệu hóa, và với API công khai có thể dùng URI relation để tránh xung đột tên. Không dùng một token ngắn tùy ý rồi kỳ vọng mọi client đều hiểu ngữ nghĩa IANA.

## Kiểm thử collection và item relation

MockMvc có thể xác nhận item resource công bố link về collection và collection response có self link, embedded relation ổn định:

```java
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
class CollectionRelationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void itemPointsToItsCollection() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.collection.href")
                        .value(org.hamcrest.Matchers.endsWith("/api/orders")));
    }

    @Test
    void collectionEmbedsOrdersAndExposesItsSelfLink() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._embedded.orders").isArray())
                .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
    }
}
```

Nếu collection có công bố link `item` tường minh, bổ sung assertion cho `$._links.item`. Khi có nhiều item cùng relation, HAL thường serialize giá trị đó thành mảng link; test cần fixture có ít nhất hai item. Nếu API chỉ dùng `_embedded.orders`, không nên ép test phải có `_links.item`.

Các test nên bao gồm collection rỗng, item có link `collection`, và route đích thực sự trả resource collection. Không khóa test vào hostname tuyệt đối nếu môi trường có thể chạy sau reverse proxy; kiểm tra path hoặc theo link để xác minh điều hướng.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `collection` cho link đến một item | Client hiểu sai kiểu resource ở target. | Chỉ dùng khi target đại diện collection. |
| Dùng `item` cho link đến trang kế tiếp | Client nhầm trang với member của collection. | Dùng `next` cho trang kế tiếp. |
| Nhầm `collection` với `up` | Ngữ nghĩa quan hệ bị sai khi cấu trúc URL thay đổi. | Dùng `collection` cho collection resource; `up` cho parent hierarchy. |
| Coi `@Relation(collectionRelation = "orders")` là IANA `collection` | Nhầm khóa `_embedded` với link relation trong `_links`. | Phân biệt `orders` embedded relation và token IANA `collection`. |
| Nghĩ `CollectionModel` tự thêm `_links.item` | Mong đợi link item dù model chỉ chứa embedded resources. | Thêm `IanaLinkRelations.ITEM` tường minh nếu hợp đồng cần. |
| Công bố link item cho collection rất lớn | Response chứa quá nhiều link và tăng kích thước payload. | Dùng pagination và embedded item/self link hoặc chỉ công bố link cần thiết. |

## Nguyên tắc thiết kế

- Dùng `collection` khi target là resource đại diện cho một collection.
- Dùng `item` khi target là member của collection hiện tại.
- Phân biệt hai relation này với `self`, `up`, `next` và `prev`.
- Trong Spring HATEOAS, ưu tiên `IanaLinkRelations.COLLECTION` và `IanaLinkRelations.ITEM`.
- Dùng `CollectionModel` cho collection representation và `@Relation` để đặt tên `_embedded` ổn định.
- Không nhầm IANA item link trong `_links` với embedded relation trong `_embedded`.
- Chỉ công bố link item tường minh khi client có nhu cầu; cân nhắc payload khi collection lớn.
- Kiểm thử relation, href và khả năng theo link đến collection/member.

Relation `collection` giúp một item công bố resource collection mà nó thuộc về; relation `item` giúp collection chỉ ra các thành viên của nó. Khi dùng đúng semantics IANA và các hằng `IanaLinkRelations` trong Spring HATEOAS, client có thể khám phá mối quan hệ giữa collection và item qua hypermedia thay vì phụ thuộc vào tên route hoặc cấu trúc URL nội bộ.
