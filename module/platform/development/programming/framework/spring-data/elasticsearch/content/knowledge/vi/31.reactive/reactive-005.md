# Chuỗi thao tác lưu, tìm kiếm và xóa không chặn

Spring Data Elasticsearch Reactive cho phép ứng dụng thực hiện các thao tác đọc và ghi theo mô hình reactive, không giữ một thread chờ đồng bộ cho mỗi request đến Elasticsearch. Thay vì trả về entity trực tiếp, các API reactive trả về `Mono<T>` hoặc `Flux<T>` của Project Reactor. Ứng dụng có thể nối các publisher để lưu document, tìm document vừa lưu, xử lý kết quả rồi xóa document mà không cần gọi `block()` giữa các bước.

Một chuỗi reactive đúng cần bảo đảm ba điều:

1. Các bước phụ thuộc nhau được nối bằng operator phù hợp, để bước sau chỉ chạy khi bước trước hoàn tất.
2. Publisher được trả về cho tầng gọi để framework quản lý subscription; service không tự `subscribe()` và không chặn thread bằng `block()`.
3. Hiểu rõ semantics của từng thao tác. Chẳng hạn, `save()` hoàn tất không đồng nghĩa document đã searchable ngay; Search API vẫn chịu ảnh hưởng của refresh.

Ví dụ một luồng nghiệp vụ:

```text
HTTP request
    |
    v
repository.save(product)          Mono<Product>
    |
    | flatMap(saved -> ...)
    v
repository.findBySku(saved.sku)   Mono<Product> (search query)
    |
    | flatMap(found -> ...)
    v
repository.delete(found)          Mono<Void>
    |
    | thenReturn(saved)
    v
Mono<Product> trả về WebFlux
```

Toàn bộ luồng được mô tả thành một publisher. Khi có subscription, Reactor điều phối các thao tác theo quan hệ phụ thuộc và phát tín hiệu hoàn tất hoặc lỗi.

## 1. Reactive trong Spring Data Elasticsearch

Spring Data Elasticsearch có hai nhóm API chính:

- API imperative như `ElasticsearchOperations` và `ElasticsearchRepository`, thường trả entity, `List`, `Page` hoặc kết quả đồng bộ.
- API reactive như `ReactiveElasticsearchOperations` và `ReactiveElasticsearchRepository`, trả `Mono` hoặc `Flux`.

API reactive phù hợp với ứng dụng Spring WebFlux hoặc hệ thống đã sử dụng Reactor xuyên suốt. Nó giúp thread xử lý request không phải ngồi chờ I/O Elasticsearch hoàn tất.

Reactive không chỉ là đổi kiểu trả về từ `Product` thành `Mono<Product>`. Để giữ được lợi ích non-blocking, toàn bộ đường đi phải sử dụng client và thao tác không chặn. Nếu bên trong chain gọi JDBC blocking, `Thread.sleep`, imperative repository hoặc `.block()`, thread vẫn có thể bị chặn.

### 1.1. `Mono` và `Flux`

| Kiểu | Số phần tử | Ví dụ |
|---|---|---|
| `Mono<T>` | 0 hoặc 1 phần tử, sau đó complete hoặc error. | Lưu một sản phẩm, lấy theo ID, xóa một document. |
| `Flux<T>` | 0 đến nhiều phần tử, sau đó complete hoặc error. | Tìm danh sách sản phẩm, stream các hit, lưu nhiều entity. |

Ví dụ:

```java
Mono<Product> saved = repository.save(product);

Mono<Product> byId = repository.findById("P-100");

Flux<Product> activeProducts = repository.findByStatus("ACTIVE");
```

Các biến trên chỉ giữ publisher. Chúng chưa nhất thiết đã gửi request đến Elasticsearch. Reactive publisher thường lazy: thao tác được thực thi khi có subscriber yêu cầu dữ liệu.

### 1.2. Publisher là mô tả công việc

Đoạn code:

```java
Mono<Product> result = repository.save(product);
```

không có nghĩa request đã chắc chắn được gửi ngay tại dòng này. Nó tạo một publisher mô tả thao tác lưu. Khi một WebFlux handler trả publisher cho framework hoặc khi test subscribe, quá trình thực thi mới diễn ra.

Nếu tạo publisher rồi bỏ đi mà không có subscriber, thao tác có thể không được thực hiện:

```java
repository.save(product); // Không dùng kết quả và không subscribe: không tạo workflow hoàn chỉnh.
```

Hãy nối publisher vào luồng trả về hoặc để framework subscribe ở ranh giới phù hợp.

## 2. Khai báo entity và reactive repository

Ví dụ entity sản phẩm:

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

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters, setters
}
```

Khai báo repository reactive:

```java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByStatus(String status);
}
```

Repository kế thừa các thao tác CRUD reactive:

- `save(entity)` trả `Mono<S>`.
- `findById(id)` trả `Mono<T>`.
- `findAll()` trả `Flux<T>`.
- `delete(entity)` trả `Mono<Void>`.
- `deleteById(id)` trả `Mono<Void>`.
- `saveAll(Publisher<S>)` trả `Flux<S>`.

Các method dẫn xuất như `findBySku` và `findByStatus` được Spring Data chuyển thành truy vấn tìm kiếm theo property. Chúng có semantics của Search API, không phải Get API theo `_id`.

## 3. Lưu một document không chặn

Lưu một entity bằng reactive repository:

```java
public Mono<Product> create(Product product) {
    return repository.save(product);
}
```

Hoặc qua `ReactiveElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import reactor.core.publisher.Mono;

public Mono<Product> create(Product product) {
    return operations.save(product);
}
```

Hai cách đều trả publisher. Service không cần tạo thread riêng hoặc gọi `subscribe()` để bắt đầu lưu.

Nếu cần thay đổi entity trước khi trả kết quả, dùng `map`:

```java
public Mono<ProductResponse> create(Product product) {
    return repository.save(product)
            .map(saved -> new ProductResponse(
                    saved.getId(),
                    saved.getSku(),
                    saved.getName()
            ));
}
```

`map` dùng cho phép biến đổi đồng bộ từ giá trị sang giá trị. Nếu bước tiếp theo trả về một `Mono` hoặc `Flux`, dùng `flatMap` để nối publisher, tránh tạo cấu trúc lồng như `Mono<Mono<T>>`.

## 4. Tìm kiếm bằng reactive repository

Method dẫn xuất trả về `Flux` khi có thể có nhiều kết quả:

```java
public Flux<Product> findActiveProducts() {
    return repository.findByStatus("ACTIVE");
}
```

Nếu query có thể trả tối đa một kết quả, dùng `Mono`:

```java
public Mono<Product> findBySku(String sku) {
    return repository.findBySku(sku);
}
```

Với một giá trị định danh `_id`, dùng `findById`:

```java
public Mono<Product> findById(String id) {
    return repository.findById(id);
}
```

Phân biệt hai cách đọc:

| Method | Kiểu đọc | Đặc điểm |
|---|---|---|
| `findById(id)` | Get theo ID | Real-time theo mặc định của Elasticsearch. |
| `findBySku(sku)` | Derived search query | Near-real-time, phụ thuộc refresh để thấy write mới. |
| `findByStatus(status)` | Derived search query | Near-real-time, có thể trả nhiều kết quả. |

Nếu vừa lưu một sản phẩm rồi gọi `findBySku` ngay, query có thể chưa thấy sản phẩm do index chưa refresh. Nối hai publisher bằng `flatMap` chỉ đảm bảo thứ tự thực thi; nó không tự ép refresh.

## 5. Tìm kiếm bằng `ReactiveElasticsearchOperations`

Khi cần CriteriaQuery hoặc native query phức tạp hơn method dẫn xuất, dùng `ReactiveElasticsearchOperations`.

Ví dụ CriteriaQuery:

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<SearchHit<Product>> searchActiveProducts() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    return operations.search(query, Product.class);
}
```

`search` trả `Flux<SearchHit<Product>>`; mỗi `SearchHit` chứa entity và metadata như ID, score, sort values. Nếu chỉ cần entity:

```java
public Flux<Product> searchActiveProductContents() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    return operations.search(query, Product.class)
            .map(SearchHit::getContent);
}
```

Khi cần metadata tổng hợp trong một object `SearchHits`, có thể dùng API `searchForHits` trả về `Mono<SearchHits<T>>` ở các phiên bản Spring Data Elasticsearch hỗ trợ:

```java
Mono<SearchHits<Product>> searchHits =
        operations.searchForHits(query, Product.class);
```

`SearchHits` chứa danh sách kết quả đã gom lại. Nếu cần xử lý dữ liệu lớn theo luồng, ưu tiên `Flux<SearchHit<T>>` thay vì gom tất cả vào một object.

## 6. Xóa document không chặn

Xóa theo ID:

```java
public Mono<Void> deleteById(String id) {
    return repository.deleteById(id);
}
```

Xóa entity:

```java
public Mono<Void> delete(Product product) {
    return repository.delete(product);
}
```

Reactive `delete` thường trả `Mono<Void>`: publisher báo complete khi thao tác hoàn tất, không phát ra entity đã xóa.

Nếu cần trả thông tin sau khi xóa, có thể dùng `thenReturn`:

```java
public Mono<String> deleteAndReturnId(String id) {
    return repository.deleteById(id)
            .thenReturn(id);
}
```

`thenReturn(id)` chỉ phát ID sau khi thao tác delete complete. Nếu delete phát error, `thenReturn` không chạy.

## 7. Nối `save → search → delete` thành một chuỗi reactive

Đây là mẫu trung tâm của bài học. Giả sử SKU là duy nhất và yêu cầu nghiệp vụ là:

1. Lưu sản phẩm.
2. Tìm lại sản phẩm bằng SKU qua một derived search query.
3. Xóa sản phẩm vừa tìm được.
4. Trả lại entity đã lưu như kết quả workflow.

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductWorkflowService {

    private final ProductRepository repository;

    public ProductWorkflowService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> saveSearchAndDelete(Product input) {
        return repository.save(input)
                .flatMap(saved -> repository.findBySku(saved.getSku())
                        .switchIfEmpty(Mono.error(
                                new IllegalStateException(
                                        "Saved product was not found by SKU")))
                        .flatMap(found -> repository.delete(found)
                                .thenReturn(saved)));
    }
}
```

Đọc chuỗi theo từng bước:

- `repository.save(input)` trả `Mono<Product>`.
- `flatMap(saved -> ...)` đợi publisher lưu phát ra entity rồi mới tạo publisher kế tiếp.
- `findBySku(saved.getSku())` thực hiện derived search query.
- `switchIfEmpty(...)` biến trường hợp search không có kết quả thành lỗi nghiệp vụ rõ ràng.
- `flatMap(found -> repository.delete(found)...)` chỉ xóa sau khi đã tìm thấy document.
- `thenReturn(saved)` phát entity đã lưu sau khi delete hoàn tất.

Phương thức trả về `Mono<Product>`, không tự subscribe và không block. Nếu search không thấy document hoặc delete lỗi, publisher kết thúc bằng error.

### 7.1. Cảnh báo về refresh trong chuỗi trên

Chuỗi operator bảo đảm thứ tự: save hoàn tất trước khi search bắt đầu. Tuy nhiên, `findBySku` là Search API và Search API near-real-time. Nếu index chưa refresh, bước search có thể không tìm thấy sản phẩm vừa lưu.

Nếu nghiệp vụ thật sự cần search ngay sau save, có thể yêu cầu refresh một cách tường minh:

```java
public Mono<Product> saveRefreshSearchAndDelete(Product input) {
    return repository.save(input)
            .flatMap(saved -> operations.indexOps(Product.class)
                    .refresh()
                    .thenReturn(saved))
            .flatMap(saved -> repository.findBySku(saved.getSku())
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("Product not searchable")))
                    .flatMap(found -> repository.delete(found)
                            .thenReturn(saved)));
}
```

`ReactiveIndexOperations.refresh()` trả publisher hoàn tất khi refresh kết thúc. `thenReturn(saved)` chỉ chuyển sang bước search sau refresh. Refresh cả index có chi phí, vì vậy không nên thêm vào mọi request nếu ứng dụng chấp nhận near-real-time. Một lựa chọn khác là cấu hình write refresh policy `WAIT_UNTIL` cho luồng cần read-after-write qua search, tùy phiên bản và cấu hình Spring Data Elasticsearch.

Nếu chỉ cần đọc document vừa lưu theo ID, dùng `findById(saved.getId())` thường phù hợp hơn và không cần refresh chỉ để GET thấy document.

## 8. Operator nào dùng cho bước nào?

Các operator Reactor quan trọng khi nối CRUD:

| Operator | Dùng khi | Ví dụ |
|---|---|---|
| `map` | Chuyển đổi đồng bộ một giá trị. | `Product` → `ProductResponse`. |
| `flatMap` | Bước tiếp theo trả về publisher; cho phép các inner publisher chạy không tuần tự khi xử lý nhiều phần tử. | Save xong mới gọi find. |
| `concatMap` | Xử lý từng phần tử theo thứ tự, đợi inner publisher trước complete. | Search nhiều sản phẩm rồi xóa tuần tự. |
| `flatMapSequential` | Chạy inner publisher có thể đồng thời nhưng phát kết quả theo thứ tự nguồn. | Map nhiều record song song nhưng giữ thứ tự output. |
| `then` | Chờ publisher trước complete rồi chạy publisher sau, bỏ qua giá trị trước. | Save xong mới refresh. |
| `thenReturn` | Chờ complete rồi phát một giá trị cố định. | Delete xong trả ID. |
| `thenMany` | Chờ `Mono`/publisher trước complete rồi bắt đầu `Flux` tiếp theo. | Save xong mới stream kết quả search. |
| `switchIfEmpty` | Cung cấp publisher thay thế khi upstream complete mà không có phần tử. | Không tìm thấy SKU thì báo lỗi. |
| `zip` | Kết hợp kết quả từ các publisher độc lập. | Lấy hai thống kê không phụ thuộc nhau. |
| `onErrorResume` | Chuyển lỗi thành publisher thay thế. | Map lỗi thành response/domain error. |
| `retryWhen` | Retry theo chính sách khi lỗi phù hợp. | Retry lỗi tạm thời có giới hạn. |

### 8.1. `map` và `flatMap`

Sai kiểu khi dùng `map` để trả publisher:

```java
Mono<Mono<Product>> nested = repository.save(product)
        .map(saved -> repository.findById(saved.getId()));
```

Kết quả là `Mono<Mono<Product>>`, không phải `Mono<Product>`. Dùng `flatMap` để làm phẳng:

```java
Mono<Product> loaded = repository.save(product)
        .flatMap(saved -> repository.findById(saved.getId()));
```

### 8.2. `then` và `flatMap`

Nếu không cần giá trị của bước trước, dùng `then`:

```java
Mono<Void> saveThenDelete(String id, Product product) {
    return repository.save(product)
            .then(repository.deleteById(id));
}
```

`then` bỏ qua entity được save và chỉ quan tâm việc publisher đã complete. Nếu cần dùng entity đã lưu để tính ID, dùng `flatMap`.

### 8.3. `thenMany` cho search stream

Ví dụ lưu một sản phẩm, sau đó stream các sản phẩm cùng trạng thái:

```java
Flux<Product> saveThenSearch(Product product) {
    return repository.save(product)
            .thenMany(repository.findByStatus(product.getStatus()));
}
```

Search chỉ bắt đầu sau khi save complete. Nhưng như đã nêu, việc này không tự bảo đảm search nhìn thấy write vừa lưu; cần refresh nếu use case yêu cầu.

## 9. Xử lý nhiều kết quả và xóa tuần tự

Giả sử cần tìm các sản phẩm đã ngừng bán rồi xóa chúng. Repository trả `Flux<Product>`:

```java
public Mono<Void> deleteDiscontinuedProducts() {
    return repository.findByStatus("DISCONTINUED")
            .concatMap(repository::delete)
            .then();
}
```

`concatMap` xử lý từng sản phẩm theo thứ tự: delete item hiện tại complete rồi mới xử lý item kế tiếp. `.then()` bỏ các giá trị trung gian và chỉ trả `Mono<Void>` khi toàn bộ luồng hoàn tất.

Nếu không yêu cầu thứ tự và muốn cho phép một số thao tác chạy đồng thời có giới hạn:

```java
public Mono<Void> deleteDiscontinuedProducts() {
    return repository.findByStatus("DISCONTINUED")
            .flatMap(repository::delete, 4)
            .then();
}
```

Tham số `4` giới hạn số inner publisher đang được subscribe đồng thời. Đây là ví dụ concurrency nhỏ; giá trị phù hợp phụ thuộc tải cluster và yêu cầu ứng dụng.

Không dùng `flatMap` không giới hạn cho một Flux rất lớn nếu mỗi phần tử tạo một request Elasticsearch. Có thể tạo quá nhiều request cùng lúc, gây áp lực connection pool, thread, cluster và memory.

## 10. Backpressure khi đọc và ghi nhiều document

`Flux` hỗ trợ backpressure: downstream có thể yêu cầu dữ liệu theo demand. Khi nối các publisher reactive đúng cách, hệ thống có cơ hội điều tiết tốc độ đọc và xử lý thay vì luôn đẩy toàn bộ dữ liệu vào bộ nhớ.

Ví dụ giới hạn số phần tử xử lý trong một luồng:

```java
Flux<Product> limited = repository.findAll()
        .limitRate(100);
```

`limitRate` điều chỉnh cách Reactor yêu cầu dữ liệu upstream; nó không phải giới hạn tổng số document trong index. Nếu chỉ cần tối đa 100 kết quả, dùng `take(100)`:

```java
Flux<Product> firstHundred = repository.findByStatus("ACTIVE")
        .take(100);
```

### 10.1. Lưu một luồng entity

Reactive repository hỗ trợ `saveAll(Publisher<S>)`:

```java
Flux<Product> source = productSource.readProducts();

Flux<Product> saved = repository.saveAll(source);
```

Đây là cách biểu diễn luồng save reactive. Tuy nhiên, `saveAll(Publisher)` không nên mặc định được hiểu là một Bulk API request duy nhất. Semantics triển khai và cách chia request phụ thuộc phiên bản Spring Data/client. Nếu yêu cầu bulk request cụ thể, hãy dùng API bulk phù hợp và kiểm soát batch size riêng.

### 10.2. Buffer theo batch

Khi cần xử lý theo nhóm nhỏ:

```java
Flux<List<Product>> batches = source.buffer(500);
```

Sau đó xử lý từng batch tuần tự:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .concatMap(batch -> repository.saveAll(batch).then())
            .then();
}
```

Đoạn code thể hiện buffer có giới hạn 500 phần tử và chỉ chuyển sang batch kế tiếp sau khi batch hiện tại complete. Với nguồn rất lớn, cần đảm bảo source thực sự streaming; không tạo `List` chứa toàn bộ dữ liệu trước khi gọi `buffer`.

### 10.3. Giới hạn concurrency khi import

Nếu muốn xử lý một số batch đồng thời:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .flatMap(batch -> repository.saveAll(batch).then(), 2)
            .then();
}
```

Ví dụ giới hạn tối đa hai batch đang chạy. Tăng concurrency có thể tăng throughput đến một mức, nhưng cũng làm tăng bộ nhớ và áp lực lên Elasticsearch. Hãy benchmark và theo dõi lỗi 429/latency.

## 11. Xử lý trường hợp không tìm thấy

`Mono` có thể complete mà không phát phần tử. Với `findById` hoặc query trả tối đa một document, cần xác định nghiệp vụ khi không có kết quả.

Trả 404 ở WebFlux controller có thể được xử lý bằng `switchIfEmpty`:

```java
public Mono<Product> getRequired(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)));
}
```

Hoặc trả một giá trị mặc định:

```java
public Mono<Product> findOrDefault(String sku) {
    return repository.findBySku(sku)
            .switchIfEmpty(Mono.just(Product.notFoundPlaceholder()));
}
```

Chỉ dùng default khi domain cho phép. Với các thao tác cập nhật/xóa, thường nên phân biệt rõ không tìm thấy với thành công.

Không dùng `defaultIfEmpty(null)` vì Reactor không cho phát `null` như một phần tử. Hãy dùng `switchIfEmpty`, `Mono.empty()` hoặc một kiểu kết quả biểu diễn rõ ràng.

## 12. Xử lý lỗi trong chuỗi reactive

Lỗi từ một thao tác trong chain thường truyền xuống downstream và kết thúc luồng, trừ khi được xử lý bằng operator phù hợp.

Ví dụ chuyển lỗi hạ tầng thành domain exception:

```java
public Mono<Product> create(Product product) {
    return repository.save(product)
            .onErrorMap(error ->
                    new ProductPersistenceException(
                            "Could not save product", error));
}
```

### 12.1. `onErrorResume`

`onErrorResume` thay publisher lỗi bằng một publisher khác:

```java
public Mono<Product> findOrCreate(String sku) {
    return repository.findBySku(sku)
            .switchIfEmpty(Mono.defer(() -> repository.save(newProduct(sku))))
            .onErrorResume(TemporaryElasticsearchException.class,
                    error -> fallbackLookup(sku));
}
```

Chỉ dùng fallback khi kết quả thay thế có ý nghĩa nghiệp vụ. Không nên bắt mọi exception rồi trả `Mono.empty()` vì lỗi thật có thể bị che giấu như trường hợp không có dữ liệu.

### 12.2. `retryWhen`

Có thể retry lỗi tạm thời với giới hạn và backoff:

```java
import java.time.Duration;
import reactor.util.retry.Retry;

public Mono<Product> findByIdWithRetry(String id) {
    return repository.findById(id)
            .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .filter(this::isTransientFailure));
}
```

Ví dụ chỉ retry khi `isTransientFailure` nhận diện lỗi tạm thời. Không retry lỗi validation, mapping, authorization hoặc lỗi nghiệp vụ không thể tự phục hồi.

Đặc biệt thận trọng khi retry thao tác ghi. Nếu Elasticsearch đã ghi document nhưng response bị mất do timeout, retry có thể gửi lại thao tác. Dùng ID ổn định và operation idempotent; với update cộng dồn hoặc script không idempotent, retry có thể áp dụng thay đổi nhiều lần.

### 12.3. Không lạm dụng `onErrorContinue`

`onErrorContinue` có thể làm một số lỗi bị bỏ qua và luồng tiếp tục, nhưng dễ làm mất ngữ cảnh item nào thất bại và khiến dữ liệu bị bỏ sót âm thầm. Với import hoặc thao tác nhiều document, nên phân loại lỗi theo từng item, ghi dead-letter/checkpoint rõ ràng và dùng operator có ngữ nghĩa dễ kiểm soát.

## 13. Reactive không đồng nghĩa với transaction

Một chuỗi:

```java
repository.save(product)
        .flatMap(saved -> repository.findBySku(saved.getSku()))
        .flatMap(repository::delete);
```

đảm bảo thứ tự phụ thuộc giữa các bước trong publisher. Nó không biến ba thao tác thành một transaction nguyên tử trên Elasticsearch.

Nếu save thành công nhưng search hoặc delete thất bại, document có thể vẫn tồn tại. Nếu delete thành công nhưng response bị mất, ứng dụng có thể không biết chính xác trạng thái cuối cùng.

Với workflow nhiều bước, cần thiết kế:

- Các thao tác có thể retry an toàn.
- ID ổn định và điều kiện version khi cập nhật.
- Trạng thái workflow/checkpoint nếu cần tiếp tục sau lỗi.
- Compensation nếu nghiệp vụ cần hoàn tác một bước đã thành công.
- Logging/metrics để quan sát bước nào hoàn tất.

Không giả định `flatMap` cung cấp rollback hoặc isolation như transaction trong cơ sở dữ liệu quan hệ.

## 14. Trả publisher từ WebFlux controller

Trong ứng dụng Spring WebFlux, controller có thể trả trực tiếp `Mono` hoặc `Flux`. WebFlux quản lý subscription và ghi response khi publisher phát dữ liệu.

Ví dụ controller:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductWorkflowService service;

    public ProductController(ProductWorkflowService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Product> create(@RequestBody Product product) {
        return service.create(product);
    }

    @GetMapping("/{id}")
    public Mono<Product> get(@PathVariable String id) {
        return service.getRequired(id);
    }

    @GetMapping
    public Flux<Product> findByStatus(@RequestParam String status) {
        return service.findByStatus(status);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> delete(@PathVariable String id) {
        return service.deleteById(id);
    }
}
```

Controller không gọi `.subscribe()` hoặc `.block()`. Nó trả publisher cho WebFlux runtime. Khi request đến, framework subscribe, quản lý tín hiệu và ghi kết quả ra HTTP response.

### 14.1. Khi nào mới cần `subscribe()`?

Trong một ứng dụng WebFlux thông thường, không tự subscribe trong service/controller. Nếu service viết:

```java
public void create(Product product) {
    repository.save(product).subscribe();
}
```

thì service trả về trước khi biết thao tác đã hoàn tất, lỗi không truyền về caller, và framework không thể điều phối lifecycle của thao tác như một phần request.

`subscribe()` phù hợp ở một số ranh giới chủ động quản lý background task, ví dụ một consumer hoặc scheduler tự sở hữu lifecycle, cancellation và error handling. Khi đó cần quản lý `Disposable`, shutdown và giám sát lỗi. Không dùng nó như cách thay thế cho việc trả publisher.

### 14.2. Vì sao không gọi `block()`?

Đoạn code sau làm mất lợi ích reactive:

```java
public Product createBlocking(Product product) {
    return repository.save(product).block();
}
```

`block()` chờ kết quả đồng bộ. Nếu được gọi trên event-loop thread của WebFlux, nó có thể gây starvation hoặc lỗi do blocking trong non-blocking thread. Hãy trả `Mono<Product>` và nối các bước bằng operator.

Nếu phải gọi một thư viện blocking không thể thay thế, hãy cô lập nó trên scheduler phù hợp như `Schedulers.boundedElastic()` và giới hạn tải. Không chuyển mọi thao tác Elasticsearch reactive sang scheduler chỉ vì một phần nhỏ của luồng là blocking.

## 15. Reactive search và read-after-write

Reactive không làm thay đổi consistency model của Elasticsearch. `ReactiveElasticsearchOperations.get` vẫn dùng Get API; `search` vẫn dùng Search API.

Ví dụ:

```java
public Mono<Product> saveThenGet(Product product) {
    return repository.save(product)
            .flatMap(saved -> repository.findById(saved.getId()));
}
```

Get theo ID có thể thấy document vừa lưu ngay vì Get API real-time theo mặc định.

Ngược lại:

```java
public Mono<Product> saveThenSearch(Product product) {
    return repository.save(product)
            .flatMap(saved -> repository.findBySku(saved.getSku()));
}
```

`findBySku` là search query. Nó có thể chưa thấy document nếu index chưa refresh.

Nếu cần search ngay, có thể refresh trong chuỗi reactive:

```java
public Mono<Product> saveRefreshThenSearch(Product product) {
    return repository.save(product)
            .flatMap(saved -> operations.indexOps(Product.class)
                    .refresh()
                    .thenReturn(saved))
            .flatMap(saved -> repository.findBySku(saved.getSku()));
}
```

Việc refresh trả về `Mono<Void>` nên vẫn nối được bằng `thenReturn`. Không cần `block()` để chờ refresh. Hãy dùng cách này khi yêu cầu search visibility thực sự cần; refresh quá thường xuyên làm giảm throughput.

## 16. Reactive delete và search visibility

Delete hoàn tất không đồng nghĩa một search query lập tức ngừng trả document. Search vẫn near-real-time và cần refresh để nhìn thấy trạng thái xóa.

Ví dụ:

```java
public Mono<Void> deleteAndRefresh(String id) {
    return repository.deleteById(id)
            .then(operations.indexOps(Product.class).refresh());
}
```

Publisher chỉ complete sau khi delete và refresh hoàn tất. Nếu chỉ cần xóa document theo ID, không cần refresh chỉ để Get API trả trạng thái mới; refresh chỉ cần khi yêu cầu các search query phản ánh delete ngay.

## 17. Kết hợp nhiều thao tác độc lập bằng `zip`

Nếu hai thao tác không phụ thuộc nhau, có thể chạy và kết hợp kết quả:

```java
public Mono<DashboardSummary> loadSummary() {
    Mono<Long> activeCount = operations.count(
            new CriteriaQuery(new Criteria("status").is("ACTIVE")),
            Product.class
    );

    Mono<Long> discontinuedCount = operations.count(
            new CriteriaQuery(new Criteria("status").is("DISCONTINUED")),
            Product.class
    );

    return Mono.zip(activeCount, discontinuedCount)
            .map(tuple -> new DashboardSummary(
                    tuple.getT1(),
                    tuple.getT2()
            ));
}
```

Hai count không phụ thuộc nhau nên có thể chạy đồng thời. Ngược lại, save rồi search document vừa lưu là quan hệ phụ thuộc; dùng `flatMap`/`then`, không dùng `zip` để mong bước sau chờ bước trước.

Tên method count và kiểu trả về cần tương thích với phiên bản `ReactiveElasticsearchOperations` của dự án; trong các phiên bản reactive hiện đại, count trả `Mono<Long>`.

## 18. Testing reactive chain với StepVerifier

Không nên kiểm thử reactive bằng cách gọi `.block()` trong test production code. Reactor cung cấp `StepVerifier` để subscribe và xác minh tín hiệu.

Ví dụ unit test với repository mock:

```java
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ProductWorkflowServiceTest {

    @Test
    void saveSearchAndDeleteInOrder() {
        Product input = new Product("P-100", "SKU-100", "Keyboard", "ACTIVE");
        Product saved = input;

        when(repository.save(input)).thenReturn(Mono.just(saved));
        when(repository.findBySku("SKU-100")).thenReturn(Mono.just(saved));
        when(repository.delete(saved)).thenReturn(Mono.empty());

        StepVerifier.create(service.saveSearchAndDelete(input))
                .expectNext(saved)
                .verifyComplete();

        verify(repository).save(input);
        verify(repository).findBySku("SKU-100");
        verify(repository).delete(saved);
    }
}
```

Đây là unit test minh họa operator flow. Mock không xác nhận được Elasticsearch refresh, mapping hay query DSL thực tế.

### 18.1. Kiểm thử trường hợp search rỗng

```java
when(repository.save(input)).thenReturn(Mono.just(saved));
when(repository.findBySku(saved.getSku())).thenReturn(Mono.empty());

StepVerifier.create(service.saveSearchAndDelete(input))
        .expectError(IllegalStateException.class)
        .verify();
```

Kiểm tra rằng delete không được gọi nếu search không tìm thấy document. Với mock, có thể dùng `verify(repository, never()).delete(any())`.

### 18.2. Integration test với Elasticsearch

Để xác nhận semantics thực tế, dùng Elasticsearch thật hoặc Testcontainers với phiên bản tương thích:

1. Tạo index và mapping cho entity.
2. Gọi reactive save.
3. Dùng `StepVerifier` xác nhận save hoàn tất.
4. Kiểm tra Get theo ID.
5. Thực hiện refresh có kiểm soát nếu test search cần thấy write ngay.
6. Chạy reactive search và xác nhận kết quả.
7. Gọi reactive delete và xác nhận completion.
8. Refresh nếu cần xác minh search không còn trả document.

Không dùng `Thread.sleep` để đợi refresh. Dùng refresh API hoặc write refresh policy `WAIT_UNTIL` khi test yêu cầu visibility.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Gọi `save()` nhưng document không được lưu | Publisher được tạo nhưng không có subscription hoặc không được nối vào response. | Trả publisher cho caller/framework hoặc quản lý subscription ở đúng boundary. |
| Service trả về trước khi thao tác xong | Gọi `subscribe()` nội bộ rồi bỏ publisher. | Trả `Mono`/`Flux` và để WebFlux quản lý subscription. |
| Event loop bị chặn | Gọi `.block()`, `Thread.sleep` hoặc thư viện blocking trong chain. | Dùng API reactive; cô lập thư viện blocking trên scheduler phù hợp nếu bắt buộc. |
| Kết quả có kiểu `Mono<Mono<T>>` | Dùng `map` để trả publisher. | Dùng `flatMap`. |
| Search ngay sau save không thấy document | Search API near-real-time; chưa refresh. | Dùng GET theo ID hoặc refresh/`WAIT_UNTIL` nếu cần search visibility. |
| Delete hoàn tất nhưng search vẫn thấy document | Delete chưa được refresh. | Refresh nếu cần search phản ánh delete ngay. |
| Chuỗi chạy sai thứ tự | Dùng các publisher độc lập hoặc `zip` cho bước phụ thuộc. | Dùng `flatMap`, `then`, `thenMany` để biểu diễn dependency. |
| Nhiều request Elasticsearch chạy đồng thời quá mức | `flatMap` không giới hạn trên Flux lớn. | Dùng concurrency limit, `concatMap` hoặc bounded queue. |
| Import vẫn dùng nhiều heap | Tải toàn bộ source vào `List` trước khi tạo Flux. | Dùng source streaming, `buffer` có giới hạn và backpressure. |
| Retry làm update bị áp dụng hai lần | Thao tác không idempotent hoặc response timeout sau khi server đã ghi. | Dùng ID/version ổn định và retry có chọn lọc. |
| Lỗi bị mất trong background job | `subscribe()` không có error handler hoặc Disposable lifecycle. | Trả publisher hoặc quản lý error/lifecycle của background task. |
| Test phụ thuộc timing | Dùng `Thread.sleep` để chờ refresh. | Dùng refresh API, `WAIT_UNTIL` và StepVerifier. |

## 20. Quy trình thiết kế một chuỗi CRUD reactive

1. **Xác định từng thao tác:** save, get, search hay delete; chọn repository method hoặc operations API tương ứng.
2. **Chọn kiểu publisher:** `Mono` cho 0/1 kết quả, `Flux` cho nhiều kết quả.
3. **Vẽ quan hệ phụ thuộc:** thao tác sau cần kết quả hoặc completion của thao tác trước không?
4. **Chọn operator:** `map` cho chuyển đổi đồng bộ, `flatMap` cho publisher phụ thuộc, `then` khi bỏ giá trị cũ, `concatMap` khi cần thứ tự.
5. **Xác định consistency:** GET real-time hay Search near-real-time; có cần refresh không?
6. **Xử lý empty:** quyết định not-found, default hoặc bỏ qua.
7. **Xử lý lỗi:** phân loại lỗi nghiệp vụ, lỗi dữ liệu và lỗi hạ tầng; retry có giới hạn.
8. **Kiểm soát tải:** dùng backpressure, batch size và concurrency limit.
9. **Trả publisher:** để WebFlux hoặc tầng gọi quản lý subscription; tránh `block()` và `subscribe()` trong service.
10. **Kiểm thử:** StepVerifier cho operator flow và integration test cho Elasticsearch behavior.

## 21. Những điểm cần nhớ

- Reactive Elasticsearch dùng `Mono` cho 0/1 kết quả và `Flux` cho 0/nhiều kết quả.
- `ReactiveElasticsearchRepository` và `ReactiveElasticsearchOperations` cung cấp API CRUD/search không chặn.
- Publisher thường lazy; tạo publisher chưa có nghĩa request đã chạy.
- Dùng `flatMap` khi bước tiếp theo trả publisher; dùng `map` cho phép biến đổi đồng bộ.
- Dùng `then`/`thenMany` khi chỉ cần chờ completion của bước trước; `thenReturn` phát giá trị sau khi hoàn tất.
- Dùng `concatMap` khi cần xử lý từng item tuần tự; giới hạn concurrency nếu dùng `flatMap` trên Flux lớn.
- `findById` là Get API; derived query như `findBySku` là Search API và có thể chịu refresh delay.
- Save rồi search trong cùng chain vẫn không tự ép refresh; refresh là quyết định riêng theo yêu cầu visibility.
- Reactive delete trả `Mono<Void>`; dùng `thenReturn` nếu cần phát kết quả sau khi xóa.
- `saveAll(Publisher)` là API reactive nhưng không mặc định đồng nghĩa một Bulk API request.
- Backpressure và batch giới hạn giúp tránh đẩy toàn bộ dữ liệu vào heap.
- Không gọi `.block()` hoặc tự `.subscribe()` trong service/controller WebFlux thông thường.
- Retry phải có điều kiện, backoff và thao tác idempotent; reactive chain không phải transaction.
- Dùng StepVerifier để kiểm tra tín hiệu và integration test để xác minh Elasticsearch behavior.

Chuỗi thao tác lưu, tìm kiếm và xóa không chặn được xây dựng bằng cách biểu diễn mỗi thao tác thành `Mono` hoặc `Flux`, sau đó nối chúng theo đúng quan hệ phụ thuộc. Khi giữ publisher xuyên suốt service và controller, kiểm soát backpressure, xử lý empty/error rõ ràng và hiểu refresh semantics của Search API, ứng dụng Spring Data Elasticsearch có thể thực hiện workflow reactive dễ đọc, không chặn và có khả năng vận hành ổn định.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch — Reactive repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/reactive-repositories.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Elasticsearch — Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html)
