# Kế thừa model trong Spring HATEOAS

Spring HATEOAS cung cấp `RepresentationModel` làm lớp cơ sở cho các biểu diễn tài nguyên có liên kết hypermedia. Khi kiểu biểu diễn cần có cấu trúc riêng, bạn có thể tạo một class kế thừa lớp này, khai báo các thuộc tính mà API muốn công bố rồi thêm liên kết bằng `Link`. Cách làm đó tạo ra một representation chuyên biệt, có thể tái sử dụng trong assembler và controller.

Bài học này tập trung vào cách kế thừa `RepresentationModel`, ý nghĩa của generic self type, cách tổ chức lớp cơ sở dùng chung và cách kiểm thử model sau khi được tuần tự hóa. Ví dụ xuyên suốt sử dụng API quản lý đơn hàng. Mục tiêu là chọn được cấu trúc model phù hợp với hợp đồng API, đồng thời giữ domain model và dữ liệu lưu trữ độc lập với representation công khai.

## 1. Vì sao cần kế thừa RepresentationModel?

Trong Spring HATEOAS, `EntityModel<T>` có thể bọc một đối tượng dữ liệu cùng các liên kết. Đây là lựa chọn gọn khi representation chỉ cần chứa một DTO có sẵn. Tuy nhiên, có những API cần một kiểu biểu diễn được thiết kế riêng, chẳng hạn:

- Tài nguyên gồm các trường được tổng hợp từ nhiều nguồn dữ liệu.
- Representation cần công bố một cấu trúc ổn định, khác với DTO của một domain object.
- Nhiều endpoint cần dùng chung một kiểu model có thuộc tính và hành vi tạo liên kết nhất quán.
- Nhóm muốn định nghĩa một lớp cơ sở cho các model cùng chia sẻ mã tài nguyên, thông tin kiểm toán hoặc metadata.

Trong các trường hợp đó, một class kế thừa `RepresentationModel` cho phép khai báo trực tiếp các thuộc tính của representation và vẫn nhận được khả năng quản lý liên kết của Spring HATEOAS.

Ví dụ, API đơn hàng có thể trả mã đơn, trạng thái, tổng tiền và liên kết `self`, `cancel`. Các trường này tạo thành một kiểu `OrderModel` riêng:

```java
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
```

`OrderModel` kế thừa các khả năng quản lý liên kết từ `RepresentationModel` và bổ sung các thuộc tính của đơn hàng. Các getter giúp Jackson đọc giá trị để tuần tự hóa response. Đây là model phục vụ API; nó không cần là entity JPA và không nên mang trách nhiệm truy vấn cơ sở dữ liệu.

## 2. Hiểu generic self type của RepresentationModel

Khai báo `RepresentationModel<OrderModel>` có thể trông lạ nếu bạn mới làm quen với generic. Tham số `OrderModel` cho Spring HATEOAS biết kiểu model cụ thể đang kế thừa lớp cơ sở. Đây là cách dùng generic tự tham chiếu (self-referential generic), thường được gọi là *self type*.

Ý tưởng là các thao tác fluent trên model có thể trả về kiểu con cụ thể. Khi thêm liên kết vào `OrderModel`, kiểu kết quả vẫn gắn với `OrderModel` thay vì bị hạ xuống thành một kiểu cha chung. Nhờ đó, việc xâu chuỗi thao tác hoặc xây dựng model có kiểu rõ ràng hơn.

```java
OrderModel model = new OrderModel(id, "PENDING", total);

model.add(Link.of("/orders/" + id, "self"));
model.add(Link.of("/orders/" + id + "/cancel", "cancel"));
```

Tham số generic cần trỏ tới kiểu con thực tế. Với model khác, hãy khai báo self type tương ứng:

```java
public class CustomerModel extends RepresentationModel<CustomerModel> {
    // Các thuộc tính representation của khách hàng.
}
```

Không nên khai báo tất cả model bằng một tham số chung tùy tiện nếu điều đó làm mất mối quan hệ giữa kiểu con và kiểu trả về của các thao tác. Self type giúp API của model giữ được kiểu cụ thể khi kế thừa.

## 3. Phân biệt kế thừa RepresentationModel và dùng EntityModel

Hai cách đều tạo ra representation có thể chứa liên kết, nhưng phục vụ cách tổ chức dữ liệu khác nhau.

| Tiêu chí | `EntityModel<T>` | Class kế thừa `RepresentationModel<T>` |
| --- | --- | --- |
| Cấu trúc dữ liệu | Bọc một object có sẵn, ví dụ `OrderView`. | Khai báo trực tiếp các thuộc tính của kiểu model riêng. |
| Mức độ tùy biến | Phù hợp khi cấu trúc object đã đáp ứng hợp đồng. | Phù hợp khi cần cấu trúc representation chuyên biệt hoặc dùng chung lớp cơ sở. |
| Mã cần viết | Thường ít hơn, có thể tạo bằng `EntityModel.of(...)`. | Cần định nghĩa class, constructor và getter hoặc accessor phù hợp. |
| Tái sử dụng | Tái sử dụng DTO được bọc. | Có thể tái sử dụng qua kế thừa và các kiểu model chuyên biệt. |
| Khi nên chọn | Một DTO cùng liên kết là đủ. | Representation có cấu trúc riêng hoặc có nhiều model cần chung một lớp cơ sở. |

Ví dụ dùng `EntityModel`:

```java
OrderView view = new OrderView(order.getId(), order.getStatus().name(), order.getTotal());
EntityModel<OrderView> model = EntityModel.of(view);
model.add(linkTo(methodOn(OrderController.class).one(order.getId())).withSelfRel());
```

Ví dụ dùng class kế thừa:

```java
OrderModel model = new OrderModel(
        order.getId(),
        order.getStatus().name(),
        order.getTotal()
);
model.add(linkTo(methodOn(OrderController.class).one(order.getId())).withSelfRel());
```

Hãy chọn cách biểu diễn dựa trên hợp đồng mà client cần đọc và mức độ tái sử dụng trong ứng dụng. Không cần tạo một class riêng cho mọi endpoint nếu `EntityModel` cùng DTO đã đủ rõ ràng. Ngược lại, không nên ép một DTO dùng chung cho nhiều representation có ý nghĩa khác nhau chỉ để giảm số class.

## 4. Tổ chức lớp cơ sở dùng chung

Khi nhiều tài nguyên chia sẻ thuộc tính, có thể tạo một lớp cơ sở kế thừa `RepresentationModel`, sau đó để các model cụ thể kế thừa lớp cơ sở đó. Ví dụ, nhiều representation có thể cùng công bố mã tài nguyên:

```java
public abstract class ResourceModel<T extends ResourceModel<T>>
        extends RepresentationModel<T> {

    private final UUID id;

    protected ResourceModel(UUID id) {
        this.id = id;
    }

    public UUID getId() {
        return id;
    }
}
```

Model đơn hàng kế thừa lớp cơ sở:

```java
public class OrderModel extends ResourceModel<OrderModel> {

    private final String status;
    private final BigDecimal total;

    public OrderModel(UUID id, String status, BigDecimal total) {
        super(id);
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Ở đây `ResourceModel<T>` cũng dùng self type để giữ quan hệ kiểu khi kế thừa. `OrderModel` truyền chính nó làm tham số generic: `ResourceModel<OrderModel>`. Một model khác có thể dùng cùng lớp cơ sở với kiểu riêng của nó.

Chỉ nên tạo lớp cơ sở khi các model thật sự chia sẻ ý nghĩa và hành vi. Nếu hai tài nguyên chỉ tình cờ có một trường tên giống nhau nhưng ý nghĩa khác nhau, kế thừa có thể làm hợp đồng API khó hiểu. Khi dữ liệu dùng chung là một nhóm thuộc tính độc lập, composition (nhúng một object metadata) có thể phù hợp hơn.

Java chỉ cho một class kế thừa trực tiếp một class khác. Nếu model cần thêm hành vi từ nhiều nhóm, hãy cân nhắc interface, composition hoặc các thành phần hỗ trợ thay vì cố tạo một cây kế thừa sâu. Model API nên dễ đọc và phản ánh cấu trúc representation mà client cần.

## 5. Chuyển domain object thành model trong assembler

Khi đã có `OrderModel`, hãy tập trung việc chuyển đổi vào `RepresentationModelAssembler`. Assembler nhận domain object, lấy những dữ liệu cần công bố, tạo model rồi thêm các liên kết phù hợp.

```java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        UUID id = order.getId();
        OrderModel model = new OrderModel(
                id,
                order.getStatus().name(),
                order.getTotal()
        );

        model.add(linkTo(methodOn(OrderController.class).one(id)).withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel"));
        }

        return model;
    }
}
```

Trong ví dụ, `Order` là domain object, `OrderModel` là representation. Assembler không trả entity trực tiếp và không để model tự truy cập repository. Quy tắc `canBeCancelled()` nên được xác định bởi domain hoặc service; assembler sử dụng kết quả đó để quyết định relation nào được công bố.

Với một collection, assembler có thể dùng phương thức `toCollectionModel` được cung cấp bởi interface để chuyển nhiều domain object thành collection model. Khi cần liên kết ở cấp collection, hãy bổ sung chúng sau khi tạo collection và kiểm thử relation đó độc lập với liên kết của từng phần tử.

## 6. Trả model từ controller

Controller nhận request, gọi service và dùng assembler tạo representation:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    OrderModel one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }

    @GetMapping
    CollectionModel<OrderModel> all() {
        return assembler.toCollectionModel(service.findAll());
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

Spring HATEOAS có thể tuần tự hóa `OrderModel` như một representation hypermedia khi ứng dụng được cấu hình với media type tương ứng. Client yêu cầu HAL bằng header `Accept: application/hal+json`. Các thuộc tính của model được xuất cùng phần liên kết theo cấu trúc HAL.

Một response minh họa có thể có dạng:

```json
{
  "id": "42",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "cancel": {
      "href": "/orders/42/cancel"
    }
  }
}
```

Đây là cấu trúc minh họa cho hợp đồng HAL; response thực tế phụ thuộc tên relation, cấu hình serialization và các trường của model. Hãy xác minh cả content type lẫn JSON được xuất ra thay vì chỉ kiểm tra object Java được tạo thành công.

## 7. Kiểm thử model kế thừa

Kiểm thử nên bao gồm hai lớp trách nhiệm: kiểm thử assembler để xác nhận dữ liệu và liên kết được tạo đúng, và kiểm thử HTTP để xác nhận representation được tuần tự hóa theo hợp đồng.

### Kiểm thử assembler

Một kiểm thử assembler có thể xác nhận model chứa đúng dữ liệu và relation `self`:

```java
@Test
void createsOrderModelWithSelfLink() {
    Order order = anOrderWithId(UUID.fromString("00000000-0000-0000-0000-000000000042"));

    OrderModel model = assembler.toModel(order);

    assertThat(model.getId()).isEqualTo(order.getId());
    assertThat(model.getStatus()).isEqualTo(order.getStatus().name());
    assertThat(model.getLinks()).anyMatch(link -> link.getRel().value().equals("self"));
}
```

Hàm `anOrderWithId` đại diện cho fixture hoặc factory của dự án. Khi kiểm thử liên kết, có thể so sánh cả relation và `href` để chắc chắn URI được tạo từ mapping đúng. Với relation nghiệp vụ, tạo dữ liệu ở cả trạng thái cho phép và không cho phép thao tác.

### Kiểm thử response HAL

Với Spring MVC và MockMvc, kiểm tra response từ endpoint:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu đơn hàng đang ở trạng thái có thể hủy, kiểm tra relation `cancel` xuất hiện. Nếu đơn đã giao, kiểm tra relation đó không xuất hiện. Tên trường JSON và cách biểu diễn UUID cần khớp với cấu hình serializer của ứng dụng.

Kiểm thử thêm trường hợp endpoint hủy bị từ chối khi người dùng không đủ quyền hoặc đơn hàng đã chuyển trạng thái. Sự hiện diện của liên kết chỉ thông báo khả năng điều hướng tại thời điểm representation được tạo; endpoint vẫn phải kiểm tra quyền và trạng thái khi request thực sự đến.

## 8. Các giới hạn và lỗi thiết kế thường gặp

**Đưa domain entity trực tiếp vào model.** Điều này dễ làm lộ trường nội bộ, kéo theo quan hệ lazy hoặc khiến schema API phụ thuộc vào cấu trúc lưu trữ. Hãy chuyển dữ liệu cần thiết sang representation model chuyên biệt.

**Kế thừa quá sâu.** Nhiều lớp cơ sở với trách nhiệm chồng lấn làm model khó hiểu và khó thay đổi. Chỉ tạo lớp cha khi có thuộc tính hoặc hành vi thực sự dùng chung; ưu tiên composition cho nhóm dữ liệu độc lập.

**Dùng sai self type.** Nếu model con truyền một kiểu generic không phản ánh chính nó, các phương thức fluent kế thừa có thể không còn giữ kiểu con như mong muốn. Hãy dùng `RepresentationModel<ConcreteModel>` cho model cụ thể và kiểm tra kiểu generic khi tạo lớp cơ sở.

**Nhầm model với quy tắc nghiệp vụ.** Model nên mô tả dữ liệu công khai và các liên kết. Việc quyết định có thể hủy, duyệt hoặc thanh toán phải thuộc domain/service; assembler chỉ sử dụng kết quả để tạo representation.

**Tạo liên kết bằng cách nối chuỗi URI.** URI thủ công dễ sai khi mapping thay đổi hoặc ứng dụng có context path. Trong Spring MVC, ưu tiên `WebMvcLinkBuilder` với `linkTo` và `methodOn`.

**Cho rằng có liên kết nghĩa là được phép thao tác.** Liên kết giúp client khám phá API. Xác thực, phân quyền và kiểm tra trạng thái vẫn phải diễn ra ở endpoint cho mỗi request.

**Dùng class kế thừa trong mọi tình huống.** Nếu chỉ cần bọc một DTO rồi thêm vài liên kết, `EntityModel<T>` thường đơn giản hơn. Ngoài ra, Java record không thể kế thừa `RepresentationModel` vì record đã kế thừa ngầm `java.lang.Record`; nếu muốn dùng record làm dữ liệu, hãy bọc record bằng `EntityModel<RecordType>` hoặc dùng một class representation riêng.

## 9. Bài tập thực hành

Thực hiện các bài tập sau trong một ứng dụng Spring Boot có Spring HATEOAS:

1. Tạo `OrderModel extends RepresentationModel<OrderModel>` với các trường `id`, `status`, `total` và getter tương ứng.
2. Tạo `CustomerModel extends RepresentationModel<CustomerModel>` và thêm liên kết `self` cho tài nguyên khách hàng.
3. Viết `OrderModelAssembler` để chuyển `Order` thành `OrderModel`, thêm `self` và chỉ thêm `cancel` khi trạng thái cho phép.
4. Tạo lớp cơ sở generic `ResourceModel<T>` chứa mã tài nguyên, sau đó cho `OrderModel` kế thừa. Kiểm tra kiểu trả về của các thao tác thêm liên kết vẫn giữ kiểu model cụ thể.
5. Trả `OrderModel` từ controller và xác nhận response có các trường dữ liệu cùng `_links` khi client yêu cầu HAL.
6. Viết kiểm thử cho đơn hàng có thể hủy và không thể hủy; kiểm tra cả liên kết lẫn hành vi endpoint.
7. Thử thay đổi URI mapping của endpoint chi tiết, sau đó xác nhận liên kết `self` được tạo theo mapping mới và client dựa trên relation vẫn điều hướng được.

Khi hoàn thành, bạn nên giải thích được tại sao `OrderModel` kế thừa `RepresentationModel<OrderModel>`, khi nào nên chọn `EntityModel<OrderView>`, và vì sao assembler là nơi thích hợp để chuyển domain object thành representation.

## 10. Danh sách kiểm tra trước khi sử dụng trong dự án

- Model chỉ công bố các trường cần thiết cho client.
- Generic self type trỏ tới kiểu model cụ thể.
- Lớp cơ sở chỉ chứa thuộc tính hoặc hành vi thực sự dùng chung.
- Domain entity và representation model có trách nhiệm riêng.
- Assembler tạo model và liên kết; domain/service quyết định quy tắc nghiệp vụ.
- URI liên kết được dựng từ mapping phù hợp.
- Relation có tên và ý nghĩa ổn định trong hợp đồng API.
- Response HAL có content type và cấu trúc `_links` đúng.
- Kiểm thử bao gồm dữ liệu, relation, URI, trạng thái và quyền truy cập.

Kế thừa `RepresentationModel` giúp bạn định nghĩa kiểu biểu diễn hypermedia phù hợp với hợp đồng của ứng dụng. Khi kết hợp self type đúng cách, assembler có trách nhiệm rõ ràng và kiểm thử ở cả cấp model lẫn HTTP, các representation chuyên biệt có thể được mở rộng mà vẫn giữ liên kết và cấu trúc API nhất quán.
