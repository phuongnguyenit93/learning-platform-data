# HATEOAS là gì

Hãy hình dung một API quản lý đơn hàng. Một đơn hàng mới tạo có thể được xác nhận hoặc hủy; đơn hàng đã giao chỉ có thể xem thông tin hoặc tạo yêu cầu đổi trả. Nếu ứng dụng khách tự ghép các URL như `/orders/{id}/cancel`, `/orders/{id}/ship` và ghi nhớ toàn bộ quy tắc trạng thái, mỗi lần máy chủ đổi đường dẫn hoặc quy trình nghiệp vụ, nhiều client phải cập nhật theo.

HATEOAS giải quyết một phần sự phụ thuộc đó bằng cách đưa các liên kết điều hướng vào biểu diễn của tài nguyên. Khi client đọc một đơn hàng, API trả về dữ liệu đơn hàng cùng những liên kết và hành động có thể thực hiện tại thời điểm đó. Client bắt đầu từ một địa chỉ đã biết, sau đó đi theo các liên kết mà máy chủ cung cấp.

Spring HATEOAS là thư viện trong hệ sinh thái Spring giúp xây dựng các biểu diễn REST có hypermedia. Thư viện cung cấp mô hình biểu diễn, kiểu liên kết, công cụ tạo URL từ controller, assembler và hỗ trợ các định dạng như HAL, HAL-FORMS.

## HATEOAS trong REST

HATEOAS là viết tắt của *Hypermedia As The Engine Of Application State*. Đây là một ràng buộc kiến trúc REST: client điều hướng qua các trạng thái của ứng dụng bằng những điều khiển hypermedia được nhúng trong biểu diễn tài nguyên.

Một biểu diễn tài nguyên thường có hai phần:

- **Dữ liệu:** thuộc tính mô tả tài nguyên, chẳng hạn mã đơn hàng, trạng thái và tổng tiền.
- **Hypermedia:** liên kết đến tài nguyên liên quan và thông tin về các hành động mà client có thể thực hiện.

Ví dụ, một phản hồi đơn hàng có thể chứa `self` để xem lại chính đơn hàng, `orders` để quay về danh sách và `cancel` khi đơn hàng vẫn đang chờ xử lý. Khi đơn hàng chuyển sang trạng thái đã giao, máy chủ có thể bỏ liên kết `cancel` và cung cấp liên kết `returns`.

Hai khái niệm cần phân biệt:

1. **Link (liên kết)** cho biết đích đến và quan hệ của đích đó với tài nguyên hiện tại. Một link thường có `href` và `rel`. Ví dụ, `rel="orders"` nói rằng liên kết dẫn đến tập hợp đơn hàng liên quan.
2. **Affordance (mô tả khả năng thao tác)** cho biết client có thể tương tác với tài nguyên như thế nào, chẳng hạn dùng HTTP `POST`, gửi kiểu dữ liệu nào và các trường đầu vào nào được chấp nhận. Affordance bổ sung ý nghĩa thao tác cho liên kết.

Một link đơn thuần không tự mô tả đầy đủ HTTP method hoặc cấu trúc request body. Nếu client cần biết cách gửi một hành động, API có thể biểu diễn affordance bằng một media type hỗ trợ metadata thao tác, chẳng hạn HAL-FORMS.

### HATEOAS giúp giải quyết vấn đề nào?

- **Giảm phụ thuộc vào cấu trúc URL:** client theo liên kết do máy chủ trả về thay vì tự ghép đường dẫn cho mọi bước nghiệp vụ.
- **Phản ánh trạng thái tài nguyên:** máy chủ chỉ cung cấp các hành động phù hợp với trạng thái hiện tại và chính sách truy cập.
- **Hỗ trợ khám phá API:** từ một điểm vào, client có thể lần theo các quan hệ như `self`, `next`, `prev`, `orders` hoặc các quan hệ nghiệp vụ riêng.
- **Giúp hợp đồng API tiến hóa có kiểm soát:** máy chủ có thể thay đổi đích của liên kết mà client vẫn hoạt động nếu client hiểu quan hệ và media type tương ứng.

HATEOAS không khiến client tự hiểu mọi nghiệp vụ. Client vẫn cần biết ý nghĩa của các quan hệ mà nó sử dụng, hiểu media type và xử lý dữ liệu theo hợp đồng. Việc thêm hypermedia cũng không thay thế tài liệu API, xác thực, phân quyền hay kiểm tra dữ liệu ở máy chủ.

## Mô hình biểu diễn trong Spring HATEOAS

Spring HATEOAS tách biểu diễn REST khỏi đối tượng nghiệp vụ. Một đối tượng domain hoặc DTO có thể được bọc trong representation model rồi bổ sung liên kết. Nhờ vậy controller không cần tự tạo JSON bằng cách ghép chuỗi hoặc đưa URL vào DTO nghiệp vụ.

Các kiểu quan trọng thường dùng:

| Kiểu | Mục đích |
| --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho biểu diễn tùy chỉnh có các liên kết hypermedia. Tham số generic tự tham chiếu giúp các thao tác như `add()` trả về đúng kiểu model. |
| `EntityModel<T>` | Bọc một đối tượng hoặc DTO đơn lẻ cùng các liên kết của nó. |
| `CollectionModel<T>` | Bọc một tập hợp phần tử và các liên kết ở cấp tập hợp, kể cả khi tập hợp rỗng. |
| `PagedModel<T>` | Biểu diễn tập hợp có phân trang và thông tin điều hướng giữa các trang. |
| `Link` | Giá trị bất biến mô tả một liên kết, thường gồm URI đích và quan hệ `rel`. |
| `RepresentationModelAssembler<S, D>` | Chuyển đối tượng nguồn thành representation model, giúp gom logic ánh xạ và tạo liên kết ra khỏi controller. |

Khi cần một kiểu biểu diễn có các trường riêng, có thể kế thừa `RepresentationModel`:

```java
public class CustomerModel extends RepresentationModel<CustomerModel> {
    private String name;
    private String email;

    // Constructor, getter và setter
}
```

Nếu chỉ cần bọc một DTO hiện có, `EntityModel.of(dto, links...)` thường ngắn gọn hơn. Với danh sách, `CollectionModel.of(items, links...)` giúp biểu diễn cả liên kết của từng phần tử lẫn liên kết điều hướng của tập hợp.

## Cài đặt và chọn định dạng hypermedia

Với ứng dụng Spring Boot, thêm starter sau và để Spring Boot dependency management chọn phiên bản tương thích với phiên bản Boot đang dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
```

Hai định dạng thường gặp:

| Media type | Đặc điểm |
| --- | --- |
| `application/hal+json` | HAL biểu diễn dữ liệu JSON cùng `_links` và có thể có `_embedded`. Phù hợp để mô tả tài nguyên và điều hướng bằng liên kết. |
| `application/prs.hal-forms+json` | HAL-FORMS mở rộng cách biểu diễn HAL bằng `_templates`, có thể mô tả HTTP method, đích gửi và các thuộc tính đầu vào của thao tác. |

HAL và HAL-FORMS là hai media type riêng biệt, không nên xem chúng là một định dạng có thể thay thế tùy ý. Client chọn định dạng mong muốn bằng header `Accept`; máy chủ cần có converter và cấu hình tương ứng để trả về định dạng đó.

Trong ứng dụng Spring Boot, starter HATEOAS thường tích hợp cấu hình hypermedia tự động. Với ứng dụng Spring MVC tự cấu hình hoặc khi muốn bật một loại hypermedia cụ thể, có thể khai báo:

```java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
```

Đổi `HAL_FORMS` thành `HAL` nếu ứng dụng chỉ cần HAL. Trước khi bật cấu hình tường minh trong Spring Boot, hãy kiểm tra cấu hình tự động hiện có để tránh đăng ký trùng các thành phần hỗ trợ hypermedia.

## Tạo liên kết từ controller

Không nên viết URL bằng cách nối chuỗi như `"/api/orders/" + id`. Cách đó làm mapping bị lặp ở nhiều nơi và dễ sai khi controller đổi đường dẫn. Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo link dựa trên mapping của controller.

Hai hàm thường dùng là:

- `linkTo(...)` xác định controller hoặc phương thức đích.
- `methodOn(...)` tạo lời gọi proxy để chỉ ra phương thức cần liên kết. Spring đọc mapping và các tham số `@PathVariable` để tạo URI.

Ví dụ:

```java
Link self = linkTo(methodOn(OrderController.class).one(orderId))
    .withSelfRel();

Link orders = linkTo(methodOn(OrderController.class).all())
    .withRel("orders");
```

`self` là quan hệ chuẩn thường dùng để chỉ tài nguyên hiện tại. `orders` là quan hệ mở rộng do ứng dụng định nghĩa. Với quan hệ phổ biến đã được IANA chuẩn hóa, nên ưu tiên hằng số trong `IanaLinkRelations` khi phù hợp. Với quan hệ nghiệp vụ riêng, hãy đặt tên ổn định và mô tả ý nghĩa trong hợp đồng API; hệ thống lớn có thể dùng URI quan hệ hoặc CURIE để tránh xung đột tên.

`methodOn(...)` không gọi phương thức controller thật để xử lý nghiệp vụ. Nó ghi nhận lời gọi trên proxy nhằm tìm mapping. Các giá trị tham số chỉ được dùng để tạo URI khi chúng tương ứng với thành phần đường dẫn như `@PathVariable`; không nên kỳ vọng mọi tham số đều trở thành query parameter của link.

## Ví dụ: API đơn hàng có liên kết và affordance

Giả sử dịch vụ quản lý đơn hàng có ba thao tác: lấy một đơn hàng, liệt kê đơn hàng và hủy đơn hàng đang chờ xử lý. DTO dùng để trả về API:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderView(UUID id, String status, BigDecimal total) {
}
```

Service cung cấp dữ liệu và thực hiện nghiệp vụ:

```java
import java.util.List;
import java.util.UUID;

public interface OrderService {
    OrderView get(UUID id);
    List<OrderView> findAll();
    OrderView cancel(UUID id);
}
```

Controller tạo representation model như sau. Các import của Spring MVC và Spring HATEOAS được đặt cùng lớp controller; `OrderView` và `OrderService` là DTO và service đã khai báo ở trên:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderView>> all() {
        List<EntityModel<OrderView>> items = orders.findAll().stream()
            .map(this::toModel)
            .toList();

        return CollectionModel.of(items,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    public EntityModel<OrderView> one(@PathVariable UUID id) {
        return toModel(orders.get(id));
    }

    @PostMapping("/{id}/cancellation")
    public EntityModel<OrderView> cancel(@PathVariable UUID id) {
        return toModel(orders.cancel(id));
    }

    private EntityModel<OrderView> toModel(OrderView order) {
        UUID id = order.id();
        Link self = linkTo(methodOn(OrderController.class).one(id))
            .withSelfRel();

        if ("PENDING".equals(order.status())) {
            self = self.andAffordance(
                afford(methodOn(OrderController.class).cancel(id)));

            return EntityModel.of(order,
                self,
                linkTo(methodOn(OrderController.class).all()).withRel("orders"),
                linkTo(methodOn(OrderController.class).cancel(id)).withRel("cancel"));
        }

        return EntityModel.of(order,
            self,
            linkTo(methodOn(OrderController.class).all()).withRel("orders"));
    }
}
```

Ở đây `afford(methodOn(...))` phân tích mapping của phương thức controller để lấy thông tin thao tác. Khi client yêu cầu HAL-FORMS, metadata affordance có thể được chuyển thành template trong `_templates`, gồm HTTP method và đích gửi. Khi client chỉ yêu cầu HAL, client vẫn nhận được các liên kết trong `_links`; HAL cơ bản không biểu diễn đầy đủ metadata form của affordance.

### Đọc phản hồi HAL

Một phản hồi HAL đơn hàng đang chờ xử lý có dạng rút gọn như sau:

```json
{
  "id": "2b2e4d1a-1a8d-4c0d-9c62-5e4b6e4c1001",
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/2b2e4d1a-1a8d-4c0d-9c62-5e4b6e4c1001"
    },
    "orders": {
      "href": "https://api.example.com/api/orders"
    },
    "cancel": {
      "href": "https://api.example.com/api/orders/2b2e4d1a-1a8d-4c0d-9c62-5e4b6e4c1001/cancellation"
    }
  }
}
```

Client đọc quan hệ `cancel` để biết thao tác hủy hiện được cung cấp và theo `href` để tìm đích. Nếu cần biết chính xác cách gửi request, client yêu cầu HAL-FORMS. Một phản hồi HAL-FORMS có thể bổ sung `_templates` tương tự:

```json
{
  "_templates": {
    "cancel": {
      "method": "post",
      "target": "https://api.example.com/api/orders/2b2e4d1a-1a8d-4c0d-9c62-5e4b6e4c1001/cancellation"
    }
  }
}
```

Tên template thường được suy ra từ tên phương thức controller được dùng để tạo affordance. Phản hồi thực tế còn phụ thuộc media type, cấu hình và metadata đầu vào/đầu ra của phương thức.

## Tổ chức mapping bằng assembler

Ví dụ controller ở trên có phương thức `toModel` để dễ theo dõi. Khi ứng dụng có nhiều controller hoặc nhiều loại biểu diễn, nên tách logic chuyển đổi sang `RepresentationModelAssembler`. Cách này giúp controller tập trung vào điều phối request và service, còn assembler chịu trách nhiệm chuyển đối tượng domain thành biểu diễn hypermedia.

Một assembler thường triển khai `toModel(source)` để tạo biểu diễn cho một phần tử và có thể tùy chỉnh `toCollectionModel(...)` cho tập hợp. Có thể tái sử dụng `linkTo(methodOn(...))` bên trong assembler, miễn là các liên kết phản ánh đúng mapping và trạng thái nghiệp vụ.

Nên dùng DTO hoặc representation model dành riêng cho API thay vì trả trực tiếp JPA entity. Entity có thể chứa quan hệ hai chiều, dữ liệu nội bộ hoặc trường không nên công khai. Tách lớp biểu diễn giúp kiểm soát dữ liệu, định dạng và hợp đồng API độc lập với cấu trúc lưu trữ.

## Kiểm thử liên kết và khả năng tiến hóa hợp đồng

Kiểm thử HATEOAS cần xác nhận cả dữ liệu lẫn điều hướng. Chỉ kiểm tra HTTP status hoặc các trường JSON chưa đủ để phát hiện một liên kết bị mất, đổi sai quan hệ hoặc xuất hiện khi hành động không còn hợp lệ.

Với `MockMvc`, có thể kiểm tra các quan hệ trong phản hồi HAL:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$._links.cancel.href").exists());
```

Với đơn hàng không còn ở trạng thái `PENDING`, kiểm tra liên kết hủy không xuất hiện:

```java
mockMvc.perform(get("/api/orders/{id}", shippedOrderId)
        .accept(MediaType.parseMediaType("application/hal+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.cancel").doesNotExist());
```

Nếu API công bố HAL-FORMS, kiểm tra template và method tương ứng:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates.cancel.method").value("post"));
```

Các kiểm thử này nên được bổ sung bằng kiểm thử nghiệp vụ cho service: người dùng không đủ quyền hoặc đơn hàng đã chuyển trạng thái vẫn phải bị từ chối khi gọi trực tiếp endpoint hủy. Việc không phát liên kết chỉ giúp client biết hành động hiện không được cung cấp; nó không phải cơ chế bảo mật. Máy chủ luôn phải kiểm tra quyền và trạng thái ở thời điểm xử lý request.

Để hợp đồng API có thể tiến hóa, hãy chú ý một số nguyên tắc:

1. **Cung cấp điểm vào rõ ràng:** client chỉ cần biết URI khởi đầu đã được thống nhất, sau đó theo các quan hệ liên kết để đi đến tài nguyên tiếp theo.
2. **Giữ ngữ nghĩa của `rel` ổn định:** nếu quan hệ `orders` có nghĩa là danh sách đơn hàng, đừng âm thầm đổi nó thành một tài nguyên có ý nghĩa khác. Với quan hệ riêng, công bố mô tả để client có thể triển khai đúng.
3. **Không bắt client ghép URL:** client nên đọc `href` từ phản hồi. Nếu đường dẫn nội bộ thay đổi nhưng quan hệ và ý nghĩa không đổi, client có thể tiếp tục hoạt động.
4. **Xem sự hiện diện của liên kết là tín hiệu điều hướng:** client cần xử lý trường hợp một quan hệ không xuất hiện, vì hành động có thể không khả dụng với trạng thái hoặc quyền hiện tại.
5. **Thỏa thuận rõ media type:** client và server cần thống nhất HAL hay HAL-FORMS. Thay đổi media type có thể làm thay đổi cách client đọc metadata.
6. **Kiểm thử hành vi thay vì phụ thuộc URL cứng:** xác nhận quan hệ, khả năng theo liên kết và điều kiện xuất hiện của hành động. Chỉ kiểm tra chuỗi `href` tuyệt đối khi host hoặc cấu trúc URL chính là điều hợp đồng cần bảo vệ.

HATEOAS giúp giảm liên kết chặt giữa client và cấu trúc điều hướng của server, nhưng không đảm bảo mọi thay đổi API đều tương thích ngược. Thay đổi tên trường, ý nghĩa quan hệ, quy tắc nghiệp vụ hoặc định dạng payload vẫn có thể yêu cầu client cập nhật. Vì vậy, hãy xem hypermedia là một phần của hợp đồng API và kiểm thử nó như các phần còn lại.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ thêm `self` link rồi coi API đã có điều hướng HATEOAS đầy đủ | Client vẫn phải tự biết mọi bước tiếp theo. | Bổ sung các quan hệ hữu ích phản ánh luồng nghiệp vụ và trạng thái tài nguyên. |
| Nối chuỗi URL trong controller hoặc client | Mapping bị lặp và dễ lệch khi endpoint thay đổi. | Dùng `WebMvcLinkBuilder` ở server và theo `href` ở client. |
| Nghĩ rằng `rel="cancel"` tự mô tả HTTP method và request body | Client có thể không biết cách gửi thao tác. | Dùng affordance và media type có khả năng biểu diễn metadata như HAL-FORMS khi cần. |
| Luôn phát mọi action link | Client nhìn thấy hành động không phù hợp với trạng thái hoặc quyền. | Tạo liên kết theo trạng thái nghiệp vụ; vẫn xác thực và phân quyền ở endpoint. |
| Trả trực tiếp entity lưu trữ | Dữ liệu nội bộ hoặc quan hệ không mong muốn có thể bị lộ. | Dùng DTO hoặc representation model dành cho API. |
| Kiểm thử mỗi status code | Liên kết sai hoặc thiếu có thể không bị phát hiện. | Kiểm tra `rel`, affordance, media type và các trường hợp action không khả dụng. |

## Ghi nhớ

- HATEOAS là cách client điều hướng trạng thái ứng dụng qua hypermedia trong biểu diễn tài nguyên.
- Spring HATEOAS cung cấp `RepresentationModel`, `EntityModel`, `CollectionModel`, `PagedModel`, `Link` và assembler để xây dựng biểu diễn đó.
- `linkTo(methodOn(...))` tạo URL dựa trên mapping controller; `rel` mô tả quan hệ giữa tài nguyên hiện tại và đích liên kết.
- Affordance mô tả cách thao tác với tài nguyên. HAL biểu diễn liên kết; HAL-FORMS có thể biểu diễn thêm template và thông tin request.
- Liên kết phản ánh hành động khả dụng, còn máy chủ vẫn phải kiểm tra quyền và quy tắc nghiệp vụ khi nhận request.
- Kiểm thử cả dữ liệu, liên kết, affordance và khả năng điều hướng để bảo vệ hợp đồng API khi hệ thống thay đổi.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API: WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [HAL – Hypertext Application Language](https://stateless.group/hal_specification.html)
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/)
