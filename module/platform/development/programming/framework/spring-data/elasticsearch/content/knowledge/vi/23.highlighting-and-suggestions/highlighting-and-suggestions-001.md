# Cơ chế đánh dấu đoạn văn bản khớp truy vấn

Highlighting trong Elasticsearch là cơ chế trả về những đoạn văn bản có chứa phần khớp với truy vấn tìm kiếm. Thay vì chỉ hiển thị tiêu đề hoặc mô tả nguyên bản, ứng dụng có thể trình bày một vài đoạn trích và đánh dấu từ hoặc cụm từ liên quan bằng thẻ như <em>...</em>.

Ví dụ, người dùng tìm “wireless mouse” và document có mô tả:

~~~text
A compact wireless mouse with a rechargeable battery.
~~~

Kết quả tìm kiếm có thể trả về fragment:

~~~html
A compact <em>wireless</em> <em>mouse</em> with a rechargeable battery.
~~~

Highlight giúp người dùng hiểu vì sao kết quả xuất hiện và nhanh chóng nhìn thấy phần nội dung phù hợp. Trong Spring Data Elasticsearch, dữ liệu highlight thường được đọc từ metadata của SearchHit, tách biệt với object domain và _source.

Cần nhớ rằng highlight chỉ tạo đoạn trích cho response. Nó không thay đổi nội dung document đã lưu, không tự quyết định document có khớp hay không và không thay thế relevance score.

## 1. Highlighting hoạt động như thế nào?

Một search request gồm query và phần highlight. Elasticsearch trước tiên xác định các document phù hợp với query. Với mỗi hit cần trả về, highlighter tìm các vùng văn bản có liên quan và tạo fragment kèm pre-tag/post-tag bao quanh phần được đánh dấu.

~~~text
Search request
    |
    +--> Query
    |      |
    |      v
    |   Tìm document phù hợp
    |      |
    |      v
    |   Tính _score / sắp xếp
    |
    +--> Highlight configuration
           |
           v
       Đọc hoặc phân tích văn bản
           |
           v
       Tạo fragment
           |
           v
       Thêm pre_tags / post_tags
           |
           v
Search response: hits + highlight metadata
~~~

Ví dụ request:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 3,
        "pre_tags": ["<mark>"],
        "post_tags": ["</mark>"]
      }
    }
  }
}
~~~

Elasticsearch trả về document trong hits và các đoạn highlight trong thuộc tính highlight của từng hit. Nội dung gốc trong _source vẫn giữ nguyên.

## 2. Highlight không phải là query và không ảnh hưởng score

Query quyết định document nào được trả về. Highlight chỉ tạo phần trích dẫn cho những hit đó.

Ví dụ:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  },
  "highlight": {
    "fields": {
      "description": {}
    }
  }
}
~~~

Nếu bỏ phần highlight, cùng query vẫn trả về cùng tập document và cách tính score về cơ bản không đổi. Response chỉ không có fragment được đánh dấu.

Một số hệ quả:

- Highlight không làm một document không khớp trở thành khớp.
- Highlight không thay thế match, term, bool hoặc query khác.
- Highlight không tự sắp xếp document theo số lần từ khóa xuất hiện.
- Highlight không cập nhật _source hoặc ghi lại document.
- Có thể có hit hợp lệ nhưng không có fragment highlight, tùy field, query và highlighter.

Nếu cần tăng thứ hạng document có từ khóa trong title, hãy điều chỉnh query/boost. Nếu cần hiển thị phần văn bản khớp, dùng highlight. Đây là hai trách nhiệm khác nhau.

## 3. Khai báo field cần highlight

Highlight chỉ áp dụng cho field được chỉ định trong phần highlight.fields. Ví dụ chỉ đánh dấu title và description:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "fields": ["title^3", "description"]
    }
  },
  "highlight": {
    "fields": {
      "title": {},
      "description": {}
    }
  }
}
~~~

Nếu chỉ khai báo title, Elasticsearch không tự tạo fragment cho description. Ngược lại, một field được highlight phải có nội dung và kiểu mapping phù hợp với highlighter.

Có thể cấu hình mỗi field khác nhau:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  },
  "highlight": {
    "fields": {
      "title": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Ở đây title yêu cầu toàn bộ field thay vì các fragment nhỏ; description chỉ trả tối đa hai đoạn ngắn. Tùy chọn number_of_fragments: 0 có ý nghĩa trả toàn bộ field, nên cần thận trọng với văn bản dài.

Nếu field không có trong query nhưng vẫn muốn highlight theo query, hành vi có thể phụ thuộc highlighter và cấu hình require_field_match. Mặc định thường chỉ highlight field khớp với query. Chỉ tắt giới hạn này khi hiểu rõ tác động và có chủ đích.

## 4. Fragment là gì?

Một field text có thể dài hàng nghìn ký tự. Thay vì trả toàn bộ nội dung, highlighter chia hoặc chọn một số đoạn văn bản có liên quan, gọi là fragment.

Các tham số thường dùng:

| Tham số | Ý nghĩa |
|---|---|
| fragment_size | Độ dài mục tiêu của một fragment |
| number_of_fragments | Số fragment tối đa cần trả về |
| no_match_size | Số ký tự đầu field có thể trả về nếu không tìm thấy fragment khớp |
| order | Cách sắp xếp fragment, ví dụ theo score |
| pre_tags | Thẻ hoặc chuỗi đặt trước phần khớp |
| post_tags | Thẻ hoặc chuỗi đặt sau phần khớp |

Ví dụ:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 100,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Highlighter cố gắng chọn các đoạn có liên quan quanh vùng khớp. fragment_size là kích thước mục tiêu chứ không phải cam kết mọi fragment có chính xác số ký tự đó. Việc cắt đoạn còn phụ thuộc ranh giới từ, câu và highlighter.

### 4.1. Trả toàn bộ field

Nếu muốn lấy toàn bộ nội dung field trong phần highlight, đặt number_of_fragments bằng 0:

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

Cách này có thể hữu ích với field ngắn. Với mô tả dài hoặc tài liệu lớn, response có thể phình to và làm tăng băng thông, bộ nhớ cũng như thời gian render.

Nếu không có fragment nào được tạo và number_of_fragments khác 0, kết quả highlight có thể là danh sách rỗng hoặc field không xuất hiện, tùy query/highlighter. Có thể dùng no_match_size nếu muốn lấy một đoạn đầu field ngay cả khi không có vùng khớp.

### 4.2. no_match_size

no_match_size yêu cầu trả một đoạn đầu field khi highlighter không tìm được đoạn khớp. Ví dụ:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "title": "elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "number_of_fragments": 1,
        "no_match_size": 80
      }
    }
  }
}
~~~

Tùy chọn này hữu ích khi title khớp query nhưng ứng dụng vẫn muốn hiển thị một đoạn mở đầu của content. Cần nhớ đoạn no-match không phải bằng chứng content chứa từ khóa; nó chỉ là đoạn văn bản dự phòng.

## 5. Pre-tags và post-tags

pre_tags và post_tags là các chuỗi được thêm trước/sau vùng khớp. Có thể dùng thẻ HTML:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "description": {}
    }
  }
}
~~~

Response có thể chứa:

~~~json
{
  "highlight": {
    "description": [
      "A compact <mark>wireless</mark> <mark>mouse</mark> for travel."
    ]
  }
}
~~~

Có thể dùng thẻ riêng cho nhiều loại field hoặc nhiều loại ứng dụng:

~~~json
{
  "highlight": {
    "pre_tags": ["<strong class=\"search-hit\">"],
    "post_tags": ["</strong>"],
    "fields": {
      "title": {},
      "description": {}
    }
  }
}
~~~

Thẻ chỉ là chuỗi trong response. Frontend chịu trách nhiệm hiển thị an toàn. Không nên nối trực tiếp fragment vào HTML bằng cơ chế bỏ qua escaping mà chưa xử lý nội dung không tin cậy.

### 5.1. Encoder

Elasticsearch có tùy chọn encoder, ví dụ html, để encode nội dung văn bản trước khi thêm thẻ highlight trong các highlighter hỗ trợ. Điều này giúp xử lý ký tự HTML đặc biệt trong văn bản gốc.

Ví dụ:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring"
    }
  },
  "highlight": {
    "encoder": "html",
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {}
    }
  }
}
~~~

Hãy kiểm tra hỗ trợ của highlighter và API version đang dùng. Dù có encoder, frontend vẫn phải tuân theo chính sách render an toàn của ứng dụng. Không giả định fragment là HTML đáng tin cậy chỉ vì Elasticsearch đã thêm thẻ.

## 6. Các loại highlighter của Elasticsearch

Elasticsearch có ba highlighter phổ biến:

- unified
- plain
- fvh (Fast Vector Highlighter)

Nếu không chỉ định type, Elasticsearch thường dùng unified highlighter.

| Highlighter | Đặc điểm | Yêu cầu mapping thường gặp |
|---|---|---|
| unified | Highlighter mặc định, hỗ trợ nhiều loại query và có thể dùng postings offsets, term vectors hoặc reanalyze source | Không bắt buộc cấu hình đặc biệt cho mọi field |
| plain | Dựng một cấu trúc index nhỏ trong bộ nhớ để tìm các đoạn khớp | Không cần cấu hình term vector riêng |
| fvh | Tận dụng term vectors để tạo highlight nhanh và hỗ trợ matched fields | Field cần term_vector có positions và offsets |

Chọn highlighter theo mapping, kích thước field, query và yêu cầu hiệu năng. Không phải highlighter nào cũng hỗ trợ mọi tùy chọn giống nhau.

### 6.1. Unified highlighter

Unified là highlighter mặc định trong Elasticsearch hiện đại. Nó chia văn bản thành fragment và đánh giá fragment dựa trên query để chọn phần phù hợp.

Có thể chỉ định rõ:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 150,
        "number_of_fragments": 3,
        "order": "score"
      }
    }
  }
}
~~~

Unified có thể lấy offset từ postings, term vectors hoặc phân tích lại source tùy mapping. Với field text thông thường, thường có thể dùng unified mà không phải thay mapping. Khi cần tối ưu trên field lớn, cân nhắc index_options hoặc term_vector theo hướng dẫn Elasticsearch và đo trên dữ liệu thực tế.

### 6.2. Plain highlighter

Plain highlighter tạo một index nhỏ trong bộ nhớ cho từng field và document được highlight, rồi chạy lại query để tìm vùng khớp. Điều này giúp hỗ trợ nhiều query nhưng có thể tốn CPU và bộ nhớ khi số hit hoặc field lớn.

Ví dụ:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "plain",
        "fragment_size": 120
      }
    }
  }
}
~~~

Plain highlighter phù hợp với một số trường hợp đơn giản, nhưng không nên chọn chỉ vì tên gọi dễ hiểu. Nếu ứng dụng highlight lượng lớn document, cần đo chi phí và so sánh với unified/FVH.

### 6.3. Fast Vector Highlighter (fvh)

FVH sử dụng term vectors được lưu trong index để tìm vị trí term. Field cần mapping term_vector có positions và offsets, thường khai báo:

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

Query:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "fvh",
        "fragment_size": 150,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

FVH có thể phù hợp với field văn bản lớn hoặc yêu cầu highlight nâng cao. Đổi lại, lưu term vectors làm tăng kích thước index và chi phí indexing/storage. Cần cấu hình mapping trước khi index dữ liệu; thay đổi mapping hiện có thường đòi hỏi tạo index mới và reindex.

### 6.4. Postings offsets

Unified highlighter cũng có thể tận dụng offsets được lưu trong postings. Mapping có thể cấu hình:

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

Offsets giúp highlighter định vị phần văn bản khớp mà không phải phân tích lại toàn bộ source trong một số trường hợp. Tuy nhiên, nó làm tăng dữ liệu index. Cân nhắc giữa chi phí ghi/lưu trữ và chi phí highlight lúc query.

## 7. require_field_match

require_field_match kiểm soát việc highlighter có chỉ đánh dấu field được query trực tiếp hay không. Mặc định thường là true.

Ví dụ query trên title nhưng muốn highlight cả description:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "wireless mouse"
    }
  },
  "highlight": {
    "require_field_match": false,
    "fields": {
      "title": {},
      "description": {}
    }
  }
}
~~~

Khi false, highlighter có thể thử đánh dấu các term của query trên field được yêu cầu dù field đó không phải field query trực tiếp. Kết quả phụ thuộc mapping, analyzer và highlighter.

Không tắt require_field_match chỉ để "highlight tất cả". Với nhiều field khác analyzer, cùng một chuỗi query có thể được xử lý khác nhau. Hãy cấu hình field cụ thể và kiểm tra kết quả.

## 8. matched_fields và multi-fields

Một nội dung có thể được lập chỉ mục qua nhiều field với cách phân tích khác nhau. Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "analyzer": "standard",
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

Ứng dụng có thể query trên content.english để tận dụng stemming nhưng muốn highlight trên nội dung gốc content. matched_fields cho phép highlighter kết hợp thông tin khớp từ các field liên quan để đánh dấu field hiển thị.

Ví dụ minh họa:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content.english": "running"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "matched_fields": ["content", "content.english"]
      }
    }
  }
}
~~~

matched_fields cần các field biểu diễn cùng nội dung gốc hoặc có quan hệ multi-field phù hợp. Không dùng nó để kết hợp các field văn bản không liên quan. Khả năng hỗ trợ và điều kiện cụ thể khác nhau giữa unified và FVH; hãy kiểm tra tài liệu của Elasticsearch version đang triển khai.

## 9. Ranh giới fragment và boundary scanner

Highlighter cần quyết định vị trí bắt đầu/kết thúc của fragment. Một số tùy chọn giúp điều chỉnh cách cắt:

- boundary_scanner: cách tìm ranh giới fragment, ví dụ theo ký tự, từ hoặc câu tùy highlighter.
- boundary_chars: tập ký tự được xem là ranh giới.
- boundary_max_scan: số ký tự tối đa tìm quanh vị trí cắt.
- boundary_scanner_locale: locale dùng khi xác định ranh giới từ/câu trong các trường hợp hỗ trợ.

Ví dụ cấu hình:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 180,
        "number_of_fragments": 2,
        "boundary_scanner": "sentence",
        "boundary_scanner_locale": "vi-VN"
      }
    }
  }
}
~~~

Tên locale và cách cắt thực tế phụ thuộc highlighter/phiên bản. Với văn bản tiếng Việt, thử nghiệm trên dữ liệu có dấu câu, xuống dòng và câu dài để xem fragment có tự nhiên hay không. Không có một fragment_size duy nhất phù hợp với mọi ngôn ngữ và mọi giao diện.

## 10. Sắp xếp fragment

Khi number_of_fragments lớn hơn 1, có thể chọn cách sắp xếp các fragment. Ví dụ order: score yêu cầu fragment có score cao hơn đứng trước:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
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

Nếu không chọn order theo score, fragment thường theo thứ tự xuất hiện trong văn bản. Hãy chọn theo nhu cầu:

- Theo vị trí: phù hợp khi muốn người đọc theo dõi nội dung theo trình tự.
- Theo score: phù hợp khi muốn đoạn có mức khớp cao nhất xuất hiện trước.

Thứ tự fragment không làm thay đổi thứ tự document trong search hits. Muốn sắp xếp document, cần sort query riêng.

## 11. Highlight phrase và query phức tạp

Highlighter cố gắng phản ánh các term/phrase mà query khớp. Với match_phrase, có thể highlight cụm từ theo positions. Với bool, nested, synonym, fuzzy hoặc query phức tạp, kết quả highlight có thể khác kỳ vọng vì mỗi highlighter hỗ trợ và diễn giải query theo cách riêng.

Ví dụ:

~~~http
POST /articles/_search
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
        "fragment_size": 160
      }
    }
  }
}
~~~

slop cho phép một mức linh hoạt về khoảng cách/vị trí token theo semantics của phrase query. Highlighter có thể đánh dấu các term của phrase; nó không nhất thiết bọc toàn bộ cụm thành một thẻ duy nhất.

Với query có synonym hoặc nhiều nhánh bool, hãy test response thực tế. Không coi số fragment hoặc cách đánh dấu là một API hiển thị bất biến giữa các phiên bản Elasticsearch.

## 12. Highlight trên nested field

Nếu document chứa nested object, query có thể dùng nested query và highlight có thể cần cấu hình tương ứng để lấy đoạn văn bản trong nested hit.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "comments": {
        "type": "nested",
        "properties": {
          "message": {
            "type": "text"
          }
        }
      }
    }
  }
}
~~~

Query:

~~~http
POST /posts/_search
{
  "query": {
    "nested": {
      "path": "comments",
      "query": {
        "match": {
          "comments.message": "elasticsearch"
        }
      },
      "inner_hits": {
        "highlight": {
          "fields": {
            "comments.message": {}
          }
        }
      }
    }
  }
}
~~~

Với nested data, highlight có thể nằm trong inner_hits thay vì phần highlight cấp document cha. Spring Data cần đọc inner hit metadata theo API tương ứng. Nếu ứng dụng chỉ đọc highlight ở SearchHit cha, có thể bỏ sót fragment nằm trong nested hit.

Đây là trường hợp nên kiểm tra kỹ API của phiên bản Spring Data Elasticsearch đang dùng và viết integration test có nested document thực tế.

## 13. Response highlight từ Elasticsearch

Một hit có thể chứa cả _source và highlight:

~~~json
{
  "hits": {
    "hits": [
      {
        "_index": "articles",
        "_id": "A-1001",
        "_score": 4.2,
        "_source": {
          "title": "Spring Data Elasticsearch",
          "content": "Learn how Spring Data integrates with Elasticsearch."
        },
        "highlight": {
          "title": [
            "<mark>Spring Data Elasticsearch</mark>"
          ],
          "content": [
            "Learn how <mark>Spring Data</mark> integrates with <mark>Elasticsearch</mark>."
          ]
        }
      }
    ]
  }
}
~~~

highlight là map theo tên field. Mỗi field thường có danh sách fragment dạng chuỗi. Một field có thể có nhiều fragment, không nên giả định luôn chỉ có một chuỗi.

Highlight fragment là đoạn text đã được highlighter thêm tag. Nó không phải một object domain field mới và không nằm trong _source.

## 14. Tích hợp Highlight với Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp các abstraction để cấu hình highlight và truy cập fragment qua SearchHit.

Các kiểu thường gặp trong Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.elasticsearch.core.query.Highlight;
import org.springframework.data.elasticsearch.core.query.HighlightField;
import org.springframework.data.elasticsearch.core.query.HighlightParameters;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
~~~

Một cấu hình minh họa:

~~~java
HighlightField contentField = new HighlightField("content");

HighlightParameters parameters = HighlightParameters.builder()
    .withPreTags("<mark>")
    .withPostTags("</mark>")
    .withFragmentSize(150)
    .withNumberOfFragments(3)
    .build();

Highlight highlight = new Highlight(
    parameters,
    List.of(contentField)
);

HighlightQuery highlightQuery = new HighlightQuery(
    highlight,
    Article.class
);
~~~

Sau đó gắn vào NativeQuery:

~~~java
NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(textQuery)
    .withHighlightQuery(highlightQuery)
    .build();

SearchHits<Article> hits =
    operations.search(nativeQuery, Article.class);
~~~

Đây là hình dạng API thường gặp ở Spring Data Elasticsearch 5.x. Constructor, builder method, kiểu pre/post tags và package có thể khác theo minor version. Hãy xác nhận trên Javadoc/IDE của dependency trong project trước khi dùng nguyên mẫu.

Nếu project dùng API Spring Data Elasticsearch thế hệ cũ, lớp cấu hình highlight hoặc cách gắn vào query có thể khác. Không trộn các kiểu query từ RestHighLevelClient với Elasticsearch Java API Client trong cùng builder.

### 14.1. Đọc fragment từ SearchHit

Sau khi chạy search:

~~~java
for (SearchHit<Article> hit : hits) {
    Article article = hit.getContent();

    List<String> fragments =
        hit.getHighlightField("content");

    System.out.println(article.getTitle());

    for (String fragment : fragments) {
        System.out.println(fragment);
    }
}
~~~

SearchHit giữ content và metadata của từng hit. getHighlightField("content") trả danh sách fragment cho field đó theo API của Spring Data.

Có thể lấy toàn bộ map:

~~~java
Map<String, List<String>> highlightFields =
    hit.getHighlightFields();
~~~

Nếu field không được highlight hoặc không có fragment, danh sách có thể rỗng. Nên xử lý trường hợp này thay vì gọi get(0) trực tiếp.

### 14.2. Tạo DTO có highlight

Một response API có thể chứa tiêu đề, ID và các đoạn trích:

~~~java
public record ArticleSearchResult(
    String id,
    String title,
    float score,
    List<String> contentFragments
) {
}
~~~

Map từ SearchHit:

~~~java
List<ArticleSearchResult> results =
    hits.getSearchHits().stream()
        .map(hit -> new ArticleSearchResult(
            hit.getId(),
            hit.getContent().getTitle(),
            hit.getScore(),
            hit.getHighlightField("content")
        ))
        .toList();
~~~

Không nên nhét fragment highlight vào property content của entity. _source vẫn là nội dung gốc; fragment chỉ là representation dành cho kết quả tìm kiếm.

## 15. Highlight trong repository hay ElasticsearchOperations?

Repository là abstraction phù hợp với các truy vấn ổn định và method đơn giản. Với highlight, query thường cần cấu hình chi tiết hơn như fields, fragment size, tags, highlighter type và options.

ElasticsearchOperations cùng NativeQuery thường linh hoạt hơn khi cần:

- Chọn field highlight theo request.
- Tùy chỉnh fragment size hoặc số fragment.
- Kết hợp highlight với multi_match/bool query.
- Đọc score và highlight metadata cùng lúc.
- Dùng query DSL nâng cao.

Một số phiên bản có thể hỗ trợ highlight trong repository query qua @Query hoặc các cấu hình khác, nhưng không nên giả định mọi derived method đều có thể bật highlight. Kiểm tra API của version dự án.

Nếu endpoint có một cấu hình highlight cố định, có thể đóng gói query trong service hoặc repository fragment để tránh lặp builder code.

## 16. Highlight và multi-field

Một field có thể có multi-field:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          },
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

Ứng dụng có thể query title.english để dùng stemming nhưng muốn hiển thị fragment trên title gốc. matched_fields hoặc cấu hình highlight tương ứng có thể kết hợp các field liên quan, tùy highlighter hỗ trợ.

Không nên highlight title.keyword nếu mục tiêu là đoạn văn bản tự nhiên; keyword thường là một token nguyên vẹn và không được phân tích như text. Hãy highlight field text chứa nội dung hiển thị.

## 17. Highlight và source filtering

Highlight fragments là metadata trong response. Source filtering điều khiển phần _source được trả về. Hai tính năng có thể dùng cùng nhau:

~~~http
POST /articles/_search
{
  "_source": ["title", "author"],
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Response có thể chỉ chứa title và author trong _source, đồng thời vẫn chứa fragment content trong highlight.

Điều này hữu ích khi content dài và API chỉ cần hiển thị một đoạn trích. Tuy nhiên, nếu service cần content gốc để tạo DTO, source filter phải giữ field đó hoặc service phải dựa vào fragment.

Không nhầm source filtering với highlight. Một cái chọn source field được trả về; cái kia tạo các đoạn text có đánh dấu.

## 18. An toàn khi render highlight ở frontend

Highlight thường dùng HTML tag như <em> hoặc <mark>. Nội dung gốc trong Elasticsearch có thể chứa ký tự do người dùng nhập, chẳng hạn:

~~~text
< script >, dấu nháy, URL hoặc đoạn HTML
~~~

Nếu frontend đưa fragment vào DOM bằng cơ chế render HTML thô mà không có chính sách an toàn, nội dung có thể gây XSS tùy cách highlighter/encoder và dữ liệu được xử lý.

Nguyên tắc:

- Chọn pre_tags/post_tags cố định do server kiểm soát.
- Không lấy tag tùy ý từ request client.
- Cấu hình encoder phù hợp và kiểm tra hành vi trên dữ liệu thực tế.
- Dùng cơ chế render an toàn ở frontend.
- Nếu frontend cần render HTML highlight, chỉ cho phép markup dự kiến và sanitize theo chính sách ứng dụng.
- Không giả định fragment từ Elasticsearch luôn đáng tin cậy.
- Không dùng fragment làm nội dung HTML có quyền thực thi.

Có thể thay HTML tag bằng marker văn bản riêng rồi render qua component frontend, nếu kiến trúc ứng dụng muốn tránh HTML thô. Điều quan trọng là phân biệt phần text gốc và phần đánh dấu do server thêm.

## 19. Hiệu năng và lựa chọn mapping

Highlight có thể làm tăng chi phí search vì Elasticsearch phải tìm và tạo fragment cho mỗi hit được trả về. Các yếu tố ảnh hưởng:

- Số hit được highlight.
- Số field được highlight.
- Độ dài source field.
- Số fragment và fragment size.
- Loại highlighter.
- Analyzer và độ phức tạp của query.
- Có thể dùng postings offsets hoặc term vectors hay phải reanalyze source.

Một số cách kiểm soát:

- Chỉ highlight field thật sự hiển thị.
- Giới hạn số hit và số fragment.
- Chọn fragment_size phù hợp với UI.
- Tránh trả toàn bộ field dài nếu chỉ cần snippet.
- Đo unified/plain/FVH trên dữ liệu đại diện.
- Chỉ thêm term vectors hoặc postings offsets khi lợi ích xứng đáng với chi phí index.
- Không bật highlight cho mọi endpoint nếu không cần.
- Giữ query và highlight field có liên quan rõ ràng.

### 19.1. Chọn highlighter theo nhu cầu

| Tình huống | Hướng lựa chọn |
|---|---|
| Bắt đầu với field text thông thường | Unified mặc định |
| Cần cấu hình đơn giản và dữ liệu vừa phải | Unified hoặc plain sau khi đo |
| Field lớn, highlight thường xuyên, muốn tận dụng term vectors | Đánh giá FVH và term_vector positions_offsets |
| Muốn unified dùng offsets đã index | Đánh giá index_options offsets |
| Chỉ cần snippet ngắn | fragment_size nhỏ và number_of_fragments giới hạn |
| Cần toàn bộ field | number_of_fragments: 0, chỉ dùng khi nội dung có kích thước kiểm soát |

Không có highlighter tốt nhất cho mọi tình huống. Quyết định nên dựa trên query, mapping, dung lượng index, latency và số hit thực tế.

## 20. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Search có hit nhưng không có highlight | Chưa khai báo field, field không chứa phần khớp hoặc query/highlighter không tương thích | Kiểm tra highlight.fields, mapping và response raw |
| Highlight field rỗng | Không có fragment khớp hoặc no_match_size chưa cấu hình | Kiểm tra query và dùng no_match_size nếu cần đoạn dự phòng |
| Không highlight đúng từ đồng nghĩa/stemming | Analyzer hoặc matched_fields chưa phù hợp | Kiểm tra analyzer, mapping và highlighter |
| FVH báo lỗi mapping | Field chưa có term vectors với positions/offsets | Cấu hình term_vector và reindex |
| Fragment bị cắt giữa câu | fragment_size/boundary scanner chưa phù hợp | Điều chỉnh fragment_size, boundary_scanner và locale |
| Chỉ highlight một field | Chỉ khai báo field đó trong highlight.fields | Thêm các field cần hiển thị |
| Highlight field không nằm trong query | require_field_match mặc định true | Xem xét false nếu semantics mong muốn và test cẩn thận |
| DTO không có highlight | Đã lấy content rồi bỏ SearchHit metadata | Giữ SearchHit/SearchHits đến tầng map DTO |
| Nested highlight không xuất hiện | Highlight nằm trong inner_hits | Đọc inner hit metadata |
| Response quá lớn | Nhiều field/fragment hoặc number_of_fragments = 0 trên field dài | Giới hạn field, số hit và fragment |
| HTML hiển thị sai hoặc có rủi ro XSS | Tag/encoder/rendering không đồng bộ | Kiểm tra encoder và sanitize ở frontend |
| Thay mapping nhưng highlight không đổi | Index cũ chưa được reindex | Kiểm tra mapping/index thực tế và dữ liệu đã lập chỉ mục |

## 21. Kiểm thử highlighting

Nên dùng integration test với Elasticsearch thật hoặc Testcontainers để xác nhận response highlight. Mock SearchHit không kiểm tra được highlighter thực tế.

Ví dụ kịch bản:

1. Tạo index với field content kiểu text.
2. Lưu một document có cụm từ cần tìm.
3. Refresh index để Search API nhìn thấy document.
4. Gửi match query cùng highlight config.
5. Kiểm tra hit có tồn tại.
6. Kiểm tra highlight map chứa field content.
7. Kiểm tra fragment có pre-tag/post-tag dự kiến.
8. Kiểm tra document không có nội dung khớp có hành vi fallback đúng.

REST request minh họa:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Assertion ở tầng Spring Data:

~~~java
SearchHits<Article> hits =
    operations.search(nativeQuery, Article.class);

assertThat(hits.getTotalHits()).isGreaterThan(0);

SearchHit<Article> first = hits.getSearchHit(0);

List<String> fragments =
    first.getHighlightField("content");

assertThat(fragments).isNotEmpty();
assertThat(fragments.get(0)).contains("<mark>");
assertThat(fragments.get(0)).contains("</mark>");
~~~

Ví dụ minh họa; cấu hình NativeQuery và test fixture cần khớp API version. Nếu dùng highlighter khác hoặc encoder, hãy điều chỉnh assertion theo response thực tế.

Nên bổ sung test cho:

- Field thiếu hoặc null.
- Query không khớp field highlight.
- Nhiều fragment.
- Văn bản có tiếng Việt và dấu câu.
- Nội dung chứa ký tự HTML.
- Multi-field/matched_fields.
- Nested inner hits nếu ứng dụng dùng nested mapping.
- Source filtering kết hợp highlight.

## 22. Quy trình debug khi highlight không đúng

Khi response không có fragment hoặc đánh dấu sai, kiểm tra theo thứ tự:

1. Xác nhận query trả về document mong muốn.
2. Kiểm tra tên field trong highlight.fields có đúng mapping không.
3. Đọc mapping để xác nhận field là text/keyword và analyzer nào được dùng.
4. Gọi Analyze API để xem token được tạo.
5. Thử unified highlighter với cấu hình tối thiểu.
6. Kiểm tra require_field_match và matched_fields.
7. Nếu dùng FVH, xác nhận term_vector có positions và offsets.
8. Nếu dùng postings offsets, kiểm tra index_options.
9. Kiểm tra source filtering và nested inner_hits.
10. Xem raw Search response để phân biệt lỗi Elasticsearch với lỗi mapping SearchHit/DTO.

Mapping và highlighter có thể khác giữa các index nếu alias trỏ tới nhiều index. Nếu search qua alias nhiều index, hãy bảo đảm các field highlight có mapping tương thích.

## 23. Bảng tra cứu nhanh

| Nhu cầu | Cấu hình |
|---|---|
| Đánh dấu field text | highlight.fields |
| Thẻ đánh dấu | pre_tags / post_tags |
| Giới hạn đoạn trích | fragment_size |
| Giới hạn số đoạn | number_of_fragments |
| Lấy toàn bộ field | number_of_fragments: 0 |
| Đoạn dự phòng khi không khớp | no_match_size |
| Fragment liên quan trước | order: score |
| Chọn highlighter | type: unified / plain / fvh |
| Dùng term vectors | term_vector: with_positions_offsets cho FVH |
| Dùng postings offsets | index_options: offsets cho unified khi phù hợp |
| Highlight field khác field query | require_field_match: false nếu phù hợp |
| Kết hợp multi-fields | matched_fields theo highlighter hỗ trợ |
| Đọc fragment trong Spring Data | SearchHit.getHighlightField(name) |
| Giữ score và metadata | SearchHit<T> / SearchHits<T> |
| Highlight nested result | inner_hits highlight và đọc metadata inner hit |

Highlighting giúp kết quả tìm kiếm dễ hiểu hơn bằng cách trả về các fragment có đánh dấu phần văn bản khớp query. Hãy chọn field, fragment size, số fragment và highlighter phù hợp; dùng unified làm điểm bắt đầu, chỉ thêm term vectors hoặc postings offsets khi cần tối ưu đã đo được. Trong Spring Data Elasticsearch, giữ SearchHit/SearchHits để đọc highlight metadata, map fragment sang DTO riêng và render an toàn ở frontend.
