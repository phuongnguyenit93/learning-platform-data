# readOnly là tín hiệu tối ưu và cần xác minh tác động thực tế

Trong ứng dụng Spring sử dụng Hibernate, annotation `@Transactional(readOnly = true)` xuất hiện rất thường xuyên ở các phương thức truy vấn. Tên gọi dễ gây hiểu nhầm rằng **mọi thao tác ghi trong phương thức đó sẽ luôn bị từ chối**. Cách hiểu đó không đúng như một cam kết tổng quát.

**Ý tưởng cốt lõi:** Trong Spring, `readOnly` trước hết là **tín hiệu về ý định của transaction**. Spring transaction manager và các thành phần bên dưới *có thể* dùng tín hiệu để tối ưu flush/dirty checking, chuyển flag xuống JDBC connection, hoặc cưỡng chế read-only transaction ở database nếu đã được cấu hình và hỗ trợ. Hiệu quả, khả năng ngăn ghi và chi phí thực tế phụ thuộc bộ phiên bản **Spring + Hibernate + JDBC driver + DBMS**, transaction manager, propagation và workload.

Ví dụ một service truy vấn:

~~~java
@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    public ProductView find(Long id) {
        Product product = products.findById(id)
            .orElseThrow();

        return new ProductView(
            product.getId(),
            product.getName(),
            product.getPrice()
        );
    }
}
~~~

Method thể hiện ý định chỉ đọc; nó không tự làm SQL `SELECT` nhanh hơn, không tự thêm `LIMIT` hoặc tránh N+1 queries, và **không được coi là cơ chế bảo mật cấm ghi**.

> **Phạm vi:** Bài lấy Spring Framework 6.x, Spring Data JPA, Hibernate ORM 6.x, Jakarta Persistence, Java 17+ làm bối cảnh. Một số behavior đã thay đổi qua các phiên bản Spring/Hibernate. `@Transactional` ở đây là `org.springframework.transaction.annotation.Transactional` — annotation Spring có thuộc tính `readOnly`, không nhầm với `jakarta.transaction.Transactional`.

## 1. Mục tiêu và vấn đề thực tế

Sau bài này, bạn có thể:

- Giải thích `readOnly` là transaction hint, không phải bảo đảm SQL DML luôn bị chặn.
- Phân biệt read-only ở Spring, Hibernate Session, Hibernate Query, JDBC và database.
- Hiểu các tối ưu có thể có đối với **flush mode, dirty checking và loaded-state snapshots**.
- Dự đoán ảnh hưởng của **transaction propagation**, self-invocation và việc dùng nhiều transaction managers.
- Biết khi nào nên dùng `@Transactional(readOnly = true)` trong Spring Data JPA.
- Xây dựng phép đo/kiểm thử xác nhận tác động thực tế trên DB production-like.
- Tránh nhầm annotation với database permissions, isolation level hoặc read-replica routing.

## 2. Mô hình domain minh họa

Entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "product")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public long getVersion() { return version; }

    public void rename(String value) { this.name = value; }
    public void changePrice(BigDecimal value) { this.price = value; }
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

DTO:

~~~java
public record ProductView(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Bảng database ví dụ:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(15,2) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Các thao tác đọc/ghi trong bài đều dựa trên entity này. Với schema thực tế, cột/ID generator/auditing có thể khác; mục đích là làm rõ semantics của transaction.

## 3. @Transactional(readOnly=true) nghĩa gì?

Spring định nghĩa readOnly trong metadata transaction. Khi một phương thức được transaction interceptor xử lý, transaction manager nhận một `TransactionDefinition` với flag read-only.

~~~java
@Transactional(readOnly = true)
public ProductView show(Long id) {
    Product p = products.findById(id).orElseThrow();
    return new ProductView(p.getId(), p.getName(), p.getPrice());
}
~~~

Những thành phần tham gia có thể:

1. Điều chỉnh flush mode của Hibernate Session.
2. Đặt Hibernate Session/default entity load ở read-only mode.
3. Gọi JDBC `Connection.setReadOnly(true)`.
4. Thiết lập database transaction read-only trên DB hỗ trợ.
5. Dùng flag để routing sang read replica — **chỉ nếu application đã cấu hình routing**.

Không có cam kết mọi thứ trên sẽ đồng thời xảy ra. Một transaction manager có thể chỉ xử lý một phần, một driver có thể chỉ xem flag là hint, và một transaction đã tồn tại có thể giữ config của transaction ngoài.

## 4. Các lớp read-only không giống nhau

| Lớp | Ví dụ | Ý nghĩa |
|---|---|---|
| Spring Transaction | `@Transactional(readOnly = true)` | Ý định của transaction, chuyển đến transaction manager. |
| Hibernate Session | `session.setDefaultReadOnly(true)` | Entity loads mới có thể bỏ một phần dirty checking/snapshot. |
| Hibernate Query | `query.setReadOnly(true)` | Áp dụng read-only semantics cho kết quả entity query. |
| JDBC Connection | `connection.setReadOnly(true)` | Flag/hint ở driver connection, khả năng enforce tùy DB. |
| Database transaction | `BEGIN TRANSACTION READ ONLY` | DBMS có thể từ chối DML theo quy định read-only. |
| Database privileges | User chỉ được `SELECT` | Authorization tại DB, độc lập với annotation. |
| Entity mapping | `@Immutable` | Hạn chế updates qua Hibernate entity mapping. |

**Không suy diễn từ lớp này sang lớp khác.** Hibernate defaultReadOnly=true không chứng minh PostgreSQL transaction ở READ ONLY; Spring readOnly=true không chứng minh user DB không có quyền UPDATE.

## 5. Sơ đồ chuỗi tích hợp

~~~mermaid
flowchart TD
    A["@Transactional(readOnly=true)"] --> B["Spring transaction proxy/interceptor"]
    B --> C["PlatformTransactionManager"]
    C --> D["Hibernate JpaDialect/Session"]
    C --> E["JDBC Connection.setReadOnly"]
    D --> F["Flush mode/defaultReadOnly"]
    E --> G["JDBC driver"]
    G --> H["Database transaction mode"]
    F --> I["ORM dirty checking/SQL flush"]
    H --> J["DB cho phép hay từ chối DML"]
    I --> J
~~~

Sơ đồ biểu diễn **các hướng tích hợp có thể có** chứ không phải hợp đồng tất cả mũi tên luôn được thực hiện trong mọi cấu hình.

## 6. Session bình thường theo dõi managed entities

Ví dụ ghi hợp lệ:

~~~java
@Transactional
public void rename(Long id, String name) {
    Product p = products.findById(id)
        .orElseThrow();

    p.rename(name);

    // Không bắt buộc gọi save() trên managed entity.
}
~~~

Với Hibernate stateful Session:

~~~text
SELECT -> hydrate entity -> managed trong persistence context
                              |
                              v
                         loaded-state snapshot
                              |
                         thay đổi field
                              |
                         dirty checking khi flush
                              |
                              v
                         UPDATE product ...
~~~

Hibernate có thể phát hiện thay đổi property và cập nhật DB lúc flush/commit thích hợp. `@Version` thường được dùng để chống lost update trên đường managed entity update.

## 7. readOnly có thể tối ưu ở tầng Hibernate

Khi Spring dùng `JpaTransactionManager` phối hợp với `HibernateJpaDialect`, một read-only transaction mới có thể làm Hibernate Session thay đổi flush mode và default read-only behavior. Điều này có thể giảm chi phí:

- Tracking loaded-state snapshots của entity results mới.
- Dirty checking ở lần flush.
- Một số auto-flush công việc không cần thiết cho luồng chỉ đọc.

Mô hình khái niệm:

~~~text
Read/write entity:
  SELECT -> managed + loaded state -> dirty check -> possible UPDATE

Read-only optimized load:
  SELECT -> entity có thể được đánh dấu read-only
         -> giảm snapshot/dirty check theo Hibernate behavior
         -> ứng dụng dùng dữ liệu để đọc
~~~

**Không viết thành quy tắc tuyệt đối** rằng mọi `readOnly=true` luôn dẫn đến `FlushMode.MANUAL` hoặc bỏ mọi snapshots. Kết quả còn phụ thuộc Spring version, transaction manager, việc tạo transaction mới và entity/query đã load trước đó.

## 8. Flush mode là gì?

Flush là quá trình ORM đồng bộ pending changes của persistence context xuống database.

Một số Hibernate flush modes:

| Mode | Ý nghĩa khái niệm |
|---|---|
| `AUTO` | Hibernate quyết định auto-flush trước một số query và khi transaction kết thúc. |
| `COMMIT` | Thường tránh nhiều flush trước query, đồng bộ tại commit theo provider semantics. |
| `MANUAL` | Chỉ flush khi được yêu cầu tường minh trong các trường hợp thích hợp. |
| `ALWAYS` | Hibernate-specific, cố gắng flush trước truy vấn mạnh hơn. |

Spring/Hibernate có thể dùng `MANUAL` trong read-only transaction. Điều này **không đồng nghĩa database cưỡng chế READ ONLY**. Một câu JDBC UPDATE, native SQL hoặc mutation được gọi tường minh có thể có behavior riêng.

JPA có `FlushModeType.AUTO` và `COMMIT`; Hibernate cung cấp thêm flush modes. Vì vậy, JPA API `getFlushMode()` không nhất thiết mô tả toàn bộ flush behavior nội bộ của Hibernate.

## 9. Dirty checking khác hẳn cấm UPDATE

Trong transaction bình thường, Hibernate so sánh snapshot của managed entity với state hiện tại để biết có cần UPDATE không. Trong read-only entity mode, Hibernate có thể bỏ một phần tracking đó.

Nhưng một service vẫn có thể gọi:

~~~java
entityManager.createNativeQuery(
    "UPDATE product SET name = :name WHERE id = :id"
)
.setParameter("name", "Tên mới")
.setParameter("id", 42L)
.executeUpdate();
~~~

Đây là **explicit DML**, không cần dirty checking. Nếu database transaction không enforce read-only, lệnh vẫn có thể chạy.

Vì vậy:

- “Không có automatic dirty-check UPDATE” là một thuộc tính ORM.
- “Không có SQL DML nào được phép chạy” là một yêu cầu enforcement DB/authorization.
- “Method không có side effects” là một yêu cầu ở application/business logic.

Ba điều này không tương đương.

## 10. readOnly không làm câu SELECT tự nhanh lên

Một query:

~~~java
@Transactional(readOnly = true)
public List<Product> list() {
    return products.findAll();
}
~~~

nếu trả một triệu rows vẫn có thể:

- Đọc một triệu rows từ DB.
- Truyền dữ liệu qua JDBC/network.
- Hydrate một triệu objects.
- Giữ một List lớn trong heap.
- Chiếm connection trong thời gian đọc dài.

Nếu bottleneck là sort lớn hoặc thiếu index, annotation readOnly không giải quyết.

Các tối ưu quan trọng thường là **pagination, DTO projection, cắt giảm columns, index, query plan, tránh N+1 và giới hạn lifetime transaction**.

## 11. readOnly không tự thêm LIMIT/pagination

Nếu API chỉ cần một trang:

~~~java
@Transactional(readOnly = true)
public Page<ProductView> list(Pageable pageable) {
    return products.findAll(pageable).map(
        p -> new ProductView(
            p.getId(),
            p.getName(),
            p.getPrice()
        )
    );
}
~~~

Đây là ví dụ pagination ở service/repository. DTO projection trực tiếp thường còn tốt hơn nếu không cần toàn entity.

`readOnly=true` không thay `setMaxResults`, không thay Pageable và không bảo đảm thứ tự kết quả. Pagination cần `ORDER BY` ổn định, nhất là khi nhiều bản ghi có cùng sort key.

## 12. readOnly không giải quyết N+1

Giả sử:

~~~java
@Transactional(readOnly = true)
public List<String> customerNames() {
    return orders.findAll().stream()
        .map(o -> o.getCustomer().getName())
        .toList();
}
~~~

Nếu `customer` là LAZY, mỗi Order có thể kích hoạt thêm SELECT. Một read-only transaction vẫn có thể chạy rất nhiều SQL statements.

Hãy chọn DTO projection, `join fetch` phù hợp, entity graph hoặc batch fetching; xác minh số SQL thực tế. Đừng dùng annotation như cách sửa fetch plan.

## 13. Sửa entity trong read-only transaction có gì rủi ro?

~~~java
@Transactional(readOnly = true)
public void renameButNotACommand(Long id) {
    Product p = products.findById(id).orElseThrow();
    p.rename("Đổi tên");
}
~~~

Trên nhiều tích hợp Spring/Hibernate, thay đổi có thể không tự đồng bộ vì flush mode/read-only entity state. Nhưng **không dùng điều đó làm contract ngăn ghi**:

- Entity có thể đã managed trước đó.
- Transaction ngoài có thể là write transaction.
- Flush mode có thể khác giữa versions.
- Explicit flush/mutation khác có thể phát SQL.
- DB có thể hoặc không enforce read-only.

Nếu muốn ghi, dùng transaction ghi rõ:

~~~java
@Transactional
public void renameProduct(Long id, String name) {
    Product p = products.findById(id).orElseThrow();
    p.rename(name);
}
~~~

## 14. @Transactional(readOnly=true) không phải bảo mật

Một phương thức chỉ đọc cần authorization phù hợp ngay cả khi có annotation.

Cờ read-only không thay thế:

- Kiểm tra quyền người dùng.
- Quyền SELECT-only của database account.
- Database transaction enforcement nếu cần.
- Validation/domain constraints.
- Audit logging.
- Phòng chống SQL injection.
- Chính sách bảo vệ dữ liệu của hệ thống.

Một method có readOnly có thể gửi email, ghi file, gọi API ngoài hoặc gửi sự kiện — tất cả là side effects ngoài database mà annotation không ngăn.

## 15. JDBC Connection.setReadOnly(true)

JDBC có:

~~~java
connection.setReadOnly(true);
~~~

Driver có thể dùng flag làm hint/thiết lập, nhưng behavior thay đổi theo DBMS và driver:

- Truyền read-only transaction mode đến database.
- Điều chỉnh cách connection được dùng.
- Tối ưu riêng cho driver.
- Không enforce như ứng dụng tưởng.

Transaction manager/pool cần quản lý việc chuẩn bị và khôi phục connection state. **Không tự đổi JDBC connection readOnly giữa một Spring-managed transaction** nếu chưa xác định ownership và transaction lifecycle.

Driver có thể từ chối thay flag khi transaction đang active; pool còn phải reset state đúng khi trả connection.

## 16. Database read-only transaction là tầng khác

PostgreSQL minh họa một transaction thật sự READ ONLY:

~~~sql
BEGIN TRANSACTION READ ONLY;

SELECT id, name
FROM product
WHERE id = 42;

UPDATE product
SET name = 'X'
WHERE id = 42;
-- PostgreSQL từ chối thay đổi ở transaction READ ONLY.

ROLLBACK;
~~~

Đây là enforcement của PostgreSQL transaction, không phải một cam kết Spring annotation trên mọi provider/DB.

DB khác có khả năng/cú pháp riêng và behavior riêng với temporary tables, sequences, stored procedures, session variables. Khi yêu cầu “không thể ghi”, phải xác minh DB-level semantics trên DB thực tế.

## 17. DataSourceTransactionManager có thể enforce

Spring `DataSourceTransactionManager` có thể chuẩn bị JDBC connection readOnly; trong những phiên bản thích hợp có tùy chọn `setEnforceReadOnly(true)` cho việc phát statement read-only transaction ở DB hỗ trợ.

~~~java
@Bean
DataSourceTransactionManager transactionManager(
        DataSource dataSource) {

    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);

    manager.setEnforceReadOnly(true);

    return manager;
}
~~~

Đây là **JDBC transaction manager** và ví dụ cấu hình cho một datasource thích hợp. Không tự suy luận rằng nó áp dụng nguyên xi khi dự án dùng Spring Data JPA với `JpaTransactionManager`. Ứng dụng nhiều transaction managers phải xác định bean quản lý từng service.

## 18. JpaTransactionManager và HibernateJpaDialect

Ứng dụng Spring Data JPA thường dùng `JpaTransactionManager`. Khi Hibernate là JPA provider, `HibernateJpaDialect` có thể:

- Điều chỉnh Hibernate flush mode.
- Thiết lập defaultReadOnly cho entity loads trong một số version.
- Chuẩn bị JDBC connection state nếu connection handling mode cho phép.
- Khôi phục session/connection state khi transaction kết thúc.

Do vậy, kết luận readOnly phải có bối cảnh:

~~~text
Spring Framework version
+ Spring Boot transaction configuration
+ PlatformTransactionManager implementation
+ HibernateJpaDialect/provider version
+ Hibernate ORM version
+ JDBC driver + connection pool
+ DBMS và transaction mode
+ Propagation/call path
~~~

Không chỉ nhìn annotation rồi khẳng định tất cả layers đã tối ưu.

## 19. Spring Data JPA có những defaults gì?

Với repository kế thừa từ `JpaRepository`, các CRUD read operations từ `SimpleJpaRepository` thường được cấu hình read-only; mutation methods như save/delete thường có transaction ghi.

Tuy nhiên **declared query methods**, bao gồm method tự định nghĩa, không mặc nhiên phải có cùng transaction configuration như inherited CRUD methods. Cần định nghĩa transaction nếu method yêu cầu một scope rõ.

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.price >= :min
        """)
    List<Product> findExpensive(
        @Param("min") BigDecimal minimum
    );
}
~~~

Khi service gọi nhiều repositories, **service-level transaction boundary** thường thể hiện use case tốt hơn việc phụ thuộc defaults của từng repository method.

## 20. Đặt transaction tại service layer

~~~java
@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    public ProductView get(Long id) {
        Product p = products.findById(id).orElseThrow();
        return new ProductView(
            p.getId(), p.getName(), p.getPrice()
        );
    }

    @Transactional
    public void rename(Long id, String name) {
        Product p = products.findById(id).orElseThrow();
        p.rename(name);
    }
}
~~~

Điều này giúp reviewer nhận biết read vs write intent, ngăn việc vô tình gọi command từ query service và dễ quan sát transaction/metrics.

Không nhất thiết phải xây kiến trúc CQRS đầy đủ; ranh giới service rõ ràng là đủ cho nhiều dự án.

## 21. REQUIRED propagation: outer transaction thường quyết định

Mặc định Spring `@Transactional` dùng `Propagation.REQUIRED`.

~~~java
@Transactional
public void placeOrder(Long productId) {
    pricingService.currentPrice(productId);
    // Các thao tác ghi khác.
}
~~~

~~~java
@Transactional(readOnly = true)
public BigDecimal currentPrice(Long id) {
    return products.findById(id).orElseThrow().getPrice();
}
~~~

Nếu `currentPrice` được gọi qua Spring-managed bean và đã có transaction outer, inner thường **tham gia transaction đang tồn tại**. Inner readOnly flag **không tự chuyển outer write transaction thành read-only**.

Ngược lại, một method ghi `@Transactional` REQUIRED gọi từ outer readOnly transaction thường **không tự nâng cấp** transaction đó thành write transaction.

## 22. Outer readOnly gọi inner write

~~~java
@Transactional(readOnly = true)
public void showAndRename(Long id) {
    productCommandService.rename(id, "Tên mới");
}
~~~

~~~java
@Transactional
public void rename(Long id, String name) {
    Product p = products.findById(id).orElseThrow();
    p.rename(name);
}
~~~

Nếu inner dùng REQUIRED, nó thường tham gia outer transaction đã có read-only semantics. Không bảo đảm inner mutation được auto-flush hoặc DB cho phép ghi.

Đừng xây business workflow dựa trên ý tưởng “annotation bên trong sẽ đè annotation bên ngoài”. Thiết kế outer command scope là transaction ghi khi use case thật sự có mutation.

## 23. REQUIRES_NEW có transaction riêng

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit() {
    // Ghi dữ liệu trong transaction mới.
}
~~~

Khi gọi qua proxy và được transaction manager hỗ trợ, Spring có thể suspend transaction ngoài rồi mở transaction mới với flags riêng.

Nhưng REQUIRES_NEW:

- Có thể mượn thêm connection.
- Commit độc lập với rollback ngoài.
- Có thể gây contention trong connection pool.
- Không sửa self-invocation.
- Thay đổi semantics consistency.

Không dùng REQUIRES_NEW đơn thuần để “vượt” readOnly mà chưa thiết kế transaction boundaries.

## 24. validateExistingTransactions và mismatch

Một số Spring transaction managers hỗ trợ kiểm tra việc method tham gia transaction có sẵn với những transaction attributes không tương thích. Tùy chọn `validateExistingTransaction` của `AbstractPlatformTransactionManager` có thể giúp phát hiện mismatches về isolation/readOnly theo implementation.

Điều này **không phải mặc định mọi cấu hình đều chặn nested write-in-readOnly**. Nếu muốn phát hiện sớm sai lệch, cần bật kiểm tra phù hợp và viết integration tests cho đúng call path.

## 25. Self-invocation làm annotation không chạy

Trong cơ chế Spring proxy thường dùng:

~~~java
@Service
public class ReportService {

    public void export() {
        this.loadProducts();
    }

    @Transactional(readOnly = true)
    public List<Product> loadProducts() {
        return products.findAll();
    }
}
~~~

`this.loadProducts()` không đi qua AOP proxy; transaction advice thường **không kích hoạt**. Cần gọi qua một Spring-managed bean/proxy phù hợp hoặc đặt transaction boundary tại method public được gọi từ ngoài.

Một method có `@Transactional` không đồng nghĩa transaction interceptor đã chạy. Nếu readOnly flags không thấy thay đổi, kiểm tra proxy/call path trước.

## 26. Proxy method và bean lifecycle

Các tình huống khác có thể khiến annotation không mang hiệu lực mong muốn:

- Object được khởi tạo bằng `new` thay vì Spring container.
- Method/call path không được proxy intercept.
- Một số final/private/non-public methods với proxy mode không phù hợp.
- `@Transactional` bị đặt nhầm package annotation.
- Method chạy trên thread mới ngoài transaction context.
- AspectJ/proxy strategy khác nhau giữa dự án.

Không dùng quy tắc đơn giản “mọi method không public đều không hỗ trợ” cho mọi Spring version; class-based proxies ở Spring hiện đại có các khả năng riêng. Điều quan trọng là **xác nhận interceptor thực sự chạy**.

## 27. Thread boundary và @Async

~~~java
@Transactional(readOnly = true)
public void exportAsync() {
    CompletableFuture.runAsync(() -> {
        queryService.loadProducts();
    });
}
~~~

Imperative Spring transaction context thường gắn với thread. Task chạy thread khác không mặc nhiên nhận transaction caller, bao gồm readOnly flag.

Nếu task async cần transaction, mở scope transaction trong chính worker thread qua service/proxy/transaction manager phù hợp. Không giữ `EntityManager` của caller rồi chia sẻ qua threads.

Reactive transaction management có context propagation khác imperative; không áp dụng trực tiếp giả định ThreadLocal cho mọi reactive flow.

## 28. OSIV không phải giải pháp của readOnly

Open Session/EntityManager in View có thể giữ persistence context qua request để lazy association có thể load khi view/controller serialize.

`@Transactional(readOnly=true)` không tự tắt OSIV và không ngăn mọi lazy SELECT sau service transaction. Điều này có thể che giấu N+1 queries hoặc làm database access khó kiểm soát.

Với API, nên lấy DTO hoặc projection trong service có transaction rõ ràng thay vì trả entity graph cho controller và kỳ vọng readOnly/OSIV tự đảm bảo hiệu năng.

## 29. Hibernate Session.setDefaultReadOnly(true)

Hibernate có:

~~~java
Session session = entityManager.unwrap(Session.class);
session.setDefaultReadOnly(true);
~~~

Theo Hibernate semantics, các entity được load sau đó, khi phù hợp, có thể ở read-only state để giảm dirty checking/snapshots.

Cần lưu ý:

- Không phải mọi entity đã managed từ trước tự chuyển sang read-only.
- Collection/association operations có thể có quy tắc riêng.
- Read-only entity state không cấm JDBC writes.
- Không bật nếu sau đó cần Hibernate tự ghi thay đổi entity.
- Đổi defaultReadOnly trở lại không tự replay những changes đã bỏ qua.

Spring/Hibernate integration có thể dùng cơ chế này, nhưng phải kiểm tra flags trong scope thực tế.

## 30. Hibernate Query.setReadOnly(true)

Hibernate hỗ trợ read-only ở cấp query:

~~~java
Session session = entityManager.unwrap(Session.class);

List<Product> rows = session.createQuery(
    "select p from Product p where p.price >= :min",
    Product.class
)
.setParameter("min", new BigDecimal("100000"))
.setReadOnly(true)
.getResultList();
~~~

So sánh:

- `@Transactional(readOnly=true)`: Spring transaction intent.
- `Session.setDefaultReadOnly(true)`: session-level default entity-load behavior.
- `Query.setReadOnly(true)`: query-result behavior.
- `@Immutable`: entity mapping-level mutability.

Đây không phải bốn cách gọi tương đương.

## 31. @Immutable khác readOnly transaction

Hibernate mapping:

~~~java
@Entity
@org.hibernate.annotations.Immutable
@Table(name = "report_snapshot")
public class ReportSnapshot {
    @Id private Long id;
    private String title;
}
~~~

`@Immutable` biểu thị entity mapping bất biến theo Hibernate dirty-checking/UPDATE semantics. Nó không biến DB table thành bất biến cho native SQL, JDBC hoặc công cụ ngoài Hibernate.

Nếu dữ liệu phải thật sự chỉ được đọc bởi một role, DB privileges/row-level policies và workflow nhập dữ liệu vẫn cần thiết.

## 32. @Column(updatable=false) khác readOnly

~~~java
@Column(updatable = false)
private Instant createdAt;
~~~

Thuộc tính này điều khiển Hibernate entity-generated UPDATE cho một mapped column, không khiến transaction thành read-only.

| Cơ chế | Phạm vi |
|---|---|
| `@Transactional(readOnly=true)` | Transaction intent/hint |
| `Session.setDefaultReadOnly(true)` | Entity-load behavior |
| `Query.setReadOnly(true)` | Query results |
| `@Immutable` | Entity mapping |
| `@Column(updatable=false)` | Một column của ORM-generated update |
| DB SELECT-only user | Authorization |
| DB transaction READ ONLY | Database enforcement |

Đặt đúng mechanism theo yêu cầu.

## 33. Gọi save() trong readOnly transaction

~~~java
@Transactional(readOnly = true)
public void notAReadOperation(Product p) {
    products.save(p);
}
~~~

Không dựa vào việc có/không có exception để kết luận.

- `save()` có thể gọi persist/merge theo entity state.
- IDENTITY generator có thể cần INSERT sớm để lấy ID.
- Flush mode/manual có thể trì hoãn/bỏ automatic flush.
- Database READ ONLY có thể từ chối DML.
- Trong nested call, transaction ngoài có thể quyết định flags.
- `save()` trả object không chứng minh DB đã commit.

**Quy ước:** Method thật sự ghi nên dùng transaction ghi. Read-only service không gọi mutation path.

## 34. @Modifying là DML tường minh

Spring Data JPA:

~~~java
@Modifying
@Query("""
    update Product p
    set p.name = :name
    where p.id = :id
    """)
int renameProduct(
    @Param("id") Long id,
    @Param("name") String name
);
~~~

Bulk update này không dựa vào dirty checking từng entity. Nếu được gọi trong readOnly transaction, kết quả phụ thuộc database enforcement và transaction manager.

Các tùy chọn `@Modifying(flushAutomatically=true, clearAutomatically=true)` có thể flush/clear context nhưng **không phải cách bảo đảm vượt qua readOnly**. Clear có thể detach managed entities và gây mất pending changes nếu chưa flush.

## 35. readOnly và automatic flush trước query

Ví dụ:

~~~java
Product p = entityManager.find(Product.class, id);
p.rename("B");

Long total = entityManager.createQuery(
    "select count(x) from Product x",
    Long.class
).getSingleResult();
~~~

Với flush mode AUTO, Hibernate có thể flush trước query liên quan để giữ semantics của kết quả. Nếu Spring readOnly transaction điều chỉnh flush mode, behavior đó có thể thay đổi.

Không giả định “readOnly=true làm mọi query bỏ flush” ở mọi provider. Nếu use case cần read-after-write consistency, đặt transaction ghi rõ ràng và test flush behavior.

## 36. readOnly không đồng nghĩa isolation

~~~java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED
)
public ProductView get(Long id) {
    // Đọc dữ liệu.
}
~~~

`readOnly` nói về ý định mutation/optimization; `isolation` nói về visibility của concurrent transactions. ReadOnly không tự tạo repeatable snapshot.

| Thuộc tính | Điều khiển |
|---|---|
| readOnly | Hint/tối ưu hoặc DB enforcement khi có |
| isolation | Visibility của concurrent changes |
| propagation | Tham gia transaction hiện có hay mở mới |
| timeout | Giới hạn lifetime transaction |
| rollbackFor | Những exception dẫn đến rollback theo policy |

Một báo cáo cần snapshot nhất quán phải thiết kế isolation/version/cutoff phù hợp, không chỉ readOnly.

## 37. Read-only transaction vẫn chiếm tài nguyên

Một SELECT lớn trong transaction readOnly vẫn có thể:

- Giữ JDBC connection lâu.
- Giữ MVCC snapshot.
- Gây áp lực vacuum/cleanup tùy DB.
- Tốn CPU, I/O và network.
- Kích hoạt query timeout.
- Làm connection pool bị tranh chấp.

Read-only không có nghĩa “transaction không tốn chi phí”. Với tác vụ kéo dài, cân nhắc keyset pagination và transaction ngắn theo batch.

## 38. Read replica routing cần cấu hình riêng

Một ứng dụng có thể dùng readOnly flag để chọn read datasource:

~~~text
Query service @Transactional(readOnly=true)
    |
    +--> custom routing datasource --> read replica

Command service @Transactional
    |
    +--> primary writer
~~~

Đây là **kiến trúc do ứng dụng cấu hình**, không tự xảy ra khi thêm annotation.

Các vấn đề phải xử lý:

- Replica lag và read-your-writes.
- Chọn datasource trước khi connection được lấy.
- Ordering của AOP advices và transaction manager.
- LazyConnectionDataSourceProxy nếu dùng để trì hoãn acquisition.
- Nested readOnly trong outer write transaction.
- Không gửi mutations vào replica do routing sai.

Một report cần nhất quán với ghi vừa thực hiện có thể phải đọc primary dù method chỉ đọc.

## 39. ReadOnly không tắt first-level cache

Hibernate Session vẫn giữ persistence context khi query đọc entities. ReadOnly có thể giảm state tracking nhưng không có nghĩa Session trở thành StatelessSession.

~~~java
@Transactional(readOnly = true)
public List<Product> all() {
    return products.findAll();
}
~~~

Nếu danh sách lớn, ứng dụng vẫn có thể giữ nhiều entities, collections và List references. Dùng DTO/scalar projections, pagination, stream/cursor có closure đúng và kiểm soát lazy loading khi cần.

## 40. Streaming và readOnly

~~~java
@Transactional(readOnly = true)
public void export(CsvWriter writer) {
    TypedQuery<Product> query = entityManager.createQuery(
        "select p from Product p order by p.id",
        Product.class
    );

    try (Stream<Product> stream = query.getResultStream()) {
        stream.forEach(p -> writer.write(
            p.getId(), p.getName(), p.getPrice()
        ));
    }
}
~~~

`CsvWriter` là component minh họa.

- Stream phải đóng bằng try-with-resources.
- Transaction phải còn hiệu lực khi tiêu thụ cursor nếu driver yêu cầu.
- Fetch size phụ thuộc JDBC driver.
- Không trả Stream để controller tiêu thụ sau khi service transaction đóng.
- Không gọi `toList()` trên một stream khổng lồ rồi xem đó là streaming tiết kiệm memory.

Nếu job rất dài, keyset pagination theo batch có thể an toàn hơn giữ transaction/cursor mở lâu.

## 41. Quan sát Hibernate flags

Trong test/dev có Hibernate provider:

~~~java
@Transactional(readOnly = true)
public void inspect() {
    Session session = entityManager.unwrap(Session.class);

    System.out.println(
        session.getHibernateFlushMode()
    );
    System.out.println(
        session.isDefaultReadOnly()
    );
}
~~~

Quan sát:

- FlushMode thực tế.
- Default read-only của Session.
- Entity load status nếu cần.

Hai giá trị này chỉ mô tả **Hibernate session state**, không chứng minh DB transaction đang READ ONLY.

## 42. Quan sát Spring transaction metadata

~~~java
boolean active =
    TransactionSynchronizationManager
        .isActualTransactionActive();

boolean readOnly =
    TransactionSynchronizationManager
        .isCurrentTransactionReadOnly();
~~~

Trong Spring-managed transaction, flags giúp biết transaction interceptor có đang quản lý scope hay không và readOnly metadata Spring nhìn thấy.

Đây **không phải** kiểm tra JDBC connection hoặc DB enforcement. Với self-invocation hoặc thread khác, kết quả có thể không như annotation trông thấy trong source.

## 43. Kiểm tra PostgreSQL transaction mode

PostgreSQL có:

~~~sql
SHOW transaction_read_only;
~~~

Hoặc:

~~~sql
SELECT current_setting('transaction_read_only');
~~~

Trong cùng transaction, có thể quan sát bằng JPA native SQL:

~~~java
@Transactional(readOnly = true)
public String readOnlyAtDatabase() {
    return (String) entityManager.createNativeQuery(
        "SELECT current_setting('transaction_read_only')"
    ).getSingleResult();
}
~~~

Kết quả thường hiển thị `on` hoặc `off`. Đây là thông tin từ **database transaction thực tế**, không chỉ Spring/Hibernate flags. Chỉ dùng câu SQL này cho PostgreSQL, không áp dụng nguyên xi cho DBMS khác.

## 44. Test đọc lại DB, không chỉ Java object

Giả sử trong readOnly method bạn viết:

~~~java
Product p = products.findById(id).orElseThrow();
p.rename("Tên tạm");

assertEquals("Tên tạm", p.getName());
~~~

Assertion chỉ chứng minh field Java đã thay đổi. Nó **không chứng minh** DB được update hoặc không update.

Một test thực tế cần:

1. Tạo dữ liệu fixture trong transaction riêng.
2. Gọi scenario under test qua Spring proxy.
3. Đợi transaction đóng/commit hoặc rollback theo test policy.
4. Mở EntityManager/transaction mới.
5. Đọc lại DB, tránh reuse entity cached trong context cũ.
6. Quan sát SQL/update count và database transaction flags khi cần.

Spring Test `@Transactional` thường rollback cuối test theo mặc định; DB không đổi có thể chỉ vì rollback của test, **không phải vì readOnly cấm ghi**.

## 45. Matrix tích hợp để kiểm tra

| Scenario | Điều cần xác minh |
|---|---|
| Transaction thường, đổi managed entity | Có UPDATE khi commit? |
| ReadOnly transaction, đổi managed entity | Có auto-flush hay không? |
| ReadOnly + native UPDATE | DB có từ chối DML không? |
| ReadOnly + JdbcTemplate.update | Connection/database flags có enforce? |
| Outer write + inner readOnly REQUIRED | Inner có tham gia outer transaction? |
| Outer readOnly + inner write REQUIRED | Có nâng cấp thành write transaction không? |
| Inner write REQUIRES_NEW | Có tạo transaction mới như kỳ vọng? |
| Self-invocation | Interceptor có chạy không? |
| Spring Data declared @Query | Transaction scope từ đâu? |
| Hibernate Session flags | FlushMode và defaultReadOnly là gì? |
| PostgreSQL transaction_read_only | DB có READ ONLY thật không? |
| Read-only export | Stream/connection có đóng đúng scope không? |

Matrix này là hướng dẫn **technical integration testing** cho cơ chế Spring/Hibernate, không phải nội dung bắt buộc phải chạy trong bước viết tài liệu.

## 46. Hibernate Statistics và SQL logging

Có thể quan sát Hibernate statistics (khi bật phù hợp):

~~~java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sf.getStatistics();

long startFlushes = stats.getFlushCount();
long startUpdates = stats.getEntityUpdateCount();

runScenario();

long flushes =
    stats.getFlushCount() - startFlushes;

long updates =
    stats.getEntityUpdateCount() - startUpdates;
~~~

`SessionFactory` statistics là số liệu toàn factory, có thể bị ảnh hưởng bởi các threads khác. Khi benchmark, cô lập workload hoặc dùng công cụ có độ phân giải phù hợp.

SQL logging Hibernate 6/Spring Boot thường dùng:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Cần tránh lộ PII/secrets khi bật bind logging. SQL log giúp nhận biết SELECT/UPDATE và N+1, nhưng không đo trực tiếp lượng entity snapshots hay mọi chi phí JDBC driver buffer.

## 47. Benchmark readOnly phải có đối chứng

Để đo tác động thực tế:

1. Dùng cùng dataset, schema/index, DB server, JVM và pool.
2. Warm-up và chạy đủ lượt để giảm nhiễu.
3. So sánh cùng query trong write transaction và readOnly transaction.
4. Không thay đổi query shape/DTO trong một biến thể mà giữ entity trong biến thể khác rồi quy lợi ích hết cho readOnly.
5. Ghi rõ Spring/Hibernate/JDBC/DB versions.
6. Đo throughput/latency và heap/allocations/GC, không chỉ tổng thời gian một lượt.

| Chỉ số | Lý do |
|---|---|
| SQL execution time | DB query có nhanh hơn không? |
| Flush count | Tần suất auto-flush thay đổi? |
| Entity update count | Có DML ngoài ý định? |
| Allocated heap / snapshots | ReadOnly có giảm tracking overhead? |
| GC pause/CPU | Lợi ích tài nguyên ở JVM? |
| p50/p95 latency | Người dùng có thấy khác biệt? |
| JDBC connection hold time | Có transaction kéo dài? |
| DB transaction_read_only | Có enforcement thật? |
| SQL statement count | Có N+1 hoặc query thừa? |

Một findById 1 row có thể có khác biệt rất nhỏ; đọc hàng chục nghìn entities có thể cho thấy chi phí state tracking rõ hơn. Chỉ kết luận sau đo.

## 48. Workload nào có lợi từ readOnly?

| Workload | Khả năng giúp ích | Điều quan trọng hơn |
|---|---|---|
| findById một entity | Có thể giảm chút overhead | Network/connection/index |
| Query nhiều managed entities | Có thể giảm dirty checking/snapshots | DTO, pagination, fetch plan |
| DTO projection | Ít managed state để tối ưu | SQL plan/index |
| COUNT/SUM scalar | Thường ít lợi ích từ snapshot | Aggregate query plan |
| N+1 association loads | Không giải quyết N+1 | Join/projection/batch fetch |
| Native UPDATE | Không phải workflow read-only | Transaction ghi/locking |
| Stream export lớn | Có thể hữu ích cho Session | Cursor/fetch size/connection lifetime |
| Read replica query | Flag có thể phục vụ routing | Replica lag/consistency |

Không có mức cải thiện phần trăm chung cho mọi dự án.

## 49. Khi nào nên dùng readOnly?

Thường phù hợp:

- Query services trả DTO/projections.
- Trang danh sách và tìm kiếm.
- Báo cáo chỉ đọc.
- Thao tác lấy thông tin để hiển thị.
- Luồng export mà transaction/session được đóng đúng.
- Các use cases cần biểu đạt rõ **không có mutation**.

Không nên gắn bừa:

- Method gọi `save`, `delete`, bulk update hay native DML.
- Method gọi command services có tác động DB.
- Transaction cần read-after-write cùng unit of work.
- Logic tạo entity mới hoặc cập nhật managed entities.
- Use case cần DB-level enforcement nhưng chưa kiểm chứng.

Đặt flag dựa trên **ý định nghiệp vụ trước**, sau đó đo lợi ích tối ưu.

## 50. Bảng lỗi hiểu nhầm phổ biến

| Phát biểu thiếu chính xác | Cách hiểu đúng hơn |
|---|---|
| readOnly luôn chặn UPDATE | Hint; chỉ DB enforcement/permissions phù hợp mới cho bảo đảm rõ. |
| readOnly luôn nhanh hơn | Phụ thuộc workload, stack và bottleneck. |
| readOnly tắt first-level cache | Hibernate Session vẫn là stateful Session. |
| readOnly tự tạo replica routing | Router datasource phải được cấu hình riêng. |
| readOnly đảm bảo snapshot nhất quán | Isolation/cutoff quyết định. |
| Inner @Transactional tự đổi outer transaction | REQUIRED thường tham gia transaction có sẵn. |
| save() không exception tức là đã commit | Cần kiểm tra transaction/flush/DB state. |
| Java object đổi tên tức DB đã đổi | Phải đọc DB sau transaction/clear context. |
| Rollback test chứng minh readOnly cấm ghi | Rollback và readOnly là hai cơ chế khác nhau. |
| readOnly đủ cho authorization | Cần xác thực, phân quyền và DB policy phù hợp. |

## 51. Cách thiết kế một service rõ ràng

~~~java
@Service
public class ProductApplicationService {

    private final ProductRepository products;

    public ProductApplicationService(ProductRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    public ProductView show(Long id) {
        Product p = products.findById(id).orElseThrow();
        return new ProductView(
            p.getId(), p.getName(), p.getPrice()
        );
    }

    @Transactional
    public void changeName(Long id, String newName) {
        Product p = products.findById(id).orElseThrow();
        p.rename(newName);
    }
}
~~~

Cách tách Query/Command giúp:

- Tên API thể hiện ý định.
- Người đọc nhìn thấy transaction boundaries.
- Hạn chế write path nằm trong read-only scope.
- Dễ áp dụng phép đo đúng workload.
- Dễ xác định queries có thể dùng replica khi consistency cho phép.

Không cần xây một hệ CQRS phức tạp để có được lợi ích này.

## 52. Bài tập thực hành

**Bài 1 — Hibernate flags.** Viết hai methods `@Transactional` và `@Transactional(readOnly=true)`. Trong từng scope, quan sát `Session.getHibernateFlushMode()` và `Session.isDefaultReadOnly()`.

**Bài 2 — Dirty checking.** Load Product, sửa name rồi kết thúc write transaction. Đọc lại từ EntityManager mới. Lặp lại với readOnly và giải thích kết quả.

**Bài 3 — Explicit DML.** Chạy native UPDATE trong readOnly transaction trên database test. Kiểm tra có bị từ chối không; đừng dự đoán từ annotation.

**Bài 4 — Propagation.** Gọi inner readOnly REQUIRED trong outer write và inner write REQUIRED trong outer readOnly qua hai Spring beans. Quan sát transaction metadata.

**Bài 5 — Self-invocation.** So sánh `this.read()` với gọi một method đọc của bean khác có `@Transactional(readOnly=true)`.

**Bài 6 — Spring Data defaults.** So sánh repository inherited findById với declared query method khi không có outer service transaction.

**Bài 7 — Memory.** Đọc nhiều managed entities với readOnly true/false; đo heap, flushes và DTO projection. Phân biệt lợi ích riêng của readOnly với đổi query shape.

**Bài 8 — PostgreSQL.** Trong cùng transaction, chạy `SELECT current_setting('transaction_read_only')`; kiểm tra explicit UPDATE trong DB transaction READ ONLY.

**Bài 9 — Read replica.** Thiết kế quy tắc query nào được phép đọc replica, query nào phải đọc primary để bảo đảm read-your-writes.

**Bài 10 — Endpoint chậm.** Lấy một API thực tế, đo query count, execution plan, dữ liệu trả về, heap và p95 trước khi quyết định thêm readOnly có giúp hay không.

## 53. Quy trình xác minh trong dự án

~~~mermaid
flowchart TD
    A["Method @Transactional(readOnly=true)"] --> B{"Proxy/interceptor có chạy?"}
    B -- "Không" --> C["Sửa bean/call path"]
    B -- "Có" --> D["Đọc Spring transaction flags"]
    D --> E["Xác định PlatformTransactionManager"]
    E --> F["Quan sát Hibernate flush mode/defaultReadOnly"]
    F --> G["Quan sát JDBC/DB read-only status"]
    G --> H["Test SELECT + explicit DML"]
    H --> I["Đo SQL/flush/heap/latency"]
    I --> J["Ghi kết luận theo version và workload"]
~~~

Một kết luận đáng tin cậy nên được ghi theo mẫu:

> Trên Spring version X, Hibernate version Y, JDBC driver Z, DBMS D và transaction manager M, `@Transactional(readOnly=true)` làm Hibernate Session có flush mode F và defaultReadOnly R khi mở transaction mới. Database transaction mode có giá trị V. Với workload W và dataset N, số flushes/allocations/latency thay đổi theo các số liệu benchmark. Kết quả này **chỉ áp dụng cho cấu hình đã kiểm thử**.

Cách viết đó cho phép đồng đội lặp lại phép đo và phát hiện regression khi nâng cấp framework.

## 54. Checklist code review

**Ý định và Spring transactions**

- [ ] Method có thật sự chỉ đọc không?
- [ ] Dùng đúng annotation Spring?
- [ ] Transaction proxy/interceptor có chạy?
- [ ] Outer transaction/propagation có đúng mong đợi?
- [ ] Không có self-invocation ngoài proxy?
- [ ] Không gọi command service trong read-only scope?
- [ ] Không truyền Stream/lazy entity ra ngoài transaction bất cẩn?

**Hibernate/JPA**

- [ ] Hibernate flush/defaultReadOnly được xác minh trên version?
- [ ] Không dựa vào giảm dirty checking như cách cấm DB writes?
- [ ] Query có DTO/projection/pagination/fetch plan hợp lý?
- [ ] Không có N+1 hoặc auto-flush ngoài ý muốn?
- [ ] Không hiểu nhầm @Immutable/@Column(updatable=false)?

**Database và vận hành**

- [ ] Nếu cần cấm ghi, DB permissions/READ ONLY enforcement có thật?
- [ ] Connection flags và driver behavior được kiểm chứng?
- [ ] Read replica routing có xử lý lag/transaction timing?
- [ ] Isolation/snapshot requirements đã thiết kế riêng?
- [ ] Transaction lớn có gây pool/DB contention?
- [ ] Test độc lập rollback, auto-flush và DB enforcement?

## 55. FAQ

**1. readOnly có ngăn repository.save() không?**  
Không có cam kết chung. Behavior phụ thuộc ORM flush mode, persistence state, JDBC driver và DB read-only enforcement. Method cần ghi nên dùng transaction ghi.

**2. readOnly luôn bật FlushMode.MANUAL?**  
Đó là behavior thường thấy trong một số tích hợp Spring/Hibernate, không phải quy tắc cho mọi JPA provider/transaction manager/version. Hãy quan sát Session thật.

**3. readOnly luôn khiến SELECT nhanh?**  
Không. Nó có thể giảm snapshots/dirty checking, nhưng query plan, index, số rows và network thường chi phối.

**4. readOnly xóa first-level cache?**  
Không. Hibernate Session vẫn có persistence context. StatelessSession là API khác.

**5. Vì sao inner readOnly không đổi outer write transaction?**  
Với REQUIRED, inner tham gia transaction đã có thay vì tạo transaction mới.

**6. Annotation nên đặt ở repository hay service?**  
Repository inherited CRUD methods có defaults; service là ranh giới rõ hơn khi use case gọi nhiều repositories.

**7. readOnly tự chọn read replica?**  
Không. Cần datasource routing riêng và xử lý consistency.

**8. Có thể thay DB read-only user bằng annotation?**  
Không. Database permissions/enforcement mạnh hơn khi cần chặn ghi thật sự.

**9. readOnly có đảm bảo repeatable snapshot?**  
Không. Isolation/snapshot semantics là vấn đề riêng.

**10. Test nào quan trọng nhất?**  
Quan sát Spring flags, Hibernate Session state, database transaction mode và SQL/DB state từ transaction mới; benchmark với workload có đối chứng.

## 56. Tổng kết

**`@Transactional(readOnly = true)` là cách thể hiện ý định chỉ đọc và có thể mang lại tối ưu quan trọng ở Spring/Hibernate, nhưng không tự biến database thành nơi cấm ghi, không tự tối ưu SQL và không bảo đảm mọi mutation đều thất bại.**

Trước khi khẳng định một lợi ích hoặc mức cưỡng chế, hãy hỏi:

1. **Spring có thật sự mở read-only transaction mới?** Kiểm tra proxy, propagation và outer transaction.
2. **Hibernate đã thay đổi điều gì?** Kiểm tra flush mode, default read-only và dirty checking.
3. **JDBC/database có enforce không?** Kiểm tra connection/DB transaction mode và explicit DML trong integration tests.
4. **Workload nhanh hơn thật không?** Đo SQL statements, heap, CPU/GC, flush count, latency và connection lifetime.

Dùng `readOnly` để **truyền đạt ý định rõ ràng**, kết hợp query design, DTO/pagination/index để tối ưu thực chất; dùng database permissions/read-only transactions khi thật sự cần bảo vệ dữ liệu; và **xác minh bằng đo đạc trên đúng Spring, Hibernate, driver và DBMS đã triển khai**.
