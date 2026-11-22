# Tránh dùng projection hoặc aggregate thiếu cột làm đầu vào save

Trong Spring Data JDBC, **projection và DTO thường phục vụ việc đọc một phần dữ liệu**, còn **repository.save(aggregate)** dùng đối tượng aggregate để đồng bộ trạng thái lưu trữ. Hai mục đích này khác nhau.

Một projection chỉ chứa ID, tên và giá sản phẩm có thể đủ để hiển thị danh sách. Nhưng nếu lấy ba giá trị đó rồi dựng một Product chỉ có một phần thông tin, sau đó gọi save, ứng dụng có thể vô tình ghi đè các thuộc tính bị bỏ sót hoặc làm mất entity con được sở hữu trong aggregate.

Spring Data JDBC không giữ snapshot trước đó để tự suy ra “chỉ sửa trường name”. Khi lưu aggregate đã tồn tại, framework xem đối tượng được truyền vào là trạng thái cần lưu. Với entity con được sở hữu, cơ chế cập nhật còn có thể xóa các hàng con hiện tại rồi chèn lại theo collection trong aggregate được truyền vào.

Vì vậy, cần phân biệt rõ:

- **Projection/DTO đọc:** lấy một phần dữ liệu để hiển thị, báo cáo hoặc trả API.
- **Aggregate đầy đủ:** dùng để thực hiện thay đổi domain và lưu bằng repository.
- **Cập nhật một phần:** dùng read-modify-save với aggregate đầy đủ, câu SQL update có chủ đích hoặc một reduced aggregate-root mapping được thiết kế riêng.

Bài học giải thích các rủi ro khi dùng dữ liệu thiếu cột làm đầu vào save, cách chọn giải pháp cập nhật an toàn và những phần logic cần tự bảo vệ khi dùng SQL tùy chỉnh.

## 1. Projection và aggregate persistence object có mục đích khác nhau

Projection là một kiểu kết quả chỉ phơi bày những thuộc tính mà use case đọc cần. Ví dụ màn hình danh sách chỉ cần mã, tên và giá sản phẩm:

~~~java
public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

Repository có thể khai báo phương thức truy vấn trả về projection:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<ProductSummary> findByStatus(String status);
}
~~~

Use case đọc:

~~~java
List<ProductSummary> products =
        productRepository.findByStatus("ACTIVE");
~~~

Ở đây, ứng dụng chỉ cần hiển thị ba trường. Projection không phải aggregate đầy đủ và không nên được coi là đối tượng persistence để lưu trở lại.

Một aggregate root có thể có nhiều thuộc tính hơn:

~~~java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;
    private BigDecimal price;
    private String status;
    private String description;
    private boolean active;

    @Version
    private Long version;

    @MappedCollection(
            idColumn = "product_id",
            keyColumn = "attribute_position"
    )
    private List<ProductAttribute> attributes = new ArrayList<>();

    // Constructor, getter và phương thức domain
}
~~~

Projection ProductSummary không chứa status, description, active, version hay attributes. Đây là điều hoàn toàn bình thường với một read model.

Vấn đề bắt đầu khi ứng dụng chuyển dữ liệu projection thành một instance có thể lưu mà không khôi phục trạng thái còn thiếu.

## 2. Vì sao save một aggregate thiếu dữ liệu nguy hiểm?

Spring Data JDBC không giữ một persistence context để theo dõi từng thuộc tính đã thay đổi như một số ORM. Framework không biết rằng một thuộc tính bị thiếu trong object là:

- Người dùng muốn xóa giá trị.
- Projection không tải thuộc tính đó.
- Mapper chưa gán thuộc tính.
- Constructor dùng giá trị mặc định.
- Collection chưa được tải.
- Dữ liệu thực sự có giá trị null hoặc rỗng.

Khi gọi save, trạng thái của aggregate được truyền vào là cơ sở để persist.

Tài liệu Spring Data Relational mô tả rằng khi aggregate root đã tồn tại, Spring Data JDBC xóa các entity được tham chiếu trong aggregate, cập nhật root rồi chèn lại các entity được tham chiếu theo trạng thái hiện tại. Framework không biết trạng thái trước đó của aggregate, nên cần đồng bộ database thành trạng thái của object được truyền vào.

Điều đó dẫn đến hai nhóm rủi ro.

### 2.1. Thuộc tính scalar bị ghi bằng giá trị không mong muốn

Giả sử bảng:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    description VARCHAR(1000),
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);
~~~

Dữ liệu hiện tại:

~~~text
id   name       price     status   description         active   version
---  ---------  --------  -------  ------------------  -------  -------
10   Keyboard   120.00    ACTIVE   Mechanical switch   true     4
~~~

Projection chỉ có:

~~~java
public record ProductSummary(
        Long id,
        String name,
        BigDecimal price
) {
}
~~~

Nếu mapper tạo một aggregate thiếu trường:

~~~java
Product partial = new Product(
        summary.id(),
        summary.name(),
        summary.price(),
        null,       // status không có trong projection
        null,       // description không có trong projection
        false,      // active nhận default primitive
        null,       // version không có trong projection
        List.of()   // attributes không được tải
);
~~~

thì các giá trị null, false và collection rỗng có thể bị hiểu là trạng thái thực sự cần lưu.

Tùy mapping và schema, kết quả có thể là:

- status bị đặt thành NULL hoặc phát sinh lỗi vì NOT NULL.
- description bị xóa.
- active bị đổi thành false dù trước đó là true.
- version bị thiếu khiến optimistic locking hoặc state detection không còn đúng như dự kiến.
- Collection attributes bị đồng bộ thành rỗng và các hàng con hiện có bị xóa.

Đây không phải lỗi của projection. Projection đã làm đúng nhiệm vụ đọc ít dữ liệu. Lỗi nằm ở việc coi dữ liệu đọc một phần là trạng thái aggregate hoàn chỉnh để ghi.

### 2.2. Entity con được sở hữu có thể bị xóa

Rủi ro với collection còn nghiêm trọng hơn.

Giả sử một sản phẩm có ba thuộc tính:

~~~text
Product 10
  attributes:
    COLOR = BLACK
    LAYOUT = US
    SWITCH = RED
~~~

Projection chỉ đọc id và name. Khi mapper dựng aggregate mới mà không có collection, constructor có thể để attributes là List.of().

Nếu gọi save với aggregate đã tồn tại, Spring Data JDBC có thể đồng bộ collection được sở hữu theo trạng thái rỗng đó. Các hàng thuộc collection hiện tại có thể bị xóa.

~~~text
Database trước save:
  product_attributes
    product_id = 10, COLOR = BLACK
    product_id = 10, LAYOUT = US
    product_id = 10, SWITCH = RED

Aggregate dựng từ projection:
  id = 10
  name = Keyboard
  attributes = []

Sau save:
  product_attributes của product 10 không còn các hàng trên
~~~

Vì vậy, **không được mặc định rằng collection không có trong projection đồng nghĩa collection không thay đổi**. Với aggregate persistence, collection rỗng là một trạng thái có ý nghĩa và có thể được ghi xuống database.

## 3. Phân biệt projection, DTO và reduced aggregate root

Ba kiểu dữ liệu sau có thể trông giống nhau trong Java nhưng vai trò khác nhau.

| Kiểu | Mục đích | Dùng trực tiếp với save? |
| --- | --- | --- |
| Projection interface | Đọc một phần thuộc tính qua accessor | Không |
| DTO/record kết quả truy vấn | Trả dữ liệu cho API, báo cáo hoặc màn hình | Không |
| Command DTO | Mang ý định thay đổi từ client vào service | Không |
| Aggregate root đầy đủ | Đại diện trạng thái domain được repository quản lý | Có |
| Reduced aggregate-root mapping | Ánh xạ có chủ đích một phần cột của cùng bảng để thực hiện use case giới hạn | Có thể, nhưng cần hiểu rõ giới hạn |

### 3.1. Projection interface

Ví dụ:

~~~java
public interface ProductSummary {
    Long getId();
    String getName();
}
~~~

Nó mô tả các giá trị cần đọc. Không có hợp đồng rằng projection chứa mọi thuộc tính hoặc collection của aggregate.

### 3.2. DTO/record

Ví dụ:

~~~java
public record ProductDetailsDto(
        Long id,
        String name,
        BigDecimal price,
        String status
) {
}
~~~

DTO có thể được dùng làm response hoặc dữ liệu trung gian. Việc DTO có một số trường trùng với entity không biến nó thành aggregate.

### 3.3. Command DTO

Ví dụ request đổi tên:

~~~java
public record RenameProductRequest(String newName) {
}
~~~

Command DTO diễn đạt **ý định**: đổi tên sản phẩm. Nó không cần chứa toàn bộ sản phẩm và cũng không nên được lưu thẳng vào repository.

Service dùng command để thay đổi aggregate đầy đủ:

~~~java
@Transactional
public Product renameProduct(
        Long productId,
        RenameProductRequest request
) {
    Product product = productRepository.findById(productId)
            .orElseThrow();

    product.rename(request.newName());

    return productRepository.save(product);
}
~~~

Đây là cách an toàn và dễ hiểu: tải aggregate đầy đủ, áp dụng hành vi domain rồi save.

### 3.4. Reduced aggregate-root mapping là trường hợp riêng

Spring Data JDBC cũng có thể dùng một class khác ánh xạ cùng bảng nhưng chỉ chứa một số thuộc tính của aggregate root. Đây là một kỹ thuật có chủ đích để cập nhật một phần root trong những use case phù hợp.

Ví dụ bảng products có các cột id, name, price, status, description, active và version. Một class ánh xạ rút gọn có thể chỉ gồm id, name và version:

~~~java
@Table("products")
public class ProductNameView {

    @Id
    private Long id;

    private String name;

    @Version
    private Long version;

    protected ProductNameView() {
    }

    public ProductNameView(Long id, String name, Long version) {
        this.id = id;
        this.name = name;
        this.version = version;
    }

    // Getter
}
~~~

Repository riêng:

~~~java
public interface ProductNameViewRepository
        extends CrudRepository<ProductNameView, Long> {
}
~~~

Đây không phải projection interface hay DTO. Đây là một persistence mapping có chủ đích đến cùng bảng, được dùng như một reduced view của aggregate root.

Khi save object này, Spring Data JDBC chỉ biết những thuộc tính được mapping bởi class này. Các cột root khác không thuộc mapping đó có thể được giữ nguyên trong database. Tuy nhiên, kỹ thuật này chỉ nên áp dụng có kiểm soát cho **aggregate root**; không được suy rộng thành quy tắc an toàn cho entity con bên trong aggregate.

Bài viết của Spring về partial update giải thích cách tiếp cận này và nhấn mạnh giới hạn đối với entities bên trong aggregate: chúng bị xóa và tạo lại; các cột không có trong reduced view của entity con có thể trở về giá trị mặc định.

## 4. Cách an toàn nhất: read-modify-save với aggregate đầy đủ

Với thay đổi domain thông thường, hãy tải aggregate qua repository trước khi sửa.

Ví dụ:

~~~java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;
    private BigDecimal price;
    private String status;
    private String description;
    private boolean active;

    @Version
    private Long version;

    @MappedCollection(
            idColumn = "product_id",
            keyColumn = "attribute_position"
    )
    private List<ProductAttribute> attributes = new ArrayList<>();

    protected Product() {
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                    "Product name is required"
            );
        }
        this.name = newName;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Price must be non-negative"
            );
        }
        this.price = newPrice;
    }

    public void deactivate() {
        this.active = false;
    }
}
~~~

Service:

~~~java
@Transactional
public Product changePrice(Long id, BigDecimal newPrice) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    product.changePrice(newPrice);

    return productRepository.save(product);
}
~~~

Luồng dữ liệu:

~~~text
Client gửi command
       |
       v
Service nhận productId + dữ liệu thay đổi
       |
       v
Repository tải aggregate đầy đủ
       |
       v
Aggregate thực thi phương thức domain
       |
       v
Repository.save(aggregate)
       |
       v
Database đồng bộ trạng thái aggregate
~~~

Cách này bảo toàn những thuộc tính và collection đã được tải, đồng thời cho aggregate cơ hội kiểm tra bất biến trước khi persist.

### 4.1. Vì sao không nên tạo entity mới chỉ từ request?

Không an toàn:

~~~java
@Transactional
public Product changePrice(
        Long id,
        BigDecimal newPrice
) {
    Product partial = new Product();
    partial.setId(id);
    partial.setPrice(newPrice);

    return productRepository.save(partial);
}
~~~

Object này chỉ có ID và giá mới. Các thuộc tính khác có thể là null/default và collection có thể rỗng. Save không tự hiểu rằng “chỉ cập nhật price”.

Thay vào đó:

~~~java
@Transactional
public Product changePrice(
        Long id,
        BigDecimal newPrice
) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    product.changePrice(newPrice);

    return productRepository.save(product);
}
~~~

Khác biệt là aggregate thứ hai được khôi phục từ database trước khi sửa.

### 4.2. Dùng projection để đọc, aggregate để ghi

Một service có thể sử dụng projection ở luồng đọc và aggregate đầy đủ ở luồng ghi:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<ProductSummary> findByStatus(String status);
}
~~~

Đọc:

~~~java
public List<ProductSummary> listActiveProducts() {
    return productRepository.findByStatus("ACTIVE");
}
~~~

Ghi:

~~~java
@Transactional
public Product rename(Long id, String newName) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    product.rename(newName);

    return productRepository.save(product);
}
~~~

Đây là sự phân công rõ ràng: projection phục vụ truy vấn đọc, aggregate root phục vụ thay đổi domain và persistence.

## 5. Khi nào reduced aggregate-root mapping có thể phù hợp?

Không phải mọi cập nhật một phần đều bắt buộc phải tải toàn bộ aggregate nếu use case chỉ thay đổi một vài cột root và có thể tách biệt rõ ràng.

Ví dụ, một tác vụ quản trị chỉ đổi tên sản phẩm. Domain có thể có một mapping riêng cùng bảng:

~~~java
@Table("products")
public record ProductNameRecord(
        @Id Long id,
        String name,
        @Version Long version
) {
}
~~~

Repository:

~~~java
public interface ProductNameRecordRepository
        extends CrudRepository<ProductNameRecord, Long> {
}
~~~

Service:

~~~java
@Transactional
public ProductNameRecord renameUsingReducedRoot(
        Long id,
        String newName
) {
    ProductNameRecord current =
            productNameRecordRepository.findById(id)
                    .orElseThrow();

    ProductNameRecord updated = new ProductNameRecord(
            current.id(),
            newName,
            current.version()
    );

    return productNameRecordRepository.save(updated);
}
~~~

Cách này có thể hữu ích khi:

- Chỉ cập nhật các cột thuộc aggregate root.
- Không cần đọc collection con cho use case.
- Cột version được xử lý đúng để tránh ghi đè thay đổi đồng thời.
- Mapping rút gọn được xem là một persistence model riêng, không bị nhầm với aggregate đầy đủ.
- Có kiểm thử xác nhận các cột bị bỏ khỏi reduced mapping vẫn được giữ nguyên.

**Đây là kỹ thuật nâng cao, không phải cách thay thế mặc định cho aggregate root.** Nếu use case thay đổi quy tắc nghiệp vụ liên quan đến các thuộc tính khác hoặc collection con, hãy tải aggregate đầy đủ.

### 5.1. Giới hạn: chỉ áp dụng có chủ đích cho aggregate root

Giả sử aggregate Product có collection attributes. Reduced root mapping không khai báo collection đó:

~~~text
Product aggregate đầy đủ:
  id
  name
  price
  status
  version
  attributes[]

Reduced root mapping:
  id
  name
  version
~~~

Khi lưu reduced root mapping, Spring Data JDBC không có metadata để xử lý collection attributes như một phần của mapping này; các hàng child không bị xóa chỉ vì class rút gọn không khai báo collection đó.

Nhưng nếu tạo reduced mapping cho **entity con**:

~~~java
@Table("product_attributes")
public record ProductAttributeView(
        Long productId,
        String key
) {
}
~~~

rồi dùng nó như một cách save một phần của entity con trong aggregate, hành vi persistence của aggregate có thể xóa và tạo lại entity con. Các cột bị thiếu trong reduced view có thể bị đặt về default hoặc giá trị không mong muốn.

Do đó, không dùng một reduced child entity như giải pháp partial update chung.

### 5.2. Bảo vệ root và child bằng khóa ngoại

Nếu dùng một reduced root mapping cùng bảng với aggregate đầy đủ, schema vẫn cần bảo vệ quan hệ với bảng con.

Ví dụ:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE product_attributes (
    product_id BIGINT NOT NULL REFERENCES products(id),
    attribute_position INTEGER NOT NULL,
    attribute_key VARCHAR(100) NOT NULL,
    attribute_value VARCHAR(500) NOT NULL,
    PRIMARY KEY (product_id, attribute_position)
);
~~~

Foreign key bảo vệ không cho xóa root khi vẫn còn hàng con nếu không có chính sách cascade phù hợp. Hãy cân nhắc cẩn thận khi có nhiều repository mapping cùng bảng; thao tác xóa từ reduced repository vẫn có thể ảnh hưởng toàn bộ root và phải tuân theo schema/domain.

## 6. Cập nhật một cột bằng SQL có chủ đích

Nếu mục tiêu là cập nhật một vài cột và không cần thực hiện toàn bộ aggregate persistence, có thể dùng câu lệnh SQL tùy chỉnh.

Ví dụ repository:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    @Modifying
    @Query("""
            UPDATE products
               SET name = :name,
                   version = version + 1
             WHERE id = :id
               AND version = :version
            """)
    int renameIfVersionMatches(
            @Param("id") Long id,
            @Param("name") String name,
            @Param("version") Long version
    );
}
~~~

Service:

~~~java
@Transactional
public void renameWithDirectUpdate(
        Long id,
        String newName
) {
    Product current = productRepository.findById(id)
            .orElseThrow();

    int updated = productRepository.renameIfVersionMatches(
            id,
            newName,
            current.getVersion()
    );

    if (updated != 1) {
        throw new OptimisticLockingFailureException(
                "Product was changed by another transaction"
        );
    }
}
~~~

Ví dụ dùng version trong điều kiện WHERE và tăng version trong cùng câu lệnh. Điều này giúp tránh việc một request dùng dữ liệu cũ ghi đè một cập nhật mới hơn.

Tuy nhiên, câu SQL trực tiếp **bỏ qua một phần cơ chế persistence của Spring Data JDBC**. Ứng dụng phải tự bảo đảm các hành vi liên quan.

### 6.1. Những trách nhiệm khi dùng direct SQL

| Cơ chế thông thường | Khi dùng SQL tùy chỉnh cần xem xét |
| --- | --- |
| Optimistic locking | Tự kiểm tra version trong WHERE và tăng version đúng cách. |
| Auditing | Tự cập nhật cột như updated_at, updated_by nếu cần. |
| Domain behavior | Gọi/thiết kế service để bảo đảm bất biến trước khi ghi. |
| Entity callbacks | Xác định callback nào không còn được thực thi và có cần thay thế không. |
| Events | Nếu ứng dụng phát event sau khi save, direct update cần có cơ chế phát event phù hợp. |
| Transaction | Đặt ranh giới transaction cho SQL và các thao tác liên quan. |
| Validation | Kiểm tra dữ liệu đầu vào và ràng buộc database. |

Nếu update SQL không tăng version trong khi entity khác vẫn dùng @Version, một object cũ có thể không nhận biết được cập nhật trực tiếp. Điều này có thể làm suy yếu optimistic locking.

### 6.2. Khi nào nên dùng custom repository?

Nếu cập nhật một phần phức tạp, cần nhiều câu SQL hoặc thao tác bảng con cụ thể, custom repository implementation có thể rõ ràng hơn một method @Query dài.

Ví dụ custom repository có thể dùng NamedParameterJdbcOperations để:

1. Kiểm tra dữ liệu cần cập nhật.
2. Thực hiện câu UPDATE có điều kiện version.
3. Kiểm tra số hàng bị ảnh hưởng.
4. Cập nhật bảng phụ nếu nghiệp vụ yêu cầu.
5. Phát sinh ngoại lệ optimistic locking khi không có hàng nào được cập nhật.

Đây là cách linh hoạt nhưng đi kèm trách nhiệm tự quản lý các quy tắc mà repository persistence mặc định vốn thực hiện.

## 7. Không nhầm update một phần với insert/update/upsert

Các API persistence có ý nghĩa khác nhau:

| API | Ý nghĩa |
| --- | --- |
| CrudRepository.save(aggregate) | Xác định aggregate mới hay đã tồn tại rồi thực hiện insert/update aggregate. |
| JdbcAggregateTemplate.insert(aggregate) | Giả định aggregate mới và thực hiện insert. |
| JdbcAggregateTemplate.update(aggregate) | Giả định aggregate đã tồn tại và thực hiện update. |
| JdbcAggregateTemplate.upsert(aggregate) | Dùng native upsert nếu dialect hỗ trợ và aggregate có ID. |
| @Modifying @Query | Thực thi SQL update/delete tùy chỉnh, do ứng dụng định nghĩa. |

JdbcAggregateTemplate.update không có nghĩa “chỉ cập nhật những property đã thay đổi”. Nó vẫn là thao tác cập nhật aggregate theo mapping persistence. Tương tự, save không phải một lệnh PATCH tự động chỉ thay đổi trường khác null.

Native upsert cũng không tự giải quyết vấn đề partial aggregate. Nó quyết định insert hay update theo khóa, không tự biết thuộc tính bị thiếu trong object là “không thay đổi”.

## 8. Những tình huống dễ gây mất dữ liệu

### 8.1. Map DTO trực tiếp sang entity

Không an toàn:

~~~java
Product product = mapper.toProduct(updateRequest);
productRepository.save(product);
~~~

Nếu updateRequest chỉ có một số trường, mapper có thể tạo object với các thuộc tính còn lại null/default.

An toàn hơn:

~~~java
Product product = productRepository.findById(updateRequest.id())
        .orElseThrow();

product.changePrice(updateRequest.price());

productRepository.save(product);
~~~

### 8.2. Collection không được gửi trong request

Giả sử request đổi tên sản phẩm không có field attributes. Nếu mapper tạo aggregate mới với attributes là collection rỗng, save có thể xóa collection hiện tại.

Đối với API cập nhật, cần phân biệt:

- Không gửi collection: không yêu cầu thay đổi collection.
- Gửi collection rỗng: yêu cầu collection trở thành rỗng.
- Gửi collection có phần tử: thay đổi theo hợp đồng API.

Không dùng một DTO thiếu field làm aggregate persistence object.

### 8.3. Primitive bị đặt về default

Nếu DTO không có field active và mapper dựng entity với primitive boolean active, giá trị có thể là false. Save có thể ghi false dù sản phẩm đang active.

Với trường tùy chọn ở request, wrapper như Boolean giúp nhận diện null, nhưng null vẫn cần được diễn giải theo contract. Nó không tự động có nghĩa “giữ nguyên giá trị cũ”.

### 8.4. Bỏ qua optimistic locking

Nếu mapper không mang version nhưng tạo aggregate có version null hoặc default, save có thể thất bại hoặc không bảo vệ cập nhật cạnh tranh theo cách mong muốn.

Đừng loại bỏ version chỉ vì response DTO không cần hiển thị nó. Version là metadata persistence, không nhất thiết là field công khai của API.

### 8.5. Reduced mapping cho child entity

Đây là trường hợp nguy hiểm vì Spring Data JDBC có thể xóa và tạo lại entity con khi save aggregate. Nếu child mapping thiếu cột, giá trị bị thiếu có thể trở về default.

Nếu cần thay đổi một thuộc tính của child entity được sở hữu, hãy tải aggregate đầy đủ, thay đổi qua root rồi save; hoặc xem xét custom SQL có kiểm soát và đánh giá lại ranh giới aggregate nếu child cần cập nhật độc lập.

## 9. Thiết kế DTO đọc và DTO ghi rõ ràng

Một ứng dụng thường có ba mô hình dữ liệu khác nhau:

~~~text
Database
   |
   v
Aggregate root (domain + persistence)
   |
   +----> Projection / Read DTO ----> API response / UI
   |
   <---- Command DTO --------------- API request / use case
~~~

### 9.1. Read DTO

Dùng để trình bày dữ liệu:

~~~java
public record ProductListItem(
        Long id,
        String name,
        BigDecimal price
) {
}
~~~

Read DTO có thể thiếu nhiều thuộc tính vì màn hình không cần chúng.

### 9.2. Command DTO

Dùng để mô tả ý định:

~~~java
public record ChangeProductPriceCommand(
        BigDecimal newPrice
) {
}
~~~

Command DTO chỉ mang những giá trị cần thiết cho use case. Service quyết định cách áp dụng lên aggregate.

### 9.3. Aggregate root

Dùng để thực thi domain behavior và persistence:

~~~java
public void changePrice(BigDecimal newPrice) {
    if (newPrice == null || newPrice.signum() < 0) {
        throw new IllegalArgumentException("Invalid price");
    }

    this.price = newPrice;
}
~~~

Không cần đưa toàn bộ aggregate vào response DTO, và không cần dùng response DTO làm entity để save. Giữ ba mô hình riêng giúp tránh nhầm lẫn về trách nhiệm.

## 10. Cập nhật nhiều trường một phần qua command

Một command có thể thay đổi một số thuộc tính:

~~~java
public record UpdateProductCommand(
        String name,
        BigDecimal price,
        Boolean active
) {
}
~~~

Service:

~~~java
@Transactional
public Product updateProduct(
        Long id,
        UpdateProductCommand command
) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    if (command.name() != null) {
        product.rename(command.name());
    }

    if (command.price() != null) {
        product.changePrice(command.price());
    }

    if (command.active() != null) {
        product.setActive(command.active());
    }

    return productRepository.save(product);
}
~~~

Đây là hợp đồng “null nghĩa là không thay đổi” cho ba trường trong command. Nếu API cần cho phép xóa giá trị bằng cách gửi null, cần thêm cách biểu diễn presence riêng, vì null ở đây đã được dùng để chỉ “không cập nhật”.

Với API PATCH, có thể dùng wrapper/presence type, JSON Merge Patch, field mask hoặc một cấu trúc command thể hiện rõ ba trạng thái:

- Không gửi field: giữ nguyên.
- Gửi giá trị: cập nhật.
- Gửi null có chủ đích: xóa giá trị nếu domain cho phép.

Sau khi xác định ý định, service vẫn tải aggregate đầy đủ và áp dụng thay đổi có kiểm soát.

## 11. Chú ý với projection và method repository

Spring Data hỗ trợ projection trong query methods để trả về một phần thuộc tính. Ví dụ:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<ProductSummary> findByStatus(String status);
}
~~~

Projection có thể là interface-based hoặc class-based DTO tùy cách khai báo và hỗ trợ của store module. Cần nhớ:

- Projection là kiểu kết quả truy vấn.
- Projection không thay đổi aggregate mapping gốc.
- Projection không tự trở thành đối tượng có thể persist.
- Không nên override một base repository method như findById với return type projection rồi kỳ vọng Spring Data tự biến nó thành query method khác; base method có thể được gọi theo hợp đồng gốc và projection không áp dụng như mong đợi.
- Với query tùy chỉnh, cần bảo đảm các cột trả về phù hợp với projection/DTO đã khai báo.

Nếu mục tiêu là đọc ít cột, projection là lựa chọn tốt. Nếu mục tiêu là cập nhật ít cột, hãy chọn read-modify-save, reduced root mapping có chủ đích hoặc SQL update tùy chỉnh. Hai use case không nên bị trộn vào một kiểu object duy nhất.

## 12. Kiểm tra tác động khi lưu aggregate

Khi điều tra một lỗi mất dữ liệu sau save, hãy kiểm tra:

1. Object được truyền vào repository là aggregate đầy đủ hay được dựng từ projection/DTO?
2. Các trường scalar nào không được tải và đang có null/default?
3. Collection nào không được tải nhưng được khởi tạo thành collection rỗng?
4. Có entity con nào bị xóa và tạo lại khi save không?
5. Có reduced mapping khác cùng trỏ đến bảng root hoặc child không?
6. Version có được đọc và cập nhật đúng không?
7. Có custom SQL nào bỏ qua auditing, callbacks hoặc domain behavior không?
8. Database có foreign key và constraint bảo vệ dữ liệu quan trọng không?
9. Câu SQL thực tế được phát ra là gì?
10. Có request đồng thời nào ghi trạng thái cũ lên trạng thái mới không?

Bật SQL logging trong môi trường phát triển hoặc dùng công cụ theo dõi JDBC để quan sát câu lệnh thực tế. Đừng suy luận từ việc method Java tên save rằng framework chỉ cập nhật một cột.

## 13. Những lỗi thường gặp

**“Projection có ID nên có thể save như entity.”** Không đúng. ID chỉ là một phần định danh; projection có thể thiếu các thuộc tính và collection cần thiết để đại diện trạng thái aggregate.

**“Trường không có trong DTO sẽ được giữ nguyên khi save.”** Không đúng nếu mapper tạo aggregate đầy đủ với giá trị null/default cho trường đó. Spring Data JDBC không tự biết trường bị thiếu có nghĩa là “không đổi”.

**“Collection không có trong projection sẽ được giữ nguyên.”** Không đúng nếu bạn dựng aggregate với collection rỗng rồi save; trạng thái collection được sở hữu có thể được đồng bộ thành rỗng.

**“Save chỉ cập nhật những trường khác null.”** Không đúng. Save không phải PATCH. Null có thể là một giá trị cần persist nếu mapping và schema cho phép.

**“Dùng Optional trong projection rồi map sang entity là đủ.”** Không tự động. Optional có thể diễn đạt giá trị nullable trong read model, nhưng không mang đầy đủ ý nghĩa presence của một lệnh cập nhật.

**“Reduced aggregate root và projection là một.”** Không. Reduced aggregate-root mapping là một persistence type có chủ đích ánh xạ cùng bảng; projection là kiểu kết quả đọc. Kỹ thuật reduced root có giới hạn và cần được quản lý riêng.

**“Có thể dùng reduced view cho entity con.”** Không nên. Entity con trong aggregate có thể bị xóa và tạo lại khi save; cột bị bỏ khỏi mapping có thể nhận giá trị mặc định.

**“Direct UPDATE không cần version.”** Không đúng nếu aggregate dùng optimistic locking. SQL tùy chỉnh phải tự bảo vệ version và kiểm tra số hàng bị ảnh hưởng.

**“Direct UPDATE vẫn tự chạy callbacks và auditing.”** Không nên giả định như vậy. SQL tùy chỉnh bỏ qua một phần cơ chế persistence thông thường; cần tự xử lý các trách nhiệm liên quan.

**“Chỉ cần kiểm tra test happy path.”** Không đủ. Cần kiểm tra các cột không được cập nhật và collection con có còn nguyên sau thao tác.

## 14. Quy trình chọn cách cập nhật phù hợp

Khi một use case chỉ thay đổi một vài trường, hãy đi theo các bước:

1. **Xác định dữ liệu đầu vào:** projection, response DTO hay command DTO?
2. **Xác định đối tượng ghi:** aggregate root đầy đủ hay reduced mapping có chủ đích?
3. **Nếu cần domain behavior:** tải aggregate đầy đủ, gọi phương thức domain rồi save.
4. **Nếu chỉ cập nhật một cột độc lập:** cân nhắc SQL update/custom repository và quản lý version, auditing, callbacks.
5. **Nếu dùng reduced aggregate-root mapping:** chỉ dùng cho root fields phù hợp, tách repository/mapping rõ ràng và kiểm tra version.
6. **Không dùng reduced child entity:** tránh mất các cột không được mapping khi child bị delete/recreate.
7. **Kiểm tra collection:** bảo đảm không biến “không tải” thành “collection rỗng” khi save.
8. **Kiểm tra transaction và concurrency:** dùng optimistic locking hoặc cơ chế phù hợp.
9. **Kiểm tra SQL thực tế:** xác nhận cột và hàng con ngoài phạm vi thay đổi vẫn được bảo toàn.
10. **Kiểm tra schema:** dùng constraint/foreign key để ngăn dữ liệu con bị mất ngoài ý muốn.

~~~mermaid
flowchart TD
    A["Có dữ liệu một phần từ projection/DTO"] --> B{"Mục tiêu là đọc?"}
    B -->|Có| C["Dùng projection / read DTO"]
    B -->|Không, cần ghi| D{"Cần domain behavior hoặc thay đổi nhiều phần aggregate?"}
    D -->|Có| E["Load aggregate đầy đủ"]
    E --> F["Áp dụng command qua phương thức domain"]
    F --> G["repository.save(aggregate)"]
    D -->|Không| H{"Chỉ update root fields có kiểm soát?"}
    H -->|Có| I["Reduced aggregate-root mapping hoặc direct SQL"]
    H -->|Không| J["Thiết kế custom repository / xem lại boundary"]
    I --> K["Bảo vệ version, auditing, callbacks, constraints và transaction"]
    J --> K
    G --> L["Kiểm tra dữ liệu và collection"]
    K --> L
~~~

## 15. Bài tập thực hành

Tạo bảng products với các cột id, name, price, status, description, active và version. Tạo thêm bảng product_attributes có khóa ngoại về products.

### Bài 1: Đọc bằng projection

1. Khai báo ProductSummary chỉ có id, name và price.
2. Viết method findByStatus trả về List<ProductSummary>.
3. Dùng projection để hiển thị danh sách sản phẩm.
4. Xác nhận use case đọc không cần tải collection attributes.

### Bài 2: Thử save từ aggregate dựng thiếu dữ liệu

1. Đọc một projection.
2. Dựng aggregate persistence object với các trường không có trong projection nhận null/default.
3. Gọi save trên dữ liệu thử nghiệm riêng.
4. Quan sát các cột scalar và collection con.
5. Giải thích vì sao save coi các giá trị mặc định là trạng thái cần lưu.

Không thực hiện thử nghiệm phá hủy trên dữ liệu thật.

### Bài 3: Read-modify-save

1. Tải aggregate đầy đủ bằng findById.
2. Đổi tên qua phương thức domain.
3. Save aggregate.
4. Đọc lại và xác nhận các cột khác cùng collection con vẫn được giữ nguyên.

### Bài 4: Reduced aggregate-root mapping

1. Tạo một class persistence rút gọn cùng ánh xạ bảng products.
2. Chỉ khai báo ID, name và version.
3. Dùng repository riêng để đổi tên.
4. Kiểm tra price, status, description, active và product_attributes vẫn còn.
5. Thử xóa root qua reduced repository trong môi trường thử nghiệm và quan sát FK bảo vệ bảng con.

### Bài 5: Direct SQL update

1. Viết method @Modifying @Query cập nhật riêng tên sản phẩm.
2. Thêm điều kiện WHERE id = :id AND version = :version.
3. Tăng version trong cùng câu lệnh.
4. Kiểm tra số hàng được cập nhật.
5. Thử dùng version cũ và xác nhận thao tác bị từ chối.
6. Bổ sung cập nhật auditing column nếu schema yêu cầu.

### Bài 6: Phân biệt PATCH

Tạo request có ba tình huống:

- Không gửi description.
- Gửi description với chuỗi mới.
- Gửi description: null.

Thiết kế command/DTO để service phân biệt rõ giữ nguyên, thay giá trị và xóa giá trị. Sau đó tải aggregate đầy đủ và áp dụng thay đổi tương ứng.

## 16. Ghi nhớ

- Projection và DTO thường là read model; không dùng chúng làm aggregate persistence object.
- repository.save lưu trạng thái aggregate được truyền vào, không tự hiểu rằng thuộc tính thiếu trong DTO có nghĩa “giữ nguyên”.
- Aggregate thiếu scalar fields có thể mang null/default và ghi đè dữ liệu đã lưu.
- Collection được sở hữu không được tải nhưng bị khởi tạo rỗng có thể bị đồng bộ thành rỗng khi save.
- Cách an toàn phổ biến là load aggregate đầy đủ, áp dụng hành vi domain rồi save.
- Reduced aggregate-root mapping là kỹ thuật riêng để cập nhật có chọn lọc một số root fields; không đồng nhất nó với projection.
- Reduced mapping không nên áp dụng cho entity con trong aggregate vì child entities có thể bị xóa và tạo lại, khiến cột bị bỏ khỏi mapping nhận giá trị mặc định.
- Direct SQL/custom repository phù hợp với partial update có chủ đích nhưng phải tự quản lý optimistic locking, auditing, callbacks, events, validation và transaction.
- Version là metadata concurrency; không loại bỏ nó chỉ vì projection hoặc API response không cần hiển thị.
- Kiểm tra SQL và dữ liệu child sau save để xác nhận những phần ngoài phạm vi cập nhật vẫn được bảo toàn.

**Projection trả lời câu hỏi “cần đọc những gì”; aggregate trả lời câu hỏi “trạng thái domain hiện tại là gì”.** Hãy giữ hai vai trò đó tách biệt. Khi cần cập nhật một phần, diễn đạt rõ ý định qua command rồi chọn read-modify-save, reduced root mapping hoặc SQL tùy chỉnh có kiểm soát.

## Tài liệu tham khảo

- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational — Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html)
- [Spring Data JDBC — How Can I Do a Partial Update of an Aggregate Root?](https://spring.io/blog/2022/01/20/spring-data-jdbc-how-can-i-do-a-partial-update-of-an-aggregate-root/)

