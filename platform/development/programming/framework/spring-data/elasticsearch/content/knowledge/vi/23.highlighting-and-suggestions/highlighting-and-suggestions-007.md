# Phân biệt tự động hoàn thành, gợi ý chính tả và tìm kiếm tiền tố

Trong một ô tìm kiếm, người dùng có thể nhận được ba loại kết quả trông khá giống nhau nhưng thực chất giải quyết ba vấn đề khác nhau:

- **Tự động hoàn thành (autocomplete):** đề xuất các cụm từ hoặc mục dữ liệu có thể chọn khi người dùng mới nhập một phần từ khóa, ví dụ nhập `iph` và nhận `iPhone 16`.
- **Gợi ý chính tả (spell suggestion):** đề xuất cách viết có khả năng đúng khi người dùng gõ sai, ví dụ `wireles hedphones` và nhận `wireless headphones`.
- **Tìm kiếm tiền tố (prefix search):** tìm các document có từ hoặc giá trị bắt đầu bằng chuỗi người dùng đã nhập, ví dụ `iph` khớp `iPhone`.

Ba chức năng có thể cùng xuất hiện trên một trang tìm kiếm, nhưng không nên coi chúng là một cơ chế. Trong Elasticsearch, autocomplete thường dùng Completion Suggester hoặc `search_as_you_type`; spelling suggestion dùng Term Suggester hoặc Phrase Suggester; prefix search dùng Prefix Query, `match_bool_prefix`, `index_prefixes` hoặc edge n-gram tùy cấu trúc dữ liệu và yêu cầu xếp hạng.

## 1. So sánh nhanh ba khái niệm

| Tiêu chí | Tự động hoàn thành | Gợi ý chính tả | Tìm kiếm tiền tố |
|---|---|---|---|
| Câu hỏi cần giải quyết | Người dùng có thể muốn nhập tiếp nội dung nào? | Người dùng có thể đã viết sai từ nào? | Document nào có từ bắt đầu bằng chuỗi đã nhập? |
| Input điển hình | Prefix đang nhập: `iph` | Từ/cụm từ có thể sai: `iphnoe` | Prefix cần tìm: `iph` |
| Output | Danh sách lựa chọn hoàn chỉnh | Candidate thay thế hoặc cụm từ sửa | Các document khớp điều kiện prefix |
| Cơ chế thường dùng | Completion Suggester, `search_as_you_type`, edge n-gram | Term/Phrase Suggester | Prefix Query, `match_bool_prefix`, edge n-gram |
| Có cần document search hits không? | Không nhất thiết; suggester trả options riêng | Không nhất thiết; suggester trả options riêng | Có, vì mục tiêu là tìm document |
| Có tự sửa query không? | Không; chỉ đưa lựa chọn | Không tự thay query nếu ứng dụng chưa chấp nhận gợi ý | Không; chỉ tìm document theo prefix |
| Ví dụ UX | Dropdown “iPhone 16”, “iPhone 16 Pro” | “Có phải bạn muốn tìm wireless headphones?” | Hiển thị sản phẩm có tên bắt đầu bằng `iph` |

Ví dụ người dùng gõ `iphnoe`:

1. Prefix search theo đúng chuỗi `iphnoe` có thể không tìm thấy sản phẩm nào.
2. Spell suggester có thể đề xuất `iphone`.
3. Sau khi người dùng chọn `iphone`, autocomplete có thể đưa ra `iPhone 16`, `iPhone 16 Pro` hoặc `iPhone case`.

Trong một sản phẩm thực tế, có thể chạy spelling suggestion khi kết quả tìm kiếm quá ít hoặc bằng 0, autocomplete khi input thay đổi, và prefix search để truy xuất các document phù hợp với phần người dùng đang nhập.

## 2. Tự động hoàn thành với Completion Suggester

Completion Suggester được thiết kế riêng cho autocomplete. Elasticsearch lập chỉ mục các input trong một cấu trúc dữ liệu tối ưu cho việc tra cứu prefix. Khi người dùng nhập một prefix, suggester trả về các input hoàn chỉnh phù hợp.

Ví dụ danh sách input đã index:

```text
iPhone 16
iPhone 16 Pro
iPhone 16 Pro Max
iPhone case
Wireless headphones
Wireless keyboard
```

Khi nhận prefix `iph`, Completion Suggester có thể trả về các lựa chọn bắt đầu bằng prefix đó. Kết quả là suggestion options, không phải một danh sách document hits được tìm bằng query thông thường.

### Mapping kiểu `completion`

Field dùng Completion Suggester phải có mapping kiểu `completion`:

```http
PUT /products
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "suggest": {
        "type": "completion",
        "analyzer": "simple",
        "search_analyzer": "simple",
        "preserve_separators": true,
        "preserve_position_increments": true,
        "max_input_length": 100
      }
    }
  }
}
```

`completion` là field chuyên dụng, không thể thay bằng field `text` thông thường rồi mong Completion Suggester hoạt động. `analyzer` và `search_analyzer` quyết định cách chuẩn hóa input lúc index và lúc tìm gợi ý. `max_input_length` giới hạn độ dài mỗi input được index.

### Index các giá trị gợi ý

Một document có thể lưu nhiều input cho cùng một mục:

```http
PUT /products/_doc/p-1001
Content-Type: application/json

{
  "name": "Apple iPhone 16 Pro",
  "suggest": [
    "iPhone 16 Pro",
    "Apple iPhone 16 Pro",
    "iPhone Pro"
  ]
}
```

Completion field có thể nhận một chuỗi, một mảng chuỗi hoặc cấu trúc input có weight/context tùy cấu hình. Việc đưa nhiều cách gọi vào input giúp người dùng tìm thấy cùng một sản phẩm qua các cách bắt đầu khác nhau.

### Query autocomplete

```http
POST /products/_search
Content-Type: application/json

{
  "_source": ["name"],
  "suggest": {
    "product_autocomplete": {
      "prefix": "iph",
      "completion": {
        "field": "suggest",
        "size": 5,
        "skip_duplicates": true
      }
    }
  }
}
```

`prefix` là phần người dùng đang nhập; `size` giới hạn số suggestion; `skip_duplicates` loại bỏ các option trùng text. Response nằm trong `suggest.product_autocomplete`, mỗi option có thể chứa text, score và thông tin document liên quan.

### Ưu điểm và giới hạn

**Ưu điểm:** độ trễ thấp cho prefix lookup, phù hợp dropdown autocomplete, hỗ trợ weight và context completion.

**Giới hạn:** cần field `completion` riêng; input phải được chuẩn bị và index; không phải một full-text search engine thay thế query thông thường; không tự sửa lỗi chính tả; cấu trúc completion có chi phí bộ nhớ cần theo dõi.

## 3. Dùng Completion Suggester trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `@CompletionField` và kiểu `Completion` để ánh xạ field completion.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;

    @CompletionField(maxInputLength = 100)
    private Completion suggest;

    // Constructors, getters and setters
}
```

Khi tạo document:

```java
product.setSuggest(new Completion(new String[] {
    "iPhone 16 Pro",
    "Apple iPhone 16 Pro",
    "iPhone Pro"
}));
```

`NativeQuery` có thể chứa suggester được xây dựng bằng Elasticsearch Java API Client:

```java
import co.elastic.clients.elasticsearch.core.search.FieldSuggester;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Suggester suggester = Suggester.of(s -> s
    .suggesters("product_autocomplete", FieldSuggester.of(fs -> fs
        .prefix("iph")
        .completion(c -> c
            .field("suggest")
            .size(5)
            .skipDuplicates(true)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

Thực thi và đọc kết quả:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasSuggest()) {
    Suggest suggest = results.getSuggest();
    Suggest.Suggestion<?> completion =
        suggest.getSuggestion("product_autocomplete");

    if (completion != null) {
        for (Suggest.Suggestion.Entry<?> entry : completion.getEntries()) {
            for (Suggest.Suggestion.Entry.Option option : entry.getOptions()) {
                String text = option.getText();
                // Đưa text vào danh sách lựa chọn autocomplete.
            }
        }
    }
}
```

Các lớp builder của Elasticsearch Java API Client được sinh theo version client mà Spring Data đang dùng. Nếu tên method hoặc kiểu option khác trong dependency của dự án, hãy dùng API tương ứng với version đó; không trộn import từ `RestHighLevelClient` cũ với ELC.

## 4. Context Completion: autocomplete có phân loại

Context completion cho phép giới hạn hoặc tăng ưu tiên suggestion dựa trên context, ví dụ danh mục sản phẩm, tenant, ngôn ngữ hoặc vị trí.

Ví dụ người dùng nhập `iph` trong danh mục `phones`. Hệ thống muốn gợi ý điện thoại, không muốn đưa ra phụ kiện có prefix tương tự.

Mapping ví dụ:

```json
{
  "properties": {
    "suggest": {
      "type": "completion",
      "contexts": [
        {
          "name": "category",
          "type": "category"
        }
      ]
    }
  }
}
```

Index document có context:

```json
{
  "suggest": {
    "input": ["iPhone 16 Pro", "Apple iPhone 16 Pro"],
    "contexts": {
      "category": ["phones"]
    }
  }
}
```

Query chỉ lấy suggestion thuộc category `phones`:

```json
{
  "suggest": {
    "product_autocomplete": {
      "prefix": "iph",
      "completion": {
        "field": "suggest",
        "size": 5,
        "contexts": {
          "category": ["phones"]
        }
      }
    }
  }
}
```

Context cần được định nghĩa trong mapping và gửi nhất quán lúc index lẫn query. Context completion có thể lọc hoặc boost theo context; chọn hành vi phù hợp với mục tiêu. Nếu context không được index đúng, query có thể không trả kết quả dù prefix tồn tại.

## 5. Tự động hoàn thành bằng `search_as_you_type`

Completion Suggester không phải lựa chọn duy nhất cho autocomplete. Nếu muốn autocomplete dựa trên nội dung nhiều từ, có thể dùng field kiểu `search_as_you_type` kết hợp `multi_match` với `bool_prefix`.

`search_as_you_type` tạo các subfield hỗ trợ tìm kiếm theo thứ tự từ và prefix của từ cuối. Ví dụ mapping:

```http
PUT /products
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "search_as_you_type"
      }
    }
  }
}
```

Elasticsearch tự tạo các subfield như:

- `name`: field gốc.
- `name._2gram`: hỗ trợ các cụm hai token liền nhau.
- `name._3gram`: hỗ trợ các cụm ba token liền nhau.
- `name._index_prefix`: cấu trúc prefix được dùng cho truy vấn phù hợp.

Query:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "multi_match": {
      "query": "wireless head",
      "type": "bool_prefix",
      "fields": [
        "name",
        "name._2gram",
        "name._3gram"
      ]
    }
  }
}
```

`bool_prefix` tìm các token đã nhập theo kiểu match và xử lý token cuối như prefix. Nó phù hợp khi người dùng nhập nhiều từ, ví dụ `wireless head` và muốn tìm `Wireless Headphones`. Query vẫn trả document hits và có thể xếp hạng theo score.

### Khi nào chọn `search_as_you_type`?

- Tìm kiếm theo nhiều từ và thứ tự từ có ý nghĩa.
- Muốn có relevance score của document.
- Muốn tận dụng các subfield do Elasticsearch tạo ra.
- Cần trải nghiệm “search as you type” trên tiêu đề hoặc tên sản phẩm.

### Khi nào không chọn?

- Chỉ cần một danh sách gợi ý prefix rất nhanh và có weight/context: Completion Suggester thường phù hợp hơn.
- Cần spelling correction: dùng Term/Phrase Suggester.
- Cần so khớp nguyên chuỗi bắt đầu bằng prefix trên một mã: Prefix Query trên `keyword` có thể đơn giản hơn.

## 6. Tìm kiếm tiền tố bằng Prefix Query

Prefix Query tìm các term có giá trị bắt đầu bằng prefix được chỉ định. Nó phù hợp với mã, tên định danh hoặc field `keyword` cần so khớp theo tiền tố.

Ví dụ field `sku` có mapping `keyword`:

```json
{
  "properties": {
    "sku": {
      "type": "keyword"
    }
  }
}
```

Query tìm SKU bắt đầu bằng `IPH`:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "prefix": {
      "sku": {
        "value": "IPH"
      }
    }
  }
}
```

Nếu `sku` là `keyword`, phép tìm kiếm thường xét toàn bộ giá trị term. Nó phù hợp với mã sản phẩm, mã khách hàng hoặc định danh có quy tắc chuẩn hóa rõ ràng.

### Prefix Query không phải full-text query

Prefix Query không tự tách câu thành các từ như `match`. Nếu field là `text`, query làm việc trên term đã được analyzer tạo ra, chứ không so sánh nguyên chuỗi `_source`. Ví dụ, một prefix có thể khớp token cuối hoặc token đã phân tích tùy analyzer và dữ liệu index. Nếu muốn tìm theo nhiều từ với token cuối chưa hoàn chỉnh, `match_bool_prefix` hoặc `search_as_you_type` thường dễ kiểm soát hơn.

### Prefix Query trong Spring Data `NativeQuery`

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

String prefix = "IPH";

Query query = NativeQuery.builder()
    .withQuery(q -> q.prefix(p -> p
        .field("sku")
        .value(prefix)
    ))
    .build();
```

Thực thi bằng `ElasticsearchOperations.search(...)` để nhận `SearchHits<ProductDocument>`. Vì đây là query tìm document, kết quả nằm trong hits, khác với completion suggestion options.

## 7. Tối ưu Prefix Query bằng `index_prefixes`

Prefix Query trên field có cardinality cao hoặc prefix dài/ngắn đa dạng có thể tốn tài nguyên nếu không có cấu trúc index hỗ trợ. Với field `text`, có thể bật `index_prefixes` để Elasticsearch lập chỉ mục các prefix trong một khoảng độ dài xác định.

```json
{
  "properties": {
    "title": {
      "type": "text",
      "index_prefixes": {
        "min_chars": 2,
        "max_chars": 10
      }
    }
  }
}
```

Elasticsearch tạo field nội bộ hỗ trợ prefix query cho độ dài prefix trong khoảng đã cấu hình. Điều này có thể cải thiện hiệu năng prefix lookup nhưng làm tăng chi phí index và dung lượng lưu trữ.

`index_prefixes` phù hợp khi vẫn muốn query kiểu prefix trên field `text` mà có thể kiểm soát trước độ dài prefix phổ biến. Nếu cần autocomplete nhiều token, `search_as_you_type` có thể biểu đạt mục tiêu tốt hơn.

## 8. Prefix matching bằng Edge N-gram

Edge n-gram là kỹ thuật analyzer tạo ra các token con bắt đầu từ đầu token gốc. Ví dụ token `wireless` có thể sinh:

```text
wi
wir
wire
wirel
wirele
wireles
wireless
```

Khi người dùng nhập `wirel`, query analyzer tạo token `wirel` và tìm được document có token prefix tương ứng. Kỹ thuật này hữu ích cho autocomplete dựa trên field `text` và cho phép kết hợp với query scoring thông thường.

### Cấu hình analyzer edge n-gram

```http
PUT /products
Content-Type: application/json

{
  "settings": {
    "analysis": {
      "filter": {
        "name_edge_ngram": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 15
        }
      },
      "analyzer": {
        "name_index_analyzer": {
          "tokenizer": "standard",
          "filter": ["lowercase", "name_edge_ngram"]
        },
        "name_search_analyzer": {
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "name_index_analyzer",
        "search_analyzer": "name_search_analyzer"
      }
    }
  }
}
```

Analyzer lúc index sinh các prefix token; search analyzer chỉ chuẩn hóa input thành token bình thường. Không dùng edge n-gram analyzer ở cả hai phía một cách thiếu chủ đích, vì có thể làm query bị mở rộng thành nhiều prefix không mong muốn.

### Ưu điểm và chi phí

- Có thể dùng query full-text thông thường trên field đã tạo prefix token.
- Dễ kết hợp với scoring, filter và nhiều field.
- Tăng số token được index, làm tăng dung lượng và chi phí indexing.
- Cần chọn `min_gram`/`max_gram` phù hợp; prefix ngắn quá có thể tạo nhiều kết quả nhiễu.
- Thay analyzer thường yêu cầu tạo index mới và reindex dữ liệu.

Edge n-gram không phải spelling correction. Nếu người dùng nhập sai một ký tự, token prefix sai vẫn không khớp token đúng.

## 9. Tìm kiếm tiền tố nhiều từ với `match_bool_prefix`

`match_bool_prefix` phân tích input thành các token. Các token trước token cuối được tìm như term match, còn token cuối được xử lý theo prefix. Đây là lựa chọn thuận tiện khi người dùng đang nhập dở từ cuối trong một cụm.

Ví dụ:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match_bool_prefix": {
      "name": "wireless head"
    }
  }
}
```

Với analyzer tạo token `wireless` và `head`, query tìm document có các term phù hợp với `wireless` và token bắt đầu bằng `head`, chẳng hạn `headphones`.

Trong Spring Data Elasticsearch:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.matchBoolPrefix(m -> m
        .field("name")
        .query("wireless head")
    ))
    .build();
```

`match_bool_prefix` trả về document hits và có scoring. Nó khác Completion Suggester ở chỗ mục tiêu là tìm document phù hợp với cụm từ đang nhập, không phải truy xuất một danh sách input autocomplete được index riêng.

## 10. Gợi ý chính tả bằng Term Suggester

Term Suggester đề xuất candidate thay thế cho từng token dựa trên khoảng cách chỉnh sửa và thống kê từ vựng của field. Ví dụ `elastcsearch` có thể được gợi ý thành `elasticsearch`.

Request:

```http
POST /products/_search
Content-Type: application/json

{
  "suggest": {
    "product_terms": {
      "text": "wireles hedphones",
      "term": {
        "field": "name",
        "suggest_mode": "popular",
        "max_edits": 2,
        "size": 5
      }
    }
  }
}
```

Term suggester tạo gợi ý ở cấp token. Với câu có nhiều từ, response có thể chứa các entry riêng cho từng token. Ứng dụng cần quyết định cách hiển thị hoặc kết hợp candidate; nó không tự động tạo một câu sửa hoàn chỉnh có ngữ cảnh tốt.

Một số tùy chọn:

- `suggest_mode: missing`: chỉ đề xuất khi token không tồn tại trong từ vựng.
- `suggest_mode: popular`: ưu tiên candidate phổ biến hơn token đầu vào.
- `suggest_mode: always`: luôn xem xét candidate.
- `max_edits`: giới hạn khoảng cách chỉnh sửa cho phép, thường là 1 hoặc 2.
- `size`: số candidate tối đa cho mỗi entry.
- `prefix_length`: số ký tự đầu phải khớp trước khi xét edit distance.

Term suggester không hiểu đầy đủ ý nghĩa câu. Nó có thể đề xuất từng từ riêng lẻ mà không nhận ra cụm từ nào hợp lý trong ngữ cảnh. Với sửa lỗi ở cấp cụm, cân nhắc Phrase Suggester.

## 11. Gợi ý chính tả theo cụm bằng Phrase Suggester

Phrase Suggester sử dụng candidate generator và thống kê cụm từ (thường dựa trên shingle/n-gram) để xếp hạng các phương án sửa cả cụm. Nó phù hợp hơn khi lỗi chính tả nằm trong một câu hoặc tên nhiều từ.

Ví dụ mapping có field trigram:

```json
{
  "settings": {
    "analysis": {
      "filter": {
        "name_shingle": {
          "type": "shingle",
          "min_shingle_size": 2,
          "max_shingle_size": 3
        }
      },
      "analyzer": {
        "name_trigram": {
          "tokenizer": "standard",
          "filter": ["lowercase", "name_shingle"]
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
            "analyzer": "name_trigram"
          }
        }
      }
    }
  }
}
```

Query phrase suggester:

```http
POST /products/_search
Content-Type: application/json

{
  "suggest": {
    "name_phrase": {
      "text": "wireles hedphones",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always",
            "max_edits": 2
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
```

Phrase Suggester có thể đánh giá candidate dựa trên thống kê n-gram và đưa ra cụm từ có khả năng hợp lý hơn. Chất lượng phụ thuộc dữ liệu index, analyzer, field shingle và candidate generator. Với catalog nhỏ hoặc dữ liệu ngôn ngữ ít, gợi ý có thể không tốt dù query chạy thành công.

## 12. Đọc Term/Phrase Suggestion trong Spring Data

`NativeQuery` có thể gắn suggester bằng `withSuggester(...)`, giống cách dùng Completion Suggester nhưng chọn loại `term` hoặc `phrase`:

```java
import co.elastic.clients.elasticsearch.core.search.FieldSuggester;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Suggester suggester = Suggester.of(s -> s
    .text("wireles hedphones")
    .suggesters("product_terms", FieldSuggester.of(fs -> fs
        .term(t -> t
            .field("name")
            .suggestMode(co.elastic.clients.elasticsearch._types.SuggestMode.Popular)
            .size(5)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

Đọc kết quả từ `SearchHits.getSuggest()`:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasSuggest()) {
    Suggest suggest = results.getSuggest();
    Suggest.Suggestion<?> termSuggestion =
        suggest.getSuggestion("product_terms");

    if (termSuggestion != null) {
        for (Suggest.Suggestion.Entry<?> entry : termSuggestion.getEntries()) {
            String original = entry.getText();

            for (Suggest.Suggestion.Entry.Option option : entry.getOptions()) {
                String candidate = option.getText();
                // Ví dụ: hiển thị candidate như một gợi ý chính tả.
            }
        }
    }
}
```

Term suggestion thường có entry theo token và option theo candidate. Phrase suggestion có kiểu entry/option tương ứng nhưng text option đại diện cụm từ được đề xuất. Hãy kiểm tra đúng loại suggester và kiểu response khi cần đọc metadata chuyên biệt như score hoặc frequency.

## 13. Khi nào dùng Prefix Query, `match_bool_prefix` hay `search_as_you_type`?

Ba cách này đều có thể hỗ trợ tìm kiếm trong lúc người dùng đang nhập, nhưng ngữ nghĩa khác nhau.

| Cơ chế | Phù hợp | Ví dụ input | Kết quả mong muốn |
|---|---|---|---|
| Prefix Query trên `keyword` | Mã hoặc giá trị nguyên bản bắt đầu bằng prefix | `IPH` | SKU bắt đầu bằng `IPH` |
| Prefix Query trên `text` | Prefix của token đã được analyzer index | `head` | Document có token bắt đầu bằng `head` |
| `match_bool_prefix` | Cụm nhiều từ, token cuối chưa hoàn chỉnh | `wireless head` | Tìm document có `wireless` và token prefix `head` |
| `search_as_you_type` + `bool_prefix` | Search-as-you-type nhiều từ có relevance tốt | `wireless head` | Tìm và xếp hạng sản phẩm phù hợp |
| Edge n-gram | Autocomplete/prefix matching qua token đã n-gram hóa | `wirel` | Document có token chứa prefix đã index |
| Completion Suggester | Dropdown gợi ý input hoàn chỉnh | `wirel` | Các input đã index bắt đầu bằng prefix |

Nếu chỉ cần lọc mã, Prefix Query trên `keyword` thường là cách đơn giản. Nếu cần tìm theo câu nhiều từ trong lúc nhập, `search_as_you_type` hoặc `match_bool_prefix` thường phù hợp hơn. Nếu giao diện cần một danh sách lựa chọn được chuẩn bị sẵn, Completion Suggester thường hợp lý.

## 14. Chọn analyzer và chuẩn hóa chữ hoa/thường

Autocomplete và prefix search phụ thuộc vào việc input lúc index và input lúc search được chuẩn hóa tương thích.

Ví dụ người dùng nhập `IPH`, trong khi dữ liệu được index là `iPhone`. Nếu field `keyword` giữ nguyên hoa/thường, Prefix Query có thể không khớp theo cách mong muốn. Có thể chuẩn hóa dữ liệu trước khi index và query, hoặc dùng normalizer trên keyword field khi phù hợp.

Ví dụ keyword normalizer:

```json
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
      "sku": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
```

Normalizer giúp so khớp không phân biệt hoa/thường và có thể chuẩn hóa dấu theo filter cấu hình. Cần xác định rõ việc bỏ dấu có phù hợp với mã định danh hay ngôn ngữ không; không nên tự động bỏ dấu nếu điều đó làm hai giá trị nghiệp vụ khác nhau trở thành một.

Với text field, analyzer có thể lowercase, tokenize hoặc dùng synonym. Dùng `_analyze` để kiểm tra token:

```http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Headphones"
}
```

Nếu query và index analyzer không tương thích, prefix hoặc spelling suggestion có thể bỏ lỡ những kết quả người dùng kỳ vọng.

## 15. Prefix search có thể tìm theo token nào?

Prefix search trên `keyword` so sánh với toàn bộ term. Với `text`, analyzer có thể tạo nhiều token từ một câu.

Ví dụ `name = "Wireless Headphones Pro"` sau khi dùng standard analyzer có thể có các token:

```text
wireless
headphones
pro
```

Prefix Query trên field `name` với `head` có thể khớp token `headphones`, dù `head` không phải prefix của toàn bộ chuỗi `_source` từ ký tự đầu. Đây là tìm prefix của token được index, không phải prefix của toàn bộ câu gốc.

Nếu yêu cầu là chuỗi bắt đầu từ ký tự đầu tiên của giá trị, hãy dùng `keyword` field đã chuẩn hóa. Nếu yêu cầu là token cuối trong câu đang nhập dở, dùng `match_bool_prefix` hoặc `search_as_you_type`.

## 16. Xếp hạng kết quả autocomplete và prefix search

Autocomplete có thể cần xếp hạng theo mức phổ biến, độ ưu tiên hoặc context. Completion input có thể được gắn weight để một lựa chọn nổi bật hơn.

Ví dụ index completion input với weight:

```json
{
  "suggest": {
    "input": ["iPhone 16 Pro"],
    "weight": 10
  }
}
```

Một lựa chọn phổ biến có thể có weight cao hơn lựa chọn ít được dùng. Weight là tín hiệu xếp hạng suggestion, không phải xác suất người dùng sẽ chọn.

Với `search_as_you_type` hoặc prefix query trả hits, thứ tự thường dựa trên `_score` nếu query có scoring. Có thể kết hợp field boost, popularity hoặc recency theo mục tiêu. Với prefix query trên keyword, relevance score có thể không đủ phân biệt các giá trị; ứng dụng có thể sort theo field nghiệp vụ.

Không nên trộn các kết quả từ Completion Suggester và search hits thành một danh sách không phân loại nếu score của hai cơ chế không cùng thang đo. Nếu cần kết hợp, hãy chuẩn hóa bằng quy tắc xếp hạng ứng dụng hoặc giữ hai nhóm UI riêng.

## 17. Thiết kế trải nghiệm tìm kiếm kết hợp ba chức năng

Một luồng tìm kiếm có thể vận hành như sau:

```text
Người dùng nhập ký tự
        |
        v
Input ngắn / prefix đang nhập
        |
        +----> Autocomplete
        |       Completion Suggester hoặc search_as_you_type
        |       Trả lựa chọn hoàn chỉnh
        |
        v
Người dùng gửi truy vấn
        |
        v
Full-text / prefix search
        |
        +----> Có kết quả: hiển thị document hits
        |
        +----> Không có hoặc quá ít kết quả:
                 chạy Term/Phrase Suggester
                 hiển thị “Có phải bạn muốn tìm...”
```

### Gợi ý hành vi UI

- Debounce input để tránh gửi request cho từng phím với tần suất quá cao.
- Chỉ gọi autocomplete khi input đạt độ dài tối thiểu, ví dụ 2 ký tự.
- Giới hạn số suggestion, thường khoảng 5–10 lựa chọn tùy giao diện.
- Khi người dùng chọn suggestion, thay input bằng cụm được chọn và chạy search bình thường.
- Chạy spelling suggestion khi kết quả rỗng hoặc chất lượng thấp, thay vì nhất thiết gọi ở mọi lần gõ.
- Hiển thị gợi ý chính tả như lựa chọn; không tự sửa query người dùng nếu chưa có quy tắc UX rõ ràng.
- Dùng prefix search cho mã hoặc token prefix khi đó là ngữ nghĩa người dùng mong đợi.

## 18. So sánh chi phí index và truy vấn

| Cơ chế | Chi phí index | Chi phí truy vấn | Ghi chú |
|---|---|---|---|
| Completion Suggester | Tạo cấu trúc completion riêng; có thể tăng heap | Prefix lookup nhanh | Theo dõi số input và kích thước completion field |
| Term/Phrase Suggester | Dựa trên field và thống kê từ vựng; phrase thường cần shingle field | Phụ thuộc candidate generation và thống kê | Chỉ chạy khi cần sửa từ; chất lượng phụ thuộc corpus |
| Prefix Query trên keyword | Thấp nếu chỉ index keyword | Có thể tốn hơn nếu prefix lookup rộng và field không được tối ưu | Dùng `index_prefixes` cho một số trường hợp text |
| `search_as_you_type` | Tạo nhiều subfield/token bổ sung | Tối ưu cho search-as-you-type | Tăng dung lượng so với text field đơn |
| Edge n-gram | Tăng số token được index đáng kể | Query token thông thường có thể nhanh | Cần chọn min/max gram và analyzer cẩn thận |
| `match_bool_prefix` | Phụ thuộc mapping text hiện có | Query full-text theo prefix token cuối | Dễ kết hợp relevance và nhiều field |

Không có một cơ chế thắng trong mọi trường hợp. Chọn dựa trên UX, cấu trúc dữ liệu, lượng input, yêu cầu xếp hạng, độ trễ và chi phí lưu trữ.

## 19. Những lỗi thường gặp

### Dùng Completion Suggester cho spelling correction

Completion chỉ tìm input phù hợp prefix. Nó không tự tìm từ có edit distance gần. Dùng Term/Phrase Suggester nếu cần đề xuất cách viết.

### Dùng Prefix Query để sửa lỗi chính tả

Prefix Query chỉ khớp prefix của term. `iphnoe` không tự khớp `iphone` chỉ vì hai từ gần nhau. Cần spelling suggester hoặc cơ chế fuzzy phù hợp.

### Dùng Prefix Query trên `text` nhưng mong khớp đầu chuỗi `_source`

Field `text` đã được analyzer tách token. Prefix Query có thể khớp prefix của một token bất kỳ theo cấu trúc index. Dùng keyword field nếu cần prefix của toàn bộ giá trị.

### Mapping completion thành `text`

Completion Suggester yêu cầu field kiểu `completion`. Một text field có analyzer không tự trở thành completion field.

### Không chuẩn hóa hoa/thường nhất quán

Index và query analyzer/normalizer khác nhau có thể làm prefix không khớp. Kiểm tra `_analyze` và normalizer của field.

### Dùng edge n-gram với `max_gram` quá lớn

Mỗi token sinh nhiều token con, làm tăng dung lượng index và chi phí indexing. Chọn khoảng gram theo độ dài input phổ biến.

### Gọi spelling suggestion ở mọi lần gõ

Term/Phrase Suggester có thể tốn chi phí hơn autocomplete prefix đơn giản. Chỉ gọi theo điều kiện UX như không có kết quả hoặc người dùng yêu cầu sửa.

### Tự động sửa truy vấn mà không thông báo

Suggestion chỉ là candidate. Nếu ứng dụng âm thầm thay input, người dùng có thể nhận kết quả khác với điều họ nhập. Hiển thị lựa chọn và cho người dùng quyết định.

## 20. Kiểm thử ba cơ chế riêng biệt

Tạo bộ dữ liệu có các trường hợp:

| Dữ liệu index | Input | Kết quả kiểm thử mong đợi |
|---|---|---|
| `iPhone 16 Pro` trong completion field | `iph` | Completion trả lựa chọn `iPhone 16 Pro` |
| `Wireless Headphones` trong text field | `wireless head` | `match_bool_prefix`/`search_as_you_type` tìm được document |
| `IPH-1001` trong keyword SKU | `IPH` | Prefix Query tìm được document |
| `Elasticsearch` trong field từ vựng | `elastcsearch` | Term suggester có thể đề xuất `elasticsearch` |
| `Wireless Headphones` trong shingle field | `wireles hedphones` | Phrase suggester có thể đề xuất cụm gần đúng |
| `iPhone 16` với category context `phones` | `iph`, context `phones` | Context completion trả lựa chọn thuộc category phù hợp |

Kiểm tra thêm:

- Input hoa/thường và dấu tiếng Việt.
- Prefix ngắn hơn `min_gram` hoặc dài hơn `max_gram`.
- Chuỗi rỗng và input chỉ chứa khoảng trắng.
- Nhiều document có cùng suggestion text.
- Weight khác nhau và context filter.
- Document không có field completion hoặc field bị thiếu.
- Spelling candidate có ý nghĩa khác nhưng edit distance gần.
- Query nhiều từ với token cuối chưa hoàn chỉnh.

Đánh giá chất lượng bằng tập query thực tế và tỷ lệ người dùng chọn suggestion. Chỉ kiểm tra query không lỗi là chưa đủ để kết luận autocomplete hoặc spelling suggestion hữu ích.

## 21. Quy trình chọn giải pháp

Khi triển khai chức năng gợi ý cho một ô tìm kiếm, hãy xác định mục tiêu trước:

1. Nếu muốn đề xuất tên/mục hoàn chỉnh từ prefix, dùng Completion Suggester.
2. Nếu cần autocomplete nhiều từ với relevance của document, dùng `search_as_you_type` và `bool_prefix`.
3. Nếu cần tìm mã hoặc giá trị bắt đầu bằng prefix nguyên bản, dùng Prefix Query trên `keyword` đã chuẩn hóa.
4. Nếu cần prefix lookup trên token text, xem xét Prefix Query với `index_prefixes` hoặc edge n-gram.
5. Nếu muốn sửa một token gõ sai, dùng Term Suggester.
6. Nếu muốn đề xuất cách sửa cho cả cụm, dùng Phrase Suggester với field shingle phù hợp.
7. Xác định analyzer/normalizer, giới hạn số kết quả, độ dài input và cách xếp hạng.
8. Kiểm thử riêng từng cơ chế với dữ liệu đúng, sai chính tả, prefix nhiều từ và giá trị biên.
9. Đặt debounce và điều kiện gọi suggestion ở tầng ứng dụng.
10. Theo dõi độ trễ, tỷ lệ chọn suggestion, dung lượng index và chất lượng kết quả.

## 22. Kết luận

Autocomplete, spelling suggestion và prefix search phục vụ ba nhu cầu khác nhau. Completion Suggester trả về các input hoàn chỉnh theo prefix và phù hợp với dropdown gợi ý. Term/Phrase Suggester tạo candidate sửa lỗi chính tả ở cấp từ hoặc cụm từ. Prefix Query, `match_bool_prefix`, `search_as_you_type` và edge n-gram tìm document có term hoặc token bắt đầu bằng phần người dùng đã nhập.

Trong Spring Data Elasticsearch, Completion Suggester có thể dùng `@CompletionField`, `Completion` và `NativeQuery.withSuggester(...)`; spelling suggester cũng được khai báo qua `Suggester`; prefix search dùng `NativeQuery` với `prefix` hoặc `matchBoolPrefix`. Hãy chọn mapping theo mục tiêu, chuẩn hóa input nhất quán và phân biệt suggestion options với document search hits. Khi ba chức năng được triển khai đúng vai trò, giao diện tìm kiếm có thể vừa gợi ý nhanh, vừa xử lý lỗi gõ, vừa truy xuất document theo prefix mà không làm lẫn ngữ nghĩa của từng kết quả.

## Tài liệu tham khảo

- [Elasticsearch – Search suggesters](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters)
- [Elasticsearch – Completion suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#completion-suggester)
- [Elasticsearch – Term suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#term-suggester)
- [Elasticsearch – Phrase suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#phrase-suggester)
- [Elasticsearch – Prefix query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-prefix-query)
- [Elasticsearch – Match bool prefix query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-bool-prefix-query)
- [Elasticsearch – Search as you type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/search-as-you-type)
- [Elasticsearch – Edge n-gram token filter](https://www.elastic.co/docs/reference/text-analysis/analysis-edgengram-tokenfilter)
- [Spring Data Elasticsearch – NativeQuery and search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
