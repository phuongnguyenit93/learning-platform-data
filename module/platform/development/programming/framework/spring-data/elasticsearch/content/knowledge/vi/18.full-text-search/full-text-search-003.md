# Multi-match và tìm kiếm trên nhiều trường

Trong tìm kiếm toàn văn, người dùng thường không biết chính xác thông tin cần tìm nằm ở field nào. Một sản phẩm có thể được tìm thấy qua tên, thương hiệu, mô tả hoặc mã phân loại; một bài viết có thể được tìm qua tiêu đề, nội dung hoặc tên tác giả. Nếu chỉ truy vấn một field, ứng dụng có thể bỏ lỡ những document có thông tin phù hợp ở field khác.

Elasticsearch cung cấp truy vấn **multi_match** để tìm cùng một từ khóa trên nhiều field trong một request. Ứng dụng có thể chỉ định danh sách field, đặt trọng số khác nhau cho từng field và chọn cách kết hợp điểm liên quan. Multi-match có nhiều kiểu hoạt động, vì vậy lựa chọn type ảnh hưởng trực tiếp đến cách các từ được phân bố giữa các field và cách document được xếp hạng.

Trong Spring Data Elasticsearch, có thể xây dựng multi-match bằng NativeQuery và biểu thức lambda của Elasticsearch Java API Client. Cách này cho phép kết hợp truy vấn nhiều trường với bool, filter, pagination, sort và các thành phần Query DSL khác.

## 1. Vì sao cần tìm kiếm trên nhiều trường?

Giả sử một index products lưu document:

    {
      "name": "Mechanical Keyboard K8",
      "brand": "Keychron",
      "description": "Wireless mechanical keyboard with compact layout",
      "category": "accessories"
    }

Người dùng có thể nhập:

- mechanical keyboard: thông tin nằm trong name và description.
- Keychron: thông tin nằm trong brand.
- compact layout: thông tin nằm trong description.
- K8: thông tin nằm trong name.

Nếu chỉ dùng match trên name, truy vấn Keychron sẽ không tìm được sản phẩm. Nếu ứng dụng chạy riêng một truy vấn cho từng field, sau đó tự ghép kết quả, code sẽ phức tạp hơn và cần tự giải quyết trùng lặp, phân trang cũng như xếp hạng.

multi_match cho phép khai báo nhiều field trong một query:

    GET products/_search
    {
      "query": {
        "multi_match": {
          "query": "mechanical keyboard",
          "fields": [
            "name",
            "brand",
            "description"
          ]
        }
      }
    }

Elasticsearch tạo các truy vấn tương ứng cho những field được chỉ định rồi kết hợp chúng theo type đã chọn. Kết quả là một tập document duy nhất được xếp hạng theo semantics của multi-match.

## 2. Cấu trúc cơ bản của multi_match

Một multi-match query có các thành phần thường dùng:

| Thành phần | Vai trò |
|---|---|
| query | Văn bản người dùng muốn tìm |
| fields | Danh sách field tham gia tìm kiếm |
| type | Cách kết hợp truy vấn và điểm số giữa các field |
| operator | Cách kết hợp các term được phân tích từ query |
| minimum_should_match | Số lượng hoặc tỷ lệ term cần khớp trong các trường hợp hỗ trợ |
| tie_breaker | Cách cộng thêm điểm từ những field khác ngoài field tốt nhất trong một số type |
| fuzziness | Cho phép khớp gần đúng với một số loại truy vấn |
| analyzer | Analyzer dùng để phân tích query |
| boost | Trọng số field hoặc query để điều chỉnh xếp hạng |

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "wireless keyboard",
          "fields": [
            "name^3",
            "brand^2",
            "description"
          ],
          "type": "best_fields",
          "operator": "and"
        }
      }
    }

Ở ví dụ này:

- name có boost 3 nên mức độ khớp ở tên được ưu tiên.
- brand có boost 2.
- description dùng trọng số mặc định.
- best_fields chọn cách đánh giá theo field khớp tốt nhất, với khả năng cộng thêm điểm qua tie_breaker nếu được cấu hình.
- operator and yêu cầu các term của query khớp theo semantics của từng field query được tạo.

Boost không phải là phần trăm xác suất. Nó là hệ số ảnh hưởng đến score, và tác động thực tế còn phụ thuộc BM25, độ dài field, tần suất term, analyzer và các clause khác.

## 3. Khai báo field và field boost

Danh sách fields xác định nơi Elasticsearch tìm kiếm. Có thể liệt kê field trực tiếp hoặc dùng wildcard có kiểm soát.

Ví dụ:

    "fields": [
      "title",
      "summary",
      "content"
    ]

Nếu một field quan trọng hơn, có thể tăng boost bằng cú pháp field^weight:

    "fields": [
      "title^4",
      "summary^2",
      "content"
    ]

Ví dụ tìm bài viết:

    GET articles/_search
    {
      "query": {
        "multi_match": {
          "query": "spring elasticsearch",
          "fields": [
            "title^4",
            "tags^2",
            "body"
          ]
        }
      }
    }

Document có cụm từ khớp trong title có thể được xếp cao hơn document chỉ khớp trong body. Boost giúp thể hiện mức quan trọng tương đối của field theo mục tiêu sản phẩm.

### Chọn field có chủ đích

Không nên đưa mọi field vào multi-match chỉ vì có thể. Những field như internal_note, raw_payload, debug_message hoặc metadata không phục vụ tìm kiếm người dùng có thể làm kết quả nhiễu và tăng chi phí query.

Hãy chọn field dựa trên:

- Ý nghĩa mà người dùng mong đợi khi nhập từ khóa.
- Kiểu mapping và analyzer của field.
- Độ quan trọng của field trong xếp hạng.
- Kích thước và tần suất xuất hiện của dữ liệu.
- Các field có nội dung trùng lặp hoặc là multi-field của nhau.

Wildcard field expansion có thể tiện, nhưng nếu mapping thay đổi và thêm field mới khớp wildcard, hành vi truy vấn cũng có thể thay đổi. Danh sách field tường minh thường dễ kiểm soát hơn cho API nghiệp vụ quan trọng.

## 4. Các type chính của multi_match

Thuộc tính type quyết định cách multi-match kết hợp truy vấn trên nhiều field. Những type thường gặp gồm:

| Type | Cách hoạt động khái quát | Trường hợp sử dụng |
|---|---|---|
| best_fields | Tạo truy vấn trên từng field và ưu tiên field khớp tốt nhất | Một field thường chứa phần lớn nội dung cần tìm |
| most_fields | Kết hợp điểm từ nhiều field | Cùng nội dung được index ở nhiều dạng hoặc analyzer |
| cross_fields | Xem nhiều field như các phần của cùng một nội dung, theo term | Tên, họ hoặc các field ngắn bổ sung cho nhau |
| phrase | Tìm cụm từ theo thứ tự trong từng field | Cần các từ xuất hiện gần nhau và đúng thứ tự |
| phrase_prefix | Tìm cụm từ, trong đó term cuối được xử lý như tiền tố | Gợi ý cụm từ khi người dùng đang nhập |
| bool_prefix | Dùng match_bool_prefix trên từng field rồi kết hợp | Tìm kiếm dạng search-as-you-type |

Nếu không chỉ định type, multi_match mặc định dùng best_fields. Cần chọn type theo cấu trúc dữ liệu và hành vi mong muốn, không chỉ dựa vào tên gọi.

## 5. best_fields: ưu tiên field khớp tốt nhất

best_fields là type mặc định. Nó chạy một match query trên từng field rồi kết hợp kết quả theo cách tương tự dis_max. Document được đánh giá chủ yếu dựa trên field có score cao nhất.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "wireless keyboard",
          "type": "best_fields",
          "fields": [
            "name^3",
            "description"
          ]
        }
      }
    }

Kiểu này phù hợp khi:

- Một field thường chứa đầy đủ nội dung người dùng cần tìm.
- Khớp tốt trong name quan trọng hơn việc các từ bị chia giữa name và description.
- Muốn field tốt nhất quyết định phần lớn thứ tự kết quả.

### Operator và minimum_should_match trong best_fields

Với best_fields, multi-match tạo match query riêng cho từng field. Vì vậy, operator và minimum_should_match được áp dụng bên trong từng field query.

Giả sử query là:

    "Will Smith"

và fields là first_name, last_name với operator and. Document có first_name = Will và last_name = Smith có thể không khớp best_fields theo cách người dùng kỳ vọng, vì mỗi field query riêng lẻ cần khớp cả hai term. Không field nào chứa đủ cả hai từ.

Đây là khác biệt quan trọng giữa best_fields và cross_fields. Nếu các field là những phần bổ sung của cùng một tên, cross_fields thường phù hợp hơn.

### tie_breaker

best_fields có thể dùng tie_breaker để cộng thêm một phần score từ các field khớp khác ngoài field có score cao nhất.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "wireless keyboard",
          "type": "best_fields",
          "tie_breaker": 0.2,
          "fields": [
            "name^3",
            "description"
          ]
        }
      }
    }

tie_breaker bằng 0.2 cho phép điểm từ những field khớp khác đóng góp một phần vào score cuối. Giá trị này cần được thử nghiệm trên dữ liệu thực tế; không nên mặc định tăng tie_breaker sẽ luôn cải thiện relevance.

## 6. most_fields: kết hợp điểm từ nhiều field

most_fields cũng tạo match query trên từng field, nhưng mục tiêu là cộng điểm từ nhiều field phù hợp. Nó hữu ích khi cùng một nội dung được index nhiều lần với cách phân tích khác nhau.

Ví dụ một title có field gốc và multi-field dùng analyzer khác:

    PUT articles
    {
      "mappings": {
        "properties": {
          "title": {
            "type": "text",
            "analyzer": "standard",
            "fields": {
              "english": {
                "type": "text",
                "analyzer": "english"
              },
              "exact": {
                "type": "text",
                "analyzer": "standard"
              }
            }
          }
        }
      }
    }

Ứng dụng có thể tìm trên nhiều biểu diễn:

    {
      "query": {
        "multi_match": {
          "query": "running shoes",
          "type": "most_fields",
          "fields": [
            "title",
            "title.english",
            "title.exact"
          ]
        }
      }
    }

Mỗi field có thể đóng góp điểm theo cách phân tích riêng. Điều này hữu ích khi muốn kết hợp các cách index như analyzer ngôn ngữ, analyzer chuẩn hóa hoặc một biến thể khác của nội dung.

Không nên dùng most_fields chỉ vì muốn tìm nhiều field thông thường. Nếu các field chứa các phần thông tin độc lập, best_fields hoặc cross_fields có thể thể hiện mục tiêu tốt hơn.

## 7. cross_fields: tìm term trên nhiều field bổ sung nhau

cross_fields là lựa chọn quan trọng khi các field tạo thành một thông tin logic chung. Ví dụ tên người được lưu riêng:

    {
      "first_name": "Will",
      "last_name": "Smith"
    }

Người dùng nhập Will Smith. Cả hai term cần được tìm thấy, nhưng mỗi term nằm ở field khác nhau. Với best_fields và operator and, mỗi field query riêng có thể đòi cả hai term nằm trong cùng field.

cross_fields hoạt động theo hướng term-centric: các term trong query có thể được tìm trên các field được chỉ định như thể chúng thuộc một nội dung logic chung, với điều kiện các field có analyzer tương thích.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "Will Smith",
          "type": "cross_fields",
          "operator": "and",
          "fields": [
            "first_name",
            "last_name"
          ]
        }
      }
    }

Trong trường hợp này, term Will có thể khớp ở first_name và term Smith có thể khớp ở last_name. Cả hai term đều cần xuất hiện trong tập field.

### Giới hạn về analyzer trong cross_fields

cross_fields nhóm các field theo analyzer. Những field có analyzer khác nhau có thể được xử lý thành các nhóm riêng, nên không phải lúc nào cũng được xem như một trường thống nhất.

Vì vậy, khi dùng cross_fields:

- Nên chọn các field có analyzer giống nhau hoặc tương thích.
- Kiểm tra search analyzer của từng field.
- Tránh trộn field có ngôn ngữ hoặc cách chuẩn hóa rất khác nhau trong cùng một nhóm.
- Kiểm tra hành vi với query chứa nhiều term và field bị thiếu dữ liệu.

cross_fields thường phù hợp với các field ngắn, bổ sung cho nhau như first_name và last_name. Nó không tự động giải quyết mọi bài toán tìm kiếm trên nhiều field.

## 8. phrase: tìm cụm từ trên nhiều field

Nếu người dùng cần tìm một cụm từ theo thứ tự, type phrase tạo match_phrase query trên từng field.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "distributed search engine",
          "type": "phrase",
          "fields": [
            "title^3",
            "description"
          ]
        }
      }
    }

Với phrase, các term cần xuất hiện theo thứ tự và gần nhau theo semantics của match_phrase. Có thể cấu hình slop để cho phép một mức khoảng cách hoặc đảo vị trí nhất định.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "distributed search",
          "type": "phrase",
          "slop": 2,
          "fields": [
            "title",
            "body"
          ]
        }
      }
    }

slop cần được lựa chọn dựa trên yêu cầu cụm từ. Giá trị lớn hơn làm query linh hoạt hơn nhưng cũng có thể tạo kết quả ít chính xác hơn.

Phrase search thường tốn kém hơn match thông thường và không phải lựa chọn mặc định cho mọi truy vấn toàn văn.

## 9. phrase_prefix: tiền tố ở cuối cụm từ

phrase_prefix phù hợp khi người dùng đang nhập một cụm từ và term cuối chưa hoàn chỉnh.

Ví dụ query:

    "quick brown fo"

Có thể khớp cụm từ có phần đầu tương ứng và từ cuối bắt đầu bằng fo. Query JSON:

    {
      "query": {
        "multi_match": {
          "query": "quick brown fo",
          "type": "phrase_prefix",
          "fields": [
            "title",
            "description"
          ],
          "max_expansions": 20
        }
      }
    }

max_expansions giới hạn số lượng phần mở rộng của tiền tố cuối. Giá trị quá lớn có thể làm query tốn tài nguyên hơn.

phrase_prefix không tương đương edge n-gram. Nó thực hiện tìm cụm từ với tiền tố cuối ở thời điểm query, trong khi edge n-gram tạo các tiền tố khi index. Hãy đánh giá cả hai theo yêu cầu latency, độ chính xác và kích thước index.

## 10. bool_prefix và search-as-you-type

bool_prefix sử dụng match_bool_prefix trên từng field rồi kết hợp kết quả. Các term trước term cuối được xử lý như term thông thường, còn term cuối được dùng làm tiền tố.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "quick brown fo",
          "type": "bool_prefix",
          "fields": [
            "title",
            "title._2gram",
            "title._3gram"
          ]
        }
      }
    }

Kiểu này thường được dùng với field type search_as_you_type, vốn tạo các sub-field phục vụ tìm kiếm khi người dùng đang nhập.

Ví dụ mapping:

    PUT articles
    {
      "mappings": {
        "properties": {
          "title": {
            "type": "search_as_you_type"
          }
        }
      }
    }

Một query thường gặp:

    GET articles/_search
    {
      "query": {
        "multi_match": {
          "query": "quick brown fo",
          "type": "bool_prefix",
          "fields": [
            "title",
            "title._2gram",
            "title._3gram"
          ]
        }
      }
    }

Các sub-field được Elasticsearch tạo theo cấu hình search_as_you_type. Chúng hỗ trợ tìm kiếm tiền tố và thứ tự term theo các cách khác nhau. Nếu bài toán là autocomplete, hãy cân nhắc search_as_you_type trước khi tự tạo một hệ thống n-gram phức tạp.

## 11. Mapping và analyzer ảnh hưởng đến multi_match

multi_match không bỏ qua mapping. Mỗi field được phân tích theo analyzer tương ứng. Nếu field là text, query text được tách thành token theo search analyzer. Nếu field là keyword, giá trị thường được giữ nguyên như một term.

Ví dụ mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "brand": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          },
          "description": {
            "type": "text",
            "analyzer": "english"
          }
        }
      }
    }

Nếu multi-match tìm đồng thời name, brand, category và description, mỗi field có thể phân tích query theo cách khác nhau. Điều này có thể tạo kết quả không đồng nhất, đặc biệt khi dùng cross_fields.

### Text và keyword

Field text phù hợp cho full-text search vì nội dung được phân tích thành token. Field keyword phù hợp cho so khớp chính xác, filter, sort và aggregation.

Nếu cần tìm tên danh mục như một cụm từ, có thể dùng một field text riêng hoặc multi-field thay vì kỳ vọng match trên keyword sẽ phân tích từ như text.

### Search analyzer

Field có thể khai báo search_analyzer khác analyzer lúc index. Multi-match sử dụng search analyzer thích hợp cho từng field khi tạo query.

Khi các field dùng analyzer khác nhau, đặc biệt với cross_fields, cần kiểm tra các nhóm analyzer và cách query được phân chia. Không nên cho rằng chỉ cần đưa field vào danh sách là tất cả sẽ được xử lý như cùng một văn bản.

### Kiểm tra analyzer bằng Analyze API

Có thể xem cách Elasticsearch phân tích một chuỗi:

    POST products/_analyze
    {
      "field": "name",
      "text": "Mechanical Keyboards"
    }

Thực hiện tương tự với description hoặc field khác để so sánh token. Điều này giúp hiểu tại sao một term khớp ở field này nhưng không khớp ở field khác.

## 12. Sử dụng multi_match trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch hiện đại, có thể tạo NativeQuery bằng builder của Spring Data và lambda của Elasticsearch Java API Client.

Ví dụ service tìm sản phẩm qua tên, thương hiệu và mô tả:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> search(
                String keyword,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .multiMatch(m -> m
                        .query(keyword)
                        .fields(
                            "name^3",
                            "brand^2",
                            "description"
                        )
                        .type(TextQueryType.BestFields)
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Các import liên quan:

    import co.elastic.clients.elasticsearch._types.query_dsl.TextQueryType;
    import org.springframework.data.domain.Pageable;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
    import org.springframework.data.elasticsearch.core.SearchHits;

Trong ví dụ:

- ElasticsearchOperations được inject qua constructor.
- NativeQuery.builder() tạo query của Spring Data.
- withQuery nhận lambda xây dựng Elasticsearch Query.
- multiMatch tạo multi-match query.
- query(keyword) đặt nội dung tìm kiếm.
- fields khai báo các field và boost.
- type(TextQueryType.BestFields) chọn cách kết hợp best_fields.
- withPageable áp dụng phân trang.
- operations.search thực thi và ánh xạ kết quả thành Product.

Tên enum và chữ ký builder cần theo phiên bản Elasticsearch Java API Client được Spring Data quản lý trong dự án. Nếu phiên bản không có overload hoặc enum như ví dụ, hãy kiểm tra dependency tương ứng và dùng kiểu được phiên bản đó cung cấp.

## 13. Kết hợp multi_match với bool và filter

Trong ứng dụng thật, multi-match thường là điều kiện tìm kiếm chính, còn status, category hoặc khoảng thời gian là điều kiện lọc.

Ví dụ:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .multiMatch(mm -> mm
                        .query(keyword)
                        .fields(
                            "name^3",
                            "brand^2",
                            "description"
                        )
                        .type(TextQueryType.BestFields)
                        .operator(Operator.And)
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of(category))
                    )
                )
            )
        )
        .withPageable(pageable)
        .build();

Các import bổ sung:

    import co.elastic.clients.elasticsearch._types.FieldValue;
    import co.elastic.clients.elasticsearch._types.query_dsl.Operator;

Ở đây:

- multi_match trong must quyết định nội dung cần tìm và đóng góp vào score.
- operator AND yêu cầu các term trong query phải khớp theo semantics của type được chọn.
- filter status và category giới hạn tập kết quả nhưng không cộng score.
- Pageable điều khiển phân trang.

Với best_fields, operator được áp dụng trong từng field query. Nếu các từ khóa có thể nằm rải rác ở nhiều field bổ sung nhau, hãy xem xét cross_fields thay vì chỉ đổi operator.

## 14. Ví dụ cross_fields trong Spring Data

Giả sử entity Person có firstName và lastName. Người dùng nhập một tên đầy đủ:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query("Will Smith")
                .fields("firstName", "lastName")
                .type(TextQueryType.CrossFields)
                .operator(Operator.And)
            )
        )
        .build();

Query này thể hiện rằng các term có thể khớp trên các field cùng nhóm analyzer. Nó phù hợp với mô hình các field ngắn bổ sung nhau, miễn là analyzer tương thích.

Nếu firstName và lastName có analyzer khác nhau, kết quả có thể không như kỳ vọng vì cross_fields xử lý các nhóm analyzer riêng. Hãy kiểm tra mapping và analyzer trước khi dùng.

## 15. Ví dụ multi_match với phrase

Nếu tìm kiếm cần cụm từ đúng thứ tự trên nhiều field:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query("distributed search engine")
                .fields("title^3", "body")
                .type(TextQueryType.Phrase)
                .slop(1)
            )
        )
        .build();

Phrase phù hợp khi thứ tự và khoảng cách giữa các term quan trọng. Slop cho phép một mức linh hoạt nhất định. Hãy kiểm tra kết quả trên dữ liệu thực tế vì phrase query thường nghiêm ngặt hơn match query và có thể bỏ lỡ document mà người dùng vẫn mong muốn tìm thấy.

Fuzziness không được hỗ trợ cho các type phrase và phrase_prefix theo cách dùng thông thường của multi_match. Nếu cần fuzzy matching, hãy chọn type phù hợp và kiểm tra giới hạn của Query DSL.

## 16. Operator và minimum_should_match

Một query nhiều từ được analyzer tách thành các term. Operator điều khiển cách các term đó được kết hợp:

- OR: chỉ cần khớp một hoặc nhiều term theo semantics query.
- AND: yêu cầu mọi term trong query khớp.

Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "wireless mechanical keyboard",
          "fields": [
            "name",
            "description"
          ],
          "operator": "and"
        }
      }
    }

minimum_should_match cho phép đặt số lượng hoặc tỷ lệ term tối thiểu cần khớp. Ví dụ:

    {
      "query": {
        "multi_match": {
          "query": "wireless mechanical keyboard",
          "fields": [
            "name",
            "description"
          ],
          "minimum_should_match": "2"
        }
      }
    }

Với best_fields và most_fields, operator và minimum_should_match được áp dụng cho từng field query riêng. Vì thế, chúng không tự động cho phép term đầu nằm ở name và term sau nằm ở description.

Với cross_fields, cách kết hợp theo term phù hợp hơn khi các từ có thể phân bố giữa nhiều field. Tuy nhiên, analyzer grouping vẫn ảnh hưởng cách thực thi.

## 17. Fuzziness và tìm kiếm gần đúng

Fuzziness cho phép một số sai khác ký tự trong term, hữu ích khi người dùng gõ sai chính tả nhẹ:

    {
      "query": {
        "multi_match": {
          "query": "keybord",
          "fields": [
            "name",
            "description"
          ],
          "fuzziness": "AUTO"
        }
      }
    }

Elasticsearch có thể tìm được keyboard dù người dùng nhập keybord, tùy độ dài term và cách cấu hình fuzziness.

Fuzzy query làm tăng chi phí tìm kiếm vì Elasticsearch cần mở rộng term thành các biến thể gần đúng. Không nên bật fuzziness cho mọi field và mọi truy vấn mà không đo hiệu năng.

Một số giới hạn:

- Fuzziness không dùng được với type phrase và phrase_prefix trong multi_match.
- Tiền tố hoặc term quá ngắn có thể không phù hợp với fuzzy matching.
- Fuzzy matching có thể tạo kết quả không mong muốn với mã sản phẩm hoặc chuỗi định danh.
- Cần cân nhắc fuzziness, prefix_length và max_expansions theo yêu cầu.

Với tên sản phẩm hoặc nội dung tự do, fuzzy matching có thể cải thiện trải nghiệm. Với mã SKU, email, số serial hoặc trạng thái, thường nên dùng field và query chính xác hơn.

## 18. Field boost và query boost

Có hai cấp boost cần phân biệt:

- Field boost trong danh sách fields, ví dụ title^4.
- Query boost trên toàn bộ query, nếu builder/API hỗ trợ cấu hình boost cho multi-match.

Field boost thể hiện độ quan trọng tương đối của từng field. Query boost thay đổi trọng số của toàn bộ query so với các clause khác khi kết hợp trong bool query.

Ví dụ một tìm kiếm có:

- multi_match trên name và description.
- filter theo category.
- should query trên brand để tăng điểm.

Có thể dùng field boost để ưu tiên name, và query boost hoặc should để ưu tiên một tín hiệu khác. Tuy nhiên, scoring là tổng hợp từ nhiều yếu tố; boost cần được hiệu chỉnh qua bộ truy vấn đánh giá thay vì chọn theo cảm tính.

## 19. multi_match và nested fields

multi_match có thể tìm trên field lồng bằng tên có dấu chấm nếu field đó được mapping theo object và truy vấn phù hợp. Tuy nhiên, với kiểu mapping nested, chỉ đưa tên field vào danh sách multi_match không tự động tạo nested query.

Ví dụ mapping:

    {
      "properties": {
        "offers": {
          "type": "nested",
          "properties": {
            "seller": {
              "type": "text"
            },
            "description": {
              "type": "text"
            }
          }
        }
      }
    }

Để tìm trong nested object, cần đặt multi_match bên trong nested query:

    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "multi_match": {
              "query": "trusted seller",
              "fields": [
                "offers.seller",
                "offers.description"
              ]
            }
          }
        }
      }
    }

Nested query giữ đúng quan hệ giữa các field trong cùng một nested object. Nếu chỉ query trực tiếp field nested như field thường, Elasticsearch có thể từ chối hoặc không cho kết quả theo ý định.

## 20. Phân trang, sort và kết quả SearchHits

Multi-match chỉ quyết định phần truy vấn và scoring. Một search API thường cần thêm phân trang và có thể cần sort.

Ví dụ:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("_score"))
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query(keyword)
                .fields("title^3", "body")
                .type(TextQueryType.BestFields)
            )
        )
        .withPageable(pageable)
        .build();

    SearchHits<Article> hits =
        operations.search(query, Article.class);

Thông thường, kết quả full-text được xếp theo score giảm dần nếu không có sort khác ghi đè. Nếu sort theo một field như createdAt, kết quả sẽ được ưu tiên theo field đó thay vì chỉ theo relevance.

Nếu cần kết hợp relevance và thời gian, cần thiết kế sort phù hợp và kiểm tra API hỗ trợ sort theo score cùng field. Với phân trang sâu, cân nhắc search_after và một thứ tự sort ổn định thay vì tăng from quá lớn.

SearchHits giữ score và metadata của từng kết quả:

    for (SearchHit<Article> hit : hits) {
        Article article = hit.getContent();
        float score = hit.getScore();
    }

Nếu ứng dụng cần hiển thị vì sao kết quả được ưu tiên, có thể xem xét Explain API hoặc profile query trong môi trường phân tích. Không nên dùng explain cho mọi request production vì chi phí có thể cao.

## 21. Multi-match so với các phương án khác

Không phải mọi bài toán tìm nhiều field đều cần multi_match.

| Phương án | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Multi-match | Cùng query được tìm trên nhiều field, cần chọn cách kết hợp score | Phải hiểu type và analyzer |
| Bool với nhiều match | Mỗi field có điều kiện hoặc trọng số riêng | Query dài hơn nhưng kiểm soát rõ |
| copy_to | Muốn gom nội dung nhiều field vào một field tìm kiếm tổng hợp | Cần thiết kế mapping và index lại dữ liệu khi thay đổi |
| Combined fields query | Muốn tìm theo term trên nhiều field như một trường logic, với scoring theo cách riêng | Cần kiểm tra field và analyzer tương thích |
| search_as_you_type | Autocomplete trên nội dung dạng cụm từ | Tăng cấu trúc index và cần query phù hợp |
| Completion suggester | Gợi ý từ danh sách được chuẩn bị trước | Không thay thế full-text search tổng quát |

### Multi-match và copy_to

copy_to cho phép copy nội dung từ nhiều field vào một field đích khi index document. Sau đó ứng dụng chỉ cần query field đích.

Ví dụ:

    {
      "properties": {
        "name": {
          "type": "text",
          "copy_to": "search_text"
        },
        "brand": {
          "type": "text",
          "copy_to": "search_text"
        },
        "description": {
          "type": "text",
          "copy_to": "search_text"
        },
        "search_text": {
          "type": "text"
        }
      }
    }

Cách này tiện khi các field cùng phục vụ một nội dung tìm kiếm tổng hợp. Nhưng nó làm mất một phần khả năng điều chỉnh boost theo từng field trong query và cần thiết kế field đích rõ ràng.

### Multi-match và combined_fields

Elasticsearch có combined_fields query cho bài toán term-centric trên nhiều field tương thích. Nó có thể là lựa chọn phù hợp khi muốn xử lý các field như một trường logic chung, với scoring theo cơ chế combined fields. Khả năng và giới hạn phụ thuộc phiên bản Elasticsearch.

cross_fields của multi_match cũng phục vụ bài toán term-centric nhưng có semantics riêng, bao gồm nhóm field theo analyzer. Khi cần kiểm soát chính xác scoring giữa nhiều field, hãy so sánh multi_match cross_fields và combined_fields bằng bộ truy vấn đại diện.

## 22. Kiểm tra truy vấn và relevance

Một multi-match query có thể hợp lệ về cú pháp nhưng kết quả không phù hợp với người dùng. Cần đánh giá relevance bằng các truy vấn thực tế.

Một quy trình kiểm tra:

1. Chuẩn bị tập query đại diện cho cách người dùng tìm kiếm.
2. Với mỗi query, ghi lại các document được mong đợi xuất hiện.
3. Chạy query trên từng type như best_fields, most_fields hoặc cross_fields.
4. Thử các mức boost khác nhau cho field quan trọng.
5. So sánh thứ tự kết quả và số lượng kết quả liên quan.
6. Kiểm tra các trường hợp thiếu field, từ đồng nghĩa, lỗi chính tả và nhiều analyzer.
7. Theo dõi latency và chi phí query khi số field tăng.

Các chỉ số đánh giá có thể gồm precision@k, recall@k, mean reciprocal rank hoặc nDCG nếu có nhãn relevance. Với ứng dụng nhỏ, một tập truy vấn được đánh giá thủ công cũng hữu ích hơn việc chỉ thử vài ví dụ ngẫu nhiên.

### Dùng Explain API

Khi một document có score bất ngờ, Explain API giúp xem các thành phần đóng góp vào score:

    GET products/_explain/p-101
    {
      "query": {
        "multi_match": {
          "query": "mechanical keyboard",
          "fields": [
            "name^3",
            "description"
          ],
          "type": "best_fields"
        }
      }
    }

Explain có thể giúp xác định field nào đóng góp điểm và term nào khớp. Chỉ nên dùng trong quá trình phân tích vì response có thể lớn và thao tác tốn tài nguyên hơn search thông thường.

## 23. Những lỗi thường gặp

### Dùng best_fields cho các field bổ sung nhau

Nếu một cụm từ được chia giữa first_name và last_name, best_fields với operator AND có thể không khớp vì mỗi field query riêng phải chứa đủ term. Hãy xem xét cross_fields.

### Nghĩ rằng operator AND áp dụng trên toàn bộ danh sách field

Với best_fields và most_fields, operator được áp dụng bên trong từng field query. Nó không tự động kết hợp term trên nhiều field. cross_fields có semantics term-centric hơn.

### Dùng cross_fields với analyzer không tương thích

cross_fields nhóm field theo analyzer. Nếu field có analyzer khác nhau, chúng có thể không được kết hợp như một trường thống nhất. Kiểm tra mapping và Analyze API.

### Boost field quá cao

Boost quá lớn có thể làm một field chi phối gần như toàn bộ thứ tự kết quả. Hãy thử nghiệm trên tập truy vấn có nhãn relevance.

### Đưa field keyword vào full-text query mà không xem xét mapping

Field keyword không được phân tích như text. Nếu cần tìm theo từng từ, dùng field text hoặc multi-field phù hợp.

### Dùng fuzziness cho mọi truy vấn

Fuzzy matching có chi phí và không phù hợp với mọi type hoặc mọi loại dữ liệu. Không dùng cho mã định danh nếu yêu cầu là khớp chính xác.

### Dùng phrase khi chỉ cần tìm các từ độc lập

Phrase query yêu cầu thứ tự và khoảng cách giữa các term, có thể bỏ lỡ kết quả mà match thông thường tìm được. Chỉ dùng khi thứ tự cụm từ là một phần yêu cầu.

### Nhầm phrase_prefix với edge n-gram

phrase_prefix mở rộng term cuối ở thời điểm query. Edge n-gram tạo tiền tố khi index. Chúng có chi phí và hành vi khác nhau.

### Bỏ qua nested mapping

Field nằm trong nested object cần nested query. Multi-match không tự tạo nested context chỉ vì field name có dấu chấm.

### Dùng wildcard fields không kiểm soát

Wildcard có thể vô tình bao gồm field mới hoặc field không liên quan sau khi mapping thay đổi. Hãy giới hạn danh sách field hoặc kiểm tra kết quả expansion.

## 24. Quy trình chọn type cho multi_match

Trước khi viết query, hãy trả lời các câu hỏi:

1. Các field là những nơi độc lập có thể chứa toàn bộ nội dung, hay là các phần bổ sung nhau?
2. Một field tốt nhất có nên quyết định phần lớn score không?
3. Nhiều field có chứa cùng nội dung được index bằng analyzer khác nhau không?
4. Người dùng cần tìm từ riêng lẻ hay một cụm từ đúng thứ tự?
5. Người dùng đang nhập một phần của cụm từ hay cần fuzzy matching?
6. Các field có cùng analyzer và mapping tương thích không?
7. Field nào quan trọng hơn và cần boost?

Gợi ý lựa chọn:

- Chọn best_fields khi một field thường chứa phần lớn nội dung khớp.
- Chọn most_fields khi cùng nội dung được index ở nhiều dạng và muốn kết hợp điểm.
- Chọn cross_fields khi term có thể nằm ở các field bổ sung nhau như first_name và last_name.
- Chọn phrase khi thứ tự cụm từ quan trọng.
- Chọn phrase_prefix hoặc bool_prefix khi cần tìm kiếm cụm từ đang được nhập.

Sau khi chọn type, kiểm tra operator, minimum_should_match, tie_breaker, boost và analyzer. Những tham số này có thể thay đổi đáng kể kết quả ngay cả khi danh sách field không đổi.

## Kết luận

multi_match cho phép tìm cùng một query trên nhiều field và kết hợp kết quả theo một type cụ thể. best_fields ưu tiên field khớp tốt nhất; most_fields kết hợp điểm từ nhiều biểu diễn; cross_fields phù hợp với các field bổ sung nhau theo từng term; phrase, phrase_prefix và bool_prefix phục vụ các kiểu tìm kiếm cụm từ và search-as-you-type.

Trong Spring Data Elasticsearch, NativeQuery.builder() kết hợp với multiMatch lambda là cách tự nhiên để xây dựng truy vấn nhiều trường. Hãy chọn field theo mapping và nhu cầu người dùng, dùng boost có chủ đích, hiểu operator/minimum_should_match theo từng type, và kiểm tra analyzer tương thích. Sau cùng, đánh giá relevance bằng truy vấn đại diện và theo dõi latency thay vì coi một query hợp lệ về cú pháp là đã cho kết quả tốt.
