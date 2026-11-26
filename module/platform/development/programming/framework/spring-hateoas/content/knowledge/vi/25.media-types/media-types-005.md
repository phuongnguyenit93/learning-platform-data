# HAL media type

HAL (Hypertext Application Language) là định dạng JSON dành cho representation của tài nguyên có liên kết hypermedia. Media type của HAL JSON là `application/hal+json`. Khi REST API trả response với media type này, client biết payload tuân theo quy ước HAL: liên kết nằm trong `_links` và tài nguyên liên quan có thể được nhúng trong `_embedded`.

Trong Spring HATEOAS, các kiểu `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel` cung cấp mô hình dữ liệu để framework serialize thành HAL. Media type được chọn qua HTTP content negotiation, thường dựa trên header `Accept` của client. Hiểu rõ `application/hal+json` giúp bạn cấu hình endpoint, kiểm thử response và phân biệt HAL với JSON thông thường hoặc HAL-FORMS.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của media type `application/hal+json`.
- Phân biệt `Content-Type` và `Accept` khi trao đổi HAL.
- Nhận diện cấu trúc HAL gồm content, `_links` và `_embedded`.
- Dùng các model của Spring HATEOAS để tạo response HAL.
- Bật hỗ trợ HAL trong Spring Boot hoặc cấu hình Spring MVC thủ công.
- Kiểm tra content negotiation và response bằng MockMvc.
- Phân biệt HAL JSON với `application/json` và HAL-FORMS.

## Media type là gì?

Media type cho biết định dạng của phần nội dung HTTP. Header `Content-Type` mô tả định dạng body đang được gửi; header `Accept` cho biết client muốn nhận những định dạng nào.

Ví dụ client yêu cầu một đơn hàng dưới dạng HAL:

```http
GET /orders/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Nếu server hỗ trợ định dạng đó, response có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": 42,
  "status": "NEW",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    }
  }
}
```

Client dùng `Accept` để thương lượng định dạng mong muốn. Server dùng `Content-Type` để xác nhận định dạng thực tế của response. Hai header này có vai trò khác nhau:

| Header | Hướng trao đổi | Ý nghĩa |
|---|---|---|
| `Accept` | Client gửi tới server | Client chấp nhận hoặc ưu tiên media type nào |
| `Content-Type` | Server gửi về client | Body response đang được biểu diễn theo media type nào |
| `Content-Type` trong request | Client gửi tới server | Body request đang dùng định dạng nào |

Với request có JSON body, client có thể gửi `Content-Type: application/json` trong khi yêu cầu response HAL bằng `Accept: application/hal+json`. Định dạng request và response được thương lượng độc lập.

## application/hal+json

`application/hal+json` là media type cho HAL được biểu diễn bằng JSON. Nó cho biết payload sử dụng các quy ước HAL, chứ không chỉ là một object JSON tùy ý.

Một representation HAL thường có:

- Các thuộc tính content của tài nguyên, ví dụ `id`, `status`, `total`.
- `_links` chứa các link object được nhóm theo relation.
- `_embedded` chứa representation của tài nguyên liên quan được nhúng inline.

Ví dụ:

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
      "href": "https://api.example.test/customers/7"
    }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Nguyen An"
    }
  }
}
```

`_links` và `_embedded` là các thành phần đặc trưng của HAL. Những trường như `id`, `status`, `total` và `name` do API định nghĩa. HAL không bắt buộc mọi API phải có cùng một schema nghiệp vụ.

### Link object trong HAL

Một link object có `href` là URI đích và có thể chứa các thuộc tính mô tả bổ sung:

| Thuộc tính | Ý nghĩa |
|---|---|
| `href` | URI đích của liên kết |
| `templated` | Cho biết `href` là URI template cần được mở rộng |
| `type` | Media type dự kiến của tài nguyên đích |
| `deprecation` | URI tới thông tin về việc relation hoặc link bị deprecated |
| `name` | Tên phân biệt một link trong cùng relation |
| `profile` | URI profile mô tả thêm representation hoặc liên kết |
| `title` | Tiêu đề dễ đọc cho người dùng |
| `hreflang` | Ngôn ngữ của tài nguyên đích nếu có |

Ví dụ:

```json
{
  "_links": {
    "search": {
      "href": "/orders{?status,page,size}",
      "templated": true,
      "title": "Search orders"
    }
  }
}
```

Khi có nhiều link cùng relation, HAL cho phép biểu diễn relation đó bằng một link object hoặc một mảng link object. Client nên xử lý theo cấu trúc HAL thay vì giả định mỗi relation luôn chỉ có một URI.

### Relation và CURIE

Tên key trong `_links` là link relation. Với relation chuẩn đã đăng ký, có thể dùng tên ngắn như `self`, `next` hoặc `related`. Với relation mở rộng riêng của API, nên định danh bằng URI để tránh xung đột ngữ nghĩa giữa các hệ thống.

HAL hỗ trợ CURIE (Compact URI) để biểu diễn URI relation dài bằng tên rút gọn. Ví dụ:

```json
{
  "_links": {
    "curies": [
      {
        "name": "ea",
        "href": "https://api.example.test/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "ea:cancel": {
      "href": "https://api.example.test/orders/42/cancellation"
    }
  }
}
```

Client có thể mở rộng `ea:cancel` theo CURIE đã khai báo để xác định URI relation tương ứng. Prefix và URI template của CURIE là một phần hợp đồng API; không thay đổi chúng tùy tiện nếu client đang sử dụng.

## Phân biệt HAL JSON với JSON thông thường

`application/json` chỉ xác định body là JSON. Nó không yêu cầu cấu trúc hypermedia cụ thể. `application/hal+json` cũng là JSON, nhưng bổ sung quy ước HAL cho link và embedded resource.

| Tiêu chí | `application/json` | `application/hal+json` |
|---|---|---|
| Định dạng cú pháp | JSON | JSON |
| Cấu trúc `_links` | Không được quy định | Thành phần chuẩn của HAL |
| Cấu trúc `_embedded` | Không được quy định | Thành phần chuẩn của HAL |
| Relation và link object | Do ứng dụng tự định nghĩa | Theo quy ước HAL |
| Khám phá tài nguyên | Phụ thuộc schema hoặc tài liệu riêng | Client có thể theo link và relation |
| Mục đích | Trao đổi dữ liệu JSON nói chung | Trao đổi representation JSON có hypermedia |

Không phải cứ response JSON có trường `_links` là tự động trở thành HAL. Server cần khai báo và serialize theo hợp đồng HAL, đồng thời gửi media type tương ứng.

## Spring HATEOAS và media type HAL

Spring HATEOAS cung cấp hạ tầng để chuyển các representation model thành HAL JSON. Một số kiểu thường gặp:

| Kiểu model | Vai trò |
|---|---|
| `RepresentationModel<T>` | Lớp cơ sở cho model có thể mang link |
| `EntityModel<T>` | Bọc content của một tài nguyên cùng các link |
| `CollectionModel<T>` | Biểu diễn tập hợp tài nguyên cùng link cấp collection |
| `PagedModel<T>` | Biểu diễn tập hợp có metadata phân trang và link điều hướng |
| `Link` | Biểu diễn một liên kết hypermedia |

Spring HATEOAS cung cấp hằng `MediaTypes.HAL_JSON` để tham chiếu media type HAL trong code và kiểm thử:

```java
import org.springframework.hateoas.MediaTypes;

var halJson = MediaTypes.HAL_JSON;
```

Giá trị tương ứng là `application/hal+json`. Dùng hằng này giúp tránh lặp chuỗi media type trong các test hoặc cấu hình Java.

## Thêm dependency

Với ứng dụng Spring Boot dùng Spring MVC, thêm starter Spring HATEOAS:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
}
```

Starter HATEOAS kéo các thành phần cần thiết để xây dựng hypermedia model và tích hợp với Spring MVC. Hãy để Spring Boot quản lý phiên bản dependency thông qua dependency management của dự án; không tự ghép phiên bản Spring HATEOAS khác với phiên bản Spring Boot nếu chưa kiểm tra ma trận tương thích.

Trong ứng dụng Spring Boot thông thường, auto-configuration của starter đã đăng ký các thành phần hypermedia cần thiết. Không cần thêm `@EnableHypermediaSupport` chỉ để bật HAL trong trường hợp này.

### Cấu hình Spring MVC thủ công

Nếu ứng dụng không dùng auto-configuration của Spring Boot, có thể bật HAL bằng `@EnableHypermediaSupport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
```

Annotation này đăng ký hạ tầng hypermedia cho định dạng đã chọn, bao gồm khả năng serialize representation model thành HAL. Khi dùng cấu hình tự quản lý, cần bảo đảm message converter của Spring MVC có thể xử lý media type HAL.

Không nên bật cấu hình thủ công một cách máy móc trong ứng dụng Spring Boot đã auto-configure. Cấu hình hypermedia thủ công có thể thay đổi cách Spring HATEOAS tích hợp với Jackson và ObjectMapper của Boot. Hãy chọn một cơ chế cấu hình nhất quán với cách ứng dụng khởi tạo context.

## Tạo response HAL với EntityModel

`EntityModel<T>` bọc dữ liệu của một tài nguyên và danh sách link. Khi được serialize bằng HAL converter, các link được đặt trong `_links`, còn content nằm ở cấp gốc representation.

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

record OrderView(long id, String status, long total) {
}

interface OrderService {
    OrderView findById(long id);
}

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        OrderView order = orders.findById(id);

        return EntityModel.of(
            order,
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel()
        );
    }
}
```

Khi client gửi `Accept: application/hal+json`, response có thể có cấu trúc:

```json
{
  "id": 42,
  "status": "NEW",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "http://localhost/orders/42"
    }
  }
}
```

URI cụ thể được tạo từ request và mapping của controller. Ví dụ trên dùng `linkTo(methodOn(...))`, vì vậy không phải tự ghép chuỗi `"/orders/"` với ID.

## Tạo response HAL cho collection

`CollectionModel<T>` biểu diễn tập hợp tài nguyên. Spring HATEOAS dùng relation collection để đặt các phần tử trong `_embedded`.

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.server.core.Relation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Relation(itemRelation = "order", collectionRelation = "orders")
record OrderView(long id, String status, long total) {
}

interface OrderService {
    List<OrderView> findAll();
}

@RestController
@RequestMapping("/orders")
class OrderCollectionController {

    private final OrderService orders;

    OrderCollectionController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    CollectionModel<OrderView> all() {
        return CollectionModel.of(
            orders.findAll(),
            linkTo(methodOn(OrderCollectionController.class).all()).withSelfRel()
        );
    }
}
```

Với `@Relation` trên `OrderView`, collection relation được công bố là `orders`, nên response HAL có thể chứa:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "NEW",
        "total": 1250000
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost/orders"
    }
  }
}
```

Nếu collection rỗng, cách biểu diễn `_embedded` có thể phụ thuộc model và cấu hình relation. Khi hợp đồng cần thể hiện rõ một collection rỗng, hãy kiểm thử response thực tế và chọn cách tạo model giữ relation mong muốn.

## Content negotiation trong controller

Spring MVC sử dụng `Accept` của request và các media type mà message converter hỗ trợ để chọn representation. Nếu controller trả về `EntityModel` hoặc `CollectionModel` và ứng dụng đã bật HAL, client có thể yêu cầu HAL qua `Accept`.

Ví dụ dùng `curl`:

```bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/orders/42
```

Response thành công cần có `Content-Type` tương thích với `application/hal+json`. Nếu client yêu cầu media type mà endpoint không hỗ trợ, server có thể trả `406 Not Acceptable`.

Có thể giới hạn định dạng mà endpoint công bố bằng `produces`:

```java
@GetMapping(
    value = "/{id}",
    produces = "application/hal+json"
)
EntityModel<OrderView> one(@PathVariable long id) {
    // Tạo EntityModel như ví dụ trước.
}
```

Khai báo `produces` hữu ích khi endpoint chỉ cung cấp HAL. Nếu API hỗ trợ nhiều representation, hãy cấu hình content negotiation có chủ đích và kiểm thử từng media type. Tránh khai báo một media type ở controller nhưng không có converter tương ứng trong application context.

### Accept có nhiều lựa chọn

Client có thể gửi nhiều media type cùng chất lượng ưu tiên:

```http
Accept: application/hal+json, application/json;q=0.8
```

Server sẽ chọn representation phù hợp nhất trong các định dạng mà endpoint và converter hỗ trợ. Thứ tự và quality factor (`q`) giúp client thể hiện ưu tiên; chúng không thể khiến server hỗ trợ một media type mà ứng dụng chưa cấu hình.

Khi cùng một URI trả các representation khác nhau theo `Accept`, cache trung gian cần biết response phụ thuộc header này. Hãy bảo đảm cơ chế content negotiation và cache phát ra `Vary: Accept` phù hợp để tránh dùng nhầm representation đã cache.

## Kiểm thử media type HAL bằng MockMvc

Kiểm thử endpoint nên xác nhận status, `Content-Type`, content và link. Ví dụ:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderHalMediaTypeTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void returnsHalJsonWhenClientRequestsHal() throws Exception {
        given(orders.findById(42L))
            .willReturn(new OrderView(42L, "NEW", 1_250_000L));

        mockMvc.perform(get("/orders/{id}", 42).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Với Spring Boot starter HATEOAS, test slice thường nhận cấu hình hypermedia từ auto-configuration phù hợp. Nếu test dùng cấu hình MVC thủ công, hãy import cấu hình có `@EnableHypermediaSupport(type = HypermediaType.HAL)`. Không nên vừa bật cấu hình thủ công vừa dựa vào auto-configuration mà không kiểm tra tác động lên Jackson.

Nên có thêm các kiểm thử:

- `Accept: application/hal+json` trả response có `Content-Type` tương ứng.
- Response có `_links.self` và relation nghiệp vụ cần thiết.
- Collection được serialize dưới `_embedded` với collection relation đúng.
- `Accept` không được hỗ trợ trả `406 Not Acceptable` nếu endpoint giới hạn media type.
- Request có body dùng `Content-Type` đúng với định dạng input, độc lập với `Accept` response.
- Cache header phù hợp khi cùng URI có nhiều representation theo `Accept`.

## Phân biệt HAL và HAL-FORMS

HAL và HAL-FORMS đều dựa trên JSON và có thể sử dụng cấu trúc link/embedded tương tự, nhưng là hai media type khác nhau với mục tiêu khác nhau:

| Tiêu chí | HAL | HAL-FORMS |
|---|---|---|
| Media type | `application/hal+json` | `application/prs.hal-forms+json` |
| Liên kết | `_links` | `_links` |
| Tài nguyên nhúng | `_embedded` | `_embedded` |
| Mô tả thao tác/form | Không có cấu trúc template form chuẩn | `_templates` |
| HTTP method và input properties | Không được mô tả đầy đủ trong HAL JSON | Có thể mô tả qua template |
| Dùng khi | Client cần khám phá và điều hướng tài nguyên | Client cần khám phá thêm cách gửi thao tác và dữ liệu đầu vào |

Trong Spring HATEOAS, affordance có thể được gắn vào `Link`. Khi client thương lượng HAL-FORMS, metadata affordance có thể được serialize thành `_templates`. Nếu client yêu cầu HAL JSON, nó nhận biểu diễn HAL tương ứng; không nên giả định `_templates` của HAL-FORMS sẽ xuất hiện trong mọi response HAL.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả JSON có `_links` nhưng khai báo `application/json` | Client không biết response cam kết theo HAL | Dùng media type `application/hal+json` khi response tuân theo HAL |
| Nhầm `Accept` với `Content-Type` | Content negotiation hoặc request body sai | Dùng `Accept` cho định dạng response, `Content-Type` cho body đang gửi |
| Chỉ thêm starter nhưng trả DTO thuần | Response không có link hypermedia | Trả `EntityModel`, `CollectionModel` hoặc model HATEOAS phù hợp |
| Bật `@EnableHypermediaSupport` trùng với cấu hình Boot mà không kiểm tra | Cấu hình Jackson hoặc message converter có thể thay đổi | Dùng auto-configuration Boot hoặc cấu hình thủ công nhất quán |
| Ép `produces` nhưng không đăng ký converter | Request có thể nhận `406 Not Acceptable` | Bảo đảm HAL converter và hypermedia configuration được đăng ký |
| Nghĩ HAL và HAL-FORMS là cùng media type | Client mong đợi `_templates` trong response HAL JSON | Dùng đúng `Accept` và media type cho khả năng cần thiết |
| Bỏ qua `Vary: Accept` khi cache nhiều representation | Cache có thể trả nhầm định dạng cho client | Cấu hình cache theo header thương lượng |
| Giả định mọi relation đều có một link | Client bỏ sót các link cùng relation | Xử lý cả link object và mảng link object theo HAL |

## Ghi nhớ

`application/hal+json` là media type cho representation JSON tuân theo HAL. Client yêu cầu định dạng bằng `Accept`; server xác nhận representation thực tế bằng `Content-Type`. Trong Spring HATEOAS, `EntityModel`, `CollectionModel` và `PagedModel` giúp tạo response có `_links` và `_embedded`; `MediaTypes.HAL_JSON` cung cấp hằng media type để dùng trong code và test. Spring Boot thường tự cấu hình HAL qua starter HATEOAS, còn ứng dụng Spring MVC tự quản lý có thể bật `@EnableHypermediaSupport(type = HypermediaType.HAL)`. HAL tập trung vào điều hướng tài nguyên; khi cần mô tả form và thao tác, hãy thương lượng media type HAL-FORMS riêng.

## Tài liệu tham khảo

- [HAL specification](https://stateless.group/hal_specification.html)
- [Spring HATEOAS – HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS – Hypermedia support configuration](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#configuration)
- [Spring HATEOAS – MediaTypes API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
