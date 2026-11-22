# Kiểu Entity và kiểu khóa định danh trong khai báo Repository

Khi khai báo một Spring Data JPA Repository, hai kiểu generic quan trọng nhất là **kiểu Entity** và **kiểu khóa định danh (ID)**. Chúng cho Spring Data biết Repository quản lý entity nào và nhận kiểu dữ liệu Java nào khi tìm, kiểm tra hoặc xóa một bản ghi theo khóa chính.

Khai báo phổ biến:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Trong ví dụ này, **Product** là kiểu Entity được quản lý, còn **Long** là kiểu Java của thuộc tính khóa chính trong Entity đó. Hai kiểu này phải khớp với mapping JPA thực tế.

## 1. Ý nghĩa của hai tham số generic

JpaRepository có dạng tổng quát:

~~~java
public interface JpaRepository<T, ID> {
}
~~~

- **T (Domain type / Entity type):** lớp entity mà Repository thao tác. Ví dụ Product, Customer, Order.
- **ID (ID type):** kiểu Java của khóa chính được ánh xạ bởi @Id hoặc kiểu lớp khóa chính dùng với @EmbeddedId / @IdClass.

Ví dụ:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Khai báo này có nghĩa Repository quản lý các đối tượng Customer; những thao tác theo khóa chính nhận một giá trị Long.

Các phương thức kế thừa sử dụng hai kiểu này. Ví dụ, về mặt chữ ký API:

~~~java
Optional<T> findById(ID id);
boolean existsById(ID id);
void deleteById(ID id);
<S extends T> S save(S entity);
~~~

Với ProductRepository extends JpaRepository<Product, Long>, các phương thức tương ứng có thể được gọi như sau:

~~~java
Optional<Product> product = productRepository.findById(10L);
boolean exists = productRepository.existsById(10L);
productRepository.deleteById(10L);

Product saved = productRepository.save(new Product("Keyboard"));
~~~

Nhờ khai báo generic, trình biên dịch có thể kiểm tra kiểu đối số và kiểu kết quả ngay trong lúc viết mã. Ví dụ, truyền một chuỗi vào findById của Repository có ID là Long sẽ gây lỗi biên dịch.

## 2. Kiểu Entity phải là lớp được JPA quản lý

Tham số thứ nhất phải đại diện cho Entity mà Repository cần thao tác. Thông thường, lớp đó được đánh dấu bằng @Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

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

Repository tương ứng:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Khi Spring Data khởi tạo Repository, nó cần xác định Entity metadata từ JPA. Vì vậy:

- Dùng đúng lớp có @Entity, ví dụ Product.
- Không dùng DTO, request object hoặc response object làm tham số Entity type.
- Không dùng một lớp chỉ có @MappedSuperclass làm Entity type của Repository nếu lớp đó không được khai báo là Entity độc lập.
- Nếu Entity nằm trong package chưa được JPA scan, ứng dụng có thể không nhận diện được Entity dù khai báo generic trông có vẻ đúng.

Một Repository có thể có các phương thức trả về DTO hoặc projection, nhưng kiểu Entity gốc của Repository vẫn là Entity được quản lý bởi JPA.

## 3. Kiểu ID phải khớp với thuộc tính khóa chính

Xét Entity có khóa chính kiểu Long:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }
}
~~~

Khai báo phù hợp:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Nếu thuộc tính được đánh dấu @Id là Integer, Repository nên khai báo ID là Integer. Nếu là String, ID type là String.

| Mapping trong Entity | ID type trong Repository | Ví dụ giá trị |
|---|---|---|
| @Id private Long id; | Long | 25L |
| @Id private Integer id; | Integer | 25 |
| @Id private String code; | String | "SKU-001" |
| @Id private UUID id; | UUID | Một đối tượng UUID |
| @EmbeddedId private OrderKey id; | OrderKey | Một đối tượng OrderKey |

ID type là **kiểu Java của thuộc tính khóa chính**, không phải tên cột và cũng không phải tên bảng. Ví dụ cột SQL có kiểu BIGINT thường được ánh xạ thành Long; Repository dùng Long, không dùng chuỗi "BIGINT".

### Dùng kiểu wrapper thay cho kiểu primitive

Java không cho phép dùng kiểu primitive làm tham số generic. Vì vậy, nếu thuộc tính ID được khai báo là long, tham số Repository vẫn phải là Long:

~~~java
@Id
private long id;

// Generic phải dùng wrapper:
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Trong Entity JPA, nên ưu tiên wrapper như Long, Integer hoặc UUID khi phù hợp. Với khóa được sinh tự động, giá trị null có thể biểu thị Entity chưa có ID. Kiểu primitive như long luôn có giá trị mặc định là 0, nên không thể biểu diễn trạng thái chưa có giá trị theo cách đó.

Ví dụ thường dùng:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Không nên tự gán ID cho Entity dùng cơ chế sinh khóa tự động trừ khi đã thiết kế rõ chiến lược sinh khóa và trạng thái mới/cũ của Entity.

## 4. Ví dụ với khóa chính kiểu String

Không phải mọi khóa chính đều là số tự tăng. Một mã nghiệp vụ duy nhất cũng có thể được dùng làm khóa chính nếu mô hình dữ liệu phù hợp.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @Column(length = 30)
    private String code;

    @Column(nullable = false)
    private String name;

    protected Category() {
    }

    public Category(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public String getCode() {
        return code;
    }
}
~~~

Repository:

~~~java
public interface CategoryRepository
        extends JpaRepository<Category, String> {
}
~~~

Cách sử dụng:

~~~java
Optional<Category> category =
        categoryRepository.findById("ELEC");

boolean exists =
        categoryRepository.existsById("ELEC");
~~~

Trong ví dụ này, String là ID type vì thuộc tính code được đánh dấu @Id. Không cần dùng Long chỉ vì nhiều bảng khác trong ứng dụng dùng khóa số.

Nếu mã nghiệp vụ có thể thay đổi trong tương lai, hãy cân nhắc dùng một khóa kỹ thuật ổn định như Long hoặc UUID, còn mã nghiệp vụ được đặt unique constraint riêng. Khóa chính thường nên ổn định vì nó có thể được tham chiếu bởi các bảng khác.

## 5. Khóa chính ghép và kiểu ID của Repository

Một Entity có thể có khóa chính gồm nhiều thuộc tính, ví dụ một dòng hàng được xác định bởi cả mã đơn hàng và số thứ tự dòng. Trong JPA, hai cách ánh xạ phổ biến là @EmbeddedId và @IdClass.

Khi dùng khóa chính ghép, ID type trong Repository là **lớp đại diện cho toàn bộ khóa ghép**, không phải kiểu của riêng một thành phần.

### Cách 1: Dùng @EmbeddedId

Tạo lớp khóa có @Embeddable:

~~~java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineKey implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineKey that)) return false;
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity chứa thuộc tính @EmbeddedId:

~~~java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineKey id;

    private String productName;

    protected OrderLine() {
    }

    public OrderLine(OrderLineKey id, String productName) {
        this.id = id;
        this.productName = productName;
    }

    public OrderLineKey getId() {
        return id;
    }
}
~~~

Repository phải khai báo lớp khóa ghép làm tham số thứ hai:

~~~java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineKey> {
}
~~~

Cách gọi:

~~~java
OrderLineKey key = new OrderLineKey(100L, 2);

Optional<OrderLine> line =
        orderLineRepository.findById(key);

orderLineRepository.deleteById(key);
~~~

Ở đây, T = OrderLine và ID = OrderLineKey. Không khai báo JpaRepository<OrderLine, Long> vì khóa chính của Entity là cả cặp orderId và lineNumber.

Lớp khóa chính cần triển khai equals() và hashCode() dựa trên toàn bộ thành phần khóa. Điều này rất quan trọng để so sánh khóa và quản lý Entity nhất quán. Theo mô hình khóa chính ghép truyền thống của JPA, lớp khóa cần có constructor không tham số phù hợp và triển khai Serializable.

### Cách 2: Dùng @IdClass

Với @IdClass, các thuộc tính khóa được khai báo riêng trên Entity và lớp ID chỉ mô tả cấu trúc của khóa:

~~~java
import java.io.Serializable;
import java.util.Objects;

public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
@IdClass(OrderLineId.class)
public class OrderLine {

    @Id
    private Long orderId;

    @Id
    private Integer lineNumber;

    private String productName;

    protected OrderLine() {
    }
}
~~~

Repository:

~~~java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {
}
~~~

Với @IdClass, tên và kiểu Java của các thuộc tính trong lớp khóa phải tương ứng với các thuộc tính @Id trên Entity. Lớp khóa cũng cần equals(), hashCode(), khả năng serialize và constructor không tham số theo yêu cầu của mô hình JPA.

Không khai báo ID type là Long chỉ vì một thành phần của khóa ghép có kiểu Long. Repository cần nhận toàn bộ khóa dưới dạng OrderLineId.

## 6. Kiểu Entity và ID ảnh hưởng đến các phương thức Repository thế nào?

Khi đã khai báo:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Các thao tác cơ bản có kiểu dữ liệu nhất quán:

~~~java
Optional<Product> findById(Long id);

boolean existsById(Long id);

void deleteById(Long id);

<S extends Product> S save(S entity);

List<Product> findAll();
~~~

Bạn không cần tự viết lại các phương thức CRUD cơ bản. Spring Data cung cấp chúng dựa trên Entity type và ID type.

Các phương thức truy vấn theo thuộc tính khác của Entity cũng dùng Entity type làm kiểu trả về:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByName(String name);

    Optional<Product> findFirstByNameOrderByIdAsc(String name);

    boolean existsByName(String name);
}
~~~

Tên thuộc tính trong phương thức derived query phải tương ứng với thuộc tính Java của Entity. Ví dụ Entity có private String productName thì phương thức có thể là findByProductName(...), dù tên cột trong database là product_name.

Cần phân biệt findById(...) kế thừa từ Repository với truy vấn derived query. findById là phương thức chuẩn dùng khóa chính được khai báo trong ID generic. Nếu muốn tìm theo một thuộc tính nghiệp vụ khác, hãy đặt tên theo thuộc tính đó, ví dụ findByCode(...) hoặc findByEmail(...).

Với phân trang, kiểu Entity cũng quyết định kiểu phần tử trong kết quả:

~~~java
Page<Product> findByNameContaining(
        String keyword,
        Pageable pageable
);
~~~

Kết quả là một Page<Product> vì Repository quản lý Entity Product.

## 7. Có thể tạo Repository cơ sở dùng generic không?

Trong dự án có nhiều Entity, có thể tạo một interface cơ sở để tái sử dụng khai báo chung:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {
}
~~~

Sau đó, từng Repository cụ thể cung cấp kiểu Entity và ID:

~~~java
public interface ProductRepository
        extends BaseRepository<Product, Long> {
}

public interface CategoryRepository
        extends BaseRepository<Category, String> {
}
~~~

@NoRepositoryBean báo cho Spring Data rằng interface cơ sở này là cấu trúc dùng để kế thừa, không phải Repository cụ thể cần tạo bean trực tiếp. Mỗi Repository con phải xác định kiểu Entity và ID thực tế.

Không nên dùng raw type như JpaRepository hoặc khai báo kiểu quá rộng như JpaRepository<Object, Object> để né lỗi generic. Cách đó làm mất kiểm tra kiểu và khiến cấu hình Repository khó hiểu, dễ phát sinh lỗi khi chạy.

## 8. Những lỗi khai báo thường gặp

### Dùng sai ID type

Entity:

~~~java
@Entity
public class Product {

    @Id
    private Long id;
}
~~~

Khai báo sai:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, String> {
}
~~~

Khai báo đúng:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

ID type phải theo kiểu Java của thuộc tính @Id. Nếu không khớp, lời gọi các phương thức như findById, existsById và deleteById có thể bị lỗi kiểu ngay khi biên dịch hoặc phát sinh lỗi khi tích hợp với metadata JPA.

### Dùng kiểu cột database thay cho kiểu Java

Không viết JpaRepository<Product, "BIGINT">. Generic cần một kiểu Java như Long, không nhận tên kiểu SQL dưới dạng chuỗi.

### Dùng kiểu primitive trong generic

Không thể viết JpaRepository<Product, long> vì generic Java không nhận primitive. Dùng Long.

### Dùng nhầm DTO làm Entity type

Một DTO không được JPA quản lý không thể thay thế Entity trong JpaRepository. Hãy khai báo Repository theo Entity, sau đó dùng projection hoặc DTO ở các phương thức truy vấn khi cần.

### Quên khai báo ID trong Entity

Entity cần có khóa chính được JPA nhận diện bằng @Id hoặc cấu trúc khóa ghép hợp lệ. Nếu không có khóa chính, Hibernate không thể quản lý Entity theo mô hình JPA thông thường.

### Khai báo ID generic là một phần của khóa ghép

Với Entity dùng @EmbeddedId hoặc @IdClass, hãy dùng lớp khóa ghép làm tham số thứ hai. Không dùng kiểu của một trường riêng lẻ trong khóa.

### Khai báo lại findById với kiểu khác

Không tự khai báo một phương thức findById(String id) trong Repository có ID generic là Long để tìm theo một cột nghiệp vụ. Dùng tên truy vấn theo thuộc tính, ví dụ findByCode(String code). Giữ findById(Long id) cho khóa chính.

## 9. Cách kiểm tra trước khi khai báo Repository

Khi tạo Repository cho một Entity mới, có thể thực hiện lần lượt:

1. Xác định lớp Entity được đánh dấu @Entity.
2. Tìm thuộc tính có @Id hoặc cấu trúc @EmbeddedId / @IdClass.
3. Đọc kiểu Java của khóa chính: Long, Integer, String, UUID hoặc lớp khóa ghép.
4. Khai báo JpaRepository<EntityType, IdType> bằng đúng hai kiểu đó.
5. Kiểm tra các lời gọi findById, save, deleteById và truy vấn theo thuộc tính có kiểu đối số/kết quả đúng.
6. Khởi động ứng dụng và xác nhận Spring Data nhận diện Repository, Entity và khóa chính.

Bảng kiểm nhanh:

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Repository quản lý Entity nào? | Lớp @Entity cụ thể |
| Entity dùng khóa đơn hay khóa ghép? | @Id, @EmbeddedId hoặc @IdClass |
| ID type là gì? | Kiểu Java của khóa hoặc lớp khóa ghép |
| Generic thứ nhất là gì? | Chính lớp Entity |
| Generic thứ hai là gì? | Chính kiểu ID |
| Phương thức tìm theo thuộc tính khác dùng tên gì? | Tên thuộc tính Java của Entity |

## 10. Lưu ý về phiên bản Jakarta Persistence

Các ví dụ trong bài dùng namespace jakarta.persistence, phù hợp với Spring Boot 3 trở lên và hệ sinh thái Jakarta EE tương ứng. Dự án Spring Boot 2 thường dùng namespace cũ javax.persistence. Không trộn hai namespace trong cùng một mô hình Entity; hãy dùng đúng phiên bản dependency mà dự án đang sử dụng.

Một số khả năng đặc thù, chẳng hạn chiến lược tự sinh UUID, phụ thuộc phiên bản Jakarta Persistence và JPA provider. Nếu dùng kiểu ID đặc thù, hãy kiểm tra hỗ trợ của phiên bản Hibernate và database đang chạy thay vì chỉ đổi generic trong Repository.

## 11. Kết luận

Trong khai báo JpaRepository<T, ID>, T là lớp Entity được JPA quản lý và ID là kiểu Java của khóa chính. Với khóa đơn, ID generic phải khớp với kiểu thuộc tính @Id; với khóa ghép, ID generic là lớp khóa được dùng trong @EmbeddedId hoặc @IdClass. Khi hai kiểu được khai báo chính xác, Spring Data có thể cung cấp các phương thức CRUD với kiểm tra kiểu rõ ràng, giúp mã Repository an toàn và dễ bảo trì hơn.
