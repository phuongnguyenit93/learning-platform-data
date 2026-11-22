# Nhận diện giới hạn Repository và thời điểm chuyển sang Operations

Spring Data Elasticsearch cung cấp repository abstraction để ứng dụng thao tác với document bằng các phương thức Java quen thuộc. Với CRUD và truy vấn phổ biến, repository giúp code ngắn gọn, dễ đọc và ít phụ thuộc vào chi tiết Elasticsearch.

Tuy nhiên, repository không phải là API phù hợp cho mọi thao tác tìm kiếm. Khi cần điều khiển Query DSL phức tạp, chọn index hoặc alias tại thời điểm gọi, đọc aggregation, lấy metadata của hit, kết hợp nhiều loại điều kiện động hoặc thực hiện một quy trình Elasticsearch chuyên biệt, **ElasticsearchOperations** thường là lựa chọn phù hợp hơn.

Điều quan trọng là nhận ra ranh giới giữa hai abstraction. Repository mô tả cách ứng dụng truy cập dữ liệu theo mô hình domain; Operations cung cấp quyền kiểm soát chi tiết hơn đối với thao tác Elasticsearch. Có thể dùng cả hai trong cùng ứng dụng: repository cho đường đi thông thường và Operations cho những use case cần khả năng điều khiển sâu.

## 1. Repository giải quyết vấn đề gì?

Repository là abstraction của Spring Data giúp ứng dụng thao tác với một loại entity mà không phải tự quản lý request HTTP hay gọi Elasticsearch client ở từng service.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // constructors, getters, setters
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    Optional<Product> findByName(String name);
}
~~~

Service có thể dùng repository như một dependency thông thường:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> findByCategory(String category) {
        return repository.findByCategory(category);
    }
}
~~~

Spring Data tạo implementation cho repository trong lúc khởi động ứng dụng. Service chỉ cần biết kiểu entity, ID và các phương thức repository. Phần triển khai phía dưới sử dụng các thành phần Spring Data Elasticsearch để chuyển lời gọi thành thao tác phù hợp với Elasticsearch.

Repository thường là lựa chọn tốt khi:

- Use case là lưu, đọc, cập nhật hoặc xóa document.
- Điều kiện truy vấn đơn giản và có thể diễn đạt rõ bằng tên phương thức.
- Một query cố định có thể khai báo bằng **@Query**.
- Kiểu kết quả của repository đã chứa đủ dữ liệu mà service cần.
- Entity luôn dùng index hoặc alias mặc định được khai báo trong **@Document**.
- Service không cần điều khiển chi tiết request hoặc đọc các phần response đặc biệt.

Repository làm cho code nghiệp vụ dễ đọc hơn. Tên phương thức như **findByCategory** thể hiện ý định truy cập dữ liệu, trong khi service không cần biết HTTP endpoint hay cấu trúc request.

## 2. Những khả năng chính của Repository

### CRUD theo entity và ID

Các repository interface cung cấp các thao tác nền tảng như:

- **save(entity)** để lưu entity.
- **saveAll(entities)** để lưu nhiều entity.
- **findById(id)** để đọc theo document ID.
- **existsById(id)** để kiểm tra document.
- **findAll()** để đọc các entity.
- **deleteById(id)** và **delete(entity)** để xóa.
- **count()** để đếm theo phạm vi repository.

Các phương thức nền tảng giúp xử lý vòng đời document mà không cần tự tạo request. Cần nhớ rằng thao tác **findById** là đọc theo document ID; nó không tương đương với một full-text search.

### Derived query từ tên phương thức

Spring Data có thể phân tích tên phương thức và tạo query theo quy ước:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndPriceLessThan(
        String category,
        Double maxPrice
    );

    List<Product> findByPriceBetween(
        Double minPrice,
        Double maxPrice
    );

    List<Product> findByNameContaining(String phrase);

    long countByCategory(String category);

    boolean existsByCategory(String category);
}
~~~

Derived query phù hợp với điều kiện có cấu trúc đơn giản, ổn định và dễ hiểu từ tên phương thức. Khi tên phương thức bắt đầu dài, lồng nhiều điều kiện hoặc không còn thể hiện rõ ý nghĩa nghiệp vụ, đó là dấu hiệu nên xem xét cách biểu diễn query khác.

Không phải mọi keyword của Spring Data JPA đều có cùng semantics hoặc được hỗ trợ giống nhau trong Spring Data Elasticsearch. Cần kiểm tra danh sách query method được hỗ trợ trong phiên bản dự án, đặc biệt với các phép toán liên quan đến collection, null, nested field, geo hoặc full-text.

### Query khai báo bằng annotation

Với truy vấn cố định nhưng không thuận tiện biểu diễn bằng tên phương thức, có thể dùng **@Query**:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0",
              "operator": "and"
            }
          }
        }
        """)
    List<Product> searchName(String phrase);
}
~~~

Annotation giúp đặt Query DSL gần với repository method. Cách này hữu ích khi query không cần xây dựng động và kiểu kết quả vẫn đơn giản.

Nhưng query JSON trong annotation có các giới hạn thực tế:

- Query được gắn với một phương thức và khó tái sử dụng như một object query có thể kết hợp.
- Khi có nhiều nhánh điều kiện tùy chọn, JSON trở nên khó đọc và khó bảo trì.
- Các tham số động phức tạp có thể khó biểu diễn.
- Sort, aggregation, highlight, source filtering và các tùy chọn khác có thể làm annotation dài.
- Việc thay đổi query có thể yêu cầu sửa annotation và kiểm tra lại phương thức repository liên quan.

Nếu query đã có nhiều biến thể hoặc được lắp ghép theo input runtime, nên cân nhắc Operations và query builder.

### Phân trang và sắp xếp cơ bản

Repository hỗ trợ các kiểu trả về phân trang phù hợp với query method và phiên bản Spring Data:

~~~java
Page<Product> findByCategory(
    String category,
    Pageable pageable
);
~~~

Service có thể tạo trang và sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "price")
);

Page<Product> page =
    productRepository.findByCategory("accessories", pageable);
~~~

Cách này phù hợp khi cần phân trang thông thường và kết quả chỉ cần entity cùng thông tin trang. Tuy nhiên, nếu cần sort theo một field phức tạp, nhiều điều kiện sort đặc biệt, giá trị missing, script sort hoặc các tùy chọn Search API khác, Operations cho phép kiểm soát request rõ hơn.

Tên property dùng trong Sort phải phù hợp với mapping metadata và field thực tế. Với multi-field, có thể cần tham chiếu đường dẫn Elasticsearch như **name.keyword**. Khả năng ánh xạ sort property cụ thể nên được kiểm tra theo API và phiên bản Spring Data đang dùng.

## 3. Những giới hạn thường gặp của Repository

Repository cung cấp một abstraction có chủ đích. Nó bao phủ các thao tác phổ biến, nhưng không nhất thiết phơi bày mọi khả năng của Elasticsearch Search API.

### Giới hạn 1: Query động có nhiều nhánh điều kiện

Giả sử màn hình tìm kiếm sản phẩm có các bộ lọc tùy chọn:

- Từ khóa tên sản phẩm.
- Một hoặc nhiều category.
- Giá tối thiểu và tối đa.
- Trạng thái còn hàng.
- Danh sách thương hiệu.
- Khoảng thời gian cập nhật.
- Sort theo nhiều tiêu chí.
- Chỉ lấy một số field trong kết quả.

Nếu tạo một derived method cho từng tổ hợp, số phương thức sẽ tăng nhanh. Một phương thức có tên dài cũng khó thể hiện rõ điều kiện nào là bắt buộc và điều kiện nào chỉ xuất hiện khi người dùng nhập giá trị.

Operations cho phép tạo query theo từng input rồi kết hợp các điều kiện có mặt:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> {
            b.filter(f -> f.term(t -> t
                .field("available")
                .value(true)
            ));

            if (category != null && !category.isBlank()) {
                b.filter(f -> f.term(t -> t
                    .field("category")
                    .value(category)
                ));
            }

            if (keyword != null && !keyword.isBlank()) {
                b.must(m -> m.match(mm -> mm
                    .field("name")
                    .query(keyword)
                ));
            }

            return b;
        })
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Đây là ví dụ minh họa cách lắp ghép điều kiện; import và overload builder cụ thể phụ thuộc phiên bản Java API Client và Spring Data Elasticsearch. Điểm quan trọng là query được xây dựng từ input thực tế thay vì phải tạo một repository method cho mỗi tổ hợp.

Khi điều kiện quá phức tạp, nên tách phần xây dựng query thành một component riêng để service không chứa nhiều chi tiết Query DSL.

### Giới hạn 2: Query DSL chuyên biệt

Repository derived query phù hợp với các phép so khớp phổ biến. Khi cần Query DSL như:

- **bool** với nhiều nhánh **must**, **filter**, **should** và **must_not**.
- **nested** query.
- **function_score** hoặc query ảnh hưởng tới relevance.
- **geo_distance**, **geo_shape** và các query địa lý.
- **script** query hoặc script score.
- **match_phrase**, **multi_match** với cấu hình chi tiết.
- **terms_set**, **wildcard**, **regexp** hoặc các loại query chuyên biệt.
- Query kết hợp nhiều tầng và nhiều field.

Operations cùng **NativeQuery** thường biểu đạt trực tiếp hơn. Có thể xây dựng query bằng Elasticsearch Java API Client, sau đó gọi Operations để Spring Data vẫn đảm nhiệm mapping entity và chuyển đổi kết quả.

Không phải cứ thấy Query DSL là phải chuyển sang Operations. Một query cố định, ngắn và dễ hiểu vẫn có thể đặt trong **@Query**. Chuyển khi query cần composition, nhiều tham số, nhiều tùy chọn hoặc khi repository method trở nên khó bảo trì.

### Giới hạn 3: Aggregation và kết quả không phải danh sách entity

Repository method thường hướng tới trả về entity, danh sách hoặc page. Nhưng nhiều use case cần kết quả tổng hợp:

- Đếm sản phẩm theo category.
- Tính trung bình giá theo thương hiệu.
- Tạo histogram theo khoảng giá.
- Phân nhóm theo ngày hoặc tháng.
- Tính cardinality của một field.
- Kết hợp nhiều tầng aggregation.
- Trả về bucket và metric thay vì document.

Aggregation là một phần riêng của Search API response. Khi ứng dụng cần đọc bucket, metric hoặc pipeline aggregation, Operations phù hợp hơn vì có thể giữ và xử lý cấu trúc response đầy đủ.

Ví dụ request aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

Kết quả của request này không phải danh sách Product. Nó là tập bucket category cùng metric average_price. Cố gắng ép kết quả này vào một kiểu entity sẽ làm mất ý nghĩa của aggregation response.

### Giới hạn 4: Cần metadata của từng SearchHit

Một số use case không chỉ cần nội dung entity mà còn cần:

- Document ID.
- Score.
- Sort values.
- Highlight fragments.
- Inner hits.
- Metadata của toàn bộ search như total hits và relation.

Nếu repository trả về **List<Product>**, ứng dụng chỉ nhận danh sách entity. Kiểu trả về này không phải lựa chọn tốt khi service cần xử lý metadata của từng hit.

Operations có thể trả về **SearchHits<T>**:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    List<Object> sortValues = hit.getSortValues();
    Map<String, List<String>> highlights =
        hit.getHighlightFields();
}
~~~

Kiểu dữ liệu và method cụ thể của SearchHit có thể khác giữa các phiên bản. Chọn SearchHits khi metadata của Elasticsearch là một phần thực sự cần thiết trong kết quả nghiệp vụ.

### Giới hạn 5: Cần chọn index hoặc alias tại thời điểm gọi

Repository thường lấy index mặc định từ **@Document(indexName = "...")**. Điều này thuận tiện khi một entity luôn thao tác trên cùng index hoặc alias.

Nhưng một ứng dụng có thể cần:

- Đọc qua **products-read**.
- Ghi qua **products-write**.
- Tìm dữ liệu theo tenant-specific index.
- Chạy truy vấn trên một index lịch sử.
- So sánh kết quả giữa hai index trong quá trình migration.

Một repository gắn với index mặc định không tự phân biệt mọi tình huống trên. Operations cho phép truyền **IndexCoordinates** vào từng thao tác:

~~~java
SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products-read")
);

Product saved = operations.save(
    product,
    IndexCoordinates.of("products-write")
);
~~~

Cách này hữu ích khi tách read alias và write alias. Cần đảm bảo tên index/alias được kiểm soát từ cấu hình đáng tin cậy, đặc biệt nếu có tenant routing. Không nối trực tiếp tên index từ input tùy ý của người dùng.

### Giới hạn 6: Cần source filtering hoặc response shaping

Một số màn hình chỉ cần vài field của document. Search API có thể giới hạn _source để giảm lượng dữ liệu truyền về:

~~~http
POST /products/_search
{
  "_source": ["name", "category", "price"],
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

Operations cho phép cấu hình source filter và các tùy chọn request phù hợp với phiên bản. Repository có thể hỗ trợ một số kiểu projection hoặc annotation tùy release, nhưng khi cần kiểm soát chính xác source includes/excludes hoặc kết hợp với query đặc biệt, Operations thường rõ ràng hơn.

Cần phân biệt source filtering với DTO projection. Source filtering quyết định dữ liệu Elasticsearch trả về; projection quyết định ứng dụng biểu diễn dữ liệu thành kiểu Java nào. Chúng có thể được kết hợp nhưng không phải cùng một việc.

### Giới hạn 7: Cần highlight, collapse hoặc search option chuyên biệt

Search API có nhiều tính năng ngoài query và sort:

- Highlight để trả đoạn văn bản chứa từ khóa.
- Collapse để gom kết quả theo field.
- **search_after** để phân trang sâu.
- **track_total_hits** để điều khiển việc đếm total hits.
- Routing hoặc preference để định hướng search.
- Runtime mappings.
- Rescore hoặc các tùy chọn nâng cao khác.

Khi những tính năng này là một phần của use case, Operations cùng query builder thường biểu đạt tốt hơn một repository method.

## 4. ElasticsearchOperations là gì?

**ElasticsearchOperations** là abstraction cấp cao của Spring Data Elasticsearch cho các thao tác trên document và tìm kiếm. Nó cho phép ứng dụng tạo query, chọn entity type và index coordinates rồi thực hiện thao tác.

Một số nhóm thao tác thường dùng:

| Nhóm | Ví dụ |
|---|---|
| Tìm kiếm | search, searchSimilar tùy phiên bản |
| Đọc document | get, multiGet |
| Ghi document | save, bulkIndex hoặc bulk operation tương ứng |
| Xóa | delete |
| Tạo và quản lý index | Thông qua IndexOperations |
| Mapping/conversion | Dựa trên ElasticsearchConverter và metadata |
| Chọn index/alias | IndexCoordinates |

Implementation phổ biến trong các phiên bản hiện đại là **ElasticsearchTemplate**. Service nên phụ thuộc vào interface **ElasticsearchOperations** để giữ abstraction và thuận tiện cho kiểm thử.

Ví dụ inject Operations:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Operations không có nghĩa ứng dụng phải tự serialize JSON hoặc gọi HTTP. Spring Data vẫn có thể chuyển entity và kết quả thông qua converter, đồng thời sử dụng client đã được cấu hình.

## 5. Xây dựng query bằng Operations

### Dùng CriteriaQuery cho điều kiện đơn giản có tính động

Criteria API của Spring Data cung cấp cách xây dựng điều kiện mà không phải viết trực tiếp JSON:

~~~java
Criteria criteria = new Criteria("category").is("accessories")
    .and("price").between(20.0, 100.0);

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

CriteriaQuery hữu ích khi muốn tạo điều kiện theo cấu trúc đơn giản và kết hợp dần theo input. Nó vẫn là một abstraction của Spring Data, không nhất thiết biểu đạt được mọi tính năng của Elasticsearch Query DSL.

Nếu query yêu cầu chức năng đặc thù không có biểu diễn tương ứng trong Criteria API, hãy dùng **NativeQuery**.

### Dùng NativeQuery cho Query DSL

NativeQuery trong các phiên bản dùng Elasticsearch Java API Client cho phép xây dựng query bằng các builder có kiểu dữ liệu của client:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("mechanical keyboard")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("category")
                    .value("accessories")
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Query gồm hai phần:

- **must** dùng full-text match trên name.
- **filter** giới hạn category mà không cần tính relevance score cho điều kiện lọc.

PageRequest cung cấp thông tin phân trang. operations.search thực hiện truy vấn trên index mặc định lấy từ entity metadata, trừ khi truyền IndexCoordinates tường minh.

Import và API builder của NativeQuery thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Khi triển khai, cần dùng đúng dependency đang có trong dự án.

### Kết hợp sort

Có thể thêm sort vào query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("name")
            .query("keyboard")
        )
    )
    .withSort(s -> s
        .field(f -> f
            .field("price")
            .order(SortOrder.Asc)
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Ví dụ này tìm theo tên rồi sắp xếp giá tăng dần. Nếu sort theo một text property, cần dùng keyword subfield phù hợp như **name.keyword**; field mapping phải hỗ trợ sort.

### Đọc SearchHits và metadata

Kết quả của operations.search thường là **SearchHits<T>**:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

long totalHits = hits.getTotalHits();

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    System.out.println("id: " + hit.getId());
    System.out.println("score: " + hit.getScore());
    System.out.println("product: " + product.getName());
}
~~~

SearchHits<T> giữ danh sách hit và metadata tổng thể. Mỗi SearchHit<T> giữ entity cùng thông tin riêng của hit. Đây là khác biệt quan trọng khi service cần giải thích hoặc trình bày kết quả tìm kiếm.

Nếu chỉ cần entity, có thể chuyển danh sách hit thành danh sách content ở tầng service. Không nên bỏ metadata ngay từ đầu nếu API phía trên cần score, highlight hoặc sort values.

## 6. Aggregation là một dấu hiệu rõ ràng để dùng Operations

Một báo cáo thống kê thường trả về bucket và metric chứ không phải entity. Vì vậy, nên dùng Operations để thực hiện query aggregation và đọc phần aggregation response.

Ví dụ request:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation(
        "by_category",
        Aggregation.of(a -> a
            .terms(t -> t.field("category"))
            .aggregations(
                "average_price",
                Aggregation.of(avg -> avg
                    .avg(v -> v.field("price"))
                )
            )
        )
    )
    .withMaxResults(0)
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Đây là minh họa về cách gắn aggregation vào NativeQuery. Cấu trúc builder và cách lấy aggregation từ response phụ thuộc phiên bản API. Khi chỉ cần aggregation, có thể đặt số hit tối đa bằng 0 để response tập trung vào thống kê.

Với API Spring Data hiện hành, aggregation có thể được truy cập từ metadata search hoặc đối tượng kết quả tương ứng. Không nên giả định SearchHits<T> tự chuyển mọi bucket thành entity. Hãy đọc aggregation theo kiểu kết quả mà phiên bản đang dùng cung cấp.

### Khi nào nên tạo DTO cho aggregation?

Nếu service trả báo cáo cho controller, nên chuyển bucket và metric thành DTO riêng:

~~~java
public record CategorySummary(
    String category,
    long productCount,
    double averagePrice
) {}
~~~

DTO mô tả kết quả nghiệp vụ. Entity Product mô tả một document. Dùng hai kiểu khác nhau giúp tránh nhầm dữ liệu tổng hợp với document thật trong index.

## 7. Chọn Operations khi cần index/alias tường minh

Một use case phổ biến là đọc và ghi qua hai alias riêng.

Repository với **@Document(indexName = "products")** thường dùng cùng tên index/alias mặc định cho các thao tác. Khi read alias và write alias tách biệt, Operations cho phép chọn đích cụ thể:

~~~java
public class ProductStore {

    private final ElasticsearchOperations operations;

    public ProductStore(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-read")
        );
    }

    public Product save(Product product) {
        return operations.save(
            product,
            IndexCoordinates.of("products-write")
        );
    }
}
~~~

Cách tiếp cận này cũng phù hợp khi ứng dụng cần truy vấn một index lịch sử hoặc chạy kiểm tra dữ liệu trong giai đoạn migration.

Tên alias nên lấy từ cấu hình ứng dụng hoặc một cấu trúc định tuyến được kiểm soát. Không nhận tên index tùy ý từ request công khai rồi truyền thẳng vào IndexCoordinates.

## 8. Repository custom fragment: giữ API nghiệp vụ, dùng Operations bên dưới

Chuyển sang Operations không có nghĩa mọi service phải biết Query DSL. Nếu một truy vấn phức tạp là khả năng riêng của domain, có thể đóng gói nó trong custom repository fragment.

Ví dụ interface fragment:

~~~java
public interface ProductSearchRepository {
    SearchHits<Product> searchCatalog(ProductSearchCriteria criteria);
}
~~~

Repository chính kết hợp fragment:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
~~~

Implementation của fragment sử dụng Operations:

~~~java
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<Product> searchCatalog(
            ProductSearchCriteria criteria) {

        // Xây dựng CriteriaQuery hoặc NativeQuery từ criteria.
        // Thực hiện bằng ElasticsearchOperations.
        Query query = buildQuery(criteria);

        return operations.search(query, Product.class);
    }

    private Query buildQuery(ProductSearchCriteria criteria) {
        // Phần xây dựng query được đóng gói tại đây.
        return new CriteriaQuery(
            new Criteria("category").is(criteria.category())
        );
    }
}
~~~

Đây là cấu trúc minh họa. Tên implementation convention, constructor và cách cấu hình repository fragment cần khớp quy tắc Spring Data của phiên bản dự án.

Lợi ích:

- Service gọi một API theo ngôn ngữ nghiệp vụ như **searchCatalog**.
- Query DSL nằm trong adapter/repository fragment.
- Repository cơ sở vẫn cung cấp CRUD.
- Có thể kiểm thử riêng logic chuyển criteria thành query.
- Khi thay đổi query, service không phải biết chi tiết Elasticsearch.

Custom fragment là lựa chọn tốt khi query phức tạp nhưng vẫn thuộc trách nhiệm truy cập dữ liệu của repository domain. Nếu thao tác là một quy trình tìm kiếm chuyên biệt chỉ có một service sử dụng, một component search riêng phụ thuộc Operations cũng có thể hợp lý hơn.

## 9. Phân chia trách nhiệm giữa Service, Repository và Operations

Một cách tổ chức dễ bảo trì là phân chia theo trách nhiệm:

~~~text
Controller
    |
    v
Application Service
    |
    +---- ProductRepository
    |         |
    |         v
    |    CRUD / derived query / simple @Query
    |
    +---- ProductSearchService hoặc custom fragment
              |
              v
       ElasticsearchOperations
              |
              v
       Query builder / IndexCoordinates
              |
              v
       Elasticsearch Java API Client
~~~

Service chịu trách nhiệm điều phối use case và quy tắc nghiệp vụ. Repository cung cấp các thao tác dữ liệu phổ biến. Component dùng Operations xử lý những query cần kiểm soát chi tiết.

Không nên để controller tự xây Query DSL. Cũng không nên để service nghiệp vụ chứa quá nhiều builder callback nếu phần query có thể được đóng gói trong một class chuyên trách.

### Một service có thể dùng cả Repository và Operations

Ví dụ:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;
    private final ElasticsearchOperations operations;

    public ProductService(
            ProductRepository repository,
            ElasticsearchOperations operations) {
        this.repository = repository;
        this.operations = operations;
    }

    public Product create(Product product) {
        return repository.save(product);
    }

    public Optional<Product> get(String id) {
        return repository.findById(id);
    }

    public SearchHits<Product> advancedSearch(Query query) {
        return operations.search(query, Product.class);
    }
}
~~~

Đây là cách kết hợp hợp lệ khi service thực sự cần cả hai abstraction. Với dự án lớn, có thể tách advancedSearch thành một component riêng để service không phải chịu trách nhiệm xây dựng hoặc quản lý query.

## 10. So sánh Repository và Operations

| Tiêu chí | Repository | ElasticsearchOperations |
|---|---|---|
| CRUD thông thường | Rất phù hợp | Có thể thực hiện |
| Derived query | Có | Không phải mục đích chính |
| Query cố định bằng JSON | @Query | Có thể dùng query object |
| Query động nhiều nhánh | Có thể trở nên cồng kềnh | Phù hợp |
| Query DSL chuyên biệt | Giới hạn theo API repository | Kiểm soát tốt hơn |
| Aggregation | Tùy kiểu kết quả/API và phiên bản | Phù hợp |
| SearchHit metadata | Cần chọn return type phù hợp | Trả SearchHits<T> trực tiếp |
| Chọn index/alias từng lần gọi | Bị chi phối bởi entity/repository metadata | Có IndexCoordinates tường minh |
| Source filtering, highlight, search options | Tùy hỗ trợ của repository method | Kiểm soát request tốt hơn |
| Quản lý mapping/index | Không phải trách nhiệm chính | Thường dùng IndexOperations |
| Độ ngắn gọn của CRUD | Cao | Nhiều chi tiết hơn |
| Tái sử dụng query builder | Hạn chế nếu chỉ dùng method/annotation | Có thể đóng gói thành component |

Operations có khả năng điều khiển nhiều hơn, nhưng cũng yêu cầu code mô tả chi tiết hơn. Không nên chuyển mọi thao tác sang Operations chỉ vì API này tổng quát hơn.

## 11. Quy trình quyết định: giữ Repository hay chuyển sang Operations?

Có thể dùng các câu hỏi sau khi thiết kế một use case mới.

### Bước 1: Xác định kiểu kết quả

Nếu kết quả là một entity, một danh sách entity hoặc một page đơn giản, repository thường đáp ứng tốt.

Nếu kết quả là bucket aggregation, metric, highlight, score, sort values hoặc metadata chuyên biệt, hãy xem xét Operations.

### Bước 2: Đánh giá độ phức tạp query

Nếu query diễn đạt rõ bằng một derived method ngắn, giữ repository.

Nếu query cố định nhưng có DSL vừa phải, cân nhắc **@Query**.

Nếu query được lắp ghép theo nhiều input tùy chọn, cần nhiều nhánh bool hoặc dùng tính năng Query DSL đặc thù, chuyển sang Operations.

### Bước 3: Kiểm tra yêu cầu về index

Nếu entity luôn dùng một index/alias mặc định, repository thuận tiện.

Nếu mỗi thao tác cần chọn read alias, write alias, index lịch sử hoặc index theo tenant, Operations với **IndexCoordinates** thường rõ ràng hơn.

### Bước 4: Kiểm tra yêu cầu của response

Nếu caller chỉ cần entity, repository là đủ.

Nếu caller cần SearchHit metadata hoặc aggregation response, dùng kiểu trả về phù hợp hoặc Operations.

### Bước 5: Kiểm tra khả năng bảo trì

Nếu repository method bắt đầu có tên rất dài, nhiều overload hoặc annotation query khó đọc, hãy dừng lại và xem query có nên được đóng gói thành một component.

Nếu một query builder chỉ dùng trong một nơi và có logic nghiệp vụ riêng, có thể tạo search component. Nếu nó là khả năng truy cập dữ liệu dùng chung của repository, custom fragment là lựa chọn phù hợp.

## 12. Những dấu hiệu cụ thể nên chuyển sang Operations

Các dấu hiệu dưới đây thường cho thấy repository abstraction đã không còn diễn đạt tốt use case:

1. **Tên derived method quá dài:** tên phương thức phải mô tả nhiều điều kiện tùy chọn hoặc lồng logic phức tạp.
2. **Annotation query khó đọc:** JSON dài, nhiều tham số, nhiều nhánh và nhiều biến thể.
3. **Query phụ thuộc input runtime:** mỗi request có thể bật/tắt nhiều filter.
4. **Cần aggregation:** kết quả là thống kê hoặc bucket thay vì entity.
5. **Cần metadata của hit:** service cần score, highlight, sort values hoặc inner hits.
6. **Cần nhiều index/alias:** index đích phụ thuộc use case hoặc tenant.
7. **Cần search option chuyên biệt:** collapse, rescore, **search_after**, runtime mappings hoặc các tính năng nâng cao.
8. **Cần source filtering chính xác:** response chỉ nên chứa một tập field cụ thể.
9. **Cần kết hợp nhiều loại query:** bool, nested, geo, script hoặc function score.
10. **Cần một adapter riêng:** query phức tạp nên được đóng gói và kiểm thử độc lập.

Chỉ cần một yêu cầu quan trọng trong số này cũng có thể đủ lý do dùng Operations. Không cần chờ tới khi repository trở nên không thể bảo trì.

## 13. Những sai lầm khi chuyển từ Repository sang Operations

### Chuyển toàn bộ CRUD sang Operations

Operations có thể thực hiện save, get, delete và search. Nhưng nếu repository đã đáp ứng tốt CRUD, chuyển toàn bộ code chỉ làm tăng chi tiết và khiến ứng dụng mất lợi ích của repository abstraction.

Giữ repository cho thao tác đơn giản. Dùng Operations ở nơi cần khả năng điều khiển bổ sung.

### Đưa Query DSL vào Service

Một service có thể cần gọi search, nhưng không nhất thiết phải chứa toàn bộ builder. Khi query phức tạp, tách ProductQueryFactory, ProductSearchRepositoryImpl hoặc ProductSearchService để code nghiệp vụ dễ đọc.

### Dùng Operations nhưng bỏ qua mapping metadata

Khi gọi **operations.search(query, Product.class)**, Spring Data vẫn cần kiểu entity và metadata mapping. Nếu truyền sai class hoặc field name, kết quả có thể không chuyển đổi đúng.

Không nên coi Operations là raw client. Nó vẫn là abstraction của Spring Data và có converter, mapping metadata cùng các quy tắc riêng.

### Dùng NativeQuery cho mọi truy vấn

NativeQuery có nhiều khả năng hơn nhưng code dài hơn derived query hoặc CriteriaQuery. Chọn API đơn giản nhất vẫn đáp ứng được yêu cầu. Query DSL phức tạp mới cần NativeQuery.

### Không giữ metadata cần thiết

Nếu dùng Operations rồi chỉ chuyển SearchHits thành List<T> ngay lập tức, service có thể làm mất score, highlight hoặc sort values mà caller cần. Xác định kiểu kết quả trước khi bỏ metadata.

### Không kiểm tra phiên bản API

Các class như NativeQuery, builder method và aggregation result API thay đổi theo release train. Ví dụ code trên cần được đối chiếu với phiên bản Spring Data Elasticsearch đang chạy. Tránh copy import hoặc builder từ tài liệu của một phiên bản khác.

## 14. Kiểm thử Repository và Operations

Repository và Operations có các điểm kiểm thử khác nhau.

### Kiểm thử repository

Kiểm tra các hành vi có ý nghĩa nghiệp vụ:

- Derived query trả đúng document theo điều kiện.
- @Query tạo đúng kết quả với tham số.
- Phân trang và sort hoạt động đúng.
- CRUD dùng đúng index/alias.
- Kiểu trả về phù hợp với use case.

### Kiểm thử query builder

Nếu tách logic xây dựng query, có thể kiểm thử riêng:

- Input không có filter.
- Chỉ có category.
- Có keyword và khoảng giá.
- Có nhiều điều kiện kết hợp.
- Sort mặc định và sort tùy chọn.
- Điều kiện biên như danh sách rỗng, giá trị null hoặc khoảng giá không hợp lệ.

Không cần kết nối Elasticsearch để kiểm tra mọi quyết định xây dựng query nếu có thể kiểm tra object query hoặc cấu trúc request ở mức unit test. Tuy nhiên, cần integration test với Elasticsearch tương thích để xác nhận semantics thực tế của Query DSL và mapping.

### Kiểm thử Operations integration

Một số vấn đề chỉ xuất hiện khi chạy với Elasticsearch thật:

- Mapping không có field được query.
- keyword subfield chưa tồn tại.
- Query DSL không tương thích phiên bản server.
- Aggregation hoặc sort không hoạt động trên field.
- IndexCoordinates trỏ sai alias.
- Response có dữ liệu nhưng converter không tạo được entity.

Integration test nên dùng phiên bản Elasticsearch phù hợp với môi trường triển khai. Nếu test dựa vào Testcontainers hoặc một cluster kiểm thử, cố định version image và cấu hình mapping rõ ràng.

## 15. Ví dụ thiết kế use case hoàn chỉnh

Giả sử catalog có hai loại thao tác:

- CRUD sản phẩm.
- Tìm kiếm nâng cao theo từ khóa, category và khoảng giá, có sort và phân trang.

Repository xử lý CRUD và query đơn giản:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

Criteria object biểu diễn input tìm kiếm:

~~~java
public record ProductSearchCriteria(
    String keyword,
    String category,
    Double minPrice,
    Double maxPrice,
    int page,
    int size
) {}
~~~

Một search component dùng Operations:

~~~java
@Service
public class ProductCatalogSearch {

    private final ElasticsearchOperations operations;

    public ProductCatalogSearch(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(ProductSearchCriteria criteria) {
        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> {
                if (criteria.category() != null
                        && !criteria.category().isBlank()) {
                    b.filter(f -> f.term(t -> t
                        .field("category")
                        .value(criteria.category())
                    ));
                }

                if (criteria.keyword() != null
                        && !criteria.keyword().isBlank()) {
                    b.must(m -> m.match(mm -> mm
                        .field("name")
                        .query(criteria.keyword())
                    ));
                }

                if (criteria.minPrice() != null) {
                    b.filter(f -> f.range(r -> r
                        .number(n -> n
                            .field("price")
                            .gte(criteria.minPrice())
                        )
                    ));
                }

                if (criteria.maxPrice() != null) {
                    b.filter(f -> f.range(r -> r
                        .number(n -> n
                            .field("price")
                            .lte(criteria.maxPrice())
                        )
                    ));
                }

                return b;
            }))
            .withPageable(PageRequest.of(
                criteria.page(),
                criteria.size()
            ))
            .build();

        return operations.search(query, Product.class);
    }
}
~~~

Ví dụ này thể hiện ý tưởng tạo query từ các điều kiện có mặt. Cú pháp range builder và kiểu numeric value có thể thay đổi giữa các phiên bản Java API Client; cần điều chỉnh theo dependency thực tế. Trong ứng dụng thật, nên xác thực page, size và khoảng giá trước khi xây dựng query.

Application service kết hợp cả hai abstraction:

~~~java
@Service
public class ProductApplicationService {

    private final ProductRepository repository;
    private final ProductCatalogSearch search;

    public ProductApplicationService(
            ProductRepository repository,
            ProductCatalogSearch search) {
        this.repository = repository;
        this.search = search;
    }

    public Product create(Product product) {
        return repository.save(product);
    }

    public Optional<Product> findById(String id) {
        return repository.findById(id);
    }

    public SearchHits<Product> search(ProductSearchCriteria criteria) {
        return search.search(criteria);
    }
}
~~~

Kết quả là service vẫn dùng repository cho thao tác thông thường, còn truy vấn nâng cao được giao cho component chuyên trách sử dụng Operations.

## 16. Checklist lựa chọn abstraction

Trước khi viết một repository method mới, hãy tự trả lời:

- [ ] Đây có phải CRUD hoặc truy vấn đơn giản không?
- [ ] Tên derived method có ngắn và dễ hiểu không?
- [ ] Nếu dùng @Query, JSON có cố định và dễ bảo trì không?
- [ ] Kết quả có chỉ cần entity hoặc page không?
- [ ] Có cần aggregation hoặc SearchHit metadata không?
- [ ] Query có nhiều điều kiện tùy chọn hoặc Query DSL chuyên biệt không?
- [ ] Có cần chọn index/alias tại thời điểm gọi không?
- [ ] Có cần source filtering, highlight, collapse hoặc search_after không?
- [ ] Logic query có nên được đóng gói trong custom fragment hoặc search component không?
- [ ] API builder có tương thích với phiên bản Spring Data/Java client của dự án không?

Nếu phần lớn yêu cầu nằm ở CRUD, derived query và phân trang cơ bản, repository thường là đủ. Khi use case cần kiểm soát query, response hoặc index cụ thể, Operations là abstraction phù hợp hơn.

Repository và Operations không loại trừ nhau. Repository giữ cho đường truy cập dữ liệu thông thường ngắn gọn; Operations mở ra quyền điều khiển chi tiết khi Elasticsearch search trở thành một phần quan trọng của use case. Kết hợp hai lớp đúng chỗ giúp code vừa dễ đọc vừa khai thác được các khả năng cần thiết của Elasticsearch.

