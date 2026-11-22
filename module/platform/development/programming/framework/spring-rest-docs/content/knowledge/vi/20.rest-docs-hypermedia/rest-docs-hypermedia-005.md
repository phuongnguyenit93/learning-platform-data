# Content type HAL, Atom và dạng hypermedia khác

## 1. Vì sao Content-Type quan trọng khi document hypermedia?

Spring REST Docs tạo tài liệu REST API từ các HTTP test bằng MockMvc, WebTestClient hoặc REST Assured. Với response có hypermedia links, REST Docs cần biết cách đọc cấu trúc liên kết trong payload. Cùng một ý nghĩa `rel` và `href` có thể được biểu diễn khác nhau tùy định dạng: HAL dùng object `_links` trong JSON, Atom dùng phần tử XML `<link>`, còn những format khác có thể dùng cấu trúc JSON/XML riêng.

HTTP header `Content-Type` cho biết định dạng của response thực tế. Spring REST Docs dùng thông tin này để chọn link extractor phù hợp khi tạo snippet `links.adoc`. Nếu media type không đủ để xác định format, có thể truyền extractor tường minh. Với định dạng riêng, có thể cung cấp một `LinkExtractor` tùy chỉnh.

Ba lựa chọn cần phân biệt:

| Loại response | Media type thường dùng | Vị trí chứa links |
| --- | --- | --- |
| HAL JSON | `application/hal+json` | Object `_links`, mỗi relation ánh xạ tới một link object hoặc danh sách link. |
| Atom | `application/atom+xml` | Các phần tử XML `<link>` bên trong feed hoặc entry. |
| Hypermedia format khác | Media type do format/API định nghĩa | Cấu trúc riêng; cần extractor tương ứng nếu muốn sinh bảng links. |

```mermaid
flowchart TD
    A[HTTP response] --> B[Đọc Content-Type]
    B --> C{Định dạng?}
    C -->|HAL| D[halLinks()]
    C -->|Atom| E[atomLinks()]
    C -->|Khác / không nhận diện| F[LinkExtractor tùy chỉnh]
    D --> G[REST Docs trích xuất rel và href]
    E --> G
    F --> G
    G --> H[links.adoc]
```

Không nên suy luận định dạng chỉ từ tên file, endpoint hoặc phần mở rộng URL. Hãy kiểm tra header response thật và payload mà server trả về.

## 2. HAL: links nằm trong `_links`

HAL (Hypertext Application Language) biểu diễn các liên kết trong thuộc tính `_links` của JSON. Một response HAL đơn giản:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "payment": {
      "href": "/api/orders/42/payment",
      "title": "Thanh toán đơn hàng"
    },
    "next": {
      "href": "/api/orders?page=1"
    }
  }
}
```

Trong HAL:

- `_links` là container của các links.
- Tên key như `self`, `payment`, `next` là relation (`rel`).
- `href` chỉ URI đích; nó có thể là URI tương đối hoặc tuyệt đối.
- Một số link object có thêm `title`, `type`, `hreflang`, `templated`, `deprecation`, `name` hoặc `profile` theo format và hợp đồng API.

Với media type `application/hal+json`, Spring REST Docs có thể sử dụng HAL link extractor. Ví dụ REST Assured:

```java
given(this.specification)
        .accept("application/hal+json")
        .filter(document("orders-get",
                links(
                        linkWithRel("self").description("Đơn hàng hiện tại"),
                        linkWithRel("payment").description("Mở quy trình thanh toán"),
                        linkWithRel("next").description("Trang kết quả kế tiếp"))))
.when()
        .get("/api/orders/42")
.then()
        .statusCode(200)
        .contentType("application/hal+json");
```

Các static import:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
```

Nếu format đã được nhận diện từ Content-Type, có thể dùng `links(...)` trực tiếp. Khi muốn chỉ định rõ extractor hoặc server trả media type không chuẩn nhưng payload vẫn theo HAL, dùng:

```java
links(halLinks(),
        linkWithRel("self").description("Đơn hàng hiện tại"),
        linkWithRel("payment").description("Mở quy trình thanh toán"))
```

`halLinks()` chỉ định cách trích xuất link từ `_links`; nó không thay đổi Content-Type response và không biến một JSON tùy ý thành HAL. Payload vẫn phải tuân theo cấu trúc HAL để extractor đọc đúng.

## 3. Atom: links nằm trong XML elements

Atom là một định dạng syndication XML. Trong Atom feed hoặc entry, link được biểu diễn bằng phần tử `<link>` với các thuộc tính như `rel`, `href`, `type`, `hreflang`, `title` và `length`.

Ví dụ response:

```http
HTTP/1.1 200 OK
Content-Type: application/atom+xml;type=feed;charset=UTF-8
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:example:orders</id>
  <title>Orders</title>
  <updated>2026-11-17T08:00:00Z</updated>
  <link rel="self" href="/api/orders" type="application/atom+xml"/>
  <link rel="next" href="/api/orders?page=1" type="application/atom+xml"/>
  <entry>
    <id>urn:example:orders:42</id>
    <title>Order 42</title>
    <link rel="self" href="/api/orders/42" type="application/atom+xml"/>
  </entry>
</feed>
```

Khi response dùng `application/atom+xml`, Spring REST Docs có thể lựa chọn Atom link extractor theo media type. Có thể gọi rõ:

```java
given(this.specification)
        .accept("application/atom+xml")
        .filter(document("orders-feed",
                links(atomLinks(),
                        linkWithRel("self").description("Feed đơn hàng hiện tại"),
                        linkWithRel("next").description("Trang feed tiếp theo"))))
.when()
        .get("/api/orders")
.then()
        .statusCode(200)
        .contentType("application/atom+xml");
```

Static import bổ sung:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.atomLinks;
```

Atom link extractor đọc các phần tử `<link>` theo cấu trúc Atom, không phải thuộc tính `_links` của HAL. Nếu response thực tế là XML tùy chỉnh không tuân theo Atom, `atomLinks()` không phải lựa chọn phù hợp chỉ vì payload là XML.

Một response Atom có thể có nhiều link cùng relation nhưng khác `hreflang`, `type` hoặc `title`. Hãy đọc raw response snippet để không bỏ qua những biến thể link có ý nghĩa. Snippet `links.adoc` tiêu chuẩn tập trung vào relation và mô tả; nó không thay thế toàn bộ XML response.

## 4. Content-Type và content negotiation

Client có thể gửi header `Accept` để bày tỏ định dạng mong muốn; server chọn representation phù hợp và trả `Content-Type` mô tả định dạng thực tế. Hai header này có vai trò khác nhau:

| Header | Hướng truyền | Ý nghĩa |
| --- | --- | --- |
| `Accept` | Request | Client muốn nhận định dạng nào, ví dụ `application/hal+json` hoặc `application/atom+xml`. |
| `Content-Type` | Response | Server thực sự trả representation theo định dạng nào. |

Không nên chỉ assert `Accept` ở request rồi giả định response là HAL. Hãy xác nhận `Content-Type` thực tế:

```java
given(this.specification)
        .accept("application/hal+json")
.when()
        .get("/api/orders/42")
.then()
        .statusCode(200)
        .contentType("application/hal+json");
```

Nếu server trả `application/json` dù client yêu cầu HAL, có thể endpoint chưa đăng ký HAL converter, chưa bật Spring HATEOAS, hoặc negotiation đang cấu hình khác mong đợi. Không tự ép `halLinks()` để che lỗi server nếu payload thực tế không theo HAL.

Với REST Assured, `.accept(...)` thiết lập request `Accept`. Với MockMvc, dùng `.accept(MediaType.parseMediaType("application/hal+json"))`; với WebTestClient, dùng `.accept(...)` tương ứng. Trong cả ba trường hợp, tài liệu phải phản ánh media type server thực sự trả.

## 5. Các format hypermedia khác: khi nào cần custom `LinkExtractor`?

Không phải mọi response có links đều dùng HAL hoặc Atom. Một số API có thể dùng:

| Format | Ví dụ cách biểu diễn links | Ghi chú |
| --- | --- | --- |
| Collection+JSON | `collection.links` hoặc links trong item | Cấu trúc JSON riêng, không phải HAL `_links`. |
| Siren | Mảng `links` và `actions` | `actions` mô tả thao tác có thể gửi, khác với navigation link đơn thuần. |
| JSON:API | `links` tại top-level/resource/relationship | Link có thể ở nhiều vị trí tùy cấp tài nguyên. |
| UBER hoặc format riêng | Các object/array mô tả link và action | Cần hiểu rõ semantics của format cụ thể. |

Danh sách trên là ví dụ về các định dạng hypermedia khác; không có nghĩa Spring REST Docs tự động nhận diện tất cả. Nếu cấu trúc hoặc Content-Type không nằm trong các loại extractor được tích hợp sẵn, hãy cung cấp `LinkExtractor` phù hợp.

`LinkExtractor` chuyển payload và media type thành một tập link theo relation mà Spring REST Docs có thể sử dụng. Về mặt khái niệm, extractor cần:

1. Nhận nội dung response cùng Content-Type.
2. Parse đúng định dạng (JSON/XML) bằng parser phù hợp.
3. Tìm các link theo quy tắc của format, kể cả link ở resource hoặc relationship lồng nhau nếu cần.
4. Trích relation, href và title (nếu có) thành đối tượng link của Spring REST Docs.
5. Trả kết quả theo cấu trúc map relation tới các link.

Đăng ký extractor trong snippet bằng overload:

```java
links(customLinkExtractor,
        linkWithRel("self").description("Tài nguyên hiện tại"),
        linkWithRel("related").description("Tài nguyên liên quan"))
```

Trong đó `customLinkExtractor` là một implementation của `LinkExtractor` do dự án cung cấp. Không truyền tên format hoặc chuỗi Content-Type thay cho extractor. Cần viết test riêng cho extractor với payload mẫu hợp lệ, payload thiếu link, nhiều link cùng `rel`, URI template và nội dung không hợp lệ.

Không nên dùng regex để parse cấu trúc JSON/XML. Hãy dùng Jackson hoặc XML parser an toàn, hỗ trợ namespace và escaping. Với XML không tin cậy, tránh cấu hình parser cho phép external entity (XXE).

## 6. Ví dụ khái niệm về custom extractor

Giả sử API dùng một JSON format nội bộ:

```json
{
  "resource": { "id": 42 },
  "navigation": [
    { "relation": "self", "url": "/api/resources/42", "label": "Tài nguyên" },
    { "relation": "related", "url": "/api/resources/42/related", "label": "Tài nguyên liên quan" }
  ]
}
```

Khác HAL, format này đặt link dưới `navigation` và dùng key `relation`/`url`/`label`. Một custom `LinkExtractor` cần map:

| JSON key | Ý nghĩa cần trích |
| --- | --- |
| `relation` | Relation name |
| `url` | Href |
| `label` | Title hoặc mô tả link có nguồn từ payload |

Sau khi extractor chuyển các phần tử này thành `Link` của Spring REST Docs, có thể dùng descriptor thông thường:

```java
links(customLinkExtractor,
        linkWithRel("self").description("Tài nguyên hiện tại"),
        linkWithRel("related").description("Tài nguyên liên quan"))
```

Phần code cài đặt cụ thể phụ thuộc signature của `LinkExtractor` ở version Spring REST Docs mà dự án đang dùng. Nên đối chiếu Javadoc đúng version và giữ implementation nhỏ, có unit test. Descriptor `linkWithRel(...)` vẫn kiểm tra relation như với HAL/Atom; chỉ bước trích xuất payload thay đổi.

## 7. Document cùng một API hỗ trợ nhiều representation

Một endpoint có thể hỗ trợ HAL và Atom tùy `Accept`. Khi đó, nên viết các test riêng vì response Content-Type và cấu trúc links khác nhau:

```java
@Test
void documentOrdersAsHal() {
    given(this.specification)
            .accept("application/hal+json")
            .filter(document("orders-hal",
                    links(halLinks(),
                            linkWithRel("self").description("Feed đơn hàng"),
                            linkWithRel("next").description("Trang tiếp theo"))))
    .when()
            .get("/api/orders")
    .then()
            .statusCode(200)
            .contentType("application/hal+json");
}

@Test
void documentOrdersAsAtom() {
    given(this.specification)
            .accept("application/atom+xml")
            .filter(document("orders-atom",
                    links(atomLinks(),
                            linkWithRel("self").description("Feed đơn hàng"),
                            linkWithRel("next").description("Trang tiếp theo"))))
    .when()
            .get("/api/orders")
    .then()
            .statusCode(200)
            .contentType("application/atom+xml");
}
```

Hai test dùng identifier riêng (`orders-hal`, `orders-atom`) để snippet không ghi đè nhau. Descriptor có thể dùng chung nếu API cam kết cùng relation semantics trong cả hai representation. Nếu Atom response có links khác HAL response, tạo descriptor phù hợp riêng.

Khi muốn kiểm chứng payload cụ thể, bổ sung assertion và document response body. Đừng chỉ kiểm tra `Content-Type`: server có thể trả đúng media type nhưng payload thiếu relation mà client cần.

## 8. Kết hợp links snippet với HTTP response và payload

`links.adoc` trình bày relation cùng mô tả; `http-response.adoc` hoặc `response-body.adoc` giữ ví dụ representation thực tế. Với HAL, người đọc cần cả hai để thấy `rel` có ý nghĩa gì và `href`/metadata có giá trị nào. Với Atom, raw XML response cho biết `href`, `type`, `hreflang` hoặc các link lặp theo relation.

Ví dụ Asciidoctor:

```asciidoc
== Orders API - HAL representation

=== HTTP response
include::{snippets}/orders-hal/http-response.adoc[]

=== Link relations
include::{snippets}/orders-hal/links.adoc[]

== Orders API - Atom representation

=== HTTP response
include::{snippets}/orders-atom/http-response.adoc[]

=== Link relations
include::{snippets}/orders-atom/links.adoc[]
```

Thuộc tính `{snippets}` phải trỏ tới đúng output directory của test. Markdown thuần không tự xử lý cú pháp `include::...[]`; nếu dự án dùng Markdown cần bước chuyển đổi hoặc cơ chế nhúng tương ứng.

## 9. Lỗi thường gặp khi xử lý Content-Type và link extractor

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `links.adoc` trống hoặc không có link | Extractor không tìm thấy cấu trúc đúng trong response. | Kiểm tra Content-Type, payload và chọn `halLinks()`/`atomLinks()` hoặc extractor phù hợp. |
| HAL response không được nhận diện | Server trả `application/json` thay vì media type HAL hoặc cấu trúc không phải HAL. | Kiểm tra contract; chỉ dùng `halLinks()` tường minh khi payload thật sự theo HAL. |
| Atom extractor không lấy được links | XML không tuân cấu trúc Atom hoặc có namespace/format riêng. | Kiểm tra `application/atom+xml` và cấu trúc `<feed>`, `<entry>`, `<link>`. |
| Client yêu cầu HAL nhưng server trả Atom | Content negotiation hoặc cấu hình endpoint chưa đúng. | Assert response `Content-Type`, kiểm tra converter và supported media types. |
| Relation có trong response nhưng báo undocumented | Strict `links(...)` chưa mô tả relation đó. | Thêm descriptor, hoặc dùng optional/ignored/relaxed đúng chủ đích. |
| Descriptor có relation nhưng báo không tìm thấy | Payload không chứa relation hoặc extractor không đọc được nó. | Xem raw response; kiểm tra relation name và extractor. |
| Format riêng không sinh snippet | Spring REST Docs chưa có extractor tương ứng. | Viết `LinkExtractor` tùy chỉnh và test độc lập. |
| HAL/Atom table không thể hiện metadata cần thiết | Links snippet tập trung vào rel và description. | Include raw HTTP response/body hoặc viết custom snippet cho metadata. |

## 10. Checklist thực hành

- [ ] Đã xem `Content-Type` của response thật, không suy đoán từ request `Accept`.
- [ ] HAL dùng `application/hal+json` và cấu trúc `_links` phù hợp.
- [ ] Atom dùng `application/atom+xml` và phần tử `<link>` đúng namespace/cấu trúc.
- [ ] Đã chọn `halLinks()` hoặc `atomLinks()` khi cần chỉ định extractor rõ ràng.
- [ ] Format khác có custom `LinkExtractor` được test với nhiều payload đại diện.
- [ ] `links(...)` descriptor mô tả đủ relation quan trọng.
- [ ] Đã giữ `http-response.adoc`/`response-body.adoc` để người đọc thấy href và metadata gốc.
- [ ] Test xác nhận Content-Type và các relation cần thiết.
- [ ] HAL/Atom test dùng identifier riêng nếu cùng endpoint hỗ trợ nhiều representation.
- [ ] Build/CI chỉ biên soạn và publish snippet từ test đã thành công.

HAL và Atom có thể mô tả cùng khái niệm hypermedia link nhưng dùng cấu trúc payload và media type khác nhau. Spring REST Docs cung cấp extractor tích hợp cho các định dạng này; với format riêng, hãy triển khai extractor phù hợp thay vì ép response vào cấu trúc HAL/Atom. Kiểm tra Content-Type, links snippet và raw response cùng nhau giúp tài liệu phản ánh đúng representation mà client thực sự nhận.

## Tài liệu tham khảo

- [Spring REST Docs – Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs – HypermediaDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/HypermediaDocumentation.html)
- [Spring REST Docs – LinkExtractor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/hypermedia/LinkExtractor.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [Atom Syndication Format RFC 4287](https://www.rfc-editor.org/rfc/rfc4287)
