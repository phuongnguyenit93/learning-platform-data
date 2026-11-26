# Điều hướng bằng liên kết

Trong REST, một tài nguyên không chỉ là dữ liệu được trả về từ máy chủ. Phản hồi còn có thể chỉ cho client biết tài nguyên liên quan nào có thể truy cập và những thao tác nào đang khả dụng. Cách thiết kế này được gọi là **HATEOAS** (*Hypermedia as the Engine of Application State*): client khám phá các bước tiếp theo bằng cách đọc liên kết và thông tin hypermedia trong phản hồi.

Spring HATEOAS cung cấp các kiểu mô hình và công cụ tạo liên kết để xây dựng cách điều hướng đó trong ứng dụng Spring. Bài học này thuộc chương **Tổng quan HATEOAS**, tập trung vào cách dùng `RepresentationModel`, xây dựng liên kết theo controller, biểu diễn hành động khả dụng, xuất dữ liệu HAL và kiểm thử hợp đồng hypermedia.

Sau bài học, bạn có thể:

- Phân biệt URI của tài nguyên với quan hệ liên kết (*link relation*).
- Chọn `RepresentationModel`, `EntityModel`, `CollectionModel` hoặc `PagedModel` phù hợp với phản hồi.
- Tạo liên kết bằng `linkTo` và `methodOn` thay vì ghép chuỗi URL thủ công.
- Thêm liên kết có điều kiện và mô tả thao tác bằng affordance.
- Đọc cấu trúc HAL và kiểm thử liên kết theo quan hệ của chúng.
- Thiết kế client có thể thích nghi khi đường dẫn hoặc trạng thái tài nguyên thay đổi.

## 1. HATEOAS biến phản hồi thành điểm bắt đầu điều hướng

Giả sử client gọi `GET /orders/42` để đọc đơn hàng. Một API chỉ trả về dữ liệu có thể gửi:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000
}
```

Client muốn xem danh sách hoặc hủy đơn hàng phải biết trước các đường dẫn tương ứng, chẳng hạn `/orders` và `/orders/42/cancellation`. Khi đường dẫn thay đổi, client có thể phải cập nhật theo.

Với HATEOAS, máy chủ gửi kèm các liên kết mô tả quan hệ của tài nguyên:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": { "href": "https://api.example.com/orders/42" },
    "orders": { "href": "https://api.example.com/orders" },
    "cancel": { "href": "https://api.example.com/orders/42/cancellation" }
  }
}
```

Client đọc quan hệ `orders` để tìm danh sách và quan hệ `cancel` để biết thao tác hủy đang được cung cấp. Client không cần tự ghép URI từ ID hoặc dựa vào cấu trúc đường dẫn nội bộ của máy chủ.

Một liên kết thường có hai thành phần quan trọng:

| Thành phần | Ý nghĩa |
|---|---|
| `rel` | Quan hệ hoặc ý nghĩa của liên kết, ví dụ `self`, `next`, `orders`, `cancel`. |
| `href` | URI mà client có thể truy cập để đi theo quan hệ đó. |

Một số định dạng còn hỗ trợ thuộc tính như `title`, `type`, `hreflang` hoặc `deprecation` để cung cấp thêm ngữ cảnh. `href` cho biết đích đến; `rel` cho biết client nên hiểu liên kết đó như thế nào. Vì vậy, tên quan hệ cần ổn định và có ý nghĩa rõ ràng.

`self`, `next`, `prev` là những quan hệ phổ biến đã được chuẩn hóa. Các quan hệ theo nghiệp vụ như `cancel`, `approve` hoặc `payment` thường là quan hệ riêng của API; hãy mô tả ý nghĩa của chúng trong hợp đồng API để client có thể sử dụng nhất quán.

## 2. Các kiểu mô hình của Spring HATEOAS

Spring HATEOAS cung cấp các lớp mô hình để gắn liên kết với dữ liệu trả về. Các lớp này thuộc gói `org.springframework.hateoas`.

| Kiểu | Khi sử dụng | Vai trò |
|---|---|---|
| `RepresentationModel<T>` | Xây dựng kiểu biểu diễn riêng | Lớp cơ sở có khả năng chứa các liên kết. |
| `EntityModel<T>` | Trả về một đối tượng | Bọc một đối tượng miền và các liên kết của nó. |
| `CollectionModel<T>` | Trả về một tập hợp | Bọc nhiều mô hình phần tử và có thể thêm liên kết cho cả tập hợp. |
| `PagedModel<T>` | Trả về dữ liệu phân trang | Biểu diễn tập hợp có metadata trang và các liên kết điều hướng trang. |

Ví dụ, `EntityModel<Order>` biểu diễn một đơn hàng; `CollectionModel<EntityModel<Order>>` biểu diễn danh sách các đơn hàng mà từng phần tử có thể có liên kết riêng.

Nếu cần một kiểu biểu diễn chuyên biệt, bạn có thể kế thừa `RepresentationModel`:

```java
public class OrderRepresentation extends RepresentationModel<OrderRepresentation> {

    private final Long id;
    private final String status;

    public OrderRepresentation(Long id, String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

Với trường hợp thông thường, `EntityModel` thường đủ dùng và tránh phải tạo thêm lớp chỉ để bọc dữ liệu. Chỉ tạo kiểu kế thừa riêng khi biểu diễn API cần cấu trúc hoặc hành vi riêng.

## 3. Tạo liên kết theo phương thức controller

Spring HATEOAS có `WebMvcLinkBuilder` để tạo liên kết từ mapping của Spring MVC. Hai hàm thường dùng là:

- `linkTo(...)`: xác định controller hoặc phương thức làm đích liên kết.
- `methodOn(...)`: tạo lời gọi proxy tới phương thức controller để Spring HATEOAS đọc mapping và tham số đường dẫn.

Ví dụ dưới đây giả định ứng dụng đã có `OrderService` để truy vấn và cập nhật đơn hàng:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

record Order(Long id, String status, BigDecimal total) {}

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

        Link self = linkTo(methodOn(OrderController.class).one(id))
                .withSelfRel();

        EntityModel<Order> model = EntityModel.of(
                order,
                self,
                linkTo(methodOn(OrderController.class).all()).withRel("orders")
        );

        if ("PENDING".equals(order.status())) {
            model.add(linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel"));
        }

        return model;
    }

    @GetMapping
    CollectionModel<EntityModel<Order>> all() {
        List<EntityModel<Order>> items = orderService.findAll().stream()
                .map(order -> EntityModel.of(
                        order,
                        linkTo(methodOn(OrderController.class).one(order.id()))
                                .withSelfRel()
                ))
                .toList();

        return CollectionModel.of(
                items,
                linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<Void> cancel(@PathVariable Long id) {
        orderService.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
```

Trong ví dụ:

1. `self` trỏ tới chính đơn hàng đang được biểu diễn.
2. `orders` cho phép client quay lại tập hợp đơn hàng.
3. `cancel` chỉ xuất hiện khi trạng thái là `PENDING`, tức là thao tác này đang khả dụng theo quy tắc nghiệp vụ.
4. `all` gắn `self` cho từng đơn hàng và cho cả tập hợp.

Lời gọi trong `methodOn` chỉ dùng để Spring HATEOAS xác định mapping; nó không thực thi nghiệp vụ của phương thức controller như một lời gọi trực tiếp thông thường. Các tham số được dùng để dựng URI, đặc biệt là `@PathVariable`. Khi một mapping thay đổi, cách tạo liên kết theo phương thức giúp giảm việc phải sửa các chuỗi URL rải rác trong mã nguồn.

Bạn cũng có thể tạo liên kết tĩnh bằng `Link.of(uri).withRel("...")`, nhưng với endpoint của ứng dụng Spring MVC, nên ưu tiên `linkTo(methodOn(...))` để liên kết bám theo mapping đã khai báo.

## 4. Tách logic tạo biểu diễn bằng assembler

Khi nhiều endpoint cần tạo biểu diễn cho cùng một loại tài nguyên, việc đặt toàn bộ logic tạo liên kết trong controller dễ dẫn tới lặp mã. `RepresentationModelAssembler` cho phép tập trung cách chuyển đối tượng miền thành mô hình hypermedia.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<Order>> {

    @Override
    public EntityModel<Order> toModel(Order order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class).one(order.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class).all()).withRel("orders")
        );
    }
}
```

Controller có thể gọi `assembler.toModel(order)` cho từng phần tử. Cách này giúp các phản hồi về cùng một loại tài nguyên giữ cấu trúc liên kết nhất quán. Với danh sách, kết quả từ assembler được đưa vào `CollectionModel`; với trang kết quả, có thể dùng `PagedModel` và cung cấp liên kết `first`, `prev`, `self`, `next`, `last` khi tương ứng.

Nếu cần kiểm soát tên quan hệ của phần tử nhúng trong HAL, có thể khai báo `@Relation` trên lớp biểu diễn với `itemRelation` và `collectionRelation`. Việc đặt tên quan hệ tường minh hữu ích khi tên lớp Java có thể thay đổi nhưng hợp đồng API cần giữ ổn định.

## 5. Biểu diễn hành động khả dụng bằng affordance

Một liên kết cho biết có thể điều hướng tới đâu. Tuy nhiên, chỉ có `href` thường chưa mô tả đầy đủ cách thực hiện thao tác: client có thể cần biết HTTP method, kiểu nội dung hoặc các trường đầu vào. Spring HATEOAS hỗ trợ **affordance** để gắn mô tả thao tác với một liên kết.

Ví dụ, liên kết `self` của đơn hàng có thể mang thêm affordance cho thao tác hủy:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

Link self = linkTo(methodOn(OrderController.class).one(id)).withSelfRel();

if ("PENDING".equals(order.status())) {
    self = self.andAffordance(
            afford(methodOn(OrderController.class).cancel(id))
    );
}
```

`afford(...)` lấy thông tin từ mapping của phương thức controller. Spring HATEOAS có thể dùng thông tin đó để mô tả phương thức HTTP và dữ liệu đầu vào mà thao tác yêu cầu. Affordance thường được gắn với liên kết đại diện tài nguyên, chẳng hạn `self`, để mô tả các hành động có thể thực hiện trên tài nguyên đó.

Affordance là metadata giúp client hiểu cách tương tác; nó không tự thực thi thao tác, không thay thế kiểm tra quyền và cũng không đảm bảo thao tác sẽ thành công. Máy chủ vẫn phải xác thực, phân quyền, kiểm tra trạng thái hiện tại và xác thực dữ liệu khi nhận request.

Định dạng phản hồi quyết định metadata này được trình bày thế nào. HAL JSON tiêu chuẩn tập trung vào `_links` và `_embedded`; nếu muốn biểu diễn các mẫu thao tác như form, có thể thương lượng nội dung với HAL-FORMS (`application/prs.hal-forms+json`). Client chỉ sử dụng được metadata affordance khi định dạng được chọn và client hỗ trợ nó. Vì vậy, cần chọn media type phù hợp với khả năng của client.

## 6. HAL và cấu trúc JSON

HAL (*Hypertext Application Language*) là một định dạng biểu diễn hypermedia phổ biến. Trong Spring Boot, dependency `spring-boot-starter-hateoas` cung cấp tích hợp Spring HATEOAS và cấu hình chuyển đổi phù hợp để các mô hình như `EntityModel` được tuần tự hóa thành HAL.

Một tài nguyên HAL thường có:

- Các thuộc tính dữ liệu của tài nguyên.
- `_links`: các liên kết được nhóm theo quan hệ.
- `_embedded`: các tài nguyên khác được nhúng, thường gặp trong biểu diễn tập hợp.

Ví dụ phản hồi cho một đơn hàng:

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
    },
    "cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    }
  }
}
```

Client nên tìm `_links.cancel` theo quan hệ thay vì giả định URL luôn kết thúc bằng `/cancellation`. Khi đơn hàng đã được giao, máy chủ có thể bỏ quan hệ `cancel`; sự vắng mặt đó báo hiệu client không được cung cấp thao tác hủy ở trạng thái hiện tại. Client vẫn phải xử lý trường hợp liên kết biến mất giữa lúc hiển thị giao diện và lúc gửi request, vì trạng thái có thể thay đổi đồng thời.

Để yêu cầu HAL JSON, client có thể gửi header:

```http
Accept: application/hal+json
```

Nếu endpoint chỉ cung cấp một định dạng, có thể khai báo `produces = MediaTypes.HAL_JSON_VALUE` trên mapping. Nếu API hỗ trợ nhiều định dạng, hãy để content negotiation lựa chọn biểu diễn phù hợp và kiểm tra đúng `Accept`/`Content-Type` trong kiểm thử.

## 7. Thiết kế điều hướng để hợp đồng API có thể tiến hóa

Hypermedia giúp client ít phụ thuộc vào cấu trúc URI cụ thể, nhưng không tự động làm cho mọi thay đổi API trở nên tương thích. Để hợp đồng có thể tiến hóa, cần giữ ổn định ý nghĩa của quan hệ và cách client diễn giải chúng.

**Giữ ổn định quan hệ, cho phép thay đổi URI.** Nếu đường dẫn chi tiết đơn hàng đổi từ `/orders/42` sang một cấu trúc khác, client vẫn có thể đi theo `self` do máy chủ cung cấp. Tránh yêu cầu client tự dựng URL từ ID hoặc ghép chuỗi đường dẫn.

**Dùng sự hiện diện của liên kết để công bố khả năng.** Một đơn hàng đang chờ có thể có `cancel`; đơn đã giao có thể không có. Client kiểm tra liên kết trước khi hiển thị hành động. Không nên gửi một liên kết tới thao tác chắc chắn bị từ chối bởi trạng thái nghiệp vụ hiện tại.

**Định nghĩa rõ quan hệ tùy chỉnh.** `cancel` phải có ý nghĩa thống nhất: tài nguyên đích là gì, thao tác mong đợi là gì và điều kiện nào khiến thao tác khả dụng. Không tái sử dụng cùng một tên quan hệ cho hai ý nghĩa khác nhau.

**Không xem liên kết là cơ chế bảo mật.** Việc ẩn liên kết chỉ giúp mô tả khả năng hiện tại cho client. Máy chủ vẫn cần xác thực và phân quyền trên endpoint, vì client có thể lưu URI cũ hoặc gửi request trực tiếp.

**Thay đổi biểu diễn có chủ đích.** Có thể bổ sung quan hệ mới mà client cũ chưa biết và client có thể bỏ qua quan hệ không sử dụng. Với thay đổi làm đổi ý nghĩa của quan hệ hoặc cấu trúc dữ liệu theo cách không tương thích, hãy cân nhắc quan hệ mới, media type có phiên bản hoặc chiến lược versioning phù hợp.

**Giữ ý nghĩa nghiệp vụ tách khỏi tên phương thức Java.** Tên phương thức controller có thể được refactor. Quan hệ như `orders` hoặc `cancel` là một phần của hợp đồng mà client dựa vào, nên cần được xem xét như API công khai.

## 8. Kiểm thử liên kết và hành vi điều hướng

Kiểm thử HATEOAS cần xác nhận phản hồi cung cấp đúng quan hệ trong đúng trạng thái, thay vì chỉ xác nhận JSON có dữ liệu. Với Spring MVC, có thể dùng `MockMvc` và JSONPath để kiểm tra HAL.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pendingOrderExposesCancelLink() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.orders.href").exists())
                .andExpect(jsonPath("$._links.cancel.href").exists());
    }

    @Test
    void deliveredOrderDoesNotExposeCancelLink() throws Exception {
        mockMvc.perform(get("/orders/43").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.cancel").doesNotExist());
    }
}
```

Ví dụ giả định dữ liệu kiểm thử đã được chuẩn bị để đơn hàng `42` ở trạng thái `PENDING` và đơn hàng `43` ở trạng thái đã giao. Trong dự án thực tế, hãy dùng fixture hoặc mock service để thiết lập trạng thái rõ ràng, tránh phụ thuộc dữ liệu môi trường.

Các điểm nên kiểm tra:

- Phản hồi dùng media type mà client yêu cầu.
- Tài nguyên có quan hệ `self` và các quan hệ điều hướng cần thiết.
- Liên kết hành động chỉ xuất hiện khi điều kiện nghiệp vụ cho phép.
- Liên kết của từng phần tử trong collection trỏ tới đúng tài nguyên.
- Nếu xuất affordance qua HAL-FORMS, kiểm tra template, HTTP method và metadata đầu vào theo hợp đồng đã công bố.
- Client hoặc kiểm thử không phụ thuộc vào host, port hay URI đầy đủ cố định nếu các giá trị đó có thể thay đổi theo môi trường.

## 9. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghép URL bằng chuỗi trong nhiều controller | Mapping đổi nhưng liên kết cũ vẫn tồn tại | Dùng `linkTo(methodOn(...))`. |
| Chỉ trả dữ liệu, không có liên kết | Client phải biết trước đường dẫn và luồng nghiệp vụ | Bổ sung mô hình hypermedia phù hợp. |
| Dùng URI làm ý nghĩa của thao tác | Client phụ thuộc vào cấu trúc path | Dùng quan hệ có ý nghĩa như `cancel`, `orders`. |
| Luôn trả liên kết hủy dù đơn đã giao | Client nhìn thấy hành động không còn hợp lệ | Chỉ thêm liên kết theo trạng thái và quyền phù hợp. |
| Cho rằng có liên kết nghĩa là được phép gọi | Request trực tiếp vẫn có thể vượt qua giao diện client | Kiểm tra quyền và trạng thái ở máy chủ. |
| Đổi ý nghĩa của một relation đã công bố | Client cũ diễn giải sai hành động | Giữ ngữ nghĩa ổn định hoặc công bố relation mới. |
| Lặp logic tạo link ở nhiều nơi | Các phản hồi cùng loại tài nguyên không nhất quán | Dùng `RepresentationModelAssembler`. |

## 10. Quy trình áp dụng

Khi bổ sung điều hướng hypermedia cho một tài nguyên, có thể thực hiện theo trình tự sau:

1. Xác định tài nguyên và các trạng thái nghiệp vụ mà API cần biểu diễn.
2. Đặt tên các quan hệ liên kết theo ý nghĩa mà client cần hiểu, ví dụ `self`, `orders`, `cancel`.
3. Chọn kiểu mô hình: `EntityModel` cho một đối tượng, `CollectionModel` cho tập hợp, `PagedModel` cho trang kết quả hoặc `RepresentationModel` cho kiểu biểu diễn riêng.
4. Dùng `linkTo(methodOn(...))` để tạo URI theo mapping của controller.
5. Chỉ thêm liên kết hành động khi thao tác khả dụng; dùng affordance khi client cần metadata về cách thực hiện.
6. Chọn HAL hoặc HAL-FORMS phù hợp với nhu cầu biểu diễn và khả năng client.
7. Kiểm thử quan hệ, media type và điều kiện xuất hiện của liên kết ở các trạng thái khác nhau.

Điều hướng bằng liên kết là một phần của hợp đồng REST. Khi quan hệ được đặt tên rõ ràng, được tạo nhất quán và được kiểm thử theo hành vi, client có thể khám phá tài nguyên và hành động qua phản hồi của máy chủ, còn ứng dụng có thêm không gian để thay đổi cách tổ chức URI mà không buộc mọi client phải biết trước từng đường dẫn.
