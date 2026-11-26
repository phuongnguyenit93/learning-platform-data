# Serialize embedded

Trong HAL, embedded resource là representation của một tài nguyên liên quan được đặt ngay bên trong response hiện tại, dưới khóa `_embedded`. Cách biểu diễn này giúp client đọc dữ liệu liên quan trong cùng một request, đồng thời vẫn có thể điều hướng tới tài nguyên gốc qua link trong `_links`.

Spring HATEOAS tích hợp Jackson để tuần tự hóa `EntityModel`, `CollectionModel` và các representation model thành HAL JSON. Với collection ở cấp cao nhất, `CollectionModel` được chuyển thành `_embedded` theo relation của kiểu phần tử. Với tài nguyên lồng nhau, `HalModelBuilder` cung cấp API chuyên biệt để tạo embedded document, preview gắn với link và collection embedded. Vì vậy, thông thường không cần tự dựng object `_embedded` hoặc viết Jackson serializer riêng.

## Embedded resource trong HAL là gì?

Giả sử một đơn hàng có khách hàng và nhiều dòng hàng. Response chỉ có link tới tài nguyên liên quan:

```json
{
  "id": "ORD-2048",
  "status": "PENDING",
  "_links": {
    "self": { "href": "/api/orders/ORD-2048" },
    "customer": { "href": "/api/customers/C-100" },
    "items": { "href": "/api/orders/ORD-2048/items" }
  }
}
```

Client phải gửi request riêng để tải khách hàng và dòng hàng. Nếu client thường xuyên cần một phần thông tin khách hàng cùng danh sách dòng hàng để hiển thị đơn hàng, server có thể nhúng các representation đó:

```json
{
  "id": "ORD-2048",
  "status": "PENDING",
  "_links": {
    "self": { "href": "/api/orders/ORD-2048" },
    "customer": { "href": "/api/customers/C-100" },
    "items": { "href": "/api/orders/ORD-2048/items" }
  },
  "_embedded": {
    "customer": {
      "id": "C-100",
      "displayName": "Nguyen An",
      "_links": {
        "self": { "href": "/api/customers/C-100" }
      }
    },
    "items": [
      {
        "id": "ITEM-1",
        "productName": "Keyboard",
        "quantity": 1
      },
      {
        "id": "ITEM-2",
        "productName": "Mouse",
        "quantity": 2
      }
    ]
  }
}
```

Trong ví dụ:

- `_links.customer` và `_links.items` cho biết nơi truy cập tài nguyên đầy đủ.
- `_embedded.customer` chứa preview thông tin khách hàng.
- `_embedded.items` chứa các dòng hàng liên quan ngay trong response.
- Mỗi embedded resource có thể tự chứa `_links` để client tiếp tục điều hướng.

Embedded resource là một phần của representation hiện tại. Nó không nhất thiết là bản sao đầy đủ của tài nguyên đích; có thể là DTO rút gọn, snapshot hoặc representation có link riêng.

## Jackson và Spring HATEOAS serialize embedded như thế nào?

Jackson thông thường biết cách serialize object và collection thành JSON, nhưng không tự hiểu quy ước HAL như `_links`, `_embedded` và relation. Spring HATEOAS cung cấp HAL Jackson module cùng các mixin/serializer để chuyển representation model thành cấu trúc HAL.

Khi hypermedia support được kích hoạt, Spring HATEOAS đăng ký các Jackson module cần thiết cho `EntityModel` và `CollectionModel`. Trong Spring Boot, cấu hình tự động thường đảm nhiệm việc này khi dependency Spring HATEOAS có mặt. Với cấu hình Spring MVC tự quản lý, có thể bật HAL bằng `@EnableHypermediaSupport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
public class HypermediaConfiguration {
}
```

Khi controller trả về representation model và client yêu cầu `application/hal+json`, converter hypermedia sử dụng HAL Jackson module để serialize. Không nên tự tạo `new ObjectMapper()` trong controller để chuyển model thành chuỗi JSON, vì mapper tự tạo có thể thiếu cấu hình hypermedia của ứng dụng.

## Đặt tên relation cho embedded resource

Tên khóa trong `_embedded` được xác định từ relation của kiểu resource hoặc relation được chỉ định rõ. Spring HATEOAS dùng `LinkRelationProvider`; có thể cấu hình tên bằng annotation `@Relation` trên kiểu representation:

```java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "orderItem", collectionRelation = "items")
public record OrderItemSummary(
        UUID id,
        String productName,
        int quantity
) {}
```

`collectionRelation = "items"` xác định relation dùng cho collection. `itemRelation = "orderItem"` xác định relation cho một phần tử đơn lẻ. Với kiểu representation không có `@Relation`, relation provider có thể suy ra tên từ tên lớp; tên suy ra có thể không khớp thuật ngữ nghiệp vụ mà API muốn công bố.

Nếu relation là một phần ổn định của hợp đồng client, hãy khai báo rõ thay vì dựa vào quy tắc suy tên. Relation cần được giữ nhất quán giữa các endpoint và giữa các phiên bản API.

## Serialize collection ở cấp cao nhất bằng CollectionModel

`CollectionModel<T>` là representation model dành cho một tập hợp. Khi serialize theo HAL, content của collection được đặt dưới `_embedded` với relation do `LinkRelationProvider` xác định.

Ví dụ model:

```java
import java.util.UUID;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

Order order = orderService.findRequired(orderId);

List<EntityModel<OrderItemSummary>> items = order.getItems().stream()
        .map(item -> EntityModel.of(
                new OrderItemSummary(
                        item.getId(),
                        item.getProductName(),
                        item.getQuantity()
                )
        ))
        .toList();

CollectionModel<EntityModel<OrderItemSummary>> model =
        CollectionModel.of(items);
```

Khi trả model từ controller với `Accept: application/hal+json`, HAL serializer đặt các item dưới relation collection `items`:

```json
{
  "_embedded": {
    "items": [
      {
        "id": "ITEM-1",
        "productName": "Keyboard",
        "quantity": 1
      }
    ]
  }
}
```

Nếu mỗi phần tử là `EntityModel`, nó có thể mang link riêng và các link đó cũng được serialize trong embedded item. Nếu chỉ cần DTO không có link, có thể dùng `CollectionModel<OrderItemSummary>`.

### Collection rỗng và thông tin kiểu

Collection rỗng tạo ra một vấn đề do Java type erasure: runtime không thể suy ra kiểu phần tử từ một collection không có phần tử. Nếu cần bảo đảm relation collection vẫn xuất hiện với mảng rỗng, cung cấp kiểu dự phòng:

```java
CollectionModel<OrderItemSummary> emptyItems =
        CollectionModel.<OrderItemSummary>empty()
                .withFallbackType(OrderItemSummary.class);
```

HAL serializer có thể dùng kiểu này để xác định relation và tạo:

```json
{
  "_embedded": {
    "items": []
  }
}
```

Nếu hợp đồng API coi collection rỗng là một collection đã biết và hợp lệ, nên giữ relation cùng mảng rỗng. Nếu không có `_embedded.items`, client có thể không phân biệt được collection rỗng với việc server không công bố relation đó.

## Nhúng tài nguyên lồng nhau bằng HalModelBuilder

Khi một representation cần có nhiều embedded resource hoặc preview gắn với link, `HalModelBuilder` là API HAL-idiomatic được Spring HATEOAS cung cấp. Builder cho phép xác định payload chính, embedded document, preview và link trong cùng một cấu trúc.

Ví dụ, đơn hàng có preview khách hàng và nhúng các dòng hàng:

```java
import java.util.List;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

var customer = new CustomerSummary(
        order.getCustomer().getId(),
        order.getCustomer().getDisplayName()
);

Link customerLink = linkTo(methodOn(CustomerController.class)
        .one(order.getCustomer().getId()))
        .withRel("customer");

List<OrderItemSummary> items = order.getItems().stream()
        .map(item -> new OrderItemSummary(
                item.getId(),
                item.getProductName(),
                item.getQuantity()
        ))
        .toList();

Link self = linkTo(methodOn(OrderController.class)
        .one(order.getId())).withSelfRel();

OrderSummary summary = new OrderSummary(
        order.getId(),
        order.getStatus().name(),
        order.getTotal()
);

var representation = HalModelBuilder.halModelOf(summary)
        .preview(customer)
        .forLink(customerLink)
        .embed(items, LinkRelation.of("items"))
        .link(self)
        .build();
```

Trong ví dụ:

- `halModelOf(...)` đặt `OrderSummary` làm payload chính của representation.
- `preview(customer)` khai báo dữ liệu preview cho tài nguyên khách hàng.
- `forLink(customerLink)` hoàn tất preview: Spring HATEOAS thêm link `customer` vào `_links` và dùng cùng relation làm khóa trong `_embedded`.
- `embed(items, LinkRelation.of("items"))` thêm collection dòng hàng vào `_embedded.items`.
- `link(self)` thêm link `self` ở cấp representation chính.
- `build()` tạo representation model để Spring serialize theo HAL.

`CustomerSummary`, `OrderSummary` và `OrderItemSummary` là DTO của ứng dụng. Trong ứng dụng thực tế, nên lấy dữ liệu cần nhúng qua service hoặc projection phù hợp, tránh để builder kích hoạt nhiều lazy-loading query trong lúc tạo response.

### Preview khác với embed độc lập

`preview(...).forLink(...)` biểu diễn một preview gắn với một link. Spring HATEOAS tạo cả `_links[rel]` và `_embedded[rel]` cho cùng relation. Đây là cách phù hợp khi muốn client có dữ liệu tóm tắt ngay lập tức nhưng vẫn cung cấp link tới tài nguyên đầy đủ.

`embed(...)` thêm embedded resource độc lập. Nó không tự tạo link tới tài nguyên đó. Nếu client cũng cần đường dẫn tới tài nguyên, hãy thêm link tương ứng bằng `link(...)` hoặc dùng `preview(...).forLink(...)` khi embedded là preview của link.

## Nhúng collection rỗng bằng HalModelBuilder

Khi gọi `embed(collection)` với collection rỗng, builder không thể suy ra relation từ phần tử nên không thêm entry vào `_embedded`. Nếu muốn công bố mảng rỗng, truyền kiểu phần tử hoặc relation tường minh:

```java
import java.util.List;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

Link self = Link.of("/api/orders/ORD-2048").withSelfRel();

var model = HalModelBuilder.emptyHalModel()
        .embed(List.of(), OrderItemSummary.class)
        .link(self)
        .build();
```

Hoặc truyền relation:

```java
var model = HalModelBuilder.emptyHalModel()
        .embed(List.of(), LinkRelation.of("items"))
        .link(self)
        .build();
```

Hai overload này cho phép serializer biết tên relation ngay cả khi không có phần tử để suy luận. Dùng kiểu phần tử khi muốn relation theo `LinkRelationProvider`; dùng `LinkRelation` khi hợp đồng yêu cầu tên relation được chỉ định trực tiếp.

## Chọn giữa link, preview và embedded

Ba cách biểu diễn giải quyết ba nhu cầu khác nhau:

| Cách | HAL output | Khi phù hợp |
|---|---|---|
| Link | Chỉ có `_links.customer.href` | Client chỉ cần biết nơi tải tài nguyên liên quan |
| Preview | Có `_links.customer` và `_embedded.customer` | Client thường cần summary ngay, đồng thời cần link tới tài nguyên đầy đủ |
| Embed độc lập | Có `_embedded.items`, không tự có link tương ứng | Dữ liệu liên quan cần đi cùng response và không cần điều hướng độc lập qua relation đó |

Không nên nhúng mọi quan hệ của domain object. Embedded payload lớn có thể làm response chậm, tăng bộ nhớ và khiến dữ liệu liên quan bị lặp ở nhiều response. Hãy nhúng phần dữ liệu client thực sự cần cho màn hình hoặc workflow cụ thể; dùng link cho phần dữ liệu có thể tải riêng, có phân quyền riêng hoặc thay đổi thường xuyên.

## Tránh vòng lặp và lồng quá sâu

Một đồ thị domain có thể có quan hệ hai chiều: `Order` tham chiếu `Customer`, còn `Customer` lại có danh sách `Orders`. Nếu nhúng toàn bộ hai chiều, response có thể lặp vô hạn hoặc phình to.

Hãy kiểm soát độ sâu representation bằng DTO tóm tắt:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record CustomerSummary(UUID id, String displayName) {}

public record OrderSummary(UUID id, String status, BigDecimal total) {}
```

Trong response đơn hàng, nhúng `CustomerSummary` thay vì nhúng một representation khách hàng có toàn bộ danh sách đơn hàng. Nếu client cần danh sách đơn hàng của khách hàng, cung cấp link `orders` để tải collection riêng.

Không serialize trực tiếp entity JPA có quan hệ hai chiều. Việc đó có thể gây vòng lặp Jackson, kích hoạt lazy loading ngoài ý muốn hoặc tạo N+1 query. Tạo DTO/projection cho embedded data và kiểm soát truy vấn ở tầng service.

## Bảo mật và tính nhất quán của embedded data

Embedded resource được trả cùng response của tài nguyên cha, vì vậy quyền truy cập cần được đánh giá theo người dùng và ngữ cảnh request hiện tại. Không nhúng trường nhạy cảm chỉ vì object nguồn có trường đó. DTO preview nên chỉ chứa thông tin client được phép xem.

Nếu tài nguyên liên quan có quyền truy cập khác với tài nguyên cha, cần cân nhắc chỉ cung cấp link hoặc nhúng một summary đã lọc. Link không thay thế authorization ở endpoint đích; client có thể gọi URI trực tiếp và quyền có thể thay đổi sau thời điểm response được tạo.

Embedded data cũng là snapshot tại thời điểm response. Nếu dữ liệu liên quan thay đổi độc lập hoặc cần độ mới cao, client có thể theo link tới tài nguyên gốc để tải phiên bản mới nhất.

## Kiểm thử serialization embedded bằng MockMvc

Kiểm thử tích hợp nên xác nhận cả relation, cấu trúc `_embedded` và link đi kèm. Ví dụ:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._embedded.customer.id").value(customerId.toString()))
    .andExpect(jsonPath("$._embedded.items").isArray())
    .andExpect(jsonPath("$._links.customer.href").exists())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Kiểm thử collection rỗng để bảo đảm relation vẫn xuất hiện nếu hợp đồng yêu cầu mảng rỗng:

```java
mockMvc.perform(get("/api/orders/{id}/items", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.items").isArray())
    .andExpect(jsonPath("$._embedded.items.length()").value(0));
```

Nếu dùng `HalModelBuilder.embed(emptyCollection, Item.class)` hoặc `CollectionModel.withFallbackType(Item.class)`, test này bảo vệ việc giữ relation khi collection không có phần tử.

Ngoài kiểm tra JSONPath, nên kiểm tra trường hợp relation tùy chọn không xuất hiện, preview và link dùng cùng relation, cũng như dữ liệu nhúng không chứa trường nội bộ. Nếu embedded item có link riêng, kiểm tra các link đó ở đúng cấp trong `_embedded`.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự dựng `_embedded` bằng map JSON | Dễ lệch relation và cấu trúc HAL | Dùng `HalModelBuilder`, `CollectionModel` và HAL Jackson support |
| Nghĩ `EntityModel` tự nhúng mọi association | Association có thể chỉ được serialize như content hoặc không theo relation mong muốn | Dùng `HalModelBuilder` để định nghĩa embed rõ ràng |
| Không khai báo relation ổn định | Tên `_embedded` phụ thuộc tên lớp hoặc provider | Dùng `@Relation` hoặc `LinkRelation` tường minh |
| Dùng `embed(emptyCollection)` không có kiểu | Không suy ra được relation, entry có thể biến mất | Truyền `Class` hoặc `LinkRelation` |
| Dùng embed thay cho link | Client không có đường dẫn tới tài nguyên gốc | Kết hợp link hoặc preview khi cần điều hướng |
| Nhúng toàn bộ đồ thị entity | Vòng lặp, payload lớn và N+1 query | Dùng DTO summary, giới hạn độ sâu và truy vấn theo lô |
| Dùng ObjectMapper tự tạo | Thiếu HAL Jackson module | Trả representation model qua converter đã cấu hình |
| Chỉ kiểm tra content cha | Không phát hiện lỗi relation hoặc nested link | Kiểm tra `_embedded` và `_links` bằng MockMvc |

## Quy trình serialize embedded

1. Xác định dữ liệu liên quan nào client cần ngay trong response.
2. Tạo DTO/representation summary cho embedded resource, tránh serialize trực tiếp entity persistence.
3. Chọn relation ổn định bằng `@Relation`, `LinkRelationProvider` hoặc `LinkRelation` tường minh.
4. Dùng `CollectionModel` cho collection ở cấp cao nhất.
5. Dùng `HalModelBuilder.preview(...).forLink(...)` khi embedded data là preview của một link.
6. Dùng `HalModelBuilder.embed(...)` cho embedded document độc lập.
7. Cung cấp kiểu hoặc relation tường minh cho collection rỗng nếu cần giữ mảng rỗng.
8. Bật HAL Jackson support và trả representation model qua Spring MVC converter.
9. Kiểm thử relation, cấu trúc `_embedded`, link tương ứng, collection rỗng và dữ liệu được phép công bố.

## Kết luận

Serialize embedded trong Spring HATEOAS là quá trình chuyển các representation liên quan thành `_embedded` theo relation trong HAL JSON. `CollectionModel` phù hợp cho collection ở cấp cao nhất; `@Relation` và `LinkRelationProvider` kiểm soát tên relation; `HalModelBuilder` tạo embedded document, preview gắn với link và collection lồng nhau. HAL Jackson module đảm nhiệm serialization khi hypermedia support được cấu hình. Khi chọn đúng dữ liệu cần nhúng, giữ relation ổn định, xử lý collection rỗng và kiểm soát vòng lặp, quyền truy cập cùng truy vấn dữ liệu, response HAL sẽ hữu ích cho client mà vẫn dễ bảo trì.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – HAL representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal): `HalModelBuilder`, preview, embedded documents và collection rỗng.
- [HalModelBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalModelBuilder.html): các phương thức `preview`, `forLink`, `embed`, `link` và `build`.
- [Relation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html): cấu hình `itemRelation` và `collectionRelation`.
- [EmbeddedWrappers API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/EmbeddedWrappers.html): wrapper cho embedded values và empty collections.
