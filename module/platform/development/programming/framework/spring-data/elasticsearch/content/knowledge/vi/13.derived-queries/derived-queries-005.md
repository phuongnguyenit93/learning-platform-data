# Like, StartingWith, EndingWith và Containing

Spring Data Elasticsearch cho phép khai báo phương thức tìm kiếm dựa trên tên method của repository. Với thuộc tính dạng chuỗi, các từ khóa như Like, StartingWith, EndingWith và Containing mô tả những kiểu khớp văn bản khác nhau. Chúng giúp viết truy vấn ngắn gọn, nhưng không có nghĩa Elasticsearch đang chạy câu lệnh SQL LIKE.

Để sử dụng đúng, cần hiểu ba điều: từ khóa method được Spring Data chuyển thành loại query Elasticsearch nào; query đó hoạt động trên term đã được lập chỉ mục ra sao; và field đang dùng là text hay keyword. Những khác biệt này ảnh hưởng trực tiếp đến kết quả, phân biệt chữ hoa/thường và hiệu năng.

## 1. Query derivation từ tên phương thức

### 1.1. Spring Data đọc tên method như thế nào?

Khi repository khai báo một method chưa có implementation, Spring Data phân tích tên method để xác định:

- Entity và property cần truy vấn.
- Điều kiện lọc.
- Kiểu so khớp được yêu cầu.
- Các điều kiện kết hợp bằng And hoặc Or.
- Thông tin sort hoặc phân trang nếu có.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByNameStartingWith(String prefix);

    List<ProductDocument> findByNameEndingWith(String suffix);

    List<ProductDocument> findByNameContaining(String fragment);

    List<ProductDocument> findByNameLike(String pattern);
}
~~~

Spring Data tạo implementation cho các method này dựa trên quy tắc query derivation được hỗ trợ bởi phiên bản Spring Data Elasticsearch của dự án.

Tên property trong method thường là tên thuộc tính Java. Nếu entity có:

~~~java
@Field(name = "product_name", type = FieldType.Keyword)
private String name;
~~~

thì method vẫn dùng findByNameStartingWith. Spring Data tra cứu metadata để ánh xạ property name sang field Elasticsearch product_name.

### 1.2. Bốn từ khóa mô tả bốn ý định tìm kiếm

Giả sử dữ liệu có các tên:

~~~text
Wireless Keyboard
Keyboard Cover
Mechanical Keyboard
Keyboard Wireless Adapter
~~~

Với chuỗi tìm là key, các ý định tìm kiếm khác nhau:

| Từ khóa | Ý nghĩa với property String | Minh họa |
|---|---|---|
| StartingWith | Giá trị hoặc term bắt đầu bằng chuỗi đưa vào | key... |
| EndingWith | Giá trị hoặc term kết thúc bằng chuỗi đưa vào | ...key |
| Containing | Giá trị hoặc term có chứa chuỗi đưa vào | ...key... |
| Like | Khớp theo mẫu theo semantics query creator của phiên bản | Phụ thuộc pattern và cách ánh xạ |

StartingWith phù hợp khi người dùng nhập đầu tên sản phẩm hoặc mã. EndingWith phù hợp khi hậu tố có ý nghĩa. Containing phù hợp khi người dùng có thể nhập một đoạn nằm ở giữa. Like dành cho truy vấn theo mẫu khi cú pháp pattern của implementation phù hợp với yêu cầu.

Không nên suy luận rằng bốn từ khóa có thể thay thế nhau. Chúng có thể tạo ra các loại query khác nhau và có chi phí thực thi khác nhau.

### 1.3. Like không phải SQL LIKE

Trong SQL, LIKE thường dùng ký tự đại diện % cho nhiều ký tự và _ cho một ký tự. Elasticsearch không có một toán tử SQL LIKE tương đương trong query DSL thông thường.

Spring Data Elasticsearch chuyển method thành query Elasticsearch theo quy tắc của phiên bản đang dùng. Tùy operator, query có thể dùng prefix, wildcard hoặc một dạng pattern query khác. Vì thế:

- Không mặc định %abc% có cùng nghĩa như trong SQL.
- Không mặc định ký tự _ luôn được hiểu giống SQL.
- Không giả định method Like sẽ tự phân tích văn bản như match query.
- Không dựa vào tên method để đoán chính xác JSON DSL được gửi đi.

Khi cần một cú pháp pattern cụ thể, hãy kiểm tra tài liệu đúng phiên bản và xem query thực tế được tạo. Nếu cần kiểm soát chính xác wildcard, regexp hoặc query string, có thể dùng @Query hay ElasticsearchOperations.

## 2. StartingWith: tìm theo tiền tố

### 2.1. Ý nghĩa

StartingWith dùng khi cần tìm những giá trị hoặc term bắt đầu bằng chuỗi được truyền vào.

~~~java
List<ProductDocument> findByNameStartingWith(String prefix);
~~~

Gọi:

~~~java
List<ProductDocument> products =
    productRepository.findByNameStartingWith("Wire");
~~~

Với dữ liệu tên sản phẩm được lưu dưới dạng keyword nguyên chuỗi, ý định là tìm những tên bắt đầu bằng Wire, chẳng hạn Wireless Keyboard và Wireless Adapter.

Ở tầng Elasticsearch, kiểu tìm theo tiền tố thường tương ứng với prefix query. Prefix query kiểm tra term trong inverted index có bắt đầu bằng chuỗi được chỉ định hay không.

### 2.2. Prefix query hoạt động trên term đã index

Prefix query không đơn giản là chạy hàm startsWith trên toàn bộ chuỗi JSON gốc. Nó làm việc với term trong inverted index.

Nếu field là keyword, toàn bộ giá trị thường được index thành một term. Ví dụ:

~~~json
{
  "name": "Wireless Keyboard"
}
~~~

Với field keyword, term có thể là toàn chuỗi Wireless Keyboard. Prefix Wire có thể khớp term đó.

Nếu field là text và dùng standard analyzer, chuỗi trên thường được tách thành các term như:

~~~text
wireless
keyboard
~~~

Khi đó prefix wire có thể khớp term wireless. Nhưng prefix wireless key không phải là prefix của một term đơn lẻ vì văn bản đã được tách thành hai term.

Do đó, phải xác định rõ ứng dụng muốn prefix trên toàn giá trị hay prefix trên từng token. Hai yêu cầu này có thể cần hai mapping khác nhau.

### 2.3. Trường hợp sử dụng

StartingWith thường phù hợp với:

- Gợi ý tên khi người dùng đang nhập.
- Tìm mã sản phẩm theo phần đầu.
- Tra cứu username hoặc mã định danh có quy ước tiền tố.
- Tìm tên tổ chức hoặc danh mục bắt đầu bằng chuỗi nhập.

Với gợi ý khi gõ, hãy giới hạn số kết quả và chỉ trả các field cần hiển thị. Nếu lượng dữ liệu lớn và yêu cầu autocomplete phức tạp, cân nhắc edge n-gram hoặc completion suggester thay vì gửi prefix query cho mọi ký tự người dùng nhập.

## 3. EndingWith: tìm theo hậu tố

### 3.1. Ý nghĩa

EndingWith dùng khi chuỗi cần tìm nằm ở cuối giá trị hoặc term.

~~~java
List<ProductDocument> findByNameEndingWith(String suffix);
~~~

Ví dụ gọi:

~~~java
List<ProductDocument> products =
    productRepository.findByNameEndingWith("Pro");
~~~

Ý định là tìm các giá trị có phần kết thúc bằng Pro. Kiểu query Elasticsearch thường dùng cho yêu cầu này là wildcard có ký tự đại diện ở đầu pattern, chẳng hạn pattern khái niệm *Pro.

### 3.2. Hậu tố thường tốn kém hơn tiền tố

Prefix query có thể tận dụng cấu trúc term dictionary để tìm vùng term bắt đầu bằng một chuỗi. Wildcard query có ký tự đại diện ở đầu thường khó giới hạn phạm vi term hơn và có thể phải xét rất nhiều term.

Vì vậy, suffix search có thể tốn tài nguyên đáng kể trên index lớn hoặc field có cardinality cao.

Không nên dùng EndingWith trên mọi field chỉ vì method dễ viết. Hãy xác định số lượng term, tần suất truy vấn, độ dài chuỗi và giới hạn tải. Với yêu cầu tìm hậu tố thường xuyên trên tập dữ liệu lớn, có thể cần thiết kế field đảo ngược chuỗi hoặc một cấu trúc index riêng để chuyển bài toán hậu tố thành tiền tố.

### 3.3. Ví dụ field đảo ngược

Một chiến lược là lưu thêm giá trị đảo ngược:

| Giá trị gốc | Giá trị đảo ngược |
|---|---|
| Wireless | sseleriW |
| Keyboard | draobyeK |
| Adapter | retpadA |

Khi người dùng tìm hậu tố less, ứng dụng đảo chuỗi thành ssel và tìm prefix trên field đảo ngược.

Cách này cần chuẩn hóa chữ hoa/thường nhất quán, xử lý Unicode đúng cách và duy trì field phụ khi ghi dữ liệu. Nó không tự động được tạo chỉ bằng method EndingWith; đây là một thiết kế mapping/ingestion riêng. Chỉ dùng khi số liệu hiệu năng chứng minh lợi ích.

## 4. Containing: tìm chuỗi nằm ở bất kỳ vị trí nào

### 4.1. Ý nghĩa

Containing với property String biểu thị ý định tìm chuỗi con xuất hiện ở đâu đó trong giá trị.

~~~java
List<ProductDocument> findByNameContaining(String fragment);
~~~

Ví dụ:

~~~java
List<ProductDocument> products =
    productRepository.findByNameContaining("less");
~~~

Với giá trị nguyên bản Wireless Keyboard, chuỗi less xuất hiện ở giữa từ Wireless.

Một cách biểu diễn ý định substring ở tầng wildcard là pattern dạng *less*. Ký tự đại diện ở cả hai đầu cho phép có nội dung trước và sau đoạn tìm.

### 4.2. Containing trên text không giống substring trên toàn câu

Đây là khác biệt rất quan trọng. Nếu field name có kiểu text, analyzer có thể tách:

~~~text
Wireless Keyboard
~~~

thành hai term:

~~~text
wireless
keyboard
~~~

Wildcard query được áp dụng trên term đã lập chỉ mục. Nó có thể tìm đoạn nằm bên trong một term như less trong wireless, nhưng không tìm một chuỗi con chạy qua ranh giới giữa hai term như ss key nếu chuỗi đó không tồn tại trong term riêng lẻ.

Nếu yêu cầu là tìm substring trên toàn bộ giá trị gốc, cần lưu giá trị dưới dạng keyword hoặc một field chuyên biệt. Nếu yêu cầu là tìm nội dung theo từ/ngữ nghĩa, full-text query như match thường phù hợp hơn.

### 4.3. Khi nào nên dùng Containing?

Containing phù hợp với tập dữ liệu vừa phải, yêu cầu substring rõ ràng và tần suất truy vấn không quá cao. Ví dụ:

- Tìm đoạn mã trong một mã tham chiếu.
- Tìm một phần tên ngắn trên field keyword.
- Tìm đoạn ký tự trong một giá trị có cấu trúc.
- Tra cứu dữ liệu nội bộ có quy mô nhỏ và đã đo hiệu năng.

Với tìm kiếm nội dung dài, hãy ưu tiên analyzer và full-text query thay vì biến mọi truy vấn thành wildcard. Người dùng thường muốn tìm các từ hoặc cụm từ, chứ không nhất thiết cần substring ở giữa một token.

## 5. Like: truy vấn theo mẫu

### 5.1. Ý định của Like

Tên method findByNameLike biểu đạt truy vấn theo mẫu. Tuy nhiên, cú pháp mẫu và loại query được tạo phụ thuộc implementation Spring Data Elasticsearch của phiên bản dự án.

Ví dụ khai báo:

~~~java
List<ProductDocument> findByNameLike(String pattern);
~~~

Đừng giả định rằng pattern truyền vào dùng cú pháp SQL. Cũng không nên tự động đưa ký tự đại diện vào tham số nếu chưa biết query creator đã tự bổ sung pattern hay chưa. Nếu method đã thêm wildcard theo semantics riêng mà ứng dụng lại truyền wildcard nữa, pattern có thể khác ý định.

Cách an toàn là tạo integration test cho các pattern quan trọng và kiểm tra query thực tế. Nếu pattern phải hỗ trợ cú pháp nâng cao, hãy viết query DSL tường minh.

### 5.2. Phân biệt wildcard và regexp

Elasticsearch có nhiều kiểu pattern query:

- **Wildcard query** hỗ trợ ký tự đại diện * cho chuỗi bất kỳ và ? cho một ký tự.
- **Regexp query** hỗ trợ biểu thức chính quy theo cú pháp Lucene.
- **Query string** có cú pháp riêng, bao gồm toán tử và ký tự đặc biệt.

Các cú pháp này không tương đương. Wildcard không phải regex; ký tự . trong wildcard không có ý nghĩa giống dấu chấm trong regex. Query string cũng có quy tắc escaping riêng.

Khi yêu cầu tìm kiếm cần pattern cụ thể, hãy chọn đúng query type và escape input theo cú pháp đó. Không nối trực tiếp input không tin cậy vào JSON query hoặc query string.

## 6. Mapping quyết định kết quả

### 6.1. Field keyword

Field keyword giữ một giá trị thành một term duy nhất và phù hợp với exact match, sorting, aggregation hoặc pattern matching trên toàn giá trị.

Ví dụ:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;
}
~~~

Với field keyword, query pattern có thể tác động lên toàn bộ tên như một term. Đây là lựa chọn thường phù hợp khi ứng dụng cần tìm tiền tố, hậu tố hoặc substring trên toàn bộ chuỗi tên ngắn.

Tuy nhiên, keyword có giới hạn độ dài term của Lucene và không phải giải pháp cho mọi nội dung dài. Với văn bản dài, hãy dùng text và thiết kế field phụ theo nhu cầu.

### 6.2. Field text

Field text được phân tích bởi analyzer. Ví dụ:

~~~java
@Field(type = FieldType.Text, analyzer = "standard")
private String description;
~~~

Analyzer có thể lowercase, tách token, loại stop word hoặc stemming. Các query prefix/wildcard làm việc với term đã index, nên kết quả không còn tương đương với thao tác trên chuỗi ban đầu.

Một chuỗi Wireless Keyboard có thể thành hai term. Substring trong một term có thể tìm được; substring cắt qua khoảng trắng hoặc ranh giới token thì không.

### 6.3. Dùng multi-field cho nhiều nhu cầu

Một property có thể cần cả full-text search lẫn exact/pattern search. Có thể khai báo multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "raw", type = FieldType.Keyword)
    }
)
private String name;
~~~

Khi đó:

- name phục vụ full-text search.
- name.raw giữ toàn bộ giá trị thành keyword để exact match, sort hoặc pattern search.

Query derivation thường tham chiếu property Java, vì vậy nếu cần truy vấn subfield cụ thể, có thể phải dùng query DSL với tên field name.raw thay vì giả định tên method có thể biểu diễn mọi đường dẫn multi-field.

### 6.4. Normalizer và chữ hoa/thường

Keyword field mặc định thường giữ nguyên cách viết hoa/thường. Vì vậy, pattern wire có thể không khớp term Wireless Keyboard nếu khác case.

Có thể cấu hình normalizer cho keyword field, chẳng hạn lowercase:

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
      "name": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Normalizer xử lý toàn bộ giá trị keyword theo quy tắc được cấu hình trước khi index. Pattern query vẫn cần được gửi theo dạng tương thích với term đã chuẩn hóa; không nên mặc định mọi query type tự chạy cùng normalizer như match query.

Một số phiên bản Elasticsearch hỗ trợ tùy chọn case-insensitive cho một số query. Khả năng đó phụ thuộc phiên bản và query API; hãy xác nhận trước khi sử dụng. Chuẩn hóa nhất quán lúc ghi và lúc truy vấn thường dễ dự đoán hơn.

## 7. Ví dụ repository đầy đủ

### 7.1. Khai báo các method tìm theo tên

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByNameStartingWith(String prefix);

    List<ProductDocument> findByNameEndingWith(String suffix);

    List<ProductDocument> findByNameContaining(String fragment);

    List<ProductDocument> findByNameLike(String pattern);
}
~~~

Các method trên minh họa cách đặt tên. Trước khi dùng trong dự án, cần xác minh các operator được hỗ trợ và query DSL thực tế với đúng phiên bản Spring Data Elasticsearch.

### 7.2. Giới hạn kết quả

Không nên trả về không giới hạn khi người dùng nhập một chuỗi rất ngắn. Có thể dùng Pageable nếu method và phiên bản hỗ trợ:

~~~java
Page<ProductDocument> findByNameStartingWith(
    String prefix,
    Pageable pageable
);
~~~

Cách gọi:

~~~java
Pageable pageable = PageRequest.of(0, 10);

Page<ProductDocument> page =
    productRepository.findByNameStartingWith("Wire", pageable);
~~~

Giới hạn kích thước trang, kiểm tra độ dài input và áp dụng rate limit cho endpoint autocomplete. Một ký tự đầu vào có thể khớp rất nhiều term và tạo truy vấn nặng.

### 7.3. Kết hợp với điều kiện khác

Có thể kết hợp điều kiện category với truy vấn theo tên nếu query derivation hỗ trợ:

~~~java
List<ProductDocument> findByCategoryAndNameStartingWith(
    String category,
    String prefix
);
~~~

Tên method dùng property Java. Điều kiện category thường nên áp dụng trên field keyword; name phải có mapping phù hợp với kiểu prefix được mong đợi.

Nếu cần kết hợp nhiều nhánh, boost hoặc điều kiện tùy chọn, hãy cân nhắc @Query hoặc ElasticsearchOperations để query được biểu diễn rõ ràng.

## 8. Khi query derivation không đủ: viết query tường minh

### 8.1. Prefix query bằng @Query

Khi muốn chắc chắn query type là prefix, có thể khai báo JSON query:

~~~java
@Query("""
{
  "prefix": {
    "name.raw": {
      "value": "?0"
    }
  }
}
""")
List<ProductDocument> searchNamePrefix(String prefix);
~~~

Ví dụ này giả định index có multi-field name.raw kiểu keyword. Hãy kiểm tra cú pháp placeholder trong annotation theo phiên bản Spring Data Elasticsearch đang sử dụng.

### 8.2. Wildcard query cho substring

Ví dụ wildcard:

~~~java
@Query("""
{
  "wildcard": {
    "name.raw": {
      "value": "*?0*"
    }
  }
}
""")
List<ProductDocument> searchNameContaining(String fragment);
~~~

Đây là ví dụ minh họa query DSL và placeholder. Khi dùng input động, phải bảo đảm ký tự đặc biệt được xử lý theo cú pháp wildcard và không làm thay đổi ý định query. Nếu cần escaping chính xác hoặc pattern phức tạp, hãy xây dựng query bằng API thay vì ghép chuỗi thủ công.

Wildcard có dấu * ở đầu có thể tốn kém. Hạn chế dùng trên index lớn nếu chưa đo hiệu năng và chưa xem xét thiết kế n-gram.

### 8.3. Prefix, wildcard và match khác nhau

| Query | Mục đích | Phân tích input |
|---|---|---|
| prefix | Term bắt đầu bằng chuỗi | Không hoạt động như full-text analyzer |
| wildcard | Pattern có wildcard trên term | Không tương đương match analyzer |
| match | Tìm nội dung văn bản sau khi phân tích query | Có sử dụng analyzer |
| match_phrase | Tìm chuỗi token theo quan hệ vị trí | Có sử dụng analyzer |

Nếu người dùng nhập wireless keyboard để tìm nội dung có hai từ đó, match hoặc match_phrase thường phù hợp hơn wildcard *wireless keyboard*. Nếu người dùng nhập wire để autocomplete một term, prefix query phù hợp hơn.

## 9. Hiệu năng và giới hạn của pattern query

### 9.1. Prefix thường dễ tối ưu hơn wildcard có leading wildcard

Prefix query giới hạn term theo phần đầu nên thường có thể tận dụng cấu trúc term dictionary tốt hơn. Wildcard dạng *fragment hoặc *fragment* có leading wildcard, làm không gian term cần xét lớn hơn.

Không thể kết luận mọi prefix query luôn rẻ hoặc mọi wildcard query luôn chậm. Hiệu năng phụ thuộc số lượng term, độ chọn lọc của pattern, kích thước index, cache, shard và tải cluster.

### 9.2. Expensive queries

Elasticsearch có thiết lập search.allow_expensive_queries. Khi cấu hình tắt các query tốn kém, một số wildcard, regexp hoặc query dạng pattern có thể bị từ chối tùy query type và phiên bản.

Vì vậy, query hoạt động trên môi trường local chưa chắc hoạt động trên production. Hãy kiểm tra chính sách cluster và thử đúng cấu hình triển khai.

Không bật lại expensive queries chỉ để làm một method chạy được mà chưa đánh giá ảnh hưởng lên cluster. Thay vào đó, cân nhắc đổi cách lập chỉ mục hoặc loại query.

### 9.3. N-gram và edge n-gram

Nếu yêu cầu substring hoặc autocomplete có tần suất cao, có thể lập chỉ mục thêm token n-gram:

- **Edge n-gram** tạo các tiền tố từ đầu token, phù hợp autocomplete.
- **N-gram** tạo các đoạn con liên tiếp trong token, phù hợp substring search.

Ví dụ từ keyboard có thể tạo edge n-gram như k, ke, key, keyb... với giới hạn min/max gram phù hợp.

Cách này tăng dung lượng index và thời gian indexing, nhưng query-time thường đơn giản hơn so với quét wildcard trên nhiều term. Cần chọn min_gram/max_gram dựa trên độ dài input người dùng và giới hạn Elasticsearch.

### 9.4. Dùng wildcard field khi phù hợp

Elasticsearch có field type wildcard dành cho các trường hợp tìm kiếm pattern trên chuỗi lớn hoặc cardinality cao theo đặc điểm của loại field này. Nó có cách lưu trữ và xử lý khác keyword/text.

Không đổi tất cả field sang wildcard type. Hãy đọc tài liệu phiên bản Elasticsearch, đánh giá workload và benchmark trước khi chọn. Field type này không thay thế analyzer cho full-text search.

## 10. Bảo vệ truy vấn và input

### 10.1. Kiểm tra input người dùng

Pattern query có thể chứa ký tự điều khiển cú pháp như *, ?, dấu gạch chéo hoặc các ký tự đặc biệt khác tùy query type. Nếu người dùng được phép nhập pattern tự do, cần xác định rõ họ có quyền dùng wildcard hay chỉ được tìm literal substring.

Các biện pháp thường cần:

- Giới hạn độ dài chuỗi tìm.
- Loại bỏ hoặc escape ký tự đặc biệt theo query type.
- Từ chối pattern chỉ gồm wildcard.
- Đặt giới hạn page size và số kết quả.
- Rate limit endpoint autocomplete/search.
- Không nối trực tiếp input vào query string hoặc JSON mà không escape.
- Theo dõi timeout và lượng request bị từ chối.

Escaping của wildcard, regexp và query string khác nhau. Không dùng một hàm escape chung cho mọi loại query.

### 10.2. Không để input biến thành query rộng ngoài ý muốn

Nếu endpoint chỉ định tìm literal substring, người dùng nhập * không nên vô tình yêu cầu khớp mọi term. Tương tự, một regex có thể tạo pattern rất rộng và gây tải lớn.

Hãy phân biệt hai chế độ sản phẩm:

- **Literal search**: người dùng chỉ nhập văn bản, ứng dụng tự xây query và escape đúng.
- **Advanced pattern search**: người dùng được phép nhập cú pháp wildcard/regex, có giới hạn và hướng dẫn rõ ràng.

Không trộn hai chế độ mà không có quy ước.

## 11. Kiểm thử hành vi thực tế

### 11.1. Tạo dữ liệu mẫu

Một tập document nhỏ giúp xác định query khớp như mong đợi:

~~~json
[
  { "id": "1", "name": "Wireless Keyboard" },
  { "id": "2", "name": "Keyboard Cover" },
  { "id": "3", "name": "Mechanical Keyboard" },
  { "id": "4", "name": "Wireless Adapter" },
  { "id": "5", "name": "Keychain" }
]
~~~

Kiểm tra các trường hợp:

| Method/ý định | Input | Điều cần xác nhận |
|---|---|---|
| StartingWith | Wire | Có khớp term hoặc giá trị bắt đầu bằng Wire theo mapping không? |
| EndingWith | board | Có khớp hậu tố mong đợi không? |
| Containing | less | Có khớp substring trong term không? |
| Like | Pattern thử nghiệm | Pattern được hiểu theo cú pháp nào trong phiên bản hiện tại? |

Không nên chỉ kiểm tra một kết quả. Hãy thêm dữ liệu có chữ hoa/thường, dấu, dấu câu, khoảng trắng, ký tự wildcard và nhiều token.

### 11.2. Kiểm tra mapping và token

Dùng mapping API để xem field thực tế là text hay keyword:

~~~http
GET /products/_mapping
~~~

Nếu field là text, kiểm tra analyzer:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Keyboard"
}
~~~

Analyze API cho biết token được tạo ra, giúp giải thích vì sao prefix hoặc wildcard match một phần token thay vì toàn bộ chuỗi.

### 11.3. Xác minh query được Spring Data tạo

Với query derivation, hãy bật logging phù hợp cho phần Spring Data Elasticsearch/client ở môi trường kiểm thử và quan sát request DSL. Cấu hình logger cụ thể phụ thuộc phiên bản client và ứng dụng.

Một integration test nên xác minh:

1. Method repository được khởi tạo thành công.
2. Query thực sự gửi đến Elasticsearch.
3. Tập ID trả về đúng với dữ liệu mẫu.
4. Case sensitivity phù hợp yêu cầu.
5. Phân trang giới hạn số kết quả.
6. Pattern chứa ký tự đặc biệt được xử lý đúng.
7. Query không tạo tải hoặc timeout bất thường với dữ liệu gần thực tế.

Unit test chỉ mock repository không xác minh được query derivation hoặc semantics của Elasticsearch. Cần integration test với Elasticsearch tương thích.

## 12. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| StartingWith không khớp phần đầu tên mong đợi | Field text đã được tách token hoặc analyzer thay đổi dữ liệu | Kiểm tra mapping, analyzer và term thực tế |
| EndingWith rất chậm | Query cần wildcard ở đầu pattern | Đo tải; cân nhắc field đảo ngược hoặc cấu trúc khác |
| Containing không tìm được đoạn qua khoảng trắng | Query hoạt động trên term, không phải chuỗi gốc đầy đủ | Dùng keyword field nếu cần substring toàn giá trị hoặc match query nếu tìm theo từ |
| Like không hiểu ký tự % | SQL wildcard không phải cú pháp mặc định của Elasticsearch | Kiểm tra query creator và dùng query DSL đúng loại |
| Tìm wire không khớp Wireless | Khác chữ hoa/thường hoặc term được chuẩn hóa khác | Dùng normalizer/analyzer phù hợp và kiểm tra query |
| Query text trả về nhiều kết quả hơn mong muốn | Analyzer tách hoặc chuẩn hóa token | Kiểm tra _analyze, dùng keyword subfield nếu cần exact |
| Query pattern bị từ chối | Cluster chặn expensive query hoặc input không hợp lệ | Kiểm tra cluster policy, query type và pattern |
| Input * trả quá nhiều kết quả | Wildcard được hiểu như cú pháp pattern | Escape input literal hoặc giới hạn pattern |
| Query method không được tạo | Operator/property không được hỗ trợ trong phiên bản | Kiểm tra method parser và chuyển sang @Query nếu cần |

## 13. Chọn công cụ theo nhu cầu

| Nhu cầu người dùng | Cách tiếp cận nên xem xét |
|---|---|
| Nhập đầu tên để gợi ý | Prefix query hoặc edge n-gram/completion |
| Tìm tên kết thúc bằng một đoạn | Wildcard suffix, field đảo ngược nếu tần suất cao |
| Tìm substring trong tên ngắn | Keyword + wildcard, hoặc n-gram nếu workload lớn |
| Tìm các từ trong mô tả | Match query với analyzer phù hợp |
| Tìm đúng cả cụm từ | Match phrase |
| Tìm mẫu có cú pháp wildcard | Wildcard query, kiểm soát input |
| Tìm mẫu regex | Regexp query, giới hạn pattern |
| Tìm chính xác toàn bộ giá trị | Keyword field và term query |

Không chọn method chỉ vì tên của nó nghe gần với yêu cầu nghiệp vụ. Hãy xác định người dùng muốn tìm theo toàn bộ giá trị, theo term đã phân tích, theo tiền tố/hậu tố hay theo một mẫu ký tự. Sau đó chọn mapping và query phù hợp.

## 14. Những điểm cần ghi nhớ

- StartingWith biểu đạt tìm theo tiền tố; EndingWith tìm theo hậu tố; Containing tìm đoạn nằm bên trong; Like là pattern matching theo semantics của query creator.
- Các từ khóa trên không có nghĩa Elasticsearch chạy SQL LIKE.
- Query prefix/wildcard làm việc với term đã index; text analyzer có thể tách một chuỗi thành nhiều term.
- Keyword phù hợp hơn khi cần pattern trên toàn bộ giá trị ngắn; text phù hợp hơn với full-text search.
- Case sensitivity phụ thuộc cách index/normalize term và loại query.
- Leading wildcard thường tốn kém hơn prefix; substring search quy mô lớn có thể cần n-gram.
- Query derivation tiện cho điều kiện đơn giản; dùng @Query hoặc ElasticsearchOperations khi cần kiểm soát DSL.
- Luôn xác minh operator được hỗ trợ và query thực tế trên đúng phiên bản Spring Data Elasticsearch.
- Kiểm thử bằng Elasticsearch thật hoặc test container để xác nhận kết quả, mapping và hiệu năng.

Khi hiểu rõ quan hệ giữa tên method, query DSL và mapping, bạn có thể chọn đúng kiểu tìm kiếm theo tên, giải thích được vì sao một truy vấn trả về hoặc bỏ sót kết quả, và tránh biến một thao tác autocomplete đơn giản thành truy vấn wildcard tốn kém trên toàn index.
