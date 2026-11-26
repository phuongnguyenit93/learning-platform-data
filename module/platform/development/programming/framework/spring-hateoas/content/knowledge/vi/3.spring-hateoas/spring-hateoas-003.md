# Mô hình lập trình Spring HATEOAS

Spring HATEOAS tổ chức việc xây dựng REST API có hypermedia quanh một ý tưởng: controller trả về **mô hình biểu diễn tài nguyên**, mô hình đó mang dữ liệu cần công bố cùng các liên kết mô tả cách khám phá tài nguyên và thao tác tiếp theo. Thư viện cung cấp kiểu mô hình, đối tượng liên kết, công cụ tạo URL từ mapping của Spring MVC và cơ chế chuyển đổi đối tượng miền thành biểu diễn API.

Khi triển khai, nên tách ba trách nhiệm: đối tượng miền mô tả nghiệp vụ; representation model mô tả dữ liệu công khai của API; assembler chuyển đổi đối tượng miền thành representation model và bổ sung các liên kết thích hợp. Cách tổ chức này giúp controller gọn hơn và giữ quy tắc tạo liên kết nhất quán giữa các endpoint.

## 1. Cài đặt và các lớp nền tảng

Với ứng dụng Spring Boot MVC, dependency thường dùng là:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
```

Starter tích hợp Spring HATEOAS với hệ sinh thái Spring Boot và Jackson để tuần tự hóa các mô hình hypermedia. Nếu không dùng Spring Boot, ứng dụng có thể khai báo trực tiếp dependency `org.springframework.hateoas:spring-hateoas` và cấu hình hỗ trợ hypermedia theo cách triển khai của mình.

Các kiểu chính của mô hình lập trình gồm:

| Kiểu | Vai trò |
|---|---|
| `RepresentationModel<T>` | Lớp cơ sở cho representation model có thể chứa liên kết |
| `EntityModel<T>` | Bọc một đối tượng dữ liệu cùng các liên kết |
| `CollectionModel<T>` | Biểu diễn một tập hợp phần tử và các liên kết của tập hợp |
| `PagedModel<T>` | Biểu diễn một tập hợp có metadata phân trang |
| `Link` | Biểu diễn một liên kết hypermedia |
| `LinkRelation` | Định danh ý nghĩa của liên kết, thường được gọi là relation hoặc `rel` |
| `RepresentationModelAssembler` | Chuyển đổi đối tượng miền thành representation model |

Các lớp này thuộc tầng biểu diễn HTTP. Chúng không thay thế entity, aggregate hay repository của ứng dụng. Một đối tượng miền có thể chứa quy tắc và trạng thái nội bộ; representation model chỉ nên công bố những trường mà hợp đồng API cho phép máy khách nhìn thấy.

## 2. Chọn kiểu representation model phù hợp

### RepresentationModel

Khi muốn tạo một kiểu biểu diễn riêng có các trường dữ liệu và liên kết, hãy kế thừa `RepresentationModel`:

```java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

import java.math.BigDecimal;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private final Long id;
    private final String status;
    private final BigDecimal total;

    public OrderModel(Long id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public Long getId() {
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

Tham số generic `OrderModel` thể hiện kiểu của chính mô hình, cho phép các phương thức trong lớp cơ sở trả về kiểu cụ thể khi thêm hoặc thay đổi liên kết. Các getter giúp Jackson tuần tự hóa những thuộc tính công khai của mô hình.

Annotation `@Relation` định nghĩa tên relation dùng khi biểu diễn phần tử trong một tập hợp hypermedia. Trong ví dụ, mỗi phần tử có relation `order`, còn tập hợp được nhúng có relation `orders`. Việc đặt tên relation rõ ràng giúp máy khách diễn giải phần tử trong `_embedded`.

### EntityModel

Nếu dữ liệu đã có một DTO phù hợp và không cần tạo lớp con của `RepresentationModel`, có thể bọc DTO bằng `EntityModel`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;

OrderSummary summary = new OrderSummary(order.getId(), order.getStatus());

EntityModel<OrderSummary> model = EntityModel.of(
    summary,
    linkTo(methodOn(OrderController.class).one(order.getId())).withSelfRel()
);
```

`EntityModel<T>` là một representation model chứa một đối tượng nội dung và tập liên kết. Đây là lựa chọn ngắn gọn cho tài nguyên đơn giản. Khi API cần nhiều quy tắc biểu diễn, trường dữ liệu hoặc logic liên kết riêng, một lớp kế thừa `RepresentationModel` thường dễ tổ chức hơn.

### CollectionModel và PagedModel

`CollectionModel<T>` dùng cho tập hợp tài nguyên. Nó có thể chứa các representation model cùng liên kết ở cấp tập hợp, ví dụ liên kết `self` hoặc liên kết điều hướng đến một tài nguyên liên quan.

`PagedModel<T>` mở rộng ý tưởng đó với metadata phân trang như kích thước trang, số trang hiện tại, tổng số phần tử và tổng số trang. Khi dùng Spring Data, `PagedResourcesAssembler` có thể chuyển một `Page<T>` thành `PagedModel<D>` thông qua assembler của tài nguyên. Cách này giúp các liên kết `first`, `prev`, `self`, `next` và `last` được tạo phù hợp với trạng thái phân trang.

Nên chọn kiểu dựa trên hình dạng dữ liệu trả về: `EntityModel` cho một nội dung đơn, `CollectionModel` cho tập hợp, `PagedModel` cho tập hợp có phân trang, hoặc một lớp con `RepresentationModel` khi cần định nghĩa mô hình biểu diễn chuyên biệt.

## 3. Link và quan hệ liên kết

Một `Link` gồm URI đích và relation mô tả ý nghĩa của liên kết. URI trả lời câu hỏi “đi đâu”; relation trả lời câu hỏi “liên kết này đại diện cho điều gì”.

Spring HATEOAS cung cấp các relation chuẩn qua `IanaLinkRelations`, chẳng hạn:

- `SELF`: liên kết đến chính tài nguyên.
- `COLLECTION`: liên kết đến tập hợp chứa tài nguyên.
- `NEXT`, `PREV`, `FIRST`, `LAST`: điều hướng phân trang.
- `RELATED`: liên kết đến tài nguyên có liên quan.

Ví dụ tạo một liên kết:

```java
Link self = Link.of("/orders/42", IanaLinkRelations.SELF);
```

Với quan hệ nghiệp vụ riêng, API cần định nghĩa ý nghĩa ổn định và tài liệu hóa để máy khách có thể xử lý. Với HAL, relation mở rộng thường được biểu diễn bằng URI relation hoặc CURIE. Ví dụ:

```java
private static final String CANCEL_REL =
    "https://api.example.com/rels/cancel";

model.add(
    linkTo(methodOn(OrderController.class).cancel(order.getId()))
        .withRel(CANCEL_REL)
);
```

Máy khách hiểu relation `cancel` theo tài liệu API và theo URI được trả về. Không nên xem tên relation tùy ý như một từ khóa có ý nghĩa phổ quát đối với mọi máy khách.

Một liên kết có thể mang thêm metadata như tiêu đề, media type, ngôn ngữ hoặc tên. Spring HATEOAS cung cấp các phương thức như `withTitle`, `withType`, `withHreflang` và `withName` để bổ sung metadata phù hợp. Chỉ thêm metadata khi máy khách có nhu cầu sử dụng và hợp đồng API xác định ý nghĩa của nó.

## 4. Tạo liên kết từ mapping của controller

Có thể khởi tạo liên kết trực tiếp từ URI, nhưng việc tự nối chuỗi đường dẫn dễ làm mã tạo liên kết lệch khỏi mapping thực tế. Với Spring MVC, `WebMvcLinkBuilder` tạo liên kết từ controller và phương thức xử lý:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
```

- `linkTo(...)` tạo link builder từ thông tin mapping.
- `methodOn(...)` tạo tham chiếu đến phương thức controller để Spring HATEOAS đọc mapping và các tham số đường dẫn.
- `withSelfRel()` gắn relation chuẩn `self`.

Cách viết này giữ logic tạo URL gần với khai báo endpoint. Khi mapping thay đổi, liên kết được xây dựng từ phương thức controller sẽ theo mapping mới sau khi ứng dụng được biên dịch và chạy lại.

Các tham số cần thiết cho mapping, chẳng hạn ID trong đường dẫn, phải được truyền vào lời gọi `methodOn`. Với endpoint có query parameter, hãy bảo đảm các giá trị và quy tắc tạo link phản ánh đúng hợp đồng tìm kiếm hoặc lọc mà controller công bố.

## 5. Tách logic tạo biểu diễn bằng RepresentationModelAssembler

Nếu mỗi controller tự tạo DTO và gắn liên kết, logic này dễ bị lặp lại. `RepresentationModelAssembler` chuẩn hóa bước chuyển đổi từ đối tượng miền sang representation model. Ví dụ dưới đây dùng `OrderModel` đã định nghĩa ở trên.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    private static final String CANCEL_REL =
        "https://api.example.com/rels/cancel";

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        model.add(
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel(IanaLinkRelations.COLLECTION)
        );

        if (order.canBeCancelled()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(order.getId()))
                    .withRel(CANCEL_REL)
            );
        }

        return model;
    }
}
```

Phương thức `toModel` có thể thực hiện các công việc sau:

1. Chọn dữ liệu nghiệp vụ được phép công bố.
2. Chuyển dữ liệu miền sang kiểu biểu diễn API.
3. Tạo liên kết `self` và các liên kết điều hướng chung.
4. Bổ sung liên kết hành động dựa trên trạng thái nghiệp vụ hoặc ngữ cảnh đã được xác định.

Assembler không thay thế kiểm tra quyền truy cập trong service hoặc tầng bảo mật. Việc quyết định một liên kết có xuất hiện trong biểu diễn hay không chỉ mô tả khả năng mà API công bố cho máy khách. Endpoint thực thi hành động vẫn phải kiểm tra quyền, trạng thái hiện tại và các điều kiện nghiệp vụ khi nhận request.

## 6. Kết hợp assembler với controller

Sau khi có assembler, controller tập trung vào nhận request, gọi service và trả về representation model:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.web.bind.annotation.*;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.stream.Collectors;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public OrderModel one(@PathVariable Long id) {
        return assembler.toModel(orderService.findById(id));
    }

    @GetMapping
    public CollectionModel<OrderModel> all() {
        var orders = orderService.findAll()
            .stream()
            .map(assembler::toModel)
            .collect(Collectors.toList());

        return CollectionModel.of(
            orders,
            linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }

    @PostMapping("/{id}/cancel")
    public OrderModel cancel(@PathVariable Long id) {
        Order updated = orderService.cancel(id);
        return assembler.toModel(updated);
    }
}
```

Trong ví dụ này, endpoint đọc một đơn hàng trả về `OrderModel`; endpoint danh sách trả về `CollectionModel<OrderModel>`; endpoint hủy trả về biểu diễn mới sau khi service thực hiện nghiệp vụ. Cùng một assembler bảo đảm các cách biểu diễn đơn hàng đều dùng chung quy tắc trường dữ liệu và liên kết.

Các kiểu `Order` và `OrderService` đại diện cho domain model và tầng nghiệp vụ của ứng dụng. Chúng cần được triển khai theo domain thực tế. Ví dụ tập trung vào ranh giới giữa controller, service, assembler và mô hình hypermedia.

## 7. Biểu diễn thao tác bằng affordance

Một `Link` thông thường cho máy khách biết URI đích và relation. Nó không tự mô tả đầy đủ mọi chi tiết của thao tác như HTTP method, kiểu dữ liệu đầu vào hoặc biểu mẫu cần gửi. Khi API muốn công bố thêm thông tin về hành động, Spring HATEOAS cung cấp cơ chế *affordance*.

Ví dụ một liên kết tự tham chiếu có thể được mở rộng để mô tả thao tác cập nhật:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Affordances;
import org.springframework.hateoas.Link;
import org.springframework.http.HttpMethod;

Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();

Link update = Affordances.of(self)
    .afford(HttpMethod.PUT)
    .withInput(OrderUpdateInput.class)
    .withName("update")
    .toLink();

model.add(update);
```

`OrderUpdateInput` là kiểu dữ liệu mô tả các trường đầu vào của thao tác cập nhật. Affordance gắn thông tin hành động với liên kết, giúp một định dạng hypermedia có khả năng biểu diễn affordance công bố thêm thông tin cho máy khách.

HAL cơ bản tập trung vào cấu trúc tài nguyên và liên kết. Khi cần biểu diễn biểu mẫu hoặc thông tin đầu vào, có thể dùng định dạng hỗ trợ affordance như HAL-FORMS và bảo đảm máy khách hiểu media type đó. Cơ chế này giúp khám phá thao tác phong phú hơn, nhưng máy chủ vẫn phải xác thực dữ liệu và kiểm tra quyền khi thao tác thực sự được gửi.

## 8. Tuần tự hóa mô hình thành HAL

Spring HATEOAS có thể tuần tự hóa representation model thành định dạng hypermedia. Với HAL JSON, liên kết được đặt trong `_links`; các phần tử được nhúng trong `_embedded`.

Ví dụ một tài nguyên đơn:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/orders"
    },
    "https://api.example.com/rels/cancel": {
      "href": "https://api.example.com/orders/42/cancel"
    }
  }
}
```

Ví dụ tập hợp có thể được biểu diễn như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "total": 1250000,
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    }
  }
}
```

Relation `orders` trong `_embedded` lấy từ metadata quan hệ của kiểu mô hình, ví dụ `@Relation(collectionRelation = "orders")`. Đây là lý do nên đặt tên relation rõ ràng thay vì phụ thuộc vào tên lớp hoặc quy tắc mặc định.

Máy khách cần yêu cầu media type phù hợp, thường là `application/hal+json`. Trong Spring Boot, starter HATEOAS hỗ trợ cấu hình hypermedia và Jackson. Nếu ứng dụng dùng cấu hình Spring Framework riêng, cần bật hỗ trợ định dạng hypermedia tương ứng. Hợp đồng API nên công bố media type mà endpoint trả về và media type mà endpoint chấp nhận.

## 9. Phân trang và điều hướng tập hợp

Với danh sách lớn, trả về toàn bộ phần tử trong một `CollectionModel` có thể không phù hợp. `PagedModel` bổ sung metadata trang và các liên kết điều hướng để máy khách khám phá trang trước hoặc trang tiếp theo.

Nếu service trả về `Page<Order>` từ Spring Data, có thể dùng `PagedResourcesAssembler<Order>` để tạo `PagedModel<OrderModel>` với `OrderModelAssembler`. Assembler phân trang có thể tạo các liên kết phù hợp với số trang, kích thước trang và tổng số phần tử. Nhờ vậy, máy khách theo liên kết được cung cấp thay vì tự tính URL của trang kế tiếp.

Khi tự tạo `PagedModel`, metadata thường gồm:

- `size`: số phần tử tối đa trên một trang.
- `number`: chỉ số trang hiện tại.
- `totalElements`: tổng số phần tử trong tập kết quả.
- `totalPages`: tổng số trang.

Các liên kết phân trang phải phản ánh đúng bộ lọc, thứ tự sắp xếp và kích thước trang hiện tại. Nếu chỉ thay đổi số trang mà làm mất query parameter tìm kiếm, máy khách sẽ nhận được điều hướng không còn cùng ngữ cảnh.

## 10. Kiểm thử representation model và hợp đồng hypermedia

Kiểm thử controller cần xác nhận cả dữ liệu lẫn liên kết mà API công bố. Một kiểm thử MockMvc đơn giản có thể xác nhận media type HAL và sự tồn tại của liên kết `self`:

```java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Ngoài kiểm tra đường dẫn liên kết, nên kiểm tra các tình huống nghiệp vụ làm thay đổi tập liên kết:

- Đơn hàng có thể hủy thì biểu diễn có relation hủy.
- Đơn hàng không thể hủy thì relation hủy không xuất hiện.
- Tài nguyên đơn luôn có liên kết `self`.
- Tập hợp có relation nhúng đúng như hợp đồng, ví dụ `orders`.
- Phân trang cung cấp liên kết điều hướng phù hợp với trang hiện tại.

Khi kiểm thử relation mở rộng, hãy xác nhận đúng URI relation đã thống nhất trong hợp đồng. Khi kiểm thử affordance, hãy xác nhận media type và phần mô tả thao tác mà máy khách thực sự tiêu thụ. Kiểm thử nên tập trung vào hành vi quan sát được của phản hồi HTTP, thay vì chỉ kiểm tra một phương thức nội bộ của assembler.

## 11. Nguyên tắc tổ chức mô hình lập trình

Một cấu trúc dễ duy trì thường có các trách nhiệm sau:

| Thành phần | Trách nhiệm |
|---|---|
| Domain model và service | Quy tắc nghiệp vụ, trạng thái và quyền thực hiện thao tác |
| DTO hoặc representation model | Các trường dữ liệu công khai trong hợp đồng API |
| Assembler | Chuyển domain model thành representation model và tạo liên kết |
| Controller | Nhận request, gọi service và trả về representation model |
| Hypermedia configuration | Định dạng và media type dùng để tuần tự hóa mô hình |
| Controller/API tests | Xác minh dữ liệu, relation, URI và affordance được công bố |

Một số nguyên tắc nên được giữ nhất quán:

- Không đưa entity nội bộ ra HTTP chỉ để tiết kiệm một lớp DTO; representation model nên phản ánh hợp đồng công khai.
- Tạo URL từ mapping của controller bằng `WebMvcLinkBuilder` khi có thể.
- Dùng relation chuẩn cho quan hệ đã đăng ký; tài liệu hóa URI relation cho quan hệ mở rộng.
- Tập trung logic ánh xạ và tạo link trong assembler khi nhiều endpoint cùng biểu diễn một loại tài nguyên.
- Chỉ công bố hành động phù hợp với trạng thái và ngữ cảnh hiện tại.
- Luôn kiểm tra quyền và điều kiện nghiệp vụ ở endpoint thực thi thao tác.
- Kiểm thử phản hồi hypermedia như một phần của hợp đồng API.

Mô hình lập trình Spring HATEOAS kết hợp representation model, link và assembler để biến dữ liệu miền thành biểu diễn REST có thể điều hướng. Controller điều phối request, assembler tạo biểu diễn và liên kết, còn cơ chế hypermedia serialization chuyển mô hình đó thành HAL hoặc định dạng đã chọn. Khi các lớp trách nhiệm này được tổ chức rõ ràng, API dễ mở rộng relation, thay đổi URL và duy trì hợp đồng điều hướng cho các máy khách.
