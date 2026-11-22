# Dùng chung DataSource, giao dịch và kiểm thử tính nhất quán

Khi một ứng dụng sử dụng đồng thời **MyBatis** và **Spring Data Relational JDBC**, hai framework có thể đọc và ghi cùng một database. Để một use case gồm nhiều thao tác có tính nguyên tử, MyBatis mapper, Spring Data JDBC repository và các JDBC template phải tham gia **cùng một transaction Spring**.

Có ba điều kiện chính:

1. MyBatis và Spring Data JDBC được cấu hình với cùng một **DataSource**.
2. Cả hai sử dụng cùng **PlatformTransactionManager** quản lý DataSource đó.
3. MyBatis dùng tích hợp Spring (**SqlSessionTemplate** và **SpringManagedTransactionFactory**), còn service mở transaction qua **@Transactional**.

Khi cấu hình đúng, một method service có thể lưu aggregate bằng Spring Data JDBC, cập nhật bảng khác bằng MyBatis và ghi audit bằng **JdbcTemplate**. Các thay đổi sẽ cùng commit hoặc rollback theo transaction boundary.

Tuy nhiên, cùng transaction chỉ đảm bảo tính nhất quán ở database. Hai framework vẫn có mapping, converter, cache và lifecycle riêng. MyBatis update trực tiếp một bảng không tự chạy aggregate callbacks, auditing hay optimistic locking của Spring Data JDBC; cache của MyBatis cũng không tự biết một repository đã sửa dữ liệu.

## 1. Kiến trúc tích hợp

Giả sử một use case đặt hàng cần:

- Lưu aggregate **PurchaseOrder** bằng Spring Data JDBC.
- Trừ tồn kho bằng MyBatis mapper.
- Ghi một dòng audit bằng MyBatis hoặc JdbcTemplate.

~~~mermaid
flowchart TD
    A["PlaceOrderService<br/>@Transactional"] --> B["PurchaseOrderRepository<br/>Spring Data JDBC"]
    A --> C["InventoryMapper<br/>MyBatis-Spring"]
    A --> D["OrderAuditMapper<br/>MyBatis-Spring"]
    B --> E["DataSource"]
    C --> E
    D --> E
    E --> F["Connection được bind vào transaction"]
    F --> G["JdbcTransactionManager"]
    G --> H["COMMIT hoặc ROLLBACK"]
~~~

Cả hai framework đều là client của cùng database và cùng DataSource. Transaction manager không cần biết câu SQL do Spring Data JDBC hay MyBatis tạo ra; nó quản lý JDBC connection và transaction resource.

**Cùng JDBC URL chưa đủ để chứng minh cùng transaction.** Hai connection pool riêng biệt, dù trỏ đến cùng URL/database, vẫn là hai DataSource/resource khác nhau. Hãy dùng cùng một bean DataSource cho repository infrastructure, MyBatis SqlSessionFactory và transaction manager.

## 2. Cấu hình DataSource dùng chung

Với Spring Boot, thường chỉ cần khai báo một DataSource:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/sales
    username: app
    password: secret-from-environment
    driver-class-name: org.postgresql.Driver
~~~

Dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.mybatis.spring.boot</groupId>
    <artifactId>mybatis-spring-boot-starter</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Dùng phiên bản MyBatis Spring Boot Starter tương thích với phiên bản Spring Boot của ứng dụng; để dependency management của Spring Boot quản lý các phiên bản Spring Framework/Spring Data thay vì nâng riêng từng thư viện tùy tiện.

Nếu dùng starter, MyBatis có thể tự cấu hình **SqlSessionFactory**, **SqlSessionTemplate** và mapper scanning từ DataSource Spring Boot. Không khai báo lại các bean đó nếu auto-configuration đã tạo đúng cấu hình.

### Cấu hình Java tường minh khi không dùng auto-configuration

Ví dụ cấu hình một DataSource, transaction manager và MyBatis factory:

~~~java
@Configuration
@EnableTransactionManagement
@MapperScan("com.example.persistence.mybatis")
public class PersistenceConfiguration {

    @Bean
    public DataSource dataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://localhost:5432/sales")
                .username("app")
                .password(System.getenv("DB_PASSWORD"))
                .driverClassName("org.postgresql.Driver")
                .build();
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource)
            throws Exception {
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setTransactionFactory(new SpringManagedTransactionFactory());
        return factory.getObject();
    }
}
~~~

Các import MyBatis/Spring quan trọng:

~~~java
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.annotation.MapperScan;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.apache.ibatis.session.SqlSessionFactory;

import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
~~~

Trong ví dụ dùng **JdbcTransactionManager**. Có thể dùng **DataSourceTransactionManager** thay thế nếu phù hợp. JdbcTransactionManager được giới thiệu trong Spring Framework 5.3 và kế thừa DataSourceTransactionManager; nó bổ sung dịch SQLException ở bước commit/rollback. DataSourceTransactionManager vẫn có thể phối hợp với MyBatis-Spring khi dùng đúng DataSource và transaction factory.

**SqlSessionFactoryBean** mặc định dùng **SpringManagedTransactionFactory**; khai báo tường minh trong ví dụ nhằm làm rõ yêu cầu tích hợp. Không thay nó bằng transaction factory JDBC độc lập nếu muốn session tham gia transaction Spring.

Với Spring Boot, cấu hình thủ công chỉ cần thiết khi muốn kiểm soát factory/mapper scan hoặc đã tắt auto-configuration. Tránh tạo hai SqlSessionFactory, hai DataSource hay hai transaction manager cùng quản lý một nhóm mapper ngoài ý muốn.

## 3. MyBatis-Spring tham gia transaction Spring như thế nào?

MyBatis-Spring cung cấp hai thành phần quan trọng:

- **SqlSessionTemplate** là implementation SqlSession an toàn khi dùng với Spring. Nó quản lý vòng đời session và phối hợp với transaction synchronization.
- **SpringManagedTransactionFactory** tạo transaction adapter sử dụng transaction do Spring quản lý thay vì tự commit độc lập.

Khi một method **@Transactional** bắt đầu:

1. Transaction manager lấy connection từ DataSource và bind connection với transaction hiện tại.
2. Spring Data JDBC repository lấy connection tương ứng khi thực hiện SQL.
3. Mapper MyBatis được gọi qua SqlSessionTemplate; MyBatis-Spring tìm session gắn với transaction hiện tại.
4. Session MyBatis dùng connection của DataSource đang được transaction Spring quản lý.
5. Khi service kết thúc, transaction manager commit hoặc rollback.
6. MyBatis-Spring đồng bộ trạng thái session và giải phóng tài nguyên theo transaction lifecycle.

Bạn không cần tự truyền Connection từ repository sang mapper. Việc chia sẻ diễn ra qua Spring transaction infrastructure và DataSource identity.

### Dùng mapper proxy thay vì mở SqlSession thủ công

Mapper interface:

~~~java
@Mapper
public interface InventoryMapper {

    @Update("""
        UPDATE inventory
        SET available = available - #{quantity}
        WHERE product_id = #{productId}
          AND available >= #{quantity}
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

Spring tạo mapper proxy và gọi MyBatis thông qua session template. Không tự gọi **SqlSessionFactory.openSession()** trong service để chạy mapper nếu muốn tích hợp transaction Spring. Session tự mở như vậy có thể nằm ngoài session/transaction được Spring đồng bộ.

Không gọi **commit()**, **rollback()** hoặc **close()** thủ công trên session do SqlSessionTemplate quản lý. Hãy để transaction manager điều khiển transaction.

## 4. Đặt transaction boundary ở application service

Transaction boundary nên bao trùm toàn bộ use case cần atomicity, thay vì để từng repository/mapper tự commit riêng.

Ví dụ aggregate root:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    private String status;

    // constructor, getters, domain methods...
}
~~~

Spring Data JDBC repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

MyBatis mapper:

~~~java
@Mapper
public interface InventoryMapper {

    @Update("""
        UPDATE inventory
        SET available = available - #{quantity}
        WHERE product_id = #{productId}
          AND available >= #{quantity}
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

Mapper ghi audit:

~~~java
@Mapper
public interface OrderAuditMapper {

    @Insert("""
        INSERT INTO order_audit(order_id, event_type)
        VALUES (#{orderId}, #{eventType})
        """)
    int insert(
            @Param("orderId") Long orderId,
            @Param("eventType") String eventType
    );
}
~~~

Service điều phối:

~~~java
@Service
public class PlaceOrderService {

    private final PurchaseOrderRepository orderRepository;
    private final InventoryMapper inventoryMapper;
    private final OrderAuditMapper auditMapper;

    public PlaceOrderService(
            PurchaseOrderRepository orderRepository,
            InventoryMapper inventoryMapper,
            OrderAuditMapper auditMapper) {
        this.orderRepository = orderRepository;
        this.inventoryMapper = inventoryMapper;
        this.auditMapper = auditMapper;
    }

    @Transactional
    public Long place(PurchaseOrder order, Long productId, int quantity) {
        PurchaseOrder saved = orderRepository.save(order);

        int reserved = inventoryMapper.reserve(productId, quantity);
        if (reserved != 1) {
            throw new InsufficientStockException(productId);
        }

        auditMapper.insert(saved.getId(), "ORDER_CREATED");

        return saved.getId();
    }
}
~~~

Nếu reserve() trả về 0, exception runtime thoát khỏi method transactional. Transaction rollback cả thao tác lưu PurchaseOrder lẫn thao tác MyBatis đã thực hiện trước đó. Audit insert chỉ xảy ra khi reserve thành công.

**@Transactional** mặc định rollback với RuntimeException và Error. Nếu service ném checked exception mà vẫn phải rollback, khai báo rollbackFor:

~~~java
@Transactional(rollbackFor = OrderProcessingException.class)
public Long place(...) throws OrderProcessingException {
    // ...
}
~~~

Không bắt exception rồi nuốt lỗi bên trong service nếu nghiệp vụ yêu cầu rollback. Nếu cần chuyển exception, hãy bảo đảm exception thoát khỏi transaction boundary hoặc đánh dấu rollback-only theo cách phù hợp.

## 5. Đọc dữ liệu do framework còn lại vừa ghi

Khi hai framework tham gia cùng transaction và dùng cùng connection, transaction có thể đọc các thay đổi mà chính nó vừa thực hiện (read-your-writes).

Ví dụ MyBatis cập nhật trạng thái, sau đó Spring Data JDBC đọc aggregate:

~~~java
@Transactional
public PurchaseOrder changeStatusAndRead(Long orderId) {
    int updated = orderMapper.changeStatus(orderId, "READY");

    if (updated != 1) {
        throw new OrderNotFoundException(orderId);
    }

    return orderRepository.findById(orderId).orElseThrow();
}
~~~

Ngược lại, Spring Data JDBC có thể lưu root rồi MyBatis mapper đọc lại trong cùng transaction:

~~~java
@Transactional
public OrderRow createAndRead(PurchaseOrder order) {
    PurchaseOrder saved = orderRepository.save(order);
    return orderMapper.findRow(saved.getId());
}
~~~

Các câu SQL được thực thi ngay trong JDBC transaction; Spring Data JDBC không giữ một persistence context kiểu JPA để chờ flush ở cuối transaction. Vì vậy, mapper có thể đọc thay đổi đã được repository ghi trước đó trên cùng transaction connection.

Điều này không có nghĩa transaction khác nhìn thấy dữ liệu chưa commit. Transaction khác vẫn tuân theo isolation level của database. Với READ_COMMITTED, transaction khác thường chỉ thấy thay đổi sau commit; với REPEATABLE_READ hoặc SERIALIZABLE, snapshot/locking semantics phụ thuộc database.

## 6. Kiểm thử rollback giữa Spring Data JDBC và MyBatis

Kiểm thử quan trọng nhất là xác nhận cả hai framework cùng rollback khi một bước thất bại.

Một service test-only hoặc một use case có thể chủ động ném exception sau khi đã ghi qua cả hai framework:

~~~java
@Service
public class ConsistencyTestService {

    private final PurchaseOrderRepository orderRepository;
    private final OrderAuditMapper auditMapper;

    public ConsistencyTestService(
            PurchaseOrderRepository orderRepository,
            OrderAuditMapper auditMapper) {
        this.orderRepository = orderRepository;
        this.auditMapper = auditMapper;
    }

    @Transactional
    public void createThenFail(PurchaseOrder order) {
        PurchaseOrder saved = orderRepository.save(order);
        auditMapper.insert(saved.getId(), "CREATED");
        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Integration test:

~~~java
@SpringBootTest
class SharedTransactionIntegrationTest {

    @Autowired ConsistencyTestService service;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void repositoryAndMyBatisWritesRollbackTogether() {
        assertThatThrownBy(() -> service.createThenFail(
                new PurchaseOrder(42L, "DRAFT")
        )).isInstanceOf(IllegalStateException.class);

        Integer orderCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE customer_id = ?",
                Integer.class,
                42L
        );

        Integer auditCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM order_audit WHERE event_type = ?",
                Integer.class,
                "CREATED"
        );

        assertThat(orderCount).isZero();
        assertThat(auditCount).isZero();
    }
}
~~~

Test này nên chạy với database thật tương thích production, chẳng hạn PostgreSQL Testcontainers. Không đánh dấu chính test method **@Transactional** nếu mục tiêu là xác nhận transaction service đã rollback trước khi assertion chạy; transaction ngoài của test có thể làm khó phân biệt transaction nào đang được kiểm tra.

### Kiểm tra commit thành công

Thêm test cho trường hợp không ném exception:

- Repository lưu aggregate.
- MyBatis mapper ghi audit hoặc cập nhật inventory.
- Service kết thúc bình thường.
- Một truy vấn độc lập sau khi service trả về xác nhận cả hai thay đổi đã commit.

### Kiểm tra read-your-writes hai chiều

Nên có các trường hợp:

1. Spring Data JDBC insert/update, MyBatis SELECT cùng transaction.
2. MyBatis UPDATE, Spring Data JDBC SELECT cùng transaction.
3. Cả hai cùng cập nhật trong một service transaction.
4. Một thao tác vi phạm constraint sau khi framework kia đã ghi; xác nhận toàn bộ transaction rollback.

**@MybatisTest** thường chỉ nạp MyBatis slice và không tự đại diện cho đầy đủ Spring Data JDBC repositories. Để kiểm tra composition thực tế, dùng **@SpringBootTest** hoặc cấu hình integration test bao gồm cả hai infrastructure.

## 7. Dùng Testcontainers để kiểm tra trên cùng database engine

H2 có thể hữu ích cho test nhanh, nhưng nếu production dùng PostgreSQL/MySQL/SQL Server, nên chạy integration test với đúng database engine và driver. Testcontainers giúp khởi chạy database tạm thời cho test.

Ví dụ PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class SharedDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("sales")
                    .withUsername("app")
                    .withPassword("secret");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
                postgres::getDriverClassName);
    }
}
~~~

Bổ sung migration Flyway/Liquibase hoặc schema SQL để tạo các bảng purchase_order, inventory và order_audit. Khi test, xác nhận MyBatis và Spring Data JDBC nhận cùng DataSource bean do Spring Boot cấu hình.

Đừng chỉ assert hai bean có cùng JDBC URL. Bằng chứng chức năng mạnh hơn là kiểm thử rollback: ghi qua framework thứ nhất, ghi qua framework thứ hai, ném exception, rồi xác nhận không thay đổi nào còn tồn tại sau khi transaction kết thúc.

## 8. Cache MyBatis có thể làm dữ liệu đọc bị cũ

Cùng DataSource và transaction không tự đồng bộ cache của hai framework.

MyBatis có:
- **Local cache cấp SqlSession** (first-level cache), mặc định có scope SESSION.
- **Second-level cache** theo mapper namespace nếu được bật và cấu hình.

Spring Data JDBC không biết mapper namespace/cache nào đã giữ kết quả. Vì vậy, nếu MyBatis SELECT một hàng, rồi Spring Data JDBC UPDATE hàng đó, một SELECT MyBatis tiếp theo trong cùng SqlSession có thể trả dữ liệu local cache cũ thay vì chạy SQL mới.

Tương tự, nếu MyBatis second-level cache chứa dữ liệu của bảng được Spring Data JDBC sửa, Spring Data JDBC không tự invalidate cache MyBatis đó.

Các cách xử lý:

- Với bảng được cả hai framework ghi, cân nhắc tắt MyBatis second-level cache cho mapper/table đó.
- Cân nhắc **localCacheScope=STATEMENT** nếu use case yêu cầu truy vấn MyBatis luôn đọc lại database giữa các statement.
- Dùng **flushCache** cho các query cần bỏ cache theo khả năng MyBatis.
- Chủ động clear/evict cache khi một đường ghi khác framework thay đổi dữ liệu, nếu vẫn cần cache.
- Tránh dùng cache dài hạn cho dữ liệu mutable được cập nhật bởi nhiều persistence mechanism nếu không có invalidation protocol rõ ràng.

Ví dụ cấu hình MyBatis:

~~~yaml
mybatis:
  configuration:
    local-cache-scope: STATEMENT
~~~

STATEMENT giảm việc tái sử dụng local cache qua nhiều statement; nó không tự vô hiệu hóa mọi second-level cache. Nếu mapper bật namespace cache, cần quản lý cache đó riêng.

### Transaction consistency và cache consistency là hai vấn đề khác nhau

| Lớp | Được đảm bảo bởi cùng transaction? |
|---|---|
| SQL update qua MyBatis | Có, nếu dùng cùng transaction resource |
| SQL update qua Spring Data JDBC | Có, nếu dùng cùng transaction resource |
| Commit/rollback giữa hai framework | Có, khi cùng manager/DataSource |
| Object Java đã tải trước đó | Không tự đồng bộ |
| MyBatis local cache | Không tự được Spring Data JDBC invalidation |
| MyBatis second-level cache | Không tự được Spring Data JDBC invalidation |
| Cache ngoài như Redis | Không tự tham gia JDBC transaction |

Sau khi một framework ghi dữ liệu, hãy reload object/cache khi cần trạng thái mới. Transaction không biến hai object graph hoặc hai cache thành một vùng nhớ chung.

## 9. Aggregate lifecycle và @Version không được chia sẻ tự động

Spring Data JDBC lưu aggregate theo mapping và lifecycle của nó. Khi dùng **repository.save(root)**, framework có thể xử lý:

- Aggregate root và các entity được sở hữu.
- Entity callbacks và lifecycle events.
- Auditing fields nếu đã cấu hình.
- Optimistic locking thông qua **@Version**.

MyBatis mapper thực thi SQL theo mapping riêng. Một câu UPDATE MyBatis trên bảng aggregate không tự gọi các callback Spring Data JDBC, không tự cập nhật **@LastModifiedDate**, và không tự tăng **@Version**.

Ví dụ entity:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

Nếu MyBatis cập nhật trực tiếp bảng này:

~~~java
@Update("""
    UPDATE purchase_order
    SET status = #{status}
    WHERE id = #{id}
    """)
int changeStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

version không tăng. Một aggregate đã được tải trước đó có thể vẫn giữ version cũ và sau đó được Spring Data JDBC lưu lại mà không phát hiện lần ghi MyBatis. Điều này có thể ghi đè dữ liệu mới.

Nếu buộc phải cập nhật root bằng MyBatis, cần tự áp dụng optimistic locking:

~~~java
@Update("""
    UPDATE purchase_order
    SET status = #{status},
        version = version + 1
    WHERE id = #{id}
      AND version = #{expectedVersion}
    """)
int changeStatus(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("expectedVersion") Long expectedVersion
);
~~~

Nếu update count bằng 0, version không còn khớp hoặc ID không tồn tại. Application service cần xử lý conflict. Sau khi mapper cập nhật, object Spring Data JDBC đã tải trước đó phải được reload hoặc cập nhật trạng thái version một cách có kiểm soát.

### Chọn quyền sở hữu đường ghi

Một quy ước hữu ích:

- Spring Data JDBC là đường ghi chính cho aggregate root và owned entities.
- MyBatis dùng cho truy vấn phức tạp, projection/DTO, báo cáo và các bảng phụ không thuộc aggregate lifecycle.
- Nếu MyBatis cần ghi bảng aggregate, phải định nghĩa rõ quy tắc version, auditing, invariant và cache invalidation.
- Không để hai framework tùy ý cập nhật cùng aggregate mà không có write protocol.

Việc dùng chung transaction không thay thế ranh giới aggregate và domain rule.

## 10. MyBatis TypeHandler và Spring Data Converter là hai hệ riêng

Spring Data JDBC dùng conversion infrastructure của Spring Data, ví dụ **@ReadingConverter** và **@WritingConverter**. MyBatis dùng **TypeHandler** để chuyển Java type thành JDBC parameter và đọc JDBC result.

Hai framework không tự chia sẻ converter:

| Nhu cầu | Spring Data JDBC | MyBatis |
|---|---|---|
| Java value object ↔ SQL scalar | Converter, JdbcCustomConversions | TypeHandler<T> |
| Đổi tên cột | @Column hoặc naming strategy | SQL alias, resultMap, @Results |
| Mapping quan hệ | Aggregate mapping, @MappedCollection, AggregateReference | SQL JOIN và result mapping do mapper khai báo |
| Optimistic version | @Version trong aggregate lifecycle | SQL mapper phải tự kiểm tra/tăng version |
| Cache | Không có persistence context cache kiểu JPA mặc định | Local/second-level cache theo cấu hình MyBatis |

Nếu domain dùng **EmailAddress**, Spring Data JDBC có thể dùng converter EmailAddress ↔ String; MyBatis mapper vẫn cần **TypeHandler<EmailAddress>** nếu mapper nhận/trả trực tiếp kiểu đó. Nếu mapper dùng String, chuyển đổi có thể diễn ra ở application layer.

Đừng giả định **@Column("email_address")** ảnh hưởng câu SQL hoặc result mapping của MyBatis. SQL và resultMap của MyBatis cần khai báo tên cột theo schema.

## 11. Generated ID và dữ liệu được chia sẻ

Hai framework có thể thao tác cùng bảng identity/sequence, nhưng cách lấy generated key được cấu hình riêng.

Spring Data JDBC dùng mapping/dialect và ID generation infrastructure của nó. MyBatis thường dùng **useGeneratedKeys/keyProperty** hoặc sequence SQL phù hợp với database.

Ví dụ MyBatis insert:

~~~java
@Insert("""
    INSERT INTO order_audit(order_id, event_type)
    VALUES (#{orderId}, #{eventType})
    """)
@Options(useGeneratedKeys = true, keyProperty = "id")
int insertAudit(AuditRecord record);
~~~

Nếu MyBatis insert một row có generated ID, key được ghi vào property đã cấu hình của parameter object theo JDBC driver và MyBatis. Nếu Spring Data JDBC insert aggregate, ID được gán theo mapping của Spring Data JDBC.

Các điểm cần kiểm tra:

- Cả hai dùng đúng bảng/sequence/identity của cùng database.
- Không tự cấp ID trùng với dải ID database đang sinh.
- Với PostgreSQL sequence, nếu ứng dụng tự cấp ID thủ công, sequence cần được đồng bộ theo chiến lược migration/maintenance.
- Test generated keys trên driver production; H2 có thể có behavior khác.

## 12. Transaction propagation và thread boundary

**@Transactional** dùng propagation mặc định REQUIRED: method mapper/repository được gọi trong service transaction sẽ tham gia transaction hiện tại khi cùng transaction manager/resource.

| Propagation | Hành vi trong tích hợp MyBatis + Spring Data JDBC |
|---|---|
| REQUIRED | Dùng chung transaction hiện tại; phù hợp cho phần lớn use case |
| REQUIRES_NEW | Tạm treo transaction ngoài và mở transaction mới; có thể cần connection thứ hai |
| SUPPORTS | Tham gia nếu có transaction; nếu không thì chạy không transaction |
| MANDATORY | Yêu cầu caller đã mở transaction |
| NESTED | Dùng savepoint nếu transaction manager/database hỗ trợ |

Không dùng REQUIRES_NEW chỉ để “làm cho MyBatis có transaction riêng” nếu nghiệp vụ cần cả hai framework rollback cùng nhau. Transaction mới có thể commit độc lập trong khi transaction ngoài rollback.

Transaction JDBC gắn với thread. Nếu service gọi @Async, executor hoặc tạo thread mới, transaction hiện tại không tự truyền sang worker thread. Worker cần transaction riêng.

**@Transactional** được áp dụng qua Spring proxy. Self-invocation — một method trong class gọi trực tiếp method khác cùng class — không đi qua proxy và không tạo transaction interceptor mới như mong đợi. Đặt transaction ở method use case được gọi từ bean khác hoặc tách service.

## 13. Nhiều DataSource không phải một transaction chung

Nếu ứng dụng có hai database:

~~~text
ordersDataSource
  ├── Spring Data JDBC repositories
  ├── MyBatis orders SqlSessionFactory
  └── ordersTransactionManager

reportingDataSource
  ├── MyBatis reporting SqlSessionFactory
  └── reportingTransactionManager
~~~

Cần tạo SqlSessionFactory, mapper scan và transaction manager tương ứng cho từng DataSource. **@Transactional("ordersTransactionManager")** chỉ quản lý resource của orders database.

Hai DataSource cùng JDBC URL nhưng là hai pool riêng cũng không tự chia sẻ connection transaction. Một local transaction manager không thể commit/rollback nguyên tử hai resource độc lập.

Nếu một use case phải ghi cả hai database, lựa chọn gồm:

- Distributed transaction/XA/JTA nếu hạ tầng và database hỗ trợ, và yêu cầu atomicity thật sự cần thiết.
- Transactional outbox kết hợp consumer/worker.
- Saga/compensation cho workflow nhiều service/database.

Không đặt hai DataSource vào cùng một service rồi giả định một @Transactional mặc định điều phối cả hai.

## 14. Những lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Repository rollback nhưng MyBatis insert vẫn còn | MyBatis dùng DataSource/transaction factory khác hoặc session tự mở | Dùng cùng DataSource và MyBatis-Spring SqlSessionTemplate |
| MyBatis mapper commit trước khi service kết thúc | Dùng MyBatis session/JDBC transaction độc lập | Dùng mapper proxy qua SqlSessionTemplate; không tự commit |
| JdbcTemplate rollback nhưng mapper không rollback | SqlSessionFactory không dùng cùng DataSource hoặc không dùng SpringManagedTransactionFactory | Kiểm tra factory và transaction manager |
| Có hai transaction manager và chọn nhầm | Nhiều DataSource hoặc nhiều manager bean | Dùng qualifier/transaction manager name rõ ràng |
| Cùng URL nhưng không cùng transaction | Hai pool/DataSource object độc lập | Dùng chung một DataSource bean |
| MyBatis SELECT trả dữ liệu cũ sau repository UPDATE | Local/second-level cache MyBatis chưa invalidated | Giảm cache scope, disable/flush cache hoặc quản lý eviction |
| MyBatis UPDATE làm mất optimistic locking | Mapper không kiểm tra/tăng version | Đưa expected version vào WHERE và tăng version trong SQL |
| Spring Data JDBC ghi đè thay đổi MyBatis | Aggregate object đang giữ trạng thái cũ/version không đổi | Reload aggregate; thiết lập write protocol và version |
| MyBatis không map được custom value object | Thiếu MyBatis TypeHandler | Đăng ký TypeHandler riêng hoặc chuyển qua scalar |
| Test MyBatis pass nhưng repository không được nạp | Dùng @MybatisTest slice mà không import Spring Data JDBC | Dùng @SpringBootTest hoặc cấu hình test tích hợp cả hai |
| Rollback test cho kết quả khó hiểu | Test method cũng mở transaction ngoài | Để test không transactional hoặc kiểm soát commit/rollback rõ ràng |
| @Transactional không có hiệu lực | Self-invocation hoặc gọi object tự tạo | Gọi qua Spring bean proxy |

## 15. Checklist kiểm thử tính nhất quán

Một integration test suite nên kiểm tra các hành vi sau:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Spring Data JDBC save, MyBatis SELECT trong cùng transaction | Mapper đọc được dữ liệu vừa lưu nếu cache không che kết quả |
| MyBatis UPDATE, Spring Data JDBC SELECT trong cùng transaction | Repository đọc được thay đổi đã commit trong cùng transaction connection |
| Repository write + MyBatis write + runtime exception | Cả hai thay đổi rollback |
| Repository write + MyBatis write + method kết thúc bình thường | Cả hai thay đổi commit |
| MyBatis UPDATE một aggregate có @Version | Version được kiểm tra/tăng theo write protocol đã thiết kế |
| Spring Data JDBC UPDATE sau MyBatis UPDATE | Không ghi đè dữ liệu do object stale/version không đổi |
| MyBatis cache bật và Spring Data JDBC ghi | Cache invalidation được kiểm soát, không trả stale data |
| Hai DataSource riêng | Không kỳ vọng một local transaction manager rollback cả hai |

Khi test rollback, hãy xác nhận dữ liệu bằng một truy vấn độc lập sau khi service transaction kết thúc. Khi test cache, tạo đúng chuỗi thao tác: MyBatis SELECT, Spring Data JDBC UPDATE, MyBatis SELECT lại trong cùng transaction/session. Chỉ test SQL commit/rollback sẽ không phát hiện cache stale.

## 16. Quy trình triển khai tích hợp

1. **Chọn một DataSource dùng chung:** cấu hình Spring Data JDBC, MyBatis và transaction manager với cùng bean.
2. **Cấu hình MyBatis-Spring:** dùng SqlSessionFactoryBean, SpringManagedTransactionFactory và mapper proxy/SqlSessionTemplate.
3. **Chọn transaction manager:** JdbcTransactionManager hoặc DataSourceTransactionManager quản lý đúng DataSource.
4. **Đặt transaction ở service:** dùng @Transactional cho use case phối hợp repository và mapper.
5. **Xác định write ownership:** quy định framework nào chịu trách nhiệm ghi aggregate root/child.
6. **Quản lý version/auditing:** MyBatis DML trên aggregate phải tự tuân thủ version và audit nếu cần.
7. **Kiểm tra cache:** tránh cache stale khi Spring Data JDBC sửa dữ liệu mà MyBatis mapper đã cache.
8. **Kiểm thử rollback:** gây exception sau khi cả hai framework đã ghi và xác nhận không có thay đổi nào được commit.
9. **Kiểm thử read-your-writes:** xác nhận dữ liệu có thể đọc chéo framework trong cùng transaction.
10. **Dùng database production-compatible:** Testcontainers giúp kiểm tra driver, generated keys, transaction và SQL trên đúng engine.

### Bảng quyết định nhanh

| Yêu cầu | Hướng triển khai |
|---|---|
| MyBatis và Spring Data JDBC cùng commit/rollback | Cùng DataSource, cùng transaction manager, MyBatis-Spring |
| MyBatis mapper dùng transaction Spring | SqlSessionTemplate và SpringManagedTransactionFactory |
| Phối hợp nhiều thao tác trong một use case | @Transactional ở application service |
| MyBatis đọc dữ liệu repository vừa ghi | Cùng transaction connection; kiểm tra cache |
| MyBatis ghi bảng aggregate | Quản lý invariant, callbacks/auditing và @Version rõ ràng |
| Hai framework dùng custom Java type | Spring Data Converter và MyBatis TypeHandler riêng |
| Cần xác nhận atomicity | Integration test gây lỗi giữa hai thao tác và kiểm tra rollback |
| Hai database độc lập | Transaction manager riêng; XA/outbox/saga nếu cần phối hợp |

**Điểm cốt lõi:** MyBatis và Spring Data JDBC có thể dùng chung transaction khi cùng dùng một DataSource, cùng transaction manager và MyBatis-Spring quản lý session. Đặt transaction boundary ở application service để nhiều thao tác commit/rollback cùng nhau. Sau đó xử lý riêng các khác biệt về cache, mapping, aggregate lifecycle và optimistic locking; database transaction không tự đồng bộ những trạng thái ở tầng framework/application.

## Tài liệu tham khảo chính thức

- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html): cách MyBatis-Spring tham gia transaction Spring và yêu cầu dùng cùng DataSource.
- [MyBatis-Spring — SqlSession](https://mybatis.org/spring/sqlsession.html): SqlSessionTemplate, quản lý session và tích hợp transaction.
- [MyBatis-Spring — SqlSessionFactoryBean](https://mybatis.org/spring/factorybean.html): cấu hình SqlSessionFactoryBean, DataSource và transaction factory.
- [MyBatis — Configuration](https://mybatis.org/mybatis-3/configuration.html): local cache, second-level cache và localCacheScope.
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): DataSourceUtils, connection reuse và transaction-aware DataSource.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction manager, propagation và declarative transactions.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction behavior của Spring Data JDBC repository và service layer.
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): version property và phát hiện cập nhật đồng thời.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): integration test với PostgreSQL container.

