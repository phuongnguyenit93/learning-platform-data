# Link builder trong Spring MVC với Spring HATEOAS

Một representation hypermedia cần công bố URI để client có thể đi tới tài nguyên hiện tại và các tài nguyên liên quan. Trong ứng dụng Spring MVC, cách tạo link nên dựa trên mapping của controller để URI phản ánh đúng cấu hình routing của ứng dụng. Spring HATEOAS cung cấp `WebMvcLinkBuilder` với hai API thường dùng là `linkTo(...)` và `methodOn(...)`.

`linkTo(...)` xác định phần URI gắn với controller hoặc method được tham chiếu. `methodOn(...)` tạo một proxy để mô tả lời gọi controller method; Spring HATEOAS đọc mapping annotation và tham số của lời gọi đó để xây URI. Controller method không được thực thi trong quá trình tạo link. Nhờ vậy, assembler có thể tạo link từ cùng nguồn mapping mà Spring MVC dùng để định tuyến request.

## 1. Vì sao dùng WebMvcLinkBuilder?

Giả sử API có endpoint đọc đơn hàng:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{orderId}")
    EntityModel<OrderView> one(
            @PathVariable("orderId") UUID orderId) {
        // Tải đơn hàng và trả representation.
    }
}
```

URI chi tiết được hình thành từ mapping cấp class `/orders` và mapping cấp method `/{orderId}`. Nếu tự nối chuỗi `"/orders/" + orderId`, assembler sẽ phải tự duy trì cùng quy tắc routing. Khi mapping đổi, các chuỗi URI thủ công có thể trở nên lỗi thời.

`WebMvcLinkBuilder` đọc mapping từ controller, ghép các thành phần URI và xử lý tham số theo quy tắc của Spring MVC. Điều này giúp link trong representation đi cùng cấu hình routing của controller.

## 2. Hai API chính: linkTo và methodOn

`WebMvcLinkBuilder` nằm trong package `org.springframework.hateoas.server.mvc`. Hai static method thường được import:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

`linkTo(...)` nhận controller class hoặc method invocation đã được tạo bởi `methodOn(...)`. `methodOn(...)` tạo proxy cho controller để ghi nhận method được tham chiếu và các tham số truyền vào.

Ví dụ tham chiếu method chi tiết:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();
```

Trong ví dụ, Spring HATEOAS đọc `@RequestMapping("/orders")`, `@GetMapping("/{orderId}")` và giá trị `orderId` để xây URI cho đơn hàng. `.withSelfRel()` gắn relation `self` cho chính tài nguyên đang được biểu diễn.

## 3. Dùng linkTo với controller class

Khi chỉ cần URI gốc được khai báo ở cấp controller, có thể truyền class trực tiếp vào `linkTo(...)`:

```java
Link orders = linkTo(OrderController.class)
        .withRel("orders");
```

Với controller khai báo `@RequestMapping("/orders")`, link sẽ trỏ tới đường dẫn collection gắn với controller. Cách này phù hợp khi muốn công bố một link tới resource root hoặc collection mà không cần chỉ rõ method.

Tuy nhiên, `linkTo(OrderController.class)` không thể hiện rõ một method cụ thể. Nếu controller có nhiều endpoint hoặc cần tham số path/query, hãy dùng `methodOn(...)` để tham chiếu method tương ứng.

## 4. Dùng methodOn để tham chiếu endpoint cụ thể

Ví dụ controller có endpoint collection và endpoint chi tiết:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        // Trả collection đơn hàng.
    }

    @GetMapping("/{orderId}")
    EntityModel<OrderView> one(
            @PathVariable("orderId") UUID orderId) {
        // Trả một đơn hàng.
    }
}
```

Assembler có thể tạo hai link:

```java
Link collection = linkTo(methodOn(OrderController.class).all())
        .withRel("orders");

Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();
```

Lời gọi `methodOn(OrderController.class).one(orderId)` không gọi logic tải đơn hàng. Nó chỉ tạo lời gọi proxy để Spring HATEOAS xác định method mapping và tham số cần đưa vào URI.

Đừng truyền một object domain lớn vào `methodOn(...)` nếu endpoint chỉ cần ID. Hãy truyền đúng các tham số mà mapping yêu cầu, đặc biệt là `@PathVariable` và `@RequestParam`.

## 5. Kết hợp mapping cấp class và cấp method

Spring MVC thường kết hợp `@RequestMapping` ở cấp class với mapping ở cấp method. `WebMvcLinkBuilder` cũng dựa trên cả hai phần đó.

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    EntityModel<OrderView> one(
            @PathVariable("orderId") UUID orderId) {
        // ...
    }
}
```

Khi gọi:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel();
```

URI được xây dựng từ `/api/orders` và `/{orderId}`. Nếu nhóm endpoint được chuyển sang prefix khác, thay đổi mapping tại controller sẽ được phản ánh vào link được tạo từ mapping đó.

Điều này cũng áp dụng với mapping có nhiều segment hoặc prefix phiên bản API. Hãy tránh lặp lại prefix như `/api/v1` trong assembler nếu controller đã khai báo mapping tương ứng.

## 6. Điền giá trị PathVariable

Khi endpoint khai báo `@PathVariable`, truyền giá trị tương ứng vào method proxy:

```java
@GetMapping("/{orderId}/items/{itemId}")
EntityModel<OrderItemView> item(
        @PathVariable("orderId") UUID orderId,
        @PathVariable("itemId") UUID itemId) {
    // ...
}
```

Tạo link:

```java
Link itemLink = linkTo(methodOn(OrderController.class)
        .item(orderId, itemId))
        .withRel("item");
```

Spring HATEOAS sử dụng tham số để mở rộng các path variable theo mapping. Việc này giúp URI được tạo nhất quán và tránh lỗi nối chuỗi, đặc biệt khi giá trị có ký tự cần URL encoding.

Tên tham số trong `@PathVariable("orderId")` nên được khai báo rõ nếu dự án không bảo đảm metadata tên tham số Java được giữ khi biên dịch. Điều đó giúp mapping và link builder không phụ thuộc vào cách compiler lưu tên biến.

## 7. Điền RequestParam vào link

Nếu controller method có `@RequestParam`, có thể tham chiếu method cùng giá trị query cần công bố:

```java
@GetMapping("/search")
CollectionModel<EntityModel<OrderView>> search(
        @RequestParam("status") OrderStatus status) {
    // ...
}
```

Tạo link tìm kiếm cho trạng thái cụ thể:

```java
Link pendingOrders = linkTo(methodOn(OrderController.class)
        .search(OrderStatus.PENDING))
        .withRel("pending-orders");
```

Giá trị query được cung cấp trong lời gọi proxy được đưa vào URI theo mapping của method. Dùng cách này khi muốn công bố một tìm kiếm cụ thể, có ngữ nghĩa rõ ràng với client.

Nếu muốn client tự chọn filter hoặc query value, hãy công bố endpoint tìm kiếm và mô tả tham số theo hợp đồng phù hợp; đừng tạo một link cố định với giá trị giả rồi kỳ vọng client biết cách thay đổi nó. Với tham số tùy chọn, chỉ truyền các giá trị thực sự muốn cố định trong link.

## 8. Ví dụ đầy đủ: assembler tạo self và association link

Giả sử representation đơn hàng cần có self link, link collection và link tới khách hàng:

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        OrderView view = new OrderView(
                order.getId(),
                order.getStatus().name(),
                order.getTotal()
        );

        Link self = linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel();

        Link customer = linkTo(methodOn(CustomerController.class)
                .one(order.getCustomer().getId())).withRel("customer");

        return EntityModel.of(view, self, customer);
    }
}
```

Assembler chuyển domain object thành DTO và dùng `WebMvcLinkBuilder` để tạo link dựa trên controller mapping. Relation `customer` là vocabulary của API, còn `href` được sinh từ method `CustomerController.one(...)`.

Nếu association khách hàng có thể null hoặc không được phép công bố, hãy kiểm tra điều kiện nghiệp vụ trước khi thêm link. Việc tạo link không thay thế authorization; endpoint khách hàng vẫn phải kiểm tra quyền truy cập khi request đến.

## 9. Thêm link vào RepresentationModel hoặc EntityModel

Các model của Spring HATEOAS cung cấp API để thêm link. Với model tự định nghĩa kế thừa `RepresentationModel`, có thể gọi `add(...)`:

```java
public class OrderModel extends RepresentationModel<OrderModel> {
    private UUID id;
    private String status;

    // Getter và setter.
}
```

Assembler có thể thêm link sau khi khởi tạo model:

```java
OrderModel model = new OrderModel();
model.setId(order.getId());
model.setStatus(order.getStatus().name());

model.add(linkTo(methodOn(OrderController.class)
        .one(order.getId())).withSelfRel());

return model;
```

Với DTO đã có sẵn, `EntityModel.of(content, links...)` thường gọn hơn. Dùng cách nào cũng được, miễn là model cuối cùng giữ đúng relation và URI theo hợp đồng API.

## 10. Tạo link collection và link item riêng biệt

Một response collection thường cần self link cho collection và mỗi item cần self link riêng. Có thể tạo collection link trong controller hoặc assembler collection:

```java
CollectionModel<EntityModel<OrderView>> model =
        orderAssembler.toCollectionModel(orderService.findAll());

Link self = linkTo(methodOn(OrderController.class).all())
        .withSelfRel();

model.add(self);
return model;
```

Trong đó, `PagedResourcesAssembler` phù hợp hơn nếu endpoint có phân trang vì nó tạo `PagedModel`, page metadata và các link điều hướng. Không tự tạo link `next`/`prev` bằng cách cộng page number nếu đã có cơ chế phân trang của Spring Data và Spring HATEOAS.

Hãy tránh thêm hai link `self` cùng ý nghĩa từ cả assembler item và controller collection. Mỗi representation cần một self link đúng với chính tài nguyên được biểu diễn.

## 11. URI được xây dựng dựa trên request hiện tại

Các phương thức `WebMvcLinkBuilder` thường dùng servlet request hiện tại làm cơ sở để xác định scheme, host, port và servlet mapping, sau đó kết hợp với mapping controller. Vì vậy, trong request MVC thực tế, link có thể phản ánh context path hoặc base URI của ứng dụng.

Điều này đặc biệt quan trọng khi ứng dụng chạy sau reverse proxy hoặc ingress. Nếu proxy thay đổi host, scheme hoặc prefix, cấu hình forwarded headers của Spring cần phù hợp để ứng dụng tạo URI công khai chính xác. Không nên tin forwarded header từ nguồn không đáng tin cậy; chỉ bật xử lý chúng trong môi trường proxy được kiểm soát.

Không hard-code `http://localhost:8080` hoặc hostname triển khai vào assembler. Dùng mapping controller và cấu hình request/proxy để URI được tạo theo môi trường thực tế.

## 12. Request context khi tạo link trong test

Vì link builder dựa trên servlet request hiện tại, gọi nó trong môi trường không có request context có thể gây lỗi hoặc tạo URI không như mong đợi. Các integration test dùng MockMvc thường cung cấp request context trong quá trình xử lý controller.

Ví dụ kiểm thử endpoint:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
            .value(endsWith("/orders/" + orderId)))
    .andExpect(jsonPath("$._links.customer.href")
            .value(endsWith("/customers/" + customerId)));
```

Nếu unit test gọi trực tiếp assembler mà không có servlet request, hãy thiết lập request context phù hợp trong test hoặc chuyển phần xác nhận URI sang MockMvc integration test. Đừng để test phụ thuộc vào một hostname ngẫu nhiên trên máy phát triển.

## 13. Kiểm thử link thay đổi theo mapping

Một lợi ích của link builder là link theo mapping controller. Có thể kiểm tra điều này bằng cách:

1. Xác nhận URI được tạo theo mapping hiện tại.
2. Thay đổi mapping trong một nhánh test hoặc cấu hình test có kiểm soát.
3. Xác nhận link mới phản ánh mapping mới.
4. Xác nhận relation như `self` hoặc `customer` vẫn ổn định.

Không cần viết test riêng cho mọi route nếu integration test đã xác nhận các controller mapping quan trọng. Nên tập trung vào các route có prefix, path variable, query parameter hoặc cấu hình proxy phức tạp.

## 14. Phân biệt WebMvcLinkBuilder với link builder của WebFlux

`WebMvcLinkBuilder` được thiết kế cho Spring MVC và dựa trên mô hình servlet request. Nếu ứng dụng dùng Spring WebFlux, hãy sử dụng `WebFluxLinkBuilder` cùng API reactive phù hợp.

Không dùng `WebMvcLinkBuilder` trong controller reactive chỉ vì tên method giống nhau. Hai stack có cơ chế request context và xử lý request khác nhau. Chọn builder tương ứng với web stack của ứng dụng.

## 15. Các lỗi thường gặp

**Nối chuỗi URI thủ công.** Mapping controller thay đổi có thể khiến link cũ sai. Dùng `linkTo(methodOn(...))` để xây URI từ mapping.

**Nhầm linkTo(Class) với methodOn.** `linkTo(Class)` thường phù hợp với mapping cấp controller; `methodOn` tham chiếu endpoint cụ thể cùng tham số.

**Nghĩ rằng methodOn thực thi controller.** Nó tạo proxy để ghi nhận lời gọi và mapping, không chạy logic endpoint.

**Truyền sai tham số path hoặc query.** Thứ tự và giá trị tham số phải khớp chữ ký method. Kiểm thử URI được tạo cho mapping có nhiều tham số.

**Dùng sai relation.** Link tới chính tài nguyên dùng `self`; link tới khách hàng hoặc collection dùng relation phù hợp như `customer` hoặc `orders`.

**Hard-code host và port.** Dùng request context và cấu hình forwarded header phù hợp với môi trường triển khai.

**Tạo link ngoài request context mà không chuẩn bị môi trường.** Dùng MockMvc hoặc thiết lập request context trong test.

**Dùng WebMvcLinkBuilder trong WebFlux.** Chọn `WebFluxLinkBuilder` cho ứng dụng reactive.

**Tạo lại pagination links thủ công.** Dùng `PagedResourcesAssembler` để page metadata và links nhất quán.

## 16. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng link cho API đơn hàng trong Spring MVC:

1. Tạo `OrderController` với mapping cấp class `/orders`.
2. Khai báo endpoint collection `GET /orders` và endpoint chi tiết `GET /orders/{orderId}`.
3. Dùng `linkTo(OrderController.class)` để tạo link tới mapping collection.
4. Dùng `linkTo(methodOn(OrderController.class).one(orderId))` để tạo self link cho đơn hàng.
5. Tạo `CustomerController` và thêm association link `customer` từ đơn hàng.
6. Tạo endpoint tìm kiếm nhận `@RequestParam` và tạo link với giá trị query cụ thể.
7. Chuyển mapping sang prefix `/api/orders` và xác nhận URI được tạo tự động cập nhật.
8. Kiểm thử response HAL bằng MockMvc.
9. Chạy ứng dụng sau reverse proxy trong môi trường test và xác nhận scheme/host/prefix nếu API công bố absolute URI.
10. Nếu dùng WebFlux, thay builder bằng API tương ứng của WebFlux.

Bạn đã nắm được link builder trong Spring MVC khi có thể dùng `linkTo(...)` cho mapping controller, dùng `methodOn(...)` cho endpoint cụ thể, truyền đúng path/query parameter, thêm link vào representation model và kiểm thử URI trong servlet request context. Cách làm này giúp hypermedia link luôn bám theo mapping Spring MVC và giảm sự phụ thuộc vào URI hard-code.

## Tài liệu tham khảo chính thức

- [Spring HATEOAS Reference Documentation – Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring HATEOAS Reference Documentation – WebFlux support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.webflux)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
