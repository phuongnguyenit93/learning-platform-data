# Hypermedia trong REST

REST mô tả tài nguyên thông qua các biểu diễn và cho phép client tương tác với chúng bằng một giao diện thống nhất. Một API có thể cung cấp URI để client gọi từng endpoint, nhưng nếu client phải tự ghép đường dẫn hoặc ghi nhớ toàn bộ luồng nghiệp vụ thì nó vẫn phụ thuộc chặt vào cấu trúc URL của server. Hypermedia giải quyết vấn đề khám phá và điều hướng đó: mỗi biểu diễn tài nguyên có thể mang theo các liên kết cho biết client có thể đi đến đâu tiếp theo.

Trong hệ sinh thái Spring, Spring HATEOAS cung cấp các kiểu dữ liệu và công cụ để xây dựng những biểu diễn như vậy. Bài này tập trung vào vai trò của hypermedia trong REST, cách đọc liên kết và cách Spring HATEOAS đưa liên kết vào phản hồi HTTP.

## 1. Vấn đề khi API chỉ trả dữ liệu và URI cố định

Giả sử một hệ thống bán hàng có API xem đơn hàng. Client biết trước rằng muốn xem đơn hàng số 42 thì phải gọi:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Server trả về:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000
}
~~~

Phản hồi có đủ dữ liệu để hiển thị đơn hàng, nhưng không cho biết những bước tiếp theo. Client có thể phải tự biết rằng đơn hàng đang chờ thanh toán được thanh toán tại `/api/orders/42/payment`, còn việc hủy đơn hàng được thực hiện tại `/api/orders/42/cancellation`. Những quy tắc này thường được sao chép vào mã nguồn client, tài liệu và các ứng dụng tích hợp.

Khi server đổi cấu trúc URL, client đang ghép hoặc lưu các URL cũ có thể bị lỗi dù ý nghĩa nghiệp vụ của tài nguyên không thay đổi. Client cũng có thể hiển thị một nút thao tác không còn hợp lệ vì trạng thái đơn hàng đã chuyển từ `PENDING` sang `PAID`.

Hypermedia cho phép server đưa các liên kết phù hợp vào chính biểu diễn của tài nguyên. Client bắt đầu từ một điểm vào đã biết, đọc các liên kết và điều hướng dựa trên quan hệ của chúng. Nhờ đó, client ít phải tự suy đoán cấu trúc URL và các bước tiếp theo.

## 2. Hypermedia và HATEOAS trong REST

Hypermedia là cách kết hợp nội dung với những phương tiện điều hướng đến nội dung hoặc hành động liên quan. Trong một trang web, các phương tiện đó có thể là liên kết, biểu mẫu và nút bấm. Với REST API, chúng thường được biểu diễn bằng các link và affordance trong thông điệp HTTP.

HATEOAS là viết tắt của *Hypermedia As The Engine Of Application State*. Đây là một ràng buộc kiến trúc của REST: client khám phá các trạng thái và chuyển tiếp có thể thực hiện thông qua hypermedia do server cung cấp. Server gửi biểu diễn hiện tại cùng những liên kết có ý nghĩa trong ngữ cảnh đó; client chọn liên kết phù hợp rồi gửi yêu cầu tiếp theo.

Ví dụ, khi client truy cập một đơn hàng đang chờ xử lý, server có thể trả về liên kết đến chính đơn hàng, danh sách đơn hàng và thao tác hủy. Sau khi đơn hàng đã thanh toán, server có thể bỏ liên kết hủy và cung cấp liên kết xem biên nhận. Các liên kết phản ánh những chuyển tiếp mà API đang công bố cho tài nguyên ở trạng thái hiện tại.

HATEOAS không đơn thuần có nghĩa là thêm một trường URL vào JSON. Để điều hướng được, client cần hiểu ý nghĩa của quan hệ liên kết, kiểu biểu diễn và giao thức tương ứng. Server cần công bố quan hệ có ngữ nghĩa ổn định; client cần dựa vào quan hệ đó thay vì phân tích chuỗi URL để đoán nghiệp vụ.

Một luồng HATEOAS thường có các bước:

1. Client biết một URI điểm vào của API, hoặc nhận URI đó từ cấu hình hay một ứng dụng khác.
2. Client gửi yêu cầu và nhận biểu diễn tài nguyên.
3. Client đọc các liên kết cùng quan hệ của chúng để tìm tài nguyên hoặc chuyển tiếp phù hợp.
4. Client theo liên kết đã chọn và tiếp tục đọc biểu diễn mới.

Server vẫn xử lý từng yêu cầu theo giao thức HTTP và giữ tính stateless của REST. Liên kết không phải một phiên làm việc lưu trạng thái client trên server; nó là thông tin điều hướng được gửi trong biểu diễn.

## 3. Các thành phần của một biểu diễn hypermedia

### Tài nguyên và biểu diễn

Tài nguyên là khái niệm mà API cung cấp để client tương tác, chẳng hạn đơn hàng, khách hàng hoặc khoản thanh toán. Biểu diễn là dữ liệu được trao đổi để mô tả tài nguyên tại một thời điểm. Một tài nguyên có thể có nhiều dạng biểu diễn tùy media type và yêu cầu của client.

Trong Spring HATEOAS, các lớp mô hình biểu diễn phổ biến gồm:

| Kiểu | Mục đích |
| --- | --- |
| `RepresentationModel` | Lớp cơ sở cho mô hình biểu diễn có thể gắn các liên kết |
| `EntityModel<T>` | Bọc một đối tượng nội dung cùng các liên kết của nó |
| `CollectionModel<T>` | Biểu diễn một tập hợp các mô hình, thường dùng cho danh sách tài nguyên |
| `PagedModel<T>` | Biểu diễn tập hợp có phân trang và thông tin điều hướng trang |

Các kiểu này giúp tách dữ liệu nghiệp vụ khỏi phần điều hướng của API. Đối tượng bên trong vẫn có thể là DTO hoặc mô hình hiển thị đã được chọn lọc; các liên kết được gắn vào lớp biểu diễn ở tầng API.

### Link và link relation

Một link thường có đích đến (URI) và một quan hệ (relation, viết tắt là rel). URI cho biết client có thể gửi yêu cầu đến đâu; rel cho biết liên kết đó có ý nghĩa gì trong ngữ cảnh của biểu diễn.

Một số quan hệ thường gặp:

| Quan hệ | Ý nghĩa thường dùng |
| --- | --- |
| `self` | URI của chính tài nguyên đang được biểu diễn |
| `next` và `prev` | Trang kế tiếp và trang trước trong một tập hợp |
| `first` và `last` | Trang đầu và trang cuối |
| `collection` | Tập hợp chứa tài nguyên hiện tại |
| Quan hệ nghiệp vụ như `cancel`, `payment` | Tài nguyên hoặc thao tác liên quan theo quy ước của API |

Các quan hệ chuẩn có thể dùng tên đã đăng ký trong IANA Link Relation Registry. Với quan hệ mở rộng của ứng dụng, nhóm phát triển cần định nghĩa ý nghĩa rõ ràng và giữ ý nghĩa đó ổn định. Không nên đặt tên rel chỉ dựa trên tên controller hoặc đường dẫn nội bộ.

Client nên tìm liên kết theo rel rồi sử dụng URI được cung cấp. Client không nên tách URI thành các đoạn, tự nối ID vào đường dẫn hay giả định rằng mọi tài nguyên đều nằm dưới cùng một tiền tố URL.

### Affordance: mô tả cách tương tác

Link cho biết một đích đến và quan hệ của nó. Affordance bổ sung thông tin về cách tương tác mà đích đến hỗ trợ, chẳng hạn phương thức HTTP, dữ liệu đầu vào hoặc cấu trúc biểu mẫu. Sự khác biệt này quan trọng với các thao tác ghi dữ liệu: một link HAL thông thường chủ yếu mang URI, nên riêng nó chưa mô tả đầy đủ một biểu mẫu cập nhật hoặc toàn bộ schema của yêu cầu.

Khi client cần biết các trường cần gửi để cập nhật tài nguyên, API có thể dùng định dạng hypermedia hỗ trợ affordance, chẳng hạn HAL-FORMS, hoặc công bố hợp đồng thao tác theo một cơ chế phù hợp. Việc công bố affordance giúp client xây dựng giao diện và yêu cầu dựa trên khả năng server cung cấp.

## 4. Biểu diễn HAL

HAL (*Hypertext Application Language*) là một định dạng JSON phổ biến để biểu diễn tài nguyên và liên kết hypermedia. HAL dùng `_links` cho liên kết và `_embedded` cho tài nguyên được nhúng. Một phản hồi minh họa cho đơn hàng đang chờ xử lý có thể như sau:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/api/orders"
    },
    "cancel": {
      "href": "https://api.example.com/api/orders/42/cancellation"
    },
    "payment": {
      "href": "https://api.example.com/api/orders/42/payment"
    }
  }
}
~~~

Trong ví dụ này, `self` trỏ đến đơn hàng hiện tại. `collection` dẫn đến danh sách đơn hàng. Hai quan hệ `cancel` và `payment` công bố các khả năng nghiệp vụ liên quan đến đơn hàng đang ở trạng thái `PENDING`. Khi đơn hàng không còn đủ điều kiện hủy hoặc thanh toán, server có thể không đưa các liên kết tương ứng vào biểu diễn.

HAL cũng hỗ trợ nhúng tài nguyên liên quan trong `_embedded`. Ví dụ, một danh sách đơn hàng có thể chứa các biểu diễn đơn hàng đã nhúng; mỗi phần tử vẫn có thể mang liên kết `self` để client mở tài nguyên chi tiết. Nhúng giúp giảm số lần gọi khi dữ liệu liên quan cần thiết ngay lập tức, còn liên kết giúp client tiếp tục điều hướng khi cần.

Media type thường dùng cho HAL là `application/hal+json`. Client có thể thể hiện mong muốn nhận định dạng này bằng header:

~~~http
Accept: application/hal+json
~~~

Client cần kiểm tra media type thực tế trong phản hồi và xử lý định dạng mà API công bố. Không nên giả định rằng mọi JSON đều có cấu trúc HAL.

## 5. Tạo liên kết bằng Spring HATEOAS

Trong ứng dụng Spring Boot, có thể thêm starter Spring HATEOAS vào Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
~~~

Starter đưa các thành phần Spring HATEOAS vào ứng dụng và tích hợp với hệ sinh thái Spring MVC. Ví dụ dưới đây minh họa cách bọc DTO trong `EntityModel` và tạo liên kết dựa trên mapping của controller.

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.CollectionModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderDto> getOrder(@PathVariable Long id) {
        OrderDto order = orderService.getById(id);

        EntityModel<OrderDto> model = EntityModel.of(order);
        model.add(linkTo(methodOn(OrderController.class)
                .getOrder(id)).withSelfRel());
        model.add(linkTo(methodOn(OrderController.class)
                .listOrders()).withRel("collection"));

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancelOrder(id)).withRel("cancel"));
        }

        return model;
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderDto>> listOrders() {
        List<EntityModel<OrderDto>> items = orderService.findAll().stream()
                .map(order -> EntityModel.of(
                        order,
                        linkTo(methodOn(OrderController.class)
                                .getOrder(order.id())).withSelfRel()))
                .toList();

        return CollectionModel.of(
                items,
                linkTo(methodOn(OrderController.class)
                        .listOrders()).withSelfRel());
    }

    @DeleteMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancelOrder(@PathVariable Long id) {
        orderService.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Ví dụ giả định ứng dụng đã có `OrderService`, `OrderDto` và `OrderStatus`; phần truy cập dữ liệu và quy tắc nghiệp vụ được lược bỏ để tập trung vào cách tạo biểu diễn.

`EntityModel.of(order)` tạo mô hình cho một đơn hàng. `withSelfRel()` gắn quan hệ `self`; `withRel("collection")` gắn một quan hệ do API định nghĩa. `linkTo(methodOn(...))` lấy thông tin mapping từ phương thức controller để tạo URI. Cách này giảm việc viết lặp đường dẫn bằng chuỗi và giúp liên kết đi theo mapping khi cấu trúc endpoint thay đổi.

Điều kiện kiểm tra trạng thái minh họa việc công bố liên kết theo ngữ cảnh: đơn hàng chỉ có liên kết `cancel` khi đang ở trạng thái `PENDING`. Quy tắc này cần nhất quán với nghiệp vụ ở server. Việc client không nhìn thấy link không thay thế cho kiểm tra quyền và trạng thái ở endpoint; server vẫn phải xác thực và từ chối yêu cầu không hợp lệ.

`CollectionModel` biểu diễn danh sách và cho phép gắn liên kết ở cấp tập hợp. Mỗi phần tử trong danh sách cũng có thể là `EntityModel` để mang liên kết riêng. Với danh sách phân trang, `PagedModel` cung cấp mô hình phù hợp hơn để biểu diễn thông tin trang và các liên kết điều hướng.

### Liên kết thao tác và phương thức HTTP

Trong ví dụ, rel `cancel` trỏ đến endpoint hủy đơn hàng. Một link HAL cơ bản cung cấp URI và rel; nó không tự mô tả đầy đủ mọi chi tiết của request như phương thức HTTP và schema dữ liệu đầu vào. Client phải hiểu ngữ nghĩa của quan hệ và hợp đồng tương ứng. Nếu mục tiêu là để client khám phá cả phương thức và dữ liệu cần gửi, hãy thiết kế affordance và chọn media type có khả năng biểu diễn chúng, chẳng hạn HAL-FORMS.

Không nên công bố link thao tác chỉ vì endpoint tồn tại. Link cần phản ánh khả năng thực hiện trong ngữ cảnh tài nguyên và người dùng hiện tại. Đồng thời, server phải kiểm tra lại quyền, trạng thái và dữ liệu ở mỗi yêu cầu vì client có thể gửi URI cũ hoặc cố tình gọi endpoint trực tiếp.

## 6. Client điều hướng API như thế nào?

Một client hypermedia nên bắt đầu từ URI điểm vào đã được công bố. Sau khi nhận biểu diễn, client tìm rel mà nó hiểu, lấy `href` tương ứng và theo liên kết đó. Ví dụ, client có thể tìm rel `self` để mở chi tiết đơn hàng hoặc rel `next` để chuyển trang. Khi cần hủy đơn hàng, client tìm quan hệ `cancel` thay vì tự ghép đường dẫn từ ID.

Client nên xử lý các tình huống sau:

- Một liên kết tùy chọn có thể không xuất hiện vì tài nguyên chưa ở trạng thái cho phép thao tác.
- Một rel mà client chưa biết có thể được bỏ qua; điều này cho phép server bổ sung liên kết mới mà không làm hỏng client cũ.
- Một liên kết có thể trỏ đến host hoặc đường dẫn khác. Client nên dùng URI nhận được theo quy tắc bảo mật của ứng dụng, không tự sửa URI.
- Một yêu cầu theo liên kết vẫn có thể thất bại do trạng thái đã thay đổi, quyền bị thu hồi hoặc lỗi mạng. Client cần xử lý phản hồi HTTP như với mọi API khác.

Client cũng cần hiểu các rel quan trọng đối với nghiệp vụ của nó. Hypermedia giảm phụ thuộc vào cấu trúc URI, nhưng không thể khiến một client tự hiểu một hành động nghiệp vụ hoàn toàn mới nếu client chưa có logic xử lý hành động đó.

## 7. Hypermedia hỗ trợ tiến hóa hợp đồng API

Khi client phụ thuộc vào các URI được hard-code, thay đổi đường dẫn có thể buộc phải cập nhật đồng thời nhiều client. Với hypermedia, client nhận URI từ biểu diễn hiện tại nên server có thêm tự do thay đổi cấu trúc đường dẫn mà vẫn giữ quan hệ và ý nghĩa của liên kết.

Server cũng có thể bổ sung rel mới hoặc thay đổi tập liên kết theo trạng thái. Client cũ có thể bỏ qua rel chưa biết; client mới có thể sử dụng khả năng mới khi gặp liên kết tương ứng. Đây là một cơ chế hỗ trợ tiến hóa API theo hướng giảm phụ thuộc giữa client và server.

Tuy nhiên, hypermedia không tự động làm cho mọi thay đổi trở nên tương thích ngược. Đổi ý nghĩa của một rel, xóa một liên kết mà client đang phụ thuộc, thay đổi cấu trúc dữ liệu hoặc đổi media type vẫn có thể phá vỡ tích hợp. Quan hệ liên kết, media type và các trường dữ liệu cần được xem là một phần của hợp đồng API và phải được quản lý có chủ đích.

Một số nguyên tắc thiết kế hữu ích:

1. Bắt đầu từ một điểm vào ổn định và công bố các liên kết cần thiết để khám phá API.
2. Chọn rel theo ý nghĩa nghiệp vụ hoặc chuẩn đã có; ghi lại ý nghĩa của rel mở rộng.
3. Để server tạo URI từ mapping và ngữ cảnh thực tế thay vì yêu cầu client ghép URL.
4. Chỉ công bố thao tác phù hợp với trạng thái tài nguyên và ngữ cảnh truy cập.
5. Giữ kiểm tra xác thực, phân quyền và quy tắc nghiệp vụ ở server, kể cả khi link đã được cung cấp.
6. Quản lý thay đổi của rel, media type và cấu trúc biểu diễn như thay đổi hợp đồng API.

## 8. Kiểm thử liên kết hypermedia

Kiểm thử API hypermedia cần xác nhận cả dữ liệu tài nguyên lẫn khả năng điều hướng được công bố. Với phản hồi HAL, có thể dùng MockMvc và JSONPath để kiểm tra sự tồn tại của các quan hệ:

~~~java
mockMvc.perform(get("/api/orders/42")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.collection.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Nên có thêm kiểm thử cho trạng thái không cho phép hủy để xác nhận rel `cancel` không được công bố trong trường hợp đó. Nếu API hỗ trợ phân quyền theo người dùng, hãy kiểm tra tập liên kết trong các ngữ cảnh quyền khác nhau. Khi kiểm thử, ưu tiên xác nhận rel và hành vi theo hợp đồng; tránh phụ thuộc không cần thiết vào hostname, cổng hoặc chi tiết triển khai có thể thay đổi.

Ngoài kiểm tra cấu trúc JSON, cần theo liên kết được trả về trong kiểm thử tích hợp để xác nhận đích đến hoạt động đúng, phương thức HTTP được hỗ trợ và server thực thi lại các quy tắc nghiệp vụ. Nếu API công bố affordance, kiểm tra cả thông tin phương thức và dữ liệu đầu vào mà affordance mô tả.

## 9. Ghi nhớ

Hypermedia đưa thông tin điều hướng vào biểu diễn tài nguyên. Trong REST, HATEOAS yêu cầu client khám phá các chuyển tiếp có thể thực hiện thông qua liên kết mà server công bố. Link kết hợp URI với rel; affordance có thể mô tả sâu hơn cách tương tác. HAL là một định dạng JSON phổ biến để biểu diễn `_links` và `_embedded`, còn Spring HATEOAS cung cấp `EntityModel`, `CollectionModel`, `PagedModel` và `WebMvcLinkBuilder` để xây dựng các biểu diễn đó trong ứng dụng Spring.

Khi thiết kế API, hãy để server công bố những liên kết có ý nghĩa theo trạng thái tài nguyên, giữ ngữ nghĩa rel ổn định và kiểm thử khả năng điều hướng như một phần của hợp đồng. Client nhờ vậy có thể khám phá API từ các biểu diễn nhận được, thay vì phải biết trước toàn bộ cấu trúc endpoint.
