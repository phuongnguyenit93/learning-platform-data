# Tái tạo index khi thay đổi kiểu trường hoặc analyzer

Trong Elasticsearch, mapping và analyzer quyết định cách document được lưu trong inverted index, cách field được so khớp, sắp xếp và tổng hợp. Khi một field đã có dữ liệu mà cần đổi kiểu, đổi cách token hóa hoặc thay cấu trúc dữ liệu, chỉ sửa annotation trong entity hay gọi API cập nhật mapping thường không đủ. Dữ liệu đã index không tự được đọc lại và xây dựng theo quy tắc mới.

Cách triển khai an toàn cho thay đổi không tương thích thường là tạo một index vật lý mới với settings và mapping mới, nạp lại dữ liệu, đối soát kết quả rồi chuyển alias sang index mới. Quy trình này thường được gọi là reindex hoặc index migration.

Ví dụ, ứng dụng đang dùng `products-v1` với field `name` kiểu `text` và analyzer cũ. Yêu cầu mới cần đổi `name` sang `keyword` để exact match, hoặc dùng analyzer tùy chỉnh để bỏ dấu và chuẩn hóa từ. Index hiện tại đã chứa các term được tạo theo analyzer cũ. Tạo index `products-v2` và reindex sẽ giúp dữ liệu được phân tích lại theo mapping mới.

Bài này tập trung vào thay đổi field type và analyzer, cách tái tạo index bằng Elasticsearch, tích hợp quy trình với Spring Data Elasticsearch, cutover bằng alias và bảo đảm có thể quay lại khi migration gặp sự cố.

## 1. Vì sao thay đổi mapping có thể cần tái tạo index?

Elasticsearch không lưu document như một bảng quan hệ đơn giản. Khi nhận document, nó dùng mapping để quyết định cách lưu từng field và dùng analyzer để chuyển text thành token trong inverted index.

Ví dụ document:

```json
{
  "product_id": "P-100",
  "name": "Mechanical Keyboard",
  "price": 2500000,
  "active": true
}
```

Mapping có thể khai báo:

```json
{
  "properties": {
    "product_id": { "type": "keyword" },
    "name": { "type": "text", "analyzer": "standard" },
    "price": { "type": "long" },
    "active": { "type": "boolean" }
  }
}
```

Với field `name` kiểu `text`, analyzer xử lý chuỗi thành token phục vụ full-text search. Field `price` được lưu theo kiểu số để range query và sort. Field `product_id` là `keyword` để so khớp chính xác.

Nếu mapping thay đổi, Elasticsearch không tự lấy lại mọi document source rồi lập chỉ mục theo quy tắc mới. Mapping hiện tại mô tả cách dữ liệu đã được index; nó không phải một schema migration tự động chạy lại trên toàn bộ document.

### 1.1. Những thay đổi thường cần index mới

| Thay đổi | Vì sao thường cần tái tạo/reindex |
|---|---|
| `text` sang `keyword` hoặc ngược lại | Cách lưu và truy vấn term khác nhau; field hiện hữu không thể đổi type trực tiếp. |
| `long` sang `date`, `double` sang `keyword` | Giá trị đã index theo kiểu cũ; mapping type xung đột. |
| `object` sang `nested` | Cấu trúc index và semantics truy vấn thay đổi. |
| Đổi index-time analyzer | Token đã lưu trong inverted index được tạo theo analyzer cũ. |
| Đổi tokenizer hoặc token filter | Cần phân tích lại text để sinh term mới. |
| Thay cách denormalize document | Source document cần được dựng lại theo cấu trúc mới. |
| Thay routing hoặc cách tạo ID | Cần chuyển document theo quy tắc định tuyến/định danh mới. |
| Thay cấu hình index không thể cập nhật khi index đang chạy | Tạo index version mới thường an toàn và dễ kiểm soát hơn. |

Không phải mọi thay đổi mapping đều cần tạo index mới. Có thể thêm field mới hoặc cập nhật một số thuộc tính được Elasticsearch cho phép. Tuy nhiên, thêm field vào mapping không có nghĩa các document cũ đã có giá trị được index cho field đó. Nếu cần field mới có dữ liệu trên toàn bộ document cũ, vẫn phải chạy update-by-query hoặc reindex để backfill.

### 1.2. Mapping hiện có không thể đổi type tùy ý

Ví dụ index đang có:

```json
{
  "properties": {
    "price": { "type": "long" }
  }
}
```

Không thể gửi mapping mới để đổi trực tiếp thành:

```json
{
  "properties": {
    "price": { "type": "scaled_float", "scaling_factor": 100 }
  }
}
```

Elasticsearch sẽ từ chối thay đổi xung đột. Cách thông thường là tạo index mới với type mong muốn rồi nạp document vào index đó.

### 1.3. Thêm multi-field cũng không tự backfill document cũ

Có thể bổ sung subfield cho một field text, ví dụ thêm `name.keyword` để sort hoặc exact match:

```http
PUT /products-v1/_mapping
Content-Type: application/json

{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": { "type": "keyword" }
      }
    }
  }
}
```

Mapping mới có thể được chấp nhận, nhưng các document đã index trước đó chưa tự có giá trị trong subfield mới. Cần chạy update-by-query để lập chỉ mục lại các document hoặc reindex sang index mới. Nếu migration còn thay đổi nhiều field/analyzer, tạo index version mới thường dễ kiểm soát hơn.

## 2. Analyzer ảnh hưởng đến dữ liệu đã index như thế nào?

Analyzer thường gồm ba phần:

1. **Character filters:** biến đổi chuỗi đầu vào trước khi tokenization, ví dụ thay ký tự hoặc chuẩn hóa ký tự.
2. **Tokenizer:** tách chuỗi thành token.
3. **Token filters:** biến đổi token, ví dụ lowercase, asciifolding, stemming hoặc synonym.

Ví dụ analyzer tùy chỉnh:

```json
{
  "analysis": {
    "analyzer": {
      "product_name_v2": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
```

Chuỗi `"Máy Tính Xách Tay"` có thể được chuẩn hóa thành các token chữ thường và bỏ dấu tùy analyzer. Điều này ảnh hưởng trực tiếp đến kết quả full-text search.

### 2.1. Index analyzer và search analyzer

Cần phân biệt hai thời điểm:

- **Index analyzer:** chạy khi document được index/update, tạo token lưu trong inverted index.
- **Search analyzer:** chạy khi query text được phân tích trước khi tìm term.

Nếu thay đổi index analyzer, các term đã lưu không được tái tạo chỉ bằng cách sửa query. Cần index lại document để sinh token mới.

Một số cấu hình phía search analyzer có thể được cập nhật theo giới hạn mapping/settings và phiên bản Elasticsearch. Việc thay đổi search analyzer chỉ ảnh hưởng cách phân tích query ở thời điểm tìm kiếm; nó không tái phân tích token đã lưu. Nếu yêu cầu là đổi cách token hóa dữ liệu đã index, cần reindex.

### 2.2. Thay đổi analyzer không chỉ là sửa tên trong annotation

Giả sử entity khai báo:

```java
@Field(type = FieldType.Text, analyzer = "standard")
private String name;
```

Đổi thành:

```java
@Field(type = FieldType.Text, analyzer = "product_name_v2")
private String name;
```

Annotation mới chỉ mô tả mapping mà Spring Data dùng khi tạo index mới hoặc mapping tương ứng. Nếu index vật lý đã tồn tại với mapping cũ, thay đổi code không tự làm dữ liệu cũ được index lại.

Cần bảo đảm analyzer mới đã được khai báo trong index settings trước khi tạo mapping sử dụng analyzer đó.

### 2.3. Kiểm tra analyzer bằng Analyze API

Trước khi chạy migration lớn, kiểm tra token thực tế:

```http
POST /products-v2/_analyze
Content-Type: application/json

{
  "analyzer": "product_name_v2",
  "text": "Máy Tính Xách Tay"
}
```

Đọc token trả về để xác nhận lowercase, folding, tokenizer và token filter hoạt động đúng. Nên thử nhiều input đại diện: chữ có dấu, chữ hoa/thường, dấu câu, mã SKU, từ ghép và chuỗi rỗng.

Có thể thử analyzer trước khi index document production. Đây là bước nhỏ nhưng giúp phát hiện cấu hình analyzer sai trước khi chạy reindex hàng triệu document.

## 3. Lập kế hoạch schema version mới

Trước khi tạo index mới, cần xác định rõ thay đổi schema:

- Tên index vật lý mới.
- Mapping của từng field.
- Analyzer, normalizer và synonym configuration.
- Kiểu dữ liệu và format date.
- Cấu trúc object/nested.
- Field bắt buộc, optional và default.
- Cách chuyển đổi dữ liệu từ schema cũ.
- Quy tắc ID và routing.
- Read alias và write alias.
- Chiến lược đồng bộ write phát sinh trong migration.
- Điều kiện validation và rollback.

Nên version hóa index:

```text
products-v1  (mapping/analyzer cũ)
products-v2  (mapping/analyzer mới)
products     (alias ổn định)
```

Ứng dụng sử dụng alias `products`. Index vật lý được quản lý bởi migration process. Khi migration thành công, alias chuyển từ v1 sang v2 mà code gọi repository không cần đổi tên index.

### 3.1. Lưu mapping/settings theo version

Có thể quản lý cấu hình trong source control:

```text
src/main/resources/elasticsearch/
  products-v1-settings.json
  products-v1-mapping.json
  products-v2-settings.json
  products-v2-mapping.json
```

Hoặc dùng index template và migration script có version. Điều quan trọng là cấu hình tạo index phải có thể tái lập, review và triển khai giống nhau ở dev, staging và production.

Không dựa vào dynamic mapping để tự quyết định type cho các field nghiệp vụ quan trọng. Một document đầu tiên có giá trị khác kiểu có thể khiến dynamic mapping chọn type không phù hợp.

## 4. Ví dụ thay đổi field type và analyzer

Giả sử v1 có mapping:

```http
PUT /products-v1
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "product_id": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "price": { "type": "long" },
      "active": { "type": "boolean" }
    }
  }
}
```

Yêu cầu mới:

- `name` dùng analyzer custom có lowercase và asciifolding.
- Thêm subfield `name.raw` kiểu keyword để sort/exact match.
- `price` chuyển sang `scaled_float` để lưu giá có phần thập phân.
- Thêm field `brand` dạng keyword.

Tạo v2:

```http
PUT /products-v2
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "product_name_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "product_id": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "product_name_v2",
        "search_analyzer": "product_name_v2",
        "fields": {
          "raw": { "type": "keyword" }
        }
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "active": { "type": "boolean" },
      "brand": { "type": "keyword" }
    }
  }
}
```

Mapping và settings v2 được tạo trước khi nạp document. Reindex API không tự sao chép mapping/settings từ v1 sang v2.

### 4.1. Xác minh mapping đích

Đọc mapping:

```http
GET /products-v2/_mapping
```

Đọc settings:

```http
GET /products-v2/_settings
```

Kiểm tra analyzer:

```http
POST /products-v2/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Máy Tính Xách Tay"
}
```

Dùng `field` để Elasticsearch áp dụng analyzer được khai báo cho field đó. So sánh token với kết quả mong đợi của ứng dụng.

## 5. Nguồn dữ liệu để dựng lại index

Có hai nguồn chính:

| Nguồn | Khi phù hợp | Giới hạn |
|---|---|---|
| Index Elasticsearch cũ | `_source` có đủ field và dữ liệu để tạo document v2. | Không khôi phục được field đã bị loại khỏi `_source` hoặc dữ liệu chưa từng được index. |
| Database/domain source of truth | Cần tính lại projection, join thêm dữ liệu hoặc thay đổi logic document. | Cần batch reader, watermark/CDC và transform trong ứng dụng. |

### 5.1. Reindex từ index cũ

Nếu `_source` được bật và chứa đủ dữ liệu, có thể dùng `_reindex` để đọc document từ v1 và ghi sang v2. Đây là cách nhanh khi thay đổi chủ yếu ở mapping/analyzer và không cần lấy thêm dữ liệu nguồn.

### 5.2. Rebuild từ database

Nếu v1 đã bỏ field cần thiết, hoặc document v2 cần kết hợp dữ liệu mới từ nhiều bảng, nên rebuild từ nguồn có thẩm quyền.

Ví dụ v1 chỉ lưu:

```json
{
  "product_id": "P-100",
  "name": "Keyboard",
  "price": 2500000
}
```

Trong khi v2 cần thêm brand name, category path và availability. Nếu những dữ liệu này không có trong `_source` của v1, reindex không thể tự suy ra. Cần đọc database hoặc event store để tạo projection đầy đủ.

### 5.3. Kiểm tra _source

Reindex từ index cũ phụ thuộc `_source`. Nếu index được cấu hình tắt `_source` hoặc source filtering đã làm mất dữ liệu cần thiết, phải dùng nguồn khác hoặc chấp nhận rằng dữ liệu đó không thể tái tạo từ index hiện tại.

Không bắt đầu migration lớn trước khi xác nhận source có đủ dữ liệu và có thể đọc hết document.

## 6. Reindex API cơ bản

Sau khi tạo `products-v2`, sao chép document từ v1:

```http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Reindex đọc document source và ghi vào destination. Nó không tự copy:

- Mapping.
- Index settings.
- Analyzer definition.
- Index template.
- Alias.
- ILM policy hoặc các cấu hình vận hành liên quan.

Những thành phần đó phải được tạo/cấu hình riêng trước khi chạy reindex.

### 6.1. Reindex có script chuyển đổi field

Nếu v1 dùng `price_cents` nhưng v2 cần `price` theo đơn vị tiền tệ, có thể chuyển đổi bằng script:

```http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  },
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.price_cents != null) { ctx._source.price = ctx._source.price_cents / 100.0; } ctx._source.remove('price_cents');"
  }
}
```

Script chạy trên từng document. Cần kiểm tra null, kiểu dữ liệu, overflow, precision và quy tắc nghiệp vụ. Ví dụ trên chỉ minh họa chuyển đổi; nếu mapping đích là scaled_float, phải xác định rõ đơn vị và scaling factor.

### 6.2. Dùng ingest pipeline

Có thể tạo ingest pipeline v2 rồi chỉ định pipeline trong destination:

```http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2",
    "pipeline": "products-projection-v2"
  }
}
```

Pipeline cần được tạo và kiểm thử trước migration. Version hóa pipeline để kết quả có thể tái lập. Nếu pipeline thay đổi giữa chừng, cùng một job có thể tạo document theo nhiều quy tắc khác nhau.

### 6.3. Chọn operation semantics

Destination mặc định dùng semantics index theo ID. Nếu cần chỉ tạo document chưa tồn tại, có thể dùng `op_type: create`. Khi ID đã tồn tại, item có thể conflict thay vì ghi đè.

Không bật bỏ qua conflict mà không hiểu nguyên nhân. Conflict có thể là expected vì destination đã nhận write mới, hoặc là dấu hiệu dữ liệu migration đang bị ghi đè/đụng độ.

## 7. Reindex lớn bằng task API

Với dataset lớn, không nên phụ thuộc vào một HTTP connection mở trong toàn bộ thời gian migration. Chạy bất đồng bộ:

```http
POST /_reindex?wait_for_completion=false
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Response trả task ID. Lưu task ID vào migration metadata để theo dõi.

Kiểm tra task:

```http
GET /_tasks/<task_id>
```

Liệt kê task reindex:

```http
GET /_tasks?actions=*reindex&detailed=true
```

Hủy task nếu cần:

```http
POST /_tasks/<task_id>/_cancel
```

Hủy task không rollback document đã được ghi vào destination. Index đích có thể chứa dữ liệu dở dang; hãy đánh dấu incomplete và dọn hoặc tiếp tục theo kế hoạch.

### 7.1. Điều chỉnh tốc độ và slicing

Một số tùy chọn thường dùng:

- `requests_per_second`: throttle tốc độ batch.
- `slices`: chia reindex thành nhiều phần chạy song song.
- `max_docs`: giới hạn số document cho lượt thử hoặc migration có phạm vi.
- `wait_for_completion=false`: chạy task nền.

Ví dụ:

```http
POST /_reindex?wait_for_completion=false&requests_per_second=300&slices=auto
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Tăng slicing không phải lúc nào cũng nhanh hơn. Quá nhiều slice có thể làm tăng search context, request và áp lực cluster. Đo CPU, disk, indexing pressure, queue và search latency trước khi tăng tốc.

### 7.2. Lưu kết quả migration

Nên lưu các metadata sau:

- Source index và destination index.
- Mapping/settings version.
- Reindex task ID.
- Thời điểm bắt đầu/kết thúc.
- Total, created, updated, version conflicts và failures.
- Watermark/CDC position nếu có write đồng thời.
- Trạng thái validation và cutover.
- Người/job khởi tạo migration.

Không kết luận thành công chỉ vì task đã hoàn tất. Phải kiểm tra failures, conflict và dữ liệu thực tế.

## 8. Vấn đề write phát sinh trong lúc reindex

Reindex không tự tạo một luồng đồng bộ hoàn chỉnh cho mọi thay đổi phát sinh trong khi job đang chạy.

Giả sử reindex bắt đầu lúc 10:00. Trong lúc job chạy:

- 10:01: sản phẩm P-100 được cập nhật giá.
- 10:02: sản phẩm P-200 được tạo.
- 10:03: sản phẩm P-300 bị xóa.
- 10:05: reindex mới đọc đến một phần dữ liệu cũ.

Nếu không capture insert/update/delete, v2 có thể thiếu P-200, còn P-300 hoặc chứa giá cũ của P-100.

### 8.1. Chiến lược có downtime ngắn

Nếu có thể tạm dừng write:

1. Đưa ứng dụng vào read-only/maintenance mode hoặc dừng write producer.
2. Chờ request đang xử lý hoàn tất.
3. Reindex toàn bộ source sang destination.
4. Refresh destination.
5. Đối soát count, sample ID và query.
6. Chuyển alias sang destination.
7. Xác minh read/write.
8. Mở lại write traffic.

Ưu điểm là đơn giản và dễ bảo đảm tính nhất quán. Nhược điểm là downtime phụ thuộc kích thước dữ liệu và thời gian reindex.

### 8.2. Chiến lược online bằng dual-write

Dual-write ghi thay đổi mới vào cả index cũ và index mới trong thời gian migration.

Luồng tổng quát:

```text
Application write
       |
       +----> products-v1
       |
       +----> products-v2

Initial backfill
       |
       +----> products-v2

Validate both indexes
       |
       v
Atomic alias cutover
```

Chỉ bật dual-write là chưa đủ. Có race condition:

1. Reindex đọc P-100 với giá cũ.
2. Dual-write ghi P-100 với giá mới vào v2.
3. Reindex ghi lại giá cũ sau đó.

Nếu backfill ghi đè dữ liệu mới, v2 vẫn sai. Cần versioning, replay theo thứ tự, hoặc backfill trước rồi catch-up change log.

Dual-write cũng không phải transaction nguyên tử giữa hai index. Một lần ghi có thể thành công ở v1 nhưng thất bại ở v2. Cần retry, idempotency và reconciliation.

### 8.3. CDC hoặc transactional outbox

Nếu database là nguồn dữ liệu có thẩm quyền, CDC/outbox thường giúp kiểm soát thay đổi tốt hơn:

1. Chốt watermark W0 của change log.
2. Giữ lại event từ W0 trở đi.
3. Tạo v2 và nạp snapshot.
4. Replay event từ W0 theo thứ tự/version phù hợp.
5. Đối soát đến watermark W1.
6. Drain các event cuối hoặc tạm serialize write.
7. Chuyển alias.
8. Tiếp tục consumer vào v2.

Snapshot và watermark phải nhất quán. Nếu snapshot đã bao gồm một event nhưng replay event đó lần nữa, thao tác phải idempotent. Nếu snapshot cũ hơn watermark mà bỏ qua event, dữ liệu sẽ thiếu.

### 8.4. Xử lý delete

Delete cũng là một thay đổi dữ liệu. Nếu chỉ dual-write insert/update mà không capture delete, v2 có thể giữ document đã bị xóa ở nguồn.

CDC/outbox cần biểu diễn delete bằng event/tombstone và consumer phải áp dụng delete theo ID/version. Đối soát chỉ count có thể không phát hiện document cũ còn sót nếu số lượng khác được bù bởi document mới.

## 9. Đối soát index mới trước cutover

Không chuyển alias chỉ vì Reindex API trả trạng thái completed. Cần xác minh destination theo cùng phạm vi dữ liệu và watermark.

### 9.1. Refresh destination

```http
POST /products-v2/_refresh
```

Refresh giúp Search API nhìn thấy các document đã index trước đó. Nếu CDC/replay vẫn đang chạy, validation cuối cùng phải chờ đến mốc đồng bộ đã xác định.

### 9.2. So sánh document count

```http
GET /products-v1/_count
```

```http
GET /products-v2/_count
```

Count chỉ có ý nghĩa khi hai index đại diện cùng một snapshot/watermark. Nếu v1 vẫn nhận write còn v2 chưa replay xong, hai count có thể khác nhau một cách hợp lệ tại thời điểm so sánh.

### 9.3. Kiểm tra sample document

Chọn các ID đại diện:

- Document mới tạo gần đây.
- Document vừa update.
- Document có field optional/null.
- Document có giá trị số ở biên.
- Document có tiếng Việt, Unicode, dấu câu và từ ghép.
- Document có nested/object hoặc mảng.
- Document có field đã đổi tên/type.

Đọc theo ID từ cả hai index và so sánh theo quy tắc chuyển đổi. Không yêu cầu byte-for-byte giống nhau nếu migration có chủ đích đổi cấu trúc.

### 9.4. Kiểm tra query semantics

Chạy bộ query thực tế của ứng dụng:

- Full-text match theo analyzer mới.
- Exact match trên keyword field.
- Range filter/sort trên numeric/date.
- Query dùng multi-field mới.
- Nested query nếu cấu trúc đổi.
- Aggregation và cardinality.
- Alias filter/routing nếu có.

Đặc biệt kiểm tra các chuỗi mà analyzer thay đổi: chữ có dấu, chữ hoa/thường, dấu câu, từ viết tắt, SKU và synonym. Một index có count đúng vẫn có thể cho kết quả search khác kỳ vọng.

### 9.5. Kiểm tra lỗi và phân bố dữ liệu

Xác minh:

- Reindex failures bằng 0 hoặc mọi failure đã được xử lý.
- Version conflicts đã được phân loại.
- Count theo tenant/category/status hợp lý.
- Field bắt buộc có tỷ lệ missing đúng dự kiến.
- Không còn bulk rejection hoặc CDC lag vượt ngưỡng.
- Mapping đích đúng với schema version mong muốn.

## 10. Chuyển alias sang index mới

Alias cho phép ứng dụng dùng một tên logic ổn định trong khi index vật lý thay đổi theo version.

Trước migration:

```text
products-v1  <--- products
```

Sau migration:

```text
products-v2  <--- products
```

Dùng một request `_aliases` để remove alias khỏi v1 và add vào v2:

```http
POST /_aliases
Content-Type: application/json

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
```

Elasticsearch áp dụng các action trong một request alias update như một thay đổi atomic ở cấp cluster state. Không tách thành hai request riêng remove rồi add, vì khi đó có thể tạo khoảng thời gian alias không tồn tại.

### 10.1. Tách read alias và write alias

Có thể dùng:

- `products-read` cho truy vấn.
- `products-write` cho index/update/delete.

Nếu hai alias cùng chuyển version, gộp remove/add vào một request:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "products-v1", "alias": "products-read" } },
    { "remove": { "index": "products-v1", "alias": "products-write" } },
    { "add": { "index": "products-v2", "alias": "products-read" } },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
```

Nếu alias trỏ nhiều index, cần chỉ định write index rõ ràng. Alias không tự fan-out write sang tất cả index.

### 10.2. Giữ metadata alias

Nếu alias cũ có filter hoặc routing, phải tái tạo đúng cấu hình trên alias mới. Bỏ quên filter/routing có thể làm thay đổi tập document nhìn thấy hoặc cách request được định tuyến sau cutover.

## 11. Tích hợp với Spring Data Elasticsearch

Ứng dụng nên sử dụng alias ổn định trong entity:

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
    private String productId;

    @Field(
        type = FieldType.Text,
        analyzer = "product_name_v2",
        searchAnalyzer = "product_name_v2"
    )
    private String name;

    @Field(type = FieldType.Scaled_Float, scalingFactor = 100)
    private double price;

    @Field(type = FieldType.Keyword)
    private String brand;

    // constructors, getters, setters
}
```

Đoạn annotation minh họa mapping v2. Tên enum/thuộc tính annotation có thể khác theo version Spring Data Elasticsearch đang sử dụng; hãy đối chiếu API của dependency dự án. Ví dụ `createIndex = false` phù hợp khi index/alias được quản lý bằng migration riêng và ứng dụng không được tự tạo index lúc khởi động.

Repository tiếp tục dùng alias:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

Khi alias `products` chuyển sang `products-v2`, repository tiếp tục sử dụng tên alias đã khai báo.

### 11.1. Quản lý index bằng IndexOperations

Spring Data cung cấp `IndexOperations` để kiểm tra và thao tác index:

```java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products-v2"));

boolean exists = indexOperations.exists();
```

Có thể dùng IndexOperations cho các thao tác quản trị phù hợp với phiên bản, chẳng hạn kiểm tra tồn tại, đọc mapping hoặc xóa index. Việc tạo index version mới cần đảm bảo settings và mapping hoàn chỉnh. Với cấu hình analyzer tùy chỉnh, có thể dùng REST API/Java API Client hoặc cơ chế index migration riêng để tạo settings/mapping trước, rồi dùng Spring Data cho CRUD/search.

Không gọi `createWithMapping()` trên index đang phục vụ chỉ vì entity annotation đã thay đổi và kỳ vọng nó tự chuyển đổi field cũ. Tạo mapping mới không tái index document hiện có.

### 11.2. Không để ứng dụng tự động tạo nhầm index vật lý

Nếu ứng dụng quản lý index bằng alias và migration, cần thống nhất cấu hình startup. Một repository khởi động trước khi alias được tạo có thể cố tạo index theo tên alias hoặc thất bại do cấu hình mapping/analyzer chưa có.

Thực hiện migration/index provisioning trước khi cho application instance nhận traffic, hoặc cấu hình entity để ứng dụng không tự tạo index. Kiểm tra behavior cụ thể theo Spring Data version.

### 11.3. Dùng IndexCoordinates khi cần thao tác index version

Một số thao tác migration cần trỏ trực tiếp đến index vật lý:

```java
IndexCoordinates oldIndex = IndexCoordinates.of("products-v1");
IndexCoordinates newIndex = IndexCoordinates.of("products-v2");
```

Có thể truyền IndexCoordinates cho các API operations phù hợp để đọc/ghi theo index cụ thể. Application repository thông thường vẫn nên dùng alias ổn định; chỉ migration/admin component cần biết version vật lý.

## 12. Thay đổi analyzer trong Spring Data mapping

Entity có thể mô tả analyzer bằng annotation:

```java
@Field(
    type = FieldType.Text,
    analyzer = "product_name_v2",
    searchAnalyzer = "product_name_v2"
)
private String name;
```

Nhưng analyzer definition phải tồn tại trong index settings. Mapping annotation không tự định nghĩa tokenizer/filter custom.

Ví dụ settings JSON có thể được quản lý riêng:

```json
{
  "analysis": {
    "analyzer": {
      "product_name_v2": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }
}
```

Nếu dùng file settings/mapping theo annotation hoặc resource path, hãy giữ file đó versioned cùng code. Thứ tự tạo index cần là settings/analyzer trước, mapping sau, rồi mới nạp document.

## 13. Chiến lược rollback

Trước cutover, nếu reindex hoặc validation thất bại, giữ alias trên v1. Có thể xóa v2 chưa hoàn chỉnh và tạo lại sau khi sửa mapping/script.

Sau cutover, rollback alias về v1 có thể nhanh:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "products-v2", "alias": "products" } },
    {
      "add": {
        "index": "products-v1",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
```

Nhưng alias rollback chỉ đổi đích alias; nó không đồng bộ write phát sinh ở v2 về v1.

Ví dụ:
1. Alias chuyển sang v2 lúc 12:00.
2. P-500 được tạo lúc 12:05 và chỉ ghi vào v2.
3. P-100 được cập nhật lúc 12:06 và chỉ ghi vào v2.
4. Alias chuyển về v1 lúc 12:10.

V1 không có P-500 và chứa giá cũ của P-100. Vì vậy rollback phải có kế hoạch dữ liệu.

### 13.1. Giữ v1 đồng bộ trong rollback window

Có thể tiếp tục dual-write hoặc giữ CDC/outbox đủ lâu để replay các thay đổi về v1. Nếu rollback, v1 phải được catch-up đến watermark cuối trước khi nhận traffic.

### 13.2. Tạm dừng write và đồng bộ delta

Nếu không duy trì dual-write, khi cần rollback:
1. Tạm chặn write.
2. Drain request đang xử lý.
3. Replay change log hoặc rebuild delta từ source of truth về v1.
4. Refresh và đối soát.
5. Chuyển alias về v1.
6. Mở lại write.

### 13.3. Giữ index cũ đủ lâu

Không xóa v1 ngay sau cutover. Giữ index cũ trong rollback window để:
- So sánh kết quả v1/v2.
- Điều tra lỗi mapping/analyzer.
- Khôi phục nếu v2 có vấn đề.
- Replay dữ liệu hoặc thực hiện đối soát.

Chỉ retire v1 sau khi v2 ổn định, rollback window kết thúc và dữ liệu cần thiết đã được bảo toàn theo retention policy.

## 14. Kiểm thử migration trước production

Một migration test nên chạy trên Elasticsearch version tương thích với production, có dữ liệu đại diện và mapping giống cấu hình triển khai.

### 14.1. Test mapping và analyzer

- Tạo v2 từ settings/mapping versioned.
- Đọc lại mapping và xác nhận field type.
- Gọi Analyze API với input đại diện.
- Xác minh token output.
- Kiểm tra query full-text và exact match.

### 14.2. Test reindex

- Tạo v1 và index document mẫu.
- Tạo v2 với mapping mới.
- Chạy reindex.
- Refresh v2.
- So sánh count và sample document.
- Xác minh script/pipeline chuyển đổi field.
- Kiểm tra failures và version conflicts.

### 14.3. Test alias cutover

- Tạo alias trỏ v1.
- Chạy alias update remove/add trong một request.
- Xác minh alias trỏ v2.
- Đọc và ghi qua alias.
- Kiểm tra write index và filter/routing nếu có.
- Test rollback alias và kiểm tra data consistency strategy.

### 14.4. Test write trong lúc migration

Nếu hệ thống online:
- Tạo/update/delete document trong lúc reindex.
- Xác minh change capture ghi nhận đủ event.
- Kiểm tra race giữa backfill và dual-write.
- Replay event theo version.
- Xác minh v2 khớp source ở watermark cutover.
- Thử rollback và xác nhận không mất write sau cutover.

Testcontainers có thể giúp khởi chạy Elasticsearch cho integration test. Nên pin image version, không dùng cluster production hoặc index dùng chung để thử thao tác xóa/tạo.

## 15. Theo dõi migration trong vận hành

Một migration job nên phát ra các metric và event kỹ thuật:

| Chỉ số | Mục đích |
|---|---|
| Reindex task status | Biết task đang chạy, hoàn tất hay bị hủy. |
| Source/target document count | Phát hiện thiếu/thừa document. |
| Reindex failures | Theo dõi item không thể chuyển. |
| Version conflicts | Phát hiện cạnh tranh ghi hoặc ID trùng. |
| Reindex duration/throughput | Ước lượng thời gian hoàn tất. |
| Target indexing latency | Phát hiện destination bị quá tải. |
| 429/rejection | Theo dõi capacity cluster. |
| CDC/outbox lag | Xác định target đã bắt kịp write chưa. |
| Validation mismatch | Đếm sai khác sau transform. |
| Alias cutover timestamp | Liên kết thay đổi alias với incident. |

Không log toàn bộ document source hoặc exception message chứa PII. Ghi task ID, index version, count, duration, error type và correlation ID an toàn.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mapping API từ chối đổi field type | Field đã được tạo với type cũ. | Tạo index mới và reindex. |
| Đổi annotation nhưng dữ liệu cũ vẫn search như trước | Mapping annotation không tái index document hiện có. | Tạo index version mới và nạp lại dữ liệu. |
| Analyzer mới không được nhận diện | Chưa khai báo analyzer trong settings của index đích. | Tạo settings trước mapping. |
| Analyzer query mới nhưng document cũ không khớp | Token lưu trong inverted index vẫn theo analyzer cũ. | Reindex nếu cần đổi index-time analyzer. |
| Multi-field mới không có dữ liệu cho document cũ | Thêm mapping không backfill giá trị đã index. | Chạy update-by-query hoặc reindex. |
| Reindex báo thành công nhưng field đích sai | Mapping/script/pipeline đích chưa đúng. | Kiểm tra mapping, Analyze API và sample document. |
| Destination thiếu document mới | Write phát sinh trong lúc reindex không được capture. | Freeze write hoặc dùng CDC/outbox/dual-write. |
| Destination có dữ liệu cũ sau update | Backfill ghi đè write mới. | Versioning hoặc replay change log theo thứ tự. |
| Document đã xóa vẫn xuất hiện ở v2 | Không replay delete event. | Capture tombstone/delete và đối soát. |
| Alias switch xong ứng dụng vẫn đọc v1 | Một số code path dùng tên index vật lý. | Tìm các đường đọc/ghi và chuyển sang alias ổn định. |
| Alias không ghi được | Nhiều index nhưng không có write index. | Đặt is_write_index cho index đích. |
| Rollback alias làm mất write mới | Write sau cutover chỉ vào v2. | Đồng bộ delta/replay về v1 trước rollback. |
| Reindex quá lâu hoặc cluster quá tải | Batch/slicing/concurrency quá cao. | Throttle, theo dõi node stats và điều chỉnh tốc độ. |
| Reindex task bị cancel nhưng target còn dữ liệu | Cancel không rollback các item đã ghi. | Đánh dấu target incomplete, dọn hoặc chạy lại có kiểm soát. |
| Count hai index khác nhau | So sánh khác watermark hoặc write chưa catch up. | Đồng bộ đến cùng watermark rồi đối soát. |
| Ứng dụng tự tạo index sai khi khởi động | Index provisioning và alias lifecycle chưa thống nhất. | Quản lý index migration trước startup/traffic hoặc tắt auto-create phù hợp. |

## 17. Checklist trước khi tái tạo index

**Schema và mapping**
- Đã xác định field nào đổi type/analyzer và lý do.
- Đã chọn tên index version mới.
- Settings custom analyzer/normalizer/synonym đã được version hóa.
- Mapping v2 đã được kiểm tra trên index thử nghiệm.
- Field mới, field rename và transform có quy tắc rõ ràng.

**Nguồn dữ liệu**
- `_source` có đủ dữ liệu nếu reindex từ index cũ.
- Nếu thiếu dữ liệu, đã xác định source of truth.
- Đã kiểm tra ID/routing và cách xử lý document delete.
- Đã xác định watermark nếu có CDC/outbox.

**Reindex**
- Destination đã được tạo với settings/mapping hoàn chỉnh.
- Script/pipeline đã được test.
- Task ID được lưu và theo dõi.
- Batch/throttle/slicing phù hợp với capacity.
- Failures và conflicts được phân loại.

**Đối soát**
- Destination đã refresh.
- Count được so sánh theo cùng watermark.
- Sample document đúng.
- Analyzer output đúng với input đại diện.
- Query, sort, aggregation và filter production hoạt động.
- CDC lag đã về ngưỡng cutover.

**Cutover và rollback**
- Repository dùng alias ổn định.
- Alias filter/routing được giữ nguyên.
- Read/write alias có write index rõ ràng.
- Alias chuyển bằng một request atomic.
- Có smoke test sau cutover.
- Index cũ được giữ trong rollback window.
- Có cách replay/dual-write để rollback không làm mất write.
- Chỉ xóa index cũ sau khi kết thúc rollback window.

## 18. Quy trình migration mẫu

```text
Giai đoạn A — Chuẩn bị
  - Xác định thay đổi mapping/analyzer
  - Version hóa settings và mapping
  - Tạo products-v2

Giai đoạn B — Kiểm tra cấu hình
  - Đọc mapping/settings
  - Gọi Analyze API
  - Chạy query acceptance test

Giai đoạn C — Capture write
  - Chốt watermark W0
  - Bật CDC/outbox hoặc chuẩn bị maintenance window

Giai đoạn D — Backfill
  - Reindex v1 -> v2 hoặc rebuild từ source of truth
  - Theo dõi task, failures và throttle

Giai đoạn E — Catch-up và validation
  - Replay insert/update/delete
  - Đối soát count, sample và query
  - Chờ watermark W1

Giai đoạn F — Cutover
  - Drain/serialize write ngắn nếu cần
  - Atomic alias switch v1 -> v2
  - Smoke test read/write

Giai đoạn G — Rollback window
  - Giữ v1 và change log
  - Dual-write hoặc bảo đảm replay về v1
  - Theo dõi lỗi và hiệu năng

Giai đoạn H — Hoàn tất
  - Kết thúc rollback window
  - Ngừng luồng đồng bộ cũ
  - Retire v1 theo retention policy
```

## 19. Những điểm cần nhớ

- Mapping và analyzer quyết định cách dữ liệu được index; sửa annotation không tự tái tạo dữ liệu cũ.
- Không thể đổi tùy ý field type đã tồn tại; thay đổi không tương thích thường cần index version mới.
- Đổi index-time analyzer cần reindex để token trong inverted index được tạo lại.
- Thay đổi search analyzer chỉ ảnh hưởng phân tích query; nó không sửa token đã lưu.
- Thêm field hoặc multi-field vào mapping không tự backfill dữ liệu cho document cũ.
- Tạo destination với settings/mapping hoàn chỉnh trước khi gọi Reindex API.
- Reindex API sao chép document source, không tự copy mapping, settings, alias hoặc template.
- Reindex từ index cũ cần `_source` đầy đủ; nếu thiếu, rebuild từ source of truth.
- Write phát sinh trong lúc reindex cần freeze, dual-write hoặc capture/replay bằng CDC/outbox.
- Phải xử lý race giữa backfill và write mới, đồng thời capture cả insert, update và delete.
- Đối soát count, sample document, analyzer output và query semantics theo cùng watermark.
- Dùng một request alias update để chuyển alias atomic.
- Spring Data repository nên dùng alias ổn định thay vì tên index vật lý có version.
- Alias rollback chỉ đổi đích; nó không tự đưa write mới về index cũ.
- Giữ index cũ trong rollback window và chỉ xóa sau khi đã xác nhận dữ liệu an toàn.

Tái tạo index là một quy trình migration dữ liệu, không chỉ là thao tác thay đổi mapping. Hãy tạo index version mới với analyzer và field type đúng, nạp lại dữ liệu từ nguồn có thẩm quyền, bắt kịp các thay đổi phát sinh, kiểm tra kết quả rồi chuyển alias. Giữ index cũ cùng change log trong rollback window để có thể quay lại mà không đánh mất write mới.

## Tài liệu tham khảo

- [Elasticsearch — Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Analyzer](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-analyzers.html)
- [Elasticsearch — Analyze API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-analyze.html)
- [Elasticsearch — Update mapping API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-put-mapping.html)
- [Elasticsearch — Index aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html)
- [Elasticsearch — Update aliases API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-aliases.html)
- [Elasticsearch — Tasks API](https://www.elastic.co/guide/en/elasticsearch/reference/current/tasks.html)
- [Spring Data Elasticsearch — Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Index operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

