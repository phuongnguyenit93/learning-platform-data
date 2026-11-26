# Tái sử dụng assembler

Trong một REST API, cùng một loại tài nguyên có thể xuất hiện ở nhiều endpoint: endpoint chi tiết, danh sách tổng thể, danh sách con của một tài nguyên cha hoặc kết quả tìm kiếm. Nếu mỗi controller tự chuyển domain object thành DTO và tự gắn liên kết, dữ liệu và quan hệ hypermedia của cùng một tài nguyên dễ bị khác nhau giữa các endpoint.

Spring HATEOAS cung cấp RepresentationModelAssembler để gom quy tắc chuyển đổi một domain object thành representation có liên kết. Khi controller cần biểu diễn một tài nguyên hoặc một collection, nó có thể dùng lại cùng assembler. Cách tổ chức này giữ dữ liệu và link của từng phần tử nhất quán, đồng thời cho phép controller bổ sung các liên kết ở cấp collection phù hợp với ngữ cảnh endpoint.

Bài học này trình bày cách thiết kế assembler có thể tái sử dụng, cách dùng toModel và toCollectionModel, cách dùng cùng assembler trong nhiều controller, cách tách mapping khỏi link generation, cách tổ chức assembler theo ranh giới tài nguyên và cách kiểm thử hợp đồng representation.

## 1. Vì sao cần tái sử dụng assembler?

Giả sử tài nguyên Order xuất hiện ở ba nơi:

- GET /api/orders/42 trả về chi tiết một đơn hàng.
- GET /api/orders trả về danh sách đơn hàng.
- GET /api/customers/7/orders trả về các đơn hàng thuộc một khách hàng.

Cả ba endpoint đều cần biểu diễn từng Order bằng các trường như mã đơn, trạng thái, tổng tiền và các liên kết self, customer hoặc cancel. Nếu mỗi controller tự tạo representation, cùng một đơn hàng có thể có tên trường khác nhau, thiếu link ở một endpoint hoặc áp dụng điều kiện link không nhất quán.

Assembler dùng chung giải quyết vấn đề đó:

~~~mermaid
flowchart TD
    S["OrderService"]
    S --> O1["OrderController: chi tiết"]
    S --> O2["OrderController: collection"]
    S --> O3["CustomerOrderController: collection con"]
    O1 --> A["OrderModelAssembler"]
    O2 --> A
    O3 --> A
    A --> R["EntityModel<OrderDto>"]
    R --> H["Representation HAL nhất quán"]
~~~

Mỗi controller tập trung vào việc nhận yêu cầu, gọi use case và bổ sung liên kết ở cấp endpoint. Assembler chịu trách nhiệm tạo biểu diễn của một Order. Khi quy tắc DTO hoặc link của Order thay đổi, có thể cập nhật tại một nơi và các endpoint sử dụng assembler sẽ cùng nhận thay đổi đó.

Tái sử dụng không có nghĩa là gom tất cả loại tài nguyên vào một assembler tổng quát. Một assembler nên có trách nhiệm rõ ràng với một loại domain object và một kiểu representation xác định.

## 2. Hợp đồng của RepresentationModelAssembler

Spring HATEOAS định nghĩa RepresentationModelAssembler với hai tham số generic:

~~~java
public interface RepresentationModelAssembler<
        T,
        D extends RepresentationModel<?>
> {
    D toModel(T entity);
}
~~~

Trong đó:

- T là kiểu domain object hoặc kiểu dữ liệu nguồn cần chuyển đổi.
- D là kiểu representation kế thừa RepresentationModel, ví dụ EntityModel<OrderDto>.
- toModel(T) chuyển một đối tượng nguồn thành một representation có dữ liệu và link.

Interface còn cung cấp toCollectionModel(Iterable<? extends T>) để chuyển một tập hợp đối tượng thành CollectionModel<D>. Cách triển khai mặc định gọi toModel cho từng phần tử, vì vậy collection dùng cùng quy tắc biểu diễn với tài nguyên đơn lẻ.

Ví dụ kiểu assembler:

~~~java
public class OrderModelAssembler
        implements RepresentationModelAssembler<
                Order,
                EntityModel<OrderDto>
        > {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        // Chuyển Order thành EntityModel<OrderDto>.
    }
}
~~~

Đây là khung rút gọn để thể hiện chữ ký generic; phần triển khai đầy đủ được trình bày ở mục tiếp theo.

Khai báo generic giúp compiler kiểm tra kiểu đầu vào và đầu ra. Controller biết assembler nhận Order và trả EntityModel<OrderDto>, không cần ép kiểu hoặc tự dựng wrapper.

## 3. Xây dựng assembler dùng chung

Trước hết, xác định domain object và DTO công khai. Ví dụ:

~~~java
import java.math.BigDecimal;

public record Order(
        Long id,
        Long customerId,
        String customerName,
        BigDecimal total,
        OrderStatus status
) {
}
~~~

~~~java
import java.math.BigDecimal;

public record OrderDto(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status
) {
}
~~~

Trạng thái dùng trong ví dụ:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Assembler chuyển đổi dữ liệu và gắn các link chuẩn của một đơn hàng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
                Order,
                EntityModel<OrderDto>
        > {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.customerName(),
                order.total(),
                order.status()
        );

        EntityModel<OrderDto> model = EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .all()).withRel("orders"),
                linkTo(methodOn(CustomerController.class)
                        .one(order.customerId())).withRel("customer")
        );

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel("cancel"));
        }

        return model;
    }
}
~~~

Assembler thường được đăng ký bằng @Component và được Spring quản lý như một bean dùng chung. Vì vậy, hãy giữ assembler stateless: không lưu Order hiện tại, không ghi dữ liệu request vào field và không thay đổi cấu hình link giữa các lần gọi. Mỗi lần gọi toModel nhận đối tượng riêng và tạo một representation mới.

Ví dụ giả định OrderController có các phương thức one, all, cancel và CustomerController có phương thức one. Các kiểu OrderStatus, controller và service được khai báo trong ứng dụng. Trong dự án Java, mỗi kiểu public được đặt trong file nguồn riêng.

Assembler làm ba việc:

1. Chọn và chuyển các trường domain thành DTO công khai.
2. Tạo các link luôn có ý nghĩa với một Order như self, orders và customer.
3. Thêm link theo trạng thái hiện tại, ví dụ cancel khi đơn hàng đang PENDING.

Assembler không truy vấn database và không thực hiện thao tác hủy. Nó chỉ dùng dữ liệu đã được service cung cấp để mô tả tài nguyên. Endpoint cancel vẫn phải kiểm tra trạng thái và quyền khi client gửi yêu cầu.

## 4. Dùng một assembler cho endpoint chi tiết và collection

Controller có thể inject assembler qua constructor:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler
    ) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderDto>> all() {
        return assembler.toCollectionModel(orderService.findAll());
    }
}
~~~

Endpoint chi tiết gọi toModel. Endpoint collection gọi toCollectionModel. Mỗi phần tử trong collection được tạo bởi cùng phương thức toModel, nên dữ liệu DTO và link ở cấp item được giữ nhất quán.

Nếu endpoint collection cần link self ở cấp collection, controller có thể bổ sung sau khi assembler tạo xong. Đây là phần thay thế cho phương thức all ở ví dụ trên:

~~~java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
public CollectionModel<EntityModel<OrderDto>> all() {
    return assembler.toCollectionModel(orderService.findAll())
            .add(linkTo(methodOn(OrderController.class)
                    .all()).withSelfRel());
}
~~~

Link self của từng Order thuộc trách nhiệm của OrderModelAssembler. Link self của collection thuộc endpoint và được controller bổ sung. Hai link này cùng có relation self nhưng tham chiếu đến hai resource khác nhau: một Order và tập hợp Orders.

## 5. Dùng lại assembler trong endpoint collection con

Một Order cũng có thể xuất hiện trong collection gắn với Customer. Endpoint này cần cùng representation cho từng Order, nhưng collection có ngữ cảnh riêng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers/{customerId}/orders")
public class CustomerOrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    public CustomerOrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler
    ) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderDto>> orders(
            @PathVariable Long customerId
    ) {
        return orderAssembler.toCollectionModel(
                orderService.findByCustomer(customerId)
        ).add(
                linkTo(methodOn(CustomerOrderController.class)
                        .orders(customerId)).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(customerId)).withRel("customer")
        );
    }
}
~~~

Service cần cung cấp findByCustomer(customerId) và bảo đảm khách hàng được xác định hợp lệ. OrderModelAssembler vẫn tạo từng Order theo cùng một cách như endpoint toàn cục. CustomerOrderController chỉ bổ sung link self của collection con và link quay về Customer.

Nhờ tách link item khỏi link collection, assembler dùng lại được ở nhiều endpoint mà không phải biết collection hiện tại là /api/orders hay /api/customers/7/orders.

## 6. Phân chia link theo phạm vi

Khi thiết kế assembler có thể tái sử dụng, cần phân biệt hai phạm vi liên kết:

| Phạm vi | Ví dụ | Nơi thường tạo |
| --- | --- | --- |
| Link của một tài nguyên | self, customer, cancel, receipt | Resource assembler |
| Link của một collection hoặc endpoint | self của collection, link quay về resource cha, link trang | Controller hoặc collection assembler chuyên biệt |

Nếu assembler luôn thêm link self của endpoint collection tổng thể, rồi controller collection con cũng thêm self, representation có thể chứa liên kết trùng hoặc gây nhầm lẫn về collection hiện tại. Hãy để assembler item tạo các link gắn với chính item; để controller hoặc thành phần collection riêng tạo link theo ngữ cảnh.

Tương tự, link customer trên một Order có thể luôn trỏ đến Customer của nó. Link quay về collection /api/customers/7/orders lại phụ thuộc vào endpoint mà client vừa gọi. Không nên buộc OrderModelAssembler phải đoán client đang ở collection nào.

## 7. Tách mapping DTO và tạo link khi cần

Khi mapping dữ liệu phức tạp, có thể tách phần chuyển đổi DTO khỏi phần xây hypermedia. Điều này hữu ích nếu nhiều representation cần dùng cùng quy tắc chuyển domain sang DTO hoặc nếu mapping được quản lý bằng MapStruct.

Ví dụ mapper:

~~~java
import org.springframework.stereotype.Component;

@Component
public class OrderDtoMapper {

    public OrderDto toDto(Order order) {
        return new OrderDto(
                order.id(),
                order.customerName(),
                order.total(),
                order.status()
        );
    }
}
~~~

Assembler sử dụng mapper:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
                Order,
                EntityModel<OrderDto>
        > {

    private final OrderDtoMapper mapper;

    public OrderModelAssembler(OrderDtoMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = mapper.toDto(order);

        EntityModel<OrderDto> model = EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(order.customerId())).withRel("customer")
        );

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel("cancel"));
        }

        return model;
    }
}
~~~

Mapper không biết URI hoặc link relation. Assembler không cần lặp lại các quy tắc chuyển đổi trường dữ liệu. Hai thành phần có thể được kiểm thử độc lập và tái sử dụng trong các use case phù hợp.

Không nên tách mapper chỉ vì một DTO có vài trường đơn giản. Hãy thêm lớp riêng khi mapping có quy tắc đáng kể, được dùng ở nhiều nơi hoặc cần một công cụ mapping độc lập.

## 8. Tổ chức assembler theo ranh giới tài nguyên

Một ứng dụng có thể có nhiều assembler:

| Assembler | Đầu vào | Representation |
| --- | --- | --- |
| OrderModelAssembler | Order | EntityModel<OrderDto> |
| CustomerModelAssembler | Customer | EntityModel<CustomerDto> |
| ProductModelAssembler | Product | EntityModel<ProductDto> |
| PaymentModelAssembler | Payment | EntityModel<PaymentDto> |

Mỗi assembler định nghĩa cách công bố một loại resource. Khi resource đó xuất hiện trong nhiều collection hoặc endpoint, controller có thể inject cùng assembler.

Nếu một resource cha cần dẫn đến resource con, thường chỉ cần thêm link relation. Ví dụ CustomerModelAssembler có thể thêm link orders trỏ đến collection đơn hàng của khách hàng. Client theo link đó để lấy collection; OrderModelAssembler tiếp tục biểu diễn từng đơn hàng.

Không nên tạo vòng phụ thuộc giữa các assembler. Ví dụ OrderModelAssembler inject CustomerModelAssembler, trong khi CustomerModelAssembler lại inject OrderModelAssembler, có thể gây circular dependency và làm mờ trách nhiệm. Ưu tiên liên kết bằng URI và relation; nếu thực sự cần nhúng representation, tổ chức phụ thuộc một chiều hoặc tạo một assembler tổng hợp riêng cho use case đó.

## 9. Khi nào không nên dùng lại cùng một assembler?

Không phải mọi endpoint đều cần cùng một representation. Một số trường hợp cần assembler riêng:

- Endpoint danh sách chỉ công bố trường tóm tắt, còn endpoint chi tiết công bố thêm dữ liệu.
- API version mới có schema khác với phiên bản cũ.
- Một use case có projection chuyên biệt, ví dụ báo cáo hoặc dashboard.
- Một số nhóm client được phép xem trường dữ liệu khác nhau theo chính sách truy cập.
- Resource có representation khác nhau theo media type hoặc profile.

Trong các trường hợp này, hãy tạo DTO và assembler phù hợp như OrderSummaryAssembler và OrderDetailAssembler. Không thêm nhiều cờ boolean vào một assembler chung kiểu toModel(order, includeItems, includePayments, compact) vì các tổ hợp cờ làm hợp đồng khó hiểu và khó kiểm thử.

Một cách tổ chức rõ ràng:

| Use case | Kiểu representation |
| --- | --- |
| Danh sách đơn hàng | OrderSummaryDto và OrderSummaryAssembler |
| Chi tiết đơn hàng | OrderDetailDto và OrderDetailAssembler |
| Collection đơn hàng của khách hàng | Dùng lại OrderSummaryAssembler cho từng phần tử |

Nếu hai representation có cùng dữ liệu và cùng ngữ nghĩa, dùng chung assembler. Nếu khác nhau về hợp đồng công khai, tạo assembler riêng thay vì cố ép chúng vào một kiểu chung.

## 10. Điều kiện nghiệp vụ và quyền truy cập

Assembler có thể thêm hoặc bỏ link dựa trên trạng thái đã có trong domain object:

~~~java
if (order.canBeCancelled()) {
    model.add(linkTo(methodOn(OrderController.class)
            .cancel(order.id())).withRel("cancel"));
}
~~~

Điều này giúp client khám phá thao tác có ý nghĩa ở thời điểm nhận representation. Nếu thao tác còn phụ thuộc vào quyền người dùng, có thể dùng một policy hoặc authorization service được thiết kế rõ ràng để xác định khả năng công bố link.

Không nên gọi repository hoặc tải thêm nhiều dữ liệu trong assembler chỉ để quyết định link. Nếu cần thông tin để dựng representation, service nên chuẩn bị dữ liệu hoặc projection đó trước. Assembler nên giữ công việc ở mức chuyển đổi và liên kết.

Link không phải cơ chế bảo mật. Client có thể lưu URI và gọi lại sau khi trạng thái hoặc quyền thay đổi. Controller và service phải xác thực, phân quyền và kiểm tra invariant tại thời điểm thực thi thao tác.

## 11. Kiểm thử assembler và khả năng tái sử dụng

Kiểm thử nên xác nhận hai điều: cùng một resource được biểu diễn nhất quán ở nhiều endpoint, và mỗi endpoint vẫn có link collection phù hợp với ngữ cảnh của nó.

Với MockMvc, có thể kiểm tra endpoint chi tiết:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsOrderWithReusableRepresentation() throws Exception {
        Order order = new Order(
                42L,
                7L,
                "Nguyen An",
                BigDecimal.valueOf(1250000),
                OrderStatus.PENDING
        );
        when(orderService.getRequired(42L)).thenReturn(order);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.customerName").value("Nguyen An"))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.customer.href").exists())
                .andExpect(jsonPath("$._links.cancel.href").exists());
    }
}
~~~

Endpoint collection con có thể kiểm tra link self của collection và link customer:

~~~java
mockMvc.perform(get("/api/customers/7/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders.length()").value(1))
    .andExpect(jsonPath("$._embedded.orders[0].id").value(42))
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Đây là các đoạn kiểm thử minh họa. Các kiểu Order, OrderStatus, OrderService, controller và assembler cần được khai báo trong package của ứng dụng. Mỗi test slice phải import assembler mà controller sử dụng và mock các service phụ thuộc.

Nên kiểm thử thêm:

- Cùng một Order có cùng các trường DTO ở endpoint chi tiết và collection.
- Link self của từng phần tử trỏ đến endpoint chi tiết Order.
- Link customer trỏ đúng khách hàng sở hữu đơn hàng.
- Link cancel chỉ xuất hiện khi trạng thái cho phép.
- Collection toàn cục có link self của /api/orders.
- Collection con có link self của /api/customers/{id}/orders và link customer.
- Collection rỗng vẫn có link collection phù hợp.

Nếu cần kiểm thử mapper riêng, có thể dùng unit test không cần Spring context. Nếu cần xác nhận link tuyệt đối, hãy thiết lập request context phù hợp; tránh khóa test vào hostname và cổng cố định nếu chúng thay đổi theo môi trường.

## 12. Những lỗi thường gặp

**Mỗi controller tự tạo DTO và link.** Cùng một resource có thể có representation khác nhau giữa endpoint. Đưa quy tắc biểu diễn item vào assembler dùng chung.

**Assembler truy vấn repository.** Điều này khiến assembler khó kiểm thử và trộn trách nhiệm truy xuất dữ liệu với trình bày. Service nên chuẩn bị dữ liệu trước khi gọi assembler.

**Assembler thực hiện nghiệp vụ.** Không hủy đơn hàng hoặc thay đổi trạng thái trong toModel. Assembler chỉ mô tả tài nguyên và khả năng điều hướng.

**Gắn link collection theo ngữ cảnh vào assembler item.** Một item có thể xuất hiện trong nhiều collection. Để controller hoặc collection assembler tạo link self và link cha của collection hiện tại.

**Dùng một assembler cho mọi loại representation.** Summary, detail và phiên bản API khác nhau có thể có hợp đồng khác nhau. Tạo assembler riêng khi cấu trúc công khai thực sự khác.

**Tạo vòng phụ thuộc giữa các assembler.** Các assembler nên có phụ thuộc một chiều. Dùng link relation để kết nối resource thay vì inject qua lại.

**Dùng cờ boolean để thay đổi representation.** Một assembler với nhiều tổ hợp tùy chọn khó hiểu và dễ sinh output không nhất quán. Dùng kiểu DTO và assembler chuyên biệt theo use case.

**Tin rằng link đã cấp quyền thực hiện hành động.** Link chỉ hỗ trợ khám phá. Endpoint phải kiểm tra quyền và trạng thái khi nhận request.

## 13. Ghi nhớ

RepresentationModelAssembler<T, D> chuẩn hóa cách chuyển một đối tượng nguồn thành representation. toModel tạo EntityModel hoặc kiểu RepresentationModel phù hợp; toCollectionModel dùng lại toModel cho từng phần tử và tạo CollectionModel. Nhờ vậy, cùng một assembler có thể được inject vào endpoint chi tiết, danh sách tổng thể và collection con.

Hãy để assembler chịu trách nhiệm về DTO và link gắn với từng tài nguyên. Controller hoặc thành phần collection riêng bổ sung link phụ thuộc vào endpoint như self của collection hoặc link quay về resource cha. Service chuẩn bị dữ liệu và thực hiện nghiệp vụ; mapper riêng chỉ nên được tách khi quy tắc chuyển đổi đủ phức tạp hoặc có nhu cầu tái sử dụng.

Tái sử dụng assembler khi hợp đồng representation giống nhau. Khi summary, detail, version hoặc profile có cấu trúc công khai khác nhau, hãy tạo DTO và assembler riêng. Kiểm thử nhiều endpoint để xác nhận cùng một resource có biểu diễn nhất quán và collection vẫn có liên kết phù hợp với ngữ cảnh của nó.
