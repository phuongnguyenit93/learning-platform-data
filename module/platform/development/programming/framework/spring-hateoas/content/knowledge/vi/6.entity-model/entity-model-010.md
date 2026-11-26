# Khi nào dùng EntityModel

Trong Spring HATEOAS, `EntityModel<T>` là lựa chọn phù hợp khi API cần biểu diễn **một tài nguyên đơn lẻ**, giữ một đối tượng nội dung `T` và gắn các liên kết hypermedia cho tài nguyên đó. Thay vì tạo một lớp mới chỉ để chứa dữ liệu cùng danh sách link, bạn có thể bọc DTO hoặc đối tượng hiện có bằng `EntityModel` rồi thêm `self`, liên kết tới collection và các hành động khả dụng.

`EntityModel` thuộc gói `org.springframework.hateoas` và kế thừa `RepresentationModel<EntityModel<T>>`. Vì vậy, nó dùng chung API quản lý liên kết của `RepresentationModel`, đồng thời bổ sung phần nội dung (`content`) được bọc bên trong. Kiểu `T` có thể là DTO, projection hoặc đối tượng miền; tên lớp không có nghĩa bắt buộc phải truyền JPA entity vào.

Bài học này thuộc chương **EntityModel** trong module **SPRING_HATEOAS**, tập trung vào tiêu chí chọn `EntityModel`, cách dùng trong controller và assembler, cũng như thời điểm nên chuyển sang một kiểu mô hình khác.

Sau bài học, bạn có thể:

- Nhận diện trường hợp một tài nguyên đơn phù hợp với `EntityModel<T>`.
- Tạo mô hình bằng `EntityModel.of(...)` và thêm liên kết theo relation.
- Kết hợp `EntityModel` với DTO và `RepresentationModelAssembler`.
- Phân biệt `EntityModel` với `RepresentationModel`, `CollectionModel` và `PagedModel`.
- Tránh các lỗi thường gặp khi bọc entity JPA và khi thiết kế phản hồi hypermedia.
- Kiểm thử nội dung, liên kết và media type của phản hồi.

## 1. Tiêu chí chọn EntityModel

Hãy bắt đầu từ hình dạng của tài nguyên mà endpoint cần trả về. Nếu kết quả là **một đối tượng** và bạn muốn gắn các liên kết vào chính đối tượng đó, `EntityModel<T>` thường là lựa chọn đơn giản:

```java
EntityModel<OrderResponse> model = EntityModel.of(orderResponse);
model.add(selfLink);
model.add(ordersLink);
```

Mô hình có hai phần logic:

| Phần | Vai trò |
|---|---|
| `content` | Đối tượng dữ liệu được biểu diễn, kiểu `T`. |
| `links` | Các liên kết mô tả quan hệ và thao tác liên quan tới tài nguyên. |

Trong HAL JSON, phần nội dung thường xuất hiện ở cấp tài nguyên, còn các liên kết nằm trong `_links`:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    }
  }
}
```

Một số dấu hiệu cho thấy `EntityModel` phù hợp:

- Endpoint trả về một tài nguyên, ví dụ một đơn hàng, sản phẩm, hồ sơ hoặc tài khoản.
- Phần dữ liệu đã có kiểu phù hợp để tuần tự hóa; bạn chỉ cần bổ sung hypermedia.
- Liên kết thuộc về chính tài nguyên đó, chẳng hạn `self`, `orders`, `reviews` hoặc `cancel`.
- Bạn không cần tạo một cấu trúc biểu diễn riêng với nhiều trường bổ sung ngoài nội dung được bọc.

Ví dụ, `GET /orders/42` trả về một đơn hàng có thể dùng `EntityModel<OrderResponse>`. Trong khi đó, `GET /orders` trả về nhiều đơn hàng thì nên dùng `CollectionModel<EntityModel<OrderResponse>>` hoặc `PagedModel<EntityModel<OrderResponse>>` nếu có phân trang.

## 2. Tạo EntityModel bằng factory method

`EntityModel` cung cấp factory method `of(...)` để tạo wrapper. Có thể tạo mô hình chỉ với nội dung, hoặc truyền các link ngay lúc khởi tạo:

```java
import org.springframework.hateoas.EntityModel;

EntityModel<OrderResponse> withoutLinks = EntityModel.of(orderResponse);

EntityModel<OrderResponse> withLinks = EntityModel.of(
        orderResponse,
        selfLink,
        ordersLink
);
```

Bạn cũng có thể tạo trước rồi bổ sung link sau:

```java
EntityModel<OrderResponse> model = EntityModel.of(orderResponse);

model.add(selfLink);
model.add(ordersLink);

if (orderResponse.status().equals("PENDING")) {
    model.add(cancelLink);
}
```

`EntityModel` kế thừa các thao tác liên kết từ `RepresentationModel`, ví dụ `add`, `getLinks`, `getLink`, `hasLink` và `removeLinks`; đồng thời cung cấp `getContent()` để truy cập đối tượng được bọc. Việc kiểm tra theo relation giúp code diễn đạt đúng ý nghĩa của liên kết:

```java
if (model.hasLink("cancel")) {
    model.getLink("cancel").ifPresent(link -> log.info(
            "Cancellation link: {}", link.getHref()));
}
```

Trong ứng dụng, client thường đọc relation từ phản hồi. Không nên yêu cầu client dựa vào thứ tự link hoặc tự dựng URI từ ID.

## 3. Dùng DTO làm content của EntityModel

Mặc dù tên là `EntityModel`, kiểu nội dung không bắt buộc là JPA entity. Một lựa chọn tốt là tạo DTO chỉ chứa các trường API muốn công bố:

```java
import java.math.BigDecimal;

public record ProductResponse(
        Long id,
        String name,
        BigDecimal price
) {}
```

Service có thể trả entity `Product`, sau đó mapper chuyển sang `ProductResponse`. `EntityModel<ProductResponse>` vừa giữ ranh giới dữ liệu của API, vừa cung cấp liên kết hypermedia:

```java
ProductResponse response = new ProductResponse(
        product.getId(),
        product.getName(),
        product.getPrice()
);

EntityModel<ProductResponse> model = EntityModel.of(response);
```

Lợi ích của DTO content:

- Không vô tình công bố mọi thuộc tính của entity.
- Tránh tuần tự hóa quan hệ JPA ngoài ý muốn hoặc vòng tham chiếu giữa các entity.
- Có thể đổi tên trường API mà không phải đổi schema persistence.
- Có thể tổng hợp dữ liệu từ nhiều nguồn trước khi tạo biểu diễn.
- Giữ việc chuyển đổi dữ liệu tách biệt khỏi việc tạo link.

Bạn vẫn có thể dùng `EntityModel<Product>` khi entity đơn giản, đã được kiểm soát rõ các trường được tuần tự hóa và không có rủi ro về association hoặc lazy loading. Với API công khai hoặc mô hình miền phức tạp, DTO thường giúp hợp đồng dễ quản lý hơn.

## 4. Tạo liên kết theo controller

Khi endpoint được khai báo bằng Spring MVC, `WebMvcLinkBuilder` giúp tạo URI từ mapping của controller. `linkTo(methodOn(...))` thường được ưu tiên để tránh rải rác chuỗi URL trong mã nguồn.

Giả sử ứng dụng có `Product` và `ProductService`. Assembler sau chuyển một sản phẩm thành `EntityModel<ProductResponse>`:

```java
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
        ProductResponse content = new ProductResponse(
                product.getId(), product.getName(), product.getPrice());

        EntityModel<ProductResponse> model = EntityModel.of(
                content,
                linkTo(methodOn(ProductController.class).one(product.getId()))
                        .withSelfRel(),
                linkTo(methodOn(ProductController.class).all())
                        .withRel("products")
        );

        if (product.isAvailable()) {
            model.add(linkTo(methodOn(ProductController.class).purchase(product.getId()))
                    .withRel("purchase"));
        }

        return model;
    }
}
```

Ở đây `self` trỏ tới sản phẩm hiện tại, `products` trỏ tới collection, còn `purchase` chỉ xuất hiện nếu sản phẩm đang có thể mua. `RepresentationModelAssembler` giúp áp dụng cùng một quy tắc chuyển đổi cho nhiều endpoint hoặc từng phần tử của collection.

Controller có thể dùng assembler như sau:

```java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;
    private final ProductModelAssembler assembler;

    public ProductController(ProductService service, ProductModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<ProductResponse> one(@PathVariable Long id) {
        Product product = service.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return assembler.toModel(product);
    }

    @GetMapping
    public CollectionModel<EntityModel<ProductResponse>> all() {
        List<EntityModel<ProductResponse>> items = service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(items);
    }

    @PostMapping("/{id}/purchase")
    public ResponseEntity<Void> purchase(@PathVariable Long id) {
        service.purchase(id);
        return ResponseEntity.noContent().build();
    }
}
```

Ví dụ giả định `ProductService` cung cấp `findById`, `findAll` và `purchase`, còn `Product` có các getter cùng `isAvailable()`. Trong ứng dụng thực tế, endpoint `purchase` cần trả status code và response phù hợp với nghiệp vụ, đồng thời kiểm tra quyền và tình trạng tồn kho.

## 5. Khi nào nên dùng EntityModel?

Các tình huống sau thường phù hợp với `EntityModel<T>`:

### Một tài nguyên chi tiết

Ví dụ `GET /customers/15` trả về một hồ sơ khách hàng. Nội dung có thể là `CustomerResponse`, còn link gồm `self`, `orders` và `addresses`. Mỗi link thể hiện một quan hệ mà client có thể theo để khám phá phần liên quan.

### Một tài nguyên có hành động tùy trạng thái

Ví dụ `GET /orders/42` trả về đơn hàng và chỉ thêm `cancel` khi trạng thái là `PENDING`. Mô hình vẫn là một đối tượng đơn; các liên kết bổ sung mô tả hành động khả dụng ở thời điểm tạo phản hồi.

### Một đối tượng hiện có chỉ cần thêm hypermedia

Nếu DTO đã có cấu trúc phù hợp và không cần trường biểu diễn mới, `EntityModel.of(dto, links...)` tránh việc tạo thêm lớp chỉ để chứa link.

### Một phần tử trong collection hoặc trang

Mỗi phần tử trong danh sách có thể là `EntityModel<T>` để giữ link riêng. Toàn bộ danh sách được bọc trong `CollectionModel` hoặc `PagedModel`, tạo cấu trúc đúng cấp tài nguyên và cấp collection.

## 6. Khi nào không nên dùng EntityModel?

`EntityModel` không phải wrapper mặc định cho mọi kiểu phản hồi. Chọn mô hình khác khi cấu trúc dữ liệu yêu cầu:

| Tình huống | Kiểu phù hợp | Lý do |
|---|---|---|
| Một đối tượng cùng các link | `EntityModel<T>` | Đúng mô hình một tài nguyên. |
| Cần lớp biểu diễn có nhiều trường riêng, dữ liệu tổng hợp hoặc quy tắc biểu diễn chuyên biệt | Lớp con `RepresentationModel<T>` | Chủ động kiểm soát cấu trúc dữ liệu và link. |
| Một tập hợp nhiều phần tử và link cấp collection | `CollectionModel<T>` | Biểu diễn nhiều phần tử, có thể gắn link cho cả collection. |
| Một tập hợp có metadata trang và link `next`, `prev` | `PagedModel<T>` | Có metadata phân trang và điều hướng. |
| Phản hồi không phải tài nguyên hypermedia, chẳng hạn scalar hoặc file download | Kiểu phản hồi phù hợp như `ResponseEntity<byte[]>` hoặc DTO thường | Không cần wrapper hypermedia nếu không có ý nghĩa điều hướng. |

Tránh bọc một danh sách vào `EntityModel<List<T>>` chỉ vì muốn thêm link. Cách đó làm toàn bộ danh sách trở thành content của một entity model duy nhất; client không có mô hình collection chuẩn và từng phần tử không có chỗ rõ ràng để mang link riêng. Hãy dùng `CollectionModel<EntityModel<T>>` hoặc `PagedModel<EntityModel<T>>`.

Nếu cần thêm nhiều thuộc tính cấp cao như `summary`, `permissions`, `calculatedTotal` hoặc `warnings` bên cạnh content, hãy cân nhắc DTO chuyên biệt kế thừa `RepresentationModel`. `EntityModel` được thiết kế để bọc một content object; không nên dùng các thủ thuật tuần tự hóa để biến wrapper thành một cấu trúc khác khó hiểu.

## 7. So sánh nhanh các mô hình

| Tiêu chí | `EntityModel<T>` | `RepresentationModel<T>` | `CollectionModel<T>` | `PagedModel<T>` |
|---|---|---|---|---|
| Hình dạng dữ liệu | Một content object | Lớp biểu diễn tùy chỉnh | Nhiều phần tử | Nhiều phần tử có metadata trang |
| Cách cung cấp dữ liệu | Bọc đối tượng có sẵn | Lớp con tự khai báo trường | Tập hợp mô hình phần tử | Tập hợp cùng metadata phân trang |
| Liên kết | Có | Có | Có ở cấp collection và từng phần tử nếu phần tử mang link | Có liên kết điều hướng trang và link của phần tử |
| Trường hợp tiêu biểu | Chi tiết một tài nguyên | DTO hypermedia đặc thù | Danh sách không phân trang | Danh sách phân trang |

Ví dụ về cấu trúc kiểu:

```java
EntityModel<ProductResponse> oneProduct;

CollectionModel<EntityModel<ProductResponse>> productCollection;

PagedModel<EntityModel<ProductResponse>> productPage;
```

Các kiểu trên đều thuộc hệ mô hình Spring HATEOAS, nhưng cấp độ biểu diễn khác nhau. Chọn theo hình dạng phản hồi thực tế giúp client hiểu đâu là tài nguyên, đâu là collection và đâu là điều hướng trang.

## 8. Tuần tự hóa EntityModel thành HAL

Với Spring Boot, dependency `spring-boot-starter-hateoas` cung cấp tích hợp Spring HATEOAS và cấu hình converter hypermedia. Client có thể yêu cầu HAL JSON bằng header:

```http
Accept: application/hal+json
```

Ví dụ nội dung `ProductResponse` cùng các link được tuần tự hóa thành:

```json
{
  "id": 10,
  "name": "Mechanical Keyboard",
  "price": 1500000,
  "_links": {
    "self": {
      "href": "https://api.example.com/products/10"
    },
    "products": {
      "href": "https://api.example.com/products"
    },
    "purchase": {
      "href": "https://api.example.com/products/10/purchase"
    }
  }
}
```

Với một `EntityModel`, content được biểu diễn ở cấp tài nguyên; `_links` chứa các liên kết theo relation. Trong khi đó, collection model dùng `_embedded` để chứa các phần tử. Cấu trúc này cho phép client đọc dữ liệu hiện tại và tìm hành động hoặc tài nguyên liên quan theo quan hệ.

Nếu ứng dụng không dùng cấu hình Spring Boot tự động, cần đăng ký cấu hình hypermedia và message converter phù hợp. Đừng chỉ kiểm tra JSON có trường `_links`; hãy kiểm tra response có media type mà client yêu cầu và relation có đúng ý nghĩa.

## 9. Kiểm thử EntityModel trong controller

Kiểm thử nên xác nhận ba điểm: content đúng, liên kết đúng và media type đúng. Ví dụ sau dùng MockMvc và JSONPath:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void productResponseContainsContentAndLinks() throws Exception {
        mockMvc.perform(get("/products/10").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(10))
                .andExpect(jsonPath("$.name").exists())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.products.href").exists())
                .andExpect(jsonPath("$._links.purchase.href").exists());
    }
}
```

Ví dụ giả định dữ liệu fixture cho sản phẩm `10` có trạng thái `available = true`. Cần chuẩn bị fixture hoặc mock service để kết quả không phụ thuộc dữ liệu môi trường. Với sản phẩm không khả dụng, bổ sung kiểm thử xác nhận quan hệ `purchase` không xuất hiện:

```java
mockMvc.perform(get("/products/11").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.purchase").doesNotExist());
```

Trong kiểm thử, có thể kiểm tra link theo thuộc tính `href`, nhưng khi kiểm tra khả năng tiến hóa hợp đồng, nên ưu tiên kiểm tra relation và hành vi của client. Tránh cố định host, port hoặc toàn bộ URL nếu chúng phụ thuộc môi trường triển khai.

## 10. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng `EntityModel` chỉ nhận JPA entity | DTO hoặc projection bị bỏ qua dù có thể làm content. | Dùng bất kỳ kiểu content phù hợp với hợp đồng API. |
| Bọc một `List<T>` trong `EntityModel` | Collection không có cấu trúc hypermedia chuẩn. | Dùng `CollectionModel` hoặc `PagedModel`. |
| Dùng entity có quan hệ phức tạp làm content mà không kiểm soát | Có thể lộ trường nội bộ, phát sinh vòng tham chiếu hoặc lazy loading. | Dùng DTO hoặc projection. |
| Tạo link bằng chuỗi URL rải rác | Mapping đổi khiến liên kết không đồng bộ. | Dùng `linkTo(methodOn(...))`. |
| Thêm link hành động ở mọi trạng thái | Client nhìn thấy hành động không khả dụng. | Thêm link theo trạng thái và quy tắc nghiệp vụ. |
| Xem link là cơ chế bảo mật | Client vẫn có thể gọi URI đã biết. | Kiểm tra quyền ở endpoint. |
| Chỉ kiểm thử content mà bỏ qua `_links` | API có thể mất khả năng điều hướng mà test vẫn xanh. | Kiểm tra relation, href và media type. |

## 11. Quy trình quyết định và áp dụng

Khi thiết kế một endpoint, hãy tự trả lời lần lượt:

1. Endpoint trả về một tài nguyên, một collection hay một trang? Nếu là một tài nguyên, tiếp tục xem xét `EntityModel`.
2. Kiểu dữ liệu hiện có đã đúng với hợp đồng API chưa? Nếu chưa, chuyển đổi sang DTO trước khi bọc.
3. Tài nguyên cần các relation nào? Xác định `self` và các liên kết nghiệp vụ có ý nghĩa.
4. Liên kết nào phụ thuộc trạng thái? Chỉ thêm những hành động đang khả dụng.
5. Logic chuyển đổi có được dùng lại ở nhiều nơi? Nếu có, đưa vào `RepresentationModelAssembler`.
6. Phản hồi có được tuần tự hóa đúng media type không? Kiểm thử HAL hoặc định dạng đã chọn.
7. Client có thể điều hướng theo relation mà không phải tự dựng URL không? Kiểm thử hợp đồng theo quan hệ.

`EntityModel<T>` phù hợp khi bạn muốn bọc một đối tượng nội dung đã có và bổ sung liên kết hypermedia cho tài nguyên đơn. Dùng nó cùng DTO và assembler giúp API giữ cấu trúc dữ liệu rõ ràng, link nhất quán và client có thể khám phá các bước tiếp theo qua relation. Khi phản hồi là tập hợp, trang dữ liệu hoặc một cấu trúc biểu diễn đặc thù, hãy chọn kiểu mô hình tương ứng thay vì ép tất cả vào một wrapper.

## Tài liệu tham khảo

- [Spring HATEOAS – Representation Models](https://docs.spring.io/spring-hateoas/reference/server/representation-models.html)
- [Spring HATEOAS – Building links](https://docs.spring.io/spring-hateoas/reference/server/links.html)
- [Spring HATEOAS – Hypermedia representations](https://docs.spring.io/spring-hateoas/reference/mediatypes.html)
