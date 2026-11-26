# Link đến endpoint bằng Spring HATEOAS

Khi tạo REST API có hypermedia, một controller thường cần trả về liên kết đến chính endpoint đang xử lý, endpoint của tập hợp, tài nguyên liên quan hoặc một thao tác nghiệp vụ. Spring HATEOAS cung cấp **WebMvcLinkBuilder** để tạo những liên kết này từ mapping của Spring MVC.

Thay vì tự ghép chuỗi URL, ứng dụng tham chiếu trực tiếp đến controller và phương thức xử lý bằng **linkTo** và **methodOn**. Spring HATEOAS đọc metadata mapping, kết hợp các tham số cần thiết và tạo URI phù hợp. Liên kết sau đó được gắn vào representation model để máy khách khám phá từ phản hồi API.

## 1. Vì sao tạo link từ controller?

Giả sử API có các endpoint:

~~~http
GET  /orders
GET  /orders/42
GET  /orders/42/items
POST /orders/42/cancel
GET  /payments/91
~~~

Nếu controller tự nối chuỗi như sau:

~~~java
String href = "/orders/" + orderId;
~~~

thì đường dẫn bị lặp lại ở nhiều nơi. Khi thay đổi class-level mapping, context path hoặc cấu trúc endpoint, các chuỗi URL tự tạo có thể không còn khớp với mapping thật.

Tạo link từ controller giúp:

- Dùng mapping đang được khai báo trên controller và phương thức.
- Truyền giá trị path variable theo đúng endpoint.
- Đưa các giá trị query parameter vào URI khi cần.
- Giảm việc lặp lại chuỗi URL trong assembler và controller.
- Giữ liên kết đồng bộ với thay đổi mapping khi mã được cập nhật.

Link được tạo vẫn là một phần của hợp đồng API. Relation và ý nghĩa mà máy khách sử dụng cần được thiết kế ổn định và tài liệu hóa.

## 2. WebMvcLinkBuilder, linkTo và methodOn

Với ứng dụng Spring MVC, lớp chính là:

~~~java
org.springframework.hateoas.server.mvc.WebMvcLinkBuilder
~~~

Hai phương thức thường được import tĩnh:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Vai trò của từng thành phần:

| Thành phần | Vai trò |
|---|---|
| linkTo(...) | Tạo link builder dựa trên controller hoặc lời gọi phương thức controller |
| methodOn(...) | Tạo tham chiếu kiểu proxy đến controller để ghi nhận phương thức và tham số |
| withSelfRel() | Hoàn tất link với relation self |
| withRel(...) | Hoàn tất link với relation được chỉ định |

Ví dụ tạo link đến một đơn hàng:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Trong ví dụ, Spring HATEOAS dùng mapping của phương thức one và giá trị orderId để tạo URI. Lời gọi methodOn không thực thi logic nghiệp vụ trong thân phương thức controller. Nó tạo một tham chiếu để framework xác định phương thức và các đối số cần dùng khi xây dựng link.

Vì vậy, phương thức được tham chiếu cần có mapping Spring MVC phù hợp. Nếu chỉ đổi tên hoặc xóa endpoint mà không cập nhật logic tạo link, ứng dụng có thể không khởi tạo được liên kết đúng.

## 3. Tạo link self cho endpoint hiện tại

Một endpoint đọc tài nguyên thường trả về link self để máy khách có thể truy cập lại chính tài nguyên đó.

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{orderId}")
    public EntityModel<OrderDto> one(
            @PathVariable("orderId") Long orderId) {

        Order order = orderService.findById(orderId);
        OrderDto dto = mapper.toDto(order);

        EntityModel<OrderDto> model = EntityModel.of(dto);

        model.add(
            linkTo(methodOn(OrderController.class).one(orderId))
                .withSelfRel()
        );

        return model;
    }
}
~~~

Với class-level mapping /orders và method-level mapping /{orderId}, link self được tạo từ cả hai phần mapping. Nếu endpoint được đổi thành /api/orders/{orderId}, link sinh ra cũng phản ánh mapping mới.

Nên tạo link self từ chính phương thức đọc tài nguyên. Điều này giúp relation self trỏ đến URI có thể GET biểu diễn hiện tại.

## 4. Tạo link đến collection endpoint

Một tài nguyên đơn thường có link về tập hợp chứa nó. Có thể tham chiếu trực tiếp phương thức collection:

~~~java
Link orders = linkTo(
    methodOn(OrderController.class).all()
).withRel(IanaLinkRelations.COLLECTION);
~~~

Trong đó all là phương thức được ánh xạ bằng @GetMapping trên /orders.

Cũng có thể tạo link từ toàn bộ controller:

~~~java
Link orders = linkTo(OrderController.class)
    .withRel(IanaLinkRelations.COLLECTION);
~~~

Cách dùng class phù hợp khi cần URI gốc theo class-level mapping. Nếu endpoint collection có method-level path hoặc query parameter, tham chiếu trực tiếp phương thức thường diễn đạt chính xác hơn.

Relation COLLECTION là relation chuẩn được cung cấp bởi IanaLinkRelations. Nó mô tả liên kết đến tập hợp. Không nên đặt relation tùy ý nếu ý nghĩa của liên kết đã có relation chuẩn phù hợp.

## 5. Truyền path variable vào methodOn

Với endpoint có một hoặc nhiều path variable, truyền giá trị tương ứng vào lời gọi methodOn.

~~~java
@GetMapping("/{orderId}/items/{itemId}")
public OrderItemDto item(
        @PathVariable Long orderId,
        @PathVariable Long itemId) {
    // Đọc một mặt hàng trong đơn hàng.
    throw new UnsupportedOperationException("Ví dụ minh họa");
}
~~~

Tạo link đến mặt hàng:

~~~java
Link itemLink = linkTo(
    methodOn(OrderItemController.class).item(orderId, itemId)
).withSelfRel();
~~~

Các giá trị được truyền theo đúng thứ tự tham số của phương thức Java. Spring HATEOAS sử dụng metadata mapping để xác định vị trí tương ứng trong URI.

Nếu phương thức có nhiều tham số, hãy dùng tên tham số rõ ràng và khai báo @PathVariable với tên tường minh khi cần. Điều này làm mã dễ đọc và tránh nhầm lẫn giữa ID của tài nguyên cha với ID của tài nguyên con.

## 6. Tạo link có query parameter

Các tham số được gắn @RequestParam có thể được truyền qua lời gọi methodOn để tạo URI chứa query string.

Ví dụ endpoint tìm kiếm:

~~~java
@GetMapping("/search")
public CollectionModel<OrderDto> search(
        @RequestParam(name = "status", required = false) String status) {
    // Tìm các đơn hàng theo trạng thái.
    throw new UnsupportedOperationException("Ví dụ minh họa");
}
~~~

Tạo link tìm kiếm với trạng thái cụ thể:

~~~java
Link paidOrders = linkTo(
    methodOn(OrderController.class).search("PAID")
).withRel("search");
~~~

Link được tạo sẽ chứa query parameter status tương ứng. Máy khách có thể theo link thay vì tự xây dựng query string.

Với tham số tùy chọn, cần xác định rõ cách API xử lý giá trị null hoặc giá trị mặc định. Nếu muốn công bố một URI template để máy khách tự điền nhiều tham số tìm kiếm, hãy tạo link templated riêng. Link đến một truy vấn cụ thể và link template phục vụ tìm kiếm tổng quát là hai trường hợp khác nhau.

## 7. Liên kết đến controller khác

Một tài nguyên có thể điều hướng đến endpoint do controller khác quản lý. Ví dụ đơn hàng liên kết tới khoản thanh toán.

~~~java
Link payment = linkTo(
    methodOn(PaymentController.class).one(order.getPaymentId())
).withRel("https://api.example.com/rels/payment");
~~~

Ví dụ dùng relation URI mở rộng để mô tả quan hệ payment. Trong API thực tế, relation này cần được tài liệu hóa và duy trì ý nghĩa ổn định.

Có thể kết hợp nhiều link trong một representation:

~~~java
EntityModel<OrderDto> model = EntityModel.of(orderDto);

model.add(
    linkTo(methodOn(OrderController.class).one(orderId))
        .withSelfRel()
);

model.add(
    linkTo(methodOn(OrderItemController.class).all(orderId))
        .withRel("https://api.example.com/rels/order-items")
);

if (order.getPaymentId() != null) {
    model.add(
        linkTo(methodOn(PaymentController.class)
            .one(order.getPaymentId()))
            .withRel("https://api.example.com/rels/payment")
    );
}
~~~

Controller đích có thể nằm ở một package hoặc bounded context khác. Điều quan trọng là endpoint đích thuộc hợp đồng API mà ứng dụng đang công bố và relation diễn tả đúng ý nghĩa liên kết.

## 8. Đặt logic tạo link trong assembler

Khi nhiều endpoint cùng trả về một loại tài nguyên, nên tập trung logic tạo representation và link trong assembler. Controller khi đó chủ yếu điều phối request và nghiệp vụ.

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    private final OrderMapper mapper;

    public OrderAssembler(OrderMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        EntityModel<OrderDto> model =
            EntityModel.of(mapper.toDto(order));

        model.add(
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel(IanaLinkRelations.COLLECTION)
        );

        if (order.canBeCancelled()) {
            model.add(
                linkTo(methodOn(OrderController.class)
                    .cancel(order.getId()))
                    .withRel("https://api.example.com/rels/cancel")
            );
        }

        return model;
    }
}
~~~

Assembler nhận domain object, chuyển thành DTO và tạo các link phù hợp. Controller có thể sử dụng assembler như sau:

~~~java
@GetMapping("/{orderId}")
public EntityModel<OrderDto> one(@PathVariable Long orderId) {
    return orderAssembler.toModel(orderService.findById(orderId));
}
~~~

Cách tổ chức này tránh việc mỗi controller tự tạo một tập link khác nhau cho cùng loại tài nguyên. Khi relation hoặc endpoint thay đổi, có thể cập nhật logic tạo link tại một nơi.

Assembler không thay thế service hoặc cơ chế phân quyền. Điều kiện hiển thị link chỉ quyết định khả năng được công bố trong biểu diễn; endpoint thực thi hành động vẫn phải xác thực người gọi, quyền truy cập và trạng thái nghiệp vụ.

## 9. Link đến endpoint hành động và affordance

Một link có relation như cancel cho máy khách biết ý nghĩa của đích đến. Tuy nhiên, link cơ bản không mô tả đầy đủ HTTP method, request body hay schema đầu vào.

Ví dụ:

~~~java
model.add(
    linkTo(methodOn(OrderController.class).cancel(order.getId()))
        .withRel("https://api.example.com/rels/cancel")
);
~~~

Đoạn mã công bố URI và relation của thao tác hủy. Máy khách cần biết qua hợp đồng API rằng endpoint này nhận POST. Nếu cần mô tả thêm method và dữ liệu đầu vào ngay trong biểu diễn, Spring HATEOAS hỗ trợ affordance và các định dạng hypermedia có thể biểu diễn affordance, chẳng hạn HAL-FORMS.

Cần phân biệt:

- **Link:** chỉ ra đích đến và relation.
- **Affordance:** mô tả thêm hành động có thể thực hiện, bao gồm thông tin method và đầu vào mà định dạng hỗ trợ.
- **Endpoint controller:** nơi nhận request và thực thi logic nghiệp vụ.

Dù link hoặc affordance có được công bố hay không, endpoint vẫn phải kiểm tra quyền và điều kiện nghiệp vụ khi request đến.

## 10. Cấu trúc HAL sau khi controller tạo link

Khi representation model được tuần tự hóa thành HAL JSON, các link xuất hiện trong thuộc tính _links.

Ví dụ phản hồi đơn hàng:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/orders"
    },
    "https://api.example.com/rels/order-items": {
      "href": "https://api.example.com/orders/42/items"
    },
    "https://api.example.com/rels/cancel": {
      "href": "https://api.example.com/orders/42/cancel"
    }
  }
}
~~~

Máy khách đọc relation và theo URI trong href. Nếu server thay đổi mapping, các URI mới được tạo từ controller mapping và gửi về trong representation tiếp theo.

Để nhận HAL JSON, máy khách thường gửi:

~~~http
Accept: application/hal+json
~~~

Ứng dụng Spring Boot có thể dùng dependency spring-boot-starter-hateoas để tích hợp Spring HATEOAS và cấu hình serialization phù hợp.

## 11. Kiểm thử link được tạo từ controller

Kiểm thử controller nên xác nhận phản hồi có các link cần thiết và URI được tạo từ mapping chính xác. Ví dụ:

~~~java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.collection.href").exists())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/cancel'].href"
    ).exists());
~~~

Nếu đơn hàng không thể hủy, nên có trường hợp kiểm thử riêng xác nhận relation cancel không xuất hiện:

~~~java
mockMvc.perform(
        get("/orders/43").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/cancel']"
    ).doesNotExist());
~~~

Ngoài ra, cần kiểm tra:

- Link self trỏ đến đúng endpoint đọc tài nguyên.
- Link collection trỏ đến endpoint danh sách.
- Link có path variable dùng đúng ID.
- Query parameter được đưa vào URI theo đúng mapping.
- Link liên-controller trỏ đến đúng endpoint đích.
- Relation hành động xuất hiện theo trạng thái và ngữ cảnh.
- Endpoint vẫn từ chối request không đủ quyền dù máy khách tự gọi URI.

Không nên chỉ kiểm tra chuỗi URL cứng nếu ứng dụng có context path, reverse proxy hoặc sinh absolute URI. Hãy kiểm tra URI theo cấu hình môi trường hoặc xác nhận các thành phần quan trọng của link.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự ghép URL từ ID | Link dễ lệch mapping | Dùng linkTo và methodOn |
| Gọi nhầm phương thức trong methodOn | Link trỏ sai endpoint | Tham chiếu đúng phương thức có mapping |
| Truyền sai thứ tự tham số | URI chứa sai giá trị | Đối chiếu chữ ký phương thức controller |
| Dùng class-level link cho endpoint có query/path riêng | Link không trỏ đúng thao tác cần thiết | Tham chiếu method-level mapping |
| Dùng relation không rõ nghĩa | Máy khách khó diễn giải | Dùng relation chuẩn hoặc URI relation được tài liệu hóa |
| Cho rằng link cancel tự mô tả POST và body | Máy khách thiếu thông tin thực thi | Dùng affordance hoặc tài liệu hợp đồng |
| Xem việc ẩn link là phân quyền | Người dùng vẫn có thể gọi URI trực tiếp | Kiểm tra quyền tại endpoint/service |
| Tạo link từ controller không có mapping phù hợp | Không thể tạo URI đáng tin cậy | Bảo đảm phương thức có mapping và tham số đúng |

## 13. Quy trình tạo link đến endpoint

Khi tạo link từ controller bằng Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định endpoint đích và relation mô tả đúng ý nghĩa.
2. Kiểm tra class-level và method-level mapping của controller.
3. Dùng methodOn để tham chiếu phương thức cùng các tham số cần thiết.
4. Dùng linkTo để tạo URI từ mapping.
5. Gắn relation bằng withSelfRel hoặc withRel.
6. Thêm link vào EntityModel, CollectionModel hoặc representation model phù hợp.
7. Đưa logic dùng chung vào assembler khi nhiều endpoint cùng tạo một loại biểu diễn.
8. Kiểm thử link trong phản hồi HTTP, gồm cả trường hợp trạng thái không cung cấp một hành động.
9. Kiểm tra quyền tại endpoint đích và mô tả affordance nếu máy khách cần biết method hoặc dữ liệu đầu vào.

WebMvcLinkBuilder giúp tạo link gắn với mapping thực tế của Spring MVC. Khi kết hợp linkTo, methodOn, relation có ý nghĩa và representation model, controller có thể công bố các đường đi tới tài nguyên hoặc thao tác tiếp theo một cách nhất quán. Máy khách khám phá endpoint qua liên kết trong phản hồi, còn ứng dụng giữ quyền kiểm soát logic nghiệp vụ và chính sách truy cập.
