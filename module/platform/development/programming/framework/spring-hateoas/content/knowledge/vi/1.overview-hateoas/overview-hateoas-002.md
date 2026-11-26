# Bài toán HATEOAS giải quyết

Một API có thể trả về dữ liệu đúng nhưng vẫn khiến ứng dụng khách phải tự biết rất nhiều chi tiết về cách đi tiếp: URL của tài nguyên liên quan, đường dẫn để thực hiện thao tác, trang kế tiếp của danh sách, hoặc thao tác nào được phép ở trạng thái hiện tại. Khi các chi tiết đó được viết cứng trong ứng dụng khách, máy khách và máy chủ bị ràng buộc chặt với cấu trúc URL và quy trình nội bộ của nhau.

HATEOAS giải quyết vấn đề điều hướng đó bằng cách đưa các liên kết và thông tin điều khiển siêu phương tiện vào biểu diễn tài nguyên. Máy chủ trả về tài nguyên cùng những đường đi hoặc thao tác có ý nghĩa trong ngữ cảnh hiện tại. Máy khách bắt đầu từ một điểm vào đã biết, đọc các liên kết và đi theo chúng thay vì tự ghép URL từ quy ước đường dẫn.

Trong Spring, Spring HATEOAS cung cấp các kiểu mô hình và công cụ tạo liên kết để xây dựng những biểu diễn như vậy một cách nhất quán.

## 1. Vấn đề khi máy khách phải tự biết đường dẫn API

Xét một hệ thống quản lý đơn hàng. Máy khách gọi:

```http
GET /api/orders/42
```

Máy chủ trả về:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000
}
```

Để hiển thị nút hủy đơn, ứng dụng khách có thể tự suy ra rằng thao tác hủy nằm ở:

```http
POST /api/orders/42/cancel
```

Cách làm này có vẻ đơn giản, nhưng nó buộc máy khách phải biết quy ước URL và quy tắc nghiệp vụ của máy chủ. Khi API thay đổi đường dẫn, mọi ứng dụng khách có cách ghép URL tương tự có thể phải cập nhật. Khi quy trình thay đổi, máy khách có thể phải tự tái hiện các điều kiện như đơn nào được hủy, đơn nào đã thanh toán, hoặc đơn nào đang giao.

Một số vấn đề thường xuất hiện:

- **Ràng buộc vào cấu trúc URL:** máy khách tự ghép `/orders/{id}/cancel`, `/orders/{id}/payments` hoặc đường dẫn của tài nguyên liên quan. URL trở thành một phần ngầm định trong mã máy khách.
- **Lặp lại quy tắc trạng thái:** máy khách phải suy đoán thao tác nào khả dụng dựa trên `status`. Nếu quy tắc nghiệp vụ thay đổi, nhiều máy khách có thể cần thay đổi theo.
- **Khó điều hướng quy trình:** một quy trình có nhiều nhánh như tạo đơn, thanh toán, hủy, giao hàng và hoàn tiền khiến máy khách phải biết trước từng đường dẫn và điều kiện chuyển trạng thái.
- **Khó khám phá tài nguyên liên quan:** từ một đơn hàng, máy khách phải biết cách tìm khách hàng, thanh toán, vận đơn hoặc danh sách đơn hàng.
- **Khó xử lý danh sách linh hoạt:** máy khách có thể tự tạo URL cho trang kế tiếp, trang trước, bộ lọc hoặc sắp xếp thay vì nhận những liên kết tương ứng từ máy chủ.

Vấn đề cốt lõi không nằm ở việc URL có đẹp hay không. Vấn đề là máy khách phải biết trước cách định tuyến và một phần quy trình mà máy chủ đang sở hữu.

## 2. HATEOAS đưa thông tin điều hướng vào biểu diễn tài nguyên

HATEOAS là viết tắt của *Hypermedia as the Engine of Application State*. Đây là một ràng buộc trong phong cách kiến trúc REST: trạng thái và khả năng điều hướng tiếp theo của ứng dụng được thể hiện thông qua các điều khiển siêu phương tiện có trong biểu diễn mà máy chủ gửi về.

Thay vì chỉ trả về dữ liệu đơn hàng, máy chủ có thể trả về dữ liệu cùng các liên kết:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "collection": {
      "href": "/api/orders"
    },
    "https://api.example.com/rels/cancel": {
      "href": "/api/orders/42/cancel"
    }
  }
}
```

Trong ví dụ này:

- `self` trỏ đến chính tài nguyên đơn hàng hiện tại.
- `collection` trỏ đến tập hợp đơn hàng liên quan.
- `https://api.example.com/rels/cancel` biểu thị khả năng điều hướng đến thao tác hủy trong ngữ cảnh hiện tại.

Nếu đơn hàng đã được giao và không thể hủy, máy chủ có thể không cung cấp liên kết hủy. Máy khách có thể dựa vào sự hiện diện của liên kết để quyết định có hiển thị hành động tương ứng hay không. Máy chủ vẫn phải kiểm tra trạng thái và quyền truy cập khi nhận yêu cầu thực hiện thao tác; việc có hay không có liên kết không thay thế kiểm tra bảo mật và nghiệp vụ.

Điểm quan trọng là máy khách sử dụng quan hệ liên kết (*link relation*, thường viết tắt là `rel`) để hiểu ý nghĩa của liên kết, sau đó đi theo `href` mà máy chủ cung cấp. Máy khách không cần tự tạo URL dựa trên ID và cấu trúc đường dẫn đã đoán.

### Quan hệ liên kết là một phần của hợp đồng

Một URL cho biết đích đến, còn quan hệ liên kết cho biết liên kết đó có ý nghĩa gì. Ví dụ:

| Relation | Ý nghĩa thường gặp |
|---|---|
| `self` | Tài nguyên hiện tại |
| `next` | Trang tiếp theo |
| `prev` | Trang trước |
| `collection` hoặc quan hệ tập hợp do API định nghĩa | Tập hợp chứa tài nguyên |
| `payment` | Quan hệ chuẩn cho liên kết thanh toán |
| `https://api.example.com/rels/cancel`, `https://api.example.com/rels/tracking` | Quan hệ mở rộng do API định nghĩa |

Các quan hệ chuẩn có thể dùng tên relation đã được đăng ký. Với quan hệ riêng của ứng dụng, HAL nên dùng URI relation hoặc CURIE; ví dụ `https://api.example.com/rels/cancel` có thể được tài liệu hóa để mô tả thao tác hủy. Các tên ngắn như `cancel` hoặc `tracking` trong bảng trạng thái chỉ là cách gọi dễ đọc. HATEOAS không khiến máy khách tự hiểu mọi nghiệp vụ; máy khách vẫn cần biết cách xử lý những relation mà nó hỗ trợ.

## 3. HATEOAS giúp quy trình phản ánh trạng thái hiện tại

Giả sử đơn hàng có các trạng thái và khả năng sau:

| Trạng thái đơn hàng | Liên kết hoặc hành động có thể được cung cấp |
|---|---|
| Chờ thanh toán | `payment`, `cancel` |
| Đã thanh toán | `tracking`, có thể không còn `cancel` |
| Đang giao | `tracking` |
| Đã giao | `review` |
| Đã hủy | `self`, `collection` |

Bảng chỉ minh họa một quy trình. Hệ thống thực tế quyết định liên kết nào xuất hiện dựa trên trạng thái, chính sách và quyền của người dùng.

Khi trạng thái thay đổi, biểu diễn tài nguyên có thể thay đổi theo. Máy khách nhận được tập liên kết phản ánh những bước tiếp theo mà máy chủ đang công bố. Điều này có ích với các quy trình nhiều bước, có nhánh hoặc thay đổi theo thời gian.

HATEOAS cũng hữu ích cho tài nguyên dạng tập hợp. Một phản hồi danh sách có thể cung cấp các liên kết `self`, `next`, `prev` hoặc liên kết đến bộ lọc. Máy khách chỉ cần theo liên kết được trả về, không phải tự suy ra cách phân trang hay cấu trúc truy vấn cho bước kế tiếp.

## 4. Spring HATEOAS hỗ trợ xây dựng biểu diễn có liên kết

Spring HATEOAS cung cấp các lớp và API để gắn liên kết vào biểu diễn tài nguyên:

| Thành phần | Vai trò |
|---|---|
| `RepresentationModel<T>` | Lớp cơ sở cho mô hình biểu diễn có thể chứa liên kết |
| `EntityModel<T>` | Bọc một đối tượng hoặc một tài nguyên đơn cùng các liên kết |
| `CollectionModel<T>` | Biểu diễn một tập hợp tài nguyên cùng các liên kết |
| `PagedModel<T>` | Biểu diễn tập hợp có thông tin phân trang |
| `Link` | Đại diện cho một liên kết và quan hệ của nó |
| `RepresentationModelAssembler` | Tách logic chuyển đổi đối tượng miền thành mô hình biểu diễn |

Spring HATEOAS còn cung cấp `WebMvcLinkBuilder` để tạo liên kết dựa trên mapping của controller. Nhờ đó, mã tạo liên kết có thể tham chiếu đến phương thức controller thay vì tự nối chuỗi URL.

Ví dụ dưới đây minh họa cách trả về một đơn hàng và chỉ thêm liên kết hủy khi trạng thái hiện tại cho phép:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable Long id) {
        Order order = orderService.findById(id);

        EntityModel<Order> model = EntityModel.of(order);

        model.add(
            linkTo(methodOn(OrderController.class).one(id))
                .withSelfRel()
        );

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel("collection")
        );

        if (order.canBeCancelled()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("https://api.example.com/rels/cancel")
            );
        }

        return model;
    }

    @GetMapping
    CollectionModel<EntityModel<Order>> all() {
        // Trả về tập hợp đơn hàng cùng các liên kết phù hợp.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }

    @PostMapping("/{id}/cancel")
    EntityModel<Order> cancel(@PathVariable Long id) {
        // Thực hiện nghiệp vụ hủy và trả về biểu diễn đơn hàng mới.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}
```

Trong ví dụ:

- `EntityModel.of(order)` tạo mô hình biểu diễn cho một đơn hàng.
- `linkTo(...).withSelfRel()` tạo liên kết `self`.
- `withRel("collection")` gắn relation chuẩn cho liên kết đến tập hợp.
- `withRel("https://api.example.com/rels/cancel")` chỉ được thêm khi đơn hàng có thể hủy.
- `methodOn(...)` tham chiếu đến phương thức controller để Spring HATEOAS xác định URL theo mapping.

Các phương thức `all()` và `cancel()` được rút gọn để tập trung vào cách tạo liên kết. Trong ứng dụng thực tế, nên trả về DTO phù hợp với hợp đồng API và có thể dùng `RepresentationModelAssembler` khi cần chuyển đổi nhiều tài nguyên theo cùng một quy tắc.

## 5. Máy khách sử dụng liên kết như thế nào?

Máy khách thường biết một URI điểm vào của API, chẳng hạn URI gốc được cấu hình trong ứng dụng. Từ điểm vào đó, nó đọc relation cần thiết và đi theo liên kết mà máy chủ cung cấp.

Một luồng xử lý có thể diễn ra như sau:

1. Gọi URI điểm vào để lấy biểu diễn gốc.
2. Đọc liên kết có relation `collection`.
3. Gọi URI trong liên kết đó để lấy danh sách đơn hàng.
4. Chọn một đơn hàng và đọc các liên kết của đơn hàng.
5. Nếu có relation `https://api.example.com/rels/cancel`, hiển thị hành động hủy theo hợp đồng mà máy khách hỗ trợ.
6. Gửi yêu cầu đến URI được cung cấp cho relation đó.

Ví dụ mã giả phía máy khách:

```javascript
const order = await get(orderUrl);
const cancelRelation = "https://api.example.com/rels/cancel";
const cancelLink = order._links[cancelRelation];

if (cancelLink) {
  showCancelAction(async () => {
    await post(cancelLink.href);
  });
}
```

Ví dụ giả định ứng dụng đã biết relation `https://api.example.com/rels/cancel` tương ứng với thao tác POST. Một liên kết HAL cơ bản chủ yếu cung cấp đích đến và metadata của liên kết; nó không tự mô tả đầy đủ HTTP method, cấu trúc request body hay quy tắc xác thực đầu vào. Khi máy khách cần khám phá cả biểu mẫu và dữ liệu đầu vào của thao tác, API cần dùng cơ chế affordance và định dạng biểu diễn hỗ trợ thông tin đó, chẳng hạn HAL-FORMS, đồng thời máy khách phải hỗ trợ định dạng tương ứng.

## 6. Phân biệt HATEOAS, HAL và Spring HATEOAS

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Bản chất | Trả lời câu hỏi |
|---|---|---|
| HATEOAS | Ràng buộc kiến trúc REST | Máy khách khám phá trạng thái và bước điều hướng tiếp theo bằng cách nào? |
| HAL | Định dạng biểu diễn hypermedia | Liên kết và tài nguyên được mã hóa trong JSON theo cấu trúc nào? |
| Spring HATEOAS | Thư viện Java/Spring | Làm thế nào để tạo mô hình tài nguyên, liên kết và affordance trong ứng dụng Spring? |

HAL thường biểu diễn liên kết trong thuộc tính `_links`. Ví dụ ở trên sử dụng cấu trúc HAL để minh họa. Spring HATEOAS hỗ trợ tạo các mô hình có liên kết và nhiều định dạng hypermedia; ứng dụng cần cấu hình hoặc thương lượng media type phù hợp với định dạng mà máy khách sử dụng.

Vì vậy, thêm một trường `url` tùy ý vào JSON chưa tự động tạo thành một API HATEOAS. Điều quan trọng là biểu diễn phải cung cấp các điều khiển hypermedia có quan hệ và ý nghĩa rõ ràng, đồng thời máy khách thực sự sử dụng chúng để điều hướng.

## 7. HATEOAS hỗ trợ tiến hóa API đến đâu?

Khi máy khách dựa vào relation và theo URI do máy chủ trả về, máy chủ có thể thay đổi cấu trúc đường dẫn mà không buộc máy khách phải ghép lại URL, miễn là các relation và ý nghĩa hợp đồng mà máy khách phụ thuộc vẫn được duy trì.

Ví dụ, máy chủ có thể chuyển đường dẫn nội bộ từ `/api/orders/42/cancel` sang một đường dẫn khác. Nếu phản hồi vẫn cung cấp relation `https://api.example.com/rels/cancel` với URI mới và máy khách theo liên kết đó, máy khách không cần biết thay đổi định tuyến.

Tuy nhiên, HATEOAS không loại bỏ mọi dạng phụ thuộc:

- Máy khách vẫn cần hiểu media type và cấu trúc dữ liệu mà nó tiêu thụ.
- Máy khách vẫn cần biết ý nghĩa của các relation mà nó xử lý.
- Thay đổi ngữ nghĩa nghiệp vụ hoặc cấu trúc dữ liệu vẫn có thể ảnh hưởng đến máy khách.
- Máy khách không theo liên kết mà vẫn tự ghép URL sẽ không nhận được lợi ích điều hướng này.
- Liên kết được cung cấp không thay thế xác thực, phân quyền và kiểm tra nghiệp vụ ở phía máy chủ.

HATEOAS giúp giảm sự phụ thuộc vào cách định tuyến và công bố quy trình điều hướng rõ ràng hơn. Nó không phải cơ chế tự động làm cho mọi thay đổi API đều tương thích ngược.

## 8. Khi nào nên áp dụng?

HATEOAS thường hữu ích khi API có một hoặc nhiều đặc điểm sau:

- Quy trình nghiệp vụ có nhiều bước hoặc nhiều nhánh.
- Khả năng thực hiện thao tác phụ thuộc vào trạng thái tài nguyên.
- Có nhiều loại máy khách cần điều hướng theo cùng một hợp đồng.
- API có tài nguyên liên quan, tập hợp, phân trang hoặc bộ lọc.
- Máy chủ cần thay đổi cách định tuyến mà vẫn duy trì relation đã công bố.

Với API nội bộ rất nhỏ, quy trình cố định và chỉ có một máy khách được triển khai đồng bộ, chi phí thiết kế relation, media type và logic điều hướng có thể lớn hơn lợi ích. Việc áp dụng nên dựa trên nhu cầu điều hướng và tiến hóa hợp đồng thực tế.

## 9. Những điểm cần kiểm tra khi thiết kế

Khi thiết kế API có HATEOAS bằng Spring HATEOAS, hãy kiểm tra các điểm sau:

- Mỗi liên kết có relation rõ nghĩa và ổn định.
- Máy khách có thể bắt đầu từ một URI điểm vào và khám phá tài nguyên tiếp theo.
- Liên kết phản ánh trạng thái và ngữ cảnh hiện tại của tài nguyên.
- Các liên kết phân trang hoặc điều hướng tập hợp được cung cấp nhất quán.
- Máy khách sử dụng relation và URI trong phản hồi thay vì tự ghép đường dẫn.
- Nếu cần mô tả HTTP method hoặc dữ liệu đầu vào của thao tác, định dạng hypermedia và affordance được chọn có hỗ trợ thông tin đó.
- Máy chủ vẫn xác thực, phân quyền và kiểm tra điều kiện nghiệp vụ cho mọi yêu cầu.

**Ý chính:** HATEOAS giải quyết bài toán máy khách phải biết trước cấu trúc URL và các bước điều hướng của API. Máy chủ đưa các liên kết có ý nghĩa vào biểu diễn tài nguyên, còn máy khách khám phá và đi theo những liên kết đó để tiếp tục tương tác. Spring HATEOAS giúp triển khai cách tiếp cận này bằng `RepresentationModel`, `EntityModel`, `CollectionModel`, `Link` và các công cụ xây dựng liên kết.
