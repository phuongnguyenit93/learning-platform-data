# Mapping entity với endpoint

Trong Spring HATEOAS, **EntityLinks** là abstraction giúp tạo liên kết đến endpoint của một loại tài nguyên dựa trên mapping của controller. Thay vì tự ghép chuỗi URL cho từng entity, ứng dụng khai báo controller nào cung cấp tài nguyên đó, sau đó dùng EntityLinks để tạo link đến collection hoặc một item cụ thể.

Ví dụ, controller quản lý đơn hàng được ánh xạ với kiểu miền Order và có các endpoint /orders, /orders/{id}. Khi assembler cần tạo self link cho một đơn hàng, nó có thể yêu cầu EntityLinks tạo link đến item Order có ID tương ứng. Nếu đường dẫn controller thay đổi, link builder dựa trên mapping sẽ theo cấu trúc mới.

EntityLinks chỉ ánh xạ kiểu tài nguyên với endpoint. Nó không truy vấn cơ sở dữ liệu, không tải entity và không quyết định quyền truy cập. Ứng dụng vẫn chịu trách nhiệm lấy dữ liệu, kiểm tra quyền và chọn các liên kết phù hợp với trạng thái nghiệp vụ.

Sau bài học, bạn có thể:

- Giải thích EntityLinks và vai trò của nó trong Spring HATEOAS.
- Ánh xạ một loại entity với controller bằng @ExposesResourceFor.
- Tạo link đến collection và item bằng EntityLinks.
- Tích hợp EntityLinks vào RepresentationModelAssembler và controller.
- Phân biệt kiểu entity dùng để tìm endpoint với DTO dùng làm content response.
- Kiểm thử mapping, URI và relation được serialize trong HAL JSON.

## Vì sao cần ánh xạ entity với endpoint?

Một ứng dụng có thể có nhiều loại tài nguyên như Order, Customer, Product và Invoice. Mỗi loại có controller và URI riêng:

| Loại tài nguyên | Collection endpoint | Item endpoint |
| --- | --- | --- |
| Order | /orders | /orders/{id} |
| Customer | /customers | /customers/{id} |
| Product | /products | /products/{id} |
| Invoice | /invoices | /invoices/{id} |

Nếu assembler tự tạo URI bằng cách nối chuỗi, quy tắc đường dẫn sẽ bị lặp lại:

~~~java
String href = "/orders/" + order.id();
~~~

Cách này gắn assembler với cấu trúc URL cụ thể. Khi controller đổi base path, thêm context path hoặc thay đổi cách định tuyến, các chuỗi URL viết tay có thể trở nên sai lệch.

Spring HATEOAS cung cấp các cách tạo link từ controller mapping. EntityLinks nâng cách tiếp cận đó lên mức loại tài nguyên: caller nói muốn link đến Order hoặc Customer, còn implementation tìm mapping đã khai báo cho loại tài nguyên đó.

## EntityLinks là gì?

EntityLinks là interface trong Spring HATEOAS, cung cấp các phương thức tạo link đến tài nguyên được controller công bố. Hai nhu cầu phổ biến là:

- Link đến collection của một loại tài nguyên, ví dụ /orders.
- Link đến một item cụ thể, ví dụ /orders/42.

Trong MVC, implementation dựa trên controller mapping có thể xác định endpoint thông qua annotation @ExposesResourceFor. Khi controller công bố rằng nó xử lý Order, EntityLinks có thể dùng thông tin đó để xây URI collection và item.

EntityLinks hữu ích trong assembler, service tạo representation hoặc thành phần khác cần tạo link mà không muốn phụ thuộc trực tiếp vào một controller cụ thể.

### EntityLinks không phải ORM mapping

Tên EntityLinks có thể khiến người đọc nghĩ đến quan hệ giữa entity trong JPA. Đây không phải chức năng đó:

- EntityLinks ánh xạ kiểu tài nguyên Java với endpoint HTTP.
- JPA mapping ánh xạ entity với bảng, cột và quan hệ trong cơ sở dữ liệu.
- EntityLinks không tải entity, không gọi repository và không kiểm tra entity có tồn tại.
- EntityLinks không xác thực hoặc phân quyền request.

Ví dụ, gọi link đến Order có ID 42 chỉ tạo một URI theo mapping. Nếu đơn hàng 42 không tồn tại, link vẫn có thể được tạo; endpoint xử lý request mới là nơi trả 404 Not Found.

## Khai báo controller bằng @ExposesResourceFor

Annotation @ExposesResourceFor khai báo loại tài nguyên mà controller cung cấp. Annotation thường được đặt trên controller:

~~~java
import org.springframework.hateoas.server.core.ExposesResourceFor;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
class OrderController {
    // Endpoints for the Order resource
}
~~~

Ở đây:

- @RequestMapping("/orders") khai báo base path của controller.
- @ExposesResourceFor(Order.class) cho biết controller này công bố tài nguyên kiểu Order.
- Các method endpoint trong controller xác định cách truy cập collection và từng item.

EntityLinks có thể dùng metadata này để liên kết Order.class với controller tương ứng. Khi cần tạo link item, caller cung cấp ID; khi cần link collection, caller cung cấp kiểu tài nguyên.

Với implementation ControllerEntityLinks, quy ước mapping thông thường gồm ba phần:

1. Annotation cấp lớp @ExposesResourceFor(Order.class) khai báo loại tài nguyên.
2. Mapping cấp lớp, chẳng hạn /orders, đại diện cho collection resource.
3. Một method mapping cấp phương thức nối thêm path segment chứa định danh, chẳng hạn /{id}, đại diện cho item resource.

EntityLinks không tự đoán mọi cấu trúc URI tùy ý. Nếu controller không theo quy ước mapping mà implementation hỗ trợ, hãy dùng LinkBuilder phù hợp hoặc tự cung cấp implementation EntityLinks.

### Một controller đầy đủ hơn

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.core.ExposesResourceFor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderResponse>> all() {
        return assembler.toCollectionModel(orderService.findAll());
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> one(@PathVariable Long id) {
        Order order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return assembler.toModel(order);
    }
}
~~~

Đoạn mã minh họa giả định OrderService.findAll() trả về một Iterable<Order>, findById() trả về Optional<Order>, cùng các kiểu Order, OrderResponse và OrderModelAssembler đã được khai báo. Controller định tuyến request và gọi service; assembler chuyển dữ liệu miền thành representation có link.

## Tạo link đến collection và item

Sau khi controller khai báo loại tài nguyên, có thể inject EntityLinks vào thành phần cần tạo link:

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
        return entityLinks.linkToCollectionResource(Order.class)
            .withRel("orders");
    }

    Link itemLink(Long id) {
        return entityLinks.linkToItemResource(Order.class, id);
    }
}
~~~

Hai lời gọi có mục đích khác nhau:

- linkToCollectionResource(Order.class) tạo Link đến endpoint collection của loại Order.
- linkToItemResource(Order.class, id) tạo Link đến endpoint item và điền định danh cụ thể.

Hai phương thức bắt đầu bằng linkTo trả về một Link hoàn chỉnh. Theo mặc định, implementation ControllerEntityLinks dùng relation self cho các link này. Có thể thay relation của collection bằng withRel("orders") như ví dụ. Với item link, relation self đã được gắn sẵn.

Nếu cần tùy chỉnh URI trước khi tạo Link, dùng các phương thức bắt đầu bằng linkFor. Ví dụ linkFor(Order.class) trả về LinkBuilder cho collection, còn linkForItemResource(Order.class, id) trả về LinkBuilder cho item. Sau đó có thể nối thêm path segment hoặc tham số rồi mới gọi withRel(...) hay withSelfRel().

Tên relation cần phản ánh semantics của API. Nếu relation collection được dùng ở nhiều nơi, hãy thống nhất tên và giữ semantics ổn định để client có thể dựa vào relation thay vì URL.

### Tạo link từ entity instance và TypedEntityLinks

EntityLinks có overload nhận entity cùng một hàm trích xuất định danh. Cách này hữu ích khi không muốn lặp lại lời gọi getter ID:

~~~java
Link self = entityLinks.linkToItemResource(order, Order::id);
~~~

Nếu cùng một loại entity được dùng ở nhiều nơi, có thể cấu hình extractor một lần bằng TypedEntityLinks:

~~~java
import org.springframework.hateoas.server.TypedEntityLinks;

TypedEntityLinks<Order> orderLinks = entityLinks.forType(Order::id);

Link self = orderLinks.linkToItemResource(order);
~~~

TypedEntityLinks giữ sẵn cách lấy ID và cho phép tạo link từ một instance. Dù dùng overload nào, kiểu resource phải khớp với kiểu được khai báo trên controller bằng @ExposesResourceFor. Nếu controller công bố Order.class nhưng caller yêu cầu Product.class, EntityLinks không thể dùng mapping Order để tạo link cho Product.

## Dùng EntityLinks trong RepresentationModelAssembler

Assembler là nơi phù hợp để chuyển đối tượng miền thành representation và gắn link. EntityLinks giúp assembler không cần import controller hoặc biết path cụ thể.

~~~java
import org.springframework.hateoas.EntityModel;
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
        OrderResponse content = new OrderResponse(
            order.id(), order.description(), order.status());

        Link self = entityLinks
            .linkToItemResource(Order.class, order.id());

        Link collection = entityLinks
            .linkToCollectionResource(Order.class)
            .withRel("orders");

        return EntityModel.of(content, self, collection);
    }
}
~~~

Trong ví dụ, Order là kiểu miền được ánh xạ với controller; OrderResponse là DTO dùng làm content công khai. Hai kiểu này có thể khác nhau. EntityLinks cần Order.class để tìm controller, trong khi EntityModel<OrderResponse> chứa DTO mà API muốn trả về.

Tách biệt như vậy giúp thay đổi schema lưu trữ hoặc entity nội bộ mà không bắt buộc làm thay đổi representation công khai. Assembler là nơi chuyển đổi từ domain model sang DTO và gắn các link tương ứng.

### Thêm link theo trạng thái nghiệp vụ

Assembler cũng có thể công bố link hành động tùy theo trạng thái:

~~~java
@Override
public EntityModel<OrderResponse> toModel(Order order) {
    OrderResponse content = new OrderResponse(
        order.id(), order.description(), order.status());

    EntityModel<OrderResponse> model = EntityModel.of(content,
        entityLinks.linkToItemResource(Order.class, order.id()),
        entityLinks.linkToCollectionResource(Order.class).withRel("orders"));

    if (order.status() == OrderStatus.PENDING_PAYMENT) {
        model.add(paymentLinks.linkToPayment(order.id()).withRel("payment"));
    }

    return model;
}
~~~

Ví dụ giả định PaymentLinkFactory chịu trách nhiệm tạo link đến tài nguyên thanh toán. EntityLinks dùng để ánh xạ Order; link payment có thể thuộc một loại tài nguyên hoặc controller khác. Chỉ công bố link khi hành động phù hợp với trạng thái nghiệp vụ và quyền của người dùng.

Link vắng mặt không phải cơ chế phân quyền. Server phải kiểm tra lại quyền và trạng thái khi client thực hiện request.

## EntityLinks với DTO và projection

Trong API thực tế, không nên mặc định trả trực tiếp JPA entity. Có thể dùng DTO hoặc projection làm content để kiểm soát dữ liệu công khai:

~~~java
public record OrderResponse(
    Long id,
    String description,
    String status
) {}
~~~

Assembler vẫn có thể sử dụng Order.class để tìm endpoint:

~~~java
EntityModel<OrderResponse> model = EntityModel.of(
    orderResponse,
    entityLinks.linkToItemResource(Order.class, orderResponse.id()));
~~~

Điều quan trọng là class được truyền vào EntityLinks phải là loại tài nguyên được controller công bố. Nó không nhất thiết là class của content trong EntityModel. Nếu controller dùng @ExposesResourceFor(Order.class), hãy truyền Order.class kể cả khi response chứa OrderResponse.

## EntityLinks và mapping tùy chỉnh

EntityLinks dựa trên metadata controller để tìm endpoint. Mapping có thể gồm base path, path variable và cấu trúc endpoint. Ví dụ:

~~~java
@RestController
@RequestMapping("/catalog/orders")
@ExposesResourceFor(Order.class)
class OrderController {

    @GetMapping
    CollectionModel<?> all() {
        // ...
    }

    @GetMapping("/{orderId}")
    EntityModel<?> one(@PathVariable("orderId") Long id) {
        // ...
    }
}
~~~

Khi controller dùng base path /catalog/orders và item variable orderId, EntityLinks sử dụng mapping được công bố để tạo link. Caller vẫn truyền Order.class và ID; caller không phải biết path variable tên orderId.

Nếu controller có mapping phức tạp, nhiều base path hoặc endpoint collection phụ thuộc tham số bổ sung, hãy kiểm tra link thực tế được sinh ra. EntityLinks chỉ có thể suy ra những route mà mapping và metadata hỗ trợ. Với URI đặc biệt không thể biểu diễn bằng abstraction này, có thể dùng WebMvcLinkBuilder hoặc UriComponentsBuilder phù hợp.

### Nhiều controller cùng công bố một loại entity

Một loại tài nguyên nên có mapping rõ ràng để EntityLinks có thể tìm endpoint nhất quán. Nếu nhiều controller cùng khai báo @ExposesResourceFor cho cùng một loại entity, việc chọn controller có thể trở nên mơ hồ hoặc phụ thuộc implementation/configuration. Tránh công bố trùng lặp ngoài ý muốn.

Nếu API có nhiều entry point cho cùng loại tài nguyên, hãy xác định controller hoặc route chuẩn dùng cho EntityLinks; các route thay thế có thể được công bố riêng bằng link relation thích hợp.

## Cấu hình và dependency

Trong ứng dụng Spring Boot, thêm starter Spring HATEOAS tương ứng với phiên bản Spring Boot đang dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
~~~

Starter tích hợp các thành phần Spring HATEOAS theo hệ sinh thái Spring Boot. Với Spring MVC, EntityLinks được cung cấp khi bật cấu hình hypermedia bằng @EnableHypermediaSupport. Ví dụ cấu hình tường minh:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = { HypermediaType.HAL })
class HypermediaConfiguration {}
~~~

Trong ứng dụng Spring Boot, cấu hình tự động có thể đảm nhiệm việc đăng ký hỗ trợ hypermedia tùy phiên bản và cấu hình ứng dụng. Khi dùng Spring MVC ngoài Boot hoặc cấu hình tùy chỉnh, hãy xác nhận implementation EntityLinks đã được đăng ký trong application context.

Không nên tự khởi tạo ControllerEntityLinks bằng new trong assembler. Hãy để Spring quản lý bean và dependency để implementation có thể sử dụng mapping, request context và cấu hình của ứng dụng.

## URI tuyệt đối, context path và reverse proxy

Link được tạo từ controller mapping có thể cần scheme, host, port và context path của request hiện tại để tạo URI tuyệt đối. Trong môi trường có reverse proxy hoặc API gateway, ứng dụng phải nhận biết đúng địa chỉ bên ngoài.

Nếu cấu hình forwarded headers không chính xác, link có thể chứa host nội bộ, port nội bộ hoặc scheme HTTP trong khi client đang truy cập HTTPS. Hãy cấu hình proxy và forwarded headers theo hạ tầng triển khai, chỉ tin cậy header từ proxy đáng tin cậy và kiểm thử link ở môi trường tương ứng.

EntityLinks giúp tránh hard-code path, nhưng không tự giải quyết mọi vấn đề triển khai mạng. Việc tạo base URI vẫn phụ thuộc request context và cấu hình của ứng dụng.

## Kiểm thử EntityLinks và mapping

Kiểm thử nên xác minh controller được ánh xạ với đúng loại entity và link sinh ra có URI cùng relation phù hợp. Có thể kiểm thử ở hai mức:

- Unit test assembler để xác minh nó yêu cầu link cho đúng resource type và ID.
- MVC test để xác minh URI thực tế được serialize trong response.

Ví dụ MockMvc:

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
class OrderEntityLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderUsesMappedItemAndCollectionLinks() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").value(
                org.hamcrest.Matchers.endsWith("/orders/42")))
            .andExpect(jsonPath("$._links.orders.href").value(
                org.hamcrest.Matchers.endsWith("/orders")));
    }
}
~~~

Test giả định order ID 42 tồn tại, controller dùng @ExposesResourceFor(Order.class), assembler tạo self và orders links, và endpoint collection có URI /orders. Nếu ứng dụng chạy với context path hoặc prefix gateway, kiểm tra path theo cấu hình môi trường thay vì cố định toàn bộ host.

Các trường hợp nên kiểm thử:

1. Order.class được ánh xạ đến đúng controller.
2. Link collection trỏ đến collection endpoint.
3. Link item chứa đúng ID và trỏ đến item endpoint.
4. DTO response vẫn dùng đúng entity type để tạo link.
5. Khi mapping controller thay đổi, link mới được sinh theo mapping mới.
6. Controller không khai báo resource type phù hợp không được dùng để tạo link nhầm.
7. Link tuyệt đối có scheme, host và prefix đúng sau reverse proxy.
8. Endpoint vẫn kiểm tra tồn tại và quyền truy cập; việc tạo được link không khẳng định tài nguyên tồn tại hoặc người dùng được phép truy cập.

## Những sai lầm thường gặp

**Nhầm EntityLinks với JPA relationship.** EntityLinks ánh xạ loại tài nguyên với endpoint HTTP; nó không mô tả quan hệ bảng hay tải dữ liệu.

**Quên @ExposesResourceFor.** Nếu implementation dựa trên annotation này mà controller không khai báo loại tài nguyên, EntityLinks có thể không tìm được mapping phù hợp.

**Truyền DTO class thay vì resource type.** Controller có thể công bố Order.class trong khi response content là OrderResponse. Khi tạo link, truyền đúng Order.class đã được ánh xạ.

**Nối chuỗi URL trong assembler.** Việc này làm assembler phụ thuộc path cụ thể và dễ sai khi mapping thay đổi. Dùng EntityLinks hoặc link builder.

**Nghĩ EntityLinks kiểm tra entity tồn tại.** EntityLinks chỉ xây URI theo mapping. Service/controller phải truy vấn dữ liệu và trả 404 nếu không có tài nguyên.

**Nghĩ link đồng nghĩa quyền truy cập.** Link không thay thế authentication, authorization hoặc kiểm tra trạng thái nghiệp vụ.

**Có nhiều controller công bố cùng một loại entity mà không xác định route chuẩn.** Điều này có thể làm mapping trở nên mơ hồ. Hãy thiết kế một mapping rõ ràng và công bố route thay thế bằng relation riêng.

## Kết luận

EntityLinks giúp Spring HATEOAS ánh xạ một loại tài nguyên Java với collection và item endpoint của controller. Controller khai báo loại tài nguyên bằng @ExposesResourceFor; assembler hoặc thành phần tạo representation dùng linkToCollectionResource và linkToItemResource để tạo URI mà không phải nối chuỗi path.

Hãy phân biệt resource type dùng để tìm endpoint với DTO dùng làm content, tập trung tạo link trong assembler, và kiểm thử URI thực tế sau serialization. EntityLinks giảm phụ thuộc vào cấu trúc URL, còn việc truy vấn dữ liệu, xác thực, phân quyền và kiểm tra trạng thái vẫn thuộc trách nhiệm của ứng dụng.

Tài liệu tham khảo: [Spring HATEOAS Reference — Using the EntityLinks interface](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-entity-links).
