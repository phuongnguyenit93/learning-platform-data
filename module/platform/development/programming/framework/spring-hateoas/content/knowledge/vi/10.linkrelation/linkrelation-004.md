# Relation mở rộng

Trong hypermedia, **link relation** (quan hệ liên kết) cho biết một link có ý nghĩa gì đối với tài nguyên hiện tại. `self` thường chỉ chính tài nguyên; `next` chỉ trang kế tiếp; `customer` có thể chỉ khách hàng liên quan. Khi API cần công bố một quan hệ nghiệp vụ riêng như phê duyệt đơn hàng, hủy đặt chỗ hoặc yêu cầu hoàn tiền, có thể định nghĩa một **extension relation** (relation mở rộng).

Spring HATEOAS biểu diễn quan hệ này bằng kiểu `LinkRelation`. Khi tạo link, ứng dụng gắn relation vào `Link`; khi serialize thành HAL JSON, relation trở thành tên khóa bên trong `_links`. Client dựa vào relation để hiểu ý nghĩa của link và dựa vào `href` để điều hướng tới đích.

## Relation chuẩn và relation mở rộng

Relation chuẩn được đăng ký trong IANA Link Relation Type Registry. Những tên quen thuộc như `self`, `next`, `prev`, `first`, `last`, `collection`, `item`, `related` và `search` có ngữ nghĩa được công bố để nhiều hệ thống có thể hiểu thống nhất.

Khi quan hệ cần thiết chưa có trong registry, API có thể định nghĩa một extension relation. Theo quy ước của Web Linking, extension relation được nhận diện bằng một URI tuyệt đối. URI đó nên ổn định và nên trỏ tới tài liệu giải thích ý nghĩa, điều kiện sử dụng và hành vi mà relation biểu thị.

Ví dụ:

| Relation | Loại | Ý nghĩa |
| --- | --- | --- |
| `self` | Relation chuẩn | Tài nguyên hiện tại |
| `next` | Relation chuẩn | Trang kế tiếp trong một chuỗi điều hướng |
| `https://api.example.com/rels/approve` | Relation mở rộng | Điểm vào để yêu cầu phê duyệt tài nguyên |
| `https://api.example.com/rels/cancel` | Relation mở rộng | Điểm vào để yêu cầu hủy tài nguyên |

Không nên dùng một từ ngắn như `approve` hoặc `cancel` làm relation tùy chỉnh trong một API công khai có thể được nhiều hệ thống tích hợp, vì tên đó không tự xác định namespace và ngữ nghĩa dùng chung. URI mở rộng giúp tránh xung đột tên và cho phép API sở hữu tài liệu định nghĩa relation. Tên miền trong ví dụ chỉ minh họa; khi triển khai, hãy dùng miền do tổ chức kiểm soát.

## Phân biệt relation với href và affordance

Một link thường có ít nhất hai thành phần quan trọng:

- **Relation (`rel`):** mô tả mối quan hệ hoặc mục đích của link.
- **Href:** URI đích mà client có thể điều hướng tới.

Ví dụ, `rel="https://api.example.com/rels/approve"` cho biết link biểu thị hành động phê duyệt; `href="/orders/42/approval"` cho biết nơi gửi request hoặc điều hướng tới. Server có thể đổi đường dẫn đích mà không cần đổi relation nếu ý nghĩa tương tác vẫn giữ nguyên.

Relation tự nó không mô tả đầy đủ HTTP method, request body, kiểu dữ liệu hoặc các trường bắt buộc. Nếu client cần biết một thao tác dùng `POST` hay `PATCH`, hoặc cần gửi nội dung nào, API có thể gắn **affordance** với link và dùng media type có khả năng biểu diễn thông tin tương tác, chẳng hạn HAL-FORMS. Relation định danh ý nghĩa; affordance mô tả cách tương tác chi tiết hơn.

## `LinkRelation` trong Spring HATEOAS

Spring HATEOAS cung cấp `LinkRelation` như một value object đại diện cho relation type. Có thể tạo relation mở rộng bằng `LinkRelation.of(...)`. Với relation chuẩn, dùng các hằng số trong `IanaLinkRelations` để tránh tự gõ tên và giữ ngữ nghĩa rõ ràng.

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

class OrderLinks {

    static final LinkRelation APPROVE =
        LinkRelation.of("https://api.example.com/rels/approve");

    Link selfLink(String uri) {
        return Link.of(uri, IanaLinkRelations.SELF);
    }

    Link approveLink(String uri) {
        return Link.of(uri, APPROVE);
    }
}
```

Trong ví dụ, `IanaLinkRelations.SELF` đại diện relation chuẩn `self`, còn `APPROVE` là relation do API định nghĩa. Khai báo relation ở một nơi giúp các controller, assembler và processor dùng cùng một giá trị, tránh sai khác do viết chuỗi ở nhiều chỗ.

## Gắn relation mở rộng vào link controller

Giả sử đơn hàng ở trạng thái chờ có thể được phê duyệt. Controller công bố endpoint phê duyệt:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderPolicy orderPolicy;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderPolicy orderPolicy,
                    OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.orderPolicy = orderPolicy;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        Order order = orderService.findById(id);
        EntityModel<OrderRepresentation> model = assembler.toModel(order);

        if (orderPolicy.canApprove(order)) {
            model.add(linkTo(methodOn(OrderController.class).approve(id))
                .withRel(OrderLinks.APPROVE));
        }

        return model;
    }

    @PostMapping("/{id}/approval")
    ResponseEntity<Void> approve(@PathVariable Long id) {
        orderService.approve(id);
        return ResponseEntity.noContent().build();
    }
}
```

`OrderRepresentation`, `OrderService`, `OrderPolicy` và `assembler` là các thành phần nghiệp vụ/biểu diễn giả định của ứng dụng. Link chỉ được thêm khi chính sách cho phép phê duyệt. `methodOn(...)` giúp Spring HATEOAS suy ra URI từ mapping của controller; lời gọi mô phỏng này không thực thi phương thức `approve`.

Trong một ứng dụng lớn, có thể đặt phần tạo link trong `RepresentationModelAssembler` nếu relation gắn chặt với representation của đơn hàng, hoặc trong `RepresentationModelProcessor` nếu đó là quy tắc hậu xử lý dùng chung cho một kiểu model. Dù đặt ở đâu, hãy dùng chung hằng số `LinkRelation` để quan hệ luôn nhất quán.

## Relation mở rộng trong HAL JSON

Với HAL JSON, các link được đặt dưới `_links`, và relation là tên khóa. Một representation có thể trông như sau:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "https://api.example.com/rels/approve": {
      "href": "https://api.example.com/orders/42/approval"
    }
  }
}
```

Client tìm relation URI `https://api.example.com/rels/approve` để biết tài nguyên hiện tại có link phê duyệt. Client không cần tự suy luận URL từ `id` hoặc đoán route `/approval`. Nếu relation không xuất hiện, client nên hiểu rằng API không công bố tương tác đó trong representation hiện tại.

## Rút gọn URI relation bằng CURIE trong HAL

URI mở rộng có thể dài. HAL hỗ trợ **CURIE** (Compact URI) để rút gọn cách viết relation URI trong `_links`, trong khi vẫn giữ namespace và ý nghĩa của relation. Một CURIE khai báo prefix và URI template; client có thể mở rộng tên viết tắt về URI đầy đủ.

```json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "ex:approve": {
      "href": "https://api.example.com/orders/42/approval"
    }
  }
}
```

Ở đây, `ex:approve` là dạng rút gọn của relation URI được tạo bằng cách thay biến `{rel}` trong CURIE template bằng `approve`. CURIE chỉ giúp representation ngắn gọn hơn; nó không tạo ra một relation mới hoặc thay đổi ngữ nghĩa của URI gốc. Client cần hỗ trợ quy tắc CURIE của HAL để giải mã relation rút gọn.

Spring HATEOAS có cơ chế `CurieProvider` cho ứng dụng HAL muốn công bố CURIE. Khi bật CURIE, cần cấu hình prefix và URI template nhất quán với các relation mở rộng mà ứng dụng phát ra. Nếu không có nhu cầu rút gọn, dùng URI relation đầy đủ sẽ đơn giản hơn cho cả server lẫn client.

## Relation cho tài nguyên nhúng và collection

Trong Spring HATEOAS, relation của link và relation dùng để đặt tên tài nguyên nhúng có liên quan nhưng không hoàn toàn đồng nhất. `LinkRelation` gắn với một `Link`; `@Relation(itemRelation = ..., collectionRelation = ...)` giúp xác định tên relation của item và collection khi representation được nhúng, chẳng hạn dưới `_embedded` trong HAL.

```java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderRepresentation(
    Long id,
    String status
) {}
```

Trong ví dụ, `order` và `orders` điều khiển tên item/collection trong representation nhúng. Nếu muốn một link dẫn tới collection đơn hàng từ tài nguyên khác, hãy tạo `Link` với relation thích hợp. Không nên nhầm tên collection trong `_embedded` với URI đích của link.

## Quy tắc thiết kế extension relation

- **Định nghĩa một ý nghĩa rõ ràng:** relation phải mô tả một loại quan hệ hoặc tương tác có thể giải thích độc lập với URL hiện tại.
- **Dùng URI tuyệt đối cho relation mở rộng:** chọn miền do tổ chức kiểm soát và duy trì URI ổn định.
- **Công bố tài liệu:** mô tả mục đích, điều kiện xuất hiện, đích đến và cách client nên sử dụng relation.
- **Giữ ngữ nghĩa ổn định:** có thể đổi `href` khi route thay đổi, nhưng không âm thầm đổi ý nghĩa của relation.
- **Không dùng relation làm cơ chế phân quyền:** link có thể vắng mặt trong response, nhưng endpoint đích vẫn phải xác thực và kiểm tra quyền.
- **Không nhồi HTTP method vào tên relation:** relation nên diễn đạt ý nghĩa nghiệp vụ; affordance hoặc tài liệu media type mô tả chi tiết request.
- **Dùng relation chuẩn khi đã có:** không tạo extension mới cho một ý nghĩa đã được registry chuẩn mô tả phù hợp.
- **Kiểm tra client thực tế:** bảo đảm client nhận biết relation đầy đủ hoặc giải mã CURIE đúng cách.

## Kiểm thử relation mở rộng

Kiểm thử nên xác nhận relation được serialize đúng và chỉ xuất hiện khi điều kiện nghiệp vụ thỏa mãn. Có thể kiểm tra trực tiếp model ở unit test:

```java
import static org.assertj.core.api.Assertions.assertThat;

Link approve = model.getLink(OrderLinks.APPROVE).orElseThrow();

assertThat(approve.getRel()).isEqualTo(OrderLinks.APPROVE);
assertThat(approve.getHref()).endsWith("/orders/42/approval");
```

Ở integration test, kiểm tra response HAL có khóa relation URI mong muốn trong `_links`, `href` đúng và relation vắng mặt khi đơn hàng không thể phê duyệt. Nếu dùng CURIE, kiểm tra cả entry `curies` và relation rút gọn mà client sẽ nhận.

Relation mở rộng giúp Spring HATEOAS công bố những quan hệ nghiệp vụ mà relation chuẩn chưa mô tả. Khi dùng `LinkRelation` nhất quán, định nghĩa URI có tài liệu và kiểm thử response thực tế, client có thể khám phá tương tác theo ý nghĩa ổn định trong khi server vẫn linh hoạt thay đổi cấu trúc URL nội bộ.
