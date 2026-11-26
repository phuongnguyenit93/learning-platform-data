# Item embedded

Trong một biểu diễn HAL, item embedded là một tài nguyên liên quan được đưa trực tiếp vào phần `_embedded` của biểu diễn cha. Ví dụ, khi client đọc một đơn hàng, API có thể nhúng bản tóm tắt khách hàng đã đặt đơn ngay trong response. Client có thể hiển thị tên khách hàng mà chưa cần gửi thêm request để đọc tài nguyên khách hàng.

Item embedded hữu ích khi một tài nguyên thường được tiêu thụ cùng một tài nguyên liên quan, dữ liệu nhúng có kích thước hợp lý và API muốn giảm số lần round-trip. Tuy vậy, embedded item vẫn có ngữ nghĩa quan hệ riêng. Trong HAL, khóa dưới `_embedded` là link relation; nếu client cần truy cập tài nguyên đầy đủ hoặc làm mới dữ liệu, response nên cung cấp link tương ứng trong `_links`.

Spring HATEOAS cung cấp `HalModelBuilder` để tạo biểu diễn HAL có embedded resource. Với một tài nguyên liên quan vừa có URI vừa có bản xem trước, cặp lời gọi `preview(...).forLink(...)` tạo cả link và nội dung nhúng theo cùng relation. Với một đối tượng cần nhúng mà không gắn link điều hướng, có thể dùng `embed(...)`.

Sau bài học, bạn có thể:

- Giải thích item embedded và phân biệt nó với link đến tài nguyên khác.
- Đọc cấu trúc `_embedded` và `_links` trong HAL.
- Dùng `HalModelBuilder` để tạo representation cha có một embedded item.
- Dùng `preview(...).forLink(...)` để công bố link cùng bản xem trước.
- Dùng `embed(..., LinkRelation)` để chỉ định relation của item nhúng.
- Kiểm soát tên relation bằng `@Relation` hoặc `LinkRelationProvider`.
- Nhúng một representation hypermedia có link và embedded resource lồng nhau.
- Cân nhắc payload, tính nhất quán dữ liệu, quyền truy cập và kiểm thử hợp đồng HAL.

## 1. Item embedded là gì?

Giả sử API quản lý đơn hàng có tài nguyên:

- Đơn hàng: `/orders/4711`.
- Khách hàng: `/customers/42`.

Một response chỉ có link đến khách hàng:

~~~json
{
  "id": "4711",
  "status": "AWAITING_PAYMENT",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/4711"
    },
    "customer": {
      "href": "https://api.example.com/customers/42"
    }
  }
}
~~~

Client biết có tài nguyên quan hệ `customer`, nhưng muốn hiển thị tên khách hàng thì phải gửi thêm request đến href đó.

Nếu API nhúng một bản xem trước khách hàng, response có thể là:

~~~json
{
  "id": "4711",
  "status": "AWAITING_PAYMENT",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/4711"
    },
    "customer": {
      "href": "https://api.example.com/customers/42"
    }
  },
  "_embedded": {
    "customer": {
      "id": "42",
      "displayName": "Nguyễn An",
      "tier": "GOLD"
    }
  }
}
~~~

Client có thể dùng dữ liệu trong `_embedded.customer` để hiển thị nhanh. Khi cần thông tin mới nhất hoặc những trường chi tiết hơn, client theo link `_links.customer`.

Một embedded item thường có các đặc điểm:

- Nằm bên trong representation của tài nguyên cha.
- Được đặt dưới một relation có ý nghĩa, chẳng hạn `customer`, `shippingAddress` hoặc `owner`.
- Có thể là DTO đơn giản hoặc một representation hypermedia có link riêng.
- Có thể đi cùng link đến tài nguyên đầy đủ.

### 1.1. Embedded item khác với thuộc tính JSON lồng nhau

Một DTO có thể có thuộc tính:

~~~json
{
  "id": "4711",
  "customer": {
    "id": "42",
    "displayName": "Nguyễn An"
  }
}
~~~

Đây là JSON lồng nhau thông thường. HAL dùng `_embedded` để thể hiện một representation liên quan theo link relation:

~~~json
{
  "id": "4711",
  "_embedded": {
    "customer": {
      "id": "42",
      "displayName": "Nguyễn An"
    }
  }
}
~~~

Sự khác biệt có ý nghĩa đối với client hypermedia. `customer` trong `_embedded` là relation của một tài nguyên nhúng; nó có thể tương ứng với link relation `customer` trong `_links`. Client có thể hiểu dữ liệu nhúng như bản xem trước của tài nguyên đích.

### 1.2. Embedded item và collection embedded

HAL dùng `_embedded` cho cả tài nguyên đơn và collection:

| Trường hợp | Cấu trúc thường gặp |
|---|---|
| Một khách hàng | `_embedded.customer: { ... }` |
| Nhiều dòng hàng | `_embedded.lineItems: [ ... ]` |
| Một địa chỉ giao hàng | `_embedded.shippingAddress: { ... }` |

Relation đơn và relation collection nên được đặt tên rõ ràng. Với một kiểu tài nguyên, Spring HATEOAS có thể lấy tên relation từ `@Relation` hoặc `LinkRelationProvider`.

## 2. Khi nào nên nhúng một item?

Nhúng tài nguyên liên quan có lợi khi dữ liệu đó thường được sử dụng cùng tài nguyên cha. Ví dụ:

- Đơn hàng nhúng bản tóm tắt khách hàng.
- Bài viết nhúng thông tin tác giả.
- Phiếu hỗ trợ nhúng bản tóm tắt người phụ trách.
- Sản phẩm nhúng ảnh đại diện hoặc thông tin danh mục.
- Lịch hẹn nhúng bản tóm tắt địa điểm.

Không nên nhúng toàn bộ tài nguyên liên quan chỉ vì có thể làm được. Hãy cân nhắc:

- **Mức độ sử dụng:** client có thường cần dữ liệu đó ngay khi đọc tài nguyên cha không?
- **Kích thước:** embedded item có làm response tăng quá nhiều không?
- **Tính thay đổi:** dữ liệu nhúng có thay đổi thường xuyên và cần luôn mới không?
- **Quyền truy cập:** người đọc tài nguyên cha có được phép xem các trường nhúng không?
- **Khả năng điều hướng:** client có cần link để truy cập tài nguyên đầy đủ không?

Một cách thiết kế phổ biến là nhúng DTO tóm tắt và cung cấp link đến tài nguyên đầy đủ. DTO tóm tắt nên chỉ chứa các trường cần thiết cho use case của response cha.

## 3. Cấu trúc HAL khi nhúng một item

Trong HAL, `_links` chứa các liên kết và `_embedded` chứa các representation được nhúng. Ví dụ:

~~~json
{
  "id": "4711",
  "status": "AWAITING_PAYMENT",
  "_links": {
    "self": {
      "href": "/orders/4711"
    },
    "customer": {
      "href": "/customers/42"
    }
  },
  "_embedded": {
    "customer": {
      "id": "42",
      "displayName": "Nguyễn An"
    }
  }
}
~~~

Ở đây:

- `self` trỏ đến đơn hàng hiện tại.
- `customer` trong `_links` trỏ đến tài nguyên khách hàng.
- `customer` trong `_embedded` là dữ liệu khách hàng được nhúng.
- Cùng relation `customer` liên kết bản xem trước với tài nguyên đích.

Không phải mọi embedded item đều bắt buộc có link tương ứng. Nếu chỉ muốn đưa một snapshot hoặc một phần dữ liệu vào representation cha, có thể nhúng theo relation mà không thêm link. Tuy nhiên, nếu item đại diện cho một tài nguyên có URI độc lập và client cần điều hướng đến nó, nên cung cấp link rõ ràng.

### 3.1. Một relation có thể xuất hiện ở cả hai phần

Có thể thấy cùng tên relation ở `_links` và `_embedded`:

~~~json
{
  "_links": {
    "customer": {
      "href": "/customers/42"
    }
  },
  "_embedded": {
    "customer": {
      "id": "42",
      "displayName": "Nguyễn An"
    }
  }
}
~~~

Hai phần này bổ sung cho nhau:

- Link cung cấp URI điều hướng.
- Embedded item cung cấp nội dung để client sử dụng ngay.

Client không nên coi embedded data luôn là bản mới nhất. Nếu dữ liệu có thể thay đổi giữa thời điểm response được tạo và thời điểm client dùng nó, client có thể theo link để làm mới.

## 4. Tạo item embedded bằng HalModelBuilder

`HalModelBuilder` là API chuyên biệt của Spring HATEOAS để tạo representation theo cách diễn đạt của HAL. Nó hỗ trợ một payload chính, nhiều embedded document và các mẫu HAL như preview.

Ví dụ, payload chính là đơn hàng:

~~~java
OrderRepresentation order = new OrderRepresentation(
    orderId,
    "AWAITING_PAYMENT",
    total
);
~~~

Bản xem trước khách hàng:

~~~java
CustomerPreview customer = new CustomerPreview(
    customerId,
    "Nguyễn An",
    "GOLD"
);
~~~

Tạo link đến khách hàng:

~~~java
Link customerLink = linkTo(
    methodOn(CustomerController.class).one(customerId)
).withRel("customer");
~~~

Trong ví dụ, `orderId`, `customerId` và `total` là các giá trị lấy từ dữ liệu đơn hàng và quan hệ khách hàng đã được tải.

Sau đó tạo representation HAL:

~~~java
RepresentationModel<?> model = HalModelBuilder
    .halModelOf(order)
    .preview(customer)
    .forLink(customerLink)
    .link(
        linkTo(methodOn(OrderController.class).one(orderId))
            .withSelfRel()
    )
    .build();
~~~

Chuỗi `preview(customer).forLink(customerLink)` có ý nghĩa:

1. `preview(customer)` cung cấp payload được nhúng.
2. `forLink(customerLink)` kết thúc cấu hình preview bằng link đích.
3. Relation của link được dùng làm khóa trong `_embedded`.
4. Link đó cũng được thêm vào `_links` của representation cha.

Kết quả HAL có cấu trúc:

~~~json
{
  "id": "4711",
  "status": "AWAITING_PAYMENT",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "/orders/4711"
    },
    "customer": {
      "href": "/customers/42"
    }
  },
  "_embedded": {
    "customer": {
      "id": "42",
      "displayName": "Nguyễn An",
      "tier": "GOLD"
    }
  }
}
~~~

Các import chính:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

### 4.1. Kích hoạt hỗ trợ HAL

Trong ứng dụng Spring MVC không dùng cấu hình tự động của Spring Boot, có thể kích hoạt HAL bằng `@EnableHypermediaSupport`:

~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
public class HypermediaConfiguration {
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
~~~

Ứng dụng Spring Boot có thể đã được cấu hình hypermedia tự động. Hãy dùng cấu hình hiện có và tránh đăng ký lặp lại converter hoặc module HAL.

`HalModelBuilder` là API dành cho HAL. Nếu endpoint hỗ trợ nhiều media type, hãy cân nhắc cách tạo representation phù hợp với từng định dạng thay vì giả định cấu trúc HAL có thể dùng nguyên vẹn cho mọi media type.

## 5. Tích hợp vào controller

Giả sử API có DTO:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}

public record CustomerPreview(
    UUID id,
    String displayName,
    String tier
) {}
~~~

Controller lấy dữ liệu đơn hàng và bản xem trước khách hàng:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final CustomerQueryService customerQueryService;

    public OrderController(
            OrderService orderService,
            CustomerQueryService customerQueryService) {
        this.orderService = orderService;
        this.customerQueryService = customerQueryService;
    }

    @GetMapping("/{id}")
    public RepresentationModel<?> one(@PathVariable("id") UUID id) {
        Order order = orderService.getRequired(id);
        CustomerPreview customer =
            customerQueryService.getPreview(order.getCustomerId());

        OrderRepresentation content = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        Link self = linkTo(
            methodOn(OrderController.class).one(id)
        ).withSelfRel();

        Link customerLink = linkTo(
            methodOn(CustomerController.class).one(customer.id())
        ).withRel("customer");

        return HalModelBuilder.halModelOf(content)
            .preview(customer)
            .forLink(customerLink)
            .link(self)
            .build();
    }
}
~~~

Ví dụ giả định `OrderService` tải đơn hàng, còn `CustomerQueryService` chỉ trả DTO preview. Không cần tải toàn bộ aggregate khách hàng nếu response chỉ cần tên và hạng thành viên.

Các import bổ sung:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Controller phối hợp việc lấy dữ liệu và dựng representation. Nếu quy tắc tạo preview được dùng ở nhiều endpoint, có thể chuyển phần tạo HAL model sang một assembler hoặc component chuyên trách để tránh lặp.

## 6. Nhúng item không cần link bằng embed

Không phải lúc nào item nhúng cũng có URI riêng hoặc cần điều hướng. Ví dụ, đơn hàng có thể chứa một bản sao địa chỉ giao hàng tại thời điểm mua. Địa chỉ này là snapshot của giao dịch; nó không nhất thiết là tài nguyên độc lập mà client có thể cập nhật.

Dùng `embed(entity, relation)` để thêm payload vào `_embedded` với relation tường minh:

~~~java
ShippingAddressSnapshot address = new ShippingAddressSnapshot(
    "12 Nguyễn Huệ",
    "Quận 1",
    "TP. Hồ Chí Minh"
);

RepresentationModel<?> model = HalModelBuilder
    .halModelOf(order)
    .embed(address, LinkRelation.of("shippingAddress"))
    .link(self)
    .build();
~~~

HAL được tạo có cấu trúc:

~~~json
{
  "id": "4711",
  "_links": {
    "self": {
      "href": "/orders/4711"
    }
  },
  "_embedded": {
    "shippingAddress": {
      "street": "12 Nguyễn Huệ",
      "district": "Quận 1",
      "city": "TP. Hồ Chí Minh"
    }
  }
}
~~~

Ở ví dụ này không có `_links.shippingAddress`, vì snapshot không phải một tài nguyên điều hướng độc lập. Client đọc nó như một phần dữ liệu của đơn hàng.

Các import:

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;
~~~

### 6.1. Chọn relation tường minh

Overload:

~~~java
.embed(address, LinkRelation.of("shippingAddress"))
~~~

cho phép chọn relation mà không phụ thuộc tên class Java. Điều này hữu ích khi:

- Tên class nội bộ không phù hợp với hợp đồng API.
- Một DTO được dùng trong nhiều ngữ cảnh.
- Muốn giữ tên relation ổn định khi refactor class.
- Có nhiều kiểu payload cần được phân biệt rõ.

Nếu relation được dùng ở nhiều nơi, nên định nghĩa thành hằng số:

~~~java
public final class OrderRelations {

    public static final LinkRelation CUSTOMER =
        LinkRelation.of("customer");

    public static final LinkRelation SHIPPING_ADDRESS =
        LinkRelation.of("shippingAddress");

    private OrderRelations() {}
}
~~~

Sau đó dùng `OrderRelations.SHIPPING_ADDRESS` trong builder. Relation là một phần hợp đồng API, nên tránh đổi tên tùy tiện sau khi client đã phụ thuộc.

## 7. Đặt tên relation bằng @Relation

Khi nhúng một object bằng `embed(entity)` mà không truyền relation rõ ràng, Spring HATEOAS cần xác định tên relation từ kiểu object. `LinkRelationProvider` chịu trách nhiệm tra cứu relation. Một cách khai báo phổ biến là dùng `@Relation`.

Ví dụ:

~~~java
@Relation(
    itemRelation = "customer",
    collectionRelation = "customers"
)
public record CustomerPreview(
    UUID id,
    String displayName,
    String tier
) {}
~~~

Các thuộc tính:

- `itemRelation` định nghĩa relation khi nhắc đến một tài nguyên đơn.
- `collectionRelation` định nghĩa relation khi nhắc đến collection.
- `value` là alias của `itemRelation`, vì vậy `value = "customer"` cũng có thể dùng cho item relation.

Sau khi khai báo, có thể dùng:

~~~java
HalModelBuilder.halModelOf(order)
    .embed(customerPreview)
    .link(self)
    .build();
~~~

Spring HATEOAS tra cứu relation của kiểu `CustomerPreview` và dùng nó làm khóa embedded. Nếu cần kiểm soát tuyệt đối tên relation tại vị trí gọi, dùng overload `embed(customerPreview, LinkRelation.of("customer"))`.

Import:

~~~java
import org.springframework.hateoas.server.core.Relation;
~~~

### 7.1. Quy tắc suy ra relation mặc định

Khi không có `@Relation` hoặc custom `LinkRelationProvider`, Spring HATEOAS có thể suy ra relation từ tên class. Quy tắc mặc định dùng tên class viết thường cho item và thêm hậu tố `List` cho collection; nếu thư viện EVO Inflector có trên classpath, nó có thể dùng dạng số nhiều theo thuật toán.

Vì quy tắc mặc định phụ thuộc tên lớp và cấu hình classpath, API công khai nên khai báo relation tường minh cho các kiểu embedded quan trọng. Điều này giúp tên relation không thay đổi chỉ vì refactor tên DTO hoặc thay đổi dependency.

## 8. Nhúng một representation có link riêng

Embedded item không nhất thiết chỉ là một DTO thuần. Nó có thể là một representation hypermedia có link riêng hoặc chứa embedded resource khác.

Ví dụ, tạo representation khách hàng:

~~~java
EntityModel<CustomerPreview> customerModel = EntityModel.of(
    customerPreview,
    linkTo(methodOn(CustomerController.class).one(customerPreview.id()))
        .withSelfRel()
);
~~~

Các import liên quan:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Có thể nhúng representation đó vào model cha với relation tường minh:

~~~java
RepresentationModel<?> orderModel = HalModelBuilder
    .halModelOf(orderRepresentation)
    .embed(customerModel, LinkRelation.of("customer"))
    .link(orderSelf)
    .build();
~~~

Khi đó embedded customer có thể chứa cả dữ liệu và `_links.self` riêng của nó. Link ở cấp cha vẫn có thể được giữ nếu client cần điều hướng trực tiếp từ đơn hàng đến khách hàng.

Cấu trúc khái quát:

~~~json
{
  "id": "4711",
  "_links": {
    "self": {
      "href": "/orders/4711"
    }
  },
  "_embedded": {
    "customer": {
      "id": "42",
      "displayName": "Nguyễn An",
      "_links": {
        "self": {
          "href": "/customers/42"
        }
      }
    }
  }
}
~~~

Dùng representation lồng nhau khi client cần khám phá các quan hệ của embedded item. Nếu chỉ cần một vài trường để hiển thị, DTO preview thuần sẽ nhẹ hơn và đơn giản hơn.

## 9. Nhúng một item và preview của link

Hai thao tác `embed(...)` và `preview(...).forLink(...)` có mục đích khác nhau:

| API | Kết quả chính | Khi dùng |
|---|---|---|
| `embed(item, rel)` | Thêm item vào `_embedded` | Snapshot hoặc dữ liệu lồng không cần link |
| `preview(item).forLink(link)` | Thêm link vào `_links` và preview vào `_embedded` | Item là bản xem trước của tài nguyên đích |
| `embed(collection, rel)` | Thêm nhiều item vào relation | Collection lồng trong representation |
| `preview(collection).forLink(link)` | Link collection cùng preview collection | Collection quan hệ có URI riêng |

Nếu client có thể truy cập tài nguyên đích, preview thường là lựa chọn phù hợp: response cung cấp dữ liệu để dùng ngay và link để điều hướng. Nếu payload chỉ là snapshot gắn với tài nguyên cha, embed độc lập có thể đúng ngữ nghĩa hơn.

Không nên dùng `embed(...)` chỉ để tránh thiết kế endpoint cho dữ liệu thực sự cần được truy cập, cập nhật hoặc phân quyền độc lập.

## 10. Embedded collection và trường hợp rỗng

Bài học này tập trung vào một item, nhưng cần hiểu cách builder phân biệt item với collection. Với một collection:

~~~java
HalModelBuilder.halModelOf(order)
    .embed(reviews, ReviewPreview.class)
    .link(self)
    .build();
~~~

Spring HATEOAS suy ra relation collection từ kiểu `ReviewPreview`. Nếu collection có phần tử, chúng được đưa vào mảng trong `_embedded`.

Nếu collection rỗng và chỉ truyền một collection không có kiểu fallback, builder không có dữ liệu để suy ra relation; khi đó relation có thể không xuất hiện. Có thể truyền kiểu hoặc relation rõ ràng:

~~~java
HalModelBuilder.halModelOf(order)
    .embed(Collections.emptyList(), ReviewPreview.class)
    .link(self)
    .build();
~~~

Import cho ví dụ collection rỗng:

~~~java
import java.util.Collections;
~~~

Hoặc:

~~~java
HalModelBuilder.halModelOf(order)
    .embed(Collections.emptyList(), LinkRelation.of("reviews"))
    .link(self)
    .build();
~~~

Cách này cho phép response công bố rõ một collection embedded rỗng:

~~~json
{
  "_embedded": {
    "reviews": []
  }
}
~~~

Đối với một item đơn lẻ, nếu không có dữ liệu liên quan, hãy quyết định hợp đồng API có nên bỏ relation embedded hay trả một biểu diễn rỗng riêng. Không biến một item không tồn tại thành object giả với các trường null nếu điều đó làm client hiểu sai trạng thái tài nguyên.

## 11. Kiểm thử item embedded bằng MockMvc

Kiểm thử cần xác nhận:

- Media type là HAL JSON khi client yêu cầu.
- Embedded item xuất hiện dưới relation đúng.
- Nội dung preview chứa đúng các trường công khai.
- Link tương ứng trỏ đến tài nguyên đích.
- Các trường nội bộ không bị serialize.
- Khi không có quan hệ, response tuân theo quy ước đã chọn.

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService orderService;

    @MockBean
    CustomerQueryService customerQueryService;

    @Test
    void embedsCustomerPreviewAndExposesItsLink() throws Exception {
        UUID orderId = UUID.fromString(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        );
        UUID customerId = UUID.fromString(
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        );

        given(orderService.getRequired(orderId))
            .willReturn(orderWithCustomer(orderId, customerId));

        given(customerQueryService.getPreview(customerId))
            .willReturn(new CustomerPreview(
                customerId,
                "Nguyễn An",
                "GOLD"
            ));

        mvc.perform(get("/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._embedded.customer.id")
                .value(customerId.toString()))
            .andExpect(jsonPath("$._embedded.customer.displayName")
                .value("Nguyễn An"))
            .andExpect(jsonPath("$._embedded.customer.tier")
                .value("GOLD"))
            .andExpect(jsonPath("$._links.customer.href")
                .value(endsWith("/customers/" + customerId)));
    }
}
~~~

Các fixture `orderWithCustomer(...)` và service là thành phần kiểm thử của ứng dụng. Import thường dùng:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

### 11.1. Kiểm thử relation và trường dữ liệu

Nếu đổi relation `customer` thành `buyer`, đường dẫn JSONPath cũng thay đổi từ `$._embedded.customer` thành `$._embedded.buyer`. Đây là thay đổi hợp đồng API, nên test cần bảo vệ tên relation đã công bố.

Ngoài ra, kiểm tra embedded DTO chỉ chứa trường được phép. Nếu vô tình nhúng JPA entity trực tiếp, response có thể lộ trường nội bộ hoặc tạo vòng lặp serialize qua quan hệ hai chiều.

### 11.2. Kiểm thử khi item không tồn tại

Nếu đơn hàng không có khách hàng liên quan hoặc khách hàng đã bị xóa, API cần quy định rõ:

- Bỏ cả link và embedded item nếu quan hệ không còn tồn tại.
- Giữ link nhưng không nhúng preview nếu tài nguyên đích không thể đọc.
- Trả một biểu diễn trạng thái quan hệ nếu nghiệp vụ yêu cầu giải thích rõ.

Không trả embedded object giả chỉ để giữ cấu trúc JSON. Kiểm thử trường hợp này để bảo đảm client nhận biết chính xác trạng thái quan hệ.

## 12. Hiệu năng, tính nhất quán và bảo mật

Nhúng item giảm request bổ sung nhưng làm response lớn hơn. Nó cũng có thể khiến dữ liệu trong embedded item cũ hơn dữ liệu ở tài nguyên đích.

Một số nguyên tắc:

- Chỉ nhúng trường cần thiết cho use case của representation cha.
- Dùng DTO preview thay vì serialize trực tiếp JPA entity.
- Tránh nhúng sâu nhiều cấp nếu nó làm payload lớn và khó kiểm soát.
- Cân nhắc cache và thời điểm dữ liệu preview được tạo.
- Nếu client cần dữ liệu mới nhất, cung cấp link để lấy tài nguyên đích.
- Chỉ nhúng trường mà người dùng hiện tại được phép đọc.
- Không coi việc ẩn embedded item hoặc link là cơ chế bảo mật duy nhất; endpoint đích vẫn phải kiểm tra quyền.

Ví dụ, một khách hàng có thể có email riêng tư. Người dùng được phép đọc đơn hàng chưa chắc được phép đọc email khách hàng. DTO preview phải được tạo theo quyền của request hiện tại và chỉ chứa dữ liệu được phép công bố.

Nếu nhiều request cùng đọc đơn hàng và khách hàng, cần tránh truy vấn N+1 khi tạo preview cho một collection lớn. Có thể dùng projection, batch query hoặc query tối ưu để lấy dữ liệu quan hệ theo nhóm.

## 13. Lỗi thường gặp khi nhúng item

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm embedded item với thuộc tính JSON thông thường | Client không nhận được ngữ nghĩa relation HAL | Đặt item trong `_embedded` qua HAL model builder |
| Chỉ nhúng dữ liệu mà quên link khi tài nguyên có URI riêng | Client khó truy cập bản đầy đủ hoặc làm mới | Dùng `preview(...).forLink(...)` |
| Dùng sai relation | Client không tìm được embedded item | Khai báo `@Relation` hoặc relation tường minh |
| Nhúng toàn bộ JPA entity | Lộ trường nội bộ, vòng lặp hoặc payload lớn | Dùng DTO preview |
| Nhúng quá nhiều cấp | Response nặng và khó duy trì | Chỉ nhúng dữ liệu thường dùng |
| Coi preview luôn mới nhất | Client dùng dữ liệu đã cũ | Theo link để làm mới khi cần |
| Không kiểm tra quyền của dữ liệu nhúng | Rò rỉ thông tin qua tài nguyên cha | Áp dụng quyền trước khi tạo preview |
| Dùng embed snapshot như tài nguyên điều hướng | Client kỳ vọng một URI không tồn tại | Chỉ thêm link khi có tài nguyên đích |
| Không kiểm thử tên relation | Thay đổi relation phá client | Kiểm thử `_embedded` và `_links` |

## 14. Quy trình thiết kế item embedded

Khi muốn nhúng một tài nguyên liên quan trong HAL, có thể làm theo trình tự:

1. Xác định tài nguyên cha và item liên quan mà client thường cần cùng lúc.
2. Quyết định item là preview của tài nguyên độc lập hay snapshot thuộc tài nguyên cha.
3. Tạo DTO chỉ chứa các trường cần công bố.
4. Chọn relation ổn định bằng `@Relation` hoặc `LinkRelation`.
5. Nếu item có URI riêng, tạo link đến nó và dùng `preview(item).forLink(link)`.
6. Nếu chỉ cần snapshot, dùng `embed(item, relation)` mà không tạo link giả.
7. Nếu item có quan hệ và link riêng, cân nhắc nhúng một representation hypermedia.
8. Kiểm tra payload, quyền truy cập và chiến lược làm mới dữ liệu.
9. Kiểm thử media type, relation, nội dung embedded, href và trường hợp không có item.
10. Theo dõi kích thước response và truy vấn khi nhúng trong collection lớn.

## 15. Kết luận

Item embedded cho phép HAL representation chứa trực tiếp một tài nguyên liên quan dưới `_embedded`. Nó giúp client dùng dữ liệu thường xuyên cần đến mà không phải gửi request bổ sung. Khi tài nguyên đích có URI riêng, nên công bố link trong `_links` và có thể nhúng bản xem trước tương ứng.

Spring HATEOAS cung cấp `HalModelBuilder` để thực hiện điều đó. `preview(...).forLink(...)` tạo link cùng embedded preview; `embed(..., LinkRelation)` nhúng một payload theo relation tường minh. `@Relation` giúp quản lý tên item và collection relation. Khi chọn đúng dữ liệu, relation và chính sách truy cập, embedded resource làm response thuận tiện hơn mà vẫn giữ khả năng điều hướng hypermedia.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Building HAL representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal): `HalModelBuilder`, preview và embedded documents.
- [Spring HATEOAS API — HalModelBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalModelBuilder.html): API `halModelOf`, `preview`, `forLink`, `embed` và `build`.
- [Spring HATEOAS API — Relation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html): cấu hình item relation và collection relation.
- [Spring HATEOAS API — LinkRelationProvider](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html): cách xác định relation cho tài nguyên và collection.

