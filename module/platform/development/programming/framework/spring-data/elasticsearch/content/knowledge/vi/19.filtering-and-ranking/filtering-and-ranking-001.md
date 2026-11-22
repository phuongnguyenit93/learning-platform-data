# Điểm `_score` và các yếu tố của BM25

Khi Elasticsearch thực hiện truy vấn tìm kiếm toàn văn, nó không chỉ xác định document nào khớp mà còn tính điểm liên quan (`_score`) để xếp hạng kết quả. Document có điểm cao hơn thường được xem là phù hợp hơn với truy vấn. Thuật toán mặc định phổ biến của Elasticsearch cho việc xếp hạng văn bản là BM25.

BM25 đánh giá mức độ liên quan dựa trên tần suất thuật ngữ xuất hiện trong document, độ hiếm của thuật ngữ trong tập document và độ dài nội dung so với độ dài trung bình. Điểm số còn chịu ảnh hưởng bởi cấu trúc query, analyzer, boost của field và các điều kiện lọc. Hiểu các yếu tố này giúp giải thích vì sao một document đứng đầu, vì sao kết quả thay đổi khi thêm từ khóa hoặc vì sao truy vấn giống nhau có thể cho thứ tự khác khi cấu hình index thay đổi.

## 1. `_score` là gì?

`_score` là điểm số Elasticsearch tính cho một document đối với một truy vấn tìm kiếm cụ thể. Trong các truy vấn có scoring, kết quả thường được sắp xếp theo `_score` giảm dần nếu ứng dụng không chỉ định một thứ tự sort khác.

Ví dụ, người dùng tìm `máy pha cà phê`. Hai sản phẩm cùng chứa các từ này nhưng một sản phẩm có tên là `Máy pha cà phê tự động`, còn sản phẩm kia chỉ nhắc cụm từ trong mô tả dài. Document có nội dung tập trung hơn vào các thuật ngữ truy vấn có thể nhận điểm cao hơn, tùy vị trí field, tần suất và độ dài field.

Điểm cần nhớ:

- `_score` biểu thị mức độ phù hợp tương đối với query hiện tại.
- `_score` không phải xác suất document đúng hoặc phần trăm độ chính xác.
- Không nên so sánh trực tiếp score của hai truy vấn khác nhau như thể chúng nằm trên cùng một thang đo.
- Thay analyzer, mapping, dữ liệu index, boost hoặc cấu trúc query có thể làm thay đổi score.
- Một document có `_score` cao không nhất thiết là lựa chọn tốt nhất theo nghiệp vụ; có thể cần kết hợp độ mới, mức phổ biến, tồn kho hoặc các tín hiệu khác.

Ví dụ response tìm kiếm:

```json
{
  "hits": {
    "total": {
      "value": 2,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "p-1001",
        "_score": 4.82,
        "_source": {
          "name": "Máy pha cà phê tự động"
        }
      },
      {
        "_id": "p-1002",
        "_score": 1.37,
        "_source": {
          "name": "Máy xay đa năng",
          "description": "Có thể dùng cùng máy pha cà phê"
        }
      }
    ]
  }
}
```

Các giá trị score trên chỉ minh họa. Không có một ngưỡng cố định như 1, 5 hay 10 để kết luận document tốt hoặc xấu.

## 2. BM25 là gì?

BM25 (Best Matching 25) là một hàm xếp hạng thông tin dựa trên thống kê thuật ngữ. Elasticsearch sử dụng BM25 làm similarity mặc định cho các field `text` trong các phiên bản hiện đại.

BM25 cải tiến cách tính liên quan so với mô hình TF-IDF cổ điển ở hai điểm quan trọng:

1. Tần suất thuật ngữ có lợi ích tăng dần nhưng bão hòa, nên lặp một từ 100 lần không làm điểm tăng tuyến tính gấp 100 lần.
2. Độ dài document được chuẩn hóa so với độ dài trung bình, giúp tránh thiên vị quá mức cho văn bản dài chỉ vì nó chứa nhiều từ.

BM25 được tính từ các thành phần thống kê của index và query. Công thức phổ biến cho một thuật ngữ truy vấn là:

\[
\operatorname{score}(q_i,d)=\operatorname{IDF}(q_i)\cdot
\frac{f(q_i,d)(k_1+1)}
{f(q_i,d)+k_1\left(1-b+b\frac{|d|}{\operatorname{avgdl}}\right)}
\]

Trong đó:

- (q_i): một thuật ngữ trong truy vấn.
- (d): document đang được chấm điểm.
- (f(q_i,d)): số lần thuật ngữ xuất hiện trong field của document (term frequency).
- (|d|): độ dài field/document theo số token được lập chỉ mục.
- (operatorname{avgdl}): độ dài trung bình của field trong tập document.
- (operatorname{IDF}(q_i)): trọng số của thuật ngữ dựa trên độ hiếm trong tập document.
- (k_1) và (b): tham số điều chỉnh BM25.

Với query có nhiều thuật ngữ, điểm thường là tổng đóng góp của các thuật ngữ khớp, sau đó có thể chịu ảnh hưởng của boost hoặc các query kết hợp khác.

## 3. Term Frequency (TF): tần suất thuật ngữ

Term frequency cho biết một thuật ngữ xuất hiện bao nhiêu lần trong field của document. Nếu người dùng tìm `espresso`, document nhắc tới `espresso` nhiều lần có thể nhận đóng góp điểm lớn hơn document chỉ nhắc một lần.

Tuy nhiên, BM25 dùng cơ chế bão hòa tần suất. Khi số lần xuất hiện tăng, phần điểm tăng thêm nhỏ dần. Điều này tránh để một document nhồi lặp từ khóa quá nhiều lần luôn chiếm ưu thế.

Ví dụ trực quan:

| Số lần `espresso` xuất hiện | Xu hướng đóng góp TF |
|---:|---|
| 0 | Không có đóng góp từ thuật ngữ này |
| 1 | Có đóng góp rõ ràng |
| 2 | Đóng góp tăng |
| 5 | Vẫn tăng nhưng mức tăng đã nhỏ hơn |
| 20 | Tiếp tục tăng nhưng gần bão hòa hơn |

Đây là xu hướng định tính, không phải bảng điểm BM25 thực tế. Điểm còn phụ thuộc IDF, độ dài field, (k_1), (b) và các yếu tố khác.

### Khi nào TF hữu ích?

TF giúp phân biệt document có nội dung tập trung vào chủ đề truy vấn với document chỉ nhắc đến thuật ngữ một lần. Tuy nhiên, không nên cố tình lặp từ khóa trong nội dung để thao túng thứ hạng. BM25 có bão hòa, còn việc nhồi từ có thể làm trải nghiệm đọc kém và không bảo đảm tăng relevance.

## 4. Inverse Document Frequency (IDF): độ hiếm của thuật ngữ

IDF đánh giá một thuật ngữ phổ biến hay hiếm trong tập document. Một từ xuất hiện ở hầu hết document thường ít có khả năng phân biệt kết quả. Một từ hiếm hơn có thể cung cấp tín hiệu mạnh hơn về chủ đề.

Ví dụ trong một catalog:

- `sản phẩm` có thể xuất hiện ở rất nhiều document.
- `espresso` xuất hiện trong một phần nhỏ sản phẩm.
- `portafilter` có thể xuất hiện ở rất ít document.

Khi người dùng tìm `portafilter`, thuật ngữ này có thể có IDF cao hơn từ `sản phẩm`, vì nó hiếm hơn trong index.

Một dạng công thức IDF thường dùng trong BM25 là:

\[
\operatorname{IDF}(q_i)=
\ln\left(1+\frac{N-df(q_i)+0.5}{df(q_i)+0.5}\right)
\]

Trong đó:

- (N): số document trong tập thống kê.
- (df(q_i)): số document chứa thuật ngữ (q_i).

IDF được tính theo thống kê index và có thể chịu ảnh hưởng bởi shard-level statistics trong truy vấn phân tán. Vì vậy, một thuật ngữ hiếm trong shard này nhưng phổ biến trong shard khác có thể có đóng góp khác nhau tùy cơ chế thu thập thống kê.

### IDF không phải tần suất trong một document

TF trả lời “từ này xuất hiện bao nhiêu lần trong document đang xét?”. IDF trả lời “từ này phổ biến đến đâu trong toàn bộ tập document?”. Hai thành phần bổ sung cho nhau.

## 5. Chuẩn hóa độ dài field (Document Length Normalization)

Nếu một document dài gấp nhiều lần document khác, nó có nhiều cơ hội chứa từ khóa hơn. BM25 chuẩn hóa theo độ dài để giảm thiên vị cho văn bản dài.

Trong công thức, tỷ lệ:

\[
\frac{|d|}{\operatorname{avgdl}}
\]

so sánh độ dài field của document với độ dài trung bình. Nếu field dài hơn trung bình, mẫu số trong phần TF thường lớn hơn và đóng góp TF bị giảm tương đối. Nếu field ngắn hơn trung bình, document có thể được lợi hơn khi chứa cùng một số lần thuật ngữ.

Ví dụ:

- Document A có mô tả 40 token và chứa `espresso` 2 lần.
- Document B có mô tả 1.000 token và cũng chứa `espresso` 2 lần.
- Nếu các yếu tố khác tương tự, độ dài field có thể khiến document A nhận đóng góp TF cao hơn.

Độ dài được tính theo token sau analyzer, không đơn giản là số ký tự hoặc số từ nhìn thấy trong chuỗi gốc. Analyzer thay đổi có thể làm số token và độ dài thống kê thay đổi.

### Độ dài được tính theo từng field

Trong tìm kiếm nhiều field, mỗi field có thống kê và độ dài riêng. `name` thường ngắn hơn nhiều so với `description`; nếu gộp mọi field một cách thiếu chủ đích, score có thể phản ánh sai tầm quan trọng của nội dung. Dùng field boost hoặc query phù hợp để thể hiện field nào quan trọng hơn.

## 6. Tham số `k1` và `b`

BM25 có hai tham số quan trọng thường được cấu hình:

| Tham số | Giá trị mặc định phổ biến | Vai trò |
|---|---:|---|
| `k1` | `1.2` | Điều chỉnh mức bão hòa của term frequency |
| `b` | `0.75` | Điều chỉnh mức chuẩn hóa theo độ dài field |

### `k1`: mức bão hòa của TF

`k1` điều khiển tốc độ phần đóng góp TF tiến tới bão hòa.

- `k1` thấp hơn làm lợi ích từ việc tăng số lần xuất hiện bão hòa sớm hơn.
- `k1` cao hơn cho phép tần suất thuật ngữ tiếp tục ảnh hưởng lâu hơn trước khi bão hòa.

Không nên tăng `k1` chỉ vì muốn document có nhiều từ khóa được xếp cao hơn. Cần đánh giá bằng tập truy vấn và nhãn relevance thực tế.

### `b`: mức ảnh hưởng của độ dài

`b` điều chỉnh mức chuẩn hóa độ dài:

- `b = 0`: không chuẩn hóa theo độ dài field.
- `b = 1`: áp dụng chuẩn hóa độ dài đầy đủ theo công thức BM25.
- Giá trị giữa 0 và 1 tạo mức ảnh hưởng trung gian.

Giảm `b` có thể phù hợp khi độ dài văn bản không phản ánh mức độ liên quan hoặc các field có cấu trúc độ dài đặc biệt. Tăng `b` làm yếu tố độ dài ảnh hưởng mạnh hơn. Giá trị phù hợp phụ thuộc dữ liệu và mục tiêu xếp hạng.

### Không điều chỉnh tham số theo cảm tính

Giá trị mặc định là điểm khởi đầu tốt cho phần lớn trường hợp. Nếu cần thay đổi, hãy chuẩn bị tập query đại diện, đánh giá relevance của kết quả và so sánh các cấu hình trên cùng dữ liệu. Thay đổi `k1` hoặc `b` có thể làm thay đổi thứ hạng của nhiều query, không chỉ một ví dụ.

## 7. Analyzer ảnh hưởng tới BM25 như thế nào?

BM25 chấm điểm trên token đã được analyzer tạo ra, không trực tiếp trên chuỗi ký tự gốc. Analyzer thường gồm character filters, tokenizer và token filters.

Ví dụ analyzer có thể:

- Chuyển chữ hoa thành chữ thường.
- Tách câu thành token.
- Loại bỏ stop words.
- Chuẩn hóa dấu hoặc ký tự Unicode.
- Tách từ đồng nghĩa hoặc tạo token synonym.
- Stemming hoặc chuyển từ về dạng gốc trong ngôn ngữ có hỗ trợ.

Những thay đổi này ảnh hưởng trực tiếp tới TF, document frequency và độ dài field, do đó ảnh hưởng score.

### Ví dụ lowercase

Nếu analyzer chuyển `Coffee`, `COFFEE` và `coffee` thành cùng token `coffee`, các cách viết khác hoa thường có thể khớp cùng một thuật ngữ.

### Ví dụ stop words

Nếu analyzer loại bỏ `the`, từ này không còn tham gia tính điểm như token bình thường. Điều đó có thể giảm nhiễu, nhưng stop word list không phù hợp có thể làm mất những từ quan trọng trong domain.

### Ví dụ tiếng Việt

Với tiếng Việt, analyzer quyết định việc xử lý dấu, chữ `đ`, Unicode và phân đoạn từ. Nếu một nội dung được tokenize thành các âm tiết riêng, query và document sẽ được chấm điểm trên những token đó. Nếu dùng segmenter từ điển hoặc synonym, thống kê TF/DF và độ dài cũng thay đổi. Vì vậy, thay analyzer có thể làm thứ hạng thay đổi đáng kể và thường cần reindex dữ liệu.

Có thể kiểm tra token thực tế bằng `_analyze`:

```http
POST /products/_analyze
Content-Type: application/json

{
  "analyzer": "standard",
  "text": "Máy pha cà phê espresso"
}
```

Hãy dùng analyzer thực tế của field thay vì chỉ kiểm tra `standard` nếu mapping đang dùng analyzer tùy chỉnh.

## 8. Cấu trúc query ảnh hưởng tới `_score`

Không phải mọi điều kiện trong Elasticsearch đều đóng góp score. Trong bool query, vị trí đặt điều kiện quyết định nó được dùng để lọc hay tính relevance.

| Bool clause | Hành vi chính | Ảnh hưởng score |
|---|---|---|
| `must` | Document phải khớp | Query con đóng góp score |
| `should` | Điều kiện tùy chọn hoặc điều kiện khớp tối thiểu tùy ngữ cảnh | Query con có thể tăng score |
| `filter` | Document phải thỏa điều kiện | Không đóng góp score |
| `must_not` | Document không được khớp | Không đóng góp score |

Ví dụ:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "espresso machine"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  }
}
```

Ở đây, `match` trên `description` quyết định điểm liên quan. `status` và `available` chỉ giới hạn tập kết quả, không làm score tăng hoặc giảm.

### `should` và `minimum_should_match`

`should` thường dùng để tăng điểm cho các tín hiệu bổ sung. Ví dụ, document có tên khớp truy vấn được ưu tiên, nhưng document chỉ khớp mô tả vẫn có thể xuất hiện nếu query cho phép.

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "description": "espresso machine" } }
      ],
      "should": [
        { "match": { "name": "espresso machine" } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Trong ví dụ này, `description` là điều kiện bắt buộc; khớp thêm `name` có thể làm document được xếp cao hơn. Khi bool query đã có `must` hoặc `filter`, các clause `should` thường là tùy chọn theo mặc định. Nếu muốn ít nhất một `should` phải khớp, hãy đặt `minimum_should_match` phù hợp.

Nếu bool query chỉ có `should` mà không có `must`/`filter`, mặc định thường yêu cầu ít nhất một nhánh khớp. Hãy khai báo rõ `minimum_should_match` khi logic nghiệp vụ phụ thuộc vào nó.

## 9. Boost field và boost query

Boost cho phép tăng hoặc giảm ảnh hưởng của một query con đối với score. Ví dụ, khớp tên sản phẩm thường quan trọng hơn khớp phần mô tả dài.

```json
{
  "query": {
    "multi_match": {
      "query": "espresso machine",
      "fields": [
        "name^4",
        "brand^2",
        "description"
      ]
    }
  }
}
```

Trong ví dụ, `name` được boost 4 lần, `brand` 2 lần và `description` dùng mức mặc định. Đây là hệ số ảnh hưởng trong quá trình tính score, không phải cam kết điểm cuối cùng tăng đúng bốn lần sau mọi phép kết hợp.

Có thể dùng boost trên một query cụ thể:

```json
{
  "match": {
    "name": {
      "query": "espresso",
      "boost": 3
    }
  }
}
```

Boost là cách điều chỉnh relevance theo cấu trúc nội dung. Nên bắt đầu bằng một số field quan trọng, đánh giá kết quả và tinh chỉnh dựa trên dữ liệu thay vì gán boost lớn cho mọi field.

## 10. Kết hợp BM25 với tín hiệu nghiệp vụ

Trong tìm kiếm sản phẩm, relevance văn bản chưa chắc phản ánh toàn bộ mục tiêu. Người dùng có thể muốn sản phẩm khớp nội dung nhưng cũng ưu tiên hàng còn tồn kho, sản phẩm phổ biến hoặc mới cập nhật.

Có thể kết hợp BM25 với các tín hiệu khác:

- Độ phổ biến hoặc lượt bán.
- Độ mới của document.
- Giá trị rating hoặc chất lượng.
- Khoảng cách địa lý.
- Trạng thái tồn kho.
- Một điểm số nghiệp vụ đã được chuẩn hóa.

`function_score` cho phép điều chỉnh điểm của query gốc bằng function như field value factor, decay function hoặc script score. Ví dụ, query BM25 tìm nội dung, sau đó thêm tín hiệu popularity:

```json
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "name": "espresso machine"
        }
      },
      "field_value_factor": {
        "field": "popularity",
        "modifier": "log1p",
        "factor": 1.0,
        "missing": 0
      },
      "boost_mode": "sum",
      "score_mode": "sum"
    }
  }
}
```

Đây là ví dụ minh họa cách kết hợp. Cần chọn `boost_mode`, `score_mode`, modifier và hệ số theo phân bố dữ liệu thực tế. Nếu popularity có miền giá trị rất lớn so với BM25, nó có thể lấn át relevance văn bản. Nên chuẩn hóa hoặc giới hạn tín hiệu nghiệp vụ để tránh kết quả bị chi phối ngoài dự kiến.

### Lọc nghiệp vụ hay tính điểm nghiệp vụ?

Nếu sản phẩm hết hàng tuyệt đối không được hiển thị, dùng `filter` để loại khỏi kết quả. Nếu sản phẩm còn hàng chỉ nên được ưu tiên hơn sản phẩm hết hàng nhưng vẫn cho phép hiển thị, có thể dùng tín hiệu score hoặc function score. Phân biệt rõ điều kiện bắt buộc với yếu tố ưu tiên.

## 11. BM25 và sort theo field

Nếu query có scoring và không chỉ định sort, Elasticsearch thường sắp xếp theo `_score` giảm dần. Nhưng nếu ứng dụng chỉ định sort theo field, thứ tự kết quả sẽ dựa trên field đó.

Ví dụ:

```json
{
  "query": {
    "match": {
      "name": "espresso"
    }
  },
  "sort": [
    { "priceMinorUnits": "asc" }
  ]
}
```

Kết quả được sắp xếp theo giá tăng dần, không phải theo score. Nếu cần giữ score để hiển thị hoặc dùng ở nơi khác, có thể yêu cầu theo dõi score khi sort theo field bằng tùy chọn `track_scores` ở các API phù hợp.

Khi cần ưu tiên relevance rồi mới dùng field làm tiêu chí phụ, có thể sort theo `_score` trước và field sau:

```json
{
  "sort": [
    { "_score": "desc" },
    { "createdAt": "desc" }
  ]
}
```

Điều này giữ relevance là thứ tự chính và dùng `createdAt` để phá hòa hoặc sắp xếp thêm.

## 12. Đọc `_score` trong Spring Data Elasticsearch

Khi dùng `ElasticsearchOperations.search(...)`, kết quả trả về là `SearchHits<T>`. Mỗi `SearchHit<T>` chứa document content cùng metadata như ID, score và highlight.

Ví dụ:

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public List<ProductResult> searchProducts(
        ElasticsearchOperations operations,
        String text) {

    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(text)
        ))
        .build();

    SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

    return hits.getSearchHits().stream()
        .map(hit -> new ProductResult(
            hit.getId(),
            hit.getScore(),
            hit.getContent()
        ))
        .toList();
}
```

DTO có thể chứa score:

```java
public record ProductResult(
        String id,
        float score,
        ProductDocument product) {
}
```

Nếu dùng repository trả về `List<ProductDocument>`, ứng dụng thường chỉ nhận entity content và không có đầy đủ metadata của từng hit. Khi cần `_score`, highlight hoặc sort values, dùng `SearchHits`/`SearchHit` thông qua `ElasticsearchOperations` hoặc API kết quả phù hợp.

## 13. Giải thích vì sao document được điểm như vậy bằng `_explain`

Khi một document có score bất ngờ, Elasticsearch cung cấp Explain API để giải thích các thành phần đã đóng góp vào điểm số.

```http
GET /products/_explain/p-1001
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "espresso machine"
    }
  }
}
```

Response thường chứa:

- `matched`: document có khớp query hay không.
- `value`: điểm score được tính.
- `description`: diễn giải phép tính.
- `details`: các thành phần con như IDF, TF và normalization.

Explain hữu ích để tìm hiểu vì sao một document nhận điểm cao/thấp. Nó tốn tài nguyên hơn truy vấn bình thường, vì vậy nên dùng để chẩn đoán một số document trong môi trường phát triển hoặc điều tra có kiểm soát, không bật cho mọi request production.

### `explain` trong search request

Có thể yêu cầu Elasticsearch trả thông tin explain cho các hit của một search request bằng tùy chọn `explain`. Cách này hữu ích khi so sánh một nhóm kết quả, nhưng response lớn hơn và chi phí tính toán cao hơn.

## 14. Dùng Profile API để xem chi phí query

Explain trả lời “vì sao document có score này?”. Profile API trả lời “Elasticsearch thực thi các phần của query tốn bao nhiêu thời gian tương đối?”.

Ví dụ:

```http
GET /products/_search
Content-Type: application/json

{
  "profile": true,
  "query": {
    "match": {
      "name": "espresso machine"
    }
  }
}
```

Profile có thể cho biết thời gian ở query tree, collector và các shard. Đây là công cụ chẩn đoán, không nên bật thường xuyên trên mọi request vì profiling làm tăng overhead. Dùng Explain khi cần phân tích score của document; dùng Profile khi cần phân tích chi phí thực thi query.

## 15. BM25 trong index settings và mapping

Elasticsearch sử dụng BM25 mặc định cho các field text. Thông thường không cần khai báo lại similarity nếu không có yêu cầu đặc biệt.

Nếu cần cấu hình similarity riêng, có thể khai báo trong index settings và gắn vào field:

```json
PUT /products-v2
{
  "settings": {
    "similarity": {
      "custom_bm25": {
        "type": "BM25",
        "k1": 1.5,
        "b": 0.65
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "similarity": "custom_bm25"
      },
      "description": {
        "type": "text"
      }
    }
  }
}
```

Trong ví dụ, field `name` dùng BM25 tùy chỉnh, còn `description` dùng similarity mặc định. Các giá trị `k1` và `b` chỉ là ví dụ để minh họa cấu hình, không phải cấu hình tối ưu cho mọi dữ liệu.

Similarity được khai báo trong settings của index và gắn vào mapping field. Nếu muốn thay đổi similarity của field đã được lập chỉ mục, cần xem xét giới hạn mapping và tạo index mới/reindex để có kết quả nhất quán. Không thể giả định sửa annotation Java sẽ cập nhật similarity cho index hiện có.

### Khai báo qua Spring Data

Spring Data có thể nạp index settings từ file bằng `@Setting`:

```java
@Document(indexName = "products-v2")
@Setting(settingPath = "/elasticsearch/products-settings.json")
public class ProductDocument {
    // fields
}
```

File settings chứa phần `similarity` như ví dụ JSON trên. Field mapping phải tham chiếu đúng tên `custom_bm25`. Cần tạo index với settings trước khi index dữ liệu.

## 16. Thống kê theo shard và sự khác biệt điểm số

Trong cluster nhiều shard, mỗi shard có thể có phân bố document và term frequency khác nhau. Với kiểu search thông thường, thống kê liên quan có thể được thu thập cục bộ theo shard; cùng một thuật ngữ có thể được xem là phổ biến ở shard này nhưng hiếm ở shard khác.

Elasticsearch hỗ trợ search type `dfs_query_then_fetch` để thu thập thống kê phân tán trước khi tính điểm, giúp score nhất quán hơn giữa shard trong một số trường hợp. Đổi lại, request cần thêm một vòng trao đổi và tốn chi phí hơn.

Không nên mặc định mọi khác biệt score giữa shard đều là lỗi. Hãy xem dữ liệu phân bố, routing, số shard và mục tiêu xếp hạng. Nếu kết quả cần thống kê toàn cục chính xác hơn, thử `dfs_query_then_fetch` trên workload đại diện và đo hiệu năng trước khi áp dụng rộng.

## 17. Đánh giá chất lượng xếp hạng

Không nên tinh chỉnh BM25 chỉ dựa trên một truy vấn mẫu. Cần một tập truy vấn đại diện cho hành vi người dùng và đánh giá kết quả có liên quan hay không.

Quy trình có thể gồm:

1. Thu thập query thực tế đã được ẩn danh và loại bỏ dữ liệu nhạy cảm.
2. Chọn một tập query đại diện theo nhóm ý định.
3. Gán nhãn relevance cho các document ứng viên theo thang phù hợp.
4. Ghi lại baseline với analyzer, mapping và BM25 mặc định.
5. Thử thay đổi field boost, analyzer hoặc `k1`/`b` từng bước.
6. So sánh thứ hạng bằng chỉ số như Precision@K, Recall@K, MRR hoặc NDCG.
7. Kiểm tra cả độ trễ, tài nguyên và các nhóm query bị giảm chất lượng.
8. Triển khai có kiểm soát và theo dõi hành vi sau thay đổi.

Mỗi lần chỉ nên thay đổi một nhóm yếu tố để biết nguyên nhân cải thiện hoặc suy giảm. Nếu cùng lúc đổi analyzer, boost, similarity và dữ liệu, rất khó xác định yếu tố nào tạo ra khác biệt.

## 18. Các lỗi thường gặp khi phân tích `_score`

### Coi `_score` là phần trăm xác suất

Score không nằm trên thang 0–100 và không phải xác suất. Không nên hiển thị `4.8` như “độ chính xác 4,8%” hoặc so sánh score giữa hai truy vấn khác nhau.

### Nghĩ document nhắc từ nhiều lần luôn đứng đầu

BM25 có term-frequency saturation và length normalization. IDF, độ dài field, analyzer và boost cũng ảnh hưởng điểm.

### Đưa điều kiện bắt buộc vào `should` mà quên `minimum_should_match`

Khi bool query đã có `must` hoặc `filter`, `should` có thể chỉ là tùy chọn. Nếu điều kiện phải khớp, đặt `minimum_should_match` hoặc dùng `must`/`filter`.

### Đặt mọi điều kiện vào `must`

Điều kiện trạng thái, tồn kho hoặc danh mục thường chỉ cần lọc. Đặt chúng vào `filter` giúp không cộng score không cần thiết và có thể tận dụng filter cache khi phù hợp.

### Dùng field `text` cho exact filter

Field `text` được analyzer tách token. Dùng `keyword` hoặc subfield keyword cho điều kiện chính xác và aggregation.

### Thay analyzer nhưng không reindex

Analyzer mới không tự phân tích lại token đã lưu trong inverted index. Cần tạo index mới và reindex dữ liệu nếu thay đổi ảnh hưởng tới quá trình index.

### Tinh chỉnh `k1` và `b` không có tập đánh giá

Thay tham số có thể làm kết quả của nhiều query thay đổi. Dùng query set và nhãn relevance để đánh giá, không dựa vào cảm nhận từ một ví dụ.

### Sort theo field rồi thắc mắc vì sao score không quyết định thứ tự

Khi có sort theo field, thứ tự không còn dựa thuần túy vào `_score`. Kiểm tra cấu hình sort và `track_scores` nếu vẫn cần score.

## 19. Quy trình điều tra một kết quả xếp hạng bất thường

Khi một document đứng quá cao hoặc quá thấp, có thể kiểm tra theo trình tự:

1. Xác nhận query thực tế và các giá trị tham số đã bind.
2. Kiểm tra document có khớp nhánh `must`, `should`, `filter` nào.
3. Kiểm tra field mapping và analyzer của field được query.
4. Dùng `_analyze` để xem token của query và document.
5. Dùng `_explain` trên một document cụ thể để xem TF, IDF, length normalization và boost.
6. Kiểm tra field boost, query boost và `minimum_should_match`.
7. Xác nhận có `function_score`, rescore hoặc sort theo field làm thay đổi thứ tự hay không.
8. Nếu cluster nhiều shard, đánh giá thống kê theo shard và thử DFS query khi phù hợp.
9. Dùng Profile API nếu cần xác định chi phí thực thi.
10. Thử điều chỉnh trên tập query đánh giá trước khi đưa thay đổi vào production.

## 20. Kết luận

`_score` là điểm liên quan mà Elasticsearch dùng để xếp hạng document đối với một query. BM25 là similarity mặc định phổ biến cho tìm kiếm văn bản và tính điểm dựa trên tần suất thuật ngữ, độ hiếm của thuật ngữ, độ dài field cùng hai tham số `k1` và `b`. Analyzer quyết định token được lập chỉ mục, còn cấu trúc bool query và field boost quyết định điều kiện nào đóng góp score.

Trong Spring Data Elasticsearch, có thể lấy score qua `SearchHit.getScore()` khi dùng `ElasticsearchOperations.search(...)`. Dùng `filter` cho điều kiện nghiệp vụ không cần tính điểm, `must` cho nội dung bắt buộc có scoring và `should` để thêm tín hiệu ưu tiên với `minimum_should_match` rõ ràng. Khi cần giải thích một kết quả, dùng `_explain`; khi cần xem chi phí thực thi, dùng Profile API. Chỉ tinh chỉnh BM25 hoặc boost sau khi đánh giá bằng tập query đại diện, vì score là tín hiệu xếp hạng tương đối chứ không phải xác suất đúng.
