# Quy ước tên lớp, phạm vi quét và ghép fragment

Khi một repository Spring Data Elasticsearch cần thêm truy vấn hoặc hành vi riêng, ứng dụng có thể mở rộng repository bằng custom implementation. Spring Data không chỉ tìm interface repository mà còn phải phát hiện implementation tương ứng, ghép các fragment vào repository proxy và đăng ký những dependency cần thiết.

Ba phần này có quy tắc riêng:

- **Phạm vi quét repository:** Spring Data tìm các interface cần tạo repository bean trong package nào.
- **Quy ước tên implementation:** Spring Data liên kết fragment interface với lớp implementation dựa trên tên và postfix.
- **Ghép fragment:** repository proxy kết hợp các interface/implementation tùy biến với chức năng CRUD cơ sở.

Nếu cấu hình package scan sai, repository bean có thể không được tạo. Nếu tên implementation sai, ứng dụng có thể khởi động nhưng custom method không được gắn đúng hoặc quá trình khởi tạo repository thất bại. Nếu ghép nhiều fragment không rõ ràng, method trùng chữ ký có thể được gọi từ implementation không mong muốn.

Spring Data hiện khuyến nghị mô hình repository composition bằng các fragment độc lập. Mỗi fragment mô tả một nhóm hành vi, có implementation riêng và được repository chính kế thừa. Quy ước implementation cũ theo tên toàn bộ repository vẫn có thể xuất hiện trong codebase, nhưng không phù hợp để mở rộng nhiều nhóm hành vi lâu dài.

## 1. Repository proxy được hình thành như thế nào?

Một repository Spring Data thường là interface. Ứng dụng không tự viết class triển khai toàn bộ CRUD mà Spring Data tạo proxy lúc khởi động.

Ví dụ:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Spring Data tạo bean proxy cho `ProductRepository`, cung cấp các thao tác kế thừa từ `ElasticsearchRepository` như `save`, `findById`, `findAll`, `deleteById` và các query method được định nghĩa trên interface.

Khi repository có custom fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
```

Spring Data vẫn tạo một repository proxy, nhưng proxy còn được ghép với implementation của `ProductSearchFragment`. Vì vậy, controller/service chỉ cần inject `ProductRepository` và gọi cả CRUD cơ sở lẫn custom method.

```text
ProductRepository interface
          |
          +---- ElasticsearchRepository base behavior
          |
          +---- ProductSearchFragment
          |          |
          |          +---- ProductSearchFragmentImpl
          |
          v
   Repository proxy bean
          |
          v
   Service injects ProductRepository
```

Custom fragment không tạo một repository bean độc lập. Nó bổ sung hành vi vào repository proxy đã được phát hiện.

## 2. Tổ chức package và tên lớp

Một cấu trúc package dễ quản lý:

```text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── Product.java
│   ├── ProductRepository.java
│   ├── ProductSearchFragment.java
│   ├── ProductSearchFragmentImpl.java
│   ├── ProductInventoryFragment.java
│   └── ProductInventoryFragmentImpl.java
└── order
    ├── Order.java
    └── OrderRepository.java
```

Trong đó:

- `ProductRepository` là repository chính.
- `ProductSearchFragment` khai báo nhóm chức năng tìm kiếm đặc thù.
- `ProductSearchFragmentImpl` triển khai fragment đó.
- `ProductInventoryFragment` và implementation của nó là một nhóm hành vi độc lập khác.
- Các fragment có thể dùng chung `ElasticsearchOperations` hoặc service khác qua constructor injection.

Đặt fragment interface và implementation gần nhau giúp quy ước tên dễ nhận biết và tránh việc một implementation vô tình bị gắn với repository không liên quan.

## 3. Quy ước tên implementation cho repository fragment

Với mô hình fragment hiện đại, tên lớp implementation được tạo từ tên fragment interface cộng với repository implementation postfix. Postfix mặc định là `Impl`.

Ví dụ:

```java
public interface ProductSearchFragment {
    List<Product> searchAvailableProducts(String keyword);
}
```

Implementation tương ứng:

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchAvailableProducts(String keyword) {
        // Build and execute the Elasticsearch query.
        return List.of();
    }
}
```

Repository chính ghép fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
```

Với cấu hình mặc định, Spring Data tìm lớp `ProductSearchFragmentImpl` cho interface `ProductSearchFragment`.

Tên phải khớp theo quy ước. Các tên như `ProductSearchImplementation`, `ProductSearchService` hoặc `ProductRepositorySearchImpl` không tự động tương ứng với `ProductSearchFragment` khi postfix mặc định là `Impl`.

### 3.1. Tên fragment và tên repository không cần giống nhau

Fragment interface có thể đặt tên theo capability thay vì tên repository:

```java
public interface ProductSearchFragment { ... }
public interface ProductInventoryFragment { ... }
public interface ProductAuditFragment { ... }
```

Mỗi interface có implementation riêng:

```text
ProductSearchFragment       -> ProductSearchFragmentImpl
ProductInventoryFragment   -> ProductInventoryFragmentImpl
ProductAuditFragment       -> ProductAuditFragmentImpl
```

Một fragment có thể được tái sử dụng bởi nhiều repository nếu domain và implementation phù hợp. Khi tái sử dụng, cần xem xét generic type hoặc tách abstraction để không phụ thuộc cứng vào một entity cụ thể.

## 4. Thay đổi implementation postfix

Mặc định, Spring Data dùng hậu tố `Impl`. Có thể thay đổi bằng thuộc tính `repositoryImplementationPostfix` trên cấu hình repository.

Ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog",
        repositoryImplementationPostfix = "Custom"
)
public class ElasticsearchRepositoryConfiguration {
}
```

Với cấu hình này, fragment implementation cần theo hậu tố `Custom`:

```text
ProductSearchFragment       -> ProductSearchFragmentCustom
ProductInventoryFragment   -> ProductInventoryFragmentCustom
```

Không đổi postfix trong cấu hình mà quên đổi tên các implementation tương ứng. Nếu dự án có nhiều cấu hình repository độc lập, hãy thống nhất quy ước hoặc tách package để tránh nhầm lẫn.

Postfix là phần tên lớp được Spring Data dùng để phát hiện implementation. Nó không phải annotation và không thay thế tên fragment interface.

## 5. Mô hình cũ: implementation theo tên repository

Trước khi repository fragment composition trở thành cách mở rộng được khuyến nghị, Spring Data thường phát hiện một custom implementation dựa trên tên repository chính cộng postfix.

Ví dụ repository:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductRepositoryCustom {
}
```

Interface custom:

```java
public interface ProductRepositoryCustom {
    List<Product> searchByBusinessRule(String keyword);
}
```

Implementation kiểu cũ:

```java
public class ProductRepositoryImpl
        implements ProductRepositoryCustom {

    private final ElasticsearchOperations operations;

    public ProductRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByBusinessRule(String keyword) {
        return List.of();
    }
}
```

Tên `ProductRepositoryImpl` được suy ra từ tên repository `ProductRepository` cộng postfix `Impl`. Mô hình này gom custom behavior của repository vào một implementation có tên gắn với repository chính.

### 5.1. Vì sao không nên tiếp tục mở rộng mô hình cũ?

Khi repository có nhiều nhóm hành vi, một class `ProductRepositoryImpl` dễ trở thành nơi tập trung nhiều trách nhiệm:

- Tìm kiếm theo nghiệp vụ.
- Đồng bộ inventory.
- Ghi audit.
- Xử lý bulk.
- Truy vấn aggregation.

Lớp này ngày càng lớn, khó tái sử dụng và dễ có xung đột method. Mô hình fragment tách từng nhóm thành interface/implementation riêng, giúp repository chính chỉ thể hiện những capability mà nó cần.

Mô hình cũ vẫn có thể tồn tại trong ứng dụng đang dùng phiên bản hoặc codebase legacy. Khi viết mới, ưu tiên fragment interface có implementation riêng. Không trộn tùy tiện hai quy ước tên trong cùng một repository vì có thể làm việc phát hiện implementation khó dự đoán.

## 6. Ghép nhiều fragment vào một repository

Một repository có thể kế thừa nhiều fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment,
                ProductInventoryFragment,
                ProductAuditFragment {
}
```

Mỗi fragment có interface và implementation riêng:

```java
public interface ProductSearchFragment {
    List<Product> searchByKeyword(String keyword);
}

public interface ProductInventoryFragment {
    void updateInventory(String productId, int quantity);
}

public interface ProductAuditFragment {
    void recordSearch(String keyword);
}
```

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {
    // Search implementation.
}

public class ProductInventoryFragmentImpl
        implements ProductInventoryFragment {
    // Inventory update implementation.
}

public class ProductAuditFragmentImpl
        implements ProductAuditFragment {
    // Audit implementation.
}
```

Repository proxy kết hợp CRUD base behavior và ba fragment. Service có thể inject một repository duy nhất:

```java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> search(String keyword) {
        return repository.searchByKeyword(keyword);
    }

    public void changeStock(String id, int quantity) {
        repository.updateInventory(id, quantity);
    }
}
```

Không cần inject riêng từng fragment implementation. Các fragment được ghép vào proxy của `ProductRepository`.

## 7. Thứ tự ghép fragment và method trùng chữ ký

Thứ tự fragment trong khai báo `extends` có ý nghĩa khi nhiều fragment cung cấp method trùng chữ ký. Spring Data ghép fragment theo thứ tự composition; fragment được khai báo sau có độ ưu tiên cao hơn khi có xung đột method.

Ví dụ:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                DefaultProductSearchFragment,
                SpecializedProductSearchFragment {
}
```

Nếu cả hai fragment đều triển khai cùng một method signature, implementation của fragment đứng sau trong composition có thể được ưu tiên.

Tuy vậy, không nên thiết kế nhiều fragment cố ý ghi đè cùng một method nếu không có nhu cầu rõ ràng. Cách tốt hơn là:

- Mỗi fragment sở hữu một nhóm method riêng.
- Dùng tên method khác nhau khi semantics khác nhau.
- Nếu cần một implementation thay thế, chỉ ghép fragment có trách nhiệm đó.
- Viết integration test xác nhận implementation thực sự được gọi khi có xung đột cần thiết.

Custom fragment có thể bổ sung hoặc thay thế một số method trùng với base repository behavior. Khi làm điều này, phải hiểu thứ tự ưu tiên giữa custom implementation, fragment composition và base implementation để tránh service gọi nhầm logic.

## 8. Phạm vi quét repository với `@EnableElasticsearchRepositories`

`@EnableElasticsearchRepositories` bật việc phát hiện và tạo bean cho các repository interface Elasticsearch trong những package được chỉ định.

Ví dụ:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class ElasticsearchConfiguration {
}
```

Spring Data sẽ tìm repository interface trong package `com.example.catalog.repository` và các package con theo phạm vi scan.

Nếu repository nằm ở:

```text
com.example.catalog.repository.product.ProductRepository
com.example.catalog.repository.order.OrderRepository
```

thì `basePackages = "com.example.catalog.repository"` bao phủ cả hai package con.

### 8.1. Dùng `basePackageClasses` để tránh chuỗi package

Có thể dùng marker class:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackageClasses = {
                ProductRepository.class,
                OrderRepository.class
        }
)
public class ElasticsearchConfiguration {
}
```

`basePackageClasses` yêu cầu Spring Data lấy package của các class được chỉ định làm gốc scan. Cách này an toàn hơn khi refactor package vì compiler có thể phát hiện class không còn tồn tại, trong khi chuỗi package là literal.

Thực tế, có thể tạo một marker class không cần logic trong package repository để làm mốc:

```java
package com.example.catalog.repository;

public final class ElasticsearchRepositories {
    private ElasticsearchRepositories() {
    }
}
```

Sau đó:

```java
@EnableElasticsearchRepositories(
        basePackageClasses = ElasticsearchRepositories.class
)
```

## 9. Spring Boot auto-configuration và package gốc

Trong Spring Boot, repository scanning thường được suy ra từ package của class có `@SpringBootApplication` hoặc cấu hình auto-configuration liên quan.

Ví dụ:

```text
com.example.catalog
├── CatalogApplication.java  (@SpringBootApplication)
├── repository
│   └── ProductRepository.java
└── domain
    └── Product.java
```

Với class ứng dụng đặt ở package gốc `com.example.catalog`, các package con thường nằm trong phạm vi component/repository scanning mặc định.

Nếu đặt class ứng dụng quá sâu:

```text
com.example.catalog.application.CatalogApplication
com.example.catalog.repository.ProductRepository
```

package `com.example.catalog.repository` có thể nằm ngoài phạm vi scan mặc định suy ra từ `com.example.catalog.application`. Khi đó cần đặt application class ở package gốc phù hợp hoặc cấu hình `@EnableElasticsearchRepositories` với base package tường minh.

Không nên nhầm component scanning với repository scanning. `@ComponentScan` tìm bean như `@Service`, `@Component`, `@Configuration`; `@EnableElasticsearchRepositories` tìm repository interface để tạo repository proxy. Hai phạm vi có liên quan trong cấu hình ứng dụng nhưng không phải cùng một cơ chế.

## 10. Quét repository và quét entity là hai việc khác nhau

Một lỗi cấu hình thường gặp là nghĩ rằng đưa package vào `@EnableElasticsearchRepositories` đồng nghĩa Spring Data đã quét mọi entity trong package đó.

Hai nhiệm vụ khác nhau:

| Cơ chế | Mục đích |
|---|---|
| Repository scanning | Tìm interface repository và tạo proxy bean. |
| Mapping context/entity metadata | Xác định cách ánh xạ entity, ID, field, nested object, geo field, join field và index metadata. |
| Component scanning | Tìm `@Service`, `@Component`, `@Configuration` và các bean ứng dụng. |

Repository generic type cho Spring Data biết domain class mà repository quản lý. Entity có thể được khai báo bằng `@Document` và mapping annotations. Đặt entity ngoài package repository không tự động làm repository biến mất nếu domain type vẫn được tham chiếu và mapping context có thể xử lý entity đó.

Khi ứng dụng có nhiều package domain, hãy tổ chức rõ ràng package entity và repository, đồng thời kiểm tra mapping/index creation theo cấu hình Spring Data Elasticsearch đang dùng.

## 11. Giới hạn scan và loại trừ repository

`@EnableElasticsearchRepositories` cung cấp các tùy chọn để kiểm soát việc tìm repository, gồm base package, include/exclude filters và một số tùy chọn cấu hình repository.

Ví dụ giới hạn theo package và loại trừ một nhóm interface:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com\\.example\\.legacy\\..*"
        )
)
public class ElasticsearchConfiguration {
}
```

Ví dụ chỉ scan các repository được đánh dấu bằng annotation riêng:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example",
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ElasticsearchStoreRepository.class
        )
)
public class ElasticsearchConfiguration {
}
```

Các ví dụ filter chỉ cần dùng khi package chứa nhiều repository hoặc ứng dụng cần chia cấu hình rõ ràng. Với phần lớn dự án, base package hẹp và có cấu trúc tốt thường dễ hiểu hơn một tập filter phức tạp.

### 11.1. Repository interface lồng nhau

Các repository interface được khai báo bên trong class khác không nhất thiết được scan mặc định. Thuộc tính `considerNestedRepositories` cho phép bật việc xem xét nested repository interface:

```java
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog",
        considerNestedRepositories = true
)
```

Chỉ bật khi dự án thật sự tổ chức repository dạng nested. Repository interface top-level thường dễ phát hiện, test và tái sử dụng hơn.

## 12. Repository scan và nhiều Spring Data module

Một ứng dụng có thể đồng thời dùng Spring Data Elasticsearch, JPA, MongoDB hoặc Redis. Khi nhiều module repository cùng có mặt, Spring Data có thể chạy ở strict repository configuration mode để xác định repository thuộc store nào.

Nên dùng đúng base interface cho từng store:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}

public interface CustomerJpaRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

Entity Elasticsearch thường dùng `@Document`; entity JPA dùng `@Entity`. Tránh tạo một repository generic chỉ kế thừa `Repository<T, ID>` khi ứng dụng có nhiều store và không có metadata đủ rõ để xác định module.

Có thể tách cấu hình scan:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.search.repository"
)
class SearchRepositoryConfiguration {
}
```

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.persistence.repository"
)
class JpaRepositoryConfiguration {
}
```

Việc tách package giúp tránh tạo nhầm repository bean, giảm xung đột bean name và làm rõ module chịu trách nhiệm cho từng store.

## 13. Repository base interface dùng chung

Khi nhiều repository cần một nhóm method chung, có thể tạo base interface:

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

@NoRepositoryBean
public interface BaseSearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    // Shared repository declarations.
}
```

Repository cụ thể kế thừa:

```java
public interface ProductRepository
        extends BaseSearchRepository<Product, String>,
                ProductSearchFragment {
}
```

`@NoRepositoryBean` báo cho Spring Data không tạo repository proxy trực tiếp cho interface trung gian. Nếu bỏ annotation, Spring Data có thể cố tạo bean cho generic base interface và không có domain type cụ thể để quản lý.

Nếu muốn customize base implementation của toàn bộ repository, đó là một cơ chế khác, thường liên quan `repositoryBaseClass`. Không nên dùng fragment chỉ để thay đổi implementation CRUD chung cho mọi repository nếu mục tiêu thực sự là thay base class.

## 14. Constructor injection trong fragment implementation

Fragment implementation là một object do Spring Data/Spring container quản lý, vì vậy có thể inject dependency qua constructor.

Ví dụ:

```java
public class ProductInventoryFragmentImpl
        implements ProductInventoryFragment {

    private final ElasticsearchOperations operations;
    private final InventoryPolicy inventoryPolicy;

    public ProductInventoryFragmentImpl(
            ElasticsearchOperations operations,
            InventoryPolicy inventoryPolicy) {
        this.operations = operations;
        this.inventoryPolicy = inventoryPolicy;
    }

    @Override
    public void updateInventory(String productId, int quantity) {
        // Apply domain policy and update Elasticsearch.
    }
}
```

Constructor injection giúp dependency rõ ràng, dễ unit test và tránh field mutable. Nếu implementation cần bean riêng, bảo đảm bean đó được Spring quản lý trong application context.

Không tạo thủ công `new ProductInventoryFragmentImpl(...)` trong service rồi kỳ vọng repository proxy tự dùng object đó. Spring Data phải phát hiện hoặc nhận bean implementation theo quy ước repository composition.

## 15. Đặt tên bean khi có nhiều implementation trùng tên

Spring Data thường phát hiện implementation theo tên class và postfix. Khi có nhiều fragment interface cùng tên đơn giản ở các package khác nhau, hoặc có nhiều implementation candidate, tên bean có thể xung đột.

Ví dụ hai module đều có:

```text
com.example.catalog.ProductSearchFragment
com.example.order.ProductSearchFragment
```

và cả hai implementation đều tên `ProductSearchFragmentImpl`. Nếu cùng được đăng ký trong một application context, tên bean mặc định có thể trùng.

Có thể giải quyết bằng cách:

- Đặt tên fragment interface cụ thể hơn, ví dụ `CatalogProductSearchFragment` và `OrderProductSearchFragment`.
- Tách package/configuration scan hợp lý.
- Đăng ký implementation bean với tên rõ ràng theo quy ước mà repository infrastructure mong đợi.
- Tránh để hai fragment không liên quan có cùng simple name trong cùng vùng scan.

Nếu tự đăng ký bean implementation, hãy kiểm tra tên bean mà Spring Data dùng để liên kết với fragment. Với postfix mặc định, tên thường được suy ra từ tên fragment interface và postfix theo quy tắc bean naming. Không thêm `@Component` một cách tùy tiện nếu việc phát hiện tự động đã đăng ký cùng implementation, vì có thể tạo hai bean candidate.

## 16. Tách fragment theo capability, không theo từng method

Không nên tạo một fragment cho mỗi method nhỏ. Fragment nên đại diện cho một nhóm hành vi có cohesion rõ ràng.

Ví dụ phân tách hợp lý:

```text
ProductRepository
  ├── ProductSearchFragment
  │     ├── searchByKeyword(...)
  │     └── findSimilarProducts(...)
  ├── ProductInventoryFragment
  │     ├── reserveStock(...)
  │     └── releaseStock(...)
  └── ProductAnalyticsFragment
        ├── aggregateByCategory(...)
        └── calculatePriceDistribution(...)
```

Mỗi fragment có thể dùng API phù hợp:

- Search fragment dùng `ElasticsearchOperations.search(...)` hoặc `NativeQuery`.
- Inventory fragment dùng update/bulk API và quy tắc version/concurrency.
- Analytics fragment dùng aggregation và mapper riêng để đọc kết quả.

Nếu một nhóm hành vi không liên quan đến repository hoặc có thể tái sử dụng độc lập, có thể để nó ở service/domain service thay vì ép mọi logic vào repository fragment.

## 17. Reactive repository và fragment

Nếu dự án dùng reactive Elasticsearch, repository được khai báo theo reactive repository infrastructure. Fragment cũng cần method signature và implementation phù hợp với reactive model.

Ví dụ:

```java
public interface ReactiveProductSearchFragment {
    Flux<Product> searchAvailableProducts(String keyword);
}
```

```java
public class ReactiveProductSearchFragmentImpl
        implements ReactiveProductSearchFragment {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchFragmentImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> searchAvailableProducts(String keyword) {
        // Build a reactive query and return the resulting Flux.
        return Flux.empty();
    }
}
```

Repository reactive:

```java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchFragment {
}
```

Với reactive repository, dùng cấu hình repository reactive tương ứng như `@EnableReactiveElasticsearchRepositories` khi cần khai báo scan tường minh. Không ghép fragment imperative trả `List`/`Page` vào repository reactive rồi mong proxy tự biến đổi thành `Flux`/`Mono`.

## 18. Những lỗi thường gặp khi scan và ghép fragment

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không inject được repository bean | Repository interface nằm ngoài package scan. | Đặt application class ở package gốc phù hợp hoặc cấu hình `basePackages`/`basePackageClasses`. |
| Repository được tạo nhưng custom method không được nhận diện | Implementation class không theo tên fragment + postfix. | Đổi thành `<FragmentInterface>Impl` hoặc postfix đã cấu hình. |
| Fragment implementation không được phát hiện | Package/implementation naming không phù hợp với repository scanning convention. | Đặt implementation gần fragment interface và kiểm tra cấu hình postfix/scan. |
| Đổi postfix nhưng application báo thiếu implementation | `repositoryImplementationPostfix` không khớp tên class thực tế. | Đồng bộ cấu hình và tên tất cả fragment implementation liên quan. |
| Một implementation cũ không còn được ghép | Code dùng tên `RepositoryImpl` trong khi đã chuyển sang fragment composition. | Tạo fragment interface riêng và implementation theo tên fragment. |
| Spring tạo bean cho generic base repository | Base interface thiếu `@NoRepositoryBean`. | Thêm annotation vào interface trung gian. |
| Repository của store khác bị tạo nhầm | Nhiều Spring Data module scan cùng package hoặc repository generic không rõ store. | Tách package và cấu hình `@Enable...Repositories` theo store. |
| Có hai bean implementation cùng tên | Fragment ở package khác nhau có cùng simple name. | Đặt tên fragment cụ thể hoặc tách cấu hình/bean name. |
| Method custom gọi implementation không mong muốn | Nhiều fragment có method trùng chữ ký và composition order không rõ. | Tránh xung đột hoặc xác định rõ thứ tự fragment. |
| Constructor implementation không được inject | Dependency chưa là bean hoặc implementation được tạo thủ công. | Để Spring quản lý implementation và đăng ký dependency. |
| Nested repository không được scan | `considerNestedRepositories` đang tắt. | Bật tùy chọn hoặc chuyển interface thành top-level. |
| Repository scan đúng nhưng mapping entity sai | Nhầm repository scan với entity mapping metadata. | Kiểm tra `@Document`, mapping context và index mapping riêng. |
| Reactive fragment không tương thích | Dùng imperative API hoặc return type trong reactive repository. | Dùng `ReactiveElasticsearchOperations` và `Mono`/`Flux`. |

## 19. Checklist cấu hình repository tùy biến

Trước khi chạy ứng dụng, có thể kiểm tra các điểm sau:

1. Repository interface nằm trong package được scan.
2. Cấu hình imperative/reactive tương ứng với loại repository.
3. Fragment interface được repository chính kế thừa.
4. Implementation có tên đúng theo fragment interface và postfix.
5. Nếu đổi postfix, mọi implementation liên quan đã đổi tên đồng bộ.
6. Fragment implementation nằm trong phạm vi phát hiện phù hợp và dependency constructor đều là bean hợp lệ.
7. Generic base repository có `@NoRepositoryBean`.
8. Không có nhiều repository cùng bị scan bởi cấu hình ngoài ý muốn.
9. Method trùng chữ ký giữa fragment được tránh hoặc có thứ tự composition chủ đích.
10. Không trộn custom fragment mới với legacy `RepositoryImpl` một cách mơ hồ.
11. Repository của từng Spring Data store được phân tách rõ.
12. Mapping entity được kiểm tra độc lập với repository scanning.

## 20. Quy trình xây dựng custom repository fragment

Một quy trình đơn giản:

1. **Xác định capability:** chọn nhóm hành vi cần mở rộng, ví dụ tìm kiếm theo nghiệp vụ.
2. **Tạo fragment interface:** khai báo các method thuộc nhóm hành vi đó.
3. **Tạo implementation:** đặt tên `<FragmentInterface>Impl` theo postfix hiện tại.
4. **Inject dependency:** dùng constructor để nhận `ElasticsearchOperations`, service hoặc policy cần thiết.
5. **Ghép vào repository:** thêm fragment interface vào `extends` của repository chính.
6. **Kiểm tra package scan:** bảo đảm repository được phát hiện và implementation nằm trong vùng phát hiện tương ứng.
7. **Kiểm tra bean:** xác nhận Spring tạo một repository proxy và các dependency được inject.
8. **Kiểm tra xung đột:** rà soát method signature trùng giữa fragments/base behavior.
9. **Kiểm thử:** gọi custom method qua repository proxy, không gọi trực tiếp implementation.
10. **Theo dõi cấu hình:** nếu nhiều store hoặc nhiều nhóm repository, tách scan configuration và package rõ ràng.

## 21. Những điểm cần nhớ

- Repository Spring Data là interface được Spring Data tạo proxy; custom fragment được ghép vào proxy đó.
- Mô hình fragment hiện đại dùng một interface và một implementation cho mỗi nhóm hành vi.
- Tên implementation mặc định là tên fragment interface cộng `Impl`, ví dụ `ProductSearchFragmentImpl`.
- `repositoryImplementationPostfix` cho phép thay đổi postfix mặc định.
- Mô hình legacy dùng tên `<RepositoryInterface>Impl`; nên ưu tiên fragment riêng khi viết mới.
- Repository có thể ghép nhiều fragment bằng cách kế thừa nhiều fragment interface.
- Thứ tự fragment trong composition có ý nghĩa khi nhiều fragment cung cấp method trùng chữ ký; nên tránh xung đột không cần thiết.
- `@EnableElasticsearchRepositories` điều khiển phạm vi scan repository; `basePackageClasses` giúp tránh package string.
- Package gốc của `@SpringBootApplication` ảnh hưởng phạm vi auto-scan mặc định.
- Component scan, repository scan và entity mapping là ba cơ chế khác nhau.
- `considerNestedRepositories` điều khiển việc phát hiện nested repository interface.
- Dùng `@NoRepositoryBean` cho generic base repository không được tạo proxy trực tiếp.
- Khi nhiều Spring Data store cùng tồn tại, tách package và cấu hình scan theo store.
- Fragment implementation có thể dùng constructor injection; không tự tạo implementation bằng `new` trong service.
- Reactive repository cần fragment/reactive operations trả `Mono` hoặc `Flux` tương thích.

Quy ước tên và phạm vi scan quyết định Spring Data có thể tìm thấy đúng repository fragment hay không; composition quyết định các hành vi đó được ghép thành một proxy như thế nào. Tổ chức fragment theo capability, dùng tên implementation nhất quán và giới hạn package scan rõ ràng giúp repository tùy biến dễ mở rộng, tái sử dụng và ít lỗi khởi động hơn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Repository configuration](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/definition.html)
- [Spring Data Commons — Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data Commons — Repository composition](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html#repositories.custom-implementations.fragments)
- [Spring Data Elasticsearch — `@EnableElasticsearchRepositories` API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/repository/config/EnableElasticsearchRepositories.html)
