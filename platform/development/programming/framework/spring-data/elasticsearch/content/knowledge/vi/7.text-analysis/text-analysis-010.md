# Thiết kế multi-field cho tìm kiếm, sắp xếp và thống kê

Một thuộc tính văn bản trong Elasticsearch thường cần phục vụ nhiều cách sử dụng. Người dùng muốn tìm sản phẩm theo từ khóa, nhưng ứng dụng cũng cần sắp xếp tên sản phẩm theo thứ tự chữ cái và thống kê số sản phẩm theo từng tên hoặc nhãn. Một kiểu field duy nhất khó đáp ứng tốt cả ba nhu cầu.

Elasticsearch giải quyết vấn đề này bằng **multi-field**: cùng một giá trị được lập chỉ mục theo nhiều cách khác nhau. Field chính có thể là `text` để phân tích nội dung và tìm kiếm toàn văn; một subfield kiểu `keyword` giữ giá trị như một chuỗi nguyên vẹn để so khớp chính xác, sắp xếp hoặc aggregation.

Spring Data Elasticsearch hỗ trợ khai báo cấu trúc này ngay trên entity bằng `@MultiField` và `@InnerField`. Thiết kế đúng multi-field giúp query rõ ràng, tránh bật fielddata tốn bộ nhớ trên `text` và tạo nền tảng cho việc phân tích dữ liệu.

## 1. Vì sao một field văn bản cần nhiều cách lập chỉ mục?

Giả sử ứng dụng quản lý sản phẩm và có thuộc tính `title`:

~~~text
Wireless Mechanical Keyboard
~~~

Với nhu cầu tìm kiếm, người dùng có thể nhập `mechanical keyboard`. Elasticsearch cần phân tích chuỗi thành token để tìm những document chứa các từ phù hợp. Đây là nhiệm vụ của field kiểu `text`.

Nhưng nếu cần sắp xếp danh sách theo tên, ứng dụng thường muốn so sánh giá trị tiêu đề như một chuỗi hoàn chỉnh. Nếu dùng field `text`, dữ liệu đã được phân tích thành token; field này không được tối ưu cho sort và aggregation. Elasticsearch mặc định tắt fielddata trên `text` để tránh tải toàn bộ term vào heap.

Tương tự, khi thống kê số sản phẩm theo tên hoặc lọc chính xác một mã dạng chuỗi, ta cần một biểu diễn không bị phân tích thành token. Đây là vai trò của `keyword`.

Một field duy nhất vì vậy có thể cần các hành vi khác nhau:

| Nhu cầu | Cách xử lý phù hợp |
|---|---|
| Tìm theo một phần nội dung hoặc các từ trong câu | `text` và full-text query như `match` |
| So khớp chính xác một chuỗi | `keyword` và `term` |
| Sắp xếp chuỗi | `keyword` |
| Terms aggregation, đếm nhóm theo giá trị | `keyword` |
| Chuẩn hóa chuỗi trước khi so sánh | `keyword` có normalizer nếu cần |

Multi-field cho phép Elasticsearch lưu nhiều biểu diễn được lập chỉ mục từ cùng một giá trị nguồn. Nhờ đó, ứng dụng có thể chọn đúng biểu diễn cho từng thao tác.

## 2. Multi-field hoạt động như thế nào?

Một mapping multi-field có field chính `title` kiểu `text` và subfield `keyword` kiểu `keyword`:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Khi index document:

~~~json
{
  "title": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch lập chỉ mục giá trị `title` theo cả hai cấu hình:

- `title` được analyzer xử lý thành các token để phục vụ full-text search.
- `title.keyword` giữ toàn bộ chuỗi như một giá trị keyword để dùng cho exact match, sort và aggregation.

Đường dẫn `title.keyword` là tên field dùng trong Query DSL. Trong `_source`, document vẫn chỉ chứa thuộc tính `title`; subfield không tạo thêm một thuộc tính JSON riêng.

### Sơ đồ xử lý

~~~text
_source.title = "Wireless Mechanical Keyboard"
                    |
                    v
              Multi-field
               /       \
              /         \
             v           v
       title (text)   title.keyword (keyword)
             |           |
         Analyzer      Whole value
             |           |
       token index    keyword index
             |           |
       match query    term / sort / aggregation
~~~

Hai field được lập chỉ mục độc lập, nhưng cùng lấy giá trị từ một property nguồn. Điều này không có nghĩa Elasticsearch lưu hai bản `_source` của chuỗi; nó tạo các cấu trúc index phù hợp với từng kiểu field.

### Multi-field không phải nested object

`title.keyword` trông giống đường dẫn object nhưng không phải một object JSON con trong `_source`. Nó là một subfield trong mapping.

Multi-field cũng khác với `nested` field. `nested` dùng để lập chỉ mục các object con cần giữ quan hệ giữa các thuộc tính; multi-field dùng để lập chỉ mục cùng một giá trị theo nhiều kiểu.

## 3. Khai báo multi-field bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp hai annotation chính:

- `@MultiField`: đánh dấu property có field chính và một hoặc nhiều subfield.
- `@InnerField`: mô tả từng subfield, gồm suffix và kiểu field.

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
                type = FieldType.Keyword
            )
        }
    )
    private String title;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // constructors, getters, setters
}
~~~

Với khai báo trên, Spring Data có metadata tương ứng với mapping:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

Cách đặt tên subfield được quyết định bởi `suffix`. Với `suffix = "keyword"`, đường dẫn field trong Elasticsearch là `title.keyword`.

Có thể khai báo nhiều subfield nếu có nhu cầu thực tế:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword
        ),
        @InnerField(
            suffix = "english",
            type = FieldType.Text,
            analyzer = "english"
        )
    }
)
private String description;
~~~

Trong ví dụ này:

- `description` dùng analyzer `standard`.
- `description.keyword` phục vụ exact match, sort và aggregation.
- `description.english` dùng analyzer tiếng Anh để tìm kiếm theo quy tắc ngôn ngữ đó.

Chỉ tạo những subfield có use case rõ ràng. Mỗi subfield làm tăng chi phí indexing, kích thước index và công việc cần thực hiện khi ghi document.

### Chọn suffix dễ hiểu

Suffix là một phần của tên field công khai trong mapping. Nên chọn tên thể hiện mục đích:

- `keyword` hoặc `raw`: biểu diễn nguyên chuỗi.
- `sort`: biểu diễn dùng để sắp xếp.
- `english`, `ngram`: biểu diễn phục vụ analyzer hoặc chiến lược tìm kiếm riêng.

Tên suffix không làm thay đổi semantics của field. `title.raw` vẫn chỉ là keyword nếu mapping khai báo `type: keyword`.

Trong một dự án, nên thống nhất convention. Nếu một property dùng `title.keyword`, property khác không nên tùy tiện dùng `name.raw` cho cùng mục đích nếu không có lý do rõ ràng.

## 4. Phân biệt text và keyword

Hiểu hai kiểu field này là nền tảng để thiết kế multi-field.

### Field text

`text` được thiết kế cho full-text search. Analyzer thường gồm các bước:

1. Character filters xử lý chuỗi đầu vào nếu được cấu hình.
2. Tokenizer chia chuỗi thành token.
3. Token filters chuẩn hóa, loại bỏ hoặc biến đổi token.

Ví dụ analyzer `standard` có thể biến:

~~~text
Wireless Mechanical Keyboard
~~~

thành các token gần như:

~~~text
wireless
mechanical
keyboard
~~~

Một `match` query trên `title` cũng phân tích truy vấn theo search analyzer phù hợp, nhờ đó có thể tìm document theo các từ thay vì yêu cầu toàn chuỗi giống hệt.

`text` thích hợp cho:

- Tên, tiêu đề, mô tả sản phẩm.
- Nội dung bài viết.
- Tên địa điểm hoặc thông tin có nhu cầu tìm theo từ.
- Trường văn bản cần relevance scoring.

### Field keyword

`keyword` được thiết kế cho giá trị dạng chuỗi không cần tokenizer. Toàn bộ chuỗi là một term. Ví dụ `Wireless Mechanical Keyboard` được xem là một giá trị duy nhất.

`keyword` phù hợp cho:

- Mã sản phẩm, mã đơn hàng.
- Trạng thái, category, nhãn.
- Email hoặc tên định danh khi cần so khớp chính xác.
- Subfield dùng để sort hoặc aggregation.

Theo mặc định, `keyword` hỗ trợ doc values, là cấu trúc dữ liệu trên đĩa được dùng hiệu quả cho sort và aggregation. `text` mặc định không có doc values và fielddata bị tắt.

### Không dùng term thay cho match một cách tùy tiện

Ví dụ full-text query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": {
        "query": "mechanical keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

Query này tìm theo nội dung đã được phân tích trên field `title`.

Ví dụ exact match:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "title.keyword": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Query này so khớp giá trị keyword. Với keyword mặc định, chữ hoa/chữ thường và dấu câu có thể ảnh hưởng đến kết quả vì chuỗi được giữ nguyên. Nếu cần so khớp không phân biệt hoa thường, hãy thiết kế normalizer phù hợp và kiểm tra hành vi query.

Một lỗi thường gặp là gửi `term` với chuỗi người dùng nhập vào field `text`. `term` không tự phân tích chuỗi tìm kiếm như `match`; nếu giá trị không đúng với term đã được index, kết quả có thể rỗng.

## 5. Thiết kế multi-field cho tìm kiếm

Khi người dùng nhập từ khóa, nên tìm trên field `text` chính. Multi-field giúp giữ riêng hành vi full-text và exact match.

Ví dụ query tìm tiêu đề có các từ liên quan đến `wireless keyboard`:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": {
        "query": "wireless keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

`operator: "and"` yêu cầu tất cả token của query phải khớp. Nếu bỏ thuộc tính này, hành vi mặc định thường là `or`, nghĩa là document có thể khớp một trong các token. Chọn `and` hay `or` theo trải nghiệm tìm kiếm mong muốn.

Nếu ứng dụng muốn ưu tiên kết quả khớp toàn bộ tiêu đề, có thể kết hợp nhiều query:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "should": [
        {
          "match_phrase": {
            "title": {
              "query": "wireless keyboard",
              "boost": 3
            }
          }
        },
        {
          "match": {
            "title": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

`match_phrase` ưu tiên các token xuất hiện theo thứ tự gần nhau trong nội dung. `boost` tăng điểm cho nhánh khớp cụm từ. Field `title.keyword` không cần tham gia truy vấn full-text này.

### Dùng @Query trong repository

Một phương thức repository có thể khai báo query JSON để tìm theo field chính:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "title": {
              "query": "?0",
              "operator": "and"
            }
          }
        }
        """)
    List<Product> searchTitle(String phrase);
}
~~~

Đây là ví dụ dùng text block của Java để dễ đọc query. Nếu dự án dùng Java chưa hỗ trợ text block, có thể viết JSON trên một dòng theo cú pháp chuỗi của Java. Cần kiểm tra cú pháp annotation và khả năng bind tham số theo phiên bản Spring Data Elasticsearch đang dùng.

Với query phức tạp, sort hoặc aggregation, có thể xây dựng `NativeQuery` rồi gọi `ElasticsearchOperations`. API builder của `NativeQuery` thay đổi theo release; nguyên tắc là chỉ định đúng tên field Elasticsearch như `title.keyword` cho thao tác cần subfield đó.

## 6. Thiết kế multi-field cho sắp xếp

Sắp xếp chuỗi cần một giá trị có thể so sánh ổn định. `keyword` là lựa chọn phổ biến vì có doc values.

Ví dụ sort theo tiêu đề tăng dần:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "keyboard"
    }
  },
  "sort": [
    {
      "title.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

Query vẫn tìm trên `title`, còn sort sử dụng `title.keyword`. Hai mục đích dùng hai field path khác nhau nhưng lấy dữ liệu từ cùng một property nguồn.

Nếu muốn sort giảm dần, dùng `order: "desc"`.

### Sắp xếp không đồng nghĩa với tìm kiếm

Một kết quả được xếp theo `title.keyword` không có nghĩa Elasticsearch tìm kiếm theo chuỗi nguyên vẹn. Query và sort là hai phần độc lập của Search API:

- `query` quyết định document nào phù hợp.
- `sort` quyết định thứ tự các document phù hợp.

Có thể kết hợp `match` trên field text với sort theo keyword, hoặc lọc bằng category rồi sort theo title keyword.

### Sort không phân biệt hoa thường

Keyword mặc định giữ nguyên giá trị, nên sort có thể chịu ảnh hưởng bởi cách viết hoa/chữ thường. Nếu yêu cầu nghiệp vụ muốn sort không phân biệt hoa thường, có thể dùng keyword subfield với normalizer.

Ví dụ mapping có custom normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "sort": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer"
          }
        }
      }
    }
  }
}
~~~

Sau đó sort bằng `title.sort`:

~~~http
POST /products/_search
{
  "sort": [
    {
      "title.sort": {
        "order": "asc"
      }
    }
  ]
}
~~~

Normalizer xử lý keyword thành một token đã chuẩn hóa. Với ví dụ trên, lowercase filter chuyển chuỗi về chữ thường trước khi index. Vì normalizer ảnh hưởng đến cách giá trị được lập chỉ mục, hãy kiểm tra mapping và kết quả mong đợi trước khi áp dụng.

Không phải mọi cấu hình analyzer đều phù hợp với sort. Analyzer có thể tách chuỗi thành nhiều token; normalizer dành cho keyword phải tạo một token duy nhất.

### Sort trên dữ liệu có nhiều kiểu

Multi-field chỉ tạo thêm một cách lập chỉ mục của cùng giá trị. Nếu giá trị là chuỗi `"100"`, sort keyword sẽ theo thứ tự từ điển; `"100"` có thể đứng trước `"20"`. Nếu cần sort theo giá trị số, hãy lưu và sort trên field kiểu numeric.

Tương tự, ngày tháng nên được lưu dưới dạng `date` để so sánh thời gian. Không dùng keyword subfield để thay thế kiểu dữ liệu số hoặc ngày.

## 7. Thiết kế multi-field cho aggregation và thống kê

Aggregation cho phép nhóm, đếm, tính toán thống kê trên dữ liệu đã index. Với chuỗi, `terms` aggregation thường chạy trên keyword field.

Ví dụ đếm số sản phẩm theo category:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Nếu muốn nhóm theo tiêu đề chính xác, có thể dùng subfield:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_title": {
      "terms": {
        "field": "title.keyword",
        "size": 20
      }
    }
  }
}
~~~

`size: 0` ở cấp search yêu cầu không trả document hits; response tập trung vào aggregation. `terms.size` giới hạn số bucket được trả về. Nó không nhất thiết giới hạn số giá trị khác nhau tồn tại trong toàn index.

### Vì sao aggregation nên dùng keyword?

`terms` aggregation cần truy cập giá trị field hiệu quả. Keyword field có doc values và phù hợp cho thao tác này. Text field mặc định không bật fielddata vì việc tải term vào heap có thể gây tiêu tốn bộ nhớ lớn.

Nếu thử aggregation trên `title` và Elasticsearch báo lỗi yêu cầu fielddata, đừng vội bật fielddata. Trước tiên hãy xem có subfield keyword hay chưa và dùng `title.keyword`.

`fielddata: true` trên `text` có thể hữu ích trong một số trường hợp đặc biệt, nhưng có thể làm tăng đáng kể heap usage. Multi-field keyword thường là lựa chọn rõ ràng và dễ kiểm soát hơn cho sort và aggregation.

### Aggregation thống kê số lượng

Một `terms` aggregation có thể trả các bucket như:

~~~json
{
  "aggregations": {
    "products_by_title": {
      "buckets": [
        {
          "key": "Wireless Mechanical Keyboard",
          "doc_count": 18
        },
        {
          "key": "Compact Keyboard",
          "doc_count": 11
        }
      ]
    }
  }
}
~~~

`key` là giá trị keyword của bucket và `doc_count` là số document thuộc bucket đó.

Nếu có rất nhiều giá trị khác nhau, `terms` aggregation chỉ trả một số bucket theo cấu hình và có thể yêu cầu điều chỉnh `size`, `shard_size` hoặc dùng composite aggregation để duyệt theo trang. Không nên đặt `size` cực lớn một cách tùy tiện vì số bucket và chi phí hợp nhất có thể tăng mạnh.

### Cardinality và thống kê số giá trị duy nhất

Nếu chỉ cần ước lượng số giá trị khác nhau, dùng `cardinality` aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "unique_titles": {
      "cardinality": {
        "field": "title.keyword"
      }
    }
  }
}
~~~

Cardinality aggregation thường dùng thuật toán ước lượng, nên kết quả có thể không chính xác tuyệt đối. Nếu nghiệp vụ yêu cầu đếm chính xác từng giá trị, hãy chọn cách truy vấn hoặc xử lý dữ liệu phù hợp thay vì mặc định coi cardinality là phép đếm tuyệt đối.

## 8. Kết hợp tìm kiếm, sort và aggregation trong một request

Search API cho phép kết hợp nhiều mục đích trong cùng request. Ví dụ, tìm sản phẩm có tiêu đề liên quan đến `keyboard`, sắp xếp theo tiêu đề keyword và đồng thời thống kê kết quả theo category:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": {
        "query": "keyboard",
        "operator": "and"
      }
    }
  },
  "sort": [
    {
      "title.keyword": {
        "order": "asc"
      }
    }
  ],
  "from": 0,
  "size": 20,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Request này có ba phần:

1. `query` tìm document theo nội dung title đã phân tích.
2. `sort` sắp xếp kết quả theo giá trị nguyên vẹn của title.
3. `aggs` thống kê các category trong tập document phù hợp với query.

Aggregation ở đây được tính trên tập document phù hợp với query, không phải trên toàn bộ index. Nếu cần aggregation trên toàn bộ index bất kể query, cần thiết kế `global` aggregation hoặc request riêng tùy mục đích.

### Spring Data Elasticsearch đảm nhiệm phần nào?

Trong ứng dụng Spring, entity annotation mô tả mapping multi-field. Repository hoặc `ElasticsearchOperations` tạo Search API request và nhận response.

- `@MultiField` và `@InnerField` mô tả cấu trúc mapping.
- Repository method có thể phục vụ query phổ biến.
- `NativeQuery` phù hợp khi cần Query DSL, sort và aggregation nâng cao.
- `SearchHits<T>` giữ danh sách entity cùng metadata hit.
- Aggregation result được đọc từ phần aggregation của response theo API Spring Data tương ứng.

Cách dựng aggregation và đọc kết quả trong Java thay đổi giữa các phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Khi triển khai, đối chiếu API của release train đang dùng và giữ nguyên tên field Elasticsearch như `title.keyword` trong request.

## 9. Tạo và cập nhật mapping multi-field

Khai báo annotation trên entity không có nghĩa mọi index đang tồn tại tự động thay đổi mapping.

Khi ứng dụng tạo index mới dựa trên metadata của entity, Spring Data có thể tạo mapping chứa multi-field. Nhưng nếu index đã tồn tại, Elasticsearch không tự chuyển đổi mapping cũ chỉ vì code Java đã thêm `@MultiField`.

### Kiểm tra mapping hiện tại

Dùng Mapping API:

~~~http
GET /products/_mapping
~~~

Kiểm tra property có cấu trúc mong muốn hay chưa:

~~~json
{
  "title": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

Nếu `title.keyword` không tồn tại, query sort hoặc aggregation trên subfield đó sẽ thất bại.

### Thêm multi-field vào mapping đã tồn tại

Elasticsearch cho phép thêm một subfield mới vào field hiện có bằng Put Mapping API trong các trường hợp được hỗ trợ:

~~~http
PUT /products/_mapping
{
  "properties": {
    "title": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Tên và kiểu của field chính phải phù hợp với mapping đang tồn tại. Không thể tùy tiện đổi kiểu một field đã được index từ `text` thành `keyword` tại chỗ; thay đổi kiểu thường cần tạo index mới và reindex.

Điểm quan trọng: thêm subfield vào mapping không tự lập chỉ mục lại giá trị của các document cũ vào subfield mới. Document mới hoặc được index lại sẽ có dữ liệu cho subfield. Các document cũ có thể chưa có term/doc values cho `title.keyword`, nên sort và aggregation sẽ thiếu chúng.

### Reindex dữ liệu cũ

Một chiến lược an toàn là tạo index mới với mapping đầy đủ, sau đó reindex dữ liệu:

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

Quy trình tổng quát:

1. Tạo index đích với mapping multi-field mới.
2. Reindex dữ liệu từ index cũ sang index mới.
3. Kiểm tra số lượng document và mapping.
4. Thử full-text search, sort và aggregation trên index mới.
5. Chuyển alias hoặc cấu hình ứng dụng sang index mới theo kế hoạch triển khai.
6. Chỉ xóa index cũ sau khi xác nhận không còn caller cần nó và có backup phù hợp.

Với hệ thống đang hoạt động, cần tính đến dữ liệu ghi mới trong thời gian reindex, alias, write alias và chiến lược đồng bộ thay đổi. Không chuyển traffic trước khi dữ liệu và mapping đích đã sẵn sàng.

### Mapping template và index mới

Nếu hệ thống tạo index theo thời gian hoặc dùng data stream, hãy cập nhật index template để các index mới đều có multi-field. Nếu chỉ sửa một index hiện tại, các index được tạo sau đó vẫn có thể thiếu mapping mới.

Spring Data annotation mô tả mapping cho entity, nhưng việc quản lý index template, alias, rollover và reindex thường cần quy trình triển khai riêng.

## 10. Normalizer cho exact match và sort

Keyword field giữ chuỗi nguyên vẹn, nhưng có thể cần chuẩn hóa để tìm kiếm chính xác không phân biệt hoa thường hoặc chuẩn hóa một số ký tự.

Normalizer hoạt động trên keyword field và phải tạo ra một token duy nhất. Ví dụ lowercase normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folded_keyword": {
          "type": "custom",
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
      "title": {
        "type": "text",
        "fields": {
          "folded": {
            "type": "keyword",
            "normalizer": "folded_keyword"
          }
        }
      }
    }
  }
}
~~~

Subfield `title.folded` lưu dạng đã chuẩn hóa. Có thể dùng nó cho exact match không phân biệt hoa thường và sort theo quy tắc đã chuẩn hóa.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "title.folded": "WIRELESS KEYBOARD"
    }
  },
  "sort": [
    {
      "title.folded": {
        "order": "asc"
      }
    }
  ]
}
~~~

Normalizer sẽ xử lý giá trị query theo cấu hình phù hợp của keyword field. Hãy kiểm tra kết quả bằng một tập dữ liệu có chữ hoa, chữ thường và dấu tiếng Việt nếu ứng dụng hỗ trợ đa ngôn ngữ.

Nếu dùng asciifolding, các dấu có thể được chuyển về dạng không dấu theo quy tắc filter. Đây là quyết định nghiệp vụ: không phải lúc nào việc gộp các chuỗi có dấu và không dấu cũng là điều mong muốn.

## 11. Những sai lầm phổ biến khi thiết kế multi-field

### Dùng field text để sort hoặc aggregation

`text` tối ưu cho full-text search. Sort hoặc aggregation trên field này thường không hoạt động mặc định do fielddata bị tắt. Hãy dùng subfield keyword.

### Dùng term trên field đã phân tích

`term` không phân tích chuỗi tìm kiếm như `match`. Hãy xác định field mapping và mục tiêu query trước khi chọn query type.

### Nghĩ rằng subfield xuất hiện trong _source

Multi-field là cách index một property nhiều lần. `_source` vẫn chứa property gốc. Đừng viết code mong đợi một thuộc tính JSON mới tên `title.keyword`.

### Thêm multi-field rồi kỳ vọng dữ liệu cũ tự có

Mapping mới không tự lập chỉ mục lại các document đã tồn tại. Cần reindex hoặc một quy trình cập nhật document để subfield mới có dữ liệu.

### Tạo quá nhiều subfield

Mỗi subfield làm tăng chi phí index và storage. Không nên tạo nhiều analyzer hoặc keyword variant nếu không có truy vấn cụ thể cần chúng.

### Dùng keyword cho chuỗi dài không kiểm soát

Keyword có giới hạn thực tế về kích thước term. Với nội dung dài, cần cân nhắc `ignore_above`, analyzer phù hợp hoặc chỉ tạo keyword subfield cho những giá trị có độ dài phù hợp. `ignore_above` có thể khiến giá trị dài không được index vào subfield, vì vậy exact match, sort và aggregation trên giá trị đó có thể không có kết quả như mong muốn.

### Dùng keyword để sort số hoặc ngày

Keyword sort theo thứ tự chuỗi. Nếu giá trị biểu diễn số hoặc ngày, hãy dùng kiểu numeric hoặc date phù hợp để có semantics sắp xếp đúng.

### Bật fielddata để né mapping chưa đúng

Bật `fielddata` trên `text` có thể tiêu tốn heap lớn. Trước tiên hãy thiết kế keyword subfield và xác nhận mapping; chỉ dùng fielddata khi có lý do đặc biệt và đã đánh giá tải bộ nhớ.

## 12. Kiểm tra và debug multi-field

Khi kết quả search, sort hoặc aggregation không đúng, hãy kiểm tra theo thứ tự.

### Kiểm tra mapping

~~~http
GET /products/_mapping
~~~

Xác nhận:

- Field chính có đúng kiểu `text` không.
- Analyzer có đúng tên và cấu hình không.
- Subfield có đúng suffix và kiểu `keyword` không.
- Normalizer có tồn tại và được gắn đúng subfield không.
- Các index trong alias có cùng mapping hay không.

Nếu alias trỏ đến nhiều index có mapping khác nhau, một query có thể hoạt động khác nhau trên từng index hoặc gây lỗi khi sort/aggregation.

### Kiểm tra analyzer

Dùng Analyze API để xem chuỗi được tách token như thế nào:

~~~http
POST /products/_analyze
{
  "field": "title",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Kết quả cho biết token, vị trí và offset. Nếu token không như mong muốn, kiểm tra analyzer, tokenizer và token filters.

### Kiểm tra field capabilities

Có thể dùng Field Capabilities API để xem kiểu field trên một hoặc nhiều index:

~~~http
GET /products/_field_caps?fields=title,title.keyword
~~~

Điều này hữu ích khi alias trỏ đến nhiều index và cần biết `title.keyword` có cùng kiểu, cùng khả năng sort/aggregation trên mọi index hay không.

### Thử từng thao tác riêng

Trước khi kết hợp query, sort và aggregation, hãy thử riêng:

1. `match` trên `title`.
2. `term` trên `title.keyword`.
3. `sort` trên `title.keyword`.
4. `terms` aggregation trên `title.keyword`.

Nếu từng phần hoạt động độc lập, kết hợp chúng sau đó sẽ dễ khoanh vùng hơn. Kiểm tra cả document cũ và document mới sau khi thay đổi mapping.

### Quan sát dữ liệu thiếu trong subfield

Nếu sort hoặc aggregation bỏ sót một số document, kiểm tra:

- Document có giá trị `title` hay không.
- Subfield đã tồn tại khi document được index chưa.
- Giá trị có vượt giới hạn `ignore_above` không.
- Document cũ đã được reindex chưa.
- Có document nào được ghi vào index khác trong alias với mapping khác không.

Không phải mọi hit đều có giá trị ở mọi subfield. Cần quyết định rõ ứng dụng xử lý missing value khi sort như thế nào.

## 13. Ví dụ thiết kế end-to-end cho Product

Giả sử ứng dụng cần ba chức năng:

- Tìm sản phẩm theo từ khóa trong tiêu đề.
- Sắp xếp kết quả theo tiêu đề không phân biệt hoa thường.
- Thống kê số sản phẩm theo từng tiêu đề.

Mapping có thể thiết kế như sau:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          },
          "sort": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer"
          }
        }
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

Trong Spring Data entity, khai báo tương ứng:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword
        ),
        @InnerField(
            suffix = "sort",
            type = FieldType.Keyword,
            normalizer = "lowercase_normalizer"
        )
    }
)
private String title;
~~~

Custom normalizer cần được khai báo trong index settings trước khi mapping tham chiếu đến nó. Trong Spring Data, có thể quản lý settings bằng file cấu hình index hoặc quy trình tạo index riêng phù hợp với dự án. Chỉ khai báo tên normalizer trong annotation không tự tạo ra định nghĩa normalizer nếu settings chưa có.

Tìm kiếm:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "wireless keyboard"
    }
  }
}
~~~

Sắp xếp:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "keyboard"
    }
  },
  "sort": [
    {
      "title.sort": {
        "order": "asc"
      }
    }
  ]
}
~~~

Thống kê:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "titles": {
      "terms": {
        "field": "title.keyword",
        "size": 50
      }
    }
  }
}
~~~

Một property `title` phục vụ ba cách sử dụng. `title` xử lý tìm kiếm toàn văn, `title.sort` phục vụ thứ tự không phân biệt hoa thường, còn `title.keyword` dùng cho nhóm giá trị nguyên bản.

## 14. Nguyên tắc thiết kế và vận hành

Khi thiết kế multi-field cho Spring Data Elasticsearch, hãy bắt đầu từ truy vấn và thao tác mà ứng dụng thực sự cần:

- Dùng `text` cho nội dung cần analyzer và full-text search.
- Thêm `keyword` subfield khi cần exact match, sort hoặc aggregation.
- Dùng normalizer cho keyword khi cần quy tắc chuẩn hóa rõ ràng.
- Dùng field numeric/date cho dữ liệu số và thời gian; keyword không thay thế semantics của các kiểu đó.
- Giữ số lượng subfield vừa đủ để hạn chế chi phí indexing và storage.
- Kiểm tra mapping thực tế trên cluster, không chỉ dựa vào annotation Java.
- Khi thêm subfield vào index đã có dữ liệu, lập kế hoạch reindex hoặc cập nhật document cũ.
- Đảm bảo mọi index đứng sau alias có mapping tương thích.
- Dùng `NativeQuery` hoặc Search API tương ứng khi cần phối hợp query, sort và aggregation nâng cao.
- Kiểm tra dữ liệu thiếu và giới hạn keyword khi kết quả sort/aggregation không đầy đủ.

Multi-field là cách biểu diễn một thuộc tính theo nhiều mục đích mà vẫn giữ mô hình entity đơn giản. Khi chọn đúng analyzer, keyword subfield và mapping lifecycle, ứng dụng có thể tìm kiếm linh hoạt, sắp xếp ổn định và tổng hợp dữ liệu hiệu quả trên cùng một document field.

