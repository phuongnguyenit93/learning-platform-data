# Assembler cho item

Trong Spring HATEOAS, item assembler chuyển một đối tượng nghiệp vụ thành representation của một tài nguyên đơn lẻ. Assembler chịu trách nhiệm chọn dữ liệu công khai cho client, tạo các liên kết hypermedia và quyết định liên kết hành động nào được công bố theo trạng thái tài nguyên.

`RepresentationModelAssembler<T, D>` là abstraction thường dùng cho công việc này. `T` là kiểu đối tượng nguồn, thường là domain object; `D` là kiểu representation đích, chẳng hạn `EntityModel<ProductResponse>` hoặc một lớp riêng kế thừa `RepresentationModel`. Phương thức `toModel(T)` thực hiện chuyển đổi một item. Controller gọi assembler rồi trả representation cho Spring MVC để tuần tự hóa thành HAL hoặc media type hypermedia đã cấu hình.

## Item assembler giải quyết vấn đề gì?

Nếu mỗi controller tự chuyển đổi domain object, chọn trường dữ liệu và tạo link, logic biểu diễn sẽ bị lặp lại ở nhiều endpoint. Khi API đổi tên trường, thêm quan hệ hoặc thay đổi điều kiện xuất hiện của action link, nhóm phát triển phải sửa nhiều nơi và dễ tạo response không nhất quán.

Item assembler gom những quyết định liên quan tới một loại tài nguyên vào một thành phần:

- Chuyển domain object thành DTO hoặc representation model.
- Tạo `self` link để client nhận diện tài nguyên hiện tại.
- Thêm link tới tài nguyên liên quan như `customer`, `category` hoặc `reviews`.
- Công bố action link như `activate`, `cancel` hoặc `archive` khi trạng thái và quyền hiện tại cho phép.
- Giữ cách biểu diễn giống nhau dù item được trả từ endpoint chi tiết, tìm kiếm hay collection.

Ví dụ, nhiều endpoint có thể trả một sản phẩm. Tất cả nên sử dụng cùng một quy tắc tạo `ProductResponse`, `self`, `category` và `activate` thay vì mỗi controller tự xây dựng response.

## Phân biệt domain object và representation

Domain object phục vụ quy tắc nghiệp vụ và lưu trữ. Representation phục vụ hợp đồng HTTP mà client nhìn thấy. Hai cấu trúc này có thể khác nhau.

Ví dụ domain object:

```java
import java.math.BigDecimal;
import java.util.UUID;

public class Product {

    private UUID id;
    private String name;
    private BigDecimal price;
    private ProductStatus status;
    private UUID categoryId;
    private String internalSupplierCode;

    public UUID getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public UUID getCategoryId() { return categoryId; }
    public String getInternalSupplierCode() { return internalSupplierCode; }

    public boolean canBeActivated() {
        return status == ProductStatus.DRAFT;
    }
}
```

API có thể chỉ công bố ID, tên, giá và trạng thái. Mã nhà cung cấp nội bộ không cần xuất hiện trong response. Tạo DTO riêng để xác định rõ nội dung công khai:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record ProductResponse(
        UUID id,
        String name,
        BigDecimal price,
        String status
) {}
```

Assembler sẽ chuyển `Product` thành `ProductResponse` rồi bọc trong `EntityModel<ProductResponse>`. Cách tách này tránh vô tình công bố trường nội bộ hoặc làm response phụ thuộc vào cấu trúc entity persistence.

## Cài đặt RepresentationModelAssembler

Interface `RepresentationModelAssembler<T, D>` nằm trong package `org.springframework.hateoas.server`. Với một sản phẩm, có thể cài đặt như sau:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class ProductModelAssembler
        implements RepresentationModelAssembler<Product, EntityModel<ProductResponse>> {

    @Override
    public EntityModel<ProductResponse> toModel(Product product) {
        UUID id = product.getId();

        ProductResponse content = new ProductResponse(
                id,
                product.getName(),
                product.getPrice(),
                product.getStatus().name()
        );

        EntityModel<ProductResponse> model = EntityModel.of(
                content,
                linkTo(methodOn(ProductController.class).one(id)).withSelfRel(),
                linkTo(methodOn(ProductController.class).all()).withRel("products")
        );

        return model;
    }
}
```

Trong ví dụ:

- `Product` là kiểu nguồn `T`.
- `EntityModel<ProductResponse>` là kiểu đích `D`.
- `toModel(...)` chuyển đổi một sản phẩm thành content và các link.
- `linkTo(methodOn(...))` tạo URI từ mapping controller, không cần nối chuỗi URL bằng ID.
- `withSelfRel()` gắn quan hệ chuẩn `self`; `withRel("products")` gắn quan hệ tới collection.

`@Component` đăng ký assembler để controller có thể nhận qua constructor injection. Assembler không truy vấn database và không thực thi thao tác nghiệp vụ; nó nhận object đã được service lấy ra và định nghĩa cách biểu diễn object đó.

## Thêm link theo trạng thái của item

Một item có thể có các khả năng khác nhau tùy trạng thái. Ví dụ, sản phẩm ở trạng thái `DRAFT` có thể được kích hoạt; sản phẩm đã `ACTIVE` không còn khả năng đó.

Thêm action link vào assembler:

```java
if (product.canBeActivated()) {
    model.add(linkTo(methodOn(ProductController.class).activate(id))
            .withRel("activate"));
}
```

Khi đó assembler hoàn chỉnh có thể tạo link liên quan và action link:

```java
if (product.getCategoryId() != null) {
    model.add(linkTo(methodOn(CategoryController.class)
            .one(product.getCategoryId())).withRel("category"));
}

if (product.canBeActivated()) {
    model.add(linkTo(methodOn(ProductController.class)
            .activate(id)).withRel("activate"));
}
```

Client có thể kiểm tra quan hệ `activate` để quyết định có hiển thị hành động kích hoạt hay không. Sự vắng mặt của link có nghĩa server hiện không công bố khả năng đó trong representation. Tuy nhiên, endpoint `activate` vẫn phải xác thực quyền và kiểm tra trạng thái khi nhận request vì trạng thái có thể thay đổi sau lúc response được tạo.

Không nên thêm mọi action link vào mọi item rồi để client tự đoán thao tác hợp lệ. Điều kiện tạo link nên dựa trên quy tắc nghiệp vụ rõ ràng; nếu khả năng còn phụ thuộc quyền người dùng, service hoặc authorization layer cần cung cấp thông tin phù hợp cho assembler.

## Dùng item assembler trong controller

Controller nhận service và assembler qua constructor. Endpoint chi tiết lấy domain object từ service, sau đó chuyển thành representation:

```java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;
    private final ProductModelAssembler assembler;

    public ProductController(ProductService service,
                             ProductModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<ProductResponse> one(@PathVariable UUID id) {
        Product product = service.findRequired(id);
        return assembler.toModel(product);
    }

    @GetMapping
    public CollectionModel<EntityModel<ProductResponse>> all() {
        return assembler.toCollectionModel(service.findAll())
                .add(linkTo(methodOn(ProductController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/activate")
    public ResponseEntity<Void> activate(@PathVariable UUID id) {
        service.activate(id);
        return ResponseEntity.noContent().build();
    }
}
```

Controller điều phối HTTP và truy xuất dữ liệu; assembler định nghĩa representation. Nếu cần thay đổi trường JSON hoặc relation của sản phẩm, có thể tập trung thay đổi trong DTO và assembler mà không làm controller phình to.

Một item assembler cũng có thể được dùng trong endpoint khác trả cùng loại tài nguyên, chẳng hạn kết quả tìm kiếm một sản phẩm theo SKU hoặc một endpoint lấy sản phẩm nổi bật. Điều kiện là các endpoint đó muốn công bố cùng hợp đồng representation. Nếu một endpoint thực sự có ngữ nghĩa khác, hãy tạo representation/assembler riêng thay vì thêm nhiều nhánh khó hiểu vào một assembler chung.

## Tái sử dụng item assembler khi tạo collection

Item assembler tập trung chuyển đổi một item. `RepresentationModelAssembler` cũng cung cấp phương thức mặc định `toCollectionModel(Iterable)` để áp dụng cùng quy tắc cho nhiều item và bọc kết quả trong `CollectionModel`.

Ví dụ:

```java
import org.springframework.hateoas.CollectionModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping
public CollectionModel<EntityModel<ProductResponse>> all() {
    Iterable<Product> products = service.findAll();

    return assembler.toCollectionModel(products)
            .add(linkTo(methodOn(ProductController.class).all()).withSelfRel());
}
```

Mỗi phần tử được chuyển qua `toModel(...)`, vì vậy các link `self`, `category` và `activate` vẫn được tạo theo cùng quy tắc. Link `self` được thêm sau đó thuộc cấp collection, trỏ tới danh sách sản phẩm.

Phân biệt hai cấp:

| Cấp | Link `self` trỏ tới | Ai tạo |
|---|---|---|
| Item | Một sản phẩm cụ thể | `toModel(Product)` |
| Collection | Danh sách sản phẩm | Controller hoặc logic tạo collection |

Khi collection cần phân trang, có thể dùng `PagedResourcesAssembler` để tạo `PagedModel`; item assembler vẫn chịu trách nhiệm biểu diễn từng phần tử.

## Kiểm thử item assembler

Unit test có thể xác nhận content và các relation của một item. Ví dụ dùng JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

class ProductModelAssemblerTest {

    private final ProductModelAssembler assembler = new ProductModelAssembler();

    @Test
    void createsProductContentAndSelfLink() {
        Product product = ProductFixtures.draftProduct();

        EntityModel<ProductResponse> model = assembler.toModel(product);

        assertEquals(product.getId(), model.getContent().id());
        assertEquals(product.getName(), model.getContent().name());
        assertTrue(model.hasLink(IanaLinkRelations.SELF));
        assertTrue(model.hasLink("products"));
    }
}
```

`ProductFixtures.draftProduct()` đại diện cho factory tạo dữ liệu test trong dự án. Vì assembler sử dụng `WebMvcLinkBuilder`, unit test gọi trực tiếp `toModel(...)` cần có request context phù hợp hoặc dùng cấu hình test của Spring. Một cách đơn giản để xác nhận mapping và URI thực tế là kiểm thử endpoint bằng MockMvc.

Kiểm thử điều kiện action link:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.EntityModel;

class ProductActionLinkTest {

    private final ProductModelAssembler assembler = new ProductModelAssembler();

    @Test
    void addsActivateLinkForDraftProduct() {
        Product product = ProductFixtures.draftProduct();

        EntityModel<ProductResponse> model = assembler.toModel(product);

        assertTrue(model.hasLink("activate"));
    }

    @Test
    void omitsActivateLinkForActiveProduct() {
        Product product = ProductFixtures.activeProduct();

        EntityModel<ProductResponse> model = assembler.toModel(product);

        assertFalse(model.hasLink("activate"));
    }
}
```

Các test này bảo vệ quy tắc biểu diễn theo trạng thái. Cần có thêm kiểm thử controller để xác nhận JSON và `href` cuối cùng được tạo đúng.

## Kiểm thử item response qua MockMvc

Kiểm thử tích hợp gọi endpoint như client và xác nhận content cùng `_links`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/products/{id}", productId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(productId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.products.href").exists());
```

Với sản phẩm nháp, kiểm tra `activate` xuất hiện; với sản phẩm đã kích hoạt, kiểm tra link này không tồn tại. Những assertion theo relation giúp phát hiện lỗi trong assembler trước khi client bị ảnh hưởng.

## Khi nào nên tạo assembler riêng?

Một assembler thường phù hợp với một loại representation và một tập quy tắc liên kết ổn định. Có thể tạo assembler riêng khi:

- Nhiều endpoint trả cùng loại tài nguyên và cần cùng representation.
- Việc chuyển đổi domain object sang DTO và thêm link có đủ logic để tách khỏi controller.
- Nhiều controller hoặc workflow cần tái sử dụng cách biểu diễn một item.
- Cần kiểm thử độc lập quy tắc tạo link theo trạng thái.

Không nhất thiết phải tạo assembler cho mọi DTO đơn giản. Nếu endpoint chỉ trả một response nhỏ, không có link và không có logic chuyển đổi dùng lại, việc tạo thêm abstraction có thể làm code khó theo dõi hơn. Hãy tách assembler khi nó tạo ra một ranh giới biểu diễn rõ ràng hoặc giúp tái sử dụng thực tế.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt logic tạo link trong nhiều controller | Response cùng loại tài nguyên không nhất quán | Tập trung vào item assembler |
| Trả trực tiếp entity persistence | Có thể lộ trường nội bộ hoặc quan hệ không mong muốn | Chuyển sang DTO/representation riêng |
| Nối chuỗi URL thủ công | Link dễ sai khi mapping đổi | Dùng `linkTo(methodOn(...))` |
| Để assembler truy vấn database | Khó kiểm soát hiệu năng và trách nhiệm | Lấy dữ liệu qua service trước khi gọi assembler |
| Thêm action link không theo trạng thái | Client thấy thao tác không phù hợp | Kiểm tra quy tắc nghiệp vụ trước khi thêm link |
| Xem link là cơ chế bảo mật | Request trực tiếp có thể bỏ qua giao diện client | Kiểm tra quyền tại endpoint/service |
| Dùng assembler item để tạo link collection | `self` có thể trỏ sai cấp tài nguyên | Thêm link collection ở cấp `CollectionModel` |
| Viết assembler quá tổng quát | Nhiều nhánh điều kiện khó hiểu | Tách representation khi ngữ nghĩa khác nhau |

## Quy trình xây dựng item assembler

1. Xác định domain object nguồn và các trường API được phép công bố.
2. Tạo DTO hoặc representation model cho một item.
3. Cài đặt `RepresentationModelAssembler<T, D>` và viết `toModel(T)`.
4. Tạo `self` link từ mapping controller bằng `linkTo(methodOn(...))`.
5. Thêm các link tới tài nguyên liên quan và action link theo trạng thái/quyền.
6. Inject assembler vào controller và trả representation thay vì tự dựng link ở từng endpoint.
7. Dùng `toCollectionModel(...)` khi cần tái sử dụng quy tắc item trong collection.
8. Kiểm thử content, relation, URI và điều kiện xuất hiện của action link.

## Kết luận

Item assembler chuyển một domain object thành representation hypermedia cho một tài nguyên đơn lẻ. `RepresentationModelAssembler<T, D>` giúp tách việc chọn content và tạo link khỏi controller; `toModel(...)` định nghĩa cách biểu diễn item, còn `toCollectionModel(...)` tái sử dụng quy tắc đó cho collection. Khi DTO chỉ công bố dữ liệu cần thiết, link được tạo từ controller mapping và action link phản ánh đúng trạng thái nghiệp vụ, API sẽ có response nhất quán và dễ kiểm thử hơn.
