# Thuật ngữ cốt lõi

Spring HATEOAS giúp một REST API trả về tài nguyên cùng các liên kết hypermedia để client khám phá những tài nguyên liên quan và những bước tiếp theo mà API cung cấp. Để thiết kế và đọc được kiểu API này, cần phân biệt rõ tài nguyên, biểu diễn, liên kết, quan hệ liên kết, affordance và các lớp mô hình mà Spring HATEOAS cung cấp.

## HATEOAS và hypermedia

**HATEOAS** là viết tắt của *Hypermedia As The Engine Of Application State*. Đây là ràng buộc của REST trong đó client điều hướng ứng dụng bằng các điều khiển hypermedia có trong biểu diễn mà server trả về. Thay vì phải tự ghép mọi URL từ quy ước đường dẫn, client đọc liên kết trong phản hồi rồi chọn liên kết phù hợp với trạng thái và mục tiêu của mình.

**Hypermedia** là nội dung kết hợp dữ liệu với các tham chiếu có thể điều hướng, chẳng hạn liên kết tới tài nguyên khác hoặc mô tả một hành động. Một phản hồi đơn giản chỉ chứa `id`, `status` và `total` có thể cho client biết thông tin về đơn hàng. Khi phản hồi còn có liên kết `self`, `customer`, `payment` hoặc `cancel`, nó cung cấp thêm các đường đi mà client có thể khám phá.

HATEOAS không có nghĩa là client không cần biết gì về API. Client vẫn cần hiểu ý nghĩa dữ liệu và các quan hệ liên kết mà API công bố. Điểm khác biệt là client dựa vào quan hệ có ý nghĩa và liên kết được server cung cấp, thay vì phụ thuộc cứng vào cấu trúc URL nội bộ.

## Tài nguyên, entity và representation

**Tài nguyên (resource)** là khái niệm mà API công bố, ví dụ một đơn hàng, khách hàng hoặc danh sách đơn hàng. Tài nguyên được nhận diện qua URI và có thể được truy xuất hoặc thay đổi thông qua các phương thức HTTP phù hợp.

**Entity/domain object** là đối tượng trong mô hình nghiệp vụ của ứng dụng. Ví dụ, `Order` có thể chứa mã đơn, trạng thái, tổng tiền và các quy tắc nghiệp vụ. Đối tượng này không nhất thiết phải được trả nguyên trạng cho client.

**Representation (biểu diễn)** là dạng dữ liệu cụ thể mà server gửi hoặc nhận khi trao đổi về một tài nguyên. Một tài nguyên có thể có nhiều biểu diễn, tùy media type và nhu cầu của client. Với Spring HATEOAS, biểu diễn thường bao gồm dữ liệu nghiệp vụ cùng metadata hypermedia như liên kết.

Phân biệt ba khái niệm này giúp tránh đồng nhất lớp entity với hợp đồng HTTP. Ứng dụng có thể giữ nguyên mô hình nghiệp vụ nhưng thay đổi cách biểu diễn, bổ sung liên kết hoặc cung cấp một media type khác mà không buộc client phải biết cấu trúc nội bộ của entity.

## Link và link relation

**Link (liên kết)** là một tham chiếu hypermedia được đặt trong biểu diễn. Một liên kết thường có các thành phần sau:

- `href`: URI đích mà client có thể điều hướng tới. URI có thể là tuyệt đối hoặc tương đối theo quy tắc của media type.
- `rel` (*relation*): tên quan hệ mô tả ý nghĩa của liên kết, tức liên kết dẫn tới loại tài nguyên hoặc bước tiếp theo nào.
- Các thuộc tính tùy chọn như `title`, `type` hoặc `templated`: cung cấp thêm thông tin về liên kết. Ý nghĩa và cách biểu diễn cụ thể phụ thuộc định dạng hypermedia.

Ví dụ, `self` thường trỏ tới chính tài nguyên hiện tại; `next` và `prev` thường dùng khi điều hướng trang; `orders` có thể biểu thị liên kết tới tập hợp đơn hàng. `self` là một quan hệ phổ biến được chuẩn hóa. Các quan hệ nghiệp vụ như `cancel` hoặc `payment` có thể do API định nghĩa; khi cần khả năng dùng chung giữa nhiều hệ thống, nên công bố định nghĩa quan hệ ổn định, chẳng hạn bằng URI tài liệu.

`href` cho biết đích đến, còn `rel` cho biết ý nghĩa của đường dẫn. Client nên dựa vào `rel` để tìm liên kết cần dùng, không phân tích chuỗi URL để đoán ý nghĩa. Tên quan hệ là một phần của hợp đồng API: đổi tên hoặc đổi nghĩa một relation có thể làm hỏng client dù đường dẫn vẫn truy cập được.

## Affordance: mô tả hành động khả dụng

**Affordance** mô tả một tương tác mà tài nguyên hỗ trợ, ví dụ hủy đơn, cập nhật địa chỉ giao hàng hoặc gửi thanh toán. Một liên kết thông thường cho biết nơi có thể điều hướng tới. Affordance bổ sung thông tin về cách tương tác, chẳng hạn phương thức HTTP và dữ liệu đầu vào mà hành động yêu cầu, tùy định dạng hypermedia được sử dụng.

Điều này đặc biệt hữu ích khi hành động phụ thuộc trạng thái. Đơn hàng đang chờ xử lý có thể cung cấp hành động `cancel`; đơn hàng đã giao có thể không còn cung cấp hành động đó. Client quan sát các điều khiển hiện có để quyết định bước tiếp theo, thay vì tự suy luận toàn bộ quy tắc chuyển trạng thái.

Trong Spring HATEOAS, affordance có thể được gắn với một `Link`. Ví dụ dưới đây minh họa ý tưởng liên kết tới đơn hàng đồng thời mô tả phương thức controller dùng để hủy đơn:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link cancelLink = linkTo(methodOn(OrderController.class).one(orderId))
    .withSelfRel()
    .andAffordance(afford(methodOn(OrderController.class).cancel(orderId)));
```

Ví dụ giả định `OrderController` có các phương thức `one` và `cancel` được ánh xạ bằng Spring MVC. Định dạng phản hồi phải hỗ trợ cách biểu diễn affordance mà ứng dụng chọn. Chỉ thêm một link có `rel="cancel"` không tự động mô tả đầy đủ HTTP method hay cấu trúc request body.

Affordance cũng không thay thế xác thực hoặc phân quyền. Server vẫn phải kiểm tra người gọi, quyền thao tác và trạng thái nghiệp vụ tại thời điểm nhận request; việc một hành động xuất hiện trong phản hồi không phải là cơ chế bảo mật.

## Các lớp mô hình trong Spring HATEOAS

Spring HATEOAS cung cấp các lớp giúp xây dựng representation có liên kết mà không phải tự tạo cấu trúc JSON hypermedia bằng tay.

| Kiểu | Vai trò |
| --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho một representation có thể gắn các `Link`. |
| `EntityModel<T>` | Bọc một đối tượng nội dung, thường là một entity hoặc DTO, cùng các liên kết của nó. |
| `CollectionModel<T>` | Biểu diễn một tập hợp các model, có thể gắn liên kết cho cả tập hợp. |
| `PagedModel<T>` | Biểu diễn tập hợp có thông tin phân trang và điều hướng trang. |
| `RepresentationModelAssembler<T, D>` | Chuyển đối tượng nguồn thành representation đích, giúp gom logic ánh xạ dữ liệu và liên kết. |
| `Link` | Đối tượng mô hình hóa một liên kết hypermedia. |

Ví dụ, `EntityModel<Order>` có thể chứa dữ liệu của một đơn hàng cùng liên kết `self` và `orders`. `CollectionModel<EntityModel<Order>>` có thể chứa nhiều model đơn hàng và liên kết tới chính collection. Khi dùng `PagedModel`, client có thể nhận thêm thông tin và liên kết điều hướng trang.

Các lớp này là mô hình Java ở phía server. Khi trả về qua Spring MVC, bộ chuyển đổi message và cấu hình hypermedia sẽ tuần tự hóa chúng thành media type tương ứng. Vì vậy, không nên giả định mọi cấu trúc JSON đều giống nhau bất kể media type.

## Tạo liên kết từ controller

`WebMvcLinkBuilder` cung cấp các hàm dựng URI dựa trên mapping của controller. `linkTo(...)` xác định controller hoặc phương thức đích; `methodOn(...)` tạo lời gọi mô phỏng để Spring HATEOAS đọc mapping và tham số đường dẫn. Lời gọi mô phỏng này không thực thi nghiệp vụ của phương thức controller.

Ví dụ rút gọn sau minh họa một endpoint chi tiết và endpoint collection:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;

    OrderController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable Long id) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }

    @GetMapping
    CollectionModel<EntityModel<Order>> all() {
        List<EntityModel<Order>> orders = repository.findAll().stream()
            .map(order -> EntityModel.of(order,
                linkTo(methodOn(OrderController.class).one(order.getId()))
                    .withSelfRel()))
            .collect(Collectors.toList());

        return CollectionModel.of(orders,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

`Order`, `OrderRepository` và `OrderNotFoundException` là các kiểu thuộc ứng dụng minh họa, cần được định nghĩa trong dự án thực tế. Endpoint chi tiết trả về `EntityModel<Order>` với hai quan hệ; endpoint collection trả về `CollectionModel` chứa các model đơn hàng. Cách tạo link từ mapping giúp giảm việc ghép chuỗi URI thủ công và giữ liên kết đồng bộ hơn khi mapping controller thay đổi.

Trong ứng dụng lớn, có thể chuyển logic tạo model sang một assembler:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        return EntityModel.of(order,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }
}
```

Controller có thể gọi `assembler.toModel(order)` cho một đối tượng và `assembler.toCollectionModel(orders)` cho một tập hợp. Cách tổ chức này giúp các endpoint dùng chung quy tắc biểu diễn, tránh mỗi controller tạo liên kết theo một kiểu khác nhau.

## HAL và cấu trúc phản hồi

**HAL** (*Hypertext Application Language*) là một định dạng biểu diễn hypermedia phổ biến. Trong HAL JSON, liên kết nằm dưới `_links`; tài nguyên con được nhúng có thể nằm dưới `_embedded`. Ví dụ minh họa:

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
    }
  }
}
```

Trong ví dụ, `id`, `status` và `total` là dữ liệu của đơn hàng; `_links` là phần điều hướng. Tên `self` và `orders` chính là các quan hệ liên kết. Client có thể đọc liên kết `orders` mà không cần tự ghép URI collection.

Với Spring Boot, dependency `spring-boot-starter-hateoas` cung cấp tích hợp Spring HATEOAS với Spring MVC và hỗ trợ cấu hình tuần tự hóa hypermedia. HAL JSON thường được trao đổi với media type `application/hal+json`. Client và server cần thống nhất media type qua cơ chế content negotiation; cấu trúc HAL không nên bị nhầm với một JSON tùy ý chỉ có trường `_links`.

HAL tập trung vào biểu diễn liên kết và tài nguyên nhúng. Nếu cần mô tả biểu mẫu hoặc dữ liệu đầu vào cho thao tác, có thể cân nhắc một định dạng hỗ trợ affordance phù hợp, chẳng hạn HAL-FORMS. Việc chọn media type ảnh hưởng đến cách client đọc metadata và do đó là một phần của hợp đồng API.

## Thuật ngữ liên quan khi thiết kế API

- **Self link**: liên kết `self` trỏ tới tài nguyên hoặc representation hiện tại. Nó giúp client lấy lại tài nguyên theo URI server công bố.
- **Collection resource**: tài nguyên tập hợp, chẳng hạn `/orders`, có thể cung cấp liên kết tới từng phần tử hoặc tới các trang.
- **Embedded resource**: tài nguyên được nhúng trong representation khác, thường dùng để giảm số lần gọi khi dữ liệu liên quan cần được đọc cùng nhau.
- **Templated link**: liên kết chứa URI template với biến cần thay thế, ví dụ một đường dẫn tìm kiếm có tham số. Client phải hiểu quy tắc template của media type trước khi mở rộng nó.
- **Media type**: định danh định dạng và ngữ nghĩa của representation, ví dụ `application/hal+json`. Media type cho client biết cách diễn giải dữ liệu và hypermedia.
- **Assembler**: thành phần ánh xạ domain object hoặc DTO thành model HTTP, bao gồm dữ liệu được công bố và các liên kết cần thiết.

Những thuật ngữ này bổ sung cho nhau: tài nguyên là khái niệm API công bố; representation là dạng trao đổi của tài nguyên; model và assembler giúp tạo representation trong ứng dụng; link cùng relation hỗ trợ điều hướng; affordance mô tả tương tác; media type quy định cách client diễn giải tất cả nội dung đó.

## Vì sao các thuật ngữ này quan trọng với khả năng tiến hóa API?

Giả sử API ban đầu đặt đơn hàng tại `/orders/{id}`. Sau này server thay đổi cấu trúc nội bộ hoặc chuyển sang một đường dẫn khác. Nếu client luôn tìm relation `self` để lấy URI chi tiết, server có thể cập nhật `href` mà không buộc client phải tự dựng lại URL. Tương tự, client tìm relation `next` để sang trang tiếp theo thay vì tự tính đường dẫn phân trang.

Khả năng tiến hóa chỉ đạt được khi hợp đồng được duy trì có kỷ luật. Server cần giữ ý nghĩa relation ổn định, công bố các thay đổi tương thích, và chỉ bỏ liên kết khi client có chiến lược xử lý phù hợp. Client cần xử lý trường hợp một relation không xuất hiện, vì hành động có thể không khả dụng trong trạng thái hiện tại hoặc với quyền hiện tại. Các thay đổi về tên relation, cấu trúc dữ liệu, media type hoặc ý nghĩa affordance đều có thể ảnh hưởng tới khả năng tương thích.

Khi đọc hoặc thiết kế một phản hồi Spring HATEOAS, hãy tự kiểm tra: dữ liệu này đại diện cho tài nguyên nào; liên kết `self` nằm ở đâu; mỗi `rel` có ý nghĩa gì; collection và phân trang được điều hướng ra sao; hành động nào được mô tả bằng affordance; và media type nào quy định cấu trúc phản hồi. Trả lời được các câu hỏi đó là nền tảng để xây dựng REST API có khả năng khám phá và tiến hóa tốt hơn.
