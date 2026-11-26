# Theo link đến collection

Một client REST có hypermedia không cần tự ghép URL để truy cập collection. Client bắt đầu từ một URI đã biết, đọc link relation trong representation rồi theo link có ý nghĩa phù hợp. Khi API root công bố relation đến collection đơn hàng, client có thể tìm collection bằng relation đó, đọc các item được nhúng và tiếp tục điều hướng theo self link hoặc link phân trang.

Spring HATEOAS hỗ trợ cả phía server lẫn client cho quy trình này. Server dùng **RepresentationModel**, **CollectionModel** và **EntityModel** để công bố link cùng dữ liệu; client có thể dùng **Traverson** để theo relation trong HAL response. Cách tiếp cận này giảm phụ thuộc vào cấu trúc URL và giúp server thay đổi route mà không buộc mọi client phải sửa mã.

## Collection được khám phá qua API root

API thường cung cấp một entry point, chẳng hạn /api. Representation root không cần chứa toàn bộ dữ liệu; nó chỉ cần công bố các link dẫn đến khả năng hoặc resource chính:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://shop.example/api/orders"
    },
    "customers": {
      "href": "https://shop.example/api/customers"
    }
  }
}
~~~

Trong ví dụ, **orders** là relation mà API định nghĩa cho link đến collection đơn hàng. Client chỉ cần biết relation này và URI entry point. Nếu server đổi đường dẫn collection sang /commerce/order-list, client vẫn có thể hoạt động nếu root tiếp tục công bố relation **orders** với target mới.

Relation **orders** trong API root không phải một URL và cũng không nhất thiết là relation chuẩn IANA. Đây là relation mở rộng của API, có ý nghĩa “đi đến collection đơn hàng”. Nếu một item cần liên kết ngược đến collection chứa nó, relation IANA **collection** có semantics riêng và có thể dùng trong representation của item.

## Công bố link collection trong Spring HATEOAS

Có thể tạo root representation bằng một kiểu kế thừa **RepresentationModel**:

~~~java
import org.springframework.hateoas.RepresentationModel;

class ApiRoot extends RepresentationModel<ApiRoot> {
}
~~~

Controller root thêm link đến collection:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class ApiRootController {

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    ApiRoot root() {
        ApiRoot model = new ApiRoot();
        model.add(linkTo(methodOn(OrderController.class).all())
                .withRel("orders"));
        return model;
    }
}
~~~

**linkTo(methodOn(...))** tạo URI dựa trên mapping của controller. **withRel("orders")** gắn relation để client nhận diện collection. **methodOn(...)** chỉ mô tả lời gọi để xây dựng link, không gọi endpoint collection ngay tại thời điểm tạo representation.

Đối với API công khai, relation mở rộng nên có semantics được tài liệu hóa và cần giữ ổn định. Có thể dùng URI relation tuyệt đối nếu cần định danh toàn cục, sau đó cấu hình CURIE để trình bày ngắn trong HAL.

## CollectionModel và embedded items

**CollectionModel<T>** biểu diễn một collection resource. Mỗi phần tử có thể là **EntityModel<T>** để mang dữ liệu cùng các link riêng. Ví dụ DTO và relation:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderDto(
        UUID id,
        String status,
        BigDecimal total) {
}
~~~

**@Relation** giúp đặt tên relation của item và collection khi serialize embedded resources. Với cấu hình trên, HAL có thể dùng khóa **_embedded.orders**. Tên này là embedded relation, khác với link relation **orders** ở **_links** của API root dù hai tên có thể giống nhau.

Controller trả collection với self link và self link cho từng item:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<EntityModel<OrderDto>> all() {
        List<EntityModel<OrderDto>> items = service.findAll().stream()
                .map(order -> {
                    OrderDto dto = toDto(order);
                    return EntityModel.of(dto,
                            linkTo(methodOn(OrderController.class)
                                    .one(order.getId())).withSelfRel());
                })
                .toList();

        return CollectionModel.of(items,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<OrderDto> one(@PathVariable UUID id) {
        Order order = service.findById(id);
        OrderDto dto = toDto(order);

        return EntityModel.of(dto,
                linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
                linkTo(methodOn(OrderController.class).all())
                        .withRel(IanaLinkRelations.COLLECTION));
    }

    private OrderDto toDto(Order order) {
        return new OrderDto(order.getId(), order.getStatus().name(),
                order.getTotal());
    }
}
~~~

Các kiểu **Order**, **OrderService** và phương thức truy vấn thuộc ứng dụng. Ví dụ tập trung vào cách tạo representation: collection có self link; mỗi embedded item có self link; item riêng lẻ có thêm relation IANA **collection** trỏ về collection liên quan.

Khi collection lớn, nên dùng phân trang thay vì tải toàn bộ item. Khi đó, có thể trả **PagedModel** với metadata và các link **first**, **prev**, **next**, **last**. Client vẫn bắt đầu từ relation collection và theo các link phân trang được công bố.

## HAL biểu diễn collection như thế nào?

Response collection có thể có hình dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "status": "PAID",
        "total": 125000,
        "_links": {
          "self": {
            "href": "https://shop.example/api/orders/o-42"
          }
        }
      },
      {
        "id": "o-43",
        "status": "PENDING",
        "total": 85000,
        "_links": {
          "self": {
            "href": "https://shop.example/api/orders/o-43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders"
    }
  }
}
~~~

Hai vùng có vai trò khác nhau:

- **_embedded.orders** chứa representation của các item thuộc collection.
- **_links.self** trỏ đến collection hiện tại.
- Embedded relation **orders** đặt tên nhóm item.
- Mỗi item có **_links.self** để client truy cập representation riêng.

Không nên nhầm **_embedded.orders** với **_links.orders**. Một link trong **_links** là URI để điều hướng; một phần tử trong **_embedded** là representation đã được nhúng ngay trong response.

## Theo link đến collection bằng Traverson

**Traverson** là client đồng bộ của Spring HATEOAS, cho phép theo một chuỗi link relation từ URI gốc. Client khai báo URI entry point và media type hypermedia mà nó hiểu:

~~~java
import java.net.URI;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

Traverson traverson = new Traverson(
        URI.create("https://shop.example/api"),
        MediaTypes.HAL_JSON);

ParameterizedTypeReference<CollectionModel<EntityModel<OrderDto>>> orderType =
        new ParameterizedTypeReference<>() { };

CollectionModel<EntityModel<OrderDto>> orders = traverson
        .follow("orders")
        .toObject(orderType);
~~~

Quá trình diễn ra như sau:

1. **Traverson** gửi GET đến URI root đã biết.
2. Client yêu cầu representation HAL bằng media type tương ứng.
3. **follow("orders")** tìm link có relation **orders** trong root representation.
4. **Traverson** gửi request đến **href** của link đó.
5. **toObject(...)** chuyển response collection thành **CollectionModel<EntityModel<OrderDto>>**.

Client không cần biết /api/orders được tạo từ controller nào hoặc route cụ thể ra sao. Nếu server thay đổi target của relation, client vẫn theo link mới từ root response.

**ParameterizedTypeReference** giữ thông tin generic khi deserialize collection chứa **EntityModel<OrderDto>**. Nếu chỉ dùng **CollectionModel.class**, client có thể mất kiểu cụ thể của item và phải xử lý các map không thuận tiện.

## Đọc item và theo self link

Sau khi lấy collection, client có thể duyệt các item được nhúng:

~~~java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;

for (EntityModel<OrderDto> item : orders) {
    OrderDto order = item.getContent();

    var selfLink = item.getRequiredLink(IanaLinkRelations.SELF);
    URI orderUri = selfLink.toUri();

    System.out.println(order.id() + " -> " + orderUri);
}
~~~

**getContent()** lấy dữ liệu item; **getRequiredLink(IanaLinkRelations.SELF)** lấy self link. Nếu relation là bắt buộc theo hợp đồng, **getRequiredLink** giúp phát hiện response không đúng hợp đồng ngay khi client xử lý. Nếu link có thể không xuất hiện, dùng **getLink(...)** hoặc kiểm tra **hasLink(...)** trước khi sử dụng.

Client có thể gửi request GET đến URI lấy từ self link bằng HTTP client của ứng dụng khi cần tải representation chi tiết. Không nên tạo URI từ ID theo quy ước như /api/orders/{id} nếu server đã cung cấp link.

Nếu client cần đi ngược từ một item đến collection, response item có thể công bố relation IANA **collection**. Nếu cần đi từ collection đến các item dưới dạng link riêng, API có thể công bố các link relation **item**; tuy nhiên, với HAL collection đã có **_embedded** và self link trên mỗi item, không nhất thiết phải lặp lại tất cả URI trong **_links.item**.

## Theo link phân trang

Với collection lớn, server có thể trả **PagedModel<EntityModel<OrderDto>>**. HAL response có thêm page metadata và link điều hướng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "_links": {
          "self": { "href": "https://shop.example/api/orders/o-42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "https://shop.example/api/orders?page=0&size=20" },
    "next": { "href": "https://shop.example/api/orders?page=1&size=20" },
    "last": { "href": "https://shop.example/api/orders?page=4&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 0
  }
}
~~~

Client có thể yêu cầu page model từ cùng relation:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.PagedModel;

ParameterizedTypeReference<PagedModel<EntityModel<OrderDto>>> pageType =
        new ParameterizedTypeReference<>() { };

PagedModel<EntityModel<OrderDto>> firstPage = traverson
        .follow("orders")
        .toObject(pageType);

if (firstPage.hasLink(IanaLinkRelations.NEXT)) {
    PagedModel<EntityModel<OrderDto>> secondPage = traverson
            .follow("orders", "next")
            .toObject(pageType);
}
~~~

**follow("orders", "next")** có nghĩa là bắt đầu tại root, theo relation **orders**, sau đó theo relation **next** trên representation collection vừa nhận. Client không tự tăng **page** hoặc nối query string. Nếu không có **next**, client đã ở trang cuối hoặc collection chỉ có một trang.

**PagedModel** cung cấp metadata cho giao diện, còn link mới là hướng dẫn điều hướng. Hãy ưu tiên theo **next**/**prev** thay vì tính URL từ **page.number + 1**, vì server có thể thay đổi cách phân trang hoặc thêm token vào URI.

## Relation của link và relation của embedded resource

Khi theo link đến collection, cần phân biệt ba khái niệm:

| Thành phần | Vị trí | Mục đích |
| --- | --- | --- |
| Relation **orders** | **_links** của API root | Chỉ ra collection đơn hàng mà client có thể mở. |
| Relation **self** | **_links** của collection hoặc item | Trỏ đến chính resource đang biểu diễn. |
| Embedded relation **orders** | **_embedded** của collection | Đặt tên nhóm item được nhúng. |

Tên relation ở root có thể là một extension relation như **orders**. Relation **collection** theo IANA thường được dùng từ một resource đến collection liên quan; relation **item** đi từ collection đến một member. Không dùng **next** để thay **item**: **next** trỏ đến trang kế tiếp, còn **item** trỏ đến một thành viên.

Trong Spring HATEOAS, **@Relation(itemRelation = "order", collectionRelation = "orders")** hoặc một **LinkRelationProvider** phù hợp giúp ổn định tên embedded relation. **IanaLinkRelations.SELF**, **COLLECTION**, **ITEM** và **NEXT** biểu diễn các relation IANA chuẩn trong **_links**.

## Khi collection không có item

Một collection rỗng vẫn là resource hợp lệ. Response có thể chỉ có self link:

~~~json
{
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders"
    }
  }
}
~~~

Tùy serializer và cấu hình, **_embedded.orders** có thể vắng mặt hoặc là mảng rỗng. Client không nên truy cập phần tử đầu tiên mà không kiểm tra collection có item. Hãy xem **CollectionModel** như một tập có thể rỗng và xử lý **getContent()** an toàn.

Nếu client cần biết vì sao collection rỗng hoặc có thể tạo item mới hay không, server có thể công bố thêm metadata hoặc affordance thích hợp. Không suy ra rằng collection rỗng đồng nghĩa client có quyền tạo resource.

## Content negotiation và HTTP request

Client cần yêu cầu đúng media type hypermedia:

~~~http
GET /api HTTP/1.1
Host: shop.example
Accept: application/hal+json
~~~

Response thành công phải công bố media type tương thích:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "_links": {
    "orders": {
      "href": "https://shop.example/api/orders"
    }
  }
}
~~~

Nếu client yêu cầu **application/json** nhưng server chỉ hỗ trợ HAL, content negotiation có thể thất bại với **406 Not Acceptable**. Client cũng cần xử lý **401**, **403**, **404** hoặc lỗi mạng khi theo link. Link là hướng dẫn điều hướng tại thời điểm response được tạo; nó không bảo đảm resource vẫn tồn tại hoặc caller vẫn có quyền ở request tiếp theo.

## Kiểm thử collection traversal bằng MockMvc

Kiểm thử server nên xác nhận API root công bố relation collection và collection trả embedded item cùng self link:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
class OrderCollectionTraversalTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rootPublishesOrdersRelation() throws Exception {
        mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.orders.href").exists());
    }

    @Test
    void collectionEmbedsOrdersWithSelfLinks() throws Exception {
        mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._embedded.orders").isArray())
                .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
    }
}
~~~

Fixture cần có ít nhất một order cho test embedded item. Nếu collection relation trong ứng dụng không phải **orders**, cập nhật JSONPath theo relation thực tế. Nên có thêm test collection rỗng và test pagination để xác nhận **next** chỉ xuất hiện khi còn trang tiếp theo.

Kiểm thử client traversal nên xác nhận client bắt đầu từ root URI, theo relation **orders** và deserialize được **CollectionModel**. Với **Traverson**, có thể thay URI root trong test bằng server test đang chạy hoặc cấu hình **RestOperations** giả lập để xác minh chuỗi request mà không khóa client vào một URL collection cố định.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Client tự ghép /api/orders | Client phụ thuộc route nội bộ và dễ hỏng khi đổi URL. | Bắt đầu từ root và theo relation **orders**. |
| Nhầm **_embedded.orders** với **_links.orders** | Client tìm link trong vùng chứa embedded data hoặc ngược lại. | Phân biệt link điều hướng với resource được nhúng. |
| Không gửi **Accept: application/hal+json** | Server có thể trả representation khác hoặc từ chối request. | Dùng media type hypermedia đã thỏa thuận. |
| Dùng **CollectionModel.class** khi deserialize generic | Mất kiểu item và phải xử lý map không an toàn kiểu. | Dùng **ParameterizedTypeReference**. |
| Giả định collection luôn có item | Client lỗi khi response rỗng. | Kiểm tra content trước khi duyệt hoặc truy cập phần tử. |
| Tự tính URL trang kế tiếp | Mất filter, sort hoặc token điều hướng. | Theo relation **next** do server công bố. |
| Coi link là bảo đảm quyền truy cập | Request tiếp theo vẫn có thể bị từ chối. | Xử lý status và authorization ở mỗi request. |

## Nguyên tắc thiết kế

- Cung cấp một API root URI ổn định để client bắt đầu traversal.
- Công bố relation đến collection trong **_links**.
- Dùng **CollectionModel** cho collection và **EntityModel** cho item có link.
- Đặt tên embedded relation ổn định bằng **@Relation** hoặc **LinkRelationProvider**.
- Dùng **Traverson** để theo relation thay vì hard-code URL collection.
- Dùng self link của item để truy cập representation chi tiết.
- Theo **next**/**prev** để phân trang; không tự ghép query string.
- Yêu cầu và trả đúng media type hypermedia.
- Xử lý collection rỗng, lỗi HTTP, quyền truy cập và link có thể thay đổi.
- Kiểm thử cả API root, collection representation và hành vi traversal của client.

Theo link đến collection là bước cơ bản trong client traversal: client biết entry point, đọc relation, theo **href** và xử lý collection representation. Spring HATEOAS cung cấp **CollectionModel** và các link ở phía server, còn **Traverson** giúp client thực hiện chuỗi điều hướng theo relation. Khi client dựa vào link và semantics được công bố thay vì tự dựng URL, API có thể thay đổi route và cách phân trang mà ít ảnh hưởng đến consumer.
