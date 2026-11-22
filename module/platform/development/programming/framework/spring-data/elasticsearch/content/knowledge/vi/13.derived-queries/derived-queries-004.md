# In, NotIn và khác biệt theo kiểu keyword hoặc text

Trong Spring Data Elasticsearch, các từ khóa truy vấn dẫn xuất In và NotIn cho phép lọc document theo một tập giá trị. Ví dụ, có thể tìm sản phẩm thuộc một trong nhiều danh mục hoặc loại ra những sản phẩm thuộc một số trạng thái nhất định.

Điều cần hiểu kỹ là In và NotIn thường được chuyển thành truy vấn theo terms của Elasticsearch. Truy vấn terms so khớp các term đã được lập chỉ mục; nó không hoạt động giống phép so sánh toàn bộ chuỗi trong Java hay SQL trong mọi trường hợp. Vì vậy kết quả phụ thuộc trực tiếp vào mapping của field:

- Với field keyword, mỗi giá trị thường được lập chỉ mục như một giá trị nguyên vẹn. In gần với phép kiểm tra field có nằm trong tập giá trị hay không.
- Với field text, nội dung được analyzer tách thành token. In có thể khớp một token riêng lẻ thay vì cả câu hoặc chuỗi ban đầu.

Hiểu khác biệt này giúp tránh dùng In trên field text khi mục tiêu thật sự là so sánh tên đầy đủ, đồng thời giúp chọn đúng query khi cần tìm kiếm toàn văn.

## 1. Ý nghĩa của In và NotIn

Trong một repository Spring Data Elasticsearch, có thể khai báo phương thức như sau:

~~~java
import java.util.Collection;
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategoryIn(Collection<String> categories);

    List<Product> findByCategoryNotIn(Collection<String> categories);
}
~~~

Spring Data phân tích tên phương thức để xác định entity property, toán tử và kiểu tham số. Trong ví dụ:

- findByCategoryIn tìm document có category khớp với ít nhất một giá trị trong collection.
- findByCategoryNotIn tìm document không khớp với bất kỳ giá trị nào trong collection.

Về ý nghĩa logic, nếu tập giá trị truyền vào là A, In tương ứng với điều kiện giá trị field thuộc A. NotIn tương ứng với điều kiện giá trị field không thuộc A.

Đây là cách diễn đạt gần với phép IN trong SQL, nhưng cần nhớ Elasticsearch truy vấn document đã lập chỉ mục và có thể có field nhiều giá trị, field thiếu hoặc field text đã phân tích. Những trường hợp đó làm kết quả khác với cách suy nghĩ về một cột SQL đơn trị.

## 2. In thường được thực hiện bằng terms query

Elasticsearch có terms query để tìm document mà field khớp với ít nhất một trong các giá trị được cung cấp.

Ví dụ REST API:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "terms": {
      "category": ["books", "electronics", "home"]
    }
  }
}
~~~

Truy vấn này khớp document có category là books, electronics hoặc home. Có thể hiểu terms query như một phép OR giữa các giá trị term trên cùng field.

Khi dùng repository method findByCategoryIn, Spring Data Elasticsearch có thể tạo truy vấn terms tương ứng. Chi tiết triển khai và kiểu query được tạo có thể thay đổi theo release train, vì vậy khi cần xác nhận hành vi chính xác của phiên bản đang dùng, hãy kiểm tra request thực tế hoặc bật logging phù hợp.

Terms query là truy vấn term-level. Nó không giống match query:

| Truy vấn | Cách xử lý giá trị tìm kiếm | Mục đích |
|---|---|---|
| terms | So khớp các term được truyền vào | Kiểm tra một field khớp một trong nhiều giá trị |
| term | So khớp một term | Tìm giá trị chính xác hoặc token chính xác |
| match | Phân tích giá trị tìm kiếm bằng analyzer của field | Tìm kiếm toàn văn |
| match_phrase | Phân tích văn bản và kiểm tra cụm từ theo thứ tự, vị trí phù hợp | Tìm cụm từ |

Do đó, chọn In hay một phương thức tìm kiếm toàn văn phải dựa vào kiểu dữ liệu và ý nghĩa của field.

## 3. Keyword: phù hợp cho In và NotIn theo giá trị nguyên vẹn

Field keyword được thiết kế cho dữ liệu cần so khớp chính xác, ví dụ:

- Mã sản phẩm.
- Mã khách hàng.
- Trạng thái đơn hàng.
- Tên danh mục.
- Mã quốc gia.
- Nhãn hoặc tag.

Mapping ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Với mapping này, document:

~~~json
{
  "category": "electronics",
  "status": "active"
}
~~~

được lập chỉ mục với các giá trị keyword tương ứng. Repository method:

~~~java
List<Product> findByCategoryIn(Collection<String> categories);
~~~

với categories chứa books và electronics sẽ trả về sản phẩm có category bằng một trong hai giá trị đó.

Tương tự:

~~~java
List<Product> findByStatusNotIn(Collection<String> statuses);
~~~

với statuses chứa archived và deleted sẽ loại các document có status khớp một trong hai giá trị.

### 3.1. Keyword là so khớp chính xác, không phải tìm chuỗi con

Giả sử field category có giá trị electronics. Truy vấn In với electronics có thể khớp; truy vấn với lectro hoặc electronic không khớp chỉ vì đó là một phần của chuỗi.

Tương tự, nếu không có normalizer, keyword thường phân biệt chữ hoa và chữ thường:

~~~text
Giá trị được index: Electronics
Giá trị query:      electronics
Kết quả:            không khớp theo exact term
~~~

Nếu nghiệp vụ muốn không phân biệt chữ hoa/chữ thường, có thể chuẩn hóa dữ liệu trước khi ghi hoặc cấu hình normalizer cho keyword field. Cần bảo đảm cách chuẩn hóa lúc ghi và lúc truy vấn nhất quán.

### 3.2. Keyword với normalizer

Ví dụ settings và mapping khai báo normalizer chuyển chữ về chữ thường:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Khi đó các giá trị category được chuẩn hóa theo normalizer. Truy vấn term-level trên keyword field có normalizer được Elasticsearch xử lý theo quy tắc normalizer của field, giúp so khớp không phân biệt hoa thường trong trường hợp này.

Normalizers phải được khai báo khi tạo mapping phù hợp. Nếu index hiện tại đã có field keyword mà không có normalizer, chỉ thêm annotation trong Java không tự thay đổi mapping đang tồn tại.

## 4. Text: In không đồng nghĩa với so sánh cả chuỗi

Field text được thiết kế cho tìm kiếm toàn văn. Khi lập chỉ mục, analyzer xử lý chuỗi thành các token. Ví dụ với analyzer standard, văn bản:

~~~text
Wireless Mechanical Keyboard
~~~

có thể được phân tích thành các term:

~~~text
wireless
mechanical
keyboard
~~~

Terms query không chạy analyzer như match query. Nó so khớp term được truyền vào với term đã có trong inverted index.

Giả sử entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    // other fields
}
~~~

Và document có name là Wireless Mechanical Keyboard. Phương thức:

~~~java
List<Product> findByNameIn(Collection<String> names);
~~~

không nên được hiểu là tìm những sản phẩm có toàn bộ tên bằng một trong các chuỗi đưa vào theo cách so sánh chuỗi thông thường. Nếu tham số chứa Wireless Mechanical Keyboard, terms query có thể không tìm thấy vì term được index là các token riêng, không phải cả chuỗi đó.

Nếu tham số chứa wireless, truy vấn có thể khớp vì đó là một term đã được lập chỉ mục. Tùy analyzer, chữ hoa/thường và dấu câu trong dữ liệu gốc có thể đã được chuẩn hóa hoặc tách thành token khác.

### 4.1. Minh họa sự khác biệt

Giả sử document có name:

~~~text
Wireless Mechanical Keyboard
~~~

Và analyzer tạo ra ba token như trên:

| Giá trị truyền vào In | Kết quả có thể xảy ra | Lý do |
|---|---|---|
| wireless | Khớp | Trùng một term đã được index |
| keyboard | Khớp | Trùng một term đã được index |
| wireless, keyboard | Khớp | Ít nhất một term trong danh sách trùng |
| Wireless Mechanical Keyboard | Không khớp theo terms thông thường | Cả câu không phải một term đã được index |
| mechanical mouse | Không khớp chỉ vì có từ mechanical | Terms query nhận chuỗi này như một term nguyên vẹn, không tự tách thành hai từ |

Bảng này giả định analyzer tạo token lowercase như ví dụ. Analyzer thực tế có thể khác, nên hãy kiểm tra bằng API _analyze và mapping của index.

### 4.2. Khi cần tìm toàn văn trên text

Nếu yêu cầu là tìm các tên hoặc mô tả chứa từ/cụm từ người dùng nhập, hãy dùng match, match_phrase hoặc multi_match thay vì In.

Ví dụ match query:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Elasticsearch phân tích chuỗi tìm kiếm theo analyzer phù hợp và so khớp các token. Nếu cần tìm cụm từ theo thứ tự, dùng match_phrase:

~~~json
{
  "query": {
    "match_phrase": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Chọn loại truy vấn theo yêu cầu:

- Tập mã/trạng thái/danh mục: terms query trên keyword.
- Từ khóa trong nội dung: match hoặc multi_match trên text.
- Cụm từ cần giữ thứ tự: match_phrase trên text.
- Tên đầy đủ cần so khớp nguyên vẹn: dùng sub-field keyword.

## 5. Kết hợp text và keyword bằng multi-fields

Một trường văn bản thường cần cả tìm kiếm toàn văn và so khớp nguyên vẹn. Elasticsearch hỗ trợ multi-fields để lập chỉ mục cùng một giá trị theo nhiều cách.

Mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
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

Khi đó:

- name phục vụ match và match_phrase.
- name.keyword phục vụ terms, sort, aggregation và so khớp nguyên vẹn.

Ví dụ document:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Tìm toàn văn trên name:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Tìm theo danh sách tên đầy đủ trên name.keyword:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "terms": {
      "name.keyword": [
        "Wireless Mechanical Keyboard",
        "Compact Keyboard"
      ]
    }
  }
}
~~~

Nếu entity chỉ có property name, phương thức dẫn xuất findByNameIn thường truy vấn field được ánh xạ từ property name, không tự chuyển sang sub-field name.keyword. Khi cần truy vấn sub-field, hãy khai báo query tường minh hoặc thiết kế metadata/property phù hợp với phiên bản Spring Data đang dùng.

## 6. Dùng @Query khi cần chỉ định sub-field

Spring Data Elasticsearch hỗ trợ @Query để khai báo Elasticsearch query JSON cho repository method. Ví dụ, nếu muốn tìm tên đầy đủ qua name.keyword:

~~~java
import java.util.Collection;
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"terms\":{\"name.keyword\":?0}}")
    List<Product> findByExactNames(Collection<String> names);
}
~~~

Tham số ?0 được thay bằng tham số đầu tiên của method theo cơ chế binding của Spring Data Elasticsearch. Kiểm tra cú pháp binding collection trong đúng phiên bản của dự án; nếu cần kiểm soát query phức tạp hơn, có thể xây dựng NativeQuery hoặc query object bằng API được phiên bản đó hỗ trợ.

Không nên dùng một derived method trên property name rồi mặc định rằng Spring Data biết ý định truy vấn name.keyword. Property path trong repository bắt đầu từ mô hình Java; sub-field là chi tiết mapping Elasticsearch.

## 7. NotIn và ý nghĩa loại trừ

NotIn loại document có field khớp với một trong các giá trị bị loại. Ví dụ:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must_not": [
        {
          "terms": {
            "status": ["deleted", "archived"]
          }
        }
      ]
    }
  }
}
~~~

Truy vấn này lấy các document không khớp với status deleted hoặc archived.

### 7.1. Field thiếu có thể vẫn được trả về

Trong Elasticsearch, bool must_not loại các document khớp với query bên trong. Document không có field status không khớp terms query, do đó có thể vẫn xuất hiện trong kết quả NotIn.

Điểm này có thể khác cách người đọc kỳ vọng khi nghĩ theo một cột SQL có giá trị NULL. Nếu yêu cầu là chỉ lấy document có status tồn tại và không thuộc tập bị loại, cần thêm điều kiện exists:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "status"
          }
        }
      ],
      "must_not": [
        {
          "terms": {
            "status": ["deleted", "archived"]
          }
        }
      ]
    }
  }
}
~~~

Hãy xác định rõ nghiệp vụ có muốn giữ document thiếu field hay không. Không nên giả định NotIn tự động loại giá trị thiếu.

### 7.2. Field có nhiều giá trị

Elasticsearch cho phép một field có nhiều giá trị cùng kiểu mà không cần khai báo kiểu array riêng. Ví dụ:

~~~json
{
  "tags": ["sale", "office", "wireless"]
}
~~~

Với terms query trên tags, document khớp nếu có ít nhất một giá trị trong danh sách truyền vào. Với NotIn, document bị loại nếu có ít nhất một giá trị của field trùng tập bị loại.

Ví dụ:

| tags của document | Danh sách In | In | Danh sách NotIn | NotIn |
|---|---|---|---|---|
| sale, office | office, home | Có | blocked, deleted | Có |
| wireless, gaming | office, home | Không | gaming, deleted | Không |
| sale | sale | Có | sale | Không |
| không có tags | sale | Không | sale | Có thể có |

Trường hợp field thiếu vẫn phụ thuộc điều kiện exists và cách ứng dụng tạo query.

## 8. Kết hợp In với các điều kiện khác

Các query method có thể kết hợp In với điều kiện khác bằng And hoặc Or nếu tên phương thức và kiểu tham số phù hợp.

Ví dụ:

~~~java
List<Product> findByCategoryInAndStatus(
        Collection<String> categories,
        String status
);
~~~

Ý nghĩa: category phải thuộc danh sách đã truyền và status phải khớp giá trị được cung cấp.

Một ví dụ khác:

~~~java
List<Product> findByCategoryInAndPriceLessThan(
        Collection<String> categories,
        BigDecimal maxPrice
);
~~~

Phương thức lọc sản phẩm thuộc các danh mục được chọn và có giá nhỏ hơn ngưỡng.

Nếu cần phân trang, có thể dùng Pageable trong chữ ký repository method được Spring Data Elasticsearch hỗ trợ:

~~~java
Page<Product> findByCategoryIn(
        Collection<String> categories,
        Pageable pageable
);
~~~

Việc kết hợp toán tử, phân trang và kiểu trả về cần được kiểm tra theo phiên bản Spring Data Elasticsearch cụ thể. Với query phức tạp, nhiều nhánh bool hoặc điều kiện trên sub-field, query tường minh thường dễ kiểm soát hơn.

## 9. In và NotIn trên các kiểu field khác

In không chỉ áp dụng cho String. Nó có thể dùng với field số, boolean, date hoặc các kiểu khác nếu mapping và conversion phù hợp.

Ví dụ:

~~~java
List<Product> findByPriceIn(Collection<BigDecimal> prices);

List<Product> findByAvailableIn(Collection<Boolean> values);

List<Order> findByStatusIn(Collection<OrderStatus> statuses);
~~~

Với field số, terms query so khớp các giá trị số đã lập chỉ mục. Với boolean, nó so khớp true hoặc false. Với date, giá trị phải được chuyển đổi theo format mapping và kiểu thời gian được Spring Data hỗ trợ.

Với enum, cần xác định cách enum được chuyển thành dữ liệu lưu trữ. Nếu dữ liệu lưu tên enum như PAID, query phải cung cấp giá trị tương ứng. Nếu custom converter lưu mã như P, repository cần dùng conversion nhất quán với cách dữ liệu đã được ghi.

## 10. Những trường hợp cần tránh

### 10.1. Dùng In để tìm từ khóa trong đoạn văn

Nếu field là text, In thường không phải lựa chọn đúng để tìm câu hoặc cụm từ. Hãy dùng match hoặc match_phrase. Nếu mục tiêu là so sánh nguyên chuỗi, hãy dùng keyword sub-field.

### 10.2. Dùng keyword khi cần tìm nội dung tự nhiên

Field keyword không tự tách từ. Một truy vấn terms trên keyword chỉ khớp giá trị đã chuẩn hóa theo mapping. Nếu người dùng nhập một từ nằm giữa tên sản phẩm, terms trên toàn chuỗi keyword sẽ không tìm thấy.

### 10.3. Giả định In không phân biệt chữ hoa/chữ thường

Keyword mặc định thường giữ nguyên khác biệt chữ hoa/chữ thường. Cần normalizer hoặc chuẩn hóa đầu vào nếu nghiệp vụ yêu cầu không phân biệt.

### 10.4. Truyền collection quá lớn

Terms query có giới hạn số lượng term được phép gửi. Giá trị mặc định thường là 65.536 term, nhưng có thể phụ thuộc phiên bản và cấu hình index. Danh sách rất lớn cũng làm request nặng và tăng chi phí truy vấn.

Nếu danh sách đầu vào lớn, hãy cân nhắc chia lô có kiểm soát, dùng terms lookup khi phù hợp hoặc thay đổi mô hình dữ liệu/query. Không nên tăng giới hạn mà chưa đo tác động bộ nhớ và tải cluster.

### 10.5. Không xử lý danh sách rỗng

Danh sách rỗng không mang ý nghĩa nghiệp vụ giống nhau trong mọi ứng dụng. Terms query với danh sách rỗng không trả kết quả; truy vấn phủ định có thể tạo kết quả gần như toàn bộ document tùy cách query được dựng. Hãy kiểm tra collection rỗng ngay tại service và quyết định rõ trả danh sách rỗng, bỏ điều kiện hay từ chối request.

Không nên để hành vi của một query rỗng quyết định ngầm nghiệp vụ.

### 10.6. Nhầm field Java với field Elasticsearch

Nếu property Java name ánh xạ thành product_name, hoặc query cần sub-field product_name.keyword, phải xác nhận đúng đường dẫn field được gửi đến Elasticsearch. Tên method dẫn xuất dựa trên property Java; query tường minh phải dùng tên field trong mapping.

## 11. Kiểm tra analyzer và mapping thực tế

Khi In trên text cho kết quả khó hiểu, hãy đọc mapping:

~~~http
GET /products/_mapping/field/name
~~~

Sau đó dùng Analyze API để xem văn bản được tách thành term như thế nào:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Kết quả trả về các token và vị trí tương ứng theo analyzer của field. Dùng thông tin đó để xác định giá trị nào mà terms query có thể khớp.

Đối với keyword field, hãy kiểm tra mapping và normalizer. Đừng suy luận từ annotation trong Java nếu index đã tồn tại lâu hoặc được tạo từ template/migration khác.

Để điều tra query được sinh từ repository, có thể bật logging phù hợp cho client hoặc kiểm tra request bằng cách quan sát query thực tế trong môi trường test. Cách cấu hình logging phụ thuộc client và phiên bản Spring Data Elasticsearch.

## 12. Ví dụ tổng hợp: lọc sản phẩm theo danh mục và tên

Giả sử ứng dụng cần hai hành vi:

1. Lọc sản phẩm thuộc một trong nhiều danh mục.
2. Tìm sản phẩm theo từ khóa trong tên.

Entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters and setters
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategoryIn(Collection<String> categories);

    List<Product> findByStatusNotIn(Collection<String> statuses);
}
~~~

Với category là keyword, phương thức In phù hợp để lọc theo danh sách danh mục. Với status là keyword, NotIn phù hợp để loại các trạng thái.

Nếu muốn tìm tên theo từ khóa, dùng query toàn văn:

~~~java
@Query("{\"match\":{\"name\":?0}}")
List<Product> searchByNameText(String text);
~~~

Nếu muốn tìm tên đầy đủ theo danh sách, mapping nên có multi-field keyword và query tường minh:

~~~java
@Query("{\"terms\":{\"name.keyword\":?0}}")
List<Product> findByExactNames(Collection<String> names);
~~~

Như vậy mỗi nhu cầu dùng đúng kiểu truy vấn:

| Nhu cầu | Field | Query phù hợp |
|---|---|---|
| Lọc danh mục thuộc danh sách | category (keyword) | In / terms |
| Loại trạng thái trong danh sách | status (keyword) | NotIn / bool must_not terms |
| Tìm từ trong tên | name (text) | match |
| Tìm cụm từ trong tên | name (text) | match_phrase |
| So khớp nguyên tên trong danh sách | name.keyword | terms |

## 13. Lưu ý về tương thích phiên bản

Spring Data Elasticsearch thay đổi theo các release train của Spring Data và phiên bản Elasticsearch client. Query derivation, các toán tử được hỗ trợ, kiểu trả về, @Query binding và API query tường minh có thể khác nhau giữa phiên bản.

Khi áp dụng vào dự án:

- Kiểm tra phiên bản Spring Data Elasticsearch và Elasticsearch server/client.
- Xác nhận toán tử In và NotIn được hỗ trợ cho loại repository/query đang dùng.
- Kiểm tra mapping thực tế thay vì chỉ dựa vào annotation.
- Quan sát query JSON được gửi nếu cần xác minh cách Spring Data triển khai toán tử.
- Viết kiểm thử tích hợp với field keyword, text và document thiếu field.

Các ví dụ trong bài thể hiện cách dùng phổ biến. Hãy đối chiếu chữ ký API và query binding với phiên bản thực tế trước khi sao chép nguyên mẫu vào dự án.

## 14. Kết luận

In và NotIn là cách thuận tiện để lọc document theo một tập giá trị trong repository method. Với field keyword, chúng phù hợp cho mã, trạng thái, danh mục và các giá trị cần so khớp nguyên vẹn. Với field text, cần cẩn thận vì terms query so khớp token đã được lập chỉ mục, không tự phân tích cả chuỗi tìm kiếm như match query.

Khi cần tìm nội dung, hãy dùng match hoặc match_phrase. Khi cần so khớp toàn bộ tên hoặc chuỗi theo danh sách, hãy dùng keyword field hoặc multi-field và truy vấn đúng đường dẫn. Với NotIn, nhớ xác định cách xử lý document thiếu field; với collection lớn hoặc rỗng, xử lý rõ ở tầng ứng dụng.

Chọn toán tử theo mapping và ý nghĩa dữ liệu sẽ giúp kết quả truy vấn dễ dự đoán, tránh nhầm giữa lọc theo giá trị và tìm kiếm toàn văn.
