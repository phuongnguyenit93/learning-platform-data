# Search-as-you-type, edge n-gram và lựa chọn theo yêu cầu

Ô tìm kiếm thường cần phản hồi ngay khi người dùng đang nhập, trước khi họ hoàn thành từ hoặc cụm từ. Nếu ứng dụng chỉ chạy match query trên nội dung đầy đủ, từ khóa đang nhập dở có thể chưa khớp với token đã được index. Elasticsearch cung cấp nhiều cách giải quyết bài toán này, trong đó hai lựa chọn thường gặp là field type search_as_you_type và analyzer dùng edge n-gram.

Hai cách đều hỗ trợ tìm kiếm theo tiền tố, nhưng có cách tổ chức index và cách truy vấn khác nhau:

- **search_as_you_type** là field type chuyên dụng của Elasticsearch. Nó tự tạo các sub-field phục vụ tìm kiếm theo cụm từ và tiền tố, thường được truy vấn bằng multi_match với type bool_prefix.
- **edge n-gram** là kỹ thuật phân tích văn bản. Khi index, analyzer tạo các token tiền tố từ đầu mỗi từ. Ứng dụng có thể tùy chỉnh min_gram, max_gram, analyzer và query theo yêu cầu riêng.

Ngoài hai lựa chọn này, Elasticsearch còn có match_phrase_prefix, prefix query và completion suggester. Cần chọn giải pháp theo bản chất dữ liệu và trải nghiệm cần xây dựng: tìm kiếm toàn văn khi đang nhập, gợi ý tên từ danh sách, tìm mã định danh hay tự động hoàn thành một cụm từ.

## 1. Vấn đề của tìm kiếm khi người dùng đang nhập

Giả sử một document có tiêu đề:

    Spring Data Elasticsearch Guide

Khi người dùng nhập lần lượt:

    s
    sp
    spr
    spri
    spring
    spring d
    spring da

Ứng dụng muốn hiển thị kết quả phù hợp ngay cả khi từ cuối chưa hoàn chỉnh. Match query thông thường phân tích query thành token và tìm các term tương ứng trong inverted index. Nếu token đã index là spring nhưng người dùng đang nhập spri, hai term không giống nhau nên match thông thường có thể không tìm thấy document.

Search-as-you-type giải quyết bằng cách chuẩn bị dữ liệu index để hỗ trợ tiền tố. Tùy giải pháp, Elasticsearch có thể tìm tiền tố của token cuối, kết hợp các từ đã hoàn chỉnh hoặc ưu tiên kết quả có thứ tự từ phù hợp.

Một ô tìm kiếm khi đang nhập có thể cần:

- Khớp các từ ở đầu tiêu đề.
- Khớp tiền tố của từ cuối.
- Cho phép một vài từ đã nhập trước đó nằm ở các vị trí phù hợp.
- Ưu tiên kết quả có cụm từ gần với thứ tự người dùng nhập.
- Giữ latency thấp khi số lượng document lớn.
- Hỗ trợ dấu, chữ hoa/chữ thường và ngôn ngữ của dữ liệu.

Không phải mọi use case đều cần cùng một semantics. Ví dụ autocomplete tên sản phẩm có thể cần gợi ý theo tiền tố của tên; tìm kiếm toàn văn có thể cần tìm nhiều field và xếp hạng theo relevance; tra mã SKU có thể chỉ cần prefix trên một field keyword.

## 2. Tổng quan các lựa chọn

| Cách làm | Cách hoạt động | Phù hợp khi |
|---|---|---|
| search_as_you_type | Elasticsearch tạo sub-field shingle và prefix để hỗ trợ cụm từ đang nhập | Muốn triển khai search-as-you-type toàn văn với cấu hình tương đối đơn giản |
| edge n-gram | Index nhiều tiền tố của từng token | Cần kiểm soát min/max gram, analyzer hoặc logic tiền tố riêng |
| match_phrase_prefix | Tìm cụm từ, term cuối được xử lý như prefix | Cần cụm từ có thứ tự và dữ liệu không quá lớn hoặc latency đã được đo phù hợp |
| prefix query | Tìm term bắt đầu bằng chuỗi trên field phù hợp | Tra cứu prefix chính xác trên keyword hoặc mã định danh |
| completion suggester | Dùng cấu trúc completion chuyên dụng để trả gợi ý | Gợi ý từ danh sách lựa chọn được chuẩn bị trước, như tên sản phẩm hoặc địa điểm |

Không có một lựa chọn luôn tốt nhất. search_as_you_type thường là điểm bắt đầu hợp lý cho ô tìm kiếm toàn văn. Edge n-gram hữu ích khi cần kiểm soát chi tiết token tiền tố. Completion suggester phù hợp với danh sách gợi ý được quản lý riêng, còn prefix query phù hợp với field keyword và mã.

## 3. search_as_you_type là gì?

search_as_you_type là field type của Elasticsearch được thiết kế cho tìm kiếm trong lúc người dùng nhập. Khi mapping field này, Elasticsearch tạo một số sub-field để hỗ trợ tìm kiếm cụm từ và tiền tố:

- Field gốc lưu nội dung dạng text.
- Các sub-field shingle như _2gram và _3gram lưu các nhóm token liền kề.
- Sub-field _index_prefix hỗ trợ truy vấn tiền tố hiệu quả và được Elasticsearch sử dụng trong cơ chế tìm kiếm tương ứng.

Ví dụ mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "search_as_you_type"
          }
        }
      }
    }

Với mapping trên, Elasticsearch tạo các sub-field cần thiết cho name. Ứng dụng không phải tự định nghĩa edge_ngram analyzer cho trường hợp cơ bản.

Có thể cấu hình max_shingle_size để kiểm soát kích thước shingle lớn nhất:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "search_as_you_type",
            "max_shingle_size": 3
          }
        }
      }
    }

Giá trị mặc định thường là 3; Elasticsearch hỗ trợ các kích thước shingle trong khoảng được tài liệu của phiên bản quy định. Tăng kích thước shingle có thể bổ sung khả năng khớp nhiều từ liên tiếp, nhưng cũng làm tăng lượng dữ liệu index.

### Các sub-field được tạo

Với field name, các sub-field thường có dạng:

    name
    name._2gram
    name._3gram
    name._index_prefix

Field gốc hỗ trợ tìm kiếm token. Các field shingle chứa các nhóm token liền kề, giúp ưu tiên cụm từ theo thứ tự. Field _index_prefix hỗ trợ tiền tố của token cuối và được Elasticsearch dùng để tối ưu cách truy vấn prefix trên các field search_as_you_type.

Trong query phổ biến, ứng dụng thường chỉ cần chỉ định name, name._2gram và name._3gram. Không cần tự thêm _index_prefix vào danh sách fields trong mọi trường hợp; cơ chế prefix sub-field được thiết kế để hỗ trợ query phù hợp.

## 4. Truy vấn search_as_you_type bằng bool_prefix

Elasticsearch thường dùng multi_match với type bool_prefix để tìm kiếm trên field search_as_you_type và các sub-field shingle.

Ví dụ:

    GET products/_search
    {
      "query": {
        "multi_match": {
          "query": "spring data elas",
          "type": "bool_prefix",
          "fields": [
            "name",
            "name._2gram",
            "name._3gram"
          ]
        }
      }
    }

bool_prefix tạo match_bool_prefix query trên từng field rồi kết hợp kết quả. Các term trước term cuối được xử lý như term thông thường; term cuối được dùng như prefix. Những sub-field shingle giúp query ưu tiên kết quả có nhiều từ liên tiếp và đúng thứ tự.

Ví dụ:

- Document có name là Spring Data Elasticsearch Guide có thể khớp với query spring data elas.
- Document có name là Elasticsearch Guide for Spring Data có thể vẫn khớp các term tùy operator và cấu trúc query, nhưng thường không nhận cùng mức ưu tiên cho chuỗi liên tiếp ở đầu.
- Document chỉ có từ spring mà không có các term còn lại sẽ không đáp ứng một query yêu cầu tất cả term.

Để yêu cầu tất cả term trong query phải khớp, có thể cấu hình operator AND:

    GET products/_search
    {
      "query": {
        "multi_match": {
          "query": "spring data elas",
          "type": "bool_prefix",
          "operator": "and",
          "fields": [
            "name",
            "name._2gram",
            "name._3gram"
          ]
        }
      }
    }

Operator điều khiển cách kết hợp các term trong match_bool_prefix. Hãy thử với dữ liệu đại diện để xác định liệu ứng dụng muốn chấp nhận document thiếu một term hay yêu cầu toàn bộ từ đã nhập đều khớp.

## 5. Vì sao search_as_you_type dùng shingle?

Shingle là nhóm token liền kề được tạo từ một chuỗi. Ví dụ văn bản:

    spring data elasticsearch guide

Các shingle hai từ có thể gồm:

    spring data
    data elasticsearch
    elasticsearch guide

Các shingle ba từ có thể gồm:

    spring data elasticsearch
    data elasticsearch guide

Khi index những cụm từ này, Elasticsearch có thể nhận ra nhiều từ xuất hiện liền nhau và ưu tiên document có thứ tự gần với query. Đây là lý do query trên field _2gram và _3gram thường giúp xếp hạng tốt hơn so với chỉ tìm các token riêng lẻ.

Shingle không có nghĩa Elasticsearch chỉ tìm đúng một cụm từ nguyên văn. Query vẫn có thể kết hợp nhiều field và token theo semantics của bool_prefix. Shingle là tín hiệu bổ sung cho việc xếp hạng và tìm cụm từ.

Khi max_shingle_size lớn hơn, index có thể chứa nhiều tổ hợp token hơn. Cần cân nhắc dung lượng index, tốc độ ingest và lợi ích relevance thực tế.

## 6. search_as_you_type trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch hiện đại, có thể dùng NativeQuery và Elasticsearch Java API Client để tạo multi-match bool_prefix.

Ví dụ entity:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        private String description;
    }

Mapping search_as_you_type nên được tạo nhất quán với entity. Có thể quản lý mapping bằng index template, script khởi tạo index hoặc IndexOperations trong Spring Data. Cách khai báo annotation cho từng FieldType phụ thuộc phiên bản Spring Data Elasticsearch đang dùng; hãy kiểm tra API phiên bản dự án thay vì giả định annotation hỗ trợ toàn bộ thuộc tính mapping của Elasticsearch.

Service tìm kiếm:

    @Service
    public class ProductSuggestService {

        private final ElasticsearchOperations operations;

        public ProductSuggestService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> suggest(
                String input,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .multiMatch(m -> m
                        .query(input)
                        .type(TextQueryType.BoolPrefix)
                        .fields(
                            "name",
                            "name._2gram",
                            "name._3gram"
                        )
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Các import chính:

    import co.elastic.clients.elasticsearch._types.query_dsl.TextQueryType;
    import org.springframework.data.domain.Pageable;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
    import org.springframework.data.elasticsearch.core.SearchHits;

Trong ví dụ:

- input là chuỗi người dùng đang nhập.
- TextQueryType.BoolPrefix chọn multi_match bool_prefix.
- name là field gốc.
- name._2gram và name._3gram là sub-field được Elasticsearch tạo tự động.
- Pageable giới hạn số gợi ý trả về.
- ElasticsearchOperations thực thi query và ánh xạ kết quả thành Product.

Tên enum và chữ ký builder phụ thuộc phiên bản Elasticsearch Java API Client mà Spring Data đang sử dụng. Nếu phiên bản dự án không có đúng enum hoặc overload như ví dụ, kiểm tra dependency thực tế và dùng API tương ứng.

## 7. Edge n-gram là gì?

Edge n-gram là kỹ thuật tạo các token tiền tố bắt đầu từ đầu mỗi token gốc. Ví dụ từ elasticsearch với min_gram = 2 và max_gram = 6 có thể tạo:

    el
    ela
    elas
    elast
    elasti

Khi người dùng nhập ela, document có token elasticsearch có thể được tìm thấy vì token ela đã được index.

Điểm khác biệt với n-gram thông thường:

- Edge n-gram chỉ tạo các chuỗi bắt đầu từ đầu token.
- N-gram có thể tạo các chuỗi con ở nhiều vị trí trong token.

Ví dụ từ keyboard:

- Edge n-gram có thể tạo ke, key, keyb, keybo...
- N-gram với độ dài 3 có thể tạo key, e y b (không có khoảng trắng), ybo, boa... tùy cấu hình và tokenization.

Đối với autocomplete theo tiền tố, edge n-gram thường phù hợp hơn n-gram tổng quát vì người dùng thường nhập từ trái sang phải từ đầu từ.

## 8. Tokenizer và token filter edge_ngram

Elasticsearch có thể tạo edge n-gram bằng tokenizer hoặc token filter. Một cấu hình phổ biến là dùng tokenizer chuẩn để tách từ, sau đó dùng edge_ngram token filter để tạo tiền tố cho từng token.

Ví dụ:

    PUT products
    {
      "settings": {
        "analysis": {
          "filter": {
            "name_edge_ngram": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 15
            }
          },
          "analyzer": {
            "name_autocomplete_index": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "name_edge_ngram"
              ]
            },
            "name_autocomplete_search": {
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
            "analyzer": "name_autocomplete_index",
            "search_analyzer": "name_autocomplete_search"
          }
        }
      }
    }

Ở đây:

- standard tokenizer tách văn bản thành token.
- lowercase chuẩn hóa chữ hoa/chữ thường.
- name_edge_ngram tạo các tiền tố ở thời điểm index.
- search_analyzer chỉ lowercase, không tạo lại n-gram khi tìm kiếm.

Việc dùng analyzer riêng cho index và search rất quan trọng. Index cần lưu các tiền tố để có thể tìm chúng; query nên được phân tích thành token bình thường. Nếu search analyzer cũng tạo edge n-gram, query có thể bị mở rộng thành nhiều tiền tố, làm thay đổi semantics và tạo kết quả quá rộng.

## 9. Vì sao nên tách index analyzer và search analyzer?

Giả sử document có:

    name = Elasticsearch

Với index analyzer edge n-gram min_gram = 2, max_gram = 6, token stream có thể chứa:

    el
    ela
    elas
    elast
    elasti

Khi người dùng nhập:

    elas

Search analyzer chuẩn hóa thành một token elas. Term này có trong inverted index nên document khớp.

Nếu search analyzer cũng tạo edge n-gram, query elas có thể biến thành:

    el
    ela
    elas

Điều này không cần thiết cho query tiền tố cơ bản và có thể làm tăng số term được tìm. Quan trọng hơn, nếu query dài hơn max_gram, token đầu vào có thể không khớp với token đã index theo cách mong muốn.

Nguyên tắc thường dùng:

- Index analyzer: tạo token tiền tố.
- Search analyzer: chuẩn hóa query nhưng giữ token đầy đủ.

Có những thiết kế đặc biệt dùng analyzer khác ở search time, nhưng phải xác định rõ semantics và kiểm thử trên dữ liệu thật.

## 10. Chọn min_gram và max_gram

Hai tham số quan trọng của edge_ngram:

- min_gram: độ dài nhỏ nhất của tiền tố được tạo.
- max_gram: độ dài lớn nhất của tiền tố được tạo.

Ví dụ min_gram = 2, max_gram = 5 với token keyboard:

    ke
    key
    keyb
    keybo

Nếu min_gram = 2, query một ký tự k không có token tương ứng trong index và có thể không tìm được kết quả. Nếu min_gram = 1, người dùng có thể nhận gợi ý ngay từ ký tự đầu, nhưng số token index tăng và kết quả có thể rất rộng.

max_gram giới hạn độ dài tiền tố được lưu. Nếu max_gram = 15 nhưng người dùng nhập token dài 20 ký tự, token đầy đủ có thể không tồn tại trong index edge n-gram. Khi query analyzer giữ nguyên token 20 ký tự, query có thể không khớp.

Một số cách xử lý:

- Chọn max_gram đủ lớn theo độ dài từ thực tế.
- Dùng multi-field có một field full-text thông thường để tìm token đầy đủ.
- Kết hợp query prefix phù hợp cho trường hợp dài hơn max_gram.
- Chỉ dùng truncate token filter ở search time khi hiểu rõ nguy cơ false positive.

Không nên đặt max_gram quá lớn chỉ để bao phủ mọi trường hợp. Nhiều tiền tố hơn làm tăng kích thước index và chi phí indexing.

### Ước lượng kích thước token

Với một token dài L, min_gram là m và max_gram là M, số tiền tố được tạo xấp xỉ:

    max(0, min(L, M) - m + 1)

Ví dụ token dài 12, min_gram = 2 và max_gram = 8 tạo khoảng 7 tiền tố. Một document có nhiều token và nhiều field edge n-gram sẽ làm số term index tăng nhanh.

## 11. Truy vấn field edge n-gram

Với mapping edge n-gram ở trên, có thể dùng match query:

    GET products/_search
    {
      "query": {
        "match": {
          "name": {
            "query": "elas",
            "operator": "and"
          }
        }
      }
    }

Search analyzer chuẩn hóa elas thành một token đầy đủ. Token này khớp với token tiền tố được index từ Elasticsearch.

Nếu query chứa nhiều từ:

    GET products/_search
    {
      "query": {
        "match": {
          "name": {
            "query": "spring data elas",
            "operator": "and"
          }
        }
      }
    }

Các từ spring và data cũng cần tồn tại dưới dạng token tiền tố được index; elas có thể khớp tiền tố của elasticsearch. Tùy yêu cầu, có thể thiết kế multi-field để các từ hoàn chỉnh được tìm bằng analyzer chuẩn còn từ cuối dùng prefix semantics.

### Edge n-gram và thứ tự từ

Edge n-gram tạo tiền tố của từng token, không tự bảo đảm thứ tự toàn cụm từ. Một query match trên field có thể khớp các term ở nhiều vị trí mà không bắt buộc chúng tạo thành cụm từ đúng thứ tự.

Nếu thứ tự từ quan trọng, có thể:

- Kết hợp edge n-gram field với field text thông thường.
- Dùng bool query để ưu tiên match_phrase trên field chuẩn.
- Dùng search_as_you_type với shingle sub-field.
- Dùng phrase_prefix nếu semantics cụm từ phù hợp.

Không nên giả định edge n-gram tự cung cấp toàn bộ khả năng phrase ranking.

## 12. Tách field autocomplete và field full-text

Trong nhiều ứng dụng, cùng một nội dung cần phục vụ hai mục tiêu:

1. Tìm kiếm thông thường sau khi người dùng gửi form.
2. Gợi ý trong lúc người dùng đang nhập.

Có thể dùng multi-field để index hai cách:

    PUT products
    {
      "settings": {
        "analysis": {
          "filter": {
            "name_edge_ngram": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 15
            }
          },
          "analyzer": {
            "autocomplete_index": {
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "name_edge_ngram"
              ]
            },
            "autocomplete_search": {
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
            "analyzer": "standard",
            "fields": {
              "autocomplete": {
                "type": "text",
                "analyzer": "autocomplete_index",
                "search_analyzer": "autocomplete_search"
              },
              "keyword": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Sau đó:

- Dùng name cho full-text match.
- Dùng name.autocomplete cho query khi đang nhập.
- Dùng name.keyword cho exact match, sort hoặc aggregation.

Thiết kế này giữ mỗi field có semantics rõ ràng. Tuy nhiên, mỗi multi-field làm tăng dung lượng index và chi phí ghi; chỉ tạo những biến thể thực sự được ứng dụng sử dụng.

## 13. Kết hợp autocomplete và full-text relevance

Một trải nghiệm tìm kiếm tốt thường không chỉ dựa trên prefix. Khi người dùng đã nhập đủ từ, full-text relevance có thể quan trọng hơn việc chỉ khớp tiền tố.

Có thể dùng bool query:

    GET products/_search
    {
      "query": {
        "bool": {
          "should": [
            {
              "multi_match": {
                "query": "spring data elas",
                "type": "bool_prefix",
                "fields": [
                  "name",
                  "name._2gram",
                  "name._3gram"
                ],
                "boost": 3
              }
            },
            {
              "match": {
                "description": {
                  "query": "spring data elasticsearch",
                  "boost": 1
                }
              }
            }
          ],
          "minimum_should_match": 1
        }
      }
    }

Trong ví dụ, search_as_you_type tạo tín hiệu chính cho tên sản phẩm, còn description bổ sung kết quả full-text. Boost điều chỉnh mức ưu tiên tương đối.

Với edge n-gram, có thể kết hợp match trên name.autocomplete và match trên name hoặc description chuẩn. Cần tránh tạo hai clause gần như giống hệt nhau nếu chúng không bổ sung giá trị.

## 14. match_phrase_prefix: lựa chọn đơn giản cho cụm từ

match_phrase_prefix tìm cụm từ theo thứ tự và cho phép term cuối là tiền tố. Ví dụ:

    GET products/_search
    {
      "query": {
        "match_phrase_prefix": {
          "name": {
            "query": "spring data elas",
            "max_expansions": 20
          }
        }
      }
    }

Query này phù hợp khi người dùng nhập một cụm từ và thứ tự các từ quan trọng. max_expansions giới hạn số tiền tố được mở rộng cho term cuối.

Ưu điểm:

- Cú pháp đơn giản.
- Không nhất thiết phải tạo edge n-gram field.
- Có semantics cụm từ rõ ràng.

Hạn chế:

- Prefix expansion ở thời điểm query có thể tốn chi phí.
- Chỉ term cuối được xử lý theo prefix trong cụm từ.
- Cần benchmark với dữ liệu lớn và số lượng term phù hợp.

Nếu yêu cầu là search-as-you-type có relevance tốt và cần tối ưu ở quy mô lớn, search_as_you_type hoặc edge n-gram thường cho phép chuẩn bị dữ liệu index trước để query hiệu quả hơn.

## 15. Prefix query cho mã định danh và keyword

Không phải mọi ô tìm kiếm đều cần analyzer text. Với mã SKU, mã đơn hàng hoặc username chuẩn hóa, prefix query trên keyword field có thể phù hợp hơn.

Mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "sku": {
            "type": "keyword"
          }
        }
      }
    }

Query:

    GET products/_search
    {
      "query": {
        "prefix": {
          "sku": {
            "value": "KB-10"
          }
        }
      }
    }

Prefix query tìm term bắt đầu bằng chuỗi chỉ định. Nó không tách chuỗi thành các từ và không xử lý analyzer giống match query.

Với keyword, cần xác định rõ chữ hoa/chữ thường và chuẩn hóa mã ở thời điểm index và query. Có thể dùng normalizer cho keyword nếu semantics yêu cầu.

Prefix query trên field có nhiều term hoặc trên tập dữ liệu lớn có thể cần benchmark. Không nên thay mọi prefix use case bằng wildcard query có dấu * ở đầu; leading wildcard thường khó tối ưu hơn.

## 16. Completion suggester cho danh sách gợi ý

Completion suggester là cơ chế chuyên dụng cho autocomplete khi ứng dụng có danh sách gợi ý được chuẩn bị trước, ví dụ:

- Tên thành phố.
- Tên thương hiệu.
- Danh mục phổ biến.
- Tên sản phẩm đã được biên tập.
- Từ khóa tìm kiếm thường dùng.

Mapping:

    PUT search_suggestions
    {
      "mappings": {
        "properties": {
          "suggest": {
            "type": "completion"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Index document:

    PUT search_suggestions/_doc/1
    {
      "suggest": {
        "input": [
          "Spring Data Elasticsearch",
          "Spring Elasticsearch"
        ],
        "weight": 10
      },
      "category": "technology"
    }

Query:

    POST search_suggestions/_search
    {
      "suggest": {
        "name-suggest": {
          "prefix": "spring data el",
          "completion": {
            "field": "suggest"
          }
        }
      }
    }

Completion suggester dùng cấu trúc dữ liệu chuyên biệt để trả gợi ý theo tiền tố. Nó phù hợp với tập lựa chọn được index vào completion field, không thay thế full-text search trên nội dung document bất kỳ.

Có thể dùng weight để xếp hạng gợi ý. Nếu cần lọc theo ngữ cảnh, completion suggester hỗ trợ context suggester theo cấu hình mapping. Hãy kiểm tra giới hạn và cách vận hành của completion field theo phiên bản Elasticsearch.

## 17. Chọn search_as_you_type hay edge n-gram?

Hai lựa chọn đều hỗ trợ prefix nhưng có mức độ tùy chỉnh khác nhau:

| Tiêu chí | search_as_you_type | edge n-gram |
|---|---|---|
| Cấu hình ban đầu | Đơn giản, field type chuyên dụng | Cần tự định nghĩa analyzer |
| Sub-field | Elasticsearch tự tạo shingle và index-prefix field | Ứng dụng tự định nghĩa multi-field nếu cần |
| Query thường dùng | multi_match bool_prefix | match trên field dùng edge n-gram, có thể kết hợp query khác |
| Kiểm soát min/max gram | Không trực tiếp như analyzer edge n-gram | Có |
| Tối ưu thứ tự từ | Có shingle sub-field tích hợp | Cần kết hợp field/query riêng |
| Tùy chỉnh analyzer | Giới hạn theo thiết kế field type | Linh hoạt |
| Khối lượng index | Tăng do sub-field | Tăng theo số prefix và số field |
| Phù hợp | Search-as-you-type toàn văn phổ biến | Quy tắc prefix riêng hoặc cần điều chỉnh chi tiết |

Nên bắt đầu với search_as_you_type khi:

- Tìm theo tiêu đề hoặc tên có nhiều từ.
- Muốn hỗ trợ prefix của term cuối.
- Muốn có shingle để cải thiện thứ tự cụm từ.
- Không cần kiểm soát trực tiếp min_gram/max_gram.

Nên cân nhắc edge n-gram khi:

- Cần xác định chính xác độ dài tiền tố tối thiểu/tối đa.
- Muốn dùng cùng kỹ thuật trên các field hoặc analyzer đặc thù.
- Cần kiểm soát normalization, tokenization hoặc nhiều multi-field riêng.
- Đã có yêu cầu relevance và benchmark chứng minh cấu hình tùy chỉnh phù hợp hơn.

## 18. Chọn theo yêu cầu sản phẩm

Một số tình huống điển hình:

| Yêu cầu | Lựa chọn nên thử trước | Lý do |
|---|---|---|
| Tìm tên sản phẩm khi đang nhập | search_as_you_type | Có shingle và prefix sub-field tích hợp |
| Tìm cụm từ theo đúng thứ tự, term cuối còn dở | match_phrase_prefix hoặc search_as_you_type | Giữ semantics cụm từ |
| Tìm prefix trên SKU hoặc mã đơn hàng | prefix trên keyword | Mã thường cần so khớp chính xác theo tiền tố |
| Gợi ý từ danh sách thành phố/thương hiệu | completion suggester | Dữ liệu gợi ý được chuẩn bị trước |
| Cần min_gram/max_gram riêng | edge n-gram | Kiểm soát analyzer trực tiếp |
| Tìm nhiều field và xếp hạng theo relevance | multi_match kết hợp field phù hợp | Có thể kết hợp prefix và full-text |
| Tìm kiếm đa ngôn ngữ với analyzer riêng | Analyzer/multi-field được thiết kế theo ngôn ngữ | Cần kiểm soát stemming, folding và tokenization |

Hãy xác định rõ người dùng đang tìm một document hay đang chọn một gợi ý. Completion suggester thường hợp với việc chọn một giá trị trong danh sách; search_as_you_type và edge n-gram phù hợp hơn khi kết quả là document full-text.

## 19. Tìm kiếm đa ngôn ngữ và chuẩn hóa

Search-as-you-type phụ thuộc vào analyzer. Với dữ liệu tiếng Việt, cần cân nhắc cách tokenizer tách từ, chuẩn hóa Unicode, dấu và quy tắc tìm kiếm của sản phẩm.

Các câu hỏi cần kiểm tra:

- Dữ liệu có dấu và không dấu có cần tìm được lẫn nhau không?
- Có cần lowercase không?
- Có cần ASCII folding hoặc bộ chuyển dấu tiếng Việt tùy chỉnh không?
- Tokenizer có tách từ tiếng Việt theo kỳ vọng không?
- Có cần analyzer riêng cho từng ngôn ngữ?
- Tên riêng, mã sản phẩm hoặc chữ viết tắt có bị phân tích sai không?

Lowercase không tự loại bỏ dấu tiếng Việt. ASCII folding có thể chuyển một số ký tự có dấu thành dạng không dấu, nhưng cần kiểm tra cấu hình analyzer và kết quả thực tế với dữ liệu tiếng Việt.

Không nên áp dụng cùng một analyzer cho mọi field. Tên sản phẩm, mã SKU, mô tả dài và tên người có thể cần mapping khác nhau.

### Kiểm tra bằng Analyze API

Trước khi triển khai, hãy xem token thực tế:

    POST products/_analyze
    {
      "analyzer": "name_autocomplete_index",
      "text": "Bàn phím cơ Keychron"
    }

Với search analyzer:

    POST products/_analyze
    {
      "analyzer": "name_autocomplete_search",
      "text": "ban phim key"
    }

So sánh hai token stream để xác nhận:

- Index analyzer tạo đúng tiền tố.
- Search analyzer không tạo n-gram ngoài ý muốn.
- Dấu và chữ hoa/chữ thường được xử lý như yêu cầu.
- min_gram và max_gram không làm mất những query hợp lệ.

## 20. Hiệu năng và kích thước index

Autocomplete thường đánh đổi dung lượng index và chi phí indexing để giảm công việc phải làm ở query time.

Với edge n-gram, mỗi token gốc tạo nhiều token tiền tố. Khi min_gram thấp và max_gram cao, số token tăng. Nếu áp dụng cho nhiều field hoặc nhiều ngôn ngữ, dung lượng inverted index có thể tăng đáng kể.

Với search_as_you_type, các sub-field shingle và prefix cũng làm tăng dữ liệu index so với một field text đơn giản. Elasticsearch quản lý cấu trúc này, nhưng ứng dụng vẫn cần đo dung lượng và throughput.

Một số nguyên tắc:

- Chỉ bật autocomplete trên field thực sự cần.
- Giới hạn max_gram theo độ dài query thực tế.
- Chọn min_gram theo số ký tự tối thiểu mà sản phẩm muốn hiển thị gợi ý.
- Giữ page size nhỏ cho endpoint suggestion.
- Debounce ở client để không gửi request cho từng phím nếu latency và tải không cho phép.
- Giới hạn số request đồng thời và áp dụng timeout.
- Theo dõi p95/p99 latency, CPU, heap và kích thước index.
- Benchmark với dữ liệu có phân phối từ và độ dài gần production.

Không nên chỉ đo một query trên vài document. Prefix ngắn thường khớp rất nhiều document và là trường hợp cần benchmark kỹ nhất.

## 21. Debounce và thiết kế endpoint gợi ý

Ngay cả khi query Elasticsearch nhanh, gửi request cho mỗi lần nhấn phím có thể tạo tải lớn. Frontend thường dùng debounce để đợi một khoảng ngắn sau lần nhập cuối trước khi gửi request.

Luồng gợi ý:

    Người dùng nhập ký tự
          |
          v
    Đặt lại debounce timer
          |
          v
    Hết thời gian chờ?
          |
          +-- Không --> Chờ tiếp
          |
          +-- Có --> Gửi request suggestion
                         |
                         v
                    Elasticsearch
                         |
                         v
                    Trả top N
                         |
                         v
                    Hiển thị gợi ý

Ở server:

- Từ chối hoặc bỏ qua query quá ngắn nếu nghiệp vụ yêu cầu.
- Giới hạn kích thước kết quả.
- Whitelist field và filter.
- Áp dụng authorization/tenant filter như các endpoint tìm kiếm khác.
- Giới hạn thời gian xử lý.
- Không trả quá nhiều metadata nếu UI chỉ cần id và label.

Debounce là tối ưu phía client, không thay thế giới hạn tải và bảo vệ tài nguyên ở server.

## 22. Reindex khi thay đổi analyzer hoặc mapping

Analyzer được sử dụng khi index document. Nếu đổi min_gram, max_gram, tokenizer hoặc filter, các token đã index không tự được tạo lại chỉ vì cập nhật cấu hình.

Nhiều thuộc tính mapping và analyzer không thể thay đổi trực tiếp trên field hiện có. Khi cần thay đổi analyzer hoặc chuyển field sang search_as_you_type, quy trình phổ biến là:

1. Tạo index mới với settings và mapping mới.
2. Reindex document từ index cũ sang index mới.
3. Kiểm tra số lượng document và query mẫu.
4. Chuyển alias sang index mới khi dữ liệu đã sẵn sàng.
5. Giữ phương án quay lại index cũ theo quy trình vận hành.

Ví dụ tạo index mới:

    PUT products_v2
    {
      "settings": {
        "analysis": {
          "filter": {
            "name_edge_ngram": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 15
            }
          },
          "analyzer": {
            "name_autocomplete_index": {
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "name_edge_ngram"
              ]
            },
            "name_autocomplete_search": {
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
            "analyzer": "name_autocomplete_index",
            "search_analyzer": "name_autocomplete_search"
          }
        }
      }
    }

Sau khi reindex và xác minh, alias có thể được chuyển sang index mới bằng một alias update request nguyên tử. Cách chuyển alias cụ thể phụ thuộc tên alias và quy trình deploy của ứng dụng.

## 23. Kiểm thử chất lượng autocomplete

Một truy vấn autocomplete hợp lệ về cú pháp chưa chắc tạo trải nghiệm tốt. Cần chuẩn bị bộ query đại diện:

| Query đang nhập | Kết quả mong đợi |
|---|---|
| spr | Spring Data Elasticsearch |
| spring d | Spring Data Elasticsearch |
| spring data el | Spring Data Elasticsearch |
| key | Keyboard, Keychron |
| KB-10 | Mã sản phẩm có prefix KB-10 |
| ban phim | Các sản phẩm có tên phù hợp theo chính sách dấu |

Với mỗi query, kiểm tra:

- Document liên quan có xuất hiện không?
- Kết quả có đúng thứ tự từ mong muốn không?
- Từ cuối có thể còn dở không?
- Query một ký tự có quá nhiều kết quả không?
- Query dài hơn max_gram có hoạt động không?
- Tên có dấu và không dấu có đáp ứng yêu cầu không?
- Có kết quả sai do analyzer hoặc field không?
- Latency có ổn định với prefix phổ biến không?

Nên đo cả relevance và hiệu năng. Với autocomplete, thứ tự top 5 hoặc top 10 thường quan trọng hơn việc lấy tổng số document chính xác. Endpoint suggestion có thể không cần total hits.

## 24. Những lỗi thường gặp

### Dùng match thông thường cho token cuối chưa hoàn chỉnh

Match query không tự hiểu token cuối là prefix. Nếu người dùng nhập elas còn document có elasticsearch, cần search_as_you_type, edge n-gram, phrase_prefix hoặc prefix query phù hợp.

### Quên query các sub-field shingle

Chỉ query field gốc có thể bỏ qua tín hiệu cụm từ mà _2gram và _3gram cung cấp. Dùng multi_match bool_prefix trên các field được thiết kế cho search_as_you_type.

### Query _index_prefix trực tiếp trong mọi trường hợp

_index_prefix là sub-field nội bộ phục vụ tối ưu prefix cho search_as_you_type. Thông thường query trên field gốc và shingle sub-field bằng bool_prefix đã là cách sử dụng dự kiến.

### Dùng edge n-gram ở cả index và search analyzer

Query có thể bị tách thành nhiều tiền tố, tạo semantics rộng và khó kiểm soát. Thường chỉ tạo n-gram khi index và dùng search analyzer chuẩn hóa thông thường.

### Chọn min_gram quá lớn

Người dùng nhập ít ký tự hơn min_gram sẽ không tìm thấy kết quả. Chọn giá trị theo trải nghiệm mong muốn.

### Chọn max_gram quá nhỏ

Token dài hơn max_gram có thể không có term đầy đủ trong index edge n-gram. Cần tăng giới hạn hợp lý hoặc kết hợp field full-text thông thường.

### Dùng n-gram thay cho edge n-gram mà không có lý do

N-gram tạo các chuỗi con ở nhiều vị trí, có thể làm index lớn và khớp những phần giữa từ không mong muốn. Với prefix từ đầu token, edge n-gram thường phù hợp hơn.

### Nghĩ edge n-gram bảo đảm thứ tự cụm từ

Edge n-gram tạo tiền tố của từng token; nó không tự bảo đảm các từ xuất hiện liền nhau theo thứ tự. Dùng shingle, phrase query hoặc search_as_you_type khi thứ tự quan trọng.

### Dùng completion suggester cho full-text search tổng quát

Completion phù hợp với danh sách gợi ý được chuẩn bị trước. Nếu cần tìm document trong nội dung dài và nhiều field, search_as_you_type hoặc full-text query phù hợp hơn.

### Không reindex sau khi thay analyzer

Document đã index không tự có token mới. Cần reindex để áp dụng analyzer mới lên dữ liệu hiện có.

### Không giới hạn kết quả và request

Prefix ngắn có thể khớp rất nhiều document. Giới hạn size, query length, concurrency và debounce để bảo vệ cluster.

## 25. Quy trình lựa chọn giải pháp

Khi thiết kế ô tìm kiếm, có thể quyết định theo các bước:

1. Xác định dữ liệu là văn bản tự do, tên trong danh sách hay mã định danh.
2. Xác định người dùng cần tìm một document hay chọn một gợi ý đã được biên tập.
3. Nếu là full-text search-as-you-type thông thường, thử search_as_you_type.
4. Nếu cần min/max prefix và analyzer riêng, thử edge n-gram với index/search analyzer tách biệt.
5. Nếu cần cụm từ theo thứ tự và chỉ term cuối chưa hoàn chỉnh, đánh giá match_phrase_prefix.
6. Nếu cần prefix trên mã hoặc keyword, dùng prefix query trên field keyword phù hợp.
7. Nếu cần gợi ý từ danh sách cố định, đánh giá completion suggester.
8. Xác định analyzer, lowercase, folding, dấu và ngôn ngữ.
9. Thiết kế query và boost để kết quả phù hợp nhất đứng đầu.
10. Kiểm tra prefix ngắn, prefix dài, từ nhiều thành phần và trường hợp thiếu dữ liệu.
11. Đo kích thước index, tốc độ ingest và latency query.
12. Lên kế hoạch reindex khi mapping/analyzer thay đổi.

## Kết luận

Search-as-you-type giúp tìm document khi người dùng đang nhập dở từ hoặc cụm từ. Field type search_as_you_type của Elasticsearch tự tạo field gốc, shingle sub-field và index-prefix sub-field; cách truy vấn thường dùng là multi_match với type bool_prefix trên field gốc cùng các field _2gram và _3gram. Cách này phù hợp với nhu cầu tìm kiếm toàn văn phổ biến và giảm công việc tự thiết kế analyzer.

Edge n-gram cho phép kiểm soát min_gram, max_gram và analyzer. Hãy tạo tiền tố ở index time, dùng search analyzer chuẩn hóa thông thường ở search time, và cân nhắc kích thước index khi chọn khoảng gram. Edge n-gram không tự bảo đảm thứ tự cụm từ, vì vậy có thể cần kết hợp shingle hoặc phrase query. Với mã định danh, prefix trên keyword thường phù hợp hơn; với danh sách gợi ý chuyên biệt, completion suggester là lựa chọn đáng cân nhắc. Quyết định cuối cùng nên dựa trên semantics người dùng cần, mapping/analyzer thực tế, chất lượng top results và benchmark ở quy mô dữ liệu dự kiến.
