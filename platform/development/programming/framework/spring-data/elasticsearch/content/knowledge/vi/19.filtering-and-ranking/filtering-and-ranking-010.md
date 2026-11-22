# Explain API, Profile API và phân tích kết quả không như mong muốn

Khi một truy vấn Elasticsearch trả về document không như mong đợi, cần phân biệt hai câu hỏi: **vì sao document này được hoặc không được chọn**, và **thành phần nào làm truy vấn chạy chậm**. Elasticsearch có các công cụ riêng cho từng câu hỏi. Explain API phân tích việc một document có khớp query hay không và cách điểm relevance được tính. Profile API đo thời gian thực thi các phần của query trên từng shard. Ngoài ra, Validate Query API giúp kiểm tra query có hợp lệ và được rewrite thành cấu trúc nào trước khi chạy.

Trong Spring Data Elasticsearch, repository, `ElasticsearchOperations`, `SearchHits` và `NativeQuery` giúp xây dựng và đọc kết quả tìm kiếm. Khi cần thông tin chẩn đoán chuyên sâu mà abstraction không cung cấp trực tiếp, có thể gọi Elasticsearch Java API Client hoặc REST API. Bài này trình bày cách chọn đúng công cụ, cách đọc response và một quy trình tìm nguyên nhân khi kết quả hoặc hiệu năng không như dự kiến.

## 1. Phân biệt Explain API, Profile API và Validate Query API

Ba API thường được dùng cùng nhau nhưng trả lời những câu hỏi khác nhau:

| Công cụ | Câu hỏi chính | Phạm vi |
|---|---|---|
| Explain API (`_explain`) | Một document cụ thể có khớp query không? Vì sao điểm relevance của nó có giá trị đó? | Một document theo ID |
| Search API với `explain: true` | Vì sao từng hit trong kết quả có điểm relevance đó? | Các hit của một search request |
| Profile API (`profile: true`) | Query được thực thi qua các bước nào và thời gian tương đối ở từng phần ra sao? | Các shard và thành phần thực thi của search request |
| Validate Query API (`_validate/query`) | Query có hợp lệ không và Elasticsearch rewrite nó thành dạng nào? | Cấu trúc query, không tìm document |

Có thể dùng theo thứ tự:

```text
Kết quả không như mong muốn
          |
          v
Kiểm tra index, mapping, dữ liệu và query
          |
          v
Validate Query: query có hợp lệ/rewrite đúng?
          |
          v
Explain: document cụ thể khớp hoặc được tính điểm thế nào?
          |
          v
Profile: phần thực thi nào đang tốn thời gian?
```

Explain tập trung vào logic khớp và scoring. Profile tập trung vào thời gian thực thi. Một query có thể đúng về logic nhưng chậm; ngược lại, query chạy nhanh vẫn có thể trả về document sai với yêu cầu nghiệp vụ.

## 2. Chuẩn bị một query ví dụ

Giả sử index `products` có các field:

```json
PUT products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "description": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
      },
      "priceInCents": {
        "type": "long"
      },
      "featured": {
        "type": "boolean"
      }
    }
  }
}
```

Query tìm sản phẩm có nội dung liên quan đến `wireless keyboard`, phải active và thuộc category `keyboards`; tên khớp sẽ ảnh hưởng điểm relevance:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ],
      "should": [
        { "match": { "description": "wireless" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Trong ví dụ, `must` yêu cầu tên phải khớp cả hai term sau khi phân tích. Hai filter là điều kiện bắt buộc nhưng không đóng góp điểm. Hai `should` chỉ có tác dụng boost vì bool có `must`/`filter` và `minimum_should_match` bằng 0.

Đây là query dùng xuyên suốt các ví dụ. Khi phân tích một hệ thống thực tế, thay index, field, analyzer và query bằng cấu hình thật của ứng dụng.

## 3. Explain API cho một document

Explain API kiểm tra một document theo ID trong một index có khớp query được gửi hay không. Endpoint:

```http
GET products/_explain/p-100
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ],
      "should": [
        { "match": { "description": "wireless" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Response có các trường quan trọng:

- `matched`: `true` nếu document khớp query, `false` nếu không khớp.
- `explanation.value`: giá trị score được tính cho document nếu khớp.
- `explanation.description`: diễn giải phép tính hoặc điều kiện đang được xem xét.
- `explanation.details`: các thành phần con giải thích score/logic ở những cấp thấp hơn.

Response minh họa rút gọn:

```json
{
  "_index": "products",
  "_id": "p-100",
  "matched": true,
  "explanation": {
    "value": 2.41,
    "description": "sum of:",
    "details": [
      {
        "value": 1.72,
        "description": "weight(name:wireless in 0) ..."
      },
      {
        "value": 0.69,
        "description": "weight(name:keyboard in 0) ..."
      }
    ]
  }
}
```

Các con số và mô tả trên chỉ minh họa cấu trúc; score thực tế phụ thuộc dữ liệu, thống kê index, analyzer, query và phiên bản Elasticsearch.

### 3.1. Explain khi document không khớp

Nếu `matched` là `false`, response vẫn có phần explanation giúp xác định điều kiện nào làm document bị loại. Ví dụ:

- Document không chứa term `wireless` hoặc `keyboard` trong field `name` sau khi analyzer xử lý.
- Một trong các filter không khớp, ví dụ `active` là `false`.
- Query có `minimum_should_match` yêu cầu nhiều clause hơn số clause document thỏa.
- Document không nằm trong index/routing scope được kiểm tra.

Explain API hữu ích vì có thể kiểm tra một document dù nó không xuất hiện trong kết quả search thông thường. Cần biết ID của document và index chứa nó.

### 3.2. Explain chỉ giải thích query được gửi

Explain không tự tìm ra query đúng cho nghiệp vụ. Nếu request gửi sai field, sai analyzer, sai filter hoặc sai index, API vẫn giải thích cách Elasticsearch xử lý query đó. Hãy đối chiếu query trong Explain request với query thực tế mà ứng dụng gửi.

Explain cũng không thay thế việc kiểm tra `_source` và mapping. Một document có thể có giá trị trong `_source` nhưng field không được lập chỉ mục như kỳ vọng, hoặc field bị đổi tên/kiểu trong mapping.

## 4. Search API với `explain: true`

Nếu cần explanation cho từng hit trong kết quả search, bật `explain` trong Search API:

```http
GET products/_search
{
  "explain": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ]
    }
  }
}
```

Mỗi hit có thể chứa trường `_explanation` với cây diễn giải score. Điều này thuận tiện khi cần so sánh vì sao sản phẩm A được xếp trên sản phẩm B.

Khác với endpoint `_explain/{id}`, Search API chỉ trả explanation cho các hit mà truy vấn search trả về. Nếu một document không khớp và vì vậy không xuất hiện trong `hits`, dùng Explain API riêng cho ID đó.

### 4.1. Khi nào bật `explain`?

Chỉ bật khi điều tra một số kết quả cụ thể hoặc trong môi trường phát triển/kiểm thử. Explanation có thể rất dài, làm tăng kích thước response và chi phí xử lý. Không nên bật cho mọi request tìm kiếm của người dùng nếu ứng dụng không cần dữ liệu chẩn đoán này.

### 4.2. Score không phải xác suất

`_score` là điểm relevance do query và similarity tính ra. Nó không phải phần trăm xác suất document đúng, cũng không nhất thiết nằm trong khoảng 0 đến 1. Không nên hiển thị score như “độ chính xác 92%” nếu không có mô hình hiệu chuẩn riêng.

Score chủ yếu có ý nghĩa tương đối giữa các kết quả của cùng một truy vấn và cùng ngữ cảnh tìm kiếm. Không nên so sánh trực tiếp score của hai query khác nhau để kết luận query nào tốt hơn.

## 5. Profile API để phân tích thời gian thực thi

Profile API được bật bằng `profile: true` trong Search API:

```http
GET products/_search
{
  "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ]
    }
  }
}
```

Response có phần `profile` chứa dữ liệu theo shard. Bên trong mỗi shard, Elasticsearch có thể trả các search context, query tree, breakdown thời gian và thông tin collector. Nếu request có aggregation hoặc thành phần khác được hỗ trợ profiling, response có phần tương ứng.

Profile hữu ích để tìm:

- Query clause nào tốn nhiều thời gian.
- Query bị rewrite thành cấu trúc Lucene nào.
- Một bool query có nhiều nhánh hoặc nested query tạo ra cây thực thi ra sao.
- Thời gian trong các giai đoạn như tạo scorer, tìm document tiếp theo, advance và score.
- Collector hoặc aggregation nào chiếm nhiều công sức xử lý.

## 6. Đọc cấu trúc Profile response

Một profile response thường có cấu trúc khái quát:

```json
{
  "profile": {
    "shards": [
      {
        "id": "...",
        "searches": [
          {
            "query": [
              {
                "type": "BooleanQuery",
                "description": "...",
                "time_in_nanos": 123456,
                "breakdown": {
                  "create_weight": 1000,
                  "build_scorer": 2000,
                  "next_doc": 3000,
                  "score": 4000
                },
                "children": []
              }
            ],
            "collector": []
          }
        ]
      }
    ]
  }
}
```

Đây là cấu trúc minh họa rút gọn; response thật có nhiều trường và tên query phụ thuộc Lucene/Elasticsearch version.

Các thành phần cần chú ý:

| Trường | Ý nghĩa |
|---|---|
| `shards` | Kết quả profile theo từng shard tham gia search |
| `searches` | Các search context/phase được profile trên shard |
| `query` | Cây query thực thi và các query con |
| `type` | Loại query Lucene thực tế |
| `description` | Biểu diễn query đã rewrite hoặc query Lucene |
| `time_in_nanos` | Thời gian tổng của node trong cây profile |
| `breakdown` | Thời gian chi tiết theo các thao tác thực thi |
| `children` | Các query con trong cây thực thi |
| `collector` | Thông tin collector dùng để thu thập kết quả |
| `aggregations` | Thông tin profile aggregation nếu request có aggregation |

`time_in_nanos` được tính theo nanosecond. Có thể đổi sang millisecond để dễ đọc bằng cách chia cho 1.000.000.

### 6.1. Các chỉ số trong `breakdown`

Một số key thường thấy:

- `create_weight`: thời gian tạo Weight cho query.
- `build_scorer`: thời gian tạo scorer để đánh giá document.
- `next_doc`: thời gian tìm document tiếp theo khớp query.
- `advance`: thời gian chuyển tới một document ID cụ thể hoặc xa hơn.
- `score`: thời gian tính điểm cho document.
- `match`: thời gian kiểm tra điều kiện match ở một số query.
- `shallow_advance`: một thao tác advance tối ưu ở mức scorer.
- `compute_max_score`: thời gian tính điểm tối đa trong một số query tối ưu.

Không phải query nào cũng có mọi key. Một số thao tác không áp dụng hoặc có giá trị bằng 0 tùy implementation.

### 6.2. Đọc query tree

Profile biểu diễn query sau khi Elasticsearch/Lucene rewrite. Một query DSL `bool` có thể được chuyển thành `BooleanQuery` cùng các node con như term, phrase, range hoặc point query. Vì vậy, tên node trong profile không nhất thiết trùng với tên JSON DSL ban đầu.

Khi một query node có `children`, hãy xem thời gian và breakdown của node cha cùng các node con. Không cộng tất cả `time_in_nanos` của cha và con như các khoản độc lập; thời gian của node cha có thể bao gồm thời gian của node con.

### 6.3. So sánh thời gian giữa shard

Mỗi shard có thể có số document, segment, cache state và tải khác nhau. Một shard chậm hơn có thể làm tăng latency tổng thể, dù các shard khác xử lý nhanh.

Profile giúp phát hiện chênh lệch giữa shard, nhưng cần đối chiếu thêm:

- Số document và kích thước segment mỗi shard.
- Phân bố dữ liệu và routing.
- Tải CPU, disk I/O và heap trên node.
- Cache warm/cold và hoạt động merge.
- Search thread pool và queue.

Không kết luận chỉ từ một lần profile vì cache state và tải cluster có thể thay đổi giữa các lần chạy.

## 7. Giới hạn và chi phí của Profile API

Profile API tạo thêm overhead đáng kể. Nó đo chi tiết các thao tác query ở tầng thấp, nên query được profile có thể chạy chậm hơn query bình thường. Không dùng profile để benchmark throughput hoặc so sánh hiệu năng production một cách trực tiếp.

Profile cũng không phải đồng hồ đo end-to-end cho toàn bộ request. Nó không bao gồm đầy đủ thời gian client gửi request, mạng, hàng đợi trước khi query bắt đầu, phối hợp trên coordinating node hoặc mọi chi phí ngoài phần thực thi được profile. Không nên cộng các số trong profile để kỳ vọng bằng `took`.

Một số điểm cần nhớ:

- `took` là thời gian search request được Elasticsearch báo cáo ở mức request; profile là breakdown chi tiết theo shard/query.
- Shard xử lý song song, vì vậy tổng thời gian của các shard không phải latency end-to-end.
- Thời gian của node cha và node con trong query tree có thể bao gồm lẫn nhau.
- Profile có thể làm response rất lớn, đặc biệt với query tree hoặc aggregation phức tạp.
- Chỉ bật cho query cụ thể, dữ liệu mẫu và thời gian điều tra ngắn.

Nếu cần đo latency người dùng thực sự, hãy kết hợp APM/metrics ở client và server, log slow search, cluster monitoring và benchmark có kiểm soát. Profile dùng để tìm chi tiết bên trong query sau khi đã xác định request đáng chú ý.

## 8. Validate Query API

Trước khi phân tích document hoặc profile, có thể xác nhận query hợp lệ bằng Validate Query API:

```http
GET products/_validate/query?explain=true
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless keyboard" } }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ]
    }
  }
}
```

Response có `valid` cho biết query có hợp lệ không. Với `explain=true`, Elasticsearch trả thêm biểu diễn query sau khi được rewrite theo cách mà engine hiểu.

Validate Query API không thực hiện một search thông thường và không trả danh sách document. Nó giúp phát hiện lỗi cấu trúc query, field/query không hợp lệ và xem cách rewrite; nó không chứng minh query trả đúng dữ liệu nghiệp vụ.

Có thể dùng `all_shards=true` nếu cần xác thực trên tất cả shard thay vì chỉ một shard được chọn theo mặc định. Điều này hữu ích khi mapping hoặc dữ liệu shard có khác biệt bất thường, nhưng hãy cân nhắc chi phí trên index lớn.

## 9. Phân tích query không trả kết quả

Khi search trả về 0 hit, hãy điều tra từ những yếu tố cơ bản trước khi tối ưu query.

### 9.1. Xác nhận đúng index, alias hoặc data stream

Kiểm tra request đang nhắm đúng index:

```http
GET _resolve/index/products
```

Kiểm tra alias:

```http
GET _alias/products
```

Một alias có thể trỏ tới nhiều index hoặc có filter riêng. Query chạy trên alias có thể trả kết quả khác query chạy trực tiếp trên một index.

### 9.2. Kiểm tra document có tồn tại không

Lấy document theo ID:

```http
GET products/_doc/p-100
```

Nếu document không tồn tại trong index đang truy vấn, Explain API cũng không thể giải thích document đó ở index này. Hãy kiểm tra ID, index, routing và quá trình ingest.

### 9.3. Kiểm tra mapping

```http
GET products/_mapping
```

Xác nhận:

- Field query có tồn tại trong mapping không.
- Field là `text`, `keyword`, numeric, date hay kiểu khác.
- Có multi-field như `name.keyword` không.
- Analyzer và search analyzer có đúng không.
- Field có nằm trong nested object cần dùng `nested` query không.
- Field có bị cấu hình `index: false` hoặc `enabled: false` không.

`term` trên field `text` thường không có semantics mong muốn; `match` trên field `keyword` cũng có hành vi khác full-text analyzer. Query hợp lệ vẫn có thể không khớp nếu chọn sai kiểu query cho mapping.

### 9.4. Kiểm tra analyzer bằng Analyze API

Dùng `_analyze` để xem query text tạo ra token nào:

```http
POST products/_analyze
{
  "field": "name",
  "text": "Wireless Keyboard"
}
```

So sánh token từ chuỗi tìm kiếm với token được tạo khi lập chỉ mục. Kiểm tra lowercase, stemming, stop words, synonym, asciifolding và tokenizer. Nếu analyzer lập chỉ mục và search analyzer khác nhau, cần hiểu sự khác biệt đó có chủ đích hay là lỗi cấu hình.

### 9.5. Kiểm tra Bool logic

Rà soát từng clause:

- Có `must` nào quá chặt khiến không document nào khớp không?
- Filter có dùng đúng giá trị và đúng field type không?
- `must_not` có vô tình loại hết kết quả không?
- `should` có bị xem là tùy chọn vì bool có `must`/`filter` không?
- `minimum_should_match` có lớn hơn số clause có thể khớp không?
- Bool lồng nhau có đặt ngưỡng ở đúng cấp không?

Để tách nguyên nhân, thử lần lượt thêm từng filter hoặc clause vào một query đơn giản. Không nên xóa tất cả điều kiện cùng lúc vì sẽ khó biết điều kiện nào gây ra kết quả rỗng.

### 9.6. Kiểm tra `post_filter`, `min_score` và giới hạn kết quả

Search request có thể chứa các phần khác ngoài `query`:

- `post_filter`: lọc hit sau khi aggregation được tính; có thể làm danh sách hit rỗng dù aggregation vẫn có bucket.
- `min_score`: loại hit có score thấp hơn ngưỡng.
- `terminate_after`: giới hạn số document được thu thập trên mỗi shard.
- `size`: chỉ giới hạn số hit trả về, không thay đổi điều kiện match.
- `from`: bỏ qua một số hit đầu tiên để phân trang; giá trị quá lớn có thể gặp giới hạn result window.
- `routing`: giới hạn shard được truy vấn; routing sai có thể khiến document không được xem xét.
- Alias filter hoặc security filter: có thể thêm điều kiện lọc ngoài query mà code nhìn thấy.

Nếu query cơ bản có kết quả nhưng request đầy đủ không có, hãy kiểm tra những thành phần này.

## 10. Phân tích kết quả có nhưng thứ hạng sai

Nếu document được trả về nhưng thứ tự không như mong đợi, hãy phân biệt điều kiện match với scoring và sorting.

### 10.1. Kiểm tra sort

Nếu search request có `sort` theo field, kết quả có thể được sắp xếp theo field đó thay vì `_score`. Ví dụ:

```json
{
  "sort": [
    { "priceInCents": { "order": "asc" } }
  ]
}
```

Khi đó sản phẩm rẻ hơn có thể đứng trước dù score thấp hơn. Nếu muốn sort theo relevance, bỏ sort theo field hoặc thêm `_score` theo thứ tự ưu tiên phù hợp.

Khi sort theo field mà vẫn cần score, có thể bật `track_scores` để Elasticsearch tính/trả score trong một số trường hợp field sort. Đừng giả định score được trả về luôn quyết định thứ tự hit.

### 10.2. Kiểm tra `must`, `filter` và `should`

Điều kiện trong `filter` không cộng điểm. Nếu tất cả nội dung tìm kiếm vô tình nằm trong filter, các document có thể có score bằng 0 hoặc không có thứ hạng relevance như mong muốn.

Các `should` có thể chỉ dùng để boost khi bool có `must`/`filter` và ngưỡng bằng 0. Nếu cần chúng là điều kiện match, đặt `minimum_should_match` phù hợp.

### 10.3. Kiểm tra boost và query structure

Điểm relevance có thể thay đổi bởi:

- `boost` trên query hoặc field.
- `function_score` hoặc `script_score`.
- `dis_max` và `tie_breaker`.
- `multi_match` và các field boost như `name^3`.
- `rescore` ở giai đoạn sau.
- Similarity được cấu hình trên index/field.

Dùng Explain API cho một số document đại diện để xem thành phần nào đóng góp hoặc làm giảm score. So sánh hai document có cùng query, cùng index và cùng ngữ cảnh thay vì so score giữa những query khác nhau.

### 10.4. BM25 và thống kê term

Elasticsearch thường dùng BM25 làm similarity mặc định cho text. Score chịu ảnh hưởng bởi tần suất term trong document, độ hiếm của term trong tập dữ liệu và độ dài field. Vì vậy, hai document có cùng từ khóa vẫn có thể có score khác nhau.

Nếu thứ hạng khác trực giác, Explain có thể cho thấy các yếu tố như term frequency, inverse document frequency và field length normalization. Không nên cố diễn giải score như số lần xuất hiện đơn thuần.

## 11. Phân tích query chạy chậm bằng Profile API

Khi query trả kết quả đúng nhưng chậm, bắt đầu bằng cách ghi nhận:

- `took` của search request.
- Số shard được truy vấn và số shard failed.
- Số hit và cách phân trang.
- Query DSL đầy đủ, sort, aggregation và filter.
- Thời điểm, tải cluster và node nhận request.

Sau đó bật `profile: true` cho cùng query với tập dữ liệu đại diện. Xem shard nào chậm và query node nào có breakdown lớn.

Một số nguyên nhân thường thấy:

- `wildcard`, `regexp` hoặc `prefix` trên field có cardinality lớn và pattern không chọn lọc.
- `script` query hoặc script scoring phải chạy trên nhiều document.
- `nested` query có nhiều document con.
- `terms` query với danh sách rất lớn.
- Query nhiều nhánh `should`/`must` phức tạp.
- Aggregation có nhiều bucket hoặc cardinality cao.
- Sort theo field chưa có doc values phù hợp hoặc yêu cầu xử lý nhiều candidate.
- Truy vấn quá nhiều shard nhỏ hoặc dữ liệu phân bố không đều.

Profile cho biết phần thực thi tốn thời gian nhưng không tự đề xuất một bản query tốt hơn. Cần kết hợp hiểu biết về mapping, dữ liệu và yêu cầu nghiệp vụ để chọn hướng tối ưu.

## 12. Kết hợp Explain và Profile

Hai API có thể được dùng trên cùng một query nhưng phục vụ mục tiêu khác nhau:

1. Chạy search bình thường để xác nhận kết quả và ghi nhận `took`.
2. Dùng Explain cho một document được xếp hạng cao và một document có thứ hạng thấp để hiểu scoring.
3. Bật Profile trên query đó để tìm query node hoặc shard tốn thời gian.
4. Thay đổi một yếu tố tại một thời điểm, ví dụ analyzer, filter, query structure hoặc sort.
5. Chạy lại test chức năng và đo hiệu năng trong điều kiện tương đương.

Không dùng profile score hoặc explain score để kết luận một query nhanh/chậm. Profile đo thời gian thực thi; Explain phân tích match và relevance.

## 13. Dùng Spring Data Elasticsearch để đọc kết quả search

Repository method có thể trả `SearchHits<T>` hoặc `SearchHit<T>` để giữ metadata của kết quả:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0"
            }
          }
        }
        """)
    SearchHits<Product> searchWithMetadata(String text);
}
```

`SearchHits<Product>` giữ thông tin tổng quát của search response; mỗi `SearchHit<Product>` có entity cùng metadata như ID, index, score, sort values và highlight fields khi được yêu cầu. Ví dụ đọc score:

```java
SearchHits<Product> hits = repository.searchWithMetadata("wireless keyboard");

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    float score = hit.getScore();

    System.out.println(product.getName() + " -> " + score);
}
```

`SearchHits` giúp xem score và metadata của hit. Nó không đồng nghĩa toàn bộ cây Explain hoặc Profile được ánh xạ vào entity. Khi cần chi tiết chẩn đoán, hãy bật explain/profile qua request API tương ứng và đọc response của Elasticsearch Java API Client hoặc REST API.

## 14. Gọi Explain và Profile bằng Elasticsearch Java API Client

Trong các release train hiện đại, Spring Data Elasticsearch tích hợp với Elasticsearch Java API Client. Nếu ứng dụng đã cấu hình bean `ElasticsearchClient`, có thể gửi Search API request với `explain` và `profile`:

```java
import java.io.IOException;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public class ProductDiagnostics {

    private final ElasticsearchClient client;

    public ProductDiagnostics(ElasticsearchClient client) {
        this.client = client;
    }

    public SearchResponse<Product> explainAndProfile() throws IOException {
        Query query = Query.of(q -> q
                .match(m -> m
                        .field("name")
                        .query("wireless keyboard")));

        SearchRequest request = SearchRequest.of(s -> s
                .index("products")
                .query(query)
                .size(20)
                .explain(true)
                .profile(true));

        return client.search(request, Product.class);
    }
}
```

Request này yêu cầu Search API trả explanation cho các hit và profile thông tin thực thi. Phần response tương ứng được truy cập từ các accessor do Elasticsearch Java API Client sinh ra, chẳng hạn hit metadata và profile section. Tên class/kiểu response chi tiết phụ thuộc phiên bản client.

Nếu chỉ cần Explain cho một document, gọi endpoint `_explain/{id}` bằng REST API hoặc API client tương ứng. Nếu cần Profile, Search API request phải có `profile(true)`.

### 14.1. Chú ý tương thích dependency

Spring Boot quản lý phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client tương thích. Không tự nâng riêng client lên một major version khác nếu chưa kiểm tra release train. Builder, response type và accessor có thể thay đổi giữa các phiên bản.

Nếu dự án không expose sẵn `ElasticsearchClient`, hãy dùng client bean đã được cấu hình theo tài liệu Spring Boot/Spring Data tương ứng hoặc gọi REST API qua công cụ quản trị. Không tạo thêm client với credential/connection riêng mà bỏ qua cấu hình TLS, authentication, timeout và lifecycle của ứng dụng.

## 15. Những nguyên nhân phổ biến khiến kết quả không như mong muốn

### Query sai field hoặc field type

Query dùng `term` trên `text`, dùng tên field Java thay vì tên field trong mapping, hoặc quên subfield `.keyword`. Kiểm tra `_mapping` và dùng query phù hợp với kiểu field.

### Analyzer không giống kỳ vọng

Từ khóa bị lowercase, stemming, stop word hoặc synonym làm biến đổi. Dùng `_analyze` theo field để xem token thực tế.

### `should` trở thành tùy chọn

Bool có `must` hoặc `filter` khiến `should` mặc định có ngưỡng 0. Đặt `minimum_should_match` nếu nhóm này phải khớp.

### Filter loại document

Một filter exact match hoặc range có thể quá chặt, sai kiểu hoặc dùng sai timezone. Thử từng filter độc lập và xác nhận giá trị trong `_source`.

### Query trên nested field thiếu `nested` query

Nếu mapping dùng `nested`, query trực tiếp như object thông thường có thể không trả kết quả đúng. Cần dùng `nested` query với path tương ứng.

### Sort làm thứ hạng khác score

Search có `sort` theo field sẽ sắp xếp theo field đó. Kiểm tra `sort`, `track_scores` và thứ tự `_score`.

### Alias hoặc routing làm thay đổi phạm vi

Alias có thể chứa filter; routing có thể giới hạn shard. Kiểm tra target index, alias và routing thực tế.

### Kết quả bị cắt hoặc tổng hit không chính xác tuyệt đối

`size`, `from`, `search_after`, `terminate_after` và `track_total_hits` ảnh hưởng số hit hoặc độ chính xác của tổng hit. Đọc `hits.total.relation` để biết tổng số là chính xác (`eq`) hay chỉ là cận dưới (`gte`).

### Refresh chưa hoàn tất

Elasticsearch near-real-time; document vừa index có thể chưa xuất hiện trong search cho tới refresh. Kiểm tra write response và refresh policy trước khi kết luận document bị mất.

## 16. Quy trình điều tra có hệ thống

Khi nhận báo cáo “tìm kiếm không đúng” hoặc “query quá chậm”, có thể làm theo quy trình:

1. Ghi lại request đầy đủ: index/alias, query, sort, filter, routing, pagination và các tùy chọn search.
2. Kiểm tra `_mapping`, `_settings`, alias và document `_source` để xác nhận dữ liệu nền.
3. Dùng `_analyze` nếu query có full-text field; xác nhận token và analyzer.
4. Dùng `_validate/query?explain=true` để kiểm tra cấu trúc và query rewrite.
5. Nếu thiếu hoặc thừa document, kiểm tra Bool logic, `minimum_should_match`, `post_filter`, `min_score`, routing và security/alias filters.
6. Dùng `_explain/{id}` cho một document cụ thể để xem nó có khớp và score được tính thế nào.
7. Nếu hit có nhưng thứ hạng sai, kiểm tra sort, boosts, similarity, `function_score`, `rescore` và các clause scoring.
8. Nếu query đúng nhưng chậm, bật `profile: true` trên một request đại diện để tìm query node/shard tốn thời gian.
9. Thay đổi một yếu tố mỗi lần, chạy lại kiểm thử chức năng và đo hiệu năng trong điều kiện tương đương.
10. Tắt explain/profile sau khi điều tra; chỉ giữ metrics và logging phù hợp cho vận hành.

## 17. Tổng kết

Explain API trả lời vì sao một document cụ thể khớp hoặc không khớp và cách điểm relevance được tính. Có thể gọi `_explain/{id}` cho một document hoặc bật `explain: true` trong Search API để nhận explanation cho từng hit. Profile API được bật bằng `profile: true` và cho biết query được thực thi ra sao trên các shard, gồm query tree và breakdown thời gian. Validate Query API kiểm tra cấu trúc query và biểu diễn query sau rewrite mà không thực hiện search.

Khi kết quả không như mong muốn, hãy kiểm tra index, mapping, dữ liệu, analyzer, Bool logic, filter, routing, alias, sort và các giới hạn search trước khi tối ưu. Dùng Explain để hiểu match/scoring, Profile để tìm bottleneck thực thi và Validate để kiểm tra query. Trong Spring Data Elasticsearch, `SearchHits` cung cấp score và metadata cho từng hit; với chẩn đoán chi tiết, có thể dùng Elasticsearch Java API Client hoặc REST API theo phiên bản tương thích. Các công cụ này bổ sung cho nhau và giúp phân biệt lỗi logic tìm kiếm với vấn đề hiệu năng.

## Tài liệu tham khảo

- [Elasticsearch – Explain API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-explain)
- [Elasticsearch – Profile search requests](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-profile)
- [Elasticsearch – Validate query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-validate-query)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Analyze API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-analyze)
- [Spring Data Elasticsearch – Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – SearchHit API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html)
