# ReactiveElasticsearchOperations và ReactiveElasticsearchTemplate

Spring Data Elasticsearch cung cấp API reactive để thao tác với Elasticsearch theo mô hình Reactor. Hai thành phần trung tâm là `ReactiveElasticsearchOperations` và `ReactiveElasticsearchTemplate`: interface mô tả các thao tác reactive ở mức document/search, còn template là implementation thực thi các thao tác đó qua reactive Elasticsearch client.

API reactive trả về `Mono` hoặc `Flux` thay vì trả kết quả đồng bộ. `Mono<T>` biểu diễn không hoặc một giá trị; `Flux<T>` biểu diễn một chuỗi từ không đến nhiều giá trị. Nhờ vậy, ứng dụng Spring WebFlux có thể ghép thao tác Elasticsearch vào pipeline không chặn thread, điều khiển luồng dữ liệu và kết hợp với các nguồn reactive khác.

Reactive API không làm thay đổi semantics của Elasticsearch: một document write vẫn là thao tác ở cấp document; Bulk vẫn có thể thành công một phần; không có transaction ACID đa tài liệu tương đương JPA. Reactive chỉ thay đổi cách ứng dụng tương tác và quản lý luồng thực thi.

## 1. Reactive trong Spring Data Elasticsearch

Trong ứng dụng imperative, một thao tác thường trả kết quả ngay sau khi method chạy:

```java
Product product = operations.get("KB-1001", Product.class);
```

Với API reactive, method trả về một publisher:

```java
Mono<Product> product = reactiveOperations.get(
    "KB-1001",
    Product.class,
    IndexCoordinates.of("products")
);
```

`Mono<Product>` chưa phải `Product`; nó mô tả một pipeline có thể phát ra một sản phẩm, hoàn tất rỗng nếu không tìm thấy hoặc phát lỗi. Việc thực thi thường bắt đầu khi có subscriber yêu cầu dữ liệu.

### 1.1 Mono và Flux

| Kiểu | Số phần tử | Ví dụ |
|---|---:|---|
| `Mono<T>` | 0 hoặc 1 | Lấy document theo ID, đếm kết quả, lưu một entity |
| `Flux<T>` | 0 đến nhiều | Lấy nhiều entity, stream search hits, lưu nhiều entity |

Ví dụ:

```java
Mono<Product> oneProduct = reactiveOperations.get(
    "KB-1001", Product.class, PRODUCTS
);

Flux<SearchHit<Product>> matchingProducts = reactiveOperations.search(
    query, Product.class, PRODUCTS
);
```

`Mono` và `Flux` là các kiểu của Project Reactor. Chúng thực hiện Reactive Streams contract, hỗ trợ truyền tín hiệu `onNext`, `onError`, `onComplete` và backpressure.

### 1.2 Publisher thường lazy

Tạo `Mono` hoặc `Flux` thường chỉ tạo pipeline. Request thực tế được gửi khi pipeline được subscribe. Vì thế, đoạn code sau không tự đảm bảo request đã chạy:

```java
Mono<Product> result = reactiveOperations.get("KB-1001", Product.class, PRODUCTS);
```

Trong controller WebFlux, trả publisher cho framework để framework subscribe và ghi response. Trong service, thường trả tiếp publisher cho caller thay vì gọi `.subscribe()` bên trong method.

### 1.3 Không gọi block trong luồng reactive

Không chuyển reactive API trở lại synchronous bằng `.block()` trong controller hoặc trên event-loop thread:

```java
// Tránh trong WebFlux request path.
Product product = reactiveOperations
    .get("KB-1001", Product.class, PRODUCTS)
    .block();
```

`block()` chờ kết quả và chiếm thread. Nếu gọi trên event loop, có thể làm giảm throughput hoặc gây lỗi blocking-call tùy môi trường. Chỉ cân nhắc bridge sang blocking ở ranh giới được kiểm soát, chẳng hạn một chương trình batch imperative; không dùng nó để viết service WebFlux.

## 2. Phân biệt Operations và Template

`ReactiveElasticsearchOperations` là abstraction mà service nên phụ thuộc. Nó tập hợp các thao tác reactive như save, get, delete, count, search, index operations và các thao tác query khác tùy phiên bản.

`ReactiveElasticsearchTemplate` là implementation cụ thể của interface này. Template phối hợp Elasticsearch reactive client, converter/mapping context và các thành phần Spring Data để chuyển entity/query thành request Elasticsearch và chuyển response về kiểu Java.

| Thành phần | Vai trò |
|---|---|
| `ReactiveElasticsearchOperations` | Interface thao tác reactive, phù hợp để inject vào service |
| `ReactiveElasticsearchTemplate` | Implementation của Operations, thực thi qua reactive client |
| `ReactiveElasticsearchClient` | Client reactive cấp thấp hơn được template sử dụng |
| `ElasticsearchConverter` | Chuyển đổi entity và document theo mapping metadata |
| `ReactiveElasticsearchRepository` | Repository abstraction reactive cho CRUD/query method |

### 2.1 Vì sao service nên phụ thuộc interface?

```java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

Service chỉ cần hợp đồng thao tác. Spring inject implementation phù hợp, thường là `ReactiveElasticsearchTemplate`. Cách này giảm coupling với class triển khai và giúp thay cấu hình hoặc mock abstraction khi kiểm thử.

### 2.2 Khi nào dùng Template trực tiếp?

Thông thường inject `ReactiveElasticsearchOperations` là đủ. Chỉ phụ thuộc trực tiếp `ReactiveElasticsearchTemplate` khi ứng dụng thật sự cần API riêng của implementation. Với query DSL linh hoạt, `NativeQuery` cùng Operations thường đáp ứng được mà không cần gọi client cấp thấp.

## 3. Cấu hình ReactiveElasticsearchTemplate

Reactive template cần reactive Elasticsearch client và mapping converter. Spring Data cung cấp cấu hình nền để tạo các bean này theo client/version đang dùng.

### 3.1 Dependency

Ứng dụng thường cần:

- Spring Data Elasticsearch tương thích với phiên bản Spring Boot/Spring Data của dự án.
- Reactor Core (thường đã có qua Spring WebFlux).
- Spring WebFlux nếu xây dựng HTTP API reactive.
- Reactive Elasticsearch client module tương ứng với dòng Spring Data Elasticsearch.

Không nên tự nâng riêng một artifact Elasticsearch Java Client lên phiên bản bất kỳ mà bỏ qua dependency management của Spring Boot/Spring Data. Các phiên bản Spring Data Elasticsearch được xây dựng để tương thích với một dòng Elasticsearch client cụ thể.

Ví dụ Maven ở mức khái quát:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>
```

Tên starter và dependency management phụ thuộc phiên bản Spring Boot. Kiểm tra BOM và tài liệu của dòng phiên bản đang sử dụng để xác định reactive client implementation được cung cấp.

### 3.2 AbstractReactiveElasticsearchConfiguration

Spring Data Elasticsearch cung cấp cấu hình nền reactive. Một cấu hình điển hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.AbstractReactiveElasticsearchConfiguration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;

@Configuration
@EnableReactiveElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class ReactiveElasticsearchConfig
        extends AbstractReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }
}
```

Cấu hình nền tạo reactive client, converter và reactive operations/template theo API của phiên bản. Khi ứng dụng dùng authentication, TLS, proxy hoặc nhiều node, cấu hình `ClientConfiguration` tương ứng với môi trường triển khai; không hard-code credential trong source code.

### 3.3 Inject Operations

Sau khi cấu hình, service có thể inject interface:

```java
@Service
public class ProductService {

    private final ReactiveElasticsearchOperations operations;

    public ProductService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

Spring thường cung cấp bean `ReactiveElasticsearchTemplate` làm implementation. Nếu ứng dụng tự tạo template, cần cung cấp đúng reactive client và converter, đồng thời bảo đảm lifecycle bean được quản lý bởi Spring.

### 3.4 Reactive và imperative client là hai luồng cấu hình khác nhau

Không truyền blocking `ElasticsearchClient` vào nơi yêu cầu reactive client. Tương tự, `ElasticsearchOperations`/`ElasticsearchTemplate` là API imperative; `ReactiveElasticsearchOperations`/`ReactiveElasticsearchTemplate` là API reactive. Chọn đúng abstraction theo execution model của ứng dụng.

## 4. Entity và mapping

Reactive template dùng mapping metadata giống Spring Data Elasticsearch thông thường. Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Integer)
    private Integer stock;

    protected Product() {
    }

    public Product(String id, String sku, String name, Double price, Integer stock) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.stock = stock;
    }

    // Getters and setters omitted for brevity.
}
```

`@Document` chỉ định index mặc định. `@Id` ánh xạ ID document. `@Field` mô tả kiểu dữ liệu Elasticsearch và các metadata mapping liên quan. Reactive template dùng converter để chuyển entity sang JSON document và ngược lại.

### 4.1 Index và mapping operations

Các thao tác index như kiểm tra tồn tại, tạo index hoặc tạo mapping cũng có API reactive qua index operations. Trong các phiên bản Spring Data hiện đại, `operations.indexOps(Product.class)` trả về abstraction index operations reactive; các thao tác như `exists()`, `create()` hoặc `putMapping()` trả publisher.

Ví dụ dạng sử dụng:

```java
Mono<Boolean> ensureIndex = operations.indexOps(Product.class)
    .exists()
    .flatMap(exists -> exists
        ? Mono.just(true)
        : operations.indexOps(Product.class).create()
    );
```

Đây là mẫu minh họa; chữ ký chính xác của index operations và cách tạo mapping có thể khác theo phiên bản. Với môi trường production, index/mapping thường được quản lý qua migration hoặc deployment step có kiểm soát thay vì tự tạo lại ở mỗi request.

## 5. CRUD với ReactiveElasticsearchOperations

### 5.1 Save một entity

`save` trả về `Mono<T>`:

```java
private static final IndexCoordinates PRODUCTS =
    IndexCoordinates.of("products");

public Mono<Product> save(Product product) {
    return operations.save(product, PRODUCTS);
}
```

Publisher phát ra entity đã được lưu/được cập nhật metadata theo mapping và client. Vì publisher lazy, caller cần subscribe hoặc trả nó cho một tầng reactive phía trên để thao tác thực thi.

### 5.2 Save nhiều entity

`saveAll` trả về `Flux<T>` và có thể nhận một publisher nguồn:

```java
public Flux<Product> saveAll(Flux<Product> products) {
    return operations.saveAll(products, PRODUCTS);
}
```

Có thể tạo publisher từ collection:

```java
Flux<Product> source = Flux.fromIterable(products);
return operations.saveAll(source, PRODUCTS);
```

Với lượng dữ liệu lớn, không nên nạp toàn bộ file vào memory rồi tạo một Flux khổng lồ nếu nguồn có thể đọc theo batch. Hãy dùng publisher có khả năng phát dữ liệu theo nhu cầu, giới hạn concurrency và theo dõi kết quả lỗi.

### 5.3 Get theo ID

```java
public Mono<Product> findById(String id) {
    return operations.get(id, Product.class, PRODUCTS);
}
```

Nếu document không tồn tại, API thường hoàn tất rỗng thay vì phát một `Product` null. Caller có thể chuyển trường hợp rỗng thành lỗi nghiệp vụ:

```java
public Mono<Product> requireById(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ));
}
```

Không trả `Mono.just(null)`: Reactor không cho phép phát null như một phần tử.

### 5.4 Delete theo ID

```java
public Mono<Void> delete(String id) {
    return operations.delete(id, Product.class, PRODUCTS)
        .then();
}
```

`.then()` bỏ giá trị kết quả và chỉ giữ tín hiệu hoàn tất/lỗi. Nếu API cần trả trạng thái xóa hoặc ID, giữ lại kiểu kết quả mà phiên bản Operations cung cấp thay vì gọi `.then()`.

### 5.5 Count

```java
public Mono<Long> countActive() {
    Query query = new CriteriaQuery(
        new Criteria("active").is(true)
    );

    return operations.count(query, Product.class, PRODUCTS);
}
```

`count` trả về `Mono<Long>` vì kết quả đến bất đồng bộ. Nó không cần tải toàn bộ document hits về ứng dụng.

## 6. Search bằng ReactiveElasticsearchOperations

Reactive Operations cung cấp các dạng search khác nhau tùy nhu cầu: stream từng hit, lấy wrapper chứa metadata search hoặc lấy page abstraction.

### 6.1 Tạo NativeQuery

Ví dụ tìm sản phẩm theo tên:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
```

`NativeQuery` dùng Query DSL builder của Elasticsearch Java Client. Nó có thể kết hợp bool, match, range, nested, aggregation, sort và các tùy chọn search khác. Query object không phụ thuộc việc execution imperative hay reactive; điểm khác là Operations thực thi và trả kết quả theo kiểu nào.

### 6.2 Search trả Flux<SearchHit<T>>

```java
public Flux<SearchHit<Product>> searchHits(String keyword) {
    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(keyword)
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

    return operations.search(query, Product.class, PRODUCTS);
}
```

Mỗi phần tử là `SearchHit<Product>`, chứa entity cùng metadata như score, ID, sort values hoặc highlight tùy request. Nếu chỉ cần entity:

```java
public Flux<Product> searchProducts(String keyword) {
    return searchHits(keyword)
        .map(SearchHit::getContent);
}
```

`Flux` cho phép downstream xử lý từng hit thay vì phải gom tất cả thành một `List` trước khi tiếp tục.

### 6.3 SearchForHits khi cần metadata

Khi cần tổng số hits hoặc metadata search cùng stream kết quả, dùng API `searchForHits` trả `Mono<ReactiveSearchHits<T>>` trong các phiên bản có abstraction này:

```java
public Mono<ReactiveSearchHits<Product>> searchWithMetadata(String keyword) {
    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(keyword)
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

    return operations.searchForHits(query, Product.class, PRODUCTS);
}
```

`ReactiveSearchHits` chứa metadata search và publisher các hit. Vì kết quả hits là reactive, việc truy cập/tiêu thụ danh sách vẫn diễn ra qua `Flux`; không nên giả định có một `List` đồng bộ sẵn trong memory.

### 6.4 SearchForPage

Khi use case cần abstraction dạng trang, các phiên bản Spring Data Elasticsearch hỗ trợ `searchForPage(...)` trả `Mono<ReactiveSearchPage<T>>`. Page abstraction giữ thông tin pageable và tổng số hit cùng publisher nội dung.

```java
public Mono<ReactiveSearchPage<Product>> searchPage(String keyword) {
    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(keyword)
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

    return operations.searchForPage(query, Product.class, PRODUCTS);
}
```

Chữ ký cụ thể của `searchForHits`, `searchForPage` và các kiểu wrapper có thể thay đổi giữa các dòng Spring Data Elasticsearch. Hãy đối chiếu Javadoc đúng phiên bản dependency trước khi sử dụng.

## 7. SearchHits, SearchHit và ReactiveSearchHits

Ba kiểu tên gần nhau nhưng có vai trò khác nhau:

| Kiểu | Ý nghĩa |
|---|---|
| `SearchHit<T>` | Một hit, gồm entity và metadata của document tìm được |
| `SearchHits<T>` | Kết quả search dạng imperative, thường chứa collection hits và metadata |
| `ReactiveSearchHits<T>` | Wrapper reactive, metadata đi cùng publisher các hit |
| `ReactiveSearchPage<T>` | Page abstraction reactive cho kết quả search |

Reactive code không nên chuyển `Flux<SearchHit<T>>` thành `List` chỉ để lấy total count. Dùng wrapper/metadata API khi cần total hits hoặc thông tin tổng thể. Nếu chỉ cần hiển thị stream kết quả, `Flux<SearchHit<T>>` thường đơn giản hơn.

### 7.1 Lấy highlight

Nếu query có highlight, metadata highlight nằm trong `SearchHit`:

```java
return operations.search(query, Product.class, PRODUCTS)
    .map(hit -> new ProductSearchResult(
        hit.getContent(),
        hit.getHighlightFields()
    ));
```

DTO có thể giữ entity và map highlight riêng. Không nên sửa nội dung entity chỉ để nhét snippet highlight vào field source gốc.

### 7.2 Lấy sort values

Với pagination bằng `search_after`, `SearchHit` có thể cung cấp sort values của document. Ứng dụng cần giữ nguyên các giá trị đó để tạo cursor cho request tiếp theo. API cụ thể để đọc sort values phụ thuộc kiểu `SearchHit` và phiên bản Spring Data.

## 8. CriteriaQuery và NativeQuery

Reactive Operations có thể thực thi các loại `Query` mà Spring Data hỗ trợ. Hai cách xây query thường gặp:

- `CriteriaQuery`: biểu diễn điều kiện đơn giản theo field/operator.
- `NativeQuery`: biểu diễn Elasticsearch Query DSL linh hoạt thông qua Java Client builder.

### 8.1 CriteriaQuery

```java
Query query = new CriteriaQuery(
    new Criteria("status").is("ACTIVE")
        .and("price").greaterThanEqual(50)
);

return operations.search(query, Product.class, PRODUCTS)
    .map(SearchHit::getContent);
```

CriteriaQuery phù hợp với điều kiện lọc cơ bản và query được tạo động từ các tham số đơn giản.

### 8.2 NativeQuery cho bool query

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("name")
            .query(keyword)
        ))
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
        .filter(f -> f.range(r -> r
            .number(n -> n
                .field("price")
                .gte(50.0)
            )
        ))
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();

return operations.search(query, Product.class, PRODUCTS);
```

NativeQuery thích hợp khi cần Query DSL đầy đủ, chẳng hạn nested query, function score, highlight, aggregation hoặc sort nâng cao. Kiểu query không làm mất tính reactive; publisher được tạo ở bước thực thi Operations.

## 9. Ghép nhiều thao tác reactive

Lợi ích lớn của Reactor là có thể ghép thao tác mà không cần chặn thread.

### 9.1 Lấy document rồi biến đổi

```java
public Mono<ProductView> getView(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .map(product -> new ProductView(
            product.getId(),
            product.getName(),
            product.getPrice()
        ));
}
```

`map` dùng cho phép biến đổi đồng bộ trên giá trị đã phát ra. Nếu bước tiếp theo trả về `Mono` hoặc `Flux`, dùng `flatMap` để làm phẳng publisher lồng nhau.

### 9.2 Ghép hai thao tác bất đồng bộ

```java
public Mono<ProductDetails> getDetails(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .flatMap(product -> loadInventory(product.getSku())
            .map(inventory -> new ProductDetails(product, inventory))
        );
}
```

`flatMap` tránh tạo `Mono<Mono<ProductDetails>>`. Nếu hai nguồn không phụ thuộc nhau, có thể chạy song song bằng `Mono.zip`:

```java
return Mono.zip(
    operations.get(id, Product.class, PRODUCTS),
    loadReviews(id)
).map(tuple -> new ProductDetails(tuple.getT1(), tuple.getT2()));
```

Khi một nguồn có thể hoàn tất rỗng, hãy quyết định semantics của `zip`: `Mono.zip` cần mỗi nguồn phát một giá trị để tạo tuple. Dùng `defaultIfEmpty`, `switchIfEmpty` hoặc `zipWhen` theo nghiệp vụ.

### 9.3 concatMap và flatMap trên Flux

Khi xử lý nhiều ID:

```java
Flux<Product> findMany(List<String> ids) {
    return Flux.fromIterable(ids)
        .concatMap(id -> operations.get(id, Product.class, PRODUCTS));
}
```

`concatMap` xử lý lần lượt và giữ thứ tự nguồn. `flatMap` cho phép nhiều thao tác chạy đồng thời, có thể tăng throughput nhưng kết quả có thể phát ra không theo thứ tự ban đầu:

```java
Flux<Product> findManyConcurrently(List<String> ids) {
    return Flux.fromIterable(ids)
        .flatMap(id -> operations.get(id, Product.class, PRODUCTS), 8);
}
```

Tham số concurrency giới hạn số publisher con hoạt động đồng thời. Chọn giá trị theo tải cluster, connection pool và độ trễ; không tăng vô hạn để tìm throughput.

## 10. Backpressure và xử lý dữ liệu lớn

Reactive Streams cho phép subscriber báo nhu cầu dữ liệu qua request(n). `Flux` có thể phối hợp với downstream để tránh đẩy vô hạn phần tử vào một consumer chậm.

Tuy nhiên, backpressure không có nghĩa mọi API Elasticsearch đều trả dữ liệu từng document qua network theo một stream vô hạn. Một search request có thể vẫn lấy một batch hits từ Elasticsearch rồi phát chúng qua Flux. Với dữ liệu lớn, cần chọn cơ chế pagination/scroll phù hợp và kiểm soát kích thước batch.

### 10.1 Giới hạn concurrency

Khi ingest nhiều document:

```java
Flux<Product> source = readProductsReactive();

return source
    .buffer(500)
    .concatMap(batch -> operations.saveAll(
        Flux.fromIterable(batch), PRODUCTS
    ));
```

Ví dụ chia nguồn thành batch 500 rồi gửi lần lượt. Batch size là giá trị minh họa; cần đo kích thước payload, throughput và áp lực cluster.

Nếu muốn chạy một số batch song song, có thể dùng `flatMap` với concurrency giới hạn. Nhưng cần lưu ý thứ tự commit và xử lý partial failure.

### 10.2 Không gom toàn bộ Flux nếu không cần

`collectList()` gom mọi phần tử vào memory:

```java
Mono<List<Product>> allProducts = operations.search(query, Product.class, PRODUCTS)
    .map(SearchHit::getContent)
    .collectList();
```

Chỉ dùng khi kết quả có giới hạn hợp lý và caller thật sự cần một list. Với hàng trăm nghìn hit, việc gom toàn bộ có thể gây áp lực heap. Hãy xử lý từng batch/element hoặc ghi dần ra sink.

### 10.3 Backpressure không tự giải quyết giới hạn Search API

`Flux` không bỏ qua `from`/`size`, `max_result_window`, giới hạn scroll/PIT hoặc giới hạn response Elasticsearch. Muốn duyệt nhiều document, cần dùng scroll, PIT + `search_after` hoặc pagination theo API hỗ trợ của phiên bản. Không nhầm publisher reactive với một cursor search vô hạn ở server.

## 11. Error handling và retry

Reactive pipeline truyền lỗi qua tín hiệu `onError`. Có thể chuyển đổi hoặc xử lý lỗi bằng Reactor operators.

### 11.1 Chuyển lỗi kỹ thuật thành lỗi nghiệp vụ

```java
public Mono<Product> findRequired(String id) {
    return operations.get(id, Product.class, PRODUCTS)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .onErrorMap(ElasticsearchException.class,
            ex -> new ProductSearchException("Cannot read product", ex));
}
```

Trong code thực tế, exception type phụ thuộc client và phiên bản. Chỉ map những lỗi đã xác định; không chuyển mọi exception thành not-found vì sẽ che giấu lỗi kết nối hoặc mapping.

### 11.2 Retry có điều kiện

```java
return operations.get(id, Product.class, PRODUCTS)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientFailure));
```

Retry phù hợp với lỗi tạm thời như network reset hoặc một số lỗi overload. Không retry vô hạn và không retry lỗi mapping, validation hoặc authorization.

### 11.3 Retry write cần idempotency

Nếu write đã thành công ở Elasticsearch nhưng response bị mất, retry có thể gửi lại thao tác. Index cùng một document ID với cùng nội dung thường có kết quả cuối idempotent; script cộng/trừ hoặc tạo document với ID ngẫu nhiên có thể không idempotent.

Trước khi retry write, hãy xác định:

- ID có ổn định không?
- Cùng payload gửi lại có tạo cùng trạng thái cuối không?
- Script có tác dụng phụ lặp không?
- Có version/sequence hoặc idempotency key để phát hiện request lặp không?
- Có cần đọc lại trạng thái trước khi retry không?

### 11.4 Timeout và cancellation

```java
return operations.get(id, Product.class, PRODUCTS)
    .timeout(Duration.ofSeconds(3));
```

Timeout phát lỗi nếu publisher không hoàn tất trong thời gian quy định. Cancellation từ client disconnect có thể hủy việc tiêu thụ pipeline; mức độ hủy request ở client/server phụ thuộc transport và API. Không giả định cancellation có nghĩa Elasticsearch chắc chắn chưa thực hiện write.

## 12. Tích hợp với Spring WebFlux

Controller WebFlux có thể trả trực tiếp `Mono` hoặc `Flux`:

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductSearchService service;

    public ProductController(ProductSearchService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ProductView> get(@PathVariable String id) {
        return service.getView(id);
    }

    @GetMapping
    public Flux<ProductView> search(@RequestParam String q) {
        return service.searchProducts(q)
            .map(ProductView::from);
    }
}
```

Spring WebFlux subscribe vào publisher và ghi dữ liệu ra response. Không cần gọi `.subscribe()` hoặc `.block()` trong controller.

### 12.1 Trả Page hay Flux?

Nếu endpoint cần page metadata như total count, page number và page size, hãy trả DTO page có cấu trúc rõ ràng. Nếu endpoint dùng streaming response hoặc chỉ cần các phần tử, Flux có thể phù hợp hơn.

Không nên gom mọi kết quả vào list chỉ để trả JSON array khi tập kết quả có thể rất lớn. Với API thông thường, pagination vẫn cần giới hạn size và có hợp đồng page/cursor rõ ràng.

## 13. Reactive repository và ReactiveElasticsearchOperations

Spring Data Elasticsearch cũng hỗ trợ repository reactive, ví dụ `ReactiveElasticsearchRepository<T, ID>`. Repository phù hợp với CRUD và query method theo quy ước tên.

```java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByActiveTrue();

    Flux<Product> findByNameContaining(String name);
}
```

So sánh:

| Lựa chọn | Phù hợp khi |
|---|---|
| `ReactiveElasticsearchRepository` | CRUD/query method đơn giản, abstraction repository |
| `ReactiveElasticsearchOperations` | Cần điều khiển query, mapping, search metadata hoặc nhiều thao tác template |
| `ReactiveElasticsearchTemplate` | Cần implementation cụ thể hoặc API template đặc thù |
| Reactive client cấp thấp | Cần tính năng client chưa được abstraction Spring Data expose |

Repository và Operations có thể cùng tồn tại trong một ứng dụng. Không cần dùng repository cho mọi query nếu query DSL phức tạp; cũng không cần dùng template cho thao tác CRUD đơn giản đã có repository method rõ ràng.

## 14. Reactive search và pagination

### 14.1 PageRequest

Có thể gắn `Pageable` vào query:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m.field("name").query(keyword)))
    .withPageable(PageRequest.of(
        page,
        size,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("sku"))
    ))
    .build();

return operations.searchForPage(query, Product.class, PRODUCTS);
```

Page number thường bắt đầu từ 0. API cần giới hạn `size`, validate page và allowlist sort field từ client. Reactive không làm cho deep offset pagination rẻ hơn.

### 14.2 Deep pagination

Với số lượng document lớn, `from`/`size` có giới hạn `max_result_window` và chi phí tăng theo offset. Dùng `search_after` với sort ổn định và PIT khi cần duyệt sâu trên một snapshot. Reactive API có thể phát kết quả theo Flux, nhưng ứng dụng vẫn phải quản lý PIT ID, sort cursor, checkpoint và cleanup.

### 14.3 Scroll

Một số phiên bản Spring Data Elasticsearch cung cấp reactive scroll hoặc `searchForStream`-style APIs. API cụ thể khác theo release. Scroll context có `keep_alive`, phải tiếp tục đúng hạn và được clear khi xong. Publisher reactive không tự biến scroll ID thành checkpoint bền vững.

## 15. Aggregations trong reactive operations

Reactive Operations cũng có thể thực thi query chứa aggregation. Khi cần hits và aggregation metadata, dùng wrapper search result reactive phù hợp với phiên bản; khi chỉ cần aggregation, đặt search `size: 0` và đọc aggregation container.

Ví dụ khai báo terms aggregation:

```java
Aggregation byCategory = Aggregation.of(a -> a
    .terms(t -> t.field("category").size(20))
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withMaxResults(0)
    .withAggregation("by_category", byCategory)
    .build();
```

Thực thi reactive:

```java
return operations.searchForHits(query, Product.class, PRODUCTS)
    .map(searchHits -> searchHits.getAggregations());
```

Kiểu aggregation container và cách đọc bucket phụ thuộc Elasticsearch Java Client/Spring Data version. Hãy phân biệt bucket/metric với `Flux<SearchHit<T>>`; aggregation không phải một stream document.

## 16. Update và delete reactive

Reactive Operations cung cấp các thao tác update/delete tương ứng với API mà phiên bản hỗ trợ. Các method thường trả `Mono` chứa response hoặc kết quả thao tác.

Ví dụ delete theo query ở mức khái quát:

```java
Query inactiveProducts = new CriteriaQuery(
    new Criteria("active").is(false)
);

Mono<?> deleteResult = operations.delete(
    inactiveProducts,
    Product.class,
    PRODUCTS
);
```

Với thao tác update, có thể dùng `UpdateQuery` và reactive update API của phiên bản. Cần kiểm tra đúng chữ ký method và response type vì một số phiên bản expose các thao tác khác nhau giữa imperative và reactive template.

### 16.1 Reactive không tạo transaction đa document

Ghép nhiều `Mono` bằng `then`, `zip` hoặc `flatMap` chỉ điều khiển thứ tự/thực thi publisher. Nó không tạo transaction ACID chung. Nếu bước đầu đã ghi thành công và bước sau lỗi, Reactor không tự rollback thao tác Elasticsearch trước đó.

Với workflow nhiều bước, vẫn cần idempotency, outbox, saga hoặc compensation theo nghiệp vụ. `onErrorResume` chỉ chọn pipeline thay thế; nó không đảo ngược side effect đã commit.

## 17. Blocking code và scheduler

Không phải mọi thư viện mà reactive service gọi tới đều non-blocking. Nếu một bước dùng JDBC, file I/O blocking hoặc SDK đồng bộ, không chạy nó trực tiếp trên event-loop thread.

Ví dụ bridge một đoạn blocking có chủ đích:

```java
Mono<LegacyData> loadLegacyData(String id) {
    return Mono.fromCallable(() -> legacyBlockingClient.load(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`boundedElastic` dành cho tác vụ blocking có giới hạn. Không bọc reactive Elasticsearch call trong `fromCallable` rồi chuyển sang boundedElastic; làm vậy sẽ mất lợi ích reactive và tạo thêm thread blocking không cần thiết.

## 18. Kiểm thử reactive operations

Có thể kiểm thử service reactive bằng Reactor Test và `StepVerifier`:

```java
StepVerifier.create(service.findById("KB-1001"))
    .expectNextMatches(product -> product.getSku().equals("KB-1001"))
    .verifyComplete();
```

Nếu document không tồn tại:

```java
StepVerifier.create(service.requireById("missing"))
    .expectError(ProductNotFoundException.class)
    .verify();
```

Unit test có thể mock `ReactiveElasticsearchOperations` và trả `Mono.just`, `Mono.empty` hoặc `Flux.just`. Integration test cần Elasticsearch tương thích để kiểm tra mapping, query DSL, converter và reactive client thực tế.

Khi mock, cần nhớ publisher lazy: chỉ verify pipeline mới kích hoạt publisher trong test. Không gọi `.subscribe()` tùy tiện rồi assert ngay vì test có thể kết thúc trước khi pipeline hoàn tất.

## 19. Những lỗi thường gặp

### 19.1 Gọi block trong controller

`.block()` làm mất non-blocking behavior và có thể chặn event loop. Trả `Mono`/`Flux` cho WebFlux.

### 19.2 Gọi subscribe trong service

Nếu service tự subscribe, caller không còn kiểm soát lifecycle, lỗi và kết quả. Trả publisher để caller ghép pipeline; chỉ subscribe ở ranh giới ứng dụng được xác định rõ như worker độc lập.

### 19.3 Nghĩ tạo Mono là đã gửi request

Publisher thường lazy. Nếu không có subscriber, pipeline có thể không chạy. Trong WebFlux, framework subscribe khi xử lý response.

### 19.4 Dùng map khi callback trả publisher

`map` tạo publisher lồng nhau như `Mono<Mono<T>>`. Dùng `flatMap` hoặc `flatMapMany` khi cần flatten.

### 19.5 flatMap không giới hạn concurrency

Gọi nhiều request Elasticsearch đồng thời có thể gây quá tải connection pool hoặc cluster. Giới hạn concurrency và dùng backpressure/batching.

### 19.6 collectList trên kết quả lớn

Gom toàn bộ Flux vào memory có thể gây heap pressure. Xử lý từng phần tử hoặc batch khi dữ liệu lớn.

### 19.7 Retry write không idempotent

Retry script tăng stock có thể cộng nhiều lần nếu request đầu đã thành công nhưng response bị mất. Thiết kế ID, version hoặc idempotency key phù hợp.

### 19.8 Dùng imperative Operations trong reactive pipeline

Không gọi `ElasticsearchOperations` blocking trên event loop rồi bọc kết quả vào Mono. Inject `ReactiveElasticsearchOperations` và dùng reactive client.

### 19.9 Nghĩ Flux đồng nghĩa server streaming toàn bộ index

Flux là abstraction publisher ở ứng dụng. Search API vẫn có giới hạn size/pagination; export lớn cần scroll hoặc PIT + search_after.

### 19.10 Nghĩ reactive có transaction

Reactor điều khiển luồng tín hiệu, không cung cấp rollback cho side effect Elasticsearch. Nhiều document vẫn cần workflow nhất quán ở tầng ứng dụng.

## 20. Service mẫu tổng hợp

```java
@Service
public class ReactiveProductService {

    private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Mono<Product> findById(String id) {
        return operations.get(id, Product.class, PRODUCTS)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }

    public Mono<Product> save(Product product) {
        return operations.save(product, PRODUCTS);
    }

    public Flux<Product> saveAll(Flux<Product> products) {
        return operations.saveAll(products, PRODUCTS);
    }

    public Flux<Product> search(String keyword, int page, int size) {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.match(m -> m
                .field("name")
                .query(keyword)
            ))
            .withPageable(PageRequest.of(page, size))
            .build();

        return operations.search(query, Product.class, PRODUCTS)
            .map(SearchHit::getContent);
    }

    public Mono<Long> countByName(String keyword) {
        Query query = new CriteriaQuery(
            new Criteria("name").contains(keyword)
        );

        return operations.count(query, Product.class, PRODUCTS);
    }

    public Mono<Void> delete(String id) {
        return operations.delete(id, Product.class, PRODUCTS).then();
    }
}
```

Service minh họa CRUD, search và count bằng reactive publisher. Tên overload cụ thể có thể khác theo phiên bản Spring Data Elasticsearch; khi áp dụng vào dự án, dùng đúng API của dependency đã được quản lý.

## 21. Nguyên tắc sử dụng

- Inject `ReactiveElasticsearchOperations` để service phụ thuộc abstraction; `ReactiveElasticsearchTemplate` là implementation.
- Dùng `Mono` cho không/một kết quả và `Flux` cho chuỗi nhiều kết quả.
- Trả publisher từ service/controller; không gọi `.block()` hoặc `.subscribe()` tùy tiện trong request path.
- Dùng `map` cho phép biến đổi đồng bộ, `flatMap` cho thao tác trả publisher.
- Giới hạn concurrency, chia batch và tránh `collectList()` trên tập dữ liệu lớn.
- Dùng `NativeQuery` hoặc `CriteriaQuery` theo độ phức tạp của query.
- Dùng search wrapper reactive khi cần total hits, aggregations hoặc page metadata.
- Xử lý lỗi bằng Reactor operators và retry có điều kiện; write retry phải idempotent.
- Cấu hình reactive client đúng với dòng Spring Data Elasticsearch, không trộn với blocking client.
- Dùng repository reactive cho CRUD/query method đơn giản; dùng Operations cho query cần điều khiển chi tiết.
- Nhớ Flux không loại bỏ giới hạn pagination/search context của Elasticsearch.
- Reactive không cung cấp transaction ACID đa document; vẫn cần outbox, saga, compensation hoặc thiết kế aggregate phù hợp.

## 22. Tổng kết

`ReactiveElasticsearchOperations` là abstraction reactive để thao tác với Elasticsearch; `ReactiveElasticsearchTemplate` là implementation làm việc qua reactive Elasticsearch client và converter của Spring Data. API trả `Mono` hoặc `Flux`, cho phép ghép CRUD, search, count và các thao tác query vào pipeline Reactor mà không phải chặn thread.

Trong ứng dụng WebFlux, controller nên trả publisher để framework quản lý subscription. Service nên ghép thao tác bằng `map`, `flatMap`, `zip`, `concatMap` hoặc `flatMap` có giới hạn concurrency. Cần hiểu publisher lazy, backpressure, cancellation, error propagation và retry. `ReactiveSearchHits`/`ReactiveSearchPage` hữu ích khi cần metadata, còn `Flux<SearchHit<T>>` phù hợp khi xử lý từng hit.

Reactive không làm thay đổi giới hạn của Elasticsearch. Search vẫn cần pagination/cursor, bulk vẫn có thể thành công một phần và nhiều document không được commit/rollback trong một transaction ACID chung. Hãy dùng đúng reactive client, kiểm soát batch/concurrency, thiết kế retry idempotent và xử lý nhất quán nghiệp vụ ở tầng ứng dụng.

## Tài liệu tham khảo

- [Spring Data Elasticsearch Reference — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch Reference — Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/reactive-repositories.html)
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Spring Framework — Web Reactive](https://docs.spring.io/spring-framework/reference/web/webflux.html)
