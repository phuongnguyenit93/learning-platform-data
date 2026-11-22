# Khi Repository tự tạo index và khi phải quản lý tường minh

Spring Data Elasticsearch có thể tự tạo index khi repository được khởi tạo, nhưng khả năng này chỉ phù hợp với một số cách triển khai. Với hệ thống có mapping phức tạp, nhiều môi trường, yêu cầu phân quyền chặt hoặc cần nâng cấp dữ liệu an toàn, việc tạo và thay đổi index nên được quản lý thành một bước triển khai riêng.

Để lựa chọn đúng, cần phân biệt ba cơ chế thường bị nhầm lẫn: **Spring Data Repository tạo index dựa trên entity metadata**, **Elasticsearch cluster tự tạo index khi nhận document ghi vào index chưa tồn tại**, và **ứng dụng hoặc pipeline triển khai chủ động gọi API tạo index**. Chúng có thời điểm, quyền hạn và kết quả khác nhau.

## 1. Index được tạo tự động theo cơ chế nào?

### 1.1. Repository tạo index dựa trên @Document

Spring Data Elasticsearch cho phép đánh dấu entity bằng annotation @Document:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;
}
~~~

Thuộc tính createIndex của @Document mặc định là true. Khi repository tương ứng được khởi tạo, Spring Data có thể kiểm tra index đích. Nếu index chưa tồn tại và entity cho phép tạo index, repository sẽ yêu cầu Elasticsearch tạo index cùng settings và mapping được suy ra từ metadata entity.

Có thể khai báo rõ ý định:

~~~java
@Document(
    indexName = "products",
    createIndex = true
)
public class ProductDocument {
    // ...
}
~~~

Cơ chế này thuận tiện cho ứng dụng nhỏ, môi trường học tập, thử nghiệm hoặc index có cấu trúc đơn giản được mô tả đầy đủ bằng annotation.

Repository chỉ có thể tạo index khi ứng dụng kết nối được tới cluster và danh tính đang dùng có quyền thực hiện thao tác cần thiết. Nếu cluster không truy cập được, credential sai hoặc tài khoản không có quyền tạo index, quá trình khởi tạo repository có thể thất bại.

### 1.2. Tạo index không đồng nghĩa cập nhật mapping hiện có

Giả sử index products đã tồn tại. Khi repository khởi tạo, Spring Data thấy index đã có thì không mặc định xóa index và tạo lại chỉ vì annotation trong Java đã thay đổi.

Ví dụ, code ban đầu khai báo:

~~~java
@Field(type = FieldType.Text)
private String category;
~~~

Sau đó đổi thành:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

Index cũ có thể vẫn giữ field category kiểu text. Metadata trong code mới không tự biến mapping cũ thành keyword.

@Document còn có thuộc tính alwaysWriteMapping, mặc định là false ở các phiên bản Spring Data Elasticsearch hỗ trợ thuộc tính này. Nếu bật, Spring Data có thể ghi mapping từ entity khi repository được khởi tạo kể cả khi index đã tồn tại. Tuy nhiên, việc ghi mapping không vượt qua các giới hạn của Elasticsearch: không thể tùy ý đổi kiểu field đã được tạo. Hãy kiểm tra đúng phiên bản Spring Data đang dùng trước khi dựa vào tùy chọn này.

Vì vậy, không nên xem createIndex = true như một cơ chế migration schema. Nó giải quyết việc tạo index còn thiếu, không thay thế kế hoạch nâng cấp index đang chứa dữ liệu.

### 1.3. Elasticsearch cluster cũng có thể tự tạo index

Elasticsearch có cơ chế cluster-level auto index creation, được điều khiển bởi thiết lập action.auto_create_index ở phía Elasticsearch server.

Khi một request ghi document vào index chưa tồn tại, cluster có thể tự tạo index nếu chính sách này cho phép. Cơ chế đó hoạt động ở phía server và không phụ thuộc vào việc ứng dụng có khai báo createIndex = true hay không.

Đây là khác biệt quan trọng:

| Cơ chế | Ai khởi tạo? | Thời điểm | Nguồn settings/mapping |
|---|---|---|---|
| Repository auto-create | Spring Data Elasticsearch | Khi repository được khởi tạo và index chưa tồn tại | Entity metadata, annotation và cấu hình liên quan |
| Cluster auto-create | Elasticsearch server | Khi nhận request cần ghi vào index chưa tồn tại | Dynamic mapping và cấu hình mặc định/chính sách của cluster |
| Explicit provisioning | Ứng dụng, migration job hoặc pipeline triển khai | Theo bước triển khai đã định | Mapping/settings được quản lý tường minh |

Ví dụ, ứng dụng khai báo createIndex = false, nhưng cluster vẫn cho phép auto-create. Nếu ứng dụng ghi document vào index chưa tồn tại, Elasticsearch có thể tự tạo index theo dynamic mapping. Vì vậy, createIndex = false không tự động vô hiệu hóa action.auto_create_index.

Nếu muốn kiểm soát việc tạo index, cần phối hợp cả cấu hình Spring Data, quyền của tài khoản và chính sách auto-create trên cluster.

## 2. Khi nào Repository auto-create phù hợp?

### 2.1. Dự án nhỏ hoặc môi trường phát triển

Repository auto-create thường phù hợp khi:

- Chỉ có một ứng dụng hoặc một module quản lý index.
- Index có cấu trúc đơn giản.
- Mapping có thể biểu diễn đầy đủ bằng annotation.
- Không có yêu cầu migration dữ liệu phức tạp.
- Môi trường phát triển có thể tạo index mới khi ứng dụng khởi động.
- Tài khoản chạy ứng dụng được phép tạo index.

Ví dụ:

~~~java
@Document(indexName = "products", createIndex = true)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;
}
~~~

Khi repository được khởi tạo và index chưa tồn tại, Spring Data có thể tạo index với mapping tương ứng. Nhóm phát triển không cần viết thêm một bước tạo index thủ công cho môi trường thử nghiệm.

### 2.2. Entity metadata đã mô tả đủ cấu trúc

Repository auto-create phù hợp hơn khi settings và mapping có thể mô tả ổn định trong source code.

Spring Data Elasticsearch hỗ trợ các annotation như:

- @Document để xác định index và hành vi tạo index.
- @Setting để cung cấp index settings.
- @Mapping để cung cấp mapping JSON.
- @Field để mô tả kiểu field và các tùy chọn liên quan.
- @MultiField và @InnerField để mô tả nhiều cách lập chỉ mục một property.

Ví dụ:

~~~java
@Document(indexName = "articles", createIndex = true)
@Setting(settingPath = "/elasticsearch/settings/articles-settings.json")
@Mapping(mappingPath = "/elasticsearch/mappings/articles-mapping.json")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Keyword)
    private String category;
}
~~~

Các đường dẫn trên là resource trên classpath của ứng dụng. Settings có thể chứa analyzer, tokenizer và token filter; mapping có thể mô tả field, nested object và các thuộc tính mapping khác.

Nếu index cần analyzer tùy chỉnh, settings phải có mặt ngay khi tạo index. Không nên trông chờ việc thêm analyzer vào annotation sau đó sẽ tự cập nhật index đã tồn tại.

## 3. Khi nào nên tắt Repository auto-create?

### 3.1. Production cần kiểm soát vòng đời index

Trong production, việc tạo index thường là một phần của quy trình triển khai dữ liệu. Có thể cần:

- Review mapping trước khi áp dụng.
- Kiểm soát shard, replica, refresh interval và analyzer.
- Tạo index theo phiên bản như products-v1, products-v2.
- Reindex dữ liệu trước khi chuyển ứng dụng sang schema mới.
- Chuyển alias để đổi index đích có kiểm soát.
- Theo dõi trạng thái migration và khả năng rollback.
- Phân tách quyền triển khai index với quyền đọc/ghi document của ứng dụng.

Trong các trường hợp này, nên tắt việc repository tự tạo index:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {
    // ...
}
~~~

Ứng dụng vẫn có thể dùng repository để đọc/ghi document trong index đã được provision. Index phải được tạo trước bằng migration job, pipeline triển khai hoặc một thành phần quản trị được cấp quyền phù hợp.

### 3.2. Ứng dụng runtime không nên giữ quyền quản trị index

Một ứng dụng chỉ cần tìm kiếm và cập nhật document thường không cần quyền tạo hoặc xóa index.

Nếu repository auto-create được bật, quá trình khởi tạo có thể yêu cầu quyền tạo index và ghi mapping. Điều này có thể buộc runtime credential phải có quyền rộng hơn mức cần thiết.

Tách hai vai trò giúp giảm quyền:

| Vai trò | Trách nhiệm | Quyền điển hình |
|---|---|---|
| Index provisioning/migration | Tạo index, áp dụng settings và mapping, quản lý alias | Quyền quản lý index cần thiết |
| Ứng dụng runtime | Tìm kiếm, đọc, index hoặc cập nhật document | Quyền đọc/ghi trên các index được cấp |

Tên và phạm vi privilege cụ thể phụ thuộc phiên bản Elasticsearch và thao tác cần chạy. Hãy cấp quyền tối thiểu theo API thực tế, không cấp quyền cluster administrator cho ứng dụng chỉ để repository khởi động được.

### 3.3. Nhiều ứng dụng cùng dùng một index

Nếu nhiều service cùng ghi vào một index, không nên để mỗi service tự quyết định mapping và thời điểm tạo index.

Ví dụ, service catalog và service search cùng dùng index products. Nếu hai ứng dụng khai báo metadata khác nhau, một service có thể mong price là double, service khác lại mong price là keyword. Việc một ứng dụng khởi động trước và tạo index có thể khiến ứng dụng còn lại gặp lỗi mapping hoặc truy vấn.

Hãy chỉ định một nguồn quản lý schema có thẩm quyền. Các service còn lại dùng cùng hợp đồng document và không tự tạo hoặc sửa mapping.

### 3.4. Mapping phức tạp hoặc cần migration

Nên quản lý tường minh nếu index sử dụng:

- Analyzer tùy chỉnh hoặc plugin phân tích ngôn ngữ.
- Nested mapping, multi-field và dynamic templates phức tạp.
- Alias và nhiều index theo phiên bản.
- ILM/data stream hoặc quy trình rollover.
- Mapping được chia sẻ giữa nhiều ứng dụng.
- Reindex, backfill hoặc migration dữ liệu.
- Yêu cầu thay đổi field type, analyzer hoặc cấu trúc document.

Các thay đổi kiểu field hoặc analyzer thường không thể áp dụng trực tiếp vào index đã có dữ liệu theo cách tùy ý. Một quy trình tạo index mới và reindex sẽ dễ kiểm soát hơn.

## 4. Tạo index tường minh bằng IndexOperations

### 4.1. Dùng mapping metadata của entity

Spring Data Elasticsearch cung cấp IndexOperations thông qua ElasticsearchOperations. Khi muốn chủ động tạo index từ metadata của entity, có thể viết:

~~~java
@Service
public class ProductIndexProvisioner {

    private final ElasticsearchOperations operations;

    public ProductIndexProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndexIfMissing() {
        IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

indexOps(ProductDocument.class) lấy index operations gắn với entity metadata. exists() kiểm tra index đích. createWithMapping() tạo index cùng settings/mapping được suy ra từ entity và các annotation liên quan.

Cách này tường minh hơn việc phụ thuộc vào thời điểm repository khởi tạo, nhưng vẫn dùng metadata Java làm nguồn cấu trúc. Nó phù hợp khi muốn có một bước provision rõ ràng trong ứng dụng hoặc một job riêng.

Không nên gọi createWithMapping() vô điều kiện ở mỗi lần request. Hãy đặt thao tác này trong bước triển khai hoặc initialization có kiểm soát.

### 4.2. Tạo index và mapping thành các bước riêng

Một số tình huống cần tách tạo index và ghi mapping:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping();
}
~~~

create() tạo index với settings tương ứng; putMapping() gửi mapping của entity. Cách tách này giúp biểu diễn rõ hai thao tác và có thể hữu ích khi cần xử lý settings/mapping riêng.

Cần hiểu trạng thái lỗi giữa hai bước: nếu tạo index thành công nhưng ghi mapping thất bại, index có thể đã tồn tại nhưng chưa có mapping mong muốn. Lần chạy tiếp theo không nên chỉ kiểm tra exists() rồi kết luận đã provision xong. Cần có cơ chế kiểm tra mapping thực tế và xử lý trạng thái dở dang.

### 4.3. Dùng IndexCoordinates khi tên index không gắn cố định với entity

Khi tên index được quyết định lúc chạy, có thể dùng IndexCoordinates:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

Cách này hữu ích với index phiên bản, index theo tenant hoặc alias được chọn động. Tuy nhiên, nếu tên index không gắn trực tiếp với entity class, ứng dụng phải tự bảo đảm settings và mapping được cung cấp đúng cho index đó.

Repository thường lấy index name từ metadata @Document. Với luồng dùng tên index động, ElasticsearchOperations và IndexCoordinates thường phù hợp hơn.

## 5. Quản lý settings và mapping tường minh

### 5.1. Settings và mapping có vai trò khác nhau

**Index settings** điều khiển cách index được tổ chức và vận hành, ví dụ:

- Số primary shards và replica.
- Refresh interval.
- Analyzer, tokenizer và token filters.
- Một số thiết lập index-level khác.

**Mapping** mô tả cách từng field được diễn giải, ví dụ:

- text, keyword, date, long, boolean.
- Object và nested.
- Multi-field.
- Dynamic mapping behavior.
- Analyzer được gắn vào field.

Settings và mapping có thể được quản lý bằng resource JSON trong source code, migration scripts hoặc công cụ triển khai. Nên review chúng như một phần của schema ứng dụng.

### 5.2. Ví dụ settings và mapping resource

Một file settings minh họa:

~~~json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  }
}
~~~

Một file mapping minh họa:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "catalog_text",
      "fields": {
        "raw": {
          "type": "keyword"
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    }
  }
}
~~~

Đây là cấu trúc ví dụ. Số shard/replica, analyzer và field type phải được chọn dựa trên quy mô, workload và phiên bản Elasticsearch thực tế. Không sao chép thông số minh họa thành cấu hình production mà chưa đánh giá.

### 5.3. Không để annotation và JSON drift khỏi nhau

Nếu cùng một field được mô tả trong Java annotation và mapping JSON, cần giữ hai nguồn đồng nhất. Ví dụ, entity khai báo category là Keyword nhưng mapping JSON lại khai báo text. Khi đó converter vẫn chuyển đổi giá trị theo Java metadata, trong khi cluster lập chỉ mục theo mapping JSON.

Có thể chọn một chiến lược rõ ràng:

- Dùng annotation làm nguồn chính cho mapping đơn giản.
- Dùng mapping JSON làm nguồn chính cho mapping phức tạp, còn annotation chỉ giữ metadata cần cho converter.
- Sinh hoặc kiểm tra mapping từ một schema được quản lý tập trung nếu nhiều ứng dụng chia sẻ index.

Sau khi provision, kiểm tra mapping thực tế trên cluster để phát hiện sai khác.

## 6. Cluster auto_create_index và dynamic mapping

### 6.1. Cấu hình phía Elasticsearch server

Elasticsearch có thiết lập action.auto_create_index để cho phép hoặc từ chối tạo index tự động khi request nhắm đến index chưa tồn tại. Chính sách này được cấu hình ở phía server, không phải trong application.yml của Spring Boot.

Tùy môi trường, quản trị viên có thể:

- Cho phép auto-create toàn cục.
- Từ chối auto-create.
- Chỉ cho phép hoặc từ chối theo pattern index.

Cú pháp pattern và chính sách chi tiết cần theo tài liệu đúng phiên bản Elasticsearch. Trong production, nên xác định rõ những index nào được phép tự tạo, đặc biệt khi tên index có thể đến từ input của ứng dụng.

### 6.2. Dynamic mapping có thể tạo schema ngoài dự kiến

Khi cluster tự tạo index do nhận document, Elasticsearch có thể suy luận mapping từ các field trong document đầu tiên. Đây là dynamic mapping.

Ví dụ document đầu tiên:

~~~json
{
  "name": "Keyboard",
  "price": 49.9
}
~~~

Elasticsearch có thể suy luận name là kiểu text/keyword phù hợp theo dynamic templates mặc định và price là kiểu số. Nhưng nếu dữ liệu sau gửi price dưới dạng chuỗi không tương thích, request có thể thất bại.

Dynamic mapping thuận tiện cho thử nghiệm hoặc dữ liệu linh hoạt, nhưng có thể gây:

- Field được suy luận sai kiểu.
- Mapping explosion khi document chứa nhiều field động.
- Khác biệt schema giữa các môi trường.
- Khó kiểm soát analyzer và nested structure.
- Lỗi khi dữ liệu không đồng nhất.

Với index nghiệp vụ ổn định, nên tạo mapping trước khi nhận dữ liệu thật.

### 6.3. Phối hợp các cơ chế

Một số cấu hình minh họa:

| @Document.createIndex | action.auto_create_index | Kết quả khi index chưa tồn tại |
|---|---|---|
| true | Cho phép | Repository có thể tạo index từ entity metadata khi khởi tạo |
| true | Từ chối | Repository auto-create bị cluster từ chối |
| false | Cho phép | Repository không chủ động tạo; thao tác ghi sau đó vẫn có thể kích hoạt cluster auto-create |
| false | Từ chối | Cần provision index trước; thao tác ghi vào index thiếu sẽ thất bại |

Kết quả còn phụ thuộc quyền của tài khoản, thời điểm repository khởi tạo và cấu hình cụ thể. Bảng này mô tả nguyên tắc phối hợp, không thay thế kiểm tra trên môi trường thực tế.

## 7. Quản lý index theo phiên bản và alias

### 7.1. Không sửa trực tiếp schema cũ khi thay đổi lớn

Khi mapping hiện tại không còn phù hợp, ví dụ cần đổi field type hoặc analyzer, một quy trình phổ biến là tạo index phiên bản mới:

~~~text
products-v1  -> index đang phục vụ
products-v2  -> index mới với mapping/settings đã cập nhật
products     -> alias trỏ đến index đang hoạt động
~~~

Alias cho phép ứng dụng dùng một tên logic ổn định trong khi index vật lý thay đổi theo phiên bản.

### 7.2. Quy trình migration cơ bản

Một quy trình blue-green index có thể gồm:

1. Tạo products-v2 với settings và mapping đã review.
2. Reindex dữ liệu từ products-v1 sang products-v2.
3. Kiểm tra số lượng document, dữ liệu mẫu và các truy vấn quan trọng.
4. Dừng hoặc đồng bộ các thay đổi phát sinh trong thời gian reindex nếu cần bảo đảm dữ liệu nhất quán.
5. Chuyển alias products từ index cũ sang index mới bằng một thao tác alias phù hợp.
6. Theo dõi ứng dụng sau khi chuyển.
7. Chỉ xóa index cũ sau khi hết thời hạn rollback và đã xác nhận dữ liệu an toàn.

Nếu ứng dụng đang ghi trong lúc reindex, cần thiết kế cách đồng bộ write mới để tránh mất cập nhật. Tùy workload, có thể tạm dừng ghi, dual-write, dùng change capture hoặc chạy một vòng đồng bộ cuối trước khi chuyển alias.

### 7.3. Repository và alias

Entity có thể khai báo index name là alias logic:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // ...
}
~~~

Trong cluster, alias products có thể trỏ đến products-v1 hoặc products-v2. Ứng dụng không cần đổi repository khi chuyển alias nếu hợp đồng mapping tương thích.

Khi dùng alias làm write target, hãy bảo đảm alias có đúng write index nếu nó trỏ đến nhiều index. Việc chuyển alias cần được thực hiện theo API alias và chính sách triển khai phù hợp.

## 8. Tránh lỗi khi nhiều instance cùng khởi động

### 8.1. Race condition khi tạo index

Trong môi trường có nhiều instance ứng dụng, hai instance có thể cùng khởi động và cùng kiểm tra index chưa tồn tại:

~~~mermaid
sequenceDiagram
    participant A as App instance A
    participant B as App instance B
    participant ES as Elasticsearch
    A->>ES: exists(products) -> false
    B->>ES: exists(products) -> false
    A->>ES: create(products)
    B->>ES: create(products)
    ES-->>A: created
    ES-->>B: resource_already_exists_exception
~~~

Một instance tạo thành công, instance còn lại có thể nhận lỗi vì index đã được tạo giữa hai lần kiểm tra. Do đó, mẫu if-not-exists-then-create không phải khóa phân tán và không loại bỏ race condition.

Có thể xử lý bằng cách:

- Chỉ chạy provisioning một lần trong pipeline hoặc migration job.
- Dùng một cơ chế lock/leader election nếu phải provision trong môi trường nhiều instance.
- Khi xử lý lỗi tạo trùng, kiểm tra lại index và mapping thực tế; chỉ coi là thành công nếu schema đạt yêu cầu.
- Không nuốt mọi exception chỉ vì nghĩ rằng index có thể đã được instance khác tạo.

### 8.2. Thứ tự triển khai

Với quản lý tường minh, thứ tự triển khai nên là:

~~~mermaid
flowchart TD
    A[Review schema và mapping] --> B[Provision index]
    B --> C[Verify settings và mapping]
    C --> D[Deploy ứng dụng]
    D --> E[Smoke test đọc/ghi]
    E --> F[Theo dõi và xác nhận]
~~~

Nếu ứng dụng được deploy trước khi index mới sẵn sàng, request có thể lỗi index_not_found_exception. Pipeline nên bảo đảm bước provision và kiểm tra hoàn tất trước khi đưa phiên bản ứng dụng phụ thuộc schema mới vào hoạt động.

## 9. Kiểm tra index trước và sau provisioning

### 9.1. Kiểm tra index tồn tại

Có thể kiểm tra qua IndexOperations:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

boolean exists = indexOperations.exists();
~~~

Hoặc gọi API Elasticsearch:

~~~http
HEAD /products
~~~

Response thành công cho biết index tồn tại và endpoint có thể trả lời request đó. Nó chưa chứng minh mapping đúng hoặc ứng dụng có đủ quyền thao tác trên document.

### 9.2. Kiểm tra mapping và settings

Sau khi tạo index, hãy đọc mapping và settings thực tế:

~~~http
GET /products/_mapping
GET /products/_settings
~~~

Đối chiếu:

- Field name có đúng không?
- Field type có đúng không?
- Analyzer và search analyzer có được cấu hình không?
- Object/nested có đúng yêu cầu truy vấn không?
- Shard/replica và refresh interval có đúng môi trường không?
- Dynamic mapping có đang được bật theo chủ đích không?

Có thể dùng API của IndexOperations để lấy mapping/settings thay vì gọi HTTP trực tiếp. Việc kiểm tra nên được thực hiện bằng tài khoản có quyền đọc thông tin index tương ứng.

### 9.3. Kiểm tra dữ liệu và truy vấn

Sau khi xác nhận mapping, hãy thử:

- Index một document đại diện.
- Đọc lại document theo ID.
- Thực hiện full-text query.
- Thực hiện exact match trên field keyword.
- Kiểm tra nested query nếu có nested mapping.
- Kiểm tra sort, aggregation và date range nếu ứng dụng sử dụng.

Index được tạo thành công chưa có nghĩa dữ liệu và query đã đúng. Smoke test nên phản ánh các thao tác quan trọng của ứng dụng.

## 10. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Repository khởi tạo thất bại vì không tạo được index | Cluster không sẵn sàng, sai credential hoặc thiếu quyền tạo index | Kiểm tra kết nối, quyền và cân nhắc tắt auto-create nếu dùng provisioning riêng |
| index_not_found_exception | Index chưa được provision và cluster không auto-create | Tạo index trước khi chạy thao tác repository |
| resource_already_exists_exception | Nhiều instance cùng tạo index hoặc index vừa được tạo bởi tiến trình khác | Kiểm tra lại index/mapping; dùng một provisioning job duy nhất |
| Index tồn tại nhưng field type sai | Mapping cũ không được thay đổi theo annotation mới | Tạo index mới và reindex nếu cần |
| Field xuất hiện với kiểu không mong muốn | Cluster auto-create và dynamic mapping suy luận từ document đầu tiên | Provision mapping tường minh và kiểm soát auto-create |
| Analyzer không tồn tại khi tạo index | Settings thiếu analyzer hoặc resource không được nạp | Kiểm tra @Setting, file resource và thứ tự tạo index |
| createIndex = false nhưng index vẫn xuất hiện | Cluster-level action.auto_create_index cho phép tạo khi ghi | Kiểm tra cấu hình server và quyền của ứng dụng |
| Tạo index được nhưng ghi mapping thất bại | Mapping không hợp lệ hoặc thiếu quyền | Kiểm tra response, schema và quyền quản lý mapping |
| Ứng dụng khởi động chậm hoặc fail khi cluster tạm thời không sẵn sàng | Provisioning diễn ra trong quá trình repository initialization | Tách provisioning thành bước triển khai và kiểm soát readiness |

Khi gặp lỗi, hãy xác định cơ chế nào đã tạo hoặc dự định tạo index. Kiểm tra log của ứng dụng, response từ Elasticsearch và mapping thực tế thay vì chỉ nhìn @Document.

## 11. Chọn chiến lược theo môi trường

| Môi trường/tình huống | Chiến lược thường phù hợp |
|---|---|
| Local learning hoặc demo | Repository auto-create với createIndex = true |
| Integration test dùng index tạm | Tạo index trong test setup, xóa sau test nếu an toàn |
| Staging có mapping gần production | Provision bằng migration/pipeline giống production |
| Production, một ứng dụng sở hữu index đơn giản | Có thể dùng auto-create nếu quyền và lifecycle được kiểm soát |
| Production, nhiều service dùng chung index | Một nguồn provisioning/schema có thẩm quyền |
| Mapping phức tạp, analyzer tùy chỉnh | Settings/mapping được quản lý tường minh |
| Thay đổi field type hoặc analyzer | Tạo index phiên bản mới, reindex và chuyển alias |
| Runtime credential không có quyền quản trị | Tắt repository auto-create và provision trước khi deploy |

Không có một lựa chọn đúng cho mọi hệ thống. Quyết định nên dựa trên ai sở hữu index, ai được phép thay đổi schema, mức độ phức tạp của mapping, cách triển khai và yêu cầu an toàn dữ liệu.

## 12. Quy trình lựa chọn thực tế

Trước khi bật auto-create, hãy trả lời:

1. Index này chỉ do một ứng dụng sử dụng hay được nhiều service chia sẻ?
2. Mapping có thể biểu diễn đầy đủ và ổn định bằng entity metadata không?
3. Có analyzer, nested, alias, rollover hoặc migration cần quản lý riêng không?
4. Ứng dụng runtime có được phép tạo index không?
5. Cluster có cho phép auto-create khi nhận request ghi không?
6. Nếu nhiều instance khởi động cùng lúc, ai chịu trách nhiệm tạo index?
7. Khi mapping thay đổi, dữ liệu cũ sẽ được xử lý như thế nào?
8. Có thể xác minh settings/mapping trước khi deploy ứng dụng không?

Nếu câu trả lời cho thấy index có lifecycle độc lập với vòng đời ứng dụng, hãy quản lý việc provision bằng một bước riêng. Nếu index đơn giản, chỉ có một chủ sở hữu và môi trường cho phép, repository auto-create là một lựa chọn thuận tiện.

Điểm cốt lõi là phân biệt rõ **tạo index còn thiếu**, **cập nhật mapping**, và **migration schema/dữ liệu**. Repository auto-create giải quyết phần đầu trong phạm vi metadata của entity. Cluster auto-create là chính sách phía server. Quản lý tường minh cho phép kiểm soát toàn bộ vòng đời index, quyền truy cập và quá trình chuyển đổi dữ liệu khi hệ thống phát triển.
