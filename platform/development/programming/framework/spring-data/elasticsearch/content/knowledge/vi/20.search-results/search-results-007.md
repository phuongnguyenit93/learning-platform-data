# Phân biệt `_source`, stored fields và docvalue fields

Khi Elasticsearch trả kết quả tìm kiếm, ứng dụng có thể cần nội dung JSON đầy đủ của document, một vài field được lưu riêng hoặc các giá trị tối ưu cho sort và aggregation. Elasticsearch cung cấp ba cơ chế thường gặp: `_source`, stored fields và doc values. Chúng có mục đích khác nhau và không thể thay thế lẫn nhau trong mọi trường hợp.

- **`_source`** giữ nội dung JSON được gửi khi index document. Đây thường là dữ liệu Spring Data Elasticsearch dùng để dựng lại entity Java.
- **Stored fields** lưu riêng những field được mapping khai báo `store: true`, sau đó có thể yêu cầu qua `stored_fields`.
- **Doc values** lưu giá trị theo dạng cột, tối ưu cho sort, aggregation, script và truy xuất field theo kiểu dữ liệu được hỗ trợ. Có thể yêu cầu chúng qua `docvalue_fields`.

Hiểu đúng ba cơ chế giúp thiết kế mapping phù hợp, giảm payload response và tránh lỗi khi ứng dụng cần dựng entity hoặc thực hiện thống kê.

## 1. Ba cơ chế lưu trữ và truy xuất

| Cơ chế | Dữ liệu được lưu như thế nào? | Cách yêu cầu trong Search API | Mục đích chính |
| --- | --- | --- | --- |
| `_source` | Nội dung JSON của document. | `_source`, `_source: { includes, excludes }`. | Đọc document và dựng lại object Java. |
| Stored fields | Bản lưu riêng của từng field có `store: true`. | `stored_fields`. | Lấy một số field được chọn lưu riêng. |
| Doc values | Cấu trúc dạng cột theo từng field, nếu kiểu field hỗ trợ. | `docvalue_fields`. | Sort, aggregation, script và đọc giá trị field phù hợp. |

Các cơ chế có thể cùng tồn tại. Ví dụ một field `sku` kiểu `keyword` có thể xuất hiện trong `_source`, được lưu riêng bằng `store: true` và có doc values để sort/aggregation. Điều đó không có nghĩa phải bật cả ba: mỗi cơ chế nên được chọn theo nhu cầu thực tế.

## 2. `_source`: nội dung JSON gốc

`_source` là phần dữ liệu JSON được gửi khi tạo hoặc cập nhật document. Nó giữ cấu trúc object, mảng, giá trị null và nội dung field theo cách ứng dụng đã gửi, trong phạm vi cơ chế lưu source của index.

Ví dụ document:

~~~json
{
  "sku": "KB-001",
  "name": "Mechanical Keyboard",
  "category": "Accessories",
  "price": 129900,
  "tags": ["wireless", "office"],
  "supplier": {
    "name": "Acme",
    "country": "VN"
  }
}
~~~

Khi search, hit thường chứa `_source` như sau:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "_score": 1.42,
  "_source": {
    "sku": "KB-001",
    "name": "Mechanical Keyboard",
    "category": "Accessories",
    "price": 129900,
    "tags": ["wireless", "office"],
    "supplier": {
      "name": "Acme",
      "country": "VN"
    }
  }
}
~~~

Vì `_source` giữ cấu trúc JSON, nó phù hợp khi ứng dụng cần:

- Dựng lại entity hoặc DTO có object lồng nhau và collection.
- Trả về nhiều field cùng lúc cho API.
- Đọc các field không được lập chỉ mục.
- Reindex hoặc cập nhật document dựa trên nội dung source.

`_source` không phải inverted index. Một field có thể không được lập chỉ mục để tìm kiếm nhưng vẫn nằm trong `_source` và có thể được trả về.

### 2.1. Lọc field trong `_source`

Không phải response nào cũng cần toàn bộ document. Search API cho phép chỉ lấy một số field bằng source filtering:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": ["sku", "name", "price"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  }
}
~~~

Có thể dùng `includes` và `excludes` để kiểm soát chi tiết hơn:

~~~json
{
  "_source": {
    "includes": ["sku", "name", "supplier.name"],
    "excludes": ["internalNotes"]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Source filtering giảm kích thước payload trả về và lượng dữ liệu cần chuyển đổi ở client. Nó không xóa field khỏi document đã lưu và cũng không thay đổi mapping hoặc khả năng query của field.

### 2.2. Tắt `_source`

Elasticsearch cho phép cấu hình `_source` disabled ở cấp index. Khi đó hit không trả nội dung JSON gốc theo cách thông thường. Việc này có thể giảm chi phí lưu source trong một số trường hợp, nhưng làm mất một cơ chế rất quan trọng của hệ thống.

Các thao tác có thể bị hạn chế khi không có `_source` gồm:

- Dựng entity đầy đủ từ search hit trong Spring Data.
- Reindex dữ liệu bằng Reindex API thông thường, vốn cần đọc source của document.
- Update document theo cách cần đọc và sửa nội dung source.
- Các quy trình ứng dụng dựa vào object JSON gốc hoặc field không được lưu riêng.

Chỉ cân nhắc tắt `_source` khi đã thiết kế rõ cách lưu và tái tạo dữ liệu thay thế. Với ứng dụng Spring Data Elasticsearch thông thường, nên giữ `_source`.

## 3. Stored fields: lưu riêng field bằng `store: true`

Mặc định, field mapping thường có `store: false`. Giá trị vẫn có thể xuất hiện trong `_source`, nhưng Elasticsearch không lưu riêng field đó như một stored field.

Khi khai báo `store: true`, Elasticsearch lưu thêm giá trị field để có thể trả về qua `stored_fields`. Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword",
        "store": true
      },
      "name": {
        "type": "text"
      },
      "price": {
        "type": "long"
      }
    }
  }
}
~~~

Yêu cầu stored field trong Search API:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": false,
  "stored_fields": ["sku"],
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

Phần response của hit có dạng:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "fields": {
    "sku": ["KB-001"]
  }
}
~~~

Stored field thường được biểu diễn trong object `fields` dưới dạng danh sách giá trị. Ngay cả khi field chỉ có một giá trị, response vẫn có thể biểu diễn nó như một mảng.

### 3.1. Điều kiện để lấy stored field

Để `stored_fields` trả được một field, mapping phải khai báo `store: true` cho field đó. Nếu không, request không thể lấy field như stored field chỉ vì nó có trong `_source` hoặc có inverted index.

`stored_fields` không tự động đọc từ `_source`. Nếu field chưa được lưu riêng, lựa chọn thông thường là:

- Lấy field qua `_source` hoặc source filtering.
- Tạo mapping mới có `store: true` nếu có lý do cần stored field, sau đó reindex dữ liệu.

Không thể bật `store: true` cho field đã tồn tại rồi kỳ vọng các document cũ tự có bản stored field mới. Thay đổi mapping field thường cần index mới và reindex.

### 3.2. Khi nào nên dùng stored fields?

Có thể cân nhắc `store: true` nếu ứng dụng thường xuyên cần lấy một vài field riêng biệt và có lý do rõ ràng để truy xuất chúng độc lập với `_source`.

Tuy nhiên, stored fields không mặc nhiên nhanh hơn source filtering. Elasticsearch lưu `_source` theo cách tối ưu riêng; khi đọc một vài field từ `_source`, chi phí thực tế còn phụ thuộc kích thước document, codec, số field cần lấy và cách dữ liệu được truy cập. Cần đo trên dữ liệu thực tế trước khi chọn stored fields như một tối ưu hiệu năng.

Không bật `store: true` cho mọi field chỉ vì muốn đọc lại giá trị. Nếu `_source` đã đáp ứng nhu cầu, lưu thêm bản riêng có thể làm tăng dung lượng và chi phí ghi.

## 4. Doc values: lưu trữ dạng cột

Doc values là cấu trúc lưu trữ theo dạng cột, được Elasticsearch tối ưu cho việc đọc giá trị của một field trên nhiều document. Chúng thường được dùng cho:

- Sắp xếp kết quả theo field.
- Aggregation như `terms`, `min`, `max`, `sum` hoặc `avg` tùy kiểu dữ liệu.
- Truy xuất field qua `docvalue_fields`.
- Một số thao tác script truy cập giá trị field.

Với nhiều kiểu field hỗ trợ, `doc_values` mặc định được bật. Các kiểu thường dùng gồm `keyword`, số, `date`, `boolean` và một số kiểu scalar khác. `text` không hỗ trợ doc values thông thường.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword",
        "doc_values": true
      },
      "price": {
        "type": "long",
        "doc_values": true
      },
      "createdAt": {
        "type": "date",
        "doc_values": true
      }
    }
  }
}
~~~

### 4.1. Sort và aggregation dùng doc values

Ví dụ sắp xếp sản phẩm theo giá:

~~~json
{
  "sort": [
    { "price": { "order": "asc" } }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Ví dụ đếm số sản phẩm theo category:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Các thao tác này thường dựa trên doc values. Đây là lý do `keyword`, số và ngày giờ thường có doc values mặc định.

### 4.2. Lấy doc values qua `docvalue_fields`

Có thể yêu cầu giá trị doc values trong search response:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": false,
  "docvalue_fields": ["category", "price"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  }
}
~~~

Hit có thể chứa:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "fields": {
    "category": ["Accessories"],
    "price": [129900]
  }
}
~~~

`docvalue_fields` trả dữ liệu trong `fields`, không tái tạo toàn bộ cấu trúc JSON. Có thể chỉ định format cho một số kiểu như date:

~~~json
{
  "_source": false,
  "docvalue_fields": [
    {
      "field": "createdAt",
      "format": "strict_date_time"
    }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Format quyết định cách giá trị được biểu diễn trong response; nó không thay đổi dữ liệu gốc của document.

### 4.3. Giới hạn của doc values

Doc values chỉ có trên các field type hỗ trợ cơ chế này. Một số điểm cần nhớ:

- `text` không có doc values thông thường. Nếu cần sort hoặc aggregation theo nội dung, thường tạo subfield `keyword`.
- `object` và `nested` không có doc values như một scalar field; các field con có mapping và doc values riêng theo kiểu dữ liệu.
- `doc_values: false` làm mất khả năng sử dụng doc values cho sort/aggregation/truy xuất tương ứng, dù field có thể vẫn được lập chỉ mục.
- Với field nhiều giá trị, thứ tự giá trị trả từ doc values không được đảm bảo giống thứ tự mảng trong `_source`.

Không dùng doc values như bản sao chính xác của JSON gốc. Chúng được tối ưu cho thao tác theo field, không nhằm tái tạo thứ tự, cấu trúc object hoặc biểu diễn ban đầu của toàn bộ document.

## 5. So sánh response của ba cơ chế

Có thể yêu cầu ba loại dữ liệu trong cùng một request nếu mapping hỗ trợ:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": ["name"],
  "stored_fields": ["sku"],
  "docvalue_fields": ["price", "category"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  },
  "sort": [
    { "price": "asc" }
  ]
}
~~~

Response minh họa:

~~~json
{
  "hits": {
    "hits": [
      {
        "_index": "products",
        "_id": "KB-001",
        "_score": null,
        "_source": {
          "name": "Mechanical Keyboard"
        },
        "fields": {
          "sku": ["KB-001"],
          "price": [129900],
          "category": ["Accessories"]
        },
        "sort": [129900]
      }
    ]
  }
}
~~~

Trong ví dụ:

- `name` đến từ `_source`.
- `sku` đến từ stored fields vì mapping có `store: true`.
- `price` và `category` đến từ doc values.
- `sort` chứa giá trị dùng để sắp xếp hit.

Không cần lấy cùng một field qua nhiều cơ chế nếu ứng dụng không sử dụng nhiều cách biểu diễn khác nhau. Yêu cầu dữ liệu dư thừa có thể làm response phức tạp và tăng chi phí truyền tải.

## 6. Bảng so sánh theo mục đích sử dụng

| Nhu cầu ứng dụng | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Dựng lại entity có object và collection | `_source` | Giữ cấu trúc JSON đầy đủ. |
| Trả về một số field của DTO | `_source` filtering | Không cần lưu riêng từng field. |
| Đọc field đã khai báo `store: true` mà không lấy source | `stored_fields` | Truy xuất bản lưu riêng của field. |
| Sort theo giá hoặc ngày tạo | Doc values | Tối ưu truy cập theo cột. |
| Aggregation theo category hoặc status | Doc values | Phù hợp cho tổng hợp trên nhiều document. |
| Script đọc giá trị scalar | Doc values nếu kiểu hỗ trợ | Cung cấp truy cập field theo cấu trúc cột. |
| Đọc field không được lập chỉ mục nhưng vẫn có trong JSON | `_source` | Không cần inverted index để lấy lại source. |
| Dựng lại document sau khi source bị tắt | Không có cơ chế thay thế tổng quát | Stored fields và doc values không tái tạo toàn bộ JSON. |

## 7. Mapping và lựa chọn cho từng kiểu field

Các kiểu field hỗ trợ các cơ chế khác nhau. Bảng dưới đây tóm tắt những trường hợp phổ biến; hãy kiểm tra mapping reference của phiên bản Elasticsearch đang chạy khi dùng kiểu đặc biệt.

| Field type | `_source` | Stored fields | Doc values | Ghi chú |
| --- | --- | --- | --- |
| `text` | Có nếu source bật | Có thể bật `store: true` | Không hỗ trợ doc values thông thường | Dùng inverted index cho full-text; thường dùng multi-field `keyword` để sort/aggregation. |
| `keyword` | Có nếu source bật | Có thể bật `store: true` | Có, mặc định thường bật | Exact match, sort và terms aggregation. |
| `long`, `integer`, `double`, `float` | Có nếu source bật | Có thể bật `store: true` | Có, mặc định thường bật | Range, sort, aggregation. |
| `date` | Có nếu source bật | Có thể bật `store: true` | Có, mặc định thường bật | Có thể định dạng khi lấy qua docvalue fields. |
| `boolean` | Có nếu source bật | Có thể bật `store: true` | Có | Lọc, sort và aggregation theo hỗ trợ của field. |
| `ip` | Có nếu source bật | Có thể bật `store: true` | Có | Truy vấn và thống kê theo địa chỉ IP. |
| `object` | Giữ cấu trúc JSON nếu source bật | Không lưu toàn bộ object như một scalar field | Không có doc values cho object tổng thể | Field con có mapping riêng. |
| `nested` | Giữ mảng object nếu source bật | Không lưu toàn bộ nested object như một scalar field | Field con có doc values riêng nếu hỗ trợ | Dùng nested query/aggregation theo semantics của nested. |

`_source` là cơ chế lưu JSON ở cấp document; hai cột stored fields và doc values mô tả cách lấy từng field. Một object có thể được giữ nguyên trong `_source` dù các field con có mapping và khả năng truy vấn riêng.

## 8. Tích hợp mapping trong Spring Data Elasticsearch

Spring Data Elasticsearch khai báo các thuộc tính `store` và `docValues` trên `@Field`. Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword, store = true)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword, docValues = true)
    private String category;

    @Field(type = FieldType.Long, docValues = true)
    private Long price;

    // Constructor, getters và setters
}
~~~

Mapping tương ứng về mặt ý tưởng:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword",
      "store": true
    },
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword",
      "doc_values": true
    },
    "price": {
      "type": "long",
      "doc_values": true
    }
  }
}
~~~

`store = true` yêu cầu Elasticsearch lưu riêng field `sku`. `docValues = true` giữ cấu trúc doc values cho các field hỗ trợ. Các kiểu `keyword`, số và date thường đã bật doc values theo mặc định, nên khai báo tường minh chủ yếu giúp thể hiện ý định mapping.

### 8.1. Mapping annotation không phải lệnh cập nhật index đã tồn tại

Thay đổi annotation không tự thay đổi mapping của index đã được tạo trước đó. Nếu `sku` trước đây có `store: false` rồi đổi thành `store: true`, các document cũ không tự có stored field mới.

Khi cần thay đổi mapping không thể cập nhật trực tiếp, hãy tạo index mới với mapping mong muốn, reindex dữ liệu và chuyển alias sau khi kiểm tra. Cần nhớ Reindex API đọc `_source`; nếu source đã bị tắt thì quy trình thông thường không thể sao chép đầy đủ document.

## 9. Đọc kết quả qua Spring Data Elasticsearch

Khi dùng repository hoặc `ElasticsearchOperations`, Spring Data thường dùng `_source` để chuyển hit thành domain object. Ví dụ:

~~~java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();
    String id = hit.getId();
    float score = hit.getScore();
}
~~~

`getContent()` là object được converter dựng từ source theo mapping metadata. Nếu request tắt `_source` và chỉ trả stored fields hoặc docvalue fields, không nên kỳ vọng `getContent()` sẽ được dựng đầy đủ như một document thông thường.

Các field trả về riêng trong response có thể được đọc từ metadata của `SearchHit`/`SearchDocument` thông qua API field map của phiên bản Spring Data đang dùng. Cấu trúc response thường chứa giá trị theo tên field trong `fields`; kiểm tra kiểu trả về thực tế và chuyển đổi có kiểm soát sang DTO.

Ví dụ minh họa cách đọc metadata field (API cụ thể có thể khác theo phiên bản):

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    Map<String, List<Object>> fields = hit.getFields();
    List<Object> storedSku = fields.get("sku");
    List<Object> priceValues = fields.get("price");
}
~~~

Không nên ép kiểu trực tiếp mà không kiểm tra null, số lượng giá trị và kiểu dữ liệu trả về. Stored fields và docvalue fields thường được biểu diễn thành danh sách vì một field có thể chứa nhiều giá trị.

### 9.1. Source filtering trong truy vấn Spring Data

Khi chỉ cần một số thuộc tính của entity, có thể cấu hình source filter trên query thay vì yêu cầu stored fields. Ví dụ REST API tương ứng:

~~~json
{
  "_source": {
    "includes": ["sku", "name", "price"]
  },
  "query": {
    "match_all": {}
  }
}
~~~

Spring Data Elasticsearch cung cấp API source filtering trên các kiểu query của nó; tên method và kiểu filter cụ thể phụ thuộc phiên bản. Hãy dùng API của dependency đang có và xác nhận request sinh ra chứa `_source.includes` như mong muốn.

## 10. Phân biệt `fields` với `stored_fields` và `docvalue_fields`

Search API còn có tham số `fields`. Đây là API lấy giá trị field theo mapping và có thể sử dụng doc values hoặc đọc từ `_source` tùy field và kiểu dữ liệu. Nó không đồng nghĩa với `stored_fields` và cũng không nên được xem là tên khác của `docvalue_fields`.

| Request option | Ý nghĩa |
| --- | --- |
| `_source` | Trả nội dung JSON gốc, có thể lọc includes/excludes. |
| `stored_fields` | Chỉ lấy field được mapping lưu riêng bằng `store: true`. |
| `docvalue_fields` | Lấy giá trị từ doc values của field hỗ trợ. |
| `fields` | API cấp cao hơn để lấy giá trị field theo mapping; nguồn dữ liệu phụ thuộc field. |

Khi cần kiểm soát rõ nguồn dữ liệu, hãy dùng đúng option tương ứng. Đặc biệt, không giả định `fields` luôn trả nguyên cấu trúc `_source` hoặc `stored_fields` luôn có thể lấy mọi field.

## 11. Multi-valued fields và cấu trúc dữ liệu

Elasticsearch cho phép một field chứa một hoặc nhiều giá trị cùng kiểu. Ba cơ chế có thể biểu diễn chúng khác nhau:

- `_source` giữ mảng theo cấu trúc JSON và thứ tự được gửi.
- Stored fields trả các giá trị field trong response `fields`; không nên dùng cách truy xuất này để tái tạo object JSON phức tạp.
- Doc values tối ưu cho xử lý theo field; với nhiều giá trị, thứ tự trả về có thể khác thứ tự mảng ban đầu.

Ví dụ source:

~~~json
{
  "tags": ["wireless", "office", "compact"]
}
~~~

Nếu lấy `tags` từ `_source`, ứng dụng nhận được mảng JSON theo thứ tự trên. Nếu dùng doc values, hãy coi các giá trị là tập giá trị field phục vụ thao tác tìm kiếm/tổng hợp; không dựa vào thứ tự gốc để hiển thị hoặc tái dựng dữ liệu.

Với object lồng nhau hoặc nested array, `_source` là cách phù hợp để giữ cấu trúc đầy đủ. Stored fields và doc values lấy từng field, không thay thế được toàn bộ quan hệ object/array.

## 12. Tác động tới query, sort và aggregation

Khả năng tìm kiếm, sắp xếp, tổng hợp và truy xuất là các việc riêng:

| Mapping và cơ chế | Query | Sort / aggregation | Đọc giá trị |
| --- | --- | --- | --- |
| `index: true`, doc values bật | Có thể query theo semantics của field. | Có nếu field hỗ trợ doc values. | `_source`, stored fields hoặc docvalue fields nếu được cấu hình. |
| `index: false`, doc values bật | Không query bằng inverted index thông thường. | Có thể sort/aggregation nếu field type hỗ trợ doc values. | `_source` hoặc docvalue fields; stored fields nếu bật. |
| `index: true`, `doc_values: false` | Query vẫn có thể hoạt động. | Sort/aggregation dựa trên doc values không khả dụng theo cách thông thường. | `_source` hoặc stored fields nếu bật. |
| `store: true` | Không tự làm field có thể query. | Không tự cung cấp doc values. | Lấy bằng `stored_fields`. |

`store` không bật query; `doc_values` không thay thế inverted index; `_source` không làm field có thể tìm kiếm. Hãy kiểm tra riêng từng yêu cầu của ứng dụng.

## 13. Chi phí và lựa chọn hiệu năng

Mỗi cơ chế có mục tiêu và chi phí khác nhau:

- `_source` lưu JSON gốc và thường là lựa chọn đơn giản nhất để dựng document. Source filtering giúp giảm payload khi không cần toàn bộ field.
- Stored fields lưu thêm giá trị riêng. Chúng hữu ích trong một số mô hình đọc nhưng tăng dung lượng và không mặc nhiên nhanh hơn `_source`.
- Doc values cần dung lượng riêng nhưng tối ưu cho sort, aggregation và truy cập field theo cột. Tắt chúng có thể tiết kiệm dung lượng nhưng làm mất các thao tác phụ thuộc.
- Inverted index là cấu trúc tìm kiếm; nó không thay thế source hoặc doc values khi cần dựng lại giá trị.

Đừng tối ưu bằng cách tắt `_source`, `store` hoặc `doc_values` chỉ dựa trên giả định. Hãy đo kích thước index, payload response, độ trễ query và tải cluster bằng dữ liệu đại diện.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `stored_fields` không trả giá trị | Field chưa được mapping `store: true`. | Đọc từ `_source` hoặc tạo index mới có stored field rồi reindex. |
| `docvalue_fields` không trả giá trị | Field không hỗ trợ doc values hoặc `doc_values` đã bị tắt. | Kiểm tra field type và mapping. |
| Sort/aggregation trên text báo lỗi | `text` không có doc values thông thường. | Dùng subfield `keyword` hoặc field phù hợp. |
| Search hit không dựng được entity đầy đủ | `_source` bị tắt hoặc request loại bỏ các field cần thiết. | Giữ `_source` hoặc dùng DTO/field retrieval có chủ đích. |
| Reindex thất bại hoặc không sao chép đủ dữ liệu | Index nguồn không có `_source` khả dụng. | Kiểm tra thiết kế source và phương án export/restore khác trước migration. |
| Thứ tự mảng khác khi đọc bằng doc values | Doc values không bảo toàn thứ tự mảng gốc. | Dùng `_source` nếu thứ tự là một phần dữ liệu nghiệp vụ. |
| Mapping annotation đã đổi nhưng response không thay đổi | Index cũ đã tồn tại với mapping trước đó. | Tạo index mới và reindex nếu thay đổi không thể áp dụng trực tiếp. |
| Stored field trả về dạng danh sách | Search response biểu diễn field trong `fields` dưới dạng array. | Đọc danh sách và xử lý trường hợp không có hoặc nhiều giá trị. |

## 15. Quy trình chọn cơ chế truy xuất

Khi thiết kế một endpoint tìm kiếm, hãy xác định:

1. Endpoint cần dựng entity đầy đủ hay chỉ cần một vài field?
2. Các object lồng nhau, collection và thứ tự mảng có cần được giữ nguyên không?
3. Field nào cần query, field nào cần sort hoặc aggregation?
4. Field có kiểu mapping hỗ trợ doc values không?
5. Có lý do thực sự để lưu riêng field bằng `store: true` không?
6. Source filtering có đáp ứng được nhu cầu giảm payload không?
7. Spring Data cần `_source` để converter dựng `SearchHit.getContent()` hay endpoint sẽ tự tạo DTO từ field metadata?
8. Có thao tác reindex/update nào phụ thuộc vào `_source` không?
9. Nếu thay đổi mapping, cần tạo index mới và reindex dữ liệu như thế nào?

Với phần lớn ứng dụng Spring Data Elasticsearch, giữ `_source` là lựa chọn mặc định hợp lý. Dùng source filtering khi cần giảm payload; chỉ bật `store: true` cho field có nhu cầu truy xuất riêng rõ ràng; giữ doc values cho các field cần sort, aggregation hoặc đọc theo cột.

## 16. Tài liệu tham khảo

- [Elasticsearch — Retrieve selected fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-fields.html)
- [Elasticsearch — The `_source` field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Elasticsearch — Stored fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-store.html)
- [Elasticsearch — Doc values](https://www.elastic.co/guide/en/elasticsearch/reference/current/doc-values.html)
- [Spring Data Elasticsearch — Search result types and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

`_source` giữ JSON gốc và là nguồn dữ liệu chính để Spring Data dựng entity. Stored fields chỉ trả các field đã bật `store: true`. Doc values lưu dữ liệu theo cột, phù hợp cho sort, aggregation và truy xuất giá trị field được hỗ trợ. Chọn cơ chế theo nhu cầu đọc, tìm kiếm và thống kê giúp response gọn mà vẫn giữ được khả năng vận hành và chuyển đổi document.
