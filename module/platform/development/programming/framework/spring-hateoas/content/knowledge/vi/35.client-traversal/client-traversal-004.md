# Theo link đến item

Một API quản lý đơn hàng có thể trả về collection gồm nhiều đơn hàng. Mỗi phần tử trong collection là một representation riêng và có thể có URI canonical để client đọc chi tiết. Client cần biết URI của item được chọn mà không tự ghép `/api/orders/{id}` từ ID trong JSON. Với hypermedia, collection trả link `self` cho từng item; client chọn item phù hợp rồi theo chính link đó.

Trong HAL, collection thường biểu diễn item trong `_embedded`. Mỗi item có thể mang `_links.self` trỏ đến representation riêng của nó. Cần phân biệt link `self` ở cấp collection với link `self` ở từng item: một link trỏ đến toàn bộ collection, link còn lại trỏ đến một item cụ thể. Spring HATEOAS hỗ trợ xây dựng các link này ở server và cung cấp `Traverson` để client đi qua các relation trong response.

## Từ collection đến item

Giả sử client bắt đầu ở API root, theo relation `orders` đến collection, sau đó chọn một đơn hàng và theo link `self` của item:

```text
API root
  |
  | rel="orders"
  v
Orders collection
  |
  | _embedded.orders[0]._links.self
  v
Order item
```

Mỗi bước sử dụng một link được server công bố. Client không cần biết route của item hoặc quy tắc tạo URI từ ID.

Quá trình này thường có ba thao tác HTTP GET:

1. GET API root để khám phá link `orders`.
2. GET collection để nhận các item được nhúng và link của từng item.
3. GET `href` của item được chọn để lấy representation chi tiết.

Nếu client đã có collection response, bước đầu tiên có thể được bỏ qua. Nếu collection nhúng đầy đủ dữ liệu cần thiết và client không cần representation canonical, client có thể sử dụng trực tiếp embedded item mà không cần GET thêm.

## Phân biệt self link của collection và item

Một HAL collection có thể trông như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/ord-1042"
          }
        }
      },
      {
        "id": "ord-1043",
        "status": "PAID",
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

Hai cấp link có ý nghĩa khác nhau:

| Vị trí | Target | Mục đích |
| --- | --- | --- |
| `$._links.self` | Collection `/api/orders` | Nhận diện collection hiện tại và truy vấn đã thực hiện. |
| `$._embedded.orders[0]._links.self` | Item `ord-1042` | Điều hướng đến representation riêng của đơn hàng đầu tiên. |
| `$._embedded.orders[1]._links.self` | Item `ord-1043` | Điều hướng đến representation riêng của đơn hàng thứ hai. |

Relation `self` luôn được hiểu theo context chứa link. `self` ở cấp collection trỏ đến collection; `self` bên trong embedded item trỏ đến item. Không lấy `$._links.self` của collection rồi xem đó là URI của một phần tử.

## Vì sao item cần self link?

Embedded item có thể chứa một số field đủ để hiển thị danh sách, nhưng chưa chắc chứa mọi dữ liệu cần cho màn hình chi tiết hoặc thao tác tiếp theo. Self link cung cấp URI canonical để client lấy representation đầy đủ.

Self link của item cũng tách client khỏi cách server định tuyến. Server có thể chuyển item từ `/api/orders/ord-1042` sang `/commerce/purchases/ord-1042`; client vẫn theo `href` mới từ collection response.

Nếu server chỉ trả ID mà không có link item, client phải tự suy ra route. Khi đó API đang buộc client phụ thuộc vào cấu trúc URI và không cung cấp đủ thông tin hypermedia để điều hướng đến item.

## Tạo item representation bằng Spring HATEOAS

Ở server, dùng `EntityModel<T>` để bọc dữ liệu của một item cùng link. `RepresentationModelAssembler` giúp áp dụng cùng quy tắc cho mọi item trong collection.

Ví dụ DTO cho đơn hàng:

```java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderView(UUID id, String status) {

    static OrderView from(Order order) {
        return new OrderView(order.getId(), order.getStatus().name());
    }
}
```

`collectionRelation = "orders"` xác định tên relation trong `_embedded` khi serialize collection. Việc khai báo rõ relation giúp API không phụ thuộc vào quy tắc pluralization mặc định của kiểu Java.

Assembler thêm self link cho từng item:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderView>> {

    @Override
    public EntityModel<OrderView> toModel(Order order) {
        return EntityModel.of(
            OrderView.from(order),
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel()
        );
    }
}
```

`methodOn(...)` ghi nhận method mapping và tham số path variable để tạo URI. Nó không gọi controller hoặc service. Mỗi item được chuyển thành `EntityModel<OrderView>` với `self` link trỏ đến endpoint đọc item.

Controller công bố collection và item endpoint:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
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
    EntityModel<OrderView> one(@PathVariable("id") UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }
}
```

`toCollectionModel(...)` áp dụng assembler cho từng phần tử. Link `self` được thêm vào collection model sau khi các item đã có self link riêng. Endpoint `one(...)` trả cùng kiểu item representation mà link của từng phần tử trỏ đến.

## HAL response sau khi serialize

Với `Accept: application/hal+json`, Spring HATEOAS serialize collection model thành HAL. Kết quả có thể có dạng:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ord-1042",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/ord-1042"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
```

Điểm quan trọng là mỗi embedded item có link riêng. `CollectionModel` chỉ bọc collection và các link cấp collection; các phần tử là `EntityModel` nên mang được link của chính chúng.

Nếu collection chỉ chứa POJO như `CollectionModel<OrderView>` thay vì `CollectionModel<EntityModel<OrderView>>`, item có thể không có self link. Nếu client cần điều hướng từ collection đến item, hãy bảo đảm mỗi item được enrich bằng link hoặc representation cung cấp một quan hệ item tương đương đã được tài liệu hóa.

## Đọc item link bằng Traverson

Spring HATEOAS cung cấp `Traverson` để client khám phá và theo link theo relation. `Traverson` nhận URI bắt đầu và media type mà client muốn dùng. Với HAL, chọn `MediaTypes.HAL_JSON`.

Ví dụ đi từ API root đến item đầu tiên trong embedded collection:

```java
import java.net.URI;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

URI apiRoot = URI.create("https://api.example.com/api/");

Traverson traverson = new Traverson(apiRoot, MediaTypes.HAL_JSON);

ParameterizedTypeReference<EntityModel<OrderView>> itemType =
    new ParameterizedTypeReference<>() {};

EntityModel<OrderView> firstOrder = traverson
    .follow("orders")
    .follow("$._embedded.orders[0]._links.self.href")
    .toObject(itemType);
```

Các bước thực hiện:

1. `Traverson` gửi GET đến URI root và yêu cầu HAL JSON.
2. `.follow("orders")` tìm link có relation `orders` trong root response và GET collection.
3. `.follow("$._embedded.orders[0]._links.self.href")` dùng JSONPath để lấy `href` self của embedded item đầu tiên rồi GET item đó.
4. `.toObject(itemType)` chuyển representation cuối cùng thành `EntityModel<OrderView>`.

`follow(...)` có thể nhận relation name hoặc biểu thức JSONPath bắt đầu bằng `$`. Mỗi hop cần đọc representation trước để tìm link cho hop kế tiếp; do đó chuỗi trên thực hiện một request cho mỗi bước điều hướng.

Ví dụ dùng index `[0]` chỉ để minh họa cách lấy item đầu tiên. Ứng dụng thực tế nên chọn item theo dữ liệu hoặc tiêu chí nghiệp vụ, không mặc định phần tử đầu tiên luôn là item người dùng cần.

## Lấy link trước, tải item sau

Đôi khi client chỉ cần biết URI của item để hiển thị liên kết, hoặc muốn quyết định thời điểm tải chi tiết. `Traverson.TraversalBuilder.asLink()` trả về link được tìm thấy ở relation cuối cùng mà không cần lấy representation của target cuối cùng.

```java
import org.springframework.hateoas.Link;

Link firstOrderLink = traverson
    .follow("orders")
    .follow("$._embedded.orders[0]._links.self.href")
    .asLink();

String itemUri = firstOrderLink.getHref();
```

Nếu cần representation của item, dùng `.toObject(...)` như ví dụ trước. Nếu chỉ cần link, `.asLink()` tránh GET cuối cùng. `asTemplatedLink()` có thể được dùng khi cần lấy URI template chưa mở rộng.

## Chọn item theo dữ liệu, không theo vị trí

Index trong JSONPath phù hợp cho ví dụ đơn giản, nhưng không phải cách chọn item bền vững. Thứ tự collection có thể thay đổi theo sort, filter hoặc dữ liệu mới.

Trong ứng dụng thực tế:

1. Theo link collection để lấy `CollectionModel`.
2. Chọn embedded item theo thuộc tính nghiệp vụ mà client đang hiển thị hoặc theo kết quả tìm kiếm.
3. Đọc `self` link từ `EntityModel` đã chọn.
4. Gửi GET đến `href` đó bằng HTTP client đã cấu hình để đọc HAL.

Ví dụ đọc collection bằng `Traverson`:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

ParameterizedTypeReference<CollectionModel<EntityModel<OrderView>>> collectionType =
    new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<OrderView>> orders = traverson
    .follow("orders")
    .toObject(collectionType);

EntityModel<OrderView> selected = orders.getContent().stream()
    .filter(item -> item.getContent().id().equals(selectedOrderId))
    .findFirst()
    .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy đơn hàng"));

Link itemLink = selected.getRequiredLink(IanaLinkRelations.SELF);
```

Đoạn code minh họa việc chọn item đã được nhúng trong collection và lấy self link. `selectedOrderId` là ID client muốn chọn. Khi cần tải representation chi tiết, gửi GET đến `itemLink.getHref()` bằng `RestTemplate` hoặc HTTP client được cấu hình hypermedia phù hợp.

Không tạo lại URI bằng `selected.getContent().id()`; ID chỉ dùng để chọn item, còn `href` là địa chỉ điều hướng do server cung cấp.

## Dùng LinkDiscoverer khi đã có response body

Nếu client đã nhận raw HAL JSON từ một HTTP client khác, có thể dùng `LinkDiscoverer` để tìm link theo relation thay vì tự đọc cấu trúc JSON:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.HalLinkDiscoverer;
import org.springframework.hateoas.client.LinkDiscoverer;

LinkDiscoverer discoverer = new HalLinkDiscoverer();

Link collectionLink = discoverer.findLinkWithRel("orders", rootJson);
```

`LinkDiscoverer` tìm link theo relation trong representation. Để tìm self link của một item, client cần trích xuất representation của item đã chọn hoặc deserialize collection thành `CollectionModel<EntityModel<OrderView>>`, sau đó đọc link từ model tương ứng.

`Traverson` mặc định đăng ký `HalLinkDiscoverer`. Nếu API dùng media type hypermedia khác, client cần link discoverer và message converter phù hợp với định dạng đó.

## URI của item có thể là relative URI

`href` không nhất thiết luôn là absolute URI. Server có thể trả link tương đối, ví dụ:

```json
{
  "_links": {
    "self": {
      "href": "/api/orders/ord-1042"
    }
  }
}
```

Client cần giải quyết relative reference dựa trên URI của representation chứa link theo quy tắc URI, không nối chuỗi với base URL một cách thủ công. `Traverson` và các link-aware client xử lý việc điều hướng từ URI được khám phá. Nếu tự viết client, dùng URI resolution như `baseUri.resolve(relativeHref)` và bảo đảm base URI là URI thực tế của response chứa link.

Không giả định item luôn nằm dưới path của collection. Link có thể trỏ đến host khác, route khác hoặc resource được cung cấp bởi một service khác. Client cần áp dụng chính sách tin cậy và xác thực phù hợp trước khi gửi thông tin nhạy cảm đến target đó.

## Theo link đến item trong collection có phân trang

Một collection có phân trang chỉ nhúng item của trang hiện tại. Nếu item người dùng cần không nằm trong page đang xem, client cần dùng link `next`, `prev`, `first`, `last` hoặc search link mà server công bố.

Không tự tăng `page` hoặc ghép `?page=2` nếu response đã cung cấp link điều hướng. Client theo `next.href`, nhận page mới rồi tiếp tục tìm item. Nếu cần tìm một item theo mã hoặc thuộc tính, nên dùng search template hoặc filter link để giảm số page phải duyệt.

Pagination và item traversal là hai cấp điều hướng:

- Page links điều hướng giữa các phần của collection.
- Item self links điều hướng từ collection đến representation riêng của từng item.

Không dùng `next` như link đến item kế tiếp trong collection. `next` trỏ đến page kế tiếp, còn self link bên trong embedded item trỏ đến item cụ thể.

## Truyền header và xác thực khi follow link

Nếu API yêu cầu bearer token, `Traverson.TraversalBuilder.withHeaders(...)` có thể cung cấp header cho các request trong traversal:

```java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

EntityModel<OrderView> firstOrder = traverson
    .follow("orders")
    .follow("$._embedded.orders[0]._links.self.href")
    .withHeaders(headers)
    .toObject(itemType);
```

Header được dùng cho các request trong traversal. Nếu link chuyển sang host hoặc origin khác, không chuyển tiếp bearer token hoặc cookie một cách mù quáng. Client cần kiểm tra target origin và áp dụng chính sách credential phù hợp.

Link không cấp quyền truy cập. Server vẫn phải xác thực và phân quyền tại endpoint item, kể cả khi self link được công bố trong collection. Một item có thể biến mất hoặc trở nên không thể truy cập sau khi collection được trả về.

## Xử lý lỗi khi theo item link

Giữa lúc client đọc collection và lúc client follow self link, trạng thái dữ liệu có thể thay đổi. Một số tình huống:

| HTTP status | Tình huống có thể gặp | Cách xử lý phía client |
| --- | --- | --- |
| `401 Unauthorized` | Token thiếu, hết hạn hoặc không hợp lệ. | Làm mới/xác thực lại theo cơ chế bảo mật của ứng dụng. |
| `403 Forbidden` | User không còn quyền đọc item. | Hiển thị trạng thái phù hợp; không thử dựng URI khác để vượt quyền. |
| `404 Not Found` | Item đã bị xóa hoặc link đã cũ. | Cập nhật collection hoặc thông báo item không còn tồn tại. |
| `410 Gone` | Resource đã bị loại bỏ có chủ đích. | Dừng follow link cũ và cập nhật trạng thái phía client. |
| `406 Not Acceptable` | Client yêu cầu media type mà endpoint không hỗ trợ. | Gửi `Accept` phù hợp với API. |
| `429 Too Many Requests` | Client follow quá nhanh hoặc vượt rate limit. | Tuân thủ `Retry-After` nếu server gửi và áp dụng backoff. |

GET là thao tác an toàn và idempotent theo semantics HTTP, nhưng client vẫn cần giới hạn retry và tránh tạo vòng lặp traversal. Không tự động retry vô hạn khi link lỗi hoặc response không hợp lệ.

## Kiểm thử item link ở server

Kiểm thử collection response để xác nhận từng embedded item có self link trỏ đúng item endpoint:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
        .value(endsWith("/api/orders/ord-1042")));
```

Test này phân biệt rõ collection self link và item self link. Cần có test riêng cho endpoint item để xác nhận URI đó trả representation đúng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists());
```

## Kiểm thử traversal từ client

Một integration test có thể chạy ứng dụng trên cổng ngẫu nhiên, tạo `Traverson` với URI root rồi theo link đến item:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

ParameterizedTypeReference<EntityModel<OrderView>> itemType =
    new ParameterizedTypeReference<>() {};

Traverson traverson = new Traverson(
    URI.create("http://localhost:" + port + "/api/"),
    MediaTypes.HAL_JSON);

EntityModel<OrderView> item = traverson
    .follow("orders")
    .follow("$._embedded.orders[0]._links.self.href")
    .toObject(itemType);

assertThat(item.getContent().id()).isEqualTo(expectedOrderId);
assertThat(item.hasLink(IanaLinkRelations.SELF)).isTrue();
```

Test này xác minh client thật sự khám phá collection relation và item self link, thay vì chỉ kiểm tra một URI được ghép sẵn. Dữ liệu test cần bảo đảm item đầu tiên có ID đã biết; nếu thứ tự collection không ổn định, hãy cố định sort hoặc dùng filter để chọn item.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ trả ID trong embedded item | Client phải tự tạo URI item. | Thêm self link cho từng item representation. |
| Dùng self link cấp collection để tải item | Client nhận collection thay vì một item. | Đọc `self` nằm bên trong embedded item đã chọn. |
| Dùng `CollectionModel<OrderView>` khi cần item links | Embedded item có thể không mang link riêng. | Dùng `CollectionModel<EntityModel<OrderView>>` hoặc representation item có link. |
| Chọn item bằng index cố định trong ứng dụng thật | Thứ tự thay đổi có thể khiến client mở nhầm item. | Chọn theo dữ liệu, filter hoặc search rồi theo self link. |
| Tự ghép `/orders/{id}` | Client phụ thuộc vào route và cấu trúc ID. | Dùng `href` được server công bố. |
| Nhầm `next` với item kế tiếp | Client chuyển sang page khác thay vì item cần xem. | Dùng page relation cho collection và item self link cho item. |
| Giả định embedded item là representation đầy đủ | Client có thể thiếu dữ liệu hoặc affordance. | Theo self link khi cần representation canonical/chi tiết. |
| Gửi credential đến mọi host trong link | Có thể làm lộ token hoặc cookie. | Kiểm tra origin và chính sách credential trước khi follow. |
| Nghĩ link đảm bảo item vẫn tồn tại hoặc được phép đọc | Request có thể trả 403/404/410. | Xử lý lỗi và authorization như mọi HTTP request. |

## Ghi nhớ

- Collection self link trỏ đến collection; self link trong embedded item trỏ đến item.
- HAL đặt các item nhúng dưới `_embedded`; mỗi item cần link riêng nếu client phải điều hướng đến nó.
- Dùng `EntityModel<T>` cho item và `CollectionModel<EntityModel<T>>` cho collection có item links.
- `RepresentationModelAssembler` giúp tạo self link nhất quán cho từng item.
- `Traverson.follow(...)` theo relation hoặc JSONPath; `.toObject(...)` lấy representation cuối cùng.
- `.asLink()` lấy link cuối cùng khi client chỉ cần URI mà chưa cần tải item.
- Chọn item theo dữ liệu hoặc search/filter; index chỉ phù hợp ví dụ minh họa.
- Theo page links để duyệt collection phân trang và theo item self link để đọc item.
- Dùng `href` thay vì dựng route từ ID; xử lý relative URI và credential cẩn thận.
- Kiểm thử cả HAL response phía server và traversal thực tế phía client.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Client-side Support / Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson)
- [Spring HATEOAS Reference Documentation – Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS API – Traverson](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Spring HATEOAS API – Traverson.TraversalBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.TraversalBuilder.html)
- [Spring HATEOAS API – LinkDiscoverer](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/LinkDiscoverer.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [RFC 3986 – URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
