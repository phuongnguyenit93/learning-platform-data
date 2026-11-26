# Thêm link vào model

Trong Spring HATEOAS, một representation model chứa dữ liệu của tài nguyên và các liên kết hypermedia mô tả cách client có thể điều hướng tiếp. Khi thêm link vào model, server công bố những quan hệ như `self`, `products`, `category` hoặc `activate` cùng với URL đích tương ứng. Client đọc quan hệ (`rel`) để hiểu ý nghĩa của liên kết và theo URL (`href`) do server cung cấp.

`RepresentationModel` là lớp cơ sở để tạo representation có liên kết. Các kiểu như `EntityModel` và `CollectionModel` cũng kế thừa cơ chế này, vì vậy có thể dùng cùng cách `add(...)` để gắn link. Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo URL từ mapping của controller, giúp liên kết phản ánh endpoint đang được ứng dụng công bố.

## Cấu trúc của một link

Một link hypermedia có hai thành phần cơ bản:

- `rel` (relation): tên quan hệ, cho biết link dẫn tới đâu hoặc có ý nghĩa gì đối với tài nguyên hiện tại.
- `href`: địa chỉ đích mà client có thể truy cập.

Ví dụ một tài nguyên sản phẩm có thể chứa các quan hệ:

| Relation | Ý nghĩa | Ví dụ đích |
|---|---|---|
| `self` | Chính tài nguyên hiện tại | `/api/products/42` |
| `products` | Tập hợp sản phẩm | `/api/products` |
| `category` | Danh mục của sản phẩm | `/api/categories/7` |
| `reviews` | Các đánh giá liên quan | `/api/products/42/reviews` |
| `activate` | Hướng tương tác kích hoạt sản phẩm | `/api/products/42/activate` |

`self` là quan hệ chuẩn thường có trong representation của một tài nguyên. Những quan hệ như `products`, `category` hoặc `activate` là quan hệ do API lựa chọn; cần đặt tên ổn định và mô tả ngữ nghĩa rõ ràng để client có thể sử dụng lâu dài.

Quan hệ `activate` chỉ nói rằng server công bố một hướng tương tác có ý nghĩa kích hoạt. Bản thân `rel` và `href` trong HAL cơ bản không mô tả đầy đủ HTTP method hay payload của request. Nếu client cần khám phá chi tiết biểu mẫu hoặc dữ liệu đầu vào, API cần công bố affordance bằng media type phù hợp.

## Tạo link từ controller bằng WebMvcLinkBuilder

Spring HATEOAS cung cấp `WebMvcLinkBuilder` để xây dựng URL từ các mapping Spring MVC. Hai phương thức thường dùng là `linkTo(...)` và `methodOn(...)`:

- `methodOn(Controller.class).method(arguments)` tạo tham chiếu tới phương thức controller và cung cấp các tham số đường dẫn cần thiết.
- `linkTo(...)` đọc mapping từ tham chiếu đó để tạo link builder.
- `withSelfRel()` gắn quan hệ `self`.
- `withRel("name")` gắn một quan hệ do API định nghĩa.

Ví dụ, controller có endpoint đọc một sản phẩm:

```java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;
    private final ProductModelAssembler assembler;

    public ProductController(ProductService productService,
                             ProductModelAssembler assembler) {
        this.productService = productService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public ProductModel one(@PathVariable UUID id) {
        Product product = productService.findRequired(id);
        return assembler.toModel(product);
    }

    @GetMapping
    public CollectionModel<ProductModel> all() {
        List<ProductModel> products = productService.findAll().stream()
                .map(assembler::toModel)
                .collect(Collectors.toList());

        return CollectionModel.of(products,
                linkTo(methodOn(ProductController.class).all()).withSelfRel());
    }

    @GetMapping(params = "page")
    public CollectionModel<ProductModel> page(@RequestParam int page) {
        List<ProductModel> products = productService.findPage(page).stream()
                .map(assembler::toModel)
                .collect(Collectors.toList());

        return CollectionModel.of(products,
                linkTo(methodOn(ProductController.class).page(page)).withSelfRel());
    }
}
```

Có thể tạo hai link như sau:

```java
Link self = linkTo(methodOn(ProductController.class).one(productId))
        .withSelfRel();

Link products = linkTo(methodOn(ProductController.class).all())
        .withRel("products");
```

`methodOn(...)` cho phép Spring HATEOAS suy ra đường dẫn từ mapping, thay vì phải nối chuỗi `"/api/products/" + productId`. Khi route được thay đổi, link được tạo từ controller sẽ theo mapping mới. Client cũng không cần phân tích cấu trúc chuỗi URL để suy ra ID hay loại tài nguyên.

### Dùng quan hệ chuẩn

Spring HATEOAS định nghĩa `IanaLinkRelations` cho một số quan hệ chuẩn. Ví dụ, có thể dùng các hằng `SELF`, `NEXT`, `PREV`, `FIRST` và `LAST` khi chúng đúng với ý nghĩa liên kết. Phương thức `page(int page)` trong controller ví dụ ở trên minh họa một endpoint có tham số trang:

```java
import org.springframework.hateoas.IanaLinkRelations;

Link next = linkTo(methodOn(ProductController.class).page(1))
        .withRel(IanaLinkRelations.NEXT);
```

Đối với quan hệ riêng của ứng dụng, dùng tên mô tả rõ nghiệp vụ, chẳng hạn `reviews`, `category` hoặc `activate`. Không nên dùng cùng một tên `rel` cho các ý nghĩa khác nhau giữa những endpoint.

## Thêm link vào EntityModel

`EntityModel<T>` bọc một đối tượng nội dung cùng các liên kết. Đây là lựa chọn thuận tiện khi dữ liệu response đã có trong DTO và chỉ cần bổ sung hypermedia.

```java
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

ProductResponse response = new ProductResponse(
        product.getId(),
        product.getName(),
        product.getPrice()
);

EntityModel<ProductResponse> model = EntityModel.of(response);

model.add(
        linkTo(methodOn(ProductController.class).one(product.getId()))
                .withSelfRel(),
        linkTo(methodOn(ProductController.class).all())
                .withRel("products")
);
```

Phương thức `add(...)` nhận một hoặc nhiều `Link`. Có thể tạo link trước rồi thêm từng link, hoặc thêm nhiều link trong một lần gọi. Model giữ cả nội dung `ProductResponse` và danh sách liên kết để Spring HATEOAS tuần tự hóa thành representation hypermedia.

## Thêm link vào lớp kế thừa RepresentationModel

Khi muốn kiểm soát trực tiếp cấu trúc representation, có thể tạo lớp riêng kế thừa `RepresentationModel<T>`. Tham số generic thường là chính lớp con, ví dụ `RepresentationModel<ProductModel>`.

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;

public class ProductModel extends RepresentationModel<ProductModel> {

    private final UUID id;
    private final String name;
    private final BigDecimal price;

    public ProductModel(UUID id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public UUID getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
```

Sau khi khởi tạo `ProductModel`, có thể gắn link trực tiếp:

```java
ProductModel model = new ProductModel(
        product.getId(),
        product.getName(),
        product.getPrice()
);

model.add(linkTo(methodOn(ProductController.class)
        .one(product.getId())).withSelfRel());

model.add(linkTo(methodOn(ProductController.class)
        .all()).withRel("products"));
```

Vì `ProductModel` kế thừa `RepresentationModel`, nó có sẵn cơ chế lưu và quản lý link. Các trường dữ liệu vẫn do lớp con định nghĩa; các link được thêm qua `add(...)` và được bộ tuần tự hóa hypermedia xử lý khi controller trả model.

Chọn `EntityModel` khi chỉ cần bọc DTO. Chọn lớp kế thừa `RepresentationModel` khi representation có cấu trúc riêng hoặc cần tái sử dụng các hành vi biểu diễn. Cả hai cách đều cho phép client nhận dữ liệu cùng liên kết.

Khi quy tắc tạo link được dùng lại ở nhiều endpoint, có thể gom chúng vào một assembler:

```java
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class ProductModelAssembler
        implements RepresentationModelAssembler<Product, ProductModel> {

    @Override
    public ProductModel toModel(Product product) {
        ProductModel model = new ProductModel(
                product.getId(),
                product.getName(),
                product.getPrice()
        );

        model.add(linkTo(methodOn(ProductController.class)
                .one(product.getId())).withSelfRel());
        model.add(linkTo(methodOn(ProductController.class)
                .all()).withRel("products"));

        if (product.canBePublished()) {
            model.add(linkTo(methodOn(ProductController.class)
                    .publish(product.getId())).withRel("publish"));
        }

        return model;
    }
}
```

Assembler chuyển đổi đối tượng miền thành `ProductModel` và tập trung quy tắc thêm link. Controller có thể gọi `assembler.toModel(product)` ở endpoint chi tiết hoặc dùng cùng assembler cho từng phần tử trong collection. Phương thức `publish(...)` là endpoint hành động minh họa và cần được khai báo trong controller của ứng dụng.

## Dùng Link.of khi đã có URI

Trong trường hợp URI đã được cung cấp từ một cấu hình hoặc nguồn bên ngoài, có thể tạo link trực tiếp bằng `Link.of(href, rel)`:

```java
import org.springframework.hateoas.Link;

model.add(Link.of("https://catalog.example.com/products", "catalog"));
```

Cách này hữu ích với một đích cố định hoặc một tài nguyên ở hệ thống khác. Với endpoint thuộc chính ứng dụng Spring MVC, nên ưu tiên `linkTo(methodOn(...))` để URL bám theo mapping và ngữ cảnh request. Không tự tạo URL ngoài dự kiến hoặc nhận URI không đáng tin cậy từ dữ liệu người dùng rồi đưa thẳng vào response.

## Gắn link theo trạng thái nghiệp vụ

Một lợi ích quan trọng của hypermedia là server có thể chỉ công bố các hướng tương tác phù hợp với trạng thái tài nguyên và quyền của người gọi. Ví dụ, sản phẩm đang ở trạng thái `DRAFT` có thể có link `publish`; sản phẩm đã `PUBLISHED` có thể có link `reviews`.

```java
ProductModel model = new ProductModel(
        product.getId(),
        product.getName(),
        product.getPrice()
);

model.add(linkTo(methodOn(ProductController.class)
        .one(product.getId())).withSelfRel());

if (product.canBePublished()) {
    model.add(linkTo(methodOn(ProductController.class)
            .publish(product.getId())).withRel("publish"));
}

if (product.hasReviews()) {
    model.add(linkTo(methodOn(ProductController.class)
            .reviews(product.getId())).withRel("reviews"));
}
```

Điều kiện trong ví dụ đại diện cho quy tắc nghiệp vụ của ứng dụng. Có thể xét thêm quyền của người dùng trước khi công bố link hành động. Việc link không xuất hiện giúp client biết thao tác hiện không được công bố; tuy nhiên, endpoint vẫn phải kiểm tra quyền và trạng thái khi nhận request vì dữ liệu có thể thay đổi sau thời điểm response được tạo.

Không nên thêm mọi action link vào mọi tài nguyên rồi để client tự đoán thao tác nào hợp lệ. Cũng không nên xem sự vắng mặt của link là cơ chế bảo mật duy nhất. Server luôn là nơi thực thi quyền truy cập và quy tắc nghiệp vụ.

## Thêm link cho collection và phân trang

`CollectionModel<T>` cũng kế thừa `RepresentationModel`, vì vậy có thể thêm link cho cả tập hợp:

```java
List<ProductModel> products = productService.findAll().stream()
        .map(productAssembler::toModel)
        .toList();

CollectionModel<ProductModel> collection = CollectionModel.of(products);

collection.add(linkTo(methodOn(ProductController.class).all())
        .withSelfRel());
```

Liên kết `self` ở đây mô tả collection hiện tại. Nếu API hỗ trợ phân trang, response có thể có thêm `next`, `prev`, `first` và `last`. Spring HATEOAS hỗ trợ `PagedModel` và tích hợp với Spring Data để tạo các liên kết điều hướng trang. Client nên theo các link được trả về thay vì tự ghép tham số `page` và `size`.

Khi thêm link cho collection, cần phân biệt link của collection với link của từng phần tử. `self` của collection trỏ tới danh sách; `self` của mỗi `ProductModel` trỏ tới một sản phẩm cụ thể.

## Response HAL sau khi thêm link

Khi controller trả một representation model và client yêu cầu HAL JSON, Spring HATEOAS chuyển các liên kết thành thuộc tính `_links`:

```http
GET /api/products/42
Accept: application/hal+json
```

Response minh họa:

```json
{
  "id": "42",
  "name": "Mechanical Keyboard",
  "price": 1850000,
  "_links": {
    "self": {
      "href": "/api/products/42"
    },
    "products": {
      "href": "/api/products"
    },
    "reviews": {
      "href": "/api/products/42/reviews"
    }
  }
}
```

Trong ví dụ, mỗi khóa dưới `_links` là một quan hệ; `href` là URL của link. Client có thể tìm `_links.reviews.href` để đi tới đánh giá mà không cần tự xây dựng URL từ ID sản phẩm. Với response collection, các phần tử thường được đặt trong `_embedded`, tùy theo collection relation và cấu hình hypermedia.

HAL cơ bản biểu diễn quan hệ và đích của link. Nếu cần mô tả method, content type hoặc trường đầu vào của một thao tác, hãy bổ sung affordance và sử dụng media type mà client hỗ trợ, chẳng hạn HAL-FORMS.

## Đọc và kiểm tra link trên model

`RepresentationModel` cung cấp các phương thức để kiểm tra hoặc truy xuất link đã thêm:

```java
boolean hasSelf = model.hasLink("self");
boolean hasReviews = model.hasLink("reviews");

Optional<Link> reviewsLink = model.getLink("reviews");
Link selfLink = model.getRequiredLink("self");
```

- `add(...)`: thêm một hoặc nhiều link vào model.
- `hasLinks()`: kiểm tra model có link hay không.
- `hasLink(rel)`: kiểm tra có link theo quan hệ được chỉ định hay không.
- `getLink(rel)`: lấy link theo quan hệ dưới dạng `Optional`.
- `getRequiredLink(rel)`: lấy link bắt buộc; lỗi được ném ra nếu quan hệ không tồn tại.
- `getLinks()`: lấy tập hợp link của model.

Khi truy xuất một quan hệ có thể không xuất hiện theo trạng thái, nên dùng `getLink(...)` hoặc `hasLink(...)` để xử lý trường hợp không có link. Chỉ dùng `getRequiredLink(...)` khi hợp đồng của model bảo đảm quan hệ đó luôn tồn tại.

## Kiểm thử các link đã thêm

Kiểm thử nên xác nhận những quan hệ quan trọng được tuần tự hóa đúng trong response. Với MockMvc, có thể kiểm tra nội dung và `_links`:

```java
import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/products/{id}", publishedProductId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.products.href").exists())
    .andExpect(jsonPath("$._links.reviews.href").exists());
```

Với sản phẩm chưa được phép xuất bản, một kiểm thử khác nên xác nhận link `publish` không xuất hiện. Với sản phẩm đã xuất bản, kiểm tra link đó có xuất hiện nếu nghiệp vụ cho phép. Các kiểm thử theo trạng thái giúp bảo vệ hợp đồng điều hướng mà client sử dụng.

Khi API thay đổi mapping, kiểm thử cũng nên xác nhận client vẫn nhận được các quan hệ có ý nghĩa như `self`, `products` hoặc `reviews`. Không nên phụ thuộc vào việc URL luôn có cùng một chuỗi nếu mục tiêu là cho phép server thay đổi route; điều quan trọng là link đúng đích và giữ nguyên ngữ nghĩa của quan hệ.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nối chuỗi URL bằng ID | Link dễ sai khi mapping thay đổi | Dùng `linkTo(methodOn(...))` |
| Quên thêm `self` | Client khó nhận diện URI của tài nguyên hiện tại | Thêm link với `withSelfRel()` |
| Đặt `rel` không có ngữ nghĩa ổn định | Client khó sử dụng link qua các phiên bản API | Chọn tên quan hệ rõ ràng và tài liệu hóa |
| Thêm action link bất kể trạng thái | Client thấy thao tác không phù hợp | Chỉ thêm link khi nghiệp vụ và quyền cho phép |
| Nghĩ rằng action link thay thế authorization | Endpoint có thể bị gọi trực tiếp khi trạng thái thay đổi | Kiểm tra quyền và điều kiện trong service/controller |
| Dùng `getRequiredLink` cho quan hệ tùy chọn | Có thể phát sinh lỗi khi link không tồn tại | Dùng `getLink` hoặc `hasLink` |
| Cho rằng HAL link mô tả toàn bộ request | Client không biết method hoặc payload | Dùng affordance và media type phù hợp khi cần |

## Quy trình thực hành

Khi thêm link vào một representation, có thể thực hiện theo thứ tự sau:

1. Xác định tài nguyên và các quan hệ client cần khám phá.
2. Chọn `EntityModel` để bọc DTO hoặc tạo lớp riêng kế thừa `RepresentationModel`.
3. Dùng `linkTo(methodOn(...))` để tạo URL từ mapping controller.
4. Gắn `self` và các link liên quan bằng `model.add(...)`.
5. Chỉ thêm action link khi trạng thái nghiệp vụ và quyền hiện tại cho phép.
6. Trả model từ controller và thương lượng media type phù hợp.
7. Kiểm thử các quan hệ trong `_links`, bao gồm trường hợp link xuất hiện và không xuất hiện.

## Kết luận

Thêm link vào model là bước biến dữ liệu response thành một representation có khả năng điều hướng. `RepresentationModel` cung cấp cơ chế lưu link; `EntityModel` giúp bọc DTO; `WebMvcLinkBuilder` tạo URL theo mapping controller; còn `add(...)` gắn các quan hệ vào model. Khi quan hệ được đặt tên ổn định, link được công bố theo trạng thái nghiệp vụ và response được kiểm thử qua HAL, client có thể khám phá tài nguyên và thao tác mà không phải tự xây dựng cấu trúc URL.
