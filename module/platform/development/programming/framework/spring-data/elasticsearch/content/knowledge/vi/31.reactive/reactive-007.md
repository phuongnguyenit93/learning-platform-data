# Truy vấn theo tên, @Query và NativeQuery trong luồng reactive

Một ứng dụng tìm kiếm sản phẩm có thể cần trả về nhiều kết quả theo tên, lọc thêm trạng thái đang bán, hoặc kết hợp tìm kiếm văn bản với điều kiện nghiệp vụ. Khi dùng Spring Data Elasticsearch theo mô hình reactive, các thao tác đọc trả về Publisher như **Mono** và **Flux**. Query vẫn được gửi tới Elasticsearch, nhưng kết quả được đưa vào một pipeline reactive để ứng dụng xử lý bất đồng bộ.

Có ba cách thường dùng để xây dựng truy vấn:

- **Derived query**: đặt tên method repository theo quy ước Spring Data, ví dụ tìm sản phẩm theo tên.
- **@Query**: khai báo Query DSL JSON ngay trên repository method khi cấu trúc query cần được viết rõ.
- **NativeQuery**: xây dựng query bằng API của Elasticsearch Java API Client rồi gọi qua **ReactiveElasticsearchOperations** khi cần linh hoạt hơn.

Bài học này trình bày cách tìm kiếm theo tên bằng repository reactive, viết truy vấn tùy chỉnh bằng @Query, xây dựng NativeQuery, đọc kết quả dưới dạng entity hoặc SearchHit, kết hợp phân trang và filter, đồng thời tổ chức pipeline reactive đúng cách.

## 1. Reactive query trong Spring Data Elasticsearch

Trong cách truy cập imperative, một method thường trả về entity hoặc collection sau khi lời gọi hoàn tất. Trong cách reactive, method trả về một Publisher mô tả thao tác sẽ thực hiện. Với Spring Data Elasticsearch, hai kiểu thường gặp là:

- **Mono<T>**: phát ra tối đa một phần tử rồi hoàn tất.
- **Flux<T>**: phát ra từ không đến nhiều phần tử rồi hoàn tất.

Ví dụ:

~~~java
Mono<Product> product = repository.findById("P-100");

Flux<Product> products = repository.findByName("Wireless Keyboard");
~~~

Khi gọi các method trên, ứng dụng nhận được Publisher. Query thường chỉ được thực thi khi có subscription. Publisher có thể được kết hợp với các toán tử Reactor trước khi subscribe.

Luồng tổng quát:

~~~text
Controller / Service
        |
        v
Reactive repository hoặc ReactiveElasticsearchOperations
        |
        v
Publisher: Mono / Flux
        |
        v
Elasticsearch reactive client
        |
        v
Elasticsearch query
        |
        v
Response và mapping entity
        |
        v
Các phần tử được phát trong reactive pipeline
        |
        v
Subscriber
~~~

Reactive không thay đổi ý nghĩa của Query DSL. Nó thay đổi cách ứng dụng nhận và xử lý kết quả, quản lý lỗi, cancellation và demand.

### Reactive không có nghĩa query tự động tìm toàn bộ index

Elasticsearch vẫn áp dụng giới hạn kết quả và phân trang của search request. Một method trả về Flux không có nghĩa request đó tự động lấy mọi document trong index. Nếu query không cấu hình kích thước hoặc cơ chế duyệt phù hợp, Elasticsearch vẫn áp dụng giới hạn mặc định.

Cần phân biệt:

- Flux là kiểu phát kết quả trong ứng dụng.
- Pageable/size là giới hạn của search request.
- Scroll hoặc cơ chế duyệt phù hợp là cách xử lý tập dữ liệu lớn theo nhiều lượt.

Không dùng Flux thay cho thiết kế phân trang hoặc export dữ liệu lớn.

## 2. Khai báo entity và reactive repository

Ví dụ entity Product:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @Field(type = FieldType.Double)
    private Double price;

    // constructors, getters and setters
}
~~~

Field **name** được mapping là text để hỗ trợ tìm kiếm toàn văn. **status** là keyword phù hợp với điều kiện chính xác hoặc filter. **active** là boolean.

Reactive repository:

~~~java
public interface ProductReactiveRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByName(String name);

    Flux<Product> findByNameAndActive(String name, boolean active);

    Mono<Product> findFirstByName(String name);
}
~~~

Spring Data tạo implementation cho các method theo quy tắc đặt tên. Không cần tự viết implementation cho các derived query được hỗ trợ.

### Chọn Mono hay Flux theo số kết quả

Dùng Flux khi query có thể trả nhiều sản phẩm. Dùng Mono khi kết quả mong đợi tối đa một sản phẩm, ví dụ tìm theo một khóa duy nhất hoặc method có giới hạn first/top.

Nếu query có thể khớp nhiều document mà nghiệp vụ lại dùng Mono, hãy kiểm tra semantics và xử lý trường hợp nhiều kết quả theo contract của method. Không chọn Mono chỉ vì caller muốn lấy phần tử đầu tiên.

### Derived query và semantics của field

Tên method mô tả điều kiện, nhưng loại query Spring Data sinh ra phụ thuộc từ khóa được hỗ trợ, mapping và phiên bản. Không nên mặc định mọi method tìm theo String đều có cùng semantics full-text relevance như một match query.

Với field text, nếu yêu cầu cụ thể là phân tích từ khóa theo analyzer, dùng match query rõ ràng bằng @Query hoặc NativeQuery. Với field keyword hoặc subfield keyword, dùng điều kiện exact phù hợp.

## 3. Tìm kiếm theo tên bằng derived query

Một repository method đơn giản:

~~~java
Flux<Product> findByName(String name);
~~~

Caller có thể kết hợp nó vào pipeline:

~~~java
public Flux<Product> findProducts(String name) {
    return repository.findByName(name);
}
~~~

Vì method trả Flux, service có thể lọc hoặc chuyển đổi kết quả bằng Reactor:

~~~java
public Flux<ProductSummary> findProductSummaries(String name) {
    return repository.findByName(name)
        .filter(Product::isActive)
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName(),
            product.getPrice()
        ));
}
~~~

Ví dụ này lọc active ở tầng ứng dụng sau khi kết quả đã được đọc. Nếu điều kiện active có thể được đẩy xuống Elasticsearch, nên đưa nó vào query để giảm số document truyền qua mạng và số entity phải mapping.

### Kết hợp điều kiện trong tên method

Ví dụ:

~~~java
Flux<Product> findByNameAndActive(String name, boolean active);

Flux<Product> findByStatusAndActive(String status, boolean active);
~~~

Derived query phù hợp khi điều kiện đơn giản, ổn định và được Spring Data hỗ trợ. Khi query cần nhiều nhánh bool, boost, nested, range hoặc điều kiện full-text rõ ràng, tên method dài sẽ khó biểu đạt. Khi đó, dùng @Query hoặc NativeQuery.

### Tìm theo tên chính xác và tìm theo nội dung

Có hai yêu cầu khác nhau:

- Tìm tên chính xác, ví dụ tên bằng đúng chuỗi Wireless Keyboard.
- Tìm nội dung có chứa các token Wireless và Keyboard theo analyzer.

Nếu name là text, match query thường phù hợp với tìm kiếm toàn văn. Nếu cần so khớp chính xác, mapping có thể định nghĩa multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Sau đó có thể dùng name cho full-text search và name.keyword cho exact filter hoặc sort. Chỉ dùng subfield keyword khi mapping thực tế đã tạo nó.

## 4. Khai báo @Query trên reactive repository

Annotation **@Query** cho phép khai báo JSON Query DSL trên repository method. Method vẫn trả về Mono hoặc Flux; annotation chỉ quyết định query được gửi tới Elasticsearch.

Ví dụ match theo tên:

~~~java
public interface ProductReactiveRepository
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
    Flux<Product> searchByName(String name);
}
~~~

Placeholder **?0** tham chiếu tham số đầu tiên của method. Nếu có nhiều tham số, thứ tự placeholder tương ứng vị trí tham số theo cơ chế binding của Spring Data.

Gọi method:

~~~java
Flux<Product> products =
    repository.searchByName("wireless keyboard");
~~~

Spring Data thực hiện binding tham số vào query và chuyển kết quả thành Publisher theo return type. Cú pháp placeholder và các kiểu tham số được hỗ trợ cần đối chiếu phiên bản Spring Data Elasticsearch của dự án.

### Kết hợp match với filter

Ví dụ chỉ tìm sản phẩm đang active:

~~~java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": {
                "query": "?0"
              }
            }
          }
        ],
        "filter": [
          {
            "term": {
              "active": true
            }
          }
        ]
      }
    }
    """)
Flux<Product> searchActiveByName(String name);
~~~

Trong query này:

- **must** chứa match query trên field name.
- **filter** giới hạn active bằng điều kiện boolean.
- Query match ảnh hưởng relevance score.
- Filter giới hạn document mà không cần tính điểm relevance cho điều kiện đó.

Đưa điều kiện có thể lọc ở Elasticsearch xuống query giúp giảm số hit mà ứng dụng phải nhận và xử lý.

### Exact match trên keyword subfield

Nếu muốn tên khớp chính xác theo keyword subfield:

~~~java
@Query("""
    {
      "term": {
        "name.keyword": "?0"
      }
    }
    """)
Flux<Product> findByExactName(String name);
~~~

Query này chỉ phù hợp nếu mapping thực sự có field name.keyword. Nếu field chỉ là text và không có subfield keyword, query sẽ không có semantics mong muốn.

### @Query phù hợp với query cố định

@Query hữu ích khi cấu trúc query tương đối ổn định nhưng không thể hoặc không muốn biểu đạt bằng derived method. Ví dụ:

- match hoặc multi_match trên một nhóm field.
- bool query với must, filter và must_not.
- range query kết hợp điều kiện text.
- nested query có path cố định.
- query có boost hoặc option cố định.

Nếu cấu trúc query thay đổi nhiều theo input runtime, NativeQuery thường dễ tổ chức hơn.

## 5. Tham số trong @Query và cách truyền dữ liệu

Placeholder trong @Query giúp thay tham số method vào query JSON:

~~~java
@Query("""
    {
      "match": {
        "name": {
          "query": "?0"
        }
      }
    }
    """)
Flux<Product> searchByName(String name);
~~~

Khi gọi:

~~~java
repository.searchByName("mechanical keyboard");
~~~

Giá trị tham số được binding theo cơ chế của Spring Data Elasticsearch. Không tự nối chuỗi người dùng vào JSON query để tạo query động bằng string concatenation.

Với nhiều tham số:

~~~java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": {
                "query": "?0"
              }
            }
          }
        ],
        "filter": [
          {
            "term": {
              "status": "?1"
            }
          }
        ]
      }
    }
    """)
Flux<Product> searchByNameAndStatus(String name, String status);
~~~

Placeholder đầu tiên ứng với name, placeholder thứ hai ứng với status.

### Query JSON có cấu trúc cố định

@Query không phải một bộ dựng Query DSL tổng quát. Cấu trúc JSON nằm trong annotation và các placeholder chỉ thay giá trị được hỗ trợ. Nếu muốn thêm hoặc bỏ nhánh query tùy điều kiện, tạo NativeQuery trong service sẽ rõ ràng hơn.

Không truyền nguyên một mảnh JSON tùy ý từ client vào placeholder để điều khiển cấu trúc query. API nên nhận các tham số nghiệp vụ có kiểu, validate chúng rồi xây dựng query ở server.

### Xử lý giá trị đặc biệt

Các chuỗi có dấu nháy, ký tự escape, khoảng trắng hoặc ký tự Unicode cần được binding đúng. Dùng cơ chế parameter binding của framework và kiểm thử các giá trị biên. Tránh tự escape bằng replace hoặc nối chuỗi vì dễ tạo JSON sai hoặc query có semantics ngoài ý muốn.

## 6. Dùng NativeQuery với ReactiveElasticsearchOperations

Khi cần xây query bằng Java thay vì viết JSON trong annotation, dùng **NativeQuery**. Đây là cách phù hợp cho query có nhiều nhánh, tham số runtime hoặc cần kết hợp nhiều loại query Elasticsearch.

Ví dụ inject reactive operations:

~~~java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Tạo query tìm tên bằng match:

~~~java
public Flux<Product> searchByName(String name) {
    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(name)
        ))
        .build();

    return operations.search(query, Product.class)
        .map(SearchHit::getContent);
}
~~~

Trong ví dụ:

- NativeQuery giữ query model được tạo bằng Elasticsearch Java API Client.
- ReactiveElasticsearchOperations thực thi query theo reactive API.
- search trả về Flux các SearchHit.
- map lấy entity content từ từng hit.

Package NativeQuery và kiểu builder phụ thuộc release train Spring Data Elasticsearch. Trong các phiên bản hiện đại, NativeQuery được đặt trong package client ELC và dùng query builder của Elasticsearch Java API Client. Đối chiếu dependency của dự án trước khi sao chép import.

### Kết hợp bool, match và filter

Ví dụ tìm tên và chỉ lấy sản phẩm active, có giá trong khoảng:

~~~java
public Flux<Product> searchActiveProducts(
        String name,
        double minPrice,
        double maxPrice) {

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
            .must(m -> m.match(mm -> mm
                .field("name")
                .query(name)
            ))
            .filter(f -> f.term(t -> t
                .field("active")
                .value(true)
            ))
            .filter(f -> f.range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(minPrice)
                    .lte(maxPrice)
                )
            ))
        ))
        .build();

    return operations.search(query, Product.class)
        .map(SearchHit::getContent);
}
~~~

Đây là ví dụ theo builder của Elasticsearch Java API Client hiện đại. Cấu trúc RangeQuery và overload có thể khác giữa các phiên bản client. Ý nghĩa query là match tên, filter active và filter price trong khoảng minPrice đến maxPrice.

### Vì sao dùng NativeQuery thay vì nối JSON?

NativeQuery có các lợi ích:

- Query được biểu diễn bằng kiểu Java của client.
- IDE hỗ trợ gợi ý API và compiler phát hiện một số lỗi cấu trúc.
- Dễ tạo nhánh query có điều kiện.
- Dễ tái sử dụng các phần query.
- Không phải tự escape chuỗi JSON.
- Vẫn sử dụng mapping và conversion của Spring Data qua ReactiveElasticsearchOperations.

NativeQuery không tự làm query reactive. Tính reactive đến từ việc gọi ReactiveElasticsearchOperations và giữ kết quả trong Mono/Flux.

## 7. Xây query động theo input

Giả sử API tìm kiếm cho phép người dùng truyền tên, trạng thái và khoảng giá tùy chọn. Có thể xây bool query chỉ thêm filter khi tham số có giá trị.

Pseudocode theo hướng tổ chức:

~~~java
public Flux<Product> search(ProductSearchCriteria criteria) {
    NativeQuery query = buildQuery(criteria);

    return operations.search(query, Product.class)
        .map(SearchHit::getContent);
}
~~~

Một builder riêng giúp tách logic tạo query:

~~~java
private NativeQuery buildQuery(ProductSearchCriteria criteria) {
    // Tạo bool query từ các điều kiện đã validate.
    // Thêm match name nếu có từ khóa.
    // Thêm term filter status nếu có trạng thái.
    // Thêm range filter khi có min/max price.
    // Thêm pageable/sort theo yêu cầu.
    // Trả về NativeQuery.
}
~~~

Đây là pseudocode cho cấu trúc service. Khi triển khai, tạo các Query object theo Java API Client builder của phiên bản đang dùng.

Validate input trước khi tạo query:

- Từ khóa không vượt giới hạn độ dài.
- minPrice không lớn hơn maxPrice.
- Status thuộc tập giá trị cho phép.
- Page number không âm.
- Page size nằm trong giới hạn.
- Sort field nằm trong allowlist của server.

Không cho client truyền tên field tùy ý rồi đưa trực tiếp vào Query DSL. Điều đó có thể làm API truy vấn các field nội bộ hoặc tạo workload không mong muốn.

## 8. Đọc SearchHit và SearchHits trong reactive flow

Có hai kiểu kết quả thường hữu ích:

**Flux<SearchHit<Product>>** giữ metadata của từng hit, như ID, score, sort values và highlight nếu query yêu cầu.

**Flux<Product>** chỉ giữ entity content sau khi map từ SearchHit.

Ví dụ giữ SearchHit:

~~~java
public Flux<SearchHit<Product>> searchHits(String name) {
    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(name)
        ))
        .build();

    return operations.search(query, Product.class);
}
~~~

Nếu chỉ cần entity:

~~~java
public Flux<Product> searchProducts(String name) {
    return searchHits(name)
        .map(SearchHit::getContent);
}
~~~

Giữ SearchHit khi cần:

- Score để hiển thị hoặc phân tích relevance.
- Highlight fragment để làm nổi bật từ khóa.
- Sort values để hỗ trợ cursor pagination.
- Document ID hoặc index metadata.
- Inner hits hoặc metadata khác mà request đã yêu cầu.

Không map sang entity quá sớm nếu tầng gọi vẫn cần metadata của hit.

### Lấy SearchHits có tổng số kết quả

Trong các API reactive hiện đại, ReactiveElasticsearchOperations cung cấp phương thức tìm kiếm theo trang có thể trả về Mono<SearchHits<T>>. Phương thức cụ thể và tên overload cần đối chiếu phiên bản đang dùng.

Ví dụ dạng sử dụng:

~~~java
Mono<SearchHits<Product>> searchPage(NativeQuery query) {
    return operations.searchForPage(query, Product.class);
}
~~~

SearchHits giữ danh sách SearchHit cùng thông tin như totalHits, maxScore và aggregation metadata tùy query. Nếu chỉ dùng Flux<SearchHit<T>>, caller nhận các hit được phát ra nhưng không nhất thiết có toàn bộ metadata tổng hợp theo cách thuận tiện như SearchHits.

## 9. Phân trang với NativeQuery

Elasticsearch search request thường giới hạn số hit trả về. Có thể cấu hình Pageable trong NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query(name)
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

PageRequest.of(0, 20) yêu cầu trang đầu với tối đa 20 kết quả. Trang tiếp theo dùng page index tăng lên.

Trong service, có thể nhận page và size từ API nhưng cần validate giới hạn trước khi tạo PageRequest:

~~~java
public Flux<SearchHit<Product>> search(
        String name,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        return Flux.error(
            new IllegalArgumentException("Invalid page request")
        );
    }

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(name)
        ))
        .withPageable(PageRequest.of(page, size))
        .build();

    return operations.search(query, Product.class);
}
~~~

Giới hạn size là quy tắc ứng dụng minh họa. Giá trị tối đa cần dựa trên SLA, cấu hình Elasticsearch và kích thước entity.

### Phân trang sâu

from/size có giới hạn và chi phí tăng khi page sâu. Với kết quả lớn, cân nhắc search_after kết hợp sort ổn định hoặc cơ chế scroll/PIT phù hợp với phiên bản Elasticsearch.

Khi dùng search_after:

- Query và sort phải nhất quán giữa các lần gọi.
- Sort nên có tie-breaker ổn định.
- Lưu toàn bộ sort values của hit cuối.
- Không tự tính lại sort values từ entity.
- Cần xử lý trường hợp index thay đổi trong lúc người dùng duyệt nếu yêu cầu snapshot nhất quán.

Reactive Publisher không tự giải quyết pagination sâu. Nó chỉ là cách tiêu thụ kết quả trong ứng dụng.

### Không phải lúc nào cũng cần Page<T>

Trong reactive repository, các kiểu Page<T> đồng bộ không phù hợp với mô hình phát kết quả bất đồng bộ như một giá trị duy nhất. Có thể dùng Flux<T> với Pageable, hoặc dùng API search trả SearchHits/Mono<SearchHits<T>> tùy nhu cầu metadata và phiên bản.

Nếu cần response gồm content, totalHits và page metadata, hãy thiết kế DTO rõ ràng từ kết quả search thay vì cố ép một kiểu Page imperative vào reactive pipeline.

## 10. Kết hợp sort với truy vấn theo tên

Có thể thêm sort vào NativeQuery để sắp xếp theo giá hoặc theo trường keyword. Ví dụ sort theo giá tăng dần cần field price có mapping numeric:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query(name)
    ))
    .withSort(s -> s.field(f -> f
        .field("price")
        .order(SortOrder.Asc)
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Cấu trúc sort builder phụ thuộc phiên bản Java API Client. Nếu sort theo tên, dùng keyword subfield thay vì text field không phù hợp với sort.

Sort có thể thay đổi ý nghĩa relevance. Nếu query match tên nhưng sort theo price, thứ tự kết quả được quyết định bởi price thay vì score. Nếu muốn relevance trước rồi giá sau, khai báo sort theo thứ tự đó.

Không nhận sort field trực tiếp từ người dùng nếu không có allowlist. Server nên ánh xạ các lựa chọn như priceAsc hoặc nameAsc sang field đã được cho phép.

## 11. Kết hợp highlight với reactive query

Nếu giao diện cần hiển thị từ khóa được đánh dấu, query có thể yêu cầu highlight. Khi dùng NativeQuery, cấu hình highlight bằng abstraction của Spring Data/Java API Client theo phiên bản hiện tại.

Kết quả nên giữ SearchHit:

~~~java
Flux<SearchHit<Product>> hits =
    operations.search(queryWithHighlight, Product.class);
~~~

Sau đó đọc entity và highlight fields:

~~~java
return hits.map(hit -> {
    Product product = hit.getContent();

    List<String> nameFragments =
        hit.getHighlightFields()
            .getOrDefault("name", List.of());

    return new ProductSearchItem(
        product.getId(),
        product.getName(),
        nameFragments
    );
});
~~~

Ví dụ DTO:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    List<String> nameHighlights
) {}
~~~

Không map SearchHit sang entity trước rồi bỏ metadata nếu API cần fragment. Đồng thời, highlight fragment có thể chứa markup; frontend phải render theo chính sách HTML an toàn của ứng dụng.

## 12. Reactive pipeline: map, flatMap và filter

Sau khi repository hoặc Operations phát kết quả, dùng toán tử Reactor để xử lý.

### map cho phép biến đổi đồng bộ

~~~java
Flux<ProductSummary> summaries =
    repository.findByName(name)
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName()
        ));
~~~

map phù hợp khi mỗi phần tử được biến đổi ngay trong cùng pipeline mà không cần gọi một Publisher khác.

### flatMap cho thao tác reactive tiếp theo

Giả sử cần lấy thông tin tồn kho từ một reactive service:

~~~java
Flux<ProductAvailability> results =
    repository.findByName(name)
        .flatMap(product ->
            inventoryService.findAvailability(product.getId())
                .map(stock -> new ProductAvailability(product, stock))
        );
~~~

flatMap kết hợp Publisher con vào một Flux kết quả. Nếu thứ tự đầu vào phải được giữ, xem xét concatMap hoặc API phù hợp thay vì mặc định flatMap.

### filter để loại kết quả ở ứng dụng

~~~java
Flux<Product> availableProducts =
    repository.findByName(name)
        .filter(Product::isActive);
~~~

Nếu active là điều kiện tìm kiếm quan trọng, tốt hơn là đưa nó vào Elasticsearch query để giảm dữ liệu truyền về. filter ở reactive pipeline phù hợp với điều kiện cần xử lý sau khi nhận entity hoặc điều kiện không thể biểu diễn trong query.

### switchIfEmpty cho trường hợp không có kết quả

~~~java
Mono<Product> findFeaturedProduct(String name) {
    return repository.findFirstByName(name)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(name)
        ));
}
~~~

Dùng switchIfEmpty khi nghiệp vụ cần chuyển trạng thái không có dữ liệu thành kết quả hoặc lỗi cụ thể.

## 13. Cold publisher, subscribe và block

Reactive repository thường trả về Publisher lazy. Nếu không có subscriber, thao tác có thể chưa được thực thi.

Ví dụ:

~~~java
Flux<Product> products = repository.findByName("keyboard");
~~~

Dòng này chỉ tạo Publisher. Khi framework web subscribe vào Publisher trả về từ controller, query mới được thực hiện.

Controller WebFlux có thể trả trực tiếp:

~~~java
@GetMapping("/products")
public Flux<Product> search(@RequestParam String name) {
    return searchService.search(name);
}
~~~

Không cần gọi subscribe trong controller hoặc service. Framework web quản lý subscription và ghi kết quả ra response.

### Tránh subscribe thủ công trong service

Không nên:

~~~java
public void search(String name) {
    repository.findByName(name)
        .subscribe(product -> log.info("Found {}", product.getId()));
}
~~~

Cách này tách công việc khỏi lifecycle của caller, khiến lỗi và cancellation khó được quản lý, đồng thời method void không cho biết khi nào thao tác hoàn tất.

Nên trả Publisher:

~~~java
public Flux<Product> search(String name) {
    return repository.findByName(name);
}
~~~

### Tránh block trong reactive request path

Không nên gọi block() để chờ kết quả trong một controller hoặc service đang chạy trên event loop. Block làm mất lợi ích non-blocking và có thể gây nghẽn hoặc deadlock tùy execution context.

Nếu cần tích hợp với thư viện imperative không có reactive API, cô lập phần blocking trên scheduler phù hợp và thiết kế boundary rõ ràng. Không biến toàn bộ pipeline thành đồng bộ chỉ để gọi một method blocking.

## 14. Error handling trong reactive query

Lỗi có thể xuất hiện khi tạo query, gửi request, mapping response hoặc xử lý trong toán tử downstream. Reactive pipeline truyền lỗi qua signal onError.

Ví dụ chuyển lỗi kỹ thuật thành lỗi ứng dụng:

~~~java
public Flux<Product> search(String name) {
    return repository.findByName(name)
        .onErrorMap(
            ElasticsearchException.class,
            ex -> new ProductSearchException(
                "Unable to search products",
                ex
            )
        );
}
~~~

Kiểu exception cụ thể phụ thuộc client và Spring Data version. Chọn exception phù hợp với dependency thực tế.

### Không biến mọi lỗi thành danh sách rỗng

Ví dụ dưới đây có thể che giấu lỗi hệ thống:

~~~java
return repository.findByName(name)
    .onErrorResume(ex -> Flux.empty());
~~~

Khi Elasticsearch mất kết nối hoặc query sai, caller sẽ nhận kết quả rỗng giống như không có sản phẩm. Điều đó khiến monitoring và nghiệp vụ khó phân biệt.

Chỉ dùng fallback empty khi đó thực sự là chính sách nghiệp vụ. Nếu không, giữ lỗi hoặc chuyển sang exception domain có ý nghĩa.

### Retry

Có thể retry lỗi tạm thời với chính sách giới hạn:

~~~java
return repository.findByName(name)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
    );
~~~

Không retry mọi exception. Lỗi mapping, query sai hoặc authentication thường không được giải quyết bằng gửi lại. Với search read-only, retry có thể phù hợp cho một số lỗi mạng hoặc quá tải; cần theo dõi retry để tránh khuếch đại tải khi cluster đang gặp sự cố.

### Logging và metric

Dùng doOnError, doOnNext hoặc instrumentation phù hợp để ghi nhận trạng thái. Các toán tử doOn... dành cho side effect quan sát, không nên dùng để thay đổi luồng dữ liệu hoặc thực hiện nghiệp vụ bắt buộc mà không xử lý lỗi.

Không log toàn bộ query params hoặc document nếu có dữ liệu nhạy cảm.

## 15. Cancellation và backpressure

Reactive Streams có cơ chế demand và cancellation. Khi client HTTP ngắt kết nối hoặc downstream không còn cần dữ liệu, subscription có thể bị cancel. Pipeline nên cho phép cancellation lan truyền về nguồn khi API hỗ trợ.

Một số điểm cần lưu ý:

- Không khởi tạo công việc phụ nằm ngoài Publisher rồi bỏ mặc khi subscriber cancel.
- Tránh subscribe lồng nhau không được quản lý.
- Giới hạn concurrency khi dùng flatMap.
- Không collectList cho tập kết quả rất lớn nếu không cần giữ toàn bộ trong memory.
- Dùng pagination hoặc stream/scroll API thích hợp cho tập dữ liệu lớn.
- Kiểm tra timeout ở client, server và web layer.

Backpressure không có nghĩa Elasticsearch chỉ gửi đúng một document mỗi lần downstream yêu cầu. Client có thể nhận một page hoặc response payload rồi phát các hit theo cơ chế riêng. Cần theo dõi kích thước page và bộ nhớ thực tế.

## 16. Khi nào dùng ReactiveElasticsearchRepository và khi nào dùng Operations?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Tìm theo một số field bằng tên method | ReactiveElasticsearchRepository |
| Query cố định cần viết rõ JSON DSL | Repository method với @Query |
| Query động có nhiều nhánh bool/filter/range | ReactiveElasticsearchOperations với NativeQuery |
| Cần giữ SearchHit metadata | ReactiveElasticsearchOperations.search |
| Cần SearchHits và total hit metadata | API search-for-page tương ứng của phiên bản |
| Cần kiểm soát request/response cấp thấp | Reactive client trực tiếp, có adapter riêng |
| CRUD reactive cơ bản | ReactiveElasticsearchRepository |

Repository thường là lựa chọn tốt cho truy vấn ổn định và đơn giản. Operations phù hợp khi service cần tự tạo query hoặc đọc metadata phong phú.

Không cần dùng NativeQuery cho mọi truy vấn. Cũng không nên ép query động phức tạp vào tên method hoặc annotation JSON quá dài.

## 17. Kiểm thử reactive query bằng StepVerifier

Với Reactor, **StepVerifier** giúp kiểm tra các signal được phát ra mà không cần block để lấy kết quả.

Ví dụ:

~~~java
@Test
void returnsProductsMatchingName() {
    StepVerifier.create(repository.findByName("keyboard"))
        .expectNextMatches(product ->
            product.getName().contains("keyboard")
        )
        .thenCancel()
        .verify();
}
~~~

Đây là minh họa kiểm tra Publisher. Dữ liệu test, phân biệt chữ hoa/thường và semantics query cần khớp mapping/analyzer của index.

Nếu muốn kiểm tra Publisher hoàn tất:

~~~java
StepVerifier.create(repository.findByName("no-such-product"))
    .verifyComplete();
~~~

### Kiểm thử @Query

Tạo document test có tên chứa các token tìm kiếm, gọi method @Query, rồi xác nhận kết quả khớp. Cần test cả trường hợp query không có kết quả và tham số có ký tự đặc biệt.

### Kiểm thử NativeQuery

Kiểm tra:

- Match query tìm đúng tên.
- Filter active loại document không phù hợp.
- Range price bao gồm/exclude biên đúng như yêu cầu.
- Pageable giới hạn đúng số hit.
- Sort đúng field và thứ tự.
- SearchHit giữ score/highlight/sort values khi query yêu cầu.
- Lỗi mapping hoặc Elasticsearch được truyền thành onError.
- Cancellation không để lại subscription phụ.

### Integration test với Elasticsearch

Unit test cho service có thể mock ReactiveElasticsearchOperations, nhưng nó không xác nhận Query DSL hoặc mapping thực tế. Nên có integration test với Elasticsearch version tương thích để kiểm tra derived query, @Query và NativeQuery.

Sau khi index dữ liệu test, chờ refresh hoặc dùng refresh policy phù hợp trước khi search. Tránh dựa vào timing ngẫu nhiên bằng sleep cố định nếu test framework có cách chờ trạng thái rõ ràng hơn.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Query không chạy dù đã gọi method | Publisher chưa được subscribe | Trả Publisher cho framework hoặc subscribe ở boundary phù hợp |
| Service trả Flux nhưng không có dữ liệu | Derived query semantics không đúng yêu cầu | Kiểm tra mapping và query thực tế |
| Tìm kiếm tên không phân tích token như mong đợi | Dùng exact/term semantics trên field không phù hợp | Dùng match trên text field |
| @Query báo JSON lỗi | Placeholder hoặc dấu nháy làm JSON không hợp lệ | Dùng parameter binding và kiểm tra query JSON |
| @Query không nhận đúng tham số | Placeholder sai vị trí hoặc kiểu không được hỗ trợ | Đối chiếu thứ tự và binding của phiên bản |
| NativeQuery compile lỗi | API Java Client thay đổi giữa release | Kiểm tra version và builder tương ứng |
| Flux chỉ trả một số hit | Query đang có page size/default size | Cấu hình Pageable hoặc cơ chế duyệt phù hợp |
| Mất score hoặc highlight | Map SearchHit sang entity quá sớm | Giữ SearchHit tới tầng cần metadata |
| Controller treo hoặc nghẽn | Gọi block hoặc subscribe thủ công | Trả Publisher và để framework quản lý |
| Lỗi Elasticsearch biến thành kết quả rỗng | onErrorResume chuyển mọi lỗi thành Flux.empty | Phân loại lỗi và giữ lỗi cần báo |
| Search chậm khi dùng flatMap | Concurrency quá lớn hoặc gọi service cho từng hit | Giới hạn concurrency hoặc batch enrichment |
| Test không thấy document vừa index | Chưa refresh | Chờ search visibility theo cách xác định |

## 19. Ví dụ service hoàn chỉnh cho tìm kiếm theo tên

Ví dụ service sử dụng NativeQuery để tìm tên, lọc active và giới hạn kết quả:

~~~java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Flux<ProductSearchItem> search(
            String name,
            int page,
            int size) {

        if (name == null || name.isBlank()) {
            return Flux.error(
                new IllegalArgumentException("name is required")
            );
        }

        if (page < 0 || size < 1 || size > 100) {
            return Flux.error(
                new IllegalArgumentException("Invalid pagination")
            );
        }

        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                    .field("name")
                    .query(name)
                ))
                .filter(f -> f.term(t -> t
                    .field("active")
                    .value(true)
                ))
            ))
            .withPageable(PageRequest.of(page, size))
            .build();

        return operations.search(query, Product.class)
            .map(hit -> new ProductSearchItem(
                hit.getId(),
                hit.getContent().getName(),
                hit.getScore()
            ));
    }
}
~~~

DTO:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    float score
) {}
~~~

Service giữ query construction và chuyển SearchHit sang DTO. Controller chỉ cần trả Flux:

~~~java
@GetMapping("/products/search")
public Flux<ProductSearchItem> search(
        @RequestParam String name,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    return productSearchService.search(name, page, size);
}
~~~

Các import và overload của NativeQuery builder phụ thuộc phiên bản Spring Data Elasticsearch/Java API Client. Hãy dùng đúng API của dependency dự án; cấu trúc ví dụ minh họa cách phối hợp reactive operations với query builder và DTO mapping.

## 20. Checklist chọn cách truy vấn reactive

- [ ] Repository kế thừa ReactiveElasticsearchRepository nếu cần CRUD/query method reactive.
- [ ] Method trả Mono khi tối đa một kết quả và Flux khi có thể nhiều kết quả.
- [ ] Derived query chỉ dùng cho toán tử được phiên bản hỗ trợ.
- [ ] Field name được mapping đúng text hoặc keyword theo yêu cầu tìm kiếm.
- [ ] Dùng match cho full-text search và term cho exact/filter semantics phù hợp.
- [ ] @Query có JSON DSL hợp lệ và placeholder đúng vị trí.
- [ ] Không nối trực tiếp input vào JSON query.
- [ ] Dùng NativeQuery khi cấu trúc query cần thay đổi theo runtime.
- [ ] Gọi NativeQuery qua ReactiveElasticsearchOperations để giữ reactive flow.
- [ ] Giữ SearchHit nếu cần score, highlight hoặc sort values.
- [ ] Cấu hình Pageable và giới hạn size rõ ràng.
- [ ] Không nhầm Flux với khả năng đọc không giới hạn toàn index.
- [ ] Không gọi subscribe hoặc block trong service/controller reactive.
- [ ] Phân loại lỗi trước khi retry hoặc fallback.
- [ ] Kiểm soát concurrency và bộ nhớ khi xử lý nhiều hit.
- [ ] Có StepVerifier test và integration test với Elasticsearch tương thích.

Derived query giúp viết nhanh các truy vấn đơn giản theo tên method. @Query phù hợp với Query DSL JSON có cấu trúc cố định và tham số được binding. NativeQuery cho phép xây query bằng Java API Client khi cần điều kiện động hoặc query phức tạp, trong khi ReactiveElasticsearchOperations giữ kết quả ở dạng Flux/SearchHit. Chọn đúng công cụ theo độ phức tạp query, giữ Publisher xuyên suốt service/controller và xử lý rõ phân trang, lỗi, cancellation giúp ứng dụng tìm kiếm bất đồng bộ mà vẫn kiểm soát được hành vi Elasticsearch.

