# Mở rộng representation

## Mục tiêu

Spring HATEOAS cung cấp lớp cơ sở RepresentationModel để ứng dụng xây dựng representation riêng có thể mang các liên kết hypermedia. Khi API cần nhiều hơn một DTO được bọc cùng links, bạn có thể tạo kiểu model chuyên biệt kế thừa RepresentationModel, định nghĩa các thuộc tính của response và bổ sung liên kết theo trạng thái tài nguyên. Với các trường hợp đơn giản hơn, EntityModel vẫn là lựa chọn gọn để bọc DTO hiện có.

Sau bài học, bạn có thể:

- Phân biệt RepresentationModel, EntityModel và CollectionModel.
- Tạo custom representation model kế thừa RepresentationModel<T>.
- Chuyển domain object thành custom model bằng RepresentationModelAssembler.
- Tùy chỉnh item relation và collection relation trong HAL.
- Kiểm thử cấu trúc dữ liệu, embedded relation và links của representation.

## Hai cách đưa dữ liệu vào hypermedia model

Spring HATEOAS tách nội dung tài nguyên khỏi các liên kết điều hướng. Có hai cách thường dùng để tạo representation:

| Cách | Khi phù hợp |
|---|---|
| Bọc DTO bằng EntityModel<T> | DTO đã có cấu trúc dữ liệu phù hợp; chỉ cần thêm links cho tài nguyên. |
| Tạo lớp riêng kế thừa RepresentationModel<T> | API cần định nghĩa một kiểu representation cụ thể, kết hợp dữ liệu, trường tổng hợp và links trong cùng một model. |

EntityModel không buộc DTO phải kế thừa lớp của Spring HATEOAS. Điều này hữu ích khi DTO được dùng ở nhiều nơi, hoặc khi muốn giữ mô hình dữ liệu ứng dụng độc lập với thư viện hypermedia. Custom model kế thừa RepresentationModel phù hợp khi cấu trúc response là một phần rõ ràng của hợp đồng API và cần được tái sử dụng nhất quán.

RepresentationModel lưu các Link và cung cấp API để thêm, truy vấn hoặc kiểm tra links. Lớp này không tự chứa quy tắc nghiệp vụ, không truy cập repository và không thay thế controller. Các thuộc tính nghiệp vụ của custom model vẫn do ứng dụng định nghĩa.

## Tạo custom model kế thừa RepresentationModel

Một lớp representation thường kế thừa RepresentationModel với chính kiểu lớp đó làm tham số generic. Mẫu self type này giúp API fluent của lớp cơ sở trả về đúng kiểu model con khi thêm links.

Ví dụ, response đơn hàng cần các trường định danh, trạng thái, tổng tiền và links:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal total;

    public OrderModel(UUID id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Lớp này có ba phần:

1. Các thuộc tính dữ liệu mô tả đơn hàng.
2. RepresentationModel<OrderModel> cung cấp nơi gắn links.
3. @Relation định nghĩa quan hệ của item và collection khi serializer hypermedia sử dụng model này.

Các trường dữ liệu được khai báo final để model không bị thay đổi sau khi tạo. Links được bổ sung khi assembler xây representation. Nếu dự án dùng Jackson với chính sách visibility hoặc constructor riêng, hãy bảo đảm các thuộc tính có thể được serialize theo cấu hình JSON của ứng dụng.

Không nên cho entity JPA kế thừa RepresentationModel chỉ để thêm links. Entity thuộc mô hình persistence, còn custom model thuộc hợp đồng HTTP. Giữ hai lớp riêng giúp thay đổi schema lưu trữ không tự động làm thay đổi response và tránh đưa các quan hệ lazy hoặc thuộc tính nội bộ ra ngoài API.

## Chuyển domain object thành representation

RepresentationModelAssembler gom logic chuyển đổi và tạo links vào một nơi. Controller chỉ cần gọi service lấy dữ liệu và yêu cầu assembler tạo model.

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
                order.getId(),
                order.getStatus().name(),
                order.getTotal());

        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());

        model.add(linkTo(methodOn(OrderController.class)
                .findAll()).withRel(IanaLinkRelations.COLLECTION));

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null)).withRel("cancel"));
        }

        return model;
    }
}
~~~

Assembler thực hiện ba việc: tạo phần dữ liệu, gắn link self và collection, sau đó thêm link cancel khi trạng thái cho phép. Các URI được tạo từ mapping của controller thông qua linkTo và methodOn; không cần ghép chuỗi URL bằng tay.

Nếu nhiều endpoint cần cùng một biểu diễn, dùng chung assembler giúp link relation và cách chuyển dữ liệu nhất quán. Nếu một endpoint cần thêm thông tin theo ngữ cảnh, có thể tách phương thức tạo model hoặc dùng một assembler chuyên biệt; tránh nhồi mọi biến thể response vào một assembler lớn với nhiều nhánh khó kiểm soát.

Controller có thể trả custom model trực tiếp:

~~~java
import java.util.Collection;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    OrderModel findById(@PathVariable UUID id) {
        return assembler.toModel(orderService.findById(id));
    }

    @GetMapping
    CollectionModel<OrderModel> findAll() {
        Collection<Order> orders = orderService.findAll();
        return assembler.toCollectionModel(orders)
                .add(linkTo(methodOn(OrderController.class)
                        .findAll()).withSelfRel());
    }
}
~~~

Phương thức toCollectionModel mặc định chuyển từng phần tử bằng toModel; controller có thể bổ sung link cấp collection sau khi tạo collection model. Với danh sách phân trang, cân nhắc PagedModel và các link điều hướng trang thay vì tự thêm query parameter vào URL.

## Tùy chỉnh quan hệ trong HAL

Khi serializer HAL chuyển một collection model thành JSON, nó cần biết tên relation dùng cho các phần tử nhúng. Annotation @Relation cho phép custom model công bố tên item relation và collection relation.

Với OrderModel ở trên:

- itemRelation = "order" là tên relation của một phần tử đơn hàng.
- collectionRelation = "orders" là tên relation của collection đơn hàng.

Một collection response có thể có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "status": "PENDING",
        "total": 125.50,
        "_links": {
          "self": { "href": "/api/orders/order-42" },
          "cancel": { "href": "/api/orders/order-42/cancellation" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders" }
  }
}
~~~

Tên relation là một phần của hợp đồng hypermedia. Nếu client đang tìm _embedded.orders, đổi collectionRelation thành purchases sẽ ảnh hưởng client dù đường dẫn endpoint không đổi. Hãy chọn tên có ý nghĩa, ổn định và kiểm thử chúng như kiểm thử các trường dữ liệu khác.

Annotation @Relation có thể đặt trên custom model. Với DTO được bọc trong EntityModel hoặc collection model dùng loại phần tử khác, hãy kiểm tra cách relation được xác định theo cấu hình hypermedia và loại model thực tế; đừng giả định tên Java class luôn tạo ra relation đúng ý muốn.

## Kết hợp custom model và EntityModel

Không cần tạo custom subclass cho mọi response. Nếu API đã có DTO rõ ràng và chỉ cần links, dùng EntityModel:

~~~java
OrderResponse response = OrderResponse.from(order);

EntityModel<OrderResponse> model = EntityModel.of(response)
        .add(linkTo(methodOn(OrderController.class)
                .findById(order.getId())).withSelfRel());
~~~

Nếu response có cấu trúc riêng, nhiều trường tổng hợp hoặc được dùng như một kiểu công khai ổn định trong nhiều endpoint, custom OrderModel giúp mô tả rõ cấu trúc đó. Có thể dùng CollectionModel<OrderModel> cho collection, hoặc PagedModel<OrderModel> cho dữ liệu phân trang.

Một nguyên tắc hữu ích là giữ model ở mức cần thiết cho hợp đồng API:

- Dùng DTO để mô tả dữ liệu ứng dụng.
- Dùng EntityModel khi chỉ cần bọc DTO và links.
- Dùng custom RepresentationModel khi cần một kiểu representation riêng có links.
- Dùng CollectionModel hoặc PagedModel để biểu diễn tập tài nguyên và điều hướng collection.

## Mở rộng model dùng chung

Nếu nhiều representation có cùng metadata, chẳng hạn thời điểm tạo hoặc phiên bản tài nguyên, có thể tạo một lớp cơ sở riêng của ứng dụng. Hãy dùng generic self type để giữ kiểu con khi kế thừa:

~~~java
import java.time.Instant;

import org.springframework.hateoas.RepresentationModel;

abstract class AuditedModel<T extends AuditedModel<T>>
        extends RepresentationModel<T> {

    private final Instant createdAt;
    private final Instant updatedAt;

    protected AuditedModel(Instant createdAt, Instant updatedAt) {
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Một model cụ thể có thể kế thừa lớp này:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public class AuditedOrderModel extends AuditedModel<AuditedOrderModel> {

    private final UUID id;
    private final BigDecimal total;

    public AuditedOrderModel(
            UUID id,
            BigDecimal total,
            Instant createdAt,
            Instant updatedAt) {
        super(createdAt, updatedAt);
        this.id = id;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Chỉ nên tạo lớp cơ sở khi các representation thật sự chia sẻ cùng khái niệm và hợp đồng. Nếu chỉ có vài trường giống nhau nhưng ý nghĩa hoặc vòng đời khác nhau, composition hoặc các DTO riêng thường dễ hiểu hơn. Tránh biến lớp cơ sở thành nơi chứa mọi tiện ích, link hoặc logic nghiệp vụ của API.

## Kiểm thử custom representation

Kiểm thử controller nên xác minh dữ liệu và links được serialize đúng định dạng. Ví dụ với MockMvc và HAL JSON:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$.id").exists())
        .andExpect(jsonPath("$.status").value("PENDING"))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Kiểm thử collection relation riêng:

~~~java
mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded.orders").isArray())
        .andExpect(jsonPath("$._links.self.href").exists());
~~~

Nếu relation trong HAL đổi ngoài ý muốn, test _embedded.orders sẽ phát hiện thay đổi hợp đồng. Bổ sung trường hợp đơn hàng không thể hủy để bảo đảm link cancel không xuất hiện. Với collection lớn hoặc phân trang, kiểm tra cả các link first, prev, self, next và last theo trang đang trả.

## Những lỗi thường gặp

- **Cho entity JPA kế thừa RepresentationModel:** điều này trộn mô hình persistence với hợp đồng HTTP và có thể làm lộ dữ liệu không mong muốn. Tạo DTO hoặc custom representation riêng.
- **Dùng custom subclass cho mọi DTO:** lớp mới làm tăng cấu trúc phải duy trì. EntityModel phù hợp khi chỉ cần bọc dữ liệu và links.
- **Quên generic self type:** dùng RepresentationModel<OrderModel> để API fluent của lớp cơ sở giữ kiểu model con.
- **Đặt logic nghiệp vụ trong model hoặc assembler:** model mô tả dữ liệu và links; assembler chuyển đổi và tạo links; service/domain quyết định nghiệp vụ.
- **Không kiểm thử relation HAL:** tên collection relation có thể thay đổi cấu trúc _embedded mà client đang sử dụng.
- **Tự tạo thuộc tính links trong DTO:** để Spring HATEOAS quản lý Link và hypermedia serialization, tránh duy trì một cấu trúc links song song.
- **Tạo lớp cơ sở quá rộng:** chỉ chia sẻ abstraction khi các representation thực sự có cùng ngữ nghĩa và vòng đời.

## Quy trình mở rộng representation

1. Xác định DTO hiện tại đã đủ hay cần một kiểu representation riêng.
2. Nếu cần kiểu riêng, tạo lớp kế thừa RepresentationModel với generic self type và các thuộc tính response rõ ràng.
3. Dùng @Relation khi cần kiểm soát item relation và collection relation trong HAL.
4. Viết RepresentationModelAssembler để chuyển domain object thành model và tạo links từ controller mapping.
5. Trả custom model hoặc CollectionModel/PagedModel từ controller; để Spring HATEOAS xử lý hypermedia serialization.
6. Kiểm thử dữ liệu, media type, link relation và tên embedded collection như các phần của hợp đồng API.

Mở rộng representation đúng cách giúp API có cấu trúc response rõ ràng, tái sử dụng được và gắn links nhất quán với trạng thái tài nguyên. Spring HATEOAS cung cấp lớp cơ sở và assembler để phần dữ liệu của ứng dụng cùng tồn tại với hypermedia mà không buộc entity persistence phải mang trách nhiệm của hợp đồng HTTP.
