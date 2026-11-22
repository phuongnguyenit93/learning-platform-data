# Edge n-gram, n-gram và chi phí kích thước chỉ mục

Khi xây dựng chức năng tìm kiếm gợi ý hoặc tìm kiếm ngay khi người dùng đang nhập, ứng dụng thường cần tìm được một document dù người dùng mới nhập một phần của từ. Elasticsearch có thể hỗ trợ yêu cầu này bằng cách tạo thêm các token ngắn từ token gốc khi index dữ liệu. Hai kỹ thuật phổ biến là **edge n-gram** và **n-gram**.

- **Edge n-gram** tạo các chuỗi con bắt đầu từ đầu token. Nó phù hợp với tìm kiếm tiền tố (*prefix search*), chẳng hạn người dùng nhập elas để tìm elasticsearch.
- **N-gram** tạo các chuỗi con liên tiếp ở nhiều vị trí trong token. Nó có thể tìm được một phần nằm giữa từ, chẳng hạn search trong elasticsearch, nhưng thường tạo nhiều token hơn.

Việc tạo thêm token giúp tìm kiếm linh hoạt hơn nhưng làm tăng lượng term và posting cần lưu trong inverted index. Vì vậy, lựa chọn giữa edge n-gram và n-gram cần dựa trên hành vi tìm kiếm thực tế, độ dài từ, khoảng gram, dung lượng lưu trữ và chi phí indexing.

## 1. N-gram là gì?

N-gram là một chuỗi gồm n đơn vị liên tiếp. Trong tìm kiếm văn bản, đơn vị thường là ký tự. Ví dụ, với token spring:

- 1-gram: s, p, r, i, n, g.
- 2-gram: sp, pr, ri, in, ng.
- 3-gram: spr, pri, rin, ing.

Nếu cấu hình một khoảng từ min_gram đến max_gram, bộ tạo gram sẽ sinh các chuỗi có độ dài trong khoảng đó. Với min_gram = 2 và max_gram = 3, token spring tạo ra:

    2-gram: sp, pr, ri, in, ng
    3-gram: spr, pri, rin, ing

N-gram giữ lại các đoạn ký tự liên tiếp ở mọi vị trí trong token. Vì thế, một truy vấn có thể khớp với đoạn nằm ở đầu, giữa hoặc cuối token nếu đoạn đó đã được index.

N-gram không hiểu ý nghĩa ngôn ngữ của từ. Nó chỉ tạo các đoạn ký tự theo cấu hình. Các gram có thể là một phần của từ mà không phải từ độc lập, nên kết quả phù hợp về mặt ký tự chưa chắc đã phù hợp về mặt ngữ nghĩa.

## 2. Edge n-gram là gì?

Edge n-gram cũng tạo các chuỗi con, nhưng chỉ bắt đầu từ ký tự đầu tiên của token. Với token spring, min_gram = 2 và max_gram = 5, kết quả là:

    sp
    spr
    spri
    sprin

Các chuỗi này đều là tiền tố của spring. Edge n-gram không tạo pr, rin hoặc ing, vì chúng không bắt đầu ở đầu token.

Đây là đặc điểm làm edge n-gram phù hợp với autocomplete theo tiền tố. Khi người dùng lần lượt nhập s, sp, spr hoặc spri, mỗi chuỗi có thể khớp với một token đã được tạo khi index document.

Ví dụ với tên sản phẩm Spring Data Elasticsearch:

| Token gốc | Edge n-gram với min=2, max=5 |
|---|---|
| spring | sp, spr, spri, sprin |
| data | da, dat, data |
| elasticsearch | el, ela, elas, elast |

Người dùng nhập elas có thể tìm được document có token elasticsearch. Người dùng nhập search thì không khớp qua edge n-gram của token đó, vì search nằm giữa token chứ không phải tiền tố.

## 3. N-gram và edge n-gram khác nhau như thế nào?

Giả sử token gốc là spring, cấu hình min_gram = 2, max_gram = 3.

| Kỹ thuật | Các gram được tạo |
|---|---|
| Edge n-gram | sp, spr |
| N-gram | sp, pr, ri, in, ng, spr, pri, rin, ing |

Edge n-gram chỉ tạo chuỗi bắt đầu từ đầu token. N-gram tạo chuỗi ở tất cả vị trí có thể.

| Tiêu chí | Edge n-gram | N-gram |
|---|---|---|
| Vị trí bắt đầu | Chỉ ở đầu token | Ở mọi vị trí trong token |
| Kiểu tìm kiếm phù hợp | Tiền tố, autocomplete | Đoạn con ở bất kỳ vị trí nào |
| Số token tạo ra | Thường ít hơn | Thường nhiều hơn |
| Kích thước index | Thường thấp hơn với cùng khoảng gram | Thường cao hơn |
| Ví dụ | Nhập spr tìm spring | Nhập rin tìm spring |
| Trường hợp dùng | Gợi ý tên, sản phẩm, địa điểm theo tiền tố | Tìm chuỗi con, mã hoặc đoạn ký tự nằm giữa token |

Nếu yêu cầu chỉ là gợi ý khi người dùng nhập từ đầu, edge n-gram thường là lựa chọn hợp lý hơn. Nếu yêu cầu cần tìm một đoạn ký tự ở giữa token, n-gram có thể phù hợp nhưng phải chấp nhận chi phí lớn hơn.

## 4. Elasticsearch tạo gram ở đâu trong analyzer?

Elasticsearch phân tích văn bản qua analyzer. Một analyzer thường gồm:

1. **Character filters:** có thể biến đổi văn bản trước khi tokenizer xử lý, ví dụ thay thế ký tự hoặc loại bỏ một số dấu.
2. **Tokenizer:** chia văn bản thành token.
3. **Token filters:** biến đổi, chuẩn hóa hoặc tạo thêm token từ kết quả tokenizer.

Edge n-gram và n-gram có thể được dùng dưới dạng tokenizer hoặc token filter. Hai dạng có vị trí và hành vi khác nhau:

- **N-gram tokenizer / edge n-gram tokenizer:** thực hiện việc chia đầu vào thành các gram ngay ở bước tokenizer. Với tokenizer, cấu hình token_chars có thể giới hạn loại ký tự được đưa vào token, ví dụ chỉ giữ chữ và số.
- **N-gram token filter / edge n-gram token filter:** nhận các token đã được tokenizer tạo ra rồi sinh gram từ từng token. Cách này thuận tiện khi muốn giữ cách tách từ của standard tokenizer và chỉ thay đổi token sau đó.

Trong ví dụ autocomplete thông dụng, có thể dùng standard tokenizer để tách câu thành từ, sau đó áp dụng edge_ngram token filter cho từng từ.

Với văn bản Spring Data, tokenizer tách thành hai token Spring và Data. Token filter edge n-gram tạo các tiền tố riêng cho từng token. Nó không tạo một chuỗi gram xuyên qua dấu cách giữa hai từ.

## 5. Cấu hình edge n-gram cho autocomplete

Giả sử ứng dụng cần tìm sản phẩm theo tiền tố tên. Ta muốn index các tiền tố có độ dài từ 2 đến 10 ký tự, đồng thời khi tìm kiếm chỉ phân tích từ khóa người dùng nhập bằng analyzer thông thường.

Có thể tạo index với custom analyzer:

    PUT products
    {
      "settings": {
        "index": {
          "max_ngram_diff": 8
        },
        "analysis": {
          "filter": {
            "autocomplete_edge": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 10
            }
          },
          "analyzer": {
            "autocomplete_index": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "autocomplete_edge"
              ]
            },
            "autocomplete_search": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase"
              ]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "autocomplete_index",
            "search_analyzer": "autocomplete_search"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Ở đây:

- autocomplete_index được dùng khi index document. Nó tách từ bằng standard tokenizer, chuyển chữ thành chữ thường rồi tạo tiền tố từ 2 đến 10 ký tự.
- autocomplete_search được dùng khi phân tích query. Nó tách từ và chuyển chữ thường nhưng không tạo thêm gram.
- search_analyzer giúp từ khóa người dùng nhập được giữ ở dạng từ thông thường, sau đó khớp với các tiền tố đã có trong inverted index.
- index.max_ngram_diff cho phép khoảng cách giữa max_gram và min_gram bằng 8. Elasticsearch giới hạn khoảng cách này để tránh cấu hình gram quá lớn ngoài ý muốn; cần đặt setting phù hợp với khoảng đã chọn.

Tách analyzer lúc index và lúc search là điểm rất quan trọng. Nếu dùng edge n-gram cho cả hai phía, một từ khóa nhập vào cũng bị tách thành nhiều tiền tố, có thể tạo ra nhiều cách khớp và làm thay đổi mức độ liên quan không như mong muốn.

### Kiểm tra token được tạo

Có thể dùng Analyze API để xem analyzer hoạt động:

    POST products/_analyze
    {
      "analyzer": "autocomplete_index",
      "text": "Spring Data"
    }

Với min=2 và max=10, kết quả sẽ có các token tiền tố của spring và data, sau khi chuyển thành chữ thường. Ví dụ phần token của spring bắt đầu bằng sp, spr, spri và tiếp tục đến spring.

Kiểm tra analyzer tìm kiếm:

    POST products/_analyze
    {
      "analyzer": "autocomplete_search",
      "text": "Spri"
    }

Analyzer tìm kiếm tạo token spri. Token này có thể khớp với token spri đã được index từ Spring.

### Thực hiện truy vấn

Sau khi index document:

    POST products/_doc/1
    {
      "name": "Spring Data Elasticsearch",
      "category": "backend"
    }

Có thể tìm theo tiền tố:

    GET products/_search
    {
      "query": {
        "match": {
          "name": "spri"
        }
      }
    }

Query match dùng search analyzer đã khai báo cho field name. Nó tạo token spri, sau đó tìm token tương ứng trong inverted index được tạo bởi edge n-gram analyzer.

Trong Spring Data Elasticsearch, entity có thể khai báo analyzer tương ứng:

    @Document(indexName = "products", createIndex = false)
    public class Product {

        @Id
        private String id;

        @Field(
            type = FieldType.Text,
            analyzer = "autocomplete_index",
            searchAnalyzer = "autocomplete_search"
        )
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;
    }

Định nghĩa analyzer phải được cung cấp trong index settings trước khi tạo index. Annotation tham chiếu tên analyzer; nó không tự định nghĩa toàn bộ cấu hình filter, tokenizer và gram range. Ví dụ đặt createIndex = false vì index và settings được tạo bởi quy trình quản lý index riêng.

## 6. Cấu hình n-gram để tìm chuỗi con

Nếu ứng dụng cần tìm một đoạn nằm giữa token, có thể sử dụng n-gram token filter. Ví dụ, muốn tìm ring trong spring, edge n-gram không tạo token ring, nhưng n-gram có thể tạo ra.

Ví dụ analyzer:

    PUT products_substring
    {
      "settings": {
        "index": {
          "max_ngram_diff": 8
        },
        "analysis": {
          "filter": {
            "substring_grams": {
              "type": "ngram",
              "min_gram": 2,
              "max_gram": 10
            }
          },
          "analyzer": {
            "substring_index": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "substring_grams"
              ]
            },
            "substring_search": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase"
              ]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "substring_index",
            "search_analyzer": "substring_search"
          }
        }
      }
    }

Với token spring, analyzer n-gram có thể tạo sp, pr, ri, in, ng và các gram dài hơn như spr, pri, rin, ing. Vì vậy, query ring có thể tìm được token gốc spring thông qua các gram được index.

N-gram mở rộng khả năng khớp nhưng cũng có thể làm kết quả rộng hơn mong muốn. Ví dụ, các từ khác nhau có thể chứa cùng một gram ngắn. Gram càng ngắn, khả năng trùng lặp giữa các từ càng cao. Vì thế, cần chọn min_gram dựa trên độ dài truy vấn ngắn nhất có ý nghĩa nghiệp vụ.

## 7. Chi phí kích thước index được tạo ra như thế nào?

Elasticsearch lưu các term trong inverted index để tìm document theo term. Khi dùng n-gram, một token gốc được chuyển thành nhiều token nhỏ. Những token này trở thành term có thể được lập chỉ mục và liên kết với document chứa chúng.

Nếu một token có độ dài L, cấu hình gram từ m đến M, số gram được tạo có thể ước tính như sau.

Với edge n-gram:

\[
N_{edge} = \max(0,\min(M,L)-m+1)
\]

Với n-gram đầy đủ:

\[
N_{ngram} =
\sum_{k=m}^{\min(M,L)} (L-k+1)
\]

Trong đó:

- L là độ dài token.
- m là min_gram.
- M là max_gram.
- k là độ dài gram đang được tạo.

Ví dụ token dài 10 ký tự, min_gram = 2, max_gram = 5:

- Edge n-gram tạo 4 token: các tiền tố dài 2, 3, 4 và 5.
- N-gram tạo 30 token: 9 gram dài 2, 8 gram dài 3, 7 gram dài 4 và 6 gram dài 5.

Đây là số lần sinh token cho một token đầu vào, không phải số term duy nhất hay số byte cuối cùng của index. Kích thước thực tế còn phụ thuộc:

- Số document và số token gốc.
- Số term duy nhất sau khi các gram trùng nhau được hợp nhất trong dictionary.
- Tần suất term xuất hiện và số document chứa term đó.
- Độ dài term, cấu trúc postings và mức độ nén.
- Các cấu hình khác của index, segment, stored fields và doc values.

Dù không thể suy ra chính xác dung lượng từ công thức token, số token phát sinh là một tín hiệu tốt để so sánh chi phí giữa các cấu hình. N-gram đầy đủ thường tạo nhiều vị trí token hơn edge n-gram, vì vậy thường làm tăng kích thước inverted index và chi phí indexing đáng kể.

## 8. Các yếu tố làm tăng hoặc giảm chi phí

### min_gram

Giảm min_gram khiến nhiều gram ngắn được tạo hơn. Ví dụ min=1 sẽ tạo các ký tự đơn. Những gram này thường xuất hiện ở rất nhiều document, có khả năng tạo postings lớn và làm kết quả tìm kiếm kém chọn lọc.

Chỉ nên dùng gram một ký tự nếu sản phẩm thực sự cần hỗ trợ tìm kiếm từ một ký tự và đã đánh giá tác động đến dung lượng, hiệu năng và chất lượng kết quả.

### max_gram

Tăng max_gram khiến nhiều gram dài hơn được tạo. Với edge n-gram, số token tăng theo số độ dài được bổ sung. Với n-gram đầy đủ, mỗi độ dài mới còn tạo chuỗi ở nhiều vị trí, nên chi phí có thể tăng nhanh hơn.

max_gram cũng ảnh hưởng đến khả năng tìm kiếm với từ khóa dài. Nếu token gốc dài hơn max_gram, analyzer index không tạo token nguyên vẹn ở độ dài đó trừ khi cấu hình có cách giữ token gốc. Điều này có thể khiến truy vấn dài không khớp như mong muốn.

### Độ dài văn bản và số lượng field

Document có nhiều từ hoặc nhiều field cùng áp dụng n-gram sẽ tạo thêm nhiều token. Nếu vừa n-gram tiêu đề, mô tả, tên thương hiệu và nội dung dài, chi phí có thể tăng mạnh.

Không nên áp dụng n-gram cho toàn bộ field văn bản theo mặc định. Hãy giới hạn nó vào field phục vụ autocomplete hoặc substring search.

### N-gram hay edge n-gram

Nếu chỉ cần tiền tố, edge n-gram thường tiết kiệm hơn. Nếu cần khớp ở giữa từ, n-gram có thể cần thiết nhưng nên giới hạn gram range và phạm vi field.

### Số lượng document và tần suất cập nhật

Nhiều document hơn đồng nghĩa nhiều lần tạo gram hơn. Khi dữ liệu thường xuyên được cập nhật hoặc index lại, chi phí CPU và I/O cho việc phân tích token cũng tăng. Cần đo cả tốc độ indexing và tốc độ search, không chỉ đo dung lượng cuối cùng.

## 9. max_gram và vấn đề truy vấn dài hơn gram đã index

Giả sử analyzer index chỉ tạo gram dài tối đa 10 ký tự, nhưng người dùng nhập một từ dài 13 ký tự. Search analyzer thông thường tạo một token dài 13 ký tự. Nếu index analyzer không lưu token gốc và không tạo gram dài hơn 10 ký tự, term dài đó có thể không tồn tại trong inverted index. Kết quả là query không khớp dù document chứa từ gốc.

Có một số cách xử lý:

1. Chọn max_gram đủ lớn cho độ dài truy vấn thường gặp.
2. Dùng edge n-gram token filter với preserve_original = true nếu cần giữ thêm token gốc bên cạnh các tiền tố.
3. Tách một sub-field bình thường để tìm kiếm từ nguyên vẹn, rồi kết hợp với field autocomplete.
4. Chuyển sang query hoặc chiến lược khác cho truy vấn dài.

Ví dụ giữ token gốc:

    "filter": {
      "autocomplete_edge": {
        "type": "edge_ngram",
        "min_gram": 2,
        "max_gram": 10,
        "preserve_original": true
      }
    }

preserve_original có thể thêm token ban đầu ngoài các gram được sinh. Điều này giúp giữ khả năng khớp nguyên từ dài hơn max_gram nhưng cũng làm tăng số token và dung lượng. Hãy kiểm tra hành vi bằng Analyze API trên đúng phiên bản Elasticsearch đang sử dụng.

Một cách khác là định nghĩa multi-field: một field dùng analyzer autocomplete, field khác dùng analyzer chuẩn. Nhờ đó, ứng dụng có thể kết hợp tìm tiền tố và tìm nguyên từ mà không buộc mọi query đi qua cùng một analyzer.

## 10. Cách chọn cấu hình theo yêu cầu tìm kiếm

| Yêu cầu | Cấu hình nên cân nhắc | Lý do |
|---|---|---|
| Gợi ý khi người dùng nhập từ đầu | Edge n-gram | Chỉ cần các tiền tố |
| Tìm đoạn ký tự ở giữa từ | N-gram | Tạo gram ở mọi vị trí |
| Tìm toàn văn thông thường | Standard analyzer hoặc analyzer ngôn ngữ phù hợp | Không cần nhân bản token thành gram |
| Gợi ý từ danh sách cố định, có trọng số | Completion suggester | Tối ưu cho danh sách gợi ý |
| Autocomplete trên field có cấu trúc hỗ trợ | search_as_you_type | Elasticsearch cung cấp field type và các sub-field phục vụ search-as-you-type |
| So khớp chính xác mã hoặc trạng thái | Keyword và term query | Không cần n-gram nếu không tìm substring |

Edge n-gram không phải lựa chọn mặc định cho mọi bài toán tìm kiếm. Nếu chỉ cần autocomplete từ danh sách gợi ý được chuẩn bị trước, completion suggester có thể phù hợp hơn. Nếu muốn tìm kiếm dạng search-as-you-type với cấu trúc được Elasticsearch hỗ trợ, hãy đánh giá field type search_as_you_type. Nếu chỉ cần so khớp chính xác, dùng keyword thay vì tạo thêm gram.

## 11. Kết hợp field autocomplete và field tìm kiếm bình thường

Một sản phẩm có thể cần nhiều kiểu tìm kiếm:

- Gợi ý nhanh khi người dùng nhập tiền tố tên.
- Tìm toàn văn theo tên.
- Lọc chính xác theo danh mục.
- Sắp xếp hoặc aggregation theo trường phù hợp.

Không nên ép một field duy nhất đáp ứng tất cả các mục tiêu nếu analyzer của nó làm thay đổi token theo cách không phù hợp. Có thể dùng multi-fields:

    PUT products
    {
      "settings": {
        "index": {
          "max_ngram_diff": 8
        },
        "analysis": {
          "filter": {
            "autocomplete_edge": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 10
            }
          },
          "analyzer": {
            "autocomplete_index": {
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "autocomplete_edge"
              ]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard",
            "fields": {
              "autocomplete": {
                "type": "text",
                "analyzer": "autocomplete_index",
                "search_analyzer": "standard"
              },
              "raw": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Trong ví dụ:

- name giữ analyzer chuẩn cho tìm kiếm toàn văn.
- name.autocomplete dùng edge n-gram cho truy vấn tiền tố.
- name.raw là keyword để so khớp chính xác, sort hoặc aggregation.

Có thể tìm autocomplete qua field phụ:

    GET products/_search
    {
      "query": {
        "match": {
          "name.autocomplete": "spri"
        }
      }
    }

Và tìm toàn văn qua field chính:

    GET products/_search
    {
      "query": {
        "match": {
          "name": "spring data"
        }
      }
    }

Multi-fields tạo thêm dữ liệu index cho cùng một giá trị nguồn. Đây là sự đánh đổi có chủ đích: khả năng truy vấn đa dạng hơn đi kèm chi phí lưu trữ và indexing cao hơn.

## 12. Kiểm tra chi phí và chất lượng trước khi triển khai

Không nên chọn min_gram, max_gram hoặc loại gram chỉ dựa trên một vài ví dụ ngắn. Cần thử trên dữ liệu đại diện và đo kết quả.

### Bước 1: kiểm tra token

Dùng Analyze API với các từ ngắn, dài, có dấu, có số, dấu gạch nối và nhiều từ:

    POST products/_analyze
    {
      "analyzer": "autocomplete_index",
      "text": [
        "Spring Data",
        "Elasticsearch",
        "A12-B34",
        "Cà phê"
      ]
    }

Kiểm tra:

- Tokenizer tách từ như mong muốn không?
- Gram có giữ hoặc loại ký tự đúng yêu cầu không?
- Từ khóa tìm kiếm được phân tích tương thích với token index không?
- Từ quá ngắn hoặc quá dài có tạo kết quả ngoài mong muốn không?

### Bước 2: so sánh cấu hình

Tạo các index thử nghiệm với cùng dữ liệu:

- Analyzer chuẩn.
- Edge n-gram với một khoảng gram nhỏ.
- Edge n-gram với khoảng gram lớn hơn.
- N-gram với khoảng gram tương ứng.

Không nên so sánh hai index có số lượng document hoặc dữ liệu đầu vào khác nhau.

### Bước 3: đo kích thước

Có thể xem dung lượng index bằng CAT API:

    GET _cat/indices/products*?v&h=index,docs.count,store.size

Hoặc dùng stats API:

    GET products/_stats/store,indexing

Quan sát store.size, số document, chỉ số indexing và thời gian index dữ liệu. Dung lượng cần được đo sau khi index và refresh hoàn tất, với cùng điều kiện so sánh.

### Bước 4: đo chất lượng và tốc độ truy vấn

Chuẩn bị một tập truy vấn mô phỏng cách người dùng nhập:

- Một ký tự.
- Hai hoặc ba ký tự đầu.
- Tiền tố dài hơn.
- Đoạn ký tự ở giữa từ.
- Từ có dấu hoặc ký tự đặc biệt.
- Từ dài hơn max_gram.

Đo latency, số lượng kết quả, thứ tự kết quả và tỷ lệ kết quả đúng với nhu cầu. Một cấu hình tạo nhiều gram có thể tìm được nhiều document hơn nhưng cũng làm tăng kết quả không liên quan.

### Bước 5: kiểm tra vận hành

Ngoài dung lượng và latency, cần kiểm tra:

- Tốc độ bulk indexing.
- Chi phí khi cập nhật document.
- Thời gian reindex dữ liệu cũ.
- Dung lượng segment và merge.
- Heap, filesystem cache và I/O của node.
- Tải truy vấn khi nhiều người dùng autocomplete đồng thời.

Không thể kết luận một cấu hình tốt chỉ từ số token lý thuyết. Hãy dùng công thức để ước lượng ban đầu, sau đó đo trên dữ liệu và hạ tầng gần với môi trường thật.

## 13. Những lỗi thường gặp

### Dùng n-gram đầy đủ cho yêu cầu chỉ cần tiền tố

N-gram tạo gram ở mọi vị trí, làm tăng số token mà không mang lại giá trị nếu người dùng chỉ nhập từ đầu. Với autocomplete theo tiền tố, edge n-gram thường tiết kiệm hơn.

### Chọn min_gram quá nhỏ

Gram một ký tự hoặc hai ký tự có thể xuất hiện trong rất nhiều từ. Kết quả trở nên rộng, nhiều document cùng khớp và chi phí postings tăng. Chọn min_gram theo độ dài truy vấn có ý nghĩa, không chỉ để hỗ trợ nhập càng ít ký tự càng tốt.

### Chọn max_gram quá thấp

Từ khóa dài hơn gram tối đa có thể không khớp nếu token gốc không được giữ. Hãy kiểm tra truy vấn dài và cân nhắc preserve_original hoặc field tìm kiếm chuẩn.

### Dùng cùng analyzer ở index và search

Nếu search analyzer cũng tạo n-gram, query có thể bị chia thành nhiều gram, làm thay đổi ngữ nghĩa khớp và điểm liên quan. Với autocomplete tiền tố, thường nên tạo gram khi index và dùng analyzer chuẩn khi search.

### Áp dụng n-gram cho mọi field

N-gram ở field mô tả dài, nội dung lớn hoặc nhiều field cùng lúc có thể làm index tăng mạnh. Chỉ áp dụng vào field thực sự cần tìm theo tiền tố hoặc chuỗi con.

### Không kiểm tra tokenizer và token_chars

Với tokenizer n-gram, cấu hình token_chars ảnh hưởng loại ký tự được giữ. Nếu không kiểm tra, dấu cách, dấu câu hoặc ký tự đặc biệt có thể tạo gram không mong muốn. Với token filter, hãy kiểm tra cách tokenizer trước đó đã tách văn bản.

### Nghĩ rằng tăng số gram chỉ làm index lớn hơn

Nhiều gram còn ảnh hưởng indexing throughput, merge, cache, query selectivity và relevance score. Những gram phổ biến có thể làm truy vấn rộng hơn và tăng công việc xử lý.

## Kết luận

Edge n-gram tạo các tiền tố của token và phù hợp với autocomplete theo từ đầu. N-gram tạo các chuỗi con ở mọi vị trí, hỗ trợ tìm đoạn nằm giữa từ nhưng thường sinh nhiều token hơn. Số token tăng làm inverted index có thêm term và postings, kéo theo chi phí dung lượng, indexing và vận hành.

Khi thiết kế, hãy xác định rõ người dùng cần tìm tiền tố hay chuỗi con, chọn min_gram và max_gram theo truy vấn thực tế, dùng analyzer index và search phù hợp, rồi đo dung lượng và hiệu năng trên dữ liệu đại diện. Nếu chỉ cần autocomplete, edge n-gram thường là điểm bắt đầu hợp lý; nếu cần tìm substring, n-gram cần được giới hạn và đánh giá kỹ để chi phí index không vượt quá lợi ích tìm kiếm.
