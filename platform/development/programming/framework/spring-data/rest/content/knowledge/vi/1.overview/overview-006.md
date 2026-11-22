# So sánh API từ Spring Data REST repository với API tự viết Controller–Service–DTO

> Phạm vi: bài tổng quan trong module Spring Data REST. Mục tiêu là hiểu hai cách đưa dữ liệu từ Spring Data ra HTTP, cách chúng khác nhau về hợp đồng API và khi nào nên chọn từng cách.

## 1. Ý tưởng cốt lõi

Spring Data REST và API tự viết đều có thể dùng chung Spring Data repository ở tầng truy cập dữ liệu. Điểm khác nhau nằm ở cách tạo HTTP API và nơi nhóm kiểm soát hợp đồng với client.

- **Spring Data REST** đọc các repository interface và tự xuất chúng thành REST resources. Repository, domain type và cấu hình quyết định phần lớn đường dẫn, thao tác HTTP và cách biểu diễn dữ liệu.
- **Controller–Service–DTO** để nhóm tự định nghĩa endpoint bằng Spring MVC, kiểm tra request, gọi service thực hiện use case, rồi chuyển kết quả thành DTO dành cho client.

Luồng khái quát:

~~~text
Spring Data REST:
Client -> Spring Data REST exporter -> Repository -> Database

Controller–Service–DTO:
Client -> Controller -> Request DTO validation -> Service -> Repository -> Database
                                                     |
                                                     v
                                             Response DTO -> Client
~~~

Spring Data REST giảm đáng kể mã CRUD lặp lại. API tự viết cần nhiều lớp hơn nhưng cho phép kiểm soát rõ ràng dữ liệu đầu vào, đầu ra, nghiệp vụ và cách API tiến hóa.

## 2. Cùng một domain, hai cách xuất API

Dùng ví dụ một sản phẩm có mã định danh, tên và giá. Các đoạn mã dưới đây là những mảnh ghép Java 17+ để minh họa kiến trúc; chúng cần nằm trong một ứng dụng Spring Boot có cấu hình persistence, database và các dependency Spring tương ứng, nên không phải một chương trình độc lập có thể chạy bằng riêng lệnh java.

### 2.1. Entity và repository dùng chung

~~~java
// Product.java
package com.example.catalog.product;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    // Public setters cho phép JSON data binding khi ghi qua Spring Data REST.
    public void setName(String name) {
        this.name = name;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
~~~

Với Spring Data JPA, repository có thể được khai báo như sau:

~~~java
// ProductRepository.java
package com.example.catalog.product;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    Page<Product> findByNameContainingIgnoreCase(
        @Param("q") String q,
        Pageable pageable
    );
}
~~~

Khi repository được Spring Data REST xuất bản, client có thể truy cập các resource mặc định và resource tìm kiếm tương ứng với query method. Việc xuất bản còn phụ thuộc repository có được phát hiện hay không, method có tồn tại và có bị đánh dấu `exported = false` hay không.

### 2.2. Cách A — để Spring Data REST xuất repository

Thêm dependency Spring Data REST phù hợp với phiên bản Spring Boot đang dùng, cùng starter của store (ví dụ Spring Data JPA) và driver database. Spring Boot dependency management nên được dùng để chọn các phiên bản tương thích.

Với repository ở trên, các URL điển hình là:

| Request | Ý nghĩa |
|---|---|
| `GET /products` | Lấy collection sản phẩm |
| `GET /products/{id}` | Lấy một sản phẩm |
| `POST /products` | Tạo sản phẩm |
| `PUT /products/{id}` | Thay thế trạng thái resource nếu method được xuất |
| `PATCH /products/{id}` | Cập nhật một phần nếu method được xuất |
| `DELETE /products/{id}` | Xóa resource nếu method được xuất |
| `GET /products/search/by-name?q=keyboard&page=0&size=10` | Chạy query method tìm theo tên |

Các method HTTP khả dụng phụ thuộc method của repository và cấu hình export. Ví dụ, nếu repository không cung cấp hoặc không xuất bản thao tác lưu, endpoint ghi tương ứng sẽ không được cung cấp.

Một request tạo sản phẩm có thể gửi JSON tương ứng với các thuộc tính được expose:

~~~http
POST /products
Content-Type: application/json

{
  "name": "Keyboard",
  "price": 1290000
}
~~~

Spring Data REST thường trả representation theo HAL. Client có thể nhận được các phần như:

~~~json
{
  "_embedded": {
    "products": [
      {
        "name": "Keyboard",
        "price": 1290000,
        "_links": {
          "self": {
            "href": "http://localhost:8080/products/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/products"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

JSON trên chỉ minh họa cấu trúc; URL đầy đủ, các link và metadata thực tế phụ thuộc cấu hình, dữ liệu và request. HAL đặt liên kết trong `_links`, collection thường nằm trong `_embedded`, còn response phân trang có metadata `page`. Client có thể khám phá resource từ URL gốc của ứng dụng thay vì phải hard-code mọi đường dẫn.

**Phân trang và sắp xếp:** với repository hỗ trợ `Pageable` hoặc `Sort`, Spring Data REST hiểu các tham số `page`, `size` và `sort`. Số trang bắt đầu từ 0; kích thước mặc định thường là 20 và có thể cấu hình. Ví dụ:

~~~http
GET /products?page=0&size=10&sort=name,asc
~~~

Kết quả phân trang có metadata và các link như `next` hoặc `prev` khi có trang tương ứng. Query method muốn phân trang cần nhận `Pageable` và trả `Page` hoặc `Slice`.

**Tùy biến:** có thể đổi collection path hoặc relation bằng `@RepositoryRestResource`, đổi path của query method bằng `@RestResource`, ẩn một repository bằng `@RepositoryRestResource(exported = false)`, hoặc ẩn riêng method bằng `@RestResource(exported = false)`. `RepositoryRestConfigurer` cho phép cấu hình base path, kích thước trang mặc định/tối đa và các tùy chọn khác.

**Representation:** projection của Spring Data có thể chọn một tập thuộc tính để trả về; Spring Data REST cũng có thể cấu hình projection mặc định cho collection. Projection giúp kiểm soát góc nhìn dữ liệu, nhưng không tự tạo ra một ranh giới DTO độc lập hoàn toàn với domain model.

### 2.3. Cách B — tự viết Controller–Service–DTO

Ở cách này, repository vẫn làm việc với entity, nhưng controller nhận và trả các kiểu dữ liệu được thiết kế riêng cho API. Nhờ vậy, client không cần gửi hoặc nhận trực tiếp toàn bộ cấu trúc persistence.

Request DTO và response DTO được đặt ở các tệp riêng:

~~~java
// CreateProductRequest.java
package com.example.catalog.product.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank @Size(max = 120) String name,
    @NotNull @Positive BigDecimal price
) {}
~~~

~~~java
// ProductResponse.java
package com.example.catalog.product.api;

import java.math.BigDecimal;

public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

~~~java
// ProductPageResponse.java
package com.example.catalog.product.api;

import java.util.List;

public record ProductPageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages
) {}
~~~

Service chứa use case và điều phối repository:

~~~java
// ProductService.java
package com.example.catalog.product;

import com.example.catalog.product.api.CreateProductRequest;
import com.example.catalog.product.api.ProductResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<ProductResponse> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(this::toResponse);
    }

    @Transactional
    public ProductResponse create(CreateProductRequest request) {
        Product product = new Product(request.name(), request.price());
        Product saved = repository.save(product);
        return toResponse(saved);
    }

    private ProductResponse toResponse(Product product) {
        return new ProductResponse(
            product.getId(),
            product.getName(),
            product.getPrice()
        );
    }
}
~~~

Controller định nghĩa hợp đồng HTTP:

~~~java
// ProductController.java
package com.example.catalog.product.api;

import com.example.catalog.product.ProductService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping
    public ProductPageResponse<ProductResponse> findAll(
        @PageableDefault(size = 20, sort = "name") Pageable pageable
    ) {
        Page<ProductResponse> result = service.findAll(pageable);

        return new ProductPageResponse<>(
            result.getContent(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages()
        );
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        return service.create(request);
    }
}
~~~

Để các annotation Bean Validation hoạt động, ứng dụng cần dependency validation tương ứng, chẳng hạn Spring Boot validation starter. Khi request không thỏa `@NotBlank`, `@Size`, `@NotNull` hoặc `@Positive`, validation từ chối request trước khi controller gọi service. Các quy tắc nghiệp vụ phụ thuộc nhiều dữ liệu hoặc trạng thái nên được kiểm tra trong service/domain, vì không phải mọi quy tắc đều diễn đạt được bằng annotation trên DTO.

Ở ví dụ trên, response phân trang là `ProductPageResponse` do ứng dụng tự định nghĩa. Đây là chủ ý: nếu API công khai cần hợp đồng ổn định, không nên mặc định coi cách Jackson serialize trực tiếp kiểu `Page` nội bộ là định dạng lâu dài. Hãy chọn rõ các trường mà client cần và kiểm thử JSON thực tế.

Các endpoint khác như đọc theo ID, cập nhật và xóa cũng được nhóm định nghĩa rõ trong controller/service. Ví dụ, service có thể ném lỗi khi không tìm thấy sản phẩm; `@RestControllerAdvice` chuyển lỗi đó thành response lỗi thống nhất, có status và mã lỗi theo hợp đồng của ứng dụng.

## 3. So sánh trực tiếp

| Tiêu chí | Spring Data REST repository | Controller–Service–DTO |
|---|---|---|
| Lượng mã ban đầu | Ít; repository có thể tạo sẵn CRUD resource | Nhiều hơn; phải viết controller, DTO, service và mapping |
| Nơi định nghĩa API | Suy ra từ repository, domain type và annotation export | Định nghĩa tường minh trong controller và DTO |
| Hợp đồng request/response | Gắn khá chặt với entity/repository; có thể tùy biến bằng projection và cấu hình | Nhóm chủ động thiết kế DTO, field, envelope và lỗi |
| CRUD | Có sẵn khi repository method tương ứng được export | Chỉ có thao tác được nhóm viết |
| Tìm kiếm | Query method có thể tự xuất thành resource dưới `/search` | Nhóm tự định nghĩa route, tham số và logic truy vấn |
| Phân trang/sắp xếp | Có hỗ trợ tích hợp `Pageable`, `Sort`, metadata và link HAL | Có thể dùng `Pageable`, nhưng nhóm quyết định format và chính sách công khai |
| Nghiệp vụ nhiều bước | Cần tùy biến; request export repository không tự đi qua service tùy chỉnh | Service là nơi tự nhiên để điều phối nhiều repository và quy tắc nghiệp vụ |
| DTO và chuyển đổi dữ liệu | Projection hỗ trợ một số góc nhìn dữ liệu | DTO và mapper được kiểm soát đầy đủ |
| Validation | Có thể đăng ký Validator theo repository event | Có thể dùng Bean Validation cho request DTO và kiểm tra nghiệp vụ trong service |
| Status, header, lỗi | Theo hành vi framework và cấu hình; có điểm tùy biến | Kiểm soát trực tiếp bằng Spring MVC và exception handler |
| Hypermedia | HAL và link khám phá resource được tích hợp sẵn | Không tự có; có thể tự thiết kế hoặc dùng Spring HATEOAS |
| Bảo trì hợp đồng | Thay đổi entity/repository có thể ảnh hưởng API đã xuất | Có thể giữ DTO ổn định khi entity và database thay đổi |
| Kiểm soát bề mặt truy cập | Phải rà soát repository/method được export và bảo vệ bằng Spring Security | Route và thao tác được khai báo rõ, vẫn cần Spring Security |
| Phù hợp nhất | CRUD hướng dữ liệu, API nội bộ hoặc trường hợp domain model phù hợp với representation công khai | API nghiệp vụ, API public/mobile/partner và hợp đồng cần ổn định |

### 3.1. Khác biệt quan trọng về luồng nghiệp vụ

Giả sử `ProductService.create()` kiểm tra hạn mức tồn kho, ghi audit log và phát sự kiện nghiệp vụ trước khi lưu. Request đi qua `POST /api/products` sẽ gọi service đó vì controller chủ động ủy quyền cho service.

Nếu cùng lúc repository được Spring Data REST xuất bản tại `POST /products`, request vào đường dẫn này được exporter xử lý trực tiếp qua repository. Nó **không tự gọi `ProductService.create()`**. Vì vậy, hai endpoint có thể tạo sản phẩm theo hai luồng khác nhau dù cùng ghi vào một bảng.

Đây là rủi ro thiết kế cần xử lý sớm. Nếu quy tắc nghiệp vụ bắt buộc phải chạy cho mọi đường ghi, hãy đặt quy tắc ở tầng domain/service dùng chung và chọn cách expose bảo đảm mọi request đi qua luồng đó. Nếu muốn chỉ dùng API tự viết, có thể tắt export repository bằng `@RepositoryRestResource(exported = false)`. Nếu dùng Spring Data REST, có thể bổ sung repository event handler và validator cho các hook phù hợp, nhưng cần cân nhắc rõ phạm vi của chúng và không coi chúng là thay thế tự động cho một use case service hoàn chỉnh.

## 4. DTO, projection và entity không phải là một khái niệm

Ba kiểu này giải quyết các vấn đề khác nhau:

- **Entity** mô hình hóa dữ liệu và quan hệ trong persistence/domain. Nó có thể chứa thuộc tính nội bộ, quan hệ lazy, hoặc cấu trúc không phù hợp để công khai.
- **Projection** tạo một góc nhìn chọn lọc trên đối tượng mà repository trả về. Nó hữu ích khi muốn ẩn bớt thuộc tính hoặc trình bày một cấu trúc đọc đơn giản hơn trong Spring Data.
- **DTO** là kiểu dữ liệu thuộc hợp đồng của ứng dụng/API. Nó có thể đổi tên field, gộp dữ liệu từ nhiều aggregate, biểu diễn request khác với entity, hoặc giữ nguyên khi cấu trúc database thay đổi.

Ví dụ, entity có `internalCost`, `supplierId` và quan hệ `auditEntries`; API sản phẩm công khai chỉ nên trả `id`, `name` và `price`. DTO làm ranh giới này rõ ràng. Projection cũng có thể chọn một phần field, nhưng khi API có quy tắc biến đổi, tổng hợp hoặc versioning riêng, DTO thường dễ quản lý hơn.

Không nên expose entity chỉ vì Spring Data REST có thể serialize entity. Trước khi công khai, cần rà soát field nhạy cảm, association, serialization vòng lặp, lazy loading và số lượng query phát sinh.

## 5. Chọn cách nào trong tình huống thực tế?

### Chọn Spring Data REST khi

- Nhu cầu chính là CRUD trên một aggregate/repository và thao tác HTTP tương ứng với thao tác dữ liệu.
- API phục vụ công cụ nội bộ, admin hoặc client có thể làm việc với HAL và link khám phá resource.
- Domain representation đủ phù hợp để expose; không cần biến đổi request/response phức tạp.
- Muốn tạo API nhanh và chấp nhận quy ước endpoint do Spring Data REST cung cấp.
- Nhóm có thể kiểm soát chặt repository nào, method nào và thuộc tính nào được export.

### Chọn Controller–Service–DTO khi

- API phục vụ mobile app, đối tác hoặc client bên ngoài và cần hợp đồng ổn định qua nhiều phiên bản.
- Một request phải phối hợp nhiều repository, gọi dịch vụ ngoài, áp dụng workflow hoặc thực hiện nhiều bước.
- Request/response khác đáng kể với entity; cần tổng hợp, đổi tên field, che dữ liệu hoặc hỗ trợ nhiều loại client.
- Cần kiểm soát chính xác status code, header, định dạng lỗi, idempotency hoặc quy tắc cập nhật.
- Quyền truy cập phụ thuộc use case, người dùng, tenant hoặc trạng thái nghiệp vụ.
- Không muốn thay đổi entity/repository vô tình làm thay đổi API công khai.

### Dùng kết hợp khi có ranh giới rõ

Một ứng dụng có thể dùng Spring Data REST cho các resource CRUD nội bộ và controller riêng cho các use case nghiệp vụ. Ví dụ, `/products` có thể phục vụ màn hình quản trị đơn giản, trong khi `/api/orders/{id}/checkout` là một use case riêng do service điều phối.

Nếu dùng kết hợp, cần xác định rõ endpoint nào được phép ghi và mọi quy tắc bắt buộc được thực thi ở đâu. Tránh để một endpoint đi qua service còn endpoint khác ghi thẳng repository rồi tạo ra kết quả nghiệp vụ không nhất quán. Nếu hai route đại diện cho cùng một hợp đồng, hãy cân nhắc chỉ giữ một đường ghi.

## 6. Những điểm cần kiểm tra trước khi đưa API vào production

1. **Danh sách repository được export:** kiểm tra repository detection strategy và mọi annotation `exported`. Không giả định chỉ repository mà controller đang dùng mới được expose.
2. **Quyền đọc và ghi:** áp dụng Spring Security cho URL và/hoặc method repository. Phân biệt quyền đọc collection, đọc item, tạo, sửa, xóa và thao tác association. Không xem việc ẩn link hoặc đổi URL là cơ chế bảo mật.
3. **Dữ liệu trả về:** rà soát entity field, association, projection, lazy loading, vòng lặp serialization và dữ liệu nội bộ.
4. **Phân trang:** đặt giới hạn kích thước trang tối đa, tránh trả toàn bộ collection lớn; chỉ cho phép sort theo các thuộc tính phù hợp.
5. **Validation:** kiểm tra dữ liệu đầu vào và invariant nghiệp vụ. Validator gắn với event của Spring Data REST chỉ chạy trong luồng event tương ứng; đừng giả định nó bao phủ mọi đường ghi trong ứng dụng.
6. **Lỗi và status:** kiểm thử trường hợp không tìm thấy, dữ liệu sai, xung đột, không đủ quyền và lỗi phụ thuộc ngoài. Với API tự viết, chuẩn hóa response lỗi qua `@RestControllerAdvice`.
7. **Tương thích client:** thay đổi tên entity, repository method, field hoặc association có thể ảnh hưởng resource Spring Data REST. Với API public, quản lý version và thay đổi DTO có chủ đích.
8. **Kiểm thử tích hợp:** kiểm tra endpoint thực tế, media type, JSON/HAL, link, phân trang, method được phép, validation và security. Test repository đơn lẻ không chứng minh hợp đồng HTTP đang đúng.

## 7. Kết luận lựa chọn

Spring Data REST phù hợp khi repository chính là trung tâm của API và nhóm muốn xuất các thao tác dữ liệu chuẩn hóa với ít mã. Controller–Service–DTO phù hợp khi API là một hợp đồng sản phẩm cần được thiết kế và duy trì độc lập với persistence.

Có thể dùng tiêu chí ngắn sau để quyết định:

- Nếu câu hỏi chính là **“client cần CRUD những resource nào của repository?”**, bắt đầu bằng Spring Data REST.
- Nếu câu hỏi chính là **“client cần thực hiện use case nào và phải nhận/gửi hợp đồng dữ liệu nào?”**, bắt đầu bằng Controller–Service–DTO.
- Nếu cần cả hai, xác định ranh giới đọc/ghi và bảo đảm mọi quy tắc nghiệp vụ bắt buộc đều chạy trên tất cả đường truy cập.

## 8. Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): resource collection, item, query method và HTTP methods.
- [Spring Data REST Reference — Getting started and configuration](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): repository detection, base path và cấu hình.
- [Spring Data REST Reference — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): tham số page, size, sort và navigation links.
- [Spring Data REST Reference — Projections](https://docs.spring.io/spring-data/rest/reference/data-commons/repositories/projections.html): projection của Spring Data.
- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): đăng ký Validator theo repository event.
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html): repository event handlers.
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html): tích hợp Spring Security và method-level security.
