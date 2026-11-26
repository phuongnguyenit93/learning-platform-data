# Relation item

Một resource có thể đại diện cho cả một collection, ví dụ danh mục sản phẩm, danh sách đơn hàng hoặc nhóm bài viết. Client thường cần khám phá từng thành viên của collection để mở trang chi tiết, đọc dữ liệu hoặc tiếp tục điều hướng. IANA định nghĩa relation `item` để diễn đạt chính xác mối quan hệ đó: khi được đặt trong representation của một collection, link `item` trỏ tới một resource là thành viên của collection ấy.

Relation đối ứng là `collection`. Khi được đặt trong representation của một thành viên, link `collection` trỏ tới resource đại diện cho collection chứa thành viên đó. Hai relation này được định nghĩa trong RFC 6573 và được đăng ký trong IANA Link Relations Registry. Spring HATEOAS cung cấp `IanaLinkRelations.ITEM` và `IanaLinkRelations.COLLECTION` để sử dụng các relation chuẩn này trong Java.

Bài học này thuộc chương **IANA relation** trong module **SPRING_HATEOAS**, tập trung vào semantics của relation `item`, cách phân biệt nó với `self`, `collection` và các relation khác, cách tạo link item trong Spring HATEOAS, cách client đọc nhiều link cùng relation và cách kiểm thử HAL representation.

Sau bài học, bạn có thể:

- Giải thích chính xác semantics của registered relation `item` theo RFC 6573.
- Phân biệt hướng liên kết `item` và `collection`.
- Nhận diện trường hợp dùng `item` thay vì `self`, `related` hoặc relation tùy chỉnh.
- Tạo link bằng `IanaLinkRelations.ITEM` trong Spring HATEOAS.
- Hiểu cách nhiều link cùng relation được biểu diễn trong HAL.
- Phân biệt relation `item` với tên collection trong `_embedded` và `@Relation`.
- Xây dựng client theo relation và `href` thay vì hard-code URL.
- Kiểm thử link item và collection bằng MockMvc/JSONPath.

## 1. Semantics của relation item

RFC 6573 định nghĩa `item` như sau: khi được đưa vào một resource đại diện cho collection, relation `item` xác định một target resource đại diện cho một thành viên của collection đó.

Ví dụ một danh mục sản phẩm:

```text
Catalog resource: /catalogs/7
    item -> /products/42
    item -> /products/43
    item -> /products/44
```

Trong representation của `/catalogs/7`, mỗi link có relation `item` trỏ tới một sản phẩm thuộc danh mục. Client có thể theo link để mở tài nguyên chi tiết mà không cần biết quy tắc tạo URL `/products/{id}`.

Điều quan trọng là `item` mô tả quan hệ giữa context resource và target resource. Nó không phải tên endpoint, không bắt buộc target phải có path dạng `/items/{id}` và cũng không quy định HTTP method dùng để thao tác với target.

Một collection resource có thể công bố một hoặc nhiều link `item`. RFC 6573 không yêu cầu phải công bố mọi thành viên trong cùng một representation. Ví dụ một trang kết quả có thể chỉ chứa link tới các thành viên thuộc trang hiện tại; các trang tiếp theo được khám phá qua relation pagination như `next`.

## 2. Quan hệ đối ứng collection

`collection` là relation đối ứng với `item`. Khi context resource đại diện cho một thành viên, link `collection` xác định target resource đại diện cho collection mà thành viên đó thuộc về.

Ví dụ representation của một sản phẩm:

```json
{
  "id": 42,
  "sku": "KB-042",
  "name": "Bàn phím cơ",
  "_links": {
    "self": {
      "href": "https://api.example.com/products/42"
    },
    "collection": {
      "href": "https://api.example.com/catalogs/7",
      "title": "Thiết bị ngoại vi"
    }
  }
}
```

Ở đây resource hiện tại là sản phẩm số 42. Link `self` trỏ tới chính sản phẩm; link `collection` trỏ tới danh mục chứa sản phẩm.

Một resource có thể thuộc nhiều collection. Ví dụ một sản phẩm vừa thuộc danh mục “Thiết bị ngoại vi”, vừa thuộc danh mục “Sản phẩm đang giảm giá”. Khi đó representation của sản phẩm có thể chứa nhiều link cùng relation `collection`, mỗi link trỏ tới một collection khác nhau.

Target của `collection` không bắt buộc phải là một danh sách có thể duyệt trực tiếp. RFC 6573 cho phép target là tài liệu cung cấp thông tin về collection mà context resource thuộc về.

Hai chiều có thể tóm tắt như sau:

| Context resource | Relation | Target resource |
|---|---|---|
| Collection `/catalogs/7` | `item` | Thành viên `/products/42` |
| Thành viên `/products/42` | `collection` | Collection `/catalogs/7` |

Không phải collection nào cũng cần link ngược từ mọi item. Chỉ công bố `collection` khi quan hệ đó có ý nghĩa và client cần điều hướng trở lại collection.

## 3. Phân biệt item, self và related

Các relation có thể cùng xuất hiện trong một representation nhưng diễn đạt ý nghĩa khác nhau:

| Relation | Ngữ nghĩa | Ví dụ |
|---|---|---|
| `self` | URI của chính resource đang được biểu diễn. | Representation danh mục trỏ tới `/catalogs/7`. |
| `item` | Target là một thành viên của collection context. | Danh mục trỏ tới `/products/42`. |
| `collection` | Target là collection mà context member thuộc về. | Sản phẩm trỏ về `/catalogs/7`. |
| `related` | Target là resource có liên quan, không khẳng định quan hệ thành viên collection. | Đơn hàng trỏ tới hồ sơ hỗ trợ liên quan. |

Không dùng `item` chỉ vì target là một object hoặc một record. Nếu resource hiện tại không đại diện cho collection, semantics `item` có thể không phù hợp. Tương tự, không dùng `related` khi quan hệ thành viên collection đã được xác định rõ và relation chuẩn `item` diễn đạt chính xác hơn.

Ví dụ representation danh mục:

```json
{
  "id": 7,
  "name": "Thiết bị ngoại vi",
  "_links": {
    "self": {
      "href": "https://api.example.com/catalogs/7"
    },
    "item": [
      { "href": "https://api.example.com/products/42" },
      { "href": "https://api.example.com/products/43" }
    ],
    "related": {
      "href": "https://api.example.com/recommendations/catalogs/7"
    }
  }
}
```

Hai link `item` trỏ tới các thành viên của danh mục. Link `related` trỏ tới một tài nguyên có liên quan nhưng không phải thành viên của danh mục.

## 4. item là relation chuẩn, không phải extension relation

`item` đã được đăng ký trong IANA Link Relations Registry theo RFC 6573. Vì vậy, khi semantics phù hợp, nên dùng relation chuẩn thay vì tự định nghĩa một relation như `product`, `catalogEntry` hoặc `member` cho cùng ý nghĩa.

Trong Spring HATEOAS, dùng hằng `IanaLinkRelations.ITEM`:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link itemLink = Link.of("/products/42", IanaLinkRelations.ITEM);
```

Relation đối ứng cũng có hằng tương ứng:

```java
Link collectionLink = Link.of("/catalogs/7", IanaLinkRelations.COLLECTION);
```

Sử dụng constant giúp tránh lỗi chính tả và thể hiện rõ đây là relation chuẩn. `LinkRelation.of("item")` cũng có thể tạo một giá trị relation, nhưng `IanaLinkRelations.ITEM` diễn đạt ý định sử dụng registered relation rõ hơn.

Relation chuẩn không làm URI đích trở thành một endpoint đặc biệt. Server vẫn kiểm soát route, representation và quyền truy cập của target resource.

## 5. Tạo link item trong Spring HATEOAS

Giả sử ứng dụng có controller cho danh mục và sản phẩm:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    EntityModel<ProductResponse> one(@PathVariable("id") Long id) {
        ProductResponse product = productService.findResponseById(id);
        return EntityModel.of(product);
    }
}
```

Để tạo link item dựa trên mapping controller, dùng `WebMvcLinkBuilder`:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link item = linkTo(methodOn(ProductController.class).one(42L))
        .withRel(IanaLinkRelations.ITEM);
```

`methodOn` mô tả method đích để Spring HATEOAS phân tích mapping; nó không thực thi logic truy vấn sản phẩm. `withRel(IanaLinkRelations.ITEM)` gắn semantics `item` cho link.

## 6. Thêm nhiều item link vào collection representation

Một resource đại diện cho collection có thể công bố nhiều link `item`. Ví dụ một danh mục hiển thị các sản phẩm thuộc trang hiện tại:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

List<EntityModel<ProductResponse>> products = productService.findFeatured().stream()
        .map(productAssembler::toModel)
        .toList();

CollectionModel<EntityModel<ProductResponse>> catalog =
        CollectionModel.of(products,
                linkTo(methodOn(CatalogController.class).one(7L)).withSelfRel());

catalog.add(
        linkTo(methodOn(ProductController.class).one(42L))
                .withRel(IanaLinkRelations.ITEM),
        linkTo(methodOn(ProductController.class).one(43L))
                .withRel(IanaLinkRelations.ITEM)
);
```

Ví dụ giả định `CatalogController.one(7L)` trả representation của danh mục và `ProductController.one(id)` trả representation của sản phẩm. `CollectionModel` chứa các representation được nhúng; các link `item` được thêm ở cấp collection để công bố rõ các URI thành viên.

Nếu mỗi embedded `EntityModel` đã có `self` link, client cũng có thể khám phá URI từng sản phẩm từ `_embedded`. Việc thêm `item` link riêng có thể hữu ích khi API muốn công bố quan hệ thành viên một cách tường minh hoặc khi không nhúng toàn bộ item representation. Tránh tạo hai nguồn link không nhất quán; cả embedded item và item link phải trỏ tới cùng tài nguyên.

## 7. HAL biểu diễn nhiều link item như thế nào?

Trong HAL, tên relation trở thành key bên dưới `_links`. Khi một collection công bố nhiều link cùng relation `item`, giá trị relation được biểu diễn thành mảng link object:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/catalogs/7"
    },
    "item": [
      {
        "href": "https://api.example.com/products/42",
        "title": "Bàn phím cơ"
      },
      {
        "href": "https://api.example.com/products/43",
        "title": "Chuột không dây"
      }
    ]
  }
}
```

Nếu chỉ có một link `item`, Spring HATEOAS mặc định tuần tự hóa relation đó thành một link object đơn. Khi có nhiều link cùng relation, serializer dùng array. Vì vậy, client tổng quát nên xử lý cả hai dạng.

Nếu ứng dụng cần luôn biểu diễn link đơn dưới dạng array, có thể cấu hình `HalConfiguration` với `RenderSingleLinks.AS_ARRAY`. Đây là chính sách serialization của HAL, không thay đổi semantics của relation `item`. Chỉ thay đổi chính sách khi client có hợp đồng rõ ràng và đã được kiểm thử.

## 8. Đọc item link ở phía client

Client nên tìm relation `item` trong `_links`, chuẩn hóa giá trị thành danh sách rồi theo từng `href`:

```javascript
function getLinksByRelation(document, relation) {
  const value = document?._links?.[relation];

  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

async function loadCatalogItems(catalogDocument) {
  const itemLinks = getLinksByRelation(catalogDocument, "item");

  return Promise.all(itemLinks.map(async link => {
    const response = await fetch(link.href, {
      headers: { Accept: "application/hal+json" }
    });

    if (!response.ok) {
      throw new Error(`Không tải được item: HTTP ${response.status}`);
    }

    return response.json();
  }));
}
```

Client không cần biết target resource được lưu trong bảng nào hoặc URL được tạo từ ID ra sao. Nó chỉ cần biết `item` có nghĩa là thành viên collection và dùng `href` do server công bố.

Nếu collection đã nhúng representation trong `_embedded`, client có thể dùng embedded data ngay và chỉ theo item link khi cần tải bản đầy đủ hoặc làm mới tài nguyên. Tránh tải lại toàn bộ item nếu dữ liệu đã có và còn đủ mới cho use case.

## 9. item không có nghĩa là toàn bộ thành viên collection

Một collection representation có thể chỉ công bố một tập con link `item`. Ví dụ:

- Trang hiện tại có 20 sản phẩm trong collection lớn.
- Danh mục chỉ hiển thị các sản phẩm nổi bật.
- Client chưa có quyền xem một số thành viên.
- Server chỉ công bố các item phù hợp với filter hiện tại.

Do đó, client không nên suy luận rằng danh sách link `item` trong một response luôn là toàn bộ thành viên của collection. Nếu collection được phân trang, client cần theo các relation pagination như `next`, `prev`, `first`, `last`. Nếu API có filter hoặc search, hãy sử dụng affordance/link được công bố cho truy vấn tương ứng.

Relation `item` cũng không xác định thứ tự sắp xếp. Nếu thứ tự có ý nghĩa, representation cần thể hiện thứ tự trong embedded collection hoặc thông qua metadata/contract phù hợp. Client không nên sắp xếp lại item chỉ dựa vào URI.

## 10. item và collection có thể xuất hiện nhiều lần

Một collection có thể có nhiều item link. Ngược lại, một item có thể thuộc nhiều collection, nên representation của item có thể có nhiều link `collection`.

RFC 6573 cũng cho phép một target link có đồng thời relation `item` và `collection` nếu target vừa là thành viên của collection context, vừa tự đại diện cho một collection. Ví dụ một danh mục con là một item của danh mục cha, đồng thời có các item riêng:

```http
Link: </catalogs/7/subcatalogs/3>; rel="item collection"
```

Điều này không có nghĩa hai relation luôn phải đi cùng nhau. Chỉ công bố nhiều relation trên cùng link khi tất cả semantics đều đúng với context và target resource.

Trong HAL, relation có thể được biểu diễn thành các key riêng hoặc nhiều giá trị relation theo cách serializer hỗ trợ. Khi cần công bố hai relation cho cùng target, hãy kiểm tra JSON output thực tế và bảo đảm client có thể nhận diện đúng cả hai ý nghĩa.

## 11. Phân biệt item link với embedded relation trong HAL

HAL có hai cơ chế thường bị nhầm lẫn:

- `_links.item`: relation chuẩn IANA, link tới một resource là thành viên của collection.
- `_embedded.products`: một hoặc nhiều representation được nhúng dưới relation `products`.

Ví dụ:

```json
{
  "_links": {
    "self": { "href": "/catalogs/7" },
    "item": [
      { "href": "/products/42" },
      { "href": "/products/43" }
    ]
  },
  "_embedded": {
    "products": [
      { "id": 42, "name": "Bàn phím cơ" },
      { "id": 43, "name": "Chuột không dây" }
    ]
  }
}
```

`item` mô tả quan hệ giữa collection và từng target URI. `products` dưới `_embedded` là tên relation được dùng để nhóm các representation nhúng. Hai cơ chế có thể cùng xuất hiện nhưng không đồng nghĩa và không bắt buộc phải dùng cùng tên.

## 12. `@Relation` không khai báo IANA item link

Spring HATEOAS có annotation `@Relation` để tùy chỉnh tên relation của resource khi nhúng vào HAL. Ví dụ:

```java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "product", collectionRelation = "products")
public record ProductResponse(Long id, String name) {
}
```

`itemRelation = "product"` và `collectionRelation = "products"` điều khiển tên dùng cho representation đơn và collection trong ngữ cảnh `_embedded`. Chúng không tự động tạo link có relation IANA `item` trong `_links`.

Nếu cần link tới một thành viên collection, hãy thêm `Link` với `IanaLinkRelations.ITEM`. Nếu cần đổi tên embedded relation, dùng `@Relation` hoặc `LinkRelationProvider`. Hai cấu hình phục vụ hai mục đích khác nhau.

## 13. Link header và các media type khác

Relation `item` không chỉ dành cho HAL. RFC 6573 định nghĩa relation này như một Web Link Relation có thể sử dụng trong nhiều media type. HTTP Link header có thể công bố item link:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </products/42>; rel="item"; title="Bàn phím cơ"
Link: </products/43>; rel="item"; title="Chuột không dây"
```

Trong HAL, cùng semantics được biểu diễn bên trong `_links`. Trong HTML, relation có thể xuất hiện trên anchor như `rel="item"`. Cú pháp khác nhau nhưng ý nghĩa relation vẫn là target resource là thành viên của collection context.

Điều này cho phép client hiểu semantics `item` xuyên qua nhiều định dạng, miễn là client có hỗ trợ cách biểu diễn link của media type đang dùng.

## 14. Kiểm thử item relation bằng MockMvc

Kiểm thử nên xác nhận relation xuất hiện ở đúng resource, đúng target và đúng media type. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemRelationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void catalogPublishesLinksToItsMemberResources() throws Exception {
        mockMvc.perform(get("/catalogs/7").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("/catalogs/7")))
                .andExpect(jsonPath("$._links.item[0].href")
                        .value(containsString("/products/42")))
                .andExpect(jsonPath("$._links.item[1].href")
                        .value(containsString("/products/43")));
    }

    @Test
    void productPublishesItsContainingCollection() throws Exception {
        mockMvc.perform(get("/products/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("/products/42")))
                .andExpect(jsonPath("$._links.collection.href")
                        .value(containsString("/catalogs/7")));
    }
}
```

Ví dụ giả định fixture danh mục `7` có ít nhất hai sản phẩm `42` và `43`, đồng thời sản phẩm `42` công bố link về danh mục `7`. Nếu response chỉ có một item link, Spring HATEOAS mặc định có thể serialize `$._links.item` thành object thay vì array; khi đó assertion cần đọc object hoặc chuẩn hóa object/array trong test client.

Trong unit test phía server, có thể kiểm tra số link cùng relation trực tiếp trên model:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(catalog.getLinks(IanaLinkRelations.ITEM)).hasSize(2);
```

`getLinks(relation)` trả về tất cả link có relation đó; `getLink(relation)` chỉ phù hợp khi code mong đợi tối đa một link.

Nên bổ sung kiểm thử cho:

- Collection không có item link.
- Collection có đúng một item link.
- Collection có nhiều item link.
- Một item thuộc nhiều collection và có nhiều link `collection`.
- Relation item cùng target URI với self link của embedded resource.
- HAL response có đúng `Content-Type`.
- Người dùng không có quyền truy cập item target.

## 15. Bảo mật và khả năng truy cập item

Một item link giúp client khám phá URI thành viên nhưng không cấp quyền truy cập. Server vẫn phải xác thực và phân quyền tại endpoint target. Không nên công bố link tới resource mà người dùng không được phép nhìn thấy nếu việc tiết lộ URI cũng làm lộ thông tin nhạy cảm.

Khi collection có filter theo tenant hoặc quyền, danh sách item link cần phản ánh phạm vi dữ liệu được phép công bố. Endpoint item vẫn phải kiểm tra quyền độc lập vì client có thể gọi trực tiếp một URI đã biết.

Client cũng nên xem `href` là dữ liệu đến từ server. Nếu link có thể trỏ tới origin bên ngoài, không tự động gửi cookie hoặc bearer token của API hiện tại sang origin đó. Áp dụng chính sách origin và credential phù hợp.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `item` cho mọi liên kết tới object | Relation không phản ánh đúng semantics collection membership. | Chỉ dùng khi context là collection và target là thành viên. |
| Nhầm `item` với `self` | Client hiểu sai URI của resource hiện tại. | `self` trỏ chính resource; `item` trỏ từ collection tới thành viên. |
| Nhầm `collection` với `item` | Hướng điều hướng bị đảo ngược. | Collection dùng `item`; member dùng `collection`. |
| Cho rằng item link phải có path `/items/{id}` | Client bị khóa vào cấu trúc URL. | Dùng bất kỳ URI hợp lệ nào và công bố qua `href`. |
| Giả định `_links.item` luôn là array | Client lỗi khi chỉ có một link. | Hỗ trợ cả object và array. |
| Coi danh sách item link là toàn bộ collection | Client bỏ sót các trang hoặc thành viên bị giới hạn. | Dùng pagination/filter links và không suy diễn tính đầy đủ. |
| Nhầm `@Relation(itemRelation=...)` với IANA `item` | Đổi tên embedded relation nhưng không tạo item link. | Dùng `IanaLinkRelations.ITEM` để tạo link. |
| Nghĩ link item cấp quyền truy cập | Endpoint vẫn có thể bị gọi trực tiếp. | Phân quyền tại target resource. |
| Dùng `related` khi semantics member đã rõ | Client mất ngữ nghĩa chuẩn có thể tái sử dụng. | Ưu tiên registered relation `item`. |

## 17. Quy trình áp dụng relation item

Khi thiết kế link tới các thành viên của một collection, hãy thực hiện theo trình tự:

1. Xác định context resource có thực sự đại diện cho collection hay không.
2. Xác định target resource có phải thành viên của collection đó hay không.
3. Dùng relation chuẩn `item`; trong Spring HATEOAS ưu tiên `IanaLinkRelations.ITEM`.
4. Tạo `href` từ controller mapping, `EntityLinks` hoặc link factory phù hợp.
5. Nếu item cũng cần điều hướng ngược, công bố relation `collection` trong representation của item.
6. Nếu một relation có nhiều target, bảo đảm client xử lý cả object và array trong HAL.
7. Phân biệt item link trong `_links` với embedded relation trong `_embedded`.
8. Giữ pagination/filter links nếu collection chỉ công bố một phần thành viên.
9. Kiểm thử relation, target URI, media type và quyền truy cập.

Relation `item` giúp collection công bố các thành viên bằng một ngữ nghĩa chuẩn và có thể hiểu được xuyên qua nhiều media type. Khi dùng đúng chiều quan hệ, client có thể theo từng `href` mà không phải đoán cấu trúc endpoint, còn server vẫn tự do thay đổi URI và cách tổ chức tài nguyên.

## Tài liệu tham khảo

- [RFC 6573 – The Item and Collection Link Relations](https://www.rfc-editor.org/rfc/rfc6573.html)
- [IANA – Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [Spring HATEOAS – IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS – LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
