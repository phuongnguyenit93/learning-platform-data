# Tạo analyzer từ character filter, tokenizer và token filter

Elasticsearch tìm kiếm văn bản dựa trên các token được tạo ra khi lập chỉ mục và khi xử lý truy vấn. **Analyzer** là thành phần quyết định cách một chuỗi văn bản được chuẩn hóa và tách thành token. Trong Spring Data Elasticsearch, analyzer được khai báo trong mapping của field và được Elasticsearch thực thi khi ứng dụng ghi hoặc tìm kiếm document.

Một custom analyzer thường gồm ba nhóm thành phần theo đúng thứ tự xử lý:

1. **Character filter**: chỉnh sửa chuỗi ký tự đầu vào trước khi tách từ, ví dụ loại bỏ HTML hoặc thay thế ký tự.
2. **Tokenizer**: chia chuỗi đã xử lý thành các token theo quy tắc ranh giới, ví dụ theo từ hoặc theo khoảng trắng.
3. **Token filter**: biến đổi, loại bỏ hoặc mở rộng token, ví dụ chuyển chữ thường, bỏ stop word, stemming hoặc áp dụng synonym.

Việc chọn và sắp xếp các thành phần này quyết định những từ nào có thể khớp với truy vấn. Một analyzer phù hợp giúp kết quả tìm kiếm gần với ngôn ngữ người dùng, đồng thời giữ khả năng lọc chính xác trên các field mã định danh.

## 1. Analyzer xử lý văn bản như thế nào?

Khi Elasticsearch lập chỉ mục một field kiểu `text`, analyzer của field sẽ biến giá trị thành chuỗi token. Khi chạy truy vấn như `match`, search analyzer tiếp tục xử lý văn bản người dùng nhập để tạo token truy vấn. Nếu hai phía chuẩn hóa tương thích, token có thể khớp nhau.

Sơ đồ pipeline:

~~~mermaid
flowchart TD
    A["Chuỗi đầu vào"] --> B["Character filters"]
    B --> C["Tokenizer"]
    C --> D["Token filters"]
    D --> E["Danh sách token"]
    E --> F["Elasticsearch lập chỉ mục hoặc tạo query terms"]
~~~

Ví dụ, văn bản đầu vào có thể chứa HTML, chữ hoa, dấu tiếng Việt hoặc ký tự đặc biệt:

~~~text
<b>Cà Phê</b> & Accessories
~~~

Một analyzer có thể:

- Bỏ các thẻ HTML như `<b>`.
- Chuẩn hóa dấu hoặc ký tự theo chính sách tìm kiếm.
- Tách văn bản thành các từ.
- Chuyển token về chữ thường.
- Loại bỏ từ không có nhiều giá trị tìm kiếm (stop words) nếu phù hợp.

Kết quả là một dãy token được Elasticsearch dùng để lập chỉ mục. `_source` vẫn giữ nội dung JSON gốc của document; analyzer không ghi đè chuỗi ban đầu trong `_source`.

## 2. Character filter — xử lý ký tự trước khi tách từ

Character filter nhận toàn bộ chuỗi đầu vào và trả về chuỗi đã biến đổi cho tokenizer. Có thể kết hợp nhiều character filter; chúng chạy theo thứ tự khai báo.

Các character filter thường dùng:

| Character filter | Công dụng |
| --- | --- |
| `html_strip` | Loại bỏ HTML tag và xử lý HTML entity. Hữu ích khi dữ liệu mô tả có markup. |
| `mapping` | Thay thế chuỗi hoặc ký tự cụ thể theo các cặp mapping. |
| `pattern_replace` | Thay thế phần khớp regular expression bằng chuỗi khác. |

### 2.1. `html_strip`

`html_strip` loại bỏ tag HTML trước khi tokenizer xử lý văn bản. Ví dụ đầu vào:

~~~html
<p>Wireless <strong>Keyboard</strong></p>
~~~

Sau khi loại bỏ tag, tokenizer nhận được phần văn bản `Wireless Keyboard`. HTML entity như `&amp;` cũng được xử lý theo quy tắc HTML.

Điều này hữu ích khi nội dung được lấy từ CMS, mô tả sản phẩm hoặc bài viết có định dạng HTML. Nếu dữ liệu đầu vào đã là plain text, không cần thêm filter này.

### 2.2. `mapping`

`mapping` thay thế ký tự hoặc chuỗi được khai báo trước khi tokenizer chạy. Ví dụ, có thể chuẩn hóa dấu `&` thành từ `and` để hai cách viết có thể tạo ra token tương thích:

~~~json
{
  "type": "mapping",
  "mappings": [
    "& => and",
    "+ => plus"
  ]
}
~~~

Các mapping được áp dụng theo danh sách. Chọn quy tắc cẩn thận vì việc thay thế có thể làm thay đổi ý nghĩa dữ liệu hoặc tạo ra token mới. Nếu mapping thay một ký tự bằng nhiều ký tự, tokenizer sẽ nhìn thấy chuỗi sau thay thế.

### 2.3. `pattern_replace`

`pattern_replace` sử dụng regular expression để thay thế một mẫu ký tự. Ví dụ, chuẩn hóa nhiều dấu gạch nối liên tiếp thành một dấu cách:

~~~json
{
  "type": "pattern_replace",
  "pattern": "[-_]+",
  "replacement": " "
}
~~~

Với đầu vào `wireless__keyboard-pro`, chuỗi sau character filter trở thành `wireless keyboard pro`. Quy tắc này hữu ích khi dữ liệu đến từ nhiều nguồn có cách đặt dấu phân cách không thống nhất.

Regular expression cần được kiểm tra với dữ liệu thực tế. Pattern quá rộng có thể xóa ký tự có ý nghĩa, và pattern phức tạp có thể tăng chi phí xử lý.

## 3. Tokenizer — chia văn bản thành token

Tokenizer nhận chuỗi sau character filters và xác định ranh giới token. Mỗi analyzer có một tokenizer. Việc chọn tokenizer phụ thuộc loại dữ liệu và cách người dùng tìm kiếm.

| Tokenizer | Cách chia | Trường hợp thường gặp |
| --- | --- | --- |
| `standard` | Chia theo quy tắc phân đoạn từ Unicode và xử lý dấu câu phổ biến. | Văn bản tự nhiên, mô tả, tiêu đề. |
| `whitespace` | Chia tại khoảng trắng; dấu câu vẫn có thể nằm trong token. | Dữ liệu đã được chuẩn hóa theo khoảng trắng. |
| `keyword` | Giữ toàn bộ chuỗi thành một token. | Khi cần xử lý nguyên giá trị như một đơn vị; thường dùng với keyword field hoặc normalizer. |
| `letter` | Chia tại các ký tự không phải chữ cái. | Văn bản mà ranh giới từ chủ yếu được xác định bằng chữ cái. |
| `pattern` | Chia theo regular expression. | Dữ liệu có định dạng phân cách đặc thù. |
| `ngram` | Tạo các chuỗi con có độ dài nằm trong khoảng cấu hình. | Tìm kiếm gần đúng hoặc autocomplete theo substring. |
| `edge_ngram` | Tạo các tiền tố của token. | Autocomplete theo phần đầu của từ. |

### 3.1. `standard`

`standard` là lựa chọn phù hợp cho nhiều loại văn bản tự nhiên. Nó nhận diện ranh giới từ dựa trên quy tắc Unicode và xử lý nhiều loại dấu câu.

Ví dụ với `Wireless Keyboard, Model X100` tokenizer standard tạo các token theo ranh giới từ; các token filter phía sau sẽ tiếp tục chuẩn hóa chúng.

### 3.2. `keyword`

`keyword` tokenizer giữ toàn bộ đầu vào thành một token. Nếu chuỗi là `SKU-AB_123`, tokenizer không tách thành `SKU`, `AB` và `123`.

Điều này khác với mapping field type `keyword` ở Elasticsearch:

- Tokenizer `keyword` là một thành phần của analyzer.
- Field type `keyword` là kiểu mapping thường dùng cho giá trị cần so khớp chính xác.

Một `keyword` field có thể dùng normalizer để chuyển chữ thường hoặc bỏ dấu mà vẫn giữ một token duy nhất. Không cần tạo analyzer custom với tokenizer `keyword` chỉ để lập chỉ mục mã định danh; hãy chọn field type phù hợp với mục đích truy vấn.

### 3.3. `ngram` và `edge_ngram`

`ngram` tạo nhiều chuỗi con liên tiếp trong mỗi token. `edge_ngram` chỉ tạo các chuỗi bắt đầu từ đầu token.

Ví dụ token `phone` với `edge_ngram` có `min_gram: 2` và `max_gram: 5` có thể tạo các tiền tố như `ph`, `pho`, `phon`, `phone`. Người dùng nhập `pho` có thể tìm được document chứa `phone`.

Các tokenizer này làm tăng số lượng token và dung lượng index. Nên dùng chúng cho trường hợp tìm kiếm autocomplete cụ thể, thường kết hợp analyzer riêng cho index và search analyzer đơn giản hơn. Không nên áp dụng ngram cho mọi field văn bản.

## 4. Token filter — biến đổi token sau khi tách

Tokenizer tạo token ban đầu. Token filter tiếp tục chuẩn hóa, loại bỏ hoặc mở rộng các token đó. Có thể dùng nhiều filter; thứ tự khai báo ảnh hưởng trực tiếp tới kết quả.

Các token filter phổ biến:

| Token filter | Tác dụng |
| --- | --- |
| `lowercase` | Chuyển token thành chữ thường. |
| `uppercase` | Chuyển token thành chữ hoa. |
| `asciifolding` | Chuyển nhiều ký tự có dấu thành dạng ASCII tương ứng, ví dụ `café` thành `cafe`. |
| `stop` | Loại bỏ các từ dừng theo danh sách cấu hình. |
| `stemmer` | Đưa từ về dạng gốc gần đúng theo ngôn ngữ, ví dụ biến thể số nhiều hoặc thì động từ. |
| `synonym_graph` | Mở rộng hoặc thay thế từ đồng nghĩa, hỗ trợ cụm từ nhiều token trong search query. |
| `word_delimiter_graph` | Tách hoặc kết hợp các phần của từ ghép, mã và chuỗi có dấu phân cách. |
| `ngram` / `edge_ngram` | Tạo token con hoặc tiền tố từ token hiện có. |

### 4.1. `lowercase`

`lowercase` chuẩn hóa chữ hoa và chữ thường để truy vấn không phụ thuộc cách viết hoa. Ví dụ `Wireless`, `WIRELESS` và `wireless` đều được chuẩn hóa về `wireless`.

Đây là filter thường xuất hiện trong analyzer cho văn bản tự nhiên. Nếu cần giữ nguyên cách viết hoa để hiển thị, `_source` vẫn giữ giá trị ban đầu; token đã chuẩn hóa chỉ phục vụ tìm kiếm.

### 4.2. `asciifolding`

`asciifolding` chuyển nhiều ký tự có dấu sang ký tự ASCII gần tương ứng. Ví dụ `café` thành `cafe`, `résumé` thành `resume`.

Điều này giúp người dùng có thể tìm nội dung có dấu bằng truy vấn không dấu trong một số ngôn ngữ. Tuy nhiên, bỏ dấu có thể làm mất khác biệt giữa các từ; cần quyết định theo ngôn ngữ và yêu cầu nghiệp vụ. Với tiếng Việt, hãy thử trên dữ liệu thực tế để đánh giá việc chuẩn hóa dấu thanh và chữ cái đặc biệt trước khi áp dụng rộng rãi.

### 4.3. `stop`

Stop filter loại bỏ các từ xuất hiện rất thường xuyên và ít đóng góp vào khả năng phân biệt kết quả. Có thể dùng bộ từ dừng tích hợp, ví dụ `_english_`, hoặc cung cấp danh sách riêng.

Ví dụ cấu hình:

~~~json
{
  "type": "stop",
  "stopwords": ["the", "a", "an", "and", "or"]
}
~~~

Không nên mặc định dùng danh sách tiếng Anh cho nội dung tiếng Việt. Việc loại bỏ từ dừng có thể ảnh hưởng ý nghĩa truy vấn, đặc biệt với cụm từ ngắn hoặc từ phủ định. Cần lựa chọn danh sách theo ngôn ngữ của dữ liệu.

### 4.4. `stemmer`

Stemming đưa các biến thể của từ về một dạng gốc gần đúng để truy vấn có thể khớp nhiều dạng ngữ pháp. Ví dụ tiếng Anh, `connect`, `connected` và `connecting` có thể được đưa về dạng gốc tương ứng theo thuật toán stemmer.

Elasticsearch cung cấp stemmer theo ngôn ngữ. Ví dụ filter `stemmer` có thể đặt `language: "english"`. Không dùng stemmer tiếng Anh cho tiếng Việt; nếu cần xử lý hình thái tiếng Việt, phải chọn công cụ hoặc analyzer phù hợp với ngôn ngữ đó.

### 4.5. `synonym_graph`

`synonym_graph` hỗ trợ đồng nghĩa, kể cả các cụm từ nhiều token. Ví dụ có thể khai báo `tv` và `television` là từ tương đương để người dùng tìm theo một cách viết vẫn nhận được tài liệu có cách viết còn lại.

Với tìm kiếm cụm từ, `synonym_graph` thường được dùng trong search analyzer để tạo token graph chính xác. Nên kiểm tra kỹ quy tắc synonym, thứ tự token filter và hành vi phrase query bằng `_analyze` cùng các truy vấn thực tế.

## 5. Kết hợp các thành phần thành custom analyzer

Một custom analyzer được khai báo trong `settings.analysis.analyzer`. Mỗi analyzer chỉ định các character filter, một tokenizer và danh sách token filter.

Ví dụ tạo analyzer cho tên sản phẩm có thể chứa HTML, dấu tiếng Anh và các dấu phân cách phổ biến:

~~~json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "html_cleaner": {
          "type": "html_strip"
        },
        "symbol_mapping": {
          "type": "mapping",
          "mappings": [
            "& => and",
            "+ => plus"
          ]
        }
      },
      "filter": {
        "english_stop": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "char_filter": [
            "html_cleaner",
            "symbol_mapping"
          ],
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding",
            "english_stop",
            "english_stemmer"
          ]
        }
      },
      "normalizer": {
        "catalog_keyword": {
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
      "name": {
        "type": "text",
        "analyzer": "catalog_text",
        "search_analyzer": "catalog_text",
        "fields": {
          "raw": {
            "type": "keyword",
            "normalizer": "catalog_keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

Trong cấu hình này:

- `html_cleaner` loại bỏ HTML trước khi tokenizer chạy.
- `symbol_mapping` chuẩn hóa `&` và `+` theo các từ tương ứng.
- `standard` chia chuỗi thành các token.
- `lowercase` và `asciifolding` chuẩn hóa chữ hoa và dấu.
- `english_stop` loại bỏ stop words tiếng Anh.
- `english_stemmer` xử lý biến thể từ tiếng Anh.
- `catalog_keyword` là normalizer cho subfield `name.raw`; nó giữ giá trị thành một token nhưng chuyển chữ thường và bỏ dấu.

Ví dụ tên sản phẩm `Café <b>Accessories</b> & Tools` sẽ được làm sạch HTML, chuẩn hóa dấu `&`, tách thành token rồi chuyển về dạng chuẩn hóa. Token cuối cùng phụ thuộc từng filter và bộ từ dừng đã cấu hình.

Field `name` dùng analyzer `catalog_text` cho tìm kiếm toàn văn. Subfield `name.raw` dùng kiểu `keyword` để so khớp chính xác, sắp xếp hoặc aggregation trên giá trị đã qua normalizer. Hai field phục vụ hai kiểu truy vấn khác nhau.

## 6. Kiểm tra analyzer bằng `_analyze` API

Không nên chỉ nhìn cấu hình rồi giả định analyzer tạo ra token mong muốn. Elasticsearch cung cấp `_analyze` API để quan sát kết quả thực tế.

Khi index đã được tạo, gửi request:

~~~http
POST /catalog/_analyze
Content-Type: application/json

{
  "analyzer": "catalog_text",
  "text": "Café <b>Accessories</b> & Tools",
  "explain": true
}
~~~

Kết quả có danh sách token và thông tin như `token`, `start_offset`, `end_offset`, `type`, `position`. Với `explain: true`, Elasticsearch có thể cung cấp thêm thông tin về các giai đoạn xử lý để xem tác động của character filter, tokenizer và token filter.

Có thể kiểm tra riêng một tokenizer hoặc token filter bằng cách truyền cấu hình trực tiếp vào `_analyze`, hoặc gọi analyzer đã khai báo trong index. Khi debug, nên thay đổi từng thành phần một để xác định filter nào làm mất hoặc biến đổi token không mong muốn.

Kiểm tra analyzer của một field cụ thể cũng có thể thực hiện bằng `field` thay cho `analyzer` trong request `_analyze`. Cách này giúp kiểm tra analyzer được mapping gắn cho field.

## 7. Gắn analyzer vào field mapping

Định nghĩa analyzer trong index settings chưa đủ. Field cần tham chiếu analyzer trong mapping:

~~~json
{
  "properties": {
    "description": {
      "type": "text",
      "analyzer": "catalog_text",
      "search_analyzer": "catalog_text"
    },
    "sku": {
      "type": "keyword"
    }
  }
}
~~~

`analyzer` là analyzer dùng khi lập chỉ mục giá trị field. `search_analyzer` là analyzer dùng để xử lý văn bản truy vấn. Nếu không khai báo `search_analyzer`, Elasticsearch thường dùng analyzer của field cho search theo mặc định.

Có thể dùng hai analyzer khác nhau cho index và search. Ví dụ autocomplete có thể dùng `edge_ngram` khi lập chỉ mục nhưng dùng `standard` khi phân tích truy vấn. Điều này tránh việc truy vấn người dùng cũng bị mở rộng thành nhiều tiền tố không cần thiết.

Analyzer custom phải tồn tại trong index settings trước khi mapping tham chiếu đến nó. Analyzer không phải một thiết lập có thể gắn tùy ý vào field sau khi dữ liệu đã được lập chỉ mục.

## 8. Sử dụng analyzer trong Spring Data Elasticsearch

Spring Data Elasticsearch cho phép khai báo mapping bằng annotation. `@Field` có các thuộc tính `analyzer` và `searchAnalyzer` để tham chiếu tên analyzer đã định nghĩa trong index settings.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog")
public class Product {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "catalog_text",
        searchAnalyzer = "catalog_text"
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    // Constructor, getters và setters
}
~~~

Các annotation này mô tả mapping field. Phần định nghĩa `catalog_text` phải được cung cấp trong settings của index. Có thể quản lý settings bằng file JSON trên classpath và dùng annotation `@Setting` ở entity:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "catalog")
@Setting(settingPath = "/elasticsearch/catalog-settings.json")
public class Product {
    // Fields và mapping annotations
}
~~~

Đặt file settings tại `src/main/resources/elasticsearch/catalog-settings.json` theo định dạng settings mà phiên bản Spring Data Elasticsearch của dự án hỗ trợ. `@Setting` giúp Spring Data sử dụng cấu hình index khi tạo index từ metadata entity.

Nếu index được tạo và quản lý riêng bằng migration hoặc REST API, hãy đảm bảo settings được cài đặt trước khi Spring Data ghi document. Annotation `@Field` không tự sửa analyzer của một index đã tồn tại.

## 9. Index analyzer và search analyzer

Analyzer khi index và analyzer khi search cần tương thích về cách chuẩn hóa token. Nếu index chuyển tất cả token về chữ thường nhưng search giữ nguyên chữ hoa, truy vấn có thể không khớp như mong đợi.

Có thể khai báo hai analyzer riêng:

- **Index analyzer:** tối ưu token được lưu trong inverted index. Có thể dùng stemming hoặc edge n-gram tùy yêu cầu.
- **Search analyzer:** chuẩn hóa truy vấn theo cách tương thích với token đã lập chỉ mục; thường tránh tạo quá nhiều token phụ.

Ví dụ với autocomplete, index analyzer dùng `edge_ngram` để tạo tiền tố, còn search analyzer chỉ dùng `standard` và `lowercase`. Khi người dùng nhập `key`, query tạo token `key`, có thể khớp với tiền tố đã lập chỉ mục của `keyboard`.

Không nên thêm stemming, synonym hoặc stop filter một cách tùy tiện vào cả hai phía. Hãy kiểm tra token ở hai pipeline và xác nhận các query thực tế vẫn cho kết quả đúng.

## 10. Synonym và thứ tự token filter

Khi cần hỗ trợ từ đồng nghĩa, có thể tạo filter `synonym_graph` và gắn nó vào search analyzer. Ví dụ cấu hình trong `analysis.filter`:

~~~json
{
  "catalog_synonyms": {
    "type": "synonym_graph",
    "synonyms": [
      "tv, television",
      "laptop, notebook"
    ]
  }
}
~~~

Analyzer tìm kiếm có thể tham chiếu filter này sau các bước chuẩn hóa chữ hoa/chữ thường:

~~~json
{
  "type": "custom",
  "char_filter": ["html_cleaner"],
  "tokenizer": "standard",
  "filter": [
    "lowercase",
    "asciifolding",
    "catalog_synonyms"
  ]
}
~~~

Vị trí synonym filter có ý nghĩa vì các filter trước đó ảnh hưởng cách synonym được phân tích. Nếu dùng stop filter hoặc stemmer, cần kiểm tra quy tắc synonym được xử lý ra sao. Với synonym nhiều từ, `synonym_graph` phù hợp hơn filter synonym đơn giản để giữ quan hệ vị trí token cho phrase query.

Quản lý synonym trong cấu hình tĩnh yêu cầu tạo hoặc cập nhật index settings theo quy trình phù hợp. Nếu dùng synonym file hoặc API reload search analyzers, cần tuân theo giới hạn và cơ chế reload của phiên bản Elasticsearch đang triển khai.

## 11. Lưu ý với ngôn ngữ tiếng Việt

Các ví dụ `english_stop` và `english_stemmer` chỉ phù hợp cho văn bản tiếng Anh. Không nên dùng nguyên xi cho field chứa tiếng Việt.

Với tiếng Việt, cần xác định rõ yêu cầu tìm kiếm:

- Có cần người dùng tìm không dấu và vẫn khớp văn bản có dấu không?
- Có cần xử lý từ ghép hoặc ranh giới âm tiết không?
- Có cần loại bỏ từ dừng không, và danh sách từ dừng nào phản ánh đúng nghiệp vụ?
- Có cần bộ tách từ tiếng Việt chuyên dụng không?

`standard` tokenizer nhận diện ranh giới theo quy tắc Unicode nhưng không phải bộ phân đoạn từ tiếng Việt theo ngữ nghĩa. `asciifolding` cũng không đảm bảo mọi khác biệt chính tả tiếng Việt được chuẩn hóa đúng theo nhu cầu sản phẩm. Hãy thử analyzer trên tập câu đại diện, bao gồm từ có dấu, không dấu, tên riêng, mã sản phẩm và từ ghép.

Khi cần bộ phân đoạn từ chuyên biệt, có thể cân nhắc plugin analysis phù hợp với phiên bản Elasticsearch hoặc xử lý văn bản trước khi gửi index. Plugin phải được cài trên mọi node phù hợp trong cluster và tương thích chính xác với phiên bản server.

## 12. Thay đổi analyzer sau khi index đã tồn tại

Analyzer và tokenizer được sử dụng khi lập chỉ mục ảnh hưởng tới inverted index. Nếu muốn thay đổi cách phân tích của field đã có dữ liệu, chỉ sửa annotation hoặc settings trong file ứng dụng không làm token cũ tự được tạo lại.

Thông thường cần tạo index mới với settings/mapping mong muốn, sau đó reindex document từ index cũ sang index mới. Có thể chuyển alias đọc/ghi sang index mới sau khi xác nhận dữ liệu và mapping.

Một số search analyzer có thể được reload nếu được cấu hình với filter hỗ trợ reloadable synonyms và Elasticsearch hỗ trợ thao tác đó. Khả năng reload không áp dụng cho mọi tokenizer, character filter hoặc analyzer; thay đổi index analyzer thường cần reindex để tạo lại token.

Quy trình thay đổi an toàn:

1. Ghi lại analyzer và mapping hiện tại.
2. Tạo index mới với settings và mapping mới.
3. Chạy `_analyze` với tập dữ liệu đại diện để xác nhận token.
4. Reindex document sang index mới.
5. Chạy các truy vấn thực tế để so sánh kết quả.
6. Chuyển alias hoặc cấu hình ứng dụng sang index mới.
7. Chỉ xóa index cũ sau khi xác nhận không còn consumer cần nó và đã có phương án khôi phục.

## 13. Lỗi thường gặp khi tạo custom analyzer

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Index creation báo analyzer hoặc filter không tồn tại | Tên component trong analyzer không khớp tên khai báo hoặc settings không được gửi cùng lúc tạo index. | Kiểm tra `analysis.char_filter`, `analysis.filter`, `analysis.tokenizer` và `analysis.analyzer`. |
| Field không tìm được analyzer | Mapping tham chiếu tên analyzer sai hoặc analyzer chưa được định nghĩa trong index settings. | Định nghĩa analyzer trước rồi tạo mapping. |
| Query không khớp dù văn bản có vẻ giống nhau | Index analyzer và search analyzer tạo token khác nhau, hoặc filter đã loại bỏ token. | Dùng `_analyze` kiểm tra cả hai pipeline. |
| Từ tiếng Việt bị xử lý không phù hợp | Dùng stop words/stemmer tiếng Anh hoặc giả định standard tokenizer phân đoạn từ theo tiếng Việt. | Xây dựng analyzer theo ngôn ngữ và kiểm tra trên dữ liệu thật. |
| Mapping update không thay đổi kết quả cũ | Token trong inverted index chưa được tạo lại. | Tạo index mới và reindex dữ liệu. |
| `dynamic: strict` từ chối document có field mới | Analyzer/type hint hoặc field khác được gửi nhưng không có trong mapping. | Khai báo field cần thiết hoặc điều chỉnh dynamic policy có chủ đích. |

## 14. Quy trình thiết kế analyzer

Khi tạo analyzer cho một field, hãy đi theo thứ tự:

1. Thu thập các ví dụ dữ liệu thực tế, bao gồm dấu câu, HTML, chữ hoa/thường, dấu và lỗi định dạng có thể xuất hiện.
2. Xác định hành vi chuẩn hóa mong muốn trước khi tách từ; chọn character filter phù hợp.
3. Chọn tokenizer theo cấu trúc dữ liệu và loại tìm kiếm.
4. Chọn token filter theo ngôn ngữ và mục tiêu tìm kiếm; sắp xếp đúng thứ tự.
5. Tạo custom analyzer trong index settings và gắn vào field mapping.
6. Dùng `_analyze` quan sát token và giải thích từng bước.
7. Kiểm tra cả analyzer khi index và search analyzer.
8. Thử truy vấn thực tế, đánh giá độ chính xác và chi phí tăng dung lượng index.
9. Khi cần thay đổi analyzer ảnh hưởng token đã lưu, tạo index mới và reindex.

Custom analyzer là pipeline có thứ tự: character filter sửa chuỗi, tokenizer xác định ranh giới token, token filter chuẩn hóa hoặc biến đổi token. Trong Spring Data Elasticsearch, `@Field` tham chiếu analyzer của field còn `@Setting` có thể cung cấp index settings khi tạo index. Kiểm tra token bằng `_analyze` trước khi đưa analyzer vào dữ liệu quan trọng giúp phát hiện sớm các khác biệt giữa cách lập chỉ mục và cách người dùng tìm kiếm.
