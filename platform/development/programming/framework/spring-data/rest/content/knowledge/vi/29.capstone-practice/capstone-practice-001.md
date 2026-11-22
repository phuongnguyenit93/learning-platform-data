# Xây dựng API quản lý danh mục với entity, repository và HAL

## Mục tiêu

Bài thực hành xây dựng một API quản lý danh mục sản phẩm bằng Spring Data REST. Ứng dụng khai báo domain entities và Spring Data repositories; Spring Data REST tự export repository thành REST resources, tạo các HTTP endpoints cho CRUD, search, association và trả representation HAL JSON.

Mô hình ví dụ có hai entity:

- `Category`: danh mục sản phẩm, gồm mã, tên, mô tả và trạng thái.
- `Product`: sản phẩm, có quan hệ nhiều-một tới `Category`.

API cho phép client khám phá resource từ root URL, đọc danh sách và chi tiết danh mục, tạo/cập nhật/xóa danh mục, tìm theo tên, đọc sản phẩm và liên kết sản phẩm với danh mục bằng URI. Các tên package, database và field có thể điều chỉnh theo dự án thực tế.

## 1. Spring Data REST hoạt động như thế nào?

Spring Data REST export Spring Data repositories thành REST resources thông qua Spring MVC. Repository là điểm khai báo chính: domain type và các method repository quyết định tài nguyên nào được export và HTTP method nào được hỗ trợ.

Ví dụ:

```java
public interface CategoryRepository
        extends CrudRepository<Category, Long> {
}
```

Nếu không tùy chỉnh, Spring Data REST tạo collection resource theo tên domain class ở dạng chữ thường và số nhiều, ví dụ `/categories`, cùng item resources theo mẫu `/categories/{id}`. Có thể thay đổi path và relation bằng `@RepositoryRestResource`.

Spring Data REST dùng HAL làm representation hypermedia mặc định. HAL JSON có các phần thường gặp:

- `_links`: các liên kết đến resource, profile hoặc thao tác liên quan.
- `_embedded`: các resource được nhúng trong collection representation.
- `page`: metadata phân trang khi response có paging.

Client nên khám phá và đi theo các link này để tìm resource tiếp theo thay vì tự ghép URL từ quy ước tên.

## 2. Tạo project và dependencies

Với Spring Boot, thêm starter Spring Data REST và starter của persistence store. Ví dụ dùng Spring Data JPA và H2 cho môi trường thực hành:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Khi dùng Spring Boot dependency management, không cần tự khai báo version cho các starter. Với Gradle, các dependency tương ứng là `implementation("org.springframework.boot:spring-boot-starter-data-rest")`, `implementation("org.springframework.boot:spring-boot-starter-data-jpa")` và `runtimeOnly("com.h2database:h2")`.

Trong production, thay H2 bằng database driver phù hợp và dùng migration tool như Flyway hoặc Liquibase để quản lý schema. Spring Data REST không tự tạo ra persistence store; nó export các repository mà ứng dụng đã cấu hình.

Cấu hình tối thiểu cho môi trường local:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalogdb
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: update
  data:
    rest:
      base-path: /api
```

Với cấu hình trên, root của Spring Data REST là `/api`. Không dùng `ddl-auto: update` như chiến lược quản lý schema production nếu cần migration có kiểm soát.

## 3. Thiết kế entity

Đặt các entity trong package được Spring Boot component/entity scan tìm thấy, ví dụ `com.example.catalog.domain`.

### 3.1. Category

```java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 40)
    @Column(nullable = false, unique = true, length = 40)
    private String code;

    @NotBlank
    @Size(max = 120)
    @Column(nullable = false, length = 120)
    private String name;

    @Size(max = 500)
    @Column(length = 500)
    private String description;

    @Column(nullable = false)
    private boolean active = true;

    protected Category() {
        // Required by JPA.
    }

    public Category(String code, String name, String description) {
        this.code = code;
        this.name = name;
        this.description = description;
        this.active = true;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Các điểm cần chú ý:

- `@Entity` đánh dấu persistence entity.
- `@Id` và `@GeneratedValue` xác định khóa chính.
- `@Column(nullable = false, unique = true)` tạo ràng buộc ở tầng database cho mã danh mục.
- `@NotBlank` và `@Size` mô tả ràng buộc dữ liệu. Cần có Bean Validation provider và cấu hình validator phù hợp để các constraint được áp dụng ở luồng REST.
- Constructor không tham số có visibility `protected` để JPA khởi tạo entity. Không cần cho client gửi `id` vì database sinh khóa.

### 3.2. Product và quan hệ tới Category

```java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String sku;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
    }

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public Category getCategory() {
        return category;
    }

    public void setCategory(Category category) {
        this.category = category;
    }
}
```

Quan hệ `@ManyToOne` cho phép nhiều sản phẩm thuộc cùng một danh mục. Khi cả `Product` và `Category` đều có repository được export, Spring Data REST có thể biểu diễn quan hệ dưới dạng association link. Client đọc link này để xem hoặc thay đổi association.

Ví dụ này không thêm collection `products` vào `Category` để tránh một object graph hai chiều không cần thiết trong bài nhập môn. Với domain model hai chiều, cần cân nhắc lazy loading, JSON recursion, projection và cách hiển thị association.

## 4. Khai báo repository và đường dẫn REST

Tạo package `com.example.catalog.repository`.

### 4.1. CategoryRepository

```java
package com.example.catalog.repository;

import com.example.catalog.domain.Category;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.jpa.repository.JpaRepository;

@RepositoryRestResource(
    path = "categories",
    collectionResourceRel = "categories"
)
public interface CategoryRepository
        extends JpaRepository<Category, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    Page<Category> findByNameContainingIgnoreCase(
            @Param("name") String name,
            Pageable pageable
    );
}
```

Giải thích:

- `JpaRepository<Category, Long>` cung cấp CRUD, paging và sorting cho entity `Category`.
- `path = "categories"` xác định collection path.
- `collectionResourceRel = "categories"` xác định relation name trong HAL collection.
- `@RestResource(path = "by-name", rel = "by-name")` đặt tên dễ đọc cho query resource.
- `@Param("name")` xác định query parameter được client gửi.
- `Page<Category>` cùng `Pageable` cho phép endpoint tìm kiếm trả kết quả có phân trang.

Spring Data REST tạo search resource nếu repository export query methods. Query method trên có thể được gọi tại `/categories/search/by-name?name=book`.

### 4.2. ProductRepository

```java
package com.example.catalog.repository;

import com.example.catalog.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Khi ứng dụng khởi động, Spring Data REST tìm repository interfaces trong phạm vi scan và export các repository phù hợp với repository detection strategy. Với cấu hình mặc định, các public repositories thường được export trừ khi bị đánh dấu không export.

Nếu không muốn export một repository, có thể khai báo `@RepositoryRestResource(exported = false)`. Nếu muốn giữ một repository method dùng nội bộ nhưng không tạo HTTP endpoint, dùng `@RestResource(exported = false)` trên method phù hợp. Kiểm tra kỹ các method CRUD được kế thừa trước khi đưa API ra môi trường thật.

## 5. Các resource được tạo

Với `spring.data.rest.base-path=/api`, API ví dụ có các URL:

| Resource | URL | Mục đích |
|---|---|---|
| API root | `GET /api` | Khám phá resource links |
| Category collection | `GET /api/categories` | Danh sách danh mục |
| Category item | `GET /api/categories/{id}` | Chi tiết một danh mục |
| Create category | `POST /api/categories` | Tạo danh mục |
| Update category | `PUT /api/categories/{id}` | Thay thế dữ liệu danh mục |
| Partial update | `PATCH /api/categories/{id}` | Cập nhật một phần |
| Delete category | `DELETE /api/categories/{id}` | Xóa danh mục |
| Search by name | `GET /api/categories/search/by-name?name=...` | Tìm theo tên |
| Product collection | `GET /api/products` | Danh sách sản phẩm |
| Product item | `GET /api/products/{id}` | Chi tiết sản phẩm |
| Product category association | `GET/PUT /api/products/{id}/category` | Đọc hoặc gán danh mục cho sản phẩm |

Path thực tế còn phụ thuộc servlet context path, custom base path, repository annotations và cấu hình export.

## 6. Khám phá API bằng HAL

Gọi API root với media type HAL:

```bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api
```

Root response có thể tương tự:

```json
{
  "_links": {
    "categories": {
      "href": "http://localhost:8080/api/categories"
    },
    "products": {
      "href": "http://localhost:8080/api/products"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
```

Đây là ví dụ minh họa. Link thực tế được sinh từ repository đã export và cấu hình của ứng dụng.

Client có thể bắt đầu từ root, đọc relation `categories` rồi gọi link `href`. Khi cần xem mô tả resource, client theo link `profile`. Spring Data REST cung cấp ALPS metadata cho repository resources; một số profile endpoint cũng có thể trả JSON Schema khi client gửi `Accept: application/schema+json`.

### 6.1. Đọc collection

```bash
curl -i   -H "Accept: application/hal+json"   "http://localhost:8080/api/categories?page=0&size=10&sort=name,asc"
```

Response HAL collection thường có dạng:

```json
{
  "_embedded": {
    "categories": [
      {
        "code": "BOOKS",
        "name": "Books",
        "description": "Printed and digital books",
        "active": true,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/categories/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/categories{?page,size,sort}",
      "templated": true
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/categories"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
```

Các property `_embedded.categories` và `page` cho client biết dữ liệu và trạng thái trang. Relation name `categories` được đặt trong `collectionResourceRel`. Client nên sử dụng link `next` hoặc `prev` khi chúng xuất hiện thay vì tự tính URL trang tiếp theo.

## 7. Tạo và cập nhật danh mục

### 7.1. POST tạo mới

```bash
curl -i -X POST http://localhost:8080/api/categories   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{
    "code": "BOOKS",
    "name": "Books",
    "description": "Printed and digital books",
    "active": true
  }'
```

Request body chứa các field của entity. Client không cần gửi `id` vì khóa được sinh bởi database. Khi thành công, Spring Data REST thường trả `201 Created` và header `Location` trỏ đến item resource vừa tạo. Có `Accept` thì response body mặc định có representation; nếu không gửi `Accept`, body có thể rỗng và client theo `Location` để đọc resource.

### 7.2. GET item

```bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api/categories/1
```

### 7.3. PUT thay thế item

```bash
curl -i -X PUT http://localhost:8080/api/categories/1   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{
    "code": "BOOKS",
    "name": "Books and Media",
    "description": "Updated category description",
    "active": true
  }'
```

`PUT` thay thế trạng thái của resource theo body gửi lên. Đảm bảo body có các field cần giữ lại, vì field bị bỏ khỏi body có thể được hiểu là giá trị rỗng/default tùy mapping và entity.

### 7.4. PATCH cập nhật một phần

```bash
curl -i -X PATCH http://localhost:8080/api/categories/1   -H "Content-Type: application/merge-patch+json"   -H "Accept: application/hal+json"   --data '{"active": false}'
```

Dùng media type và body đúng semantics của JSON Merge Patch. Spring Data REST hỗ trợ các media type JSON Patch và JSON Merge Patch cho item PATCH; không đổi header nếu body không theo định dạng tương ứng.

### 7.5. DELETE xóa danh mục

```bash
curl -i -X DELETE http://localhost:8080/api/categories/1
```

Xóa có thể bị từ chối bởi ràng buộc khóa ngoại nếu sản phẩm còn tham chiếu danh mục. Quy tắc xóa danh mục trong ứng dụng thực tế cần được thiết kế theo nghiệp vụ: chặn xóa, chuyển sản phẩm sang danh mục khác, hoặc áp dụng chính sách archive/soft delete. Không tự động bật cascade delete nếu chưa xác định tác động dữ liệu.

## 8. Tìm kiếm, phân trang và sắp xếp

Query method trong `CategoryRepository` tạo một search resource. Gọi:

```bash
curl -i   -H "Accept: application/hal+json"   "http://localhost:8080/api/categories/search/by-name?name=book&page=0&size=10"
```

Các tham số:

- `name`: giá trị được truyền vào `@Param("name")`.
- `page`: số trang, mặc định bắt đầu từ 0.
- `size`: số phần tử trên một trang, mặc định thường là 20.
- `sort`: property và chiều sắp xếp, ví dụ `sort=name,asc`.

Ví dụ tìm kiếm và sắp xếp:

```bash
curl -i   -H "Accept: application/hal+json"   "http://localhost:8080/api/categories/search/by-name?name=book&sort=name,asc&page=0&size=5"
```

Nếu repository method trả `Page` hoặc `Slice` và nhận `Pageable`, Spring Data REST có thể cung cấp metadata và navigation links. Giới hạn page size tối đa phù hợp để tránh client yêu cầu lượng dữ liệu quá lớn.

## 9. Quản lý association giữa Product và Category

Vì `Product` có field `category` tham chiếu tới entity có repository được export, item resource của sản phẩm có association link. Đọc sản phẩm:

```bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api/products/10
```

Representation có thể chứa link tương tự:

```json
{
  "sku": "BOOK-001",
  "name": "Spring in Practice",
  "price": 29.90,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/10"
    },
    "category": {
      "href": "http://localhost:8080/api/products/10/category"
    }
  }
}
```

Link `category` dẫn tới association resource. Để gán sản phẩm vào danh mục, gửi URI của category:

```bash
curl -i -X PUT http://localhost:8080/api/products/10/category   -H "Content-Type: text/uri-list"   --data 'http://localhost:8080/api/categories/1'
```

Association `PUT` dùng `text/uri-list`. Đây là request liên kết resource đã tồn tại, không phải JSON body để tạo entity. Sau khi gán, GET association resource hoặc GET lại product để xác nhận liên kết.

## 10. Validation, projections và metadata

### 10.1. Validation

Có thể dùng Jakarta Bean Validation annotations như `@NotBlank`, `@Size` và `@Positive` để mô tả giới hạn dữ liệu. Với các quy tắc nghiệp vụ phụ thuộc repository hoặc trạng thái khác, Spring Data REST hỗ trợ đăng ký `Validator` theo repository event như `beforeCreate` và `beforeSave`.

Ví dụ tên bean validator theo event:

```java
@Component("beforeCreateCategoryValidator")
class CategoryCreateValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Category.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Category category = (Category) target;
        if (category.getCode() != null
                && category.getCode().contains(" ")) {
            errors.rejectValue(
                "code",
                "category.code.whitespace",
                "Category code must not contain spaces"
            );
        }
    }
}
```

Bean name có prefix `beforeCreate` để Spring Data REST gắn validator vào event tạo mới. Nếu cần áp dụng trước khi cập nhật, dùng event phù hợp như `beforeSave`. Cần cấu hình validator đúng với phiên bản Spring Data REST và kiểm tra lỗi trả về bằng integration test.

### 10.2. Projections và excerpts

Mặc định Spring Data REST có thể hiển thị các thuộc tính domain được export. Khi client cần một view rút gọn, định nghĩa interface projection:

```java
@Projection(name = "summary", types = Category.class)
public interface CategorySummary {
    String getCode();
    String getName();
    boolean isActive();
}
```

Projection phải được Spring Data REST phát hiện, ví dụ nằm cùng package entity hoặc sub-package, hoặc được đăng ký thủ công. Client có thể gọi item resource với `?projection=summary`.

Không đưa dữ liệu nhạy cảm như password, token hoặc internal-only fields vào entity representation. Projections có thể làm lộ field ngay cả khi field bị ẩn bằng một cấu hình serialization khác; chỉ khai báo projection cho những field thực sự được phép công khai.

### 10.3. Profile, ALPS và JSON Schema

Root resource cung cấp link `profile`. Theo link này, client có thể tìm metadata mô tả repository resources. Spring Data REST cung cấp ALPS cho các transition và thuộc tính của repository; JSON Schema có thể được yêu cầu bằng `Accept: application/schema+json` ở profile resource phù hợp.

Metadata giúp client hiểu resource và field mà không phải đoán từ tên Java class. Dù vậy, API contract công khai vẫn nên được tài liệu hóa và kiểm soát thay đổi theo phiên bản.

## 11. Kiểm soát repository exposure và bảo mật

Spring Data REST có thể export nhiều method CRUD chỉ bằng cách khai báo repository. Điều đó thuận tiện cho API đơn giản nhưng có nghĩa mọi public repository đủ điều kiện có thể trở thành HTTP API.

Trước khi triển khai:

- Chỉ export các repository phù hợp với API công khai.
- Dùng `@RepositoryRestResource(exported = false)` để ẩn repository không nên public.
- Dùng `@RestResource(exported = false)` để ẩn query method hoặc method không nên tạo endpoint.
- Xem xét repository detection strategy nếu ứng dụng có nhiều repository nội bộ.
- Cấu hình Spring Security cho từng nhóm resource và method.
- Phân quyền DELETE, PUT và PATCH theo nghiệp vụ; không cho rằng việc endpoint được tạo tự động đồng nghĩa endpoint đó được phép truy cập công khai.

Spring Data REST hỗ trợ method-level security với `@PreAuthorize` và `@Secured`. Nếu đặt security annotation ở repository và override method để đổi quyền, cần hiểu rằng method-level settings override repository-level settings; chúng không tự động kết hợp. Các method delete kế thừa có nhiều overload, nên cần bảo vệ đầy đủ các đường xóa.

Spring Data REST phù hợp khi CRUD repository phản ánh đúng hợp đồng API. Với workflow nhiều bước, orchestration, kiểm tra quyền phức tạp hoặc nghiệp vụ không thể biểu diễn bằng CRUD, hãy dùng service layer và custom controller phù hợp thay vì export trực tiếp mọi thao tác persistence.

## 12. Kiểm thử API bằng MockMvc

Dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để test Spring Data REST qua application context. Ví dụ giả định đã có database test và `CategoryRepository`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CatalogApiTests {

    private static final MediaType HAL_JSON =
            MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CategoryRepository categoryRepository;

    @BeforeEach
    void setUp() {
        categoryRepository.deleteAll();
        categoryRepository.save(
            new Category("BOOKS", "Books", "Printed books")
        );
    }

    @Test
    void rootPublishesCategoryLink() throws Exception {
        mockMvc.perform(get("/api").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.categories.href").exists());
    }

    @Test
    void listsCategoriesAsHalCollection() throws Exception {
        mockMvc.perform(get("/api/categories").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._embedded.categories[0].code")
                .value("BOOKS"));
    }

    @Test
    void createsCategory() throws Exception {
        mockMvc.perform(post("/api/categories")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(HAL_JSON)
                .content("""
                    {
                      "code": "GAMES",
                      "name": "Games",
                      "description": "Board and video games",
                      "active": true
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"));
    }

    @Test
    void searchesCategoriesByName() throws Exception {
        mockMvc.perform(get("/api/categories/search/by-name")
                .param("name", "book")
                .accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.categories[0].name")
                .value("Books"));
    }
}
```

Các import chính:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Chạy test bằng `./mvnw test` hoặc `./gradlew test` tùy build tool. Nếu test nhận 404, kiểm tra repository detection, package scan và base path. Nếu GET trả JSON nhưng không có `_embedded.categories`, kiểm tra relation name trong `@RepositoryRestResource` và dữ liệu test. Nếu POST trả 400, xem validation error và body; nếu trả 405, kiểm tra method repository có được export hay không.

Ngoài các test trên, nên có test cho:

- Category item GET/PUT/PATCH/DELETE.
- Query method khi không có kết quả và khi có nhiều trang.
- Product association GET/PUT và URI không tồn tại.
- Validation khi code hoặc name trống/quá dài.
- Quyền truy cập của user thường và administrator.
- Repository hoặc method được đánh dấu `exported = false` không tạo endpoint công khai.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| GET root không có link categories | Repository không được export, sai package scan hoặc detection strategy |
| GET /categories trả 404 | Base path, path annotation hoặc repository detection không đúng |
| POST trả 405 | Repository không export `save` hoặc method bị ẩn |
| POST trả 400 | JSON không hợp lệ, field mapping sai hoặc validation thất bại |
| POST trả 415 | `Content-Type` không được hỗ trợ; collection POST thường nhận JSON/HAL JSON |
| PATCH trả 415 | Media type hoặc cấu trúc JSON Patch/Merge Patch không đúng |
| Association PUT trả 415 | Phải dùng `Content-Type: text/uri-list` |
| Association PUT trả 400 | URI list không hợp lệ hoặc nhiều URI được gửi vào association to-one |
| Collection response không có embedded data | Không có bản ghi, relation name khác hoặc representation được tùy biến |
| Không thấy search link | Repository chưa khai báo query method được export |
| Dữ liệu nhạy cảm xuất hiện trong HAL | Entity đang export field không nên public; kiểm tra Jackson mapping và projection |

## 14. Checklist hoàn thành bài thực hành

- [ ] Đã thêm Spring Data REST và persistence starter phù hợp.
- [ ] Đã tạo entity Category với khóa chính, mã duy nhất và field cần thiết.
- [ ] Đã tạo entity Product và quan hệ tới Category.
- [ ] Đã khai báo CategoryRepository và ProductRepository.
- [ ] Đã xác định rõ collection path và relation name.
- [ ] GET root trả HAL links đến categories, products và profile.
- [ ] GET collection và item trả HAL JSON.
- [ ] POST tạo category và trả Location.
- [ ] PUT/PATCH/DELETE hoạt động theo hợp đồng đã chọn.
- [ ] Search query method được khám phá qua search resource.
- [ ] Association Product → Category được cập nhật bằng URI list.
- [ ] Đã giới hạn dữ liệu được export và cấu hình quyền truy cập.
- [ ] Đã viết integration tests cho các thao tác chính và các lỗi phổ biến.

## Tài liệu chính thức

1. [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): starter, auto-configuration, repository detection và base path.
2. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): cách repository trở thành collection, item, association, search và query resources.
3. [Spring Data REST — Domain Object Representations](https://docs.spring.io/spring-data/rest/reference/representations.html): JSON representation và cách Spring Data REST mapping domain objects.
4. [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): định nghĩa projection và excerpt để điều chỉnh representation.
5. [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page, size, sort và navigation links.
6. [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html): ALPS và JSON Schema.
7. [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): đăng ký validator theo repository events.
8. [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html): method-level security với Spring Security.
9. [Spring Data JPA — Defining Repository Interfaces](https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html): domain-specific repositories, CRUD interfaces và paging/sorting interfaces.
10. [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): kiểm thử Spring MVC request/response trong application context.

*Ví dụ dùng Spring Boot, Spring Data JPA và Jakarta Persistence. Hãy đối chiếu package, starter và phiên bản tài liệu với dependency thực tế của ứng dụng trước khi triển khai.*