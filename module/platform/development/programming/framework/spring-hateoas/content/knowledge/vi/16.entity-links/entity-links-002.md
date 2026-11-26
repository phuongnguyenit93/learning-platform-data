# Link theo loại entity

Khi xây dựng REST API bằng Spring HATEOAS, nhiều nơi trong ứng dụng cần tạo liên kết tới cùng một loại tài nguyên. Ví dụ, controller thanh toán cần link tới đơn hàng; assembler hóa đơn cần link tới khách hàng; một phản hồi tổng hợp cần link tới collection sản phẩm. Nếu mỗi nơi phải biết class controller, mapping và cách ghép ID, mã nguồn sẽ phụ thuộc chặt vào cấu trúc web.

`EntityLinks` giải quyết vấn đề đó bằng cách tạo `Link` hoặc `LinkBuilder` dựa trên **loại entity/domain type**. Thay vì tham chiếu trực tiếp `OrderController`, thành phần gọi chỉ cần nói rằng nó muốn link tới tài nguyên `Order` hoặc một `Order` cụ thể. Spring HATEOAS tìm implementation phù hợp để chuyển yêu cầu đó thành URI theo mapping đã khai báo.

Bài học này thuộc chương **EntityLinks** trong module **SPRING_HATEOAS**, tập trung vào cách đánh dấu controller bằng `@ExposesResourceFor`, bật và inject `EntityLinks`, tạo link collection/item, dùng `TypedEntityLinks`, và mở rộng cơ chế bằng SPI.

Sau bài học, bạn có thể:

- Giải thích vì sao `EntityLinks` tạo liên kết theo kiểu entity thay vì controller.
- Cấu hình `@EnableHypermediaSupport` để inject `EntityLinks`.
- Khai báo controller tương thích với `ControllerEntityLinks` bằng `@ExposesResourceFor`.
- Dùng `linkToCollectionResource`, `linkToItemResource`, `linkFor` và `linkForItemResource`.
- Tập trung logic lấy ID bằng `TypedEntityLinks<T>`.
- Hiểu cách `DelegatingEntityLinks` chọn implementation và vai trò của `RepositoryEntityLinks`.
- Nhận biết giới hạn của `EntityLinks` và kiểm thử link theo loại entity.

## 1. Vì sao cần EntityLinks?

Giả sử ứng dụng có các tài nguyên `Order`, `Customer` và `Payment`. Một phản hồi thanh toán cần chứa liên kết tới đơn hàng liên quan. Nếu tự ghép URL, code có thể viết:

```java
Link orderLink = Link.of("/orders/" + orderId).withRel("order");
```

Đoạn code này biết trước cấu trúc `/orders/{id}`. Nếu controller đổi đường dẫn thành `/sales/orders/{id}`, mọi nơi ghép chuỗi đều cần được tìm và sửa. Dùng `WebMvcLinkBuilder` giúp tham chiếu mapping controller, nhưng thành phần gọi vẫn phải biết controller class.

`EntityLinks` thêm một mức trừu tượng: ánh xạ từ kiểu entity sang tài nguyên mà controller hoặc repository công bố.

```java
Link orderLink = entityLinks.linkToItemResource(Order.class, orderId)
        .withRel("order");
```

Đoạn code chỉ cần biết loại tài nguyên là `Order` và ID của nó. Cách ánh xạ từ `Order` sang URI được giao cho implementation của `EntityLinks`.

Điều này hữu ích khi:

- Nhiều controller hoặc assembler cần liên kết tới cùng một loại entity.
- Muốn tránh để controller nghiệp vụ phụ thuộc trực tiếp vào controller của tài nguyên đích.
- Đường dẫn được quản lý theo quy ước hoặc metadata repository.
- Muốn thay đổi cách ánh xạ URI bằng một implementation khác mà ít ảnh hưởng code gọi.

`EntityLinks` tạo URI theo loại entity; nó không truy vấn database, không kiểm tra entity có tồn tại và không thay thế service hoặc repository. Thành phần gọi vẫn chịu trách nhiệm lấy dữ liệu và xác định ID hợp lệ.

## 2. Bật hỗ trợ EntityLinks

Theo cấu hình Spring HATEOAS, `EntityLinks` được cung cấp thông qua dependency injection khi ứng dụng bật `@EnableHypermediaSupport` cho Spring MVC. Annotation này đăng ký các thành phần hạ tầng hypermedia, trong đó có `DelegatingEntityLinks` và các implementation phù hợp trong `ApplicationContext`.

Ví dụ bật HAL:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
```

Sau khi cấu hình, có thể inject interface `EntityLinks` vào controller, assembler hoặc service:

```java
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class PaymentLinkFactory {

    private final EntityLinks entityLinks;

    PaymentLinkFactory(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }
}
```

Nên phụ thuộc vào interface `EntityLinks` thay vì inject trực tiếp `ControllerEntityLinks`. Như vậy, code gọi không cần biết link được tạo từ controller mapping, repository mapping hay implementation tùy chỉnh.

## 3. Khai báo controller bằng ExposesResourceFor

Implementation mặc định `ControllerEntityLinks` tìm các controller Spring MVC có annotation `@ExposesResourceFor`. Annotation này khai báo loại domain/entity mà controller đang công bố tài nguyên collection và item.

Ví dụ controller quản lý `Order`:

```java
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/orders")
class OrderController {

    @GetMapping
    ResponseEntity<Void> all() {
        // Phần truy vấn và tạo CollectionModel được lược trong ví dụ mapping.
        return ResponseEntity.ok().build();
    }

    @GetMapping("/{id}")
    ResponseEntity<Void> one(@PathVariable("id") Long id) {
        // Phần truy vấn và tạo EntityModel được lược trong ví dụ mapping.
        return ResponseEntity.ok().build();
    }
}
```

Ví dụ thể hiện cấu trúc mapping mà `ControllerEntityLinks` cần nhận diện:

1. `@ExposesResourceFor(Order.class)` xác định controller này công bố tài nguyên `Order`.
2. `@RequestMapping("/orders")` xác định đường dẫn gốc của collection.
3. Method có `@GetMapping` gắn với class mapping, không thêm path segment, xử lý collection resource.
4. Method có `@GetMapping("/{id}")` xử lý item resource với ID trong `@PathVariable`.

Các phần thân phương thức ở trên được lược để tập trung vào quy ước mapping. Trong ứng dụng, hãy triển khai chúng bằng service và representation assembler tương ứng.

`ControllerEntityLinks` dựa trên quy ước URI collection và item. Nếu controller có cấu trúc đường dẫn khác, ví dụ item không nằm dưới collection path hoặc dùng nhiều biến path đặc biệt, hãy kiểm tra khả năng ánh xạ của implementation trước khi sử dụng. Không nên giả định mọi cấu trúc URL tùy ý đều có thể suy ra chỉ từ entity class.

## 4. Tạo link tới collection resource

Với loại entity, có thể tạo link tới collection bằng `linkToCollectionResource`:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;

Link collectionLink = entityLinks.linkToCollectionResource(Order.class);
```

Phương thức trả về một `Link` đã được tạo hoàn chỉnh. Relation do implementation quyết định và theo hợp đồng mặc định thường là `self`. Nếu link được thêm vào một representation khác với ý nghĩa “danh sách đơn hàng”, có thể thay relation:

```java
Link ordersLink = entityLinks.linkToCollectionResource(Order.class)
        .withRel("orders");
```

Khi cần tiếp tục xây dựng URI trước khi tạo link, dùng `linkFor` để nhận `LinkBuilder`:

```java
import org.springframework.hateoas.server.LinkBuilder;

LinkBuilder ordersBuilder = entityLinks.linkFor(Order.class);
Link ordersLink = ordersBuilder.withRel("orders");
```

`linkFor(Order.class)` hướng tới collection resource và yêu cầu mapping của controller đã được mở rộng đầy đủ, không còn path variable chưa có giá trị. API cũng có overload `linkFor(Class<?>, Object... parameters)` để truyền các tham số cần mở rộng trong URI template của mapping.

Phân biệt hai nhóm phương thức:

- `linkFor...` trả `LinkBuilder`, phù hợp khi cần nối thêm path segment hoặc tùy chỉnh link trước khi hoàn tất.
- `linkTo...` trả `Link`, phù hợp khi đã biết đích cần tạo.

## 5. Tạo link tới item resource

Để tạo link tới một đối tượng cụ thể, cần có loại entity và ID của đối tượng:

```java
Link orderLink = entityLinks.linkToItemResource(Order.class, 42L);
```

Theo quy ước của `ControllerEntityLinks`, link sẽ trỏ tới item resource tương ứng, ví dụ `/orders/42`. Relation mặc định của link được implementation xác định và thường là `self`.

Nếu muốn tùy chỉnh relation khi thêm vào một biểu diễn khác:

```java
Link relatedOrder = entityLinks
        .linkToItemResource(Order.class, 42L)
        .withRel("order");
```

Hoặc lấy builder để tiếp tục mở rộng:

```java
import org.springframework.hateoas.server.LinkBuilder;

LinkBuilder orderBuilder = entityLinks.linkForItemResource(Order.class, 42L);
Link self = orderBuilder.withSelfRel();
```

Trong thực tế, nên dùng `linkToItemResource` khi chỉ cần một link hoàn chỉnh. Chỉ dùng `linkForItemResource` nếu còn cần nối thêm segment, query parameter hoặc tùy chỉnh builder.

### Gắn link entity vào một representation khác

Một controller có thể trả về thông tin thanh toán cùng liên kết tới đơn hàng mà không cần tham chiếu `OrderController`:

```java
import java.math.BigDecimal;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

record PaymentResponse(Long id, Long orderId, BigDecimal amount) {}

@Component
class PaymentRepresentationFactory {

    private final EntityLinks entityLinks;

    PaymentRepresentationFactory(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    EntityModel<PaymentResponse> toModel(PaymentResponse payment) {
        return EntityModel.of(
                payment,
                entityLinks.linkToItemResource(Order.class, payment.orderId())
                        .withRel("order")
        );
    }
}
```

`PaymentRepresentationFactory` chỉ biết `Order.class` và ID lấy từ `PaymentResponse`. Đường dẫn `/orders/{id}` được phân giải bởi implementation đang quản lý entity đó. Cách này giảm phụ thuộc giữa module thanh toán và controller đơn hàng.

## 6. Tập trung cách lấy ID bằng TypedEntityLinks

Nếu nhiều chỗ đều phải gọi `linkToItemResource(entity, entity.getId())`, có thể tập trung hàm lấy ID bằng `TypedEntityLinks<T>`. `EntityLinks.forType(...)` tạo một đối tượng đã biết loại entity và identifier extractor.

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.TypedEntityLinks;

class OrderLinkFactory {

    private final TypedEntityLinks<Order> orderLinks;

    OrderLinkFactory(EntityLinks entityLinks) {
        this.orderLinks = entityLinks.forType(Order::getId);
    }

    Link selfLink(Order order) {
        return orderLinks.linkToItemResource(order);
    }
}
```

Ở constructor, `Order::getId` được đăng ký một lần. Các lần gọi sau chỉ cần truyền đối tượng `Order`; không phải truyền ID riêng hoặc lặp lại extractor.

`TypedEntityLinks<T>` cũng cung cấp `linkForItemResource(entity)` nếu cần `LinkBuilder` thay vì link hoàn chỉnh. API có overload `forType(Class<T>, Function<T, Object>)` khi muốn chỉ rõ kiểu entity thay vì để compiler suy luận từ extractor.

Typed links đặc biệt hữu ích khi:

- Một assembler tạo link cho nhiều đơn hàng.
- Có nhiều kiểu ID hoặc cách lấy ID khác nhau.
- Muốn gom quy tắc tạo link vào một factory theo từng domain type.
- Muốn giảm lặp code và hạn chế truyền nhầm ID của loại entity khác.

Identifier extractor chỉ chịu trách nhiệm lấy ID từ đối tượng. Nó không kiểm tra ID có tồn tại trong database hay không và cũng không tải entity từ repository.

## 7. EntityLinks và LinkBuilder API

Các phương thức chính của `EntityLinks` có thể nhóm theo loại kết quả:

| Phương thức | Đầu vào | Kết quả | Mục đích |
|---|---|---|---|
| `linkFor(type)` | Entity class | `LinkBuilder` | Bắt đầu xây link tới collection resource. |
| `linkFor(type, parameters...)` | Entity class và tham số mapping | `LinkBuilder` | Mở rộng URI template của mapping. |
| `linkForItemResource(type, id)` | Entity class và ID | `LinkBuilder` | Bắt đầu xây link tới item resource. |
| `linkToCollectionResource(type)` | Entity class | `Link` | Tạo link hoàn chỉnh tới collection. |
| `linkToItemResource(type, id)` | Entity class và ID | `Link` | Tạo link hoàn chỉnh tới item. |
| `forType(extractor)` | Hàm lấy ID | `TypedEntityLinks<T>` | Tạo API typed dùng lại extractor. |

Ví dụ sử dụng cả collection và item:

```java
Link orders = entityLinks.linkToCollectionResource(Order.class)
        .withRel("orders");

Link order = entityLinks.linkToItemResource(Order.class, orderId)
        .withSelfRel();

model.add(orders, order);
```

Lưu ý relation của link phụ thuộc mục đích biểu diễn. Link tới collection có thể mang `self` khi collection chính là tài nguyên đang được biểu diễn, hoặc mang relation nghiệp vụ như `orders` khi nó là một liên kết từ tài nguyên khác. Không nên dùng cùng một relation cho các ý nghĩa khác nhau.

## 8. ControllerEntityLinks và quy ước URI

`ControllerEntityLinks` là implementation mặc định dựa trên Spring MVC controller. Nó kiểm tra controller được đánh dấu bằng `@ExposesResourceFor` và suy ra collection/item resource từ mapping.

Một controller phù hợp với quy ước cơ bản có dạng:

```java
import org.springframework.http.ResponseEntity;

@RestController
@ExposesResourceFor(Customer.class)
@RequestMapping("/customers")
class CustomerController {

    @GetMapping
    ResponseEntity<Void> all() {
        // Phần xử lý collection được lược trong ví dụ mapping.
        return ResponseEntity.ok().build();
    }

    @GetMapping("/{id}")
    ResponseEntity<Void> one(@PathVariable("id") Long id) {
        // Phần xử lý item được lược trong ví dụ mapping.
        return ResponseEntity.ok().build();
    }
}
```

Khi `EntityLinks` được bật, các thành phần khác có thể tạo link bằng `Customer.class` mà không cần biết controller tên gì. Nếu đường dẫn collection thay đổi từ `/customers` sang `/clients`, việc cập nhật mapping controller được phản ánh trong link do implementation phân giải.

Các điểm cần giữ đúng:

- `@ExposesResourceFor` phải trỏ tới domain type mà controller thực sự quản lý.
- Class-level mapping xác định collection resource.
- Item mapping phải mở rộng collection path và nhận ID bằng path variable.
- Controller phải nằm trong `ApplicationContext` mà `EntityLinks` đang quét.
- Nếu có nhiều controller cùng công bố một entity type hoặc mapping không theo quy ước, cần xem xét implementation tùy chỉnh để tránh ánh xạ mơ hồ.

## 9. EntityLinks như một SPI

`EntityLinks` không chỉ là tiện ích gắn với controller. Nó còn là một SPI (*Service Provider Interface*) cho phép nhiều implementation cùng tham gia tạo link.

Khi `@EnableHypermediaSupport` đăng ký hạ tầng, bean được inject dưới dạng `EntityLinks` thường là `DelegatingEntityLinks`. Nó ủy quyền yêu cầu cho các implementation đã đăng ký trong `ApplicationContext`. `ControllerEntityLinks` là implementation mặc định cho controller Spring MVC; ứng dụng có thể bổ sung implementation riêng bằng cách đăng ký bean.

Ví dụ minh họa một implementation tùy chỉnh được đăng ký:

```java
@Configuration
class CustomEntityLinksConfiguration {

    @Bean
    CustomOrderEntityLinks customOrderEntityLinks(/* dependencies */) {
        return new CustomOrderEntityLinks(/* dependencies */);
    }
}
```

`CustomOrderEntityLinks` cần triển khai `EntityLinks` hoặc kế thừa một lớp cơ sở thích hợp, đồng thời định nghĩa cách tạo link cho loại entity mà nó hỗ trợ. `DelegatingEntityLinks` sử dụng cơ chế plugin để chọn implementation có `supports(type)` phù hợp.

SPI hữu ích khi:

- URI được lưu trong metadata hoặc cấu hình thay vì annotation controller.
- Tài nguyên được phục vụ bởi hệ thống ngoài hoặc gateway.
- Một số domain type có cấu trúc URI khác quy ước mặc định.
- Cần thay đổi cách tạo link mà không sửa các thành phần đang inject `EntityLinks`.

Không nên viết implementation tùy chỉnh nếu `ControllerEntityLinks` đã đáp ứng quy ước mapping của ứng dụng. Một SPI riêng cần có kiểm thử cho loại entity được hỗ trợ, loại không hỗ trợ và trường hợp mapping không hợp lệ.

## 10. Tích hợp với Spring Data REST qua RepositoryEntityLinks

Spring Data REST cung cấp `RepositoryEntityLinks`, một implementation của `EntityLinks` có thể tạo link dựa trên mapping repository. Điều này khác với `ControllerEntityLinks`, vốn đọc mapping của controller Spring MVC.

`RepositoryEntityLinks` phù hợp khi tài nguyên được export bởi Spring Data REST và cần tạo link tới collection, item, trang hoặc search resource theo cấu hình repository. Nó hiểu các tùy chỉnh như đường dẫn repository và ID converter mà một implementation chỉ nhìn controller không thể tự suy ra.

Trong ứng dụng có Spring Data REST, có thể inject implementation chuyên biệt khi cần API mở rộng của nó:

```java
import org.springframework.hateoas.Link;
import org.springframework.data.rest.webmvc.support.RepositoryEntityLinks;
import org.springframework.stereotype.Component;

@Component
class RepositoryLinkFactory {

    private final RepositoryEntityLinks repositoryLinks;

    RepositoryLinkFactory(RepositoryEntityLinks repositoryLinks) {
        this.repositoryLinks = repositoryLinks;
    }

    Link productSearchLink() {
        return repositoryLinks.linkToCollectionResource(Product.class);
    }
}
```

Ví dụ minh họa việc tạo link collection cho repository export. `RepositoryEntityLinks` còn có các API riêng để tạo link tới paged resource và search resource. Nếu chỉ cần các thao tác chung của `EntityLinks`, hãy phụ thuộc interface; chỉ inject `RepositoryEntityLinks` khi thật sự cần chức năng đặc thù của Spring Data REST.

## 11. Giới hạn và lưu ý khi sử dụng

`EntityLinks` hiện hướng tới Spring MVC. Tài liệu Spring HATEOAS 3.1.2 nêu rõ các implementation và SPI này chưa được cung cấp sẵn cho Spring WebFlux vì hợp đồng ban đầu được thiết kế quanh Spring MVC và chưa mô hình hóa kiểu reactive. Nếu ứng dụng dùng WebFlux, hãy dùng cơ chế link builder tương ứng của WebFlux hoặc tự thiết kế abstraction phù hợp.

Ngoài ra, cần lưu ý:

- **Không truy vấn dữ liệu:** `EntityLinks` chỉ tạo link; service/repository vẫn lấy entity.
- **Không xác nhận tài nguyên tồn tại:** có thể tạo URI từ type và ID ngay cả khi ID không tồn tại. Endpoint đích vẫn phải xử lý `404`.
- **Không thay thế phân quyền:** link được công bố không phải cơ chế kiểm soát truy cập. Endpoint đích phải kiểm tra quyền khi request đến.
- **Phụ thuộc mapping đã đăng ký:** với `ControllerEntityLinks`, controller phải có `@ExposesResourceFor` và cấu trúc mapping phù hợp.
- **Không nên phụ thuộc implementation cụ thể nếu không cần:** inject `EntityLinks` giúp giữ code linh hoạt hơn.
- **Relation cần rõ ràng:** link builder tạo URI, còn relation vẫn phải được chọn theo ý nghĩa của biểu diễn.

## 12. Kiểm thử EntityLinks

Kiểm thử nên xác nhận `EntityLinks` được inject, tìm đúng mapping theo entity type và tạo đúng URI cho collection/item. Với MockMvc, có thể kiểm tra link được gắn vào phản hồi.

Ví dụ controller khác dùng `EntityLinks` để trả thông tin đơn hàng liên quan:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record PaymentPreview(Long orderId) {}

@RestController
@RequestMapping("/payment-previews")
class PaymentPreviewController {

    private final EntityLinks entityLinks;

    PaymentPreviewController(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    @GetMapping("/{orderId}")
    EntityModel<PaymentPreview> preview(@PathVariable Long orderId) {
        PaymentPreview content = new PaymentPreview(orderId);

        return EntityModel.of(
                content,
                entityLinks.linkToItemResource(Order.class, orderId)
                        .withRel("order")
        );
    }
}
```

Kiểm thử phản hồi HAL:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EntityLinksIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void paymentPreviewContainsLinkToOrderItem() throws Exception {
        mockMvc.perform(get("/payment-previews/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.order.href", endsWith("/orders/42")));
    }
}
```

Ví dụ giả định `OrderController` đã được đánh dấu `@ExposesResourceFor(Order.class)`, cấu hình `@EnableHypermediaSupport` đã được bật, và `PaymentPreview` là DTO có constructor nhận `orderId`. Không cần cố định host hoặc port trong assertion; kiểm tra phần path giúp test ít phụ thuộc môi trường hơn.

Ngoài kiểm thử HTTP, có thể kiểm tra trực tiếp các trường hợp:

- `linkToCollectionResource(Order.class)` tạo URI collection đúng.
- `linkToItemResource(Order.class, 42L)` tạo URI item đúng.
- `TypedEntityLinks<Order>` lấy đúng ID từ đối tượng.
- Một entity type không được implementation hỗ trợ tạo lỗi phù hợp, thay vì trả link sai.
- Mapping controller đổi thì link mới phản ánh mapping đã cập nhật.
- Nếu có custom implementation, `supports(type)` chọn đúng implementation.

## 13. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Quên `@ExposesResourceFor` | `ControllerEntityLinks` không nhận diện entity type của controller. | Đánh dấu controller bằng annotation đúng domain type. |
| Controller không theo quy ước collection/item | Link item có thể không được suy ra đúng. | Dùng mapping collection và method item có path variable theo quy ước. |
| Nhầm `linkFor` với `linkTo` | Code dùng sai kiểu builder hoặc link hoàn chỉnh. | Nhớ `linkFor...` trả `LinkBuilder`, `linkTo...` trả `Link`. |
| Gọi link item mà không truyền ID | Không thể xác định URI của item cụ thể. | Dùng overload có ID hoặc `TypedEntityLinks` với extractor. |
| Lặp lại `entity.getId()` ở nhiều nơi | Code dễ sai khi đổi cách lấy identifier. | Dùng `forType(Order::getId)`. |
| Inject `ControllerEntityLinks` ở mọi nơi | Thành phần nghiệp vụ bị khóa vào implementation controller. | Inject interface `EntityLinks`. |
| Cho rằng EntityLinks kiểm tra entity tồn tại | Link có thể trỏ tới ID không tồn tại. | Dùng service/repository và để endpoint xử lý `404`. |
| Dùng EntityLinks cho WebFlux | Không có implementation mặc định tương ứng trong Spring HATEOAS hiện hành. | Dùng API reactive phù hợp hoặc abstraction riêng. |

## 14. Quy trình áp dụng

Khi cần tạo link theo loại entity, thực hiện theo trình tự:

1. Xác định domain type mà controller hoặc repository công bố.
2. Nếu dùng Spring MVC controller, đánh dấu bằng `@ExposesResourceFor` và khai báo mapping collection/item theo quy ước.
3. Bật `@EnableHypermediaSupport` để đăng ký hạ tầng và inject `EntityLinks`.
4. Dùng `linkToCollectionResource` cho collection hoặc `linkToItemResource` cho một item.
5. Dùng `linkFor` hoặc `linkForItemResource` nếu cần tiếp tục tùy chỉnh URI bằng builder.
6. Dùng `forType` để tập trung identifier extractor khi tạo nhiều link cho cùng loại entity.
7. Nếu URI dựa trên repository mapping, cân nhắc `RepositoryEntityLinks`; nếu có cấu trúc riêng, đăng ký implementation SPI phù hợp.
8. Kiểm thử collection URI, item URI, relation và trường hợp entity type không được hỗ trợ.

`EntityLinks` giúp ứng dụng yêu cầu liên kết theo ngôn ngữ domain thay vì theo tên controller hoặc chuỗi URL. Khi mapping được khai báo đúng và implementation được chọn phù hợp, các thành phần như assembler, payment service hoặc controller tổng hợp có thể tạo link nhất quán tới collection và item, đồng thời giảm phụ thuộc vào cấu trúc web nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS – Using the EntityLinks interface](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.entity-links)
- [Spring HATEOAS – EntityLinks API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/EntityLinks.html)
- [Spring HATEOAS – ControllerEntityLinks API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/ControllerEntityLinks.html)
- [Spring HATEOAS – ExposesResourceFor API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/ExposesResourceFor.html)
- [Spring HATEOAS – TypedEntityLinks API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/TypedEntityLinks.html)
- [Spring Data REST – RepositoryEntityLinks API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/support/RepositoryEntityLinks.html)
