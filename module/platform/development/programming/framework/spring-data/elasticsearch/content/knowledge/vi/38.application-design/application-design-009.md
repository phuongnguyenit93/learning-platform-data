# Nhiều index, nhiều cluster và giới hạn truy vấn liên nguồn

Một ứng dụng Spring Data Elasticsearch có thể cần tìm kiếm trên nhiều index, nhiều nhóm dữ liệu hoặc nhiều Elasticsearch cluster. Ví dụ, catalog sản phẩm được chia theo năm, tenant hoặc vùng; hệ thống có một cluster cho dữ liệu giao dịch và một cluster cho dữ liệu phân tích; hoặc một màn hình tổng hợp kết quả từ nhiều hệ thống độc lập.

Các trường hợp này có bề ngoài giống nhau nhưng khác về kiến trúc:

- **Nhiều index trong cùng cluster:** một search request có thể nhắm đến nhiều index, alias hoặc index pattern. Elasticsearch điều phối shard và tổng hợp kết quả trong cùng cluster.
- **Nhiều cluster:** mỗi cluster có client, kết nối, quyền truy cập, trạng thái và giới hạn tài nguyên riêng. Muốn tìm xuyên cluster cần Cross-Cluster Search (CCS), hoặc ứng dụng phải fan-out request đến nhiều client rồi hợp nhất kết quả.
- **Nhiều nguồn dữ liệu khác loại:** Elasticsearch không tự join với database, message broker hay một search engine khác. Ứng dụng cần xây dựng read model hoặc phối hợp kết quả ở tầng service.

Spring Data Elasticsearch cung cấp ElasticsearchOperations, IndexCoordinates, repository và query abstraction để làm việc với index. Tuy nhiên, một ElasticsearchOperations instance gắn với client/cluster đã được cấu hình. Truyền nhiều index coordinates không có nghĩa là truy vấn tự chạy trên nhiều cluster độc lập.

## 1. Phân biệt index, alias, cluster và nguồn dữ liệu

Trước khi thiết kế truy vấn liên nguồn, cần xác định tài nguyên nào đang được kết hợp.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Index | Không gian lưu document và shard trong một cluster | products-2025 |
| Alias | Tên logic trỏ tới một hoặc nhiều index | products-read |
| Index pattern | Biểu thức chọn nhiều index | products-* |
| Cluster | Một Elasticsearch deployment có cluster state và tài nguyên riêng | catalog-cluster |
| Remote cluster | Cluster khác được cấu hình để cluster điều phối truy cập | archive |
| Data stream | Tên logic quản lý các backing index theo thời gian | product-events |
| Nguồn dữ liệu | Hệ thống phát sinh hoặc lưu dữ liệu | PostgreSQL, Kafka, Elasticsearch |

### 1.1. Nhiều index không phải nhiều cluster

Các index sau có thể cùng nằm trong một cluster:

~~~text
catalog-cluster
  |
  +-- products-2024
  +-- products-2025
  +-- products-2026
  +-- products-current
~~~

Một search request có thể nhắm đến nhiều index trong cluster đó:

~~~http
GET /products-2024,products-2025,products-2026/_search
~~~

Hoặc dùng index pattern:

~~~http
GET /products-*/_search
~~~

Elasticsearch điều phối truy vấn đến các shard liên quan trong cùng cluster và reduce kết quả.

### 1.2. Nhiều cluster có ranh giới riêng

~~~text
Application
   |
   +---- client A ----> catalog-cluster
   |
   +---- client B ----> archive-cluster
   |
   +---- client C ----> analytics-cluster
~~~

Mỗi cluster có thể có endpoint, TLS và credential riêng; cluster state, index, shard và node riêng; mapping/analyzer khác nhau; version Elasticsearch khác nhau trong phạm vi tương thích được hỗ trợ; giới hạn tài nguyên, latency và availability riêng; quyền truy cập và chính sách retention riêng.

Một request đến catalog-cluster không tự biết archive-cluster tồn tại. Muốn search trên cluster khác phải cấu hình CCS hoặc gửi request bằng client của cluster đó.

### 1.3. Nhiều nguồn dữ liệu không đồng nghĩa Elasticsearch join được chúng

Elasticsearch có thể truy vấn các document trong những index được cung cấp cho search request. Nó không tự thực hiện distributed SQL join với PostgreSQL, một Kafka topic hoặc một API nghiệp vụ.

Nếu cần tìm kiếm kết hợp dữ liệu từ nhiều hệ thống, thường có ba hướng:

1. Đồng bộ dữ liệu cần tìm vào một Elasticsearch read model.
2. Fan-out truy vấn đến từng nguồn rồi hợp nhất ở application layer.
3. Dùng một cơ chế federation/search platform phù hợp với loại nguồn và yêu cầu nghiệp vụ.

Chọn cách nào phụ thuộc dữ liệu cần join, độ mới, độ trễ và yêu cầu nhất quán.

## 2. Tìm kiếm trên nhiều index trong cùng cluster

Đây là trường hợp đơn giản nhất. Một query có thể nhắm tới nhiều index thông qua danh sách index cụ thể, alias trỏ tới nhiều index, index pattern/wildcard hoặc data stream.

Ví dụ:

~~~http
GET /products-2025,products-2026/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Hoặc:

~~~http
GET /products-*/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Elasticsearch trả một tập hits hợp nhất từ các shard được truy vấn. Mỗi hit vẫn có metadata cho biết index nguồn qua trường _index.

### 2.1. Dùng danh sách index tường minh

Danh sách index tường minh phù hợp khi ứng dụng biết chính xác index cần đọc, số index nhỏ và ổn định, cần tránh vô tình truy vấn index không liên quan hoặc có thể quản lý lifecycle của index trong code/cấu hình.

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "products-2025",
    "products-2026"
);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

IndexCoordinates đại diện cho index đích của thao tác Spring Data. Khi truyền nhiều tên index, thao tác search có thể hướng đến nhiều index trong cùng cluster, tùy API và phiên bản đang dùng.

Không truyền tên index của cluster khác vào đây rồi kỳ vọng Spring Data tự chọn client khác. IndexCoordinates chỉ mô tả tên index/đích của request gửi qua operations hiện tại.

### 2.2. Dùng wildcard/index pattern

Index pattern giúp truy vấn một tập index được tạo theo quy ước:

~~~java
IndexCoordinates coordinates =
    IndexCoordinates.of("products-202*");
~~~

Pattern có thể hữu ích khi index được tạo theo năm hoặc theo partition. Tuy nhiên, wildcard rộng có thể chọn nhiều index hơn dự kiến, làm tăng số shard được truy vấn và chi phí reduce.

Không nên dùng pattern chung như dấu sao cho truy vấn ứng dụng thường ngày. Nó có thể chạm vào index nội bộ, index của module khác hoặc dữ liệu không cùng schema.

### 2.3. Dùng alias làm abstraction

Alias tạo tên logic ổn định:

~~~text
products-read
    |
    +--> products-2025
    +--> products-2026
~~~

Ứng dụng truy vấn products-read mà không cần biết index vật lý nào đang chứa dữ liệu. Khi thêm index mới, vận hành cập nhật alias; code vẫn dùng cùng tên logic.

Alias phù hợp khi ứng dụng cần đọc nhiều index cùng schema, index vật lý được rollover hoặc thay thế định kỳ, muốn chuyển index mà không đổi code hoặc muốn che giấu cấu trúc lưu trữ vật lý khỏi repository/service.

### 2.4. Alias đọc và alias ghi

Read alias có thể trỏ tới nhiều index. Write alias thường cần xác định rõ một write index để thao tác ghi có đích duy nhất.

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-2025",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-2026",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-2026",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Ứng dụng đọc qua products-read và ghi qua products-write. Không để một write alias trỏ nhiều index mà không có write index rõ ràng.

## 3. Giới hạn quan trọng khi search nhiều index

Một search request trên nhiều index là một truy vấn phân tán trong cùng cluster, nhưng không có nghĩa mọi index có thể được xem như một schema đồng nhất.

Các giới hạn chính:

- Mapping của cùng field có thể khác kiểu.
- Analyzer hoặc normalizer có thể khác.
- Field có thể tồn tại ở index này nhưng không tồn tại ở index khác.
- Sort và aggregation cần kiểu dữ liệu tương thích.
- Query được gửi đến nhiều shard nên chi phí tăng theo số shard.
- Relevance score có thể bị ảnh hưởng bởi corpus statistics khác nhau.
- Pagination và snapshot consistency cần được thiết kế cẩn thận.

### 3.1. Mapping phải tương thích

Giả sử:

~~~text
products-2025:
  price -> double
  brandId -> keyword
  name -> text

products-2026:
  price -> keyword
  brandId -> keyword
  name -> text
~~~

Một range query trên price có thể hoạt động ở index này nhưng thất bại hoặc có semantics không phù hợp ở index kia. Sort/aggregation trên field có kiểu khác nhau cũng có thể lỗi.

Trước khi gom index vào cùng alias hoặc query, cần xác định một schema contract gồm field name/type, analyzer/normalizer, date format và timezone semantics, nested/object structure, multi-fields, null/missing behavior và version của document schema.

### 3.2. Field không có ở một số index

Một field có thể chưa được thêm vào index cũ. Query trên nhiều index có thể cần unmapped_type cho sort hoặc kiểm soát mapping để tránh lỗi khi field không tồn tại.

~~~json
{
  "sort": [
    {
      "rating": {
        "order": "desc",
        "unmapped_type": "double"
      }
    }
  ]
}
~~~

unmapped_type giúp Elasticsearch xử lý index không có field đó trong một số ngữ cảnh sort. Nó không biến field thiếu thành dữ liệu hợp lệ và không sửa được mapping conflict giữa các kiểu không tương thích.

### 3.3. Mapping conflict không thể chữa chỉ bằng wildcard

Nếu một index lưu price là keyword và index khác lưu price là double, query pattern không tự chuyển đổi hai mapping. Các lựa chọn:

- Tạo index mới theo schema thống nhất và reindex dữ liệu cũ.
- Dùng field mới có tên/schema thống nhất.
- Tách query theo nhóm mapping tương thích.
- Chuẩn hóa dữ liệu ở tầng ingest hoặc application.

Không nên dựa vào runtime conversion tùy tiện cho mọi truy vấn production vì chi phí và semantics khó kiểm soát.

## 4. Repository và ElasticsearchOperations khi có nhiều index

Spring Data Elasticsearch có hai cách sử dụng thường gặp: repository dựa trên metadata entity, ví dụ @Document(indexName = "products"), và ElasticsearchOperations nhận IndexCoordinates tường minh cho thao tác cụ thể.

### 4.1. Repository thường gắn với index metadata

~~~java
@Document(indexName = "products-read")
public class ProductDocument {
    @Id
    private String id;
    private String name;
}
~~~

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Repository dùng index/alias trong metadata của entity. Điều này thuận tiện khi repository luôn làm việc với cùng logical index.

Repository method thông thường không nhận một IndexCoordinates khác cho từng lần gọi. Nếu cần chọn index động theo tenant, thời gian hoặc shard group, dùng ElasticsearchOperations với coordinates tường minh hoặc thiết kế repository/operations riêng.

### 4.2. Dùng ElasticsearchOperations với nhiều index

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "products-2025",
    "products-2026"
);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

Một ElasticsearchOperations instance sử dụng client/template đã được cấu hình. Nhiều index coordinates trong request vẫn thuộc cluster mà client đó kết nối.

### 4.3. IndexCoordinates không phải cluster selector

Không dùng cách sau với ý nghĩ hai index thuộc hai cluster khác nhau:

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "cluster-a:products",
    "cluster-b:products"
);
~~~

Chuỗi cluster-a:products chỉ có ý nghĩa remote index expression trong request CCS nếu cluster điều phối đã cấu hình remote cluster alias cluster-a. Nó không khiến Spring Data tự tạo hoặc chọn hai client khác nhau.

Nếu remote cluster chưa được cấu hình, request sẽ thất bại vì remote alias không được nhận diện hoặc không thể kết nối.

## 5. Nhiều Elasticsearch cluster trong một ứng dụng Spring

Khi ứng dụng phải làm việc với hai cluster độc lập mà không dùng CCS, cần cấu hình hai client và hai operations/template tương ứng.

~~~text
Spring ApplicationContext
       |
       +-- catalogClient
       |       |
       |       +-- catalogOperations
       |       +-- catalogRepositories
       |
       +-- archiveClient
               |
               +-- archiveOperations
               +-- archiveRepositories
~~~

Mỗi operations instance phải được gắn với đúng client. Khi gọi repository hoặc service, dependency injection cần chỉ rõ cluster nào được sử dụng.

### 5.1. Tách cấu hình client

Một cấu hình khái niệm:

~~~java
@Configuration
class CatalogElasticsearchConfiguration {

    @Bean
    ElasticsearchClient catalogClient() {
        // Tạo client kết nối catalog cluster.
        return createCatalogClient();
    }

    @Bean
    ElasticsearchOperations catalogOperations(
            ElasticsearchClient catalogClient) {
        // Tạo Spring Data operations từ catalog client.
        return createOperations(catalogClient);
    }
}
~~~

~~~java
@Configuration
class ArchiveElasticsearchConfiguration {

    @Bean
    ElasticsearchClient archiveClient() {
        // Tạo client kết nối archive cluster.
        return createArchiveClient();
    }

    @Bean
    ElasticsearchOperations archiveOperations(
            ElasticsearchClient archiveClient) {
        // Tạo Spring Data operations từ archive client.
        return createOperations(archiveClient);
    }
}
~~~

Các hàm createCatalogClient, createArchiveClient và createOperations là placeholder để thể hiện cấu trúc. Cách khởi tạo client, transport, converter và template phụ thuộc phiên bản Spring Data Elasticsearch, Java API Client và cấu hình TLS/authentication của dự án.

Trong ứng dụng thực tế, tránh tạo hai bean cùng tên hoặc hai candidate không phân biệt được. Dùng bean name/qualifier rõ ràng.

### 5.2. Inject đúng operations

~~~java
@Service
class ProductSearchService {

    private final ElasticsearchOperations catalogOperations;
    private final ElasticsearchOperations archiveOperations;

    ProductSearchService(
            @Qualifier("catalogOperations")
            ElasticsearchOperations catalogOperations,
            @Qualifier("archiveOperations")
            ElasticsearchOperations archiveOperations) {
        this.catalogOperations = catalogOperations;
        this.archiveOperations = archiveOperations;
    }
}
~~~

Mỗi lần gọi search cần dùng operations đúng nguồn. Một query đến catalog cluster không thể dùng archiveOperations chỉ bằng cách thay tên index.

### 5.3. Tách repository scanning theo operations

Nếu dùng repository cho cả hai cluster, mỗi nhóm repository cần được gắn với operations tương ứng thông qua cấu hình repository scanning mà phiên bản Spring Data hỗ trợ, chẳng hạn thuộc tính elasticsearchOperationsRef của @EnableElasticsearchRepositories.

Ví dụ cấu trúc:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchOperationsRef = "catalogOperations"
)
class CatalogRepositoriesConfiguration {
}
~~~

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.archive.repository",
    elasticsearchOperationsRef = "archiveOperations"
)
class ArchiveRepositoriesConfiguration {
}
~~~

Tên thuộc tính và khả năng dùng nhiều repository configuration cần đối chiếu với phiên bản Spring Data Elasticsearch. Hai vùng package không nên scan chồng lấn cùng repository interface.

### 5.4. Reactive cluster clients

Nếu dùng reactive operations, mỗi cluster cần ReactiveElasticsearchClient/ReactiveElasticsearchOperations tương ứng. Không trộn reactive repository với operations của cluster khác.

Một service có thể fan-out reactive request đến nhiều cluster, nhưng phải kết hợp Publisher và xử lý lỗi/timeout cho từng nguồn. Nếu một cluster chậm, toàn bộ kết quả tổng hợp có thể bị trì hoãn tùy policy.

## 6. Cross-Cluster Search (CCS)

Cross-Cluster Search cho phép một Elasticsearch cluster điều phối truy vấn đến các remote cluster đã được cấu hình. Client gửi một search request đến cluster điều phối; cluster đó fan-out phần truy vấn đến các cluster từ xa và reduce kết quả.

~~~text
Application
    |
    v
Coordinating cluster
    |
    +---- local index
    |
    +---- remote alias A ----> archive cluster
    |
    +---- remote alias B ----> analytics cluster
    |
    v
Merged search response
~~~

CCS phù hợp khi cần một search API hợp nhất trên các index nằm ở nhiều cluster Elasticsearch.

### 6.1. Cấu hình remote cluster

Cluster điều phối cần biết remote cluster thông qua cấu hình remote cluster connection. Cấu hình bao gồm alias, seed addresses hoặc cơ chế kết nối phù hợp, TLS, authentication và các giới hạn kết nối.

Remote alias là tên logic dùng trong index expression. Ví dụ alias archive có thể đại diện cho cluster archive.

Remote cluster phải được cấu hình trước khi query. Việc thêm prefix archive: vào tên index không tự thiết lập kết nối.

### 6.2. Cú pháp remote index expression

Một request CCS có thể chỉ định index local và remote:

~~~http
GET /products-current,archive:products-2024,archive:products-2025/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Hoặc dùng wildcard trên remote:

~~~http
GET /archive:products-*/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Tên remote alias phải trùng cấu hình trên cluster điều phối. Index expression có thể chứa nhiều remote alias, nhưng phạm vi và cú pháp cụ thể phụ thuộc version Elasticsearch.

### 6.3. Gửi CCS qua Spring Data Elasticsearch

Spring Data Elasticsearch dùng client được cấu hình bên dưới. Nếu client gửi search request đến một coordinating cluster đã bật CCS, query có thể sử dụng remote index expression trong phần index coordinates nếu phiên bản API hỗ trợ truyền nguyên vẹn tên index expression đó.

Ví dụ khái niệm:

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "products-current",
    "archive:products-2024",
    "archive:products-2025"
);

SearchHits<ProductDocument> hits =
    coordinatingOperations.search(
        query,
        ProductDocument.class,
        coordinates
    );
~~~

coordinatingOperations vẫn chỉ kết nối đến coordinating cluster. Chính Elasticsearch cluster đó thực hiện CCS. Nếu cần kiểm soát tham số CCS đặc thù mà Spring Data abstraction không expose, có thể dùng Elasticsearch Java API Client trực tiếp.

Không cấu hình một ElasticsearchOperations cho mỗi remote alias nếu mục tiêu là CCS. Remote alias được quản lý ở cluster điều phối, không phải là một bean client ở phía Spring.

### 6.4. CCS không phải distributed transaction

CCS chỉ hợp nhất kết quả search. Nó không cung cấp transaction ghi nguyên tử lên nhiều cluster, distributed join tùy ý giữa các document theo quan hệ nghiệp vụ, một snapshot transaction chung xuyên tất cả cluster, cơ chế tự đồng bộ dữ liệu giữa các remote cluster hoặc bảo đảm mọi remote cluster cùng available.

Nếu cần cập nhật nhiều cluster, ứng dụng phải có workflow ghi, retry, reconciliation và chính sách partial failure riêng.

## 7. Giới hạn nhất quán khi truy vấn nhiều index/cluster

Search trên nhiều index hoặc cluster không nên được hiểu như một transaction đọc snapshot trên toàn bộ nguồn.

### 7.1. Không có snapshot chung xuyên cluster

Một request có thể được điều phối đến các shard ở nhiều index/cluster tại những thời điểm khác nhau. Nếu dữ liệu thay đổi trong lúc truy vấn, các nguồn có thể phản ánh trạng thái ở những thời điểm khác nhau.

PIT có thể giữ view ổn định trong phạm vi mà Elasticsearch hỗ trợ cho request đó, nhưng không nên giả định có một transaction snapshot toàn cục qua mọi remote cluster. Khả năng PIT/CCS kết hợp và giới hạn remote cần kiểm tra theo phiên bản.

Nếu nghiệp vụ cần snapshot thống nhất, thường phải tạo một read model hợp nhất hoặc dùng watermark/version ở tầng dữ liệu.

### 7.2. Eventual consistency giữa các cluster

Nếu dữ liệu được replicate hoặc project sang nhiều cluster bất đồng bộ, một cluster có thể mới hơn cluster khác.

~~~text
catalog cluster: Product P-100 version 42
archive cluster: Product P-100 version 40
~~~

CCS có thể trả cả hai document nếu chúng cùng nằm trong index pattern. Elasticsearch không tự biết chúng là hai phiên bản của cùng một aggregate nghiệp vụ.

Ứng dụng cần chọn một nguồn có thẩm quyền cho mỗi document, lưu sourceVersion/updatedAt có semantics rõ, deduplicate theo business ID khi cần hoặc bảo đảm mỗi aggregate chỉ xuất hiện trong một nguồn được query.

### 7.3. Duplicate document giữa các index

Nếu cùng một document được lưu trong index cũ và index mới, query alias trỏ cả hai có thể trả hai hits với cùng business ID.

Elasticsearch coi _index + _id là định danh trong phạm vi index; cùng _id ở hai index vẫn là hai document riêng.

Không giả định Elasticsearch tự gộp hai hits cùng ID. Nếu dùng alias để đọc cả index cũ và mới trong quá trình migration, cần chiến lược tránh duplicate hoặc deduplicate ở tầng ứng dụng.

### 7.4. Không có join nghiệp vụ tự động

Nếu product nằm ở catalog cluster và inventory nằm ở stock cluster, CCS không tự join product.id với inventory.productId như một relational database.

Các lựa chọn:

- Đồng bộ inventory field vào product search document.
- Fan-out query rồi join kết quả ở service.
- Dùng một data platform/read model phù hợp với truy vấn.

Join ở application layer cần pagination, sorting và count được định nghĩa rõ. Nếu chỉ lấy top 20 từ mỗi nguồn rồi ghép, không bảo đảm top 20 toàn cục chính xác nếu chưa có chiến lược merge phù hợp.

## 8. Relevance score trên nhiều index và cluster

Điểm _score phụ thuộc query và thống kê term trong tập dữ liệu/shard. Khi search qua nhiều index hoặc cluster có corpus khác nhau, không nên giả định score luôn so sánh hoàn hảo giữa mọi nguồn.

Các yếu tố ảnh hưởng:

- Tần suất term trong từng shard/index.
- Số lượng document và phân bố field.
- Analyzer và mapping khác nhau.
- Search type và cách lấy term statistics.
- Version và cấu hình cluster.

### 8.1. Dùng sort theo field khi cần thứ tự nghiệp vụ

Nếu cần xếp toàn cục theo giá, thời điểm hoặc một ranking field có semantics chung, dùng sort theo field có mapping thống nhất.

~~~json
{
  "sort": [
    {
      "updatedAt": {
        "order": "desc",
        "unmapped_type": "date"
      }
    },
    {
      "productId": {
        "order": "asc",
        "unmapped_type": "keyword"
      }
    }
  ]
}
~~~

Field tie-breaker giúp thứ tự ổn định hơn khi nhiều document có cùng updatedAt. Kiểu dữ liệu phải tương thích giữa các index.

### 8.2. dfs_query_then_fetch

Elasticsearch có search type dfs_query_then_fetch, có thể thu thập term statistics từ shard trước khi query để cải thiện tính nhất quán của scoring trong một số truy vấn phân tán.

Nó có thêm round trip và chi phí. Không nên bật chỉ vì truy vấn có nhiều index. Với CCS, khả năng và semantics của search type cần đối chiếu theo version; không giả định nó tạo ra một relevance score hoàn toàn chuẩn hóa giữa các cluster có dữ liệu/mapping rất khác nhau.

### 8.3. Chuẩn hóa ranking ở tầng ứng dụng

Nếu cần hợp nhất kết quả từ nhiều nguồn có scoring khác nhau, có thể dùng sort field có semantics chung, áp dụng ranking model chung trên dữ liệu đã chuẩn hóa, kết hợp score với source priority hoặc freshness, dùng reciprocal rank fusion (RRF) hoặc phương pháp rank fusion thích hợp nếu sản phẩm hỗ trợ, và deduplicate theo business ID trước khi trả kết quả.

Không so sánh trực tiếp _score từ hai query khác nhau hoặc hai cluster khác corpus nếu chưa chứng minh được ý nghĩa so sánh.

## 9. Pagination và sort trên nhiều index

Pagination dễ trở nên không ổn định nếu index có mapping khác nhau hoặc dữ liệu thay đổi trong lúc người dùng chuyển trang.

### 9.1. from/size

from/size phù hợp với phân trang nông. Elasticsearch có giới hạn index.max_result_window cho kết quả phân trang sâu, mặc định thường là 10.000 hits cho nhiều cấu hình.

Tăng giới hạn có thể làm tăng memory và chi phí heap vì shard phải giữ nhiều kết quả hơn. Không nên tăng max_result_window để giải quyết mọi trường hợp pagination.

### 9.2. search_after

Với kết quả sâu, dùng sort ổn định và search_after để lấy trang tiếp theo từ sort values của hit cuối trang trước.

Ví dụ sort:

~~~json
{
  "sort": [
    { "updatedAt": "desc" },
    { "productId": "asc" }
  ]
}
~~~

Trang tiếp theo gửi search_after tương ứng với sort values của hit cuối trang trước. Field sort phải có doc values và mapping tương thích ở các index.

### 9.3. PIT

Point in Time giúp giữ một view ổn định trong khi phân trang sâu trên một index/cluster scope được hỗ trợ. Kết hợp PIT và search_after giúp tránh kết quả bị dịch chuyển do refresh/indexing giữa các trang.

Với CCS, PIT và remote cluster support có giới hạn theo version và topology. Không giả định PIT ID hoặc lifecycle giống hệt truy vấn local; kiểm tra tài liệu version đang chạy.

### 9.4. Pagination khi fan-out nhiều client

Nếu ứng dụng gửi riêng một request đến từng cluster rồi merge:

1. Mỗi nguồn trả một page cục bộ.
2. Application merge các kết quả theo sort key chung.
3. Cần giữ cursor/continuation token riêng cho từng nguồn.
4. Trang tiếp theo cần tiếp tục từ cursor của từng nguồn.

Chỉ lấy cùng from/size ở mọi cluster rồi ghép không bảo đảm pagination toàn cục đúng. Cần một thuật toán k-way merge và đủ lookahead từ từng nguồn.

Nếu một nguồn không trả đủ kết quả hoặc bị timeout, trang kết quả tổng hợp có thể thiếu phần tử đứng trước trong thứ tự toàn cục.

## 10. Aggregation trên nhiều index và cluster

Trong cùng cluster, aggregation có thể chạy trên nhiều index trong một search request nếu mapping tương thích.

~~~http
GET /products-2025,products-2026/_search
{
  "size": 0,
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brandId"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
~~~

Kết quả được reduce từ shard. Tuy nhiên, field type phải tương thích; terms aggregation phân phối bucket có thể chịu sai số do shard_size; cardinality aggregation là ước lượng theo thuật toán approximate; pipeline aggregation phụ thuộc dữ liệu bucket được thu thập; aggregation trên nhiều index có thể tiêu thụ memory và CPU đáng kể.

### 10.1. Aggregation và missing fields

Nếu một index không có field brandId, aggregation có thể bỏ qua document không có giá trị đó. Cần phân biệt missing field với giá trị nghiệp vụ thực sự.

Nếu field có mapping khác nhau, request có thể lỗi. Hãy chuẩn hóa schema hoặc tách query theo nhóm mapping.

### 10.2. Aggregation qua CCS

CCS có thể thực hiện search và reduce aggregation từ remote clusters trong phạm vi tính năng/version hỗ trợ. Tuy nhiên, không phải mọi aggregation/plugin hoặc mọi cấu hình cluster đều có semantics giống một index duy nhất.

Kiểm tra remote cluster version compatibility, field mapping và type, shard failures/partial results, bucket limits và memory, aggregation accuracy, security privileges trên remote indices.

### 10.3. Aggregation khi application fan-out

Nếu gọi nhiều cluster riêng biệt, application phải merge aggregation result. Không cộng mù các giá trị:

- sum thường có thể cộng nếu cùng đơn vị và cùng filter semantics.
- count cần biết có document trùng giữa nguồn không.
- avg phải merge theo sum và count, không lấy trung bình các average.
- cardinality estimate không thể cộng trực tiếp để ra cardinality toàn cục chính xác.
- percentile và histogram cần thuật toán merge phù hợp hoặc query tập trung.

Với analytics cần kết quả chính xác và nhất quán, thường nên dùng một pipeline/materialized dataset hợp nhất thay vì tự ghép các response tùy ý.

## 11. Failure semantics khi query nhiều nguồn

Khi search nhiều index/shard/cluster, một phần nguồn có thể lỗi trong khi phần khác vẫn trả kết quả.

### 11.1. Shard failure trong một cluster

Một search response có thể có shard failures. Nếu cho phép partial results, response vẫn có thể chứa hits từ shard thành công nhưng không đại diện đầy đủ cho toàn bộ tập dữ liệu.

Ứng dụng cần kiểm tra timed_out, failed shard count, danh sách shard failures, terminated_early nếu có và CCS remote cluster status khi dùng CCS.

Không coi HTTP 200 đồng nghĩa toàn bộ shard đã thành công.

### 11.2. Remote cluster unavailable

Trong CCS, một remote cluster có thể không kết nối được hoặc timeout. Tùy cấu hình request, Elasticsearch có thể trả partial response hoặc fail toàn bộ request.

Chọn policy theo nghiệp vụ:

- **Strict:** nếu một nguồn bắt buộc lỗi, trả lỗi cho caller.
- **Best effort:** trả kết quả từ nguồn thành công và kèm trạng thái nguồn lỗi.
- **Fallback:** dùng read model/cache dự phòng nếu được phép.

Không âm thầm bỏ qua remote failure nếu giao diện cần kết quả đầy đủ.

### 11.3. Timeout và deadline

Một query nhiều cluster có latency phụ thuộc nguồn chậm nhất nếu ứng dụng đợi tất cả. Đặt deadline tổng thể, timeout riêng cho từng nguồn và cancellation policy.

Nếu fan-out bằng reactive API, cần xử lý timeout và error cho từng Publisher. Một lỗi trong một nhánh có thể làm zip/combine thất bại toàn bộ nếu không chuyển nhánh đó thành trạng thái kết quả riêng.

### 11.4. Circuit breaker

Nếu một cluster thường xuyên lỗi, circuit breaker có thể ngăn ứng dụng gửi request liên tục vào nguồn đang suy giảm.

Cần xác định threshold mở circuit, thời gian open, half-open probe, fallback hoặc partial response, metric và alert.

Không để circuit breaker biến lỗi dữ liệu thành kết quả rỗng mà caller không nhận biết.

## 12. Bảo mật khi truy vấn nhiều index/cluster

Mỗi index/cluster có thể có quyền truy cập riêng.

### 12.1. Least privilege

Client chỉ nên có quyền đọc những index cần thiết. Không dùng một credential có quyền quản trị cluster chỉ để chạy search.

### 12.2. CCS remote privileges

CCS cần quyền phù hợp trên coordinating cluster và remote cluster. Tùy Elasticsearch security/version, remote user hoặc API key phải có quyền đọc index/cluster cần thiết.

Không giả định quyền đọc local index tự động cho phép đọc remote index.

### 12.3. Tenant filter phải được áp dụng trên mọi nguồn

Nếu ứng dụng fan-out sang nhiều cluster, điều kiện tenant/authorization phải được áp dụng cho từng request. Một nguồn quên filter có thể làm lộ dữ liệu.

Nếu dùng CCS, bảo đảm remote index mapping và security policy áp dụng cùng tenant semantics. Query filter ở application không thay thế kiểm soát quyền ở Elasticsearch.

### 12.4. Không để client tự chọn index tùy ý

Không nhận raw index expression từ người dùng rồi đưa thẳng vào IndexCoordinates hoặc CCS request. Resolve tenant/source/index từ cấu hình hoặc authorization context đã được kiểm soát.

Index expression quá rộng có thể truy vấn dữ liệu ngoài phạm vi hoặc gây tải lớn.

## 13. Chọn giữa alias, CCS và application fan-out

| Nhu cầu | Giải pháp thường phù hợp | Lý do |
| --- | --- | --- |
| Nhiều index cùng cluster, cùng schema | Alias | Tên logic ổn định, vận hành dễ |
| Nhiều index cùng cluster, tập index thay đổi theo pattern | Index pattern | Truy vấn tập index theo quy ước |
| Nhiều cluster Elasticsearch cần một search response | CCS | Elasticsearch điều phối và reduce |
| Nhiều cluster có auth/client/policy độc lập | Nhiều operations + application fan-out | Kiểm soát từng nguồn và failure riêng |
| Join dữ liệu Elasticsearch với database | Read model hoặc application join | CCS không phải relational join |
| Cần ranking và pagination toàn cục phức tạp | Unified read model/search service | Dễ kiểm soát schema, score và cursor |
| Nguồn có độ mới khác nhau | Source version/freshness policy | Cần quyết định bản ghi nào có thẩm quyền |

### 13.1. Ưu tiên alias khi chỉ khác index vật lý

Nếu tất cả index cùng một cluster và cùng schema, alias thường là abstraction đơn giản nhất. Service không cần biết danh sách index vật lý.

### 13.2. Dùng CCS khi remote là Elasticsearch

Nếu các nguồn đều là Elasticsearch cluster và cần một search response hợp nhất, CCS có thể giảm phần code fan-out và merge ở application.

Tuy nhiên, CCS không loại bỏ yêu cầu mapping compatibility, security, latency budget, remote failure handling và pagination.

### 13.3. Dùng fan-out khi cần kiểm soát từng nguồn

Application fan-out phù hợp khi mỗi cluster cần query khác nhau, mỗi nguồn có authentication hoặc timeout riêng, cần fallback/partial result theo nghiệp vụ, kết quả cần transform trước khi merge hoặc CCS không phù hợp/không khả dụng.

Đổi lại, ứng dụng phải tự xây merge algorithm, pagination, aggregation reconciliation và duplicate handling.

### 13.4. Xây unified read model khi query thường xuyên

Nếu mỗi request phải gọi năm cluster rồi join/deduplicate/sort, chi phí và độ phức tạp sẽ tăng nhanh. Có thể xây một Elasticsearch index/read model tổng hợp được cập nhật từ các nguồn qua CDC/outbox.

Read model cần document ID và source ownership rõ, version và idempotency, schema thống nhất, reconciliation và rebuild, freshness SLO, xử lý delete/tombstone.

Đây thường là lựa chọn tốt hơn cho các truy vấn liên nguồn có tần suất cao và semantics ổn định.

## 14. Ví dụ Spring Data: tìm kiếm qua alias nhiều index

Entity:

~~~java
@Document(indexName = "products-read")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Double)
    private Double price;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Alias products-read trỏ tới products-2025 và products-2026. Repository vẫn truy vấn qua cùng logical name:

~~~java
Page<ProductDocument> products =
    productRepository.findByBrandId(
        "BRAND-10",
        PageRequest.of(0, 20)
    );
~~~

Việc alias trỏ tới index nào do Elasticsearch quản lý. Không cần thay repository code khi thêm index mới nếu mapping tương thích.

## 15. Ví dụ Spring Data: chọn nhiều index tường minh

Khi cần query một tập index cụ thể:

~~~java
public SearchHits<ProductDocument> searchArchive(
        Query query,
        ElasticsearchOperations operations) {

    IndexCoordinates indices = IndexCoordinates.of(
        "products-2024",
        "products-2025"
    );

    return operations.search(
        query,
        ProductDocument.class,
        indices
    );
}
~~~

Đây là một request trên cluster mà operations đang sử dụng. Nếu danh sách index thay đổi theo request, cần validate các tên index và không nhận raw pattern tùy ý từ client.

## 16. Ví dụ CCS bằng Elasticsearch REST API

Giả sử cluster điều phối đã cấu hình remote alias archive:

~~~http
GET /products-current,archive:products-2024/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "updatedAt": {
        "order": "desc",
        "unmapped_type": "date"
      }
    }
  ]
}
~~~

Request này được gửi đến coordinating cluster. Remote alias archive phải được cấu hình và credential phải có quyền đọc index đích.

Nếu mapping updatedAt khác nhau giữa local và remote index, sort có thể lỗi hoặc có semantics không nhất quán. unmapped_type chỉ xử lý field không có mapping; nó không giải quyết mọi kiểu mapping conflict.

## 17. Ví dụ application fan-out đến hai cluster

Khi dùng hai ElasticsearchOperations riêng, service có thể gọi từng nguồn:

~~~java
public record SearchSourceResult<T>(
    String source,
    List<T> items,
    boolean complete,
    String error
) {}
~~~

~~~java
public SearchResponse<ProductDocument> searchAcrossSources(
        Query query) {

    SearchSourceResult<ProductDocument> catalog =
        searchCatalog(query);

    SearchSourceResult<ProductDocument> archive =
        searchArchive(query);

    return mergeResults(catalog, archive);
}
~~~

Đây là cấu trúc minh họa. mergeResults cần định nghĩa sort key chung, deduplication key, nguồn có thẩm quyền khi trùng business ID, chính sách khi một nguồn lỗi, pagination cursor cho từng nguồn, cách hợp nhất aggregation và freshness/version policy.

Không ghép hai list theo thứ tự nhận response nếu thứ tự kết quả là yêu cầu nghiệp vụ.

### 17.1. Merge theo sort key

Nếu hai nguồn đã trả danh sách được sort theo cùng một key, có thể dùng k-way merge:

~~~text
Catalog: A(10), C(30), E(50)
Archive: B(20), D(40), F(60)

Merged:  A(10), B(20), C(30), D(40), E(50), F(60)
~~~

Nhưng để bảo đảm trang đầu chứa top N toàn cục, mỗi nguồn phải trả đủ số phần tử cần thiết và cursor tiếp tục phải được giữ. Nếu một nguồn timeout, kết quả không còn bảo đảm top N toàn cục.

### 17.2. Deduplicate theo business ID

Nếu cùng Product P-100 tồn tại ở cả catalog và archive, cần chọn một bản: ưu tiên nguồn hiện hành, so sánh sourceVersion, so sánh authoritative timestamp nếu có semantics rõ hoặc loại archive record nếu product đã được migrate.

Không dùng _score để quyết định bản ghi nào mới hơn.

## 18. Observability cho truy vấn nhiều nguồn

Một search service liên nguồn cần đo latency và trạng thái từng nguồn, không chỉ tổng thời gian endpoint.

| Metric | Ý nghĩa |
| --- | --- |
| search_requests_total | Tổng request tìm kiếm |
| search_source_latency | Latency theo cluster/source |
| search_source_failures_total | Lỗi theo nguồn |
| search_partial_results_total | Số response không đầy đủ |
| search_remote_timeout_total | Timeout remote cluster |
| search_shard_failures_total | Shard failure |
| search_hits_per_source | Số hits từng nguồn |
| search_merge_duration | Thời gian merge ở application |
| search_duplicate_hits_total | Hits trùng business ID |
| search_mapping_errors_total | Lỗi mapping/type |
| search_freshness_lag | Độ trễ dữ liệu theo nguồn |

Log nên có correlation ID, source name, index expression, latency, timeout, shard/remote failure và trạng thái partial. Tránh log query payload có dữ liệu nhạy cảm.

### 18.1. Phân biệt lỗi query với lỗi nguồn

Một query có thể lỗi vì syntax/DSL sai, field mapping conflict, index không tồn tại, không đủ quyền, shard failure, remote cluster timeout hoặc circuit breaker/resource exhaustion.

Phân loại lỗi giúp quyết định retry hay sửa query. Không retry vô hạn lỗi mapping hoặc authorization.

## 19. Kiểm thử thiết kế nhiều index/cluster

Integration test nên kiểm tra các ranh giới thực tế.

### 19.1. Nhiều index cùng cluster

- Tạo hai index với mapping tương thích.
- Ghi document có ID khác nhau vào từng index.
- Query bằng danh sách index hoặc alias.
- Xác nhận hits từ cả hai index.
- Xác nhận _index cho biết nguồn.
- Xác nhận sort/aggregation đúng trên toàn tập.

### 19.2. Mapping incompatibility

- Tạo một index có field numeric.
- Tạo index khác có cùng field dạng keyword.
- Thực hiện sort/range/aggregation.
- Xác nhận hệ thống phát hiện lỗi hoặc dùng chiến lược tách query.

### 19.3. CCS

- Cấu hình remote cluster test.
- Query local và remote index trong cùng request.
- Mô phỏng remote unavailable.
- Kiểm tra partial-result policy.
- Kiểm tra quyền truy cập remote.

### 19.4. Application fan-out

- Mock hoặc dùng hai cluster test riêng.
- Làm một nguồn trả chậm hoặc lỗi.
- Kiểm tra timeout/deadline.
- Kiểm tra deduplication.
- Kiểm tra merge sort và pagination.
- Kiểm tra aggregation merge nếu ứng dụng hỗ trợ.

### 19.5. Không dùng production cluster cho test failure

Test cần tạo index, thay alias hoặc ngắt remote cluster. Hãy dùng Testcontainers/test cluster và credential giới hạn quyền.

## 20. Các lỗi thường gặp

**Cho rằng nhiều IndexCoordinates có thể chọn nhiều cluster.** Coordinates chỉ chỉ định index expression cho client hiện tại. Dùng CCS hoặc nhiều client/operations.

**Dùng wildcard rộng.** Có thể truy vấn index ngoài ý muốn và làm tăng số shard. Dùng alias hoặc pattern hẹp.

**Gộp index có mapping khác nhau vào một alias.** Query, sort và aggregation có thể lỗi hoặc trả kết quả không đồng nhất. Chuẩn hóa schema trước khi gộp.

**Cho rằng alias tự deduplicate document.** Cùng business ID trong hai index vẫn tạo hai hits. Deduplicate hoặc thiết kế dữ liệu không trùng.

**Dùng write alias trỏ nhiều index mà không có write index.** Write operation có thể lỗi hoặc không xác định đích. Cấu hình is_write_index rõ ràng.

**Cho rằng repository có thể đổi index mỗi method bằng IndexCoordinates ở service.** Repository thường dùng entity metadata. Dùng operations hoặc cấu hình repository theo đúng index.

**Cấu hình nhiều ElasticsearchOperations nhưng inject không có qualifier.** Spring có thể báo multiple candidates hoặc chọn bean không mong muốn. Đặt bean name và qualifier rõ.

**Cho rằng CCS tự thiết lập remote cluster.** Remote alias phải được cấu hình trên coordinating cluster và có credential/network phù hợp.

**Dùng CCS như distributed transaction.** CCS chỉ hợp nhất search response. Ghi đa cluster cần workflow riêng.

**Coi _score từ mọi cluster là hoàn toàn so sánh được.** Corpus statistics, analyzer và mapping có thể khác. Chuẩn hóa ranking hoặc sort theo field nghiệp vụ.

**Pagination fan-out bằng cùng from/size trên mỗi nguồn.** Không bảo đảm thứ tự toàn cục hoặc top N. Dùng k-way merge và cursor từng nguồn hoặc unified read model.

**Gộp average bằng cách lấy trung bình các average.** Cần sum và count để tính average toàn cục đúng.

**Coi partial response là kết quả đầy đủ.** Kiểm tra timed_out, shard failures và remote cluster status.

**Bỏ qua tenant filter trên một nguồn.** Có thể lộ dữ liệu. Áp dụng authorization trên mọi source.

**Dùng application fan-out nhưng không đặt deadline.** Một nguồn chậm có thể giữ request vô hạn. Đặt timeout và policy partial/fallback.

**Tự ghép aggregation approximate như thể là exact.** Cardinality, percentile và terms bucket có semantics xấp xỉ/phân phối. Dùng cơ chế merge đúng hoặc unified analytics store.

## 21. Quy trình thiết kế truy vấn liên nguồn

Khi có yêu cầu search qua nhiều index hoặc cluster:

1. Liệt kê nguồn dữ liệu và xác định nguồn nào là Elasticsearch index, cluster hay hệ thống khác.
2. Xác định các index cùng cluster hay nằm ở cluster riêng.
3. Nếu cùng cluster và cùng schema, ưu tiên alias hoặc danh sách index tường minh.
4. Nếu cần query remote Elasticsearch, đánh giá CCS và cấu hình remote cluster.
5. Nếu cần auth/failure/query khác nhau theo nguồn, cân nhắc nhiều operations và application fan-out.
6. Nếu cần join thường xuyên hoặc ranking/pagination phức tạp, cân nhắc unified read model.
7. Chuẩn hóa mapping, analyzer, field type, ID và sourceVersion.
8. Xác định duplicate handling và nguồn có thẩm quyền.
9. Chọn scoring/sort strategy chung.
10. Thiết kế pagination và snapshot consistency.
11. Xác định aggregation semantics và partial failure policy.
12. Thiết lập timeout, circuit breaker, security và observability.
13. Kiểm thử mapping conflict, remote failure, duplicate, timeout và pagination.

## 22. Tài liệu tham khảo

- [Spring Data Elasticsearch - Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): ElasticsearchOperations, IndexCoordinates và query execution.
- [Spring Data Elasticsearch - Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html): repository abstraction và cấu hình repository scanning.
- [Elasticsearch - Search multiple indices](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-multiple-indices.html): index expression, wildcard và search trên nhiều index.
- [Elasticsearch - Aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html): read/write aliases và alias actions.
- [Elasticsearch - Cross-cluster search](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-cross-cluster-search.html): remote cluster và CCS.
- [Elasticsearch - Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html): search parameters, sort, pagination và partial results.
- [Elasticsearch - Pagination](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html): from/size, search_after và PIT.
- [Elasticsearch - Search aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html): distributed aggregations và kết quả reduce.
- [Elasticsearch - Distributed search](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-shard-routing.html): shard routing và distributed search behavior.

API và giới hạn CCS, PIT, remote cluster, repository configuration có thể thay đổi theo version Elasticsearch và Spring Data Elasticsearch. Hãy đối chiếu tài liệu/Javadoc khớp với dependency đang triển khai. Nguyên tắc quan trọng là nhiều index trong cùng cluster có thể được query bằng một request nếu schema tương thích; nhiều cluster cần CCS hoặc nhiều client; còn join, transaction, pagination toàn cục và nhất quán liên nguồn phải được thiết kế rõ ở tầng dữ liệu hoặc ứng dụng.
