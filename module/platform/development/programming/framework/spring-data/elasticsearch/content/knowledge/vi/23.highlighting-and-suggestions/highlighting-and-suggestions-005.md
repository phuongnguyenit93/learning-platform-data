# Fragment size, số đoạn, thẻ đánh dấu và nguồn văn bản

Highlighting giúp giao diện tìm kiếm cho người dùng thấy phần văn bản khớp với truy vấn ngay trong từng kết quả. Elasticsearch có thể trích một hoặc nhiều đoạn văn bản xung quanh token khớp, chèn thẻ đánh dấu trước và sau phần khớp, rồi trả các đoạn đó trong trường highlight của mỗi hit.

Khi thiết kế highlight, cần quyết định bốn việc:

- **Nguồn văn bản:** highlighter lấy nội dung field từ đâu và field có được lưu trong _source hay stored field không?
- **Fragment size:** mỗi đoạn tối đa khoảng bao nhiêu ký tự?
- **Số fragment:** mỗi field của một hit trả về tối đa bao nhiêu đoạn?
- **Tags:** dùng thẻ nào để đánh dấu phần khớp và có cần encode HTML hay không?

Các thiết lập này ảnh hưởng payload response, trải nghiệm hiển thị, chi phí xử lý và khả năng an toàn khi render nội dung trong trình duyệt.

## 1. Highlighting hoạt động như thế nào?

Một search request có thể chứa query để tìm document và phần highlight để yêu cầu Elasticsearch trích các đoạn khớp từ một số field. Query quyết định document nào được trả về; highlighter quyết định phần văn bản nào của field được đưa vào đoạn trích.

Ví dụ document:

~~~json
{
  "title": "Spring Data Elasticsearch",
  "content": "Spring Data Elasticsearch integrates Spring applications with Elasticsearch. It provides repositories and operations for search."
}
~~~

Khi tìm cụm Spring Data, request có thể yêu cầu highlight field title và content. Một hit có thể chứa:

~~~json
{
  "_index": "articles",
  "_id": "article-1",
  "_source": {
    "title": "Spring Data Elasticsearch",
    "content": "Spring Data Elasticsearch integrates Spring applications with Elasticsearch. It provides repositories and operations for search."
  },
  "highlight": {
    "title": [
      "<em>Spring</em> <em>Data</em> Elasticsearch"
    ],
    "content": [
      "<em>Spring</em> <em>Data</em> Elasticsearch integrates Spring applications with Elasticsearch."
    ]
  }
}
~~~

Highlight fragments nằm trong object highlight, tách biệt với _source. Highlighter không sửa document đã lưu và không thay thế giá trị gốc trong _source. Ứng dụng thường dùng _source để hiển thị nội dung đầy đủ và dùng highlight để hiển thị preview có đánh dấu.

## 2. Khai báo field cần highlight

Highlighting thường được dùng trên field văn bản có mapping phù hợp, đặc biệt là text. Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard"
      },
      "content": {
        "type": "text",
        "analyzer": "standard"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Field title và content được phân tích thành token để query và highlight. Field status thường được dùng để lọc, không phải nội dung cần trích đoạn.

Ví dụ Search API:

~~~http
GET /articles/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {}
    }
  }
}
~~~

Khi không chỉ định tham số riêng cho field, Elasticsearch dùng cấu hình mặc định của highlighter. Có thể khai báo tùy chọn chung ở cấp highlight và ghi đè cho từng field khi cần.

## 3. fragment_size: kích thước mỗi đoạn

fragment_size đặt kích thước mục tiêu của mỗi fragment tính theo ký tự, không phải số từ hay số byte. Highlighter cố gắng chọn đoạn quanh phần khớp sao cho có đủ ngữ cảnh để người đọc hiểu kết quả.

Ví dụ giới hạn fragment khoảng 120 ký tự:

~~~json
{
  "highlight": {
    "fragment_size": 120,
    "fields": {
      "content": {}
    }
  }
}
~~~

Kích thước mặc định thường là 100 ký tự. Giá trị thực tế của fragment có thể khác con số cấu hình do highlighter phải tôn trọng ranh giới từ/câu, vị trí token khớp và cách chọn boundary.

### 3.1. Chọn fragment size theo giao diện

| Mục đích | Kích thước gợi ý để bắt đầu |
| --- | ---: |
| Preview ngắn trong danh sách kết quả | 80–120 ký tự |
| Snippet có đủ ngữ cảnh trong trang tìm kiếm | 150–250 ký tự |
| Đoạn dài cho màn hình đọc nội dung | 250–400 ký tự hoặc hơn tùy nội dung |

Các khoảng trên chỉ là điểm bắt đầu để thử nghiệm. Nên đo với độ dài từ, ngôn ngữ và độ dài field thực tế. Một giá trị quá nhỏ có thể cắt mất ngữ cảnh; một giá trị quá lớn làm response nặng và khiến danh sách kết quả khó quét nhanh.

### 3.2. Fragment size không phải giới hạn độ dài field

fragment_size không cắt hoặc sửa nội dung được lưu. Nó chỉ điều khiển đoạn trích được trả về trong response. Document vẫn giữ toàn bộ giá trị field trong _source nếu source được bật.

Field ngắn hơn fragment size có thể được trả gần như toàn bộ. Với field dài, highlighter chọn các đoạn có chứa phần khớp và có thể điều chỉnh ranh giới để tránh cắt giữa từ hoặc câu.

## 4. number_of_fragments: số đoạn cho mỗi field

number_of_fragments xác định số fragment tối đa highlighter trả về cho một field trong một hit.

Ví dụ lấy tối đa ba đoạn trong field content:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 160,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Mặc định, highlighter thường trả tối đa 5 fragment cho mỗi field. Nếu document có nhiều vùng khớp, số đoạn trả về bị giới hạn theo giá trị cấu hình. Nếu chỉ có một hoặc hai vùng phù hợp, response có thể chứa ít hơn số lượng tối đa.

### 4.1. Mỗi field có số fragment riêng

Có thể yêu cầu các field khác nhau với kích thước và số đoạn khác nhau:

~~~json
{
  "highlight": {
    "fields": {
      "title": {
        "fragment_size": 80,
        "number_of_fragments": 1
      },
      "content": {
        "fragment_size": 180,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Trong ví dụ, tiêu đề chỉ cần một đoạn ngắn, còn nội dung có thể trả tối đa ba đoạn. Đây là cách hữu ích để tối ưu payload theo vai trò của từng field.

### 4.2. number_of_fragments: 0: trả toàn bộ field

Khi đặt number_of_fragments bằng 0, Elasticsearch không chia field thành các fragment ngắn mà trả toàn bộ nội dung field trong một fragment. Trong trường hợp này, fragment_size bị bỏ qua.

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "number_of_fragments": 0
      }
    }
  }
}
~~~

Chế độ này phù hợp khi field ngắn và giao diện cần toàn bộ nội dung đã đánh dấu. Với field dài, response có thể rất lớn. Nếu chỉ cần preview, hãy dùng số fragment hữu hạn.

## 5. Không có fragment khớp và no_match_size

Đôi khi document được trả về do query khớp một field khác, nhưng field đang yêu cầu highlight không chứa token khớp. Khi đó highlighter có thể không trả fragment cho field đó.

no_match_size cho phép trả một đoạn đầu field ngay cả khi không tìm thấy phần khớp trong field được highlight:

~~~json
{
  "highlight": {
    "fields": {
      "title": {
        "number_of_fragments": 1,
        "no_match_size": 80
      }
    }
  }
}
~~~

no_match_size là kích thước đoạn đầu được lấy khi không có match trong field đó; mặc định là 0, tức không trả đoạn thay thế. Nó không tạo highlight tag cho một từ không khớp.

Ví dụ query tìm trong content nhưng yêu cầu highlight cả title. Nếu title không có từ truy vấn, no_match_size có thể giúp giao diện vẫn có preview title. Tuy nhiên, cần phân biệt rõ đoạn preview không có tag với đoạn chứa match thực sự.

## 6. pre_tags và post_tags: thẻ đánh dấu

pre_tags xác định chuỗi được chèn trước phần khớp; post_tags xác định chuỗi được chèn sau phần khớp.

Ví dụ dùng thẻ mark:

~~~json
{
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {}
    }
  }
}
~~~

Fragment trả về có thể là:

~~~text
<mark>Spring</mark> <mark>Data</mark> Elasticsearch
~~~

Có thể dùng class CSS riêng:

~~~json
{
  "highlight": {
    "pre_tags": ["<span class=\"search-hit\">"],
    "post_tags": ["</span>"],
    "fields": {
      "content": {}
    }
  }
}
~~~

và CSS:

~~~css
.search-hit {
    background: #fff2a8;
    font-weight: 600;
}
~~~

### 6.1. Nhiều cặp tag

Elasticsearch cho phép truyền nhiều pre_tags và post_tags. Highlighter có thể luân phiên sử dụng các cặp tag theo phần match hoặc cách triển khai highlighter. Điều này có thể giúp phân biệt nhiều loại match, nhưng giao diện nên dùng một bộ tag thống nhất nếu không có yêu cầu thiết kế rõ ràng.

### 6.2. Tags không phải là nội dung an toàn

Highlight fragment thường được trả về dưới dạng chuỗi có chứa tag. Nếu render trực tiếp bằng innerHTML hoặc cơ chế tương đương, nội dung gốc trong document có thể chứa markup hoặc chuỗi HTML không an toàn.

Không coi fragment là HTML đáng tin cậy chỉ vì tag highlight do ứng dụng cấu hình. Hãy encode hoặc sanitize phần văn bản gốc theo đúng chính sách của giao diện; chỉ cho phép tag highlight dự kiến. Có thể dùng encoder: html để yêu cầu highlighter encode nội dung HTML trong fragment trong khi vẫn giữ tag highlight. Cần kiểm tra response thực tế trước khi render.

## 7. encoder: xử lý HTML trong văn bản nguồn

encoder quyết định cách highlighter encode nội dung fragment:

| Giá trị | Ý nghĩa |
| --- | --- |
| default | Không encode HTML trong nội dung nguồn. Đây là mặc định. |
| html | Encode ký tự đặc biệt HTML trong nội dung nguồn trước khi trả fragment. |

Ví dụ:

~~~json
{
  "highlight": {
    "encoder": "html",
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Nếu source chứa chuỗi script hoặc markup HTML, encoder html giúp nó được trả dưới dạng văn bản đã escape, giảm nguy cơ thực thi markup khi hiển thị. Tuy vậy, ứng dụng vẫn phải dùng cách render an toàn và kiểm tra tag được phép. Không ghép fragment với HTML tùy ý từ nguồn người dùng.

## 8. Chọn highlighter type

Elasticsearch hỗ trợ nhiều highlighter. Nếu không chỉ định type, highlighter unified thường được dùng mặc định.

| Type | Đặc điểm | Điều kiện và trường hợp dùng |
| --- | --- | --- |
| unified | Highlighter mặc định, hỗ trợ nhiều loại query và chọn fragment theo mức độ liên quan. | Lựa chọn chung cho phần lớn ứng dụng. |
| plain | Dùng một index nhỏ trong bộ nhớ để phân tích lại văn bản và xác định match. | Phù hợp với field nhỏ; có thể tốn chi phí hơn khi field lớn hoặc số lượng hit nhiều. |
| fvh | Fast Vector Highlighter sử dụng term vectors. | Cần mapping term_vector: with_positions_offsets; có thể phù hợp khi cần highlight nhiều fragment trên field lớn. |
| postings | Dùng offsets được lưu trong postings. | Cần index_options: offsets trên field. |

Ví dụ chỉ định unified:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 180,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Không nên chọn fvh hoặc postings chỉ vì tên gợi ý hiệu năng cao. Chúng cần cấu hình mapping tương ứng và có trade-off về dung lượng index, tốc độ index, memory và khả năng xử lý query. Hãy đo trên dữ liệu đại diện.

### 8.1. Unified highlighter

Unified là lựa chọn mặc định hợp lý cho đa số trường hợp. Nó có thể sử dụng offsets từ postings, term vectors hoặc phân tích lại văn bản tùy mapping và khả năng sẵn có.

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 200,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

### 8.2. Fast Vector Highlighter

FVH cần term vectors có positions và offsets. Mapping ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "term_vector": "with_positions_offsets"
      }
    }
  }
}
~~~

Query highlight:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "fvh",
        "fragment_size": 200,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Term vectors làm tăng dung lượng index và chi phí khi index document. Chỉ bật nếu có use case highlight cần thiết và đã đo lợi ích.

### 8.3. Postings highlighter

Postings highlighter cần offsets được lưu trong postings:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "index_options": "offsets"
      }
    }
  }
}
~~~

Yêu cầu highlight:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "postings",
        "fragment_size": 180,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Postings offsets có thể tăng dung lượng inverted index. Cần cân nhắc giữa tốc độ highlight và chi phí lưu trữ.

## 9. Chọn ranh giới fragment

Highlighter cố gắng chọn fragment quanh match sao cho văn bản dễ đọc. boundary_scanner điều khiển cách xác định ranh giới:

| Giá trị | Cách chọn ranh giới |
| --- | --- |
| chars | Dùng các ký tự boundary được cấu hình. |
| sentence | Cố gắng cắt theo ranh giới câu. |
| word | Cố gắng cắt theo ranh giới từ. |

Ví dụ ưu tiên ranh giới câu:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 220,
        "number_of_fragments": 2,
        "boundary_scanner": "sentence",
        "boundary_scanner_locale": "vi-VN"
      }
    }
  }
}
~~~

boundary_scanner_locale cho phép chỉ định locale khi highlighter cần xác định ranh giới theo ngôn ngữ. Kết quả vẫn phụ thuộc văn bản, tokenizer và implementation của highlighter; cần thử với câu tiếng Việt có dấu câu, viết tắt và dấu ngoặc.

Với boundary_scanner: chars, có thể khai báo boundary_chars và boundary_max_scan để kiểm soát ký tự và phạm vi tìm ranh giới. Một cấu hình ví dụ:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "boundary_scanner": "chars",
        "boundary_chars": ".,!?;: \t\n",
        "boundary_max_scan": 30,
        "fragment_size": 160
      }
    }
  }
}
~~~

Các tùy chọn boundary có thể khác nhau theo highlighter type; không phải mọi tham số đều được hỗ trợ giống nhau bởi tất cả implementation.

## 10. Sắp xếp fragment bằng order

Một field có thể có nhiều fragment khớp. order quyết định cách sắp xếp các đoạn:

- score: sắp xếp fragment theo mức độ liên quan; thường là lựa chọn phù hợp cho preview tìm kiếm.
- none: giữ thứ tự theo vị trí trong văn bản thay vì xếp theo score.

Ví dụ:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 3,
        "order": "score"
      }
    }
  }
}
~~~

Nếu giao diện muốn hiển thị đoạn đầu tiên theo thứ tự đọc tự nhiên, dùng order: none có thể phù hợp hơn. Nếu muốn đưa đoạn liên quan nhất lên trước, dùng score.

## 11. require_field_match và highlight_query

### 11.1. require_field_match

Mặc định require_field_match là true: field được highlight cần có match phù hợp với query. Nếu đặt false, highlighter có thể highlight field dù query chính không trực tiếp nhắm tới field đó, tùy cấu trúc truy vấn và khả năng highlighter.

Ví dụ:

~~~json
{
  "highlight": {
    "require_field_match": false,
    "fields": {
      "title": {},
      "content": {}
    }
  }
}
~~~

Không đặt false chỉ để “highlight được nhiều hơn”. Nó có thể làm các field được highlight theo điều kiện không mong muốn. Nếu cần query riêng cho highlight, cân nhắc highlight_query.

### 11.2. highlight_query

highlight_query cho phép chỉ định query dùng riêng để xác định phần văn bản cần đánh dấu. Nó hữu ích khi query tìm document phức tạp hơn query muốn highlight, ví dụ query chính có nhiều điều kiện filter hoặc dùng synonym/fuzzy.

Ví dụ query chính tìm document bằng match và filter trạng thái, còn highlight dùng phrase query:

~~~json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "content": "spring data elasticsearch" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  },
  "highlight": {
    "fields": {
      "content": {}
    },
    "highlight_query": {
      "match_phrase": {
        "content": {
          "query": "spring data elasticsearch",
          "slop": 1
        }
      }
    }
  }
}
~~~

highlight_query chỉ điều khiển việc highlight; nó không thay thế query chính và không quyết định document nào được trả về. Nếu query highlight không khớp field, có thể không có fragment dù document đã được query chính tìm thấy.

## 12. Multi-field và matched_fields

Một thuộc tính có thể được lập chỉ mục qua nhiều field, ví dụ content kiểu text và content.english với analyzer khác. Nếu query tìm trên một subfield nhưng muốn highlight từ field chính, có thể dùng matched_fields trong các trường hợp highlighter hỗ trợ.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "fields": {
          "english": {
            "type": "text",
            "analyzer": "english"
          }
        }
      }
    }
  }
}
~~~

Ví dụ highlight:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "matched_fields": ["content", "content.english"],
        "type": "unified"
      }
    }
  }
}
~~~

matched_fields cho phép kết hợp match information từ nhiều field liên quan để highlight trên field đích. Cách dùng và giới hạn phụ thuộc highlighter type; FVH có các yêu cầu riêng. Không áp dụng máy móc cho những field không cùng nội dung hoặc không cùng cấu trúc token.

## 13. Nguồn văn bản: _source, stored field và term vectors

Highlighter cần truy cập nội dung văn bản để dựng fragment. Trong ứng dụng thông thường, _source là nơi giữ văn bản gốc và thường được sử dụng để cung cấp nội dung cho highlight.

Các điểm cần hiểu:

- _source giữ giá trị JSON của document; highlighter có thể dùng nó để lấy văn bản cần highlight khi mapping và highlighter phù hợp.
- Stored field lưu riêng một field khi mapping đặt store: true; có thể cần thiết trong những thiết kế không dùng _source cho field đó.
- Term vectors giữ token và metadata vị trí/offset; FVH yêu cầu term vectors có positions và offsets.
- Postings offsets lưu offset trong inverted index và được postings highlighter sử dụng.

Không đồng nhất các cơ chế này. Term vectors hoặc postings offsets cung cấp thông tin token/offset; chúng không phải bản sao JSON gốc. Stored field cung cấp giá trị field riêng. _source giữ cấu trúc document và thường cần thiết để dựng entity.

### 13.1. Khi _source bị tắt

Khi index tắt _source, highlighter có thể không còn nguồn văn bản để dựng fragment theo cách thông thường. Khả năng highlight lúc đó phụ thuộc field có được lưu riêng hay có thông tin cần thiết từ term vectors/highlighter type hay không.

Không nên tắt _source chỉ để giảm dung lượng nếu ứng dụng cần highlight, reindex hoặc dựng entity. Hãy kiểm tra chính xác tổ hợp mapping và highlighter trên phiên bản Elasticsearch đang dùng trước khi triển khai index không có source.

### 13.2. Field stored

Nếu cần truy xuất nội dung field độc lập với _source, có thể khai báo store: true cho field và yêu cầu stored field. Tuy nhiên, việc bật store không tự động làm mọi highlighter hoạt động với mọi cấu hình. Highlighter vẫn cần thông tin token, offsets và nội dung phù hợp với implementation.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "store": true
      }
    }
  }
}
~~~

Khi dùng source filtering, stored fields hoặc docvalue fields cùng highlight, hãy kiểm tra response: highlight nằm ở object riêng, còn dữ liệu gốc được trả theo option tương ứng.

## 14. Giới hạn phân tích và field dài

Với field rất dài, highlighter có thể cần phân tích nhiều văn bản để tìm fragment. Elasticsearch có các giới hạn bảo vệ như index.highlight.max_analyzed_offset và tham số request liên quan trong những phiên bản hỗ trợ.

Nếu văn bản vượt giới hạn phân tích, highlighter có thể chỉ xử lý phần đầu hoặc báo lỗi tùy cấu hình và phiên bản. Không nên tăng giới hạn vô điều kiện vì việc phân tích văn bản lớn có thể làm tăng CPU và bộ nhớ.

Đối với nội dung rất dài như bài viết, tài liệu hoặc log:

- Giới hạn số hit cần highlight bằng page size.
- Chỉ highlight các field thực sự cần preview.
- Giữ number_of_fragments nhỏ.
- Dùng fragment size phù hợp với UI.
- Đánh giá highlighter type và mapping offsets/term vectors bằng benchmark.
- Nếu use case là tìm trong tài liệu cực dài, cân nhắc lưu các phần nội dung thành các document/chunk có cấu trúc phù hợp.

## 15. Highlight trong Spring Data Elasticsearch

Spring Data Elasticsearch cho phép cấu hình highlight thông qua HighlightQuery và gắn nó vào query được thực thi bởi ElasticsearchOperations hoặc repository query.

Ví dụ domain object:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    // Constructor, getters và setters
}
~~~

Với các phiên bản Spring Data Elasticsearch hiện đại, có thể tạo highlight metadata và gắn vào NativeQuery. API chi tiết của Highlight, HighlightField, HighlightParameters và HighlightQuery phụ thuộc phiên bản Spring Data đang dùng; cấu trúc tổng quát như sau:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;

HighlightParameters parameters = HighlightParameters.builder()
        .withPreTags("<mark>")
        .withPostTags("</mark>")
        .withFragmentSize(180)
        .withNumberOfFragments(3)
        .build();

Highlight highlight = new Highlight(
        parameters,
        List.of(
                new HighlightField("title"),
                new HighlightField("content")
        )
);

HighlightQuery highlightQuery = new HighlightQuery(
        highlight, ArticleDocument.class);

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("content")
                .query("spring data")))
        .withHighlightQuery(highlightQuery)
        .build();
~~~

Đoạn code minh họa cách khai báo hai field highlight, tag và kích thước/số lượng fragment. Hãy đối chiếu constructor và builder method với API của phiên bản Spring Data Elasticsearch trong dự án; nếu chữ ký khác, giữ nguyên ý nghĩa cấu hình và dùng kiểu tương ứng của dependency.

### 15.1. Đọc highlight từ SearchHit

Khi thực thi query:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ArticleDocument> hits =
        operations.search(query, ArticleDocument.class);

for (SearchHit<ArticleDocument> hit : hits) {
    ArticleDocument article = hit.getContent();

    List<String> titleFragments = hit.getHighlightField("title");
    List<String> contentFragments = hit.getHighlightField("content");
}
~~~

getContent() trả domain object được chuyển đổi từ source theo cấu hình query. getHighlightField("content") trả danh sách fragment cho field đó. Một field có thể không có highlight result, vì vậy ứng dụng cần xử lý danh sách rỗng hoặc null theo API phiên bản đang dùng.

Highlight fragments là nội dung hiển thị phụ trợ. Không nên ghi đè article.getContent() bằng fragment vì fragment có thể chỉ chứa một phần văn bản và có thêm tag.

### 15.2. Trả highlight qua DTO

API thường nên chuyển kết quả thành DTO riêng thay vì đưa toàn bộ SearchHit ra ngoài:

~~~java
public record ArticleSearchResult(
        String id,
        String title,
        List<String> titleHighlights,
        List<String> contentHighlights) {
}

ArticleSearchResult toResult(SearchHit<ArticleDocument> hit) {
    ArticleDocument article = hit.getContent();

    return new ArticleSearchResult(
            hit.getId(),
            article.getTitle(),
            hit.getHighlightField("title"),
            hit.getHighlightField("content"));
}
~~~

Giao diện có thể dùng title làm nội dung gốc và titleHighlights làm snippet. Cần thống nhất rõ fragment là HTML đã được encode hay chuỗi plain text có tag; không để frontend phải đoán.

## 16. Kết hợp highlight với query, filter và phân trang

Highlight chỉ áp dụng cho các hit được query trả về. Vì vậy cần giới hạn số hit bằng page size và chỉ yêu cầu các field cần hiển thị.

Ví dụ request:

~~~http
GET /articles/_search
Content-Type: application/json

{
  "from": 0,
  "size": 10,
  "query": {
    "bool": {
      "must": [
        { "match": { "content": "spring data elasticsearch" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  },
  "_source": ["title", "summary"],
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "encoder": "html",
    "fields": {
      "title": {
        "fragment_size": 100,
        "number_of_fragments": 1
      },
      "content": {
        "fragment_size": 180,
        "number_of_fragments": 2,
        "order": "score"
      }
    }
  }
}
~~~

Trong ví dụ, chỉ lấy 10 hit, _source chỉ trả title và summary, còn highlight trả một fragment title và tối đa hai fragment content. Việc source filtering không đồng nghĩa với việc highlight result bị loại bỏ; highlight là phần riêng của hit.

## 17. Highlight cho phrase query và multi-term query

Highlighter cần dựa trên query để xác định token nào cần đánh dấu. Với query phức tạp như phrase, fuzzy, prefix, wildcard hoặc synonym, khả năng highlight có thể khác theo highlighter type.

Ví dụ phrase query:

~~~json
{
  "query": {
    "match_phrase": {
      "content": {
        "query": "spring data elasticsearch",
        "slop": 1
      }
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 180,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Với multi-term query, highlighter cần xác định các term phù hợp để đánh dấu. Unified highlighter hỗ trợ nhiều loại query và thường là lựa chọn đầu tiên. Nếu query sử dụng nhiều nhánh, synonym graph hoặc custom analyzer, hãy kiểm tra fragment thực tế để xác nhận phần được đánh dấu đúng với kỳ vọng.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có highlight trong hit | Field không được yêu cầu, không có match trong field hoặc query không tương thích. | Kiểm tra highlight.fields, field name, query và require_field_match. |
| Fragment quá ngắn hoặc thiếu ngữ cảnh | fragment_size nhỏ hoặc boundary không phù hợp. | Tăng kích thước và chọn boundary scanner phù hợp. |
| Response quá lớn | Quá nhiều hit, fragment size lớn hoặc số fragment cao. | Giảm page size, số field, number_of_fragments và fragment size. |
| Chỉ trả một đoạn dù field có nhiều match | number_of_fragments đang giới hạn số đoạn. | Tăng số fragment hoặc đặt 0 nếu thật sự cần toàn field. |
| Không trả đoạn khi field không có match | no_match_size mặc định bằng 0. | Đặt no_match_size nếu muốn preview đầu field. |
| Tag không xuất hiện | pre_tags/post_tags không được cấu hình hoặc highlighter không tìm thấy token match. | Kiểm tra query, analyzer và tag trong request. |
| Nội dung HTML nguồn được render như markup | encoder mặc định không encode HTML. | Dùng encoder: html và render an toàn ở frontend. |
| FVH báo thiếu term vectors | Mapping chưa có term_vector: with_positions_offsets. | Tạo mapping đúng và reindex document. |
| Postings highlighter không hoạt động | Field không lưu index_options: offsets. | Cấu hình offsets trên index mới và reindex. |
| Highlight không có source text | _source bị tắt hoặc field không được lưu theo cách highlighter cần. | Kiểm tra nguồn văn bản, stored field và highlighter type. |
| Spring Data getContent() thiếu dữ liệu | Request chỉ lấy highlight/stored/docvalue fields hoặc source filtering loại field cần thiết. | Giữ các field source cần dựng entity hoặc map kết quả riêng. |

## 19. Quy trình thiết kế highlight cho một endpoint

Khi triển khai highlight, hãy xác định:

1. Field nào thực sự cần đánh dấu: title, summary, content hay một số field khác?
2. Field có mapping text và analyzer phù hợp với query không?
3. Giao diện cần preview ngắn hay toàn bộ field?
4. Chọn fragment_size và number_of_fragments theo bố cục UI và kích thước response.
5. Chọn pre_tags/post_tags và quyết định encode HTML.
6. Nếu không có match trong field, có cần no_match_size để trả preview không?
7. Có cần sắp xếp fragment theo score hay theo thứ tự văn bản?
8. Highlighter type nào phù hợp: unified, plain, fvh hay postings?
9. _source, stored field, term vectors hoặc postings offsets có cung cấp nội dung/metadata cần thiết không?
10. Có query phức tạp cần highlight_query, matched_fields hoặc require_field_match không?
11. Giới hạn số hit và số field highlight để kiểm soát chi phí.
12. Kiểm tra response thực tế và cách frontend render tag trên nội dung có HTML.

## 20. Tài liệu tham khảo

- [Elasticsearch — Highlighting](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html)
- [Elasticsearch — Unified highlighter](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#unified-highlighter)
- [Elasticsearch — Fast vector highlighter](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#fast-vector-highlighter)
- [Elasticsearch — Postings highlighter](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#postings-highlighter)
- [Elasticsearch — Term vectors](https://www.elastic.co/guide/en/elasticsearch/reference/current/term-vector.html)
- [Spring Data Elasticsearch — Search result types and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

fragment_size điều khiển kích thước mục tiêu của mỗi snippet; number_of_fragments giới hạn số snippet cho mỗi field và giá trị 0 yêu cầu trả toàn bộ field trong một fragment. pre_tags/post_tags đánh dấu phần match, còn encoder điều khiển việc encode HTML của văn bản nguồn. Highlight được trả trong phần riêng của hit; Spring Data Elasticsearch cung cấp HighlightQuery và SearchHit để cấu hình, đọc các fragment trong ứng dụng.

