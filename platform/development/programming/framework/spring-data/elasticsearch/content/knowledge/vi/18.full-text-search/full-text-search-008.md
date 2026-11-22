# Fuzzy query, fuzziness và kiểm soát lỗi chính tả

## 1. Fuzzy search giải quyết vấn đề gì?

Khi người dùng tìm kiếm, họ có thể gõ sai một vài ký tự, đảo vị trí hai ký tự liền nhau hoặc bỏ sót một ký tự. Nếu truy vấn chỉ yêu cầu khớp chính xác, những lỗi nhỏ này có thể khiến ứng dụng không trả về kết quả dù document mong muốn vẫn tồn tại.

Ví dụ, index chứa tên sản phẩm:

~~~text
Wireless Headphones
Bluetooth Speaker
Mechanical Keyboard
~~~

Người dùng nhập `wirless headphones`. Từ `wirless` bị thiếu một ký tự so với `wireless`. Một truy vấn chỉ khớp chính xác có thể không tìm thấy sản phẩm đầu tiên. Fuzzy matching cho phép Elasticsearch tìm các term gần với từ người dùng nhập trong một khoảng sai khác được giới hạn.

Trong Elasticsearch, khả năng này thường được cấu hình qua:

- `fuzzy` query: truy vấn term-level tìm những term gần giống với một term chỉ định.
- `match` query với `fuzziness`: tìm kiếm toàn văn, phân tích chuỗi truy vấn rồi áp dụng fuzzy matching cho các term phù hợp.
- `multi_match` với `fuzziness`: mở rộng tìm kiếm fuzzy trên nhiều field văn bản trong những kiểu multi-match được hỗ trợ.

Fuzzy search giúp truy vấn chịu lỗi chính tả tốt hơn. Nó không tự sửa chuỗi người dùng nhập và cũng không bảo đảm kết quả gần nhất về mặt ngữ nghĩa luôn đứng đầu.

## 2. Edit distance là gì?

Fuzzy matching dựa trên **edit distance**: số thao tác chỉnh sửa ký tự tối thiểu cần thực hiện để biến một term thành term khác.

Các thao tác cơ bản gồm:

| Thao tác | Ví dụ | Số edit |
|---|---|---:|
| Thay thế một ký tự | `cat` → `bat` | 1 |
| Xóa một ký tự | `black` → `lack` | 1 |
| Chèn một ký tự | `sic` → `sick` | 1 |
| Đảo hai ký tự liền kề | `act` → `cat` | 1 khi bật transpositions |

Ví dụ so sánh:

- `wireless` và `wirless`: cần chèn ký tự `e`, edit distance bằng 1.
- `headphones` và `headphnoes`: hai ký tự liền kề bị đảo chỗ, được tính là một edit khi transpositions được bật.
- `keyboard` và `keyboarx`: thay một ký tự, edit distance bằng 1.
- `phone` và `phones`: cần chèn một ký tự, edit distance bằng 1.

Elasticsearch hỗ trợ fuzzy matching dựa trên edit distance. Với tùy chọn transpositions mặc định bật, việc đổi chỗ hai ký tự liền kề được tính là một thay đổi. Nếu tắt tùy chọn này, thao tác đảo chỗ được tính theo cách nghiêm ngặt hơn.

Edit distance chỉ đo độ khác nhau về ký tự. Hai từ có khoảng cách nhỏ chưa chắc đồng nghĩa hoặc có liên quan nghiệp vụ. Vì vậy, fuzzy search phù hợp để chịu lỗi gõ sai, không thay thế synonym, semantic search hay logic xếp hạng theo nghiệp vụ.

## 3. Tham số fuzziness

`fuzziness` xác định số edit tối đa được phép giữa term truy vấn và term được lập chỉ mục.

Các giá trị thường dùng:

- `0`: khớp chính xác, không cho phép chỉnh sửa.
- `1`: cho phép tối đa một edit.
- `2`: cho phép tối đa hai edit.
- `AUTO`: Elasticsearch tự chọn khoảng cách dựa trên độ dài term.

Với cấu hình mặc định tương đương `AUTO:3,6`, quy tắc theo độ dài term là:

| Độ dài term | Edit tối đa |
|---|---:|
| 0 đến 2 ký tự | 0, phải khớp chính xác |
| 3 đến 5 ký tự | 1 |
| Trên 5 ký tự | 2 |

Ví dụ:

| Term tìm kiếm | Độ dài | Fuzziness theo AUTO |
|---|---:|---:|
| `ki` | 2 | 0 |
| `cat` | 3 | 1 |
| `phone` | 5 | 1 |
| `wireless` | 8 | 2 |
| `elasticsearch` | 13 | 2 |

`AUTO` thường là lựa chọn hợp lý để bắt đầu vì từ ngắn được bảo vệ khỏi việc mở rộng quá rộng, trong khi từ dài có thể chịu được nhiều lỗi hơn.

Có thể chỉ định ngưỡng riêng theo dạng `AUTO:low,high`. Ví dụ, `AUTO:4,7` điều chỉnh các ngưỡng độ dài để quyết định khi nào cho phép một hoặc hai edit. Khi thay đổi ngưỡng, hãy kiểm tra với dữ liệu và cách nhập thực tế của người dùng.

Không nên mặc định đặt `fuzziness: 2` cho mọi truy vấn. Với từ ngắn, hai edit có thể tạo ra quá nhiều biến thể và làm tăng số kết quả không liên quan.

## 4. Fuzzy query: truy vấn term-level

`fuzzy` là một term-level query. Nó tìm document có term trong field gần với giá trị truy vấn theo edit distance.

Ví dụ REST API:

~~~http
GET /products/_search
{
  "query": {
    "fuzzy": {
      "sku": {
        "value": "WIRLESS",
        "fuzziness": "AUTO",
        "max_expansions": 25,
        "prefix_length": 1,
        "transpositions": true
      }
    }
  }
}
~~~

Ý nghĩa:

- `sku`: field được tìm kiếm.
- `value`: term người dùng nhập.
- `fuzziness`: edit distance tối đa hoặc chế độ tự động.
- `max_expansions`: giới hạn số biến thể term được tạo.
- `prefix_length`: số ký tự đầu phải giữ nguyên.
- `transpositions`: cho phép tính việc đảo hai ký tự liền kề như một edit.

`fuzzy` query tạo ra các term mở rộng trong giới hạn fuzziness, sau đó tìm document chứa một trong những term đó. Vì vậy, số lượng term trong dictionary và số expansion có ảnh hưởng đến chi phí thực thi.

### Ví dụ với field keyword

Giả sử mapping có field mã người dùng hoặc mã sản phẩm:

~~~json
{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

Truy vấn fuzzy trên `sku` phù hợp khi mã được lưu thành một term keyword duy nhất. Với tên sản phẩm gồm nhiều từ, `match` có fuzziness thường phù hợp hơn vì nó phân tích chuỗi tìm kiếm thành các token.

Giả sử index có SKU `WIRELESS` nhưng người dùng nhập `WIRLESS`; fuzzy query có thể tìm term gần giống đó. Nếu keyword field có normalizer, kết quả còn phụ thuộc cách chuẩn hóa đã cấu hình.

Fuzzy query không tự phân tích toàn bộ câu tìm kiếm như match query. Nếu đưa một chuỗi nhiều từ vào `fuzzy` query, Elasticsearch xử lý nó như giá trị term cho field, không tự biến mỗi từ thành một điều kiện full-text độc lập.

## 5. Match query với fuzziness: lựa chọn phổ biến cho tìm kiếm toàn văn

Với field `text`, ứng dụng thường cần tìm một câu hoặc nhiều từ. `match` query phân tích chuỗi truy vấn bằng search analyzer rồi tạo fuzzy matching cho từng term phù hợp.

Ví dụ:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": {
        "query": "wirless headphones",
        "fuzziness": "AUTO",
        "prefix_length": 1,
        "max_expansions": 25,
        "fuzzy_transpositions": true
      }
    }
  }
}
~~~

Ở đây:

1. Elasticsearch phân tích chuỗi `wirless headphones` thành các token theo analyzer.
2. Với các term được hỗ trợ, query tạo những biến thể trong giới hạn fuzziness.
3. Các document khớp được trả về theo logic của match query và điểm liên quan.

`match` có thêm các tùy chọn điều khiển cách kết hợp token:

~~~json
{
  "match": {
    "name": {
      "query": "wirless headphones",
      "fuzziness": "AUTO",
      "operator": "and",
      "minimum_should_match": "75%",
      "prefix_length": 1,
      "max_expansions": 25,
      "fuzzy_transpositions": true
    }
  }
}
~~~

- `operator: "or"` cho phép khớp một hoặc nhiều token; đây là mặc định thông dụng.
- `operator: "and"` yêu cầu tất cả token theo logic AND.
- `minimum_should_match` quy định số lượng hoặc tỷ lệ clause cần khớp.
- `prefix_length`, `max_expansions` và `fuzzy_transpositions` kiểm soát fuzzy expansion.

Cần phân biệt hai tham số transposition:

- Trong `fuzzy` query, tên tham số là `transpositions`.
- Trong `match` query, tên tham số là `fuzzy_transpositions`.

Không sao chép nhầm tên giữa hai loại query.

### Fuzzy matching theo từng token

Với truy vấn `wirless headphones`, lỗi nằm ở token `wirless`. Token `headphones` có thể khớp chính xác. `match` query áp dụng fuzziness cho các term sau khi phân tích, vì vậy cách kết hợp `OR`, `AND` hoặc `minimum_should_match` ảnh hưởng kết quả.

Nếu dùng `operator: "or"`, document có thể khớp chỉ vì một token được tìm thấy. Nếu dùng `operator: "and"`, tất cả token cần thỏa mãn. Lựa chọn này phải phản ánh yêu cầu tìm kiếm của giao diện.

## 6. Multi-match query với fuzziness

Khi muốn tìm trên nhiều field văn bản, có thể dùng `multi_match`:

~~~json
{
  "multi_match": {
    "query": "wirless headphones",
    "fields": [
      "name^3",
      "description",
      "brandName^2"
    ],
    "type": "best_fields",
    "fuzziness": "AUTO",
    "prefix_length": 1,
    "max_expansions": 25
  }
}
~~~

Trong ví dụ:

- `name^3` tăng trọng số field tên sản phẩm.
- `description` được tìm với trọng số mặc định.
- `brandName^2` ưu tiên field thương hiệu hơn description.
- `best_fields` chọn kết quả dựa trên field có mức khớp tốt.
- `fuzziness` cho phép chịu lỗi chính tả trên các term được hỗ trợ.

Không phải mọi kiểu `multi_match` đều hỗ trợ fuzziness. Ví dụ, các kiểu phrase và cross-fields có những giới hạn riêng. Hãy xác nhận loại multi-match đang dùng trước khi thêm tham số fuzziness.

Fuzzy matching trên nhiều field có thể tạo nhiều expansion hơn so với một field. Vì vậy, nên giới hạn số field, dùng boost có chủ đích và đo hiệu năng trên tập dữ liệu thực tế.

## 7. Kiểm soát fuzzy expansion

Fuzzy matching có thể tạo ra nhiều biến thể term. Ba tham số quan trọng giúp giới hạn phạm vi tìm kiếm là `fuzziness`, `prefix_length` và `max_expansions`.

### prefix_length

`prefix_length` là số ký tự đầu tiên phải khớp chính xác, không được thay thế trong quá trình fuzzy expansion.

Ví dụ truy vấn `wireless`:

- `prefix_length: 0`: không yêu cầu ký tự đầu khớp.
- `prefix_length: 1`: ký tự `w` phải giống nhau.
- `prefix_length: 2`: hai ký tự đầu `wi` phải giống nhau.

Tăng prefix length có thể giảm số expansion và cải thiện hiệu năng. Đổi lại, nếu người dùng gõ sai ngay từ đầu từ, document đúng có thể không được tìm thấy.

Ví dụ, với `wireless` và `prefix_length: 1`, term `vireless` không khớp vì ký tự đầu khác nhau, dù khoảng cách chỉnh sửa chỉ là một.

### max_expansions

`max_expansions` giới hạn số term biến thể mà query được phép tạo cho một term tìm kiếm. Giá trị mặc định là 50.

Không nên tăng giá trị này một cách tùy tiện. Khi `prefix_length` bằng 0 và `max_expansions` lớn, số term được xem xét có thể tăng mạnh và làm query chậm.

Một cấu hình bắt đầu có thể là:

~~~json
{
  "fuzziness": "AUTO",
  "prefix_length": 1,
  "max_expansions": 25,
  "transpositions": true
}
~~~

Đây chỉ là điểm bắt đầu để thử nghiệm, không phải cấu hình tối ưu cho mọi index. Hãy đo thời gian tìm kiếm, số hit và độ phù hợp của kết quả trước khi điều chỉnh.

### transpositions

Khi `transpositions` bật, đổi chỗ hai ký tự liền nhau được tính là một edit. Đây là trường hợp gõ nhầm khá phổ biến, ví dụ `teh` thay vì `the`.

- `true`: cho phép chuyển vị trí hai ký tự liền kề, mặc định.
- `false`: không áp dụng quy tắc chuyển vị như một edit đơn.

Trong `match` query, tham số tương ứng là `fuzzy_transpositions`.

## 8. Kết hợp fuzzy với bool query và filter

Tìm kiếm toàn văn thường cần kết hợp fuzzy với các điều kiện nghiệp vụ. Ví dụ tìm tên sản phẩm có lỗi chính tả, chỉ lấy sản phẩm đang hoạt động và thuộc danh mục audio:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wirless headphones",
            "fuzziness": "AUTO",
            "prefix_length": 1,
            "max_expansions": 25
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "term": {
          "active": true
        }
      }
    ]
  }
}
~~~

`must` chứa điều kiện full-text fuzzy và có thể ảnh hưởng score. `filter` giới hạn danh mục và trạng thái mà không tham gia tính điểm liên quan.

Cách kết hợp này giúp fuzzy search mở rộng khả năng chịu lỗi trong phần văn bản, trong khi các điều kiện chính xác vẫn được áp dụng cho field phân loại hoặc trạng thái.

Không nên đặt fuzzy query vào mọi field chỉ vì muốn tìm kiếm dễ dãi. Những field như trạng thái, mã định danh, số tiền hoặc ngày tháng thường cần điều kiện chính xác hoặc range query phù hợp.

## 9. Fuzziness và analyzer

Với `match` query, Elasticsearch phân tích chuỗi tìm kiếm trước khi fuzzy matching. Vì vậy, analyzer có ảnh hưởng trực tiếp đến token được đem so sánh.

Ví dụ analyzer có thể:

- Chuyển chữ hoa thành chữ thường.
- Tách câu thành token.
- Loại bỏ stop words.
- Chuẩn hóa dấu hoặc ký tự theo cấu hình.
- Stemming để đưa các biến thể từ về dạng gốc.

Nếu analyzer loại bỏ một token hoặc biến đổi token, fuzzy matching sẽ hoạt động trên kết quả phân tích chứ không phải nguyên văn chuỗi ban đầu.

Một số trường hợp có synonym hoặc nhiều token cùng vị trí có thể không áp dụng fuzzy expansion theo cách thông thường. Elasticsearch tạo một dạng synonym query đặc biệt cho các trường hợp này, và dạng đó không hỗ trợ fuzzy expansion cho những term tương ứng.

Vì vậy, nếu fuzzy search không tìm được kết quả như dự kiến:

1. Kiểm tra mapping của field.
2. Dùng Analyze API để xem token sau phân tích.
3. Kiểm tra synonym filter và stemming filter.
4. Thử một query match không fuzziness để tách biệt lỗi analyzer với lỗi fuzzy.
5. Sau đó thử `fuzziness: 1` hoặc `AUTO` trên một term đơn giản.

Với dữ liệu tiếng Việt, cần đặc biệt chú ý cách chuẩn hóa Unicode, chữ hoa/chữ thường, dấu và analyzer. Fuzzy matching không tự hiểu rằng hai cách viết có dấu và không dấu là tương đương. Nếu nghiệp vụ cần hỗ trợ cả hai cách viết, hãy thiết kế analyzer hoặc field chuẩn hóa riêng và thử nghiệm với dữ liệu thực.

## 10. Fuzzy query không phải công cụ sửa chính tả

Fuzzy query tìm document có term gần với chuỗi truy vấn. Nó không trả về một từ đã được sửa để hiển thị cho người dùng.

Ví dụ, người dùng nhập `wirless` và query trả về document có tên `Wireless Headphones`. Điều đó không có nghĩa Elasticsearch đã biến `wirless` thành `wireless` trong request hoặc response.

Nếu giao diện cần hiển thị gợi ý kiểu “Có phải bạn muốn tìm wireless?”, hãy sử dụng chức năng suggester phù hợp:

- **Term suggester:** đề xuất các term thay thế dựa trên từ điển term của field.
- **Phrase suggester:** tạo gợi ý cho cụm từ, có thể dùng n-gram hoặc thống kê ngôn ngữ để chọn cụm hợp lý.
- **Completion suggester:** hỗ trợ autocomplete; có thể cấu hình fuzzy để chịu lỗi khi người dùng nhập prefix.

Có thể kết hợp hai luồng:

1. Chạy tìm kiếm fuzzy để vẫn trả về kết quả khi người dùng gõ sai.
2. Nếu cần, chạy suggester để tạo đề xuất sửa chính tả.
3. Hiển thị gợi ý cho người dùng và cho phép họ chọn truy vấn mới.

Fuzzy matching tập trung vào việc tìm document. Suggester tập trung vào việc tạo các phương án từ hoặc cụm từ thay thế.

## 11. Sử dụng fuzzy query trong Spring Data Elasticsearch

Có thể sử dụng Query DSL với `@Query` trên repository. Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
    {
      "match": {
        "name": {
          "query": "?0",
          "fuzziness": "AUTO",
          "prefix_length": 1,
          "max_expansions": 25,
          "fuzzy_transpositions": true
        }
      }
    }
    """)
    List<Product> searchByNameWithTypoTolerance(String keyword);
}
~~~

`?0` là tham số đầu tiên của phương thức repository. Query method thay placeholder bằng giá trị truyền vào khi thực thi. Dùng `match` giúp phân tích từ khóa nhiều từ trước khi áp dụng fuzzy matching.

Nếu cần kiểm soát Query DSL bằng Java API Client, có thể tạo `NativeQuery`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public SearchHits<Product> searchWithFuzziness(
        ElasticsearchOperations operations,
        String keyword) {

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query(keyword)
                .fuzziness("AUTO")
                .prefixLength(1)
                .maxExpansions(25)
                .fuzzyTranspositions(true)
            )
        )
        .build();

    return operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
    );
}
~~~

Trong ví dụ này, Spring Data `NativeQuery` nhận query được xây dựng bằng các kiểu của Elasticsearch Java API Client. Các tên phương thức `prefixLength`, `maxExpansions` và `fuzzyTranspositions` tương ứng với các tham số của match query.

Nếu muốn dùng term-level fuzzy query thay vì full-text match, có thể xây dựng `fuzzy` clause bằng NativeQuery builder:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .fuzzy(f -> f
            .field("sku")
            .value(keyword)
            .fuzziness("AUTO")
            .prefixLength(1)
            .maxExpansions(25)
            .transpositions(true)
        )
    )
    .build();
~~~

Dùng ví dụ `fuzzy` cho một field keyword chứa một term, chẳng hạn mã hoặc username. Với câu tìm kiếm nhiều từ trên field text, `match` cùng fuzziness thường phù hợp hơn.

Các package và builder API phụ thuộc phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client trong dự án. Khi triển khai, hãy đối chiếu API của dependency đang dùng.

## 12. Fuzzy matching và độ liên quan

Fuzzy matching mở rộng tập term có thể khớp, nhưng không có nghĩa document gần nhất về edit distance luôn đứng đầu trong mọi trường hợp.

Elasticsearch còn tính điểm liên quan dựa trên query, tần suất term, độ dài field và các yếu tố khác. Một document có nhiều term khớp hoặc có mức liên quan cao có thể xếp trên document chỉ khớp một biến thể fuzzy.

Có thể kết hợp fuzzy với:

- `bool.must` để tìm nội dung chính.
- `bool.filter` để lọc điều kiện chính xác.
- `boost` để ưu tiên field quan trọng.
- `multi_match` để tìm trên nhiều field.
- Sort theo field nghiệp vụ nếu thứ tự không chỉ dựa trên score.

Không nên dùng sort cố định theo tên hoặc giá nếu mục tiêu chính là xếp hạng theo mức liên quan, vì sort field có thể làm kết quả không còn được sắp xếp theo score như mong đợi.

Khi đánh giá fuzzy search, hãy tạo tập truy vấn gồm:

- Từ viết đúng.
- Thiếu ký tự.
- Thừa ký tự.
- Sai một ký tự.
- Đảo hai ký tự liền kề.
- Sai ký tự đầu.
- Từ ngắn.
- Từ dài.
- Cụm từ có nhiều token và một token bị sai.

Quan sát cả recall (có tìm được document mong muốn không) lẫn precision (có trả về quá nhiều document không liên quan không). Chọn fuzziness và expansion dựa trên cân bằng giữa hai mục tiêu.

## 13. Giới hạn hiệu năng và cấu hình cluster

Fuzzy query tạo các biến thể term và có thể tốn tài nguyên hơn truy vấn chính xác. Elasticsearch xem fuzzy query là loại truy vấn có chi phí cao. Nếu cluster đặt `search.allow_expensive_queries` thành `false`, fuzzy query có thể không được thực thi.

Một số nguyên tắc kiểm soát:

- Dùng `AUTO` làm điểm bắt đầu thay vì luôn cho phép hai edit.
- Giữ `max_expansions` ở mức vừa phải.
- Cân nhắc `prefix_length` từ 1 hoặc lớn hơn nếu dữ liệu cho phép.
- Không chạy fuzzy trên quá nhiều field cùng lúc.
- Không fuzzy trên các field không cần chịu lỗi chính tả.
- Giới hạn kích thước trang.
- Theo dõi latency, CPU và số lượng hit khi thử nghiệm.
- Kiểm tra cấu hình `search.allow_expensive_queries` nếu query bị từ chối.

Không nên tăng `max_expansions` để cố lấy thêm kết quả mà chưa hiểu vì sao query hiện tại bỏ sót document. Hãy kiểm tra analyzer, mapping, edit distance và prefix trước.

## 14. Những lỗi thường gặp

**Đặt fuzziness quá cao.** Với từ ngắn, nhiều biến thể có thể khớp và trả về nhiều kết quả không liên quan. Dùng `AUTO` hoặc giới hạn một edit khi phù hợp.

**Dùng fuzzy query cho câu nhiều từ.** `fuzzy` là term-level query; dùng `match` với fuzziness nếu cần phân tích nhiều token.

**Nhầm `transpositions` và `fuzzy_transpositions`.** `fuzzy` query dùng `transpositions`; `match` query dùng `fuzzy_transpositions`.

**Tăng `max_expansions` quá lớn.** Nhiều expansion làm tăng chi phí, đặc biệt khi `prefix_length` bằng 0.

**Đặt prefix length quá dài.** Nếu ký tự đầu bị gõ sai, query có thể bỏ qua term mong muốn. Chọn prefix dựa trên kiểu lỗi người dùng thường gặp.

**Dùng fuzzy trên field không phù hợp.** Field số, ngày hoặc trạng thái nghiệp vụ thường cần truy vấn đúng kiểu. Fuzzy phù hợp với term văn bản hoặc keyword dạng chuỗi.

**Bỏ qua analyzer.** Analyzer có thể thay đổi hoặc loại bỏ token trước khi fuzzy matching diễn ra. Kiểm tra token thực tế bằng Analyze API.

**Cho rằng fuzzy tự sửa từ khóa.** Query trả về document phù hợp; nếu muốn gợi ý từ đúng, hãy dùng suggester.

**Bật fuzzy cho mọi tìm kiếm.** Không phải mọi màn hình đều cần chịu lỗi chính tả. Cân nhắc chỉ bật sau khi truy vấn chính xác không có kết quả hoặc dùng một chiến lược kết hợp có kiểm soát.

**Không kiểm tra `search.allow_expensive_queries`.** Cấu hình cluster có thể chặn fuzzy query. Hãy kiểm tra chính sách cluster khi query bị từ chối.

## 15. Quy trình thiết kế tìm kiếm chịu lỗi chính tả

Có thể triển khai theo các bước:

1. Xác định field nào là nội dung người dùng thường nhập sai, ví dụ tên sản phẩm hoặc thương hiệu.
2. Kiểm tra mapping và analyzer của các field đó.
3. Bắt đầu với `match` query và `fuzziness: AUTO`.
4. Đặt `prefix_length` và `max_expansions` ở mức phù hợp với dữ liệu.
5. Kết hợp filter chính xác cho danh mục, trạng thái hoặc quyền truy cập.
6. Thử các kiểu lỗi gõ phổ biến, bao gồm lỗi ký tự đầu và lỗi đảo ký tự.
7. Đánh giá độ chính xác và độ bao phủ của kết quả.
8. Chỉ dùng `multi_match` nếu thật sự cần tìm trên nhiều field.
9. Dùng suggester riêng nếu giao diện cần đề xuất từ hoặc cụm từ đã sửa.
10. Theo dõi hiệu năng và điều chỉnh cấu hình dựa trên truy vấn thực tế.

## Kết luận

Fuzzy query giúp Elasticsearch tìm các term gần với term người dùng nhập dựa trên edit distance. `fuzziness` đặt giới hạn sai khác; `AUTO` tự điều chỉnh theo độ dài term. `prefix_length`, `max_expansions` và tùy chọn transpositions giúp cân bằng khả năng chịu lỗi với hiệu năng.

Với một term đơn trên field keyword, có thể dùng `fuzzy` query. Với tìm kiếm toàn văn nhiều từ, `match` query có fuzziness thường là lựa chọn phù hợp hơn vì Elasticsearch phân tích chuỗi truy vấn trước khi mở rộng term. Trong Spring Data Elasticsearch, có thể khai báo Query DSL bằng `@Query` hoặc xây dựng `NativeQuery` rồi thực thi qua `ElasticsearchOperations`.

Fuzzy matching chỉ giúp tìm được document khi có lỗi gõ. Nếu sản phẩm cần hiển thị cách viết đề xuất, hãy bổ sung term, phrase hoặc completion suggester. Thiết kế tốt cần thử với lỗi nhập thực tế, kiểm soát expansion và theo dõi chất lượng kết quả lẫn hiệu năng.

## Tài liệu tham khảo

- [Elasticsearch — Fuzzy query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-fuzzy-query)
- [Elasticsearch — Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
- [Elasticsearch — Fuzziness and edit distance](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/common-options#fuzziness)
- [Elasticsearch — Search suggesters](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters)
- [Spring Data Elasticsearch — Repositories and Query Methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
