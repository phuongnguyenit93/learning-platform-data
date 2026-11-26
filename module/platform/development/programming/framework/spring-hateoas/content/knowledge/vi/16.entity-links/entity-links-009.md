# Kiểm thử EntityLinks

`EntityLinks` là abstraction của Spring HATEOAS dùng để tạo liên kết đến resource theo kiểu entity và định danh của nó. Thay vì tham chiếu trực tiếp một controller và handler như `WebMvcLinkBuilder`, code có thể yêu cầu link đến item hoặc collection bằng class của resource. Cách này giúp assembler tập trung vào mô hình tài nguyên mà không phụ thuộc chặt vào tên controller.

Vì link được suy ra từ mapping của controller, kiểm thử `EntityLinks` cần xác nhận cả hai điều: mapping được khai báo đúng để thư viện tìm thấy resource, và link tạo ra có URI/relation đúng như hợp đồng API. Kiểm thử unit với mock hữu ích để kiểm tra assembler gọi đúng abstraction; kiểm thử tích hợp với Spring context mới xác nhận được `EntityLinks` thật có thể phân giải mapping của ứng dụng.

## 1. EntityLinks làm gì?

`EntityLinks` nằm trong package `org.springframework.hateoas.server`. Các thao tác phổ biến gồm:

| Phương thức | Mục đích |
| --- | --- |
| `linkToItemResource(Order.class, id)` | Tạo link đến một order cụ thể theo định danh |
| `linkToCollectionResource(Order.class)` | Tạo link đến collection order |
| `linkToSearchResource(Order.class, searchName, ...)` | Tạo link đến search resource được công bố cho kiểu resource, nếu controller có mapping tương ứng |

Các phương thức này trả về một `LinkBuilder`. Có thể gắn relation bằng `withSelfRel()` hoặc `withRel(...)`, rồi thêm link vào `EntityModel`, `CollectionModel` hoặc kiểu kế thừa `RepresentationModel`.

Ví dụ:

```java
Link item = entityLinks
        .linkToItemResource(Order.class, orderId)
        .withSelfRel();

Link collection = entityLinks
        .linkToCollectionResource(Order.class)
        .withRel("orders");
```

`EntityLinks` thường được triển khai bởi `ControllerEntityLinks`, thành phần dò mapping controller để tìm nơi công bố resource. Controller cần chỉ rõ kiểu resource mà nó expose bằng `@ExposesResourceFor`.

## 2. Khai báo controller để EntityLinks tìm mapping

Ví dụ controller công bố resource `Order` tại `/orders`:

```java
import java.util.UUID;

import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    List<Order> all() {
        return orderService.findAll();
    }

    @GetMapping("/{id}")
    Order one(@PathVariable UUID id) {
        return orderService.getRequired(id);
    }
}
```

`@ExposesResourceFor(Order.class)` khai báo controller này đại diện cho resource `Order`. Mapping ở cấp lớp xác định đường dẫn collection; mapping item và path variable cung cấp đường dẫn đến một order cụ thể. Đây là thông tin để `ControllerEntityLinks` liên kết kiểu `Order` với endpoint tương ứng.

Trong ví dụ đầy đủ, cần import `java.util.List` và định nghĩa `Order`, `OrderService` theo ứng dụng. Các phương thức trả entity chỉ nhằm minh họa mapping; API thực tế thường trả DTO hoặc hypermedia representation để kiểm soát dữ liệu công khai.

## 3. Cấu hình HATEOAS trong test context

Khi dùng Spring Boot với starter HATEOAS, cấu hình tự động thường đăng ký hạ tầng hypermedia cho ứng dụng. Nếu cấu hình Spring thuần, có thể bật hỗ trợ hypermedia bằng `@EnableHypermediaSupport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HateoasConfiguration {
}
```

Kiểm thử tích hợp nên khởi tạo context có controller được đánh dấu `@ExposesResourceFor` và cấu hình HATEOAS tương ứng. Nếu chỉ mock `EntityLinks`, test không kiểm tra được việc phát hiện mapping, cách ghép path hoặc cấu hình thực tế.

## 4. Kiểm thử link item và collection bằng EntityLinks thật

Với ứng dụng Spring Boot, có thể dùng `@SpringBootTest` để inject `EntityLinks` thật:

```java
import java.net.URI;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class EntityLinksIntegrationTest {

    @Autowired
    EntityLinks entityLinks;

    @Test
    void createsSelfLinkForAnOrder() {
        UUID id = UUID.fromString(
                "f9b36b7a-9a10-4d21-9b53-0d9e8a2c0001");

        Link link = entityLinks
                .linkToItemResource(Order.class, id)
                .withSelfRel();

        URI uri = URI.create(link.getHref());

        assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
        assertThat(uri.getPath()).endsWith("/orders/" + id);
    }

    @Test
    void createsLinkForTheOrderCollection() {
        Link link = entityLinks
                .linkToCollectionResource(Order.class)
                .withRel("orders");

        URI uri = URI.create(link.getHref());

        assertThat(link.getRel().value()).isEqualTo("orders");
        assertThat(uri.getPath()).endsWith("/orders");
    }
}
```

Các assertion kiểm tra relation và path thay vì cố định toàn bộ host, scheme hoặc port. Khi test chạy trong request context, URI có thể chứa origin của môi trường test; khi không có request context, cách tạo URI còn phụ thuộc cấu hình link builder. Nếu hợp đồng yêu cầu link tuyệt đối, hãy bổ sung assertion cho `uri.isAbsolute()`, scheme và host trong một test có base URI được cấu hình rõ ràng.

Ví dụ giả định ứng dụng đã khởi tạo bean `EntityLinks`, controller `OrderController` và kiểu `Order`. Nếu test không tìm thấy mapping, hãy kiểm tra controller có nằm trong component scan/test context và có `@ExposesResourceFor(Order.class)` hay không.

## 5. Kiểm thử EntityLinks qua assembler

Trong ứng dụng, assembler thường dùng `EntityLinks` để tạo link cho representation:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    private final EntityLinks entityLinks;

    OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    EntityModel<OrderRepresentation> toModel(Order order) {
        Link self = entityLinks
                .linkToItemResource(Order.class, order.getId())
                .withSelfRel();

        Link orders = entityLinks
                .linkToCollectionResource(Order.class)
                .withRel("orders");

        return EntityModel.of(OrderRepresentation.from(order), self, orders);
    }
}
```

Có thể kiểm thử assembler theo hai mức:

- Unit test mock `EntityLinks` để xác nhận assembler yêu cầu đúng resource type và ID, sau đó thêm các link nhận được vào model.
- Integration test dùng `EntityLinks` thật để xác nhận mapping controller được phát hiện và URI được dựng đúng.

Hai mức test trả lời hai câu hỏi khác nhau. Unit test nhanh và cô lập, nhưng mock có thể được cấu hình trả về URI đúng ngay cả khi mapping thật bị sai. Integration test xác minh cấu hình và mapping thực tế, nhưng cần khởi tạo Spring context.

## 6. Unit test assembler với mock EntityLinks

Nếu chỉ muốn kiểm tra logic chuyển đổi của assembler, có thể mock `EntityLinks` và `LinkBuilder`. Ví dụ dùng Mockito:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.hateoas.server.LinkBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class OrderModelAssemblerTest {

    @Test
    void addsSelfLinkFromEntityLinks() {
        UUID id = UUID.randomUUID();
        EntityLinks entityLinks = mock(EntityLinks.class);
        LinkBuilder itemBuilder = mock(LinkBuilder.class);
        LinkBuilder collectionBuilder = mock(LinkBuilder.class);
        Link self = Link.of("/orders/" + id).withSelfRel();
        Link orders = Link.of("/orders").withRel("orders");

        when(entityLinks.linkToItemResource(Order.class, id))
                .thenReturn(itemBuilder);
        when(itemBuilder.withSelfRel()).thenReturn(self);
        when(entityLinks.linkToCollectionResource(Order.class))
                .thenReturn(collectionBuilder);
        when(collectionBuilder.withRel("orders")).thenReturn(orders);

        OrderModelAssembler assembler = new OrderModelAssembler(entityLinks);
        EntityModel<OrderRepresentation> model =
                assembler.toModel(OrderFixture.orderWithId(id));

        assertThat(model.getLink(IanaLinkRelations.SELF)).contains(self);
        verify(entityLinks).linkToItemResource(Order.class, id);
        verify(entityLinks).linkToCollectionResource(Order.class);
    }
}
```

`OrderFixture.orderWithId(...)` là fixture của dự án, cần tạo một order có đúng ID. Test này xác nhận assembler gọi `linkToItemResource` với `Order.class` và ID tương ứng, rồi gắn link `self` vào model. Do `EntityLinks` và `LinkBuilder` đều là mock, test này không xác nhận controller mapping thực tế.

Khi dùng Mockito với phiên bản Spring HATEOAS khác, cần kiểm tra kiểu trả về `LinkBuilder` trong dependency của dự án. Nếu API hoặc generic type thay đổi theo phiên bản, hãy điều chỉnh khai báo mock theo chữ ký thực tế thay vì ép kiểu không an toàn.

## 7. Kiểm thử response HAL bằng MockMvc

Kiểm thử `EntityLinks` ở mức context xác nhận URI builder, còn kiểm thử controller xác nhận link xuất hiện đúng trong response sau khi serialize. Với Spring MVC, dùng `MockMvc`:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerHateoasTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesSelfLinkForOrder() throws Exception {
        UUID id = UUID.fromString(
                "f9b36b7a-9a10-4d21-9b53-0d9e8a2c0001");

        mockMvc.perform(get("/orders/{id}", id)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href")
                        .value(endsWith("/orders/" + id)));
    }
}
```

Test cần có dữ liệu order tương ứng và service trả về resource đó. Nếu ứng dụng dùng database thật, có thể chuẩn bị dữ liệu trong fixture hoặc test setup; nếu dùng mock service, cấu hình service trả đúng order. Kiểm thử này đi qua controller, assembler, `EntityLinks` và HAL serializer nên phát hiện được lỗi ở nhiều lớp tích hợp.

## 8. Các trường hợp cần kiểm tra

Một bộ test tốt cho `EntityLinks` nên bao phủ các tình huống sau:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Item link | URI chứa đúng mapping item và ID |
| Collection link | URI trỏ đến mapping collection, không gắn ID item |
| Relation | `self` hoặc relation nghiệp vụ có giá trị đúng |
| Controller exposure | Controller được đánh dấu `@ExposesResourceFor` cho đúng class |
| Mapping thay đổi | Link mới phản ánh mapping thực tế sau khi cập nhật controller |
| Context path | URI có prefix triển khai đúng nếu ứng dụng dùng context path |
| HAL serialization | Link xuất hiện tại đúng vị trí `_links` trong response |
| Resource không tồn tại | Endpoint xử lý 404 hoặc phản hồi theo chính sách API; không nhầm lỗi dữ liệu với lỗi dựng link |

Nếu controller được đặt dưới `/api/v2/orders`, hãy kiểm tra link có prefix đó thay vì chỉ kiểm tra `/orders`. Nếu ứng dụng chạy sau reverse proxy, hãy kiểm thử forwarded headers theo cấu hình triển khai để link không lộ host nội bộ.

## 9. Kiểm thử collection và item không cùng một loại link

Một lỗi dễ gặp là tạo đúng link item nhưng dùng nhầm nó làm link collection. Có thể viết test riêng cho hai phương thức:

```java
@Test
void itemAndCollectionLinksHaveDifferentPaths() {
    UUID id = UUID.randomUUID();

    String itemPath = URI.create(entityLinks
            .linkToItemResource(Order.class, id)
            .withSelfRel().getHref()).getPath();

    String collectionPath = URI.create(entityLinks
            .linkToCollectionResource(Order.class)
            .withRel("orders").getHref()).getPath();

    assertThat(itemPath).endsWith("/orders/" + id);
    assertThat(collectionPath).endsWith("/orders");
}
```

Test này xác nhận hai loại link được tạo từ hai API khác nhau và trỏ đến đúng cấp tài nguyên. Nếu mapping item của ứng dụng không dùng `/{id}` hoặc collection có prefix khác, cập nhật assertion theo hợp đồng thực tế.

## 10. Lỗi thường gặp khi kiểm thử EntityLinks

**Chỉ mock EntityLinks rồi kết luận mapping đúng:** mock không chạy `ControllerEntityLinks`, vì vậy không phát hiện controller thiếu `@ExposesResourceFor` hoặc mapping sai. Hãy có ít nhất một integration test với bean thật.

**Controller không nằm trong test context:** `EntityLinks` không tìm thấy controller nếu controller không được component scan hoặc không được import vào context. Kiểm tra cấu hình test và package scan.

**Thiếu `@ExposesResourceFor`:** nếu controller không khai báo resource class, implementation mặc định có thể không biết controller đại diện cho kiểu entity nào. Đặt annotation trên controller phù hợp.

**So sánh toàn bộ URL tuyệt đối trong mọi môi trường:** host, port và scheme có thể khác giữa local, CI và production. Khi kiểm thử mapping, so sánh path và relation; chỉ kiểm tra origin khi test đã cấu hình base URI rõ ràng.

**Chỉ kiểm tra link tồn tại:** link có thể tồn tại nhưng sai ID hoặc sai relation. Xác nhận path, path variable và relation cụ thể.

**Nhầm lỗi endpoint với lỗi link builder:** nếu `EntityLinks` tạo link đúng nhưng request theo link trả 404, kiểm tra handler mapping và dữ liệu riêng. Hai vấn đề cần assertion riêng.

## 11. Checklist kiểm thử

- Controller khai báo `@ExposesResourceFor` với đúng kiểu resource.
- HATEOAS được cấu hình trong Spring test context.
- `EntityLinks` thật được inject trong integration test.
- Item link chứa đúng ID và mapping.
- Collection link trỏ đến collection endpoint.
- Relation được gắn đúng và ổn định.
- Assembler unit test xác nhận gọi đúng `EntityLinks` API.
- MockMvc test xác nhận link được serialize trong HAL response.
- Assertion tránh phụ thuộc host/port khi không cần kiểm tra origin.
- Có kiểm thử riêng cho context path hoặc reverse proxy nếu ứng dụng triển khai theo mô hình đó.

Kiểm thử `EntityLinks` cần xác nhận mối nối giữa kiểu resource, controller mapping và URI hypermedia mà client nhận được. Kết hợp unit test cho assembler với integration test dùng `EntityLinks` thật và kiểm thử HAL response sẽ giúp phát hiện cả lỗi logic dựng model lẫn lỗi cấu hình mapping trong ứng dụng Spring HATEOAS.
