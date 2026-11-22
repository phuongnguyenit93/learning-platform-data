# Index template, component template và phạm vi API được hỗ trợ

Khi một ứng dụng Spring Data Elasticsearch tạo nhiều index, việc lặp lại settings và mappings cho từng index dễ dẫn đến cấu hình không nhất quán. Elasticsearch cung cấp **index template** để áp dụng một cấu hình chung cho những index mới có tên khớp với pattern. Với composable index templates, cấu hình có thể được chia thành các **component template** nhỏ, có thể tái sử dụng và kết hợp theo thứ tự.

Spring Data Elasticsearch hỗ trợ làm việc với index, mapping, settings và alias thông qua các abstraction như `IndexOperations`. Tuy nhiên, quản lý composable index template và component template là một nhóm API cấp cluster của Elasticsearch. Cần phân biệt rõ phần nào thuộc API Spring Data, phần nào thuộc Elasticsearch Java API Client và phần nào là REST API gốc của Elasticsearch.

Bài học này giải thích cấu trúc index template, component template, cách chọn template theo pattern và priority, cách mô phỏng kết quả trước khi tạo index, cách dùng template với data stream và phạm vi API có thể sử dụng từ ứng dụng Spring Boot.

## 1. Vì sao cần index template?

Giả sử một hệ thống ghi log tạo index theo ngày:

```text
app-logs-2026.11.12
app-logs-2026.11.13
app-logs-2026.11.14
```

Mỗi index cần có mapping giống nhau cho các field `@timestamp`, `level`, `service` và `message`. Nếu ứng dụng phải gửi cùng settings và mappings mỗi lần tạo index, cấu hình có thể bị sao chép ở nhiều nơi. Một index mới có thể vô tình thiếu mapping, dùng sai số shard hoặc có kiểu field khác các index trước.

Index template giải quyết vấn đề này bằng cách định nghĩa một bộ settings, mappings và aliases áp dụng cho những index được tạo sau đó có tên khớp với `index_patterns`.

Ví dụ khái niệm:

```text
Index template: app-logs-template
index_patterns: ["app-logs-*"]
        |
        +----> app-logs-2026.11.12
        +----> app-logs-2026.11.13
        +----> app-logs-2026.11.14
```

Khi một index mới được tạo, Elasticsearch tìm template phù hợp, hợp nhất cấu hình template với cấu hình tạo index và tạo index theo kết quả cuối cùng. Template giúp chuẩn hóa cấu hình cho một nhóm index mà không cần lặp lại toàn bộ mapping trong từng lệnh `PUT index`.

## 2. Composable index template và component template

Elasticsearch hiện đại cung cấp composable index templates. Cấu trúc này tách template thành hai lớp:

- **Component template** chứa một phần settings, mappings hoặc aliases có thể tái sử dụng.
- **Composable index template** xác định index pattern, priority và cách kết hợp các component template để tạo cấu hình hoàn chỉnh cho index mới.

Một component template không tự áp dụng cho index chỉ vì nó tồn tại. Nó chỉ được dùng khi được tham chiếu trong `composed_of` của một composable index template.

```text
Component template: common-settings ----+
                                         |
Component template: event-mappings ------+--> Composable index template
                                         |        index_patterns: events-*
Component template: common-aliases ------+        priority: 300
                                                  |
                                                  v
                                         Index mới: events-2026.11
```

Việc tách cấu hình giúp dùng chung settings giữa nhiều nhóm index, dùng chung mapping chuẩn giữa các ứng dụng và thay đổi từng phần mà không phải sao chép toàn bộ template.

### 2.1. Component template chứa gì?

Component template được tạo bằng Cluster API:

```http
PUT _component_template/common-event-settings
{
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    }
  },
  "version": 1,
  "_meta": {
    "description": "Settings chung cho event indices"
  }
}
```

Ví dụ component template chỉ chứa mapping:

```http
PUT _component_template/common-event-mappings
{
  "template": {
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "service": {
          "type": "keyword"
        },
        "message": {
          "type": "match_only_text"
        },
        "level": {
          "type": "keyword"
        }
      }
    }
  },
  "version": 1,
  "_meta": {
    "description": "Mapping chung cho event documents"
  }
}
```

Một component template có thể chứa `settings`, `mappings` và `aliases` bên trong đối tượng `template`. Các trường `version` và `_meta` giúp quản lý phiên bản và metadata mô tả; chúng không thay thế settings hay mapping.

Component template không có `index_patterns` và không tự chọn index nào sẽ nhận cấu hình. Việc chọn index thuộc composable index template.

### 2.2. Composable index template kết hợp component templates

Tạo index template tham chiếu các component vừa khai báo:

```http
PUT _index_template/app-events-template
{
  "index_patterns": ["app-events-*"],
  "priority": 300,
  "composed_of": [
    "common-event-settings",
    "common-event-mappings"
  ],
  "template": {
    "settings": {
      "number_of_replicas": 0
    },
    "aliases": {
      "app-events-read": {}
    }
  },
  "version": 1,
  "_meta": {
    "owner": "catalog-platform",
    "purpose": "Template cho event index của ứng dụng"
  }
}
```

Trong ví dụ:

- `index_patterns` chọn các index có tên bắt đầu bằng `app-events-`.
- `priority` xác định mức ưu tiên khi nhiều composable index template cùng khớp.
- `composed_of` liệt kê component template được ghép vào.
- `template` chứa phần cấu hình riêng của index template, có thể bổ sung hoặc ghi đè cấu hình từ component templates.
- `version` và `_meta` lưu thông tin quản trị.

Khi tạo `app-events-2026.11`, Elasticsearch sử dụng template phù hợp và tạo index với cấu hình tổng hợp. Trong ví dụ, component settings đặt `number_of_replicas` là `1`, còn phần `template.settings` của index template đặt thành `0`; giá trị ở phần cấu hình index template được áp dụng sau các component và ghi đè giá trị trùng khóa.

## 3. Thứ tự hợp nhất cấu hình

Khi Elasticsearch áp dụng composable index template, thứ tự cấu hình có ý nghĩa:

1. Các component template trong `composed_of` được áp dụng theo thứ tự khai báo.
2. Phần `template` của composable index template được áp dụng sau cùng.
3. Cấu hình được gửi trực tiếp trong request tạo index có thể ghi đè giá trị tương ứng từ template.

Nếu hai component cùng khai báo một setting hoặc cùng định nghĩa một phần mapping, component được áp dụng sau có thể ghi đè phần trùng lặp theo quy tắc hợp nhất của Elasticsearch. Phần `template` của composable index template có ưu tiên cao hơn các component được ghép.

Ví dụ:

```text
common-settings
  number_of_replicas = 1
          |
          v
environment-settings
  number_of_replicas = 0
          |
          v
index template's template
  number_of_replicas = 2
          |
          v
Create index request
  number_of_replicas = 3
          |
          v
Final index setting = 3
```

Không nên để nhiều component cùng định nghĩa một field mapping theo những kiểu dữ liệu khác nhau. Một field không thể vừa là `keyword` vừa là `date` trong cùng một mapping. Thiết kế component theo trách nhiệm rõ ràng giúp giảm xung đột và dễ xác định nguồn cấu hình.

## 4. `index_patterns` và `priority`

`index_patterns` là danh sách pattern dùng để xác định tên index được template áp dụng. Pattern thường dùng wildcard `*`.

Ví dụ:

| Pattern | Tên index khớp ví dụ |
|---|---|
| `app-logs-*` | `app-logs-2026.11.13` |
| `orders-*` | `orders-v1`, `orders-2026.11` |
| `metrics-prod-*` | `metrics-prod-host-01` |

Nên đặt pattern đủ cụ thể để tránh một template vô tình áp dụng cho index thuộc ứng dụng khác.

Nếu nhiều composable index templates cùng khớp tên index mới, Elasticsearch chọn template có `priority` cao nhất. Các composable index templates có priority thấp hơn không tự động được ghép thêm vào template thắng cuộc. Muốn tái sử dụng cấu hình từ nhiều nguồn, hãy đưa chúng thành component templates và tham chiếu trong `composed_of`.

Ví dụ có hai index template:

```http
PUT _index_template/all-app-template
{
  "index_patterns": ["app-*"],
  "priority": 100,
  "template": {
    "settings": {
      "number_of_replicas": 1
    }
  }
}
```

```http
PUT _index_template/app-logs-template
{
  "index_patterns": ["app-logs-*"],
  "priority": 300,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    }
  }
}
```

Khi tạo `app-logs-2026.11.13`, cả hai pattern đều khớp nhưng `app-logs-template` có priority cao hơn nên được chọn. Settings từ `all-app-template` không tự động được cộng vào. Nếu cần settings chung, hãy chuyển phần chung vào component template rồi tham chiếu từ `app-logs-template`.

Priority là giá trị số nguyên; nếu không khai báo, Elasticsearch dùng giá trị mặc định là `0`. Hãy chọn các khoảng priority có quy ước trong tổ chức để tránh template mới vô tình chiếm quyền áp dụng của template khác. Một số template hệ thống hoặc template do dịch vụ quản lý có thể sử dụng priority riêng; cần xem tài liệu của phiên bản và sản phẩm đang dùng trước khi đặt priority gần các phạm vi dành riêng.

## 5. Template áp dụng lúc nào?

Index template được áp dụng khi một index mới được tạo và tên của index khớp pattern. Index có thể được tạo tường minh bằng Create Index API hoặc được tự động tạo khi ghi document nếu cấu hình auto-create cho phép.

Template không tự cập nhật index đã tồn tại. Nếu thay đổi mapping hoặc settings trong template, những index cũ không tự nhận cấu hình mới. Muốn thay đổi index hiện có, cần dùng API cập nhật mapping/settings nếu Elasticsearch cho phép, hoặc tạo index mới và reindex dữ liệu theo quy trình migration.

Ví dụ, sau khi sửa component template `common-event-mappings`, index `app-events-2026.10` đã tồn tại không tự đổi mapping. Index mới như `app-events-2026.11` có thể nhận mapping mới khi được tạo.

Điều này đặc biệt quan trọng với mapping. Elasticsearch thường không cho phép đổi kiểu của một field đã được lập chỉ mục từ `text` sang `keyword` hoặc từ `keyword` sang `date` ngay trên cùng index. Hãy quản lý version index và alias để triển khai thay đổi không gián đoạn.

## 6. Kiểm tra template và cấu hình đã lưu

Lấy một component template:

```http
GET _component_template/common-event-settings
```

Lấy composable index template:

```http
GET _index_template/app-events-template
```

Liệt kê tất cả component templates:

```http
GET _component_template
```

Liệt kê tất cả composable index templates:

```http
GET _index_template
```

Các API này giúp xác nhận template đã được tạo, tên tham chiếu trong `composed_of` chính xác và pattern/priority đúng với thiết kế.

Nếu template tham chiếu một component template không tồn tại, thao tác tạo hoặc cập nhật index template có thể thất bại, trừ khi request được cấu hình rõ để bỏ qua component bị thiếu. Trong quy trình chuẩn, nên tạo component templates trước, sau đó tạo composable index template tham chiếu chúng.

## 7. Mô phỏng template trước khi tạo index

Elasticsearch cung cấp Simulate Index Template API để xem cấu hình tổng hợp mà một template sẽ tạo ra. Đây là bước hữu ích trước khi áp dụng template lên index thật.

### 7.1. Mô phỏng một định nghĩa template

Có thể gửi một định nghĩa template chưa lưu để xem kết quả:

```http
POST _index_template/_simulate
{
  "index_patterns": ["app-events-*"],
  "priority": 300,
  "composed_of": [
    "common-event-settings",
    "common-event-mappings"
  ],
  "template": {
    "settings": {
      "number_of_replicas": 0
    }
  }
}
```

Response cho biết settings, mappings và aliases sau khi các component được hợp nhất. Dùng kết quả để phát hiện cấu hình thiếu hoặc bị ghi đè ngoài dự kiến.

### 7.2. Mô phỏng template đã lưu theo tên

Có thể mô phỏng composable index template đã lưu bằng tên của nó:

```http
POST _index_template/_simulate/app-events-template
```

Response cho thấy cấu hình tổng hợp của template đó. Khi điều tra xung đột, chú ý thông tin về các template khác có thể chồng lấn pattern nếu response của phiên bản hỗ trợ trả thông tin này.

### 7.3. Mô phỏng cấu hình cho một tên index cụ thể

Để biết template nào sẽ được chọn cho một index cụ thể, dùng Simulate Index API:

```http
POST _index_template/_simulate_index/app-events-2026.11.13
```

API này hữu ích khi có nhiều template cùng pattern. Nó giúp kiểm tra template được chọn và cấu hình cuối cùng trước khi gửi lệnh tạo index.

Mô phỏng không tạo index và không thay thế bước kiểm tra cluster thực tế. Nó cũng không chứng minh rằng mọi request ghi document sau này đều thành công; quyền truy cập, ingest pipeline, tài nguyên cluster và dữ liệu đầu vào vẫn có thể gây lỗi riêng.

## 8. Tạo index và xác minh template được áp dụng

Sau khi template đã được lưu và mô phỏng đúng, tạo index mới:

```http
PUT app-events-2026.11.13
```

Kiểm tra settings:

```http
GET app-events-2026.11.13/_settings
```

Kiểm tra mapping:

```http
GET app-events-2026.11.13/_mapping
```

Kiểm tra alias:

```http
GET app-events-2026.11.13/_alias
```

Kết quả thực tế là nguồn xác nhận cuối cùng cho index đã được tạo. Nếu settings hoặc mapping không như mong đợi, hãy xem lại pattern, priority, thứ tự component và phần `template` ghi đè. Cũng cần kiểm tra xem index có được tạo từ trước hay không; template chỉ áp dụng khi tạo mới.

## 9. Sử dụng index template với data stream

Data stream là abstraction của Elasticsearch dành cho dữ liệu append-only theo thời gian, chẳng hạn log, metric hoặc event. Data stream quản lý các backing indices phía dưới và cho phép ghi dữ liệu vào write index hiện tại.

Để tạo data stream, cần có composable index template khớp tên stream và có thuộc tính `data_stream`. Mapping phải có field timestamp phù hợp, thông thường là `@timestamp` kiểu `date`.

Ví dụ:

```http
PUT _index_template/app-logs-stream-template
{
  "index_patterns": ["app-logs-*"],
  "priority": 500,
  "data_stream": {},
  "template": {
    "settings": {
      "number_of_replicas": 1
    },
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "service": {
          "type": "keyword"
        },
        "message": {
          "type": "match_only_text"
        }
      }
    }
  }
}
```

Tạo data stream:

```http
PUT _data_stream/app-logs-api
```

Ghi document:

```http
POST app-logs-api/_doc
{
  "@timestamp": "2026-11-13T09:30:00Z",
  "service": "catalog-api",
  "message": "Application started"
}
```

Data stream cần timestamp field theo quy tắc của Elasticsearch. Các backing indices được tạo theo lifecycle của data stream; ứng dụng ghi qua tên data stream thay vì tự quản lý tên từng backing index.

### 9.1. Template thông thường và template cho data stream

| Đặc điểm | Index thông thường | Data stream |
|---|---|---|
| Cách ghi | Ghi vào tên index cụ thể hoặc alias | Ghi vào tên data stream |
| Cấu trúc | Một index độc lập | Một stream gồm nhiều backing indices |
| Timestamp | Không bắt buộc với mọi index | Cần timestamp field theo yêu cầu data stream |
| Rollover | Có thể quản lý bằng alias/ILM | Là một phần của lifecycle data stream |
| Template | Composable index template thông thường | Composable index template có `data_stream` |

Không nên khai báo `data_stream` cho template nếu pattern đó được dùng để tạo index thông thường. Hãy tách pattern và template cho hai mục đích để tránh nhầm lẫn khi tạo tài nguyên.

## 10. Alias trong index template

Index template có thể khai báo aliases để index mới tự động tham gia một alias chung.

Ví dụ:

```http
PUT _index_template/orders-template
{
  "index_patterns": ["orders-v*"],
  "priority": 300,
  "template": {
    "mappings": {
      "properties": {
        "status": {
          "type": "keyword"
        },
        "createdAt": {
          "type": "date"
        }
      }
    },
    "aliases": {
      "orders-read": {}
    }
  }
}
```

Khi tạo index `orders-v1`, alias `orders-read` được gắn tự động. Khi tạo `orders-v2`, alias đó cũng được gắn vào index mới nếu template vẫn khớp.

Template giúp alias được khai báo nhất quán, nhưng không tự thực hiện toàn bộ quy trình chuyển đổi read/write alias khi migrate. Trong migration, cần dùng Aliases API để chuyển alias tới index mới và loại bỏ alias khỏi index cũ theo một thao tác phù hợp.

## 11. Quản lý template khi dùng Spring Data Elasticsearch

Spring Data Elasticsearch có các abstraction cho thao tác trên một index cụ thể. Có thể lấy `IndexOperations` từ `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class OrderIndexService {

    private final ElasticsearchOperations operations;

    public OrderIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean indexExists() {
        IndexOperations indexOperations = operations.indexOps(
                IndexCoordinates.of("orders-v1"));
        return indexOperations.exists();
    }
}
```

`IndexOperations` tập trung vào lifecycle và metadata của index cụ thể. Các thao tác thường gặp, tùy phiên bản Spring Data Elasticsearch, gồm:

- Kiểm tra index tồn tại (`exists`).
- Tạo và xóa index (`create`, `delete`).
- Tạo hoặc lấy mapping (`createMapping`, `getMapping`).
- Cập nhật mapping (`putMapping`).
- Đọc/cập nhật settings (`getSettings`, `putSettings`).
- Refresh index.
- Làm việc với alias.

Các API này phù hợp khi ứng dụng cần thao tác trên index đã biết. Chúng không nên bị nhầm với toàn bộ Cluster API để quản lý component templates và composable index templates.

### 11.1. Annotation entity không thay thế index template

Spring Data Elasticsearch cho phép khai báo metadata index trong entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders-v1", createIndex = true)
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private java.time.Instant createdAt;
}
```

`@Document`, `@Field`, `@Setting` hoặc `@Mapping` mô tả metadata và cấu hình gắn với entity/index theo cơ chế Spring Data. Chúng không tự tạo reusable component template hay composable index template trên cluster.

Nếu Elasticsearch đã có một index template khớp với tên index, template được Elasticsearch áp dụng khi Spring Data tạo index mới. Spring Data không cần tự đọc template rồi ghép từng component; đây là trách nhiệm của Elasticsearch khi xử lý Create Index API.

Ngược lại, nếu index đã tồn tại, `createIndex = true` không có nghĩa Spring Data sẽ xóa index cũ và tạo lại để áp dụng template mới. Việc thay đổi index hiện hữu cần quy trình migration riêng.

### 11.2. Phạm vi API của Spring Data và Elasticsearch

Nên phân biệt ba lớp API:

| Lớp API | Phạm vi chính | Dùng cho template? |
|---|---|---|
| Spring Data `IndexOperations` | Tạo/xóa index cụ thể, mapping, settings, alias, refresh | Không nên giả định có đầy đủ API quản lý composable/component templates; kiểm tra interface của release train đang dùng |
| Elasticsearch Java API Client | Client Java chính thức cho các REST API Elasticsearch, gồm API ở namespace cluster và indices | Có thể dùng các request tương ứng để quản lý component template, index template và simulate |
| Elasticsearch REST API | Toàn bộ endpoint được server phiên bản đó hỗ trợ | Cách trực tiếp và rõ ràng nhất để quản lý template, data stream và mô phỏng |

Trong các release train Spring Data Elasticsearch phổ biến, `IndexOperations` là abstraction cho index-level operations. Index template và component template thuộc nhóm cluster/index template management API của Elasticsearch. Nếu phiên bản Spring Data không cung cấp abstraction chuyên biệt cho các API này, ứng dụng có thể:

- Dùng Elasticsearch Java API Client được cấu hình cùng Spring Boot để gọi endpoint tương ứng.
- Gọi Elasticsearch REST API từ một công cụ triển khai hoặc migration riêng.
- Quản lý templates bằng infrastructure-as-code hoặc pipeline vận hành trước khi ứng dụng bắt đầu ghi dữ liệu.

Không nên tự suy luận rằng một method `IndexOperations` có thể tạo component template chỉ vì nó có thể tạo index hoặc mapping. Hãy kiểm tra Javadoc và API của đúng phiên bản Spring Data Elasticsearch trong dự án.

## 12. Gọi template API từ Elasticsearch Java API Client

Spring Boot/Spring Data Elasticsearch sử dụng Elasticsearch Java API Client ở các phiên bản hiện đại. Khi cần quản lý template từ Java, có thể inject `co.elastic.clients.elasticsearch.ElasticsearchClient` và gọi API tương ứng trong client.

Ví dụ cấu trúc service:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.stereotype.Service;

@Service
public class ElasticsearchTemplateAdminService {

    private final ElasticsearchClient client;

    public ElasticsearchTemplateAdminService(ElasticsearchClient client) {
        this.client = client;
    }

    // Use client.cluster().putComponentTemplate(...)
    // and client.indices().putIndexTemplate(...)
    // with request types from the matching Elasticsearch Java API Client version.
}
```

Các endpoint được ánh xạ vào những nhóm API tương ứng:

- Component template: Cluster API, ví dụ `cluster().putComponentTemplate(...)`, `cluster().getComponentTemplate(...)` và `cluster().deleteComponentTemplate(...)`.
- Composable index template: Indices API, ví dụ `indices().putIndexTemplate(...)`, `indices().getIndexTemplate(...)` và `indices().deleteIndexTemplate(...)`.
- Mô phỏng template: Indices API với request simulate tương ứng của phiên bản client.

Request class và builder được sinh theo phiên bản Elasticsearch Java API Client. Cấu trúc kiểu cho `settings`, `mappings`, `aliases`, `composed_of` và `data_stream` có thể thay đổi giữa các bản client. Hãy dùng request types từ đúng dependency mà Spring Boot/Spring Data quản lý, thay vì tự thêm một client major version không tương thích vào classpath.

Nếu template được quản lý bởi quy trình triển khai, thường nên để pipeline quản trị thực hiện các thao tác tạo/cập nhật template bằng REST API hoặc công cụ hạ tầng. Ứng dụng runtime chỉ cần quyền đọc/ghi index cần thiết; không nhất thiết phải có quyền cluster-level để thay đổi template.

## 13. API quản lý template thường dùng

Các REST endpoint quan trọng:

| Mục đích | Endpoint |
|---|---|
| Tạo/cập nhật component template | `PUT _component_template/{name}` |
| Đọc component template | `GET _component_template/{name}` |
| Liệt kê component templates | `GET _component_template` |
| Xóa component template | `DELETE _component_template/{name}` |
| Tạo/cập nhật composable index template | `PUT _index_template/{name}` |
| Đọc composable index template | `GET _index_template/{name}` |
| Liệt kê composable index templates | `GET _index_template` |
| Xóa composable index template | `DELETE _index_template/{name}` |
| Mô phỏng định nghĩa template | `POST _index_template/_simulate` |
| Mô phỏng template đã lưu | `POST _index_template/_simulate/{name}` |
| Mô phỏng template cho tên index | `POST _index_template/_simulate_index/{index}` |

Các API template cần quyền cluster phù hợp. Một service account chỉ có quyền index document có thể không có quyền tạo hoặc xóa template. Hãy tách quyền quản trị template khỏi quyền runtime khi triển khai production.

Ngoài ra còn có các API dành cho legacy index templates và các API riêng cho data streams. Khi phát triển mới, ưu tiên composable index templates và kiểm tra tài liệu theo phiên bản Elasticsearch server đang vận hành.

## 14. Legacy index templates và composable templates

Elasticsearch từng cung cấp legacy index templates qua endpoint `_template`. Composable index templates được giới thiệu để giải quyết nhu cầu ghép component templates, điều khiển priority và quản lý cấu hình rõ ràng hơn.

| Legacy template | Composable template |
|---|---|
| API `_template/{name}` | API `_index_template/{name}` |
| Không có component template composition theo mô hình mới | Có `composed_of` để ghép component templates |
| Cơ chế ưu tiên/ghép template cũ | Có `priority` để chọn một composable template phù hợp nhất |
| Cấu trúc quản lý cũ | Phù hợp hơn cho thiết kế template hiện đại và data streams |

Legacy templates đã bị đánh dấu deprecated trong các phiên bản Elasticsearch hiện đại sau khi composable templates xuất hiện. Trạng thái hỗ trợ hoặc loại bỏ cụ thể phụ thuộc phiên bản server. Với hệ thống mới, nên dùng `_index_template` và `_component_template`; với cluster cũ, kiểm tra tài liệu nâng cấp trước khi chuyển đổi.

Không nên duy trì song song hai mô hình mà không hiểu quy tắc ưu tiên giữa chúng. Khi migrate, liệt kê legacy templates, kiểm tra pattern, chuyển cấu hình cần thiết sang component/composable templates, mô phỏng kết quả và kiểm tra index mới trước khi loại bỏ cấu hình cũ.

## 15. Quản lý thay đổi template và migration index

Template là cấu hình cho index được tạo trong tương lai. Khi thay đổi template, cần có kế hoạch cho cả index mới lẫn index cũ.

Ví dụ thay đổi mapping `customerCode` từ `text` sang `keyword`:

1. Tạo component template version mới với mapping `customerCode` kiểu `keyword`.
2. Cập nhật composable index template để tham chiếu component mới.
3. Dùng Simulate Index API với tên index dự kiến để xác nhận mapping.
4. Tạo index mới, ví dụ `orders-v2`.
5. Reindex dữ liệu từ `orders-v1` sang `orders-v2` nếu cần giữ dữ liệu cũ.
6. Kiểm tra document, mapping và truy vấn trên index mới.
7. Chuyển read/write aliases sang index mới bằng Aliases API.
8. Chỉ xóa index cũ sau khi xác nhận migration và chính sách lưu trữ cho phép.

Đặt version và `_meta` trên component/index templates để theo dõi thay đổi. Có thể lưu định nghĩa template dưới dạng JSON/YAML trong repository và triển khai bằng pipeline, giúp thay đổi mapping có lịch sử và có thể review.

Không nên dùng `PUT _index_template` như một thao tác sửa mapping cho mọi index hiện tại. Cập nhật template không chạy migration và không sửa dữ liệu đã lập chỉ mục.

## 16. Quyền truy cập và vận hành

Tạo hoặc xóa template là thao tác quản trị cluster. Hãy phân quyền theo vai trò:

- **Template administrator/deployment pipeline:** có quyền quản lý component templates, index templates và data stream nếu cần.
- **Application runtime:** có quyền đọc/ghi vào index hoặc data stream cụ thể.
- **Read-only analyst:** chỉ có quyền tìm kiếm/đọc dữ liệu phù hợp.

Không cấp quyền cluster-wide quản lý template cho mọi ứng dụng chỉ vì ứng dụng có dùng Spring Data Elasticsearch. Template thay đổi có thể ảnh hưởng nhiều index được tạo sau đó, nên cần review và kiểm soát thay đổi.

Trong môi trường nhiều team, đặt tên component templates theo phạm vi dùng chung và sở hữu rõ ràng. Tránh component template quá rộng có thể vô tình thay đổi mapping của nhiều nhóm index không liên quan.

## 17. Quy trình kiểm tra template trước khi phát hành

Một quy trình triển khai đáng tin cậy có thể gồm:

1. Xác định pattern index hoặc data stream cần áp dụng.
2. Tách settings, mappings và aliases thành component templates theo trách nhiệm.
3. Tạo composable index template với `index_patterns`, `priority`, `composed_of` và phần cấu hình riêng.
4. Kiểm tra component templates và index template đã lưu.
5. Gọi `_simulate` để xem kết quả ghép cấu hình.
6. Gọi `_simulate_index/{index}` để xác định template được chọn cho tên index cụ thể.
7. Tạo index thử nghiệm và đọc lại `_settings`, `_mapping`, `_alias`.
8. Kiểm tra ứng dụng Spring Data Elasticsearch có thể ghi/đọc document với mapping mới.
9. Triển khai template trước khi ứng dụng bắt đầu tạo index mới.
10. Với thay đổi không tương thích, tạo index version mới, reindex và chuyển alias theo quy trình migration.

## 18. Tổng kết

Composable index template định nghĩa index nào nhận cấu hình bằng `index_patterns` và `priority`. Component templates chia settings, mappings và aliases thành các phần có thể tái sử dụng; index template kết hợp chúng qua `composed_of` rồi bổ sung cấu hình riêng trong `template`. Khi nhiều composable templates cùng khớp, template có priority cao nhất được chọn; những template thấp hơn không tự động được ghép vào.

Template chỉ được áp dụng khi tạo index mới hoặc khi tạo backing index mới theo lifecycle của data stream. Thay đổi template không tự sửa index hiện tại. Simulate APIs giúp xem kết quả hợp nhất và template sẽ được chọn trước khi tạo tài nguyên thật.

Trong Spring Data Elasticsearch, `IndexOperations` chủ yếu quản lý index cụ thể như mapping, settings và aliases. Quản lý component templates, composable index templates và simulate thuộc API của Elasticsearch; ứng dụng có thể dùng Elasticsearch Java API Client hoặc REST API phù hợp với phiên bản server/client. Phân biệt rõ các lớp API này giúp chọn đúng công cụ, tránh phụ thuộc vào một abstraction không hỗ trợ đầy đủ và quản lý template an toàn trong vòng đời index.
