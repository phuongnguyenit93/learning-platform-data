# Thêm relation link trong Spring HATEOAS

## Mục tiêu dự án

Trong bài thực hành này, bạn sẽ mở rộng API quản lý đơn hàng để client có thể khám phá các tài nguyên liên quan thông qua hypermedia. Bạn sẽ thêm hai relation vào representation của đơn hàng: relation dẫn đến khách hàng và relation dẫn đến danh sách sản phẩm trong đơn hàng.

Sau khi hoàn thành, bạn có thể:

- Giải thích vai trò của relation trong một hypermedia link.
- Phân biệt relation chuẩn với relation mở rộng do API định nghĩa.
- Khai báo relation mở rộng bằng URI ổn định.
- Dùng Spring HATEOAS tạo link từ mapping của controller.
- Kiểm thử relation và URI trong HAL JSON.
- Đánh giá tác động của việc thêm relation lên hợp đồng API hiện có.

## 1. Bối cảnh và yêu cầu

Giả sử ứng dụng bán hàng đã có endpoint trả về chi tiết đơn hàng. Response hiện có dữ liệu đơn hàng và link self, nhưng client muốn mở khách hàng sở hữu đơn hàng và xem các dòng hàng của đơn hàng đó.

Bạn cần mở rộng representation để cung cấp:

| Relation | Ý nghĩa | Đích đến |
|---|---|---|
| self | Đơn hàng hiện tại | GET /api/orders/{id} |
| https://api.example.com/rels/customer | Khách hàng sở hữu đơn hàng | GET /api/customers/{customerId} |
| https://api.example.com/rels/order-items | Các dòng hàng của đơn hàng | GET /api/orders/{id}/items |

Hai relation có URI là relation mở rộng của API. Trong dự án thực tế, hãy thay api.example.com bằng tên miền do tổ chức kiểm soát và công bố tài liệu giải thích ý nghĩa của từng relation.

Client sẽ khám phá relation trong response rồi theo href tương ứng. Client không cần tự suy ra ID khách hàng từ cấu trúc JSON hoặc tự ghép đường dẫn /api/orders/{id}/items.

### Relation và href có vai trò khác nhau

Một link có hai thành phần quan trọng:

- **Relation (rel):** mô tả mối quan hệ giữa tài nguyên hiện tại và đích đến của link.
- **Href:** URI để client truy cập đích đến.

Ví dụ, relation customer cho biết link dẫn đến khách hàng liên quan đến đơn hàng. Href cho biết URI cụ thể của khách hàng đó. Nếu đường dẫn được thay đổi, server có thể cập nhật href trong khi giữ nguyên ý nghĩa relation để client tiếp tục hoạt động.

## 2. Chuẩn bị cấu trúc API

Bài thực hành giả định ứng dụng có các kiểu miền và service tương tự:

Các đoạn mã bên dưới lược bỏ một số import thông dụng của Java, Spring MVC và Spring HATEOAS để tập trung vào phần cần triển khai.

~~~java
public record Order(
    UUID id,
    UUID customerId,
    OrderStatus status
) {}

public record Customer(
    UUID id,
    String name
) {}

public record OrderItem(
    UUID id,
    String productName,
    int quantity
) {}
~~~

Controller khách hàng cung cấp endpoint chi tiết:

~~~java
@RestController
@RequestMapping("/api/customers")
class CustomerController {

    private final CustomerService customerService;

    CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping("/{id}")
    EntityModel<Customer> one(@PathVariable UUID id) {
        Customer customer = customerService.findById(id);

        Link self = linkTo(
            methodOn(CustomerController.class).one(id)
        ).withSelfRel();

        return EntityModel.of(customer, self);
    }
}
~~~

Controller đơn hàng cần có endpoint chi tiết và endpoint danh sách dòng hàng. Nếu ứng dụng đã có các endpoint tương đương, hãy dùng mapping hiện tại thay vì tạo route trùng lặp.

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable UUID id) {
        return assembler.toModel(orderService.findById(id));
    }

    @GetMapping("/{id}/items")
    CollectionModel<OrderItem> items(@PathVariable UUID id) {
        return CollectionModel.of(orderService.findItems(id));
    }
}
~~~

Các phương thức findById và findItems đại diện cho thao tác lấy dữ liệu hiện có của service. Bạn có thể điều chỉnh kiểu trả về theo mô hình của dự án, miễn là các URI đích tồn tại và có thể truy cập.

## 3. Khai báo relation mở rộng

Spring HATEOAS cung cấp LinkRelation để biểu diễn relation. Relation chuẩn đã đăng ký có thể dùng hằng trong IanaLinkRelations, ví dụ IanaLinkRelations.SELF.

Với quan hệ đặc thù của miền đơn hàng, hãy định nghĩa relation mở rộng bằng URI:

~~~java
import org.springframework.hateoas.LinkRelation;

final class OrderRelations {

    static final LinkRelation CUSTOMER =
        LinkRelation.of("https://api.example.com/rels/customer");

    static final LinkRelation ITEMS =
        LinkRelation.of("https://api.example.com/rels/order-items");

    private OrderRelations() {
    }
}
~~~

Dùng URI giúp relation có định danh toàn cục và tránh xung đột với relation do chuẩn hoặc hệ thống khác định nghĩa. URI relation nên ổn định theo thời gian. Nếu cần mô tả chi tiết, tổ chức có thể cung cấp tài liệu tại URI đó hoặc tại trang tài liệu được relation trỏ tới.

Không nên đặt relation theo tên class Java hoặc tên method nội bộ, vì những tên đó có thể thay đổi khi refactor mà không phản ánh ý nghĩa hợp đồng API.

## 4. Thêm relation vào OrderModelAssembler

Assembler chịu trách nhiệm chuyển Order thành EntityModel<Order>. Hãy giữ quy tắc tạo link tại đây để endpoint chi tiết và endpoint danh sách có thể dùng chung một representation.

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {

        Link self = linkTo(
            methodOn(OrderController.class).one(order.id())
        ).withSelfRel();

        Link customer = linkTo(
            methodOn(CustomerController.class).one(order.customerId())
        ).withRel(OrderRelations.CUSTOMER);

        Link items = linkTo(
            methodOn(OrderController.class).items(order.id())
        ).withRel(OrderRelations.ITEMS);

        return EntityModel.of(order, self, customer, items);
    }
}
~~~

Ba link được tạo từ mapping của controller:

- self trỏ đến chính đơn hàng.
- customer trỏ đến khách hàng theo customerId.
- items trỏ đến endpoint lấy các dòng hàng theo ID đơn hàng.

methodOn tạo proxy để ghi nhận lời gọi phương thức và các đối số. Spring HATEOAS dùng thông tin mapping của controller để xây URI; phương thức controller không được thực thi như một request thật trong lúc tạo link.

Khi dùng methodOn, hãy truyền các giá trị định danh đã có sẵn trong đối tượng. Không nên truy cập một quan hệ ORM lazy chỉ để lấy ID nếu việc truy cập đó có thể kích hoạt truy vấn bổ sung. Nếu cần, hãy tải ID bằng projection hoặc truy vấn phù hợp ở tầng service.

## 5. Quan sát HAL JSON sau khi thêm relation

Khi gọi GET /api/orders/{id}, response có thể có dạng:

~~~json
{
  "id": "7f1f7d0c-2c91-4e65-8b6c-3e4f4d2a1001",
  "customerId": "d13e4b10-0d72-4b4a-92f7-2a9d2e3f2002",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/orders/7f1f7d0c-2c91-4e65-8b6c-3e4f4d2a1001"
    },
    "https://api.example.com/rels/customer": {
      "href": "https://api.example.test/api/customers/d13e4b10-0d72-4b4a-92f7-2a9d2e3f2002"
    },
    "https://api.example.com/rels/order-items": {
      "href": "https://api.example.test/api/orders/7f1f7d0c-2c91-4e65-8b6c-3e4f4d2a1001/items"
    }
  }
}
~~~

Tên relation được dùng làm key bên trong _links. Client có thể tìm relation theo URI đã biết, lấy href và gửi request đến đích.

Ví dụ, khi cần hiển thị thông tin khách hàng, client tìm relation https://api.example.com/rels/customer rồi truy cập href của nó. Nếu server đổi endpoint khách hàng từ /api/customers/{id} sang một đường dẫn khác, client vẫn hoạt động miễn relation được giữ ổn định và href mới được công bố.

## 6. Kiểm thử relation và đích đến

Kiểm thử cần xác nhận cả relation lẫn URI được tạo. Đừng chỉ kiểm tra rằng response có status 200 OK; một response thành công nhưng thiếu relation mới vẫn chưa đáp ứng yêu cầu của dự án.

Ví dụ với MockMvc và Jackson:

~~~java
@Test
void orderRepresentationContainsCustomerAndItemsRelations()
        throws Exception {

    UUID orderId = UUID.fromString(
        "7f1f7d0c-2c91-4e65-8b6c-3e4f4d2a1001"
    );

    MvcResult result = mockMvc.perform(
            get("/api/orders/{id}", orderId)
        )
        .andExpect(status().isOk())
        .andReturn();

    JsonNode root = objectMapper.readTree(
        result.getResponse().getContentAsString()
    );

    JsonNode links = root.path("_links");

    assertThat(links.path("self").path("href").asText())
        .contains("/api/orders/" + orderId);

    assertThat(links.has(
        "https://api.example.com/rels/customer"
    )).isTrue();

    assertThat(links.path(
        "https://api.example.com/rels/customer"
    ).path("href").asText())
        .contains("/api/customers/");

    assertThat(links.has(
        "https://api.example.com/rels/order-items"
    )).isTrue();

    assertThat(links.path(
        "https://api.example.com/rels/order-items"
    ).path("href").asText())
        .contains("/api/orders/" + orderId + "/items");
}
~~~

Ví dụ trên giả định test đã cấu hình MockMvc, ObjectMapper, dữ liệu đơn hàng và các dependency service cần thiết. Các assertion dùng relation URI đầy đủ để xác nhận chính xác hợp đồng đã công bố.

Ngoài kiểm tra JSON, hãy kiểm tra endpoint đích:

~~~java
mockMvc.perform(get("/api/orders/{id}/items", orderId))
    .andExpect(status().isOk());
~~~

Tương tự, kiểm tra endpoint khách hàng bằng ID được gắn với đơn hàng. Điều này đảm bảo link không chỉ có cú pháp đúng mà còn dẫn đến một tài nguyên có thể truy cập.

Nếu ứng dụng cấu hình base path, reverse proxy hoặc host động, hãy tránh hard-code toàn bộ URL tuyệt đối trong test. Kiểm tra relation và phần path cần thiết, hoặc dùng URI được trả về từ response để điều hướng trong kiểm thử tích hợp.

## 7. Đánh giá tính tương thích của hợp đồng API

Thêm relation mới thường là thay đổi mở rộng: client cũ có thể bỏ qua relation mà nó chưa biết, còn client mới có thể sử dụng khả năng vừa được công bố. Tuy nhiên, vẫn cần kiểm tra các điểm sau:

- Không đổi ý nghĩa của relation self đang tồn tại.
- Không tái sử dụng một relation cũ cho một loại tài nguyên khác.
- Không xóa relation mà client hiện tại có thể đang phụ thuộc.
- Dùng cùng một URI relation cho cùng một ý nghĩa trong mọi representation.
- Đảm bảo endpoint đích có chính sách xác thực và phân quyền phù hợp.
- Cập nhật tài liệu relation nếu ý nghĩa hoặc cách sử dụng thay đổi.

Relation là một phần của hợp đồng hypermedia. Một client có thể dựa vào relation để quyết định hành động tiếp theo, vì vậy tên và ý nghĩa của relation cần ổn định hơn tên class hoặc tên method trong server.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Relation không xuất hiện trong _links | Chưa truyền link vào EntityModel.of hoặc relation bị khai báo sai | Kiểm tra assembler và relation được thêm vào model |
| Href chứa ID sai | Truyền nhầm ID hoặc lấy ID từ quan hệ không đúng | Dùng đúng thuộc tính định danh của tài nguyên liên quan |
| Link trỏ đến endpoint không tồn tại | Mapping trong methodOn không khớp controller thật | Kiểm tra mapping và method được tham chiếu |
| Client không nhận diện relation | Relation tùy chỉnh chưa được tài liệu hóa hoặc client tìm sai URI | Dùng URI relation ổn định và công bố ý nghĩa |
| Response có nhiều link trùng relation | Cùng relation được thêm nhiều lần với ý nghĩa không rõ ràng | Xem lại quy tắc tạo link và quyết định khi nào dùng nhiều link cùng relation |
| Tạo link làm phát sinh truy vấn ngoài ý muốn | Đọc thuộc tính quan hệ lazy để lấy ID | Tải ID cần thiết ở service hoặc dùng projection |

## 9. Thử thách mở rộng

Sau khi hai relation customer và order-items hoạt động, hãy mở rộng dự án với relation cancel cho phép hủy đơn hàng.

Chỉ công bố link hủy khi trạng thái đơn hàng cho phép hành động đó. Ví dụ, đơn hàng ở trạng thái PENDING có thể được hủy, còn đơn hàng đã giao hoặc đã hủy thì không.

Hãy thực hiện:

1. Khai báo URI relation riêng cho hành động hủy.
2. Tạo endpoint hủy đơn hàng với mapping rõ ràng.
3. Thêm link hủy vào representation khi trạng thái cho phép.
4. Kiểm thử rằng đơn hàng PENDING có link cancel.
5. Kiểm thử rằng đơn hàng không còn đủ điều kiện không có link đó.
6. Vẫn xác minh quyền ở endpoint hủy khi client gửi request; sự hiện diện của link không thay thế kiểm tra quyền.

Thử thách này giúp bạn áp dụng cùng nguyên tắc relation cho cả liên kết tài nguyên và liên kết mô tả hành động khả dụng.

## 10. Tiêu chí hoàn thành

- [ ] Relation self vẫn trỏ đến đơn hàng hiện tại.
- [ ] Relation khách hàng được khai báo bằng URI ổn định.
- [ ] Relation danh sách dòng hàng được khai báo bằng URI ổn định.
- [ ] OrderModelAssembler tạo link từ mapping của controller.
- [ ] HAL JSON có đủ ba relation và href hợp lệ.
- [ ] Endpoint khách hàng và dòng hàng có thể truy cập.
- [ ] Test xác nhận tên relation và URI đích.
- [ ] Client có thể điều hướng dựa trên relation mà không tự ghép URL.
- [ ] Chính sách xác thực và phân quyền vẫn được áp dụng ở endpoint đích.

Khi hoàn thành, representation đơn hàng sẽ mô tả được các mối quan hệ quan trọng của nó. Client có thể khám phá khách hàng và dòng hàng từ các relation được công bố, còn server giữ quyền kiểm soát cấu trúc URI thông qua Spring HATEOAS.

