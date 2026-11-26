# PagedResourcesAssembler cho Page

## 1. Từ kết quả phân trang đến biểu diễn web có điều hướng

Trong chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**, Page là kết quả ở tầng truy vấn, còn response HTTP cần một hợp đồng mà client có thể đọc và điều hướng.

Một danh sách sản phẩm phân trang thường cần:

- Dữ liệu của các phần tử thuộc trang hiện tại.
- Kích thước trang và số trang hiện tại.
- Tổng số phần tử, tổng số trang nếu API lựa chọn cung cấp.
- Liên kết tới chính trang đó và các trang có thể điều hướng.
- Liên kết tới từng sản phẩm khi hợp đồng hypermedia yêu cầu.

PagedResourcesAssembler chuyển Page thành mô hình phân trang của Spring HATEOAS. Nó giúp tập trung việc xây dựng metadata và liên kết điều hướng, thay vì để mỗi controller tự ghép URL.

Luồng sử dụng điển hình:

~~~text
HTTP request
    → Pageable và bộ lọc đã được xử lý
    → service/repository trả Page<T>
    → assembler của phần tử tạo representation
    → PagedResourcesAssembler tạo mô hình của trang
    → HTTP message converter serialize theo media type
~~~

Bài viết minh họa Spring MVC và API của Spring Data Commons 3.5.1. Những cấu hình serialization, URL và module dữ liệu thực tế vẫn cần được xác nhận trong ứng dụng sử dụng.

## 2. Nhận diện đúng các kiểu và package

Tên PagedResourcesAssembler được giữ lại dù kiểu kết quả hiện đại mang tên PagedModel. Khi đọc ví dụ cũ, cần kiểm tra cả package lẫn tên method.

| Kiểu | Package | Vai trò trong bài |
| --- | --- | --- |
| Page<T> | org.springframework.data.domain | Nội dung và thông tin phân trang từ đường truy vấn |
| PagedResourcesAssembler<T> | org.springframework.data.web | Chuyển Page sang representation có liên kết |
| PagedModel<T> | org.springframework.hateoas | Mô hình collection phân trang hỗ trợ hypermedia |
| EntityModel<T> | org.springframework.hateoas | Bọc dữ liệu một phần tử và các link của phần tử đó |
| RepresentationModelAssembler<T, R> | org.springframework.hateoas.server | Ánh xạ một phần tử thành representation R |

Điểm dễ nhầm là Spring Data còn có lớp **org.springframework.data.web.PagedModel<T>**. Lớp này cung cấp biểu diễn JSON ổn định cho Page, có từ Spring Data Commons 3.3; nó không phải kiểu PagedModel có hypermedia mà PagedResourcesAssembler trả về. [PagedModel của Spring Data](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/web/PagedModel.html), [PagedModel của Spring HATEOAS](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)

Trong bài này, khi code import PagedModel, luôn dùng:

~~~java
import org.springframework.hateoas.PagedModel;
~~~

Không thay import bằng org.springframework.data.web.PagedModel chỉ vì IDE gợi ý cùng tên.

## 3. Assembler cung cấp gì?

Lời gọi đơn giản:

~~~java
PagedModel<EntityModel<ProductView>> model =
        pageAssembler.toModel(page);
~~~

Ở đây page có kiểu Page<ProductView>, còn pageAssembler có kiểu PagedResourcesAssembler<ProductView>.

Ba phần được kết hợp là:

1. Nội dung trang được chuyển thành các representation.
2. Metadata được lấy từ Page.
3. Các pagination link được tạo theo thông tin trang và URI phù hợp.

Overload toModel(page) bọc từng phần tử bằng EntityModel, nhưng không tự phát minh link chi tiết cho mỗi ProductView. Nếu cần item-level self link, truyền thêm assembler của phần tử. [API PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/web/PagedResourcesAssembler.html)

### 3.1. Không dùng assembler để thay thế tầng truy vấn

Assembler không tự chọn store, tạo derived query, áp dụng Query by Example hoặc cấp quyền đọc dữ liệu. Trước khi nhận Page, service cần xác định đúng:

- Bộ lọc và phạm vi dữ liệu mà người gọi được phép xem.
- Page size và các property sort được hỗ trợ.
- Kiểu dữ liệu cần trả: entity, projection hoặc DTO.
- Ý nghĩa của totalElements đối với tập kết quả ấy.

Một representation đẹp không sửa được Page chứa sai dữ liệu hoặc total của một phạm vi khác.

## 4. Chuẩn bị Spring Data Web và hypermedia

Ứng dụng cần các thành phần tương ứng:

- Spring MVC để xử lý controller và HTTP representation.
- Spring Data Web để resolve Pageable và PagedResourcesAssembler.
- Spring HATEOAS cùng cấu hình media type dự định sử dụng.

Trong cấu hình thủ công, EnableSpringDataWebSupport bật các thành phần web của Spring Data và phát hiện hỗ trợ HATEOAS trên classpath. Trong Spring Boot, cần xác nhận cấu hình tự động tương ứng đang hoạt động, tránh đăng ký lại resolver một cách chồng chéo. [Spring Data Web và hypermedia support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

PagedResourcesAssembler có thể được nhận trực tiếp qua tham số handler. Resolver của nó gắn assembler với Pageable phù hợp của method, nhờ đó việc sinh link có thể dùng cùng ngữ cảnh tham số phân trang. [Argument resolver của assembler, bản 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PagedResourcesAssemblerArgumentResolver.java)

Chỉ thêm annotation produces cho HAL không tự đăng ký mọi serializer cần thiết. Cấu hình message converter và media type phải thực sự hỗ trợ mô hình được trả về.

## 5. Ví dụ DTO và assembler cho từng sản phẩm

Ví dụ dùng Java 17 trở lên. Các public type dưới đây được hiểu là các type riêng trong cùng package.

### 5.1. DTO dành cho API

~~~java
package com.example.catalog;

import java.math.BigDecimal;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "product", collectionRelation = "products")
public record ProductView(Long id, String name, BigDecimal price) {
}
~~~

DTO làm rõ field mà API công bố. Annotation Relation đặt tên quan hệ collection dùng trong ví dụ HAL; tên này cần được giữ ổn định nếu client đã sử dụng.

Service cung cấp hợp đồng đọc:

~~~java
package com.example.catalog;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductReadService {

    Page<ProductView> search(String name, Pageable pageable);

    ProductView get(Long id);
}
~~~

Implementation của service phải truy vấn đúng phạm vi được phép và dùng module dữ liệu phù hợp. Ví dụ tập trung vào biểu diễn kết quả nên không giả định entity mapping hay backend cụ thể.

### 5.2. Assembler của một phần tử

~~~java
package com.example.catalog;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder
        .linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder
        .methodOn;

@Component
public class ProductModelAssembler
        implements RepresentationModelAssembler<
                ProductView, EntityModel<ProductView>> {

    @Override
    public EntityModel<ProductView> toModel(ProductView product) {
        return EntityModel.of(
                product,
                linkTo(methodOn(ProductController.class)
                        .detail(product.id()))
                        .withSelfRel());
    }
}
~~~

Assembler này tạo link chi tiết của sản phẩm. Nó không tạo first, prev, next hoặc last cho danh sách; đó là trách nhiệm của assembler trang.

Nên giữ phép ánh xạ này nhẹ và có chủ đích. Nếu mapper đọc một quan hệ lazy hoặc tự gọi repository cho từng item, bước dựng representation có thể làm phát sinh thêm I/O.

## 6. Controller nhận Page và trả PagedModel

~~~java
package com.example.catalog;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductReadService service;
    private final ProductModelAssembler itemAssembler;

    public ProductController(
            ProductReadService service,
            ProductModelAssembler itemAssembler) {
        this.service = service;
        this.itemAssembler = itemAssembler;
    }

    @GetMapping(
            value = "/products",
            produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<EntityModel<ProductView>> list(
            @RequestParam(name = "name", defaultValue = "") String name,
            @PageableDefault(size = 2, sort = "id") Pageable pageable,
            PagedResourcesAssembler<ProductView> pageAssembler) {

        Page<ProductView> page = service.search(name, pageable);
        return pageAssembler.toModel(page, itemAssembler);
    }

    @GetMapping(
            value = "/products/{id}",
            produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<ProductView> detail(
            @PathVariable("id") Long id) {

        return itemAssembler.toModel(service.get(id));
    }
}
~~~

Page size 2 chỉ làm ví dụ ngắn và dễ quan sát. Ứng dụng thực tế cần chọn mặc định, giới hạn kích thước và quyền ghi đè phù hợp.

Generic của các thành phần phải khớp:

~~~text
Page<ProductView>
    + PagedResourcesAssembler<ProductView>
    + RepresentationModelAssembler<
          ProductView, EntityModel<ProductView>>
    → PagedModel<EntityModel<ProductView>>
~~~

Nếu muốn mỗi item là một model tự định nghĩa kế thừa RepresentationModel, có thể đổi kiểu kết quả của item assembler tương ứng. Không bọc thêm EntityModel một cách máy móc quanh một model vốn đã có link.

## 7. Đọc một response HAL cụ thể

Giả sử request:

~~~http
GET /products?name=book&page=1&size=2&sort=id,asc
Accept: application/hal+json
~~~

Kết quả truy vấn có 5 sản phẩm phù hợp, trang hiện tại chứa 2 sản phẩm. Với đánh số từ 0 và cấu hình HAL của ví dụ, response có thể có dạng:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 103,
        "name": "Java book",
        "price": 120000,
        "_links": {
          "self": {
            "href": "https://api.example.com/products/103"
          }
        }
      },
      {
        "id": 104,
        "name": "Spring book",
        "price": 150000,
        "_links": {
          "self": {
            "href": "https://api.example.com/products/104"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "https://api.example.com/products?name=book&page=0&size=2&sort=id,asc"
    },
    "prev": {
      "href": "https://api.example.com/products?name=book&page=0&size=2&sort=id,asc"
    },
    "self": {
      "href": "https://api.example.com/products?name=book&page=1&size=2&sort=id,asc"
    },
    "next": {
      "href": "https://api.example.com/products?name=book&page=2&size=2&sort=id,asc"
    },
    "last": {
      "href": "https://api.example.com/products?name=book&page=2&size=2&sort=id,asc"
    }
  },
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Đây là biểu diễn minh họa, không phải một bản chụp output đã chạy. Host, thứ tự query parameter và cách percent-encode có thể khác theo cấu hình.

Phải phân biệt:

- _embedded.products: nội dung trang hiện tại.
- _links ở cấp gốc: điều hướng của collection phân trang.
- _links.self bên trong item: tài nguyên chi tiết của sản phẩm.
- page: metadata của kết quả phân trang.

HAL dùng cấu trúc _links và _embedded để thể hiện các quan hệ. Không suy rằng chỉ cần có đối tượng PagedModel là JSON ở mọi media type đều mang đúng cấu trúc HAL. [Spring HATEOAS và HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)

## 8. Metadata và link điều hướng phải nhất quán

Với Page có chỉ số nội bộ 1, size 2, totalElements 5:

| Thuộc tính | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| size | 2 | Kích thước trang được dùng |
| number | 1 | Trang thứ hai theo cách đánh số từ 0 |
| totalElements | 5 | Tổng số phần tử của tập kết quả |
| totalPages | 3 | Số trang theo total và size |

Size không phải lúc nào cũng bằng số item trong response: trang cuối của ví dụ chỉ còn một phần tử.

Ở cấu hình mặc định của assembler 3.5.1:

| Trạng thái Page | Các rel điều hướng điển hình |
| --- | --- |
| Trang đầu, có trang sau | self, next, first, last |
| Trang giữa | self, prev, next, first, last |
| Trang cuối, có trang trước | self, prev, first, last |
| Một trang, không có trước/sau | self |
| Không có dữ liệu ở trang đầu | self |

First và last mặc định được thêm khi trang có khả năng điều hướng trước hoặc sau. Có thể yêu cầu luôn thêm chúng bằng setForceFirstAndLastRels(true). Thiết lập này không tạo thêm dữ liệu hoặc thay đổi total của Page. [Cơ chế pagination links, bản 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PagedResourcesAssembler.java)

Không đánh giá sự tồn tại của prev chỉ bằng việc content rỗng hay không. Một request vượt quá trang cuối vẫn có thể mang chỉ số trang lớn và có đường quay lại, tùy Page được trả về.

Ứng dụng cần chọn chính sách cho request ngoài phạm vi. Assembler không tự chuyển một Page ngoài phạm vi thành HTTP 404 hoặc tự chạy lại query ở trang cuối.

## 9. Giữ bộ lọc và cấu hình Pageable trong các link

Link next phải tiếp tục truy vấn cùng tập dữ liệu:

~~~text
Hiện tại:
    name=book, page=1, size=2, sort=id ASC

Trang sau:
    name=book, page=2, size=2, sort=id ASC
~~~

Trong luồng dùng URI request hiện tại, assembler có cơ sở để giữ các query parameter không phải paging và điều chỉnh tham số phân trang. Khi dùng base URI hoặc link tự cung cấp, chính URI đó phải chứa bộ lọc cần thiết.

Không kiểm tra link chỉ bằng cách tìm chuỗi page=2. Cần xác nhận cả path, filter, size, sort và cách đánh số.

### 9.1. Tên tham số tùy biến và đánh số từ 1

Nếu resolver dùng tên p và limit, link được tạo cần dùng p và limit. Nếu request đánh số trang từ 1, liên kết phải tuân thủ cách đánh số đó.

HateoasPageableHandlerMethodArgumentResolver dùng cấu hình resolver để bổ sung tham số vào URI. Trong assembler 3.5.1, metadata number cũng được điều chỉnh khi resolver dùng one-indexed parameters. Vì vậy, không mặc định metadata luôn bắt đầu từ 0 trong mọi cấu hình. [Resolver sinh URI](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/HateoasPageableHandlerMethodArgumentResolver.java), [Tạo metadata của assembler](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PagedResourcesAssembler.java)

Không tự new một assembler với resolver mặc định trong controller rồi kỳ vọng nó biết các tùy biến của resolver ứng dụng. Nên dùng assembler được hạ tầng web cung cấp hoặc chủ động truyền đúng resolver khi có nhu cầu cấu hình riêng.

### 9.2. Nhiều Pageable trong một handler

Khi handler có nhiều bộ phân trang, cần qualifier tương ứng cho cả Pageable và assembler:

~~~java
public void dashboard(
        @Qualifier("featured") Pageable featured,
        @Qualifier("recent") Pageable recent,
        @Qualifier("featured")
        PagedResourcesAssembler<ProductView> featuredAssembler,
        @Qualifier("recent")
        PagedResourcesAssembler<ProductView> recentAssembler) {

    // Mỗi assembler làm việc với Page tương ứng.
}
~~~

Qualifier thuộc org.springframework.beans.factory.annotation.Qualifier. Theo quy ước resolver chuẩn, request có thể dùng featured_page và recent_page cùng các tham số liên quan.

Đừng chọn assembler chỉ dựa vào generic ProductView: hai bộ phân trang có thể cùng kiểu nội dung. Hạ tầng cần biết chính tham số Pageable nào đang được biểu diễn. [Ghép assembler với Pageable theo qualifier](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PageableMethodParameterUtils.java)

## 10. Cung cấp self link có chủ đích

Khi URI công khai cần được xác định riêng, có overload nhận link:

~~~java
Link self = Link.of(
        "https://api.example.com/products"
                + "?name=book&page=1&size=2&sort=id,asc")
        .withSelfRel();

PagedModel<EntityModel<ProductView>> model =
        pageAssembler.toModel(page, itemAssembler, self);
~~~

Link thuộc org.springframework.hateoas.Link. URL cố định ở đây chỉ để minh họa API; khi xây dựng URL thực tế, dùng URI/link builder và encode đầu vào đúng cách.

Link truyền vào đóng vai trò self và cơ sở để tạo link điều hướng. Nếu chỉ truyền /products mà bỏ bộ lọc name, assembler không thể suy ra name từ Page.

Một self link tự cung cấp cũng phải phản ánh đúng page và size thực sự được dùng. Không dựa vào việc assembler sẽ tự sửa lại mọi chi tiết của self link khi request đã bị giới hạn page size.

Đối với ứng dụng sau reverse proxy, cần kiểm tra scheme, host và path công khai trong link. Cấu hình forwarded header phải gắn với hạ tầng proxy được tin cậy; link tới hostname nội bộ không hữu dụng với client bên ngoài. [Forwarded headers trong Spring HATEOAS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder.forwarded-headers)

## 11. Trang rỗng và kiểu collection

Khi không có phần tử, serializer có thể thiếu thông tin để suy ra collection relation từ item. Nếu hợp đồng yêu cầu một relation rỗng tường minh, có thể dùng toEmptyModel:

~~~java
@GetMapping(
        value = "/products",
        produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<?> list(
        @RequestParam(name = "name", defaultValue = "") String name,
        @PageableDefault(size = 2, sort = "id") Pageable pageable,
        PagedResourcesAssembler<ProductView> pageAssembler) {

    Page<ProductView> page = service.search(name, pageable);

    if (page.isEmpty()) {
        return pageAssembler.toEmptyModel(page, ProductView.class);
    }

    return pageAssembler.toModel(page, itemAssembler);
}
~~~

Đây là biến thể thay cho method list trước đó, không phải một endpoint thứ hai cùng mapping.

toEmptyModel yêu cầu Page không có content và nhận kiểu phần tử để tạo embedded collection rỗng. Với cấu hình relation/HAL phù hợp, có thể biểu diễn products là một mảng rỗng thay vì để client phải đoán kiểu collection. Cần kiểm thử JSON thực tế với cấu hình của ứng dụng.

Phải giữ Page gốc khi xử lý rỗng. Không tùy tiện thay một trang ngoài phạm vi có total đã biết bằng Page.empty() rồi làm mất metadata truy vấn. [Các overload cho empty model](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/web/PagedResourcesAssembler.html)

Kiểu trả về PagedModel<?> ở biến thể này phản ánh việc nhánh rỗng sử dụng embedded wrapper nội bộ. Không ép kiểu không kiểm tra chỉ để giữ một chữ ký generic đẹp hơn.

## 12. Ánh xạ Page và giữ đúng metadata

Nếu repository trả Page<Product>, có thể ánh xạ một-một sang DTO bằng Page.map:

~~~java
Page<ProductView> views = products.map(product ->
        new ProductView(
                product.getId(),
                product.getName(),
                product.getPrice()));
~~~

Sau đó dùng PagedResourcesAssembler<ProductView> cho Page<ProductView>.

Điểm cần tránh là chỉ lấy content, map thành List rồi tạo một Page mới không truyền thông tin paging/total phù hợp. Cách đó có thể khiến link và metadata phản ánh một danh sách cục bộ thay vì toàn bộ kết quả query.

Cũng không nên:

~~~text
Query một Page của toàn bộ dữ liệu
    → bỏ các item không có quyền ở bộ nhớ
    → vẫn giữ total ban đầu
    → tạo PagedModel
~~~

Cách làm này có thể tạo trang thiếu phần tử, tổng số sai hoặc metadata lộ phạm vi ngoài quyền. Điều kiện quyền và bộ lọc cần được xử lý trong đường truy vấn thích hợp; phép ánh xạ representation nên giữ cùng tập kết quả.

Projection giúp chỉ lấy dữ liệu cần từ store khi module/query hỗ trợ. DTO ở tầng web và projection ở tầng truy vấn có thể phối hợp, nhưng không đồng nhất về trách nhiệm.

## 13. Assembler không xóa chi phí của Page

Page có totalElements và totalPages, nên đường query thường phải xác định tổng số kết quả. Chi phí đó phụ thuộc module, query và khả năng tối ưu; không nên khẳng định mọi Page luôn thực hiện đúng hai câu truy vấn.

PagedResourcesAssembler không tự tạo câu count mới để thay cho repository. Nó sử dụng thông tin của Page và gọi assembler cho từng phần tử. Tuy nhiên, code ánh xạ hoặc getter của entity có thể gây I/O ngoài dự kiến.

Nếu API chỉ cần biết có phần tiếp theo mà không cần tổng số, hãy đánh giá Slice và cơ chế biểu diễn phù hợp thay vì bịa total để dùng assembler của Page.

Một số giới hạn vẫn cần được xử lý riêng:

- Sort phải hợp lệ và có thứ tự phân biệt khi các giá trị chính bằng nhau.
- Offset sâu có thể tốn chi phí tùy store.
- Dữ liệu thay đổi giữa hai lần theo link có thể dịch chuyển vị trí phần tử.
- Count và content cần có cùng điều kiện lọc và phạm vi quyền.
- Liên kết hiện diện không thay thế kiểm tra quyền tại endpoint đích.

Metadata của Page mô tả kết quả của đường đọc đã chọn; nó không tự tạo ra một snapshot bất biến xuyên nhiều request.

## 14. Kiểm thử assembler mà không cần database

Có thể kiểm thử cấu trúc model và link bằng một PageImpl tự tạo. Ví dụ JUnit 5:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.HateoasPageableHandlerMethodArgumentResolver;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.web.util.UriComponentsBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductPageAssemblerTest {

    @Test
    void middlePageKeepsFilterAndBuildsNextLink() {
        var resolver =
                new HateoasPageableHandlerMethodArgumentResolver();

        var base = UriComponentsBuilder.fromUriString(
                "https://api.example.com/products?name=book").build();

        var assembler =
                new PagedResourcesAssembler<ProductView>(resolver, base);

        Page<ProductView> page = new PageImpl<>(
                List.of(
                        new ProductView(
                                103L, "Java book", new BigDecimal("120000")),
                        new ProductView(
                                104L, "Spring book", new BigDecimal("150000"))),
                PageRequest.of(1, 2, Sort.by("id")),
                5);

        var model = assembler.toModel(page);

        assertEquals(2, model.getContent().size());
        assertEquals(1L, model.getMetadata().getNumber());
        assertEquals(5L, model.getMetadata().getTotalElements());
        assertEquals(3L, model.getMetadata().getTotalPages());

        String href = model.getRequiredLink(IanaLinkRelations.NEXT)
                .getHref();

        var next = UriComponentsBuilder.fromUriString(href).build();

        assertEquals("/products", next.getPath());
        assertEquals("book", next.getQueryParams().getFirst("name"));
        assertEquals("2", next.getQueryParams().getFirst("page"));
        assertEquals("2", next.getQueryParams().getFirst("size"));
        assertEquals("id,asc",
                next.getQueryParams().getFirst("sort"));

        assertTrue(model.hasLink(IanaLinkRelations.PREV));

        // toModel(page) không tự tạo self link cho từng ProductView.
        var firstItem = model.getContent().iterator().next();
        assertFalse(firstItem.hasLink(IanaLinkRelations.SELF));
    }
}
~~~

Test dùng base URI tường minh nên không cần current request. Trong dự án thực tế, đặt test trong package phù hợp hoặc import ProductView.

Các đoạn code là minh họa thiết kế kiểm thử, không phải xác nhận đã chạy thành công trong một môi trường cụ thể.

Test model trên chưa chứng minh JSON HAL đúng. Cần thêm kiểm thử HTTP với cấu hình thật:

| Nhóm kiểm thử | Nội dung cần xác nhận |
| --- | --- |
| Trang đầu/giữa/cuối | Rel hiện diện hoặc vắng đúng trạng thái |
| Chỉ một trang | Không xuất hiện next/prev không hợp lệ |
| Rỗng | Relation collection và metadata theo hợp đồng |
| Bộ lọc | Theo next vẫn dùng cùng filter |
| Sort nhiều order | Link không làm mất thứ tự hoặc direction |
| One-indexed | Link và metadata nhất quán với cấu hình |
| Nhiều Pageable | Query parameter có đúng qualifier |
| HAL negotiation | Content-Type và cấu trúc _embedded/_links đúng |
| Proxy/public URL | Scheme, host, context path dùng được bên ngoài |
| DTO và quyền | Không xuất hiện field hoặc tổng số ngoài phạm vi |

Nên parse URI để so sánh query parameter; thứ tự tham số và chi tiết encode không phải tiêu chí nghiệp vụ. Với HTTP test, có thể lấy next link từ response rồi gửi request tiếp theo để kiểm chứng việc điều hướng thực sự hoạt động.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân cần xem xét |
| --- | --- |
| Import PagedModel nhưng không khớp generic | Chọn nhầm lớp của Spring Data thay vì Spring HATEOAS |
| Có pagination link nhưng item không có self | Chỉ dùng overload toModel(page) |
| Link next mất bộ lọc | Base URI hoặc self link tự cung cấp thiếu filter |
| Metadata đúng nhưng URL đánh số sai | Resolver sinh link không cùng cấu hình với resolver đọc request |
| Request có nhiều Pageable nhưng link dùng sai prefix | Thiếu hoặc sai qualifier của assembler |
| JSON khác cấu trúc HAL dự kiến | Media type, message converter hoặc relation provider chưa phù hợp |
| Mảng rỗng không có relation mong muốn | Chưa cung cấp thông tin kiểu hoặc chưa kiểm thử empty representation |
| Total bị đổi sau khi map | Tạo Page mới từ content mà làm mất metadata |
| Dựng response phát sinh nhiều query | Mapper hoặc getter tải thêm dữ liệu |
| Link đã có nhưng endpoint đích từ chối | Link là gợi ý điều hướng; quyền vẫn được kiểm tra khi truy cập |

## 16. Tự kiểm tra

1. PagedResourcesAssembler nhận Page và trả kiểu nào khi gọi toModel(page)?
2. Vì sao toModel(page) không bảo đảm từng item có self link?
3. Hai lớp PagedModel khác package có khác trách nhiệm gì?
4. Trong response có 2 item nhưng size bằng 5, đây có nhất thiết là lỗi không?
5. Vì sao next link phải giữ bộ lọc và sort?
6. Khi có hai Pageable cùng kiểu nội dung, qualifier giúp giải quyết vấn đề gì?
7. Khi nào cần toEmptyModel và vì sao nên giữ Page gốc?
8. Kiểm thử model khác kiểm thử HAL serialization ở điểm nào?
9. Assembler có tự giới hạn quyền, loại bỏ count query hoặc bảo đảm snapshot giữa các trang không?

Một response phân trang đáng tin cậy cần nội dung, metadata và liên kết cùng mô tả một tập kết quả. PagedResourcesAssembler giúp biểu diễn Page theo hướng đó khi được kết hợp với query đúng phạm vi, DTO phù hợp, cấu hình resolver nhất quán và media type đã được kiểm thử.
