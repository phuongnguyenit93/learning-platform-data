# EntityLinks trong controller

`EntityLinks` là một abstraction của Spring HATEOAS cho phép tạo liên kết đến tài nguyên dựa trên kiểu domain mà controller công bố. Thay vì để một controller biết tên và mapping của controller khác, ứng dụng có thể yêu cầu `EntityLinks` tạo link đến collection hoặc item resource bằng cách truyền vào kiểu tài nguyên và định danh của nó.

Ví dụ, `PaymentController` cần trả về link đến đơn hàng liên quan. Nếu gọi trực tiếp `linkTo(methodOn(OrderController.class).one(orderId))`, controller thanh toán phụ thuộc vào lớp `OrderController`. Với `EntityLinks`, nó chỉ cần gọi `entityLinks.linkToItemResource(Order.class, orderId)`. Controller quản lý `Order` được đánh dấu bằng `@ExposesResourceFor(Order.class)`, và Spring HATEOAS ánh xạ kiểu domain đó đến URI do controller công bố.

Cách tiếp cận này tách việc sử dụng tài nguyên khỏi chi tiết controller đang xử lý nó. Nó đặc biệt hữu ích khi nhiều controller hoặc assembler cần tạo link đến cùng một loại tài nguyên, hoặc khi muốn thay đổi cách tổ chức controller mà vẫn giữ một API tạo link thống nhất.

Sau bài học, bạn có thể:

- Giải thích vai trò của `EntityLinks` và cách nó khác với `WebMvcLinkBuilder`.
- Đánh dấu controller bằng `@ExposesResourceFor` để công bố kiểu tài nguyên.
- Kích hoạt hạ tầng hypermedia và inject `EntityLinks`.
- Tạo link đến collection resource và item resource.
- Dùng `EntityLinks` trong controller và assembler để liên kết các tài nguyên.
- Dùng `TypedEntityLinks` để tái sử dụng logic lấy định danh.
- Nhận diện cấu trúc URI mà `ControllerEntityLinks` có thể suy ra.
- Kiểm thử mapping giữa domain type và controller.

## 1. Vì sao cần EntityLinks?

Giả sử hệ thống thương mại điện tử có hai tài nguyên: `Order` và `Payment`. Một khoản thanh toán luôn tham chiếu đến một đơn hàng. Khi trả về thông tin thanh toán, API muốn cung cấp link đến đơn hàng tương ứng.

Nếu tạo link trực tiếp từ controller:

~~~java
Link orderLink = linkTo(
    methodOn(OrderController.class).one(payment.getOrderId())
).withRel("order");
~~~

Cách này hợp lệ, nhưng `PaymentController` phải biết `OrderController`. Khi ứng dụng có nhiều controller hoặc muốn thay đổi cấu trúc tổ chức controller, các tham chiếu lớp có thể lan rộng.

Dùng `EntityLinks`:

~~~java
Link orderLink = entityLinks
    .linkToItemResource(Order.class, payment.getOrderId())
    .withRel("order");
~~~

Ở đây, code chỉ nêu kiểu domain `Order` và ID. `EntityLinks` tìm implementation biết cách tạo URI cho kiểu đó. Với Spring MVC, implementation mặc định là `ControllerEntityLinks`, sử dụng metadata từ controller đã công bố tài nguyên bằng `@ExposesResourceFor`.

Sự khác biệt về trách nhiệm:

| Cách tạo link | Phụ thuộc vào | Phù hợp khi |
|---|---|---|
| `WebMvcLinkBuilder.linkTo(methodOn(...))` | Controller class và method cụ thể | Cần link đến một endpoint hoặc hành động cụ thể |
| `EntityLinks` | Kiểu domain và hạ tầng ánh xạ tài nguyên | Cần link đến collection hoặc item resource theo quy ước |
| URI lấy từ cấu hình | Địa chỉ do hệ thống ngoài quản lý | Link đến dịch vụ hoặc tài liệu bên ngoài |

`EntityLinks` không thay thế toàn bộ link builder. Nó giải quyết việc định vị collection và item resource theo kiểu domain. Với endpoint hành động như `cancel`, `approve` hoặc `publish`, `WebMvcLinkBuilder` vẫn hữu ích vì các hành động này không nhất thiết là item resource theo quy ước.

## 2. Công bố kiểu tài nguyên bằng @ExposesResourceFor

Để `ControllerEntityLinks` tìm được controller quản lý một kiểu domain, controller cần khai báo `@ExposesResourceFor`.

Ví dụ:

~~~java
@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/orders")
public class OrderController {

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        // ...
    }

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Các import chính cho controller:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

Annotation:

~~~java
@ExposesResourceFor(Order.class)
~~~

cho biết controller này công bố collection và item resource cho kiểu `Order`.

Các thành phần của mapping:

- `@ExposesResourceFor(Order.class)` liên kết domain type với controller.
- `@RequestMapping("/orders")` xác định URI cơ sở của collection.
- `@GetMapping` hoặc một mapping HTTP khác tại cấp phương thức cho phép xử lý collection.
- `@GetMapping("/{id}")` công bố item resource có định danh trong path.

Controller cần có phương thức được ánh xạ cho collection và một phương thức ánh xạ item resource bằng path variable. Đây là quy ước mà `ControllerEntityLinks` sử dụng để suy ra URI.

### 2.1. Phân biệt domain type và representation type

Giá trị của `@ExposesResourceFor` thường là kiểu domain mà controller quản lý, ví dụ `Order.class`. Nó không bắt buộc phải là DTO được serialize trong response.

~~~java
@ExposesResourceFor(Order.class)
public class OrderController {
    // Response có thể trả EntityModel<OrderRepresentation>
}
~~~

Ở đây:

- `Order` là kiểu được dùng để tra cứu link.
- `OrderRepresentation` là kiểu dữ liệu công khai trong response.
- `EntityModel<OrderRepresentation>` bao DTO cùng link hypermedia.

Cách tách này giúp API thay đổi DTO mà không cần đổi cách `EntityLinks` nhận diện tài nguyên.

### 2.2. Một kiểu tài nguyên cần ánh xạ rõ ràng

Nếu một domain type được nhiều controller công bố với những URI khác nhau, việc tra cứu có thể trở nên mơ hồ hoặc implementation không biết chọn mapping nào. Nên xác định rõ controller nào sở hữu collection và item resource chuẩn cho kiểu đó.

Nếu hệ thống có nhiều representation hoặc nhiều API version cho cùng domain type, hãy cân nhắc dùng kiểu resource riêng, custom `EntityLinks` implementation hoặc một abstraction khác để lựa chọn đúng endpoint theo ngữ cảnh.

## 3. Kích hoạt EntityLinks và inject vào controller

Trong cấu hình Spring MVC, kích hoạt hypermedia support bằng `@EnableHypermediaSupport`. Ví dụ khi dùng HAL:

~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
public class HypermediaConfiguration {
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.HypermediaType;
~~~

Khi hypermedia support được kích hoạt, Spring HATEOAS đăng ký các implementation mặc định của `EntityLinks`. Implementation nền tảng cho Spring MVC là `ControllerEntityLinks`; nó kiểm tra các controller trong `ApplicationContext` để tìm `@ExposesResourceFor` và suy ra mapping collection/item.

Có thể inject interface `EntityLinks` vào controller:

~~~java
@RestController
@RequestMapping("/payments")
public class PaymentController {

    private final EntityLinks entityLinks;

    public PaymentController(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }
}
~~~

Import:

~~~java
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.LinkBuilder;
~~~

Nên inject interface thay vì tự khởi tạo `ControllerEntityLinks`. Interface cho phép Spring chọn implementation phù hợp và hỗ trợ mở rộng bằng các implementation khác.

Nếu ứng dụng Spring Boot đã có cấu hình hypermedia support thông qua cấu hình hiện hành, hãy sử dụng cấu hình đó và tránh đăng ký lặp lại không cần thiết. Điểm cốt lõi là trong ApplicationContext phải có bean `EntityLinks` và các controller được đánh dấu phải được phát hiện.

## 4. Tạo link đến collection resource

Một collection resource đại diện cho tập hợp các đối tượng cùng loại. Với controller:

~~~java
@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/orders")
public class OrderController {

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        // ...
    }

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Có thể tạo link builder đến collection:

~~~java
Link collection = entityLinks
    .linkFor(Order.class)
    .withRel(IanaLinkRelations.COLLECTION);
~~~

`linkFor(Order.class)` trả về `LinkBuilder` trỏ đến collection resource của kiểu `Order`. Sau đó có thể chọn relation phù hợp bằng `withRel(...)`.

Một overload trả về link hoàn chỉnh:

~~~java
Link collection = entityLinks
    .linkToCollectionResource(Order.class)
    .withRel(IanaLinkRelations.COLLECTION);
~~~

`linkToCollectionResource(...)` trả về `Link` đã được tạo. Theo hợp đồng API, relation mặc định do implementation quyết định và thường là `self`; nếu cần biểu diễn collection relation trong một tài nguyên khác, có thể thay bằng relation phù hợp như `collection`.

Import relation chuẩn:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
~~~

Không nên giả định link collection luôn phải có relation `self` hoặc luôn phải có relation `collection`. Ý nghĩa phụ thuộc vào vị trí link trong biểu diễn:

- Khi response chính là collection, link đến chính collection thường dùng `self`.
- Khi một item trỏ về collection chứa nó, relation `collection` diễn đạt rõ quan hệ đó.

## 5. Tạo link đến item resource

Item resource là một tài nguyên thành viên có định danh riêng, ví dụ `/orders/{id}`.

Dùng `linkForItemResource(...)` để nhận `LinkBuilder`:

~~~java
LinkBuilder itemBuilder = entityLinks
    .linkForItemResource(Order.class, orderId);

Link self = itemBuilder.withSelfRel();
~~~

Hoặc dùng `linkToItemResource(...)` để nhận trực tiếp `Link`:

~~~java
Link self = entityLinks.linkToItemResource(Order.class, orderId);
~~~

Theo quy ước, link đến item resource thường có relation `self`. Có thể thay relation nếu link được dùng trong một biểu diễn khác:

~~~java
Link orderLink = entityLinks
    .linkToItemResource(Order.class, orderId)
    .withRel("order");
~~~

Điều này thường hữu ích khi một tài nguyên khác tham chiếu đến đơn hàng. Ví dụ, biểu diễn thanh toán có thể có link relation `order` trỏ đến item resource của đơn hàng.

### 5.1. So sánh các phương thức chính

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| `linkFor(Order.class)` | `LinkBuilder` | Tạo link builder đến collection |
| `linkForItemResource(Order.class, id)` | `LinkBuilder` | Tạo link builder đến item |
| `linkToCollectionResource(Order.class)` | `Link` | Tạo link collection hoàn chỉnh |
| `linkToItemResource(Order.class, id)` | `Link` | Tạo link item hoàn chỉnh |

Các phương thức bắt đầu bằng `linkFor...` trả về builder để có thể bổ sung path segment hoặc relation. Các phương thức bắt đầu bằng `linkTo...` trả về `Link` đã sẵn sàng để gắn vào representation.

## 6. Dùng EntityLinks trong một controller khác

Một trường hợp thực tế là controller đang xử lý tài nguyên này nhưng cần tạo link đến một tài nguyên khác. Ví dụ `PaymentController` trả về khoản thanh toán cùng link đến đơn hàng.

Giả sử các DTO:

~~~java
public record PaymentRepresentation(
    UUID id,
    BigDecimal amount,
    String status
) {}

public record CreatePaymentRequest(
    UUID orderId,
    BigDecimal amount
) {}
~~~

Controller công bố payment resource và dùng `EntityLinks` để tạo link đến cả payment lẫn order:

~~~java
@RestController
@ExposesResourceFor(Payment.class)
@RequestMapping("/payments")
public class PaymentController {

    private final PaymentService service;
    private final EntityLinks entityLinks;

    public PaymentController(
            PaymentService service,
            EntityLinks entityLinks) {
        this.service = service;
        this.entityLinks = entityLinks;
    }

    @PostMapping
    public EntityModel<PaymentRepresentation> create(
            @RequestBody CreatePaymentRequest request) {

        Payment payment = service.create(request);

        Link self = entityLinks.linkToItemResource(
            Payment.class,
            payment.getId()
        );

        Link order = entityLinks.linkToItemResource(
            Order.class,
            payment.getOrderId()
        ).withRel("order");

        return EntityModel.of(
            new PaymentRepresentation(
                payment.getId(),
                payment.getAmount(),
                payment.getStatus().name()
            ),
            self,
            order
        );
    }

    @GetMapping("/{id}")
    public EntityModel<PaymentRepresentation> one(@PathVariable("id") UUID id) {
        Payment payment = service.getRequired(id);

        return EntityModel.of(
            new PaymentRepresentation(
                payment.getId(),
                payment.getAmount(),
                payment.getStatus().name()
            ),
            entityLinks.linkToItemResource(Payment.class, id),
            entityLinks.linkToItemResource(Order.class, payment.getOrderId())
                .withRel("order")
        );
    }
}
~~~

Controller không cần import hoặc gọi `OrderController`. Nó chỉ biết rằng `Order.class` là kiểu tài nguyên được công bố. Spring HATEOAS tìm controller được đánh dấu `@ExposesResourceFor(Order.class)` và tạo href theo mapping của controller đó.

Trong ví dụ, `PaymentController` cũng được đánh dấu `@ExposesResourceFor(Payment.class)`, vì chính nó công bố item resource cho `Payment`. Do đó, link self của payment có thể được tạo bằng `entityLinks.linkToItemResource(Payment.class, payment.getId())`.

### 6.1. Các import chính

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

Ví dụ giả định các kiểu `Payment`, `Order`, `PaymentService` và các phương thức truy cập của chúng đã được định nghĩa trong ứng dụng.

## 7. Dùng EntityLinks trong assembler

Nếu nhiều response cần tạo link đến cùng loại tài nguyên, có thể inject `EntityLinks` vào assembler thay vì lặp logic trong controller.

~~~java
@Component
public class PaymentModelAssembler {

    private final EntityLinks entityLinks;

    public PaymentModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    public EntityModel<PaymentRepresentation> toModel(Payment payment) {
        Link self = entityLinks.linkToItemResource(
            Payment.class,
            payment.getId()
        );

        Link order = entityLinks.linkToItemResource(
            Order.class,
            payment.getOrderId()
        ).withRel("order");

        return EntityModel.of(
            new PaymentRepresentation(
                payment.getId(),
                payment.getAmount(),
                payment.getStatus().name()
            ),
            self,
            order
        );
    }
}
~~~

Controller lúc này chỉ điều phối:

~~~java
@GetMapping("/{id}")
public EntityModel<PaymentRepresentation> one(
        @PathVariable UUID id) {
    return assembler.toModel(service.getRequired(id));
}
~~~

Lợi ích của cách tổ chức này:

- Quy tắc chuyển Payment thành representation được tập trung.
- Các link đến Payment và Order được tạo theo cùng một cơ chế.
- Controller không cần biết cấu trúc URI của controller quản lý Order.
- Có thể kiểm thử assembler riêng bằng cách mock `EntityLinks`.

Không bắt buộc mọi link đều phải nằm trong assembler. Với một hành động chỉ xuất hiện ở một endpoint, controller hoặc assembler có thể tạo link tương ứng. Hãy chọn vị trí sao cho logic biểu diễn được tái sử dụng và dễ kiểm thử.

## 8. TypedEntityLinks và định danh được khai báo một lần

Khi thường xuyên tạo link cho cùng một kiểu domain, ứng dụng có thể lặp lại việc truyền class và ID:

~~~java
entityLinks.linkToItemResource(Order.class, order.getId());
entityLinks.linkToItemResource(Order.class, anotherOrder.getId());
~~~

`EntityLinks.forType(...)` tạo một `TypedEntityLinks<T>` đã gắn với hàm lấy ID. Ví dụ:

~~~java
TypedEntityLinks<Order> orderLinks =
    entityLinks.forType(Order::getId);
~~~

Import cho kiểu typed:

~~~java
import org.springframework.hateoas.server.TypedEntityLinks;
~~~

Sau đó:

~~~java
Link self = orderLinks.linkToItemResource(order);
~~~

Hàm `Order::getId` được khai báo một lần; mỗi lần tạo link, chỉ cần truyền đối tượng Order.

Có thể dùng trong assembler:

~~~java
@Component
public class OrderModelAssembler {

    private final TypedEntityLinks<Order> orderLinks;

    public OrderModelAssembler(EntityLinks entityLinks) {
        this.orderLinks = entityLinks.forType(Order::getId);
    }

    public EntityModel<OrderRepresentation> toModel(Order order) {
        return EntityModel.of(
            new OrderRepresentation(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
            ),
            orderLinks.linkToItemResource(order)
        );
    }
}
~~~

Nếu cần cả thông tin kiểu rõ ràng và khả năng tạo link collection, API có overload `forType(Order.class, Order::getId)` trả về `ExtendedTypedEntityLinks<Order>`. Chọn dạng typed phù hợp với nhu cầu của assembler và controller.

Typed links hữu ích khi ID có quy tắc lấy phức tạp hoặc được dùng ở nhiều nơi. Nếu chỉ tạo một hoặc hai link, gọi trực tiếp `linkToItemResource(Order.class, id)` có thể dễ đọc hơn.

## 9. Mapping có tham số ở cấp controller

`ControllerEntityLinks` suy ra URI từ cấu trúc mapping đã công bố. Với collection mapping không có path variable, có thể gọi:

~~~java
entityLinks.linkFor(Order.class)
~~~

Nếu mapping cấp lớp chứa biến, ví dụ:

~~~java
@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/customers/{customerId}/orders")
public class CustomerOrderController {
    // ...
}
~~~

thì cần truyền giá trị cho URI template khi tạo link collection:

~~~java
LinkBuilder collection = entityLinks.linkFor(
    Order.class,
    customerId
);

Link collectionLink = collection.withRel(IanaLinkRelations.COLLECTION);
~~~

`linkFor(Class, Object... parameters)` nhận các tham số để mở rộng URI template của mapping controller. Với item resource nằm dưới collection đó, có thể nối ID vào builder:

~~~java
Link item = entityLinks
    .linkFor(Order.class, customerId)
    .slash(orderId)
    .withSelfRel();
~~~

Cách này dựa trên quy ước collection path có tham số cha và item ID là path segment tiếp theo. Hãy kiểm thử mapping thực tế, đặc biệt khi route có nhiều path variable hoặc cấu trúc lồng nhau.

Với URI phức tạp không theo quy ước mà `ControllerEntityLinks` hỗ trợ, dùng `WebMvcLinkBuilder` cho endpoint cụ thể hoặc đăng ký một implementation `EntityLinks` riêng.

## 10. Giới hạn và cách mở rộng EntityLinks

`ControllerEntityLinks` dựa trên quy ước mapping nhất định. Controller cần:

1. Có `@ExposesResourceFor(DomainType.class)`.
2. Có mapping cấp lớp làm URI cơ sở của collection.
3. Có ít nhất một phương thức được ánh xạ để xử lý collection.
4. Có phương thức ánh xạ item resource với path variable định danh.

Nếu controller không tuân theo cấu trúc này, `EntityLinks` mặc định có thể không suy ra được link. Khi kiểu domain chưa được đăng ký hoặc implementation không hỗ trợ kiểu đó, lời gọi có thể ném `IllegalArgumentException`.

Có thể kiểm tra implementation hỗ trợ kiểu tài nguyên trước khi gọi:

~~~java
if (!entityLinks.supports(Order.class)) {
    throw new IllegalStateException(
        "No EntityLinks mapping registered for Order"
    );
}
~~~

### 10.1. EntityLinks là một SPI

`EntityLinks` là một Service Provider Interface. Cấu hình hypermedia mặc định cung cấp `DelegatingEntityLinks`, tập hợp các implementation được đăng ký trong ApplicationContext. `ControllerEntityLinks` là implementation cơ bản cho Spring MVC controller.

Ứng dụng có thể đăng ký implementation riêng khi URI được quản lý bởi một nguồn khác, ví dụ:

- Repository-based resource mapping.
- Một gateway hoặc API registry.
- Một cấu trúc URI nghiệp vụ không theo quy ước controller mặc định.
- Một hệ thống có nhiều kiểu biểu diễn cho cùng domain type.

Ví dụ cấu hình một implementation riêng:

~~~java
@Configuration
public class CustomEntityLinksConfiguration {

    @Bean
    CustomOrderEntityLinks customOrderEntityLinks() {
        return new CustomOrderEntityLinks();
    }
}
~~~

`CustomOrderEntityLinks` cần triển khai `EntityLinks` hoặc mở rộng một base implementation phù hợp. Khi được đăng ký đúng trong ApplicationContext, cơ chế delegate có thể chọn implementation hỗ trợ kiểu domain tương ứng.

Không cần tự viết implementation riêng nếu `ControllerEntityLinks` đã đáp ứng quy ước URI của ứng dụng.

### 10.2. Giới hạn với WebFlux

`EntityLinks` được thiết kế ban đầu cho Spring Web MVC. Spring HATEOAS hiện không cung cấp sẵn các implementation `EntityLinks` tương đương cho Spring WebFlux. Nếu ứng dụng dùng WebFlux, cần cân nhắc API link builder dành cho WebFlux hoặc một implementation phù hợp với kiến trúc reactive.

## 11. Kiểm thử EntityLinks

Kiểm thử nên xác nhận rằng domain type được ánh xạ đến đúng collection và item URI. Một integration test có thể khởi tạo ApplicationContext với hypermedia support và các controller đã đánh dấu.

~~~java
@SpringBootTest
class EntityLinksIntegrationTest {

    @Autowired
    EntityLinks entityLinks;

    @Test
    void createsItemLinkForOrderType() {
        Link link = entityLinks.linkToItemResource(
            Order.class,
            42L
        );

        assertThat(link.getHref()).endsWith("/orders/42");
    }

    @Test
    void createsCollectionLinkForOrderType() {
        Link link = entityLinks.linkToCollectionResource(Order.class);

        assertThat(link.getHref()).endsWith("/orders");
    }
}
~~~

Ví dụ giả định controller quản lý Order có mapping collection `/orders`, item `/orders/{id}`, và test context kích hoạt `@EnableHypermediaSupport`. Relation mặc định của link do implementation quyết định; nếu cần kiểm tra relation cụ thể, hãy đặt relation trong API hoặc kiểm tra theo hợp đồng mà ứng dụng công bố.

Các import chính:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;

import static org.assertj.core.api.Assertions.assertThat;
~~~

### 11.1. Kiểm thử trường hợp kiểu tài nguyên chưa được đăng ký

Nếu ứng dụng có nhiều domain type, nên kiểm tra kiểu nào được hỗ trợ:

~~~java
assertThat(entityLinks.supports(Order.class)).isTrue();
assertThat(entityLinks.supports(UnmappedResource.class)).isFalse();
~~~

Không nên chỉ kiểm tra response JSON có một trường href. Cần xác nhận link đến đúng mapping mà controller công bố, đặc biệt khi có nhiều controller và nhiều resource type.

### 11.2. Kiểm thử qua response HAL

Ngoài kiểm thử trực tiếp `EntityLinks`, có thể kiểm tra response của controller chứa relation và href mong đợi:

Giả sử test đã inject `MockMvc` và các service cần thiết đã được cấu hình hoặc mock:

~~~java
mvc.perform(get("/payments/{id}", paymentId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(endsWith("/payments/" + paymentId)))
    .andExpect(jsonPath("$._links.order.href")
        .value(endsWith("/orders/" + orderId)));
~~~

Các import thường dùng cho phần kiểm thử HTTP:

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Điều này xác nhận `EntityLinks` được tích hợp đúng vào controller hoặc assembler và link được serialize trong HAL như mong đợi.

## 12. Lỗi thường gặp khi sử dụng EntityLinks

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Quên `@ExposesResourceFor` | Controller không được nhận diện cho domain type | Đánh dấu controller quản lý tài nguyên |
| Chỉ khai báo item mapping, thiếu collection mapping | Không suy ra được collection resource theo quy ước | Công bố mapping collection |
| Không có method mapping với path variable cho item | Không tạo được item resource như mong đợi | Thêm mapping item có ID |
| Truyền DTO class thay vì domain type đã expose | Không tìm thấy mapping | Truyền đúng kiểu trong `@ExposesResourceFor` |
| Gọi EntityLinks khi hypermedia support chưa được kích hoạt | Không có bean hoặc không có ControllerEntityLinks | Cấu hình `@EnableHypermediaSupport` phù hợp |
| Dùng EntityLinks cho endpoint hành động tùy ý | Không biểu diễn đúng mapping action | Dùng `WebMvcLinkBuilder` cho method cụ thể |
| Cho rằng EntityLinks tự kiểm tra quyền | Client có thể thấy hoặc gọi hành động không phù hợp | Tạo link theo quyền và kiểm tra ở endpoint |
| Dùng ControllerEntityLinks cho WebFlux | Không có implementation mặc định tương ứng | Dùng API WebFlux hoặc custom implementation |
| Có nhiều controller expose cùng một domain type | Mapping có thể mơ hồ | Chọn một controller sở hữu resource hoặc dùng custom EntityLinks |

## 13. Quy trình áp dụng trong một API

Khi thêm `EntityLinks` vào ứng dụng Spring HATEOAS, có thể làm theo trình tự:

1. Xác định domain type mà API muốn công bố, ví dụ `Order.class`.
2. Đánh dấu controller quản lý kiểu đó bằng `@ExposesResourceFor(Order.class)`.
3. Khai báo mapping cấp lớp cho collection và mapping item có path variable.
4. Kích hoạt hypermedia support để Spring đăng ký `EntityLinks`.
5. Inject interface `EntityLinks` vào controller hoặc assembler.
6. Dùng `linkToCollectionResource` hoặc `linkFor` để tạo link collection.
7. Dùng `linkToItemResource` hoặc `linkForItemResource` để tạo link item.
8. Chọn relation phù hợp theo vị trí link trong representation.
9. Dùng `TypedEntityLinks` nếu cần tái sử dụng logic lấy ID.
10. Dùng `WebMvcLinkBuilder` cho các action endpoint không thuộc collection/item convention.
11. Kiểm thử domain type, href, relation và response HAL.
12. Dùng custom implementation nếu cấu trúc URI không phù hợp với ControllerEntityLinks mặc định.

## 14. Kết luận

`EntityLinks` cung cấp cách tạo link dựa trên kiểu domain thay vì phụ thuộc trực tiếp vào controller class. Với Spring MVC, `ControllerEntityLinks` đọc controller được đánh dấu bằng `@ExposesResourceFor`, kết hợp mapping collection và item để tạo URI. Các phương thức `linkToCollectionResource`, `linkToItemResource`, `linkFor` và `linkForItemResource` đáp ứng những nhu cầu tạo link phổ biến; `TypedEntityLinks` giúp tái sử dụng hàm lấy định danh.

Khi dùng `EntityLinks` trong controller hoặc assembler, một tài nguyên có thể tham chiếu đến tài nguyên khác mà không cần biết controller đích. Điều đó giúp giảm phụ thuộc giữa các controller và tập trung quy tắc định vị tài nguyên. Cần tuân theo cấu trúc mapping mà implementation hỗ trợ, kích hoạt hypermedia support, kiểm thử mapping và dùng `WebMvcLinkBuilder` hoặc custom implementation cho các trường hợp ngoài quy ước.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Using the EntityLinks interface](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.entity-links): kích hoạt EntityLinks, ControllerEntityLinks, TypedEntityLinks và SPI.
- [Spring HATEOAS API — EntityLinks](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/EntityLinks.html): các phương thức tạo link collection và item.
- [Spring HATEOAS API — ControllerEntityLinks](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/ControllerEntityLinks.html): quy ước mapping và cách controller được phát hiện.
- [Spring HATEOAS API — ExposesResourceFor](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/ExposesResourceFor.html): annotation công bố domain type mà controller quản lý.

