# Xử lý kết quả rỗng, nhiều kết quả và lỗi chuyển đổi

Khi truy vấn Elasticsearch bằng Spring Data Elasticsearch, ứng dụng cần xử lý ba tình huống thường gặp: truy vấn không tìm thấy tài liệu, truy vấn trả về nhiều tài liệu hơn dự kiến và dữ liệu từ Elasticsearch không chuyển đổi được thành đối tượng Java. Nếu không xác định rõ hợp đồng kết quả, service có thể gặp **NullPointerException**, lỗi kích thước kết quả hoặc trả dữ liệu không đầy đủ cho API.

Cách xử lý phụ thuộc vào kiểu API đang dùng. Repository thường biểu diễn kết quả đơn bằng **Optional<T>**, collection bằng **List<T>** hoặc **Iterable<T>**, và kết quả phân trang bằng **Page<T>** hoặc **Slice<T>**. **ElasticsearchOperations.get(...)** thường trả về entity hoặc **null**, trong khi **search(...)** trả về **SearchHits<T>**, kể cả khi không có hit. Khi dữ liệu được ánh xạ từ JSON sang Java, **MappingElasticsearchConverter** và các converter của Spring Data chịu trách nhiệm chuyển đổi giá trị; sai kiểu hoặc định dạng có thể làm quá trình đọc thất bại.

Bài này dùng ví dụ index **products**, lớp tài liệu **Product** và các trường SKU, tên, danh mục, giá, trạng thái, ngày tạo. Nội dung tập trung vào cách xác định số lượng kết quả, xử lý trường hợp rỗng, phân biệt lỗi nghiệp vụ với lỗi kỹ thuật và chẩn đoán lỗi chuyển đổi.

## 1. Ba tình huống kết quả cần phân biệt

Một truy vấn có thể dẫn đến các tình huống sau:

1. **Không có tài liệu phù hợp.** Elasticsearch thực thi truy vấn thành công nhưng không có hit.
2. **Có một hoặc nhiều tài liệu.** Kết quả hợp lệ và cần được xử lý theo kiểu trả về.
3. **Không thể đọc hoặc chuyển đổi kết quả.** Request có thể thành công ở phía Elasticsearch nhưng Spring Data không ánh xạ được source sang kiểu Java; hoặc chính Elasticsearch từ chối request do lỗi mapping, query hay kết nối.

Không nên coi cả ba tình huống là “không tìm thấy dữ liệu”. Một collection rỗng là kết quả hợp lệ. Lỗi chuyển đổi là lỗi kỹ thuật cần được ghi nhận và xử lý riêng.

| Tình huống | Ví dụ | Cách biểu diễn thường gặp |
|---|---|---|
| Không tìm thấy một tài liệu | Không có sản phẩm với ID p-9999 | Optional.empty() hoặc null, tùy API |
| Không tìm thấy tài liệu nào trong truy vấn nhiều kết quả | Không có sản phẩm thuộc category unknown | Collection, Page hoặc SearchHits rỗng |
| Tìm thấy đúng một tài liệu | Có một SKU phù hợp | Optional có giá trị hoặc entity |
| Tìm thấy nhiều tài liệu | Nhiều sản phẩm cùng category | List, Iterable, Page, Slice hoặc SearchHits |
| Query đơn trả về nhiều tài liệu | findByCategory khai báo Optional nhưng category có nhiều sản phẩm | Có thể phát sinh IncorrectResultSizeDataAccessException |
| Dữ liệu không ánh xạ được | Ngày có định dạng sai hoặc trường số chứa chuỗi không hợp lệ | Conversion/mapping exception |
| Elasticsearch từ chối ghi | Giá trị không phù hợp mapping strict | Lỗi từ Elasticsearch, thường có thông tin mapper_parsing_exception |

## 2. Hợp đồng kết quả của Repository

Repository method nên khai báo kiểu trả về phù hợp với số lượng tài liệu mà truy vấn có thể tìm thấy.

Ví dụ:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByCategory(String category);

    Page<Product> findByStatus(String status, Pageable pageable);
}
~~~

Các hợp đồng trên có ý nghĩa khác nhau:

- **Optional<Product>** biểu diễn không có hoặc có một Product.
- **List<Product>** biểu diễn không hoặc nhiều Product; khi không có dữ liệu, list rỗng.
- **Page<Product>** biểu diễn một trang kết quả và metadata phân trang.

Đừng khai báo một phương thức trả về một entity đơn nếu điều kiện truy vấn có thể khớp nhiều tài liệu. Nếu SKU được dùng như khóa nghiệp vụ duy nhất, ứng dụng phải bảo đảm dữ liệu không tạo ra nhiều tài liệu có cùng SKU. Elasticsearch không tự tạo unique constraint cho một trường keyword thông thường.

## 3. Xử lý Optional khi tìm một tài liệu

Các phương thức CRUD như **findById(id)** của repository trả về **Optional<T>**. Nếu tài liệu không tồn tại, kết quả là **Optional.empty()**.

~~~java
Optional<Product> result = productRepository.findById("p-1001");

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Không tìm thấy sản phẩm");
}
~~~

Có thể viết ngắn hơn bằng **orElseThrow**:

~~~java
Product product = productRepository.findById("p-1001")
        .orElseThrow(() -> new ProductNotFoundException("p-1001"));
~~~

Hoặc dùng **ifPresent** khi không cần trả kết quả:

~~~java
productRepository.findById("p-1001")
        .ifPresent(product -> sendNotification(product));
~~~

### Không dùng get() của Optional khi chưa kiểm tra

Đoạn mã sau có thể ném **NoSuchElementException** nếu Optional rỗng:

~~~java
Product product = productRepository.findById(id).get();
~~~

Chỉ dùng get() khi đã chứng minh Optional có giá trị. Trong mã nghiệp vụ, **orElseThrow**, **map**, **ifPresent** hoặc kiểm tra **isPresent()** thường diễn đạt ý định rõ hơn.

### Query method trả về entity đơn

Một derived query có thể được khai báo trả về trực tiếp Product:

~~~java
Product findBySku(String sku);
~~~

Với kiểu trả về đơn, trường hợp không có kết quả thường được biểu diễn bằng **null**. Điều này buộc caller phải kiểm tra null. Vì vậy, nếu “không tìm thấy SKU” là tình huống bình thường, **Optional<Product>** thường là hợp đồng an toàn và dễ đọc hơn:

~~~java
Optional<Product> findBySku(String sku);
~~~

Cần phân biệt phương thức query tự định nghĩa với các phương thức CRUD kế thừa. Ví dụ **findById** có hợp đồng Optional được định nghĩa bởi repository API; không suy luận rằng mọi method trả entity đều có cùng hợp đồng.

## 4. Khi truy vấn đơn lại khớp nhiều tài liệu

Một query method trả về Product hoặc Optional<Product> chỉ có thể biểu diễn tối đa một kết quả. Nếu truy vấn thực tế khớp nhiều tài liệu, Spring Data có thể phát sinh **IncorrectResultSizeDataAccessException**.

Ví dụ khai báo không phù hợp:

~~~java
Optional<Product> findByCategory(String category);
~~~

Nếu category accessories có 30 sản phẩm, Optional không thể chứa cả 30 tài liệu. Hãy thay đổi kiểu trả về:

~~~java
List<Product> findByCategory(String category);
~~~

Nếu nghiệp vụ chỉ cần một sản phẩm đầu tiên theo một quy tắc rõ ràng, giới hạn kết quả và xác định thứ tự:

~~~java
Optional<Product> findFirstByCategoryOrderByPriceAsc(String category);
~~~

Cách đặt tên derived query và khả năng hỗ trợ **First**, **Top** hoặc **OrderBy** phụ thuộc phiên bản Spring Data Elasticsearch. Khi cần kiểm soát rõ ràng hơn, truyền Pageable có kích thước 1 hoặc xây dựng query với sort.

Không nên dựa vào thứ tự mặc định của Elasticsearch để chọn “một tài liệu bất kỳ”. Kết quả có thể thay đổi theo score, shard, segment hoặc dữ liệu được cập nhật. Nếu nghiệp vụ cần sản phẩm rẻ nhất, mới nhất hoặc được ưu tiên, hãy khai báo sort tương ứng.

## 5. Xử lý collection rỗng khi tìm nhiều tài liệu

Với truy vấn nhiều kết quả, dùng **List<T>** hoặc **Iterable<T>**. Nếu không có hit, collection trả về rỗng.

~~~java
List<Product> products =
        productRepository.findByCategory("unknown");

if (products.isEmpty()) {
    System.out.println("Danh mục chưa có sản phẩm");
} else {
    products.forEach(product ->
            System.out.println(product.getName()));
}
~~~

Không nên trả null thay cho một collection không có phần tử. Collection rỗng cho phép caller gọi **isEmpty()**, duyệt vòng lặp hoặc chuyển thành response JSON mà không cần kiểm tra null.

Ví dụ service có thể trả danh sách rỗng:

~~~java
public List<Product> findByCategory(String category) {
    return productRepository.findByCategory(category);
}
~~~

Khi không có sản phẩm, controller có thể trả HTTP 200 cùng mảng JSON rỗng, nếu đó là hợp đồng API đã chọn:

~~~json
[]
~~~

Đây thường là cách phù hợp cho endpoint danh sách. Một truy vấn danh sách không có kết quả không đồng nghĩa tài nguyên endpoint không tồn tại.

### findAllById và các ID bị thiếu

**findAllById(ids)** trả về các entity được tìm thấy. Các ID không tồn tại sẽ không tạo ra phần tử null trong collection.

~~~java
List<String> requestedIds =
        List.of("p-1001", "p-1002", "p-9999");

List<Product> found = new ArrayList<>();
productRepository.findAllById(requestedIds).forEach(found::add);
~~~

Nếu cần xác định ID nào bị thiếu, so sánh danh sách ID đầu vào với ID của kết quả:

~~~java
Set<String> foundIds = found.stream()
        .map(Product::getId)
        .collect(Collectors.toSet());

List<String> missingIds = requestedIds.stream()
        .filter(id -> !foundIds.contains(id))
        .toList();
~~~

Thứ tự entity trong kết quả không nhất thiết giống thứ tự ID đầu vào. Nếu thứ tự đầu vào quan trọng, cần dựng lại kết quả theo danh sách ID ban đầu.

## 6. Xử lý Page và Slice rỗng

Khi truy vấn cần phân trang, repository có thể trả về **Page<T>**:

~~~java
Page<Product> findByStatus(String status, Pageable pageable);
~~~

Gọi truy vấn:

~~~java
Page<Product> page = productRepository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20)
);

if (page.isEmpty()) {
    System.out.println("Không có sản phẩm ACTIVE");
} else {
    System.out.println("Số sản phẩm: " + page.getTotalElements());
}
~~~

Một Page rỗng vẫn là một đối tượng Page hợp lệ. Có thể gọi **getContent()**, **getTotalElements()**, **getTotalPages()** và **hasNext()** mà không cần kiểm tra null.

**Slice<T>** phù hợp khi giao diện chỉ cần biết còn trang tiếp theo hay không, không cần tổng số kết quả:

~~~java
Slice<Product> slice = productRepository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20)
);

if (slice.isEmpty()) {
    // Không có phần tử trong lát hiện tại.
}

if (slice.hasNext()) {
    Pageable nextPage = slice.nextPageable();
    // Tải phần kết quả tiếp theo.
}
~~~

Page thường cần thông tin tổng số phần tử để cung cấp metadata đầy đủ. Slice tập trung vào phần nội dung hiện tại và việc còn dữ liệu tiếp hay không. Khả năng hỗ trợ kiểu trả về cụ thể phụ thuộc phiên bản và loại query method.

## 7. Xử lý SearchHits rỗng khi dùng ElasticsearchOperations

Khi dùng **ElasticsearchOperations.search(...)**, kết quả thường là **SearchHits<T>**. SearchHits vẫn được trả về khi không có tài liệu phù hợp; danh sách hit bên trong sẽ rỗng.

~~~java
Query query = new CriteriaQuery(
        Criteria.where("category").is("unknown")
);

SearchHits<Product> searchHits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);

if (searchHits.getSearchHits().isEmpty()) {
    System.out.println("Không tìm thấy sản phẩm");
}
~~~

Để lấy entity từ từng hit:

~~~java
List<Product> products = searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
~~~

SearchHits còn giữ metadata tìm kiếm như ID, score, index nguồn và highlight theo từng hit. Nếu chỉ chuyển thành List<Product>, các metadata đó sẽ không còn nằm trong danh sách entity.

Ví dụ đọc score:

~~~java
for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();

    System.out.println(
            product.getName() + " - score: " + hit.getScore()
    );
}
~~~

Nếu cần phân biệt không có hit với request thất bại, hãy kiểm tra exception riêng. SearchHits rỗng có nghĩa request đã hoàn tất và không trả về hit; lỗi kết nối, lỗi query hoặc lỗi chuyển đổi thường được ném dưới dạng exception.

## 8. Phân biệt get, exists và search khi không có tài liệu

Các API Operations có hợp đồng khác nhau:

| API | Khi không tìm thấy |
|---|---|
| **operations.get(id, Product.class, index)** | Thường trả về null |
| **operations.exists(id, index)** | Trả về false |
| **operations.search(query, Product.class, index)** | Trả về SearchHits có danh sách hit rỗng |
| **repository.findById(id)** | Trả về Optional.empty() |
| **repository.findAllById(ids)** | Trả collection chỉ chứa entity tìm thấy |
| **repository.findByCategory(category)** | Trả collection rỗng nếu không có hit |

Ví dụ đọc bằng Operations:

~~~java
Product product = operations.get(
        "p-9999",
        Product.class,
        IndexCoordinates.of("products")
);

if (product == null) {
    // Không có tài liệu với ID này.
}
~~~

Nếu chỉ cần biết tài liệu tồn tại:

~~~java
boolean exists = operations.exists(
        "p-9999",
        IndexCoordinates.of("products")
);
~~~

Không cần gọi exists() rồi get() nếu mục tiêu cuối cùng là lấy entity. get() đã cho biết tài liệu có tồn tại thông qua kết quả null. Hai request riêng biệt còn tạo ra một khoảng thời gian mà tài liệu có thể bị xóa hoặc thay đổi giữa lần kiểm tra và lần đọc.

## 9. Không nhầm kết quả rỗng với lỗi kỹ thuật

Một trong những lỗi thiết kế nghiêm trọng là bắt mọi exception rồi trả collection rỗng hoặc Optional.empty. Cách này khiến ứng dụng báo “không có dữ liệu” ngay cả khi Elasticsearch đang mất kết nối hoặc mapping bị lỗi.

Phân biệt các nhóm:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Kết quả nghiệp vụ rỗng | Không có sản phẩm phù hợp | Trả Optional rỗng, collection rỗng hoặc 404 theo hợp đồng |
| Lỗi truy vấn | Query DSL sai hoặc field không phù hợp | Sửa query, mapping hoặc dữ liệu đầu vào |
| Lỗi chuyển đổi | Không chuyển được JSON source sang kiểu Java | Kiểm tra field, type, date format và converter |
| Lỗi ghi dữ liệu | Giá trị không phù hợp mapping | Sửa dữ liệu hoặc mapping |
| Lỗi kết nối | Elasticsearch không truy cập được | Retry có kiểm soát, báo lỗi hạ tầng |
| Lỗi xác thực/quyền | Tài khoản không có quyền đọc index | Sửa cấu hình credential hoặc quyền |
| Lỗi quá tải/timeout | Cluster không xử lý request kịp | Kiểm tra tải, timeout và thiết kế query |

Một cách xử lý sai:

~~~java
public List<Product> search(String category) {
    try {
        return productRepository.findByCategory(category);
    } catch (Exception exception) {
        return List.of();
    }
}
~~~

Đoạn mã này che giấu mọi lỗi kỹ thuật. Caller không thể biết danh mục thật sự không có sản phẩm hay Elasticsearch đang gặp sự cố.

Nên để lỗi kỹ thuật được xử lý ở tầng phù hợp, ghi log với ngữ cảnh cần thiết và ánh xạ sang phản hồi API đúng loại.

## 10. Luồng chuyển đổi dữ liệu từ Elasticsearch sang Java

Khi Spring Data Elasticsearch đọc một tài liệu, source JSON cần được chuyển thành object Java. **MappingElasticsearchConverter** sử dụng metadata của entity, annotation và các converter đã đăng ký để thực hiện quá trình này.

Luồng khái quát:

~~~text
Elasticsearch document (_source)
          |
          v
MappingElasticsearchConverter
          |
          +--> Entity metadata
          |
          +--> @Id / @Field / type information
          |
          +--> Custom conversions
          |
          v
Java object (Product)
          |
          v
Service / Repository caller
~~~

Ví dụ source:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5,
  "createdAt": "2026-10-20T09:30:00Z"
}
~~~

Entity tương ứng:

~~~java
import java.time.Instant;

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

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructor, getter và setter.
}
~~~

Spring Data lấy dữ liệu source, nhận diện trường tương ứng và chuyển giá trị sang kiểu Java. Nếu tên trường hoặc kiểu dữ liệu không khớp, object có thể thiếu giá trị hoặc quá trình chuyển đổi có thể phát sinh exception.

## 11. Lỗi tên trường và mapping field

Một nguyên nhân thường gặp là tên trường trong JSON khác tên thuộc tính Java.

Ví dụ source có:

~~~json
{
  "created_at": "2026-10-20T09:30:00Z"
}
~~~

Trong Java, thuộc tính lại tên **createdAt**. Có thể khai báo tên trường rõ ràng:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Nếu không khai báo quy tắc tên phù hợp, converter có thể không tìm thấy giá trị theo tên thuộc tính Java và trường nhận giá trị null hoặc mặc định.

Cần kiểm tra:

- Tên thực tế trong **_source**.
- Tên thuộc tính Java.
- Thuộc tính **name** trong **@Field**.
- Quy tắc naming strategy của ứng dụng.
- Mapping đang tồn tại trên index.

Đừng chỉ kiểm tra annotation trong source code. Mapping thực tế của index có thể cũ hơn entity do index đã được tạo trước khi thay đổi code.

## 12. Lỗi không tương thích kiểu dữ liệu

Dữ liệu trong **_source** có thể không tương thích với kiểu Java.

Ví dụ entity khai báo:

~~~java
@Field(type = FieldType.Double)
private Double price;
~~~

Nhưng một tài liệu cũ có source:

~~~json
{
  "price": "eighty-nine"
}
~~~

Giá trị chuỗi không thể chuyển thành Double theo converter mặc định. Tùy vị trí phát sinh lỗi và phiên bản, ứng dụng có thể nhận **ConversionException**, **MappingException** hoặc exception được bọc trong lớp truy cập dữ liệu.

Một số trường hợp thường gặp:

| Source JSON | Kiểu Java mong đợi | Rủi ro |
|---|---|---|
| price là chuỗi "89.5" | Double | Có thể chuyển đổi được trong một số ngữ cảnh, nhưng nên lưu số JSON đúng kiểu |
| price là chuỗi "unknown" | Double | Không thể chuyển đổi sang số |
| quantity là 12.5 | Integer | Có thể mất phần thập phân hoặc không chuyển đổi được theo converter |
| active là chuỗi "yes" | Boolean | Chuỗi không phải biểu diễn boolean chuẩn |
| createdAt là "20/10/2026" | Instant | Không khớp định dạng ngày giờ mong đợi |
| tags là "keyboard" | List<String> | Source là scalar trong khi Java mong collection |
| address là object JSON | String | Object JSON không tự động trở thành chuỗi theo mọi converter |

Nên thống nhất schema dữ liệu từ đầu. Nếu index đã chứa tài liệu cũ theo định dạng khác, cần có migration hoặc custom converter rõ ràng để đọc tương thích.

## 13. Lỗi ngày giờ và định dạng date

Ngày giờ là nguồn gây lỗi chuyển đổi phổ biến. Elasticsearch mapping có thể chấp nhận một số định dạng, nhưng Java type cũng phải tương thích.

Ví dụ dùng Instant:

~~~java
@Field(type = FieldType.Date)
private Instant createdAt;
~~~

Source nên dùng một định dạng ISO-8601 rõ ràng:

~~~json
{
  "createdAt": "2026-10-20T09:30:00Z"
}
~~~

Nếu dữ liệu cũ dùng định dạng riêng, cần khai báo format phù hợp trong mapping và kiểm tra cách converter đọc giá trị đó. Với annotation Spring Data, có thể chỉ định format:

~~~java
@Field(type = FieldType.Date, format = DateFormat.date_time)
private Instant createdAt;
~~~

Tên format và khả năng hỗ trợ kiểu ngày phụ thuộc phiên bản. Mapping Elasticsearch và converter Java phải thống nhất. Việc Elasticsearch chấp nhận một giá trị khi ghi không tự động bảo đảm converter Java có thể ánh xạ nó vào mọi kiểu thời gian.

Không nên dùng String cho mọi trường ngày giờ chỉ để né lỗi chuyển đổi nếu ứng dụng cần so sánh, range query hoặc xử lý múi giờ. Hãy chọn kiểu thời gian phù hợp và chuẩn hóa định dạng đầu vào.

## 14. Enum và kiểu dữ liệu tùy chỉnh

Enum thường được lưu dưới dạng chuỗi tên hoặc cách biểu diễn được converter cấu hình. Ví dụ:

~~~java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
~~~

Entity:

~~~java
@Field(type = FieldType.Keyword)
private ProductStatus status;
~~~

Source tương ứng:

~~~json
{
  "status": "ACTIVE"
}
~~~

Nếu source chứa giá trị không có trong enum, chẳng hạn ARCHIVED trong khi enum chưa có ARCHIVED, converter có thể phát sinh lỗi khi đọc. Cần xử lý thay đổi enum có kế hoạch: cập nhật enum, chuyển dữ liệu cũ hoặc dùng kiểu dữ liệu trung gian nếu cần tương thích nhiều phiên bản ứng dụng.

Với kiểu dữ liệu riêng như Money, Address hoặc mã định danh dạng value object, có thể đăng ký custom converter để xác định cách ghi và đọc.

## 15. Dùng custom converter cho kiểu dữ liệu riêng

Giả sử ứng dụng có kiểu Money chứa số tiền và đơn vị tiền tệ:

~~~java
public class Money {

    private final double amount;
    private final String currency;

    public Money(double amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public double getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Nếu muốn lưu Money thành chuỗi có định dạng **89.50 USD**, có thể viết converter đọc:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.trim().split("\\s+");

        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Giá trị Money phải có dạng '<amount> <currency>'"
            );
        }

        double amount = Double.parseDouble(parts[0]);
        return new Money(amount, parts[1]);
    }
}
~~~

Converter ghi:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.getAmount() + " " + source.getCurrency();
    }
}
~~~

Đăng ký các converter thông qua **ElasticsearchCustomConversions** trong cấu hình Spring Data Elasticsearch của dự án:

~~~java
new ElasticsearchCustomConversions(
        List.of(
                new StringToMoneyConverter(),
                new MoneyToStringConverter()
        )
);
~~~

Đây là phần tạo đối tượng conversions; ứng dụng cần đưa đối tượng đó vào extension point cấu hình custom conversions của phiên bản Spring Data Elasticsearch đang dùng. Cách khai báo bean hoặc override cấu hình phụ thuộc cấu hình Spring Boot và phiên bản thư viện. Không chỉ tạo converter class mà quên đăng ký, vì khi đó MappingElasticsearchConverter sẽ không biết phải sử dụng converter đó.

Custom converter nên xác thực dữ liệu và đưa ra lỗi có thông tin đủ để chẩn đoán. Không nên âm thầm chuyển giá trị sai thành 0 hoặc một giá trị mặc định vì có thể làm sai dữ liệu nghiệp vụ.

## 16. Phân biệt lỗi chuyển đổi khi đọc và lỗi mapping khi ghi

Hai nhóm lỗi có thể xuất hiện ở những thời điểm khác nhau:

**Lỗi chuyển đổi khi đọc**

- Elasticsearch trả source.
- Spring Data cố ánh xạ source sang entity.
- Một trường có kiểu hoặc định dạng không tương thích.
- Converter phát sinh exception.

**Lỗi mapping khi ghi**

- Ứng dụng gửi tài liệu lên Elasticsearch.
- Elasticsearch kiểm tra mapping của index.
- Giá trị không phù hợp kiểu trường hoặc mapping đặt **dynamic: strict**.
- Elasticsearch từ chối document và trả lỗi như **mapper_parsing_exception**.

Ví dụ mapping strict:

~~~json
{
  "dynamic": "strict",
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    }
  }
}
~~~

Nếu ứng dụng gửi thêm trường không được khai báo, Elasticsearch có thể từ chối tài liệu vì dynamic strict. Đây là lỗi ở phía Elasticsearch khi ghi, không phải lỗi chuyển đổi source thành Java khi đọc.

Cần xem exception gốc và thời điểm phát sinh để phân biệt hai nhóm. Sửa converter sẽ không giải quyết một mapping strict từ chối trường mới; sửa mapping cũng không tự giải quyết một chuỗi ngày sai định dạng trong source cũ.

## 17. Kiểm tra source và mapping khi gặp lỗi

Khi một tài liệu không ánh xạ được, hãy kiểm tra dữ liệu thực tế trước.

Đọc mapping:

~~~http
GET /products/_mapping
~~~

Đọc tài liệu theo ID:

~~~http
GET /products/_doc/p-1001
~~~

Kiểm tra một số điểm:

- Trường có tồn tại trong **_source** không?
- Giá trị là string, number, boolean, array hay object?
- Tên trường có khớp với **@Field(name=...)** không?
- Mapping có đúng kiểu dữ liệu không?
- Date format có chấp nhận giá trị không?
- Entity có dùng kiểu Java phù hợp không?
- Custom converter đã được đăng ký chưa?
- Tài liệu có được ghi bởi phiên bản ứng dụng cũ với schema khác không?

Nếu mapping đúng nhưng một vài tài liệu cũ có dữ liệu không đồng nhất, có thể cần sửa dữ liệu, chạy migration hoặc xây dựng converter tương thích. Không nên thay kiểu Java để che giấu vấn đề nếu điều đó làm mất khả năng kiểm tra dữ liệu.

## 18. _source bị tắt hoặc bị lọc

Spring Data thường cần **_source** để chuyển tài liệu thành entity. Nếu index được tạo với _source bị disabled, hoặc request chỉ yêu cầu một phần source, entity có thể không được điền đầy đủ.

Ví dụ mapping tắt source:

~~~json
{
  "mappings": {
    "_source": {
      "enabled": false
    },
    "properties": {
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

Khi _source không được lưu, Elasticsearch không thể trả lại JSON gốc theo cách thông thường. Những thao tác cần chuyển source thành Product sẽ bị hạn chế hoặc không thể khôi phục các thuộc tính entity như mong đợi.

Source filtering trong một search request cũng có thể chỉ trả một số trường:

~~~http
POST /products/_search
{
  "_source": [
    "sku",
    "name"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Nếu Product có thêm price và category, các trường đó có thể không được điền trong kết quả vì request không yêu cầu chúng. Đây không nhất thiết là lỗi converter; dữ liệu source đã bị giới hạn từ request.

Khi cần ánh xạ đầy đủ entity, hãy bảo đảm request trả đủ source fields hoặc dùng DTO phù hợp với tập trường được chọn.

## 19. Xây dựng service xử lý kết quả và lỗi rõ ràng

Một service có thể đóng gói quy tắc không tìm thấy và giữ nguyên lỗi kỹ thuật:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product getRequiredById(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }

    public Optional<Product> findById(String id) {
        return repository.findById(id);
    }

    public List<Product> findByCategory(String category) {
        return repository.findByCategory(category);
    }

    public Optional<Product> findBySku(String sku) {
        return repository.findBySku(sku);
    }
}
~~~

Service không cần bắt DataAccessException chỉ để trả collection rỗng. Lỗi truy cập dữ liệu nên được xử lý tại nơi có thể ghi log, gắn correlation ID và chuyển thành phản hồi phù hợp.

Nếu cần bổ sung ngữ cảnh cho lỗi, có thể bắt exception cụ thể rồi ném lại exception nghiệp vụ/hạ tầng có cause:

~~~java
try {
    return repository.findByCategory(category);
} catch (DataAccessException exception) {
    throw new ProductSearchException(
            "Không thể tìm sản phẩm theo danh mục " + category,
            exception
    );
}
~~~

Không nên bắt Exception chung rồi bỏ qua cause. Cause chứa thông tin cần thiết để xác định lỗi kết nối, query, mapping hoặc converter.

## 20. Ánh xạ kết quả sang HTTP response

API nên phản ánh đúng hợp đồng dữ liệu.

Một số quy ước thường dùng:

| Trường hợp | HTTP response thường phù hợp |
|---|---|
| GET một tài nguyên theo ID và không tồn tại | 404 Not Found |
| Tìm danh sách nhưng không có phần tử | 200 OK với [] |
| Tìm một tài nguyên theo điều kiện và không có kết quả | 404 hoặc 204, tùy hợp đồng endpoint |
| Query đầu vào không hợp lệ | 400 Bad Request |
| Elasticsearch không truy cập được | 503 Service Unavailable hoặc lỗi gateway phù hợp |
| Lỗi mapping/conversion không dự kiến | 500 Internal Server Error |
| Request thành công và có dữ liệu | 200 OK |

Ví dụ controller lấy một sản phẩm:

~~~java
@GetMapping("/products/{id}")
public ResponseEntity<Product> getById(@PathVariable String id) {
    Product product = service.getRequiredById(id);
    return ResponseEntity.ok(product);
}
~~~

Exception handler:

~~~java
@RestControllerAdvice
public class ProductApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<String> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(exception.getMessage());
    }
}
~~~

Đối với endpoint danh sách:

~~~java
@GetMapping("/products")
public ResponseEntity<List<Product>> findByCategory(
        @RequestParam String category) {
    return ResponseEntity.ok(service.findByCategory(category));
}
~~~

Nếu không có sản phẩm, response body là mảng rỗng. Không nên biến lỗi converter thành HTTP 404 vì tài liệu có thể tồn tại nhưng ứng dụng không đọc được.

Không trả stack trace, thông tin kết nối hoặc chi tiết nội bộ Elasticsearch cho client. Ghi log ở server với request ID và exception cause; trả thông báo phù hợp với hợp đồng API.

## 21. Kiểm tra kết quả trong kiểm thử

Có thể viết test cho ba nhóm chính: kết quả rỗng, nhiều kết quả và lỗi chuyển đổi.

### Kiểm tra Optional rỗng

~~~java
@Test
void findByIdReturnsEmptyWhenProductDoesNotExist() {
    when(productRepository.findById("missing"))
            .thenReturn(Optional.empty());

    assertTrue(productService.findById("missing").isEmpty());
}
~~~

### Kiểm tra collection rỗng

~~~java
@Test
void findByCategoryReturnsEmptyListWhenNoProductMatches() {
    when(productRepository.findByCategory("unknown"))
            .thenReturn(List.of());

    assertTrue(productService.findByCategory("unknown").isEmpty());
}
~~~

### Kiểm tra nhiều kết quả

~~~java
@Test
void findByCategoryReturnsAllMatchingProducts() {
    List<Product> products = List.of(
            new Product("p-1", "KB-1", "Keyboard", "accessories", 80.0),
            new Product("p-2", "MS-2", "Mouse", "accessories", 25.0)
    );

    when(productRepository.findByCategory("accessories"))
            .thenReturn(products);

    assertEquals(
            2,
            productService.findByCategory("accessories").size()
    );
}
~~~

### Kiểm tra lỗi không bị biến thành kết quả rỗng

~~~java
@Test
void searchFailureIsNotReturnedAsEmptyList() {
    when(productRepository.findByCategory("accessories"))
            .thenThrow(new DataAccessResourceFailureException(
                    "Elasticsearch unavailable"
            ));

    assertThrows(
            DataAccessException.class,
            () -> productService.findByCategory("accessories")
    );
}
~~~

Các test trên minh họa hợp đồng service bằng mock. Để kiểm tra converter và mapping thật, cần integration test với Elasticsearch tương thích, tạo index theo mapping dự kiến và đọc/ghi tài liệu có dữ liệu đại diện.

## 22. Quy trình chẩn đoán lỗi chuyển đổi

Khi một truy vấn báo lỗi trong lúc đọc kết quả, có thể điều tra theo trình tự:

1. **Xác định request đã thành công chưa.** Phân biệt lỗi HTTP/Elasticsearch với lỗi xảy ra sau khi nhận response.
2. **Đọc exception gốc.** Tìm ConversionException, MappingException, ConverterNotFoundException hoặc thông tin lỗi từ client.
3. **Xác định tài liệu và trường gây lỗi.** Kiểm tra ID, index, tên field và giá trị source.
4. **Đối chiếu entity.** Kiểm tra @Id, @Field, kiểu Java và cấu trúc nested object.
5. **Đọc mapping thực tế.** Không giả định mapping trong code đã được áp dụng lên index đang chạy.
6. **Kiểm tra date, enum và collection.** Đây là các kiểu thường có dữ liệu không đồng nhất giữa các phiên bản ứng dụng.
7. **Kiểm tra custom conversions.** Xác nhận converter đã được đăng ký và có cả chiều đọc/ghi khi cần.
8. **Kiểm tra _source.** Xác nhận source được lưu và request trả đủ trường cần ánh xạ.
9. **Tạo test với source gây lỗi.** Tái hiện trên môi trường phát triển để xác định nguyên nhân.
10. **Sửa dữ liệu hoặc schema có kế hoạch.** Không âm thầm bỏ qua trường sai nếu nó có ý nghĩa nghiệp vụ.

Tên exception cụ thể có thể khác theo phiên bản Spring Data Elasticsearch, Spring Data Commons và Elasticsearch Java Client. Hãy xem cause chain thay vì chỉ dựa vào lớp exception ngoài cùng.

## 23. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| NullPointerException khi dùng kết quả get | operations.get(...) trả null khi ID không tồn tại | Kiểm tra null hoặc đóng gói bằng exception nghiệp vụ |
| NoSuchElementException | Gọi Optional.get() khi Optional rỗng | Dùng orElseThrow, map hoặc kiểm tra isPresent() |
| IncorrectResultSizeDataAccessException | Query trả entity/Optional đơn nhưng khớp nhiều tài liệu | Đổi sang List/Page hoặc giới hạn và sort rõ ràng |
| Collection không có phần tử | Truy vấn thành công nhưng không có hit | Xử lý collection rỗng như kết quả hợp lệ |
| Page rỗng | Không có tài liệu trong trang hoặc điều kiện query không khớp | Kiểm tra isEmpty() và tham số Pageable |
| SearchHits rỗng | Search không có hit phù hợp | Kiểm tra getSearchHits().isEmpty() |
| ConversionException hoặc MappingException | Source không tương thích kiểu entity | Kiểm tra source, mapping và converter |
| Không đọc được ngày | Date format khác với kiểu Java mong đợi | Chuẩn hóa ISO-8601 hoặc cấu hình date format thống nhất |
| Enum gây lỗi | Source chứa giá trị chưa có trong enum | Đồng bộ enum và dữ liệu cũ hoặc dùng converter |
| Thuộc tính Java luôn null | Tên source field khác tên thuộc tính hoặc source bị lọc | Kiểm tra @Field(name=...) và _source |
| Ghi tài liệu báo mapper_parsing_exception | Giá trị không phù hợp mapping hoặc dynamic strict | Sửa dữ liệu, entity hoặc mapping |
| Tìm kiếm báo lỗi kết nối nhưng service trả danh sách rỗng | Exception bị bắt quá rộng | Giữ nguyên lỗi kỹ thuật và xử lý riêng |

## 24. Nguyên tắc thiết kế hợp đồng kết quả

Khi xây dựng repository và service, hãy áp dụng các nguyên tắc sau:

- Dùng **Optional<T>** khi truy vấn mong đợi tối đa một tài liệu và không tồn tại là trường hợp hợp lệ.
- Dùng **List<T>** hoặc **Iterable<T>** khi truy vấn có thể trả nhiều tài liệu.
- Dùng **Page<T>** hoặc **Slice<T>** khi cần phân trang.
- Dùng **SearchHits<T>** khi cần score, highlight hoặc metadata của từng hit.
- Kiểm tra null với **ElasticsearchOperations.get(...)**.
- Xem collection, Page và SearchHits rỗng là kết quả bình thường.
- Không khai báo kiểu trả về đơn cho điều kiện có thể khớp nhiều tài liệu.
- Không biến lỗi query, kết nối hoặc converter thành kết quả rỗng.
- Giữ mapping Elasticsearch và kiểu Java tương thích.
- Chuẩn hóa ngày giờ, enum, collection và value object.
- Đăng ký custom converter khi kiểu dữ liệu cần quy tắc chuyển đổi riêng.
- Kiểm tra _source và mapping thực tế khi entity bị thiếu trường.

Xử lý kết quả tìm kiếm tốt bắt đầu từ hợp đồng kiểu trả về. **Optional** biểu diễn không có hoặc có một tài liệu; collection, Page và SearchHits biểu diễn tập kết quả có thể rỗng; query đơn khớp nhiều tài liệu cần được thiết kế lại hoặc giới hạn rõ ràng. Lỗi chuyển đổi xảy ra ở một lớp khác: Spring Data không thể ánh xạ source sang entity theo metadata và converter hiện có. Khi tách bạch kết quả rỗng, sai số lượng và lỗi chuyển đổi, ứng dụng sẽ trả phản hồi đúng hơn, đồng thời việc chẩn đoán sự cố Elasticsearch cũng rõ ràng hơn.
