# Script score và giới hạn chi phí tính toán

Elasticsearch mặc định xếp hạng kết quả tìm kiếm bằng relevance score do query tạo ra. Khi nghiệp vụ cần đưa thêm tín hiệu riêng vào thứ tự kết quả, chẳng hạn độ phổ biến, chất lượng, mức ưu tiên hoặc độ gần đây, có thể dùng `script_score` để tính điểm cho từng document phù hợp.

Script score rất linh hoạt, nhưng có chi phí. Elasticsearch phải chạy script trên các document mà query bên trong tìm thấy để tính điểm mới. Nếu query bên trong quá rộng, script phức tạp hoặc phải đọc dữ liệu tốn kém, một truy vấn có thể tiêu thụ CPU đáng kể. Vì vậy, thiết kế script score luôn cần đi cùng chiến lược giới hạn tập document, giới hạn độ phức tạp và đo lường hiệu năng.

## 1. Score trong Elasticsearch và vai trò của script_score

### 1.1. Relevance score mặc định

Với full-text query như `match`, Elasticsearch tính điểm dựa trên mức độ phù hợp giữa query và nội dung document. Score phụ thuộc query type, analyzer, thống kê term và cấu hình tìm kiếm.

Ví dụ:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Kết quả thường được sắp xếp theo score giảm dần. Document khớp tốt hơn với các term truy vấn thường được xếp cao hơn, nhưng score không phải phần trăm hoặc xác suất tài liệu đúng.

### 1.2. Khi nào cần score tùy chỉnh?

Một số sản phẩm cần kết hợp độ phù hợp văn bản với tín hiệu nghiệp vụ:

- Sản phẩm có độ phổ biến cao được ưu tiên hơn khi độ phù hợp tương đương.
- Bài viết mới hơn được tăng điểm trong một khoảng thời gian nhất định.
- Tài liệu có chất lượng đã được đánh giá cao được xếp trên.
- Kết quả thuộc nhóm ưu tiên được tăng điểm.
- Khoảng cách địa lý hoặc thời gian ảnh hưởng đến thứ tự kết quả.

Có thể dùng các query/function dựng sẵn như `function_score`, `field_value_factor`, decay functions hoặc `rank_feature`. Khi công thức cần xử lý đặc thù mà các chức năng dựng sẵn không biểu diễn gọn, `script_score` là lựa chọn linh hoạt hơn.

### 1.3. Script score thay đổi thứ tự như thế nào?

`script_score` nhận một query bên trong để xác định candidate documents, sau đó chạy script trên từng document phù hợp để tính score mới.

~~~mermaid
flowchart TD
    A[Search request] --> B[Inner query selects candidates]
    B --> C[Documents matching inner query]
    C --> D[Painless script per candidate]
    D --> E[New score]
    E --> F[Sort by score and return top hits]
~~~

Query bên trong xác định document nào có thể xuất hiện. Script tính điểm cho các document đó. Kết quả sau cùng được xếp hạng theo score mới, trừ khi request chỉ định một sort khác.

Đây là điểm quan trọng để kiểm soát chi phí: cần giới hạn candidate trước khi script chạy.

## 2. Cấu trúc script_score query

### 2.1. Query DSL cơ bản

Một query `script_score` có hai thành phần chính:

- `query`: query bên trong để chọn document.
- `script`: công thức tính score cho từng document đã khớp.

Ví dụ:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "script": {
        "source": "_score * 1.5"
      }
    }
  }
}
~~~

Trong ví dụ, query bên trong tìm document theo tên. Script lấy score gốc `_score` và nhân với 1,5. Vì mọi candidate đều được nhân cùng một hệ số dương, thứ tự giữa chúng không đổi; ví dụ này chỉ minh họa cách truy cập score.

### 2.2. Truy cập score gốc

Trong Painless script score context, biến `_score` chứa score do query bên trong tạo ra. Có thể dùng nó để kết hợp độ phù hợp văn bản với các tín hiệu khác.

Ví dụ khái niệm:

~~~text
finalScore = textScore * businessMultiplier
~~~

Nếu muốn giữ relevance là yếu tố chính, multiplier nên thay đổi trong một khoảng có kiểm soát. Nếu tín hiệu nghiệp vụ quá lớn, document khớp kém có thể vượt document khớp tốt chỉ nhờ popularity hoặc priority.

### 2.3. Truy cập field qua doc values

Script thường đọc field bằng `doc['field_name']`. Cách này sử dụng doc values khi field hỗ trợ, phù hợp hơn việc đọc và phân tích toàn bộ `_source` trong mỗi lần tính điểm.

Ví dụ kiểm tra field có giá trị:

~~~painless
if (doc['popularity'].size() == 0) {
    return _score;
}
double popularity = doc['popularity'].value;
return _score + popularity;
~~~

Điều kiện `size() == 0` giúp xử lý document thiếu giá trị. Không truy cập `.value` trước khi kiểm tra field có tồn tại, nếu không script có thể lỗi khi gặp document thiếu field.

Doc values thường có sẵn cho các field numeric, keyword, date và một số kiểu khác. Field `text` thường không có doc values mặc định; bật fielddata cho text có thể tiêu thụ nhiều heap. Với tín hiệu dùng để tính điểm, hãy cân nhắc lưu thành numeric/keyword field riêng.

## 3. Ví dụ kết hợp text relevance và popularity

### 3.1. Công thức có giới hạn

Giả sử document có field numeric `popularity`, không âm. Ta muốn:

- Giữ score văn bản làm nền.
- Tăng điểm cho sản phẩm phổ biến.
- Giới hạn mức tăng để popularity không lấn át hoàn toàn độ phù hợp.

Có thể dùng hàm bão hòa:

\[
normalizedPopularity = \frac{popularity}{popularity + k}
\]

Khi popularity tăng, giá trị tiến gần 1 nhưng không vượt 1 với popularity không âm và \(k > 0\).

Score cuối:

\[
finalScore = textScore \times (1 + weight \times normalizedPopularity)
\]

Nếu `weight = 0.5`, multiplier nằm trong khoảng từ 1 đến dưới 1,5. Tín hiệu popularity chỉ tăng điểm trong một giới hạn rõ ràng.

### 3.2. Query DSL với Painless

~~~json
{
  "query": {
    "script_score": {
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
            {
              "term": {
                "available": true
              }
            }
          ]
        }
      },
      "script": {
        "source": "double p = doc['popularity'].size() == 0 ? 0.0 : Math.max(0.0, doc['popularity'].value); double k = params.k; double normalized = p / (p + k); return _score * (1.0 + params.weight * normalized);",
        "params": {
          "k": 10.0,
          "weight": 0.5
        }
      }
    }
  }
}
~~~

Query bên trong dùng `match` để chọn candidate theo tên và `filter` để bỏ sản phẩm không có sẵn. Script chỉ chạy trên document thỏa điều kiện đó.

`Math.max` bảo vệ công thức nếu dữ liệu popularity có giá trị âm ngoài dự kiến. Tốt hơn nữa, hãy xác thực dữ liệu ngay khi ingest và quy định rõ miền giá trị hợp lệ.

### 3.3. Vì sao cần chuẩn hóa tín hiệu?

Các field nghiệp vụ có thể có thang đo rất khác nhau:

- Popularity có thể từ 0 đến hàng triệu.
- Rating có thể từ 0 đến 5.
- Priority có thể từ 1 đến 10.
- Timestamp có thể là số rất lớn.

Cộng trực tiếp các giá trị này vào `_score` có thể khiến một tín hiệu chi phối toàn bộ ranking. Hãy chuyển tín hiệu về thang đo có ý nghĩa, chẳng hạn 0–1, rồi đặt trọng số có giới hạn.

Không chọn `weight` theo cảm tính. Hãy đánh giá kết quả trên tập query có nhãn relevance và so sánh thứ tự trước/sau.

### 3.4. Xử lý giá trị thiếu và dữ liệu bất thường

Một script score nên xác định rõ cách xử lý:

- Field không tồn tại.
- Field có giá trị null hoặc không được index.
- Giá trị âm ngoài miền hợp lệ.
- Giá trị quá lớn.
- Field có nhiều giá trị.
- Score đầu vào bằng 0.

Ví dụ xử lý giá trị popularity thiếu bằng 0 giúp document vẫn có thể xếp hạng theo text score. Nếu nghiệp vụ muốn loại document thiếu field, nên thực hiện bằng filter ở query bên trong thay vì để script ném lỗi.

Với field multi-valued, không nên mặc định `.value` biểu diễn giá trị nghiệp vụ mong muốn. Hãy xác định cần min, max, trung bình hay một phần tử cụ thể, rồi triển khai rõ ràng. Nếu chỉ cần một tín hiệu duy nhất, lưu field single-valued sẽ dễ kiểm soát hơn.

## 4. Tham số hóa script

### 4.1. Dùng params thay cho tạo source động

Không nên tạo một chuỗi script mới cho mỗi request bằng cách ghép giá trị người dùng vào source. Hãy giữ source ổn định và truyền giá trị thay đổi qua `params`:

~~~json
{
  "script": {
    "source": "return _score * params.boost;",
    "params": {
      "boost": 1.2
    }
  }
}
~~~

Lợi ích:

- Source ổn định có thể được tái sử dụng trong script compilation cache.
- Giá trị runtime không làm phát sinh một source khác cho mỗi request.
- Giảm rủi ro lỗi escaping.
- Phân biệt rõ logic tính điểm và tham số nghiệp vụ.
- Dễ kiểm thử nhiều bộ tham số trên cùng một script.

Không nhận nguyên Painless source từ client công khai. Client chỉ nên truyền giá trị nghiệp vụ đã được validate.

### 4.2. Ví dụ với tham số ngưỡng

Giả sử muốn chỉ tăng điểm khi popularity vượt ngưỡng:

~~~json
{
  "script": {
    "source": "double p = doc['popularity'].size() == 0 ? 0.0 : doc['popularity'].value; return p >= params.threshold ? _score * params.boost : _score;",
    "params": {
      "threshold": 100.0,
      "boost": 1.25
    }
  }
}
~~~

Cùng source có thể dùng với threshold và boost khác nhau mà không cần biên dịch script mới chỉ vì giá trị params thay đổi.

### 4.3. Stored scripts

Nếu script được dùng ở nhiều truy vấn hoặc cần quản lý độc lập, có thể lưu thành stored script trong Elasticsearch và tham chiếu theo ID.

Ví dụ lưu script:

~~~http
PUT _scripts/product-popularity-score
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "double p = doc['popularity'].size() == 0 ? 0.0 : Math.max(0.0, doc['popularity'].value); double k = params.k; return _score * (1.0 + params.weight * p / (p + k));"
  }
}
~~~

Sau đó tham chiếu:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "script": {
        "id": "product-popularity-score",
        "params": {
          "k": 10.0,
          "weight": 0.5
        }
      }
    }
  }
}
~~~

Stored script giúp tập trung quản lý source và có thể triển khai qua pipeline. Cần version hóa hoặc rollout có kiểm soát vì thay đổi stored script có thể ảnh hưởng nhiều truy vấn đang dùng cùng ID.

### 4.4. Script compilation cache

Elasticsearch biên dịch Painless script trước khi thực thi. Script source ổn định có thể được cache để giảm chi phí biên dịch. Nếu mỗi request tạo source khác nhau, cache hit giảm và có thể vượt giới hạn tốc độ biên dịch.

Hãy:

- Dùng source ổn định.
- Đưa giá trị thay đổi vào `params`.
- Tránh sinh tên biến, biểu thức hoặc source theo input.
- Theo dõi lỗi compilation và cache eviction.
- Điều chỉnh cache/compilation rate chỉ khi đã có số liệu và hiểu ảnh hưởng ở cấp node.

Các thiết lập như `script.max_compilations_rate` và kích thước script cache phụ thuộc phiên bản Elasticsearch và cấu hình node. Không thay đổi mặc định trên production chỉ để che một thiết kế source động.

## 5. Giới hạn chi phí bằng cách thu hẹp candidate set

### 5.1. Filter trước, script sau

Chi phí lớn nhất thường đến từ số document phải chạy script. Vì vậy, inner query nên loại bỏ càng nhiều document không liên quan càng sớm càng tốt.

Ví dụ tốt hơn so với script trên `match_all`:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "description": "wireless keyboard"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "tenantId": "tenant-42"
              }
            },
            {
              "term": {
                "available": true
              }
            },
            {
              "range": {
                "price": {
                  "lte": 200
                }
              }
            }
          ]
        }
      },
      "script": {
        "source": "return _score * params.boost;",
        "params": {
          "boost": 1.1
        }
      }
    }
  }
}
~~~

Filter tenant, trạng thái và khoảng giá làm hẹp tập candidate. Script score chỉ tính cho những document còn lại.

### 5.2. Tránh script_score trên match_all nếu không thật sự cần

Query bên trong `match_all` khiến gần như toàn bộ document trong phạm vi index trở thành candidate. Nếu script được chạy trên một index rất lớn, chi phí có thể tăng nhanh.

Nếu nghiệp vụ thực sự cần xếp hạng mọi document, hãy cân nhắc:

- Lọc theo tenant, trạng thái, thời gian hoặc phạm vi dữ liệu.
- Chia dữ liệu theo index/alias hoặc routing phù hợp.
- Dùng tín hiệu scoring dựng sẵn.
- Tính trước score hoặc feature trong lúc ingest.
- Chỉ chạy script ở giai đoạn rerank trên tập nhỏ hơn nếu kiến trúc cho phép.

### 5.3. Filter context và scoring context

Điều kiện không cần đóng góp relevance nên đặt trong `filter` thay vì `must` khi phù hợp.

- `must` yêu cầu query khớp và thường tham gia tính score.
- `filter` yêu cầu điều kiện đúng nhưng không cộng điểm relevance.
- `must_not` loại document.
- `should` có thể tăng điểm hoặc tạo điều kiện bắt buộc tùy `minimum_should_match` và cấu trúc bool.

Filter giúp tách điều kiện nghiệp vụ khỏi phần tính điểm. Nó cũng cho Elasticsearch cơ hội tận dụng filter cache trong các trường hợp phù hợp, dù không nên mặc định mọi filter đều được cache.

### 5.4. Giới hạn phạm vi index và shard

Một query chạy trên nhiều index hoặc nhiều shard có thể tạo thêm công việc phân phối và tổng hợp kết quả. Hãy chọn index/alias cần thiết, dùng routing khi dữ liệu được partition đúng cách và tránh wildcard index pattern quá rộng.

Routing chỉ có lợi khi cách phân vùng dữ liệu và query được thiết kế đồng bộ. Chọn routing không đúng có thể bỏ sót document hoặc làm mất cân bằng tải giữa shard.

## 6. Giữ script ngắn và chi phí dự đoán được

### 6.1. Tránh vòng lặp và thao tác nặng

Script score được gọi nhiều lần, thường một lần cho mỗi candidate document. Vì vậy, một thao tác nhỏ nhân với hàng trăm nghìn document có thể trở thành chi phí lớn.

Nên tránh:

- Vòng lặp qua collection lớn trong mỗi document.
- Regex phức tạp hoặc xử lý chuỗi dài.
- Tạo nhiều object tạm không cần thiết.
- Tính toán lặp lại cùng một hằng số.
- Đọc `_source` hoặc phân tích JSON cho mỗi hit khi có thể dùng doc values.
- Công thức có nhánh phức tạp mà không cần thiết.

Ưu tiên phép toán số học đơn giản, kiểm tra field ngắn gọn và tham số đã được tính trước ở ứng dụng.

### 6.2. Ưu tiên doc values

Doc values được tổ chức để truy cập giá trị field theo document và thường phù hợp với script scoring. Các field numeric, date và keyword thường là lựa chọn tốt cho tín hiệu ranking.

Ví dụ:

~~~painless
if (doc['rating'].size() == 0) {
    return _score;
}
double rating = doc['rating'].value;
return _score + rating * params.ratingWeight;
~~~

Với field dùng để scoring thường xuyên, hãy thiết kế mapping để có doc values. Không bật fielddata cho text chỉ vì script cần đọc field; hãy cân nhắc tạo numeric/keyword field phụ hoặc chuẩn hóa dữ liệu khi ingest.

### 6.3. Tính trước những gì có thể tính trước

Nếu một công thức chỉ phụ thuộc dữ liệu không đổi trong thời gian dài, hãy cân nhắc tính trước lúc ghi document.

Ví dụ:

- Điểm chất lượng tổng hợp.
- Tỷ lệ chuyển đổi đã chuẩn hóa.
- Nhóm ưu tiên.
- Giá trị popularity đã log-transform.
- Trạng thái nghiệp vụ được quy đổi thành numeric rank.

Khi query chỉ cần đọc một field đã tính sẵn, chi phí có thể thấp hơn chạy công thức phức tạp cho mọi candidate.

Cần cập nhật lại feature khi dữ liệu nguồn thay đổi. Tính trước giúp query rẻ hơn nhưng chuyển một phần chi phí sang ingestion và đồng bộ dữ liệu.

### 6.4. Tránh tính toán lại giá trị bất biến trong script

Nếu `k`, trọng số hoặc hệ số chuẩn hóa không thay đổi theo document, truyền qua params hoặc tính sẵn trong ứng dụng. Không gọi các phép tính đắt tiền nhiều lần nếu có thể chuẩn hóa tham số trước request.

Với công thức có log, exp hoặc distance, hãy kiểm tra miền giá trị và tránh giá trị gây overflow/underflow.

## 7. Giới hạn score và xử lý giá trị không hợp lệ

### 7.1. Score phải không âm và hữu hạn

Script score phải trả về một số hợp lệ, không âm. Các giá trị âm, `NaN` hoặc vô cực có thể khiến Elasticsearch từ chối truy vấn hoặc phát sinh lỗi khi chuyển score.

Không dùng công thức có thể trả số âm mà không kiểm tra. Với tín hiệu có thể âm, hãy chuyển thành miền hợp lệ hoặc dùng max/clamp theo ý nghĩa nghiệp vụ.

Ví dụ:

~~~painless
double raw = doc['priority'].size() == 0
    ? 0.0
    : doc['priority'].value;

double safePriority = Math.max(0.0, Math.min(raw, 100.0));
return _score * (1.0 + safePriority / 100.0);
~~~

Đoạn script giới hạn priority trong khoảng 0–100 trước khi dùng. Cần chọn giới hạn theo dữ liệu thật, không sao chép con số minh họa một cách máy móc.

### 7.2. Giới hạn multiplier

Nếu dùng multiplier, hãy xác định biên dưới và biên trên. Ví dụ:

\[
1 \le multiplier \le 1.5
\]

Điều này giúp tín hiệu phụ chỉ tăng score trong phạm vi kiểm soát. Nếu muốn một tín hiệu có thể giảm điểm, hãy đảm bảo multiplier vẫn không âm và không làm mất khả năng phân biệt theo relevance ngoài ý muốn.

### 7.3. Tránh score quá lớn

Elasticsearch dùng score dạng số thực có độ chính xác hữu hạn. Một giá trị rất lớn có thể làm mất khác biệt giữa các score gần nhau hoặc gây vấn đề số học.

Chuẩn hóa feature trước khi kết hợp, giới hạn giá trị đầu vào và giữ công thức trong miền ổn định. Score không phải nơi lưu số liệu nghiệp vụ chính xác; không dùng nó để thay thế giá trị tiền tệ hoặc phép tính kế toán.

### 7.4. Kiểm tra field thiếu và kiểu mapping

Script truy cập `doc['field']` phụ thuộc mapping của index. Nếu field không được map, script có thể lỗi. Nếu field có mặt trong mapping nhưng document không có giá trị, `size()` có thể là 0.

Khi query qua nhiều index có mapping không đồng nhất, một field có thể tồn tại ở index này nhưng thiếu hoặc khác kiểu ở index khác. Hãy đồng bộ mapping hoặc xử lý rõ trường hợp unmapped theo khả năng của query/script context.

## 8. Script score, function_score và scoring dựng sẵn

### 8.1. Khi nào nên dùng function_score?

`function_score` cho phép kết hợp query score với một hoặc nhiều scoring functions. Các function có thể là:

- `weight`
- `field_value_factor`
- `random_score`
- Decay functions như `gauss`, `exp`, `linear`
- Script score trong các trường hợp cần custom logic

Nếu nhu cầu chỉ là nhân điểm theo field numeric, `field_value_factor` có thể đơn giản hơn `script_score`.

Ví dụ khái niệm:

~~~json
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "field_value_factor": {
        "field": "popularity",
        "modifier": "log1p",
        "factor": 0.5,
        "missing": 0
      },
      "boost_mode": "sum"
    }
  }
}
~~~

Hãy kiểm tra semantics `score_mode` và `boost_mode` theo công thức mong muốn. Function score có thể kết hợp nhiều function theo các chế độ khác nhau; không mặc định kết quả tương đương với một script tự viết.

### 8.2. Dùng decay function cho độ gần đây hoặc khoảng cách

Nếu muốn kết quả gần một mốc thời gian hoặc vị trí được ưu tiên, decay function có thể phù hợp hơn tự viết công thức.

Ví dụ ý tưởng:

- Bài viết mới hơn được tăng điểm.
- Địa điểm gần vị trí tìm kiếm được ưu tiên.
- Sự kiện gần thời điểm hiện tại có score cao hơn.

Decay functions cung cấp các tham số như origin, scale, offset và decay. Chúng giúp mô tả suy giảm điểm theo khoảng cách/thời gian mà không phải tự viết toàn bộ toán học trong Painless.

### 8.3. Dùng rank_feature khi tín hiệu phù hợp

Nếu một field numeric biểu diễn feature dùng cho ranking, có thể xem xét mapping `rank_feature` và query tương ứng. Elasticsearch hỗ trợ các hàm scoring cho feature như saturation, log và sigmoid tùy loại field/query.

Loại field/query này được thiết kế cho ranking feature và có thể hiệu quả hơn script tùy chỉnh. Cần kiểm tra yêu cầu mapping và các giới hạn của rank feature trước khi lựa chọn.

### 8.4. Bảng lựa chọn

| Nhu cầu | Công cụ nên xem xét |
|---|---|
| Kết hợp relevance với một numeric field | `field_value_factor` |
| Ưu tiên theo độ gần đây/khoảng cách | Decay function |
| Ranking feature có saturation/log | `rank_feature` |
| Công thức riêng, nhiều điều kiện số học | `script_score` |
| Nhiều hàm scoring kết hợp | `function_score` |
| Tín hiệu ổn định có thể tính trước | Precomputed numeric field |

Chỉ dùng script score khi công cụ dựng sẵn không diễn đạt được công thức cần thiết hoặc benchmark cho thấy lựa chọn đó phù hợp.

## 9. Giảm số document phải chạy script

### 9.1. Rescore trên nhóm kết quả đầu

Với một số hệ thống, có thể chạy truy vấn ban đầu rẻ để lấy candidate rồi áp dụng một bước rerank đắt hơn trên một cửa sổ kết quả đầu. Elasticsearch có rescore API với `window_size` để giới hạn số hit được rescore trên mỗi shard.

Mẫu này hữu ích khi:

1. Query đầu tiên dùng match/filter và scoring rẻ.
2. Lấy một nhóm candidate đủ rộng.
3. Chạy scoring nâng cao trên nhóm candidate đó.
4. Trả về top results sau rerank.

Cần kiểm tra query type và khả năng kết hợp script score trong rescore theo phiên bản Elasticsearch. `window_size` quá nhỏ có thể bỏ lỡ document đáng lẽ được đẩy lên nhờ tín hiệu phụ; quá lớn lại tăng chi phí.

### 9.2. Rerank ở ứng dụng có đánh đổi riêng

Có thể lấy một tập candidate giới hạn rồi tính điểm bổ sung trong ứng dụng. Cách này giúp kiểm soát thuật toán bằng Java nhưng có thể cần tải nhiều field và giữ dữ liệu trong memory.

Chỉ nên dùng khi candidate set đã nhỏ, dữ liệu cần thiết có thể lấy hiệu quả và việc xếp hạng lại trong ứng dụng không làm sai semantics phân trang. Không lấy một trang nhỏ rồi rerank nếu người dùng kỳ vọng top toàn cục; document phù hợp nằm ngoài trang đầu sẽ không có cơ hội được chọn.

### 9.3. Lọc bằng điều kiện nghiệp vụ trước khi rerank

Các điều kiện như tenant, quyền truy cập, trạng thái hoạt động, ngày hiệu lực và danh mục nên được đặt trong inner query/filter khi có thể.

Đặc biệt, filter phân quyền phải nằm trong query thực thi ở Elasticsearch hoặc được áp dụng bằng cơ chế bảo đảm không thể bỏ qua. Không chỉ lọc kết quả sau khi script scoring ở ứng dụng, vì như vậy có thể làm lộ metadata hoặc tạo chi phí không cần thiết.

## 10. Giới hạn chi phí ở cấp cluster và request

### 10.1. search.allow_expensive_queries

Elasticsearch có cluster setting `search.allow_expensive_queries`. Khi setting này tắt, một số query được xem là expensive, trong đó có `script_score`, có thể bị từ chối.

Điều này là chính sách phía cluster, không phải thuộc tính của `@Document` hay repository. Ứng dụng phải biết môi trường production có cho phép loại query này không.

Không bật setting toàn cluster chỉ để một query thiếu tối ưu chạy được. Hãy đánh giá candidate count, thay thế scoring dựng sẵn, hoặc thay đổi cách lập chỉ mục trước.

### 10.2. Script compilation rate và cache

Script source cần được biên dịch. Elasticsearch có giới hạn tốc độ biên dịch và cache script đã biên dịch. Nếu tạo source mới liên tục, có thể gặp lỗi vượt compilation rate hoặc cache thrashing.

Giữ source cố định, truyền dữ liệu qua params và theo dõi các metric/log liên quan đến script. Các setting như `script.max_compilations_rate` và cache size có thể thay đổi theo phiên bản; kiểm tra tài liệu của cluster đang chạy trước khi điều chỉnh.

### 10.3. Search timeout không phải giới hạn CPU chính xác

Search request có thể đặt timeout để giới hạn thời gian chờ. Tuy nhiên timeout không phải quota CPU chính xác cho một script và có thể khiến response trả kết quả một phần với cờ `timed_out`.

Ứng dụng cần kiểm tra trạng thái timeout và không hiển thị một tập kết quả chưa hoàn chỉnh như kết quả đầy đủ nếu nghiệp vụ không cho phép.

### 10.4. Giới hạn page size không giới hạn số lần chạy script

Đặt `size: 10` chỉ giới hạn số hit trả về, không có nghĩa script chỉ chạy trên 10 document. Để xếp hạng top 10, Elasticsearch vẫn có thể cần tính score cho nhiều candidate phù hợp.

Đây là lý do quan trọng để filter candidate set. Page size nhỏ giảm dữ liệu trả về, nhưng không thay thế việc thu hẹp query bên trong.

### 10.5. Giới hạn input và quyền dùng query

API công khai không nên cho client gửi Painless source, stored script ID tùy ý, tên field tùy ý hoặc DSL hoàn chỉnh. Thay vào đó:

- Chọn script từ danh sách được ứng dụng quản lý.
- Chỉ nhận các params có kiểu rõ ràng.
- Validate miền giá trị của params.
- Giới hạn page size và độ rộng query.
- Áp dụng authorization filter.
- Giám sát query timeout và lỗi script.

Painless có sandbox và context riêng, nhưng điều đó không thay thế kiểm soát quyền truy cập và giới hạn chi phí ở tầng ứng dụng.

## 11. Tích hợp script_score trong Spring Data Elasticsearch

### 11.1. Dùng NativeQuery khi cần type-safe DSL

Spring Data Elasticsearch có `NativeQuery` để xây dựng query qua Elasticsearch Java API Client. Với script score, builder cụ thể phụ thuộc phiên bản client và Spring Data. Hãy dùng kiểu script/query builder được dependency hiện tại cung cấp thay vì sao chép một đoạn builder từ phiên bản khác.

Mô hình cần tạo là query DSL có cấu trúc:

- `script_score` ở lớp ngoài.
- Query bên trong gồm match/filter.
- Script source ổn định.
- Params tách riêng.

### 11.2. Dùng StringQuery cho JSON DSL tĩnh

Khi muốn quản lý query JSON trong tài nguyên hoặc có DSL đã được kiểm thử, có thể dùng `StringQuery`:

~~~java
String queryJson = """
{
  "script_score": {
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
          {
            "term": {
              "available": true
            }
          }
        ]
      }
    },
    "script": {
      "source": "return _score * (1.0 + params.boost);",
      "params": {
        "boost": 0.2
      }
    }
  }
}
""";

Query query = new StringQuery(queryJson);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Đây là query clause cho Spring Data, không phải toàn bộ search request body có trường `query` ở cấp ngoài. Với tham số runtime, hãy tạo JSON tree và serialize bằng Jackson thay vì nối chuỗi.

### 11.3. Dùng resource JSON và tham số runtime

Có thể lưu phần query trong classpath rồi thay giá trị `params` bằng Jackson:

~~~json
{
  "script_score": {
    "query": {
      "bool": {
        "must": [
          {
            "match": {
              "name": {
                "query": ""
              }
            }
          }
        ],
        "filter": [
          {
            "term": {
              "available": true
            }
          }
        ]
      }
    },
    "script": {
      "source": "return _score * (1.0 + params.boost);",
      "params": {
        "boost": 0.0
      }
    }
  }
}
~~~

Java cập nhật các node có kiểu:

~~~java
ObjectNode root = (ObjectNode) template.deepCopy();

ObjectNode match = (ObjectNode) root.at(
    "/script_score/query/bool/must/0/match/name"
);
match.put("query", keyword);

ObjectNode params = (ObjectNode) root.at(
    "/script_score/script/params"
);
params.put("boost", boost);
~~~

Sau đó serialize thành JSON và tạo `StringQuery`. Mỗi request cần một bản sao riêng của template để tránh hai request đồng thời ghi đè params của nhau.

### 11.4. Gắn sort và pageable riêng

Sort/pageable có thể được cấu hình qua Spring Data `Query` thay vì nhúng toàn bộ search request vào JSON:

~~~java
query.setPageable(PageRequest.of(0, 20));
~~~

Nếu cần sort theo score, hãy để query scoring quyết định thứ tự mặc định hoặc khai báo sort phù hợp. Nếu sort theo field nghiệp vụ, hãy hiểu rằng thứ tự field sort có thể thay đổi vai trò của score.

## 12. Kiểm thử công thức và hành vi ranking

### 12.1. Unit test cho hàm chuẩn hóa

Nếu công thức có thể tách thành hàm Java thuần, hãy kiểm thử các giá trị biên trước:

- Popularity bằng 0.
- Popularity thiếu.
- Popularity âm.
- Popularity tại ngưỡng.
- Popularity rất lớn.
- Trọng số bằng 0.
- Tham số k không hợp lệ.

Ví dụ kiểm tra hàm bão hòa:

~~~java
static double normalizePopularity(double popularity, double k) {
    if (k <= 0) {
        throw new IllegalArgumentException("k must be positive");
    }

    double safePopularity = Math.max(0.0, popularity);
    return safePopularity / (safePopularity + k);
}
~~~

Unit test cho hàm Java không xác minh Painless script giống hệt. Nó chỉ kiểm tra toán học và validation ở tầng ứng dụng.

### 12.2. Integration test với Elasticsearch

Cần integration test trên Elasticsearch tương thích để xác minh:

1. Mapping có field numeric và doc values phù hợp.
2. Script compile và chạy được trong Painless context.
3. Document thiếu field không làm query lỗi.
4. Score không âm và hữu hạn.
5. Params thay đổi kết quả theo kỳ vọng.
6. Filter inner query loại document ngoài phạm vi.
7. Thứ tự kết quả phù hợp công thức.
8. Cluster policy có cho phép script score.
9. Query không timeout trên tập dữ liệu đại diện.

Mock `ElasticsearchOperations` không kiểm tra được Painless compile hoặc cách Elasticsearch tính score.

### 12.3. So sánh ranking trước và sau

Tạo tập query đại diện, gán nhãn relevance và so sánh:

- Precision@k.
- NDCG@k.
- MRR.
- Tỷ lệ kết quả nghiệp vụ mong muốn xuất hiện ở đầu danh sách.
- Độ trễ p50, p95 và p99.
- CPU và số candidate được đánh giá.

Nếu ranking tốt hơn nhưng latency tăng quá mức, cần cân nhắc giảm candidate set, dùng feature precomputed hoặc thay công thức.

### 12.4. Dùng explain và profile có mục đích

Explain giúp hiểu score của một document cụ thể và các thành phần scoring. Profile API giúp quan sát chi phí các phần query trên shard.

Profile có overhead đáng kể và không nên bật rộng rãi trên mọi request production. Dùng trên truy vấn đại diện trong môi trường kiểm thử hoặc điều tra có kiểm soát.

## 13. Theo dõi chi phí trong vận hành

### 13.1. Chỉ số cần quan sát

Nên theo dõi ít nhất:

- Số request dùng script score.
- Latency p50/p95/p99 của nhóm query đó.
- Timeout và rejected request.
- Số shard/index được query.
- Số candidate ước lượng hoặc tổng hit.
- CPU và tải search thread pool.
- Script compilation/cache metrics và lỗi compilation.
- Số lượng query bị từ chối do expensive-query policy.

So sánh các chỉ số trước và sau khi triển khai công thức mới.

### 13.2. Log query có kiểm soát

Có thể log query ID, version script, thời gian thực thi, page size và trạng thái timeout. Tránh log toàn bộ dữ liệu nhạy cảm hoặc Painless source được tạo từ input.

Nếu nhiều query dùng chung stored script, log ID/version giúp xác định công thức đang chạy khi điều tra sự thay đổi ranking.

### 13.3. Rollout công thức mới

Khi thay đổi script score, có thể triển khai theo từng bước:

1. Tạo version script mới.
2. Chạy integration test và benchmark.
3. So sánh ranking với tập query đã gán nhãn.
4. Thử trên traffic hoặc dữ liệu thử nghiệm có kiểm soát.
5. Theo dõi latency, CPU, timeout và chất lượng kết quả.
6. Giữ khả năng quay lại version trước nếu có regression.

Đổi script được dùng chung có thể ảnh hưởng đồng thời nhiều endpoint. Hãy quản lý version và rollout rõ ràng thay vì sửa source không có kiểm soát.

## 14. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Script lỗi khi đọc field | Field không có trong mapping hoặc document thiếu giá trị | Kiểm tra mapping và dùng `doc['field'].size()` trước `.value` |
| Query bị từ chối dù DSL hợp lệ | `search.allow_expensive_queries` đang tắt | Kiểm tra cluster policy và đánh giá cách scoring khác |
| Compilation rate bị vượt | Source thay đổi liên tục giữa các request | Giữ source ổn định, truyền giá trị qua params |
| Ranking bị chi phối bởi popularity | Feature có thang đo lớn hơn text score | Chuẩn hóa và giới hạn multiplier |
| Script trả score lỗi | Công thức có số âm, NaN hoặc vô cực | Validate miền dữ liệu và giới hạn kết quả |
| Query rất chậm trên index lớn | Inner query chọn quá nhiều candidate | Thêm filter, routing phù hợp hoặc dùng rerank |
| `size` nhỏ nhưng query vẫn tốn CPU | Script vẫn phải chấm nhiều candidate để chọn top hits | Thu hẹp inner query; xem xét rescore window |
| Script dùng nhiều heap | Đọc text field qua fielddata hoặc thao tác object lớn | Dùng doc values/numeric field phù hợp |
| Kết quả không ổn định giữa các index | Mapping hoặc dữ liệu feature không đồng nhất | Đồng bộ schema và xử lý missing/unmapped |
| Test unit pass nhưng production lỗi | Chưa compile/chạy Painless trên Elasticsearch thật | Thêm integration test với đúng phiên bản |
| Thay stored script làm thay đổi nhiều màn hình | Nhiều query dùng chung script ID | Version hóa và rollout có kiểm soát |

## 15. Quy trình quyết định có nên dùng script_score

Trước khi viết script, hãy xác định:

1. Relevance score mặc định có thực sự chưa đáp ứng yêu cầu không?
2. Tín hiệu phụ có thể biểu diễn bằng `field_value_factor`, decay function hoặc `rank_feature` không?
3. Field dùng để scoring có doc values và mapping đúng không?
4. Query bên trong có thể lọc candidate đủ hẹp không?
5. Công thức có miền giá trị và score output được giới hạn không?
6. Source có ổn định để tận dụng compilation cache không?
7. Có thể tính trước feature lúc ingest không?
8. Có cần rescore chỉ trên top candidate không?
9. Có integration test và tập query để đánh giá ranking không?
10. Cluster production có cho phép expensive query và có đủ tài nguyên không?

Nếu công thức đơn giản, hãy dùng scoring function dựng sẵn. Nếu cần script, giữ nó ngắn, ổn định, dùng params và chạy trên candidate set đã được lọc.

## 16. Những điểm cần ghi nhớ

- `script_score` tính score mới cho các document khớp inner query.
- Painless script có thể kết hợp `_score`, doc values và params.
- Script score phải trả số hợp lệ, không âm và hữu hạn.
- Luôn kiểm tra field thiếu trước khi truy cập `.value`.
- Chuẩn hóa feature và giới hạn multiplier để tín hiệu phụ không lấn át relevance.
- Dùng params thay cho tạo source động để giảm biên dịch và tận dụng cache.
- Filter candidate trước khi script chạy; page size nhỏ không giới hạn số document phải chấm điểm.
- Ưu tiên doc values và tính trước feature nếu công thức có thể chuyển sang ingestion.
- Cân nhắc `field_value_factor`, decay function, `rank_feature` hoặc rescore trước khi dùng script cho mọi candidate.
- `search.allow_expensive_queries` có thể chặn script score; script compilation rate/cache cũng cần được theo dõi.
- Timeout không phải giới hạn CPU chính xác và có thể dẫn đến kết quả một phần.
- Kiểm thử Painless trên Elasticsearch thật, đo ranking và latency trên dữ liệu đại diện.

Script score hữu ích khi cần đưa tín hiệu nghiệp vụ vào ranking bằng công thức riêng. Chất lượng triển khai phụ thuộc vào việc chọn đúng candidate, giữ công thức ổn định và giới hạn chi phí tính toán. Khi các phần đó được thiết kế rõ, ứng dụng có thể cải thiện thứ tự kết quả mà vẫn giữ tải tìm kiếm trong phạm vi có thể dự đoán.
