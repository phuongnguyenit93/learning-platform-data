# Phát hiện truy vấn sai lúc khởi tạo và lúc thực thi trong Spring Data JPA

## 1. Vì sao lỗi truy vấn xuất hiện ở hai thời điểm khác nhau?

Trong Spring Data JPA, một repository method có thể được phân tích và chuẩn bị ngay khi ứng dụng khởi động, nhưng SQL cuối cùng thường chỉ được gửi tới database khi method được gọi. Vì vậy, lỗi truy vấn có thể xuất hiện ở hai giai đoạn:

- **Lúc khởi tạo (bootstrap/startup):** Spring Data phân tích tên method, tìm thuộc tính entity, tìm named query hoặc tạo đối tượng truy vấn JPQL. Những lỗi có thể phát hiện từ metadata và cú pháp JPQL thường xuất hiện trong giai đoạn này.
- **Lúc thực thi (execution):** JPA provider tạo và gửi SQL, database phân tích câu lệnh, bind giá trị và truy cập bảng/cột/hàm thực tế. Các lỗi phụ thuộc schema, database, dữ liệu, quyền truy cập hoặc giá trị tham số thường chỉ xuất hiện khi truy vấn chạy.

Phân biệt hai giai đoạn giúp xác định đúng nơi cần kiểm tra. Nếu ứng dụng không thể tạo repository bean, hãy xem query derivation, JPQL và repository bootstrap. Nếu repository bean đã tạo được nhưng method thất bại khi gọi, hãy kiểm tra SQL sinh ra, schema, tham số và database.

Không phải mọi lỗi đều được phân loại tuyệt đối theo hai nhóm. JPA provider, phiên bản Spring Data JPA, loại truy vấn và bootstrap mode có thể làm thay đổi thời điểm một số kiểm tra được thực hiện.

## 2. Vòng đời của một repository query

Một repository method thường đi qua các bước khái quát sau:

~~~text
Ứng dụng khởi động
       |
       v
Spring tạo repository bean
       |
       v
Phân tích method name hoặc tìm query đã khai báo
       |
       v
Tạo query object và kiểm tra những phần có thể kiểm tra sớm
       |
       v
Ứng dụng sẵn sàng nhận request
       |
       v
Service gọi repository method
       |
       v
JPA provider tạo SQL và bind tham số
       |
       v
Database phân tích và thực thi SQL
       |
       v
Ánh xạ kết quả về entity / projection
~~~

Các bước trên là mô hình khái niệm. Một số xử lý như tạo query object, parse JPQL hoặc kiểm tra metadata có thể diễn ra sớm; việc gửi SQL và kiểm tra khả năng thực thi trên schema thực tế thường cần tới lúc method được gọi.

Ví dụ repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Query("""
        select c
        from Customer c
        where c.status = :status
    """)
    List<Customer> findByStatus(@Param("status") CustomerStatus status);
}
~~~

Khi Spring tạo repository, framework có thể phân tích findByEmail và chuẩn bị truy vấn JPQL cho findByStatus. Khi ứng dụng gọi findByEmail, provider mới cần lấy dữ liệu từ database để trả kết quả.

## 3. Lỗi có thể phát hiện lúc khởi tạo repository

### 3.1. Derived query tham chiếu sai tên thuộc tính

Spring Data phân tích tên method để xác định thuộc tính và điều kiện cần truy vấn. Nếu tên thuộc tính không tồn tại trong entity, query derivation có thể thất bại khi repository được tạo.

Ví dụ entity:

~~~java
@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String email;
    private String fullName;
}
~~~

Repository viết sai:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmali(String email);
}
~~~

Customer không có thuộc tính emali; tên đúng là email. Spring Data không thể tạo truy vấn từ property path không hợp lệ. Lỗi thường xuất hiện trong quá trình khởi tạo repository, với nguyên nhân gốc có thể là PropertyReferenceException hoặc một exception tạo query được bọc bên ngoài.

Sửa lại:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Ngoài tên thuộc tính trực tiếp, cần kiểm tra cả property path lồng nhau:

~~~java
List<Customer> findByAddress_City(String city);
~~~

Entity phải có quan hệ hoặc thuộc tính address, và kiểu của nó phải có thuộc tính city. Dấu gạch dưới có thể giúp phân tách rõ các thành phần của property path khi tên thuộc tính gây mơ hồ.

### 3.2. JPQL @Query sai cú pháp hoặc sai tên entity/property

JPQL dùng tên entity và thuộc tính Java, không dùng trực tiếp tên bảng/cột SQL.

Ví dụ sai:

~~~java
@Query("select c from Customer c where c.emali = :email")
Optional<Customer> findByEmail(@Param("email") String email);
~~~

Nếu entity chỉ có thuộc tính email, biểu thức c.emali không hợp lệ. Với truy vấn JPQL được khai báo bằng @Query, Spring Data JPA và JPA provider thường có thể yêu cầu provider tạo query để kiểm tra cú pháp/metadata khi repository được khởi tạo. Vì vậy, lỗi có thể làm ứng dụng thất bại ngay lúc startup, trước khi method được gọi.

Phiên bản đúng:

~~~java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findByEmail(@Param("email") String email);
~~~

Các lỗi JPQL thường gặp:

- Viết sai tên entity trong FROM.
- Dùng tên cột database thay cho tên thuộc tính entity.
- Viết sai alias hoặc tham chiếu alias chưa khai báo.
- Dùng sai cú pháp JOIN, ORDER BY, GROUP BY hoặc biểu thức.
- Gọi hàm không được provider/database hỗ trợ.
- Dùng constructor expression với tên DTO hoặc thứ tự kiểu tham số sai.
- Khai báo count query không hợp lệ cho phương thức phân trang.

Thời điểm và loại exception cụ thể phụ thuộc provider và cách repository được khởi tạo. Nhưng với JPQL tĩnh, kiểm tra cú pháp sớm là một lợi thế quan trọng.

### 3.3. Named query không tồn tại hoặc khai báo sai

JPA cho phép khai báo named query trên entity hoặc trong mapping XML. Ví dụ:

~~~java
@Entity
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = :email"
)
public class Customer {
    @Id
    private Long id;

    private String email;
}
~~~

Spring Data JPA có thể tìm named query theo quy ước tên entity và method, chẳng hạn Customer.findByEmail. Nếu ứng dụng cấu hình chỉ sử dụng declared query mà named query tương ứng không tồn tại, việc tạo repository có thể thất bại.

Nếu named query tồn tại nhưng JPQL sai, JPA provider có thể phát hiện khi khởi tạo persistence unit hoặc khi query được tạo; thời điểm chính xác phụ thuộc provider.

Khi dùng @Query trực tiếp trên repository method, khai báo đó được ưu tiên cho method tương ứng so với named query theo quy tắc lookup của Spring Data JPA.

### 3.4. Lỗi tên tham số hoặc khai báo method

Ví dụ query dùng :status nhưng method không cung cấp tham số phù hợp:

~~~java
@Query("select c from Customer c where c.status = :status")
List<Customer> findByStatus(CustomerStatus state);
~~~

Tên tham số method là state, còn named parameter trong JPQL là status. Hãy khai báo nhất quán bằng @Param:

~~~java
@Query("select c from Customer c where c.status = :status")
List<Customer> findByStatus(
    @Param("status") CustomerStatus state
);
~~~

Một số sai lệch tham số có thể được phát hiện khi Spring Data phân tích method hoặc tạo query; việc bind giá trị và kiểm tra kiểu thực tế diễn ra khi method được gọi. Đừng dựa vào việc ứng dụng startup thành công để kết luận mọi cách bind tham số đều đúng.

## 4. Lỗi thường chỉ lộ ra khi truy vấn thực thi

### 4.1. Native SQL sai tên bảng hoặc cột

Native query dùng SQL của database:

~~~java
@Query(
    value = "select * from customer where emali = :email",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(
    @Param("email") String email
);
~~~

Giả sử bảng customer có cột email chứ không có emali. Cú pháp JPQL parser không kiểm tra được tên cột native này như một thuộc tính entity. Database thường chỉ báo lỗi khi câu SQL được thực thi.

Sửa lại:

~~~java
@Query(
    value = "select * from customer where email = :email",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(
    @Param("email") String email
);
~~~

Native SQL có thể được provider xử lý một phần khi tạo query, nhưng việc xác nhận đầy đủ cú pháp, tên bảng/cột, function, operator và quyền truy cập thường cần database thực thi. Khả năng kiểm tra sớm phụ thuộc provider, driver và database.

### 4.2. Bảng hoặc cột không tồn tại trong schema đang kết nối

Một JPQL query có thể hợp lệ theo entity metadata, nhưng schema thực tế lại thiếu bảng hoặc cột cần thiết. Khi truy vấn chạy, database có thể trả lỗi kiểu “table/relation not found” hoặc “column not found”.

Ví dụ:

- Entity ánh xạ tới bảng customer.
- Ứng dụng kết nối nhầm database hoặc schema.
- Migration tạo bảng chưa được chạy ở môi trường đó.
- Tên cột bị đổi nhưng native query chưa được cập nhật.

Hãy kiểm tra datasource URL, database/schema hiện tại, migration history và metadata bảng/cột trên chính môi trường bị lỗi.

### 4.3. Hàm database hoặc kiểu dữ liệu không tương thích

Một JPQL query có thể chứa:

~~~java
@Query("""
    select function('date_trunc', 'day', o.createdAt)
    from PurchaseOrder o
""")
List<Object> findOrderDays();
~~~

Nếu database không có hàm date_trunc, extension chưa cài, hoặc kiểu đối số không phù hợp, lỗi có thể xuất hiện khi database thực thi SQL. Một số provider có thể phát hiện sớm hàm hoặc kiểu không hỗ trợ, nhưng không nên giả định mọi hàm database được kiểm tra đầy đủ khi startup.

Tương tự, native query dùng JSON operator, full-text search, hàm địa lý hoặc kiểu vendor-specific có thể chỉ chạy trên một database/dialect cụ thể.

### 4.4. Lỗi bind tham số và dữ liệu thực tế

Query có thể được tạo thành công nhưng thất bại khi chạy do:

- Thiếu giá trị cho named parameter.
- Giá trị Java không tương thích với kiểu cột hoặc kiểu biểu thức.
- Giá trị vượt precision/scale hoặc độ dài cột.
- Truyền enum theo cách không khớp mapping.
- Dữ liệu đầu vào làm hàm database nhận giá trị không hợp lệ.
- Kết quả trả về không ánh xạ được vào entity hoặc projection.

Một số lỗi kiểu tham số có thể được phát hiện từ metadata; các lỗi liên quan giá trị thực tế thường chỉ có thể biết khi bind hoặc thực thi.

### 4.5. Lỗi quyền truy cập, kết nối và constraint

Query hợp lệ vẫn có thể thất bại do môi trường:

- Database không khả dụng hoặc connection pool hết kết nối.
- Tài khoản ứng dụng không có quyền SELECT/EXECUTE.
- Hàm hoặc extension không được cấp quyền sử dụng.
- Query timeout hoặc lock timeout.
- Dữ liệu vi phạm constraint khi query ghi dữ liệu hoặc stored function có tác dụng phụ.
- Transaction đã bị đánh dấu rollback-only.

Đây là lỗi môi trường hoặc thực thi, không nhất thiết là lỗi cú pháp JPQL.

## 5. So sánh thời điểm phát hiện theo loại query

| Loại truy vấn | Có thể kiểm tra lúc khởi tạo | Cần thực thi để xác nhận |
|---|---|---|
| Derived query, ví dụ findByEmail | Phân tích tên method, property path và loại truy vấn | SQL, schema, dữ liệu, quyền và kết quả |
| JPQL @Query | Parse JPQL, entity/attribute, alias và nhiều lỗi cú pháp | SQL cụ thể, function/database behavior, bind value và kết quả |
| JPA @NamedQuery | Provider thường kiểm tra khi persistence unit hoặc query được khởi tạo | Database-specific behavior, schema và dữ liệu |
| Native @Query | Method metadata, parameter metadata hoặc một phần xử lý query tùy provider | Thường cần database thực thi để xác nhận SQL, tên cột/bảng, hàm và dialect |
| Stored procedure/function | Kiểm tra khai báo method và một phần metadata | Procedure/function thực tế, quyền, tham số và kiểu kết quả |
| Criteria API tạo động | Kiểm tra code Java khi compile; một số cấu trúc khi tạo Criteria query | Query cuối cùng, bind value và SQL trên database |

Bảng này mô tả xu hướng chung. Nó không phải cam kết rằng mọi lỗi của một loại query luôn xuất hiện ở cùng một thời điểm trên mọi phiên bản.

## 6. Repository bootstrap mode ảnh hưởng thời điểm khởi tạo

Spring Data JPA hỗ trợ các chế độ bootstrap repository. Chế độ này quyết định repository được khởi tạo sớm hay muộn, do đó có thể làm thay đổi thời điểm lỗi khởi tạo được nhìn thấy.

| Chế độ | Hành vi khái quát | Khi nào lỗi khởi tạo repository lộ ra? |
|---|---|---|
| DEFAULT | Khởi tạo repository theo cách mặc định, thường eager | Trong giai đoạn startup |
| DEFERRED | Trì hoãn một phần khởi tạo tới sau khi application context refresh, nhưng hoàn tất trước khi ứng dụng báo sẵn sàng | Gần cuối startup, trước trạng thái ready |
| LAZY | Khởi tạo repository khi bean được yêu cầu lần đầu | Khi repository được truy cập lần đầu |

Với Spring Boot, có thể cấu hình qua:

~~~properties
spring.data.jpa.repositories.bootstrap-mode=default
~~~

Hoặc dùng deferred hay lazy khi kiến trúc có nhu cầu cụ thể.

Lưu ý:

- LAZY không sửa query sai; nó chỉ trì hoãn thời điểm lỗi có thể xuất hiện.
- Nếu repository chỉ được truy cập sau khi có request, lỗi có thể xuất hiện trong request đầu tiên.
- DEFERRED giúp trì hoãn công việc nhưng vẫn hoàn tất khởi tạo repository trước khi ứng dụng được xem là sẵn sàng.
- Với ứng dụng production, eager/default bootstrap thường giúp phát hiện sớm lỗi cấu hình trước khi nhận traffic.

Không nên bật lazy bootstrap chỉ để che một lỗi query hoặc làm startup có vẻ thành công.

## 7. QueryLookupStrategy và việc tìm truy vấn

Spring Data JPA có chiến lược xác định query cho repository method:

- CREATE: tạo query từ tên method.
- USE_DECLARED_QUERY: yêu cầu query đã được khai báo, ví dụ @Query hoặc named query phù hợp.
- CREATE_IF_NOT_FOUND: tìm declared query trước; nếu không có thì tạo query từ tên method.

CREATE_IF_NOT_FOUND là lựa chọn mặc định phổ biến. Ví dụ, Spring Data có thể tìm named query theo quy ước tên trước khi phân tích method thành derived query.

Chiến lược lookup trả lời câu hỏi **query lấy từ đâu**; nó không bảo đảm database đã thực thi query thành công. Một declared JPQL query có thể parse được nhưng vẫn gặp lỗi schema hoặc dữ liệu khi chạy.

Khi debug, hãy xác định method đang dùng:

1. @Query trên repository method?
2. Named query trong entity hoặc XML?
3. Derived query từ method name?
4. Native SQL hay JPQL?

Nếu không biết query nào thực sự được chọn, có thể kiểm tra khai báo method, named query và log phù hợp của Spring Data/JPA provider.

## 8. Cách đọc stack trace để tìm giai đoạn lỗi

### 8.1. Lỗi khi tạo ApplicationContext

Nếu ứng dụng không khởi động được và stack trace có các lớp như:

- BeanCreationException
- UnsatisfiedDependencyException
- QueryCreationException
- PropertyReferenceException
- Exception parse/semantic query của Hibernate

hãy lần theo chuỗi Caused by sâu nhất. Exception bên ngoài thường chỉ cho biết repository bean hoặc service bean không tạo được; nguyên nhân thực sự thường nằm ở lỗi property path, JPQL hoặc named query.

Ví dụ dạng lỗi:

~~~text
Error creating bean with name 'customerRepository'
...
QueryCreationException
...
No property 'emali' found for type 'Customer'
~~~

Cách xử lý: kiểm tra method name, entity property, @Query, named query và tham số trước khi kiểm tra SQL runtime.

### 8.2. Lỗi sau khi gọi repository method

Nếu ứng dụng đã startup thành công và lỗi chỉ xảy ra khi service gọi repository, stack trace có thể chứa:

- DataAccessException hoặc lớp con được Spring dịch.
- InvalidDataAccessResourceUsageException.
- BadSqlGrammarException với một số đường JDBC/translation.
- SQLGrammarException, JDBCException hoặc exception tương ứng của Hibernate.
- Exception cụ thể từ driver, chẳng hạn lỗi SQL của PostgreSQL hoặc SQL Server.

Hãy xem câu SQL và thông báo gốc của database. Đừng chỉ sửa annotation dựa trên tên exception bên ngoài; cần xác định database đang từ chối bảng, cột, hàm, kiểu, quyền hay giá trị nào.

### 8.3. Không phải mọi lỗi startup đều là query lỗi

Một repository có thể không khởi tạo được vì datasource, entity scan, transaction manager, dialect hoặc mapping entity sai. Hãy đọc nguyên nhân gốc trước khi kết luận query method có vấn đề.

## 9. Bật log để quan sát SQL và bind parameter

Trong môi trường phát triển, có thể bật log Hibernate để xem SQL được gửi xuống database:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Với Hibernate 6, log bind parameter có thể bật bằng:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Với Hibernate 5, logger bind parameter thường dùng category:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Tên logger phụ thuộc phiên bản Hibernate. Chỉ bật log bind parameter khi cần chẩn đoán; giá trị có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Không nên để TRACE bind parameter trên production lâu dài nếu chưa có kiểm soát bảo vệ log.

Có thể dùng spring.jpa.show-sql=true để quan sát SQL đơn giản, nhưng logger thường hữu ích hơn khi cần kiểm soát mức log và kết hợp với log ứng dụng.

Khi đọc SQL:

1. Xác định SQL có đúng bảng/cột dự kiến không.
2. Kiểm tra alias và JOIN.
3. Kiểm tra placeholder và giá trị bind.
4. So sánh kiểu dữ liệu Java với kiểu database.
5. Chạy câu SQL trên đúng database/schema để tái hiện.
6. Xem execution plan nếu truy vấn chạy được nhưng quá chậm.

## 10. Schema validation không thay thế query validation

Một cấu hình thường gặp:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

validate yêu cầu Hibernate kiểm tra một số phần tương thích giữa mapping entity và schema database khi khởi tạo. Nó có thể giúp phát hiện bảng/cột mapping không khớp.

Tuy nhiên, schema validation không có nghĩa là Hibernate đã chạy thử tất cả repository method. Nó không bảo đảm:

- Mọi native query đều đúng cú pháp.
- Mọi tên cột trong native SQL đều tồn tại.
- Mọi database function hoặc stored procedure đều có.
- Mọi tham số và giá trị runtime đều hợp lệ.
- Mọi truy vấn đều có quyền truy cập và hiệu năng phù hợp.

Vì vậy cần kết hợp kiểm tra mapping/schema với integration test thực thi từng query quan trọng.

## 11. Kiểm thử để phát hiện lỗi trước khi triển khai

### 11.1. Kiểm tra repository bootstrap trong test

@DataJpaTest tạo slice test cho JPA, thường cấu hình entity và repository để kiểm tra tầng persistence:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void repositoryContextStarts() {
        assertThat(repository).isNotNull();
    }
}
~~~

Test này hữu ích để phát hiện lỗi tạo repository, derived query hoặc JPQL có thể kiểm tra lúc bootstrap. Nhưng nó không xác nhận mọi method chạy đúng nếu method chưa được gọi.

### 11.2. Gọi từng query với dữ liệu đại diện

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        Customer customer = new Customer("an@example.com");
        repository.saveAndFlush(customer);

        Optional<Customer> result =
            repository.findByEmail("an@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getEmail())
            .isEqualTo("an@example.com");
    }
}
~~~

Đây là ví dụ cấu trúc; constructor và getter cần khớp với entity thực tế của dự án. Gọi method trong test buộc query đi qua provider và database, giúp phát hiện lỗi chỉ lộ ra khi thực thi.

Nên có test riêng cho:

- Derived query với các property path.
- JPQL @Query và named query.
- Native query và database function.
- Named parameter, enum và kiểu ngày giờ.
- JOIN, DISTINCT, GROUP BY và count query.
- Phân trang/sắp xếp.
- Trường hợp không có kết quả, NULL và dữ liệu biên.

### 11.3. Dùng đúng database trong integration test

H2 có thể hữu ích cho test nhanh, nhưng không thay thế hoàn toàn database production. Một native query dùng PostgreSQL jsonb, unaccent, date_trunc hoặc toán tử riêng có thể không chạy trên H2.

Nếu production dùng PostgreSQL, MySQL hoặc SQL Server, hãy cân nhắc Testcontainers để chạy đúng engine trong integration test. Điều này giúp phát hiện lỗi dialect, function, schema và kiểu dữ liệu gần với môi trường thật.

### 11.4. Kiểm thử toàn bộ query method quan trọng

Việc ApplicationContext khởi động thành công chỉ chứng minh các phần được khởi tạo đã qua những kiểm tra tương ứng. Nó không chứng minh mọi method repository đã chạy đúng.

Một checklist kiểm thử tốt:

1. Khởi tạo persistence context và repository.
2. Tạo schema bằng migration giống môi trường mục tiêu.
3. Gọi từng query method quan trọng.
4. Xác nhận nội dung, số lượng và kiểu kết quả.
5. Kiểm tra tham số NULL và giá trị biên.
6. Kiểm tra count query khi dùng Page.
7. Chạy test trên database đúng dialect.
8. Kiểm tra query chậm bằng execution plan khi cần.

## 12. Quy trình xử lý lỗi theo thời điểm

Khi gặp lỗi, hãy làm theo thứ tự:

1. **Xác định thời điểm:** ứng dụng thất bại trong startup hay sau khi method repository được gọi?
2. **Tìm nguyên nhân gốc:** đọc các dòng Caused by sâu nhất trong stack trace.
3. **Xác định loại query:** derived, JPQL, named query, native SQL, stored procedure hay Criteria.
4. **Nếu startup lỗi:** kiểm tra tên property, entity name, JPQL, named query, tham số và repository bootstrap.
5. **Nếu runtime lỗi:** xem SQL, bind parameter, database/schema, function, quyền, kiểu dữ liệu, transaction và dữ liệu đầu vào.
6. **Tái hiện bằng integration test:** chạy query trên database và schema tương ứng.
7. **Sửa tại đúng tầng:** query derivation/JPQL, mapping, migration, native SQL hoặc cấu hình database.
8. **Chạy lại test:** xác nhận cả repository bootstrap lẫn method thực thi thành công.

Không nên đổi ddl-auto, chuyển sang lazy bootstrap hoặc tắt validation chỉ để ứng dụng vượt qua startup. Những thay đổi đó có thể trì hoãn lỗi tới lúc có request và làm khó việc chẩn đoán.

## 13. Ghi nhớ

- Derived query thường được phân tích khi Spring Data tạo repository; tên property sai thường làm lỗi startup.
- JPQL @Query thường được provider kiểm tra cú pháp/metadata khi repository query được khởi tạo.
- Named query có thể được provider kiểm tra khi persistence unit hoặc query được khởi tạo; thời điểm cụ thể phụ thuộc provider.
- Native SQL thường cần database thực thi mới xác nhận đầy đủ tên bảng/cột, cú pháp và function; mức kiểm tra sớm tùy provider.
- Lỗi schema, quyền, kết nối, kiểu tham số và dữ liệu thường lộ ra khi thực thi.
- DEFAULT, DEFERRED và LAZY thay đổi thời điểm repository được khởi tạo, không sửa nội dung query sai.
- ddl-auto=validate kiểm tra một phần mapping/schema, không chạy thử mọi repository method.
- Startup test và integration test thực thi query là hai lớp kiểm tra bổ sung cho nhau.
- Dùng đúng database trong Testcontainers hoặc môi trường tương đương khi query phụ thuộc dialect.
- Đọc exception gốc và SQL thực tế trước khi thay đổi cấu hình.

Phát hiện lỗi sớm cần kết hợp kiểm tra lúc repository bootstrap với integration test chạy truy vấn thật. Kiểm tra startup giúp bắt lỗi tên method, property và JPQL; thực thi trên đúng database giúp bắt lỗi SQL, schema, function, tham số và hành vi dữ liệu mà không thể xác nhận chỉ từ metadata.