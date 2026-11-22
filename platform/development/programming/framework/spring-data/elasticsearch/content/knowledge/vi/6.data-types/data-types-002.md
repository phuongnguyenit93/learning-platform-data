# Multi-field với `@MultiField` và `@InnerField`

Trong Elasticsearch, một thuộc tính chuỗi đôi khi cần phục vụ nhiều cách sử dụng. Ví dụ, tên sản phẩm cần được phân tích để tìm kiếm toàn văn, đồng thời cần được giữ nguyên để lọc chính xác, sắp xếp hoặc aggregation. Nếu chỉ khai báo trường là `text`, ta có tìm kiếm theo từ nhưng không có sẵn trường phù hợp cho sort và aggregation. Nếu chỉ khai báo `keyword`, ta có thể so khớp toàn bộ giá trị nhưng không có hành vi tìm kiếm toàn văn như mong muốn.

**Multi-field** cho phép lập chỉ mục cùng một giá trị dưới nhiều kiểu dữ liệu hoặc cách phân tích khác nhau. Trong Spring Data Elasticsearch, annotation `@MultiField` khai báo trường chính, còn `@InnerField` khai báo các trường con bổ sung.

## 1. Multi-field giải quyết vấn đề gì?

Giả sử một sản phẩm có tên:

`Wireless Mechanical Keyboard`

Ứng dụng có các nhu cầu:

- Người dùng tìm sản phẩm bằng từ `mechanical` hoặc `keyboard`.
- Màn hình cần sắp xếp sản phẩm theo tên.
- Bộ lọc cần tìm chính xác tên `Wireless Mechanical Keyboard`.
- Báo cáo cần nhóm hoặc đếm tài liệu theo tên.

Các nhu cầu này có cách lập chỉ mục khác nhau:

| Nhu cầu | Kiểu trường phù hợp |
|---|---|
| Tìm theo từ, cụm từ, mức độ liên quan | `text` |
| So khớp toàn bộ giá trị | `keyword` |
| Sắp xếp theo giá trị chuỗi | Thường dùng `keyword` |
| Terms aggregation | Thường dùng `keyword` |

Multi-field tạo ra nhiều cách truy cập tới cùng một giá trị nguồn:

- `name`: trường chính kiểu `text`, dành cho tìm kiếm toàn văn.
- `name.keyword`: trường con kiểu `keyword`, dành cho so khớp chính xác, sort và aggregation.

Hai trường này không phải hai thuộc tính Java riêng. Chúng là hai cách lập chỉ mục của cùng một thuộc tính `name`.

## 2. Cấu trúc mapping của multi-field

Mapping Elasticsearch cho một multi-field có dạng:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
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

Cấu trúc này có thể đọc như sau:

- `name` là field chính có kiểu `text`.
- `analyzer: standard` quy định cách phân tích văn bản cho trường chính.
- `fields` khai báo các multi-field.
- `keyword` là tên trường con.
- `type: keyword` giữ giá trị thành một token để so khớp nguyên vẹn và hỗ trợ doc values.

Khi tài liệu được index với dữ liệu:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch lập chỉ mục giá trị của `name` theo analyzer của trường chính, đồng thời lập chỉ mục cùng giá trị cho trường con `name.keyword`. Trong `_source`, ứng dụng vẫn lưu một thuộc tính `name`; multi-field không tạo thêm một thuộc tính nguồn độc lập tên `name.keyword`.

Tên `keyword` chỉ là quy ước phổ biến. Có thể đặt tên khác như `raw`, `sort` hoặc `exact`, miễn là mapping và truy vấn dùng cùng tên.

## 3. Khai báo multi-field bằng `@MultiField` và `@InnerField`

Spring Data Elasticsearch cung cấp hai annotation:

- `@MultiField`: đặt trên thuộc tính entity để khai báo mapping nhiều trường.
- `@InnerField`: khai báo từng trường con bổ sung, gồm hậu tố và kiểu dữ liệu của trường con.

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
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

Ý nghĩa của phần khai báo multi-field:

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
        )
    }
)
private String name;
~~~

- `mainField` mô tả field chính `name`. Trong ví dụ, field chính là `text` với analyzer `standard`.
- `otherFields` là danh sách các trường con.
- `@InnerField` khai báo trường con có hậu tố `keyword` và kiểu `Keyword`.
- Spring Data kết hợp tên thuộc tính `name` với hậu tố để tạo đường dẫn trường con `name.keyword` trong mapping.

Có thể khai báo nhiều trường con nếu một giá trị cần nhiều cách sử dụng:

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
            suffix = "raw",
            type = FieldType.Keyword
        )
    }
)
private String title;
~~~

Mapping tương ứng có các trường `title`, `title.keyword` và `title.raw`. Trong thực tế, không nên tạo nhiều trường con nếu không có nhu cầu truy vấn cụ thể, vì mỗi trường bổ sung làm tăng chi phí lưu trữ và lập chỉ mục.

## 4. Truy vấn trường chính và trường con

Sau khi mapping có hiệu lực, hãy chọn đúng đường dẫn field cho từng loại truy vấn.

### Tìm kiếm toàn văn trên field chính

Dùng `match` với `name`:

~~~json
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Elasticsearch phân tích chuỗi truy vấn bằng search analyzer phù hợp và so sánh token với dữ liệu đã lập chỉ mục trên trường chính.

### So khớp chính xác với field con

Dùng `term` với `name.keyword`:

~~~json
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

`term` không phân tích đầu vào như `match`. Với trường keyword mặc định, giá trị cần khớp với giá trị được lập chỉ mục. Chữ hoa/chữ thường cũng được phân biệt nếu không cấu hình normalizer.

### Sắp xếp theo tên

Dùng trường con keyword:

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

Sắp xếp theo `text` không phải lựa chọn thông thường vì trường text không có doc values theo mặc định. Trường keyword được thiết kế để hỗ trợ thao tác sort hiệu quả.

### Aggregation theo tên

~~~json
{
  "aggs": {
    "products_by_name": {
      "terms": {
        "field": "name.keyword"
      }
    }
  }
}
~~~

Terms aggregation nhóm các tài liệu theo giá trị của trường con keyword. Nếu trường có số lượng giá trị duy nhất rất lớn, cần cân nhắc cardinality và chi phí aggregation trước khi dùng làm chiều thống kê.

### Kết hợp tìm kiếm toàn văn và lọc chính xác

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "name.keyword": "Wireless Mechanical Keyboard"
          }
        }
      ]
    }
  }
}
~~~

Trong ví dụ, `must` tìm nội dung trên trường chính `text`; `filter` áp dụng điều kiện lọc trên các trường keyword. Một truy vấn có thể sử dụng đồng thời cả hai trường của cùng một thuộc tính.

## 5. Dùng multi-field với Spring Data Elasticsearch

Khi đã khai báo `@MultiField`, Spring Data Elasticsearch có thể tạo mapping từ metadata của entity. Ứng dụng thao tác với entity như bình thường; không cần tạo một thuộc tính Java riêng cho `name.keyword`.

Ví dụ tạo index và mapping bằng `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndex() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

`indexOps(Product.class)` lấy thông tin index gắn với entity `Product`. `createWithMapping()` tạo index cùng mapping được suy ra từ metadata của entity, trong đó có khai báo multi-field.

Đây là ví dụ minh họa cách khởi tạo index. Trong ứng dụng thực tế, nên quản lý thời điểm tạo index bằng migration hoặc quy trình triển khai phù hợp, tránh nhiều instance ứng dụng cùng thực hiện thao tác tạo index khi khởi động.

Khi lưu entity:

~~~java
Product product = new Product();
product.setName("Wireless Mechanical Keyboard");

productRepository.save(product);
~~~

Spring Data lưu một giá trị `name` trong document. Elasticsearch lập chỉ mục giá trị đó cho field chính và các field con theo mapping đã tạo.

Khi tìm kiếm bằng repository, các method query derivation thông thường hoạt động theo thuộc tính Java. Với truy vấn cần chỉ rõ đường dẫn multi-field như `name.keyword`, có thể dùng Elasticsearch query tùy chỉnh hoặc `ElasticsearchOperations` để thể hiện chính xác field path.

## 6. Phân biệt `@InnerField` với object và nested field

Tên `@InnerField` có thể khiến người học nhầm rằng đây là cách khai báo object lồng nhau. Trong multi-field, `@InnerField` có nghĩa là **một cách lập chỉ mục bổ sung cho cùng một giá trị field**.

Ví dụ multi-field:

~~~text
name
├── name (text)
└── name.keyword (keyword)
~~~

Đây không phải hai object con trong JSON. Dữ liệu nguồn vẫn là:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Trong khi đó, object field mô tả một cấu trúc dữ liệu có thuộc tính con:

~~~json
{
  "manufacturer": {
    "name": "Acme",
    "country": "VN"
  }
}
~~~

Object mapping có thể khai báo các field như `manufacturer.name` và `manufacturer.country`. Nested mapping là một kiểu dữ liệu khác dùng khi cần bảo toàn mối liên hệ giữa các object trong một mảng theo semantics của Elasticsearch.

| Đặc điểm | Multi-field | Object / Nested |
|---|---|---|
| Mục đích | Lập chỉ mục cùng một giá trị theo nhiều cách | Mô tả dữ liệu có cấu trúc, thuộc tính con |
| Annotation liên quan | `@MultiField`, `@InnerField` | `@Field(type = Object/Nested)` và mapping thuộc tính con |
| Ví dụ đường dẫn | `name.keyword` | `manufacturer.name` |
| Có tạo thêm object trong `_source` không? | Không | Có, theo cấu trúc dữ liệu nguồn |

## 7. Kết hợp analyzer và normalizer

Multi-field hữu ích khi cùng một giá trị cần các quy tắc phân tích khác nhau.

Ví dụ, trường chính dùng analyzer `standard` để tìm kiếm toàn văn, còn trường con keyword dùng normalizer để so khớp không phân biệt chữ hoa/chữ thường:

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
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer"
          }
        }
      }
    }
  }
}
~~~

Trong Spring Data Elasticsearch, có thể khai báo normalizer trên `@InnerField` theo API annotation của phiên bản đang sử dụng:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword,
            normalizer = "lowercase_normalizer"
        )
    }
)
private String name;
~~~

Normalizer phải được định nghĩa trong index settings trước khi mapping tham chiếu đến nó. Chỉ khai báo tên normalizer trong annotation mà không tạo cấu hình tương ứng ở index settings sẽ làm mapping không hợp lệ khi tạo index.

Không nên nhầm analyzer với normalizer:

- Analyzer có thể tạo nhiều token, phù hợp cho tìm kiếm toàn văn.
- Normalizer biến đổi giá trị keyword nhưng giữ kết quả thành một token duy nhất.

Việc chọn analyzer/normalizer phải nhất quán với cách ứng dụng muốn tìm kiếm và so khớp dữ liệu.

## 8. Những lưu ý khi thay đổi mapping

Multi-field là một phần của mapping index. Việc thay đổi annotation Java không tự động biến đổi mapping đã tồn tại trong Elasticsearch.

### Khi tạo index mới

Khi index chưa tồn tại, Spring Data có thể tạo mapping dựa trên entity metadata. Hãy bảo đảm mapping được tạo trước khi ghi dữ liệu cần multi-field.

### Khi index đã tồn tại

Nếu field `name` đã tồn tại kiểu `text`, Elasticsearch cho phép bổ sung một multi-field vào mapping bằng update mapping API trong các trường hợp được hỗ trợ:

~~~http
PUT /products/_mapping
Content-Type: application/json

{
  "properties": {
    "name": {
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

Tuy nhiên, việc thêm field con vào mapping không tự lập chỉ mục lại giá trị của các document cũ cho field con mới. Document được index trước thời điểm bổ sung mapping có thể chưa có dữ liệu ở `name.keyword` trong inverted index/doc values.

Cần thực hiện một bước cập nhật hoặc reindex để các tài liệu cũ được lập chỉ mục lại theo mapping mới. Ví dụ, có thể dùng update by query để yêu cầu Elasticsearch lập chỉ mục lại document hiện có, hoặc tạo index mới với mapping đầy đủ rồi reindex dữ liệu sang index mới.

### Không thể đổi kiểu field chính tùy tiện

Nếu `name` đã là `text`, không thể sửa annotation thành `keyword` rồi mong Elasticsearch tự đổi kiểu field trong index hiện tại. Thay đổi kiểu field đã được lập chỉ mục thường cần index mới và reindex.

Multi-field thường là cách thiết kế ngay từ đầu để tránh phải thay đổi cấu trúc field chính về sau.

## 9. Các lỗi thường gặp

### Truy vấn nhầm field

Nếu dùng `term` với `name` nhưng kỳ vọng so khớp nguyên câu, kết quả có thể không đúng vì `name` là trường text đã qua analyzer. Hãy dùng `name.keyword` cho so khớp toàn bộ.

Ngược lại, nếu dùng `match` trên `name.keyword`, trường keyword vẫn chỉ có một token cho toàn bộ giá trị. Nó không hoạt động như tìm kiếm từng từ trên text field.

### Sort trên trường text

Sort theo `name` có thể lỗi vì `text` không bật doc values theo mặc định. Dùng `name.keyword` cho sort.

### Aggregation trên trường text

Terms aggregation trên `text` thường bị từ chối do fielddata mặc định tắt. Dùng multi-field keyword thay vì bật fielddata chỉ để giải quyết nhu cầu nhóm giá trị.

### Quên tạo hoặc cập nhật mapping

Nếu index không có `name.keyword`, truy vấn hoặc sort theo field path này sẽ không hoạt động như dự kiến. Kiểm tra mapping thực tế của index thay vì chỉ kiểm tra annotation Java.

### Thêm multi-field nhưng dữ liệu cũ chưa được lập chỉ mục lại

Mapping có thể đã xuất hiện `name.keyword`, nhưng tài liệu cũ vẫn chưa có giá trị được lập chỉ mục cho field con. Cần reindex hoặc cập nhật lại tài liệu cũ.

### Tạo quá nhiều multi-field

Mỗi field con bổ sung làm tăng chi phí lưu trữ và indexing. Chỉ tạo field con khi có truy vấn, sort hoặc aggregation thực sự cần cách lập chỉ mục đó.

## 10. Quy trình lựa chọn và sử dụng multi-field

Khi thiết kế entity:

1. Xác định các cách ứng dụng sẽ sử dụng một thuộc tính chuỗi.
2. Chọn kiểu dữ liệu cho field chính, thường là `text` nếu cần tìm kiếm toàn văn.
3. Thêm `@InnerField` kiểu `Keyword` nếu cần lọc chính xác, sort hoặc aggregation.
4. Đặt hậu tố có ý nghĩa, ví dụ `keyword`, `raw` hoặc `sort`.
5. Khai báo analyzer và normalizer đúng với nhu cầu.
6. Tạo index với mapping từ entity trước khi index dữ liệu.
7. Dùng field chính cho truy vấn toàn văn và field con cho so khớp chính xác/sort/aggregation.
8. Khi mapping đã tồn tại, lên kế hoạch cập nhật mapping và lập chỉ mục lại dữ liệu cũ nếu bổ sung multi-field.

Bảng ghi nhớ:

| Annotation / field | Vai trò |
|---|---|
| `@MultiField` | Khai báo một thuộc tính được lập chỉ mục dưới nhiều field |
| `mainField` | Cấu hình field chính |
| `otherFields` | Danh sách field con bổ sung |
| `@InnerField` | Khai báo hậu tố và kiểu dữ liệu của một field con |
| `name` | Field chính, ví dụ `text` |
| `name.keyword` | Field con, ví dụ `keyword` |

## Kết luận

Multi-field cho phép Elasticsearch lập chỉ mục cùng một giá trị theo nhiều cách để đáp ứng các nhu cầu truy vấn khác nhau. Trong Spring Data Elasticsearch, `@MultiField` định nghĩa field chính và danh sách field con; `@InnerField` định nghĩa từng field con với hậu tố và kiểu dữ liệu riêng. Hãy dùng field chính cho tìm kiếm toàn văn, field keyword cho lọc chính xác, sort và aggregation, đồng thời bảo đảm mapping và dữ liệu cũ được cập nhật đúng khi thay đổi index.
