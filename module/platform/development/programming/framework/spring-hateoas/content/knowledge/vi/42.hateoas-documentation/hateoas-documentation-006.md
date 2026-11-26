# Ví dụ điều hướng

Một client quản lý đơn hàng cần bắt đầu từ API, tìm collection đơn hàng, chọn một đơn cụ thể, đọc chi tiết rồi thực hiện thao tác hủy nếu đơn vẫn đang chờ xử lý. Nếu client tự ghép các đường dẫn như `/api/orders`, `/api/orders/{id}` và `/api/orders/{id}/cancellation`, nó phụ thuộc vào cấu trúc route của server. Khi API thay đổi đường dẫn, client phải được sửa theo.

Spring HATEOAS cho phép server trả representation kèm các link mô tả tài nguyên và thao tác có thể khám phá. Client bắt đầu tại một URI đã biết, sau đó đi theo relation và `href` mà response cung cấp. Bài này xây dựng một luồng điều hướng hoàn chỉnh cho Orders API: **API root → collection → item → action**.

## Luồng điều hướng tổng thể

Giả sử client chỉ được cấu hình URI gốc `https://api.example.com/api`. Từ URI đó, client khám phá các tài nguyên:

```text
Client
  |
  | GET /api
  v
API root
  |
  | rel="acme:orders"
  v
Orders collection
  |
  | _embedded.orders[n]._links.self
  v
Order item
  |
  | rel="acme:cancel" (nếu đơn còn PENDING)
  v
Cancellation action
  |
  | POST theo hợp đồng của relation
  v
Updated order representation
```

Mỗi bước đều lấy target URI từ response hiện tại. Client không cần suy ra path từ ID hoặc tự tạo query string. `relation` cho biết ý nghĩa của link; `href` cho biết nơi cần điều hướng.

## Xây dựng các relation của Orders API

API dùng hai extension relations:

| Relation URI | CURIE trong HAL | Ý nghĩa |
| --- | --- | --- |
| `https://api.example.com/rels/orders` | `acme:orders` | Collection các đơn hàng mà client hiện tại có thể truy cập. |
| `https://api.example.com/rels/cancel` | `acme:cancel` | Target thực hiện yêu cầu hủy đơn hàng nếu trạng thái và quyền cho phép. |

`self` là relation chuẩn dùng để trỏ đến chính resource hiện tại. Các relation riêng của API dùng URI do tổ chức kiểm soát. Không dùng chuỗi ngắn tùy ý làm extension relation nếu API cần công bố relation theo HAL; CURIE giúp rút gọn URI trong JSON.

Khai báo relation tập trung:

```java
import org.springframework.hateoas.LinkRelation;

final class OrderRelations {

    static final LinkRelation ORDERS = LinkRelation.of(
        "https://api.example.com/rels/orders");

    static final LinkRelation CANCEL = LinkRelation.of(
        "https://api.example.com/rels/cancel");

    private OrderRelations() {
    }
}
```

Định nghĩa CURIE provider cho HAL:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
            "acme",
            new UriTemplate("https://api.example.com/rels/{rel}"));
    }
}
```

Khi serialize HAL, relation URI `https://api.example.com/rels/orders` có thể xuất hiện dưới tên `acme:orders`. CURIE là cách viết tắt trong representation; định danh đầy đủ vẫn là URI relation đã khai báo.

## Bước 1: Tạo API root

API root là điểm bắt đầu mà client biết trước. Root không cần chứa toàn bộ dữ liệu đơn hàng; nó chỉ công bố các resource chính và link tự tham chiếu.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class ApiRootController {

    @GetMapping(path = "/api", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<ApiInfo> root() {
        return EntityModel.of(
            new ApiInfo("Orders API", "Quản lý đơn hàng"),
            linkTo(methodOn(ApiRootController.class).root()).withSelfRel(),
            linkTo(methodOn(OrderController.class).all())
                .withRel(OrderRelations.ORDERS)
        );
    }
}

record ApiInfo(String name, String description) {
}
```

`linkTo(methodOn(...))` lấy URI từ mapping của controller. Khi mapping collection đổi, link được tạo từ mapping mới mà không cần client biết route mới. `methodOn(...)` tạo proxy để ghi nhận method và tham số, không gọi thân controller hoặc service.

Một root response HAL minh họa:

```json
{
  "name": "Orders API",
  "description": "Quản lý đơn hàng",
  "_links": {
    "self": {
      "href": "https://api.example.com/api"
    },
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "acme:orders": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
```

Client chỉ cần biết URI `/api` và media type `application/hal+json`. Nó tìm relation `acme:orders` để đến collection.

## Bước 2: Tạo collection representation

Mỗi item trong collection cần có self link nếu client có thể điều hướng đến representation riêng của item. Dùng `EntityModel<T>` để bọc dữ liệu và link của item; dùng `CollectionModel<T>` để biểu diễn tập hợp.

DTO đơn hàng:

```java
import java.math.BigDecimal;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(String id, String status, BigDecimal total) {

    static OrderView from(Order order) {
        return new OrderView(
            order.getId().toString(),
            order.getStatus().name(),
            order.getTotal());
    }
}
```

`collectionRelation = "orders"` xác định tên relation của mảng embedded trong HAL. DTO chỉ công bố các trường client cần; không serialize trực tiếp toàn bộ entity domain.

Assembler tạo self link và action link theo trạng thái:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        EntityModel<OrderView> model = EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.getId().toString()))
                .withSelfRel());

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId().toString()))
                .withRel(OrderRelations.CANCEL));
        }

        return model;
    }
}
```

Trong ví dụ, `canBeCancelled()` trả về true khi đơn ở trạng thái cho phép hủy, chẳng hạn `PENDING`. Ứng dụng thực tế cần kết hợp cả authorization của principal hiện tại khi quyết định có công bố action link hay không. Endpoint hủy vẫn phải kiểm tra quyền và trạng thái khi nhận request; ẩn link không thay thế authorization.

Controller công bố collection và item endpoint:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping(path = "/api/orders", produces = MediaTypes.HAL_JSON_VALUE)
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        return assembler.toCollectionModel(orderService.findAll())
            .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable("id") String id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @PostMapping("/{id}/cancellation")
    EntityModel<OrderView> cancel(@PathVariable("id") String id) {
        return assembler.toModel(orderService.cancel(id));
    }
}
```

`OrderService` là thành phần nghiệp vụ của ứng dụng. `findAll()` trả về các đơn có thể xem trong phạm vi người dùng hiện tại; `getRequired(...)` tìm một đơn hoặc trả lỗi phù hợp; `cancel(...)` thực hiện quy tắc hủy và trả trạng thái mới.

Collection response HAL có thể có dạng:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "total": 1250000,
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/ord-1042"
          },
          "acme:cancel": {
            "href": "https://api.example.com/api/orders/ord-1042/cancellation"
          }
        }
      },
      {
        "id": "ord-1043",
        "status": "PAID",
        "total": 890000,
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/ord-1043"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
```

Đơn `ord-1042` có link `acme:cancel` vì đang chờ xử lý. Đơn `ord-1043` đã thanh toán nên không công bố link này. Self link ở cấp collection trỏ đến collection; self link bên trong từng item trỏ đến item tương ứng.

## Bước 3: Client theo relation đến collection

Spring HATEOAS cung cấp `Traverson` cho client muốn khám phá và theo các link trong representation. `Traverson` nhận URI bắt đầu và media type của hypermedia response.

```java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

URI apiRoot = URI.create("https://api.example.com/api");

Traverson traverson = new Traverson(apiRoot, MediaTypes.HAL_JSON);
```

Để lấy collection, client follow relation `acme:orders`:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

ParameterizedTypeReference<CollectionModel<EntityModel<OrderView>>> collectionType =
    new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<OrderView>> orders = traverson
    .follow("acme:orders")
    .toObject(collectionType);
```

`Traverson` đọc root response, tìm relation `acme:orders`, gửi GET đến `href` rồi chuyển collection response thành `CollectionModel`. Client không cần biết collection nằm ở `/api/orders`.

Nếu muốn lấy item đầu tiên trong embedded collection bằng một traversal expression, có thể dùng JSONPath:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;

ParameterizedTypeReference<EntityModel<OrderView>> orderType =
    new ParameterizedTypeReference<>() {};

EntityModel<OrderView> firstOrder = traverson
    .follow("acme:orders")
    .follow("$._embedded.orders[0]._links.self.href")
    .toObject(orderType);
```

`follow(...)` đầu tiên tìm collection relation; `follow(...)` thứ hai lấy self link của embedded item đầu tiên rồi GET target. Index `[0]` chỉ phù hợp minh họa hoặc test có dữ liệu cố định. Ứng dụng thật nên chọn item theo tiêu chí nghiệp vụ hoặc để người dùng chọn từ danh sách.

## Bước 4: Chọn item rồi theo self link

Nếu cần chọn item theo ID hoặc thuộc tính, deserialize collection rồi lấy self link từ item đã chọn:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

String selectedOrderId = "ord-1042";

EntityModel<OrderView> selected = orders.getContent().stream()
    .filter(item -> item.getContent().id().equals(selectedOrderId))
    .findFirst()
    .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy đơn hàng"));

Link itemSelf = selected.getRequiredLink(IanaLinkRelations.SELF);
String itemHref = itemSelf.getHref();
```

ID chỉ được dùng để chọn item trong collection. URI điều hướng lấy từ `self` link của item. Không tạo URL bằng phép nối chuỗi như `"/api/orders/" + selectedOrderId`.

Nếu embedded representation đã chứa đủ dữ liệu cần dùng, client có thể hiển thị ngay mà không GET item thêm lần nữa. Nếu cần representation canonical hoặc dữ liệu chi tiết, client gửi GET đến `itemHref` bằng HTTP client có cấu hình message converter HAL phù hợp.

## Bước 5: Khám phá action link

Sau khi lấy item representation, client kiểm tra relation `acme:cancel`:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link cancelLink = selected.getLink(LinkRelation.of(
    "https://api.example.com/rels/cancel"))
    .orElse(null);

if (cancelLink != null) {
    String cancelHref = cancelLink.getHref();
    // Chỉ thực hiện khi client hỗ trợ semantics của relation này.
}
```

Nếu relation không xuất hiện, client không nên giả định thao tác hủy đang khả dụng. Link có thể vắng mặt vì trạng thái đơn hàng, quyền của người dùng hoặc chính sách API.

### Link HAL không tự mô tả HTTP method và request body

Một link HAL thông thường cung cấp relation và `href`; nó không tự mô tả đầy đủ rằng target phải được gọi bằng `POST`, body có schema gì hoặc cần header nào. API cần tài liệu hóa contract của `acme:cancel`. Trong ví dụ này, contract quy định:

| Thành phần | Giá trị |
| --- | --- |
| Relation | `acme:cancel` |
| Method | `POST` |
| Target | `href` của link trong item representation |
| Request body | Không cần body trong ví dụ |
| Authentication | Bearer token theo chính sách API |
| Kết quả | Representation đơn hàng sau khi hủy hoặc lỗi nghiệp vụ |

Nếu client cần khám phá method và input một cách máy đọc được, hãy công bố affordance phù hợp và dùng media type như HAL-FORMS. `Traverson` chủ yếu hỗ trợ GET traversal; nó không tự suy ra rồi thực thi POST chỉ từ một HAL link.

### Gọi action bằng HTTP client

Sau khi tìm được link, client dùng `href` cùng method đã được relation contract hoặc affordance mô tả:

```java
import java.net.URI;

import org.springframework.http.HttpHeaders;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.client.RestClient;

URI cancelUri = URI.create(cancelLink.getHref());

RestClient restClient = RestClient.builder().build();

restClient.post()
    .uri(cancelUri)
    .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
    .accept(MediaTypes.HAL_JSON)
    .retrieve()
    .toBodilessEntity();
```

Ví dụ giả định server trả `cancelLink.href` là URI tuyệt đối và `RestClient` đã được cấu hình cho môi trường ứng dụng. Nếu link là relative URI, resolve nó dựa trên URI thực tế của representation đã chứa link. Trong luồng đang chọn item từ `_embedded`, base URI là URI của collection response; nếu client GET item riêng rồi đọc action link từ response item, base URI là URI item đó. Với cross-origin target, client phải kiểm tra origin trước khi gửi credential; không chuyển bearer token đến host bất kỳ chỉ vì response chứa một link.

Trong ứng dụng cần đọc response HAL sau thao tác, hãy cấu hình HTTP client với converter hypermedia phù hợp và deserialize response thành `EntityModel<OrderView>`. Nếu API trả `204 No Content`, client cần GET lại item qua self link để nhận trạng thái mới.

## Bước 6: Theo pagination link

Nếu collection có phân trang, response có thể công bố `first`, `prev`, `next` và `last`. Client dùng relation để chuyển page:

```java
CollectionModel<EntityModel<OrderView>> nextPage = traverson
    .follow("acme:orders")
    .follow("next")
    .toObject(collectionType);
```

Hoặc sau khi đã có representation collection, lấy `next` link rồi follow target đó. Client không tự tăng `page=1` hoặc ghép query string. Server chịu trách nhiệm giữ lại filter, sort và page size trong `href`.

Ở trang cuối, relation `next` có thể không tồn tại. Client cần xem việc vắng mặt của link là dấu hiệu không có page tiếp theo; không tự tạo URI kế tiếp.

## Bước 7: Xử lý kết quả và điều hướng tiếp

Sau khi gửi POST đến cancellation target, server có thể trả representation đơn hàng đã cập nhật. Ví dụ:

```json
{
  "id": "ord-1042",
  "status": "CANCELLED",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    }
  }
}
```

Link `acme:cancel` không còn xuất hiện vì đơn đã hủy. Client nên dùng representation mới nhận được để cập nhật UI và tập thao tác khả dụng. Không giữ lại action link cũ như thể nó vẫn còn hiệu lực.

Nếu server trả `202 Accepted`, client cần follow `monitor` hoặc `status` link để theo dõi công việc bất đồng bộ. Không gửi lại POST chỉ vì thao tác chưa hoàn tất. Nếu target trả `403`, `404`, `409` hoặc lỗi khác, client xử lý theo status và Problem Details; link cũ không đảm bảo trạng thái resource vẫn như lúc link được tạo.

## Xử lý relative URI và host công khai

Một `href` có thể là absolute URI hoặc relative reference. Client cần resolve relative link dựa trên URI của representation đã chứa link, theo quy tắc URI. Không nối chuỗi thủ công với API root vì target có thể nằm ở route khác hoặc service khác.

Với Spring MVC chạy sau reverse proxy, link builder cần nhìn thấy scheme, host và prefix công khai. Cấu hình forwarded headers phải chỉ tin proxy đáng tin cậy. Nếu link được tạo ngoài request context, dùng public base URI từ cấu hình thay vì hostname nội bộ.

Client cũng cần kiểm tra scheme và origin trước khi gửi credential hoặc tự động follow target. Điều này ngăn rò rỉ token và hạn chế SSRF đối với client chạy phía server.

## Kiểm thử luồng điều hướng

Kiểm thử riêng từng endpoint giúp phát hiện sai mapping; integration test traversal chứng minh client thực sự theo link mà server trả về.

### Kiểm tra API root

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links['acme:orders'].href").exists());
```

### Kiểm tra collection và item links

```java
mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links['acme:cancel'].href")
        .exists());
```

Test trên giả định item đầu tiên đang ở trạng thái cho phép hủy. Với item `PAID`, viết test riêng để xác nhận link `acme:cancel` không xuất hiện.

### Kiểm tra traversal qua server đang chạy

`Traverson` gọi HTTP thật nên integration test cần khởi động ứng dụng, ví dụ bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, rồi follow relation từ root:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderNavigationIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void followsRootToOrderItem() {
        URI root = URI.create("http://localhost:" + port + "/api");
        Traverson traverson = new Traverson(root, MediaTypes.HAL_JSON);

        ParameterizedTypeReference<EntityModel<OrderView>> orderType =
            new ParameterizedTypeReference<>() {};

        EntityModel<OrderView> order = traverson
            .follow("acme:orders")
            .follow("$._embedded.orders[0]._links.self.href")
            .toObject(orderType);

        assertThat(order.getContent()).isNotNull();
        assertThat(order.hasLink("self")).isTrue();
    }
}
```

Test giả định fixture có ít nhất một đơn hàng và CURIE `acme` đã được cấu hình. Bổ sung static import `org.junit.jupiter.api.Test` khi dùng đoạn code trong test class. Nếu thứ tự collection không cố định, hãy seed một item xác định hoặc dùng filter/sort rõ ràng thay vì dựa vào phần tử đầu tiên.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Client hard-code `/api/orders` và `/api/orders/{id}` | Client phụ thuộc vào route server. | Bắt đầu từ root rồi follow relation và `href`. |
| Chỉ trả ID trong embedded item | Client phải tự dựng URI item. | Thêm self link cho từng item representation. |
| Nhầm self link collection với self link item | Client GET collection thay vì item. | Đọc self link nằm trong embedded item đã chọn. |
| Dùng index cố định trong production | Thứ tự collection đổi có thể làm chọn nhầm item. | Chọn theo dữ liệu hoặc search/filter relation. |
| Nghĩ HAL link tự mô tả POST và body | Client không biết method/input của action. | Tài liệu hóa relation contract hoặc công bố affordance/HAL-FORMS. |
| Dùng Traverson để tự thực hiện write action | Traverson tập trung vào GET traversal. | Dùng HTTP client với method đã được contract/affordance mô tả. |
| Gọi action dù link không còn xuất hiện | Thao tác có thể không hợp lệ hoặc user không có quyền. | Dùng representation mới và xử lý lỗi; endpoint vẫn authorize. |
| Tự ghép page number | Bỏ qua filter, sort hoặc pagination policy của server. | Follow `next.href` khi relation có mặt. |
| Resolve relative URI từ sai base | Client đi đến target sai. | Resolve dựa trên URI của representation chứa link. |
| Gửi token đến mọi host trong link | Có thể làm lộ credential. | Kiểm tra origin và trust policy trước khi gửi header. |

## Ghi nhớ

- Client chỉ cần biết URI entry point và media type ban đầu; các bước sau khám phá bằng hypermedia.
- API root công bố collection links; collection công bố item self links; item công bố action links theo trạng thái.
- `EntityModel` biểu diễn một item có link; `CollectionModel` biểu diễn tập hợp; assembler tạo link nhất quán.
- `WebMvcLinkBuilder` và `methodOn()` tạo target URI từ controller mapping.
- Dùng CURIE để rút gọn extension relation URI trong HAL.
- `Traverson.follow()` theo relation hoặc JSONPath; `.toObject()` chuyển representation cuối thành model.
- Chọn item theo dữ liệu và lấy `self` link; không ghép URI từ ID.
- HAL link thông thường không tự mô tả method/body; write action cần relation contract hoặc affordance như HAL-FORMS.
- Theo `next` link để phân trang; không tự tạo query parameter.
- Cập nhật UI từ response mới sau action; luôn xử lý lỗi và kiểm tra quyền tại endpoint.
- Resolve relative URI đúng base và chỉ gửi credential đến origin tin cậy.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS Reference – Client-side Support / Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson)
- [Spring HATEOAS Reference – Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS API – Traverson](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
