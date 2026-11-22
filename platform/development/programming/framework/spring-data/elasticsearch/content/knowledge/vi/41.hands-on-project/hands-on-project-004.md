# Thiết kế tự động hoàn thành và gợi ý sửa lỗi chính tả

Autocomplete giúp người dùng tìm đúng nội dung khi họ mới nhập một phần truy vấn. Spell correction đề xuất cách viết có khả năng đúng hơn khi người dùng gõ nhầm. Hai tính năng thường xuất hiện cạnh nhau trong ô tìm kiếm, nhưng có mục tiêu và cơ chế khác nhau.

Elasticsearch cung cấp nhiều cách xây dựng gợi ý:

- **Completion suggester** tối ưu cho gợi ý prefix có độ trễ thấp, phù hợp với tên sản phẩm, thương hiệu hoặc cụm từ điều hướng.
- **search_as_you_type** tạo các subfield phục vụ truy vấn nhiều từ đang nhập, bao gồm prefix và infix matching.
- **Term suggester** đề xuất từ thay thế theo edit distance.
- **Phrase suggester** chọn cách sửa cho cả cụm từ dựa trên mô hình đồng xuất hiện n-gram.
- **Fuzzy completion** cho phép completion suggester chịu một số lỗi gõ trong prefix.

Spring Data Elasticsearch hỗ trợ mapping completion field, xây query bằng NativeQuery/Elasticsearch Java API Client và đọc kết quả qua SearchHits. Khi triển khai, cần chọn đúng suggester cho trải nghiệm người dùng, giới hạn số kết quả và kiểm soát ngôn ngữ, tenant, ranking cũng như chi phí truy vấn.

## 1. Phân biệt autocomplete và spell correction

### 1.1. Autocomplete dự đoán phần còn lại của truy vấn

Người dùng mới nhập:

~~~text
wireless key
~~~

Autocomplete có thể đề xuất:

- Wireless Keyboard
- Wireless Keyboard Compact
- Wireless Keypad
- Wireless Keyboard Bluetooth

Mục tiêu là giúp người dùng hoàn tất truy vấn nhanh hơn. Kết quả thường là tên thực thể hoặc cụm từ có thể chọn ngay.

### 1.2. Spell correction sửa lỗi đã xuất hiện trong truy vấn

Người dùng nhập:

~~~text
wirless keybord
~~~

Spell correction có thể đề xuất:

~~~text
Did you mean "wireless keyboard"?
~~~

Mục tiêu là tìm một cách viết gần với input nhưng có xác suất đúng cao hơn dựa trên từ điển và ngữ cảnh dữ liệu.

### 1.3. Hai tính năng nên có luồng xử lý riêng

| Tình huống | Cơ chế phù hợp | Ví dụ |
|---|---|---|
| Người dùng đang gõ prefix | Completion suggester | "wire" → "Wireless Keyboard" |
| Người dùng gõ nhiều từ theo thứ tự linh hoạt | search_as_you_type | "wire key" → "Wireless Keyboard" |
| Người dùng gõ sai một token | Term suggester hoặc fuzzy completion | "keybord" → "keyboard" |
| Cần sửa cả cụm từ theo ngữ cảnh | Phrase suggester | "wireles keybord" → "wireless keyboard" |
| Cần kết quả tìm kiếm ngay cả khi chưa chọn suggestion | Search query bình thường | Search theo input hiện tại |

Không nên tự động thay đổi truy vấn của người dùng mỗi khi suggester đưa ra một candidate. Thường nên hiển thị suggestion để người dùng chọn hoặc dùng correction như một nhánh fallback có thể quan sát.

### 1.4. Luồng UI gợi ý

~~~mermaid
flowchart TD
    A[User types text] --> B{Input length sufficient?}
    B -->|No| C[Wait for more characters]
    B -->|Yes| D[Autocomplete query]
    D --> E[Show top suggestions]
    E --> F{User selects suggestion?}
    F -->|Yes| G[Run search with selected value]
    F -->|No| H[User submits raw query]
    H --> I[Run normal search]
    I --> J{Few or no useful results?}
    J -->|Yes| K[Run spell correction]
    J -->|No| L[Show search results]
    K --> M[Offer corrected query]
~~~

Autocomplete thường chạy theo debounce khi người dùng nhập. Spell correction có thể chạy khi submit hoặc khi search trả ít kết quả, tránh gọi correction nặng cho từng phím bấm.

## 2. Chọn cơ chế autocomplete trong Elasticsearch

### 2.1. Completion suggester

Completion suggester dùng field mapping kiểu **completion** và cấu trúc dữ liệu được tối ưu để tra cứu prefix nhanh.

Phù hợp khi:

- Gợi ý tên sản phẩm, thương hiệu, địa điểm hoặc câu truy vấn phổ biến.
- Cần trả danh sách ngắn khi người dùng đang nhập.
- Muốn xếp hạng suggestion bằng weight.
- Muốn dùng fuzzy option cho một số lỗi gõ trong prefix.

Completion suggester ưu tiên tốc độ và có thể tiêu thụ memory vì cấu trúc completion được lưu trong memory. Nó là tính năng điều hướng/autocomplete, không thay thế spell correction tổng quát.

### 2.2. search_as_you_type

Field type **search_as_you_type** tự tạo các subfield như:

- Field gốc đã được analyze.
- Subfield shingle 2-gram.
- Subfield shingle 3-gram.
- Subfield prefix index.

Cách query thường dùng là **multi_match** với type **bool_prefix** trên field gốc và các shingle subfield. Cơ chế này hỗ trợ prefix completion và infix completion trong một giá trị nhiều từ.

Phù hợp khi:

- Người dùng nhập nhiều từ.
- Từ đang nhập có thể nằm ở vị trí khác trong field.
- Muốn dùng query DSL thông thường thay vì suggester riêng.
- Cần kết hợp với filter, scoring hoặc các query khác.

### 2.3. Edge n-gram analyzer

Edge n-gram tạo các token prefix ở thời điểm index. Ví dụ từ keyboard có thể tạo:

~~~text
ke
key
keyb
keybo
keyboa
keyboard
~~~

Query time dùng analyzer bình thường để tìm token tương ứng.

Cách này linh hoạt nhưng làm tăng số term được index và có thể tăng dung lượng. Phải cấu hình analyzer index-time và search-time đúng cách; nếu dùng edge n-gram ở cả hai phía, kết quả có thể bị lệch.

### 2.4. So sánh ba lựa chọn

| Tiêu chí | Completion suggester | search_as_you_type | Edge n-gram |
|---|---|---|---|
| Mapping | completion | search_as_you_type | text + custom analyzer |
| Tốc độ prefix | Rất phù hợp | Phù hợp | Phụ thuộc index và query |
| Infix/multi-term | Hạn chế theo completion input | Có hỗ trợ | Có thể thiết kế |
| Fuzzy prefix | Có fuzzy options | Không phải cơ chế typo correction chính | Cần fuzzy query riêng |
| Ranking weight | Có weight riêng | Dùng query score | Dùng query score |
| Chi phí index | Completion structure, memory | Nhiều subfield | Nhiều token |
| Use case | Danh sách gợi ý điều hướng | Search-as-you-type trên text | Tùy biến prefix search |

Không cần triển khai cả ba cho cùng một field. Chọn theo dữ liệu, UX và yêu cầu latency.

## 3. Mapping completion field bằng Spring Data

### 3.1. Dùng @CompletionField

Spring Data Elasticsearch có annotation **@CompletionField** và kiểu **Completion**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions-v1")
public class ProductSuggestionDocument {

    @Id
    private String id;

    private String productName;

    @CompletionField(maxInputLength = 100)
    private Completion suggest;

    // Getters and setters.
}
~~~

Completion field được dùng để index một hoặc nhiều input string phục vụ gợi ý. Thuộc tính maxInputLength giới hạn độ dài input được index để tránh dữ liệu quá lớn làm phình completion structure.

### 3.2. Completion chứa nhiều input và weight

Một document có thể có nhiều cách gọi:

~~~java
Completion completion =
    new Completion(List.of(
        "Wireless Keyboard",
        "Wireless Keyboard Compact",
        "Bluetooth Keyboard"
    ));

completion.setWeight(100);
document.setSuggest(completion);
~~~

Weight là số nguyên dương dùng để xếp hạng suggestion. Có thể dùng popularity, mức độ ưu tiên nghiệp vụ hoặc tín hiệu chất lượng đã được tính trước.

Không đặt weight quá cao cho một item chỉ để nó luôn đứng đầu nếu điều đó làm suggestion kém liên quan. Cần đo click-through và conversion của suggestion để điều chỉnh ranking.

### 3.3. Index aliases và tên thay thế

Một product có thể được gợi ý bằng:

- Tên chính thức.
- Tên viết tắt.
- Tên không dấu.
- Alias phổ biến.
- Tên model.
- Tên cũ nếu người dùng vẫn thường tìm.

Ví dụ:

~~~java
Completion completion =
    new Completion(List.of(
        "Ho Chi Minh City",
        "HCMC",
        "Saigon",
        "Thành phố Hồ Chí Minh"
    ));
~~~

Các input này được gắn với cùng document ID. Khi người dùng chọn một suggestion, ứng dụng có thể lấy ID của document để điều hướng hoặc chạy search chính xác.

### 3.4. Không index mọi biến thể tùy tiện

Không nên tạo hàng trăm biến thể cho mỗi document. Chỉ index alias có giá trị thực tế. Quá nhiều input làm tăng kích thước completion structure và có thể trả suggestion nhiễu.

Chuẩn hóa viết hoa/thường, khoảng trắng và dấu câu nhất quán. Với tiếng Việt, quyết định rõ có index cả bản có dấu và không dấu hay dùng analyzer/normalization phù hợp. Đừng giả định lowercase filter tự chuyển tiếng Việt có dấu thành không dấu.

### 3.5. Tạo document suggestion từ domain model

Ví dụ mapper:

~~~java
public ProductSuggestionDocument toSuggestion(Product product) {
    ProductSuggestionDocument document =
        new ProductSuggestionDocument();

    document.setId(product.getId());
    document.setProductName(product.getName());

    Completion completion = new Completion(
        List.of(
            product.getName(),
            product.getSearchAlias()
        )
    );
    completion.setWeight(product.getPopularityWeight());

    document.setSuggest(completion);
    return document;
}
~~~

Đây là ví dụ cấu trúc. Trong production, bỏ alias null/rỗng và loại duplicate input trước khi index. Dữ liệu suggestion nên được cập nhật cùng projection khi tên hoặc alias nguồn thay đổi.

## 4. Query completion suggester qua NativeQuery

### 4.1. Xây Suggester bằng Elasticsearch Java API Client

NativeQueryBuilder có phương thức **withSuggester** nhận Suggester từ Elasticsearch Java API Client.

Ví dụ completion query:

~~~java
import co.elastic.clients.elasticsearch._types.SuggestMode;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Suggester suggester = Suggester.of(s -> s
    .suggesters("product-completion", field -> field
        .prefix(prefix)
        .completion(completion -> completion
            .field("suggest")
            .size(10)
            .skipDuplicates(true)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();

SearchHits<ProductSuggestionDocument> hits =
    operations.search(query, ProductSuggestionDocument.class);
~~~

Tên builder method và kiểu generated có thể thay đổi theo Elasticsearch Java API Client version. Nếu import hoặc overload không khớp, kiểm tra Javadoc của client được Spring Data release train quản lý. Không thay client dependency riêng chỉ để làm ví dụ compile.

### 4.2. Prefix và số lượng suggestion

Trong ví dụ:

- prefix là phần text người dùng đã nhập.
- field là tên completion field trong mapping.
- size giới hạn số suggestion.
- skipDuplicates loại các suggestion text trùng nhau trong response.

Giới hạn size ở mức nhỏ, thường chỉ vài đến một vài chục kết quả. Trả quá nhiều suggestion làm tăng payload và khó chọn trên UI.

### 4.3. Đọc suggestion từ SearchHits

Spring Data trả suggest response trong **SearchHits.getSuggest()**:

~~~java
Suggest suggest = hits.getSuggest();

if (suggest != null) {
    Suggest.Suggestion<?> suggestion =
        suggest.getSuggestion("product-completion");

    if (suggestion != null) {
        for (var entry : suggestion.getEntries()) {
            for (var option : entry.getOptions()) {
                String text = option.getText();
                Double score = option.getScore();
                // Map text and score to an API response DTO.
            }
        }
    }
}
~~~

Suggestion response khác với danh sách document hits. Một search có thể trả hits, suggestions hoặc cả hai tùy request. Hãy kiểm tra null và tên suggestion khi parse.

### 4.4. Trả DTO nhỏ cho frontend

Không cần trả toàn bộ entity chỉ để hiển thị gợi ý. Một DTO có thể gồm:

~~~java
public record SearchSuggestion(
    String id,
    String text,
    String type,
    double score
) {
}
~~~

Có thể lấy document ID từ completion option nếu response có search hit gắn với option theo phiên bản. Nếu chỉ cần text, trả text và loại suggestion. Khi người dùng chọn, frontend gửi ID hoặc text đã chọn tới search endpoint.

## 5. Fuzzy completion để chịu lỗi gõ

### 5.1. Fuzzy completion là gì?

Completion suggester có fuzzy option để chấp nhận một số sai khác trong prefix. Ví dụ người dùng nhập:

~~~text
wirless key
~~~

Fuzzy completion có thể gợi ý Wireless Keyboard nếu prefix đủ dài và các fuzzy settings cho phép.

### 5.2. Ví dụ fuzzy completion qua NativeQuery

~~~java
Suggester suggester = Suggester.of(s -> s
    .suggesters("product-completion", field -> field
        .prefix(prefix)
        .completion(completion -> completion
            .field("suggest")
            .size(8)
            .skipDuplicates(true)
            .fuzzy(fuzzy -> fuzzy)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
~~~

Đoạn code bật fuzzy options mặc định của client/server. Nếu cần tinh chỉnh, các thuộc tính phổ biến gồm fuzziness, transpositions, min_length và prefix_length. Tên enum/kiểu builder cụ thể phụ thuộc client version.

### 5.3. Giới hạn fuzzy để tránh suggestion nhiễu

Fuzzy có thể tăng candidate và chi phí. Nên:

- Chỉ bật sau khi prefix đủ dài.
- Giữ một phần prefix đầu phải khớp.
- Giới hạn edit distance.
- Giới hạn số suggestion.
- Không fuzzy với mã định danh cần exact match.
- So sánh kết quả fuzzy với exact completion trước khi hiển thị.

Không nên sửa một input ngắn như “a” hoặc “ip” bằng fuzzy vì có quá nhiều cách diễn giải.

### 5.4. Transposition

Fuzzy completion có thể coi việc đảo hai ký tự liền nhau là một lỗi tùy thiết lập transpositions.

Ví dụ:

~~~text
keybaord -> keyboard
~~~

Điều này hữu ích với lỗi gõ phổ biến. Tuy nhiên, fuzzy không hiểu ngữ nghĩa; nó chỉ tìm chuỗi gần theo edit distance.

## 6. search_as_you_type cho nhiều từ

### 6.1. Mapping

Spring Data có FieldType.Search_As_You_Type:

~~~java
@Document(indexName = "catalog-suggest-v1")
public class CatalogSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Search_As_You_Type)
    private String name;

    @Field(type = FieldType.Keyword)
    private String categoryId;
}
~~~

Elasticsearch tạo các subfield cho shingles và prefix. Mapping JSON tương đương:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "search_as_you_type",
        "max_shingle_size": 3
      },
      "categoryId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Subfield thường có dạng name._2gram, name._3gram và name._index_prefix. Không cần khai báo từng subfield trong entity.

### 6.2. Query bool_prefix

Cách query phổ biến là multi_match với type bool_prefix:

~~~json
{
  "query": {
    "multi_match": {
      "query": "wireless key",
      "type": "bool_prefix",
      "fields": [
        "name",
        "name._2gram",
        "name._3gram"
      ]
    }
  }
}
~~~

Các từ có thể khớp ở nhiều vị trí; shingle subfield giúp xếp hạng cao hơn khi các từ xuất hiện đúng thứ tự.

### 6.3. NativeQuery với bool_prefix

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .multiMatch(m -> m
            .query(prefix)
            .type(TextQueryType.BoolPrefix)
            .fields(
                "name",
                "name._2gram",
                "name._3gram"
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<CatalogSearchDocument> hits =
    operations.search(query, CatalogSearchDocument.class);
~~~

Enum và builder type cần khớp phiên bản Elasticsearch Java API Client. Nếu code không compile, kiểm tra generated API docs thay vì đổi query semantics một cách ngẫu nhiên.

### 6.4. Prefix và infix

search_as_you_type hỗ trợ prefix completion và infix completion trong field text. Điều này hữu ích khi người dùng gõ các từ theo thứ tự khác nhau hoặc bắt đầu từ một từ giữa tên.

Ví dụ document:

~~~text
The Quick Brown Fox
~~~

Query có thể bắt đầu bằng:

~~~text
brown f
~~~

Nếu cần cụm từ đúng thứ tự, dùng match_phrase_prefix hoặc match_phrase theo semantics phù hợp. Phrase-prefix có thể bị giới hạn bởi max_expansions và không phải lúc nào cũng là lựa chọn autocomplete tốt nhất.

### 6.5. search_as_you_type không tự sửa typo

Nếu người dùng nhập "wireles keybord", bool_prefix không tự hiểu rằng họ muốn "wireless keyboard". Cần kết hợp fuzzy query hoặc suggester riêng cho spell correction.

Không bật fuzzy trên mọi query theo mặc định vì có thể làm search rộng và giảm độ chính xác.

## 7. Edge n-gram analyzer

### 7.1. Khi cần kiểm soát prefix indexing

Edge n-gram hữu ích khi muốn tự kiểm soát độ dài prefix, analyzer hoặc field dùng cho autocomplete.

Ví dụ settings:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "autocomplete_edge": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 20
        }
      },
      "analyzer": {
        "autocomplete_index": {
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "autocomplete_edge"
          ]
        },
        "autocomplete_search": {
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "nameAutocomplete": {
        "type": "text",
        "analyzer": "autocomplete_index",
        "search_analyzer": "autocomplete_search"
      }
    }
  }
}
~~~

### 7.2. Vì sao search analyzer khác index analyzer?

Index analyzer tạo nhiều prefix token. Search analyzer chỉ tạo token bình thường từ input để khớp các prefix đã index.

Nếu dùng edge n-gram analyzer cả ở query time, một input ngắn có thể tạo ra nhiều token ngoài ý muốn và làm query semantics thay đổi.

### 7.3. Chi phí của edge n-gram

Giá trị min_gram và max_gram ảnh hưởng số token:

- min_gram quá thấp tạo nhiều prefix ngắn và nhiều false positive.
- max_gram quá cao tăng kích thước index.
- Query input dài hơn max_gram có thể không được xử lý như mong đợi.
- Mỗi thay đổi analyzer thường cần index mới và reindex dữ liệu.

Đo kích thước index và latency trước khi áp dụng cho nhiều field.

## 8. Term suggester cho lỗi chính tả từng từ

### 8.1. Term suggester hoạt động thế nào?

Term suggester đề xuất từ thay thế dựa trên edit distance và thống kê term trong field. Input được analyze thành token; suggestion được đưa ra cho từng token.

Ví dụ:

~~~text
Input: "wirless keybord"
Suggestions:
- wirless -> wireless
- keybord -> keyboard
~~~

Term suggester không xét query chính trong request và không hiểu đầy đủ ngữ cảnh cả câu. Nó phù hợp cho gợi ý từ thay thế riêng lẻ.

### 8.2. Query term suggester

Ví dụ Query DSL:

~~~json
{
  "suggest": {
    "text": "wirless keybord",
    "spellcheck": {
      "term": {
        "field": "name",
        "suggest_mode": "missing",
        "max_edits": 2,
        "prefix_length": 1,
        "min_word_length": 4,
        "size": 3
      }
    }
  }
}
~~~

Các tham số:

- field: field lấy vocabulary.
- suggest_mode: missing, popular hoặc always.
- max_edits: edit distance tối đa, thường 1 hoặc 2.
- prefix_length: số ký tự đầu phải khớp.
- min_word_length: bỏ qua token quá ngắn.
- size: số candidate cho mỗi token.

### 8.3. suggest_mode

| Mode | Hành vi |
|---|---|
| missing | Chỉ gợi ý khi token gốc không có trong index |
| popular | Ưu tiên candidate xuất hiện trong nhiều document hơn token gốc |
| always | Luôn tạo candidate phù hợp theo edit distance |

Mode missing thường phù hợp cho spell correction cơ bản. Popular có thể hữu ích khi token có trong index nhưng từ phổ biến hơn mới là lựa chọn đúng. Always tạo nhiều gợi ý hơn nhưng dễ nhiễu.

### 8.4. Hạn chế của term suggester

Term suggester sửa từng token độc lập. Nó có thể đề xuất một từ có edit distance gần nhưng không phù hợp ngữ cảnh.

Ví dụ một từ viết đúng trong tên riêng hoặc mã sản phẩm có thể bị xem như typo. Chỉ chạy suggester trên field vocabulary phù hợp và kiểm tra candidate trước khi đề xuất cho người dùng.

## 9. Phrase suggester cho sửa cả cụm từ

### 9.1. Vì sao cần phrase suggester?

Phrase suggester xây candidate từ term alternatives rồi xếp hạng cả cụm bằng mô hình n-gram. Nó có thể chọn từ dựa trên các từ xuất hiện cùng nhau trong dữ liệu.

Ví dụ:

~~~text
Input: "noble prize"
Suggested phrase: "nobel prize"
~~~

Một candidate có thể có edit distance tốt nhưng không tạo thành cụm từ phổ biến. Phrase suggester dùng thông tin đồng xuất hiện để cải thiện lựa chọn.

### 9.2. Cần mapping hỗ trợ n-gram

Phrase suggester thường cần field được index với shingle/ngram analyzer. Ví dụ mapping:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "trigram_filter": {
          "type": "shingle",
          "min_shingle_size": 2,
          "max_shingle_size": 3,
          "output_unigrams": true
        }
      },
      "analyzer": {
        "trigram_analyzer": {
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "trigram_filter"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "trigram": {
            "type": "text",
            "analyzer": "trigram_analyzer"
          }
        }
      }
    }
  }
}
~~~

### 9.3. Phrase suggester request

~~~json
{
  "suggest": {
    "text": "wirless keybord",
    "phrase-correction": {
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "gram_size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "missing",
            "max_edits": 2,
            "prefix_length": 1
          }
        ],
        "highlight": {
          "pre_tag": "<em>",
          "post_tag": "</em>"
        }
      }
    }
  }
}
~~~

Phrase suggester có thể sử dụng smoothing model như stupid_backoff, laplace hoặc linear_interpolation. Chọn theo dữ liệu và đánh giá candidate ranking.

### 9.4. Collate để kiểm tra phrase có kết quả

Phrase suggester có thể dùng collate query để kiểm tra candidate phrase có match document nào không. Điều này hữu ích khi chỉ muốn đề xuất cụm từ có khả năng trả kết quả.

Collate query làm thêm công việc cho mỗi candidate, vì vậy giới hạn số candidate và kiểm tra hiệu năng. Không xem collate như một cơ chế authorization.

## 10. NativeQuery và suggester response trong Spring Data

### 10.1. Đặt suggester vào NativeQuery

NativeQueryBuilder có phương thức withSuggester nhận Suggester của Elasticsearch Java API Client.

Ví dụ cấu trúc completion suggester:

~~~java
Suggester suggester = Suggester.of(s -> s
    .suggesters("spellcheck", field -> field
        .text(input)
        .term(term -> term
            .field("name")
            .size(3)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Đây là mẫu builder của ELC client. Nếu generated method hoặc overload khác trong dependency hiện tại, kiểm tra Javadoc đúng client version. Có thể dùng raw Query/Suggester model của Java API Client khi Spring Data abstraction chưa expose option cần thiết.

### 10.2. Lấy suggestion từ SearchHits

Spring Data trả suggest response qua SearchHits:

~~~java
Suggest suggest = hits.getSuggest();

if (suggest != null) {
    var result = suggest.getSuggestion("spellcheck");

    if (result != null) {
        for (var entry : result.getEntries()) {
            for (var option : entry.getOptions()) {
                String candidate = option.getText();
                Double score = option.getScore();
            }
        }
    }
}
~~~

Các kiểu response cụ thể gồm CompletionSuggestion, TermSuggestion và PhraseSuggestion. Dùng tên suggestion đã khai báo trong request để lấy đúng kết quả.

### 10.3. Search và suggest có thể cùng request

Search API cho phép gửi query và suggest trong cùng một request. Khi đó ứng dụng có thể:

- Trả kết quả search hiện tại.
- Trả suggestion autocomplete hoặc correction.
- Chỉ hiển thị correction khi số hit thấp.
- Hiển thị cả kết quả và “Did you mean?” nếu phù hợp.

Nếu chỉ cần suggestion, có thể gửi request chỉ có suggest. Không cần chạy thêm match_all hoặc query giả để lấy kết quả.

### 10.4. Reactive API

ReactiveSearchOperations cũng hỗ trợ query có suggest response theo version. Có thể lấy ReactiveSearchHits hoặc Suggest từ kết quả reactive theo interface hiện hành.

Giữ pipeline reactive và tránh block trong request path. Nếu endpoint chỉ trả suggestion list, map response thành Flux/Mono DTO nhỏ.

## 11. Context suggester cho category, tenant và loại dữ liệu

### 11.1. Vì sao cần context?

Completion suggester mặc định xét toàn bộ document trong index. Một ứng dụng có thể cần gợi ý theo:

- Category.
- Brand.
- Tenant.
- Loại thực thể.
- Ngôn ngữ.
- Khu vực.

Elasticsearch hỗ trợ context mappings cho completion field, gồm category và geo contexts.

### 11.2. Khai báo context mapping

Spring Data có annotation CompletionContext dùng cùng CompletionField. Ví dụ khái niệm:

~~~java
@CompletionField(
    contexts = {
        @CompletionContext(
            name = "category",
            type = CompletionContext.ContextMappingType.CATEGORY
        )
    }
)
private Completion suggest;
~~~

Tên enum/annotation attributes cần khớp Spring Data release. Context mapping phải được tạo trong index mapping trước khi index completion inputs.

### 11.3. Ghi context cùng suggestion

Completion object có thể mang context:

~~~java
Completion completion =
    new Completion(List.of("Wireless Keyboard"));

completion.setContexts(
    Map.of("category", List.of("computer-accessories"))
);

document.setSuggest(completion);
~~~

Context-enabled completion field yêu cầu context tương ứng khi index và khi query. Nếu thiếu context, request có thể bị từ chối hoặc không trả kết quả mong muốn.

### 11.4. Context không thay thế authorization

Context giúp filter/boost suggestion theo metadata. Nó không thay thế kiểm tra quyền ở service hoặc Elasticsearch security.

Nếu tenant là ranh giới bảo mật, tenant context phải được tạo từ principal đã xác thực. Không nhận tenant context tùy ý từ query string mà không kiểm tra quyền.

## 12. Xây dựng search API cho autocomplete

### 12.1. Giới hạn input

Trước khi gọi Elasticsearch:

- Trim khoảng trắng.
- Chuẩn hóa Unicode theo quy tắc sản phẩm.
- Giới hạn độ dài input.
- Bỏ query rỗng hoặc quá ngắn.
- Giới hạn số kết quả.
- Áp dụng rate limit phù hợp.

Không gửi request với mỗi ký tự mà không debounce ở frontend hoặc throttle ở API gateway.

### 12.2. Debounce ở frontend

Ví dụ UX:

- Người dùng nhập ký tự.
- Đợi khoảng 150-300 ms sau lần gõ cuối.
- Gửi request autocomplete.
- Hủy request cũ nếu query mới được gửi.
- Chỉ hiển thị response mới nhất.

Khoảng debounce cần điều chỉnh theo latency, thiết bị và trải nghiệm. Không hardcode một giá trị mà không đo.

### 12.3. Service Spring

Một service có thể nhận prefix, xây query và chuyển suggestion response thành DTO:

~~~java
public List<String> suggestProducts(String prefix) {
    if (prefix == null || prefix.trim().length() < 2) {
        return List.of();
    }

    Suggester suggester = Suggester.of(s -> s
        .suggesters("product-completion", field -> field
            .prefix(prefix.trim())
            .completion(completion -> completion
                .field("suggest")
                .size(8)
                .skipDuplicates(true)
            )
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withSuggester(suggester)
        .build();

    SearchHits<ProductSuggestionDocument> hits =
        operations.search(query, ProductSuggestionDocument.class);

    Suggest suggest = hits.getSuggest();
    if (suggest == null) {
        return List.of();
    }

    var result = suggest.getSuggestion("product-completion");
    if (result == null) {
        return List.of();
    }

    return result.getEntries().stream()
        .flatMap(entry -> entry.getOptions().stream())
        .map(option -> option.getText())
        .distinct()
        .limit(8)
        .toList();
}
~~~

Đây là ví dụ cho Spring Data/ELC hiện đại. Các import và builder overload phải được kiểm tra theo version dependency. Ứng dụng thực tế nên trả DTO có ID, label và loại suggestion thay vì chỉ chuỗi.

### 12.4. Không trả kết quả vượt quyền

Nếu suggestion lấy từ catalog có nhiều tenant hoặc trạng thái visibility, áp dụng context/filter tương ứng và kiểm tra authorization ở service. Gợi ý có thể làm lộ tên document ngay cả khi search endpoint sau đó từ chối mở document.

### 12.5. Cache có giới hạn

Prefix phổ biến có thể được cache trong thời gian ngắn. Cache key cần bao gồm tenant, language, category hoặc context liên quan để không trả gợi ý từ phạm vi khác.

Đặt TTL ngắn nếu catalog thay đổi thường xuyên. Không cache response có dữ liệu nhạy cảm vào shared cache thiếu isolation.

## 13. Xây dựng spell correction flow

### 13.1. Không chạy correction cho mọi truy vấn

Một chiến lược hợp lý:

1. Chạy search bình thường với query gốc.
2. Nếu có đủ kết quả phù hợp, trả kết quả.
3. Nếu không có hit hoặc chất lượng thấp, chạy term/phrase suggester.
4. Chọn candidate có relevance tốt.
5. Kiểm tra candidate có tạo ra kết quả search không.
6. Trả gợi ý để người dùng xác nhận hoặc cung cấp kết quả thay thế có nhãn rõ ràng.

Cách này tránh thêm chi phí correction cho mọi query.

### 13.2. Chỉ sửa những field phù hợp

Dùng field text chứa vocabulary tự nhiên, ví dụ product name hoặc title. Không dùng field mã định danh, SKU, số điện thoại hoặc chuỗi kỹ thuật làm từ điển chính tả.

Một từ lạ có thể là tên riêng, thương hiệu hoặc mã sản phẩm hợp lệ. Spell correction không nên tự sửa các giá trị exact-match quan trọng.

### 13.3. Ngưỡng hiển thị correction

Có thể đặt các điều kiện:

- Query có độ dài tối thiểu.
- Search gốc có ít hơn một số hit nhất định.
- Candidate score vượt ngưỡng đã đánh giá.
- Candidate khác query gốc đủ rõ.
- Candidate sau correction trả được kết quả có ý nghĩa.

Không lấy một score threshold tùy ý rồi coi là xác suất đúng. Calibrate bằng dữ liệu truy vấn thực tế.

### 13.4. Giữ nguyên query gốc

Response API có thể gồm:

~~~json
{
  "query": "wirless keybord",
  "suggestedQuery": "wireless keyboard",
  "correctionApplied": false,
  "results": []
}
~~~

Nếu người dùng chọn suggestion, ghi nhận query được chọn để phục vụ analytics. Nếu ứng dụng tự áp dụng correction, vẫn nên hiển thị rõ truy vấn đã sửa và cho phép quay lại query gốc.

### 13.5. Từ điển và synonym

Synonym khác spell correction:

- Synonym mở rộng các từ có quan hệ cùng nghĩa hoặc cách gọi.
- Spell correction sửa chuỗi có khả năng gõ sai.
- Alias là tên thay thế có chủ đích của một thực thể.

Ví dụ "laptop" và "notebook" có thể là synonym; "keybord" là typo; "ThinkPad" là brand/model alias. Không gộp mọi loại vào một cơ chế vì ranking và maintenance khác nhau.

## 14. Ngôn ngữ, Unicode và tiếng Việt

### 14.1. Chuẩn hóa Unicode

Cùng một ký tự có thể được biểu diễn bằng dạng Unicode tổ hợp khác nhau. Nếu indexing và query không normalize nhất quán, người dùng có thể không tìm thấy nội dung dù nhìn thấy giống nhau.

Xác định normalization form và áp dụng đồng bộ trước khi index và search. Không tự xóa dấu tiếng Việt nếu nghiệp vụ cần phân biệt nội dung có dấu.

### 14.2. Có dấu và không dấu

Với tiếng Việt, người dùng có thể nhập không dấu. Một số chiến lược:

- Index thêm alias không dấu.
- Tạo subfield normalized bằng analyzer phù hợp.
- Tạo suggestion input có dấu và không dấu.
- Dùng một service normalization có kiểm thử ngôn ngữ.

Lowercase filter không loại bỏ dấu. Cần dùng character filter/asciifolding phù hợp và kiểm tra tác động với tên riêng.

### 14.3. Tokenization

Term và phrase suggester phụ thuộc analyzer. Analyzer không phù hợp có thể tách từ tiếng Việt sai, làm candidate spelling correction kém.

Đánh giá analyzer trên corpus tiếng Việt thực tế. Với nội dung đa ngôn ngữ, có thể tách field theo language hoặc chọn analyzer theo ngôn ngữ document.

### 14.4. Không fuzzy mã và số

Fuzzy search trên SKU hoặc model number có thể tạo candidate gần về ký tự nhưng sai thực thể.

Dùng exact keyword matching cho identifier. Chỉ bật fuzzy cho tên tự nhiên hoặc field được xác định là phù hợp.

## 15. Ranking suggestion

### 15.1. Weight trong completion field

Completion input có thể gắn weight để ưu tiên gợi ý phổ biến hoặc quan trọng.

Weight có thể được tính từ:

- Popularity.
- Click-through rate.
- Sales hoặc conversion.
- Trạng thái đang hoạt động.
- Mức độ ưu tiên nghiệp vụ.
- Recency, nếu use case cần.

Không dùng một metric duy nhất nếu nó tạo feedback loop khiến các kết quả đã phổ biến luôn chiếm vị trí đầu.

### 15.2. Deduplication

Một product có thể có nhiều alias tạo cùng suggestion text. Dùng skip_duplicates hoặc deduplicate ở application layer.

Cần quyết định có gộp các document trùng label hay không. Nếu hai sản phẩm cùng tên nhưng khác category, có thể hiển thị label phụ như brand hoặc category để phân biệt.

### 15.3. Ranking theo ngữ cảnh

Có thể boost suggestion theo category hoặc geo context. Ví dụ query trong trang điện thoại có thể ưu tiên phụ kiện điện thoại.

Context nên phản ánh ngữ cảnh đã được xác thực hoặc được lấy từ route/application state đáng tin cậy.

### 15.4. Không đánh đồng score giữa các suggester

Completion weight, term suggestion score và phrase suggestion score có semantics khác nhau. Không sort chung các kết quả từ nhiều suggester bằng cách so sánh raw score mà chưa chuẩn hóa.

Nếu gộp nhiều nguồn, tạo ranking layer riêng dựa trên thứ hạng, business priority và relevance evaluation.

## 16. Phiên bản Spring Data và Elasticsearch client

### 16.1. NativeQuery và Java API Client

Spring Data Elasticsearch hiện đại dùng NativeQuery với Elasticsearch Java API Client. NativeQueryBuilder có withSuggester nhận Suggester từ client.

Các ví dụ cũ có thể sử dụng NativeSearchQuery, SuggestBuilder của RestHighLevelClient hoặc các class thuộc package org.elasticsearch. Đừng trộn các class này với ELC client.

### 16.2. SearchHits suggest response

Spring Data có SearchHits.getSuggest() và các response type CompletionSuggestion, TermSuggestion, PhraseSuggestion từ phiên bản 4.3. API SearchOperations.search(Query, Class) có thể trả cả hits và suggest metadata.

Một số suggest methods cũ nhận SearchResponse trực tiếp đã được deprecated trong các release trước. Ưu tiên search(Query, Class) và đọc getSuggest() theo contract của release đang dùng.

### 16.3. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch,co.elastic.clients:elasticsearch-java,org.elasticsearch.client:*
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration runtimeClasspath
~~~

Dùng dependency management của Spring Boot/Spring Data để chọn client version. Không override client version riêng chỉ để copy một builder method từ tài liệu khác.

### 16.4. Khi builder không hỗ trợ option cần dùng

Có thể gọi Elasticsearch Java API Client trực tiếp với Suggester hoặc SearchRequest. Dùng client đã được Spring cấu hình để giữ endpoint, TLS và credential nhất quán.

Khi gọi client trực tiếp, response được deserialize qua JsonpMapper của transport; không giả định custom Spring Data converters tự động được áp dụng. Nếu cần mapping domain phức tạp, tạo DTO hoặc adapter riêng.

### 16.5. Server version cũng quyết định tính năng

Completion, search_as_you_type, fuzzy options, contexts và suggester parameters có thể có khác biệt theo Elasticsearch server version. Kiểm tra reference của đúng server major/minor và chạy integration test với version tương thích.

## 17. Kiểm thử autocomplete và spell correction

### 17.1. Unit test cho normalization và mapping

Kiểm tra:

- Prefix được trim và normalize.
- Alias rỗng/null bị loại.
- Duplicate input được gộp.
- Weight nằm trong phạm vi hợp lệ.
- Ngôn ngữ và tenant context được gắn đúng.
- Query quá ngắn không gọi Elasticsearch.

### 17.2. Integration test completion suggester

Dùng Elasticsearch thật qua Testcontainers:

1. Tạo index với completion mapping.
2. Index một số document có input và weight khác nhau.
3. Refresh index.
4. Query prefix.
5. Xác nhận suggestion text và thứ tự.
6. Bật skip_duplicates và xác nhận kết quả trùng được lọc.
7. Test fuzzy prefix với typo có chủ đích.

Không chỉ mock Suggester response nếu cần xác nhận mapping và fuzzy behavior.

### 17.3. Integration test search_as_you_type

Tạo document với nhiều từ, query prefix một từ và nhiều từ. Xác nhận:

- Prefix ở đầu.
- Infix ở giữa.
- Bool-prefix query.
- Filter category/tenant.
- Kết quả xếp hạng khi từ xuất hiện đúng thứ tự.

### 17.4. Test term và phrase suggester

Tạo vocabulary có các cặp từ gần nhau và phrase xuất hiện đủ thường xuyên. Test:

- suggest_mode missing.
- popular/always khi phù hợp.
- max_edits và prefix_length.
- Phrase n-gram field.
- Collate candidate nếu sử dụng.

Đánh giá trên một tập typo thực tế, không chỉ một ví dụ cố định.

### 17.5. Đánh giá chất lượng

Theo dõi:

- Suggestion acceptance rate.
- Click-through rate.
- Search success sau khi chọn suggestion.
- Correction acceptance rate.
- False correction rate.
- Empty suggestion rate.
- Latency p50/p95/p99.
- Query count theo prefix length.

Không tối ưu chỉ theo click vì suggestion phổ biến có thể nhận nhiều click nhưng không giúp người dùng hoàn thành tác vụ.

## 18. Vận hành và hiệu năng

### 18.1. Giới hạn số kết quả

Autocomplete thường chỉ cần một danh sách ngắn. Giữ size thấp và tránh trả cả document lớn.

### 18.2. Completion structure tiêu thụ memory

Completion suggester tối ưu tốc độ và lưu cấu trúc dữ liệu trong memory. Theo dõi heap, shard size và số lượng input được index.

Với index lớn, đánh giá shard strategy; completion query trên nhiều shard có thêm giai đoạn lấy kết quả từ shard. Một shard có thể nhanh hơn trong một số use case, nhưng không nên gộp toàn bộ dữ liệu vào một shard nếu heap hoặc scale yêu cầu chia nhỏ.

### 18.3. Search-as-you-type tăng số subfield

search_as_you_type tạo thêm shingle và prefix subfield. max_shingle_size cao hơn tăng khả năng match cụ thể nhưng cũng tăng index size.

Dùng mặc định trước, chỉ tăng shingle size khi relevance test cho thấy cần thiết.

### 18.4. Rate limit và chống lạm dụng

Autocomplete endpoint có thể nhận request liên tục. Dùng debounce, rate limit, giới hạn input size và response size.

Không cho client gửi arbitrary analyzer, field hoặc suggester configuration.

### 18.5. Observability

Theo dõi:

- Số request autocomplete.
- Completion/term/phrase suggester latency.
- Số suggestion trả về.
- Tỷ lệ empty result.
- Fuzzy correction rate.
- Query error theo mapping/version.
- Memory và search load.
- Tỷ lệ người dùng chọn suggestion.

Không log nguyên query nếu có thể chứa thông tin nhạy cảm; dùng sampling hoặc redaction phù hợp.

## 19. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Completion query không trả gì | Field chưa mapping completion hoặc index chưa refresh | Kiểm tra mapping, document và refresh |
| @CompletionField không tạo mapping như mong muốn | Sai field type hoặc dependency version | Kiểm tra Spring Data annotation và mapping thực tế |
| withSuggester không compile | NativeQuery/client API không khớp version | Kiểm tra dependency tree và Javadoc |
| Gợi ý bị trùng | Nhiều document/alias có cùng text | Dùng skip_duplicates hoặc deduplicate |
| Fuzzy trả quá nhiều kết quả | Prefix quá ngắn hoặc edit distance quá rộng | Tăng min length/prefix length, giảm size |
| Completion không tìm thấy từ giữa chuỗi | Completion chủ yếu phục vụ prefix | Dùng search_as_you_type hoặc field/index khác |
| search_as_you_type bỏ lỡ typo | Bool-prefix không phải spell correction | Kết hợp fuzzy hoặc term/phrase suggester |
| Phrase suggester không hoạt động tốt | Thiếu shingle/ngram mapping | Tạo field trigram và reindex |
| Term suggester sửa sai tên riêng | Từ điển không có ngữ cảnh phrase | Dùng phrase suggester hoặc loại field khỏi correction |
| Suggestion tenant khác xuất hiện | Không áp dụng context/filter phù hợp | Gắn context đã xác thực và kiểm tra authorization |
| Không parse được suggest response | Đọc hits thay vì SearchHits.getSuggest | Lấy đúng Suggest theo tên đã khai báo |
| Search endpoint quá tải | Query mỗi phím, size lớn hoặc fuzzy quá rộng | Debounce, rate limit và giới hạn candidate |
| Suggestion không cập nhật sau đổi tên | Projection chưa đồng bộ | Cập nhật completion inputs theo event và kiểm tra refresh |
| Tiếng Việt không dấu không match | Lowercase không loại dấu | Thêm normalization/alias có kiểm thử |
| Mã sản phẩm bị sửa thành từ khác | Dùng fuzzy trên identifier | Dùng exact keyword matching |

## 20. Quy trình triển khai

Khi xây autocomplete và spell correction bằng Spring Data Elasticsearch:

1. Xác định UX: prefix suggestions, multi-term search-as-you-type hay did-you-mean.
2. Chọn completion, search_as_you_type, edge n-gram hoặc tổ hợp có lý do.
3. Thiết kế input/alias, weight và context cho suggestion.
4. Tạo mapping với @CompletionField hoặc Search_As_You_Type phù hợp.
5. Index input ổn định và loại duplicate.
6. Xây NativeQuery với Suggester từ Elasticsearch Java API Client.
7. Đọc response qua SearchHits.getSuggest() và map DTO.
8. Dùng fuzzy completion có giới hạn cho lỗi prefix.
9. Dùng term/phrase suggester cho correction theo token/cụm từ.
10. Áp dụng normalization theo ngôn ngữ, đặc biệt với Unicode và tiếng Việt.
11. Kiểm tra tenant/visibility trước khi trả suggestion.
12. Giới hạn prefix length, size, debounce và rate.
13. Chạy integration test với Elasticsearch server tương thích.
14. Đo acceptance, false correction, latency và resource usage.
15. Cập nhật projection khi tên, alias, popularity hoặc context thay đổi.

## 21. Những điểm cần ghi nhớ

- Autocomplete hoàn tất input; spell correction đề xuất cách viết khác. Hai mục tiêu cần cơ chế riêng.
- Completion suggester tối ưu prefix lookup và có thể dùng fuzzy options, nhưng không phải công cụ spell correction theo ngữ cảnh.
- search_as_you_type tạo các subfield shingle/prefix và thường được query bằng multi_match bool_prefix.
- Edge n-gram cho phép kiểm soát prefix indexing nhưng tăng số token và dung lượng index.
- Spring Data có @CompletionField và Completion để ánh xạ input, weight và context.
- NativeQueryBuilder.withSuggester nhận Suggester của Elasticsearch Java API Client.
- SearchHits.getSuggest() chứa suggestion response; nó khác danh sách document hits.
- Term suggester sửa token theo edit distance và không xét query context.
- Phrase suggester xếp hạng cả cụm bằng n-gram co-occurrence và thường cần mapping shingle.
- Completion fuzzy cần prefix đủ dài và giới hạn edit distance để tránh nhiễu.
- Context suggester giúp filter/boost nhưng không thay thế authorization.
- Với tiếng Việt, cần kiểm thử Unicode normalization và tìm kiếm có/không dấu.
- Không fuzzy SKU hoặc identifier cần exact match.
- Dùng debounce, giới hạn size và rate limit cho autocomplete endpoint.
- Theo dõi acceptance rate, false correction, latency và memory.
- Kiểm tra Spring Data và Elasticsearch client version trước khi copy NativeQuery builder code.

Một trải nghiệm tìm kiếm tốt thường dùng completion để giúp người dùng chọn nhanh, search_as_you_type để tìm theo nhiều từ và phrase/term suggester để xử lý typo khi cần. Khi chọn đúng cơ chế, kiểm soát mapping và giới hạn fuzzy, Spring Data Elasticsearch có thể cung cấp gợi ý nhanh mà vẫn giữ được độ chính xác và quyền truy cập của kết quả.

