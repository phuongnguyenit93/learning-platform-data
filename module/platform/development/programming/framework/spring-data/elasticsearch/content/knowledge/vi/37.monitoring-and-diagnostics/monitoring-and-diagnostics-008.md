# Lỗi sắp xếp, aggregation trên text và giới hạn fielddata

Một lỗi thường gặp khi dùng Elasticsearch là cố gắng sort hoặc chạy terms aggregation trên một field kiểu text. Request có thể trả về thông báo như “Fielddata is disabled on text fields by default”. Lỗi này không có nghĩa Elasticsearch không thể sắp xếp chuỗi; nó cho biết field đang được truy vấn được thiết kế cho full-text search và không có cấu trúc phù hợp cho thao tác sort/aggregation theo giá trị.

Cách xử lý thường đúng là tạo keyword multi-field cho cùng dữ liệu, rồi dùng field con đó khi sort, terms aggregation hoặc exact filter. Có thể bật fielddata trên text trong một số trường hợp đặc biệt, nhưng fielddata được nạp vào heap và có thể tiêu thụ lượng bộ nhớ lớn, làm tăng garbage collection hoặc kích hoạt circuit breaker.

Trong Spring Data Elasticsearch, cần khai báo mapping đúng từ đầu, dùng đúng tên field trong query và kiểm tra mapping thực tế trên cluster. Bài này giải thích nguyên nhân lỗi, cách fielddata hoạt động, giới hạn bộ nhớ, giải pháp keyword, cách xử lý dữ liệu cũ, ví dụ với Spring Data và Elasticsearch API, cùng các bước giám sát và chẩn đoán.

## 1. Vì sao sort và aggregation trên text thường thất bại?

Field kiểu text được thiết kế cho full-text search. Khi index, analyzer tách nội dung thành token và có thể chuẩn hóa chữ hoa/thường, dấu câu hoặc từ dừng.

Ví dụ:

~~~text
Giá trị gốc: "Wireless Ergonomic Mouse"
Analyzer:
  wireless
  ergonomic
  mouse
~~~

Elasticsearch lưu các token trong inverted index để tìm document theo từ. Cấu trúc này phù hợp với match query, nhưng không phải representation tối ưu để lấy toàn bộ giá trị của từng document nhằm sort hoặc gom nhóm.

Ví dụ request sort:

~~~http
GET products/_search
{
  "sort": [
    {
      "name": {
        "order": "asc"
      }
    }
  ]
}
~~~

Nếu name là text và fielddata chưa bật, Elasticsearch thường trả lỗi tương tự:

~~~text
Fielddata is disabled on [name] in [products].
Text fields are not optimised for operations that require per-document field data
like aggregations and sorting, so these operations are disabled by default.
Please use a keyword field instead.
Alternatively, set fielddata=true on [name] in order to load field data by uninverting the inverted index.
~~~

Terms aggregation trên text cũng có thể gặp cùng vấn đề:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "names": {
      "terms": {
        "field": "name"
      }
    }
  }
}
~~~

Đây là vấn đề mapping/query mismatch. Elasticsearch đang được yêu cầu thao tác theo giá trị của document trên một field được cấu hình chủ yếu để tìm kiếm theo token.

## 2. text, keyword và cách truy cập dữ liệu

Hai field type chuỗi phổ biến có semantics khác nhau.

| Đặc điểm | text | keyword |
|---|---|---|
| Analyzer/tokenization | Có | Không tokenize như text |
| Full-text match | Phù hợp | Exact term là chính |
| Exact filter | Thường cần representation khác | Phù hợp |
| Sort theo giá trị | Fielddata có thể được bật nhưng tốn heap | Doc values thường có sẵn |
| Terms aggregation | Cần fielddata hoặc field khác | Doc values thường có sẵn |
| Dữ liệu được xem như | Token đã phân tích | Giá trị nguyên vẹn đã chuẩn hóa tùy normalizer |

Ví dụ mapping:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword"
    }
  }
}
~~~

Với mapping này:

- name phù hợp cho match query.
- category phù hợp cho term filter, sort và terms aggregation.
- Không nên dùng name cho sort hoặc aggregation theo toàn bộ tên sản phẩm.

Nếu một giá trị cần cả full-text search lẫn sort/aggregation, dùng multi-field.

## 3. Multi-field là giải pháp mặc định cho chuỗi cần nhiều cách truy cập

Multi-field cho phép index cùng một giá trị theo nhiều representation. Ví dụ name là text chính và name.keyword là keyword sub-field.

~~~json
PUT products-v2
{
  "mappings": {
    "properties": {
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
  }
}
~~~

Khi index document, Elasticsearch tạo:

- name: token hóa để tìm full-text.
- name.keyword: giữ giá trị nguyên vẹn để exact match, sort và aggregation.

Query full-text tiếp tục dùng name:

~~~http
GET products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Sort dùng name.keyword:

~~~http
GET products/_search
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

Terms aggregation dùng name.keyword:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "names": {
      "terms": {
        "field": "name.keyword",
        "size": 20
      }
    }
  }
}
~~~

Exact filter cũng dùng sub-field:

~~~http
GET products/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Ergonomic Mouse"
    }
  }
}
~~~

Exact match trên keyword vẫn tuân theo quy tắc normalizer nếu field có cấu hình normalizer. Nếu không có normalizer, khác biệt chữ hoa/thường và khoảng trắng có thể ảnh hưởng kết quả.

### 3.1. Chọn tên sub-field

Tên phổ biến là keyword, nhưng có thể đặt tên thể hiện mục đích:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "raw": {
        "type": "keyword",
        "ignore_above": 256
      },
      "sort": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Khi đó:

- name dùng full-text.
- name.raw dùng exact value theo nguyên bản.
- name.sort dùng giá trị đã normalize cho sort.

Không tạo nhiều sub-field nếu không có use case. Mỗi representation bổ sung có chi phí lưu trữ, indexing và merge.

### 3.2. ignore_above và giá trị dài

Keyword field có thể giới hạn độ dài giá trị được index bằng ignore_above. Ví dụ ignore_above: 256 nghĩa là giá trị dài hơn giới hạn sẽ không được index vào keyword sub-field.

Giá trị vẫn có thể còn trong _source và text field chính vẫn có thể tìm full-text. Tuy nhiên, document đó không có term/doc value tương ứng ở sub-field, vì vậy có thể không tham gia sort hoặc aggregation theo cách mong muốn.

Chọn giới hạn dựa trên dữ liệu thực tế. Với chuỗi dài không phù hợp làm category hoặc sort key, hãy xem xét dùng field khác thay vì đặt giới hạn rất lớn một cách tùy tiện.

## 4. Doc values giúp sort và aggregation như thế nào?

Keyword field thường có doc values được bật mặc định. Doc values lưu giá trị theo hướng document-to-value, phù hợp cho việc đọc field trên tập document.

Ví dụ category:

~~~json
{
  "category": {
    "type": "keyword"
  }
}
~~~

Aggregation:

~~~json
{
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Sort:

~~~json
{
  "sort": [
    {
      "category": {
        "order": "asc"
      }
    }
  ]
}
~~~

Doc values thường được lưu trên disk và có thể tận dụng filesystem cache. Chúng không đồng nghĩa với việc toàn bộ giá trị được nạp vào Java heap như fielddata.

Điều này không có nghĩa sort và aggregation không tốn memory. Aggregation vẫn cần bộ nhớ cho bucket và kết quả trung gian; sort cần xử lý các giá trị và top hits. Doc values chỉ cung cấp representation phù hợp cho việc truy cập field.

## 5. Fielddata là gì?

Fielddata là cấu trúc dữ liệu trong memory được Elasticsearch xây dựng từ inverted index để cung cấp giá trị theo document cho các thao tác như sort, aggregation hoặc script trên một số field, đặc biệt là text.

Khi bật fielddata trên text:

~~~json
PUT products/_mapping
{
  "properties": {
    "name": {
      "type": "text",
      "fielddata": true
    }
  }
}
~~~

Elasticsearch có thể uninvert inverted index để xây dựng fielddata. Quá trình này có thể nạp nhiều term và quan hệ term-document vào heap.

Fielddata khác doc values:

| Đặc điểm | Fielddata trên text | Doc values |
|---|---|---|
| Nguồn/representation | Xây dựng từ inverted index | Cấu trúc cột được tạo khi index |
| Memory | Có thể chiếm JVM heap đáng kể | Chủ yếu lưu trên disk, dùng filesystem cache |
| Mục đích | Cho phép sort/aggregation trên text khi bật | Sort/aggregation trên field type hỗ trợ |
| Chi phí | Có thể phát sinh khi fielddata được load | Có chi phí lưu trữ/indexing từ lúc ghi |
| Rủi ro nổi bật | Heap pressure và fielddata circuit breaker | Disk/cache và chi phí bucket/sort vẫn tồn tại |

Fielddata có thể được cache sau khi được nạp. Lần truy vấn đầu tiên có thể có chi phí xây dựng lớn; các truy vấn sau có thể tái sử dụng cache cho đến khi segment/cache thay đổi hoặc bị clear/evict.

### 5.1. Fielddata không chỉ lưu một chuỗi cho mỗi document

Với text, analyzer có thể tạo nhiều token cho một field. Fielddata có thể cần biểu diễn nhiều term và document association. Một field mô tả dài với nhiều token và nhiều document có thể tạo footprint lớn.

Ví dụ description:

~~~text
"Wireless mouse with ergonomic design and rechargeable battery"
~~~

Analyzer có thể tạo nhiều token. Aggregation trên field này thường nhóm theo token đã phân tích chứ không phải nguyên câu mô tả. Kết quả vừa có thể không đúng mục đích nghiệp vụ, vừa có thể tốn heap.

Nếu mục tiêu là nhóm theo nguyên giá trị description, keyword multi-field thường phù hợp hơn về semantics, nhưng cần cân nhắc độ dài và cardinality.

### 5.2. Fielddata có thể làm tăng heap và GC

Khi fielddata chiếm nhiều heap:

- Garbage collection có thể chạy thường xuyên hơn.
- Search latency có thể tăng.
- Node có thể bị memory pressure.
- Circuit breaker có thể từ chối load fielddata hoặc request.
- Node có thể mất ổn định nếu memory bị sử dụng quá mức.

Fielddata được quản lý ở cấp node và có thể liên quan tới nhiều shard trên cùng node. Một query trên một index có thể làm fielddata được load trên nhiều shard mà query chạm tới.

## 6. Vì sao Elasticsearch tắt fielddata mặc định trên text?

Elasticsearch chọn mặc định an toàn vì sort/aggregation trên text thường không phải use case chính và có thể gây chi phí heap không dự đoán được.

Nếu mọi text field tự động load fielddata khi có aggregation, một dashboard hoặc query mới có thể làm heap tăng mạnh trên production.

Thông báo lỗi yêu cầu dùng keyword field là lời khuyên phù hợp trong đa số trường hợp:

- Full-text search: text.
- Exact/sort/aggregation: keyword.
- Cần cả hai: multi-field.

Bật fielddata là lựa chọn có chủ đích cho trường hợp cần thao tác trên token đã phân tích, sau khi đo memory và kiểm soát query.

## 7. Khi nào fielddata có thể hợp lý?

Có một số use case đặc biệt cần aggregation hoặc sort trên token đã phân tích. Ví dụ:

- Thống kê tần suất token trong nội dung.
- Phân tích từ khóa sau analyzer.
- Nghiên cứu search relevance hoặc dữ liệu ngôn ngữ.
- Một field text ngắn, cardinality và số document được kiểm soát, và semantics aggregation thực sự cần token.

Ngay cả trong các trường hợp đó, phải xác định rõ aggregation đang nhóm theo token hay nguyên giá trị. Fielddata không biến text thành keyword; nó cung cấp dữ liệu theo document từ token của text.

Trước khi bật, đánh giá:

1. Số lượng document có field.
2. Độ dài trung bình và số token mỗi document.
3. Cardinality của token.
4. Số shard và số node có thể load fielddata.
5. Heap thực tế và mức sử dụng cao điểm.
6. Số query có thể kích hoạt fielddata.
7. Tác động khi cache bị cold hoặc segment merge.

Nếu mục tiêu chỉ là sort theo tên hoặc group theo category, dùng keyword multi-field.

## 8. Fielddata frequency filter

Elasticsearch có thể hỗ trợ cấu hình fielddata frequency filter cho text field để giới hạn term nào được nạp vào fielddata, tùy phiên bản.

Ví dụ minh họa:

~~~json
{
  "name": {
    "type": "text",
    "fielddata": true,
    "fielddata_frequency_filter": {
      "min": 0.01,
      "max": 0.5,
      "min_segment_size": 500
    }
  }
}
~~~

Filter này dựa trên tần suất term trong segment và có thể bỏ qua term quá hiếm hoặc quá phổ biến theo ngưỡng cấu hình. Nó không biến fielddata thành doc values và không bảo đảm memory usage cố định.

Cần xác nhận tên setting, ý nghĩa ngưỡng và khả năng hỗ trợ trên Elasticsearch version đang dùng. Đo kết quả với dữ liệu thực tế trước khi đưa vào production.

## 9. Fielddata circuit breaker

Elasticsearch dùng circuit breaker để ngăn một số thao tác ước tính vượt quá giới hạn memory được cấu hình.

Fielddata circuit breaker theo dõi việc load fielddata. Nếu ước lượng bộ nhớ mới vượt giới hạn, Elasticsearch có thể từ chối thao tác và trả lỗi circuit breaking thay vì tiếp tục làm heap tăng.

Các setting liên quan có thể gồm:

- indices.breaker.fielddata.limit
- indices.breaker.fielddata.overhead
- indices.breaker.request.limit
- indices.breaker.total.limit

Tên, default và semantics phụ thuộc phiên bản Elasticsearch. Không thay đổi breaker limit chỉ để làm query chạy được khi chưa hiểu nguồn memory pressure.

### 9.1. Circuit breaker không phải bộ tối ưu hóa

Circuit breaker là cơ chế bảo vệ. Nếu query liên tục chạm breaker, tăng limit có thể khiến node tiến gần OOM hơn.

Trước khi điều chỉnh:

- Xác định field nào đang load fielddata.
- Xác định query/aggregation kích hoạt nó.
- Kiểm tra fielddata memory theo node.
- Kiểm tra heap usage, GC và request concurrency.
- Xem có thể dùng keyword multi-field không.
- Giảm bucket cardinality hoặc phạm vi dữ liệu nếu phù hợp.

Chỉ thay đổi breaker limit sau khi đã đánh giá heap headroom, tải đồng thời và tác động lên các workload khác.

## 10. Cách xử lý lỗi sort trên text

### 10.1. Xác định mapping thực tế

Đọc mapping:

~~~http
GET products/_mapping
~~~

Tìm field đang được sort. Nếu field là:

~~~json
{
  "name": {
    "type": "text"
  }
}
~~~

thì sort trực tiếp trên name cần fielddata, vốn bị tắt mặc định.

### 10.2. Kiểm tra có keyword sub-field không

Nếu mapping đã có:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

hãy đổi query sort sang name.keyword:

~~~http
GET products/_search
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

### 10.3. Xử lý missing value và tie-breaker

Nếu một số document không có keyword sub-field, có thể cấu hình missing:

~~~json
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc",
        "missing": "_last"
      }
    },
    {
      "_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

Tie-breaker giúp thứ tự ổn định hơn khi nhiều document có cùng tên. Với pagination sâu, cân nhắc search_after và sort theo một khóa ổn định.

Không dùng _id như một field doc values thông thường cho mọi sort pattern. Nếu cần sort theo identifier, có thể map một field keyword riêng chứa ID nghiệp vụ và dùng field đó.

## 11. Cách xử lý lỗi aggregation trên text

Nếu aggregation cần nhóm theo giá trị nguyên vẹn, dùng keyword field:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 50
      }
    }
  }
}
~~~

Nếu field là text với keyword sub-field:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "by_name": {
      "terms": {
        "field": "name.keyword",
        "size": 20
      }
    }
  }
}
~~~

Nếu thực sự cần aggregation theo token, có thể bật fielddata sau khi đánh giá:

~~~json
PUT products/_mapping
{
  "properties": {
    "description": {
      "type": "text",
      "fielddata": true
    }
  }
}
~~~

Nhưng kết quả terms aggregation khi đó phản ánh token đã phân tích, không phải toàn bộ chuỗi description. Ví dụ description có "wireless mouse" và "wireless keyboard" sẽ tạo bucket theo token wireless, mouse, keyboard.

## 12. Sửa mapping trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ khai báo multi-field bằng @MultiField và @InnerField.

Ví dụ entity:

~~~java
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

    // getters and setters
}
~~~

Mapping dự kiến:

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
  },
  "category": {
    "type": "keyword"
  }
}
~~~

Sau đó query cần tham chiếu đúng tên field con.

Annotation mapping không tự sửa mapping đã tồn tại trên cluster chỉ vì code entity thay đổi. Phải kiểm tra lifecycle tạo index, mapping update và chiến lược migration của ứng dụng.

### 12.1. Khai báo fielddata trong Spring Data

Nếu có use case thật sự cần fielddata, annotation @Field của phiên bản Spring Data Elasticsearch phù hợp có thể cung cấp thuộc tính fielddata:

~~~java
@Field(
    type = FieldType.Text,
    fielddata = true
)
private String analyzedTerms;
~~~

Xác nhận thuộc tính này có trong annotation version đang dùng và kiểm tra mapping thực tế sau khi tạo index.

Không bật fielddata cho mọi text field theo mặc định. Chỉ bật trên field có yêu cầu token-level sort/aggregation đã được đánh giá và theo dõi.

### 12.2. Dùng IndexOperations để kiểm tra mapping

Có thể đọc mapping qua IndexOperations:

~~~java
IndexOperations indexOperations =
    operations.indexOps(Product.class);

Map<String, Object> mapping =
    indexOperations.getMapping();
~~~

Tên method và kiểu trả về phụ thuộc phiên bản. Khi chẩn đoán production, REST Mapping API vẫn là cách trực tiếp để xác nhận mapping trên index thực tế.

## 13. Spring Data query: sort và aggregation dùng field con

Ví dụ với ElasticsearchOperations và NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
    .withSort(Sort.by(Sort.Order.asc("name.keyword")))
    .withQuery(QueryBuilders.matchQuery("name", "wireless mouse"))
    .build();
~~~

API builder và cách tạo query phụ thuộc phiên bản Spring Data Elasticsearch. Một lựa chọn là dùng Elasticsearch Java API Client query DSL hoặc request JSON khi cần kiểm soát chính xác.

Aggregation theo keyword field có thể được biểu diễn qua aggregation builder tương ứng:

~~~json
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Điểm cần kiểm tra trong code là field path:

- Match query: name.
- Sort: name.keyword.
- Terms aggregation: name.keyword hoặc category.
- Exact filter: name.keyword hoặc category.

Không thay mọi query dùng name thành name.keyword. Full-text search vẫn cần text field.

## 14. Multi-field mới không tự tạo dữ liệu cho document cũ

Đây là lỗi triển khai phổ biến. Mapping mới thêm name.keyword nhưng các document đã được index trước đó không tự động được xử lý lại.

Ví dụ mapping cũ:

~~~json
{
  "name": {
    "type": "text"
  }
}
~~~

Mapping mới bổ sung:

~~~json
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
~~~

Sau khi mapping được cập nhật, document mới sẽ có name.keyword. Document cũ cần được index lại để tạo term/doc values cho sub-field.

Có hai hướng thường dùng:

**Update by query**: reprocess document hiện có trong cùng index để áp dụng mapping mới, khi phù hợp với yêu cầu và semantics update.

~~~http
POST products/_update_by_query?conflicts=proceed
{
  "query": {
    "match_all": {}
  }
}
~~~

**Reindex sang index mới**: tạo index đích với mapping hoàn chỉnh rồi copy dữ liệu:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Update by query có thể tạo tải lớn và có thể gặp version conflicts. Reindex sang index mới thường phù hợp hơn khi thay đổi schema lớn hoặc cần rollback rõ ràng.

Sau khi backfill, kiểm tra document cũ có keyword value, chạy sort/aggregation và xác nhận kết quả.

## 15. Mapping type đã tồn tại không thể đổi tùy ý

Nếu field name đang là text và muốn đổi thành keyword, không thể đơn giản thay type trong mapping hiện tại. Hãy tạo field/sub-field mới hoặc index mới.

Với thay đổi analyzer, type hoặc cấu trúc phức tạp:

1. Tạo index version mới.
2. Khai báo mapping và settings.
3. Reindex dữ liệu.
4. Kiểm tra document count và field capabilities.
5. Chạy query sort/aggregation trên index mới.
6. Chuyển alias hoặc ứng dụng.
7. Giữ rollback plan theo chính sách.

Nếu chỉ thêm multi-field, mapping update có thể được hỗ trợ nhưng dữ liệu cũ vẫn cần backfill. Không nhầm “mapping update thành công” với “mọi document đã có giá trị mới”.

## 16. Cardinality và kích thước aggregation

Dùng keyword field đúng chưa đủ để aggregation luôn rẻ. Một terms aggregation có cardinality cao có thể tạo nhiều bucket và tiêu tốn memory.

Ví dụ category có vài chục giá trị thường nhẹ hơn customerEmail có hàng triệu giá trị duy nhất.

Trước khi aggregate, cân nhắc:

- Cardinality thực tế.
- Số document sau filter.
- Kích thước bucket cần trả.
- Shard count.
- Sub-aggregations.
- Có cần mọi bucket hay chỉ top N.
- Có thể dùng composite aggregation để paginate bucket không.
- Có thể tính trước summary ở index riêng không.

size giới hạn số bucket trả về, nhưng không có nghĩa mọi chi phí xử lý phía shard biến mất. shard_size ảnh hưởng số candidate bucket shard gửi về coordinator. Điều chỉnh phải dựa trên độ chính xác và tải.

Với cardinality cao và nhu cầu duyệt hết bucket, composite aggregation có thể phù hợp hơn terms aggregation lớn.

## 17. Fielddata cache và công cụ giám sát

Để biết fielddata đang được sử dụng ở đâu, kiểm tra cluster metrics.

### 17.1. CAT fielddata

~~~http
GET _cat/fielddata?v
~~~

Có thể lọc theo field:

~~~http
GET _cat/fielddata/name,description?v
~~~

Output giúp nhận biết field nào đang giữ fielddata và dung lượng liên quan trên node.

### 17.2. Node stats

~~~http
GET _nodes/stats/indices/fielddata
~~~

Có thể xem chi tiết theo field nếu API version hỗ trợ query parameter fields tương ứng.

Theo dõi:

- Fielddata memory size.
- Fielddata evictions.
- Heap usage.
- Old generation pressure.
- GC count/time.
- Search latency.
- Circuit breaker trips.
- Node restarts.

### 17.3. Circuit breaker stats

~~~http
GET _nodes/stats/breaker
~~~

Kiểm tra breaker count, estimated size và limit theo response của phiên bản. Nếu breaker thường xuyên trip, xác định query và field gây tải trước khi tăng giới hạn.

### 17.4. Query profiling

Profile API có thể giúp xem phần query/aggregation thực thi:

~~~http
GET products/_search
{
  "profile": true,
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Profile có overhead và không nên bật cho mọi request production. Kết hợp profile với metrics, slow logs và đo latency end-to-end.

## 18. Clear fielddata cache có giải quyết lỗi không?

Elasticsearch có API clear cache, ví dụ:

~~~http
POST products/_cache/clear?fielddata=true
~~~

Lệnh này giải phóng fielddata cache liên quan tới index được chỉ định. Nó có thể hữu ích khi:

- Cần giải phóng cache trong tình huống vận hành có kiểm soát.
- Đã thay đổi dữ liệu/mapping theo quy trình cần làm sạch cache.
- Điều tra hoặc xử lý một tình huống cụ thể.

Nhưng clear cache không sửa mapping và không loại bỏ nguyên nhân query đang yêu cầu fielddata. Query tiếp theo có thể load lại fielddata và gây cùng memory pressure.

Không chạy clear cache định kỳ như một cách tối ưu hiệu năng. Nó có thể khiến query sau đó phải xây dựng cache lại, gây latency spike.

## 19. Những cách xử lý sai thường gặp

| Cách xử lý | Vì sao có vấn đề | Hướng phù hợp |
|---|---|---|
| Bật fielddata cho mọi text field | Có thể làm heap tăng mạnh | Chỉ bật khi cần token-level aggregation |
| Tăng heap ngay khi gặp lỗi | Không sửa mapping/query mismatch | Dùng keyword multi-field |
| Tăng fielddata breaker limit | Có thể đẩy node tới OOM | Xác định field/query gây memory pressure |
| Sort trực tiếp trên text | Không có doc values mặc định | Sort theo keyword sub-field |
| Aggregate text để đếm nguyên chuỗi | Thực tế có thể group theo token | Dùng keyword representation |
| Clear fielddata cache liên tục | Cache sẽ load lại và tạo spike | Sửa mapping và query |
| Thêm multi-field rồi không backfill | Document cũ thiếu sub-field | Update by query hoặc reindex |
| Chỉ sửa annotation Java | Mapping cluster hiện tại có thể không đổi | Kiểm tra và migrate index |
| Tăng terms size vô hạn | Tạo nhiều bucket và tốn memory | Chỉ lấy top N hoặc composite aggregation |
| Dùng keyword cho mọi văn bản dài | Cardinality/disk/indexing có thể tăng mạnh | Chỉ tạo sub-field theo use case |

## 20. Kiểm thử mapping và query trong ứng dụng

Nên có integration test xác nhận mapping và query behavior, thay vì chỉ test entity annotation.

Một kịch bản:

1. Tạo index test với mapping name text + name.keyword.
2. Index một số sản phẩm có tên khác nhau.
3. Chạy match query trên name.
4. Chạy sort trên name.keyword.
5. Chạy terms aggregation trên name.keyword.
6. Xác nhận query không yêu cầu fielddata trên name.
7. Thêm document có name dài hơn ignore_above.
8. Xác nhận behavior của keyword sub-field với giá trị dài.
9. Nếu đang migration, backfill document cũ rồi chạy lại query.

Ví dụ dữ liệu:

~~~json
[
  { "name": "Wireless Mouse", "category": "Accessories" },
  { "name": "Mechanical Keyboard", "category": "Accessories" },
  { "name": "Office Chair", "category": "Furniture" }
]
~~~

Kết quả mong đợi:

- Match "wireless" tìm được Wireless Mouse.
- Sort theo name.keyword trả thứ tự lexical theo giá trị keyword.
- Terms aggregation category trả Accessories và Furniture.
- Không có fielddata load trên name chỉ vì các thao tác sort/aggregation này.

### 20.1. Test lỗi fielddata có chủ đích

Có thể tạo index test chỉ có name kiểu text, chạy sort/aggregation trên name và xác nhận request bị từ chối theo mapping hiện tại. Sau đó thêm keyword multi-field trên index mới hoặc test index khác và xác nhận query dùng name.keyword thành công.

Không phụ thuộc chính xác toàn bộ error message trong assertion vì message có thể thay đổi theo Elasticsearch version. Assert loại exception/status và nội dung có ý nghĩa.

## 21. Quy trình chẩn đoán lỗi production

Khi nhận lỗi sort hoặc aggregation trên text:

1. Ghi lại index, field, query và error type.
2. Kiểm tra mapping thực tế bằng _mapping.
3. Xác nhận field là text hay keyword.
4. Kiểm tra field có multi-field phù hợp không.
5. Nếu có keyword sub-field, đổi query sang đúng field path.
6. Nếu chưa có, xác định có thể thêm multi-field hay cần index version mới.
7. Lập kế hoạch backfill/reindex để document cũ có sub-field.
8. Kiểm tra cardinality và kích thước aggregation.
9. Nếu fielddata đã bật, kiểm tra CAT fielddata, node stats và breaker stats.
10. Đánh giá heap, GC, search latency và concurrency.
11. Chỉ giữ fielddata nếu semantics yêu cầu token-level operation và memory budget đủ.
12. Thêm integration test để tránh query regression.

Không bắt đầu bằng việc tăng heap hoặc breaker. Trước tiên xác định query đang dùng field representation nào và có thể chuyển sang keyword hay không.

## 22. Bảng tra cứu nhanh

| Triệu chứng hoặc nhu cầu | Cách xử lý |
|---|---|
| Sort trên text báo fielddata disabled | Dùng keyword sub-field |
| Terms aggregation trên text báo lỗi | Aggregate trên keyword field |
| Full-text search và exact sort cùng cần | Tạo multi-field text + keyword |
| Cần aggregate token đã phân tích | Cân nhắc fielddata có kiểm soát |
| Heap tăng khi fielddata load | Xác định field/query, ưu tiên keyword/doc values |
| Circuit breaker fielddata trip | Kiểm tra fielddata size, heap và concurrency |
| Document cũ thiếu keyword sub-field | Update by query hoặc reindex |
| Mapping field type cần đổi | Tạo index mới và reindex |
| Aggregation có cardinality cao | Filter, giới hạn bucket hoặc composite aggregation |
| Xác định fielddata đang dùng | _cat/fielddata và node stats |
| Xem breaker | _nodes/stats/breaker |
| Clear cache | Chỉ dùng có chủ đích; không thay mapping |
| Spring Data mapping | @MultiField, @InnerField, @Field |
| Kiểm tra mapping thật | GET index/_mapping |
| Kiểm thử query | Integration test với Elasticsearch |

Lỗi sort và aggregation trên text thường xuất phát từ việc query dùng field được thiết kế cho full-text search. Hãy giữ text cho match query và tạo keyword multi-field cho exact filter, sort và terms aggregation. Fielddata có thể cho phép thao tác trên token đã phân tích, nhưng nó được load vào heap, có thể tạo áp lực GC và kích hoạt circuit breaker; chỉ bật khi use case thực sự cần và đã đo memory. Khi thêm multi-field, dữ liệu cũ không tự có representation mới, vì vậy cần backfill bằng update by query hoặc reindex. Trong Spring Data Elasticsearch, khai báo mapping bằng annotation hoặc IndexOperations, dùng đúng field path trong query và kiểm tra mapping thực tế, fielddata stats cùng breaker metrics trước khi thay đổi cấu hình bộ nhớ.
