# Điều hướng theo relation

Một client REST thường bắt đầu bằng một địa chỉ đã biết, sau đó cần tìm collection, item, trang tiếp theo hoặc thao tác nghiệp vụ. Nếu client tự ghép URL như `/api/orders/42/approval`, nó phải biết cấu trúc đường dẫn và sẽ dễ hỏng khi server đổi mapping. Hypermedia giải quyết vấn đề này bằng cách để server công bố các link cùng link relation mô tả ý nghĩa của từng đích.

Trong Spring HATEOAS, client có thể dùng `Traverson` để bắt đầu từ một URI entry point và đi lần lượt qua các relation. `Traverson` đọc representation, tìm link theo relation, gửi request tiếp theo và có thể chuyển kết quả cuối thành Java object. Khi chỉ cần trích một link từ JSON đã nhận, `LinkDiscoverer` cung cấp API tìm link theo relation.

Bài học này tập trung vào cách client điều hướng theo relation: hiểu entry point, phân biệt relation với URI, dùng `Traverson.follow(...)`, mở rộng URI template, truy cập embedded item, đọc kết quả có kiểu, xử lý link tùy chọn, dùng `LinkDiscoverer`, và kiểm thử hành vi điều hướng.

## 1. Vì sao client nên điều hướng theo relation?

Giả sử API đơn hàng công bố:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    },
    "search": {
      "href": "https://api.example.com/api/orders/search"
    }
  }
}
~~~

Client biết link `search` là điểm vào tìm kiếm vì relation có ngữ nghĩa đó. Client không cần tự tạo đường dẫn bằng cách nối `/search` vào URI collection.

Khi API thay đổi path từ `/api/orders` sang `/v2/order-collection`, server chỉ cần công bố `href` mới. Client tiếp tục tìm relation `search` và theo URI được trả về.

~~~mermaid
flowchart TD
    A["API entry point"] -->|"orders"| B["Orders collection"]
    B -->|"search"| C["Search resource"]
    C -->|"byStatus"| D["Search result"]
    D -->|"next"| E["Next page"]
    D -->|"self"| F["Current result"]
~~~

Điều hướng theo relation tạo ra một ranh giới rõ ràng:

- Server chịu trách nhiệm công bố link và relation phù hợp.
- Client hiểu relation để chọn bước tiếp theo.
- Client sử dụng `href` do server cung cấp để gửi request.
- Cấu trúc URI nội bộ có thể thay đổi mà không bắt buộc client sửa logic điều hướng.

Client vẫn cần biết URI entry point ban đầu và vocabulary relation mà nó hiểu. Hypermedia giảm sự phụ thuộc vào các URI trung gian; nó không loại bỏ hoàn toàn cấu hình điểm bắt đầu hoặc yêu cầu hiểu ngữ nghĩa nghiệp vụ.

## 2. Phân biệt relation và href

Một link có hai thành phần quan trọng:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Relation | Mô tả mối quan hệ giữa resource hiện tại và resource đích | `orders`, `next`, `search`, `self` |
| `href` | Địa chỉ cụ thể để truy cập resource đích | `https://api.example.com/api/orders` |

Relation không phải tên endpoint. `orders` có thể trỏ đến `/api/orders`, `/v2/order-collection` hoặc một URI khác. Client chỉ cần tìm đúng relation.

Các relation IANA như `self`, `next`, `prev`, `first` và `last` có ngữ nghĩa đã đăng ký. API cũng có thể dùng extension relation như `https://api.example.com/rels/approve`. Với HAL, extension relation có thể được biểu diễn bằng CURIE, chẳng hạn `acme:approve`.

Client cần phân biệt relation chuẩn với relation riêng:

- Với relation chuẩn, client có thể tái sử dụng hiểu biết đã thống nhất trong IANA registry.
- Với custom relation, client phải biết vocabulary của API hoặc đọc tài liệu/profile tương ứng.
- Relation không tự mô tả HTTP method, request body hay quyền thực hiện hành động; khi cần, client phải đọc affordance hoặc metadata của media type.

## 3. Khởi tạo Traverson từ API entry point

`Traverson` thuộc package `org.springframework.hateoas.client`. Constructor nhận URI gốc và danh sách media type mà client muốn sử dụng. Với HAL, dùng `MediaTypes.HAL_JSON`:

~~~java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

URI apiRoot = URI.create("https://api.example.com/api/");

Traverson traverson = new Traverson(
        apiRoot,
        MediaTypes.HAL_JSON
);
~~~

URI entry point là điểm bắt đầu mà ứng dụng client cần cấu hình hoặc nhận từ một cơ chế bootstrap khác. Sau khi lấy được representation đầu tiên, `Traverson` dùng relation để khám phá các URI tiếp theo.

Media type truyền vào constructor được dùng để thiết lập `Accept` header cho request. Server cần trả representation tương thích với media type đó. Nếu API dùng HAL, response thường có cấu trúc `_links` và `_embedded`.

`Traverson` mặc định có `HalLinkDiscoverer` để tìm link trong HAL. Với media type khác, cần đăng ký converter và link discoverer tương ứng.

## 4. Điều hướng qua nhiều relation bằng follow

Phương thức `follow(...)` nhận một hoặc nhiều relation. Mỗi relation là một bước điều hướng; `Traverson` lấy representation hiện tại, tìm link theo relation tiếp theo rồi gửi request đến đích.

Ví dụ API phim có chuỗi relation `movies`, `movie`, `actor`:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

Traverson traverson = new Traverson(
        URI.create("https://api.example.com/"),
        MediaTypes.HAL_JSON
);

Map<String, Object> parameters = Map.of("user", 27);

String actorName = traverson
        .follow("movies", "movie", "actor")
        .withTemplateParameters(parameters)
        .toObject("$.name");
~~~

Ví dụ giả định link `movie` và `actor` trong API có URI template chứa biến `user`. `Traverson` lần lượt đi theo ba relation, mở rộng những template có biến tương ứng, rồi lấy trường `name` từ representation cuối bằng JSONPath.

Có thể viết từng bước riêng để dễ quan sát:

~~~java
var traversal = traverson.follow("movies");
traversal = traversal.follow("movie");
traversal = traversal.follow("actor");

String actorName = traversal.toObject("$.name");
~~~

`follow(...)` có thể nối chuỗi. Một chuỗi nhiều relation tương ứng với nhiều lần đọc resource trong quá trình điều hướng. Vì vậy, hãy giữ số hop hợp lý và tránh thực hiện traversal lặp lại cho từng dòng dữ liệu nếu API có thể trả collection phù hợp ngay từ đầu.

## 5. Dùng relation có URI template

Một link có thể chứa URI template, ví dụ:

~~~json
{
  "_links": {
    "byStatus": {
      "href": "https://api.example.com/api/orders/search{?status,page,size}",
      "templated": true
    }
  }
}
~~~

`templated: true` cho biết client cần cung cấp giá trị cho các biến trước khi gửi request. Client không cần tự nối `?status=` hoặc đoán thứ tự query parameter.

`withTemplateParameters(Map)` truyền một map biến cho traversal:

~~~java
import java.util.Map;

Integer totalElements = traverson
        .follow("orders", "search", "byStatus")
        .withTemplateParameters(Map.of(
                "status", "PENDING",
                "page", 0,
                "size", 20
        ))
        .toObject("$.page.totalElements");
~~~

Ví dụ giả định API root có relation `orders`, collection có relation `search`, và search resource có relation `byStatus` với các biến tương ứng. Map được áp dụng cho những URI template gặp trong traversal. Nếu nhiều hop có biến trùng tên nhưng cần giá trị khác nhau, nên dùng `Hop` để cấu hình riêng từng bước.

## 6. Cấu hình tham số cho một hop bằng Hop

`Hop` đại diện cho một bước điều hướng và cho phép gắn tham số template riêng. Phương thức tĩnh `rel(...)` giúp tạo hop theo relation:

~~~java
import static org.springframework.hateoas.client.Hop.rel;

Integer totalElements = traverson
        .follow("orders")
        .follow("search")
        .follow(rel("byStatus")
                .withParameter("status", "PENDING")
                .withParameter("page", 0)
                .withParameter("size", 20))
        .toObject("$.page.totalElements");
~~~

`withParameter(...)` trả về một `Hop` mới và có thể nối nhiều lần. Nếu đã có một map, dùng `withParameters(map)`. Cách này hữu ích khi một traversal có nhiều search resource và mỗi hop cần một tập biến khác nhau.

Ví dụ:

~~~java
import static org.springframework.hateoas.client.Hop.rel;

var traversal = traverson
        .follow("catalog")
        .follow(rel("search")
                .withParameter("category", "books"))
        .follow(rel("offers")
                .withParameter("currency", "VND"));
~~~

Ở đây, `category` chỉ áp dụng cho hop `search`, còn `currency` áp dụng cho hop `offers`. Client không cần biết các biến được ghép vào query string như thế nào; `Traverson` mở rộng URI template của link được phát hiện.

## 7. Duyệt embedded item trong HAL

HAL có thể nhúng các item vào `_embedded`. Mỗi item thường có link `self` riêng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/orders/42"
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
~~~

Nếu client muốn mở item đầu tiên, có thể dùng JSONPath expression để lấy `href` của self link:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;

ParameterizedTypeReference<EntityModel<OrderDto>> orderType =
        new ParameterizedTypeReference<>() {};

EntityModel<OrderDto> order = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(orderType);
~~~

`follow(...)` chấp nhận cả relation name và JSONPath expression bắt đầu bằng `$`. JSONPath trong ví dụ chọn `self.href` của phần tử đầu tiên trong `_embedded.orders`; hop kế tiếp gửi request tới URI đó.

JSONPath hữu ích khi cần truy cập một embedded item mà representation không công bố relation riêng cho từng item ở cấp collection. Tuy nhiên, biểu thức này phụ thuộc cấu trúc HAL của response. Nếu server có thể cung cấp link relation phù hợp hoặc client có thể xử lý `CollectionModel` rồi theo self link của item, những cách đó thường dễ bảo trì hơn khi cấu trúc embedded thay đổi.

## 8. Deserialize kết quả thành EntityModel hoặc CollectionModel

`Traverson` có thể trả về một object Java thay vì JSONPath value. Với item resource, dùng `EntityModel<T>` để giữ payload cùng các link:

Các ví dụ dùng DTO đơn hàng rút gọn sau:

~~~java
public record OrderDto(Long id, String status) {
}
~~~

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<EntityModel<OrderDto>> orderType =
        new ParameterizedTypeReference<>() {};

EntityModel<OrderDto> order = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(orderType);

OrderDto content = order.getContent();
var selfLink = order.getRequiredLink("self");
~~~

`ParameterizedTypeReference` giữ thông tin generic mà Java type erasure có thể làm mất. `EntityModel` hữu ích khi client cần cả dữ liệu đơn hàng lẫn link điều hướng tiếp theo.

Với collection, Spring HATEOAS cung cấp `TypeReferences.CollectionModelType`:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.core.TypeReferences;

var collectionType =
        new TypeReferences.CollectionModelType<EntityModel<OrderDto>>() {};

CollectionModel<EntityModel<OrderDto>> orders = traverson
        .follow("orders")
        .toObject(collectionType);

for (EntityModel<OrderDto> item : orders) {
    OrderDto order = item.getContent();
    var self = item.getRequiredLink("self");
}
~~~

Kiểu phần tử cần khớp với representation server trả về. Nếu server nhúng object thuần thay vì entity model có link riêng, kiểu phần tử có thể là `OrderDto` thay vì `EntityModel<OrderDto>`. Với collection rỗng, metadata kiểu generic vẫn quan trọng để converter biết kiểu phần tử cần deserialize.

## 9. Lấy link cuối cùng thay vì tải resource đích

Đôi khi client chỉ cần URI của link để tự quyết định khi nào gửi request. `asLink()` trả về link tìm được ở relation cuối trong chuỗi traversal:

~~~java
import java.net.URI;

import org.springframework.hateoas.Link;

Link nextPage = traverson
        .follow("orders")
        .follow("next")
        .asLink();

URI nextPageUri = URI.create(nextPage.getHref());
~~~

Nếu link cuối là URI template và muốn giữ nguyên template, dùng `asTemplatedLink()`:

~~~java
Link searchTemplate = traverson
        .follow("orders")
        .follow("search")
        .follow("byStatus")
        .asTemplatedLink();
~~~

Phân biệt các thao tác cuối:

| Phương thức | Kết quả |
| --- | --- |
| `asLink()` | Link cuối đã được mở rộng bằng template parameters đã cấu hình |
| `asTemplatedLink()` | Link cuối còn giữ URI template |
| `toObject(Class)` | Deserialize representation cuối thành kiểu chỉ định |
| `toObject(ParameterizedTypeReference)` | Deserialize kiểu generic |
| `toObject(JSONPath)` | Lấy giá trị từ representation cuối bằng JSONPath |
| `toEntity(Class)` | Trả `ResponseEntity` cùng body đã deserialize |

`asLink()` hữu ích khi cần lưu hoặc chuyển tiếp URI đích. `toObject(...)` phù hợp khi cần tải nội dung resource cuối cùng.

## 10. Duyệt trang tiếp theo và trang trước

Collection có phân trang thường công bố `first`, `prev`, `self`, `next` và `last`. Client không cần tự tăng `page` hoặc tự tạo query string:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.core.TypeReferences;

var nextPage = traverson
        .follow("orders")
        .follow("next")
        .toObject(new TypeReferences.CollectionModelType<EntityModel<OrderDto>>() {});
~~~

Nếu muốn lấy link trang kế tiếp trước, dùng:

~~~java
Link next = traverson
        .follow("orders")
        .follow("next")
        .asLink();
~~~

Sau đó có thể tiếp tục theo URI mà link trả về bằng một `Traverson` traversal mới hoặc dùng client HTTP phù hợp. Trong luồng điều hướng thông thường, hãy giữ resource hiện tại và gọi `follow("next")` từ representation đó.

Không giả định mọi trang đều có `next`. Trang cuối thường không có relation này. Hãy kiểm tra link tùy chọn trước khi yêu cầu bước tiếp theo. Tương tự, trang đầu có thể không có `prev`.

## 11. Tìm link tùy chọn và xử lý trường hợp thiếu relation

Không phải link nào cũng xuất hiện trong mọi trạng thái. Ví dụ:

- `next` không xuất hiện ở trang cuối.
- `approve` chỉ xuất hiện khi đơn hàng có thể duyệt.
- `edit` có thể không xuất hiện với người dùng chỉ có quyền đọc.
- `search` có thể không được cung cấp bởi một API collection cụ thể.

Nếu dùng `Traverson` để theo một relation bắt buộc nhưng relation không tồn tại, traversal sẽ không thể tiếp tục. Khi muốn xử lý link tùy chọn, có thể dùng `LinkDiscoverer` để kiểm tra trước:

~~~java
import java.util.Optional;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;

Optional<Link> next = discoverer.findLinkWithRel("next", representation);

if (next.isPresent()) {
    URI nextUri = URI.create(next.get().getHref());
    // Gửi request tiếp theo bằng HTTP client của ứng dụng.
}
~~~

Với `RepresentationModel` đã deserialize, có thể dùng API của model:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

if (page.hasLink(IanaLinkRelations.NEXT)) {
    Link next = page.getRequiredLink(IanaLinkRelations.NEXT);
    // Điều hướng đến next.getHref().
}
~~~

Chỉ dùng `getRequiredLink(...)` khi relation là một phần bắt buộc của hợp đồng tại bước đó. Với relation phụ thuộc trạng thái, hãy dùng API trả `Optional` hoặc kiểm tra `hasLink(...)`.

## 12. Dùng LinkDiscoverer khi đã có JSON representation

`LinkDiscoverer` tìm link theo relation trong representation. Với HAL, Spring HATEOAS cung cấp `HalLinkDiscoverer`:

~~~java
import java.net.URI;
import java.util.Optional;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

String representation = """
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
""";

LinkDiscoverer discoverer = new HalLinkDiscoverer();

Optional<Link> ordersLink =
        discoverer.findLinkWithRel("orders", representation);

URI ordersUri = ordersLink
        .map(Link::getHref)
        .map(URI::create)
        .orElseThrow();
~~~

`findLinkWithRel(...)` trả `Optional<Link>`. Nếu muốn lấy tất cả link có cùng relation, dùng `findLinksWithRel(...)`. Nếu hợp đồng yêu cầu link phải tồn tại, có thể dùng `findRequiredLinkWithRel(...)`.

`LinkDiscoverer` chỉ tìm link; nó không gửi HTTP request và không thực hiện toàn bộ chuỗi traversal. Dùng `Traverson` khi muốn đi qua nhiều resource, dùng `LinkDiscoverer` khi cần tách bước tìm link khỏi bước gọi HTTP.

## 13. Tìm link nằm trong embedded resource

Mặc định, việc tìm link trong HAL thường tập trung vào các link ở cấp representation hiện tại. Nếu cần tìm link nằm bên trong `_embedded`, `HalLinkDiscoverer` cung cấp `inspectEmbeddeds()`:

~~~java
import java.util.Optional;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

LinkDiscoverer embeddedDiscoverer =
        new HalLinkDiscoverer().inspectEmbeddeds();

Optional<Link> embeddedSelf =
        embeddedDiscoverer.findLinkWithRel("self", representation);
~~~

Khi nhiều embedded item có cùng relation `self`, `findLinkWithRel(...)` chỉ trả một link đầu tiên tìm thấy. Nếu cần xử lý tất cả item, dùng `findLinksWithRel(...)` hoặc deserialize collection thành `CollectionModel` để duyệt từng phần tử.

Không dùng một link `self` bất kỳ thay cho link của item mong muốn. Cần xác định đúng embedded item trước khi lấy link của nó.

## 14. Custom relation và CURIE trong client

API có thể công bố custom relation qua CURIE:

~~~json
{
  "_links": {
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approve": {
      "href": "https://api.example.com/api/orders/42/approval"
    }
  }
}
~~~

Client cần nhận diện đúng relation key được biểu diễn trong HAL, ví dụ `acme:approve`. CURIE cho biết cách mở rộng prefix thành URI relation đầy đủ. Nếu client sử dụng custom relation, cần thống nhất vocabulary và cách xử lý namespace với server.

Ví dụ tìm link action:

~~~java
import org.springframework.hateoas.Link;

Link approve = discoverer
        .findLinkWithRel("acme:approve", representation)
        .orElseThrow();
~~~

Custom relation không tự nói HTTP method hoặc payload. Nếu action cần request body, client phải đọc affordance hoặc hợp đồng media type tương ứng trước khi gửi request. Không suy luận rằng relation `approve` luôn có nghĩa là POST nếu API chưa công bố điều đó.

## 15. Gửi headers trong quá trình traversal

Một số API yêu cầu thông tin xác thực, tenant, locale hoặc correlation ID. `Traverson.TraversalBuilder.withHeaders(...)` cho phép gắn HTTP headers vào các request của traversal:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.hateoas.EntityModel;

HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);
headers.set("X-Tenant", tenantId);
headers.set("Accept-Language", "vi");

EntityModel<OrderDto> order = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .withHeaders(headers)
        .toObject(orderType);
~~~

Headers được dùng cho các request của traversal. Không ghi token vào URI, query parameter hoặc log. Nếu token hết hạn giữa các hop, client cần xử lý lỗi xác thực và làm mới token theo cơ chế của ứng dụng.

## 16. Tích hợp WebClient cho client reactive

Nếu ứng dụng dùng `WebClient` để gọi API, Spring HATEOAS cung cấp `HypermediaWebClientConfigurer` để đăng ký encoder và decoder hỗ trợ media type hypermedia:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaWebClientConfigurer;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class HypermediaClientConfiguration {

    @Bean
    WebClient.Builder hypermediaWebClient(
            HypermediaWebClientConfigurer configurer
    ) {
        return configurer.registerHypermediaTypes(WebClient.builder());
    }
}
~~~

Sau đó, client có thể dùng `WebClient` đã cấu hình để tải representation theo link được phát hiện:

Giả sử `webClient` là instance đã được build từ builder ở phần trên và `orderLink` là link đã được tìm từ representation:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import reactor.core.publisher.Mono;

Mono<EntityModel<OrderDto>> order = webClient.get()
        .uri(orderLink.getHref())
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .bodyToMono(new ParameterizedTypeReference<EntityModel<OrderDto>>() {});
~~~

`WebClient` cung cấp cách gọi reactive và kiểm soát luồng request. `Traverson` là API chuyên dụng để duyệt chuỗi relation theo cách đồng bộ. Khi dùng `WebClient`, ứng dụng có thể tự tổ chức chuỗi request bằng các link đã tìm được từ representation.

## 17. Thay HTTP client và cấu hình request

`Traverson` dùng `RestOperations` để gửi request. Có thể thay implementation mặc định bằng cách gọi `setRestOperations(...)`:

~~~java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

RestOperations operations = new RestTemplate();

Traverson traverson = new Traverson(
        URI.create("https://api.example.com/api/"),
        MediaTypes.HAL_JSON
);

traverson.setRestOperations(operations);
~~~

Điều này hữu ích khi ứng dụng cần dùng HTTP client đã cấu hình timeout, proxy, interceptors, tracing hoặc authentication. Hãy bảo đảm client vẫn có message converter phù hợp với media type mà API trả về.

Traversal có thể tạo nhiều request liên tiếp. Cần cấu hình timeout và retry có kiểm soát; không retry tự động mọi lỗi vì một số thao tác hoặc endpoint có thể không an toàn khi gửi lặp.

## 18. Kiểm thử client traversal

Có thể kiểm tra riêng khả năng tìm relation từ representation HAL bằng unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

class LinkDiscovererTest {

    @Test
    void findsOrdersLinkByRelation() {
        String json = """
        {
          "_links": {
            "orders": {
              "href": "https://api.example.com/api/orders"
            }
          }
        }
        """;

        LinkDiscoverer discoverer = new HalLinkDiscoverer();

        Link link = discoverer
                .findRequiredLinkWithRel("orders", json);

        assertThat(link.getHref())
                .isEqualTo("https://api.example.com/api/orders");
    }
}
~~~

Kiểm thử traversal end-to-end nên xác nhận client bắt đầu từ entry point, theo đúng relation và nhận resource mong muốn. Ví dụ với Spring Boot test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ClientTraversalIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void followsOrdersRelationFromApiRoot() {
        URI root = URI.create("http://localhost:" + port + "/");

        Traverson traverson = new Traverson(
                root,
                MediaTypes.HAL_JSON
        );

        Link orders = traverson
                .follow("orders")
                .asLink();

        assertThat(orders.getHref()).endsWith("/orders");
    }
}
~~~

Ví dụ giả định ứng dụng test có API root công bố relation `orders`. Test cần Spring HATEOAS/HAL support và controller hoặc Spring Data REST endpoint tương ứng. Khi kiểm thử traversal nhiều hop, chuẩn bị dữ liệu để từng relation trong chuỗi đều tồn tại.

Các tình huống nên kiểm thử:

- Entry point trả đúng media type và link relation cần thiết.
- Relation bắt buộc có mặt ở đúng resource.
- URI template được mở rộng bằng đúng tham số.
- Embedded item được chọn đúng trước khi theo self link.
- `next` không tồn tại ở trang cuối và client xử lý trường hợp đó.
- Custom relation/CURIE được phát hiện theo tên relation đã công bố.
- Headers xác thực và tenant được gửi trong các request.
- API trả 401, 403, 404 hoặc 5xx thì client xử lý theo chính sách phù hợp.

## 19. Những lỗi thường gặp

**Ghép URI từ tên resource.** Client tự nối `/orders/{id}` sẽ phụ thuộc path. Hãy lấy link theo relation từ representation.

**Nhầm relation với target URI.** Relation mô tả ý nghĩa, còn `href` là địa chỉ. Không dùng relation để dựng URL.

**Khởi tạo Traverson bằng media type không khớp.** Server trả HAL nhưng client cấu hình media type khác có thể không tìm được link. Dùng `MediaTypes.HAL_JSON` khi API công bố HAL.

**Quên mở rộng URI template.** Link có `templated: true` cần giá trị biến. Dùng `withTemplateParameters(...)` hoặc `Hop.withParameter(...)`.

**Áp dụng một map cho mọi hop dù giá trị khác nhau.** Khi các bước cần tham số riêng, dùng `Hop` cho từng relation.

**Dùng JSONPath cho mọi bước.** JSONPath hữu ích với embedded item nhưng phụ thuộc cấu trúc representation. Ưu tiên relation có ý nghĩa khi API công bố được.

**Lấy nhầm self link trong embedded collection.** Nhiều item có cùng relation `self`. Xác định đúng item trước khi theo link.

**Giả định link tùy chọn luôn tồn tại.** `next`, `approve` hoặc `edit` có thể vắng mặt. Kiểm tra link trước khi sử dụng.

**Dùng LinkDiscoverer như HTTP client.** `LinkDiscoverer` chỉ tìm link. Dùng `Traverson`, `RestOperations` hoặc `WebClient` để gửi request.

**Không truyền authentication headers qua traversal.** Nếu API yêu cầu token hoặc tenant, dùng `withHeaders(...)` và cấu hình HTTP client phù hợp.

**Coi việc có link là được cấp quyền.** Server vẫn phải kiểm tra authentication, authorization và trạng thái nghiệp vụ ở mỗi request.

**Không kiểm soát số request.** Mỗi hop có thể phát sinh một request. Hạn chế chuỗi quá dài và cấu hình timeout phù hợp.

## 20. Ghi nhớ

Điều hướng theo relation giúp client khám phá API qua ngữ nghĩa của link thay vì tự tạo URI. Client bắt đầu từ một entry point đã biết, sau đó dùng `Traverson.follow(...)` để đi qua relation. `withTemplateParameters(...)` hoặc `Hop.withParameter(...)` mở rộng URI template; `toObject(...)` deserialize resource cuối; `asLink()` lấy link cuối để client tự quyết định bước tiếp theo.

Khi cần truy cập embedded item, có thể dùng JSONPath expression để lấy self link hoặc deserialize collection thành `CollectionModel`. `LinkDiscoverer` tìm link theo relation trong JSON representation, còn `HalLinkDiscoverer.inspectEmbeddeds()` có thể tìm sâu trong `_embedded`. Với ứng dụng reactive, cấu hình `WebClient` bằng `HypermediaWebClientConfigurer` để hỗ trợ media type hypermedia.

Client nên xử lý relation tùy chọn, custom relation, headers xác thực, lỗi HTTP và chi phí nhiều request trong traversal. Kiểm thử cả link discovery lẫn chuỗi điều hướng để bảo đảm client theo đúng hợp đồng hypermedia khi URI của server thay đổi.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Client-side Support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client-side)
- [Spring HATEOAS Reference – Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson)
- [Traverson API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Traverson.TraversalBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.TraversalBuilder.html)
- [Hop API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Hop.html)
- [LinkDiscoverer API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/LinkDiscoverer.html)
- [HalLinkDiscoverer API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalLinkDiscoverer.html)
- [TypeReferences API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/TypeReferences.html)
