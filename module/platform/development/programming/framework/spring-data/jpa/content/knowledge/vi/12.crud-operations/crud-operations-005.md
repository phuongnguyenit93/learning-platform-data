# findById, Optional và hợp đồng khi dữ liệu không tồn tại

Trong Spring Data JPA, phương thức findById() dùng để tìm một Entity theo khóa chính. Phương thức này trả về Optional<T> thay vì trả về Entity trực tiếp hoặc null. Optional biểu diễn rõ hai trạng thái: tìm thấy một Entity hoặc không có Entity tương ứng với ID đã truyền vào.

Ví dụ:

~~~java
Optional<Product> result = productRepository.findById(10L);
~~~

Nếu bản ghi tồn tại, Optional chứa Product. Nếu không tồn tại, phương thức trả về Optional.empty(). Vì vậy, mã gọi phải chủ động quyết định cách xử lý trường hợp thiếu dữ liệu: trả HTTP 404, ném ngoại lệ nghiệp vụ, dùng giá trị mặc định hoặc bỏ qua thao tác.

## 1. Hợp đồng của findById()

Phương thức findById(ID id) được kế thừa từ CrudRepository và có kiểu trả về Optional<T>. Trong Spring Data JPA, JpaRepository kế thừa hợp đồng này.

Ví dụ Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Với khai báo trên:

- T là Product, kiểu Entity mà Repository quản lý.
- ID là Long, kiểu Java của khóa chính Product.
- findById nhận một Long và trả về Optional<Product>.

Các trường hợp chính:

| Tình huống | Kết quả |
|---|---|
| ID hợp lệ và bản ghi tồn tại | Optional chứa Entity |
| ID hợp lệ nhưng không có bản ghi | Optional.empty() |
| ID truyền vào là null | Ném IllegalArgumentException |
| Database hoặc provider gặp lỗi | Ngoại lệ truy cập dữ liệu, không phải Optional.empty() |

Không nên hiểu Optional.empty() là mọi lỗi truy vấn đều được chuyển thành “không tìm thấy”. Nó chỉ biểu thị rằng truy vấn hoàn tất nhưng không có Entity tương ứng. Lỗi kết nối, lỗi SQL, lỗi mapping hoặc lỗi transaction vẫn được báo bằng ngoại lệ phù hợp.

findById() tìm theo identifier được JPA mapping. Nó không phụ thuộc tên thuộc tính Java có phải là id hay không. Nếu Entity dùng thuộc tính khóa chính tên productCode, findById vẫn nhận giá trị productCode theo kiểu ID đã khai báo trong Repository.

## 2. Optional biểu diễn kết quả có thể vắng mặt

Optional<T> là một container có thể chứa một giá trị không-null hoặc không chứa giá trị nào. Mục tiêu của nó là khiến trường hợp không có kết quả được thể hiện rõ trong kiểu trả về.

Ví dụ:

~~~java
Optional<Product> found = productRepository.findById(10L);

if (found.isPresent()) {
    Product product = found.get();
    System.out.println(product.getName());
} else {
    System.out.println("Product not found");
}
~~~

Cách trên hợp lệ vì đã kiểm tra isPresent() trước khi gọi get(). Tuy nhiên, Java cung cấp các phương thức giúp viết gọn và diễn đạt ý định tốt hơn.

### Dùng orElseThrow() khi thiếu dữ liệu là lỗi

~~~java
Product product = productRepository.findById(10L)
        .orElseThrow();
~~~

Nếu không có Entity, orElseThrow() không tham số ném NoSuchElementException. Trong ứng dụng nghiệp vụ, nên dùng một ngoại lệ có ý nghĩa rõ ràng:

~~~java
Product product = productRepository.findById(10L)
        .orElseThrow(() ->
                new ProductNotFoundException(10L));
~~~

Ví dụ ngoại lệ tùy chỉnh:

~~~java
public class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
~~~

Đây là cách phù hợp khi service cần bảo đảm Entity phải tồn tại để thực hiện thao tác tiếp theo.

### Dùng orElse() khi có giá trị thay thế

~~~java
Product product = productRepository.findById(10L)
        .orElse(defaultProduct);
~~~

Nếu Optional có giá trị, kết quả là Entity tìm được. Nếu rỗng, kết quả là defaultProduct.

Lưu ý: đối số của orElse() được tính trước khi gọi phương thức, kể cả khi Optional đã có giá trị. Nếu việc tạo giá trị thay thế tốn chi phí hoặc có side effect, dùng orElseGet().

### Dùng orElseGet() để tạo giá trị khi thật sự cần

~~~java
Product product = productRepository.findById(10L)
        .orElseGet(() -> createFallbackProduct());
~~~

Supplier chỉ được gọi khi Optional rỗng. Tuy nhiên, chỉ nên tạo fallback khi nghiệp vụ thực sự cho phép. Không nên âm thầm tạo một Entity mới khi người dùng yêu cầu một ID cụ thể nhưng ID đó không tồn tại.

### Dùng ifPresent() khi chỉ cần thực hiện hành động nếu tìm thấy

~~~java
productRepository.findById(10L)
        .ifPresent(product ->
                System.out.println(product.getName()));
~~~

Nếu không tìm thấy, lambda không được thực hiện. Cách này phù hợp khi việc thiếu dữ liệu là bình thường và không cần xử lý riêng.

### Dùng ifPresentOrElse() để xử lý cả hai trường hợp

Java 9 trở lên hỗ trợ:

~~~java
productRepository.findById(10L)
        .ifPresentOrElse(
                product -> System.out.println(product.getName()),
                () -> System.out.println("Product not found")
        );
~~~

Cách này diễn đạt rõ cả nhánh tìm thấy và không tìm thấy.

## 3. Chuyển đổi kết quả bằng map() và filter()

Optional hỗ trợ biến đổi hoặc lọc giá trị mà không cần tự kiểm tra null.

### Dùng map() để lấy một thuộc tính

~~~java
Optional<String> productName =
        productRepository.findById(10L)
                .map(Product::getName);
~~~

Nếu tìm thấy Product, map() gọi getName() và tạo Optional<String>. Nếu không tìm thấy, kết quả vẫn là Optional.empty().

Có thể nối nhiều phép biến đổi:

~~~java
Optional<String> normalizedName =
        productRepository.findById(10L)
                .map(Product::getName)
                .map(String::trim)
                .map(String::toUpperCase);
~~~

### Dùng filter() để kiểm tra điều kiện

~~~java
Optional<Product> availableProduct =
        productRepository.findById(10L)
                .filter(Product::isActive);
~~~

Nếu không tìm thấy hoặc Product không active, kết quả đều là Optional.empty(). Nếu nghiệp vụ cần phân biệt hai nguyên nhân, hãy xử lý chúng riêng thay vì gộp vào một filter.

### Dùng flatMap() khi phép biến đổi cũng trả Optional

~~~java
Optional<Category> category =
        productRepository.findById(10L)
                .flatMap(Product::getCategoryOptional);
~~~

flatMap() tránh tạo Optional lồng nhau như Optional<Optional<Category>>. Chỉ dùng ví dụ này nếu phương thức được gọi thực sự trả về Optional<Category>.

## 4. Xử lý bản ghi không tồn tại ở tầng Service

Repository nên tập trung vào truy cập dữ liệu. Service quyết định ý nghĩa nghiệp vụ của việc không tìm thấy.

Ví dụ Entity và Repository:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Service trả Optional nếu việc không tìm thấy là một kết quả hợp lệ đối với caller:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.Optional;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Optional<Product> findById(Long id) {
        return repository.findById(id);
    }
}
~~~

Service khác có thể yêu cầu Entity bắt buộc tồn tại:

~~~java
@Transactional(readOnly = true)
public Product getRequiredProduct(Long id) {
    return repository.findById(id)
            .orElseThrow(() ->
                    new ProductNotFoundException(id));
}
~~~

Hai kiểu API này đều có thể hợp lý. Hãy chọn theo ngữ nghĩa nghiệp vụ và giữ nhất quán trong dự án.

Không nên bắt repository trả null bằng cách tự viết wrapper quanh findById(). Hợp đồng Optional đã thể hiện rõ trạng thái thiếu dữ liệu.

## 5. Trả HTTP 404 khi không tìm thấy Entity

Với REST API, yêu cầu GET một tài nguyên không tồn tại thường nên trả HTTP 404 Not Found.

Có thể ánh xạ Optional sang ResponseEntity:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<ProductResponse> getById(
            @PathVariable Long id) {

        return ResponseEntity.of(
                service.findById(id)
                        .map(ProductResponse::from)
        );
    }
}
~~~

DTO response:

~~~java
public record ProductResponse(Long id, String name) {

    public static ProductResponse from(Product product) {
        return new ProductResponse(
                product.getId(),
                product.getName()
        );
    }
}
~~~

ResponseEntity.of(Optional<T>) trả response 200 với body khi Optional có giá trị và 404 khi Optional rỗng. Việc dùng DTO giúp kiểm soát dữ liệu API trả ra thay vì serialize trực tiếp Entity.

Một cách khác là service ném ProductNotFoundException và controller advice ánh xạ ngoại lệ thành 404. Chọn một quy ước rõ ràng; tránh để cùng một tình huống lúc trả 404, lúc trả 500.

Không nên trả 200 với body null cho một GET tài nguyên không tồn tại nếu hợp đồng API quy định 404.

## 6. findById() khác gì getReferenceById()?

JpaRepository cung cấp cả findById() và getReferenceById(). Hai phương thức không có cùng hợp đồng.

| Tiêu chí | findById(id) | getReferenceById(id) |
|---|---|---|
| Kiểu trả về | Optional<T> | T |
| Mục đích | Kiểm tra và lấy Entity nếu tồn tại | Lấy reference/proxy để tham chiếu Entity |
| Truy vấn database | Thường thực hiện truy vấn để xác định và tải Entity | Provider có thể trì hoãn truy vấn đến khi trạng thái được truy cập |
| Không tồn tại | Optional.empty() | Có thể phát sinh EntityNotFoundException khi proxy được truy cập; provider có thể phát hiện sớm hơn |
| Kiểm tra tồn tại | Phù hợp | Không phù hợp để kiểm tra tồn tại |

Ví dụ findById():

~~~java
Optional<Product> result = productRepository.findById(10L);

if (result.isEmpty()) {
    // Xử lý trường hợp không tồn tại ngay tại đây.
}
~~~

Ví dụ getReferenceById():

~~~java
Product reference = productRepository.getReferenceById(10L);
order.setProduct(reference);
~~~

getReferenceById() có thể hữu ích khi chỉ cần thiết lập quan hệ đến một Entity đã biết ID và không cần đọc các thuộc tính của Entity đó. Tuy nhiên, nếu ID không tồn tại, lỗi có thể chỉ xuất hiện khi proxy được truy cập hoặc được đồng bộ, tùy provider.

Nếu cần trả lời rõ ràng rằng tài nguyên có tồn tại hay không, dùng findById() hoặc existsById().

## 7. findById() khác gì existsById()?

existsById(ID id) trả về boolean để kiểm tra sự tồn tại theo khóa chính.

~~~java
boolean exists = productRepository.existsById(10L);
~~~

Nếu chỉ cần biết có hay không, existsById() diễn đạt đúng mục đích. Nhưng nếu sau đó cần sử dụng Entity, tránh gọi existsById() rồi findById() liên tiếp vì có thể tạo hai truy vấn và vẫn có khoảng thời gian dữ liệu thay đổi giữa hai lần đọc.

Không cần:

~~~java
if (productRepository.existsById(id)) {
    Product product = productRepository.findById(id).orElseThrow();
    // Dùng product
}
~~~

Có thể thay bằng:

~~~java
Product product = productRepository.findById(id)
        .orElseThrow(() -> new ProductNotFoundException(id));
~~~

Lời gọi findById() vừa kiểm tra kết quả vừa lấy Entity.

## 8. Phân biệt không tìm thấy với lỗi truy cập dữ liệu

Optional.empty() chỉ là kết quả hợp lệ khi không có bản ghi tương ứng. Các lỗi khác vẫn có thể ném ngoại lệ.

Ví dụ:

- ID không tồn tại: Optional.empty().
- ID là null: IllegalArgumentException theo hợp đồng Repository.
- Database mất kết nối: ngoại lệ truy cập dữ liệu như DataAccessResourceFailureException hoặc một DataAccessException phù hợp.
- Lỗi SQL hoặc mapping: ngoại lệ được provider/Spring chuyển đổi.
- Transaction đã rollback hoặc không thể bắt đầu: lỗi transaction tương ứng.

Không nên viết:

~~~java
try {
    return repository.findById(id);
} catch (Exception ex) {
    return Optional.empty();
}
~~~

Đoạn mã này biến lỗi hệ thống thành kết quả “không tìm thấy”, khiến caller không thể phân biệt database bị lỗi với ID không có dữ liệu. Hãy để ngoại lệ kỹ thuật được xử lý ở tầng phù hợp, ghi log có kiểm soát và trả lỗi API tương ứng.

## 9. Tình huống dữ liệu bị xóa sau khi đọc

findById() trả kết quả tại thời điểm truy vấn. Nó không bảo đảm Entity vẫn tồn tại đến khi một thao tác sau đó được thực hiện.

Ví dụ:

1. Transaction A đọc Product 10 thành công.
2. Transaction B xóa Product 10 và commit.
3. Transaction A tiếp tục thực hiện thao tác ghi hoặc tạo quan hệ dựa trên Product đã đọc.

Kết quả phụ thuộc isolation level, persistence context, ràng buộc khóa ngoại và thao tác cụ thể. Việc findById() đã trả Optional có giá trị không loại bỏ race condition.

Nếu nghiệp vụ yêu cầu chống cập nhật đồng thời, có thể dùng @Version (optimistic locking) hoặc cơ chế khóa phù hợp như PESSIMISTIC_WRITE trong transaction. Ràng buộc foreign key ở database vẫn là lớp bảo vệ quan trọng cho tính toàn vẹn quan hệ.

Không nên dùng một lần kiểm tra tồn tại như bảo đảm rằng dữ liệu sẽ không thay đổi trong tương lai.

## 10. findAllById() và dữ liệu thiếu trong truy vấn nhiều ID

CrudRepository cũng có findAllById(Iterable<ID> ids). Phương thức này trả các Entity có ID nằm trong danh sách đầu vào.

Nếu một số ID không tồn tại, chúng sẽ bị bỏ qua trong kết quả. Phương thức không trả về một Optional cho từng ID và không bảo đảm thứ tự kết quả trùng với thứ tự đầu vào.

Ví dụ:

~~~java
List<Product> products =
        productRepository.findAllById(
                List.of(10L, 20L, 999L)
        );
~~~

Nếu ID 999 không tồn tại, kết quả chỉ chứa các Product tìm được. Nếu nghiệp vụ cần biết chính xác ID nào bị thiếu, hãy so sánh tập ID yêu cầu với tập ID thực tế trả về.

Không nên giả định kết quả có cùng kích thước hoặc thứ tự với danh sách ID đầu vào.

## 11. Optional trong thiết kế API và domain model

Optional phù hợp nhất như kiểu trả về của phương thức có thể không tìm thấy giá trị. Nó làm rõ hợp đồng và buộc caller suy nghĩ về trường hợp rỗng.

Không nên dùng Optional làm field của Entity:

~~~java
@Entity
public class Product {

    @Id
    private Long id;

    // Không nên dùng kiểu này làm persistent field:
    private Optional<String> description;
}
~~~

JPA không yêu cầu provider phải ánh xạ Optional như một kiểu persistent cơ bản. Hãy dùng String nullable hoặc mapping rõ ràng, rồi dùng Optional ở API/service khi cần.

Cũng không nên dùng Optional làm tham số phương thức hoặc trường DTO chỉ để biểu diễn null một cách máy móc. Với API đầu vào, hãy xác định rõ field có bắt buộc hay không và dùng validation phù hợp.

Không dùng Optional.get() khi chưa kiểm tra giá trị. Ưu tiên orElseThrow(), map(), flatMap(), filter(), ifPresent() hoặc ifPresentOrElse() theo mục đích.

## 12. Kiểm thử hợp đồng findById()

Một repository test với Spring Boot có thể kiểm tra cả trường hợp có và không có dữ liệu.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void returnsEntityWhenIdExists() {
        Product saved = repository.save(new Product("Keyboard"));

        Optional<Product> result =
                repository.findById(saved.getId());

        assertTrue(result.isPresent());
        assertEquals("Keyboard", result.orElseThrow().getName());
    }

    @Test
    void returnsEmptyWhenIdDoesNotExist() {
        Optional<Product> result = repository.findById(-1L);

        assertTrue(result.isEmpty());
    }

    @Test
    void rejectsNullId() {
        assertThrows(
                IllegalArgumentException.class,
                () -> repository.findById(null)
        );
    }
}
~~~

Ví dụ cần có Entity Product với constructor và getter tương ứng, Repository kế thừa JpaRepository<Product, Long>, cùng test dependency và cấu hình database phù hợp.

Trong test repository, dữ liệu thường được chạy trong transaction do @DataJpaTest quản lý và được rollback sau test. Nếu kiểm tra hành vi liên quan đến commit, callback hoặc constraint, cần hiểu rõ transaction của test và có thể chủ động flush để buộc SQL được gửi xuống database.

## 13. Những lỗi thường gặp

**Gọi get() trực tiếp**

Nếu Optional rỗng, get() ném NoSuchElementException. Dùng orElseThrow() với ngoại lệ có ý nghĩa hoặc xử lý nhánh empty rõ ràng.

**Dùng orElse() với thao tác tốn kém**

Đối số của orElse() được tính ngay cả khi Optional có giá trị. Dùng orElseGet() nếu cần tạo fallback một cách lazy.

**Nhầm findById() với truy vấn theo trường tên id**

findById() là phương thức chuẩn tìm theo identifier JPA. Nếu cần tìm theo mã nghiệp vụ, dùng findByCode(), findByEmail() hoặc tên thuộc tính tương ứng.

**Chuyển lỗi database thành Optional.empty()**

Không bắt mọi Exception rồi trả empty. Chỉ kết quả không có bản ghi mới được biểu diễn bằng Optional.empty().

**Dùng getReferenceById() để kiểm tra tồn tại**

Reference có thể trì hoãn truy vấn. Dùng findById() hoặc existsById() khi cần xác định sự tồn tại.

**Kiểm tra existsById() rồi mới findById()**

Nếu cần Entity, gọi findById() một lần. Tránh truy vấn dư và tránh khoảng thời gian dữ liệu thay đổi giữa hai thao tác.

**Trả Entity trực tiếp từ REST API**

Nên dùng DTO/projection để kiểm soát dữ liệu, tránh lazy loading ngoài transaction và tránh lộ các trường nội bộ.

## 14. Quy trình xử lý một yêu cầu tìm Entity

Một luồng service/controller rõ ràng có thể là:

~~~text
HTTP GET /products/{id}
          |
          v
Controller nhận ID
          |
          v
ProductService.findById(id)
          |
          v
ProductRepository.findById(id)
          |
      +---+---+
      |       |
  Có dữ liệu  Không có
      |       |
      v       v
  Map sang   Optional.empty()
    DTO        |
      |        v
      v      HTTP 404
   HTTP 200
~~~

Khi triển khai, cần xác định:

1. ID có được validate về định dạng và phạm vi trước khi gọi Repository không?
2. Không tìm thấy là kết quả bình thường hay lỗi nghiệp vụ?
3. Service nên trả Optional hay ném exception?
4. Controller ánh xạ trường hợp thiếu dữ liệu thành HTTP status nào?
5. Lỗi database được log và chuyển thành phản hồi lỗi ra sao?
6. Có cần kiểm soát đồng thời hoặc kiểm tra quyền truy cập trước khi trả Entity không?

## 15. Kết luận

findById() trong Spring Data JPA trả về Optional<T> để biểu diễn rõ trường hợp tìm thấy hoặc không có Entity theo khóa chính. Optional.empty() không phải lỗi database; ID null hoặc lỗi truy cập dữ liệu vẫn được xử lý bằng ngoại lệ. Hãy chọn orElseThrow(), orElseGet(), map() hoặc ifPresent() theo ngữ nghĩa nghiệp vụ, phân biệt findById() với getReferenceById() và existsById(), đồng thời dùng DTO/projection ở API để kiểm soát dữ liệu trả về.
