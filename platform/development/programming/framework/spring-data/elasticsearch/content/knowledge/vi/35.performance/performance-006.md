# Kiểm soát wildcard đầu chuỗi, script và truy vấn tốn tài nguyên

Một truy vấn Elasticsearch có thể trả kết quả đúng nhưng tiêu tốn CPU, heap, I/O và thời gian xử lý nhiều hơn mức cần thiết. Những trường hợp thường gặp gồm wildcard bắt đầu bằng dấu sao, regexp trên field có nhiều term, script phải chạy trên hàng triệu document, sort/aggregation trên field không có mapping phù hợp, hoặc phân trang sâu bằng from/size.

Trong Spring Data Elasticsearch, query DSL chỉ là cách ứng dụng gửi yêu cầu tới Elasticsearch. Việc dùng NativeQuery hay repository method không làm một query vốn tốn tài nguyên trở nên rẻ hơn. Muốn kiểm soát chi phí, cần hiểu cách query được thực thi, chọn mapping phù hợp, thu hẹp tập document trước khi chạy thao tác nặng và đo trên dữ liệu gần với production.

Bài này tập trung vào wildcard đầu chuỗi, prefix/substring search, script query và script sort, các loại truy vấn có chi phí cao, giới hạn ở cấp cluster, cách viết query qua Spring Data Elasticsearch, cùng công cụ profiling và giám sát.

## 1. Vì sao một số query tốn tài nguyên?

Elasticsearch lập chỉ mục document thành các cấu trúc như inverted index và doc values. Một query đơn giản có thể tìm term trực tiếp trong inverted index. Nhưng một số query cần tìm hoặc đánh giá rất nhiều term/document trước khi xác định kết quả.

Các yếu tố thường làm chi phí tăng:

- Pattern không có phần đầu cố định, ví dụ *timeout.
- Regex có thể khớp với lượng lớn term.
- Script phải chạy cho từng document trong tập ứng viên.
- Sort hoặc aggregation cần đọc giá trị trên nhiều document.
- Query không có filter đủ chọn lọc.
- Pagination yêu cầu bỏ qua quá nhiều kết quả.
- Aggregation tạo nhiều bucket hoặc cardinality cao.
- Request trả về quá nhiều hit hoặc quá nhiều source data.
- Nhiều truy vấn nặng chạy đồng thời trên cùng shard/node.

Chi phí không chỉ phụ thuộc số document cuối cùng trả về. Một request size 10 vẫn có thể tốn nhiều CPU nếu Elasticsearch phải xét hàng triệu ứng viên để tìm ra 10 kết quả.

## 2. Wildcard query hoạt động ra sao?

Wildcard query khớp term theo pattern. Hai ký tự phổ biến:

- * khớp với không hoặc nhiều ký tự.
- ? khớp với đúng một ký tự.

Ví dụ:

~~~json
{
  "query": {
    "wildcard": {
      "username.keyword": {
        "value": "admin*"
      }
    }
  }
}
~~~

Pattern admin* có phần đầu cố định. Elasticsearch có thể dùng phần tiền tố để thu hẹp term cần xét.

Pattern *admin thì không có phần đầu cố định. Để tìm các term kết thúc bằng admin, engine có thể phải xem xét rất nhiều term trong dictionary của field. Với field có cardinality cao, chi phí có thể lớn.

Pattern *admin* còn rộng hơn vì chuỗi có thể xuất hiện ở bất kỳ vị trí nào.

Ví dụ field path.keyword chứa hàng triệu URL hoặc đường dẫn:

~~~text
/api/v1/orders/timeout
/api/v1/users/timeout
/archive/timeout-report
/system/logs/timeout
...
~~~

Query:

~~~json
{
  "query": {
    "wildcard": {
      "path.keyword": "*timeout"
    }
  }
}
~~~

có thể cần xem xét rất nhiều term của path.keyword.

Các yếu tố ảnh hưởng:

- Số lượng distinct term.
- Độ dài term.
- Số shard được truy vấn.
- Số document có field.
- Selectivity của các filter đi kèm.
- Caching và trạng thái filesystem cache.
- Tải đồng thời trên node.

Một wildcard có vẻ nhỏ trong JSON vẫn có thể tạo lượng công việc lớn ở mỗi shard.

### 2.1. Wildcard không giống full-text search

Nếu người dùng muốn tìm sản phẩm theo từ khóa, dùng match query trên text field:

~~~json
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  }
}
~~~

Nếu cần exact match trên mã, dùng term query trên keyword:

~~~json
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

Nếu cần prefix, dùng prefix query hoặc mapping hỗ trợ prefix. Chỉ dùng wildcard khi pattern thực sự là một phần của yêu cầu tìm kiếm.

## 3. Vì sao leading wildcard đặc biệt tốn kém?

Inverted index được tổ chức để tìm term và document chứa term đó. Với pattern có prefix, engine có thể bắt đầu từ một vùng term hẹp hơn trong dictionary.

Với pattern bắt đầu bằng wildcard, chẳng hạn *error, không có ký tự đầu để giới hạn phạm vi. Engine có thể phải xét nhiều term để xác định term nào khớp pattern. Khi field chứa nhiều giá trị khác nhau, số term cần xét có thể tăng mạnh.

Ví dụ field path.keyword chứa hàng triệu URL hoặc đường dẫn. Query *timeout có thể phải xem xét nhiều term trên mỗi shard.

Các yếu tố ảnh hưởng gồm số distinct term, độ dài term, số shard, filter selectivity, cache và tải đồng thời. Một wildcard có vẻ nhỏ trong JSON vẫn có thể tạo lượng công việc lớn.

## 4. Chọn query thay thế theo mục đích

Trước khi tối ưu wildcard, hãy xác định người dùng thực sự muốn tìm kiểu gì.

| Yêu cầu | Cơ chế nên cân nhắc |
|---|---|
| Exact value | term query trên keyword |
| Full-text search | match query trên text |
| Bắt đầu bằng một prefix | prefix query |
| Autocomplete nhiều từ | search_as_you_type hoặc completion suggester tùy use case |
| Tìm substring bất kỳ | ngram index hoặc wildcard field |
| Kết thúc bằng suffix | Field đảo chuỗi rồi prefix query, nếu phù hợp |
| Pattern phức tạp | wildcard/regexp có giới hạn và đo tải |
| So sánh theo logic nghiệp vụ | Precompute field hoặc script sau khi filter hẹp |

Không thay wildcard bằng script chỉ vì script dễ viết hơn. Script thường phải chạy trên từng document ứng viên và có thể còn tốn hơn.

## 5. Dùng prefix query thay cho wildcard có prefix cố định

Nếu yêu cầu là tìm giá trị bắt đầu bằng một chuỗi, dùng prefix query:

~~~json
{
  "query": {
    "prefix": {
      "username.keyword": {
        "value": "admin"
      }
    }
  }
}
~~~

Query này thể hiện rõ semantics prefix và thường dễ tối ưu hơn wildcard tổng quát như admin*.

Prefix query vẫn có thể tốn kém nếu field có cardinality lớn hoặc mapping không hỗ trợ tối ưu prefix. Elasticsearch có thể hỗ trợ index_prefixes trên text field để tăng hiệu quả cho prefix query trong những giới hạn độ dài được cấu hình.

Ví dụ mapping:

~~~json
{
  "name": {
    "type": "text",
    "index_prefixes": {
      "min_chars": 2,
      "max_chars": 10
    }
  }
}
~~~

index_prefixes tạo thêm cấu trúc index cho các prefix trong khoảng đã chọn, tăng chi phí lưu trữ/indexing nhưng có thể giảm công việc của prefix query.

Chọn min_chars và max_chars theo pattern autocomplete thực tế. Không bật trên mọi text field nếu không có nhu cầu.

## 6. Autocomplete không nhất thiết cần wildcard

Với autocomplete tên sản phẩm hoặc người dùng, có các lựa chọn chuyên biệt.

### 6.1. search_as_you_type

Field type search_as_you_type tạo các sub-field hỗ trợ tìm kiếm khi người dùng nhập từng phần của cụm từ. Query thường dùng multi_match với type bool_prefix.

Mapping:

~~~json
{
  "name": {
    "type": "search_as_you_type"
  }
}
~~~

Query:

~~~json
{
  "query": {
    "multi_match": {
      "query": "wire mou",
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

Cách này phù hợp với autocomplete theo từ và thứ tự từ. Nó không phải công cụ substring tùy ý cho mọi vị trí ký tự.

### 6.2. Edge n-gram

Edge n-gram analyzer index các prefix của token. Ví dụ token wireless có thể tạo các term wi, wir, wire, wirel... theo giới hạn cấu hình.

Mapping/settings minh họa:

~~~json
{
  "settings": {
    "analysis": {
      "tokenizer": {
        "edge_prefix_tokenizer": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 12,
          "token_chars": ["letter", "digit"]
        }
      },
      "analyzer": {
        "prefix_index_analyzer": {
          "type": "custom",
          "tokenizer": "edge_prefix_tokenizer",
          "filter": ["lowercase"]
        },
        "prefix_search_analyzer": {
          "type": "custom",
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
        "analyzer": "prefix_index_analyzer",
        "search_analyzer": "prefix_search_analyzer"
      }
    }
  }
}
~~~

Edge n-gram phù hợp với prefix của từng token. Nó làm index lớn hơn vì mỗi token gốc tạo ra nhiều term. Chọn giới hạn gram và token_chars cẩn thận.

### 6.3. N-gram cho substring

Nếu yêu cầu là tìm chuỗi con ở bất kỳ vị trí nào, n-gram tokenizer có thể index các chuỗi con có độ dài nhất định.

Ví dụ với token mouse và gram size 3, các gram có thể gồm mou, ous, use. Query tìm ous có thể match token gốc.

N-gram làm tăng số term và kích thước index, đặc biệt với chuỗi dài. Cần cân nhắc min_gram/max_gram, ngôn ngữ và Unicode, dấu câu, normalization, chuỗi ngắn hơn min_gram, index size và indexing throughput. Có thể dùng n-gram để tạo candidate rồi kiểm tra chuỗi đầy đủ ở bước tiếp theo nếu semantics cần chính xác tuyệt đối.

## 7. Wildcard field type cho chuỗi máy sinh

Elasticsearch có field type wildcard dành cho các trường hợp tìm kiếm pattern trên chuỗi có cardinality cao, chẳng hạn log message, path hoặc identifier máy sinh.

Ví dụ mapping:

~~~json
{
  "properties": {
    "message": {
      "type": "wildcard"
    }
  }
}
~~~

Query:

~~~json
{
  "query": {
    "wildcard": {
      "message": {
        "value": "*connection reset*"
      }
    }
  }
}
~~~

Wildcard field được thiết kế để hỗ trợ grep-like wildcard/regexp trên chuỗi, có thể phù hợp hơn keyword thông thường cho loại workload này. Cơ chế nội bộ và trade-off khác keyword; nó không phải lựa chọn thay thế cho text full-text search.

Cần xác nhận hỗ trợ và hành vi theo Elasticsearch version. Đánh giá bằng dữ liệu thật, pattern thật và đo index size, indexing throughput, query latency.

Không mặc định wildcard field phù hợp cho sort, terms aggregation hoặc exact analytics giống keyword. Nếu cùng một dữ liệu cần nhiều use case, có thể cần multi-field hoặc field riêng cho từng cách truy cập.

## 8. Tìm suffix bằng cách đảo chuỗi

Nếu yêu cầu thường xuyên là tìm giá trị kết thúc bằng một suffix, có thể tạo một field phụ chứa chuỗi đảo ngược.

Ví dụ:

~~~text
Original:    service-timeout
Reversed:    tuoemit-ecivres
~~~

Suffix query timeout có thể chuyển thành prefix query trên reversed field:

~~~json
{
  "query": {
    "prefix": {
      "name.reversed": "tuoemit"
    }
  }
}
~~~

Cách này cần một normalizer/processor hoặc application logic để tạo field reversed khi index. Nó phù hợp khi suffix search là pattern phổ biến và ổn định.

Nhược điểm là phải duy trì field phụ nhất quán, xác định quy tắc Unicode và normalization, và thay đổi logic tạo field có thể cần reindex. Không dùng cách này cho tìm substring bất kỳ nếu n-gram hoặc wildcard field phù hợp hơn.

## 9. Giới hạn truy vấn đắt bằng search.allow_expensive_queries

Elasticsearch có setting search.allow_expensive_queries để kiểm soát một số loại query bị xem là tốn kém. Khi setting bị tắt, các query thuộc nhóm bị hạn chế có thể bị từ chối thay vì thực thi.

Những query chịu ảnh hưởng có thể bao gồm wildcard, regexp, fuzzy, script query và một số query khác; phạm vi chính xác phụ thuộc loại query và Elasticsearch version. Prefix query có thể được tối ưu trong một số cấu hình như index_prefixes, vì vậy không nên coi mọi prefix query đều giống leading wildcard.

Setting này là guardrail ở cấp cluster. Nó không tự biến query chậm thành query nhanh và không thay thế mapping/query design.

Ví dụ cấu hình cluster:

~~~http
PUT _cluster/settings
{
  "persistent": {
    "search.allow_expensive_queries": false
  }
}
~~~

Khi bật guardrail này, ứng dụng cần biết query nào có thể bị từ chối. Không triển khai thay đổi trên production mà chưa kiểm kê query, dashboard và người dùng phụ thuộc vào wildcard/regexp/script.

Nếu cần một query pattern đặc biệt, cân nhắc thiết kế index hoặc API riêng với giới hạn, quyền truy cập và resource budget phù hợp.

## 10. Script query là gì?

Script query cho phép đánh giá một biểu thức trên document để quyết định document có match hay không.

Ví dụ:

~~~json
{
  "query": {
    "script": {
      "script": {
        "source": "doc['price'].size() != 0 && doc['price'].value > params.minPrice",
        "params": {
          "minPrice": 100000
        }
      }
    }
  }
}
~~~

Script kiểm tra giá có tồn tại và lớn hơn ngưỡng.

Nếu cùng logic có thể biểu diễn bằng range query, nên dùng query native:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gt": 100000
      }
    }
  }
}
~~~

Range query có thể tận dụng cấu trúc index của numeric field. Script query thường phải đánh giá expression trên từng document ứng viên và ít có cơ hội tối ưu tương đương.

### 10.1. Thu hẹp tập document trước khi chạy script

Nếu script thực sự cần thiết, hãy kết hợp với filter chọn lọc:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "Accessories"
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01"
            }
          }
        },
        {
          "script": {
            "script": {
              "source": "doc['price'].size() != 0 && doc['price'].value * params.factor < params.limit",
              "params": {
                "factor": 1.1,
                "limit": 500000
              }
            }
          }
        }
      ]
    }
  }
}
~~~

Filter category và createdAt giúp thu hẹp candidate set trước khi script được đánh giá. Hiệu quả thực tế phụ thuộc query planner, shard và data distribution; đo bằng profile/metrics.

### 10.2. Kiểm tra field tồn tại trước khi đọc value

Không giả định mọi document đều có field. Với doc values, kiểm tra size trước khi dùng value:

~~~painless
if (doc['price'].size() == 0) {
    return false;
}
return doc['price'].value > params.minPrice;
~~~

Truy cập value khi field thiếu có thể làm script lỗi. Với multi-valued field, xác định rõ cần min, max, first hay kiểm tra mọi giá trị; value không đại diện cho toàn bộ semantics của array.

## 11. Doc values và _source trong script

Với field có doc values, script thường nên dùng:

~~~painless
doc['price'].value
~~~

thay vì đọc toàn bộ _source chỉ để lấy một giá trị đơn giản.

Doc values được tổ chức cho truy cập theo document. _source là JSON source và có chi phí load/parse khác. Tuy nhiên, không phải script context nào cũng hỗ trợ cùng một cách truy cập; cần xác nhận context.

Một số field type không hỗ trợ doc values hoặc đã tắt doc_values. Khi đó script phải dùng representation khác hoặc mapping cần thay đổi.

Đừng tắt doc_values trên field được script query, sort hoặc aggregation sử dụng.

## 12. Script query, script_score và script sort khác nhau

| Cơ chế | Mục đích | Chi phí thường gặp |
|---|---|---|
| Script query | Quyết định document có match không | Đánh giá script trên candidate documents |
| script_score | Tính điểm relevance tùy chỉnh | Tính script score cho document được query chọn |
| Script sort | Tính sort key bằng script | Tính giá trị sort cho nhiều hit/candidate |
| Runtime field | Tính field khi query chạy | Tính toán lặp lại theo document được truy cập |
| Ingest-time derived field | Tính trước khi index | Tăng chi phí ghi/storage, giảm tính toán lúc search |

Nếu một phép tính ổn định theo dữ liệu nguồn, tính trước field ở application hoặc ingest pipeline có thể giảm chi phí mỗi lần query.

Script_score phù hợp khi scoring thật sự cần công thức riêng. Trước khi dùng, lọc candidate bằng query native để script chỉ chạy trên tập nhỏ.

Script sort thường đắt hơn sort trên field có doc values. Nếu có thể, tạo field numeric/keyword dẫn xuất khi index và sort trực tiếp.

## 13. Script compilation cache và parameters

Elasticsearch biên dịch Painless script và có cơ chế cache compiled script. Nếu mỗi request tạo source code khác nhau bằng cách nối giá trị vào chuỗi script, cache có thể bị phân mảnh và tăng chi phí compile.

Không nên xây dựng script source bằng cách nối dữ liệu người dùng vào chuỗi. Nên dùng script source ổn định và truyền giá trị qua params:

~~~json
{
  "script": {
    "source": "doc['price'].value > params.threshold",
    "params": {
      "threshold": 250000
    }
  }
}
~~~

Lợi ích:

- Source ổn định, dễ cache.
- Giá trị động không thay đổi script identity.
- Giảm nguy cơ xây dựng script từ input không tin cậy.
- Dễ test và quan sát.

Vẫn cần giới hạn số lượng script khác nhau, kiểm soát compilation rate và dùng stored scripts khi phù hợp với chính sách triển khai.

## 14. Runtime fields có miễn phí không?

Runtime field cho phép định nghĩa field được tính khi query cần, thay vì lưu giá trị đã index. Chúng hữu ích khi cần linh hoạt hoặc thử nghiệm schema.

Ví dụ runtime field:

~~~json
{
  "runtime_mappings": {
    "priceWithTax": {
      "type": "double",
      "script": {
        "source": "if (doc['price'].size() != 0) emit(doc['price'].value * params.factor)",
        "params": {
          "factor": 1.1
        }
      }
    }
  },
  "query": {
    "range": {
      "priceWithTax": {
        "gte": 100000
      }
    }
  }
}
~~~

Runtime field có thể phải tính giá trị cho document được truy cập. Nếu query thường xuyên dùng field đó trên tập dữ liệu lớn, chi phí lặp lại có thể đáng kể.

Nếu logic ổn định và thường xuyên được dùng cho filter/sort/aggregation, cân nhắc materialize field khi index. Runtime field phù hợp cho nhu cầu linh hoạt hoặc dữ liệu ít được truy vấn theo cách đó.

## 15. Tránh script khi query native diễn đạt được logic

Một số phép toán có query native tương ứng:

| Nhu cầu | Query native nên cân nhắc |
|---|---|
| Lớn hơn/nhỏ hơn | range |
| Bằng một giá trị | term |
| Một trong danh sách | terms |
| Chuỗi bắt đầu bằng | prefix |
| Full-text | match |
| Khoảng thời gian | range trên date |
| Field tồn tại | exists |
| Kết hợp điều kiện | bool |
| Lọc theo nested object | nested |
| Sắp xếp số/ngày | Sort trên field có doc values |

Ví dụ không cần script:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "range": { "stock": { "gt": 0 } } },
        { "range": { "price": { "lte": 500000 } } }
      ]
    }
  }
}
~~~

Native query thường tận dụng cấu trúc index tốt hơn và dễ đọc hơn. Script chỉ nên dùng khi biểu thức không thể mô tả hợp lý bằng query native hoặc cần logic tùy chỉnh có đo đạc.

## 16. Các truy vấn tốn tài nguyên khác cần kiểm soát

### 16.1. Regexp query

Regexp có thể khớp nhiều term và biểu thức phức tạp có thể rất tốn kém. Tránh regex không giới hạn trên field có cardinality cao. Nếu pattern đơn giản là prefix, dùng prefix query.

~~~json
{
  "query": {
    "regexp": {
      "code.keyword": {
        "value": "ORD-[0-9]{6}"
      }
    }
  }
}
~~~

Giới hạn pattern đầu vào và không cho người dùng gửi regex tùy ý không kiểm soát nếu API công khai.

### 16.2. Fuzzy query

Fuzzy query tìm term gần giống theo edit distance. Nó hữu ích cho typo tolerance nhưng có thể mở rộng thành nhiều term candidate.

Giới hạn fuzziness, prefix_length, max_expansions và chỉ bật trên field/query có nhu cầu rõ ràng.

### 16.3. Terms query với danh sách lớn

Một terms query chứa danh sách rất lớn có thể làm request body lớn và tăng chi phí xử lý. Nếu danh sách được sinh từ một tập dữ liệu lớn, cân nhắc terms lookup hoặc thiết kế dữ liệu/index để filter hiệu quả hơn.

Không gửi hàng chục nghìn ID trong mỗi request nếu có cách biểu diễn quan hệ hoặc lọc khác phù hợp hơn.

### 16.4. Deep pagination

Dùng from/size để nhảy tới trang rất sâu buộc mỗi shard giữ nhiều kết quả hơn số hit cuối cùng trả về. Ví dụ from 100000, size 50 có thể tốn nhiều bộ nhớ và CPU.

Với pagination sâu, cân nhắc:

- search_after với sort ổn định.
- Point in Time (PIT) để giữ snapshot nhất quán trong lúc phân trang.
- Scroll cho batch extraction phù hợp, không dùng như pagination tương tác thông thường.

Ví dụ search_after:

~~~json
{
  "size": 50,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:00:00Z",
    "P-1001"
  ],
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

Giá trị search_after phải lấy từ sort values của hit cuối trang trước. Sort cần có tie-breaker ổn định để tránh trùng hoặc bỏ sót document.

### 16.5. Exact total hits

Nếu chỉ cần biết còn trang tiếp theo hay không, không nhất thiết phải tính chính xác tổng số hit trên toàn bộ index.

Có thể dùng track_total_hits false hoặc giới hạn ngưỡng phù hợp. Tính tổng chính xác trên tập rất lớn có thể tăng chi phí.

### 16.6. Aggregation cardinality cao

Terms aggregation với rất nhiều giá trị duy nhất có thể tạo nhiều bucket. Giới hạn size, lọc trước, dùng composite aggregation khi cần duyệt tất cả bucket hoặc tạo summary index nếu dashboard chạy lặp lại.

### 16.7. Nested query và join

Nested query phải xét cấu trúc nested documents. Parent-child join có chi phí riêng và cần cân nhắc dữ liệu/shard. Chỉ dùng khi semantics quan hệ yêu cầu; tránh query join rộng trên mọi document nếu có thể denormalize phù hợp.

## 17. Filter context và scoring context

Trong bool query, filter context phù hợp với điều kiện chỉ cần đúng/sai và không cần relevance score. Ví dụ category, active, tenantId và date range thường nên nằm trong filter.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "Accessories"
          }
        },
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  }
}
~~~

Filter context tránh tính điểm relevance cho các điều kiện đó. Một số filter có thể được query cache tùy loại query, segment và điều kiện sử dụng; không nên giả định mọi filter đều được cache.

Không chuyển mọi điều kiện sang filter một cách máy móc. Điều kiện cần scoring/relevance vẫn nên ở query context.

## 18. Đặt giới hạn cho request và query đầu vào

Một API tìm kiếm công khai nên giới hạn những thứ người dùng có thể yêu cầu:

- Kích thước page.
- Số lượng sort field.
- Số lượng aggregation và bucket size.
- Số lượng phần tử trong terms list.
- Độ dài wildcard/regexp pattern.
- Có cho phép leading wildcard hay không.
- Có cho phép script query hay không.
- Thời gian timeout.
- Số truy vấn đồng thời theo user/tenant.
- Quyền truy cập vào index/field.

Không nhận một Elasticsearch DSL JSON tùy ý từ client rồi chuyển thẳng xuống cluster. Hãy xây API tìm kiếm có contract và allowlist query features.

## 19. search timeout và cancellation

Có thể đặt timeout cho search request để giới hạn thời gian chờ:

~~~json
{
  "timeout": "2s",
  "query": {
    "wildcard": {
      "message": {
        "value": "*connection reset*"
      }
    }
  }
}
~~~

Timeout không đảm bảo mọi công việc đã dừng ngay lập tức trên tất cả shard. Đây là giới hạn thời gian thực thi/search response theo semantics Elasticsearch; cancellation và cleanup có thể diễn ra bất đồng bộ.

Ở application layer, cần phân biệt client timeout, Elasticsearch search timeout, proxy timeout, request cancellation do user disconnect và cluster overload/rejection.

Không coi timeout là bằng chứng query không tạo tác động. Với query có script hoặc side effect ở tầng ứng dụng, thiết kế retry và cancellation riêng.

## 20. Viết query qua Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp NativeQuery để gửi query DSL của Elasticsearch Java API Client trong các phiên bản hiện đại.

Ví dụ prefix query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.prefix(p -> p
        .field("username.keyword")
        .value("admin")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<UserDocument> hits =
    operations.search(query, UserDocument.class);
~~~

Ví dụ wildcard query khi pattern là yêu cầu thực sự:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.wildcard(w -> w
        .field("message")
        .value("*connection reset*")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Ví dụ filter native trước query full-text:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("description")
            .query("wireless mouse")
        ))
        .filter(f -> f.term(t -> t
            .field("category")
            .value("Accessories")
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(true)
        ))
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Tên builder, lambda và overload phụ thuộc Spring Data Elasticsearch/Java API Client version. Kiểm tra compile API của dependency dự án. Dù query được dựng qua NativeQuery, semantics và chi phí ở Elasticsearch vẫn như DSL tương ứng.

### 20.1. Script query qua Java API Client DSL

Script query có thể được biểu diễn bằng query DSL của Java API Client. Cấu trúc object builder tương đối dài, vì vậy hãy giữ source ổn định và truyền params riêng.

Painless source minh họa:

~~~painless
doc['price'].size() != 0 &&
doc['price'].value > params.minPrice
~~~

Nếu query có thể được biểu diễn bằng range, dùng range thay cho script. Nếu script bắt buộc, kết hợp filter chọn lọc và kiểm tra field tồn tại.

### 20.2. Repository method có thể che giấu chi phí

Một method như findByNameContaining có thể được triển khai theo query derivation của Spring Data. Đừng giả định nó tạo prefix, wildcard hay match query như mong muốn. Kiểm tra query thực tế được gửi hoặc dùng explicit query khi semantics và hiệu năng cần kiểm soát.

Với các truy vấn nhạy cảm hiệu năng, đặt tên method rõ ràng, test query DSL hoặc dùng NativeQuery để biểu diễn chính xác ý định.

## 21. Kiểm tra query bằng Profile API

Profile API cung cấp chi tiết về phần thực thi query trên shard.

Ví dụ:

~~~http
GET logs/_search
{
  "profile": true,
  "query": {
    "wildcard": {
      "message": {
        "value": "*connection reset*"
      }
    }
  }
}
~~~

Profile có thể giúp nhận biết query node nào chiếm thời gian, rewrite và term expansion, scoring hoặc collector tốn thời gian, aggregation nào tiêu tốn thời gian và khác biệt giữa các shard.

Profile có overhead và không đại diện đầy đủ latency end-to-end. Nó không bao gồm mọi chi phí network, queueing, fetch/serialization hoặc tải của client. Chỉ dùng có chủ đích trên dữ liệu và request phù hợp.

## 22. Slow logs, task API và node metrics

### 22.1. Search slow logs

Search slow logs giúp xác định query chậm theo shard. Có thể cấu hình ngưỡng cho query phase và fetch phase ở index settings, theo Elasticsearch version.

Slow log hữu ích để phát hiện wildcard/regexp pattern quá rộng, aggregation cardinality cao, script query/sort chậm, query chạy trên nhiều shard và fetch phase trả source quá lớn.

Không đặt ngưỡng quá thấp ngay từ đầu vì có thể tạo log volume rất lớn.

### 22.2. Task API

Một số search task có thể được quan sát qua Tasks API:

~~~http
GET _tasks?detailed=true&actions=indices:data/read/search*
~~~

API và action filters có thể thay đổi theo version. Dùng để quan sát task đang chạy lâu, cancel task khi phù hợp và xác định node thực hiện.

Cancel không đảm bảo mọi công việc dừng tức thì; theo dõi trạng thái task sau khi yêu cầu hủy.

### 22.3. Node stats và thread pools

Theo dõi CPU và heap, garbage collection, search thread pool active/queue/rejected, search latency và request rate, circuit breaker trips, filesystem/cache, disk I/O và merge pressure, shard count và query fan-out.

Ví dụ API:

~~~http
GET _nodes/stats/jvm,thread_pool,indices,breaker
~~~

Tên stats và cấu trúc response tùy Elasticsearch version. Đối chiếu metrics trước, trong và sau khi chạy workload để tìm tương quan.

## 23. Kiểm thử hiệu năng có kiểm soát

Không so sánh hai query bằng một lần chạy duy nhất. Cache, merge, refresh, shard placement và tải nền có thể làm kết quả khác nhau.

Một quy trình benchmark:

1. Dùng tập dữ liệu có cardinality và kích thước gần production.
2. Tạo mapping đại diện.
3. Warm up theo kịch bản thống nhất nếu workload production có warm cache.
4. Chạy query nhiều lần và ghi p50, p95, p99.
5. Đo CPU, heap, GC, queue/rejection và bytes transferred.
6. So sánh leading wildcard, prefix, ngram hoặc wildcard field.
7. So sánh script với query native hoặc precomputed field.
8. Thử tải đồng thời, không chỉ request đơn.
9. Kiểm tra kết quả có cùng semantics.
10. Ghi lại Elasticsearch/JDK version, shard count, mapping và dữ liệu test.

Không benchmark trên production bằng pattern cực rộng hoặc concurrency lớn nếu chưa có giới hạn và kế hoạch rollback.

## 24. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query *term chậm | Leading wildcard phải xét nhiều term | Dùng prefix/keyword design hoặc wildcard field/ngram |
| Prefix query vẫn chậm | Cardinality cao hoặc chưa tối ưu prefix | Xem index_prefixes, mapping và profile |
| Wildcard trên text không khớp chuỗi gốc | Analyzer đã tách token | Dùng keyword/wildcard field phù hợp |
| Autocomplete tạo nhiều wildcard query | Chọn sai search primitive | Dùng search_as_you_type hoặc edge n-gram |
| Script query tốn CPU | Script chạy trên quá nhiều candidate | Dùng native query hoặc filter hẹp trước |
| Script sort chậm | Tính sort key theo từng hit | Materialize field và sort bằng doc values |
| Script compile nhiều lần | Source thay đổi theo từng request | Dùng source ổn định và params |
| Script lỗi trên document thiếu field | Truy cập value mà không kiểm tra | Kiểm tra doc field size trước |
| Runtime field làm search chậm | Tính lại trên nhiều document mỗi request | Index field nếu được dùng thường xuyên |
| from/size trang sâu chậm | Mỗi shard phải giữ nhiều hit trung gian | search_after và PIT |
| Aggregation nhiều bucket tốn memory | Cardinality cao và bucket size lớn | Filter, top N hoặc composite aggregation |
| Query bị từ chối khi tắt expensive queries | Query thuộc nhóm bị giới hạn | Thiết kế lại hoặc cho phép có kiểm soát |
| Timeout nhưng cluster vẫn bận | Timeout không phải cancellation tức thời | Theo dõi task và giới hạn concurrency |
| Query repository chậm khó hiểu | Derived query tạo DSL ngoài dự kiến | Kiểm tra query thực tế và dùng NativeQuery |
| Profile cho kết quả khác production | Profile overhead và thiếu tải nền | Kết hợp slow logs/metrics/benchmark |

## 25. Quy trình thiết kế và kiểm soát query tốn tài nguyên

Khi thêm một search feature:

1. Xác định semantics: exact, full-text, prefix, substring hay regex.
2. Chọn field type và analyzer/normalizer tương ứng.
3. Ưu tiên query native có cấu trúc index hỗ trợ.
4. Tránh leading wildcard nếu có thể.
5. Nếu cần substring, đánh giá wildcard field hoặc n-gram và chi phí index.
6. Chỉ dùng script khi query native không đáp ứng.
7. Dùng doc values khi script cần truy cập field hỗ trợ.
8. Thu hẹp candidate set bằng filter trước script/aggregation nặng.
9. Giới hạn page size, bucket size, terms list và pattern length.
10. Dùng search_after/PIT cho pagination sâu.
11. Đặt timeout và concurrency budget.
12. Kiểm tra search.allow_expensive_queries theo query inventory.
13. Profile và benchmark trên dữ liệu đại diện.
14. Theo dõi slow logs, task, thread pool, heap và circuit breaker.
15. Viết integration/performance regression test cho query quan trọng.

## 26. Bảng tra cứu nhanh

| Yêu cầu | Lựa chọn nên cân nhắc |
|---|---|
| Exact match | term trên keyword |
| Full-text search | match trên text |
| Prefix | prefix query, index_prefixes hoặc edge n-gram |
| Autocomplete theo từ | search_as_you_type |
| Substring bất kỳ | n-gram hoặc wildcard field |
| Wildcard pattern tổng quát | wildcard có giới hạn và đo tải |
| Script logic đơn giản | Thay bằng range/term/bool nếu có thể |
| Script bắt buộc | Filter hẹp, source ổn định, params |
| Sort theo phép tính ổn định | Precompute field và doc values |
| Deep pagination | search_after và PIT |
| Không cần tổng hit chính xác | track_total_hits false/threshold |
| Aggregation cardinality cao | Filter, top N hoặc composite aggregation |
| Query quá đắt | expensive-query guardrail, timeout và rate limit |
| Chẩn đoán query chậm | Profile, slow logs, Tasks API, node stats |

Kiểm soát wildcard đầu chuỗi và script bắt đầu từ việc chọn đúng semantics tìm kiếm. Leading wildcard như *term có thể phải xét nhiều term và trở nên đắt trên field cardinality cao; prefix query, search_as_you_type, n-gram hoặc wildcard field phù hợp hơn tùy yêu cầu. Script query, script_score, script sort và runtime field cần được dùng có chủ đích, với filter thu hẹp candidate set và source/params ổn định. Ưu tiên query native, giới hạn pagination/aggregation/request đầu vào, kiểm tra expensive-query guardrail và đo bằng Profile API, slow logs, task/thread-pool và heap metrics. Spring Data Elasticsearch không làm thay đổi chi phí thực thi của DSL; hãy kiểm tra query thực tế và benchmark trên dữ liệu đại diện trước khi phát hành tính năng tìm kiếm.
