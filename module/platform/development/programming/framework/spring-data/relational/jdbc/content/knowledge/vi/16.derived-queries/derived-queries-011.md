# Nhận diện lỗi tên thuộc tính hoặc tên phương thức khi khởi động

Trong **Spring Data Relational JDBC**, Spring Data thường tạo truy vấn từ tên method của repository nếu method không khai báo SQL tường minh. Khi ứng dụng khởi động, framework phân tích tên method, tìm các property tương ứng trong domain type và tạo query. Một lỗi chính tả nhỏ như `findByFristName(...)` thay vì `findByFirstName(...)` có thể khiến repository không được khởi tạo và kéo theo lỗi khởi động ứng dụng.

Điều quan trọng là phân biệt ba lớp lỗi:

- **Tên method không phân tích được:** phần subject/predicate hoặc keyword không đúng cú pháp query derivation.
- **Property path không tồn tại:** method có cú pháp hợp lệ nhưng tham chiếu property không có trong entity.
- **SQL/schema hoặc kiểu tham số không đúng:** method được tạo nhưng truy vấn lỗi khi thực thi.

Hai nhóm đầu thường xuất hiện khi Spring tạo repository bean; nhóm cuối có thể chỉ xuất hiện khi gọi method. Bài này tập trung vào cách nhận diện và sửa lỗi tên method/property path trước khi ứng dụng chạy.

## 1. Spring Data phân tích tên repository method như thế nào?

Ví dụ repository:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCity(String status, String city);
}
```

Với method không có `@Query`, Spring Data có thể phân tích tên để xác định:

1. **Subject** — loại truy vấn hoặc giới hạn kết quả, ví dụ `find`, `read`, `get`, `count`, `exists`, `delete`, `Top`, `First`.
2. **Predicate** — điều kiện sau `By`, ví dụ `Email`, `StatusAndCity`.
3. **Property path** — tên property domain mà từng điều kiện tham chiếu.
4. **Operator/keyword** — phép so sánh, nối điều kiện hoặc sắp xếp, ví dụ `And`, `Or`, `Between`, `GreaterThan`, `OrderBy`.

```text
findTop10ByStatusAndCreatedAtAfterOrderByCreatedAtDesc
│    │    │    │      │            │
│    │    │    │      │            └─ sort: CreatedAt DESC
│    │    │    │      └─ operator: After
│    │    │    └─ property: createdAt
│    │    └─ property: status
│    └─ predicate bắt đầu sau By
└─ subject: find, giới hạn 10 kết quả
```

Ví dụ trên minh họa cách đọc tên method. Keyword được hỗ trợ cụ thể phụ thuộc module và phiên bản Spring Data; không phải mọi keyword của Spring Data JPA đều tự động có trong Spring Data JDBC.

Spring Data Commons sử dụng bộ phân tích query method (trong đó có `PartTree`) và metadata mapping để hiểu tên method. Khi repository được tạo, framework cần biết entity nào được truy vấn và property path nào được dùng để tạo SQL.

## 2. Lỗi property name: `No property ... found for type ...`

Đây là lỗi phổ biến nhất khi viết derived query. Giả sử entity có property `firstName`:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    private String email;
    private String status;
}
```

Method đúng:

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByFirstName(String firstName);
}
```

Method sai chính tả:

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByFristName(String firstName);
}
```

Khi Spring tạo repository, nó có thể báo lỗi dạng:

```text
BeanCreationException
  └─ QueryCreationException
       └─ PropertyReferenceException:
            No property 'fristName' found for type 'Customer'
```

Thông điệp chính là `No property 'fristName' found for type 'Customer'`. `BeanCreationException` thường chỉ là lớp bọc ở tầng Spring container; nguyên nhân gốc nằm trong `PropertyReferenceException`.

### Cách sửa

1. Mở entity được ghi trong thông báo (`Customer`).
2. Tìm tên property Java thật (`firstName`).
3. Sửa phần sau `By` thành `FirstName`.
4. Kiểm tra lại chữ hoa/chữ thường và ranh giới giữa các property.
5. Khởi động lại context hoặc chạy test khởi tạo repository.

Đừng sửa tên method theo tên cột SQL nếu property Java vẫn giữ tên khác.

## 3. `@Column` đổi tên cột SQL, không đổi tên property trong derived query

Đây là nguồn nhầm lẫn phổ biến:

```java
@Column("first_name")
private String firstName;
```

Có hai tên ở hai tầng:

| Tầng | Tên |
|---|---|
| Java domain property | `firstName` |
| SQL column | `first_name` |

Derived query tham chiếu **property Java**:

```java
findByFirstName(String firstName); // Đúng
```

Không viết:

```java
findByFirst_name(String firstName); // Sai: đây không phải property Java
```

Nếu dùng `@Query`, câu SQL lại dùng **tên bảng/cột**:

```java
@Query("SELECT * FROM customer WHERE first_name = :name")
List<Customer> findCustomersByFirstName(@Param("name") String name);
```

Tên method ở đây chủ yếu là tên Java API; SQL thực tế được khai báo trong annotation. Cần phân biệt rõ derived query và annotated query.

## 4. Tên method có đúng cú pháp nhưng property path vẫn sai

Một method có thể có subject và keyword hợp lệ nhưng tham chiếu property không tồn tại:

```java
List<Customer> findByStatusAndCreatedOnAfter(String status, Instant time);
```

Nếu entity chỉ có `createdAt`, không có `createdOn`, Spring Data không thể tạo property path. Hãy đối chiếu toàn bộ phần predicate với entity:

```java
private String status;
private Instant createdAt;
```

Method đúng:

```java
List<Customer> findByStatusAndCreatedAtAfter(String status, Instant time);
```

Một số ví dụ sai thường gặp:

| Method | Vấn đề có thể gặp | Cách sửa |
|---|---|---|
| `findByFirst_Name(...)` | Entity có `firstName`, không có `first` hoặc `name` theo đường dẫn parser hiểu | `findByFirstName(...)` |
| `findByCustomerName(...)` | Entity chỉ có `customer` hoặc `name`, không có property `customerName` | Dùng đúng property path hoặc query tường minh |
| `findByCreated(...)` | Entity có `createdAt`, không có `created` | `findByCreatedAt(...)` |
| `findByIsActive(...)` | JavaBeans property có thể được nhận diện là `active` nếu getter là `isActive()` | Kiểm tra property metadata; thường dùng `findByActive(...)` |
| `findByEamil(...)` | Đảo chữ trong `email` | `findByEmail(...)` |

Tên method phải phản ánh **property mà Spring Data nhìn thấy qua mapping metadata**, không chỉ tên field mà lập trình viên nhớ trong đầu. Với Lombok, record hoặc getter tùy biến, hãy kiểm tra cách property được expose và mapping constructor thực tế.

## 5. Nested property path và dấu gạch dưới để phân định

Một số domain model có object lồng nhau, chẳng hạn địa chỉ được embed trong customer:

```java
public class Address {
    private String city;
    private String postalCode;
}

@Table("customer")
public class Customer {
    @Id
    private Long id;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL)
    private Address address;
}
```

Khi query property lồng nhau, Spring Data Commons phân tích property path theo camel case. Có thể dùng dấu gạch dưới `_` để chỉ rõ ranh giới path trong trường hợp tên gây mơ hồ:

```java
List<Customer> findByAddress_City(String city);
```

`Address_City` diễn đạt rõ đường đi `address.city`. Khả năng tạo SQL cho nested path còn phụ thuộc kiểu mapping và khả năng query của Spring Data JDBC ở phiên bản đang dùng; đừng suy luận rằng mọi tham chiếu object đều tự tạo JOIN như ORM. Với query xuyên bảng hoặc quan hệ phức tạp, dùng `@Query` hoặc custom repository query và kiểm tra SQL.

### Trường hợp tên property mơ hồ

Giả sử entity có cả `addressZip` và object `address.zipCode`. Một tên method như `findByAddressZipCode(...)` có thể được parser thử phân tách theo property dài nhất, dẫn đến đường dẫn khác dự định. Dấu `_` giúp chỉ rõ ranh giới:

```java
findByAddress_ZipCode(String zipCode);
```

Nên ưu tiên tên property rõ ràng và dùng `_` khi cần phân định. Không dùng dấu gạch dưới tùy tiện nếu nó khiến tên Java method khó đọc.

## 6. Keyword và toán tử trong tên method

Một số keyword thường gặp trong derived query:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| So sánh bằng | `findByStatus`, `findByStatusIs` | `status = ?` |
| Khác | `findByStatusNot` | Khác giá trị |
| Kết hợp | `findByStatusAndCity`, `findByStatusOrCity` | `AND`, `OR` |
| Lớn/nhỏ | `findByAgeGreaterThan`, `findByAgeLessThanEqual` | So sánh số/ngày |
| Khoảng | `findByCreatedAtBetween` | Nằm trong khoảng |
| Null | `findByEmailIsNull`, `findByEmailIsNotNull` | Kiểm tra null |
| Chuỗi | `findByNameLike`, `findByNameStartingWith`, `findByNameContaining` | So khớp chuỗi |
| Tập giá trị | `findByStatusIn`, `findByStatusNotIn` | `IN` / `NOT IN` |
| Boolean | `findByActiveTrue`, `findByActiveFalse` | Giá trị boolean |
| Sắp xếp | `findByStatusOrderByCreatedAtDesc` | Thêm `ORDER BY` |
| Giới hạn | `findTop10ByStatus`, `findFirstByEmail` | Giới hạn số kết quả |

Ví dụ:

```java
List<Customer> findTop20ByStatusOrderByCreatedAtDesc(String status);

List<Customer> findByAgeGreaterThanEqualAndActiveTrue(int age);

List<Customer> findByEmailIsNotNullAndStatusIn(Collection<String> statuses);
```

Nếu keyword không được hỗ trợ hoặc đặt sai vị trí, lỗi có thể xuất hiện dưới dạng không phân tích được method hoặc query creation failure. Hãy tra danh sách keyword trong tài liệu **Spring Data Relational JDBC của đúng phiên bản**; không lấy danh sách keyword của JPA hoặc MongoDB áp vào JDBC.

## 7. Phân biệt lỗi property với lỗi reserved repository method

Một số method như `findById`, `existsById`, `deleteById` là method được kế thừa từ `CrudRepository`. Chúng là **reserved methods** và truy cập property được đánh dấu `@Id`, không nhất thiết property Java có tên `id`.

Ví dụ:

```java
@Table("customer")
public class Customer {

    @Id
    private Long customerKey;

    private String id; // mã nghiệp vụ, không phải @Id
}
```

```java
public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findById(Long value);       // tìm theo @Id customerKey
    Optional<Customer> findCustomerById(String id); // derived query theo property id
}
```

Phần `Customer` trong `findCustomerById` là phần mô tả subject; predicate `Id` tham chiếu property Java `id`. Nếu method chỉ đặt tên `findById`, nó trùng reserved method và được hiểu là tìm theo identifier. Đây là một ngoại lệ quan trọng khi entity có property nghiệp vụ tên `id` nhưng khóa chính có tên khác.

Khi cần query theo business property tên `id`, thêm một subject descriptor để method không trùng reserved signature, ví dụ `findCustomerById(...)`, và đảm bảo kiểu tham số khớp property đó.

## 8. Khi nào lỗi xuất hiện lúc khởi động?

Mặc định, Spring Data tạo repository proxy và xây dựng query method khi repository được khởi tạo. Nếu query derivation không tìm thấy property, quá trình tạo bean có thể thất bại trước khi ứng dụng sẵn sàng nhận request.

Một stack trace thường có nhiều lớp bọc:

```text
ApplicationContextException / BeanCreationException
  -> Error creating bean with name 'customerRepository'
     -> QueryCreationException
        -> PropertyReferenceException
           -> No property 'fristName' found for type 'Customer'
```

Đọc **exception sâu nhất có ý nghĩa**, thường là `PropertyReferenceException` hoặc nguyên nhân query creation cụ thể, thay vì chỉ đọc dòng `ApplicationContext failed to start`.

### Bootstrap mode có thể thay đổi thời điểm phát hiện

Spring Data repositories có các chế độ bootstrap khác nhau (eager/default, lazy hoặc deferred). Nếu repository được khởi tạo lười hoặc trì hoãn, lỗi có thể không xuất hiện trong giai đoạn startup ban đầu mà chỉ lộ ra khi bean/query được khởi tạo hoặc sử dụng lần đầu.

Vì vậy, “ứng dụng đã start” không chứng minh mọi derived query đều hợp lệ nếu dự án dùng lazy/deferred bootstrap. Một bài test chủ động nạp repository context sẽ giúp phát hiện lỗi sớm hơn.

## 9. Phân biệt lỗi khởi tạo query và lỗi khi thực thi SQL

Không phải mọi lỗi repository đều do tên property. Bảng sau giúp xác định giai đoạn lỗi:

| Giai đoạn | Ví dụ lỗi | Nguyên nhân cần kiểm tra |
|---|---|---|
| Parse tên method | `PropertyReferenceException` | Property không tồn tại, nested path sai |
| Tạo query | `QueryCreationException` | Keyword/method signature/query declaration không hợp lệ |
| Bind tham số | Lỗi kiểu hoặc số tham số | Kiểu Java không tương thích, named parameter không khớp |
| Thực thi SQL | `BadSqlGrammarException`, `DataAccessException` | Tên cột/bảng, dialect, SQL, schema |
| Đọc kết quả | Conversion/mapping exception | Kiểu cột, converter, nullability hoặc mapping constructor |
| Kết quả cardinality | `IncorrectResultSizeDataAccessException` | Method kỳ vọng một kết quả nhưng query trả nhiều hàng |

Ví dụ, property Java `firstName` được map sang cột `first_name`. Nếu method `findByFirstName(...)` được parse thành công nhưng database báo `column first_name does not exist`, đó là lỗi schema/SQL khi thực thi, không phải lỗi tên method.

Ngược lại, nếu `findByFristName(...)` báo `No property 'fristName' found`, database thậm chí chưa cần nhận câu SQL; query không được tạo thành công.

## 10. `@Query` khi tên method không đủ diễn đạt truy vấn

Derived query phù hợp với điều kiện đơn giản dựa trên property. Với JOIN, aggregation, subquery, vendor-specific SQL hoặc projection phức tạp, dùng `@Query`:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT c.*
        FROM customer c
        WHERE c.status = :status
          AND EXISTS (
              SELECT 1
              FROM purchase_order o
              WHERE o.customer_id = c.customer_key
          )
        """)
    List<Customer> findCustomersWithOrders(@Param("status") String status);
}
```

Trong SQL của `@Query`, dùng tên bảng và cột database (`customer_key`, `customer_id`), không dùng tên property Java (`customerKey`) trừ khi đó cũng là tên cột thật. Tên method có thể được đặt theo ý nghĩa use case; SQL trong annotation mới là nguồn tạo query.

`@Query` không phải cách chữa cho mọi lỗi property. Nếu truy vấn chỉ cần `findByFirstName`, sửa typo sẽ dễ bảo trì hơn. Chỉ chuyển sang SQL tường minh khi query thực sự cần kiểm soát cấu trúc hoặc hiệu năng.

## 11. Cách đọc và sửa stack trace theo từng bước

Khi ứng dụng không khởi động do repository, thực hiện theo trình tự:

1. **Tìm bean repository bị lỗi.** Ví dụ `customerRepository`.
2. **Tìm method được nhắc đến.** Ví dụ `findByFristName`.
3. **Tìm exception sâu nhất.** Nếu là `PropertyReferenceException`, ghi lại property không tìm thấy và domain type.
4. **Mở domain type đúng.** Kiểm tra property Java, getter, embedded type và `@Id`.
5. **Tách tên method thành các phần.** Subject, `By`, property path, operator, `And`/`Or`, `OrderBy`.
6. **Kiểm tra `@Column`.** Đảm bảo không nhầm tên SQL column với tên Java property.
7. **Kiểm tra reserved method.** `findById` có thể đang trỏ đến `@Id` chứ không phải business property `id`.
8. **Kiểm tra keyword theo Spring Data JDBC version.** Đừng áp dụng keyword từ module khác.
9. **Chạy test tạo repository context.** Xác nhận bean khởi tạo được trước khi chạy ứng dụng đầy đủ.
10. **Nếu query đã tạo nhưng runtime lỗi, chuyển sang kiểm tra SQL/schema/parameter.** Đừng tiếp tục đổi tên method khi lỗi nằm ở database.

### Ví dụ phân tích stack trace

Giả sử log có:

```text
Caused by: org.springframework.data.mapping.PropertyReferenceException:
No property 'createdOn' found for type 'Customer'
```

Entity:

```java
private Instant createdAt;
```

Repository:

```java
List<Customer> findByCreatedOnAfter(Instant time);
```

Sửa thành:

```java
List<Customer> findByCreatedAtAfter(Instant time);
```

Không cần thay schema, thêm converter hay đổi database; chỉ cần method trỏ đúng property đã tồn tại.

## 12. Kiểm thử lỗi query method ngay trong test

Một `@DataJdbcTest` có thể tạo repository slice và phát hiện lỗi query derivation khi Spring nạp context:

```java
@DataJdbcTest
class CustomerRepositoryContextTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void repositoryIsCreated() {
        assertThat(repository).isNotNull();
    }
}
```

Test này không cần gọi method để phát hiện lỗi parse nếu repository được bootstrap eager trong test context. Nếu dự án dùng lazy/deferred repository bootstrap, hãy gọi method trong test hoặc cấu hình test để khởi tạo repository sớm.

Với lỗi property path, không cần database có dữ liệu để tái hiện; query method có thể thất bại ngay lúc repository được tạo. Tuy nhiên, `@DataJdbcTest` vẫn cần cấu hình database và schema phù hợp để các test query thực thi.

Một test runtime kiểm tra derived query thực tế:

```java
@Test
void findsCustomerByFirstName() {
    jdbcTemplate.update(
            "INSERT INTO customer(id, first_name, email, status) VALUES (?, ?, ?, ?)",
            1L, "Lan", "lan@example.com", "ACTIVE"
    );

    List<Customer> customers = repository.findByFirstName("Lan");

    assertThat(customers).hasSize(1);
    assertThat(customers.get(0).getFirstName()).isEqualTo("Lan");
}
```

Ví dụ SQL cần điều chỉnh theo DDL thật và Java version của dự án. Mục tiêu là kiểm tra cả hai giai đoạn: repository method được tạo thành công và SQL trả đúng kết quả.

## 13. Các lỗi tên method/property thường gặp

| Tình huống | Thông báo hoặc kết quả | Nguyên nhân | Hướng xử lý |
|---|---|---|---|
| Gõ sai property | `No property 'fristName' found for type 'Customer'` | Typo trong predicate | Sửa theo tên property thật |
| Dùng tên cột SQL trong method | `No property 'first_name' found` | Nhầm `@Column` với Java property | Dùng `findByFirstName` |
| Sai nested path | `No property 'zip' found...` hoặc path không hợp lệ | Tên path bị parser chia sai | Kiểm tra từng segment; dùng `_` để phân định |
| Dùng `findById` cho business ID | Trả theo khóa chính `@Id` | Method trùng reserved CRUD signature | Đặt tên như `findCustomerById` |
| Keyword không hỗ trợ | Query creation/parsing error | Áp dụng keyword của module khác hoặc đặt sai cú pháp | Tra tài liệu Spring Data JDBC đúng version |
| Derived query tạo được nhưng SQL lỗi | SQL grammar/schema exception | Tên cột/bảng hoặc dialect sai | Kiểm tra DDL và SQL thực tế |
| Kỳ vọng một kết quả nhưng có nhiều row | `IncorrectResultSizeDataAccessException` lúc chạy | Return type đơn trong khi dữ liệu không unique | Dùng `List`, hoặc thêm unique constraint/điều kiện phù hợp |
| Ứng dụng start nhưng lần gọi đầu mới lỗi | Repository lazy/deferred bootstrap | Query chưa được khởi tạo trong startup | Eagerly test repository hoặc gọi method trong test |

## 14. Quy ước đặt tên giúp tránh lỗi

- Giữ tên method theo camel case và đúng Java property: `findByFirstName`, `findByCreatedAt`.
- Đặt tên property domain nhất quán, tránh nhiều alias gần giống như `created`, `createdOn`, `createdAt` nếu chúng có cùng ý nghĩa.
- Dùng `_` chỉ khi cần làm rõ ranh giới nested property path.
- Dùng `And`/`Or` để phân chia predicate rõ ràng; với điều kiện phức tạp, viết `@Query` thay vì tạo method name quá dài.
- Dùng tên subject dễ hiểu (`find`, `exists`, `count`, `delete`) và kiểm tra keyword của đúng module.
- Nhớ các method reserved từ `CrudRepository`, đặc biệt `findById`, `existsById`, `deleteById`.
- Khi đổi tên property Java, cập nhật derived query methods tương ứng; khi chỉ đổi tên cột SQL bằng `@Column`, derived method thường không cần đổi.
- Dùng context test để phát hiện lỗi query method trước khi đóng gói/deploy.

**Điểm cốt lõi:** derived query được xây dựng từ tên method và Java property path. Khi thấy `PropertyReferenceException`, hãy kiểm tra tên property và đường dẫn trong domain class trước tiên. `@Column` chỉ điều chỉnh tên cột SQL, còn method như `findById` có thể là reserved identifier method. Nếu repository đã khởi tạo thành công nhưng truy vấn lỗi lúc chạy, chuyển sang kiểm tra SQL, schema, parameter và kiểu dữ liệu.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): cách khai báo derived query, keyword và `@Query`.
- [Spring Data Commons — Query Method Details](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): subject, predicate, property expressions, nested path và reserved methods.
- [Spring Data Commons — Query Creation](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-methods.query-creation): query lookup và tạo query từ method name.
- [Spring Data Commons — `PropertyReferenceException` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PropertyReferenceException.html): lỗi property path không tồn tại.
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): ánh xạ domain property sang relational column.
