# Tạo, cập nhật và xóa alias bằng API phù hợp

Trong Elasticsearch, **alias** là một tên logic trỏ đến một hoặc nhiều index. Ứng dụng có thể truy cập dữ liệu qua alias thay vì gắn trực tiếp với tên index vật lý. Nhờ vậy, hệ thống có thể thay index, chuyển phiên bản dữ liệu, tạo read/write endpoint riêng hoặc giới hạn tập document được tìm kiếm mà không phải thay tên index trong mọi nơi của ứng dụng.

Ví dụ, thay vì để ứng dụng truy cập trực tiếp `products-v1`, ta tạo alias `products` trỏ đến index đó:

```text
Ứng dụng Spring Data Elasticsearch
              |
              | indexName = "products"
              v
        Alias: products
              |
              v
       Index: products-v1
```

Khi cần thay mapping hoặc analyzer, có thể tạo `products-v2`, sao chép dữ liệu và chuyển alias `products` sang index mới. Ứng dụng vẫn dùng tên logic `products` trong cấu hình.

Elasticsearch cung cấp các API chính để quản lý alias:

| Mục đích | API thường dùng |
|---|---|
| Tạo alias | `PUT /<index>/_alias/<alias>` hoặc `POST /_aliases` với action `add`. |
| Cập nhật/chuyển alias | `POST /_aliases` với một hoặc nhiều action `add`, `remove`. |
| Xem alias | `GET /_alias/<alias>`, `GET /<index>/_alias/<alias>` hoặc `_cat/aliases`. |
| Xóa alias | `DELETE /<index>/_alias/<alias>` hoặc action `remove` trong `POST /_aliases`. |
| Xóa index vật lý | `DELETE /<index>`; đây là thao tác khác với xóa alias. |

## 1. Alias là gì và dùng để làm gì?

Alias là một tên thay thế cho index. Một alias có thể trỏ đến một index hoặc nhiều index cùng lúc. Nhiều alias cũng có thể trỏ đến cùng một index.

Một số cách sử dụng phổ biến:

- **Tên index ổn định:** ứng dụng dùng `products`, trong khi index vật lý được đánh phiên bản như `products-v1`, `products-v2`.
- **Chuyển đổi phiên bản:** sau khi tạo index mới và reindex xong, chuyển alias từ index cũ sang index mới.
- **Tách đọc và ghi:** alias đọc có thể trỏ đến nhiều index; alias ghi trỏ đến index nhận dữ liệu mới.
- **Lọc dữ liệu:** alias có filter để các truy vấn search qua alias chỉ nhìn thấy một phần document.
- **Routing:** alias có thể quy định routing cho thao tác tìm kiếm hoặc ghi để giới hạn shard cần truy cập.
- **Quản lý vòng đời:** alias có thể được dùng làm write alias cho rollover, khi hệ thống chuyển sang index vật lý tiếp theo.

Alias không phải index và không lưu document độc lập. Dữ liệu vẫn nằm trong index vật lý mà alias trỏ tới.

## 2. Tạo alias

Giả sử đã có index `products-v1`. Có thể tạo alias `products` bằng API riêng cho một index:

```http
PUT /products-v1/_alias/products
```

Sau khi request thành công, ứng dụng có thể tìm kiếm qua alias:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
```

Hoặc dùng Aliases API để thêm alias:

```json
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
```

Hai cách trên đều tạo quan hệ alias. `PUT /<index>/_alias/<alias>` tiện khi chỉ thao tác trên một index; `POST /_aliases` hữu ích khi cần phối hợp nhiều thay đổi trong cùng một request.

### Tạo alias có write index

Một alias có thể trỏ đến nhiều index. Nếu alias được dùng để ghi và trỏ đến nhiều index, Elasticsearch cần biết index nào là đích ghi. Có thể khai báo `is_write_index` ngay khi tạo:

```json
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
```

Nếu alias chỉ trỏ đến một index, index đó mặc định được xem là write index. Khi alias trỏ đến nhiều index, nên chỉ định rõ một write index. Nếu không có write index xác định, thao tác ghi qua alias nhiều index sẽ bị từ chối vì Elasticsearch không thể chọn đích ghi.

### Tạo alias có filter

Alias có thể áp dụng một filter cho các truy vấn search đi qua alias. Ví dụ tạo alias chỉ hiển thị sản phẩm đang hoạt động:

```json
PUT /products-v1/_alias/active-products
{
  "filter": {
    "term": {
      "active": true
    }
  }
}
```

Khi gọi:

```http
GET /active-products/_search
```

Elasticsearch tự kết hợp filter của alias vào truy vấn search. Ứng dụng không cần lặp lại điều kiện `active = true` trong mọi query.

Filter của alias là tiện ích cho truy vấn tìm kiếm, không phải cơ chế phân quyền hoặc ranh giới bảo mật. Không nên dùng alias filter để ngăn người dùng truy cập dữ liệu nhạy cảm. Hãy cấu hình security role và quyền truy cập index phù hợp. Ngoài ra, filter alias không được áp dụng như một điều kiện ràng buộc cho mọi API đọc/ghi document; cần hiểu rõ loại API đang dùng.

### Tạo alias có routing

Nếu ứng dụng dùng custom routing, alias có thể gắn routing để giảm phạm vi shard cần truy cập. Ví dụ:

```json
PUT /tenant-events-v1/_alias/tenant-42-events
{
  "search_routing": "tenant-42",
  "index_routing": "tenant-42"
}
```

`search_routing` được áp dụng cho truy vấn search qua alias; `index_routing` được áp dụng cho thao tác ghi qua alias. Routing phải nhất quán với cách document được ghi vào index. Nếu một document đã được index bằng routing khác, truy vấn qua alias với routing cố định có thể không tìm thấy document đó.

Không dùng alias routing như một cơ chế bảo mật thay thế phân quyền. Routing chủ yếu giúp định tuyến shard và tối ưu phạm vi thao tác.

## 3. Xem alias đang trỏ đến đâu

Để xem một alias cụ thể:

```http
GET /_alias/products
```

Response cho biết các index mà alias `products` đang trỏ đến cùng metadata alias như filter, routing và write index nếu có.

Để xem alias của một index cụ thể:

```http
GET /products-v1/_alias/products
```

Để liệt kê alias dạng bảng dễ đọc:

```http
GET /_cat/aliases?v
```

Có thể xem index và alias cùng lúc bằng các API cat tương ứng:

```http
GET /_cat/indices?v
GET /_cat/aliases?v
```

Khi điều tra lỗi, hãy xác nhận alias thực sự trỏ đến index nào trước khi kiểm tra mapping hoặc document. Một truy vấn sai kết quả có thể do alias vẫn trỏ đến index cũ, alias trỏ đến nhiều index có mapping không đồng nhất, hoặc filter/routing làm thay đổi tập dữ liệu được truy cập.

## 4. Cập nhật alias

Trong thực tế, cập nhật alias thường có nghĩa là thay đổi metadata của alias hoặc chuyển alias từ index này sang index khác.

### Chuyển alias từ index cũ sang index mới

Giả sử:

- `products-v1` là index hiện tại.
- `products-v2` đã được tạo với mapping mới và đã nhận dữ liệu reindex.
- `products` là alias mà ứng dụng đang sử dụng.

Có thể chuyển alias bằng một request `_aliases` chứa action remove và add:

```json
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
```

Các action trong một request update aliases được áp dụng như một thay đổi cluster state nguyên tử. Client không nhìn thấy trạng thái trung gian mà alias đã bị gỡ khỏi index cũ nhưng chưa được thêm vào index mới. Đây là lý do nên gom thao tác remove/add vào cùng một request thay vì gửi hai request tách biệt.

Sau khi chuyển, kiểm tra lại:

```http
GET /_alias/products
```

Alias `products` phải trỏ đến `products-v2`. Ứng dụng tiếp tục gửi request tới `products` như trước.

### Thêm một index vào alias nhiều index

Alias đọc có thể trỏ đến nhiều index, ví dụ dữ liệu theo tháng:

```json
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-2026-10",
        "alias": "orders-history"
      }
    },
    {
      "add": {
        "index": "orders-2026-11",
        "alias": "orders-history"
      }
    }
  ]
}
```

Truy vấn qua `orders-history` sẽ tìm kiếm trên các index được alias tham chiếu. Cần bảo đảm mapping giữa các index tương thích với những field mà query sử dụng. Nếu cùng một field có kiểu không tương thích ở các index khác nhau, search hoặc sort có thể gặp lỗi hoặc cho kết quả không nhất quán.

### Cập nhật filter hoặc routing

Khi muốn đổi filter/routing của alias, có thể dùng action `add` với `is_write_index` và metadata mới, hoặc remove alias cũ rồi add lại với cấu hình mong muốn trong cùng request:

```json
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "active-products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "active-products",
        "filter": {
          "term": {
            "status": "PUBLISHED"
          }
        }
      }
    }
  ]
}
```

Ở ví dụ này, alias được thay filter từ điều kiện cũ sang điều kiện `status = PUBLISHED`. Nếu alias có thêm metadata như routing hoặc `is_write_index`, hãy khai báo lại đầy đủ các thuộc tính cần giữ khi tái tạo alias.

## 5. Xóa alias

Để gỡ alias `products` khỏi index `products-v1`, dùng:

```http
DELETE /products-v1/_alias/products
```

Hoặc dùng Aliases API với action `remove`:

```json
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    }
  ]
}
```

Thao tác này chỉ xóa liên kết alias khỏi index. Index `products-v1` và các document bên trong vẫn tồn tại.

Nếu alias trỏ đến nhiều index và muốn gỡ khỏi tất cả, cần chỉ định đúng các index hoặc mẫu index phù hợp trong action remove. Trước khi thực hiện, hãy xem alias hiện tại bằng `GET /_alias/<alias>` để tránh bỏ sót liên kết.

### Phân biệt xóa alias và xóa index

Hai thao tác sau có ý nghĩa rất khác nhau:

```http
DELETE /products-v1/_alias/products
```

Gỡ alias `products` khỏi index `products-v1`; dữ liệu index vẫn còn.

```http
DELETE /products-v1
```

Xóa index vật lý `products-v1` cùng dữ liệu của nó. Nếu alias đang trỏ đến index đó, alias cũng không còn đích trỏ tương ứng.

Aliases API còn có action `remove_index` để xóa index vật lý:

```json
POST /_aliases
{
  "actions": [
    {
      "remove_index": {
        "index": "products-obsolete"
      }
    }
  ]
}
```

`remove_index` là thao tác xóa dữ liệu index, không phải cách thông thường để xóa alias. Chỉ dùng khi thật sự muốn xóa index và đã xác nhận chính sách lưu giữ/backup.

## 6. Write index khi alias trỏ đến nhiều index

Alias đọc có thể trỏ đến nhiều index, nhưng một alias chỉ có tối đa một write index. Khi alias trỏ đến nhiều index, cần đánh dấu index nhận thao tác ghi bằng `is_write_index: true`.

Ví dụ:

```json
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-2026-10",
        "alias": "orders"
      }
    },
    {
      "add": {
        "index": "orders-2026-11",
        "alias": "orders",
        "is_write_index": true
      }
    }
  ]
}
```

Kết quả:

- Search qua `orders` có thể đọc cả hai index.
- Index request qua `orders` được gửi đến `orders-2026-11`.
- Document cũ trong `orders-2026-10` vẫn được tìm kiếm.

Nếu không khai báo write index cho alias nhiều index, thao tác ghi qua alias sẽ không được định tuyến đến một index duy nhất. Khi thiết kế alias, hãy phân biệt rõ alias chỉ đọc và alias có quyền ghi.

Một thiết kế thường gặp là tách hai alias:

```text
orders-read  ---> orders-2026-10
             ---> orders-2026-11

orders-write ---> orders-2026-11 (is_write_index = true)
```

Alias đọc phục vụ truy vấn lịch sử; alias ghi chỉ định index hiện hành. Cách này hữu ích khi rollover hoặc phân chia dữ liệu theo thời gian.

## 7. Rollover alias và vòng đời index

Elasticsearch có Rollover API để chuyển write alias sang một index mới khi đạt điều kiện về tuổi, số document hoặc kích thước. Alias cần được thiết lập với write index trước khi rollover.

Ví dụ tạo index đầu tiên và write alias:

```json
PUT /events-000001
{
  "aliases": {
    "events-write": {
      "is_write_index": true
    },
    "events-read": {}
  }
}
```

Khi index đạt điều kiện, có thể rollover:

```json
POST /events-write/_rollover
{
  "conditions": {
    "max_age": "30d",
    "max_docs": 1000000,
    "max_size": "50gb"
  }
}
```

Nếu điều kiện đạt, Elasticsearch tạo index tiếp theo theo quy tắc tên và chuyển write alias sang index mới. Alias đọc có thể tiếp tục trỏ đến các index lịch sử theo cấu hình rollover/ILM phù hợp.

Rollover thường được kết hợp với Index Lifecycle Management (ILM) để quản lý hot/warm/cold/delete phases. Lưu ý `events-read` trong ví dụ chỉ trỏ đến index đầu tiên; rollover write alias không tự động thêm index mới vào mọi alias đọc khác. Nếu muốn `events-read` bao gồm cả index mới, cần thêm index mới vào alias đó bằng Aliases API hoặc cấu hình lifecycle policy phù hợp. Khi dùng ILM, cần khai báo alias và lifecycle policy nhất quán; không tự chuyển alias thủ công nếu ILM đang điều khiển cùng alias mà chưa hiểu trạng thái policy.

## 8. Sử dụng alias trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch, `@Document(indexName = "...")` xác định tên index logic mà entity sử dụng. Tên này có thể là alias đã được tạo trong Elasticsearch:

```java
@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;
}
```

Ở đây, `products` là alias trỏ đến index vật lý như `products-v1` hoặc `products-v2`. Repository vẫn có thể sử dụng alias:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

Khi gọi `save`, `findById` hoặc search repository, request được gửi đến tên logic mà entity khai báo; Elasticsearch giải quyết alias và định tuyến đến index vật lý.

`createIndex = false` được dùng trong ví dụ khi index/alias đã được quản lý bởi migration hoặc deployment. Nếu Spring Data được phép tự tạo index, hãy xác định rõ thứ tự tạo settings, mapping và alias để tránh việc ứng dụng tạo một concrete index có tên trùng với alias dự kiến. Thuộc tính annotation và hành vi auto-creation cần được đối chiếu với phiên bản Spring Data Elasticsearch của dự án.

### Tạo và chuyển alias qua IndexOperations

Spring Data Elasticsearch có `IndexOperations` để quản lý metadata index và alias. Tùy phiên bản, API có thể cung cấp các phương thức thêm/xóa alias hoặc thao tác alias qua `AliasQuery`/`AliasAction`. Nếu cần kiểm soát đầy đủ các action atomically, có thể dùng Elasticsearch Java API Client hoặc REST API trực tiếp.

Ví dụ về cách inject operations để quản lý index:

```java
@Service
public class ProductIndexAdminService {

    private final ElasticsearchOperations operations;

    public ProductIndexAdminService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean indexExists(String indexName) {
        return operations.indexOps(IndexCoordinates.of(indexName)).exists();
    }
}
```

Đoạn code trên minh họa việc truy cập `IndexOperations`; kiểm tra alias tồn tại và thực hiện update alias cần dùng đúng method/API của phiên bản Spring Data đang chạy. Không nên giả định `exists()` trên một abstraction bất kỳ luôn phân biệt concrete index với alias theo cùng cách của Elasticsearch Indices API.

Với các thao tác alias quan trọng trong production, request `_aliases` là một cách rõ ràng để thể hiện toàn bộ thay đổi trong một payload và tận dụng tính nguyên tử của update aliases. Có thể gọi thông qua Elasticsearch Java API Client được inject bởi Spring Boot hoặc qua HTTP client được quản lý bởi ứng dụng.

## 9. Quy trình triển khai index version mới bằng alias

Một quy trình phổ biến để thay đổi mapping hoặc analyzer:

1. Ứng dụng đang dùng alias `products` trỏ đến `products-v1`.
2. Tạo `products-v2` với mapping/settings mới.
3. Reindex dữ liệu từ `products-v1` sang `products-v2`.
4. Kiểm tra count, mapping, document mẫu và các truy vấn quan trọng.
5. Đồng bộ các thay đổi phát sinh trong lúc reindex hoặc tạm dừng ghi theo kế hoạch.
6. Chuyển alias `products` từ `products-v1` sang `products-v2` bằng một request `_aliases` chứa remove và add.
7. Theo dõi ứng dụng sau chuyển đổi; giữ index cũ để rollback trong thời gian cần thiết.
8. Chỉ xóa `products-v1` khi đã hết thời hạn rollback và dữ liệu được backup theo chính sách.

Sơ đồ:

```text
Trước khi chuyển:
  Application -> products -> products-v1

Chuẩn bị:
  products-v1 -- reindex --> products-v2
  Kiểm tra mapping, count, search relevance

Sau khi chuyển:
  Application -> products -> products-v2
  products-v1 được giữ lại tạm thời để rollback
```

Việc chuyển alias không tự đồng bộ dữ liệu. Nếu vẫn ghi vào index cũ trong khi reindex, cần xử lý các thay đổi mới trước khi chuyển. Nếu không, dữ liệu mới có thể bị thiếu trong index đích.

## 10. Các lỗi thường gặp khi quản lý alias

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `invalid_alias_name_exception` | Tên alias trùng với tên index/data stream hoặc vi phạm quy tắc đặt tên. | Chọn tên logic khác; alias không thể cùng tên với concrete index. |
| 404 khi tạo alias | Index đích chưa tồn tại hoặc tên index sai. | Tạo index trước, sau đó mới add alias. |
| Ghi qua alias nhiều index bị từ chối | Alias không có write index xác định. | Đặt `is_write_index: true` cho đúng một index. |
| Search trả dữ liệu từ nhiều phiên bản | Alias đang trỏ đến nhiều index. | Kiểm tra `GET /_alias/<alias>` và remove index không còn cần thiết. |
| Search không thấy document | Alias filter/routing hoặc alias đang trỏ sai index. | Kiểm tra metadata alias, routing và mapping. |
| Query lỗi sau khi chuyển alias | Mapping giữa index cũ và mới không tương thích. | Kiểm tra mapping của tất cả index alias trỏ tới. |
| Spring Data tự tạo index có tên alias | Auto index creation chạy trước khi alias được thiết lập. | Quản lý index/alias theo migration và cấu hình createIndex phù hợp. |
| Xóa alias nhưng dữ liệu biến mất | Đã xóa concrete index thay vì chỉ xóa alias. | Phân biệt `DELETE /<index>/_alias/<alias>` với `DELETE /<index>`. |

Khi thao tác alias, nên kiểm tra trạng thái trước và sau bằng `GET /_alias/<alias>`. Với thay đổi production, ghi lại index cũ, index mới và payload alias để có thể kiểm tra hoặc rollback.

## 11. Nguyên tắc đặt tên và quản lý alias

- Dùng tên alias ổn định, dễ hiểu theo nghiệp vụ, ví dụ `products`, `orders-read`, `orders-write`.
- Dùng tên index vật lý có phiên bản hoặc mốc thời gian, ví dụ `products-v3`, `orders-2026-11`.
- Tạo index và mapping trước khi thêm alias.
- Với alias nhiều index, khai báo rõ write index nếu alias được dùng để ghi.
- Dùng một request `_aliases` để chuyển alias remove/add nguyên tử.
- Kiểm tra mapping giữa các index nếu một alias đọc nhiều index.
- Không xem alias filter hoặc routing là cơ chế bảo mật.
- Không nhầm lẫn xóa alias với xóa index vật lý.
- Giữ index cũ trong thời gian rollback và chỉ xóa khi đã xác nhận.
- Nếu ILM/rollover quản lý alias, không thay đổi alias thủ công mà không kiểm tra policy và trạng thái hiện tại.

## 12. Những điểm cần nhớ

- Alias là tên logic trỏ đến một hoặc nhiều index; dữ liệu vẫn nằm trong index vật lý.
- Tạo alias bằng `PUT /<index>/_alias/<alias>` hoặc action `add` trong `POST /_aliases`.
- Xem alias bằng `GET /_alias/<alias>` hoặc `GET /_cat/aliases?v`.
- Chuyển alias bằng action `remove` và `add` trong cùng một request `POST /_aliases` để cập nhật nguyên tử.
- Alias nhiều index cần write index rõ ràng nếu dùng để ghi; một alias chỉ có tối đa một write index.
- Alias filter tác động đến search; không dùng nó để bảo vệ dữ liệu nhạy cảm.
- Alias routing giúp định tuyến shard nhưng phải khớp với routing lúc ghi document.
- Xóa alias bằng `DELETE /<index>/_alias/<alias>` chỉ gỡ liên kết; `DELETE /<index>` xóa dữ liệu index.
- Spring Data có thể dùng alias làm `indexName`; cần quản lý index creation và alias lifecycle có chủ đích.
- Alias hỗ trợ triển khai index version mới, rollover và rollback mà không buộc ứng dụng đổi tên index vật lý.

Quản lý alias đúng cách giúp ứng dụng Spring Data Elasticsearch duy trì một tên truy cập ổn định trong khi index vật lý được tạo mới, thay thế hoặc phân chia theo vòng đời. Hãy tạo index trước, kiểm tra dữ liệu, chuyển alias bằng một thao tác nguyên tử và giữ khả năng rollback để quá trình thay đổi index có thể kiểm soát được.
