# Phân biệt R2DBC, JDBC và JPA/Hibernate

R2DBC, JDBC và JPA/Hibernate đều xuất hiện khi một ứng dụng Java làm việc với cơ sở dữ liệu quan hệ. Tuy nhiên, chúng không phải là ba công nghệ cùng tầng để thay thế trực tiếp cho nhau. **JDBC và R2DBC định nghĩa cách ứng dụng giao tiếp với cơ sở dữ liệu; JPA định nghĩa cách ánh xạ và quản lý dữ liệu dưới dạng đối tượng; Hibernate là một implementation phổ biến của JPA.**

Muốn chọn đúng công nghệ trong Spring, trước hết cần phân biệt hai câu hỏi:

- Ứng dụng gửi câu lệnh SQL và nhận kết quả theo kiểu blocking hay reactive?
- Ứng dụng muốn tự quản lý việc ánh xạ dữ liệu hay dùng một ORM quản lý trạng thái và quan hệ giữa các entity?

## 1. Nhìn nhanh vị trí của từng công nghệ

| Công nghệ | Thuộc tầng nào? | Cách thực thi thường gặp | Vai trò chính |
|---|---|---|---|
| JDBC | API kết nối cơ sở dữ liệu của Java | Blocking, đồng bộ | Gửi SQL, nhận kết quả qua driver JDBC |
| R2DBC | SPI kết nối cơ sở dữ liệu quan hệ theo mô hình reactive | Non-blocking nếu driver hỗ trợ | Gửi SQL và phát kết quả theo luồng reactive |
| JPA | Đặc tả persistence và ORM của Java | Thường blocking vì provider dùng JDBC | Quy định cách ánh xạ entity, truy vấn và quản lý vòng đời đối tượng |
| Hibernate ORM | ORM provider, có thể triển khai JPA | Thường blocking trong ứng dụng Spring MVC | Thực thi các quy tắc ORM, tạo SQL và đồng bộ entity với cơ sở dữ liệu |

JPA không phải là một driver cơ sở dữ liệu. Hibernate cũng không phải một giao thức kết nối thay thế JDBC. Trong cấu hình Hibernate ORM thông thường, Hibernate sử dụng JDBC ở tầng dưới để thực thi SQL.

Sơ đồ các tầng thường gặp:

~~~text
Ứng dụng Spring
│
├── Spring Data JDBC
│      └── JDBC API
│             └── JDBC Driver
│                    └── Cơ sở dữ liệu
│
├── Spring Data R2DBC
│      └── R2DBC SPI
│             └── R2DBC Driver
│                    └── Cơ sở dữ liệu
│
└── Spring Data JPA
       └── JPA API
              └── Hibernate ORM (JPA provider)
                     └── JDBC API
                            └── JDBC Driver
                                   └── Cơ sở dữ liệu
~~~

Sơ đồ mô tả kiến trúc phổ biến trong ứng dụng Spring; provider JPA có thể là implementation khác ngoài Hibernate.

## 2. JDBC: cách kết nối cơ sở dữ liệu truyền thống của Java

**JDBC (Java Database Connectivity)** là API chuẩn của Java để làm việc với cơ sở dữ liệu quan hệ. Ứng dụng lấy kết nối, tạo statement, thực thi SQL rồi đọc dữ liệu từ ResultSet. JDBC driver chuyển các lời gọi API thành giao tiếp phù hợp với hệ quản trị cơ sở dữ liệu.

Một lời gọi JDBC thông thường là blocking: thread gọi phương thức sẽ chờ trong lúc driver gửi câu lệnh và chờ cơ sở dữ liệu trả kết quả. Trong thời gian chờ, thread đó không thể tiếp tục xử lý một công việc khác.

Ví dụ sử dụng JdbcTemplate của Spring:

~~~java
List<Customer> customers = jdbcTemplate.query(
    "SELECT id, name FROM customer WHERE active = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"),
        rs.getString("name")
    ),
    true
);
~~~

Ở ví dụ này:

1. JdbcTemplate quản lý các thao tác JDBC phổ biến như lấy và giải phóng tài nguyên.
2. Câu SQL được gửi xuống cơ sở dữ liệu thông qua JDBC driver.
3. RowMapper chuyển từng dòng trong ResultSet thành một đối tượng Java.
4. Phương thức chỉ trả về sau khi truy vấn hoàn tất và dữ liệu đã được đọc.

JDBC không bắt buộc phải dùng ORM. Lập trình viên có thể viết SQL và tự ánh xạ từng dòng, hoặc dùng thư viện ở tầng cao hơn như Spring Data JDBC. JDBC phù hợp với ứng dụng cần SQL rõ ràng, cách thực thi dễ theo dõi và hệ sinh thái driver trưởng thành.

Trong Spring, những thành phần thường gặp ở nhánh JDBC gồm:

- DataSource: cung cấp kết nối JDBC, thường đi cùng connection pool.
- JdbcTemplate hoặc JdbcClient: hỗ trợ thực thi SQL và xử lý tài nguyên.
- DataSourceTransactionManager hoặc JdbcTransactionManager: quản lý transaction JDBC.
- Spring Data JDBC: cung cấp repository và mapping theo mô hình aggregate trên nền JDBC.

## 3. R2DBC: kết nối cơ sở dữ liệu theo mô hình reactive

**R2DBC (Reactive Relational Database Connectivity)** là một SPI dành cho việc truy cập cơ sở dữ liệu quan hệ theo mô hình reactive. Nó định nghĩa các abstraction như ConnectionFactory, Connection, Statement và Result. Driver R2DBC hiện thực SPI đó cho từng hệ quản trị cơ sở dữ liệu.

Điểm khác biệt quan trọng là API R2DBC được thiết kế để không chặn thread khi chờ I/O. Thay vì trả ngay một List chứa toàn bộ kết quả, thao tác thường trả về một reactive publisher. Trong Spring, ứng dụng thường làm việc với Reactor:

- Mono<T> biểu diễn kết quả có tối đa một phần tử hoặc không có phần tử.
- Flux<T> biểu diễn một luồng có thể phát ra nhiều phần tử.

Ví dụ dùng DatabaseClient của Spring:

~~~java
Flux<Customer> customers =
    databaseClient.sql(
            "SELECT id, name FROM customer WHERE active = :active"
        )
        .bind("active", true)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all();
~~~

Đoạn code trên mô tả một pipeline reactive. Việc thực thi và phát dữ liệu diễn ra khi publisher được subscribe. Kết quả được phát dần qua Flux, thay vì bắt buộc phải gom tất cả vào một collection trước khi trả về. Pipeline có thể kết hợp với các bước reactive khác và hỗ trợ backpressure.

Spring Data R2DBC cung cấp abstraction ở tầng repository và mapping để giảm phần code truy cập dữ liệu trực tiếp:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByActiveTrue();
}
~~~

Entity được ánh xạ bằng các annotation của Spring Data Relational, chẳng hạn @Table, @Id và @Column:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private boolean active;
}
~~~

R2DBC không tự động làm cho mọi thao tác trong ứng dụng trở thành non-blocking. Lợi ích đó chỉ có khi driver cơ sở dữ liệu thực sự hỗ trợ R2DBC và các bước I/O liên quan trong pipeline cũng không chặn thread. Nếu gọi một API blocking bên trong pipeline reactive, thread vẫn có thể bị chặn.

Khả năng của driver R2DBC cũng phụ thuộc hệ quản trị cơ sở dữ liệu và phiên bản driver. Cần kiểm tra hỗ trợ về kiểu dữ liệu, transaction, batch, locking và các tính năng SQL mà ứng dụng thực sự sử dụng.

## 4. JPA và Hibernate: ánh xạ quan hệ thành đối tượng

**JPA (Jakarta Persistence, trước đây là Java Persistence API)** là một đặc tả mô tả cách ứng dụng Java ánh xạ, truy vấn và quản lý dữ liệu quan hệ dưới dạng entity. JPA quy định API và hành vi mà một persistence provider cần cung cấp; bản thân JPA không phải implementation.

**Hibernate ORM** là một ORM framework và là một trong những JPA provider phổ biến. Khi ứng dụng dùng Spring Data JPA với Hibernate, các tầng thường là:

1. Ứng dụng gọi repository hoặc EntityManager.
2. Spring Data JPA chuyển yêu cầu đến JPA provider.
3. Hibernate quản lý entity, tạo SQL và thực thi thông qua JDBC.
4. JDBC driver giao tiếp với cơ sở dữ liệu.

ORM (Object-Relational Mapping) giúp ánh xạ bảng và quan hệ trong cơ sở dữ liệu sang class và object trong Java. Hibernate cung cấp nhiều tính năng ORM như:

- Persistence context để theo dõi các entity đang được quản lý.
- Dirty checking để phát hiện thay đổi trên entity và đồng bộ khi flush.
- Mapping quan hệ như @OneToOne, @OneToMany, @ManyToOne và @ManyToMany.
- Lazy loading, cascade và các chiến lược fetch.
- JPQL, Criteria API và khả năng sinh SQL từ mô hình entity.

Ví dụ entity JPA:

~~~java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
~~~

Repository với Spring Data JPA:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByName(String name);
}
~~~

Với JPA/Hibernate, lập trình viên thường thao tác với entity và quan hệ đối tượng. Provider chịu trách nhiệm tạo SQL, theo dõi trạng thái entity và đồng bộ thay đổi với cơ sở dữ liệu. Điều này thuận tiện với domain model có nhiều quan hệ và vòng đời đối tượng phức tạp, nhưng cũng đòi hỏi hiểu rõ persistence context, fetch strategy, flush và vấn đề N+1 query.

Trong cấu hình Spring Data JPA/Hibernate phổ biến, truy vấn vẫn đi qua JDBC nên là blocking. Việc đổi kiểu trả về ở tầng service thành Mono hoặc Flux không biến Hibernate/JDBC thành reactive.

## 5. So sánh trực tiếp

| Tiêu chí | JDBC | R2DBC | JPA/Hibernate |
|---|---|---|---|
| Bản chất | API kết nối cơ sở dữ liệu | SPI kết nối reactive | Đặc tả ORM và ORM provider |
| API thường dùng | Connection, PreparedStatement, ResultSet | ConnectionFactory, Statement, Publisher | EntityManager, entity, repository |
| Kiểu I/O | Blocking | Non-blocking khi driver hỗ trợ | Thường blocking qua JDBC |
| Cách nhận kết quả | Đọc đồng bộ từ ResultSet | Mono/Flux hoặc publisher tương ứng | Đối tượng entity hoặc collection |
| Mapping | Thường tự viết hoặc nhờ thư viện | Mapping qua Spring Data R2DBC hoặc code riêng | ORM mapping theo entity |
| Theo dõi thay đổi entity | Không có persistence context ORM mặc định | Không có persistence context kiểu JPA | Có persistence context và dirty checking |
| Quan hệ object | Tự xử lý hoặc do tầng mapping hỗ trợ | Thiết kế theo aggregate, thường truy vấn tường minh | Có mapping quan hệ và fetch strategy |
| Transaction | JDBC transaction | Reactive transaction | JPA transaction, thường dựa trên JDBC |
| Tích hợp Spring thường gặp | Spring JDBC / Spring Data JDBC | Spring Data R2DBC | Spring Data JPA + Hibernate |

Điểm cần nhớ: so sánh JDBC với R2DBC là so sánh hai cách truy cập cơ sở dữ liệu ở tầng kết nối. So sánh Spring Data JDBC hoặc Spring Data R2DBC với Spring Data JPA lại là so sánh các cách tổ chức mapping và persistence ở tầng cao hơn.

## 6. Spring Data JDBC và Spring Data R2DBC khác JPA/Hibernate như thế nào?

Spring Data JDBC và Spring Data R2DBC thuộc hệ sinh thái Spring Data Relational. Hai module này chia sẻ cách tiếp cận mapping dữ liệu quan hệ theo aggregate, nhưng sử dụng cơ chế kết nối khác nhau:

- Spring Data JDBC dùng JDBC và thực thi theo kiểu blocking.
- Spring Data R2DBC dùng R2DBC và cung cấp API reactive.

Chúng thường phù hợp với mô hình domain trong đó aggregate root là ranh giới nhất quán khi ghi dữ liệu. Các đối tượng con thuộc aggregate có thể được mapping bằng những annotation của Spring Data Relational, ví dụ @MappedCollection.

Khác với JPA/Hibernate, Spring Data Relational không cung cấp persistence context theo dõi mọi entity đang được quản lý, không có dirty checking kiểu JPA và không tự động tải quan hệ theo cơ chế lazy-loading của Hibernate. Ứng dụng thường thiết kế quan hệ giữa các aggregate bằng ID và chủ động truy vấn dữ liệu cần thiết. Điều này làm hành vi SQL dễ dự đoán hơn, nhưng lập trình viên phải chủ động tổ chức các truy vấn và thao tác lưu.

Vì vậy, không nên suy luận rằng Spring Data R2DBC là “Hibernate reactive”. Spring Data R2DBC cung cấp repository và mapping trên R2DBC; nó không triển khai toàn bộ mô hình ORM và persistence context của JPA/Hibernate.

## 7. Transaction và việc kết hợp các công nghệ

Mỗi nhánh có cơ chế transaction tương ứng:

- JDBC dùng transaction của JDBC connection, thường được Spring quản lý bằng PlatformTransactionManager như JdbcTransactionManager.
- JPA dùng transaction của persistence provider, thường được Spring quản lý bằng JpaTransactionManager.
- R2DBC dùng reactive transaction, được quản lý bằng một ReactiveTransactionManager như R2dbcTransactionManager.

Với R2DBC, transaction context được truyền trong reactive pipeline. Vì vậy, các thao tác cần thuộc cùng transaction phải tiếp tục trong pipeline đó. Cần cấu hình đúng reactive transaction manager và giữ các thao tác trong phạm vi reactive transaction.

Một ứng dụng có thể cùng lúc sử dụng JDBC/JPA và R2DBC, nhưng không nên mặc định rằng một transaction sẽ tự động bao phủ cả hai. Hai nhánh thường dùng connection và transaction manager riêng. Nếu một nghiệp vụ ghi dữ liệu qua cả JPA và R2DBC, cần thiết kế tính nhất quán và xử lý lỗi rõ ràng; annotation @Transactional đơn lẻ không tự biến hai transaction độc lập thành một transaction phân tán nguyên tử.

Đặc biệt, không nên bọc lời gọi JPA/JDBC blocking trong Mono rồi kết luận rằng thao tác đã reactive:

~~~java
Mono.fromCallable(() -> jpaRepository.findById(id))
~~~

Đoạn code trên vẫn gọi một API blocking. Nếu buộc phải tích hợp trong ứng dụng reactive, cần cô lập phần blocking trên scheduler phù hợp, chẳng hạn Schedulers.boundedElastic(), đồng thời cân nhắc giới hạn tài nguyên và áp lực tải. Đây là cách cô lập blocking work, không phải biến driver JDBC thành non-blocking. Gọi block() trong luồng xử lý WebFlux cũng có thể làm mất lợi ích của mô hình reactive.

## 8. Khi nào nên chọn công nghệ nào?

| Bối cảnh | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Ứng dụng Spring MVC, xử lý request theo kiểu đồng bộ | JDBC hoặc Spring Data JDBC | Mô hình lập trình đơn giản, driver phổ biến và dễ vận hành |
| Cần viết SQL tường minh, kiểm soát truy vấn và mapping | JDBC / Spring JDBC | Chủ động câu SQL và cách chuyển kết quả |
| Domain model có nhiều quan hệ entity, cần dirty checking, cascade hoặc lazy loading | JPA/Hibernate | ORM quản lý persistence context và mapping quan hệ |
| Ứng dụng WebFlux cần xử lý nhiều I/O đồng thời và database có driver R2DBC phù hợp | R2DBC / Spring Data R2DBC | Có thể giữ pipeline non-blocking và tận dụng backpressure |
| Hệ quản trị hoặc tính năng cần dùng chưa được driver R2DBC hỗ trợ tốt | JDBC hoặc JPA/Hibernate | Tận dụng mức độ hỗ trợ và độ trưởng thành của JDBC driver |

Không có lựa chọn nào luôn nhanh hơn trong mọi hệ thống. R2DBC có thể giúp sử dụng thread hiệu quả hơn khi có nhiều request đồng thời phải chờ I/O, nhưng hiệu năng thực tế còn phụ thuộc driver, connection pool, câu SQL, schema, cách mapping và tải của cơ sở dữ liệu. Reactive cũng làm tăng độ phức tạp trong cách viết, debug và quản lý lỗi.

Nếu ứng dụng dùng Spring MVC và JDBC đáp ứng tốt tải hiện tại, chuyển sang R2DBC chỉ vì nghe nói non-blocking chưa chắc đem lại lợi ích. Ngược lại, nếu toàn bộ ứng dụng đã dùng WebFlux và cần giữ luồng xử lý non-blocking từ HTTP đến cơ sở dữ liệu, R2DBC là lựa chọn đáng cân nhắc khi driver đáp ứng yêu cầu.

## 9. Các nhầm lẫn thường gặp

**“R2DBC là phiên bản reactive của JPA.”** Không chính xác. R2DBC là SPI truy cập cơ sở dữ liệu quan hệ. Spring Data R2DBC cung cấp repository và mapping reactive, nhưng không cung cấp đầy đủ persistence context và ORM semantics của JPA/Hibernate.

**“JPA và JDBC là hai driver để kết nối database.”** Không chính xác. JDBC là API kết nối. JPA là đặc tả persistence/ORM; JPA provider như Hibernate thường dùng JDBC bên dưới.

**“Dùng Mono hoặc Flux là ứng dụng đã non-blocking.”** Không đúng nếu bên trong pipeline vẫn gọi JDBC, JPA hoặc một API blocking khác. Kiểu trả về reactive không thay đổi bản chất của thao tác I/O.

**“R2DBC luôn nhanh hơn JDBC.”** Không có bảo đảm như vậy. R2DBC thay đổi cách sử dụng thread và tổ chức luồng dữ liệu; hiệu năng phải được đo trên workload thực tế.

**“Spring Data JDBC và Spring Data R2DBC có đầy đủ tính năng như Hibernate.”** Không đúng. Spring Data Relational tập trung vào mapping và persistence theo aggregate, với cách quản lý trạng thái đơn giản hơn ORM như Hibernate.

## 10. Ghi nhớ

- **JDBC**: API kết nối cơ sở dữ liệu quan hệ của Java; thông thường blocking.
- **R2DBC**: SPI truy cập cơ sở dữ liệu quan hệ theo mô hình reactive; non-blocking khi driver và pipeline hỗ trợ.
- **JPA**: đặc tả persistence và ORM; không phải driver.
- **Hibernate**: ORM provider phổ biến triển khai JPA; trong ứng dụng Spring thông thường, Hibernate thực thi SQL qua JDBC và vì vậy blocking.
- **Spring Data JDBC** và **Spring Data R2DBC**: cùng hướng tiếp cận Spring Data Relational theo aggregate, nhưng khác tầng kết nối và kiểu thực thi.
- Chọn công nghệ dựa trên kiến trúc ứng dụng, yêu cầu mapping, khả năng của driver và tải thực tế; không chọn chỉ dựa trên nhãn reactive hoặc giả định hiệu năng.
