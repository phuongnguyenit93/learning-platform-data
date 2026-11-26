# `_embedded` trong HAL

Trong HAL (Hypertext Application Language), thuộc tính `_embedded` chứa representation của những tài nguyên được nhúng trực tiếp vào response hiện tại. Mỗi nhóm tài nguyên nhúng được đặt dưới một link relation, ví dụ `_embedded.orders`, `_embedded.customer` hoặc `_embedded.lineItems`. Nhờ vậy, client có thể đọc dữ liệu liên quan ngay trong response thay vì phải gửi thêm request cho từng tài nguyên.

Spring HATEOAS hỗ trợ cấu trúc này thông qua `CollectionModel`, `EntityModel` và đặc biệt là `HalModelBuilder`. `HalModelBuilder` cho phép kết hợp nội dung chính, các tài nguyên nhúng và các liên kết thành một HAL representation. Bài học tập trung vào cách tổ chức `_embedded`, cách đặt relation ổn định và cách chọn dữ liệu nên nhúng.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `_embedded` và quan hệ của nó với `_links` trong HAL.
- Đọc cấu trúc embedded resource đơn lẻ, collection và resource lồng nhau.
- Dùng `HalModelBuilder` để tạo representation có tài nguyên nhúng.
- Dùng `preview()` để trả preview gắn với một link.
- Dùng `@Relation` hoặc `LinkRelation` để kiểm soát tên thuộc tính trong `_embedded`.
- Xử lý collection rỗng và kiểm thử cấu trúc HAL bằng MockMvc.
- Cân nhắc kích thước response, độ mới dữ liệu và cache khi nhúng tài nguyên.

## `_embedded` dùng để làm gì?

HAL tách hai cách cung cấp thông tin liên quan:

- `_links` chứa các liên kết điều hướng. Mỗi liên kết cho biết URI đích và relation mô tả ý nghĩa của liên kết.
- `_embedded` chứa representation của tài nguyên liên quan ngay trong response. Các representation này cũng có thể có `_links` và `_embedded` riêng.

Ví dụ, response chi tiết đơn hàng có thể chứa dữ liệu khách hàng và các dòng hàng:

```json
{
  "id": 42,
  "status": "NEW",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "customer": {
      "href": "https://api.example.test/orders/42/customer"
    }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Nguyen An",
      "_links": {
        "self": {
          "href": "https://api.example.test/customers/7"
        }
      }
    },
    "lineItems": [
      {
        "productId": 301,
        "name": "Keyboard",
        "quantity": 1
      },
      {
        "productId": 412,
        "name": "Mouse",
        "quantity": 2
      }
    ]
  }
}
```

Ở đây:

- `customer` là relation của tài nguyên khách hàng được nhúng.
- `lineItems` là relation của tập hợp dòng hàng.
- `customer` xuất hiện cả trong `_links` và `_embedded`: link cho phép client điều hướng tới tài nguyên khách hàng, còn embedded representation cung cấp bản dữ liệu để client sử dụng ngay.
- Mỗi embedded resource có thể mang liên kết riêng, ví dụ `customer._links.self`.

HAL không bắt buộc mọi tài nguyên liên quan phải được nhúng. Server có thể chỉ công bố link trong `_links`, nhúng representation trong `_embedded`, hoặc cung cấp cả hai khi phù hợp với cách client tương tác.

## Cấu trúc và quy tắc relation

`_embedded` là một object JSON. Mỗi thuộc tính của nó được đặt tên theo link relation. Giá trị có thể là:

| Giá trị trong `_embedded` | Dùng khi | Ví dụ |
|---|---|---|
| Một object | Nhúng một tài nguyên | `"customer": { ... }` |
| Một array | Nhúng một tập hợp tài nguyên | `"lineItems": [{ ... }, { ... }]` |
| Array rỗng | Muốn biểu diễn rõ collection hiện không có phần tử | `"orders": []` |

Tên relation là một phần của hợp đồng API. Với Spring HATEOAS, relation cho embedded resource thường được xác định bởi `LinkRelationProvider`, có thể tùy chỉnh bằng `@Relation`. Nếu relation là nghiệp vụ riêng, hãy chọn tên ổn định và tài liệu hóa để client có thể tìm đúng nhóm dữ liệu.

Ví dụ khai báo relation cho các DTO:

```java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
record OrderView(long id, String status, long total) {
}

@Relation(itemRelation = "lineItem", collectionRelation = "lineItems")
record LineItemView(long productId, String name, int quantity) {
}
```

Khi Spring HATEOAS cần xác định relation cho một collection `OrderView`, relation collection `orders` được sử dụng. Với `LineItemView`, relation collection là `lineItems`. Khai báo tường minh giúp tránh phụ thuộc vào quy tắc số ít/số nhiều tự động, nhất là với thuật ngữ nghiệp vụ hoặc từ bất quy tắc.

## Tạo HAL representation bằng `HalModelBuilder`

`HalModelBuilder` nằm trong package `org.springframework.hateoas.mediatype.hal`. Đây là builder dành riêng cho HAL, cho phép tạo một representation có payload chính, các embedded resource và links.

Client thường yêu cầu representation bằng media type `application/hal+json`. Ví dụ request:

```http
GET /orders/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Ứng dụng Spring Boot dùng `spring-boot-starter-hateoas` thường đã được cấu hình để serialize model thành HAL. Với cấu hình Spring MVC tự quản lý, bật hỗ trợ HAL bằng `@EnableHypermediaSupport(type = HypermediaType.HAL)` hoặc đăng ký cấu hình message converter tương ứng. Khi `HalModelBuilder` tạo representation có embedded entries, builder cũng đánh dấu HAL và HAL-FORMS là các media type ưu tiên của model.

Các phương thức thường dùng:

| API | Vai trò |
|---|---|
| `halModelOf(entity)` | Tạo builder với entity làm payload chính |
| `emptyHalModel()` | Tạo builder không có payload chính, thường dùng cho collection ở cấp root |
| `embed(entity, relation)` | Nhúng một entity dưới relation chỉ định |
| `embed(collection, type)` | Nhúng collection và suy ra relation từ kiểu phần tử |
| `embed(collection, relation)` | Nhúng collection dưới relation chỉ định |
| `preview(entity).forLink(link)` | Thêm link và nhúng preview dưới cùng relation của link |
| `link(link)` | Thêm link ở cấp representation ngoài cùng |
| `build()` | Tạo `RepresentationModel` hoàn chỉnh |

Ví dụ đơn giản, tạo một representation có payload chính là đơn hàng và nhúng khách hàng:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var model = HalModelBuilder.halModelOf(orderView)
    .embed(customerSummary, LinkRelation.of("customer"))
    .build();
```

`orderView` là nội dung chính của representation. `customerSummary` được nhúng dưới relation `customer`, nên khi serialize thành HAL, nó xuất hiện tại `_embedded.customer`.

Đối với collection, truyền kiểu phần tử để Spring HATEOAS xác định relation:

```java
var model = HalModelBuilder.emptyHalModel()
    .embed(orderViews, OrderView.class)
    .build();
```

Với `@Relation(itemRelation = "order", collectionRelation = "orders")` trên `OrderView`, collection được đặt dưới `_embedded.orders`.

## Kết hợp link và embedded resource

Một quan hệ thường cần cả khả năng điều hướng lẫn dữ liệu preview. Ví dụ, client cần hiển thị tên khách hàng ngay trong trang đơn hàng nhưng vẫn có thể mở tài nguyên khách hàng đầy đủ khi người dùng chọn.

Spring HATEOAS cung cấp `preview()` để tạo đồng thời link và embedded preview:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

Link customerLink = Link.of(
    "/orders/42/customer",
    "customer"
);

var model = HalModelBuilder.halModelOf(orderView)
    .preview(customerSummary)
    .forLink(customerLink)
    .build();
```

Kết quả có cả `_links.customer` và `_embedded.customer`. Relation của embedded preview được lấy từ relation của link, nhờ đó hai phần luôn mô tả cùng một mối quan hệ. `preview()` phù hợp khi representation nhúng là bản xem trước của tài nguyên có thể truy cập qua link.

Nếu không cần link tương ứng, dùng `embed(...)` trực tiếp. Nếu cần link nhưng không muốn gửi bản preview, chỉ thêm `link(...)` hoặc link vào model. Hãy chọn theo nhu cầu của client thay vì nhúng mọi dữ liệu có thể lấy được.

## Ví dụ hoàn chỉnh: đơn hàng, khách hàng và dòng hàng

Ví dụ dưới đây xây dựng response cho một đơn hàng. Đơn hàng là payload chính; khách hàng là preview gắn với link; các dòng hàng được nhúng thành collection.

```java
import java.util.List;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Relation(itemRelation = "lineItem", collectionRelation = "lineItems")
record LineItemView(long productId, String name, int quantity) {
}

record CustomerSummary(long id, String name) {
}

@Relation(itemRelation = "order", collectionRelation = "orders")
record OrderView(long id, String status, long total) {
}

record OrderDetails(
    OrderView order,
    CustomerSummary customer,
    List<LineItemView> lineItems
) {
}

interface OrderService {
    OrderDetails findDetails(long id);
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    RepresentationModel<?> one(@PathVariable long id) {
        OrderDetails details = orders.findDetails(id);

        Link self = linkTo(methodOn(OrderController.class).one(id))
            .withSelfRel();
        Link customer = linkTo(methodOn(OrderController.class).customer(id))
            .withRel("customer");
        EntityModel<CustomerSummary> customerPreview = EntityModel.of(
            details.customer(),
            linkTo(methodOn(OrderController.class).customer(id)).withSelfRel()
        );

        return HalModelBuilder.halModelOf(details.order())
            .link(self)
            .preview(customerPreview).forLink(customer)
            .embed(details.lineItems(), LineItemView.class)
            .build();
    }

    @GetMapping("/{id}/customer")
    CustomerSummary customer(@PathVariable long id) {
        return orders.findDetails(id).customer();
    }
}
```

Trong ứng dụng thực tế, nên tránh gọi `findDetails(id)` lặp lại ở nhiều endpoint nếu việc đó tạo truy vấn không cần thiết. Có thể tách `CustomerService` hoặc dùng query service phù hợp. Phần quan trọng ở đây là builder tạo representation với ba thành phần: payload đơn hàng, preview khách hàng và collection dòng hàng.

Response HAL có cấu trúc minh họa:

```json
{
  "id": 42,
  "status": "NEW",
  "total": 1250000,
  "_links": {
    "self": { "href": "https://api.example.test/orders/42" },
    "customer": { "href": "https://api.example.test/orders/42/customer" }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Nguyen An",
      "_links": {
        "self": {
          "href": "https://api.example.test/orders/42/customer"
        }
      }
    },
    "lineItems": [
      { "productId": 301, "name": "Keyboard", "quantity": 1 },
      { "productId": 412, "name": "Mouse", "quantity": 2 }
    ]
  }
}
```

Đây là payload HAL minh họa; host và scheme thực tế được tạo từ request hiện tại. Client có thể dùng `customer` preview để hiển thị ngay tên khách hàng hoặc theo `href` để truy cập tài nguyên khách hàng.

## Nhúng collection ở cấp root

HAL cũng dùng `_embedded` để biểu diễn collection ở cấp root. Với `CollectionModel`, Spring HATEOAS serialize các phần tử dưới relation collection tương ứng. Có thể tạo collection model bằng assembler thông thường:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

CollectionModel<EntityModel<OrderView>> model =
    orderAssembler.toCollectionModel(orders)
        .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Khi cần tự xây một HAL document chỉ chứa embedded collection, dùng `emptyHalModel()`:

```java
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var model = HalModelBuilder.emptyHalModel()
    .embed(orderViews, OrderView.class)
    .link(linkTo(methodOn(OrderController.class).all()).withSelfRel())
    .build();
```

Nếu `orderViews` có phần tử, relation collection được suy ra từ `OrderView`. Nếu danh sách rỗng, overload `embed(collection, type)` vẫn giữ relation và tạo array rỗng trong `_embedded`. Đây là cách hữu ích khi client cần phân biệt collection hiện không có phần tử với việc server không công bố relation đó.

Lưu ý: `embed(collection)` không có tham số type hoặc relation sẽ không thêm embedded entry khi collection rỗng, vì builder không có dữ liệu để suy ra relation. Hãy dùng overload có `Class<?>` hoặc `LinkRelation` nếu cần biểu diễn collection rỗng một cách tường minh.

```java
import java.util.List;

var emptyOrders = HalModelBuilder.emptyHalModel()
    .embed(List.of(), OrderView.class)
    .build();
```

Với `OrderView` đã khai báo `collectionRelation = "orders"`, representation trên giữ `_embedded.orders` dưới dạng array rỗng.

## Embedded resource lồng nhau

Một embedded resource có thể là một representation model chứa links và embedded resources riêng. Điều này cho phép tạo cấu trúc nhiều cấp, ví dụ đơn hàng chứa preview khách hàng, và preview khách hàng lại chứa liên kết tới địa chỉ giao hàng.

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var customerModel = HalModelBuilder.halModelOf(customerSummary)
    .link(customerSelf)
    .embed(addressSummary, LinkRelation.of("shippingAddress"))
    .build();

var orderModel = HalModelBuilder.halModelOf(orderView)
    .embed(customerModel, LinkRelation.of("customer"))
    .build();
```

Ở đây, `customerModel` là một representation HAL lồng bên trong `orderModel`. Nó có thể chứa `_links` và `_embedded` riêng. Khi serialize, client có thể khám phá dữ liệu theo từng cấp mà không cần thêm request ngay lập tức.

Không nên lồng sâu không giới hạn. Cấu trúc quá sâu làm response khó đọc, tăng kích thước payload và khiến client tải nhiều dữ liệu mà có thể không sử dụng. Chỉ nhúng những phần có ích cho luồng sử dụng chính.

## Relation của embedded resource

Tên relation quyết định vị trí dữ liệu trong `_embedded`. Có ba cách phổ biến để kiểm soát relation:

1. Dùng `@Relation` trên kiểu representation để định nghĩa `itemRelation` và `collectionRelation`.
2. Truyền `LinkRelation` rõ ràng vào `embed(entity, relation)` hoặc `embed(collection, relation)`.
3. Cấu hình `LinkRelationProvider` nếu ứng dụng cần quy tắc đặt tên tập trung.

Ví dụ truyền relation tường minh:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.mediatype.hal.HalModelBuilder;

var model = HalModelBuilder.halModelOf(orderView)
    .embed(customerSummary, LinkRelation.of("customer"))
    .embed(lineItems, LinkRelation.of("lineItems"))
    .build();
```

Relation tùy chỉnh nên được giữ ổn định và mô tả trong hợp đồng API hoặc profile. Các tên ngắn như `customer` và `lineItems` trong ví dụ là tên relation dễ đọc trong phạm vi bài học; với HAL công khai, hãy dùng relation đã đăng ký hoặc URI relation tuyệt đối. Nếu muốn hiển thị tên ngắn cho URI relation tùy chỉnh, cấu hình CURIE để client có thể mở rộng tên đó về URI gốc. Không đổi ý nghĩa hoặc tên relation một cách âm thầm nếu client hiện tại đang tìm `_embedded.customer`.

## Khi nào nên nhúng và khi nào chỉ cung cấp link?

Nhúng dữ liệu có thể giảm số request mà client cần gửi. Tuy nhiên, mỗi embedded representation làm response lớn hơn và có thể phản ánh snapshot tại thời điểm server xử lý request.

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Client luôn cần tên khách hàng khi xem đơn | Nhúng preview khách hàng và giữ link `customer` | Giảm request phụ nhưng vẫn cho phép truy cập tài nguyên đầy đủ |
| Tài nguyên liên quan lớn hoặc ít khi được mở | Chỉ cung cấp link | Tránh gửi dữ liệu client không dùng |
| Collection có thể chứa hàng nghìn phần tử | Dùng link tới endpoint phân trang | Tránh payload quá lớn và khó cache |
| Dữ liệu liên quan thay đổi thường xuyên | Cân nhắc chỉ link hoặc preview có thời hạn/cache rõ ràng | Tránh client dựa vào snapshot cũ |
| Client cần một vài trường để hiển thị danh sách | Nhúng DTO preview nhỏ | Giới hạn dữ liệu và giữ representation gọn |

Embedded resource không thay thế tài nguyên gốc. Khi cần dữ liệu mới nhất hoặc cần thực hiện thao tác trên tài nguyên liên quan, client có thể theo link tới URI canonical. Server cần thiết kế cache headers phù hợp vì response cha có thể chứa bản sao dữ liệu của tài nguyên con.

## Kiểm thử `_embedded` bằng MockMvc

Kiểm thử endpoint nên xác nhận cả `_links` và `_embedded`, bao gồm tên relation và hình dạng object/array:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderEmbeddedResourcesTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void embedsCustomerPreviewAndLineItems() throws Exception {
        given(orders.findDetails(42L)).willReturn(new OrderDetails(
            new OrderView(42L, "NEW", 1_250_000L),
            new CustomerSummary(7L, "Nguyen An"),
            List.of(new LineItemView(301L, "Keyboard", 1))
        ));

        mockMvc.perform(get("/orders/{id}", 42).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.customer.href").exists())
            .andExpect(jsonPath("$._embedded.customer.name").value("Nguyen An"))
            .andExpect(jsonPath("$._embedded.lineItems").isArray())
            .andExpect(jsonPath("$._embedded.lineItems[0].productId").value(301));
    }
}
```

Test slice này cần `OrderController` dùng đúng `HalModelBuilder` như ví dụ và mock `OrderService`. Nếu ứng dụng yêu cầu cấu hình HAL thủ công, hãy import cấu hình hypermedia tương ứng; Spring Boot với starter HATEOAS thường đã tự cấu hình HAL. Nên kiểm thử thêm collection rỗng bằng `embed(emptyList, OrderView.class)` để xác nhận `_embedded.orders` tồn tại dưới dạng array rỗng.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm `_embedded` với `_links` | Client tìm dữ liệu trong link hoặc tìm URI trong object nhúng | Dùng `_links` cho URI điều hướng và `_embedded` cho representation inline |
| Không khai báo relation ổn định | Tên key có thể thay đổi theo quy tắc suy luận | Dùng `@Relation`, `LinkRelation` hoặc `LinkRelationProvider` |
| Nhúng mọi tài nguyên liên quan | Response lớn, tăng độ trễ và dữ liệu thừa | Chỉ nhúng dữ liệu client thường cần |
| Dùng `embed(collection)` với collection rỗng | Relation không xuất hiện trong `_embedded` | Dùng `embed(collection, Type.class)` hoặc relation tường minh |
| Cho rằng embedded representation luôn mới | Client có thể dùng snapshot cũ | Theo link canonical khi cần dữ liệu mới nhất và cấu hình cache phù hợp |
| Nhúng collection lớn không phân trang | Payload lớn và tốn bộ nhớ | Cung cấp link tới collection phân trang |
| Dùng `preview()` nhưng không có link tương ứng | Không thể hiện được quan hệ điều hướng đầy đủ | Dùng `preview(entity).forLink(link)` hoặc `embed()` nếu chỉ cần inline data |
| Không kiểm thử `_embedded` | Thay đổi relation có thể phá client mà test không phát hiện | Assert tên relation và cấu trúc object/array trong HAL response |

## Ghi nhớ

`_embedded` trong HAL chứa representation của tài nguyên liên quan, được nhóm theo link relation. `_links` cung cấp URI để điều hướng, còn `_embedded` cung cấp dữ liệu inline; một quan hệ có thể xuất hiện ở cả hai nơi. Spring HATEOAS hỗ trợ tạo cấu trúc này bằng `HalModelBuilder`: dùng `halModelOf()` cho payload chính, `embed()` cho tài nguyên hoặc collection, `preview().forLink()` khi cần cả link và bản xem trước, và `emptyHalModel()` cho collection ở cấp root. Dùng `@Relation` hoặc `LinkRelation` để giữ tên relation ổn định, xử lý collection rỗng tường minh và chỉ nhúng dữ liệu thực sự hữu ích cho client.

## Tài liệu tham khảo

- [Spring HATEOAS – HAL representation models and embedded resources](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [HalModelBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalModelBuilder.html)
- [HAL specification](https://stateless.group/hal_specification.html)
