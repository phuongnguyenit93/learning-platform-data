# Tiêm ElasticsearchOperations hoặc ReactiveElasticsearchOperations

Khi một repository method cần query phức tạp, nhiều bước xử lý hoặc thao tác không phù hợp với query method có sẵn, Spring Data Elasticsearch cho phép bổ sung custom repository implementation. Trong implementation này, ứng dụng có thể inject `ElasticsearchOperations` hoặc `ReactiveElasticsearchOperations` để làm việc trực tiếp với Elasticsearch thông qua abstraction của Spring Data.

`ElasticsearchOperations` là API imperative: method thường trả kết quả ngay như `SearchHits<T>`, entity hoặc response object. `ReactiveElasticsearchOperations` là API reactive: method trả publisher như `Mono<T>` hoặc `Flux<SearchHit<T>>`. Hai interface phục vụ hai kiểu lập trình khác nhau và không thể thay thế cho nhau chỉ bằng cách đổi tên biến.

Bài học này hướng dẫn cách tạo repository fragment, tiêm operations bằng constructor injection, viết query tùy biến, chọn đúng bean khi ứng dụng có nhiều Elasticsearch template, tổ chức reactive implementation và xử lý các lỗi wiring thường gặp.

## 1. Vì sao custom repository cần ElasticsearchOperations?

Spring Data repository đã cung cấp CRUD và query method dựa trên tên phương thức. Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

Với query đơn giản, cách này thường đủ. Nhưng một số yêu cầu cần nhiều quyền kiểm soát hơn:

- Ghép nhiều điều kiện động tùy tham số request.
- Dùng Query DSL cụ thể mà query derivation không biểu diễn rõ.
- Kết hợp search, aggregation, highlight hoặc metadata của hit.
- Thực hiện nhiều thao tác Elasticsearch trong một phương thức nghiệp vụ.
- Dùng API của `ElasticsearchOperations` hoặc `ReactiveElasticsearchOperations` mà repository interface không expose trực tiếp.
- Tái sử dụng logic tìm kiếm cho nhiều repository.

Thay vì đưa toàn bộ logic vào service hoặc tạo một client riêng, có thể viết custom repository fragment và inject operations vào implementation.

~~~text
ProductRepository
       |
       +---- ElasticsearchRepository<Product, String>
       |            CRUD và query methods
       |
       +---- ProductSearchRepository
                    custom search contract
                          |
                          v
              ProductSearchRepositoryImpl
                          |
                          v
               ElasticsearchOperations
                          |
                          v
                    Elasticsearch
~~~

Spring Data ghép các fragment thành một repository proxy. Client chỉ inject `ProductRepository` và gọi cả method CRUD lẫn method custom.

## 2. Phân biệt hai operations interface

Spring Data Elasticsearch cung cấp hai abstraction:

| Interface | Kiểu lập trình | Kết quả tìm kiếm thường gặp |
|---|---|---|
| `ElasticsearchOperations` | Imperative, blocking | `SearchHits<T>` |
| `ReactiveElasticsearchOperations` | Reactive, non-blocking | `Flux<SearchHit<T>>` hoặc `Mono<ReactiveSearchHits<T>>` |

Hai interface có các nhóm chức năng tương ứng như document operations, search, query, aggregation và index management, nhưng chữ ký method và cách tiêu thụ kết quả khác nhau.

### 2.1. ElasticsearchOperations

`ElasticsearchOperations` là interface tổng hợp cho các thao tác imperative. Nó cung cấp các API như:

- `save(...)`, `get(...)`, `delete(...)`.
- `search(...)`, `searchOne(...)`, `searchForStream(...)`.
- `count(...)`, `exists(...)`.
- `indexOps(...)` để thao tác metadata/index.
- `update(...)`, bulk operations và các thao tác query khác.

Ví dụ:

~~~java
SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

Lời gọi trả về sau khi thao tác đồng bộ hoàn tất. Nếu gọi từ WebFlux event-loop, API này có thể block thread; không dùng nó trực tiếp trong reactive request path.

### 2.2. ReactiveElasticsearchOperations

`ReactiveElasticsearchOperations` cung cấp các thao tác reactive. Ví dụ:

~~~java
Flux<SearchHit<Product>> hits = reactiveOperations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

Publisher chỉ mô tả thao tác cho tới khi có subscription. Khi downstream subscribe, request mới được thực thi và các `SearchHit<Product>` được phát lần lượt.

Một số method trả metadata tìm kiếm đầy đủ:

~~~java
Mono<ReactiveSearchHits<Product>> result =
        reactiveOperations.searchForHits(
                query,
                Product.class,
                IndexCoordinates.of("products"));
~~~

`ReactiveSearchHits<T>` chứa metadata search và cung cấp publisher các hit qua `getSearchHits()`.

### 2.3. Không tiêm nhầm operations

Không thể gán `ReactiveElasticsearchOperations` cho biến `ElasticsearchOperations` hoặc ngược lại. Chúng là hai abstraction riêng.

Một custom fragment imperative nên inject `ElasticsearchOperations`. Một custom fragment reactive nên inject `ReactiveElasticsearchOperations`. Nếu ứng dụng có cả hai stack, nên đặt implementation trong package hoặc module phù hợp và để kiểu constructor thể hiện rõ nhu cầu.

## 3. Repository fragment là gì?

Spring Data xây repository từ nhiều fragment. Một fragment gồm:

1. Interface khai báo chức năng custom.
2. Class implementation thực thi interface đó.

Repository chính kế thừa interface fragment. Spring Data ghép fragment vào repository proxy khi khởi tạo repository.

Ví dụ interface:

~~~java
package com.example.catalog.repository;

public interface ProductSearchRepository {

    List<Product> searchByText(String text);
}
~~~

Implementation:

~~~java
package com.example.catalog.repository;

public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    // Implementation is added in the next sections.
}
~~~

Tên class implementation mặc định là tên fragment interface cộng hậu tố `Impl`: `ProductSearchRepository` → `ProductSearchRepositoryImpl`.

Repository chính:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
~~~

Khi Spring tạo `ProductRepository`, proxy có cả method CRUD từ `ElasticsearchRepository` và `searchByText` từ fragment.

## 4. Tiêm ElasticsearchOperations bằng constructor injection

Custom fragment implementation là một bean do repository infrastructure phát hiện và đăng ký. Nó có thể dùng dependency injection thông thường của Spring. Cách nên dùng là constructor injection:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    // Custom methods use operations here.
}
~~~

Spring tìm bean phù hợp kiểu `ElasticsearchOperations`, truyền vào constructor khi tạo fragment implementation. Field được khai báo `final`, nên dependency luôn có mặt sau khi object được khởi tạo.

Constructor injection có các lợi ích:

- Thể hiện dependency bắt buộc ngay trong chữ ký constructor.
- Dễ viết unit test bằng mock hoặc fake operations.
- Hỗ trợ object bất biến sau khi khởi tạo.
- Tránh trạng thái object đã tạo nhưng field `@Autowired` chưa được gán.
- Dễ phát hiện lỗi thiếu bean hoặc nhiều bean không phân biệt được ngay lúc khởi động.

Với một constructor duy nhất, Spring không cần annotation `@Autowired` trên constructor.

### 4.1. Không cần tự tạo ElasticsearchOperations trong fragment

Không tạo client hoặc template mới bên trong implementation:

~~~java
// Avoid creating a new client/template for every repository fragment.
public ProductSearchRepositoryImpl() {
    // new ElasticsearchClient(...)
    // new ElasticsearchTemplate(...)
}
~~~

Hãy inject operations do Spring configuration quản lý. Template dùng chung cấu hình connection, converter, mapping context, callbacks và các thành phần tích hợp khác của ứng dụng.

### 4.2. Không inject repository vào chính fragment của nó

Tránh tạo vòng phụ thuộc như:

~~~java
public ProductSearchRepositoryImpl(ProductRepository repository) {
    // ProductRepository itself includes this fragment.
}
~~~

`ProductRepository` được tạo bằng cách ghép `ProductSearchRepositoryImpl`. Nếu implementation lại yêu cầu chính `ProductRepository`, Spring có thể gặp circular dependency hoặc không tạo được proxy.

Fragment nên phụ thuộc vào `ElasticsearchOperations`, `ReactiveElasticsearchOperations` hoặc service khác không phụ thuộc ngược vào repository proxy đó.

## 5. Viết custom search bằng ElasticsearchOperations

Ví dụ tìm sản phẩm theo tên bằng `CriteriaQuery`:

~~~java
package com.example.catalog.repository;

import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

import com.example.catalog.domain.Product;

public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByText(String text) {
        Criteria criteria = Criteria.where("name").contains(text);
        CriteriaQuery query = new CriteriaQuery(criteria);

        SearchHits<Product> hits = operations.search(
                query,
                Product.class,
                IndexCoordinates.of("products"));

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
~~~

Trong ví dụ:

- `Criteria` biểu diễn điều kiện tìm kiếm.
- `CriteriaQuery` đóng gói query cho Spring Data.
- `Product.class` cung cấp domain type để mapping.
- `IndexCoordinates.of("products")` chỉ rõ index đích.
- `SearchHits<Product>` giữ metadata của toàn bộ search response.
- `SearchHit::getContent` lấy entity từ từng hit.

Nếu cần score, highlight hoặc sort values, có thể trả `SearchHits<Product>` hoặc DTO được ánh xạ từ từng `SearchHit` thay vì chỉ trả `List<Product>`.

### 5.1. Dùng NativeQuery khi cần Query DSL cụ thể

Khi query có nhiều điều kiện Elasticsearch-specific, có thể dùng `NativeQuery`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(match -> match
                                        .field("name")
                                        .query(text)))
                        .filter(f -> f
                                .term(term -> term
                                        .field("active")
                                        .value(true)))))
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

`NativeQuery` cho phép xây query bằng Elasticsearch Java API Client builder. `ElasticsearchOperations` vẫn đảm nhiệm việc thực thi và ánh xạ kết quả sang domain type.

Dùng CriteriaQuery khi điều kiện đơn giản và dễ biểu diễn bằng Criteria API. Dùng NativeQuery khi cần các thành phần Query DSL cụ thể hoặc API của client.

### 5.2. Giữ metadata của SearchHit

Nếu method custom cần trả cả entity và score:

~~~java
public interface ProductSearchRepository {
    SearchHits<Product> searchWithMetadata(String text);
}
~~~

Implementation:

~~~java
@Override
public SearchHits<Product> searchWithMetadata(String text) {
    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("name").contains(text));

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

Tầng service có thể đọc `hits.getTotalHits()`, `hits.getMaxScore()` và `hit.getScore()` hoặc highlight fields nếu query đã bật highlight.

## 6. Dùng fragment trong service và controller

Service chỉ cần inject repository tổng hợp:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> search(String text) {
        return repository.searchByText(text);
    }
}
~~~

Controller không cần biết custom fragment sử dụng operations nào:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/search")
    public List<Product> search(@RequestParam String q) {
        return service.search(q);
    }
}
~~~

Luồng phụ thuộc:

~~~text
Controller
    |
    v
ProductService
    |
    v
ProductRepository proxy
    |
    +---- ElasticsearchRepository base implementation
    |
    +---- ProductSearchRepositoryImpl
                  |
                  v
          ElasticsearchOperations
                  |
                  v
             Elasticsearch
~~~

Service và controller phụ thuộc vào repository contract. Chỉ custom implementation phụ thuộc trực tiếp vào operations.

## 7. Tiêm ReactiveElasticsearchOperations

Với ứng dụng reactive, định nghĩa fragment trả publisher:

~~~java
package com.example.catalog.repository;

import reactor.core.publisher.Flux;

import com.example.catalog.domain.Product;

public interface ReactiveProductSearchRepository {

    Flux<Product> searchByText(String text);
}
~~~

Repository chính:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;

public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchRepository {
}
~~~

Implementation inject `ReactiveElasticsearchOperations`:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

import reactor.core.publisher.Flux;

import com.example.catalog.domain.Product;

public class ReactiveProductSearchRepositoryImpl
        implements ReactiveProductSearchRepository {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchRepositoryImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> searchByText(String text) {
        CriteriaQuery query = new CriteriaQuery(
                Criteria.where("name").contains(text));

        return operations.search(
                        query,
                        Product.class,
                        IndexCoordinates.of("products"))
                .map(SearchHit::getContent);
    }
}
~~~

`ReactiveElasticsearchOperations.search(...)` trả `Flux<SearchHit<Product>>`. Method custom map mỗi hit thành entity nhưng vẫn giữ publisher reactive.

Không gọi `.block()` hoặc `.subscribe()` bên trong fragment. Hãy trả `Flux<Product>` về repository caller để WebFlux hoặc tầng ngoài điều khiển subscription và cancellation.

### 7.1. Trả metadata với ReactiveSearchHits

Nếu cần total hits hoặc metadata search, định nghĩa fragment trả `Mono<ReactiveSearchHits<Product>>`:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveSearchHits;

public interface ReactiveProductSearchRepository {
    Mono<ReactiveSearchHits<Product>> searchWithMetadata(String text);
}
~~~

Implementation:

~~~java
@Override
public Mono<ReactiveSearchHits<Product>> searchWithMetadata(String text) {
    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("name").contains(text));

    return operations.searchForHits(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

Caller có thể lấy publisher hit:

~~~java
return repository.searchWithMetadata(text)
        .flatMapMany(ReactiveSearchHits::getSearchHits)
        .map(SearchHit::getContent);
~~~

`search(...)` phù hợp khi chỉ cần stream hit. `searchForHits(...)` phù hợp khi cần object metadata tổng thể của search response.

## 8. Constructor injection và nhiều operations bean

Trong ứng dụng đơn giản, Spring thường có một bean `ElasticsearchOperations` và một bean `ReactiveElasticsearchOperations`. Constructor injection theo type có thể tự tìm bean phù hợp.

Khi ứng dụng có nhiều cluster, nhiều index template hoặc nhiều operations bean cùng kiểu, cần chỉ định rõ bean bằng `@Qualifier`.

Ví dụ:

~~~java
public ProductSearchRepositoryImpl(
        @Qualifier("catalogElasticsearchOperations")
        ElasticsearchOperations operations) {
    this.operations = operations;
}
~~~

Với reactive:

~~~java
public ReactiveProductSearchRepositoryImpl(
        @Qualifier("catalogReactiveElasticsearchOperations")
        ReactiveElasticsearchOperations operations) {
    this.operations = operations;
}
~~~

Tên qualifier phải khớp với tên bean đã khai báo trong Spring context. Không đặt qualifier theo tên index; bean name và index name là hai khái niệm khác nhau.

### 8.1. Khai báo nhiều imperative operations bean

Ví dụ cấu hình hai cluster/template:

~~~java
@Configuration
public class ElasticsearchOperationsConfiguration {

    @Bean("catalogElasticsearchOperations")
    ElasticsearchOperations catalogOperations(
            ElasticsearchClient catalogClient,
            ElasticsearchConverter converter) {
        return new ElasticsearchTemplate(catalogClient, converter);
    }

    @Bean("auditElasticsearchOperations")
    ElasticsearchOperations auditOperations(
            ElasticsearchClient auditClient,
            ElasticsearchConverter converter) {
        return new ElasticsearchTemplate(auditClient, converter);
    }
}
~~~

Đây là ví dụ cấu trúc; constructor và cách tạo client cụ thể phụ thuộc cấu hình Spring Data Elasticsearch/client version của ứng dụng. Trong hệ thống thực tế, mỗi template cần gắn đúng client, converter và mapping context của cluster tương ứng.

Custom fragment:

~~~java
public ProductSearchRepositoryImpl(
        @Qualifier("catalogElasticsearchOperations")
        ElasticsearchOperations operations) {
    this.operations = operations;
}
~~~

### 8.2. Primary bean

Nếu một operations bean nên là mặc định cho các dependency không có qualifier, có thể đánh dấu `@Primary`:

~~~java
@Bean
@Primary
ElasticsearchOperations defaultElasticsearchOperations(...) {
    // Create the default template.
}
~~~

`@Primary` giải quyết lựa chọn mặc định theo type. Khi fragment cần một cluster cụ thể, vẫn nên dùng `@Qualifier` để thể hiện rõ ý định.

### 8.3. Bean name mặc định và repository infrastructure

Spring Data repository infrastructure cần operations/template bean tương ứng để tạo repository proxy:

| Repository infrastructure | Operations bean mặc định |
|---|---|
| `@EnableElasticsearchRepositories` | `elasticsearchTemplate` |
| `@EnableReactiveElasticsearchRepositories` | `reactiveElasticsearchTemplate` |

Nếu dùng nhiều repository configuration hoặc nhiều cluster, cấu hình từng registrar để repository sử dụng đúng template. Việc tiêm operations trực tiếp vào custom fragment và việc repository proxy chọn template nền là hai điểm wiring riêng cần thống nhất.

## 9. Cấu hình repository cho nhiều cluster

Khi có nhiều Elasticsearch cluster, có thể chia package repository:

~~~text
com.example.catalog
    catalog
        repository
            ProductRepository
            ProductSearchRepository
            ProductSearchRepositoryImpl
        config
            CatalogElasticsearchConfig
    audit
        repository
            AuditRepository
        config
            AuditElasticsearchConfig
~~~

Mỗi cấu hình bật repository scanning cho package tương ứng và tham chiếu template đúng:

~~~java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.catalog.repository",
        elasticsearchTemplateRef = "catalogElasticsearchTemplate")
public class CatalogRepositoryConfig {
}
~~~

~~~java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.audit.repository",
        elasticsearchTemplateRef = "auditElasticsearchTemplate")
public class AuditRepositoryConfig {
}
~~~

Tên thuộc tính template reference được dùng trong cấu hình repository imperative. Với reactive repositories, dùng `@EnableReactiveElasticsearchRepositories` và `reactiveElasticsearchTemplateRef`.

Custom fragment trong package catalog cần inject đúng `catalogElasticsearchOperations` hoặc bean tương ứng. Không để fragment dùng cluster audit chỉ vì bean đó được đánh dấu Primary.

## 10. Discovery và naming của custom fragment

Repository infrastructure tìm fragment implementation trong phạm vi package repository được scan. Theo mặc định, implementation có hậu tố `Impl`.

Ví dụ:

~~~text
ProductSearchRepository
ProductSearchRepositoryImpl
ProductRepository
~~~

Các interface và implementation nên nằm trong cùng package hoặc vị trí mà repository scanning có thể phát hiện theo quy tắc của Spring Data.

### 10.1. Tùy chỉnh postfix

Có thể đổi hậu tố trong repository configuration:

~~~java
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository",
        repositoryImplementationPostfix = "Custom")
~~~

Với postfix `Custom`, Spring tìm `ProductSearchRepositoryCustom` thay cho `ProductSearchRepositoryImpl`.

Reactive repository configuration cũng có thuộc tính postfix tương ứng. Nếu đổi postfix, bảo đảm tất cả fragment implementation tuân thủ cùng naming convention được cấu hình.

### 10.2. Không nhầm fragment implementation với tên repository + Impl kiểu cũ

Trước đây Spring Data thường tìm một class theo tên repository chính cộng `Impl`, ví dụ `ProductRepositoryImpl`. Cách single-custom-implementation này đã bị deprecated trong tài liệu Spring Data hiện hành; nên dùng fragment interface riêng và implementation có tên theo fragment.

Mô hình được khuyến nghị:

~~~text
ProductRepository
    extends ElasticsearchRepository
    extends ProductSearchRepository

ProductSearchRepositoryImpl
    implements ProductSearchRepository
    injects ElasticsearchOperations
~~~

Mô hình fragment giúp chia custom behavior thành các phần độc lập, có thể tái sử dụng và kết hợp nhiều fragment trong một repository.

### 10.3. Có cần gắn @Component hoặc @Repository?

Fragment implementation được repository infrastructure phát hiện và đăng ký theo quy ước. Trong trường hợp thông thường, không cần thêm `@Component` chỉ để fragment được tìm thấy.

Nếu tự khai báo bean thủ công vì cần wiring đặc biệt, tên bean phải khớp quy ước fragment interface cộng postfix để infrastructure liên kết đúng implementation. Tránh vừa khai báo bean thủ công vừa để component scan tạo thêm một bean cùng class với tên khác.

## 11. Tái sử dụng fragment cho nhiều repository

Một fragment interface có thể được nhiều repository kế thừa:

~~~java
public interface TextSearchFragment<T> {
    SearchHits<T> searchText(String text, Class<T> type, String indexName);
}
~~~

Implementation generic:

~~~java
public class TextSearchFragmentImpl<T>
        implements TextSearchFragment<T> {

    private final ElasticsearchOperations operations;

    public TextSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<T> searchText(
            String text,
            Class<T> type,
            String indexName) {

        CriteriaQuery query = new CriteriaQuery(
                Criteria.where("name").contains(text));

        return operations.search(
                query,
                type,
                IndexCoordinates.of(indexName));
    }
}
~~~

Hai repository có thể cùng kế thừa fragment:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                TextSearchFragment<Product> {
}

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String>,
                TextSearchFragment<Article> {
}
~~~

Trong code thực tế, generic fragment cần được đặt tên và tổ chức sao cho Spring Data có thể xác định implementation phù hợp. Nếu fragment generic được đóng góp từ module/thư viện bên ngoài hoặc nằm ngoài repository base package, có thể cần đăng ký fragment thông qua cơ chế fragment registration như `spring.factories` theo tài liệu Spring Data.

Nếu index name có thể lấy từ metadata entity hoặc `@Document`, tránh nhận index name tùy ý từ request bên ngoài. Chỉ cho phép các index đã được ứng dụng cấu hình.

## 12. Custom fragment với nhiều dependency

Implementation có thể inject nhiều bean, không chỉ ElasticsearchOperations:

~~~java
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;
    private final ProductSearchPolicy policy;
    private final Clock clock;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations,
            ProductSearchPolicy policy,
            Clock clock) {
        this.operations = operations;
        this.policy = policy;
        this.clock = clock;
    }
}
~~~

Ví dụ:

- `ElasticsearchOperations` thực thi query.
- `ProductSearchPolicy` áp dụng quy tắc lọc hoặc giới hạn kết quả.
- `Clock` cung cấp thời gian hiện tại để test dễ kiểm soát.

Fragment vẫn là một Spring bean thông thường nên có thể tham gia dependency injection, AOP và các cơ chế bean khác. Hãy giữ dependency rõ ràng và tránh để fragment trở thành nơi chứa toàn bộ logic nghiệp vụ của ứng dụng.

## 13. Kiểm thử custom repository imperative

Có thể unit test fragment bằng cách mock `ElasticsearchOperations`:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchRepositoryImplTest {

    @Mock
    ElasticsearchOperations operations;

    @Test
    void executesSearchAndReturnsContents() {
        Product product = new Product(
                "p-100",
                "Wireless Keyboard",
                "accessories");

        // Stub operations.search(...) with a SearchHits<Product> fixture.
        when(operations.search(
                any(Query.class),
                eq(Product.class),
                any(IndexCoordinates.class)))
                .thenReturn(searchHitsContaining(product));

        ProductSearchRepositoryImpl fragment =
                new ProductSearchRepositoryImpl(operations);

        List<Product> result = fragment.searchByText("keyboard");

        assertThat(result).containsExactly(product);
        verify(operations).search(
                any(Query.class),
                eq(Product.class),
                any(IndexCoordinates.class));
    }
}
~~~

Đoạn test minh họa cách mock contract và xác nhận fragment gọi operations. Helper `searchHitsContaining` là fixture do test tạo để tránh phụ thuộc constructor chi tiết của `SearchHit`/`SearchHitsImpl` trong từng release train.

Unit test không xác nhận mapping hoặc Query DSL được Elasticsearch chấp nhận. Cần integration test để kiểm tra query thực tế.

## 14. Kiểm thử reactive fragment

Reactive operations nên được mock trả publisher:

~~~java
@ExtendWith(MockitoExtension.class)
class ReactiveProductSearchRepositoryImplTest {

    @Mock
    ReactiveElasticsearchOperations operations;

    @Test
    void mapsReactiveSearchHitsToProducts() {
        Product product = new Product(
                "p-100",
                "Wireless Keyboard",
                "accessories");

        SearchHit<Product> hit = createSearchHit(product);

        when(operations.search(
                any(Query.class),
                eq(Product.class),
                any(IndexCoordinates.class)))
                .thenReturn(Flux.just(hit));

        ReactiveProductSearchRepositoryImpl fragment =
                new ReactiveProductSearchRepositoryImpl(operations);

        StepVerifier.create(fragment.searchByText("keyboard"))
                .expectNext(product)
                .verifyComplete();
    }
}
~~~

`StepVerifier` kiểm tra publisher mà không cần gọi `block()`. Trong integration test, khởi tạo reactive Elasticsearch client thật để xác nhận query và mapping.

## 15. Kiểm thử repository composition và dependency injection

Unit test implementation chỉ xác nhận constructor nhận operations. Để kiểm tra Spring Data có phát hiện fragment và ghép nó vào repository proxy hay không, cần khởi động ApplicationContext.

Một integration test có thể:

1. Bật `@EnableElasticsearchRepositories` cho package test.
2. Cung cấp `ElasticsearchOperations` bean.
3. Khởi tạo `ProductRepository`.
4. Autowire repository proxy.
5. Gọi custom method `searchByText`.
6. Xác nhận implementation fragment được gọi và kết quả được ánh xạ.

Với reactive:

1. Bật `@EnableReactiveElasticsearchRepositories`.
2. Cung cấp `ReactiveElasticsearchOperations`.
3. Khởi tạo `ReactiveProductRepository`.
4. Gọi custom method và verify bằng StepVerifier.

Test này phát hiện các lỗi như fragment implementation nằm ngoài package scan, sai tên postfix, thiếu operations bean hoặc qualifier trỏ sai.

## 16. Các lỗi thường gặp khi tiêm operations

### Không tìm thấy bean ElasticsearchOperations

Nguyên nhân có thể là client/template chưa được cấu hình, dependency thiếu hoặc ứng dụng tắt auto-configuration. Kiểm tra Spring context có bean kiểu `ElasticsearchOperations` hay chưa.

### Có nhiều bean ElasticsearchOperations

Spring không biết chọn bean nào nếu có nhiều candidate và không có `@Primary` hoặc `@Qualifier`. Gắn qualifier rõ ràng vào constructor fragment.

### Inject reactive operations vào imperative fragment

Hai interface khác nhau. Dùng đúng loại theo repository và kiểu trả về của fragment.

### Custom implementation không được phát hiện

Kiểm tra fragment interface có được repository chính kế thừa, class implementation có đúng tên postfix và nằm trong phạm vi scan hay không.

### Dùng tên ProductRepositoryImpl theo quy ước cũ

Ưu tiên `ProductSearchRepository` + `ProductSearchRepositoryImpl`. Fragment model tách contract custom khỏi repository chính và được khuyến nghị trong tài liệu hiện hành.

### Gắn @Component rồi tạo bean trùng

Fragment infrastructure đã quản lý implementation theo naming convention. Nếu tự khai báo component/bean, bảo đảm tên bean và cách đăng ký không tạo hai instance cạnh tranh.

### Vòng phụ thuộc giữa fragment và repository proxy

Không inject repository proxy vào chính fragment tạo nên proxy đó. Tiêm operations hoặc một dependency cấp thấp hơn.

### Repository dùng template khác với fragment

Trong ứng dụng nhiều cluster, repository proxy và custom fragment có thể vô tình trỏ tới hai operations bean khác nhau. Cấu hình template reference và `@Qualifier` đồng nhất.

### Gọi block trong reactive fragment

`ReactiveElasticsearchOperations` trả publisher. Không block hoặc subscribe bên trong fragment; trả publisher cho caller.

### Dùng ElasticsearchOperations trong WebFlux request path

Operations imperative có thể block. Nếu cần xử lý non-blocking, dùng reactive repository/operations xuyên suốt.

### Tự tạo template trong constructor

Việc tạo client/template thủ công làm phân tán cấu hình và khó quản lý connection. Inject bean đã được Spring quản lý.

## 17. Khi nào dùng repository fragment, khi nào dùng operations trong service?

Không phải mọi query tùy biến đều cần custom repository.

| Tình huống | Cách tổ chức phù hợp |
|---|---|
| Query cố định theo method name | Derived repository method |
| Query DSL khai báo tĩnh | `@Query` |
| Query động chỉ dùng trong một use case | Service inject operations |
| Query động gắn với trách nhiệm truy cập Product | ProductSearchRepository fragment |
| Custom behavior dùng lại ở nhiều repository | Reusable fragment |
| Thay đổi cách hoạt động của mọi repository | Custom repository base class, khi thật sự cần |
| Cần điều khiển sâu việc tạo repository proxy | Repository factory customization |

Fragment phù hợp khi custom behavior là một phần của contract repository và cần được tái sử dụng/kiểm thử riêng. Nếu query chỉ phục vụ một bước orchestration trong service, inject operations trực tiếp vào service có thể đơn giản hơn.

Không tạo fragment chỉ để chuyển tiếp một dòng gọi `operations.search(...)` nếu nó không bổ sung abstraction hoặc tái sử dụng nào.

## 18. Phân biệt custom fragment với custom base repository

Custom fragment thêm một nhóm method cho repository cụ thể:

~~~java
public interface ProductSearchRepository {
    List<Product> searchByText(String text);
}
~~~

Custom base repository thay đổi hành vi nền cho tất cả repository trong phạm vi cấu hình. Nó thường kế thừa lớp implementation repository của store và được đăng ký bằng `repositoryBaseClass`.

Không dùng custom base repository chỉ để inject `ElasticsearchOperations` vào một query. Fragment thường có ít coupling và dễ ghép hơn.

Nếu cần thay đổi logic chung cho tất cả repository, phải kiểm tra constructor mà repository factory yêu cầu và cung cấp đúng constructor/store infrastructure. Đây là kỹ thuật nâng cao hơn fragment injection.

## 19. Quy trình triển khai

Khi thêm custom repository cần dùng Elasticsearch operations:

1. Xác định query có thực sự cần custom implementation hay có thể dùng derived query hoặc `@Query`.
2. Chọn imperative hay reactive theo stack của ứng dụng.
3. Tạo fragment interface khai báo method custom.
4. Cho repository chính kế thừa fragment interface.
5. Tạo class implementation theo tên fragment cộng hậu tố `Impl`.
6. Inject `ElasticsearchOperations` hoặc `ReactiveElasticsearchOperations` qua constructor.
7. Dùng `IndexCoordinates` và query object để chỉ rõ index và điều kiện.
8. Giữ nguyên kiểu kết quả imperative hoặc reactive phù hợp.
9. Nếu có nhiều operations bean, dùng `@Qualifier` và cấu hình repository template reference đúng cluster.
10. Đặt fragment trong phạm vi repository scan hoặc đăng ký theo cơ chế fragment phù hợp.
11. Unit test implementation bằng mock operations.
12. Integration test repository composition, bean injection, mapping và query thực tế.
13. Tránh block/subscribe trong reactive path và tránh gọi imperative operations trên event-loop.

## 20. Tổng kết

Custom repository implementation của Spring Data Elasticsearch có thể inject `ElasticsearchOperations` hoặc `ReactiveElasticsearchOperations` như một Spring bean thông thường. Mô hình nên dùng là repository fragment: khai báo interface custom, cho repository chính kế thừa interface đó, rồi cung cấp class implementation có tên fragment cộng hậu tố `Impl`. Spring Data phát hiện và ghép fragment vào repository proxy.

Với imperative stack, inject `ElasticsearchOperations`; method search trả `SearchHits<T>` và thao tác chạy đồng bộ. Với reactive stack, inject `ReactiveElasticsearchOperations`; method search trả `Flux<SearchHit<T>>` hoặc `Mono<ReactiveSearchHits<T>>`. Không trộn hai abstraction hoặc gọi block/subscribe trong reactive fragment.

Constructor injection giúp dependency bắt buộc rõ ràng, dễ test và phát hiện wiring error khi khởi động. Nếu có nhiều operations bean, dùng `@Qualifier` và bảo đảm repository infrastructure cũng tham chiếu đúng template. Fragment implementation cần nằm trong phạm vi scan và tuân theo naming convention. Chọn fragment khi custom behavior thuộc contract truy cập dữ liệu; nếu query chỉ dùng một lần trong service, inject operations trực tiếp vào service có thể gọn hơn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html)
- [Spring Data Elasticsearch – ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch – ReactiveElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveElasticsearchOperations.html)
- [Spring Data Elasticsearch – SearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchOperations.html)
- [Spring Data Elasticsearch – ReactiveSearchOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveSearchOperations.html)
- [Spring Data Elasticsearch – Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
