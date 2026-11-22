# `index`, `store`, `doc_values` và giới hạn truy xuất từng loại trường

Elasticsearch có nhiều cơ chế lưu trữ và lập chỉ mục cho một field. Các tùy chọn `index`, `store` và `doc_values` quyết định field có thể được tìm kiếm, lấy lại hoặc dùng cho sắp xếp và aggregation theo cách nào. Ngoài ra, `_source` lưu nội dung JSON của document để ứng dụng có thể đọc lại dữ liệu gốc.

Ba tùy chọn này giải quyết các mục đích khác nhau:

- `index`: tạo cấu trúc phục vụ truy vấn trên field.
- `store`: lưu riêng giá trị field để có thể yêu cầu Elasticsearch trả về qua `stored_fields`.
- `doc_values`: lưu dữ liệu theo dạng cột để hỗ trợ sort, aggregation và một số thao tác script/truy xuất field.

Không nên bật cả ba theo thói quen. Hãy chọn theo cách ứng dụng tìm kiếm và đọc dữ liệu, đồng thời hiểu rằng `_source` là một cơ chế riêng.

## 1. Bốn cơ chế cần phân biệt

| Cơ chế | Mục đích chính | Cách lấy hoặc sử dụng |
| --- | --- | --- |
| Inverted index / cấu trúc tìm kiếm | Tìm document theo nội dung hoặc giá trị field. | Query như `match`, `term`, `range` tùy kiểu field và mapping. |
| `store: true` | Lưu riêng giá trị field để trả về theo yêu cầu. | `stored_fields` trong Get/Search API. |
| `doc_values: true` | Lưu dữ liệu dạng cột cho sort, aggregation và script. | `sort`, `aggs`, `docvalue_fields` và một số script. |
| `_source` | Lưu nội dung JSON của document để dựng lại dữ liệu. | Mặc định được trả về trong hit; có thể dùng source filtering. |

Các cơ chế có thể cùng tồn tại trên một field. Ví dụ một field `keyword` có thể được lập chỉ mục, có doc values và đồng thời xuất hiện trong `_source`. Điều đó không có nghĩa ba bản lưu trữ thay thế lẫn nhau.

## 2. `index` — lập chỉ mục để tìm kiếm

`index` quyết định Elasticsearch có tạo cấu trúc lập chỉ mục cho field để phục vụ truy vấn hay không. Với nhiều kiểu dữ liệu, mặc định là `true`.

### 2.1. Field có `index: true`

Khi field được lập chỉ mục, Elasticsearch có thể tìm document dựa trên field đó theo ngữ nghĩa của kiểu dữ liệu:

- Field `text` được analyzer xử lý và tạo token để tìm kiếm toàn văn.
- Field `keyword` được lập chỉ mục như giá trị nguyên vẹn để so khớp chính xác.
- Field số và ngày giờ sử dụng cấu trúc lập chỉ mục phù hợp cho truy vấn giá trị, range và sort/query theo kiểu dữ liệu.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "index": true
      },
      "status": {
        "type": "keyword",
        "index": true
      },
      "price": {
        "type": "long",
        "index": true
      }
    }
  }
}
~~~

Có thể tìm kiếm `title` bằng `match`, lọc `status` bằng `term` và lọc `price` bằng `range`.

### 2.2. Field có `index: false`

Khi đặt `index: false`, Elasticsearch không tạo cấu trúc lập chỉ mục tìm kiếm thông thường cho field. Giá trị vẫn có thể nằm trong `_source`, và nếu kiểu field hỗ trợ doc values thì doc values có thể vẫn được bật.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "debugLabel": {
        "type": "keyword",
        "index": false
      }
    }
  }
}
~~~

Ứng dụng có thể đọc `debugLabel` từ `_source`, nhưng không thể dùng nó như một field được lập chỉ mục cho các truy vấn `term` thông thường. Nếu field có doc values, vẫn có thể dùng cho những thao tác được doc values hỗ trợ như sort hoặc aggregation.

`index: false` hữu ích khi field không cần dùng để lọc hoặc tìm kiếm nhưng vẫn cần được lưu để hiển thị, sort hoặc tổng hợp. Nó có thể giảm chi phí lập chỉ mục, nhưng không tự động loại bỏ field khỏi document hoặc `_source`.

### 2.3. `index` không giống `enabled`

`index: false` áp dụng cho một field có kiểu mapping cụ thể. Với object, tùy chọn `enabled: false` có ý nghĩa khác: Elasticsearch không phân tích nội dung object đó để lập chỉ mục các field con, dù nội dung vẫn có thể được giữ trong `_source`.

Không dùng `index: false` trên một object như cách thay thế cho `enabled: false` nếu mục tiêu là ngăn Elasticsearch xử lý toàn bộ cây field con. Hãy chọn đúng tùy chọn theo kiểu field và phiên bản Elasticsearch.

## 3. `store` — lưu riêng giá trị field

Mặc định, `store` là `false`. Elasticsearch không lưu field thành một stored field riêng. Tuy nhiên, giá trị thường vẫn nằm trong `_source` nếu `_source` được bật.

Khi đặt `store: true`, Elasticsearch lưu riêng giá trị field để có thể trả về qua `stored_fields` mà không cần lấy toàn bộ `_source`.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "legacyCode": {
        "type": "keyword",
        "store": true
      }
    }
  }
}
~~~

Lấy stored field trong Search API:

~~~http
GET /articles/_search
Content-Type: application/json

{
  "stored_fields": ["legacyCode"],
  "query": {
    "match": {
      "title": "Elasticsearch guide"
    }
  }
}
~~~

Giá trị stored field được trả về trong phần `fields` của hit. Nếu muốn lấy nội dung JSON thông thường, có thể yêu cầu `_source` cùng lúc hoặc dùng source filtering theo nhu cầu.

### 3.1. Khi nào cần `store: true`?

Có thể cân nhắc stored field khi:

- Ứng dụng thường xuyên chỉ cần lấy một vài field riêng lẻ và không muốn đọc toàn bộ `_source`.
- Có lý do rõ ràng để truy xuất field bằng `stored_fields`.
- Field cần được lưu riêng theo thiết kế dữ liệu hoặc API đọc.

Trong phần lớn ứng dụng, `_source` đã đáp ứng tốt việc lấy dữ liệu document. Bật `store: true` cho mọi field thường làm tăng chi phí lưu trữ và ghi mà không mang lại lợi ích đáng kể.

### 3.2. `store` không làm field có thể tìm kiếm

`store: true` chỉ điều khiển việc lưu riêng giá trị field để truy xuất. Nó không thay thế `index: true`.

Ví dụ field có `index: false, store: true` có thể được trả về bằng `stored_fields`, nhưng không trở thành field có thể dùng để tìm kiếm bằng `term` hoặc `match` như field đã lập chỉ mục.

Ngược lại, field có `index: true, store: false` vẫn có thể tìm kiếm bình thường. Nếu `_source` được bật, ứng dụng vẫn đọc lại giá trị từ `_source`.

## 4. `doc_values` — lưu trữ dạng cột

`doc_values` là cấu trúc lưu trữ theo dạng cột, được tối ưu cho các thao tác cần đọc giá trị field trên nhiều document, chẳng hạn:

- Sắp xếp kết quả theo giá trị field.
- Aggregation như `terms`, `min`, `max`, `avg`, `sum` tùy kiểu dữ liệu.
- Truy xuất giá trị bằng `docvalue_fields`.
- Một số thao tác script cần đọc giá trị field.

Với hầu hết kiểu field hỗ trợ doc values, mặc định `doc_values` là `true`. Field `text` không hỗ trợ doc values theo cách thông thường.

### 4.1. Ví dụ doc values

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

Sắp xếp theo giá:

~~~json
{
  "sort": [
    { "price": { "order": "asc" } }
  ]
}
~~~

Tổng hợp theo category:

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

### 4.2. Tắt doc values

Đặt `doc_values: false` sẽ ngăn Elasticsearch tạo doc values cho field hỗ trợ tùy chọn này. Nếu field vẫn có `index: true`, nó vẫn có thể được tìm kiếm, nhưng các thao tác dựa trên doc values như sort và aggregation thông thường sẽ không khả dụng hoặc không hoạt động theo cách mong muốn.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "eventCode": {
        "type": "keyword",
        "index": true,
        "doc_values": false
      }
    }
  }
}
~~~

Field `eventCode` vẫn có thể được dùng cho truy vấn chính xác, nhưng không thể dùng doc values để sort/aggregation trên field này. Chỉ tắt doc values khi chắc chắn ứng dụng không cần các thao tác đó.

### 4.3. `index: false` nhưng `doc_values: true`

Hai tùy chọn này độc lập. Một field có thể không được lập chỉ mục cho truy vấn nhưng vẫn giữ doc values để sort hoặc aggregation:

~~~json
{
  "mappings": {
    "properties": {
      "reportingGroup": {
        "type": "keyword",
        "index": false,
        "doc_values": true
      }
    }
  }
}
~~~

Đây là lựa chọn có thể phù hợp nếu ứng dụng chỉ cần nhóm hoặc sắp xếp theo `reportingGroup` mà không cần tìm document theo giá trị đó. Hãy thử các thao tác thực tế cần dùng để xác nhận kiểu field hỗ trợ hành vi mong muốn.

### 4.4. Lấy giá trị bằng `docvalue_fields`

Có thể yêu cầu Elasticsearch trả về giá trị doc values trong phần `fields` của hit:

~~~http
GET /products/_search
Content-Type: application/json

{
  "_source": false,
  "docvalue_fields": ["price", "createdAt"],
  "query": {
    "match_all": {}
  }
}
~~~

`docvalue_fields` chỉ hoạt động với field có doc values và kiểu dữ liệu hỗ trợ. Nó không trả về toàn bộ object JSON, không thay thế `_source` và không phải cơ chế lấy mọi loại field. Với date, có thể chỉ định format để điều khiển cách giá trị ngày giờ được trả về.

Doc values được tối ưu cho truy cập theo field trên nhiều document, không nhằm tái tạo nguyên vẹn cấu trúc JSON ban đầu. Đối với field nhiều giá trị, thứ tự hoặc cách biểu diễn trả về có thể khác với thứ tự trong `_source`; không dùng doc values như bản sao byte-for-byte của mảng gốc.

## 5. `_source` — nội dung JSON gốc của document

`_source` lưu nội dung JSON được gửi khi index document. Đây là nguồn dữ liệu thông dụng để trả về document và chuyển đổi thành entity Java trong Spring Data Elasticsearch.

Ví dụ một hit:

~~~json
{
  "_index": "products",
  "_id": "KB-001",
  "_source": {
    "name": "Mechanical Keyboard",
    "category": "Accessories",
    "price": 129900,
    "reportingGroup": "peripherals"
  }
}
~~~

`_source` độc lập với `index`, `store` và `doc_values` của từng field:

- Field có `index: false` vẫn có thể xuất hiện trong `_source`.
- Field có `store: false` vẫn có thể được đọc từ `_source`.
- Field có `doc_values: false` vẫn có thể được đọc từ `_source`.
- Field có `index: true` không nhất thiết phải có `store: true` để đọc lại nội dung.

### 5.1. Source filtering

Khi chỉ cần một số field, có thể lọc `_source` trong request:

~~~json
{
  "_source": ["name", "category"],
  "query": {
    "term": {
      "category": "Accessories"
    }
  }
}
~~~

Source filtering giảm lượng nội dung JSON được trả về qua mạng và lượng dữ liệu cần chuyển đổi ở client. Nó không đồng nghĩa với việc các field còn lại bị xóa khỏi index hoặc không được lưu trong `_source`.

Có thể loại trừ field bằng cú pháp `excludes` hoặc kết hợp `includes`/`excludes` theo API. Đây là cách tối ưu payload response khi ứng dụng không cần toàn bộ document.

### 5.2. Khi nào tắt `_source`?

Elasticsearch cho phép cấu hình `_source` disabled trong một số trường hợp, nhưng điều đó làm mất khả năng lấy lại JSON gốc theo cách thông thường. Những thao tác phụ thuộc vào source như reindex, update document dựa trên source, hoặc chuyển đổi search hit thành entity đầy đủ có thể bị hạn chế.

Với ứng dụng Spring Data Elasticsearch, `_source` thường cần thiết để converter dựng lại entity từ kết quả tìm kiếm. Chỉ cân nhắc tắt `_source` khi đã thiết kế cơ chế lưu và truy xuất thay thế, đồng thời chấp nhận các giới hạn vận hành liên quan.

## 6. Khả năng theo từng kiểu field

Các field type không hỗ trợ mọi tùy chọn như nhau. Bảng dưới đây tóm tắt các trường hợp thường gặp; cần kiểm tra tài liệu của đúng phiên bản Elasticsearch và kiểu field đang sử dụng.

| Field type | `index` | `store` | `doc_values` | Ghi chú |
| --- | --- | --- | --- | --- |
| `text` | Có | Có | Không hỗ trợ doc values thông thường | Dùng inverted index cho full-text; muốn sort/aggregation thường dùng subfield `keyword`. |
| `keyword` | Có | Có | Có, mặc định thường bật | Phù hợp exact match, sort và terms aggregation. |
| `long`, `integer`, `double`, `float` | Có | Có | Có, mặc định thường bật | Hỗ trợ truy vấn số, sort và aggregation. |
| `date` | Có | Có | Có, mặc định thường bật | Có thể query theo khoảng và sort theo thời gian. |
| `boolean` | Có | Có | Có | Có thể lọc và tổng hợp theo giá trị boolean. |
| `ip` | Có | Có | Có | Có thể lọc theo địa chỉ hoặc range IP, sort và aggregation theo hỗ trợ của kiểu. |
| `object` | Không áp dụng như field scalar | Không áp dụng như scalar | Không áp dụng như scalar | Các field con mới có mapping và tùy chọn riêng. |
| `nested` | Không áp dụng như field scalar | Không áp dụng như scalar | Không áp dụng như scalar | Các field con bên trong nested object có tùy chọn riêng. |

Với `text`, nếu thật sự cần aggregation/sort trên nội dung, Elasticsearch có tùy chọn fielddata nhưng có thể tiêu tốn nhiều heap. Thiết kế thường được khuyến nghị là dùng multi-field: một field `text` cho tìm kiếm toàn văn và một subfield `keyword` cho exact match, sort hoặc aggregation.

## 7. Kết hợp các tùy chọn trong cùng mapping

Ví dụ mapping cho catalog:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "index": true
      },
      "category": {
        "type": "keyword",
        "index": true,
        "doc_values": true
      },
      "reportingGroup": {
        "type": "keyword",
        "index": false,
        "doc_values": true
      },
      "legacyCode": {
        "type": "keyword",
        "index": false,
        "store": true
      },
      "price": {
        "type": "long",
        "index": true,
        "doc_values": true
      },
      "description": {
        "type": "text",
        "index": true,
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Với mapping này:

- `title` dùng để tìm kiếm toàn văn.
- `category` dùng để lọc chính xác, sort hoặc aggregation.
- `reportingGroup` không được lập chỉ mục tìm kiếm nhưng vẫn có thể dùng doc values cho sort/aggregation.
- `legacyCode` có thể được trả về qua `stored_fields`, nhưng không dùng để tìm kiếm bằng inverted index.
- `price` dùng cho range query, sort và aggregation.
- `description` có thể tìm toàn văn qua field chính và dùng `description.raw` khi cần thao tác theo chuỗi nguyên vẹn.

Các giá trị vẫn có thể nằm trong `_source` nếu source được bật. Không cần bật `store: true` cho `title`, `category` hoặc `price` chỉ để ứng dụng đọc lại chúng.

## 8. Lấy dữ liệu bằng các cơ chế khác nhau

Có thể kết hợp source filtering, stored fields và docvalue fields trong một search request:

~~~http
GET /catalog/_search
Content-Type: application/json

{
  "_source": ["title", "category"],
  "stored_fields": ["legacyCode"],
  "docvalue_fields": ["price"],
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

Response hit có thể chứa:

- `_source` với các field `title` và `category` được chọn.
- `fields.legacyCode` cho stored field.
- `fields.price` cho doc value.
- Metadata như `_index`, `_id` và `_score` theo loại request.

Không nên yêu cầu cả ba cơ chế cho cùng một field nếu không có lý do. Chọn một cách truy xuất đơn giản nhất đáp ứng yêu cầu của ứng dụng.

## 9. Khai báo trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp các thuộc tính trên annotation `@Field` để mô tả mapping. Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog")
public class CatalogItem {

    @Id
    private String id;

    @Field(type = FieldType.Text, index = true)
    private String title;

    @Field(
        type = FieldType.Keyword,
        index = true,
        docValues = true
    )
    private String category;

    @Field(
        type = FieldType.Keyword,
        index = false,
        docValues = true
    )
    private String reportingGroup;

    @Field(
        type = FieldType.Keyword,
        index = false,
        store = true
    )
    private String legacyCode;

    @Field(
        type = FieldType.Long,
        index = true,
        docValues = true
    )
    private Long price;

    // Constructor, getters và setters
}
~~~

Các thuộc tính có ý nghĩa tương ứng với mapping Elasticsearch:

- `index = true`: lập chỉ mục field để tìm kiếm.
- `index = false`: không lập chỉ mục field cho truy vấn thông thường.
- `store = true`: lưu riêng field để lấy bằng stored fields.
- `docValues = true`: bật doc values nếu kiểu field hỗ trợ.

Các giá trị mặc định của annotation thường phản ánh mặc định mapping Elasticsearch, nhưng nên khai báo tường minh khi thiết kế có yêu cầu đặc biệt. Hãy xác nhận API annotation theo phiên bản Spring Data Elasticsearch của dự án.

### 9.1. Dùng multi-field cho text và keyword

Một thuộc tính Java có thể được lập chỉ mục theo nhiều cách thông qua multi-field. Field chính là `text` để tìm kiếm toàn văn, còn subfield `keyword` phục vụ exact match, sort và aggregation:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String description;
~~~

Khi đó mapping tương ứng có thể chứa `description` kiểu `text` và `description.keyword` kiểu `keyword`. Search toàn văn dùng `description`; sort hoặc aggregation thường dùng `description.keyword`.

Multi-field không tạo thêm thuộc tính Java độc lập và không thay đổi `_source`; nó tạo nhiều cách lập chỉ mục cho cùng một giá trị nguồn.

## 10. Ảnh hưởng tới query, sort và aggregation

| Thiết lập | Query | Sort | Aggregation | Truy xuất giá trị |
| --- | --- | --- | --- | --- |
| `index: true`, doc values bật | Hỗ trợ query theo kiểu field. | Hỗ trợ trên kiểu có doc values. | Hỗ trợ trên kiểu có doc values. | `_source`; thêm stored/docvalue fields nếu cấu hình. |
| `index: false`, doc values bật | Không dùng như field được lập chỉ mục cho query thông thường. | Có thể dùng trên kiểu hỗ trợ doc values. | Có thể dùng trên kiểu hỗ trợ doc values. | `_source` hoặc docvalue fields; stored fields nếu bật. |
| `index: true`, `doc_values: false` | Vẫn query được theo cấu trúc index. | Sort dựa trên doc values không khả dụng theo cách thông thường. | Aggregation dựa trên doc values không khả dụng theo cách thông thường. | `_source`; stored fields nếu bật. |
| `index: false`, `store: true`, doc values tắt | Không query được như field đã lập chỉ mục. | Không có doc values để sort. | Không có doc values để aggregation. | Có thể lấy qua stored fields hoặc `_source`. |

Khả năng cụ thể còn phụ thuộc field type và query/aggregation đang dùng. Bảng này mô tả cách thiết kế phổ biến, không thay thế tài liệu mapping cho từng loại field.

## 11. Chi phí lưu trữ và hiệu năng

Mỗi cơ chế có chi phí riêng:

- Inverted index hoặc cấu trúc lập chỉ mục làm tăng dung lượng index nhưng giúp truy vấn hiệu quả.
- Stored fields lưu thêm bản sao riêng của giá trị field, có thể tăng dung lượng và chi phí ghi.
- Doc values cần dung lượng lưu trữ nhưng giúp sort/aggregation hiệu quả mà không phải nạp toàn bộ giá trị vào heap.
- `_source` giữ JSON gốc, hữu ích cho việc trả document, update và reindex; kích thước phụ thuộc dữ liệu được lưu.

Không nên tắt index chỉ để tiết kiệm dung lượng nếu ứng dụng cần tìm kiếm theo field đó. Không nên tắt doc values nếu dashboard hoặc API cần sort/aggregation. Không nên bật store cho mọi field nếu `_source` đã đáp ứng truy xuất.

Với field text cần aggregation, bật `fielddata` có thể nạp dữ liệu vào heap và làm tăng đáng kể áp lực bộ nhớ. Subfield `keyword` thường là lựa chọn phù hợp hơn cho exact match và aggregation.

## 12. Thay đổi các tùy chọn sau khi index đã tồn tại

Các tùy chọn mapping như `index`, `store` và `doc_values` thường không thể tùy ý đổi trực tiếp trên field đã được tạo. Đặc biệt, thay đổi cách lập chỉ mục ảnh hưởng cấu trúc index hiện hữu.

Khi cần thay đổi mapping, cách thông dụng là:

1. Tạo index mới với mapping có `index`, `store` và `doc_values` theo thiết kế mới.
2. Reindex dữ liệu từ index cũ sang index mới.
3. Kiểm tra truy vấn, sort, aggregation và cách lấy source/stored/doc values.
4. Chuyển alias sang index mới sau khi dữ liệu được xác minh.

Thay đổi mapping field hiện có không tự tái tạo dữ liệu lập chỉ mục cũ. Nếu chỉ thêm multi-field mới, các document cũ cũng cần được cập nhật/reindex để subfield mới có dữ liệu tìm kiếm tương ứng.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `term` query không tìm thấy field | Field có `index: false`. | Bật index trên index mới nếu cần query, sau đó reindex dữ liệu. |
| `stored_fields` không trả về giá trị | Field chưa được khai báo `store: true`. | Bật store trong mapping mới hoặc đọc field từ `_source`. |
| Sort hoặc aggregation báo lỗi/không có dữ liệu | Field không hỗ trợ doc values hoặc đã đặt `doc_values: false`. | Dùng kiểu field hỗ trợ doc values, bật lại trên index mới hoặc dùng subfield phù hợp. |
| Không aggregation được trên `text` | `text` không có doc values thông thường. | Tạo subfield `keyword` và aggregation trên subfield. |
| Tắt store nhưng ứng dụng vẫn đọc được field | Giá trị vẫn có trong `_source`. | Đây là hành vi bình thường; store và source là hai cơ chế riêng. |
| Đổi mapping nhưng dữ liệu cũ không thay đổi | Inverted index/doc values cũ không tự được xây dựng lại. | Tạo index mới và reindex. |
| `docvalue_fields` không trả về field | Field không hỗ trợ hoặc doc values bị tắt. | Kiểm tra kiểu mapping và `doc_values`. |

## 14. Cách chọn cấu hình cho từng nhu cầu

Khi thiết kế mapping, có thể dùng các quy tắc thực tế sau:

1. Field cần tìm kiếm toàn văn: dùng `text` với `index: true`; thêm subfield `keyword` nếu cần sort/aggregation.
2. Field cần lọc chính xác, sort hoặc aggregation: dùng `keyword` hoặc kiểu scalar phù hợp, giữ `index: true` và doc values theo mặc định.
3. Field chỉ dùng để sort hoặc aggregation: cân nhắc `index: false` nhưng giữ doc values nếu kiểu hỗ trợ.
4. Field không cần tìm kiếm nhưng phải lấy riêng bằng `stored_fields`: cân nhắc `store: true`; nếu `_source` đã đủ thì không cần store riêng.
5. Field chỉ cần trả về cùng document: thường giữ `_source`, không cần bật `store` chỉ vì muốn đọc field.
6. Field không cần tìm kiếm, sort hoặc aggregation: cân nhắc giảm các cấu trúc index không cần thiết nhưng vẫn xác định rõ cách ứng dụng lấy dữ liệu.
7. Trước khi tắt `_source`, đánh giá tác động tới entity conversion, update và reindex.

`index`, `store` và `doc_values` là ba tùy chọn độc lập: `index` phục vụ tìm kiếm, `store` phục vụ truy xuất field riêng và `doc_values` phục vụ sort/aggregation/script. `_source` giữ JSON gốc và thường là cơ chế đọc dữ liệu mặc định của Spring Data Elasticsearch. Chọn đúng cơ chế theo từng field giúp cân bằng khả năng tìm kiếm, cách truy xuất, dung lượng index và hiệu năng.
