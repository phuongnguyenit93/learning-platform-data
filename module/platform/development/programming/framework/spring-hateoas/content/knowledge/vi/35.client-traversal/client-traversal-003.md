# Bắt đầu từ API root

Trong một API theo HATEOAS, client cần một điểm vào ban đầu để bắt đầu khám phá tài nguyên. Điểm vào đó thường được gọi là **API root** hoặc **API entry point**. Client biết URI của root từ cấu hình, tài liệu tích hợp hoặc service discovery; sau request đầu tiên, client đọc các link relation trong representation để tìm collection, search resource, profile và các tài nguyên liên quan.

Với Spring HATEOAS, `Traverson` hỗ trợ quy trình này ở phía client. Client khởi tạo `Traverson` bằng URI của API root và media type mà API sử dụng, sau đó gọi `follow(...)` theo các relation được server công bố. Client không cần tự ghép các đường dẫn như `/orders`, `/orders/search` hoặc `/orders/{id}`. Server có thể thay đổi cấu trúc URI mà client vẫn tiếp tục hoạt động nếu các relation và ngữ nghĩa của chúng được giữ ổn định.

## API root là điểm bắt đầu của traversal

API root là tài nguyên đầu tiên mà client truy cập trong một API. Nó thường không chứa toàn bộ dữ liệu nghiệp vụ; thay vào đó, nó công bố các link để client khám phá phần còn lại của API.

Ví dụ API bán hàng có thể trả root representation dạng HAL:

```json
{
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
    "products": {
      "href": "https://api.example.com/api/products"
    },
    "profile": {
      "href": "https://api.example.com/api/profile"
    }
  }
}
```

Trong response này:

- `self` trỏ tới chính API root.
- `orders`, `customers` và `products` là các relation dẫn tới collection resource.
- `profile` dẫn tới tài liệu mô tả cấu trúc hoặc ngữ nghĩa của API.
- `href` cung cấp URI đích thực tế; client không cần tự suy ra đường dẫn từ tên relation.

Root representation có thể chứa thêm `search`, `documentation`, `health` hoặc các relation tùy theo API. Không có một bộ relation root bắt buộc cho mọi ứng dụng. Điều quan trọng là server công bố những khả năng thực sự hỗ trợ và client hiểu các relation mà workflow của nó cần.

### API root khác base URL như thế nào?

Base URL là địa chỉ gốc được client cấu hình, còn API root là tài nguyên được phục vụ tại điểm vào đó. Trong nhiều ứng dụng, hai khái niệm trùng nhau, ví dụ `https://api.example.com/api`. Nhưng chúng không nhất thiết phải giống nhau: reverse proxy, gateway hoặc phiên bản API có thể làm URI public khác với địa chỉ nội bộ của service.

Client vẫn cần biết ít nhất một URI ban đầu. HATEOAS không loại bỏ hoàn toàn cấu hình; nó giảm số URI nghiệp vụ mà client phải biết trước. Sau khi nhận API root, client nên theo các link relation thay vì tự ghép URL từ convention nội bộ.

## Root resource trong Spring HATEOAS

Với Spring MVC, có thể tạo root endpoint trả `RepresentationModel` và thêm link tới các collection controller. `WebMvcLinkBuilder` lấy URI từ mapping controller, giúp tránh hard-code path.

```java
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api")
public class ApiRootController {

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public RepresentationModel<?> root() {
        RepresentationModel<?> model = new RepresentationModel<>();

        model.add(linkTo(methodOn(ApiRootController.class).root()).withSelfRel());
        model.add(linkTo(OrderController.class).withRel("orders"));
        model.add(linkTo(CustomerController.class).withRel("customers"));
        model.add(linkTo(ProductController.class).withRel("products"));

        return model;
    }
}
```

Giả sử các controller tương ứng được ánh xạ dưới `/api/orders`, `/api/customers` và `/api/products`. `linkTo(OrderController.class)` tạo link tới mapping của controller; relation `orders` đặt tên ý nghĩa mà client sẽ tìm. Khi đổi mapping controller, link root được tạo lại từ mapping mới mà không cần sửa client.

Nếu dùng Spring Data REST, root resource thường được framework tạo từ các repository đã export. Có thể tùy chỉnh collection relation và path bằng `@RepositoryRestResource`:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        path = "orders",
        collectionResourceRel = "orders"
)
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
```

Khi repository được export, root resource có thể công bố link `orders` tới collection. Nếu cần endpoint root tổng hợp riêng hoặc bổ sung link tới dịch vụ khác, có thể dùng cấu hình Spring Data REST hoặc một root controller phù hợp với kiến trúc ứng dụng.

Không tạo link tới endpoint chưa được đăng ký hoặc không có quyền truy cập. Một relation xuất hiện trong root là lời công bố rằng client có thể điều hướng tới khả năng đó; endpoint đích vẫn cần xác thực và phân quyền cho từng request.

## Hợp đồng root nên ổn định

Root là nơi client bắt đầu, nên các relation quan trọng cần được xem là một phần của hợp đồng API. Một số nguyên tắc thiết kế:

1. **Giữ relation có ý nghĩa ổn định.** `orders` nên luôn chỉ collection đơn hàng, kể cả khi đường dẫn đích thay đổi.
2. **Dùng relation IANA khi phù hợp.** Các relation chuẩn như `self`, `profile` hoặc `search` có ngữ nghĩa đã được định nghĩa. Relation riêng của domain nên dùng extension relation phù hợp.
3. **Công bố đúng khả năng.** Nếu một tính năng không được bật hoặc người dùng hiện tại không thể sử dụng, hãy quyết định rõ có nên lược link khỏi representation hay không.
4. **Giữ URI root có thể cấu hình.** Client nên nhận root URI từ cấu hình môi trường hoặc service discovery, không gắn cứng trong nhiều class.
5. **Không buộc client phụ thuộc thứ tự link.** Client tìm theo relation, không dựa vào vị trí property trong JSON.
6. **Cung cấp media type và tài liệu rõ ràng.** Client phải biết định dạng representation để chọn parser và hiểu profile nếu API sử dụng.

Tên relation là định danh, không phải nhãn giao diện. Client có thể hiển thị chữ “Đơn hàng” cho người dùng nhưng vẫn tìm link theo relation `orders`.

## Khởi tạo Traverson từ API root

`Traverson` nằm trong package `org.springframework.hateoas.client`. Constructor nhận URI ban đầu và danh sách media type mà client muốn nhận. Với HAL JSON:

```java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

URI apiRoot = URI.create("https://api.example.com/api");

Traverson traverson = new Traverson(
        apiRoot,
        MediaTypes.HAL_JSON
);
```

`MediaTypes.HAL_JSON` cho biết client mong nhận `application/hal+json`. `Traverson` dùng media type này làm `Accept` khi tải các representation trong quá trình traversal và dùng HAL link discoverer mặc định để tìm relation trong `_links`.

Địa chỉ `apiRoot` là cấu hình môi trường, ví dụ có thể lấy từ `application.yml`:

```yaml
client:
  order-api:
    root: https://api.example.com/api
```

Inject cấu hình vào client service:

```java
import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client.order-api")
public record OrderApiProperties(URI root) {}
```

Đăng ký record bằng `@ConfigurationPropertiesScan` trên class ứng dụng hoặc `@EnableConfigurationProperties(OrderApiProperties.class)`. Sau đó tạo `Traverson` từ `properties.root()`. Cách này giúp mỗi môi trường có thể trỏ tới API root khác nhau mà không thay đổi code traversal.

## Theo link relation đầu tiên từ root

Khi đã có `Traverson`, client có thể theo relation `orders` được root công bố:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

ParameterizedTypeReference<PagedModel<EntityModel<OrderSummary>>> orderPageType =
        new ParameterizedTypeReference<>() {};

PagedModel<EntityModel<OrderSummary>> orders = traverson
        .follow("orders")
        .toObject(orderPageType);
```

`follow("orders")` yêu cầu `Traverson` tải root, tìm link có relation `orders`, rồi gửi request tới `href` đó. `toObject(...)` đọc representation cuối thành kiểu Java được chỉ định. Dùng `ParameterizedTypeReference` khi kiểu đích có generic lồng nhau như `PagedModel<EntityModel<OrderSummary>>`.

Nếu API trả collection không phân trang, kiểu đích có thể là `CollectionModel<EntityModel<OrderSummary>>`. Hãy dùng đúng kiểu response thực tế của endpoint; không giả định mọi collection đều là `PagedModel`.

### Theo nhiều relation liên tiếp

Root thường chỉ dẫn tới collection. Collection có thể cung cấp link `search`, và search resource tiếp tục cung cấp các query link. Client có thể theo chuỗi relation:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

import java.util.Map;

Map<String, Object> parameters = Map.of(
        "status", "OPEN",
        "page", 0,
        "size", 20
);

PagedModel<EntityModel<OrderSummary>> openOrders = traverson
        .follow("orders", "search", "findByStatus")
        .withTemplateParameters(parameters)
        .toObject(orderPageType);
```

Ví dụ giả định root công bố `orders`, collection có link `search`, và search resource công bố `findByStatus` dưới dạng URI template có các biến `status`, `page` và `size`. Tên query relation phụ thuộc repository và cấu hình Spring Data REST; hãy kiểm tra representation thực tế hoặc profile API.

Mỗi hop trong `follow(...)` là một bước điều hướng riêng: `Traverson` tải tài nguyên hiện tại, tìm relation kế tiếp, rồi gửi request tới link tìm được. Chuỗi relation vì thế mô tả một hành trình qua API, không phải một đường dẫn URL được ghép sẵn.

## Đọc link root mà chưa theo tới tài nguyên

Đôi khi client chỉ cần biết URI của một khả năng để quyết định lúc nào mới gọi. `asLink()` trả link được tìm thấy ở hop cuối, thay vì tải representation cuối cùng:

```java
import java.net.URI;

import org.springframework.hateoas.Link;

Link ordersLink = traverson
        .follow("orders")
        .asLink();

URI ordersUri = URI.create(ordersLink.getHref());
```

Nếu link là URI template, dùng `asTemplatedLink()` để giữ thông tin templated và chỉ mở rộng khi đã có tham số:

```java
import org.springframework.hateoas.Link;

Link searchLink = traverson
        .follow("orders", "search", "findByStatus")
        .asTemplatedLink();
```

`asLink()` và `asTemplatedLink()` hữu ích khi ứng dụng muốn tách discovery khỏi thời điểm thực hiện request, ví dụ hiển thị danh sách chức năng hoặc lưu link để gọi sau. Client vẫn cần xử lý link có thể vắng mặt nếu server không công bố relation.

## Root link có thể là URI template

Một số API công bố link template ngay ở root, chẳng hạn link tìm kiếm toàn cục:

```json
{
  "_links": {
    "self": { "href": "/api" },
    "search": {
      "href": "/api/search{?q,category,page,size}",
      "templated": true
    }
  }
}
```

Client cần mở rộng template bằng tham số phù hợp thay vì tự ghép query string:

```java
import java.util.Map;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

Map<String, Object> parameters = Map.of(
        "q", "keyboard",
        "category", "accessories",
        "page", 0,
        "size", 10
);

PagedModel<EntityModel<ProductSummary>> result = traverson
        .follow("search")
        .withTemplateParameters(parameters)
        .toObject(new ParameterizedTypeReference<>() {});
```

Tên biến phải khớp template server công bố. Không gửi tham số không được template hỗ trợ với kỳ vọng server sẽ tự hiểu. Nếu một hop cần bộ tham số khác, Spring HATEOAS cung cấp `Hop` để cấu hình từng bước riêng.

Ví dụ cấu hình một hop:

```java
import java.util.Map;

import static org.springframework.hateoas.client.Hop.rel;

Map<String, Object> queryParameters = Map.of(
        "status", "OPEN",
        "page", 0,
        "size", 20
);

PagedModel<EntityModel<OrderSummary>> result = traverson
        .follow(rel("orders"))
        .follow(rel("search"))
        .follow(rel("findByStatus").withParameters(queryParameters))
        .toObject(orderPageType);
```

`Hop` cho phép gắn URI template parameter vào đúng relation. Khi có nhiều tham số, có thể dùng `.withParameters(Map)` trên hop. Đây là cách rõ ràng hơn khi mỗi bước traversal cần giá trị khác nhau.

## Xử lý root và link không tồn tại

Client không nên giả định mọi relation luôn có mặt. Server có thể lược một link khi tính năng không được bật, tài nguyên không tồn tại hoặc quyền truy cập hiện tại không cho phép công bố khả năng đó.

Trước khi thực hiện workflow, client nên xác định link cần dùng có tồn tại hay không. Nếu relation không có, ứng dụng có thể:

- Ẩn chức năng tương ứng trong giao diện.
- Hiển thị thông báo rằng thao tác hiện không khả dụng.
- Chọn một workflow thay thế nếu hợp đồng cho phép.
- Ghi nhận lỗi tích hợp nếu relation bắt buộc theo hợp đồng nhưng server không công bố.

Không tự dựng URI dự phòng bằng cách nối chuỗi path. Cách đó tạo ra một hợp đồng ngầm ngoài hypermedia và có thể thất bại khi server thay đổi mapping.

Khi `Traverson.follow(...)` không tìm thấy relation, traversal sẽ thất bại thay vì tự đoán URI. Nếu muốn xử lý mềm, client có thể tải root bằng HTTP client thông thường, kiểm tra `_links` trước rồi mới khởi tạo traversal. Cũng có thể dùng `LinkDiscoverer` để tìm link trong representation đã tải.

## Dùng LinkDiscoverer khi cần kiểm soát root response

`Traverson` phù hợp với chuỗi điều hướng. Nếu client cần tự quyết định bước tiếp theo, `LinkDiscoverer` có thể tìm link relation trong raw HAL JSON:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.mediatype.hal.HalLinkDiscoverer;

String rootJson = """
        {
          "_links": {
            "self": { "href": "/api" },
            "orders": { "href": "/api/orders" }
          }
        }
        """;

LinkDiscoverer discoverer = new HalLinkDiscoverer();
Link orders = discoverer.findLinkWithRel("orders", rootJson)
        .orElseThrow(() -> new IllegalStateException(
                "API root không công bố relation orders"));
```

`LinkDiscoverer` chỉ phân tích representation đã có; nó không tự gửi request tới `href`. Sau đó client có thể quyết định tải link bằng `RestClient`, `WebClient` hoặc `Traverson`. Cách này hữu ích khi cần kiểm tra link tùy chọn, xử lý nhiều link cùng relation hoặc ghi log quá trình discovery.

## Truyền authentication và header cho traversal

Các request do `Traverson` thực hiện thường cần cùng authentication và một số header như `Accept-Language`, correlation ID hoặc tenant context. Có thể truyền header cho traversal:

```java
import java.util.List;
import java.util.Locale;

import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);
headers.setAcceptLanguageAsLocales(List.of(Locale.forLanguageTag("vi")));

PagedModel<EntityModel<OrderSummary>> orders = traverson
        .follow("orders")
        .withHeaders(headers)
        .toObject(orderPageType);
```

Header được áp dụng cho các request trong traversal đó. Token cần được cấp bởi cơ chế xác thực của ứng dụng; không ghi token vào URI hoặc log. Nếu các hop dẫn tới host khác, cần áp dụng chính sách bảo mật phù hợp trước khi gửi credential tới host đích.

Mặc định `Traverson` dùng `RestTemplate` cùng message converter phù hợp với media type đã cấu hình. Có thể thay `RestOperations` bằng client đã được cấu hình timeout, proxy, TLS hoặc authentication interceptor:

```java
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;
import org.springframework.web.client.RestTemplate;

Traverson traverson = new Traverson(apiRoot, MediaTypes.HAL_JSON)
        .setRestOperations(restTemplate);
```

`RestTemplate` trong ví dụ cần được cấu hình bởi ứng dụng. Không dùng một client mặc định không timeout trong các workflow có yêu cầu giới hạn thời gian rõ ràng.

`Traverson` là API client đồng bộ dựa trên `RestOperations`; mỗi hop thực hiện request HTTP trong luồng gọi hiện tại. Với ứng dụng reactive cần tránh blocking, dùng `WebClient` và `LinkDiscoverer`/model HAL để thực hiện từng bước theo cách reactive thay vì gọi `Traverson` trực tiếp trong pipeline.

## API root trong Spring Data REST

Spring Data REST tự tạo root resource từ repository được export. Ví dụ, nếu ứng dụng có `OrderRepository` và `CustomerRepository`, root có thể chứa relation collection tương ứng. Client bắt đầu bằng URI base path đã cấu hình, ví dụ `/api`, sau đó khám phá link `orders` hoặc `customers`.

Collection resource thường công bố link `search` nếu repository có query method được export. Search resource công bố link tới từng query method. Một query link có thể là URI template để nhận tham số:

```json
{
  "_links": {
    "findByStatus": {
      "href": "/api/orders/search/findByStatus{?status,page,size,sort}",
      "templated": true
    }
  }
}
```

Client đi từ root tới collection, từ collection tới search resource, rồi từ search resource tới query relation. Mỗi bước đều dựa vào relation mà server công bố. Nếu query method bị đổi tên nội bộ nhưng relation công khai được giữ qua cấu hình phù hợp, client vẫn có thể tiếp tục theo relation đó.

## Kiểm thử API root và client traversal

Root endpoint là hợp đồng đầu tiên mà client gặp. Kiểm thử cần xác nhận root trả đúng media type, có `self` link và công bố những relation cốt lõi:

```java
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
class ApiRootControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesEntryPointLinks() throws Exception {
        mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.customers.href").exists());
    }
}
```

Ngoài test root, nên kiểm tra traversal từ root tới một tài nguyên đích bằng mock HTTP server hoặc môi trường integration test. Kiểm tra này giúp phát hiện lỗi ở `href`, relation, media type, template expansion và authentication mà test controller đơn lẻ không bao quát.

Các tình huống cần cân nhắc:

| Tình huống | Điều cần xác nhận |
|---|---|
| Root trả HAL JSON | `Content-Type` tương thích `application/hal+json` |
| Root có relation `orders` | Client tìm thấy link và tải được collection |
| Relation tùy chọn bị lược | Client xử lý gracefully, không tự ghép URL |
| Link là URI template | Tham số được mở rộng đúng và được encode |
| Root đổi path nội bộ | Client vẫn hoạt động qua relation và `href` mới |
| API yêu cầu bearer token | Header xác thực được gửi theo traversal |
| API trả media type không hỗ trợ | Client báo lỗi rõ ràng thay vì parse sai representation |

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Bắt đầu từ URL collection đã hard-code | Client bỏ qua API entry point và phụ thuộc path | Cấu hình root URI rồi theo relation |
| Nghĩ API root luôn là `/` | Gateway hoặc base path có thể khác | Cấu hình URI root thực tế |
| Root chỉ trả dữ liệu, không có link | Client không có đường khám phá | Công bố relation dẫn tới resource cần thiết |
| Dùng tên controller để suy ra relation | Refactor code có thể làm client hỏng | Dùng relation như hợp đồng công khai, độc lập tên class |
| Gọi `.follow("orders")` nhưng root không có relation đó | Traversal thất bại | Kiểm tra root contract và relation đã export |
| Tự nối `"/api/orders"` khi thiếu link | Tạo phụ thuộc URI ngầm | Xử lý link vắng mặt theo workflow |
| Không khai báo media type cho Traverson | Client có thể gửi Accept không đúng hoặc không parse được HAL | Khởi tạo với `MediaTypes.HAL_JSON` |
| Dùng `toObject(Class)` cho generic collection | Mất thông tin kiểu phần tử | Dùng `ParameterizedTypeReference<T>` |
| Không mở rộng URI template | Request thiếu query parameter hoặc còn dấu ngoặc template | Dùng `withTemplateParameters(...)` hoặc `Hop` |
| Giả định mọi link đều có sẵn cho mọi người dùng | Workflow thất bại khi capability bị lược | Kiểm tra relation trước khi sử dụng |
| Gửi credential tới host bất kỳ từ link | Có thể rò rỉ token | Kiểm tra origin và chính sách chuyển tiếp header |

## Quy trình bắt đầu traversal

1. Lấy API root URI từ cấu hình, tài liệu tích hợp hoặc service discovery.
2. Xác định media type mà API root trả về, ví dụ `MediaTypes.HAL_JSON`.
3. Tạo `Traverson` với root URI và media type đó.
4. Gửi request root và đọc các relation trong `_links`.
5. Chọn relation theo workflow, ví dụ `orders` hoặc `customers`.
6. Dùng `follow(...)` để đi qua các relation tiếp theo như `search` và query relation.
7. Mở rộng URI template bằng tham số được công bố.
8. Chuyển representation cuối thành kiểu Java phù hợp hoặc lấy `Link` nếu chỉ cần URI đích.
9. Xử lý link vắng mặt, lỗi HTTP, authentication và media type không tương thích.
10. Kiểm thử root contract và toàn bộ traversal quan trọng.

## Kết luận

API root là điểm vào duy nhất mà client cần biết trước để bắt đầu khám phá một API hypermedia. Root công bố các relation dẫn tới collection, search resource, profile và các khả năng khác; client theo `href` thay vì tự ghép URI. Spring HATEOAS `Traverson` hỗ trợ bắt đầu từ root, theo nhiều relation, mở rộng URI template, truyền header và đọc representation cuối. Khi root contract ổn định, relation có ngữ nghĩa rõ ràng và client xử lý link tùy chọn một cách chủ động, API có thể thay đổi cấu trúc URI mà không buộc mọi client phải sửa theo.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Client-side Support / Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client): khởi tạo Traverson, theo relation, truyền template parameters và đọc representation.
- [Traverson API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html): constructor, `follow`, `setRestOperations` và `setLinkDiscoverers`.
- [Traverson.TraversalBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.TraversalBuilder.html): `withHeaders`, `withTemplateParameters`, `toObject`, `toEntity`, `asLink` và `asTemplatedLink`.
- [Spring HATEOAS Reference – Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links): relation và target trong hypermedia link.
