# Relation chuẩn

## Mục tiêu

Sau bài này, bạn có thể giải thích vai trò của link relation trong hypermedia, nhận diện các relation chuẩn thường dùng, phân biệt relation chuẩn với relation mở rộng, tạo link bằng `IanaLinkRelations` và `LinkRelation` trong Spring HATEOAS, đồng thời kiểm thử relation như một phần của hợp đồng API.

## 1. Link relation là gì?

Một link trong REST hypermedia thường có hai thông tin cốt lõi:

- **Relation (rel):** mô tả mối quan hệ hoặc ý nghĩa của liên kết đối với tài nguyên hiện tại.
- **href:** URI reference chỉ đích mà client có thể truy cập.

Ví dụ HAL:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "collection": {
      "href": "/orders"
    },
    "payment": {
      "href": "/orders/42/payment"
    }
  }
}
```

Trong ví dụ, `self`, `collection` và `payment` là relation; các giá trị `href` là đích liên kết. Relation trả lời câu hỏi “liên kết này có ý nghĩa gì?”, còn href trả lời “đi đến đâu?”.

Relation không phải tên phương thức Java, HTTP method hay một phần bắt buộc của URL. Relation `payment` có thể trỏ đến một tài nguyên thanh toán, nhưng tên này không tự nói client phải dùng GET hay POST. Nếu client cần biết cách gửi dữ liệu hoặc method nào được hỗ trợ, API cần cung cấp thêm affordance hoặc metadata của định dạng hypermedia.

## 2. Vì sao nên dùng relation chuẩn?

Relation chuẩn được đăng ký trong IANA Link Relation Type Registry và có ý nghĩa được mô tả công khai. Khi server và client cùng hiểu một relation chuẩn, chúng có thể phối hợp mà không phải tự định nghĩa lại ý nghĩa của liên kết đó.

Ví dụ:

- `self` xác định URI của chính tài nguyên hiện tại.
- `next` và `prev` điều hướng giữa các phần hoặc trang liền kề.
- `first` và `last` trỏ đến phần đầu và phần cuối của một tập hợp có thể điều hướng.
- `collection` liên kết đến collection chứa tài nguyên.
- `item` liên kết đến một phần tử trong collection.
- `up` dẫn đến tài nguyên cấp trên trong cấu trúc phân cấp.
- `related` chỉ một tài nguyên có liên quan.
- `describedby` dẫn đến tài liệu mô tả tài nguyên hoặc liên kết.
- `alternate` cung cấp một biểu diễn hoặc cách truy cập thay thế.
- `profile` chỉ profile mô tả semantics của tài nguyên.
- `search` chỉ tài nguyên hoặc biểu mẫu hỗ trợ tìm kiếm.

Đây là các ví dụ thường gặp, không phải toàn bộ registry. Khi cần chọn relation chuẩn cho một tình huống cụ thể, hãy đối chiếu ý nghĩa trong IANA registry thay vì chọn tên chỉ vì nó nghe có vẻ phù hợp.

## 3. Một số relation thường gặp trong API

| Relation | Ý nghĩa sử dụng | Ví dụ đích |
|---|---|---|
| `self` | Chính tài nguyên hiện tại | `/orders/42` |
| `collection` | Collection chứa tài nguyên | `/orders` |
| `item` | Một phần tử của collection | `/orders/42` |
| `first` | Phần đầu tiên của tập hợp phân trang | `/orders?page=0` |
| `prev` | Trang trước | `/orders?page=1` |
| `next` | Trang tiếp theo | `/orders?page=3` |
| `last` | Trang cuối | `/orders?page=5` |
| `up` | Tài nguyên cấp trên | `/customers/7` |
| `related` | Tài nguyên liên quan | `/customers/7` |
| `describedby` | Tài liệu mô tả | `/docs/order-schema` |
| `search` | Điểm truy cập tìm kiếm | `/orders{?status}` |
| `alternate` | Biểu diễn thay thế | `/orders/42.pdf` |

Một số relation chỉ có ý nghĩa trong ngữ cảnh nhất định. Ví dụ, `next` chỉ hữu ích khi có một chuỗi kết quả hoặc trang có thể điều hướng; không nên công bố link này ở trang cuối. `collection` và `item` giúp client hiểu quan hệ giữa collection và phần tử, nhưng không thay thế nội dung hoặc metadata phân trang.

## 4. Dùng IanaLinkRelations trong Spring HATEOAS

Spring HATEOAS cung cấp lớp `IanaLinkRelations` chứa các hằng số cho những relation chuẩn. Dùng các hằng số này giúp tránh gõ sai tên relation và làm rõ ý định trong code.

Ví dụ:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42")
        .withRel(IanaLinkRelations.SELF);

Link next = Link.of("/orders?page=1")
        .withRel(IanaLinkRelations.NEXT);

Link previous = Link.of("/orders?page=0")
        .withRel(IanaLinkRelations.PREV);
```

Có thể kết hợp với link builder để href lấy từ mapping controller:

```java
Link self = linkTo(methodOn(OrderController.class)
        .getOrder(orderId))
        .withRel(IanaLinkRelations.SELF);

Link collection = linkTo(methodOn(OrderController.class)
        .getOrders())
        .withRel(IanaLinkRelations.COLLECTION);
```

Nếu dùng các phương thức tiện ích, `withSelfRel()` là cách ngắn gọn để tạo relation `self`. Với các relation chuẩn khác, có thể truyền hằng số tương ứng cho `withRel(...)`.

Các import cho ví dụ link builder:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
```

Dùng `IanaLinkRelations` khi relation có trong registry. Nếu relation không có trong registry và mang ý nghĩa riêng của domain, hãy định nghĩa relation mở rộng có chủ đích.

## 5. Relation chuẩn trong assembler và controller

Giả sử API đơn hàng có endpoint đọc một đơn hàng và endpoint liệt kê các đơn hàng. Assembler có thể thêm relation chuẩn để client điều hướng:

```java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        Link self = linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel();

        Link collection = linkTo(methodOn(OrderController.class)
                .getOrders())
                .withRel(IanaLinkRelations.COLLECTION);

        return EntityModel.of(order, self, collection);
    }
}
```

Với collection có phân trang, các relation `first`, `prev`, `next` và `last` thường được tạo dựa trên thông tin trang. Trong Spring Data MVC, `PagedResourcesAssembler` có thể tạo các link phân trang và metadata cho `PagedModel`, giúp tránh tự tính URL và relation ở từng controller.

Client có thể theo `collection` để quay về danh sách hoặc theo `self` để truy cập lại tài nguyên hiện tại. Khi trang hiện tại không phải trang đầu hoặc trang cuối, response có thể công bố `prev` hoặc `next` tương ứng.

## 6. Relation chuẩn và relation mở rộng

Không phải mọi khái niệm nghiệp vụ đều có relation chuẩn. Ví dụ, API đơn hàng có thể cần các quan hệ như:

- `payment`: thông tin hoặc tài nguyên thanh toán của đơn hàng.
- `invoice`: hóa đơn của đơn hàng.
- `shipment`: thông tin giao hàng.
- `cancel`: điểm truy cập hành động hủy.

Nếu không có relation chuẩn phù hợp, ứng dụng có thể định nghĩa relation mở rộng. Trong Spring HATEOAS, dùng `LinkRelation.of(...)` để tạo relation tùy chỉnh:

```java
import org.springframework.hateoas.LinkRelation;

Link payment = linkTo(methodOn(PaymentController.class)
        .getPayment(order.getId()))
        .withRel(LinkRelation.of("payment"));

Link invoice = linkTo(methodOn(InvoiceController.class)
        .getInvoice(order.getId()))
        .withRel(LinkRelation.of("invoice"));
```

Tên relation mở rộng cần:

1. Có ý nghĩa nghiệp vụ rõ ràng.
2. Được dùng nhất quán trong toàn bộ API.
3. Không trùng với ý nghĩa của relation chuẩn đã đăng ký.
4. Được mô tả trong tài liệu hợp đồng để client biết cách diễn giải.

Theo quy tắc Web Linking, relation mở rộng có thể dùng URI tuyệt đối để định danh duy nhất. Với HAL, các relation mở rộng dạng URI có thể được công bố ngắn gọn thông qua CURIE (Compact URI). Nếu API dùng CURIE, cần cung cấp liên kết `curies` để client có thể mở rộng tên relation về URI định danh. Spring HATEOAS cũng cho phép ứng dụng dùng tên relation ngắn qua `LinkRelation.of(...)`; hãy xem đó là vocabulary riêng của hợp đồng ứng dụng và tài liệu hóa cho client. Nếu cần định danh mở rộng có khả năng liên thông theo chuẩn Web Linking/HAL, ưu tiên URI relation và CURIE.

Không nên tạo relation mới chỉ để diễn đạt lại một relation chuẩn. Ví dụ, dùng `self` cho chính tài nguyên thay vì tự tạo `currentOrder`; dùng `next` cho trang kế tiếp thay vì `nextPageLink`.

## 7. Relation có thể xuất hiện nhiều lần

Một tài nguyên có thể có nhiều liên kết cùng một relation. Ví dụ, một tài liệu có thể có nhiều phiên bản thay thế hoặc collection có nhiều link `item`. Khi tuần tự hóa HAL, một relation có thể được biểu diễn bằng một đối tượng link hoặc một mảng link tùy số lượng.

Ví dụ:

```json
{
  "_links": {
    "item": [
      {
        "href": "/orders/42"
      },
      {
        "href": "/orders/43"
      }
    ]
  }
}
```

Client nên xử lý đúng cả trường hợp relation trỏ đến một link và trường hợp có nhiều link, nếu hợp đồng API cho phép nhiều đích. Không nên giả định mọi relation luôn tương ứng với một chuỗi href duy nhất.

Trong Spring HATEOAS, có thể thêm nhiều link cùng relation vào representation. Hãy kiểm tra JSON được tuần tự hóa để bảo đảm client tiêu thụ được cấu trúc mà server phát ra.

## 8. Kiểm thử relation trong response

Kiểm thử nên tập trung vào relation mà client sử dụng và ý nghĩa điều hướng của chúng. Ví dụ với MockMvc và HAL:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.collection.href").exists());
```

Với response phân trang, kiểm tra link điều hướng theo vị trí trang:

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.prev").doesNotExist());
```

Cần có kiểm thử cho trang cuối để xác nhận không công bố `next`, và kiểm thử cho trang giữa để xác nhận cả `prev` lẫn `next` xuất hiện khi tương ứng có trang trước và sau.

Với relation mở rộng, kiểm thử tên relation và href đích:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.payment.href").exists())
    .andExpect(jsonPath("$._links.invoice.href").exists());
```

Khi kiểm thử hợp đồng, ưu tiên xác nhận relation có ý nghĩa và đích có thể truy cập thay vì khóa cứng mọi chi tiết triển khai. Một relation có thể giữ nguyên dù đường dẫn đích thay đổi, miễn là server cập nhật href đúng và giữ semantics đã cam kết.

## 9. Những lỗi thường gặp khi chọn relation

**Dùng tên relation như một HTTP method.** Relation mô tả ý nghĩa liên kết, không tự quyết định request dùng GET, POST hay DELETE. Dùng affordance khi cần mô tả tương tác.

**Tạo relation riêng dù đã có relation chuẩn.** Việc này làm client phải học thêm vocabulary không cần thiết. Kiểm tra registry trước khi đặt tên mới.

**Đổi relation tùy tiện.** Client có thể phụ thuộc vào tên relation để tìm chức năng. Xem việc đổi tên relation là thay đổi hợp đồng API và cần có chiến lược tương thích.

**Dùng relation mơ hồ.** Tên như `link1` hoặc `other` không giúp client hiểu ý nghĩa. Chọn tên theo quan hệ nghiệp vụ hoặc semantics đã đăng ký.

**Giả định relation luôn có một href.** Một relation có thể chứa nhiều link; client nên xử lý đúng cấu trúc mà media type quy định.

## 10. Nguyên tắc thiết kế

- **Ưu tiên relation chuẩn:** dùng relation IANA khi semantics phù hợp.
- **Dùng relation mở rộng có chủ đích:** chọn tên ổn định và tài liệu hóa semantics.
- **Tách relation khỏi href:** relation nói về ý nghĩa; href nói về đích.
- **Không suy ra HTTP method từ relation:** dùng affordance hoặc hợp đồng tương tác khi cần.
- **Giữ semantics qua các phiên bản:** đổi URL có thể tương thích nếu relation giữ nguyên và href mới đúng.
- **Kiểm thử relation quan trọng:** bảo đảm link được công bố đúng theo trạng thái và vị trí điều hướng.

Có thể tra cứu danh sách relation chuẩn tại <https://www.iana.org/assignments/link-relations/link-relations.xhtml> và đặc tả Web Linking trong RFC 8288. Khi chọn relation, hãy kiểm tra định nghĩa chính thức để dùng đúng semantics trong API.

## Kết luận

Link relation là vocabulary mô tả mối quan hệ giữa tài nguyên và đích liên kết. Spring HATEOAS cung cấp `IanaLinkRelations` cho các relation chuẩn và `LinkRelation.of(...)` cho relation mở rộng. Chọn relation theo semantics, giữ tên ổn định, tách nó khỏi href và kiểm thử những relation mà client dựa vào sẽ giúp hợp đồng hypermedia dễ hiểu và có khả năng tiến hóa.

