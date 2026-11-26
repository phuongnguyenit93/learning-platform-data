# Search relation

Trong hypermedia API, client cần khám phá cách tìm kiếm tài nguyên thông qua những link mà server công bố. Spring HATEOAS hỗ trợ relation chuẩn IANA `search` bằng hằng số `IanaLinkRelations.SEARCH`. Link mang relation này chỉ ra một tài nguyên có thể được dùng để tìm kiếm trong ngữ cảnh của link hiện tại và các tài nguyên liên quan.

Ví dụ, representation của collection sản phẩm có thể chứa link `search` trỏ đến endpoint `/products/search`. Link đó có thể là URI template với các biến như `q` và `category` để client cung cấp từ khóa và bộ lọc. Client tìm link theo relation chuẩn thay vì phải biết trước đường dẫn hoặc tên controller.

Cần phân biệt relation với cơ chế tìm kiếm. Relation `search` mô tả ý nghĩa của liên kết; bản thân nó không quy định HTTP method, tên query parameter, cú pháp biểu thức tìm kiếm, định dạng kết quả hoặc thuật toán xếp hạng. Những chi tiết đó phải được mô tả bằng URI template, affordance, media type hoặc hợp đồng API thích hợp.

Bài học này tập trung vào ý nghĩa của search relation, cách tạo link bằng Spring HATEOAS, cách công bố query template, cách client khám phá và mở rộng link, sự khác nhau giữa endpoint tìm kiếm và OpenSearch Description Document, cùng các cách kiểm thử hợp đồng hypermedia.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của relation `search` trong IANA Link Relation Registry.
- Dùng `IanaLinkRelations.SEARCH` để tạo link tìm kiếm chuẩn.
- Phân biệt search relation với URI, query parameter và search result.
- Công bố search link dưới dạng URI template.
- Tạo search link từ controller mapping bằng `WebMvcLinkBuilder`.
- Giúp client tìm và mở rộng search link bằng `RepresentationModel` và `Link.expand(...)`.
- Phân biệt link đến search endpoint với link đến OpenSearch Description Document.
- Kiểm thử relation, target, template variables và response được serialize.
- Thiết kế search contract rõ ràng, an toàn và có thể tiến hóa.

## 1. Search relation là gì?

Link relation mô tả quan hệ ngữ nghĩa giữa tài nguyên hiện tại (context) và tài nguyên đích (target). Relation không phải tên của endpoint hoặc tên một phương thức Java.

Relation `search` được đăng ký trong IANA Link Relation Registry với ý nghĩa: liên kết đến một tài nguyên có thể được dùng để tìm kiếm trong ngữ cảnh của liên kết và các tài nguyên liên quan.

Ví dụ một collection sản phẩm:

~~~json
{
  "_links": {
    "self": {
      "href": "/products"
    },
    "search": {
      "href": "/products/search{?q,category}",
      "templated": true
    }
  }
}
~~~

Trong ví dụ:

- `self` định danh collection sản phẩm đang được biểu diễn.
- `search` trỏ đến khả năng tìm kiếm trong ngữ cảnh collection đó.
- `q` là biến query cho từ khóa.
- `category` là biến query tùy chọn để giới hạn danh mục.
- `templated: true` cho biết href chứa URI template variables.

Client có thể tìm link theo relation `search`, lấy danh sách biến và mở rộng link với giá trị tìm kiếm. Nó không cần ghép đường dẫn `/products/search` từ một quy ước riêng của ứng dụng.

### 1.1. Relation là ngữ nghĩa, href là đích

Một link có hai thành phần cốt lõi:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Relation | Liên kết này có ý nghĩa gì? | `search` |
| Href | Client đi đến đâu? | `/products/search{?q,category}` |

Nếu chỉ có href mà không có relation, client phải dựa vào quy ước riêng để đoán mục đích của URI. Nếu chỉ có relation mà không có href, client không có địa chỉ để truy cập tài nguyên đích.

Spring HATEOAS biểu diễn hai phần này bằng `Link` và `LinkRelation`.

### 1.2. Search relation không phải kết quả tìm kiếm

Một link `search` thường trỏ đến endpoint hoặc tài nguyên mô tả cách tìm kiếm. Nó không tự chứa danh sách kết quả.

Ví dụ:

- `/products` là collection resource.
- `/products/search{?q}` là khả năng tìm kiếm collection.
- `/products/search?q=spring` là một truy vấn cụ thể.
- Response từ truy vấn đó là search result, có thể được biểu diễn bằng `CollectionModel` hoặc `PagedModel`.

Việc phân biệt này giúp client biết khi nào cần theo link để bắt đầu tìm kiếm và khi nào đang đọc kết quả của một truy vấn đã thực hiện.

## 2. IanaLinkRelations.SEARCH trong Spring HATEOAS

Spring HATEOAS cung cấp lớp `IanaLinkRelations` để sử dụng các link relation chuẩn đã đăng ký với IANA. Search relation được truy cập qua:

~~~java
IanaLinkRelations.SEARCH
IanaLinkRelations.SEARCH_VALUE
~~~

`SEARCH` là một `LinkRelation`; `SEARCH_VALUE` là giá trị chuỗi tương ứng.

Ví dụ:

~~~java
Link search = Link.of(
    "/products/search",
    IanaLinkRelations.SEARCH
);
~~~

Hoặc gắn relation sau khi tạo link:

~~~java
Link search = Link.of("/products/search")
    .withRel(IanaLinkRelations.SEARCH);
~~~

Cả hai cách đều tạo link có relation `search`.

Import:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
~~~

### 2.1. Vì sao nên dùng hằng số IANA?

Có thể viết trực tiếp:

~~~java
Link search = Link.of("/products/search", "search");
~~~

Tuy nhiên, `IanaLinkRelations.SEARCH` có một số lợi ích:

- Thể hiện rõ đây là relation chuẩn IANA.
- Tránh lỗi chính tả khi viết chuỗi.
- Dễ dùng chung relation ở server, client và test.
- Giúp phân biệt relation chuẩn với relation tùy chỉnh của ứng dụng.

Nếu ứng dụng cần một quan hệ riêng không có trong IANA registry, có thể dùng `LinkRelation.of("...")`. Với ý nghĩa tìm kiếm thông thường, hãy ưu tiên relation chuẩn `search`.

### 2.2. Tìm link theo relation

Các representation model của Spring HATEOAS lưu link trong `RepresentationModel`. Client có thể tìm link:

~~~java
Link search = model.getRequiredLink(IanaLinkRelations.SEARCH);
~~~

Nếu link có thể không tồn tại:

~~~java
Optional<Link> search = model.getLink(IanaLinkRelations.SEARCH);

search.ifPresent(link -> {
    // Xử lý khả năng tìm kiếm được công bố.
});
~~~

Có thể kiểm tra sự hiện diện trước:

~~~java
if (model.hasLink(IanaLinkRelations.SEARCH)) {
    Link search = model.getRequiredLink(IanaLinkRelations.SEARCH);
}
~~~

Các API thường dùng:

| API | Ý nghĩa |
|---|---|
| `getLink(IanaLinkRelations.SEARCH)` | Trả về `Optional<Link>` |
| `getRequiredLink(IanaLinkRelations.SEARCH)` | Trả link hoặc báo lỗi nếu thiếu |
| `hasLink(IanaLinkRelations.SEARCH)` | Kiểm tra representation có search link hay không |
| `Link.hasRel(IanaLinkRelations.SEARCH)` | Kiểm tra relation của một link |

Client nên xử lý trường hợp link không có mặt. Search có thể không khả dụng trong một ngữ cảnh, với một trạng thái tài nguyên hoặc đối với một người dùng cụ thể.

## 3. Tạo search link trỏ đến endpoint

Giả sử API có collection sản phẩm và endpoint tìm kiếm:

~~~java
@RestController
@RequestMapping("/products")
class ProductController {

    @GetMapping
    CollectionModel<EntityModel<ProductRepresentation>> all() {
        // Trả về collection sản phẩm.
        // ...
    }

    @GetMapping("/search")
    CollectionModel<EntityModel<ProductRepresentation>> search(
            @RequestParam("q") String query,
            @RequestParam(required = false) String category) {
        // Tìm kiếm theo từ khóa và danh mục.
        // ...
    }
}
~~~

Có thể tạo link trỏ đến endpoint search:

~~~java
Link search = linkTo(
    methodOn(ProductController.class).search(null, null)
).withRel(IanaLinkRelations.SEARCH);
~~~

Link có relation `search` và href đến mapping của phương thức `search`.

Các import tĩnh:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

`methodOn(...)` tạo proxy để link builder phân tích mapping. Các tham số thông thường của method invocation không tự động trở thành query template variables; ngoại lệ quan trọng là các giá trị được dùng làm `@PathVariable`. Vì vậy, nếu muốn công bố các query parameter mà client tự điền, cần bổ sung URI template variables một cách tường minh.

### 3.1. Tạo search link có query variables

Dùng `UriTemplate` và `TemplateVariable.requestParameter(...)` để công bố các biến tìm kiếm:

~~~java
URI searchUri = linkTo(
    methodOn(ProductController.class).search(null, null)
).toUri();

UriTemplate searchTemplate = UriTemplate.of(searchUri.toString())
    .with(TemplateVariable.requestParameter("q"))
    .with(TemplateVariable.requestParameter("category"));

Link search = Link.of(
    searchTemplate,
    IanaLinkRelations.SEARCH
).withTitle("Search products");
~~~

Href có dạng:

~~~text
/products/search{?q,category}
~~~

Các import:

~~~java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

`linkTo(methodOn(...))` lấy URI từ mapping thực tế của controller. Sau đó `UriTemplate` thêm các query variable mà client được phép cung cấp.

### 3.2. Thêm search link vào collection representation

Có thể gắn search link vào `CollectionModel`:

~~~java
CollectionModel<EntityModel<ProductRepresentation>> model =
    CollectionModel.of(products)
        .add(
            Link.of(
                UriTemplate.of("/products/search")
                    .with(TemplateVariable.requestParameter("q"))
                    .with(TemplateVariable.requestParameter("category")),
                IanaLinkRelations.SEARCH
            ).withTitle("Search products")
        );
~~~

Trong ứng dụng thực tế, nên lấy URI gốc từ controller mapping thay vì lặp chuỗi path. Ví dụ trên làm rõ cấu trúc link và relation.

Khi serialize thành HAL, representation có thể có dạng:

~~~json
{
  "_links": {
    "self": {
      "href": "/products"
    },
    "search": {
      "href": "/products/search{?q,category}",
      "templated": true,
      "title": "Search products"
    }
  },
  "_embedded": {
    "product": []
  }
}
~~~

Tên relation `search` xuất hiện trong `_links`. Đây là điểm mà client có thể khám phá để bắt đầu tìm kiếm.

## 4. URI template mô tả cách cung cấp tiêu chí tìm kiếm

Search relation chỉ công bố ngữ nghĩa của link. URI template cung cấp tên biến để client điền vào href.

Ví dụ:

~~~text
/products/search{?q,category,available}
~~~

Các biến:

| Biến | Ý nghĩa trong API ví dụ |
|---|---|
| `q` | Từ khóa tìm kiếm |
| `category` | Danh mục cần giới hạn |
| `available` | Chỉ lấy sản phẩm còn hàng |

Khi client cung cấp:

~~~java
Map<String, Object> parameters = Map.of(
    "q", "spring",
    "category", "books",
    "available", true
);

Link expanded = search.expand(parameters);
~~~

Href sau khi mở rộng có dạng:

~~~text
/products/search?q=spring&category=books&available=true
~~~

Import:

~~~java
import java.util.Map;
~~~

`Link.expand(Map)` tạo link mới với các giá trị được thay vào template. Các query variable tùy chọn không được cung cấp sẽ không xuất hiện trong URI mở rộng.

### 4.1. Tìm kiếm chỉ với từ khóa

Client có thể chỉ gửi `q`:

~~~java
Link expanded = search.expand(Map.of("q", "spring"));
~~~

Href có dạng:

~~~text
/products/search?q=spring
~~~

Các bộ lọc không được cung cấp sẽ bị bỏ qua. API cần quy định rõ cách xử lý khi chỉ có từ khóa, chỉ có bộ lọc hoặc không có tiêu chí nào.

### 4.2. Mã hóa giá trị tìm kiếm

Không nên nối chuỗi query thủ công:

~~~java
String href = "/products/search?q=" + query;
~~~

Từ khóa có thể chứa dấu cách, dấu tiếng Việt, dấu `&`, dấu `+` hoặc ký tự cần percent-encoding. Dùng URI template expansion để các giá trị được xử lý theo quy tắc URI.

Ví dụ từ khóa `spring & hateoas` không được làm dấu `&` trở thành dấu phân cách của một query parameter mới. Hãy kiểm thử cả dữ liệu Unicode và ký tự đặc biệt mà API cho phép.

### 4.3. URI template không tự mô tả toàn bộ search contract

Template cho biết tên các biến và cách đưa chúng vào URI. Nó không nhất thiết mô tả kiểu dữ liệu của từng biến, giá trị hợp lệ, cách kết hợp các điều kiện, quy tắc phân tích từ khóa, cách xếp hạng kết quả, cấu trúc response và pagination.

Nếu client cần những thông tin đó, hãy bổ sung affordance metadata, tài liệu API, profile hoặc một search description document phù hợp.

## 5. Công bố search link từ controller

Một controller có thể tạo collection model và thêm search link:

~~~java
@RestController
@RequestMapping("/products")
class ProductController {

    private final ProductService service;
    private final ProductModelAssembler assembler;

    ProductController(
            ProductService service,
            ProductModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<ProductRepresentation>> all() {

        var products = service.findAll().stream()
            .map(assembler::toModel)
            .toList();

        Link self = linkTo(methodOn(ProductController.class).all())
            .withSelfRel();

        URI searchUri = linkTo(
            methodOn(ProductController.class).search(null, null)
        ).toUri();

        Link search = Link.of(
            UriTemplate.of(searchUri.toString())
                .with(TemplateVariable.requestParameter("q"))
                .with(TemplateVariable.requestParameter("category")),
            IanaLinkRelations.SEARCH
        ).withTitle("Search products");

        return CollectionModel.of(products, self, search);
    }

    @GetMapping("/search")
    CollectionModel<EntityModel<ProductRepresentation>> search(
            @RequestParam("q") String query,
            @RequestParam(required = false) String category) {

        var products = service.search(query, category).stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(products);
    }
}
~~~

Các import cho controller (không bao gồm các kiểu service và model của ứng dụng):

~~~java
import java.net.URI;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Đoạn code thể hiện các trách nhiệm:

1. `all()` trả về collection resource.
2. Link `self` xác định collection hiện tại.
3. URI của search endpoint được lấy từ mapping `search(...)`.
4. `UriTemplate` công bố query variable `q` và `category`.
5. `IanaLinkRelations.SEARCH` gắn ngữ nghĩa chuẩn cho link.
6. Client có thể tìm link bằng relation `search` và mở rộng nó.

Các kiểu `ProductService`, `ProductModelAssembler` và `ProductRepresentation` thuộc ứng dụng. Ví dụ tập trung vào việc tạo và công bố search relation.

### 5.1. Tách search endpoint khỏi collection endpoint

Trong một API, collection endpoint có thể trả danh sách mặc định hoặc các tài nguyên hiện tại; search endpoint thực hiện truy vấn theo tiêu chí.

Có thể thiết kế:

| Endpoint | Trách nhiệm |
|---|---|
| `GET /products` | Đọc collection mặc định |
| `GET /products/search?q=...` | Tìm sản phẩm theo từ khóa |
| `GET /products/{id}` | Đọc một sản phẩm |

Không bắt buộc phải có path `/search` riêng. Một API có thể dùng cùng collection URI với query parameter, chẳng hạn `GET /products?q=spring`. Search relation chỉ cần trỏ đến URI phù hợp với thiết kế API.

Điều quan trọng là target và query template phải khớp với endpoint thực tế.

### 5.2. Search theo trạng thái tài nguyên

Search link có thể được công bố theo ngữ cảnh hoặc quyền của người dùng. Ví dụ collection sản phẩm công khai có search link chung, trong khi một collection quản trị có thể công bố thêm bộ lọc nội bộ.

Server có thể quyết định link nào được đưa vào representation dựa trên trạng thái tài nguyên và quyền của người dùng hiện tại. Tuy nhiên, việc không công bố link không thay thế kiểm tra quyền ở endpoint tìm kiếm. Server vẫn phải xác thực quyền trên mỗi request.

## 6. Search relation và OpenSearch Description Document

Một trường hợp phổ biến của relation `search` là trỏ đến OpenSearch Description Document (OSDD). Tài liệu này mô tả search engine, URL template, định dạng kết quả và một số metadata của dịch vụ tìm kiếm.

Khi target là OSDD, link thường có các thuộc tính:

- `rel="search"`.
- `type="application/opensearchdescription+xml"`.
- `title` mô tả search engine.
- `href` trỏ đến tài liệu XML mô tả tìm kiếm.

Trong Spring HATEOAS:

~~~java
Link openSearchDescription = Link.of(
    "/opensearch.xml",
    IanaLinkRelations.SEARCH
).withType("application/opensearchdescription+xml")
 .withTitle("Product search");
~~~

`withType(...)` đặt media type gợi ý của tài nguyên đích. Ở đây giá trị đó mô tả tài liệu XML mà client sẽ tải từ `/opensearch.xml`; nó không phải `Content-Type` của representation collection hiện tại.

Link này vẫn dùng search relation, nhưng target là tài liệu mô tả search engine chứ không phải trực tiếp endpoint trả kết quả.

### 6.1. OSDD và search endpoint là hai tài nguyên khác nhau

| Thành phần | Vai trò |
|---|---|
| Search relation link đến endpoint | Cho client địa chỉ thực hiện tìm kiếm |
| Search relation link đến OSDD | Cho client địa chỉ tải mô tả search service |
| OSDD | Mô tả search URL template và định dạng kết quả |
| Search endpoint | Nhận tiêu chí tìm kiếm và trả kết quả |

Không phải mọi search link đều phải trỏ đến OSDD. Một API hypermedia có thể công bố trực tiếp URI template của endpoint tìm kiếm. Dùng OSDD khi muốn tương thích với client và công cụ hiểu OpenSearch.

### 6.2. Ví dụ discovery trong HTML

OpenSearch thường sử dụng phần tử link trong HTML head để công bố OSDD:

~~~html
<link
    rel="search"
    type="application/opensearchdescription+xml"
    title="Product search"
    href="/opensearch.xml" />
~~~

Đây là cách discovery của HTML. Trong representation Spring HATEOAS, cùng ngữ nghĩa relation có thể được biểu diễn trong `_links` của HAL.

## 7. Search relation khác gì với các relation khác?

Một số relation có thể xuất hiện gần search trong API nhưng có ý nghĩa khác nhau.

| Relation | Ý nghĩa |
|---|---|
| `search` | Tài nguyên đích có thể dùng để tìm kiếm trong ngữ cảnh hiện tại và tài nguyên liên quan |
| `self` | Định danh tài nguyên hiện tại |
| `collection` | Trỏ đến collection resource chứa tài nguyên hiện tại |
| `item` | Trỏ đến một thành viên của collection |
| `next` | Trỏ đến tài nguyên tiếp theo trong một chuỗi |
| `related` | Trỏ đến tài nguyên có liên quan |
| `create-form` | Trỏ đến tài nguyên cung cấp form tạo mới |
| `edit-form` | Trỏ đến tài nguyên cung cấp form chỉnh sửa |

Search relation không phải relation pagination. Một search link có thể trả về collection được phân trang, nhưng link `next` mới mô tả trang tiếp theo trong chuỗi kết quả.

Search relation cũng không đồng nghĩa với affordance POST. Nếu API cần mô tả thao tác POST với request body phức tạp, hãy dùng affordance để công bố HTTP method và input metadata; relation `search` vẫn có thể được dùng để định danh ngữ nghĩa của tài nguyên tìm kiếm nếu phù hợp với hợp đồng.

## 8. Client khám phá và sử dụng search relation

Client không nên hard-code path `/products/search`. Thay vào đó, client đọc representation và tìm link theo relation.

Ví dụ:

~~~java
CollectionModel<EntityModel<ProductRepresentation>> model = // response đã đọc

Link search = model.getRequiredLink(IanaLinkRelations.SEARCH);

Map<String, Object> parameters = Map.of(
    "q", "spring",
    "category", "books"
);

Link requestLink = search.expand(parameters);
URI searchUri = requestLink.toUri();
~~~

Các import:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
~~~

Trong một client thực tế, bước tiếp theo là gửi HTTP GET đến URI đã mở rộng bằng HTTP client phù hợp. Spring HATEOAS cung cấp hỗ trợ client như Traverson và LinkDiscoverer để làm việc với representation hypermedia.

### 8.1. Xử lý khi search relation không có mặt

Không phải mọi representation đều cần có search link. Ví dụ:

- Tài nguyên không hỗ trợ tìm kiếm liên quan.
- Người dùng hiện tại không có quyền tìm kiếm.
- Một trạng thái nghiệp vụ chưa cho phép thao tác.
- Search service tạm thời không khả dụng và server không công bố link.

Client nên dùng `getLink(...)` để xử lý trường hợp không có link:

~~~java
model.getLink(IanaLinkRelations.SEARCH)
    .ifPresent(search -> {
        // Hiển thị chức năng tìm kiếm nếu có link.
    });
~~~

Không nên giả định link luôn tồn tại hoặc tự tạo URL thay thế khi link vắng mặt.

### 8.2. Client không cần biết controller

Một client hypermedia chỉ cần hiểu:

- Relation `search` có nghĩa gì.
- Link có phải URI template hay không.
- Các biến nào có thể mở rộng.
- Media type và định dạng response mà API công bố.

Client không cần biết tên class controller, route nội bộ hoặc cách server tổ chức service. Đây là lợi ích quan trọng của việc sử dụng relation chuẩn và link động.

## 9. Kiểm thử search relation

Kiểm thử nên xác nhận relation chuẩn, URI template và biến tìm kiếm được công bố.

### 9.1. Unit test cho relation và template

~~~java
@Test
void createsSearchLinkWithQueryVariables() {

    Link search = Link.of(
        UriTemplate.of("/products/search")
            .with(TemplateVariable.requestParameter("q"))
            .with(TemplateVariable.requestParameter("category")),
        IanaLinkRelations.SEARCH
    );

    assertThat(search.getRel().isSameAs(IanaLinkRelations.SEARCH))
        .isTrue();

    assertThat(search.isTemplated()).isTrue();

    assertThat(search.getVariableNames())
        .containsExactly("q", "category");
}
~~~

Import:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

import static org.assertj.core.api.Assertions.assertThat;
~~~

Kiểm thử này bảo đảm relation không bị đổi thành chuỗi tùy chỉnh và client có thể khám phá đúng query variable.

### 9.2. Unit test cho mở rộng link

~~~java
@Test
void expandsSearchLink() {

    Link search = Link.of(
        UriTemplate.of("/products/search")
            .with(TemplateVariable.requestParameter("q"))
            .with(TemplateVariable.requestParameter("category")),
        IanaLinkRelations.SEARCH
    );

    Link expanded = search.expand(Map.of(
        "q", "spring",
        "category", "books"
    ));

    assertThat(expanded.isTemplated()).isFalse();
    assertThat(expanded.getRel().isSameAs(IanaLinkRelations.SEARCH))
        .isTrue();
    assertThat(expanded.getHref())
        .contains("q=spring")
        .contains("category=books");
}
~~~

Kiểm thử này xác nhận link sau khi mở rộng vẫn giữ relation `search` và chứa các giá trị query mong muốn.

### 9.3. Kiểm thử search link trong HAL response

~~~java
mvc.perform(get("/products")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(containsString("/products/search{?q,category}")));
~~~

Import:

~~~java
import org.springframework.hateoas.MediaTypes;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Nếu ứng dụng tạo absolute URI, hãy kiểm tra phần path và template thay vì so sánh toàn bộ href với một chuỗi tương đối cố định.

### 9.4. Kiểm thử endpoint tìm kiếm

Kiểm thử link không chứng minh endpoint thực hiện truy vấn đúng. Cần có test riêng cho endpoint:

~~~java
mvc.perform(get("/products/search")
        .param("q", "spring")
        .param("category", "books")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
~~~

Kiểm thử response collection nên xác nhận dữ liệu kết quả, pagination và các link tiếp theo nếu endpoint có hỗ trợ. Kiểm thử search relation bảo vệ discovery; kiểm thử endpoint bảo vệ hành vi tìm kiếm.

## 10. Những lưu ý khi thiết kế search contract

### 10.1. Đặt tên relation và query variable đúng vai trò

Dùng relation `search` để biểu thị ngữ nghĩa tìm kiếm. Dùng query variable như `q`, `category`, `sort` hoặc `page` để mô tả đầu vào cụ thể.

Không nên đặt relation thành `searchByCategory` chỉ để thể hiện một filter. Có thể dùng một search link duy nhất với nhiều query variable nếu API hỗ trợ nhiều tiêu chí.

### 10.2. Công bố chính xác các biến được hỗ trợ

Nếu URI template có `q` và `category`, endpoint cần thực sự nhận và xử lý hai biến đó. Không công bố biến mà server bỏ qua hoặc chưa triển khai.

Khi search contract thay đổi, hãy cập nhật đồng bộ controller, link template và contract test.

### 10.3. Xác định rõ ngữ nghĩa truy vấn

Tài liệu API nên giải thích:

- `q` tìm trên những trường nào.
- Các filter kết hợp bằng AND hay OR.
- Tìm kiếm có phân biệt hoa thường hay dấu tiếng Việt hay không.
- Có hỗ trợ prefix, phrase hoặc full-text search hay không.
- Kết quả được sắp xếp theo tiêu chí nào.
- Pagination và giới hạn số kết quả hoạt động ra sao.

Relation `search` không định nghĩa những quy tắc nghiệp vụ này.

### 10.4. Bảo vệ search endpoint

Search endpoint nhận đầu vào từ client. Server cần:

- Kiểm tra độ dài từ khóa.
- Giới hạn số filter và kích thước trang.
- Allowlist trường có thể tìm hoặc sắp xếp.
- Tránh đưa trực tiếp tên trường client gửi vào SQL hoặc JPQL.
- Áp dụng phân quyền cho tập dữ liệu được tìm.
- Giới hạn chi phí truy vấn và chống lạm dụng.

Việc công bố search link không làm cho endpoint trở thành endpoint công khai không cần xác thực.

### 10.5. Chọn GET hay POST theo đặc điểm truy vấn

GET phù hợp với truy vấn có tham số gọn, không làm thay đổi trạng thái server và có thể biểu diễn trong URI. Nó cũng hỗ trợ caching và chia sẻ URL theo chính sách phù hợp.

Nếu bộ lọc quá lớn, có cấu trúc lồng nhau hoặc chứa dữ liệu không phù hợp để đưa vào URI, có thể thiết kế endpoint POST cho truy vấn. Khi đó, cần mô tả input bằng affordance hoặc một cơ chế form/schema phù hợp. Search relation vẫn chỉ định ngữ nghĩa tìm kiếm; nó không tự quy định method.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng chuỗi relation tùy ý cho tìm kiếm | Client không nhận ra relation chuẩn | Dùng `IanaLinkRelations.SEARCH` |
| Coi search relation là URL cố định | Client phụ thuộc vào route nội bộ | Công bố link từ mapping hoặc URI template |
| Nghĩ relation tự mô tả query parameter | Client không biết gửi tiêu chí nào | Thêm URI template hoặc affordance metadata |
| Nghĩ `methodOn` tự tạo query variables | Link thiếu các biến query mong muốn | Bổ sung `TemplateVariable.requestParameter(...)` |
| Coi search link là search result | Client không biết phải gọi endpoint | Phân biệt target search và response kết quả |
| Dùng `related` thay cho `search` | Mất ngữ nghĩa tìm kiếm chuẩn | Chọn relation theo ý nghĩa target |
| Nhầm search relation với `next` | Sai điều hướng pagination | Dùng relation pagination cho trang kế tiếp |
| Coi search link là cơ chế phân quyền | Endpoint vẫn có thể bị gọi trực tiếp | Kiểm tra quyền tại server |
| Công bố query variable không được xử lý | Client gửi truy vấn vô hiệu | Đồng bộ template với controller |
| Không kiểm thử relation sau serialize | Link có thể bị mất hoặc sai rel | Kiểm thử HAL response và relation |

## 12. Quy trình triển khai search relation

Khi thêm search relation vào một hypermedia API, hãy thực hiện theo trình tự:

1. Xác định tài nguyên hiện tại và phạm vi dữ liệu có thể tìm kiếm.
2. Chọn endpoint hoặc search description resource làm target.
3. Dùng `IanaLinkRelations.SEARCH` để tạo relation chuẩn.
4. Nếu client cần tự cung cấp tiêu chí, công bố URI template variables.
5. Lấy URI từ controller mapping bằng `WebMvcLinkBuilder` khi có thể.
6. Đặt tên query variable và định nghĩa ngữ nghĩa của từng biến.
7. Gắn search link vào `RepresentationModel` hoặc `CollectionModel` thích hợp.
8. Kiểm tra quyền và giới hạn truy vấn ở endpoint.
9. Kiểm thử relation, href, template variables và response serialization.
10. Kiểm thử riêng endpoint và kết quả tìm kiếm.
11. Cập nhật contract test khi search behavior hoặc query contract thay đổi.

## 13. Kết luận

Search relation là một link relation chuẩn IANA cho biết tài nguyên đích có thể được dùng để tìm kiếm trong ngữ cảnh tài nguyên hiện tại và các tài nguyên liên quan. Spring HATEOAS cung cấp `IanaLinkRelations.SEARCH` để tạo link có ngữ nghĩa thống nhất. Khi kết hợp với `UriTemplate` và `TemplateVariable.requestParameter(...)`, server có thể công bố các query variable để client mở rộng link bằng `Link.expand(...)`.

Relation chỉ mô tả mục đích của liên kết. API vẫn phải định nghĩa HTTP method, query contract, cách xử lý tìm kiếm và cấu trúc kết quả. Khi client khám phá link theo relation chuẩn, mở rộng template và theo các link tiếp theo trong response, client giảm phụ thuộc vào URL nội bộ và có thể tiến hóa cùng hợp đồng hypermedia của server.

## Tài liệu tham khảo

- [IANA Link Relation Registry](https://www.iana.org/assignments/link-relations): định nghĩa relation `search` và các relation chuẩn khác.
- [Spring HATEOAS Reference — Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links.link-relations): sử dụng relation chuẩn và `IanaLinkRelations`.
- [Spring HATEOAS Reference — URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates): URI template variables và mở rộng link.
- [Spring HATEOAS API — IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html): hằng số `SEARCH` và `SEARCH_VALUE`.
- [Spring HATEOAS API — Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html): tạo link từ `UriTemplate`, đặt relation và mở rộng link.
- [MDN — OpenSearch description format](https://developer.mozilla.org/en-US/docs/Web/XML/Guides/OpenSearch): discovery link và định dạng OpenSearch Description Document.

