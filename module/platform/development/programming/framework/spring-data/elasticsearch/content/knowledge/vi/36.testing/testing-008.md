# Kiểm thử derived query, CriteriaQuery, @Query và NativeQuery

Spring Data Elasticsearch hỗ trợ nhiều cách diễn đạt truy vấn: suy ra query từ tên method repository, tạo điều kiện bằng `CriteriaQuery`, khai báo JSON DSL qua annotation `@Query`, hoặc dùng `NativeQuery` để xây dựng truy vấn bằng Elasticsearch Java API Client.

Các cách viết này khác nhau ở mức độ trừu tượng và khả năng biểu đạt, nhưng cuối cùng đều phải tạo ra request mà Elasticsearch hiểu. Vì vậy, kiểm thử cần trả lời hai câu hỏi riêng:

- **Query có được xây dựng đúng từ code không?** Có thể kiểm tra một phần bằng unit test cho logic tạo query, tham số và nhánh điều kiện.
- **Elasticsearch có thực thi query với mapping và dữ liệu thật theo đúng semantics không?** Cần repository integration test chạy với Elasticsearch thật.

Mock repository không xác minh được derived query, `@Query`, mapping hoặc DSL. Tương tự, chỉ kiểm tra rằng method không ném exception cũng chưa đủ: một query hợp lệ nhưng lọc nhầm field có thể trả về danh sách rỗng mà test vẫn pass nếu không có assertion về nội dung.

## 1. Bốn cách tạo query và phạm vi kiểm thử

| Cách tạo query | Nơi khai báo | Điểm mạnh | Điều cần kiểm thử trên Elasticsearch |
|---|---|---|---|
| Derived query | Tên method repository như `findByStatusAndPriceLessThan` | Ngắn, dễ đọc, phù hợp điều kiện phổ biến. | Tên property, toán tử, mapping và kết quả thực tế. |
| `CriteriaQuery` | Java code dùng `Criteria` | Xây dựng điều kiện động theo nhánh nghiệp vụ. | Field, operator, kết hợp AND/OR, range và kết quả thực tế. |
| `@Query` | JSON query DSL trong annotation repository | Khai báo query tĩnh, dễ nhìn thấy DSL. | JSON DSL, placeholder, kiểu dữ liệu và kết quả thực tế. |
| `NativeQuery` | Java API Client query DSL | Biểu đạt query phức tạp, aggregation, nested, join và tính năng Elasticsearch cụ thể. | DSL được serialize, mapping và semantics trên engine. |

Các cách này có thể cùng tồn tại trong một repository. Nên chọn cách đơn giản nhất vẫn diễn đạt rõ yêu cầu, rồi kiểm thử theo đúng tầng chịu trách nhiệm.

## 2. Dựng dữ liệu và mapping dùng chung cho ví dụ

Giả sử ứng dụng quản lý sản phẩm với các field:

- `id`: document ID.
- `sku`: mã sản phẩm duy nhất, dùng để tìm chính xác.
- `name`: tên sản phẩm, dùng full-text search.
- `status`: trạng thái, dùng filter chính xác.
- `price`: giá, dùng range query và sort.

Entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-query-it")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private double price;

    public Product() {
    }

    public Product(String id, String sku, String name, String status, double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.status = status;
        this.price = price;
    }

    // Getters and setters.
}
```

Mapping là một phần của query contract. `term` phù hợp với `keyword`, còn full-text `match` thường dùng trên `text`. Nếu đổi `status` thành `text`, truy vấn chính xác theo giá trị có thể có semantics khác do analyzer.

Repository:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByStatusAndPriceLessThan(String status, double maxPrice);

    Optional<Product> findBySku(String sku);

    @Query("{\"term\": {\"status\": \"?0\"}}")
    List<Product> findByStatusUsingJsonQuery(String status);
}
```

Repository có một derived query, một query trả về tối đa một kết quả và một method sử dụng JSON DSL qua `@Query`.

## 3. Thiết lập Elasticsearch integration test

Để xác minh query thực sự, cần Elasticsearch instance tương thích với Spring Data Elasticsearch và Java API Client của dự án. Testcontainers là lựa chọn phổ biến vì mỗi test suite có thể khởi chạy một phiên bản Elasticsearch được pin rõ ràng.

Dependencies Gradle minh họa:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:elasticsearch'
}
```

Nên quản lý version Testcontainers bằng BOM/dependency management của dự án. Pin Elasticsearch image theo version tương thích, không dùng `latest` trong CI.

Ví dụ test class:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

@Testcontainers
@SpringBootTest
abstract class AbstractProductQueryIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
                    )
            ).withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void configureElasticsearch(DynamicPropertyRegistry registry) {
        registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
    }

    @Autowired
    protected ProductRepository repository;

    @Autowired
    protected ElasticsearchOperations operations;

    @BeforeEach
    void resetIndex() {
        IndexOperations index = operations.indexOps(Product.class);
        index.delete();
        index.createWithMapping();
    }

    protected void insertProducts() {
        repository.saveAll(List.of(
                new Product("P-100", "SKU-100", "Mechanical Keyboard", "ACTIVE", 250.0),
                new Product("P-101", "SKU-101", "Wireless Mouse", "ACTIVE", 45.0),
                new Product("P-102", "SKU-102", "Keyboard Wrist Rest", "INACTIVE", 30.0),
                new Product("P-103", "SKU-103", "USB-C Hub", "ACTIVE", 80.0)
        ));
        indexRefresh();
    }

    protected void indexRefresh() {
        operations.indexOps(Product.class).refresh();
    }
}
```

Đây là cấu hình minh họa. Property kết nối, security và cách khởi chạy container phải khớp với phiên bản Spring Boot/Testcontainers/Elasticsearch của dự án. Nếu môi trường test cần security bật, hãy cấu hình credential và TLS tương ứng thay vì tắt security.

`resetIndex()` tạo mapping mới cho từng test. `insertProducts()` thêm dữ liệu mẫu rồi refresh để các Search API query nhìn thấy dữ liệu. Không dùng `Thread.sleep` để đợi refresh.

## 4. Kiểm thử derived query

Derived query được tạo từ tên method. Ví dụ:

```java
List<Product> findByStatusAndPriceLessThan(String status, double maxPrice);
```

Spring Data phân tích tên method thành điều kiện tương đương:

```text
status = :status AND price < :maxPrice
```

Kiểm thử integration:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class ProductDerivedQueryIT extends AbstractProductQueryIT {

    @Test
    void derivesEqualityAndLessThanConditions() {
        insertProducts();

        List<Product> results =
                repository.findByStatusAndPriceLessThan("ACTIVE", 100.0);

        assertThat(results)
                .extracting(Product::getId)
                .containsExactlyInAnyOrder("P-101", "P-103");
    }
}
```

Test xác minh nhiều điều cùng lúc:

- Spring Data nhận diện được tên property `status` và `price`.
- Toán tử `And` kết hợp hai điều kiện.
- `LessThan` được chuyển thành range condition nhỏ hơn.
- Mapping của hai field tương thích với query.
- Kết quả search thực tế chứa đúng document.

### 4.1. Kiểm thử method trả về một kết quả

```java
@Test
void derivesQueryForUniqueSku() {
    insertProducts();

    Optional<Product> found = repository.findBySku("SKU-100");

    assertThat(found)
            .isPresent()
            .get()
            .extracting(Product::getId)
            .isEqualTo("P-100");
}
```

`sku` được map thành `keyword`, phù hợp với tìm kiếm chính xác. Nếu dữ liệu có thể trùng SKU, kiểu trả về `Optional<Product>` không còn phản ánh đúng cardinality nghiệp vụ; khi đó cần unique constraint ở nguồn dữ liệu hoặc đổi method trả về collection và xử lý trùng rõ ràng.

### 4.2. Kiểm thử các toán tử biên

Với range query, nên kiểm tra giá trị nằm ngay dưới, đúng bằng và ngay trên ngưỡng:

```java
@Test
void lessThanDoesNotIncludeTheBoundary() {
    insertProducts();

    List<Product> results =
            repository.findByStatusAndPriceLessThan("ACTIVE", 80.0);

    assertThat(results)
            .extracting(Product::getId)
            .containsExactly("P-101");
}
```

`LessThan(80.0)` không bao gồm sản phẩm có giá đúng 80.0. Nếu nghiệp vụ yêu cầu bao gồm ngưỡng, dùng toán tử `LessThanEqual` và viết test biên tương ứng.

### 4.3. Derived query cần kiểm tra mapping và tên field

Tên property Java và tên field Elasticsearch có thể khác nhau nếu dùng `@Field(name = "...")`. Derived query thường dựa vào property của entity; Spring Data mapping chuyển property sang tên field tương ứng.

Nếu entity khai báo:

```java
@Field(name = "product_status", type = FieldType.Keyword)
private String status;
```

thì test phải xác minh query trên mapping thực tế `product_status`, không giả định field trong index mang tên `status`.

## 5. Kiểm thử `@Query` với JSON DSL

`@Query` cho phép khai báo query JSON trực tiếp trên repository method:

```java
@Query("{\"term\": {\"status\": \"?0\"}}")
List<Product> findByStatusUsingJsonQuery(String status);
```

`?0` là placeholder cho tham số đầu tiên. Với method có nhiều tham số, `?1`, `?2`... tham chiếu theo thứ tự tham số. Không nối chuỗi input vào JSON DSL bằng string concatenation.

Integration test:

```java
class ProductAnnotatedQueryIT extends AbstractProductQueryIT {

    @Test
    void executesJsonQueryWithBoundParameter() {
        insertProducts();

        List<Product> results =
                repository.findByStatusUsingJsonQuery("ACTIVE");

        assertThat(results)
                .extracting(Product::getId)
                .containsExactlyInAnyOrder("P-100", "P-101", "P-103");
    }
}
```

Test này xác minh JSON query hợp lệ, placeholder được thay bằng giá trị truyền vào và `term` query lọc đúng trạng thái.

### 5.1. Dùng `match` cho field text

Ví dụ method tìm tên sản phẩm theo full-text:

```java
@Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
List<Product> searchByName(String text);
```

Test:

```java
@Test
void executesMatchQueryForTextField() {
    insertProducts();

    List<Product> results = repository.searchByName("keyboard");

    assertThat(results)
            .extracting(Product::getId)
            .contains("P-100", "P-102");
}
```

`match` dùng analyzer của field `name`. Kết quả phụ thuộc analyzer và dữ liệu index; test nên sử dụng từ khóa có semantics ổn định theo analyzer được cấu hình.

### 5.2. Test nhiều placeholder

Một query tĩnh có thể nhận nhiều tham số:

```java
@Query("""
        {
          "bool": {
            "filter": [
              { "term": { "status": "?0" } },
              { "range": { "price": { "lt": ?1 } } }
            ]
          }
        }
        """)
List<Product> findByStatusAndMaximumPrice(String status, double maxPrice);
```

Text block yêu cầu Java version hỗ trợ text block. Nếu dự án dùng Java cũ hơn, dùng string literal được escape.

Test:

```java
@Test
void bindsMultipleQueryParameters() {
    insertProducts();

    List<Product> results =
            repository.findByStatusAndMaximumPrice("ACTIVE", 100.0);

    assertThat(results)
            .extracting(Product::getId)
            .containsExactlyInAnyOrder("P-101", "P-103");
}
```

Điều cần kiểm tra là placeholder được thay đúng vị trí và kiểu dữ liệu được biểu diễn đúng trong JSON. Với numeric range, không đặt placeholder trong dấu nháy nếu DSL cần một JSON number.

### 5.3. Những điểm cần chú ý khi kiểm thử `@Query`

- JSON phải hợp lệ và tương thích phiên bản Elasticsearch.
- Field name phải khớp mapping, bao gồm tên field được đổi qua `@Field(name = ...)`.
- `term` phù hợp với exact value/keyword; `match` phù hợp với full-text field.
- Placeholder phải nằm đúng kiểu JSON: chuỗi có quote, numeric/boolean không có quote.
- Không nối input người dùng trực tiếp vào query string.
- Test với dữ liệu có kết quả dương và dữ liệu không khớp để phát hiện query quá rộng.
- Nếu query có sort, paging hoặc filter, hãy xác minh từng hành vi riêng.

## 6. Kiểm thử `CriteriaQuery`

`CriteriaQuery` hữu ích khi điều kiện phụ thuộc vào tham số tùy chọn hoặc logic nghiệp vụ. Ví dụ người dùng có thể lọc theo trạng thái và mức giá tối đa.

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = new CriteriaQuery(
        new Criteria("status").is("ACTIVE")
                .and("price").lessThan(100.0)
);
```

Thực thi qua `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits = operations.search(query, Product.class);

List<Product> products = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
```

### 6.1. Integration test cho CriteriaQuery

```java
class ProductCriteriaQueryIT extends AbstractProductQueryIT {

    @Test
    void combinesStatusAndPriceCriteria() {
        insertProducts();

        Query query = new CriteriaQuery(
                new Criteria("status").is("ACTIVE")
                        .and("price").lessThan(100.0)
        );

        SearchHits<Product> hits = operations.search(query, Product.class);

        assertThat(hits.getSearchHits())
                .extracting(hit -> hit.getContent().getId())
                .containsExactlyInAnyOrder("P-101", "P-103");
    }
}
```

Test chạy CriteriaQuery qua Spring Data converter và Elasticsearch engine thật. Nó có thể phát hiện lỗi field, operator, mapping hoặc cách kết hợp điều kiện.

### 6.2. Kiểm thử điều kiện tùy chọn

Một service có thể chỉ thêm điều kiện khi người dùng truyền tham số:

```java
public Query buildProductSearch(String status, Double maxPrice) {
    Criteria criteria = new Criteria();

    if (status != null && !status.isBlank()) {
        criteria = criteria.and("status").is(status);
    }

    if (maxPrice != null) {
        criteria = criteria.and("price").lessThanEqual(maxPrice);
    }

    return new CriteriaQuery(criteria);
}
```

Với builder kiểu này, có thể viết unit test để kiểm tra nhánh tạo query và integration test cho một số tổ hợp quan trọng.

Các trường hợp nên có:

- Không có filter nào.
- Chỉ có status.
- Chỉ có max price.
- Có cả status và max price.
- Giá đúng bằng ngưỡng khi dùng `lessThanEqual`.
- Status không có kết quả.

Không cần chạy mọi tổ hợp logic đơn giản qua Elasticsearch nếu query builder đã được kiểm tra riêng, nhưng phải có integration test xác nhận query được thực thi đúng với mapping.

### 6.3. Kết hợp OR và AND

Criteria API hỗ trợ tạo nhóm điều kiện. Ví dụ tìm sản phẩm active thuộc một trong hai khoảng giá hoặc có tên phù hợp. Cần chú ý precedence và grouping vì thay đổi vị trí `and`/`or` có thể đổi semantics.

Ví dụ ý tưởng:

```java
Criteria status = new Criteria("status").is("ACTIVE");
Criteria priceRange = new Criteria("price").lessThan(50.0)
        .or("price").greaterThan(200.0);

Criteria combined = status.and(priceRange);
Query query = new CriteriaQuery(combined);
```

Hãy viết integration test có document thuộc từng nhánh OR, document không thuộc nhánh nào và document có status khác để xác minh grouping thực tế. Không chỉ kiểm tra số lượng kết quả vì hai tập kết quả sai có thể có cùng count.

## 7. Kiểm thử `NativeQuery`

`NativeQuery` phù hợp khi cần biểu đạt DSL của Elasticsearch Java API Client. Nó cho phép sử dụng query type cụ thể như `bool`, `nested`, `has_child`, `geo_distance`, `function_score`, cùng sort, aggregation và các tùy chọn nâng cao.

Ví dụ query tìm sản phẩm có tên khớp `keyboard` và trạng thái `ACTIVE`:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query nativeDsl = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("name")
                                .query("keyboard")
                        )
                )
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                        )
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(nativeDsl)
        .build();
```

Thực thi:

```java
SearchHits<Product> hits = operations.search(nativeQuery, Product.class);
```

### 7.1. Integration test cho NativeQuery

```java
class ProductNativeQueryIT extends AbstractProductQueryIT {

    @Test
    void executesBoolQueryWithMustAndFilter() {
        insertProducts();

        Query nativeDsl = Query.of(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(mm -> mm
                                        .field("name")
                                        .query("keyboard")
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value(FieldValue.of("ACTIVE"))
                                )
                        )
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(nativeDsl)
                .build();

        SearchHits<Product> hits = operations.search(query, Product.class);

        assertThat(hits.getSearchHits())
                .extracting(hit -> hit.getContent().getId())
                .containsExactly("P-100");
    }
}
```

Query này yêu cầu cả hai điều kiện: tên match `keyboard` và trạng thái exact `ACTIVE`. `P-102` có tên khớp nhưng inactive nên phải bị loại bởi filter.

### 7.2. Vì sao dùng `NativeQuery` thay vì `@Query`?

Chọn `NativeQuery` khi:

- Query có nhiều nhánh bool/nested hoặc cấu trúc DSL phức tạp.
- Cần tính năng mới của Elasticsearch Java API Client.
- Query được tạo động theo nhiều điều kiện.
- Cần sort, aggregation, highlight, suggest hoặc các option nâng cao.
- Muốn tận dụng type-safe builder của Java API Client thay vì ghép JSON string.

`@Query` phù hợp với query tĩnh, nhỏ và dễ đọc ngay tại repository method. Không cần chuyển mọi query sang `NativeQuery` nếu method derivation hoặc `@Query` đã rõ ràng.

## 8. Kiểm thử aggregation trong NativeQuery

Nếu NativeQuery có aggregation, test cần xác minh cả kết quả bucket/metric chứ không chỉ xác nhận search không lỗi.

Ví dụ tạo terms aggregation theo trạng thái:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Aggregation byStatus = Aggregation.of(a -> a
        .terms(t -> t.field("status"))
);

NativeQuery query = NativeQuery.builder()
        .withQuery(Query.of(q -> q.matchAll(m -> m)))
        .withAggregation("products_by_status", byStatus)
        .build();
```

Sau khi gọi search, đọc aggregation từ `SearchHits`/aggregation container theo API Spring Data version đang dùng. Các kiểu wrapper aggregation và cách lấy bucket đã thay đổi giữa các thế hệ API; nên dùng đúng kiểu do version dự án cung cấp.

Một integration test aggregation nên kiểm tra:

- Bucket key, ví dụ `ACTIVE` và `INACTIVE`.
- Bucket document count.
- Metric value nếu có `avg`, `sum`, `min`, `max`.
- Kết quả khi không có document.
- Filter/query scope áp dụng lên aggregation có đúng không.

Không hardcode toàn bộ JSON response thành một string để so sánh. Trích giá trị có ý nghĩa và assertion trên key/count/value để test ít phụ thuộc format.

## 9. Kiểm thử sort và pagination

Query đúng filter nhưng sort hoặc page sai vẫn có thể làm API trả kết quả không đúng.

Với repository method, có thể nhận `Pageable` hoặc `Sort` nếu method signature hỗ trợ:

```java
Page<Product> findByStatus(String status, Pageable pageable);
```

Integration test cần xác minh:

- Trang đầu và trang kế tiếp không lặp document.
- Tổng số phần tử phù hợp với query.
- Sort tăng/giảm theo field đúng.
- Tie-breaker ổn định nếu nhiều document có cùng giá trị sort.
- Mapping field có hỗ trợ sort, ví dụ `keyword` hoặc numeric field.

Ví dụ sort:

```java
Pageable pageable = PageRequest.of(
        0,
        2,
        Sort.by(Sort.Direction.DESC, "price")
);

Page<Product> page = repository.findByStatus("ACTIVE", pageable);
```

Test nên assert thứ tự ID/giá theo dữ liệu cố định. Nếu dùng full-text field `name` có mapping `text`, sort có thể cần subfield `keyword` thay vì sort trực tiếp trên text field.

## 10. Kiểm thử query builder tách biệt với query execution

Khi query phức tạp, có thể tách việc xây dựng query thành component thuần:

```java
public class ProductQueryFactory {

    public Query build(String status, String keyword) {
        // Return the Elasticsearch Java API Client Query.
    }
}
```

Unit test cho factory có thể kiểm tra các nhánh đầu vào, ví dụ status null thì không thêm filter, keyword rỗng thì không thêm match clause. Tuy nhiên, chỉ unit test factory không chứng minh Elasticsearch thực thi DSL đúng.

Một chiến lược cân bằng:

1. Unit test query factory cho các nhánh logic và tham số.
2. Một số integration test cho query đại diện và các trường hợp biên.
3. Integration test riêng cho tính năng engine-specific như nested, geo, join, aggregation hoặc script.

Không cần kiểm thử từng dòng builder hai lần nếu một integration test đã bao phủ đầy đủ behavior quan trọng. Chọn test theo rủi ro và độ phức tạp query.

## 11. Kiểm thử empty result và điều kiện không khớp

Một query không lỗi nhưng trả rỗng có thể là kết quả đúng hoặc dấu hiệu query sai. Cần có dữ liệu đối chứng.

Ví dụ:

```java
@Test
void returnsEmptyWhenNoProductMatchesStatus() {
    insertProducts();

    List<Product> results =
            repository.findByStatusAndPriceLessThan("DELETED", 100.0);

    assertThat(results).isEmpty();
}
```

Với query phức tạp, nên tạo dữ liệu:

- Khớp tất cả điều kiện.
- Chỉ khớp điều kiện thứ nhất.
- Chỉ khớp điều kiện thứ hai.
- Không khớp điều kiện nào.
- Có field null/missing nếu query phải xử lý trường hợp đó.

Đây là cách phát hiện lỗi thiếu filter, sai AND/OR hoặc điều kiện null bị bỏ qua.

## 12. Kiểm thử dữ liệu null và missing field

Trong Elasticsearch, field không có giá trị và field có giá trị `null` thường không tạo indexed term như một giá trị thông thường. Query `exists`, `must_not exists` và điều kiện range có semantics riêng.

Nếu query phải tìm document thiếu field:

```java
Query missingBrand = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e.field("brand"))
                )
        )
);
```

Test nên có document không chứa `brand`, document có `brand`, và document có `brand: null` nếu source converter có thể tạo trường hợp đó. Xác minh kết quả thực tế theo mapping và cấu hình `null_value` nếu có.

Không giả định Java `null`, JSON `null` và field missing luôn được xử lý giống nhau trong mọi query.

## 13. Refresh là phần của query integration test

Search API là near-real-time. Sau `repository.save(...)`, `@Query`, derived query, CriteriaQuery và NativeQuery có thể chưa nhìn thấy document mới nếu index chưa refresh.

Không ổn định:

```java
repository.save(product);
assertThat(repository.findBySku(product.getSku())).isPresent();
```

Ổn định hơn:

```java
repository.save(product);
operations.indexOps(Product.class).refresh();

assertThat(repository.findBySku(product.getSku())).isPresent();
```

Không dùng `Thread.sleep` để chờ refresh. Nếu test đang xác minh Get API theo ID, `findById` có real-time semantics theo mặc định và không cần refresh chỉ để đọc document mới.

Với bulk setup, lưu toàn bộ dữ liệu trước rồi refresh một lần thay vì refresh sau từng document.

## 14. Test repository với custom index name và alias

Test nên dùng index riêng như `products-query-it`, không trỏ vào index production hoặc index local đang dùng cho phát triển.

Nếu ứng dụng dùng alias, có thể tạo index version trong test rồi gắn alias tương ứng. Điều này giúp xác minh:

- Repository dùng đúng alias được khai báo trong `@Document`.
- Alias trỏ đúng index vật lý.
- Query chạy được qua alias.
- Write operation đi đến write index khi alias trỏ nhiều index.

Đối với test chỉ tập trung query DSL, index riêng không cần mô phỏng toàn bộ alias migration. Chỉ thêm alias behavior khi đó là một phần của hợp đồng cần kiểm thử.

## 15. Kiểm thử mapping trước khi kết luận query sai

Query có thể trả kết quả sai vì mapping chứ không phải vì builder.

Ví dụ:

- `term` trên field `text` có analyzer có thể không khớp giá trị nguyên bản.
- `match` trên field `keyword` không có semantics phân tích từ như `text`.
- Range query trên string có thể so sánh khác numeric range.
- Sort trên `text` field có thể bị cấm hoặc cần subfield keyword.
- Nested query chỉ hoạt động khi field được mapping là `nested`.
- Geo query yêu cầu đúng `geo_point`/`geo_shape` mapping.

Khi integration test thất bại, kiểm tra mapping thực tế:

```http
GET /products-query-it/_mapping
```

Đừng chỉ sửa query cho đến khi test pass nếu mapping mới là nguyên nhân. Query và mapping là một hợp đồng; cả hai cần khớp với yêu cầu nghiệp vụ.

## 16. Kiểm thử query với dữ liệu ổn định

Test data nên nhỏ nhưng phân biệt rõ các trường hợp. Ví dụ bốn sản phẩm ở phần đầu bài đủ để kiểm tra status, full-text và price range.

Một số nguyên tắc:

- ID cố định để assertion dễ đọc.
- Field cần filter có giá trị rõ ràng.
- Dữ liệu biên cho range và sort.
- Không dùng dữ liệu ngẫu nhiên nếu kết quả mong đợi phụ thuộc nội dung.
- Mỗi test tự tạo dữ liệu và không phụ thuộc test khác.
- Dùng unique ID/index nếu chạy song song.
- Dọn index/document sau test hoặc dùng container riêng.

Không cần tạo hàng nghìn document cho một test xác minh query cơ bản. Dataset lớn chỉ cần khi kiểm thử pagination, performance hoặc behavior phụ thuộc phân bố dữ liệu.

## 17. Kiểm thử lỗi query và mapping rejection

Một số lỗi nên được kiểm tra ở integration test:

- Field không tồn tại hoặc query dùng sai field path.
- Query DSL không hợp lệ.
- Kiểu giá trị không tương thích mapping.
- Nested path không phải nested mapping.
- Script không hợp lệ hoặc field thiếu.
- Aggregation trên field không hỗ trợ aggregation.

Không nên viết test khẳng định mọi query sai phải ném cùng một exception class ở tất cả phiên bản. Exception wrapping có thể khác giữa Spring Data, Java API Client và server. Hãy kiểm tra loại lỗi ở mức ứng dụng đã chuẩn hóa hoặc status/error type ổn định theo version đang pin.

## 18. Unit test cho service gọi repository query

Service có thể quyết định gọi method nào dựa trên request:

```java
public List<Product> search(ProductFilter filter) {
    if (filter.status() != null && filter.maxPrice() != null) {
        return repository.findByStatusAndPriceLessThan(
                filter.status(), filter.maxPrice());
    }

    if (filter.sku() != null) {
        return repository.findBySku(filter.sku()).stream().toList();
    }

    return repository.findAll().stream().toList();
}
```

Unit test có thể mock repository và xác minh service chọn đúng method/argument theo filter. Nó không cần biết query method được chuyển thành DSL nào; phần đó thuộc repository integration test.

Tách test như vậy giúp phát hiện lỗi ở đúng tầng:

- Service gọi nhầm method hoặc truyền sai tham số: service unit test.
- Repository method sinh query sai: repository integration test.
- Mapping field không tương thích query: repository integration test.

## 19. Reactive query cũng cần cùng chiến lược

Với `ReactiveElasticsearchRepository`, derived query trả `Mono` hoặc `Flux`. `ReactiveElasticsearchOperations` cũng hỗ trợ CriteriaQuery/NativeQuery theo API reactive tương ứng.

Service unit test có thể mock publisher:

```java
when(repository.findByStatus("ACTIVE"))
        .thenReturn(Flux.just(product1, product2));

StepVerifier.create(service.findActive())
        .expectNext(product1, product2)
        .verifyComplete();
```

Repository integration test cần subscribe publisher và xác minh kết quả trên Elasticsearch thật:

```java
StepVerifier.create(repository.findByStatus("ACTIVE"))
        .expectNextCount(2)
        .verifyComplete();
```

Trước khi chạy search, cần refresh index nếu test vừa ghi dữ liệu. Reactive không làm thay đổi near-real-time semantics của Search API.

Không gọi `.block()` trong service/controller để test dễ hơn. Dùng `StepVerifier` để kiểm tra `onNext`, `onComplete` và `onError`.

## 20. Cô lập test và tránh phụ thuộc thứ tự

Elasticsearch không tự rollback document khi test kết thúc. `@Transactional` không mặc nhiên xóa dữ liệu đã index.

Các lựa chọn cô lập:

1. Tạo lại index trước mỗi test như ví dụ `resetIndex()`.
2. Dùng ID duy nhất theo test run và cleanup sau test.
3. Tạo index riêng theo class/suite hoặc theo test khi chạy song song.
4. Dùng container riêng cho test suite.

Nếu nhiều test dùng chung một index và chạy parallel, việc test A xóa index trong khi test B đang query sẽ gây lỗi khó tái hiện. Khi cần parallel execution, dùng namespace index riêng hoặc chia sẻ container nhưng tách index cho từng test.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Service test pass nhưng query production sai | Repository bị mock nên query không được thực thi. | Thêm repository integration test với Elasticsearch thật. |
| Derived query trả rỗng | Sai property name, mapping hoặc dữ liệu chưa refresh. | Kiểm tra entity property/mapping và refresh trước search. |
| `term` không khớp giá trị text | Dùng exact query trên field `text` đã qua analyzer. | Dùng keyword field/subfield hoặc query phù hợp. |
| `match` trả quá nhiều kết quả | Analyzer token hóa/chuẩn hóa khác kỳ vọng. | Kiểm tra analyzer và test bằng dữ liệu đại diện. |
| `@Query` lỗi parse | JSON không hợp lệ hoặc placeholder sai vị trí/kiểu. | Kiểm tra JSON DSL, quote và index mapping. |
| `@Query` không lọc đúng tham số | Dùng sai `?0`, `?1` hoặc placeholder nằm trong JSON type không phù hợp. | Kiểm tra thứ tự tham số và kiểu JSON. |
| CriteriaQuery bỏ sót điều kiện | Ghép AND/OR hoặc nhánh optional sai. | Test từng nhánh và document chỉ khớp một điều kiện. |
| NativeQuery compile nhưng kết quả sai | DSL hợp lệ nhưng field path/operator/mapping sai. | Integration test trên engine và kiểm tra mapping. |
| Sort trên field text thất bại | Field không có doc values/sortable mapping phù hợp. | Dùng keyword subfield hoặc mapping hỗ trợ sort. |
| Test lúc pass lúc fail | Search chạy trước refresh. | Refresh tường minh hoặc dùng `WAIT_UNTIL`. |
| Test phụ thuộc dữ liệu cũ | Index dùng chung và không cleanup. | Reset index, unique ID hoặc index riêng. |
| Test parallel gây xung đột | Nhiều test xóa/tạo cùng index. | Tách index theo test hoặc không chạy song song nhóm đó. |
| Aggregation count không đúng | Query scope, mapping hoặc field aggregation sai. | Kiểm tra field type và assertion từng bucket/metric. |
| Test query không chạy trong CI | Integration test không được gắn vào task/build pipeline. | Cấu hình task/test source set và container runtime rõ ràng. |

## 22. Ma trận kiểm thử cho bốn kiểu query

| Hạng mục | Unit test | Repository integration test |
|---|---|---|
| Tên derived method và service chọn đúng method | Có thể kiểm tra lời gọi từ service. | Xác minh query derivation và kết quả thực tế. |
| `@Query` placeholder | Có thể kiểm tra method/argument ở service boundary. | Xác minh JSON query và binding. |
| CriteriaQuery builder | Kiểm tra nhánh tạo điều kiện. | Xác minh AND/OR/operator trên engine. |
| NativeQuery factory | Kiểm tra nhánh logic và tham số. | Xác minh DSL, mapping và semantics. |
| Mapping/analyzer | Không. | Có. |
| Refresh visibility | Không. | Có. |
| Sort/pagination | Service có thể kiểm tra tham số. | Xác minh thứ tự/trang thực tế. |
| Aggregation/nested/geo/join | Không xác minh engine. | Có. |
| Lỗi nghiệp vụ từ kết quả query | Có. | Có thể chọn lọc ở service integration. |

## 23. Quy trình viết test cho một query mới

1. **Xác định semantics:** query cần exact match, full-text, range, nested hay aggregation?
2. **Kiểm tra mapping:** field type, analyzer, subfield, nested path và doc values có phù hợp không?
3. **Chọn cách biểu đạt:** derived method, CriteriaQuery, `@Query` hoặc NativeQuery.
4. **Tách logic động:** nếu query builder có nhiều nhánh, đưa thành component có thể unit test.
5. **Chuẩn bị Elasticsearch test:** dùng Testcontainers với version pin phù hợp.
6. **Tạo index và dữ liệu:** dùng mapping giống production và dataset có trường hợp khớp/không khớp.
7. **Refresh:** refresh sau setup trước khi chạy Search API query.
8. **Assert kết quả:** kiểm tra ID/content, không chỉ count hoặc không ném exception.
9. **Kiểm tra biên:** empty, null/missing, range boundary, AND/OR, sort và paging nếu có.
10. **Cô lập dữ liệu:** reset index hoặc dùng namespace riêng; tránh sleep và phụ thuộc thứ tự.
11. **Đưa vào CI:** bảo đảm integration test thực sự chạy với Elasticsearch container.

## 24. Những điểm cần nhớ

- Derived query được suy ra từ tên method; cần kiểm thử property, operator và kết quả trên mapping thật.
- `CriteriaQuery` phù hợp với điều kiện động; cần test từng nhánh và cách ghép AND/OR.
- `@Query` chứa JSON DSL; kiểm thử JSON, placeholder `?0`/`?1`, kiểu dữ liệu và field mapping.
- `NativeQuery` dùng Java API Client DSL cho truy vấn phức tạp và tính năng Elasticsearch chuyên biệt.
- Mock repository chỉ kiểm tra service; nó không xác minh query được thực thi.
- Repository integration test nên dùng Elasticsearch thật, thường qua Testcontainers với version được pin.
- `term` thường dùng với `keyword`; `match` thường dùng với `text`; range/sort cần kiểu field phù hợp.
- Search API near-real-time; refresh tường minh trong test sau khi ghi dữ liệu.
- Không dùng `Thread.sleep` để chờ refresh.
- Assert document ID/content và điều kiện biên; chỉ assert count có thể bỏ sót query sai.
- Kiểm tra mapping thực tế khi query trả kết quả không như mong đợi.
- Test sort, pagination, aggregation, nested, geo, join và routing ở tầng integration khi ứng dụng sử dụng các tính năng đó.
- Dùng index/test data riêng và không giả định `@Transactional` rollback Elasticsearch.
- Reactive query vẫn cần `StepVerifier` và refresh; reactive không thay đổi semantics Search API.

Kiểm thử derived query, CriteriaQuery, `@Query` và NativeQuery cần kết hợp hiểu biết về code tạo query với hành vi thực của Elasticsearch. Unit test phù hợp để kiểm tra logic chọn điều kiện và orchestration của service; repository integration test xác minh mapping, DSL, parameter binding, refresh và kết quả tìm kiếm trên engine. Khi mỗi loại test tập trung đúng trách nhiệm, lỗi query được phát hiện sớm và dễ xác định nguyên nhân hơn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — CriteriaQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — `@Query` annotation](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/Query.html)
- [Spring Data Elasticsearch — NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch — Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
