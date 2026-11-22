# Projection động và phạm vi hỗ trợ của phương thức

Trong **Spring Data Relational JDBC**, projection cho phép repository trả về một góc nhìn dữ liệu thay vì luôn trả về toàn bộ aggregate root. Với projection tĩnh, kiểu kết quả được cố định trong chữ ký method. Với **dynamic projection (projection động)**, caller chọn kiểu kết quả ngay lúc gọi method, thường thông qua tham số `Class<T>`.

Ví dụ cùng một điều kiện tìm người theo họ có thể trả về:

- Aggregate `Person` đầy đủ khi caller truyền `Person.class`.
- Projection interface chỉ có tên khi caller truyền `PersonName.class`.
- DTO/record chứa một số trường khi caller truyền kiểu DTO tương ứng.

Khả năng này tiện lợi khi nhiều use case đọc cùng một tập dữ liệu nhưng cần các trường khác nhau. Tuy nhiên, dynamic projection không làm mọi method repository trở thành truy vấn tùy ý. Spring Data JDBC có các giới hạn riêng về query derivation, phương thức CRUD kế thừa, SQL khai báo bằng `@Query`, ánh xạ DTO và phân trang. Hiểu đúng phạm vi hỗ trợ giúp chọn chữ ký method phù hợp và tránh nhầm dynamic projection với cơ chế tạo SQL tùy ý.

## 1. Projection tĩnh và projection động

Một projection mô tả những thuộc tính mà phía đọc muốn nhận. Ví dụ aggregate:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("person")
public record Person(
        @Id Long id,
        String firstname,
        String lastname,
        String email,
        String status
) {}
```

Projection tĩnh:

```java
public interface PersonName {
    String getFirstname();
    String getLastname();
}
```

Repository có thể khai báo riêng một method trả projection:

```java
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    List<PersonName> findByLastname(String lastname);
}
```

Kiểu kết quả của method này luôn là `PersonName`. Nếu một màn hình khác cần cả email và status, bạn có thể tạo thêm projection và method tương ứng.

Với **dynamic projection**, method dùng một kiểu generic `T`:

```java
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    <T> List<T> findByLastname(String lastname, Class<T> projectionType);
}
```

Caller chọn kiểu kết quả:

```java
List<Person> people =
        repository.findByLastname("Nguyen", Person.class);

List<PersonName> names =
        repository.findByLastname("Nguyen", PersonName.class);
```

Cùng một query method và điều kiện lọc, nhưng kiểu kết quả thay đổi theo đối số `Class<T>`. Đây là điểm khác biệt chính: projection tĩnh chọn kiểu trong khai báo repository; projection động chọn kiểu tại thời điểm gọi.

## 2. Cấu trúc method dynamic projection

Mẫu tổng quát:

```java
<T> Collection<T> findBySomeProperty(
        PropertyType value,
        Class<T> projectionType
);
```

Các thành phần:

- `<T>` khai báo generic type cho method.
- `Collection<T>` hoặc `List<T>` là kiểu dữ liệu trả về theo projection được chọn.
- `Class<T>` cho Spring Data biết kiểu cần materialize.
- Các tham số trước `Class<T>` vẫn là điều kiện truy vấn thông thường.

Có thể dùng kiểu collection khác phù hợp với query, chẳng hạn `List<T>` hoặc `Collection<T>`. Nếu truy vấn chỉ trả tối đa một hàng, có thể dùng dạng kết quả đơn phù hợp với semantics của query; với truy vấn có thể trả nhiều hàng, collection giúp thể hiện rõ cardinality.

### 2.1. Ví dụ đầy đủ

Giả sử có hai projection:

```java
public interface PersonName {
    String getFirstname();
    String getLastname();
}

public interface PersonContact {
    Long getId();
    String getEmail();
}
```

Repository:

```java
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    <T> List<T> findByLastname(String lastname, Class<T> projectionType);
}
```

Service:

```java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PersonQueryService {

    private final PersonRepository repository;

    public PersonQueryService(PersonRepository repository) {
        this.repository = repository;
    }

    public List<PersonName> findNames(String lastname) {
        return repository.findByLastname(lastname, PersonName.class);
    }

    public List<PersonContact> findContacts(String lastname) {
        return repository.findByLastname(lastname, PersonContact.class);
    }

    public List<Person> findAggregates(String lastname) {
        return repository.findByLastname(lastname, Person.class);
    }
}
```

`PersonName.class` và `PersonContact.class` là các kiểu projection được yêu cầu. Khi truyền `Person.class`, method trả aggregate root theo kiểu thông thường. Dynamic projection không tự thay đổi điều kiện `WHERE lastname = ...`; nó quyết định hình dạng object kết quả.

## 3. Projection interface: proxy và property cần khớp

Với interface-based projection, Spring Data tạo proxy tại runtime và chuyển lời gọi accessor sang giá trị tương ứng trong đối tượng đích:

```java
public interface PersonSummary {
    Long getId();
    String getFirstname();
    String getLastname();
}
```

Các accessor nên khớp với persistent properties của aggregate root. Nếu property trong entity là `firstname`, accessor theo JavaBean convention là `getFirstname()`. Tên cột SQL vật lý có thể khác do `@Column` hoặc naming strategy; projection tham chiếu property của domain model.

Ví dụ entity dùng tên cột khác:

```java
@Table("person")
public record Person(
        @Id Long id,
        @Column("first_name") String firstname,
        @Column("last_name") String lastname,
        String email
) {}
```

Projection vẫn dùng `getFirstname()` và `getLastname()`, không cần đổi thành `getFirstNameColumn()` hay tên cột SQL.

### 3.1. Projection phải nằm ngoài type hierarchy của entity

Một kiểu được xem là projection khi nó nằm ngoài hệ phân cấp kiểu của entity. Nếu entity đã implement một interface, rồi repository trả interface đó, Spring Data có thể trả entity đã materialize đầy đủ thay vì tạo projection proxy.

Ví dụ không nên dùng để mong có projection:

```java
public interface PersonView {
    String getFirstname();
}

public class Person implements PersonView {
    // Entity implementation...
}
```

`PersonView` là interface mà `Person` đã implement, nên nó nằm trong type hierarchy của entity. Trả về `PersonView` không đồng nghĩa chỉ đọc một phần dữ liệu. Hãy khai báo một projection interface riêng mà entity không implement.

### 3.2. Closed projection

Một interface projection là **closed projection** khi mọi accessor tương ứng trực tiếp với property của aggregate:

```java
public interface PersonName {
    String getFirstname();
    String getLastname();
}
```

Vì framework biết chính xác các property được sử dụng, Spring Data có thể tối ưu việc truy vấn để chỉ lấy những trường cần thiết khi module và query type hỗ trợ. Với Spring Data JDBC, cần xác nhận SQL thực tế trong phiên bản đang chạy trước khi kết luận số cột đã được giảm.

### 3.3. Open projection

Projection interface có thể tính giá trị bằng `@Value` và SpEL:

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplay {
    @Value("#{target.firstname + ' ' + target.lastname}")
    String getDisplayName();
}
```

Đây là **open projection** vì biểu thức có thể truy cập nhiều thuộc tính của target. Spring Data không thể xác định tĩnh toàn bộ property cần thiết để tối ưu truy vấn như closed projection.

Với phép tính đơn giản, default method thường dễ đọc hơn:

```java
public interface PersonDisplay {
    String getFirstname();
    String getLastname();

    default String getDisplayName() {
        return getFirstname() + " " + getLastname();
    }
}
```

Default method chỉ nên dựa trên các accessor đã có trong projection. Logic nghiệp vụ phức tạp nên đặt ở service hoặc một Spring bean thay vì nhồi vào biểu thức SpEL.

## 4. Dynamic projection với DTO và record

Projection động cũng có thể chọn class-based DTO. Ví dụ record:

```java
public record PersonCard(
        Long id,
        String firstname,
        String email
) {}
```

Gọi:

```java
List<PersonCard> cards =
        repository.findByLastname("Nguyen", PersonCard.class);
```

Class-based projection không dùng proxy như interface projection. Spring Data tạo DTO thông qua constructor phù hợp với các input properties. Java record thường thuận tiện vì có một canonical constructor và tên component rõ ràng.

Nếu DTO class có nhiều constructor, Spring Data cần biết constructor nào được dùng. Có thể đánh dấu constructor mong muốn bằng `@PersistenceCreator`:

```java
import org.springframework.data.annotation.PersistenceCreator;

public class PersonCard {
    private final Long id;
    private final String firstname;

    protected PersonCard() {
        this.id = null;
        this.firstname = null;
    }

    @PersistenceCreator
    public PersonCard(Long id, String firstname) {
        this.id = id;
        this.firstname = firstname;
    }

    public Long getId() {
        return id;
    }

    public String getFirstname() {
        return firstname;
    }
}
```

DTO class-based không có nested projection theo cùng cách interface projection hỗ trợ. Nếu cần cấu trúc lồng nhau, có thể dùng interface projection lồng nhau hoặc tự ánh xạ query result sang DTO.

## 5. Tham số Class<T> được Spring Data nhận diện thế nào?

Spring Data kiểm tra tham số kiểu `Class` để xác định nó có phải dynamic projection parameter hay không. Khi generic type của `Class<T>` trùng với kiểu trả về thực tế của query, tham số đó được coi là **tham số chọn projection**, không phải giá trị query bình thường.

Ví dụ:

```java
<T> List<T> findByLastname(String lastname, Class<T> projectionType);
```

Trong chữ ký này, `projectionType` là thông tin điều khiển kiểu kết quả. Nó không được bind thành một giá trị SQL và cũng không có sẵn như một query parameter trong SpEL.

Nếu ứng dụng thực sự muốn truyền một đối tượng `Class` như **giá trị điều kiện truy vấn**, cần dùng kiểu generic khác, ví dụ `Class<?>`, để nó không bị nhận diện là dynamic projection parameter:

```java
List<Person> findByEntityClass(Class<?> entityClass);
```

Ví dụ này chỉ minh họa cách phân biệt generic signature; việc `Class<?>` có thể được bind thành giá trị SQL hay không còn phụ thuộc property, converter và kiểu dữ liệu của schema. Không phải mọi database đều có kiểu cột có thể lưu một Java Class object.

## 6. Phạm vi hỗ trợ của query method trong Spring Data JDBC

Dynamic projection là một tính năng của hệ thống repository/projection của Spring Data, nhưng **khả năng của từng loại query vẫn do Spring Data JDBC quyết định**.

### 6.1. Derived query chỉ hỗ trợ property trực tiếp của aggregate root

Spring Data JDBC có thể suy diễn truy vấn từ tên method:

```java
List<PersonName> findByLastname(String lastname);

<T> List<T> findByLastname(String lastname, Class<T> projectionType);
```

Tuy nhiên, query derivation trong Spring Data JDBC bị giới hạn ở các property đơn giản nằm trực tiếp trên aggregate root và chỉ hỗ trợ SELECT query theo cách này. Không thể mặc định viết property path xuyên qua quan hệ để Spring tự tạo JOIN như một số ORM.

Ví dụ nếu `Person` có property `address` và `Address` có `city`, đừng mặc định method:

```java
List<PersonName> findByAddressCity(String city);
```

sẽ tạo JOIN qua bảng địa chỉ. Derived query JDBC chỉ hỗ trợ các property có thể dùng trong WHERE mà không cần JOIN. Với nhu cầu truy vấn liên bảng, dùng SQL tường minh, view, query DAO hoặc mô hình đọc phù hợp.

### 6.2. Không biến method CRUD kế thừa thành projection bằng cách đổi return type

Các method nền tảng từ `CrudRepository` hoặc repository base interface có contract riêng. Nếu khai báo lại một method như `findAll()` với return type projection, lời gọi có thể vẫn được xử lý như base method, không phải một query method projection mới.

Ví dụ không nên:

```java
// Không dùng cách đổi return type của method CRUD để tạo projection.
List<PersonName> findAll();
```

Hãy đặt một query method có tên riêng:

```java
List<PersonName> findAllPersonNamesByStatus(String status);

<T> List<T> findByStatus(String status, Class<T> projectionType);
```

Tên method riêng giúp Spring Data nhận diện query method và tránh xung đột với method có sẵn của repository base interface. Một số store module có hỗ trợ biến method override thành query bằng `@Query`, nhưng phải kiểm tra rõ hỗ trợ của Spring Data JDBC và không áp dụng quy tắc của Spring Data JPA một cách máy móc.

### 6.3. @Query là SQL do ứng dụng kiểm soát

Spring Data JDBC cho phép khai báo SQL bằng `@Query`:

```java
@Query("""
    SELECT id, firstname, lastname
    FROM person
    WHERE lastname = :lastname
    """)
List<Person> findPeopleByLastname(@Param("lastname") String lastname);
```

SQL string-based query có các ràng buộc riêng:

- Query phải trả các cột phù hợp với mapping result type.
- Với entity, các cột được constructor sử dụng phải có mặt trong kết quả; các property được gán qua setter, wither hoặc field access có thể không bắt buộc nếu không có trong result.
- Spring Data JDBC dùng RowMapper mặc định để ánh xạ kết quả; có thể cấu hình custom `RowMapper` hoặc `ResultSetExtractor` khi cần kiểu kết quả khác.
- Spring Data JDBC hỗ trợ named parameter trong `@Query`.
- String-based query không hỗ trợ tự động áp dụng `Pageable`, `Sort`, `PageRequest` hoặc `Limit` như derived query; nếu cần giới hạn/sắp xếp, hãy viết chúng trong SQL và bind tham số thích hợp.

Do đó, khi dùng `@Query` cho DTO hoặc projection tùy chỉnh, hãy xác định rõ cách ánh xạ kết quả. Không giả định việc truyền `Class<T>` sẽ tự viết lại một SQL string tùy ý theo danh sách cột của DTO.

### 6.4. Custom RowMapper cho kiểu đọc riêng

Nếu SQL trả về cấu trúc không khớp entity, custom mapper cho phép ánh xạ rõ ràng:

```java
public record PersonCard(Long id, String firstname, String email) {}
```

```java
public class PersonCardRowMapper implements RowMapper<PersonCard> {

    @Override
    public PersonCard mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new PersonCard(
                rs.getLong("id"),
                rs.getString("firstname"),
                rs.getString("email")
        );
    }
}
```

Khai báo query method:

```java
@Query(
    value = """
        SELECT id, firstname, email
        FROM person
        WHERE lastname = :lastname
        """,
    rowMapperClass = PersonCardRowMapper.class
)
List<PersonCard> findCardsByLastname(@Param("lastname") String lastname);
```

Đây là một query đọc với kiểu kết quả cố định. Nó không tự động là dynamic projection; nếu cần chọn nhiều hình dạng DTO khác nhau, có thể tạo method riêng, dùng query DAO với mapper do ứng dụng chọn hoặc dùng derived dynamic projection trong phạm vi được hỗ trợ.

## 7. Dynamic projection có thể kết hợp với phân trang không?

Về mặt repository method, Spring Data có thể kết hợp projection với tham số phân trang cho các query method được module hỗ trợ. Ví dụ dạng derived query:

```java
<T> Page<T> findByLastname(
        String lastname,
        Pageable pageable,
        Class<T> projectionType
);
```

Caller:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.asc("firstname"), Sort.Order.asc("id"))
);

Page<PersonName> page = repository.findByLastname(
        "Nguyen",
        pageable,
        PersonName.class
);
```

`Page<T>` cung cấp tổng số phần tử và tổng số trang; để tạo metadata chính xác, framework có thể chạy thêm count query. Với `Slice<T>`, ứng dụng chỉ cần biết có trang tiếp theo hay không và có thể tránh yêu cầu tổng số trang. Cần xác nhận query method cụ thể và phiên bản Spring Data JDBC đang dùng hỗ trợ kiểu trả về này.

Lưu ý quan trọng: hạn chế của string-based `@Query` vẫn áp dụng. Không truyền `Pageable` vào một `@Query` dạng chuỗi rồi kỳ vọng Spring tự viết lại SQL để thêm offset, sort hoặc limit. Hãy khai báo cú pháp phân trang/sắp xếp trong SQL nếu dùng custom query.

## 8. Projection động không phải dynamic SQL

Hai khái niệm dễ bị nhầm:

| Khái niệm | Điều thay đổi | Ví dụ |
| --- | --- | --- |
| Dynamic projection | Kiểu Java dùng để biểu diễn kết quả | `Person.class` hoặc `PersonName.class` |
| Dynamic SQL | Cấu trúc câu SQL được tạo/thay đổi khi chạy | Chọn bảng, cột, JOIN hoặc điều kiện theo request |

Dynamic projection không cho phép caller truyền tên bảng hoặc một đoạn SQL tùy ý. Nó cũng không tự thêm JOIN để lấy dữ liệu từ aggregate khác.

Ví dụ:

```java
List<PersonName> names =
        repository.findByLastname("Nguyen", PersonName.class);
```

vẫn truy vấn theo điều kiện `lastname`. Nó chỉ thay đổi cách kết quả được biểu diễn. Nếu cần dữ liệu từ nhiều bảng hoặc một phép tổng hợp phức tạp, dùng custom query/DAO và ánh xạ DTO riêng.

## 9. Chọn projection phù hợp

| Tình huống | Cách phù hợp |
| --- | --- |
| Một use case luôn cần cùng vài property | Projection interface hoặc DTO tĩnh |
| Nhiều caller cần các góc nhìn khác nhau trên cùng derived query | Dynamic projection với `Class<T>` |
| Cần entity đầy đủ để thực hiện hành vi domain | Trả aggregate root |
| Cần JOIN, GROUP BY hoặc tính toán trên nhiều bảng | `@Query` với mapping tường minh hoặc `JdbcTemplate`/DAO |
| Cần truy vấn qua property lồng nhau đòi hỏi JOIN | Custom SQL/query DAO |
| Cần DTO có cấu trúc kết quả riêng và mapping đặc biệt | DTO + custom `RowMapper`/`ResultSetExtractor` |
| Cần phân trang với derived query | `Pageable`/`Page` hoặc `Slice` nếu method hỗ trợ |
| Cần phân trang với string-based `@Query` | Viết limit/offset/order trong SQL và bind tham số phù hợp |

Đừng dùng dynamic projection chỉ vì có thể. Nếu mỗi màn hình có yêu cầu rất khác nhau, các method riêng có tên rõ ràng đôi khi dễ hiểu và dễ tối ưu hơn một method generic có nhiều kiểu kết quả.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Trả về entity đầy đủ dù khai báo interface | Interface projection nằm trong type hierarchy của entity | Dùng interface projection riêng mà entity không implement |
| Không tìm thấy property projection | Accessor không khớp property Java | Đối chiếu tên property, getter và mapping metadata |
| `Class<T>` bị xem là tham số projection, không phải điều kiện | Generic type của Class trùng với return type | Dùng `Class<?>` hoặc generic type khác nếu thực sự là query argument |
| Đổi return type `findAll()` nhưng vẫn nhận entity | Method trùng base repository method | Tạo derived query method có tên riêng |
| Derived query báo không hỗ trợ property path | Query cần JOIN qua quan hệ | Dùng custom SQL/DAO; query derivation JDBC chỉ hỗ trợ property trực tiếp |
| DTO không tạo được | Constructor không phù hợp hoặc thiếu metadata property | Dùng một constructor rõ ràng hoặc `@PersistenceCreator` |
| Custom query thiếu dữ liệu khi map entity | SQL không trả các cột constructor cần | Bổ sung cột hoặc dùng DTO/custom RowMapper |
| `@Query` không áp dụng sort/page | String-based query không tự rewrite để thêm các tham số này | Viết ORDER BY/LIMIT/OFFSET trong SQL |
| Projection open không giảm số cột | SpEL có thể truy cập bất kỳ property nào | Dùng closed projection hoặc DTO với query chọn cột rõ |
| Mong dynamic projection tự JOIN bảng khác | Nhầm kiểu kết quả với cấu trúc SQL | Dùng query nhiều bảng và mapper riêng |

## 11. Quy trình triển khai dynamic projection

Khi thêm projection động vào repository:

1. Xác định aggregate root và các property đọc cần cung cấp.
2. Tạo interface/DTO projection nằm ngoài type hierarchy của entity.
3. Khai báo method generic có return type `T` và tham số `Class<T>`.
4. Đảm bảo điều kiện derived query chỉ dùng property mà Spring Data JDBC hỗ trợ.
5. Gọi method bằng entity class hoặc projection class cụ thể.
6. Nếu dùng DTO, bảo đảm constructor và tên input properties ánh xạ được.
7. Nếu dùng `@Query`, kiểm soát SQL, cột trả về và RowMapper; không mặc định dynamic projection tự thay đổi SQL.
8. Nếu cần pagination, kiểm tra method type/module hỗ trợ; với string-based SQL, tự viết giới hạn và thứ tự.
9. Quan sát SQL trong môi trường dev để xác nhận projection có thực sự giảm dữ liệu được đọc.

## 12. Bài tập thực hành

**Bài 1 — Hai kiểu kết quả.** Tạo `PersonName` và `PersonContact`. Khai báo `<T> List<T> findByLastname(String lastname, Class<T> type)`; gọi với hai projection và với `Person.class`.

**Bài 2 — Closed và open projection.** Tạo một closed projection chỉ có firstname/lastname, sau đó tạo open projection dùng `@Value` để ghép tên. Quan sát khác biệt về khả năng tối ưu truy vấn.

**Bài 3 — DTO động.** Tạo record `PersonCard` và truyền `PersonCard.class` vào method. Thử một DTO có nhiều constructor, rồi đánh dấu constructor phù hợp bằng `@PersistenceCreator`.

**Bài 4 — Type hierarchy.** Cho entity implement một interface có getter, thử trả interface đó rồi so sánh với một projection interface độc lập. Giải thích vì sao kiểu thứ nhất có thể trả entity đã materialize đầy đủ.

**Bài 5 — Class parameter.** So sánh chữ ký `Class<T>` với `Class<?>`. Quan sát tham số nào được Spring nhận diện là dynamic projection parameter và tham số nào còn có thể là query argument theo mapping phù hợp.

**Bài 6 — Giới hạn query.** Thử derived query dùng property trực tiếp và property lồng cần JOIN. Sau đó viết `@Query` với JOIN, custom RowMapper và DTO để so sánh hai đường truy vấn.

**Bài 7 — Phân trang.** Kết hợp dynamic projection với `Pageable` trên derived query được hỗ trợ. So sánh `Page` và `Slice`; sau đó thử custom string-based `@Query` và xác định phần ORDER BY/LIMIT/OFFSET phải do SQL đảm nhiệm.

### Tài liệu tham khảo

- [Spring Data Relational — Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html): interface, DTO và dynamic projections; quy tắc nhận diện `Class<T>`.
- [Spring Data Relational — JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): phạm vi query derivation, `@Query`, tham số phân trang và custom RowMapper.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): mapping và repository support của Spring Data JDBC.
