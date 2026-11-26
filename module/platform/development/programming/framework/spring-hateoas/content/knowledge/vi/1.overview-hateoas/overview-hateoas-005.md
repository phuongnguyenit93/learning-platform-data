# Link như hợp đồng

Trong REST API, một đường dẫn cho biết tài nguyên nằm ở đâu. Nhưng một client còn cần biết **tài nguyên hiện tại liên hệ với tài nguyên nào và nó có thể tiếp tục làm gì**. HATEOAS đưa thông tin đó vào response dưới dạng link. Vì vậy, link là một phần của hợp đồng API: nó mô tả ý nghĩa của quan hệ và cung cấp đích để client khám phá.

Giả sử client đọc một đơn hàng. Nếu client tự ghép URL như `/api/orders/42/cancellation`, nó phải biết cấu trúc route và quy tắc của máy chủ. Khi route đổi, client có thể hỏng dù nghiệp vụ không đổi. Nếu response cung cấp quan hệ `cancel`, client có thể tìm hành động theo ý nghĩa của nó và lấy URI từ server. Máy chủ có thể thay URI mà vẫn giữ nguyên quan hệ.

## Một link mang ý nghĩa gì?

Một link HATEOAS thường có hai thành phần quan trọng:

- **Relation (`rel`)** cho biết link đại diện cho quan hệ nào với tài nguyên hiện tại. Ví dụ `self` là chính tài nguyên này, `next` là trang kế tiếp, `orders` là tập hợp đơn hàng, còn `cancel` là khả năng hủy đơn hàng.
- **Target (`href`)** là URI mà client có thể truy cập để đi theo quan hệ đó. URI do server tạo và có thể thay đổi theo cấu hình, phiên bản hoặc cấu trúc triển khai.

Link có thể mang thêm metadata như `title`, `type`, `hreflang`, `profile`, `deprecation` hoặc thông tin cho URI template. Metadata giúp client hiểu cách trình bày hay diễn giải link, nhưng không thay thế hợp đồng về nội dung representation và quy tắc HTTP.

Điểm ổn định nhất của hợp đồng là ý nghĩa của relation. Nếu `/api/orders/42` được chuyển thành `/v2/purchases/42`, client theo relation `self` vẫn lấy được URI mới từ response. Ngược lại, nếu server đổi nghĩa của relation `cancel` thành một thao tác khác, client có thể hiểu sai dù URI vẫn truy cập được.

Relation nên có tên ngắn, nhất quán và không phụ thuộc ngôn ngữ giao diện. Dùng relation chuẩn của IANA khi ý nghĩa phù hợp, chẳng hạn `self`, `next`, `prev` hoặc `collection`. Với nghiệp vụ riêng, chọn tên rõ nghĩa như `cancel`, `invoice` hay `payments` và giữ ý nghĩa đó ổn định. Nếu API cần chia sẻ rộng giữa nhiều tổ chức, có thể dùng relation URI hoặc profile để định nghĩa rõ các relation mở rộng.

## Tạo representation và link với Spring HATEOAS

Spring HATEOAS cung cấp các kiểu model để gắn link vào dữ liệu trả về:

| Kiểu | Mục đích |
| --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho representation có thể chứa một hoặc nhiều link. Dùng khi cần định nghĩa DTO tài nguyên riêng. |
| `EntityModel<T>` | Bọc một đối tượng nội dung, chẳng hạn DTO đơn hàng, cùng các link của nó. |
| `CollectionModel<T>` | Biểu diễn một tập hợp các model, thường có thêm link đến collection hoặc trang liên quan. |
| `PagedModel<T>` | Biểu diễn collection có thông tin phân trang. |

`EntityModel` và `CollectionModel` đều kế thừa cơ chế link từ `RepresentationModel`. Do đó, controller có thể trả về model giàu liên kết thay vì tự ghép một JSON chứa các URL.

Spring HATEOAS có `WebMvcLinkBuilder` để tạo URI từ mapping của controller. Hai hàm thường dùng là `linkTo(...)` và `methodOn(...)`:

- `methodOn(Controller.class).method(arguments)` mô tả method và tham số cần định tuyến.
- `linkTo(...)` chuyển mô tả đó thành link dựa trên mapping Spring MVC.
- `withSelfRel()` gán relation `self`; `withRel("...")` gán relation nghiệp vụ.

Ví dụ dưới đây dùng đơn hàng có trạng thái `PENDING` hoặc `CANCELLED`. Đơn hàng đang chờ có thể được hủy; đơn hàng đã hủy thì không còn link `cancel`.

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
        EntityModel<Order> model = EntityModel.of(order);

        model.add(linkTo(methodOn(OrderController.class)
                .one(order.id())).withSelfRel());
        model.add(linkTo(methodOn(OrderController.class)
                .all()).withRel("orders"));

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel("cancel"));
        }

        return model;
    }
}
```

Assembler nhận đối tượng nghiệp vụ và chuyển nó thành representation. Cách tổ chức này gom quy tắc tạo link vào một nơi, giúp các endpoint trả về cùng một loại tài nguyên có cấu trúc nhất quán. Trong ứng dụng thực tế, điều kiện thêm link nên xét cả trạng thái nghiệp vụ lẫn quyền của người dùng hiện tại.

Controller có thể dùng assembler cho cả endpoint chi tiết và collection:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<Order> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @GetMapping
    CollectionModel<EntityModel<Order>> all() {
        var orders = service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<Void> cancel(@PathVariable UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

`Order`, `OrderStatus` và `OrderService` ở đây đại diện cho model và tầng nghiệp vụ của ứng dụng. `one` trả về `EntityModel<Order>`; `all` trả về `CollectionModel<EntityModel<Order>>`. Khi mapping controller thay đổi, các URI được tạo từ mapping mới mà assembler không cần tự nối chuỗi đường dẫn.

## HAL thể hiện hợp đồng link ra sao?

Với HAL, response của một đơn hàng có thể có dạng:

```json
{
  "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042"
    },
    "orders": {
      "href": "https://shop.example/api/orders"
    },
    "cancel": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042/cancellation"
    }
  }
}
```

`_links` là vùng dành cho các quan hệ. Client có thể đọc `self.href` để mở tài nguyên hiện tại, hoặc tìm `cancel.href` để biết đích của quan hệ hủy. Khi đơn hàng không còn hủy được, server bỏ quan hệ `cancel`; client dựa vào sự hiện diện của link để quyết định có hiển thị thao tác hay không.

Trong ứng dụng Spring Boot, dependency `spring-boot-starter-hateoas` tích hợp Spring HATEOAS với cơ chế tự cấu hình hypermedia. Client có thể yêu cầu HAL bằng media type `application/hal+json`. Với cấu hình Spring không dùng auto-configuration của Boot, có thể bật hỗ trợ HAL bằng `@EnableHypermediaSupport(type = HypermediaType.HAL)`.

### Link điều hướng và mô tả thao tác

Một điểm cần phân biệt: link HAL thông thường mô tả relation và URI đích. Nó **không tự khai báo HTTP method, kiểu dữ liệu đầu vào hoặc các trường bắt buộc**. Trong ví dụ, relation `cancel` trỏ đến endpoint được khai báo bằng `POST`, nhưng chỉ nhìn vào `href` thì client không thể suy ra chắc chắn rằng phải gửi `POST` hay cần gửi body nào.

Nếu client cần khám phá đầy đủ cách thực hiện một thao tác, hãy mô tả affordance bằng cơ chế hypermedia phù hợp. Spring HATEOAS hỗ trợ affordance và có thể biểu diễn chúng qua HAL-FORMS. Một template HAL-FORMS có thể mô tả tên thao tác, method, target và các property đầu vào, ví dụ:

```json
{
  "_templates": {
    "cancel": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "target": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042/cancellation"
    }
  }
}
```

Đây là ví dụ rút gọn để minh họa metadata của thao tác; một template thực tế có thể khai báo thêm `contentType` và `properties` mô tả dữ liệu đầu vào. Khi dùng affordance, hãy cấu hình media type tương ứng và tạo affordance từ mapping/controller bằng API Spring HATEOAS. Với API công khai, tài liệu profile hoặc OpenAPI vẫn hữu ích để giải thích quy tắc nghiệp vụ, lỗi có thể xảy ra và schema chi tiết.

## Link phản ánh trạng thái và quyền

Link hành động nên được tạo theo khả năng thực hiện tại thời điểm server tạo response. Ví dụ:

- Đơn hàng `PENDING` và người dùng có quyền hủy: có thể cung cấp relation `cancel`.
- Đơn hàng `SHIPPED`: không cung cấp `cancel` nếu nghiệp vụ không cho phép hủy ở trạng thái này.
- Đơn hàng đã hủy: không cung cấp lại relation `cancel`.
- Người dùng không có quyền hủy: không cung cấp link hành động đó cho response của người dùng này.

Client có thể dùng sự hiện diện của link để điều chỉnh giao diện, nhưng link không phải cơ chế bảo mật. Trạng thái hoặc quyền có thể thay đổi sau khi client nhận response. Endpoint `POST` vẫn phải xác thực người dùng, kiểm tra quyền và kiểm tra lại trạng thái trước khi thực hiện. Nếu thao tác không còn hợp lệ, server cần trả về lỗi HTTP phù hợp và representation lỗi có thể cung cấp link giúp client xử lý tiếp.

Đừng đưa mọi link hành động vào mọi response chỉ vì endpoint tồn tại. Một link xuất hiện trong representation nên phản ánh khả năng có ý nghĩa với tài nguyên và ngữ cảnh hiện tại. Cũng không nên coi việc link biến mất là lỗi của client: khả năng có thể thay đổi theo trạng thái, quyền hoặc quy tắc nghiệp vụ.

## Kiểm thử hợp đồng link

Kiểm thử HATEOAS cần xác minh cả nội dung tài nguyên lẫn các relation mà client được phép khám phá. Với MockMvc, có thể kiểm tra response HAL như sau:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pendingOrderExposesCancelRelation() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.orders.href").exists())
                .andExpect(jsonPath("$._links.cancel.href").exists());
    }

    @Test
    void nonCancellableOrderDoesNotExposeCancelRelation() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10099")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.cancel").doesNotExist());
    }
}
```

Các UUID trong ví dụ cần được chuẩn bị trong dữ liệu kiểm thử: UUID kết thúc bằng `0042` là đơn hàng đang chờ và UUID kết thúc bằng `0099` là đơn hàng không thể hủy. Nếu quy tắc link phụ thuộc quyền, hãy bổ sung test cho người dùng có và không có quyền. Những kiểm thử này bảo vệ hợp đồng ở góc nhìn client: relation nào xuất hiện, relation nào vắng mặt và response dùng đúng media type.

## Giữ hợp đồng có thể tiến hóa

Khi phát triển API, hãy xem relation là tên có ý nghĩa lâu dài và URI là đích do server cung cấp. Một số thay đổi thường an toàn hơn khi client tuân theo link:

- Thay đổi cấu trúc URI nhưng giữ nguyên ý nghĩa relation.
- Bổ sung một relation mới mà client cũ có thể bỏ qua.
- Bỏ relation khi thao tác không còn khả dụng, với điều kiện client đã được thiết kế để xử lý link tùy chọn.

Các thay đổi cần cân nhắc tương thích gồm đổi ý nghĩa relation, đổi media type hoặc schema representation, và thay đổi cách thực hiện một affordance. Client nên tìm link bằng relation thay vì dựa vào thứ tự link, chuỗi URL cụ thể hoặc giả định rằng mọi tài nguyên đều có cùng tập hành động.

Khi thiết kế một relation mới, hãy trả lời ba câu hỏi: quan hệ này có nghĩa gì với tài nguyên hiện tại, trong điều kiện nào nó xuất hiện, và client cần biết gì để đi theo nó? Nếu chỉ cần điều hướng, link HAL có thể đủ. Nếu client cần biết method và dữ liệu đầu vào của một thao tác, hãy cung cấp affordance hoặc hợp đồng bổ sung phù hợp.

Một API có link tốt giúp client khám phá đường đi tiếp theo từ response, trong khi server vẫn kiểm soát URI và khả năng thao tác theo trạng thái hiện tại. Đó là giá trị của việc xem link như một phần hợp đồng REST: client phụ thuộc vào ý nghĩa được công bố, còn server có không gian để thay đổi cách tổ chức tài nguyên.
