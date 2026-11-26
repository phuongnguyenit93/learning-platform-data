# Link cho filtering

Trong REST API, filtering thường được thực hiện bằng các query parameter trên một collection resource. Ví dụ, client có thể yêu cầu danh sách sản phẩm thuộc danh mục `books`, có giá từ 100 đến 500, hoặc chỉ lấy những sản phẩm còn hàng. Spring HATEOAS giúp công bố các link đến collection và mô tả các tham số lọc để client có thể khám phá cách truy vấn mà không phải tự ghép URL.

Một link filtering có thể trỏ đến kết quả tìm kiếm hiện tại, chẳng hạn `/products?category=books&available=true`. Link cũng có thể là URI template để client tự điền bộ lọc, chẳng hạn `/products{?category,minPrice,maxPrice,available}`. Trường hợp thứ hai đặc biệt hữu ích khi client cần biết collection hỗ trợ những tiêu chí lọc nào.

Bài học này tập trung vào cách xây dựng hai dạng link đó bằng Spring HATEOAS: dùng `WebMvcLinkBuilder` để tạo URL có query parameter thực tế từ controller mapping, và dùng `UriTemplate` cùng `TemplateVariable` để công bố link filtering có thể mở rộng. Nội dung cũng trình bày cách xử lý bộ lọc nhiều giá trị, cách kiểm thử link và những lưu ý khi thiết kế query contract.

Sau bài học, bạn có thể:

- Giải thích vai trò của link filtering trong hypermedia API.
- Phân biệt link đến kết quả đã lọc với link template cho phép client tự lọc.
- Tạo link đến controller method có `@RequestParam`.
- Dùng `UriTemplate` và `TemplateVariable.requestParameter(...)` để công bố query variable.
- Mở rộng link template bằng `Link.expand(...)`.
- Hiểu cách Spring HATEOAS biểu diễn collection-valued request parameter.
- Dùng `@NonComposite` khi muốn biểu diễn danh sách bằng dấu phẩy.
- Kiểm thử href, variable names và link được serialize.
- Thiết kế query parameter ổn định, an toàn và dễ tiến hóa.

## 1. Filtering trong collection resource

Filtering là cách giới hạn tập kết quả của một collection theo tiêu chí do client cung cấp. Ví dụ một API sản phẩm có endpoint:

~~~http
GET /products
~~~

Client có thể yêu cầu một tập con:

~~~http
GET /products?category=books&available=true
~~~

Hoặc giới hạn khoảng giá:

~~~http
GET /products?minPrice=100&maxPrice=500
~~~

Các tham số nằm trong query string vì chúng mô tả cách truy vấn collection. Chúng không định danh một tài nguyên con như path variable `/products/42`.

Một controller Spring MVC có thể khai báo các bộ lọc:

~~~java
@RestController
@RequestMapping("/products")
class ProductController {

    @GetMapping
    CollectionModel<EntityModel<ProductRepresentation>> search(
            @RequestParam(required = false) String category,
            @RequestParam(required = false) BigDecimal minPrice,
            @RequestParam(required = false) BigDecimal maxPrice,
            @RequestParam(required = false) Boolean available) {
        // Tìm sản phẩm theo các tiêu chí đã cung cấp.
        // ...
    }
}
~~~

Các tham số được đánh dấu `required = false` vì client có thể chỉ gửi một vài tiêu chí hoặc không gửi bộ lọc nào. Server cần định nghĩa rõ ý nghĩa của từng tham số và cách kết hợp chúng, ví dụ các điều kiện được kết hợp bằng AND.

Các import liên quan:

~~~java
import java.math.BigDecimal;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
~~~

### 1.1. Vì sao nên công bố link filtering?

Nếu client phải tự đoán endpoint và query parameter, client cần biết trước:

- Collection nằm ở URI nào.
- Tên các query parameter được hỗ trợ.
- Giá trị nào có thể gửi.
- Tham số nào là tùy chọn.
- Cách truyền danh sách nhiều giá trị.

Một link hypermedia giúp server công bố điểm truy cập cho collection. URI template có thể công bố cả những biến query mà client có thể mở rộng. Khi mapping thay đổi, server cập nhật link được tạo từ controller; client tiếp tục theo link được công bố thay vì tự xây URL.

Ví dụ một representation collection có link:

~~~json
{
  "_links": {
    "self": {
      "href": "/products"
    },
    "search": {
      "href": "/products{?category,minPrice,maxPrice,available}",
      "templated": true
    }
  }
}
~~~

`self` trỏ đến collection hiện tại. `search` cho biết client có thể cung cấp các tiêu chí lọc qua query string.

### 1.2. Filtering khác với pagination và sorting

Filtering quyết định bản ghi nào được đưa vào kết quả. Pagination chia kết quả thành các trang; sorting xác định thứ tự các bản ghi.

Một API thường kết hợp các nhóm tham số:

| Nhóm | Ví dụ query parameter | Mục đích |
|---|---|---|
| Filtering | `category`, `available`, `minPrice` | Giới hạn tập kết quả |
| Sorting | `sort`, `direction` | Sắp xếp kết quả |
| Pagination | `page`, `size` | Chia kết quả thành trang |

Có thể công bố tất cả trên cùng một URI template nếu collection hỗ trợ chúng. Tuy nhiên, cần đặt tên và quy tắc riêng cho từng nhóm để client không nhầm tiêu chí lọc với cách phân trang hoặc sắp xếp.

## 2. Hai dạng link cho filtering

Khi xây dựng API, cần phân biệt link đến một truy vấn cụ thể và link template cho truy vấn có thể tùy chỉnh.

### 2.1. Link đến kết quả đã lọc

Nếu server đang trả về kết quả theo bộ lọc hiện tại, có thể công bố link self chứa các giá trị đã áp dụng:

~~~json
{
  "_links": {
    "self": {
      "href": "/products?category=books&available=true"
    },
    "search": {
      "href": "/products{?category,minPrice,maxPrice,available}",
      "templated": true
    }
  }
}
~~~

`self` mô tả collection đang được biểu diễn, bao gồm ngữ cảnh lọc hiện tại. `search` cho phép client tạo một truy vấn khác.

Điều này giúp client biết kết quả hiện tại đến từ bộ lọc nào và có thể bắt đầu một truy vấn mới bằng link được công bố.

### 2.2. Link template cho bộ lọc

URI template sử dụng cú pháp theo RFC 6570. Phần `{?...}` biểu thị các query parameter có thể được mở rộng.

Ví dụ:

~~~text
/products{?category,minPrice,maxPrice,available}
~~~

Khi client điền:

~~~text
category = books
minPrice = 100
available = true
~~~

URI có thể được mở rộng thành:

~~~text
/products?category=books&minPrice=100&available=true
~~~

Những biến không được cung cấp sẽ bị bỏ khỏi query string. Đây là hành vi phù hợp với bộ lọc tùy chọn.

Trong Spring HATEOAS, `Link` có thể giữ URI template, cho biết link có được template hóa hay không và cung cấp API để mở rộng nó.

## 3. Tạo link có query parameter từ controller method

`WebMvcLinkBuilder` giúp xây dựng link dựa trên mapping của Spring MVC. Khi method có tham số được đánh dấu `@RequestParam`, Spring HATEOAS có thể dùng giá trị tham số để tạo query string.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/products")
class ProductController {

    @GetMapping
    CollectionModel<EntityModel<ProductRepresentation>> search(
            @RequestParam(required = false) String category,
            @RequestParam(required = false) BigDecimal minPrice,
            @RequestParam(required = false) BigDecimal maxPrice) {
        // ...
    }
}
~~~

Tạo link đến kết quả đã lọc:

~~~java
Link filteredProducts = linkTo(
    methodOn(ProductController.class).search(
        "books",
        new BigDecimal("100"),
        new BigDecimal("500")
    )
).withRel("search");
~~~

Link được xây dựng từ mapping của controller và các giá trị query đã cung cấp. Với mapping ở ví dụ, href có dạng:

~~~text
/products?category=books&minPrice=100&maxPrice=500
~~~

Các import tĩnh:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

`methodOn(...)` tạo một proxy ghi nhận lời gọi method để link builder phân tích mapping. Nó không thực thi logic tìm kiếm trong controller.

### 3.1. Tham số tùy chọn không có giá trị

Giả sử client chỉ lọc theo danh mục:

~~~java
Link books = linkTo(
    methodOn(ProductController.class).search(
        "books",
        null,
        null
    )
).withRel("search");
~~~

Các tham số `minPrice` và `maxPrice` được để trống vì client không áp dụng hai tiêu chí đó. Với query parameter tùy chọn, hãy xác nhận href được tạo không chứa các khóa lọc không có giá trị; không dùng chuỗi rỗng để thay cho việc bỏ một bộ lọc.

Ví dụ href mong đợi:

~~~text
/products?category=books
~~~

Hãy dùng `@RequestParam` rõ ràng cho các tham số query. Những tham số method không được Spring MVC nhận diện là path variable hoặc request parameter không nên được kỳ vọng sẽ tự động trở thành query parameter.

### 3.2. Dùng link builder thay vì ghép chuỗi URL

Không nên tạo link bằng cách nối chuỗi:

~~~java
String href = "/products?category=" + category
    + "&minPrice=" + minPrice;
~~~

Cách làm này dễ tạo URI sai khi giá trị chứa dấu cách, dấu `&`, dấu `+`, ký tự Unicode hoặc ký tự cần percent-encoding. Nó cũng lặp lại mapping `/products` ngoài controller.

Dùng `WebMvcLinkBuilder` giúp lấy mapping từ controller và dùng cơ chế URI của Spring để xử lý tham số. Nếu phải xây dựng URI thủ công, hãy dùng API URI builder hoặc URI template thay vì nối chuỗi.

## 4. Tạo URI template bằng UriTemplate và TemplateVariable

Một link đến kết quả cụ thể chỉ thể hiện các giá trị đã chọn. Nếu muốn client tự chọn bộ lọc, hãy công bố query variable.

Spring HATEOAS cung cấp:

- `UriTemplate`: biểu diễn một URI template.
- `TemplateVariable`: biểu diễn một biến trong URI template.
- `TemplateVariable.requestParameter(...)`: tạo biến query parameter.
- `Link.of(UriTemplate, relation)`: tạo link từ URI template và link relation.

Ví dụ tạo link search cho collection sản phẩm:

~~~java
UriTemplate template = UriTemplate.of("/products")
    .with(TemplateVariable.requestParameter("category"))
    .with(TemplateVariable.requestParameter("minPrice"))
    .with(TemplateVariable.requestParameter("maxPrice"))
    .with(TemplateVariable.requestParameter("available"));

Link search = Link.of(template, "search");
~~~

Link này có href dạng:

~~~text
/products{?category,minPrice,maxPrice,available}
~~~

Các import:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;
~~~

`TemplateVariable.requestParameter(...)` tạo biến dành cho query string. Dùng nó cho các tiêu chí lọc tùy chọn, chẳng hạn category, khoảng giá hoặc trạng thái tồn kho.

### 4.1. Lấy URI collection từ mapping của controller

Ví dụ trên dùng đường dẫn `/products` để tập trung vào cú pháp template. Trong ứng dụng, có thể lấy URI gốc từ controller mapping rồi bổ sung biến:

~~~java
URI productsUri = linkTo(ProductController.class).toUri();

UriTemplate template = UriTemplate.of(productsUri.toString())
    .with(TemplateVariable.requestParameter("category"))
    .with(TemplateVariable.requestParameter("minPrice"))
    .with(TemplateVariable.requestParameter("maxPrice"));

Link search = Link.of(template, "search");
~~~

Import bổ sung:

~~~java
import java.net.URI;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
~~~

Cách này giữ đường dẫn collection đồng bộ với `@RequestMapping` của controller. Nếu mapping thay đổi, link builder sử dụng mapping mới mà code không phải sửa chuỗi URI ở nhiều nơi.

### 4.2. Đưa link filtering vào representation

Có thể thêm link template vào `CollectionModel`:

~~~java
CollectionModel<EntityModel<ProductRepresentation>> model =
    CollectionModel.of(products)
        .add(search);
~~~

Hoặc thêm link vào một representation model riêng:

~~~java
public class ProductCatalogModel
        extends RepresentationModel<ProductCatalogModel> {

    private final List<ProductRepresentation> products;

    public ProductCatalogModel(List<ProductRepresentation> products) {
        this.products = products;
    }

    public List<ProductRepresentation> getProducts() {
        return products;
    }
}
~~~

Sau đó:

~~~java
ProductCatalogModel model = new ProductCatalogModel(products);
model.add(search);
~~~

Các import cho model:

~~~java
import java.util.List;

import org.springframework.hateoas.RepresentationModel;
~~~

Client có thể đọc relation `search`, kiểm tra href là URI template và hiển thị những tiêu chí lọc tương ứng.

## 5. Mở rộng link template bằng Link.expand

Khi có một `Link` được template hóa, client hoặc code server có thể mở rộng các biến bằng `Link.expand(...)`.

Ví dụ:

~~~java
Link search = Link.of(
    UriTemplate.of("/products")
        .with(TemplateVariable.requestParameter("category"))
        .with(TemplateVariable.requestParameter("minPrice"))
        .with(TemplateVariable.requestParameter("available")),
    "search"
);

Map<String, Object> filters = Map.of(
    "category", "books",
    "minPrice", 100,
    "available", true
);

Link filtered = search.expand(filters);
~~~

Href sau khi mở rộng có dạng:

~~~text
/products?category=books&minPrice=100&available=true
~~~

Các import:

~~~java
import java.util.Map;
~~~

`Link.expand(Map)` giữ relation của link và thay các biến bằng giá trị được cung cấp. Các biến query tùy chọn không được cung cấp sẽ không xuất hiện trong URI đã mở rộng.

Có thể kiểm tra link trước khi mở rộng:

~~~java
assertThat(search.isTemplated()).isTrue();
assertThat(search.getVariableNames())
    .contains("category", "minPrice", "available");
~~~

Và kiểm tra kết quả:

~~~java
assertThat(filtered.isTemplated()).isFalse();
assertThat(filtered.getHref())
    .contains("category=books")
    .contains("minPrice=100")
    .contains("available=true");
~~~

### 5.1. Giá trị cần được encode đúng

Không nên tự encode giá trị trước khi truyền cho `expand(...)` nếu không có yêu cầu đặc biệt. URI template expansion chịu trách nhiệm áp dụng quy tắc encode tương ứng.

Ví dụ category có giá trị `home & garden`. Nếu nối chuỗi trực tiếp, dấu `&` có thể bị hiểu là dấu phân cách query parameter. Khi mở rộng template, giá trị được encode như một giá trị query, tránh biến một phần nội dung thành tham số khác.

Hãy kiểm thử những giá trị có dấu cách, dấu tiếng Việt, dấu `&`, dấu `+` và ký tự đặc biệt mà API cho phép.

## 6. Filtering với tham số có nhiều giá trị

Một tiêu chí lọc đôi khi nhận nhiều giá trị. Ví dụ client muốn lấy sản phẩm thuộc một trong các tag `new` hoặc `sale`.

Controller:

~~~java
@GetMapping
CollectionModel<EntityModel<ProductRepresentation>> search(
        @RequestParam(required = false) List<String> tags) {
    // ...
}
~~~

Theo cách biểu diễn composite mặc định, một collection-valued query parameter được lặp tên cho từng giá trị:

~~~text
/products?tags=new&tags=sale
~~~

Spring MVC có thể parse định dạng này thành một collection.

### 6.1. Dùng @NonComposite cho danh sách phân tách bằng dấu phẩy

Nếu API muốn dùng dạng:

~~~text
/products?tags=new,sale
~~~

hãy đánh dấu tham số bằng `@NonComposite`:

~~~java
@GetMapping
CollectionModel<EntityModel<ProductRepresentation>> search(
        @NonComposite
        @RequestParam(required = false)
        Collection<String> tags) {
    // ...
}
~~~

Import:

~~~java
import java.util.Collection;

import org.springframework.hateoas.NonComposite;
import org.springframework.web.bind.annotation.RequestParam;
~~~

Khi tạo link từ controller method, Spring HATEOAS dùng cách biểu diễn không composite đã khai báo:

~~~java
List<String> tags = List.of("new", "sale");

Link tagSearch = linkTo(
    methodOn(ProductController.class).search(tags)
).withRel("search");
~~~

Href có dạng:

~~~text
/products?tags=new,sale
~~~

Nếu không dùng `@NonComposite`, Spring HATEOAS mặc định tạo dạng lặp tham số. Cả hai định dạng đều có thể được Spring MVC parse; hãy chọn một dạng nhất quán trong API và kiểm thử client thực tế.

### 6.2. Query variable cho một tham số collection

Với URI template, một biến query có thể được mở rộng bằng một collection:

~~~java
Link search = Link.of(
    UriTemplate.of("/products")
        .with(TemplateVariable.requestParameter("tags")),
    "search"
);

Link expanded = search.expand(
    Map.of("tags", List.of("new", "sale"))
);
~~~

Cách serialize giá trị collection phụ thuộc loại template variable và quy tắc composite. Nếu hợp đồng yêu cầu danh sách phân tách bằng dấu phẩy, hãy xác định rõ quy tắc này ở controller bằng `@NonComposite` và kiểm thử href được sinh ra.

## 7. Phân biệt URI template và affordance query parameter

Spring HATEOAS có hai abstraction dễ bị nhầm:

- `TemplateVariable` mô tả biến trong URI template của một link.
- `QueryParameter` mô tả query parameter của một affordance được xây dựng bằng API `Affordances`.

Với link filtering thông thường, `UriTemplate` và `TemplateVariable.requestParameter(...)` là đủ để công bố URI có thể mở rộng.

Nếu cần mô tả một thao tác cụ thể như GET search trong affordance, có thể dùng `QueryParameter.optional(...)` khi xây affordance thủ công:

~~~java
Link search = Affordances.of(Link.of("/products", "products"))
    .afford(HttpMethod.GET)
    .withOutput(ProductSearchResult.class)
    .addParameters(
        QueryParameter.optional("category"),
        QueryParameter.optional("minPrice"),
        QueryParameter.optional("maxPrice")
    )
    .withName("searchProducts")
    .toLink();
~~~

Các import:

~~~java
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;
~~~

`QueryParameter` thuộc mô hình affordance, cho phép media type hỗ trợ affordance chuyển metadata thao tác thành biểu diễn phù hợp. Nó không thay thế URI template của link thông thường.

Không cần thêm affordance chỉ để tạo một link search đơn giản. Chỉ dùng khi API cần mô tả chi tiết khả năng thao tác, ví dụ kết hợp method, input/output metadata và query parameter.

## 8. Tổ chức link filtering trong collection response

Một response collection thường cần ít nhất link self và link search. Ví dụ:

~~~java
@GetMapping
CollectionModel<EntityModel<ProductRepresentation>> search(
        @RequestParam(required = false) String category,
        @RequestParam(required = false) BigDecimal minPrice,
        @RequestParam(required = false) BigDecimal maxPrice) {

    List<EntityModel<ProductRepresentation>> products =
        service.search(category, minPrice, maxPrice).stream()
            .map(assembler::toModel)
            .toList();

    Link self = linkTo(
        methodOn(ProductController.class)
            .search(category, minPrice, maxPrice)
    ).withSelfRel();

    Link searchTemplate = Link.of(
        UriTemplate.of(linkTo(ProductController.class).toUri().toString())
            .with(TemplateVariable.requestParameter("category"))
            .with(TemplateVariable.requestParameter("minPrice"))
            .with(TemplateVariable.requestParameter("maxPrice")),
        "search"
    );

    return CollectionModel.of(products, self, searchTemplate);
}
~~~

Đoạn code minh họa hai mục đích:

- `self` phản ánh truy vấn hiện tại cùng các filter đã áp dụng.
- `search` là template để client tạo truy vấn khác.

Nếu ứng dụng có nhiều filter, nên đóng gói phần tạo template thành một phương thức hoặc component riêng để controller không phải lặp danh sách query variable. Danh sách variable phải đồng bộ với query contract mà endpoint thực sự hỗ trợ.

## 9. Kiểm thử link filtering

Kiểm thử link cần xác nhận URI template chứa đúng tên biến và link cụ thể giữ đúng giá trị query.

### 9.1. Unit test cho URI template

~~~java
@Test
void exposesOptionalProductFilters() {

    UriTemplate template = UriTemplate.of("/products")
        .with(TemplateVariable.requestParameter("category"))
        .with(TemplateVariable.requestParameter("minPrice"))
        .with(TemplateVariable.requestParameter("available"));

    Link search = Link.of(template, "search");

    assertThat(search.isTemplated()).isTrue();
    assertThat(search.getVariableNames())
        .containsExactly("category", "minPrice", "available");
}
~~~

Import:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

import static org.assertj.core.api.Assertions.assertThat;
~~~

Kiểm thử này xác nhận link công bố đúng tập biến mà client có thể điền.

### 9.2. Unit test cho mở rộng filter

~~~java
@Test
void expandsOnlyProvidedFilterValues() {

    Link search = Link.of(
        UriTemplate.of("/products")
            .with(TemplateVariable.requestParameter("category"))
            .with(TemplateVariable.requestParameter("minPrice"))
            .with(TemplateVariable.requestParameter("available")),
        "search"
    );

    Link filtered = search.expand(Map.of(
        "category", "books",
        "available", true
    ));

    assertThat(filtered.getHref())
        .contains("category=books")
        .contains("available=true")
        .doesNotContain("minPrice");
}
~~~

Kiểm thử chứng minh biến không được cung cấp không xuất hiện trong query string sau khi mở rộng.

### 9.3. Kiểm thử link được serialize trong response

Với HAL, link template thường được biểu diễn bằng `href` và cờ `templated`:

~~~java
mvc.perform(get("/products")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(containsString("{?category,minPrice,maxPrice}")));
~~~

Import kiểm thử:

~~~java
import org.springframework.hateoas.MediaTypes;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Tùy cấu trúc representation và media type, đường dẫn JSONPath có thể khác. Hãy kiểm tra đúng relation và cấu trúc response mà API công bố.

### 9.4. Kiểm thử link có giá trị filter hiện tại

Khi response đang phản ánh một truy vấn cụ thể, kiểm thử self link:

~~~java
mvc.perform(get("/products")
        .param("category", "books")
        .param("available", "true")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(containsString("category=books")))
    .andExpect(jsonPath("$._links.self.href")
        .value(containsString("available=true")));
~~~

Điều này giúp phát hiện trường hợp response trả kết quả đã lọc nhưng self link lại bỏ mất một tiêu chí.

## 10. Những lưu ý khi thiết kế query contract

### 10.1. Dùng tên query parameter ổn định

Tên filter là một phần hợp đồng mà client sử dụng. Nên chọn tên dễ hiểu và giữ ổn định, chẳng hạn `category`, `minPrice`, `maxPrice`, `available`.

Không nên đổi tên tùy tiện theo tên biến nội bộ hoặc tên cột database. Nếu cần thay đổi, hãy cân nhắc khả năng tương thích và thời gian hỗ trợ client cũ.

### 10.2. Không công bố filter mà endpoint không hỗ trợ

URI template phải phản ánh chính xác các query parameter mà endpoint nhận. Nếu template công bố `supplier` nhưng controller không có tham số tương ứng hoặc không xử lý nó, client sẽ gửi request không có tác dụng.

Có thể duy trì một danh sách filter contract dùng chung cho controller, link assembler và kiểm thử để giảm sai lệch.

### 10.3. Kiểm tra kiểu và miền giá trị

Query parameter thường đến từ bên ngoài dưới dạng chuỗi. Spring MVC chuyển đổi sang kiểu Java, nhưng server vẫn cần kiểm tra quy tắc nghiệp vụ.

Ví dụ:

- `minPrice` không được âm.
- `maxPrice` không được nhỏ hơn `minPrice`.
- `available` chỉ nhận boolean hợp lệ.
- `category` phải thuộc danh mục được phép.
- Danh sách tag cần có giới hạn số phần tử.

Có thể dùng Bean Validation cho request parameter khi cấu hình method validation phù hợp, hoặc kiểm tra trong service. Metadata trong link không thay thế validation.

### 10.4. Tránh công bố tên thuộc tính nội bộ tùy ý

Nếu cho client gửi tên trường để lọc động như `sortBy=...` hoặc `filterField=...`, server cần allowlist các trường được phép. Không chuyển trực tiếp giá trị query thành tên cột SQL, biểu thức JPQL hoặc thuộc tính reflection.

Link hypermedia công bố khả năng lọc được hỗ trợ; nó không nên mở ra một truy vấn tùy ý vào mô hình dữ liệu nội bộ.

### 10.5. Encoding và giới hạn độ dài

Giá trị filter có thể chứa Unicode, dấu cách hoặc ký tự đặc biệt. Dùng URI template expansion hoặc URI builder để encode đúng.

Server cũng nên giới hạn:

- Độ dài query string.
- Số lượng filter được phép.
- Số giá trị trong collection-valued parameter.
- Độ dài từng giá trị.
- Chi phí truy vấn và thời gian thực thi.

Một client có thể mở rộng template với rất nhiều giá trị; server cần kiểm soát request như với mọi đầu vào khác.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Ghép query string bằng nối chuỗi | Sai encoding hoặc sai dấu phân cách | Dùng `WebMvcLinkBuilder`, `UriTemplate` hoặc URI builder |
| Dùng link tĩnh khi client cần tự chọn filter | Client phải tự đoán tên query parameter | Công bố URI template |
| Công bố URI template không khớp controller | Client gửi filter không được xử lý | Đồng bộ template và query contract |
| Nhầm query parameter với path variable | URI không đúng cấu trúc endpoint | Dùng `TemplateVariable.requestParameter(...)` |
| Dùng `methodOn` với tham số không có annotation phù hợp | Giá trị không xuất hiện như mong đợi | Khai báo `@RequestParam` rõ ràng |
| Không xử lý tham số null | Query string chứa giá trị không hợp lệ hoặc không mong muốn | Định nghĩa filter là optional và bỏ giá trị rỗng |
| Không nhất quán cách truyền collection | Client và server parse khác nhau | Chọn composite hoặc `@NonComposite` |
| Dùng `QueryParameter` thay cho URI template ở mọi trường hợp | Nhầm metadata affordance với link template | Chọn abstraction theo nhu cầu |
| Không kiểm tra self link | Link không phản ánh bộ lọc đang áp dụng | Kiểm thử URI self theo request |
| Cho phép tên filter tùy ý | Rủi ro truy vấn vượt phạm vi | Dùng allowlist và validation |

## 12. Quy trình triển khai link filtering

Khi thêm link filtering vào một collection resource, hãy thực hiện theo trình tự:

1. Xác định collection endpoint và các query parameter được hỗ trợ.
2. Khai báo `@RequestParam` rõ ràng trong controller.
3. Xác định giá trị nào bắt buộc và giá trị nào tùy chọn.
4. Tạo self link bằng `WebMvcLinkBuilder` để phản ánh bộ lọc hiện tại.
5. Tạo link template bằng `UriTemplate` và `TemplateVariable.requestParameter(...)`.
6. Gắn link vào `CollectionModel` hoặc representation model phù hợp.
7. Nếu query nhận collection, chọn định dạng composite hoặc `@NonComposite`.
8. Kiểm tra encoding và giá trị mở rộng bằng `Link.expand(...)`.
9. Kiểm thử href, variable names, self link và response serialization.
10. Đồng bộ query contract với validation, quyền truy cập và giới hạn truy vấn.

## 13. Kết luận

Link filtering giúp client khám phá cách truy vấn collection resource thông qua hypermedia. Với Spring HATEOAS, `WebMvcLinkBuilder` có thể tạo link đến một truy vấn cụ thể dựa trên controller mapping và các giá trị `@RequestParam`. Khi muốn client tự lựa chọn tiêu chí lọc, `UriTemplate` kết hợp `TemplateVariable.requestParameter(...)` tạo link có query variable; `Link.expand(...)` chuyển template thành URI cụ thể.

Hãy giữ query contract nhất quán với controller, xử lý đúng bộ lọc tùy chọn và collection-valued parameter, dùng URI API để encode dữ liệu và kiểm thử cả link template lẫn self link. Link công bố khả năng lọc mà server hỗ trợ, giúp client điều hướng và tạo truy vấn mà không phải tự ghép cấu trúc URL.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — URI templates](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.uri-templates): URI template, biến query và mở rộng link.
- [Spring HATEOAS Reference — Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder.mvc): tạo link từ controller method và request parameter.
- [Spring HATEOAS Reference — Controlling the rendering of request parameters](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder.mvc.request-parameters): cách biểu diễn collection-valued request parameter và `@NonComposite`.
- [Spring HATEOAS API — TemplateVariable](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/TemplateVariable.html): tạo request parameter template variable.
- [Spring HATEOAS API — UriTemplate](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html): tạo, mở rộng và truy xuất biến của URI template.
- [Spring HATEOAS API — Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html): tạo link từ URI template và mở rộng link.

