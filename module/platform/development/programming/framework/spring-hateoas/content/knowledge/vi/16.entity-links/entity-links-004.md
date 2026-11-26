# Item resource link

Một dịch vụ thanh toán nhận `orderId` và cần đưa vào response một liên kết đến đơn hàng tương ứng. Nếu dùng `linkTo(methodOn(OrderController.class).one(orderId))`, code tạo link phải biết controller đang quản lý đơn hàng. Khi nhiều service hoặc assembler cần tham chiếu cùng loại resource, việc phụ thuộc trực tiếp vào controller có thể làm các thành phần gắn chặt với cấu trúc MVC.

Spring HATEOAS cung cấp `EntityLinks` để tạo liên kết dựa trên kiểu entity và định danh của nó. Thay vì chỉ định controller, code có thể yêu cầu link đến item resource của `Order` với ID cụ thể. Với cấu hình controller theo quy ước, `ControllerEntityLinks` tìm mapping tương ứng và tạo URI. Cách tiếp cận này hữu ích khi nhiều nơi cần tạo link đến cùng loại resource.

## Item resource link là gì?

Item resource là một resource đơn lẻ trong một collection. Ví dụ, `/api/orders` là collection đơn hàng còn `/api/orders/ord-1042` là item resource của một đơn hàng cụ thể.

Một item link thường có:

- **Kiểu resource:** loại entity/model mà API công bố, chẳng hạn `Order.class`.
- **Định danh:** ID của item, chẳng hạn `orderId`.
- **URI đích:** đường dẫn công khai đến item resource.
- **Relation:** quan hệ của link với representation hiện tại, thường là `self` nếu link mô tả chính item đó.

Spring HATEOAS `EntityLinks` cung cấp API để lấy link hoặc link builder từ kiểu entity và ID. Các phương thức bắt đầu bằng `linkTo...` trả về `Link` hoàn chỉnh; phương thức bắt đầu bằng `linkFor...` trả về `LinkBuilder` để có thể bổ sung path segment, tham số hoặc metadata trước khi tạo link.

## EntityLinks và ControllerEntityLinks

`EntityLinks` là abstraction cho phép tạo link đến collection resource và item resource dựa trên kiểu entity. Ứng dụng có thể inject interface này mà không cần tham chiếu trực tiếp controller quản lý entity.

`ControllerEntityLinks` là implementation mặc định dựa trên mapping Spring MVC. Nó tìm controller có khai báo entity được expose và suy ra URI theo một quy ước:

1. Controller có annotation `@ExposesResourceFor(Order.class)` để khai báo loại resource mà controller cung cấp.
2. Mapping cấp lớp, chẳng hạn `@RequestMapping("/api/orders")`, xác định URI collection.
3. Một method mapping xử lý collection resource.
4. Một method mapping khác xử lý item resource bằng path variable, chẳng hạn `@GetMapping("/{id}")`.

Ví dụ:

```java
import java.util.UUID;

import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    void all() { }

    @GetMapping("/{id}")
    void one(@PathVariable("id") UUID id) { }
}
```

Annotation `@ExposesResourceFor` gắn kiểu `Order` với controller. `ControllerEntityLinks` dùng mapping cấp lớp làm collection URI và mapping item có path variable để xác định cấu trúc URI cho một đơn hàng. Các method `void` có thân rỗng ở đây chỉ minh họa mapping cần thiết; ứng dụng thực tế sẽ trả representation tương ứng.

Để inject `EntityLinks` trong cấu hình Spring MVC thủ công, bật hỗ trợ hypermedia:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
```

Khi cấu hình này được kích hoạt, Spring HATEOAS đăng ký các thành phần hỗ trợ hypermedia, trong đó có `EntityLinks` ủy quyền đến implementation phù hợp như `ControllerEntityLinks`. Với Spring Boot starter HATEOAS, hãy kiểm tra auto-configuration của phiên bản đang dùng trước khi thêm cấu hình tường minh để tránh đăng ký trùng.

## Tạo link đến một item bằng EntityLinks

Giả sử một controller khác cần liên kết đến đơn hàng từ `orderId`. Inject `EntityLinks` và gọi `linkToItemResource(...)`:

```java
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class PaymentLinkFactory {

    private final EntityLinks entityLinks;

    PaymentLinkFactory(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    Link orderLink(UUID orderId) {
        return entityLinks.linkToItemResource(Order.class, orderId);
    }
}
```

`linkToItemResource(Order.class, orderId)` trả về một `Link` trỏ đến item resource của entity `Order` có ID tương ứng. Relation được implementation xác định và mặc định nên là `self`. Nếu link được thêm vào representation khác để chỉ một đơn hàng liên quan, có thể đổi relation theo hợp đồng:

```java
Link relatedOrder = entityLinks
    .linkToItemResource(Order.class, orderId)
    .withRel("order");
```

Ví dụ trên dùng `order` làm relation mở rộng do API định nghĩa. Hãy chọn relation ổn định, mô tả đúng quan hệ giữa resource hiện tại và đơn hàng đích.

## Phân biệt linkToItemResource và linkForItemResource

`EntityLinks` cung cấp cả phương thức tạo link hoàn chỉnh và phương thức tạo builder:

| Phương thức | Giá trị trả về | Cách sử dụng |
| --- | --- | --- |
| `linkToItemResource(Order.class, id)` | `Link` | Khi cần link item hoàn chỉnh ngay. |
| `linkForItemResource(Order.class, id)` | `LinkBuilder` | Khi cần bổ sung path segment, query parameter hoặc metadata trước khi tạo link. |
| `linkToCollectionResource(Order.class)` | `Link` | Khi cần link đến collection của loại entity. |
| `linkFor(Order.class)` | `LinkBuilder` | Khi cần builder cho collection resource theo kiểu entity. |

Ví dụ dùng builder:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.LinkBuilder;

LinkBuilder builder = entityLinks.linkForItemResource(Order.class, orderId);
Link self = builder.withSelfRel();
```

Trong hầu hết trường hợp, `linkToItemResource(...)` là lựa chọn gọn nhất. Dùng `linkForItemResource(...)` khi cần tiếp tục xây URI hoặc gắn relation theo từng bước.

Không nhầm `linkFor(Order.class)` với `linkForItemResource(Order.class, id)`: phương thức đầu tiên hướng đến collection resource, còn phương thức thứ hai hướng đến item resource có ID cụ thể.

## Tạo link từ chính entity object

Nếu đã có đối tượng `Order`, không nhất thiết phải tự gọi getter ID ở mọi nơi. `EntityLinks` có overload nhận entity cùng một hàm trích xuất định danh:

```java
Link self = entityLinks.linkToItemResource(order, Order::getId);
```

Hàm `Order::getId` cho Spring HATEOAS biết cách lấy ID từ object. Cách này hữu ích khi model có nhiều loại ID hoặc muốn tách logic lấy định danh khỏi nơi tạo link.

Nếu entity là record:

```java
Link self = entityLinks.linkToItemResource(order, Order::id);
```

Hàm trích xuất phải trả về định danh mà controller mapping dùng để nhận diện item. Không truyền một thuộc tính khác như mã hiển thị hoặc tên khách hàng nếu endpoint cần UUID hoặc khóa chính.

## Dùng TypedEntityLinks để tái sử dụng ID extractor

Khi một ứng dụng tạo nhiều link đến cùng loại entity, việc truyền `Order::getId` lặp lại có thể gây dư thừa. `EntityLinks.forType(...)` tạo `TypedEntityLinks<T>` đã ghi nhận loại entity và hàm lấy ID.

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.TypedEntityLinks;

class PaymentServiceLinks {

    private final TypedEntityLinks<Order> orderLinks;

    PaymentServiceLinks(EntityLinks entityLinks) {
        this.orderLinks = entityLinks.forType(Order::getId);
    }

    Link linkToOrder(Order order) {
        return orderLinks.linkToItemResource(order);
    }
}
```

Sau khi tạo `TypedEntityLinks<Order>`, code chỉ cần truyền đối tượng `Order`. ID được trích xuất bằng function đã cấu hình. Cách này giúp tập trung quy tắc định danh và giảm nguy cơ dùng nhầm getter khi tạo link ở nhiều nơi.

Typed link cũng có thể tạo link builder:

```java
LinkBuilder builder = orderLinks.linkForItemResource(order);
Link self = builder.withSelfRel();
```

Chọn `TypedEntityLinks` khi cùng một kiểu entity và ID extractor được dùng lặp lại. Với một link đơn lẻ, gọi `linkToItemResource(entity, extractor)` thường dễ đọc hơn.

## Tích hợp item link vào EntityModel

Một assembler có thể dùng `EntityLinks` để tạo self link cho từng item mà không phụ thuộc trực tiếp vào controller:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    private final EntityLinks entityLinks;

    OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = OrderView.from(order);

        return EntityModel.of(view,
            entityLinks.linkToItemResource(order, Order::getId));
    }
}
```

`EntityLinks` chịu trách nhiệm tạo URI item; assembler chịu trách nhiệm chuyển domain object thành representation và gắn link. `OrderView.from(order)` là phương thức ánh xạ minh họa. Nếu muốn relation khác `self`, có thể dùng `.withRel(...)` trên link trước khi truyền vào `EntityModel.of(...)`.

Với collection, assembler có thể tạo item link cho từng phần tử và controller tạo link cấp collection riêng. Hai cấp link có trách nhiệm khác nhau: `EntityLinks.linkToItemResource(...)` trỏ đến một item, còn `CollectionModel` mang link của collection.

## So sánh EntityLinks với WebMvcLinkBuilder

Hai cách đều có thể tạo link đến controller resource, nhưng mức độ phụ thuộc khác nhau:

| Tiêu chí | `EntityLinks` | `WebMvcLinkBuilder` với `methodOn` |
| --- | --- | --- |
| Cách chỉ định đích | Kiểu entity và ID | Controller class, method và đối số |
| Phụ thuộc controller cụ thể | Thấp hơn; dùng abstraction entity resource | Trực tiếp tham chiếu controller và method |
| Điều kiện mapping | Cần cấu hình `@ExposesResourceFor` và URI convention mà implementation hiểu | Dựa trên mapping của phương thức được tham chiếu |
| Trường hợp phù hợp | Nhiều nơi cần link đến cùng loại item/collection | Cần link đến method cụ thể hoặc endpoint có cấu trúc đặc biệt |
| Tùy chỉnh URI | Có thể đăng ký implementation `EntityLinks` riêng | Có thể tạo link từ mapping method hoặc builder tùy chỉnh |

Ví dụ `WebMvcLinkBuilder`:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
    .withSelfRel();
```

Ví dụ `EntityLinks`:

```java
Link self = entityLinks.linkToItemResource(Order.class, orderId);
```

Nếu chỉ cần link đến item resource theo loại entity, `EntityLinks` giảm phụ thuộc vào tên controller. Nếu cần link đến một thao tác cụ thể như `cancel`, `ship` hoặc `replace`, `methodOn` thường diễn đạt trực tiếp hơn vì thao tác được xác định bằng method mapping.

## Cấu trúc URI và giới hạn của ControllerEntityLinks

`ControllerEntityLinks` dựa trên quy ước mapping controller. Nó phù hợp khi collection URI nằm ở class-level mapping và item URI được tạo bằng cách nối một path variable ở method-level mapping. Ví dụ `/api/orders` và `/api/orders/{id}`.

Nếu item URI có cấu trúc phức tạp như `/tenants/{tenantId}/orders/{id}`, cần cung cấp đủ tham số base mapping qua các API builder phù hợp hoặc cân nhắc một implementation `EntityLinks` riêng. Nếu một controller quản lý nhiều loại resource với cấu trúc URI không theo quy ước, không nên kỳ vọng `ControllerEntityLinks` tự suy ra mọi mapping tùy ý.

`EntityLinks` là SPI nên có thể đăng ký implementation riêng dưới dạng Spring bean. `DelegatingEntityLinks` sẽ ủy quyền đến các implementation hỗ trợ kiểu entity. Ví dụ, Spring Data REST cung cấp `RepositoryEntityLinks` để tạo link theo mapping repository. Cách này hữu ích khi URI được quyết định bởi một hệ thống mapping khác thay vì controller MVC.

Các implementation dựa trên request thường cần request context để xác định host và scheme. Khi tạo link trong HTTP request, hãy kiểm tra forwarded headers và cấu hình reverse proxy để URI trả về là địa chỉ công khai. Với batch job hoặc tiến trình nền không có request context, cần dùng base URI được cấu hình hoặc một implementation `EntityLinks` phù hợp thay vì giả định luôn có request hiện tại.

## Lưu ý với Spring WebFlux

`EntityLinks` được thiết kế ban đầu cho Spring Web MVC và hiện không được cung cấp sẵn như một abstraction tương đương trong Spring WebFlux. Nếu ứng dụng dùng WebFlux, hãy kiểm tra hỗ trợ của phiên bản Spring HATEOAS đang sử dụng và cân nhắc tạo link bằng các API phù hợp với WebFlux hoặc một abstraction riêng. Không nên giả định bean `EntityLinks` và `ControllerEntityLinks` sẽ tự xuất hiện trong ứng dụng reactive.

## Kiểm thử item resource link

Kiểm thử nên xác nhận link trỏ đến đúng URI item và có relation đúng. Với unit test cho factory:

```java
Link link = entityLinks.linkToItemResource(Order.class, orderId);

assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
assertThat(link.getHref()).endsWith("/api/orders/" + orderId);
```

Relation mặc định phụ thuộc implementation `EntityLinks` và link relation provider. `ControllerEntityLinks` nên mặc định relation item là `self`; nếu ứng dụng tùy chỉnh relation provider hoặc thay implementation, hãy kiểm thử theo hợp đồng thực tế.

Với endpoint trả về HAL, có thể kiểm tra link trong response bằng MockMvc:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.endsWith("/api/orders/" + orderId)));
```

Ngoài ra, nên kiểm tra:

- ID truyền vào được ánh xạ đúng vào path variable.
- ID null hoặc không hợp lệ bị từ chối ở tầng thích hợp.
- Link trong assembler trỏ đến item, không nhầm sang collection.
- Relation `self` hoặc relation mở rộng đúng với hợp đồng.
- Mapping class-level và item-level thay đổi thì link sinh ra vẫn đúng.
- URI công khai có scheme, host và context path đúng khi ứng dụng chạy sau reverse proxy.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Quên `@ExposesResourceFor` | `ControllerEntityLinks` không biết controller quản lý entity nào. | Đánh dấu controller bằng kiểu entity được expose. |
| Thiếu mapping item có path variable | Không đủ quy ước để suy ra URI của item. | Khai báo method mapping cho item resource, ví dụ `/{id}`. |
| Dùng `linkFor(Order.class)` khi cần item | Link builder trỏ đến collection resource. | Dùng `linkForItemResource(Order.class, id)` hoặc `linkToItemResource(...)`. |
| Truyền nhầm ID extractor | Link có thể trỏ đến item khác hoặc URI sai. | Dùng extractor tương ứng với path variable của controller. |
| Phụ thuộc trực tiếp vào controller ở nhiều service | Tạo liên kết trở nên gắn chặt với cấu trúc MVC. | Dùng `EntityLinks` khi chỉ cần tham chiếu item/collection theo entity type. |
| Dùng EntityLinks cho endpoint hành động cụ thể | Không thể hiện rõ method action như `cancel` hoặc `replace`. | Dùng `WebMvcLinkBuilder`/`methodOn` và affordance cho method cụ thể. |
| Giả định EntityLinks có sẵn trong WebFlux | Không có bean/implementation tương ứng như trong MVC. | Chọn API hoặc abstraction phù hợp với WebFlux. |

## Ghi nhớ

- `EntityLinks` tạo link đến collection và item resource dựa trên kiểu entity và ID.
- `ControllerEntityLinks` dùng `@ExposesResourceFor`, class-level `@RequestMapping` và method mapping có path variable để suy ra URI.
- `linkToItemResource(type, id)` trả `Link`; `linkForItemResource(type, id)` trả `LinkBuilder`.
- Có thể truyền entity cùng ID extractor hoặc dùng `TypedEntityLinks` để tái sử dụng extractor.
- Dùng `EntityLinks` khi cần link đến item theo entity type mà không muốn tham chiếu controller cụ thể.
- Dùng `WebMvcLinkBuilder`/`methodOn` khi cần trỏ đến method hoặc action cụ thể.
- `EntityLinks` có thể mở rộng qua SPI; không mặc định có implementation sẵn cho WebFlux.
- Kiểm thử relation và URI item trong model lẫn response HAL đã serialize.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Using the EntityLinks interface](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-generation.entity-links)
- [Spring HATEOAS API – EntityLinks](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/EntityLinks.html)
- [Spring HATEOAS API – ControllerEntityLinks](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/ControllerEntityLinks.html)
- [Spring HATEOAS API – TypedEntityLinks](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/TypedEntityLinks.html)
- [Spring HATEOAS API – ExposesResourceFor](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/ExposesResourceFor.html)
