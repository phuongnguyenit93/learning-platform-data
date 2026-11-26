# EntityModel với DTO trong Spring HATEOAS

`EntityModel<T>` là kiểu biểu diễn dùng để bọc một đối tượng nội dung cùng các liên kết hypermedia. Khi kết hợp với DTO, nó cho phép API trả về dữ liệu đã được chọn lọc cho máy khách và bổ sung các liên kết điều hướng mà không cần biến DTO thành một lớp phụ thuộc trực tiếp vào Spring HATEOAS.

Đây là cách tổ chức phù hợp khi DTO đã mô tả tốt dữ liệu công khai của một tài nguyên, còn controller hoặc assembler chịu trách nhiệm gắn `self`, liên kết đến tập hợp và các hành động khả dụng.

## 1. EntityModel là gì?

Trong Spring HATEOAS, `EntityModel<T>` đại diện cho một tài nguyên đơn. Nó giữ một đối tượng nội dung kiểu `T` và một tập các `Link` mô tả tài nguyên đó có thể được khám phá hoặc tương tác như thế nào.

Ví dụ, DTO đơn hàng có thể chứa mã, trạng thái và tổng tiền:

```java
import java.math.BigDecimal;

public record OrderDto(
    Long id,
    String status,
    BigDecimal total
) {}
```

Ví dụ dùng Java record, có từ Java 16. Với phiên bản Java cũ hơn, có thể định nghĩa DTO bằng class bất biến với constructor và getter.

Khi bọc DTO này bằng `EntityModel`, API có thể cung cấp thêm liên kết:

```java
EntityModel<OrderDto> model = EntityModel.of(orderDto);
```

Kiểu generic `T` cho biết nội dung mà EntityModel đang bọc. Trong ví dụ, `T` là `OrderDto`, do đó kiểu trả về là `EntityModel<OrderDto>`.

Cần phân biệt hai khái niệm:

- **Entity trong domain hoặc persistence:** đối tượng nghiệp vụ hoặc entity JPA, có thể chứa trạng thái và chi tiết nội bộ.
- **EntityModel trong Spring HATEOAS:** wrapper thuộc tầng biểu diễn HTTP, chứa nội dung được công bố và các liên kết hypermedia.

Tên `EntityModel` không có nghĩa là phải bọc một JPA entity. Trong API thực tế, nên ưu tiên bọc DTO đã được thiết kế cho hợp đồng công khai.

## 2. Vì sao kết hợp EntityModel với DTO?

DTO (Data Transfer Object) định nghĩa dữ liệu được trao đổi qua API. DTO giúp kiểm soát trường nào được trả về, kiểu dữ liệu và cấu trúc mà máy khách phụ thuộc.

Nếu DTO tự kế thừa `RepresentationModel`, lớp dữ liệu sẽ phụ thuộc vào Spring HATEOAS. Cách làm đó có thể hợp lý khi chính DTO là một representation model chuyên biệt, nhưng không cần thiết trong mọi trường hợp.

Khi dùng `EntityModel<DTO>`, hai trách nhiệm được tách rõ:

| Thành phần | Trách nhiệm |
|---|---|
| DTO | Mô tả dữ liệu công khai của tài nguyên |
| EntityModel | Bọc DTO và giữ các liên kết hypermedia |
| Mapper | Chuyển domain object thành DTO |
| Assembler | Bọc DTO bằng EntityModel và thêm liên kết |
| Controller | Nhận request, gọi nghiệp vụ và trả về representation |

Cách kết hợp này mang lại một số lợi ích:

- DTO có thể được dùng ở những nơi không cần Spring HATEOAS.
- Link được thêm tại tầng biểu diễn, không phải trộn vào dữ liệu nghiệp vụ.
- API tránh công bố trực tiếp entity JPA và các trường nội bộ.
- Cùng một DTO có thể được bọc với các liên kết khác nhau tùy ngữ cảnh endpoint.
- Logic ánh xạ và tạo liên kết có thể được tái sử dụng trong assembler.

## 3. Tạo EntityModel từ DTO

Cách đơn giản nhất là dùng factory method `EntityModel.of(...)`.

### Bọc nội dung mà chưa thêm liên kết

```java
OrderDto dto = new OrderDto(
    order.getId(),
    order.getStatus().name(),
    order.getTotal()
);

EntityModel<OrderDto> model = EntityModel.of(dto);
```

Ở thời điểm này, model đã có nội dung nhưng chưa công bố liên kết. Có thể thêm link sau khi xác định được ngữ cảnh và các mapping của API.

### Tạo nội dung cùng các liên kết

Factory method cũng nhận các liên kết:

```java
EntityModel<OrderDto> model = EntityModel.of(
    dto,
    linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel()
);
```

Ví dụ tạo một link `self` trỏ đến endpoint đọc chính đơn hàng. Cách này ngắn gọn khi model chỉ cần một vài liên kết và tất cả đã có sẵn tại thời điểm tạo.

### Thêm liên kết sau khi tạo

Khi liên kết phụ thuộc vào trạng thái nghiệp vụ, có thể tạo model trước rồi thêm từng link:

```java
EntityModel<OrderDto> model = EntityModel.of(dto);

model.add(
    linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel()
);

if (order.canBeCancelled()) {
    model.add(
        linkTo(methodOn(OrderController.class).cancel(order.getId()))
            .withRel("https://api.example.com/rels/cancel")
    );
}
```

`add(Link)` thêm liên kết vào model. Việc kiểm tra `canBeCancelled()` quyết định API có công bố liên kết điều hướng tới thao tác hủy hay không. Endpoint hủy vẫn phải kiểm tra trạng thái, quyền và điều kiện nghiệp vụ tại thời điểm nhận request.

## 4. Tạo link bằng WebMvcLinkBuilder

Không nên ghép URL bằng cách nối chuỗi như `"/orders/" + id` ở nhiều nơi trong ứng dụng. Nếu mapping thay đổi, các chuỗi URL có thể không còn khớp với controller.

Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo liên kết từ mapping Spring MVC:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
```

- `methodOn(...)` tham chiếu đến phương thức controller và các tham số cần cho mapping.
- `linkTo(...)` tạo link builder từ mapping đó.
- `withSelfRel()` gắn quan hệ chuẩn `self`.

Với liên kết đến tập hợp, có thể dùng relation chuẩn:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link collection = linkTo(
    methodOn(OrderController.class).all()
).withRel(IanaLinkRelations.COLLECTION);
```

Các relation chuẩn được Spring HATEOAS cung cấp qua `IanaLinkRelations`, chẳng hạn `SELF`, `COLLECTION`, `NEXT`, `PREV`, `FIRST` và `LAST`.

Với quan hệ nghiệp vụ riêng như hủy đơn, thanh toán hoặc theo dõi vận chuyển, API nên định nghĩa và tài liệu hóa URI relation ổn định. Ví dụ `https://api.example.com/rels/cancel` có thể mô tả liên kết tới thao tác hủy. Máy khách cần biết ý nghĩa của relation qua tài liệu hợp đồng API; tên relation tùy ý không tự có ý nghĩa phổ quát.

## 5. Ánh xạ domain object sang DTO trước khi bọc

Một lỗi thường gặp là đưa entity JPA thẳng vào `EntityModel`:

```java
// Không nên dùng làm mặc định cho API công khai.
return EntityModel.of(orderEntity);
```

Cách làm này có thể làm lộ trường nội bộ, kéo theo quan hệ ORM không cần thiết, gây vòng lặp khi tuần tự hóa hoặc khiến cấu trúc persistence trở thành hợp đồng API ngoài ý muốn.

Thay vào đó, chuyển domain object sang DTO:

```java
import org.springframework.stereotype.Component;

@Component
public class OrderDtoMapper {

    public OrderDto toDto(Order order) {
        return new OrderDto(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );
    }
}
```

Mapper chỉ chọn các trường được phép công bố. Nếu API có nhiều dạng biểu diễn, có thể định nghĩa DTO riêng cho danh sách, chi tiết hoặc màn hình tóm tắt. Việc chọn DTO phải theo hợp đồng và use case, không theo toàn bộ thuộc tính của entity.

## 6. Tổ chức việc tạo EntityModel bằng assembler

Khi nhiều endpoint cần tạo cùng một kiểu tài nguyên, nên gom logic ánh xạ và tạo link vào một assembler. Spring HATEOAS định nghĩa `RepresentationModelAssembler<T, D>`; kiểu biểu diễn `D` có thể là `EntityModel<OrderDto>`.

Ví dụ:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderDtoAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    private static final String CANCEL_REL =
        "https://api.example.com/rels/cancel";

    private final OrderDtoMapper mapper;

    public OrderDtoAssembler(OrderDtoMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = mapper.toDto(order);
        EntityModel<OrderDto> model = EntityModel.of(dto);

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

Assembler thực hiện ba việc liên quan trực tiếp đến representation:

1. Gọi mapper để tạo DTO từ domain object.
2. Bọc DTO bằng `EntityModel.of(dto)`.
3. Thêm các liên kết theo danh tính, quan hệ và trạng thái của tài nguyên.

Assembler không nên tự thay thế service nghiệp vụ hoặc tầng bảo mật. Việc thêm hoặc ẩn link chỉ điều khiển khả năng điều hướng được công bố trong phản hồi. Endpoint đích vẫn phải thực hiện kiểm tra quyền và điều kiện nghiệp vụ.

## 7. Trả EntityModel từ controller

Sau khi có assembler, controller có thể trả về kiểu `EntityModel<OrderDto>`:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.*;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderDtoAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderDtoAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        Order order = orderService.findById(id);
        return assembler.toModel(order);
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderDto>> all() {
        List<EntityModel<OrderDto>> models = orderService.findAll()
            .stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(
            models,
            linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }

    @PostMapping("/{id}/cancel")
    public EntityModel<OrderDto> cancel(@PathVariable Long id) {
        Order updated = orderService.cancel(id);
        return assembler.toModel(updated);
    }
}
```

Ở đây:

- Endpoint `GET /orders/{id}` trả về một `EntityModel<OrderDto>`.
- Endpoint `GET /orders` trả về `CollectionModel<EntityModel<OrderDto>>`, tức tập hợp các model đơn cùng link ở cấp collection.
- Endpoint hủy gọi service để thực hiện nghiệp vụ rồi trả về representation của trạng thái mới.

Các lớp `Order` và `OrderService` đại diện cho domain model và tầng nghiệp vụ của ứng dụng. Chúng cần được triển khai theo mô hình thực tế. Ví dụ sử dụng `Stream.toList()`, phù hợp với Java 16 trở lên; với phiên bản Java cũ hơn có thể dùng `collect(Collectors.toList())`.

## 8. EntityModel được tuần tự hóa thành HAL như thế nào?

Khi ứng dụng trả về `EntityModel<OrderDto>` và dùng HAL JSON, các trường của DTO xuất hiện trực tiếp trong biểu diễn cùng với thuộc tính `_links`. Nội dung DTO không bị bọc thêm trong một trường `content`.

Ví dụ phản hồi:

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

Cấu trúc này giúp máy khách đọc dữ liệu đơn hàng và các liên kết từ cùng một biểu diễn. Link `self` trỏ đến tài nguyên hiện tại; `collection` đưa máy khách về tập hợp; relation mở rộng `cancel` công bố khả năng điều hướng tới thao tác hủy.

Để nhận HAL, máy khách có thể gửi header:

```http
Accept: application/hal+json
```

Trong ứng dụng Spring Boot, `spring-boot-starter-hateoas` cung cấp tích hợp cần thiết cho các kiểu hypermedia và Jackson. Hợp đồng API cần xác định media type mà endpoint trả về, cũng như các media type mà endpoint chấp nhận.

## 9. EntityModel trong collection và relation nhúng

`EntityModel` dành cho tài nguyên đơn. Khi cần trả về nhiều tài nguyên, có thể kết hợp nó với `CollectionModel`:

```java
List<EntityModel<OrderDto>> orders = orderService.findAll()
    .stream()
    .map(assembler::toModel)
    .toList();

CollectionModel<EntityModel<OrderDto>> collection =
    CollectionModel.of(orders);
```

Mỗi phần tử có thể mang liên kết `self` riêng; collection có thể có liên kết `self`, `next`, `prev` hoặc các liên kết tìm kiếm tùy theo API.

Khi tuần tự hóa thành HAL, collection thường có cấu trúc `_embedded` chứa danh sách phần tử và `_links` chứa liên kết cấp tập hợp. Relation dùng để đặt tên phần tử nhúng cần được xác định ổn định trong hợp đồng. Có thể khai báo metadata relation trên kiểu nội dung hoặc cấu hình relation/fallback type phù hợp với mô hình ứng dụng.

Không nên dùng `EntityModel` để bọc toàn bộ danh sách như thể danh sách là một tài nguyên đơn. Dùng `CollectionModel` cho tập hợp và `PagedModel` khi cần metadata phân trang.

## 10. Kiểm thử EntityModel với DTO

Kiểm thử controller nên xác nhận nội dung DTO và các liên kết hypermedia mà máy khách thực sự nhận được. Ví dụ với MockMvc:

```java
mockMvc.perform(
        get("/orders/42").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.status").value("PENDING"))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/cancel'].href"
    ).exists());
```

Với đơn hàng không thể hủy, dùng một trường hợp kiểm thử riêng để xác nhận relation hủy không xuất hiện:

```java
mockMvc.perform(
        get("/orders/43").accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/cancel']"
    ).doesNotExist());
```

Nên kiểm tra cả trường hợp đơn hàng không thể hủy để bảo đảm link hành động không được công bố khi trạng thái không cho phép. Đồng thời, kiểm tra endpoint hủy từ chối request không đủ quyền hoặc không hợp lệ.

Một số điểm cần xác nhận trong kiểm thử:

- DTO chỉ chứa các trường được phép công bố.
- Link `self` trỏ đúng tài nguyên đang đọc.
- Link `collection` hoặc relation liên quan có URI đúng.
- Link hành động xuất hiện theo trạng thái và ngữ cảnh phù hợp.
- Phản hồi dùng đúng media type.
- Collection có relation nhúng và liên kết cấp tập hợp như hợp đồng đã định nghĩa.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Bọc entity JPA trực tiếp | Lộ trường nội bộ, quan hệ ORM hoặc gây lỗi tuần tự hóa | Ánh xạ sang DTO trước |
| Tự ghép URL bằng chuỗi | Link dễ lệch mapping controller | Dùng `WebMvcLinkBuilder` |
| Dùng relation tùy ý không tài liệu hóa | Máy khách không biết cách diễn giải link | Dùng relation chuẩn hoặc URI relation có tài liệu |
| Thêm link mà không kiểm tra ngữ cảnh | Máy khách thấy hành động không khả dụng | Tạo link theo trạng thái và quyền đã xác định |
| Xem việc ẩn link là cơ chế bảo mật | Endpoint vẫn có thể bị gọi trực tiếp | Kiểm tra quyền ở endpoint/service |
| Dùng EntityModel cho một collection | Mô hình biểu diễn không đúng hình dạng dữ liệu | Dùng `CollectionModel` hoặc `PagedModel` |
| Nhét link vào thuộc tính DTO | DTO phụ thuộc hypermedia và khó tái sử dụng | Để EntityModel giữ các link |

## 12. Khi nào nên dùng EntityModel với DTO?

`EntityModel<DTO>` phù hợp khi API trả về một tài nguyên đơn, DTO đã định nghĩa rõ nội dung công khai và cần bổ sung liên kết mà không muốn DTO phụ thuộc vào Spring HATEOAS.

Nếu cần mô hình biểu diễn có nhiều hành vi, trường dữ liệu hoặc logic hypermedia chuyên biệt, có thể tạo lớp riêng kế thừa `RepresentationModel`. Nếu trả về nhiều phần tử, dùng `CollectionModel`; nếu cần phân trang, dùng `PagedModel`.

Trong đa số API Spring MVC, cách tổ chức dễ duy trì là domain/service quản lý nghiệp vụ, mapper chuyển domain object thành DTO, assembler bọc DTO bằng `EntityModel` và tạo link, còn controller trả về representation tương ứng. Nhờ đó, dữ liệu công khai và khả năng điều hướng được công bố rõ ràng, trong khi DTO vẫn có thể được sử dụng độc lập ở những phần khác của ứng dụng.
