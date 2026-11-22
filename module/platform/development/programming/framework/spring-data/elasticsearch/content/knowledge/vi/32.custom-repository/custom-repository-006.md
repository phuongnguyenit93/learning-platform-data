# Dùng client trực tiếp cho API Operations chưa cung cấp

Spring Data Elasticsearch cung cấp các abstraction cấp cao như ElasticsearchOperations, ElasticsearchTemplate và ElasticsearchRepository. Chúng phù hợp với phần lớn thao tác thường ngày: lưu và đọc entity, tìm kiếm bằng Query DSL, phân trang, aggregation, quản lý index, script và một số API chuyên biệt.

Tuy nhiên, Elasticsearch có nhiều endpoint hơn những gì các abstraction của Spring Data bao phủ. Khi ứng dụng cần một API chưa có method tương ứng trong Operations, có thể gọi trực tiếp Elasticsearch Java API Client. Cách này cho phép sử dụng request và response kiểu mạnh do Elasticsearch cung cấp mà vẫn dùng chung client, transport, xác thực và kết nối đã được Spring cấu hình.

Có ba cách tích hợp thường gặp:

- Dùng ElasticsearchTemplate.execute(...) để chạy callback với ElasticsearchClient và nhận exception translation của Spring Data.
- Inject ElasticsearchClient trực tiếp khi cần một gateway độc lập hoặc API không nằm trong repository.
- Trong ứng dụng reactive, dùng ReactiveElasticsearchTemplate.execute(...) với ReactiveElasticsearchClient để giữ luồng Publisher.

Bài viết sử dụng Term Vectors API làm ví dụ. Đây là API lấy token, tần suất xuất hiện, vị trí và offset của term trong một document; nó không phải thao tác CRUD/search thông thường mà ElasticsearchOperations cung cấp trực tiếp.

## 1. Vai trò của ElasticsearchOperations và Repository

Spring Data Elasticsearch chia thao tác thành các nhóm abstraction:

| Abstraction | Trách nhiệm |
| --- | --- |
| DocumentOperations | Lưu, cập nhật, lấy và xóa document. |
| SearchOperations | Tìm kiếm, đếm, phân trang, đọc SearchHit và kết quả aggregation. |
| IndexOperations | Tạo/xóa index, mapping, alias và các cấu hình index được hỗ trợ. |
| ElasticsearchOperations | Kết hợp các thao tác document và search, đồng thời cung cấp mapping/conversion. |
| ElasticsearchRepository | Repository CRUD và query method dựa trên Spring Data. |

ElasticsearchTemplate là implementation mặc định của ElasticsearchOperations trong client stack hiện hành. Nó dùng Elasticsearch Java API Client ở bên dưới và bổ sung mapping entity, conversion, callback, resource management cùng exception translation.

Với các truy vấn phức tạp nhưng vẫn thuộc Search API, hãy xem NativeQuery trước. NativeQuery cho phép sử dụng các query builder và aggregation builder của Elasticsearch Java API Client. Không cần chuyển sang gọi client trực tiếp chỉ vì Criteria API không biểu diễn được một truy vấn.

Chỉ nên dùng client trực tiếp khi có endpoint hoặc request option chưa được Operations/NativeQuery cung cấp, hoặc khi cần một response chuyên biệt mà abstraction hiện tại không mô hình hóa.

## 2. Khi nào cần gọi Elasticsearch Java API Client?

Một số tình huống có thể cần API cấp thấp:

- Lấy term vectors của một document.
- Gọi endpoint chuyên biệt về cluster, node hoặc snapshot.
- Thao tác với API mới của Elasticsearch mà phiên bản Spring Data đang dùng chưa có abstraction tương ứng.
- Truy cập trường request/response đặc thù mà SearchHit hoặc SearchHits không biểu diễn.
- Gọi một endpoint quản trị hoặc vận hành không thuộc luồng CRUD/search của repository.

Bảng lựa chọn:

| Nhu cầu | Cách nên ưu tiên |
| --- | --- |
| Lưu, lấy, cập nhật, xóa entity | ElasticsearchOperations hoặc Repository. |
| Query DSL, filter, sort, phân trang | Query/NativeQuery qua Operations. |
| Aggregation | NativeQuery và Operations. |
| Script đã lưu hoặc script update được hỗ trợ | ScriptOperations/UpdateQuery trước. |
| Quản lý index và mapping được hỗ trợ | IndexOperations. |
| API Elasticsearch chưa có trong Operations | ElasticsearchClient trực tiếp. |
| Cần giữ non-blocking trong reactive application | ReactiveElasticsearchClient qua ReactiveElasticsearchTemplate. |

Ví dụ, tìm sản phẩm theo tên bằng match query đã được hỗ trợ qua NativeQuery. Nhưng nếu cần đọc term vectors của field description trong một document, có thể gọi Term Vectors API trực tiếp.

Không nên xây một repository riêng chỉ để bọc lại những method mà ElasticsearchOperations đã cung cấp. Làm vậy tạo thêm lớp chuyển tiếp nhưng không bổ sung khả năng mới.

## 3. Kiến trúc khi dùng client trực tiếp

Với cấu hình imperative hiện hành, Spring Data Elasticsearch sử dụng Elasticsearch Java API Client và Rest5Client. Cấu hình thông thường tạo các bean:

~~~text
Spring Boot hoặc ElasticsearchConfiguration
              |
              v
       ClientConfiguration
              |
              v
          Rest5Client
              |
              v
    ElasticsearchTransport
              |
              v
       ElasticsearchClient
          /          \
         v            v
ElasticsearchTemplate  Custom repository fragment
         |                        |
         v                        v
ElasticsearchOperations     API chưa có trong Operations
         |
         v
Spring Data Repository
~~~

Điểm quan trọng là custom fragment nên dùng lại ElasticsearchClient do Spring quản lý. Không tự tạo một Rest5Client hoặc ElasticsearchClient mới trong từng repository, vì điều đó tạo thêm connection pool, transport, cấu hình TLS và lifecycle phải quản lý.

Spring Boot có thể auto-configure ElasticsearchClient nếu dependency và cấu hình phù hợp. Nếu dùng Java configuration, ElasticsearchConfiguration cung cấp bean ElasticsearchClient từ transport. Cả hai trường hợp đều có thể inject client vào component.

## 4. Hai cách lấy ElasticsearchClient

### 4.1. Dùng ElasticsearchTemplate.execute(...)

ElasticsearchTemplate có method execute nhận callback. Callback được cung cấp ElasticsearchClient để gọi trực tiếp API. Template thực hiện exception translation cho lỗi phát sinh trong callback.

Ví dụ:

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductTermVectorGateway {

    private final ElasticsearchTemplate template;

    public ProductTermVectorGateway(ElasticsearchTemplate template) {
        this.template = template;
    }

    public TermvectorsResponse getDescriptionTerms(String id) {
        return template.execute(client -> client.termvectors(t -> t
                .index("products")
                .id(id)
                .fields("description")
                .positions(true)
                .offsets(true)
        ));
    }
}
~~~

Trong ví dụ:

- ElasticsearchTemplate được inject từ Spring context.
- execute mở callback trên ElasticsearchClient đã cấu hình.
- client.termvectors(...) gọi Term Vectors API.
- Kết quả là TermvectorsResponse do Elasticsearch Java API Client sinh ra.
- Exception được template dịch theo cơ chế của Spring Data.

Đây là lựa chọn phù hợp khi custom repository cần gọi một API thấp hơn nhưng vẫn muốn giữ cách xử lý lỗi của Spring Data.

Lưu ý: execute là method của implementation ElasticsearchTemplate, không phải method được khai báo trên interface ElasticsearchOperations. Nếu cần execute, inject concrete ElasticsearchTemplate hoặc inject ElasticsearchClient trực tiếp; không giả định mọi implementation của ElasticsearchOperations đều có method này.

### 4.2. Inject ElasticsearchClient trực tiếp

Cũng có thể inject bean ElasticsearchClient:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.stereotype.Component;

@Component
public class ProductTermVectorClient {

    private final ElasticsearchClient client;

    public ProductTermVectorClient(ElasticsearchClient client) {
        this.client = client;
    }

    public TermvectorsResponse getDescriptionTerms(String id)
            throws java.io.IOException {

        return client.termvectors(t -> t
                .index("products")
                .id(id)
                .fields("description")
                .positions(true)
                .offsets(true)
        );
    }
}
~~~

Cách này hữu ích khi muốn tạo một gateway độc lập với ElasticsearchTemplate hoặc khi cần dùng nhiều API Java Client trong cùng component.

Khác biệt chính:

| Tiêu chí | Template execute | Inject ElasticsearchClient |
| --- | --- | --- |
| Client | Dùng client mà template đang sử dụng. | Dùng bean ElasticsearchClient do Spring quản lý. |
| Exception translation | Có exception translation của template. | Nhận exception từ Java API Client. |
| Mapping entity Spring Data | Không tự động map response của API thấp cấp thành entity. | Không tự động map response thành entity. |
| Phụ thuộc | Phụ thuộc implementation ElasticsearchTemplate. | Phụ thuộc Elasticsearch Java API Client. |
| Phù hợp | Custom repository fragment cần hòa nhập với Spring Data. | Gateway/service chuyên biệt cần gọi nhiều endpoint. |

Dù chọn cách nào, không khởi tạo client mới trong method. Hãy dùng bean singleton đã cấu hình endpoint, TLS, authentication và timeout của ứng dụng.

## 5. Tích hợp theo custom repository fragment

Spring Data khuyến nghị mở rộng repository bằng fragment interface và implementation. Mỗi fragment bổ sung một nhóm chức năng riêng vào repository hiện có.

Ví dụ cần một method lấy term vectors của mô tả sản phẩm.

### 5.1. Khai báo fragment interface

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;

public interface ProductTermVectorRepository {

    TermvectorsResponse getDescriptionTerms(String productId);
}
~~~

Interface chỉ mô tả chức năng nghiệp vụ mà caller cần. Nó không cần kế thừa ElasticsearchRepository hoặc ElasticsearchOperations.

### 5.2. Kết hợp fragment vào repository

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductTermVectorRepository {
}
~~~

ProductRepository có cả CRUD/query method của ElasticsearchRepository và method bổ sung getDescriptionTerms(...).

### 5.3. Viết implementation

Tên implementation mặc định được tạo từ tên fragment interface cộng hậu tố Impl:

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductTermVectorRepositoryImpl
        implements ProductTermVectorRepository {

    private final ElasticsearchTemplate template;

    public ProductTermVectorRepositoryImpl(
            ElasticsearchTemplate template) {
        this.template = template;
    }

    @Override
    public TermvectorsResponse getDescriptionTerms(String productId) {
        return template.execute(client -> client.termvectors(t -> t
                .index("products")
                .id(productId)
                .fields("description")
                .positions(true)
                .offsets(true)
                .termStatistics(true)
        ));
    }
}
~~~

Spring Data ghép fragment implementation vào repository proxy. Khi service gọi productRepository.getDescriptionTerms(...), method được chuyển tới implementation của fragment.

Implementation cần nằm trong phạm vi package scan mà repository infrastructure có thể phát hiện, trừ khi cấu hình fragment thủ công. Nếu đổi postfix bằng repository configuration, tên class implementation cũng phải theo postfix mới.

### 5.4. Sử dụng repository

~~~java
@Service
public class ProductAnalysisService {

    private final ProductRepository productRepository;

    public ProductAnalysisService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public TermvectorsResponse analyzeDescription(String productId) {
        return productRepository.getDescriptionTerms(productId);
    }
}
~~~

Service chỉ phụ thuộc vào repository contract. Nó không cần biết callback, ElasticsearchClient hay cách tạo request termvectors.

## 6. Ví dụ API chưa có trong Operations: Term Vectors

Term Vectors API trả thông tin token của một document. Tùy request, response có thể chứa:

- Tần suất xuất hiện của từng term trong field.
- Vị trí token trong văn bản.
- Offset bắt đầu và kết thúc của token.
- Payload nếu mapping và request hỗ trợ.
- Term statistics và field statistics.

Ví dụ REST request:

~~~http
GET /products/_termvectors/P-100
Content-Type: application/json

{
  "fields": ["description"],
  "positions": true,
  "offsets": true,
  "term_statistics": true,
  "field_statistics": false
}
~~~

Request Java API Client tương ứng:

~~~java
TermvectorsResponse response = client.termvectors(t -> t
        .index("products")
        .id("P-100")
        .fields("description")
        .positions(true)
        .offsets(true)
        .termStatistics(true)
        .fieldStatistics(false)
);
~~~

Response được biểu diễn bằng TermvectorsResponse. Có thể kiểm tra document có tồn tại và đọc map term vectors theo field:

~~~java
if (!response.found()) {
    // Document không tồn tại.
    return;
}

var descriptionVector = response.termVectors().get("description");

if (descriptionVector == null) {
    // Không có term vector cho field được yêu cầu.
    return;
}

var terms = descriptionVector.terms();
~~~

Mỗi entry trong terms map đại diện cho một term và metadata tương ứng. Ứng dụng có thể đọc frequency, positions hoặc offsets theo cấu trúc Term và TermVector của phiên bản Elasticsearch Java Client đang dùng.

### 6.1. Mapping và term vectors

Elasticsearch có thể lưu term vectors trong index hoặc tính chúng từ dữ liệu đã index khi có thể. Nếu use case cần term positions và offsets thường xuyên, có thể khai báo term_vector trong mapping:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "term_vector": "with_positions_offsets"
      }
    }
  }
}
~~~

Các tùy chọn term vector thường gặp:

| Giá trị | Thông tin lưu |
| --- | --- |
| no | Không lưu term vectors. Đây là mặc định. |
| yes | Lưu term và tần suất. |
| with_positions | Thêm vị trí token. |
| with_offsets | Thêm offset ký tự. |
| with_positions_offsets | Lưu cả vị trí và offset. |
| with_positions_offsets_payloads | Lưu vị trí, offset và payload. |

Lưu term vectors làm tăng dung lượng index và có thể làm tăng chi phí ghi. Chỉ bật khi ứng dụng thật sự cần thông tin đó và đã đo ảnh hưởng trên dữ liệu đại diện.

### 6.2. Ý nghĩa của statistics

Term statistics và field statistics không phải lúc nào cũng là số liệu toàn index chính xác. Term Vectors API lấy thông tin từ shard chứa document; các thống kê được trả về có giới hạn và nên được hiểu theo mục đích của API.

Nếu chỉ cần frequency/positions/offsets của document, không yêu cầu statistics không cần thiết. Giảm payload giúp request rõ mục đích hơn.

### 6.3. Lấy term vectors cho nhiều document

Elasticsearch Java API Client còn có mtermvectors để lấy term vectors cho nhiều document trong một request:

~~~java
var response = client.mtermvectors(m -> m
        .index("products")
        .ids("P-100", "P-101", "P-102")
        .fields("description")
        .positions(true)
        .offsets(true)
);
~~~

API batch hữu ích khi phân tích một nhóm document. Cần giới hạn số ID trong mỗi request và kiểm soát kích thước response. Không gửi một danh sách vô hạn chỉ vì endpoint hỗ trợ nhiều document.

## 7. Dùng client trực tiếp trong custom service thay vì repository

Không phải mọi API Elasticsearch đều thuộc trách nhiệm của repository. Repository thường đại diện cho truy cập dữ liệu theo aggregate/domain type. Các API quản trị cluster như snapshot, node stats, cluster settings hoặc index lifecycle thường phù hợp hơn với service vận hành riêng.

Ví dụ một gateway quản trị snapshot:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.snapshot.CreateSnapshotResponse;
import org.springframework.stereotype.Component;

@Component
public class SnapshotGateway {

    private final ElasticsearchClient client;

    public SnapshotGateway(ElasticsearchClient client) {
        this.client = client;
    }

    public CreateSnapshotResponse createSnapshot(
            String repository,
            String snapshot,
            String index) throws java.io.IOException {

        return client.snapshot().create(s -> s
                .repository(repository)
                .snapshot(snapshot)
                .indices(index)
                .includeGlobalState(false)
                .waitForCompletion(false)
        );
    }
}
~~~

Đây là ví dụ service-level vì snapshot là tác vụ quản trị cluster, không phải hành vi của ProductRepository.

Cần cấp cluster privilege phù hợp cho danh tính chạy snapshot. Không cấp quyền quản trị cluster cho service nghiệp vụ chỉ để thực hiện CRUD sản phẩm.

## 8. Direct client không tự dùng Spring Data mapping

Khi gọi ElasticsearchTemplate.save(entity), Spring Data dùng mapping metadata để chuyển entity thành document. Quá trình này có thể xét:

- @Document và index name.
- @Id và @Field.
- Field naming strategy.
- Custom conversions.
- Type hints.
- Entity callbacks.
- Routing và refresh policy theo cấu hình template.

Khi gọi client.index(...) hoặc client.get(...), Elasticsearch Java API Client dùng serializer/JsonpMapper của transport và kiểu dữ liệu mà caller chỉ định. Nó không tự chạy toàn bộ entity mapping lifecycle của Spring Data.

Ví dụ direct client:

~~~java
var response = client.get(g -> g
        .index("products")
        .id("P-100"),
        Product.class
);
~~~

Đây là Java API Client deserialize source sang Product theo JsonpMapper. Không nên giả định mọi annotation Spring Data trên Product đều được áp dụng giống khi đọc qua ElasticsearchOperations.

Nếu cần Spring Data mapping, hãy dùng Operations để lấy entity rồi gọi client trực tiếp cho phần API bổ sung. Nếu response là model riêng của Elasticsearch, giữ nó ở tầng gateway/adapter và chuyển sang DTO nghiệp vụ khi cần.

## 9. Không làm mất cấu hình client hiện có

Khi gọi client trực tiếp, hãy tái sử dụng bean được Spring quản lý. Cấu hình kết nối thường được cung cấp bằng ElasticsearchConfiguration hoặc Spring Boot auto-configuration.

Ví dụ cấu hình Java:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

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

Cấu hình này tạo transport và ElasticsearchClient. Các component có thể inject ElasticsearchClient hoặc ElasticsearchTemplate.

Nếu ứng dụng dùng Spring Boot, Boot có thể tạo client từ các thuộc tính spring.elasticsearch. Không thêm một client thứ hai chỉ để gọi một API khác.

Các thành phần cần được giữ nhất quán:

- Endpoint và danh sách node.
- TLS/certificate validation.
- Basic auth hoặc API key.
- Default headers.
- Connect/socket timeout.
- Proxy và path prefix.
- TransportOptions và JsonpMapper.
- Observation/tracing nếu đã cấu hình.

Không tạo Rest5Client mới bên trong repository. Rest5Client là low-level HTTP transport; phần lớn use case direct API nên dùng ElasticsearchClient có kiểu mạnh.

## 10. Reactive custom repository

Nếu ứng dụng dùng reactive stack, không gọi ElasticsearchClient đồng bộ từ WebFlux request path. Dùng ReactiveElasticsearchClient và ReactiveElasticsearchTemplate.

ReactiveElasticsearchTemplate có execute callback để gọi trực tiếp reactive client và trả Publisher. Ví dụ:

~~~java
import co.elastic.clients.elasticsearch.core.TermvectorsResponse;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchTemplate;
import reactor.core.publisher.Mono;

public class ReactiveProductTermVectorRepositoryImpl {

    private final ReactiveElasticsearchTemplate template;

    public ReactiveProductTermVectorRepositoryImpl(
            ReactiveElasticsearchTemplate template) {
        this.template = template;
    }

    public Mono<TermvectorsResponse> getDescriptionTerms(String productId) {
        return Mono.from(template.execute(client ->
                client.termvectors(t -> t
                        .index("products")
                        .id(productId)
                        .fields("description")
                        .positions(true)
                        .offsets(true)
                )
        ));
    }
}
~~~

Callback reactive trả Publisher; Mono.from(...) chuyển Publisher một kết quả thành Mono. Việc gọi API chỉ diễn ra khi publisher được subscribe.

Không gọi block() hoặc subscribe() bên trong custom repository reactive. Hãy trả Mono/Flux cho caller để framework quản lý subscription, cancellation và error signal.

## 11. Xử lý lỗi từ client trực tiếp

Elasticsearch Java API Client có thể phát sinh:

- IOException do lỗi truyền tải hoặc đọc response.
- ElasticsearchException khi cluster trả lỗi API.
- Lỗi mapping/serialization khi chuyển đổi JSON.
- Lỗi xác thực hoặc phân quyền.
- Lỗi do request không hợp lệ hoặc API không tương thích phiên bản.

Khi dùng ElasticsearchTemplate.execute, template thực hiện exception translation để chuyển một số lỗi sang hệ exception của Spring Data.

Khi inject ElasticsearchClient trực tiếp, caller cần xử lý exception phù hợp với API và kiến trúc ứng dụng.

Ví dụ:

~~~java
public TermvectorsResponse getTerms(String id) {
    try {
        return client.termvectors(t -> t
                .index("products")
                .id(id)
                .fields("description")
        );
    } catch (IOException ex) {
        throw new ProductSearchInfrastructureException(
                "Could not read product term vectors", ex
        );
    }
}
~~~

Trong code thực tế, nên phân biệt lỗi kết nối, lỗi 404, lỗi 401/403, lỗi request 400 và lỗi server 5xx. Không bắt Exception chung rồi trả danh sách rỗng, vì điều đó che giấu lỗi cấu hình hoặc lỗi nghiệp vụ.

Không log toàn bộ request/response nếu chúng chứa dữ liệu nhạy cảm. Có thể log index, endpoint, request ID, error type và script/query ID phù hợp với chính sách observability.

## 12. Phân quyền và bảo mật

Direct client không vượt qua security của Elasticsearch. Request vẫn chạy dưới danh tính và credential được cấu hình trong transport.

Ví dụ:

| API | Quyền thường cần |
| --- | --- |
| Term Vectors | Quyền đọc document/index tương ứng. |
| Snapshot create | Cluster privilege tạo snapshot và quyền cần thiết với snapshot repository. |
| Cluster/node monitoring | Cluster monitor privilege hoặc privilege tương ứng với endpoint. |
| Index metadata | Index/cluster privilege theo API cụ thể. |

Chỉ cấp quyền cần thiết cho service. Nếu một service chỉ đọc term vectors từ products, không cấp quyền quản trị snapshot hoặc thay đổi cluster settings.

Đối với API quản trị, nên tách gateway/service và credential vận hành khỏi service nghiệp vụ. Kiểm tra security privilege theo endpoint và phiên bản Elasticsearch, vì quyền có thể khác nhau giữa API.

## 13. Giới hạn phiên bản và tương thích

Elasticsearch Java API Client sinh request/response model theo phiên bản client. Một method hoặc field có thể chưa tồn tại trong client mà Spring Data đang quản lý, dù cluster Elasticsearch mới đã hỗ trợ endpoint đó.

Khi cần một API mới:

1. Kiểm tra phiên bản Elasticsearch cluster.
2. Kiểm tra phiên bản Spring Data Elasticsearch.
3. Kiểm tra phiên bản Elasticsearch Java API Client được dependency quản lý.
4. Xác nhận endpoint và field request đã có trong client.
5. Chỉ nâng client riêng khi compatibility matrix cho phép.
6. Kiểm thử serialization, response và lỗi trên cluster tương thích.

Không ép dependency Elasticsearch Java Client lên phiên bản khác một cách tùy tiện. Spring Data Elasticsearch phụ thuộc vào các kiểu client cụ thể; nâng client độc lập có thể gây lỗi binary hoặc API incompatibility.

Nếu endpoint chưa có trong Java API Client hiện tại, cân nhắc:
- Chờ phiên bản client hỗ trợ.
- Nâng Spring Data và client theo compatibility matrix.
- Dùng low-level HTTP client đã được cấu hình trong Spring để gọi REST endpoint, nhưng phải tự chịu trách nhiệm serialize request, parse response, xử lý lỗi và kiểm tra security.

Không quay lại RestHighLevelClient cũ cho code mới. RestHighLevelClient đã bị loại bỏ khỏi các thế hệ Elasticsearch mới.

## 14. Kiểm thử custom repository

Custom fragment có thể kiểm thử bằng mock ElasticsearchTemplate hoặc mock ElasticsearchClient, tùy cách triển khai.

Với implementation dùng template.execute, có thể kiểm tra:

- Fragment gọi đúng API và index.
- Document ID được truyền chính xác.
- Field list và các tùy chọn term vectors đúng yêu cầu.
- Response được trả lại cho caller.
- Lỗi từ callback được chuyển tiếp hoặc dịch theo contract.
- Không tạo client mới trong mỗi method.

Ví dụ kiểm thử ở mức service/fragment:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductTermVectorRepositoryImplTest {

    @Mock
    ElasticsearchTemplate template;

    @Test
    void delegatesTermVectorRequestToTemplate() {
        // Stub template.execute(...) và xác nhận kết quả.
        // Có thể dùng Answer nếu cần kiểm tra callback với client giả.
    }
}
~~~

Vì execute nhận callback, test cần gọi callback với client mock hoặc dùng integration test để xác minh request thật. Không nên chỉ xác nhận template.execute được gọi mà không kiểm tra nội dung request quan trọng.

Với integration test:

- Dùng Elasticsearch tương thích với client.
- Tạo index và mapping cần thiết.
- Index document có field cần lấy term vectors.
- Gọi repository fragment.
- Kiểm tra found, field, term, frequency, positions và offsets.
- Kiểm tra document không tồn tại.
- Kiểm tra lỗi thiếu privilege.
- Kiểm tra trường hợp field không có term vector hoặc không có giá trị.

Testcontainers có thể cung cấp cluster tạm thời. Dùng image version phù hợp với Spring Data Elasticsearch và Java API Client trong dự án.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không inject được ElasticsearchClient | Chưa có auto-configuration hoặc cấu hình Java client. | Kiểm tra dependency, bean và ElasticsearchConfiguration. |
| Không gọi được execute trên ElasticsearchOperations | execute không thuộc interface ElasticsearchOperations. | Inject ElasticsearchTemplate hoặc ElasticsearchClient. |
| Không tìm thấy fragment implementation | Sai tên hậu tố, package hoặc repository scan. | Dùng tên FragmentNameImpl và đặt class trong phạm vi scan. |
| Direct client không áp dụng @Field mapping | Java API Client dùng JsonpMapper, không chạy toàn bộ Spring Data converter. | Dùng Operations cho entity mapping hoặc tự chuyển đổi response. |
| Lỗi 401/403 | Credential hoặc privilege không đủ. | Kiểm tra danh tính, index privileges và cluster privileges. |
| IOException | Lỗi kết nối, timeout hoặc response transport. | Kiểm tra endpoint, TLS, timeout và network. |
| API không tồn tại trong client | Java API Client quá cũ so với endpoint cluster. | Kiểm tra compatibility và nâng cấp theo matrix. |
| Term vectors trả field rỗng | Field không được index hoặc không có dữ liệu phù hợp. | Kiểm tra mapping và document source. |
| Term vectors tốn tài nguyên | Tính term vectors on the fly hoặc lấy quá nhiều metadata. | Chỉ yêu cầu field cần thiết; cân nhắc lưu term_vector khi use case lặp lại. |
| Reactive endpoint bị blocking | Gọi ElasticsearchClient đồng bộ trong WebFlux. | Dùng ReactiveElasticsearchTemplate/ReactiveElasticsearchClient. |
| Tạo nhiều connection pool | Tự tạo client trong fragment/service. | Inject bean singleton do Spring quản lý. |

## 16. Quy trình lựa chọn cách triển khai

Khi cần một tính năng Elasticsearch mới trong repository:

1. Kiểm tra ElasticsearchOperations, IndexOperations, ScriptOperations và SearchOperations đã có method tương ứng chưa.
2. Nếu là truy vấn, kiểm tra CriteriaQuery, StringQuery hoặc NativeQuery trước.
3. Nếu API chưa có abstraction, kiểm tra Elasticsearch Java API Client có hỗ trợ endpoint không.
4. Tạo fragment interface với tên method theo ngôn ngữ nghiệp vụ.
5. Tạo implementation có hậu tố Impl.
6. Inject ElasticsearchTemplate hoặc ElasticsearchClient đã được Spring cấu hình.
7. Gọi API trong callback hoặc gateway riêng.
8. Chuyển low-level response thành DTO nếu không muốn rò rỉ client model ra ngoài.
9. Xử lý exception, security và timeout theo contract của service.
10. Kiểm thử request/response với Elasticsearch version tương thích.
11. Theo dõi latency, lỗi và resource usage.
12. Khi Spring Data bổ sung abstraction chính thức, đánh giá việc chuyển lại để giảm code tự quản lý.

## 17. Tài liệu tham khảo

- [Spring Data Elasticsearch — Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Spring Data Elasticsearch — ElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchTemplate.html)
- [Spring Data Elasticsearch — ElasticsearchTemplate.ClientCallback API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchTemplate.ClientCallback.html)
- [Elasticsearch — Get term vector information](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-termvectors)
- [Elasticsearch — Java API Client](https://www.elastic.co/docs/reference/elasticsearch/clients/java)
- [Elasticsearch — Create a snapshot](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-snapshot-create)

Khi Operations chưa cung cấp một endpoint, custom repository fragment có thể gọi Elasticsearch Java API Client trực tiếp. ElasticsearchTemplate.execute là cách phù hợp khi muốn dùng client chung và exception translation của Spring Data; inject ElasticsearchClient trực tiếp phù hợp với gateway chuyên biệt. Cần giữ mapping boundary rõ ràng, không tạo client riêng, dùng reactive client trong reactive application và kiểm tra compatibility cùng security privilege của API cụ thể.

