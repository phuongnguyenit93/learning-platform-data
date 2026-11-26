# Kiểm thử assembler

## Mục tiêu

Sau bài này, bạn có thể kiểm thử một `RepresentationModelAssembler` ở hai mức: kiểm tra trực tiếp việc ánh xạ dữ liệu và tạo link, sau đó kiểm tra response HTTP đã được tuần tự hóa thành HAL. Bạn cũng có thể xác nhận link điều kiện xuất hiện đúng theo trạng thái tài nguyên, kiểm thử collection và tránh các assertion quá phụ thuộc vào chi tiết triển khai.

## 1. Vì sao cần kiểm thử assembler?

Assembler chuyển domain object thành representation mà API công bố. Nó thường chịu trách nhiệm cho ba nhóm hành vi:

- Ánh xạ đúng các trường dữ liệu công khai.
- Tạo relation và href đến tài nguyên hoặc thao tác liên quan.
- Chỉ công bố một số link khi trạng thái nghiệp vụ hoặc quyền truy cập cho phép.

Một assembler có thể biên dịch thành công nhưng vẫn tạo hợp đồng hypermedia sai. Ví dụ, link `self` trỏ nhầm ID, relation `cancel` xuất hiện cả khi đơn hàng đã giao, hoặc collection không có self link. Các lỗi này ảnh hưởng trực tiếp đến client dù phần xử lý nghiệp vụ vẫn chạy đúng.

Nên kết hợp hai loại kiểm thử:

| Loại kiểm thử | Phạm vi | Điều cần xác nhận |
|---|---|---|
| Unit test assembler | Gọi trực tiếp `toModel` hoặc `toCollectionModel` | Ánh xạ trường, relation, href và link có điều kiện |
| Integration test HTTP | Gọi controller qua MockMvc | Status, media type, JSON HAL và link thực tế trong response |

Unit test giúp tìm lỗi nhanh và xác định rõ logic assembler. MockMvc kiểm tra thêm việc controller gọi assembler, Spring chọn message converter và serializer tạo đúng cấu trúc hypermedia.

## 2. Chuẩn bị assembler cần kiểm thử

Giả sử ứng dụng có domain object `Order` với các phương thức `getId()`, `getStatus()`, `getTotal()` và `canBeCancelled()`. Assembler tạo `EntityModel<Order>`, thêm self link và chỉ thêm link `cancel` khi đơn hàng có thể hủy:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        EntityModel<Order> model = EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .getOrder(order.getId())).withSelfRel()
        );

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancelOrder(order.getId(), null)).withRel("cancel"));
        }

        return model;
    }
}
```

Các import chính:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Ví dụ giả định controller có hai mapping:

```java
@GetMapping("/{id}")
public EntityModel<Order> getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}

@PostMapping("/{id}/cancellations")
public EntityModel<Order> cancelOrder(
        @PathVariable UUID id,
        @RequestBody CancellationRequest request) {
    return assembler.toModel(
            orderService.cancel(id, request.reason()));
}
```

`methodOn(...)` chỉ tham chiếu chữ ký phương thức để tạo link; nó không gửi request và không thực thi thao tác hủy. Phần `null` là đối số giữ chỗ cho request body khi xây href.

## 3. Unit test trực tiếp toModel

Khi gọi assembler trực tiếp, link builder của Spring MVC cần request context để xác định base URI. Trong unit test, có thể thiết lập `MockHttpServletRequest` và gắn `ServletRequestAttributes` vào `RequestContextHolder`.

Ví dụ với JUnit 5, Spring Test và AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class OrderModelAssemblerTest {

    private final OrderModelAssembler assembler =
            new OrderModelAssembler();

    private ServletRequestAttributes requestAttributes;

    @BeforeEach
    void bindRequestContext() {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/orders");

        request.setScheme("https");
        request.setServerName("api.example.test");
        request.setServerPort(443);
        request.setRequestURI("/orders");

        requestAttributes = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(requestAttributes);
    }

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.resetRequestAttributes();
        requestAttributes.requestCompleted();
    }

    @Test
    void addsSelfAndCancelLinksWhenOrderCanBeCancelled() {
        Order order = OrderTestData.pendingOrder();

        EntityModel<Order> model = assembler.toModel(order);

        assertThat(model.getContent()).isSameAs(order);
        assertThat(model.getLink("self")).isPresent();
        assertThat(model.getLink("cancel")).isPresent();

        assertThat(model.getLink("self").orElseThrow().getHref())
                .endsWith("/orders/" + order.getId());

        assertThat(model.getLink("cancel").orElseThrow().getHref())
                .endsWith("/orders/" + order.getId() + "/cancellations");
    }

    @Test
    void omitsCancelLinkWhenOrderCannotBeCancelled() {
        Order order = OrderTestData.shippedOrder();

        EntityModel<Order> model = assembler.toModel(order);

        assertThat(model.getLink("self")).isPresent();
        assertThat(model.getLink("cancel")).isEmpty();
    }
}
```

`OrderTestData` là test fixture do dự án định nghĩa để tạo đơn hàng ở các trạng thái hợp lệ. Thay helper này bằng factory hoặc builder thực tế của domain model.

Các điểm cần chú ý:

- Request context được thiết lập trước khi gọi assembler và được dọn trong `@AfterEach`.
- Dùng scheme và host giả lập để kiểm soát base URI của link trong test.
- Kiểm tra nội dung model độc lập với link.
- Kiểm tra relation bằng tên relation mà client sẽ sử dụng.
- Kiểm tra phần path có ý nghĩa thay vì phụ thuộc toàn bộ hostname hoặc port nếu chúng không thuộc hợp đồng API.

Nếu assembler sử dụng `EntityLinks`, `WebFluxLinkBuilder` hoặc một cơ chế tạo link khác, cách thiết lập test context có thể khác. Hãy tạo đúng ngữ cảnh mà implementation link builder yêu cầu.

## 4. Kiểm thử ánh xạ dữ liệu

Ngoài link, assembler còn phải công bố đúng trường và giá trị. Nếu assembler tạo DTO hoặc representation riêng, kiểm tra từng trường quan trọng:

```java
@Test
void mapsOnlyThePublicOrderFields() {
    Order order = OrderTestData.pendingOrder();
    OrderSummaryModelAssembler summaryAssembler =
            new OrderSummaryModelAssembler();

    OrderSummaryModel model = summaryAssembler.toModel(order);

    assertThat(model.getId()).isEqualTo(order.getId());
    assertThat(model.getStatus()).isEqualTo("PENDING");
    assertThat(model.getTotal()).isEqualByComparingTo(order.getTotal());
}
```

Đoạn test dùng một `OrderSummaryModelAssembler` riêng, có kiểu đích là `OrderSummaryModel` (DTO kế thừa `RepresentationModel`). Nó minh họa trường hợp assembler thật sự ánh xạ từng trường sang representation mới. Với assembler `EntityModel<Order>` ở phần trước, kiểu trả về vẫn là `EntityModel<Order>` và content vẫn là domain object; khi đó có thể kiểm tra content được giữ đúng, nhưng chưa chứng minh API đã giới hạn các trường công khai. Với API cần kiểm soát trường công khai, hãy dùng DTO riêng và kiểm tra DTO đó. Không nên dùng unit test assembler để hợp thức hóa việc vô tình tuần tự hóa toàn bộ entity persistence.

Các trường cần kiểm tra phụ thuộc hợp đồng API. Ưu tiên ID, trạng thái, số tiền, thông tin hiển thị và các giá trị mà client thật sự sử dụng. Nếu có trường nội bộ không được phép công bố, hãy kiểm tra response HTTP để bảo đảm trường đó không xuất hiện.

## 5. Kiểm thử toCollectionModel

Nếu assembler dùng implementation mặc định của `toCollectionModel`, Spring HATEOAS sẽ gọi `toModel` cho từng phần tử và gom kết quả thành `CollectionModel`. Nếu đã ghi đè phương thức này để thêm link cấp collection, cần kiểm tra cả link ở cấp ngoài lẫn link của từng phần tử.

Ví dụ:

```java
@Test
void convertsEveryOrderAndAddsCollectionSelfLink() {
    List<Order> orders = List.of(
            OrderTestData.pendingOrder(),
            OrderTestData.shippedOrder()
    );

    CollectionModel<EntityModel<Order>> model =
            assembler.toCollectionModel(orders);

    assertThat(model.getContent()).hasSize(2);
    assertThat(model.getLink("self")).isPresent();

    assertThat(model.getContent()).allSatisfy(item ->
            assertThat(item.getLink("self")).isPresent());
}
```

Ví dụ giả định assembler đã ghi đè `toCollectionModel` và thêm self link cho collection. Nếu chưa ghi đè, assertion `model.getLink("self")` sẽ không đúng; khi đó có thể kiểm tra các phần tử ở unit test và để controller hoặc một collection assembler riêng chịu trách nhiệm thêm link cấp ngoài.

Với collection relation được công bố trong HAL, nên khai báo relation rõ ràng bằng `@Relation` trên representation model nếu client cần tên ổn định, ví dụ `orders`. Sau đó kiểm tra tên relation trong MockMvc thay vì chỉ kiểm tra số lượng phần tử.

## 6. Integration test với MockMvc

Unit test không kiểm tra message converter hoặc cấu trúc JSON sau serialization. MockMvc cho phép gọi controller qua Spring MVC mà không cần khởi động server thật.

Ví dụ cấu hình test slice:

```java
@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerWebTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsOrderWithHalLinks() throws Exception {
        UUID id = UUID.fromString(
                "8d1f1e3c-4c21-4e3f-a4e1-1f2e3d4c5b6a");
        Order order = OrderTestData.pendingOrder(id);

        given(orderService.getRequired(id)).willReturn(order);

        mockMvc.perform(get("/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(id.toString()))
            .andExpect(jsonPath("$._links.self.href")
                    .value(endsWith("/orders/" + id)))
            .andExpect(jsonPath("$._links.cancel.href")
                    .value(endsWith("/orders/" + id + "/cancellations")));
    }
}
```

Các import test thường dùng:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
```

Test slice cần import assembler nếu nó không được phát hiện trong phạm vi cấu hình test. Các dependency khác của controller cần được mock hoặc import theo cấu trúc ứng dụng. Với phiên bản Spring Boot mới hơn, annotation mock bean có thể được thay bằng API tương ứng của Spring Test đang dùng.

Test này xác nhận một chuỗi quan trọng: controller gọi service, assembler tạo model, message converter tuần tự hóa HAL và response chứa các relation cùng href mà client có thể sử dụng.

## 7. Kiểm thử link theo trạng thái

Link hành động thường phụ thuộc trạng thái nghiệp vụ. Nên có ít nhất một test cho trạng thái cho phép và một test cho trạng thái không cho phép.

```java
@Test
void doesNotExposeCancelLinkForShippedOrder() throws Exception {
    UUID id = UUID.fromString(
            "8d1f1e3c-4c21-4e3f-a4e1-1f2e3d4c5b6a");
    Order order = OrderTestData.shippedOrder(id);

    given(orderService.getRequired(id)).willReturn(order);

    mockMvc.perform(get("/orders/{id}", id)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders/" + id)))
        .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
```

Nếu link phụ thuộc quyền người dùng, kiểm thử bằng các danh tính có quyền và không có quyền. Ví dụ, người có quyền quản lý đơn hàng nhận relation `cancel`, còn người chỉ được xem không nhận link đó. Cần dùng cơ chế test security của ứng dụng để tạo đúng principal và authority.

Ẩn link là cách hướng dẫn client hiển thị hành động phù hợp. Nó không thay thế kiểm tra authorization ở endpoint. Hãy có kiểm thử riêng chứng minh request hủy trực tiếp vẫn bị từ chối khi người dùng không có quyền hoặc trạng thái đơn hàng không cho phép.

## 8. Kiểm thử collection response bằng MockMvc

Với endpoint collection, kiểm tra self link cấp ngoài, cấu trúc embedded và link của từng phần tử:

```java
@Test
void returnsCollectionWithItemLinks() throws Exception {
    Order first = OrderTestData.pendingOrder();
    Order second = OrderTestData.shippedOrder();

    given(orderService.findAll()).willReturn(List.of(first, second));

    mockMvc.perform(get("/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders")))
        .andExpect(jsonPath("$._embedded").exists());
}
```

Nếu collection relation đã được cố định là `orders` bằng `@Relation`, có thể kiểm tra cụ thể:

```java
.andExpect(jsonPath("$._embedded.orders").isArray())
.andExpect(jsonPath("$._embedded.orders.length()").value(2))
.andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

Cũng nên kiểm thử collection rỗng. Một collection không có item vẫn có thể cần self link và link tìm kiếm hoặc tạo mới theo hợp đồng API. Nếu API dùng `PagedModel`, kiểm tra metadata `page` và các relation `first`, `prev`, `next`, `last` theo vị trí trang.

## 9. Những gì nên và không nên assert

Một test tốt bảo vệ semantics mà client dựa vào, nhưng không khóa chặt chi tiết nội bộ có thể thay đổi an toàn.

| Nên kiểm tra | Cần cân nhắc tránh |
|---|---|
| HTTP status và media type | Toàn bộ JSON snapshot dài nếu không cần thiết |
| Relation quan trọng như `self`, `collection`, `cancel` | Thứ tự các thuộc tính JSON |
| Href dẫn đến đúng tài nguyên hoặc mapping | Host/port local không thuộc hợp đồng |
| Link xuất hiện hoặc vắng mặt theo trạng thái/quyền | Mọi trường nội bộ của domain object |
| Tên relation của `_embedded` nếu đã cam kết | Chi tiết serializer không ảnh hưởng client |

Nếu host public là một phần hợp đồng hoặc test đang xác minh forwarded headers, hãy kiểm tra scheme và host đầy đủ. Nếu test chỉ xác minh mapping, kiểm tra suffix hoặc path thường ít phụ thuộc môi trường hơn.

Không nên chỉ assert rằng `_links` tồn tại. Một response có `_links` nhưng thiếu `self` hoặc chứa href sai vẫn là hợp đồng không đạt yêu cầu.

## 10. Các lỗi kiểm thử thường gặp

**Gọi assembler mà không thiết lập request context.** Link builder của Spring MVC có thể cần request hiện tại để tạo href. Hãy gắn request attributes trong unit test hoặc dùng MockMvc để chạy qua MVC context.

**Không dọn RequestContextHolder.** Request attributes là trạng thái gắn với thread. Luôn reset sau test để tránh làm rò context sang test kế tiếp.

**Chỉ kiểm tra link tồn tại.** Href có thể trỏ sai ID hoặc sai endpoint. Kiểm tra phần URI quan trọng theo hợp đồng.

**Bỏ qua trạng thái không hợp lệ.** Test chỉ xác nhận link xuất hiện khi hợp lệ sẽ không phát hiện trường hợp assembler luôn thêm link. Hãy kiểm tra cả trường hợp link phải vắng mặt.

**Chỉ unit test assembler.** Unit test không kiểm tra HAL serialization, content negotiation hoặc controller mapping. Bổ sung ít nhất một test HTTP qua MockMvc.

**Dùng dữ liệu fixture không đại diện trạng thái.** Fixture nên tạo domain object hợp lệ và biểu diễn đúng điều kiện nghiệp vụ. Tránh mock các getter theo cách khiến object không thể tồn tại trong hệ thống thực.

**Nhầm link với bảo mật.** Test response không có link hành động không chứng minh endpoint đã được bảo vệ. Kiểm thử authorization ở endpoint riêng.

## 11. Quy trình kiểm thử đề xuất

Với một assembler mới hoặc thay đổi relation, có thể triển khai theo thứ tự:

1. Tạo test fixture cho ít nhất một tài nguyên hợp lệ và hai trạng thái nghiệp vụ khác nhau.
2. Unit test `toModel` để kiểm tra dữ liệu, self link và link điều kiện.
3. Unit test `toCollectionModel` nếu assembler có logic cấp collection.
4. Dùng MockMvc gọi endpoint chi tiết để kiểm tra status, media type, relation và href.
5. Gọi endpoint collection để kiểm tra embedded relation và link cấp ngoài.
6. Kiểm tra trường hợp collection rỗng, trạng thái không cho phép và người dùng không có quyền nếu có liên quan.
7. Chạy test suite phù hợp của dự án để phát hiện lỗi tích hợp với cấu hình thực tế.

Mỗi assertion nên gắn với một cam kết cụ thể của API. Khi relation hoặc semantics thay đổi, cập nhật hợp đồng và test có chủ đích thay vì sửa test chỉ để làm cho nó qua.

## Kết luận

Kiểm thử `RepresentationModelAssembler` cần xác nhận cả việc ánh xạ dữ liệu lẫn khả năng điều hướng mà representation công bố. Unit test kiểm tra trực tiếp `toModel` và `toCollectionModel`; MockMvc xác nhận controller, content negotiation và HAL serialization hoạt động cùng nhau. Hãy kiểm tra relation, href và sự xuất hiện của link theo trạng thái hoặc quyền truy cập, đồng thời kiểm thử endpoint thực thi hành động độc lập. Cách này bảo vệ hợp đồng hypermedia mà client thực sự sử dụng.

