# Cardinality, percentile và giới hạn độ chính xác

Elasticsearch cung cấp nhiều aggregation để tổng hợp dữ liệu mà không cần tải toàn bộ document về ứng dụng. Trong đó, `cardinality` dùng để ước lượng số giá trị duy nhất, còn `percentiles` và `percentile_ranks` dùng để mô tả phân phối của dữ liệu số.

Các aggregation này rất hữu ích cho dashboard, phân tích hành vi và theo dõi hiệu năng. Ví dụ, một hệ thống có thể cần ước lượng số người dùng duy nhất trong ngày, tính P50/P95/P99 của thời gian phản hồi hoặc xác định một giá trị đang nằm ở percentile nào trong tập dữ liệu.

Điểm cần hiểu rõ là các kết quả này thường mang tính xấp xỉ. Elasticsearch dùng thuật toán và cấu hình có giới hạn bộ nhớ để xử lý dữ liệu phân tán trên nhiều shard. Tăng độ chính xác thường làm tăng bộ nhớ hoặc thời gian tính toán. Vì vậy, cần chọn cấu hình theo yêu cầu nghiệp vụ thay vì mặc định rằng một con số percentile hay distinct count luôn chính xác tuyệt đối.

## 1. Tổng quan về Cardinality và Percentile

### 1.1. Cardinality là số lượng giá trị duy nhất

Cardinality trả lời câu hỏi có bao nhiêu giá trị khác nhau trong một field.

Ví dụ dữ liệu sự kiện:

| eventId | userId | eventType |
|---|---|---|
| E01 | U100 | view |
| E02 | U101 | click |
| E03 | U100 | purchase |
| E04 | U102 | view |
| E05 | U101 | view |

Có 5 document nhưng chỉ có 3 userId duy nhất: U100, U101 và U102.

Một aggregation thông thường có thể đếm số document. Cardinality aggregation đếm số giá trị duy nhất của field, nên phù hợp với các câu hỏi như:

- Có bao nhiêu người dùng duy nhất truy cập website?
- Có bao nhiêu địa chỉ IP khác nhau?
- Có bao nhiêu sản phẩm khác nhau được xem?
- Có bao nhiêu session hoặc thiết bị duy nhất?
- Có bao nhiêu mã đơn hàng khác nhau trong một khoảng thời gian?

Cardinality aggregation thường là ước lượng dựa trên HyperLogLog++, không phải phép đếm chính xác mọi giá trị duy nhất.

### 1.2. Percentile mô tả vị trí trong phân phối

Percentile cho biết một giá trị nằm ở vị trí nào trong phân phối đã sắp xếp.

Ví dụ, nếu P95 của thời gian phản hồi là 850 ms, có thể diễn giải gần đúng rằng 95% quan sát có thời gian phản hồi không vượt quá 850 ms và khoảng 5% quan sát nằm cao hơn mức đó.

Một số percentile thường gặp:

| Percentile | Ý nghĩa thường dùng |
|---|---|
| P50 | Median, giá trị ở giữa phân phối |
| P75 | Mốc mà khoảng 75% quan sát nằm ở hoặc dưới |
| P90 | Mốc 90% |
| P95 | Mốc 95%, thường dùng theo dõi tail latency |
| P99 | Mốc 99%, tập trung vào phần đuôi |
| P99.9 | Phần đuôi rất nhỏ, nhạy với outlier và lượng dữ liệu |

Percentile hữu ích hơn average trong nhiều bài toán latency vì average có thể che khuất một nhóm request rất chậm.

### 1.3. Percentiles và percentile ranks là hai chiều khác nhau

- `percentiles` nhận các mức phần trăm, trả về giá trị tương ứng trong phân phối.
- `percentile_ranks` nhận các giá trị cụ thể, trả về vị trí phần trăm ước lượng của từng giá trị trong phân phối.

Ví dụ:

- Percentile 95 trả về thời gian phản hồi ở mốc P95.
- Percentile rank của 500 ms trả về tỷ lệ phần trăm quan sát có giá trị ở hoặc dưới khoảng 500 ms.

Đừng nhầm hai phép tính này khi đặt tên field trên dashboard.

## 2. Cardinality aggregation

### 2.1. Query DSL cơ bản

Ví dụ đếm số userId duy nhất:

~~~json
{
  "size": 0,
  "aggs": {
    "unique_users": {
      "cardinality": {
        "field": "userId"
      }
    }
  }
}
~~~

`size: 0` cho biết không cần trả document hits. Response tập trung vào aggregation.

Kết quả có dạng khái niệm:

~~~json
{
  "aggregations": {
    "unique_users": {
      "value": 3
    }
  }
}
~~~

Giá trị `3` trong ví dụ dữ liệu nhỏ là kết quả minh họa. Với dữ liệu lớn, cardinality thường là ước lượng và có thể lệch so với số lượng distinct chính xác.

### 2.2. Field phải phù hợp để đếm distinct

Cardinality hoạt động trên giá trị của field được index. Các field thường dùng gồm:

- `keyword`: user ID, session ID, mã sản phẩm.
- Numeric: mã số hoặc giá trị số cần distinct.
- `ip`: địa chỉ IP.
- Một số kiểu field khác có hỗ trợ doc values theo mapping.

Với field text, cần hiểu mapping. Field `text` được phân tích thành token và thường không có doc values mặc định. Đếm cardinality trên text field thường không phải ý định mong muốn. Nếu cần đếm distinct toàn bộ chuỗi, hãy dùng keyword subfield.

Ví dụ multi-field:

~~~json
{
  "mappings": {
    "properties": {
      "email": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Khi cần đếm email duy nhất, sử dụng `email.keyword` thay vì `email`.

### 2.3. Cardinality có thể nằm trong bucket aggregation

Có thể tính số user duy nhất theo từng ngày hoặc từng danh mục:

~~~json
{
  "size": 0,
  "aggs": {
    "by_day": {
      "date_histogram": {
        "field": "eventTime",
        "calendar_interval": "day"
      },
      "aggs": {
        "unique_users": {
          "cardinality": {
            "field": "userId"
          }
        }
      }
    }
  }
}
~~~

Mỗi bucket ngày có một ước lượng distinct user riêng. Đây là mẫu phổ biến trong dashboard hoạt động hàng ngày.

Nếu có nhiều bucket, mỗi bucket chứa trạng thái cardinality riêng. Tổng chi phí bộ nhớ có thể tăng theo số bucket và cấu hình precision. Không nên tạo hàng trăm nghìn bucket rồi đặt precision threshold lớn cho mỗi bucket mà chưa đánh giá tải.

### 2.4. Missing values

Document không có field thường không đóng góp giá trị vào cardinality. Nếu muốn coi mọi document thiếu field là cùng một giá trị giả định, có thể sử dụng tùy chọn `missing`:

~~~json
{
  "cardinality": {
    "field": "campaignId",
    "missing": "unknown"
  }
}
~~~

Trong ví dụ, các document không có campaignId được xem như cùng một giá trị `unknown` cho aggregation. Điều này làm thay đổi ý nghĩa thống kê: kết quả bao gồm một nhóm giá trị đại diện cho dữ liệu thiếu.

Chỉ dùng missing khi nghiệp vụ thực sự muốn gom các document thiếu field thành một nhóm. Nếu không, để chúng bị bỏ qua thường phản ánh đúng hơn số giá trị thực sự đã biết.

### 2.5. Cardinality trên giá trị được tính bằng script

Có thể tính cardinality từ script hoặc runtime field trong trường hợp cần chuẩn hóa giá trị trước khi đếm. Ví dụ về mặt ý tưởng, chuẩn hóa mã thành chữ thường trước khi distinct.

Tuy nhiên, script có chi phí trên mỗi document và có thể làm tăng tải đáng kể. Nếu giá trị chuẩn hóa được dùng thường xuyên, nên tính trước và lưu vào một keyword field khi ingest.

Khi đếm một khóa ghép từ nhiều field, tránh nối chuỗi bằng delimiter có thể xuất hiện trong dữ liệu. Hai cặp giá trị khác nhau có thể tạo cùng một chuỗi nếu encoding không được thiết kế rõ. Cân nhắc composite aggregation hoặc tạo một khóa ghép đã chuẩn hóa, không nhập nhằng từ trước.

## 3. HyperLogLog++ và độ chính xác của Cardinality

### 3.1. Vì sao Elasticsearch không lưu toàn bộ tập giá trị?

Nếu một index có hàng trăm triệu user ID, việc giữ toàn bộ tập distinct trong bộ nhớ để đếm chính xác có thể rất tốn kém. Trên hệ thống phân tán, mỗi shard còn phải tạo và gửi thông tin về tập giá trị cho coordinator.

Cardinality aggregation dùng thuật toán HyperLogLog++ (HLL++) để ước lượng số phần tử duy nhất bằng một cấu trúc dữ liệu có kích thước bị giới hạn. Thay vì giữ mọi giá trị đã thấy, thuật toán dùng các register và thông tin băm để ước lượng cardinality.

Lợi ích:

- Bộ nhớ không tăng tuyến tính theo tổng số document.
- Có thể hợp nhất kết quả từ nhiều shard.
- Phù hợp với distinct count trên dữ liệu lớn.
- Cung cấp trade-off giữa bộ nhớ và độ chính xác.

Đổi lại, kết quả có sai số thống kê và không bảo đảm bằng số distinct thực tế trong mọi trường hợp.

### 3.2. precision_threshold là gì?

`precision_threshold` cho phép điều chỉnh mức cardinality mà Elasticsearch hướng tới độ chính xác cao hơn. Đây là ngưỡng mục tiêu cho số lượng giá trị duy nhất; không phải cam kết rằng mọi kết quả dưới ngưỡng đều chính xác tuyệt đối.

Ví dụ:

~~~json
{
  "cardinality": {
    "field": "userId",
    "precision_threshold": 10000
  }
}
~~~

Một số mốc quan trọng trong Elasticsearch:

- Giá trị mặc định thường là 3.000.
- Giá trị tối đa có hiệu lực là 40.000.
- Giá trị lớn hơn 40.000 không tiếp tục tăng độ chính xác.
- Bộ nhớ sử dụng tăng theo precision threshold.

Hãy kiểm tra tài liệu phiên bản Elasticsearch đang chạy vì các chi tiết triển khai và giới hạn có thể thay đổi giữa các phiên bản.

### 3.3. Chọn threshold theo cardinality dự kiến

Nếu một bucket thường chỉ có vài trăm user duy nhất, dùng threshold quá lớn có thể lãng phí bộ nhớ. Nếu một bucket thường có hàng chục nghìn giá trị, threshold mặc định có thể tạo sai số không phù hợp với yêu cầu dashboard.

Ví dụ định hướng:

| Cardinality dự kiến trong mỗi bucket | Hướng lựa chọn |
|---|---|
| Vài chục đến vài trăm | Threshold mặc định có thể đã đủ |
| Vài nghìn | Benchmark default và threshold cao hơn |
| Vài chục nghìn | Cân nhắc threshold gần giới hạn cần thiết |
| Hàng triệu | Không đặt threshold hàng triệu; thuật toán vẫn là ước lượng với cấu trúc bộ nhớ giới hạn |
| Cần distinct chính xác | Dùng cách liệt kê bucket hoặc mô hình dữ liệu khác |

Không chọn threshold chỉ dựa trên tổng document count. Điều cần ước lượng là số giá trị duy nhất trong từng aggregation bucket.

### 3.4. Trade-off bộ nhớ

Tăng precision threshold có thể giảm sai số ở vùng cardinality quan tâm, nhưng mỗi aggregation cần thêm trạng thái bộ nhớ. Nếu cardinality nằm trong nhiều bucket, tổng bộ nhớ có thể tăng đáng kể.

Cần xem xét đồng thời:

- Số bucket được tạo.
- Số aggregation cardinality trong request.
- Số shard tham gia.
- Số request chạy đồng thời.
- Threshold được đặt cho từng aggregation.
- Kích thước và phân phối dữ liệu thực tế.

Một dashboard có nhiều date histogram buckets, mỗi bucket lại có cardinality threshold cao, có thể tiêu thụ bộ nhớ nhiều hơn dự kiến.

### 3.5. Không cộng các cardinality bucket để suy ra distinct toàn cục

Giả sử:

- Ngày 1 có 100 user duy nhất.
- Ngày 2 có 120 user duy nhất.
- Có 50 user xuất hiện ở cả hai ngày.

Tổng distinct user trong hai ngày là 170, không phải 220.

Cardinality theo từng bucket có thể hữu ích để đo unique users mỗi ngày. Nhưng cộng các kết quả bucket không tạo ra unique users trên toàn khoảng thời gian nếu cùng một giá trị xuất hiện ở nhiều bucket.

Nếu cần unique toàn khoảng, chạy cardinality ở cấp toàn khoảng hoặc dùng phương pháp exact phù hợp.

### 3.6. Sai số không phải lúc nào cũng là một số cố định

Sai số cardinality là tính chất của thuật toán ước lượng. Không nên diễn giải kết quả như “luôn lệch tối đa 1%” hoặc tự cộng/trừ một biên cố định nếu không có benchmark và tài liệu cụ thể cho workload.

Hãy kiểm tra bằng dữ liệu mẫu có số distinct thật đã biết, với phân phối và quy mô gần production. Đo sai số tương đối:

\[
relativeError = \frac{|estimated - actual|}{actual}
\]

Khi actual bằng 0, cần xử lý riêng để tránh chia cho 0.

## 4. Khi nào cần distinct count chính xác?

### 4.1. Cardinality không phải phép đếm chính xác

Nếu nghiệp vụ yêu cầu một con số chính xác để đối soát, thanh toán, tính phí hoặc kiểm toán, không nên dùng cardinality approximation làm nguồn quyết định cuối cùng.

Cardinality phù hợp với phân tích, dashboard và metric mà sai số nhỏ có thể chấp nhận. Nó không thay thế một quy trình exact counting khi kết quả có hậu quả nghiệp vụ trực tiếp.

### 4.2. Composite aggregation để liệt kê khóa duy nhất

Composite aggregation cho phép phân trang qua các bucket theo một hoặc nhiều source field. Nếu cần đếm chính xác số khóa distinct, có thể duyệt tất cả bucket và đếm số bucket đã nhận.

Ví dụ query:

~~~json
{
  "size": 0,
  "aggs": {
    "unique_users": {
      "composite": {
        "size": 1000,
        "sources": [
          {
            "user": {
              "terms": {
                "field": "userId"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Nếu response có `after_key`, gửi request tiếp theo với `after` bằng giá trị đó cho đến khi hết bucket. Mỗi bucket đại diện một giá trị duy nhất theo source đã khai báo.

Đây là phép liệt kê bucket, nên chi phí phụ thuộc số distinct values. Với cardinality rất lớn, phải xử lý theo batch, giới hạn thời gian và bộ nhớ, đồng thời cân nhắc PIT hoặc chiến lược snapshot nếu dữ liệu thay đổi trong lúc duyệt.

### 4.3. Distinct trên tổ hợp nhiều field

Ví dụ cần đếm số cặp userId và deviceId duy nhất. Có thể tạo composite aggregation với hai source:

~~~json
{
  "size": 0,
  "aggs": {
    "unique_user_devices": {
      "composite": {
        "size": 1000,
        "sources": [
          {
            "user": {
              "terms": {
                "field": "userId"
              }
            }
          },
          {
            "device": {
              "terms": {
                "field": "deviceId"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Mỗi bucket biểu diễn một tổ hợp giá trị. Duyệt tất cả trang và đếm bucket sẽ cho số tổ hợp distinct trong phạm vi dữ liệu mà query chọn.

Nếu dùng script để ghép hai field thành một string rồi cardinality, cần encoding không nhập nhằng và tính đến missing/null. Composite thường thể hiện ý nghĩa tuple rõ ràng hơn.

### 4.4. Terms aggregation không phải cách exact vô điều kiện

Terms aggregation trả các bucket phổ biến nhất theo cấu hình `size` và `shard_size`. Nó có thể bỏ qua các bucket có tần suất thấp hơn và có các metadata như `sum_other_doc_count` hoặc `doc_count_error_upper_bound`.

Không nên đặt size nhỏ rồi đếm số bucket để kết luận đó là số distinct toàn bộ. Ngay cả khi tăng size rất lớn, giới hạn bucket và bộ nhớ vẫn cần được xem xét. Composite phù hợp hơn khi mục tiêu là duyệt đầy đủ các khóa theo trang.

### 4.5. Snapshot và dữ liệu thay đổi

Nếu dữ liệu thay đổi trong khi đang duyệt composite pages, các bucket có thể phản ánh trạng thái index ở các thời điểm khác nhau. Với báo cáo cần tái lập, hãy xác định snapshot hoặc khoảng thời gian dữ liệu đóng, cân nhắc PIT nếu API/version và loại aggregation hỗ trợ trong kiến trúc của bạn.

Đừng giả định nhiều request composite liên tiếp tự động tạo thành một transaction hoặc snapshot nhất quán.

## 5. Percentiles aggregation

### 5.1. Query DSL cơ bản

Ví dụ tính các percentile của thời gian phản hồi:

~~~json
{
  "size": 0,
  "aggs": {
    "response_time_percentiles": {
      "percentiles": {
        "field": "responseTime",
        "percents": [50, 90, 95, 99]
      }
    }
  }
}
~~~

Kết quả có thể có dạng:

~~~json
{
  "aggregations": {
    "response_time_percentiles": {
      "values": {
        "50.0": 120.5,
        "90.0": 410.0,
        "95.0": 620.0,
        "99.0": 1250.0
      }
    }
  }
}
~~~

Các giá trị là ví dụ. Nếu P99 là 1.250 ms, điều đó cho biết phần lớn request nhanh hơn mốc đó và nhóm đuôi khoảng 1% có độ trễ cao hơn.

### 5.2. Chọn các percentile phù hợp

Không phải dashboard nào cũng cần mọi mốc. Một số lựa chọn:

- P50 cho trải nghiệm điển hình.
- P90 hoặc P95 cho nhóm request chậm hơn bình thường.
- P99 cho tail latency.
- P99.9 khi có đủ dữ liệu và yêu cầu quan sát tail rất sâu.

P99.9 trên một bucket chỉ có vài trăm quan sát thường không ổn định và khó diễn giải. Percentile càng cao thì càng phụ thuộc vào số lượng mẫu và các outlier ở đuôi phân phối.

### 5.3. Percentile không phải average

Giả sử latency (ms) của 5 request là:

~~~text
10, 12, 15, 20, 1000
~~~

Average là 211,4 ms, nhưng median/P50 gần 15 ms. Average bị kéo lên bởi một request rất chậm. P95/P99 giúp nhìn thấy tail latency, trong khi P50 phản ánh trải nghiệm ở giữa phân phối.

Nên kết hợp percentile với count và đôi khi cả average/min/max để hiểu quy mô mẫu và hình dạng dữ liệu.

### 5.4. Percentile theo từng bucket

Có thể tính latency percentile theo service, endpoint hoặc ngày:

~~~json
{
  "size": 0,
  "aggs": {
    "by_service": {
      "terms": {
        "field": "service.keyword",
        "size": 20
      },
      "aggs": {
        "latency": {
          "percentiles": {
            "field": "responseTime",
            "percents": [50, 95, 99]
          }
        }
      }
    }
  }
}
~~~

Mỗi service có một phân phối riêng. Điều này hữu ích để xác định service nào có tail latency cao.

Terms aggregation có thể không trả mọi service nếu số lượng bucket vượt size. Nếu cần liệt kê toàn bộ nhóm, hãy cân nhắc composite aggregation.

### 5.5. Percentile ranks

Nếu muốn biết 500 ms nằm ở percentile nào, dùng `percentile_ranks`:

~~~json
{
  "size": 0,
  "aggs": {
    "latency_rank": {
      "percentile_ranks": {
        "field": "responseTime",
        "values": [100, 250, 500, 1000]
      }
    }
  }
}
~~~

Kết quả có thể cho biết tỷ lệ phần trăm quan sát có giá trị ở hoặc dưới từng ngưỡng. Ví dụ, nếu percentile rank của 500 ms là 92, có thể hiểu khoảng 92% quan sát không vượt quá ngưỡng 500 ms theo phép ước lượng.

Dùng percentile ranks khi câu hỏi bắt đầu bằng “bao nhiêu phần trăm request hoàn thành trong 500 ms?” thay vì “P95 là bao nhiêu ms?”.

## 6. Thuật toán percentile và trade-off độ chính xác

### 6.1. T-digest là phương pháp mặc định phổ biến

Elasticsearch dùng T-digest cho percentile aggregation theo mặc định. T-digest nén phân phối thành các centroid, cho phép tính percentile gần đúng mà không giữ toàn bộ giá trị đã sắp xếp.

Đặc điểm:

- Có thể hợp nhất các sketch từ nhiều shard.
- Sử dụng bộ nhớ ít hơn việc giữ mọi giá trị.
- Phù hợp với dữ liệu lớn và phân phối rộng.
- Có thể cung cấp độ chính xác tốt ở phần đuôi khi được cấu hình phù hợp.
- Kết quả là ước lượng, không phải thứ tự thống kê exact trên toàn bộ raw values.

### 6.2. compression điều khiển T-digest

Có thể điều chỉnh `compression`:

~~~json
{
  "percentiles": {
    "field": "responseTime",
    "percents": [50, 95, 99],
    "tdigest": {
      "compression": 200
    }
  }
}
~~~

Compression cao hơn thường tăng độ chính xác nhưng cũng làm tăng bộ nhớ và thời gian xử lý. Giá trị mặc định phổ biến là 100. Hãy kiểm tra mặc định và giới hạn của phiên bản Elasticsearch đang chạy.

Không nên tăng compression tối đa cho mọi aggregation. Nếu query có nhiều bucket, mỗi bucket có thể giữ trạng thái T-digest riêng; tổng chi phí có thể tăng đáng kể.

### 6.3. Compression không phải phần trăm chính xác

`compression: 200` không có nghĩa percentile chính xác 200% hoặc sai số 0,5%. Đây là tham số kiểm soát kích thước/độ chi tiết của T-digest, không phải một cam kết error bound trực tiếp cho mọi phân phối.

Độ chính xác thực tế còn phụ thuộc:

- Phân phối dữ liệu.
- Số lượng quan sát.
- Mức percentile cần tính.
- Số shard và cách hợp nhất kết quả.
- Số bucket và số request đồng thời.
- Phiên bản Elasticsearch và triển khai thuật toán.

Hãy benchmark trên dữ liệu gần production thay vì suy ra sai số chỉ từ giá trị compression.

### 6.4. T-digest và phân phối có outlier

P99/P99.9 nhạy với các giá trị cực lớn. T-digest được thiết kế để phân bổ độ chi tiết không đồng đều trên phân phối và thường chú ý nhiều hơn đến phần đuôi, nhưng kết quả vẫn là ước lượng.

Nếu dữ liệu có outlier bất thường, hãy kiểm tra nguồn dữ liệu, đơn vị đo và cách xử lý timeout. Một giá trị latency bị ghi nhầm đơn vị từ milliseconds thành microseconds có thể làm percentile mất ý nghĩa dù aggregation chạy đúng.

## 7. HDR Histogram

### 7.1. Chọn phương pháp HDR

Percentiles aggregation có thể dùng phương pháp HDR Histogram thay cho T-digest trong các phiên bản Elasticsearch hỗ trợ:

~~~json
{
  "percentiles": {
    "field": "responseTime",
    "percents": [50, 95, 99],
    "hdr": {
      "number_of_significant_value_digits": 3
    }
  }
}
~~~

HDR Histogram được thiết kế để theo dõi phân phối số với độ chính xác có ý nghĩa theo chữ số. Nó có thể phù hợp với latency hoặc metric có miền giá trị được xác định tương đối rõ.

### 7.2. number_of_significant_value_digits

`number_of_significant_value_digits` điều chỉnh số chữ số có nghĩa mà histogram duy trì. Giá trị chính xác được hỗ trợ và mặc định phụ thuộc phiên bản Elasticsearch; cấu hình phổ biến là 3 chữ số có nghĩa.

Tăng độ chính xác làm tăng bộ nhớ histogram. Mức sử dụng bộ nhớ còn phụ thuộc range giá trị phải biểu diễn, nên outlier rất lớn có thể khiến cấu trúc cần nhiều bộ nhớ hơn.

Không tăng số chữ số có nghĩa nếu độ chính xác bổ sung không tạo khác biệt trong quyết định nghiệp vụ.

### 7.3. T-digest và HDR khác nhau thế nào?

| Tiêu chí | T-digest | HDR Histogram |
|---|---|---|
| Cách biểu diễn | Centroids nén phân phối | Histogram với các bucket theo độ chính xác |
| Tham số chính | compression | number_of_significant_value_digits |
| Bộ nhớ | Phụ thuộc compression và số bucket | Phụ thuộc độ chính xác và range giá trị |
| Đặc điểm | Linh hoạt với phân phối rộng, có thể hợp nhất sketch | Hữu ích khi miền giá trị và độ chính xác tương đối đã biết |
| Kết quả | Xấp xỉ | Xấp xỉ |
| Lựa chọn | Benchmark theo phân phối thực tế | Benchmark theo range và yêu cầu precision |

Không có phương pháp nào luôn tốt hơn trong mọi workload. Chọn theo dữ liệu, số bucket, số shard, latency và bộ nhớ thực tế.

### 7.4. Giá trị bất thường và range

HDR cần biểu diễn range số. Nếu dữ liệu có outlier lớn hoặc range thay đổi rộng, footprint bộ nhớ có thể khác xa dự kiến.

Hãy xác định:

- Đơn vị field (ms, µs, bytes, điểm).
- Min/max hợp lý.
- Outlier có phải dữ liệu hợp lệ không.
- Có cần clamp hoặc loại bỏ dữ liệu sai từ pipeline ingest không.
- Mức độ chính xác cần thiết ở từng percentile.

Không loại bỏ outlier chỉ để làm aggregation nhẹ hơn nếu outlier là tín hiệu vận hành quan trọng. Hãy xử lý ở tầng dữ liệu theo quy tắc được định nghĩa rõ.

## 8. Cardinality và percentile trong Spring Data Elasticsearch

### 8.1. Xây NativeQuery với aggregation

Spring Data Elasticsearch hỗ trợ aggregation thông qua `NativeQuery` và Elasticsearch Java API Client. Ví dụ khái niệm với cardinality:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.range(r -> r
        .field("eventTime")
        .gte(JsonData.of("2026-01-01T00:00:00Z"))
    ))
    .withAggregation(
        "unique_users",
        Aggregation.of(a -> a.cardinality(c -> c
            .field("userId")
            .precisionThreshold(10000)
        ))
    )
    .build();

SearchHits<EventDocument> hits =
    operations.search(query, EventDocument.class);
~~~

Kiểu builder và cách biểu diễn range value có thể khác theo phiên bản Elasticsearch Java API Client. Đoạn code minh họa cách đặt aggregation vào query, không phải cam kết rằng mọi phiên bản có cùng chữ ký overload.

Nếu chỉ cần aggregation, có thể đặt page size bằng 0 hoặc cấu hình query để không lấy document hits, tùy API đang dùng.

### 8.2. Thêm percentile aggregation

Với percentile, builder có thể được tạo theo cấu trúc tương tự:

~~~java
Aggregation latencyPercentiles = Aggregation.of(a -> a
    .percentiles(p -> p
        .field("responseTime")
        .percents(50.0, 95.0, 99.0)
        .tdigest(t -> t.compression(200.0))
    )
);
~~~

Tên method/overload cụ thể phụ thuộc phiên bản Java API Client. Một số bản client biểu diễn danh sách percentile hoặc cấu hình method bằng kiểu builder khác. Hãy dùng IDE/API reference của dependency dự án để xác nhận.

Sau đó gắn aggregation vào `NativeQuery`:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation("latency_percentiles", latencyPercentiles)
    .build();
~~~

### 8.3. Đọc aggregation từ SearchHits

`ElasticsearchOperations.search` trả về `SearchHits<T>`. Metadata aggregation được giữ trong phần aggregation container của response. Cách unwrap cụ thể phụ thuộc Spring Data Elasticsearch version và loại client aggregation.

Trong các phiên bản dùng Elasticsearch Java API Client, thường cần lấy `AggregationsContainer` từ `SearchHits`, ép về implementation Elasticsearch tương ứng rồi đọc `Aggregate` theo tên aggregation. Kiểu kết quả là tagged union; cần kiểm tra nhánh thực tế như cardinality hoặc percentiles trước khi lấy giá trị.

Không ép một aggregate bất kỳ sang kiểu percentile/cardinality nếu không kiểm tra loại. Một request có thể trả nhiều aggregation và nested bucket, nên mapper cần biết chính xác tên và cấu trúc đã khai báo.

### 8.4. Tách mapper aggregation khỏi controller

Nên tạo mapper/service chuyển kết quả aggregation thành DTO ứng dụng:

~~~java
public record UniqueUserMetric(
    long estimatedCount
) {
}

public record LatencyPercentileMetric(
    Map<Double, Double> values
) {
}
~~~

Với cardinality, có thể đặt tên `estimatedCount` để nhắc người dùng API rằng đây là ước lượng. Với percentile, giữ cặp percentile-value và đơn vị rõ ràng.

Không trả raw client aggregation object trực tiếp từ controller. Cấu trúc đó phụ thuộc thư viện và không phải hợp đồng API ổn định.

### 8.5. Đơn vị đo phải rõ ràng

Nếu field `responseTime` lưu milliseconds, DTO và dashboard cần ghi rõ `ms`. Nếu lưu microseconds, không được hiển thị như milliseconds.

Có thể dùng DTO:

~~~java
public record PercentileValue(
    double percentile,
    double value,
    String unit
) {
}
~~~

Một field numeric không tự mang đơn vị. Đơn vị phải được định nghĩa trong mapping, ingestion contract hoặc tên field.

## 9. Aggregation lồng nhau và số lượng bucket

### 9.1. Cardinality trong nhiều bucket

Ví dụ cardinality theo ngày và theo loại sự kiện:

~~~json
{
  "size": 0,
  "aggs": {
    "by_day": {
      "date_histogram": {
        "field": "eventTime",
        "calendar_interval": "day"
      },
      "aggs": {
        "by_event_type": {
          "terms": {
            "field": "eventType",
            "size": 10
          },
          "aggs": {
            "unique_users": {
              "cardinality": {
                "field": "userId",
                "precision_threshold": 3000
              }
            }
          }
        }
      }
    }
  }
}
~~~

Mỗi bucket con có cardinality sketch riêng. Khi số ngày, event type và threshold đều tăng, bộ nhớ aggregation có thể tăng đáng kể.

### 9.2. Percentile trong bucket

Percentile theo từng endpoint:

~~~json
{
  "size": 0,
  "aggs": {
    "by_endpoint": {
      "terms": {
        "field": "endpoint.keyword",
        "size": 50
      },
      "aggs": {
        "latency_percentiles": {
          "percentiles": {
            "field": "responseTime",
            "percents": [50, 95, 99]
          }
        }
      }
    }
  }
}
~~~

Mỗi endpoint có phân phối latency riêng. Nếu endpoint có cardinality cao, terms size 50 chỉ trả nhóm bucket theo cấu hình, không phải mọi endpoint.

### 9.3. Bucket explosion

Nested aggregations có thể nhân số bucket qua từng tầng. Ví dụ 365 ngày × 100 endpoint × 10 region đã tạo ra nhiều bucket trước khi tính cardinality hoặc percentile bên trong.

Cần:

- Giới hạn terms size.
- Dùng filter để thu hẹp thời gian và phạm vi dữ liệu.
- Tránh nhiều tầng bucket không cần thiết.
- Xem xét composite aggregation để phân trang bucket.
- Đo memory/latency với số bucket gần thực tế.
- Theo dõi giới hạn `search.max_buckets` của cluster.

Một query trả ít document hits vẫn có thể tạo rất nhiều aggregation buckets và tiêu thụ tài nguyên đáng kể.

## 10. Độ chính xác của kết quả percentile

### 10.1. Percentile là ước lượng

T-digest và HDR đều biểu diễn phân phối theo cấu trúc tóm tắt thay vì sắp xếp toàn bộ raw values trên toàn cluster. Do đó kết quả percentile có thể lệch so với percentile exact tính trên danh sách dữ liệu đầy đủ.

Mức sai khác phụ thuộc thuật toán, cấu hình, phân phối và cách dữ liệu được chia trên shard. Không nên dùng một kết quả percentile như một ranh giới toán học tuyệt đối khi nghiệp vụ yêu cầu quyết định ở sát ngưỡng.

### 10.2. Sample size ảnh hưởng cách diễn giải

Nếu bucket chỉ có 10 request, P99 không mang nhiều ý nghĩa thực tế: phần đuôi 1% nhỏ hơn một quan sát. Nếu bucket có hàng triệu request, P99 có thể ổn định hơn nhưng vẫn là kết quả approximate của aggregation.

Dashboard nên hiển thị count cùng percentile để người xem biết quy mô mẫu. Có thể ẩn hoặc đánh dấu percentile rất cao khi sample size quá thấp.

### 10.3. Phân phối lệch và outlier

Latency thường có phân phối lệch phải: phần lớn request nhanh, một số request rất chậm. Average không đủ để mô tả tail. P95/P99 có thể hữu ích, nhưng cũng nhạy với:

- Timeout được ghi thành giá trị cố định.
- Request bị retry và đếm nhiều lần.
- Đơn vị đo không đồng nhất.
- Dữ liệu lỗi hoặc outlier không hợp lệ.
- Bucket có quá ít quan sát.

Trước khi điều chỉnh compression, hãy kiểm tra chất lượng dữ liệu và cách ghi nhận metric.

### 10.4. Không cộng percentile của các bucket

P95 của ngày 1 cộng P95 của ngày 2 không tạo P95 của toàn bộ hai ngày. Percentile không có tính cộng tuyến.

Tương tự, không lấy trung bình P95 của từng service để suy ra P95 toàn hệ thống. Muốn percentile toàn cục, phải chạy aggregation trên toàn bộ tập dữ liệu mục tiêu hoặc dùng một mô hình phân phối có thể hợp nhất đúng cách.

## 11. Chọn cấu hình theo yêu cầu nghiệp vụ

### 11.1. Dashboard realtime

Với dashboard cập nhật liên tục:

- Cardinality approximate thường phù hợp để ước lượng active users.
- Percentile approximate thường phù hợp theo dõi latency.
- Giữ threshold/compression ở mức vừa phải.
- Giới hạn số bucket và thời gian truy vấn.
- Chấp nhận một mức sai số đã được đánh giá.

Dashboard cần phản hồi nhanh và xu hướng ổn định hơn là một con số exact tuyệt đối cho mọi lần refresh.

### 11.2. Báo cáo phân tích

Với báo cáo định kỳ:

- Có thể tăng precision threshold hoặc compression nếu benchmark chứng minh cần thiết.
- Giảm số bucket không cần thiết.
- Dùng khoảng thời gian cố định.
- Ghi nhận cấu hình aggregation cùng dữ liệu kết quả.
- So sánh với phép tính exact trên sample để đo sai số.

Nếu báo cáo phải tái lập, cần ghi lại phiên bản mapping, query, cấu hình aggregation và khoảng dữ liệu.

### 11.3. Đối soát và tính phí

Với nghiệp vụ cần exact count:

- Không dựa vào cardinality approximation để tính hóa đơn.
- Cân nhắc composite aggregation duyệt đầy đủ distinct keys.
- Hoặc duy trì bảng/stream state distinct trong hệ thống lưu trữ phù hợp.
- Kiểm soát snapshot và dữ liệu đến muộn.
- Kiểm tra số liệu bằng nguồn đối soát độc lập.

Với percentile dùng làm SLA hoặc quyết định tự động, cần xác định sai số được chấp nhận và cách xử lý trường hợp giá trị sát ngưỡng.

## 12. Kiểm thử độ chính xác và hiệu năng

### 12.1. Tạo dataset có kết quả exact đã biết

Để đánh giá cardinality, tạo dataset với:

- Số document đã biết.
- Số distinct userId đã biết.
- Tỷ lệ lặp giá trị khác nhau.
- Giá trị thiếu.
- Cardinality nhỏ, vừa và lớn.
- Nhiều shard hoặc index nếu production có phân tán.

Tính exact distinct count bên ngoài hoặc bằng phép duyệt bucket trên dataset test, rồi so sánh với cardinality estimate.

### 12.2. Đo sai số cardinality

Một metric đơn giản:

\[
relativeError = \frac{|estimate - exact|}{exact}
\]

Đánh giá nhiều lần trên nhiều phân phối, không chỉ một dataset. Nếu exact bằng 0, so sánh tuyệt đối thay vì tính relative error.

Thử các precision threshold khác nhau và ghi nhận đồng thời:

- Sai số.
- Thời gian query.
- Heap/memory.
- Số bucket.
- Số shard.
- Số request chạy đồng thời.

### 12.3. Đánh giá percentile bằng phép tính tham chiếu

Trên dataset nhỏ, có thể lấy toàn bộ giá trị số, sắp xếp và tính percentile bằng một định nghĩa interpolation rõ ràng. So sánh kết quả tham chiếu với T-digest/HDR.

Lưu ý các thư viện có thể dùng quy ước interpolation khác nhau (nearest rank, linear interpolation hoặc phương pháp khác). Trước khi kết luận Elasticsearch sai, hãy đảm bảo hai bên dùng cùng định nghĩa percentile.

### 12.4. Benchmark T-digest và HDR

Với cùng dữ liệu và cùng danh sách percentile:

1. Chạy T-digest ở compression mặc định.
2. Tăng compression theo một vài mức.
3. Chạy HDR với precision digits phù hợp.
4. So sánh sai khác P50/P95/P99/P99.9.
5. Ghi nhận heap và latency.
6. Thử bucket count và shard count gần production.
7. Chọn cấu hình đáp ứng yêu cầu với chi phí chấp nhận được.

Không chỉ so sánh một query đơn trên index nhỏ. Chi phí thực tế phụ thuộc số bucket, shard và concurrency.

### 12.5. Test với dữ liệu biên

Nên có:

- Field thiếu hoặc null.
- Giá trị bằng 0.
- Giá trị âm nếu miền dữ liệu cho phép.
- Giá trị rất lớn.
- Dữ liệu tập trung tại một giá trị.
- Phân phối lệch mạnh.
- Bucket rỗng.
- Bucket có rất ít quan sát.
- Document đến muộn hoặc thay đổi trong lúc báo cáo.

Các trường hợp này giúp phát hiện sai lệch do mapping, ingestion và cách diễn giải thống kê.

## 13. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Cardinality thấp hoặc cao hơn exact count | HLL++ là thuật toán ước lượng | Benchmark với exact sample và điều chỉnh precision threshold |
| Tăng precision threshold nhưng bộ nhớ tăng mạnh | Nhiều bucket/cardinality aggregation cùng request | Giảm bucket, giảm số aggregation hoặc hạ threshold |
| Cộng unique users mỗi ngày ra tổng sai | Một user xuất hiện ở nhiều ngày | Chạy cardinality trên toàn khoảng hoặc dùng exact distinct |
| Đếm distinct text không đúng mong muốn | Dùng field text đã phân tích thành token | Dùng keyword subfield |
| Terms bucket count nhỏ hơn distinct thật | Terms chỉ trả bucket theo size/shard_size | Dùng composite để duyệt toàn bộ bucket |
| P99 dao động mạnh | Sample size nhỏ hoặc tail có outlier | Hiển thị count, mở rộng cửa sổ và kiểm tra dữ liệu |
| P95 khác giữa công cụ báo cáo | Khác định nghĩa percentile/interpolation | Chuẩn hóa phương pháp tham chiếu |
| Compression cao gây chậm | T-digest giữ trạng thái chi tiết hơn | Giảm compression hoặc benchmark HDR |
| HDR tiêu thụ bộ nhớ bất thường | Range giá trị rộng hoặc precision cao | Kiểm tra đơn vị/outlier và cấu hình significant digits |
| Percentile toàn hệ thống không khớp | Lấy trung bình/cộng percentile từ từng bucket | Chạy percentile trên tập dữ liệu toàn cục |
| Aggregation request quá nặng | Bucket explosion hoặc quá nhiều metric | Thu hẹp filter, giảm bucket và theo dõi max_buckets |
| Spring Data không đọc được aggregate | Khác biệt API client/version hoặc unwrap sai kiểu | Kiểm tra AggregationsContainer và kiểu Aggregate thực tế |

## 14. Quy trình triển khai aggregation trong ứng dụng

Một quy trình thực tế:

1. Xác định câu hỏi thống kê: distinct count, percentile hay percentile rank.
2. Chọn field có mapping và doc values phù hợp.
3. Xác định kết quả có thể approximate hay bắt buộc exact.
4. Ước lượng cardinality hoặc sample size trong từng bucket.
5. Chọn precision threshold cho cardinality.
6. Chọn T-digest hoặc HDR và cấu hình độ chính xác cho percentile.
7. Giới hạn bucket count, shard scope và khoảng thời gian.
8. Xây aggregation bằng NativeQuery hoặc API client phù hợp.
9. Đọc aggregation container theo đúng kiểu và ánh xạ sang DTO có đơn vị rõ ràng.
10. Benchmark sai số, bộ nhớ và latency trên dữ liệu đại diện.
11. Ghi lại cấu hình cùng phiên bản query/mapping.
12. Theo dõi sai số và chi phí khi dữ liệu hoặc số bucket tăng.

## 15. Những điểm cần ghi nhớ

- Cardinality đếm số giá trị duy nhất và thường là ước lượng bằng HyperLogLog++.
- `precision_threshold` điều chỉnh trade-off giữa độ chính xác và bộ nhớ; mặc định phổ biến là 3.000 và mức tối đa có hiệu lực là 40.000.
- Threshold là mục tiêu độ chính xác, không phải cam kết exact.
- Cardinality theo từng bucket không thể cộng để có distinct count toàn cục nếu giá trị lặp giữa bucket.
- Composite aggregation có thể duyệt đầy đủ các khóa distinct theo trang khi cần exact counting, nhưng chi phí phụ thuộc số bucket.
- Percentiles trả giá trị tại các mốc phần trăm; percentile ranks trả vị trí của các giá trị được hỏi.
- T-digest dùng `compression` để điều chỉnh độ chi tiết, đổi lại bộ nhớ và thời gian xử lý.
- HDR dùng `number_of_significant_value_digits`; footprint phụ thuộc độ chính xác và range giá trị.
- Percentile là ước lượng và nhạy với sample size, outlier, đơn vị đo và phân phối dữ liệu.
- Không cộng hoặc lấy trung bình percentile của các bucket để suy ra percentile toàn cục.
- Spring Data Elasticsearch giữ aggregation trong response container; cần unwrap đúng loại aggregation theo phiên bản client.
- Giới hạn số bucket và số aggregation lồng nhau để tránh bucket explosion.
- Với nghiệp vụ đối soát hoặc tính phí, dùng phương pháp exact thay vì dựa vào approximation chưa được kiểm chứng.

Cardinality và percentile giúp tổng hợp dữ liệu lớn với chi phí có thể kiểm soát, miễn là hiểu rõ giới hạn của thuật toán. Chọn đúng field, bucket, precision và phương pháp tham chiếu sẽ giúp dashboard và báo cáo đưa ra số liệu hữu ích mà không đánh đổi quá nhiều bộ nhớ hoặc thời gian xử lý.
