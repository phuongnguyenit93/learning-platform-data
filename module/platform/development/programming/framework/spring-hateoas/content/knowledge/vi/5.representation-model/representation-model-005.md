# Model generic

Spring HATEOAS dùng generic type trong các representation model để giữ an toàn kiểu khi ứng dụng thêm liên kết hypermedia và chuyển đổi tài nguyên. Điểm cần hiểu rõ là tham số generic của `RepresentationModel<T>` biểu thị kiểu model cụ thể, còn tham số generic của `EntityModel<T>` biểu thị kiểu nội dung được bọc. Hai ý nghĩa này khác nhau, dù cùng được viết bằng ký hiệu `T`.

Bài học này giải thích cấu trúc generic tự tham chiếu của `RepresentationModel`, cách khai báo model riêng, cách phân biệt generic của `EntityModel`, `CollectionModel` và `PagedModel`, cũng như cách dùng generic trong assembler và phương thức tiện ích. Các ví dụ dùng tài nguyên đơn hàng để minh họa cách compiler giữ đúng kiểu trong quá trình tạo representation.

## 1. Vì sao Spring HATEOAS dùng generic?

Một representation thường gồm dữ liệu công khai và các liên kết. Ví dụ, biểu diễn đơn hàng có thể chứa mã đơn, trạng thái, tổng tiền cùng các link `self` và `cancel`.

Spring HATEOAS cung cấp nhiều lớp model để biểu diễn những hình dạng tài nguyên khác nhau. Các lớp này có API chung để thêm, đọc và xóa link. Khi thêm link vào model, ứng dụng thường muốn tiếp tục làm việc với đúng kiểu model ban đầu.

Xét một model tùy chỉnh:

~~~java
public class OrderModel {
    private UUID id;
    private String status;

    public OrderModel(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Nếu model kế thừa một lớp cơ sở không giữ thông tin kiểu con, các phương thức fluent của lớp cơ sở thường chỉ có thể trả về kiểu cơ sở. Khi đó, chuỗi lời gọi dễ mất kiểu cụ thể hoặc cần ép kiểu.

Spring HATEOAS giải quyết vấn đề này bằng generic tự tham chiếu. Model khai báo kiểu của chính nó khi kế thừa `RepresentationModel`. Nhờ vậy, phương thức thêm link có thể trả về đúng kiểu model con và compiler kiểm tra được kiểu ở thời điểm biên dịch.

## 2. Cấu trúc generic tự tham chiếu của RepresentationModel

Khai báo khái quát của `RepresentationModel` có dạng:

~~~java
public class RepresentationModel<T extends RepresentationModel<T>> {
    // Các phương thức quản lý Link
}
~~~

Phần `T extends RepresentationModel<T>` là một ràng buộc generic tự tham chiếu, thường được gọi là *F-bounded polymorphism*. Nó yêu cầu kiểu truyền vào `T` phải là một kiểu `RepresentationModel` có tham số generic chính là kiểu đó.

Với một model cụ thể, khai báo thường là:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {
    // Các trường và phương thức của đơn hàng
}
~~~

Ở đây:

- `OrderModel` là kiểu model cụ thể.
- `RepresentationModel<OrderModel>` là lớp cơ sở của model đó.
- Tham số `OrderModel` nói rằng các thao tác fluent của lớp cơ sở sẽ làm việc với chính `OrderModel`.

Có thể hình dung mối quan hệ kiểu như sau:

~~~text
OrderModel
    |
    +-- extends RepresentationModel<OrderModel>
                                  |
                                  +-- T = OrderModel
~~~

Tham số generic không phải kiểu dữ liệu nghiệp vụ như `OrderDto`, `Order` hoặc `String`. Nó mô tả kiểu model kế thừa `RepresentationModel`.

### 2.1. Thêm liên kết và giữ kiểu model

Ví dụ model đơn hàng:

~~~java
import org.springframework.hateoas.RepresentationModel;

import java.math.BigDecimal;
import java.util.UUID;

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
~~~

Khi thêm link, kiểu trả về vẫn là `OrderModel`:

~~~java
OrderModel model = new OrderModel(orderId, "PROCESSING", total);

OrderModel linkedModel = model.add(selfLink);
~~~

Vì `add(...)` trả về tham số self type, biến `linkedModel` có kiểu `OrderModel`. Không cần ép kiểu từ `RepresentationModel` về `OrderModel`.

Có thể tiếp tục gọi các phương thức của model con sau khi thêm link:

~~~java
model.add(selfLink)
     .add(ordersLink)
     .getTotal();
~~~

Chuỗi lời gọi này minh họa lợi ích của generic tự tham chiếu: các thao tác quản lý link vẫn giữ kiểu model cụ thể, nên những phương thức như `getTotal()` tiếp tục được compiler nhận diện.

`RepresentationModel` còn cung cấp các thao tác để đọc và quản lý link, chẳng hạn `getLinks()`, `getLink(rel)`, `getRequiredLink(rel)`, `hasLink(rel)` và `removeLinks()`. Các thao tác này làm việc với tập link của model; chúng không thay thế dữ liệu nghiệp vụ của tài nguyên.

### 2.2. Khai báo sai tham số generic

Một lỗi thường gặp là dùng kiểu nội dung làm tham số cho `RepresentationModel`:

~~~java
// Không hợp lệ nếu OrderDto không kế thừa RepresentationModel<OrderDto>
public class OrderModel extends RepresentationModel<OrderDto> {
}
~~~

Compiler từ chối khai báo này vì `OrderDto` không thỏa ràng buộc `T extends RepresentationModel<T>`. Tham số generic phải là kiểu model tự tham chiếu phù hợp, ví dụ `OrderModel`.

Nếu mục tiêu là bọc một DTO làm nội dung, hãy cân nhắc `EntityModel<OrderDto>`. Đây là kiểu model được thiết kế cho trường hợp đó.

## 3. Phân biệt generic của các model Spring HATEOAS

Các lớp model có thể cùng kế thừa `RepresentationModel` nhưng tham số generic của từng lớp có ý nghĩa riêng. Cần đọc kiểu khai báo của lớp đang dùng, không suy luận rằng mọi `T` đều là kiểu DTO.

| Kiểu model | Ý nghĩa của tham số generic | Ví dụ |
|---|---|---|
| `RepresentationModel<T>` | Kiểu model tự tham chiếu | `OrderModel extends RepresentationModel<OrderModel>` |
| `EntityModel<T>` | Kiểu nội dung được bọc | `EntityModel<OrderDto>` |
| `CollectionModel<T>` | Kiểu của mỗi phần tử trong tập hợp | `CollectionModel<EntityModel<OrderDto>>` |
| `PagedModel<T>` | Kiểu của mỗi phần tử trong trang | `PagedModel<EntityModel<OrderDto>>` |

Sự khác biệt này quan trọng khi đọc chữ ký phương thức hoặc thiết kế kiểu trả về cho controller.

### 3.1. EntityModel<T>: T là kiểu nội dung

`EntityModel<T>` dùng để bọc một đối tượng nội dung và gắn link cho tài nguyên đơn. Ví dụ:

~~~java
public record OrderDto(
    UUID id,
    String status,
    BigDecimal total
) {}

OrderDto dto = new OrderDto(orderId, "PROCESSING", total);

EntityModel<OrderDto> model = EntityModel.of(dto);
model.add(selfLink);
~~~

Trong `EntityModel<OrderDto>`, `OrderDto` là kiểu của nội dung được bọc. `EntityModel` tự triển khai phần self type của lớp cơ sở, vì vậy ứng dụng không cần khai báo `EntityModel<EntityModel<OrderDto>>`.

Có thể lấy nội dung bằng `getContent()`:

~~~java
OrderDto content = model.getContent();
~~~

Đây là điểm phân biệt quan trọng: `RepresentationModel<T>` dùng `T` để mô tả kiểu model con; `EntityModel<T>` dùng `T` để mô tả nội dung.

### 3.2. CollectionModel<T>: T là kiểu phần tử

`CollectionModel<T>` biểu diễn một tập hợp. Mỗi phần tử có thể là DTO hoặc một model có link, tùy cách API muốn công bố nội dung.

Ví dụ tập hợp các tài nguyên đơn hàng đã được bọc:

~~~java
List<EntityModel<OrderDto>> orders = List.of(
    EntityModel.of(firstOrder),
    EntityModel.of(secondOrder)
);

CollectionModel<EntityModel<OrderDto>> collection =
    CollectionModel.of(orders);

collection.add(ordersLink);
~~~

Ở đây, kiểu phần tử là `EntityModel<OrderDto>`. Tập hợp có thể có link ở cấp collection, trong khi từng phần tử có các link riêng.

Một cách khác là dùng `CollectionModel<OrderDto>` nếu muốn tập hợp chứa trực tiếp DTO. Lựa chọn phụ thuộc vào cấu trúc hypermedia mong muốn và cách serializer biểu diễn các phần tử. Với HAL, nếu mỗi phần tử cần relation và link riêng, bọc từng phần tử bằng `EntityModel` thường làm ý định rõ ràng hơn.

### 3.3. PagedModel<T>: T là kiểu phần tử của trang

`PagedModel<T>` mở rộng mô hình tập hợp để biểu diễn metadata phân trang. Tham số `T` vẫn là kiểu phần tử, không phải kiểu metadata.

Ví dụ về mặt cấu trúc:

~~~java
List<EntityModel<OrderDto>> items = loadPageItems();

PagedModel.PageMetadata metadata =
    new PagedModel.PageMetadata(20, 0, 42, 3);

PagedModel<EntityModel<OrderDto>> page =
    PagedModel.of(items, metadata);
~~~

Metadata ví dụ mô tả kích thước trang, chỉ số trang, tổng số phần tử và tổng số trang. Ứng dụng cần tạo các link điều hướng như `next` hoặc `prev` dựa trên kết quả truy vấn thực tế. Kiểu generic chỉ đảm bảo mỗi phần tử trong trang có kiểu nhất quán; nó không tự tạo logic phân trang hoặc link điều hướng.

## 4. Generic trong RepresentationModelAssembler

Generic cũng xuất hiện trong `RepresentationModelAssembler<S, D>`. Interface này chuyển một đối tượng nguồn thành representation model.

Hai tham số có ý nghĩa:

- `S` là kiểu đối tượng nguồn, thường là entity hoặc domain object.
- `D` là kiểu representation được trả về, phải là một kiểu `RepresentationModel`.

Ví dụ dùng DTO được bọc bằng `EntityModel`:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        var dto = new OrderDto(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(
            dto,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );
    }
}
~~~

Trong khai báo:

`RepresentationModelAssembler<Order, EntityModel<OrderDto>>`

- `Order` là đầu vào mà assembler nhận.
- `EntityModel<OrderDto>` là kiểu đầu ra.
- `toModel(Order order)` trả về đúng kiểu đã khai báo.

Khi controller gọi assembler, compiler biết kiểu kết quả:

~~~java
@GetMapping("/{id}")
public EntityModel<OrderDto> one(@PathVariable UUID id) {
    Order order = service.findById(id);
    return assembler.toModel(order);
}
~~~

Nếu dùng model riêng `OrderModel`, kiểu assembler tương ứng là:

~~~java
public class OrderAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        var model = new OrderModel(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        model.add(
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );

        return model;
    }
}
~~~

Việc chọn `EntityModel<OrderDto>` hay `OrderModel` phụ thuộc cách tổ chức representation. `EntityModel` phù hợp khi cần bọc một DTO; model riêng hữu ích khi biểu diễn có cấu trúc chuyên biệt, hành vi hoặc trường dữ liệu được đóng gói trong một kiểu rõ ràng.

## 5. Tạo model generic có kiểu nội dung riêng

Trong một số ứng dụng, nhiều tài nguyên cần cùng một cấu trúc wrapper nhưng nội dung khác kiểu. Có thể tạo lớp generic riêng. Khi đó, lớp wrapper dùng một tham số cho nội dung và vẫn truyền chính kiểu wrapper làm self type cho `RepresentationModel`.

~~~java
import org.springframework.hateoas.RepresentationModel;

public class ResourceModel<C>
        extends RepresentationModel<ResourceModel<C>> {

    private final C content;

    public ResourceModel(C content) {
        this.content = content;
    }

    public C getContent() {
        return content;
    }
}
~~~

Có thể tạo wrapper cho nhiều loại nội dung:

~~~java
ResourceModel<OrderDto> orderResource =
    new ResourceModel<>(orderDto);

ResourceModel<CustomerDto> customerResource =
    new ResourceModel<>(customerDto);
~~~

Trong `ResourceModel<C>`:

- `C` là kiểu nội dung.
- `ResourceModel<C>` là kiểu model cụ thể.
- `RepresentationModel<ResourceModel<C>>` giữ self type cho các phương thức quản lý link.

Có thể thêm link và vẫn giữ kiểu wrapper:

~~~java
ResourceModel<OrderDto> linkedOrder =
    orderResource.add(orderLink);
~~~

Kiểu wrapper generic hữu ích khi nhiều tài nguyên thực sự có cùng cấu trúc biểu diễn. Tuy nhiên, không nên tạo wrapper chung chỉ để giảm số lớp nếu mỗi tài nguyên có hợp đồng, quan hệ hoặc quy tắc hiển thị khác nhau. Model riêng có tên nghiệp vụ thường giúp API dễ đọc và dễ tiến hóa hơn.

## 6. Dùng wildcard khi làm việc với nhiều kiểu model

Khi một phương thức chỉ cần đọc thông tin chung của nhiều model, có thể nhận `RepresentationModel<?>`. Dấu `?` nói rằng kiểu self cụ thể không cần biết tại vị trí đó.

~~~java
import org.springframework.hateoas.RepresentationModel;

public void printLinks(RepresentationModel<?> model) {
    model.getLinks().forEach(System.out::println);
}
~~~

Phương thức có thể nhận `OrderModel`, `EntityModel<OrderDto>` hoặc một representation model khác. Nó chỉ thao tác trên API chung của lớp cơ sở.

Nếu phương thức cần thêm link và trả lại đúng kiểu model đầu vào, hãy dùng generic method để giữ self type:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;

public static <M extends RepresentationModel<M>> M addLink(
        M model, Link link) {
    return model.add(link);
}
~~~

Cách gọi:

~~~java
OrderModel orderModel = new OrderModel(orderId, "PROCESSING", total);

OrderModel result = addLink(orderModel, selfLink);
~~~

Kiểu `M` được suy luận từ đối số truyền vào, vì vậy phương thức trả lại đúng kiểu model cụ thể. Đây là cách viết helper an toàn kiểu hơn so với nhận `RepresentationModel<?>` rồi ép kiểu kết quả.

### 6.1. Wildcard và tính bất biến của generic

Generic trong Java có tính bất biến. Ví dụ, `EntityModel<OrderDto>` không phải subtype của `EntityModel<Object>`, dù `OrderDto` có thể là subtype của `Object`.

Tương tự, không thể gán một `CollectionModel<EntityModel<OrderDto>>` trực tiếp vào biến có kiểu `CollectionModel<RepresentationModel<?>>`. Hai kiểu tham số khác nhau và generic không tự chuyển thành quan hệ kế thừa.

Nếu cần chấp nhận nhiều loại phần tử model, hãy cân nhắc wildcard có giới hạn phù hợp, ví dụ:

~~~java
CollectionModel<? extends RepresentationModel<?>> resources;
~~~

Kiểu wildcard cho biết collection chứa một kiểu cụ thể nào đó kế thừa `RepresentationModel<?>`, nhưng người gọi không cần biết chính xác kiểu đó. Vì không biết kiểu phần tử cụ thể, khả năng thêm phần tử mới vào collection bị giới hạn; wildcard thường thích hợp cho việc đọc hoặc truyền dữ liệu hơn là sửa đổi collection.

## 7. Generic bảo vệ kiểu ở thời điểm biên dịch, không quyết định JSON

Generic giúp compiler kiểm tra cách chương trình sử dụng model. Chúng không tự quyết định tên trường, cấu trúc JSON hoặc relation HAL.

Ví dụ:

~~~java
EntityModel<OrderDto> model = EntityModel.of(orderDto);
~~~

Compiler đảm bảo `getContent()` trả về `OrderDto` trong mã nguồn có kiểu cụ thể. Khi tuần tự hóa, Jackson và cấu hình hypermedia của Spring HATEOAS đọc đối tượng nội dung cùng các link để tạo response theo media type đã chọn.

Các điểm sau cần được thiết kế riêng:

- Tên trường JSON phụ thuộc thuộc tính/getter, annotation Jackson và cấu hình serializer.
- Quan hệ link như `self`, `orders` hoặc `cancel` đến từ các `Link` đã thêm vào model.
- Tên relation trong phần tử nhúng của HAL có thể cần cấu hình bằng `@Relation` hoặc relation provider.
- Media type quyết định định dạng hypermedia được trả về, ví dụ HAL JSON.

Do Java dùng type erasure, tham số generic không tồn tại như một đối tượng kiểu riêng trong mọi thao tác runtime. Vì vậy, không nên dựa vào `T` để mong serializer tự suy ra quy tắc JSON. Hãy khai báo rõ DTO, getter, annotation và cấu hình media type theo hợp đồng API.

## 8. Kiểm thử kiểu model và biểu diễn

Generic được compiler kiểm tra trong lúc biên dịch, nhưng kiểm thử vẫn cần xác nhận response thực tế có nội dung và link đúng. Với controller Spring MVC, có thể dùng MockMvc; với WebFlux, dùng WebTestClient.

Ví dụ kiểm tra response HAL:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Có thể kiểm tra riêng assembler bằng unit test để xác nhận:

1. Đối tượng nguồn `Order` được chuyển thành đúng kiểu model.
2. Nội dung DTO giữ đúng các trường công khai.
3. Link `self` được tạo cho tài nguyên.
4. Link hành động chỉ xuất hiện khi điều kiện nghiệp vụ cho phép.
5. Collection assembler trả về đúng kiểu phần tử và link ở cấp tập hợp.

Nếu model dùng `EntityModel<OrderDto>`, kiểm tra `getContent()` chứa DTO dự kiến. Nếu dùng `OrderModel`, kiểm tra các getter của model con và tập link kế thừa. Cách kiểm tra này xác nhận cả cấu trúc kiểu trong ứng dụng lẫn hợp đồng JSON mà client nhìn thấy.

## 9. Lỗi thường gặp khi khai báo generic model

| Lỗi | Vì sao sai hoặc gây khó khăn | Cách xử lý |
|---|---|---|
| Dùng `RepresentationModel<OrderDto>` | `OrderDto` không thỏa ràng buộc self type nếu không kế thừa `RepresentationModel<OrderDto>` | Dùng `RepresentationModel<OrderModel>` cho model con |
| Nghĩ `T` trong `RepresentationModel<T>` là payload | Tham số này mô tả kiểu model tự tham chiếu | Dùng `EntityModel<OrderDto>` khi cần bọc DTO |
| Dùng raw type như `EntityModel` | Mất kiểm tra kiểu nội dung và có thể phát sinh ép kiểu không an toàn | Khai báo `EntityModel<OrderDto>` |
| Nhầm generic assembler | Đảo kiểu nguồn và kiểu representation | Dùng `RepresentationModelAssembler<Order, EntityModel<OrderDto>>` |
| Gán các collection generic khác tham số | Generic Java là bất biến | Dùng wildcard có giới hạn khi cần đọc đa hình |
| Tạo wrapper generic cho mọi tài nguyên | Có thể che khuất ý nghĩa nghiệp vụ và làm hợp đồng khó hiểu | Chỉ dùng wrapper chung khi cấu trúc biểu diễn thực sự giống nhau |
| Mong generic quyết định cấu trúc HAL | Generic là kiểm tra kiểu compile time | Thiết kế DTO, Link, relation và media type rõ ràng |

## 10. Quy trình chọn kiểu generic

Khi thiết kế một representation bằng Spring HATEOAS, có thể đi theo các bước sau:

1. Xác định response đại diện cho một tài nguyên, một tập hợp hay một trang.
2. Nếu chỉ cần bọc DTO, chọn `EntityModel<Dto>`.
3. Nếu cần lớp biểu diễn riêng, tạo `MyModel extends RepresentationModel<MyModel>`.
4. Nếu cần tập hợp, chọn `CollectionModel<ElementModel>`; nếu có metadata phân trang, cân nhắc `PagedModel<ElementModel>`.
5. Khi viết assembler, đặt kiểu nguồn ở tham số generic thứ nhất và kiểu representation ở tham số thứ hai.
6. Dùng `RepresentationModel<?>` cho thao tác chung chỉ cần đọc model; dùng generic method có self bound khi cần trả lại đúng kiểu cụ thể.
7. Kiểm tra response JSON/HAL để xác nhận nội dung và các relation được công bố đúng hợp đồng.

Hiểu đúng generic giúp thiết kế model rõ ràng, giảm ép kiểu và để compiler phát hiện sớm các lỗi không tương thích. Trong Spring HATEOAS, quy tắc dễ nhớ nhất là: `RepresentationModel<T>` dùng `T` cho kiểu model tự tham chiếu; `EntityModel<T>` dùng `T` cho kiểu nội dung; `CollectionModel<T>` và `PagedModel<T>` dùng `T` cho kiểu phần tử.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RepresentationModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)

