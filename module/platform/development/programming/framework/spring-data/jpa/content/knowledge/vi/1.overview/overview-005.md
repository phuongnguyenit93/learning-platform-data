# So sánh Spring Data JPA với JDBC, Spring Data JDBC và R2DBC

Tài liệu này phân biệt bốn cách làm việc với cơ sở dữ liệu quan hệ trong hệ sinh thái Java/Spring. Điểm cần nhớ là **JDBC, Spring JDBC, Spring Data JDBC, Spring Data JPA và R2DBC nằm ở các lớp trừu tượng khác nhau**. Chúng có thể cùng giải quyết bài toán đọc/ghi dữ liệu, nhưng khác nhau về cách ánh xạ đối tượng, quản lý trạng thái, viết SQL, giao dịch và mô hình I/O.

## 1. Làm rõ thuật ngữ

- **JDBC (Java Database Connectivity)** là API chuẩn của Java, chủ yếu nằm trong `java.sql` và `javax.sql`. Ứng dụng làm việc với `Connection`, `PreparedStatement`, `ResultSet` và JDBC driver. Các lời gọi JDBC thông thường là đồng bộ và có tính blocking: luồng gọi chờ thao tác cơ sở dữ liệu hoàn tất.
- **Spring JDBC** là lớp hỗ trợ của Spring trên JDBC, nổi bật với `JdbcTemplate`, `NamedParameterJdbcTemplate`, `RowMapper` và cơ chế chuyển lỗi JDBC sang hệ thống `DataAccessException`. Nó giảm mã lặp khi quản lý tài nguyên và ánh xạ kết quả, nhưng ứng dụng vẫn chủ động viết SQL và quyết định cách ánh xạ dữ liệu.
- **Spring Data JDBC** cung cấp mô hình repository và ánh xạ đối tượng trên JDBC. Nó giúp thao tác CRUD theo aggregate mà không triển khai đầy đủ mô hình ORM của JPA. I/O vẫn là JDBC blocking.
- **Spring Data JPA** cung cấp repository trên chuẩn Jakarta Persistence (JPA). Một JPA provider như Hibernate thực hiện ORM: ánh xạ entity, quản lý persistence context, theo dõi thay đổi và tạo SQL. Spring Data JPA không phải một JDBC driver; provider thường sử dụng JDBC ở tầng dưới.
- **R2DBC (Reactive Relational Database Connectivity)** là SPI riêng cho truy cập cơ sở dữ liệu quan hệ theo mô hình reactive và non-blocking. Spring Data R2DBC bổ sung mapping và repository reactive. R2DBC dùng `ConnectionFactory` và R2DBC driver, không dùng `DataSource`/JDBC driver theo cách của JDBC.

Vì vậy, khi nói “JDBC” cần xác định đang nói về API JDBC thuần hay Spring JDBC. Cả hai đều khác Spring Data JDBC. Tương tự, R2DBC không phải chế độ bất đồng bộ của JDBC; đây là một SPI và hệ driver riêng.

## 2. Luồng xử lý tổng quát

**Spring Data JPA**

`Service → JpaRepository → EntityManager → JPA provider (ví dụ Hibernate) → JDBC → JDBC driver → Database`

Repository giảm mã CRUD; EntityManager và provider quản lý entity, persistence context, quan hệ và việc đồng bộ thay đổi xuống cơ sở dữ liệu.

**Spring JDBC**

`Service → JdbcTemplate / NamedParameterJdbcTemplate → DataSource → JDBC driver → Database`

Ứng dụng viết SQL, cung cấp tham số và định nghĩa cách chuyển từng hàng kết quả thành đối tượng.

**Spring Data JDBC**

`Service → CrudRepository → Spring Data JDBC mapping/template → DataSource → JDBC driver → Database`

Repository cung cấp thao tác dữ liệu theo aggregate. Mapping đơn giản hơn JPA và không có persistence context theo dõi entity.

**Spring Data R2DBC**

`Service → ReactiveCrudRepository / R2dbcEntityTemplate → DatabaseClient → ConnectionFactory → R2DBC driver → Database`

Các thao tác trả về publisher reactive như `Mono` hoặc `Flux`; pipeline có thể điều phối I/O non-blocking và truyền backpressure.

## 3. Bảng so sánh nhanh

| Tiêu chí | JDBC thuần / Spring JDBC | Spring Data JDBC | Spring Data JPA | Spring Data R2DBC |
|---|---|---|---|---|
| API truy cập | `java.sql`, `JdbcTemplate` | JDBC | JPA qua provider, thường dùng JDBC bên dưới | R2DBC SPI |
| Mô hình I/O | Đồng bộ, blocking | Đồng bộ, blocking | Đồng bộ, blocking trong cách dùng thông thường | Reactive, non-blocking nếu driver hỗ trợ đúng |
| Cách viết truy vấn | SQL do ứng dụng viết | SQL hoặc query method phù hợp | JPQL, query method, Criteria/Specification, native SQL | SQL hoặc query method phù hợp |
| Ánh xạ | Tự viết `RowMapper` hoặc mapper tương đương | Mapping entity đơn giản | ORM phong phú | Mapping relational đơn giản |
| Quản lý trạng thái entity | Không | Không có persistence context/dirty checking như JPA | Có persistence context, identity map và dirty checking | Không có persistence context kiểu JPA |
| Quan hệ đối tượng | Tự JOIN và ánh xạ | Theo aggregate; quan hệ cần được thiết kế rõ | Hỗ trợ quan hệ entity phong phú | Thường truy vấn quan hệ tường minh; không có lazy proxy kiểu JPA |
| Lazy loading | Không tự có | Không | Có thể dùng tùy mapping/provider | Không có lazy loading kiểu JPA |
| Giao dịch | Spring transaction manager cho JDBC | JDBC transaction manager | JPA transaction manager | R2DBC transaction manager và reactive context |
| Repository | Tự tổ chức hoặc dùng DAO | Có | Có | Có reactive repository |
| Phù hợp khi | Cần kiểm soát SQL trực tiếp | Domain theo aggregate, CRUD rõ ràng | Domain có entity và quan hệ phong phú | Ứng dụng reactive end-to-end và driver phù hợp |

Bảng này mô tả cách sử dụng phổ biến trong Spring. Khả năng cụ thể còn phụ thuộc phiên bản framework, provider, driver và hệ quản trị cơ sở dữ liệu.

## 4. Khác biệt về mapping và quản lý trạng thái

### 4.1. Spring Data JPA: ORM và persistence context

JPA ánh xạ class thành entity và quan hệ giữa entity với bảng. Một entity được quản lý bởi persistence context có định danh ổn định trong phạm vi context đó. Khi cùng một hàng được tải nhiều lần trong cùng persistence context, JPA thường trả về cùng một instance được quản lý.

Khi thay đổi một entity đang được quản lý, provider có thể phát hiện thay đổi bằng **dirty checking** và tạo câu lệnh SQL khi flush hoặc commit. Do đó, trong một transaction, nhiều khi không cần gọi một lệnh update riêng cho từng thuộc tính đã đổi.

JPA hỗ trợ các quan hệ như `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany`, cascade, fetch strategy, inheritance mapping và lifecycle callback. Quan hệ có thể được tải eager hoặc lazy tùy cấu hình và mặc định của từng loại quan hệ. Lazy loading cần được dùng có chủ đích vì việc truy cập thuộc tính sau khi persistence context đóng có thể gây lỗi hoặc tạo truy vấn ngoài dự kiến.

Các tiện ích mạnh này đi kèm chi phí cần quản lý: trạng thái entity, thời điểm flush, số lượng câu SQL, kích thước persistence context và chiến lược tải quan hệ. JPA phù hợp khi mô hình domain thực sự cần các khả năng ORM đó.

### 4.2. Spring Data JDBC: aggregate-oriented mapping

Spring Data JDBC không cố tái tạo toàn bộ ORM của JPA. Mô hình trung tâm là **aggregate** và **aggregate root**:

- Aggregate root là điểm truy cập và lưu aggregate.
- Các đối tượng con thuộc cùng aggregate được lưu cùng ranh giới aggregate.
- Quan hệ tới aggregate khác thường được biểu diễn bằng định danh tham chiếu thay vì một object graph được tự động tải.
- Không có persistence context kiểu JPA, dirty checking hay lazy proxy tự động. Ứng dụng thay đổi đối tượng và gọi repository để lưu.

Cách tiếp cận này khuyến khích xác định ranh giới nhất quán của domain. Một aggregate quá lớn khiến mỗi lần lưu có thể kéo theo nhiều dữ liệu; vì vậy không nên gom mọi quan hệ vào một aggregate chỉ để tiện mapping.

Spring Data JDBC hỗ trợ mapping bằng các annotation của Spring Data Relational như `@Table`, `@Id` và `@MappedCollection`. Nó có thể dùng repository và query method, đồng thời cho phép viết SQL tường minh khi cần. Nó vẫn dùng JDBC nên không trở thành reactive chỉ vì có repository.

### 4.3. JDBC / Spring JDBC: SQL là trung tâm

Với JDBC thuần hoặc Spring JDBC, ứng dụng quyết định câu SQL, phép JOIN, thứ tự truy vấn và cách biến kết quả thành object. `JdbcTemplate` giúp đóng/mở tài nguyên an toàn, xử lý exception và truyền tham số; `RowMapper` chuyển từng hàng `ResultSet` thành đối tượng.

Cách này cho khả năng kiểm soát SQL rất cao, phù hợp với truy vấn báo cáo, truy vấn nhiều phép JOIN, stored procedure, thao tác bulk hoặc schema phức tạp. Đổi lại, ứng dụng tự chịu trách nhiệm tổ chức mapping, phân trang, quan hệ và các thao tác cập nhật.

Luôn truyền giá trị đầu vào qua tham số của `PreparedStatement`/template; không nối chuỗi đầu vào của người dùng trực tiếp vào SQL. Điều này giúp tránh SQL injection và cho phép driver xử lý kiểu dữ liệu đúng cách.

### 4.4. R2DBC: mapping đơn giản trong pipeline reactive

Spring Data R2DBC có thể ánh xạ hàng thành object và cung cấp repository, nhưng không có mô hình persistence context và dirty checking như JPA. Việc đọc các dữ liệu liên quan thường cần được thực hiện bằng truy vấn rõ ràng hoặc kết hợp các publisher trong service.

Reactive API giúp ứng dụng không phải giữ một thread chờ I/O trong lúc database xử lý, nếu driver và toàn bộ đường đi đều non-blocking. Publisher chỉ thực thi khi được subscribe; dữ liệu có thể được truyền theo luồng và chịu điều tiết bằng backpressure.

R2DBC không biến một truy vấn SQL thành truy vấn nhanh hơn. Lợi ích chính nằm ở khả năng sử dụng tài nguyên hiệu quả khi có nhiều thao tác I/O đồng thời. Nếu code gọi `block()`, dùng JDBC blocking hoặc gọi thư viện blocking trong pipeline, lợi ích non-blocking có thể bị mất.

## 5. Truy vấn và repository

### Spring Data JPA

- Có thể khai báo repository bằng `JpaRepository<Entity, IdType>`.
- Tên method có thể được dùng để suy ra truy vấn, ví dụ `findByEmail`.
- `@Query` mặc định thường dùng JPQL, truy vấn theo entity và thuộc tính entity; có thể dùng native SQL khi cần.
- Có thể dùng projection, Specification, Criteria API, entity graph và fetch join để kiểm soát dữ liệu cần tải.

### Spring Data JDBC

- Repository thường kế thừa `CrudRepository<AggregateRoot, IdType>`.
- Query method có thể đáp ứng truy vấn đơn giản.
- `@Query` dùng SQL, không phải JPQL.
- Khi truy vấn nhiều bảng hoặc cần projection đặc thù, hãy cân nhắc SQL rõ ràng và mapping kết quả phù hợp.

### Spring JDBC

Không bắt buộc dùng repository framework. DAO có thể gọi `JdbcTemplate.query`, `queryForObject`, `update` hoặc `batchUpdate`. `NamedParameterJdbcTemplate` cho phép đặt tên tham số thay vì dùng dấu `?` theo vị trí. Ứng dụng kiểm soát SQL trực tiếp và tự định nghĩa kết quả.

### Spring Data R2DBC

- Repository reactive thường kế thừa `ReactiveCrudRepository<Entity, IdType>`.
- Các method trả về kiểu reactive như `Mono<T>`, `Flux<T>` hoặc publisher tương ứng.
- `@Query` dùng SQL; không có JPQL và EntityManager như JPA.
- Có thể dùng `R2dbcEntityTemplate` hoặc `DatabaseClient` khi cần kiểm soát truy vấn chi tiết hơn repository.

## 6. Ví dụ code đại diện

Các đoạn dưới đây minh họa cách khai báo và truy vấn trong một ứng dụng Spring. Chúng là các mảnh code cần project Spring Boot/Spring phù hợp, dependency, cấu hình database và import tương ứng; không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`.

### 6.1. Spring Data JPA

Entity dùng annotation Jakarta Persistence:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
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

Repository có thể dùng query method:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
    Optional<Customer> findByName(String name);
}
```

Khi gọi `save`, Spring Data JPA chọn thao tác persist hoặc merge dựa trên cơ chế nhận diện entity mới. Với entity đang được quản lý, thay đổi thuộc tính có thể được ghi xuống database khi flush/commit nhờ dirty checking.

### 6.2. Spring JDBC

Dùng record làm kiểu kết quả và tự ánh xạ từng hàng:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.Optional;

public record CustomerRow(Long id, String name) {}

@Repository
public class CustomerJdbcQueries {
    private final JdbcTemplate jdbc;

    public CustomerJdbcQueries(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerRow> findById(long id) {
        return jdbc.query(
            "select id, name from customer where id = ?",
            (rs, rowNum) -> new CustomerRow(
                rs.getLong("id"),
                rs.getString("name")
            ),
            id
        ).stream().findFirst();
    }
}
```

SQL và mapping đều hiển thị ngay trong code. Với truy vấn phức tạp, có thể viết JOIN và tạo DTO chuyên biệt thay vì phải mô hình hóa mọi kết quả thành entity.

### 6.3. Spring Data JDBC

Dùng annotation của Spring Data Relational, không dùng annotation entity của JPA:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(@Id Long id, String name) {}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Ở đây `@Table` và `@Id` đến từ Spring Data Relational. Không có `@Entity`, `EntityManager` hoặc dirty checking. Với aggregate có đối tượng con, cần thiết kế rõ ranh giới aggregate và mapping collection.

### 6.4. Spring Data R2DBC

Entity relational có thể dùng annotation Spring Data Relational tương tự:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> findCustomer(Long id) {
        return repository.findById(id);
    }
}
```

Method trả về `Mono<Customer>`; kết quả được phát ra trong reactive pipeline khi có subscriber. Trong một ứng dụng reactive, hãy tiếp tục kết hợp publisher thay vì chặn luồng bằng `block()`.

## 7. Giao dịch và tính nhất quán

**JDBC và Spring Data JDBC:** giao dịch thường được quản lý bằng transaction manager gắn với `DataSource`, ví dụ `DataSourceTransactionManager` hoặc `JdbcTransactionManager`. `@Transactional` trên service giúp nhóm nhiều câu lệnh JDBC thành một giao dịch.

**Spring Data JPA:** thường dùng `JpaTransactionManager`. Transaction quản lý persistence context; thay đổi entity được đồng bộ khi flush hoặc commit. Cần hiểu propagation, isolation, flush và rollback để tránh giả định rằng mỗi lần gọi repository là một giao dịch độc lập.

**Spring Data R2DBC:** dùng `R2dbcTransactionManager` và reactive transaction context. Với phương thức reactive, transaction được gắn với pipeline và Reactor Context; nên trả về `Mono`/`Flux` từ phương thức transactional hoặc dùng reactive transaction operator. Không dựa vào ThreadLocal như cách hiểu đơn giản của code imperative.

Không nên mặc định JDBC và R2DBC cùng tham gia một transaction chỉ vì chúng kết nối tới cùng database. Chúng dùng API, connection và transaction manager khác nhau. Nếu một luồng nghiệp vụ trộn hai mô hình, cần thiết kế điều phối giao dịch rõ ràng và kiểm thử rollback thực tế.

## 8. Hiệu năng và các vấn đề thường gặp

### JPA

- Giảm đáng kể mã mapping và CRUD khi mô hình entity phù hợp.
- Có thể gặp N+1 query khi tải một danh sách entity rồi truy cập quan hệ lazy trong vòng lặp.
- Tải quá nhiều quan hệ eager hoặc dùng fetch join không phù hợp có thể làm kết quả phình to.
- Persistence context lớn, dirty checking trên nhiều entity và flush không đúng thời điểm có thể làm tăng chi phí.
- Cải thiện bằng projection, entity graph, fetch join có chủ đích, phân trang đúng cách, batch fetching và kiểm tra SQL thực tế.

### Spring JDBC

- SQL trực tiếp giúp dự đoán rõ truy vấn và tối ưu theo database.
- Ít tầng mapping hơn ORM, nhưng có thể tạo nhiều mã lặp nếu mỗi DAO tự quản lý mapping.
- Phải tự quản lý các trường hợp null, kiểu dữ liệu, mapping quan hệ, phân trang và cập nhật đồng bộ.
- Phù hợp với bulk update, truy vấn báo cáo và trường hợp cần khai thác tính năng riêng của database.

### Spring Data JDBC

- Mô hình đơn giản, ít hành vi ngầm hơn JPA và vẫn có repository.
- Hợp với aggregate có kích thước hợp lý và quy tắc nhất quán rõ.
- Không có lazy loading để tự tải object graph; service cần gọi repository/query phù hợp.
- Nếu aggregate quá lớn hoặc quan hệ chéo phức tạp, thao tác lưu và mô hình domain có thể trở nên nặng nề.

### Spring Data R2DBC

- Có thể phục vụ nhiều thao tác I/O đồng thời với số thread chờ ít hơn trong ứng dụng reactive đúng nghĩa.
- Không bảo đảm một câu SQL riêng lẻ chạy nhanh hơn JDBC; CPU, index, lock và kế hoạch truy vấn vẫn quyết định nhiều phần hiệu năng.
- Phụ thuộc chất lượng và tính năng của R2DBC driver cho database đang dùng.
- Cần tránh lời gọi blocking trong event loop; theo dõi connection pool, backpressure, timeout, retry và lỗi phát sinh bất đồng bộ.

Không có lựa chọn nào luôn nhanh nhất. Cần đo trên workload thật: độ phức tạp truy vấn, số kết nối đồng thời, kích thước dữ liệu, độ trễ database, driver và cách tổ chức transaction.

## 9. Chọn công nghệ theo bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Domain có entity và quan hệ phong phú, cần dirty checking/cascade/lazy loading | Spring Data JPA | ORM quản lý object graph và trạng thái entity |
| CRUD theo aggregate, muốn mapping đơn giản và ít hành vi ngầm | Spring Data JDBC | Repository có sẵn, mô hình aggregate rõ, không cần persistence context |
| SQL phức tạp, báo cáo, bulk operation hoặc cần kiểm soát từng câu truy vấn | Spring JDBC | SQL và mapping do ứng dụng kiểm soát trực tiếp |
| Ứng dụng reactive end-to-end, nhiều I/O đồng thời, database có R2DBC driver phù hợp | Spring Data R2DBC | API non-blocking và publisher reactive |
| Ứng dụng Spring MVC đồng bộ, nghiệp vụ thông thường, đội ngũ đã quen JPA | Spring Data JPA hoặc Spring JDBC | Chọn theo độ phức tạp domain và mức kiểm soát SQL cần thiết |
| Dự án chỉ cần CRUD đơn giản nhưng không cần ORM phong phú | Spring Data JDBC | Ít cơ chế hơn JPA nhưng vẫn có repository |

Một số quy tắc quyết định:

1. Bắt đầu từ mô hình domain. Nếu cần quản lý quan hệ entity, lifecycle, dirty checking và truy vấn theo object graph, JPA có lợi thế.
2. Nếu domain có aggregate rõ và muốn SQL/mapping dễ dự đoán, xem xét Spring Data JDBC.
3. Nếu truy vấn là phần trọng tâm, cần JOIN/bulk/reporting hoặc muốn tối ưu SQL cụ thể, Spring JDBC thường phù hợp.
4. Chỉ chọn R2DBC khi có nhu cầu reactive thực tế và driver hỗ trợ database cần dùng. Một tầng repository reactive đặt trong ứng dụng còn lại đều blocking thường không mang lại nhiều lợi ích.
5. Đừng chọn theo số dòng code của một ví dụ CRUD. Hãy đánh giá transaction, quan hệ, truy vấn, vận hành, driver, kỹ năng nhóm và khả năng kiểm thử.

## 10. Lỗi thiết kế và hiểu nhầm phổ biến

- **Coi Spring Data JDBC là JPA nhẹ hơn:** hai công nghệ có mô hình persistence khác nhau. Thiết kế aggregate của Spring Data JDBC không nên sao chép nguyên object graph JPA.
- **Nghĩ Spring Data JPA không dùng JDBC:** JPA provider thường dùng JDBC driver ở tầng truy cập database; JPA bổ sung lớp ORM và quản lý trạng thái.
- **Nhầm R2DBC với JDBC bất đồng bộ:** R2DBC có SPI và driver riêng, không dùng trực tiếp JDBC `DataSource` hoặc JDBC driver.
- **Cho rằng repository tự làm truy vấn luôn tối ưu:** query method tiện lợi nhưng vẫn cần kiểm tra SQL, index, số lượt truy cập và kế hoạch thực thi.
- **Bỏ qua N+1 trong JPA:** kiểm tra SQL thực tế và thiết kế fetch plan theo use case.
- **Truy cập lazy relation sau khi transaction/persistence context đóng:** xác định dữ liệu cần trả về ngay trong service và dùng projection/fetch plan phù hợp.
- **Gọi `block()` trong reactive pipeline:** thao tác này chặn luồng và có thể làm mất lợi ích của R2DBC/WebFlux.
- **Đưa thư viện blocking vào event loop:** JDBC, file I/O blocking hoặc HTTP client blocking cần được xử lý ở execution model phù hợp; không để chúng chặn luồng reactive.
- **Trộn annotation JPA với Spring Data Relational:** `jakarta.persistence.Entity`/`Id` dành cho JPA; Spring Data JDBC/R2DBC dùng annotation mapping của Spring Data Relational và `org.springframework.data.annotation.Id`.
- **Gộp quá nhiều dữ liệu vào một aggregate:** aggregate cần nhỏ đủ để duy trì quy tắc nhất quán và thao tác lưu hợp lý.
- **Giả định transaction manager tự phối hợp JDBC và R2DBC:** cần cấu hình và thiết kế rõ ràng; cùng một database không đồng nghĩa cùng một transaction context.

## 11. Checklist trước khi quyết định

- [ ] Ứng dụng đang dùng mô hình imperative hay reactive từ controller tới database?
- [ ] Database có driver JDBC/R2DBC phù hợp và đã được kiểm chứng cho các tính năng cần dùng?
- [ ] Domain cần ORM, lazy loading, cascade và dirty checking hay chỉ cần mapping đơn giản?
- [ ] Ranh giới aggregate và quy tắc nhất quán đã rõ chưa?
- [ ] Các truy vấn quan trọng cần JPQL, SQL tường minh, JOIN phức tạp hay bulk update?
- [ ] Transaction manager, propagation, isolation và rollback đã được xác định?
- [ ] Đã có kế hoạch kiểm tra N+1, connection pool, timeout, index và SQL thực tế?
- [ ] Đội ngũ có thể vận hành và debug mô hình persistence đã chọn?

## 12. Kết luận

- **Spring Data JPA** phù hợp khi cần ORM phong phú và quản lý trạng thái entity.
- **Spring Data JDBC** phù hợp khi muốn repository trên JDBC với mô hình aggregate đơn giản, rõ ràng.
- **Spring JDBC/JDBC thuần** phù hợp khi SQL và quyền kiểm soát truy vấn là ưu tiên.
- **Spring Data R2DBC** phù hợp khi cần truy cập relational database theo reactive/non-blocking và có driver hỗ trợ.

Hãy chọn dựa trên mô hình domain, truy vấn, giao dịch và kiến trúc I/O của toàn ứng dụng. Không nên chuyển sang reactive chỉ vì muốn “nhanh hơn”, cũng không nên dùng ORM đầy đủ nếu ứng dụng chỉ cần những thao tác SQL tường minh.
