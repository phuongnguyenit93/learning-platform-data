# Lợi ích của HATEOAS

HATEOAS (Hypermedia as the Engine of Application State) giúp một REST API hướng dẫn client cách tiếp tục tương tác thông qua các liên kết và thông tin hành động được đặt ngay trong biểu diễn tài nguyên. Thay vì phải biết trước mọi URL và tự suy luận trạng thái nghiệp vụ, client đọc tài nguyên hiện tại, tìm liên kết có quan hệ phù hợp rồi đi theo liên kết đó.

Với Spring HATEOAS, server có thể xây dựng các biểu diễn như `EntityModel`, `CollectionModel` và `PagedModel`, sau đó gắn các `Link` được tạo từ ánh xạ controller. Cách làm này đem lại lợi ích rõ nhất khi API có nhiều tài nguyên liên quan, quy trình nhiều trạng thái hoặc cần thay đổi đường dẫn theo thời gian.

## HATEOAS thay đổi cách client sử dụng API như thế nào?

Một API chỉ trả dữ liệu thường yêu cầu client biết trước cấu trúc URL:

```http
GET /api/orders/ORD-2048
```

Client nhận được mã đơn hàng và trạng thái, rồi tự ghép URL để hủy đơn, xem danh sách hoặc theo dõi giao hàng. Khi đường dẫn thay đổi, logic ghép URL ở từng client có thể phải cập nhật.

Với HATEOAS, biểu diễn đơn hàng mang theo các liên kết mô tả những hướng đi có ý nghĩa:

```json
{
  "id": "ORD-2048",
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "/api/orders/ORD-2048"
    },
    "orders": {
      "href": "/api/orders"
    },
    "cancel": {
      "href": "/api/orders/ORD-2048/cancel"
    }
  }
}
```

Đây là dạng biểu diễn theo HAL. `_links` chứa các liên kết; mỗi liên kết có một quan hệ (`rel`) và một đích (`href`). `self` trỏ về tài nguyên hiện tại, `orders` dẫn đến tập hợp đơn hàng, còn `cancel` biểu thị hướng tương tác hủy đơn đang khả dụng. Client có thể tìm liên kết theo `rel` thay vì tự ghép đường dẫn từ `id`.

Ví dụ trên minh họa một liên kết tới thao tác. Trong HAL cơ bản, `href` và `rel` chưa mô tả đầy đủ HTTP method hay cấu trúc dữ liệu gửi lên. Nếu client cần biết cách thực hiện một thao tác như `POST`, dữ liệu đầu vào và kiểu nội dung, API cần công bố thêm affordance qua định dạng hypermedia phù hợp, chẳng hạn HAL-FORMS, hoặc thông qua hợp đồng API đã thống nhất.

## Những lợi ích chính

### 1. Khám phá API từ chính tài nguyên

Client có thể bắt đầu từ một URL gốc đã biết, sau đó lần theo các liên kết để tìm tài nguyên tiếp theo. Mỗi biểu diễn cung cấp ngữ cảnh điều hướng tại thời điểm được trả về.

Điều này hữu ích khi client không cần được cấu hình sẵn toàn bộ đường dẫn. Ví dụ, từ tài nguyên khách hàng, client có thể tìm liên kết `orders` để xem các đơn hàng của khách hàng; từ một đơn hàng, client có thể tìm `payment`, `cancel` hoặc `tracking` nếu các hướng tương tác đó được cung cấp.

Các quan hệ liên kết có ý nghĩa nghiệp vụ giúp biểu diễn dễ hiểu hơn. Client quan tâm đến quan hệ `orders` hoặc `tracking`, thay vì phải đoán rằng một URL cụ thể có chứa `/customers/{id}/orders` hay `/shipments/{id}`.

### 2. Giảm phụ thuộc vào cấu trúc URL

Khi client tự ghép URL, cấu trúc đường dẫn trở thành một phần ngầm định của hợp đồng. Chuyển `/api/orders/{id}` sang `/api/v2/orders/{id}` có thể làm hỏng client nếu client lưu cứng đường dẫn.

Với HATEOAS, client nhận URL từ liên kết trong biểu diễn. Server có thể tổ chức lại route hoặc đặt API sau một gateway mà vẫn giữ được cách điều hướng, miễn là các quan hệ liên kết và ngữ nghĩa của chúng tiếp tục được hỗ trợ. Đây là giảm phụ thuộc vào URL, không phải loại bỏ mọi phụ thuộc: client vẫn cần hiểu media type, các quan hệ liên kết mà nó sử dụng và quy tắc của thao tác.

### 3. Phản ánh trạng thái nghiệp vụ và hành động khả dụng

Một tài nguyên có thể cung cấp các liên kết khác nhau tùy trạng thái hiện tại. Đơn hàng `PENDING` có thể cho phép thanh toán hoặc hủy; đơn hàng `SHIPPED` có thể cung cấp liên kết theo dõi; đơn hàng `DELIVERED` có thể cung cấp liên kết đánh giá.

Server có thể quyết định liên kết nào xuất hiện dựa trên trạng thái và quyền của người dùng. Client đọc các khả năng được công bố thay vì tự sao chép toàn bộ quy tắc chuyển trạng thái. Điều này giảm nguy cơ giao diện hiển thị một nút cho thao tác không còn hợp lệ.

```text
PENDING
  ├── payment  → PAID
  └── cancel   → CANCELLED

PAID
  └── shipment → SHIPPED

SHIPPED
  └── tracking → DELIVERED
```

Sơ đồ chỉ minh họa quy trình. Trong API thực tế, liên kết được trả về phải phản ánh trạng thái và quyền truy cập hiện tại; server vẫn phải kiểm tra điều kiện nghiệp vụ khi client gọi endpoint. Việc một liên kết từng xuất hiện không đảm bảo thao tác sẽ thành công mãi mãi, vì trạng thái có thể thay đổi giữa lúc đọc và lúc gửi yêu cầu.

### 4. Hỗ trợ API tiến hóa theo thời gian

Khi API bổ sung một hướng điều hướng mới, server có thể thêm một quan hệ liên kết vào biểu diễn. Client cũ có thể bỏ qua quan hệ mà nó chưa biết, trong khi client mới có thể sử dụng liên kết đó khi cần.

Ví dụ, một phiên bản API bổ sung `invoice` cho đơn hàng đã thanh toán. Client vốn chỉ đọc `self`, `orders` và `cancel` vẫn có thể tiếp tục xử lý những quan hệ quen thuộc. Client mới có thể phát hiện `invoice` và mở hóa đơn.

Khả năng tiến hóa này hiệu quả khi quan hệ liên kết được đặt tên ổn định, có ngữ nghĩa rõ ràng và được tài liệu hóa. Thay đổi ý nghĩa của một `rel`, thay đổi định dạng dữ liệu mà client đang phụ thuộc hoặc xóa một quan hệ đang được sử dụng vẫn có thể tạo ra thay đổi không tương thích.

### 5. Điều hướng tập hợp và phân trang thuận tiện

Với danh sách lớn, client thường cần biết trang kế tiếp, trang trước hoặc trang đầu. Các liên kết `next`, `prev`, `first` và `last` cho phép server cung cấp đích điều hướng tương ứng với truy vấn hiện tại.

Client chỉ cần theo liên kết được trả về, không phải tự tính `page`, `size` hay ghép lại các tham số lọc và sắp xếp. Server có thể thay đổi chiến lược phân trang hoặc cách biểu diễn tham số mà không buộc mọi client phải tự xây dựng URL mới.

Spring HATEOAS hỗ trợ `PagedModel` để biểu diễn dữ liệu phân trang cùng metadata và liên kết điều hướng. Các liên kết này đặc biệt hữu ích khi tập dữ liệu thay đổi liên tục hoặc khi cách phân trang được quản lý tập trung ở server.

### 6. Tạo hợp đồng tương tác rõ ràng hơn

Liên kết có quan hệ được đặt tên giúp thể hiện tài nguyên liên quan và hướng đi tiếp theo. Affordance có thể bổ sung mô tả về thao tác được hỗ trợ, chẳng hạn phương thức HTTP, kiểu nội dung và các trường đầu vào. Nhờ đó, một số client có thể xây dựng giao diện hoặc biểu mẫu dựa trên khả năng server công bố.

Spring HATEOAS cho phép gắn affordance vào liên kết. Khi cần truyền mô tả thao tác cho client, hãy chọn media type có khả năng biểu diễn affordance, chẳng hạn HAL-FORMS, và kiểm tra đúng cấu trúc phản hồi mà client hỗ trợ. Chỉ thêm một `Link` trong HAL không tự động biến liên kết đó thành một biểu mẫu hay mô tả đầy đủ request.

## Spring HATEOAS hỗ trợ hiện thực hóa các lợi ích này

Spring HATEOAS cung cấp các lớp mô hình và API tạo liên kết để ứng dụng xây dựng biểu diễn hypermedia nhất quán.

| Thành phần | Vai trò | Lợi ích khi sử dụng |
|---|---|---|
| `RepresentationModel<T>` | Lớp cơ sở cho biểu diễn có liên kết | Cho phép mô hình phản hồi tùy chỉnh mang theo các liên kết |
| `EntityModel<T>` | Bọc một đối tượng nội dung cùng các liên kết | Tạo biểu diễn cho một tài nguyên đơn lẻ |
| `CollectionModel<T>` | Bọc một tập hợp tài nguyên cùng các liên kết | Mô tả tập hợp và đường dẫn điều hướng của tập hợp |
| `PagedModel<T>` | Biểu diễn tập hợp có phân trang | Cung cấp metadata trang và các liên kết điều hướng |
| `WebMvcLinkBuilder` | Tạo liên kết dựa trên ánh xạ Spring MVC | Hạn chế việc viết cứng đường dẫn trong mã tạo liên kết |
| `RepresentationModelAssembler` | Chuyển đổi đối tượng miền thành mô hình biểu diễn | Tập trung cách tạo liên kết và biểu diễn cho một loại tài nguyên |

Ví dụ sau tạo biểu diễn cho một đơn hàng. Liên kết `cancel` chỉ được thêm khi đơn hàng còn ở trạng thái chờ xử lý:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        UUID id = order.getId();

        EntityModel<Order> model = EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
                linkTo(methodOn(OrderController.class).all()).withRel("orders")
        );

        if (order.getStatus() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel")
                    .andAffordance(afford(methodOn(OrderController.class).cancel(id))));
        }

        return model;
    }
}
```

`methodOn(...)` tạo tham chiếu tới phương thức controller để Spring HATEOAS suy ra đường dẫn từ mapping. `withSelfRel()` gắn quan hệ chuẩn `self`; `withRel("orders")` và `withRel("cancel")` gắn các quan hệ do API định nghĩa. Việc gom logic vào assembler giúp controller tập trung xử lý yêu cầu, còn cách biểu diễn và điều hướng của đơn hàng được dùng lại ở nhiều nơi.

Controller có thể ủy quyền việc chuyển đổi cho assembler:

```java
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<Order> one(@PathVariable UUID id) {
        Order order = service.findRequired(id);
        return assembler.toModel(order);
    }

    @GetMapping
    public CollectionModel<EntityModel<Order>> all() {
        List<EntityModel<Order>> orders = service.findAll().stream()
                .map(assembler::toModel)
                .collect(Collectors.toList());

        return CollectionModel.of(
                orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }

    @PostMapping("/{id}/cancel")
    public ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }

}
```

Đây là ví dụ rút gọn; ứng dụng cần khai báo các kiểu miền và service tương ứng. `andAffordance(afford(...))` gắn mô tả thao tác hủy vào liên kết. Để client nhận được mô tả này, ứng dụng cần thương lượng và trả về media type hỗ trợ affordance, chẳng hạn `application/prs.hal-forms+json`. Endpoint hủy đơn vẫn phải xác thực quyền và kiểm tra trạng thái trong service. Việc assembler chỉ thêm liên kết khi đơn hàng đang `PENDING` giúp client hiểu khả năng hiện tại, nhưng không thay thế kiểm tra ở phía server.

## Ví dụ về tác động đối với client

Giả sử client nhận được một biểu diễn HAL và cần hiển thị thao tác hủy. Client tìm quan hệ `cancel`:

```javascript
const cancelUrl = order._links?.cancel?.href;

if (cancelUrl) {
  showCancelButton();
} else {
  hideCancelButton();
}
```

Khi người dùng chọn hủy, client gửi yêu cầu theo hợp đồng của API tới URL trong liên kết. Với ví dụ endpoint ở trên, thao tác dùng `POST`. Nếu client cần xác định method và dữ liệu đầu vào một cách tự động, server phải cung cấp affordance theo media type mà client hiểu.

Điểm quan trọng là client không suy ra URL bằng cách nối `order.id` vào chuỗi `"/api/orders/"`, cũng không cần tự quyết định rằng mọi đơn hàng đều có thể hủy. Client sử dụng quan hệ liên kết server công bố, còn server thực thi quy tắc nghiệp vụ cuối cùng.

## Khi nào lợi ích của HATEOAS thể hiện rõ?

HATEOAS phù hợp khi một hoặc nhiều điều kiện sau xuất hiện:

- Quy trình có nhiều trạng thái và mỗi trạng thái cho phép các thao tác khác nhau.
- Client cần điều hướng giữa nhiều loại tài nguyên có quan hệ với nhau.
- API có phân trang, lọc hoặc các liên kết tiếp diễn do server quyết định.
- Server cần thay đổi cấu trúc URL mà vẫn duy trì cách điều hướng theo các quan hệ ổn định.
- Nhiều loại client cần khám phá các khả năng được API công bố theo cùng một hợp đồng hypermedia.

HATEOAS cũng tạo thêm chi phí: phản hồi chứa nhiều metadata hơn, client phải hiểu media type và quan hệ liên kết, còn đội ngũ phát triển phải duy trì và kiểm thử các liên kết đó. Với API nội bộ rất nhỏ, ít thay đổi và chỉ có một client được kiểm soát chặt, lợi ích có thể chưa bù được chi phí triển khai.

## Những điểm cần lưu ý để nhận được lợi ích thực tế

1. **Chọn quan hệ liên kết có ngữ nghĩa ổn định.** Dùng `self`, `next`, `prev` khi đúng ý nghĩa chuẩn; với quan hệ riêng của API, chọn tên dễ hiểu và tài liệu hóa.
2. **Để server quyết định khả năng hiện tại.** Tạo hoặc loại bỏ liên kết dựa trên trạng thái nghiệp vụ và quyền của người gọi. Vẫn kiểm tra lại mọi điều kiện khi nhận yêu cầu thực thi.
3. **Để client theo `rel`, không phân tích `href`.** Client nên xem URL là đích được server cung cấp, không phụ thuộc vào cấu trúc chuỗi của URL.
4. **Thống nhất media type.** HAL biểu diễn liên kết theo `_links`; nếu cần mô tả biểu mẫu hoặc thao tác chi tiết, hãy chọn định dạng có hỗ trợ affordance và bảo đảm client hiểu định dạng đó.
5. **Kiểm thử hợp đồng hypermedia.** Kiểm tra `self`, các liên kết liên quan, liên kết phân trang và việc liên kết hành động xuất hiện hoặc biến mất theo trạng thái.

Ví dụ kiểm thử với MockMvc có thể xác nhận liên kết `cancel` xuất hiện cho đơn hàng đang chờ xử lý:

```java
mockMvc.perform(get("/api/orders/{id}", pendingOrderId)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với đơn hàng đã giao, một kiểm thử tương ứng nên xác nhận liên kết `cancel` không xuất hiện và liên kết `tracking` hoặc quan hệ phù hợp với trạng thái được cung cấp. Các kiểm thử này bảo vệ hành vi điều hướng mà client thực sự sử dụng, đồng thời giúp nhóm phát hiện sớm thay đổi ngoài ý muốn trong hợp đồng API.

## Kết luận

HATEOAS giúp REST API trở nên dễ khám phá và có khả năng tự mô tả hướng tương tác thông qua liên kết hypermedia. Khi được áp dụng đúng, nó giảm sự phụ thuộc của client vào URL cố định, phản ánh hành động theo trạng thái nghiệp vụ, hỗ trợ phân trang và tạo điều kiện để API tiến hóa có kiểm soát. Spring HATEOAS cung cấp các mô hình và công cụ tạo liên kết để đưa những lợi ích đó vào controller và lớp biểu diễn của ứng dụng Spring.
