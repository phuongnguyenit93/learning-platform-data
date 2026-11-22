# ReactiveElasticsearchRepository và quét Repository

Spring Data Elasticsearch hỗ trợ repository theo mô hình reactive dựa trên Project Reactor. Thay vì trả về một entity hoặc collection thông thường, reactive repository trả về các publisher như Mono và Flux. Các publisher này mô tả một luồng thao tác bất đồng bộ; thao tác chỉ được thực thi khi có subscriber đăng ký.

ReactiveElasticsearchRepository là repository chuyên biệt cho Elasticsearch. Interface này kế thừa ReactiveCrudRepository và ReactiveSortingRepository, vì vậy có các thao tác CRUD, tìm kiếm theo điều kiện, sắp xếp và các query method được tạo từ tên phương thức. Spring tạo implementation proxy cho repository interface thông qua cơ chế repository scanning. Annotation EnableReactiveElasticsearchRepositories cho phép chỉ định package cần quét, template reactive sẽ được sử dụng và các bộ lọc repository.

Bài học này trình bày cách khai báo entity và ReactiveElasticsearchRepository, cách dùng Mono/Flux trong CRUD và query method, cách cấu hình Reactive Elasticsearch client, cách Spring tìm repository interface và đăng ký bean, cách phân tách reactive với imperative repositories, cùng những lỗi thường gặp khi triển khai.

## 1. Reactive repository là gì?

Repository là abstraction giúp ứng dụng truy cập dữ liệu thông qua interface. Với Spring Data Elasticsearch, repository interface mô tả các thao tác cần thiết; Spring Data tạo implementation dựa trên Elasticsearch operations.

Có hai hướng chính:

| Repository | Kiểu trả về phổ biến | Operations sử dụng |
|---|---|---|
| ElasticsearchRepository | Entity, List, Iterable, Page | ElasticsearchOperations |
| ReactiveElasticsearchRepository | Mono, Flux | ReactiveElasticsearchOperations |

Reactive repository sử dụng Project Reactor làm thư viện composition. ReactiveElasticsearchOperations thực hiện các thao tác thông qua ReactiveElasticsearchClient.

Luồng tổng quát:

~~~text
WebFlux Controller / Reactive Service
                 |
                 v
     ReactiveElasticsearchRepository
                 |
                 v
     Repository proxy do Spring tạo
                 |
                 v
     ReactiveElasticsearchOperations
                 |
                 v
       ReactiveElasticsearchClient
                 |
                 v
             Elasticsearch
~~~

Reactive không chỉ là đổi kiểu trả về từ List sang Flux. Toàn bộ luồng cần giữ tính non-blocking: từ HTTP handler, service, repository đến client. Nếu gọi block() hoặc dùng một API đồng bộ trong luồng xử lý request, ứng dụng có thể làm nghẽn event-loop và mất lợi ích reactive.

## 2. Mono và Flux

Project Reactor cung cấp hai kiểu publisher thường dùng:

| Kiểu | Số phần tử | Ví dụ |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Tìm một sản phẩm theo ID |
| Flux<T> | 0 đến nhiều | Tìm tất cả sản phẩm trong một category |

Mono có thể hoàn tất mà không phát phần tử nào, ví dụ khi document không tồn tại. Flux có thể phát nhiều phần tử theo thời gian rồi hoàn tất.

Ví dụ:

~~~java
Mono<Product> product = repository.findById("p-100");

Flux<Product> products = repository.findByCategory("accessories");
~~~

Hai biến trên chỉ giữ publisher. Khi khai báo publisher, chưa có nghĩa request Elasticsearch đã được gửi. Việc thực thi xảy ra khi có subscriber.

### 2.1. Các toán tử thường dùng

| Toán tử | Mục đích |
|---|---|
| map | Chuyển đổi mỗi giá trị đồng bộ |
| flatMap | Chuyển mỗi giá trị thành publisher khác và hợp nhất kết quả |
| concatMap | Chuyển đổi tuần tự, giữ thứ tự xử lý |
| filter | Chỉ giữ phần tử thỏa điều kiện |
| switchIfEmpty | Chọn publisher thay thế nếu nguồn rỗng |
| defaultIfEmpty | Phát giá trị mặc định nếu nguồn rỗng |
| then | Chờ publisher hoàn tất rồi chạy bước tiếp theo |
| onErrorResume | Chuyển lỗi thành một publisher thay thế |
| onErrorMap | Chuyển loại exception |
| doOnNext | Quan sát phần tử để logging/metrics |

Ví dụ kết hợp hai thao tác:

~~~java
public Mono<Product> findAndRename(String id, String newName) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)))
            .map(product -> {
                product.setName(newName);
                return product;
            })
            .flatMap(repository::save);
}
~~~

Repository được gọi trong cùng một chuỗi reactive. Không cần tự subscribe bên trong service.

## 3. Khai báo entity Elasticsearch

Entity có thể dùng annotation Document và Id như repository thông thường:

~~~java
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

    @Field(type = FieldType.Long)
    private Long price;

    public Product() {
    }

    public Product(String id, String name, String category, Long price) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public Long getPrice() {
        return price;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Với Elasticsearch, ID được biểu diễn dưới dạng chuỗi. Tài liệu Spring Data Elasticsearch hướng dẫn property ID của entity có kiểu String. Vì vậy, dùng String cho ID là lựa chọn phổ biến và rõ ràng.

Annotation Document mô tả index đích và metadata mapping. Repository scanning không tự tạo index ngay khi quét package; việc tạo index phụ thuộc mapping metadata, cấu hình createIndex và quá trình khởi tạo của ứng dụng.

## 4. Khai báo ReactiveElasticsearchRepository

Repository chỉ cần là interface kế thừa ReactiveElasticsearchRepository:

~~~java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;

import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {
}
~~~

Hai generic type:

- Product: domain type được lưu trong Elasticsearch.
- String: kiểu ID của entity.

Spring Data tạo proxy cho interface này khi repository scanning được bật. Ứng dụng có thể inject ProductRepository vào service hoặc controller.

ReactiveElasticsearchRepository kế thừa:

- ReactiveCrudRepository: CRUD reactive.
- ReactiveSortingRepository: truy cập và sắp xếp kết quả.

Do đó không cần tự khai báo lại các method save, findById, findAll hoặc deleteById.

## 5. Các thao tác CRUD reactive

Một số method kế thừa phổ biến:

| Method | Kiểu trả về | Ý nghĩa |
|---|---|---|
| save(entity) | Mono<S> | Lưu một entity |
| saveAll(Iterable<S>) | Flux<S> | Lưu nhiều entity từ Iterable |
| saveAll(Publisher<S>) | Flux<S> | Lưu từ một publisher |
| findById(id) | Mono<T> | Tìm một document theo ID |
| findAll() | Flux<T> | Tìm nhiều document |
| existsById(id) | Mono<Boolean> | Kiểm tra ID có tồn tại |
| count() | Mono<Long> | Đếm document |
| deleteById(id) | Mono<Void> | Xóa theo ID |
| delete(entity) | Mono<Void> | Xóa entity |
| deleteAll() | Mono<Void> | Xóa tất cả theo repository operation |

Ví dụ lưu và đọc:

~~~java
Mono<Product> saveProduct(Product product) {
    return repository.save(product);
}

Mono<Product> findProduct(String id) {
    return repository.findById(id);
}
~~~

Xóa document:

~~~java
Mono<Void> deleteProduct(String id) {
    return repository.deleteById(id);
}
~~~

Mono<Void> biểu thị thao tác chỉ cần báo hoàn tất hoặc lỗi, không phát entity kết quả.

### 5.1. saveAll với Publisher

Reactive repository có overload nhận Publisher:

~~~java
Flux<Product> saveProducts(Flux<Product> products) {
    return repository.saveAll(products);
}
~~~

Điều này cho phép nối một nguồn reactive trực tiếp vào repository mà không cần chuyển toàn bộ dữ liệu thành List trước.

Nếu nguồn dữ liệu là Iterable:

~~~java
Flux<Product> saveProducts(List<Product> products) {
    return repository.saveAll(Flux.fromIterable(products));
}
~~~

Với luồng lớn, tránh gọi collectList() chỉ để chuyển Flux thành List nếu không cần giữ toàn bộ dữ liệu trong bộ nhớ.

## 6. Derived query methods

Spring Data tạo query dựa trên tên method. Reactive repository dùng cùng quy tắc đặt tên query method như các repository Spring Data khác, nhưng kiểu trả về là Mono hoặc Flux.

~~~java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Flux<Product> findByCategoryAndPriceLessThan(
            String category,
            Long maxPrice);

    Mono<Product> findFirstByCategoryOrderByPriceAsc(String category);

    Flux<Product> findByNameContaining(String text);

    Mono<Long> countByCategory(String category);

    Mono<Boolean> existsByName(String name);

    Mono<Long> deleteByCategory(String category);
}
~~~

Ý nghĩa:

- findByCategory trả về các document có category tương ứng.
- findByCategoryAndPriceLessThan kết hợp hai điều kiện.
- findFirstByCategoryOrderByPriceAsc tìm một document đầu tiên theo giá tăng dần.
- findByNameContaining tạo truy vấn theo semantics của keyword được hỗ trợ cho field.
- countByCategory trả số document thỏa điều kiện.
- existsByName kiểm tra có ít nhất một document phù hợp.
- deleteByCategory xóa các document phù hợp và trả số lượng theo kiểu reactive.

Tên method phải tuân thủ property name của domain model và các keyword mà Spring Data Elasticsearch hỗ trợ. Không phải mọi keyword của Spring Data JPA đều có cùng semantics hoặc được hỗ trợ trong Elasticsearch.

### 6.1. Kết hợp And và Or

Ví dụ:

~~~java
Flux<Product> findByCategoryAndPriceLessThan(
        String category,
        Long maxPrice);

Flux<Product> findByCategoryOrName(
        String category,
        String name);
~~~

Spring Data phân tích tên method để xây query. Khi logic tìm kiếm phức tạp hoặc cần kiểm soát Query DSL chính xác, dùng @Query hoặc ReactiveElasticsearchOperations.

### 6.2. Sort và Pageable

Reactive query method có thể nhận Sort hoặc Pageable:

~~~java
Flux<Product> findByCategory(String category, Sort sort);

Flux<Product> findByCategory(String category, Pageable pageable);
~~~

Ví dụ gọi:

~~~java
Pageable firstPage = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "price"));

Flux<Product> products = repository.findByCategory(
        "accessories",
        firstPage);
~~~

Reactive method vẫn trả Flux. Pageable truyền thông tin offset, size và sort; nó không biến kết quả thành Page<T> đồng bộ.

Nếu API cần cả danh sách hiện tại và tổng số phần tử, có thể kết hợp query kết quả với count query:

~~~java
Mono<ProductPageResponse> findPage(String category, Pageable pageable) {
    Flux<Product> items = repository.findByCategory(category, pageable);
    Mono<Long> total = repository.countByCategory(category);

    return Mono.zip(items.collectList(), total)
            .map(tuple -> new ProductPageResponse(
                    tuple.getT1(),
                    tuple.getT2(),
                    pageable.getPageNumber(),
                    pageable.getPageSize()));
}
~~~

Hai query là hai thao tác độc lập; nếu dữ liệu thay đổi giữa lúc chạy, total và items có thể phản ánh hai thời điểm hơi khác nhau. Với phân trang sâu, cân nhắc search_after hoặc cursor phù hợp thay vì offset lớn.

## 7. Dùng @Query trong reactive repository

Khi derived query method không đủ diễn đạt, annotation Query cho phép viết Query DSL:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0"
            }
          }
        }
        """)
    Flux<Product> searchByName(String text);
}
~~~

Placeholder ?0 tham chiếu tham số đầu tiên của method. Với method có nhiều tham số, có thể dùng ?1, ?2 theo vị trí tương ứng.

Một ví dụ query kết hợp filter:

~~~java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": "?0"
            }
          }
        ],
        "filter": [
          {
            "term": {
              "category": "?1"
            }
          }
        ]
      }
    }
    """)
Flux<Product> search(String text, String category);
~~~

Query DSL vẫn được Elasticsearch thực thi. Reactive chỉ ảnh hưởng cách request và kết quả được composition trong ứng dụng, không thay đổi semantics của query.

## 8. Publisher làm tham số query

Reactive repository có thể nhận Publisher cho tham số finder method:

~~~java
Flux<Product> findByCategory(Publisher<String> category);
~~~

Điều này hữu ích khi giá trị tìm kiếm đến từ một nguồn reactive khác. Ví dụ:

~~~java
Mono<String> category = resolveCategoryFromRequest();

Flux<Product> products = repository.findByCategory(category);
~~~

Không phải method nào cũng cần nhận Publisher. Với một giá trị đơn giản đã có sẵn, tham số String thông thường dễ đọc hơn. Dùng Publisher khi cần composition reactive giữa nguồn tham số và query.

## 9. Reactive repository chỉ thực thi khi có subscription

Một trong những điểm quan trọng nhất của Reactor là publisher thường lazy. Ví dụ:

~~~java
Mono<Product> result = repository.save(product);
~~~

Dòng code này tạo publisher, nhưng nếu không có subscriber thì thao tác save có thể không được thực hiện.

Trong Spring WebFlux, controller có thể trả publisher trực tiếp:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductRepository repository;

    public ProductController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Mono<Product> findById(@PathVariable String id) {
        return repository.findById(id);
    }

    @GetMapping
    public Flux<Product> findAll() {
        return repository.findAll();
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Product product) {
        return repository.save(product);
    }
}
~~~

WebFlux framework subscribe publisher trong quá trình xử lý request và ghi kết quả ra HTTP response. Controller không cần gọi subscribe().

### 9.1. Không tự subscribe trong service

Tránh viết:

~~~java
public void create(Product product) {
    repository.save(product).subscribe();
}
~~~

Service tự subscribe làm tách rời vòng đời thao tác khỏi request/caller. Caller không nhận được kết quả hoặc lỗi theo cùng một chuỗi reactive; việc kiểm soát cancellation, tracing và transaction context cũng trở nên khó hơn.

Ưu tiên trả publisher:

~~~java
public Mono<Product> create(Product product) {
    return repository.save(product);
}
~~~

### 9.2. Chỉ block tại ranh giới imperative

block() chờ publisher hoàn tất và biến kết quả thành lời gọi đồng bộ. Không dùng block() trong WebFlux controller, reactive service hoặc event-loop thread.

Trong một command-line job hoặc test imperative, có thể dùng block() ở ranh giới ngoài cùng khi thật sự cần chờ:

~~~java
repository.save(product).block();
~~~

Đây là cách chặn luồng gọi. Nó không còn là xử lý non-blocking trong đoạn code đó.

## 10. Xây dựng service reactive

Service có thể kết hợp nhiều repository operation:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> rename(String id, String newName) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)))
                .map(product -> {
                    product.setName(newName);
                    return product;
                })
                .flatMap(repository::save);
    }

    public Flux<Product> findAffordable(String category, long maxPrice) {
        return repository.findByCategoryAndPriceLessThan(
                category,
                maxPrice);
    }
}
~~~

flatMap phù hợp khi bước tiếp theo trả publisher. map phù hợp khi chỉ biến đổi giá trị trong bộ nhớ. Không bọc repository call trong Mono.just(repository.save(...)) vì khi đó kiểu dữ liệu sẽ trở thành Mono<Mono<Product>> và thao tác không được flatten đúng.

## 11. Xử lý lỗi trong reactive chain

Lỗi trong Reactor được truyền dưới dạng error signal. Có thể chuyển hoặc xử lý lỗi bằng các toán tử:

~~~java
public Mono<Product> findRequired(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)))
            .onErrorMap(
                    DataAccessException.class,
                    ProductStorageException::new);
}
~~~

Nếu muốn fallback khi một loại lỗi xảy ra:

~~~java
public Mono<Product> findOrFallback(String id) {
    return repository.findById(id)
            .onErrorResume(
                    DataAccessResourceFailureException.class,
                    error -> loadFallbackProduct(id));
}
~~~

Không nên bắt mọi Throwable rồi trả Mono.empty() vì điều đó có thể biến lỗi kết nối, lỗi mapping hoặc lỗi quyền truy cập thành trường hợp “không tìm thấy dữ liệu”, khiến nguyên nhân thật bị che giấu.

Nếu cần trả HTTP status tương ứng, có thể xử lý exception ở controller advice hoặc chuyển lỗi nghiệp vụ thành response ở tầng web.

## 12. Backpressure và luồng dữ liệu lớn

Flux hỗ trợ backpressure: downstream có thể điều tiết tốc độ yêu cầu phần tử từ upstream. Điều này giúp xây dựng pipeline xử lý dữ liệu lớn mà không phải gom mọi thứ vào bộ nhớ.

Ví dụ lưu tuần tự:

~~~java
Flux<Product> importProducts(Flux<Product> input) {
    return input.concatMap(repository::save);
}
~~~

concatMap xử lý từng phần tử theo thứ tự. Nếu cho phép nhiều thao tác đồng thời:

~~~java
Flux<Product> importProducts(Flux<Product> input) {
    return input.flatMap(repository::save, 8);
}
~~~

Tham số concurrency giới hạn số publisher con được subscribe đồng thời. Giá trị phù hợp phụ thuộc throughput, giới hạn cluster và kích thước document.

Không nên mặc định dùng flatMap không giới hạn trên một nguồn lớn. Quá nhiều request đồng thời có thể làm tăng tải Elasticsearch và tạo queue trong ứng dụng.

### 12.1. Tránh collectList cho tập dữ liệu lớn

collectList() gom toàn bộ phần tử thành một List trước khi phát kết quả:

~~~java
Mono<List<Product>> allProducts = repository.findAll().collectList();
~~~

Điều này có thể phù hợp với tập dữ liệu nhỏ, nhưng tốn bộ nhớ khi index có hàng triệu document. Nếu cần xử lý theo luồng, tiếp tục dùng Flux và các toán tử như buffer, window, concatMap hoặc flatMap với concurrency giới hạn.

### 12.2. Reactive không có nghĩa mọi downstream đều tự backpressure

Khi nối thêm broker, HTTP service hoặc API bên ngoài, cần kiểm tra publisher đó có thực sự hỗ trợ backpressure hay có buffer không giới hạn. Dùng limitRate, giới hạn concurrency và bounded buffer khi phù hợp. Theo dõi memory, queue và độ trễ của pipeline.

## 13. Reactive Elasticsearch client và operations

Reactive repository được thực thi thông qua ReactiveElasticsearchOperations. Có thể inject abstraction này khi cần query động hoặc thao tác không phù hợp với repository method:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;

@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

ReactiveElasticsearchOperations là reactive counterpart của ElasticsearchOperations. Nó cung cấp các thao tác document, search và index ở dạng Mono/Flux. Reactive repository sử dụng operations này ở bên dưới.

ReactiveElasticsearchClient là client reactive do Spring Data Elasticsearch cung cấp, dựa trên Elasticsearch Java client transport. Khi làm việc ở tầng ứng dụng, ưu tiên ReactiveElasticsearchOperations hoặc repository; chỉ gọi client trực tiếp khi cần API cấp thấp mà abstraction chưa biểu diễn.

## 14. Cấu hình client reactive bằng Java configuration

Với Spring Data Elasticsearch hiện hành, có thể kế thừa ReactiveElasticsearchConfiguration để cấu hình client:

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
public class ReactiveEsClientConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

ReactiveElasticsearchConfiguration tạo các bean cần thiết, trong đó có ReactiveElasticsearchClient và ReactiveElasticsearchOperations. Operations bean cũng được đăng ký dưới tên reactiveElasticsearchTemplate để repository infrastructure sử dụng theo mặc định.

Trong môi trường thực tế, cấu hình thêm TLS, authentication, connection settings và timeout theo yêu cầu cluster. Không hard-code credential trong source code.

### 14.1. ReactiveElasticsearchConfiguration và cấu hình legacy

Spring Data Elasticsearch 6.x sử dụng ReactiveElasticsearchConfiguration với reactive client dựa trên Rest5Client transport. Cấu hình ReactiveElasticsearchLegacyRestClientConfiguration dùng legacy RestClient đã deprecated từ phiên bản 6.0 và được khuyến nghị chuyển sang ReactiveElasticsearchConfiguration.

Ví dụ cấu hình cũ từ các phiên bản trước có thể dùng class khác hoặc factory method khác. Khi nâng cấp, kiểm tra version Spring Data Elasticsearch và Elasticsearch client tương thích thay vì sao chép cấu hình từ một release train khác.

## 15. Bật repository scanning

Spring Data cần biết package nào chứa repository interface để tạo bean proxy. Với reactive Elasticsearch, dùng annotation:

~~~java
@EnableReactiveElasticsearchRepositories
~~~

Annotation này kích hoạt reactive Elasticsearch repository infrastructure. Nếu không chỉ định package, Spring quét package của class cấu hình được gắn annotation và các package con.

Ví dụ:

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;

@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository")
public class ReactiveRepositoryConfiguration {
}
~~~

Spring tìm các repository interface trong package được cấu hình, tạo factory/proxy tương ứng và đăng ký bean trong ApplicationContext. Ứng dụng sau đó inject interface như một Spring bean thông thường.

### 15.1. Repository scanning khác ComponentScan

Hai cơ chế này có mục đích khác nhau:

| Cơ chế | Tìm loại class nào | Kết quả |
|---|---|---|
| ComponentScan | @Component, @Service, @Controller, @Configuration và stereotype liên quan | Bean từ class được đánh dấu |
| EnableReactiveElasticsearchRepositories | Repository interface thuộc Spring Data reactive Elasticsearch | Repository proxy bean |
| Mapping context | Domain type và metadata mapping | Thông tin chuyển đổi entity/index |

Repository interface không cần gắn @Component. Annotation EnableReactiveElasticsearchRepositories kích hoạt registrar chuyên biệt để tìm repository và tạo proxy.

Repository scanning cũng không có nghĩa mọi entity trong package đều được tạo thành Spring bean. Domain object được quản lý bởi mapping context khi repository hoặc operations làm việc với kiểu đó.

## 16. Chọn package cần quét

EnableReactiveElasticsearchRepositories có các thuộc tính:

| Thuộc tính | Mục đích |
|---|---|
| value | Alias của basePackages |
| basePackages | Tên package cần quét |
| basePackageClasses | Cách chỉ định package an toàn theo kiểu bằng class marker |
| includeFilters | Chọn thêm repository theo filter |
| excludeFilters | Loại repository theo filter |
| considerNestedRepositories | Có quét nested repository interface hay không |
| reactiveElasticsearchTemplateRef | Tên ReactiveElasticsearchOperations bean sử dụng |
| repositoryImplementationPostfix | Hậu tố của custom repository implementation |
| queryLookupStrategy | Chiến lược tìm query method |
| namedQueriesLocation | Vị trí file named query |

### 16.1. basePackages

Chỉ định package bằng String:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackages = {
                "com.example.catalog.repository",
                "com.example.inventory.repository"
        })
~~~

Spring quét các package đã khai báo và các package con.

### 16.2. basePackageClasses

Có thể dùng một class marker nằm trong package repository:

~~~java
package com.example.catalog.repository;

public interface CatalogRepositoryMarker {
}
~~~

Sau đó:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackageClasses = CatalogRepositoryMarker.class)
~~~

basePackageClasses là lựa chọn an toàn hơn so với String package vì refactor package có thể được IDE/compiler hỗ trợ tốt hơn. Marker chỉ dùng để chỉ ra package; nó không phải repository.

### 16.3. Package mặc định của class cấu hình

Nếu không chỉ định value, basePackages hoặc basePackageClasses, Spring quét package chứa class cấu hình và các package con.

Ví dụ:

~~~text
com.example.catalog
    Application.java
    config
        ReactiveRepositoryConfiguration.java
    repository
        ProductRepository.java
~~~

Nếu annotation nằm trên ReactiveRepositoryConfiguration trong package com.example.catalog.config, package mặc định là com.example.catalog.config. Nó không tự quét package sibling com.example.catalog.repository.

Đây là nguyên nhân phổ biến khiến ứng dụng báo không tìm thấy bean ProductRepository. Hãy chỉ định basePackages hoặc basePackageClasses nếu repository nằm ngoài package con của class cấu hình.

## 17. Các thuộc tính scanning quan trọng

### 17.1. reactiveElasticsearchTemplateRef

Mặc định, reactive repository infrastructure sử dụng bean có tên reactiveElasticsearchTemplate. Nếu ứng dụng có nhiều ReactiveElasticsearchOperations bean hoặc bean tùy chỉnh tên khác, chỉ định rõ:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.repository",
        reactiveElasticsearchTemplateRef = "catalogReactiveOperations")
~~~

Bean được tham chiếu phải là ReactiveElasticsearchOperations tương thích. Không trỏ reactive repository tới ElasticsearchOperations imperative.

### 17.2. considerNestedRepositories

Mặc định false. Nếu repository interface được khai báo lồng bên trong class khác, nó không được phát hiện trừ khi bật:

~~~java
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog",
        considerNestedRepositories = true)
~~~

Thông thường nên đặt repository interface thành top-level type để dễ tìm, test và quản lý package. Chỉ bật tùy chọn này nếu dự án thực sự cần nested repository interface.

### 17.3. repositoryImplementationPostfix

Nếu repository có custom implementation fragment, hậu tố mặc định được dùng để tìm class triển khai là Impl.

Ví dụ repository ProductRepository có thể ghép với class ProductRepositoryImpl theo quy ước custom implementation tương ứng. Có thể đổi hậu tố nếu dự án dùng naming convention riêng.

### 17.4. queryLookupStrategy

Chiến lược mặc định là CREATE_IF_NOT_FOUND:

- CREATE: tạo query từ tên method.
- USE_DECLARED_QUERY: yêu cầu query được khai báo sẵn.
- CREATE_IF_NOT_FOUND: ưu tiên query khai báo; nếu không có thì tạo từ method name.

Chọn chiến lược theo quy ước của dự án. Nếu phần lớn query dùng derived method, mặc định thường phù hợp.

### 17.5. namedQueriesLocation

Cho phép chỉ định file chứa named query properties. Mặc định là META-INF/elasticsearch-named-queries.properties. Dùng khi dự án quản lý query được đặt tên ngoài annotation hoặc method declaration.

## 18. Spring Boot auto-configuration

Trong ứng dụng Spring Boot, auto-configuration có thể tạo client, template và repository infrastructure khi các dependency cần thiết có trên classpath.

Dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Spring Boot quản lý version tương thích thông qua dependency management của Boot. Không tự ghép version Spring Data Elasticsearch, Elasticsearch Java client và Spring Boot tùy ý.

Khi Reactor có trên classpath, Spring Boot hỗ trợ reactive client và ReactiveElasticsearchTemplate bên cạnh các thành phần imperative phù hợp. Repository scanning mặc định dựa trên auto-configuration packages, thường bắt đầu từ package của class SpringBootApplication.

Ví dụ:

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Nếu application class nằm trong package gốc com.example.catalog, các package repository con thường được phát hiện theo cấu hình auto-configuration. Khi cấu trúc package đặc biệt hoặc cần giới hạn scan, dùng EnableReactiveElasticsearchRepositories tường minh.

Có thể tắt repository auto-configuration bằng property:

~~~properties
spring.data.elasticsearch.repositories.enabled=false
~~~

Chỉ tắt khi ứng dụng tự quản lý repository configuration hoặc không muốn Spring Boot đăng ký repository beans.

## 19. Kết hợp reactive và imperative repositories

Một ứng dụng có thể có cả repository imperative và reactive, nhưng nên phân chia package rõ ràng:

~~~text
com.example.catalog
    imperative
        repository
            LegacyProductRepository
    reactive
        repository
            ProductRepository
    config
        ImperativeRepositoryConfig
        ReactiveRepositoryConfig
~~~

Ví dụ cấu hình:

~~~java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.imperative.repository")
class ImperativeRepositoryConfig {
}
~~~

~~~java
@Configuration
@EnableReactiveElasticsearchRepositories(
        basePackages = "com.example.catalog.reactive.repository")
class ReactiveRepositoryConfig {
}
~~~

Hai nhóm repository có thể cùng truy cập một Elasticsearch cluster, nhưng mỗi nhóm dùng operations/template phù hợp với kiểu lập trình của nó.

Không để hai registrar quét cùng package repository một cách tùy tiện. Khi có nhiều Spring Data modules, hãy dùng package rõ ràng và store-specific repository base interface để tránh repository được gắn nhầm store hoặc tạo bean trùng.

Không gọi imperative repository trong reactive request path rồi bọc kết quả bằng Mono.just. Lời gọi imperative đã block trước khi Mono được tạo:

~~~java
Mono<Product> wrong = Mono.just(blockingRepository.findById("p-100").orElseThrow());
~~~

Nếu bắt buộc tích hợp một API blocking, cần đưa nó ra khỏi event-loop bằng scheduler phù hợp và giới hạn concurrency. Tốt hơn là dùng reactive API xuyên suốt khi hệ thống đã chọn reactive stack.

## 20. Dùng ReactiveElasticsearchOperations cho query động

Repository method phù hợp với query cố định hoặc có thể suy ra từ tên method. Khi query được xây dựng từ nhiều điều kiện tùy request, dùng ReactiveElasticsearchOperations.

Ví dụ khung service:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

public class DynamicProductSearch {

    private final ReactiveElasticsearchOperations operations;

    public DynamicProductSearch(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Flux<Product> findByCategory(String category) {
        CriteriaQuery query = new CriteriaQuery(
                Criteria.where("category").is(category));

        return operations.search(
                        query,
                        Product.class,
                        IndexCoordinates.of("products"))
                .map(SearchHit::getContent);
    }
}
~~~

ReactiveElasticsearchOperations trả publisher cho search result. Ứng dụng có thể map SearchHit thành entity hoặc giữ metadata hit nếu cần score, highlight, sort values hay aggregations.

## 21. Custom repository implementation

Nếu repository cần một query đặc thù nhưng không muốn đưa logic vào service, có thể dùng custom repository fragment. Phần implementation có thể inject ReactiveElasticsearchOperations và trả Mono/Flux.

Interface fragment:

~~~java
public interface ProductSearchRepository {
    Flux<Product> searchByText(String text);
}
~~~

Repository chính:

~~~java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
~~~

Implementation:

~~~java
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(
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

Tên implementation phải khớp quy ước repository fragment và postfix được cấu hình. Nếu dùng custom repository implementation, bảo đảm class nằm trong vùng package mà repository infrastructure có thể phát hiện.

## 22. Kiểm thử reactive repository

Với Reactor, StepVerifier giúp kiểm tra publisher mà không cần block:

~~~java
import reactor.test.StepVerifier;

@Test
void findsProductById() {
    Mono<Product> result = repository.findById("p-100");

    StepVerifier.create(result)
            .expectNextMatches(product ->
                    product.getId().equals("p-100"))
            .verifyComplete();
}
~~~

Kiểm thử Flux:

~~~java
@Test
void findsProductsByCategory() {
    Flux<Product> result = repository.findByCategory("accessories");

    StepVerifier.create(result)
            .expectNextCount(2)
            .verifyComplete();
}
~~~

Test lưu entity:

~~~java
@Test
void savesProduct() {
    Product product = new Product(
            "p-100",
            "Wireless Keyboard",
            "accessories",
            1299000L);

    StepVerifier.create(repository.save(product))
            .expectNextMatches(saved ->
                    saved.getId().equals("p-100"))
            .verifyComplete();
}
~~~

Các ví dụ giả định index và Elasticsearch test instance đã được khởi tạo. Integration test nên dùng Elasticsearch tương thích với Spring Data version đang chạy, chẳng hạn container trong môi trường test, và phải quản lý index/cleanup rõ ràng.

### 22.1. Kiểm thử repository scanning

Nếu repository không được inject:

- Khởi tạo Spring ApplicationContext trong test.
- Xác nhận bean ProductRepository tồn tại.
- Kiểm tra package nằm trong basePackages/basePackageClasses.
- Kiểm tra bean ReactiveElasticsearchOperations được tạo.
- Kiểm tra reactiveElasticsearchTemplateRef trỏ đúng bean.

Không chỉ mock ProductRepository trong unit test service nếu mục tiêu là xác nhận repository scanning; mock không khởi động repository infrastructure.

## 23. Các lỗi thường gặp

### Không tìm thấy bean ReactiveElasticsearchRepository

Nguyên nhân thường là chưa bật repository scanning, package scan không bao phủ repository interface hoặc cấu hình chỉ bật EnableElasticsearchRepositories imperative.

Kiểm tra EnableReactiveElasticsearchRepositories và basePackages/basePackageClasses.

### Đặt configuration class ở package con và quên package sibling

Nếu package không được chỉ định, Spring chỉ quét package của class cấu hình và các package con. Repository ở sibling package sẽ không được phát hiện.

### Reactive repository được gắn với imperative template

Reactive repository cần ReactiveElasticsearchOperations. Nếu có nhiều template, cấu hình reactiveElasticsearchTemplateRef đúng bean.

### Gọi subscribe trong service

Tự subscribe làm tách rời kết quả và lỗi khỏi caller. Trả Mono/Flux để framework hoặc tầng ngoài subscribe.

### Gọi block trong WebFlux

block chặn thread và có thể gây lỗi khi chạy trên Reactor non-blocking thread. Giữ reactive chain hoặc đưa blocking integration ra scheduler riêng ở ranh giới thích hợp.

### Dùng List hoặc Page cho reactive finder

Reactive query method thường trả Flux hoặc Mono. Pageable có thể là tham số, nhưng kết quả vẫn là Flux; nếu cần total count, compose một count query riêng.

### Dùng collectList cho dữ liệu lớn

collectList gom toàn bộ phần tử vào heap. Tiếp tục xử lý bằng Flux và giới hạn concurrency/buffer.

### Nghĩ Flux tự động bảo đảm tốc độ phù hợp

Backpressure chỉ hữu ích khi toàn bộ publisher chain và các integration hỗ trợ nó đúng cách. Kiểm soát concurrency, buffer và queue ở các điểm nối hệ thống.

### Dùng legacy reactive client configuration

Cấu hình legacy RestClient đã deprecated từ Spring Data Elasticsearch 6.0. Với stack hiện hành, dùng ReactiveElasticsearchConfiguration và client transport tương ứng.

### Dùng sai ID type

Elasticsearch document ID là chuỗi. Dùng String làm ID property giúp mapping và repository generic nhất quán.

### Quét cùng package bằng cả hai registrar

Imperative và reactive repository infrastructure có mục tiêu khác nhau. Tách package và chỉ định rõ base package cho từng registrar để tránh đăng ký trùng hoặc gắn nhầm operations.

## 24. Quy trình thiết lập ReactiveElasticsearchRepository

Khi thêm reactive repository vào ứng dụng:

1. Chọn reactive stack cho request path và bảo đảm Reactor có trên classpath.
2. Thêm dependency Spring Data Elasticsearch tương thích với Spring Boot release train.
3. Khai báo entity với Document, Id và mapping field phù hợp.
4. Tạo repository interface kế thừa ReactiveElasticsearchRepository<Entity, String>.
5. Chọn Spring Boot auto-configuration hoặc cấu hình client bằng ReactiveElasticsearchConfiguration.
6. Bật EnableReactiveElasticsearchRepositories nếu cần scan tường minh.
7. Chỉ định basePackages hoặc basePackageClasses phù hợp với package repository.
8. Xác nhận ReactiveElasticsearchOperations bean tồn tại và repository dùng đúng template.
9. Viết finder method trả Mono/Flux và dùng @Query khi cần Query DSL tùy chỉnh.
10. Inject repository vào reactive service/controller và trả publisher trực tiếp.
11. Không gọi subscribe hoặc block trong luồng WebFlux.
12. Giới hạn concurrency và tránh gom dữ liệu lớn vào List.
13. Dùng StepVerifier và integration test để xác nhận query, mapping và repository scanning.
14. Theo dõi lỗi, độ trễ, memory, queue và tải Elasticsearch trong môi trường thực tế.

## 25. Tổng kết

ReactiveElasticsearchRepository là abstraction repository của Spring Data Elasticsearch sử dụng Project Reactor. Interface này kế thừa ReactiveCrudRepository và ReactiveSortingRepository, cung cấp CRUD, sorting và query method dưới dạng Mono hoặc Flux. Derived query method, Pageable, Sort và @Query vẫn được hỗ trợ; khi cần query động, có thể dùng ReactiveElasticsearchOperations.

Repository scanning được kích hoạt bằng EnableReactiveElasticsearchRepositories. Nếu không chỉ định package, Spring quét package của class cấu hình và các package con. Có thể dùng basePackages hoặc basePackageClasses để chỉ rõ phạm vi; reactiveElasticsearchTemplateRef chọn ReactiveElasticsearchOperations bean dùng cho repository. Scanning repository là cơ chế riêng, không đồng nghĩa với ComponentScan hoặc việc tạo entity bean.

Với Spring Boot, reactive client và template có thể được auto-configure khi dependency phù hợp có trên classpath. Khi cấu hình thủ công trong Spring Data Elasticsearch hiện hành, dùng ReactiveElasticsearchConfiguration. Giữ reactive chain xuyên suốt, trả publisher về caller, tránh block/subscribe trong service và kiểm soát backpressure khi xử lý luồng lớn. Tách package reactive và imperative rõ ràng giúp repository được phát hiện và gắn đúng operations.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Reactive Elasticsearch Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-elasticsearch-repositories.html)
- [Spring Data Elasticsearch – ReactiveElasticsearchRepository API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/repository/ReactiveElasticsearchRepository.html)
- [Spring Data Elasticsearch – EnableReactiveElasticsearchRepositories API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/repository/config/EnableReactiveElasticsearchRepositories.html)
- [Spring Data Elasticsearch – ReactiveElasticsearchConfiguration API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ReactiveElasticsearchConfiguration.html)
- [Spring Data Elasticsearch – Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Boot – NoSQL and Elasticsearch](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
