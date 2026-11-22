# Match phrase, khoảng cách từ và thứ tự xuất hiện

Khi tìm kiếm toàn văn, đôi khi chỉ cần các từ xuất hiện trong cùng một document là chưa đủ. Người dùng có thể muốn tìm một cụm từ theo đúng thứ tự, chẳng hạn `quick brown fox`, hoặc chấp nhận một vài từ nằm giữa các từ trong cụm. Elasticsearch cung cấp **`match_phrase` query** để tìm theo vị trí token, đồng thời cho phép nới lỏng điều kiện bằng tham số **`slop`**.

Trong Spring Data Elasticsearch, có thể tạo loại truy vấn này bằng `NativeQuery` và Elasticsearch Java API Client. Hiểu rõ analyzer, vị trí token và cách tính slop giúp chọn được độ linh hoạt phù hợp mà vẫn giữ kết quả có ý nghĩa.

## 1. Match thông thường và match phrase

`match` và `match_phrase` đều phân tích chuỗi truy vấn bằng analyzer, nhưng chúng có mục đích khác nhau:

| Query | Điều kiện khớp | Khi nào dùng |
| --- | --- | --- |
| `match` | Các token được phân tích có thể khớp theo operator AND/OR; không bắt buộc nằm cạnh nhau hoặc theo đúng thứ tự. | Tìm nội dung theo từ khóa, khi vị trí chính xác không quan trọng. |
| `match_phrase` | Các token phải khớp theo quan hệ vị trí và thứ tự của cụm từ, trong phạm vi slop cho phép. | Tìm cụm từ, tên riêng, tiêu đề hoặc thuật ngữ có thứ tự từ quan trọng. |
| `match_phrase_prefix` | Tương tự phrase query, nhưng token cuối có thể được khớp theo tiền tố. | Gợi ý cụm từ/autocomplete theo phần đầu của từ cuối cùng. |

Giả sử document có nội dung:

~~~text
The quick brown fox jumps over the lazy dog.
~~~

Truy vấn `match` với `quick fox` có thể tìm thấy document vì cả hai từ đều xuất hiện, dù có từ `brown` nằm giữa. `match_phrase` với `quick fox` và `slop: 0` không khớp vì hai token không ở vị trí liền kề. Nếu đặt `slop: 1`, phrase query có thể khớp vì token `fox` chỉ cách vị trí mong đợi một bước.

`match_phrase` không so sánh chuỗi ký tự nguyên văn. Nó so sánh các token và vị trí do analyzer tạo ra. Vì vậy dấu câu, chữ hoa/thường, dấu tiếng Việt hoặc stop words có thể ảnh hưởng kết quả theo cấu hình analyzer.

## 2. Analyzer tạo token và vị trí

Elasticsearch không lưu văn bản `text` như một chuỗi duy nhất để phrase query so sánh từng ký tự. Khi index một field `text`, analyzer chuyển chuỗi thành token và ghi thông tin vị trí (position) của các token trong inverted index.

Ví dụ với analyzer đơn giản, văn bản:

~~~text
quick brown fox
~~~

có thể tạo các token:

| Token | Position |
| --- | ---: |
| `quick` | 0 |
| `brown` | 1 |
| `fox` | 2 |

Phrase query `quick brown fox` ở slop 0 yêu cầu các token xuất hiện theo đúng thứ tự và vị trí tương đối này. Nếu document là `quick red brown fox`, vị trí có thể là `quick=0`, `red=1`, `brown=2`, `fox=3`; phrase query ban đầu cần di chuyển vị trí các token để khớp và slop quyết định mức di chuyển được chấp nhận.

### 2.1. Vị trí khác với khoảng cách ký tự

Position là thứ tự token trong luồng analyzer, không phải vị trí byte, ký tự hay số lượng dấu cách trong chuỗi. Nhiều dấu cách, dấu phẩy hoặc dấu chấm có thể bị tokenizer bỏ qua mà không tạo token riêng.

Ví dụ `quick, brown   fox` thường vẫn có các token ở vị trí 0, 1, 2 với analyzer standard. Phrase query có thể khớp dù dấu câu và số lượng khoảng trắng khác nhau.

### 2.2. Analyzer của field và search analyzer

Analyzer dùng khi lập chỉ mục tạo token/position được lưu trong inverted index. Khi chạy `match_phrase`, chuỗi truy vấn cũng được phân tích bằng search analyzer của field (hoặc analyzer được chỉ định trong query). Hai phía cần có quy tắc tương thích.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "search_analyzer": "standard"
      }
    }
  }
}
~~~

Nếu index analyzer và search analyzer khác nhau, phrase query vẫn có thể hoạt động nhưng vị trí và token phải được thiết kế có chủ đích. Thay analyzer sau khi dữ liệu đã được index không tự tạo lại token cũ; khi thay đổi cách phân tích lúc index, thường cần tạo index mới và reindex.

## 3. Cú pháp `match_phrase` và tham số `slop`

Query DSL cơ bản:

~~~json
{
  "query": {
    "match_phrase": {
      "title": "quick brown fox"
    }
  }
}
~~~

Có thể khai báo object để điều khiển `slop`, analyzer và boost:

~~~json
{
  "query": {
    "match_phrase": {
      "title": {
        "query": "quick brown fox",
        "slop": 1,
        "analyzer": "standard",
        "boost": 2.0
      }
    }
  }
}
~~~

Các tham số quan trọng:

| Tham số | Ý nghĩa |
| --- | --- |
| `query` | Cụm văn bản cần phân tích thành token. |
| `slop` | Mức di chuyển vị trí được cho phép để các token khớp với cụm. Mặc định là `0`. |
| `analyzer` | Ghi đè analyzer dùng để phân tích văn bản truy vấn; nếu bỏ qua, Elasticsearch dùng search analyzer của field theo quy tắc mapping. |
| `boost` | Điều chỉnh trọng số relevance của query so với các query khác. |
| `zero_terms_query` | Quy định hành vi nếu analyzer loại bỏ toàn bộ token; mặc định thường là `none`. |

`slop: 0` yêu cầu các token khớp theo đúng vị trí tương đối, không có khoảng trống bổ sung. Tăng slop cho phép các token di chuyển vị trí để phrase vẫn khớp.

## 4. Slop đo khoảng cách như thế nào?

Slop là chi phí di chuyển vị trí token để biến các vị trí trong document thành quan hệ vị trí mà phrase query yêu cầu. Có thể hiểu gần đúng là mức linh hoạt về khoảng cách và thứ tự, nhưng **slop không đơn giản luôn bằng số từ nằm giữa hai từ**.

Ví dụ query:

~~~json
{
  "query": {
    "match_phrase": {
      "title": {
        "query": "quick fox",
        "slop": 1
      }
    }
  }
}
~~~

Document `quick brown fox` có token `quick` ở position 0 và `fox` ở position 2. Để khớp phrase `quick fox`, token `fox` phải dịch một vị trí về quan hệ mong muốn; slop 1 đủ để chấp nhận trường hợp này.

Với query `quick brown fox`, document `quick brown red fox` có thêm một token giữa `brown` và `fox`. Slop 1 có thể cho phép cụm khớp bằng một bước dịch vị trí.

### 4.1. Slop 0

Slop 0 là lựa chọn chặt nhất: các token phải xuất hiện theo đúng thứ tự và vị trí tương đối liền nhau sau khi analyzer xử lý.

| Document | Query `quick brown fox`, slop 0 |
| --- | --- |
| `quick brown fox` | Khớp. |
| `quick brown red fox` | Không khớp vì có token chen giữa. |
| `brown quick fox` | Không khớp vì thứ tự thay đổi. |
| `quick, brown fox` | Thường khớp vì dấu câu không tạo token riêng với standard analyzer. |

### 4.2. Slop lớn hơn 0

Slop lớn hơn 0 cho phép token cách nhau một khoảng hoặc dịch vị trí tương đối. Điều này hữu ích khi người viết có thể thêm từ phụ nhưng cụm từ chính vẫn cần giữ gần nhau.

Ví dụ:

| Document | Query `quick brown fox` | Nhận xét |
| --- | --- | --- |
| `quick brown fox` | slop 0 | Khớp chính xác theo vị trí. |
| `quick brown red fox` | slop 1 | Có thể khớp với một bước dịch vị trí. |
| `quick very brown red fox` | slop nhỏ | Cần nhiều dịch chuyển hơn; tăng slop theo vị trí thực tế. |
| `fox brown quick` | slop thấp | Không khớp; đảo thứ tự cần chi phí lớn hơn. |

Khi chọn slop, hãy kiểm tra trên tập câu đại diện bằng `_analyze` và truy vấn thực tế. Không nên chọn một con số lớn chỉ để tăng số kết quả, vì các cụm có từ quan trọng bị đảo hoặc cách xa nhau cũng có thể bắt đầu khớp.

### 4.3. Đảo vị trí từ (transposition)

Phrase query có slop lớn hơn 0 có thể chấp nhận một số trường hợp token đổi thứ tự. Trong cách tính slop của Elasticsearch, việc hoán đổi hai token liền kề có chi phí 2.

Ví dụ query `quick brown` và document `brown quick` không khớp ở slop 0. Slop 2 có thể chấp nhận việc đảo hai token này. Vì vậy, nếu nghiệp vụ yêu cầu thứ tự từ phải chính xác, hãy dùng slop 0.

Slop lớn không chỉ có nghĩa là “cho phép thêm N từ”. Nó còn cho phép token dịch vị trí và, khi đủ chi phí, thay đổi thứ tự. Hãy cân nhắc ý nghĩa ngôn ngữ trước khi tăng slop.

## 5. Thứ tự xuất hiện của từ

Với slop 0, `match_phrase` giữ thứ tự token như cụm truy vấn. Ví dụ query `spring data elasticsearch` khớp cụm theo đúng thứ tự đó sau analyzer.

| Nội dung document | Query `spring data elasticsearch`, slop 0 |
| --- | --- |
| `Spring Data Elasticsearch` | Khớp. |
| `Learn Spring Data Elasticsearch` | Khớp vì cụm xuất hiện liên tiếp bên trong câu. |
| `Elasticsearch Spring Data` | Không khớp vì thứ tự khác. |
| `Spring Elasticsearch Data` | Không khớp vì vị trí tương đối khác. |
| `Spring Data for Elasticsearch` | Không khớp ở slop 0 vì có token `for` chen giữa. |

Khi đặt slop phù hợp, document có một số từ phụ giữa các token vẫn có thể khớp. Nếu cho phép đổi thứ tự, slop phải đủ lớn để trả chi phí cho sự di chuyển đó.

## 6. Dùng `match_phrase` trong Spring Data Elasticsearch

Với Spring Data Elasticsearch dùng Elasticsearch Java API Client, có thể xây dựng phrase query qua `NativeQuery`.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard",
            searchAnalyzer = "standard")
    private String title;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String content;

    // Constructor, getters và setters
}
~~~

Tạo phrase query với slop 0:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.matchPhrase(mp -> mp
                .field("title")
                .query("spring data elasticsearch")
                .slop(0)))
        .build();
~~~

Thực thi qua `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<ArticleDocument> findExactPhrase(
        ElasticsearchOperations operations) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.matchPhrase(mp -> mp
                    .field("title")
                    .query("spring data elasticsearch")
                    .slop(0)))
            .build();

    return operations.search(query, ArticleDocument.class);
}
~~~

Để cho phép một token chen giữa, có thể đổi slop:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.matchPhrase(mp -> mp
                .field("content")
                .query("spring data elasticsearch")
                .slop(2)))
        .build();
~~~

Các method builder được sinh từ Elasticsearch Java API Client. Tên method và kiểu tham số cần tương thích với phiên bản client được Spring Data Elasticsearch quản lý trong dự án.

## 7. Dùng phrase query trong repository/service

Với truy vấn phrase có cấu trúc cố định, có thể đặt logic trong custom repository fragment hoặc service chuyên tìm kiếm. Điều này giúp caller chỉ truyền cụm từ và không phải tự tạo Query DSL.

Ví dụ service:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {

    private final ElasticsearchOperations operations;

    public ArticleSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ArticleDocument> searchTitlePhrase(String phrase) {
        NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q.matchPhrase(mp -> mp
                        .field("title")
                        .query(phrase)
                        .slop(0)))
                .build();

        return operations.search(query, ArticleDocument.class);
    }
}
~~~

Có thể mở rộng method để nhận slop do use case lựa chọn, nhưng nên giới hạn giá trị trong khoảng hợp lý. Không nên cho client tự đặt slop rất lớn mà không có giới hạn, vì điều đó có thể làm truy vấn rộng hơn mong muốn và tăng chi phí tìm kiếm.

## 8. Phrase query kết hợp điều kiện lọc

Phrase query thường là phần tìm kiếm nội dung và có thể tham gia relevance score. Các điều kiện như tenant, trạng thái, loại bài viết hoặc ngày xuất bản thường chỉ giới hạn tập kết quả.

Có thể kết hợp bằng `bool.must` và `bool.filter`:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match_phrase": {
            "title": {
              "query": "spring data elasticsearch",
              "slop": 0
            }
          }
        }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } },
        { "term": { "language": "vi" } }
      ]
    }
  }
}
~~~

Trong Spring Data, tạo NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.matchPhrase(mp -> mp
                        .field("title")
                        .query("spring data elasticsearch")
                        .slop(0)))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("PUBLISHED"))))
                .filter(f -> f.term(t -> t
                        .field("language")
                        .value(FieldValue.of("vi"))))))
        .build();
~~~

Phrase query quyết định mức độ khớp của cụm từ; filter chỉ loại document không đúng trạng thái hoặc ngôn ngữ. Kết quả có thể được xếp hạng theo score từ phrase query.

## 9. Tác động của analyzer tới phrase matching

Phrase query chỉ có thể làm việc chính xác khi hiểu cách analyzer tạo token và position. Một số cấu hình cần chú ý:

### 9.1. Lowercase và asciifolding

Analyzer có `lowercase` giúp `Spring`, `SPRING` và `spring` tạo token tương thích. `asciifolding` có thể chuẩn hóa một số ký tự có dấu về dạng ASCII gần tương ứng.

Ví dụ, nếu cả index analyzer và search analyzer đều chuyển chữ thường, query `Spring Data` có thể khớp document `SPRING DATA`. Việc bỏ dấu phụ thuộc analyzer và ngôn ngữ; hãy thử với dữ liệu tiếng Việt thực tế thay vì giả định mọi dấu được chuẩn hóa theo cùng cách.

### 9.2. Stop words và khoảng trống vị trí

Stop filter có thể loại bỏ những từ thường gặp như `the`, `of`, `and`. Khi loại stop word, analyzer có thể giữ khoảng trống vị trí thông qua position increments.

Ví dụ câu `state of the art` sau khi loại `of` và `the` có thể còn token `state` và `art`, nhưng vị trí của `art` vẫn phản ánh khoảng trống do các từ bị loại. Phrase query `state art` vì vậy không nhất thiết tương đương với hai token liền nhau; hành vi phụ thuộc cấu hình analyzer và việc giữ position increments.

Không nên tắt position increments một cách tùy tiện để làm phrase query khớp dễ hơn, vì điều đó có thể khiến các từ vốn cách xa nhau trở thành liền kề về mặt vị trí.

### 9.3. Synonym và synonym graph

Synonym có thể mở rộng một từ thành nhiều lựa chọn hoặc một cụm nhiều token. Với synonym nhiều từ, filter `synonym_graph` được thiết kế để giữ cấu trúc token graph cần thiết cho truy vấn phrase.

Ví dụ `ny` và `new york` có thể được khai báo là các cách viết tương đương. Khi analyzer áp dụng synonym graph, phrase query có thể xét các đường token tương ứng. Cần kiểm tra bằng `_analyze` và truy vấn mẫu vì thứ tự filter, cách cấu hình synonym và search analyzer ảnh hưởng trực tiếp kết quả.

### 9.4. Tokenizer và ngôn ngữ

`standard` tokenizer phù hợp với nhiều loại văn bản tự nhiên, nhưng không phải bộ phân đoạn từ chuyên biệt cho mọi ngôn ngữ. Với tiếng Việt, cần kiểm tra các cụm có dấu, không dấu, từ ghép, tên riêng và cách người dùng nhập truy vấn.

Nếu analyzer tạo token khác với cách người dùng hiểu cụm từ, `match_phrase` có thể không cho kết quả mong muốn dù chuỗi nhìn bằng mắt có vẻ giống nhau. Khi đó cần điều chỉnh analyzer hoặc dùng plugin phân tích ngôn ngữ phù hợp.

## 10. Mảng giá trị text và khoảng cách giữa các giá trị

Một field `text` có thể chứa nhiều giá trị, ví dụ mảng tiêu đề hoặc tags dạng chuỗi. Elasticsearch dùng `position_increment_gap` để tạo khoảng cách vị trí giữa các giá trị trong cùng field, nhằm hạn chế phrase query khớp xuyên qua ranh giới giữa hai giá trị.

Ví dụ document:

~~~json
{
  "aliases": [
    "spring data",
    "elasticsearch guide"
  ]
}
~~~

Mặc định, Elasticsearch thường đặt khoảng cách vị trí lớn giữa các giá trị của cùng một field (mặc định 100). Vì vậy phrase query `data elasticsearch` với slop thông thường sẽ không khớp xuyên từ cuối giá trị thứ nhất sang đầu giá trị thứ hai.

Có thể cấu hình gap trên text field:

~~~json
{
  "mappings": {
    "properties": {
      "aliases": {
        "type": "text",
        "position_increment_gap": 100
      }
    }
  }
}
~~~

Đây là một cơ chế kiểm soát phrase positions, không phải ranh giới bảo mật. Nếu đặt slop lớn hơn gap, phrase query có thể vượt qua khoảng cách đó. Hãy chọn gap và giới hạn slop theo semantics của dữ liệu.

## 11. Field cần lưu positions

Phrase query cần thông tin vị trí token trong inverted index. Với field `text`, `index_options` mặc định thường lưu positions. Nếu mapping giảm `index_options` xuống mức không lưu positions, phrase query không thể hoạt động như mong muốn.

Ví dụ mapping thông thường:

~~~json
{
  "mappings": {
    "properties": {
      "body": {
        "type": "text",
        "index_options": "positions"
      }
    }
  }
}
~~~

Thông thường không cần khai báo `index_options` vì giá trị mặc định của `text` đã hỗ trợ phrase query. Chỉ thay đổi nó khi đã hiểu rõ tác động tới phrase, span và các truy vấn phụ thuộc vị trí.

## 12. Kiểm tra token bằng `_analyze`

Khi phrase query không trả kết quả như mong đợi, hãy kiểm tra analyzer trước. Ví dụ:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "field": "title",
  "text": "Spring Data for Elasticsearch",
  "explain": true
}
~~~

Phản hồi `_analyze` hiển thị các token cùng thông tin position, offset và type. Hãy xem:

- Token nào được tạo ra?
- Chữ hoa/thường và dấu được chuẩn hóa ra sao?
- Stop words có bị loại bỏ không?
- Position của token có giữ khoảng trống không?
- Synonym có tạo nhiều đường token không?

Có thể kiểm tra trực tiếp analyzer đã khai báo:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "standard",
  "text": "quick brown fox"
}
~~~

Khi dùng `field`, Elasticsearch lấy analyzer được gắn với field đó theo mapping. Khi dùng `analyzer`, request chỉ định analyzer cụ thể. So sánh kết quả giữa analyzer dùng khi index và analyzer dùng khi search để tìm nguyên nhân phrase mismatch.

## 13. So sánh `match_phrase`, `match_phrase_prefix` và `span_near`

| Query | Khả năng | Trường hợp sử dụng |
| --- | --- | --- |
| `match_phrase` | Khớp cụm token theo thứ tự và vị trí, có slop. | Tìm cụm từ hoàn chỉnh. |
| `match_phrase_prefix` | Giống phrase query nhưng token cuối được tìm theo prefix. | Autocomplete cụm từ. |
| `span_near` | Kết hợp span clauses với khoảng cách và thứ tự được kiểm soát chi tiết. | Truy vấn vị trí phức tạp, nhiều nhánh hoặc yêu cầu positional logic nâng cao. |

Không dùng `match_phrase_prefix` như cách thay thế mặc định cho phrase query. Prefix trên token cuối có thể mở rộng số lượng term cần xét và làm truy vấn tốn tài nguyên hơn.

`span_near` phù hợp khi cần kiểm soát chính xác khoảng cách, thứ tự và các loại clause vị trí. Query này phức tạp hơn và thường cần `NativeQuery` hoặc Query DSL trực tiếp.

## 14. Ảnh hưởng tới relevance score

`match_phrase` là query context và có thể đóng góp vào `_score`. Document khớp cụm từ gần với vị trí yêu cầu thường có mức độ phù hợp tốt hơn theo cách scoring của phrase query.

Có thể tăng trọng số phrase query khi muốn cụm từ chính xác quan trọng hơn các kết quả chỉ khớp từ khóa thông thường:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "match": {
            "content": {
              "query": "spring data elasticsearch"
            }
          }
        },
        {
          "match_phrase": {
            "title": {
              "query": "spring data elasticsearch",
              "slop": 0,
              "boost": 3.0
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Ở đây, `match` giúp tìm các document có token liên quan trong nội dung; `match_phrase` tăng mức ưu tiên cho document có cụm chính xác trong title. Giá trị boost là ví dụ và cần điều chỉnh dựa trên dữ liệu, đánh giá relevance và hành vi người dùng.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `match_phrase` không khớp dù các từ đều có trong document | Từ không liền nhau, sai thứ tự hoặc slop chưa đủ. | Kiểm tra positions và tăng slop có kiểm soát nếu nghiệp vụ cho phép. |
| Cụm từ khớp dù dấu câu khác | Analyzer loại bỏ dấu câu hoặc chuẩn hóa chuỗi. | Đây là hành vi dựa trên token; kiểm tra `_analyze` nếu cần phân biệt dấu câu. |
| Query phân biệt chữ hoa/thường ngoài dự kiến | Index/search analyzer không dùng lowercase tương thích. | Kiểm tra analyzer ở cả hai phía và cấu hình lowercase nếu phù hợp. |
| Từ có dấu và không dấu không khớp | Analyzer chưa áp dụng folding phù hợp hoặc ngôn ngữ cần xử lý riêng. | Thử `asciifolding` và bộ dữ liệu ngôn ngữ thực tế. |
| Phrase query khớp xuyên hai giá trị trong mảng | Slop đủ lớn để vượt `position_increment_gap`. | Chọn gap và giới hạn slop phù hợp với cấu trúc dữ liệu. |
| Phrase query báo lỗi về positions | Field mapping không lưu positions trong index options. | Dùng mapping `text` hỗ trợ positions và reindex dữ liệu. |
| Phrase query trên `keyword` không hoạt động như cụm từ | Keyword analyzer coi toàn chuỗi là một token. | Dùng field `text` hoặc multi-field phù hợp. |
| Tăng slop làm kết quả quá rộng | Slop cho phép token dịch vị trí và có thể đổi thứ tự. | Giảm slop, dùng slop 0 nếu thứ tự là bắt buộc. |
| Synonym làm phrase matching bất ngờ | Token graph hoặc thứ tự filter không phù hợp. | Kiểm tra analyzer với `explain` và cấu hình `synonym_graph`. |

## 16. Quy trình thiết kế phrase search

Khi thêm phrase search cho một field, hãy thực hiện theo thứ tự:

1. Xác định người dùng cần cụm chính xác hay có thể chấp nhận từ phụ ở giữa.
2. Chọn field mapping `text` có analyzer phù hợp; bảo đảm inverted index lưu positions.
3. Kiểm tra index analyzer và search analyzer tạo token tương thích.
4. Dùng `match_phrase` với slop 0 nếu thứ tự và vị trí liền kề phải chính xác.
5. Chỉ tăng slop khi nghiệp vụ cho phép khoảng cách hoặc thay đổi vị trí; nhớ rằng slop là chi phí di chuyển token, không chỉ là số từ chen giữa.
6. Nếu thứ tự tuyệt đối quan trọng, tránh slop đủ lớn để chấp nhận transposition.
7. Với mảng text, xem xét `position_increment_gap` để ngăn phrase query vượt ranh giới giá trị.
8. Kiểm tra stop words, synonyms và token positions bằng `_analyze`.
9. Dùng NativeQuery trong Spring Data khi cần phrase query hoặc kết hợp bool/filter rõ ràng.
10. Đánh giá kết quả và relevance trên tập truy vấn đại diện trước khi phát hành.

`match_phrase` tìm các token theo quan hệ vị trí và thứ tự, còn `slop` cho phép chúng dịch chuyển trong giới hạn chi phí. Slop 0 phù hợp với cụm liên tiếp đúng thứ tự; slop lớn hơn chấp nhận khoảng cách và có thể chấp nhận cả việc đảo vị trí khi đủ chi phí. Trong Spring Data Elasticsearch, `NativeQuery` giúp khai báo phrase query rõ ràng; `_analyze` là công cụ cần dùng để hiểu token và positions mà analyzer thực sự tạo ra.
