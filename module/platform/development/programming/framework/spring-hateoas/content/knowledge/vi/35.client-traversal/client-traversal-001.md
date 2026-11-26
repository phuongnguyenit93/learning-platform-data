# Traverson là gì

## Mục tiêu

Một client HATEOAS bắt đầu từ URI bootstrap, đọc representation rồi tìm link theo relation để đi tới tài nguyên tiếp theo. Nếu client tự ghép URL từ tên resource hoặc cấu trúc path, nó vẫn phụ thuộc vào cách server triển khai. Spring HATEOAS cung cấp Traverson để thực hiện quá trình khám phá và điều hướng này ở phía client.

Traverson là API client-side giúp theo các link relation trong hypermedia representation. Client cung cấp URI ban đầu và media type cần nhận, sau đó khai báo chuỗi relation cần đi theo. Traverson gửi request, phát hiện link trong từng response, theo href mà server trả về và chuyển representation cuối thành kiểu Java hoặc trích xuất dữ liệu bằng JSONPath.

Sau bài học, bạn có thể:

- Giải thích vai trò của Traverson trong một HATEOAS client.
- Khởi tạo Traverson với URI bootstrap và HAL JSON.
- Điều hướng qua một hoặc nhiều link relation.
- Chuyển representation cuối thành object có kiểu hoặc đọc bằng JSONPath.
- Mở rộng URI template bằng tham số tìm kiếm.
- Tùy chỉnh header cho toàn traversal hoặc từng hop.
- Cấu hình RestOperations và LinkDiscoverer khi cần.
- Kiểm thử quá trình client khám phá API.

## Traverson giải quyết vấn đề gì?

Giả sử API có root representation tại /api. Root chứa relation orders trỏ tới collection đơn hàng. Collection chứa embedded items, mỗi item có self link. Client muốn tải đơn hàng đầu tiên.

Nếu client tự ghép URL, nó có thể viết cứng /api/orders rồi ghép ID vào path. Cách làm này phụ thuộc vào cấu trúc URI và quy ước đặt tên của server.

Với Traverson, client mô tả đường đi theo hypermedia:

1. Bắt đầu từ URI root đã được cấu hình.
2. Tìm relation orders trong root representation.
3. Gọi href của link orders.
4. Từ collection response, tìm self link của item cần lấy.
5. Gọi link đó và chuyển response thành kiểu dữ liệu mong muốn.

Server có thể đổi đường dẫn collection hoặc item mà không cần client tự tính lại URL, miễn là server giữ các relation và semantics cần thiết trong representation.

Traverson thuộc package org.springframework.hateoas.client. Đây là công cụ phía client, không phải link builder phía server. Nó không tạo relation, không thay thế controller hoặc assembler, và không quyết định nghiệp vụ nào người dùng được phép thực hiện.

## Khởi tạo Traverson

Constructor nhận URI bootstrap và một hoặc nhiều media type mà client muốn sử dụng. Với HAL JSON:

~~~java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

Traverson traverson = new Traverson(
        URI.create("https://api.example.com/api/"),
        MediaTypes.HAL_JSON);
~~~

Media type được truyền vào constructor được dùng để cấu hình header Accept khi Traverson gọi server. Server cần hỗ trợ media type đó và trả representation có cấu trúc link mà client có thể phát hiện.

URI truyền vào là điểm bắt đầu của traversal. Client vẫn cần biết URI bootstrap này từ cấu hình môi trường, tài liệu tích hợp hoặc một cơ chế discovery ban đầu. Sau bước đó, client nên theo relation và href được công bố thay vì tự ghép các URI con.

Traverson mặc định dùng HAL link discoverer và RestTemplate với các message converters tương ứng media type được cấu hình. Với HAL JSON, LinkDiscoverer đọc cấu trúc _links để tìm href theo relation.

## Theo một relation

Phương thức follow(...) bắt đầu một traversal. Kết quả là TraversalBuilder; gọi toObject(...) để thực hiện traversal và chuyển representation cuối thành object:

~~~java
import java.net.URI;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;
import org.springframework.core.ParameterizedTypeReference;

record OrderSummary(String id, String status) {
}

Traverson traverson = new Traverson(
        URI.create("https://api.example.com/api/"),
        MediaTypes.HAL_JSON);

EntityModel<OrderSummary> order = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(new ParameterizedTypeReference<EntityModel<OrderSummary>>() {});
~~~

Ví dụ dùng JSONPath ở hop thứ hai để chọn self link của item đầu tiên trong embedded collection. Biểu thức JSONPath bắt đầu bằng ký tự $; Traverson hiểu chuỗi đó là đường dẫn trong representation thay vì tên relation thông thường.

Khi relation orders trỏ tới collection, client có thể deserialize toàn bộ collection:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

ParameterizedTypeReference<CollectionModel<EntityModel<OrderSummary>>> orderCollectionType =
        new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<OrderSummary>> orders = traverson
        .follow("orders")
        .toObject(orderCollectionType);
~~~

ParameterizedTypeReference giữ generic type ở runtime. Nếu chỉ truyền CollectionModel.class, thông tin kiểu phần tử EntityModel<OrderSummary> sẽ bị mất do Java type erasure.

## Theo nhiều relation liên tiếp

Có thể truyền nhiều relation vào một lần follow:

~~~java
String actorName = traverson
        .follow("movies", "movie", "actor")
        .toObject("$.name");
~~~

Traverson đi theo các relation lần lượt. Mỗi bước cần đọc representation hiện tại để tìm href cho bước tiếp theo; vì vậy một chuỗi relation dài tạo ra nhiều request GET tuần tự, phụ thuộc vào response trước đó.

Có thể viết thành nhiều lời gọi follow để dễ đọc hoặc cấu hình riêng từng bước:

~~~java
EntityModel<OrderSummary> order = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(new ParameterizedTypeReference<EntityModel<OrderSummary>>() {});
~~~

Thứ tự relation là thứ tự điều hướng, không phải danh sách endpoint để gọi độc lập. Nếu relation không tồn tại trong representation hiện tại, traversal không thể tiếp tục và client nhận lỗi từ quá trình tìm link hoặc request tương ứng.

## Dùng JSONPath để chọn link trong representation

Ngoài relation name, Traverson cho phép dùng JSONPath expression làm một hop. Cách này hữu ích khi link cần chọn nằm trong embedded resource hoặc một phần tử của mảng.

Ví dụ HAL collection:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "status": "PAID",
        "_links": {
          "self": {
            "href": "/api/orders/order-42"
          }
        }
      }
    ]
  }
}
~~~

Client có thể đi tới self link của phần tử đầu tiên bằng:

~~~java
EntityModel<OrderSummary> firstOrder = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(new ParameterizedTypeReference<EntityModel<OrderSummary>>() {});
~~~

JSONPath giúp chọn link trong một representation cụ thể. Tuy nhiên, nếu API có relation ổn định cho hành động hoặc tài nguyên mà client cần, nên ưu tiên relation đó. JSONPath gắn client chặt hơn với cấu trúc JSON như tên embedded key, vị trí mảng và cấu trúc _links.

## Đọc kết quả bằng toObject và toEntity

TraversalBuilder cung cấp nhiều cách đọc representation cuối:

| Phương thức | Kết quả | Khi dùng |
|---|---|---|
| toObject(Class<T>) | Object của kiểu được chỉ định. | DTO hoặc kiểu đơn giản không cần generic lồng nhau. |
| toObject(ParameterizedTypeReference<T>) | Object giữ được generic type. | EntityModel<T>, CollectionModel<EntityModel<T>> hoặc kiểu generic khác. |
| toObject(String jsonPath) | Giá trị được trích xuất từ representation bằng JSONPath. | Chỉ cần một thuộc tính, chẳng hạn tên hoặc trạng thái. |
| toEntity(Class<T>) | ResponseEntity<T> chứa response cuối. | Cần đọc status và headers cùng body. |

Ví dụ chỉ lấy trạng thái:

~~~java
String status = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject("$.status");
~~~

Ví dụ lấy ResponseEntity:

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;

ResponseEntity<OrderSummary> response = traverson
        .follow("orders")
        .follow("$._embedded.orders[0]._links.self.href")
        .toEntity(OrderSummary.class);

HttpStatusCode statusCode = response.getStatusCode();
OrderSummary body = response.getBody();
~~~

toEntity(Class<T>) trả response entity của request cuối trong traversal. Các request trung gian vẫn được thực hiện để phát hiện relation và đi tiếp.

Nếu chỉ muốn lấy link cuối mà không tải representation của tài nguyên đích, dùng asLink() hoặc asTemplatedLink() trên TraversalBuilder. asLink() trả link đã được mở rộng bằng các template parameters đã cung cấp; asTemplatedLink() giữ URI template.

## Mở rộng URI template

HAL link có thể chứa URI template để công bố các query parameters được hỗ trợ. Ví dụ root representation có search link:

~~~json
{
  "_links": {
    "search": {
      "href": "/api/orders{?status,customerName,page,size}",
      "templated": true
    }
  }
}
~~~

Client không cần tự ghép query string. Nó truyền giá trị template cho TraversalBuilder:

~~~java
import java.util.Map;

Map<String, Object> parameters = Map.of(
        "status", "PAID",
        "customerName", "An",
        "page", 0,
        "size", 20);

CollectionModel<EntityModel<OrderSummary>> paidOrders = traverson
        .follow("search")
        .withTemplateParameters(parameters)
        .toObject(orderCollectionType);
~~~

Traverson dùng các tham số này để mở rộng những link dạng template được phát hiện trong traversal. Khi truyền map vào TraversalBuilder, cùng map tham số được áp dụng cho các templated links gặp trong các hop của traversal.

Nếu chỉ một hop cần tham số riêng, dùng Hop:

~~~java
import static org.springframework.hateoas.client.Hop.rel;

EntityModel<OrderSummary> order = traverson
        .follow(rel("orders").withParameter("projection", "compact"))
        .follow("$._embedded.orders[0]._links.self.href")
        .toObject(new ParameterizedTypeReference<EntityModel<OrderSummary>>() {});
~~~

withParameter(...) trả về một Hop mới có thể nối tiếp thêm tham số. Có thể dùng withParameters(Map) khi đã có sẵn một map. Cách này hữu ích khi các URI template ở các bước khác nhau dùng những biến khác nhau.

Không truyền tham số ngoài những biến mà link công bố. Server vẫn phải validate giá trị, giới hạn page size, allowlist sort và áp dụng quyền khi xử lý request.

## Gửi header cho traversal

API có thể yêu cầu header xác thực hoặc header ngữ cảnh. withHeaders(...) trên TraversalBuilder áp dụng HttpHeaders cho các request của traversal:

~~~java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

CollectionModel<EntityModel<OrderSummary>> orders = traverson
        .follow("orders")
        .withHeaders(headers)
        .toObject(orderCollectionType);
~~~

Nếu chỉ một hop cần header riêng, Hop hỗ trợ withHeaders(...) và header(name, value):

~~~java
EntityModel<OrderSummary> order = traverson
        .follow(rel("orders").header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + accessToken))
        .toObject(new ParameterizedTypeReference<EntityModel<OrderSummary>>() {});
~~~

Không ghi token vào log hoặc đưa token vào URI template. Dùng HTTPS cho request mang thông tin xác thực và để credential được quản lý bởi cấu hình an toàn của ứng dụng.

## Tùy chỉnh RestOperations

Traverson có thể dùng RestOperations do ứng dụng cung cấp. Điều này hữu ích khi cần timeout, connection pool, proxy, interceptor, tracing hoặc cơ chế xác thực riêng:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;
import org.springframework.hateoas.config.HypermediaRestTemplateConfigurer;
import org.springframework.web.client.RestTemplate;

@Configuration
class ClientHttpConfiguration {

@Bean
RestTemplate hypermediaRestTemplate(
        HypermediaRestTemplateConfigurer configurer) {
    return configurer.registerHypermediaTypes(new RestTemplate());
}

    @Bean
    Traverson orderApiTraverson(RestTemplate restTemplate) {
        return new Traverson(
                URI.create("https://api.example.com/api/"),
                MediaTypes.HAL_JSON)
                .setRestOperations(restTemplate);
    }
}

~~~

Khi tự tạo RestTemplate, cần đăng ký hypermedia message converters để mapper hiểu HAL links và embedded resources. HypermediaRestTemplateConfigurer của Spring HATEOAS thực hiện việc đó. Nếu dùng RestTemplate tự cấu hình mà thiếu converter, response có thể không deserialize được thành representation model hoặc Traverson không đọc được links.

Trong Spring Boot, có thể đăng ký RestTemplateCustomizer để áp dụng HypermediaRestTemplateConfigurer cho RestTemplate được tạo từ RestTemplateBuilder. Traverson mặc định dùng RestTemplate nếu không được cung cấp RestOperations khác.

## Tùy chỉnh LinkDiscoverer

LinkDiscoverer chịu trách nhiệm tìm link theo relation trong representation. Traverson mặc định đăng ký HalLinkDiscoverer. Nếu dùng media type khác, cần LinkDiscoverer tương ứng để client có thể tìm link trong định dạng đó.

Có thể thay danh sách discoverer bằng setLinkDiscoverers(...). Khi truyền null, Traverson áp dụng lại discoverer mặc định. Với media type tùy chỉnh, cần đăng ký cả message converter/mapper và LinkDiscoverer hiểu cấu trúc relation của media type đó.

Nếu client chỉ giao tiếp với HAL JSON, thường không cần cấu hình LinkDiscoverer thủ công.

## Traverson và chi phí request

Traverson làm cho client ít phụ thuộc vào URI cụ thể, nhưng mỗi hop cần đọc một representation để tìm link tiếp theo. Một traversal dài có thể tạo nhiều request mạng tuần tự:

~~~text
GET /api
  └── rel orders
      GET /api/orders
        └── chọn self link của item
            GET /api/orders/order-42
~~~

Vì mỗi bước phụ thuộc response trước, các hop không thể được gửi song song một cách tùy ý. Hãy giữ traversal ở mức cần thiết và ưu tiên representation có relation phù hợp với mục tiêu client.

Nếu chỉ cần URI của link cuối, dùng asLink() để tránh gọi thêm request tới tài nguyên đích. Nếu cần dữ liệu, dùng toObject() hoặc toEntity(). Không dùng JSONPath để duyệt cấu trúc sâu nếu server có thể công bố relation rõ nghĩa cho tài nguyên đó.

Traverson thực hiện HTTP client call đồng bộ qua RestOperations. Trong ứng dụng reactive cần tránh chặn event-loop; có thể dùng WebClient được cấu hình hypermedia thay vì gọi Traverson trực tiếp trên luồng reactive.

## Xử lý lỗi và bảo mật

Traversal có thể thất bại khi:

- URI bootstrap không truy cập được hoặc trả status lỗi.
- Representation không có relation được yêu cầu.
- Link chứa URI template nhưng client thiếu tham số bắt buộc.
- Href trỏ tới URI sai hoặc tài nguyên đã bị xóa.
- Media type response không tương thích với converter/discoverer.
- Request bị từ chối do authentication hoặc authorization.

Hãy xử lý lỗi HTTP từ RestOperations, lỗi không tìm thấy relation và lỗi deserialize như các tình huống khác nhau. Log relation và URI đã chuẩn hóa khi cần chẩn đoán, nhưng không log Authorization header hoặc dữ liệu nhạy cảm trong query parameters.

Traverson không thay thế authorization. Việc client nhìn thấy link không đảm bảo request tiếp theo sẽ được phép; server phải kiểm tra quyền trên mỗi request. Client cũng không nên tin URI do response cung cấp nếu API có thể trả link tới host ngoài dự kiến. Với hệ thống có ranh giới tin cậy, áp dụng chính sách outbound destination phù hợp để tránh gọi URI ngoài miền được phép.

## Kiểm thử client traversal

Kiểm thử nên xác minh client bắt đầu từ root, tìm relation và gọi href được server cung cấp. Với client dùng RestTemplate, có thể cấu hình hypermedia converter rồi dùng mock HTTP server để mô phỏng từng response.

Các điểm cần kiểm tra:

- Request đầu tiên đi tới đúng URI bootstrap.
- Header Accept chứa media type mà Traverson được cấu hình.
- Request tiếp theo dùng href tìm được từ relation, không phải URL client tự ghép.
- Mỗi hop nhận đúng response và relation kế tiếp được phát hiện.
- URI template được mở rộng với giá trị đã truyền.
- Header xác thực được gửi theo chính sách của từng hop.
- Generic response được deserialize đúng kiểu.
- JSONPath expression chọn đúng link hoặc property.
- Thiếu relation, status lỗi và media type không hỗ trợ được xử lý rõ ràng.

Nên có một integration test bắt đầu từ API root và đi tới một item resource. Test như vậy bảo vệ cả hợp đồng links của server và cách client sử dụng relation. Nếu server đổi path collection nhưng vẫn giữ relation orders, test traversal vẫn có thể thành công mà không cần thay URI trong client.

## Những lỗi thường gặp

- **Dùng Traverson như link builder:** Traverson là client-side traversal API; server dùng WebMvcLinkBuilder hoặc WebFluxLinkBuilder để tạo links.
- **Truyền URI của collection thay vì bootstrap URI:** truyền entry point ổn định rồi theo relation từ response.
- **Dùng tên path thay cho relation:** follow("orders") tìm relation orders trong representation hiện tại, không tự tạo path /orders.
- **Quên media type:** constructor cần media type để gửi Accept và chọn converter/discoverer phù hợp.
- **Dùng Class cho generic collection:** dùng ParameterizedTypeReference hoặc TypeReferences để giữ kiểu phần tử.
- **Dùng JSONPath cho mọi hop:** ưu tiên relation ngữ nghĩa; JSONPath gắn client với cấu trúc JSON cụ thể.
- **Truyền template parameters sai hop:** withTemplateParameters áp dụng map cho các templated links trong traversal; dùng Hop khi từng bước cần tham số riêng.
- **Tự tạo RestTemplate nhưng thiếu hypermedia converter:** đăng ký HypermediaRestTemplateConfigurer trước khi truyền RestOperations cho Traverson.
- **Tưởng một chuỗi relation chỉ tạo một request:** mỗi hop cần request để khám phá representation tiếp theo.
- **Coi link là quyền truy cập:** server vẫn phải kiểm tra authorization trên endpoint đích.
- **Dùng Traverson trên reactive event-loop:** Traverson đồng bộ; dùng WebClient cho luồng reactive.

## Quy trình sử dụng Traverson

1. Lấy URI bootstrap từ cấu hình client hoặc kênh discovery đáng tin cậy.
2. Khởi tạo Traverson với URI và media type mà server hỗ trợ.
3. Xác định relation hoặc JSONPath cần đi theo từ representation hiện tại.
4. Dùng follow(...) để mô tả các hop và Hop khi cần tham số/header riêng.
5. Mở rộng URI template bằng withTemplateParameters(...) hoặc tham số theo Hop.
6. Chọn toObject(), toEntity(), asLink() hoặc asTemplatedLink() tùy dữ liệu cần lấy.
7. Kiểm thử request, relation, href, headers, kiểu deserialize và các trường hợp lỗi.

Traverson giúp client sử dụng hypermedia như một bản đồ điều hướng do server công bố. Client chỉ cần biết entry point, relation cần tìm và kiểu dữ liệu muốn nhận; server giữ quyền quyết định URI thực tế. Khi kết hợp đúng media type, link discoverer, template parameters và HTTP configuration, client có thể đi theo API mà ít phụ thuộc vào cấu trúc URL nội bộ.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Client-side Support – Traverson: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson
- Spring HATEOAS API, Traverson: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html
- Spring HATEOAS API, Traverson.TraversalBuilder: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.TraversalBuilder.html
- Spring HATEOAS API, Hop: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Hop.html
- Spring HATEOAS Reference Documentation, Configuring RestTemplate instances: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.resttemplate
