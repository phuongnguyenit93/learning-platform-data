# Chuyển từ TransportClient hoặc RestHighLevelClient sang client phù hợp

Elasticsearch đã thay đổi client Java qua nhiều thế hệ. Ứng dụng cũ có thể dùng `TransportClient` để kết nối trực tiếp tới node qua transport protocol, hoặc dùng `RestHighLevelClient` (HLRC) để gọi REST API bằng các request/response Java đã định kiểu. Với ứng dụng mới, hướng phát triển hiện tại là **Elasticsearch Java API Client** (`co.elastic.clients:elasticsearch-java`), sử dụng HTTP REST transport và cung cấp API Java có kiểu dữ liệu rõ ràng. Spring Data Elasticsearch cũng đã chuyển sang client mới ở các thế hệ hiện đại.

Việc chuyển client không chỉ là thay dependency. Cấu hình kết nối, xác thực/TLS, query builders, bulk response, aggregation, exception handling, serialization và lifecycle đóng tài nguyên đều có thể thay đổi. Cần xác định chính xác phiên bản Elasticsearch server, Spring Boot, Spring Data Elasticsearch và Java client trước khi sửa code.

Nếu ứng dụng dùng Spring Data Elasticsearch, phần lớn thao tác CRUD/search thông thường nên đi qua `ElasticsearchRepository`, `ElasticsearchOperations` hoặc `ReactiveElasticsearchOperations`. Java API Client có thể dùng cho API mới chưa được abstraction bao phủ. Giữ ranh giới này giúp domain/service không phụ thuộc trực tiếp vào kiểu request/response của một client cụ thể.

## 1. Ba thế hệ client cần phân biệt

| Client | Giao thức | Đặc điểm | Trạng thái định hướng |
|---|---|---|---|
| `TransportClient` | Elasticsearch transport protocol, thường qua cổng 9300 | Kết nối node/cluster trực tiếp, discovery và cluster settings; API cũ | Deprecated từ Elasticsearch 7.0 và bị loại bỏ ở Elasticsearch 8.0 |
| `RestHighLevelClient` | HTTP REST, thường qua cổng 9200 | Request/response Java có kiểu, xây trên Low Level REST Client | Deprecated từ Elasticsearch 7.15; được thay thế bởi Java API Client |
| Elasticsearch Java API Client | HTTP REST | API Java hiện đại, typed builders, typed responses, sync và async | Client được khuyến nghị cho phát triển mới; chọn version tương thích server |

Ngoài ra còn có **Low Level REST Client** (`org.elasticsearch.client:elasticsearch-rest-client`). Đây là HTTP client cấp thấp để gửi `Request` và nhận `Response`. HLRC được xây trên Low Level REST Client; Java API Client dùng REST transport để gửi request nhưng có lớp API Java typed riêng.

### Không nhầm cổng transport và HTTP

- TransportClient thường kết nối transport port, mặc định thường là `9300`.
- REST clients kết nối HTTP/HTTPS endpoint, thường là `9200`.
- Khi chuyển từ TransportClient sang REST client, cần mở đúng network route/firewall, cập nhật endpoint và xác thực TLS/HTTP.
- Không thể thay `9300` bằng `9200` trong cùng cấu hình rồi kỳ vọng TransportClient hoạt động; đây là hai giao thức khác nhau.

## 2. Vì sao phải rời TransportClient?

TransportClient từng là cách phổ biến để ứng dụng Java kết nối trực tiếp tới Elasticsearch cluster. Client sử dụng transport protocol nội bộ, có thể biết cluster name, nhận node discovery và gửi request tới các node.

Các nhược điểm trong kiến trúc hiện đại:

- TransportClient gắn chặt với giao thức nội bộ và compatibility của Elasticsearch.
- Ứng dụng phải phụ thuộc vào các node transport có thể truy cập được.
- Cấu hình cluster discovery/sniffing có thể không phù hợp với proxy, managed service hoặc môi trường cloud.
- Việc nâng cấp server và client có ràng buộc version chặt hơn.
- TransportClient đã bị loại bỏ trong Elasticsearch 8.0.

Ứng dụng dùng TransportClient không thể kết nối trực tiếp tới Elasticsearch 8 bằng client cũ. Cần chuyển sang HTTP REST client trước khi nâng server lên phiên bản không còn transport protocol.

### Cấu hình cũ minh họa

```java
Settings settings = Settings.builder()
    .put("cluster.name", "search-cluster")
    .build();

TransportClient client = new PreBuiltTransportClient(settings)
    .addTransportAddress(
        new TransportAddress(
            InetAddress.getByName("es-node-1"),
            9300
        )
    );
```

Code này phụ thuộc các lớp transport cũ. Khi chuyển, không giữ `Settings`, `PreBuiltTransportClient` hoặc `TransportAddress` trong cấu hình mới. Thay bằng HTTP endpoint, TLS và cơ chế xác thực mà cluster yêu cầu.

## 3. Vì sao nên thay RestHighLevelClient?

HLRC cung cấp API typed cho search, index, update, delete, bulk, aggregation và nhiều API quản trị. Nó giúp lập trình Java thuận tiện hơn so với việc tự tạo JSON REST request. Tuy nhiên, Elastic đã đánh dấu HLRC deprecated từ Elasticsearch 7.15 và giới thiệu Java API Client làm hướng thay thế.

Những điểm cần lưu ý:

- HLRC dùng các kiểu như `SearchRequest`, `SearchSourceBuilder`, `SearchResponse`, `BulkRequest` và `RequestOptions`.
- Java API Client dùng các kiểu mới trong package `co.elastic.clients.elasticsearch.*`.
- Request builder, response model, query DSL và aggregation variant không tương thích trực tiếp.
- Không thể chỉ đổi import từ `org.elasticsearch.*` sang `co.elastic.clients.*`.
- Các tính năng API mới được phát triển trên Java API Client.

Nếu ứng dụng đang chạy trên một phiên bản Elasticsearch cũ, có thể cần một giai đoạn chuyển tiếp. Nhưng không nên lấy HLRC làm đích kiến trúc dài hạn cho hệ thống mới. Hãy chọn client và Spring Data version theo compatibility matrix đang được hỗ trợ.

## 4. Vai trò của Low Level REST Client

Low Level REST Client là HTTP client cấp thấp:

```java
RestClient restClient = RestClient.builder(
    new HttpHost("localhost", 9200, "http")
).build();

Request request = new Request("GET", "/products/_search");
request.setJsonEntity("""
    {
      "query": {
        "match": {
          "name": "wireless mouse"
        }
      }
    }
    """);

Response response = restClient.performRequest(request);
```

Ứng dụng phải tự xây JSON, quản lý response body, status và deserialize. Đây là lựa chọn khi cần REST endpoint đặc biệt chưa được client typed hỗ trợ hoặc khi viết integration rất thấp cấp.

Với phần lớn use case search/index, Java API Client giảm công việc thủ công nhờ request builder và typed response. Spring Data Elasticsearch còn cung cấp abstraction cao hơn cho repository, mapping và template operations.

## 5. Java API Client là gì?

Elasticsearch Java API Client được cung cấp qua artifact:

`co.elastic.clients:elasticsearch-java`

Client cung cấp:

- Java API typed cho các Elasticsearch REST API.
- Builder lambda để dựng request.
- Typed response cho document class được chỉ định.
- Query DSL và aggregation theo mô hình dữ liệu của client.
- API đồng bộ `ElasticsearchClient`.
- API bất đồng bộ `ElasticsearchAsyncClient`, thường trả `CompletableFuture`.
- JSON-P mapping thông qua `JsonpMapper`, có thể dùng `JacksonJsonpMapper`.

Java API Client sử dụng REST transport. Trong cấu hình truyền thống, `RestClientTransport` kết hợp Low Level REST Client và `JacksonJsonpMapper`:

```java
RestClient restClient = RestClient.builder(
    new HttpHost("localhost", 9200, "http")
).build();

ElasticsearchTransport transport =
    new RestClientTransport(
        restClient,
        new JacksonJsonpMapper()
    );

ElasticsearchClient client = new ElasticsearchClient(transport);
```

Đoạn code minh họa cách dựng client thủ công. Nếu dùng Spring Boot hoặc Spring Data Elasticsearch, ưu tiên auto-configuration hoặc `ClientConfiguration` của framework để tránh tạo nhiều connection pool/client không cần thiết.

## 6. Chọn phiên bản client theo phiên bản server và Spring Data

Không nên nâng riêng một dependency mà không kiểm tra cả bộ phiên bản. Có ít nhất bốn thành phần liên quan:

1. Elasticsearch server.
2. Spring Boot.
3. Spring Data Elasticsearch.
4. Elasticsearch Java API Client và REST transport mà Spring Data sử dụng.

Các thế hệ Spring Data Elasticsearch khác nhau dùng client khác nhau. Những nhánh Spring Data Elasticsearch 4.x gắn với hệ sinh thái Elasticsearch 7 và HLRC; nhánh 5.x chuyển sang Elasticsearch Java API Client cho hệ sinh thái Elasticsearch 8. Các nhánh mới hơn có thể thay đổi yêu cầu Java, Spring Framework và Elasticsearch server.

| Bối cảnh | Định hướng |
|---|---|
| Ứng dụng Spring Data Elasticsearch 4.x | Thường dựa trên HLRC; kiểm tra compatibility matrix và kế hoạch nâng Spring Data |
| Ứng dụng Spring Data Elasticsearch 5.x | Dùng Java API Client; không tự thêm HLRC để viết code mới |
| Ứng dụng Spring Boot mới | Dùng starter/BOM tương ứng và để dependency management chọn các phiên bản tương thích |
| Ứng dụng gọi REST API trực tiếp | Dùng Java API Client phù hợp với server hoặc Low Level REST Client cho trường hợp thực sự cần low-level |
| Ứng dụng đang dùng TransportClient | Chuyển sang REST trước khi nâng tới Elasticsearch 8 trở lên |

Đây là định hướng theo thế hệ, không phải bảng cam kết mọi minor version đều tương thích với mọi server. Trước khi nâng, kiểm tra ma trận tương thích và tài liệu phát hành của chính phiên bản dự án.

### Dùng BOM thay vì tự ghim từng jar

Với Spring Boot, nên để Spring Boot dependency management quản lý Spring Data, Spring Framework, Reactor và các client liên quan. Tránh thêm một version `elasticsearch-java` mới hơn hoặc thấp hơn tùy ý so với version Spring Data đã kiểm thử.

Nếu cần override version, phải có lý do, kiểm tra binary/API compatibility và chạy integration tests với đúng Elasticsearch server.

## 7. Kiểm kê dependency trước khi migration

Trước khi sửa code, xác định client đang được kéo vào trực tiếp hay gián tiếp:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Hoặc lọc dependency:

```bash
./gradlew dependencyInsight \
  --dependency elasticsearch \
  --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree
```

Tìm các artifact thường gặp:

| Artifact/package | Ý nghĩa |
|---|---|
| `org.elasticsearch:elasticsearch` | Core/server-related Java classes được một số client cũ dùng |
| `org.elasticsearch.client:transport` | TransportClient cũ |
| `org.elasticsearch.client:elasticsearch-rest-high-level-client` | HLRC |
| `org.elasticsearch.client:elasticsearch-rest-client` | Low Level REST Client |
| `co.elastic.clients:elasticsearch-java` | Java API Client |
| `spring-data-elasticsearch` | Spring Data repository/template abstraction |

Không xóa một dependency chỉ dựa vào tên. Kiểm tra dependency graph để biết thư viện nào còn cần nó và version nào đang được resolve. Tránh để hai thế hệ client cùng tồn tại nếu không có nhu cầu chuyển tiếp rõ ràng.

## 8. Tìm toàn bộ code phụ thuộc client cũ

Tìm imports và API cũ trong source:

```bash
rg -n "TransportClient|PreBuiltTransportClient|TransportAddress|Settings\\.builder" .
rg -n "RestHighLevelClient|RequestOptions|SearchSourceBuilder|SearchRequest|BulkRequest" .
rg -n "org\\.elasticsearch\\.action|org\\.elasticsearch\\.search\\.builder|org\\.elasticsearch\\.client" .
```

Phân loại nơi sử dụng:

- Cấu hình kết nối và lifecycle.
- Repository/custom repository.
- Search query builder.
- Aggregation, sort, highlight và suggest.
- Bulk/index/update/delete.
- Index/template/alias management.
- Exception mapping và retry.
- Custom serializer/deserializer.
- Test fixture và mock.

Không chỉ tìm constructor client. Các kiểu request/response cũ có thể nằm sâu trong service, mapper, test hoặc interface public.

## 9. Thay đổi cấu hình kết nối

TransportClient thường cần cluster name, transport address và có thể có sniffing. REST client cần URI HTTP/HTTPS, TLS, credentials/API key và các timeout/connection settings.

| Cấu hình cũ | Cấu hình REST mới |
|---|---|
| Cluster name | Thường không cần khai báo trong client REST |
| Transport address, port 9300 | HTTP/HTTPS URI, thường port 9200 |
| Transport sniffing | Load balancer/service discovery/DNS phù hợp với môi trường |
| Transport-level security | HTTPS/TLS và HTTP authentication |
| Node list nội bộ | Một hoặc nhiều REST endpoint được client hỗ trợ |
| Transport connection settings | HTTP connection pool, connect/response timeout và retry policy |

Không chuyển nguyên `cluster.name` hoặc transport sniff settings sang REST client. Thiết kế kết nối mới theo cách cluster được triển khai: self-managed, Kubernetes, cloud service hoặc managed Elasticsearch.

## 10. Cấu hình Spring Boot bằng properties

Với Spring Boot có auto-configuration cho Elasticsearch, cấu hình thường được đặt trong `application.yml`:

```yaml
spring:
  elasticsearch:
    uris:
      - https://es.example.internal:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 5s
    socket-timeout: 30s
```

Tên property và kiểu giá trị phụ thuộc Spring Boot version. Kiểm tra configuration metadata/reference đúng phiên bản trước khi dùng. Nếu dùng API key hoặc certificate authentication, cấu hình theo hỗ trợ của version hoặc cung cấp custom client configuration phù hợp.

Không hard-code password, API key hoặc private key trong source/config được commit. Dùng secret manager, environment variables hoặc cơ chế quản lý secret của nền tảng.

### Khi nào dùng auto-configuration?

Auto-configuration phù hợp khi:

- Chỉ cần một client/connection configuration chính.
- Endpoint, auth và timeout có thể cấu hình qua properties.
- Không cần custom transport phức tạp.
- Muốn Spring Boot quản lý lifecycle bean.

Không tạo thêm một client thủ công song song nếu auto-configuration đã cung cấp đúng bean. Hai client có thể tạo hai connection pool, tăng socket/memory và làm health/metrics khó hiểu.

## 11. Cấu hình Spring Data Elasticsearch bằng ClientConfiguration

Khi cần cấu hình tùy chỉnh, Spring Data Elasticsearch cung cấp `ClientConfiguration` và configuration base class tương ứng version.

Ví dụ cho cấu hình imperative:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("es.example.internal:9200")
            .usingSsl()
            .withBasicAuth(
                System.getenv("ELASTICSEARCH_USERNAME"),
                System.getenv("ELASTICSEARCH_PASSWORD")
            )
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(30))
            .build();
    }
}
```

Package/class và các builder option thay đổi theo Spring Data Elasticsearch version. Đối chiếu Javadoc của dependency thực tế. Nếu Spring Boot auto-configuration đã được tùy biến qua properties, đừng đồng thời tạo một cấu hình khác mà không hiểu bean nào đang được sử dụng.

### TLS và certificate validation

Trong production, dùng HTTPS và xác minh certificate chain/hostname. Không tắt certificate validation chỉ để kết nối được trong môi trường thật. Nếu cluster dùng CA riêng, cấu hình trust store/SSL context theo cơ chế được client/framework hỗ trợ.

Không dùng `usingSsl()` như bằng chứng rằng mọi certificate đã được cấu hình đúng. Kiểm tra CA, hostname, certificate expiry và TLS policy trong deployment thực tế.

## 12. TransportClient sniffing và REST discovery

TransportClient có thể sniff cluster để biết node addresses. Trong môi trường cloud, Kubernetes, proxy hoặc managed service, việc client tự kết nối tới node IP được quảng bá có thể thất bại vì:

- Node publish address không truy cập được từ application network.
- Chỉ một endpoint gateway được phép truy cập.
- TLS certificate không khớp hostname node nội bộ.
- Managed service không cho ứng dụng truy cập transport port.
- Pod/node IP thay đổi theo lifecycle.

Với REST client, thường dùng DNS/service endpoint hoặc load balancer được nền tảng cung cấp. Cần bảo đảm các REST endpoint trả lời ổn định và connection pool có thể phân phối request đúng cách.

Không bật sniffing chỉ vì cấu hình cũ từng dùng nó. Nếu dùng cơ chế node discovery, kiểm tra rõ server publish address, TLS identity, routing và network policy.

## 13. Từ HLRC sang Java API Client: thay đổi kiểu dữ liệu

Ví dụ search bằng HLRC:

```java
SearchRequest request = new SearchRequest("products");
SearchSourceBuilder source = new SearchSourceBuilder()
    .query(QueryBuilders.matchQuery("name", "wireless mouse"))
    .size(20);
request.source(source);

SearchResponse response =
    highLevelClient.search(request, RequestOptions.DEFAULT);
```

Với Java API Client:

```java
SearchResponse<ProductDocument> response = client.search(
    search -> search
        .index("products")
        .size(20)
        .query(query -> query
            .match(match -> match
                .field("name")
                .query("wireless mouse")
            )
        ),
    ProductDocument.class
);
```

Khác biệt chính:

- Request được xây bằng builder lambda hoặc builder object của Java API Client.
- Query DSL được biểu diễn qua các variant typed như `match`, `term`, `bool`, `range`.
- Kiểu response thường có generic document class.
- Không còn `RequestOptions.DEFAULT` theo cách HLRC sử dụng.
- Không tái sử dụng `SearchSourceBuilder` hoặc `QueryBuilders` cũ.

## 14. Chuyển QueryBuilders sang typed Query DSL

Ví dụ HLRC:

```java
QueryBuilder query = QueryBuilders.boolQuery()
    .must(QueryBuilders.matchQuery("name", "mouse"))
    .filter(QueryBuilders.termQuery("status", "ACTIVE"))
    .filter(QueryBuilders.rangeQuery("price").lte(100));
```

Java API Client:

```java
Query query = Query.of(q -> q.bool(b -> b
    .must(m -> m.match(mm -> mm
        .field("name")
        .query("mouse")
    ))
    .filter(f -> f.term(t -> t
        .field("status")
        .value("ACTIVE")
    ))
    .filter(f -> f.range(r -> r
        .number(n -> n
            .field("price")
            .lte(100.0)
        )
    ))
));
```

Các kiểu scalar, range và builder overload có thể khác theo client version. Dùng compiler và Javadoc để chọn đúng variant. Không chuyển một query bằng cách đổi tên class rồi bỏ qua semantics của `must`, `filter`, `should`, `minimum_should_match` hoặc score.

### Lợi ích của typed DSL

- IDE autocomplete tốt hơn.
- Compiler phát hiện nhiều lỗi cấu trúc.
- Ít lỗi JSON field/operator do nối chuỗi.
- Response typed giúp giảm parsing thủ công.
- Dễ tạo helper/query factory dùng lại.

Tuy vậy, typed DSL không bảo đảm query đúng nghiệp vụ. Cần test query behavior trên Elasticsearch thật với mapping và dữ liệu đại diện.

## 15. Chuyển SearchResponse và hit mapping

HLRC thường trả `SearchResponse` chứa `SearchHits`, mỗi hit có `_id`, `_source`, score, sort values và metadata.

Java API Client trả `SearchResponse<TDocument>` với danh sách hits typed:

```java
SearchResponse<ProductDocument> response = client.search(
    s -> s.index("products")
        .query(q -> q.match(m -> m.field("name").query("mouse"))),
    ProductDocument.class
);

for (Hit<ProductDocument> hit : response.hits().hits()) {
    String id = hit.id();
    float score = hit.score() == null ? 0.0f : hit.score();
    ProductDocument product = hit.source();
}
```

Khi migration, kiểm tra:

- `_source` có thể null nếu request không trả source hoặc mapping thất bại.
- Score có thể null với query/context không có scoring.
- Sort values cần đọc đúng kiểu JSON value.
- Highlight, inner hits, matched queries và explanation có cấu trúc mới.
- `total` có relation như `eq` hoặc `gte`; không luôn là số đếm chính xác nếu giới hạn total hits.
- Nếu dùng field collapse hoặc aggregations, response accessors khác HLRC.

Đừng giả định tổng số hits luôn là `long` chính xác như cách code cũ đọc. Kiểm tra `track_total_hits` và relation của response.

## 16. Chuyển aggregation

HLRC dùng các lớp như `TermsAggregationBuilder`, `DateHistogramAggregationBuilder`, `AggregationBuilders` và các kiểu response `ParsedTerms`, `ParsedDateHistogram`.

Java API Client dùng typed aggregation builders và response variants:

```java
SearchResponse<ProductDocument> response = client.search(
    s -> s.index("products")
        .size(0)
        .aggregations("by_status", a -> a
            .terms(t -> t.field("status"))
        ),
    ProductDocument.class
);

Aggregate aggregate = response.aggregations().get("by_status");
if (aggregate != null && aggregate.isSterms()) {
    for (StringTermsBucket bucket : aggregate.sterms().buckets().array()) {
        String key = bucket.key().stringValue();
        long count = bucket.docCount();
    }
}
```

Đoạn code minh họa một terms aggregation trên keyword field. Kiểu variant phụ thuộc mapping và API version; terms aggregation có các biến thể khác nhau theo kiểu field. Cần đọc đúng variant thay vì ép kiểu response như HLRC.

### Kiểm tra bucket và count

- `docCount` là số document trong bucket.
- `sum_other_doc_count` có thể cho biết document thuộc các bucket không được trả về.
- `terms.size` giới hạn số bucket trả về, không nhất thiết liệt kê mọi giá trị.
- Composite aggregation có semantics phân trang bucket khác terms aggregation.
- Filter aggregation, nested aggregation và global aggregation cần được kiểm tra lại scope.

Migration aggregation cần so sánh kết quả trên fixture giống nhau giữa client cũ và mới.

## 17. Chuyển Bulk API

HLRC:

```java
BulkRequest request = new BulkRequest();
request.add(new IndexRequest("products")
    .id(product.getId())
    .source(jsonSource, XContentType.JSON));

BulkResponse response =
    highLevelClient.bulk(request, RequestOptions.DEFAULT);
```

Java API Client:

```java
BulkResponse response = client.bulk(bulk -> bulk
    .operations(operation -> operation
        .index(index -> index
            .index("products")
            .id(product.getId())
            .document(product)
        )
    )
);

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() != null) {
            // Record item.id(), item.status() and item.error().
        }
    }
}
```

Java API Client cho phép serialize object trực tiếp qua mapper. Nếu source có custom conversion, kiểm tra `JsonpMapper` và mapping để dữ liệu gửi lên không đổi ngoài ý muốn.

### Partial failures vẫn phải được xử lý

Bulk API không phải transaction. `errors()` có thể true dù request tổng thể đã được xử lý. Duyệt từng item, phân loại mapping error, conflict, 429 và lỗi tạm thời. Chỉ retry item có thể retry an toàn; không đánh dấu toàn batch thành công chỉ vì HTTP request trả response.

## 18. Chuyển Index, Update và Delete API

Các request/response cũ không tương thích trực tiếp với Java API Client. Ví dụ:

| HLRC | Java API Client |
|---|---|
| `IndexRequest` | `IndexRequest<TDocument>` builder |
| `UpdateRequest` | `UpdateRequest<TDocument, TPartialDocument>` builder |
| `DeleteRequest` | `DeleteRequest` builder |
| `GetRequest` | `GetRequest` builder |
| `BulkRequest` | `BulkRequest` builder với `operations` |
| `RequestOptions` | Transport/client configuration và request options mới theo API |

Với update, cần kiểm tra cách serialize `doc`, `upsert`, script và retry-on-conflict. Với delete, kiểm tra routing và optimistic concurrency metadata. Không giả định các default giống HLRC.

## 19. Chuyển index/template/alias APIs

Ứng dụng có thể dùng HLRC để tạo index, mapping, template, alias và kiểm tra cluster. Java API Client tổ chức các API này theo namespace typed:

```java
CreateIndexResponse response = client.indices().create(
    create -> create
        .index("products-v2")
        .mappings(mapping -> mapping
            .properties("name", property -> property
                .text(text -> text)
            )
            .properties("status", property -> property
                .keyword(keyword -> keyword)
            )
        )
);
```

Trong Spring Data Elasticsearch, có thể dùng `IndexOperations` qua `ElasticsearchOperations` cho nhiều thao tác index lifecycle:

```java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping();
}
```

Không nên để mỗi application instance tự tạo/đổi mapping trong startup nếu deployment yêu cầu migration có kiểm soát. Index template, alias switch và reindex thường nên được quản lý như một bước release/infra có chủ đích.

## 20. Exception handling thay đổi

HLRC có các exception và response status theo API cũ, ví dụ `ElasticsearchException`, `ElasticsearchStatusException` hoặc `ResponseException` ở tầng low-level. Java API Client và transport có exception model khác.

Khi migration, rà soát:

- HTTP status và error type.
- Error body/caused-by.
- Version conflict.
- Resource not found.
- Authentication/authorization failures.
- Connection timeout, socket timeout và connection reset.
- Serialization/deserialization errors.
- Request rejected và cluster overload.

Không bắt mọi exception rồi chuyển thành `Optional.empty()` hoặc HTTP 200. Điều đó có thể che giấu lỗi kết nối, mapping hoặc authorization.

### Tạo application-level exception

Một cách giảm phụ thuộc client là chuyển exception ở adapter/repository boundary sang exception nghiệp vụ:

```java
try {
    return client.get(request, ProductDocument.class);
} catch (ElasticsearchException ex) {
    if (isNotFound(ex)) {
        throw new ProductNotFoundException(productId);
    }
    throw new SearchInfrastructureException("Elasticsearch get failed", ex);
}
```

Tên method/accessor để phân loại exception phụ thuộc client version. Ví dụ chỉ minh họa nguyên tắc: domain/service không nên phải import exception của HLRC hoặc Java API Client ở mọi nơi.

## 21. Serialization và mapping

Đây là một trong những vùng dễ phát sinh lỗi migration. HLRC thường dùng `XContentBuilder`, `XContentType`, `XContentParser` hoặc serializer riêng. Java API Client dùng JSON-P và `JsonpMapper`, thường cấu hình `JacksonJsonpMapper`.

Kiểm tra các kiểu dữ liệu:

- `Instant`, `LocalDate`, `OffsetDateTime` và date format.
- Enum serialization.
- Null handling và field omission.
- `BigDecimal`, integer và floating point.
- Nested object và collection.
- Custom field name/alias.
- Geo types và binary values.
- Unknown fields trong response.
- Custom Jackson modules và naming strategy.

### Dùng JacksonJsonpMapper

Ví dụ cấu hình mapper:

```java
ObjectMapper objectMapper = new ObjectMapper()
    .findAndRegisterModules();

JsonpMapper jsonpMapper = new JacksonJsonpMapper(objectMapper);
```

Mapper này cho phép Java API Client dùng Jackson cho JSON mapping. Nếu ứng dụng dùng Java Time module, naming strategy hoặc custom serializers, hãy xác nhận các module được đăng ký và áp dụng đúng với client.

Spring Data Elasticsearch có mapping/conversion infrastructure riêng cho entity repository. Không giả định Jackson annotations, Spring Data `@Field` và JSON-P mapping có semantics hoàn toàn giống nhau trong mọi đường gọi. Nếu cùng một POJO được ghi qua Spring Data và Java API Client trực tiếp, test serialization của cả hai đường.

## 22. Phân biệt Spring Data mapping và client mapping

Spring Data Elasticsearch cung cấp:

- `@Document` để mô tả index.
- `@Id` để ánh xạ document ID.
- `@Field` để định nghĩa field mapping.
- Custom conversions và entity callbacks.
- `ElasticsearchRepository`.
- `ElasticsearchOperations` và `ReactiveElasticsearchOperations`.

Java API Client trực tiếp dùng `JsonpMapper` để serialize/deserialize source. Nó không tự chạy toàn bộ Spring Data entity conversion/callback pipeline.

Điều này có nghĩa:

- Ghi qua `ElasticsearchOperations.save()` có thể áp dụng Spring Data conversions/callbacks.
- Ghi trực tiếp bằng `ElasticsearchClient.index()` dùng mapper của Java API Client.
- Cùng entity có thể serialize khác nhau nếu hai cấu hình mapping khác nhau.
- Nếu cần dùng client trực tiếp, hãy dùng DTO/document model rõ ràng và test JSON output.

Không trộn hai đường ghi cho cùng index nếu chưa bảo đảm schema/source tương thích.

## 23. Khi nào dùng Spring Data abstraction, khi nào gọi Java API Client trực tiếp?

| Use case | Lựa chọn phù hợp |
|---|---|
| CRUD document thông thường | `ElasticsearchRepository` |
| Custom search query, aggregation và template operation | `ElasticsearchOperations` |
| Reactive repository/search | `ReactiveElasticsearchRepository`, `ReactiveElasticsearchOperations` |
| API Elasticsearch mới chưa được Spring Data abstraction bọc | Java API Client |
| REST endpoint đặc biệt hoặc API chưa có typed support | Low Level REST Client, có kiểm soát |
| Business logic/domain service | Nên phụ thuộc application port/service, không phụ thuộc client request types |

Không cần gọi Java API Client trực tiếp chỉ để dùng `match` hoặc `term` query nếu Spring Data `NativeQuery` đã đáp ứng. Dùng abstraction của Spring Data giúp giữ mapping, repository conventions và lifecycle tích hợp.

## 24. Chuyển custom repository

Nếu code cũ inject `RestHighLevelClient` vào repository:

```java
public class ProductSearchRepositoryImpl {
    private final RestHighLevelClient client;

    // Builds SearchRequest and parses SearchResponse
}
```

Có thể chuyển sang `ElasticsearchOperations`:

```java
public class ProductSearchRepositoryImpl {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(Query query) {
        return operations.search(
            query,
            ProductDocument.class,
            IndexCoordinates.of("products")
        );
    }
}
```

`Query` có thể được tạo bằng `NativeQuery`:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless mouse")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
```

Tên package/import và builder phụ thuộc Spring Data version. Custom repository fragment nên giữ API nghiệp vụ ổn định, còn implementation có thể thay đổi từ HLRC sang Spring Data/Java API Client.

## 25. Reactive client không đồng nghĩa với Java API Client async

Java API Client cung cấp `ElasticsearchAsyncClient` dựa trên `CompletableFuture`. Đây là API bất đồng bộ, nhưng không tự tạo Reactive Streams `Mono`/`Flux` với backpressure.

Ví dụ async:

```java
ElasticsearchAsyncClient asyncClient =
    new ElasticsearchAsyncClient(transport);

CompletableFuture<SearchResponse<ProductDocument>> future =
    asyncClient.search(
        request,
        ProductDocument.class
    );
```

Nếu cần tích hợp với Reactor, có thể chuyển `CompletableFuture` thành `Mono`:

```java
Mono<SearchResponse<ProductDocument>> result =
    Mono.fromFuture(() -> asyncClient.search(request, ProductDocument.class));
```

Nhưng cần hiểu cancellation semantics, executor, connection lifecycle và backpressure. `Mono.fromFuture` chỉ biểu diễn một future thành publisher; nó không biến một API request đơn lẻ thành stream có khả năng điều khiển demand từng document.

Spring Data Elasticsearch có reactive client/operations riêng cho reactive repository. Nếu ứng dụng cần Reactive Streams xuyên suốt, ưu tiên `ReactiveElasticsearchOperations` thay vì tự bọc async client ở nhiều nơi. Kiểm tra đúng reactive transport/client version được Spring Data hỗ trợ.

## 26. Quản lý lifecycle và đóng client

Client và transport sở hữu connection pool, thread hoặc resource liên quan. Khi tạo thủ công, cần đóng đúng resource khi application context dừng:

```java
@Bean(destroyMethod = "close")
RestClient restClient() {
    return RestClient.builder(
        new HttpHost("localhost", 9200, "http")
    ).build();
}
```

Với Java API Client thủ công, cần quản lý cả transport và underlying RestClient theo hướng dẫn của client/version. Không tạo client mới trong mỗi method call hoặc mỗi request; hãy dùng singleton bean được quản lý bởi Spring.

Nếu Spring Boot/Spring Data đã quản lý lifecycle client, không tự đóng bean dùng chung ở một service. Đóng client quá sớm sẽ làm các request khác lỗi; không đóng client khi shutdown có thể để lại thread/socket.

## 27. Timeout, retry và connection pool

Các cấu hình TransportClient không chuyển nguyên sang REST. Cần thiết kế:

- Connection timeout: thời gian thiết lập kết nối.
- Socket/response timeout: thời gian chờ phản hồi.
- Connection pool size và per-route limits.
- Connection keep-alive và stale connection handling.
- Retry policy cho lỗi mạng/tạm thời.
- Node selection/load balancing.
- Request timeout cho API cụ thể nếu được hỗ trợ.

Không retry mọi lỗi. Với index/update có ID ổn định, retry có thể idempotent tùy semantics; với script increment hoặc thao tác không idempotent, retry có thể lặp side effect. Timeout cũng không chứng minh server chưa thực hiện request.

Đặt timeout theo workload: autocomplete và search tương tác thường có deadline ngắn hơn export hoặc batch. Không đặt timeout quá cao để che giấu query chậm hoặc cluster overload.

## 28. Authentication và TLS

TransportClient cũ có thể dùng plugin/security transport settings riêng. REST migration phải chuyển sang cơ chế HTTP phù hợp:

- HTTPS/TLS.
- Basic authentication hoặc API key.
- CA certificate/trust store.
- Client certificate nếu môi trường yêu cầu mutual TLS.
- Credential rotation.
- Least-privilege role/index privileges.

Không truyền username/password trong URL. Không log Authorization header hoặc API key. Không tắt hostname verification/certificate validation trong production.

### Kiểm tra TLS

Trước khi rollout:

1. Xác nhận endpoint dùng `https`.
2. Xác nhận CA được trust.
3. Xác nhận hostname khớp certificate.
4. Xác nhận certificate chưa hết hạn.
5. Kiểm tra credential có quyền đúng index/API.
6. Kiểm tra rotation không yêu cầu restart ngoài kế hoạch.

## 29. Search semantics cần giữ nguyên trong migration

Một query có thể compile thành request hợp lệ nhưng trả kết quả khác sau khi migration. Các điểm cần so sánh:

- `must`, `filter`, `should`, `must_not`.
- `minimum_should_match`.
- Analyzer và multi-fields.
- Fuzziness, prefix và wildcard.
- Sort và missing value behavior.
- Nested query/inner hits.
- Highlight fields and fragment settings.
- `track_total_hits`.
- Pagination `from/size`, `search_after` và PIT.
- Runtime mappings và script fields.
- Routing và preference.
- Source filtering.
- Timeout và terminate-after.

Hãy giữ query semantics ở mức nghiệp vụ, tạo test fixtures và so sánh kết quả giữa client cũ/mới trên cùng cluster/index. Không dùng snapshot JSON của request làm bằng chứng duy nhất nếu server semantics cũng thay đổi theo version.

## 30. Search after, PIT và scroll

Các ứng dụng export hoặc phân trang sâu có thể dùng Scroll, `search_after` hoặc Point in Time. API typed mới biểu diễn các request/response này khác HLRC.

Khi chuyển:

- Giữ nguyên sort ổn định và tie-breaker.
- Giữ PIT ID giữa các trang nếu dùng PIT.
- Cập nhật PIT ID nếu response trả ID mới.
- Đóng PIT khi hoàn tất/cancel.
- Kiểm tra scroll keep-alive và cleanup.
- Không trộn `from/size` sâu với `search_after`.
- Test cancellation và lỗi giữa chừng.

Đừng chỉ chuyển tên method. Semantics của cursor, sort values và lifecycle snapshot phải được giữ nguyên.

## 31. Query templates, scripts và runtime fields

Nếu ứng dụng dùng stored search templates, Painless scripts hoặc runtime mappings, kiểm tra cách request builder mới biểu diễn các cấu trúc này. Một số kiểu JSON tổng quát có thể được truyền dưới dạng `JsonData`, nhưng điều đó không có nghĩa mọi giá trị Java được serialize đúng nếu mapper chưa cấu hình.

Nguyên tắc:

- Giữ script source cố định và truyền dữ liệu qua params.
- Không nhận script source tùy ý từ client public.
- Kiểm tra stored script ID và quyền truy cập.
- Test runtime field type và query behavior.
- Kiểm tra template parameters sau migration.

## 32. Xử lý JSON và JsonData

Java API Client dùng `JsonData` cho dữ liệu JSON động trong một số API. Nó hữu ích khi cấu trúc dữ liệu không biết trước ở compile time, nhưng giảm mức type safety so với POJO.

Ví dụ:

```java
JsonData scriptParam = JsonData.of(Map.of(
    "minimumPrice", 10,
    "maximumPrice", 100
));
```

Nếu sử dụng custom mapper, cần bảo đảm `JsonData` serialize/deserialize với cùng `JsonpMapper` mong muốn. Không chuyển mọi entity sang `Map<String, Object>` nếu domain model đã có kiểu rõ ràng; giữ typed model khi có thể.

## 33. Test migration theo tầng

Một kế hoạch test phù hợp nên có:

### Unit tests

- Query factory tạo đúng filter và operator.
- Mapper chuyển entity sang document đúng.
- Error adapter phân loại timeout/conflict/validation.
- Retry chỉ áp dụng cho lỗi được cho phép.
- Bulk response parser xử lý partial failure.
- Service không phụ thuộc trực tiếp vào legacy request/response types.

### Integration tests

- Kết nối đúng Elasticsearch server bằng REST/TLS.
- Authentication và index privileges hoạt động.
- Save/get/search/update/delete.
- Bulk item success và partial failure.
- Mapping/date/enum/nested serialization.
- Aggregation, sort, highlight và pagination.
- Alias/index/template management.
- Refresh/search visibility.
- PIT/scroll/search_after nếu có.

### Regression tests

- Chạy cùng fixture và query trên client cũ/mới trong môi trường tương thích.
- So sánh IDs, ordering, total relation, aggregation buckets và highlights.
- Ghi nhận khác biệt được chấp nhận do server version/mapping thay đổi.

Không nên chỉ kiểm tra rằng client mới khởi tạo thành công. Mục tiêu migration là giữ hành vi nghiệp vụ và khả năng vận hành.

## 34. Dùng Testcontainers hoặc môi trường Elasticsearch test

Integration test cần một Elasticsearch instance tương thích với client/Spring Data version. Có thể dùng Testcontainers hoặc môi trường test cô lập.

Ví dụ cấu trúc:

```text
JUnit
  |
  v
Spring ApplicationContext
  |
  v
Spring Data Elasticsearch / Java API Client
  |
  v
Elasticsearch test node
```

Chọn image version tương thích với client và Spring Data. Nếu cluster production bật security/TLS, nên có một nhóm test xác nhận auth/TLS riêng thay vì chỉ test HTTP không bảo mật.

Không dùng Elasticsearch test image khác major version rồi kết luận migration production an toàn. Client/server compatibility và API behavior phải được xác minh trên version mục tiêu.

## 35. Lộ trình migration từ TransportClient

Một lộ trình có thể chia thành các bước:

1. Kiểm kê server, Java, Spring Boot và Spring Data version.
2. Tìm toàn bộ `TransportClient`, `PreBuiltTransportClient`, transport address và sniff settings.
3. Xác định endpoint REST, network policy, TLS và authentication.
4. Chọn Spring Data/Java API Client version tương thích với Elasticsearch mục tiêu.
5. Chuyển cấu hình connection từ transport sang REST.
6. Thay custom repository/API call bằng Spring Data operations hoặc Java API Client.
7. Thay đổi query/aggregation/bulk builders và response parsing.
8. Xác minh serialization, mapping, retry, timeout và resource lifecycle.
9. Chạy integration/regression tests.
10. Rollout canary và theo dõi latency, errors, throughput, heap và connection pool.
11. Loại dependency transport cũ và cấu hình legacy sau khi không còn caller.

Nếu server hiện tại là Elasticsearch 7.x, có thể cần nâng cấp client và server theo từng bước tương thích. Không nâng server lên 8.x trước khi các ứng dụng phụ thuộc TransportClient đã được chuyển.

## 36. Lộ trình migration từ RestHighLevelClient

Với HLRC, có thể chia nhỏ:

1. Kiểm kê mọi import và API HLRC.
2. Nâng Spring Data Elasticsearch/Spring Boot tới nhánh dùng Java API Client nếu kiến trúc dựa trên Spring Data.
3. Giữ interface repository/service ổn định.
4. Chuyển CRUD/search cơ bản sang `ElasticsearchOperations` hoặc repository.
5. Chuyển API đặc biệt sang Java API Client typed builders.
6. Thay query builders, aggregation parsing và bulk response handling.
7. Chuyển serializer sang `JsonpMapper` hoặc giữ mapping Spring Data đúng boundary.
8. Cập nhật exception translation, timeout và retry.
9. Chạy test so sánh hành vi.
10. Xóa HLRC dependency/imports và code adapter cũ.

### Không chuyển toàn bộ cùng một commit nếu codebase lớn

Có thể tạo adapter interface ở application boundary:

```java
public interface ProductSearchPort {
    SearchPage<ProductDocument> search(ProductSearchCriteria criteria);
}
```

Implementation cũ dùng HLRC, implementation mới dùng Spring Data/Java API Client. Test contract chạy trên cả hai implementation trong giai đoạn chuyển tiếp. Khi rollout hoàn tất, xóa implementation cũ và dependency legacy.

Không nên duy trì hai implementation lâu dài nếu không có nhu cầu vận hành cụ thể; dual path làm tăng chi phí test và có thể tạo khác biệt hành vi.

## 37. Canary rollout và rollback

Với hệ thống có traffic lớn:

- Triển khai client mới trên một instance/canary trước.
- Giữ index/mapping và query semantics không đổi trong lần rollout client nếu có thể.
- So sánh latency p50/p95/p99, error rate, connection count và throughput.
- Theo dõi serialization error, bulk item failure và rejected request.
- Chạy shadow read nếu dữ liệu và chi phí cho phép; không nhân đôi write side effect.
- Mở rộng traffic dần khi kết quả ổn định.
- Có kế hoạch rollback binary/config trong giới hạn tương thích server.

Nếu migration đi cùng nâng major Elasticsearch server, rollback cần xem xét cả compatibility của client cũ và index/mapping. Không giả định chỉ rollback application binary là đủ sau khi đã thay server hoặc schema.

## 38. Những lỗi thường gặp khi migration

### Chỉ đổi dependency nhưng giữ code HLRC

Request/response types không tương thích. Phải chuyển các API call và parsing tương ứng.

### Dùng TransportClient với Elasticsearch 8+

TransportClient đã bị loại bỏ ở Elasticsearch 8. Chuyển sang REST client.

### Dùng HLRC cho phát triển mới

HLRC đã deprecated từ 7.15. Chọn Java API Client theo compatibility matrix.

### Cấu hình nhầm cổng

Transport port và HTTP port là hai giao thức khác nhau. REST client dùng HTTP/HTTPS endpoint.

### Giữ sniffing cũ trong cloud

Node publish address có thể không truy cập được hoặc certificate không khớp. Dùng endpoint/load balancer phù hợp.

### Tạo nhiều client/connection pool

Auto-configuration và custom bean cùng tạo client có thể tăng socket, thread và memory. Xác định một lifecycle owner.

### Bỏ qua serialization khác biệt

Date, enum, null, numeric và nested fields có thể thay đổi JSON. Test payload thực tế.

### Không kiểm tra bulk item errors

HTTP 200 không đồng nghĩa tất cả bulk actions thành công. Duyệt response item.

### Chỉ test client initialization

Client tạo được chưa chứng minh query, aggregation, mapping và pagination tương đương.

### Bọc CompletableFuture thành Mono rồi gọi là reactive end-to-end

Async API không tự cung cấp backpressure cho một luồng document. Chọn reactive abstraction nếu cần Reactive Streams.

## 39. Checklist trước khi hoàn tất migration

- Elasticsearch server version và Java runtime đã được xác nhận.
- Spring Boot/Spring Data/Java client version tương thích.
- Không còn caller của TransportClient.
- Không còn caller mới dùng HLRC.
- Endpoint REST, TLS và authentication hoạt động.
- Connection pool và timeout được cấu hình theo workload.
- Client/transport lifecycle được Spring quản lý.
- Search query và aggregation semantics được giữ nguyên.
- Bulk item errors, retry và idempotency được xử lý.
- Mapping và JSON serialization đã được kiểm thử.
- PIT/scroll/search_after được xác minh nếu có.
- Exception translation và logging không làm lộ secret.
- Metrics/tracing thể hiện đúng client operation.
- Integration/regression tests chạy trên server version mục tiêu.
- Canary và rollback plan đã được xác định.
- Dependency tree không còn artifact legacy không cần thiết.

## 40. Kết luận

TransportClient dùng transport protocol nội bộ và đã bị loại bỏ ở Elasticsearch 8.0. RestHighLevelClient dùng HTTP REST nhưng đã deprecated từ 7.15; hướng thay thế là Elasticsearch Java API Client. Client mới cung cấp typed builders, typed responses, sync/async APIs và dùng REST transport. Low Level REST Client vẫn hữu ích cho request HTTP cấp thấp, còn Spring Data Elasticsearch cung cấp repository/template abstraction cho phần lớn nghiệp vụ.

Migration cần bắt đầu từ compatibility matrix của Elasticsearch server, Spring Boot, Spring Data và Java client. Sau đó chuyển endpoint/cấu hình TLS-auth, thay request/response builders, aggregation, bulk handling, serialization, exception mapping và lifecycle. Nếu dùng Spring Data, ưu tiên repository/`ElasticsearchOperations`/reactive operations; chỉ gọi Java API Client trực tiếp cho phần cần API thấp hơn. Kiểm thử mapping, query semantics, partial bulk failure, timeout, security và search visibility trên server mục tiêu; rollout canary rồi mới loại dependency legacy. Không coi việc compile thành công hoặc khởi tạo client được là hoàn tất migration.

## Tài liệu tham khảo

- [Elasticsearch – Java API Client](https://www.elastic.co/docs/reference/elasticsearch/clients/java)
- [Elasticsearch – Migrating from the High Level REST Client](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/migrate-hlrc.html)
- [Elasticsearch – Low Level REST Client](https://www.elastic.co/guide/en/elasticsearch/client/java-rest/current/java-rest-low.html)
- [Elasticsearch – TransportClient removal/deprecation notes](https://www.elastic.co/guide/en/elasticsearch/client/java-api/current/transport-client.html)
- [Spring Data Elasticsearch – Reference](https://docs.spring.io/spring-data/elasticsearch/reference/)
- [Spring Data Elasticsearch – Client configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Boot – Elasticsearch](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.elasticsearch)
