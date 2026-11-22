# Tham số ?0, ?1 và cơ chế thay thế giá trị

Trong Spring Data Elasticsearch, annotation @Query cho phép khai báo Elasticsearch Query DSL dưới dạng chuỗi JSON ngay trên repository method. Các placeholder vị trí như ?0, ?1 và ?2 giúp đưa giá trị từ tham số method vào query mà không phải ghép chuỗi JSON thủ công.

Placeholder được đánh số từ 0 theo thứ tự các tham số có thể bind của method. Khi thực thi, Spring Data xử lý query khai báo, thay các placeholder bằng giá trị tương ứng và gửi truy vấn đến Elasticsearch. Cấu trúc JSON và ý nghĩa Query DSL vẫn do lập trình viên thiết kế.

Điểm cần nhớ là placeholder chỉ đại diện cho giá trị dữ liệu. Nó không tự tạo điều kiện tìm kiếm, không thay thế tên field hoặc toán tử và không tự quyết định cách Elasticsearch phân tích field. Vì vậy cần viết JSON đúng, đặt placeholder đúng vị trí và hiểu mapping của field được truy vấn.

## 1. @Query và positional placeholder

Một repository có thể khai báo query JSON bằng annotation @Query:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
    List<Product> searchByName(String text);
}
~~~

Trong ví dụ:

- Chuỗi JSON trong @Query là Elasticsearch Query DSL.
- ?0 là placeholder cho tham số đầu tiên có thể bind của method.
- Khi gọi searchByName("wireless keyboard"), Spring Data đưa giá trị tham số vào vị trí placeholder.
- Elasticsearch nhận một match query trên field name.

@Query không phải SQL, JPQL hoặc cú pháp derived query. Spring Data không tự suy ra điều kiện từ tên method khi đã dùng query JSON tường minh; nội dung JSON quyết định cấu trúc truy vấn.

## 2. Đánh số ?0, ?1, ?2

Các placeholder được đánh số bắt đầu từ 0:

| Placeholder | Tham số bind tương ứng |
|---|---|
| ?0 | Tham số bind thứ nhất |
| ?1 | Tham số bind thứ hai |
| ?2 | Tham số bind thứ ba |
| ?3 | Tham số bind thứ tư |

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"bool\":{\"filter\":["
            + "{\"term\":{\"category\":\"?0\"}},"
            + "{\"term\":{\"status\":\"?1\"}}"
            + "]}}")
    List<Product> findByCategoryAndStatus(
            String category,
            String status
    );
}
~~~

Khi gọi:

~~~java
repository.findByCategoryAndStatus("books", "published");
~~~

?0 nhận books; ?1 nhận published. Hai giá trị nằm trong hai điều kiện term riêng biệt.

Thứ tự placeholder phải khớp với thứ tự tham số bind của method. Nếu đảo ?0 và ?1, query vẫn có thể là JSON hợp lệ nhưng điều kiện sẽ lọc nhầm field.

### 2.1. Tham số đặc biệt như Pageable và Sort

Pageable và Sort là các tham số đặc biệt mà Spring Data sử dụng để điều khiển phân trang hoặc sắp xếp. Chúng không phải giá trị dữ liệu thông thường cần đặt vào placeholder JSON.

Ví dụ:

~~~java
@Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
Page<Product> searchByName(String text, Pageable pageable);
~~~

Trong ví dụ này, ?0 ứng với text; Pageable điều khiển phân trang. Không viết ?1 để bind Pageable thành một giá trị trong JSON query. Cách áp dụng paging và sort cần tuân theo API repository của phiên bản Spring Data Elasticsearch đang sử dụng.

## 3. Thay thế giá trị chuỗi

Với một giá trị chuỗi, placeholder thường được đặt trong chuỗi JSON:

~~~java
@Query("{\"term\": {\"status\": \"?0\"}}")
List<Product> findByStatus(String status);
~~~

Giá trị status được bind vào vị trí đó. Dấu nháy kép trong ví dụ thuộc về cú pháp JSON bao quanh giá trị chuỗi.

Hãy để cơ chế binding của Spring Data xử lý tham số. Không tự nối input của người dùng vào query:

~~~java
// Không nên tự ghép chuỗi JSON từ dữ liệu đầu vào
String json = "{\"term\":{\"status\":\"" + status + "\"}}";
~~~

Ghép chuỗi thủ công dễ làm JSON hỏng khi giá trị có dấu nháy kép, dấu gạch chéo ngược hoặc ký tự điều khiển. Nó cũng làm code khó kiểm soát và dễ đưa dữ liệu không đáng tin cậy vào cấu trúc query.

Placeholder giúp tách cấu trúc query cố định khỏi giá trị động. Tuy vậy, vẫn cần kiểm tra giá trị đầu vào theo quy tắc nghiệp vụ và xác nhận cách binding/escape của phiên bản đang dùng.

## 4. Thay thế giá trị số, boolean và ngày giờ

Vị trí placeholder phải phù hợp với kiểu JSON mà Elasticsearch mong đợi. Với số và boolean, giá trị thường không được đặt trong dấu nháy kép.

Ví dụ query khoảng giá:

~~~java
@Query("{\"range\":{\"price\":{\"gte\":?0,\"lt\":?1}}}")
List<Product> findByPriceRange(
        BigDecimal minimum,
        BigDecimal maximumExclusive
);
~~~

?0 và ?1 lần lượt đại diện cho cận dưới và cận trên. JSON sau binding cần có các giá trị số hợp lệ.

Ví dụ điều kiện boolean:

~~~java
@Query("{\"term\":{\"available\":?0}}")
List<Product> findByAvailable(Boolean available);
~~~

Ví dụ truy vấn theo ngày giờ:

~~~java
@Query("{\"range\":{\"createdAt\":{\"gte\":\"?0\",\"lt\":\"?1\"}}}")
List<Product> findCreatedBetween(String from, String to);
~~~

Với thời gian, nên thống nhất định dạng đầu vào, chẳng hạn ISO-8601 có offset hoặc UTC. Mapping của field createdAt phải chấp nhận format đó. Nếu dùng kiểu Java như Instant, hãy xác nhận cơ chế binding của phiên bản Spring Data và cách query processor chuyển giá trị sang biểu diễn mà Elasticsearch nhận được.

Không được đặt dấu nháy quanh placeholder số hoặc boolean nếu query mong đợi JSON number hoặc boolean. Nếu đặt "gte":"?0", Elasticsearch nhận một chuỗi thay vì một giá trị số.

## 5. Bind collection vào terms query

Khi tham số là collection, có thể dùng placeholder làm giá trị cho mảng terms:

~~~java
import java.util.Collection;
import java.util.List;

@Query("{\"terms\":{\"category\":?0}}")
List<Product> findByCategories(Collection<String> categories);
~~~

Query DSL mong đợi một mảng:

~~~json
{
  "terms": {
    "category": ["books", "games", "electronics"]
  }
}
~~~

Giá trị collection cần được chuyển thành cấu trúc JSON mà terms query chấp nhận. Cách binding collection, kiểu phần tử và xử lý giá trị null cần được xác nhận với phiên bản Spring Data Elasticsearch đang sử dụng.

Terms query là truy vấn term-level. Với field keyword, nó thường phù hợp để so khớp một trong nhiều giá trị chính xác. Với field text, terms query so khớp term đã được lập chỉ mục; nó không tự phân tích từng chuỗi truyền vào như match query.

### 5.1. Danh sách rỗng

Không nên để danh sách rỗng quyết định ngầm hành vi nghiệp vụ. Trước khi gọi repository, hãy chọn rõ một trong các quy tắc:

- Danh sách rỗng nghĩa là không có lựa chọn nào, trả về danh sách rỗng.
- Danh sách rỗng nghĩa là không áp dụng bộ lọc danh mục.
- Danh sách rỗng là request không hợp lệ và cần trả lỗi validation.

Không nên giả định một terms query với mảng rỗng sẽ có cùng ý nghĩa với việc bỏ điều kiện query. Hãy xử lý ở service và kiểm thử hành vi đã chọn.

## 6. Nhiều placeholder trong một query

Một query có thể sử dụng nhiều placeholder ở các nhánh khác nhau. Ví dụ tìm sản phẩm theo danh mục, khoảng giá và trạng thái:

~~~java
@Query("{\"bool\":{"
        + "\"filter\":["
        + "{\"term\":{\"category\":\"?0\"}},"
        + "{\"term\":{\"status\":\"?1\"}},"
        + "{\"range\":{\"price\":{\"gte\":?2,\"lte\":?3}}}"
        + "]"
        + "}}")
List<Product> searchProducts(
        String category,
        String status,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice
);
~~~

Ánh xạ tham số:

| Placeholder | Tham số method | Field hoặc vị trí query |
|---|---|---|
| ?0 | category | term.category |
| ?1 | status | term.status |
| ?2 | minimumPrice | range.price.gte |
| ?3 | maximumPrice | range.price.lte |

Biểu thức JSON sau binding có ý nghĩa:

~~~json
{
  "bool": {
    "filter": [
      {"term": {"category": "books"}},
      {"term": {"status": "published"}},
      {"range": {"price": {"gte": 100, "lte": 500}}}
    ]
  }
}
~~~

Các điều kiện trong filter phải cùng khớp. Dùng filter phù hợp cho điều kiện lọc không cần tính điểm relevance.

## 7. Placeholder chỉ bind giá trị, không bind cấu trúc query

Placeholder ?0 không phải biến có thể thay thế tùy ý mọi phần của JSON DSL. Hãy xem nó là vị trí cho giá trị dữ liệu.

Các trường hợp sau không nên được thiết kế dựa trên placeholder:

- Thay tên field động, ví dụ ?0 đại diện cho category hoặc status.
- Thay tên toán tử, ví dụ term, match hoặc range.
- Thay toàn bộ một nhánh JSON tùy ý.
- Thay tên index hoặc alias trong cấu trúc query.
- Thay tên aggregation hoặc sort field.

Ví dụ, không nên kỳ vọng query sau hoạt động như một query builder động:

~~~java
// Không coi placeholder là tên field
@Query("{\"term\":{\"?0\":\"?1\"}}")
List<Product> searchDynamicField(String fieldName, String value);
~~~

Nếu field cần truy vấn thay đổi theo input, hãy xây dựng query bằng Java qua CriteriaQuery hoặc NativeQuery và chỉ chọn field từ danh sách cho phép. Việc kiểm soát danh sách field giúp tránh người dùng tự quyết định cấu trúc truy vấn.

Tương tự, nếu cấu trúc query thay đổi theo nhiều lựa chọn, hãy tạo query object trong service thay vì cố gắng nhét toàn bộ logic vào một chuỗi @Query.

## 8. Placeholder trong nested bool query

Placeholder có thể nằm sâu trong cấu trúc JSON, miễn là vị trí đó là giá trị hợp lệ của Query DSL.

Ví dụ: trạng thái phải là published và tên phải khớp từ khóa người dùng nhập:

~~~java
@Query("{\"bool\":{\"filter\":["
        + "{\"term\":{\"status\":\"?0\"}}"
        + "],\"must\":["
        + "{\"match\":{\"name\":{\"query\":\"?1\"}}}"
        + "]}}")
List<Product> searchPublishedProducts(
        String status,
        String nameText
);
~~~

?0 được dùng trong filter term-level; ?1 được dùng trong match query. Hai placeholder có thể xuất hiện ở các nhánh khác nhau của cùng một JSON query.

Nếu query có nhiều cấp lồng nhau, hãy định dạng JSON dễ đọc trước khi chuyển thành chuỗi Java. Có thể viết thành nhiều phần chuỗi hoặc dùng text block nếu dự án chạy Java hỗ trợ text block:

~~~java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } }
        ],
        "must": [
          { "match": { "name": { "query": "?1" } } }
        ]
      }
    }
    """)
List<Product> searchPublishedProducts(String status, String nameText);
~~~

Text block chỉ là cách trình bày chuỗi Java. Nó không thay đổi quy tắc placeholder hoặc ngữ nghĩa Elasticsearch Query DSL.

## 9. Dùng @Query cho match, term và range

### 9.1. Match query

~~~java
@Query("{\"match\":{\"description\":{\"query\":\"?0\"}}}")
List<Product> searchDescription(String text);
~~~

match phân tích chuỗi tìm kiếm theo analyzer của field. Nó phù hợp với nội dung text.

### 9.2. Term query

~~~java
@Query("{\"term\":{\"status\":\"?0\"}}")
List<Product> findByExactStatus(String status);
~~~

term so khớp term đã lập chỉ mục. Với trạng thái hoặc mã định danh, field keyword thường là lựa chọn phù hợp. Không dùng term trên text với kỳ vọng so sánh nguyên văn cả câu.

### 9.3. Range query

~~~java
@Query("{\"range\":{\"price\":{\"gte\":?0,\"lt\":?1}}}")
List<Product> findByPriceRange(
        BigDecimal minimum,
        BigDecimal maximumExclusive
);
~~~

Range query dùng các cận như gt, gte, lt và lte. Kiểu dữ liệu của tham số phải phù hợp mapping của field.

## 10. Binding và chuyển đổi kiểu dữ liệu

Giá trị Java cần được chuyển sang biểu diễn phù hợp với JSON và mapping Elasticsearch. Một số trường hợp thường gặp:

| Kiểu tham số Java | Vị trí query thường dùng | Điều cần xác nhận |
|---|---|---|
| String | Giá trị chuỗi trong term hoặc match | Dấu nháy, escape và mapping keyword/text |
| Integer, Long, BigDecimal | Giá trị số trong range hoặc term | Không biến số thành chuỗi; mapping numeric phù hợp |
| Boolean | Giá trị boolean | Dùng true/false JSON, không phải chuỗi |
| Collection<String> | Mảng của terms | Phần tử hợp lệ và danh sách rỗng |
| Instant, LocalDate, Date | Giá trị thời gian | Format, offset và cách converter của phiên bản xử lý |
| Enum | Giá trị chuỗi hoặc mã đã chuyển đổi | Cách enum được lưu trong document phải nhất quán |

Đối với kiểu nghiệp vụ riêng, ví dụ EmailAddress hoặc Money, hãy kiểm tra custom conversion đã đăng ký có được áp dụng cho query parameter hay không. Không nên mặc định converter dùng khi ghi entity chắc chắn được dùng giống hệt cho mọi đường binding trong @Query.

Nếu dữ liệu query có format đặc biệt, có thể chuẩn hóa tại service trước khi gọi repository. Cách này làm rõ hợp đồng đầu vào và giảm phụ thuộc vào cách xử lý ngầm.

## 11. Null, giá trị tùy chọn và điều kiện động

Placeholder không tự động loại bỏ một điều kiện JSON khi tham số là null. Một query chứa field với giá trị null có thể không có ý nghĩa như mong muốn hoặc bị Elasticsearch từ chối tùy loại query.

Ví dụ, nếu status là tùy chọn, không nên mặc định truyền null vào:

~~~java
@Query("{\"term\":{\"status\":\"?0\"}}")
List<Product> findByStatus(String status);
~~~

Thay vào đó, service nên quyết định:

- Khi status có giá trị, dùng query có filter status.
- Khi status không có giá trị, bỏ filter status.

Với query động, CriteriaQuery hoặc NativeQuery thường phù hợp hơn vì có thể thêm điều kiện có chọn lọc:

~~~java
public SearchHits<Product> searchProducts(String status, String name) {
    Criteria criteria = new Criteria();

    if (status != null && !status.isBlank()) {
        criteria.and("status").is(status);
    }

    if (name != null && !name.isBlank()) {
        criteria.and("name").matches(name);
    }

    return operations.search(
            new CriteriaQuery(criteria),
            Product.class
    );
}
~~~

Đoạn code minh họa ý tưởng xây query từ các điều kiện tùy chọn; cần xác nhận API Criteria phù hợp phiên bản dự án và xử lý trường hợp không có điều kiện theo yêu cầu nghiệp vụ.

## 12. Phân trang và sắp xếp với query có placeholder

Repository method dùng @Query có thể kết hợp với Pageable khi kiểu trả về và API phiên bản hỗ trợ:

~~~java
@Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
Page<Product> searchByName(String text, Pageable pageable);
~~~

?0 bind chuỗi tìm kiếm; Pageable điều khiển trang, kích thước trang và có thể cả sort. Không đưa Pageable vào JSON như một giá trị placeholder.

Khi dùng sort động, cần bảo đảm field được sắp xếp có mapping phù hợp. Ví dụ, sort theo tên thường cần keyword sub-field thay vì field text đã phân tích. Nếu sort field phụ thuộc input, nên kiểm soát bằng danh sách field được phép trong Java.

## 13. So sánh @Query với CriteriaQuery và NativeQuery

| Cách tiếp cận | Khi phù hợp | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|---|
| @Query với ?0, ?1 | JSON DSL cố định, chỉ thay một số giá trị | Ngắn gọn, query hiển thị ngay trên repository | Chuỗi JSON khó refactor; không phù hợp cấu trúc thay đổi lớn |
| CriteriaQuery | Bộ lọc động, điều kiện field và nhóm logic thông thường | Xây dựng bằng Java, dễ thêm/bỏ điều kiện | Cần hiểu cách Criteria chuyển thành DSL |
| NativeQuery | Query phức tạp cần kiểm soát Elasticsearch DSL | Hỗ trợ cấu trúc bool, nested, scoring và tính năng client | Gắn với API Elasticsearch Java Client của phiên bản |
| Derived query method | Điều kiện phổ biến, đơn giản | Tên method thể hiện ý định | Không linh hoạt với DSL đặc thù hoặc query lồng sâu |

Không cần dùng @Query chỉ vì query có nhiều tham số. Nếu điều kiện thay đổi theo input, việc xây dựng query trong service có thể rõ ràng hơn một chuỗi JSON dài với nhiều placeholder.

## 14. Lỗi thường gặp khi dùng ?0, ?1

### 14.1. Đánh số nhầm từ 1

Placeholder bắt đầu từ ?0, không phải ?1. Nếu method có hai tham số bind, tham số đầu tiên là ?0, tham số thứ hai là ?1.

### 14.2. Đảo thứ tự tham số

JSON vẫn hợp lệ nhưng giá trị có thể đi vào sai field. Hãy lập bảng ánh xạ placeholder và method argument khi query có nhiều tham số.

### 14.3. Đặt sai dấu nháy

Chuỗi thường cần được đặt đúng vị trí chuỗi JSON. Số và boolean phải ở vị trí giá trị JSON tương ứng, không biến thành chuỗi. Kiểm tra query sau binding nếu Elasticsearch báo lỗi parse hoặc mapping.

### 14.4. Dùng placeholder cho tên field hoặc operator

Placeholder dành cho giá trị. Với field động hoặc cấu trúc query động, hãy tạo query bằng API Java và chỉ chọn field từ danh sách được phép.

### 14.5. Truy vấn text bằng term

@Query chỉ định rõ DSL. Nếu dùng term trên field text, giá trị có thể không khớp vì analyzer đã tách chuỗi thành token. Dùng match cho toàn văn hoặc keyword sub-field cho so khớp nguyên vẹn.

### 14.6. Truyền null hoặc collection rỗng

Null không tự loại điều kiện khỏi JSON. Collection rỗng cũng cần quy tắc nghiệp vụ riêng. Xử lý các trường hợp này ở service trước khi gọi repository.

### 14.7. Giả định mọi kiểu Java đều được bind giống nhau

Các kiểu ngày giờ, enum và value object có thể cần conversion. Kiểm tra đúng đường binding của phiên bản đang dùng và viết test cho kiểu dữ liệu quan trọng.

## 15. Kiểm tra query sau khi thay thế

Khi query trả kết quả không đúng hoặc lỗi parse, hãy kiểm tra theo thứ tự:

1. JSON tĩnh trong @Query có hợp lệ không?
2. Mỗi placeholder có đúng chỉ số và đúng vị trí không?
3. Tham số Java có kiểu phù hợp với giá trị JSON mong đợi không?
4. Chuỗi, số, boolean và ngày giờ có được biểu diễn đúng không?
5. Field trong query có đúng tên mapping, kể cả sub-field không?
6. Mapping field có phù hợp với loại query như term, match hoặc range không?
7. Các tham số null, collection rỗng hoặc collection lớn đã được xử lý chưa?
8. Query thực tế gửi đến Elasticsearch có đúng như dự định không?

Trong môi trường test, có thể bật logging request phù hợp với Elasticsearch Java Client hoặc quan sát request gửi đến cluster. Cấu hình logging phụ thuộc phiên bản client. Không ghi log dữ liệu nhạy cảm nếu query chứa thông tin cá nhân, token hoặc nội dung riêng tư.

Một bộ test nên bao gồm:

- Chuỗi thông thường.
- Chuỗi có dấu nháy kép, dấu gạch chéo ngược hoặc ký tự Unicode.
- Giá trị số ở cận dưới và cận trên.
- Boolean true và false.
- Collection có một phần tử, nhiều phần tử và rỗng.
- Giá trị null nếu API cho phép.
- Giá trị thời gian có offset và các mốc ranh giới.

## 16. Ví dụ hoàn chỉnh: repository tìm sản phẩm

Entity rút gọn:

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

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
    List<Product> searchByName(String text);

    @Query("{\"terms\":{\"category\":?0}}")
    List<Product> findByCategories(Collection<String> categories);

    @Query("{\"bool\":{\"filter\":["
            + "{\"term\":{\"status\":\"?0\"}},"
            + "{\"range\":{\"price\":{\"gte\":?1,\"lt\":?2}}}"
            + "]}}")
    List<Product> findPublishedInPriceRange(
            String status,
            BigDecimal minimum,
            BigDecimal maximumExclusive
    );
}
~~~

Cách gọi:

~~~java
List<Product> matchingName =
        repository.searchByName("mechanical keyboard");

List<Product> inCategories =
        repository.findByCategories(List.of("books", "games"));

List<Product> priceRange =
        repository.findPublishedInPriceRange(
                "published",
                new BigDecimal("100"),
                new BigDecimal("500")
        );
~~~

Mỗi method có cấu trúc query cố định và chỉ thay các giá trị dữ liệu. searchByName dùng match cho field text; findByCategories dùng terms cho field keyword; findPublishedInPriceRange kết hợp term filter và range filter.

## 17. Lưu ý tương thích phiên bản

Spring Data Elasticsearch đã thay đổi theo release train của Spring Data và Elasticsearch Java Client. Cách xử lý placeholder, kiểu tham số, hỗ trợ Pageable và query annotation cần được kiểm tra theo phiên bản thực tế.

Khi áp dụng:

- Kiểm tra package và annotation @Query của đúng dependency.
- Xác nhận positional placeholder bắt đầu từ 0 và ánh xạ đúng bindable parameters.
- Kiểm tra kiểu tham số có được chuyển đổi như mong đợi.
- Thử query với giá trị đặc biệt và collection.
- Xác nhận field trong JSON tồn tại và có mapping phù hợp.
- Quan sát query thực tế trong integration test nếu kết quả chưa rõ.

Không nên sao chép query annotation từ một phiên bản Spring Data khác mà chưa kiểm tra chữ ký và cách binding. Nếu API không hỗ trợ kiểu tham số hoặc cấu trúc mong muốn, chuyển sang CriteriaQuery hoặc NativeQuery.

## 18. Kết luận

?0, ?1, ?2 là positional placeholder dùng để đưa giá trị từ tham số repository method vào JSON query khai báo bằng @Query. Chỉ số bắt đầu từ 0 và đi theo thứ tự tham số có thể bind; các tham số đặc biệt như Pageable điều khiển phân trang thay vì trở thành giá trị query.

Đặt placeholder ở đúng vị trí JSON: chuỗi trong giá trị chuỗi, số ở vị trí số, boolean ở vị trí boolean và collection ở vị trí mảng mà DSL yêu cầu. Placeholder bind giá trị chứ không thay thế tên field, toán tử hoặc cấu trúc query động.

Hãy để Spring Data xử lý binding, xác nhận mapping của field, xử lý rõ null và collection rỗng, rồi kiểm tra query thực tế trong test. Với query cố định có một vài giá trị động, @Query gọn và dễ đọc; với cấu trúc thay đổi theo input hoặc logic lồng sâu, CriteriaQuery và NativeQuery thường phù hợp hơn.
