# Phân biệt quản lý vòng đời ở cluster với chức năng Repository

Trong một ứng dụng Spring Data Elasticsearch, hai nhóm chức năng thường bị nhầm lẫn là **quản lý vòng đời dữ liệu ở Elasticsearch cluster** và **các thao tác CRUD của Spring Data Repository**. Cả hai đều có thể ảnh hưởng đến dữ liệu, nhưng chúng hoạt động ở những tầng khác nhau và giải quyết những bài toán khác nhau.

Quản lý vòng đời ở cluster điều khiển index hoặc data stream trong suốt thời gian tồn tại: khi nào rollover sang index mới, khi nào chuyển dữ liệu sang tầng lưu trữ khác, khi nào xóa index cũ và khi nào tạo snapshot. Repository là abstraction ở tầng ứng dụng để lưu, đọc, tìm kiếm hoặc xóa document theo model Java.

```text
                Spring Boot application
                ------------------------
                ProductRepository
                ElasticsearchOperations
                         |
                         | document CRUD / query
                         v
                 Elasticsearch cluster
                 ----------------------
                 Index / Data stream
                 Shards / Replicas
                 Aliases
                 ILM / Data Stream Lifecycle
                 SLM / Snapshot repository
```

Repository gửi thao tác document đến cluster. Các policy vòng đời được cấu hình ở cluster và được Elasticsearch thực thi theo trạng thái, tuổi hoặc điều kiện của index. Repository không tự trở thành bộ lập lịch retention, rollover hoặc snapshot chỉ vì nó được khai báo trong ứng dụng.

## 1. Hai tầng quản lý khác nhau

| Khía cạnh | Quản lý vòng đời ở cluster | Spring Data Repository |
|---|---|---|
| Đối tượng chính | Index, backing index của data stream, shard và snapshot. | Document được ánh xạ thành Java entity. |
| Nơi cấu hình | Elasticsearch cluster settings, lifecycle policy, index template và snapshot repository. | Interface repository, entity mapping, query method và cấu hình Spring. |
| Công việc | Rollover, chuyển data tier, retention, xóa index theo policy, snapshot định kỳ. | `save`, `findById`, tìm kiếm, cập nhật và xóa document. |
| Cách kích hoạt | Elasticsearch chạy policy theo lịch và trạng thái index; một số thao tác có thể được gọi qua API. | Ứng dụng gọi method repository trong luồng nghiệp vụ hoặc job của ứng dụng. |
| Phạm vi tác động | Có thể áp dụng cho nhiều index theo policy hoặc template. | Phạm vi dữ liệu của entity/repository và index hoặc alias mà entity sử dụng. |
| Phụ thuộc ứng dụng | Policy đã cài trong cluster có thể tiếp tục chạy khi ứng dụng Spring dừng. | Cần ứng dụng hoặc thành phần gọi repository thực hiện thao tác. |

Ví dụ: `ProductRepository.save(product)` ghi một document sản phẩm. Một ILM policy có thể quản lý index `application-logs-*`, rollover index theo dung lượng rồi xóa các index cũ sau thời hạn retention. Hai việc này không thay thế nhau.

## 2. Repository quản lý document, không quản lý toàn bộ vòng đời index

Spring Data Elasticsearch cung cấp repository abstraction để thao tác với document. Một repository thường được khai báo như sau:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

Entity chỉ định index logic mà nó sử dụng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // constructors, getters, setters
}
```

Nếu `products` là alias, repository có thể gửi request qua alias đó; Elasticsearch sẽ định tuyến đến index vật lý mà alias đang trỏ tới. Repository không cần biết index hiện tại là `products-v1` hay `products-v2`.

Các thao tác thường gặp:

```java
productRepository.save(product);
productRepository.findById("P-100");
productRepository.findAll();
productRepository.deleteById("P-100");
```

Các method này làm việc với document. Chúng không định nghĩa retention policy, không tự rollover index theo dung lượng, không chuyển shard từ hot sang warm, và không tạo snapshot định kỳ.

### `deleteById`, `deleteAll` và xóa index không giống nhau

Cần phân biệt rõ ba mức thao tác:

- `deleteById(id)` xóa document có id tương ứng theo mapping/repository.
- `deleteAll()` xóa các document trong phạm vi mà method repository triển khai; nó không nên được hiểu là lệnh xóa index vật lý.
- Xóa index là thao tác quản trị index, ví dụ gọi `IndexOperations.delete()` hoặc Elasticsearch Indices API `DELETE /<index>`.

Ví dụ thao tác index qua Spring Data:

```java
IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);

if (indexOperations.exists()) {
    indexOperations.delete();
}
```

Đây là thao tác quản trị có thể xóa toàn bộ dữ liệu của index tương ứng. Không đặt nó trong luồng CRUD thông thường nếu mục đích chỉ là xóa một số sản phẩm. Cần xem xét alias và index thực tế mà entity trỏ đến trước khi gọi.

Chi tiết triển khai của các method repository và API index có thể thay đổi theo phiên bản Spring Data Elasticsearch. Khi cần biết một method tác động đến document, index hay alias nào, hãy kiểm tra contract của phiên bản thư viện và xác minh request được gửi đến Elasticsearch.

## 3. Quản lý vòng đời ở cluster là gì?

Elasticsearch có các cơ chế quản lý vòng đời để vận hành index trong thời gian dài. Các policy có thể được cấu hình một lần ở cluster và được áp dụng cho những index phù hợp.

Những nhu cầu thường gặp:

- Tạo index mới khi index hiện tại đạt giới hạn về tuổi, dung lượng hoặc số document.
- Chuyển index cũ sang data tier phù hợp với tần suất truy cập.
- Giữ dữ liệu nóng để truy vấn thường xuyên và đưa dữ liệu ít truy cập sang tầng lưu trữ tiết kiệm hơn.
- Xóa index sau thời hạn lưu giữ.
- Tạo snapshot định kỳ để có thể khôi phục dữ liệu khi cần.

Các cơ chế chính cần phân biệt:

| Cơ chế | Mục đích |
|---|---|
| Index Lifecycle Management (ILM) | Quản lý vòng đời index theo các phase và action, ví dụ rollover, migrate, shrink, force merge và delete. |
| Data Stream Lifecycle | Quản lý vòng đời backing index của data stream theo chính sách được hỗ trợ bởi phiên bản Elasticsearch. |
| Snapshot Lifecycle Management (SLM) | Lập lịch tạo snapshot và quản lý retention của snapshot trong snapshot repository. |
| Index template | Áp dụng settings, mapping, alias và lifecycle policy cho index mới phù hợp với pattern. |

ILM và Data Stream Lifecycle tập trung vào vòng đời index/data stream. SLM quản lý bản sao lưu snapshot. Một policy xóa index sau 90 ngày không có nghĩa snapshot của index cũng tự được giữ hoặc xóa theo cùng quy tắc; hai vòng đời cần được thiết kế riêng.

## 4. Index Lifecycle Management (ILM)

ILM cho phép định nghĩa các phase trong vòng đời của index. Các phase thường gặp gồm:

- **Hot:** dữ liệu mới, có tần suất ghi và đọc cao.
- **Warm:** dữ liệu ít được ghi hơn, vẫn có thể cần truy cập thường xuyên.
- **Cold:** dữ liệu ít truy cập, ưu tiên tiết kiệm tài nguyên.
- **Frozen:** dữ liệu rất ít truy cập, thường dùng cơ chế lưu trữ phù hợp cho truy vấn thưa thớt.
- **Delete:** xóa index khi hết thời hạn lưu giữ.

Các phase và action khả dụng phụ thuộc phiên bản Elasticsearch, cấu hình node role/data tier và license/tính năng của môi trường. Không phải cluster nào cũng có cùng topology hoặc hỗ trợ mọi action.

### Tạo ILM policy

Ví dụ policy cho index log: rollover khi primary shard đạt 50 GB hoặc index đạt 30 ngày; xóa index sau thời hạn retention tính từ mốc rollover theo lifecycle policy.

```json
PUT /_ilm/policy/app-logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "50gb",
            "max_age": "30d"
          }
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

Policy là cấu hình được lưu ở cluster. Sau khi index được gắn policy, Elasticsearch theo dõi điều kiện và thực hiện action tương ứng. Ứng dụng Spring không cần gọi `deleteAll()` mỗi ngày để xóa index đã hết hạn.

### Gắn policy vào index và rollover alias

Một index ban đầu có thể được tạo với lifecycle policy và write alias:

```json
PUT /app-logs-000001
{
  "settings": {
    "index.lifecycle.name": "app-logs-policy",
    "index.lifecycle.rollover_alias": "app-logs"
  },
  "aliases": {
    "app-logs": {
      "is_write_index": true
    }
  }
}
```

Ứng dụng ghi qua alias `app-logs`. Khi điều kiện rollover đạt, ILM tạo index kế tiếp và chuyển write alias theo cấu hình. Ứng dụng tiếp tục dùng tên alias ổn định.

Đối với index được tạo tự động trong tương lai, nên cấu hình index template để settings lifecycle và alias được áp dụng nhất quán. Nếu thiếu template hoặc cấu hình bootstrap phù hợp, index mới có thể không được gắn policy như mong đợi.

### Theo dõi ILM

Xem policy:

```http
GET /_ilm/policy/app-logs-policy
```

Xem trạng thái lifecycle của một index:

```http
GET /app-logs-000001/_ilm/explain
```

API explain giúp xác định index đang ở phase nào, action nào đang chạy hoặc vì sao một bước bị chờ/lỗi. Không nên chỉ dựa vào tên index hoặc thời gian tạo để kết luận policy đã thực thi.

Khi cần xử lý lỗi, trước tiên đọc thông tin explain và nguyên nhân trong cluster. Elasticsearch có API retry cho một số bước ILM bị lỗi sau khi nguyên nhân đã được xử lý; không nên lặp retry khi điều kiện lỗi vẫn còn.

## 5. Data Stream Lifecycle

Data stream là cách tổ chức dữ liệu dạng append-only, thường phù hợp với log, metric hoặc event theo thời gian. Một data stream quản lý nhiều backing index; ứng dụng ghi vào tên data stream thay vì tự chọn index vật lý.

```text
Ứng dụng ghi event
       |
       v
  Data stream: app-events
       |
       +--> .ds-app-events-...-000001
       +--> .ds-app-events-...-000002
       +--> .ds-app-events-...-000003
```

Data Stream Lifecycle có thể quản lý retention của backing index theo chính sách được hỗ trợ. Điều này phù hợp với dữ liệu append-only mà phần lớn document có timestamp và được ghi liên tục.

Data stream không giống repository. Repository chỉ gửi document vào tên index/data stream được cấu hình; lifecycle policy ở cluster chịu trách nhiệm rollover hoặc retention. Khi chọn ILM hay Data Stream Lifecycle, cần kiểm tra khả năng của phiên bản Elasticsearch và loại dữ liệu đang lưu, tránh áp dụng đồng thời hai cơ chế quản lý cho cùng một luồng index theo cách xung đột.

## 6. Snapshot Lifecycle Management (SLM)

Xóa index theo retention không phải backup. Nếu một index bị xóa nhầm hoặc dữ liệu bị ghi sai, ILM không khôi phục lại dữ liệu đã mất. SLM giúp lập lịch tạo snapshot trong snapshot repository và quản lý thời gian lưu snapshot.

Ví dụ policy snapshot hằng ngày:

```json
PUT /_slm/policy/daily-app-logs
{
  "schedule": "0 30 1 * * ?",
  "name": "<app-logs-{now/d}>-snapshot",
  "repository": "my_backup_repository",
  "config": {
    "indices": ["app-logs-*"],
    "ignore_unavailable": true,
    "include_global_state": false
  },
  "retention": {
    "expire_after": "30d",
    "min_count": 5,
    "max_count": 50
  }
}
```

Snapshot repository phải được đăng ký và cấu hình trước, với storage phù hợp như shared filesystem hoặc object storage được hỗ trợ. Cần kiểm thử restore, không chỉ kiểm tra snapshot job có chạy thành công. Snapshot không phải bản sao tức thời của mọi thay đổi sau thời điểm snapshot; RPO/RTO phụ thuộc lịch snapshot, thời gian phục hồi và quy trình vận hành.

## 7. Vì sao Repository không thay thế ILM?

Giả sử ứng dụng có `LogRepository` và cần giữ log 90 ngày. Có thể nghĩ đến việc chạy job hằng ngày:

```java
logRepository.deleteByTimestampBefore(cutoff);
```

Đây là cách xóa document theo điều kiện ở tầng ứng dụng. Nó khác với ILM:

- Repository job phải được ứng dụng lập lịch và thực thi. Nếu job không chạy, dữ liệu không được xóa.
- Job có thể tạo truy vấn xóa trên lượng lớn document, ảnh hưởng tài nguyên cluster và tải tìm kiếm.
- Job cần xử lý phân trang/batch, retry, lỗi một phần và quan sát tiến trình.
- ILM quản lý index theo lifecycle state ở cluster, không cần ứng dụng liệt kê từng document để quyết định xóa index cũ.

Với log hoặc event được phân vùng theo thời gian, rollover và xóa index cũ thường hiệu quả hơn xóa từng document. Tuy nhiên, ILM xóa toàn bộ index khi hết hạn. Nếu mỗi document có thời hạn lưu khác nhau và không thể nhóm theo index/time bucket, có thể cần job ứng dụng, Delete By Query hoặc mô hình lưu trữ khác.

Elasticsearch không cung cấp TTL tự động cho từng document theo kiểu cũ. Việc khai báo một field `expiresAt` trong entity không khiến document tự biến mất. Ứng dụng phải truy vấn/xóa theo field đó hoặc tổ chức dữ liệu theo index/data stream có lifecycle phù hợp.

## 8. Chọn ILM, Data Stream Lifecycle hay job Repository?

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Log/event append-only, lưu theo ngày/tuần và xóa theo tuổi index | Data stream với lifecycle phù hợp hoặc ILM cho index theo thời gian. |
| Index cần rollover theo kích thước, chuyển data tier và xóa theo retention | ILM. |
| Cần backup định kỳ và retention của bản backup | SLM và snapshot repository. |
| Xóa một sản phẩm theo yêu cầu người dùng | Repository `deleteById` hoặc thao tác document tương ứng. |
| Xóa một nhóm document theo điều kiện nghiệp vụ | Repository query/Delete By Query hoặc service batch có kiểm soát. |
| Mỗi document có hạn dùng khác nhau, không thể gom thành index theo thời gian | Job ứng dụng hoặc quy trình xóa document phù hợp; không dùng ILM như TTL document. |
| Thay mapping/analyzer và chuyển sang index mới | Tạo index version mới, reindex, xác minh rồi chuyển alias. |

Một hệ thống có thể sử dụng đồng thời các cơ chế: Repository phục vụ CRUD nghiệp vụ, ILM quản lý index log, Data Stream Lifecycle quản lý event, và SLM tạo snapshot. Cần phân định rõ index nào thuộc policy nào và ai chịu trách nhiệm triển khai cấu hình.

## 9. Vai trò của `IndexOperations` trong Spring Data

Spring Data Elasticsearch có `ElasticsearchOperations` và `IndexOperations` cho các tác vụ ở mức index như kiểm tra tồn tại, tạo/xóa index, đọc mapping/settings và thao tác alias theo API mà phiên bản thư viện hỗ trợ.

Ví dụ:

```java
@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean exists() {
        return operations.indexOps(ProductDocument.class).exists();
    }
}
```

`IndexOperations` giúp ứng dụng thực hiện một số thao tác quản trị index, nhưng không phải bộ thực thi ILM. Việc tạo policy, gắn policy, kiểm tra trạng thái lifecycle và quản lý snapshot cần dùng các cluster APIs tương ứng hoặc công cụ triển khai hạ tầng.

Nếu ứng dụng cần gọi ILM API từ Java, có thể sử dụng Elasticsearch Java API Client được cấu hình trong Spring Boot. Cũng có thể triển khai policy bên ngoài ứng dụng bằng REST API, deployment scripts hoặc hạ tầng dưới dạng mã. Việc chọn cách nào tùy thuộc quy trình vận hành và quyền của service account.

### Tách quyền ứng dụng và quyền quản trị

Một ứng dụng phục vụ request người dùng thường chỉ cần quyền đọc/ghi trên alias hoặc index nghiệp vụ. Không nhất thiết phải cấp quyền tạo/xóa index, sửa ILM policy hoặc xóa snapshot cho mọi instance ứng dụng.

Nên tách:

- **Runtime application identity:** quyền đọc/ghi document cần thiết.
- **Index provisioning identity:** quyền tạo index, mapping, template và alias trong quá trình triển khai.
- **Lifecycle administration identity:** quyền quản lý ILM, Data Stream Lifecycle và SLM policy.
- **Snapshot/restore identity:** quyền cần thiết để vận hành snapshot repository và khôi phục dữ liệu.

Phân tách quyền giúp giảm khả năng một lỗi trong endpoint CRUD vô tình xóa index hoặc thay đổi retention của toàn cluster.

## 10. Vòng đời của Spring bean cũng khác vòng đời dữ liệu

Spring có khái niệm bean lifecycle: bean được khởi tạo, dependency được inject, callback khởi tạo được gọi và bean được hủy khi ApplicationContext đóng. Đây là vòng đời đối tượng trong JVM.

Elasticsearch index lifecycle là vòng đời tài nguyên dữ liệu trong cluster. Hai khái niệm này độc lập:

- Spring bean `ProductRepository` được tạo khi ứng dụng khởi động.
- Index `products-v1` có thể đã tồn tại từ trước khi ứng dụng chạy.
- Ứng dụng có thể dừng nhưng ILM vẫn tiếp tục xử lý index trong cluster.
- Đóng ApplicationContext không đồng nghĩa xóa repository data hoặc index.
- Xóa index không đồng nghĩa Spring bean repository bị hủy.

Vì vậy, không nên dùng `@PostConstruct` hoặc `@PreDestroy` để thực hiện rollover, retention hoặc xóa index như một cơ chế vòng đời mặc định. Những callback đó gắn với vòng đời tiến trình ứng dụng và có thể chạy nhiều lần khi nhiều replica ứng dụng khởi động/dừng.

## 11. Thiết kế kiến trúc Spring Data và lifecycle policy

Một kiến trúc rõ ràng có thể chia trách nhiệm như sau:

```text
                 Deployment / Platform
                         |
             Create templates and policies
                         |
                         v
                Elasticsearch cluster
                ├── Alias / Index templates
                ├── ILM / Data Stream Lifecycle
                └── SLM / Snapshot repository
                         ^
                         |
                 Spring Boot application
                 ├── Repository: document CRUD
                 ├── Operations: mapping/index APIs
                 └── Service: business rules
```

Ví dụ với log:

1. Deployment tạo lifecycle policy và index template cho `app-logs-*`.
2. Cluster tạo index đầu tiên cùng write alias hoặc data stream theo thiết kế.
3. Spring Boot ghi event qua alias/data stream.
4. ILM hoặc Data Stream Lifecycle rollover và xóa index cũ theo policy.
5. SLM tạo snapshot định kỳ trong repository backup.
6. Monitoring theo dõi trạng thái policy, shard, dung lượng và kết quả snapshot.

Repository không cần biết mỗi index vật lý được tạo vào ngày nào. Nó chỉ cần sử dụng tên alias/data stream ổn định và mapping tương thích.

## 12. Theo dõi và vận hành

Một policy được tạo thành công chưa có nghĩa dữ liệu đang được quản lý đúng. Cần giám sát trạng thái thực tế.

Các API thường dùng:

```http
GET /_ilm/status
GET /_ilm/policy/app-logs-policy
GET /app-logs-000001/_ilm/explain
GET /_data_stream/app-events
GET /_slm/policy/daily-app-logs
GET /_slm/stats
GET /_snapshot/my_backup_repository/_all
```

Ý nghĩa:

- `/_ilm/status` cho biết ILM đang chạy hay bị dừng.
- `/_ilm/policy/...` đọc định nghĩa policy.
- `/_ilm/explain` giải thích trạng thái lifecycle của index.
- `/_data_stream/...` xem data stream và backing index.
- `/_slm/policy/...` đọc cấu hình snapshot policy.
- `/_slm/stats` xem thống kê hoạt động SLM.
- `/_snapshot/.../_all` liệt kê snapshot trong repository.

Ngoài các API này, nên theo dõi số lượng index, kích thước primary shard, số shard unassigned, dung lượng disk, thời gian rollover, lỗi lifecycle và kết quả restore định kỳ. Một snapshot chỉ thực sự hữu ích khi quy trình restore đã được kiểm thử.

## 13. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Dùng `repository.deleteAll()` để thay ILM retention | Ứng dụng phải tự chạy job và xóa từng document; không quản lý shard/index lifecycle. | Dùng ILM hoặc Data Stream Lifecycle nếu retention theo index/time bucket. |
| Nghĩ `expiresAt` tự xóa document | Field chỉ là dữ liệu, không phải TTL tự động. | Tạo job xóa document hoặc partition index theo thời gian. |
| Dùng ILM để thay snapshot backup | Xóa index không tạo bản backup có thể restore. | Cấu hình SLM và kiểm thử restore riêng. |
| Cho mọi ứng dụng quyền xóa index và sửa policy | Tăng phạm vi ảnh hưởng khi có lỗi hoặc credential bị lộ. | Tách quyền runtime và quyền quản trị. |
| Gắn policy vào index thủ công nhưng quên index mới | Index rollover/tạo mới có thể không nhận lifecycle policy. | Dùng index template/data stream template và kiểm tra index mới. |
| Tạo index trong startup của mọi application replica | Nhiều instance cùng thực hiện thao tác quản trị, có thể phát sinh race hoặc cấu hình ngoài ý muốn. | Quản lý index qua migration/provisioning; chỉ bật auto-create khi đã thiết kế rõ. |
| Xóa index cũ ngay sau khi alias chuyển | Mất đường rollback và có thể mất dữ liệu chưa được xác minh. | Giữ index cũ theo thời gian rollback và chính sách backup. |
| Chỉ kiểm tra repository CRUD | Không phát hiện ILM/SLM bị dừng hoặc retention không chạy. | Giám sát cluster lifecycle APIs và snapshot restore. |

## 14. Checklist lựa chọn trách nhiệm

Trước khi triển khai, hãy trả lời các câu hỏi sau:

1. Dữ liệu được lưu theo document hay theo index/data stream có thời gian?
2. Retention áp dụng cho toàn index hay từng document riêng lẻ?
3. Có cần rollover theo tuổi, kích thước hoặc số document không?
4. Có cần chuyển dữ liệu giữa các data tier không?
5. Dữ liệu cần backup bao lâu một lần và snapshot được giữ trong bao lâu?
6. Repository chỉ cần quyền CRUD nào? Ai được phép tạo/xóa index và thay đổi policy?
7. Index mới được tạo qua template, migration hay auto-configuration?
8. Làm thế nào để phát hiện policy lỗi, snapshot thất bại hoặc index chưa được gắn policy?
9. Quy trình restore và rollback đã được thử nghiệm chưa?

## 15. Những điểm cần nhớ

- Repository là abstraction Spring Data để thao tác document; nó không phải cơ chế quản lý vòng đời index ở cluster.
- `save`, `findById` và `deleteById` thao tác document; `deleteAll` không nên bị hiểu nhầm là xóa index vật lý.
- `IndexOperations` cung cấp một số thao tác quản trị index, nhưng không thay thế ILM hoặc SLM.
- ILM quản lý rollover, phase và retention của index; Data Stream Lifecycle quản lý vòng đời backing index của data stream theo tính năng phiên bản.
- SLM quản lý snapshot định kỳ và retention của backup; cần kiểm thử restore.
- ILM xóa index theo policy, không tự xóa từng document dựa trên field `expiresAt`.
- Spring bean lifecycle là vòng đời object trong JVM, khác với vòng đời index trong Elasticsearch cluster.
- Nên tách quyền runtime CRUD khỏi quyền quản trị index, lifecycle policy và snapshot.
- Alias/data stream cung cấp tên truy cập ổn định để ứng dụng không phụ thuộc vào tên index vật lý.

Phân chia đúng trách nhiệm giúp Spring Data Repository tập trung vào nghiệp vụ document, trong khi Elasticsearch cluster đảm nhiệm việc vận hành index và dữ liệu dài hạn. Khi thiết kế hệ thống, hãy xác định rõ đơn vị retention, cơ chế backup, quyền quản trị và cách giám sát để tránh dùng CRUD job thay cho lifecycle policy hoặc nhầm lẫn xóa document với xóa index.
