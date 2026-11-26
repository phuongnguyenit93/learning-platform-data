# Giới hạn của EntityLinks trong Spring HATEOAS

`EntityLinks` là một abstraction của Spring HATEOAS giúp tạo liên kết đến tài nguyên item và collection dựa trên kiểu tài nguyên. Nó hữu ích khi ứng dụng muốn tạo link mà không cần tham chiếu trực tiếp đến class controller. Tuy nhiên, abstraction này chỉ giải quyết một phần bài toán xây dựng hypermedia.

`EntityLinks` không tự hiểu toàn bộ quy trình nghiệp vụ, không quyết định người dùng có được phép thực hiện hành động hay không và cũng không mô tả đầy đủ HTTP method hoặc dữ liệu đầu vào của một thao tác. Khi API có route tùy biến, tài nguyên lồng nhau hoặc hành động phụ thuộc trạng thái, cần kết hợp nó với các công cụ và logic biểu diễn khác của Spring HATEOAS.

## 1. EntityLinks giải quyết bài toán nào?

Trong một API theo quy ước tài nguyên, thường có endpoint cho collection và item:

~~~http
GET /orders
GET /orders/42
~~~

Nếu muốn tạo link đến hai loại tài nguyên trên, code có thể tham chiếu controller trực tiếp bằng `WebMvcLinkBuilder`. Nhưng trong một số trường hợp, assembler chỉ cần biết kiểu tài nguyên và ID, không cần biết controller nào đang triển khai route.

`EntityLinks` cung cấp abstraction cho tình huống này:

~~~java
Link item = entityLinks.linkToItemResource(Order.class, order.getId());
Link collection = entityLinks.linkToCollectionResource(Order.class);
~~~

Hai lời gọi biểu đạt ý định ở mức tài nguyên:

- `linkToItemResource(...)` tạo link đến một item cụ thể.
- `linkToCollectionResource(...)` tạo link đến collection của kiểu tài nguyên đó.

Ứng dụng có thể gắn relation sau khi tạo link:

~~~java
Link self = entityLinks
    .linkToItemResource(Order.class, order.getId())
    .withSelfRel();

Link orders = entityLinks
    .linkToCollectionResource(Order.class)
    .withRel(IanaLinkRelations.COLLECTION);
~~~

Cách làm này giảm phụ thuộc trực tiếp vào tên controller và phương thức. Tuy nhiên, nó dựa trên metadata và quy ước mà implementation của `EntityLinks` có thể nhận diện.

## 2. Controller cần công bố loại tài nguyên

Với implementation dựa trên Spring MVC controller, `@ExposesResourceFor` cho biết controller đang công bố loại tài nguyên nào. Controller cũng cần mapping phản ánh collection và item route.

~~~java
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
public class OrderController {

    @GetMapping
    public CollectionModel<OrderDto> all() {
        // Trả về collection đơn hàng.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }

    @GetMapping("/{id}")
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        // Trả về một đơn hàng.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}
~~~

Sau khi controller được cấu hình để expose `Order.class`, thành phần tạo link có thể dùng kiểu `Order.class` làm khóa để tìm mapping phù hợp.

Ví dụ inject abstraction vào assembler:

~~~java
@Component
public class OrderLinks {

    private final EntityLinks entityLinks;

    public OrderLinks(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    public Link self(Order order) {
        return entityLinks
            .linkToItemResource(Order.class, order.getId())
            .withSelfRel();
    }

    public Link collection() {
        return entityLinks
            .linkToCollectionResource(Order.class)
            .withRel(IanaLinkRelations.COLLECTION);
    }
}
~~~

Ví dụ tập trung vào cách dùng API. Ứng dụng cần bật cấu hình hypermedia phù hợp và bảo đảm implementation `EntityLinks` được đăng ký trong application context. Chi tiết cấu hình có thể khác theo phiên bản Spring HATEOAS và loại web stack đang sử dụng.

## 3. Giới hạn ở mô hình item và collection

Điểm mạnh của `EntityLinks` cũng là phạm vi giới hạn của nó: abstraction được thiết kế quanh việc định vị item resource và collection resource theo kiểu tài nguyên.

Nó phù hợp với các đường dẫn có hình dạng tương đối chuẩn:

~~~text
/orders
/orders/42
~~~

Nhưng nhiều API có route diễn đạt ngữ cảnh nghiệp vụ phức tạp hơn:

~~~text
/orders/42/items
/orders/42/items/3
/orders/42/cancellations
/customers/7/orders
/reports/monthly
~~~

Những route này có thể phụ thuộc nhiều tham số, quan hệ cha-con, truy vấn hoặc một hành động cụ thể. Một kiểu domain như `Order.class` không đủ để mô tả mọi route có thể liên quan đến đơn hàng.

Ví dụ, `linkToCollectionResource(Order.class)` có thể tạo link đến collection đơn hàng, nhưng không thể tự suy ra rằng trong một ngữ cảnh cụ thể, máy khách cần collection đơn hàng của khách hàng số 7 tại `/customers/7/orders`.

Với route phụ thuộc nhiều tham số hoặc một phương thức cụ thể, nên tham chiếu trực tiếp controller method bằng `WebMvcLinkBuilder`:

~~~java
Link customerOrders = linkTo(
    methodOn(CustomerOrderController.class).orders(customerId)
).withRel("https://api.example.com/rels/customer-orders");
~~~

Cách này diễn đạt rõ endpoint và tham số cần thiết. `EntityLinks` vẫn có thể dùng cho link item/collection chuẩn, còn link route đặc thù được tạo bằng builder phù hợp.

## 4. Không tự tạo link cho mọi hành động nghiệp vụ

Một tài nguyên có thể có nhiều hành động: hủy đơn, xác nhận thanh toán, hoàn tiền, gửi lại hóa đơn hoặc cập nhật địa chỉ giao hàng. Những hành động này không nhất thiết tương ứng với một item hay collection resource.

Ví dụ:

~~~http
POST /orders/42/cancel
POST /payments/91/refunds
PATCH /orders/42/shipping-address
~~~

`EntityLinks` không thể tự suy ra các endpoint hành động này chỉ từ `Order.class` hoặc `Payment.class`. Nó cũng không biết HTTP method, request body hay điều kiện nghiệp vụ của từng thao tác.

Hãy dùng link builder tham chiếu phương thức controller hoặc tạo link tường minh:

~~~java
Link cancel = linkTo(
    methodOn(OrderController.class).cancel(order.getId())
).withRel("https://api.example.com/rels/cancel");
~~~

Nếu cần công bố thêm HTTP method và dữ liệu đầu vào, có thể dùng affordance và một định dạng hypermedia hỗ trợ affordance, chẳng hạn HAL-FORMS. Một link thông thường chỉ cung cấp đích đến và relation; relation cần được tài liệu hóa để máy khách biết ý nghĩa thao tác.

## 5. Không biết trạng thái nghiệp vụ để quyết định link

`EntityLinks` tạo link dựa trên loại tài nguyên và mapping. Nó không tự kiểm tra đơn hàng có thể hủy hay không, thanh toán đã được xác nhận chưa hoặc người dùng đã hoàn thành bước xác minh nào.

Ví dụ, chỉ đơn hàng ở trạng thái `PENDING` mới có thể hủy:

~~~java
EntityModel<OrderDto> model = EntityModel.of(mapper.toDto(order));

model.add(orderLinks.self(order));

if (order.canBeCancelled()) {
    model.add(
        linkTo(methodOn(OrderController.class).cancel(order.getId()))
            .withRel("https://api.example.com/rels/cancel")
    );
}
~~~

Ở đây, `EntityLinks` có thể tạo link self. Điều kiện `canBeCancelled()` đến từ domain/service quyết định link hủy có xuất hiện trong biểu diễn hay không.

Cần giữ hai trách nhiệm riêng:

- EntityLinks định vị tài nguyên theo mapping.
- Domain/service hoặc policy layer xác định hành động nào khả dụng trong trạng thái hiện tại.

Không nên thêm link hành động chỉ vì endpoint tồn tại. Máy khách cần nhận được tập link phản ánh đúng ngữ cảnh nghiệp vụ mà API công bố.

## 6. Không thay thế authorization và bảo mật

Sự hiện diện hoặc vắng mặt của link không phải cơ chế phân quyền. Nếu API không trả về link hủy, một máy khách vẫn có thể thử gửi request trực tiếp đến URI của endpoint hủy.

Endpoint đích phải tự xác thực và kiểm tra quyền:

~~~java
@PostMapping("/{id}/cancel")
public EntityModel<OrderDto> cancel(@PathVariable Long id) {
    Order order = orderService.findById(id);

    authorizationService.assertCanCancel(order);
    Order updated = orderService.cancel(order);

    return orderAssembler.toModel(updated);
}
~~~

Đoạn code minh họa việc kiểm tra quyền trước khi thực hiện thao tác. Kiểm tra thực tế có thể nằm trong service, method security hoặc policy layer tùy kiến trúc ứng dụng.

Cần kiểm tra ít nhất:

- Người gọi đã được xác thực chưa?
- Người gọi có quyền trên đúng đối tượng này không?
- Đối tượng có thuộc tenant hoặc phạm vi dữ liệu của người gọi không?
- Trạng thái hiện tại có cho phép thao tác không?
- Request có đáp ứng các điều kiện nghiệp vụ khác không?

`EntityLinks` không thay thế bất kỳ bước nào trong số đó. Nó chỉ hỗ trợ tạo địa chỉ liên kết.

## 7. Phụ thuộc vào metadata controller và quy ước mapping

Khả năng tạo link của implementation dựa trên controller phụ thuộc vào việc controller được khai báo nhất quán và framework có thể nhận diện mapping.

Một số tình huống có thể gây khó khăn:

- Controller không khai báo loại tài nguyên bằng annotation cần thiết.
- Mapping item hoặc collection không theo quy ước mà implementation hỗ trợ.
- Có nhiều controller cùng expose một kiểu domain.
- Route cần tham số cha hoặc tham số bổ sung mà abstraction không thể suy ra.
- Mapping được tạo động hoặc phụ thuộc cấu hình đặc biệt.

Ví dụ, hai controller cùng công bố `Order.class` nhưng phục vụ hai API khác nhau:

~~~java
@RestController
@RequestMapping("/orders")
@ExposesResourceFor(Order.class)
class PublicOrderController {
    // API công khai.
}

@RestController
@RequestMapping("/admin/orders")
@ExposesResourceFor(Order.class)
class AdminOrderController {
    // API quản trị.
}
~~~

Trong trường hợp này, chỉ biết `Order.class` không đủ để diễn đạt rõ muốn tạo link theo route công khai hay route quản trị. Không nên dựa vào thứ tự scan component hoặc giả định rằng implementation sẽ chọn controller mong muốn.

Hãy chọn một cách rõ ràng: dùng controller method cụ thể, tách resource type/representation theo hợp đồng, hoặc cấu hình implementation phù hợp để ánh xạ duy nhất.

## 8. Ràng buộc giữa domain type và hợp đồng API

API công khai thường dùng DTO hoặc representation model, trong khi `EntityLinks` nhận một class làm định danh loại tài nguyên. Trong ví dụ, class đó thường là domain type như `Order.class`.

Điều này tạo ra một liên kết giữa tầng biểu diễn và kiểu domain. Liên kết đó có thể thuận tiện, nhưng cũng có giới hạn:

- Một domain type có thể được biểu diễn bằng nhiều DTO khác nhau.
- Một DTO có thể tổng hợp dữ liệu từ nhiều domain type.
- Một kiểu domain có thể được expose qua nhiều API với URI khác nhau.
- Thay đổi cấu trúc domain không nhất thiết nên làm thay đổi hợp đồng URI công khai.

Không nên vì `EntityLinks` nhận `Order.class` mà trả trực tiếp JPA entity ra HTTP. Vẫn nên chuyển entity/domain object sang DTO trước khi tạo representation:

~~~java
OrderDto dto = mapper.toDto(order);

EntityModel<OrderDto> model = EntityModel.of(
    dto,
    entityLinks.linkToItemResource(Order.class, order.getId())
        .withSelfRel()
);
~~~

Trong ví dụ, domain type chỉ dùng làm khóa để định vị mapping; nội dung response vẫn là DTO. Nếu API có nhiều representation cho cùng domain type, hãy quyết định rõ relation và link có thể dùng chung hay cần endpoint riêng.

## 9. Không bảo đảm URI sẽ ổn định mãi mãi

`EntityLinks` tạo URI dựa trên mapping hiện có. Nếu mapping thay đổi, URI được tạo ở phản hồi sau cũng có thể thay đổi.

Ví dụ:

~~~text
/orders/42
/api/v2/orders/42
~~~

Công cụ tạo link giúp code không phải tự ghép URL, nhưng không tự bảo đảm URI là vĩnh viễn. Độ ổn định của URI là cam kết trong thiết kế và vận hành hợp đồng API.

Để máy khách ít phụ thuộc vào cấu trúc đường dẫn:

- Duy trì relation có ý nghĩa ổn định.
- Công bố link qua representation thay vì yêu cầu máy khách tự ghép URL.
- Có chính sách tương thích hoặc chuyển hướng khi cần đổi URI.
- Kiểm thử relation và link như một phần của hợp đồng API.
- Tài liệu hóa thay đổi có ảnh hưởng đến máy khách.

Relation và URI có vai trò khác nhau: relation mô tả ý nghĩa của link; href xác định đích đến hiện tại. Duy trì relation không tự động bảo đảm endpoint luôn tồn tại, nhưng giúp máy khách nhận diện loại liên kết qua các lần thay đổi định tuyến.

## 10. Giới hạn khi mô tả API reactive

`EntityLinks` là abstraction chung, nhưng implementation và khả năng tích hợp controller phụ thuộc stack web cũng như phiên bản Spring HATEOAS đang dùng. Không nên mặc định mọi cách cấu hình dựa trên Spring MVC controller đều áp dụng nguyên trạng cho reactive controller.

Với ứng dụng WebFlux cần tạo link từ phương thức reactive controller và request context, `WebFluxLinkBuilder` là công cụ chuyên biệt:

~~~java
Mono<Link> self = linkTo(
    methodOn(ReactiveOrderController.class).one(orderId)
).withSelfRel();
~~~

Kết quả là `Mono<Link>`, vì vậy cần ghép với dữ liệu bằng `flatMap`, `map` hoặc `Mono.zip`. Hãy xác minh implementation `EntityLinks` và hỗ trợ WebFlux theo đúng phiên bản đang sử dụng; nếu cần tham chiếu một reactive controller method cụ thể, dùng builder reactive là cách diễn đạt trực tiếp hơn.

## 11. Chọn công cụ phù hợp với từng loại liên kết

Không cần buộc mọi liên kết phải được tạo bằng một abstraction duy nhất. Chọn công cụ theo mục tiêu:

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Link item/collection theo kiểu tài nguyên | `EntityLinks` |
| Link đến một phương thức Spring MVC cụ thể | `WebMvcLinkBuilder` |
| Link đến một phương thức Spring WebFlux cụ thể | `WebFluxLinkBuilder` |
| URI ngoài mapping controller hoặc URI được cấu hình | `Link.of(...)` hoặc URI builder phù hợp |
| Mẫu tìm kiếm có biến | URI template và templated `Link` |
| Mô tả method và dữ liệu đầu vào của hành động | Affordance và định dạng hỗ trợ affordance |
| Quyết định link nào được công bố | Assembler kết hợp domain/service hoặc policy |

Một assembler có thể kết hợp nhiều nguồn link:

~~~java
EntityModel<OrderDto> model = EntityModel.of(mapper.toDto(order));

model.add(
    entityLinks.linkToItemResource(Order.class, order.getId())
        .withSelfRel()
);

model.add(
    linkTo(methodOn(OrderController.class).cancel(order.getId()))
        .withRel("https://api.example.com/rels/cancel")
);
~~~

Link self dùng abstraction theo tài nguyên; link hủy tham chiếu trực tiếp phương thức endpoint. Cách kết hợp này phù hợp khi hai liên kết có hai yêu cầu tạo khác nhau.

## 12. Kiểm thử các giới hạn và hợp đồng link

Kiểm thử không nên chỉ xác nhận rằng `EntityLinks` trả về một URI. Cần kiểm tra link có trỏ đến đúng route, đúng relation và được công bố trong đúng ngữ cảnh.

Ví dụ kiểm thử phản hồi HAL:

~~~java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.collection.href").exists());
~~~

Với các hành động phụ thuộc trạng thái, kiểm thử cả hai nhánh:

~~~java
// Đơn hàng có thể hủy: relation cancel xuất hiện.
mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/cancel'].href"
    ).exists());

// Đơn hàng không thể hủy: relation cancel không xuất hiện.
mockMvc.perform(get("/orders/43").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/cancel']"
    ).doesNotExist());
~~~

Ngoài ra, nên kiểm thử:

- Controller expose đúng resource type.
- Item và collection link được tạo từ mapping mong muốn.
- Không có mapping mơ hồ khi nhiều controller expose cùng kiểu.
- Route lồng nhau giữ đủ ID cha và ID con.
- Link hành động tuân theo trạng thái và policy.
- Endpoint từ chối request không đủ quyền dù người gọi biết URI.
- Relation được duy trì khi mapping thay đổi.
- DTO không làm lộ trường nội bộ chỉ vì link được tạo từ domain type.

## 13. Quy trình sử dụng EntityLinks có kiểm soát

Khi cân nhắc dùng `EntityLinks`, hãy đi theo trình tự:

1. Xác định tài nguyên có collection route và item route theo quy ước rõ ràng.
2. Khai báo resource type mà controller expose.
3. Kiểm tra implementation `EntityLinks` đã được cấu hình và nhận diện mapping.
4. Dùng `linkToItemResource` hoặc `linkToCollectionResource` cho các link chuẩn.
5. Dùng builder theo phương thức controller cho route lồng, route tùy biến hoặc hành động cụ thể.
6. Dùng assembler để kết hợp link với DTO và điều kiện nghiệp vụ.
7. Dùng affordance nếu máy khách cần khám phá method và dữ liệu đầu vào.
8. Kiểm tra quyền ở endpoint đích, không dựa vào sự hiện diện của link.
9. Kiểm thử relation, URI, trạng thái và khả năng tương thích của hợp đồng.

`EntityLinks` hữu ích khi API có mô hình item/collection nhất quán và muốn tạo link mà không phụ thuộc trực tiếp vào class controller. Giới hạn của nó xuất hiện khi API cần diễn đạt route tùy biến, quan hệ nhiều cấp, hành động nghiệp vụ hoặc quyền truy cập theo ngữ cảnh. Kết hợp `EntityLinks` với controller link builder, assembler, affordance và policy nghiệp vụ giúp biểu diễn hypermedia chính xác mà vẫn giữ ranh giới giữa định vị tài nguyên và quyết định nghiệp vụ.
