# Quy trình tạo index mới, reindex, kiểm tra và chuyển alias

Khi cần thay đổi mapping, analyzer hoặc số primary shard của Elasticsearch index, ứng dụng thường không thể sửa trực tiếp cấu trúc đã tồn tại theo ý muốn. Cách triển khai phổ biến là tạo một index phiên bản mới, sao chép dữ liệu bằng Reindex API, xác minh index mới rồi chuyển alias để ứng dụng tiếp tục dùng cùng một tên logic.

Ví dụ, ứng dụng đang đọc và ghi qua alias `products`, hiện trỏ tới index vật lý `products-v1`. Khi cần thay đổi cấu trúc, ta tạo `products-v2`, chuyển dữ liệu sang đó, kiểm tra và chuyển alias `products` sang index mới. Code ứng dụng vẫn sử dụng tên alias ổn định.

## 1. Index vật lý và alias

Index vật lý là nơi Elasticsearch lưu document, shard, mapping và settings. Alias là một tên logic trỏ tới một hoặc nhiều index. Ứng dụng có thể gửi request tới alias gần giống như gửi tới tên index.

~~~mermaid
flowchart LR
    A["Spring Data Elasticsearch"] -->|"products"| B["Alias products"]
    B --> C["products-v1"]
    D["Quy trình migration"] --> E["products-v2"]
    B -. "sau khi chuyển alias" .-> E
~~~

Các lợi ích chính của alias:

- Ứng dụng giữ nguyên tên truy cập khi index vật lý thay đổi.
- Có thể chuẩn bị index mới và kiểm tra trước khi chuyển ứng dụng sang dữ liệu mới.
- Có thể chuyển alias bằng một thao tác cập nhật alias duy nhất, giảm khoảng thời gian alias không trỏ tới index nào.
- Có thể giữ index cũ trong một khoảng thời gian để hỗ trợ rollback.

Alias không lưu document riêng và không thay thế mapping/settings của index. Nó chỉ định tuyến request tới index đích, có thể kèm filter, routing hoặc chỉ định write index.

### 1.1. Đặt tên index theo phiên bản

Nên tách tên index vật lý và tên alias. Ví dụ:

| Loại | Tên | Vai trò |
| --- | --- | --- |
| Index vật lý cũ | `products-v1` | Chứa dữ liệu và mapping hiện tại. |
| Index vật lý mới | `products-v2` | Đích của migration. |
| Alias ứng dụng | `products` | Tên ổn định mà ứng dụng dùng để đọc và ghi. |

Không tạo một index vật lý có tên `products` nếu muốn dùng `products` làm alias; một tên không thể đồng thời là tên index và alias. Có thể dùng hậu tố version, ngày triển khai hoặc số thứ tự để quản lý các thế hệ index.

### 1.2. Alias đọc và ghi

Một alias có thể trỏ tới nhiều index để đọc. Khi alias trỏ tới nhiều index, cần xác định index nào nhận thao tác ghi bằng `is_write_index: true`. Nếu không có write index rõ ràng trong trường hợp nhiều index, thao tác ghi qua alias có thể bị từ chối.

Với mô hình đơn giản, một alias `products` có thể vừa đọc vừa ghi và chỉ trỏ tới một index vật lý tại một thời điểm. Khi chuyển phiên bản, alias được chuyển từ `products-v1` sang `products-v2`.

Với hệ thống có yêu cầu đặc biệt, có thể dùng hai alias như `products-read` và `products-write`. Khi đó ứng dụng phải được cấu hình đúng vai trò của từng alias; không nên tách alias nếu không có nhu cầu cụ thể.

## 2. Quy trình migration tổng quát

Một lần thay đổi index thường gồm các bước:

1. Xác định index hiện tại, alias và ứng dụng đang sử dụng.
2. Thiết kế settings và mapping cho index phiên bản mới.
3. Tạo index mới với tên vật lý riêng.
4. Reindex dữ liệu từ index cũ sang index mới.
5. Kiểm tra số lượng, nội dung, mapping, settings và hành vi truy vấn.
6. Đồng bộ các thay đổi phát sinh trong thời gian reindex.
7. Chuyển alias sang index mới.
8. Theo dõi ứng dụng và giữ index cũ trong thời gian rollback.
9. Xóa index cũ khi đã hết thời gian giữ lại và không còn cần rollback.

Điểm quan trọng là **Reindex API chỉ sao chép document**. Nó không tự sao chép settings, mapping, analyzer hoặc alias của index nguồn sang index đích. Index đích phải được tạo và cấu hình trước.

## 3. Khảo sát index hiện tại

Trước khi tạo index mới, hãy xác định alias đang trỏ tới đâu:

~~~http
GET /_alias/products
~~~

Có thể xem alias bằng cat API:

~~~http
GET /_cat/aliases/products?v
~~~

Đọc mapping và settings của index vật lý hiện tại:

~~~http
GET /products-v1/_mapping
~~~

~~~http
GET /products-v1/_settings?include_defaults=true
~~~

Ghi nhận các thông tin cần thiết:

- Tên index vật lý và alias đang được sử dụng.
- Mapping của tất cả field, bao gồm `text`, `keyword`, object, nested, date và các field nghiệp vụ.
- Analyzer, normalizer và các index settings quan trọng.
- Số lượng document, kích thước index và tốc độ ghi trong thời gian bình thường.
- Các filter, routing và write index được cấu hình trên alias.
- Ứng dụng, job nền hoặc consumer khác đang truy cập trực tiếp index vật lý hay qua alias.

Không giả định mọi client đều dùng alias. Nếu một job vẫn gọi trực tiếp `products-v1`, chuyển alias sẽ không chuyển job đó sang index mới. Cần tìm và chuyển các consumer về alias nếu muốn quản lý vòng đời tập trung.

## 4. Tạo index phiên bản mới

Giả sử cần tạo `products-v2` với mapping mới và hai primary shard. Khai báo settings và mapping trong request tạo index:

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
        "analyzer": "catalog_text_v2",
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      },
      "priceInCents": {
        "type": "long"
      },
      "active": {
        "type": "boolean"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Index mới có mapping và settings độc lập với index cũ. Chọn số primary shard ngay lúc tạo vì `index.number_of_shards` không thể đổi trực tiếp sau đó. Định nghĩa analyzer phải có trong settings trước khi mapping field tham chiếu tới analyzer đó.

Kiểm tra index vừa tạo:

~~~http
GET /products-v2/_mapping
~~~

~~~http
GET /products-v2/_settings
~~~

Chưa gắn alias ứng dụng vào index mới ở bước này. Ta cần hoàn thành việc sao chép và kiểm tra trước khi chuyển traffic.

## 5. Sao chép dữ liệu bằng Reindex API

### 5.1. Reindex đồng bộ

Với tập dữ liệu nhỏ hoặc môi trường học tập, có thể chạy reindex đồng bộ:

~~~http
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
~~~

Elasticsearch đọc document từ `products-v1` và ghi vào `products-v2`. Theo mặc định, `_id` của document được giữ lại, giúp ứng dụng tiếp tục tra cứu theo ID cũ.

Reindex cần `_source` của index nguồn để đọc nội dung document. Nếu index nguồn không lưu `_source`, không thể dùng quy trình reindex thông thường để sao chép toàn bộ nội dung như ví dụ.

### 5.2. Reindex bất đồng bộ cho tập dữ liệu lớn

Với index lớn, có thể chạy request nền để nhận task ID:

~~~http
POST /_reindex?wait_for_completion=false&slices=auto
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Response trả về `task` ID. Theo dõi tiến trình bằng:

~~~http
GET /_tasks/<task-id>
~~~

Khi task hoàn tất, kiểm tra các trường như `total`, `created`, `updated`, `version_conflicts`, `noops`, `retries` và `failures`. Một request HTTP thành công chưa đủ để kết luận toàn bộ document đã được sao chép; cần đọc phần kết quả của task và xử lý mọi lỗi được báo cáo.

Có thể giới hạn tốc độ reindex bằng `requests_per_second` nếu muốn giảm ảnh hưởng tới cluster đang phục vụ traffic. Tùy quy mô, nên theo dõi heap, CPU, disk I/O, search/write latency và shard allocation trong suốt quá trình.

### 5.3. Biến đổi dữ liệu trong khi reindex

Reindex hỗ trợ script để biến đổi `_source` khi sao chép. Ví dụ đổi tên field `oldName` thành `name`:

~~~http
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
    "source": "if (ctx._source.containsKey(\u0027oldName\u0027)) { ctx._source.name = ctx._source.remove(\u0027oldName\u0027); }"
  }
}
~~~

Khi dùng script, phải xác định rõ cách xử lý document thiếu field, giá trị null, kiểu dữ liệu cũ và trường hợp xung đột tên field. Nên thử trên một tập dữ liệu nhỏ trước khi chạy trên toàn bộ index.

## 6. Đồng bộ các thay đổi phát sinh trong lúc reindex

Đây là bước dễ bị bỏ sót. Reindex đọc một tập dữ liệu từ nguồn tại thời điểm bắt đầu. Nếu ứng dụng vẫn ghi vào index cũ trong lúc reindex chạy, các thay đổi phát sinh sau thời điểm đọc có thể chưa có trong index đích. Các thao tác xóa cũng không tự được truyền sang đích chỉ bằng cách chạy reindex ban đầu.

Có hai chiến lược phổ biến:

### 6.1. Migration có cửa sổ dừng ghi

Đây là cách đơn giản và dễ kiểm soát cho hệ thống nhỏ hoặc môi trường có thể bảo trì:

1. Tạm dừng các API/job ghi vào index nguồn.
2. Chờ các request đang chạy hoàn tất.
3. Nếu index đích đã chứa dữ liệu từ lần chạy thử trước, xóa và tạo lại index đích hoặc bảo đảm nó ở trạng thái sạch theo kế hoạch.
4. Chạy reindex toàn bộ từ nguồn sang đích.
5. Refresh index đích, kiểm tra số lượng và nội dung.
6. Chuyển alias sang index mới.
7. Xác nhận ứng dụng ghi/đọc qua alias thành công rồi mở lại luồng ghi.

Vì không có ghi/xóa mới trong thời gian sao chép, dữ liệu nguồn ổn định và kết quả reindex có thể được so sánh chính xác hơn. Cần tính trước thời gian dừng ghi theo kích thước index và tốc độ reindex.

### 6.2. Migration gần như không gián đoạn

Với hệ thống cần tiếp tục ghi trong lúc backfill, cần một cơ chế đồng bộ thay đổi riêng, ví dụ:

- Ứng dụng dual-write sang cả index cũ và mới trong một khoảng thời gian.
- Ghi thay đổi vào outbox/event log rồi replay sang index mới.
- Dùng change data capture hoặc một pipeline đồng bộ có thể theo dõi update và delete.

Quy trình thường gồm backfill dữ liệu ban đầu, replay các sự kiện thay đổi theo thứ tự, tạm dừng ghi trong một khoảng ngắn để drain phần sự kiện còn lại, xác minh và chuyển alias.

Chỉ chạy `_reindex` lần thứ hai không đủ để đồng bộ chính xác mọi thay đổi. Một document đã bị xóa khỏi nguồn sau lần đọc đầu có thể vẫn còn trong đích; reindex không tự xóa document cũ khỏi destination. Nếu dùng dual-write hoặc event replay, phải xử lý cả insert, update, delete, thứ tự sự kiện, retry và tính idempotent.

## 7. Kiểm tra index đích trước khi chuyển alias

Chỉ chuyển alias khi index mới đã đáp ứng yêu cầu dữ liệu và truy vấn. Có thể kiểm tra theo nhiều lớp.

### 7.1. Kiểm tra kết quả reindex

Với reindex đồng bộ, đọc response và xác nhận:

- `timed_out` là `false`.
- Số document xử lý (`total`) phù hợp với số lượng nguồn tại thời điểm migration.
- `created` và `updated` phù hợp với tình trạng index đích.
- `version_conflicts` bằng `0`, trừ khi xung đột được dự kiến và có kế hoạch xử lý.
- Mảng `failures` rỗng.

Với reindex chạy nền, kiểm tra task tới khi hoàn tất và đọc phần response cuối cùng, không chỉ nhìn thấy task đã biến mất khỏi danh sách đang chạy.

### 7.2. Refresh và so sánh số lượng

Đảm bảo document mới đã có thể được tìm kiếm:

~~~http
POST /products-v2/_refresh
~~~

Đếm document ở hai index:

~~~http
GET /products-v1/_count
~~~

~~~http
GET /products-v2/_count
~~~

So sánh count chỉ có ý nghĩa khi dữ liệu nguồn ổn định hoặc khi đã đồng bộ đầy đủ các thay đổi. Nếu ứng dụng vẫn ghi vào nguồn, hai con số có thể khác nhau hợp lệ trong thời gian migration.

### 7.3. Kiểm tra mapping và settings

Đọc lại mapping và settings đích để chắc chắn cấu hình đúng với thiết kế:

~~~http
GET /products-v2/_mapping
~~~

~~~http
GET /products-v2/_settings
~~~

Kiểm tra các điểm quan trọng như kiểu field, analyzer, normalizer, nested path, số primary shard và replica. Reindex không tự mang mapping từ nguồn sang đích; một mapping sai có thể khiến document ghi thành công nhưng truy vấn sau này không hoạt động như mong đợi.

### 7.4. Kiểm tra document và hành vi truy vấn

Lấy một số document theo ID đại diện từ index nguồn và đích:

~~~http
GET /products-v1/_doc/KB-001
~~~

~~~http
GET /products-v2/_doc/KB-001
~~~

So sánh `_source`, field quan trọng, giá trị null, collection, nested object và các trường đã được biến đổi. Sau đó chạy các truy vấn nghiệp vụ quan trọng trên index đích: tìm kiếm toàn văn, lọc chính xác, range, sort, aggregation và nested query nếu có.

Có thể dùng aggregation hoặc các truy vấn kiểm tra để so sánh phân bố dữ liệu, chẳng hạn số sản phẩm đang active, nhóm theo trạng thái hoặc khoảng giá. Với dữ liệu quan trọng, nên có tập ID mẫu và các invariant nghiệp vụ để xác minh ngoài việc so sánh count.

### 7.5. Kiểm tra trạng thái cluster

~~~http
GET /_cluster/health/products-v2?pretty
~~~

Kiểm tra primary shard đã được phân bổ và replica đạt trạng thái mong muốn. Trạng thái `yellow` trong cluster một node có thể do replica không có node thứ hai; cần đánh giá theo topology và chính sách replica của môi trường.

## 8. Chuyển alias bằng một thao tác atomic

Khi index mới đã sẵn sàng, chuyển alias `products` từ `products-v1` sang `products-v2` bằng một request `_aliases` gồm hành động remove và add:

~~~http
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
~~~

Elasticsearch áp dụng các hành động alias trong cùng một cập nhật cluster state. Client truy cập alias sẽ được định tuyến theo cấu hình mới sau khi cập nhật được áp dụng. Điều này tránh khoảng trống do phải xóa alias ở một request rồi thêm lại ở request khác.

Nếu alias hiện tại có filter hoặc routing, phải giữ lại các thuộc tính đó trong hành động `add`. Nếu alias trỏ tới nhiều index, cần xác định rõ index đọc và write index sau khi chuyển; không xóa hoặc thêm alias một cách làm mất cấu hình routing/filter đang cần.

Kiểm tra kết quả:

~~~http
GET /_alias/products
~~~

~~~http
GET /_cat/aliases/products?v
~~~

Có thể tạo alias lần đầu bằng:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Không cần đổi tên index vật lý hoặc di chuyển document chỉ để thay tên logic. Ứng dụng tiếp tục gửi request tới `products`, còn Elasticsearch định tuyến tới index đang được alias tham chiếu.

## 9. Sử dụng alias trong Spring Data Elasticsearch

Entity Spring Data có thể dùng tên alias trong `@Document` để repository thao tác qua alias:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    // Constructor, getters và setters
}
~~~

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository extends ElasticsearchRepository<Product, String> {
}
~~~

Ở đây `products` là alias do quy trình migration quản lý. `createIndex = false` ngăn Spring Data tự tạo index theo tên alias khi khởi tạo entity metadata; index vật lý được tạo và cấu hình riêng trước khi alias được chuyển tới nó.

Khi gọi `productRepository.save(product)` hoặc `findById`, client gửi request qua tên `products`. Sau alias switch, request được định tuyến tới `products-v2` mà code repository không cần đổi tên index.

Đối với migration, dùng REST API hoặc `IndexOperations` với tên index vật lý cụ thể như `products-v2` để tạo và kiểm tra index đích. Không dùng alias ứng dụng làm tên index vật lý trong bước tạo mới. Các API quản lý index và alias có thể khác chữ ký giữa các phiên bản Spring Data Elasticsearch; REST API ở trên thể hiện trực tiếp thao tác Elasticsearch.

Nếu ứng dụng dùng nhiều alias hoặc tách alias đọc/ghi, hãy cấu hình `@Document(indexName = "...")` theo alias mà repository thực sự cần dùng và kiểm tra hành vi ghi qua write alias. Không trỏ repository tới tên index vật lý có phiên bản nếu muốn việc đổi index được thực hiện độc lập với code ứng dụng.

## 10. Rollback và giữ index cũ

Không xóa `products-v1` ngay sau khi alias chuyển sang `products-v2`. Giữ index cũ trong thời gian quan sát để có thể quay lại nếu phát hiện lỗi mapping, dữ liệu hoặc truy vấn.

Nếu chưa có dữ liệu ghi mới vào index đích sau khi cutover, có thể chuyển alias trở lại bằng một request atomic:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

**Lưu ý về dữ liệu ghi sau cutover:** sau khi ứng dụng đã ghi document mới hoặc cập nhật document trên `products-v2`, chuyển alias ngược về `products-v1` có thể làm mất các thay đổi đó đối với ứng dụng. Trước khi rollback, phải xác định cách đồng bộ các write phát sinh sau cutover về index cũ, hoặc chấp nhận khôi phục về một thời điểm dữ liệu cũ theo quyết định vận hành. Alias switch chỉ đổi định tuyến, không tự sao chép dữ liệu giữa hai index.

Giữ lại index cũ cùng thông tin migration, mapping, settings và thời điểm cutover. Sau thời gian quan sát, khi đã xác nhận không cần rollback và đã có backup phù hợp, mới xóa index cũ bằng tên vật lý cụ thể.

~~~http
DELETE /products-v1
~~~

Không gửi lệnh DELETE tới tên alias dùng cho ứng dụng khi mục tiêu là xóa một index cũ. Hãy xác định chính xác tên index vật lý trước khi xóa để tránh xóa nhầm dữ liệu đang phục vụ.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Reindex thành công nhưng mapping đích không đúng | Nghĩ rằng Reindex API sao chép cả mapping/settings. | Tạo index đích với settings và mapping trước khi reindex. |
| Count nguồn và đích khác nhau | Nguồn vẫn có ghi/xóa, reindex có lỗi hoặc destination có dữ liệu từ lần chạy trước. | Kiểm tra response/task, failures, version conflicts và chiến lược đồng bộ thay đổi. |
| Document mới không xuất hiện trong index đích | Document được ghi vào nguồn sau khi reindex đã đọc qua vị trí đó. | Dừng ghi hoặc dùng dual-write/CDC để catch up cả insert, update và delete. |
| Alias không chuyển được | Tên alias/index sai, quyền quản lý alias thiếu hoặc action không hợp lệ. | Kiểm tra alias hiện tại, tên index, quyền và response của `_aliases`. |
| Ghi qua alias bị từ chối | Alias trỏ nhiều index nhưng không có write index rõ ràng. | Chỉ định `is_write_index: true` cho index nhận ghi. |
| Repository tự tạo index tên alias | Cấu hình entity cho phép auto-create hoặc migration chưa tạo alias. | Quản lý schema/alias riêng và cân nhắc `createIndex = false`. |
| Rollback làm mất dữ liệu mới | Ứng dụng đã ghi vào index mới sau cutover. | Đồng bộ các thay đổi ngược lại hoặc chọn phương án khôi phục có kiểm soát trước khi đổi alias. |

## 12. Checklist triển khai migration

### Trước khi bắt đầu

- [ ] Xác định alias và tất cả consumer đang truy cập index.
- [ ] Lưu mapping, settings, số lượng document và các truy vấn nghiệp vụ quan trọng của index cũ.
- [ ] Thiết kế mapping/settings mới và chọn tên index vật lý có phiên bản.
- [ ] Quyết định migration có cửa sổ dừng ghi hay cần dual-write/CDC.
- [ ] Chuẩn bị phương án rollback và thời gian giữ index cũ.

### Trong khi migration

- [ ] Tạo index đích trước khi reindex.
- [ ] Theo dõi task reindex, retries, version conflicts và failures.
- [ ] Đồng bộ thay đổi phát sinh, bao gồm cả delete.
- [ ] Refresh index đích và xác minh count, mapping, settings, document mẫu, query và cluster health.
- [ ] Chuyển alias bằng một request `_aliases` atomic và đặt write index rõ ràng.

### Sau khi chuyển alias

- [ ] Xác nhận alias trỏ đúng index mới.
- [ ] Kiểm tra repository đọc và ghi qua alias.
- [ ] Theo dõi log, lỗi truy vấn, độ trễ, throughput và trạng thái shard.
- [ ] Giữ index cũ trong thời gian rollback đã định.
- [ ] Chỉ xóa index cũ sau khi xác nhận dữ liệu mới ổn định và không còn nhu cầu quay lại.

## 13. Quy trình thực hành rút gọn

Với một môi trường học tập có thể tạm dừng ghi, quy trình mẫu là:

1. Tạo `products-v2` với settings và mapping mong muốn.
2. Tạm dừng ứng dụng hoặc luồng ghi vào `products-v1`.
3. Chạy `POST /_reindex` từ `products-v1` sang `products-v2`.
4. Refresh `products-v2`, đọc response reindex và so sánh `_count`.
5. Kiểm tra mapping, settings, document mẫu và các truy vấn quan trọng.
6. Chuyển alias `products` bằng một request `_aliases` gồm remove cũ và add mới với `is_write_index: true`.
7. Kiểm tra alias và thực hiện một lần đọc/ghi thử qua repository.
8. Mở lại luồng ghi và theo dõi hệ thống.
9. Giữ `products-v1` cho đến khi hết thời gian rollback.

Trong Spring Data Elasticsearch, repository nên truy cập qua alias ổn định được khai báo trong `@Document`. Index vật lý được tạo và migration độc lập. Reindex chuyển document giữa hai index đã tồn tại; kiểm tra dữ liệu và mapping xác nhận index đích sẵn sàng; alias switch cập nhật nơi ứng dụng đọc/ghi mà không phải đổi tên logic trong code. Việc đồng bộ các write/delete phát sinh và giữ kế hoạch rollback là điều kiện để migration không làm mất dữ liệu.
