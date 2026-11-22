# Read alias, write alias và is_write_index

Trong Elasticsearch, alias là một tên logic trỏ tới một hoặc nhiều index. Ứng dụng có thể dùng alias để đọc dữ liệu mà không cần biết tên index vật lý đang chứa dữ liệu. Khi tạo index mới, chuyển alias sang index mới giúp ứng dụng tiếp tục dùng cùng một tên ổn định.

Với hệ thống có nhiều index theo thời gian hoặc cần triển khai không gián đoạn, nên phân biệt rõ **read alias** và **write alias**. Read alias xác định những index cần được tìm kiếm. Write alias xác định index nhận thao tác ghi. Thuộc tính **is_write_index** chỉ ra index nào là đích ghi khi một alias trỏ tới nhiều index.

Bài học này trình bày cách hoạt động của alias, cách cấu hình read/write alias, cách Elasticsearch chọn write index, cách thay đổi alias an toàn và cách tích hợp alias với Spring Data Elasticsearch.

## 1. Alias là gì?

Alias là một tên thay thế cho index hoặc một nhóm index. Ứng dụng gửi request tới alias như thể đang làm việc với index:

~~~http
GET /products-read/_search
~~~

Nếu products-read là alias trỏ tới products-000001, Elasticsearch thực hiện tìm kiếm trên index đó. Ứng dụng không cần biết index vật lý có hậu tố 000001.

Alias không chứa document riêng và không lưu dữ liệu. Dữ liệu vẫn nằm trong các index vật lý. Alias chỉ cung cấp một lớp định tuyến và một tên ổn định cho các thao tác được hỗ trợ.

Ví dụ, hệ thống có các index:

~~~text
products-000001
products-000002
products-000003
~~~

Có thể tạo alias products-read trỏ đến cả ba index. Một request search tới alias sẽ tìm trên các index thành viên và hợp nhất kết quả.

Một alias có thể trỏ tới:

- Một index duy nhất.
- Nhiều index cùng lúc.
- Một data stream trong các trường hợp Elasticsearch hỗ trợ alias tương ứng.

Tên alias không được trùng với tên index hoặc data stream đã tồn tại. Nên dùng convention rõ ràng để phân biệt tên index vật lý và tên alias, ví dụ hậu tố -read và -write.

### Alias giúp ứng dụng độc lập với tên index vật lý

Nếu ứng dụng truy cập trực tiếp products-000001, mỗi lần chuyển sang index mới, phải thay cấu hình hoặc triển khai lại ứng dụng. Nếu ứng dụng truy cập products-read, quản trị viên có thể thay đổi index đứng sau alias mà code vẫn dùng tên cũ.

Đây là nền tảng của:

- Chuyển đổi index sau khi reindex.
- Triển khai blue/green.
- Quản lý index theo ngày hoặc theo chu kỳ.
- Rollover khi index đạt ngưỡng dung lượng hoặc tuổi.
- Tách luồng đọc và ghi.

## 2. Read alias và write alias khác nhau thế nào?

Hai loại alias có mục đích khác nhau.

**Read alias** đại diện cho tập index mà ứng dụng cần đọc. Nó thường trỏ tới một hoặc nhiều index. Khi search qua read alias, Elasticsearch tìm trên các index được alias tham chiếu.

**Write alias** đại diện cho đích nhận thao tác ghi. Nó cần xác định một index có thể nhận thao tác index/update/create/delete phù hợp với API được gọi. Nếu alias trỏ tới nhiều index, Elasticsearch cần biết index nào là write index.

Ví dụ một ứng dụng catalog:

~~~text
products-read  ---> products-000001
              ---> products-000002
              ---> products-000003

products-write ---> products-000003 (write index)
~~~

Ứng dụng đọc qua products-read nên có thể tìm thấy document từ các index cũ và mới. Ứng dụng ghi qua products-write nên document mới được ghi vào index hiện hành.

Read alias và write alias có thể là hai alias riêng. Chúng cũng có thể là cùng một alias nếu hệ thống muốn một tên dùng cho cả đọc và ghi. Trong trường hợp alias vừa trỏ tới nhiều index vừa nhận ghi, is_write_index xác định đích ghi.

### Read alias có thể trỏ tới nhiều index

Một alias đọc có thể bao gồm tất cả index đang giữ dữ liệu:

~~~http
GET /products-read/_search
{
  "query": {
    "match": {
      "title": "keyboard"
    }
  }
}
~~~

Elasticsearch gửi công việc tới các shard thuộc những index được alias tham chiếu. Response được hợp nhất như một lần tìm kiếm trên nhiều index.

Các index phía sau alias nên có mapping tương thích. Nếu một index khai báo price là double còn index khác khai báo cùng field là keyword, sort hoặc aggregation có thể gặp lỗi hoặc hành vi không đồng nhất.

### Write alias cần một đích ghi rõ ràng

Khi một alias trỏ tới đúng một index, index đó mặc định được xem là write index nếu không có cấu hình khác. Khi alias trỏ tới nhiều index, cần đánh dấu một index bằng is_write_index: true.

Nếu alias trỏ tới nhiều index nhưng không có write index, thao tác ghi qua alias sẽ thất bại vì Elasticsearch không thể tự chọn index nhận dữ liệu.

Đây là lý do read alias thường có nhiều thành viên, còn write alias cần đúng một đích ghi.

## 3. is_write_index có ý nghĩa gì?

is_write_index là thuộc tính của quan hệ giữa một alias và một index. Nó cho Elasticsearch biết index nào là đích ghi khi alias có nhiều index đích.

Ví dụ:

~~~json
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
        "alias": "products-write",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "products-000002",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Trong cấu hình này:

- products-write trỏ tới hai index.
- products-000001 không nhận ghi qua alias.
- products-000002 là write index.
- Request ghi qua products-write được chuyển tới products-000002.

is_write_index không phải thuộc tính của document, không phải mapping field và cũng không thay đổi quyền truy cập. Nó chỉ xác định đích ghi cho alias.

### Nếu alias chỉ trỏ tới một index

Khi alias trỏ tới một index duy nhất, Elasticsearch tự xem index đó là write index theo mặc định. Có thể khai báo rõ is_write_index: true để cấu hình dễ đọc và tránh nhầm lẫn khi sau này thêm index.

### Nếu alias trỏ tới nhiều index nhưng không chỉ định write index

Elasticsearch không có cơ sở để chọn index ghi. Thao tác ghi qua alias sẽ báo lỗi yêu cầu xác định write index.

Không nên trông chờ Elasticsearch chọn index mới nhất theo tên hoặc theo ngày. Tên index không quyết định write target; alias metadata mới là nguồn thông tin có thẩm quyền.

### Nếu mọi index đều được đặt is_write_index: false

Alias không có write index. Search qua alias vẫn có thể hoạt động, nhưng thao tác ghi qua alias không có đích hợp lệ và sẽ thất bại.

### Có thể có nhiều write index cho cùng một alias không?

Một alias không thể có nhiều write index đồng thời. Khi cấu hình alias trỏ tới nhiều index, chỉ một index được đánh dấu là write index. Việc có nhiều write target sẽ làm mất tính xác định của định tuyến ghi.

Nếu cần ghi vào nhiều index, ứng dụng phải thực hiện nhiều thao tác ghi có chủ đích hoặc dùng một cơ chế ingest/replication phù hợp. Không dùng một alias với nhiều write index để kỳ vọng Elasticsearch tự nhân bản request.

## 4. Tạo index và cấu hình read/write alias

Giả sử bắt đầu với index products-000001. Ta tạo index với mapping trước:

~~~http
PUT /products-000001
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Sau đó gắn hai alias vào index này:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-000001",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Lúc này:

- Search qua products-read đọc từ products-000001.
- Ghi qua products-write ghi vào products-000001.

Có thể xác nhận alias:

~~~http
GET /_alias/products-read
GET /_alias/products-write
~~~

Hoặc xem alias của một index cụ thể:

~~~http
GET /products-000001/_alias
~~~

API trả về thông tin index và alias đang liên kết với nó. Kiểm tra is_write_index trong metadata của write alias để xác nhận đích ghi.

### Dùng một alias cho cả đọc và ghi

Một mô hình khác là chỉ dùng products làm alias chung. Alias có thể trỏ tới nhiều index để đọc, đồng thời chỉ định một write index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
        "alias": "products",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "products-000002",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Search qua products đọc cả hai index; thao tác ghi qua products chỉ đi vào products-000002.

Cách này đơn giản cho ứng dụng chỉ cần một tên. Tuy nhiên, tách read/write alias giúp quyền truy cập và mục đích sử dụng rõ ràng hơn, nhất là khi các thành phần ứng dụng có chính sách đọc/ghi khác nhau.

## 5. Định tuyến các thao tác qua alias

Alias được dùng trong đường dẫn của API giống như tên index.

### Đọc và tìm kiếm

~~~http
GET /products-read/_doc/p-100
~~~

~~~http
POST /products-read/_search
{
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

Khi read alias trỏ tới nhiều index, Elasticsearch tìm document theo các index thành viên. Với thao tác lấy document theo ID, nếu nhiều index có thể chứa cùng ID thì cần hiểu rõ phạm vi tìm kiếm và tránh thiết kế dữ liệu khiến ID trùng gây kết quả mơ hồ.

### Ghi document

~~~http
POST /products-write/_doc
{
  "title": "Wireless Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Nếu alias có write index hợp lệ, Elasticsearch tạo document tại index đó và sinh ID.

Với ID do ứng dụng cung cấp:

~~~http
PUT /products-write/_doc/p-100
{
  "title": "Wireless Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Các API index, update và delete qua alias đều cần một đích ghi phù hợp. Đừng nhầm is_write_index với thao tác ghi vào mọi index trong alias.

### Alias filter và routing

Alias còn có thể chứa filter hoặc routing để giới hạn document được tìm kiếm hoặc chỉ định shard. Ví dụ read alias cho một nhóm dữ liệu:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
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

Khi search qua active-products, filter alias được áp dụng để giới hạn kết quả theo điều kiện. Filter alias phục vụ các thao tác đọc/search; nó không phải rào chắn bảo mật cho thao tác ghi. Ghi qua alias có filter không có nghĩa Elasticsearch tự kiểm tra document mới có thỏa filter hay không.

Không dùng alias filter để thay thế authorization. Phân quyền truy cập index và dữ liệu nhạy cảm phải được thiết kế bằng security roles và các cơ chế bảo mật thích hợp.

Routing alias có thể hướng thao tác đến shard phù hợp. Khi dùng routing, cần đảm bảo các thao tác index và search nhất quán với routing key đã chọn; nếu không, document có thể không xuất hiện trong truy vấn như mong đợi.

## 6. Thay đổi alias an toàn khi tạo index mới

Một lợi ích lớn của alias là chuyển đổi index mà không cần đổi tên endpoint trong ứng dụng.

Giả sử hệ thống đang chạy:

~~~text
products-read  ---> products-000001
products-write ---> products-000001 (write index)
~~~

Ta muốn chuyển ghi sang products-000002 và cho phép đọc cả dữ liệu cũ lẫn mới:

~~~text
products-read  ---> products-000001
              ---> products-000002

products-write ---> products-000002 (write index)
~~~

Đầu tiên, tạo index mới với mapping tương thích:

~~~http
PUT /products-000002
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Sau đó cập nhật alias trong một request _aliases:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000002",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-000001",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-000001",
        "alias": "products-write",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "products-000002",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Các hành động trong _aliases được áp dụng như một cập nhật metadata nguyên tử. Client không nhìn thấy trạng thái trung gian mà alias đã bị gỡ nhưng chưa được thêm lại. Việc chuyển write target vì thế có thể được thực hiện trong một lần cập nhật.

Tuy nhiên, cập nhật alias không tự copy document từ index cũ sang index mới. Nếu products-000002 chưa có dữ liệu cũ, read alias sau khi cập nhật chỉ tìm được dữ liệu ở index mới và dữ liệu cũ vẫn nằm trong index cũ. Nếu muốn read alias trả đầy đủ lịch sử, cần reindex hoặc một chiến lược dữ liệu tương ứng trước khi chuyển đổi.

### Khi nào nên giữ index cũ trong read alias?

Có thể giữ index cũ trong read alias nếu:

- Index cũ vẫn chứa document cần truy vấn.
- Mapping của index cũ tương thích với index mới.
- Ứng dụng cần đọc lịch sử từ nhiều index.
- Việc giữ dữ liệu cũ đáp ứng chính sách lưu trữ.

Nếu đã reindex toàn bộ dữ liệu sang index mới và xác nhận kết quả, có thể loại index cũ khỏi read alias. Chỉ xóa index cũ sau khi xác nhận không còn nhu cầu truy cập và đã đáp ứng yêu cầu backup/lưu trữ.

## 7. Rollover và write alias

Rollover tạo index mới khi index hiện tại đạt một hoặc nhiều điều kiện, ví dụ tuổi, số document hoặc kích thước shard. Rollover thường được dùng cùng write alias để ứng dụng luôn ghi qua một tên ổn định.

Ví dụ alias events-write hiện trỏ tới index events-000001 với is_write_index: true. Khi index đạt điều kiện, gọi Rollover API:

~~~http
POST /events-write/_rollover/events-000002
{
  "conditions": {
    "max_age": "30d",
    "max_docs": 1000000
  }
}
~~~

Elasticsearch tạo index mới nếu điều kiện được đáp ứng và cập nhật write alias để index mới trở thành write index. Nếu điều kiện chưa đạt, API có thể báo không rollover.

Các điều kiện trong ví dụ chỉ mang tính minh họa. Chọn ngưỡng theo dung lượng shard, tốc độ ghi, thời gian lưu trữ và khả năng truy vấn của cluster.

### Rollover alias và read alias riêng

Nếu hệ thống dùng events-read để đọc nhiều index và events-write để ghi, cần quản lý cả hai alias.

- Rollover API chuyển write alias sang index mới.
- Read alias cần được thêm index mới nếu ứng dụng muốn đọc dữ liệu vừa ghi.
- Nếu read alias cần truy vấn toàn bộ lịch sử, giữ các index cũ trong read alias cho tới khi hết thời gian lưu trữ hoặc dữ liệu đã được chuyển đi.

Đừng giả định việc rollover write alias tự động cập nhật mọi alias khác có liên quan. Kiểm tra metadata sau rollover và cập nhật read alias theo chiến lược của hệ thống.

### Rollover không thay thế reindex

Rollover tạo index mới để tiếp tục nhận ghi. Nó không chuyển toàn bộ document cũ sang index mới. Mỗi index sau rollover có thể giữ một khoảng dữ liệu riêng. Đây là mô hình phù hợp với dữ liệu append-only hoặc dữ liệu theo thời gian, nhưng không tự giải quyết migration mapping của dữ liệu lịch sử.

## 8. Tích hợp read/write alias với Spring Data Elasticsearch

Spring Data Elasticsearch làm việc với index thông qua metadata của entity và IndexCoordinates. Giá trị indexName trong @Document có thể là tên alias thay vì tên index vật lý.

Ví dụ:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String title;
    private String category;
    private Double price;
}
~~~

Nếu products là alias, repository dùng tên alias này cho các thao tác tương ứng. Một alias chung có thể vừa đọc nhiều index vừa ghi vào một write index nếu cấu hình is_write_index đúng.

### Repository với alias chung

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Với entity @Document(indexName = "products"), repository có thể gọi:

~~~java
List<Product> products = productRepository.findByCategory("accessories");
Product saved = productRepository.save(product);
~~~

Nếu products là alias trỏ tới nhiều index, thao tác tìm kiếm đi qua các index thành viên. Thao tác save được định tuyến tới write index. Điều này chỉ hoạt động khi alias có write target hợp lệ.

### Tách read alias và write alias bằng IndexCoordinates

Nếu ứng dụng cần hai alias riêng, một repository với một @Document(indexName = "...") cố định không tự động biết lúc nào phải dùng alias đọc và lúc nào phải dùng alias ghi. Có thể gọi ElasticsearchOperations với IndexCoordinates tường minh:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductStore {

    private final ElasticsearchOperations operations;

    public ProductStore(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-read")
        );
    }

    public Product save(Product product) {
        return operations.save(
            product,
            IndexCoordinates.of("products-write")
        );
    }
}
~~~

IndexCoordinates cho phép chỉ định alias hoặc index ở thời điểm gọi. Query vẫn dùng field mapping của Product, còn đích đọc/ghi được chọn riêng.

Tên method và overload có thể thay đổi theo phiên bản Spring Data Elasticsearch. Khi áp dụng vào dự án, kiểm tra API ElasticsearchOperations của release train đang dùng. Nguyên tắc thiết kế vẫn là truyền read alias cho thao tác đọc và write alias cho thao tác ghi.

### Khi nào dùng repository, khi nào dùng operations?

| Nhu cầu | Cách tiếp cận |
|---|---|
| Một alias chung vừa đọc vừa ghi | @Document(indexName = "alias") và repository |
| Read alias và write alias tách riêng | ElasticsearchOperations với IndexCoordinates tường minh |
| Query theo tên method đơn giản | Repository method |
| Query phức tạp, nhiều index hoặc aggregation | ElasticsearchOperations và query phù hợp |
| Quản lý index, mapping và alias | Quy trình index administration riêng hoặc API Elasticsearch |

Repository tiện cho CRUD và query theo quy ước. ElasticsearchOperations phù hợp khi ứng dụng cần điều khiển rõ index/alias ở từng thao tác.

### Không để repository ghi nhầm vào read alias

Một read alias có thể trỏ tới nhiều index và không có write index. Nếu cấu hình @Document(indexName = "products-read") rồi dùng repository save, thao tác ghi sẽ thất bại nếu alias không có write target.

Đây là lỗi thiết kế thường gặp khi tách read/write alias. Hãy kiểm tra mọi thao tác CRUD của repository: save, delete, findById, search và các custom operation có thể dùng cùng indexName mặc định. Nếu tách alias, dùng operations hoặc cấu trúc repository/configuration phù hợp để từng thao tác dùng đúng alias.

## 9. Alias và mapping phải tương thích

Một read alias có thể trỏ tới nhiều index. Khi đó, các field được dùng chung trong query, sort và aggregation cần có mapping tương thích trên tất cả index.

Ví dụ:

| Index | Mapping của price |
|---|---|
| products-000001 | double |
| products-000002 | double |
| products-000003 | keyword |

Một query sort hoặc aggregation trên price có thể thất bại hoặc không hoạt động như mong muốn vì cùng tên field có kiểu khác nhau.

Các điểm cần kiểm tra trước khi thêm index vào read alias:

- Field names và field types có nhất quán không?
- Analyzer và search analyzer có tương thích không?
- Multi-field như title.keyword có tồn tại trên mọi index không?
- Date format có thống nhất không?
- Field có bật doc values khi cần sort/aggregation không?
- Có index cũ thiếu field mới không?

Nếu mapping khác nhau, có thể dùng field_caps để xem khả năng field trên alias:

~~~http
GET /products-read/_field_caps?fields=title,title.keyword,price
~~~

Field Capabilities API giúp nhận biết field cùng tên có kiểu khác nhau giữa các index. Dựa vào kết quả, quyết định chuẩn hóa mapping, loại index không tương thích khỏi alias hoặc chuyển dữ liệu sang index mới.

## 10. Quản lý alias bằng API và Spring Data

Elasticsearch cung cấp các API chính để quản lý alias:

| API | Mục đích |
|---|---|
| GET /_alias/{name} | Xem index mà alias trỏ tới |
| GET /{index}/_alias | Xem alias của index |
| POST /_aliases | Thêm, xóa hoặc cập nhật nhiều alias trong một request |
| POST /{alias}/_rollover | Tạo index mới và chuyển write alias theo điều kiện |
| GET /_cat/aliases?v | Xem danh sách alias dạng bảng |

POST /_aliases là lựa chọn quan trọng khi cần chuyển đổi alias nguyên tử. Có thể thêm và xóa quan hệ alias trong cùng một request.

Spring Data Elasticsearch cũng có abstraction quản lý index thông qua IndexOperations và các API alias action ở những phiên bản hỗ trợ. Tuy nhiên, thao tác alias thường gắn với quy trình quản trị index, migration và triển khai. Nên gom các thay đổi alias vào một bước triển khai có kiểm soát thay vì để mỗi instance ứng dụng tự ý thay đổi alias khi khởi động.

### Ai nên có quyền thay đổi alias?

Ứng dụng nghiệp vụ thường chỉ cần quyền đọc và ghi document qua alias. Quyền tạo index, xóa index, cập nhật mapping và thay đổi alias nên thuộc về tiến trình triển khai hoặc tài khoản quản trị riêng.

Tách quyền này giúp giảm khả năng một lỗi trong ứng dụng làm chuyển alias sai hoặc xóa nhầm index. Các quyền Elasticsearch nên được cấp theo đúng API và phạm vi index mà từng thành phần cần.

## 11. Kiểm tra trạng thái alias và write index

Khi thao tác ghi qua alias thất bại, hãy xác minh metadata trước khi thay đổi code.

### Xem toàn bộ alias

~~~http
GET /_cat/aliases?v
~~~

Kết quả cho biết alias, index đích và các thông tin liên quan. Để kiểm tra chi tiết hơn:

~~~http
GET /_alias/products-write
~~~

Tìm quan hệ alias tới từng index và giá trị is_write_index.

### Xác nhận write index

Nếu alias có nhiều thành viên, chỉ một thành viên nên có is_write_index: true. Kiểm tra rằng:

- Có đúng một write index.
- Write index đang tồn tại và ở trạng thái phù hợp.
- Alias ứng dụng gọi đúng tên.
- Không có cấu hình ghi qua alias cũ đã bị loại bỏ.
- Các node ứng dụng đã nạp cấu hình mới nếu alias name thay đổi.

### Kiểm tra bằng một thao tác ghi có kiểm soát

Trong môi trường kiểm thử, có thể ghi một document với ID rõ ràng qua write alias:

~~~http
PUT /products-write/_doc/alias-check-001
{
  "title": "Alias verification",
  "category": "internal",
  "price": 1.0
}
~~~

Sau đó xác định document nằm ở index nào bằng Get API hoặc search metadata. Không dùng document thử nghiệm trên production nếu chưa có quy trình dọn dữ liệu phù hợp.

### Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Write request báo không xác định được write index | Alias trỏ tới nhiều index nhưng không có is_write_index: true | Xem alias metadata và chỉ định write target |
| Write request không tìm thấy alias | Alias chưa được tạo hoặc tên sai | GET /_alias/{name} |
| Search trả kết quả thiếu | Read alias chưa bao gồm index cần đọc | Kiểm tra alias membership và dữ liệu |
| Search qua alias lỗi mapping | Các index có field type không tương thích | Dùng _field_caps và kiểm tra mapping |
| Save qua Spring Data thất bại | @Document trỏ tới alias đọc không có write target | Dùng write alias hoặc IndexCoordinates |
| Sau rollover không thấy dữ liệu mới khi đọc | Read alias chưa được thêm index mới | Kiểm tra và cập nhật read alias |
| Thao tác ghi vào index cũ | Write alias chưa chuyển hoặc ứng dụng dùng tên index trực tiếp | Kiểm tra URI/coordinates và alias metadata |
| Alias update báo lỗi | Index không tồn tại, alias trùng tên hoặc action không hợp lệ | Đọc response lỗi và xác nhận trạng thái trước/sau |

## 12. Kịch bản chuyển đổi index không gián đoạn

Giả sử ứng dụng hiện đọc và ghi qua alias catalog. Alias đang trỏ tới catalog-v1, là write index.

Ta muốn tạo catalog-v2 với mapping mới.

Một quy trình có thể thực hiện:

1. Tạo catalog-v2 với mapping mới.
2. Reindex document từ catalog-v1 sang catalog-v2.
3. Đồng bộ các thay đổi ghi phát sinh trong lúc reindex nếu ứng dụng vẫn hoạt động.
4. Kiểm tra document count, mapping, query, sort và aggregation.
5. Dùng một request _aliases để thêm catalog-v2 vào alias và chuyển write index sang v2.
6. Kiểm tra ứng dụng đọc/ghi qua alias sau cutover.
7. Giữ v1 trong thời gian rollback nếu cần.
8. Loại v1 khỏi alias và xóa theo chính sách lưu trữ sau khi xác nhận.

Ví dụ cập nhật alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "catalog-v1",
        "alias": "catalog"
      }
    },
    {
      "add": {
        "index": "catalog-v2",
        "alias": "catalog",
        "is_write_index": true
      }
    }
  ]
}
~~~

Request này thay alias từ v1 sang v2 trong một lần cập nhật metadata. Nếu cần giữ cả hai index để đọc trong giai đoạn chuyển tiếp, hãy thêm v2 mà vẫn giữ v1 trong alias, đồng thời chỉ đặt v2 là write index.

### Rollback

Nếu phát hiện lỗi sau cutover, có thể chuyển write index về v1 bằng một cập nhật alias khác, miễn là v1 vẫn tồn tại và mapping/ứng dụng tương thích.

Tuy nhiên, nếu đã có document mới được ghi vào v2 sau cutover, chuyển alias về v1 không tự chuyển các document đó trở lại. Cần xác định chiến lược đồng bộ dữ liệu trước khi rollback. Alias switch chỉ đổi định tuyến; nó không sao chép hoặc hợp nhất dữ liệu.

## 13. Những nguyên tắc cần giữ

- Dùng read alias để ứng dụng truy vấn một hoặc nhiều index mà không phụ thuộc tên vật lý.
- Dùng write alias để định tuyến ghi tới index hiện hành.
- Khi alias trỏ tới nhiều index, đặt đúng một is_write_index: true nếu cần ghi qua alias.
- Nếu alias chỉ trỏ tới một index, index đó mặc định là write index trừ khi cấu hình khác.
- Không coi is_write_index là cơ chế phân quyền hoặc mapping.
- Dùng _aliases để thay đổi nhiều quan hệ alias nguyên tử.
- Đảm bảo mapping tương thích giữa các index đứng sau read alias.
- Sau rollover, kiểm tra read alias có bao gồm index mới hay không.
- Khi tách read/write alias trong Spring Data, truyền IndexCoordinates phù hợp cho từng thao tác hoặc tổ chức repository rõ ràng.
- Không để ứng dụng nghiệp vụ tự ý quản trị alias nếu nó chỉ cần đọc và ghi document.
- Nhớ rằng alias switch không reindex, không copy dữ liệu và không tự giải quyết rollback dữ liệu.

Alias cung cấp một tên ổn định để ứng dụng làm việc với index qua nhiều giai đoạn vòng đời. Read alias xác định phạm vi đọc, write alias xác định đích ghi và is_write_index làm rõ index nhận dữ liệu khi alias có nhiều thành viên. Khi kết hợp đúng ba khái niệm này với mapping nhất quán và quy trình chuyển đổi có kiểm soát, hệ thống có thể mở rộng và thay index mà không buộc ứng dụng phụ thuộc vào tên index vật lý.

