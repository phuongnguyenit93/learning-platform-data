# Cách ly nhiều khách hàng bằng index hoặc bộ lọc tenant

Trong ứng dụng SaaS, nhiều khách hàng (tenant) có thể dùng chung một cụm Elasticsearch. Mỗi tenant cần chỉ nhìn thấy dữ liệu của mình, kể cả khi hai tenant có document ID giống nhau hoặc cùng tìm kiếm một loại dữ liệu.

Spring Data Elasticsearch cung cấp API lưu trữ, tìm kiếm và mapping document; nó không tự động tạo ranh giới bảo mật giữa các tenant. Kiến trúc phải quyết định nơi đặt ranh giới đó và bảo đảm mọi đường truy cập đều tuân theo cùng một quy tắc.

Hai mô hình phổ biến là:

- **Index riêng cho từng tenant:** dữ liệu của mỗi khách hàng nằm trong index riêng. Có thể giới hạn quyền Elasticsearch theo index.
- **Index dùng chung với tenant filter:** nhiều khách hàng dùng cùng index, mỗi document có trường tenantId và mọi thao tác được giới hạn theo tenant đó.

Có thể kết hợp hai mô hình cho hệ thống có nhiều tenant nhỏ và một số tenant lớn. Dù chọn cách nào, tenant identity phải được lấy từ danh tính đã xác thực, không tin tenantId do client tự gửi lên.

## 1. Mục tiêu của cách ly tenant

Một thiết kế multi-tenant cần bảo đảm:

1. Tenant A không thể đọc document của tenant B.
2. Tenant A không thể cập nhật hoặc xóa document của tenant B.
3. Search, aggregation, count, bulk và các endpoint phụ trợ đều tuân thủ cùng ranh giới.
4. Tenant không thể chọn index hoặc alias của tenant khác bằng cách sửa request.
5. Một document ID giống nhau ở hai tenant không gây ghi đè hoặc truy cập nhầm.
6. Quyền truy cập được kiểm soát ở server-side và có thể kiểm thử.
7. Việc thêm tenant mới không đòi hỏi thay đổi code hoặc cấu hình thủ công không kiểm soát.

Cách ly tenant bao gồm cả đọc và ghi. Một search filter đúng chưa đủ nếu API get-by-ID, update, delete, bulk hoặc endpoint export vẫn truy cập document mà không kiểm tra tenant.

Cũng cần phân biệt ba lớp:

- **Data partitioning:** dữ liệu được đặt ở index nào, shard nào và field nào.
- **Application authorization:** service xác định tenant nào được phép thao tác.
- **Elasticsearch security:** cluster/index privileges, document-level security (DLS) và field-level security (FLS) hạn chế những gì credential có thể đọc hoặc thay đổi.

Các lớp này bổ trợ nhau. Routing hoặc alias có thể giúp định tuyến và đơn giản hóa truy vấn, nhưng không tự thay thế authorization.

## 2. Chọn mô hình lưu trữ

### 2.1. Một index cho mỗi tenant

Mỗi tenant có index riêng, ví dụ:

~~~text
products-tenant-001
products-tenant-002
products-tenant-003
~~~

Ưu điểm:

- Có thể cấp index privileges theo tenant.
- Cùng một document ID có thể xuất hiện ở các index khác nhau.
- Dễ áp dụng index template, mapping và lifecycle policy theo nhóm tenant.
- Có thể snapshot, restore, reindex hoặc xóa dữ liệu một tenant độc lập hơn.
- Dễ giới hạn phạm vi truy cập bằng credential chỉ có quyền trên index tương ứng.

Nhược điểm:

- Số lượng index và shard tăng theo số tenant.
- Tạo quá nhiều index nhỏ làm tăng cluster state, heap và chi phí quản trị.
- Cần tự động hóa tạo index, mapping, alias, lifecycle và migration.
- Cross-tenant reporting cần truy vấn nhiều index hoặc một index tổng hợp.
- Thay đổi mapping phải được triển khai đồng bộ cho nhiều index.

Mô hình này phù hợp khi tenant cần ranh giới truy cập mạnh ở cấp index, có quy mô dữ liệu đáng kể hoặc cần vòng đời dữ liệu độc lập.

### 2.2. Một index dùng chung, lọc bằng tenantId

Tất cả tenant lưu document trong cùng index:

~~~text
products
  ├── tenantId = tenant-001, document P-100
  ├── tenantId = tenant-002, document P-100
  └── tenantId = tenant-003, document P-200
~~~

Mapping cần một trường tenantId có kiểu keyword:

~~~json
{
  "mappings": {
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      }
    }
  }
}
~~~

Ưu điểm:

- Ít index và shard hơn khi có nhiều tenant nhỏ.
- Dễ áp dụng một mapping và một pipeline triển khai.
- Dễ chạy tác vụ quản trị hoặc báo cáo trên toàn bộ tenant khi được cấp quyền.
- Thêm tenant mới thường không cần tạo index.
- Tận dụng tài nguyên cluster tốt khi dữ liệu của các tenant phân tán đều.

Nhược điểm:

- Mọi truy vấn tenant-facing phải mang tenant filter.
- Một đường code quên filter có thể làm lộ dữ liệu chéo tenant nếu không có lớp bảo vệ bổ sung.
- Cùng một index không cho phép index privileges phân biệt document theo tenant.
- Một tenant có lượng dữ liệu hoặc tải rất lớn có thể ảnh hưởng tenant khác.
- ID document phải được thiết kế để tránh va chạm trong cùng index.

Mô hình này phù hợp khi có nhiều tenant nhỏ, dữ liệu có cấu trúc tương tự và hệ thống có một lớp truy cập dữ liệu được kiểm soát chặt.

### 2.3. Mô hình hybrid

Một hệ thống có thể dùng index chung cho tenant nhỏ và index riêng cho tenant lớn hoặc tenant có yêu cầu cô lập cao:

~~~text
small tenants
     |
     v
shared-products
  tenantId filter

large tenant A
     |
     v
products-tenant-A

regulated tenant B
     |
     v
products-tenant-B
~~~

Cách này cần một tenant-to-storage resolver để xác định nơi lưu dữ liệu của mỗi tenant. Resolver phải lấy tenant từ security context đã xác thực và tra cứu cấu hình lưu trữ đáng tin cậy.

Không để client truyền trực tiếp tên index. Nếu tenant có thể gửi một chuỗi bất kỳ làm index name, họ có thể thử truy cập index ngoài phạm vi được cấp.

### 2.4. So sánh nhanh

| Tiêu chí | Index riêng | Index chung + tenant filter |
| --- | --- | --- |
| Ranh giới ở Elasticsearch | Có thể giới hạn theo index privilege. | Cần DLS hoặc lớp ứng dụng để giới hạn document. |
| Số lượng index | Tăng theo tenant. | Ít index hơn. |
| Chi phí quản trị | Provisioning và migration phức tạp hơn. | Mapping và lifecycle đơn giản hơn. |
| ID giống nhau giữa tenant | Được phép ở index khác nhau. | Cần ID toàn index duy nhất hoặc composite ID. |
| Cross-tenant analytics | Cần truy vấn nhiều index hoặc index tổng hợp. | Dễ hơn trong cùng index nếu có quyền. |
| Xóa dữ liệu tenant | Có thể xóa index riêng sau quy trình kiểm soát. | Cần xóa theo tenant filter và xác minh phạm vi. |
| Tenant lớn bất thường | Có thể tách shard/index riêng. | Có nguy cơ noisy neighbor. |
| Cấu hình security | Role theo index. | DLS có thể giới hạn đọc; write vẫn cần kiểm soát ở ứng dụng hoặc phân vùng khác. |

Không có một lựa chọn đúng cho mọi hệ thống. Quyết định phụ thuộc số tenant, kích thước dữ liệu, yêu cầu compliance, tải truy vấn, chi phí shard và khả năng tự động hóa vận hành.

## 3. Tenant identity phải đến từ nguồn tin cậy

Tenant ID là một phần của authorization context. Không dùng giá trị tenant do request body hoặc query parameter cung cấp làm căn cứ truy cập dữ liệu.

Một luồng phù hợp:

~~~text
HTTP request
     |
     v
Authentication
     |
     v
JWT / session / API credential
     |
     v
Resolve tenant membership
     |
     v
Trusted TenantContext
     |
     v
Service / Repository
     |
     v
Tenant-scoped Elasticsearch request
~~~

Ví dụ request có thể chứa tenantId trong URL để chọn một tài nguyên, nhưng server phải xác minh tenant đó nằm trong danh sách tenant mà principal được phép truy cập. Nếu ứng dụng chỉ hỗ trợ một tenant trong mỗi request, hãy lấy tenant ID từ claim hoặc membership đã xác thực.

Một số nguyên tắc:

- Không tin tenantId trong JSON payload.
- Không cho caller tự chọn index name.
- Không cho caller tự gửi DLS query hoặc Elasticsearch Query DSL tùy ý.
- Không dùng tenant ID chưa được kiểm tra để tạo alias hoặc routing value.
- Gắn tenant ID vào audit log cùng principal và request ID.
- Với tác vụ background, lưu tenant ID trong job payload đã được xác thực và kiểm tra lại khi chạy.

Nếu người dùng có thể thuộc nhiều tenant, authorization phải xác định tenant hiện tại mà họ đang thao tác. Không mặc định rằng biết ID của tenant đồng nghĩa có quyền truy cập tenant đó.

## 4. Thiết kế document và tenantId

Với shared index, mỗi document phải có tenantId:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructor, getters và setters
}
~~~

tenantId nên là keyword vì ứng dụng thường dùng exact match, filter và aggregation theo tenant. Không dùng text analyzer cho tenant identity.

Có thể đặt mapping strict hơn để ngăn document thiếu hoặc có field sai kiểu, nhưng dynamic mapping và dynamic templates cần được thiết kế cùng schema của ứng dụng. Quan trọng nhất là service phải gán tenantId từ context đã xác thực khi tạo document.

### 4.1. Tenant ID nên bất biến

Khi document đã được tạo trong tenant A, không cho phép một update thông thường đổi tenantId sang tenant B. Thay đổi tenant là thao tác di chuyển dữ liệu có chủ đích, cần quy trình riêng:

1. Xác thực quyền trên tenant nguồn và tenant đích.
2. Đọc document nguồn.
3. Kiểm tra xung đột ID và business key.
4. Ghi document vào nơi lưu của tenant đích.
5. Xác minh dữ liệu và quan hệ liên quan.
6. Xóa document nguồn sau khi xác nhận.
7. Ghi audit event.

Không cho phép DTO cập nhật chung chứa tenantId rồi dùng nó để ghi đè entity. Hãy loại tenantId khỏi request update hoặc kiểm tra nó khớp tenant context hiện tại.

### 4.2. ID document trong shared index

Trong một index dùng chung, Elasticsearch yêu cầu _id duy nhất trong phạm vi index. Nếu hai tenant đều có sản phẩm ID P-100, một lần index có thể ghi đè document còn lại nếu dùng cùng _id.

Có hai cách phổ biến:

- Dùng ID nội bộ toàn cục được sinh bởi hệ thống.
- Dùng composite ID từ tenant và business ID, ví dụ tenant-001:P-100.

Ví dụ hàm tạo ID:

~~~java
public String documentId(String tenantId, String businessId) {
    return tenantId + ":" + businessId;
}
~~~

Chỉ dùng giá trị tenantId đã được xác thực và businessId đã được validate. Nếu ID có thể chứa dấu phân cách, hãy dùng encoding hoặc định dạng composite có thể giải mã không mơ hồ.

Với index riêng cho tenant, cùng _id có thể tồn tại trong các index khác nhau. Tuy nhiên, vẫn cần tenant-aware index resolution để ngăn truy cập sai index.

## 5. Cách ly bằng index riêng trong Spring Data

Annotation @Document thường khai báo index mặc định của entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // fields
}
~~~

Với index động theo tenant, có thể truyền IndexCoordinates vào các method của ElasticsearchOperations. IndexCoordinates chỉ định index thực tế cho thao tác hiện tại.

Ví dụ resolver:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;

@Component
public class TenantIndexResolver {

    public IndexCoordinates productsIndex(TenantId tenantId) {
        String indexName = "products-" + tenantId.value();
        return IndexCoordinates.of(indexName);
    }
}
~~~

TenantId trong ví dụ là kiểu miền được tạo từ tenant identity đã xác thực, không phải chuỗi tùy ý do client gửi. Trong hệ thống thực tế, index name cần được chuẩn hóa theo quy tắc tên index của Elasticsearch hoặc được lấy từ registry cấu hình tenant.

Lưu document:

~~~java
@Service
public class TenantProductService {

    private final ElasticsearchOperations operations;
    private final TenantIndexResolver indexResolver;

    public TenantProductService(
            ElasticsearchOperations operations,
            TenantIndexResolver indexResolver) {
        this.operations = operations;
        this.indexResolver = indexResolver;
    }

    public ProductDocument save(TenantId tenantId, ProductDocument product) {
        product.setTenantId(tenantId.value());

        IndexCoordinates index = indexResolver.productsIndex(tenantId);
        return operations.save(product, index);
    }
}
~~~

Đọc document:

~~~java
public ProductDocument findById(TenantId tenantId, String id) {
    IndexCoordinates index = indexResolver.productsIndex(tenantId);
    return operations.get(id, ProductDocument.class, index);
}
~~~

Tại đây index được chọn từ tenant đã xác thực. Cùng một document ID có thể xuất hiện trong index của tenant khác nhưng request chỉ nhắm tới index tương ứng.

### 5.1. Vì sao repository mặc định có thể không đủ?

Repository thường lấy index mặc định từ @Document. Một repository dùng chung có thể không tự biết tenant hiện tại để chọn concrete index.

Với index-per-tenant, có thể:

- Dùng ElasticsearchOperations và truyền IndexCoordinates theo từng request.
- Tạo adapter/service riêng để che việc chọn index khỏi controller.
- Dùng repository riêng cho từng nhóm index cố định nếu số nhóm nhỏ.
- Dùng custom repository fragment có tenant-aware index resolver.

Không tạo một repository hoặc ElasticsearchClient mới cho mỗi request. Việc chọn IndexCoordinates là đủ để đổi index đích trong thao tác Operations.

### 5.2. Tạo và quản lý index theo tenant

Index của tenant cần cùng mapping và settings cơ bản. Có thể dùng index template để áp dụng cấu hình khi tạo index mới:

~~~http
PUT /_index_template/products-template
Content-Type: application/json

{
  "index_patterns": ["products-*"],
  "template": {
    "mappings": {
      "properties": {
        "tenantId": { "type": "keyword" },
        "sku": { "type": "keyword" },
        "name": { "type": "text" },
        "category": { "type": "keyword" }
      }
    }
  }
}
~~~

Provisioning service có thể tạo concrete index khi tenant được kích hoạt. Hãy tách quyền tạo index khỏi credential runtime nếu service nghiệp vụ không cần quyền quản trị index.

Cần quản lý:

- Mapping version.
- Number of primary shards và replica policy.
- Index template và component template.
- Lifecycle/retention policy.
- Alias đọc/ghi.
- Snapshot và restore.
- Migration khi mapping thay đổi.
- Quy trình offboarding và xóa dữ liệu tenant.

Không tạo index mặc định một primary shard cho mọi tenant mà không xem xét tổng số tenant và kích thước dữ liệu. Hàng nghìn index nhỏ có thể tạo ra hàng nghìn shard và gây áp lực đáng kể lên cluster.

## 6. Cách ly bằng tenant filter trong shared index

Với shared index, mọi request tenant-facing cần gắn filter tenantId lấy từ trusted context.

Ví dụ tìm sản phẩm theo tên:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import java.util.List;

public List<ProductDocument> search(
        String tenantId,
        String searchText) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(FieldValue.of(tenantId))
                    ))
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(searchText)
                    ))
            ))
            .build();

        return operations.search(
                    query,
                    ProductDocument.class,
                    IndexCoordinates.of("products"))
            .stream()
            .map(SearchHit::getContent)
            .toList();
}
~~~

Đây là ví dụ dùng ElasticsearchOperations đồng bộ, nên kết quả được chuyển từ SearchHits thành List. Với ứng dụng reactive, dùng ReactiveElasticsearchOperations và trả Flux như phần reactive bên dưới. Điểm quan trọng của query là tenant filter phải nằm trong bool filter của mọi search request.

Ví dụ JSON Query DSL:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-001"
          }
        }
      ],
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ]
    }
  }
}
~~~

Dùng filter context cho tenantId vì đây là điều kiện phân vùng dữ liệu, không phải tín hiệu relevance. Filter có thể được cache tùy điều kiện và cấu hình, đồng thời không làm thay đổi score.

Không nối tenantId vào chuỗi query. Hãy truyền nó như giá trị term có kiểu dữ liệu.

### 6.1. Tenant filter phải được áp dụng ở mọi loại query

Các endpoint sau đều cần tenant boundary:

| Thao tác | Điều kiện cần có |
| --- | --- |
| Search/list | tenantId filter. |
| Count | tenantId filter. |
| Aggregation/facets | tenantId filter ở query scope trước aggregation. |
| Search after/PIT | Mỗi request tiếp theo giữ nguyên tenant scope và PIT phù hợp. |
| Update by query | tenantId filter cùng điều kiện cập nhật. |
| Delete by query | tenantId filter cùng điều kiện xóa. |
| Bulk index/update/delete | Kiểm tra tenant của từng item; không nhận tenantId từ payload không tin cậy. |
| Multi-search | Mỗi sub-request phải có tenant scope. |
| Suggest/script query | Không được bỏ tenant scope hoặc đọc dữ liệu tenant khác. |
| Export/report | Tenant filter phải áp dụng trước khi stream hoặc tổng hợp dữ liệu. |

Một filter được thêm trong controller search không bảo vệ các method khác. Hãy tập trung tenant scoping trong service/repository adapter để tất cả đường truy cập đi qua cùng quy tắc.

### 6.2. Aggregation cũng phải được lọc

Không chạy aggregation trên toàn shared index rồi chỉ lọc bucket ở frontend. Điều đó có thể làm lộ số lượng, tên category, giá trị hoặc xu hướng của tenant khác.

Đặt tenant filter ở query cấp cao nhất:

~~~json
{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-001"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

Mọi metric và bucket con khi đó được tính trên tập document đã lọc.

## 7. Tránh đường truy cập bỏ qua tenant filter

Rủi ro phổ biến của shared index là một method tiện lợi nhưng không tenant-aware.

Ví dụ các lời gọi cần xem xét:

~~~java
repository.findAll();
repository.findById(id);
operations.get(id, ProductDocument.class);
operations.count(Query.findAll(), ProductDocument.class);
~~~

Các method này không tự biết tenant hiện tại. Nếu gọi trực tiếp trong service tenant-facing, chúng có thể trả dữ liệu ngoài tenant.

Một quy tắc thiết kế hữu ích:

- Không inject repository thô vào controller.
- Tạo TenantProductService làm cổng truy cập dữ liệu.
- Các method service luôn nhận TenantId đã xác thực hoặc lấy từ context an toàn.
- Không expose findAll/getById không có tenant scope cho code nghiệp vụ tenant-facing.
- Dùng custom repository fragment cho các query phức tạp cần tenant scope.
- Kiểm tra cả background job, admin endpoint và export path.

### 7.1. Derived query có tenant condition

Có thể tạo method có tenantId trong tên:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByTenantIdAndCategory(
            String tenantId,
            String category);

    Optional<ProductDocument> findByTenantIdAndId(
            String tenantId,
            String id);
}
~~~

Method derived query có tenantId giúp thể hiện phạm vi truy cập ngay trong contract. Tuy nhiên, repository vẫn kế thừa findAll(), findById() và các method không có tenant condition.

Vì vậy, đừng cho service tenant-facing gọi repository trực tiếp. Có thể ẩn repository sau service hoặc custom facade và chỉ công khai các method đã scope. Nếu dùng custom base repository, phải bảo đảm các method inherited như findById, existsById, deleteById và findAll cũng được triển khai theo tenant policy; override thiếu một method vẫn có thể tạo lỗ hổng.

### 7.2. Get-by-ID cần tenant guard

Một search filter không bảo vệ một lời gọi get theo ID nếu get request không có điều kiện tenant. Với shared index, có thể:

- Dùng composite _id chứa tenant ID và chỉ tạo ID sau khi xác thực tenant.
- Dùng query có cả tenantId và ID/business ID.
- Sau khi đọc, kiểm tra tenantId trước khi trả dữ liệu, nhưng tránh để response hoặc timing làm lộ thông tin tồn tại chéo tenant.

Composite ID giúp giảm nguy cơ ID collision nhưng không thay thế authorization. Nếu attacker biết composite ID của tenant khác, endpoint vẫn phải kiểm tra tenant hiện tại.

## 8. Alias và giới hạn của filtered alias

Có thể tạo alias có filter cho từng tenant:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "add": {
        "index": "products",
        "alias": "products-tenant-001",
        "filter": {
          "term": {
            "tenantId": "tenant-001"
          }
        }
      }
    }
  ]
}
~~~

Alias giúp request sử dụng tên thân thiện và có thể gom tenant filter vào một cấu hình tập trung cho các API search phù hợp.

Tuy nhiên, filtered alias không nên được xem là ranh giới bảo mật hoàn chỉnh:

- Filter của alias chủ yếu áp dụng cho các thao tác tìm kiếm/đếm và một số API query-based được hỗ trợ.
- Không giả định filter tự áp dụng cho Get API đọc theo _id.
- Filter alias không tự kiểm tra tenantId khi index document mới qua alias.
- Caller có quyền truy cập concrete index vẫn có thể bỏ qua alias.
- Các API khác nhau có thể có semantics riêng; cần kiểm tra tài liệu endpoint cụ thể.

Nếu dùng alias để phân vùng, hãy kết hợp với index privileges/DLS và không cấp quyền truy cập concrete index rộng hơn nhu cầu. Đối với shared index, alias có thể là một lớp tiện ích định tuyến query, nhưng service vẫn cần bảo vệ get/write và các API không được alias filter bao phủ.

## 9. Document-level security và field-level security

Elasticsearch security có thể giới hạn dữ liệu đọc bằng document-level security (DLS) và giới hạn field trả về bằng field-level security (FLS), tùy license và cấu hình triển khai.

### 9.1. DLS cho shared index

DLS gắn một query filter vào index privilege của role. Ví dụ role chỉ đọc document có tenantId bằng tenant-001:

~~~json
{
  "indices": [
    {
      "names": ["products"],
      "privileges": ["read"],
      "query": {
        "term": {
          "tenantId": "tenant-001"
        }
      }
    }
  ]
}
~~~

Khi principal dùng role này để thực hiện thao tác đọc được hỗ trợ, Elasticsearch áp dụng document query theo role. Nếu ứng dụng gửi query tìm tất cả document, DLS vẫn giới hạn tập document mà role được đọc.

DLS có ích khi muốn enforcement tại Elasticsearch thay vì phụ thuộc mọi đoạn code đều nhớ thêm tenant filter. Tuy nhiên, cần lưu ý:

- DLS gắn với read privileges; không coi nó là cơ chế giới hạn document được ghi hoặc cập nhật.
- Credential dùng chung có thể mang role rộng hơn, làm mất ý nghĩa cách ly.
- Nếu một principal có nhiều role, cách các role kết hợp có thể làm phạm vi đọc rộng hơn dự kiến; cần thiết kế role composition cẩn thận.
- DLS có giới hạn và tương tác riêng với một số API/tính năng; kiểm tra endpoint cụ thể.
- Tác vụ quản trị hoặc cross-tenant cần một identity riêng có quyền được kiểm soát.

Với shared index, DLS bảo vệ đọc ở lớp Elasticsearch, còn service vẫn phải gán tenantId đúng và kiểm tra quyền trên mọi thao tác ghi.

### 9.2. FLS để ẩn field nhạy cảm

FLS giới hạn những field mà role được đọc. Ví dụ có thể cho phép role đọc tất cả field trừ internalCost hoặc margin:

~~~json
{
  "field_security": {
    "grant": ["*"],
    "except": ["internalCost", "supplierNotes"]
  }
}
~~~

FLS hữu ích khi cùng tenant có các nhóm người dùng với quyền khác nhau, hoặc service chỉ được đọc một phần dữ liệu. Nó không thay thế tenant isolation: FLS giới hạn field, DLS giới hạn document.

### 9.3. API key theo tenant

Có thể cấp API key riêng cho tenant hoặc service, gắn role descriptor giới hạn index và/hoặc DLS. Khi làm vậy:

- Tạo key bằng một identity có quyền cấp đúng privilege.
- Giới hạn key vào index cần thiết.
- Với shared index, dùng DLS cho read nếu phù hợp.
- Không cấp cluster privilege không cần thiết.
- Quản lý expiration, rotation và revocation.
- Không lưu key trong source code hoặc log.
- Kiểm tra quyền hiệu lực của key, bao gồm giao của quyền key với quyền identity tạo key theo cơ chế Elasticsearch.

API key chỉ có ý nghĩa nếu role descriptor thực sự giới hạn quyền. Một API key có quyền read toàn bộ shared index vẫn có thể đọc dữ liệu của mọi tenant nếu không có DLS.

## 10. Phân quyền theo index với index-per-tenant

Với index riêng, có thể cấp role chỉ truy cập index của tenant:

~~~json
{
  "indices": [
    {
      "names": ["products-tenant-001"],
      "privileges": ["read", "write"]
    }
  ]
}
~~~

Identity này không cần quyền trên products-tenant-002. Một service có thể dùng API key riêng cho tenant hoặc credential được lấy từ một credential broker có kiểm soát.

Không cấp quyền wildcard như products-* cho service của tenant nếu mục tiêu là cách ly index. Các quyền create/manage index nên thuộc provisioning service hoặc operator riêng.

Nếu một service backend phục vụ nhiều tenant, service có thể chọn credential phù hợp sau khi xác thực tenant. Credential selection phải dựa trên registry tin cậy, không dựa trên header do client tự đặt.

## 11. Routing theo tenant để cải thiện locality

Với shared index, có thể dùng tenantId làm routing value để document của cùng tenant thường được gửi tới cùng shard.

Ví dụ index:

~~~http
PUT /products/_doc/P-100?routing=tenant-001
Content-Type: application/json

{
  "tenantId": "tenant-001",
  "name": "Keyboard"
}
~~~

Mapping có thể yêu cầu routing:

~~~json
{
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

Khi search theo tenant, gửi routing tương ứng để Elasticsearch chỉ tìm trên shard đích:

~~~http
GET /products/_search?routing=tenant-001
Content-Type: application/json

{
  "query": {
    "term": {
      "tenantId": "tenant-001"
    }
  }
}
~~~

Cần phân biệt:

- routing chọn shard sẽ xử lý request.
- tenantId filter chọn document được phép nằm trong kết quả.
- routing không kiểm tra quyền tenant.
- nhiều tenant có thể hash vào cùng một shard.
- tenant có tải rất lớn có thể làm shard tương ứng nóng.

Vì vậy, luôn giữ tenant filter ngay cả khi request có routing. Routing là tối ưu hiệu năng và locality, không phải security boundary.

Nếu mapping đặt _routing.required=true, mọi index request phải truyền routing. Get/update/delete theo ID cũng cần cùng routing. Hãy kiểm tra Spring Data routing resolver hoặc truyền routing qua API tương ứng để không vô tình tạo request thiếu routing.

### 11.1. Routing và tenant lớn

Một tenant có số document hoặc tốc độ ghi vượt trội có thể tập trung tải vào một shard khi dùng tenantId làm routing. Đây là trade-off giữa locality và phân phối tải.

Các lựa chọn:

- Không custom route nếu cluster cần phân phối dữ liệu đều hơn.
- Tách tenant lớn sang index riêng.
- Dùng routing partitioning nếu phù hợp với phiên bản và mô hình truy vấn.
- Chia dữ liệu tenant theo một khóa phụ có kiểm soát, đồng thời bảo đảm truy vấn biết các routing partition cần tìm.

Không dùng routing partition như một cơ chế bảo mật. Filter tenant vẫn bắt buộc.

## 12. Cách triển khai tenant-aware service trong Spring Data

Một service nên nhận tenant identity từ tầng authorization rồi áp dụng nó vào mọi thao tác.

Ví dụ shared-index service:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class TenantProductService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public TenantProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> search(
            TenantId tenantId,
            String text) {

        NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q.bool(b -> b
                        .filter(f -> f.term(t -> t
                                .field("tenantId")
                                .value(FieldValue.of(tenantId.value()))
                        ))
                        .must(m -> m.match(mm -> mm
                                .field("name")
                                .query(text)
                        ))
                ))
                .build();

        return operations.search(
                        query,
                        ProductDocument.class,
                        PRODUCTS)
                .stream()
                .map(SearchHit::getContent)
                .toList();
    }

    public ProductDocument save(
            TenantId tenantId,
            ProductDocument product) {

        product.setTenantId(tenantId.value());
        return operations.save(product, PRODUCTS);
    }
}
~~~

Ví dụ giả định TenantId đã được tạo từ authenticated principal và không thể được caller tự dựng từ request payload. Service gán tenantId khi ghi và bắt buộc thêm filter khi search.

Với shared index, cần bổ sung tenant scope cho get/update/delete. Không tái sử dụng một method get-by-ID không filter trong endpoint tenant-facing.

### 12.1. Cập nhật document có tenant condition

Nếu dùng query-based update, điều kiện cần bao gồm cả document identity và tenant:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-001" } },
        { "term": { "sku": "SKU-100" } }
      ]
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.price = params.price",
    "params": {
      "price": 49.99
    }
  }
}
~~~

Nếu update theo _id, không có nghĩa tenant filter được tự động áp dụng. Có thể đọc document bằng một query có cả tenantId và ID rồi mới cập nhật với concurrency token, hoặc dùng một request query-based có điều kiện tenant. Lựa chọn cụ thể cần cân nhắc race condition, routing và yêu cầu atomicity.

### 12.2. Xóa document

Xóa theo ID mà không kiểm tra tenant có thể xóa nhầm document nếu endpoint nhận ID do caller gửi.

Với shared index, dùng delete-by-query có tenant condition hoặc một bước xác thực quyền trên document trước khi xóa. Ví dụ query scope:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-001" } },
        { "term": { "sku": "SKU-100" } }
      ]
    }
  }
}
~~~

Với index riêng, index resolver đã giới hạn phạm vi index; vẫn phải xác thực tenant trước khi chọn IndexCoordinates.

## 13. Reactive application và tenant context

Trong WebFlux, không dùng ThreadLocal làm nơi duy nhất lưu tenant context. Reactive pipeline có thể chuyển thread giữa các operator; ThreadLocal không tự đi theo subscription.

Các cách an toàn:

- Truyền TenantId như tham số rõ ràng qua service method.
- Nếu cần context xuyên suốt pipeline, đặt tenant identity vào Reactor Context sau authentication.
- Chỉ lấy tenant context đã được xác thực từ security layer.
- Không dùng tenantId trong request body để ghi đè context.
- Đảm bảo background publisher/job mang tenant ID đã được kiểm tra.

Ví dụ service reactive nhận tenant ID tường minh:

~~~java
public Flux<ProductDocument> search(
        TenantId tenantId,
        String text) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(FieldValue.of(tenantId.value()))
                    ))
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(text)
                    ))
            ))
            .build();

    return reactiveOperations.search(
                    query,
                    ProductDocument.class,
                    IndexCoordinates.of("products"))
            .map(SearchHit::getContent);
}
~~~

Ví dụ này dùng ReactiveElasticsearchOperations. Không inject ElasticsearchOperations đồng bộ rồi bọc kết quả trong Mono để giả lập non-blocking.

## 14. Background jobs, events và message queues

Tenant isolation thường bị bỏ sót ở những luồng không đi qua HTTP controller:

- Scheduled job.
- Kafka/RabbitMQ consumer.
- Batch import/export.
- Reindex hoặc data migration.
- Webhook handler.
- Async event listener.
- Admin tooling.

Mỗi job cần biết tenant scope hợp lệ và giữ nó trong suốt quá trình xử lý.

Ví dụ event:

~~~json
{
  "eventId": "evt-100",
  "tenantId": "tenant-001",
  "type": "ProductPriceChanged",
  "productId": "P-100"
}
~~~

Consumer không nên tin tenantId chỉ vì nó có trong message. Message producer phải được xác thực, topic/queue permissions phải phù hợp và consumer cần kiểm tra tenant ownership trước khi thao tác.

Với batch xử lý nhiều tenant, hãy chia batch theo tenant hoặc giữ tenant scope riêng cho từng item. Không dùng một tenant context mutable chung cho nhiều tác vụ chạy song song.

## 15. Migration giữa hai mô hình

Có thể cần chuyển tenant từ shared index sang index riêng khi quy mô tăng hoặc yêu cầu cách ly thay đổi.

Một quy trình migration có kiểm soát:

1. Xác định tenant, document count, mapping và các quan hệ liên quan.
2. Tạo index đích từ template đúng version.
3. Bắt đầu đồng bộ thay đổi mới bằng dual-write hoặc change capture có thứ tự.
4. Copy dữ liệu tenant bằng query filter tenantId.
5. Xác minh count, checksum hoặc business key theo tập dữ liệu.
6. Chuyển tenant resolver sang index mới.
7. Chặn hoặc xử lý write đang chạy để tránh mất cập nhật.
8. Kiểm tra read/write trên index đích.
9. Ngừng ghi tenant vào shared index.
10. Xóa dữ liệu nguồn sau thời gian rollback được phê duyệt.

Không chỉ copy dữ liệu rồi đổi alias mà không giải quyết các write đồng thời. Một document được cập nhật trong lúc reindex có thể bị mất hoặc ghi đè nếu không có cơ chế đồng bộ.

Khi chuyển từ index-per-tenant về shared index, cần bảo đảm ID toàn cục không va chạm, tenantId được điền đầy đủ và mọi service đã chuyển sang tenant-scoped query trước khi mở quyền truy cập shared index.

## 16. Offboarding và xóa dữ liệu tenant

Khi tenant ngừng dịch vụ, quy trình xóa dữ liệu phụ thuộc mô hình:

- Index riêng: xác minh đúng index tenant, snapshot/retention theo chính sách rồi xóa index.
- Shared index: chạy delete-by-query với tenantId chính xác và kiểm tra số document bị xóa.
- Hybrid: xử lý mọi index, alias, snapshot và bản sao liên quan.

Xóa dữ liệu trong Elasticsearch chưa chắc đã xóa mọi bản sao trong snapshot, backup, data lake, log hoặc hệ thống downstream. Quy trình offboarding cần xác định phạm vi dữ liệu và thời gian retention theo chính sách của tổ chức.

Không cho endpoint tenant-facing nhận index name hoặc delete query tùy ý. Tác vụ xóa tenant nên là workflow quản trị có phê duyệt, audit và xác nhận tenant identity.

## 17. Kiểm thử tenant isolation

Kiểm thử phải chứng minh cả truy cập hợp lệ và truy cập chéo tenant bị chặn.

Tạo fixture:

| Tenant | Document ID | SKU | Name |
| --- | --- | --- | --- |
| tenant-A | A:P-100 | P-100 | Keyboard A |
| tenant-B | B:P-100 | P-100 | Keyboard B |

Các kiểm thử tối thiểu:

1. Tenant A search chỉ trả Keyboard A.
2. Tenant B search chỉ trả Keyboard B.
3. Tenant A không lấy được document B bằng business ID.
4. Tenant A không cập nhật được document B.
5. Tenant A không xóa được document B.
6. Count và aggregation của A không bao gồm document B.
7. Bulk request không ghi tenantId của B khi đang chạy dưới A.
8. Request không có tenant context bị từ chối.
9. Request cố truyền tenantId khác trong body không thay đổi tenant scope.
10. Alias, routing và DLS không tạo đường truy cập bypass.
11. Background job kiểm tra tenant của từng message.
12. Admin/cross-tenant workflow dùng credential riêng và có audit.

Với index-per-tenant, kiểm tra credential tenant A không có index privileges trên index tenant B.

Với shared index, kiểm tra cả service filter lẫn DLS role nếu sử dụng DLS. Một test chỉ gọi service search không đủ để xác nhận API get/update/delete hoặc credential trực tiếp cũng an toàn.

### 17.1. Kiểm thử ID collision

Tạo hai document có cùng business ID ở hai tenant:

~~~text
tenant-A + P-100
tenant-B + P-100
~~~

Với shared index, xác nhận hệ thống dùng _id khác nhau hoặc ID nội bộ toàn cục. Với index riêng, xác nhận resolver luôn chọn đúng index trước khi đọc hoặc ghi.

### 17.2. Kiểm thử quyền Elasticsearch

Nếu dùng DLS hoặc index privileges, chạy integration test với credential tenant thực tế:

- Gửi search không có tenant filter và xác nhận DLS vẫn giới hạn kết quả.
- Thử truy cập index của tenant khác và xác nhận bị từ chối.
- Thử get-by-ID và các API không được alias filter bao phủ.
- Kiểm tra role kết hợp không vô tình mở rộng quyền.
- Thử write document có tenantId khác và xác nhận service layer ngăn thao tác đó.

DLS không giới hạn write theo tenant. Test phải xác minh ứng dụng gán tenantId từ principal và không cho phép caller tự đổi tenant field.

## 18. Hiệu năng và noisy neighbor

Multi-tenancy không chỉ là vấn đề authorization. Tenant có tải cao có thể ảnh hưởng latency của tenant khác.

Theo dõi theo tenant:

- Document count và index size.
- Tốc độ ingest/update/delete.
- Search request rate và latency.
- Query timeout và rejected requests.
- Aggregation bucket count.
- Shard skew khi dùng routing.
- Cache usage và refresh pressure.
- Bulk batch size.
- Tỷ lệ lỗi và retry.

Các biện pháp kiểm soát:

- Giới hạn page size và kích thước bulk.
- Rate limit theo tenant ở API gateway/service.
- Giới hạn query complexity và aggregation size.
- Đặt timeout hợp lý.
- Dùng index riêng cho tenant vượt ngưỡng.
- Tách workload ingest và search nếu cần.
- Tránh để tenant tự gửi Query DSL hoặc script tùy ý.
- Cache kết quả có tenant ID trong cache key.

Nếu cache chỉ dùng key là productId hoặc query text, dữ liệu tenant A có thể bị trả cho tenant B dù Elasticsearch filter đúng. Cache key cần bao gồm tenant identity và các tham số authorization liên quan.

## 19. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Tin tenantId từ request body | Caller có thể giả tenant khác. | Lấy từ authenticated principal và kiểm tra membership. |
| Chỉ filter trong controller search | get/update/delete hoặc job có thể bỏ qua. | Tập trung tenant scoping trong service/repository boundary. |
| Dùng alias filter làm security duy nhất | Get-by-ID hoặc write có thể không chịu filter như mong đợi. | Dùng index privilege/DLS và authorization ở service. |
| Dùng routing thay cho tenant filter | Routing chỉ chọn shard, không xác thực document ownership. | Giữ cả routing và tenant filter. |
| Dùng findAll/findById không scope | Có thể truy cập document tenant khác. | Expose tenant-aware facade và hạn chế repository thô. |
| Shared index dùng business ID làm _id | Hai tenant có thể ghi đè nhau. | Dùng ID toàn cục hoặc composite ID. |
| Cho phép đổi tenantId qua update DTO | Document có thể bị chuyển tenant ngoài ý muốn. | Tenant ID bất biến trong luồng cập nhật thông thường. |
| DLS được xem là bảo vệ cả write | DLS áp dụng cho read; write cần kiểm soát riêng. | Gán tenantId và validate quyền ở service hoặc dùng index riêng. |
| API key có quyền read toàn index | Key có thể đọc mọi tenant nếu không có DLS. | Role descriptor giới hạn index/document và kiểm tra effective privileges. |
| Cache không có tenant trong key | Có thể trả dữ liệu chéo tenant. | Đưa tenant ID vào cache key. |
| ThreadLocal trong reactive flow | Tenant context có thể mất khi đổi thread. | Truyền tham số hoặc dùng Reactor Context. |
| Tạo index cho mọi tenant nhỏ mà không theo dõi shard | Cluster có quá nhiều shard/index. | Dùng shared index hoặc hybrid theo ngưỡng. |
| Xóa dữ liệu tenant bằng query thiếu filter | Có thể xóa dữ liệu của nhiều khách hàng. | Workflow offboarding có tenant scope, audit và xác minh count. |

## 20. Quy trình thiết kế tenant isolation

Khi xây dựng một module Spring Data Elasticsearch multi-tenant:

1. Xác định yêu cầu cô lập, compliance, số tenant và quy mô dữ liệu.
2. Chọn index-per-tenant, shared index hoặc hybrid.
3. Xác định tenant identity từ authentication và membership.
4. Thiết kế TenantContext/TenantId bất biến và được xác thực.
5. Nếu dùng shared index, mapping tenantId thành keyword và gán ở server.
6. Thiết kế _id để tránh collision giữa tenant.
7. Tập trung query vào tenant-aware service hoặc custom repository fragment.
8. Kiểm tra search, count, aggregation, get, update, delete, bulk và background job.
9. Nếu dùng index riêng, resolve IndexCoordinates từ registry tin cậy.
10. Nếu dùng DLS/FLS hoặc API key, thiết kế role và kiểm tra effective privileges.
11. Chỉ dùng alias và routing như công cụ định tuyến/tối ưu, không coi chúng là authorization.
12. Lập kế hoạch provisioning, mapping migration, rollover và offboarding.
13. Kiểm thử negative case giữa các tenant.
14. Đo noisy neighbor và đặt quota/rate limit.
15. Audit các đường truy cập trực tiếp tới Elasticsearch.

## 21. Tài liệu tham khảo

- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories.html)
- [Elasticsearch — Index privileges and security](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Elasticsearch — Document-level security](https://www.elastic.co/guide/en/elasticsearch/reference/current/document-level-security.html)
- [Elasticsearch — Field-level security](https://www.elastic.co/guide/en/elasticsearch/reference/current/field-level-security.html)
- [Elasticsearch — Index aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html)
- [Elasticsearch — Routing](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-routing-field.html)
- [Elasticsearch — Index templates](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-templates.html)
- [Elasticsearch — Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html)

Index riêng cho tenant giúp giới hạn quyền ở cấp index và hỗ trợ vòng đời dữ liệu độc lập, nhưng làm tăng chi phí index/shard và provisioning. Shared index tiết kiệm tài nguyên hơn nhưng đòi hỏi tenant filter ở mọi thao tác và một lớp authorization đáng tin cậy; DLS có thể bổ sung enforcement cho đọc, còn write vẫn cần kiểm soát riêng. Spring Data Elasticsearch cung cấp IndexCoordinates, Operations và repository fragment để triển khai cả hai mô hình. Tenant identity phải đến từ principal đã xác thực, còn alias và routing chỉ hỗ trợ định tuyến chứ không thay thế security boundary.

