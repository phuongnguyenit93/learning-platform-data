# Phân loại lỗi cấu hình, ánh xạ, truy vấn và dữ liệu trong Spring Data JPA

## 1. Vì sao cần phân loại lỗi?

Khi Spring Data JPA gặp lỗi, stack trace thường chứa nhiều lớp: service, repository proxy, Spring ORM, JPA provider (thường là Hibernate), JDBC driver và database. Exception xuất hiện ở đầu stack trace có thể chỉ là lớp bọc; nguyên nhân thật thường nằm trong **Caused by** sâu hơn hoặc trong SQLState/vendor error code của database.

Ví dụ:

- Ứng dụng không khởi động vì thiếu DataSource là lỗi cấu hình/kết nối.
- Hibernate không tạo được EntityManagerFactory vì hai entity ánh xạ trùng tên bảng là lỗi mapping.
- Repository không tạo được query do tên thuộc tính sai là lỗi định nghĩa truy vấn.
- INSERT thất bại vì vi phạm khóa ngoại là lỗi dữ liệu/ràng buộc.
- UPDATE không lưu được vì entity đã bị transaction khác sửa là lỗi đồng thời.

Phân loại đúng giúp chọn đúng nơi cần kiểm tra. Sửa cấu hình khi lỗi nằm ở dữ liệu chỉ làm tăng độ phức tạp; sửa query khi lỗi do schema sai cũng không giải quyết được gốc rễ.

Bốn nhóm chính trong bài:

1. **Lỗi cấu hình và kết nối**: Spring context, datasource, transaction manager, dialect, migration và quyền truy cập.
2. **Lỗi ánh xạ**: entity, field, quan hệ, kiểu dữ liệu Java/SQL và schema.
3. **Lỗi truy vấn**: derived query, JPQL, native SQL, tham số, projection, phân trang và thực thi.
4. **Lỗi dữ liệu**: null, constraint, conversion, dữ liệu không duy nhất, trạng thái entity và concurrency.

Các exception cụ thể có thể khác theo phiên bản Spring Boot, Spring Data, Hibernate, JPA provider và JDBC driver. Hãy đọc exception thực tế và cause chain thay vì kết luận chỉ từ tên lớp.

## 2. Quy trình chẩn đoán chung

Khi gặp lỗi, đi theo thứ tự sau:

1. **Xác định thời điểm**: lỗi xảy ra lúc khởi động context, lúc tạo repository, khi gọi method, khi flush hay khi commit transaction?
2. **Tìm exception gốc**: đọc toàn bộ Caused by, không dừng ở DataAccessException hoặc JpaSystemException đầu tiên.
3. **Lấy câu SQL và tham số**: xác định câu lệnh nào thất bại, bảng/cột nào liên quan và tham số nào gây lỗi. Không ghi dữ liệu nhạy cảm vào log.
4. **Đối chiếu mapping và schema**: entity, migration, tên schema/table/column, kiểu dữ liệu và constraint có đồng bộ không?
5. **Tái hiện tối thiểu**: tạo test nhỏ với cùng DBMS, cùng migration và cùng JDBC driver.
6. **Sửa nguyên nhân**: thay đổi đúng cấu hình, mapping, query hoặc dữ liệu.
7. **Kiểm thử lại**: xác nhận cả trường hợp thành công, dữ liệu biên và rollback nếu có transaction.

### Đọc stack trace theo lớp

| Lớp exception thường thấy | Ý nghĩa ban đầu | Cần truy tiếp |
|---|---|---|
| BeanCreationException | Một bean không tạo được | Caused by sâu nhất và bean đang khởi tạo |
| UnsatisfiedDependencyException | Không inject được dependency | Bean/type/qualifier bị thiếu hoặc lỗi khi tạo |
| PersistenceException / JpaSystemException | JPA provider gặp lỗi | Hibernate cause, JDBC exception và SQL |
| DataAccessException | Spring đã dịch lỗi truy cập dữ liệu | Exception gốc, SQLState và vendor code |
| QueryCreationException | Repository query không tạo được | Tên property, JPQL, named query hoặc tham số |
| DataIntegrityViolationException | Dữ liệu vi phạm constraint | Constraint name, bảng/cột và giá trị liên quan |
| TransactionSystemException | Lỗi ở ranh giới transaction | Lỗi flush/commit và rollback exception |
| OptimisticLockingFailureException | Cập nhật đồng thời không còn hợp lệ | Version, số hàng cập nhật và transaction cạnh tranh |

Spring thường dịch exception của persistence provider/JDBC thành hệ exception thống nhất trong package **org.springframework.dao**. Tên exception ngoài cùng không nhất thiết là tên lỗi mà database trả về.

## 3. Nhóm lỗi cấu hình và kết nối

### 3.1 Thiếu hoặc cấu hình sai DataSource

Dấu hiệu thường gặp:

- Không có bean DataSource hoặc không tìm thấy JDBC URL.
- Không kết nối được database: connection refused, timeout, authentication failed.
- Pool khởi tạo được nhưng không lấy được connection khi truy vấn.
- Test vô tình kết nối database khác với database dự kiến.

Nguyên nhân thường gặp:

- Thiếu JDBC driver trong classpath.
- Sai host, port, database name, username hoặc password.
- Database chưa chạy, DNS/firewall/network không cho phép kết nối.
- Profile Spring không được kích hoạt hoặc biến môi trường chưa được truyền vào.
- Driver và DBMS không tương thích.
- Pool cạn do connection không được giải phóng, truy vấn lâu hoặc transaction giữ connection quá lâu.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: app_user
    password: \${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  jpa:
    hibernate:
      ddl-auto: validate
```

Đây là cấu hình minh họa cho PostgreSQL; thay URL, driver và biến môi trường theo DBMS thực tế. Không lưu password thật trong source control. Khi dùng HikariCP, kiểm tra log khởi tạo pool và thông tin connection timeout; không tăng pool size ngay khi chưa xác định connection đang bị giữ bởi transaction hay truy vấn chậm.

### 3.2 Không tìm thấy transaction manager hoặc EntityManagerFactory

Dấu hiệu:

- NoSuchBeanDefinitionException cho PlatformTransactionManager hoặc EntityManagerFactory.
- Bean repository không được tạo.
- Ứng dụng có nhiều DataSource nhưng repository sử dụng nhầm transaction manager.
- Một phần thao tác không tham gia transaction dự kiến.

Cần kiểm tra:

- Dependency Spring Data JPA và JDBC driver có đúng scope không.
- Package repository/entity có nằm trong vùng scan không.
- Có nhiều cấu hình datasource và mỗi nhóm repository đã gắn đúng entityManagerFactoryRef/transactionManagerRef chưa.
- Transaction manager có quản lý đúng EntityManagerFactory không.
- Có khai báo cấu hình tùy chỉnh vô tình làm mất auto-configuration cần thiết không.

Với một datasource đơn giản, Spring Boot thường tự cấu hình JpaTransactionManager. Với nhiều datasource, cần cấu hình tường minh từng EntityManagerFactory, transaction manager và repository package. Không dùng transaction manager của datasource A cho EntityManagerFactory của datasource B.

### 3.3 Lỗi dialect, schema và migration

Dấu hiệu:

- Hibernate không xác định được dialect.
- Schema-validation báo thiếu bảng/cột hoặc sai kiểu.
- Repository khởi tạo thành công nhưng query thất bại vì procedure/table chưa được tạo.
- Migration thất bại do cú pháp không phù hợp DBMS.

Cách xử lý:

- Kiểm tra DBMS thực tế và JDBC metadata.
- Đảm bảo JDBC URL/driver đúng; Hibernate thường có thể suy ra dialect từ metadata.
- Chỉ khai báo hibernate.dialect khi thật sự cần hoặc khi môi trường không thể đọc metadata; chọn dialect tương thích Hibernate đang dùng.
- Kiểm tra Flyway/Liquibase có chạy đúng database/schema và đúng thứ tự không.
- Dùng ddl-auto=validate để phát hiện lệch mapping/schema khi khởi động; không coi validate là công cụ tạo hoặc sửa schema.
- Đối chiếu DDL migration đã triển khai, không chỉ dựa vào entity annotation.

Các giá trị ddl-auto thường gặp:

| Giá trị | Hành vi | Cách dùng |
|---|---|---|
| none | Không quản lý schema | Migration chịu trách nhiệm |
| validate | Kiểm tra mapping với schema | Hữu ích cho môi trường kiểm soát migration |
| update | Hibernate cố cập nhật schema | Tránh dựa vào đây cho migration production |
| create | Tạo schema khi khởi tạo | Chủ yếu cho môi trường thử nghiệm |
| create-drop | Tạo schema và xóa khi context đóng | Test/demo có dữ liệu tạm |

Không dùng create hoặc create-drop với database có dữ liệu cần giữ. Với ứng dụng có migration, thường chọn validate hoặc none theo quy trình triển khai.

### 3.4 Quyền và cấu hình runtime

Một ứng dụng có thể kết nối thành công nhưng vẫn không đọc/ghi được vì user thiếu quyền. Kiểm tra quyền SELECT, INSERT, UPDATE, DELETE, EXECUTE, quyền sequence và quyền trên schema theo đúng thao tác. Chạy test bằng tài khoản giống ứng dụng; không chạy mọi test bằng database owner rồi kết luận quyền production đã đúng.

Các thiết lập như default schema, search_path, case sensitivity, timezone, collation và SQL mode cũng ảnh hưởng kết quả. Hãy xác minh chúng trong môi trường test và production khi query phụ thuộc vào các thiết lập này.

## 4. Nhóm lỗi ánh xạ entity và schema

### 4.1 Entity không hợp lệ hoặc mapping không nhất quán

Dấu hiệu:

- AnnotationException, MappingException hoặc lỗi tạo SessionFactory/EntityManagerFactory.
- Hibernate không tìm thấy identifier.
- Hai entity ánh xạ trùng table/column theo cách không hợp lệ.
- Field không được ánh xạ như mong đợi hoặc không thể khởi tạo entity.

Các nguyên nhân phổ biến:

- Entity không có @Id hoặc @EmbeddedId.
- Lớp entity không đáp ứng yêu cầu constructor/access của JPA.
- Quan hệ tham chiếu sai kiểu hoặc thiếu target entity.
- Dùng sai annotation giữa jakarta.persistence và javax.persistence.
- Dùng @Column cho tên cột khác với schema thực tế.
- Kế thừa entity/mapped superclass được cấu hình không đúng.
- Kiểu Java không tương thích kiểu SQL.

Ví dụ mapping cơ bản:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer", schema = "app")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true, length = 180)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Đoạn code minh họa cho Jakarta Persistence; cần có bảng app.customer tương ứng trong migration. Entity cần identifier; constructor không tham số có thể là protected. Các thuộc tính name, schema, nullable, unique và length phải khớp ý định thiết kế và DDL thật.

### 4.2 Sai tên bảng hoặc cột

Dấu hiệu:

- SQLGrammarException hoặc BadSqlGrammarException.
- Database báo relation/table/column does not exist hoặc invalid identifier.
- Chỉ một query lỗi dù các query khác vẫn chạy.

Cách kiểm tra:

1. Lấy SQL do Hibernate phát ra.
2. Đối chiếu tên bảng/cột với migration trên đúng schema.
3. Kiểm tra naming strategy có chuyển camelCase thành snake_case không.
4. Kiểm tra quote/case sensitivity và tên reserved keyword.
5. Xác nhận datasource đang kết nối đúng database.

Ví dụ entity dùng @Column(name = "created_at") nhưng migration tạo createdAt. Hibernate sẽ truy cập tên theo mapping và database có thể không tìm thấy cột. Sửa mapping hoặc migration theo một quy ước thống nhất; không đổi tên tùy tiện nếu dữ liệu hiện tại cần được bảo toàn.

### 4.3 Quan hệ và khóa ngoại

Các lỗi thường gặp:

- @ManyToOne hoặc @OneToOne tham chiếu cột join sai.
- Quan hệ hai chiều có mappedBy trỏ đến tên field không tồn tại.
- @JoinColumn không khớp tên cột khóa ngoại.
- Cascade không đúng làm persist/remove ngoài dự kiến.
- Đối tượng liên quan chưa được lưu hoặc không thuộc persistence context.

Ví dụ:

```java
@Entity
@Table(name = "orders", schema = "app")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }
}
```

Migration phải tạo cột customer_id và khóa ngoại tới khóa chính customer. Nếu lưu PurchaseOrder với Customer chưa tồn tại, database sẽ từ chối khi insert/flush. Nếu Customer đã có trong database nhưng object Java là transient/detached, hãy tải reference phù hợp trong transaction hoặc cấu hình cascade đúng với vòng đời domain. Không thêm CascadeType.ALL chỉ để làm biến mất exception; cascade có thể xóa hoặc persist dữ liệu không mong muốn.

### 4.4 Enum, ngày giờ, precision và kiểu dữ liệu

Một số lỗi mapping chỉ xuất hiện khi dữ liệu cụ thể được ghi hoặc đọc:

- Enum lưu ordinal có thể đổi nghĩa khi thứ tự enum thay đổi.
- String enum có thể vượt độ dài cột.
- BigDecimal có precision/scale không phù hợp.
- Instant/LocalDateTime/OffsetDateTime có quy tắc timezone khác nhau.
- UUID, JSON, ARRAY, enum native và kiểu vendor-specific cần hỗ trợ từ provider/dialect/driver.
- Primitive Java không thể biểu diễn SQL NULL; đọc NULL vào int/long có thể gây lỗi chuyển đổi hoặc giá trị mặc định sai.

Nếu giá trị enum cần ổn định theo tên, dùng @Enumerated(EnumType.STRING) và migration cột tương ứng; vẫn cần quản lý việc đổi tên enum vì dữ liệu đã lưu sẽ chứa tên cũ. Với tiền tệ, chọn precision/scale phù hợp và dùng BigDecimal thay vì float/double. Với ngày giờ, xác định rõ đó là thời điểm tuyệt đối hay giờ địa phương trước khi chọn kiểu Java và SQL.

## 5. Nhóm lỗi định nghĩa và thực thi truy vấn

### 5.1 Derived query không tìm thấy property

Spring Data phân tích tên method để tạo query theo thuộc tính entity. Nếu tên property sai, lỗi có thể xuất hiện ngay khi khởi tạo repository, thường dưới dạng PropertyReferenceException hoặc QueryCreationException.

Ví dụ entity có field email:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

Nếu viết findByMailAddress nhưng entity không có property mailAddress, Spring Data không thể tạo query. Tên method phải dựa trên property Java của entity, không nhất thiết là tên cột SQL. Ví dụ cột database là email_address nhưng field Java là emailAddress, derived query vẫn dùng findByEmailAddress.

Với property lồng nhau, tên method có thể mơ hồ. Dùng dấu phân tách _ để chỉ rõ đường dẫn, ví dụ findByCustomer_Address_City nếu model thực tế có các thuộc tính đó. Kiểm tra đúng tên Java property và quan hệ được ánh xạ.

### 5.2 JPQL khác SQL

JPQL truy vấn entity và thuộc tính Java, không truy vấn trực tiếp tên bảng/cột (trừ native query). Ví dụ:

```java
@Query("""
    select c
    from Customer c
    where c.email = :email
    """)
Optional<Customer> findCustomer(@Param("email") String email);
```

Ở đây Customer là entity name, email là thuộc tính entity. Viết SELECT * FROM customer trong JPQL sẽ sai cú pháp; nếu muốn dùng SQL theo bảng, khai báo nativeQuery = true:

```java
@Query(
    value = "SELECT * FROM app.customer WHERE email = :email",
    nativeQuery = true
)
Optional<Customer> findCustomerNative(@Param("email") String email);
```

Native query phụ thuộc DBMS, tên schema/cột và mapping kết quả. Khi dùng pagination, query đếm (countQuery) có thể cần khai báo riêng, nhất là query phức tạp có join, group by hoặc CTE.

### 5.3 Sai tham số, kiểu trả về hoặc số kết quả

Dấu hiệu:

- Named parameter not bound hoặc parameter not found.
- Kiểu tham số không tương thích với kiểu property.
- Query trả nhiều hàng nhưng method khai báo một entity/Optional.
- Projection không khớp alias hoặc constructor.
- No result hoặc NonUniqueResultException.

Ví dụ:

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findByEmail(@Param("email") String email);
```

Tên :email phải khớp @Param("email"). Nếu repository dùng positional parameter, thứ tự tham số phải chính xác. Tránh trộn tên tham số và vị trí trong cùng một query nếu không cần thiết.

Optional<Customer> thể hiện kỳ vọng tối đa một kết quả. Nếu email không unique trong database, query có thể trả nhiều hàng và phát sinh lỗi non-unique result. Ràng buộc unique ở database mới bảo vệ dữ liệu trước các ghi đồng thời; chỉ dùng Optional không tạo ra tính duy nhất.

Nếu nghiệp vụ cho phép nhiều kết quả, trả List<Customer>, Slice<Customer> hoặc Page<Customer> phù hợp. Nếu chỉ một kết quả được phép, bảo đảm constraint dữ liệu và xử lý trường hợp không có kết quả rõ ràng.

### 5.4 Lỗi khi thực thi SQL

Query có thể được tạo thành công nhưng thất bại khi chạy vì:

- Tên bảng/cột sai hoặc thiếu quyền.
- SQL không tương thích dialect/DBMS.
- Tham số có kiểu dữ liệu không tương thích.
- Dữ liệu vượt precision/length hoặc vi phạm constraint.
- Function, procedure hoặc extension không tồn tại.
- Query timeout, deadlock hoặc lock timeout.

Đọc SQLState và vendor code trong SQLException. SQLState thường giúp nhận diện nhóm lỗi chuẩn, còn vendor code và message chỉ rõ hơn theo database. Không xử lý lỗi bằng cách bắt Exception chung rồi bỏ qua; hãy dịch lỗi ở ranh giới phù hợp thành exception nghiệp vụ có ngữ nghĩa.

## 6. Nhóm lỗi dữ liệu và ràng buộc

### 6.1 NOT NULL, UNIQUE, FOREIGN KEY và CHECK

| Ràng buộc | Biểu hiện | Cách kiểm tra |
|---|---|---|
| NOT NULL | Không thể ghi giá trị null | Kiểm tra field, validation và cột |
| UNIQUE | Trùng giá trị duy nhất | Kiểm tra dữ liệu hiện có và race condition |
| FOREIGN KEY | Bản ghi con tham chiếu bản ghi cha không tồn tại | Kiểm tra thứ tự ghi, khóa và cascade |
| CHECK | Giá trị không thỏa điều kiện | Kiểm tra business rule và DDL |
| LENGTH/precision | Chuỗi/số vượt giới hạn cột | Kiểm tra length, precision, scale và rounding |

Spring có thể dịch lỗi constraint thành DataIntegrityViolationException hoặc DuplicateKeyException tùy driver và ngữ cảnh. Exception này không cho biết đầy đủ nghiệp vụ bị vi phạm; cần xem constraint name, SQLState và vendor message.

Không chỉ kiểm tra trước bằng SELECT rồi INSERT để tránh trùng. Hai request đồng thời vẫn có thể cùng thấy chưa tồn tại và cùng insert. Database unique constraint mới là hàng rào cuối cùng; bắt lỗi vi phạm và chuyển thành thông báo nghiệp vụ thích hợp.

### 6.2 Null và validation ở tầng ứng dụng

Có thể dùng Bean Validation để phản hồi sớm:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Entity
public class Contact {

    @Id
    private Long id;

    @NotBlank
    @Email
    @Size(max = 180)
    @Column(nullable = false, length = 180)
    private String email;
}
```

Các annotation validation kiểm tra dữ liệu ở tầng ứng dụng khi validation được kích hoạt; @Column mô tả mapping/schema cho JPA. Hai cơ chế không thay thế nhau. Nếu batch job hoặc native SQL ghi trực tiếp database, Bean Validation ở entity có thể không chạy; constraint database vẫn cần thiết.

### 6.3 Vi phạm kiểu và chuyển đổi

Các lỗi conversion có thể xảy ra khi:

- Cột SQL chứa chuỗi không thể chuyển sang kiểu Java.
- Dữ liệu cũ không tuân thủ format hiện tại.
- Native query trả kiểu numeric/date khác kiểu projection mong đợi.
- Enum trong database có giá trị không còn tồn tại trong Java.
- JSON/UUID/vendor type cần converter hoặc Hibernate type phù hợp.

Cách xử lý là kiểm tra giá trị thực tế, metadata cột, JDBC type và converter. Không ép kiểu bằng cast trong Java nếu chưa xác nhận dữ liệu hợp lệ. Với dữ liệu legacy, cân nhắc migration làm sạch và test các giá trị cũ trước khi siết chặt mapping.

## 7. Các lỗi trạng thái entity và transaction thường bị nhầm với lỗi dữ liệu

### 7.1 Transient, managed và detached

JPA phân biệt trạng thái entity:

- **Transient**: object mới, chưa được persistence context quản lý.
- **Managed**: entity đang được EntityManager quản lý; thay đổi có thể được flush.
- **Detached**: entity từng được quản lý nhưng hiện không còn gắn với persistence context.
- **Removed**: entity được đánh dấu xóa và sẽ bị xóa khi flush.

Một số lỗi như detached entity passed to persist, object references an unsaved transient instance hoặc entity not found xuất phát từ vòng đời entity/quan hệ. Hãy xác định object đang ở trạng thái nào, transaction còn mở không và thao tác persist/merge/reference có phù hợp không.

Ví dụ:

```java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException(
                    "Customer not found: " + id));

    customer.rename(newName);
    // Entity đang managed; dirty checking ghi thay đổi khi flush/commit.
}
```

Trong transaction, entity lấy từ repository thường được quản lý bởi persistence context hiện tại. Không cần gọi save() lần nữa chỉ để dirty checking phát hiện thay đổi; tuy nhiên gọi save() có thể cần thiết cho ý đồ repository/API hoặc entity detached.

### 7.2 LazyInitializationException

Lỗi này thường xảy ra khi truy cập quan hệ LAZY sau khi persistence context đã đóng. Cách xử lý:

- Tải dữ liệu cần thiết trong transaction bằng fetch join hoặc EntityGraph.
- Dùng DTO projection để chỉ lấy dữ liệu cần trả về.
- Giữ truy cập dữ liệu trong ranh giới service transaction phù hợp.
- Tránh bật EAGER toàn cục để chữa triệu chứng; có thể tạo N+1 query hoặc tải quá nhiều dữ liệu.

Ví dụ fetch join:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithCustomer(@Param("id") Long id);
```

Không phải mọi quan hệ đều nên fetch join trong mọi query. Với collection, pagination có thể có giới hạn hoặc gây kết quả trùng; chọn EntityGraph, batch fetching hoặc query DTO theo nhu cầu.

### 7.3 Optimistic locking và cập nhật đồng thời

Khi hai transaction cùng đọc và sửa một entity, @Version giúp phát hiện một transaction đã ghi trước. Transaction còn lại có thể gặp OptimisticLockException hoặc Spring OptimisticLockingFailureException.

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;

    public void decrease(int amount) {
        if (amount <= 0 || amount > quantity) {
            throw new IllegalArgumentException("Invalid amount");
        }
        quantity -= amount;
    }
}
```

Version được JPA provider quản lý; không tự tăng version trong code nghiệp vụ. Khi optimistic lock thất bại, đọc lại trạng thái mới và quyết định retry hay trả xung đột cho người dùng. Retry phải có giới hạn và chỉ thực hiện lại nghiệp vụ an toàn/idempotent.

### 7.4 Lỗi flush và commit

Một số lỗi không xuất hiện tại lệnh save() vì JPA có thể trì hoãn SQL đến flush hoặc commit. Vì vậy, test cần dùng saveAndFlush() hoặc EntityManager.flush() khi muốn lỗi phát sinh ngay trong test.

Transaction có thể thất bại ở cuối phương thức do constraint, deadlock hoặc optimistic lock. Nếu exception xảy ra tại commit, đọc root cause và transaction boundary; đừng kết luận method repository đã chạy thành công chỉ vì không ném lỗi ngay tại dòng save().

## 8. Bảng phân loại nhanh theo dấu hiệu

| Dấu hiệu | Nhóm ưu tiên kiểm tra | Điểm bắt đầu |
|---|---|---|
| App không khởi động, thiếu bean | Cấu hình | Dependency, component scan, bean definitions |
| Connection refused/authentication failed | Kết nối | URL, DB availability, credentials, network |
| Không tạo được EntityManagerFactory | Mapping/cấu hình | Entity metadata, dialect, JDBC metadata, schema |
| Table/column does not exist | Mapping/schema | Migration, schema name, naming strategy |
| PropertyReferenceException | Truy vấn | Tên Java property trong method repository |
| JPQL syntax/validation error | Truy vấn | Entity name, property, alias, parameter |
| SQLGrammarException | Truy vấn/schema | SQL sinh ra, dialect, table/column và quyền |
| DataIntegrityViolationException | Dữ liệu | Constraint name, giá trị, quan hệ |
| ConversionFailedException | Mapping/dữ liệu | Java type, JDBC type, converter |
| LazyInitializationException | Persistence context | Ranh giới transaction và fetch plan |
| OptimisticLockingFailureException | Đồng thời | @Version, transaction cạnh tranh |
| TransactionSystemException | Transaction/flush | Cause của flush/commit và rollback |

Bảng này chỉ định hướng ban đầu. Một SQLGrammarException có thể do migration chưa chạy (cấu hình triển khai), mapping sai hoặc query sai; luôn đối chiếu câu SQL và schema thực tế.

## 9. Bật log có kiểm soát để tìm nguyên nhân

Trong môi trường phát triển hoặc test, có thể bật log SQL và bind parameter:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.orm.jpa: DEBUG
    org.springframework.transaction: TRACE
```

Tên logger bind parameter phụ thuộc phiên bản Hibernate. Kiểm tra tài liệu phiên bản đang dùng. Không bật TRACE bind parameter rộng rãi ở production nếu chưa đánh giá rủi ro lộ dữ liệu, token, email, thông tin cá nhân hoặc bí mật nghiệp vụ.

Có thể bật format SQL trong cấu hình Hibernate khi cần đọc log dễ hơn. Tránh log SQL và parameter nhiều hơn mức cần thiết vì có thể làm tăng chi phí, dung lượng log và lộ dữ liệu.

Khi log exception, lưu đủ cause chain, SQLState, vendor error code và correlation/request id. Không chỉ log ex.getMessage() nếu làm mất root cause. Cũng không trả stack trace hoặc câu SQL nội bộ cho client; trả lỗi API có mã và thông điệp phù hợp, còn chi tiết kỹ thuật nằm trong log có kiểm soát.

## 10. Ví dụ chẩn đoán từ lỗi đến cách sửa

### Tình huống A: Repository không khởi tạo

Thông báo: No property 'mailAddress' found for type 'Customer'.

- **Nhóm**: định nghĩa truy vấn.
- **Nguyên nhân**: method derived query tham chiếu property Java không tồn tại.
- **Kiểm tra**: entity có field email; method đang dùng findByMailAddress.
- **Sửa**: đổi thành findByEmail hoặc thêm property đúng theo domain và mapping.
- **Kiểm thử**: khởi tạo repository context và gọi method với dữ liệu có/không có kết quả.

### Tình huống B: Query chạy nhưng báo thiếu cột

Thông báo: column c.created_at does not exist.

- **Nhóm**: mapping/schema hoặc query.
- **Nguyên nhân có thể**: entity/JPQL/native SQL dùng created_at nhưng migration chưa tạo cột, tên cột thực tế khác hoặc kết nối sai schema.
- **Kiểm tra**: log SQL, metadata bảng, migration history và schema đang kết nối.
- **Sửa**: đồng bộ @Column(name=...), JPQL/native SQL và migration theo tên chuẩn.
- **Kiểm thử**: khởi tạo database test rỗng bằng migration rồi chạy query.

### Tình huống C: Insert bị trùng email

Thông báo: DataIntegrityViolationException, unique constraint violation.

- **Nhóm**: dữ liệu/ràng buộc.
- **Nguyên nhân**: email đã tồn tại hoặc hai request insert cùng lúc.
- **Kiểm tra**: constraint name, dữ liệu hiện có, transaction cạnh tranh.
- **Sửa**: giữ unique constraint; bắt lỗi ở ranh giới service và chuyển thành lỗi nghiệp vụ “email đã được sử dụng”.
- **Kiểm thử**: test trường hợp trùng tuần tự và trường hợp đồng thời nếu rủi ro cao.

### Tình huống D: LazyInitializationException khi trả JSON

Thông báo: could not initialize proxy - no Session.

- **Nhóm**: persistence context/fetch plan.
- **Nguyên nhân**: controller/serializer truy cập quan hệ LAZY sau khi service transaction đã kết thúc.
- **Sửa**: service tải dữ liệu cần thiết và trả DTO; dùng fetch join/EntityGraph có chọn lọc.
- **Kiểm thử**: gọi service, đóng persistence context rồi serialize DTO và xác minh không phát sinh truy vấn ngoài dự kiến.

## 11. Quy trình xử lý theo checklist

- [ ] Ghi nhận thời điểm lỗi: startup, repository creation, method call, flush hay commit.
- [ ] Đọc exception ngoài cùng và toàn bộ Caused by.
- [ ] Xác định DBMS, phiên bản, JDBC driver và profile đang chạy.
- [ ] Lấy SQL sinh ra và SQLState/vendor error code khi có.
- [ ] Đối chiếu entity mapping với migration/schema thực tế.
- [ ] Kiểm tra query method, JPQL/native SQL, tên tham số và kiểu trả về.
- [ ] Kiểm tra dữ liệu đầu vào, null, length, precision và constraint.
- [ ] Kiểm tra persistence context, fetch plan và transaction boundary.
- [ ] Tái hiện bằng test cô lập trên đúng DBMS khi lỗi phụ thuộc database.
- [ ] Thêm test hồi quy cho nguyên nhân vừa sửa.

Không sửa nhiều nhóm cùng lúc khi chưa có bằng chứng. Giữ lại một ca tái hiện nhỏ giúp xác nhận thay đổi nào thực sự giải quyết lỗi.

## 12. Ghi nhớ

- **Cấu hình/kết nối**: kiểm tra bean, profile, DataSource, driver, transaction manager, schema và quyền.
- **Ánh xạ**: kiểm tra @Entity, @Id, @Column, quan hệ, kiểu Java/SQL và migration.
- **Truy vấn**: phân biệt derived query, JPQL và native SQL; đối chiếu property Java, entity name, tham số và kết quả.
- **Dữ liệu**: kiểm tra null, constraint, conversion, dữ liệu trùng, trạng thái entity và concurrency.
- Đọc cause chain, SQL và vendor error code trước khi sửa.
- Flush/commit có thể là thời điểm lỗi thực sự xuất hiện; save() trả về chưa chứng minh transaction đã commit.
- Test hồi quy trên đúng DBMS giúp tránh lỗi chỉ xuất hiện khi triển khai.

## 13. Tài liệu tham khảo

- [Spring Data JPA — Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Hibernate ORM — User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
