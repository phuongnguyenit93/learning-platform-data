# Embedded và top-level link

Một endpoint `/api/orders` có thể trả về danh sách đơn hàng. Client thường cần hai loại thông tin: dữ liệu của từng đơn hàng để hiển thị danh sách và các liên kết để tiếp tục điều hướng. Với HAL, Spring HATEOAS biểu diễn hai loại thông tin này ở hai vị trí khác nhau: resource được nhúng nằm trong `_embedded`, còn các liên kết điều hướng của resource hiện tại nằm trong `_links` ở cấp cao nhất.

Hai cấp này có vai trò riêng. Top-level link `self` trỏ đến collection đang được mô tả; top-level link `search` hoặc `next` giúp client khám phá chức năng hoặc trang khác. Mỗi resource nhúng có thể có `_links` riêng, chẳng hạn link `self` trỏ đến một đơn hàng cụ thể hoặc link `customer` dẫn đến khách hàng liên quan.

## Embedded resource và top-level link là gì?

Trong HAL, một representation có thể chứa:

- **`_links`:** các liên kết mô tả quan hệ giữa resource hiện tại và những resource khác. Ở cấp gốc, đây là các link của collection hoặc resource hiện tại.
- **`_embedded`:** các representation của resource khác được đưa trực tiếp vào response theo một relation. Mỗi embedded resource có thể chứa dữ liệu và link riêng.

Ví dụ response của collection đơn hàng:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    },
    "search": {
      "href": "https://api.example.com/api/orders/search"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/ord-1042"
          },
          "customer": {
            "href": "https://api.example.com/api/customers/cus-73"
          }
        }
      }
    ]
  }
}
```

Trong response này:

- `._links.self` là top-level self link của collection `/api/orders`.
- `._links.search` là top-level link đến chức năng tìm kiếm.
- `._embedded.orders` chứa các representation đơn hàng được nhúng.
- `._embedded.orders[0]._links.self` trỏ đến item resource `ord-1042`.
- `._embedded.orders[0]._links.customer` trỏ đến resource khách hàng liên quan.

Một embedded resource không phải chỉ là một object JSON lồng tùy ý. Nó đại diện cho một resource liên quan và có thể mang dữ liệu cùng hypermedia riêng. Nếu chỉ cần một thuộc tính mô tả như `status` hoặc `total`, hãy để nó là field của representation đơn hàng, không cần tạo relation `_embedded` mới.

## Phân biệt hai cấp link

Top-level link mô tả collection hiện tại hoặc các quan hệ điều hướng từ collection. Link bên trong embedded item mô tả item đó và các resource liên quan của nó.

| Vị trí | Ví dụ relation | Đích thường gặp | Ý nghĩa |
| --- | --- | --- | --- |
| Top-level `_links` | `self` | `/api/orders` | Chính collection đang được trả về. |
| Top-level `_links` | `search` | `/api/orders/search` | Điểm tìm kiếm đơn hàng. |
| Top-level `_links` | `next` | `/api/orders?page=1` | Trang tiếp theo của collection. |
| Embedded item `_links` | `self` | `/api/orders/ord-1042` | Chính đơn hàng đang nhúng. |
| Embedded item `_links` | `customer` | `/api/customers/cus-73` | Khách hàng liên quan đến đơn hàng. |
| Embedded item `_links` | `cancel` | `/api/orders/ord-1042/cancellation` | Hành động có thể thực hiện trên đơn hàng nếu điều kiện cho phép. |

Không đặt link `self` của từng đơn hàng ở top-level collection. Nếu đưa tất cả item link lên cấp gốc, client khó biết link nào thuộc item nào. Ngược lại, không đặt link `next` của collection bên trong một item vì phân trang là đặc tính của collection.

## Tạo embedded resource bằng CollectionModel và EntityModel

Spring HATEOAS cung cấp `CollectionModel<T>` để biểu diễn collection và `EntityModel<T>` để bọc một item cùng các link riêng. Khi collection chứa `EntityModel`, mỗi phần tử được serialize thành embedded resource có thể mang `_links` riêng.

Giả sử có DTO đơn hàng:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(
    UUID id,
    String status,
    BigDecimal total
) {
}
```

`@Relation` định nghĩa tên relation dùng khi nhúng item và collection. `collectionRelation = "orders"` giúp collection được đặt dưới `_embedded.orders`. Các relation nên ổn định vì client có thể dựa vào chúng để tìm embedded resource.

Assembler tạo representation cho từng item:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
            order.getId(),
            order.getStatus().name(),
            order.getTotal());

        return EntityModel.of(view,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel(),
            linkTo(methodOn(CustomerController.class).one(order.getCustomerId()))
                .withRel("customer"));
    }
}
```

Assembler chuyển domain object thành DTO và thêm link ở cấp item. Ví dụ giả định `Order` có các getter tương ứng, `OrderController.one(UUID)` trả về chi tiết đơn hàng và `CustomerController.one(UUID)` trả về khách hàng. Nếu khách hàng không tồn tại hoặc không được phép công bố, hãy xử lý điều kiện đó trước khi thêm link.

Controller tạo collection và bổ sung top-level link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orders, OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        CollectionModel<EntityModel<OrderView>> collection =
            assembler.toCollectionModel(orders.findAll());

        collection.add(
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
        collection.add(
            linkTo(methodOn(OrderController.class).search(null))
                .withRel("search"));

        return collection;
    }
}
```

Ví dụ giả định controller có phương thức `search(String status)` được ánh xạ đến endpoint tìm kiếm và `OrderService.findAll()` trả về `Iterable<Order>`. `toCollectionModel(...)` dùng assembler để tạo link riêng cho từng item. Hai lần `collection.add(...)` bổ sung link ở cấp collection.

Khi serialize thành HAL, kết quả có cấu trúc tương tự ví dụ đầu bài: `_embedded.orders` chứa các item và `_links` ở gốc chứa `self`, `search`. Các item có `_links.self` và `_links.customer` riêng.

## Dùng CollectionModel với DTO không có link riêng

Không phải collection nào cũng cần link cho từng item. Nếu client chỉ cần đọc danh sách dữ liệu nhỏ và không cần mở từng resource qua hypermedia, có thể trả `CollectionModel<OrderView>`:

```java
CollectionModel<OrderView> collection = CollectionModel.of(
    orderService.findRecentViews(),
    linkTo(methodOn(OrderController.class).recent()).withSelfRel());
```

Trong trường hợp này, collection vẫn có top-level `_links.self`, còn các phần tử nhúng là dữ liệu DTO thông thường. Không có `_links` riêng bên trong từng item vì kiểu phần tử không phải `EntityModel` hoặc custom `RepresentationModel`.

Nếu client cần điều hướng đến từng đơn hàng, dùng `CollectionModel<EntityModel<OrderView>>` hoặc một kiểu item model tùy chỉnh. Quyết định này nên xuất phát từ hành vi client cần thực hiện, không chỉ từ việc muốn response có thêm nhiều link.

## Top-level link có thể mô tả những gì?

Top-level links thường giúp client khám phá hoặc điều hướng collection:

- `self`: URI của collection hiện tại, giữ filter, sort hoặc page đang được áp dụng.
- `search`: endpoint tìm kiếm hoặc lọc collection.
- `next`, `prev`, `first`, `last`: điều hướng giữa các trang nếu API phân trang.
- `profile`: tài liệu mô tả cấu trúc hoặc ngữ nghĩa representation.
- `create`: quan hệ mở rộng do API định nghĩa nếu collection cho phép tạo item.

Chỉ thêm link khi hành động hoặc resource đích thực sự tồn tại và người gọi có thể sử dụng. Nếu collection phụ thuộc trạng thái người dùng, quyền truy cập hoặc filter, các link cần phản ánh đúng ngữ cảnh request.

Ví dụ collection có filter:

```java
@GetMapping
CollectionModel<EntityModel<OrderView>> all(
        @RequestParam(required = false) String status) {

    var result = orders.findAll(status);
    var collection = assembler.toCollectionModel(result);

    collection.add(linkTo(methodOn(OrderController.class).all(status))
        .withSelfRel());

    return collection;
}
```

Self link phải giữ giá trị `status` hiện tại. Nếu bỏ query parameter, client theo self link sẽ nhận một collection khác với representation vừa nhận.

## Embedded resource và link-only resource

HAL cho phép server chọn nhúng representation hoặc chỉ cung cấp link đến resource liên quan. Hai cách có tác động khác nhau:

| Tiêu chí | Embedded resource | Link-only resource |
| --- | --- | --- |
| Dữ liệu trong response | Có dữ liệu resource liên quan ngay trong `_embedded`. | Chỉ có link trong `_links`; client cần theo link để lấy representation. |
| Số lần gọi | Có thể giảm request tiếp theo. | Có thể cần thêm request. |
| Kích thước payload | Lớn hơn khi nhúng nhiều hoặc dữ liệu lớn. | Nhỏ hơn. |
| Tính cập nhật | Dữ liệu là snapshot tại thời điểm response được tạo. | Client lấy representation mới nhất khi theo link. |
| Cache | Cache collection có thể chứa bản sao dữ liệu liên quan. | Resource liên quan có thể được cache độc lập. |
| Phân quyền | Server phải bảo đảm dữ liệu nhúng được phép xem trong request hiện tại. | Quyền được kiểm tra khi client truy cập resource đích. |

Nên nhúng dữ liệu nhỏ, thường được client cần cùng lúc với resource cha, chẳng hạn một số trường tóm tắt khách hàng trong danh sách đơn hàng. Nên chỉ cung cấp link khi resource liên quan lớn, ít được dùng, thay đổi độc lập, cần cache riêng hoặc có chính sách truy cập khác.

Không nên nhúng toàn bộ graph object của domain. Việc nhúng cần có giới hạn rõ ràng để tránh payload lớn, vòng lặp quan hệ, lộ dữ liệu không cần thiết và khó kiểm soát độ tươi của dữ liệu.

## Có thể vừa embed vừa cung cấp link không?

Có. Một embedded resource có thể chứa link `self` để client mở representation độc lập sau này. Ví dụ danh sách đơn hàng nhúng một số trường của từng đơn hàng, đồng thời mỗi item có link `self` đến resource đầy đủ. Client có thể dùng dữ liệu nhúng để hiển thị nhanh, sau đó theo link nếu cần tải chi tiết mới nhất.

Tương tự, resource cha có thể embed một representation liên quan dưới `_embedded.customer` và đồng thời cung cấp `_links.customer` đến URI chuẩn của khách hàng. Cách này hữu ích khi client thường cần bản tóm tắt khách hàng ngay lập tức nhưng vẫn cần khả năng điều hướng đến resource đầy đủ.

Nếu cung cấp cả hai, hãy xác định rõ embedded representation là snapshot hoặc projection nào, và link trỏ đến canonical resource nào. Tránh khiến client không biết dữ liệu nào là nguồn sự thật khi hai representation khác thời điểm.

## Tên relation trong _embedded

Tên relation trong `_embedded` là một phần hợp đồng HAL. Spring HATEOAS có thể suy ra tên từ kiểu representation hoặc dùng `@Relation` để cấu hình tên item và collection:

```java
@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(UUID id, String status) {
}
```

Với cấu hình này, collection relation là `orders`. Tên item relation là `order` và có thể được dùng bởi các cơ chế HAL cần biểu diễn một item theo relation tương ứng. Hãy kiểm tra JSON được serialize thực tế vì tên relation phụ thuộc model type và cấu hình relation provider.

Không nên để client phụ thuộc vào tên class Java như `orderViewList` nếu đó chỉ là tên mặc định do framework suy ra. Đổi tên class nội bộ không nên vô tình làm thay đổi key `_embedded` mà client đang sử dụng.

## Embedded và top-level link trong phân trang

Khi collection được phân trang, top-level links thường chứa `self`, `first`, `prev`, `next`, `last`. `_embedded` chứa các item trong trang hiện tại. Link điều hướng trang thuộc collection, không thuộc từng item.

Spring Data HATEOAS có thể chuyển `Page<T>` thành `PagedModel` bằng `PagedResourcesAssembler`:

```java
@GetMapping
PagedModel<EntityModel<OrderView>> all(Pageable pageable) {
    Page<Order> page = orders.findAll(pageable);
    return pagedResourcesAssembler.toModel(page, assembler);
}
```

Ví dụ giả định controller được tiêm `PagedResourcesAssembler<Order>` và `assembler` có kiểu `RepresentationModelAssembler<Order, EntityModel<OrderView>>`. Paged assembler tạo metadata trang và top-level links điều hướng; item assembler tạo representation và link riêng cho từng đơn hàng.

Không nên đặt link `next` vào từng embedded item. Link đó đại diện cho trang tiếp theo của collection. Client nên theo `next.href` thay vì tự tăng tham số `page` hoặc tự ghép URL.

## Kiểm thử embedded resources và top-level links

Kiểm thử nên xác nhận cấu trúc response HAL ở cả hai cấp. Với MockMvc:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/hal+json")))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.search.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.customer.href").exists());
```

Test này xác nhận top-level links và item links nằm đúng vị trí. `orders` là tên embedded relation được cấu hình bằng `@Relation` trong ví dụ.

Với collection rỗng, HAL có thể bỏ `_embedded` vì không có phần tử. Do đó, nên kiểm tra top-level link độc lập:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Các trường hợp nên có test riêng:

- Collection có nhiều item và mỗi item có link `self` đúng.
- Top-level `self` trỏ đến collection, không trỏ đến item đầu tiên.
- Filter/sort/page hiện tại được giữ trong top-level self link.
- Embedded relation giữ đúng tên đã công bố.
- Link đến resource liên quan xuất hiện khi quan hệ có thể truy cập.
- Dữ liệu nhúng không chứa field nhạy cảm hoặc field ngoài projection.
- Collection rỗng vẫn trả link cấp collection theo hợp đồng.
- Link phân trang nằm ở top-level `_links`, không nằm trong item.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm top-level `_links` với link trong embedded item | Client tìm link ở sai cấp và không điều hướng được. | Xác định resource mà mỗi link mô tả và đặt link đúng cấp. |
| Trả `CollectionModel<DTO>` nhưng kỳ vọng item có `_links` | Embedded item chỉ có dữ liệu, không có link riêng. | Dùng `CollectionModel<EntityModel<DTO>>` hoặc custom model nếu cần item links. |
| Dùng top-level link cho từng item | Không biết link nào thuộc đơn hàng nào. | Đặt item link bên trong representation của item. |
| Nhúng quá nhiều dữ liệu | Payload lớn, chậm và khó cache. | Chỉ nhúng projection nhỏ mà client thường cần; phần còn lại cung cấp link. |
| Không giữ relation `_embedded` ổn định | Đổi tên class có thể làm client không tìm thấy collection. | Cấu hình `@Relation` và kiểm thử JSON HAL. |
| Bỏ filter khỏi top-level self link | Client theo link nhận một collection khác. | Giữ query parameter ảnh hưởng đến kết quả. |
| Cho rằng embedded data luôn mới nhất | Client có thể dùng snapshot cũ. | Mô tả rõ snapshot và cung cấp self link đến canonical resource khi cần. |
| Nhúng dữ liệu vượt quyền | Response làm lộ thông tin của resource liên quan. | Áp dụng authorization và projection ở server trước khi embed. |
| Đặt link phân trang bên trong item | Client hiểu sai phạm vi điều hướng. | Đặt `next`, `prev`, `first`, `last` ở top-level collection links. |

## Ghi nhớ

- HAL dùng `_embedded` để chứa representation của resource liên quan và `_links` để công bố các quan hệ điều hướng.
- Top-level `_links` mô tả collection hiện tại; `_links` bên trong embedded item mô tả item đó.
- Dùng `CollectionModel<EntityModel<T>>` khi collection cần item link riêng; dùng `CollectionModel<T>` khi chỉ cần dữ liệu item.
- `@Relation(itemRelation, collectionRelation)` giúp ổn định tên relation khi embed.
- Embedded resource giảm request tiếp theo nhưng tăng payload và có thể là snapshot; link-only resource cho phép client tải representation độc lập.
- Có thể vừa embed vừa cung cấp link đến canonical resource nếu hợp đồng xác định rõ ý nghĩa của hai dạng dữ liệu.
- Link phân trang như `next` và `prev` thuộc top-level collection.
- Kiểm thử JSON HAL ở cả cấp collection và item, bao gồm collection rỗng, relation name, query context và quyền truy cập.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS API – CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Spring HATEOAS API – EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS API – Relation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [HAL – Hypertext Application Language](https://stateless.group/hal_specification.html)
