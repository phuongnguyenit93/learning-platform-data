# Projection cho derived query, JPQL và native SQL trong Spring Data JPA

## Mục tiêu

Sau bài này, bạn có thể chọn kiểu projection phù hợp khi repository cần trả về một phần dữ liệu; khai báo interface projection và class/record DTO cho derived query; viết projection với JPQL `@Query`; ánh xạ kết quả native SQL bằng alias hoặc constructor mapping; sử dụng closed, open, nested và dynamic projection; đồng thời kiểm tra giới hạn, hiệu năng và tính tương thích của từng cách.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Jakarta Persistence (`jakarta.persistence.*`). Các đoạn code thuộc cùng một package minh họa; nếu dự án đã có entity hoặc repository tương ứng, hãy bổ sung projection và method vào cấu trúc hiện tại thay vì tạo các class trùng tên.

## 1. Projection là gì và dùng khi nào?

Một entity thường chứa nhiều thuộc tính và có thể có quan hệ tới nhiều entity khác. Nhưng một màn hình danh sách, báo cáo hoặc API thường chỉ cần vài trường. Nếu luôn tải entity đầy đủ, ứng dụng có thể lấy nhiều dữ liệu hơn cần thiết, kéo theo join, hydrate object và chi phí bộ nhớ không cần thiết.

**Projection** định nghĩa hình dạng dữ liệu mà truy vấn cần trả về. Thay vì trả `Customer` với toàn bộ trạng thái persistent, repository có thể trả `id`, `firstName`, `lastName` và `email` dưới dạng một view hoặc DTO.

Projection hữu ích khi:

- Hiển thị bảng danh sách hoặc thẻ tóm tắt chỉ cần vài trường.
- Trả dữ liệu đọc cho REST API mà không muốn expose entity.
- Tạo báo cáo, thống kê hoặc kết quả truy vấn tổng hợp.
- Giảm lượng dữ liệu cần chuyển từ database lên ứng dụng.
- Giữ hợp đồng dữ liệu của use case độc lập với entity persistence.

Projection không thay thế entity trong mọi trường hợp. Khi cần thay đổi trạng thái, dùng dirty checking, cascade hoặc điều hướng quan hệ trong domain, entity thường phù hợp hơn. DTO/projection chủ yếu phục vụ việc đọc dữ liệu theo một hình dạng cụ thể.

## 2. Mô hình ví dụ dùng xuyên suốt bài

Entity `Customer` có nhiều trường, trong khi danh sách tên khách hàng chỉ cần một phần:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String firstName, String lastName, String email, boolean active) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.active = active;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public String getEmail() { return email; }
    public boolean isActive() { return active; }
}
```

Giả sử bảng `customers` có các cột `id`, `first_name`, `last_name`, `email` và `active`. Tên thuộc tính Java là `firstName`, còn tên cột SQL là `first_name`; JPQL dùng tên thuộc tính, native SQL dùng tên cột.

## 3. Interface projection

Interface projection là cách khai báo đơn giản để mô tả các getter mà kết quả cần cung cấp. Spring Data JPA tạo proxy thực hiện interface đó khi truy vấn.

```java
package com.example.learning.customer;

public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
    String getEmail();
}
```

Repository có thể trả interface này từ một derived query:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerNameView> findByActiveTrueOrderByLastNameAscFirstNameAsc();
}
```

Tên method được phân tích như một derived query thông thường: lọc `active = true`, sắp xếp theo `lastName` rồi `firstName`. Kiểu trả về `CustomerNameView` yêu cầu Spring Data cung cấp các thuộc tính mà interface khai báo.

### 3.1. Closed projection

Closed projection chỉ khai báo các accessor tương ứng với thuộc tính của aggregate/entity:

```java
public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
}
```

Spring Data biết chính xác những property được yêu cầu và có thể tối ưu việc chọn dữ liệu cho truy vấn phù hợp. Mức tối ưu thực tế còn phụ thuộc query, provider, mapping và quan hệ được truy cập; hãy xem SQL được sinh ra nếu việc giảm cột là yêu cầu hiệu năng quan trọng.

Closed projection phù hợp cho các view nhỏ, có hình dạng ổn định. Khi thêm một getter, bạn đã thay đổi dữ liệu mà projection yêu cầu và có thể làm truy vấn cần thêm cột hoặc join.

### 3.2. Default method để ghép dữ liệu

Nếu cần tính một giá trị từ các accessor đã có, có thể dùng default method:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Default method không cần truy vấn thêm một cột `displayName`; nó tính từ các getter của projection. Cách này phù hợp với logic hiển thị đơn giản. Quy tắc nghiệp vụ phức tạp nên đặt trong service hoặc một component chuyên trách.

### 3.3. Open projection với @Value

Open projection dùng SpEL để tính giá trị từ target entity:

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerOpenView {
    Long getId();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Vì biểu thức có thể truy cập toàn bộ target, Spring Data không thể biết chắc chỉ cần những property nào. Open projection có thể khiến entity phải được tải đầy đủ, làm mất một phần lợi ích tối ưu cột của projection.

Chỉ dùng `@Value` khi thật sự cần biểu thức SpEL. Với phép ghép đơn giản, default method trên closed projection thường rõ ràng và dễ tối ưu hơn.

## 4. Nested projection cho quan hệ

Projection có thể khai báo một projection khác cho thuộc tính quan hệ. Ví dụ customer có quan hệ tới `Address`:

```java
public interface AddressView {
    String getCity();
    String getCountry();
}

public interface CustomerWithAddressView {
    Long getId();
    String getFirstName();
    AddressView getAddress();
}
```

Nested projection giúp API đọc có cấu trúc theo object graph. Tuy nhiên, không nên mặc định rằng nested projection chỉ tải đúng vài cột ở mọi cấp. Spring Data có thể cần join quan hệ và materialize phần nested property theo cách rộng hơn dự kiến.

Nếu nested view cần kiểm soát chính xác số cột, join, aggregation hoặc phân trang, hãy cân nhắc JPQL DTO constructor expression hoặc native query projection với select list rõ ràng. Kiểm tra SQL sinh ra để xác nhận truy vấn thực tế.

## 5. Class-based projection và DTO

Class-based projection trả một object DTO được tạo từ constructor thay vì proxy interface. DTO phù hợp khi muốn một kiểu dữ liệu cụ thể, có thể truyền qua service/API mà không phụ thuộc proxy.

Ví dụ dùng Java record:

```java
package com.example.learning.customer;

public record CustomerNameDto(
    Long id,
    String firstName,
    String lastName
) {
}
```

Record có canonical constructor và tên component rõ ràng. Có thể dùng class thông thường nếu cần thêm hành vi hoặc tương thích codebase chưa dùng record:

```java
public class CustomerNameDto {
    private final Long id;
    private final String firstName;
    private final String lastName;

    public CustomerNameDto(Long id, String firstName, String lastName) {
        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
}
```

Spring Data cần xác định constructor dùng để tạo DTO. Với class có nhiều constructor, hãy cung cấp một constructor phù hợp hoặc đánh dấu constructor mong muốn bằng `@PersistenceCreator`. Với record, canonical constructor thường làm lựa chọn này rõ ràng.

### 5.1. DTO từ derived query

Derived query có thể trả class-based projection nếu DTO có constructor phù hợp với các property mà Spring Data suy ra từ constructor parameter:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerNameDto> findByActiveTrueOrderByLastNameAscFirstNameAsc();
}
```

Đối với DTO class/record, tên constructor parameter cần tương ứng với property của entity để Spring Data xác định dữ liệu cần lấy. Nếu constructor có nhiều tham số hoặc tên không khớp, việc tạo projection có thể thất bại lúc khởi tạo query.

Class-based projection không hỗ trợ nested projection như interface projection. Nếu DTO cần cấu trúc lồng nhau, hãy viết query và mapping tường minh hoặc tạo các DTO ở tầng service.

## 6. Projection với JPQL @Query

JPQL truy vấn entity và thuộc tính Java. Với interface projection, có thể đặt alias cho từng biểu thức để khớp getter:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select c.id as id,
               c.firstName as firstName,
               c.lastName as lastName,
               c.email as email
        from Customer c
        where c.active = :active
        order by c.lastName asc, c.firstName asc
        """)
    List<CustomerNameView> findNameViewsByActive(
        @Param("active") boolean active
    );
}
```

Alias `id`, `firstName`, `lastName` và `email` khớp với accessor của `CustomerNameView`. JPQL dùng `Customer`, `firstName`, `lastName` là entity/property name; không dùng `customers` hoặc `first_name` trong biểu thức JPQL.

### 6.1. DTO constructor expression trong JPQL

Với class-based projection, JPQL dùng constructor expression `select new` và tên lớp đầy đủ:

```java
@Query("""
    select new com.example.learning.customer.CustomerNameDto(
        c.id, c.firstName, c.lastName
    )
    from Customer c
    where c.active = :active
    order by c.lastName asc, c.firstName asc
    """)
List<CustomerNameDto> findNameDtosByActive(
    @Param("active") boolean active
);
```

Thứ tự và kiểu các biểu thức phải khớp với constructor của `CustomerNameDto`. Tên lớp trong constructor expression phải là fully qualified class name; JPQL không dùng `new CustomerNameDto(...)` nếu không có tên đầy đủ.

Constructor expression là cách tường minh, dễ review và portable theo JPQL. Spring Data JPA có thể rewrite một số JPQL query để tạo constructor expression cho DTO, nhưng không nên dựa vào rewrite khi câu query đã có select expression phức tạp hoặc alias không phù hợp.

### 6.2. Tổng hợp và biểu thức tính toán

DTO projection đặc biệt hữu ích khi query trả kết quả tổng hợp không tương ứng với một entity:

```java
public record CustomerCountByActive(boolean active, Long total) {
}
```

```java
@Query("""
    select new com.example.learning.customer.CustomerCountByActive(
        c.active, count(c)
    )
    from Customer c
    group by c.active
    """)
List<CustomerCountByActive> countCustomersByActive();
```

Kết quả là các dòng tổng hợp theo trạng thái active. Đây là dữ liệu đọc, không phải entity managed. Không dùng DTO tổng hợp để gọi `save()` hoặc mong JPA tự đồng bộ nó về bảng.

## 7. Projection với native SQL

Native SQL dùng tên bảng và cột vật lý. Với interface projection, alias kết quả nên khớp với tên property của projection:

```java
@Query(
    value = """
        select c.id as id,
               c.first_name as firstName,
               c.last_name as lastName,
               c.email as email
        from customers c
        where c.active = ?1
        order by c.last_name, c.first_name
        """,
    nativeQuery = true
)
List<CustomerNameView> findNativeNameViewsByActive(boolean active);
```

Trong ví dụ, `?1` là positional parameter. Native SQL alias `firstName` cần được giữ đúng column label mà projection yêu cầu. Một số database tự chuyển identifier không quote về chữ thường hoặc chữ hoa; nếu alias bị biến đổi, hãy quote alias theo dialect (ví dụ PostgreSQL dùng dấu ngoặc kép) hoặc điều chỉnh alias/mapping. Luôn kiểm tra trên database thực tế.

Native query phù hợp khi cần SQL đặc thù, nhưng projection phụ thuộc chặt hơn vào tên cột, alias và kiểu dữ liệu trả về. Thay đổi schema có thể làm query hỏng dù entity property không đổi.

### 7.1. DTO từ native SQL

Class-based DTO có thể nhận kết quả native query trực tiếp khi số cột, thứ tự cột và kiểu dữ liệu trả về khớp với constructor của DTO:

```java
@Query(
    value = """
        select c.id, c.first_name, c.last_name
        from customers c
        where c.active = ?1
        order by c.last_name, c.first_name
        """,
    nativeQuery = true
)
List<CustomerNameDto> findNativeNameDtosByActive(boolean active);
```

Ở đây thứ tự select là `id`, `first_name`, `last_name`, tương ứng với constructor `CustomerNameDto(Long, String, String)`. Hãy kiểm tra kiểu JDBC mà database/provider trả về; một kiểu số hoặc timestamp có thể không khớp chính xác kiểu constructor mong đợi.

Nếu thứ tự cột, kiểu dữ liệu hoặc cấu trúc kết quả không khớp trực tiếp với DTO, hãy dùng mapping tường minh thay vì dựa vào conversion ngầm.

### 7.2. @SqlResultSetMapping cho kết quả phức tạp

Jakarta Persistence hỗ trợ `@SqlResultSetMapping` và `@ConstructorResult` để ánh xạ column label vào constructor DTO:

```java
import jakarta.persistence.ColumnResult;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerNameMapping",
    classes = @ConstructorResult(
        targetClass = CustomerNameDto.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "given_name", type = String.class),
            @ColumnResult(name = "family_name", type = String.class)
        }
    )
)
public class Customer {
    @Id
    private Long id;

    protected Customer() {
    }
}
```

Trên Spring Data JPA 3.4+, `@NativeQuery` có thuộc tính `sqlResultSetMapping` để tham chiếu mapping đã khai báo:

```java
import org.springframework.data.jpa.repository.NativeQuery;

@NativeQuery(
    value = """
        select c.id as customer_id,
               c.first_name as given_name,
               c.last_name as family_name
        from customers c
        where c.active = ?1
        """,
    sqlResultSetMapping = "CustomerNameMapping"
)
List<CustomerNameDto> findNativeDtosWithMapping(boolean active);
```

Column label trong SQL phải khớp `@ColumnResult`; thứ tự và kiểu phải phù hợp constructor. `@NativeQuery` được giới thiệu trong Spring Data JPA 3.4.0. Với phiên bản cũ hơn, có thể gọi `EntityManager.createNativeQuery(sql, "CustomerNameMapping")` trong custom repository hoặc dùng một cơ chế mapping tương thích.

## 8. Dynamic projection

Dynamic projection cho phép caller chọn kiểu kết quả tại thời điểm gọi method thay vì khai báo một method riêng cho mỗi projection:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    <T> List<T> findByActiveTrue(Class<T> projectionType);
}
```

Gọi cùng một repository method với nhiều kiểu:

```java
List<CustomerNameView> views =
    repository.findByActiveTrue(CustomerNameView.class);

List<CustomerNameDto> dtos =
    repository.findByActiveTrue(CustomerNameDto.class);

List<Customer> entities =
    repository.findByActiveTrue(Customer.class);
```

Spring Data nhận diện tham số `Class<T>` là lựa chọn projection khi kiểu generic của tham số phù hợp với kiểu trả về. Nếu dùng `Class<?>` hoặc kiểu không được nhận diện là dynamic projection, tham số có thể được xem là một tham số truy vấn thông thường.

Dynamic projection hữu ích khi cùng một điều kiện lọc phục vụ nhiều caller. Tuy nhiên, không nên tạo quá nhiều kiểu projection tùy tiện; mỗi projection vẫn là một hợp đồng dữ liệu cần được kiểm soát và kiểm thử.

## 9. So sánh projection theo loại query

| Cách truy vấn | Interface projection | Class/record DTO |
| --- | --- | --- |
| Derived query | Trả interface projection trực tiếp; getter xác định property cần thiết | Có thể trả DTO nếu constructor parameter khớp property entity |
| JPQL `@Query` | Select expression kèm alias khớp getter | Dùng `select new fully.qualified.Dto(...)` |
| Native SQL | Chọn cột và alias khớp accessor; kiểm tra cách database xử lý alias | Cột phải khớp thứ tự/kiểu constructor hoặc dùng `@SqlResultSetMapping` |

Không có một loại projection tối ưu cho mọi query. Interface projection tiện cho view nhỏ và nested accessor; DTO phù hợp với API contract, phép tính hoặc tổng hợp; native SQL DTO cần mapping cẩn thận hơn vì provider không có metadata JPQL để suy ra cấu trúc.

## 10. Projection có luôn nhanh hơn entity không?

Projection có thể giảm lượng dữ liệu được chọn và số object được tạo, nhưng không tự động bảo đảm truy vấn nhanh hơn. Hiệu quả phụ thuộc vào SQL thực tế:

- Closed interface projection và DTO constructor query có thể chỉ chọn các cột cần thiết.
- Open projection có SpEL truy cập target có thể cần tải entity đầy đủ.
- Nested projection có thể tạo join và tải thêm dữ liệu quan hệ.
- Một native query có thể chạy nhanh hoặc chậm tùy index, join, filter và execution plan.
- Nếu projection chỉ giảm vài cột nhưng truy vấn vẫn join nhiều bảng hoặc quét toàn bộ bảng, lợi ích có thể nhỏ.

Hãy kiểm tra SQL sinh ra, số hàng, số cột, số lần truy vấn và execution plan. Đo trên dữ liệu gần với production thay vì kết luận chỉ từ kiểu trả về Java.

### 10.1. Projection không phải cơ chế cập nhật entity

Interface projection hoặc DTO thường là dữ liệu đọc. Thay đổi một giá trị trên DTO không tự động cập nhật entity hoặc database. Nếu cần ghi:

1. Tải entity cần thay đổi trong transaction.
2. Áp dụng thay đổi qua method nghiệp vụ.
3. Commit transaction để JPA flush entity managed.

Với bulk update, dùng query ghi phù hợp và quản lý persistence context theo quy tắc riêng; projection không thay thế transaction hoặc dirty checking.

## 11. Integration test cho interface và DTO

Test dưới đây xác nhận derived query trả interface projection và DTO đúng dữ liệu. Nó giả định entity `Customer`, record `CustomerNameDto` và repository đã được khai báo như các ví dụ trên, đồng thời project có `spring-boot-starter-test`, `spring-boot-starter-data-jpa` và database kiểm thử như H2.

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerProjectionTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void returnsInterfaceAndDtoProjections() {
        customers.saveAll(List.of(
            new Customer("Ada", "Lovelace", "ada@example.test", true),
            new Customer("Grace", "Hopper", "grace@example.test", false)
        ));
        customers.flush();

        List<CustomerNameView> views =
            customers.findByActiveTrueOrderByLastNameAscFirstNameAsc();

        assertThat(views)
            .extracting(CustomerNameView::getEmail)
            .containsExactly("ada@example.test");

        List<CustomerNameDto> dtos = customers.findByActiveFalse();

        assertThat(dtos)
            .extracting(CustomerNameDto::email)
            .containsExactly("grace@example.test");
    }
}
```

Record accessor dùng tên component, vì vậy test gọi `CustomerNameDto::email`. Interface projection dùng getter method reference `CustomerNameView::getEmail`. `flush()` buộc các entity mới được đồng bộ xuống database trước khi repository query chạy.

Để kiểm thử JPQL/native projection, gọi thêm các repository method tương ứng và xác nhận từng field. Native query cần chạy trên database tương thích với cú pháp và alias mà query sử dụng; H2 không thay thế hoàn toàn kiểm thử trên PostgreSQL, MySQL, SQL Server hoặc Oracle.

## 12. Những lỗi thường gặp

- **Getter projection không khớp property.** Kiểm tra tên getter, JavaBeans property và alias trong query.
- **JPQL dùng tên cột SQL.** JPQL phải dùng entity/property; chỉ native SQL mới dùng tên bảng/cột vật lý.
- **JPQL DTO thiếu fully qualified class name.** Constructor expression cần tên lớp đầy đủ và thứ tự/kiểu tham số khớp constructor.
- **DTO có nhiều constructor không rõ lựa chọn.** Cung cấp constructor phù hợp hoặc đánh dấu bằng `@PersistenceCreator`.
- **Native interface projection alias bị đổi chữ hoa/thường.** Quote alias theo dialect và kiểm tra column label thực tế.
- **Native DTO select sai thứ tự hoặc kiểu cột.** Căn chỉnh select list với constructor hoặc dùng `@SqlResultSetMapping`.
- **Dùng open projection chỉ để ghép hai chuỗi.** Ưu tiên default method để giữ closed projection.
- **Giả định nested projection luôn chỉ tải đúng vài cột.** Kiểm tra join và SQL thực tế.
- **Dùng projection để cập nhật database.** Tải entity managed và cập nhật trong transaction.
- **Đưa entity trực tiếp ra API vì tiện.** Dùng DTO/projection để kiểm soát dữ liệu được expose và tránh phụ thuộc persistence model.
- **Không kiểm thử native SQL trên dialect thật.** Alias, kiểu dữ liệu và cú pháp có thể khác giữa các hệ quản trị.

## 13. Quy trình chọn projection

1. Xác định use case cần đọc những trường nào và có cần entity managed hay không.
2. Với derived query đơn giản, thử interface projection hoặc DTO constructor phù hợp.
3. Với JPQL, dùng alias khớp getter cho interface hoặc `select new` cho DTO.
4. Với native SQL, chọn cột vật lý rõ ràng; alias interface projection cẩn thận; kiểm tra thứ tự và kiểu constructor của DTO.
5. Dùng `@SqlResultSetMapping` khi native result set phức tạp hoặc không khớp trực tiếp constructor.
6. Dùng dynamic projection khi cùng một query thực sự cần nhiều hình dạng kết quả.
7. Kiểm tra SQL sinh ra, join, số cột, số hàng và execution plan.
8. Viết integration test cho cả dữ liệu bình thường, null, join và kết quả tổng hợp nếu có.

## 14. Bảng lựa chọn nhanh

| Nhu cầu | Lựa chọn gợi ý |
| --- | --- |
| Danh sách nhỏ, getter đơn giản | Closed interface projection |
| Ghép vài trường từ accessor hiện có | Closed projection với default method |
| Biểu thức SpEL phụ thuộc target entity | Open projection, dùng có chủ đích |
| Dữ liệu đọc cần kiểu cụ thể, bất biến | Record DTO |
| JPQL trả DTO hoặc kết quả tổng hợp | Constructor expression `select new` |
| Native SQL trả vài cột | Interface projection với alias chính xác |
| Native SQL trả DTO đơn giản | Constructor DTO khi thứ tự/kiểu cột khớp |
| Native SQL có mapping phức tạp | `@SqlResultSetMapping` hoặc custom repository |
| Cùng điều kiện lọc, nhiều hình dạng kết quả | Dynamic projection |

## Kết luận

Projection cho phép repository trả đúng hình dạng dữ liệu mà use case cần. Interface projection thuận tiện với getter và derived query; DTO/record cung cấp kiểu dữ liệu cụ thể; JPQL dùng alias hoặc constructor expression; native SQL cần alias và result mapping chính xác. Hãy chọn projection theo mục đích đọc, kiểm tra SQL thật và giữ entity cho các thao tác thay đổi trạng thái. Với native query, luôn xác nhận alias, thứ tự và kiểu cột trên database mục tiêu.