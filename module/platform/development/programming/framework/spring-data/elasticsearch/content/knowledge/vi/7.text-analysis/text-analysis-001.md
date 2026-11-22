# Phân biệt phân tích lúc lập chỉ mục và lúc tìm kiếm

Elasticsearch sử dụng **analyzer** để chuyển văn bản thành các token phục vụ tìm kiếm. Quá trình này diễn ra ở hai thời điểm khác nhau:

- **Index-time analysis**: phân tích nội dung khi document được ghi vào index.
- **Search-time analysis**: phân tích văn bản truy vấn khi người dùng tìm kiếm.

Hai quá trình có liên hệ chặt chẽ nhưng không nhất thiết phải dùng cùng một analyzer. Hiểu đúng sự khác biệt giúp thiết kế mapping, lựa chọn analyzer và xử lý các tình huống như chữ hoa/chữ thường, stemming, stop words và synonyms.

## 1. Hai thời điểm phân tích trong luồng tìm kiếm

Khi một document được lập chỉ mục, Elasticsearch phân tích giá trị của field `text` và lưu các token vào inverted index. Khi nhận một truy vấn toàn văn, Elasticsearch có thể phân tích văn bản truy vấn rồi tìm các token tương ứng trong inverted index.

~~~mermaid
flowchart TD
    A["Document JSON"] --> B["Index-time analyzer"]
    B --> C["Tokens"]
    C --> D["Inverted index"]
    E["Search text"] --> F["Search-time analyzer"]
    F --> G["Query tokens"]
    G --> H["Match với inverted index"]
    D --> H
    H --> I["Search results và relevance score"]
~~~

Ví dụ document có nội dung:

`The Quick Brown Foxes`

Analyzer lúc lập chỉ mục có thể chuyển nội dung thành:

`quick`, `brown`, `fox`

Khi người dùng tìm:

`QUICK FOX`

Search analyzer có thể chuyển truy vấn thành:

`quick`, `fox`

Hai tập token tương thích nên Elasticsearch có thể tìm được document.

Điểm cốt lõi là **token được tạo khi lập chỉ mục phải tương thích với token mà truy vấn tạo ra**. Nếu hai analyzer xử lý cùng một từ theo cách không tương thích, kết quả tìm kiếm có thể thiếu hoặc không khớp dù nội dung gốc có vẻ giống nhau.

## 2. Analyzer gồm những thành phần nào?

Một analyzer thường bao gồm ba giai đoạn:

1. **Character filters**: xử lý chuỗi đầu vào trước khi tách từ, ví dụ loại bỏ hoặc thay thế một số ký tự.
2. **Tokenizer**: chia chuỗi thành các token theo quy tắc, ví dụ tách theo ranh giới từ.
3. **Token filters**: biến đổi token, ví dụ chuyển về chữ thường, loại stop words, stemming hoặc thêm synonyms.

Ví dụ, analyzer `standard` thường tách văn bản thành các token và chuyển chúng về chữ thường. Analyzer `english` có thể thực hiện thêm các xử lý ngôn ngữ tiếng Anh như loại stop words và stemming.

Cùng một analyzer có thể được dùng ở cả index time và search time. Nhưng khi ứng dụng có yêu cầu riêng cho truy vấn, ta có thể khai báo analyzer khác nhau cho hai thời điểm.

## 3. Index-time analysis

Index-time analysis diễn ra khi Elasticsearch nhận document để lập chỉ mục. Analyzer được khai báo bằng mapping parameter `analyzer` của field.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "english"
      }
    }
  }
}
~~~

Khi document được index:

~~~json
{
  "description": "The applications are running quickly"
}
~~~

Analyzer `english` xử lý nội dung theo các quy tắc tiếng Anh. Tùy cấu hình analyzer, các token có thể được chuyển chữ thường, loại stop words và đưa về dạng gốc thông qua stemming.

Index-time analysis có các đặc điểm:

- Xảy ra khi document được index hoặc được lập chỉ mục lại.
- Quyết định token được ghi vào inverted index.
- Thay đổi analyzer lập chỉ mục không tự động phân tích lại những document đã tồn tại.
- Có ảnh hưởng đến cách dữ liệu được tìm thấy trong các truy vấn về sau.

Vì vậy, chọn index analyzer là quyết định quan trọng khi thiết kế mapping. Nếu thay đổi quy tắc tách từ hoặc stemming sau khi đã có dữ liệu, thường cần tạo index mới và reindex dữ liệu.

## 4. Search-time analysis

Search-time analysis diễn ra khi Elasticsearch xử lý một truy vấn toàn văn. Mapping parameter `search_analyzer` cho phép khai báo analyzer dùng khi phân tích nội dung truy vấn.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "english",
        "search_analyzer": "standard"
      }
    }
  }
}
~~~

Trong ví dụ:

- `analyzer: english` dùng để phân tích nội dung khi index document.
- `search_analyzer: standard` dùng để phân tích văn bản truy vấn.

Khi người dùng tìm bằng `match`:

~~~json
{
  "query": {
    "match": {
      "description": "RUNNING applications"
    }
  }
}
~~~

Elasticsearch dùng search analyzer được cấu hình cho field để phân tích chuỗi truy vấn trước khi tìm token trong inverted index.

### Vì sao cần search analyzer riêng?

Có một số trường hợp ứng dụng muốn xử lý nội dung truy vấn khác với nội dung document:

- Mở rộng từ đồng nghĩa ở thời điểm tìm kiếm.
- Chuẩn hóa truy vấn theo quy tắc riêng.
- Giữ cách lập chỉ mục ổn định trong khi điều chỉnh trải nghiệm tìm kiếm.
- Áp dụng quy tắc phân tích khác nhau cho truy vấn thông thường và truy vấn cụm từ.

Search analyzer không viết lại token đã lưu trong inverted index. Nó chỉ quyết định cách văn bản truy vấn được chuyển thành token để so khớp với dữ liệu đã index.

## 5. Khi không khai báo search analyzer

Nếu field có khai báo `analyzer` nhưng không khai báo `search_analyzer`, analyzer lập chỉ mục thường cũng được dùng làm search analyzer cho field đó.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard"
      }
    }
  }
}
~~~

Trong trường hợp này, `standard` được dùng khi index và mặc định cả khi phân tích truy vấn.

Nếu không khai báo analyzer riêng, Elasticsearch dùng analyzer mặc định theo cấu hình của index, thường là `standard`.

Không nên cho rằng mọi field đều tự động có analyzer riêng. Với field `keyword`, Elasticsearch không tách chuỗi thành token như field `text`; nếu cần chuẩn hóa giá trị keyword, ta dùng normalizer.

## 6. Phân biệt `analyzer`, `search_analyzer` và `search_quote_analyzer`

Ba mapping parameter này có vai trò khác nhau:

| Parameter | Thời điểm sử dụng | Mục đích |
|---|---|---|
| `analyzer` | Index time | Phân tích nội dung field khi lập chỉ mục |
| `search_analyzer` | Search time | Phân tích văn bản truy vấn thông thường |
| `search_quote_analyzer` | Search time | Phân tích phần văn bản được đặt trong dấu ngoặc kép của `query_string` query |

`search_quote_analyzer` hữu ích khi muốn xử lý phần văn bản được đặt trong dấu ngoặc kép của `query_string` theo quy tắc riêng, chẳng hạn không mở rộng synonyms cho cụm từ đó. Nếu không khai báo, Elasticsearch mặc định dùng `search_analyzer`.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "analyzer": "content_index",
        "search_analyzer": "content_search",
        "search_quote_analyzer": "content_phrase_search"
      }
    }
  }
}
~~~

Các analyzer `content_index`, `content_search` và `content_phrase_search` phải được định nghĩa trong settings của index trước khi mapping tham chiếu đến chúng. `content_phrase_search` sẽ được dùng cho phần quoted text trong `query_string` theo mapping này.

Không phải mọi truy vấn đều dùng search analyzer theo cùng cách. `match` và `match_phrase` là các truy vấn toàn văn có phân tích đầu vào. Các truy vấn term-level như `term` so khớp term đã có và không phân tích chuỗi đầu vào như `match`.

## 7. Ví dụ: dùng analyzer riêng cho index và search

Giả sử ứng dụng tìm kiếm tên sản phẩm. Khi index, ta muốn chuẩn hóa chữ thường và stemming tiếng Anh. Khi search, ngoài các xử lý đó, ta muốn mở rộng một số từ đồng nghĩa như `tv` và `television`.

Có thể định nghĩa settings như sau:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        },
        "product_synonyms": {
          "type": "synonym_graph",
          "synonyms": [
            "tv, television",
            "laptop, notebook"
          ]
        }
      },
      "analyzer": {
        "product_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stemmer"
          ]
        },
        "product_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stemmer",
            "product_synonyms"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "product_index",
        "search_analyzer": "product_search"
      }
    }
  }
}
~~~

Trong ví dụ này:

- `product_index` dùng khi lưu tên sản phẩm.
- `product_search` dùng khi phân tích từ khóa người dùng nhập.
- `product_synonyms` là synonym graph filter được áp dụng ở search time.
- `name` vẫn là một field text; ứng dụng không cần tạo hai thuộc tính Java riêng.

Trong ví dụ, `english_stemmer` là filter tùy chỉnh được định nghĩa bằng loại `stemmer` với ngôn ngữ `english`. Có thể thay bằng token filter built-in phù hợp, nhưng tên và cấu hình phải đúng với phiên bản Elasticsearch đang chạy.

Synonym graph thường được dùng ở search time để xử lý cụm từ đồng nghĩa. Việc thay đổi danh sách synonyms ở search time có thể giúp điều chỉnh hành vi tìm kiếm mà không cần lập chỉ mục lại toàn bộ document, miễn là cấu hình index và cách cập nhật analyzer cho phép.

## 8. Kết quả khi index analyzer và search analyzer không tương thích

Giả sử index analyzer chuyển từ:

`running` → `run`

Nhưng search analyzer giữ nguyên:

`running` → `running`

Khi người dùng tìm `running`, truy vấn tạo term `running`, trong khi inverted index chỉ có term `run`. Hai term không khớp nên document có thể không xuất hiện.

Tình huống ngược lại cũng có thể xảy ra. Nếu search analyzer stemming thành `run`, nhưng index analyzer lưu `running`, truy vấn có thể không tìm được document.

Một số điểm cần nhớ:

- Hai analyzer không nhất thiết phải giống nhau hoàn toàn.
- Chúng phải tạo ra các token có khả năng so khớp theo ý đồ tìm kiếm.
- Các filter như lowercase, stemming, stop words và synonyms có thể làm thay đổi tập token.
- Trước khi thay đổi analyzer, hãy kiểm tra token thực tế bằng Analyze API.

## 9. Những loại query nào phân tích đầu vào?

Không phải mọi query đều phân tích văn bản đầu vào.

| Query | Phân tích đầu vào? | Mục đích |
|---|---|---|
| `match` | Có | Tìm kiếm toàn văn |
| `match_phrase` | Có | Tìm cụm từ theo thứ tự/vị trí |
| `multi_match` | Có | Tìm toàn văn trên nhiều field |
| `query_string` | Có, theo analyzer và cú pháp query | Truy vấn văn bản có cú pháp |
| `term` | Không như full-text query | So khớp một term đã lập chỉ mục |
| `terms` | Không như full-text query | So khớp một trong nhiều term |
| `prefix` | Không chạy analyzer toàn văn trên đầu vào | Tìm term bắt đầu bằng prefix |
| `wildcard` | Không chạy analyzer toàn văn trên đầu vào | Tìm term theo mẫu wildcard |

Ví dụ `match`:

~~~json
{
  "query": {
    "match": {
      "name": "Wireless Keyboard"
    }
  }
}
~~~

Đầu vào được phân tích theo search analyzer của field `name`.

Ví dụ `term`:

~~~json
{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

`term` không chuyển `PUBLISHED` qua analyzer toàn văn. Nó so khớp với term được lập chỉ mục. Vì vậy, khi dùng `term` trên field text đã lowercase, giá trị chữ hoa ban đầu có thể không khớp với token chữ thường trong index.

Đây là lý do field keyword thường được dùng cho status, mã, loại dữ liệu và các điều kiện lọc chính xác.

## 10. Kiểm tra analyzer bằng Analyze API

Không nên chỉ đọc cấu hình rồi suy đoán token được tạo ra. Elasticsearch cung cấp Analyze API để kiểm tra kết quả phân tích.

Kiểm tra analyzer index:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "analyzer": "product_index",
  "text": "TVs and wireless laptops"
}
~~~

Kiểm tra analyzer search:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "analyzer": "product_search",
  "text": "TVs and wireless laptops"
}
~~~

Kết quả trả về chứa danh sách token và thông tin như vị trí, offset. So sánh hai kết quả giúp phát hiện:

- Analyzer có chuyển chữ thường đúng không?
- Stop words có bị loại bỏ không?
- Stemming có tạo ra dạng từ mong muốn không?
- Synonyms có mở rộng đúng không?
- Token position có phù hợp với truy vấn phrase không?

Có thể kiểm tra analyzer đang áp dụng cho một field bằng cách dùng tên field:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Cách kiểm tra theo field hữu ích vì Elasticsearch sử dụng cấu hình analyzer gắn với mapping field đó.

## 11. Khai báo trong Spring Data Elasticsearch

Spring Data Elasticsearch cho phép khai báo analyzer và search analyzer bằng annotation `@Field`.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "product_index",
        searchAnalyzer = "product_search"
    )
    private String name;

    // Constructors, getters and setters
}
~~~

Trong ví dụ:

- `type = FieldType.Text` xác định đây là field văn bản toàn văn.
- `analyzer = "product_index"` chọn analyzer dùng khi index.
- `searchAnalyzer = "product_search"` chọn analyzer dùng khi tìm kiếm.

Tên analyzer trong annotation phải khớp với analyzer được định nghĩa trong index settings. Annotation chỉ mô tả mapping field; nó không tự tạo các định nghĩa custom analyzer nếu settings chưa được cấu hình.

Một cách tổ chức là quản lý settings bằng file JSON/YAML hoặc bằng quy trình tạo index trong ứng dụng. Khi dùng annotation `@Setting` hoặc `IndexOperations`, cần bảo đảm index settings được áp dụng trước mapping và trước khi ghi document.

Ví dụ tạo index bằng Spring Data:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

Đoạn code minh họa việc tạo index với mapping suy ra từ metadata entity. Nếu analyzer tùy chỉnh cần settings riêng, phải bảo đảm settings đó được đưa vào quy trình tạo index trước khi mapping tham chiếu analyzer.

## 12. Thay đổi analyzer có cần reindex không?

Cần phân biệt thay đổi index analyzer và search analyzer.

### Thay đổi index analyzer

Index analyzer quyết định token được lưu vào inverted index. Khi thay đổi analyzer, các token cũ không tự động được tạo lại.

Ví dụ, trước đây `running` được lưu thành `running`; sau đó analyzer mới chuyển thành `run`. Nếu chỉ sửa mapping, các document cũ vẫn giữ token cũ.

Để dữ liệu nhất quán, thông thường cần:

1. Tạo index mới với settings và mapping mới.
2. Reindex document từ index cũ sang index mới.
3. Kiểm tra kết quả tìm kiếm và dữ liệu.
4. Chuyển alias hoặc ứng dụng sang index mới theo kế hoạch triển khai.

### Thay đổi search analyzer

Search analyzer chỉ xử lý văn bản truy vấn, không thay đổi token đã lưu trong inverted index. Vì vậy, thay đổi quy tắc search-time có thể không cần reindex dữ liệu.

Tuy nhiên, việc cập nhật mapping hoặc analyzer settings vẫn tuân theo giới hạn của Elasticsearch và phiên bản đang sử dụng. Một số thay đổi settings cần đóng index trước khi cập nhật; các analyzer/filter tham chiếu cũng phải tồn tại trong settings. Hãy kiểm tra khả năng cập nhật của từng mapping parameter trước khi triển khai.

### Thay đổi synonyms

Nếu synonyms chỉ được áp dụng trong search analyzer, việc cập nhật synonyms thường có thể thực hiện mà không phải lập chỉ mục lại document. Đây là một ưu điểm của việc xử lý synonyms tại search time.

Nếu synonyms được áp dụng ở index time, thay đổi quy tắc synonyms sẽ không tự sửa các token cũ; cần lập chỉ mục lại để dữ liệu phản ánh quy tắc mới.

## 13. Các lỗi thường gặp

### Dùng search analyzer tạo token không có trong index

Ví dụ index analyzer stemming nhưng search analyzer không stemming, khiến `running` và `run` không khớp. Hãy kiểm tra token ở cả hai phía bằng Analyze API.

### Cho rằng sửa mapping sẽ phân tích lại document cũ

Mapping mới chỉ ảnh hưởng đến các document được index sau khi mapping có hiệu lực hoặc document được lập chỉ mục lại. Document cũ không tự thay đổi token.

### Dùng term query và kỳ vọng analyzer chạy

`term` không hoạt động như `match`. Nếu cần tìm kiếm toàn văn, hãy chọn query phù hợp.

### Đặt synonyms ở index time khi muốn thay đổi thường xuyên

Synonyms index-time gắn với token đã lưu. Nếu danh sách synonyms thay đổi thường xuyên, cân nhắc xử lý tại search time.

### Quên cấu hình custom analyzer trong index settings

Mapping tham chiếu tên analyzer chưa tồn tại sẽ không tạo được cấu hình hợp lệ. Hãy tạo settings trước mapping.

### Chỉ kiểm tra kết quả truy vấn, không kiểm tra token

Khi kết quả tìm kiếm sai, nguyên nhân có thể nằm ở tokenizer, token filter hoặc search analyzer. Analyze API giúp xác định vấn đề trực tiếp hơn.

## 14. Quy trình thiết kế và vận hành

Khi cấu hình phân tích văn bản cho một field:

1. Xác định ngôn ngữ và dạng dữ liệu của nội dung.
2. Chọn index analyzer để tạo token phù hợp cho dữ liệu lưu trữ.
3. Chọn search analyzer sao cho token truy vấn tương thích với token trong index.
4. Chỉ tách riêng search analyzer khi có lý do như synonyms hoặc quy tắc chuẩn hóa truy vấn.
5. Xác định có cần search quote analyzer cho phrase query hay không.
6. Kiểm tra kết quả bằng Analyze API trước khi index dữ liệu lớn.
7. Dùng `match` hoặc query full-text tương ứng khi cần phân tích đầu vào; dùng `term` cho so khớp term chính xác.
8. Khi thay đổi index analyzer, lập kế hoạch reindex.
9. Khi thay đổi search analyzer, kiểm tra mapping/settings và thử nghiệm truy vấn thực tế.
10. Ghi lại cấu hình analyzer cùng phiên bản index để có thể tái tạo và vận hành nhất quán.

## Kết luận

Index-time analysis quyết định token được lưu trong inverted index; search-time analysis quyết định token được tạo từ văn bản truy vấn. Hai analyzer có thể khác nhau, nhưng phải tạo ra các token tương thích với mục tiêu tìm kiếm. Trong Spring Data Elasticsearch, có thể khai báo chúng bằng `analyzer` và `searchAnalyzer` trên `@Field`. Hãy kiểm tra token bằng Analyze API, dùng đúng loại query và nhớ rằng thay đổi analyzer lúc lập chỉ mục thường cần reindex dữ liệu cũ.
