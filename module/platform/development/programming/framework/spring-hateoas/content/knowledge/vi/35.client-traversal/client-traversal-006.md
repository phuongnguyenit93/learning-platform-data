# Theo link template với Spring HATEOAS

Trong hypermedia API, một link có thể trỏ trực tiếp tới URI hoàn chỉnh hoặc mô tả một **URI template** còn chứa biến. Client đọc template từ representation, cung cấp giá trị cho các biến rồi mở rộng thành URI có thể gửi request. Cách này đặc biệt hữu ích với search endpoint, filter, phân trang và tài nguyên có path parameter.

Spring HATEOAS hỗ trợ hai mức xử lý. Lớp `Link` và `UriTemplate` cho phép client đọc biến và mở rộng template. `Traverson` hỗ trợ điều hướng qua các link relation, tự tìm link trong representation HAL và mở rộng template trong quá trình đi qua API.

Bài này sử dụng một API đơn hàng để minh họa cách khám phá link `search`, truyền các tiêu chí tìm kiếm và theo link được server công bố mà không tự ghép đường dẫn.

## 1. URI template là gì?

URI template là một URI có chứa các biểu thức biến theo quy tắc RFC 6570. Biến cho phép client cung cấp một phần của URI tại thời điểm sử dụng.

Ví dụ:

~~~text
/orders/{orderId}
/orders{?status,page,size}
/orders/{orderId}{?projection}
~~~

Ý nghĩa:

- `/orders/{orderId}` có biến path `orderId`.
- `/orders{?status,page,size}` có các query parameter tùy chọn.
- `/orders/{orderId}{?projection}` kết hợp biến path và query.

Nếu client cung cấp `orderId=42`, URI đầu tiên được mở rộng thành:

~~~text
/orders/42
~~~

Nếu client cung cấp `status=PAID` và `page=0` cho template thứ hai, URI được tạo thành:

~~~text
/orders?status=PAID&page=0
~~~

Template không phải endpoint riêng. Nó là mô tả cách tạo URI từ những giá trị đầu vào.

## 2. Vì sao server công bố template thay vì client tự ghép URL?

Giả sử client cần tìm các đơn hàng đã thanh toán. Nếu API chỉ công bố link collection:

~~~json
{
  "_links": {
    "orders": {
      "href": "/api/orders"
    }
  }
}
~~~

client vẫn phải biết tên query parameter, chẳng hạn `status`, `page` và `size`. Khi server đổi tên parameter hoặc chuyển route, client có thể tiếp tục gửi request theo quy ước cũ.

Nếu server công bố link templated:

~~~json
{
  "_links": {
    "search": {
      "href": "/api/orders{?status,createdFrom,page,size,sort}",
      "templated": true
    }
  }
}
~~~

client có thể khám phá tên biến từ chính link. Server kiểm soát URI đích và công bố các biến mà endpoint hỗ trợ.

Lợi ích chính:

- Client không phải tự đoán cấu trúc URI.
- Server có thể thay đổi route mà không buộc client ghép URL mới.
- Một link có thể mô tả nhiều request dựa trên các giá trị khác nhau.
- Các tham số tìm kiếm và phân trang trở thành một phần có thể khám phá của contract hypermedia.

Template chỉ công bố hình dạng URI. Nó không tự mô tả đầy đủ kiểu dữ liệu, giới hạn, ý nghĩa nghiệp vụ hoặc quyền truy cập của từng biến. Nếu client cần metadata form như kiểu input, required, options hay HTTP method, API có thể công bố thêm affordance HAL-FORMS hoặc tài liệu profile.

## 3. Nhận biết templated link trong HAL

Trong HAL, link template được biểu diễn bằng thuộc tính `templated: true`.

Ví dụ:

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

Client cần kiểm tra thuộc tính này trước khi quyết định có mở rộng link hay không. Một link thông thường không chứa biến thì có thể được sử dụng trực tiếp.

Hai khái niệm cần phân biệt:

| Link | Ý nghĩa |
|---|---|
| Link thông thường | `href` đã là URI có thể sử dụng |
| Templated link | `href` còn chứa biến cần được mở rộng |

Không nên tự suy luận rằng mọi href có dấu ngoặc nhọn đều là template hợp lệ. Hãy dựa vào metadata link do media type cung cấp và dùng thư viện hypermedia để đọc nó.

## 4. Các biểu thức template thường gặp

RFC 6570 định nghĩa các toán tử mở rộng khác nhau. Khi làm việc với API Spring, các dạng thường gặp nhất là biến path và query.

| Biểu thức | Mục đích | Ví dụ sau khi mở rộng |
|---|---|---|
| `{id}` | Chèn biến vào URI | `/orders/42` |
| `{/id}` | Thêm path segment | `/orders/42` |
| `{?status,page}` | Tạo query string | `/orders?status=PAID&page=0` |
| `{&size}` | Bổ sung query parameter | `/orders?status=PAID&size=20` |
| `{?tag*}` | Mở rộng collection thành nhiều parameter | `/orders?tag=urgent&tag=gift` |

Ví dụ template kết hợp:

~~~text
/orders/{orderId}{?projection,locale}
~~~

Với `orderId=42`, `projection=summary` và `locale=vi`, URI có dạng:

~~~text
/orders/42?projection=summary&locale=vi
~~~

Nên dùng những biểu thức phổ biến mà client và server cùng hỗ trợ. Đừng tự đặt cú pháp placeholder như `:id` hoặc `[status]` rồi kỳ vọng Spring HATEOAS hiểu chúng như RFC 6570.

## 5. Link và UriTemplate trong Spring HATEOAS

`Link` là value object chứa href, relation và metadata của liên kết. Khi href là URI template, Spring HATEOAS có thể:

- Kiểm tra link có phải template hay không bằng `isTemplated()`.
- Đọc tên biến bằng `getVariableNames()`.
- Lấy các `TemplateVariable` chi tiết bằng `getVariables()`.
- Mở rộng link bằng `expand(...)`.

`UriTemplate` biểu diễn template độc lập và cung cấp `expand(...)` để tạo URI.

Ví dụ:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.UriTemplate;

Link searchLink = Link.of(
    UriTemplate.of("/api/orders{?status,page,size}"),
    IanaLinkRelations.SEARCH
);
~~~

Trong ví dụ, link mang relation `search` và href là URI template. Client có thể đọc metadata hoặc mở rộng nó khi cần thực hiện truy vấn.

## 6. Đọc tên biến trước khi mở rộng

Không nên hard-code tên biến trong client nếu client có thể khám phá chúng từ link.

~~~java
Link searchLink = Link.of(
    UriTemplate.of("/api/orders{?status,createdFrom,page,size,sort}"),
    IanaLinkRelations.SEARCH
);

if (searchLink.isTemplated()) {
    List<String> variables = searchLink.getVariableNames();

    System.out.println(variables);
}
~~~

Kết quả có thể là:

~~~text
[status, createdFrom, page, size, sort]
~~~

Ứng dụng có thể dùng danh sách này để kiểm tra khả năng của endpoint hoặc tạo giao diện tìm kiếm đơn giản.

`getVariableNames()` chỉ cho biết tên biến. Nó không cho biết chắc chắn biến có bắt buộc hay không, kiểu dữ liệu mong đợi là gì, hoặc giá trị nào được server chấp nhận. Muốn có metadata đó, cần contract bổ sung.

## 7. Mở rộng Link bằng Map

Cách phổ biến là truyền một `Map<String, ?>` vào `Link.expand`.

~~~java
import java.util.Map;

Map<String, Object> parameters = Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20
);

Link expanded = searchLink.expand(parameters);
~~~

Với template:

~~~text
/api/orders{?status,page,size}
~~~

link sau khi mở rộng có href tương đương:

~~~text
/api/orders?status=PAID&page=0&size=20
~~~

Có thể chuyển link đã mở rộng thành `URI`:

~~~java
URI requestUri = expanded.toUri();
~~~

Sau khi mở rộng đủ biến cần thiết, link không còn là template. Client có thể đưa URI này cho HTTP client như `RestClient`, `RestTemplate` hoặc `WebClient`.

Dùng Map giúp code dễ đọc và không phụ thuộc thứ tự khai báo biến trong template. Cách truyền tham số dạng varargs yêu cầu giá trị được cung cấp theo thứ tự biến mà template phát hiện.

Với biến query tùy chọn, có thể bỏ hẳn key khỏi Map nếu không muốn gửi parameter đó. `Map.of(...)` không nhận giá trị `null`; vì vậy hãy chỉ đưa các filter mà client thực sự muốn áp dụng vào map.

## 8. Mở rộng UriTemplate trực tiếp

Khi chỉ cần URI và không cần giữ relation hoặc metadata link, có thể mở rộng `UriTemplate` trực tiếp.

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of(
    "/api/orders/{orderId}{?projection}"
);

URI uri = template.expand(Map.of(
    "orderId", 42,
    "projection", "summary"
));
~~~

Kết quả:

~~~text
/api/orders/42?projection=summary
~~~

Sử dụng `Link.expand` khi cần giữ relation và metadata hypermedia. Dùng `UriTemplate.expand` khi chỉ cần tạo URI từ một template đã có.

## 9. Biến tùy chọn và biến bắt buộc

Một template có thể chứa các biến query tùy chọn hoặc biến cần thiết để tạo URI hợp lệ.

Ví dụ:

~~~text
/orders{?status,page,size}
~~~

Đây là query template. Client có thể cung cấp một số biến phù hợp với contract.

Ví dụ path:

~~~text
/orders/{orderId}
~~~

`orderId` cần có giá trị để tạo URI hoàn chỉnh. Nếu thiếu biến bắt buộc, quá trình mở rộng có thể thất bại.

Spring HATEOAS `Link.toUri()` mở rộng link mà không truyền tham số. Các biến tùy chọn sẽ bị bỏ qua; nếu template còn biến bắt buộc, việc tạo URI sẽ ném `IllegalStateException`.

Vì vậy, không gọi `toUri()` trực tiếp trên template còn biến bắt buộc. Hãy mở rộng link với đủ giá trị trước:

~~~java
URI uri = link.expand(Map.of("orderId", 42)).toUri();
~~~

Đừng xem việc một biến xuất hiện trong query template là bằng chứng rằng giá trị đó bắt buộc. Hãy dựa vào contract của endpoint hoặc metadata affordance để hiểu quy tắc đầu vào.

## 10. Giá trị được encode khi mở rộng

Giá trị biến phải được đưa vào URI theo quy tắc encoding. Ví dụ từ khóa có dấu cách hoặc ký tự đặc biệt:

~~~java
Link search = Link.of(
    UriTemplate.of("/orders{?customer}"),
    IanaLinkRelations.SEARCH
);

Link expanded = search.expand(
    Map.of("customer", "Nguyen Van An & Sons")
);
~~~

Client không nên nối chuỗi:

~~~java
String uri = "/orders?customer=" + customer;
~~~

Vì giá trị có thể chứa dấu `&`, `+`, dấu cách, ký tự Unicode hoặc ký tự có ý nghĩa đặc biệt trong URI. Nối thủ công có thể làm sai cấu trúc query string hoặc thay đổi giá trị thực sự mà server nhận.

Hãy dùng `Link.expand`, `UriTemplate.expand` hoặc URI builder phù hợp. Cũng không encode toàn bộ href trước khi mở rộng, vì điều đó có thể biến các dấu phân cách template thành dữ liệu thông thường.

## 11. Theo link template bằng Traverson

`Traverson` là client-side API của Spring HATEOAS để điều hướng qua các link relation. Nó nhận URI gốc và media type, tìm link trong representation, theo relation và mở rộng template khi cần.

Ví dụ API công bố:

Root resource:

~~~json
{
  "_links": {
    "orders": {
      "href": "/api/orders"
    }
  }
}
~~~

Collection orders:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders"
    },
    "search": {
      "href": "/api/orders{?status,page,size}",
      "templated": true
    }
  }
}
~~~

Client cần lấy đơn hàng có trạng thái PAID:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

Traverson traverson = new Traverson(
    URI.create("https://api.example.com/api"),
    MediaTypes.HAL_JSON
);

Object totalElements = traverson
    .follow("orders")
    .follow("search")
    .withTemplateParameters(Map.of(
        "status", "PAID",
        "page", 0,
        "size", 20
    ))
    .toObject("$.page.totalElements");
~~~

Quá trình diễn ra:

1. Traverson gửi GET tới API root.
2. Nó tìm relation `orders` và theo href của link đó.
3. Nó đọc representation collection orders.
4. Nó tìm relation `search`.
5. Vì link search là template, Traverson mở rộng bằng các tham số đã cung cấp.
6. Nó gửi request tới URI đã mở rộng và đọc `page.totalElements` từ response cuối.

Mỗi relation trong `follow(...)` tương ứng với một chặng điều hướng và cần request để khám phá representation tiếp theo. Client không phải tự parse HAL JSON hoặc nối href.

## 12. Truyền tham số cho toàn bộ traversal

`withTemplateParameters(Map)` thêm một map tham số vào traversal. Nếu traversal gặp templated link, map đó được dùng để mở rộng link.

~~~java
Map<String, Object> parameters = Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20
);

Object total = traverson
    .follow("orders", "search")
    .withTemplateParameters(parameters)
    .toObject("$.page.totalElements");
~~~

Cách này ngắn gọn khi các template trong hành trình sử dụng cùng bộ biến hoặc khi map chỉ chứa các biến liên quan tới những template đó.

Lưu ý: tham số ở cấp traversal được áp dụng cho mọi templated link mà traversal gặp. Nếu hai chặng có template khác nhau và cần giá trị riêng, dùng `Hop` để gắn tham số vào đúng relation.

## 13. Dùng Hop để truyền tham số riêng cho từng chặng

`Hop` đại diện cho một bước điều hướng tùy chỉnh. Nó cho phép gắn query parameter hoặc header vào đúng relation.

~~~java
import static org.springframework.hateoas.client.Hop.rel;

Object total = traverson
    .follow("orders")
    .follow(
        rel("search")
            .withParameter("status", "PAID")
            .withParameter("page", 0)
            .withParameter("size", 20)
    )
    .toObject("$.page.totalElements");
~~~

Nếu cần truyền nhiều tham số, có thể dùng `withParameters(Map)`:

~~~java
Hop searchHop = rel("search").withParameters(Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20
));

Object total = traverson
    .follow("orders")
    .follow(searchHop)
    .toObject("$.page.totalElements");
~~~

`Hop` phù hợp khi mỗi chặng có bộ tham số hoặc header khác nhau. Nó giúp tránh việc đưa tất cả giá trị vào một map toàn cục rồi vô tình áp dụng chúng cho các template không liên quan.

## 14. Lấy templated link mà chưa thực hiện request cuối

Đôi khi client muốn khám phá link template trước, hiển thị form cho người dùng, rồi mới gửi request khi người dùng chọn điều kiện.

Traverson cung cấp `asTemplatedLink()` để lấy link template ở relation cuối của traversal:

~~~java
Link searchTemplate = traverson
    .follow("orders")
    .follow("search")
    .asTemplatedLink();
~~~

Sau đó client có thể đọc biến:

~~~java
List<String> variableNames = searchTemplate.getVariableNames();
~~~

Khi người dùng nhập tiêu chí tìm kiếm, client mở rộng link:

~~~java
Link requestLink = searchTemplate.expand(Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20
));

URI requestUri = requestLink.toUri();
~~~

`asTemplatedLink()` hữu ích khi muốn giữ template để dùng nhiều lần với các giá trị khác nhau. `asLink()` trả về link cuối sau khi áp dụng các tham số template được cung cấp cho traversal.

Không gọi `asTemplatedLink()` nếu mục tiêu là lấy nội dung representation cuối; trong trường hợp đó dùng `toObject(...)` hoặc `toEntity(...)`.

## 15. Đọc kết quả bằng kiểu Java thay vì JSONPath

`toObject(String jsonPath)` hữu ích khi chỉ cần một phần dữ liệu trong representation cuối. Nếu cần deserialize toàn bộ response thành kiểu Java, có thể dùng `toObject(Class<T>)` hoặc `toObject(ParameterizedTypeReference<T>)`.

Ví dụ lấy một giá trị đơn:

~~~java
Integer totalPages = traverson
    .follow("orders", "search")
    .withTemplateParameters(Map.of(
        "status", "PAID",
        "page", 0,
        "size", 20
    ))
    .toObject("$.page.totalPages");
~~~

Ví dụ lấy response dưới dạng object có generic:

~~~java
ParameterizedTypeReference<PagedModel<EntityModel<OrderDto>>> responseType =
    new ParameterizedTypeReference<>() {};

PagedModel<EntityModel<OrderDto>> result = traverson
    .follow("orders", "search")
    .withTemplateParameters(Map.of(
        "status", "PAID",
        "page", 0,
        "size", 20
    ))
    .toObject(responseType);
~~~

Kiểu dữ liệu đích phải phù hợp với representation thực tế và message converter được cấu hình cho media type đó. Nếu client chỉ cần link hoặc HTTP headers của response cuối, dùng `toEntity(...)`.

## 16. Gửi header khi theo link template

Một số API yêu cầu authentication hoặc header bổ sung. Traverson hỗ trợ truyền header cho traversal hoặc cho từng hop.

Header cho traversal:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);

PagedModel<EntityModel<OrderDto>> result = traverson
    .follow("orders", "search")
    .withHeaders(headers)
    .withTemplateParameters(Map.of(
        "status", "PAID",
        "page", 0,
        "size", 20
    ))
    .toObject(responseType);
~~~

Header cho một hop cụ thể:

~~~java
Hop authenticatedSearch = rel("search")
    .withParameter("status", "PAID")
    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi");

Object total = traverson
    .follow("orders")
    .follow(authenticatedSearch)
    .toObject("$.page.totalElements");
~~~

Không đặt access token trong URI template hoặc query parameter. Token nên được gửi bằng header thích hợp. Chỉ tin forwarded headers hoặc thông tin host do hạ tầng proxy đáng tin cậy cung cấp.

## 17. Tùy chỉnh HTTP client và LinkDiscoverer

Traverson mặc định sử dụng một `RestTemplate` và `HalLinkDiscoverer` cho HAL. Có thể thay đổi `RestOperations` khi ứng dụng cần timeout, proxy, interceptor hoặc authentication configuration riêng.

~~~java
Traverson traverson = new Traverson(
    URI.create("https://api.example.com/api"),
    MediaTypes.HAL_JSON
);

RestTemplate restTemplate = new RestTemplate(
    Traverson.getDefaultMessageConverters(MediaTypes.HAL_JSON)
);

traverson.setRestOperations(restTemplate);
~~~

Khi tự tạo `RestTemplate`, cần bảo đảm nó có message converter hiểu HAL. `getDefaultMessageConverters(...)` cung cấp các converter mặc định phù hợp với media type được truyền vào; nếu ứng dụng đã có cấu hình converter riêng, hãy giữ lại cấu hình đó và bổ sung hỗ trợ hypermedia tương ứng.

Nếu API dùng một media type hypermedia khác, client cần một `LinkDiscoverer` phù hợp để đọc link relation từ representation đó.

~~~java
traverson.setLinkDiscoverers(customLinkDiscoverers);
~~~

Chỉ thay link discoverer khi media type thực sự yêu cầu. Với HAL JSON thông thường, discoverer mặc định của Traverson đã được đăng ký.

## 18. Xử lý template có collection parameter

Một query parameter có thể nhận nhiều giá trị. Ví dụ API cho phép lọc nhiều trạng thái:

~~~text
/orders{?status*}
~~~

Nếu biến `status` là collection gồm `PAID` và `SHIPPED`, dạng mở rộng theo explode có thể tạo query lặp:

~~~text
/orders?status=PAID&status=SHIPPED
~~~

Điều này phù hợp với endpoint nhận nhiều giá trị cùng tên query parameter.

Không nên giả định mọi API dùng cùng một quy ước collection. Một API khác có thể yêu cầu comma-separated:

~~~text
/orders?status=PAID,SHIPPED
~~~

Client phải tuân theo template và contract mà server công bố. Nếu template chỉ có `{?status}`, hãy xác minh cách server định nghĩa giá trị collection trước khi truyền một List.

## 19. Template không thay thế validation và authorization

Một templated link cho biết cách tạo URI, không bảo đảm mọi giá trị đều hợp lệ hoặc người gọi có quyền truy cập.

Ví dụ template:

~~~text
/orders{?status,page,size,sort}
~~~

vẫn có thể nhận giá trị không hợp lệ:

- `status=UNKNOWN` không tồn tại trong enum.
- `page=-1` nằm ngoài phạm vi.
- `size=1000000` vượt giới hạn server.
- `sort=internalSecretField,desc` không được phép.
- Người gọi không có quyền xem các đơn hàng thuộc tenant khác.

Server vẫn phải validate từng request, giới hạn page size, allow-list sort key và kiểm tra authorization theo tài nguyên. Client cũng nên xử lý lỗi HTTP như `400 Bad Request`, `401 Unauthorized`, `403 Forbidden` và `404 Not Found`.

Không coi template là schema xác thực đầu vào. Nó chỉ mô tả cách hình thành URI.

## 20. Những lỗi thường gặp khi theo link template

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Bỏ qua `templated: true` | Client gửi nguyên template như URI | Kiểm tra `Link.isTemplated()` hoặc dùng Traverson |
| Tự ghép query string | Sai encoding hoặc trùng dấu phân cách | Dùng `Link.expand` hoặc `UriTemplate.expand` |
| Đoán tên biến | Request không khớp contract | Đọc `getVariableNames()` |
| Gọi `toUri()` khi còn biến bắt buộc | Có thể ném `IllegalStateException` | Cung cấp đủ biến trước khi tạo URI |
| Dùng một map cho mọi hop dù biến khác nhau | Giá trị bị áp dụng nhầm chặng | Dùng `Hop.withParameter(...)` |
| Nghĩ `follow()` chỉ tạo một request | Đánh giá sai số lần gọi mạng | Mỗi relation cần được khám phá qua một request |
| Dùng JSONPath không khớp response | Không đọc được kết quả | Kiểm tra cấu trúc representation thực tế |
| Gửi token trong query | Token có thể xuất hiện trong log hoặc history | Gửi credential bằng header |
| Cho rằng template đảm bảo input hợp lệ | Server vẫn nhận giá trị sai hoặc không có quyền | Validate và authorize ở server |
| Không cấu hình LinkDiscoverer cho media type riêng | Traverson không tìm thấy relation | Đăng ký discoverer tương ứng |

## 21. Kiểm thử việc mở rộng template

Có thể kiểm thử `Link` độc lập mà không cần gọi HTTP server:

~~~java
@Test
void expandsSearchLink() {
    Link search = Link.of(
        UriTemplate.of("/orders{?status,page,size}"),
        IanaLinkRelations.SEARCH
    );

    Link expanded = search.expand(Map.of(
        "status", "PAID",
        "page", 0,
        "size", 20
    ));

    assertThat(search.isTemplated()).isTrue();
    assertThat(search.getVariableNames())
        .containsExactly("status", "page", "size");

    assertThat(expanded.isTemplated()).isFalse();
    assertThat(expanded.getHref())
        .isEqualTo("/orders?status=PAID&page=0&size=20");
}
~~~

Có thể kiểm thử API tích hợp bằng mock HTTP server hoặc `MockRestServiceServer` để xác nhận Traverson:

- Gửi request tới đúng API root.
- Tìm relation từ representation HAL.
- Theo đúng thứ tự relation.
- Mở rộng template với các giá trị được cung cấp.
- Gửi đúng `Accept` header.
- Deserialize response cuối thành kiểu Java hoặc JSONPath.
- Trả lỗi rõ ràng khi relation hoặc biến không tồn tại.

Kiểm thử cả URI sau mở rộng và request cuối giúp phát hiện lỗi encoding, tên biến hoặc cấu trúc relation.

## 22. Quy trình theo một link template

Khi client cần dùng một templated link, hãy thực hiện theo trình tự:

1. Nhận representation hypermedia từ server.
2. Tìm link theo relation cần dùng, chẳng hạn `search`.
3. Kiểm tra link có phải template hay không.
4. Đọc tên biến và metadata mà API công bố.
5. Thu thập giá trị phù hợp từ client hoặc người dùng.
6. Mở rộng link bằng `Link.expand` hoặc `UriTemplate.expand`.
7. Nếu cần đi qua nhiều resource, dùng `Traverson.follow`.
8. Dùng `withTemplateParameters` cho bộ tham số chung hoặc `Hop` cho từng chặng.
9. Gửi request bằng HTTP client và đọc representation cuối.
10. Xử lý lỗi, validate dữ liệu và không giả định template đảm bảo quyền truy cập.

Theo link template giúp client tạo request từ thông tin server công bố. Spring HATEOAS cung cấp `Link` và `UriTemplate` cho việc đọc biến, mở rộng URI; `Traverson` giúp theo relation và tự xử lý templated link trong quá trình điều hướng. Khi client dựa trên relation và template thay vì ghép URL, hai phía có thể tiến hóa route và query contract có kiểm soát hơn.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates)
- [Spring HATEOAS Reference — Client-side support and Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson)
- [Spring HATEOAS API — Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API — UriTemplate](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html)
- [Spring HATEOAS API — Traverson](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Spring HATEOAS API — Hop](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Hop.html)
- [RFC 6570 — URI Template](https://www.rfc-editor.org/rfc/rfc6570)
