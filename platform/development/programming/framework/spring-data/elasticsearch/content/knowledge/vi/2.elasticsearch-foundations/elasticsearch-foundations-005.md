# Phân biệt `text`, `keyword` và mục đích sử dụng

Trong Elasticsearch, một chuỗi không tự mang sẵn ý nghĩa “văn bản để tìm kiếm” hay “giá trị để so sánh”. **Mapping** quyết định Elasticsearch phân tích, lập chỉ mục và truy vấn chuỗi đó như thế nào. Hai kiểu dữ liệu quan trọng nhất cho chuỗi là `text` và `keyword`.

Khi thiết kế entity với Spring Data Elasticsearch, chọn đúng kiểu dữ liệu giúp kết quả tìm kiếm phù hợp, đồng thời hỗ trợ lọc, sắp xếp và thống kê mà không phải đánh đổi bộ nhớ hoặc hiệu năng.

## 1. Khác biệt cốt lõi

| Tiêu chí | `text` | `keyword` |
|---|---|---|
| Mục đích | Tìm kiếm nội dung theo từ hoặc cụm từ | Lưu và so sánh toàn bộ giá trị |
| Phân tích chuỗi | Có, thông qua analyzer | Không tách thành token; có thể chuẩn hóa bằng normalizer |
| Cách lập chỉ mục | Thường tạo nhiều token từ một chuỗi | Lập chỉ mục một token đại diện cho toàn bộ giá trị |
| Truy vấn thường dùng | `match`, `match_phrase` | `term`, `terms` |
| Độ phù hợp | Tìm kiếm toàn văn và tính điểm liên quan | So khớp chính xác, lọc, nhóm và sắp xếp |
| Sắp xếp / aggregation | Không phù hợp theo mặc định | Phù hợp |
| Ví dụ | Mô tả sản phẩm, nội dung bài viết | Mã SKU, trạng thái, danh mục, email |

Hãy xét chuỗi:

`Spring Data Elasticsearch`

- Với `text`, analyzer có thể tách chuỗi thành các token như `spring`, `data` và `elasticsearch`. Người dùng tìm `elasticsearch` vẫn có thể tìm thấy tài liệu chứa cả cụm ban đầu.
- Với `keyword`, toàn bộ chuỗi được xem như một giá trị duy nhất. Truy vấn giá trị `Spring Data Elasticsearch` có thể khớp toàn bộ; truy vấn riêng `elasticsearch` không có nghĩa là tìm một từ bên trong chuỗi.

Đây là khác biệt về cách lập chỉ mục, không đơn thuần là khác biệt cú pháp truy vấn.

## 2. `text`: dành cho tìm kiếm toàn văn

### Analyzer làm gì?

Khi một giá trị `text` được lập chỉ mục, Elasticsearch đưa nó qua một **analyzer**. Một analyzer thường gồm ba giai đoạn:

1. **Character filters**: biến đổi hoặc loại bỏ ký tự trước khi tách từ, ví dụ xử lý một số dạng HTML.
2. **Tokenizer**: chia chuỗi thành các token theo quy tắc ngôn ngữ.
3. **Token filters**: biến đổi token, ví dụ chuyển chữ hoa thành chữ thường, chuẩn hóa hoặc loại bỏ stop words nếu được cấu hình.

Ví dụ, analyzer `standard` thường tách văn bản theo ranh giới từ và chuyển token về chữ thường. Vì vậy, nội dung `Spring Data Elasticsearch` có thể được tìm bằng từ `spring` hoặc `data`.

Analyzer quyết định cách nội dung được lưu trong inverted index. Analyzer lúc tìm kiếm cũng quan trọng: Elasticsearch thường phân tích cụm từ truy vấn theo search analyzer tương ứng rồi tìm các token đã được lập chỉ mục.

### Các kiểu truy vấn phù hợp

**`match`** là lựa chọn thông dụng để tìm kiếm toàn văn. Elasticsearch phân tích đầu vào truy vấn rồi tìm các token phù hợp:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  }
}
~~~

Tài liệu có các token phù hợp có thể được trả về và được tính điểm liên quan. Cách kết hợp token phụ thuộc các tùy chọn của query, chẳng hạn `operator` hoặc `minimum_should_match`.

**`match_phrase`** dùng khi thứ tự và vị trí các token trong cụm từ quan trọng:

~~~json
{
  "query": {
    "match_phrase": {
      "description": "spring data"
    }
  }
}
~~~

Truy vấn này tìm cụm token theo thứ tự và khoảng cách phù hợp, thay vì chỉ cần các từ xuất hiện rời rạc.

### Vì sao không dùng `text` cho mọi chuỗi?

`text` được tối ưu cho tìm kiếm nội dung. Nó không phải lựa chọn mặc định tốt cho mã định danh, trạng thái hay các giá trị cần so sánh nguyên vẹn.

Một truy vấn `term` không phân tích đầu vào như `match`. Nếu trường `text` đã được tách thành các token chữ thường, truy vấn `term` với nguyên câu ban đầu thường không khớp như mong đợi. Truy vấn `term` với đúng một token đã được lập chỉ mục vẫn có thể khớp, nhưng điều đó không biến `text` thành kiểu phù hợp cho so khớp toàn bộ giá trị.

Ngoài ra, `text` không bật `fielddata` theo mặc định. Do đó, sắp xếp hoặc aggregation trực tiếp trên trường `text` thường không khả dụng. Có thể bật `fielddata`, nhưng việc này có thể tiêu thụ nhiều heap; thông thường nên dùng một trường `keyword` riêng cho các thao tác đó.

## 3. `keyword`: dành cho giá trị nguyên vẹn

`keyword` phù hợp khi ứng dụng cần coi toàn bộ chuỗi là một giá trị duy nhất:

- `status = PUBLISHED`
- `category = LAPTOP`
- `sku = KB-1001`
- `email = user@example.com`
- `countryCode = VN`

Trường `keyword` không đi qua quy trình tách từ như `text`. Theo mặc định, chữ hoa và chữ thường là khác nhau. Nếu cần chuẩn hóa, có thể cấu hình **normalizer**. Normalizer biến đổi giá trị nhưng vẫn giữ nó thành một token duy nhất; ví dụ có thể chuyển chữ về chữ thường để việc so khớp không phụ thuộc cách viết hoa.

### Truy vấn chính xác

Dùng `term` khi cần so khớp một giá trị:

~~~json
{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Dùng `terms` khi cần so khớp một trong nhiều giá trị:

~~~json
{
  "query": {
    "terms": {
      "status": ["PUBLISHED", "APPROVED"]
    }
  }
}
~~~

Với `keyword`, các truy vấn này so sánh giá trị đã được lập chỉ mục. Nếu trường có normalizer, cần hiểu rằng giá trị được chuẩn hóa trước khi so sánh.

### Sắp xếp và thống kê

`keyword` phù hợp cho các thao tác như sắp xếp theo tên, đếm số tài liệu theo trạng thái hoặc nhóm sản phẩm theo danh mục:

~~~json
{
  "sort": [
    {
      "sku": {
        "order": "asc"
      }
    }
  ],
  "aggs": {
    "products_by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
~~~

Các trường `keyword` thường có doc values để hỗ trợ sắp xếp và aggregation hiệu quả. Nếu giá trị chuỗi có thể rất dài và mapping sử dụng `ignore_above`, hãy kiểm tra giới hạn đó: giá trị vượt giới hạn có thể vẫn nằm trong `_source` nhưng không được lập chỉ mục ở trường keyword tương ứng.

## 4. Một thuộc tính cần cả tìm kiếm toàn văn và so khớp chính xác: multi-fields

Tên sản phẩm là ví dụ điển hình. Người dùng có thể muốn:

- Tìm sản phẩm bằng một phần tên hoặc các từ trong tên.
- Sắp xếp sản phẩm theo tên.
- Lọc chính xác một tên.
- Nhóm hoặc thống kê theo tên.

Nếu chỉ khai báo `text`, thao tác tìm kiếm toàn văn thuận tiện nhưng sắp xếp và aggregation gặp hạn chế. Nếu chỉ khai báo `keyword`, so khớp nguyên vẹn tốt nhưng tìm kiếm theo từng từ không phù hợp.

**Multi-fields** giải quyết vấn đề này bằng cách lập chỉ mục cùng một thuộc tính dưới nhiều kiểu dữ liệu. Ví dụ, trường `name` có một trường chính `text` và một trường con `name.keyword` kiểu `keyword`.

Mapping tương ứng có dạng:

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

Hai trường này có vai trò riêng:

| Trường | Dùng cho |
|---|---|
| `name` | `match`, `match_phrase`, tìm kiếm theo nội dung |
| `name.keyword` | `term`, lọc chính xác, sort, aggregation |

Tên `keyword` là hậu tố thường được chọn, không phải quy tắc bắt buộc của Elasticsearch. Tên trường con phụ thuộc mapping mà ứng dụng khai báo.

## 5. Khai báo mapping bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp annotation để mô tả mapping từ entity Java. Có thể dùng `@Field` để chọn kiểu dữ liệu cụ thể.

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

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructors, getters and setters
}
~~~

Trong ví dụ:

- `name` là multi-field. Spring Data mô tả trường chính kiểu `text` và trường con `name.keyword` kiểu `keyword`.
- `description` dùng `text` vì cần tìm kiếm nội dung.
- `status` và `category` dùng `keyword` vì thường được lọc hoặc nhóm theo giá trị.

`@Id` đánh dấu định danh của entity Spring Data. Định danh này có vai trò ánh xạ tài liệu; không nên nhầm nó với việc chọn `text` hay `keyword` cho các thuộc tính nghiệp vụ khác.

Nếu muốn dùng normalizer cho một trường keyword, cần khai báo normalizer trong index settings trước khi tạo index, sau đó tham chiếu tên normalizer trong mapping. Không thể chỉ đổi cách truy vấn ở repository rồi kỳ vọng dữ liệu đã được lập chỉ mục theo quy tắc mới.

## 6. Dùng đúng trường khi truy vấn

Giả sử entity `Product` có mapping ở phần trước.

### Tìm theo tên hoặc mô tả

Dùng trường `text`:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Truy vấn sẽ được phân tích theo analyzer của trường và tìm theo token.

### Lọc theo trạng thái

Dùng trường `keyword`:

~~~json
{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

### Tìm chính xác toàn bộ tên

Dùng trường con `name.keyword`:

~~~json
{
  "query": {
    "term": {
      "name.keyword": "Wireless Keyboard"
    }
  }
}
~~~

### Sắp xếp theo tên

Dùng trường con `name.keyword`:

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

### Kết hợp tìm kiếm và lọc

Một yêu cầu thực tế có thể vừa tìm sản phẩm theo nội dung, vừa chỉ lấy sản phẩm đang phát hành:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "wireless keyboard"
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
            "category": "ACCESSORIES"
          }
        }
      ]
    }
  }
}
~~~

Trong ví dụ này, `must` chứa điều kiện tìm kiếm toàn văn có thể ảnh hưởng điểm liên quan; `filter` chứa điều kiện lọc chính xác, không dùng để tính điểm liên quan. Việc chọn đúng trường cho từng điều kiện giúp query rõ ràng và tận dụng đúng cách lập chỉ mục.

## 7. Những lỗi thiết kế thường gặp

### Dùng `text` cho trạng thái hoặc mã

Nếu `status` được khai báo là `text`, chuỗi có thể bị phân tích thành token. Dùng `term` với nguyên giá trị trạng thái có thể không cho kết quả mong muốn. Hãy dùng `keyword` cho trạng thái, mã, enum, mã quốc gia và các giá trị cần so khớp nguyên vẹn.

### Dùng `keyword` cho nội dung dài cần tìm theo từ

Một mô tả dài được lưu bằng `keyword` sẽ được coi là một giá trị duy nhất. Người dùng tìm một từ trong mô tả sẽ không nhận được hành vi tìm kiếm toàn văn như mong đợi. Hãy dùng `text` cho nội dung cần phân tích.

### Dùng `text` để sort hoặc aggregation

Sắp xếp hoặc thống kê trên `text` thường bị từ chối vì `fielddata` mặc định tắt. Không nên bật `fielddata` chỉ để khắc phục nhanh nếu có thể tạo multi-field kiểu `keyword` phù hợp.

### Chỉ dùng `name` thay vì `name.keyword`

Với multi-field, `name` và `name.keyword` là hai trường được lập chỉ mục riêng. Tìm kiếm toàn văn dùng `name`; lọc chính xác, sort và aggregation dùng `name.keyword`. Chọn sai trường có thể gây lỗi truy vấn hoặc kết quả khác kỳ vọng.

### Thay đổi kiểu dữ liệu của một field đã tồn tại

Không thể đổi trực tiếp một field đã được lập chỉ mục từ `text` sang `keyword` bằng cách sửa annotation rồi mong index hiện tại tự chuyển đổi dữ liệu. Cần tạo index mới với mapping đúng, lập chỉ mục lại dữ liệu (reindex) và chuyển ứng dụng sang index mới theo quy trình triển khai phù hợp.

Khi bổ sung một multi-field vào mapping đã tồn tại, các tài liệu cũ cũng chưa tự có giá trị được lập chỉ mục cho trường con mới. Cần lập chỉ mục lại hoặc cập nhật lại tài liệu cũ để trường con được điền dữ liệu.

## 8. Quy tắc chọn kiểu dữ liệu

Có thể dùng các câu hỏi sau khi thiết kế entity:

1. Người dùng cần tìm một từ hoặc cụm từ nằm bên trong nội dung? Chọn `text`.
2. Ứng dụng cần so sánh toàn bộ giá trị, ví dụ trạng thái, mã, danh mục hoặc email? Chọn `keyword`.
3. Cùng một thuộc tính cần cả tìm kiếm toàn văn và lọc/sắp xếp chính xác? Dùng multi-fields với trường chính `text` và trường con `keyword`.
4. Có cần bỏ qua khác biệt chữ hoa/chữ thường khi so khớp keyword? Cấu hình normalizer phù hợp và tạo mapping/index với cấu hình đó.
5. Có cần sort hoặc aggregation? Kiểm tra query đang dùng trường `keyword`, thường là trường con của multi-field.

| Dữ liệu nghiệp vụ | Mapping thường phù hợp | Lý do |
|---|---|---|
| `description`, `content` | `text` | Tìm kiếm toàn văn |
| `title`, `name` | Multi-field: `text` + `keyword` | Tìm theo từ và sort/lọc chính xác |
| `status`, `type` | `keyword` | Giá trị phân loại hữu hạn |
| `sku`, `code` | `keyword` | Mã cần được giữ nguyên |
| `category`, `tags` | `keyword` | Lọc và aggregation |
| `email` | `keyword` | So khớp toàn bộ địa chỉ |

Không có quy tắc rằng mọi thuộc tính Java kiểu `String` phải là `text`. Kiểu Java chỉ biểu diễn dữ liệu trong ứng dụng; mapping Elasticsearch cần phản ánh cách dữ liệu được tìm kiếm và sử dụng.

## Kết luận

`text` và `keyword` phục vụ hai mô hình truy vấn khác nhau. `text` phân tích chuỗi thành token để tìm kiếm toàn văn; `keyword` giữ toàn bộ giá trị thành một đơn vị để so khớp, lọc, sắp xếp và thống kê. Trong Spring Data Elasticsearch, hãy khai báo mapping rõ ràng bằng `@Field`; dùng `@MultiField` khi một thuộc tính cần cả hai cách sử dụng.
