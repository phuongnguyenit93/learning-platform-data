# Link không có ý nghĩa

## Mục tiêu

Sau bài này, bạn có thể nhận diện link relation không mang ngữ nghĩa rõ ràng, phân biệt relation với URI đích và nhãn hiển thị, chọn relation IANA hoặc relation mở rộng phù hợp, thiết kế vocabulary ổn định cho API Spring HATEOAS, mô tả điều kiện xuất hiện và affordance của link, đồng thời kiểm thử hợp đồng hypermedia để client có thể điều hướng mà không phải đoán ý nghĩa từ URL.

## 1. Vì sao link phải có ý nghĩa?

HATEOAS cho phép client khám phá tài nguyên và khả năng tiếp theo thông qua links trong representation. Một link chỉ hữu ích khi client hiểu được quan hệ mà nó biểu diễn.

Ví dụ representation có một link như sau:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "link1": {
      "href": "/orders/order-42/cancel"
    },
    "action": {
      "href": "/orders/order-42/approve"
    },
    "related": {
      "href": "/orders/order-42/invoice"
    }
  }
}
```

Client nhìn thấy ba URI nhưng không biết:

- `link1` là link đến chính order, collection, hóa đơn hay thao tác hủy?
- `action` có nghĩa là approve, cancel, submit hay một thao tác khác?
- `related` liên quan theo khía cạnh nào?
- Client phải dùng HTTP method nào và gửi body gì?
- Link có xuất hiện cho mọi trạng thái và mọi người dùng không?

Client có thể đoán từ path, nhưng như vậy nó phụ thuộc vào cấu trúc URL nội bộ của server. Nếu route thay đổi, client có thể hỏng dù semantics của tài nguyên không đổi.

Link relation có ý nghĩa giúp client hiểu quan hệ dựa trên hợp đồng hypermedia. URI `href` chỉ ra nơi client có thể đi đến; relation cho biết link đó biểu diễn quan hệ gì.

## 2. Phân biệt relation, href và title

Một link thường có ba khía cạnh cần phân biệt:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Relation (`rel`) | Đây là quan hệ gì với tài nguyên hiện tại? | `self`, `collection`, `cancel` |
| `href` | Client đi đến URI nào? | `/orders/order-42/cancel` |
| `title` | Có nhãn nào hữu ích cho con người? | `Hủy đơn hàng` |

Ví dụ:

```json
{
  "_links": {
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel",
      "title": "Hủy đơn hàng"
    }
  }
}
```

Client máy nên dựa vào relation để nhận diện quan hệ. `title` là nhãn hỗ trợ giao diện hoặc người đọc; nó có thể được bản địa hóa, thay đổi cách viết hoặc rút gọn. Không dùng `title` làm mã máy.

`href` cũng không phải relation. URI có thể thay đổi từ `/orders/order-42/cancel` sang `/order-actions/7f31` trong khi relation `cancel` vẫn giữ nguyên. Client tiếp tục tìm relation đã biết và theo URI mới được server cung cấp.

## 3. Các dạng link không có ý nghĩa rõ ràng

Một số anti-pattern thường xuất hiện khi assembler tạo link:

| Anti-pattern | Vì sao gây vấn đề | Cách cải thiện |
|---|---|---|
| `link1`, `link2`, `link3` | Không thể suy ra quan hệ | Dùng relation có semantics |
| `action`, `operation` | Không nói hành động cụ thể là gì | Dùng relation mô tả khả năng |
| `data`, `resource` | Quá chung để client quyết định bước tiếp theo | Dùng relation chuẩn hoặc extension URI |
| `related` cho mọi liên kết | Không phân biệt quan hệ nghiệp vụ | Dùng relation cụ thể như `invoice`, `customer`, `payment` |
| `doIt`, `process` | Tên mơ hồ, phụ thuộc cách đặt tên nội bộ | Định nghĩa vocabulary ổn định |
| `cancel-order-42` | Relation chứa định danh từng tài nguyên | Relation mô tả loại quan hệ, ID nằm trong URI |
| `getOrder`, `postCancel` | Phơi bày tên method/controller | Công bố semantics độc lập với code |
| `nextPageUrl` như một field tùy ý | Client phải biết schema riêng thay vì link relation | Dùng relation pagination như `next` |

Một relation không có ý nghĩa không chỉ làm representation khó đọc. Nó buộc client viết điều kiện dựa trên path, title hoặc vị trí phần tử. Những phụ thuộc đó làm giảm khả năng thay đổi server mà không cần phát hành client mới.

## 4. Ưu tiên relation đã được chuẩn hóa khi semantics phù hợp

IANA duy trì registry các link relation dùng chung. Nếu một relation đã đăng ký mô tả đúng mối quan hệ, hãy sử dụng relation đó thay vì tạo tên mới.

Một số relation phổ biến:

| Relation | Ý nghĩa khái quát | Ví dụ sử dụng |
|---|---|---|
| `self` | Tài nguyên hiện tại | Link đến representation của order |
| `collection` | Collection chứa tài nguyên | Link từ order đến danh sách orders |
| `item` | Một item trong collection | Link đến một order trong collection |
| `next` | Trang hoặc phần tiếp theo | Trang kế tiếp của collection |
| `prev` | Trang trước | Trang trước của collection |
| `first` | Trang đầu tiên | Trang đầu của kết quả phân trang |
| `last` | Trang cuối cùng | Trang cuối của kết quả phân trang |
| `related` | Tài nguyên có liên quan | Quan hệ liên quan khi không có relation cụ thể hơn |

Chỉ dùng relation chuẩn khi semantics của API thực sự khớp với định nghĩa của relation đó. Không gán `next` cho một thao tác tiếp tục workflow nếu nó không phải quan hệ điều hướng đến phần tiếp theo theo nghĩa đã đăng ký. Không dùng `collection` cho một tài nguyên tổng hợp chỉ vì nó chứa một mảng.

Spring HATEOAS cung cấp các hằng số trong `IanaLinkRelations` cho nhiều relation chuẩn. Với relation thường dùng như `self`, có thể dùng trực tiếp:

```java
model.add(linkTo(methodOn(OrderController.class)
        .getOrder(order.getId()))
        .withSelfRel());
```

Cách này biểu đạt quan hệ `self` bằng API của Spring HATEOAS, thay vì tự viết chuỗi relation.

Nếu dùng relation chuẩn khác, hãy xác nhận tên và semantics trong IANA registry và phiên bản thư viện. Đừng tạo alias nội bộ có cùng tên nhưng ý nghĩa khác.

## 5. Tạo extension relation cho nghiệp vụ riêng

Không phải mọi quan hệ domain đều có trong IANA registry. Các hành động như hủy đơn hàng, duyệt yêu cầu, hoàn tiền hoặc xem hóa đơn có thể cần relation riêng.

Một extension relation nên là URI tuyệt đối, ổn định và có semantics được tài liệu hóa. Ví dụ:

- `https://api.example.com/rels/cancel`
- `https://api.example.com/rels/approve`
- `https://api.example.com/rels/refund`
- `https://api.example.com/rels/invoice`

URI relation không phải URI đích của thao tác. Nó định danh loại quan hệ; `href` trong link mới là URI mà client gọi.

Trong Spring HATEOAS, có thể tạo `LinkRelation`:

```java
import org.springframework.hateoas.LinkRelation;

public final class OrderRelations {

    private OrderRelations() {
    }

    public static final LinkRelation CANCEL =
            LinkRelation.of("https://api.example.com/rels/cancel");

    public static final LinkRelation INVOICE =
            LinkRelation.of("https://api.example.com/rels/invoice");
}
```

Assembler sử dụng relation đó:

```java
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
                order.getId(),
                order.getStatus()
        );

        model.add(linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId()))
                    .withRel(OrderRelations.CANCEL));
        }

        return model;
    }
}
```

Ví dụ giả định `Order`, `OrderModel` và các method trong `OrderController` đã tồn tại. Điều quan trọng là relation `CANCEL` có một định nghĩa dùng chung, còn assembler xây `href` từ mapping của controller.

Không tạo relation động như `cancel-order-42` hoặc `cancel-order-43`. Relation mô tả loại khả năng, còn định danh order thuộc về URI target.

## 6. Tài liệu hóa relation như một phần vocabulary API

Một relation extension cần có tài liệu để client biết semantics. Tài liệu nên giải thích ít nhất:

- URI relation và tên ngắn dùng trong tài liệu.
- Tài nguyên nguồn mà relation xuất hiện.
- Tài nguyên hoặc endpoint đích.
- Ý nghĩa nghiệp vụ của quan hệ.
- Điều kiện relation được công bố hoặc bị ẩn.
- HTTP method và request media type nếu link đại diện một hành động.
- Response thành công và các lỗi có thể xảy ra.
- Chính sách tương thích khi semantics thay đổi.

Ví dụ registry relation cho order:

| Relation URI | Tài nguyên nguồn | Target | Điều kiện công bố |
|---|---|---|---|
| `https://api.example.com/rels/cancel` | Order | Endpoint yêu cầu hủy | Order còn ở trạng thái có thể hủy và principal có quyền |
| `https://api.example.com/rels/invoice` | Order | Invoice resource | Hóa đơn đã được phát hành và principal có quyền xem |
| `https://api.example.com/rels/approve` | Approval request | Endpoint phê duyệt | Request đang chờ và principal có quyền phê duyệt |

Có thể công bố trang tài liệu tại chính URI relation. Khi client hoặc developer mở URI, server có thể trả nội dung mô tả relation hoặc chuyển đến tài liệu tương ứng. Đây là cách giúp extension relation dễ khám phá và duy trì lâu dài.

Nếu relation URI không được phục vụ trực tiếp, vẫn cần một tài liệu API ổn định có thể tra cứu URI đó. Không đổi URI relation chỉ vì tài liệu được chuyển sang hệ thống docs mới.

## 7. Relation phải ổn định khi URI endpoint thay đổi

Relation mô tả semantics, không mô tả cấu trúc route.

Giả sử ban đầu API cung cấp:

```json
{
  "_links": {
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel"
    }
  }
}
```

Sau khi hệ thống tái cấu trúc endpoint:

```json
{
  "_links": {
    "https://api.example.com/rels/cancel": {
      "href": "/order-actions/act-91"
    }
  }
}
```

Client vẫn tìm relation `https://api.example.com/rels/cancel` và theo `href` mới. Không cần phát hành client mới chỉ vì route thay đổi.

Ngược lại, nếu semantics của thao tác thay đổi đáng kể, ví dụ link trước đây thực hiện hủy ngay lập tức nhưng link mới chỉ mở một quy trình yêu cầu phê duyệt, hãy đánh giá xem relation cũ còn chính xác không. Nếu không, định nghĩa relation mới, cập nhật tài liệu và duy trì tương thích theo kế hoạch versioning.

Đừng dùng cùng một relation cho hai hành vi khác nhau tùy endpoint hoặc phiên bản mà không có quy tắc rõ ràng. Client cần có thể hiểu relation nhất quán ở mọi nơi nó xuất hiện.

## 8. Không dùng relation để thay thế mô tả HTTP action

Một relation như `cancel` nói client biết đây là khả năng hủy. Tuy nhiên, một HAL link đơn giản chỉ có `href` không nhất thiết mô tả đầy đủ:

- HTTP method cần gọi.
- Request body có cần gửi không.
- Request body dùng media type nào.
- Những field nào bắt buộc.
- Validation hoặc giá trị được phép.

Ví dụ link:

```json
{
  "_links": {
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel"
    }
  }
}
```

Relation giúp client hiểu mục đích, nhưng nếu thao tác yêu cầu `POST` và một body xác nhận, API cần công bố affordance hoặc form template tương ứng. Có thể dùng HAL-FORMS hoặc affordance metadata của Spring HATEOAS để mô tả method, content type và input properties.

Ví dụ HAL-FORMS minh họa:

```json
{
  "_links": {
    "self": {
      "href": "/orders/order-42"
    }
  },
  "_templates": {
    "cancel": {
      "title": "Yêu cầu hủy đơn hàng",
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "prompt": "Lý do hủy",
          "required": true
        }
      ]
    }
  }
}
```

Tên template `cancel` và cấu trúc trên là một phần hợp đồng HAL-FORMS do API công bố. Cần tài liệu hóa template, field và semantics; không suy ra request body chỉ từ relation.

Nếu endpoint chỉ là điều hướng GET đến một tài nguyên mô tả hoặc form, một HAL link có thể đủ. Nếu link biểu diễn thao tác ghi, hãy bảo đảm client có metadata cần thiết để thực hiện đúng request.

## 9. Tránh relation quá chung như related hoặc action

`related` là một relation có nghĩa trong registry, nhưng nghĩa của nó vẫn rộng. Nếu client cần phân biệt hóa đơn, khách hàng và thanh toán, dùng `related` cho tất cả sẽ không giúp client biết phải chọn link nào.

Ví dụ mơ hồ:

```json
{
  "_links": {
    "related": [
      { "href": "/orders/order-42/invoice" },
      { "href": "/customers/customer-7" },
      { "href": "/payments/payment-5" }
    ]
  }
}
```

Client phải đoán target dựa trên URI hoặc thứ tự trong mảng.

Representation có semantics cụ thể hơn:

```json
{
  "_links": {
    "https://api.example.com/rels/invoice": {
      "href": "/orders/order-42/invoice"
    },
    "https://api.example.com/rels/customer": {
      "href": "/customers/customer-7"
    },
    "https://api.example.com/rels/payment": {
      "href": "/payments/payment-5"
    }
  }
}
```

Có thể dùng relation `related` khi quan hệ thật sự chỉ mang ý nghĩa “có liên quan” và client không cần phân loại sâu hơn. Nếu client phải thực hiện quyết định dựa trên loại quan hệ, hãy định nghĩa relation cụ thể.

Tương tự, `action` không nói hành động gì. Hãy dùng `approve`, `cancel`, `refund` hoặc URI relation có vocabulary rõ ràng.

## 10. Không để nhãn giao diện quyết định semantics

Một anti-pattern khác là dùng tên hiển thị làm relation:

```json
{
  "_links": {
    "Hủy đơn hàng ngay": {
      "href": "/orders/order-42/cancel"
    }
  }
}
```

Nhãn hiển thị có thể thay đổi theo ngôn ngữ, thiết kế UX hoặc cách viết. Client không nên phải so sánh chuỗi tiếng Việt để tìm một thao tác.

Hãy tách relation máy đọc được và title dành cho người dùng:

```json
{
  "_links": {
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel",
      "title": "Hủy đơn hàng ngay"
    }
  }
}
```

Nếu client cần giao diện đa ngôn ngữ, có thể cung cấp `title` theo ngôn ngữ hoặc metadata hiển thị phù hợp. Relation vẫn giữ ổn định, độc lập với bản dịch.

## 11. Dùng CURIE để rút gọn extension relation trong HAL

HAL hỗ trợ CURIE để biểu diễn relation URI dài bằng prefix. Ví dụ:

```json
{
  "_links": {
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "acme:cancel": {
      "href": "/orders/order-42/cancel"
    },
    "acme:invoice": {
      "href": "/orders/order-42/invoice"
    }
  }
}
```

Client có thể mở rộng `acme:cancel` dựa trên CURIE template thành URI relation đầy đủ. CURIE chỉ rút gọn cách biểu diễn relation; nó không làm thay đổi semantics hoặc URI định danh gốc.

Trong Spring HATEOAS, `CurieProvider` và `DefaultCurieProvider` có thể được cấu hình để công bố prefix cho relation extension. Khi dùng CURIE:

- Prefix phải ổn định và được công bố trong response.
- Template phải mở rộng thành URI relation đúng.
- Không dùng cùng prefix cho hai vocabulary khác nhau.
- Tài liệu vẫn cần giải thích semantics của relation.
- Client phải xử lý relation đầy đủ hoặc CURIE theo quy ước HAL mà nó hỗ trợ.

Không dùng CURIE để che giấu một vocabulary chưa được định nghĩa. Việc rút ngắn tên không làm relation trở nên có ý nghĩa hơn.

## 12. Quan hệ có điều kiện phải được tài liệu hóa

Một số link chỉ xuất hiện khi trạng thái nghiệp vụ hoặc quyền truy cập cho phép. Đây là hành vi hợp lệ của hypermedia, nhưng điều kiện cần rõ ràng.

Ví dụ:

| Relation | Điều kiện trạng thái | Điều kiện quyền |
|---|---|---|
| `cancel` | Order ở trạng thái `PENDING` hoặc `CONFIRMED` | Principal có quyền hủy |
| `invoice` | Hóa đơn đã được phát hành | Principal có quyền xem hóa đơn |
| `approve` | Request đang `WAITING_FOR_APPROVAL` | Principal có authority phê duyệt |
| `refund` | Payment đã capture và chưa hoàn tiền | Principal có quyền hoàn tiền |

Client cần hiểu rằng link tùy chọn có thể vắng mặt. Không nên xem absence của link là lỗi serialization nếu điều kiện công bố không thỏa mãn.

Ngược lại, nếu relation được cam kết luôn có cho một loại resource nhưng assembler vô tình bỏ quên, đó là lỗi hợp đồng. Tài liệu phải phân biệt link bắt buộc với link tùy chọn và mô tả điều kiện cho từng loại.

Ẩn link không thay thế authorization. Client có thể giữ URI cũ hoặc tự tạo request; endpoint đích vẫn phải kiểm tra quyền và trạng thái tại thời điểm request.

## 13. Thiết kế một relation catalog

Với API có nhiều resource và hành động, nên duy trì relation catalog để tránh tên trùng, nghĩa không nhất quán hoặc relation chỉ được định nghĩa trong một assembler.

Một mục catalog có thể dùng cấu trúc:

| Thuộc tính | Nội dung |
|---|---|
| Relation URI | URI ổn định định danh relation |
| Short name | Tên ngắn để dùng trong trao đổi nội bộ |
| Description | Semantics của quan hệ |
| Source resource | Loại representation có thể chứa link |
| Target | Loại tài nguyên hoặc endpoint đích |
| Method / affordance | GET, POST, PATCH... và request schema nếu là action |
| Availability | Điều kiện trạng thái, quyền và feature |
| Errors | Các status/problem type có thể trả về |
| Compatibility | Quy tắc duy trì hoặc thay đổi semantics |

Ví dụ catalog:

| Relation URI | Short name | Source → target | Semantics |
|---|---|---|---|
| `https://api.example.com/rels/cancel` | `cancel` | Order → Cancel operation | Yêu cầu hủy order hiện tại |
| `https://api.example.com/rels/invoice` | `invoice` | Order → Invoice | Truy cập hóa đơn đã phát hành |
| `https://api.example.com/rels/customer` | `customer` | Order → Customer | Truy cập customer sở hữu order |
| `https://api.example.com/rels/approve` | `approve` | Approval → Approval operation | Phê duyệt yêu cầu đang chờ |

Relation catalog có thể được quản lý cùng tài liệu API và review trong thay đổi hợp đồng. Khi thêm relation mới, cần xem client cũ có bỏ qua relation chưa biết an toàn hay không. Khi thay đổi semantics, cần đánh giá versioning và migration.

## 14. Kiểm thử relation contract bằng MockMvc

Test cần kiểm tra relation có ý nghĩa xuất hiện đúng nơi, trỏ đến target đúng và biến mất khi điều kiện không còn đúng.

Ví dụ người dùng được phép hủy nhận relation:

```java
@Test
@WithMockUser(authorities = "ORDER_CANCEL")
void exposesCancelRelationWhenOrderCanBeCancelled() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                    "$._links['https://api.example.com/rels/cancel'].href"
            ).exists());
}
```

Người chỉ có quyền đọc không nhận relation hủy:

```java
@Test
@WithMockUser(authorities = "ORDER_READ")
void omitsCancelRelationForReadOnlyPrincipal() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                    "$._links['https://api.example.com/rels/cancel']"
            ).doesNotExist());
}
```

Kiểm tra self relation không bị thay bằng URI hard-code hoặc relation tùy ý:

```java
@Test
void publishesSelfRelationForCurrentOrder() throws Exception {
    mockMvc.perform(get("/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href")
                    .value(endsWith("/orders/" + orderId)));
}
```

Các ví dụ giả định test context có fixture order, service, security configuration và assembler phù hợp. Nếu API dùng CURIE, JSON key của relation extension có thể là `acme:cancel`; assertion phải khớp representation thực tế và cần test rằng CURIE template được công bố.

## 15. Kiểm thử semantics, không chỉ kiểm tra link tồn tại

Một test chỉ assert `_links` tồn tại có thể bỏ qua việc relation sai. Ví dụ link `/orders/42/cancel` xuất hiện dưới relation `invoice` vẫn vượt qua một assertion quá chung.

Với mỗi relation quan trọng, test nên xác nhận:

1. Relation key chính xác.
2. `href` trỏ đến đúng loại target.
3. `title` nếu có chỉ là metadata hiển thị, không phải định danh relation.
4. Link xuất hiện khi điều kiện nghiệp vụ thỏa mãn.
5. Link bị ẩn khi trạng thái hoặc quyền không cho phép.
6. Affordance hoặc form template mô tả đúng HTTP method và request media type nếu có thao tác ghi.
7. Endpoint đích vẫn thực thi authorization độc lập.

Có thể dùng JSONPath để kiểm tra quan hệ cụ thể:

```java
.andExpect(jsonPath(
        "$._links['https://api.example.com/rels/invoice'].href"
).value(endsWith("/invoice")));
```

Với một relation catalog lớn, có thể tạo contract test data-driven từ registry của dự án. Mỗi relation trong catalog cần ít nhất một test xác nhận representation và một test cho điều kiện không xuất hiện nếu nó là optional relation.

## 16. Những lỗi thường gặp

**Dùng `link1` hoặc `action`.** Client không biết quan hệ nào được biểu diễn. Chọn relation chuẩn hoặc URI extension có semantics.

**Dùng URL path để suy ra ý nghĩa.** Client phụ thuộc vào route nội bộ. Dùng relation để định danh quan hệ và `href` để điều hướng.

**Dùng `title` làm relation.** Nhãn có thể đổi hoặc được dịch. Giữ relation máy đọc được ổn định và dùng title cho con người.

**Dùng `related` cho mọi tài nguyên.** Client không thể phân biệt hóa đơn, khách hàng và thanh toán. Dùng relation domain cụ thể khi semantics cần phân biệt.

**Đặt relation chứa ID của resource.** Vocabulary phình to theo từng instance. Để ID trong `href`, relation chỉ mô tả loại quan hệ.

**Đổi nghĩa relation mà giữ nguyên URI.** Client cũ có thể thực hiện sai hành vi. Giữ semantics ổn định hoặc định nghĩa relation mới và lập kế hoạch chuyển đổi.

**Dùng relation `cancel` nhưng không mô tả request.** Client biết mục đích nhưng không biết method hoặc body. Công bố affordance hoặc HAL-FORMS template.

**Công bố link không có điều kiện rõ ràng.** Client không hiểu vì sao link lúc có lúc không. Tài liệu hóa state và authorization condition.

**Cho rằng link bị ẩn là đủ bảo mật.** Client có thể gọi URI cũ trực tiếp. Endpoint phải kiểm tra quyền và trạng thái lại.

**Tạo CURIE nhưng không công bố vocabulary.** Prefix rút gọn một relation vẫn chưa rõ nghĩa. Duy trì relation catalog và profile/docs ổn định.

**Chỉ kiểm tra link tồn tại.** Link có thể mang relation sai hoặc trỏ sai target. Test relation, href, condition và affordance.

## 17. Nguyên tắc thiết kế

- Xem relation là một phần hợp đồng công khai của API.
- Ưu tiên IANA relation khi semantics đã được định nghĩa phù hợp.
- Dùng URI extension ổn định cho quan hệ nghiệp vụ riêng.
- Phân biệt relation, `href` và `title`.
- Không dùng relation mơ hồ như `link1`, `action` hoặc `data`.
- Không suy ra semantics từ URL hoặc tên method nội bộ.
- Duy trì relation catalog và tài liệu cho extension relation.
- Giữ relation ổn định khi route thay đổi nhưng semantics không đổi.
- Tạo relation mới khi semantics thay đổi đáng kể.
- Dùng affordance hoặc HAL-FORMS để mô tả method và request body của action.
- Tài liệu hóa điều kiện công bố link theo trạng thái và quyền.
- Kiểm thử relation key, target, availability và endpoint authorization.

## Kết luận

Link không có ý nghĩa khiến client phải đoán từ URL, title hoặc vị trí trong JSON, làm hợp đồng hypermedia phụ thuộc vào chi tiết triển khai. Trong Spring HATEOAS, hãy dùng relation chuẩn khi phù hợp và URI extension ổn định cho vocabulary riêng; giữ semantics tách biệt khỏi `href` và `title`; mô tả điều kiện xuất hiện cùng affordance của thao tác. Relation catalog và MockMvc contract tests giúp phát hiện link sai nghĩa, sai target hoặc xuất hiện không đúng ngữ cảnh. Khi relation được thiết kế rõ ràng, client có thể điều hướng theo hợp đồng API ngay cả khi route và cấu trúc nội bộ thay đổi.

## Tài liệu tham khảo

- [IANA Link Relation Types Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 6573 – The Item and Collection Link Relations](https://www.rfc-editor.org/rfc/rfc6573.html)
- [Spring HATEOAS Reference – Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links)
- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [JSON Hypertext Application Language (HAL) – Internet-Draft](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal-11)

