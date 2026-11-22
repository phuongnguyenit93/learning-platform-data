# Interface cơ sở dùng chung và `@NoRepositoryBean`

Trong một ứng dụng Spring Data Elasticsearch, nhiều entity thường cần cùng một nhóm thao tác repository: lưu document, tìm theo ID, xóa, đếm hoặc truy vấn theo các thuộc tính chung. Nếu mỗi repository đều lặp lại cùng khai báo và cùng logic hỗ trợ, mã nguồn sẽ khó bảo trì khi quy tắc chung thay đổi.

Spring Data cho phép tạo **repository interface cơ sở dùng chung** bằng generic type. Repository cụ thể kế thừa interface này và cung cấp kiểu entity cùng kiểu ID. Annotation `@NoRepositoryBean` đánh dấu interface trung gian không phải một repository bean độc lập. Spring Data bỏ qua việc tạo implementation cho interface cơ sở, nhưng vẫn sử dụng các method của nó khi tạo repository cho interface cụ thể.

Bài học này trình bày cách thiết kế generic repository interface, vai trò của `@NoRepositoryBean`, cách Spring Data phát hiện repository, cách method được kế thừa và phân tích theo entity cụ thể, cũng như sự khác nhau giữa interface cơ sở, custom repository fragment và custom repository base class.

## 1. Repository interface trong Spring Data Elasticsearch

Spring Data repository là abstraction giúp ứng dụng thao tác với dữ liệu thông qua interface. Spring Data tạo implementation runtime dựa trên repository interface và loại datastore được cấu hình.

Với Spring Data Elasticsearch, repository thường kế thừa `ElasticsearchRepository<T, ID>`:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Hai generic type có ý nghĩa:

- `T`: kiểu entity/document mà repository quản lý, ở đây là `Product`.
- `ID`: kiểu định danh của entity, ở đây là `String`.

Spring Data sử dụng thông tin này để xác định mapping metadata, chuyển đổi entity/document và tạo các thao tác repository phù hợp.

Một repository cụ thể thường có thể khai báo thêm query method:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

Spring Data phân tích tên method `findByCategory` theo thuộc tính của entity `Product`, sau đó tạo query phù hợp. Nếu nhiều entity có cùng một nhóm thao tác, có thể đưa các method dùng chung vào interface cha.

## 2. Vì sao cần interface cơ sở dùng chung?

Giả sử ứng dụng có các entity `Product`, `Customer` và `Order`. Mỗi repository có thể cần:

- Thao tác CRUD chuẩn.
- Một số method tiện ích chung, ví dụ tìm entity bắt buộc phải tồn tại theo ID.
- Quy tắc truy vấn theo tenant nếu các entity đều có field `tenantId`.
- Các method nghiệp vụ thống nhất giữa nhiều repository.

Nếu viết lại cùng một method ở từng repository, thay đổi nhỏ phải được thực hiện nhiều lần. Generic base repository cho phép mô tả một lần và tái sử dụng:

```text
BaseElasticsearchRepository<T, ID>
                 |
       +---------+---------+
       |         |         |
       v         v         v
ProductRepository  CustomerRepository  OrderRepository
<Product,String>  <Customer,String>    <Order,String>
```

Generic type giúp interface cơ sở không phụ thuộc vào một entity cụ thể. Repository con cung cấp type cụ thể khi kế thừa.

## 3. Tạo generic repository interface

Tạo interface cơ sở có hai generic type `T` và `ID`:

```java
package com.example.catalog.repository;

import java.util.NoSuchElementException;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    default T getRequiredById(ID id) {
        return findById(id).orElseThrow(
                () -> new NoSuchElementException("Document not found: " + id));
    }
}
```

Interface này kế thừa `ElasticsearchRepository<T, ID>`, vì vậy repository cụ thể nhận được các thao tác mà Spring Data Elasticsearch cung cấp. Method `getRequiredById` là Java default method; nó dùng lại `findById` và ném exception nếu không tìm thấy document.

`@NoRepositoryBean` là annotation quan trọng trên interface cơ sở. Nó báo cho repository infrastructure rằng không được tạo một repository bean độc lập cho interface này. Interface chỉ đóng vai trò định nghĩa chung để các repository cụ thể kế thừa.

### 3.1. Tại sao interface generic cần `@NoRepositoryBean`?

Spring Data quét các interface repository trong phạm vi cấu hình. Nếu một interface kế thừa repository abstraction và không bị loại khỏi quá trình tạo repository, Spring Data có thể xem nó là repository candidate.

Với interface tổng quát như:

```java
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {
}
```

Spring Data không có một entity cụ thể để tạo repository độc lập cho `T`. Repository cần biết domain type và ID type thực tế để xây dựng mapping context, query method và implementation. Interface trung gian chỉ nên được dùng sau khi một interface con cung cấp các kiểu cụ thể.

`@NoRepositoryBean` giúp loại interface cơ sở khỏi việc tạo bean. Nếu thiếu annotation, quá trình khởi động có thể thất bại vì Spring Data cố tạo repository cho interface chưa được tham số hóa bằng domain type cụ thể, hoặc phát sinh lỗi liên quan đến việc xác định domain type.

Annotation này không xóa các method của interface và cũng không ngăn interface con kế thừa chúng. Nó chỉ đánh dấu interface hiện tại không phải repository bean cần khởi tạo.

## 4. Tạo repository cụ thể kế thừa interface cơ sở

Giả sử entity `Product`:

```java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructors, getters and setters
}
```

Repository cụ thể kế thừa interface cơ sở và cung cấp kiểu thực tế:

```java
package com.example.catalog.repository;

import java.util.List;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends BaseElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

Khi Spring Data phát hiện `ProductRepository`, nó biết:

- Domain type là `Product`.
- ID type là `String`.
- Các method kế thừa từ `ElasticsearchRepository` được cung cấp cho `Product`.
- Method `getRequiredById` được kế thừa từ base interface.
- Method `findByCategory` được phân tích theo mapping của `Product`.

Spring Data tạo bean cho `ProductRepository`. Nó không tạo bean riêng cho `BaseElasticsearchRepository` vì interface đó có `@NoRepositoryBean`.

## 5. Dùng một interface cơ sở cho nhiều entity

Các repository khác có thể kế thừa cùng interface:

```java
public interface CustomerRepository
        extends BaseElasticsearchRepository<Customer, String> {
}

public interface OrderRepository
        extends BaseElasticsearchRepository<Order, String> {
}
```

Mỗi repository con cung cấp domain type riêng. Các method CRUD và default method từ base interface được dùng theo type tương ứng.

Ví dụ service có thể inject repository cụ thể:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Product getRequired(String id) {
        return productRepository.getRequiredById(id);
    }
}
```

Service không cần biết chi tiết implementation do Spring Data tạo. Nó chỉ phụ thuộc vào interface cụ thể của domain.

## 6. Đưa query method dùng chung vào interface cơ sở

Một interface cơ sở có thể khai báo query method nếu method đó hợp lệ với mọi domain type kế thừa nó.

Ví dụ, các document trong một hệ thống đều có `tenantId`. Có thể mô tả contract bằng một interface Java:

```java
public interface TenantScoped {
    String getTenantId();
}
```

Entity cụ thể có thuộc tính `tenantId`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product implements TenantScoped {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String name;

    @Override
    public String getTenantId() {
        return tenantId;
    }
}
```

Generic repository cho các entity thuộc tenant:

```java
import java.util.List;

import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface TenantScopedRepository<T extends TenantScoped, ID>
        extends BaseElasticsearchRepository<T, ID> {

    List<T> findByTenantId(String tenantId);
}
```

Repository cụ thể:

```java
public interface ProductRepository
        extends TenantScopedRepository<Product, String> {

    List<Product> findByName(String name);
}
```

Spring Data phân tích `findByTenantId` dựa trên domain type cụ thể là `Product`. Do `Product` có persistent property `tenantId`, method có thể được tạo thành query.

Điều kiện quan trọng: mọi domain type dùng `TenantScopedRepository` phải thực sự có persistent property mà query method tham chiếu. Java interface `TenantScoped` giúp biểu đạt contract ở cấp mã nguồn, nhưng Spring Data vẫn cần tìm thấy property tương ứng trong metadata của entity.

Nếu một repository con dùng entity không có field `tenantId`, Spring Data có thể báo lỗi lúc khởi tạo repository, chẳng hạn không tìm thấy property được tham chiếu trong method name. Không nên đưa query method phụ thuộc một field riêng của một entity vào base interface dùng cho mọi entity.

## 7. Có thể tạo nhiều tầng interface cơ sở

Ứng dụng có thể xây dựng các tầng interface để tái sử dụng theo nhóm domain:

```text
ElasticsearchRepository<T, ID>
              |
              v
BaseElasticsearchRepository<T, ID>
              |
              v
TenantScopedRepository<T extends TenantScoped, ID>
              |
              +-------------------+
              |                   |
              v                   v
ProductRepository           CustomerRepository
```

Mỗi interface trung gian không được tạo bean riêng, vì vậy cần đánh dấu `@NoRepositoryBean` trên từng interface trung gian được dùng làm base repository.

Ví dụ:

```java
@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {
    // Shared methods
}

@NoRepositoryBean
public interface TenantScopedRepository<T extends TenantScoped, ID>
        extends BaseElasticsearchRepository<T, ID> {
    List<T> findByTenantId(String tenantId);
}

public interface ProductRepository
        extends TenantScopedRepository<Product, String> {
}
```

Khi một interface trung gian mới được thêm vào, hãy đánh giá xem nó có phải repository bean thực tế hay chỉ là định nghĩa chung. Nếu chỉ là định nghĩa chung, gắn `@NoRepositoryBean`.

## 8. `@NoRepositoryBean` không đặt trên repository cụ thể

Annotation này dành cho interface cơ sở không được khởi tạo trực tiếp. Không đặt nó lên interface repository cụ thể mà service cần inject.

Ví dụ không phù hợp:

```java
@NoRepositoryBean
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Trong trường hợp này, Spring Data được yêu cầu bỏ qua việc tạo bean `ProductRepository`. Nếu service inject `ProductRepository`, ứng dụng có thể không tìm thấy bean tương ứng.

Cách khai báo phù hợp:

```java
@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {
}

public interface ProductRepository
        extends BaseElasticsearchRepository<Product, String> {
}
```

Chỉ interface cơ sở nhận `@NoRepositoryBean`; interface cụ thể được để Spring Data khởi tạo.

## 9. Repository scanning và package structure

Spring Boot thường tự phát hiện repository trong phạm vi package scan bắt đầu từ package của lớp `@SpringBootApplication` và các package con. Ví dụ cấu trúc:

```text
com.example.catalog
├── CatalogApplication.java
├── domain
│   ├── Product.java
│   └── Customer.java
├── repository
│   ├── BaseElasticsearchRepository.java
│   ├── TenantScopedRepository.java
│   ├── ProductRepository.java
│   └── CustomerRepository.java
└── service
    └── ProductService.java
```

Các interface repository nên nằm trong package được scan. Nếu repository nằm ngoài phạm vi mặc định hoặc muốn cấu hình rõ package, có thể dùng `@EnableElasticsearchRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository")
public class ElasticsearchRepositoryConfig {
}
```

Không cần thêm annotation này nếu auto-configuration đã quét đúng package. Tránh cấu hình scan trùng hoặc quá rộng khiến repository ngoài ý muốn được phát hiện.

`@NoRepositoryBean` vẫn có ý nghĩa khi repository scanning được cấu hình tường minh: interface cơ sở được loại khỏi việc tạo bean, còn repository cụ thể trong phạm vi scan được xử lý bình thường.

## 10. Method nào phù hợp để đặt trong base interface?

Không phải mọi method nên được đưa lên interface cơ sở. Hãy phân biệt ba nhóm:

| Nhóm method | Ví dụ | Có nên đặt ở base interface? |
|---|---|---|
| Method tổng quát không phụ thuộc field riêng | `getRequiredById(ID id)` | Có, nếu nhiều repository cần cùng hành vi |
| Query method dựa trên property có ở mọi entity thuộc nhóm | `findByTenantId(String tenantId)` | Có, nếu contract được đảm bảo và mapping tồn tại ở mọi entity |
| Query method dựa trên field riêng của một entity | `findByCategory(String category)` | Đặt trong repository cụ thể của entity đó |

Một base interface tốt nên chứa những contract thực sự chung. Nếu base interface chứa quá nhiều query method đặc thù, các entity phải có cấu trúc giống nhau một cách gượng ép và việc thay đổi domain trở nên khó khăn.

### 10.1. Default method cho logic chung

Default method phù hợp với logic nhỏ có thể triển khai bằng các method repository đã có:

```java
@NoRepositoryBean
public interface BaseElasticsearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    default boolean existsAndHasId(ID id) {
        return id != null && existsById(id);
    }
}
```

Default method được triển khai ngay trong interface Java và không cần khai báo custom implementation chỉ để ghép một vài method có sẵn.

Nếu logic cần gọi API Elasticsearch phức tạp, xử lý nhiều bước hoặc phụ thuộc dịch vụ khác, hãy cân nhắc service hoặc custom repository fragment thay vì nhồi toàn bộ logic vào base interface.

### 10.2. Query method được phân tích theo entity cụ thể

Method name như `findByTenantId` được phân tích khi Spring Data tạo repository cụ thể. Property path phải tồn tại trên domain type cuối cùng. Với nested property, tên method phải phù hợp với cấu trúc property path và quy tắc phân tách của Spring Data.

Nếu property path không hợp lệ, lỗi thường xuất hiện khi khởi tạo repository thay vì chỉ khi method được gọi. Điều này giúp phát hiện mapping/query contract không nhất quán sớm trong quá trình khởi động.

## 11. `@NoRepositoryBean` khác với custom repository implementation

`@NoRepositoryBean` chỉ điều khiển việc Spring Data có tạo repository bean cho interface hiện tại hay không. Nó không cung cấp implementation tùy chỉnh cho method và cũng không thay thế cơ chế mở rộng repository.

Spring Data có những cơ chế khác cho logic tùy chỉnh:

- **Default method:** triển khai logic nhỏ ngay trong interface.
- **Repository fragment:** tách một nhóm method tùy chỉnh thành interface riêng và lớp implementation tương ứng.
- **Custom repository base class:** thay đổi implementation cơ sở được dùng cho nhiều repository.

Ba cơ chế này giải quyết những nhu cầu khác nhau. `@NoRepositoryBean` có thể xuất hiện trên generic base interface, trong khi fragments hoặc base class được cấu hình riêng để bổ sung implementation.

## 12. Dùng repository fragment cho hành vi Elasticsearch chuyên biệt

Khi một số repository cần truy vấn phức tạp, có thể tạo fragment thay vì thêm method đặc thù vào base interface dùng chung.

Interface fragment:

```java
import java.util.List;

public interface ProductSearchRepository {
    List<Product> searchByText(String text);
}
```

Implementation fragment (minh họa cấu trúc; phần tạo query tùy API của phiên bản Spring Data Elasticsearch):

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchRepositoryImpl implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByText(String text) {
        // Build a full-text query and execute it with ElasticsearchOperations.
        // The exact NativeQuery API depends on the Spring Data release train.
        throw new UnsupportedOperationException("Implement the version-specific query here");
    }
}
```

Repository cụ thể kết hợp repository chuẩn và fragment:

```java
public interface ProductRepository
        extends BaseElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
```

Spring Data kết hợp method CRUD/query method được tạo tự động với method tùy chỉnh từ fragment. Quy ước đặt tên implementation và cách đăng ký phụ thuộc cơ chế repository fragment của Spring Data; hãy theo tài liệu phiên bản đang sử dụng.

Ví dụ trên tập trung vào cấu trúc fragment. Trong mã chạy thực tế, thay phần placeholder bằng query cụ thể sử dụng `NativeQuery`, `ElasticsearchOperations` hoặc API được hỗ trợ bởi release train của dự án.

## 13. Custom repository base class là một cơ chế khác

Nếu muốn thay đổi implementation cơ sở cho nhiều repository, Spring Data cho phép cấu hình repository base class. Đây là lớp triển khai repository, không phải interface dùng chung và cũng không được điều khiển bởi `@NoRepositoryBean`.

Một custom base class thường kế thừa implementation mặc định của Spring Data Elasticsearch và bổ sung hành vi chung. Constructor của nó phải phù hợp với factory/repository infrastructure của phiên bản Spring Data đang dùng.

Chỉ chọn cơ chế này khi cần thay đổi hành vi nền tảng cho nhiều repository và đã xác định rõ API constructor. Với logic chỉ dùng ở một vài repository, repository fragment thường dễ cô lập hơn. Với logic nhỏ dựa trên method có sẵn, default method thường đơn giản hơn.

## 14. Các thay đổi API giữa các phiên bản Spring Data

Repository hierarchy có thể thay đổi giữa các major version của Spring Data. Đặc biệt, Spring Data 3.x điều chỉnh quan hệ giữa `CrudRepository`, `ListCrudRepository`, `PagingAndSortingRepository` và các abstraction liên quan. Vì vậy, không nên giả định mọi interface repository luôn kế thừa cùng một tập method ở tất cả phiên bản.

`ElasticsearchRepository<T, ID>` là abstraction chuyên biệt của Spring Data Elasticsearch. Hãy kiểm tra Javadoc của đúng phiên bản dependency để biết chính xác interface đó kế thừa các contract nào, kiểu collection được trả về và những API Elasticsearch-specific được cung cấp.

Khi xây dựng base interface, có thể kế thừa `ElasticsearchRepository<T, ID>` nếu muốn sử dụng repository abstraction chuyên biệt của Elasticsearch. Nếu tự kết hợp các interface như `CrudRepository` và `PagingAndSortingRepository`, hãy xác nhận hierarchy ở release train đang dùng để tránh method bị thiếu hoặc trùng lặp không cần thiết.

Không thêm một phiên bản `spring-data-commons` hoặc `spring-data-elasticsearch` riêng chỉ để có một interface mới mà không kiểm tra dependency management của Spring Boot. Các module Spring Data cần tương thích với nhau.

## 15. Những lỗi thường gặp

### Quên `@NoRepositoryBean` trên generic base interface

Spring Data có thể cố khởi tạo repository cho interface trung gian chưa có domain type cụ thể. Đánh dấu base interface bằng `@NoRepositoryBean`.

### Đặt `@NoRepositoryBean` lên repository cụ thể

Spring Data bỏ qua repository đó, khiến service không thể inject bean. Chỉ đặt annotation trên interface trung gian không cần được khởi tạo.

### Query method dùng property không có ở mọi entity

Một method như `findByCategory` trong base interface chỉ hợp lệ nếu mọi domain type kế thừa đều có persistent property `category`. Nếu không, tách method vào repository cụ thể hoặc tạo base interface chuyên biệt có type bound/contract phù hợp.

### Dùng generic type không xác định rõ

Khai báo repository con với raw type hoặc không cung cấp domain/ID type cụ thể có thể khiến Spring Data không xác định được metadata cần thiết. Kế thừa base interface với đầy đủ generic arguments, ví dụ `Product, String`.

### Đặt logic nghiệp vụ phức tạp trong interface cơ sở

Base interface trở nên khó hiểu nếu chứa nhiều query và logic đặc thù. Tách logic thành service hoặc repository fragment theo phạm vi sử dụng.

### Nhầm `@NoRepositoryBean` với `@Repository`

`@NoRepositoryBean` không phải annotation đăng ký bean. Nó loại interface cơ sở khỏi việc tạo repository bean. Repository cụ thể được Spring Data phát hiện thông qua repository scanning.

### Dùng API không có trong phiên bản Spring Data đang chạy

Các interface và method repository thay đổi qua release train. Kiểm tra dependency tree và Javadoc của đúng phiên bản thay vì dựa trên ví dụ từ một major version khác.

## 16. Quy trình thiết kế base repository

Khi muốn tạo interface cơ sở dùng chung, có thể làm theo trình tự:

1. Liệt kê những thao tác thực sự dùng chung giữa các entity.
2. Chọn generic type `T` và `ID` để thể hiện domain cùng kiểu định danh.
3. Kế thừa `ElasticsearchRepository<T, ID>` hoặc abstraction phù hợp với release train.
4. Đặt `@NoRepositoryBean` trên interface trung gian.
5. Chỉ đưa query method vào base interface khi mọi entity kế thừa đều có property path tương ứng.
6. Dùng default method cho logic nhỏ dựa trên repository method đã có.
7. Dùng repository fragment hoặc service cho logic tìm kiếm phức tạp và đặc thù.
8. Tạo repository cụ thể với domain type và ID type rõ ràng.
9. Đảm bảo package scan phát hiện repository cụ thể.
10. Khởi động ứng dụng để Spring Data phân tích repository method và phát hiện lỗi property path sớm.

## 17. Tổng kết

Generic repository interface giúp chuẩn hóa các thao tác dùng chung giữa nhiều repository trong Spring Data Elasticsearch. Interface cơ sở thường khai báo `T` cho entity và `ID` cho kiểu định danh, sau đó kế thừa `ElasticsearchRepository<T, ID>` để nhận các thao tác repository chuẩn.

`@NoRepositoryBean` đánh dấu interface trung gian không được tạo thành repository bean độc lập. Repository cụ thể kế thừa interface đó và cung cấp domain type cùng ID type thực tế, nhờ vậy Spring Data vẫn tạo implementation cho repository cụ thể và áp dụng các method được kế thừa.

Chỉ đưa vào base interface những method có ý nghĩa với mọi entity trong nhóm. Query method phụ thuộc property phải khớp mapping của từng domain type. Với logic phức tạp, dùng service hoặc repository fragment; với thay đổi implementation nền tảng, cân nhắc custom repository base class. Phân biệt đúng các cơ chế này giúp repository dễ tái sử dụng, dễ kiểm soát và tương thích hơn với các phiên bản Spring Data Elasticsearch.
