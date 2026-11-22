# Thực hiện lưu, đọc, tìm kiếm và xóa tài liệu

Spring Data Elasticsearch giúp ứng dụng Spring làm việc với Elasticsearch thông qua các đối tượng Java. Thay vì tự tạo HTTP request cho từng thao tác, ta khai báo lớp mô tả tài liệu, repository hoặc sử dụng **ElasticsearchOperations** để lưu, đọc, tìm kiếm và xóa dữ liệu.

Trong bài này, ta xây dựng ví dụ quản lý tài liệu sản phẩm trong index **products**. Một tài liệu có mã định danh, tên, danh mục, giá và thời điểm tạo. Các thao tác được trình bày theo luồng thường gặp: kết nối Elasticsearch, ánh xạ lớp Java, ghi dữ liệu, truy vấn và xóa dữ liệu.

## 1. Chuẩn bị kết nối Elasticsearch

Ứng dụng cần có Elasticsearch đang hoạt động và dependency Spring Data Elasticsearch tương thích với phiên bản Spring Boot đang dùng. Với dự án Spring Boot, có thể thêm starter sau vào Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>
~~~

Nên để Spring Boot quản lý phiên bản dependency thông qua dependency management của dự án. Tránh tự ghép một phiên bản Spring Data Elasticsearch với một phiên bản Elasticsearch Java Client không tương thích.

Cấu hình địa chỉ máy chủ trong **application.yml**:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Nếu Elasticsearch yêu cầu xác thực, cấu hình thêm thông tin đăng nhập bằng cơ chế quản lý bí mật phù hợp với môi trường triển khai:

~~~yaml
spring:
  elasticsearch:
    uris: https://elasticsearch.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
~~~

Không đưa mật khẩu thật vào Git. Với môi trường có TLS, cần cấu hình chứng chỉ và cơ chế xác thực theo yêu cầu của cụm Elasticsearch. Tên thuộc tính và cách cấu hình chi tiết có thể khác giữa các thế hệ Spring Boot; hãy dùng tài liệu tương ứng với phiên bản dự án.

Khi ứng dụng khởi động, Spring Boot tạo các thành phần kết nối cần thiết để Spring Data Elasticsearch sử dụng. Trong phần lớn ứng dụng, ta chỉ cần inject repository hoặc **ElasticsearchOperations**, không cần tự tạo HTTP client cho từng request.

## 2. Khai báo lớp tài liệu và ánh xạ trường

Elasticsearch lưu dữ liệu dưới dạng tài liệu JSON trong một index. Spring Data Elasticsearch ánh xạ tài liệu đó với một lớp Java thông qua các annotation trong package **org.springframework.data.elasticsearch.annotations**.

Ví dụ lớp **Product**:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date, format = DateFormat.date_optional_time)
    private Instant createdAt;

    public Product() {
    }

    public Product(String id, String name, String category,
                   Double price, Instant createdAt) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public Double getPrice() {
        return price;
    }

    public void setPrice(Double price) {
        this.price = price;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Các annotation chính có ý nghĩa như sau:

- **@Document(indexName = "products")** chỉ định index chứa các tài liệu thuộc lớp này.
- **@Id** đánh dấu trường được dùng làm **_id** của tài liệu Elasticsearch.
- **@Field(type = FieldType.Text)** khai báo trường văn bản được phân tích thành các token, phù hợp với tìm kiếm toàn văn.
- **@Field(type = FieldType.Keyword)** khai báo trường có giá trị nguyên vẹn, phù hợp với lọc chính xác, nhóm và sắp xếp.
- **@Field(type = FieldType.Double)** ánh xạ trường số thực.
- **@Field(type = FieldType.Date, ...)** khai báo trường ngày giờ.

Chọn kiểu dữ liệu dựa trên cách truy vấn. Chẳng hạn, tên sản phẩm thường là **Text** vì người dùng có thể tìm theo một phần nội dung; mã sản phẩm, trạng thái và danh mục thường là **Keyword** vì cần so khớp chính xác. Nếu cần vừa tìm toàn văn vừa lọc chính xác trên cùng một nội dung, có thể khai báo multi-field với một trường **text** và một trường con **keyword**.

**Double** thuận tiện cho ví dụ, nhưng không phải lựa chọn mặc định tốt nhất cho mọi dữ liệu tiền tệ. Với giá trị cần độ chính xác thập phân, hãy cân nhắc lưu theo đơn vị nhỏ nhất dưới dạng số nguyên hoặc thiết kế mapping **scaled_float** với hệ số phù hợp.

### Tạo index và mapping

Index phải tồn tại trước khi ghi tài liệu. Tùy cấu hình, Spring Data Elasticsearch có thể tạo index từ metadata của **@Document**. Trong ứng dụng cần kiểm soát mapping rõ ràng, có thể chủ động tạo index và mapping bằng **IndexOperations**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void initialize() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.create();
            indexOperations.putMapping();
        }
    }
}
~~~

Đoạn mã trên minh họa thứ tự thao tác: kiểm tra index, tạo index rồi áp dụng mapping được suy ra từ lớp tài liệu. Có thể đặt logic khởi tạo trong thành phần chạy khi ứng dụng khởi động, chẳng hạn một bean triển khai **ApplicationRunner**.

Trong môi trường thực tế, mapping nên được thiết kế và quản lý có chủ đích. Thay đổi annotation trong mã Java không tự động chuyển đổi dữ liệu đã tồn tại theo mapping mới. Khi cần đổi kiểu trường hoặc analyzer, thường phải tạo index mới với mapping đúng, chuyển dữ liệu sang index mới rồi chuyển alias hoặc cấu hình ứng dụng sang index đó.

## 3. Tạo repository để thao tác dữ liệu

Spring Data Elasticsearch cung cấp **ElasticsearchRepository**, cho phép dùng các phương thức CRUD có sẵn và khai báo truy vấn dựa trên tên phương thức.

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndPriceBetween(
            String category,
            Double minPrice,
            Double maxPrice);
}
~~~

Tham số kiểu thứ nhất là lớp tài liệu **Product**; tham số kiểu thứ hai là kiểu của trường định danh, ở đây là **String**.

Kế thừa **ElasticsearchRepository** cung cấp sẵn các thao tác phổ biến:

| Phương thức | Mục đích |
|---|---|
| **save(entity)** | Lưu tài liệu; nếu đã có tài liệu cùng ID thì ghi lại tài liệu đó |
| **saveAll(entities)** | Lưu một tập tài liệu |
| **findById(id)** | Đọc một tài liệu theo ID, trả về **Optional** |
| **findAll()** | Đọc các tài liệu |
| **existsById(id)** | Kiểm tra ID có tồn tại hay không |
| **count()** | Đếm tài liệu |
| **deleteById(id)** | Xóa tài liệu theo ID |
| **delete(entity)** | Xóa tài liệu tương ứng với entity |
| **deleteAll()** | Xóa toàn bộ tài liệu thuộc repository |

Các phương thức tự khai báo như **findByCategory** và **findByCategoryAndPriceBetween** được Spring Data phân tích tên để tạo truy vấn. Tên thuộc tính phải khớp với thuộc tính của lớp tài liệu. Các toán tử như **And**, **Or**, **Between**, **LessThan**, **GreaterThan**, **In** và **Containing** có thể dùng để biểu đạt điều kiện, tùy khả năng hỗ trợ của phiên bản Spring Data Elasticsearch.

## 4. Lưu tài liệu mới

Để lưu một sản phẩm, tạo đối tượng Java rồi truyền cho **save**:

~~~java
import java.time.Instant;
import java.util.UUID;

Product product = new Product(
        UUID.randomUUID().toString(),
        "Mechanical Keyboard",
        "accessories",
        89.50,
        Instant.now()
);

Product savedProduct = productRepository.save(product);
~~~

Spring Data chuyển đối tượng thành tài liệu JSON và gửi thao tác ghi đến index được khai báo trong **@Document**. Ví dụ tài liệu tương ứng có dạng:

~~~json
{
  "id": "a-generated-id",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5,
  "createdAt": "2026-11-13T12:00:00Z"
}
~~~

Giá trị ID trong ví dụ JSON chỉ mang tính minh họa. Khi ứng dụng tự tạo ID, cần bảo đảm ID đó duy nhất trong index. Nếu không tự gán ID, Elasticsearch có thể tạo ID cho tài liệu theo cơ chế của nó, nhưng việc quản lý và cập nhật tài liệu thường dễ kiểm soát hơn khi ứng dụng có ID ổn định.

**save** là thao tác ghi tài liệu theo ID. Nếu ID chưa tồn tại, tài liệu mới được tạo; nếu ID đã tồn tại, nội dung tài liệu được ghi lại theo dữ liệu của đối tượng được truyền vào. Vì vậy, khi cập nhật một tài liệu, hãy nạp dữ liệu hiện tại trước nếu cần giữ lại các trường khác.

## 5. Đọc tài liệu

### Đọc theo ID

Phương thức **findById** trả về **Optional<Product>** vì tài liệu có thể không tồn tại:

~~~java
Optional<Product> result = productRepository.findById(productId);

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Không tìm thấy sản phẩm");
}
~~~

Có thể viết gọn bằng **orElse**, **orElseGet** hoặc **orElseThrow** tùy cách xử lý trường hợp không tìm thấy:

~~~java
Product product = productRepository.findById(productId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy sản phẩm: " + productId));
~~~

### Đọc nhiều tài liệu

**findAll()** trả về các tài liệu trong index tương ứng:

~~~java
Iterable<Product> products = productRepository.findAll();

for (Product product : products) {
    System.out.println(product.getName());
}
~~~

Không nên gọi **findAll()** để tải toàn bộ một index lớn vào bộ nhớ. Khi dữ liệu nhiều, hãy dùng phân trang hoặc một truy vấn giới hạn kết quả.

### Đọc có phân trang và sắp xếp

Repository hỗ trợ các truy vấn nhận **Pageable**. Ví dụ bổ sung phương thức sau vào **ProductRepository**:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Product> findByCategory(String category, Pageable pageable);
~~~

Gọi phương thức với trang đầu tiên gồm 20 phần tử, sắp xếp giá tăng dần:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest pageRequest = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "price")
);

Page<Product> page =
        productRepository.findByCategory("accessories", pageRequest);

List<Product> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Số trang bắt đầu từ **0**. Phân trang theo số trang phù hợp với danh sách vừa phải. Với tập kết quả rất lớn hoặc cần duyệt ổn định qua nhiều trang, nên xem xét cơ chế **search_after** và thứ tự sắp xếp có trường phân biệt rõ ràng.

## 6. Tìm kiếm tài liệu

Tìm kiếm trong Elasticsearch phụ thuộc vào kiểu mapping của trường và loại truy vấn. Cần phân biệt tìm kiếm toàn văn với so khớp chính xác:

- **match** thường dùng cho trường **text**; nội dung truy vấn được phân tích theo analyzer.
- **term** dùng để so khớp một giá trị chính xác, thường áp dụng cho trường **keyword**, mã định danh hoặc giá trị trạng thái.
- **range** dùng để lọc theo khoảng số hoặc thời gian.
- **bool** kết hợp nhiều điều kiện bằng **must**, **should**, **filter** và **must_not**.

### Tìm kiếm bằng tên phương thức repository

Ví dụ hai phương thức đã khai báo trong **ProductRepository**:

~~~java
List<Product> accessories =
        productRepository.findByCategory("accessories");

List<Product> affordableAccessories =
        productRepository.findByCategoryAndPriceBetween(
                "accessories", 20.0, 100.0);
~~~

Truy vấn thứ hai kết hợp điều kiện danh mục và khoảng giá. Nó phù hợp khi điều kiện tìm kiếm tương đối cố định và có thể biểu đạt rõ qua tên phương thức.

### Tìm kiếm bằng @Query

Khi cần viết truy vấn Elasticsearch Query DSL trực tiếp, có thể dùng annotation **@Query**:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<Product> searchByName(String text);
}
~~~

Chuỗi JSON trong annotation là phần truy vấn Query DSL; **?0** được thay bằng tham số thứ nhất của phương thức. Truy vấn **match** phù hợp với trường **name** được ánh xạ kiểu **text**. Cần giữ đúng cú pháp JSON và tên trường trong mapping.

### Tìm kiếm linh hoạt bằng ElasticsearchOperations

Khi truy vấn có nhiều điều kiện hoặc được xây dựng động theo tham số người dùng, **ElasticsearchOperations** cho phép tạo query trong mã Java. Ví dụ sau dùng API **NativeQuery** của Spring Data Elasticsearch 5.x với Elasticsearch Java API Client:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<Product> searchByName(String text) {
        NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q.match(m -> m
                        .field("name")
                        .query(text)))
                .withPageable(PageRequest.of(0, 10))
                .build();

        SearchHits<Product> hits =
                operations.search(query, Product.class);

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .collect(Collectors.toList());
    }
}
~~~

Trong ví dụ:

1. **NativeQuery.builder()** tạo bộ dựng truy vấn.
2. **withQuery(...)** khai báo truy vấn **match** trên trường **name**.
3. **withPageable(...)** giới hạn kết quả ở 10 tài liệu đầu tiên.
4. **operations.search(query, Product.class)** thực thi truy vấn và ánh xạ kết quả về **Product**.
5. **SearchHits** chứa các **SearchHit**; mỗi hit có nội dung tài liệu cùng metadata như ID, điểm liên quan và thông tin highlight nếu truy vấn yêu cầu.

Có thể mở rộng query bằng cách kết hợp điều kiện **bool**, lọc theo danh mục, giới hạn khoảng giá hoặc sắp xếp. Ví dụ, trường danh mục nên dùng điều kiện chính xác trên mapping **keyword**, còn tên sản phẩm nên dùng **match** trên mapping **text**.

Lưu ý: **NativeQuery** trong ví dụ thuộc API Spring Data Elasticsearch 5.x. Các dự án dùng phiên bản cũ hơn có thể sử dụng API truy vấn khác. Hãy kiểm tra package và tài liệu đúng phiên bản thay vì sao chép nguyên mã của một thế hệ thư viện sang thế hệ khác.

## 7. Cập nhật tài liệu

Cách dễ hiểu nhất để cập nhật một tài liệu là đọc theo ID, thay đổi thuộc tính cần thiết rồi gọi **save**:

~~~java
Product product = productRepository.findById(productId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy sản phẩm: " + productId));

product.setPrice(79.90);
productRepository.save(product);
~~~

Vì **save** ghi lại tài liệu theo ID, đối tượng được gửi cần có đầy đủ các trường mà ứng dụng muốn giữ. Nếu tạo một đối tượng mới chỉ chứa ID và một trường thay đổi rồi gọi **save**, các trường không có trong đối tượng có thể bị mất khỏi tài liệu đã lưu.

Nếu chỉ muốn cập nhật một vài trường mà không đọc toàn bộ tài liệu, có thể dùng API cập nhật của **ElasticsearchOperations** với **UpdateQuery**. Cách dựng **Document**, **UpdateQuery** và chỉ định **IndexCoordinates** phụ thuộc phiên bản Spring Data Elasticsearch. Chỉ dùng cập nhật từng phần khi đã xác định rõ hành vi với trường bị thiếu, trường null và tài liệu không tồn tại.

## 8. Xóa tài liệu

### Xóa theo ID

Dùng **deleteById** khi đã biết ID của tài liệu:

~~~java
productRepository.deleteById(productId);
~~~

Có thể kiểm tra trước khi xóa nếu nghiệp vụ cần phân biệt trường hợp không tồn tại:

~~~java
if (productRepository.existsById(productId)) {
    productRepository.deleteById(productId);
}
~~~

Việc kiểm tra trước tạo thêm một lần truy vấn và tài liệu vẫn có thể thay đổi giữa hai thao tác. Nếu không cần thông báo riêng cho trường hợp không tồn tại, gọi thẳng **deleteById** thường đơn giản hơn.

### Xóa đối tượng hoặc một tập ID

~~~java
productRepository.delete(product);
productRepository.deleteAllById(productIds);
~~~

**delete(entity)** xóa tài liệu theo định danh của đối tượng. **deleteAllById** xóa các tài liệu có ID nằm trong tập được truyền vào.

### Xóa toàn bộ tài liệu

~~~java
productRepository.deleteAll();
~~~

**deleteAll()** có phạm vi ảnh hưởng lớn vì xóa tất cả tài liệu thuộc repository. Chỉ gọi khi nghiệp vụ thực sự yêu cầu làm rỗng tập dữ liệu, chẳng hạn trong môi trường thử nghiệm hoặc tác vụ quản trị đã được kiểm soát. Không đặt lời gọi này trong luồng xử lý thông thường của một request người dùng.

Nếu cần xóa theo điều kiện, hãy tạo truy vấn xóa theo query bằng API delete-by-query mà phiên bản Spring Data Elasticsearch đang dùng hỗ trợ. Điều kiện phải được kiểm tra kỹ trước khi thực thi vì thao tác có thể xóa nhiều tài liệu cùng lúc.

## 9. Gom các thao tác vào service

Trong ứng dụng Spring, controller thường gọi service; service xử lý quy tắc nghiệp vụ và sử dụng repository. Ví dụ service đơn giản:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(Product product) {
        if (product.getId() == null || product.getId().isBlank()) {
            product.setId(UUID.randomUUID().toString());
        }
        return repository.save(product);
    }

    public Optional<Product> getById(String id) {
        return repository.findById(id);
    }

    public List<Product> getAll() {
        List<Product> result = new ArrayList<>();
        repository.findAll().forEach(result::add);
        return result;
    }

    public Product updatePrice(String id, Double newPrice) {
        Product product = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy sản phẩm: " + id));

        product.setPrice(newPrice);
        return repository.save(product);
    }

    public void delete(String id) {
        repository.deleteById(id);
    }
}
~~~

Service này minh họa cách tổ chức trách nhiệm; ứng dụng thực tế cần bổ sung kiểm tra dữ liệu đầu vào, quy tắc giá hợp lệ, xử lý ngoại lệ và cách trả lỗi phù hợp với API. Nếu ID được tạo ở tầng khác hoặc có quy tắc định danh riêng, hãy áp dụng quy tắc đó thay cho UUID trong ví dụ.

## 10. Hiểu tính nhất quán khi ghi và tìm kiếm

Elasticsearch là hệ thống tìm kiếm gần thời gian thực. Sau khi ghi hoặc xóa tài liệu, thay đổi có thể chưa xuất hiện ngay trong kết quả tìm kiếm vì index cần được refresh. Do đó, một thao tác **save** thành công không có nghĩa mọi truy vấn tìm kiếm kế tiếp sẽ lập tức nhìn thấy tài liệu đó.

Khi kiểm thử, tránh giả định rằng ghi xong là tìm thấy ngay bằng truy vấn toàn văn. Nếu bài kiểm thử cần đọc lại ngay, hãy dùng cơ chế refresh phù hợp với phiên bản và cấu hình đang chạy. Không nên ép refresh sau mọi lần ghi trong môi trường tải cao vì có thể làm giảm hiệu năng.

Cũng cần phân biệt:

- Đọc theo ID kiểm tra tài liệu bằng định danh.
- Tìm kiếm toàn văn chạy trên inverted index và chịu ảnh hưởng của analyzer.
- Truy vấn **keyword** so khớp giá trị nguyên vẹn, phù hợp với bộ lọc chính xác.
- Kết quả tìm kiếm có thể được xếp hạng theo điểm liên quan, không nhất thiết theo thứ tự tài liệu được ghi.

## 11. Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không kết nối được Elasticsearch | Sai URI, máy chủ chưa chạy, lỗi mạng hoặc TLS | Kiểm tra địa chỉ, cổng, log kết nối và chứng chỉ |
| Lỗi xác thực | Thiếu hoặc sai thông tin đăng nhập | Kiểm tra cấu hình môi trường và quyền của tài khoản |
| Index chưa tồn tại | Index chưa được tạo hoặc tên index sai | Kiểm tra **@Document** và quá trình khởi tạo index |
| Lỗi mapping khi ghi | Giá trị Java không phù hợp kiểu trường đã khai báo | So sánh kiểu dữ liệu, mapping thực tế và payload |
| Tìm kiếm không ra kết quả mong đợi | Dùng sai kiểu truy vấn hoặc analyzer | Kiểm tra mapping **text**/**keyword** và chọn **match**/**term** phù hợp |
| Dữ liệu mới chưa xuất hiện trong tìm kiếm | Elasticsearch chưa refresh index | Kiểm tra thời điểm refresh và cách kiểm thử |
| Cập nhật làm mất trường khác | Ghi lại tài liệu bằng đối tượng chỉ chứa một phần dữ liệu | Đọc tài liệu hiện tại trước khi sửa rồi **save**, hoặc dùng cập nhật từng phần |

Khi gặp lỗi, nên xem cả exception của ứng dụng và phản hồi từ Elasticsearch. Các thông tin như tên index, tên trường, kiểu dữ liệu, trạng thái kết nối và nội dung truy vấn thường giúp xác định nguyên nhân nhanh hơn.

## 12. Quy trình thao tác hoàn chỉnh

Một luồng xử lý tài liệu điển hình có thể triển khai theo thứ tự sau:

1. Khởi động Elasticsearch và cấu hình URI, xác thực, TLS nếu cần.
2. Khai báo lớp tài liệu với **@Document**, **@Id** và mapping cho từng trường.
3. Tạo index cùng mapping trước khi ghi dữ liệu nếu ứng dụng cần kiểm soát việc khởi tạo.
4. Khai báo repository kế thừa **ElasticsearchRepository**.
5. Dùng **save** hoặc **saveAll** để ghi tài liệu.
6. Dùng **findById** để đọc theo ID; dùng repository query hoặc **ElasticsearchOperations** để tìm kiếm.
7. Đọc tài liệu hiện tại, cập nhật thuộc tính rồi lưu lại; dùng API cập nhật từng phần khi phù hợp.
8. Dùng **deleteById**, **delete** hoặc thao tác xóa theo điều kiện để xóa dữ liệu đúng phạm vi.

Với các thao tác CRUD cơ bản, repository giúp mã nguồn ngắn gọn và dễ đọc. Khi cần truy vấn động, lấy metadata của kết quả, xây dựng điều kiện phức tạp hoặc điều khiển thao tác index, **ElasticsearchOperations** cung cấp mức kiểm soát cao hơn. Hai cách tiếp cận có thể cùng tồn tại trong một ứng dụng: repository xử lý các thao tác phổ biến, còn operations đảm nhiệm những truy vấn chuyên biệt.
