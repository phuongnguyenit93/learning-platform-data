# EntityLinks là gì

## Mục tiêu

Khi tạo hypermedia link, ứng dụng thường cần trỏ tới collection hoặc một tài nguyên cụ thể. Nếu mỗi assembler đều phải tham chiếu controller và tự mô tả cách tạo URI, code sẽ phụ thuộc vào cấu trúc controller. Spring HATEOAS cung cấp EntityLinks để tạo link dựa trên kiểu tài nguyên và định danh của nó. Nhờ vậy, code có thể nói rõ “link tới collection Order” hoặc “link tới Order có ID này” mà không cần tham chiếu trực tiếp OrderController.

EntityLinks là một abstraction ở phía server, hỗ trợ tra cứu Link hoặc LinkBuilder cho tài nguyên miền. Với Spring MVC, triển khai ControllerEntityLinks có thể đọc mapping của controller được đánh dấu bằng @ExposesResourceFor.

Sau bài học, bạn có thể:

- Giải thích mục đích của EntityLinks trong Spring HATEOAS.
- Phân biệt link tới collection resource và item resource.
- Cấu hình và sử dụng ControllerEntityLinks qua @EnableHypermediaSupport.
- Đánh dấu controller bằng @ExposesResourceFor để khai báo kiểu tài nguyên được expose.
- Dùng EntityLinks trong assembler và kiểm thử URI được tạo.
- Nhận biết khi nào cần TypedEntityLinks hoặc một implementation tùy chỉnh.

## EntityLinks giải quyết vấn đề gì?

Giả sử ứng dụng có tài nguyên Order được expose qua hai endpoint:

~~~text
GET /api/orders
GET /api/orders/42
~~~

Assembler có thể cần tạo hai loại link:

- Collection resource: /api/orders.
- Item resource: /api/orders/42.

Nếu dùng WebMvcLinkBuilder, code tham chiếu trực tiếp OrderController và method tương ứng. Cách này hữu ích khi link gắn với một handler cụ thể. Nhưng nếu nhiều nơi chỉ cần link theo kiểu tài nguyên và ID, việc lặp lại controller class cùng method có thể tạo phụ thuộc không cần thiết.

EntityLinks cung cấp API theo kiểu tài nguyên:

~~~java
Link collection = entityLinks.linkToCollectionResource(Order.class);
Link item = entityLinks.linkToItemResource(Order.class, 42L);
~~~

Đoạn code thể hiện ý định ở mức miền: tạo link tới collection Order hoặc item Order có định danh 42. Implementation sẽ tìm controller quản lý kiểu đó và dùng mapping để tạo URI. Consumer của EntityLinks không cần biết controller có tên gì.

EntityLinks không phải entity model và không phải repository. Nó không tải dữ liệu, không lưu entity, không thực hiện nghiệp vụ và cũng không tự quyết định quyền truy cập. Nó chỉ là abstraction để tạo link tới tài nguyên mà ứng dụng đã công bố.

## Collection resource và item resource

Một collection resource đại diện cho tập tài nguyên cùng loại. Một item resource đại diện cho một phần tử trong tập đó.

| Loại link | API | Kết quả minh họa |
|---|---|---|
| Collection resource | linkToCollectionResource(Order.class) | /api/orders |
| Item resource | linkToItemResource(Order.class, orderId) | /api/orders/42 |
| Link builder theo kiểu tài nguyên | linkFor(Order.class) | Builder cho URI gốc của collection Order |

Các method bắt đầu bằng linkTo... trả về Link đã được tạo. Method linkFor(...) trả về LinkBuilder, cho phép bổ sung path segment hoặc metadata trước khi tạo link.

Ví dụ, linkFor tạo builder cho collection resource. Có thể nối ID vào builder để tạo link item:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.LinkBuilder;

LinkBuilder orders = entityLinks.linkFor(Order.class);
Link item = orders.slash(orderId).withSelfRel();
~~~

Ví dụ:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class OrderLinkFactory {

    private final EntityLinks entityLinks;

    OrderLinkFactory(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    Link collectionLink() {
        return entityLinks.linkToCollectionResource(Order.class);
    }

    Link itemLink(Order order) {
        return entityLinks.linkToItemResource(
                Order.class, order.getId());
    }
}
~~~

Định danh phải khớp kiểu và cách mapping của ứng dụng. Nếu ID là UUID, truyền UUID; nếu ID là Long, truyền Long. Không truyền toàn bộ entity vào overload nhận Class và ID.

## Cấu hình EntityLinks trong Spring MVC

Trong cấu hình Spring HATEOAS cho Spring MVC, bật hỗ trợ hypermedia bằng @EnableHypermediaSupport. Annotation này đăng ký các thành phần cần thiết cho hypermedia và một EntityLinks có thể inject. Implementation mặc định quan trọng là ControllerEntityLinks, dùng metadata trên controller để tìm mapping cho kiểu tài nguyên.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
~~~

Ví dụ dùng HAL JSON. Nếu ứng dụng Spring Boot đã có auto-configuration cho Spring HATEOAS, hãy kiểm tra cấu hình hiện có trước khi khai báo thêm một cấu hình trùng lặp. Tự khai báo @EnableHypermediaSupport là cách kiểm soát rõ cấu hình; trong Boot, việc dùng annotation này sẽ thay đổi cách auto-configuration xử lý JSON mapper.

Để ControllerEntityLinks nhận diện controller, đánh dấu controller bằng @ExposesResourceFor và tổ chức mapping theo quy ước:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
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
    CollectionModel<EntityModel<OrderResponse>> findAll() {
        return null; // Thay bằng collection representation của ứng dụng.
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> findById(@PathVariable UUID id) {
        return null; // Thay bằng representation của đơn hàng.
    }
}
~~~

Các thành phần có ý nghĩa:

1. @ExposesResourceFor(Order.class) khai báo controller này expose collection và item resources cho kiểu Order.
2. @RequestMapping("/api/orders") xác định mapping cơ sở của collection resource.
3. Handler method có mapping ở cấp method xử lý collection resource, ví dụ @GetMapping.
4. Handler method khác có path variable để xác định item resource, ví dụ @GetMapping("/{id}").

ControllerEntityLinks dựa trên cấu trúc mapping này để suy ra link collection và link item. Nếu controller dùng URI structure không theo quy ước, nhiều base path khác nhau cho cùng entity hoặc cách ánh xạ item phức tạp, implementation mặc định có thể không phù hợp; khi đó cân nhắc custom EntityLinks.

## Inject EntityLinks vào assembler

Assembler có thể phụ thuộc vào abstraction EntityLinks thay vì controller cụ thể:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    private final EntityLinks entityLinks;

    OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        Link self = entityLinks.linkToItemResource(
                Order.class, order.getId())
                .withRel(IanaLinkRelations.SELF);

        Link collection = entityLinks.linkToCollectionResource(Order.class)
                .withRel(IanaLinkRelations.COLLECTION);

        return EntityModel.of(
                OrderResponse.from(order), self, collection);
    }
}
~~~

EntityLinks tạo URI và relation mặc định theo thông tin resource. Assembler có thể thay relation của link khi hợp đồng representation yêu cầu, ví dụ dùng self cho item và collection cho link quay lại danh sách. Hãy chọn relation nhất quán với ý nghĩa mà client sẽ tiêu thụ.

Trong ví dụ, assembler không cần biết URI được xây từ /api/orders/{id} hay một mapping khác. Việc thay đổi mapping ở controller có thể được phản ánh trong link do implementation tra cứu mapping.

## TypedEntityLinks và ID extractor

Nếu nhiều nơi thường xuyên tạo link item từ cùng một kiểu entity, việc truyền class và ID lặp lại có thể được gom lại bằng TypedEntityLinks.

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.TypedEntityLinks;

class OrderLinkFactory {

    private final TypedEntityLinks<Order> orderLinks;

    OrderLinkFactory(EntityLinks entityLinks) {
        this.orderLinks = entityLinks.forType(Order::getId);
    }

    Link self(Order order) {
        return orderLinks.linkToItemResource(order)
                .withRel("self");
    }
}
~~~

forType(Order::getId) cung cấp hàm lấy ID một lần. Sau đó, code có thể tạo item link trực tiếp từ entity bằng linkToItemResource(order) mà không phải truyền lại class và ID ở từng chỗ. Cách này hữu ích khi ID extractor được dùng lặp lại trong nhiều assembler hoặc service tạo link.

Hàm lấy ID phải trả về đúng định danh được dùng trong URI mapping. Nếu entity chưa được lưu hoặc ID chưa được gán, link item có thể không tạo được URI hợp lệ; hãy chỉ tạo link sau khi có định danh.

## EntityLinks và WebMvcLinkBuilder

Hai API đều tạo link từ mapping của Spring MVC nhưng bắt đầu từ các khái niệm khác nhau:

| EntityLinks | WebMvcLinkBuilder |
|---|---|
| Bắt đầu từ kiểu tài nguyên và ID. | Bắt đầu từ controller hoặc handler method. |
| Không cần assembler tham chiếu controller cụ thể. | Tham chiếu trực tiếp controller class và method qua methodOn. |
| Phù hợp với quy ước collection/item nhất quán. | Phù hợp với endpoint đặc biệt, action hoặc mapping có cấu trúc riêng. |
| linkToItemResource(Order.class, id) | linkTo(methodOn(OrderController.class).findById(id)) |

Ví dụ, link tới item chuẩn của Order có thể dùng EntityLinks. Link tới hành động cancel, approve hoặc một endpoint tìm kiếm đặc biệt thường dễ diễn đạt hơn bằng WebMvcLinkBuilder, vì các thao tác đó không nhất thiết là collection/item resource theo quy ước.

Có thể kết hợp hai API trong cùng ứng dụng. Dùng EntityLinks cho các link item/collection phổ biến và dùng WebMvcLinkBuilder cho các handler đặc thù.

## EntityLinks là một SPI có thể mở rộng

EntityLinks là một service provider interface. Cấu hình hypermedia support đăng ký một DelegatingEntityLinks, implementation này tổng hợp các implementation EntityLinks được đăng ký thành Spring bean. ControllerEntityLinks là implementation mặc định dựa trên controller mapping.

Nếu ứng dụng có cấu trúc URI riêng, có thể viết implementation EntityLinks tùy chỉnh. Ví dụ, một kiểu tài nguyên có thể được expose qua gateway hoặc một hệ thống route khác không theo quy ước @ExposesResourceFor. Implementation tùy chỉnh chịu trách nhiệm tạo link đúng theo mapping của hệ thống đó và được đăng ký làm bean để DelegatingEntityLinks có thể sử dụng.

Spring Data REST cũng có RepositoryEntityLinks, implementation sử dụng thông tin mapping của repository để tạo link tới resource do repository expose. Điều này cho phép code làm việc theo kiểu entity mà không cần biết chi tiết controller/repository mapping.

Lưu ý: EntityLinks được thiết kế ban đầu cho Spring MVC. Tài liệu Spring HATEOAS hiện hành không cung cấp sẵn các implementation EntityLinks tương đương cho Spring WebFlux; không nên giả định chỉ cần inject cùng interface là có hành vi mặc định trong ứng dụng reactive.

## Kiểm thử EntityLinks

Kiểm thử tích hợp với MockMvc giúp xác nhận @ExposesResourceFor và mapping controller tạo ra URI đúng:

~~~java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/api/orders/" + orderId)));
~~~

Nếu representation có link collection, kiểm tra relation và path tương ứng. Có thể kiểm thử trực tiếp EntityLinks trong một test có ApplicationContext đã bật hypermedia support:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

Link item = entityLinks.linkToItemResource(Order.class, orderId);
Link collection = entityLinks.linkToCollectionResource(Order.class);

assertThat(item.getHref()).endsWith("/api/orders/" + orderId);
assertThat(collection.getHref()).endsWith("/api/orders");
~~~

Các trường hợp nên kiểm thử:

- Controller có @ExposesResourceFor đúng kiểu domain.
- Mapping cấp class tạo đúng collection path.
- Mapping item có path variable tạo đúng URI với ID.
- Các kiểu ID khác nhau được serialize đúng trong path.
- Custom EntityLinks được chọn đúng nếu ứng dụng có nhiều resource mapping.
- Mapping thay đổi nhưng link được tạo vẫn theo endpoint mới.

Nếu EntityLinks không tìm thấy controller tương ứng, kiểm tra annotation @ExposesResourceFor, mapping cấp class, mapping item và cấu hình @EnableHypermediaSupport trước khi thay thế implementation.

## Những lỗi thường gặp

- **Nhầm EntityLinks với EntityModel:** EntityLinks tạo link; EntityModel bọc nội dung representation cùng links.
- **Cho rằng EntityLinks tự truy vấn dữ liệu:** API chỉ tạo URI, không gọi repository hoặc tải entity.
- **Quên @ExposesResourceFor:** ControllerEntityLinks cần biết controller expose kiểu domain nào.
- **Mapping không theo quy ước collection/item:** implementation mặc định dựa trên base mapping và item mapping có path variable. Cấu trúc khác cần custom implementation hoặc link builder trực tiếp.
- **Dùng EntityLinks cho mọi action:** API này tập trung vào collection và item resources. Action đặc biệt thường cần WebMvcLinkBuilder và affordance.
- **Nhầm kiểu ID:** truyền ID không đúng kiểu hoặc ID chưa tồn tại sẽ tạo link sai hoặc không thể mở rộng URI.
- **Giả định WebFlux có implementation mặc định:** kiểm tra hỗ trợ của phiên bản đang dùng; EntityLinks hiện hướng tới Spring MVC.

## Quy trình sử dụng EntityLinks

1. Xác định kiểu domain cần expose và các URI collection/item tương ứng.
2. Đánh dấu controller bằng @ExposesResourceFor và tổ chức mapping collection cùng item theo quy ước.
3. Bật hypermedia support trong Spring MVC để đăng ký EntityLinks.
4. Inject EntityLinks vào assembler hoặc thành phần tạo link.
5. Dùng linkToCollectionResource và linkToItemResource; cân nhắc TypedEntityLinks khi ID extractor được dùng lặp lại.
6. Dùng WebMvcLinkBuilder hoặc custom EntityLinks cho các mapping đặc biệt.
7. Kiểm thử URI collection/item, relation và khả năng theo kịp thay đổi mapping.

EntityLinks giúp tạo liên kết dựa trên kiểu tài nguyên và định danh, giảm phụ thuộc của assembler vào tên controller và method. Khi controller công bố rõ resource type qua @ExposesResourceFor và mapping tuân theo quy ước collection/item, Spring HATEOAS có thể tạo các link nhất quán cho representation hypermedia.
