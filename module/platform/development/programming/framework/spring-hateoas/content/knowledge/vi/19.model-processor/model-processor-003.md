# Processor cho item

## Mục tiêu

Sau bài này, bạn có thể dùng `RepresentationModelProcessor` để bổ sung liên kết cho representation của một item trong Spring HATEOAS, xác định đúng kiểu model mà processor cần xử lý, phân biệt processor với assembler và processor của collection, tránh tạo link trùng và kiểm thử hành vi tự động áp dụng processor trong response HAL.

## 1. Processor cho item giải quyết vấn đề gì?

Một API có thể trả về cùng một loại tài nguyên từ nhiều luồng xử lý. Ví dụ, đơn hàng có thể được trả về từ endpoint chi tiết, kết quả tìm kiếm hoặc một thao tác nghiệp vụ. Các representation này đều có thể cần một số liên kết chung như:

- Link `self` đến chính đơn hàng.
- Link `customer` đến khách hàng liên quan.
- Link `cancel` nếu đơn hàng còn được phép hủy.
- Link `invoice` nếu hóa đơn đã được phát hành.

Nếu mỗi nơi tự thêm cùng một nhóm link, logic dễ bị lặp và có thể không nhất quán. Spring HATEOAS cung cấp `RepresentationModelProcessor` như một điểm mở rộng để bổ sung hoặc điều chỉnh representation model trước khi model được trả về cho client.

Với processor cho item, tham số kiểu thường là `EntityModel<Order>` hoặc lớp representation cụ thể như `OrderModel`. Processor nhận model đã được tạo, đọc nội dung và các link hiện có, sau đó bổ sung những link dùng chung.

## 2. RepresentationModelProcessor là gì?

`RepresentationModelProcessor<T>` là interface trong package `org.springframework.hateoas.server`. Kiểu `T` xác định representation model mà processor nhận và trả về.

Ví dụ, nếu controller trả `EntityModel<Order>`, có thể khai báo:

```java
@Component
public class OrderItemProcessor
        implements RepresentationModelProcessor<EntityModel<Order>> {

    @Override
    public EntityModel<Order> process(EntityModel<Order> model) {
        // Bổ sung hoặc điều chỉnh link của item.
        return model;
    }
}
```

Spring HATEOAS có cơ chế phát hiện các processor được đăng ký thành bean và gọi processor phù hợp trong quá trình xử lý representation. Nhờ vậy, controller không cần gọi thủ công `process(...)` mỗi lần trả item.

Các điểm cần nhớ:

- `T` phải khớp với kiểu representation mà processor cần xử lý.
- Processor nhận một representation model, không nhận trực tiếp HTTP request hay domain repository.
- Processor nên trả về model sau khi xử lý.
- Processor có thể đọc nội dung model và các link đã được assembler thêm trước đó.
- Processor không thay thế việc xác thực, phân quyền hoặc kiểm tra quy tắc nghiệp vụ ở endpoint.

Nếu ứng dụng dùng `OrderModel extends RepresentationModel<OrderModel>` thay vì `EntityModel<Order>`, kiểu processor nên là `RepresentationModelProcessor<OrderModel>`. Khai báo đúng kiểu giúp Spring xác định processor nào phù hợp với representation.

## 3. Tạo processor cho EntityModel của một item

Giả sử assembler đã tạo `EntityModel<Order>` với link `self`. Ta muốn mọi response item đơn hàng đều có link `cancel` khi trạng thái cho phép, kể cả khi item được trả về từ nhiều endpoint.

Processor có thể thực hiện điều đó:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderItemProcessor
        implements RepresentationModelProcessor<EntityModel<Order>> {

    private final OrderActionPolicy actionPolicy;

    public OrderItemProcessor(OrderActionPolicy actionPolicy) {
        this.actionPolicy = actionPolicy;
    }

    @Override
    public EntityModel<Order> process(EntityModel<Order> model) {
        Order order = model.getContent();

        if (actionPolicy.canCancel(order)
                && model.getLink("cancel").isEmpty()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancelOrder(order.getId(), null))
                    .withRel("cancel"));
        }

        return model;
    }
}
```

Giải thích:

1. `EntityModel<Order>` cho biết processor xử lý representation của một đơn hàng.
2. `getContent()` lấy domain object đang được bao trong model.
3. `actionPolicy.canCancel(order)` hỏi policy của ứng dụng xem hành động có khả dụng trong ngữ cảnh hiện tại hay không.
4. `getLink("cancel").isEmpty()` tránh thêm một link cùng relation nếu assembler đã tạo link đó.
5. `linkTo(methodOn(...))` tạo href theo mapping của endpoint hủy.
6. `return model` trả representation đã được bổ sung.

Đối số `null` trong lời gọi `cancelOrder(..., null)` là giá trị giữ chỗ để Spring HATEOAS phân tích chữ ký phương thức có request body. `methodOn` không gửi request và không thực hiện thao tác hủy. Relation `cancel` cho biết ý nghĩa của link; nếu client cần biết HTTP method và schema đầu vào, hãy mô tả thêm affordance phù hợp.

Ví dụ giả định controller có mapping tương ứng:

```java
@GetMapping("/{id}")
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}

@PostMapping("/{id}/cancellations")
public EntityModel<Order> cancelOrder(
        @PathVariable UUID id,
        @RequestBody CancellationRequest request) {
    Order cancelled = orderService.cancel(id, request.reason());
    return assembler.toModel(cancelled);
}
```

Processor là bean Spring nên cần được component scan hoặc đăng ký trong cấu hình ứng dụng. Với Spring Boot và starter HATEOAS, hạ tầng xử lý hypermedia thường được auto-configure.

## 4. Processor phối hợp với assembler như thế nào?

Assembler và processor đều tác động đến representation, nhưng có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| `RepresentationModelAssembler` | Chuyển domain object thành representation | Tạo `EntityModel<Order>`, ánh xạ trường và link `self` |
| `RepresentationModelProcessor` | Bổ sung hoặc điều chỉnh model đã được tạo | Thêm link chung `cancel` cho item đủ điều kiện |
| Controller | Điều phối request và trả representation | Gọi service, gọi assembler, trả model |
| Service/domain | Cung cấp dữ liệu và quy tắc nghiệp vụ | Xác định đơn hàng có thể hủy hay không |

Một cách tổ chức rõ ràng là để assembler tạo dữ liệu và các link cốt lõi của tài nguyên, còn processor xử lý các liên kết dùng chung cho nhiều response cùng kiểu model.

Ví dụ assembler:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .getOrder(order.getId())).withSelfRel()
        );
    }
}
```

Processor sau đó có thể bổ sung link `cancel` mà không cần lặp lại ánh xạ `self`. Controller chỉ cần gọi assembler:

```java
@GetMapping("/{id}")
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Khi response được Spring HATEOAS xử lý, processor phù hợp sẽ được áp dụng theo kiểu representation. Nhờ đó, các endpoint trả cùng kiểu `EntityModel<Order>` có thể chia sẻ logic bổ sung link.

Không nên để assembler và processor cùng sở hữu một relation mà không có quy ước. Nếu cả hai đều thêm `cancel`, cần kiểm tra relation hiện có như ví dụ trên hoặc chuyển quyền tạo link về một thành phần duy nhất. Tránh phụ thuộc vào việc link trùng sẽ được serializer xử lý ra sao.

## 5. Công bố link theo trạng thái và quyền truy cập

Processor thường hữu ích khi một link chung phụ thuộc vào nội dung item. Ví dụ, đơn hàng ở trạng thái `PENDING` có thể hủy; đơn hàng đã giao hoặc đã hủy thì không.

| Trạng thái đơn hàng | Link `cancel` |
|---|---|
| `PENDING` | Có thể công bố nếu người dùng có quyền |
| `PAID` | Tùy quy tắc nghiệp vụ |
| `SHIPPED` | Thông thường không công bố |
| `CANCELLED` | Không công bố |

Bảng chỉ minh họa; điều kiện thực tế phải theo quy tắc của ứng dụng. Nếu khả năng hủy phụ thuộc quyền người dùng, processor cần nhận được thông tin quyền hoặc kết quả kiểm tra từ một thành phần phù hợp. Không nên tự suy đoán quyền từ dữ liệu item.

Có thể dùng một policy chuyên trách để đưa ra quyết định. Ví dụ, hợp đồng của policy có thể đơn giản như sau:

```java
public interface OrderActionPolicy {
    boolean canCancel(Order order);
}
```

`OrderActionPolicy` được inject vào processor ở phần trước. Policy có thể kết hợp trạng thái đơn hàng với quyền của người dùng hiện tại. Nếu policy cần security context, hãy bảo đảm nó được gọi trong đúng request context và có kiểm thử cho người dùng với quyền khác nhau. Không nên đưa truy vấn repository hoặc lời gọi dịch vụ từ xa vào processor nếu policy hoặc service có thể cung cấp quyết định hiệu quả hơn.

Việc không công bố link chỉ giúp client hiểu hành động hiện không khả dụng. Server vẫn phải kiểm tra trạng thái và quyền tại endpoint hủy, vì client có thể gửi request trực tiếp hoặc sử dụng response cũ.

## 6. Processor cho item và processor cho collection

Kiểu generic của processor xác định cấp representation mà nó xử lý. Ví dụ:

```java
RepresentationModelProcessor<EntityModel<Order>>
```

nhắm đến model của một item đơn hàng, trong khi:

```java
RepresentationModelProcessor<CollectionModel<EntityModel<Order>>>
```

nhắm đến model collection bao gồm các item đơn hàng.

Hai loại này không nên bị nhầm lẫn:

- Item processor thêm link hoặc metadata vào representation của một đơn hàng.
- Collection processor thêm link hoặc metadata cấp tập hợp, ví dụ `self`, `search`, `create` hoặc thông tin điều hướng.
- Nếu muốn mọi phần tử nhúng trong collection có link riêng, hãy bảo đảm assembler của từng item tạo các link đó. Đừng mặc định rằng processor dành cho collection sẽ tự xử lý từng phần tử bên trong.

Ví dụ một processor cấp collection:

```java
@Component
public class OrderCollectionProcessor
        implements RepresentationModelProcessor<
                CollectionModel<EntityModel<Order>>> {

    @Override
    public CollectionModel<EntityModel<Order>> process(
            CollectionModel<EntityModel<Order>> model) {

        if (model.getLink("self").isEmpty()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .getOrders()).withSelfRel());
        }

        return model;
    }
}
```

Ví dụ này thêm self link cấp collection nếu chưa có. Nếu collection được lọc hoặc phân trang, link self cần giữ đúng query parameter của request hiện tại; khi đó có thể dùng link builder phù hợp với mapping và ngữ cảnh truy vấn thay vì tạo link gốc không có bộ lọc.

## 7. Tránh processor làm tăng độ phức tạp

Processor được gọi tự động, vì vậy một thay đổi nhỏ có thể ảnh hưởng đến nhiều endpoint trả cùng kiểu representation. Hãy giữ processor tập trung và dễ dự đoán:

- Chỉ thêm hoặc điều chỉnh link thuộc trách nhiệm chung của processor.
- Không thực hiện truy vấn N+1 cho từng item trong collection.
- Không gọi dịch vụ từ xa chỉ để quyết định có thêm link hay không nếu dữ liệu đó có thể được cung cấp từ service hoặc policy đã có.
- Không thay đổi nội dung domain object trong processor.
- Tránh tạo link trùng relation; kiểm tra link hiện có trước khi thêm.
- Giữ processor idempotent: xử lý cùng một model nhiều lần không nên tạo thêm link trùng hoặc làm thay đổi kết quả ngoài dự kiến.

Nếu cần dữ liệu nghiệp vụ để tạo link, cân nhắc để service hoặc assembler cung cấp dữ liệu đó sẵn trong model. Processor không nên trở thành một lớp điều phối nghiệp vụ mới.

Cũng cần chú ý đến phạm vi kiểu. Một processor cho `EntityModel<Order>` không nên được kỳ vọng xử lý `EntityModel<Customer>` hoặc một DTO khác chỉ vì chúng đều là representation model. Tạo processor riêng cho từng kiểu hoặc trừu tượng hóa một thành phần dùng chung khi thực sự có cùng semantics.

## 8. Kiểm thử processor trực tiếp

Unit test có thể gọi `process(...)` trực tiếp để xác nhận link được thêm hoặc bỏ qua đúng điều kiện. Vì ví dụ dùng `linkTo(methodOn(...))`, test cần thiết lập request context cho Spring MVC link builder.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class OrderItemProcessorTest {

    private final OrderActionPolicy actionPolicy = mock(OrderActionPolicy.class);
    private final OrderItemProcessor processor =
            new OrderItemProcessor(actionPolicy);

    private ServletRequestAttributes attributes;

    @BeforeEach
    void setUpRequestContext() {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/orders");

        request.setScheme("https");
        request.setServerName("api.example.test");
        request.setServerPort(443);

        attributes = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(attributes);
    }

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.resetRequestAttributes();
        attributes.requestCompleted();
    }

    @Test
    void addsCancelLinkWhenOrderCanBeCancelled() {
        Order order = OrderTestData.pendingOrder();
        given(actionPolicy.canCancel(order)).willReturn(true);
        EntityModel<Order> model = EntityModel.of(order);

        EntityModel<Order> processed = processor.process(model);

        assertThat(processed.getLink("cancel")).isPresent();
        assertThat(processed.getLink("cancel").orElseThrow().getHref())
                .endsWith("/orders/" + order.getId() + "/cancellations");
    }

    @Test
    void doesNotAddCancelLinkWhenOrderCannotBeCancelled() {
        Order order = OrderTestData.shippedOrder();
        given(actionPolicy.canCancel(order)).willReturn(false);
        EntityModel<Order> model = EntityModel.of(order);

        EntityModel<Order> processed = processor.process(model);

        assertThat(processed.getLink("cancel")).isEmpty();
    }
}
```

`OrderTestData` là test fixture của ứng dụng, cần tạo các đối tượng có trạng thái hợp lệ. Nếu processor dùng `OrderActionPolicy`, hãy inject mock policy vào constructor và kiểm tra cả kết quả policy cho phép lẫn từ chối.

Có thể kiểm tra tính idempotent bằng cách gọi processor hai lần trên cùng model rồi xác nhận chỉ có một link `cancel`:

```java
Order order = OrderTestData.pendingOrder();
given(actionPolicy.canCancel(order)).willReturn(true);
EntityModel<Order> model = EntityModel.of(order);

EntityModel<Order> once = processor.process(model);
EntityModel<Order> twice = processor.process(once);

assertThat(twice.getLink("cancel")).isPresent();
```

Vì processor chỉ thêm link khi `getLink("cancel").isEmpty()`, lần xử lý tiếp theo không thêm lại relation đó. Test trực tiếp xác nhận logic của processor; nó chưa chứng minh Spring tự động phát hiện và áp dụng bean processor trong response controller, nên vẫn cần integration test.

## 9. Kiểm thử processor được áp dụng tự động bằng MockMvc

Dùng MockMvc để kiểm tra pipeline Spring MVC và serialization HAL. Trong test slice, import processor nếu component không được quét tự động:

```java
@WebMvcTest(OrderController.class)
@Import({OrderModelAssembler.class, OrderItemProcessor.class})
class OrderItemProcessorWebTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @MockBean
    private OrderActionPolicy actionPolicy;

    @Test
    void appliesItemProcessorToOrderResponse() throws Exception {
        UUID id = UUID.fromString(
                "8d1f1e3c-4c21-4e3f-a4e1-1f2e3d4c5b6a");
        Order order = OrderTestData.pendingOrder(id);

        given(orderService.getRequired(id)).willReturn(order);
        given(actionPolicy.canCancel(order)).willReturn(true);

        mockMvc.perform(get("/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.cancel.href")
                    .value(endsWith("/orders/" + id + "/cancellations")));
    }
}
```

Test này xác nhận controller trả `EntityModel<Order>`, processor đã được đăng ký trong application context và response HAL có link `cancel` khi trạng thái cho phép.

Nên có thêm test cho trạng thái không cho phép:

```java
Order shippedOrder = OrderTestData.shippedOrder(id);
given(orderService.getRequired(id)).willReturn(shippedOrder);
given(actionPolicy.canCancel(shippedOrder)).willReturn(false);

mockMvc.perform(get("/orders/{id}", id)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Nếu processor không xuất hiện trong response, kiểm tra:

1. Processor có được đăng ký thành Spring bean không?
2. Kiểu generic có khớp với model mà controller trả về không?
3. Controller có trả representation model hay trả DTO/entity thuần?
4. Test slice có import processor và cấu hình HATEOAS cần thiết không?
5. Client có yêu cầu đúng media type hypermedia không?

## 10. Những lỗi thường gặp

**Khai báo sai kiểu generic.** Processor dành cho `EntityModel<Order>` không tự động trở thành processor cho `EntityModel<Customer>` hoặc `OrderModel`. Khai báo đúng kiểu representation cần xử lý.

**Gọi processor thủ công ở mọi controller.** Khi đã đăng ký processor theo cơ chế Spring HATEOAS, hãy để pipeline áp dụng processor phù hợp. Việc gọi thêm thủ công có thể khiến logic chạy hai lần.

**Thêm link đã tồn tại.** Nếu assembler và processor cùng tạo relation, response có thể chứa link trùng hoặc hành vi khó đoán. Kiểm tra link hiện tại và quy định rõ thành phần sở hữu relation.

**Đưa truy vấn nghiệp vụ vào processor.** Processor có thể được gọi cho nhiều response. Truy vấn bổ sung trong mỗi lần xử lý dễ làm tăng độ trễ và tạo N+1. Dùng dữ liệu đã có hoặc policy/service được thiết kế phù hợp.

**Dùng item processor để thêm link collection.** Link cấp tập hợp thuộc collection representation. Hãy dùng collection processor hoặc assembler tạo collection.

**Chỉ unit test mà không kiểm tra pipeline.** Gọi `process(...)` trực tiếp không chứng minh Spring tự động áp dụng bean. Bổ sung MockMvc test cho response thực tế.

**Xem link là cơ chế bảo mật.** Processor ẩn link không ngăn client gửi request. Endpoint vẫn phải xác thực và phân quyền.

## 11. Khi nào nên dùng processor cho item?

Dùng `RepresentationModelProcessor<EntityModel<T>>` khi một quy tắc bổ sung link áp dụng chung cho nhiều response của cùng loại item và dữ liệu cần thiết đã có trong representation.

Dùng assembler khi logic gắn với việc chuyển một domain object cụ thể thành representation, nhất là khi cần ánh xạ trường, tạo self link hoặc tạo link phụ thuộc vào dữ liệu nguồn.

Dùng collection processor khi muốn bổ sung link hoặc metadata cho wrapper collection. Nếu link cần có trên từng item nhúng, hãy bảo đảm assembler tạo chúng cho từng phần tử.

Trước khi thêm processor, hãy cân nhắc xem logic có thật sự dùng chung hay chỉ xuất hiện ở một endpoint. Một processor toàn cục làm thay đổi mọi response khớp kiểu model, vì vậy phạm vi ảnh hưởng cần được thể hiện rõ trong test.

## Kết luận

`RepresentationModelProcessor<EntityModel<Order>>` cho phép bổ sung link dùng chung vào representation của từng đơn hàng trong pipeline Spring HATEOAS. Assembler vẫn chịu trách nhiệm ánh xạ domain object và tạo cấu trúc cơ bản; processor bổ sung liên kết theo kiểu model, trạng thái hoặc policy đã có. Hãy khai báo đúng kiểu generic, tránh link trùng, giữ processor nhẹ và idempotent, rồi kiểm thử cả phương thức `process(...)` lẫn response HAL qua MockMvc để xác nhận Spring tự động áp dụng processor như mong đợi.

