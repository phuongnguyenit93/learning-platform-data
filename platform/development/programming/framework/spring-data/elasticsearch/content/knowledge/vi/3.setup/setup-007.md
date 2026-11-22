# Kiểm tra index, mapping và dữ liệu bằng API Elasticsearch

Elasticsearch cung cấp REST API để quan sát trạng thái cluster, kiểm tra index, đọc mapping và truy vấn document. Khi một ứng dụng Spring Data Elasticsearch không tìm thấy dữ liệu hoặc trả về kết quả khác mong đợi, các API này giúp xác định vấn đề nằm ở index, cấu trúc field hay dữ liệu đã được ghi vào Elasticsearch.

Ba khái niệm cần phân biệt:

- **Index** là nơi Elasticsearch lưu một tập document có liên quan. Có thể hình dung index gần giống một bảng trong cơ sở dữ liệu quan hệ, nhưng cách lưu trữ và truy vấn khác nhau.
- **Mapping** mô tả kiểu dữ liệu và cách Elasticsearch xử lý từng field, chẳng hạn `text`, `keyword`, `date`, `long` hoặc `nested`.
- **Document** là một bản ghi JSON được lưu trong index. Mỗi document có một `_id` và nội dung thường được trả về trong `_source`.

Các lệnh trong bài tập trung vào việc đọc và kiểm tra dữ liệu. Bạn có thể chạy chúng trong Kibana **Dev Tools → Console**, hoặc gửi HTTP request bằng curl, Postman hay một REST client khác.

## 1. Chuẩn bị địa chỉ Elasticsearch

Một Elasticsearch node trong môi trường phát triển thường được truy cập qua một địa chỉ như:

```text
http://localhost:9200
```

Đây chỉ là địa chỉ minh họa. Hãy dùng đúng host, port và giao thức mà môi trường của bạn cấu hình. Elasticsearch ở môi trường triển khai có thể yêu cầu HTTPS, tài khoản, mật khẩu, API key hoặc chứng chỉ TLS.

Trong Kibana Dev Tools, nhập trực tiếp request theo cú pháp:

```http
GET /
```

Trong terminal, có thể khai báo địa chỉ và thông tin xác thực bằng biến môi trường rồi gọi API. Ví dụ dưới đây minh họa cách gọi bằng curl; thay các giá trị mẫu bằng cấu hình của môi trường:

```bash
export ES_URL="http://localhost:9200"
export ES_USERNAME="elastic"
export ES_PASSWORD="your-password"

curl --user "$ES_USERNAME:$ES_PASSWORD" "$ES_URL/"
```

Trên Windows PowerShell, dùng `curl.exe` để gọi chương trình curl thay vì alias `curl` có thể trỏ tới `Invoke-WebRequest`:

```powershell
$env:ES_URL = "http://localhost:9200"
$env:ES_USERNAME = "elastic"
$env:ES_PASSWORD = "your-password"

curl.exe --user "$($env:ES_USERNAME):$($env:ES_PASSWORD)" "$($env:ES_URL)/"
```

Không ghi mật khẩu thật vào source code, file cấu hình được commit hoặc lịch sử lệnh dùng chung. Nếu cluster dùng HTTPS với CA riêng, hãy cấu hình curl tin cậy CA đó bằng tùy chọn `--cacert`. Chỉ trong môi trường local tạm thời mới cân nhắc bỏ qua xác minh chứng chỉ; không biến cách làm đó thành cấu hình triển khai.

Request `GET /` trả về thông tin cơ bản của node/cluster, thường gồm tên node, tên cluster, phiên bản Elasticsearch và một số thông tin build. Đây là bước đầu để xác nhận bạn đang kết nối đúng máy chủ và biết phiên bản đang chạy.

## 2. Kiểm tra trạng thái cluster và danh sách index

### 2.1. Xem sức khỏe cluster

Gửi request:

```http
GET /_cluster/health?pretty
```

Một response rút gọn có thể trông như sau:

```json
{
  "cluster_name": "elasticsearch",
  "status": "green",
  "number_of_nodes": 1,
  "active_primary_shards": 3,
  "active_shards": 3,
  "unassigned_shards": 0
}
```

Các trường thường cần chú ý:

| Trường | Ý nghĩa |
|---|---|
| `status` | Trạng thái sức khỏe tổng thể: `green`, `yellow` hoặc `red`. |
| `number_of_nodes` | Số node hiện có trong cluster. |
| `active_primary_shards` | Số primary shard đang hoạt động. |
| `active_shards` | Tổng số shard đang hoạt động, gồm primary và replica. |
| `unassigned_shards` | Số shard chưa được phân bổ cho node. |

Ý nghĩa của ba trạng thái:

- **green**: tất cả primary shard và replica shard cần thiết đều được phân bổ.
- **yellow**: primary shard đã được phân bổ nhưng có ít nhất một replica shard chưa được phân bổ. Dữ liệu vẫn có thể đọc và ghi, nhưng mức dự phòng chưa đầy đủ.
- **red**: có ít nhất một primary shard chưa được phân bổ. Một phần dữ liệu có thể không truy cập được.

Cluster một node thường không thể phân bổ replica sang node thứ hai. Vì vậy trạng thái `yellow` trong môi trường local một node có thể là tình huống dự kiến, không đồng nghĩa index bị hỏng. Hãy xem thêm số node, shard và cấu hình replica trước khi kết luận.

### 2.2. Liệt kê index

Dùng CAT Indices API:

```http
GET /_cat/indices?v&s=index
```

Kết quả dạng bảng giúp quan sát nhanh tên index, trạng thái, số primary shard, số replica, số document và dung lượng:

```text
health status index    uuid                   pri rep docs.count store.size
green  open   products AbCdEf1234567890        1   0   125        48kb
```

Một số cột quan trọng:

- `health`: trạng thái của index.
- `status`: trạng thái mở hoặc đóng của index.
- `index`: tên index.
- `pri`: số primary shard.
- `rep`: số replica shard được cấu hình.
- `docs.count`: số document được thống kê trong index.
- `store.size`: dung lượng lưu trữ của index.

Có thể lọc để xem một index cụ thể:

```http
GET /_cat/indices/products?v
```

CAT API được thiết kế để con người đọc kết quả trong quá trình vận hành và kiểm tra. Khi viết chương trình cần xử lý dữ liệu có cấu trúc, hãy ưu tiên các API chuyên biệt thay vì phụ thuộc vào định dạng bảng CAT.

### 2.3. Kiểm tra một index có tồn tại hay không

Dùng HEAD request:

```http
HEAD /products
```

Thông thường:

- HTTP `200`: index tồn tại.
- HTTP `404`: index không tồn tại hoặc tên được yêu cầu không phân giải được thành index.

Nếu muốn xem metadata của index, dùng:

```http
GET /products?pretty
```

Response cung cấp metadata của index, trong đó có settings và mappings. Ta sẽ đọc mapping riêng ở phần tiếp theo để tập trung vào cấu trúc field.

Tên index Elasticsearch phải viết thường. Nếu ứng dụng khai báo `products` nhưng request lại kiểm tra `Products`, bạn có thể đang kiểm tra nhầm tên. Ngoài index trực tiếp, một tên được ứng dụng sử dụng cũng có thể là alias. Để kiểm tra alias:

```http
GET /_cat/aliases?v
```

Alias là tên tham chiếu tới một hoặc nhiều index. Vì vậy cần xác nhận ứng dụng đang trỏ tới index thật hay alias trước khi kết luận dữ liệu nằm sai nơi.

### 2.4. Kiểm tra shard khi index có vấn đề

Nếu index có trạng thái bất thường, xem shard của index:

```http
GET /_cat/shards/products?v
```

Mỗi dòng biểu diễn một shard và trạng thái phân bổ của nó. Thông tin này giúp xác định primary hoặc replica nào đang hoạt động, shard nào chưa được phân bổ và node nào đang giữ shard. Trong môi trường phát triển một node, số replica lớn hơn khả năng phân bổ có thể khiến index ở trạng thái yellow.

## 3. Đọc mapping để kiểm tra cấu trúc field

Mapping cho biết Elasticsearch hiểu mỗi field trong document như thế nào. Đây là thông tin quan trọng khi truy vấn không trả về kết quả dù document đã tồn tại.

Gửi request:

```http
GET /products/_mapping?pretty
```

Response rút gọn:

```json
{
  "products": {
    "mappings": {
      "properties": {
        "id": {
          "type": "keyword"
        },
        "name": {
          "type": "text"
        },
        "price": {
          "type": "double"
        },
        "quantity": {
          "type": "integer"
        },
        "createdAt": {
          "type": "date"
        },
        "active": {
          "type": "boolean"
        }
      }
    }
  }
}
```

Trong ví dụ này, Elasticsearch lưu `name` dưới dạng `text`, còn `id` là `keyword`. Hai kiểu này có mục đích khác nhau:

| Kiểu | Cách sử dụng thường gặp |
|---|---|
| `text` | Nội dung cần phân tích thành token để tìm kiếm toàn văn, ví dụ tên hoặc mô tả. |
| `keyword` | Giá trị nguyên vẹn dùng để lọc chính xác, sắp xếp hoặc aggregation, ví dụ mã sản phẩm, trạng thái, email. |
| `integer`, `long`, `short`, `byte` | Số nguyên. |
| `float`, `double`, `scaled_float` | Số có phần thập phân. |
| `boolean` | Giá trị đúng/sai. |
| `date` | Ngày giờ theo định dạng Elasticsearch hỗ trợ hoặc định dạng được khai báo. |
| `object` | Một đối tượng JSON chứa các field con. |
| `nested` | Mảng đối tượng cần giữ quan hệ giữa các field trong cùng một phần tử khi truy vấn. |

### 3.1. Phân biệt text và keyword

Giả sử mapping có:

```json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
```

Elasticsearch có thể phân tích `name` thành token để tìm kiếm toàn văn. Field phụ `name.keyword` lưu giá trị nguyên vẹn để so khớp chính xác, sắp xếp hoặc aggregation.

Ví dụ:

```http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
```

`match` phù hợp với field `text` vì giá trị truy vấn được phân tích theo analyzer của field.

Để tìm giá trị chính xác trên field `keyword`:

```http
POST /products/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mouse"
    }
  }
}
```

`term` so sánh giá trị chính xác và không phân tích chuỗi như `match`. Nếu mapping chỉ có `name: text` mà không có field phụ `name.keyword`, truy vấn trên `name.keyword` sẽ không hoạt động như mong đợi. Hãy kiểm tra mapping thực tế trước khi chọn field và loại query.

### 3.2. Kiểm tra settings của index

Mapping mô tả field; settings mô tả cấu hình index như số shard, replica và các thiết lập liên quan đến analyzer:

```http
GET /products/_settings?pretty
```

Ví dụ một phần response:

```json
{
  "products": {
    "settings": {
      "index": {
        "number_of_shards": "1",
        "number_of_replicas": "0"
      }
    }
  }
}
```

Khi kiểm tra index, đừng nhầm `number_of_shards` với `number_of_replicas`: primary shard chia dữ liệu thành các phần; replica shard là bản sao phục vụ khả năng chịu lỗi và một số hoạt động đọc. Số replica không quyết định số document mà ứng dụng có thể lưu.

### 3.3. Kiểm tra kiểu của một field cụ thể

Khi mapping lớn, có thể yêu cầu Elasticsearch trả về mapping của một field:

```http
GET /products/_mapping/field/price
```

Hoặc kiểm tra khả năng và kiểu field trên nhiều index:

```http
GET /products,archived-products/_field_caps?fields=name,price,status
```

Field Capabilities API hữu ích khi cùng một field name xuất hiện ở nhiều index nhưng có thể được khai báo với kiểu khác nhau. Ví dụ, `price` là `double` trong index cũ nhưng lại là `keyword` trong index mới. Sự không đồng nhất này có thể làm truy vấn trên nhiều index gặp lỗi hoặc cho kết quả khó hiểu.

### 3.4. Mapping thay đổi như thế nào?

Mapping hiện có không thể tùy ý đổi kiểu của một field đã được tạo. Ví dụ, nếu `price` đang là `keyword`, bạn không thể đổi trực tiếp nó thành `double` bằng cách gửi một mapping mới.

Thông thường có hai hướng xử lý:

1. Thêm field mới với kiểu phù hợp nếu cấu trúc hiện tại cho phép.
2. Tạo index mới với mapping đúng, chuyển dữ liệu sang bằng reindex hoặc quy trình migrate phù hợp, sau đó chuyển alias/ứng dụng sang index mới.

Không gửi lệnh thay đổi mapping hoặc reindex chỉ để kiểm tra. Trước khi thực hiện thay đổi cấu trúc, cần xác định dữ liệu hiện có, kế hoạch chuyển đổi và ảnh hưởng tới ứng dụng.

## 4. Kiểm tra document và dữ liệu đã lưu

Sau khi xác nhận index tồn tại và mapping hợp lý, hãy kiểm tra document cụ thể.

### 4.1. Lấy document theo ID

Dùng Get API:

```http
GET /products/_doc/1001?pretty
```

Response minh họa:

```json
{
  "_index": "products",
  "_id": "1001",
  "_version": 1,
  "found": true,
  "_source": {
    "id": "1001",
    "name": "Wireless Mouse",
    "price": 29.9,
    "quantity": 15,
    "active": true
  }
}
```

Các trường cần đọc:

- `_index`: index chứa document.
- `_id`: định danh document trong index.
- `_version`: phiên bản nội bộ của document, có thể tăng khi document được cập nhật.
- `found`: cho biết document có được tìm thấy hay không.
- `_source`: nội dung JSON được lưu cho document, nếu source được bật và không bị loại trừ.

Nếu document không tồn tại, API trả về HTTP `404`. Hãy kiểm tra lại cả index và ID. ID mà Spring Data Elasticsearch sử dụng có thể đến từ thuộc tính được đánh dấu `@Id`, vì vậy giá trị ID trong Java cần khớp với ID bạn đang tra cứu.

### 4.2. Đếm document trong index

Dùng Count API:

```http
GET /products/_count?pretty
```

Response:

```json
{
  "count": 125,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  }
}
```

Có thể đếm theo điều kiện. Ví dụ đếm sản phẩm đang hoạt động:

```http
POST /products/_count
{
  "query": {
    "term": {
      "active": true
    }
  }
}
```

Count API cho biết số document khớp query. Nếu kết quả bằng 0, hãy thử đếm toàn index trước, sau đó kiểm tra kiểu field và điều kiện lọc.

### 4.3. Tìm kiếm document bằng Search API

Để xem một số document trong index:

```http
POST /products/_search
{
  "query": {
    "match_all": {}
  },
  "size": 10
}
```

Dùng `POST` ở đây vì request có JSON body. Search API là thao tác truy vấn; việc dùng HTTP POST không có nghĩa request sẽ tạo hoặc cập nhật document.

Response thường có cấu trúc:

```json
{
  "took": 3,
  "timed_out": false,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 125,
      "relation": "eq"
    },
    "max_score": 1.0,
    "hits": [
      {
        "_index": "products",
        "_id": "1001",
        "_score": 1.0,
        "_source": {
          "id": "1001",
          "name": "Wireless Mouse",
          "price": 29.9
        }
      }
    ]
  }
}
```

Các trường quan trọng:

- `took`: thời gian Elasticsearch xử lý request, tính bằng mili giây.
- `timed_out`: request có bị timeout hay không.
- `_shards.failed`: số shard truy vấn thất bại.
- `hits.total.value`: số kết quả được báo cáo; xem thêm `relation` để biết số lượng là chính xác (`eq`) hay cận dưới (`gte`).
- `hits.hits`: các document được trả về trong trang kết quả.
- `_score`: điểm liên quan của document đối với truy vấn, thường có ý nghĩa với tìm kiếm toàn văn.
- `_source`: dữ liệu document được trả về.

Tham số `size` giới hạn số document trong `hits.hits`; nó không làm thay đổi tổng số kết quả khớp. Vì vậy `size: 10` có thể đi cùng `hits.total.value: 125`.

### 4.4. Lọc theo điều kiện

Ví dụ tìm sản phẩm có tên liên quan đến từ `mouse`:

```http
POST /products/_search
{
  "query": {
    "match": {
      "name": "mouse"
    }
  }
}
```

Tìm mã sản phẩm chính xác:

```http
POST /products/_search
{
  "query": {
    "term": {
      "id": "1001"
    }
  }
}
```

Lọc sản phẩm có giá trong một khoảng:

```http
POST /products/_search
{
  "query": {
    "range": {
      "price": {
        "gte": 10,
        "lte": 50
      }
    }
  }
}
```

Kết hợp nhiều điều kiện:

```http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "price": {
              "lte": 50
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "size": 20
}
```

Trong `bool` query:

- `must` yêu cầu điều kiện phải khớp và thường tham gia tính điểm liên quan.
- `filter` yêu cầu điều kiện phải khớp nhưng không tính điểm liên quan; phù hợp với điều kiện lọc như trạng thái, khoảng giá hoặc ngày.
- `should` biểu diễn điều kiện nên khớp, tùy cấu hình `minimum_should_match`.
- `must_not` loại bỏ document khớp điều kiện.

Kiểu field vẫn quyết định cách query hoạt động. Dùng `match` cho tìm kiếm toàn văn trên `text`; dùng `term` cho giá trị chính xác trên `keyword`, boolean hoặc field số phù hợp. Với field ngày, dùng `range` và định dạng ngày tương thích mapping.

### 4.5. Giới hạn field trả về và sắp xếp

Khi chỉ cần một vài field, có thể giới hạn nội dung `_source`:

```http
POST /products/_search
{
  "_source": ["name", "price", "active"],
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "price": {
        "order": "desc"
      }
    }
  ],
  "size": 5
}
```

Nếu `_source` bị tắt hoặc một số field bị loại trừ trong cấu hình, response có thể không chứa nội dung bạn mong đợi dù document vẫn tồn tại. Khi đó hãy kiểm tra mapping và cấu hình lưu source.

## 5. Liên hệ mapping Elasticsearch với Spring Data Elasticsearch

Trong ứng dụng Spring Data Elasticsearch, entity thường khai báo index và kiểu field bằng annotation. Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // constructors, getters and setters
}
```

Các annotation giúp Spring Data Elasticsearch ánh xạ thuộc tính Java sang cấu trúc document và mapping. Tuy nhiên, điều cần kiểm tra là mapping thực tế đang tồn tại trên Elasticsearch. Entity trong source code có thể đã thay đổi sau khi index được tạo; thay đổi annotation không tự động chứng minh rằng mapping trên cluster đã được cập nhật tương ứng.

Nếu ứng dụng dùng `ElasticsearchOperations`, có thể đọc một số metadata qua API Spring Data:

```java
IndexOperations indexOps = operations.indexOps(Product.class);

boolean exists = indexOps.exists();

if (exists) {
    Map<String, Object> mapping = indexOps.getMapping();
    Map<String, Object> settings = indexOps.getSettings();
}
```

Đoạn code minh họa việc kiểm tra từ phía ứng dụng; cần có bean `ElasticsearchOperations` và import phù hợp trong project. Khi cần xác minh request REST, response nguyên bản hoặc cấu hình cluster, gọi REST API trực tiếp vẫn giúp quan sát rõ Elasticsearch đang trả về điều gì.

Repository cũng cung cấp các thao tác ở mức ứng dụng, ví dụ `count()`, `findById(id)` hoặc các phương thức tìm kiếm đã khai báo. Hãy phân biệt:

- REST API giúp kiểm tra trạng thái và dữ liệu trực tiếp trên Elasticsearch.
- Spring Data repository/operations giúp ứng dụng thao tác với Elasticsearch qua abstraction của Spring.
- Entity annotation mô tả cách ứng dụng dự kiến ánh xạ dữ liệu.

Khi kết quả từ repository khác kết quả REST API, hãy đối chiếu index name hoặc alias, ID, mapping, query được sinh ra, bộ lọc và thời điểm refresh.

## 6. Quy trình kiểm tra khi ứng dụng không tìm thấy dữ liệu

Giả sử ứng dụng lưu sản phẩm nhưng API tìm kiếm trả về danh sách rỗng. Có thể kiểm tra theo thứ tự sau:

**Bước 1 — Xác nhận đang kết nối đúng cluster**

```http
GET /
GET /_cluster/health?pretty
```

Đối chiếu tên cluster, phiên bản và trạng thái. Nếu không kết nối được, kiểm tra URL, port, giao thức, thông tin xác thực, TLS và quyền truy cập.

**Bước 2 — Xác nhận index hoặc alias tồn tại**

```http
GET /_cat/indices?v&s=index
GET /_cat/aliases?v
HEAD /products
```

Đảm bảo tên index/alias đúng với `indexName` trong entity hoặc cấu hình ứng dụng.

**Bước 3 — Kiểm tra mapping thực tế**

```http
GET /products/_mapping?pretty
GET /products/_settings?pretty
```

Xác nhận tên field, kiểu dữ liệu, field phụ như `.keyword`, analyzer và định dạng ngày. Đặc biệt chú ý sự khác nhau giữa kiểu Java và kiểu Elasticsearch được tạo ra.

**Bước 4 — Kiểm tra document đã được ghi hay chưa**

```http
GET /products/_count?pretty
GET /products/_doc/1001?pretty
```

Nếu count bằng 0 hoặc ID không tồn tại, xem lại luồng lưu dữ liệu, index đích và giá trị ID.

**Bước 5 — Thử truy vấn đơn giản trước**

```http
POST /products/_search
{
  "query": {
    "match_all": {}
  },
  "size": 5
}
```

Nếu `match_all` có kết quả nhưng query của ứng dụng không có, tập trung kiểm tra query, kiểu field, analyzer, điều kiện lọc, sort và phân trang.

**Bước 6 — So sánh với thời điểm ghi dữ liệu**

Elasticsearch sử dụng cơ chế near-real-time cho tìm kiếm. Document vừa được index có thể chưa xuất hiện ngay trong Search API cho đến lần refresh tiếp theo. Get API theo ID thường có thể đọc document mới ngay sau khi ghi, trong khi Search API phụ thuộc refresh. Nếu Get API thấy document nhưng Search API chưa thấy ngay, hãy kiểm tra thời điểm refresh trước khi kết luận dữ liệu bị mất.

Trong ứng dụng thông thường, không nên ép refresh sau mọi lần ghi vì refresh liên tục làm giảm hiệu năng. Hãy dùng chiến lược refresh phù hợp với yêu cầu nhất quán và tải của hệ thống.

## 7. Một số lỗi thường gặp và hướng kiểm tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| HTTP `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực. | Kiểm tra authentication, API key và cấu hình client. |
| HTTP `403 Forbidden` | Tài khoản đã xác thực nhưng thiếu quyền. | Kiểm tra quyền đọc cluster/index và quyền gọi API. |
| HTTP `404 Not Found` | Sai tên index, alias hoặc document ID. | Liệt kê index/alias, sau đó kiểm tra ID. |
| Index ở trạng thái `yellow` | Replica shard chưa được phân bổ. | Xem số node, replica và CAT Shards; môi trường một node thường gặp trường hợp này. |
| Index ở trạng thái `red` | Có primary shard chưa hoạt động. | Kiểm tra shard allocation và log cluster; một phần dữ liệu có thể không truy cập được. |
| Count lớn hơn 0 nhưng query không có kết quả | Query không khớp kiểu field hoặc giá trị. | Thử `match_all`, đọc mapping, rồi kiểm tra `match`/ `term` và điều kiện lọc. |
| `term` không tìm thấy chuỗi | Đang truy vấn field `text` hoặc giá trị không trùng chính xác. | Kiểm tra field `keyword`, analyzer và giá trị đã lưu. |
| Sort hoặc range báo lỗi kiểu dữ liệu | Field có kiểu không phù hợp hoặc khác kiểu giữa các index. | Đọc mapping và dùng Field Capabilities API. |
| Get theo ID có dữ liệu nhưng Search chưa thấy | Search chưa nhìn thấy thay đổi do refresh. | Kiểm tra thời điểm refresh và cấu hình refresh. |
| `_source` thiếu field | Source bị tắt hoặc field bị loại trừ. | Kiểm tra mapping và cấu hình source. |
| Có document nhưng ứng dụng đọc index khác | Entity, alias hoặc cấu hình index name không đồng nhất. | Đối chiếu `@Document(indexName = ...)`, alias và request thực tế. |

Khi gặp lỗi, hãy đọc cả HTTP status và response body. Elasticsearch thường trả về object `error` có loại lỗi, lý do và thông tin index/shard liên quan. Không nên chỉ dựa vào thông báo rút gọn ở phía ứng dụng.

## 8. Lưu ý khi kiểm tra dữ liệu trên môi trường thật

Các request `GET`, `HEAD` và các truy vấn Search/Count trong bài là các thao tác đọc. Dù vậy, hãy giới hạn phạm vi truy vấn khi index lớn: đặt `size` hợp lý, chỉ lấy field cần thiết và tránh quét dữ liệu không cần thiết.

Không chạy các API ghi hoặc xóa như `PUT` tạo/cập nhật index, `DELETE` xóa index, `_bulk` ghi hàng loạt hay `_delete_by_query` trong lúc chỉ muốn kiểm tra. Một số request dùng HTTP POST như `_search` và `_count` vẫn là truy vấn đọc; cần phân biệt theo endpoint và nội dung API, không chỉ theo HTTP method.

Không đưa mật khẩu, API key hoặc dữ liệu nhạy cảm vào ảnh chụp Dev Tools, log, tài liệu chia sẻ hay kết quả kiểm tra công khai. Với môi trường production, hãy dùng tài khoản có quyền đọc tối thiểu cần thiết và tuân thủ quy trình truy cập của hệ thống.

## 9. Bảng tra cứu nhanh các API

| Mục đích | Request |
|---|---|
| Thông tin node/cluster | `GET /` |
| Sức khỏe cluster | `GET /_cluster/health?pretty` |
| Liệt kê index | `GET /_cat/indices?v` |
| Kiểm tra index tồn tại | `HEAD /products` |
| Xem metadata index | `GET /products?pretty` |
| Xem shard | `GET /_cat/shards/products?v` |
| Xem alias | `GET /_cat/aliases?v` |
| Xem mapping | `GET /products/_mapping?pretty` |
| Xem mapping của field | `GET /products/_mapping/field/price` |
| Xem settings | `GET /products/_settings?pretty` |
| Kiểm tra kiểu field trên nhiều index | `GET /products,archived-products/_field_caps?fields=name,price` |
| Lấy document theo ID | `GET /products/_doc/1001?pretty` |
| Đếm document | `GET /products/_count?pretty` |
| Tìm kiếm document | `POST /products/_search` |

Thay `products`, `archived-products` và `1001` bằng tên index, alias và ID thực tế của ứng dụng.

Khi debug Spring Data Elasticsearch, thứ tự kiểm tra hiệu quả là: xác nhận cluster → xác nhận index/alias → đọc mapping/settings → kiểm tra document/count → chạy `match_all` → kiểm tra query cụ thể. Làm theo thứ tự này giúp khoanh vùng lỗi dựa trên response thực tế của Elasticsearch, đồng thời tránh thay đổi dữ liệu trong lúc điều tra.

