# Kiểm tra token bằng Analyze API

Trong Elasticsearch, văn bản được chuyển thành token trước khi được lưu vào inverted index hoặc trước khi được dùng để thực hiện một truy vấn toàn văn. Quá trình này được điều khiển bởi **analyzer**. Một thay đổi nhỏ trong tokenizer hoặc token filter có thể làm thay đổi token được tạo ra, từ đó ảnh hưởng trực tiếp đến kết quả tìm kiếm.

Khi một truy vấn không trả về tài liệu mong đợi, không nên đoán ngay rằng dữ liệu bị thiếu hoặc query viết sai. Trước tiên, hãy kiểm tra văn bản đầu vào được phân tích thành những token nào. Elasticsearch cung cấp **Analyze API** (`_analyze`) để thực hiện chính việc đó. API cho phép kiểm tra analyzer có sẵn, analyzer gắn với một field hoặc một tổ hợp character filter, tokenizer và token filter được chỉ định trực tiếp trong request.

Bài học này trình bày cách dùng Analyze API, cách đọc kết quả token, cách kiểm tra analyzer theo mapping, cách thử analyzer tùy chỉnh và cách sử dụng kết quả phân tích để chẩn đoán vấn đề trong Spring Data Elasticsearch.

## 1. Analyzer và token trong Elasticsearch

Analyzer nhận văn bản và tạo ra một chuỗi token. Chuỗi token này là cơ sở để Elasticsearch lập chỉ mục văn bản hoặc xử lý chuỗi truy vấn.

Một analyzer thông thường gồm ba phần theo thứ tự:

1. **Character filters**: biến đổi chuỗi ký tự trước khi tách token, ví dụ loại bỏ HTML hoặc thay thế một mẫu ký tự.
2. **Tokenizer**: chia chuỗi thành các token, ví dụ tách từ theo ranh giới từ.
3. **Token filters**: biến đổi, loại bỏ hoặc mở rộng token, ví dụ chuyển chữ thường, bỏ stop words, stemming hoặc synonym.

```text
Văn bản đầu vào
      |
      v
Character filters
      |
      v
Tokenizer
      |
      v
Token filters
      |
      v
Chuỗi token đầu ra
```

Ví dụ, văn bản `The QUICK Brown Foxes!` khi đi qua một analyzer tiếng Anh có thể được chuyển thành các token chữ thường; filter stop words có thể loại `the`, còn stemmer có thể đưa `foxes` về dạng gốc `fox`. Kết quả thực tế phụ thuộc analyzer, ngôn ngữ và thứ tự các filter.

Token không chỉ là một chuỗi ký tự. Elasticsearch/Lucene còn có thể lưu các thuộc tính như vị trí token, offset trong văn bản gốc, kiểu token và thông tin về độ dài vị trí. Các thuộc tính này hỗ trợ phrase query, highlighting và xử lý token graph.

## 2. Analyze API dùng để làm gì?

Analyze API cho phép gửi văn bản đến Elasticsearch và xem kết quả analyzer tạo ra. API này hữu ích khi:

- Xác định tokenizer đang tách văn bản theo quy tắc nào.
- Kiểm tra filter lowercase, stop words, stemming, synonym hoặc asciifolding.
- Xác nhận analyzer được mapping cho một field.
- So sánh analyzer lập chỉ mục và analyzer dự kiến dùng khi tìm kiếm.
- Thử một analyzer tùy chỉnh trước khi đưa vào index settings.
- Chẩn đoán vì sao truy vấn `match` hoặc `match_phrase` không khớp tài liệu.
- Kiểm tra tác động của dấu câu, chữ hoa/thường, ký tự có dấu, HTML hoặc chuỗi nhiều ngôn ngữ.

Analyze API không tìm kiếm document và không trả về danh sách tài liệu phù hợp. Nó chỉ phân tích chuỗi đầu vào và trả về các token. Vì vậy, kết quả của `_analyze` giúp kiểm tra một phần của pipeline tìm kiếm, nhưng không thay thế việc kiểm tra mapping, dữ liệu đã lập chỉ mục và query thực tế.

## 3. Gọi Analyze API cơ bản

Analyze API có thể được gọi ở cấp cluster:

```http
POST _analyze
{
  "analyzer": "standard",
  "text": "The QUICK Brown-Foxes!"
}
```

`analyzer` chỉ định tên analyzer muốn sử dụng; `text` là văn bản cần phân tích. Ví dụ này dùng analyzer `standard` có sẵn trong Elasticsearch.

Một phản hồi thường có dạng:

```json
{
  "tokens": [
    {
      "token": "the",
      "start_offset": 0,
      "end_offset": 3,
      "type": "<ALPHANUM>",
      "position": 0
    },
    {
      "token": "quick",
      "start_offset": 4,
      "end_offset": 9,
      "type": "<ALPHANUM>",
      "position": 1
    }
  ]
}
```

Đây là phần minh họa cấu trúc response; kết quả đầy đủ phụ thuộc tokenizer và văn bản đầu vào. Một response có thể chứa nhiều token hơn ví dụ trên.

Các thuộc tính thường cần đọc:

| Thuộc tính | Ý nghĩa |
|---|---|
| `token` | Nội dung token được tạo ra |
| `start_offset` | Vị trí bắt đầu token trong văn bản đầu vào |
| `end_offset` | Vị trí kết thúc token trong văn bản đầu vào |
| `type` | Loại token do tokenizer cung cấp |
| `position` | Vị trí token trong chuỗi token |
| `positionLength` | Độ dài vị trí của token trong token graph, khi thuộc tính này được cung cấp |

Offset giúp liên hệ token với đoạn văn bản gốc, ví dụ khi highlighting. Position cho biết thứ tự và khoảng cách tương đối giữa token, rất quan trọng với phrase query. Với synonym filter dạng graph, một số token có thể chia sẻ hoặc mở rộng vị trí; không nên chỉ nhìn danh sách chuỗi token rồi kết luận rằng các token nằm cạnh nhau.

## 4. Kiểm tra analyzer đang được gắn với một field

Trong ứng dụng thực tế, field có thể khai báo analyzer riêng trong mapping. Thay vì đoán tên analyzer hoặc gọi một analyzer chung, hãy dùng tham số `field` để kiểm tra analyzer được cấu hình cho field đó.

Giả sử index `articles` có mapping:

```http
PUT articles
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      }
    }
  }
}
```

Kiểm tra field `title`:

```http
POST articles/_analyze
{
  "field": "title",
  "text": "Spring Data Elasticsearch"
}
```

Khi dùng `field`, Elasticsearch tra mapping của field và sử dụng analyzer gắn với field đó. Cách này giúp kiểm tra cấu hình của index thay vì chỉ thử một analyzer có tên biết trước.

Nếu field không tồn tại trong mapping hoặc không có analyzer phù hợp, request có thể báo lỗi hoặc sử dụng hành vi mặc định theo quy tắc của API/phiên bản. Hãy kiểm tra mapping trước khi kết luận.

Lấy mapping hiện tại bằng:

```http
GET articles/_mapping
```

Lệnh này giúp xác nhận kiểu field, analyzer, search analyzer và các multi-fields đã được tạo trong index thực tế.

### 4.1. Kiểm tra multi-field

Một thuộc tính có thể được lập chỉ mục dưới nhiều kiểu bằng multi-fields:

```http
PUT articles
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
```

Có thể kiểm tra field chính:

```http
POST articles/_analyze
{
  "field": "title",
  "text": "Spring Data Elasticsearch"
}
```

Và field con:

```http
POST articles/_analyze
{
  "field": "title.keyword",
  "text": "Spring Data Elasticsearch"
}
```

Field `title` kiểu `text` được phân tích thành token. Field `title.keyword` giữ toàn bộ giá trị như một term (có thể có normalizer nếu được cấu hình). So sánh hai kết quả để hiểu vì sao truy vấn toàn văn và truy vấn chính xác có hành vi khác nhau.

## 5. Kiểm tra analyzer bằng tên cụ thể

Có thể gọi analyzer dựng sẵn mà không cần tạo index:

```http
POST _analyze
{
  "analyzer": "whitespace",
  "text": "Spring-Data Elasticsearch"
}
```

Analyzer `whitespace` tách theo khoảng trắng; dấu gạch nối vẫn có thể nằm trong token. So sánh với `standard`:

```http
POST _analyze
{
  "analyzer": "standard",
  "text": "Spring-Data Elasticsearch"
}
```

Sự khác nhau cho thấy tokenizer quyết định ranh giới token như thế nào. Các analyzer dựng sẵn khác có thể gồm `simple`, `stop`, `keyword`, `pattern` và analyzer theo ngôn ngữ. Không phải analyzer nào cũng phù hợp cho mọi field; hãy chọn dựa trên ngôn ngữ và nhu cầu tìm kiếm.

Ví dụ analyzer `keyword` coi toàn bộ chuỗi là một token:

```http
POST _analyze
{
  "analyzer": "keyword",
  "text": "Spring Data Elasticsearch"
}
```

Điều này minh họa khác biệt giữa một field văn bản cần tách từ và một field chuỗi cần so khớp nguyên giá trị.

## 6. Kiểm tra từng thành phần của analyzer

Analyze API có thể nhận `char_filter`, `tokenizer` và `filter` riêng lẻ. Cách này hữu ích khi muốn thử một tổ hợp analyzer mà chưa cần ghi nó vào index settings.

Ví dụ, loại bỏ HTML, tách theo tokenizer `standard`, rồi chuyển token thành chữ thường và bỏ dấu ASCII:

```http
POST _analyze
{
  "char_filter": ["html_strip"],
  "tokenizer": "standard",
  "filter": ["lowercase", "asciifolding"],
  "text": "<p>Café SPRING Data</p>"
}
```

Request trên định nghĩa một pipeline phân tích trực tiếp trong request. Nó không tạo hoặc thay đổi analyzer lưu trong index. Đây là cách nhanh để thử thành phần và thứ tự xử lý.

Có thể thay tokenizer để quan sát tác động của ranh giới từ:

```http
POST _analyze
{
  "tokenizer": "whitespace",
  "filter": ["lowercase"],
  "text": "Spring-Data Elasticsearch"
}
```

Hoặc chỉ thử token filter trên tokenizer chuẩn:

```http
POST _analyze
{
  "tokenizer": "standard",
  "filter": ["lowercase", "stop"],
  "text": "The quick brown fox jumps over the lazy dog"
}
```

Nếu một filter yêu cầu cấu hình riêng, cần khai báo filter đó trong index settings và tham chiếu theo tên. Không phải mọi filter đều có thể được mô tả đầy đủ chỉ bằng tên filter dựng sẵn.

## 7. Xem chi tiết quá trình phân tích bằng `explain`

Khi chỉ nhận danh sách token cuối cùng, có thể khó xác định thành phần nào đã thay đổi văn bản. Tham số `explain: true` yêu cầu Elasticsearch trả về thông tin chi tiết của các bước trong quá trình analysis.

```http
POST _analyze
{
  "analyzer": "standard",
  "text": "The QUICK Brown-Foxes!",
  "explain": true
}
```

Response khi bật `explain` có cấu trúc chi tiết hơn response thông thường. Nó có thể cho thấy:

- Kết quả sau mỗi character filter.
- Tokenizer và các token mà tokenizer tạo ra.
- Kết quả sau từng token filter.
- Thuộc tính token ở từng giai đoạn.

Để tập trung vào một số thuộc tính token, có thể truyền `attributes` cùng `explain`:

```http
POST _analyze
{
  "analyzer": "standard",
  "text": "Spring Data Elasticsearch",
  "explain": true,
  "attributes": ["keyword", "positionLength"]
}
```

`attributes` yêu cầu thêm các token attribute được hỗ trợ vào phần giải thích. Thuộc tính cụ thể có thể phụ thuộc tokenizer/filter và phiên bản Elasticsearch. Khi phân tích synonym graph hoặc phrase query, chú ý vị trí token và position length thay vì chỉ kiểm tra văn bản token.

`explain` có thể tạo response lớn hơn đáng kể so với chế độ thông thường. Dùng nó cho chuỗi thử nghiệm ngắn và tắt khi không cần xem chi tiết.

## 8. Tạo và kiểm tra custom analyzer

Trong ứng dụng thực tế, analyzer thường được định nghĩa trong settings của index để mapping có thể tham chiếu theo tên. Ví dụ tạo analyzer `product_text`:

```http
PUT products
{
  "settings": {
    "analysis": {
      "char_filter": {
        "replace_ampersand": {
          "type": "mapping",
          "mappings": [
            "& => and"
          ]
        }
      },
      "analyzer": {
        "product_text": {
          "type": "custom",
          "char_filter": ["html_strip", "replace_ampersand"],
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
        "analyzer": "product_text"
      }
    }
  }
}
```

Sau khi tạo index, kiểm tra analyzer bằng tên field:

```http
POST products/_analyze
{
  "field": "name",
  "text": "Café & Tea"
}
```

Hoặc gọi analyzer theo tên:

```http
POST products/_analyze
{
  "analyzer": "product_text",
  "text": "Café & Tea"
}
```

Hai cách có mục đích hơi khác nhau. `field` kiểm tra analyzer gắn với mapping của field; `analyzer` kiểm tra analyzer được gọi trực tiếp theo tên. Nếu hai cấu hình khác nhau, kết quả có thể khác nhau.

### 8.1. Thử analyzer trước khi lưu vào index

Nếu chưa muốn tạo index, có thể mô tả trực tiếp các thành phần trong request `_analyze`. Tuy nhiên, khi đã đưa analyzer vào settings, hãy kiểm tra lại bằng endpoint của index vì đó là cấu hình thực tế mà mapping sẽ sử dụng.

Việc thử trực tiếp rất tiện để so sánh các tokenizer/filter, nhưng không thay thế việc kiểm tra index settings sau khi triển khai. Analyzer có thể phụ thuộc custom filter, synonym set, plugin hoặc cấu hình chỉ tồn tại trong cluster.

### 8.2. Analyzer và normalizer

Analyzer có thể tạo nhiều token từ một chuỗi. Normalizer dành cho field `keyword`, chuẩn hóa giá trị nhưng giữ nó thành một token duy nhất. Khi kiểm tra field `keyword`, cần chú ý normalizer được khai báo trong mapping.

Ví dụ mapping:

```http
PUT customers
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "emailLabel": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
```

Có thể kiểm tra cách chuẩn hóa field bằng Analyze API với `field`:

```http
POST customers/_analyze
{
  "field": "emailLabel",
  "text": "USER@EXAMPLE.COM"
}
```

Khi dùng normalizer, kết quả vẫn là một token duy nhất. Không nên dùng normalizer nếu yêu cầu nghiệp vụ là tách chuỗi thành nhiều từ để tìm kiếm toàn văn.

## 9. Kiểm tra analyzer lập chỉ mục và analyzer tìm kiếm

Elasticsearch có thể dùng analyzer khác nhau ở hai thời điểm:

- **Index-time analyzer** được dùng khi lập chỉ mục giá trị field.
- **Search-time analyzer** được dùng khi phân tích chuỗi truy vấn cho field đó.

Mapping có thể khai báo `analyzer` và `search_analyzer`:

```http
PUT articles
{
  "settings": {
    "analysis": {
      "analyzer": {
        "title_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        },
        "title_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "title_index",
        "search_analyzer": "title_search"
      }
    }
  }
}
```

Kiểm tra cách field được phân tích:

```http
POST articles/_analyze
{
  "field": "title",
  "text": "Café Spring"
}
```

Để thử riêng một analyzer đã đặt tên trong settings, chỉ định tên đó:

```http
POST articles/_analyze
{
  "analyzer": "title_index",
  "text": "Café Spring"
}
```

```http
POST articles/_analyze
{
  "analyzer": "title_search",
  "text": "Café Spring"
}
```

So sánh hai chuỗi token để xác nhận việc chuẩn hóa có khác nhau như dự định không. Tham số `field` hữu ích để xem analyzer gắn với mapping; gọi `analyzer` theo tên hữu ích để thử rõ từng cấu hình. Khi điều tra một truy vấn thực tế, cũng cần kiểm tra query type và search analyzer mà query đó sử dụng.

Không nên thay đổi analyzer một cách tùy tiện. Nếu index-time analyzer thay đổi, các document đã lập chỉ mục vẫn giữ token cũ cho tới khi được lập chỉ mục lại. Thông thường cần tạo index mới với settings/mapping mới, chạy reindex rồi chuyển alias hoặc ứng dụng sang index mới.

## 10. Dùng Analyze API để chẩn đoán kết quả tìm kiếm

Giả sử một ứng dụng tìm kiếm tiêu đề bằng `match`:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": "Spring Data"
    }
  }
}
```

Nếu kết quả không đúng kỳ vọng, có thể điều tra theo trình tự:

1. Lấy mapping của field `title` để biết kiểu field, analyzer và search analyzer.
2. Gọi `_analyze` với `field: "title"` để kiểm tra token theo cấu hình field.
3. Gọi `_analyze` với tên analyzer index-time và search-time để so sánh từng pipeline.
4. Kiểm tra `_source` của document để xác nhận giá trị gốc thực sự được lưu.
5. Kiểm tra document đã được lập chỉ mục sau khi thay đổi analyzer hay chưa.
6. Kiểm tra query type: `match`, `match_phrase`, `term` và các query khác có semantics khác nhau.
7. Chạy lại truy vấn thực tế sau khi xác định token đầu vào và token trong index tương thích.

### 10.1. Trường hợp chữ hoa và chữ thường

Nếu analyzer dùng `lowercase`, `Spring`, `SPRING` và `spring` có thể tạo ra cùng token `spring`. Nếu field là `keyword` không có normalizer, toàn bộ chuỗi có thể được giữ nguyên và phân biệt chữ hoa/thường.

Analyze API cho phép xác nhận điều đó trước khi thay query hoặc chuẩn hóa dữ liệu trong ứng dụng.

### 10.2. Trường hợp dấu và ký tự Unicode

`asciifolding` có thể chuyển một số ký tự có dấu sang dạng ASCII tương ứng. Ví dụ, `café` có thể tạo token `cafe` nếu filter được cấu hình. Không nên giả định filter này giải quyết mọi quy tắc ngôn ngữ hoặc mọi dạng Unicode. Hãy thử với dữ liệu thật, gồm chữ có dấu, dấu kết hợp và ký tự ngoài bảng Latin.

### 10.3. Trường hợp stop words và stemming

Stop filter có thể loại bỏ các từ phổ biến. Stemmer có thể đưa nhiều biến thể từ về dạng gốc. Những thay đổi này có thể làm thay đổi position và khả năng khớp cụm từ. Dùng `explain: true` để xem filter nào đã loại bỏ hoặc biến đổi token.

Không nên xóa stop words chỉ để giảm số token mà chưa xem xét nhu cầu tìm cụm từ. Một số từ ngắn vẫn có ý nghĩa quan trọng trong tên riêng, mã hoặc truy vấn nghiệp vụ.

### 10.4. Trường hợp synonym

Synonym filter có thể mở rộng một token thành các biến thể đồng nghĩa hoặc thay token bằng một nhóm token khác. Với synonym graph, một token có thể tạo ra nhiều đường đi trong token graph. Điều này ảnh hưởng tới phrase query và query builder.

Khi kiểm tra synonym, hãy dùng Analyze API với `explain: true` và quan sát vị trí token. Nếu chỉ nhìn `token` mà bỏ qua `position` hoặc `positionLength`, có thể hiểu sai cấu trúc các đường đi mà analyzer tạo ra.

## 11. Tiếng Việt và lựa chọn analyzer

Với tiếng Việt, khoảng trắng thường phân tách âm tiết, nhưng một từ có nghĩa có thể gồm nhiều âm tiết. Analyzer `standard` thường xử lý theo ranh giới ký tự/từ mà tokenizer hỗ trợ; nó không mặc nhiên thực hiện phân đoạn từ tiếng Việt theo từ điển.

Ví dụ, cụm `cơ chế tìm kiếm` có thể được tách thành các token tương ứng với các âm tiết `cơ`, `chế`, `tìm`, `kiếm`. Nếu yêu cầu nghiệp vụ cần nhận biết `cơ chế` hoặc `tìm kiếm` là đơn vị từ vựng, chỉ dùng analyzer tiêu chuẩn có thể chưa đáp ứng.

Analyze API rất hữu ích để kiểm tra điều này:

```http
POST _analyze
{
  "analyzer": "standard",
  "text": "Cơ chế tìm kiếm văn bản"
}
```

Sau đó so sánh với analyzer hoặc pipeline tiếng Việt được tổ chức lựa chọn. Nếu dùng plugin phân tích tiếng Việt, cần cài plugin tương thích trên tất cả node phù hợp trong cluster, khởi động lại node theo hướng dẫn và kiểm tra token đầu ra sau khi plugin được cài.

Không có một analyzer duy nhất phù hợp cho mọi tập dữ liệu tiếng Việt. Hãy xây dựng bộ truy vấn mẫu từ cách người dùng thực sự tìm kiếm, đánh giá precision/recall và thử với tên riêng, dấu câu, từ ghép, chữ viết tắt và từ mượn.

## 12. Tích hợp kiểm tra analyzer trong quy trình phát triển Spring Data Elasticsearch

Trong ứng dụng Spring Data Elasticsearch, analyzer được cấu hình trong index settings và mapping. Entity có thể khai báo analyzer bằng annotation `@Field`, nhưng analyzer tùy chỉnh phải tồn tại trong settings của index trước khi index được tạo.

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class Article {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "title_index")
    private String title;

    // Constructors, getters and setters
}
```

Tên `title_index` phải được khai báo trong analysis settings của index. Annotation `@Field` mô tả metadata cho field; nó không tự định nghĩa toàn bộ tokenizer và filter tùy chỉnh.

Một quy trình phát triển hữu ích:

1. Xác định ngôn ngữ, kiểu dữ liệu và nhu cầu tìm kiếm của field.
2. Thiết kế analyzer trong index settings.
3. Gọi `_analyze` trực tiếp với analyzer hoặc field để xem token.
4. Thử với tập văn bản đại diện và các trường hợp biên.
5. Tạo index với settings/mapping đã chọn.
6. Lập chỉ mục một số document mẫu.
7. Chạy query thực tế và đánh giá kết quả.
8. Chỉ sau khi kết quả phù hợp mới áp dụng cấu hình cho dữ liệu lớn.

Khi analyzer đã được dùng để lập chỉ mục, thay đổi analyzer có thể yêu cầu reindex. Do đó, nên đưa settings/mapping vào quy trình quản lý phiên bản và migration index.

## 13. Giới hạn của Analyze API

Analyze API trả lời câu hỏi “văn bản này được analyzer chuyển thành token nào?”. Nó không trả lời đầy đủ những câu hỏi sau:

- Document cụ thể có tồn tại trong index hay không.
- Document đã được refresh và có thể tìm kiếm hay chưa.
- Query có kết hợp các token theo AND, OR, phrase hay bool clause nào.
- Document có điểm relevance bao nhiêu.
- Field có bị giới hạn bởi routing, alias filter, security hoặc query filter không.
- Một token có được lưu trong inverted index của document đã lập chỉ mục từ trước hay không.

Để điều tra đầy đủ, hãy kết hợp Analyze API với `_mapping`, `_settings`, đọc document qua `_source` và chạy query thực tế. Với các vấn đề về scoring hoặc query execution, có thể cần thêm `explain` của Search API hoặc Profile API; đây là những API khác với `explain` của Analyze API.

Analyze API cũng tiêu thụ tài nguyên của cluster. Không nên gửi văn bản rất lớn hoặc gọi liên tục trong mỗi request người dùng như một bước tìm kiếm thông thường. Dùng nó chủ yếu cho phát triển, kiểm thử và chẩn đoán; nếu ứng dụng cần phân tích văn bản ở runtime, cân nhắc analyzer/query phù hợp và giới hạn kích thước đầu vào.

## 14. Các lỗi thường gặp khi dùng Analyze API

### Không tìm thấy analyzer

Nếu analyzer tùy chỉnh chưa được khai báo trong settings của index hoặc tên gọi sai, Elasticsearch có thể trả lỗi không tìm thấy analyzer. Kiểm tra `_settings` và bảo đảm analyzer được tạo trước khi mapping tham chiếu tới nó.

### Field không tồn tại hoặc mapping không như dự kiến

Khi dùng tham số `field`, tên field phải khớp mapping thực tế, bao gồm cả tên multi-field như `title.keyword`. Dùng `GET index/_mapping` để xác nhận.

### Kết quả `_analyze` khác kết quả tìm kiếm

Có thể đang kiểm tra analyzer khác với analyzer mà query thực sự sử dụng; index-time analyzer và search-time analyzer có thể khác nhau. Hãy kiểm tra mapping và query, rồi chỉ định analyzer theo tên để so sánh.

### Thay analyzer nhưng document cũ vẫn không khớp

Document cũ được lập chỉ mục bằng token của analyzer tại thời điểm ghi. Thay mapping hoặc settings không tự xây dựng lại inverted index. Cần reindex dữ liệu vào index mới nếu thay đổi index-time analysis.

### Chỉ nhìn tên token mà bỏ qua vị trí

Phrase query và synonym graph phụ thuộc positions/position length. Bật `explain` và xem các token attribute khi cần chẩn đoán cụm từ hoặc synonym.

### Dùng analyzer chung cho dữ liệu nhiều ngôn ngữ

Một analyzer có thể xử lý không tốt một số ngôn ngữ hoặc loại nội dung. Tạo field/analyzer phù hợp, thử dữ liệu đại diện và đánh giá chất lượng kết quả thay vì giả định một cấu hình áp dụng tốt cho mọi nội dung.

## 15. Quy trình kiểm tra nhanh

Khi cần kiểm tra token của một field, có thể thực hiện theo các bước sau:

1. Xem mapping bằng `GET index/_mapping`.
2. Gọi `POST index/_analyze` với `field` và văn bản mẫu.
3. Xem `token`, `position`, `start_offset`, `end_offset` và `type`.
4. Bật `explain: true` nếu cần xem tác động của từng character filter, tokenizer hoặc token filter.
5. Gọi analyzer theo tên bằng `analyzer` để so sánh các cấu hình.
6. Kiểm tra query thật và document đã lập chỉ mục nếu token có vẻ đúng nhưng kết quả vẫn sai.

Analyze API là công cụ trực tiếp và dễ dùng nhất để quan sát bước phân tích văn bản của Elasticsearch. Khi hiểu token đầu ra, vị trí và các thuộc tính đi kèm, lập trình viên có thể thiết kế analyzer phù hợp, giải thích được hành vi của `match`/`match_phrase` và phát hiện sớm những khác biệt giữa cấu hình lập chỉ mục với cấu hình tìm kiếm trong ứng dụng Spring Data Elasticsearch.
