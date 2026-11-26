# Khi nào tự viết assembler

Trong Spring HATEOAS, assembler chuyển đối tượng nghiệp vụ thành representation mà REST API công bố cho client. Không phải endpoint nào cũng cần một lớp assembler riêng. Khi response chỉ là DTO đơn giản và không có liên kết, controller có thể trả DTO trực tiếp. Khi một response chỉ cần một vài link đơn giản tại một nơi, có thể tạo `EntityModel` ngay trong controller. Nên tự viết assembler khi việc chuyển đổi dữ liệu và tạo link trở thành quy tắc biểu diễn cần dùng lại, có điều kiện nghiệp vụ hoặc cần kiểm thử độc lập.

`RepresentationModelAssembler<T, D>` cung cấp hợp đồng phổ biến cho việc này: `T` là kiểu đối tượng nguồn, còn `D` là kiểu representation đích. Phương thức `toModel(T)` chuyển một item; phương thức `toCollectionModel(...)` mặc định giúp áp dụng cùng quy tắc cho một tập hợp. Tự viết assembler tạo một ranh giới rõ ràng giữa dữ liệu nghiệp vụ và hợp đồng hypermedia của API.

## Ba lựa chọn khi xây dựng response

Trước khi tạo assembler, hãy xác định độ phức tạp và khả năng tái sử dụng của response.

| Cách làm | Khi phù hợp | Ví dụ |
|---|---|---|
| Trả DTO trực tiếp | Response chỉ chứa dữ liệu, không cần link hypermedia | Endpoint nội bộ trả trạng thái xử lý đơn giản |
| Tạo `EntityModel` tại controller | Một endpoint có vài link tĩnh, logic biểu diễn ngắn và không lặp lại | Endpoint nhỏ trả một tài nguyên cùng `self` |
| Tự viết assembler | Có nhiều link, mapping DTO, điều kiện theo trạng thái hoặc cùng representation được dùng ở nhiều endpoint | Nhiều endpoint cùng trả đơn hàng với `self`, `customer`, `cancel` |

Ví dụ DTO không cần hypermedia:

```java
import org.springframework.web.bind.annotation.GetMapping;

public record HealthResponse(String status, String version) {}

@GetMapping("/health")
public HealthResponse health() {
    return new HealthResponse("UP", "1.0");
}
```

Không cần tạo assembler chỉ để bọc một DTO không có link. Nếu API cần khả năng điều hướng, có thể dùng `EntityModel` trực tiếp khi logic tạo link thực sự nhỏ:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping("/{id}")
public EntityModel<CustomerResponse> one(@PathVariable UUID id) {
    Customer customer = service.findRequired(id);
    CustomerResponse content = mapper.toResponse(customer);

    return EntityModel.of(
            content,
            linkTo(methodOn(CustomerController.class).one(id)).withSelfRel()
    );
}
```

Nếu chỉ một endpoint sử dụng cách biểu diễn này và không có quy tắc phức tạp, tạo thêm một lớp assembler có thể không đem lại lợi ích đáng kể. Khi cùng logic xuất hiện ở nhiều nơi hoặc bắt đầu có nhiều điều kiện, hãy tách nó ra.

## Dấu hiệu nên tự viết assembler

### 1. Nhiều endpoint cần cùng representation

Một tài nguyên có thể được trả từ endpoint chi tiết, kết quả tìm kiếm, danh sách nổi bật hoặc một workflow khác. Nếu các endpoint cần cùng trường dữ liệu và cùng link, assembler giúp chúng dùng chung một quy tắc.

Ví dụ, mọi response đơn hàng đều cần:

- Các trường công khai như ID, trạng thái và tổng tiền.
- Link `self` tới endpoint đọc đơn hàng.
- Link `customer` tới khách hàng liên quan.
- Link `cancel` khi đơn hàng còn có thể hủy.

Nếu mỗi controller tự tạo các trường và link, một endpoint có thể quên `customer`, endpoint khác có thể vẫn hiển thị `cancel` sau khi đơn hàng đã giao. Assembler tập trung cách biểu diễn để tránh những khác biệt không chủ ý.

### 2. Mapping domain object sang DTO có nhiều quy tắc

Domain object thường chứa dữ liệu phục vụ xử lý nội bộ, còn API chỉ nên công bố một phần. Nếu việc chuyển đổi có tính toán, chuẩn hóa hoặc lựa chọn trường theo hợp đồng, assembler là nơi phù hợp để thực hiện mapping representation.

Ví dụ, `Order` có thể chứa thông tin thanh toán, dữ liệu vận chuyển và ghi chú nội bộ. `OrderResponse` chỉ công bố ID, trạng thái, tổng tiền và ngày tạo. Assembler chuyển domain object sang DTO này trước khi gắn link.

Nếu mapping DTO quá phức tạp, có thể tách phần chuyển đổi dữ liệu sang mapper riêng rồi để assembler tập trung vào việc tạo representation và link. Không cần buộc assembler sở hữu mọi quy tắc chuyển đổi của toàn bộ domain.

### 3. Link phụ thuộc trạng thái hoặc khả năng hiện tại

Một số action link chỉ hợp lệ ở những trạng thái nhất định. Ví dụ, đơn hàng `PENDING` có thể có `cancel`; đơn hàng `SHIPPED` có thể có `tracking`; đơn hàng `DELIVERED` có thể có `review`.

Assembler có thể thêm link theo trạng thái:

```java
if (order.canBeCancelled()) {
    model.add(linkTo(methodOn(OrderController.class).cancel(id))
            .withRel("cancel"));
}
```

Khi client thấy relation `cancel`, nó biết server đang công bố hướng tương tác đó cho đơn hàng hiện tại. Khi link không xuất hiện, client có thể ẩn thao tác tương ứng. Endpoint vẫn phải xác thực quyền và kiểm tra trạng thái khi nhận request; link chỉ mô tả khả năng được công bố tại thời điểm tạo response.

Nếu khả năng phụ thuộc quyền người dùng, đừng để assembler tự suy đoán quyền bằng cách lặp lại quy tắc bảo mật. Hãy cung cấp thông tin capability đã được tính toán bởi service hoặc authorization layer, hoặc dùng một collaborator chuyên trách nếu kiến trúc yêu cầu. Việc thực thi quyền vẫn thuộc server ở endpoint.

### 4. Cần kiểm thử quy tắc biểu diễn độc lập

Khi assembler quyết định trường nào xuất hiện, relation nào được thêm hoặc khi nào action link bị ẩn, các quy tắc này nên có unit test riêng. Một assembler rõ ràng giúp kiểm thử các trường hợp như:

- Đơn hàng đang chờ xử lý có link `cancel`.
- Đơn hàng đã giao không có link `cancel`.
- Tài nguyên có khách hàng liên quan có link `customer`.
- Representation không công bố trường nội bộ của domain object.

Nếu logic tạo link chỉ có một dòng và không có khả năng tái sử dụng, kiểm thử trực tiếp ở controller có thể đã đủ. Assembler riêng đáng giá khi nó tạo ra một đơn vị hành vi có thể kiểm thử và bảo trì độc lập.

## Ví dụ: assembler cho đơn hàng

Giả sử API công bố một DTO:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderResponse(
        UUID id,
        String status,
        BigDecimal total,
        Instant createdAt
) {}
```

Assembler chuyển `Order` thành `EntityModel<OrderResponse>` và thêm các link cần thiết:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        UUID id = order.getId();

        OrderResponse content = new OrderResponse(
                id,
                order.getStatus().name(),
                order.getTotal(),
                order.getCreatedAt()
        );

        EntityModel<OrderResponse> model = EntityModel.of(
                content,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
                linkTo(methodOn(OrderController.class).all()).withRel("orders")
        );

        if (order.getCustomerId() != null) {
            model.add(linkTo(methodOn(CustomerController.class)
                    .one(order.getCustomerId())).withRel("customer"));
        }

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel"));
        }

        return model;
    }
}
```

Assembler này có lý do rõ ràng để tồn tại: mapping content, tạo nhiều link và áp dụng điều kiện cho link `customer` và `cancel`. Các endpoint trả đơn hàng có thể dùng chung `toModel(...)`.

Controller giữ trách nhiệm điều phối request:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> one(@PathVariable UUID id) {
        return assembler.toModel(service.findRequired(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderResponse>> all() {
        return assembler.toCollectionModel(service.findAll())
                .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancel")
    public ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

Endpoint chi tiết dùng `toModel(...)`. Endpoint collection dùng `toCollectionModel(...)`, vì vậy từng item vẫn được chuyển đổi theo cùng quy tắc. Link `self` được thêm sau đó là link của collection, trỏ tới danh sách đơn hàng.

## Khi nào không nên tự viết assembler?

Assembler là một abstraction hữu ích, nhưng không phải quy tắc bắt buộc cho mọi response. Có thể chưa cần assembler riêng trong các trường hợp sau:

- Response chỉ là DTO đơn giản, không có hypermedia link.
- Một endpoint duy nhất tạo một `EntityModel` với một hoặc hai link đơn giản.
- Mapping chỉ sao chép vài trường, không có logic dùng lại hoặc điều kiện biểu diễn.
- Việc tạo assembler khiến một lớp nhỏ bị chia thành nhiều abstraction mà không tăng khả năng tái sử dụng hay kiểm thử.

Trong trường hợp này, dùng DTO hoặc tạo `EntityModel` trực tiếp sẽ giúp luồng xử lý dễ đọc hơn. Có thể tách assembler sau khi quy tắc biểu diễn phát triển hoặc được dùng lại ở nhiều nơi.

## Tránh biến assembler thành service nghiệp vụ

Assembler chịu trách nhiệm biểu diễn, không nên trở thành nơi điều phối toàn bộ nghiệp vụ. Tránh để assembler:

- Tự truy vấn nhiều repository để tìm dữ liệu liên quan.
- Thực hiện cập nhật trạng thái hoặc gọi thao tác ghi dữ liệu.
- Tự thực thi authorization thay cho security/service layer.
- Chứa quy trình nghiệp vụ dài hoặc nhiều quyết định không liên quan tới representation.

Nếu cần thông tin bổ sung để tạo link, service có thể trả về một projection hoặc object chứa dữ liệu và capability cần thiết. Assembler nhận dữ liệu đã sẵn sàng rồi chuyển thành representation. Điều này giúp tránh N+1 query khi tạo collection và giữ assembler có thể dự đoán, dễ kiểm thử.

Ví dụ, thay vì assembler gọi `customerRepository.findById(...)` cho từng đơn hàng, service có thể truy vấn dữ liệu liên quan theo lô và cung cấp `customerId` trong object đầu vào. Assembler chỉ dùng ID đó để tạo link `customer`.

## Một assembler hay nhiều assembler?

Không nhất thiết mỗi domain type chỉ có một assembler. Một domain object có thể được biểu diễn theo nhiều góc nhìn khác nhau:

| Representation | Nội dung | Link thường có |
|---|---|---|
| `OrderDetailModel` | Chi tiết đơn hàng | `self`, `customer`, `items`, action links |
| `OrderSummaryModel` | Trường tóm tắt cho danh sách | `self`, `details` |
| `OrderAdminModel` | Dữ liệu dành cho giao diện quản trị | Link quản trị theo quyền và trạng thái |

Nếu representation khác nhau về trường dữ liệu hoặc ngữ nghĩa link, tạo assembler riêng như `OrderDetailAssembler` và `OrderSummaryAssembler`. Tránh một assembler duy nhất với nhiều tham số boolean như `includeAdminFields`, `summaryOnly` hoặc `includeActions`, vì caller khó biết hợp đồng response nào sẽ được tạo.

Nếu hai assembler chỉ khác một vài link nhưng cùng representation, có thể trích xuất helper hoặc collaborator nhỏ. Hãy giữ cấu trúc đơn giản và để tên assembler thể hiện rõ loại representation nó tạo ra.

## Kiểm thử assembler

Unit test có thể kiểm tra content và relation mà không cần chạy toàn bộ ứng dụng. Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler = new OrderModelAssembler();

    @Test
    void addsCancelLinkWhenOrderIsPending() {
        Order order = OrderFixtures.pendingOrder();

        EntityModel<OrderResponse> model = assembler.toModel(order);

        assertEquals(order.getId(), model.getContent().id());
        assertTrue(model.hasLink(IanaLinkRelations.SELF));
        assertTrue(model.hasLink("cancel"));
    }

    @Test
    void omitsCancelLinkWhenOrderIsShipped() {
        Order order = OrderFixtures.shippedOrder();

        EntityModel<OrderResponse> model = assembler.toModel(order);

        assertFalse(model.hasLink("cancel"));
    }
}
```

`OrderFixtures` đại diện cho factory dữ liệu kiểm thử của ứng dụng. Vì assembler dùng `WebMvcLinkBuilder`, unit test gọi `toModel(...)` trực tiếp cần có request context phù hợp. Có thể thiết lập request context trong test hoặc dùng MockMvc để xác nhận URI cuối cùng được tạo theo mapping controller.

Kiểm thử HTTP nên xác nhận response HAL thực tế:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists());
```

Unit test bảo vệ quy tắc chuyển đổi và điều kiện link; integration test bảo vệ mapping, serialization và hợp đồng HTTP mà client nhận được.

## Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là “Có” | Hướng xử lý |
|---|---|---|
| Response có cần hypermedia link? | Có | Dùng `EntityModel` hoặc representation kế thừa `RepresentationModel` |
| Chỉ một endpoint có một vài link đơn giản? | Có | Có thể tạo model trực tiếp trong controller |
| Nhiều endpoint dùng cùng quy tắc biểu diễn? | Có | Tự viết assembler |
| Link phụ thuộc trạng thái hoặc capability? | Có | Đặt logic công bố link trong assembler, lấy capability từ lớp nghiệp vụ phù hợp |
| Cùng domain object có nhiều hợp đồng response? | Có | Tạo assembler riêng cho từng representation |
| Assembler cần truy vấn dữ liệu hoặc thực thi nghiệp vụ? | Có | Chuyển phần đó về service/use case trước khi gọi assembler |

## Quy trình quyết định và triển khai

1. Xác định response có cần hypermedia hay chỉ cần DTO.
2. Nếu cần link, đánh giá logic có đủ nhỏ để đặt trực tiếp trong controller hay không.
3. Nếu mapping, link hoặc điều kiện biểu diễn được dùng lại, tạo assembler riêng.
4. Chọn DTO hoặc representation model phù hợp với hợp đồng client.
5. Cài đặt `RepresentationModelAssembler<T, D>` và tập trung logic trong `toModel(...)`.
6. Dùng `toCollectionModel(...)` để tái sử dụng quy tắc item khi tạo collection.
7. Đưa truy vấn dữ liệu, quyền và nghiệp vụ về service hoặc lớp chuyên trách.
8. Kiểm thử content, relation, URI và các trường hợp link xuất hiện/biến mất.

## Kết luận

Hãy tự viết assembler khi một loại tài nguyên có quy tắc biểu diễn đủ phức tạp, được tái sử dụng hoặc cần kiểm thử độc lập. `RepresentationModelAssembler<T, D>` giúp tập trung mapping từ domain object sang representation và tạo link cho item; `toCollectionModel(...)` mở rộng cùng quy tắc đó cho collection. Với response nhỏ và đơn giản, DTO hoặc `EntityModel` tạo trực tiếp vẫn phù hợp. Giữ assembler tập trung vào biểu diễn, để service xử lý truy vấn, quyền và nghiệp vụ, sẽ giúp API Spring HATEOAS dễ đọc và tiến hóa hơn.
