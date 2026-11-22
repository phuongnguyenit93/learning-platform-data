# Độ mới, mức phổ biến và khoảng cách trong công thức xếp hạng

Trong một hệ thống tìm kiếm, các document thỏa điều kiện truy vấn chưa chắc đã được sắp xếp theo thứ tự hữu ích nhất cho người dùng. Ngoài mức độ liên quan của nội dung, ứng dụng có thể cần ưu tiên tài liệu mới, sản phẩm phổ biến hoặc địa điểm gần người tìm kiếm.

Elasticsearch cung cấp các cơ chế tính điểm như function_score, decay functions và rank_feature để kết hợp những tín hiệu này với điểm relevance của truy vấn. Spring Data Elasticsearch cho phép gửi các truy vấn đó qua @Query hoặc xây dựng query bằng Elasticsearch Java Client thông qua NativeQuery.

Ba tín hiệu thường gặp:

- **Độ mới (freshness):** tài liệu mới thường được ưu tiên hơn tài liệu cũ.
- **Mức phổ biến (popularity):** nội dung có nhiều lượt xem, tương tác hoặc giao dịch có thể được xếp hạng cao hơn.
- **Khoảng cách (distance):** địa điểm gần vị trí tìm kiếm thường được ưu tiên hơn địa điểm xa.

Không nên dùng các tín hiệu này thay thế điều kiện phù hợp nội dung hoặc điều kiện nghiệp vụ. Trước hết phải xác định document nào được phép xuất hiện; sau đó mới tính điểm để xếp thứ tự các kết quả hợp lệ.

## 1. Tách điều kiện lọc khỏi tín hiệu xếp hạng

Một trang tìm kiếm địa điểm có thể cần:

- Tên địa điểm phải liên quan đến từ khóa.
- Địa điểm phải đang hoạt động.
- Địa điểm phải nằm trong bán kính phục vụ tối đa.
- Địa điểm mới cập nhật được ưu tiên.
- Địa điểm có nhiều đánh giá tốt được ưu tiên.
- Địa điểm gần người tìm kiếm được ưu tiên.

Các điều kiện như trạng thái hoạt động và bán kính tối đa quyết định địa điểm có đủ điều kiện xuất hiện hay không. Độ mới, mức phổ biến và khoảng cách bên trong bán kính thường là tín hiệu xếp hạng.

Có thể mô tả luồng:

~~~text
Yêu cầu tìm kiếm
       |
       v
Query bắt buộc + filter
       |
       v
Tập document đủ điều kiện
       |
       v
Tính các tín hiệu xếp hạng
  - relevance nội dung
  - freshness
  - popularity
  - proximity
       |
       v
Kết hợp điểm và sắp xếp
       |
       v
Kết quả trả về
~~~

Ví dụ, nếu chỉ muốn tìm nhà hàng đang mở trong bán kính 10 km, hãy đặt điều kiện hoạt động và khoảng cách tối đa trong filter. Trong tập kết quả đó, dùng decay theo khoảng cách để ưu tiên nơi gần hơn. Nếu chỉ dùng decay mà không có giới hạn khoảng cách, một địa điểm rất xa vẫn có thể xuất hiện với điểm thấp.

## 2. Điểm relevance cơ bản

Các truy vấn toàn văn như match hoặc multi_match thường tạo ra _score phản ánh mức độ phù hợp giữa nội dung document và truy vấn. Điểm này là nền tảng để xếp hạng:

~~~json
{
  "query": {
    "multi_match": {
      "query": "cà phê rang xay",
      "fields": ["name^3", "description"]
    }
  }
}
~~~

Trong ví dụ, tên địa điểm có trọng số cao hơn mô tả. Elasticsearch tính score dựa trên query và dữ liệu được lập chỉ mục. Score không phải xác suất và không có thang điểm cố định để diễn giải như phần trăm phù hợp.

Nếu chỉ sắp xếp theo relevance, một tài liệu cũ nhưng khớp nhiều từ khóa có thể đứng trên tài liệu mới hơn hoặc phổ biến hơn. Khi nghiệp vụ cần thêm các tín hiệu khác, cần kết hợp chúng với score nền một cách có kiểm soát.

## 3. function_score kết hợp nhiều tín hiệu

function_score cho phép áp dụng một hoặc nhiều hàm tính điểm cho các document đã khớp query. Các hàm có thể sử dụng:

- Giá trị field số thông qua field_value_factor.
- Độ gần theo thời gian hoặc địa lý thông qua decay functions.
- Một trọng số cố định (weight).
- Script score khi công thức cần logic riêng.
- Một số hàm điểm khác như random score trong trường hợp phù hợp.

Khung tổng quát:

~~~json
{
  "query": {
    "function_score": {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "title": "search engine"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "published"
              }
            }
          ]
        }
      },
      "functions": [
        {
          "weight": 2
        },
        {
          "field_value_factor": {
            "field": "viewCount",
            "modifier": "log1p",
            "factor": 0.2,
            "missing": 0
          }
        },
        {
          "gauss": {
            "publishedAt": {
              "origin": "now",
              "scale": "14d",
              "offset": "1d",
              "decay": 0.5
            }
          }
        }
      ],
      "score_mode": "sum",
      "boost_mode": "sum",
      "max_boost": 10
    }
  }
}
~~~

Đây là cấu trúc minh họa: query con xác định document đủ điều kiện và các function bổ sung tín hiệu xếp hạng. Trong thực tế, cần hiệu chỉnh trọng số, scale và giới hạn theo dữ liệu của hệ thống.

## 4. Hai cách kết hợp điểm: score_mode và boost_mode

Hai thuộc tính này giải quyết hai câu hỏi khác nhau.

### 4.1. score_mode: kết hợp nhiều function với nhau

score_mode quy định cách kết hợp kết quả từ các function trong mảng functions.

| Giá trị | Ý nghĩa |
|---|---|
| multiply | Nhân điểm từ các function |
| sum | Cộng điểm từ các function |
| avg | Tính trung bình có xét trọng số |
| first | Dùng function đầu tiên phù hợp |
| max | Lấy điểm function cao nhất |
| min | Lấy điểm function thấp nhất |

Ví dụ, nếu có một function độ mới và một function phổ biến:

- sum cộng đóng góp của hai tín hiệu.
- multiply khiến các tín hiệu tác động theo tích; một tín hiệu nhỏ có thể kéo tổng điểm xuống mạnh.
- max chỉ giữ function tạo ra điểm cao nhất.

Với công thức có nhiều tín hiệu độc lập, sum thường dễ diễn giải hơn khi đã hiệu chỉnh trọng số. multiply có thể phù hợp khi các tín hiệu cần kết hợp theo kiểu tất cả cùng tốt, nhưng cần thử kỹ với các giá trị bằng 0 hoặc rất nhỏ.

### 4.2. boost_mode: kết hợp điểm function với điểm query

boost_mode quy định cách kết hợp điểm tổng hợp từ function với _score của query nền.

| Giá trị | Ý nghĩa |
|---|---|
| multiply | Nhân điểm query với điểm function |
| sum | Cộng điểm query và điểm function |
| avg | Trung bình hai điểm |
| max | Lấy điểm lớn hơn |
| min | Lấy điểm nhỏ hơn |
| replace | Dùng điểm function thay cho điểm query |

Ví dụ, khi dùng boost_mode: sum, query relevance vẫn đóng góp vào điểm cuối cùng, đồng thời freshness, popularity và proximity có thể cộng thêm điểm.

Nếu query nền chỉ có các filter, điểm query có thể bằng 0. Khi đó, boost_mode: multiply có thể khiến điểm cuối bằng 0 dù function có giá trị. Nếu mục tiêu là xếp hạng chỉ bằng function, cân nhắc replace; nếu muốn giữ relevance, hãy có query nền tạo score hoặc chọn cách kết hợp phù hợp.

### 4.3. Giới hạn điểm bằng max_boost

max_boost giới hạn điểm tối đa mà các function đóng góp trước khi kết hợp với điểm query theo boost_mode. Nó hữu ích để một tín hiệu không tăng điểm quá lớn và lấn át relevance.

Đừng chọn max_boost theo cảm tính. Hãy quan sát phân phối score thực tế, thử các truy vấn đại diện và đánh giá xem kết quả có bị chi phối bởi một tín hiệu duy nhất không.

## 5. Độ mới với decay function theo thời gian

Độ mới thường được biểu diễn bằng một field thời gian như publishedAt, createdAt hoặc updatedAt. Một tài liệu mới có thể nhận điểm cao, còn tài liệu càng cũ thì điểm freshness càng giảm.

Elasticsearch cung cấp ba decay function chính:

- gauss: suy giảm theo đường cong Gaussian.
- exp: suy giảm theo hàm mũ.
- linear: suy giảm tuyến tính.

Cả ba có thể dùng cho field date, numeric hoặc geo point phù hợp. Với thời gian, các tham số thường gồm:

- origin: mốc thời gian tham chiếu, ví dụ now.
- scale: khoảng thời gian đặc trưng của độ suy giảm.
- offset: vùng quanh origin chưa bắt đầu suy giảm.
- decay: điểm số mục tiêu tại khoảng cách scale tính từ origin, sau khi tính offset.

### 5.1. Ví dụ freshness với gauss

~~~json
{
  "gauss": {
    "publishedAt": {
      "origin": "now",
      "scale": "14d",
      "offset": "1d",
      "decay": 0.5
    }
  }
}
~~~

Ý nghĩa:

- Mốc tham chiếu là thời điểm hiện tại.
- Trong khoảng một ngày gần nhất, điểm freshness chưa suy giảm do offset.
- Sau vùng offset, điểm giảm dần theo đường cong Gaussian.
- Ở khoảng cách scale tính từ origin, điểm decay đạt mức 0.5 theo định nghĩa của hàm.

Nếu bài viết mới xuất bản cần được ưu tiên trong khoảng hai tuần, có thể bắt đầu thử scale: 14d. Giá trị này chỉ là điểm khởi đầu để thử nghiệm; hệ thống tin tức cập nhật theo phút có thể cần scale ngắn hơn, trong khi tài liệu kiến thức ổn định có thể cần scale dài hơn.

### 5.2. So sánh gauss, exp và linear

| Hàm | Đặc điểm | Khi cân nhắc |
|---|---|---|
| gauss | Suy giảm cong, tương đối mềm quanh origin | Freshness hoặc khoảng cách khi muốn ưu tiên mạnh vùng gần |
| exp | Suy giảm theo hàm mũ | Khi muốn điểm giảm đều theo tỷ lệ theo khoảng cách |
| linear | Giảm tuyến tính về mức decay ở scale | Khi muốn hành vi đơn giản, dễ giải thích |

Ví dụ đổi sang exp:

~~~json
{
  "exp": {
    "publishedAt": {
      "origin": "now",
      "scale": "30d",
      "offset": "2d",
      "decay": 0.5
    }
  }
}
~~~

Ví dụ dùng linear:

~~~json
{
  "linear": {
    "publishedAt": {
      "origin": "now",
      "scale": "30d",
      "offset": "2d",
      "decay": 0.5
    }
  }
}
~~~

Không có một hàm luôn tốt nhất. Hãy chọn theo hành vi xếp hạng mong muốn và đánh giá trên tập truy vấn, document thực tế.

### 5.3. Freshness không giống điều kiện thời hạn

Decay chỉ giảm điểm theo độ cũ. Nó không tự loại tài liệu cũ khỏi kết quả. Nếu nghiệp vụ không cho phép hiển thị bài viết cũ hơn một năm, thêm range filter:

~~~json
{
  "range": {
    "publishedAt": {
      "gte": "now-365d"
    }
  }
}
~~~

Kết hợp range filter và decay giúp phân biệt:

- Filter đặt giới hạn cứng: tài liệu quá cũ không được xuất hiện.
- Decay tạo ưu tiên mềm: trong tập tài liệu hợp lệ, bài mới hơn được xếp cao hơn.

### 5.4. Dữ liệu thời gian cần được chuẩn hóa

Field thời gian nên có mapping date hoặc date_nanos phù hợp và được ghi theo một quy ước nhất quán, thường là thời điểm tuyệt đối UTC. Với kiểu Java, Instant thường biểu diễn rõ một thời điểm trên dòng thời gian.

Nếu dữ liệu nguồn là giờ địa phương, hãy chuyển đổi sang thời điểm có offset hoặc Instant trước khi lưu. Không dùng chuỗi ngày giờ không có múi giờ nếu producer và consumer chưa thống nhất cách diễn giải.

## 6. Mức phổ biến bằng field_value_factor

Mức phổ biến thường dựa trên một field số, ví dụ:

- viewCount: số lượt xem.
- clickCount: số lượt nhấp.
- purchaseCount: số giao dịch.
- favoriteCount: số lượt yêu thích.
- ratingCount hoặc một chỉ số đã tổng hợp từ đánh giá.

field_value_factor đọc giá trị field, nhân với factor rồi áp dụng modifier nếu được khai báo. Kết quả được dùng làm điểm function.

Ví dụ:

~~~json
{
  "field_value_factor": {
    "field": "viewCount",
    "factor": 0.2,
    "modifier": "log1p",
    "missing": 0
  }
}
~~~

Trong đó:

- field: field số dùng làm tín hiệu.
- factor: hệ số nhân với giá trị field trước khi áp dụng modifier.
- modifier: phép biến đổi giá trị, ví dụ log1p, sqrt, log, ln, square hoặc reciprocal.
- missing: giá trị thay thế khi document không có field.

### 6.1. Vì sao thường dùng log1p?

Giá trị phổ biến có thể chênh lệch rất lớn. Một bài viết có 10 lượt xem và bài khác có 100.000 lượt xem không nhất thiết nên tạo ra chênh lệch điểm tuyến tính gấp 10.000 lần.

log1p tính log(1 + x), giúp nén dải giá trị:

| Lượt xem x | log(1 + x), xấp xỉ |
|---:|---:|
| 0 | 0 |
| 9 | 2.30 |
| 99 | 4.61 |
| 999 | 6.91 |
| 9,999 | 9.21 |

Giá trị lớn vẫn có lợi thế, nhưng lợi thế tăng chậm dần. Đây là cách thường dùng để popularity không lấn át hoàn toàn độ liên quan nội dung.

### 6.2. Chọn factor và modifier

Factor điều chỉnh mức đóng góp của popularity. Modifier kiểm soát hình dạng tăng trưởng.

| Modifier | Hành vi |
|---|---|
| none | Giữ giá trị tuyến tính |
| log1p | Nén giá trị lớn, xử lý 0 tốt hơn log thông thường |
| sqrt | Nén nhẹ hơn log ở nhiều miền giá trị |
| square | Làm giá trị lớn tăng nhanh hơn |
| reciprocal | Giá trị lớn tạo điểm nhỏ hơn |

Với lượt xem hoặc số lần tương tác không âm, log1p thường là điểm bắt đầu hợp lý. Cần kiểm tra miền dữ liệu: các modifier log yêu cầu đầu vào hợp lệ; giá trị âm hoặc giá trị bất thường có thể làm truy vấn lỗi hoặc tạo điểm không mong muốn.

### 6.3. Giá trị thiếu và dữ liệu phổ biến

Nếu field không tồn tại, missing có thể cung cấp giá trị thay thế. Ví dụ missing: 0 nghĩa là document chưa có lượt xem nhận popularity bằng 0.

Field nên là kiểu số phù hợp trong mapping. Cần kiểm soát giá trị null, số âm, dữ liệu bị trùng hoặc lượt xem tự động. Nếu một document có lượt xem tăng liên tục, cập nhật counter trực tiếp vào Elasticsearch có thể tạo tải ghi đáng kể; nhiều hệ thống tổng hợp tín hiệu ở tầng ingest hoặc từ nguồn dữ liệu phân tích rồi đồng bộ theo lịch.

### 6.4. Popularity có thể dùng rank_feature

Nếu một field chủ yếu được dùng để xếp hạng và dữ liệu là giá trị dương, mapping rank_feature cùng query rank_feature có thể là lựa chọn chuyên biệt:

~~~json
{
  "mappings": {
    "properties": {
      "popularity": {
        "type": "rank_feature"
      }
    }
  }
}
~~~

Query:

~~~json
{
  "rank_feature": {
    "field": "popularity",
    "saturation": {
      "pivot": 100
    }
  }
}
~~~

Hàm saturation làm điểm tăng nhanh ở giá trị thấp rồi dần bão hòa khi popularity tăng. pivot điều chỉnh vị trí vùng bão hòa. rank_feature được tối ưu cho tín hiệu xếp hạng dạng feature; hãy chọn nó khi cách lưu và truy vấn phù hợp với yêu cầu. Nếu cần lọc, sort, aggregation hoặc xử lý số học tổng quát trên field, kiểu numeric thông thường có thể linh hoạt hơn.

## 7. Khoảng cách địa lý bằng geo decay

Với tìm kiếm địa điểm, khoảng cách từ vị trí gốc là một tín hiệu xếp hạng tự nhiên. Elasticsearch hỗ trợ field geo_point và các decay function trên field này.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "name": "Central Coffee",
  "location": {
    "lat": 10.78,
    "lon": 106.69
  }
}
~~~

### 7.1. Tính điểm theo khoảng cách

Ví dụ decay Gaussian:

~~~json
{
  "gauss": {
    "location": {
      "origin": {
        "lat": 10.78,
        "lon": 106.69
      },
      "scale": "5km",
      "offset": "500m",
      "decay": 0.5
    }
  }
}
~~~

Ý nghĩa:

- origin là tọa độ tham chiếu.
- offset tạo vùng gần origin chưa bị giảm điểm.
- scale xác định khoảng cách đặc trưng của suy giảm.
- decay là điểm tại khoảng cách scale sau khi trừ offset.

Ở đây địa điểm trong phạm vi 500 m được giữ điểm proximity tối đa; ra xa hơn, điểm giảm dần và đạt 0.5 tại khoảng cách scale theo định nghĩa decay.

Với tọa độ dạng chuỗi, Elasticsearch thường nhận thứ tự lat,lon; với object, dùng hai thuộc tính lat và lon. Hãy chú ý thứ tự tọa độ vì đảo latitude và longitude có thể đưa origin đến vị trí hoàn toàn khác.

### 7.2. Giới hạn bán kính bằng geo_distance filter

Geo decay chỉ làm giảm điểm. Nếu cần loại địa điểm ngoài bán kính phục vụ, thêm geo distance filter:

~~~json
{
  "geo_distance": {
    "distance": "10km",
    "location": {
      "lat": 10.78,
      "lon": 106.69
    }
  }
}
~~~

Kết hợp:

- geo_distance filter bảo đảm kết quả nằm trong 10 km.
- gauss decay ưu tiên địa điểm gần hơn trong tập kết quả đó.

Đây là cách tách rõ ràng giữa giới hạn nghiệp vụ và tín hiệu xếp hạng.

### 7.3. Distance sort và distance score

Có hai nhu cầu khác nhau:

- **Sort theo khoảng cách:** xếp chính xác từ gần đến xa, thường dùng sort _geo_distance.
- **Tính điểm theo khoảng cách:** kết hợp độ gần với relevance, freshness hoặc popularity, dùng decay function hoặc distance_feature.

Nếu chỉ sort theo khoảng cách, điểm relevance nội dung có thể không còn quyết định thứ tự. Nếu dùng distance decay, một địa điểm khớp nội dung tốt nhưng xa hơn vẫn có thể xếp trên một địa điểm gần nhưng ít liên quan, tùy công thức tổng hợp.

### 7.4. distance_feature như một lựa chọn khác

Khi chỉ cần tăng điểm theo độ gần của một field date hoặc geo_point, distance_feature query có thể đơn giản và hiệu quả:

~~~json
{
  "distance_feature": {
    "field": "location",
    "origin": "10.78,106.69",
    "pivot": "2km"
  }
}
~~~

Với thời gian:

~~~json
{
  "distance_feature": {
    "field": "publishedAt",
    "origin": "now",
    "pivot": "7d"
  }
}
~~~

 pivot điều chỉnh tốc độ suy giảm điểm theo khoảng cách hoặc thời gian. Có thể đặt distance_feature trong should của bool query để cộng tín hiệu proximity/freshness với query relevance. Dùng function_score khi cần kết hợp nhiều function, trọng số, decay đa dạng hoặc quy tắc score_mode/boost_mode rõ ràng.

## 8. Kết hợp freshness, popularity và proximity

Một công thức xếp hạng tổng hợp có thể gồm:

1. Relevance của nội dung.
2. Freshness theo ngày xuất bản.
3. Popularity theo lượt tương tác.
4. Proximity theo khoảng cách địa lý.

Ví dụ Query DSL:

~~~json
{
  "query": {
    "function_score": {
      "query": {
        "bool": {
          "must": [
            {
              "multi_match": {
                "query": "cà phê rang xay",
                "fields": ["name^3", "description"]
              }
            }
          ],
          "filter": [
            {
              "term": {
                "active": true
              }
            },
            {
              "geo_distance": {
                "distance": "10km",
                "location": {
                  "lat": 10.78,
                  "lon": 106.69
                }
              }
            }
          ]
        }
      },
      "functions": [
        {
          "gauss": {
            "publishedAt": {
              "origin": "now",
              "scale": "14d",
              "offset": "1d",
              "decay": 0.5
            }
          },
          "weight": 2
        },
        {
          "field_value_factor": {
            "field": "viewCount",
            "factor": 0.2,
            "modifier": "log1p",
            "missing": 0
          },
          "weight": 1
        },
        {
          "gauss": {
            "location": {
              "origin": {
                "lat": 10.78,
                "lon": 106.69
              },
              "scale": "5km",
              "offset": "500m",
              "decay": 0.5
            }
          },
          "weight": 2
        }
      ],
      "score_mode": "sum",
      "boost_mode": "sum",
      "max_boost": 10
    }
  }
}
~~~

Trong ví dụ:

- multi_match tạo score relevance nền.
- Filter chỉ giữ địa điểm đang hoạt động và nằm trong bán kính 10 km.
- Function freshness ưu tiên nội dung mới.
- Function popularity tăng điểm theo lượt xem đã được nén bằng log1p.
- Function proximity ưu tiên địa điểm gần origin.
- score_mode: sum cộng các đóng góp function.
- boost_mode: sum cộng điểm function với score relevance.
- max_boost giới hạn tổng đóng góp function.

Các tọa độ và tham số chỉ là dữ liệu ví dụ. Trong ứng dụng thực tế, origin địa lý phải đến từ vị trí tìm kiếm hợp lệ của request hoặc ngữ cảnh nghiệp vụ; không hard-code tọa độ mẫu vào truy vấn production.

## 9. Trọng số và cân bằng các tín hiệu

Các tín hiệu có thang điểm khác nhau. Relevance có thể thay đổi theo độ dài truy vấn và nội dung; popularity có thể từ 0 đến hàng triệu; decay thường nằm trong khoảng từ 0 đến 1. Cộng trực tiếp các giá trị chưa hiệu chỉnh có thể khiến một tín hiệu lấn át các tín hiệu khác.

Một công thức khái niệm:

\[
S = S_{\text{text}} + w_f F + w_p P + w_d D
\]

Trong đó:

- S_text: điểm relevance nội dung.
- F: điểm freshness.
- P: điểm popularity đã chuẩn hóa.
- D: điểm proximity.
- w_f, w_p, w_d: trọng số cho từng tín hiệu.

Đây là mô hình giải thích ý tưởng. Điểm thực tế của function_score còn phụ thuộc score_mode, boost_mode, max_boost và cách mỗi function được đánh giá.

### 9.1. Dùng weight cho từng function

Có thể thêm weight để tăng hoặc giảm ảnh hưởng của một function:

~~~json
{
  "filter": {
    "term": {
      "featured": true
    }
  },
  "weight": 1.5
}
~~~

Function trên chỉ áp dụng cho document có featured=true và đóng góp trọng số 1.5. Filter của function quyết định function có được áp dụng cho document hay không; nó không phải filter loại document khỏi query nền.

Điểm này hữu ích khi một số tín hiệu chỉ có ý nghĩa với một nhóm document. Ví dụ, một ưu đãi chỉ boost sản phẩm thuộc chiến dịch đang hoạt động.

### 9.2. Tránh để popularity lấn át relevance

Nếu chỉ dùng lượt xem, nội dung cũ hoặc nội dung được quảng bá mạnh có thể luôn đứng đầu. Một số cách giảm vấn đề:

- Dùng log1p hoặc saturation để nén giá trị lớn.
- Giới hạn đóng góp bằng weight và max_boost.
- Dùng lượt tương tác trong một cửa sổ thời gian thay vì tổng tích lũy suốt đời.
- Tách tương tác hợp lệ khỏi traffic tự động hoặc spam.
- Giữ query relevance làm điểm nền.
- Đánh giá kết quả trên nhiều truy vấn, không chỉ một truy vấn demo.

Popularity cũng có thể tạo vòng lặp phản hồi: kết quả đã đứng đầu nhận nhiều click hơn, rồi tiếp tục được boost. Nên theo dõi thiên lệch vị trí và cân nhắc dữ liệu tương tác đã hiệu chỉnh.

## 10. Dùng function filter để áp dụng tín hiệu có điều kiện

Mỗi function có thể có filter riêng. Điều này hữu ích khi chỉ một số document nhận được một loại boost.

Ví dụ chỉ boost sản phẩm được đánh dấu featured:

~~~json
{
  "filter": {
    "term": {
      "featured": true
    }
  },
  "weight": 1.5
}
~~~

Một function khác có thể áp dụng cho mọi document:

~~~json
{
  "field_value_factor": {
    "field": "viewCount",
    "modifier": "log1p",
    "missing": 0
  }
}
~~~

Các function được đánh giá theo filter của chính chúng. Nếu filter của function không khớp, function đó không đóng góp cho document. Document vẫn phải thỏa query nền của function_score.

## 11. Tích hợp với Spring Data Elasticsearch

Spring Data Elasticsearch có thể gửi function score query thông qua JSON DSL của @Query hoặc query object được xây dựng từ Elasticsearch Java Client.

### 11.1. Dùng @Query cho công thức cố định

Khi công thức xếp hạng ít thay đổi, @Query giúp giữ DSL gần repository method:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    @Query("""
        {
          "function_score": {
            "query": {
              "bool": {
                "must": [
                  {
                    "match": {
                      "title": "?0"
                    }
                  }
                ],
                "filter": [
                  {
                    "term": {
                      "status": "published"
                    }
                  }
                ]
              }
            },
            "functions": [
              {
                "gauss": {
                  "publishedAt": {
                    "origin": "now",
                    "scale": "14d",
                    "offset": "1d",
                    "decay": 0.5
                  }
                },
                "weight": 2
              },
              {
                "field_value_factor": {
                  "field": "viewCount",
                  "factor": 0.2,
                  "modifier": "log1p",
                  "missing": 0
                }
              }
            ],
            "score_mode": "sum",
            "boost_mode": "sum",
            "max_boost": 10
          }
        }
        """)
    List<Article> searchRanked(String text);
}
~~~

Placeholder ?0 nhận từ khóa tìm kiếm. Các tham số scale, weight và tên field là một phần của công thức cố định. Cần xác nhận cách binding placeholder và khả năng hỗ trợ query của release train Spring Data Elasticsearch trong dự án.

Nếu scale, trọng số, origin hoặc tập filter thay đổi theo request, không nên ghép JSON bằng nối chuỗi. Hãy xây dựng query bằng NativeQuery và Elasticsearch Java Client.

### 11.2. Dùng NativeQuery khi công thức thay đổi theo request

NativeQuery là lớp tích hợp của Spring Data Elasticsearch với Query DSL từ Elasticsearch Java Client. Có thể xây dựng function score query bằng các builder được sinh từ client rồi truyền vào:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(functionScoreQuery)
        .build();

SearchHits<Article> hits =
        operations.search(query, Article.class);
~~~

Ở đây functionScoreQuery là đối tượng Query được tạo bằng builder của Elasticsearch Java Client với function_score, các decay function, field value factor, score mode và boost mode. Tên package, builder và overload cụ thể phụ thuộc phiên bản Elasticsearch Java Client mà Spring Data Elasticsearch đang dùng.

Cách tách này giúp service tính origin và tham số theo request, đồng thời giữ entity mapping do Spring Data quản lý. Không nên tự serialize entity thành JSON bằng Jackson rồi coi đó là query object; query cần tuân theo cấu trúc của Elasticsearch Java Client.

### 11.3. Chọn @Query hay NativeQuery

| Nhu cầu | Cách phù hợp |
|---|---|
| Công thức cố định, chỉ thay từ khóa | @Query |
| Origin thời gian luôn là now, scale cố định | @Query có thể đủ |
| Origin địa lý thay đổi theo vị trí người dùng | NativeQuery |
| Trọng số thay đổi theo loại request | NativeQuery |
| Thêm/bỏ function theo điều kiện | NativeQuery |
| Function score có nhiều nhánh filter | NativeQuery hoặc JSON DSL cố định nếu dễ đọc |

## 12. Mapping entity cho các tín hiệu xếp hạng

Ví dụ các field cần có trong index:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "status": {
        "type": "keyword"
      },
      "publishedAt": {
        "type": "date"
      },
      "viewCount": {
        "type": "long"
      },
      "location": {
        "type": "geo_point"
      },
      "featured": {
        "type": "boolean"
      }
    }
  }
}
~~~

Đối chiếu với Java model:

| Field | Kiểu Java gợi ý | Mapping Elasticsearch |
|---|---|---|
| title | String | text |
| status | String hoặc enum | keyword |
| publishedAt | Instant | date hoặc date_nanos nếu cần |
| viewCount | Long | long |
| location | GeoPoint hoặc kiểu tọa độ phù hợp | geo_point |
| featured | Boolean | boolean |

Annotation Spring Data có thể khai báo kiểu field tương ứng bằng @Field. Với field địa lý, hãy dùng kiểu GeoPoint và cách khai báo được hỗ trợ bởi phiên bản đang dùng. Mapping thực tế trên index vẫn cần được kiểm tra; chỉ khai báo annotation không tự sửa mapping của index đã tồn tại.

## 13. Dữ liệu thiếu và tín hiệu không đáng tin cậy

Một công thức xếp hạng cần định nghĩa cách xử lý khi document không có dữ liệu cho một tín hiệu:

| Tình huống | Cách xử lý cần cân nhắc |
|---|---|
| Không có viewCount | Dùng missing: 0 hoặc giá trị mặc định phù hợp |
| Không có publishedAt | Xác định có loại document, dùng fallback hoặc không áp dụng decay |
| Không có location | Không áp dụng proximity; nếu vị trí là bắt buộc thì loại bằng exists/filter |
| Giá trị popularity âm | Làm sạch dữ liệu hoặc áp dụng quy tắc nghiệp vụ trước khi tính điểm |
| Timestamp tương lai bất thường | Kiểm tra nguồn dữ liệu; không để giá trị lỗi nhận boost quá mức |

Không nên mặc định tất cả document đều có đủ tín hiệu. Nếu một field là điều kiện bắt buộc, hãy dùng exists hoặc validation. Nếu chỉ là tín hiệu phụ, hãy xác định fallback và kiểm tra cách Elasticsearch xử lý field thiếu cho function tương ứng.

## 14. Hiệu chỉnh công thức và đánh giá chất lượng

Một công thức có thể đúng về mặt cú pháp nhưng xếp hạng kém. Cần đánh giá bằng dữ liệu và truy vấn đại diện.

Quy trình hiệu chỉnh:

1. Tạo baseline chỉ dùng relevance.
2. Thêm freshness và quan sát mức thay đổi thứ hạng.
3. Thêm popularity với giá trị đã nén.
4. Thêm proximity nếu sản phẩm có ngữ cảnh địa lý.
5. Thay đổi từng weight hoặc scale một lần để hiểu tác động.
6. So sánh top-k của từng phiên bản công thức.
7. Thu thập đánh giá từ người dùng hoặc nhãn relevance đã có.
8. Theo dõi tỷ lệ click, chuyển đổi, độ đa dạng kết quả và thiên lệch vị trí.

Các metric có thể dùng tùy bài toán gồm Precision@K, Recall@K, NDCG@K và tỷ lệ chuyển đổi. Không nên chỉ tối ưu click nếu click không phản ánh chất lượng cuối cùng.

### 14.1. Dùng Explain để hiểu điểm

Elasticsearch cung cấp Explain API cho một document cụ thể để phân tích vì sao document có score nhất định:

~~~http
GET /articles/_explain/article-100
Content-Type: application/json

{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "title": "search"
        }
      },
      "functions": [
        {
          "field_value_factor": {
            "field": "viewCount",
            "modifier": "log1p",
            "missing": 0
          }
        }
      ],
      "score_mode": "sum",
      "boost_mode": "sum"
    }
  }
}
~~~

Explain giúp xem score nền và phần đóng góp từ function. Nó hữu ích khi một document bất ngờ đứng cao hoặc thấp. Dùng trong quá trình điều tra và phát triển; không nên bật giải thích chi tiết cho mọi request production vì chi phí có thể lớn.

### 14.2. Kiểm thử với thời gian cố định

Query dùng origin: now thay đổi theo thời điểm chạy. Điều này làm test khó tái lập nếu so sánh score chính xác. Trong kiểm thử decay, có thể dùng một origin thời gian cố định, tạo document ở các mốc đã biết rồi xác nhận thứ tự và xu hướng điểm.

Với proximity, dùng tọa độ cố định và document có khoảng cách đã biết. Kiểm tra cả trường hợp nằm trong offset, gần scale, ngoài bán kính filter và thiếu location.

## 15. Các lỗi thường gặp

### 15.1. Dùng decay để thay cho filter giới hạn

Decay chỉ giảm điểm; document xa hoặc cũ vẫn có thể xuất hiện. Nếu có giới hạn cứng, hãy thêm range hoặc geo distance filter.

### 15.2. Để popularity lấn át relevance

Counter lớn có thể tạo điểm cao bất thường. Dùng log1p, saturation, factor, weight và max_boost để kiểm soát.

### 15.3. Nhầm score_mode với boost_mode

score_mode kết hợp các function với nhau. boost_mode kết hợp điểm function với điểm query nền. Chọn nhầm có thể làm kết quả khác đáng kể.

### 15.4. Dùng multiply với function có giá trị 0

Một function bằng 0 có thể kéo tích điểm xuống 0. Hãy kiểm tra miền giá trị, fallback và ý nghĩa nghiệp vụ trước khi chọn multiply.

### 15.5. Dùng query nền chỉ có filter nhưng vẫn boost_mode multiply

Nếu query nền không tạo score, phép nhân có thể khiến kết quả cuối bằng 0. Dùng query có relevance, hoặc chọn boost_mode phù hợp như replace khi function là nguồn điểm chính.

### 15.6. Không xử lý field thiếu

Document không có popularity, timestamp hoặc location có thể nhận điểm khác dự kiến. Hãy định nghĩa fallback và kiểm thử.

### 15.7. Đảo thứ tự latitude và longitude

Chuỗi tọa độ và object tọa độ có quy tắc biểu diễn riêng. Dùng sai thứ tự có thể làm khoảng cách được tính từ vị trí sai.

### 15.8. Cộng các tín hiệu có thang đo khác nhau

Không chuẩn hóa popularity nhưng cộng thẳng vào relevance có thể khiến popularity thống trị. Hãy quan sát phân phối score và hiệu chỉnh từng tín hiệu.

### 15.9. Đánh giá bằng một truy vấn duy nhất

Một công thức có thể tốt cho một từ khóa nhưng tệ với truy vấn khác. Hãy dùng tập truy vấn đại diện và đánh giá top-k.

## 16. Quy trình thiết kế công thức xếp hạng

Khi thêm freshness, popularity hoặc distance vào tìm kiếm:

1. Xác định điều kiện bắt buộc và đặt chúng trong must/filter/must_not.
2. Xác định score relevance nền.
3. Chọn field nguồn cho freshness, popularity và proximity.
4. Kiểm tra mapping và chất lượng dữ liệu của từng field.
5. Chọn decay function và tham số origin, scale, offset, decay.
6. Chọn field_value_factor hoặc rank_feature cho popularity.
7. Quyết định distance là filter cứng, distance sort hay tín hiệu score.
8. Chọn score_mode và boost_mode.
9. Giới hạn đóng góp bằng weight hoặc max_boost nếu cần.
10. Kiểm thử dữ liệu thiếu, giá trị biên và query thực tế.
11. Đánh giá thứ hạng trên nhiều truy vấn và điều chỉnh bằng số liệu.
12. Theo dõi chất lượng sau khi triển khai.

Một số quyết định mẫu:

| Mục tiêu | Cách triển khai |
|---|---|
| Tin mới đứng cao hơn | Date decay trên publishedAt |
| Bài phổ biến được ưu tiên nhưng không lấn át | field_value_factor với log1p hoặc rank_feature |
| Địa điểm gần được ưu tiên | Geo decay trên geo_point |
| Chỉ tìm trong bán kính nhất định | geo_distance filter |
| Giữ relevance và cộng tín hiệu phụ | score_mode: sum, boost_mode: sum sau khi hiệu chỉnh |
| Chỉ xếp hạng theo function | boost_mode: replace, nếu đúng yêu cầu |

## 17. Kết luận

Độ mới, mức phổ biến và khoảng cách là các tín hiệu bổ sung giúp kết quả tìm kiếm gần với nhu cầu thực tế hơn. Date decay ưu tiên tài liệu mới, field value factor hoặc rank_feature thể hiện mức phổ biến, còn geo decay hoặc distance_feature giúp ưu tiên địa điểm gần.

function_score kết hợp nhiều function với nhau bằng score_mode, rồi kết hợp kết quả đó với điểm query bằng boost_mode. Hai tham số có vai trò khác nhau và cần được lựa chọn cùng với weight, scale, offset, decay và max_boost.

Hãy giữ điều kiện đủ tiêu chuẩn trong query/filter, dùng freshness/popularity/proximity để xếp hạng bên trong tập kết quả đó, xử lý rõ dữ liệu thiếu và kiểm tra mapping. Công thức tốt cần được đánh giá trên nhiều truy vấn thực tế, có baseline, Explain và metric top-k; không nên chỉ dựa vào một ví dụ hoặc một bộ trọng số cảm tính.
