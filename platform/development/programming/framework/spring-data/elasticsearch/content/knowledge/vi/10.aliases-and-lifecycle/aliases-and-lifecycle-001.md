# Alias là gì và cách tách tên logic khỏi index vật lý

## 1. Alias là gì?

Trong Elasticsearch, **index alias** là một tên logic trỏ đến một hoặc nhiều index vật lý. Ứng dụng có thể gửi truy vấn hoặc thao tác ghi thông qua alias mà không cần biết tên index đang chứa dữ liệu thực tế.

Ví dụ, hệ thống đang lưu dữ liệu trong index:

~~~text
products-v1
~~~

Thay vì để ứng dụng phụ thuộc trực tiếp vào tên đó, ta tạo alias:

~~~text
products  ->  products-v1
~~~

Ứng dụng chỉ sử dụng tên `products`. Khi cần thay index vật lý, quản trị viên hoặc quy trình triển khai có thể chuyển alias sang `products-v2` mà không phải sửa tên index trong mọi service.

Alias là metadata trong cluster, không phải một index thứ hai và cũng không sao chép dữ liệu. Nó không có shard, mapping hay document riêng. Mọi dữ liệu vẫn nằm trong index vật lý được alias trỏ tới.

## 2. Phân biệt tên logic và tên index vật lý

Tên index vật lý thường biểu thị thế hệ hoặc thời điểm tạo dữ liệu. Tên alias biểu thị khái niệm nghiệp vụ mà ứng dụng muốn truy cập.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Index vật lý | `products-v1` | Nơi thực sự lưu document, mapping và shard |
| Alias logic | `products` | Tên ổn định mà ứng dụng sử dụng |
| Index vật lý mới | `products-v2` | Thế hệ index mới có thể thay mapping hoặc settings |
| Alias đọc | `products-read` | Tên logic dùng cho các truy vấn đọc |
| Alias ghi | `products-write` | Tên logic dùng cho các thao tác ghi |

Sơ đồ:

~~~text
Ứng dụng Spring Data Elasticsearch
              |
              | dùng tên "products"
              v
        Alias: products
              |
              v
        Index: products-v1
              |
              v
        Documents và shards
~~~

Sau khi chuyển sang thế hệ mới:

~~~text
Ứng dụng Spring Data Elasticsearch
              |
              | vẫn dùng tên "products"
              v
        Alias: products
              |
              v
        Index: products-v2
              |
              v
        Documents và shards
~~~

Ứng dụng tiếp tục dùng cùng một tên logic. Việc thay đổi nằm ở quan hệ giữa alias và index vật lý.

Alias đặc biệt hữu ích khi:

- Cần thay mapping hoặc analyzer mà không thể sửa trực tiếp mapping cũ.
- Muốn triển khai index thế hệ mới và chuyển đổi mà hạn chế gián đoạn.
- Muốn tách tên ứng dụng sử dụng khỏi quy tắc đặt tên index theo phiên bản hoặc ngày.
- Muốn tạo tên đọc/ghi ổn định cho nhiều index.
- Muốn giới hạn phạm vi tìm kiếm bằng filter hoặc routing của alias.

## 3. Tạo index và gắn alias

Có thể tạo index vật lý trước:

~~~http
PUT /products-v1
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Sau đó gắn alias `products` vào index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products"
      }
    }
  ]
}
~~~

Từ thời điểm đó, có thể truy vấn thông qua alias:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless headphones"
    }
  }
}
~~~

Elasticsearch giải quyết tên `products` thành index vật lý mà alias đang trỏ tới. Ứng dụng không cần gửi tên `products-v1`.

Có thể kiểm tra alias:

~~~http
GET /_alias/products
~~~

Hoặc xem toàn bộ alias:

~~~http
GET /_cat/aliases?v
~~~

Một alias có thể trỏ đến một index hoặc nhiều index. Khi alias trỏ đến nhiều index, truy vấn đọc thường được thực hiện trên tất cả index đích. Vì vậy, cần bảo đảm mapping giữa các index tương thích với các truy vấn mà ứng dụng gửi qua alias.

Tên alias không thể đồng thời là tên của một index vật lý khác. Hãy dành riêng một namespace tên logic như `products`, `products-read` và `products-write`, còn index vật lý dùng tên có phiên bản như `products-v1`, `products-v2`.

## 4. Alias đọc và alias ghi

Trong hệ thống lớn, có thể tách alias đọc và alias ghi:

~~~text
products-read   -> các index phục vụ tìm kiếm
products-write  -> index nhận document mới và cập nhật
~~~

Tách biệt hai alias giúp ứng dụng kiểm soát rõ luồng đọc và ghi. Ví dụ, alias đọc có thể trỏ đến nhiều index theo thời gian, còn alias ghi chỉ trỏ đến index hiện hành.

Tạo hai alias cùng trỏ đến index đầu tiên:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Ứng dụng dùng:

- `products-read` cho tìm kiếm, lọc và aggregation.
- `products-write` cho index, update và delete document.

Nếu một alias chỉ trỏ đến đúng một index, Elasticsearch có thể mặc định coi index đó là write index. Tuy nhiên, khi alias trỏ đến nhiều index, cần xác định rõ index nhận thao tác ghi bằng `is_write_index: true`. Nếu không có write index được xác định trong trường hợp nhiều index, thao tác ghi qua alias có thể thất bại vì Elasticsearch không biết phải ghi vào đâu.

Một alias có nhiều index đích không có nghĩa thao tác ghi sẽ tự động ghi vào tất cả index. Alias chỉ có một write index được chỉ định cho thao tác ghi. Các truy vấn đọc qua alias nhiều index có thể tìm trên tất cả index đích.

Nếu chỉ có một index đích, có thể dùng cùng một alias cho cả đọc và ghi. Tách riêng read/write alias là lựa chọn kiến trúc, không phải yêu cầu bắt buộc.

## 5. Chuyển alias giữa các index một cách nguyên tử

Một trong những giá trị quan trọng nhất của alias là khả năng chuyển hướng từ index cũ sang index mới bằng một yêu cầu `_aliases`.

Giả sử hiện tại:

~~~text
products -> products-v1
~~~

Ta đã tạo `products-v2` và nạp dữ liệu cần thiết. Có thể chuyển alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Các hành động remove và add trong cùng một yêu cầu alias được áp dụng như một cập nhật cluster state nguyên tử. Client không nhìn thấy trạng thái trung gian mà alias đã bị gỡ khỏi index cũ nhưng chưa được gắn vào index mới.

Trước khi chuyển:

~~~text
products -> products-v1
~~~

Sau khi chuyển:

~~~text
products -> products-v2
~~~

Ứng dụng tiếp tục gửi request đến `products`. Alias mới trỏ đến index mới sau khi cập nhật hoàn tất.

Nếu dùng hai alias đọc và ghi, cần chuyển cả hai trong cùng một thao tác:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Việc thay alias nguyên tử giúp chuyển hướng request nhất quán. Tuy nhiên, nó không tự di chuyển dữ liệu, không đồng bộ các thay đổi phát sinh trong lúc reindex và không bảo đảm index mới đã có đầy đủ dữ liệu. Những việc đó phải được xử lý trước khi chuyển alias.

## 6. Dùng alias để nâng cấp mapping và reindex

Mapping của một field đã được lập chỉ mục thường không thể đổi tùy ý tại chỗ. Ví dụ, `name` ban đầu là `text` nhưng hệ thống mới cần một cấu hình analyzer khác. Cách phổ biến là tạo index mới với mapping/settings mới rồi reindex dữ liệu.

Quy trình tổng quát:

~~~text
products-v1
    |
    | dữ liệu hiện tại
    v
Tạo products-v2 với mapping mới
    |
    v
Reindex từ products-v1 sang products-v2
    |
    v
Kiểm tra số document và kết quả truy vấn
    |
    v
Chuyển alias products sang products-v2
    |
    v
Ứng dụng tiếp tục dùng alias products
~~~

### Bước 1: tạo index mới

~~~http
PUT /products-v2
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "brand": {
        "type": "keyword"
      }
    }
  }
}
~~~

### Bước 2: sao chép document

Dùng Reindex API để sao chép dữ liệu từ index cũ sang index mới:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Reindex đọc document từ source và ghi chúng vào destination. Nó không sao chép alias; alias cần được tạo hoặc chuyển riêng.

### Bước 3: kiểm tra index mới

Có thể so sánh số lượng document:

~~~http
GET /products-v1/_count
GET /products-v2/_count
~~~

Sau đó kiểm tra mapping, các truy vấn quan trọng, dữ liệu đại diện và aggregation. Chỉ số lượng document bằng nhau chưa đủ chứng minh dữ liệu mới chính xác; cần kiểm tra các trường đã thay đổi và những trường hợp nghiệp vụ quan trọng.

### Bước 4: chuyển alias

Sau khi index mới đã sẵn sàng, dùng `_aliases` để chuyển alias từ `products-v1` sang `products-v2`.

### Bước 5: giữ index cũ để rollback

Không nên xóa index cũ ngay sau khi chuyển alias. Có thể giữ lại trong một khoảng thời gian để đối chiếu hoặc rollback nếu phát hiện lỗi. Khi chắc chắn không cần nữa, mới xóa index cũ theo quy trình quản lý vòng đời dữ liệu.

### Lưu ý khi hệ thống vẫn nhận ghi trong lúc reindex

Reindex không tự tạo ra một bản sao đồng bộ liên tục. Nếu ứng dụng tiếp tục ghi vào `products-v1` sau thời điểm reindex đã đọc qua document tương ứng, những thay đổi mới có thể chưa xuất hiện trong `products-v2`.

Cần chọn một chiến lược đồng bộ phù hợp:

- Tạm dừng ghi trong khoảng ngắn, chạy lần đồng bộ cuối cùng, xác minh rồi chuyển alias.
- Dùng transactional outbox hoặc change data capture để ghi nhận các thay đổi phát sinh trong thời gian reindex và áp dụng chúng vào index mới.
- Dùng một quy trình dual-write có kiểm soát, bảo đảm xử lý lỗi và thứ tự cập nhật giữa hai index.
- Chia migration thành giai đoạn có catch-up và một khoảng chuyển đổi ngắn được kiểm soát.

Không nên chỉ chạy `_reindex`, thấy số lượng document gần bằng nhau rồi chuyển alias trong khi hệ thống vẫn có lưu lượng ghi lớn. Alias switch là nguyên tử, nhưng quá trình sao chép dữ liệu trước đó không phải một giao dịch nguyên tử với các thao tác ghi của ứng dụng.

## 7. Alias có thể trỏ đến nhiều index

Một alias có thể đại diện cho một tập index. Ví dụ, hệ thống lưu dữ liệu sản phẩm theo từng năm:

~~~text
products-2025
products-2026
products-2027

products-all -> products-2025
             -> products-2026
             -> products-2027
~~~

Khi tìm kiếm qua `products-all`, Elasticsearch có thể truy vấn tất cả index được alias trỏ tới. Cách này hữu ích cho dữ liệu phân vùng theo thời gian hoặc các tập dữ liệu có cùng mô hình.

Ví dụ tạo alias đọc trên nhiều index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-2025",
        "alias": "products-all"
      }
    },
    {
      "add": {
        "index": "products-2026",
        "alias": "products-all"
      }
    }
  ]
}
~~~

Nếu alias có nhiều index, cần lưu ý:

- Mapping của các index cần tương thích với truy vấn chung.
- Một field có kiểu khác nhau giữa các index có thể gây lỗi hoặc kết quả không nhất quán.
- Truy vấn và aggregation có thể tốn tài nguyên hơn vì phải xử lý nhiều index.
- Thao tác ghi cần xác định rõ write index.
- Khi nhiều index chứa bản sao của cùng một document, kết quả tìm kiếm có thể xuất hiện trùng lặp ở cấp nghiệp vụ.

Không nên dùng alias nhiều index để ghép tùy tiện các thế hệ mapping không tương thích. Khi nâng cấp mapping, thường chuyển alias sang một index thế hệ mới sau khi đã reindex thay vì giữ lâu dài cả hai thế hệ trong cùng alias đọc.

## 8. Filtered alias: giới hạn tập document khi đọc

Alias có thể có filter để các thao tác tìm kiếm qua alias chỉ nhìn thấy document thỏa mãn điều kiện.

Ví dụ tạo alias chỉ hiển thị sản phẩm đang hoạt động:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v2",
        "alias": "active-products",
        "filter": {
          "term": {
            "status": "ACTIVE"
          }
        }
      }
    }
  ]
}
~~~

Truy vấn qua alias:

~~~http
GET /active-products/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

Alias filter được kết hợp với truy vấn tìm kiếm để giới hạn document phù hợp. Ứng dụng có thể dùng các tên logic như `active-products` và `archived-products` cho những tập dữ liệu khác nhau.

Cần nhớ rằng filter của alias không phải cơ chế bảo mật. Nó không thay thế authentication, authorization hoặc document-level security. Filter chủ yếu áp dụng cho truy vấn đọc; không nên dựa vào nó để ngăn ứng dụng ghi một document có `status` không phù hợp qua alias. Nếu cần ràng buộc quyền truy cập dữ liệu, phải cấu hình bảo mật ở Elasticsearch hoặc tầng ứng dụng.

## 9. Alias và routing

Alias cũng có thể cấu hình routing để giới hạn shard mà request sử dụng. Điều này có ích khi hệ thống chủ động dùng custom routing, chẳng hạn phân vùng document theo tenant.

Ví dụ một alias gắn với routing cố định:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v2",
        "alias": "tenant-42-products",
        "index_routing": "tenant-42",
        "search_routing": "tenant-42"
      }
    }
  ]
}
~~~

Trong đó:

- `index_routing` xác định routing được dùng khi ghi qua alias.
- `search_routing` xác định routing được dùng khi tìm kiếm qua alias.

Routing có thể giảm số shard cần truy vấn nếu thiết kế phân phối dữ liệu phù hợp. Tuy nhiên, routing phải nhất quán với cách document được lập chỉ mục. Nếu document được ghi với routing khác, truy vấn qua alias có thể không tìm thấy document đó.

Không nên dùng routing thay cho kiểm soát truy cập. Routing chỉ điều khiển cách Elasticsearch định tuyến đến shard; nó không tự xác thực người dùng hay bảo đảm một tenant không thể truy cập dữ liệu của tenant khác.

## 10. Dùng alias trong Spring Data Elasticsearch

Spring Data Elasticsearch làm việc với index thông qua metadata của entity. Thuộc tính `indexName` trong `@Document` có thể đặt bằng tên alias logic.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructors, getters và setters
}
~~~

Trong ví dụ:

- `indexName = "products"` là tên alias mà repository hoặc operations sử dụng.
- `createIndex = false` ngăn cơ chế tạo index tự động của entity cố tạo một index vật lý có tên `products` khi alias này đã được quản lý bên ngoài.
- Index vật lý thực tế có thể là `products-v1`, `products-v2` hoặc một tên khác do quy trình triển khai quản lý.

Khi repository lưu hoặc tìm `ProductDocument`, Spring Data sử dụng index coordinates lấy từ metadata của entity. Nếu alias `products` đã được tạo và trỏ đúng index, ứng dụng có thể thao tác thông qua alias.

Ví dụ repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Service không cần biết index vật lý:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public ProductDocument save(ProductDocument product) {
        return productRepository.save(product);
    }
}
~~~

Nếu muốn tách riêng alias đọc và ghi, có thể truyền `IndexCoordinates` tương ứng khi gọi API operations hoặc thiết kế repository/service riêng cho từng luồng. Cần bảo đảm các thao tác ghi đi qua alias có write index được chỉ định.

Một điểm cần lưu ý: thao tác tạo index từ `IndexOperations` là thao tác trên index vật lý. Không gọi tạo index với tên alias đã tồn tại như thể alias là index mới. Quy trình provisioning cần tạo index vật lý, mapping và alias trước; ứng dụng sau đó dùng alias để truy cập dữ liệu.

## 11. Quản lý alias bằng IndexOperations và Elasticsearch API

Spring Data Elasticsearch cung cấp abstraction để thao tác index, mapping và alias thông qua `IndexOperations`. Có thể lấy đối tượng thao tác theo entity hoặc `IndexCoordinates`.

Ví dụ lấy `IndexOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

Từ `IndexOperations`, ứng dụng có thể thực hiện các thao tác index và mapping mà abstraction hỗ trợ. Các API alias cụ thể có thể thay đổi theo phiên bản Spring Data Elasticsearch; khi cần các thao tác alias phức tạp như đổi nhiều alias trong một request, dùng Elasticsearch Java API Client hoặc REST API `_aliases` là cách thể hiện trực tiếp và dễ đối chiếu với tài liệu Elasticsearch.

Không nên để mọi instance ứng dụng tự tạo, xóa hoặc chuyển alias khi khởi động. Nhiều replica cùng chạy migration có thể tạo ra tranh chấp hoặc thay đổi trạng thái ngoài dự kiến. Nên quản lý vòng đời index/alias bằng một bước triển khai hoặc migration job có kiểm soát, còn các instance ứng dụng chỉ sử dụng alias đã được provision.

## 12. Alias và rollover

Một ứng dụng ghi dữ liệu liên tục có thể dùng write alias kết hợp với rollover để tạo index vật lý mới khi index hiện tại đạt điều kiện về kích thước, tuổi hoặc số document.

Ví dụ:

~~~text
events-write -> events-000001
~~~

Khi đạt điều kiện rollover, Elasticsearch tạo index tiếp theo và chuyển write alias sang index mới:

~~~text
events-write -> events-000002
~~~

Ví dụ gọi rollover API:

~~~http
POST /events-write/_rollover
{
  "conditions": {
    "max_age": "30d",
    "max_primary_shard_size": "50gb"
  }
}
~~~

Rollover API kiểm tra điều kiện, tạo index mới theo cấu hình phù hợp và cập nhật write alias. Các thao tác ghi tiếp theo qua `events-write` sẽ đến index mới. Đây là mô hình thường dùng cho log, event và dữ liệu append-heavy.

Index vật lý có thể được đặt theo chuỗi số tăng dần như `events-000001`, `events-000002`. Ứng dụng chỉ cần dùng `events-write` cho ghi và một alias đọc phù hợp cho tìm kiếm.

Rollover không giống reindex:

- **Rollover** tạo index kế tiếp để nhận dữ liệu mới; các index cũ vẫn giữ dữ liệu cũ.
- **Reindex** sao chép document từ index nguồn sang index đích, thường dùng khi thay mapping hoặc cấu trúc dữ liệu.

Nếu cần quản lý dữ liệu theo thời gian với lifecycle policy, có thể kết hợp alias với Index Lifecycle Management (ILM) hoặc cơ chế data stream phù hợp. Hãy chọn mô hình theo loại dữ liệu và yêu cầu truy vấn.

## 13. Những lỗi thường gặp khi dùng alias

**Nhầm alias với index vật lý.** Alias không chứa document riêng. Xóa alias không đồng nghĩa xóa index đích; xóa index đích có thể làm alias mất target.

**Ứng dụng tự tạo index trùng tên alias.** Nếu `products` đã là alias, cơ chế tự tạo index có thể thất bại do tên đó đã được sử dụng. Với entity dùng alias đã provision sẵn, cân nhắc `createIndex = false`.

**Alias nhiều index nhưng không có write index.** Truy vấn đọc có thể hoạt động nhưng thao tác ghi thất bại vì Elasticsearch không xác định được index nhận dữ liệu. Đặt `is_write_index` rõ ràng.

**Chuyển alias trước khi dữ liệu sẵn sàng.** Alias switch rất nhanh nhưng không kiểm tra tính đầy đủ của dữ liệu. Chỉ chuyển sau khi reindex, catch-up và xác minh hoàn tất.

**Bỏ qua các lần ghi phát sinh trong migration.** Reindex không tự đồng bộ các thay đổi mới. Cần pause/catch-up, CDC hoặc một chiến lược dual-write có kiểm soát.

**Mapping giữa các index không tương thích.** Alias đọc nhiều index có thể gặp lỗi truy vấn hoặc aggregation khi một field có kiểu khác nhau. Hãy thống nhất mapping trước khi thêm index vào alias chung.

**Dùng alias filter làm bảo mật.** Filter không thay thế authorization. Phân quyền phải được cấu hình bằng cơ chế bảo mật thích hợp.

**Xóa index cũ ngay sau khi switch.** Giữ index cũ đủ lâu để xác minh và rollback theo chính sách lưu trữ của hệ thống.

**Để mọi instance ứng dụng quản lý alias.** Provisioning nên là một bước triển khai có kiểm soát, tránh nhiều instance cùng thực hiện thao tác thay đổi cluster state.

## 14. Quy trình thiết kế alias trong dự án

Có thể triển khai theo trình tự sau:

1. Chọn tên logic ổn định mà ứng dụng sẽ sử dụng, ví dụ `products`.
2. Đặt tên index vật lý theo thế hệ, ví dụ `products-v1`.
3. Tạo index vật lý với settings và mapping đã xác định.
4. Tạo alias đọc/ghi hoặc alias dùng chung, chỉ định write index nếu cần.
5. Cấu hình entity Spring Data với `@Document(indexName = "products", createIndex = false)` khi alias được provision bên ngoài.
6. Kiểm tra repository và operations đọc/ghi thông qua alias.
7. Khi cần thay mapping, tạo index thế hệ mới, reindex và đồng bộ các thay đổi phát sinh.
8. Xác minh dữ liệu, mapping, truy vấn và số document trước khi chuyển alias.
9. Dùng một request `_aliases` để chuyển hướng alias nguyên tử.
10. Theo dõi ứng dụng, giữ index cũ trong thời gian rollback rồi mới xóa theo chính sách.

## Kết luận

Alias tách tên logic mà ứng dụng sử dụng khỏi tên index vật lý nơi Elasticsearch thực sự lưu document. Ứng dụng có thể tiếp tục làm việc với `products` trong khi hệ thống thay `products-v1` bằng `products-v2`, hoặc dùng các alias đọc/ghi riêng để quản lý luồng truy cập.

Alias còn hỗ trợ nhiều index, write index, filter, routing và rollover. Giá trị lớn nhất của nó trong vòng đời index là cho phép chuyển hướng bằng một cập nhật cluster state nguyên tử. Để migration an toàn, vẫn phải chuẩn bị mapping, reindex, đồng bộ dữ liệu phát sinh trong lúc chuyển đổi và xác minh index đích trước khi đổi alias.

Trong Spring Data Elasticsearch, đặt `@Document(indexName = "products")` giúp repository và operations sử dụng tên logic ổn định. Việc tạo index vật lý và quản lý alias nên được thực hiện như một bước provisioning có kiểm soát, để ứng dụng không phụ thuộc vào tên index theo từng thế hệ.

## Tài liệu tham khảo

- [Elasticsearch — Aliases](https://www.elastic.co/docs/manage-data/data-store/aliases)
- [Elasticsearch — Add and remove aliases](https://www.elastic.co/docs/manage-data/data-store/aliases#alias-management)
- [Elasticsearch — Reindex documents](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex)
- [Elasticsearch — Rollover API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-rollover)
- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
