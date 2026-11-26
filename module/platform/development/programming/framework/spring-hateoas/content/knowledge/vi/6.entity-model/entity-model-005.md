# EntityModel với entity

Spring HATEOAS cung cấp EntityModel<T> để biểu diễn một tài nguyên đơn bằng cách bọc nội dung và các liên kết hypermedia trong cùng một model. Khi làm việc với entity trong ứng dụng, ta có thể dùng EntityModel để thêm link self, link đến tập hợp hoặc link đến hành động mà tài nguyên đang cho phép.

Cần phân biệt hai khái niệm dễ gây nhầm lẫn: EntityModel là lớp biểu diễn của Spring HATEOAS; entity là đối tượng miền hoặc đối tượng persistence của ứng dụng. EntityModel không phải JPA entity, không quản lý vòng đời dữ liệu và không tự chuyển đổi entity thành DTO. Tham số generic T chính là kiểu nội dung được bọc.

Bài học này trình bày cách tạo EntityModel từ entity, gắn liên kết bằng WebMvcLinkBuilder, tích hợp với controller và assembler, xử lý quan hệ giữa các tài nguyên, xuất HAL JSON và kiểm thử hợp đồng hypermedia. Ví dụ xuyên suốt dùng đơn hàng.

## 1. EntityModel là gì?

EntityModel<T> là một implementation cụ thể của RepresentationModel, được thiết kế để bọc một đối tượng nội dung cùng các Link. Chữ Entity trong tên lớp nói đến một tài nguyên có nội dung, không có nghĩa đây là lớp entity của JPA.

Khai báo generic có thể hiểu theo cấu trúc:

~~~java
public class EntityModel<T>
        extends RepresentationModel<EntityModel<T>> {
    // Nội dung T và các link
}
~~~

Tham số T là kiểu của nội dung được bọc. Ví dụ:

- EntityModel<Order> bọc một đối tượng Order.
- EntityModel<OrderDto> bọc một DTO có tên OrderDto.
- EntityModel<CustomerSummary> bọc phần dữ liệu tóm tắt khách hàng.

EntityModel cung cấp hai phần chính:

1. Nội dung tài nguyên, có thể đọc bằng getContent().
2. Tập hợp link, được quản lý thông qua các phương thức kế thừa từ RepresentationModel.

Nhờ đó, controller có thể trả về một kiểu thống nhất chứa cả dữ liệu và các đường dẫn hypermedia.

### 1.1. EntityModel không phải JPA Entity

Tên hai kiểu có thể khiến người mới học nhầm lẫn:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| JPA entity | Mô hình persistence được ORM ánh xạ tới bảng dữ liệu | Order được đánh dấu @Entity |
| Domain entity | Đối tượng có danh tính và quy tắc nghiệp vụ | Order có trạng thái và hành vi cancel |
| DTO | Kiểu dữ liệu định nghĩa trường API công bố | OrderDto |
| EntityModel<T> | Wrapper Spring HATEOAS chứa nội dung và link | EntityModel<OrderDto> |

EntityModel không lưu dữ liệu xuống database. Nó không thay thế @Entity, repository hay domain model. Nó chỉ đóng gói nội dung cho response hypermedia.

Một entity có thể được dùng làm nội dung của EntityModel, nhưng việc đó không tự động biến entity thành một biểu diễn API an toàn. Ứng dụng vẫn phải quyết định trường nào được phép công khai và cách xử lý quan hệ nội bộ.

## 2. Tạo EntityModel từ một entity

Cách đơn giản nhất là dùng phương thức tĩnh EntityModel.of(...). Ví dụ, giả sử service đã tìm được một đơn hàng:

~~~java
Order order = orderRepository.findById(orderId)
    .orElseThrow(() -> new OrderNotFoundException(orderId));

EntityModel<Order> model = EntityModel.of(order);
~~~

Biến model chứa nội dung order. Có thể lấy lại nội dung bằng getContent():

~~~java
Order content = model.getContent();
~~~

Nếu muốn tạo model cùng các liên kết ngay từ đầu, truyền các Link làm tham số bổ sung:

~~~java
EntityModel<Order> model = EntityModel.of(
    order,
    selfLink,
    ordersLink
);
~~~

EntityModel.of(content, links...) tạo wrapper và thêm các link đã cung cấp. Nếu model đã được tạo, có thể thêm link bằng add():

~~~java
EntityModel<Order> model = EntityModel.of(order);

model.add(selfLink);
model.add(ordersLink);
~~~

Có thể thêm nhiều link trong cùng một lời gọi add:

~~~java
model.add(selfLink, ordersLink, customerLink);
~~~

Các phương thức quản lý link được kế thừa từ RepresentationModel. Chúng cho phép kiểm tra link theo relation, đọc link hoặc xóa link. Nội dung của entity vẫn được giữ trong model.

### 2.1. Tạo link self

Mỗi biểu diễn tài nguyên đơn thường nên có link self để client biết URI của chính tài nguyên đó.

Với Spring MVC, WebMvcLinkBuilder hỗ trợ tạo URI từ ánh xạ controller:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

var selfLink = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();

EntityModel<Order> model = EntityModel.of(order, selfLink);
~~~

methodOn(...) tạo lời gọi controller giả lập để Spring HATEOAS đọc metadata của mapping và tham số đường dẫn. Lời gọi này không thực thi logic nghiệp vụ của handler. linkTo(...) chuyển thông tin mapping thành link builder; withSelfRel() gắn relation chuẩn self.

Khi mapping controller thay đổi, link được tạo từ mapping có thể đi theo URI mới mà không phải tìm và sửa các chuỗi URL được viết thủ công ở nhiều nơi.

### 2.2. Tạo link đến tập hợp

Ngoài self, một tài nguyên đơn có thể cung cấp đường dẫn quay lại tập hợp:

~~~java
var ordersLink = linkTo(
    methodOn(OrderController.class).all()
).withRel("orders");

EntityModel<Order> model = EntityModel.of(
    order,
    selfLink,
    ordersLink
);
~~~

Relation orders có ý nghĩa nghiệp vụ và là một phần hợp đồng API. Hãy chọn tên relation dễ hiểu, ổn định và không phụ thuộc tên method Java.

### 2.3. Tạo link đến tài nguyên liên quan

Một đơn hàng thường có quan hệ với khách hàng. Có thể cung cấp link đến tài nguyên khách hàng:

~~~java
var customerLink = linkTo(
    methodOn(CustomerController.class).one(order.getCustomer().getId())
).withRel("customer");

model.add(customerLink);
~~~

Client có thể theo relation customer để truy cập thông tin khách hàng. Cách này giữ biểu diễn đơn hàng gọn và tránh nhúng toàn bộ dữ liệu khách hàng vào mọi response.

Nếu client thực sự cần một phần dữ liệu khách hàng trong cùng response, ứng dụng có thể thiết kế DTO có trường lồng nhau hoặc dùng cơ chế embedding phù hợp. Link và dữ liệu nhúng phục vụ hai nhu cầu khác nhau: link cho phép điều hướng đến tài nguyên; nội dung nhúng cung cấp dữ liệu liên quan ngay trong biểu diễn hiện tại.

## 3. Ví dụ entity đơn hàng và EntityModel

Giả sử ứng dụng có entity đơn hàng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    private UUID id;

    private String status;
    private BigDecimal total;

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public boolean canCancel() {
        return "NEW".equals(status) || "PROCESSING".equals(status);
    }
}
~~~

Đây là entity minh họa; constructor, setter, mapping quan hệ và quy tắc thay đổi trạng thái được lược bỏ để tập trung vào biểu diễn.

Một controller có thể bọc entity bằng EntityModel:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderRepository repository;

    public OrderController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public EntityModel<Order> one(@PathVariable UUID id) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

        return EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders")
        );
    }

    @GetMapping
    public CollectionModel<EntityModel<Order>> all() {
        // Phần tạo collection được trình bày ở mục sau.
        return CollectionModel.empty();
    }
}
~~~

Khi trả EntityModel<Order>, response có nội dung từ các thuộc tính được serializer công bố của Order và phần _links do model quản lý. Đây là cách minh họa trực tiếp EntityModel với entity.

Tuy nhiên, nếu Order là JPA entity trong ứng dụng thực tế, việc tuần tự hóa trực tiếp có thể làm lộ trường nội bộ, kích hoạt truy vấn lazy, tạo vòng tham chiếu hoặc phụ thuộc vào cấu trúc persistence. Phần tiếp theo trình bày cách giữ entity ở phía trong ứng dụng và dùng DTO làm nội dung của EntityModel.

## 4. Bọc DTO thay vì công khai trực tiếp JPA entity

API nên kiểm soát rõ dữ liệu công khai. Entity lưu trữ có thể chứa thông tin không dành cho client, chẳng hạn ghi chú nội bộ, dữ liệu kiểm toán, trạng thái thanh toán chi tiết hoặc quan hệ với các entity khác.

Tạo một DTO chỉ gồm các trường mà endpoint cần công bố:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Sau đó chuyển entity sang DTO và bọc DTO trong EntityModel:

~~~java
OrderRepresentation body = new OrderRepresentation(
    order.getId(),
    order.getStatus(),
    order.getTotal()
);

EntityModel<OrderRepresentation> model =
    EntityModel.of(body, selfLink, ordersLink);
~~~

Ở đây, EntityModel vẫn thực hiện đúng nhiệm vụ: bọc nội dung cùng các link. Thay đổi nằm ở kiểu nội dung T từ Order sang OrderRepresentation.

Lợi ích của cách tổ chức này:

- API chỉ công bố các trường được lựa chọn.
- Thay đổi cấu trúc bảng hoặc quan hệ ORM ít ảnh hưởng đến client.
- Không vô tình tuần tự hóa proxy hoặc quan hệ lazy.
- Có thể tạo các biểu diễn khác nhau cho các use case khác nhau.
- Hợp đồng API được kiểm soát bằng kiểu DTO thay vì phụ thuộc entity persistence.

Nếu entity trong ứng dụng cũng là domain model thuần, không chứa chi tiết ORM hay dữ liệu nhạy cảm, có thể dùng trực tiếp làm nội dung trong một số trường hợp đơn giản. Quyết định cần dựa trên ranh giới hợp đồng API và đặc điểm entity thực tế.

## 5. Dùng RepresentationModelAssembler để tạo EntityModel

Nếu nhiều endpoint cần tạo cùng một loại biểu diễn, không nên lặp lại logic chuyển đổi và tạo link trong từng controller. Spring HATEOAS cung cấp RepresentationModelAssembler<S, D> để chuẩn hóa việc chuyển đối tượng nguồn thành representation.

Hai tham số generic có ý nghĩa:

- S là kiểu đối tượng nguồn, ví dụ Order.
- D là kiểu model đầu ra, ví dụ EntityModel<OrderRepresentation>.

Ví dụ assembler:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus(),
            order.getTotal()
        );

        var model = EntityModel.of(
            body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel(),
            linkTo(methodOn(OrderController.class).all())
                .withRel("orders")
        );

        if (order.canCancel()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(order.getId()))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Assembler chịu trách nhiệm:

1. Chuyển entity Order thành OrderRepresentation.
2. Tạo link self đến chính đơn hàng.
3. Tạo link orders đến tập hợp.
4. Chỉ thêm link cancel khi trạng thái đơn hàng cho phép.

Việc tập trung logic này giúp các endpoint sử dụng cùng một biểu diễn và tránh tình trạng một controller tạo thiếu link hoặc dùng tên relation không nhất quán.

### 5.1. Dùng assembler trong controller

Controller chỉ cần truy xuất entity rồi giao cho assembler:

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
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        Order order = service.findById(id);
        return assembler.toModel(order);
    }
}
~~~

Controller tập trung vào HTTP và điều phối service. Assembler định nghĩa cách tài nguyên được biểu diễn. Service xử lý truy xuất và quy tắc nghiệp vụ.

Trong ứng dụng thật, service có thể trả Optional<Order>, hoặc ném ngoại lệ nếu không tìm thấy. Ví dụ rút gọn dùng Order trực tiếp để làm rõ cách phối hợp giữa controller và assembler.

### 5.2. Dùng toCollectionModel

RepresentationModelAssembler cũng cung cấp toCollectionModel(...) để chuyển một tập hợp entity thành CollectionModel của các representation tương ứng.

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderRepresentation>> all() {
    List<Order> orders = service.findAll();

    return assembler.toCollectionModel(orders)
        .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
~~~

Mỗi Order được chuyển qua toModel(...), vì vậy từng phần tử có link riêng. CollectionModel còn có thể chứa link ở cấp tập hợp như self, create hoặc search tùy hợp đồng API.

Không nên trả về CollectionModel<Order> nếu muốn mỗi phần tử có link riêng mà chưa có cơ chế tạo link cho từng phần tử. Hãy chọn kiểu phần tử phù hợp với biểu diễn mong muốn.

Với tập dữ liệu lớn, nên dùng phân trang. PagedModel hoặc các cơ chế hỗ trợ phân trang của Spring HATEOAS có thể cung cấp metadata và link điều hướng trang. Không tải toàn bộ bảng dữ liệu chỉ để tạo một response collection.

## 6. EntityModel và các quan hệ giữa tài nguyên

Một entity thường có nhiều quan hệ nghiệp vụ. Ví dụ:

- Đơn hàng thuộc về một khách hàng.
- Đơn hàng chứa nhiều dòng hàng.
- Đơn hàng có thể liên kết đến thanh toán.
- Đơn hàng có thể cho phép hành động hủy hoặc xác nhận.

Có hai cách biểu diễn thông tin liên quan.

### 6.1. Dùng link đến tài nguyên riêng

Một response đơn hàng có thể chứa:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "customer": {
      "href": "/customers/CUS-7"
    },
    "items": {
      "href": "/orders/ORD-42/items"
    }
  }
}
~~~

Client theo relation customer hoặc items để truy cập tài nguyên liên quan. Cách này phù hợp khi tài nguyên có vòng đời, quyền truy cập hoặc nhu cầu truy vấn riêng.

### 6.2. Dùng nội dung nhúng

Nếu client cần thông tin khách hàng ngắn gọn trong response đơn hàng, DTO có thể có trường lồng nhau:

~~~java
public record CustomerSummary(
    UUID id,
    String name
) {}

public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total,
    CustomerSummary customer
) {}
~~~

Đây là dữ liệu lồng nhau trong payload. Nó không tự động là một EntityModel độc lập và không mặc nhiên có tập link riêng. Nếu cần điều hướng đến khách hàng, vẫn có thể bổ sung relation customer ở EntityModel của đơn hàng.

Quyết định dùng link hay nhúng dữ liệu phụ thuộc use case:

| Nhu cầu | Cách biểu diễn phù hợp |
|---|---|
| Client cần mở tài nguyên liên quan | Thêm Link với relation rõ ràng |
| Client chỉ cần một phần dữ liệu để hiển thị ngay | DTO lồng nhau |
| Tài nguyên liên quan có quyền truy cập riêng | Link đến endpoint riêng |
| Dữ liệu liên quan lớn hoặc thay đổi độc lập | Link, tránh nhúng toàn bộ |
| Dữ liệu nhỏ và luôn cần cùng tài nguyên chính | Có thể nhúng vào DTO |

EntityModel không tự phát hiện quan hệ ORM và không tự quyết định nhúng hay liên kết. Chính thiết kế representation và các Link được thêm vào sẽ xác định response hypermedia.

## 7. Liên kết hành động khả dụng

Một tài nguyên có thể công bố các hành động khác nhau tùy theo trạng thái nghiệp vụ. Ví dụ đơn hàng mới tạo có thể hủy; đơn hàng đã giao thì không.

Assembler có thể quyết định có thêm link cancel hay không:

~~~java
if (order.canCancel()) {
    model.add(
        linkTo(methodOn(OrderController.class).cancel(order.getId()))
            .withRel("cancel")
    );
}
~~~

Khi link có mặt, client biết server đang công bố đường dẫn của hành động đó. Khi link không xuất hiện, client có thể hiểu rằng thao tác không được công bố trong biểu diễn hiện tại.

Tuy nhiên, link không phải cơ chế cấp quyền. Endpoint cancel vẫn phải kiểm tra trạng thái đơn hàng, quyền người dùng và các điều kiện nghiệp vụ khi nhận request. Response có thể đã cũ tại thời điểm client gửi thao tác.

Một ví dụ controller:

~~~java
@PostMapping("/{id}/cancellation")
public ResponseEntity<Void> cancel(@PathVariable UUID id) {
    service.cancel(id);
    return ResponseEntity.noContent().build();
}
~~~

Tên relation cancel nên ổn định và có ý nghĩa nghiệp vụ. Client nên dựa vào relation được trả về thay vì tự nối URL hoặc giả định mọi đơn hàng đều có thể hủy.

## 8. HAL JSON được tạo từ EntityModel

Khi controller trả EntityModel và ứng dụng được cấu hình hỗ trợ HAL, Spring HATEOAS có thể chuyển model thành HAL JSON. Link được biểu diễn trong _links; nội dung được bọc trở thành các thuộc tính của tài nguyên.

Ví dụ:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/ORD-42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "cancel": {
      "href": "https://api.example.com/orders/ORD-42/cancellation"
    }
  }
}
~~~

EntityModel không tạo cấu trúc JSON riêng bao quanh nội dung bằng một thuộc tính tên content. Với HAL, nội dung được trình bày cùng các thành phần hypermedia theo định dạng.

Controller có thể khai báo media type:

~~~java
@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
    return assembler.toModel(service.findById(id));
}
~~~

Client gửi Accept: application/hal+json để yêu cầu HAL. Việc chuyển đổi phụ thuộc cấu hình hypermedia và message converter của ứng dụng.

Nếu dùng media type JSON thông thường hoặc cấu hình serializer khác, cấu trúc response có thể khác. Hãy kiểm tra response thực tế bằng test thay vì chỉ suy luận từ kiểu Java.

## 9. Xử lý lỗi và nội dung rỗng

EntityModel được thiết kế để biểu diễn một tài nguyên đơn có nội dung. Nếu tài nguyên không tồn tại, controller nên trả HTTP 404 thay vì tạo một model rỗng không có ý nghĩa.

Ví dụ:

~~~java
@GetMapping("/{id}")
public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
    Order order = service.findById(id)
        .orElseThrow(() -> new OrderNotFoundException(id));

    return assembler.toModel(order);
}
~~~

Ngoại lệ có thể được ánh xạ bằng @ControllerAdvice:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Void> handleNotFound() {
        return ResponseEntity.notFound().build();
    }
}
~~~

Nếu service trả Optional, controller có thể chuyển Optional thành exception hoặc ResponseEntity phù hợp. Hãy giữ semantics HTTP rõ ràng: 404 khi không tìm thấy, 403 khi không đủ quyền, 409 khi thao tác xung đột trạng thái, tùy quy tắc API.

Không nên trả HTTP 200 với EntityModel có content null chỉ để tránh xử lý lỗi. Client cần biết tài nguyên có tồn tại và có thể truy cập hay không.

## 10. Kiểm thử EntityModel và link

Kiểm thử cần xác nhận cả dữ liệu nội dung và liên kết. Với Spring MVC, có thể dùng MockMvc:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$.status").value("PROCESSING"))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Kiểm tra đơn hàng không thể hủy:

~~~java
mockMvc.perform(get("/orders/{id}", deliveredOrderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Có thể kiểm tra assembler riêng:

~~~java
Order order = sampleOrder();
EntityModel<OrderRepresentation> model = assembler.toModel(order);

assertThat(model.getContent().id()).isEqualTo(order.getId());
assertThat(model.hasLink("self")).isTrue();
assertThat(model.hasLink("orders")).isTrue();
~~~

Với đơn hàng đã giao, kiểm tra hasLink("cancel") trả về false. Cách này xác nhận điều kiện nghiệp vụ ảnh hưởng đúng đến tập link.

Nên kiểm tra relation và trường dữ liệu có ý nghĩa thay vì cố định toàn bộ host tuyệt đối trong mọi test. Host, context path hoặc reverse proxy có thể làm thay đổi URI đầy đủ. Khi cần xác minh URI, có thể kiểm tra phần path theo cấu hình test.

## 11. Những lỗi thường gặp khi dùng EntityModel với entity

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm EntityModel với JPA @Entity | Dùng wrapper như một lớp persistence | Xem EntityModel là lớp biểu diễn response |
| Bọc trực tiếp entity có quan hệ lazy | Có thể kích hoạt truy vấn ngoài dự kiến hoặc lỗi khi serialize | Chuyển sang DTO và truy vấn dữ liệu cần thiết |
| Công khai toàn bộ entity | Lộ trường nội bộ và khóa cấu trúc API vào schema lưu trữ | Chọn DTO/representation có chủ đích |
| Quên link self | Client khó nhận biết URI của tài nguyên hiện tại | Tạo link self từ controller mapping |
| Dùng URL nối chuỗi thủ công | Client/server phụ thuộc cấu trúc route và dễ sai khi mapping đổi | Dùng WebMvcLinkBuilder hoặc link builder phù hợp |
| Đưa mọi quan hệ ORM vào response | Response lớn, vòng tham chiếu và coupling mạnh | Chọn link hoặc dữ liệu nhúng theo use case |
| Công bố link hành động nhưng không kiểm tra ở endpoint | Request cũ hoặc giả mạo vẫn có thể thực thi thao tác | Kiểm tra lại quyền và trạng thái ở server |
| Dùng relation không ổn định | Client phụ thuộc tên nội bộ hoặc tên method | Dùng relation theo ngôn ngữ nghiệp vụ và giữ ổn định |
| Trả model rỗng khi không tìm thấy | Client nhận HTTP 200 không phản ánh đúng trạng thái tài nguyên | Trả 404 hoặc status phù hợp |

## 12. Quy trình áp dụng EntityModel

Khi xây endpoint trả về một tài nguyên đơn, có thể thực hiện theo trình tự:

1. Xác định entity/domain object nguồn và các trường được phép công khai.
2. Tạo DTO/representation nếu entity chứa chi tiết persistence hoặc trường nội bộ.
3. Dùng EntityModel.of(content) để bọc nội dung.
4. Tạo link self từ mapping controller và thêm các relation cần thiết.
5. Chỉ thêm link hành động khi trạng thái và quyền hiện tại cho phép.
6. Dùng assembler nếu nhiều endpoint cần cùng cách chuyển đổi entity sang representation.
7. Trả EntityModel từ controller và công bố media type phù hợp.
8. Kiểm thử content, relation, trường hợp link tùy chọn và lỗi tài nguyên không tồn tại.

EntityModel giúp kết hợp nội dung tài nguyên với khả năng điều hướng hypermedia trong một kiểu trả về rõ ràng. Khi dùng cùng DTO và assembler, ứng dụng có thể giữ entity ở bên trong miền nghiệp vụ, kiểm soát dữ liệu API công bố và cung cấp các liên kết ổn định để client khám phá tài nguyên cũng như hành động khả dụng.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [RepresentationModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring MVC Link Builder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)

