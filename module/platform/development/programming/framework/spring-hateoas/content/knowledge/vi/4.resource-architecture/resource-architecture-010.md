# DTO và resource model

Trong một REST API dùng Spring HATEOAS, dữ liệu trả về cho client thường đi qua nhiều lớp trước khi được serialize thành JSON. Đối tượng domain biểu diễn quy tắc nghiệp vụ; DTO xác định dữ liệu API cần nhận hoặc trả; resource model kết hợp dữ liệu công khai với các liên kết hypermedia. Phân biệt ba khái niệm này giúp API có hợp đồng rõ ràng, tránh phụ thuộc trực tiếp vào cấu trúc cơ sở dữ liệu và cho phép client khám phá tài nguyên qua link.

Ví dụ, hệ thống bán hàng có entity `Order` với quan hệ đến khách hàng, dòng sản phẩm, thanh toán và lịch sử xử lý. Client xem danh sách đơn hàng có thể chỉ cần mã, trạng thái, tổng tiền và link đến chi tiết. Nếu serialize entity trực tiếp, response có thể để lộ trường nội bộ, kéo theo quan hệ không cần thiết hoặc tạo vòng lặp JSON. Một DTO giới hạn dữ liệu công khai, còn resource model gắn thêm link `self`, `customer` hay `cancel` tùy ngữ cảnh.

## Phân biệt domain entity, DTO và resource model

Các đối tượng này có mục đích khác nhau dù đôi khi chứa một số trường giống nhau:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Domain entity / aggregate | Biểu diễn trạng thái và quy tắc nghiệp vụ trong miền ứng dụng. | `Order`, có trạng thái, dòng hàng và hành vi `cancel()`. |
| Request DTO | Mô tả dữ liệu client gửi lên để yêu cầu một thao tác. | `CreateOrderRequest`, gồm địa chỉ giao hàng và danh sách mặt hàng. |
| Response DTO | Mô tả các trường dữ liệu ứng dụng muốn công bố. | `OrderDto`, gồm mã đơn, trạng thái và tổng tiền. |
| Resource model / representation model | Biểu diễn tài nguyên API, thường gồm dữ liệu và link hypermedia. | `EntityModel<OrderDto>` hoặc lớp riêng kế thừa `RepresentationModel`. |

DTO là viết tắt của *Data Transfer Object*. Nó gom dữ liệu qua ranh giới giữa các tầng hoặc qua mạng. DTO không tự mang ý nghĩa hypermedia. Resource model mô tả cách tài nguyên được công bố cho client và có thể thêm link để client đi tiếp từ response.

Trong Spring HATEOAS, từ *representation* chỉ cách tài nguyên được biểu diễn trong response. Representation không nhất thiết giống entity trong cơ sở dữ liệu. Một resource có thể tổng hợp dữ liệu từ nhiều aggregate, ẩn một số thuộc tính hoặc trình bày một góc nhìn riêng cho client. Vì thế, không nên xem mỗi bảng hoặc mỗi JPA entity là một resource API bắt buộc.

## Vì sao không trả trực tiếp entity?

Trả entity JPA trực tiếp có thể có vẻ nhanh ở bước đầu, nhưng làm API phụ thuộc vào mô hình lưu trữ. Những thay đổi như tách bảng, đổi quan hệ hoặc thêm trường nội bộ có thể vô tình làm thay đổi JSON công khai. Entity cũng có thể chứa proxy lazy-loading, quan hệ hai chiều gây vòng lặp serialize, hoặc dữ liệu nhạy cảm không dành cho client.

Một ranh giới API riêng mang lại các lợi ích sau:

- **Kiểm soát dữ liệu công bố:** chỉ đưa trường mà client cần đọc, chẳng hạn `id`, `status`, `totalAmount`.
- **Tách vòng đời:** có thể thay đổi entity hoặc schema lưu trữ mà vẫn giữ response DTO ổn định.
- **Tối ưu theo use case:** danh sách, trang chi tiết và màn hình quản trị có thể dùng các projection khác nhau.
- **Gắn hành vi điều hướng:** resource model có thể chứa link theo trạng thái và quyền hiện tại.
- **Kiểm soát dữ liệu đầu vào:** request DTO xác định rõ trường được phép gửi và áp dụng validation.

DTO cũng cần được thiết kế có chủ đích. Không nên tạo một DTO khổng lồ dùng chung cho mọi request và response nếu các use case có nhu cầu khác nhau. Ví dụ, client có thể gửi `CreateOrderRequest` để tạo đơn, nhưng response của đơn hàng còn chứa `id`, `status`, `totalAmount` và các link mà client không được tự quyết định.

## Thiết kế DTO cho tài nguyên

Giả sử domain có một đơn hàng. DTO phản hồi chỉ công bố những trường cần thiết:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderDto(
        UUID id,
        String status,
        BigDecimal totalAmount
) {
}
```

`OrderDto` là dữ liệu của response. Annotation `@Relation` cho Spring HATEOAS biết tên relation dùng khi loại model này được nhúng trong collection HAL: `orders` cho collection và `order` cho từng item. Annotation này không tạo link và cũng không thay thế các thuộc tính dữ liệu của DTO.

Một request DTO có thể được thiết kế riêng cho thao tác tạo đơn:

```java
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotNull String shippingAddress,
        @NotEmpty List<@Valid OrderLineRequest> lines
) {
}

public record OrderLineRequest(
        @NotNull String productCode,
        @NotNull Integer quantity
) {
}
```

Trong ứng dụng thực tế, nên dùng các constraint phù hợp hơn cho địa chỉ, mã sản phẩm và số lượng, chẳng hạn `@NotBlank` và `@Positive`. Ví dụ tập trung vào ranh giới dữ liệu: client chỉ gửi những trường cần cho thao tác tạo đơn. Server vẫn phải kiểm tra quyền, tồn kho, giá và các quy tắc domain trong tầng nghiệp vụ; validation DTO không thay thế kiểm tra nghiệp vụ.

## Các kiểu resource model trong Spring HATEOAS

Spring HATEOAS cung cấp một số abstraction để tạo representation có link:

| Kiểu | Cách dùng | Khi phù hợp |
| --- | --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho model do ứng dụng tự định nghĩa; model có thể thêm `Link`. | Khi muốn có kiểu resource riêng và kiểm soát cấu trúc dữ liệu ở cấp gốc. |
| `EntityModel<T>` | Bọc một nội dung `T` và các link. | Khi đã có DTO rõ ràng và chỉ cần thêm link vào nội dung đó. |
| `CollectionModel<T>` | Bọc một collection các model cùng các link của collection. | Khi trả danh sách tài nguyên. |
| `PagedModel<T>` | Biểu diễn collection có thông tin phân trang. | Khi API trả kết quả theo trang và cần metadata phân trang. |

`EntityModel<T>` và `CollectionModel<T>` sử dụng cơ chế link của `RepresentationModel`. Tham số generic là kiểu nội dung/model được bọc, không có nghĩa đó phải là entity JPA. Trong nhiều API, `EntityModel<OrderDto>` là lựa chọn đơn giản: dữ liệu tách riêng, link được thêm ở lớp bọc.

### Cách 1: Bọc DTO bằng EntityModel

Một assembler chuyển domain entity thành DTO, rồi bọc DTO trong `EntityModel` và thêm link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.getId(),
                order.getStatus().name(),
                order.getTotalAmount());

        EntityModel<OrderDto> model = EntityModel.of(dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .all()).withRel("orders"));

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId())).withRel("cancel"));
        }

        return model;
    }
}
```

`RepresentationModelAssembler` đặt phép chuyển đổi domain-to-resource ở một nơi. `linkTo(...)` và `methodOn(...)` tạo URI từ mapping của controller, tránh nối chuỗi URL bằng tay. Relation `cancel` chỉ xuất hiện nếu trạng thái hiện tại cho phép thao tác. Trong hệ thống có phân quyền, điều kiện này còn phải xét quyền của người dùng đang thực hiện request.

`Order`, `OrderStatus` và `OrderService` trong ví dụ là các kiểu nghiệp vụ của ứng dụng. Phương thức `canBeCancelled()` đại diện cho quy tắc domain, không phải API có sẵn của Spring. Nếu quy tắc cần dữ liệu người dùng hoặc chính sách phân quyền, assembler có thể nhận thêm một collaborator chuyên kiểm tra khả năng thao tác.

### Cách 2: Tạo resource model riêng kế thừa RepresentationModel

Khi resource có cấu trúc riêng, cần thêm thuộc tính tổng hợp hoặc cần một kiểu rõ ràng cho hợp đồng API, có thể định nghĩa model riêng:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderResource extends RepresentationModel<OrderResource> {

    private final UUID id;
    private final String status;
    private final BigDecimal totalAmount;

    public OrderResource(UUID id, String status, BigDecimal totalAmount) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Assembler của model riêng trả về `OrderResource` và gắn link trực tiếp:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderResourceAssembler
        implements RepresentationModelAssembler<Order, OrderResource> {

    @Override
    public OrderResource toModel(Order order) {
        OrderResource resource = new OrderResource(
                order.getId(), order.getStatus().name(), order.getTotalAmount());

        resource.add(linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());
        resource.add(linkTo(methodOn(OrderController.class)
                .all()).withRel("orders"));

        return resource;
    }
}
```

Ở cách này, các thuộc tính dữ liệu và link cùng nằm trên resource model. `RepresentationModel<OrderResource>` dùng generic self type để các thao tác trên model giữ kiểu cụ thể. Model có thể thêm các trường được tính toán như `displayStatus`, `canReview` hoặc thông tin tổng hợp mà không cần để lộ cấu trúc domain.

Hai cách trên là các lựa chọn thiết kế. `EntityModel<DTO>` phù hợp khi DTO đã mô tả đầy đủ dữ liệu và muốn thêm link bằng một wrapper. Model riêng kế thừa `RepresentationModel` hữu ích khi resource có danh tính và cấu trúc công khai riêng, hoặc cần được tái sử dụng ở nhiều endpoint. Tránh tạo model riêng chỉ để đổi tên một wrapper mà không mang lại lợi ích rõ ràng.

## Kết hợp resource model với controller

Controller nên điều phối HTTP và gọi service/assembler. Nó không cần tự chuyển entity thành JSON hay tự ghép từng URL:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<OrderDto> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<EntityModel<OrderDto>> all() {
        List<EntityModel<OrderDto>> orders = service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping
    ResponseEntity<EntityModel<OrderDto>> create(
            @Valid @RequestBody CreateOrderRequest request) {
        Order created = service.create(request);
        EntityModel<OrderDto> response = assembler.toModel(created);
        return ResponseEntity.created(response.getRequiredLink("self").toUri())
                .body(response);
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

`create` dùng link `self` của resource vừa tạo làm URI trong header `Location`. Cách này giúp response và header trỏ đến cùng một địa chỉ. Trong một ứng dụng thực tế, service có thể nhận một command object được ánh xạ từ request DTO; ví dụ dùng trực tiếp request để làm rõ luồng, nhưng tầng domain không nên phụ thuộc vào kiểu HTTP.

`CollectionModel` giúp response danh sách có link của collection và từng phần tử. Nếu dùng phân trang, có thể trả về `PagedModel` để biểu diễn metadata trang cùng các link điều hướng như `first`, `prev`, `self`, `next` và `last`. Client nên đi theo các relation được công bố thay vì tự tính URL trang tiếp theo.

## Dữ liệu nhúng và liên kết tài nguyên

Resource model có thể biểu diễn quan hệ giữa các tài nguyên bằng link. Ví dụ, đơn hàng có thể có link `customer` đến khách hàng và link `items` đến các dòng hàng. Nếu API chọn nhúng một tài nguyên liên quan trong response, HAL biểu diễn nó dưới `_embedded` với relation tương ứng.

Nên chọn giữa link và embedded resource theo nhu cầu của client:

- Dùng link khi client có thể truy cập tài nguyên liên quan qua endpoint riêng, hoặc dữ liệu liên quan thay đổi độc lập.
- Dùng embedded resource khi client thường cần dữ liệu đó cùng lúc và việc nhúng giúp giảm số lần gọi API.
- Dùng cả hai khi client cần dữ liệu tóm tắt ngay lập tức nhưng vẫn cần link đến representation đầy đủ.

Không nên nhúng toàn bộ đồ thị entity chỉ vì các quan hệ tồn tại trong database. Việc nhúng cần được thiết kế ở cấp API, có giới hạn độ sâu và dữ liệu rõ ràng. Điều này tránh response quá lớn, lặp dữ liệu và tạo hợp đồng khó tiến hóa.

## Resource model và khả năng thao tác

Một resource model có thể chứa link điều hướng và link hành động. Link `self` trỏ đến tài nguyên hiện tại; `orders` dẫn về collection; `cancel` thể hiện thao tác có thể thực hiện trong ngữ cảnh hiện tại. Với thao tác có dữ liệu đầu vào hoặc cần mô tả HTTP method, có thể dùng affordance và định dạng như HAL-FORMS để mô tả thêm biểu mẫu.

Sự xuất hiện của link hành động nên phản ánh trạng thái nghiệp vụ và quyền hiện tại. Tuy nhiên, link không phải hàng rào bảo mật: endpoint vẫn phải xác thực, kiểm tra quyền và xác minh trạng thái khi client gửi request. Client cũng phải chấp nhận rằng khả năng thao tác có thể thay đổi giữa lúc đọc representation và lúc gửi lệnh.

## Kiểm thử ranh giới DTO và resource model

Kiểm thử API nên xác minh dữ liệu công khai, link và media type. Ví dụ với MockMvc:

```java
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
class OrderResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void detailReturnsDtoFieldsAndResourceLinks() throws Exception {
        mockMvc.perform(get("/api/orders/{id}",
                        "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.status").exists())
                .andExpect(jsonPath("$.totalAmount").exists())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.orders.href").exists());
    }

    @Test
    void collectionEmbedsOrdersAndExposesSelfLink() throws Exception {
        mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._embedded.orders").isArray());
    }
}
```

Các UUID trong ví dụ cần tồn tại trong dữ liệu kiểm thử. Tên thuộc tính JSON phụ thuộc cấu hình Jackson; nếu ứng dụng dùng naming strategy như `SNAKE_CASE`, hãy điều chỉnh JSONPath tương ứng. Khi kiểm thử, nên xác nhận thêm những trường nội bộ không được công bố, relation chỉ xuất hiện ở trạng thái phù hợp và response tạo mới có header `Location` trỏ đến link `self`.

Một số lỗi thiết kế thường gặp:

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Trả thẳng JPA entity | Lộ trường nội bộ, lazy loading hoặc vòng lặp serialize. | Ánh xạ entity sang DTO trước khi tạo resource model. |
| Dùng một DTO cho mọi endpoint | Response chứa nhiều trường thừa hoặc request cho phép gửi trường không cần thiết. | Thiết kế DTO theo use case và hướng dữ liệu. |
| DTO tự chứa URL ghép bằng chuỗi | Client và server phụ thuộc vào cấu trúc route. | Để assembler thêm link bằng `linkTo` và `methodOn`. |
| Nhầm DTO với `EntityModel` | Không rõ phần nào là dữ liệu, phần nào là hypermedia. | Dùng DTO cho payload; dùng model HATEOAS để thêm link. |
| Nhúng toàn bộ quan hệ domain | Response lớn và hợp đồng phụ thuộc sâu vào schema lưu trữ. | Chọn link hoặc embedded resource theo nhu cầu client. |

## Giữ hợp đồng tài nguyên có thể tiến hóa

Resource model là một phần của hợp đồng công khai. Khi đổi cấu trúc database, có thể giữ nguyên DTO và relation để client không cần biết chi tiết lưu trữ. Khi bổ sung trường tùy chọn, client cũ thường có thể bỏ qua nếu được thiết kế đúng. Khi đổi tên thuộc tính, xóa trường bắt buộc hoặc đổi ý nghĩa relation, cần xem đó là thay đổi tương thích và có chiến lược phiên bản hoặc chuyển tiếp phù hợp.

Hãy giữ relation ổn định theo ý nghĩa nghiệp vụ. URI nên được tạo từ mapping của server và được client lấy từ link. Đặt quy tắc chuyển đổi domain-to-DTO trong mapper hoặc assembler để các endpoint không tạo ra những biến thể response khác nhau ngoài dự kiến. Kiểm thử JSON, media type và relation quan trọng như kiểm thử bất kỳ phần nào khác của hợp đồng API.

Khi phân chia rõ entity, DTO và resource model, ứng dụng có thể thay đổi mô hình nội bộ mà vẫn cung cấp một representation nhất quán. DTO kiểm soát dữ liệu đi qua ranh giới API; resource model bổ sung các quan hệ hypermedia để client khám phá tài nguyên và hành động tiếp theo.
