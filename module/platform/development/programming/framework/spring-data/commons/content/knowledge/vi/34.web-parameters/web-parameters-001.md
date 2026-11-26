# Kích hoạt @EnableSpringDataWebSupport

## 1. Vai trò trong chương Tham số web

Một API danh sách sản phẩm thường nhận yêu cầu:

```http
GET /products?page=1&size=15&sort=name,asc&sort=id,asc
```

Controller cần hiểu chỉ số trang, kích thước trang và thứ tự sắp xếp, rồi chuyển những yêu cầu đó xuống lớp truy vấn. Nếu mỗi controller tự đọc chuỗi, chuyển kiểu và dựng đối tượng phân trang, các endpoint dễ sử dụng quy ước khác nhau.

Trong module **SPRING_DATA_COMMONS**, `@EnableSpringDataWebSupport` là điểm kích hoạt tích hợp giữa **Spring MVC** và các abstraction của Spring Data. Annotation thuộc package:

```java
import org.springframework.data.web.config.EnableSpringDataWebSupport;
```

Sau khi cấu hình được nạp, các thành phần tích hợp có thể chuyển tham số HTTP thành `Pageable`, `Sort` và hỗ trợ chuyển định danh thành đối tượng domain thông qua repository. Phạm vi kích hoạt được mô tả trong [API của EnableSpringDataWebSupport](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/web/config/EnableSpringDataWebSupport.html).

Bài này tập trung vào cấu hình và hành vi ở ranh giới HTTP. Kiến thức về CRUD, derived queries, projection, Query by Example, metadata và auditing vẫn được áp dụng ở lớp dữ liệu theo khả năng của từng module lưu trữ. Annotation web không tự bổ sung các khả năng truy vấn đó cho repository.

Sau bài học, bạn có thể:

- Chọn cách kích hoạt phù hợp với MVC cấu hình thủ công hoặc Spring Boot.
- Giải thích đường đi từ query parameter đến `Pageable` và `Sort`.
- Thiết lập mặc định, giới hạn kích thước trang và quy ước đánh số trang.
- Phân biệt binding tham số, truy vấn repository và biểu diễn response.
- Nhận diện trường hợp cần kiểm tra sort hoặc nhận ID tường minh.

## 2. Những thành phần được kích hoạt

| Thành phần | Công việc tại lớp web | Điều kiện hoặc giới hạn |
| --- | --- | --- |
| `PageableHandlerMethodArgumentResolver` | Dựng `Pageable` cho tham số controller từ request | Phải được đăng ký vào hạ tầng argument resolver của MVC |
| `SortHandlerMethodArgumentResolver` | Dựng `Sort` từ tham số sắp xếp | Ứng dụng vẫn cần kiểm tra khóa sort theo hợp đồng API |
| `DomainClassConverter` | Chuyển định danh sang đối tượng domain được repository quản lý | Cần repository phù hợp và khả năng chuyển kiểu ID |
| Tích hợp Spring HATEOAS khi thư viện hiện diện | Hỗ trợ resolver và assembler cho biểu diễn có liên kết | Không tự thêm liên kết vào mọi response |

Các thành phần hỗ trợ JSON cũng có thể được đăng ký tùy dependency và module dữ liệu. Không nên hiểu rằng thêm annotation là mọi kiểu dữ liệu của mọi kho đều có thể được đọc hoặc ghi qua HTTP. Xem [Javadoc của annotation](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/web/config/EnableSpringDataWebSupport.html).

Luồng xử lý phân trang:

```text
HTTP request: page, size, sort
               |
               v
Spring MVC chọn controller và giải quyết tham số phương thức
               |
               v
Pageable resolver phối hợp với Sort resolver
               |
               v
Pageable(pageNumber=1, pageSize=15, sort=name ASC)
               |
               v
Controller -> service -> repository thích hợp
               |
               v
Kết quả truy vấn -> DTO và metadata phân trang -> HTTP response
```

Tạo `Pageable` chưa thực hiện truy vấn dữ liệu. Service hoặc repository phải nhận đối tượng này và áp dụng nó vào thao tác đọc.

Có ba phần cấu hình riêng:

| Nhu cầu | Phần chịu trách nhiệm |
| --- | --- |
| Nhận request và gọi controller | Spring MVC |
| Đọc `Pageable`, `Sort` hoặc chuyển ID sang domain | Spring Data web support |
| Tạo repository và truy cập cơ sở dữ liệu | Module lưu trữ cùng cấu hình persistence |

Bật web support không tự tạo `DataSource`, `EntityManager`, kết nối MongoDB hay repository bean. Annotation cũng không tự xuất bản repository thành REST endpoint; ứng dụng vẫn cần controller hoặc cơ chế xuất bản API khác.

## 3. Kích hoạt trong Spring MVC cấu hình thủ công

### 3.1. Dependency và application context

Ứng dụng cần Spring MVC và Spring Data Commons ở các phiên bản tương thích. Nếu truy cập dữ liệu thật, cần thêm module lưu trữ tương ứng và cấu hình repository của module đó. Nên dùng dependency management của nền tảng để giữ các phiên bản đồng bộ.

Ví dụ dành cho ứng dụng quản lý cấu hình MVC tường minh:

```java
package example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@EnableSpringDataWebSupport
public class CatalogWebConfiguration {
}
```

Class phải được đăng ký trong application context phục vụ `DispatcherServlet`, chẳng hạn thông qua cơ chế import hoặc đăng ký cấu hình của ứng dụng. Một class nằm ngoài phạm vi được nạp vào context không kích hoạt chức năng nào.

`@EnableWebMvc` thiết lập hạ tầng MVC tường minh; `@EnableSpringDataWebSupport` thêm tích hợp Spring Data vào hạ tầng đó. Đây là cách cấu hình được minh họa trong [tài liệu web support của Commons](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

Nếu ứng dụng đã có cấu hình MVC, tích hợp annotation vào cấu hình hiện hữu. Controller, service và repository vẫn phải được đăng ký riêng; class trên chỉ minh họa phần kích hoạt web support.

### 3.2. Phạm vi Spring MVC

Bài học nói về Spring MVC trên Servlet stack. Với WebFlux, phải sử dụng cơ chế resolver và cấu hình phù hợp với stack reactive của phiên bản đang dùng. Không thể suy rằng chỉ thêm annotation cấu hình MVC là ứng dụng reactive đã được thiết lập đúng.

Tương tự, việc resolve được `Pageable` không chứng minh một reactive repository có phương thức trả `Page<T>` giống repository đồng bộ. Cần kiểm tra hợp đồng truy vấn theo module lưu trữ.

## 4. Trường hợp Spring Boot

Trong ứng dụng Boot dùng Servlet MVC, khi có dependency cần thiết và thỏa điều kiện auto-configuration, Boot thường cấu hình Spring Data web support sẵn. Controller khi đó có thể nhận `Pageable` mà không cần thêm annotation thủ công. [SpringDataWebAutoConfiguration của Boot 3.x](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/data/web/SpringDataWebAutoConfiguration.html) mô tả cấu hình tự động này tương đương việc bật web support của Spring Data.

Cách lựa chọn:

1. Với MVC cấu hình thủ công, chủ động dùng `@EnableSpringDataWebSupport`.
2. Với Boot có auto-configuration hoạt động, ưu tiên cấu hình do Boot cung cấp.
3. Khi thay thế bằng cấu hình thủ công, kiểm tra resolver thực tế và những thiết lập còn được áp dụng.

Không thêm `@EnableWebMvc` vào ứng dụng Boot chỉ để nhận `Pageable`. Annotation đó chuyển sang quản lý MVC tường minh và có thể làm thay đổi các tiện ích MVC mà Boot đang cấu hình.

Auto-configuration của Boot có điều kiện liên quan đến sự hiện diện của `PageableHandlerMethodArgumentResolver`. Nếu cấu hình thủ công tạo resolver, một phần cấu hình tự động có thể nhường quyền. Vì vậy không mặc định rằng property Boot vẫn điều khiển resolver tự đăng ký. Xem [các điều kiện auto-configuration](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/data/web/SpringDataWebAutoConfiguration.html).

Ví dụ property khi dùng hướng auto-configuration:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
      sort:
        sort-parameter: sort
```

Giới hạn `100` là chính sách ứng dụng trong ví dụ, không phải mặc định framework. Các tên property được mô tả trong [danh mục cấu hình Boot 3.5](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).

Đoạn YAML này là ví dụ học tập; không phải nội dung của file metadata bài học.

## 5. Từ query parameter đến Pageable và Sort

### 5.1. Quy ước cơ bản

Khi chưa tùy biến resolver và chưa có annotation mặc định tại tham số phương thức:

| Tham số | Ý nghĩa | Quy ước cơ bản |
| --- | --- | --- |
| `page` | Chỉ số trang | Bắt đầu từ `0`, mặc định `0` |
| `size` | Số phần tử tối đa của trang | Mặc định `20` |
| `sort` | Thuộc tính và hướng sắp xếp | Có thể lặp để diễn đạt nhiều thứ tự |

Request:

```http
GET /products?page=1&size=15&sort=name,asc&sort=id,desc
```

Mang thông tin tương đương:

```java
PageRequest.of(
    1,
    15,
    Sort.by(
        Sort.Order.asc("name"),
        Sort.Order.desc("id")
    )
);
```

`PageRequest` và `Sort` thuộc package `org.springframework.data.domain`. Trang `1` là trang thứ hai. Với phân trang theo offset, vị trí bắt đầu tương ứng là `1 * 15 = 15`.

Tham số `sort=name,id,asc` diễn đạt cùng hướng tăng dần cho hai thuộc tính. Khi cần hướng khác nhau, dùng các tham số `sort` riêng. Các quy ước được trình bày trong [phần argument resolver của tài liệu Commons](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

Trong chữ ký controller thông thường, không cần gắn `@RequestBody` hoặc `@RequestParam` lên `Pageable`. Đối tượng được resolver chuyên dụng dựng từ request, thay vì được đọc như một object JSON.

### 5.2. Mặc định tại endpoint

Đoạn chữ ký minh họa:

```java
@GetMapping("/products")
public Object list(
        @PageableDefault(size = 20, sort = "id") Pageable pageable) {
    return productQueries.findPage(pageable);
}
```

`productQueries` ở đây là dependency truy vấn đã được inject. Phần 7 trình bày lớp web đầy đủ hơn. `@PageableDefault` thuộc `org.springframework.data.web.PageableDefault`.

Annotation cung cấp mặc định khi request không có thông tin tương ứng, không bắt buộc mọi request phải dùng đúng kích thước đó. Ví dụ, client vẫn có thể gửi `size=5` nếu chính sách khác không ngăn lại.

Hai mặc định dễ nhầm:

- Resolver thông thường không có annotation tại tham số dùng kích thước mặc định `20`.
- Bản thân `@PageableDefault` không khai báo `size` có giá trị `10`.

Do đó, `@PageableDefault(sort = "id")` có thể đồng thời làm kích thước mặc định thành `10`. Viết rõ `size` khi hợp đồng endpoint muốn dùng `20`. Xem [API của PageableDefault](https://docs.spring.io/spring-data/jpa/reference/data-commons/3.5/api/java/org/springframework/data/web/PageableDefault.html).

Khi chỉ cần sắp xếp, có thể nhận `Sort` riêng:

```java
@GetMapping("/product-options")
public Object options(
        @SortDefault(sort = "name", direction = Sort.Direction.ASC)
        Sort sort) {
    return productQueries.findOptions(sort);
}
```

Đây là đoạn minh họa khác; `findOptions` là thao tác của ứng dụng, không phải phương thức Spring Data mặc định. Các import liên quan là `org.springframework.data.domain.Sort` và `org.springframework.data.web.SortDefault`.

`Sort` không chứa page number hoặc page size. `Pageable` đã có `getSort()`, nên thường không cần nhận thêm `Sort` cho cùng danh sách. Resolver đọc thông tin từ request hoặc annotation được mô tả trong [API của SortHandlerMethodArgumentResolver](https://docs.spring.io/spring-data/commons/reference/3.5/api/java/org/springframework/data/web/SortHandlerMethodArgumentResolver.html).

## 6. Tùy biến resolver và giới hạn đầu vào

### 6.1. Customizer khi chủ động dùng annotation

Có thể dùng customizer để điều chỉnh resolver được tích hợp sẵn:

```java
package example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
@EnableSpringDataWebSupport
public class CatalogDataWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setFallbackPageable(PageRequest.of(0, 20));
            resolver.setMaxPageSize(100);
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

Đây là phương án thay cho phần kích hoạt tối thiểu, được tích hợp vào một cấu hình MVC nhất quán. Nếu chọn Boot auto-configuration, bắt đầu từ các property tương ứng và thêm customizer khi có nhu cầu cụ thể.

| Thiết lập | Tác dụng |
| --- | --- |
| `setFallbackPageable(...)` | Chọn phân trang dự phòng khi không có mặc định phù hợp tại tham số |
| `setMaxPageSize(100)` | Giới hạn kích thước trang được resolver chấp nhận |
| `setOneIndexedParameters(false)` | Giữ quy ước request bắt đầu từ trang `0` |

API cũng cho phép đổi tên tham số và delimiter. Xem [PageableHandlerMethodArgumentResolverSupport](https://docs.spring.io/spring-data/commons/docs/3.5.5/api/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.html).

Giới hạn resolver chỉ tác động đến đầu vào đi qua resolver đó. Job hoặc service nội bộ tự tạo `PageRequest.of(0, 10000)` không được giới hạn bởi cấu hình HTTP này.

### 6.2. Quy ước bắt đầu từ 1 chỉ nằm ở đầu vào HTTP

Nếu chọn `setOneIndexedParameters(true)`, request `page=1` biểu thị trang đầu tiên. `Pageable` nội bộ vẫn có chỉ số bắt đầu từ `0`.

Không tự trừ `1` lần nữa trong controller khi resolver đã chuyển đổi. Cũng không giả định metadata response sẽ tự chuyển hết sang quy ước bắt đầu từ `1`; ứng dụng cần thiết kế rõ hợp đồng trả về.

### 6.3. Binding không thay thế validation

Resolver có thể dùng mặc định hoặc chuẩn hóa một số giá trị không phù hợp. Vì vậy không nên công bố rằng mọi giá trị `page` hay `size` sai đều tự động nhận `400 Bad Request`.

Nếu hợp đồng yêu cầu trả `400` cho mọi `size` vượt `100`, cần lớp kiểm tra request rõ ràng. `setMaxPageSize(100)` nhằm khống chế kích thước được resolve; controller có thể chỉ thấy giá trị đã bị giới hạn thay vì giá trị gốc.

Hãy quyết định hành vi với request sai trước, rồi xác minh ở mức HTTP. Không dùng lỗi nội bộ của persistence provider làm hợp đồng công khai.

## 7. Controller với chính sách sort rõ ràng

Ví dụ giả định ứng dụng có bean triển khai `ProductQueries`. Đây là cổng truy vấn của ứng dụng, được service hoặc adapter dữ liệu thực hiện; web support không tự tạo bean đó.

Adapter có thể dùng repository của JPA, MongoDB hoặc module khác, miễn thao tác được chọn hỗ trợ hợp đồng phân trang. Ví dụ sử dụng Java record và `org.springframework.data.web.PagedModel`, loại có từ Commons 3.3. Dự án cũ hơn cần DTO response riêng tương đương.

```java
package example.catalog;

import java.util.Set;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.PagedModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/products")
public class ProductController {

    private static final Set<String> ALLOWED_SORTS =
            Set.of("id", "name", "createdAt");

    private final ProductQueries queries;

    public ProductController(ProductQueries queries) {
        this.queries = queries;
    }

    @GetMapping
    public PagedModel<ProductView> list(
            @PageableDefault(size = 20, sort = "id") Pageable pageable) {

        Sort sort = pageable.getSort();

        for (Sort.Order order : sort) {
            if (!ALLOWED_SORTS.contains(order.getProperty())) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Thuộc tính sort không được hỗ trợ: "
                                + order.getProperty());
            }
        }

        if (sort.getOrderFor("id") == null) {
            sort = sort.and(Sort.by("id"));
        }

        Pageable effectivePageable = PageRequest.of(
                pageable.getPageNumber(),
                pageable.getPageSize(),
                sort);

        Page<ProductView> result = queries.findPage(effectivePageable);
        return new PagedModel<>(result);
    }

    public record ProductView(Long id, String name) {
    }

    public interface ProductQueries {
        Page<ProductView> findPage(Pageable pageable);
    }
}
```

Bốn quyết định của ứng dụng trong ví dụ:

1. Request không chỉ định thông tin phân trang dùng kích thước `20` và sort `id ASC`.
2. API chỉ nhận ba khóa sort đã công bố.
3. Nếu thiếu `id`, controller thêm `id ASC` để phân định các giá trị bằng nhau.
4. Kết quả được bọc trong `PagedModel<ProductView>` để biểu diễn nội dung cùng metadata phân trang.

`id` cần duy nhất trong tập dữ liệu để đóng vai trò phân định thứ tự. Điều này giúp phân trang ổn định hơn khi nhiều bản ghi trùng tên, nhưng không tạo snapshot xuyên suốt nhiều request. Dữ liệu thay đổi giữa hai lần đọc vẫn có thể làm kết quả offset pagination dịch chuyển.

Ví dụ giả định `id`, `name`, `createdAt` cũng là tên thuộc tính mà tầng truy vấn hiểu. Nếu API dùng tên khác, chẳng hạn `created_at`, adapter cần ánh xạ sang thuộc tính được hỗ trợ. Danh sách khóa cho phép và ánh xạ phải được duy trì cùng hợp đồng API.

`Sort` chỉ chứa chỉ dẫn sắp xếp. Nhận được nó không chứng minh thuộc tính có tồn tại, được phép truy cập hoặc được kho dữ liệu hỗ trợ hiệu quả. Kiểm tra sớm tránh đưa yêu cầu không được hỗ trợ xuống tầng truy vấn.

Nếu gọi phương thức controller trực tiếp thay vì qua HTTP, cần tự bảo đảm các tiền điều kiện về phân trang. Giới hạn page size ở phần trước nằm tại web resolver.

## 8. Nối Pageable xuống repository

Commons cung cấp hợp đồng chung; cách thực thi nằm ở module lưu trữ. Với repository đồng bộ hỗ trợ cả CRUD và phân trang, hình dạng interface có thể là:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {
}
```

`Product` đại diện cho domain model đã được ánh xạ theo kho dữ liệu. Khai báo interface chưa đủ để cấu hình persistence. Trong các dòng Spring Data hiện đại, nên khai báo rõ các hợp đồng cần dùng, thay vì suy rằng mọi interface phân trang đồng thời cung cấp toàn bộ CRUD.

Adapter triển khai `ProductQueries` có thể gọi `repository.findAll(pageable)`, rồi dùng `Page.map(...)` để chuyển domain object sang `ProductView`. Nếu dùng derived query có điều kiện, adapter phải chọn phương thức nhận `Pageable` và áp dụng điều kiện cùng phân trang.

Request có thêm `status=ACTIVE` không tự trở thành điều kiện repository chỉ vì controller có `Pageable`. Ứng dụng vẫn cần đọc bộ lọc, xác thực giá trị và chuyển xuống truy vấn thích hợp. Tương tự, web support không tự dựng Query by Example, chọn projection hay điền trường auditing.

Cần đánh giá riêng:

- Truy vấn có áp dụng phân trang và sort tại tầng dữ liệu không?
- Trả `Page<T>` có cần truy vấn đếm, và chi phí có phù hợp không?
- Nếu chỉ cần biết còn dữ liệu hay không, hợp đồng `Slice<T>` có phù hợp hơn không?
- Kho dữ liệu có hỗ trợ trường sort và cách xử lý chữ hoa/chữ thường mà API công bố không?

Binding thành công chỉ xác nhận phần đọc tham số. Tính đúng của kết quả còn phụ thuộc truy vấn, mapping và chính sách nghiệp vụ.

## 9. DomainClassConverter: từ ID đến domain object

Web support cũng có thể hỗ trợ chữ ký dạng:

```java
@GetMapping("/products/{id}")
public ProductView detail(@PathVariable("id") Product product) {
    return new ProductView(product.getId(), product.getName());
}
```

Đây là đoạn minh họa khác, giả định domain `Product`, DTO và repository phù hợp đã được khai báo. `@PathVariable` thuộc `org.springframework.web.bind.annotation.PathVariable`.

Với request `/products/42`, quá trình chuyển đổi về cơ bản cần chuyển chuỗi `"42"` sang kiểu ID, tìm repository cho `Product`, thực hiện tra cứu theo ID rồi cung cấp kết quả cho tham số MVC.

Tài liệu hiện nêu repository phải triển khai `CrudRepository` để đủ điều kiện được converter phát hiện. Xem [phần DomainClassConverter trong tài liệu Commons](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

Cách viết này giảm mã tra cứu trong tình huống phù hợp. Tuy nhiên, ứng dụng vẫn phải định nghĩa hành vi khi ID sai kiểu, đối tượng không tồn tại hoặc người dùng không có quyền đọc.

Converter không bảo đảm tenant, quyền sở hữu tài nguyên hay quy tắc nghiệp vụ. Truy vấn chuyển đổi có thể xảy ra trước khi thân phương thức controller chạy. Khi cần truy vấn theo cả ID và tenant hoặc kiểm soát rõ `404` và `403`, thường nên nhận ID tường minh:

```java
@GetMapping("/products/{id}")
public ProductView detail(@PathVariable("id") Long id) {
    return productService.findVisibleProduct(id);
}
```

`productService` là service của ứng dụng, nơi tra cứu đúng phạm vi và chuyển sang DTO. Cách này giúp luồng nghiệp vụ hiện rõ trong mã.

## 10. Nhiều Pageable và cách biểu diễn response

### 10.1. Phân biệt nhiều bộ tham số

Một màn hình có hai danh sách có thể dùng `@Qualifier` thuộc `org.springframework.beans.factory.annotation.Qualifier`:

```java
@GetMapping("/dashboard")
public Object dashboard(
        @Qualifier("products") Pageable productPage,
        @Qualifier("orders") Pageable orderPage) {
    return dashboardService.load(productPage, orderPage);
}
```

`dashboardService` đại diện cho dependency ứng dụng. Request theo delimiter mặc định:

```http
GET /dashboard?products_page=0&products_size=5&products_sort=name,asc&orders_page=2&orders_size=10&orders_sort=id,desc
```

Không thêm hai `Pageable` không được phân biệt rồi kỳ vọng resolver tự đoán chúng thuộc hai bảng. Quy tắc prefix theo qualifier được mô tả trong [tài liệu web support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

### 10.2. Tách đọc tham số khỏi ghi JSON

Argument resolver quyết định request được chuyển thành `Pageable` hoặc `Sort` như thế nào. Serialization quyết định dữ liệu và metadata được gửi lại ra sao. Hai chiều này có cấu hình riêng.

Từ Commons 3.3, có thể bọc `Page<T>` bằng `org.springframework.data.web.PagedModel<T>`, như controller phần 7. Đây là DTO phân trang đơn giản, được mô tả trong [API của PagedModel](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/web/PagedModel.html).

Response minh họa với tổng cộng `37` bản ghi, page size `15`, đang đọc trang thứ hai:

```json
{
  "content": [
    { "id": 21, "name": "Bàn phím" },
    { "id": 35, "name": "Chuột" }
  ],
  "page": {
    "size": 15,
    "number": 1,
    "totalElements": 37,
    "totalPages": 3
  }
}
```

`content` chỉ liệt kê hai phần tử tiêu biểu để rút gọn ví dụ. Metadata phải được tạo từ kết quả truy vấn thực, không suy ra từ query parameter đơn thuần.

Với cấu hình annotation tường minh, có thể tự động chuyển biểu diễn `PageImpl`:

```java
import static org.springframework.data.web.config.EnableSpringDataWebSupport
        .PageSerializationMode.VIA_DTO;

@Configuration
@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)
class CatalogWebConfiguration {
}
```

Đoạn này dùng lại import `Configuration` và `EnableSpringDataWebSupport` ở phần cấu hình trước; đây là phương án thay thế, không phải một class cấu hình thứ hai cần khai báo cùng tên.

`pageSerializationMode` có từ Commons 3.3. API mô tả mặc định tương thích ngược là `DIRECT` và khuyến nghị biểu diễn DTO hoặc chuyển đổi tường minh. Xem [API của annotation](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/web/config/EnableSpringDataWebSupport.html).

Bọc tường minh bằng `PagedModel` giúp kiểu response hiện rõ tại endpoint và không yêu cầu thay cách kích hoạt chỉ vì một endpoint cần biểu diễn khác.

Không nhầm `org.springframework.data.web.PagedModel` với `org.springframework.hateoas.PagedModel`. Loại của Commons phục vụ biểu diễn đơn giản; loại của HATEOAS phục vụ mô hình hypermedia. Có HATEOAS trong dependency chưa đủ để mọi response tự có liên kết; cần model hoặc assembler thích hợp.

## 11. Thực hành quan sát hành vi HTTP

Với controller phần 7, bean `ProductQueries` hoạt động và giới hạn page size `100`, lần lượt gửi các request:

| Request | Điều cần quan sát |
| --- | --- |
| `GET /products` | Trang `0`, kích thước `20`, sort `id ASC` |
| `GET /products?page=1&size=5` | Trang thứ hai, tối đa `5` phần tử |
| `GET /products?sort=name,desc` | Chính sách ứng dụng bổ sung `id ASC` |
| `GET /products?sort=name,asc&sort=id,desc` | Giữ `name ASC`, rồi `id DESC` |
| `GET /products?sort=internalCost,desc` | Controller ví dụ trả `400` trước khi gọi cổng truy vấn |
| `GET /products?size=10000` | Quan sát giới hạn resolver; không mặc định kỳ vọng `400` |

Trong môi trường học, đặt breakpoint ở đầu controller để xem `getPageNumber()`, `getPageSize()` và `getSort()`. Sau đó xem `effectivePageable` để thấy chính sách sort mà ứng dụng bổ sung.

Để kiểm tra riêng phần kích hoạt, có thể dùng bean truy vấn giả trong cấu hình thực hành, trả một `Page` dựng từ dữ liệu cố định. Khi chuyển sang repository thực, cần kiểm tra thêm rằng phân trang và sort đến được tầng truy vấn.

Quan sát binding giúp khoanh vùng lỗi MVC; nó không thay thế việc kiểm tra khả năng kho dữ liệu.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| MVC không resolve được `Pageable` | Cấu hình chưa được nạp hoặc resolver chưa đăng ký | Kiểm tra context phục vụ `DispatcherServlet` |
| Có annotation nhưng endpoint vẫn lỗi | Controller, service hoặc repository chưa được đăng ký | Kiểm tra riêng các bean và cấu hình persistence |
| Property Boot không có tác dụng như mong đợi | Resolver thủ công hoặc auto-configuration đã nhường quyền | Xác định resolver thực tế và nguồn tùy biến |
| Trang đầu lệch một đơn vị | Trộn quy ước bắt đầu từ `0` và `1` | Thống nhất hợp đồng; không chuyển đổi hai lần |
| Kích thước mặc định thành `10` | `@PageableDefault` không khai báo `size` | Viết rõ giá trị tại endpoint |
| Bind sort thành công nhưng truy vấn lỗi | Khóa sort không thuộc mô hình hoặc không được hỗ trợ | Kiểm tra khóa và ánh xạ trước truy vấn |
| Chuyển ID sang domain thất bại | Thiếu repository đủ điều kiện hoặc không chuyển được kiểu ID | Kiểm tra mapping; cân nhắc nhận ID tường minh |
| JSON phân trang thay đổi sau nâng cấp | Phụ thuộc cấu trúc implementation | Dùng `PagedModel` phù hợp hoặc DTO có hợp đồng rõ |

Khi triển khai endpoint mới, hãy tự trả lời: ai kích hoạt resolver, tham số nào được chấp nhận, mặc định đến từ đâu, giới hạn nào được thực thi, sort được kiểm tra ở đâu, và repository nào thực sự nhận `Pageable`? Những câu hỏi này nối cấu hình `@EnableSpringDataWebSupport` với hành vi API mà người dùng quan sát được.
