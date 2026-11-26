# Relation của embedded item

Trong HAL, tài nguyên liên quan có thể được nhúng ngay trong representation hiện tại dưới thuộc tính `_embedded`. Mỗi embedded resource được đặt dưới một khóa relation để client biết nội dung đó đại diện cho quan hệ nào. Với một tài nguyên đơn lẻ, relation thường dùng tên số ít như `customer`; với một tập hợp, relation thường dùng tên collection như `orderItems`.

Spring HATEOAS cho phép định nghĩa tên relation này bằng `@Relation` hoặc một `LinkRelationProvider`. Khi cần tạo HAL document có nhiều embedded resource, `HalModelBuilder` cung cấp API `embed(...)` và `preview(...).forLink(...)`. Các API này giúp relation trong `_embedded` có ý nghĩa ổn định và có thể gắn một embedded preview với link điều hướng tương ứng.

## HAL dùng relation để đặt tên embedded resource

Một HAL representation có hai vùng hypermedia thường gặp:

- `_links` chứa URI để client điều hướng đến tài nguyên liên quan.
- `_embedded` chứa representation của tài nguyên liên quan được nhúng trong response hiện tại.

Ví dụ, trang chi tiết đơn hàng có thể nhúng thông tin tóm tắt khách hàng và các dòng hàng:

```json
{
  "id": "o-42",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "customer": {
      "href": "https://shop.example/api/customers/c-17"
    }
  },
  "_embedded": {
    "customer": {
      "id": "c-17",
      "displayName": "Nguyen An"
    },
    "orderItems": [
      {
        "id": "i-1",
        "productCode": "KB-100",
        "quantity": 2
      },
      {
        "id": "i-2",
        "productCode": "MS-200",
        "quantity": 1
      }
    ]
  }
}
```

Trong ví dụ:

- `customer` là relation của một embedded customer.
- `orderItems` là relation của collection dòng hàng.
- `_links.customer.href` là URI để lấy tài nguyên khách hàng đầy đủ.
- `_embedded.customer` là bản tóm tắt khách hàng đã được nhúng vào response đơn hàng.

Tên relation không phải tên class Java, tên bảng hoặc tên thuộc tính database. Đây là một phần hợp đồng hypermedia mà client dùng để tìm embedded content. Vì vậy, hãy chọn tên theo ý nghĩa nghiệp vụ và giữ ổn định khi cấu trúc nội bộ thay đổi.

## Phân biệt embedded relation và link relation

Một relation có thể xuất hiện trong cả `_links` và `_embedded`, nhưng hai vùng có vai trò khác nhau:

| Vị trí | Nội dung | Ví dụ |
| --- | --- | --- |
| `_links.customer` | Link đến tài nguyên khách hàng. | `href: /api/customers/c-17` |
| `_embedded.customer` | Representation khách hàng được nhúng. | `{ "id": "c-17", "displayName": "..." }` |
| `_embedded.orderItems` | Mảng representation các dòng hàng. | `[{...}, {...}]` |

Link relation trả lời câu hỏi “có thể đi đến đâu và quan hệ đó là gì?”. Embedded relation trả lời câu hỏi “representation nào đã được đưa vào response và được đặt dưới quan hệ nào?”. Một embedded item không nhất thiết phải có link riêng; nếu client cần tải bản đầy đủ hoặc làm mới dữ liệu, hãy cung cấp link tương ứng.

Trong HAL, một embedded item đơn lẻ thường dùng item relation; một collection dùng collection relation. Đây là lý do Spring HATEOAS phân biệt `itemRelation` và `collectionRelation` trong `@Relation`.

## Khai báo relation bằng `@Relation`

`@Relation` thuộc package `org.springframework.hateoas.server.core`. Annotation này cho `LinkRelationProvider` biết tên relation của resource khi được biểu diễn như một item hoặc một collection.

```java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "customer", collectionRelation = "customers")
public record CustomerSummary(
        UUID id,
        String displayName
) {
}

@Relation(itemRelation = "orderItem", collectionRelation = "orderItems")
public record OrderItemSummary(
        UUID id,
        String productCode,
        int quantity
) {
}
```

Với hai kiểu trên, relation item của `CustomerSummary` là `customer`, collection relation là `customers`; relation item của `OrderItemSummary` là `orderItem`, collection relation là `orderItems`. Khi một `CustomerSummary` được nhúng riêng lẻ, relation item có thể được dùng. Khi danh sách `OrderItemSummary` được nhúng, relation collection được dùng làm khóa trong `_embedded`.

`@Relation` chỉ định tên relation. Nó không tự tải dữ liệu liên quan, không tự thêm embedded item và không tự tạo link. Ứng dụng vẫn phải chọn dữ liệu cần nhúng và tạo representation phù hợp.

## Cách Spring HATEOAS tìm relation

Spring HATEOAS dùng `LinkRelationProvider` để xác định relation cho một kiểu resource. Quy tắc tổng quát là:

1. Nếu kiểu có `@Relation`, sử dụng tên được khai báo trong annotation.
2. Nếu không có annotation, provider áp dụng quy tắc mặc định dựa trên tên kiểu Java.
3. Nếu thư viện pluralization như Evo Inflector có trên classpath, provider tương ứng có thể suy ra tên collection theo quy tắc số nhiều.

Tên suy ra từ class có thể không khớp ngôn ngữ hoặc quy ước API. Ví dụ, tên class `PersonSummary` không nhất thiết phải tạo ra relation mà client mong đợi. Với API công khai hoặc được nhiều client sử dụng, khai báo `@Relation` rõ ràng giúp tránh việc đổi tên class làm đổi relation.

Có thể dùng `LinkRelationProvider` để kiểm tra tên item và collection mà ứng dụng đang cấu hình:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;

@SpringBootTest
class EmbeddedRelationTest {

    @Autowired
    LinkRelationProvider relationProvider;

    @Test
    void resolvesConfiguredItemAndCollectionRelations() {
        assertThat(relationProvider.getItemResourceRelFor(CustomerSummary.class))
                .isEqualTo(LinkRelation.of("customer"));
        assertThat(relationProvider.getCollectionResourceRelFor(CustomerSummary.class))
                .isEqualTo(LinkRelation.of("customers"));

        assertThat(relationProvider.getItemResourceRelFor(OrderItemSummary.class))
                .isEqualTo(LinkRelation.of("orderItem"));
        assertThat(relationProvider.getCollectionResourceRelFor(OrderItemSummary.class))
                .isEqualTo(LinkRelation.of("orderItems"));
    }
}
```

Kiểm thử này xác nhận provider thực tế trả về relation mong đợi. Nếu ứng dụng đăng ký provider tùy chỉnh, test sẽ giúp phát hiện cấu hình làm thay đổi tên relation trước khi client bị ảnh hưởng.

## Dùng HalModelBuilder để nhúng item và link preview

`HalModelBuilder` thuộc package `org.springframework.hateoas.mediatype.hal`. Đây là builder dành riêng cho HAL, hữu ích khi một representation có payload chính, nhiều embedded resource và link ở cấp ngoài cùng.

Giả sử service đã tải đơn hàng, thông tin tóm tắt khách hàng và danh sách dòng hàng. Ta tạo link `customer`, rồi gắn preview khách hàng với link đó:

DTO đơn hàng dùng làm payload chính có thể được định nghĩa như sau:

```java
import java.util.UUID;

public record OrderDto(UUID id, String status) {
}
```

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

class OrderRepresentationAssembler {

    RepresentationModel<?> toModel(Order order) {
        OrderDto orderDto = new OrderDto(
                order.getId(), order.getStatus().name());

        CustomerSummary customer = new CustomerSummary(
                order.getCustomer().getId(),
                order.getCustomer().getDisplayName());

        List<OrderItemSummary> items = order.getItems().stream()
                .map(item -> new OrderItemSummary(
                        item.getId(), item.getProductCode(), item.getQuantity()))
                .toList();

        Link self = linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel();

        Link customerLink = linkTo(methodOn(CustomerController.class)
                .one(customer.id())).withRel("customer");

        return HalModelBuilder.halModelOf(orderDto)
                .preview(customer)
                .forLink(customerLink)
                .embed(items)
                .link(self)
                .build();
    }
}
```

Trong ví dụ:

- `halModelOf(orderDto)` đặt DTO đơn hàng làm payload chính.
- `preview(customer).forLink(customerLink)` thêm link `customer` vào `_links` và đặt preview khách hàng dưới `_embedded.customer`.
- `embed(items)` nhúng collection dòng hàng. Relation `orderItems` được xác định từ `@Relation` của `OrderItemSummary` hoặc provider đang cấu hình.
- `link(self)` thêm self link cho representation đơn hàng ở cấp ngoài cùng.

`preview(...).forLink(...)` đặc biệt hữu ích khi muốn client vừa xem dữ liệu tóm tắt, vừa có URI để mở representation đầy đủ. Relation của preview lấy từ link được truyền vào `forLink`, vì vậy hãy đặt relation của link đúng với embedded resource. `embed(...)` có thể thêm embedded resource khác không cần preview link riêng.

Trong ví dụ này, relation `customer` của preview được lấy từ `customerLink.withRel("customer")`. Nếu gọi `embed(customer)` trực tiếp ở nơi khác, relation item được suy ra từ `@Relation(itemRelation = "customer", ...)` trên `CustomerSummary`.

`HalModelBuilder` tạo một `RepresentationModel` có các embedded entries. Khi có embedded content, builder ưu tiên media type HAL và HAL-FORMS. Nếu API cần nhiều định dạng hypermedia khác nhau, hãy cân nhắc model/assembler trung lập định dạng và để message converter phù hợp đảm nhiệm việc serialize.

## Nhúng một item trực tiếp

Nếu chỉ cần nhúng một item và không cần preview gắn với link, dùng `embed(item)`:

```java
RepresentationModel<?> model = HalModelBuilder.halModelOf(orderDto)
        .embed(customerSummary)
        .link(orderSelfLink)
        .build();
```

Relation của embedded customer được suy ra từ `LinkRelationProvider`, thường lấy từ `@Relation(itemRelation = "customer", ...)`. Có thể chỉ định relation tường minh nếu muốn ghi đè tên được suy ra:

```java
import org.springframework.hateoas.LinkRelation;

RepresentationModel<?> model = HalModelBuilder.halModelOf(orderDto)
        .embed(customerSummary, LinkRelation.of("customer"))
        .link(orderSelfLink)
        .build();
```

Chỉ định relation trực tiếp hữu ích khi một kiểu DTO được nhúng trong nhiều ngữ cảnh với tên khác nhau. Tuy nhiên, nếu cùng kiểu luôn đại diện cùng một loại resource, `@Relation` thường dễ duy trì hơn.

## Nhúng collection và xử lý collection rỗng

Với collection, `embed(collection)` dùng relation collection được suy ra từ kiểu phần tử. Ví dụ, `List<OrderItemSummary>` được đặt dưới `_embedded.orderItems` theo annotation của `OrderItemSummary`.

```java
RepresentationModel<?> model = HalModelBuilder.halModelOf(orderDto)
        .embed(orderItems)
        .link(orderSelfLink)
        .build();
```

Một trường hợp cần chú ý là collection rỗng. Nếu chỉ gọi `embed(emptyList)`, builder không có phần tử để suy ra kiểu và relation; do đó có thể không tạo khóa trong `_embedded`. Nếu hợp đồng yêu cầu luôn thể hiện collection dù không có phần tử, hãy truyền kiểu phần tử hoặc relation rõ ràng:

```java
import java.util.List;

RepresentationModel<?> model = HalModelBuilder.halModelOf(orderDto)
        .embed(List.of(), OrderItemSummary.class)
        .link(orderSelfLink)
        .build();
```

Khi collection rỗng, cách này vẫn cho phép tạo:

```json
{
  "_embedded": {
    "orderItems": []
  }
}
```

Hoặc có thể chỉ định relation trực tiếp:

```java
.embed(List.of(), LinkRelation.of("orderItems"))
```

Hãy chọn nhất quán giữa hai cách. Việc giữ `_embedded.orderItems: []` có thể hữu ích nếu client cần phân biệt collection rỗng với quan hệ chưa được cung cấp trong response.

## Preview collection gắn với link

`HalModelBuilder` cũng hỗ trợ preview cho một collection. Điều này hữu ích khi muốn nhúng một số dữ liệu tóm tắt nhưng vẫn cung cấp link đến collection đầy đủ:

```java
Link itemsLink = linkTo(methodOn(OrderItemController.class)
        .allForOrder(order.getId())).withRel("orderItems");

RepresentationModel<?> model = HalModelBuilder.halModelOf(orderDto)
        .preview(itemSummaries)
        .forLink(itemsLink)
        .link(orderSelfLink)
        .build();
```

Relation `orderItems` từ link được dùng cho cả `_links.orderItems` và `_embedded.orderItems`. Với preview collection rỗng, có thể dùng overload `preview(collection, OrderItemSummary.class)` để builder biết kiểu cần dùng khi suy ra relation:

```java
HalModelBuilder.halModelOf(orderDto)
        .preview(itemSummaries, OrderItemSummary.class)
        .forLink(itemsLink)
        .link(orderSelfLink)
        .build();
```

Preview collection giúp client hiển thị một phần dữ liệu ngay trong trang cha. Link cho phép client tải collection đầy đủ, phân trang hoặc truy cập các thao tác dành riêng cho collection.

## Chọn embed hay chỉ cung cấp link

Không phải mọi quan hệ domain đều cần nhúng. Việc embed giúp giảm số request nhưng làm response lớn hơn và có thể khiến dữ liệu trong embedded preview nhanh lỗi thời.

| Tình huống | Cách biểu diễn phù hợp |
| --- | --- |
| Client gần như luôn cần tên khách hàng khi xem đơn hàng | Nhúng `customer` dạng summary và cung cấp link `customer` đến bản đầy đủ. |
| Collection dòng hàng nhỏ, được hiển thị cùng đơn hàng | Nhúng `orderItems` dưới dạng collection. |
| Collection có hàng nghìn phần tử hoặc cần phân trang độc lập | Chỉ cung cấp link `orderItems` đến endpoint collection. |
| Dữ liệu liên quan nhạy cảm hoặc phụ thuộc quyền | Chỉ embed các trường được phép; kiểm tra quyền trước khi thêm link và payload. |
| Client cần dữ liệu mới nhất hoặc thao tác thường xuyên | Cung cấp link để client truy cập representation hiện tại. |

Không nhúng trực tiếp toàn bộ JPA entity. Hãy tạo DTO hoặc summary model với các trường cần công bố. Cách này tránh vô tình lộ trường nội bộ, lazy loading và vòng lặp serialize qua quan hệ hai chiều.

## Relation và khả năng tiến hóa hợp đồng

Tên relation trong `_embedded` là một phần hợp đồng mà client có thể phụ thuộc. Khi đổi `customer` thành `buyer`, client đang tìm `_embedded.customer` sẽ không còn tìm thấy dữ liệu. Khi đổi `orderItems` thành `items`, client phải cập nhật cách đọc collection.

Vì vậy:

- Chọn tên relation theo ý nghĩa nghiệp vụ mà client hiểu.
- Dùng `@Relation` để cố định item và collection relation, tránh phụ thuộc tên class.
- Dùng relation URI hoặc CURIE khi cần định nghĩa relation mở rộng có namespace rõ ràng.
- Giữ relation ổn định khi đổi package, tên class hoặc cấu trúc database.
- Kiểm thử cả `_embedded` và `_links`, không chỉ kiểm tra payload dữ liệu.

Nếu API có nhiều loại embedded item, tránh dùng cùng một relation cho các kiểu dữ liệu khác nghĩa. Một relation nên có ngữ nghĩa nhất quán ở mọi response.

## Kiểm thử embedded relation trong HAL

MockMvc có thể xác minh relation của embedded customer, collection dòng hàng và link điều hướng tương ứng:

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
class OrderEmbeddedResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderUsesConfiguredEmbeddedRelations() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._embedded.customer.id").value("c-17"))
                .andExpect(jsonPath("$._embedded.orderItems").isArray())
                .andExpect(jsonPath("$._links.customer.href").exists())
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Fixture cần chuẩn bị đơn hàng `o-42`, khách hàng `c-17` và ít nhất một dòng hàng. Nếu collection rỗng, bổ sung test xác nhận API có chủ đích trả `_embedded.orderItems: []` hoặc bỏ relation khỏi `_embedded`. Cả hai cách đều có thể có ý nghĩa khác nhau với client; hãy chọn theo hợp đồng đã công bố.

Các lỗi thường gặp:

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm relation embedded với tên thuộc tính DTO | Client không tìm thấy item dưới `_embedded`. | Khai báo `@Relation` hoặc relation tường minh trong `HalModelBuilder`. |
| Nghĩ `@Relation` tự nhúng dữ liệu | Response chỉ có link hoặc payload thường, không có `_embedded`. | Dùng `HalModelBuilder.embed` hoặc `preview(...).forLink(...)` để thêm embedded content. |
| Nhầm `itemRelation` với `collectionRelation` | Khóa `_embedded` không nhất quán giữa item và collection. | Dùng item relation cho một resource, collection relation cho tập hợp. |
| Preview và link dùng relation khác nhau | Client khó liên hệ embedded preview với link đầy đủ. | Dùng cùng relation trong `forLink` và kiểm thử cả hai vùng. |
| Collection rỗng làm mất khóa relation | Client không phân biệt collection rỗng với relation không được cung cấp. | Dùng `embed(collection, ItemType.class)` hoặc relation tường minh. |
| Embed toàn bộ entity | Lộ dữ liệu, response nặng hoặc phát sinh truy vấn N+1. | Nhúng DTO tóm tắt và giới hạn kích thước. |

## Nguyên tắc thiết kế

- Dùng relation số ít cho embedded item và collection relation cho danh sách.
- Khai báo `@Relation(itemRelation = "...", collectionRelation = "...")` trên kiểu resource cần embed.
- Dùng `HalModelBuilder.preview(...).forLink(...)` khi embedded preview đại diện cho tài nguyên có link đầy đủ.
- Dùng `embed(...)` cho embedded resource bổ sung; truyền type hoặc relation rõ ràng nếu collection có thể rỗng.
- Phân biệt khóa trong `_embedded` với link relation trong `_links`.
- Chỉ nhúng DTO/summary cần thiết; cung cấp link cho dữ liệu lớn hoặc cần làm mới.
- Kiểm thử relation thực tế trong HAL để bảo vệ hợp đồng client.

Relation của embedded item cho client biết loại tài nguyên nào đang được nhúng và cách tìm nó trong representation. Khi relation được định nghĩa ổn định, `HalModelBuilder` và `@Relation` giúp response vừa cung cấp dữ liệu cần thiết ngay lập tức, vừa giữ các link để client tiếp tục điều hướng đến tài nguyên đầy đủ.
