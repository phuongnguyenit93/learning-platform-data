# ElasticsearchRepository và các thao tác dữ liệu được cung cấp

Spring Data Elasticsearch cung cấp `ElasticsearchRepository` để ứng dụng Java thao tác với document theo mô hình repository quen thuộc của Spring Data. Bạn khai báo một interface gắn với entity và kiểu ID; Spring tạo implementation tại runtime để thực hiện các thao tác lưu, đọc, tìm kiếm, phân trang và xóa.

Repository giúp giảm mã truy cập dữ liệu lặp lại, nhưng không loại bỏ nhu cầu hiểu Elasticsearch. Một thao tác `findById` là đọc document theo định danh; một phương thức tìm theo tên cần được ánh xạ thành query phù hợp; `save` ghi document vào index; và `deleteAll` có thể tác động đến toàn bộ document trong index của entity. Hiểu rõ từng thao tác giúp tránh dùng repository sai mục đích hoặc vô tình tạo tải lớn lên cluster.

## 1. Repository trong Spring Data Elasticsearch

### 1.1. Repository là abstraction truy cập dữ liệu

Trong ứng dụng Spring, repository là interface mô tả các thao tác dữ liệu mà service cần. Thay vì tự viết HTTP request cho từng thao tác, bạn khai báo interface kế thừa repository phù hợp:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Hai tham số generic có ý nghĩa:

- `ProductDocument` là kiểu entity/document mà repository quản lý.
- `String` là kiểu của ID được đánh dấu bằng `@Id`.

Spring Data tạo proxy implementation cho interface khi ứng dụng khởi động và repository được scan. Service inject interface này và gọi các phương thức đã được cung cấp.

Bạn không cần tự viết class `ProductRepositoryImpl` chỉ để có các thao tác CRUD cơ bản. Khi cần truy vấn đặc biệt, có thể khai báo query method, dùng `@Query`, hoặc chuyển sang API linh hoạt hơn như `ElasticsearchOperations`.

### 1.2. Luồng gọi repository

~~~mermaid
flowchart TD
    A[Controller] --> B[Service]
    B --> C[ProductRepository interface]
    C --> D[Spring Data repository proxy]
    D --> E[Mapping and query infrastructure]
    E --> F[Elasticsearch Java client]
    F --> G[Elasticsearch cluster]
    G --> F
    F --> E
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Các lớp có trách nhiệm riêng:

- Controller tiếp nhận HTTP request và trả response.
- Service áp dụng quy tắc nghiệp vụ.
- Repository cung cấp API truy cập document.
- Spring Data chuyển lời gọi repository thành thao tác phù hợp.
- Mapping converter chuyển đổi object Java và document.
- Elasticsearch client gửi request đến cluster.

Repository không nên trở thành nơi chứa toàn bộ nghiệp vụ. Service quyết định khi nào lưu, khi nào tìm kiếm và cách xử lý kết quả.

### 1.3. Khai báo entity trước khi khai báo repository

Repository cần biết entity được ánh xạ đến index nào và property nào là ID:

~~~java
@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;

    public ProductDocument() {
    }

    public ProductDocument(
            String id,
            String name,
            String category,
            BigDecimal price,
            boolean available) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.available = available;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

Trong ví dụ, `createIndex = false` thể hiện index được provision ở bước quản lý riêng. Nếu dự án cho phép repository tạo index tự động, có thể cấu hình hành vi đó theo chiến lược của ứng dụng.

Kiểu `Double` chỉ minh họa field số. Với dữ liệu tiền tệ, cần cân nhắc độ chính xác và cách mapping, chẳng hạn scaled float với scaling factor phù hợp hoặc lưu đơn vị tiền nhỏ nhất dưới dạng số nguyên. Không nên chọn kiểu số chỉ để khớp tên kiểu Java.

## 2. Các thao tác CRUD cơ bản

Các thao tác CRUD là nhóm API được sử dụng thường xuyên nhất. Chúng thường được kế thừa từ các repository abstraction của Spring Data và được ElasticsearchRepository hỗ trợ cho entity tương ứng.

### 2.1. Tổng quan phương thức

| Phương thức | Chức năng | Kết quả thường gặp |
|---|---|---|
| `save(entity)` | Lưu một document | Entity đã lưu |
| `saveAll(entities)` | Lưu nhiều document | Các entity đã lưu |
| `findById(id)` | Đọc document theo ID | `Optional<T>` |
| `existsById(id)` | Kiểm tra ID có tồn tại | `boolean` |
| `findAll()` | Lấy các document | `Iterable<T>` |
| `findAllById(ids)` | Lấy document theo nhiều ID | `Iterable<T>` |
| `count()` | Đếm document | `long` |
| `deleteById(id)` | Xóa theo ID | Không trả kết quả |
| `delete(entity)` | Xóa entity | Không trả kết quả |
| `deleteAllById(ids)` | Xóa theo danh sách ID | Không trả kết quả |
| `deleteAll(entities)` | Xóa các entity được truyền vào | Không trả kết quả |
| `deleteAll()` | Xóa toàn bộ document thuộc repository/index | Không trả kết quả |

Tên và kiểu trả về chi tiết có thể thay đổi theo phiên bản Spring Data Commons/Spring Data Elasticsearch. Hãy đối chiếu API của phiên bản dự án đang dùng khi cần chữ ký phương thức chính xác.

### 2.2. Lưu một document bằng save

~~~java
ProductDocument product = new ProductDocument(
    "P1001",
    "Wireless Keyboard",
    "ACCESSORY",
    new BigDecimal("49.90"),
    true
);

ProductDocument saved = productRepository.save(product);
~~~

`save` chuyển entity thành document và gửi thao tác ghi đến index gắn với entity. Với ID đã tồn tại, thao tác ghi thường thay thế nội dung document tại ID đó theo semantics của Elasticsearch index operation.

Điều này có nghĩa `save` thường được dùng cho cả tạo mới và cập nhật toàn bộ document theo ID. Nếu muốn cập nhật một phần field mà không thay toàn bộ document, cần dùng API update phù hợp hoặc `ElasticsearchOperations`.

Nếu ID chưa được gán, Elasticsearch có thể tạo ID tự sinh tùy API và phiên bản. Với dữ liệu nghiệp vụ cần đọc/cập nhật ổn định, nên chủ động thiết kế ID hoặc kiểm tra cách phiên bản đang dùng trả lại ID được sinh.

Không nên hiểu `save` là phép merge tự động mọi field. Nếu object gửi lên thiếu một property, document được ghi có thể không còn giá trị cũ của property đó, tùy thao tác ghi được sử dụng.

### 2.3. Lưu nhiều document bằng saveAll

~~~java
List<ProductDocument> products = List.of(
    new ProductDocument(
        "P1001", "Wireless Keyboard", "ACCESSORY",
        new BigDecimal("49.90"), true
    ),
    new ProductDocument(
        "P1002", "Wireless Mouse", "ACCESSORY",
        new BigDecimal("29.90"), true
    )
);

Iterable<ProductDocument> savedProducts =
    productRepository.saveAll(products);
~~~

`saveAll` thuận tiện khi cần lưu một nhóm entity. Spring Data Elasticsearch có thể tối ưu thao tác nhiều document bằng bulk API thay vì gửi một request độc lập cho từng document, tùy implementation và phiên bản.

Bulk request giúp giảm overhead mạng, nhưng không có nghĩa toàn bộ nhóm được xử lý như một transaction nguyên tử. Một số item có thể thành công trong khi item khác thất bại. Khi nhập dữ liệu lớn, cần theo dõi lỗi theo item và có chiến lược retry phù hợp.

Không gửi một danh sách không giới hạn vào `saveAll`. Hãy chia batch theo kích thước phù hợp với dung lượng document, tải cluster, giới hạn request và độ trễ thực tế.

### 2.4. Đọc theo ID bằng findById

~~~java
Optional<ProductDocument> result =
    productRepository.findById("P1001");

result.ifPresent(product ->
    System.out.println(product.getName())
);
~~~

`findById` đọc document theo `_id`. Đây là thao tác truy cập trực tiếp bằng định danh, phù hợp khi ứng dụng đã biết ID.

Kết quả là `Optional<T>` vì document có thể không tồn tại. Hãy phân biệt:

- `Optional.empty()`: không có document với ID đó.
- Có entity nhưng một property là `null`: document tồn tại, field có thể thiếu hoặc null.
- Exception: request thất bại do kết nối, quyền, lỗi server hoặc lỗi mapping.

Không nên bắt mọi exception rồi trả về `Optional.empty()`. Làm như vậy sẽ khiến lỗi hệ thống bị hiểu nhầm thành trường hợp không tìm thấy dữ liệu.

### 2.5. Kiểm tra tồn tại bằng existsById

~~~java
boolean exists = productRepository.existsById("P1001");
~~~

Phương thức này phù hợp khi chỉ cần biết document có tồn tại theo ID hay không. Nếu cần dữ liệu để hiển thị hoặc xử lý tiếp, gọi `findById` thường hợp lý hơn.

Nếu nghiệp vụ cần kiểm tra điều kiện phức tạp như “có sản phẩm thuộc danh mục này và đang bán hay không”, hãy khai báo query method hoặc query rõ ràng. `existsById` chỉ kiểm tra theo định danh.

### 2.6. Đọc nhiều ID bằng findAllById

~~~java
List<String> ids = List.of("P1001", "P1002", "P1003");

Iterable<ProductDocument> found =
    productRepository.findAllById(ids);
~~~

Phương thức này hữu ích khi đã có danh sách ID và muốn lấy các document tương ứng. Không nên giả định thứ tự kết quả luôn giống thứ tự ID đầu vào hoặc mọi ID đều có kết quả. Hãy xử lý trường hợp một số ID không tồn tại.

Nếu cần bảo toàn thứ tự đầu vào, ứng dụng có thể tạo map theo ID rồi sắp xếp kết quả theo danh sách ID ban đầu.

### 2.7. Lấy toàn bộ bằng findAll

~~~java
Iterable<ProductDocument> allProducts =
    productRepository.findAll();
~~~

`findAll()` phù hợp với tập dữ liệu nhỏ hoặc các tác vụ quản trị có giới hạn. Với index lớn, lấy toàn bộ document có thể tạo request nặng, tiêu tốn bộ nhớ ứng dụng và gây tải lên cluster.

Đối với màn hình danh sách, hãy dùng phân trang. Đối với tác vụ quét dữ liệu lớn, cân nhắc scroll, search_after hoặc cơ chế batch phù hợp thay vì materialize toàn bộ index vào RAM.

### 2.8. Đếm document bằng count

~~~java
long total = productRepository.count();
~~~

`count()` trả về số document thuộc index của repository theo phạm vi truy vấn mặc định. Nó hữu ích cho thống kê tổng quan hoặc kiểm tra số lượng dữ liệu.

Đếm toàn bộ index có thể tốn tài nguyên tùy kích thước và workload. Nếu cần số lượng theo điều kiện, hãy dùng query phù hợp. Với dashboard cập nhật liên tục, cần cân nhắc tần suất gọi count và khả năng dùng aggregation hoặc số liệu được tổng hợp sẵn.

### 2.9. Xóa document

Xóa theo ID:

~~~java
productRepository.deleteById("P1001");
~~~

Xóa entity:

~~~java
productRepository.delete(product);
~~~

Xóa theo danh sách ID:

~~~java
productRepository.deleteAllById(List.of("P1002", "P1003"));
~~~

Xóa các entity đã chọn:

~~~java
productRepository.deleteAll(selectedProducts);
~~~

Các thao tác này phù hợp khi phạm vi xóa đã được xác định rõ.

Đặc biệt cẩn thận với:

~~~java
productRepository.deleteAll();
~~~

Phương thức này có thể xóa toàn bộ document trong phạm vi repository/index tương ứng. Không gọi nó như một thao tác “xóa danh sách hiện tại” hoặc dùng trong endpoint công khai nếu chưa có kiểm soát rõ ràng.

Trong môi trường production, thao tác xóa hàng loạt nên có xác nhận phạm vi, quyền phù hợp, log kiểm toán và kế hoạch khôi phục dữ liệu nếu nghiệp vụ yêu cầu.

## 3. Phân trang và sắp xếp

### 3.1. Vì sao cần Pageable?

Kết quả tìm kiếm có thể chứa hàng nghìn hoặc hàng triệu document. Thay vì lấy tất cả, ứng dụng yêu cầu một trang với kích thước giới hạn.

Spring Data dùng `Pageable` để mô tả số trang, kích thước trang và thông tin sort:

~~~java
Pageable pageable = PageRequest.of(0, 20);

Page<ProductDocument> page =
    productRepository.findAll(pageable);
~~~

Trong ví dụ, trang đầu tiên có tối đa 20 document. Chỉ số trang bắt đầu từ 0.

### 3.2. Sắp xếp bằng Sort

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "price");

Pageable pageable = PageRequest.of(0, 20, sort);

Page<ProductDocument> page =
    productRepository.findAll(pageable);
~~~

Có thể sắp xếp theo nhiều thuộc tính:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("category"),
    Sort.Order.desc("price")
);
~~~

Tên property thường được khai báo theo property Java trong entity để Spring Data ánh xạ qua metadata. Hãy dùng field có kiểu và mapping hỗ trợ sort. Với nội dung `text`, sort trực tiếp thường không phù hợp; hãy dùng subfield `keyword` hoặc một field chuyên cho sort.

### 3.3. Đọc thông tin từ Page

~~~java
Page<ProductDocument> page =
    productRepository.findAll(PageRequest.of(0, 20));

List<ProductDocument> content = page.getContent();
int pageNumber = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

`Page<T>` chứa nội dung trang hiện tại và thông tin tổng quan về kết quả, chẳng hạn tổng số phần tử và tổng số trang.

Để tạo `Page`, framework có thể cần thông tin tổng số kết quả. Tính tổng có thể tạo thêm công việc cho Elasticsearch. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, một kiểu phân trang nhẹ hơn như `Slice` có thể phù hợp khi được query method và phiên bản hỗ trợ.

### 3.4. Phân trang sâu

Phân trang offset thông thường phù hợp với các trang đầu. Khi `from` tăng rất lớn, Elasticsearch phải xử lý nhiều kết quả trung gian và có giới hạn `index.max_result_window` mặc định phổ biến là 10.000.

Với luồng duyệt dữ liệu lớn hoặc trang sâu, hãy cân nhắc `search_after` kết hợp sort ổn định và point-in-time (PIT) khi yêu cầu tính nhất quán cần thiết. Đây là các khả năng thường cần query API cấp thấp hơn, không nên cố ép mọi tình huống vào `findAll(Pageable)`.

## 4. Query method được suy ra từ tên phương thức

### 4.1. Query derivation

Spring Data có thể tạo query từ tên phương thức repository theo quy ước. Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategory(String category);

    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByPriceBetween(
        BigDecimal minimum,
        BigDecimal maximum
    );

    List<ProductDocument> findByCategoryAndAvailable(
        String category,
        boolean available
    );
}
~~~

Spring phân tích tên phương thức, nhận diện property và operator rồi tạo query phù hợp.

Một số từ khóa thường gặp trong query derivation gồm:

| Từ khóa trong tên | Ý nghĩa |
|---|---|
| `And`, `Or` | Kết hợp điều kiện |
| `Is`, `Equals` | So sánh bằng |
| `Between` | Nằm trong khoảng |
| `LessThan`, `GreaterThan` | So sánh nhỏ hơn/lớn hơn |
| `In` | Thuộc một tập giá trị |
| `Not` | Phủ định điều kiện |
| `True`, `False` | Điều kiện boolean |
| `OrderBy` | Chỉ định thứ tự kết quả |

Không phải mọi operator của Spring Data đều được hỗ trợ giống nhau cho mọi kiểu field và phiên bản Elasticsearch. Hãy kiểm tra query được tạo và thử trên dữ liệu thực tế.

### 4.2. Tên phương thức dùng property Java

Giả sử entity có:

~~~java
@Field(name = "product_category", type = FieldType.Keyword)
private String category;
~~~

Query method nên tham chiếu property Java:

~~~java
List<ProductDocument> findByCategory(String category);
~~~

Spring Data dùng metadata để ánh xạ `category` sang field `product_category`. Không tự đổi tên phương thức thành `findByProductCategory` trừ khi entity thực sự có property Java tên như vậy.

### 4.3. Query method có Pageable

~~~java
Page<ProductDocument> findByCategory(
    String category,
    Pageable pageable
);
~~~

Cách gọi:

~~~java
Page<ProductDocument> page =
    productRepository.findByCategory(
        "ACCESSORY",
        PageRequest.of(
            0,
            20,
            Sort.by(Sort.Direction.ASC, "price")
        )
    );
~~~

Kết hợp điều kiện với Pageable giúp xây dựng API danh sách theo bộ lọc. Hãy giới hạn page size từ đầu vào client để tránh một request yêu cầu hàng chục nghìn document.

### 4.4. Khi nào tên phương thức không đủ rõ?

Tên phương thức phù hợp với điều kiện đơn giản và dễ đọc. Khi query cần:

- Boolean query phức tạp với nhiều nhánh must/should/filter.
- Full-text matching với analyzer cụ thể.
- Phrase query, fuzzy query hoặc proximity.
- Highlight, aggregation hoặc function score.
- Script, nested query hoặc nhiều field.
- Kiểm soát chính xác scoring và sort.

thì tên phương thức có thể trở nên dài và khó diễn đạt ý định. Khi đó, dùng `@Query` hoặc `ElasticsearchOperations` sẽ rõ ràng hơn.

## 5. Khai báo truy vấn bằng @Query

### 5.1. Dùng JSON query trực tiếp

`@Query` cho phép khai báo Elasticsearch query dạng JSON trên phương thức repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<ProductDocument> searchByName(String text);
}
~~~

Placeholder `?0` tham chiếu tham số đầu tiên. Với nhiều tham số, có thể dùng placeholder theo chỉ số tương ứng nếu cú pháp của phiên bản hỗ trợ.

Ví dụ query filter theo danh mục và điều kiện có sẵn hàng:

~~~java
@Query("""
{
  "bool": {
    "filter": [
      { "term": { "category": "?0" } },
      { "term": { "available": true } }
    ]
  }
}
""")
List<ProductDocument> findAvailableInCategory(String category);
~~~

Đây là JSON query minh họa. Hãy xác nhận cách thay thế placeholder và cú pháp annotation theo phiên bản Java/Spring Data Elasticsearch của dự án.

### 5.2. Query method và @Query có vai trò khác nhau

| Cách khai báo | Phù hợp khi |
|---|---|
| Query derivation | Điều kiện đơn giản, tên phương thức vẫn dễ hiểu |
| `@Query` | Muốn viết rõ query DSL nhưng vẫn giữ repository interface |
| `ElasticsearchOperations` | Cần query động, nhiều điều kiện tùy chọn hoặc kiểm soát sâu |
| Elasticsearch Java client trực tiếp | Cần API client chuyên biệt hoặc tính năng chưa được abstraction hỗ trợ thuận tiện |

Không nên đưa một JSON query rất dài vào annotation chỉ để tránh dùng `ElasticsearchOperations`. Khi query cần được xây dựng từ nhiều tham số tùy chọn hoặc có logic phức tạp, code builder thường dễ đọc và kiểm thử hơn.

## 6. Dùng repository trong Service

### 6.1. Constructor injection

Service nên nhận repository qua constructor:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public ProductDocument create(ProductDocument product) {
        return productRepository.save(product);
    }

    public Optional<ProductDocument> findById(String id) {
        return productRepository.findById(id);
    }

    public void delete(String id) {
        productRepository.deleteById(id);
    }
}
~~~

Cách này giúp service phụ thuộc vào abstraction và dễ thay thế hoặc mock repository trong unit test.

### 6.2. Xử lý trường hợp không tìm thấy

Service có thể chuyển kết quả Optional thành exception nghiệp vụ hoặc kiểu kết quả mà ứng dụng sử dụng:

~~~java
public ProductDocument getRequired(String id) {
    return productRepository.findById(id)
        .orElseThrow(() ->
            new ProductNotFoundException(id)
        );
}
~~~

`ProductNotFoundException` là exception do ứng dụng định nghĩa. Controller hoặc exception handler có thể chuyển nó thành HTTP 404.

Không nên để mọi tầng tự quyết định cách xử lý không tìm thấy. Quy tắc nghiệp vụ nên được tập trung ở service.

### 6.3. Không đặt nghiệp vụ vào repository

Repository nên tập trung vào truy cập dữ liệu. Ví dụ, phương thức `findByCategory` chỉ truy vấn dữ liệu; quyết định danh mục nào người dùng được xem, sản phẩm nào được phép bán hoặc cách áp dụng giảm giá thuộc nghiệp vụ của service.

Nếu một thao tác gồm nhiều bước, service điều phối các repository hoặc API cần thiết. Tuy nhiên, đừng giả định các lời gọi Elasticsearch liên tiếp được bao bọc trong một transaction ACID như một số hệ quản trị quan hệ. Hãy thiết kế rõ cách xử lý khi một bước thành công còn bước khác thất bại.

## 7. Giới hạn và semantics của thao tác repository

### 7.1. Save thường ghi document theo ID

`save` phù hợp để ghi document đầy đủ theo ID. Nếu cần cập nhật một vài field mà giữ nguyên phần còn lại, hãy tìm hiểu update API phù hợp. Đọc document, sửa object rồi save có thể tạo ra vấn đề lost update nếu nhiều tiến trình cùng cập nhật một document mà không có cơ chế concurrency phù hợp.

Với dữ liệu có nhiều writer, cần hiểu optimistic concurrency control, sequence number, primary term hoặc cơ chế versioning được API/client hỗ trợ.

### 7.2. Bulk không phải transaction

`saveAll` và các thao tác bulk có thể gửi nhiều item trong một request. Bulk API thường xử lý từng item riêng; một item lỗi không đồng nghĩa mọi item khác bị rollback.

Khi import dữ liệu:

- Chia batch hợp lý.
- Theo dõi kết quả từng item.
- Ghi nhận ID của item lỗi.
- Retry có giới hạn với lỗi tạm thời.
- Không retry lỗi mapping hoặc dữ liệu sai mà chưa sửa nguyên nhân.
- Điều tiết tốc độ để không làm quá tải cluster.

### 7.3. Delete cần xác định rõ phạm vi

`deleteById` và `delete(entity)` có phạm vi rõ ràng hơn `deleteAll()`. Xóa toàn bộ index có thể ảnh hưởng đến nhiều tính năng hoặc service khác cùng sử dụng dữ liệu.

Với thao tác xóa theo điều kiện, hãy dùng API query/delete phù hợp và kiểm tra điều kiện trước khi thực hiện. Một lỗi filter có thể dẫn đến xóa nhiều document hơn dự định.

### 7.4. Không giả định transaction như RDBMS

Elasticsearch tập trung vào document và tìm kiếm phân tán. Không nên mặc định một chuỗi thao tác repository trên nhiều document hoặc nhiều index sẽ được commit/rollback nguyên tử.

Nếu nghiệp vụ cần phối hợp nhiều hệ thống, có thể cần outbox, saga, retry, idempotency hoặc quy trình bù trừ. Lựa chọn phụ thuộc mức độ nhất quán mà nghiệp vụ yêu cầu.

## 8. Repository hay ElasticsearchOperations?

`ElasticsearchRepository` là lựa chọn thuận tiện cho CRUD và query method đã biết trước. `ElasticsearchOperations` phù hợp khi ứng dụng cần điều khiển query linh hoạt hơn.

| Nhu cầu | Công cụ thường phù hợp |
|---|---|
| Lưu hoặc đọc một document theo ID | Repository |
| CRUD đơn giản | Repository |
| Query method theo property | Repository |
| Query JSON cố định | Repository với `@Query` |
| Bộ lọc động theo nhiều tham số tùy chọn | `ElasticsearchOperations` |
| Aggregation phức tạp | `ElasticsearchOperations` hoặc Java client |
| Highlight và truy cập SearchHit metadata | Search API phù hợp của Spring Data |
| Search after, PIT hoặc scroll | API tìm kiếm chuyên biệt |
| Quản lý index, settings, mapping | `IndexOperations` |
| Tính năng client mới chưa có abstraction thuận tiện | Elasticsearch Java client |

Không nhất thiết phải chọn một công cụ cho toàn ứng dụng. Một service có thể dùng repository cho thao tác CRUD phổ biến và dùng `ElasticsearchOperations` cho màn hình tìm kiếm nâng cao.

## 9. Repository đồng bộ và ReactiveElasticsearchRepository

`ElasticsearchRepository` là API imperative (đồng bộ): lời gọi phương thức trả kết quả trực tiếp hoặc chờ thao tác hoàn tất theo cách gọi thông thường.

Spring Data Elasticsearch còn có `ReactiveElasticsearchRepository` cho ứng dụng reactive:

~~~java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<ProductDocument, String> {
}
~~~

Các phương thức reactive thường trả về kiểu như `Mono<T>` hoặc `Flux<T>` thay vì `Optional<T>`, `Iterable<T>` hoặc `Page<T>` theo API imperative.

Không nên trộn lẫn hai mô hình một cách tùy tiện. Nếu ứng dụng sử dụng WebFlux và reactive end-to-end, cần tránh chặn event-loop bằng các thao tác đồng bộ. Nếu ứng dụng Spring MVC truyền thống, repository imperative thường đơn giản và phù hợp hơn.

## 10. Cấu hình và phát hiện repository

Trong ứng dụng Spring Boot, repository scanning thường được tự động cấu hình khi starter và package structure phù hợp. Repository interface nên nằm trong package được Spring scan.

Với cấu hình tùy chỉnh hoặc ứng dụng không dùng auto-configuration, có thể khai báo:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.product.repository"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Chỉ cần dùng `@EnableElasticsearchRepositories` khi cấu hình ứng dụng yêu cầu. Không khai báo trùng nhiều cấu hình scan repository cho cùng package nếu không có chủ đích.

Nếu repository không được inject, hãy kiểm tra:

- Interface có kế thừa repository phù hợp không?
- Package có nằm trong phạm vi component/repository scan không?
- Entity có metadata `@Document` và `@Id` phù hợp không?
- Dependency Spring Data Elasticsearch có tương thích với Spring Boot không?
- Có lỗi tạo repository hoặc kết nối trong log lúc khởi động không?

Repository proxy có thể được tạo thành công nhưng request thực tế vẫn thất bại nếu Elasticsearch không sẵn sàng hoặc credential thiếu quyền.

## 11. Kiểm thử repository

### 11.1. Unit test cho service

Có thể mock repository để kiểm tra nghiệp vụ service mà không cần Elasticsearch:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository productRepository;

    @InjectMocks
    private ProductService productService;

    @Test
    void returnsProductWhenItExists() {
        ProductDocument product = new ProductDocument(
            "P1001",
            "Wireless Keyboard",
            "ACCESSORY",
            new BigDecimal("49.90"),
            true
        );

        when(productRepository.findById("P1001"))
            .thenReturn(Optional.of(product));

        ProductDocument result =
            productService.getRequired("P1001");

        assertEquals("P1001", result.getId());
    }
}
~~~

Unit test này kiểm tra cách service xử lý kết quả repository. Nó không chứng minh query được Elasticsearch thực thi đúng.

### 11.2. Integration test với Elasticsearch thật hoặc test container

Để kiểm tra mapping, query derivation và semantics của repository, cần integration test kết nối với một Elasticsearch instance tương thích.

Một test cơ bản có thể:

1. Tạo index với settings/mapping cần thiết.
2. Lưu một vài document đại diện.
3. Đọc lại theo ID.
4. Kiểm tra query method và `@Query`.
5. Kiểm tra sort và pagination.
6. Dọn dữ liệu hoặc index test sau khi hoàn thành.

Không nên chỉ mock repository rồi kết luận Elasticsearch query hoạt động. Query derivation, analyzer, mapping và version compatibility chỉ được xác minh đáng tin cậy khi chạy với Elasticsearch.

### 11.3. Dữ liệu test cần bao phủ trường hợp biên

Hãy thử:

- ID không tồn tại.
- Field bị thiếu hoặc null.
- Chuỗi có chữ hoa/thường và dấu.
- Giá trị số ở biên khoảng.
- Document có collection hoặc object lồng nhau.
- Trang cuối chỉ còn một phần tử.
- Batch có một item lỗi.
- Xóa ID không tồn tại.
- Query không có kết quả.

Các trường hợp này giúp phát hiện khác biệt giữa cách Java biểu diễn dữ liệu và cách Elasticsearch mapping/query xử lý.

## 12. Lỗi thường gặp khi sử dụng ElasticsearchRepository

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Repository không được inject | Package chưa được scan hoặc thiếu cấu hình repository | Kiểm tra package và `@EnableElasticsearchRepositories` nếu cần |
| Lỗi generic ID hoặc mapping | Kiểu ID không khớp property `@Id` | Đồng bộ kiểu generic và kiểu ID |
| `findById` không tìm thấy document | Dùng ID khác với `_id` hoặc document chưa được index | Kiểm tra `_id` thực tế và index đích |
| `findBy...` trả kết quả bất ngờ | Query derivation không phù hợp với field type/analyzer | Kiểm tra mapping và query được thực thi |
| Sort lỗi hoặc không đúng | Sort trên field text hoặc field không hỗ trợ sort | Dùng keyword subfield hoặc field phù hợp |
| `save` làm mất field cũ | Ghi toàn bộ document từ object không chứa giá trị cũ | Dùng update semantics phù hợp hoặc đọc/sửa có concurrency control |
| `saveAll` có item lỗi | Một số document không tương thích mapping hoặc bị từ chối | Kiểm tra lỗi theo từng item bulk |
| `findAll` quá chậm hoặc tốn bộ nhớ | Đọc toàn bộ index lớn | Dùng Pageable, search_after, scroll hoặc batch |
| `deleteAll` xóa quá nhiều dữ liệu | Hiểu sai phạm vi của thao tác | Xác nhận index/repository và quyền trước khi xóa |
| Repository tạo index thất bại | Cluster không sẵn sàng hoặc runtime thiếu quyền | Kiểm tra `@Document.createIndex`, quyền và provisioning |

Khi có lỗi, hãy kiểm tra log và response từ Elasticsearch. Không nên chỉ bắt exception chung rồi trả về kết quả rỗng, vì điều đó che mất các lỗi kết nối, quyền, mapping hoặc query.

## 13. Ví dụ tổng hợp

Một repository cho sản phẩm có thể khai báo:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategory(String category);

    Page<ProductDocument> findByCategory(
        String category,
        Pageable pageable
    );

    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByPriceBetween(
        BigDecimal minimum,
        BigDecimal maximum
    );

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<ProductDocument> searchByName(String text);
}
~~~

Service sử dụng repository:

~~~java
@Service
public class ProductCatalogService {

    private final ProductRepository productRepository;

    public ProductCatalogService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public ProductDocument save(ProductDocument product) {
        return productRepository.save(product);
    }

    public Optional<ProductDocument> find(String id) {
        return productRepository.findById(id);
    }

    public Page<ProductDocument> browseCategory(
            String category,
            int page,
            int size) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), 100);

        Pageable pageable = PageRequest.of(
            safePage,
            safeSize,
            Sort.by(Sort.Direction.ASC, "name")
        );

        return productRepository.findByCategory(category, pageable);
    }

    public List<ProductDocument> searchName(String text) {
        return productRepository.searchByName(text);
    }

    public void remove(String id) {
        productRepository.deleteById(id);
    }
}
~~~

Ví dụ minh họa cách tổ chức code. Khi dùng trong dự án thật, cần bảo đảm field `name` hỗ trợ sort theo mapping thích hợp; với field `text`, thường nên sort qua subfield `keyword`. Query method và `@Query` cũng cần được kiểm tra với phiên bản Spring Data Elasticsearch và mapping đang chạy.

## 14. Cách chọn thao tác phù hợp

Khi thiết kế một chức năng, hãy bắt đầu từ nhu cầu dữ liệu:

- Đã biết ID và cần lấy một document: dùng `findById`.
- Cần kiểm tra document theo ID: dùng `existsById`.
- Cần lưu hoặc thay thế document: dùng `save`.
- Cần nhập một nhóm document: dùng `saveAll` theo batch.
- Cần tìm theo thuộc tính với điều kiện đơn giản: dùng query method.
- Cần query DSL cố định: dùng `@Query`.
- Cần lọc động, aggregation hoặc kiểm soát scoring: cân nhắc `ElasticsearchOperations`.
- Cần danh sách có giới hạn: dùng `Pageable` hoặc API phân trang phù hợp.
- Cần duyệt tập dữ liệu rất lớn: cân nhắc `search_after`, PIT hoặc scroll.
- Cần xóa: xác định rõ ID/tập document trước khi gọi thao tác delete.

`ElasticsearchRepository` là điểm bắt đầu tốt cho phần lớn thao tác dữ liệu phổ biến. Hiểu rõ ID, mapping, query derivation, phân trang, bulk và semantics xóa/ghi sẽ giúp bạn dùng repository an toàn. Khi bài toán cần kiểm soát truy vấn hoặc vòng đời index sâu hơn, hãy kết hợp với `ElasticsearchOperations` và các API Elasticsearch chuyên biệt.
