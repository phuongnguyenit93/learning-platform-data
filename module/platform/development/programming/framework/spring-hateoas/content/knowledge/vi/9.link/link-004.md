# title của link

Một API có thể trả về liên kết `orders` để client quay lại danh sách đơn hàng. Relation `orders` cho biết liên kết có ý nghĩa gì trong hợp đồng API, còn `href` cho biết đích cần truy cập. Tuy nhiên, khi hiển thị liên kết cho người dùng, một nhãn dễ hiểu như “Danh sách đơn hàng” sẽ hữu ích hơn tên relation kỹ thuật. Spring HATEOAS cho phép gắn metadata `title` vào một `Link` để cung cấp gợi ý văn bản này.

`title` là thuộc tính tùy chọn, mang thông tin mô tả dễ đọc về liên kết. Nó giúp client hoặc công cụ tiêu thụ API hiểu thêm về đích liên kết, nhưng không thay thế `rel`, `href` hay affordance. Trong Spring HATEOAS, có thể tạo title bằng `withTitle(...)` và đọc lại bằng `getTitle()`.

## title của link là gì?

Trong mô hình liên kết Web, một link thường có đích (`href`) và quan hệ (`rel`). Ngoài hai thành phần đó, link có thể mang metadata bổ sung như tiêu đề, kiểu media, ngôn ngữ của đích hoặc tên dùng để phân biệt liên kết.

`title` là một nhãn văn bản ngắn, dễ đọc, mô tả liên kết. Ví dụ:

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `rel` | `orders` | Liên kết có quan hệ “danh sách đơn hàng” với resource hiện tại. |
| `href` | `/api/orders` | URI mà client có thể truy cập. |
| `title` | `Danh sách đơn hàng` | Nhãn thân thiện để mô tả liên kết với người đọc hoặc client. |
| `type` | `application/hal+json` | Gợi ý media type của tài nguyên đích nếu được khai báo. |

Trong HTTP Web Linking, thuộc tính `title` được định nghĩa như một tham số mô tả mang thông tin dễ đọc cho link. HAL cũng cho phép đối tượng link chứa trường `title`. Spring HATEOAS cung cấp API để tạo và tuần tự hóa metadata đó.

Ví dụ HAL:

```json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/api/orders",
      "title": "Danh sách đơn hàng"
    }
  }
}
```

Client có thể dùng `title` làm gợi ý nhãn hiển thị. Việc có hiển thị hay không phụ thuộc client; một client có thể dùng relation để chọn biểu tượng hoặc hành vi và dùng title làm nội dung văn bản.

## Phân biệt title với rel và href

Ba thuộc tính này giải quyết ba câu hỏi khác nhau:

- **`rel` – liên kết này có quan hệ gì?** Đây là ngữ nghĩa máy có thể dùng để nhận biết vai trò của link, chẳng hạn `self`, `next`, `orders` hoặc `cancel`.
- **`href` – cần đi đến đâu?** Đây là URI đích. Client theo liên kết thay vì tự ghép URL từ ID hoặc quy tắc đường dẫn.
- **`title` – có thể mô tả liên kết bằng lời như thế nào?** Đây là gợi ý văn bản cho con người hoặc client, chẳng hạn “Trang tiếp theo” hay “Hồ sơ khách hàng”.

Không nên dùng title để quyết định hành vi nghiệp vụ. Client cần dựa vào `rel`, affordance và hợp đồng media type để hiểu hành động; `href` xác định đích. Title có thể thay đổi theo ngôn ngữ hoặc cách diễn đạt mà không làm thay đổi ý nghĩa của relation.

Ví dụ, các giá trị sau cùng mô tả một liên kết đến collection đơn hàng:

```json
{
  "rel": "orders",
  "href": "/api/orders",
  "title": "Danh sách đơn hàng"
}
```

Nếu đổi title thành “Các đơn hàng của tôi” nhưng relation và đích vẫn giữ nguyên, client vẫn nhận biết link qua `rel="orders"`. Nếu đổi `rel` thành một quan hệ khác, đó là thay đổi ngữ nghĩa của hợp đồng và cần được xem xét như một thay đổi API.

## Phân biệt title với các thuộc tính link khác

Spring HATEOAS `Link` có thể mang nhiều metadata. Mỗi thuộc tính có vai trò riêng:

| Thuộc tính | Mục đích | Ví dụ |
| --- | --- | --- |
| `rel` | Quan hệ của link với resource hiện tại | `self`, `orders`, `next` |
| `href` | URI đích | `/api/orders?page=1` |
| `title` | Mô tả ngắn, dễ đọc về link | `Trang tiếp theo` |
| `type` | Gợi ý media type của đích | `application/hal+json` |
| `hreflang` | Ngôn ngữ của representation ở đích | `vi`, `en` |
| `name` | Tên phân biệt link, hữu ích khi có nhiều link cùng relation | `primary`, `archive` |
| `deprecation` | URI thông tin về việc link đã bị deprecated | `https://api.example.com/deprecations/orders-v1` |
| `profile` | URI mô tả profile của representation đích | `https://api.example.com/profiles/order` |

`title` không thay thế `hreflang`: title là nhãn mô tả link, còn `hreflang` nói về ngôn ngữ của tài nguyên ở đích. Một nhãn tiếng Việt không có nghĩa representation ở đích chắc chắn là tiếng Việt.

`title` cũng không thay thế `type`. Client không nên suy ra media type của tài nguyên đích từ nội dung title. Tương tự, `name` là metadata nhận diện một link trong một số trường hợp; nó không phải văn bản hiển thị cho người dùng.

## Tạo title bằng Spring HATEOAS

Spring HATEOAS cung cấp `Link.withTitle(String)` để tạo một link mới có title. `Link` là kiểu giá trị bất biến; các phương thức `with...` trả về một link với metadata được cập nhật, vì vậy cần giữ kết quả trả về.

### Tạo link trực tiếp

```java
import org.springframework.hateoas.Link;

Link ordersLink = Link.of("/api/orders")
    .withRel("orders")
    .withTitle("Danh sách đơn hàng");
```

Link có relation `orders`, đích `/api/orders` và title tiếng Việt. Có thể thêm link này vào model:

```java
EntityModel<OrderView> model = EntityModel.of(order,
    Link.of("/api/orders/" + order.id()).withSelfRel(),
    ordersLink);
```

Trong ứng dụng thực tế, nên tạo link bằng mapping controller để tránh tự nối URL. Ví dụ tiếp theo dùng `WebMvcLinkBuilder`.

### Tạo title từ mapping controller

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link ordersLink = linkTo(methodOn(OrderController.class).all())
    .withRel("orders")
    .withTitle("Danh sách đơn hàng");
```

`linkTo(methodOn(...))` tạo đích dựa trên mapping của controller. `withRel("orders")` gắn ngữ nghĩa quan hệ; `withTitle(...)` bổ sung nhãn. Việc tạo link qua mapping giúp URI theo kịp thay đổi trong cấu hình endpoint.

### Thêm title vào EntityModel

Một controller có thể tạo title cho các link trong representation:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<OrderView> all() {
        return CollectionModel.of(orders.findRecent(),
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable UUID id) {
        OrderView order = orders.get(id);

        Link self = linkTo(methodOn(OrderController.class).one(id))
            .withSelfRel()
            .withTitle("Chi tiết đơn hàng");

        Link collection = linkTo(methodOn(OrderController.class).all())
            .withRel("orders")
            .withTitle("Danh sách đơn hàng");

        return EntityModel.of(order, self, collection);
    }
}
```

Ví dụ giả định `OrderService.get(...)` trả về `OrderView` và controller có phương thức `all()` cho collection. Title ở đây là metadata của từng link, không phải trường dữ liệu được thêm vào `OrderView`.

## Title trong response HAL

Khi ứng dụng trả HAL (`application/hal+json`), title được tuần tự hóa thành thuộc tính `title` bên trong đối tượng link ở `_links`.

Ví dụ response:

```json
{
  "id": "ord-1042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042",
      "title": "Chi tiết đơn hàng"
    },
    "orders": {
      "href": "https://api.example.com/api/orders",
      "title": "Danh sách đơn hàng"
    }
  }
}
```

Title là metadata tùy chọn. Nếu không đặt title, link vẫn hợp lệ và client vẫn có thể điều hướng qua `href`. Client có thể dùng `rel` làm nhãn dự phòng, hoặc tự tạo nhãn theo quy ước giao diện của nó.

Không nên giả định mọi media type đều tuần tự hóa link giống HAL. Nếu API hỗ trợ nhiều media type, hãy xem tài liệu của từng định dạng và kiểm thử phản hồi theo `Accept` tương ứng.

## Khi nào nên đặt title?

Title hữu ích khi relation kỹ thuật chưa đủ thân thiện để hiển thị trực tiếp hoặc khi liên kết cần được phân biệt rõ trong một tập hợp nhiều liên kết.

Các trường hợp thường gặp:

- **Điều hướng:** `self` có thể có title “Chi tiết đơn hàng”, còn `orders` có title “Danh sách đơn hàng”.
- **Phân trang:** link `next` có title “Trang tiếp theo”; link `prev` có title “Trang trước”.
- **Tài nguyên liên quan:** link `customer` có title “Hồ sơ khách hàng”.
- **Hành động nghiệp vụ:** link `cancel` có title “Hủy đơn hàng” nếu hành động hiện khả dụng.
- **Nhiều link cùng relation:** title có thể giúp người đọc phân biệt đích như “Tài liệu hướng dẫn” và “Tài liệu lưu trữ”, trong khi relation và `name` được xác định theo hợp đồng phù hợp.

Không cần đặt title cho mọi link. Nếu relation đã rõ và client không có nhu cầu hiển thị nhãn, có thể bỏ qua thuộc tính này. Thêm title không làm link có khả năng mới và cũng không thay thế affordance khi client cần biết HTTP method, kiểu nội dung hoặc trường đầu vào.

## Viết title ngắn gọn và nhất quán

Title nên mô tả đích hoặc mục đích của liên kết bằng ngôn ngữ rõ ràng. Một số nguyên tắc:

1. **Ngắn và có nghĩa:** dùng “Danh sách đơn hàng” thay cho câu dài giải thích toàn bộ nghiệp vụ.
2. **Mô tả đúng đích:** link `customer` nên có title nói về hồ sơ khách hàng, không đặt tên theo một thao tác không liên quan.
3. **Nhất quán:** cùng một relation nên có cách diễn đạt thống nhất giữa các endpoint.
4. **Không nhúng dữ liệu nhạy cảm:** tránh đưa email, số điện thoại, token hoặc thông tin riêng tư vào title.
5. **Không mã hóa logic vào văn bản:** client không nên phân tích chuỗi title để xác định trạng thái hay quyền.
6. **Có thể bản địa hóa:** nếu API phục vụ nhiều ngôn ngữ, title nên được tạo theo locale đã thỏa thuận.

Title là văn bản hiển thị hoặc gợi ý cho người dùng, vì vậy cần tránh nội dung gây hiểu nhầm. Nếu link chỉ khả dụng với một số trạng thái, hãy chỉ phát link khi phù hợp và để server kiểm tra lại quyền cùng điều kiện nghiệp vụ khi nhận request.

## Bản địa hóa title

Spring HATEOAS không tự dịch title theo ngôn ngữ người dùng. Ứng dụng có thể dùng `MessageSource` của Spring để lấy nhãn theo locale rồi truyền vào `withTitle(...)`.

Ví dụ:

```java
Link ordersLink = linkTo(methodOn(OrderController.class).all())
    .withRel("orders")
    .withTitle(messageSource.getMessage(
        "api.link.orders",
        null,
        locale));
```

Trong đó `messageSource` là bean `MessageSource` và `locale` là ngôn ngữ đã được xác định cho request. Các bundle thông điệp có thể khai báo:

```properties
# messages_vi.properties
api.link.orders=Danh sách đơn hàng
```

```properties
# messages_en.properties
api.link.orders=Order list
```

Nên dùng cùng chính sách locale cho toàn bộ title trong một response. Nếu server thương lượng ngôn ngữ qua `Accept-Language`, hãy đảm bảo response và cache xử lý header `Vary: Accept-Language` phù hợp để không dùng nhầm nhãn giữa các ngôn ngữ.

`hreflang` là metadata khác, dùng để mô tả ngôn ngữ của tài nguyên đích. Nó không tự động quyết định ngôn ngữ của title và không thay thế việc bản địa hóa chuỗi.

## Kiểm thử title của link

Kiểm thử nên xác nhận title được đưa vào đúng relation và được serialize theo media type đã công bố. Với MockMvc và HAL:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.title")
        .value("Chi tiết đơn hàng"))
    .andExpect(jsonPath("$._links.orders.title")
        .value("Danh sách đơn hàng"));
```

Có thể kiểm tra ở mức unit test khi tạo link:

```java
Link link = Link.of("/api/orders")
    .withRel("orders")
    .withTitle("Danh sách đơn hàng");

assertThat(link.getRel().value()).isEqualTo("orders");
assertThat(link.getHref()).isEqualTo("/api/orders");
assertThat(link.getTitle()).isEqualTo("Danh sách đơn hàng");
```

Ngoài giá trị title, cần xác nhận `href` và `rel` vẫn đúng. Kiểm thử title riêng lẻ không chứng minh liên kết dẫn đến đúng tài nguyên.

Nếu title được bản địa hóa, kiểm thử ít nhất một locale khác để bảo đảm chuỗi thay đổi đúng nhưng relation và đích link vẫn giữ nguyên. Nếu title không được cấu hình, kiểm tra client vẫn xử lý link thiếu trường `title` bình thường.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng title thay cho `rel` | Client không có relation ổn định để nhận biết ngữ nghĩa link. | Giữ relation có ý nghĩa; title chỉ bổ sung nhãn dễ đọc. |
| Dùng title thay cho `href` | Client không biết URI đích cần truy cập. | Cung cấp `href` hợp lệ và dùng title làm metadata. |
| Phân tích chuỗi title để quyết định hành động | Thay đổi ngôn ngữ hoặc cách diễn đạt có thể làm client hỏng. | Dựa vào `rel`, affordance và media type. |
| Gắn title quá dài hoặc mơ hồ | Nhãn khó đọc và không giúp phân biệt liên kết. | Dùng cụm từ ngắn mô tả đúng đích hoặc hành động. |
| Nghĩ `hreflang` là ngôn ngữ của title | Client có thể hiểu sai ngôn ngữ của representation đích. | Bản địa hóa title riêng; dùng `hreflang` cho ngôn ngữ tài nguyên đích. |
| Không giữ kết quả `withTitle(...)` | Title không được gắn vào link được trả về. | Gán link trả về từ chuỗi `with...` vì `Link` là immutable. |
| Giả định mọi media type đều có title | Client phụ thuộc vào metadata không có trong định dạng đang dùng. | Kiểm thử từng media type và xem title là tùy chọn. |

## Ghi nhớ

- `title` là metadata tùy chọn, cung cấp nhãn văn bản dễ đọc cho một link.
- `rel` mô tả ngữ nghĩa quan hệ; `href` là đích; `title` là gợi ý mô tả cho người đọc hoặc client.
- Spring HATEOAS hỗ trợ tạo title bằng `Link.withTitle(...)` và đọc bằng `getTitle()`.
- Với HAL, title xuất hiện trong đối tượng link bên dưới `_links`.
- Title không thay thế affordance, không quyết định quyền và không nên được dùng để phân tích logic nghiệp vụ.
- Bản địa hóa title qua `MessageSource` nếu API phục vụ nhiều locale; `hreflang` mô tả ngôn ngữ của đích.
- Kiểm thử title cùng `rel`, `href` và media type để bảo vệ hợp đồng hypermedia.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [HAL – Hypertext Application Language](https://stateless.group/hal_specification.html)
