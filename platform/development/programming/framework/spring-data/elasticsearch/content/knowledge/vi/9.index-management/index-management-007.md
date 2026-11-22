# Settings tĩnh, settings động và điều kiện cập nhật

Index Elasticsearch có nhiều thiết lập ảnh hưởng tới cách dữ liệu được lưu, phân bổ shard, làm mới kết quả tìm kiếm và phân tích văn bản. Spring Data Elasticsearch có thể cung cấp settings khi tạo index và gọi API để thay đổi những thiết lập được phép cập nhật. Trước khi thay đổi, cần xác định setting thuộc phạm vi nào, có thể đổi khi index đang mở hay không và thay đổi đó có yêu cầu lập chỉ mục lại dữ liệu hay không.

Bài học tập trung vào **index settings**. Đây là cấu hình của một index cụ thể, khác với mapping mô tả kiểu và cách lập chỉ mục của từng field, cũng khác với cluster settings áp dụng cho toàn cluster.

## 1. Settings, mapping và cluster settings

Elasticsearch quản lý cấu hình index thành hai nhóm lớn:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Index settings | Điều khiển hoạt động và cấu trúc của một index. | Số primary shard, số replica, refresh interval, analyzer. |
| Mapping | Định nghĩa field, kiểu dữ liệu và cách field được lập chỉ mục. | `text`, `keyword`, `date`, `object`, `nested`. |

Ngoài ra, cluster settings điều khiển hành vi ở cấp cluster hoặc node, chẳng hạn một số chính sách phân bổ shard, giới hạn cluster và hành vi vận hành. Cluster settings có API và phạm vi áp dụng riêng; không nên nhầm chúng với index settings chỉ vì tên setting đều có tiền tố `cluster.*` hoặc `index.*`.

Ví dụ:

- `index.number_of_replicas` là setting của index.
- `index.refresh_interval` là setting của index.
- `index.analysis.analyzer` định nghĩa analyzer thuộc settings của index.
- `cluster.routing.allocation.enable` là setting ở cấp cluster.

Mapping và settings thường được khai báo cùng lúc khi tạo index, nhưng chúng là hai phần cấu hình riêng. Thay đổi số replica không đổi kiểu field; thay đổi mapping từ `text` sang `keyword` không phải là cập nhật index settings.

## 2. Settings tĩnh và settings động

Elasticsearch phân loại index settings theo điều kiện cập nhật. Cần đọc đúng loại setting trước khi gọi API.

### 2.1. Dynamic settings

**Dynamic settings** có thể được cập nhật khi index đang mở. Sau khi gọi Update Index Settings API thành công, Elasticsearch áp dụng giá trị mới mà không cần đóng index.

Một số ví dụ thường gặp:

| Setting | Tác dụng |
| --- | --- |
| `index.number_of_replicas` | Số replica shard cho mỗi primary shard. |
| `index.refresh_interval` | Khoảng thời gian định kỳ để thay đổi được làm mới và có thể xuất hiện trong search. |
| `index.max_result_window` | Giới hạn cửa sổ kết quả cho các truy vấn phân trang kiểu `from`/`size`. |
| `index.routing.allocation.*` | Một số quy tắc điều khiển nơi shard của index được phân bổ. |

Ví dụ, đổi số replica và refresh interval:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "number_of_replicas": 0,
    "refresh_interval": "30s"
  }
}
~~~

Request trên thay đổi settings của index `products` khi index đang mở. Đặt replica về `0` thường phù hợp với một cluster học tập chỉ có một node, vì không có node thứ hai để phân bổ replica. Trong cluster nhiều node, số replica cần được chọn theo yêu cầu sẵn sàng và khả năng chịu lỗi.

`refresh_interval` lớn hơn có thể giảm tần suất refresh và cải thiện throughput ghi, nhưng dữ liệu mới sẽ xuất hiện trong search chậm hơn. Đặt giá trị `-1` sẽ tắt refresh định kỳ; khi đó ứng dụng cần chủ động refresh nếu muốn tìm thấy dữ liệu vừa ghi trong lúc kiểm thử. Không thay đổi setting này mà không hiểu tác động tới độ trễ tìm kiếm.

### 2.2. Static settings

**Static settings** thường chỉ có thể thay đổi khi index đã đóng, hoặc chỉ có thể khai báo khi tạo index. Điều kiện cụ thể phụ thuộc setting.

Một số setting thuộc nhóm static có thể được cập nhật sau khi đóng index. Ví dụ, các cấu hình analyzer trong `index.analysis` thường cần index đóng trước khi cập nhật. Trình tự tổng quát:

1. Đóng index.
2. Gửi thay đổi settings được phép cập nhật.
3. Mở lại index.
4. Kiểm tra trạng thái index và hoạt động của ứng dụng.

Ví dụ dạng API:

~~~http
POST /products/_close
~~~

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "analysis": {
      "analyzer": {
        "catalog_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  }
}
~~~

~~~http
POST /products/_open
~~~

Đây là minh họa quy trình thay đổi setting analyzer. Analyzer phải được tham chiếu đúng trong mapping field và cấu hình mới cần được kiểm tra bằng `_analyze`. Đóng index làm gián đoạn hoạt động đọc/ghi/search của index trong khoảng thời gian cập nhật; nên lên kế hoạch cho thao tác này.

### 2.3. Static không đồng nghĩa với có thể đổi khi index đóng

Một số settings là **final/immutable** sau khi index đã được tạo. Đóng index không làm chúng trở thành có thể cập nhật.

Ví dụ quan trọng nhất là `index.number_of_shards`: số primary shard được quyết định khi tạo index và không thể đổi bằng Update Index Settings API sau đó, kể cả khi index đã đóng.

Nếu cần thay đổi số primary shard, phải chọn một chiến lược di chuyển dữ liệu phù hợp, chẳng hạn:

- Tạo index mới với số shard mong muốn rồi reindex dữ liệu sang index mới.
- Dùng split index khi điều kiện của thao tác split được đáp ứng và số routing shard ban đầu cho phép.
- Dùng shrink index khi muốn giảm số primary shard và đáp ứng các điều kiện của shrink.

Không gửi request cập nhật `number_of_shards` rồi kỳ vọng đóng/mở index sẽ giải quyết được. Cần thiết kế việc chuyển đổi index và kiểm tra dữ liệu trước khi chuyển alias hoặc cấu hình ứng dụng.

## 3. Xem settings hiện tại

Trước khi cập nhật, hãy đọc cấu hình đang có:

~~~http
GET /products/_settings
~~~

Để xem cả giá trị mặc định mà Elasticsearch áp dụng:

~~~http
GET /products/_settings?include_defaults=true
~~~

Phản hồi có cấu trúc theo index và chứa các giá trị settings. Khi đọc kết quả, phân biệt giá trị được khai báo trực tiếp với giá trị mặc định do Elasticsearch cung cấp. Không nên sao chép toàn bộ kết quả settings rồi gửi ngược lại một cách máy móc, vì payload có thể chứa các giá trị nội bộ hoặc setting không cần thay đổi.

Có thể đọc một số setting cụ thể bằng cách giới hạn tên setting trong API hoặc lọc kết quả ở phía client, tùy nhu cầu kiểm tra.

## 4. Tạo index với settings ngay từ đầu

Với setting static hoặc final, cách an toàn nhất là khai báo giá trị mong muốn khi tạo index. Ví dụ tạo index `products` có một primary shard, không có replica và custom analyzer:

~~~http
PUT /products
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "catalog_text"
      },
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

Index được tạo với toàn bộ settings và mapping trong một request. Việc này tránh tạo index trước với cấu hình mặc định rồi phải thay đổi những setting cần quyết định ngay từ đầu.

Khi thiết kế index cho môi trường thật, số shard nên dựa trên kích thước dữ liệu, tốc độ ghi/đọc, topology cluster và kế hoạch tăng trưởng. Không chọn số shard chỉ theo thói quen hoặc sao chép từ môi trường học tập.

## 5. Cập nhật dynamic settings bằng REST API

Ví dụ thay đổi `refresh_interval` trong lúc index đang mở:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index.refresh_interval": "5s"
}
~~~

Có thể gửi một hoặc nhiều setting trong cùng request. Chỉ đưa vào payload những setting thực sự cần thay đổi. Elasticsearch kiểm tra quyền của người gọi và tính hợp lệ của giá trị trước khi áp dụng.

Để kiểm tra sau khi cập nhật:

~~~http
GET /products/_settings?filter_path=*.settings.index.number_of_replicas,*.settings.index.refresh_interval
~~~

Việc update setting dynamic không có nghĩa mọi thay đổi đã hoàn tất ngay tức khắc ở mọi node. Thay đổi số replica có thể kích hoạt phân bổ và đồng bộ shard; cần theo dõi cluster health và allocation cho tới khi hệ thống đạt trạng thái mong muốn.

## 6. Cập nhật static settings cần đóng index

Với setting cho phép cập nhật khi index đóng, quy trình có thể thực hiện như sau:

~~~http
POST /products/_close
~~~

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding", "trim"]
        }
      }
    }
  }
}
~~~

~~~http
POST /products/_open
~~~

Khi thao tác thủ công, hãy xác nhận index đã đóng trước khi gửi setting và mở lại sau khi cập nhật thành công. Nếu request cập nhật thất bại, cần kiểm tra trạng thái index và xử lý để index không bị bỏ quên ở trạng thái closed.

Thay đổi định nghĩa analyzer không tự phân tích lại dữ liệu đã được index trước đó. Analyzer mới có thể được sử dụng cho các lần lập chỉ mục tiếp theo hoặc tìm kiếm theo cấu hình tương ứng, nhưng token cũ trong inverted index vẫn được tạo bởi analyzer trước đó. Muốn thay đổi index-time analysis cho toàn bộ dữ liệu, cần reindex vào index mới.

Một số search analyzer có thể hỗ trợ reload riêng, ví dụ khi dùng synonym filter được thiết kế để reload. Đây là cơ chế chuyên biệt theo loại filter và phiên bản Elasticsearch; không được hiểu rằng mọi static settings đều có thể reload khi index đang mở.

## 7. Những điều kiện cần kiểm tra trước khi cập nhật

Không phải mọi setting đều có cùng điều kiện. Trước khi gọi API, cần kiểm tra các điểm sau:

| Điều kiện | Câu hỏi cần trả lời |
| --- | --- |
| Phạm vi | Đây là index setting, mapping hay cluster setting? |
| Loại setting | Dynamic, static nhưng cập nhật được khi đóng, hay final/immutable? |
| Trạng thái index | Index có cần closed không? Có ứng dụng đang phụ thuộc vào index không? |
| Quyền | Tài khoản có quyền quản lý settings của index không? |
| Tương thích | Setting và giá trị có được phiên bản Elasticsearch hiện tại hỗ trợ không? |
| Dữ liệu | Thay đổi có làm thay đổi cách lập chỉ mục dữ liệu cũ không? Có cần reindex? |
| Tác động vận hành | Có phát sinh shard relocation, thời gian ngừng truy cập hoặc tăng tải không? |
| Khả năng quay lui | Có lưu lại giá trị cũ và cách phục hồi không? |

Đặc biệt, setting có thể cập nhật khi index mở vẫn có thể gây tác động hiệu năng. Ví dụ giảm refresh frequency có thể tăng độ trễ tìm kiếm; tăng replica làm tăng dung lượng lưu trữ và tải mạng; thay đổi allocation có thể di chuyển shard giữa các node.

## 8. Settings trong Spring Data Elasticsearch

Spring Data Elasticsearch có thể cung cấp settings khi tạo index thông qua metadata entity. Annotation `@Setting` cho phép chỉ định file settings trên classpath.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products")
@Setting(settingPath = "/elasticsearch/products-settings.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "catalog_text")
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    // Constructor, getters và setters
}
~~~

File `src/main/resources/elasticsearch/products-settings.json` có thể chứa settings như sau:

~~~json
{
  "index": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  }
}
~~~

Khi Spring Data tạo index dựa trên metadata của entity, settings từ file được dùng cùng mapping tương ứng. `@Field(analyzer = "catalog_text")` tham chiếu analyzer đã được khai báo trong settings.

`@Setting` mô tả cấu hình cho quá trình tạo index. Nó không phải cơ chế migration tự động để cập nhật mọi index đã tồn tại mỗi khi ứng dụng khởi động. Nếu index đã được tạo trước đó, việc sửa file settings không tự động thay đổi cấu hình của index đang chạy.

## 9. Cập nhật settings qua `IndexOperations`

`ElasticsearchOperations` cung cấp `IndexOperations` để quản lý index từ code Java. Có thể lấy operations tương ứng với entity:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void inspectIndex() {
        IndexOperations indexOperations = operations.indexOps(Product.class);
        boolean exists = indexOperations.exists();

        if (exists) {
            var currentSettings = indexOperations.getSettings(false);
            // Ghi nhận hoặc kiểm tra các settings cần thiết
        }
    }
}
~~~

Với dynamic setting, có thể tạo một `Document` chứa các giá trị cần cập nhật rồi gọi `putSettings`. Ví dụ minh họa cho API của Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.IndexOperations;

IndexOperations indexOperations = operations.indexOps(Product.class);

Document updateSettings = Document.parse("""
    {
      "index": {
        "number_of_replicas": 0,
        "refresh_interval": "10s"
      }
    }
    """);

indexOperations.putSettings(updateSettings);
~~~

Các method và kiểu tham số có thể khác giữa các phiên bản Spring Data Elasticsearch. Hãy dùng API tương ứng với phiên bản dependency của dự án. Nguyên tắc vẫn giống REST API: `putSettings` gửi phần settings cần thay đổi; nó không biến một setting final thành setting có thể cập nhật.

Đối với thay đổi cần đóng index, cần điều phối rõ các thao tác close, put settings và open bằng `IndexOperations` hoặc REST API phù hợp. Không nên đặt chuỗi thao tác này trong logic khởi động ứng dụng mà không có kiểm soát thời gian ngừng truy cập và xử lý lỗi.

## 10. Settings và vòng đời index

Settings thường được áp dụng ở những thời điểm khác nhau:

~~~mermaid
flowchart TD
    A["Thiết kế index"] --> B["Khai báo settings và mapping"]
    B --> C["Tạo index"]
    C --> D["Ghi và tìm kiếm document"]
    D --> E{"Cần thay đổi setting?"}
    E -->|Không| D
    E -->|Có| F{"Loại setting?"}
    F -->|Dynamic| G["Update khi index mở"]
    F -->|Static có thể sửa| H["Close index"]
    H --> I["Update setting"]
    I --> J["Open index"]
    F -->|Final/immutable| K["Tạo index mới hoặc dùng split/shrink nếu phù hợp"]
    G --> L["Kiểm tra settings và cluster health"]
    J --> L
    K --> M["Di chuyển dữ liệu / chuyển alias"]
    L --> D
    M --> D
~~~

Đối với index quan trọng, nên quản lý thay đổi bằng migration có phiên bản thay vì cập nhật thủ công tùy hứng. Migration cần biết trạng thái hiện tại, giá trị đích, điều kiện cập nhật, cách xác minh và cách khôi phục khi thao tác thất bại.

## 11. Reindex khi thay đổi cách phân tích hoặc cấu trúc

Một số thay đổi chỉ ảnh hưởng hoạt động vận hành, nhưng một số thay đổi ảnh hưởng cách document được lập chỉ mục. Cần phân biệt:

| Thay đổi | Có cần reindex không? |
| --- | --- |
| Tăng `number_of_replicas` | Không cần reindex; Elasticsearch phân bổ thêm replica. |
| Đổi `refresh_interval` | Không cần reindex. |
| Thêm hoặc đổi định nghĩa analyzer dùng khi index | Thường cần reindex để token của document cũ được tạo lại theo analyzer mới. |
| Đổi kiểu mapping của field đã tồn tại | Thông thường cần index mới và reindex. |
| Đổi số primary shard bằng cách tạo index mới | Cần chuyển dữ liệu sang index mới hoặc dùng thao tác split/shrink thích hợp. |

Ví dụ tạo index mới với settings và mapping mới:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "catalog_text_v2"
      },
      "sku": { "type": "keyword" }
    }
  }
}
~~~

Chuyển dữ liệu:

~~~http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Reindex sao chép document từ source sang destination; nó không tự tạo settings hoặc mapping đích theo ý muốn. Vì vậy phải tạo `products-v2` trước với settings/mapping cần thiết. Với hệ thống đang ghi liên tục, cần kế hoạch đồng bộ phần thay đổi phát sinh trong lúc reindex trước khi chuyển alias hoặc endpoint ứng dụng.

## 12. Kiểm tra và xác minh sau khi cập nhật

Sau mỗi thay đổi, xác minh cả cấu hình lẫn hành vi:

1. Đọc lại settings bằng `GET /<index>/_settings`.
2. Kiểm tra index đã mở và có trạng thái mong muốn.
3. Kiểm tra cluster health và shard allocation nếu thay đổi replica hoặc allocation.
4. Nếu thay analyzer, chạy `_analyze` để xác nhận token mới.
5. Thử ghi và tìm kiếm document đại diện.
6. Kiểm tra ứng dụng Spring Data đang kết nối đúng index/alias.
7. Ghi nhận giá trị cũ, giá trị mới và kết quả migration để có thể truy vết.

Không coi HTTP status thành công là bằng chứng duy nhất. Ví dụ, update replica có thể thành công nhưng shard vẫn đang được phân bổ; thay đổi analyzer có thể được lưu nhưng document cũ vẫn mang token cũ.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Update settings bị từ chối vì index đang mở | Setting yêu cầu index phải closed. | Kiểm tra loại setting, đóng index theo kế hoạch rồi cập nhật và mở lại. |
| Update `number_of_shards` thất bại | Đây là setting final sau khi tạo index. | Tạo index mới, reindex hoặc dùng split/shrink nếu đáp ứng điều kiện. |
| Index không mở lại sau khi update | Setting mới không hợp lệ hoặc có lỗi vận hành khi reopen. | Đọc response và log, sửa nguyên nhân rồi mở lại; xác nhận trạng thái trước khi kết thúc migration. |
| Thay analyzer nhưng kết quả cũ không đổi | Document cũ vẫn có token được tạo bởi analyzer cũ. | Reindex dữ liệu vào index mới với analyzer mới. |
| Ứng dụng khởi động nhưng settings không đổi | `@Setting` chỉ được dùng khi tạo index; index đã tồn tại. | Quản lý cập nhật bằng migration hoặc `IndexOperations`/REST API. |
| Replica không được phân bổ | Cluster thiếu node phù hợp, allocation bị giới hạn hoặc node không đủ tài nguyên. | Kiểm tra `_cluster/health`, allocation explain và cấu hình cluster. |
| Refresh interval đổi nhưng search vẫn trễ | Giá trị mới chưa được kiểm tra đúng, refresh bị tắt hoặc request cần refresh rõ ràng. | Đọc lại setting và kiểm tra refresh/search visibility. |

## 14. Quy trình quản lý settings an toàn

Khi chuẩn bị thay đổi index settings, hãy thực hiện theo trình tự:

1. Xác định index hoặc alias thực tế mà ứng dụng đang dùng.
2. Đọc settings hiện tại và lưu lại giá trị liên quan.
3. Tra cứu điều kiện cập nhật của từng setting theo phiên bản Elasticsearch đang chạy.
4. Phân loại dynamic, static có thể cập nhật khi đóng hoặc final/immutable.
5. Xác định có cần đóng index, reindex, split hoặc shrink hay không.
6. Đánh giá tác động tới search, write, shard allocation, dung lượng và thời gian ngừng truy cập.
7. Chuẩn bị giá trị mới, lệnh cập nhật, bước xác minh và phương án quay lui.
8. Thực hiện thay đổi trong migration hoặc cửa sổ vận hành phù hợp.
9. Đọc lại settings, kiểm tra cluster health và thử các thao tác ứng dụng.
10. Chỉ chuyển alias hoặc hoàn tất phát hành khi index mới đáp ứng yêu cầu.

Trong Spring Data Elasticsearch, `@Setting` giúp khai báo settings cho lúc tạo index, còn `IndexOperations` cung cấp API đọc và cập nhật index trong code. Quyền cập nhật thực tế vẫn do Elasticsearch quyết định: dynamic settings có thể đổi khi index mở, một số static settings cần đóng index, còn setting final như số primary shard phải được quyết định khi tạo index hoặc xử lý bằng chiến lược di chuyển dữ liệu.
