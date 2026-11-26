# Link dẫn nhập

Một client muốn sử dụng API quản lý đơn hàng cần biết nơi bắt đầu. Nếu client phải ghi cứng `/api/orders`, `/api/customers`, `/api/orders/{id}/cancel` và mọi URI khác, mỗi lần server đổi cấu trúc đường dẫn đều có thể buộc client phát hành phiên bản mới. Một API hypermedia cung cấp một URI dẫn nhập ổn định; từ representation tại URI đó, client khám phá các resource và thao tác tiếp theo bằng link.

Link dẫn nhập (*entry-point link*) là điểm bắt đầu để client bước vào không gian tài nguyên của API. Trong Spring HATEOAS, entry point thường được triển khai như một root resource trả về `RepresentationModel` hoặc `EntityModel`, chứa link `self` và các link đến collection/resource chính. Client chỉ cần biết URI root cùng media type ban đầu; các URI tiếp theo được khám phá từ response.

## Entry point trong thiết kế Web API

Một API thường có nhiều URI: collection, item, search, action và tài liệu. Entry point là URI mà client biết trước để bắt đầu khám phá các URI còn lại.

Ví dụ:

```text
Client
  |
  | GET /api
  v
API root resource
  |-- acme:orders -----> /api/orders
  |-- acme:customers --> /api/customers
  |-- service-doc -----> /docs
```

Client cần biết URI `/api` thông qua cấu hình, tài liệu onboarding, developer portal hoặc một cơ chế bootstrap khác. Sau khi nhận root representation, client theo link có relation phù hợp để đến collection hoặc resource tiếp theo.

Không có quy ước bắt buộc mọi API phải dùng `/api` làm root. URI có thể là `/`, `/api`, `/v1` hoặc một URI riêng theo hạ tầng. Điều quan trọng là URI dẫn nhập được công bố rõ, ổn định và trả representation có khả năng khám phá.

## Entry point khác gì endpoint thông thường?

Endpoint thông thường phục vụ một thao tác hoặc một resource cụ thể. Entry point được thiết kế làm điểm bắt đầu chung, cung cấp các liên kết để khám phá phần còn lại của API.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Entry point | Điểm bắt đầu đã biết trước | `GET /api` |
| Collection resource | Đại diện tập hợp resource | `GET /api/orders` |
| Item resource | Đại diện một resource cụ thể | `GET /api/orders/ord-1042` |
| Search resource | Điểm vào chức năng tìm kiếm | `/api/orders/search{?status}` |
| Action target | Endpoint cho một thao tác khả dụng | `POST /api/orders/ord-1042/cancellation` |
| Documentation resource | Tài liệu giải thích API | `/docs` |

Entry point không cần chứa toàn bộ dữ liệu hoặc tất cả endpoint. Nó chỉ cần cung cấp đủ link để client khám phá những capability chính mà client được phép sử dụng.

## Vì sao cần link dẫn nhập?

Nếu client tự ghép URI theo cấu trúc route, client phụ thuộc vào chi tiết triển khai. Ví dụ, đổi `/api/orders` thành `/commerce/orders` sẽ làm hỏng client đang hard-code đường dẫn.

Khi client điều hướng bằng link:

- Server có thể thay đổi URI đích mà vẫn giữ relation ổn định.
- Client khám phá resource và capability từ response hiện tại.
- API có thể thêm collection hoặc thao tác mới mà không bắt buộc client cũ phải sử dụng chúng.
- Server có thể công bố hoặc ẩn link theo trạng thái resource và quyền của người dùng.
- Client giảm nhu cầu xây dựng URL từ ID, path segment hoặc query string.

Link dẫn nhập không loại bỏ mọi phụ thuộc. Client vẫn cần biết URI ban đầu, media type, cách xác thực và semantics của các relation mà nó sử dụng. Mục tiêu là thu hẹp phần URI phải biết trước và chuyển điều hướng runtime sang hợp đồng hypermedia.

## Cấu trúc root representation bằng HAL

Với HAL JSON, root representation có thể chứa dữ liệu mô tả API cùng `_links`:

```json
{
  "name": "Orders API",
  "description": "API quản lý đơn hàng và khách hàng",
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
    },
    "acme:customers": {
      "href": "https://api.example.com/api/customers"
    },
    "service-doc": {
      "href": "https://api.example.com/docs"
    }
  }
}
```

Các thành phần có ý nghĩa:

- `self` trỏ đến chính root resource.
- `acme:orders` và `acme:customers` là custom relations trỏ đến collection tương ứng.
- `curies` khai báo cách mở rộng prefix `acme` thành URI relation đầy đủ.
- `service-doc` là relation chuẩn trỏ đến tài liệu dịch vụ.

Trong HAL, `_links` là nơi công bố link. `_embedded` chỉ dùng khi response thực sự nhúng representation của resource liên quan. Root resource thường chỉ cần link đến collection; không cần nhúng toàn bộ đơn hàng hoặc khách hàng vào root response.

## Relation cho các link tại entry point

Relation giải thích ý nghĩa của target đối với root resource. Chọn relation chuẩn trong IANA Link Relations Registry khi có relation phù hợp. Với relation riêng của API, dùng extension relation URI và có thể rút gọn bằng CURIE khi serialize HAL.

Ví dụ relation:

| Relation | Ý nghĩa trong root resource |
| --- | --- |
| `self` | URI của root resource hiện tại. |
| `service-doc` | Tài liệu mô tả dịch vụ/API. |
| `acme:orders` | Collection đơn hàng do API công bố. |
| `acme:customers` | Collection khách hàng do API công bố. |
| `acme:search-orders` | Điểm vào chức năng tìm kiếm đơn hàng. |

Relation `acme:orders` không phải target URI. Relation nhận diện ý nghĩa “collection đơn hàng”; `href` cung cấp URI hiện tại để client điều hướng. Nếu server đổi `/api/orders` sang `/commerce/orders`, client vẫn theo relation `acme:orders` và nhận URI mới từ response.

Không tái sử dụng cùng một relation URI cho ý nghĩa khác. Nếu semantics của relation thay đổi không tương thích, hãy định nghĩa relation mới và có kế hoạch chuyển đổi.

## Xây dựng API root bằng Spring HATEOAS

Spring HATEOAS cung cấp `EntityModel<T>` để bọc nội dung và các link. Một root controller có thể tạo entry point như sau:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
class ApiRootController {

    @GetMapping(path = "/api", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<ApiInfo> root() {
        EntityModel<ApiInfo> model = EntityModel.of(
            new ApiInfo("Orders API", "API quản lý đơn hàng và khách hàng"));

        model.add(linkTo(methodOn(ApiRootController.class).root())
            .withSelfRel());

        model.add(linkTo(methodOn(OrderController.class).all())
            .withRel(ApiRelations.ORDERS));

        model.add(linkTo(methodOn(CustomerController.class).all())
            .withRel(ApiRelations.CUSTOMERS));

        return model;
    }
}
```

Các kiểu `ApiInfo`, `OrderController` và `CustomerController` là thành phần của ví dụ ứng dụng. `all()` đại diện cho mapping collection không có tham số. Nếu controller nhận `Pageable` hoặc filter, hãy truyền placeholder phù hợp vào `methodOn(...)` theo chữ ký method.

Kiểu nội dung root có thể là một record đơn giản:

```java
public record ApiInfo(String name, String description) {
}
```

Định nghĩa relation riêng thành hằng:

```java
import org.springframework.hateoas.LinkRelation;

final class ApiRelations {

    static final LinkRelation ORDERS = LinkRelation.of(
        "https://api.example.com/rels/orders");

    static final LinkRelation CUSTOMERS = LinkRelation.of(
        "https://api.example.com/rels/customers");

    private ApiRelations() {
    }
}
```

Các URI relation cần thuộc namespace mà tổ chức kiểm soát và được tài liệu hóa. Giá trị trong `LinkRelation` là định danh ngữ nghĩa; target URI được `WebMvcLinkBuilder` tạo từ mapping controller.

### Rút gọn extension relation bằng CURIE

Nếu API dùng HAL, có thể cấu hình `CurieProvider` để biểu diễn URI relation dài bằng prefix ngắn:

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

Với cấu hình này, relation URI `https://api.example.com/rels/orders` có thể được serialize thành `acme:orders` trong HAL. CURIE chỉ rút gọn cách biểu diễn; định danh đầy đủ vẫn là URI relation.

Nếu không dùng CURIE, HAL có thể biểu diễn extension relation bằng URI đầy đủ theo quy ước media type. Client cần xử lý relation theo đúng định dạng response mà API công bố.

## Tạo link từ mapping controller

`WebMvcLinkBuilder` giúp tạo link từ mapping Spring MVC:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    OrderController(OrderService orderService,
                    OrderModelAssembler orderAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderView>> all() {
        return orderAssembler.toCollectionModel(orderService.findAll());
    }
}
```

`linkTo(methodOn(OrderController.class).all())` đọc mapping của controller để tạo target URI. `methodOn(...)` dùng proxy để ghi nhận method và tham số, không gọi thân controller hoặc service. Vì vậy, root controller có thể tham chiếu mapping của collection mà không tự viết lại path `/api/orders`.

Khi thay đổi mapping collection, link được tạo từ method mapping sẽ theo cấu hình mới. Đây là một lợi ích quan trọng của việc xây link dựa trên controller thay vì nối chuỗi URI thủ công.

## Công bố capability theo trạng thái và quyền

Root resource có thể công bố những collection mà người dùng hiện tại được phép khám phá. Ví dụ, tài khoản quản trị có thể nhìn thấy link đến collection báo cáo; tài khoản thông thường chỉ thấy đơn hàng và khách hàng.

```java
EntityModel<ApiInfo> model = EntityModel.of(apiInfo);

model.add(linkTo(methodOn(OrderController.class).all())
    .withRel(ApiRelations.ORDERS));

if (authorization.canViewCustomers(currentUser)) {
    model.add(linkTo(methodOn(CustomerController.class).all())
        .withRel(ApiRelations.CUSTOMERS));
}
```

Đoạn code minh họa việc chỉ công bố link khách hàng khi user có quyền xem. `authorization` và `currentUser` là dependency/context của ứng dụng, cần được triển khai phù hợp.

Ẩn link không thay thế kiểm tra quyền tại endpoint. Client có thể biết URI từ cache, log hoặc một response cũ và gọi trực tiếp. Endpoint đích phải xác thực, phân quyền và kiểm tra điều kiện nghiệp vụ trên mọi request.

Không nên thay đổi cấu trúc root tùy tiện giữa các user nếu response bị cache dùng chung. Nếu link phụ thuộc quyền, cache cần tách theo principal/tenant hoặc dùng chính sách cache phù hợp, chẳng hạn `private` hay `no-store` cho dữ liệu nhạy cảm.

## Client bắt đầu từ entry point như thế nào?

Client chỉ cấu hình URI root và media type ban đầu. Ví dụ:

```http
GET /api HTTP/1.1
Host: api.example.com
Accept: application/hal+json
Authorization: Bearer <access-token>
```

Sau khi nhận response, client:

1. Đọc `_links` trong root representation.
2. Tìm relation có ý nghĩa cần dùng, ví dụ `acme:orders`.
3. Lấy `href` của link đó.
4. Gửi request đến `href` với media type và thông tin xác thực phù hợp.
5. Tiếp tục khám phá link trong collection hoặc item response.

Client không cần tự ghép `/api/orders` hoặc dự đoán ID của đơn hàng. Nếu server đổi target URI, client vẫn theo relation từ response mới.

Khi một relation xuất hiện nhiều lần, client cần xử lý cardinality theo hợp đồng. Nếu root chỉ có một link `acme:orders`, việc chọn link đơn giản. Nếu có nhiều link cùng relation, tài liệu cần giải thích cách phân biệt, chẳng hạn bằng `title`, `name` hoặc context khác.

## Entry point và API documentation

Tài liệu API vẫn cần cung cấp URI root, media type, cơ chế xác thực và hướng dẫn bootstrap. Entry point không tự giải quyết cách client tìm URI đầu tiên.

Có thể công bố URI root qua:

- Developer portal hoặc tài liệu onboarding.
- Cấu hình của SDK/client.
- Một URL ổn định do tổ chức công bố.
- Một well-known URI nếu API và hệ sinh thái có quy ước cụ thể.

Sau khi client đã vào API, hypermedia links cung cấp điều hướng runtime. OpenAPI có thể mô tả endpoint, schema và request/response; root representation cho client biết các link hiện có trong ngữ cảnh request thực tế. Hai cách tiếp cận bổ trợ nhau.

Không coi `/api` là well-known URI theo tiêu chuẩn chung. Nếu sử dụng `/.well-known/...`, phải chọn một quy ước được định nghĩa và tài liệu hóa rõ, không tự đặt tên rồi kỳ vọng client khác tự nhận ra.

## Versioning và khả năng tiến hóa

Entry point thường là một trong những URI ổn định nhất của API. Client có thể được cấu hình một lần để truy cập root; server có thể thay đổi các link bên dưới khi API phát triển.

Ví dụ ban đầu:

```json
{
  "_links": {
    "acme:orders": { "href": "/api/orders" }
  }
}
```

Sau khi đổi cấu trúc route:

```json
{
  "_links": {
    "acme:orders": { "href": "/commerce/orders" }
  }
}
```

Client tuân theo relation `acme:orders` tiếp tục hoạt động mà không cần biết path mới. Điều này chỉ đúng khi relation giữ nguyên semantics và server vẫn cung cấp representation tương thích.

Nếu API có version trong path, root URI có thể là `/api/v1` hoặc `/api/v2`. Có thể duy trì một root trung lập để dẫn đến các version được hỗ trợ, nhưng cần tài liệu hóa chính sách deprecation và thời gian hỗ trợ. Không thay đổi ý nghĩa của relation cũ âm thầm.

## Link dẫn nhập và link HTTP header

Entry point thường được trả về trong response body dưới dạng HAL hoặc media type hypermedia khác. HTTP cũng có `Link` header theo RFC 8288 để công bố link ở cấp message.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Link: </docs>; rel="service-doc"

{
  "_links": {
    "self": { "href": "/api" },
    "acme:orders": { "href": "/api/orders" }
  }
}
```

`Link` header có thể bổ sung link ở cấp HTTP message, nhưng không thay thế root representation khi client cần khám phá nhiều resource và capability. Nếu cùng một quan hệ được công bố trong body và header, hãy bảo đảm hai URI không mâu thuẫn.

## Bảo mật và vận hành entry point

Root resource là một điểm truy cập quan trọng, vì vậy cần xử lý các khía cạnh vận hành:

- **Authentication:** xác định root có công khai hay yêu cầu token.
- **Authorization:** chỉ công bố link mà principal được phép khám phá, nhưng vẫn bảo vệ endpoint đích.
- **Tenant isolation:** không để root của tenant này chứa link sang tài nguyên tenant khác.
- **Cache:** tránh dùng chung response có link phụ thuộc user/role/tenant.
- **Forwarded headers:** nếu API chạy sau reverse proxy, link cần phản ánh host, scheme và prefix công khai; chỉ tin header từ proxy đáng tin cậy.
- **Availability:** root nên nhẹ, ít truy vấn và không tải toàn bộ collection.
- **Observability:** log request root và các link relation chính để hỗ trợ chẩn đoán client navigation.

Root resource nên được thiết kế nhẹ. Không thực hiện truy vấn nặng chỉ để dựng danh sách link nếu link có thể được tạo từ mapping và quyền hiện tại.

## Kiểm thử API entry point

Kiểm thử root resource qua Spring MVC để xác nhận response cuối cùng có đúng media type và link.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links['acme:orders'].href")
        .value(org.hamcrest.Matchers.endsWith("/api/orders")))
    .andExpect(jsonPath("$._links['acme:customers'].href")
        .value(org.hamcrest.Matchers.endsWith("/api/customers")));
```

Test giả định CURIE `acme` đã được cấu hình và root response có cả hai collection link. Nếu không dùng CURIE, hãy kiểm tra key relation theo dạng URI đầy đủ.

Ngoài việc kiểm tra `href`, nên kiểm tra hành vi điều hướng:

- Lấy root URI từ cấu hình client và nhận HAL response.
- Đọc link relation cần thiết và gọi `href` của nó.
- Xác nhận collection đích trả đúng representation.
- Kiểm tra item link từ collection dẫn đến đúng resource.
- Kiểm tra link capability chỉ xuất hiện khi điều kiện và quyền phù hợp.
- Kiểm tra client cũ vẫn nhận được các relation cũ sau khi server thêm link mới.
- Kiểm tra link sau reverse proxy có host, scheme và prefix công khai đúng.

Một contract test có thể kiểm tra tập relation bắt buộc nhưng không nên thất bại chỉ vì server bổ sung relation mới. Client hypermedia nên bỏ qua link mà nó không hiểu, trừ khi hợp đồng quy định rõ phải xử lý relation đó.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Client hard-code mọi endpoint sau root | Client phụ thuộc cấu trúc route và khó tiến hóa. | Theo relation và `href` trong response. |
| Root trả về toàn bộ dữ liệu collection | Response nặng và root khó cache. | Chỉ trả thông tin mô tả cùng link dẫn nhập. |
| Không có `self` link | Client khó nhận diện URI của root representation. | Công bố `self` link. |
| Dùng relation tùy ý nhưng không tài liệu hóa | Client không hiểu ý nghĩa link. | Dùng IANA relation hoặc extension URI có tài liệu. |
| Nhầm relation với target URI | Client phụ thuộc nhầm vào đường dẫn. | Giữ relation ổn định, lấy URI từ `href`. |
| Công bố link nhưng endpoint không kiểm tra quyền | Client có thể gọi target trực tiếp ngoài quyền. | Authorization ở endpoint trên mọi request. |
| Cache chung root phụ thuộc người dùng | Có thể lộ link hoặc capability của user khác. | Chọn cache policy theo principal/tenant. |
| Coi `/api` là quy ước bắt buộc | Tích hợp client không rõ URI bootstrap thực tế. | Công bố URI root trong tài liệu hoặc cấu hình. |
| Test chỉ kiểm tra status 200 | Không phát hiện thiếu link hoặc sai relation. | Kiểm tra media type, relation, href và luồng theo link. |

## Ghi nhớ

- Entry point là URI dẫn nhập để client bắt đầu khám phá API.
- Client biết URI root qua cấu hình hoặc tài liệu; sau đó dùng hypermedia links để điều hướng.
- Root resource thường chứa `self` và link đến các collection/capability chính.
- `EntityModel` hoặc `RepresentationModel` có thể biểu diễn API root trong Spring HATEOAS.
- Dùng `WebMvcLinkBuilder` và `methodOn(...)` để tạo link từ mapping controller.
- Relation mô tả ý nghĩa của target; `href` cung cấp URI hiện tại.
- Dùng IANA relation khi phù hợp; custom relation cần URI ổn định và tài liệu hóa, có thể rút gọn bằng CURIE trong HAL.
- Không nhúng toàn bộ collection vào root; chỉ cung cấp link dẫn nhập và metadata cần thiết.
- Link có thể phụ thuộc quyền và trạng thái, nhưng endpoint đích vẫn phải kiểm tra authorization.
- Kiểm thử root response, media type, relation, target URI và khả năng điều hướng theo link.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – RepresentationModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [Spring HATEOAS API – EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS API – WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
