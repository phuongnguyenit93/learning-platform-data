# findBy, countBy, existsBy và deleteBy theo khả năng hỗ trợ

Spring Data Elasticsearch cho phép khai báo nhiều truy vấn ngay trên tên method của repository. Thay vì tự tạo query cho các điều kiện đơn giản, bạn có thể đặt tên method theo quy ước như findBySku, countByActiveTrue hoặc existsByEmail. Spring Data phân tích tên method, xác định property và predicate, sau đó tạo truy vấn phù hợp với Elasticsearch.

Các nhóm tên thường gặp có mục đích khác nhau:

- **findBy** tìm và trả về document thỏa điều kiện.
- **countBy** đếm số document thỏa điều kiện.
- **existsBy** kiểm tra có document thỏa điều kiện hay không.
- **deleteBy** xóa document thỏa điều kiện.

Không phải mọi keyword truy vấn của Spring Data đều được hỗ trợ giống nhau trong Spring Data Elasticsearch. Khả năng derivation còn phụ thuộc phiên bản, kiểu field, mapping và query backend. Vì vậy, hãy dùng derived query cho các điều kiện đơn giản đã được phiên bản dự án hỗ trợ; với truy vấn phức tạp hoặc không rõ semantics, dùng @Query hoặc ElasticsearchOperations.

## 1. Cấu trúc tên method

Một derived query thường có dạng:

~~~text
<operation><By><property><predicate><And/Or><property>...
~~~

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByActiveTrue();

    long countByCategory(String category);

    boolean existsBySku(String sku);

    void deleteBySku(String sku);
}
~~~

Spring Data phân tích tiền tố operation để xác định loại thao tác, phần sau By để xác định property và điều kiện.

Với findBySku:

- findBy cho biết đây là truy vấn đọc.
- Sku được phân giải thành property sku của domain type.
- Tham số String sku cung cấp giá trị cần tìm.
- Kiểu trả về List<Product> yêu cầu trả về các document phù hợp.

Với countByCategory:

- countBy cho biết cần đếm.
- Category là property category.
- Kết quả là số document phù hợp, thường dùng long.

Với existsBySku:

- existsBy cho biết chỉ cần kết quả boolean.
- Không cần tải toàn bộ nội dung document về service nếu mục tiêu chỉ là kiểm tra có kết quả.

Với deleteBySku:

- deleteBy cho biết cần xóa document thỏa điều kiện.
- Đây là thao tác ghi/xóa dữ liệu và cần được dùng với phạm vi điều kiện rõ ràng.

Tên property phải khớp với domain model. Nếu entity có skuCode thì findBySku(...) không tự động hiểu đó là skuCode. Spring Data thường báo lỗi khi không phân giải được property.

## 2. Entity và repository dùng trong ví dụ

Giả sử ứng dụng quản lý sản phẩm:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // constructors, getters and setters
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByCategory(String category);

    List<Product> findByActiveTrue();

    long countByCategory(String category);

    boolean existsBySku(String sku);

    void deleteBySku(String sku);
}
~~~

Ví dụ sử dụng:

~~~java
List<Product> products =
    productRepository.findByCategory("accessories");

long total =
    productRepository.countByCategory("accessories");

boolean exists =
    productRepository.existsBySku("SKU-1001");
~~~

Các ví dụ trên giả định các property và mapping tương ứng đã tồn tại trên index. Tên method được phân tích dựa trên Java domain model, nhưng semantics của truy vấn còn phụ thuộc mapping Elasticsearch.

## 3. findBy: tìm document theo điều kiện

findBy là nhóm method phổ biến nhất. Nó tạo truy vấn đọc dựa trên property trong tên method.

Tìm theo một property:

~~~java
List<Product> findBySku(String sku);
~~~

Tìm theo nhiều điều kiện kết hợp AND:

~~~java
List<Product> findByCategoryAndActiveTrue(String category);
~~~

Tìm theo điều kiện OR:

~~~java
List<Product> findBySkuOrName(String sku, String name);
~~~

Trong các method nhiều điều kiện, thứ tự tham số đi theo thứ tự property trong tên method. Ví dụ findBySkuAndCategory(String sku, String category) nhận sku trước rồi category.

Hãy giữ method ngắn và diễn đạt rõ nghiệp vụ. Khi một method có nhiều điều kiện, nhiều nhánh OR và nhiều modifier, một query tường minh thường dễ đọc, dễ kiểm soát và dễ debug hơn.

### 3.1. findBy với kiểu trả về

Các kiểu trả về thường dùng gồm:

~~~java
Optional<Product> findBySku(String sku);

List<Product> findByCategory(String category);

Page<Product> findByActiveTrue(Pageable pageable);
~~~

Ý nghĩa:

- Optional<Product>: phù hợp khi nghiệp vụ kỳ vọng tối đa một kết quả. Nếu dữ liệu có thể có nhiều kết quả, không nên dùng Optional đơn lẻ.
- List<Product>: trả về danh sách kết quả, phù hợp khi số kết quả có giới hạn hợp lý.
- Page<Product>: trả về một trang cùng thông tin phân trang và tổng số hit theo cơ chế của query/page được sử dụng.

Nếu SKU được bảo đảm duy nhất trong nghiệp vụ, có thể dùng Optional<Product> findBySku(...). Nếu dữ liệu không được ràng buộc duy nhất, một query có thể khớp nhiều document; khi đó dùng List hoặc xử lý kết quả trùng rõ ràng.

Kiểu trả về và các dạng SearchHits/SearchPage được hỗ trợ có thể khác theo phiên bản Spring Data Elasticsearch. Kiểm tra tài liệu/API của dependency đang dùng trước khi chọn kiểu nâng cao.

### 3.2. Phân trang với Pageable

Có thể truyền Pageable để giới hạn số kết quả và chọn trang:

~~~java
Page<Product> findByCategory(
    String category,
    Pageable pageable
);
~~~

Sử dụng:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "name")
);

Page<Product> page =
    productRepository.findByCategory("accessories", pageable);

List<Product> products = page.getContent();
long total = page.getTotalElements();
int pageCount = page.getTotalPages();
~~~

Pageable mô tả page number, page size và sort. Với Elasticsearch, phân trang sâu bằng from/size có giới hạn thực tế và có thể tốn tài nguyên. Khi cần duyệt tập dữ liệu lớn, cân nhắc search_after hoặc cơ chế scroll phù hợp thay vì tăng page number không giới hạn.

Page thường cần thông tin tổng số kết quả. Nếu màn hình chỉ cần biết còn trang tiếp theo hay không, dùng Slice nếu phiên bản và repository method hỗ trợ, hoặc chọn cách truy vấn chỉ lấy số lượng cần thiết. Không yêu cầu total chính xác nếu nghiệp vụ không cần.

### 3.3. Sắp xếp theo tên method

Có thể khai báo sort cố định bằng OrderBy:

~~~java
List<Product> findByCategoryOrderByPriceInCentsAsc(String category);

List<Product> findByCategoryOrderByPriceInCentsDesc(String category);
~~~

Tên method diễn đạt property dùng để sort và chiều tăng/giảm. Nếu cần sort linh hoạt theo request, truyền Sort hoặc Pageable khi method và phiên bản hỗ trợ.

Field dùng để sort phải có mapping phù hợp. Với field text được phân tích, thường cần sort trên field keyword phụ như name.keyword thay vì chính field text. Hãy kiểm tra mapping thực tế trước khi dùng sort.

## 4. countBy: đếm document theo điều kiện

countBy trả về số document khớp với predicate.

~~~java
long countByCategory(String category);

long countByActiveTrue();

long countByCategoryAndActiveTrue(String category);
~~~

Sử dụng:

~~~java
long activeAccessories =
    productRepository.countByCategoryAndActiveTrue("accessories");
~~~

Đây là cách diễn đạt trực tiếp khi chỉ cần số lượng. Không cần tải danh sách Product về ứng dụng rồi gọi size():

~~~java
// Không nên tải toàn bộ kết quả chỉ để lấy số lượng:
long total = productRepository
    .findByCategory("accessories")
    .size();
~~~

Cách trên có thể tải nhiều document qua mạng, cấp phát object Java và tiêu tốn bộ nhớ. countBy phù hợp hơn vì mục tiêu là đếm.

Tuy nhiên, count vẫn cần Elasticsearch thực thi điều kiện trên phạm vi index/shard liên quan. Nó không phải thao tác miễn phí. Hạn chế gọi countBy lặp lại trên mỗi request nếu số liệu không cần cập nhật liên tục.

### 4.1. countBy và count()

Phân biệt:

| Method | Phạm vi |
|---|---|
| count() | Đếm tất cả document trong phạm vi repository |
| countByCategory(category) | Đếm document có category bằng giá trị truyền vào |
| countByActiveTrue() | Đếm document có active = true |
| countByCategoryAndActiveTrue(category) | Đếm document thỏa cả hai điều kiện |

count() thường được kế thừa từ repository base interface. countBy... là derived query dựa trên điều kiện nghiệp vụ.

### 4.2. Kiểu trả về và độ lớn

Dùng long cho số lượng để tránh giới hạn thấp của int:

~~~java
long total = productRepository.countByCategory("accessories");
~~~

Nếu một method countBy không được phiên bản hiện tại hỗ trợ, có thể dùng ElasticsearchOperations.count với Query tương ứng. Đừng thay bằng findBy rồi tải toàn bộ document chỉ để đếm.

## 5. existsBy: chỉ kiểm tra có kết quả hay không

existsBy trả về boolean. Nó phù hợp khi service chỉ cần biết một điều kiện có document nào thỏa hay không.

~~~java
boolean existsBySku(String sku);

boolean existsByCategoryAndActiveTrue(String category);
~~~

Ví dụ:

~~~java
if (productRepository.existsBySku("SKU-1001")) {
    throw new IllegalArgumentException("SKU already exists");
}
~~~

existsBy khác countBy ở kết quả và ý định:

- existsBy chỉ cần biết có ít nhất một kết quả.
- countBy cần biết số lượng kết quả.

Nếu chỉ cần boolean, không nên gọi countBy rồi so sánh lớn hơn 0 nếu existsBy tương ứng được phiên bản hỗ trợ. Một query existence có thể tránh công việc đếm chính xác.

### 5.1. existsById và existsBySku

existsById là method chuẩn của repository để kiểm tra theo document ID. existsBySku là derived query kiểm tra property sku.

~~~java
boolean existsById(String id);

boolean existsBySku(String sku);
~~~

Hai method không tương đương:

- existsById tra cứu document theo ID Elasticsearch.
- existsBySku tìm document có field sku khớp giá trị.

Nếu SKU không unique, existsBySku vẫn chỉ trả boolean. Nó không cho biết có bao nhiêu sản phẩm dùng SKU đó.

### 5.2. existsBy không thay thế ràng buộc duy nhất

Mẫu sau có thể gặp race condition:

~~~java
if (!productRepository.existsBySku(sku)) {
    productRepository.save(product);
}
~~~

Hai request đồng thời có thể cùng kiểm tra và nhận false trước khi request nào ghi dữ liệu. Sau đó cả hai cùng ghi một SKU.

Elasticsearch không tự tạo unique constraint cho một field keyword giống database quan hệ. Nếu nghiệp vụ yêu cầu uniqueness, hãy thiết kế document ID xác định từ SKU hoặc dùng cơ chế ghi có điều kiện và xử lý conflict phù hợp. Không coi existsBy là khóa hoặc ràng buộc duy nhất.

## 6. deleteBy: xóa document theo điều kiện

deleteBy diễn đạt thao tác xóa theo predicate:

~~~java
void deleteByCategory(String category);

void deleteByActiveFalse();
~~~

Ví dụ:

~~~java
productRepository.deleteByCategory("discontinued");
~~~

Method này có tác động dữ liệu. Trước khi dùng, cần xác nhận điều kiện khớp đúng phạm vi cần xóa và có cơ chế bảo vệ nếu giá trị đầu vào rỗng hoặc không hợp lệ.

### 6.1. Phân biệt deleteById, deleteAllById và deleteBy

| Method | Mục đích |
|---|---|
| deleteById(id) | Xóa một document theo ID |
| deleteAllById(ids) | Xóa các document theo tập ID |
| deleteBySku(sku) | Xóa document thỏa điều kiện SKU |
| deleteByCategory(category) | Xóa document thỏa điều kiện category |
| deleteAll() | Xóa toàn bộ document trong phạm vi repository theo semantics của implementation |

deleteBy... là query method theo điều kiện. deleteById và deleteAllById là method CRUD chuẩn. deleteAll() có phạm vi ảnh hưởng rộng và cần được dùng cẩn trọng.

### 6.2. Giá trị trả về của deleteBy

Khả năng hỗ trợ kiểu trả về của derived delete method có thể thay đổi theo phiên bản Spring Data Elasticsearch và cách query được triển khai. Ví dụ đơn giản:

~~~java
void deleteByCategory(String category);
~~~

Nếu cần biết số document bị xóa, hãy xác nhận phiên bản hỗ trợ kiểu trả về số lượng cho derived delete method. Nếu API không cung cấp số lượng theo cách cần thiết, hãy dùng thao tác xóa/query có kết quả được kiểm soát qua ElasticsearchOperations hoặc Elasticsearch Delete By Query API.

Không giả định một method deleteBy luôn trả số document bị xóa chỉ vì một module Spring Data khác có hành vi như vậy.

### 6.3. Chi phí và quy mô của deleteBy

Xóa theo điều kiện có thể yêu cầu Elasticsearch xác định các document khớp rồi thực hiện thao tác xóa. Cách triển khai cụ thể có thể khác giữa phiên bản và loại query. Với số lượng lớn, hãy xem request thực tế và cân nhắc Delete By Query API hoặc cơ chế batch phù hợp.

Một thao tác xóa lớn có thể:

- Tốn CPU và I/O khi tìm document khớp.
- Tạo tải trên nhiều shard.
- Kéo dài thời gian thực hiện.
- Ảnh hưởng hoạt động đọc/ghi khác.
- Cần xử lý timeout, retry và kết quả một phần tùy API.

Không chạy deleteBy với điều kiện quá rộng trong production nếu chưa xác nhận phạm vi. Với dữ liệu quan trọng, hãy chạy truy vấn đọc trước để xem số lượng và mẫu document sẽ bị tác động.

## 7. Các predicate thường gặp và giới hạn hỗ trợ

Spring Data có quy ước đặt tên cho nhiều kiểu điều kiện. Spring Data Elasticsearch hỗ trợ một tập con và semantics cụ thể tùy phiên bản. Một số nhóm thường gặp trong query derivation:

| Nhóm | Ví dụ tên method | Ý nghĩa mong muốn |
|---|---|---|
| So khớp giá trị | findBySku, findBySkuIs | Giá trị bằng |
| Kết hợp AND | findByCategoryAndActiveTrue | Cả hai điều kiện đúng |
| Kết hợp OR | findBySkuOrName | Một trong các điều kiện đúng |
| Boolean | findByActiveTrue, findByActiveFalse | Giá trị true/false |
| So sánh số | findByPriceInCentsGreaterThan | Lớn hơn |
| So sánh biên | findByPriceInCentsGreaterThanEqual | Lớn hơn hoặc bằng |
| Khoảng | findByPriceInCentsBetween | Nằm trong khoảng |
| Tập giá trị | findByCategoryIn | Thuộc một tập giá trị |
| Không thuộc tập | findByCategoryNotIn | Không thuộc tập giá trị |
| Chuỗi | findByNameStartingWith | Bắt đầu bằng chuỗi |
| Null | findByDescriptionIsNull | Giá trị null theo semantics được hỗ trợ |

Đây là các mẫu tên để hiểu quy ước, không phải cam kết rằng mọi keyword đều được triển khai cho mọi phiên bản hoặc mọi field type của Spring Data Elasticsearch.

Trước khi sử dụng predicate mới, kiểm tra danh sách supported keywords của đúng version. Nếu method không được hỗ trợ, Spring có thể báo lỗi lúc tạo repository hoặc query được tạo ra có semantics khác với điều bạn mong đợi.

### 7.1. So sánh số và ngày

Các predicate GreaterThan, LessThan, Between, Before và After thường được dùng cho kiểu số/ngày nếu phiên bản hỗ trợ:

~~~java
List<Product> findByPriceInCentsGreaterThan(Long minimum);

List<Product> findByPriceInCentsBetween(
    Long minimum,
    Long maximum
);
~~~

Mapping phải tương thích với phép so sánh. Field số nên có kiểu integer/long/double phù hợp; field ngày cần mapping date và format nhất quán.

Không dùng so sánh range trên field keyword chỉ vì giá trị nhìn giống số. Keyword được so khớp theo chuỗi, có thể tạo thứ tự khác với thứ tự số.

### 7.2. Điều kiện chuỗi và analyzer

Với field name kiểu text, query có thể được phân tích theo analyzer. Với field sku kiểu keyword, so khớp thường dựa trên giá trị nguyên vẹn.

Ví dụ:

~~~java
List<Product> findByName(String name);

List<Product> findBySku(String sku);
~~~

Hai method có cùng cấu trúc tên nhưng không nhất thiết có cùng semantics tìm kiếm vì mapping khác nhau.

Các từ khóa như Containing, StartingWith, EndingWith, Like hoặc IgnoreCase cần được kiểm tra kỹ với Spring Data Elasticsearch version đang dùng. Không suy ra rằng chúng hoạt động giống Spring Data JPA hoặc giống cách gọi String.contains() trong Java.

Nếu cần wildcard, regexp, fuzzy, phrase, analyzer riêng hoặc tìm kiếm đa ngôn ngữ, hãy tạo query tường minh và kiểm tra mapping/analyzer thay vì dựa vào tên method đơn giản.

## 8. Property path và tên field lồng nhau

Spring Data phân tích property path từ tên method. Với entity lồng nhau:

~~~java
public class Address {
    private String city;
}

@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    private Address address;
}
~~~

Có thể cần truy vấn theo property lồng nhau:

~~~java
List<Customer> findByAddressCity(String city);
~~~

Tên AddressCity được phân tích thành property address.city nếu mapping context xác định được đường dẫn đó.

Nếu tên property có thể gây nhập nhằng, dấu gạch dưới có thể dùng để phân tách path trong một số quy ước Spring Data:

~~~java
List<Customer> findByAddress_City(String city);
~~~

Hỗ trợ nested/object query còn phụ thuộc mapping. Elasticsearch phân biệt object và nested mapping; truy vấn trên array object cần semantics nested khi muốn các điều kiện cùng khớp trên một phần tử. Derived query không tự sửa mapping để biến object thành nested.

Với nested query phức tạp, dùng @Query hoặc ElasticsearchOperations để thể hiện rõ nested path và điều kiện.

## 9. Kết hợp AND, OR và thứ tự điều kiện

Có thể ghép nhiều predicate:

~~~java
List<Product> findByCategoryAndActiveTrue(String category);

List<Product> findByCategoryAndPriceInCentsLessThan(
    String category,
    Long maximumPrice
);
~~~

OR:

~~~java
List<Product> findBySkuOrName(
    String sku,
    String name
);
~~~

Khi kết hợp AND và OR trong cùng một tên method, cần đặc biệt chú ý cách parser nhóm điều kiện và mức độ dễ đọc. Một tên dài có thể tạo logic khác với cách người viết suy nghĩ nếu không hiểu quy tắc phân tích method name.

Nếu biểu thức có ngoặc logic, nhiều nhánh hoặc cần kiểm soát bool query must/should/filter/must_not, hãy dùng query tường minh. Query tường minh giúp thể hiện cấu trúc logic và dễ đối chiếu với REST request.

## 10. Dùng @Query khi derived query không đủ

Spring Data Elasticsearch cho phép khai báo Elasticsearch query bằng @Query trên repository method trong các phiên bản hỗ trợ.

Ví dụ query theo SKU:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"term\":{\"sku\":\"?0\"}}")
    List<Product> findExactSku(String sku);
}
~~~

Tham số ?0 tham chiếu đối số đầu tiên của method. Với query JSON phức tạp, cần escape chuỗi đúng và xác nhận cú pháp JSON hợp lệ.

Ví dụ query theo khoảng giá:

~~~java
@Query("""
{
  "range": {
    "priceInCents": {
      "gte": ?0,
      "lte": ?1
    }
  }
}
""")
List<Product> findInPriceRange(Long minimum, Long maximum);
~~~

Cú pháp text block yêu cầu Java 15 trở lên. Nếu project dùng Java thấp hơn, dùng chuỗi Java đã escape hoặc cách khai báo query được phiên bản hỗ trợ.

@Query hữu ích khi cần kiểm soát DSL cụ thể nhưng vẫn muốn method nằm trong repository interface. Nếu query cần được xây dựng từ nhiều điều kiện tùy chọn ở runtime, ElasticsearchOperations thường linh hoạt hơn.

## 11. Dùng ElasticsearchOperations cho query động

Khi filter được chọn tùy request, không nên tạo hàng chục method cho mọi tổ hợp điều kiện.

Ví dụ dùng Criteria API:

~~~java
Criteria criteria = new Criteria("active").is(true);

if (category != null && !category.isBlank()) {
    criteria = criteria.and("category").is(category);
}

if (minimumPrice != null) {
    criteria = criteria.and("priceInCents").greaterThanEqual(minimumPrice);
}

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Ví dụ này minh họa việc ghép điều kiện theo dữ liệu đầu vào. Cú pháp Criteria và kiểu query có thể thay đổi giữa các phiên bản Spring Data Elasticsearch; hãy dùng API tương ứng với dependency dự án.

Operations phù hợp khi cần:

- Thêm/bỏ filter tùy request.
- Dùng nested query.
- Dùng aggregation.
- Kiểm soát sort, pagination và source filtering.
- Truy vấn nhiều index bằng IndexCoordinates.
- Dùng các query DSL nâng cao của Elasticsearch.

Repository derived query phù hợp cho các truy vấn đơn giản, ổn định và dễ biểu đạt bằng tên method.

## 12. Phân trang, tổng số và chi phí truy vấn

Một method trả Page có thể cần tổng số hit để điền Page.totalElements. Với tập dữ liệu lớn, việc tính total chính xác có chi phí.

Ví dụ:

~~~java
Page<Product> findByCategory(String category, Pageable pageable);
~~~

Nếu giao diện chỉ hiển thị 20 kết quả và nút tiếp theo, hãy cân nhắc có thật sự cần tổng số trang chính xác hay không. Có thể chọn một dạng kết quả không cần tổng chính xác nếu phiên bản Spring Data Elasticsearch hỗ trợ.

Ngoài ra:

- Giới hạn page size.
- Tránh phân trang sâu bằng offset lớn.
- Dùng sort ổn định khi cần duyệt dữ liệu.
- Với tập dữ liệu lớn, cân nhắc search_after hoặc scroll.
- Không gọi countBy riêng nếu kết quả Page đã cung cấp total phù hợp yêu cầu.
- Không tải List không giới hạn rồi mới lọc ở Java.

## 13. An toàn khi dùng deleteBy

Derived delete method có thể xóa nhiều document. Trước khi gọi, cần bảo đảm:

- Predicate đủ cụ thể.
- Không truyền null hoặc chuỗi rỗng ngoài ý muốn.
- Đã xác định index/alias mà repository đang dùng.
- Có phân quyền cho người thực hiện thao tác.
- Có log/audit phù hợp với nghiệp vụ.
- Có kế hoạch phục hồi hoặc backup nếu dữ liệu quan trọng.

Ví dụ, thay vì xóa theo category lấy trực tiếp từ request mà không kiểm tra:

~~~java
productRepository.deleteByCategory(request.category());
~~~

hãy validate đầu vào và quyền trước khi thực hiện:

~~~java
if (category == null || category.isBlank()) {
    throw new IllegalArgumentException("Category is required");
}

authorizationService.requireCanDeleteCategory(category);
productRepository.deleteByCategory(category);
~~~

Không thiết kế một method deleteBy... mà điều kiện có thể rỗng rồi vô tình xóa phạm vi rộng. Nếu nghiệp vụ cần xóa nhiều document, cân nhắc thao tác có xác nhận phạm vi, giới hạn batch và quan sát kết quả.

Với xóa theo điều kiện phức tạp hoặc số lượng lớn, Elasticsearch Delete By Query có thể phù hợp hơn, nhưng cần xử lý timeout, version conflict, throttling và kết quả một phần theo API. Đừng giả định derived delete method và Delete By Query có cùng hành vi vận hành.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| PropertyReferenceException | Tên property trong method không tồn tại | Đối chiếu tên field trong domain class |
| Repository khởi tạo lỗi | Predicate hoặc return type không được hỗ trợ | Kiểm tra supported keywords và root cause |
| findBy trả về rỗng | Sai index, mapping, field name hoặc query semantics | Kiểm tra @Document, mapping và document _source |
| findBy trên text không khớp như mong đợi | Analyzer khác với cách người viết kỳ vọng | Kiểm tra mapping và Analyze API |
| term-like query không exact | Field keyword/text hoặc normalizer không phù hợp | Đọc mapping, dùng field đúng semantics |
| countBy chậm | Query chạy trên nhiều shard hoặc filter tốn kém | Đo latency, giới hạn index và tối ưu filter |
| existsBy trả false | Sai field, sai index, routing hoặc dữ liệu chưa hiển thị | Kiểm tra ID/field, alias, routing và refresh |
| deleteBy xóa quá nhiều | Predicate quá rộng hoặc input không được validate | Chạy query đọc trước và kiểm tra phạm vi |
| Page có total chậm | Tính tổng hit tốn tài nguyên | Xem xét Slice/giới hạn total nếu được hỗ trợ |
| Nested property query sai | Mapping object/nested không phù hợp | Kiểm tra mapping và dùng nested query tường minh |

Khi startup lỗi, đọc toàn bộ cause chain. Một repository có thể được scan thành công nhưng thất bại khi Spring phân tích method hoặc tạo query. Không phải mọi lỗi repository đều là lỗi package scanning.

## 15. Quy trình chọn cách khai báo query

Có thể chọn theo thứ tự sau:

1. Nếu điều kiện đơn giản và supported keyword đã rõ, dùng findBy/countBy/existsBy/deleteBy.
2. Nếu cần JSON DSL cố định nhưng muốn giữ method trong repository, dùng @Query.
3. Nếu điều kiện thay đổi theo request, dùng ElasticsearchOperations.
4. Nếu query có aggregation, nested, script, geo hoặc scoring phức tạp, dùng query API tường minh.
5. Nếu cần kiểm soát index đích theo runtime, dùng Operations cùng IndexCoordinates.

Một ví dụ repository tổng hợp:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByCategoryAndActiveTrue(String category);

    Page<Product> findByCategory(
        String category,
        Pageable pageable
    );

    long countByCategory(String category);

    boolean existsBySku(String sku);

    void deleteBySku(String sku);
}
~~~

Đây là danh sách method minh họa. Trước khi đưa vào project, kiểm tra các keyword, kiểu trả về và overload được hỗ trợ bởi phiên bản Spring Data Elasticsearch đang sử dụng.

## 16. Kiểm tra query method bằng integration test

Một unit test có thể xác nhận logic service gọi đúng repository method, nhưng chỉ integration test với Elasticsearch mới kiểm tra được mapping và query thực tế.

Ví dụ:

~~~java
@Test
void shouldFindCountAndCheckExistence() {
    Product product = new Product(
        "P-1001",
        "SKU-1001",
        "Wireless Mouse",
        "accessories",
        259900L,
        true
    );

    productRepository.save(product);

    // Refresh index trước khi kiểm tra query/search-derived methods
    indexOperations.refresh();

    assertThat(productRepository.findBySku("SKU-1001"))
        .hasSize(1);

    assertThat(productRepository.countByCategory("accessories"))
        .isEqualTo(1);

    assertThat(productRepository.existsBySku("SKU-1001"))
        .isTrue();
}
~~~

Đây là ví dụ minh họa; Product constructor, test setup và indexOperations cần khớp với entity/project thực tế. Get theo ID và Search/Count có thời điểm hiển thị khác nhau do Elasticsearch near-real-time refresh. Trong test query method, hãy refresh khi cần quan sát document vừa ghi.

Với deleteBy, test nên xác nhận cả document mục tiêu bị xóa và document không thỏa predicate vẫn còn:

~~~java
@Test
void shouldDeleteOnlyMatchingProducts() {
    productRepository.save(productA);
    productRepository.save(productB);

    indexOperations.refresh();

    productRepository.deleteBySku("SKU-DELETE");

    // Đọc lại theo ID để xác nhận phạm vi xóa.
    assertThat(productRepository.findById("P-DELETE")).isEmpty();
    assertThat(productRepository.findById("P-KEEP")).isPresent();
}
~~~

Nếu kiểm tra bằng Search API ngay sau delete, có thể cần refresh trước khi xác nhận kết quả tìm kiếm.

## 17. Bảng tra cứu nhanh

| Nhu cầu | Method/cách dùng |
|---|---|
| Tìm theo property | findByProperty(...) |
| Kết hợp điều kiện | findByAAndB(...), findByAOrB(...) |
| Tìm và phân trang | findByProperty(..., Pageable) |
| Đếm theo điều kiện | countByProperty(...) |
| Kiểm tra có kết quả | existsByProperty(...) |
| Kiểm tra theo document ID | existsById(id) |
| Xóa theo điều kiện | deleteByProperty(...) nếu phiên bản hỗ trợ |
| Query DSL cố định | @Query |
| Query động hoặc nâng cao | ElasticsearchOperations |
| Chọn index tại runtime | Operations cùng IndexCoordinates |

findBy, countBy, existsBy và deleteBy giúp biểu đạt truy vấn đơn giản ngay trên repository interface. Hãy chọn tiền tố theo kết quả cần nhận, đặt property path đúng với domain model, xác nhận predicate được phiên bản Spring Data Elasticsearch hỗ trợ và hiểu mapping quyết định semantics của query. Với điều kiện phức tạp, query động hoặc thao tác xóa quy mô lớn, chuyển sang @Query hoặc ElasticsearchOperations để kiểm soát DSL và phạm vi tác động rõ ràng.

