# Thay API cũ như ElasticsearchRestTemplate và NativeSearchQuery theo dòng phiên bản

Spring Data Elasticsearch đã thay đổi client nền tảng giữa dòng 4.x và 5.x. Ở dòng 4.x, ứng dụng thường dùng Elasticsearch Rest High Level Client (HLRC), ElasticsearchRestTemplate và NativeSearchQuery. Từ dòng 5.x, Spring Data chuyển sang Elasticsearch Java API Client; template imperative tương ứng là ElasticsearchTemplate và truy vấn native dùng NativeQuery.

Đây là thay đổi kiến trúc client và query DSL, không chỉ là đổi tên class. Những kiểu như org.elasticsearch.index.query.QueryBuilder của HLRC không thể truyền thẳng vào Java API Client. Khi nâng cấp, cần đồng bộ Spring Boot, Spring Data Elasticsearch, Elasticsearch server và client dependency; sau đó chuyển cấu hình, query builder, aggregation, sort, bulk và các điểm tích hợp trực tiếp với client.

Bài này hướng dẫn cách nhận diện API theo dòng phiên bản, thay ElasticsearchRestTemplate và NativeSearchQuery, chuyển query DSL cũ sang Java API Client DSL, xử lý dependency/configuration, giữ phần abstraction ổn định và kiểm thử migration theo từng bước.

## 1. Bắt đầu bằng việc xác định dòng phiên bản

Tên class không đủ để xác định API đang được dùng. Hãy kiểm tra dependency tree, import trong source và phiên bản Spring Boot BOM.

Có thể hình dung hai dòng chính như sau:

| Thành phần | Spring Data Elasticsearch 4.x | Spring Data Elasticsearch 5.x |
|---|---|---|
| Client chính | Elasticsearch Rest High Level Client (HLRC) | Elasticsearch Java API Client |
| Client type thường gặp | RestHighLevelClient | ElasticsearchClient |
| Template imperative | ElasticsearchRestTemplate | ElasticsearchTemplate |
| Native query | NativeSearchQuery / NativeSearchQueryBuilder | NativeQuery |
| Query builder | org.elasticsearch.index.query.QueryBuilders | Java API Client generated DSL |
| Aggregation builder | org.elasticsearch.search.aggregations.AggregationBuilders | Java API Client Aggregation builders |
| Transport HTTP | RestClient bên dưới HLRC | RestClient + ElasticsearchTransport bên dưới Java API Client |
| Framework baseline | Dòng Spring Framework 5 / Boot 2.x | Dòng Spring Framework 6 / Boot 3.x |
| Java baseline | Phụ thuộc release 4.x; các bản cuối hỗ trợ Java 8+ | Java 17+ |

Bảng này mô tả hướng chuyển đổi phổ biến, không thay thế bảng compatibility chính thức của đúng release. Các minor/patch release có thể thay đổi phiên bản Elasticsearch server/client được hỗ trợ. Hãy kiểm tra release train và dependency management trước khi chọn cặp version.

### 1.1. Kiểm tra dependency thực tế

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-rest-high-level-client --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch
mvn dependency:tree -Dincludes=org.elasticsearch.client:elasticsearch-rest-high-level-client
mvn dependency:tree -Dincludes=co.elastic.clients:elasticsearch-java
~~~

Kiểm tra cả version được quản lý bởi Spring Boot BOM. Không nâng riêng spring-data-elasticsearch hoặc elasticsearch-java lên version tùy ý nếu Boot đang quản lý dependency đó.

### 1.2. Phân biệt ba lớp client

Trong migration, tên có chữ Rest dễ gây nhầm:

- RestHighLevelClient: client Java cấp cao cũ, dùng trong Spring Data Elasticsearch 4.x.
- RestClient: HTTP client cấp thấp, có thể vẫn xuất hiện bên dưới transport mới.
- ElasticsearchClient: client Java API mới, cung cấp API type-safe/generated DSL.

Việc Spring Data 5.x dùng RestClient ở tầng HTTP không có nghĩa ứng dụng vẫn dùng ElasticsearchRestTemplate hoặc RestHighLevelClient. Đừng thay tên class theo cảm tính; xác định đúng abstraction ở từng tầng.

## 2. Dòng 4.x: mô hình cũ với ElasticsearchRestTemplate

Trong Spring Data Elasticsearch 4.x, cấu hình phổ biến dựa trên RestHighLevelClient. ElasticsearchRestTemplate triển khai ElasticsearchOperations và thực hiện thao tác thông qua client này.

Ví dụ import thường gặp:

~~~java
import org.elasticsearch.client.RestHighLevelClient;
import org.springframework.data.elasticsearch.core.ElasticsearchRestTemplate;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.NativeSearchQuery;
import org.springframework.data.elasticsearch.core.query.NativeSearchQueryBuilder;
~~~

Một số ứng dụng tạo template trực tiếp:

~~~java
@Bean
public ElasticsearchOperations elasticsearchOperations(
        RestHighLevelClient client) {
    return new ElasticsearchRestTemplate(client);
}
~~~

Cấu hình chi tiết có thể dùng AbstractElasticsearchConfiguration, ClientConfiguration và RestClients tùy minor version. Nên giữ việc tạo client trong configuration tập trung, không tạo RestHighLevelClient mới trong từng service.

### 2.1. Dùng interface thay vì phụ thuộc concrete template

Ngay cả ở dòng 4.x, service nên inject ElasticsearchOperations nếu chỉ cần các thao tác Spring Data:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

ElasticsearchRestTemplate là một implementation cụ thể. ElasticsearchOperations là abstraction phù hợp hơn cho repository/template operations thông thường.

Khi nâng cấp, việc service đã phụ thuộc ElasticsearchOperations giúp giảm số nơi phải sửa. Nếu code inject trực tiếp ElasticsearchRestTemplate, đổi sang interface trước hoặc trong cùng migration để tránh khóa service vào implementation cũ.

## 3. Dòng 5.x: Java API Client và ElasticsearchTemplate

Từ Spring Data Elasticsearch 5.x, client chính chuyển sang Elasticsearch Java API Client. Cấu hình Spring Data thường kế thừa ElasticsearchConfiguration và cung cấp ClientConfiguration.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }
}
~~~

Khi dùng cấu hình này, Spring Data tạo các bean client và operations tương ứng. Tên class/package phải khớp release đang dùng; trong dòng 5.x, implementation imperative mới thường là ElasticsearchTemplate trong package client.elc.

Nếu service chỉ cần operations, tiếp tục inject ElasticsearchOperations:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Nếu thật sự cần gọi Elasticsearch Java API Client trực tiếp, inject ElasticsearchClient thay vì lấy RestHighLevelClient cũ.

### 3.1. Cấu hình TLS và authentication

ClientConfiguration tiếp tục là điểm cấu hình host, SSL và authentication trong dòng 5.x:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
        .connectedTo("es.internal.example:9200")
        .usingSsl()
        .withBasicAuth(
            System.getenv("ES_USERNAME"),
            System.getenv("ES_PASSWORD")
        )
        .build();
}
~~~

Ví dụ trên dùng SSL trust configuration mặc định của runtime. Nếu cluster dùng CA nội bộ, cần cấu hình truststore/SSLContext theo API của đúng release. Không dùng cấu hình trust-all để làm migration vượt qua lỗi certificate.

### 3.2. Không tự tạo client thứ hai nếu không cần

Nếu Spring Data đã tạo ElasticsearchClient/ElasticsearchTemplate, tránh tự tạo một RestClient hoặc ElasticsearchClient thứ hai cho cùng endpoint mà không có lý do rõ ràng.

Nhiều client có thể tạo:

- Connection pool trùng lặp.
- Cấu hình TLS/authentication không đồng nhất.
- Lifecycle và shutdown khó quản lý.
- Metrics và timeout khác nhau.
- Repository dùng một client trong khi service khác dùng client khác.

Chỉ tạo custom client khi cần transport hoặc behavior riêng và phải quản lý bean/lifecycle rõ ràng.

## 4. ElasticsearchRestTemplate được thay thế như thế nào?

Trong migration từ dòng 4.x sang 5.x, thay đổi thông thường là:

~~~text
ElasticsearchRestTemplate
        |
        v
ElasticsearchTemplate
~~~

Tuy nhiên, lựa chọn tốt hơn trong business service thường là:

~~~text
ElasticsearchRestTemplate (concrete dependency)
        |
        v
ElasticsearchOperations (stable abstraction)
~~~

Service gọi các thao tác Spring Data như save, search, get, delete, bulkIndex thông qua interface. Spring Data 5.x cung cấp implementation mới ở client.elc.

### 4.1. Trước: inject concrete class cũ

~~~java
@Service
public class ProductService {

    private final ElasticsearchRestTemplate template;

    public ProductService(ElasticsearchRestTemplate template) {
        this.template = template;
    }

    public void save(Product product) {
        template.save(product);
    }
}
~~~

### 4.2. Sau: inject operations abstraction

~~~java
@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void save(Product product) {
        operations.save(product);
    }
}
~~~

Cách này tránh phụ thuộc vào tên implementation cụ thể. Nếu cần API đặc thù của Java API Client, tạo một component riêng phụ thuộc ElasticsearchClient và giới hạn phạm vi đó.

### 4.3. Những API template cần rà soát

Không nên giả định mọi overload của ElasticsearchRestTemplate có cùng signature ở ElasticsearchTemplate. Rà soát các chỗ gọi:

- search và searchForPage.
- get và multiGet.
- save và index.
- delete.
- bulkIndex, bulkUpdate, bulkDelete.
- indexOps và IndexOperations.
- refresh và refresh policy.
- callback hoặc request options tùy chỉnh.
- NativeQuery/CriteriaQuery/StringQuery.
- Các method trả về SearchHits, SearchPage hoặc SearchScrollHits.

Các abstraction chính có thể vẫn tồn tại, nhưng kiểu tham số, response type hoặc cách cấu hình client có thể thay đổi. Dùng compiler để tìm các điểm gãy và kiểm tra Javadoc của version đích.

## 5. NativeSearchQuery được thay bằng NativeQuery

Đây là thay đổi quan trọng khi chuyển query code.

Dòng 4.x thường dùng:

- NativeSearchQuery.
- NativeSearchQueryBuilder.
- QueryBuilders từ Elasticsearch HLRC.
- SortBuilders và AggregationBuilders của HLRC.

Dòng 5.x dùng NativeQuery và Java API Client DSL. Query được biểu diễn bằng các kiểu trong package co.elastic.clients.elasticsearch._types.query_dsl.

### 5.1. Query cũ: NativeSearchQueryBuilder

Ví dụ query tìm title và filter theo status:

~~~java
import org.elasticsearch.index.query.QueryBuilders;
import org.springframework.data.elasticsearch.core.query.NativeSearchQuery;
import org.springframework.data.elasticsearch.core.query.NativeSearchQueryBuilder;
import org.springframework.data.domain.PageRequest;

NativeSearchQuery query = new NativeSearchQueryBuilder()
    .withQuery(
        QueryBuilders.boolQuery()
            .must(
                QueryBuilders.matchQuery("title", "spring data")
            )
            .filter(
                QueryBuilders.termQuery("status.keyword", "published")
            )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

### 5.2. Query mới: NativeQuery

Trong dòng 5.x, query tương đương có thể được xây dựng bằng Java API Client DSL:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.domain.PageRequest;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(match -> match
                    .field("title")
                    .query("spring data")
                )
            )
            .filter(f -> f
                .term(term -> term
                    .field("status.keyword")
                    .value("published")
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Thực thi qua operations:

~~~java
SearchHits<Article> hits =
    operations.search(query, Article.class);
~~~

Điểm khác biệt:

- Không dùng org.elasticsearch.index.query.QueryBuilders.
- Không truyền QueryBuilder của HLRC vào NativeQuery.
- DSL mới dùng builder/lambda của Elasticsearch Java API Client.
- Field path, query semantics và analyzer vẫn phải khớp mapping thực tế.

### 5.3. Dùng Query.of khi muốn tạo object trước

Có thể tạo Query của Java API Client rồi truyền vào NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query queryDsl = Query.of(q -> q
    .match(m -> m
        .field("title")
        .query("spring data")
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(queryDsl)
    .build();
~~~

Cách này hữu ích khi query DSL được xây dựng trong một helper hoặc được tái sử dụng.

## 6. Chuyển từng query builder cũ sang DSL mới

Không có phép đổi tên cơ học cho mọi QueryBuilders method. Hãy chuyển theo semantics của query.

| HLRC 4.x | Java API Client DSL trong 5.x |
|---|---|
| QueryBuilders.matchQuery | q.match(...) |
| QueryBuilders.termQuery | q.term(...) |
| QueryBuilders.termsQuery | q.terms(...) |
| QueryBuilders.rangeQuery | q.range(...) |
| QueryBuilders.boolQuery | q.bool(...) |
| QueryBuilders.existsQuery | q.exists(...) |
| QueryBuilders.prefixQuery | q.prefix(...) |
| QueryBuilders.wildcardQuery | q.wildcard(...) |
| QueryBuilders.nestedQuery | q.nested(...) |
| QueryBuilders.matchAllQuery | q.matchAll(...) |
| QueryBuilders.queryStringQuery | q.queryString(...) |
| QueryBuilders.multiMatchQuery | q.multiMatch(...) |

Các lambda trên là dạng minh họa của generated Java API Client DSL. Tên enum, kiểu giá trị và overload cần xác nhận theo client version được Spring Data quản lý.

### 6.1. Match query

Cũ:

~~~java
QueryBuilders.matchQuery("description", "wireless mouse");
~~~

Mới:

~~~java
q -> q.match(m -> m
    .field("description")
    .query("wireless mouse")
)
~~~

### 6.2. Term query

Cũ:

~~~java
QueryBuilders.termQuery("status.keyword", "published");
~~~

Mới:

~~~java
q -> q.term(t -> t
    .field("status.keyword")
    .value("published")
)
~~~

Term query không phân tích chuỗi như match query. Hãy dùng field keyword hoặc field type có semantics phù hợp.

### 6.3. Range query

Cũ:

~~~java
QueryBuilders.rangeQuery("price")
    .gte(100)
    .lte(500);
~~~

Mới:

~~~java
q -> q.range(r -> r
    .number(n -> n
        .field("price")
        .gte(100.0)
        .lte(500.0)
    )
)
~~~

Java API Client có typed range variants ở các release mới. Ví dụ trên minh họa numeric range. Date range có cách biểu diễn value tương ứng; đừng truyền số cho field date hoặc ngược lại mà không theo mapping.

### 6.4. Bool query

Cũ:

~~~java
QueryBuilders.boolQuery()
    .must(QueryBuilders.matchQuery("title", "elasticsearch"))
    .filter(QueryBuilders.termQuery("active", true))
    .mustNot(QueryBuilders.termQuery("deleted", true));
~~~

Mới:

~~~java
q -> q.bool(b -> b
    .must(m -> m.match(mm -> mm
        .field("title")
        .query("elasticsearch")
    ))
    .filter(f -> f.term(t -> t
        .field("active")
        .value(true)
    ))
    .mustNot(n -> n.term(t -> t
        .field("deleted")
        .value(true)
    ))
)
~~~

Giữ đúng must, should, filter và must_not. Không chuyển mọi clause thành must; điều đó có thể làm thay đổi scoring và kết quả.

### 6.5. Prefix và wildcard

Cũ:

~~~java
QueryBuilders.prefixQuery("username.keyword", "admin");
QueryBuilders.wildcardQuery("path.keyword", "*timeout");
~~~

Mới:

~~~java
q -> q.prefix(p -> p
    .field("username.keyword")
    .value("admin")
)
~~~

~~~java
q -> q.wildcard(w -> w
    .field("path.keyword")
    .value("*timeout")
)
~~~

Migration không phải lúc để giữ nguyên mọi wildcard nếu query đó đang gây tải. Xem lại semantics, leading wildcard, mapping và expensive-query policy trước khi chuyển nguyên xi.

## 7. Chuyển sort

Dòng 4.x có thể dùng SortBuilders hoặc Spring Data Sort:

~~~java
.withSort(
    SortBuilders.fieldSort("createdAt")
        .order(SortOrder.DESC)
)
~~~

Trong Spring Data 5.x, nếu chỉ sort field thông thường, có thể dùng Spring Data Sort:

~~~java
NativeQuery query = NativeQuery.builder()
    .withSort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("productId")
    ))
    .build();
~~~

Nếu cần đầy đủ option của Elasticsearch Java API Client, tạo SortOptions:

~~~java
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;

SortOptions sort = SortOptions.of(s -> s
    .field(f -> f
        .field("createdAt")
        .order(SortOrder.Desc)
    )
);
~~~

Sau đó truyền vào NativeQuery bằng overload withSort được cung cấp ở version đang dùng.

Kiểm tra:

- Sort field có doc values hay không.
- Text field có dùng keyword sub-field không.
- Missing value policy.
- Multi-valued sort mode.
- Nested sort nếu field nằm trong nested object.
- Tie-breaker ổn định cho pagination.
- Sort order không bị đảo khi chuyển enum.

## 8. Chuyển aggregation

Dòng 4.x thường dùng AggregationBuilders:

~~~java
AggregationBuilder aggregation =
    AggregationBuilders.terms("by_status")
        .field("status.keyword")
        .size(20);
~~~

Trong Java API Client, aggregation là kiểu Aggregation:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Aggregation aggregation = Aggregation.of(a -> a
    .terms(t -> t
        .field("status.keyword")
        .size(20)
    )
);
~~~

Đưa vào query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation("by_status", aggregation)
    .withMaxResults(0)
    .build();
~~~

Tên method và cách lấy aggregation result phụ thuộc Spring Data/Java API Client release. Trong dòng 5.x, phần response thường được biểu diễn bằng kiểu aggregate của Java API Client; không giả định các class InternalTerms/Terms cũ còn tồn tại.

Sau migration, kiểm tra:

- Aggregation name.
- Field path.
- Bucket size và shard_size.
- Sub-aggregation.
- Key type.
- Doc values và fielddata requirements.
- Cách đọc bucket/result trong response mới.

## 9. Chuyển query response và SearchHits

Spring Data cung cấp abstraction SearchHits và SearchHit để ứng dụng không phải phụ thuộc trực tiếp vào response object của client ở nhiều trường hợp.

Ví dụ:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    float score = hit.getScore();
}
~~~

Kiểm tra code cũ có đọc trực tiếp:

- SearchResponse của HLRC.
- SearchHits/SearchHit cũ.
- Aggregations hoặc InternalAggregations.
- TotalHits relation.
- Highlight fields.
- Suggest response.
- Explain/profile data.
- Scroll/PIT metadata.

Nếu có, hãy xác định phần nào có thể chuyển sang SearchHits hoặc Spring Data result abstraction, phần nào cần dùng Java API Client response types.

Không chuyển raw response type cũ sang raw response type mới bằng cách cast. Kiểu dữ liệu và cách truy cập khác nhau.

## 10. CriteriaQuery và StringQuery có thể giúp giảm phạm vi migration

Không phải mọi query đều cần viết lại thành NativeQuery.

### 10.1. CriteriaQuery

CriteriaQuery phù hợp với điều kiện đơn giản như equality, range và kết hợp criteria mà Spring Data hỗ trợ.

Ví dụ:

~~~java
Criteria criteria = new Criteria("status").is("published")
    .and("price").greaterThan(100);

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

CriteriaQuery là abstraction của Spring Data, có thể giảm phụ thuộc vào generated client DSL cho các truy vấn cơ bản. Tuy nhiên, không phải mọi tính năng Elasticsearch đều được biểu diễn qua Criteria API.

### 10.2. StringQuery

Với query JSON đã được lưu trong annotation hoặc configuration, StringQuery có thể giữ nguyên DSL JSON nếu cú pháp vẫn được Elasticsearch server hỗ trợ:

~~~java
StringQuery query = new StringQuery(
    "{\"match\":{\"title\":\"spring data\"}}"
);
~~~

Cách này không yêu cầu dùng QueryBuilder cũ, nhưng JSON vẫn phải hợp lệ với Elasticsearch version đích. Các phần như kNN, runtime fields, aggregation hoặc option mới có thể cần cập nhật.

### 10.3. Repository @Query

Các repository method dùng @Query với JSON có thể cần ít thay đổi hơn query builder Java:

~~~java
@Query("{\"match\":{\"title\":\"?0\"}}")
List<Article> findByTitleText(String text);
~~~

Kiểm tra cách bind parameter và JSON escaping của đúng version. Không nối user input trực tiếp vào JSON query string.

## 11. Migration dependency và tránh trộn client cũ/mới

Một migration phổ biến là bỏ dependency trực tiếp tới HLRC nếu ứng dụng không còn dùng nó, rồi để Spring Boot/Spring Data quản lý Elasticsearch Java API Client.

Ví dụ dependency Gradle với Spring Boot plugin/BOM:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
}
~~~

Thông thường không cần tự thêm version cho spring-data-elasticsearch hoặc elasticsearch-java khi Boot BOM đã quản lý. Nếu không dùng Spring Boot, hãy dùng Spring Data BOM/release train phù hợp.

Rà soát dependency cũ:

~~~gradle
// Remove when no longer required by application code:
implementation("org.elasticsearch.client:elasticsearch-rest-high-level-client")
~~~

Không xóa dependency này chỉ vì thấy nó trong file build. Trước hết tìm mọi import trực tiếp và thư viện khác còn phụ thuộc HLRC.

Kiểm tra dependency tree sau thay đổi để phát hiện:

- Hai version elasticsearch-java.
- HLRC còn sót lại.
- Elasticsearch server/client version không tương thích.
- Apache HTTP client version conflict.
- Spring Data Elasticsearch bị override khỏi Boot BOM.
- Library nội bộ vẫn expose kiểu RestHighLevelClient hoặc QueryBuilder cũ.

## 12. Các import cũ và mới thường gặp

| Chức năng | Import dòng 4.x | Import dòng 5.x |
|---|---|---|
| Client cấp cao | org.elasticsearch.client.RestHighLevelClient | co.elastic.clients.elasticsearch.ElasticsearchClient |
| Template imperative | org.springframework.data.elasticsearch.core.ElasticsearchRestTemplate | org.springframework.data.elasticsearch.client.elc.ElasticsearchTemplate |
| Native query | org.springframework.data.elasticsearch.core.query.NativeSearchQuery | org.springframework.data.elasticsearch.client.elc.NativeQuery |
| Query builder | org.elasticsearch.index.query.QueryBuilders | co.elastic.clients.elasticsearch._types.query_dsl.Query |
| Aggregation builder | org.elasticsearch.search.aggregations.AggregationBuilders | co.elastic.clients.elasticsearch._types.aggregations.Aggregation |
| Sort options | org.elasticsearch.search.sort.SortBuilders | co.elastic.clients.elasticsearch._types.SortOptions |
| Configuration | AbstractElasticsearchConfiguration theo HLRC | ElasticsearchConfiguration theo ELC |

Một số abstraction Spring Data nằm trong package chung và tiếp tục được sử dụng. Đừng đổi import hàng loạt chỉ theo tên; dùng IDE/compiler và đối chiếu package của dependency đích.

## 13. Cấu hình repository theo dòng phiên bản

Repository interface thường có thể giữ nguyên nếu chỉ dùng CRUD và query derivation:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

Nhưng cần kiểm tra:

- Repository factory được cấu hình bởi đúng configuration class.
- Client bean tương ứng với dòng Spring Data.
- Custom repository implementation có dùng RestHighLevelClient hay QueryBuilder cũ không.
- @Query JSON có còn hợp lệ không.
- Derived method có tạo query semantics tương đương không.
- Index creation/mapping lifecycle không bị thay đổi ngoài ý muốn.

Không khai báo hai cấu hình repository cùng scan một package nếu không có chủ đích; điều này có thể tạo bean trùng hoặc gắn repository với template khác.

## 14. Reactive API trong quá trình nâng cấp

Ứng dụng reactive cần được migration riêng. Không thể lấy imperative ElasticsearchClient rồi dùng thay cho reactive client.

Các điểm cần rà soát:

- ReactiveElasticsearchOperations.
- ReactiveElasticsearchTemplate implementation.
- ReactiveElasticsearchConfiguration.
- Reactive repository factory.
- Reactive query/response types.
- Client transport và connection lifecycle.
- Retry/backpressure behavior.

Tên concrete class và client configuration phụ thuộc dòng release. Giữ service phụ thuộc ReactiveElasticsearchOperations khi có thể; chỉ chạm vào concrete reactive client ở configuration/integration boundary.

Không dùng block() để làm cho reactive code gọi imperative ElasticsearchClient trong đường request. Điều đó làm mất lợi ích non-blocking và có thể gây nghẽn event-loop.

## 15. Những API khác có thể bị ảnh hưởng

Khi bỏ HLRC, tìm toàn repository các kiểu thuộc org.elasticsearch.* cũ. Không chỉ template và query builder có thể bị ảnh hưởng.

Các khu vực cần kiểm tra:

- RestHighLevelClient và RequestOptions.
- SearchRequest/SearchResponse.
- IndexRequest, UpdateRequest, DeleteRequest.
- BulkRequest/BulkResponse.
- QueryBuilder và QueryBuilders.
- SortBuilder/SortBuilders.
- AggregationBuilder/AggregationBuilders.
- Script và ScriptType.
- HighlightBuilder.
- SearchSourceBuilder.
- Scroll và clear scroll.
- Index settings/mapping request.
- Low-level RestClient callbacks.
- Exception types và error parsing.

Java API Client dùng request/response model riêng. Có thể giữ một số REST endpoint thông qua low-level RestClient, nhưng nên giới hạn raw HTTP ở adapter riêng thay vì rải trong domain service.

## 16. Bulk operations sau migration

Nếu code dùng Spring Data ElasticsearchOperations.bulkIndex, bulkUpdate hoặc bulkDelete, kiểm tra signature và failure semantics ở version đích.

Nếu code gọi trực tiếp HLRC BulkRequest, chuyển sang Java API Client BulkRequest và BulkResponse:

~~~java
BulkResponse response = elasticsearchClient.bulk(request);

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() != null) {
            // classify this item failure
        }
    }
}
~~~

Đây là API mới ở mức khái niệm. Request operation builder, response item types và metadata phải theo client version. Bulk không phải transaction; vẫn phải xử lý item-level failures, retry subset và idempotency.

Đừng chỉ chuyển code compile được rồi coi migration hoàn tất. Kiểm tra các lỗi partial success và timeout mơ hồ.

## 17. Exception và error handling

Các exception có thể thay đổi package và kiểu giữa HLRC, Java API Client và Spring Data. Không nên bắt một exception cũ rồi cast exception mới.

Thiết kế error handling theo lớp:

1. Lỗi kết nối/transport.
2. Lỗi request serialization hoặc validation.
3. HTTP/API error từ Elasticsearch.
4. Item-level failure trong bulk.
5. Lỗi mapping/conversion của Spring Data.
6. Lỗi nghiệp vụ như not found hoặc version conflict.

Giữ nguyên status, error type, index, document ID và correlation ID trong log khi có thể. Không log credentials hoặc toàn bộ source nhạy cảm.

## 18. Quy trình migration an toàn

Một lộ trình có thể chia thành các giai đoạn:

### Giai đoạn 1: Kiểm kê

- Xác định Spring Boot, Spring Data Elasticsearch và Elasticsearch server versions.
- Lưu dependency tree.
- Tìm mọi import RestHighLevelClient, ElasticsearchRestTemplate, NativeSearchQuery và QueryBuilders.
- Tìm custom repository/template, bulk và low-level client usage.
- Ghi lại query quan trọng và response semantics.

### Giai đoạn 2: Nâng framework và client

- Chọn Spring Boot/Spring Data release train tương thích.
- Nâng Java runtime theo baseline của dòng mới.
- Dùng dependency management/BOM.
- Loại bỏ override client version không cần thiết.
- Cập nhật configuration class và transport.
- Xác nhận TLS/authentication/timeout.

### Giai đoạn 3: Giảm phụ thuộc implementation

- Inject ElasticsearchOperations thay vì ElasticsearchRestTemplate.
- Inject ReactiveElasticsearchOperations cho reactive service.
- Đưa raw client usage vào adapter riêng.
- Tách business query specification khỏi client builder nếu codebase lớn.

### Giai đoạn 4: Chuyển query

- Chuyển NativeSearchQuery sang NativeQuery.
- Chuyển QueryBuilders sang Java API Client DSL.
- Chuyển sort và aggregation.
- Kiểm tra highlight, suggest, script, kNN, runtime fields và query options.
- Giữ CriteriaQuery/StringQuery khi chúng đáp ứng yêu cầu.

### Giai đoạn 5: Chuyển các API khác

- Bulk operations.
- Index/mapping/settings.
- Scroll/PIT.
- Exception handling.
- Custom repository.
- Reactive stack.
- Monitoring và low-level HTTP.

### Giai đoạn 6: Kiểm thử và triển khai

- Chạy unit/integration tests.
- Xác nhận mapping và index lifecycle.
- So sánh query result với bản cũ.
- Đo latency/throughput.
- Test partial bulk failure và retry.
- Test authentication, TLS và timeout.
- Triển khai canary/rolling theo khả năng vận hành.
- Có kế hoạch rollback và quan sát lỗi sau deploy.

## 19. Kiểm thử tương đương query trước và sau migration

Một query compile thành công chưa chứng minh semantics giống bản cũ. Với từng query quan trọng, tạo fixture document và kiểm tra:

- Document IDs được trả về.
- Total hits và relation.
- Sort order.
- Filter behavior.
- Scoring nếu ứng dụng dùng score.
- Aggregation bucket/key/count.
- Highlight fields.
- Missing field behavior.
- Date/time zone.
- Nested query semantics.
- Pagination và tie-breaker.

Ví dụ cùng một tập dữ liệu:

~~~text
Product A: title="Spring Data", status=published
Product B: title="Spring Boot", status=draft
Product C: title="Elasticsearch", status=published
~~~

Query match title Spring Data và filter status published phải trả cùng document trước/sau migration. Đừng chỉ assert response không null.

### 19.1. Kiểm tra query JSON thực tế

Trong lúc migration, có thể log request DSL ở môi trường test hoặc dùng Elasticsearch profile/slow logs để xác nhận query mới được gửi đúng. Không bật logging payload nhạy cảm trong production.

So sánh cả semantics chứ không yêu cầu JSON builder output có cùng thứ tự field; hai DSL có thể khác hình thức nhưng tương đương behavior.

### 19.2. Test compatibility với cluster thật

Dùng Elasticsearch Testcontainers hoặc test cluster đúng major/minor tương ứng môi trường đích. Một mock Java client không phát hiện hết vấn đề về mapping, query rewrite, aggregation response hoặc server compatibility.

## 20. Các lỗi thường gặp khi nâng cấp

| Lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm thấy ElasticsearchRestTemplate | Đã chuyển sang dòng 5.x | Dùng ElasticsearchTemplate/ElasticsearchOperations |
| Không tìm thấy NativeSearchQuery | Native query API cũ không còn là lựa chọn mới | Dùng NativeQuery |
| Không tương thích QueryBuilder | QueryBuilder thuộc HLRC | Viết lại bằng Java API Client DSL |
| Không tìm thấy QueryBuilders | Import cũ không còn dependency | Dùng generated query DSL |
| RestHighLevelClient không được inject | Configuration/client stack mới | Dùng ElasticsearchClient hoặc operations |
| Hai bean operations cùng tồn tại | Cấu hình cũ và mới cùng đăng ký | Giữ một cấu hình rõ ràng |
| ClassNotFound/NoSuchMethod | Client/Spring Data version conflict | Dùng BOM và dependencyInsight |
| Query trả kết quả khác | Chuyển sai must/filter/should hoặc field path | Test semantics trên fixture |
| Aggregation result không đọc được | Response type mới khác HLRC | Dùng aggregate types mới hoặc Spring Data abstraction |
| Sort lỗi fielddata | Mapping/query mismatch đã tồn tại từ trước | Dùng keyword/doc values |
| TLS lỗi sau nâng cấp | Client transport/trust config thay đổi | Cấu hình SSLContext/truststore đúng |
| Repository dùng sai client | Nhiều configuration/template bean | Kiểm tra repository factory và bean wiring |
| Reactive request bị block | Dùng imperative client trong reactive flow | Dùng reactive operations/client |
| Bulk coi cả batch thành công | Bỏ qua response.errors/items | Xử lý từng item |

## 21. Chiến lược giảm rủi ro cho codebase lớn

Với ứng dụng lớn, không nên thay mọi query builder và template call trong một patch khó review.

Có thể chia:

- Một commit nâng dependency/configuration.
- Một commit chuyển injection sang operations interface.
- Các commit chuyển từng nhóm query.
- Một commit chuyển aggregation/bulk/raw client.
- Một commit xóa dependency và import HLRC còn sót.
- Một bước kiểm thử/benchmark trước release.

Có thể tạo adapter nội bộ cho các query dùng nhiều:

~~~java
public interface ProductSearchQueries {
    NativeQuery findPublishedProducts(String text, int page, int size);
}
~~~

Implementation mới dùng Java API Client DSL. Business service không cần biết query được xây bằng builder nào. Không tạo abstraction quá tổng quát chỉ để bọc mọi tính năng Elasticsearch; adapter nên thể hiện use case cụ thể.

## 22. Checklist trước khi hoàn tất migration

| Hạng mục | Điều cần xác nhận |
|---|---|
| Version matrix | Boot, Spring Data, Java, Elasticsearch server tương thích |
| Dependency BOM | Không override client version tùy tiện |
| Old HLRC imports | Không còn code phụ thuộc ngoài adapter có chủ đích |
| Template | Service dùng ElasticsearchOperations khi phù hợp |
| Native query | NativeSearchQuery đã được chuyển sang NativeQuery |
| Query DSL | Không còn QueryBuilder cũ trong code path mới |
| Sort/aggregation | Field path và result parsing đúng |
| Repository | Repository factory gắn đúng operations bean |
| Reactive | Không gọi imperative client/block trong reactive path |
| TLS/auth | Truststore, hostname verification và credentials đúng |
| Bulk | Item-level errors và retry được xử lý |
| Index mapping | Mapping thực tế đúng với entity/query |
| Tests | Query results, sort, aggregation và pagination tương đương |
| Observability | Metrics/logging không bị mất sau migration |
| Rollback | Có kế hoạch quay lại version/index tương thích |

## 23. Bảng tra cứu nhanh

| API cũ | Hướng thay thế |
|---|---|
| ElasticsearchRestTemplate | ElasticsearchTemplate trong dòng 5.x; ưu tiên inject ElasticsearchOperations |
| RestHighLevelClient | ElasticsearchClient |
| NativeSearchQuery | NativeQuery |
| NativeSearchQueryBuilder | NativeQuery.builder() |
| QueryBuilders | Java API Client Query DSL |
| AggregationBuilders | Java API Client Aggregation |
| SortBuilders | Spring Data Sort hoặc Java API Client SortOptions |
| SearchResponse HLRC | SearchHits abstraction hoặc Java API Client response |
| Abstract config dùng HLRC | ElasticsearchConfiguration theo ELC |
| Raw HLRC BulkRequest | Java API Client BulkRequest hoặc Spring Data bulk operations |
| Reactive concrete template | ReactiveElasticsearchOperations và implementation tương ứng version |

Khi thay API cũ của Spring Data Elasticsearch, hãy xác định chính xác release train trước. Dòng 4.x phổ biến với RestHighLevelClient, ElasticsearchRestTemplate và NativeSearchQuery; dòng 5.x chuyển sang Elasticsearch Java API Client, ElasticsearchTemplate và NativeQuery. ElasticsearchOperations là abstraction nên ưu tiên trong service để giảm phụ thuộc vào concrete template. QueryBuilder, aggregation và sort của HLRC không tương thích trực tiếp với Java API Client DSL; cần chuyển theo semantics và kiểm thử kết quả. Đồng bộ Spring Boot BOM, Java runtime, client và Elasticsearch server, sau đó rà soát cả bulk, reactive, mapping, TLS, exception và raw client usage. Migration hoàn tất khi query behavior, mapping, security và vận hành đã được xác nhận trên cluster đúng version, không chỉ khi source code biên dịch thành công.
