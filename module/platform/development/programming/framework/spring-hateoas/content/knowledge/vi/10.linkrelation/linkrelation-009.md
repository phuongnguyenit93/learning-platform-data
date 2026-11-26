# Relation của item

Khi Spring HATEOAS biểu diễn một collection, client cần biết tên relation dùng cho cả tập hợp và cho một tài nguyên đơn lẻ. Hai khái niệm này có liên quan nhưng khác nhau. `itemRelation` đặt tên quan hệ của một item; `collectionRelation` đặt tên quan hệ của collection chứa các item đó. Spring HATEOAS cho phép khai báo hai tên này bằng annotation `@Relation` trên kiểu resource.

Ví dụ, một đơn hàng là item `order`, còn tập hợp các đơn hàng là `orders`. Khi API trả một collection HAL, khóa dưới `_embedded` thường là `orders`; các phần tử trong mảng là từng representation đơn hàng. Nếu một representation đơn hàng được nhúng như tài nguyên đơn lẻ ở nơi khác, relation của item là `order`. Việc đặt tên rõ ràng giúp client hiểu loại tài nguyên mà nó đang nhận.

## Item relation và collection relation

Relation mô tả ý nghĩa của tài nguyên hoặc liên kết trong ngữ cảnh hypermedia. Đối với một kiểu resource có thể xuất hiện riêng lẻ hoặc trong collection, nên xác định cả tên item và tên collection:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `itemRelation` | Relation dùng để nhận diện một resource đơn lẻ thuộc kiểu đó. | `order` |
| `collectionRelation` | Relation dùng để nhận diện collection của các resource cùng kiểu. | `orders` |

Với ví dụ đơn hàng, `order` mô tả một đơn hàng cụ thể; `orders` mô tả tập hợp đơn hàng. Tên relation thường là token ngắn, ổn định và có ý nghĩa nghiệp vụ. Không nên để client phải suy ra tên từ tên class Java hoặc cách pluralize một từ tiếng Anh.

Hai relation này cũng khác với relation của một `Link`. `withRel("self")` hoặc `withRel("orders")` tạo một link trong `_links`. `@Relation` cung cấp tên cho representation được nhúng trong hypermedia. Annotation không tự thêm link vào model và cũng không thay thế `withRel(...)`.

## Khai báo `@Relation`

Spring HATEOAS cung cấp annotation `org.springframework.hateoas.server.core.Relation`. Có thể khai báo cả item relation và collection relation trên resource model:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal totalAmount;

    public OrderModel(UUID id, String status, BigDecimal totalAmount) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

`OrderModel` là representation dành cho API. Nó kế thừa `RepresentationModel` để có thể mang link; các trường dữ liệu được công bố qua getter. `@Relation` khai báo hai tên relation cho kiểu model này. Nó không ảnh hưởng đến tên class, tên endpoint hoặc cấu trúc bảng trong database.

Nếu ứng dụng dùng DTO được bọc bằng `EntityModel`, có thể khai báo `@Relation` trên kiểu nội dung mà relation provider dùng để xác định resource. Dù chọn custom `RepresentationModel` hay `EntityModel<DTO>`, hãy bảo đảm annotation được đặt trên kiểu resource được dùng khi tạo embedded representation.

## Relation được dùng trong HAL

HAL biểu diễn tài nguyên nhúng trong `_embedded`. Khi một collection đơn hàng được trả về, relation của collection xác định khóa chứa mảng item:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
        "status": "PENDING",
        "totalAmount": 125000,
        "_links": {
          "self": {
            "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders"
    }
  }
}
```

Ở đây, `orders` là relation của collection và là khóa trong `_embedded`. Mỗi phần tử là một representation `OrderModel`; bản thân phần tử có thể có self link để client truy cập riêng. HAL không thêm một khóa `order` quanh từng phần tử của mảng. `itemRelation` vẫn quan trọng khi relation provider cần tên của một resource đơn lẻ, còn `collectionRelation` đặt tên cho collection.

Phân biệt `_embedded` và `_links`:

- `_embedded.orders` chứa representation của các đơn hàng được nhúng.
- `_links.self` trỏ đến chính collection đơn hàng.
- `_links` bên trong mỗi item có thể chứa `self`, `customer`, `invoice` hoặc các relation khác của đơn hàng.

Nếu API chỉ muốn cung cấp đường dẫn đến collection mà không nhúng nội dung, hãy thêm link bằng `withRel("orders")`. Khi client theo link đó, endpoint collection mới trả `_embedded.orders`.

## Tạo collection với CollectionModel

Assembler chuyển domain entity thành `OrderModel` và tạo self link cho từng item:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
                order.getId(),
                order.getStatus().name(),
                order.getTotalAmount());

        model.add(linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());

        return model;
    }
}
```

Controller tạo collection bằng `CollectionModel` và thêm self link cho tập hợp:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<OrderModel> all() {
        List<OrderModel> orders = service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    OrderModel one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }
}
```

Khi Spring HATEOAS serialize `CollectionModel<OrderModel>` thành HAL, relation provider xác định tên collection dựa trên kiểu item. `@Relation(collectionRelation = "orders")` bảo đảm collection có tên rõ ràng; item model vẫn mang các link riêng được assembler thêm vào.

## Relation provider và tên mặc định

Spring HATEOAS dùng `LinkRelationProvider` để xác định relation của item và collection. Provider có thể đọc metadata `@Relation` hoặc áp dụng quy tắc mặc định cho kiểu Java. Nếu không khai báo annotation, tên được suy ra từ kiểu resource và quy tắc của provider; điều này tiện cho ví dụ đơn giản nhưng có thể tạo tên không phù hợp với hợp đồng API.

Với API được client sử dụng lâu dài, nên khai báo relation rõ ràng bằng `@Relation`. Nhờ vậy, đổi tên class `OrderModel` thành `PurchaseResource` không nhất thiết làm thay đổi relation công khai `order` và `orders`.

Có thể kiểm tra relation mà provider trả về trong unit test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;

@SpringBootTest
class OrderRelationTest {

    @Autowired
    LinkRelationProvider relationProvider;

    @Test
    void declaresSingularAndCollectionRelations() {
        assertThat(relationProvider.getItemResourceRelFor(OrderModel.class))
                .isEqualTo(LinkRelation.of("order"));
        assertThat(relationProvider.getCollectionResourceRelFor(OrderModel.class))
                .isEqualTo(LinkRelation.of("orders"));
    }
}
```

Kiểm thử này xác nhận metadata relation được resolve theo annotation. Nếu ứng dụng tự cấu hình provider, hãy kiểm tra provider thực tế được Spring inject, vì quy tắc mặc định hoặc provider tùy chỉnh có thể làm thay đổi tên được trả về.

## Phân biệt item relation với link relation

Một item trong collection cũng có thể mang các link. Relation của embedded item và relation của link là hai lớp thông tin khác nhau:

| Thành phần | Vị trí thường gặp trong HAL | Mục đích |
| --- | --- | --- |
| Item relation | Tên relation do relation provider xác định cho một resource đơn lẻ. | Nhận diện loại embedded resource. |
| Collection relation | Khóa của collection trong `_embedded`. | Nhận diện tập hợp các item cùng kiểu. |
| Link relation | Khóa trong `_links`, chẳng hạn `self`, `next`, `customer`. | Mô tả quan hệ điều hướng đến URI đích. |

Ví dụ, `orders` trong `_embedded.orders` xác định collection đơn hàng; `self` trong `_links.self` xác định URI của collection hoặc item hiện tại; `customer` trong `_links.customer` dẫn đến khách hàng liên quan. Không nên dùng `itemRelation` để tạo link `self` hoặc thay cho một relation điều hướng.

## Đặt tên relation ổn định

Relation là một phần hợp đồng mà client có thể dựa vào để tìm resource. Vì vậy, hãy chọn tên theo ý nghĩa nghiệp vụ và giữ nhất quán giữa các endpoint:

- Dùng danh từ số ít cho item, ví dụ `order`, `product`, `customer`.
- Dùng tên collection rõ ràng, ví dụ `orders`, `products`, `customers`.
- Dùng relation chuẩn IANA khi ngữ nghĩa phù hợp, chẳng hạn `self`, `next`, `prev` hoặc `collection` cho link.
- Với quan hệ riêng của domain, chọn token hoặc URI relation có ý nghĩa và ghi nhận trong hợp đồng API.
- Không đổi relation chỉ vì đổi tên class, package hoặc cấu trúc lưu trữ.

Không nên suy đoán relation từ tên bảng database. Resource API có thể tổng hợp nhiều entity, và một entity có thể được biểu diễn theo nhiều góc nhìn. Tên relation nên mô tả resource mà client nhìn thấy.

## Kiểm thử relation trong response HAL

Kiểm thử HTTP xác nhận collection được serialize dưới đúng relation và từng item có self link:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void collectionUsesConfiguredRelation() throws Exception {
        mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._embedded.orders").isArray())
                .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Fixture cần có ít nhất một đơn hàng nếu test truy cập phần tử `[0]`. Với collection rỗng, hãy kiểm tra response theo quy tắc HAL của ứng dụng mà không giả định phần tử đầu tiên tồn tại. Kết hợp unit test cho `LinkRelationProvider` với MockMvc test giúp bảo vệ cả tên relation đã cấu hình lẫn JSON mà client thực sự nhận.

Các lỗi thường gặp:

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ khai báo `collectionRelation` | Tên collection rõ nhưng relation item có thể vẫn theo mặc định. | Khai báo cả `itemRelation` và `collectionRelation` khi cần hợp đồng rõ ràng. |
| Nhầm `itemRelation` với `withRel` | Mong đợi annotation tự thêm link nhưng response không có link đó. | Dùng assembler và `withRel` để tạo link điều hướng. |
| Đổi tên class làm đổi relation mặc định | Client phụ thuộc vào tên suy ra từ implementation. | Khai báo relation tường minh bằng `@Relation`. |
| Dùng tên item cho khóa collection | Client khó phân biệt một item và tập hợp item. | Dùng số ít cho item, số nhiều hoặc tên tập hợp cho collection. |
| Kiểm thử chỉ dựa vào Java annotation | JSON HAL có thể dùng provider hoặc cấu hình khác. | Kiểm thử cả provider và response HTTP thực tế. |

## Nguyên tắc thiết kế

- Xác định riêng relation của item và relation của collection.
- Dùng `@Relation(itemRelation = "...", collectionRelation = "...")` trên kiểu resource phù hợp.
- Dùng `CollectionModel` để biểu diễn tập hợp; thêm link điều hướng riêng bằng `Link` API.
- Xem `itemRelation` và `collectionRelation` là metadata tên resource; không nhầm với `rel` của link trong `_links`.
- Giữ relation ổn định khi đổi tên class hoặc cấu trúc nội bộ.
- Kiểm thử relation provider và JSON HAL mà client nhận được.

Khi item relation và collection relation được định nghĩa rõ, representation của một resource và tập hợp resource có thể được nhận diện nhất quán. Client dựa vào tên relation để diễn giải nội dung hypermedia, còn ứng dụng vẫn có thể thay đổi class và cấu trúc nội bộ mà không làm đổi hợp đồng công khai.
