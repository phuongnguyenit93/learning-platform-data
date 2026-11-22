# Function score để bổ sung tín hiệu nghiệp vụ

Trong tìm kiếm toàn văn, Elasticsearch thường xếp hạng document dựa trên mức độ khớp với nội dung người dùng nhập. Tuy nhiên, kết quả phù hợp về từ khóa chưa chắc đã là kết quả tốt nhất đối với nghiệp vụ. Một cửa hàng có thể muốn ưu tiên sản phẩm đang được bán, sản phẩm phổ biến hoặc sản phẩm mới cập nhật. Một hệ thống tuyển dụng có thể muốn ưu tiên tin còn hạn nộp hồ sơ. Một cổng nội dung có thể muốn kết hợp độ liên quan văn bản với độ mới và mức độ tương tác.

Elasticsearch cung cấp truy vấn function_score để bổ sung các tín hiệu như vậy vào điểm liên quan. Query bên trong vẫn tìm document theo nội dung, còn các function bổ sung điểm hoặc điều chỉnh điểm dựa trên field, điều kiện hoặc công thức. Nhờ đó, ứng dụng có thể kết hợp relevance với tín hiệu nghiệp vụ trong cùng một truy vấn.

Function score hữu ích khi muốn điều chỉnh thứ tự kết quả nhưng vẫn giữ kết quả tìm kiếm dựa trên nội dung. Cần thiết kế cẩn thận để tín hiệu nghiệp vụ hỗ trợ relevance thay vì lấn át nó, và phải phân biệt việc xếp hạng với điều kiện bắt buộc như quyền truy cập, trạng thái được phép hiển thị hoặc tồn tại hàng.

## 1. Vì sao cần bổ sung tín hiệu nghiệp vụ?

Giả sử người dùng tìm wireless keyboard. Elasticsearch có thể tìm thấy ba sản phẩm:

| Sản phẩm | Mức khớp nội dung | Tín hiệu nghiệp vụ |
|---|---|---|
| Keyboard A | Rất cao | Ít lượt xem, hàng tồn thấp |
| Keyboard B | Cao | Phổ biến, còn hàng |
| Keyboard C | Cao | Mới cập nhật, đang được ưu tiên |

Nếu chỉ dựa trên text relevance, Keyboard A có thể đứng đầu vì tên khớp chính xác hơn. Nhưng sản phẩm có thể muốn ưu tiên B hoặc C, miễn là chúng vẫn liên quan đến truy vấn.

Các tín hiệu thường gặp:

- **Popularity:** lượt xem, lượt mua, số lần được lưu hoặc đánh giá.
- **Freshness:** thời điểm xuất bản, cập nhật hoặc thời điểm sự kiện diễn ra.
- **Business priority:** chiến dịch, nhóm sản phẩm ưu tiên hoặc mức độ quan trọng.
- **Inventory:** trạng thái còn hàng hoặc lượng tồn kho.
- **Quality:** điểm đánh giá, độ tin cậy hoặc chất lượng dữ liệu.
- **User context:** khu vực, phân khúc hoặc sở thích đã được phép sử dụng cho xếp hạng.

Không phải tín hiệu nào cũng nên đưa vào score. Điều kiện bắt buộc như sản phẩm bị khóa, hết hạn hoặc người dùng không có quyền xem phải được xử lý bằng filter hoặc authorization trước khi xếp hạng. Function score chỉ nên điều chỉnh thứ tự của những document vốn đã đủ điều kiện xuất hiện.

## 2. Function score là gì?

function_score bao bọc một query cơ sở và một hoặc nhiều scoring function. Query cơ sở xác định document nào khớp; function xác định cách tính thêm hoặc điều chỉnh score cho những document đó.

Ví dụ:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "functions": [
            {
              "field_value_factor": {
                "field": "popularity",
                "factor": 1.2,
                "modifier": "log1p",
                "missing": 0
              }
            }
          ],
          "boost_mode": "multiply"
        }
      }
    }

Trong ví dụ:

1. match tìm sản phẩm liên quan đến wireless keyboard.
2. field_value_factor đọc giá trị popularity của từng document.
3. modifier log1p biến đổi giá trị popularity để hạn chế ảnh hưởng quá lớn của các sản phẩm có số lượt xem rất cao.
4. boost_mode multiply kết hợp function score với score của query cơ sở.

Document không khớp query cơ sở sẽ không được đưa vào kết quả chỉ vì có popularity cao. Function score điều chỉnh điểm của những document được query cơ sở chọn.

## 3. Cấu trúc của function_score

Một function score query thường gồm các phần:

| Thành phần | Vai trò |
|---|---|
| query | Query cơ sở để xác định document và tính relevance ban đầu |
| functions | Danh sách function bổ sung điểm |
| filter trong từng function | Điều kiện quyết định function đó có áp dụng cho document hay không |
| score_mode | Cách kết hợp điểm từ nhiều function đang áp dụng |
| boost_mode | Cách kết hợp function score với score của query cơ sở |
| max_boost | Giới hạn điểm function sau khi các function được kết hợp |
| min_score | Loại kết quả có score cuối thấp hơn ngưỡng |

Có thể hình dung luồng tính điểm:

    Query cơ sở
        |
        v
    Chọn document phù hợp
        |
        v
    Tính score nội dung (query score)
        |
        +---------------------------+
        |                           |
        v                           v
    Function 1                  Function 2
    popularity                  freshness
        |                           |
        +-------------+-------------+
                      |
                      v
               score_mode
                      |
                      v
              function score
                      |
                      v
                max_boost
                      |
                      v
          boost_mode với query score
                      |
                      v
                score cuối
                      |
                      v
              Xếp hạng kết quả

Điểm quan trọng là score_mode và boost_mode giải quyết hai bước khác nhau. score_mode kết hợp các function với nhau; boost_mode kết hợp kết quả function với score của query cơ sở.

## 4. Các function thường dùng

Elasticsearch cung cấp một số scoring function:

| Function | Tín hiệu phù hợp | Cách hoạt động |
|---|---|---|
| weight | Ưu tiên một nhóm document | Nhân điểm function với một trọng số cố định |
| field_value_factor | Popularity, rating, số lượt mua | Dùng giá trị numeric trong field để tạo điểm |
| gauss | Độ mới, khoảng cách hoặc thời gian | Điểm giảm theo đường cong Gaussian khi xa origin |
| exp | Độ mới hoặc khoảng cách | Điểm giảm theo hàm mũ |
| linear | Độ mới hoặc khoảng cách | Điểm giảm tuyến tính |
| random_score | Xáo trộn kết quả có kiểm soát | Tạo điểm ngẫu nhiên, có thể dùng seed |
| script_score | Công thức nghiệp vụ tùy chỉnh | Tính score bằng script |

Có thể dùng nhiều function trong một query. Mỗi function có thể áp dụng cho toàn bộ document khớp hoặc chỉ áp dụng khi filter riêng của function đúng.

Không cần dùng script cho mọi tình huống. Các function chuyên biệt như field_value_factor và decay thường dễ hiểu, dễ tối ưu và an toàn hơn công thức script tự viết.

## 5. Weight function: ưu tiên một nhóm document

weight gán trọng số cố định cho document thỏa filter của function. Ví dụ, muốn ưu tiên sản phẩm thuộc chiến dịch đang chạy:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "functions": [
            {
              "filter": {
                "term": {
                  "campaign": "featured"
                }
              },
              "weight": 2.0
            }
          ],
          "boost_mode": "multiply"
        }
      }
    }

Các document có campaign = featured nhận function weight 2.0. Với boost_mode multiply, score cơ sở của chúng được nhân với function score; các document không khớp filter của function không nhận phần ưu tiên này.

Weight phù hợp với tín hiệu dạng nhóm:

- Sản phẩm đang tham gia chiến dịch.
- Bài viết thuộc chuyên mục cần ưu tiên.
- Tài liệu được xác minh.
- Nhà cung cấp thuộc nhóm ưu tiên.

Trọng số cố định dễ giải thích nhưng cần tránh tạo chênh lệch quá lớn. Nếu weight cao hơn nhiều so với chênh lệch score nội dung, một document chỉ khớp yếu vẫn có thể vượt document liên quan hơn.

### Filter của function khác filter của query cơ sở

Hai vị trí filter có vai trò khác nhau:

- Filter trong bool của query cơ sở giới hạn document được phép xuất hiện.
- Filter trong một function chỉ quyết định function đó có tác động lên document hay không.

Ví dụ sản phẩm hết hàng cần bị loại khỏi kết quả thì đặt status hoặc in_stock trong query filter. Nếu chỉ đặt điều kiện còn hàng trong function filter, sản phẩm hết hàng vẫn có thể xuất hiện, chỉ là không nhận điểm thưởng.

## 6. Field value factor: dùng giá trị số để tính điểm

field_value_factor lấy giá trị numeric của một field trong document để tạo function score. Đây là lựa chọn phổ biến cho popularity, số lượt mua, rating hoặc một tín hiệu số khác.

Ví dụ:

    GET products/_search
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
            "factor": 1.2,
            "modifier": "log1p",
            "missing": 0
          },
          "boost_mode": "sum"
        }
      }
    }

Trong trường hợp này:

- field chỉ định field numeric.
- factor nhân giá trị field trước khi modifier được áp dụng theo công thức của Elasticsearch.
- modifier biến đổi giá trị để điều chỉnh phân phối.
- missing là giá trị thay thế nếu document không có field.

Một số modifier thường gặp:

| Modifier | Ý nghĩa khái quát | Lưu ý |
|---|---|---|
| none | Giữ giá trị sau khi nhân factor | Giá trị lớn có thể chi phối score |
| log | Logarit cơ số 10 | Có thể âm hoặc không hợp lệ nếu đầu vào không phù hợp |
| log1p | Logarit của 1 cộng giá trị | Thường phù hợp với số đếm không âm |
| log2p | Logarit của 2 cộng giá trị | Hạn chế vấn đề ở vùng giá trị nhỏ |
| ln | Logarit tự nhiên | Cần chú ý miền giá trị |
| ln1p | Logarit tự nhiên của 1 cộng giá trị | Thường dùng với số đếm không âm |
| ln2p | Logarit tự nhiên của 2 cộng giá trị | Biến đổi mềm ở vùng giá trị nhỏ |
| sqrt | Căn bậc hai | Giảm tốc độ tăng của giá trị lớn |
| square | Bình phương | Làm giá trị lớn tăng nhanh |
| reciprocal | Nghịch đảo | Giá trị lớn tạo điểm nhỏ hơn |

### Vì sao thường dùng log cho popularity?

Giả sử sản phẩm A có 10 lượt mua, B có 100 lượt mua và C có 100.000 lượt mua. Nếu dùng trực tiếp số lượt mua, C có thể tạo điểm lớn hơn rất nhiều và lấn át mức độ khớp văn bản.

Logarithm nén khoảng cách giữa các giá trị lớn. Nó vẫn thể hiện rằng sản phẩm phổ biến hơn có tín hiệu mạnh hơn, nhưng giảm ảnh hưởng của các giá trị cực lớn.

Với số đếm không âm, log1p hoặc ln1p thường thuận tiện vì có thể xử lý giá trị 0. Dù vậy, vẫn cần kiểm tra dữ liệu thiếu, giá trị âm và kiểu mapping.

### Giới hạn của field_value_factor

- Field phải có giá trị numeric phù hợp.
- Giá trị field cần được kiểm soát để không tạo score âm hoặc không hợp lệ.
- Với field đa trị, field_value_factor sử dụng một giá trị theo quy tắc của Elasticsearch, không tự tổng hợp tất cả phần tử như một phép tính nghiệp vụ tùy ý.
- missing nên được khai báo khi field có thể vắng mặt.
- Nếu dùng field có giá trị rất lớn, hãy chọn modifier hoặc factor để tránh score vượt quá mức mong muốn.

Nếu cần kết hợp nhiều field hoặc công thức phức tạp, có thể dùng nhiều function hoặc script_score; nhưng hãy ưu tiên chuẩn hóa dữ liệu trước khi tăng độ phức tạp query.

## 7. Decay function: giảm điểm theo độ mới hoặc khoảng cách

Decay function giúp document nhận điểm cao khi gần một giá trị tham chiếu (origin) và giảm điểm khi càng xa. Chúng thường được dùng cho:

- Bài viết mới xuất bản.
- Sản phẩm vừa được cập nhật.
- Sự kiện sắp diễn ra.
- Địa điểm gần vị trí tìm kiếm.
- Tài liệu có thời hạn hoặc thời điểm hiệu lực.

Elasticsearch hỗ trợ ba dạng decay phổ biến:

- gauss: giảm theo đường cong Gaussian, mềm ở gần origin.
- exp: giảm theo hàm mũ.
- linear: giảm tuyến tính.

Các tham số thường có:

| Tham số | Vai trò |
|---|---|
| origin | Giá trị tham chiếu, nơi điểm decay đạt 1 |
| scale | Khoảng cách mà tại đó điểm giảm đến mức decay |
| offset | Vùng quanh origin không bị giảm điểm |
| decay | Mức điểm tại khoảng cách scale, thường là giá trị từ 0 đến 1 |

Ví dụ ưu tiên bài viết mới trong 30 ngày:

    GET articles/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "title": "spring data"
            }
          },
          "functions": [
            {
              "gauss": {
                "published_at": {
                  "origin": "2026-11-13T00:00:00Z",
                  "scale": "30d",
                  "offset": "2d",
                  "decay": 0.5
                }
              }
            }
          ],
          "boost_mode": "multiply"
        }
      }
    }

Với cấu hình này:

- Bài viết gần origin nhận điểm decay gần 1.
- Trong vùng offset hai ngày, điểm không giảm.
- Ở khoảng cách scale tính từ ranh giới offset, điểm giảm về mức decay theo hàm đã chọn.
- Bài viết càng xa thời điểm tham chiếu càng nhận điểm thấp hơn.

Giá trị origin trong ví dụ là cố định để minh họa. Trong ứng dụng thực tế, thời điểm tham chiếu thường cần được tạo theo thời gian hiện tại khi request được xử lý hoặc theo mốc nghiệp vụ cụ thể. Tránh lưu ngày hiện tại cố định trong source code.

### Chọn decay theo nghiệp vụ

gauss thường phù hợp khi muốn giảm mềm quanh origin. exp giảm nhanh hơn theo khoảng cách. linear tạo đường giảm đều đến khi chạm vùng giới hạn. Không có dạng nào luôn tốt nhất; hãy thử với các mốc thời gian thực tế và xem thứ tự kết quả.

### Decay cho khoảng cách địa lý

Decay cũng có thể áp dụng cho field geo_point, ví dụ ưu tiên địa điểm gần vị trí người dùng. Khi đó origin là tọa độ và scale/offset dùng đơn vị khoảng cách phù hợp.

Nếu vị trí là điều kiện bắt buộc trong bán kính tìm kiếm, hãy dùng geo filter để giới hạn kết quả; decay chỉ nên quyết định địa điểm gần hơn được xếp hạng cao hơn trong tập đã đủ điều kiện.

## 8. Kết hợp nhiều function

Một truy vấn có thể kết hợp popularity, freshness và campaign priority. Mỗi function có thể có filter riêng:

    GET products/_search
    {
      "query": {
        "function_score": {
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
                    "status": "ACTIVE"
                  }
                },
                {
                  "term": {
                    "in_stock": true
                  }
                }
              ]
            }
          },
          "functions": [
            {
              "field_value_factor": {
                "field": "popularity",
                "modifier": "log1p",
                "missing": 0
              },
              "weight": 1.0
            },
            {
              "filter": {
                "term": {
                  "campaign": "featured"
                }
              },
              "weight": 1.5
            },
            {
              "gauss": {
                "updated_at": {
                  "origin": "2026-11-13T00:00:00Z",
                  "scale": "30d",
                  "decay": 0.5
                }
              }
            }
          ],
          "score_mode": "sum",
          "boost_mode": "sum",
          "max_boost": 8
        }
      }
    }

Query cơ sở chỉ cho phép sản phẩm đang hoạt động và còn hàng. Ba function bổ sung tín hiệu popularity, campaign và freshness.

Trong ví dụ:

- Function popularity dùng giá trị số đã biến đổi bằng log1p.
- Function campaign chỉ áp dụng cho document có campaign = featured.
- Function gauss đánh giá độ mới dựa trên updated_at.
- score_mode sum cộng điểm từ các function đang áp dụng.
- boost_mode sum cộng function score với query score.
- max_boost giới hạn function score trước khi kết hợp với query score.

Đây là ví dụ minh họa cấu trúc. Trọng số và cách kết hợp cần được hiệu chỉnh bằng dữ liệu thực tế. Không nên sao chép các con số 1.5, 8 hoặc scale 30 ngày như giá trị mặc định cho mọi nghiệp vụ.

## 9. score_mode: kết hợp nhiều function với nhau

Khi có nhiều function, score_mode xác định cách kết hợp điểm của những function áp dụng cho document.

| score_mode | Ý nghĩa |
|---|---|
| multiply | Nhân các function score |
| sum | Cộng các function score |
| avg | Lấy trung bình |
| first | Dùng function đầu tiên khớp filter |
| max | Lấy function score lớn nhất |
| min | Lấy function score nhỏ nhất |

Ví dụ:

    "functions": [
      {
        "filter": { "term": { "campaign": "featured" } },
        "weight": 2
      },
      {
        "field_value_factor": {
          "field": "popularity",
          "modifier": "log1p",
          "missing": 0
        }
      }
    ],
    "score_mode": "sum"

Với sum, điểm campaign và popularity được cộng lại. Với multiply, hai function được nhân với nhau; nếu một function bằng 0, tích có thể trở thành 0. Điều này có thể tạo kết quả không mong muốn nếu một tín hiệu có thể vắng mặt hoặc bằng 0.

first hữu ích khi các function được sắp theo thứ tự ưu tiên và filter của chúng loại trừ nhau. Elasticsearch dùng function đầu tiên có filter khớp. Hãy sắp xếp functions có chủ đích nếu dùng mode này.

avg trong function score có tính đến trọng số function theo semantics của Elasticsearch. Khi cần kiểm soát chính xác công thức, hãy đọc tài liệu của phiên bản đang chạy và kiểm tra bằng Explain API.

## 10. boost_mode: kết hợp function score với relevance

Sau khi có function score, boost_mode quyết định cách kết hợp nó với score của query cơ sở.

| boost_mode | Ý nghĩa |
|---|---|
| multiply | Nhân query score với function score |
| sum | Cộng query score và function score |
| avg | Lấy trung bình |
| max | Lấy giá trị lớn hơn |
| min | Lấy giá trị nhỏ hơn |
| replace | Dùng function score thay cho query score |

Ví dụ:

    "boost_mode": "multiply"

Với multiply, document có relevance thấp nhưng function score rất cao vẫn có thể được đẩy lên. Ngược lại, function score thấp có thể kéo giảm document dù nội dung khớp tốt.

Với sum, function score đóng vai trò tín hiệu cộng thêm. Cách này đôi khi dễ kiểm soát hơn nếu score nghiệp vụ đã được chuẩn hóa về một khoảng phù hợp.

Với replace, score nội dung bị thay thế hoàn toàn bởi function score. Chỉ nên dùng khi chủ đích là xếp hạng bằng công thức function, hoặc query cơ sở chỉ đóng vai trò lọc. Nếu muốn giữ relevance văn bản, không nên chọn replace một cách vô tình.

### Phân biệt score_mode và boost_mode

Ví dụ có hai function:

    popularity score = 2
    freshness score = 3

Nếu score_mode = sum, function score là 5. Nếu score_mode = multiply, function score là 6.

Giả sử query score là 4:

- Với function score 5 và boost_mode = sum, score cuối là 9.
- Với function score 5 và boost_mode = multiply, score cuối là 20.
- Với function score 5 và boost_mode = replace, score cuối là 5.

Ví dụ số học này giúp phân biệt hai bước kết hợp; score thực tế còn phụ thuộc cách Elasticsearch tính từng function và giới hạn score.

## 11. max_boost và min_score

### max_boost

max_boost giới hạn điểm function sau khi các function được kết hợp bằng score_mode. Nó giúp tránh một tín hiệu nghiệp vụ có giá trị quá lớn làm score cuối tăng vượt mức dự kiến.

Ví dụ:

    "score_mode": "sum",
    "max_boost": 5,
    "boost_mode": "sum"

Nếu tổng function score vượt 5, phần function score bị giới hạn ở 5 trước khi kết hợp với query score.

max_boost không chuẩn hóa dữ liệu nguồn. Nếu popularity có giá trị bất thường, vẫn nên xử lý ở tầng dữ liệu hoặc chọn modifier phù hợp.

### min_score

min_score loại document có score cuối thấp hơn ngưỡng:

    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "keyboard"
            }
          },
          "min_score": 0.8
        }
      }
    }

Khi dùng min_score, Elasticsearch cần tính score cho các document phù hợp trước khi loại những document dưới ngưỡng. Điều này có thể làm query tốn tài nguyên hơn, đặc biệt với tập kết quả lớn.

Không nên dùng min_score như một cách thay thế filter cho điều kiện bắt buộc. Nếu sản phẩm phải còn hàng, hãy dùng term filter in_stock: true. Score threshold phù hợp hơn với yêu cầu xếp hạng hoặc loại kết quả có mức liên quan quá thấp sau khi đã đánh giá score.

## 12. Script score: công thức nghiệp vụ tùy chỉnh

Khi các function có sẵn không đủ diễn đạt công thức, có thể dùng script_score. Script có thể kết hợp nhiều field, tham số và phép biến đổi.

Ví dụ kết hợp popularity và rating:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "script_score": {
            "script": {
              "source": "Math.log(1 + doc['popularity'].value) + doc['rating'].value",
              "params": {}
            }
          },
          "boost_mode": "replace"
        }
      }
    }

Trong ví dụ này, script tạo score từ popularity và rating, còn replace dùng kết quả script thay cho query score. Nếu muốn giữ relevance, có thể chọn boost_mode khác, chẳng hạn sum hoặc multiply, và điều chỉnh công thức.

### Dùng params thay vì ghép chuỗi script

Nếu công thức có tham số thay đổi theo request, truyền qua params:

    "script": {
      "source": "Math.log(1 + doc['popularity'].value) * params.popularityWeight",
      "params": {
        "popularityWeight": 0.4
      }
    }

Tham số giúp tái sử dụng script đã biên dịch và tránh ghép dữ liệu đầu vào vào chuỗi script. Không đưa nội dung người dùng trực tiếp vào source script.

### Xử lý field thiếu

Trước khi đọc doc['field'].value, cần xác định field có thể thiếu hay không. Có thể dùng kiểm tra kích thước:

    "source": "doc['popularity'].size() == 0 ? 0 : Math.log(1 + doc['popularity'].value)"

Nếu field có thể âm hoặc chứa dữ liệu ngoài miền dự kiến, cần xác thực trước hoặc xử lý rõ trong script. Score cuối phải là giá trị hợp lệ, không âm và không vượt giới hạn số mà Elasticsearch hỗ trợ.

### Chi phí và an toàn của script

Script score linh hoạt nhưng thường tốn chi phí hơn các function chuyên biệt. Script được thực thi trong quá trình tính điểm cho document; với tập ứng viên lớn, chi phí có thể đáng kể.

Nên:

- Dùng field_value_factor hoặc decay nếu đã đủ cho nghiệp vụ.
- Giữ script ngắn và tránh thao tác không cần thiết.
- Dùng params để truyền biến.
- Không cho người dùng gửi script tùy ý.
- Kiểm tra field có tồn tại và có kiểu dữ liệu phù hợp.
- Đo latency và tải trên tập dữ liệu đại diện.

## 13. Random score: xáo trộn kết quả có kiểm soát

random_score tạo điểm ngẫu nhiên cho document. Nó có thể hữu ích khi muốn tránh kết quả luôn xuất hiện theo cùng thứ tự, ví dụ:

- Xáo trộn các sản phẩm có mức liên quan tương đương.
- Chọn mẫu ngẫu nhiên cho một danh sách gợi ý.
- Tạo sự đa dạng trong một số luồng khám phá nội dung.

Ví dụ:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "category": "accessories"
            }
          },
          "random_score": {
            "seed": 42
          },
          "boost_mode": "replace"
        }
      }
    }

Seed giúp tạo kết quả lặp lại trong các điều kiện tương ứng, nhưng tính ổn định còn phụ thuộc cách Elasticsearch tạo random score và field được sử dụng. Nếu cần kết quả ổn định qua nhiều lần phân trang, phải thiết kế seed và field ổn định, đồng thời kiểm tra semantics theo phiên bản.

Không nên dùng random score để thay thế relevance trong tìm kiếm chính. Có thể kết hợp random score với query score bằng boost_mode phù hợp nếu chỉ muốn thêm một mức đa dạng nhỏ.

## 14. Thiết kế tín hiệu popularity

Popularity thường là tín hiệu nghiệp vụ dễ bắt đầu, nhưng số lượt xem thô có thể tạo thiên lệch lớn.

Một quy trình hợp lý:

1. Xác định sự kiện nào được tính là popularity: view, click, add-to-cart hay purchase.
2. Chọn khoảng thời gian: toàn bộ lịch sử, 30 ngày gần nhất hay 7 ngày gần nhất.
3. Chuẩn hóa giá trị để sản phẩm lâu năm không luôn vượt sản phẩm mới.
4. Giới hạn tác động bằng modifier, factor hoặc max_boost.
5. Đảm bảo document thiếu dữ liệu có giá trị mặc định hợp lý.
6. Đánh giá kết quả trên các query đại diện.

Ví dụ mapping:

    {
      "properties": {
        "popularity_30d": {
          "type": "long"
        }
      }
    }

Query:

    {
      "field_value_factor": {
        "field": "popularity_30d",
        "factor": 1.0,
        "modifier": "log1p",
        "missing": 0
      }
    }

Dùng cửa sổ thời gian như 30 ngày có thể giúp tín hiệu phản ánh xu hướng hiện tại hơn. Việc tính popularity nên được xử lý ở pipeline dữ liệu hoặc service ingest; không nên tính lại một phép aggregation đắt tiền trên toàn bộ dữ liệu cho mỗi search request nếu không cần thiết.

## 15. Thiết kế tín hiệu freshness

Freshness thường dùng cho bài viết, sản phẩm mới cập nhật, tin tuyển dụng hoặc sự kiện. Một cách phổ biến là decay trên field date.

Ví dụ:

    {
      "gauss": {
        "published_at": {
          "origin": "now",
          "scale": "14d",
          "offset": "1d",
          "decay": 0.5
        }
      }
    }

Với origin là now, document mới gần thời điểm hiện tại có điểm cao hơn. Scale 14 ngày và decay 0.5 định nghĩa tốc độ giảm. Offset 1 ngày giữ vùng rất mới không bị giảm điểm.

Freshness không nên luôn được áp dụng với trọng số lớn. Trong tìm kiếm tài liệu kỹ thuật, một bài cũ nhưng chính xác có thể hữu ích hơn bài mới nhưng chất lượng thấp. Hãy để text relevance và quality vẫn có vai trò đáng kể.

Nếu truy vấn tìm sự kiện trong một khoảng thời gian, dùng range filter để loại sự kiện đã qua hoặc quá xa. Decay chỉ nên xếp hạng các sự kiện còn hợp lệ theo khoảng cách đến thời điểm mong muốn.

## 16. Tín hiệu nghiệp vụ nên là score hay filter?

Đây là quyết định quan trọng nhất khi thiết kế function score.

| Yêu cầu nghiệp vụ | Cách xử lý thường phù hợp |
|---|---|
| Chỉ hiển thị sản phẩm đang hoạt động | Filter |
| Người dùng chỉ được xem tài liệu thuộc tenant của họ | Authorization/filter bắt buộc |
| Chỉ hiển thị sản phẩm còn hàng | Filter nếu là điều kiện bắt buộc |
| Ưu tiên sản phẩm phổ biến hơn | Function score |
| Ưu tiên bài viết mới hơn nhưng vẫn cho phép bài cũ | Decay function |
| Ưu tiên chiến dịch trong một khoảng thời gian | Filter trong function + weight |
| Chỉ lấy sự kiện trong bán kính nhất định | Geo filter |
| Trong bán kính hợp lệ, ưu tiên địa điểm gần hơn | Geo decay |

Không dùng score để bảo vệ dữ liệu. Một tài liệu không được phép xem phải bị loại bằng cơ chế authorization hoặc filter phù hợp; không thể chỉ cho nó score thấp rồi hy vọng nó không xuất hiện trong trang đầu.

## 17. Function score trong Spring Data Elasticsearch

Spring Data Elasticsearch hiện đại cho phép xây dựng function_score thông qua NativeQuery và builder của Elasticsearch Java API Client.

Ví dụ ưu tiên sản phẩm phổ biến:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .functionScore(fs -> fs
                .query(q2 -> q2
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .functions(fn -> fn
                    .fieldValueFactor(fvf -> fvf
                        .field("popularity")
                        .factor(1.0)
                        .modifier(FieldValueFactorModifier.Log1p)
                        .missing(0.0)
                    )
                )
                .scoreMode(FunctionScoreMode.Sum)
                .boostMode(FunctionBoostMode.Sum)
                .maxBoost(5.0)
            )
        )
        .withPageable(pageable)
        .build();

Query cơ sở là match trên name. Function lấy popularity, dùng log1p và kết hợp với query score bằng sum. maxBoost giới hạn phần function score.

Các kiểu thường cần import từ Elasticsearch Java API Client:

    import co.elastic.clients.elasticsearch._types.query_dsl.FieldValueFactorModifier;
    import co.elastic.clients.elasticsearch._types.query_dsl.FunctionBoostMode;
    import co.elastic.clients.elasticsearch._types.query_dsl.FunctionScoreMode;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Tên enum và overload builder phụ thuộc phiên bản Java API Client do Spring Data sử dụng. Hãy kiểm tra dependency thực tế nếu IDE báo khác chữ ký ví dụ. Tránh dùng NativeSearchQuery và QueryBuilders của các thế hệ Spring Data cũ trong cùng đoạn code với NativeQuery/Java API Client hiện đại.

### Kết hợp function có filter

Ví dụ thêm weight cho chiến dịch:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .functionScore(fs -> fs
                .query(q2 -> q2
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .functions(fn -> fn
                    .filter(f -> f
                        .term(t -> t
                            .field("campaign")
                            .value(FieldValue.of("featured"))
                        )
                    )
                    .weight(1.5)
                )
                .scoreMode(FunctionScoreMode.Sum)
                .boostMode(FunctionBoostMode.Sum)
            )
        )
        .build();

Function chỉ được áp dụng khi campaign là featured. Các document khác vẫn có thể xuất hiện nếu query cơ sở khớp, nhưng không nhận weight của function này.

### Kết hợp nhiều function

Java API Client cho phép thêm nhiều function vào danh sách functions. Có thể xây dựng từng FunctionScore riêng rồi truyền vào builder để code dễ đọc hơn, nhất là khi mỗi function có filter hoặc loại score khác nhau.

Ví dụ cấu trúc khái quát:

    List<FunctionScore> functions = List.of(
        FunctionScore.of(fn -> fn
            .fieldValueFactor(fvf -> fvf
                .field("popularity")
                .modifier(FieldValueFactorModifier.Log1p)
                .missing(0.0)
            )
        ),
        FunctionScore.of(fn -> fn
            .filter(f -> f
                .term(t -> t
                    .field("campaign")
                    .value(FieldValue.of("featured"))
                )
            )
            .weight(1.5)
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .functionScore(fs -> fs
                .query(q2 -> q2
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .functions(functions)
                .scoreMode(FunctionScoreMode.Sum)
                .boostMode(FunctionBoostMode.Sum)
            )
        )
        .build();

Đây là cách tổ chức khi phiên bản Java API Client có overload nhận danh sách FunctionScore. Một số phiên bản cung cấp thêm overload builder lambda cho functions; có thể dùng dạng phù hợp với API đang cài đặt.

## 18. Giữ query cơ sở đủ chọn lọc

Function score thường phải tính điểm cho các document khớp query cơ sở. Nếu query cơ sở quá rộng, nhiều document phải chạy qua scoring functions, làm tăng chi phí.

Ví dụ không tốt:

    {
      "query": {
        "function_score": {
          "query": {
            "match_all": {}
          },
          "field_value_factor": {
            "field": "popularity"
          }
        }
      }
    }

Nếu index chứa hàng chục triệu document, query này có thể buộc Elasticsearch tính score trên một tập ứng viên rất lớn.

Hãy dùng query cơ sở phù hợp:

- Match hoặc multi_match trên nội dung cần tìm.
- Filter theo tenant, trạng thái, loại tài liệu và các điều kiện bắt buộc.
- Range filter theo thời gian hoặc giá trị nếu nghiệp vụ yêu cầu.
- Giữ tập ứng viên đủ rộng để không bỏ sót kết quả tốt, nhưng tránh match_all không cần thiết.

Function score điều chỉnh thứ tự, không thay thế thiết kế query cơ sở.

## 19. Kiểm soát score và tránh tín hiệu lấn át relevance

Score Elasticsearch không phải xác suất. Score có thể thay đổi khi:

- Nội dung index thay đổi.
- Tần suất term hoặc phân phối document thay đổi.
- Analyzer thay đổi.
- Số shard và dữ liệu được phân bố thay đổi.
- Function score, boost hoặc query clause thay đổi.

Do đó, không nên đặt một ngưỡng score tùy ý rồi xem nó như một thước đo chất lượng cố định giữa mọi index hoặc mọi thời điểm.

Một số cách kiểm soát:

1. Dùng modifier để nén các giá trị số có phân phối lệch.
2. Chuẩn hóa tín hiệu ở tầng dữ liệu.
3. Dùng weight nhỏ lúc đầu và tăng dần qua đánh giá.
4. Giới hạn function score bằng max_boost.
5. Chọn boost_mode phù hợp để giữ vai trò của query score.
6. Dùng filter cho điều kiện bắt buộc.
7. Đánh giá thứ tự kết quả bằng tập query thực tế.

Nếu tín hiệu popularity có thang từ 0 đến hàng triệu còn text score thường nhỏ hơn nhiều, dùng sum trực tiếp có thể khiến popularity chi phối. Có thể dùng log1p, scale factor nhỏ hoặc chuẩn hóa trước.

## 20. Explain và profile để hiểu kết quả

Khi một document được xếp hạng cao hoặc thấp bất ngờ, Explain API có thể cho biết các thành phần score:

    GET products/_explain/p-101
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
            "missing": 0
          },
          "boost_mode": "sum"
        }
      }
    }

Explain có thể giúp xác định:

- Query cơ sở đóng góp bao nhiêu điểm.
- Function nào được áp dụng.
- Giá trị field được dùng trong function.
- Cách boost_mode tạo score cuối.

Profile API có thể giúp phân tích thời gian thực thi các thành phần query, nhưng làm tăng chi phí request và tạo response lớn. Dùng chúng trong quá trình điều tra hoặc benchmark, không bật mặc định cho mọi request production.

## 21. Những lưu ý về hiệu năng

Function score có thể làm query tốn kém hơn, đặc biệt khi function được áp dụng trên số lượng lớn document.

Các yếu tố ảnh hưởng:

- Số lượng document khớp query cơ sở.
- Số lượng function trong danh sách.
- Độ phức tạp của script.
- Field có doc values hay không.
- Số lượng field phải đọc để tính score.
- Loại decay và cấu trúc dữ liệu.
- Tần suất request và mức độ đồng thời.

Để kiểm soát:

- Dùng filter để thu hẹp tập ứng viên trước khi tính điểm.
- Ưu tiên function dựng sẵn hơn script khi có thể.
- Không thêm function không ảnh hưởng thực tế đến relevance.
- Chuẩn hóa và lưu trước các tín hiệu tốn kém.
- Benchmark trên dữ liệu và concurrency gần production.
- Theo dõi latency p95/p99, CPU, heap và throughput.

Với tín hiệu số đơn giản, có thể cân nhắc field type rank_feature và query rank_feature thay vì function_score. Đây là cơ chế được thiết kế cho một số tín hiệu xếp hạng và có thể hiệu quả hơn. Lựa chọn phụ thuộc loại tín hiệu, khả năng mapping và phiên bản Elasticsearch.

## 22. Function score so với sort

Sort và function score giải quyết hai bài toán khác nhau:

- **Sort:** sắp xếp theo một hoặc nhiều field theo thứ tự cố định.
- **Function score:** điều chỉnh score để kết hợp relevance với tín hiệu nghiệp vụ.

Ví dụ sort theo popularity:

    "sort": [
      { "popularity": "desc" }
    ]

Kết quả có thể đưa sản phẩm phổ biến nhất lên đầu dù nó khớp từ khóa kém hơn.

Nếu dùng function score, popularity được kết hợp với text relevance. Sản phẩm cần vừa phù hợp với query vừa có tín hiệu nghiệp vụ tốt để đạt điểm cao.

Dùng sort khi thứ tự theo field là yêu cầu cứng, ví dụ mới nhất trước hoặc giá thấp nhất trước. Dùng function score khi cần một thứ tự tổng hợp giữa nhiều tín hiệu. Có thể kết hợp score và sort, nhưng phải hiểu rằng sort theo field có thể ghi đè vai trò xếp hạng của score.

## 23. Kiểm tra relevance trước khi triển khai

Function score là một quyết định sản phẩm, không chỉ là thay đổi cú pháp query. Trước khi triển khai, nên chuẩn bị một tập truy vấn đại diện và xác định thứ tự mong muốn.

Quy trình thực tế:

1. Lưu kết quả baseline chỉ dùng query cơ sở.
2. Chọn một tín hiệu nghiệp vụ và thêm một function.
3. So sánh thứ tự kết quả trước và sau.
4. Kiểm tra các query phổ biến, query ít phổ biến và query không có kết quả tốt.
5. Thử các giá trị weight, factor, modifier hoặc decay khác nhau.
6. Kiểm tra document thiếu field, field bằng 0 và giá trị ngoại lệ.
7. Đo latency và tải khi số lượng ứng viên tăng.
8. Chỉ thêm tín hiệu tiếp theo khi tín hiệu trước đã tạo cải thiện có thể quan sát.

Các chỉ số đánh giá có thể gồm:

- Precision@k: tỷ lệ kết quả liên quan trong top k.
- Recall@k: tỷ lệ tài liệu liên quan được tìm thấy trong top k.
- nDCG@k: đánh giá thứ tự xếp hạng có xét mức độ liên quan.
- MRR: vị trí của kết quả liên quan đầu tiên.
- Tỷ lệ chuyển đổi hoặc chỉ số nghiệp vụ phù hợp với sản phẩm.

Không nên chỉ tối ưu lượt click. Một tín hiệu có thể tăng click ngắn hạn nhưng làm giảm chất lượng, đa dạng hoặc mức độ tin cậy của kết quả.

## 24. Những lỗi thường gặp

### Dùng function score để thay thế điều kiện bắt buộc

Nếu document không được phép xuất hiện, hãy loại bằng authorization hoặc filter. Cho điểm thấp không bảo đảm document sẽ biến mất khỏi kết quả.

### Nhầm filter của function với filter của query

Filter trong function chỉ quyết định function có áp dụng hay không. Nó không loại document khỏi kết quả. Điều kiện bắt buộc phải đặt trong query cơ sở.

### Dùng popularity thô

Giá trị popularity quá lớn có thể lấn át text relevance. Dùng log modifier, factor hoặc chuẩn hóa dữ liệu trước khi tính điểm.

### Chọn boost_mode mà không hiểu score

multiply, sum và replace tạo kết quả rất khác nhau. Hãy xác định function score đang đóng vai trò tín hiệu bổ sung hay thay thế relevance.

### Nhầm score_mode với boost_mode

score_mode kết hợp các function với nhau. boost_mode kết hợp function score với query score. Hai bước này không thể thay thế cho nhau.

### Không khai báo missing

Document thiếu field có thể gây lỗi hoặc không tạo được điểm theo ý muốn. Dùng missing phù hợp và xác định rõ giá trị mặc định của nghiệp vụ.

### Dùng modifier log với giá trị không phù hợp

Giá trị bằng 0 hoặc âm có thể làm log không hợp lệ hoặc tạo score âm. Với số đếm không âm, log1p thường phù hợp hơn; vẫn cần kiểm tra dữ liệu đầu vào.

### Thêm quá nhiều function

Nhiều function làm query khó giải thích và tăng chi phí. Thêm từng tín hiệu, đo kết quả và bỏ những function không cải thiện relevance.

### Dùng script_score cho công thức đơn giản

Nếu field_value_factor hoặc decay đã đáp ứng nhu cầu, dùng script có thể tăng chi phí và độ phức tạp không cần thiết.

### Dùng min_score như filter nghiệp vụ

Score không phải thước đo ổn định giữa mọi truy vấn. Điều kiện trạng thái, tenant, quyền truy cập hoặc tồn kho nên dùng filter tương ứng.

### Dùng sort khi thực sự cần kết hợp relevance

Sort theo popularity hoặc ngày cập nhật có thể đẩy kết quả khớp yếu lên đầu. Nếu cần kết hợp text relevance và tín hiệu nghiệp vụ, hãy cân nhắc function score.

## 25. Quy trình thiết kế function score

Khi thêm tín hiệu nghiệp vụ vào tìm kiếm, có thể thực hiện theo thứ tự:

1. Xác định query cơ sở và bảo đảm nó trả đúng tập document có liên quan.
2. Phân loại từng quy tắc thành điều kiện bắt buộc hay tín hiệu xếp hạng.
3. Với điều kiện bắt buộc, dùng bool filter hoặc authorization.
4. Với tín hiệu numeric đơn giản, thử field_value_factor.
5. Với độ mới hoặc khoảng cách, thử decay function.
6. Với ưu tiên theo nhóm, dùng filter trong function kết hợp weight.
7. Chỉ dùng script_score khi function dựng sẵn không đủ.
8. Chọn score_mode để kết hợp các function.
9. Chọn boost_mode để giữ hoặc thay thế query relevance theo mục tiêu.
10. Giới hạn bằng max_boost nếu cần và thận trọng với min_score.
11. Dùng Explain API để hiểu score khi kết quả bất ngờ.
12. Đánh giá relevance và hiệu năng trên dữ liệu đại diện trước khi phát hành.

## Kết luận

function_score giúp kết hợp text relevance với tín hiệu nghiệp vụ như popularity, freshness, campaign priority hoặc khoảng cách. Query cơ sở xác định document phù hợp; các function bổ sung điểm theo field, điều kiện hoặc công thức. score_mode kết hợp các function với nhau, còn boost_mode kết hợp function score với score của query cơ sở.

Trong Spring Data Elasticsearch, có thể xây dựng function score bằng NativeQuery và Elasticsearch Java API Client builder. Hãy dùng filter cho điều kiện bắt buộc, function score cho tín hiệu xếp hạng, chuẩn hóa giá trị numeric, chọn modifier/decay phù hợp và giữ ảnh hưởng của tín hiệu trong giới hạn. Bắt đầu với một function, đánh giá thứ tự kết quả và latency, sau đó mới thêm tín hiệu khác. Mục tiêu là làm kết quả phù hợp hơn với nhu cầu nghiệp vụ mà vẫn giữ chất lượng tìm kiếm toàn văn.
