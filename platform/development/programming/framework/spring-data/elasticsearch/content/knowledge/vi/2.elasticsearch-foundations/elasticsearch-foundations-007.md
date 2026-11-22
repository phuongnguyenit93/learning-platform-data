# Query context, filter context và điểm liên quan

Khi tìm kiếm trong Elasticsearch, một document có thể được đánh giá theo hai mục đích khác nhau: xác định document có thỏa điều kiện hay không, và xác định document phù hợp với nội dung tìm kiếm đến mức nào. Elasticsearch gọi hai cách đánh giá này là **filter context** và **query context**.

- **Query context** kiểm tra document có khớp với một query hay không, đồng thời tính điểm liên quan (*relevance score*) cho document đó.
- **Filter context** chỉ kiểm tra document có thỏa điều kiện hay không. Elasticsearch không tính điểm liên quan cho điều kiện filter.

Sự khác biệt này ảnh hưởng trực tiếp đến thứ tự kết quả, hiệu năng và cách xây dựng truy vấn. Trong ứng dụng Spring Data Elasticsearch, đây vẫn là ngữ nghĩa của Elasticsearch Query DSL; Spring Data cung cấp API để xây dựng và gửi truy vấn, còn Elasticsearch thực hiện việc lọc và tính điểm.

## 1. Query context: tìm document phù hợp và tính điểm

Query context được dùng khi mục tiêu là tìm những document phù hợp với nội dung người dùng tìm kiếm. Elasticsearch vừa xác định document có khớp query hay không, vừa tính một giá trị _score biểu thị mức độ liên quan.

Ví dụ, người dùng tìm bài viết về spring data:

    GET articles/_search
    {
      "query": {
        "match": {
          "title": "spring data"
        }
      }
    }

Query match phân tích chuỗi đầu vào bằng analyzer của trường title, sau đó tìm các document phù hợp. Những document khớp được trả về cùng _score. Mặc định, kết quả tìm kiếm thường được sắp xếp theo _score giảm dần, nên document được đánh giá liên quan hơn xuất hiện trước.

Một query trong query context trả lời hai câu hỏi:

1. Document có khớp điều kiện tìm kiếm không?
2. Nếu khớp, document liên quan đến truy vấn ở mức nào?

Điểm số có ý nghĩa khi so sánh các document trong cùng kết quả tìm kiếm. Nó không phải xác suất, phần trăm độ chính xác hay một thang điểm cố định có thể so sánh trực tiếp giữa mọi truy vấn.

Query context phù hợp với những điều kiện cần ảnh hưởng đến thứ tự ưu tiên, chẳng hạn:

- Tìm toàn văn theo tiêu đề hoặc nội dung.
- Tìm cụm từ hoặc các từ gần nhau.
- Tìm nhiều trường với trọng số khác nhau.
- Tăng mức ưu tiên cho document có nội dung khớp tốt hơn.

Các query như match, multi_match và match_phrase thường được dùng trong query context để tìm nội dung văn bản. Những query khác cũng có thể được thực thi trong query context; việc tính điểm phụ thuộc loại query và similarity được cấu hình.

## 2. Filter context: chỉ xác định document có thỏa điều kiện

Filter context được dùng khi điều kiện chỉ có ý nghĩa đúng hoặc sai. Elasticsearch xác định document có thỏa điều kiện hay không nhưng không tính điểm liên quan cho điều kiện đó.

Ví dụ, ứng dụng chỉ muốn tìm bài viết đã xuất bản:

    GET articles/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "status": "PUBLISHED"
              }
            }
          ]
        }
      }
    }

Điều kiện status = PUBLISHED là điều kiện lọc. Một bài viết đã xuất bản thỏa điều kiện; bài viết ở trạng thái nháp không thỏa. Không có lý do nghiệp vụ nào để bài viết có trạng thái PUBLISHED được xem là liên quan hơn một bài viết khác cũng có trạng thái đó chỉ vì giá trị trường giống nhau.

Filter context thường phù hợp với:

- Trạng thái: PUBLISHED, DRAFT, ACTIVE.
- Danh mục hoặc mã định danh chính xác.
- Khoảng thời gian, khoảng số.
- Quyền truy cập hoặc phạm vi dữ liệu.
- Các điều kiện bắt buộc khác không cần tham gia xếp hạng.

Các điều kiện filter thường được kết hợp theo logic AND: document phải thỏa tất cả điều kiện trong danh sách filter để được giữ lại.

Filter context có thể giúp tiết kiệm công việc tính điểm và tạo cơ hội sử dụng query cache của Elasticsearch. Tuy nhiên, không nên hiểu rằng mọi filter đều tự động được cache hoặc luôn nhanh hơn mọi query. Query cache hoạt động theo segment và heuristic của Elasticsearch; khả năng cache phụ thuộc loại query, tần suất sử dụng và đặc điểm dữ liệu.

## 3. So sánh query context và filter context

| Tiêu chí | Query context | Filter context |
|---|---|---|
| Mục đích | Tìm nội dung phù hợp và đánh giá mức độ liên quan | Kiểm tra điều kiện đúng/sai |
| Kết quả đánh giá | Khớp hoặc không khớp, kèm điểm _score | Khớp hoặc không khớp |
| Tính điểm liên quan | Có | Không |
| Ảnh hưởng xếp hạng | Có thể làm thay đổi thứ tự theo _score | Không đóng góp điểm liên quan |
| Ví dụ | Tìm tiêu đề chứa spring data | Chỉ lấy bài viết có status = PUBLISHED |
| Vị trí phổ biến trong bool | must, should | filter, must_not |

Hai context không phải hai loại endpoint hoặc hai chế độ kết nối khác nhau. Chúng là hai cách thực thi một query clause tùy theo vị trí và ngữ cảnh mà clause được đặt vào.

## 4. Các clause của bool query

bool query cho phép kết hợp nhiều điều kiện. Bốn clause quan trọng nhất là must, should, filter và must_not.

### must

Các document phải khớp với tất cả query trong must. Mỗi query trong must chạy ở query context và có thể đóng góp vào _score.

Ví dụ:

    {
      "bool": {
        "must": [
          {
            "match": {
              "title": "spring data"
            }
          }
        ]
      }
    }

Document phải phù hợp với nội dung spring data trong trường title. Mức độ phù hợp của query này được tính vào điểm liên quan.

### should

should chứa những query giúp tăng mức độ phù hợp. Khi một query trong should khớp, nó có thể đóng góp thêm điểm vào _score.

    {
      "bool": {
        "must": [
          {
            "match": {
              "title": "spring data"
            }
          }
        ],
        "should": [
          {
            "match": {
              "summary": "spring data"
            }
          }
        ]
      }
    }

Trong ví dụ này, bài viết phải khớp nội dung trong title. Nếu phần summary cũng khớp, bài viết có thể nhận thêm điểm và được xếp cao hơn một bài viết chỉ khớp title.

Có một quy tắc mặc định cần chú ý: nếu bool có should nhưng không có must hoặc filter, mặc định ít nhất một điều kiện should phải khớp. Nếu đã có must hoặc filter, mặc định should trở thành tùy chọn và chỉ đóng góp điểm khi khớp.

Có thể kiểm soát hành vi này bằng minimum_should_match:

- minimum_should_match: 1 yêu cầu ít nhất một query trong should phải khớp.
- minimum_should_match: 2 yêu cầu ít nhất hai query trong should phải khớp.
- minimum_should_match: 0 cho phép tất cả query trong should chỉ đóng vai trò tăng điểm.

Khi nghiệp vụ yêu cầu ít nhất một điều kiện lựa chọn phải đúng, nên khai báo minimum_should_match rõ ràng thay vì phụ thuộc vào giá trị mặc định.

### filter

Các document phải thỏa tất cả query trong filter. Những query này chạy ở filter context, không tính điểm và không đóng góp vào _score.

    {
      "bool": {
        "filter": [
          {
            "term": {
              "status": "PUBLISHED"
            }
          },
          {
            "term": {
              "category": "backend"
            }
          }
        ]
      }
    }

Document phải vừa có trạng thái PUBLISHED, vừa thuộc danh mục backend. Hai điều kiện này thu hẹp tập kết quả nhưng không quyết định bài viết nào liên quan hơn.

### must_not

must_not loại bỏ document khớp với query được chỉ định. Các query trong must_not chạy ở filter context, nên không tính điểm liên quan.

    {
      "bool": {
        "must_not": [
          {
            "term": {
              "status": "DELETED"
            }
          }
        ]
      }
    }

Document có trạng thái DELETED bị loại khỏi kết quả. Điều kiện loại trừ này không làm thay đổi điểm của các document còn lại.

### Nhìn tổng thể

| Clause | Điều kiện đối với document | Context | Đóng góp vào _score_ |
|---|---|---|---|
| must | Phải khớp tất cả query | Query | Có |
| should | Có thể là tùy chọn hoặc bắt buộc theo minimum_should_match | Query | Có |
| filter | Phải khớp tất cả query | Filter | Không |
| must_not | Không được khớp query | Filter | Không |

## 5. Kết hợp tìm kiếm và lọc trong một truy vấn

Trong ứng dụng thực tế, người dùng thường muốn vừa tìm nội dung liên quan, vừa giới hạn kết quả theo trạng thái, danh mục hoặc khoảng giá. Đây là trường hợp nên kết hợp query context và filter context trong cùng một bool query.

Giả sử có index articles với các trường:

| Trường | Kiểu mapping | Ý nghĩa |
|---|---|---|
| title | text | Tiêu đề dùng tìm kiếm toàn văn |
| summary | text | Nội dung tóm tắt |
| status | keyword | Trạng thái bài viết |
| category | keyword | Danh mục |
| price | double | Giá trị số |

Yêu cầu tìm kiếm là:

- Tiêu đề phải phù hợp với từ khóa spring data.
- Bài viết phải ở trạng thái PUBLISHED.
- Bài viết phải thuộc danh mục backend.
- Giá nằm trong khoảng từ 100 đến 1000.
- Nếu phần tóm tắt cũng phù hợp với spring data, tăng mức ưu tiên.

Có thể biểu diễn bằng Elasticsearch Query DSL:

    GET articles/_search
    {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "title": "spring data"
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
                "category": "backend"
              }
            },
            {
              "range": {
                "price": {
                  "gte": 100,
                  "lte": 1000
                }
              }
            }
          ],
          "should": [
            {
              "match": {
                "summary": "spring data"
              }
            }
          ],
          "minimum_should_match": 0
        }
      }
    }

Truy vấn có ba nhóm trách nhiệm:

1. must quyết định bài viết có phù hợp với từ khóa tìm kiếm chính hay không, đồng thời đóng góp điểm liên quan.
2. filter loại các bài viết không đúng trạng thái, danh mục hoặc khoảng giá mà không tính điểm cho các điều kiện này.
3. should tăng điểm cho bài viết có phần tóm tắt phù hợp. minimum_should_match: 0 cho biết điều kiện này không bắt buộc vì truy vấn đã có must và filter.

Kết quả cuối cùng chỉ chứa bài viết thỏa toàn bộ điều kiện bắt buộc. Trong tập kết quả đó, _score phản ánh mức độ phù hợp của các query trong query context.

Nếu nghiệp vụ yêu cầu bài viết phải khớp ít nhất một trong hai trường title hoặc summary, có thể đưa cả hai query vào should, đặt minimum_should_match: 1 và giữ các điều kiện trạng thái, danh mục, khoảng giá trong filter. Khi đó, một trong hai trường phải khớp để document được trả về.

## 6. Điểm liên quan _score được tính như thế nào?

Elasticsearch dùng similarity để tính điểm cho query chạy trong query context. Với các trường văn bản, similarity mặc định thường là **BM25**. BM25 đánh giá mức độ phù hợp dựa trên những tín hiệu như:

- **Term frequency (TF):** một thuật ngữ xuất hiện bao nhiêu lần trong document. Việc xuất hiện nhiều lần có thể làm tăng mức độ phù hợp, nhưng ảnh hưởng được điều chỉnh và không tăng tuyến tính vô hạn.
- **Inverse document frequency (IDF):** thuật ngữ hiếm trong tập document thường mang nhiều thông tin phân biệt hơn thuật ngữ xuất hiện ở hầu hết document.
- **Field length normalization:** độ dài trường được xét đến; một document rất dài không mặc nhiên được ưu tiên chỉ vì chứa nhiều lần thuật ngữ.

Ví dụ, khi tìm từ elasticsearch, một bài viết có nội dung tập trung vào Elasticsearch có thể được đánh giá phù hợp hơn một tài liệu rất dài chỉ nhắc đến từ này một lần. Điểm thực tế còn phụ thuộc analyzer, mapping, similarity, cấu trúc query và dữ liệu được index.

Điểm _score có một số đặc điểm:

1. Đây là giá trị số do Elasticsearch tính để phục vụ xếp hạng kết quả.
2. Giá trị lớn hơn thường biểu thị document phù hợp hơn với query hiện tại.
3. Điểm được tạo bởi nhiều clause trong query context có thể được kết hợp trong bool query.
4. Clause trong filter context không đóng góp điểm.
5. Không nên diễn giải _score = 8 là chính xác 80%, hoặc so sánh điểm của hai truy vấn khác nhau như cùng một thang đo.

Khi một bool query có nhiều clause tính điểm, các đóng góp có thể được cộng lại theo quy tắc của bool query. Vì vậy, thêm một should phù hợp hoặc thay đổi boost có thể làm thay đổi thứ tự kết quả.

### Tăng hoặc cố định điểm

Có thể dùng boost để thay đổi mức ảnh hưởng của một query trong quá trình tính điểm. Ví dụ, tiêu đề có thể được ưu tiên hơn phần tóm tắt:

    {
      "bool": {
        "should": [
          {
            "match": {
              "title": {
                "query": "spring data",
                "boost": 3
              }
            }
          },
          {
            "match": {
              "summary": {
                "query": "spring data",
                "boost": 1
              }
            }
          }
        ],
        "minimum_should_match": 1
      }
    }

Trong ví dụ, kết quả khớp tiêu đề được ưu tiên cao hơn kết quả chỉ khớp phần tóm tắt, theo trọng số đã đặt. boost ảnh hưởng đến phép tính điểm, không biến một query thành filter.

Nếu muốn một điều kiện lọc vẫn có điểm cố định, Elasticsearch cung cấp constant_score:

    {
      "constant_score": {
        "filter": {
          "term": {
            "status": "PUBLISHED"
          }
        },
        "boost": 1.0
      }
    }

Query này chọn các document có trạng thái PUBLISHED bằng filter, rồi gán điểm cố định theo boost cho document khớp. Cách này khác với filter thông thường, vốn không đóng góp điểm. Chỉ nên dùng khi thực sự muốn một điều kiện dạng lọc tham gia xếp hạng với trọng số cố định.

## 7. Sử dụng query context và filter context trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp ElasticsearchOperations để thực hiện truy vấn và ánh xạ kết quả về entity. Với các truy vấn cần kết hợp nhiều clause của Elasticsearch, có thể dùng NativeQuery.

Giả sử ứng dụng có entity:

    @Document(indexName = "articles")
    public class Article {

        @Id
        private String id;

        @Field(type = FieldType.Text)
        private String title;

        @Field(type = FieldType.Text)
        private String summary;

        @Field(type = FieldType.Keyword)
        private String status;

        @Field(type = FieldType.Keyword)
        private String category;

        @Field(type = FieldType.Double)
        private Double price;

        // constructors, getters and setters
    }

Có thể xây dựng truy vấn tìm tiêu đề, đồng thời lọc trạng thái và danh mục:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("title")
                        .query("spring data")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("PUBLISHED"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("backend"))
                    )
                )
            )
        )
        .build();

    SearchHits<Article> hits =
        elasticsearchOperations.search(query, Article.class);

must chứa match query nên chạy trong query context. Hai clause filter kiểm tra trạng thái và danh mục nên chạy trong filter context. Spring Data gửi truy vấn thông qua tầng client và chuyển các document trả về thành Article.

Có thể đọc điểm liên quan từ từng search hit:

    for (SearchHit<Article> hit : hits) {
        Article article = hit.getContent();
        float score = hit.getScore();

        // Use article and score
    }

SearchHit.getScore() cho phép ứng dụng quan sát điểm Elasticsearch trả về. Khi kết quả chỉ được giới hạn bằng filter, điểm không thể hiện mức độ phù hợp giữa các document. Nếu giao diện cần xếp hạng theo nội dung, phải có query chạy trong query context.

Tên API và kiểu builder cụ thể cần theo phiên bản Spring Data Elasticsearch đang dùng. Ví dụ trên minh họa API NativeQuery của các dòng hiện đại sử dụng Elasticsearch Java Client.

## 8. Chọn query hay filter cho từng điều kiện

Một quy tắc thực tế là đặt điều kiện vào query context nếu nó cần ảnh hưởng đến mức độ liên quan; đặt vào filter context nếu nó chỉ quyết định document có được phép xuất hiện trong tập kết quả hay không.

| Điều kiện nghiệp vụ | Cách thể hiện thường dùng | Lý do |
|---|---|---|
| Tiêu đề phải liên quan đến từ khóa | must + match | Cần tính điểm nội dung |
| Nội dung phụ có thể làm kết quả tốt hơn | should + match | Khớp thêm thì tăng điểm |
| Chỉ lấy trạng thái đã xuất bản | filter + term | Điều kiện đúng/sai |
| Chỉ lấy một danh mục | filter + term | Không cần xếp hạng theo danh mục |
| Giá nằm trong khoảng | filter + range | Chỉ giới hạn tập kết quả |
| Loại document đã xóa | must_not + term | Loại document khỏi kết quả |
| Bắt buộc khớp một trong nhiều trường | should + minimum_should_match | Điều khiển số điều kiện phải khớp |

Không phải cứ query term hoặc range là luôn phải đặt trong filter context. Context phụ thuộc vị trí query được sử dụng. Một query clause có thể chạy trong query context hoặc filter context tùy cách nó được lồng vào truy vấn.

### Chú ý về kiểu trường và query

Context không thay thế cho việc chọn đúng mapping và loại query:

- Trường text thường được phân tích token. Dùng match khi muốn tìm theo nội dung đã phân tích.
- Trường keyword giữ giá trị phù hợp cho so khớp chính xác, lọc, nhóm và aggregation. term thường phù hợp với trường này.
- Trường số hoặc ngày tháng có thể dùng range để giới hạn khoảng.
- Không nên dùng term để tìm một cụm từ tự nhiên trên trường text nếu chưa hiểu rõ analyzer và giá trị thực tế được index.

Ví dụ, nếu status được mapping là keyword, filter bằng term với giá trị PUBLISHED phù hợp cho điều kiện trạng thái. Nếu title là text, query match phù hợp hơn cho tìm kiếm toàn văn.

## 9. Các lỗi thiết kế truy vấn thường gặp

### Đưa mọi điều kiện vào must

Nếu đặt cả từ khóa, trạng thái, danh mục và khoảng giá vào must, tất cả điều kiện đều chạy trong query context. Điều kiện trạng thái hoặc danh mục khi đó có thể tham gia tính điểm dù nghiệp vụ không cần điều đó.

Nên chuyển các điều kiện chỉ có ý nghĩa giới hạn tập kết quả sang filter. Giữ những điều kiện tìm kiếm nội dung và xếp hạng trong must hoặc should.

### Đặt điều kiện bắt buộc vào should nhưng quên minimum_should_match

Khi bool đã có must hoặc filter, should mặc định có thể chỉ mang tính tùy chọn. Nếu nghiệp vụ yêu cầu ít nhất một điều kiện should phải khớp, hãy đặt minimum_should_match phù hợp.

### Dùng filter nhưng mong kết quả được xếp hạng theo nội dung

Filter chỉ xác định document có thỏa điều kiện hay không. Nếu toàn bộ truy vấn chỉ có filter, không có tín hiệu liên quan để xếp hạng kết quả theo nội dung. Hãy thêm query phù hợp vào query context nếu cần xếp hạng.

### Nhầm điểm số với phần trăm chính xác

_score là giá trị phục vụ sắp xếp tương đối trong một truy vấn. Nó không biểu thị xác suất document đúng hoặc phần trăm mức độ chính xác. Không nên trình bày trực tiếp _score cho người dùng như một chỉ số chất lượng tuyệt đối nếu chưa có mô hình diễn giải riêng.

### Dùng term trên trường text mà không xét analyzer

term tìm giá trị term chính xác trong inverted index và không phân tích chuỗi đầu vào như match. Trên trường text, dữ liệu đã có thể được phân tích thành token, nên giá trị nguyên chuỗi có thể không khớp như mong đợi. Hãy dùng match cho tìm kiếm toàn văn và term cho trường có mapping phù hợp, thường là keyword.

### Nghĩ rằng filter luôn được cache

Filter context tạo điều kiện để Elasticsearch sử dụng query cache, nhưng không có cam kết rằng mọi filter đều được cache. Không nên thêm hoặc tách filter chỉ với giả định rằng thao tác đó chắc chắn tạo cache hit. Cần dựa trên loại query, dữ liệu, tần suất truy cập và đo đạc thực tế.

## 10. Cách đọc và kiểm tra kết quả

Khi truy vấn trả về kết quả, có thể quan sát _score để hiểu thứ tự xếp hạng:

    GET articles/_search
    {
      "explain": true,
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "title": "spring data"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "PUBLISHED"
              }
            }
          ]
        }
      }
    }

explain: true yêu cầu Elasticsearch cung cấp giải thích chi tiết hơn về cách tính điểm cho từng kết quả. Thông tin này hữu ích khi điều tra vì sao một document được xếp cao hơn document khác, nhưng có thể làm response lớn và tăng chi phí xử lý; chỉ nên bật khi kiểm tra hoặc phân tích truy vấn.

Khi debug, nên kiểm tra theo thứ tự:

1. Document mong muốn có thực sự được index vào đúng index không?
2. Mapping của các trường có đúng với loại query đang dùng không?
3. Query có trả về document khi bỏ bớt từng điều kiện filter không?
4. Các clause must, should, filter và must_not có được đặt đúng theo ý nghĩa nghiệp vụ không?
5. minimum_should_match có khiến điều kiện tùy chọn trở thành bắt buộc hoặc ngược lại không?
6. Nếu document khớp nhưng xếp hạng chưa hợp lý, kiểm tra analyzer, similarity, boost và giải thích điểm bằng explain.

_score chỉ điều khiển thứ tự khi truy vấn được sắp xếp theo điểm liên quan. Nếu ứng dụng khai báo sort theo trường khác, kết quả sẽ được sắp xếp theo trường đó thay vì mặc định theo _score.

## Kết luận

Query context và filter context giải quyết hai mục đích khác nhau trong Elasticsearch. Query context vừa tìm document phù hợp vừa tính điểm liên quan để xếp hạng. Filter context chỉ kiểm tra điều kiện đúng/sai và không đóng góp vào điểm số.

Trong bool query, must và should chạy trong query context; filter và must_not chạy trong filter context. Một truy vấn tìm kiếm thực tế thường kết hợp cả hai: dùng query context cho nội dung người dùng muốn tìm, dùng filter context cho trạng thái, danh mục, thời gian, khoảng số và các điều kiện giới hạn khác.

Với Spring Data Elasticsearch, có thể biểu diễn các clause này qua NativeQuery và thực hiện bằng ElasticsearchOperations. Nắm rõ context của từng clause giúp xây dựng truy vấn đúng ý nghĩa nghiệp vụ, kiểm soát thứ tự kết quả và tránh tính điểm cho những điều kiện vốn chỉ dùng để lọc.
