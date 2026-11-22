# Analyzer, tokenizer, token filter và normalizer

## 1. Vì sao Elasticsearch cần phân tích văn bản?

Khi người dùng nhập một cụm từ để tìm kiếm, Elasticsearch cần biến văn bản thành dạng có thể lập chỉ mục và so khớp hiệu quả. Quá trình đó gọi là **analysis** (phân tích văn bản). Nó thường tách câu thành các token, chuẩn hóa chữ hoa và chữ thường, xử lý dấu câu, loại bỏ từ không cần thiết hoặc chuyển từ về dạng gốc.

Ví dụ, một tài liệu có tiêu đề:

~~~text
The Quick Brown Foxes!
~~~

Có thể được phân tích thành các token:

~~~text
quick
brown
fox
~~~

Đây chỉ là ví dụ minh họa cho một cấu hình có xử lý chữ thường và stemming. Kết quả thực tế phụ thuộc analyzer, tokenizer và token filter được cấu hình.

Nếu không phân tích văn bản, tìm kiếm thường phải so khớp cả chuỗi hoặc xử lý thủ công nhiều biến thể. Analysis giúp Elasticsearch tìm được nội dung phù hợp ngay cả khi cách viết trong tài liệu và truy vấn khác nhau ở chữ hoa, dấu câu hoặc dạng từ.

Trong Elasticsearch, analysis được dùng chủ yếu với trường kiểu `text`. Trường `keyword` thường lưu toàn bộ giá trị như một đơn vị để lọc, sắp xếp hoặc gom nhóm; trường này có thể dùng **normalizer** để chuẩn hóa giá trị mà vẫn giữ nó thành một token duy nhất.

## 2. Chuỗi phân tích gồm những thành phần nào?

Một analyzer hoàn chỉnh có thể gồm ba bước theo thứ tự:

~~~text
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
Danh sách token đầu ra
~~~

- **Character filter** xử lý văn bản trước khi tách token, chẳng hạn loại bỏ thẻ HTML hoặc thay thế một chuỗi ký tự.
- **Tokenizer** chia văn bản thành các token theo quy tắc nhất định.
- **Token filter** nhận danh sách token và biến đổi, loại bỏ hoặc bổ sung token.

Một analyzer có thể có không, một hoặc nhiều character filter; nó có đúng một tokenizer và có thể có nhiều token filter. Thứ tự các bộ lọc rất quan trọng vì mỗi bước nhận kết quả từ bước trước.

Ví dụ, với nội dung `"<p>CAFÉ Shoes</p>"`, một analyzer có thể loại thẻ HTML, tách thành token, chuyển chữ thường và chuyển ký tự có dấu về dạng ASCII. Kết quả có thể là `cafe` và `shoes`.

## 3. Character filter: xử lý ký tự trước khi tách từ

Character filter nhận toàn bộ chuỗi đầu vào và biến đổi chuỗi trước khi tokenizer hoạt động. Elasticsearch cung cấp một số loại thường dùng:

| Character filter | Công dụng | Ví dụ sử dụng |
|---|---|---|
| `html_strip` | Loại bỏ thẻ HTML và giải mã một số entity HTML | Bỏ `<b>` khỏi nội dung mô tả |
| `mapping` | Thay thế chuỗi hoặc ký tự theo bảng ánh xạ | Đổi ký hiệu đặc biệt hoặc chuẩn hóa biến thể ký tự |
| `pattern_replace` | Thay thế phần khớp biểu thức chính quy | Loại mã định dạng hoặc thay dấu phân cách |

Ví dụ, `html_strip` có thể biến:

~~~html
<p>Spring <strong>Data</strong></p>
~~~

thành văn bản:

~~~text
Spring Data
~~~

Một cấu hình analyzer có character filter:

~~~json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "remove_html": {
          "type": "html_strip"
        }
      },
      "analyzer": {
        "html_text": {
          "type": "custom",
          "char_filter": ["remove_html"],
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  }
}
~~~

Character filter cũng phải được cân nhắc khi xử lý nội dung có định dạng. Ví dụ, xóa mọi dấu gạch nối có thể khiến một số mã sản phẩm hoặc thuật ngữ bị thay đổi ý nghĩa. Chỉ nên thay thế những ký tự mà quy tắc tìm kiếm của ứng dụng thực sự muốn chuẩn hóa.

## 4. Tokenizer: chia văn bản thành token

Tokenizer quyết định ranh giới giữa các token. Nó là thành phần duy nhất bắt buộc trong một custom analyzer. Elasticsearch có nhiều tokenizer tích hợp sẵn:

| Tokenizer | Cách hoạt động | Trường hợp thường gặp |
|---|---|---|
| `standard` | Chia văn bản theo quy tắc ranh giới từ Unicode | Văn bản thông thường, nhiều ngôn ngữ |
| `whitespace` | Tách tại khoảng trắng | Dữ liệu đã được chuẩn hóa ranh giới từ |
| `letter` | Tách tại ký tự không phải chữ cái | Nội dung chủ yếu là từ ngữ |
| `keyword` | Giữ toàn bộ đầu vào thành một token | Khi cần xem cả chuỗi là một đơn vị |
| `pattern` | Tách theo biểu thức chính quy | Dữ liệu có dấu phân cách riêng |
| `ngram` | Sinh các chuỗi con có độ dài cấu hình | Tìm kiếm một phần chuỗi |
| `edge_ngram` | Sinh các chuỗi con từ đầu token | Gợi ý khi người dùng đang nhập |
| `path_hierarchy` | Tách đường dẫn thành các cấp từ trái sang phải | Lọc theo cây thư mục hoặc phân cấp |

Ví dụ với `standard` tokenizer, chuỗi:

~~~text
Spring Data Elasticsearch 2026
~~~

có thể được chia thành các token tương ứng với `Spring`, `Data`, `Elasticsearch` và `2026`. Token filter phía sau có thể tiếp tục chuyển các token này thành chữ thường.

Với `keyword` tokenizer, toàn bộ chuỗi `Spring Data Elasticsearch 2026` trở thành một token. Vì vậy tokenizer này phù hợp khi cả giá trị cần được xem như một đơn vị. Trên trường kiểu `keyword`, Elasticsearch thường dùng cơ chế này thông qua keyword analyzer hoặc normalizer.

### N-gram và edge n-gram

`ngram` tạo nhiều chuỗi con liên tiếp từ token gốc. Ví dụ với từ `phone` và độ dài n-gram từ 2 đến 3, các token có thể gồm `ph`, `pho`, `ho`, `hon`, `on`, `one`.

`edge_ngram` chỉ tạo các chuỗi con bắt đầu từ đầu token. Với cùng từ `phone`, kết quả có thể gồm `ph`, `pho`, `phon`, `phone` tùy giới hạn độ dài.

Hai tokenizer này hữu ích cho tìm kiếm một phần chuỗi và autocomplete, nhưng làm tăng số lượng token được lập chỉ mục. Nên giới hạn khoảng độ dài, dùng trường riêng cho chức năng gợi ý và đo kích thước index trước khi triển khai rộng.

### Lưu ý với tiếng Việt

Tiếng Việt viết các âm tiết cách nhau bằng khoảng trắng, trong khi một từ có thể gồm nhiều âm tiết. Tokenizer dựa trên ranh giới khoảng trắng hoặc ranh giới từ Unicode có thể tách từng âm tiết, nhưng không nhất thiết nhận biết đầy đủ ranh giới từ ghép theo ngôn ngữ. Ví dụ, một cụm nhiều âm tiết có thể được chia thành nhiều token dù người đọc xem đó là một đơn vị từ vựng.

Vì vậy, analyzer mặc định có thể đáp ứng tìm kiếm cơ bản nhưng chưa chắc đáp ứng yêu cầu tìm kiếm tiếng Việt có chất lượng cao. Nếu cần nhận diện từ ghép, đồng nghĩa hoặc các biến thể ngôn ngữ, cần đánh giá plugin phân tích phù hợp, bộ từ điển hoặc bước tiền xử lý riêng. Việc bỏ dấu bằng `asciifolding` chỉ là chuẩn hóa ký tự; nó không thực hiện phân đoạn từ tiếng Việt.

## 5. Token filter: biến đổi danh sách token

Token filter nhận các token do tokenizer tạo ra. Có thể xếp nhiều filter liên tiếp để đạt quy tắc phân tích mong muốn.

Một số token filter thường gặp:

| Token filter | Tác dụng | Ví dụ hoặc mục đích |
|---|---|---|
| `lowercase` | Chuyển token thành chữ thường | `Spring` thành `spring` |
| `uppercase` | Chuyển token thành chữ hoa | Chuẩn hóa mã theo chữ hoa |
| `asciifolding` | Chuyển nhiều ký tự ngoài ASCII về dạng ASCII tương ứng | `café` thành `cafe` |
| `stop` | Loại bỏ từ dừng theo danh sách | Bỏ những từ quá phổ biến nếu phù hợp |
| `stemmer` | Đưa từ về dạng gốc gần đúng theo ngôn ngữ | `running` có thể về `run` |
| `synonym` / `synonym_graph` | Mở rộng hoặc thay thế token bằng từ đồng nghĩa | Tìm `tv` cùng với `television` |
| `trim` | Loại khoảng trắng ở đầu và cuối token | Làm sạch token |
| `unique` | Loại token trùng lặp | Hạn chế lặp trong một vị trí |
| `ngram` / `edge_ngram` | Sinh token con từ token đã tách | Tìm kiếm từng phần hoặc autocomplete |
| `shingle` | Tạo token từ các nhóm token liền nhau | Tăng khả năng khớp cụm từ |

### Thứ tự filter ảnh hưởng kết quả

Giả sử analyzer dùng `lowercase` và `stop`. Token filter `stop` sẽ loại từ dừng theo danh sách được cấu hình. Việc chuyển chữ thường trước giúp danh sách stopword được áp dụng nhất quán với các biến thể viết hoa.

Tương tự, khi dùng synonym filter, cần xác định từ đồng nghĩa được phân tích như thế nào. Một chuỗi đồng nghĩa có thể chứa nhiều từ; `synonym_graph` thường phù hợp hơn cho truy vấn nhiều từ vì giữ thông tin quan hệ token cần thiết cho phrase query. Cấu hình synonym cũng cần được kiểm tra với các filter đứng trước nó.

Không nên thêm tất cả filter chỉ vì chúng có sẵn. Stemming có thể làm mất khác biệt ý nghĩa trong một số lĩnh vực; stopword có thể chứa từ quan trọng đối với nghiệp vụ; synonym có thể làm tăng số kết quả không mong muốn. Hãy xác định hành vi tìm kiếm cần có rồi mới chọn chuỗi filter.

## 6. Analyzer tích hợp sẵn và custom analyzer

Elasticsearch cung cấp nhiều analyzer tích hợp sẵn. Một số lựa chọn phổ biến:

| Analyzer | Đặc điểm chính | Khi nào cân nhắc |
|---|---|---|
| `standard` | Standard tokenizer và lowercase; cấu hình stopword mặc định không loại từ nào | Lựa chọn khởi đầu cho văn bản phổ thông |
| `simple` | Tách theo ký tự không phải chữ cái và chuyển chữ thường | Văn bản chủ yếu gồm chữ cái |
| `whitespace` | Tách theo khoảng trắng | Khi ranh giới từ đã được kiểm soát |
| `stop` | Tương tự simple và loại stopword | Khi cần bỏ từ dừng theo ngôn ngữ |
| `keyword` | Giữ toàn bộ chuỗi thành một token | Giá trị cần so khớp nguyên chuỗi |
| `pattern` | Tách bằng biểu thức chính quy | Dữ liệu có cấu trúc phân cách riêng |
| `language` | Áp dụng quy tắc phân tích cho một ngôn ngữ được hỗ trợ | Văn bản ngôn ngữ tương ứng |
| `fingerprint` | Chuẩn hóa và sắp xếp token để tạo biểu diễn fingerprint | Nhận diện nội dung tương đương theo token |

Khi analyzer tích hợp sẵn không đáp ứng yêu cầu, có thể định nghĩa **custom analyzer** bằng cách kết hợp character filter, tokenizer và token filter.

Ví dụ custom analyzer cho tên sản phẩm:

~~~json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "strip_html": {
          "type": "html_strip"
        }
      },
      "filter": {
        "fold_accents": {
          "type": "asciifolding",
          "preserve_original": true
        }
      },
      "analyzer": {
        "product_index": {
          "type": "custom",
          "char_filter": ["strip_html"],
          "tokenizer": "standard",
          "filter": ["lowercase", "fold_accents"]
        },
        "product_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "fold_accents"]
        }
      }
    }
  }
}
~~~

Analyzer `product_index` loại thẻ HTML, chia từ, chuyển chữ thường và xử lý dấu. `product_search` áp dụng cách chuẩn hóa tương ứng cho nội dung truy vấn. Trong cấu hình này `preserve_original` giữ cả token gốc và token đã folding; điều này có thể tăng số token và cần được kiểm tra theo kết quả mong muốn.

Cấu hình analyzer phải được khai báo trong settings của index trước khi tạo mapping sử dụng analyzer đó. Nếu index đã tồn tại, việc chỉ sửa file cấu hình hoặc annotation Java không tự thay đổi analyzer đã được lưu trong index.

## 7. Analyzer ở thời điểm index và thời điểm search

Elasticsearch có thể phân tích văn bản ở hai thời điểm:

- **Index time:** phân tích giá trị trường trước khi lưu token vào inverted index.
- **Search time:** phân tích chuỗi truy vấn trước khi so khớp với các token đã lập chỉ mục.

Trong mapping, có thể chỉ định `analyzer` cho lúc lập chỉ mục và `search_analyzer` cho lúc truy vấn. Nếu không chỉ định `search_analyzer`, analyzer của trường thường được dùng làm mặc định cho tìm kiếm.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "product_index",
        "search_analyzer": "product_search"
      }
    }
  }
}
~~~

Hai analyzer không bắt buộc phải giống hệt nhau. Tuy nhiên, chúng cần tạo ra các token tương thích. Nếu lúc index dùng stemming mà lúc search không dùng, truy vấn có thể tạo token không khớp với token đã lưu. Ngược lại, nếu search analyzer mở rộng quá nhiều từ đồng nghĩa, kết quả có thể rộng hơn mong muốn.

Một cách tiếp cận thường dùng là giữ analyzer index ổn định, sau đó điều chỉnh analyzer tìm kiếm cho các nhu cầu như synonym hoặc xử lý truy vấn. Việc lựa chọn còn phụ thuộc vào khả năng thay đổi cấu hình và yêu cầu nhất quán của ứng dụng.

## 8. Normalizer: chuẩn hóa giá trị keyword

Normalizer là cơ chế chuẩn hóa dành cho trường kiểu `keyword`. Khác với analyzer, normalizer không có tokenizer và phải tạo ra đúng một token. Nó thường dùng các character filter và token filter phù hợp với giới hạn của normalizer, chẳng hạn lowercase hoặc asciifolding.

Ví dụ, ứng dụng muốn mã thương hiệu không phân biệt chữ hoa chữ thường khi lọc. Có thể khai báo normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_ascii": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "brand": {
        "type": "keyword",
        "normalizer": "lowercase_ascii"
      }
    }
  }
}
~~~

Khi lập chỉ mục và tìm kiếm trên trường này, giá trị được chuẩn hóa theo cùng quy tắc. Ví dụ `SONY`, `Sony` và `sony` có thể được chuẩn hóa về cùng dạng chữ thường. Với các ký tự có dấu, `asciifolding` có thể chuyển một số biến thể về dạng ASCII tương ứng.

So sánh nhanh:

| Đặc điểm | Analyzer | Normalizer |
|---|---|---|
| Mục tiêu chính | Phân tích văn bản để tìm kiếm toàn văn | Chuẩn hóa giá trị keyword |
| Tokenizer | Có đúng một tokenizer | Không có tokenizer |
| Số token đầu ra | Có thể có nhiều token | Luôn là một token |
| Trường thường dùng | `text` | `keyword` |
| Ví dụ | Tách tiêu đề thành các từ | Chuẩn hóa tên thương hiệu để lọc không phân biệt hoa thường |

Không dùng normalizer thay cho analyzer khi cần tìm kiếm theo từng từ. Ngược lại, không nên dùng trường `text` đã tách token cho yêu cầu so khớp nguyên giá trị, sắp xếp hoặc aggregation theo toàn bộ chuỗi. Khi một thuộc tính cần cả hai cách sử dụng, hãy tạo multi-fields.

## 9. Áp dụng analyzer và normalizer trong Spring Data Elasticsearch

Spring Data Elasticsearch ánh xạ entity Java với mapping của Elasticsearch. Có thể khai báo analyzer và normalizer trong annotation của trường, đồng thời cung cấp settings khi tạo index.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products")
@Setting(settingPath = "/elasticsearch/product-settings.json")
public class ProductDocument {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "product_index",
        searchAnalyzer = "product_search"
    )
    private String name;

    @Field(
        type = FieldType.Keyword,
        normalizer = "lowercase_ascii"
    )
    private String brand;

    // Constructors, getters và setters
}
~~~

Trong ví dụ:

- `@Document` xác định index của entity.
- `@Setting` chỉ tới file settings chứa định nghĩa analyzer và normalizer.
- `@Field(type = FieldType.Text, ...)` ánh xạ tên sản phẩm thành trường toàn văn và chọn analyzer riêng cho index/search.
- `@Field(type = FieldType.Keyword, normalizer = ...)` chuẩn hóa thương hiệu nhưng vẫn giữ giá trị thành một token.

Đặt file cấu hình tại classpath, ví dụ `src/main/resources/elasticsearch/product-settings.json`. Nội dung file có thể chứa phần `analysis` tương tự ví dụ custom analyzer và normalizer ở trên. Tên analyzer, search analyzer và normalizer trong annotation phải khớp chính xác với tên được khai báo trong settings.

Một thuộc tính có thể cần cả tìm kiếm toàn văn và so khớp nguyên chuỗi. Có thể dùng multi-fields để lập chỉ mục cùng một giá trị theo nhiều kiểu:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "product_index",
        searchAnalyzer = "product_search"
    ),
    otherFields = {
        @InnerField(
            suffix = "raw",
            type = FieldType.Keyword,
            normalizer = "lowercase_ascii"
        )
    }
)
private String name;
~~~

Mapping tạo ra có thể cung cấp trường `name` để tìm toàn văn và `name.raw` để lọc chính xác, sắp xếp hoặc aggregation. Cần kiểm tra mapping thực tế được tạo ra để chắc chắn các field và settings đã được áp dụng.

Tên thuộc tính annotation và API có thể khác theo phiên bản Spring Data Elasticsearch. Khi nâng cấp phiên bản, cần đối chiếu tài liệu của phiên bản đang dùng, đặc biệt với cách khai báo settings, mapping và query.

## 10. Kiểm tra analyzer bằng Analyze API

Không nên đoán token đầu ra chỉ từ tên analyzer. Elasticsearch cung cấp Analyze API để xem trực tiếp văn bản được phân tích như thế nào.

Ví dụ gọi analyzer của index:

~~~http
POST /products/_analyze
{
  "analyzer": "product_index",
  "text": "<p>CAFÉ Shoes</p>"
}
~~~

Có thể yêu cầu Elasticsearch giải thích từng bước bằng tùy chọn `explain`:

~~~http
POST /products/_analyze
{
  "analyzer": "product_index",
  "text": "CAFÉ Shoes",
  "explain": true
}
~~~

Kết quả trả về chứa danh sách token và các thông tin như vị trí, offset, kiểu token; chế độ explain cung cấp thêm chi tiết theo từng giai đoạn. Đây là cách hữu ích để xác nhận character filter, tokenizer và token filter đang hoạt động đúng như dự định.

Ngoài Analyze API, có thể kiểm tra cấu hình index và mapping:

~~~http
GET /products/_settings
GET /products/_mapping
~~~

Khi thử truy vấn, cần phân biệt `match` và `term`:

~~~json
{
  "query": {
    "match": {
      "name": "cafe shoes"
    }
  }
}
~~~

`match` phân tích chuỗi truy vấn bằng search analyzer phù hợp với trường trước khi tìm kiếm. Đây thường là lựa chọn cho trường `text`.

~~~json
{
  "query": {
    "term": {
      "brand": "SONY"
    }
  }
}
~~~

`term` tìm giá trị đã được lập chỉ mục theo dạng chính xác và không tự phân tích chuỗi truy vấn như `match`. Với trường keyword có normalizer, cần hiểu cách giá trị được chuẩn hóa để gửi giá trị truy vấn tương thích. Không nên dùng `term` trên trường `text` cho tìm kiếm toàn văn thông thường.

## 11. Những lỗi cấu hình thường gặp

**Dùng sai kiểu field.** Nếu trường cần tìm toàn văn lại được ánh xạ thành `keyword`, truy vấn `match` không có hành vi phân tích từng từ như mong đợi. Nếu trường cần lọc theo nguyên giá trị lại chỉ có dạng `text`, việc lọc và aggregation có thể không phù hợp. Dùng multi-fields khi cần cả hai cách.

**Analyzer không tồn tại.** Mapping tham chiếu `product_index` nhưng settings không khai báo analyzer đó, hoặc settings chưa được áp dụng khi index được tạo. Kiểm tra `_settings` và thứ tự tạo index.

**Analyzer index và search không tương thích.** Token sinh ra ở thời điểm tìm kiếm không khớp token được lập chỉ mục. Dùng Analyze API với cả hai analyzer trên những cụm từ đại diện rồi so sánh kết quả.

**Thay đổi annotation nhưng index không đổi.** Annotation trong mã Java mô tả mapping mà Spring Data sử dụng khi tạo index. Nếu index đã tồn tại với mapping cũ, việc cập nhật entity không đồng nghĩa Elasticsearch tự sửa mapping hoặc phân tích lại dữ liệu cũ. Thông thường cần tạo index mới với settings/mapping mới, reindex dữ liệu rồi chuyển alias hoặc luồng đọc sang index mới.

**Dùng n-gram quá rộng.** N-gram có thể làm tăng đáng kể số lượng token và kích thước index. Giới hạn min/max gram, chọn trường riêng và đo hiệu năng bằng dữ liệu gần với thực tế.

**Bỏ dấu hoặc stemming quá mức.** Chuẩn hóa giúp tìm kiếm dễ hơn nhưng có thể làm mất phân biệt giữa các từ hoặc mã. Nên kiểm tra các cặp từ dễ nhầm và dữ liệu đặc thù trước khi áp dụng trên toàn bộ nội dung.

**Giả định analyzer mặc định hiểu mọi ngôn ngữ.** Quy tắc tách từ và stemming phụ thuộc ngôn ngữ. Đặc biệt với tiếng Việt, tách theo khoảng trắng chưa chắc nhận diện đúng từ ghép. Cần thử với truy vấn và nội dung thực tế của sản phẩm.

## 12. Quy trình thiết kế và triển khai

Có thể triển khai theo trình tự sau:

1. **Xác định hành vi tìm kiếm.** Làm rõ có cần tìm theo từng từ, cụm từ, không phân biệt hoa thường, không phân biệt dấu, từ đồng nghĩa, autocomplete hay so khớp chính xác.
2. **Chọn kiểu field.** Dùng `text` cho nội dung cần phân tích; dùng `keyword` cho mã, trạng thái, danh mục và giá trị cần lọc hoặc gom nhóm; dùng multi-fields nếu cần cả hai.
3. **Chọn analyzer tối thiểu.** Bắt đầu với analyzer tích hợp sẵn. Chỉ tạo custom analyzer khi có yêu cầu cụ thể.
4. **Thiết kế settings và mapping.** Khai báo character filter, tokenizer, token filter, normalizer và gắn chúng vào đúng field trước khi tạo index.
5. **Thử bằng Analyze API.** Kiểm tra các ví dụ có dấu câu, chữ hoa, dấu tiếng Việt, từ ghép, mã sản phẩm và từ đồng nghĩa.
6. **Kiểm tra truy vấn thực tế.** So sánh kết quả `match`, phrase query, `term`, filter và aggregation với kỳ vọng nghiệp vụ.
7. **Đưa vào Spring Data Elasticsearch.** Khai báo settings và mapping qua annotation hoặc cơ chế tạo index phù hợp với kiến trúc ứng dụng; xác nhận index đã được tạo với cấu hình mong muốn.
8. **Lập kế hoạch thay đổi index.** Khi thay đổi analyzer hoặc mapping cần áp dụng lại cho dữ liệu đã lưu, chuẩn bị reindex và chuyển đổi an toàn.

Analyzer quyết định cách văn bản được biến thành token; tokenizer xác định ranh giới token; token filter thay đổi danh sách token; normalizer chuẩn hóa một giá trị keyword thành một token duy nhất. Nắm rõ vai trò và thời điểm áp dụng của từng thành phần giúp thiết kế tìm kiếm nhất quán, dễ kiểm thử và phù hợp với dữ liệu thực tế của ứng dụng Spring Data Elasticsearch.
