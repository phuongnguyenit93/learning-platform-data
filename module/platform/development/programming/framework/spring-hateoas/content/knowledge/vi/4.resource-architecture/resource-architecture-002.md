# Resource representation

Trong REST, **resource (tài nguyên)** là khái niệm mà server công bố và client truy cập qua URI. **Representation (biểu diễn tài nguyên)** là dạng dữ liệu cụ thể được trao đổi khi client đọc hoặc gửi thông tin về tài nguyên đó. Một tài nguyên có thể có nhiều representation tùy theo trạng thái hiện tại, quyền truy cập, nhu cầu của client và media type được thương lượng.

Spring HATEOAS giúp xây dựng representation chứa cả dữ liệu lẫn hypermedia. Thay vì trả một đối tượng nghiệp vụ thô hoặc tự ghép JSON có trường `_links`, ứng dụng có thể dùng `RepresentationModel`, `EntityModel`, `CollectionModel` và assembler để định nghĩa hợp đồng phản hồi rõ ràng. Cách tổ chức này tách mô hình lưu trữ khỏi dữ liệu công bố qua API, đồng thời giúp client khám phá các tài nguyên liên quan bằng link.

## Resource và representation khác nhau thế nào?

Resource là một khái niệm trừu tượng của API. Ví dụ `/orders/42` nhận diện một đơn hàng. Tại một thời điểm, tài nguyên đó có trạng thái như mã đơn, trạng thái xử lý, tổng tiền và khách hàng liên quan. Client không nhất thiết được nhìn thấy toàn bộ trạng thái nội bộ này.

Representation là cách server chọn và trình bày thông tin của tài nguyên trong một lần trao đổi. Cùng đơn hàng `/orders/42` có thể được biểu diễn theo nhiều cách:

- Một representation tóm tắt chỉ có mã đơn và trạng thái để hiển thị trong danh sách.
- Một representation chi tiết có thêm tổng tiền, địa chỉ giao hàng và các mục hàng.
- Một representation dành cho nhân viên vận hành có thêm thông tin xử lý nội bộ nếu người dùng có quyền.
- Một representation HAL có dữ liệu đơn hàng cùng các link tới chính đơn hàng, khách hàng và các thao tác khả dụng.

Do đó, URI nhận diện tài nguyên; representation là nội dung server chọn để trao đổi về tài nguyên tại thời điểm request. Thay đổi representation không nhất thiết đồng nghĩa thay đổi tài nguyên hoặc mô hình nghiệp vụ phía server.

## Phân biệt domain entity, DTO và representation model

Các lớp này có vai trò khác nhau trong ứng dụng:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Domain entity | Mô hình nghiệp vụ và trạng thái do ứng dụng quản lý; có thể gắn với persistence. | `Order` chứa trạng thái đơn, khách hàng và các quy tắc nghiệp vụ. |
| DTO (Data Transfer Object) | Cấu trúc dữ liệu được thiết kế để truyền qua ranh giới ứng dụng. | `OrderSummary` chỉ có `id`, `status` và `total`. |
| Representation | Nội dung và metadata cụ thể được trao đổi cho một tài nguyên qua HTTP. | JSON của đơn hàng, có thể kèm liên kết hypermedia. |
| Spring HATEOAS model | Kiểu Java dùng để xây representation có link. | `EntityModel<OrderSummary>`. |

Không nên mặc định trả trực tiếp JPA entity làm response. Entity có thể chứa trường nội bộ, quan hệ lazy, tham chiếu vòng hoặc cấu trúc thay đổi theo cách tổ chức persistence. Nếu serialize entity trực tiếp, thay đổi trong database model có thể vô tình trở thành thay đổi hợp đồng API. DTO giúp chọn chính xác trường được công bố và ổn định cấu trúc response theo nhu cầu của client.

Representation model của Spring HATEOAS có thể bọc DTO. Nhờ đó, ứng dụng giữ được ranh giới rõ: domain model thực hiện nghiệp vụ, DTO mô tả dữ liệu trao đổi, còn HATEOAS model gắn thêm các điều khiển hypermedia.

## Thành phần của một representation

Một representation có thể được hiểu qua ba phần liên quan:

1. **Dữ liệu tài nguyên:** những thuộc tính client cần để hiểu trạng thái hoặc nội dung, ví dụ `id`, `status`, `total`.
2. **Metadata biểu diễn:** thông tin giúp diễn giải dữ liệu, thường được xác định qua media type và các metadata HTTP liên quan. Ví dụ `application/hal+json` cho biết cấu trúc hypermedia HAL JSON.
3. **Điều khiển hypermedia:** link và các thông tin tương tác cho phép client khám phá tài nguyên liên quan hoặc hành động tiếp theo.

Không phải representation nào cũng cần tất cả các thuộc tính nghiệp vụ. Chỉ đưa dữ liệu cần thiết cho use case và quyền truy cập tương ứng. Link cũng có ý nghĩa hợp đồng: `self` chỉ tài nguyên hiện tại, `customer` có thể chỉ tài nguyên khách hàng, còn `orders` có thể chỉ collection. Client dựa vào quan hệ (`rel`) để hiểu link, thay vì suy luận từ chuỗi URL.

## Mô hình hóa representation bằng Spring HATEOAS

Spring HATEOAS cung cấp một số kiểu cơ bản:

| Kiểu | Công dụng |
| --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho representation có thể gắn một hoặc nhiều `Link`. |
| `EntityModel<T>` | Bọc một đối tượng nội dung cùng các link của representation đó. |
| `CollectionModel<T>` | Biểu diễn một tập hợp các model và có thể gắn link cho cả collection. |
| `PagedModel<T>` | Biểu diễn collection có thông tin phân trang. |
| `RepresentationModelAssembler<T, D>` | Chuyển đối tượng nguồn thành model đích, tập trung logic tạo dữ liệu và link. |

Ví dụ, định nghĩa một DTO dành cho response chi tiết:

```java
import java.math.BigDecimal;

public record OrderRepresentation(
    Long id,
    String status,
    BigDecimal total
) {}
```

Assembler chuyển domain entity thành DTO rồi bọc trong `EntityModel`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel(),
            linkTo(methodOn(OrderController.class).all())
                .withRel("orders"),
            linkTo(methodOn(CustomerController.class).one(order.getCustomerId()))
                .withRel("customer"));
    }
}
```

`Order`, `OrderController`, `CustomerController` và các getter trong ví dụ là thành phần thuộc ứng dụng. `methodOn(...)` cho phép Spring HATEOAS suy ra URI từ mapping controller; lời gọi mô phỏng không chạy logic nghiệp vụ của endpoint. Assembler chỉ công bố các trường được chọn trong `OrderRepresentation` và gắn ba quan hệ `self`, `orders`, `customer`.

Controller có thể dùng assembler cho cả tài nguyên đơn lẻ và collection:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler assembler;

    OrderController(OrderRepository repository, OrderModelAssembler assembler) {
        this.repository = repository;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        return assembler.toModel(order);
    }

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(repository.findAll());
    }
}
```

Các kiểu `OrderRepository` và `OrderNotFoundException` được lược giản để tập trung vào representation. Với collection, mỗi phần tử có thể có link `self`, trong khi collection có thể có link riêng tới chính nó, bộ lọc hoặc trang tiếp theo. Khi có phân trang, dùng mô hình phân trang phù hợp và cung cấp các link điều hướng để client không phải tự tính URI trang.

## Representation trong HAL JSON

HAL (*Hypertext Application Language*) là một định dạng hypermedia phổ biến. Với HAL JSON, dữ liệu của tài nguyên thường nằm ở các thuộc tính thông thường; link được nhóm trong `_links`; tài nguyên liên quan được nhúng có thể nằm trong `_embedded`.

Ví dụ representation của đơn hàng:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "customer": {
      "href": "https://api.example.com/customers/7"
    }
  }
}
```

Trong ví dụ, ba trường đầu là dữ liệu DTO, còn `_links` cung cấp các đường điều hướng. Client có thể tìm relation `customer` để lấy thông tin khách hàng mà không phải tự ghép URI từ `customerId`.

Khi response có nhiều tài nguyên liên quan, server có thể chọn chỉ trả link hoặc nhúng representation con dưới `_embedded`. Hai cách có mục đích khác nhau:

- **Link:** client có thể truy cập tài nguyên liên quan khi cần; dữ liệu được lấy qua request riêng.
- **Embedded representation:** server gửi kèm dữ liệu liên quan trong response hiện tại, giảm số request nhưng làm response lớn hơn và có thể tạo bản sao dữ liệu tại thời điểm trả lời.

Chọn link hay embedded dựa trên nhu cầu sử dụng, kích thước dữ liệu, tần suất thay đổi và yêu cầu nhất quán. Không nên nhúng toàn bộ cây quan hệ chỉ vì có thể làm được; response quá sâu và quá lớn khiến client tải dữ liệu không cần thiết, đồng thời làm hợp đồng khó tiến hóa.

## Media type và content negotiation

Representation phải được diễn giải theo định dạng mà client và server thống nhất. HTTP dùng media type để mô tả định dạng nội dung. Một số ví dụ:

- `application/json`: JSON thông thường, không quy định cấu trúc hypermedia cụ thể.
- `application/hal+json`: JSON tuân theo cấu trúc HAL.
- `application/problem+json`: JSON mô tả lỗi theo Problem Details.

Client có thể gửi `Accept: application/hal+json` để thể hiện mong muốn nhận HAL JSON. Server phản hồi với `Content-Type` phù hợp khi hỗ trợ định dạng đó. Đây là content negotiation. Header `Accept` mô tả định dạng client muốn nhận; `Content-Type` mô tả định dạng của nội dung response hoặc request body.

Với Spring Boot, dependency `spring-boot-starter-hateoas` cung cấp tích hợp Spring HATEOAS và cấu hình hỗ trợ hypermedia cho Spring MVC. Khi controller trả các kiểu model HATEOAS, message converter phù hợp sẽ chuyển chúng thành representation theo media type được chọn. Cấu hình ứng dụng và request của client quyết định định dạng thực tế; không nên giả định mọi client đều tự động nhận HAL nếu không có thỏa thuận về media type.

## Chọn representation phù hợp

Một API có thể cung cấp representation khác nhau cho các use case khác nhau mà vẫn tham chiếu cùng tài nguyên. Khi thiết kế, hãy cân nhắc:

- **Mục đích sử dụng:** danh sách cần trường tóm tắt; trang chi tiết có thể cần thêm nội dung.
- **Quyền truy cập:** chỉ đưa dữ liệu người gọi được phép xem. Việc ẩn một trường trong representation không thay thế kiểm tra quyền ở server.
- **Tính ổn định của hợp đồng:** tránh để thay đổi cấu trúc bảng hoặc entity tự động làm thay đổi JSON công khai.
- **Kích thước và độ trễ:** chỉ nhúng dữ liệu thực sự cần thiết; dùng phân trang cho collection lớn.
- **Khả năng điều hướng:** cung cấp các relation ổn định để client khám phá tài nguyên liên quan và thao tác khả dụng.
- **Media type:** chọn định dạng mà client có thể diễn giải và công bố rõ trong hợp đồng API.

Nếu cần một representation tóm tắt và một representation chi tiết, có thể tạo hai DTO hoặc hai assembler tương ứng. Tránh dùng một DTO khổng lồ với nhiều trường nullable chỉ để phục vụ mọi màn hình, vì client khó biết trường nào luôn có mặt và server khó duy trì hợp đồng.

## Khả năng tiến hóa của representation

Representation là một phần của hợp đồng API. Thêm một trường tùy chọn thường dễ tương thích hơn việc đổi tên hoặc đổi kiểu một trường hiện có, nhưng tác động còn phụ thuộc cách client giải mã dữ liệu. Đổi relation, thay đổi media type hoặc thay link bằng dữ liệu nhúng cũng có thể ảnh hưởng đến hành vi client.

Để API tiến hóa có kiểm soát:

1. Giữ ý nghĩa của URI và relation đã công bố ổn định.
2. Chỉ công bố trường dữ liệu cần thiết và xác định rõ trường bắt buộc hay tùy chọn.
3. Dùng DTO để tách hợp đồng HTTP khỏi cấu trúc persistence.
4. Kiểm tra representation thực tế bằng integration test, bao gồm dữ liệu, media type và các link quan trọng.
5. Khi thay đổi không tương thích, lập kế hoạch versioning hoặc giai đoạn chuyển tiếp để client có thời gian thích nghi.

Trong Spring HATEOAS, assembler là nơi phù hợp để tập trung việc ánh xạ domain object sang representation và gắn link. Khi cấu trúc nội bộ thay đổi, có thể điều chỉnh assembler hoặc DTO để giữ hợp đồng bên ngoài ổn định. Khi nhu cầu client thay đổi, có thể thêm một representation hoặc relation mới mà không phải phơi bày cách lưu trữ bên trong.

## Tóm tắt cách tư duy

Khi thiết kế một endpoint, trước hết xác định tài nguyên mà URI nhận diện. Tiếp theo chọn dữ liệu nào cần xuất hiện trong representation cho use case đó, chuyển dữ liệu từ domain object sang DTO, rồi dùng Spring HATEOAS model và assembler để bổ sung link. Cuối cùng xác định media type, cách biểu diễn collection hoặc embedded resource, và kiểm thử response như một hợp đồng HTTP.

Một representation tốt giúp client hiểu tài nguyên hiện tại, biết cách tìm tài nguyên liên quan và khám phá các tương tác được server công bố. Nó đồng thời bảo vệ ứng dụng khỏi việc để cấu trúc nội bộ của domain hoặc database quyết định trực tiếp hợp đồng API.
