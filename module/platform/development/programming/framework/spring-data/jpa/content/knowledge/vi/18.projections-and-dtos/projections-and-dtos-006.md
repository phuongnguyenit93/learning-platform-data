# DTO theo constructor và lựa chọn constructor bằng @PersistenceCreator

## 1. DTO projection là gì?

Trong Spring Data JPA, projection cho phép repository trả về đúng phần dữ liệu mà một use case cần. Thay vì tải toàn bộ entity với mọi thuộc tính và quan hệ, ứng dụng có thể nhận một DTO chỉ chứa mã, tên, email hoặc một vài giá trị tổng hợp.

Class-based projection (DTO projection) sử dụng constructor để tạo object kết quả. JPA provider hoặc Spring Data lấy các giá trị từ query rồi truyền chúng vào constructor phù hợp. DTO thường là object chỉ đọc dùng để chuyển dữ liệu giữa repository, service và API; nó không trở thành entity được quản lý trong persistence context.

Ví dụ, màn hình danh sách khách hàng chỉ cần ID và tên:

- Entity Customer có thể chứa email, địa chỉ, trạng thái, quan hệ đơn hàng và nhiều thuộc tính khác.
- DTO CustomerSummary chỉ giữ ID và tên.
- Repository trả về CustomerSummary để giảm dữ liệu cần tải và làm rõ cấu trúc response.

Điểm cần phân biệt là constructor của DTO projection không phải constructor dùng để Hibernate tạo JPA entity. Entity có hợp đồng khởi tạo riêng theo Jakarta Persistence; DTO projection được tạo theo constructor được query hoặc Spring Data lựa chọn.

## 2. DTO class-based projection cơ bản

### 2.1. Tạo DTO có constructor phù hợp

Ví dụ DTO:

```java
package com.example.customer.dto;

public class CustomerSummary {

    private final Long id;
    private final String name;

    public CustomerSummary(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

DTO không cần annotation `@Entity`, `@Table` hoặc ID mapping. Nó chỉ cần constructor nhận các giá trị cần trả về và những accessor mà service/controller sử dụng.

Các field có thể là final để biểu đạt dữ liệu bất biến sau khi tạo. DTO không cần no-argument constructor theo hợp đồng JPA Entity. Constructor phải nhận đúng số lượng, thứ tự và kiểu dữ liệu mà cơ chế projection sử dụng.

### 2.2. Dùng DTO trong repository

Một derived query có thể trả về DTO:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(CustomerStatus status);
}
```

Spring Data JPA nhận diện kiểu trả về là DTO class-based projection và sử dụng constructor của DTO để tạo kết quả. Với derived query, tên tham số constructor được dùng để xác định các thuộc tính cần lấy từ entity. Vì vậy, tên tham số nên khớp với tên property Java của entity.

Ví dụ, nếu DTO có constructor `CustomerSummary(Long id, String name)`, các property `id` và `name` của Customer là những thuộc tính projection cần thiết.

### 2.3. Bật giữ tên tham số khi compile Java

Để Spring Data có thể khám phá tên tham số constructor trong class Java, nên biên dịch với tùy chọn `-parameters`.

Với Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Với Maven Compiler Plugin, cấu hình compiler argument tương ứng:

```xml
<configuration>
    <parameters>true</parameters>
</configuration>
```

Spring Boot và phiên bản build plugin có thể đã cấu hình một số tùy chọn mặc định, nhưng hãy xác nhận bytecode của dự án giữ parameter names nếu projection phụ thuộc vào chúng. Nếu tên tham số không được lưu, Spring Data có thể không xác định được property cần lấy như mong đợi.

Tên tham số constructor là tên property Java, không phải tên cột SQL. Nếu entity dùng `@Column(name = "customer_name")` cho field `name`, tham số DTO vẫn nên là `name` khi projection dựa trên property của entity.

## 3. Khi DTO có nhiều constructor: dùng @PersistenceCreator

### 3.1. Vấn đề constructor bị mơ hồ

Một DTO có thể có nhiều cách khởi tạo:

```java
public class CustomerSummary {

    private final Long id;
    private final String name;

    public CustomerSummary(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public CustomerSummary(Long id, String name, String prefix) {
        this(id, prefix + name);
    }

    // getters
}
```

Khi có nhiều constructor, Spring Data cần biết constructor nào là constructor tạo projection. Nếu không có constructor mặc định duy nhất hoặc quy tắc lựa chọn rõ ràng, việc tạo projection có thể thất bại vì không xác định được constructor phù hợp.

### 3.2. Đánh dấu constructor được chọn

Spring Data cung cấp annotation:

```java
import org.springframework.data.annotation.PersistenceCreator;
```

Đánh dấu constructor muốn Spring Data sử dụng:

```java
package com.example.customer.dto;

import org.springframework.data.annotation.PersistenceCreator;

public class CustomerSummary {

    private final Long id;
    private final String name;

    @PersistenceCreator
    public CustomerSummary(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public CustomerSummary(Long id, String name, String prefix) {
        this(id, prefix + name);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Trong trường hợp class có nhiều constructor, `@PersistenceCreator` chỉ rõ constructor được Spring Data ưu tiên khi cần tạo object theo cơ chế mapping của Spring Data. Constructor được chọn vẫn phải phù hợp với các property và giá trị mà projection cần.

### 3.3. Annotation thuộc Spring Data, không phải JPA

Cần import đúng:

```java
org.springframework.data.annotation.PersistenceCreator
```

Đây là annotation của Spring Data Commons. Nó không phải `jakarta.persistence.PersistenceContext`, không phải `@Entity` và không phải annotation chuẩn để yêu cầu Hibernate chọn constructor khởi tạo entity.

Phân biệt:

| Cơ chế | Mục đích |
|---|---|
| Constructor DTO projection | Tạo object kết quả từ các giá trị query |
| `@PersistenceCreator` | Chỉ định constructor hoặc factory method Spring Data nên dùng khi tạo object theo mapping của Spring Data |
| Constructor không tham số của Entity | Cho phép JPA provider tạo entity trước khi hydrate dữ liệu |
| JPQL `select new` | Gọi constructor có chữ ký khớp với các biểu thức trong constructor expression |

Không thêm `@PersistenceCreator` vào entity rồi kỳ vọng Hibernate sẽ dùng nó thay constructor không tham số theo hợp đồng JPA. Với DTO projection, annotation giúp Spring Data giải quyết lựa chọn constructor khi class có nhiều cách khởi tạo.

## 4. Quy tắc chọn constructor

Có thể áp dụng các quy tắc thực hành sau:

1. Nếu DTO chỉ có một constructor phù hợp, Spring Data thường có thể sử dụng constructor đó.
2. Nếu DTO có nhiều constructor, đánh dấu constructor mong muốn bằng `@PersistenceCreator`.
3. Constructor được chọn phải có tham số tương ứng với các property cần projection.
4. Giữ tên tham số rõ ràng và khớp tên property Java khi Spring Data cần suy ra input properties.
5. Nếu dùng record có canonical constructor duy nhất, thường không cần thêm annotation để chọn constructor.
6. Nếu dùng JPQL constructor expression, constructor được chọn theo số lượng, thứ tự và kiểu của các biểu thức trong `select new`; `@PersistenceCreator` không thay thế việc khớp chữ ký đó.

Spring Data cũng hỗ trợ factory method tĩnh được đánh dấu `@PersistenceCreator` trong các cơ chế object mapping. Tuy nhiên, JPQL `select new` là constructor expression của JPA và gọi constructor theo chữ ký trong query; không giả định provider sẽ gọi static factory method.

## 5. JPQL constructor expression với select new

### 5.1. Viết constructor expression tường minh

JPQL hỗ trợ tạo DTO bằng cú pháp `select new`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.name
        )
        from Customer c
        where c.status = :status
        order by c.name
        """)
    List<CustomerSummary> findSummariesByStatus(
        @Param("status") CustomerStatus status
    );
}
```

Các quy tắc cần nhớ:

- Dùng tên class DTO đầy đủ (fully qualified class name).
- Thứ tự biểu thức phải khớp thứ tự tham số constructor.
- Kiểu dữ liệu của biểu thức phải tương thích với kiểu tham số.
- DTO cần có constructor tương ứng.
- Không đặt alias cho từng biểu thức bên trong constructor expression.

Ví dụ `select new com.example.CustomerSummary(c.id as id, c.name as name)` không phải cú pháp JPQL constructor expression hợp lệ. Alias thường dùng cho tuple/interface projection; với `select new`, hãy liệt kê trực tiếp các biểu thức theo đúng thứ tự constructor.

### 5.2. @PersistenceCreator có vai trò gì trong select new?

Với query:

```sql
select new com.example.customer.dto.CustomerSummary(c.id, c.name)
from Customer c
```

JPA provider tìm constructor có hai tham số tương thích với kiểu của `c.id` và `c.name`. Việc phân giải constructor của JPQL dựa trên constructor expression và chữ ký Java.

`@PersistenceCreator` chủ yếu giúp Spring Data chọn constructor trong quá trình mapping DTO. Nó không làm cho một constructor không tương thích trở nên hợp lệ đối với JPQL `select new`. Khi viết constructor expression tường minh, hãy kiểm tra chữ ký constructor và thứ tự tham số trước tiên.

### 5.3. Query rewriting của Spring Data JPA

Trong một số trường hợp, Spring Data JPA có thể tự viết lại JPQL để dùng constructor expression khi method trả về DTO class-based projection. Ví dụ query ban đầu chọn entity root hoặc một danh sách biểu thức có thể được chuyển thành `select new ...`.

Tuy nhiên, việc rewrite phụ thuộc cấu trúc query và phiên bản Spring Data JPA. Nếu query đã có constructor expression, framework không cần viết lại. Với query phức tạp, hãy viết `select new` tường minh để thể hiện chính xác DTO cần tạo và kiểm thử trên phiên bản thực tế.

Không dùng alias không cần thiết trong danh sách biểu thức khi dự định để Spring Data rewrite thành constructor expression. Alias phù hợp với một số projection dạng tuple, nhưng không phù hợp bên trong cú pháp `select new`.

## 6. Dùng Java record làm DTO projection

Record là lựa chọn tự nhiên cho DTO bất biến:

```java
package com.example.customer.dto;

public record CustomerSummary(Long id, String name) {
}
```

Record có canonical constructor tương ứng với các record component. Với một canonical constructor duy nhất, Spring Data thường có thể xác định constructor mà không cần `@PersistenceCreator`.

Repository:

```java
List<CustomerSummary> findByStatus(CustomerStatus status);
```

Hoặc JPQL tường minh:

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummariesByStatus(
    @Param("status") CustomerStatus status
);
```

Record phù hợp khi DTO chỉ mang dữ liệu và không cần setter. Nó không phải entity JPA thông thường: record là final và có mô hình constructor canonical, trong khi entity có các yêu cầu riêng về constructor và khả năng proxy.

Nếu record có thêm constructor phụ, hãy giữ canonical constructor rõ ràng và kiểm tra cơ chế tạo projection của phiên bản Spring Data đang dùng. Đừng thêm annotation chỉ theo thói quen nếu record đã có một constructor duy nhất phù hợp.

## 7. DTO projection từ derived query và @Query

### 7.1. Derived query

Ví dụ:

```java
List<CustomerSummary> findByStatus(CustomerStatus status);
```

Spring Data dựa trên kiểu trả về và constructor DTO để tạo projection. Với class DTO có nhiều constructor, dùng `@PersistenceCreator` để chỉ rõ constructor. Tên tham số constructor được dùng để xác định property cần lấy trong class-based projection; giữ tên tham số và bật `-parameters` khi cần.

### 7.2. @Query với tự động rewrite

Có thể khai báo query chọn entity root:

```java
@Query("""
    select c
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummaries(
    @Param("status") CustomerStatus status
);
```

Spring Data JPA có thể rewrite query thành constructor projection khi xác định được DTO projection và cấu trúc query phù hợp. Hành vi này không nên được coi là bảo đảm cho mọi JPQL. Nếu muốn tránh phụ thuộc vào rewrite, viết constructor expression tường minh.

### 7.3. @Query với constructor expression

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummariesExplicitly(
    @Param("status") CustomerStatus status
);
```

Cách này thể hiện trực tiếp danh sách thuộc tính và constructor cần dùng. Nó đặc biệt hữu ích khi query có join, điều kiện phức tạp hoặc nhiều projection khác nhau.

## 8. Native query và constructor DTO

Native SQL không sử dụng cú pháp JPQL `select new`. Việc ánh xạ kết quả SQL sang DTO phụ thuộc thứ tự cột, kiểu JDBC và cơ chế mapping.

### 8.1. Mapping trực tiếp khi thứ tự và kiểu khớp

Với một số trường hợp, Spring Data JPA có thể tạo class-based projection từ native query nếu các cột được trả về theo đúng thứ tự và kiểu tương thích với constructor DTO.

Ví dụ DTO:

```java
public record CustomerSummary(Long id, String name) {
}
```

Native query minh họa:

```java
@Query(
    value = """
        select c.id, c.name
        from customer c
        where c.status = :status
        order by c.name
        """,
    nativeQuery = true
)
List<CustomerSummary> findNativeSummaries(
    @Param("status") String status
);
```

Cần xác nhận kiểu cột và thứ tự trả về thực tế. Ví dụ database có thể trả một kiểu số khác với kiểu Java dự kiến; chuyển đổi không tương thích có thể gây lỗi lúc ánh xạ.

### 8.2. Khi cần @SqlResultSetMapping

Nếu thứ tự cột, alias hoặc kiểu kết quả không khớp constructor DTO, có thể dùng `@SqlResultSetMapping` với `@ConstructorResult` và `@ColumnResult` theo Jakarta Persistence, hoặc custom repository để ánh xạ rõ ràng.

Ví dụ cấu trúc mapping:

```java
@SqlResultSetMapping(
    name = "CustomerSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerSummary.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class)
        }
    )
)
@Entity
@Table(name = "customer")
public class Customer {
    // Entity mapping và constructor JPA được khai báo tại đây.
}
```

Đây là ví dụ cấu trúc annotation; entity vẫn cần đầy đủ ID, constructor và mapping hợp lệ. Mapping này chỉ định cột kết quả nào được truyền vào constructor DTO. `@PersistenceCreator` không thay thế `@SqlResultSetMapping` và không giải quyết việc đổi tên hoặc chuyển đổi cột native SQL.

## 9. Các giới hạn và lỗi thường gặp

### 9.1. Không có constructor tương thích

Nếu JPQL yêu cầu `new CustomerSummary(Long, String)` nhưng DTO chỉ có constructor nhận `Customer`, provider không thể tạo projection. Hãy kiểm tra số lượng, thứ tự và kiểu tham số.

### 9.2. Có nhiều constructor nhưng không chỉ định constructor cho Spring Data

Với DTO class-based projection, nhiều constructor có thể khiến Spring Data không biết constructor nào là constructor mapping. Đánh dấu constructor phù hợp bằng `@PersistenceCreator` hoặc đơn giản hóa DTO để chỉ còn một constructor phù hợp.

### 9.3. Tên tham số không khớp property

Với derived class-based projection, Spring Data cần xác định property từ constructor parameter names. Nếu entity có `firstName` nhưng DTO đặt tham số là `name`, framework có thể không tìm được property như mong muốn. Đặt tên tham số khớp property Java và giữ metadata `-parameters`.

### 9.4. Nhầm tên cột với tên property

Derived projection dựa trên property của entity. Nếu cột database là `customer_name` nhưng property Java là `name`, constructor parameter thường cần là `name`. Với native query, alias/cột và kiểu kết quả lại phải khớp cơ chế native mapping.

### 9.5. Dùng primitive cho giá trị có thể null

Nếu cột có thể null, tránh constructor nhận primitive như `long` hoặc `int` cho giá trị đó. Dùng wrapper `Long`, `Integer` để biểu diễn null an toàn. Việc unbox null có thể gây NullPointerException.

### 9.6. DTO bị hiểu nhầm là Entity

DTO projection không được quản lý như entity. Thay đổi field trên DTO không được dirty checking và không tự persist xuống database. Nếu cần cập nhật dữ liệu, tải entity managed trong transaction hoặc dùng câu lệnh cập nhật phù hợp.

### 9.7. Lombok sinh thêm constructor

Các annotation như `@AllArgsConstructor`, `@NoArgsConstructor` hoặc `@Builder` có thể tạo thêm constructor và làm thay đổi cách Spring Data nhìn thấy DTO. Khi có nhiều constructor, hãy kiểm tra bytecode được sinh ra và gắn `@PersistenceCreator` lên constructor đúng nếu cơ chế mapping cần nó.

Không dùng `@Value` một cách máy móc cho entity JPA; class và field final của nó không phù hợp với entity thông thường. Với DTO, class bất biến là lựa chọn hợp lý nếu constructor projection được cấu hình đúng.

### 9.8. Constructor có side effect

Constructor DTO nên chỉ gán và chuẩn hóa dữ liệu đơn giản. Không gọi service, repository, mở transaction hoặc thực hiện I/O trong constructor. Provider/Spring Data có thể tạo nhiều DTO khi query trả nhiều hàng; side effect trong constructor khiến kết quả khó dự đoán và khó kiểm thử.

## 10. Chọn DTO projection hay interface projection?

| Tiêu chí | Class-based DTO | Interface projection |
|---|---|---|
| Cách tạo kết quả | Gọi constructor | Thường dùng proxy triển khai interface |
| Cấu trúc | Class hoặc record | Interface |
| Tính bất biến | Dễ thiết kế bất biến | Thường chỉ khai báo getter |
| Constructor | Cần constructor tương thích | Không cần constructor DTO |
| Chọn constructor | Có thể dùng @PersistenceCreator | Không áp dụng |
| JPQL tường minh | Dùng select new | Thường dùng tuple/alias |
| Logic biến đổi | Có thể đặt logic đơn giản trong DTO | Có thể dùng default method hoặc SpEL theo hỗ trợ |
| Phù hợp | API response/value object có cấu trúc rõ | Projection đơn giản theo getter |

Chọn class-based projection khi muốn kiểu trả về cụ thể, bất biến và có constructor rõ ràng. Chọn interface projection khi chỉ cần getter đơn giản và muốn Spring Data tạo proxy projection. Với logic nghiệp vụ hoặc mapping phức tạp, cân nhắc service mapper riêng thay vì làm DTO constructor quá nhiều việc.

## 11. Kiểm thử constructor projection

Một integration test nên xác nhận repository tạo đúng DTO và giá trị đúng thứ tự:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void mapsCustomerToConstructorProjection() {
        Customer customer = new Customer(
            "An",
            CustomerStatus.ACTIVE
        );
        entityManager.persist(customer);
        entityManager.flush();
        entityManager.clear();

        List<CustomerSummary> result =
            repository.findByStatus(CustomerStatus.ACTIVE);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName()).isEqualTo("An");
    }
}
```

Ví dụ giả định entity Customer có constructor và mapping phù hợp với hai thuộc tính được truyền vào. Nếu DTO là record, dùng accessor `name()` thay cho `getName()`. Test nên kiểm tra:

- Constructor được chọn đúng khi DTO có nhiều constructor.
- Parameter names khớp property với derived projection.
- JPQL constructor expression có đúng FQCN, thứ tự và kiểu tham số.
- Native query trả cột theo đúng mapping.
- Giá trị null được xử lý bằng kiểu wrapper.
- DTO không bị coi là managed entity.
- Query chỉ lấy các cột cần thiết khi projection cho phép.

Với native SQL và database-specific type, chạy integration test trên cùng loại database production. H2 có thể khác về kiểu dữ liệu và cách ánh xạ kết quả.

## 12. Checklist chọn và cấu hình constructor

- [ ] DTO là class/record dùng làm kết quả projection, không nhầm với entity.
- [ ] Constructor nhận đúng dữ liệu cần trả về.
- [ ] DTO chỉ có một constructor phù hợp hoặc constructor được chọn đã đánh dấu `@PersistenceCreator`.
- [ ] Import đúng `org.springframework.data.annotation.PersistenceCreator`.
- [ ] Tên tham số khớp property Java khi dùng derived class-based projection.
- [ ] Build giữ tên tham số bằng `-parameters` khi cần.
- [ ] JPQL `select new` dùng fully qualified class name.
- [ ] Thứ tự và kiểu biểu thức khớp constructor expression.
- [ ] Không đặt alias bên trong danh sách tham số của `select new`.
- [ ] Native query có thứ tự/kiểu cột tương thích hoặc mapping tường minh.
- [ ] Cột nullable dùng kiểu wrapper phù hợp.
- [ ] Constructor không chứa I/O hoặc side effect.
- [ ] Integration test bao phủ constructor selection và dữ liệu trả về.

## 13. Kết luận

Class-based DTO projection tạo object kết quả bằng constructor. Với một constructor phù hợp, Spring Data thường có thể sử dụng trực tiếp; khi DTO có nhiều constructor, `@PersistenceCreator` của Spring Data chỉ rõ constructor cần dùng cho cơ chế mapping của Spring Data. Tên tham số constructor cần khớp property Java khi Spring Data suy ra các thuộc tính projection từ DTO.

JPQL `select new` có quy tắc riêng: dùng tên class đầy đủ và constructor có số lượng, thứ tự, kiểu tham số khớp các biểu thức trong query. Provider phân giải constructor theo chữ ký JPQL; `@PersistenceCreator` không thay thế việc khớp chữ ký này. Record là lựa chọn gọn cho DTO bất biến có canonical constructor. Native query cần cột và kiểu dữ liệu tương thích hoặc mapping như `@SqlResultSetMapping`.

Hãy tách rõ DTO projection khỏi JPA Entity, chọn constructor tường minh khi có nhiều lựa chọn, giữ parameter names khi cần và kiểm thử trên provider/database thực tế.