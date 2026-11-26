# Phương thức toModel

Trong Spring HATEOAS, RepresentationModelAssembler là thành phần chuyển một đối tượng miền hoặc entity nguồn thành representation model dành cho API. Phương thức toModel(T entity) là điểm chuyển đổi chính: nhận một đối tượng nguồn, tạo kiểu biểu diễn phù hợp, ánh xạ dữ liệu công khai và gắn các liên kết hypermedia cần thiết.

Một assembler giúp nhiều controller hoặc endpoint dùng chung một cách biểu diễn cho cùng loại tài nguyên. Khi quy tắc ánh xạ, tên relation hoặc cách tạo link thay đổi, ta có một nơi tập trung để cập nhật và kiểm thử. Điều này đặc biệt hữu ích với API REST có điều hướng hypermedia, nơi response phải thể hiện trạng thái tài nguyên và các đường đi tiếp theo mà server công bố.

Bài học này tập trung vào hợp đồng của toModel, cách triển khai assembler tổng quát, cách chọn kiểu đầu ra EntityModel hoặc model riêng, cách dùng SimpleRepresentationModelAssembler và RepresentationModelAssemblerSupport, cách tích hợp controller, xử lý dữ liệu tùy chọn và kiểm thử kết quả.

## 1. Vai trò của toModel

Interface RepresentationModelAssembler nằm trong package org.springframework.hateoas.server. Nó định nghĩa cách chuyển một kiểu nguồn thành một RepresentationModel.

Chữ ký tổng quát:

~~~java
public interface RepresentationModelAssembler<
        T, D extends RepresentationModel<?>> {

    D toModel(T entity);

    default CollectionModel<D> toCollectionModel(
            Iterable<? extends T> entities) {
        // Chuyển từng phần tử bằng toModel(...)
    }
}
~~~

Hai tham số generic có ý nghĩa:

- T là kiểu dữ liệu nguồn, thường là domain object hoặc entity được service/repository trả về.
- D là kiểu representation đầu ra và phải kế thừa RepresentationModel.

Phương thức toModel(T entity) nhận một đối tượng nguồn và trả về đúng kiểu D. Ví dụ, assembler có thể chuyển Order thành EntityModel<OrderRepresentation> hoặc chuyển Order thành OrderModel do ứng dụng tự định nghĩa.

Phương thức này là một hợp đồng chuyển đổi. Nó không tự truy vấn dữ liệu, không tự quyết định status HTTP và cũng không tự chạy handler controller. Nhiệm vụ chính là tạo biểu diễn nhất quán từ đối tượng đầu vào.

## 2. Các trách nhiệm của toModel

Một triển khai toModel thường thực hiện bốn nhóm công việc:

1. **Tạo representation:** khởi tạo DTO hoặc model chứa dữ liệu mà API muốn công bố.
2. **Ánh xạ dữ liệu:** chuyển các trường từ mô hình nguồn sang cấu trúc response.
3. **Tạo liên kết:** thêm self, liên kết đến tài nguyên liên quan và các link hành động phù hợp.
4. **Trả model hoàn chỉnh:** trả về một RepresentationModel có kiểu rõ ràng để controller hoặc framework tuần tự hóa.

Ví dụ, một Order trong miền nghiệp vụ có thể chứa thông tin nội bộ như ghi chú vận hành, thông tin thanh toán chi tiết và quan hệ ORM. Response công khai chỉ cần mã đơn, trạng thái và tổng tiền. toModel là nơi lựa chọn các trường đó và gắn các link mà client cần.

Không nên trả null từ toModel. Mỗi đầu vào hợp lệ phải được chuyển thành một representation model hợp lệ hoặc phát sinh lỗi phù hợp nếu dữ liệu không thể biểu diễn. Với tài nguyên không tồn tại, controller/service nên xử lý 404 trước khi gọi assembler; assembler không nên âm thầm biến trường hợp đó thành model rỗng.

## 3. Ví dụ nguồn và representation

Giả sử ứng dụng có mô hình nguồn Order. Ví dụ dùng record để tập trung vào dữ liệu:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record Order(
    UUID id,
    String status,
    BigDecimal total,
    boolean cancellable
) {
    public boolean canCancel() {
        return cancellable;
    }
}
~~~

Đây là kiểu nguồn minh họa cho bài học. Trong ứng dụng thật, T có thể là JPA entity, aggregate của domain hoặc đối tượng do một dịch vụ khác trả về.

API dùng một representation riêng:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Order có thể chứa nhiều thuộc tính hơn OrderRepresentation. Việc tách hai kiểu giúp hợp đồng API không phụ thuộc trực tiếp vào cấu trúc lưu trữ.

Kiểu đầu ra được chọn là EntityModel<OrderRepresentation>. EntityModel bọc DTO và cho phép thêm các Link. Vì vậy, assembler có generic:

~~~java
RepresentationModelAssembler<
    Order,
    EntityModel<OrderRepresentation>>
~~~

T là Order; D là EntityModel<OrderRepresentation>. Tham số generic thứ hai không phải DTO đơn thuần, vì D phải là một kiểu kế thừa RepresentationModel.

## 4. Triển khai toModel bằng EntityModel

Ví dụ assembler hoàn chỉnh:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<
            Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.id(),
            order.status(),
            order.total()
        );

        var self = linkTo(
            methodOn(OrderController.class).one(order.id())
        ).withSelfRel();

        var orders = linkTo(
            methodOn(OrderController.class).all()
        ).withRel("orders");

        var model = EntityModel.of(body, self, orders);

        if (order.canCancel()) {
            model.add(
                linkTo(methodOn(OrderController.class)
                    .cancel(order.id()))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Cách triển khai trên thể hiện rõ từng bước:

- Tạo OrderRepresentation từ Order.
- Tạo self link đến handler chi tiết của đơn hàng.
- Tạo orders link đến tập hợp đơn hàng.
- Chỉ thêm cancel link khi trạng thái nghiệp vụ cho phép.
- Trả EntityModel chứa nội dung và liên kết.

methodOn(...) ghi nhận lời gọi giả lập đến handler method; nó không thực thi logic của controller. linkTo(...) đọc metadata mapping để tạo URI. Khi controller đổi mapping, link được sinh từ handler có thể theo cấu hình mới mà không cần viết lại chuỗi đường dẫn ở assembler.

Trong ví dụ, order không null. Nếu service không tìm thấy đơn hàng, controller nên chuyển trường hợp đó thành lỗi tài nguyên không tồn tại trước khi gọi toModel.

## 5. Chọn kiểu đầu ra phù hợp

Không phải mọi assembler đều cần tạo model riêng. Có ba cách thường gặp:

| Cách triển khai | Kiểu đầu ra | Khi phù hợp |
|---|---|---|
| RepresentationModelAssembler tổng quát | EntityModel<DTO> hoặc model riêng | Cần tự kiểm soát cả ánh xạ dữ liệu và kiểu representation |
| SimpleRepresentationModelAssembler | EntityModel<T> | Muốn giữ nguyên đối tượng nguồn làm content và chủ yếu bổ sung link |
| RepresentationModelAssemblerSupport | Model riêng kế thừa RepresentationModel | Muốn tận dụng việc khởi tạo model và tạo self link theo controller mapping |

Nếu cần đổi Order thành OrderRepresentation, hãy dùng RepresentationModelAssembler tổng quát. Nếu chỉ muốn bọc Order hiện có rồi thêm link, SimpleRepresentationModelAssembler có thể giảm boilerplate. Nếu có model riêng và muốn helper tạo self link từ controller, RepresentationModelAssemblerSupport là một lựa chọn.

Việc chọn kiểu đầu ra phải phản ánh hợp đồng response. Không nên chọn EntityModel<Order> chỉ vì nó ít code hơn nếu entity chứa dữ liệu nội bộ hoặc quan hệ persistence không phù hợp để công bố.

## 6. Dùng SimpleRepresentationModelAssembler

SimpleRepresentationModelAssembler<T> là biến thể đơn giản khi nội dung của EntityModel chính là đối tượng nguồn T. Interface này cung cấp các hook addLinks thay cho việc phải tự viết toModel.

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.SimpleRepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class SimpleOrderAssembler
        implements SimpleRepresentationModelAssembler<Order> {

    @Override
    public void addLinks(EntityModel<Order> model) {
        Order order = model.getContent();

        model.add(
            linkTo(methodOn(OrderController.class).one(order.id()))
                .withSelfRel()
        );

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel("orders")
        );
    }

    @Override
    public void addLinks(
            CollectionModel<EntityModel<Order>> collection) {

        collection.add(
            linkTo(methodOn(OrderController.class).all())
                .withSelfRel()
        );
    }
}
~~~

SimpleRepresentationModelAssembler cung cấp triển khai mặc định cho toModel(T) và toCollectionModel(...). Với từng phần tử, framework tạo EntityModel từ đối tượng nguồn rồi gọi addLinks(EntityModel<T>). Với tập hợp, framework tạo CollectionModel và gọi addLinks(CollectionModel<EntityModel<T>>).

Điểm quan trọng là kiểu content vẫn là T. Nếu muốn chuyển Order thành OrderRepresentation có cấu trúc khác, hãy triển khai RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> thay vì cố nhồi logic chuyển đổi vào SimpleRepresentationModelAssembler.

## 7. Dùng RepresentationModelAssemblerSupport

RepresentationModelAssemblerSupport<T, D> là lớp cơ sở trong package org.springframework.hateoas.server.mvc. Nó hỗ trợ tạo representation model và thêm self link dựa trên controller class cùng resource type được khai báo trong constructor.

Ví dụ model riêng:

~~~java
import org.springframework.hateoas.RepresentationModel;

import java.math.BigDecimal;
import java.util.UUID;

public class OrderModel extends RepresentationModel<OrderModel> {

    private UUID id;
    private String status;
    private BigDecimal total;

    public OrderModel() {
    }

    public void setId(UUID id) {
        this.id = id;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public void setTotal(BigDecimal total) {
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

Assembler kế thừa lớp hỗ trợ:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        extends RepresentationModelAssemblerSupport<Order, OrderModel> {

    public OrderModelAssembler() {
        super(OrderController.class, OrderModel.class);
    }

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = createModelWithId(order.id(), order);

        model.setId(order.id());
        model.setStatus(order.status());
        model.setTotal(order.total());

        if (order.canCancel()) {
            model.add(
                linkTo(methodOn(OrderController.class)
                    .cancel(order.id()))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

createModelWithId(...) tạo instance model và thêm self link dựa trên controller mapping đã khai báo cùng ID của entity. Các overload có thể nhận thêm tham số URI khi mapping cần nhiều giá trị.

Mặc định, lớp hỗ trợ khởi tạo resource type bằng reflection và yêu cầu model có constructor không tham số. Nếu muốn dùng constructor riêng hoặc tránh chi phí reflection, có thể override instantiateModel(T entity) để tự khởi tạo model.

Lớp hỗ trợ này không thay thế logic ánh xạ trong toModel. Assembler vẫn phải điền các trường representation và thêm các liên kết nghiệp vụ còn lại.

## 8. Tích hợp toModel vào controller

Sau khi assembler được đăng ký như Spring bean, controller có thể inject và gọi toModel:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService service,
            OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable UUID id) {

        Order order = service.findById(id);
        return assembler.toModel(order);
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        var orders = service.findAll();

        return assembler.toCollectionModel(orders)
            .add(linkTo(methodOn(OrderController.class).all())
                .withSelfRel());
    }
}
~~~

Controller chịu trách nhiệm nhận request, gọi service và trả kết quả. Assembler chuyển đối tượng nguồn thành representation. Service chịu trách nhiệm truy xuất dữ liệu và quy tắc nghiệp vụ.

Không nên sao chép logic tạo DTO và link trong từng handler. Khi một tài nguyên được trả về từ nhiều endpoint, dùng chung assembler giúp các response nhất quán hơn.

Ví dụ trên giả định OrderService trả Order khi tìm thấy và một Iterable<Order> cho danh sách. Nếu service dùng Optional<Order>, hãy xử lý trường hợp empty trước khi gọi assembler. Nếu service dùng reactive publisher trong WebFlux, hãy dùng ReactiveRepresentationModelAssembler với chữ ký toModel(Order, ServerWebExchange) trả Mono<D>; không dùng assembler đồng bộ trong reactive pipeline chỉ để gọi block().

## 9. toModel và toCollectionModel phối hợp ra sao?

RepresentationModelAssembler cung cấp phương thức mặc định toCollectionModel(Iterable<? extends T>). Phương thức này chuyển từng phần tử bằng toModel rồi bọc các representation trong CollectionModel.

Về mặt khái niệm:

~~~java
CollectionModel<D> toCollectionModel(
        Iterable<? extends T> entities) {

    List<D> models = StreamSupport
        .stream(entities.spliterator(), false)
        .map(this::toModel)
        .toList();

    return CollectionModel.of(models);
}
~~~

Đây là mô tả luồng xử lý để hiểu quan hệ giữa hai phương thức; ứng dụng thường gọi trực tiếp toCollectionModel(...) được cung cấp bởi interface.

Mỗi phần tử được xử lý qua cùng logic toModel. Vì vậy, link self và các link nghiệp vụ của từng tài nguyên được tạo nhất quán. CollectionModel là một tài nguyên tập hợp riêng và có thể cần link ở cấp collection như self, search, create hoặc phân trang. Việc thêm link cấp collection không tự động được bảo đảm chỉ vì từng phần tử đã có link.

Có thể bổ sung link collection ở controller:

~~~java
return assembler.toCollectionModel(orders)
    .add(linkTo(methodOn(OrderController.class).all())
        .withSelfRel());
~~~

Với tập dữ liệu lớn, hãy giới hạn kết quả bằng phân trang hoặc cursor trước khi tạo collection. toCollectionModel nhận Iterable hữu hạn; không dùng nó để gom một nguồn vô hạn.

## 10. Giữ toModel tập trung và dễ dự đoán

Một assembler tốt thường có thể được đọc như một quy tắc chuyển đổi: đầu vào là một đối tượng nguồn, đầu ra là representation có dữ liệu và link phù hợp.

Một số nguyên tắc thiết kế:

- **Ánh xạ tường minh:** chọn các trường API cần công bố thay vì serialize toàn bộ entity.
- **Không thay đổi nguồn:** tránh cập nhật trạng thái nghiệp vụ hoặc sửa entity bên trong toModel.
- **Không gây tác dụng phụ:** không gửi email, ghi giao dịch hoặc thực hiện thao tác ngoài nhiệm vụ biểu diễn.
- **Link có điều kiện rõ ràng:** chỉ thêm link hành động khi trạng thái và chính sách cho phép.
- **Xử lý dữ liệu quan hệ có chủ đích:** chỉ truy xuất dữ liệu cần cho representation; tránh kích hoạt hàng loạt lazy loading.
- **Trả model không null:** không dùng null để biểu thị tài nguyên không tồn tại.
- **Tách trách nhiệm:** controller xử lý HTTP, service xử lý nghiệp vụ, assembler xử lý representation.

Nếu việc tạo representation cần thêm dữ liệu từ nhiều nguồn, cân nhắc để service hoặc một query component chuẩn bị dữ liệu cần thiết trước khi gọi assembler. Điều này giúp toModel không trở thành một nơi truy vấn dữ liệu phức tạp và khó kiểm thử.

## 11. Xử lý quan hệ và dữ liệu tùy chọn

Một đơn hàng có thể liên kết với khách hàng, hóa đơn và dòng hàng. Không phải quan hệ nào cũng cần được nhúng vào payload.

Nếu client cần truy cập tài nguyên riêng, assembler có thể thêm link:

~~~java
model.add(
    linkTo(methodOn(CustomerController.class)
        .one(order.customerId()))
        .withRel("customer")
);
~~~

Nếu thông tin khách hàng chỉ cần để hiển thị nhanh, representation có thể chứa một DTO tóm tắt. Link customer vẫn có thể được cung cấp nếu client cần điều hướng.

Với dữ liệu tùy chọn, kiểm tra rõ trước khi thêm link:

~~~java
if (order.invoiceId() != null) {
    model.add(
        linkTo(methodOn(InvoiceController.class)
            .one(order.invoiceId()))
            .withRel("invoice")
    );
}
~~~

Không tạo href với ID null. Nếu quan hệ chưa tồn tại, hãy bỏ link hoặc biểu diễn trạng thái theo hợp đồng API. Client cần hiểu rằng một relation có thể không xuất hiện trong một số trạng thái.

## 12. Kiểm thử toModel bằng unit test

Có thể kiểm thử assembler trực tiếp mà không cần gọi HTTP. Test cần xác nhận nội dung được ánh xạ đúng và link xuất hiện theo điều kiện.

Ví dụ với JUnit và AssertJ:

~~~java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@Test
void mapsOrderAndAddsExpectedLinks() {
    Order order = new Order(
        UUID.fromString("7f2d8a6e-3f16-4f41-9a73-1f0b4e6c9a20"),
        "PROCESSING",
        new BigDecimal("125000"),
        true
    );

    MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/orders");
    request.setScheme("https");
    request.setServerName("api.example.test");
    request.setServerPort(443);
    RequestContextHolder.setRequestAttributes(
        new ServletRequestAttributes(request)
    );

    try {
        EntityModel<OrderRepresentation> model =
            assembler.toModel(order);

        assertThat(model.getContent().id()).isEqualTo(order.id());
        assertThat(model.getContent().status()).isEqualTo("PROCESSING");
        assertThat(model.getContent().total())
            .isEqualByComparingTo("125000");

        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
        assertThat(model.hasLink("orders")).isTrue();
        assertThat(model.hasLink("cancel")).isTrue();
    } finally {
        RequestContextHolder.resetRequestAttributes();
    }
}
~~~

Khi assembler dùng WebMvcLinkBuilder, unit test cần có request context nếu muốn tạo URI tuyệt đối. Có thể thiết lập MockHttpServletRequest và RequestContextHolder, hoặc kiểm thử qua MockMvc để Spring thiết lập ngữ cảnh request.

Ví dụ kiểm tra link hành động không xuất hiện:

~~~java
@Test
void omitsCancelLinkWhenOrderCannotBeCancelled() {
    Order order = new Order(
        UUID.randomUUID(),
        "DELIVERED",
        new BigDecimal("125000"),
        false
    );

    EntityModel<OrderRepresentation> model =
        assembler.toModel(order);

    assertThat(model.hasLink("cancel")).isFalse();
}
~~~

Unit test nên tập trung vào quy tắc ánh xạ và relation. Không cần khóa cứng host, port hoặc scheme nếu chúng phụ thuộc môi trường.

## 13. Kiểm thử response HTTP sau khi gọi toModel

Unit test không kiểm tra serializer, content negotiation hoặc controller mapping. Bổ sung integration test để xác nhận response HAL mà client nhận.

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists());
~~~

Nếu đơn hàng được phép hủy, kiểm tra relation cancel:

~~~java
mockMvc.perform(get("/orders/{id}", processingOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Nếu đơn hàng đã giao, xác nhận link đó không xuất hiện. Khi kiểm thử cả assembler và HTTP response, có thể phân biệt lỗi ánh xạ model với lỗi serialize hypermedia.

## 14. Những lỗi thường gặp trong toModel

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả null từ toModel | Collection assembler hoặc controller có thể tạo kết quả không hợp lệ | Trả representation hợp lệ hoặc ném lỗi phù hợp |
| Dùng sai kiểu generic D | Không thể gán kết quả vào kiểu model mong muốn | Chọn D kế thừa RepresentationModel |
| Đưa entity persistence trực tiếp vào response | Lộ dữ liệu nội bộ, lazy loading và vòng tham chiếu | Ánh xạ sang DTO khi cần |
| Tạo link bằng chuỗi cố định | Link không theo mapping khi route thay đổi | Dùng WebMvcLinkBuilder |
| Quên self link | Client khó nhận biết URI của tài nguyên | Tạo self link trong assembler hoặc dùng AssemblerSupport |
| Gắn mọi link hành động ở mọi trạng thái | Client thấy thao tác không khả dụng | Kiểm tra trạng thái và quyền trước khi thêm link |
| Truy vấn nhiều quan hệ trong toModel | Tăng truy vấn và làm assembler khó kiểm thử | Chuẩn bị dữ liệu cần thiết ở service/query layer |
| Dùng SimpleRepresentationModelAssembler khi cần đổi DTO | Kiểu content vẫn là entity nguồn | Dùng RepresentationModelAssembler tổng quát |
| Nghĩ toCollectionModel tự thêm self cho collection | Collection response thiếu link cấp tập hợp | Thêm link collection riêng |
| Dùng assembler đồng bộ trong WebFlux | Có nguy cơ chặn reactive pipeline | Dùng ReactiveRepresentationModelAssembler |

## 15. Quy trình triển khai toModel

Khi tạo assembler cho một tài nguyên mới, có thể đi theo thứ tự:

1. Xác định kiểu nguồn T mà service trả về.
2. Chọn kiểu đầu ra D: EntityModel<DTO> hoặc model riêng.
3. Khai báo RepresentationModelAssembler<T, D>.
4. Triển khai toModel(T) để ánh xạ các trường công khai.
5. Tạo self link từ handler method và gắn relation phù hợp.
6. Thêm link đến tài nguyên liên quan và hành động có điều kiện.
7. Inject assembler vào controller và gọi toModel cho endpoint tài nguyên đơn.
8. Dùng toCollectionModel cho tập hợp và bổ sung link ở cấp collection.
9. Kiểm thử nội dung, relation, điều kiện link và response HAL.
10. Nếu dùng WebFlux, chọn assembler reactive tương ứng và giữ toàn bộ thao tác trong publisher.

toModel là điểm tập trung cách một đối tượng miền trở thành tài nguyên hypermedia. Khi phương thức này ánh xạ dữ liệu công khai rõ ràng, tạo link theo mapping và giữ quy tắc hành động nhất quán, các controller có thể trả về representation đồng bộ và dễ kiểm thử. Đây là nền tảng để API Spring HATEOAS duy trì hợp đồng điều hướng khi cấu trúc nội bộ và URI được thay đổi có kiểm soát.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation model assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [SimpleRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/SimpleRepresentationModelAssembler.html)
- [RepresentationModelAssemblerSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelAssemblerSupport.html)
- [ReactiveRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/reactive/ReactiveRepresentationModelAssembler.html)

