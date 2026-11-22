# Chọn mapping và doc_values phù hợp trước khi tối ưu query

Hiệu năng query trong Elasticsearch phụ thuộc rất lớn vào cách document được lập chỉ mục. Một query có thể viết gọn và đúng cú pháp nhưng vẫn chậm nếu field dùng sai kiểu, analyzer không phù hợp, sort/aggregation phải nạp fielddata vào heap, hoặc mapping tạo ra quá nhiều cấu trúc không cần thiết.

Trong Spring Data Elasticsearch, mapping thường được khai báo bằng annotation trên entity hoặc được tạo tường minh qua IndexOperations. Các quyết định như text hay keyword, bật index hay doc_values, có tạo multi-field hay không sẽ ảnh hưởng trực tiếp tới cách Elasticsearch lưu và truy cập dữ liệu.

Nguyên tắc quan trọng là thiết kế mapping theo cách field sẽ được sử dụng: tìm kiếm toàn văn, lọc chính xác, sắp xếp, aggregation, script hay chỉ trả về trong response. Đừng bắt đầu bằng việc bật thêm cache hoặc tăng heap trước khi xác nhận field có representation phù hợp.

Bài này giải thích inverted index, doc values và _source; cách chọn field type; các trade-off giữa index và doc_values; mapping trong Spring Data Elasticsearch; cách kiểm tra chi phí và quy trình thay đổi mapping an toàn.

## 1. Mapping quyết định cách Elasticsearch lưu field

Mapping mô tả cấu trúc và cách Elasticsearch xử lý từng field trong document. Nó không chỉ là schema để validate JSON. Mapping quyết định field được phân tích thành token, được lập chỉ mục để tìm kiếm, được lưu trong cấu trúc cột để sort/aggregation, hoặc chỉ được giữ trong source.

Ví dụ document sản phẩm:

~~~json
{
  "sku": "SKU-1001",
  "name": "Wireless Ergonomic Mouse",
  "description": "Bluetooth mouse with rechargeable battery",
  "category": "Accessories",
  "priceInCents": 259900,
  "stock": 42,
  "active": true,
  "createdAt": "2026-11-13T08:00:00Z"
}
~~~

Một trang tìm kiếm sản phẩm có thể cần:

- Tìm từ khóa trong name và description.
- Lọc chính xác theo category, active và sku.
- Lọc khoảng giá trên priceInCents.
- Sort theo priceInCents hoặc createdAt.
- Aggregation đếm sản phẩm theo category.
- Trả name, description và các field khác cho người dùng.

Không phải mọi field đều cần cùng một cấu trúc. name phù hợp với text để tìm toàn văn; category phù hợp với keyword để lọc và group; priceInCents phù hợp với long để range query và sort; createdAt phù hợp với date.

Một mapping được thiết kế tốt giúp Elasticsearch thực hiện đúng loại thao tác mà query yêu cầu mà không phải tạo cấu trúc đắt đỏ khi query chạy.

## 2. Ba cách lưu trữ cần phân biệt: inverted index, doc values và _source

Elasticsearch sử dụng nhiều cấu trúc lưu trữ khác nhau cho một field. Ba khái niệm thường bị nhầm lẫn là inverted index, doc values và _source.

### 2.1. Inverted index

Inverted index ánh xạ term tới danh sách document chứa term đó. Nó là cấu trúc chính cho các truy vấn tìm kiếm.

Với numeric và một số field chuyên biệt, Elasticsearch có thể dùng cấu trúc index như BKD tree để phục vụ range query thay vì biểu diễn mọi giá trị như term trong inverted index truyền thống. Thuộc tính mapping index là khái niệm rộng hơn một cấu trúc lưu trữ cụ thể.

Ví dụ text field name sau khi analyzer xử lý:

~~~text
"Wireless Ergonomic Mouse"
        |
        v
["wireless", "ergonomic", "mouse"]
~~~

Inverted index có thể giúp Elasticsearch tìm document chứa term mouse hoặc kết hợp nhiều term theo query.

Với keyword, giá trị thường được index như một term nguyên vẹn, phù hợp với term query, exact filter và các thao tác tìm kiếm chính xác.

### 2.2. Doc values

Doc values là cấu trúc lưu trữ theo hướng document-to-value, thường được gọi là column-oriented hoặc columnar. Thay vì đi từ một term tới document, Elasticsearch có thể đọc giá trị của một field theo tập document để phục vụ:

- Sort.
- Aggregation.
- Truy cập field trong script qua doc values.
- Một số thao tác nội bộ cần đọc giá trị theo document.

Ví dụ category có doc values cho phép aggregation nhóm các document theo giá trị category. priceInCents có doc values cho phép sort theo giá và tính min/max/avg.

Doc values thường được lưu trên disk theo định dạng tối ưu cho truy cập cột và có thể tận dụng filesystem cache. Chúng không giống một bản sao đầy đủ của field trong Java heap.

### 2.3. _source

_source là bản JSON của document được lưu để có thể trả lại hoặc xử lý lại nội dung gốc. Nó thường được bật mặc định.

_source hữu ích cho:

- Trả document cho ứng dụng.
- Reindex.
- Update API.
- Đọc field trong một số script hoặc fetch operation.
- Điều tra dữ liệu đã ghi.

_source không phải inverted index và cũng không phải doc values. Việc một field có trong _source không có nghĩa field đó có thể được sort hoặc aggregate hiệu quả.

| Cấu trúc | Hướng truy cập chính | Mục đích điển hình |
|---|---|---|
| Inverted index | Term → document | Search, term/match/range query tùy field |
| Doc values | Document → field value | Sort, aggregation, script |
| _source | Document → JSON ban đầu | Fetch, update, reindex, hiển thị |

Một field có thể có inverted index và doc values cùng lúc. Ví dụ keyword và numeric field thường hỗ trợ cả hai theo mặc định.

## 3. Chọn field type theo cách query sử dụng

Không chọn kiểu field chỉ dựa trên kiểu Java. Cần xem field được tìm kiếm như thế nào.

| Nhu cầu | Field type thường phù hợp |
|---|---|
| Tìm kiếm ngôn ngữ tự nhiên, phân tích token | text |
| Exact match, filter, sort, terms aggregation | keyword |
| Giá, số lượng, điểm số | integer, long, float, double hoặc scaled_float |
| Thời điểm | date hoặc date_nanos |
| true/false | boolean |
| Địa chỉ IP | ip |
| Vị trí địa lý | geo_point hoặc geo_shape |
| Object có cấu trúc | object |
| Object cần truy vấn độc lập từng phần tử | nested |
| Key/value động nhưng không muốn mapping cho từng key | flattened trong trường hợp phù hợp |

Hãy chọn field type theo query pattern và semantics dữ liệu. Chuyển một giá trị số thành keyword chỉ vì muốn exact match có thể làm range query và numeric sorting kém phù hợp. Ngược lại, dùng text cho một mã định danh có thể khiến exact filter hoạt động không như mong đợi.

## 4. text và keyword: khác biệt quan trọng nhất

### 4.1. text dùng cho full-text search

text field được analyzer xử lý trước khi index. Analyzer thường gồm character filter, tokenizer và token filters.

Ví dụ:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "standard"
  }
}
~~~

Với text field, query match có thể tìm theo token đã phân tích. Field này thường không có doc values mặc định, vì mục đích chính là full-text search.

Text phù hợp cho:

- Tên sản phẩm.
- Mô tả.
- Nội dung bài viết.
- Log message.
- Văn bản cần match theo từ hoặc cụm từ.

Text không phải lựa chọn mặc định cho sort hoặc terms aggregation. Muốn sort/group theo giá trị nguyên vẹn, thường dùng thêm keyword sub-field.

### 4.2. keyword dùng cho exact value

keyword không phân tích chuỗi thành các token theo cách của text. Nó lưu giá trị như một term, phù hợp với exact matching và bucket aggregation.

~~~json
{
  "category": {
    "type": "keyword"
  }
}
~~~

Ví dụ query:

~~~json
{
  "term": {
    "category": "Accessories"
  }
}
~~~

Keyword thường phù hợp với:

- SKU và mã định danh.
- Trạng thái.
- Category.
- Country code.
- Email hoặc username khi cần exact match.
- Các field dùng để sort hoặc terms aggregation.

Nếu cần chuẩn hóa chữ hoa/thường mà vẫn giữ exact semantics, có thể dùng keyword normalizer:

~~~json
{
  "sku": {
    "type": "keyword",
    "normalizer": "lowercase_normalizer"
  }
}
~~~

Normalizer được định nghĩa trong analysis settings của index. Hãy đảm bảo ứng dụng và query gửi giá trị theo quy tắc chuẩn hóa đã chọn.

### 4.3. Multi-fields: vừa full-text vừa exact

Một field có thể có nhiều representation thông qua multi-fields. Ví dụ name có text chính và keyword sub-field:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Khi đó:

- Query full-text dùng name.
- Exact filter dùng name.keyword.
- Sort dùng name.keyword.
- Terms aggregation dùng name.keyword.

Ví dụ:

~~~json
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

Không phải mọi text field đều cần keyword sub-field. Chỉ tạo khi có use case exact/sort/aggregation. Nếu field có thể dài tùy ý, cân nhắc ignore_above và cách ứng dụng xử lý giá trị vượt ngưỡng.

ignore_above khiến giá trị dài hơn giới hạn không được index vào keyword sub-field; giá trị vẫn có thể còn trong _source. Khi đó document vẫn có thể được tìm qua text field, nhưng không có keyword term/doc value tương ứng để sort hoặc aggregate theo giá trị đó.

## 5. Doc values hoạt động như thế nào?

Doc values tổ chức dữ liệu theo field để có thể đọc giá trị của field trên nhiều document mà không phải dựng toàn bộ dữ liệu vào heap như fielddata của text.

Ví dụ aggregation:

~~~json
{
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Elasticsearch cần đọc category của các document phù hợp rồi gom nhóm. Doc values cung cấp representation phù hợp cho công việc đó.

Ví dụ sort:

~~~json
{
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

Doc values cho phép lấy giá trị priceInCents để so sánh và sắp xếp các hit.

### 5.1. Field type nào có doc values?

Doc values được hỗ trợ bởi nhiều field type thường dùng cho sort và aggregation, chẳng hạn keyword, numeric, date, boolean và một số loại field khác.

text không có doc values theo cách thông thường. Một số field type có quy tắc hỗ trợ riêng hoặc không hỗ trợ doc values. Hãy kiểm tra tài liệu mapping của đúng field type và Elasticsearch version trước khi cấu hình.

Với các field hỗ trợ, doc_values thường được bật mặc định. Không cần khai báo doc_values: true cho mọi field nếu đó đã là default. Hãy khai báo rõ khi muốn tắt và đã xác nhận không có query pattern nào cần nó.

### 5.2. Doc values không phải cache trong RAM

Doc values thường được lưu trên disk và đọc qua cơ chế truy cập theo cột. Filesystem cache có thể giữ các page được truy cập thường xuyên trong memory, nhưng không đồng nghĩa toàn bộ field được nạp vào Java heap.

Điều này khác với fielddata của text, vốn có thể tiêu thụ heap đáng kể. Tuy nhiên, doc values không miễn phí: chúng chiếm disk, tạo chi phí indexing/merge và sort/aggregation vẫn cần CPU, memory cho bucket hoặc sort state.

Không suy luận rằng bật doc values sẽ làm mọi aggregation nhanh tức thì. Hiệu năng còn phụ thuộc số document, cardinality, số bucket, shard count, filter selectivity và cache.

## 6. index và doc_values là hai lựa chọn độc lập

Hai tham số thường bị nhầm:

- index: field có được lập chỉ mục cho truy vấn hay không.
- doc_values: field có representation theo cột cho các thao tác như sort/aggregation hay không.

Với field type hỗ trợ cả hai, có thể cấu hình theo các nhu cầu khác nhau:

| index | doc_values | Ý nghĩa thường gặp |
|---|---|---|
| true | true | Có thể search và dùng cho sort/aggregation |
| true | false | Có inverted index nhưng không có doc values |
| false | true | Không có inverted index cho search thông thường, nhưng có thể dùng doc values cho sort/aggregation/script được hỗ trợ |
| false | false | Chỉ giữ source theo cấu hình, không có hai cấu trúc này cho field |

Cần kiểm tra khả năng cụ thể theo field type. index: false không biến field thành field có thể term-query chỉ nhờ doc values. doc_values: false cũng không tắt inverted index nếu index vẫn true.

### 6.1. Khi nào tắt index?

Nếu field chỉ cần sort/aggregation và không cần query trực tiếp, có thể xem xét index: false nhưng giữ doc values nếu field type hỗ trợ.

Ví dụ field internalRank chỉ dùng để sort:

~~~json
{
  "internalRank": {
    "type": "long",
    "index": false,
    "doc_values": true
  }
}
~~~

Trước khi chọn cách này, kiểm tra mọi query thực tế. Nếu sau này cần range filter hoặc term query trên field, cấu hình hiện tại có thể không đáp ứng.

### 6.2. Khi nào tắt doc_values?

Nếu field chỉ cần được tìm kiếm bằng inverted index và không bao giờ được sort, aggregate hoặc truy cập qua doc values, có thể cân nhắc tắt doc values cho field type hỗ trợ tùy chọn này.

~~~json
{
  "externalReference": {
    "type": "keyword",
    "index": true,
    "doc_values": false
  }
}
~~~

Việc tắt có thể giảm chi phí lưu trữ/indexing, nhưng sẽ làm mất khả năng sử dụng field cho sort và aggregation dựa trên doc values. Không tắt nếu query, script hoặc dashboard hiện tại cần nó.

### 6.3. Chỉ lưu source

Nếu field chỉ được trả về cho client và không cần search, sort, aggregation hoặc script access, có thể cân nhắc không index và không tạo doc values:

~~~json
{
  "longDescription": {
    "type": "text",
    "index": false
  }
}
~~~

Với text, doc values vốn không được hỗ trợ mặc định. Field vẫn có thể nằm trong _source để trả về, nếu _source được bật.

Cần phân biệt field source-only với store: true. Stored field là một cơ chế lưu riêng; không cần bật store chỉ để trả field nếu _source đã đáp ứng yêu cầu.

## 7. Vì sao không nên bật fielddata cho text một cách tùy tiện?

Elasticsearch có tùy chọn fielddata cho text field để hỗ trợ sort/aggregation trên text. Khi bật, fielddata được xây dựng từ inverted index và có thể chiếm nhiều heap.

Ví dụ:

~~~json
{
  "description": {
    "type": "text",
    "fielddata": true
  }
}
~~~

Đây thường không phải lựa chọn đầu tiên. Nếu cần exact sort hoặc terms aggregation, tạo keyword multi-field thường phù hợp hơn:

~~~json
{
  "description": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Fielddata trên text có thể cần thiết cho một số use case đặc biệt, ví dụ aggregation trên token đã phân tích. Nhưng cần đánh giá heap, cardinality, số shard và fielddata cache.

Trước khi bật fielddata, hãy trả lời:

- Có thật sự cần aggregate token thay vì giá trị nguyên vẹn không?
- Có thể dùng keyword multi-field không?
- Cardinality của field là bao nhiêu?
- Heap còn đủ không?
- Có thể giới hạn query hoặc dùng filter để giảm document tham gia không?

Không bật fielddata chỉ để làm biến mất lỗi kiểu “Fielddata is disabled on text fields”. Lỗi đó thường cho thấy query đang dùng sai representation.

## 8. Chọn mapping cho numeric và date

Numeric field nên dùng kiểu số tương ứng với miền giá trị và độ chính xác.

| Kiểu | Trường hợp thường dùng |
|---|---|
| byte, short, integer, long | Số nguyên với miền giá trị phù hợp |
| unsigned_long | Số nguyên không âm có miền lớn, khi được hỗ trợ |
| half_float, float, double | Số thực |
| scaled_float | Số thực có scale cố định, ví dụ giá trị tiền theo đơn vị nhỏ |

Ví dụ tiền:

~~~json
{
  "priceInCents": {
    "type": "long"
  }
}
~~~

Lưu tiền dưới dạng số nguyên đơn vị nhỏ thường tránh sai số floating point. Nếu dùng scaled_float, phải chọn scaling_factor đúng với độ chính xác nghiệp vụ.

Numeric field thường có cấu trúc index tối ưu cho truy vấn số, chẳng hạn range query, cùng doc values theo cấu hình mặc định. Doc values hữu ích cho sort, aggregation và script.

Date field:

~~~json
{
  "createdAt": {
    "type": "date",
    "format": "strict_date_optional_time||epoch_millis"
  }
}
~~~

Date thường được lưu nội bộ dưới dạng số thời gian và hỗ trợ sort/aggregation qua doc values. Chọn format phù hợp với dữ liệu ghi và query. Đừng biến timestamp thành keyword nếu cần range query theo thời gian.

## 9. Mapping cho boolean, IP và field đặc thù

Boolean phù hợp cho cờ trạng thái:

~~~json
{
  "active": {
    "type": "boolean"
  }
}
~~~

IP phù hợp cho IPv4/IPv6 và hỗ trợ các truy vấn IP chuyên biệt:

~~~json
{
  "clientIp": {
    "type": "ip"
  }
}
~~~

Geo field cần mapping đúng loại, ví dụ geo_point cho tọa độ điểm. Các field type đặc thù có khả năng sort, aggregation hoặc doc values riêng; đừng áp dụng quy tắc của keyword/numeric cho tất cả.

Nếu field chỉ phục vụ display, có thể không cần lập chỉ mục. Nếu cần tìm theo prefix, range hoặc geo distance, chọn type và query phù hợp từ đầu.

## 10. Object, nested và flattened cũng ảnh hưởng query

Object thông thường được flatten thành các path field. Với array object, query trên các field có thể match chéo giữa các phần tử nếu dùng object mapping thông thường.

Ví dụ:

~~~json
{
  "offers": [
    { "seller": "A", "price": 100 },
    { "seller": "B", "price": 500 }
  ]
}
~~~

Nếu cần bảo đảm seller và price thuộc cùng một phần tử, có thể cần nested mapping và nested query. Nested có chi phí lưu trữ và query cao hơn object thông thường, vì vậy chỉ dùng khi semantics yêu cầu.

flattened phù hợp với object có nhiều key động mà không muốn tạo một mapping field riêng cho từng key. Nó có trade-off về kiểu dữ liệu và khả năng query; không thay thế object/nested trong mọi trường hợp.

Việc chọn object/nested/flattened là quyết định mapping quan trọng trước khi tối ưu query, bởi đổi cấu trúc về sau thường cần reindex.

## 11. Spring Data Elasticsearch: khai báo mapping bằng annotation

Spring Data Elasticsearch cho phép khai báo mapping trên entity.

Ví dụ:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "standard"
        ),
        otherFields = {
            @InnerField(
                suffix = "keyword",
                type = FieldType.Keyword,
                ignoreAbove = 256
            )
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

Trong ví dụ:

- sku là keyword cho exact filter.
- name là text cho full-text search và name.keyword cho exact/sort.
- category là keyword cho filter/aggregation.
- priceInCents là long cho range/sort/aggregation.
- active là boolean.
- createdAt là date.

Annotation hỗ trợ các thuộc tính mapping khác nhau theo phiên bản. Hãy kiểm tra @Field, @MultiField và @InnerField trong dependency thực tế. Với field cần docValues = false hoặc index = false, dùng thuộc tính annotation nếu phiên bản hỗ trợ và xác nhận mapping tạo ra bằng API.

### 11.1. Ví dụ tắt doc values cho keyword

Nếu một keyword field chỉ cần exact query và không cần sort/aggregation/script doc-value access, có thể khai báo theo API hỗ trợ:

~~~java
@Field(
    type = FieldType.Keyword,
    index = true,
    docValues = false
)
private String externalReference;
~~~

Đây là quyết định có ảnh hưởng tới query capabilities. Nếu dashboard sau này cần terms aggregation theo externalReference, mapping này không đáp ứng qua doc values.

### 11.2. Ví dụ chỉ dùng doc values

Với numeric field chỉ cần sort hoặc aggregation và không cần search query trên field, có thể cấu hình:

~~~java
@Field(
    type = FieldType.Long,
    index = false,
    docValues = true
)
private Long internalRank;
~~~

Cần xác nhận field type và phiên bản hỗ trợ cấu hình này. Test query thật để đảm bảo không có filter/range query nào phụ thuộc inverted index.

## 12. Tạo mapping tường minh bằng IndexOperations

Annotation phù hợp khi schema gắn chặt với domain class. Với index versioning, alias, analyzer hoặc mapping phức tạp, có thể tạo index và mapping tường minh qua IndexOperations.

Ví dụ mapping JSON:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "category": {
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
    },
    "internalRank": {
      "type": "long",
      "index": false,
      "doc_values": true
    }
  }
}
~~~

Spring Data có thể tạo mapping từ entity metadata:

~~~java
IndexOperations indexOperations =
    operations.indexOps(Product.class);

indexOperations.create();
indexOperations.putMapping(
    indexOperations.createMapping()
);
~~~

Tên method và cách tạo mapping có thể khác theo version. Cần tạo index với settings phù hợp trước khi mapping được áp dụng, đặc biệt nếu dùng custom analyzer.

Với mapping JSON tự quản lý, dùng IndexOperations.putMapping(...) hoặc API client phù hợp phiên bản. Giữ mapping trong source control để có thể review thay đổi và triển khai lặp lại.

## 13. Dynamic mapping và dynamic templates

Nếu không khai báo mapping cho field mới, Elasticsearch có thể tự suy luận kiểu qua dynamic mapping. Điều này tiện cho thử nghiệm nhưng có thể gây ra schema ngoài ý muốn:

- Chuỗi được map thành text với keyword sub-field theo dynamic template mặc định.
- Chuỗi ngày có thể được nhận dạng theo date detection.
- Số được map thành numeric theo giá trị đầu tiên.
- Field tùy ý có thể làm mapping tăng nhanh.

Dynamic templates cho phép định nghĩa quy tắc theo tên hoặc kiểu field mới. Ví dụ mọi field kết thúc bằng Code có thể được map thành keyword:

~~~json
{
  "dynamic_templates": [
    {
      "code_fields": {
        "match": "*Code",
        "mapping": {
          "type": "keyword"
        }
      }
    }
  ]
}
~~~

Có thể đặt dynamic thành false để không thêm field mới vào mapping hoặc strict để từ chối document có field không được khai báo, tùy mục đích.

Với hệ thống có schema ổn định, explicit mapping hoặc dynamic templates thường dễ kiểm soát hơn để Elasticsearch tự đoán mọi field.

## 14. Chọn doc_values cho từng query pattern

Một bảng quyết định thực tế:

| Query pattern | Mapping nên cân nhắc |
|---|---|
| Match full-text trên tên | text + analyzer phù hợp |
| Exact filter trên SKU | keyword, index true |
| Sort theo tên nguyên vẹn | name.keyword có doc values |
| Terms aggregation theo category | keyword có doc values |
| Range filter theo giá | numeric với index true |
| Sort theo giá | numeric có doc values |
| Min/max/avg giá | numeric có doc values |
| Sort theo thời gian | date có doc values |
| Chỉ hiển thị mô tả dài | source-only nếu không search |
| Exact query nhưng không sort/aggregate | keyword; cân nhắc doc_values false nếu chắc chắn |
| Chỉ sort/aggregate, không search | doc_values true và index false nếu field type hỗ trợ |
| Full-text search và sort/aggregate | multi-field text + keyword |

Đừng tắt doc values chỉ để giảm vài phần trăm disk nếu chưa kiểm tra toàn bộ query, dashboard, export và script đang sử dụng field đó.

## 15. Script và doc values

Painless có thể đọc field qua doc values trong script context hỗ trợ:

~~~json
{
  "script_fields": {
    "priceWithTax": {
      "script": {
        "source": "doc['priceInCents'].value * params.factor",
        "params": {
          "factor": 1.1
        }
      }
    }
  }
}
~~~

Cách đọc qua doc['field'] thường phù hợp hơn khi field có doc values và script cần truy cập giá trị đã lập chỉ mục.

Một số lưu ý:

- Field có thể thiếu ở một số document; kiểm tra doc['field'].size() trước khi truy cập .value.
- Field multi-valued có thể có nhiều giá trị; .value chỉ lấy một giá trị theo semantics của doc values.
- Không phải field type nào cũng hỗ trợ doc values.
- Script context khác nhau có biến và quyền truy cập khác nhau.
- Đọc _source có thể có chi phí khác với doc values và không phải context nào cũng hỗ trợ giống nhau.

Ví dụ kiểm tra field có giá trị:

~~~painless
if (doc['priceInCents'].size() == 0) {
    return 0;
}
return doc['priceInCents'].value;
~~~

Không dùng script để thay thế một query hoặc sort native có thể diễn đạt trực tiếp. Script có thể làm giảm khả năng tối ưu hóa và tăng CPU.

## 16. Sort và aggregation: doc values giúp gì, không giúp gì?

Doc values là nền tảng truy cập field cho sort và nhiều aggregation, nhưng không xóa bỏ chi phí của chính phép toán.

### 16.1. Sorting

Sort theo numeric/date/keyword field thường sử dụng doc values. Chi phí còn phụ thuộc:

- Số hit và số shard cần xét.
- Sort theo một hay nhiều field.
- Tie-breaker.
- Missing values.
- Multi-valued sort mode.
- Deep pagination và search_after.
- Shard-level top-N merge.

Nếu sort theo text, thường phải dùng keyword multi-field. Bật fielddata cho text có thể tạo áp lực heap lớn.

### 16.2. Aggregation

Terms aggregation trên keyword dùng doc values để đọc giá trị. Nhưng aggregation cardinality cao vẫn có thể tốn memory vì Elasticsearch phải quản lý nhiều bucket.

Các yếu tố:

- Số lượng distinct values.
- Kích thước tập document sau filter.
- Số shard.
- size, shard_size và execution hint nếu phù hợp.
- Sub-aggregation.
- Cardinality precision.
- Kích thước response.

Nếu aggregation chậm, kiểm tra cả cardinality và số bucket, không chỉ doc_values.

### 16.3. Fielddata cache và heap

Fielddata cache chủ yếu liên quan tới fielddata được xây dựng cho text field và một số cấu trúc liên quan. Doc values không đồng nghĩa fielddata cache.

Có thể xem fielddata statistics bằng node stats hoặc CAT API phù hợp. Nếu fielddata heap tăng mạnh, tìm query nào đang aggregate/sort trên text field và chuyển sang keyword sub-field nếu semantics phù hợp.

## 17. Mapping có thể thay đổi đến đâu?

Elasticsearch cho phép bổ sung field mới vào mapping, nhưng nhiều thuộc tính của field đã tạo không thể thay đổi tùy ý.

Thông thường không thể đổi trực tiếp:

- Field type từ text sang keyword hoặc long.
- Analyzer của field đã index theo cách làm thay đổi tokenization.
- Bật/tắt index hoặc doc_values cho field đã được tạo nếu thay đổi không được hỗ trợ.
- Một số tham số mapping ảnh hưởng cách dữ liệu đã index được biểu diễn.

Nếu cần thay đổi cấu trúc, cách an toàn thường là:

1. Tạo index mới với mapping/settings mong muốn.
2. Reindex dữ liệu từ index cũ sang index mới.
3. Kiểm tra số document và query behavior.
4. Chuyển alias hoặc ứng dụng sang index mới.
5. Theo dõi và giữ đường rollback theo chính sách.

### 17.1. Thêm multi-field không tự populate dữ liệu cũ

Có thể thêm multi-field vào mapping hiện tại, ví dụ thêm name.keyword. Mapping mới áp dụng cho document được index sau đó. Những document cũ không tự được phân tích lại để tạo keyword term/doc values mới.

Nếu cần sort/aggregation trên toàn bộ dữ liệu cũ bằng sub-field mới, phải reindex hoặc cập nhật lại document để field được index theo mapping mới.

### 17.2. Version hóa index

Một mô hình thường dùng:

~~~text
products-v1  -> dữ liệu và mapping hiện tại
products-v2  -> mapping mới
products     -> alias đọc/ghi
~~~

Khi migration hoàn tất, chuyển alias sang v2 theo quy trình kiểm soát. Ứng dụng có thể tiếp tục dùng alias ổn định trong khi schema được nâng cấp.

## 18. Kiểm tra mapping và capabilities trước khi tối ưu query

Đừng chỉ đọc annotation Java rồi giả định mapping thực tế đúng. Kiểm tra trực tiếp trên cluster.

Lấy mapping:

~~~http
GET products/_mapping
~~~

Kiểm tra field capabilities trên một hoặc nhiều index:

~~~http
POST products/_field_caps?fields=name,name.keyword,category,priceInCents,createdAt
~~~

Field capabilities hữu ích khi nhiều index trong alias có mapping khác nhau. Nếu cùng một field là keyword ở index này nhưng text ở index khác, query hoặc aggregation có thể lỗi hoặc có behavior không nhất quán.

Kiểm tra fielddata:

~~~http
GET _cat/fielddata?v
~~~

Hoặc node stats:

~~~http
GET _nodes/stats/indices/fielddata
~~~

Kiểm tra index stats:

~~~http
GET products/_stats
~~~

Dùng Profile API để hiểu phần thực thi query khi cần:

~~~json
{
  "profile": true,
  "query": {
    "bool": {
      "filter": [
        { "term": { "category": "Accessories" } },
        { "range": { "priceInCents": { "gte": 100000, "lte": 500000 } } }
      ]
    }
  }
}
~~~

Profile giúp quan sát query execution, nhưng bản thân nó có overhead và không phản ánh đầy đủ latency end-to-end của production. Đo thêm network, queue, fetch phase, serialization và tải cluster.

## 19. Ví dụ mapping hoàn chỉnh cho catalog

Một mapping phù hợp với các query pattern đã nêu:

~~~http
PUT products-v2
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "description": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      },
      "priceInCents": {
        "type": "long"
      },
      "stock": {
        "type": "integer"
      },
      "active": {
        "type": "boolean"
      },
      "createdAt": {
        "type": "date"
      },
      "internalRank": {
        "type": "long",
        "index": false,
        "doc_values": true
      },
      "externalPayload": {
        "type": "object",
        "enabled": false
      }
    }
  }
}
~~~

Thiết kế này có chủ đích:

- sku exact filter.
- name full-text và exact sort qua name.keyword.
- description full-text nhưng không tạo keyword sub-field dài.
- category filter và terms aggregation.
- priceInCents/stock numeric query và sort.
- active boolean filter.
- createdAt date range/sort.
- internalRank chỉ dùng cho sort/aggregation theo giả định use case, không search.
- externalPayload được giữ trong source nhưng không parse/index field con theo cấu hình enabled false.

dynamic: strict giúp phát hiện field ngoài schema, nhưng có thể làm ingest thất bại nếu producer gửi field mới. Chỉ chọn strict khi contract dữ liệu được kiểm soát và ứng dụng xử lý lỗi phù hợp.

## 20. Các lỗi mapping thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Terms aggregation lỗi trên text | Text không có doc values mặc định | Dùng keyword multi-field hoặc cân nhắc fielddata có kiểm soát |
| Sort theo tên lỗi | Sort đang dùng text field | Sort theo name.keyword |
| Keyword field không có kết quả khi giá trị dài | ignore_above loại giá trị khỏi keyword sub-field | Điều chỉnh giới hạn hoặc thiết kế field khác |
| Range query trên số hoạt động sai | Field được map thành keyword hoặc dữ liệu sai kiểu | Dùng numeric mapping và kiểm tra source |
| Aggregation tốn heap | Fielddata trên text hoặc bucket cardinality cao | Chuyển sang keyword khi phù hợp, kiểm soát cardinality |
| Script báo field không có doc values | doc_values bị tắt hoặc field type không hỗ trợ | Dùng mapping phù hợp hoặc truy cập source theo context |
| Tắt doc_values làm sort/aggregation lỗi | Query phụ thuộc doc values | Bật trong index mới và reindex |
| Thêm keyword sub-field nhưng document cũ không có giá trị | Sub-field mới chưa được index trên dữ liệu cũ | Reindex hoặc cập nhật lại document |
| Mapping conflict giữa index trong alias | Field có type khác nhau | Chuẩn hóa schema và reindex index không đồng nhất |
| Mapping explosion | Quá nhiều field động | Dùng explicit mapping, dynamic templates hoặc flattened |
| Query đúng nhưng vẫn chậm | Sai field type, cardinality cao, quá nhiều shard hoặc fetch cost | Kiểm tra mapping, profile và metrics end-to-end |
| index: false khiến filter không chạy | Field không có inverted index cho query đó | Bật index ở index mới nếu query cần |
| Dữ liệu chỉ có trong _source | Field không được index/doc values | Xác định query requirement và reindex |

## 21. Quy trình chọn mapping trước khi tối ưu query

Với mỗi field, hãy ghi rõ:

1. Field có cần full-text search không?
2. Có cần exact filter không?
3. Có cần range query không?
4. Có cần sort không?
5. Có cần aggregation không?
6. Có cần script truy cập field qua doc values không?
7. Field có cardinality thấp hay cao?
8. Có giá trị dài hoặc nhiều giá trị trong một document không?
9. Field chỉ cần trả về từ _source hay cần index?
10. Query nào đang sử dụng field và tần suất ra sao?

Sau đó chọn:

- text cho full-text search.
- keyword cho exact matching, sorting và terms aggregation.
- numeric/date/boolean/ip/geo type theo semantics.
- multi-field nếu một giá trị cần nhiều cách truy cập.
- doc_values bật cho field cần sort/aggregation/script khi field type hỗ trợ.
- index bật khi cần query trên inverted index.
- tắt index hoặc doc_values chỉ khi đã chứng minh use case không cần cấu trúc đó.

Cuối cùng, tạo index thử nghiệm, index dữ liệu đại diện, chạy query thực tế và đo. Không tối ưu chỉ bằng cách đọc mapping hoặc nhìn một query đơn lẻ.

## 22. Bảng tra cứu nhanh

| Khái niệm | Dùng cho |
|---|---|
| Inverted index | Tìm term và document phù hợp |
| Doc values | Sort, aggregation và truy cập field trong script |
| _source | Lưu JSON để fetch, update và reindex |
| text | Full-text search qua analyzer |
| keyword | Exact filter, sort và terms aggregation |
| Multi-field | Một field có cả text và keyword representation |
| fielddata | Hỗ trợ một số thao tác trên text nhưng có thể tốn heap |
| index | Bật/tắt inverted index cho field |
| doc_values | Bật/tắt column-oriented field values |
| ignore_above | Bỏ giá trị dài khỏi keyword indexing/doc values |
| normalizer | Chuẩn hóa keyword mà không tokenize |
| dynamic templates | Áp dụng mapping rule cho field mới |
| index: false, doc_values: true | Có thể phù hợp cho sort/aggregation mà không cần search |
| index: true, doc_values: false | Search nhưng không dùng doc values cho sort/aggregation |
| Reindex | Chuyển dữ liệu sang index có mapping mới |

Mapping và doc values nên được chọn theo query pattern của từng field. Inverted index phục vụ tìm kiếm, doc values phục vụ truy cập theo cột cho sort/aggregation và script, còn _source giữ JSON để fetch hoặc reindex. Dùng text cho full-text, keyword cho exact filter và aggregation, numeric/date cho range và sort; tạo multi-field khi một giá trị cần nhiều cách truy cập. Giữ doc_values cho field cần sort/aggregation, chỉ tắt index hoặc doc_values khi đã xác nhận query contract không cần chúng. Vì nhiều mapping parameter không thể đổi trên field đã tạo và multi-field mới không tự populate document cũ, hãy version hóa index và reindex khi cần thay đổi cấu trúc.
