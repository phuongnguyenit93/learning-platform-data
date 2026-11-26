# Thiết kế entry point

## Mục tiêu

Một Web API có thể cung cấp nhiều collection, tài nguyên, thao tác và kiểu truy vấn. Nếu client phải biết trước toàn bộ URL của từng endpoint, mọi thay đổi cấu trúc URI đều có thể buộc client phải phát hành lại. Entry point giải quyết vấn đề khởi đầu này: client biết một URI bootstrap ổn định, đọc representation tại đó và khám phá các tài nguyên tiếp theo qua hypermedia links.

Trong Spring HATEOAS, entry point thường là API root resource được trả về dưới dạng RepresentationModel hoặc EntityModel. Root representation chứa self link và các links có relation mô tả những khả năng mà API công bố. Client điều hướng theo relation và href do server cung cấp thay vì tự ghép đường dẫn.

Sau bài học, bạn có thể:

- Giải thích vai trò của API entry point trong một Web API.
- Thiết kế một API root resource có self link và các relation cấp cao.
- Tạo root endpoint bằng Spring MVC và Spring HATEOAS.
- Phân biệt relation chuẩn với relation nghiệp vụ tùy chỉnh.
- Công bố search URI template và profile link.
- Thiết kế entry point ổn định khi API có nhiều phiên bản.
- Kiểm soát links theo trạng thái và quyền của người gọi.
- Kiểm thử khả năng khám phá API từ root representation.

## Entry point là gì?

Entry point là URI ban đầu mà client dùng để bắt đầu khám phá API. Ví dụ, một hệ thống quản lý đơn hàng có thể công bố:

~~~text
https://api.example.com/api
~~~

Client gửi request tới URI này và nhận API root representation:

~~~http
GET /api
Accept: application/hal+json
~~~

Response có thể chứa:

~~~json
{
  "name": "Orders API",
  "description": "API quản lý đơn hàng và khách hàng",
  "_links": {
    "self": {
      "href": "https://api.example.com/api"
    },
    "orders": {
      "href": "https://api.example.com/api/orders"
    },
    "customers": {
      "href": "https://api.example.com/api/customers"
    },
    "search": {
      "href": "https://api.example.com/api/orders{?status,customerName,page,size,sort}",
      "templated": true
    },
    "profile": {
      "href": "https://api.example.com/api/profile"
    }
  }
}
~~~

Client chỉ cần biết URI /api và media type được API công bố. Từ response, nó có thể tìm collection đơn hàng bằng relation orders, bắt đầu truy vấn bằng search hoặc đọc profile để hiểu thêm hợp đồng representation.

Entry point không phải danh sách mọi URL nội bộ. Nó là điểm bắt đầu dẫn đến các vùng chức năng chính. Các tài nguyên cấp thấp hơn tiếp tục cung cấp links để client đi sâu theo nhu cầu.

## Thiết kế một API root ổn định

Một entry point tốt có các đặc điểm:

- **Ổn định:** URI bootstrap thay đổi rất ít và được công bố qua cấu hình, tài liệu tích hợp hoặc kênh phân phối API.
- **Có self link:** client có thể nhận diện URI của representation hiện tại.
- **Có relation rõ nghĩa:** mỗi link cho biết mục đích hoặc loại tài nguyên đích.
- **Có phạm vi vừa đủ:** root dẫn tới các collection và khả năng chính, không cần liệt kê mọi thao tác trên từng item.
- **Phản ánh khả năng hiện tại:** links có thể thay đổi theo quyền, trạng thái nghiệp vụ hoặc phiên bản API.
- **Không rò rỉ chi tiết triển khai:** client không cần biết tên controller, service, database hay cấu trúc package.

Client vẫn phải biết URI bootstrap và media type để thực hiện request đầu tiên. HATEOAS không loại bỏ hoàn toàn cấu hình ban đầu; nó giảm số URI và quy tắc điều hướng mà client phải mã hóa cứng sau bước đó.

Không nên chọn một URI entry point phụ thuộc vào tên máy chủ nội bộ hoặc đường dẫn triển khai của service. Dùng host công khai của API và cấu hình proxy để links phản ánh đúng địa chỉ bên ngoài.

## Chọn relation cho các links cấp cao

Relation mô tả ngữ nghĩa của mối quan hệ giữa representation hiện tại và tài nguyên đích. Một số relation thường gặp:

| Relation | Ý nghĩa | Ví dụ tại API root |
|---|---|---|
| self | URI của representation hiện tại. | Link về /api. |
| collection | Tài nguyên đích là một collection liên quan. | Link tới collection đơn hàng. |
| search | Tài nguyên đích hỗ trợ tìm kiếm. | URI template truy vấn đơn hàng. |
| profile | Mô tả profile mà representation tuân theo. | Link tới tài liệu profile của API. |
| orders | Relation nghiệp vụ tùy chỉnh chỉ collection đơn hàng. | Link tới /api/orders. |
| customers | Relation nghiệp vụ tùy chỉnh chỉ collection khách hàng. | Link tới /api/customers. |

Nên dùng relation chuẩn IANA khi ngữ nghĩa phù hợp. Với quan hệ riêng của ứng dụng, có thể dùng relation tùy chỉnh; khi cần khả năng liên thông rộng, định danh relation bằng URI và công bố tài liệu mô tả relation. Trong HAL, CURIE có thể rút gọn các extension relation URI.

Một collection có thể được công bố bằng relation collection, nhưng nếu API root có nhiều collection thì relation nghiệp vụ như orders và customers giúp client phân biệt đích rõ ràng hơn. Điều quan trọng là duy trì ngữ nghĩa ổn định và không dùng cùng một relation cho các tài nguyên không liên quan.

Trong code, Spring HATEOAS biểu diễn relation bằng LinkRelation. Với relation chuẩn, dùng IanaLinkRelations; với relation riêng, dùng LinkRelation.of(...):

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

var selfRel = IanaLinkRelations.SELF;
var ordersRel = LinkRelation.of("orders");
~~~

Không dùng tên method Java hoặc tên controller làm relation. Client cần hiểu ý nghĩa của link, không cần biết class nào đã tạo ra nó.

## Tạo API root bằng Spring MVC

Một API root có thể dùng DTO nhỏ để mô tả API và bọc nó bằng EntityModel:

~~~java
public record ApiRootResponse(
        String name,
        String description) {
}
~~~

Controller tạo links dựa trên mapping của các controller chức năng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api")
class ApiRootController {

    @GetMapping
    EntityModel<ApiRootResponse> root() {
        Link self = linkTo(methodOn(ApiRootController.class)
                .root())
                .withSelfRel();

        Link orders = linkTo(methodOn(OrderController.class)
                .findAll())
                .withRel(LinkRelation.of("orders"));

        Link customers = linkTo(methodOn(CustomerController.class)
                .findAll())
                .withRel(LinkRelation.of("customers"));

        Link search = Link.of(
                "/api/orders{?status,customerName,page,size,sort}",
                IanaLinkRelations.SEARCH)
                .withTemplated(true);

        Link profile = Link.of(
                "/api/profile",
                LinkRelation.of("profile"));

        return EntityModel.of(
                new ApiRootResponse(
                        "Orders API",
                        "API quản lý đơn hàng và khách hàng"),
                self,
                orders,
                customers,
                search,
                profile);
    }
}
~~~

Ví dụ giả định OrderController và CustomerController có các method findAll() được ánh xạ tới collection endpoints. methodOn(...) tạo proxy để Spring HATEOAS đọc mapping; nó không gọi controller method thật và không thực hiện truy vấn.

Link.of(...) được dùng cho search URI template vì template mô tả một tập query parameters có thể thay đổi. withTemplated(true) đánh dấu link là URI template để HAL serializer công bố thuộc tính templated.

Root endpoint có thể trả EntityModel<ApiRootResponse> như response body thông thường. Spring MVC chọn message converter; với hypermedia support đã bật, Spring HATEOAS serialize nội dung và links theo media type mà client yêu cầu.

## Công bố URI bootstrap cho client

Client cần biết entry point đầu tiên. Có thể phân phối URI này qua:

- Cấu hình môi trường của ứng dụng client.
- Tài liệu tích hợp hoặc trang developer portal.
- Cấu hình tenant hoặc endpoint discovery của nền tảng.
- Một URI ổn định được công bố trong hợp đồng triển khai.

Không yêu cầu client tự đoán rằng collection luôn nằm ở /api/orders hoặc ghép URL từ tên resource. Sau request bootstrap, client nên tìm relation orders, customers, search và theo href tương ứng.

Nếu API có nhiều môi trường, chỉ thay base URI cấu hình của môi trường. Các link trong response sẽ dẫn client tới host và path phù hợp của môi trường đó.

Có thể cung cấp một redirect từ / tới /api, nhưng redirect không thay thế root representation. Client cần nhận được media type hypermedia và links ở đích cuối cùng.

## Search link và URI template

Entry point thường cung cấp link tới collection và link search. Hai link có vai trò khác nhau:

- Relation orders dẫn tới collection resource.
- Relation search cho biết client có thể thực hiện truy vấn và truyền các filter được hỗ trợ.

Ví dụ URI template:

~~~text
/api/orders{?status,customerName,page,size,sort}
~~~

Client có thể mở rộng template thành:

~~~text
/api/orders?status=PAID&customerName=An&page=0&size=20
~~~

URI template không phải endpoint mới; nó là cách mô tả những biến mà client có thể đưa vào URI. Server vẫn phải validate các giá trị, giới hạn page size, allowlist sort properties và áp dụng authorization khi thực hiện tìm kiếm.

Không đưa mọi tham số nội bộ vào template. Chỉ công bố những filter và sort option thuộc hợp đồng công khai. Khi một filter không còn được hỗ trợ, cần xử lý như thay đổi hợp đồng API và có kế hoạch tương thích.

## Entry point và versioning

Entry point nên ổn định để client không phải mã hóa cứng nhiều URI. Nếu API dùng version trong path, có thể giữ root ổn định và để root dẫn tới các phiên bản đang hỗ trợ:

~~~json
{
  "_links": {
    "self": {
      "href": "/api"
    },
    "orders": {
      "href": "/api/v2/orders"
    },
    "legacy-orders": {
      "href": "/api/v1/orders"
    }
  }
}
~~~

Client mới có thể chọn relation orders trỏ tới phiên bản hiện hành; client cũ có thể tiếp tục dùng relation tương thích trong giai đoạn chuyển đổi. Không cần để client tự ghép /v2 vào URL.

Nếu version được biểu diễn qua media type hoặc header, root response vẫn cần công bố media type/profile phù hợp và links đến các khả năng mà client được phép sử dụng. Tránh đưa nhiều cơ chế versioning chồng chéo nếu không có yêu cầu tương thích cụ thể.

Việc giữ root URI ổn định không có nghĩa mọi link phía dưới phải bất biến. Server có thể chuyển collection sang path mới miễn là relation và semantics được duy trì, và client đi theo link mới do server cung cấp.

## Links phản ánh quyền và trạng thái

API root có thể được cá nhân hóa theo người gọi. Đoạn sau minh họa phần tạo links bên trong method root() sau khi các links chung đã được tạo. Người dùng chỉ có quyền đọc đơn hàng sẽ thấy link collection và search, trong khi người quản trị có thể thấy thêm link quản lý:

~~~java
List<Link> links = new ArrayList<>();
links.add(self);
links.add(orders);
links.add(search);

if (authorizationService.canManageOrders(currentUser)) {
    links.add(manageOrders);
}

return EntityModel.of(rootResponse, links);
~~~

Việc không công bố link có thể giúp client hiểu rằng thao tác không khả dụng trong ngữ cảnh hiện tại. Tuy nhiên, links không phải cơ chế bảo mật. Endpoint đích vẫn phải kiểm tra authentication và authorization mỗi khi request được gửi; client có thể lưu hoặc tự tạo URI.

Tương tự, link thao tác chỉ nên xuất hiện khi trạng thái nghiệp vụ cho phép. Ví dụ, link cancel chỉ xuất hiện khi đơn hàng còn ở trạng thái có thể hủy. Server vẫn phải kiểm tra trạng thái tại thời điểm nhận request để tránh race condition.

Không đưa thông tin nhạy cảm vào API root như danh sách tenant nội bộ, tên service private hoặc quyền chi tiết không cần thiết. Chỉ công bố những khả năng có ích cho client hiện tại.

## Content negotiation và caching của API root

API root là representation HTTP nên cần tuân theo content negotiation. Client có thể yêu cầu HAL JSON:

~~~http
GET /api
Accept: application/hal+json
~~~

Nếu client yêu cầu media type không được hỗ trợ, server trả lỗi phù hợp thay vì âm thầm trả một định dạng khác mà client không hiểu. Dùng produces ở mapping khi muốn giới hạn rõ media type; nếu hỗ trợ nhiều hypermedia formats, cấu hình message converters tương ứng.

API root thường ít thay đổi, nhưng links có thể phụ thuộc người dùng, quyền hoặc tenant. Nếu response khác nhau theo Authorization hoặc cookie, cấu hình cache phải tính tới biến thể đó. Không cache một API root cá nhân hóa trong shared cache theo cách khiến người dùng nhận links của người khác. Dùng Cache-Control và Vary phù hợp với cơ chế xác thực và content negotiation của hệ thống.

Nếu root response là giống nhau cho mọi người dùng và chỉ chứa links công khai, có thể cache theo chính sách phù hợp. Khi links thay đổi do triển khai hoặc version rollout, cache lifetime cần đủ ngắn hoặc có validator để client nhận được root representation mới.

## Kiểm thử API entry point

MockMvc xác minh root endpoint có media type, self link và các relation cần thiết:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$.name").value("Orders API"))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.orders.href").exists())
        .andExpect(jsonPath("$._links.customers.href").exists())
        .andExpect(jsonPath("$._links.search.href").exists())
        .andExpect(jsonPath("$._links.search.templated").value(true))
        .andExpect(jsonPath("$._links.profile.href").exists());
~~~

Nên kiểm thử thêm:

- Mọi link trong root đều trỏ tới endpoint thực sự tồn tại.
- Link relation có tên và semantics ổn định.
- Search template chỉ công bố các query parameters được hỗ trợ.
- User không có quyền quản trị không nhận link manage.
- User không có quyền vẫn bị từ chối nếu gọi trực tiếp URI của thao tác quản trị.
- Host và scheme của link đúng khi ứng dụng chạy sau proxy tin cậy.
- Root URI tiếp tục ổn định khi collection endpoint đổi path hoặc version.
- Content-Type và cache headers phù hợp với biến thể response.

Một kiểm thử quan trọng là bắt đầu từ /api, đọc relation orders, lấy href của link rồi gọi href đó trong test tiếp theo. Cách này xác minh client có thể khám phá API theo links thay vì phụ thuộc vào đường dẫn được viết cứng trong test.

## Những lỗi thường gặp

- **Bắt client biết tất cả endpoint:** chỉ công bố URI bootstrap; để client khám phá links từ root và các resource tiếp theo.
- **Root chỉ trả metadata mà không có links:** thêm self và các relation cấp cao cần thiết.
- **Dùng relation không có ngữ nghĩa ổn định:** chọn relation IANA hoặc extension relation được tài liệu hóa.
- **Dùng relation như tên controller:** relation mô tả mục đích link, không mô tả cấu trúc code.
- **Đưa mọi endpoint vào root:** root chỉ cần dẫn tới các collection và khả năng cấp cao; resource con công bố links chi tiết hơn.
- **Ghép URL bằng chuỗi trong client:** theo href trong response để server có thể thay đổi URI.
- **Coi link ẩn là cơ chế authorization:** luôn kiểm tra quyền ở endpoint đích.
- **Công bố search template quá rộng:** chỉ đưa filter và sort được hỗ trợ vào URI template.
- **Để entry point thay đổi theo mỗi lần deploy:** giữ bootstrap URI ổn định và chuyển hướng client bằng links.
- **Cache root cá nhân hóa như response công khai:** tách cache theo người dùng/tenant hoặc không shared-cache response có links riêng.

## Quy trình thiết kế entry point

1. Chọn một URI bootstrap công khai và ổn định cho API.
2. Xác định các collection và khả năng cấp cao mà client cần khám phá đầu tiên.
3. Chọn relation chuẩn IANA hoặc relation nghiệp vụ có ngữ nghĩa được công bố.
4. Tạo API root representation bằng EntityModel hoặc RepresentationModel.
5. Dùng WebMvcLinkBuilder để tạo links theo controller mappings và URI template cho search.
6. Công bố profile hoặc tài liệu hợp đồng khi client cần hiểu semantics bổ sung.
7. Chỉ đưa links phù hợp với quyền và trạng thái hiện tại; vẫn bảo vệ endpoint bằng authorization.
8. Kiểm thử khả năng bắt đầu từ root và đi theo links tới các tài nguyên tiếp theo.

Entry point là điểm khởi đầu của quá trình khám phá Web API. Khi URI bootstrap ổn định, root representation công bố các relation rõ nghĩa và client luôn theo href do server cung cấp, API có thể thay đổi cấu trúc URI và phiên bản ở phía sau mà giảm phụ thuộc vào mã client.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Building links in Spring MVC: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder
- Spring HATEOAS Reference Documentation, Representation models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models
- Spring HATEOAS Reference Documentation, HAL: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal
- IANA Link Relations Registry: https://www.iana.org/assignments/link-relations/link-relations.xhtml
