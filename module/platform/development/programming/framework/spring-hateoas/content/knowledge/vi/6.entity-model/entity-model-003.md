# Nội dung và link

`EntityModel<T>` là kiểu biểu diễn của Spring HATEOAS dùng để kết hợp một đối tượng nội dung với các liên kết hypermedia. Phần nội dung mô tả dữ liệu của tài nguyên; các link mô tả tài nguyên hiện tại liên quan đến đâu và client có thể khám phá những bước tiếp theo nào.

Ví dụ, một API quản lý sản phẩm có thể trả về thông tin sản phẩm cùng link self, link về collection sản phẩm và link publish nếu sản phẩm đang ở trạng thái bản nháp. Client đọc dữ liệu để hiển thị sản phẩm, đồng thời dựa vào relation của link để khám phá hành động có thể thực hiện. Client không cần tự ghép URI từ ID hoặc suy luận endpoint từ tên trạng thái.

Trong Spring HATEOAS, `EntityModel` thường được dùng khi bạn đã có DTO hoặc một đối tượng biểu diễn và muốn bao nó cùng các link. Nếu muốn chính lớp biểu diễn tự mang link, có thể kế thừa `RepresentationModel`. Bài học này tập trung vào cách tổ chức nội dung và link trong `EntityModel`, cách tạo link từ controller mapping, cách phát link theo trạng thái và cách kiểm thử biểu diễn HAL.

Sau bài học, bạn có thể:

- Giải thích vai trò của `EntityModel<T>` trong Spring HATEOAS.
- Phân biệt nội dung tài nguyên với các link hypermedia.
- Tạo `EntityModel` bằng `EntityModel.of(...)` và bổ sung link bằng `add(...)`.
- Dùng `linkTo(...)` và `methodOn(...)` để tạo URI theo mapping của controller.
- Chọn relation phù hợp cho link self, collection và hành động theo nghiệp vụ.
- Tạo link có điều kiện dựa trên trạng thái hoặc quyền.
- Kiểm thử nội dung, relation, href và media type của phản hồi HAL.

## 1. EntityModel kết hợp nội dung và liên kết

Trong một API thông thường, controller có thể trả về một DTO:

~~~java
public record ProductRepresentation(
    UUID id,
    String name,
    BigDecimal price,
    String status
) {}
~~~

DTO này mô tả dữ liệu sản phẩm. Nếu client chỉ nhận JSON thuần, client có thể phải biết trước quy tắc tạo URI để đọc chi tiết, mở đánh giá hoặc thực hiện thao tác publish.

`EntityModel<T>` bao DTO cùng các link:

~~~java
EntityModel<ProductRepresentation> model =
    EntityModel.of(productRepresentation);
~~~

Sau khi thêm link, model có cả dữ liệu lẫn khả năng điều hướng:

~~~java
model.add(selfLink);
model.add(collectionLink);
model.add(publishLink);
~~~

Một phản hồi HAL minh họa có thể như sau:

~~~json
{
  "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "name": "Mechanical Keyboard",
  "price": 1850000,
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "https://api.example.com/products/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    },
    "products": {
      "href": "https://api.example.com/products"
    },
    "publish": {
      "href": "https://api.example.com/products/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/publication"
    }
  }
}
~~~

Trong HAL, thuộc tính dữ liệu nằm ở cấp biểu diễn, còn các liên kết nằm trong `_links`. Relation là tên ngữ nghĩa của link, ví dụ `self`, `products` hoặc `publish`; href là URI đích.

### 1.1. EntityModel không phải JPA entity

Tên `EntityModel` dễ khiến người mới nhầm nó với entity của JPA. Hai khái niệm có mục đích khác nhau:

| Khái niệm | Vai trò |
|---|---|
| JPA entity | Mô hình đối tượng ánh xạ đến dữ liệu lưu trữ |
| DTO / representation | Dữ liệu được chọn để công bố qua API |
| `EntityModel<T>` | Bao một đối tượng representation cùng các link hypermedia |

Tham số kiểu `T` thường nên là DTO hoặc kiểu dữ liệu API được kiểm soát. Không nên mặc định đưa thẳng JPA entity vào `EntityModel`, vì điều đó có thể làm lộ trường nội bộ, quan hệ persistence hoặc cấu trúc dữ liệu chưa phù hợp với hợp đồng API.

Ví dụ:

~~~java
ProductRepresentation content = new ProductRepresentation(
    product.getId(),
    product.getName(),
    product.getPrice(),
    product.getStatus().name()
);

EntityModel<ProductRepresentation> model = EntityModel.of(content);
~~~

Cách này tách rõ việc chuyển đổi dữ liệu miền thành biểu diễn công khai khỏi việc gắn link.

### 1.2. Khi nào dùng EntityModel và RepresentationModel?

Hai cách tổ chức thường gặp:

- Dùng `EntityModel<T>` khi đã có DTO hoặc đối tượng nội dung và muốn bọc nó cùng các link.
- Kế thừa `RepresentationModel<T>` khi chính lớp biểu diễn cần khai báo cấu trúc dữ liệu và các link của nó.

Ví dụ lớp biểu diễn tự kế thừa:

~~~java
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
~~~

Với `EntityModel<ProductRepresentation>`, Spring HATEOAS quản lý lớp bao và tập hợp link. Với `ProductModel`, lớp biểu diễn do ứng dụng định nghĩa kế thừa khả năng chứa link. Hãy chọn một cách phù hợp với cấu trúc DTO và quy ước của dự án; không cần tạo lớp kế thừa chỉ để thêm vài link đơn giản.

## 2. Tạo EntityModel và thêm link

Spring HATEOAS cung cấp các factory method để tạo `EntityModel`. Cách phổ biến nhất là `EntityModel.of(...)`.

### 2.1. Tạo model chỉ có nội dung

~~~java
ProductRepresentation content = new ProductRepresentation(
    id,
    "Mechanical Keyboard",
    new BigDecimal("1850000"),
    "DRAFT"
);

EntityModel<ProductRepresentation> model = EntityModel.of(content);
~~~

Ở thời điểm này, model đã chứa nội dung nhưng chưa có link. Có thể thêm link sau khi tạo model hoặc truyền link ngay trong lời gọi `of`.

### 2.2. Tạo model cùng nhiều link

~~~java
EntityModel<ProductRepresentation> model = EntityModel.of(
    content,
    selfLink,
    collectionLink
);
~~~

Phương thức factory nhận nội dung và các link ban đầu. Sau đó có thể bổ sung link theo điều kiện:

~~~java
if (product.canBePublished()) {
    model.add(publishLink);
}
~~~

`add(...)` trả về chính mô hình để có thể nối lời gọi. Ví dụ:

~~~java
EntityModel<ProductRepresentation> model = EntityModel.of(content)
    .add(selfLink)
    .add(collectionLink);
~~~

Nếu có một nhóm link được tạo sẵn, có thể thêm chúng bằng các overload nhận nhiều link hoặc một tập hợp link. Điều quan trọng là mỗi relation phải có ý nghĩa rõ ràng và phù hợp với tài nguyên đang biểu diễn.

### 2.3. Link được tạo thủ công

Có thể tạo link từ URI đã biết:

~~~java
Link selfLink = Link.of(
    "https://api.example.com/products/42",
    "self"
);
~~~

Cách này hữu ích khi URI đến từ một nguồn bên ngoài hoặc không được quản lý bởi mapping Spring MVC. Tuy nhiên, nếu endpoint thuộc controller của chính ứng dụng, nên ưu tiên tạo link từ mapping để giảm việc lặp lại đường dẫn trong mã nguồn.

### 2.4. Tạo link theo mapping bằng linkTo và methodOn

Spring HATEOAS cung cấp `WebMvcLinkBuilder` với hai hàm thường dùng:

- `linkTo(...)` xác định URI dựa trên mapping của controller.
- `methodOn(...)` mô tả phương thức controller và tham số để Spring HATEOAS dựng URI tương ứng.

Ví dụ, tạo link self cho một sản phẩm:

~~~java
Link selfLink = linkTo(
    methodOn(ProductController.class).one(product.getId())
).withSelfRel();
~~~

Tạo link về collection:

~~~java
Link productsLink = linkTo(
    methodOn(ProductController.class).all()
).withRel("products");
~~~

Tạo link đến thao tác publish:

~~~java
Link publishLink = linkTo(
    methodOn(ProductController.class).publish(product.getId())
).withRel("publish");
~~~

Lời gọi `methodOn` không thực thi logic nghiệp vụ của controller. Nó tạo một lời gọi mô phỏng để Spring HATEOAS xác định mapping và tham số cần dùng khi dựng URI.

Cách này đặc biệt hữu ích khi controller có path variable, context path hoặc mapping lồng nhau. Khi mapping được thay đổi, link sinh từ mapping mới sẽ cập nhật theo, miễn là phương thức và cách ánh xạ tham số vẫn tương ứng.

## 3. Thiết kế relation cho link

Một link không chỉ là một URL. Relation (rel) mô tả vai trò của liên kết đối với tài nguyên hiện tại. Client nên dựa vào relation để hiểu link có ý nghĩa gì và dùng href như URI đích.

### 3.1. Link self

Relation `self` trỏ đến chính tài nguyên đang được biểu diễn. Spring HATEOAS cung cấp helper `withSelfRel()`:

~~~java
Link self = linkTo(
    methodOn(ProductController.class).one(id)
).withSelfRel();
~~~

Link self giúp client biết URI chuẩn để truy cập lại biểu diễn. Nó cũng giúp client tránh phải tự tạo URI từ ID.

### 3.2. Link collection

Một member thường có link về collection chứa nó:

~~~java
Link collection = linkTo(
    methodOn(ProductController.class).all()
).withRel(IanaLinkRelations.COLLECTION);
~~~

Relation chuẩn nên được ưu tiên khi ý nghĩa phù hợp. Spring HATEOAS có `IanaLinkRelations` cho một số quan hệ được chuẩn hóa, chẳng hạn `SELF`, `COLLECTION`, `NEXT`, `PREV`, `FIRST` và `LAST`.

### 3.3. Custom relation

Các thao tác theo miền có thể dùng relation tùy chỉnh:

- `publish`: xuất bản sản phẩm.
- `archive`: lưu trữ sản phẩm.
- `reviews`: xem đánh giá.
- `approve`: phê duyệt yêu cầu.
- `cancel`: hủy một giao dịch hoặc lịch đặt.

Ví dụ:

~~~java
Link publish = linkTo(
    methodOn(ProductController.class).publish(id)
).withRel("publish");
~~~

Tên relation tùy chỉnh phải có ngữ nghĩa ổn định. Nếu API được nhiều client độc lập sử dụng, nên định nghĩa tài liệu cho relation; với hợp đồng công khai, có thể dùng URI relation hoặc CURIE để tránh xung đột tên và cung cấp nơi tra cứu ngữ nghĩa.

Không nên đổi ý nghĩa của một relation đã công bố. Nếu `publish` có nghĩa là đưa sản phẩm từ DRAFT sang PUBLISHED, không nên tái sử dụng relation đó cho một hành động xóa sản phẩm.

### 3.4. Nhiều link cùng một relation

Một tài nguyên có thể có nhiều link cùng relation, ví dụ nhiều tài liệu liên quan hoặc nhiều lựa chọn điều hướng. Khi serialize, định dạng hypermedia có thể biểu diễn relation đó thành một mảng link. Client cần xử lý cả link đơn và nhiều link nếu hợp đồng cho phép.

Không nên phụ thuộc vào thứ tự các link trừ khi định dạng hoặc hợp đồng có quy định rõ. Mỗi link nên có URI hợp lệ và cùng ngữ nghĩa relation.

## 4. Xây dựng EntityModel bằng assembler

Khi một tài nguyên được trả về từ nhiều endpoint, việc tạo nội dung và link nên được tập trung để tránh mỗi controller phát ra một cấu trúc khác nhau. `RepresentationModelAssembler` là cơ chế phù hợp cho việc này.

Giả sử ứng dụng quản lý sản phẩm có lớp miền `Product`, `ProductService` và DTO:

~~~java
public record ProductRepresentation(
    UUID id,
    String name,
    BigDecimal price,
    String status
) {}
~~~

Assembler tạo nội dung và link:

~~~java
@Component
public class ProductModelAssembler
        implements RepresentationModelAssembler<Product, EntityModel<ProductRepresentation>> {

    @Override
    public EntityModel<ProductRepresentation> toModel(Product product) {
        UUID id = product.getId();

        ProductRepresentation content = new ProductRepresentation(
            id,
            product.getName(),
            product.getPrice(),
            product.getStatus().name()
        );

        EntityModel<ProductRepresentation> model = EntityModel.of(
            content,
            linkTo(methodOn(ProductController.class).one(id)).withSelfRel(),
            linkTo(methodOn(ProductController.class).all())
                .withRel(IanaLinkRelations.COLLECTION)
        );

        if (product.canBePublished()) {
            model.add(
                linkTo(methodOn(ProductController.class).publish(id))
                    .withRel("publish")
            );
        }

        return model;
    }
}
~~~

Assembler chịu trách nhiệm:

1. Chuyển dữ liệu miền thành DTO công khai.
2. Tạo link self cho member.
3. Tạo link về collection.
4. Thêm link nghiệp vụ khi điều kiện phù hợp.

Vì logic được tập trung, mọi endpoint sử dụng assembler có thể trả về cùng cấu trúc representation và cùng ngữ nghĩa relation.

### 4.1. Tích hợp assembler vào controller

Controller trả về `EntityModel<ProductRepresentation>` thay vì DTO thuần:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;
    private final ProductModelAssembler assembler;

    public ProductController(
            ProductService service,
            ProductModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<ProductRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(ProductController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    public EntityModel<ProductRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }

    @PostMapping("/{id}/publication")
    public ResponseEntity<Void> publish(@PathVariable UUID id) {
        service.publish(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Các import chính của ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Các kiểu `Product` và `ProductService` là thành phần miền của ứng dụng minh họa. Trong dự án thực tế, thay chúng bằng model và service tương ứng. Phương thức `publish` cần kiểm tra điều kiện nghiệp vụ và quyền truy cập ở service hoặc tầng domain.

## 5. Link theo trạng thái và quyền

Một ưu điểm quan trọng của hypermedia là link có thể thay đổi theo trạng thái hiện tại của tài nguyên. Ví dụ:

| Trạng thái sản phẩm | Link có thể xuất hiện |
|---|---|
| DRAFT | self, collection, publish |
| PUBLISHED | self, collection, reviews, archive |
| ARCHIVED | self, collection |

Đây là hợp đồng minh họa. Hành động thực tế phụ thuộc vào quy tắc nghiệp vụ của ứng dụng.

### 5.1. Tạo link theo trạng thái nghiệp vụ

Assembler có thể kiểm tra trạng thái trước khi thêm link:

~~~java
if (product.canBePublished()) {
    model.add(
        linkTo(methodOn(ProductController.class).publish(id))
            .withRel("publish")
    );
}

if (product.isPublished()) {
    model.add(
        linkTo(methodOn(ProductController.class).reviews(id))
            .withRel("reviews")
    );
}
~~~

Khi sản phẩm còn là bản nháp, client có thể khám phá hành động publish. Sau khi xuất bản, link publish biến mất và link reviews có thể xuất hiện.

Điều kiện tạo link nên dựa trên quy tắc miền có tên rõ ràng như `canBePublished()`, thay vì lặp lại các phép so sánh trạng thái rải rác trong assembler. Cách này giúp quy tắc nghiệp vụ dễ đọc và dễ kiểm thử hơn.

### 5.2. Tạo link theo quyền người dùng

Các khả năng cũng có thể phụ thuộc người dùng đang gọi API. Ví dụ, người quản trị có thể thấy link archive, còn người đọc thông thường chỉ thấy self và reviews.

Có thể truyền một đối tượng quyền hoặc policy vào assembler:

~~~java
if (permissions.canArchive(product)) {
    model.add(
        linkTo(methodOn(ProductController.class).archive(id))
            .withRel("archive")
    );
}
~~~

Ví dụ này giả định `permissions` đã được cung cấp bởi tầng ứng dụng. Không nên để assembler tự truy cập ngẫu nhiên vào security context hoặc thực hiện truy vấn nghiệp vụ phức tạp. Hãy truyền rõ thông tin cần thiết hoặc dùng một service/policy chuyên trách.

### 5.3. Link không thay thế kiểm tra quyền

Link chỉ mô tả khả năng được công bố trong biểu diễn tại thời điểm server tạo response. Nó không phải token cấp quyền. Client có thể lưu href cũ hoặc gửi request trực tiếp mà không đọc link.

Do đó, endpoint thực hiện hành động vẫn phải kiểm tra:

- Người dùng có quyền thực hiện thao tác không?
- Tài nguyên có đang ở trạng thái cho phép không?
- Các điều kiện nghiệp vụ khác có được thỏa mãn không?
- Request có hợp lệ và có đủ dữ liệu cần thiết không?

Nếu điều kiện không còn đúng, server phải trả lỗi HTTP phù hợp. Việc bỏ link giúp client tránh hiển thị hành động không khả dụng, còn kiểm tra phía server bảo vệ tài nguyên.

## 6. Đọc và chuyển đổi nội dung của EntityModel

`EntityModel` cung cấp các phương thức để truy cập nội dung và các link. Điều này hữu ích trong các thành phần xử lý representation hoặc kiểm thử.

Ví dụ:

~~~java
EntityModel<ProductRepresentation> model = assembler.toModel(product);

ProductRepresentation content = model.getContent();
Iterable<Link> links = model.getLinks();

boolean hasPublish = model.hasLink("publish");
Optional<Link> self = model.getLink("self");
~~~

Nếu khai báo kiểu tường minh, `Link` được import từ `org.springframework.hateoas`; `Optional` thuộc `java.util`, còn `Iterable` thuộc `java.lang`.

Các thao tác thường gặp:

| API | Ý nghĩa |
|---|---|
| `EntityModel.of(content)` | Tạo model từ nội dung |
| `EntityModel.of(content, links...)` | Tạo model với nội dung và các link ban đầu |
| `model.add(link)` | Thêm link |
| `model.getContent()` | Lấy nội dung |
| `model.getLinks()` | Lấy tập hợp link |
| `model.getLink(rel)` | Tìm link theo relation, kết quả là Optional |
| `model.hasLink(rel)` | Kiểm tra relation có tồn tại |
| `model.getRequiredLink(rel)` | Lấy link bắt buộc; lỗi nếu không có |

Khi lấy link tùy chọn, nên xử lý trường hợp relation vắng mặt:

~~~java
model.getLink("publish")
    .ifPresent(link -> logger.info("Publish URI: {}", link.getHref()));
~~~

Không nên giả định mọi model đều có link `publish`, vì link này có thể chỉ xuất hiện ở trạng thái DRAFT hoặc với người dùng có quyền tương ứng.

### 6.1. Chuyển đổi nội dung bằng mapContent

Nếu cần thay đổi kiểu nội dung nhưng vẫn giữ các link hiện tại, `EntityModel` cung cấp `mapContent(...)`:

~~~java
EntityModel<ProductSummary> summary = model.mapContent(content ->
    new ProductSummary(content.id(), content.name())
);
~~~

Kết quả là một `EntityModel<ProductSummary>` mới với nội dung đã chuyển đổi và các link của model ban đầu. Cách này hữu ích khi cần tạo một biểu diễn rút gọn mà vẫn giữ điều hướng.

Việc giữ lại link chỉ hợp lý khi các link đó vẫn có ý nghĩa với biểu diễn mới. Nếu nội dung rút gọn không còn hỗ trợ một hành động nào đó hoặc người dùng có quyền khác, cần tạo lại tập link thay vì giữ nguyên một cách máy móc.

## 7. Serialize EntityModel thành HAL

Spring HATEOAS tích hợp với Spring Web để serialize các mô hình hypermedia. Khi client yêu cầu HAL:

~~~http
GET /products/42 HTTP/1.1
Accept: application/hal+json
~~~

Controller trả về `EntityModel<ProductRepresentation>`; Spring có thể serialize thành JSON HAL. Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "42",
  "name": "Mechanical Keyboard",
  "price": 1850000,
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "https://api.example.com/products/42"
    },
    "collection": {
      "href": "https://api.example.com/products"
    },
    "publish": {
      "href": "https://api.example.com/products/42/publication"
    }
  }
}
~~~

Cần phân biệt hai phần:

- Nội dung là dữ liệu mô tả sản phẩm.
- `_links` là các liên kết có quan hệ ngữ nghĩa.

Client HAL nên tìm relation cần dùng rồi truy cập href. Nó không nên phân tích chuỗi URI để đoán ID hoặc quy tắc định tuyến.

Spring Boot starter HATEOAS cung cấp cấu hình tích hợp phổ biến cho HAL. Nếu API không trả media type như mong đợi, hãy kiểm tra dependency, content negotiation và cấu hình message converter của ứng dụng.

## 8. Kiểm thử nội dung và link bằng MockMvc

Kiểm thử một endpoint trả `EntityModel` nên xác nhận cả nội dung lẫn link. Ví dụ, với sản phẩm đang ở trạng thái DRAFT, response cần có link publish:

~~~java
@WebMvcTest(ProductController.class)
@Import(ProductModelAssembler.class)
class ProductControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    ProductService service;

    @Test
    void returnsProductContentAndPublishLinkForDraft() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.getRequired(id)).willReturn(draftProduct(id));

        mvc.perform(get("/products/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(id.toString()))
            .andExpect(jsonPath("$.name").value("Mechanical Keyboard"))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/products/" + id)))
            .andExpect(jsonPath("$._links.publish.href").exists());
    }
}
~~~

Với sản phẩm đã xuất bản, kiểm tra link publish không xuất hiện:

~~~java
.andExpect(jsonPath("$._links.publish").doesNotExist());
~~~

Các import thường dùng trong kiểm thử:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Trong ví dụ, `draftProduct(id)` là fixture do nhóm kiểm thử định nghĩa. Ngoài kiểm thử trên, nên kiểm tra:

- Link self được tạo đúng khi mapping có path variable.
- Link collection có relation đúng và trỏ đến collection.
- Link nghiệp vụ xuất hiện hoặc biến mất theo trạng thái.
- Link được phát đúng theo quyền người dùng.
- Content negotiation trả media type phù hợp.
- Request thực hiện hành động vẫn bị từ chối nếu trạng thái hoặc quyền không còn hợp lệ.
- Link công khai có host, scheme và context path chính xác khi chạy sau proxy hoặc gateway.

MockMvc kiểm tra tích hợp giữa Spring MVC, assembler và quá trình serialize response trong môi trường test. Nếu API được triển khai qua gateway hoặc reverse proxy, cần có kiểm thử tích hợp để xác nhận URI bên ngoài mà client nhìn thấy.

## 9. Lỗi thường gặp khi sử dụng EntityModel

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm EntityModel với JPA entity | Để lộ cấu trúc persistence trong API | Dùng DTO làm nội dung |
| Chỉ trả nội dung, không có link | Client phải tự dựng URI | Thêm self và link quan hệ cần thiết |
| Tạo URI bằng chuỗi lặp lại | Link dễ lệch khi mapping thay đổi | Dùng linkTo và methodOn |
| Dùng rel không rõ nghĩa | Client không biết link thực hiện việc gì | Định nghĩa relation ổn định |
| Luôn phát mọi link | Client thấy thao tác không khả dụng | Tạo link theo trạng thái và quyền |
| Cho rằng có link là được phép | Request trực tiếp có thể vượt qua giả định của client | Kiểm tra quyền và nghiệp vụ tại server |
| Giữ link sau khi đổi nội dung mà không xem xét | Link có thể không còn phù hợp với representation mới | Đánh giá link khi mapContent hoặc chuyển DTO |
| Chỉ kiểm thử trường dữ liệu | Lỗi relation hoặc href không được phát hiện | Kiểm tra cả nội dung, link và media type |

## 10. Quy trình xây dựng EntityModel

Khi thêm `EntityModel` cho một tài nguyên, có thể thực hiện theo trình tự:

1. Xác định dữ liệu nào được phép công bố qua API.
2. Tạo DTO hoặc representation riêng cho dữ liệu đó.
3. Tạo `EntityModel.of(content)` hoặc `EntityModel.of(content, links...)`.
4. Tạo link self từ mapping của controller.
5. Thêm link collection hoặc link đến tài nguyên liên quan.
6. Thêm link hành động dựa trên trạng thái và quyền.
7. Trả model từ controller và cấu hình media type hypermedia phù hợp.
8. Kiểm thử nội dung, relation, href, link có điều kiện và trường hợp link vắng mặt.
9. Đảm bảo endpoint vẫn kiểm tra quyền và quy tắc nghiệp vụ khi nhận request.

## 11. Kết luận

`EntityModel<T>` kết hợp một đối tượng nội dung với các liên kết hypermedia trong cùng một biểu diễn. Nội dung mô tả dữ liệu công khai của tài nguyên; link cung cấp cách client khám phá tài nguyên liên quan và hành động tiếp theo. Spring HATEOAS hỗ trợ tạo model bằng `EntityModel.of(...)`, thêm link bằng `add(...)` và xây URI theo mapping thông qua `linkTo(...)` cùng `methodOn(...)`.

Khi dùng DTO làm nội dung, định nghĩa relation rõ ràng và phát link theo trạng thái hoặc quyền, API giúp client điều hướng theo hợp đồng hypermedia ổn định. Assembler tập trung việc tạo biểu diễn, HAL cung cấp định dạng trao đổi phổ biến, còn MockMvc giúp kiểm tra cả dữ liệu lẫn link. Server vẫn phải kiểm tra quyền và điều kiện nghiệp vụ ở mỗi thao tác.

