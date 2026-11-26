# API root resource trong Spring HATEOAS

API root resource là điểm vào ban đầu của một Web API. Client gửi request đến URI gốc đã được cấu hình hoặc được cung cấp khi tích hợp, nhận một representation chứa các liên kết tới collection và khả năng mà API công bố, rồi tiếp tục điều hướng bằng những link đó. Với Spring HATEOAS, API root thường được biểu diễn bằng một model chỉ chứa links, được tạo từ mapping của các controller và serialize thành HAL JSON.

Ví dụ, client bắt đầu tại `https://api.example.com/api`. Response root công bố link tới orders, customers, search và profile. Client có thể khám phá tài nguyên cần dùng mà không phải tự ghép các đường dẫn `/api/orders` hoặc `/api/customers`.

## 1. API root resource là gì?

API root resource là một resource HTTP đại diện cho điểm vào của một API hoặc một phiên bản API. Nó thường không chứa toàn bộ dữ liệu nghiệp vụ. Representation của nó chủ yếu công bố các link dẫn tới những resource khác.

Ví dụ HAL JSON tối giản:

~~~json
{
  "_links": {
    "self": {
      "href": "/api"
    },
    "https://api.example.com/rels/orders": {
      "href": "/api/orders"
    },
    "https://api.example.com/rels/customers": {
      "href": "/api/customers"
    }
  }
}
~~~

Trong ví dụ, `/api` là URI của root resource. Hai link còn lại dẫn tới collection resource. Client có thể bắt đầu từ root rồi chọn link theo relation phù hợp với tác vụ.

API root có ba vai trò chính:

- Cung cấp một điểm bắt đầu ổn định cho client.
- Công bố những khả năng và tài nguyên mà server muốn client khám phá.
- Giảm sự phụ thuộc của client vào cấu trúc URL nội bộ của server.

API root không phải trang HTML index và cũng không nhất thiết là endpoint trả về danh sách mọi bản ghi. Nó là một representation hypermedia có thể được máy khách đọc và điều hướng.

## 2. Phân biệt API root, collection resource và item resource

Ba loại resource thường xuất hiện trong một API:

| Resource | Ví dụ URI | Vai trò |
|---|---|---|
| API root | `/api` | Điểm bắt đầu và công bố các khả năng cấp cao |
| Collection | `/api/orders` | Truy cập, tìm kiếm hoặc duyệt tập đơn hàng |
| Item | `/api/orders/42` | Truy cập một đơn hàng cụ thể |

Một luồng điều hướng điển hình:

~~~text
GET /api
   |
   | rel="orders"
   v
GET /api/orders
   |
   | rel="self" của một phần tử
   v
GET /api/orders/42
~~~

Mỗi resource có contract và link phù hợp với phạm vi của nó. API root có thể dẫn tới collection; collection có thể dẫn tới item, search và các trang tiếp theo; item có thể dẫn tới customer, payment hoặc các thao tác khả dụng.

Không nên đưa toàn bộ đơn hàng vào API root. Cách đó làm response root tăng theo dữ liệu và biến entry point thành một collection lớn khó phân trang, cache và tiến hóa.

## 3. API root có bắt buộc trong REST không?

REST yêu cầu client có một điểm bắt đầu được biết trước, nhưng không bắt buộc mọi API phải dùng một endpoint cụ thể tên là `/` hoặc `/api`. Điểm bắt đầu có thể được cung cấp qua cấu hình, tài liệu tích hợp, DNS, một trang đăng ký dịch vụ hoặc một cơ chế bootstrap khác.

Trong API dùng hypermedia, một API root resource là cách thực tế để cung cấp điểm vào và công bố các quan hệ tiếp theo. Nó giúp client giảm việc hard-code URI của từng endpoint.

Một API nhỏ chỉ phục vụ một thao tác có thể không cần root resource riêng. Khi API có nhiều collection, search endpoint, profile hoặc nhiều phiên bản, root resource thường hữu ích hơn.

Điều quan trọng là client biết URI entry point từ một nguồn đáng tin cậy. Sau request đầu tiên, các URI còn lại nên được khám phá từ representation và link relation.

## 4. Thiết kế nội dung của API root

Root resource nên công bố các link có ý nghĩa đối với client. Một số loại link thường gặp:

| Link relation | Mục đích |
|---|---|
| `self` | URI của API root hiện tại |
| Relation collection | Dẫn tới collection như orders hoặc customers |
| `search` | Dẫn tới điểm tìm kiếm hoặc URI template tìm kiếm |
| `profile` | Dẫn tới tài liệu mô tả semantics của representation |
| `describedby` | Dẫn tới tài liệu mô tả API hoặc contract |
| Relation phiên bản | Dẫn tới root của phiên bản API khác nếu có |

Không cần công bố mọi endpoint nội bộ. Hãy công bố các khả năng mà client được phép sử dụng và cần biết để hoàn thành workflow.

Root resource có thể thay đổi link tùy theo principal, tenant hoặc trạng thái hệ thống. Ví dụ người dùng không có quyền quản lý đơn hàng có thể không nhận link tới chức năng quản trị. Dù vậy, việc ẩn link không thay thế authorization ở endpoint đích.

## 5. Chọn link relation cho collection

Link relation mô tả ý nghĩa của mối quan hệ giữa resource hiện tại và resource đích. Không nên dùng tên relation tùy tiện mà không có quy ước.

Với relation đã đăng ký trong IANA, dùng tên relation chuẩn. Với relation mở rộng của ứng dụng, có thể dùng URI relation ổn định, ví dụ:

~~~text
https://api.example.com/rels/orders
https://api.example.com/rels/customers
~~~

URI relation giúp tránh xung đột tên với relation chuẩn hoặc relation do thư viện khác định nghĩa. Tài liệu API nên giải thích ý nghĩa và cách client sử dụng từng relation mở rộng.

Trong ví dụ dưới đây, relation orders và customers được biểu diễn bằng URI relation mở rộng. Nếu hệ thống dùng CURIE để rút gọn relation, cần công bố CURIE mapping trong representation theo định dạng hypermedia đang dùng.

## 6. Tạo model dành cho API root

API root thường không cần payload domain. Có thể tạo một model nhỏ kế thừa `RepresentationModel` để chứa các link.

~~~java
import org.springframework.hateoas.RepresentationModel;

public class ApiRootModel extends RepresentationModel<ApiRootModel> {
}
~~~

Model không có field nghiệp vụ. Các link được thêm tại controller hoặc một thành phần chuyên trách xây dựng root links.

Cách này giữ rõ ý nghĩa: API root là một representation model có hypermedia controls. Nếu cần thêm metadata như tên API hoặc phiên bản hiển thị, có thể mở rộng model, nhưng không nên đưa thông tin cấu hình nội bộ hoặc secret vào response.

## 7. Tạo API root controller bằng Spring MVC

Spring MVC controller có thể trả về `ApiRootModel`. Dùng `WebMvcLinkBuilder` và `methodOn` để lấy URI từ mapping của các controller đích.

~~~java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api")
class ApiRootController {

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    ApiRootModel root() {
        ApiRootModel model = new ApiRootModel();

        model.add(
            linkTo(methodOn(ApiRootController.class).root())
                .withSelfRel()
        );

        model.add(
            linkTo(methodOn(OrderController.class).all())
                .withRel(LinkRelation.of(
                    "https://api.example.com/rels/orders"
                ))
        );

        model.add(
            linkTo(methodOn(CustomerController.class).all())
                .withRel(LinkRelation.of(
                    "https://api.example.com/rels/customers"
                ))
        );

        return model;
    }
}
~~~

Giả sử `OrderController` và `CustomerController` có method `all()` ánh xạ tới collection tương ứng. Các controller này được Spring MVC quản lý độc lập; root controller chỉ tham chiếu method mapping để tạo link.

Những điểm cần chú ý:

- `@RequestMapping("/api")` đặt root resource tại `/api`.
- `@GetMapping` xử lý GET tới root path.
- `produces` công bố HAL JSON cho endpoint.
- `linkTo(methodOn(...))` tạo URI dựa trên controller mapping.
- `withSelfRel()` tạo link `self`.
- `LinkRelation.of(...)` tạo relation mở rộng có URI.

Trong dự án thực tế, đặt các relation URI trong hằng số hoặc một lớp định nghĩa relation dùng chung để tránh gõ lặp và sai khác giữa các assembler.

## 8. Representation HAL của API root

Khi client gửi:

~~~http
GET /api HTTP/1.1
Accept: application/hal+json
~~~

Spring HATEOAS có thể serialize model thành HAL JSON:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "self": {
      "href": "/api"
    },
    "https://api.example.com/rels/orders": {
      "href": "/api/orders"
    },
    "https://api.example.com/rels/customers": {
      "href": "/api/customers"
    }
  }
}
~~~

Root response không cần `_embedded` nếu mục đích của nó chỉ là công bố link. Client có thể theo link orders hoặc customers để lấy collection representation.

Nếu API hỗ trợ nhiều media type, root endpoint cần khai báo và cấu hình media type phù hợp. Đừng trả body HAL nhưng công bố `Content-Type: application/json` nếu contract yêu cầu client hiểu HAL.

## 9. Thêm search link và URI template

Root resource có thể công bố khả năng tìm kiếm collection. Với Spring HATEOAS, relation `search` có thể gắn vào một URI template liệt kê query variables.

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.UriTemplate;

Link searchLink = Link.of(
    UriTemplate.of(
        "/api/orders{?status,customer,page,size,sort}"
    ),
    IanaLinkRelations.SEARCH
);

model.add(searchLink);
~~~

Trong HAL, link có thể được serialize như sau:

~~~json
{
  "_links": {
    "search": {
      "href": "/api/orders{?status,customer,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Client đọc danh sách biến từ template và cung cấp những điều kiện cần thiết. Nó không phải tự đoán tên query parameter hoặc ghép URL.

Trong ứng dụng thực tế, nên tạo URI template từ mapping controller thay vì lặp lại `/api/orders`:

~~~java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.UriTemplate;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

URI ordersUri = linkTo(
    methodOn(OrderController.class).all()
).toUri();

UriTemplate template = UriTemplate.of(
    ordersUri + "{?status,customer,page,size,sort}"
);

model.add(Link.of(template, IanaLinkRelations.SEARCH));
~~~

Ví dụ giả định method `all()` trỏ tới collection `/api/orders`. Nếu collection mapping thay đổi, phần base URI được tạo lại từ controller mapping. Danh sách biến template vẫn phải đồng bộ với contract của search endpoint.

## 10. Thêm link profile và tài liệu

API root có thể dẫn tới tài liệu giải thích semantics của representation. Relation `profile` thường trỏ tới tài liệu profile; `describedby` có thể trỏ tới tài liệu mô tả contract hoặc API.

~~~java
import org.springframework.hateoas.Link;

model.add(
    Link.of("https://api.example.com/profiles/order-api")
        .withRel("profile")
);

model.add(
    Link.of("https://docs.example.com/orders-api")
        .withRel("describedby")
);
~~~

Hai URI trên chỉ là ví dụ về địa chỉ tài liệu công khai. Trong ứng dụng thật, hãy dùng URI do tổ chức kiểm soát và duy trì ổn định.

Profile mô tả ý nghĩa hoặc ràng buộc bổ sung của representation. Tài liệu API có thể giải thích cách gọi endpoint, query parameter, lỗi và các relation mở rộng. Chúng bổ sung cho hypermedia link, không thay thế khả năng điều hướng.

## 11. Client điều hướng từ API root như thế nào?

Một hypermedia client có thể thực hiện quy trình:

1. Nhận URI entry point từ cấu hình hoặc thông tin tích hợp.
2. Gửi GET tới URI đó với `Accept` phù hợp.
3. Đọc `_links` trong root representation.
4. Tìm relation tương ứng với tác vụ, ví dụ relation orders.
5. Theo `href` của link để truy cập collection.
6. Từ collection, tiếp tục theo `self`, `next`, `search` hoặc link tới item.

Ví dụ logic client ở mức khái niệm:

~~~text
entryUri = configuredApiEntryPoint
root = GET(entryUri, Accept: application/hal+json)

ordersLink = findLink(root, "https://api.example.com/rels/orders")
orders = GET(ordersLink.href, Accept: application/hal+json)

nextLink = findLink(orders, "next")
if nextLink exists:
    nextPage = GET(nextLink.href, Accept: application/hal+json)
~~~

Client không cần biết collection được đặt tại `/api/orders` hay `/v2/sales`. Server có thể thay đổi route mà không làm hỏng client tuân thủ hypermedia, miễn là relation và semantics được duy trì.

Client nên bỏ qua relation không hiểu thay vì thất bại khi root bổ sung link mới. Điều này giúp API có thể mở rộng mà không buộc mọi client cập nhật đồng thời.

## 12. Root resource và API versioning

Có thể tổ chức root resource riêng cho từng phiên bản:

~~~text
/api/v1
/api/v2
~~~

Mỗi root công bố các collection và khả năng thuộc phiên bản đó. Một root cấp cao hơn cũng có thể công bố link tới các phiên bản được hỗ trợ.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/api"
    },
    "v1": {
      "href": "/api/v1"
    },
    "v2": {
      "href": "/api/v2"
    }
  }
}
~~~

`v1` và `v2` trong ví dụ là relation do API định nghĩa; cần mô tả trong tài liệu hoặc dùng URI relation mở rộng nếu muốn tránh tên ngắn không chuẩn.

Khi thêm endpoint mới tương thích ngược, có thể thêm link relation mới vào root. Khi thay đổi semantics không tương thích, hãy cân nhắc một phiên bản root riêng thay vì âm thầm thay đổi ý nghĩa của relation cũ.

Không nên dùng API root làm nơi công bố mọi chi tiết version nội bộ. Chỉ công bố phiên bản mà client có thể thực sự sử dụng.

## 13. Giữ link đúng khi chạy sau reverse proxy

Trong môi trường production, ứng dụng có thể chạy sau gateway hoặc reverse proxy. Client truy cập:

~~~text
https://api.example.com/platform/api
~~~

nhưng ứng dụng phía sau proxy chỉ thấy:

~~~text
http://service-internal:8080/api
~~~

Nếu forwarded headers không được xử lý, link được tạo từ request có thể chứa host, scheme hoặc prefix nội bộ. Client nhận link không thể truy cập từ bên ngoài.

Với Spring Boot servlet application, có thể cấu hình:

~~~properties
server.forward-headers-strategy=framework
~~~

Cấu hình này cho phép framework xử lý forwarded headers khi triển khai phù hợp. Reverse proxy phải gửi đúng `Forwarded` hoặc `X-Forwarded-*` headers và chỉ tin các header đến từ proxy được tin cậy. Proxy biên cần loại bỏ forwarded headers do client bên ngoài tự gửi trước khi thêm giá trị chính xác.

Sau khi cấu hình, kiểm thử API root qua đúng hostname và prefix bên ngoài. Đừng chỉ kiểm thử bằng localhost vì môi trường đó có thể không phản ánh URI mà client production nhìn thấy.

## 14. Root links và bảo mật

API root có thể được cá nhân hóa theo quyền truy cập hoặc trạng thái của người gọi.

Ví dụ:

- Người mua có link tới collection đơn hàng của chính họ.
- Nhân viên hỗ trợ có link tra cứu đơn hàng.
- Quản trị viên có link tới chức năng quản trị.
- Người chưa đăng nhập chỉ thấy link đăng nhập hoặc tài liệu công khai.

Việc công bố link nên dựa trên quyền và capability thực tế. Tuy nhiên, không được xem việc ẩn link là cơ chế bảo mật duy nhất. Endpoint đích vẫn phải xác thực và kiểm tra quyền trên từng request.

Không đưa thông tin bí mật, token hoặc dữ liệu nhạy cảm vào link. Query string có thể xuất hiện trong log và history.

Nếu root response phụ thuộc người dùng, tenant hoặc quyền truy cập, cần thiết kế cache phù hợp. Tránh để cache dùng chung trả root links của người dùng này cho người dùng khác. Có thể dùng cache private hoặc policy không cache tùy mức độ nhạy cảm của response.

## 15. Caching API root

API root thường thay đổi ít hơn dữ liệu nghiệp vụ, vì vậy có thể cache trong một khoảng thời gian phù hợp. Tuy nhiên, chính sách cache phải xét tới:

- Link có thay đổi theo phiên bản hoặc rollout không.
- Link có phụ thuộc authentication hoặc tenant không.
- Response có khác nhau theo `Accept` hay không.
- Gateway/CDN có phân biệt các biến thể response không.

Nếu response phụ thuộc media type, `Vary: Accept` có thể cần thiết để cache phân biệt representation HAL với các representation khác. Nếu root phụ thuộc người dùng, dùng cache policy riêng tư hoặc không cache ở shared cache.

Không đặt thời gian cache quá dài nếu root là nơi công bố các capability thay đổi theo feature flag hoặc trạng thái triển khai. Một client dùng root cũ có thể tiếp tục thấy link tới chức năng đã bị gỡ.

## 16. Xử lý root resource và lỗi HTTP

Root endpoint cần có hành vi rõ ràng khi client truy cập sai URI, không gửi media type được hỗ trợ hoặc chưa xác thực.

| Tình huống | Status thường gặp | Ý nghĩa |
|---|---|---|
| Root tồn tại và representation được tạo | `200 OK` | Client nhận được entry point |
| Client gửi `Accept` không được hỗ trợ | `406 Not Acceptable` | Server không tạo được representation phù hợp |
| Client chưa xác thực và root yêu cầu đăng nhập | `401 Unauthorized` | Cần cung cấp thông tin xác thực |
| Client đã xác thực nhưng không được phép xem root | `403 Forbidden` | Không đủ quyền |
| URI root không tồn tại | `404 Not Found` | Entry point không được triển khai tại URI đó |

Nếu root được thiết kế công khai, có thể cho phép truy cập root mà không cần đăng nhập nhưng chỉ công bố các link công khai. Endpoint riêng tư vẫn thực hiện authorization độc lập.

## 17. Kiểm thử API root bằng MockMvc

Kiểm thử root cần xác nhận status, media type, self link và các relation quan trọng.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(
        get("/api")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.search.templated").value(true));
~~~

Có thể kiểm tra relation mở rộng bằng JSONPath bracket notation:

~~~java
mockMvc.perform(
        get("/api")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['https://api.example.com/rels/orders'].href"
    ).exists());
~~~

Các trường hợp nên có:

- Root trả `200 OK` và đúng `Content-Type`.
- `self` trỏ tới URI root có thể truy cập từ góc nhìn client.
- Link tới collection tồn tại và theo đúng relation contract.
- Search URI template được đánh dấu `templated: true`.
- Root không vô tình trả dữ liệu nghiệp vụ lớn.
- Các link theo quyền người dùng được công bố đúng.
- Forwarded headers tạo host, scheme và prefix đúng sau proxy.
- Cache headers phù hợp với response công khai hoặc cá nhân hóa.

Ngoài MockMvc, nên có kiểm thử tích hợp qua reverse proxy hoặc gateway trong môi trường gần production để xác minh các URI được sinh ra.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Client phải hard-code mọi endpoint | Route thay đổi làm client hỏng | Bắt đầu từ API root và theo relation |
| API root trả toàn bộ collection | Response lớn và khó phân trang | Chỉ công bố link tới collection |
| Dùng `self` cho link collection | Client khó phân biệt root với collection | Dùng relation riêng có semantics rõ |
| Relation mở rộng không được tài liệu hóa | Client không biết link có ý nghĩa gì | Dùng URI relation ổn định và mô tả contract |
| Hard-code URL trong controller | Mapping đổi nhưng root link không đổi | Dùng `WebMvcLinkBuilder` và `methodOn` |
| Root không công bố search template | Client phải đoán filter parameter | Thêm link `search` với URI template |
| Link chứa host nội bộ sau proxy | Client không thể truy cập URI | Cấu hình forwarded headers và kiểm thử bên ngoài |
| Ẩn link rồi bỏ authorization endpoint | Người dùng có thể gọi trực tiếp endpoint | Luôn kiểm tra quyền ở endpoint đích |
| Cache chung response cá nhân hóa | Người dùng nhận link của principal khác | Dùng cache private hoặc policy phù hợp |
| Root đổi semantics relation cũ | Client hiện tại hiểu sai capability | Giữ relation ổn định hoặc tạo version root mới |

## 19. Quy trình xây dựng API root resource

Khi triển khai API root với Spring HATEOAS, hãy thực hiện theo trình tự:

1. Chọn URI entry point ổn định cho API hoặc từng phiên bản.
2. Xác định các collection và capability mà client cần khám phá.
3. Chọn IANA relation đã đăng ký hoặc URI relation mở rộng cho từng link.
4. Tạo root representation model kế thừa `RepresentationModel`.
5. Tạo link từ controller mapping bằng `WebMvcLinkBuilder` và `methodOn`.
6. Thêm search URI template, profile hoặc link tài liệu khi phù hợp.
7. Trả root representation theo media type hypermedia như HAL JSON.
8. Bảo đảm client có thể theo link từ root tới collection và item.
9. Xử lý quyền truy cập, cache và forwarded headers theo môi trường triển khai.
10. Kiểm thử relation, href, media type và hành vi sau reverse proxy.

API root resource tạo một điểm bắt đầu rõ ràng cho hypermedia API. Spring HATEOAS giúp biểu diễn root bằng `RepresentationModel`, tạo link từ controller mapping và công bố các relation để client khám phá collection, search và profile. Khi client điều hướng dựa trên những link này, server có thể thay đổi cấu trúc URI nội bộ mà vẫn duy trì contract hypermedia ổn định.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc.link-builder)
- [Spring HATEOAS Reference — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS API — RepresentationModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [Spring HATEOAS API — LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [RFC 6570 — URI Template](https://www.rfc-editor.org/rfc/rfc6570)
