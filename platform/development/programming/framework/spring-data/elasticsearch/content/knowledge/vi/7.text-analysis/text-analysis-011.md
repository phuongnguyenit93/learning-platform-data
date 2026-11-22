# Thay đổi analyzer, reindex và kiểm thử chất lượng tìm kiếm

Trong Elasticsearch, analyzer quyết định cách văn bản được biến đổi thành các token để lập chỉ mục và truy vấn. Một thay đổi nhỏ như bỏ stop word, thêm stemming, đổi tokenizer hoặc bổ sung synonym có thể làm thay đổi tập document được tìm thấy và thứ tự kết quả. Vì vậy, thay đổi analyzer cần được xem là một thay đổi đối với hợp đồng tìm kiếm của index.

Khi thay đổi cách phân tích văn bản ở thời điểm index, dữ liệu đã lập chỉ mục không tự được phân tích lại. Muốn áp dụng analyzer mới cho dữ liệu cũ, cần tạo index với settings/mapping mới rồi reindex document. Sau đó phải kiểm thử chất lượng tìm kiếm trước khi chuyển ứng dụng sang index mới.

Quy trình tổng quát:

```text
Phân tích vấn đề tìm kiếm
          |
          v
Thiết kế analyzer mới
          |
          v
Kiểm tra token bằng _analyze
          |
          v
Tạo index mới + mapping mới
          |
          v
Reindex dữ liệu
          |
          v
Kiểm thử chức năng và relevance
          |
          v
Chuyển alias sang index mới
          |
          v
Theo dõi kết quả thực tế và giữ phương án rollback
```

## 1. Analyzer ảnh hưởng đến tìm kiếm như thế nào?

Analyzer là một chuỗi các bước xử lý văn bản. Với field kiểu `text`, Elasticsearch thường dùng analyzer khi lập chỉ mục và có thể dùng analyzer khác khi phân tích nội dung truy vấn.

Một analyzer tùy chỉnh thường gồm ba thành phần, theo thứ tự:

1. **Character filters:** biến đổi văn bản đầu vào trước khi tokenization, ví dụ loại bỏ HTML hoặc thay thế ký tự.
2. **Tokenizer:** chia văn bản thành các token theo quy tắc, ví dụ tách theo ranh giới từ.
3. **Token filters:** biến đổi token, ví dụ lowercase, bỏ stop word, stemming, asciifolding hoặc synonym.

Ví dụ với câu `The QUICK brown foxes!`:

```text
Input
  "The QUICK brown foxes!"
       |
       v
Tokenizer
  [The] [QUICK] [brown] [foxes]
       |
       v
Lowercase filter
  [the] [quick] [brown] [foxes]
       |
       v
Stop filter
  [quick] [brown] [foxes]
       |
       v
English stemmer
  [quick] [brown] [fox]
```

Kết quả cuối cùng là các token được đưa vào inverted index. Khi người dùng tìm `fox`, document chứa `foxes` có thể được tìm thấy nếu analyzer lúc index và analyzer lúc search tạo ra các token tương thích.

### Index analyzer và search analyzer

- `analyzer` là analyzer dùng khi phân tích giá trị field lúc index.
- `search_analyzer` là analyzer dùng khi phân tích nội dung query cho field đó.

Hai analyzer có thể giống nhau hoặc khác nhau. Ví dụ, một field có thể index với tokenizer tiêu chuẩn và lowercase, trong khi search analyzer bổ sung synonym để người dùng có thể tìm bằng từ đồng nghĩa.

```json
PUT /articles-v1
{
  "settings": {
    "analysis": {
      "analyzer": {
        "article_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        },
        "article_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "article_index",
        "search_analyzer": "article_search"
      }
    }
  }
}
```

Ví dụ trên khai báo hai analyzer riêng để có thể điều chỉnh độc lập sau này. Trong trường hợp chúng có cùng chuỗi xử lý, có thể dùng chung một analyzer.

## 2. Khi nào cần thay đổi analyzer?

Một số dấu hiệu cho thấy analyzer hiện tại không phù hợp:

- Người dùng tìm đúng nội dung nhưng không tìm thấy document vì khác chữ hoa/chữ thường hoặc dấu.
- Các dạng từ biến đổi như số ít/số nhiều không được khớp như mong muốn.
- Ký tự đặc biệt hoặc dấu câu làm tokenization không đúng với ngôn ngữ và dữ liệu.
- Tên sản phẩm, từ viết tắt hoặc thuật ngữ đồng nghĩa cần được tìm thấy cùng nhau.
- Tìm kiếm autocomplete cần khớp tiền tố thay vì chỉ khớp token hoàn chỉnh.
- Kết quả trả về quá nhiều document không liên quan do analyzer tạo token quá rộng hoặc giữ lại stop word không cần thiết.

Không phải vấn đề tìm kiếm nào cũng giải quyết bằng analyzer. Nếu field được mapping thành `keyword` nhưng ứng dụng lại dùng full-text query, cần xem lại kiểu field và query. Nếu query sai tên field, sửa analyzer không giúp ích. Nếu dữ liệu chưa refresh, search có thể chưa nhìn thấy document mới. Hãy xác định nguyên nhân trước khi thay đổi cấu hình phân tích.

## 3. Thiết kế analyzer mới

Giả sử hệ thống tìm kiếm bài viết tiếng Anh và muốn:

- Chuẩn hóa chữ hoa/thường.
- Bỏ dấu tiếng Anh để hỗ trợ truy vấn không dấu.
- Loại bỏ một số stop word.
- Chuẩn hóa các dạng từ bằng stemming.

Có thể khai báo custom analyzer:

```json
PUT /articles-analyzer-v2
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stop_filter": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "english_stemmer_filter": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "article_text": {
          "type": "custom",
          "char_filter": ["html_strip"],
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding",
            "english_stop_filter",
            "english_stemmer_filter"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "article_text"
      },
      "body": {
        "type": "text",
        "analyzer": "article_text"
      },
      "category": {
        "type": "keyword"
      },
      "published_at": {
        "type": "date"
      }
    }
  }
}
```

Analyzer `article_text` thực hiện các bước:

1. `html_strip` loại bỏ markup HTML khỏi nội dung.
2. `standard` chia nội dung thành token.
3. `lowercase` chuyển token về chữ thường.
4. `asciifolding` chuẩn hóa một số ký tự có dấu về dạng ASCII tương ứng.
5. `english_stop_filter` loại bỏ stop word tiếng Anh.
6. `english_stemmer_filter` đưa một số biến thể từ về dạng gốc.

Thứ tự filter có ý nghĩa. Ví dụ, lowercase trước stop filter giúp so khớp stop word không phụ thuộc chữ hoa/thường. Stemming và synonym cũng có thể tương tác; cần thử với các câu thực tế trước khi quyết định thứ tự.

### Synonym và synonym graph

Nếu người dùng tìm `tv` nhưng tài liệu dùng `television`, có thể dùng synonym filter. Với search analyzer, `synonym_graph` thường phù hợp hơn khi xử lý synonym trong truy vấn có nhiều từ hoặc phrase query.

Ví dụ analyzer ở thời điểm search:

```json
PUT /articles-synonyms-v1
{
  "settings": {
    "analysis": {
      "filter": {
        "article_synonyms": {
          "type": "synonym_graph",
          "synonyms": [
            "tv, television",
            "car, automobile"
          ]
        }
      },
      "analyzer": {
        "article_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "article_synonyms"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "body": {
        "type": "text",
        "analyzer": "standard",
        "search_analyzer": "article_search"
      }
    }
  }
}
```

Ví dụ này minh họa synonym được áp dụng khi phân tích query. Nếu chỉ thay đổi search analyzer mà token đã index vẫn tương thích, thường không cần lập chỉ mục lại toàn bộ document. Tuy nhiên, phải kiểm tra khả năng cập nhật/reload analyzer theo phiên bản Elasticsearch, vì analyzer và filter đã được cấu hình trong index có các ràng buộc vòng đời riêng.

Synonym không nên được thêm tùy tiện. Quy tắc quá rộng có thể làm tăng false positive, khiến kết quả không còn đúng ý định người dùng. Nên có danh sách synonym được quản lý, ví dụ theo domain sản phẩm, thuật ngữ viết tắt hoặc từ đồng nghĩa đã được xác nhận.

### Analyzer cho autocomplete

Autocomplete theo tiền tố có thể dùng `edge_ngram` ở index analyzer và analyzer đơn giản hơn khi search. Ví dụ:

```json
PUT /products-suggest-v2
{
  "settings": {
    "analysis": {
      "filter": {
        "product_prefix_filter": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 15
        }
      },
      "analyzer": {
        "product_prefix_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "product_prefix_filter"]
        },
        "product_prefix_search": {
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
        "analyzer": "product_prefix_index",
        "search_analyzer": "product_prefix_search"
      }
    }
  }
}
```

Với từ `spring`, edge n-gram có thể tạo các tiền tố như `sp`, `spr`, `spri`, ... theo giới hạn gram đã cấu hình. Điều này giúp query prefix khớp khi người dùng mới nhập một phần từ. Đổi lại, số token được lưu tăng lên và index có thể lớn hơn.

`edge_ngram` và `ngram` khác nhau: edge n-gram tạo các chuỗi con bắt đầu từ đầu token, còn n-gram tạo nhiều chuỗi con ở các vị trí khác nhau. Với autocomplete theo tiền tố, edge n-gram thường phù hợp và tiết kiệm hơn.

## 4. Kiểm tra analyzer bằng `_analyze` trước khi reindex

Không nên tạo index production hoặc reindex hàng triệu document chỉ để xem analyzer có tạo token như mong muốn hay không. API `_analyze` cho phép kiểm tra kết quả xử lý trực tiếp.

Kiểm tra analyzer đã khai báo trong index:

```json
POST /articles-analyzer-v2/_analyze
{
  "analyzer": "article_text",
  "text": "The QUICK brown foxes are running."
}
```

Response trả về danh sách token, vị trí và offset. Có thể dùng kết quả để xác nhận lowercase, stop word, stemming và các filter khác hoạt động như dự kiến.

Kiểm tra tokenizer/filter riêng lẻ:

```json
POST /_analyze
{
  "tokenizer": "standard",
  "filter": ["lowercase", "asciifolding"],
  "text": "Crème Brûlée"
}
```

Kiểm tra analyzer ở thời điểm search:

```json
POST /articles-synonyms-v1/_analyze
{
  "analyzer": "article_search",
  "text": "TV and automobiles"
}
```

Nên chuẩn bị một tập input đại diện cho dữ liệu thật:

- Chữ hoa/thường, dấu câu và ký tự đặc biệt.
- Từ có dấu và không dấu.
- Từ viết tắt, tên riêng và thuật ngữ domain.
- Số, mã sản phẩm, email hoặc chuỗi định danh.
- Từ số ít/số nhiều và các biến thể cần stemming.
- Cụm từ nhiều từ và phrase query.

Đừng chỉ kiểm tra một câu ví dụ đẹp. Analyzer có thể xử lý tốt câu đơn giản nhưng làm hỏng mã sản phẩm, tên riêng hoặc từ chuyên ngành.

## 5. Vì sao thay đổi analyzer thường cần reindex?

Khi document được index, analyzer tạo token và Elasticsearch lưu chúng trong inverted index. `_source` vẫn giữ nội dung gốc (nếu `_source` được bật), nhưng token đã tạo không tự thay đổi khi ta sửa cấu hình analyzer.

Ví dụ ban đầu analyzer không dùng stemming:

```text
Document text: "running"
Indexed token: "running"
```

Sau đó analyzer mới dùng stemming:

```text
Document text: "running"
New indexed token: "run"
```

Nếu chỉ đổi analyzer ở query time, query có thể được phân tích thành `run` nhưng document cũ vẫn có token `running`. Kết quả có thể không khớp như mong muốn. Để dữ liệu cũ có token mới, cần index lại document bằng analyzer mới.

Các điểm cần phân biệt:

- **Thay đổi index analyzer:** ảnh hưởng token được lưu trong inverted index; cần reindex dữ liệu hiện có để áp dụng đầy đủ.
- **Thay đổi search analyzer:** thay đổi cách phân tích query. Nếu token đã index tương thích với cách query mới, có thể không cần reindex, nhưng cần kiểm tra mapping và khả năng cập nhật analyzer của phiên bản đang dùng.
- **Thay đổi mapping field hoặc kiểu dữ liệu:** có thể không cập nhật được trực tiếp trên field đã tồn tại; thường cần index mới và migration.
- **Thay đổi `_source`:** là thay đổi dữ liệu document, không chỉ là thay đổi analyzer; cần cập nhật/reindex dữ liệu theo yêu cầu.

Với thay đổi quan trọng, tạo index mới là cách dễ kiểm soát và có thể rollback hơn. Không nên dựa vào việc thay settings tại chỗ để kỳ vọng Elasticsearch tự xây dựng lại toàn bộ inverted index.

## 6. Reindex sang index mới

Reindex API đọc document từ source index và ghi document vào destination index. Nó chuyển nội dung `_source`; nó không tự sao chép settings, mapping, alias hoặc template từ source sang destination. Vì vậy, cần tạo destination index trước với analyzer, mapping và settings mong muốn.

Giả sử index cũ là `articles-v1`, index mới là `articles-v2`.

### Bước 1: Tạo index đích

Tạo `articles-v2` với analyzer mới và mapping đã kiểm thử bằng `_analyze`:

```json
PUT /articles-v2
{
  "settings": {
    "analysis": {
      "analyzer": {
        "article_text_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "article_text_v2"
      },
      "body": {
        "type": "text",
        "analyzer": "article_text_v2"
      },
      "category": {
        "type": "keyword"
      }
    }
  }
}
```

### Bước 2: Chạy reindex

```json
POST /_reindex?wait_for_completion=true
{
  "source": {
    "index": "articles-v1"
  },
  "dest": {
    "index": "articles-v2"
  }
}
```

Elasticsearch đọc `_source` của từng document trong `articles-v1`, sau đó index vào `articles-v2`. Analyzer của index đích được áp dụng khi ghi document mới, nhờ vậy inverted index được xây dựng lại theo cấu hình mới.

Nếu tập dữ liệu lớn, có thể chạy reindex bất đồng bộ bằng `wait_for_completion=false`. API trả về task id để theo dõi tiến trình qua Tasks API. Cần quan sát số document đã xử lý, lỗi, version conflict và tài nguyên cluster trong khi chạy.

### Bước 3: Xác minh kết quả reindex

So sánh số document:

```http
GET /articles-v1/_count
GET /articles-v2/_count
```

Kiểm tra mapping:

```http
GET /articles-v2/_mapping
```

Kiểm tra một số document mẫu:

```http
GET /articles-v2/_doc/article-100
```

Count bằng nhau là một tín hiệu cần thiết nhưng chưa đủ. Cần kiểm tra document quan trọng, field bị thiếu, kiểu dữ liệu, lỗi parse, các query nghiệp vụ và kết quả tìm kiếm. Nếu có script, pipeline hoặc transform trong quá trình reindex, cần kiểm tra kỹ dữ liệu đầu ra.

### Bước 4: Chuyển alias

Ứng dụng nên truy cập index qua một alias ổn định, ví dụ `articles`, thay vì gắn chặt với tên vật lý `articles-v1`. Khi index mới đã sẵn sàng, có thể chuyển alias bằng một request `_aliases`:

```json
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "articles-v1",
        "alias": "articles"
      }
    },
    {
      "add": {
        "index": "articles-v2",
        "alias": "articles",
        "is_write_index": true
      }
    }
  ]
}
```

Các thao tác alias trong cùng request được áp dụng nguyên tử ở cấp cluster state. Ứng dụng tiếp tục dùng tên `articles`; sau chuyển đổi, alias trỏ đến index mới.

Nếu hiện tại `articles` đang là tên của một concrete index chứ chưa phải alias, không thể thêm alias cùng tên khi index đó vẫn tồn tại. Cần lập kế hoạch chuyển đổi tên/alias phù hợp trước lần migration đầu tiên.

## 7. Bảo đảm dữ liệu không bị mất trong lúc reindex

Reindex là một tác vụ đọc source và ghi destination trong một khoảng thời gian. Nếu ứng dụng vẫn tiếp tục cập nhật source, các thay đổi phát sinh sau khi reindex đã đi qua document tương ứng có thể chưa có ở destination. Vì vậy, quy trình production cần xử lý ghi đồng thời.

Một số chiến lược:

### Tạm dừng ghi trong cửa sổ chuyển đổi

1. Chặn hoặc tạm dừng các thao tác ghi vào source.
2. Chạy reindex đến khi hoàn tất.
3. Xác minh dữ liệu và query.
4. Chuyển alias sang destination.
5. Mở lại ghi qua alias.

Chiến lược này đơn giản, dễ hiểu nhưng có downtime ghi trong khoảng chuyển đổi.

### Đồng bộ thay đổi trong lúc migration

Với hệ thống cần giảm downtime, có thể dùng dual-write hoặc change data capture/outbox để đưa các thay đổi mới sang destination trong lúc reindex. Tuy nhiên, cần xử lý thứ tự event, ghi lặp, delete, retry và xung đột phiên bản. Một quy trình thường gồm:

1. Bắt đầu ghi nhận thay đổi từ source bằng outbox/CDC.
2. Chạy reindex dữ liệu nền sang destination.
3. Phát lại các thay đổi phát sinh trong thời gian reindex.
4. Đối soát và bắt kịp đến một checkpoint rõ ràng.
5. Chuyển alias và hướng ghi/đọc sang destination.

Dual-write trực tiếp từ request thread vào hai index có thể tạo trạng thái lệch khi một bên thành công và bên kia thất bại. Nếu dùng, phải có retry, idempotency và quy trình đối soát; outbox/CDC thường giúp quản lý nguồn sự thật và replay rõ ràng hơn.

### Giữ khả năng rollback

Không xóa index cũ ngay sau khi chuyển alias. Giữ lại trong khoảng thời gian đủ để theo dõi lỗi, đối chiếu kết quả và rollback. Nếu cần quay lại, chuyển alias về index cũ bằng một request alias phù hợp. Chỉ xóa index cũ sau khi xác nhận index mới ổn định và có backup theo chính sách vận hành.

## 8. Reindex với xử lý bổ sung

Reindex có thể kết hợp script hoặc ingest pipeline để chuyển đổi dữ liệu trong quá trình sao chép. Ví dụ đổi tên field trong `_source` hoặc bổ sung giá trị mặc định:

```json
POST /_reindex
{
  "source": {
    "index": "articles-v1"
  },
  "dest": {
    "index": "articles-v2"
  },
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.containsKey('old_title')) { ctx._source.title = ctx._source.remove('old_title'); }"
  }
}
```

Script chỉ là ví dụ minh họa. Với chuyển đổi phức tạp, nên kiểm thử trên bản sao dữ liệu và giới hạn phạm vi trước khi chạy production. Reindex không phải công cụ thay thế backup; một script sai có thể ghi dữ liệu đích không mong muốn.

Nếu dùng ingest pipeline, khai báo pipeline ở destination và chỉ định `pipeline` trong phần `dest` của request reindex. Cần xác minh pipeline có xử lý được toàn bộ dữ liệu cũ, bao gồm document thiếu field hoặc có kiểu dữ liệu khác thường.

## 9. Khai báo analyzer trong Spring Data Elasticsearch

Spring Data Elasticsearch cho phép mô tả mapping trên entity bằng annotation. `@Field` có thể chỉ định `analyzer` và `searchAnalyzer`:

```java
@Document(indexName = "articles-spring-data-v2")
public class ArticleDocument {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "article_text",
        searchAnalyzer = "article_search"
    )
    private String title;

    @Field(
        type = FieldType.Text,
        analyzer = "article_text",
        searchAnalyzer = "article_search"
    )
    private String body;

    @Field(type = FieldType.Keyword)
    private String category;
}
```

Định nghĩa analyzer và token filter thuộc index settings, không chỉ nằm trong annotation field. Có thể quản lý settings bằng resource JSON/YAML theo cơ chế `@Setting` hoặc tạo index qua `IndexOperations` với settings và mapping rõ ràng. API cụ thể cần đối chiếu phiên bản Spring Data Elasticsearch đang dùng.

Ví dụ cấu hình settings dạng resource có thể chứa:

```json
{
  "analysis": {
    "analyzer": {
      "article_text": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      },
      "article_search": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }
}
```

Trong ứng dụng, cần quyết định rõ ai sở hữu việc tạo index. Nếu Spring Data tự động tạo index từ entity, hãy bảo đảm settings resource được áp dụng trước khi dữ liệu được ghi. Nếu index do deployment/migration quản lý, cần tắt hoặc tránh các hành vi tự tạo index ngoài kế hoạch để không tạo mapping thiếu analyzer.

`@Document(indexName = "articles-spring-data-v2")` có thể gắn entity với tên index phiên bản mới trong giai đoạn migration. Với môi trường dùng alias, có thể cấu hình tên index logic/alias theo cách tương thích với phiên bản Spring Data và cơ chế quản lý index của ứng dụng. Điều quan trọng là mapping thực tế của index đích phải tồn tại trước khi repository ghi dữ liệu.

## 10. Kiểm thử chất lượng tìm kiếm

Kiểm thử analyzer chỉ xác nhận token được tạo ra như dự kiến. Nó chưa chứng minh kết quả search tốt hơn. Chất lượng tìm kiếm cần được đánh giá bằng tập truy vấn đại diện và các document liên quan đã được xác định.

### Bộ dữ liệu đánh giá

Chuẩn bị một tập query phản ánh cách người dùng thực sự tìm kiếm. Với mỗi query, ghi lại các document được đánh giá là liên quan và mức độ liên quan nếu có.

Ví dụ:

| Query | Document liên quan mong đợi | Ghi chú |
|---|---|---|
| `spring data elasticsearch` | `doc-10`, `doc-14` | Tìm theo cụm từ công nghệ. |
| `tv` | `doc-21`, `doc-22` | Kiểm tra synonym với `television`. |
| `running` | `doc-31`, `doc-32` | Kiểm tra stemming. |
| `crème brûlée` | `doc-41` | Kiểm tra dấu và asciifolding. |
| `SKU-AX100` | `doc-50` | Kiểm tra mã định danh không bị analyzer phá vỡ. |

Đây là dữ liệu ví dụ. Bộ kiểm thử thật cần dựa trên domain, ngôn ngữ, dữ liệu và hành vi người dùng của ứng dụng.

### Precision và Recall

- **Precision@k:** trong k kết quả đầu tiên, có bao nhiêu kết quả liên quan.
- **Recall@k:** trong toàn bộ document liên quan đã biết, có bao nhiêu document xuất hiện trong k kết quả đầu tiên.

Ví dụ, query có 10 document liên quan đã được gán nhãn. Search trả 5 kết quả đầu, trong đó 4 kết quả liên quan:

```text
Precision@5 = 4 / 5 = 0.80
Recall@5    = 4 / 10 = 0.40
```

Precision cao nhưng recall thấp có thể nghĩa là kết quả đầu rất chính xác nhưng bỏ sót nhiều document cần tìm. Tùy sản phẩm, cần cân bằng hai chỉ số này.

### MRR và NDCG

- **MRR (Mean Reciprocal Rank):** đánh giá vị trí của kết quả liên quan đầu tiên. Nếu kết quả liên quan đầu tiên ở vị trí 1 thì reciprocal rank là 1; ở vị trí 4 thì là 1/4.
- **NDCG@k:** đánh giá thứ tự kết quả khi mỗi document có mức độ liên quan khác nhau. Kết quả rất liên quan nên xuất hiện trước kết quả ít liên quan.

MRR hữu ích với trải nghiệm mà người dùng thường chọn một kết quả đầu tiên. NDCG hữu ích khi có nhiều mức độ relevance và thứ tự trong top-k rất quan trọng.

### So sánh analyzer cũ và mới

Chạy cùng một tập query trên index cũ và index mới. Ghi lại:

- Số lượng query có kết quả.
- Precision@k, Recall@k, MRR hoặc NDCG@k.
- Những query có cải thiện rõ rệt.
- Những query bị giảm chất lượng hoặc xuất hiện false positive.
- Thời gian phản hồi và kích thước index.

Không chỉ nhìn điểm trung bình. Một thay đổi có thể cải thiện phần lớn query nhưng làm hỏng nhóm quan trọng như mã sản phẩm, tên riêng hoặc truy vấn tiếng Việt. Hãy phân nhóm theo intent/ngôn ngữ để phát hiện regression.

## 11. Công cụ kiểm tra relevance và truy vấn

### Explain API

`_explain` giúp hiểu vì sao một document khớp hoặc không khớp query và score được tính như thế nào:

```json
GET /articles-v2/_explain/article-100
{
  "query": {
    "match": {
      "body": "spring elasticsearch"
    }
  }
}
```

Kết quả giúp kiểm tra document có khớp query không và các thành phần score. Đây là công cụ chẩn đoán cho một document, không thay thế bộ đánh giá relevance trên nhiều query.

### Profile API

Profile giúp quan sát chi phí thực thi các phần của query trên shard:

```json
GET /articles-v2/_search
{
  "profile": true,
  "query": {
    "match": {
      "body": "spring data elasticsearch"
    }
  }
}
```

Profile có overhead và response khá lớn; chỉ nên bật khi chẩn đoán. Nó giúp phân tích hiệu năng truy vấn, không đo trực tiếp chất lượng relevance.

### Search Analyzer trong truy vấn

Có thể chỉ định analyzer cho `match` query để kiểm tra cách query được phân tích:

```json
GET /articles-v2/_search
{
  "query": {
    "match": {
      "body": {
        "query": "TV and automobiles",
        "analyzer": "article_search"
      }
    }
  }
}
```

Điều này hữu ích khi so sánh analyzer hoặc kiểm tra synonym ở search time. Khi kiểm thử chính thức, hãy dùng cùng cấu hình query mà ứng dụng production sẽ gửi.

## 12. Tự động hóa kiểm thử trong dự án Spring

Có thể tổ chức kiểm thử tìm kiếm thành nhiều lớp:

1. **Analyzer unit-like tests:** gọi `_analyze` trên index thử nghiệm và so sánh token đầu ra với expected tokens.
2. **Mapping tests:** xác nhận field có đúng type, analyzer, search analyzer và settings.
3. **Integration tests:** index bộ document mẫu, chạy query và kiểm tra tập kết quả.
4. **Relevance regression tests:** chạy tập query có relevance labels trên cả index cũ và mới, tính các metric.
5. **Performance tests:** đo latency, throughput và kích thước index với dữ liệu gần production.

Một test tích hợp đơn giản có thể dùng `ElasticsearchOperations` hoặc repository để ghi document, sau đó query và kiểm tra kết quả. Cần refresh index trong test nếu test tìm kiếm ngay sau khi ghi; không nên dựa vào thời gian chờ ngẫu nhiên.

Ví dụ dạng kiểm thử logic:

```java
@Test
void searchShouldFindStemmedTerm() {
    // Arrange: index document chứa "running".
    // Act: tìm kiếm bằng từ "run" qua analyzer đã cấu hình.
    // Assert: document mong đợi xuất hiện trong kết quả.
}
```

Đoạn trên là khung minh họa; cách tạo index, refresh và thực thi query cụ thể phụ thuộc test infrastructure và phiên bản Spring Data. Với relevance test, nên tách expected query/document judgments thành fixture dữ liệu để dễ mở rộng và so sánh qua nhiều phiên bản analyzer.

## 13. Quy trình triển khai thay đổi analyzer an toàn

Một lần thay đổi analyzer nên đi qua các bước có thể kiểm tra và lặp lại:

1. **Ghi nhận baseline:** lưu settings, mapping, query mẫu, relevance labels và metric hiện tại.
2. **Xác định vấn đề:** phân loại query thất bại, ví dụ stemming, synonym, dấu, mã định danh hoặc autocomplete.
3. **Thiết kế analyzer:** thay đổi tối thiểu các char filter, tokenizer, token filter cần thiết.
4. **Kiểm tra `_analyze`:** dùng tập câu đại diện và xác nhận token đầu ra.
5. **Tạo index mới:** áp dụng settings/mapping mới và kiểm tra mapping thực tế.
6. **Reindex:** sao chép document, theo dõi task, lỗi và version conflict.
7. **Kiểm thử:** chạy functional tests, relevance regression tests và performance tests.
8. **Đồng bộ dữ liệu mới:** bảo đảm các thay đổi phát sinh trong lúc reindex đã được áp dụng ở destination.
9. **Chuyển alias:** chuyển đọc/ghi theo một thao tác có kiểm soát.
10. **Theo dõi và rollback khi cần:** giữ index cũ cho đến khi xác nhận index mới ổn định.

Nên lưu settings, mapping và test fixtures trong source control để mỗi lần tạo index có thể tái lập. Không chỉnh analyzer thủ công trực tiếp trên production mà không có migration được review và kiểm thử.

## 14. Những điểm cần nhớ

- Analyzer gồm character filters, tokenizer và token filters; thứ tự xử lý ảnh hưởng token cuối cùng.
- `analyzer` áp dụng khi index; `search_analyzer` áp dụng khi phân tích query.
- `_analyze` là công cụ quan trọng để kiểm tra token trước khi tạo index hoặc reindex.
- Thay đổi index analyzer không tự xây dựng lại inverted index của document cũ; cần reindex để áp dụng cho dữ liệu hiện có.
- Reindex chỉ chuyển document `_source`; destination phải được tạo trước với settings và mapping mong muốn.
- Dùng versioned index và alias ổn định để chuyển đổi, kiểm thử và rollback có kiểm soát.
- Trong lúc reindex cần xử lý dữ liệu mới phát sinh bằng maintenance window, dual-write hoặc outbox/CDC đã thiết kế rõ.
- Kiểm thử token chưa đủ; cần relevance dataset và các metric như Precision@k, Recall@k, MRR hoặc NDCG.
- Explain API giúp hiểu score của document; Profile API giúp chẩn đoán hiệu năng và có overhead.
- Với Spring Data Elasticsearch, annotation và settings resource phải khớp mapping thực tế; thay đổi entity không tự migration index cũ.

Thay đổi analyzer là một thay đổi có ảnh hưởng trực tiếp đến hành vi tìm kiếm. Kết hợp kiểm tra token, reindex có kiểm soát và bộ kiểm thử relevance giúp ứng dụng Spring Data Elasticsearch cải thiện chất lượng tìm kiếm mà vẫn giữ được khả năng xác minh và quay lại cấu hình cũ khi cần.
