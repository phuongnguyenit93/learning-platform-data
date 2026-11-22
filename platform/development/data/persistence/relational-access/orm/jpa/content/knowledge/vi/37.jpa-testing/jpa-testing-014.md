# Kiểm thử tương thích khi đổi provider hoặc phiên bản đặc tả JPA

Một ứng dụng JPA có thể hoạt động ổn định nhiều năm trên một provider, ví dụ Hibernate ORM, nhưng xuất hiện lỗi khi chuyển sang EclipseLink, đổi database dialect, nâng Hibernate major version hoặc thay JPA 2.x bằng Jakarta Persistence 3.x. Những lỗi này không nhất thiết nằm ở một dòng `persist()` hay `find()`. Chúng thường bắt nguồn từ **giả định ngầm** về cách provider triển khai chuẩn: thời điểm flush, cách cấp ID, kiểu SQL, thứ tự insert, lazy proxy, cache, xử lý kiểu dữ liệu, JPQL parser, schema generation hoặc cách dịch exception.

Một bộ kiểm thử tương thích tốt không chỉ trả lời “project có compile và chạy test không?” mà phải xác định:

- Ứng dụng đang dùng **phiên bản API/đặc tả** nào?
- Persistence provider nào thực sự được khởi tạo ở runtime?
- Database, JDBC driver, JDK và transaction manager nào đang tham gia?
- Hành vi nào được **Jakarta Persistence/JPA contract** bảo đảm?
- Hành vi nào là **provider extension** và phải được kiểm riêng?
- Những bất biến nghiệp vụ nào phải giữ khi thay một hoặc nhiều thành phần?
- Làm thế nào để phát hiện regression sớm, cô lập nguyên nhân và rollback an toàn?

Bài này thuộc chương **Kiểm thử JPA** của chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung tập trung vào chiến lược kiểm thử, các ví dụ Java/JUnit/Spring Data JPA, ma trận CI và quy trình chuyển đổi có khả năng kiểm chứng. Mọi cấu hình phiên bản trong ví dụ cần được điều chỉnh theo stack đang triển khai; không có một danh sách version tương thích áp dụng vĩnh viễn cho mọi ứng dụng.

---

## 1. “Tương thích” phải được định nghĩa như một hợp đồng hành vi

Có ba loại tương thích khác nhau:

1. **Tương thích source/binary**: ứng dụng và các dependency compile/link được với API mới.
2. **Tương thích persistence behavior**: entity mappings, queries, transactions và constraints tạo cùng kết quả có ý nghĩa.
3. **Tương thích vận hành**: latency, số SQL, locks, cache usage, memory và migration vẫn nằm trong giới hạn hệ thống chấp nhận.

Một chương trình compile được nhưng một `LEFT JOIN` bắt đầu trả số dòng khác do JPQL không đúng chuẩn vẫn có thể vi phạm nghiệp vụ. Một chương trình CRUD đúng kết quả nhưng vô tình làm N+1 tăng 100 lần cũng có thể không phù hợp production.

### 1.1. Kết quả tương đương không luôn đồng nghĩa SQL giống nhau

Hai providers có thể phát SQL khác nhau:

~~~sql
SELECT id, title FROM document WHERE id = ?
~~~

và

~~~sql
SELECT d.id, d.title FROM document d WHERE d.id = ?
~~~

Cả hai có thể tương đương về kết quả. Không nên viết cross-provider test yêu cầu exact whitespace, alias names hoặc thứ tự columns nếu đó không phải contract nghiệp vụ.

### 1.2. Những điều cần giữ nguyên

Ví dụ một service lưu đơn hàng phải bảo đảm:

- Mỗi Order có primary key duy nhất.
- Order và OrderLines commit atomically.
- Find theo PK trả đúng entity hoặc null.
- Versioned update không silently overwrite stale data.
- Query theo tenant không trả rows tenant khác.
- Pagination giữ thứ tự ổn định và count đúng.
- Rollback không để lại business rows.
- Lazy collections không bị truy cập sai transaction boundary.
- Public DTO không đổi ý nghĩa khi provider sinh SQL khác.

### 1.3. Compatibility test không phải vendor benchmark

Một provider nhanh hơn trong một microbenchmark không có nghĩa ứng dụng tương thích. Kiểm đúng dữ liệu, transaction và authorization là điều kiện cần; hiệu năng được đánh giá sau đó trong một lớp riêng.

---

## 2. Phân loại các thay đổi để quyết định test scope

| Thay đổi | Rủi ro tiêu biểu | Kiểm thử bắt buộc |
|---|---|---|
| Hibernate version A → B | JPQL/HQL parser, generators, type mapping, cache, SQL | Mapping + queries + transactions |
| Hibernate → EclipseLink | Vendor extension, fetch hints, proxy/weaving, batching | Portable suite + extension migration |
| EclipseLink → Hibernate | Named query, converters, fetch, sequence, cascade | Portable suite + integration |
| JPA 2.x → Jakarta Persistence 3.x | `javax.persistence` → `jakarta.persistence`, dependencies | Compile, bootstrap, mapping |
| Jakarta Persistence 3.0 → 3.1 | API mới như `GenerationType.UUID` | Feature compatibility tests |
| Jakarta Persistence 3.1 → 3.2 | API additions như `getSingleResultOrNull()` | Compile/runtime + null/cardinality |
| Database đổi engine | SQL dialect, sequence/identity, column types, locks | Testcontainers DB matrix |
| JDBC driver major upgrade | Generated keys, batching, timeouts, result mapping | Data/transaction/throughput tests |
| Spring Data/Spring Boot upgrade | Repository semantics, transaction/exception translation | Service/repository integration |
| JDK upgrade | Bytecode, reflection, modules, proxies, enhancers | Bootstrap + runtime integration |

Ma trận chỉ là điểm khởi đầu. Một thay đổi nhỏ ở database collation hoặc timestamp precision có thể quan trọng hơn một major version upgrade nếu hệ thống phụ thuộc vào những semantics đó.

### 2.1. Đổi một biến mỗi lần khi có thể

Nếu cùng lúc đổi JDK, provider, database và Spring Boot, khi test thất bại rất khó biết đâu là nguyên nhân. Giữ một cấu hình baseline và triển khai các trục nâng cấp riêng trước khi thử tổ hợp cuối.

### 2.2. Upgrade không phải lúc nào cũng đổi chuẩn JPA

Một provider version mới có thể tiếp tục implement cùng Jakarta Persistence API version nhưng thay internal SQL generation. Ngược lại, một API version mới có thể không yêu cầu rewrite mọi entity.

---

## 3. Lập “sổ kiểm kê” runtime trước khi đổi

Bộ kiểm thử tương thích phải ghi rõ:

- JDK runtime version.
- `jakarta.persistence-api` hoặc `javax.persistence-api` version.
- Implementation: Hibernate, EclipseLink hoặc provider cụ thể khác.
- Spring Boot/Spring Data/Jakarta EE platform version.
- JDBC driver và database engine/version.
- Transaction manager: RESOURCE_LOCAL, JTA hay Spring local.
- Schema migration tool/version.
- Bytecode enhancement, weaving, proxies, annotation processors.
- Second-level cache, query cache, custom cache integrations.
- Provider properties và vendor-specific annotations.
- Custom types, AttributeConverters, ID generators.
- Native SQL, stored procedures, query hints.

### 3.1. Nhận diện provider runtime, không chỉ dependency khai báo

Trong hệ thống có nhiều dependencies, việc khai báo Hibernate trong build file không chứng minh runtime đang dùng nó. Một provider khác có thể được chọn bởi service discovery, persistence unit hoặc container.

### 3.2. “Chạy được” chưa chứng minh đúng provider

Nếu test được thiết kế để kiểm EclipseLink nhưng runtime khởi tạo Hibernate, toàn bộ test green là **false confidence**. Vì vậy mỗi matrix job cần assert provider identity hoặc ghi kết quả startup đủ rõ để fail khi chọn nhầm.

### 3.3. Khóa dependency transitive

Một thư viện cũ có thể kéo API `javax.persistence` vào classpath trong khi runtime dự kiến `jakarta.persistence`. Cần dependency tree/lockfile review và kiểm compile/runtime, không chỉ sửa imports của application.

---

## 4. Di chuyển từ javax.persistence sang jakarta.persistence

JPA 2.x thường dùng imports:

~~~java
import javax.persistence.Entity;
import javax.persistence.EntityManager;
import javax.persistence.PersistenceContext;
~~~

Jakarta Persistence 3.0 trở lên chuyển sang namespace:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
~~~

Đây là thay đổi package/API boundary quan trọng, không phải chỉ thay tên một annotation bằng string replacement.

### 4.1. Những vị trí phải xét

- Entity annotations: `@Entity`, `@Id`, `@OneToMany`, `@Version`.
- Entity listeners và `AttributeConverter`.
- Persistence APIs: `EntityManager`, `Query`, Criteria.
- `persistence.xml` namespaces/schema declarations.
- Validation packages `javax.validation`/`jakarta.validation` nếu framework migration liên quan.
- CDI/JTA/Servlet APIs nếu toàn platform chuyển đổi.
- Static metamodel generated sources.
- Bytecode enhancement plugins.
- ORM provider modules và cache plugins.
- Third-party libraries trả/nhận `javax.persistence.EntityManager`.

### 4.2. Không mix hai types chỉ vì tên gần giống

`javax.persistence.EntityManager` và `jakarta.persistence.EntityManager` là hai Java types khác nhau. Container/proxy hoặc library biên dịch với type cũ không tự có binary compatibility với type mới.

### 4.3. Test compile trước test behavior

Một CI stage chỉ compile domain/repository/service modules có thể bắt API namespace mismatch rất sớm. Sau đó bootstrap provider và chạy integration tests trên database.

### 4.4. Không ghép các API jars khác generation bừa bãi

Trong migration, tránh để cả hai API packages tồn tại mà code và framework dùng lẫn lộn. Nếu một dependency buộc giữ javax, cần kế hoạch nâng/thay/isolating adapter thực tế, không giả định thêm jar jakarta sẽ giải quyết.

---

## 5. Khả năng mới theo phiên bản đặc tả phải được test riêng

Ví dụ:

- `GenerationType.UUID` được chuẩn hóa từ **Jakarta Persistence 3.1**.
- `Query.getSingleResultOrNull()` có trong **Jakarta Persistence 3.2**.
- Các provider có thể có UUID generator hoặc nullable-single-result extension từ trước, nhưng đó không có nghĩa method chuẩn xuất hiện trong API version cũ.

### 5.1. Tính tương thích source

~~~java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

Đoạn trên không thể giả định compile với Jakarta Persistence 3.0/JPA 2.x. Khi xây multi-version test matrix, có thể:
- Giữ portable core module không dùng APIs mới.
- Tách feature module compile riêng trên API version hỗ trợ.
- Dùng adapter abstraction nếu cần hỗ trợ nhiều versions.
- Tránh cố gọi method mới từ một binary target cũ.

### 5.2. getSingleResultOrNull khác getSingleResult

~~~java
Customer customer =
    query.getSingleResultOrNull();
~~~

Trên API hỗ trợ, không có row thì trả null, trong khi nhiều hơn một result vẫn là non-unique condition. Test cả ba tình huống 0/1/nhiều, và phân biệt **scalar result null** với **không có result** khi contract yêu cầu.

### 5.3. Không dùng reflection để che thiếu API

Một workaround reflection có thể làm compile pass nhưng mang runtime dependency bất định. Nếu tổ chức cần hỗ trợ phiên bản cũ, ưu tiên adapter có compile target rõ và integration tests riêng.

---

## 6. Xây baseline behavior trước khi upgrade

Trước khi đổi implementation hoặc API, chạy test suite trên stack hiện tại và lưu:

- Test pass/fail list.
- Hành vi entity CRUD và transaction.
- Schema migration applied version.
- SQL counts ở use cases quan trọng.
- Duration/throughput/p95-p99 cho representative workflows.
- Các known provider-specific differences.
- Test fixture/snapshot data, sanitized khi cần.
- Error mapping/cause chain cho lock/constraint scenarios.
- ID allocation settings, cache providers và fetch plans.

### 6.1. Baseline phải có assertions đúng nghiệp vụ

Nếu baseline test đang dựa vào undefined behavior, nó có thể green chỉ vì provider cũ làm vậy. Khi provider mới tuân chuẩn khác cách provider cũ, cần phân biệt **regression thật** với **test dựa vào giả định sai**.

### 6.2. Đừng snapshot mọi generated SQL verbatim

Chỉ snapshot SQL khi SQL shape là contract hiệu năng/kỹ thuật đã có chủ đích. Còn lại hãy assert row counts, result values, atomicity, constraint semantics và query counts theo khoảng/threshold phù hợp.

### 6.3. Bảo vệ dữ liệu thử nghiệm

Không lấy nguyên production database chứa PII vào CI. Dùng synthetic data hoặc bản đã khử định danh, kiểm tính đại diện của constraints/distribution mà không làm lộ dữ liệu.

---

## 7. Ma trận tương thích cần chạy

Một ma trận minh họa:

| Nhóm | API | Provider | DB | Trọng tâm |
|---|---|---|---|---|
| Baseline | API đang dùng | Provider hiện tại | DB hiện tại | Chứng minh behavior gốc |
| Provider migration | Giữ cùng API | Provider mới | DB hiện tại | Khác biệt implementation |
| API upgrade | API mới | Provider hỗ trợ API mới | DB hiện tại | Namespace/feature changes |
| DB migration | API mới | Provider mới | DB mới | Dialect, constraints |
| Full target | Stack mục tiêu | Stack mục tiêu | Stack mục tiêu | End-to-end correctness |
| Negative compatibility | API cũ | Provider/config không tương thích | DB test | Fail fast/clear diagnostics |

Không phải tổ hợp nào cũng được vendor hỗ trợ. Matrix không nên chạy một combination không hợp lệ rồi kết luận provider có bug vì nó fail.

### 7.1. Phân chia suite theo chi phí

- Mọi pull request: compile, smoke bootstrap, CRUD, query, mapping, transaction basic.
- Hằng ngày hoặc release candidate: provider/database full matrix.
- Trước production cutover: concurrency, load/locking, migration rehearsal, rollback test.

### 7.2. Ghi chính xác identity của từng job

Ví dụ job metadata:

~~~text
api=JakartaPersistence-3.x
provider=Hibernate-or-EclipseLink + exact tested version
database=PostgreSQL + exact tested version
jdk=exact runtime
transaction=RESOURCE_LOCAL
schemaMigration=V27
~~~

Trong hệ thống thật, thay placeholder bằng versions thực tế; không kết luận “tương thích với Hibernate” nếu chỉ test một phiên bản cụ thể.

---

## 8. Entity mẫu để dùng trong test suite portable

Một entity được dùng nhất quán trong các providers:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_code",
        columnNames = {"tenant_id", "customer_code"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "customer_code", nullable = false)
    private String code;

    @Column(nullable = false)
    private String displayName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CustomerStatus status;

    @Version
    private long version;

    @Column(name = "created_at")
    private Instant createdAt;

    protected Customer() {}

    public Customer(
            Long tenantId,
            String code,
            String displayName) {
        this.tenantId = tenantId;
        this.code = code;
        this.displayName = displayName;
        this.status = CustomerStatus.ACTIVE;
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }
    public CustomerStatus getStatus() { return status; }
    public long getVersion() { return version; }

    public void rename(String value) {
        displayName = value;
    }
}

enum CustomerStatus {
    ACTIVE, SUSPENDED
}
~~~

`SEQUENCE` được dùng cho ví dụ trên DB có native sequence. Nếu matrix có database không hỗ trợ, dùng một mapping/profile tương ứng nhưng **ghi rõ vì sao generator khác** thay vì ngầm so sánh khác strategy và quy mọi chênh lệch cho provider.

### 8.1. Entity classes phải cùng nghĩa ở mỗi matrix job

Không sửa business model để test mới pass, trừ khi đó là migration được phê duyệt. Các khác biệt mapping cần được ghi thành adapter/config riêng.

### 8.2. Version và business uniqueness

`@Version` giúp phát hiện stale updates; `UNIQUE(tenant_id,customer_code)` bảo vệ business identity. Không coi một trong hai thay thế cái còn lại.

---

## 9. Mô hình Order và quan hệ cha–con

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines =
        new ArrayList<>();

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.setOrder(null);
    }

    public Long getId() { return id; }
    public List<OrderLine> getLines() {
        return lines;
    }
}
~~~

~~~java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public void setOrder(PurchaseOrder order) {
        this.order = order;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
~~~

Các Java imports và table/sequence DDL cần được cung cấp trong test fixture theo database.

### 9.1. Những contract cần test

- `persist(order)` cascade tạo lines.
- Owning side `OrderLine.order` quyết định FK.
- `removeLine` với persistent child và orphanRemoval xóa child.
- `remove(order)` xóa graph theo cascade policy.
- `merge` của detached graph có behavior được kiểm cụ thể.
- Truy cập lazy relationship được xử lý đúng trong transaction/fetch plan.

### 9.2. Không phụ thuộc thứ tự SQL của hai providers

Một provider có thể batch/reorder INSERT trong giới hạn FK requirements. Assertion phải kiểm rows/FKs, không mặc định parent/children insert statements xuất hiện ở exact log order.

---

## 10. Kiểm bootstrap bằng provider chính xác

Với JPA RESOURCE_LOCAL:

~~~java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "compatibility-test"
    );
~~~

Nếu persistence unit để provider tự chọn, tests có thể khởi tạo provider không mong đợi khi classpath chứa nhiều implementations.

### 10.1. persistence.xml có khai báo provider

Ví dụ về cấu hình của một **profile chỉ chạy Hibernate**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
  <persistence-unit name="compatibility-test"
                    transaction-type="RESOURCE_LOCAL">
    <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
    <class>com.example.Customer</class>
    <class>com.example.PurchaseOrder</class>
    <class>com.example.OrderLine</class>
    <properties>
      <!-- JDBC, dialect và schema settings theo test profile -->
    </properties>
  </persistence-unit>
</persistence>
~~~

XML schema/version và classnames phải khớp API/provider thực tế. Đối với EclipseLink, dùng provider class/config tương ứng, không chỉ thêm hai providers rồi hy vọng service discovery chọn đúng.

### 10.2. Không thay provider bằng classpath tình cờ

Tốt hơn là build/test profile riêng với một implementation được chủ động chọn. Nếu chạy nhiều providers trong cùng JVM, phải cô lập resources/services/enhancement/config và xác minh provider thực tế.

### 10.3. Fail fast khi bootstrap không đúng

Test smoke nên fail khi persistence unit thiếu entity mappings, thiếu connection, unsupported API level, không tạo EntityManager được hoặc chọn sai provider.

---

## 11. Kết cấu test suite tách portable contract và vendor-specific

Đề xuất cấu trúc:

~~~text
test/
  portable/
    CrudContractTest
    MappingContractTest
    QueryContractTest
    TransactionContractTest
    AssociationContractTest
    ConcurrencyContractTest
  provider/
    HibernateExtensionTest
    EclipseLinkExtensionTest
  database/
    PostgresSpecificTest
    MysqlSpecificTest
  migration/
    SchemaUpgradeTest
    LegacyDataCompatibilityTest
  performance/
    WritePathBudgetTest
    NPlusOneBudgetTest
~~~

### 11.1. Portable suite

Chỉ dùng hành vi theo chuẩn và business contract; cùng assertions được chạy trên từng provider-supported combination.

### 11.2. Extension suite

Nếu code dùng Hibernate `@Filter`, `@BatchSize`, custom `UserType`, cache hints, statistics hoặc EclipseLink weaving/descriptor features, phải có test riêng. Chúng không phải portability guarantees.

### 11.3. Database suite

Native JSON operators, partial indexes, sequences, stored procedures và locking nuances phải được test trên DB engine cụ thể.

### 11.4. Không ép portable test phải pass với unsupported feature

Nếu một feature không nằm trong spec version hoặc bị database không hỗ trợ, tách/suppress job với lý do minh bạch; không lén thay assertion.

---

## 12. JUnit 5 harness cho cùng bộ tests nhiều environments

Một harness đơn giản lấy persistence unit từ system property:

~~~java
public final class JpaCompatibilityHarness {

    private JpaCompatibilityHarness() {}

    public static EntityManagerFactory createFactory() {
        String unit = System.getProperty(
            "test.persistence.unit",
            "compatibility-test"
        );

        return Persistence.createEntityManagerFactory(unit);
    }

    public static <T> T transaction(
            EntityManagerFactory emf,
            Function<EntityManager, T> operation) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            T result = operation.apply(em);

            tx.commit();
            return result;
        } catch (RuntimeException | Error problem) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    problem.addSuppressed(rollbackFailure);
                }
            }
            throw problem;
        } finally {
            em.close();
        }
    }
}
~~~

Các imports bao gồm `jakarta.persistence.*` và `java.util.function.Function`. Với Spring/JTA-managed EntityManager, dùng transaction owner của framework thay helper RESOURCE_LOCAL này.

### 12.1. Tại sao mỗi call tạo EntityManager mới?

Một test cần chứng minh DB commit phải đọc từ context khác, tránh first-level cache làm kết quả xanh giả.

### 12.2. Thay provider bằng build profile

Có thể chạy cùng test class ở hai test jobs khác nhau với provider class/dependency/persistence unit khác. Cần ghi rõ JPA version và provider version để kết quả có thể tái lập.

---

## 13. JUnit 5 test kiểm persist/find và commit

~~~java
@Test
void persistAndFind_workAcrossProviders() {
    String code = "C-" + UUID.randomUUID();

    Long id = JpaCompatibilityHarness.transaction(
        emf,
        em -> {
            Customer customer = new Customer(
                42L, code, "Alice"
            );

            em.persist(customer);
            em.flush();

            assertTrue(em.contains(customer));
            assertNotNull(customer.getId());

            return customer.getId();
        }
    );

    Customer reloaded = JpaCompatibilityHarness.transaction(
        emf,
        em -> em.find(Customer.class, id)
    );

    assertNotNull(reloaded);
    assertEquals(42L, reloaded.getTenantId());
    assertEquals(code, reloaded.getCode());
    assertEquals("Alice", reloaded.getDisplayName());
}
~~~

### 13.1. Không đọc trong cùng persistence context

`em.find(Customer.class, id)` ngay sau persist có thể trả managed instance từ L1 mà không chạm SQL, nên không đủ chứng minh transaction đã commit.

### 13.2. Không assert ID trước flush theo mọi strategy

`IDENTITY`, `SEQUENCE`, `TABLE` và `UUID` khác thời điểm cấp ID. Bài test tập trung vào hậu điều kiện sau flush/commit.

### 13.3. Không dùng exact SQL làm correctness oracle

Provider có thể chọn SQL khác nhau mà vẫn lưu đúng dữ liệu.

---

## 14. Test managed dirty checking

~~~java
@Test
void dirtyChecking_updatesManagedEntity() {
    Long id = createCustomerFixture();

    JpaCompatibilityHarness.transaction(emf, em -> {
        Customer managed = em.find(
            Customer.class, id
        );

        managed.rename("Updated Name");

        // Không gọi em.merge(managed).
        return null;
    });

    String title = JpaCompatibilityHarness.transaction(
        emf,
        em -> em.find(
            Customer.class, id
        ).getDisplayName()
    );

    assertEquals("Updated Name", title);
}
~~~

### 14.1. Điều được kỳ vọng

JPA tracks persistent changes của managed entities. Sau transaction commit, fresh context phải đọc thấy changed state.

### 14.2. Không cố định thời điểm SQL UPDATE

Một provider có thể flush trước query, provider khác flush ở commit. Nếu result cuối đúng và contract không phụ thuộc thời điểm, đừng assert UPDATE phải được gửi tại setter.

---

## 15. Test merge detached và returned managed instance

~~~java
@Test
void merge_detachedCopiesStateToManagedResult() {
    Long id = createCustomerFixture();

    Customer detached = JpaCompatibilityHarness.transaction(
        emf,
        em -> em.find(Customer.class, id)
    );

    detached.rename("Detached State");

    JpaCompatibilityHarness.transaction(emf, em -> {
        assertFalse(em.contains(detached));

        Customer managed = em.merge(detached);

        assertTrue(em.contains(managed));
        assertFalse(em.contains(detached));
        assertNotSame(detached, managed);
        assertEquals("Detached State",
                     managed.getDisplayName());

        return null;
    });

    String stored = JpaCompatibilityHarness.transaction(
        emf,
        em -> em.find(
            Customer.class, id
        ).getDisplayName()
    );

    assertEquals("Detached State", stored);
}
~~~

### 15.1. Cả hai providers phải giữ semantics này

`merge` không reattach input object. Nó trả managed instance, copy persistent state theo JPA merge semantics.

### 15.2. Đừng khẳng định merge luôn phát SELECT

Nếu context đã chứa managed instance cùng identity hoặc cache/provider có cách khác, số SQL có thể khác mà contract vẫn đúng.

### 15.3. Test detached stale version riêng

Nếu đã có `@Version`, merge snapshot cũ sau khi concurrent transaction cập nhật phải được kiểm bằng optimistic locking test, không gộp vào bài CRUD thông thường.

---

## 16. Test remove và rollback

~~~java
@Test
void remove_committedEntityDisappears() {
    Long id = createCustomerFixture();

    JpaCompatibilityHarness.transaction(emf, em -> {
        Customer managed = em.find(
            Customer.class, id
        );

        assertNotNull(managed);

        em.remove(managed);
        em.flush();

        return null;
    });

    Customer missing = JpaCompatibilityHarness.transaction(
        emf,
        em -> em.find(Customer.class, id)
    );

    assertNull(missing);
}
~~~

Một test khác nên thực hiện `persist` hoặc `remove`, `flush()` rồi `rollback()` và xác nhận DB không giữ thay đổi sau fresh transaction.

### 16.1. Remove detached không phải operation hợp lệ

Test `em.remove(detached)` phải có expectation theo chuẩn, thường `IllegalArgumentException`. Không “fix” bằng cách bỏ exception ở provider mới.

### 16.2. Không đánh đồng `@PostRemove` với after-commit

Callbacks có thể chạy trước khi transaction quyết định rollback vì một lỗi khác. Compatibility tests phải phân biệt lifecycle event và durable commit.

---

## 17. Test entity lifecycle callbacks

Những callbacks phổ biến:

- `@PrePersist` / `@PostPersist`.
- `@PreUpdate` / `@PostUpdate`.
- `@PreRemove` / `@PostRemove`.
- `@PostLoad`.

### 17.1. Ví dụ

~~~java
@PrePersist
void prePersist() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
~~~

Test:
1. Tạo new entity.
2. Persist và flush trong transaction.
3. Assert basic local state được set.
4. Commit.
5. Fresh read xác nhận database state.

### 17.2. Không bắt callbacks chạy ở exact Java statement

Một provider có thể defer SQL tới flush; thời điểm callback tuân JPA lifecycle nhưng không nhất thiết được trigger giống nhau nếu test chỉ assert ngay sau setter.

### 17.3. Callback ordering khi có inheritance/listeners

Nếu ứng dụng có superclass listener/entity listener và entity callback, kiểm theo đặc tả và mapping. Những callback-specific vendor assumptions nên được tách và ghi rõ.

### 17.4. Đừng gọi EntityManager trong callback cho portability

Nested persistence queries/relationships/external effects trong callbacks thường tạo phụ thuộc không cần thiết và có thể vi phạm portable callback constraints. Đưa nghiệp vụ sang service, outbox hoặc transaction-aware infrastructure.

---

## 18. Access type: Field và property mapping

Hai cách truy cập state:

~~~java
@Id
private Long id;
~~~

hoặc:

~~~java
@Id
public Long getId() {
    return id;
}
~~~

Vị trí placement của `@Id` thường xác định access type mặc định theo JPA mapping conventions.

### 18.1. Test trước upgrade

- Field access annotations trên fields.
- Property access annotations trên getters.
- `@Access(FIELD)`/`@Access(PROPERTY)` được dùng khi cần override.
- `@Transient` đúng vị trí.
- Không vô ý mix annotations ở field/getter làm provider diễn giải khác.

### 18.2. Getter có side effects là nguy hiểm

Một property-access getter tự tải network hoặc mutate state có thể bị gọi theo các đường khác nhau giữa providers. Test cần phát hiện và refactor getter thành thao tác thuần.

### 18.3. Enhancement và proxy

Bytecode enhancement/weaving có thể thay cách track changes hoặc lazy loading. Khi chuyển provider, cần test runtime với instrumentation thực tế, không chỉ compile entity.

---

## 19. Embedded và composite IDs

Với `@EmbeddedId` hoặc `@IdClass`, compatibility tests phải bao gồm:

- Identity equality/hashCode ổn định.
- Fetch/find qua composite PK object.
- Mapping column names/types.
- Relationship `@MapsId` nếu có.
- Composite foreign key references.
- Constraint/DDL alignment trên DB.

### 19.1. Ví dụ embedded ID

~~~java
@Embeddable
public class MembershipKey implements Serializable {
    private Long tenantId;
    private Long userId;

    protected MembershipKey() {}

    public MembershipKey(Long tenantId, Long userId) {
        this.tenantId = tenantId;
        this.userId = userId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof MembershipKey that)) {
            return false;
        }
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(userId, that.userId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, userId);
    }
}
~~~

Imports gồm `java.io.Serializable` và `java.util.Objects`.

### 19.2. Test composite PK không chỉ đọc bằng query

`em.find(Membership.class, new MembershipKey(tenant,user))` phải trả entity chính xác, không trộn rows khi hai tenants dùng cùng user ID.

### 19.3. Provider differences cần phân biệt với mapping sai

Một composite key thiếu `equals/hashCode` phù hợp là mapping/code bug, không được coi là “EclipseLink khác Hibernate nên chấp nhận”.

---

## 20. AttributeConverter, Enum và temporal types

### 20.1. Enum

~~~java
@Enumerated(EnumType.STRING)
private CustomerStatus status;
~~~

Test sau commit dữ liệu vẫn giữ tên enum. Không phụ thuộc ordinal nếu business cần schema ổn định. Nếu đã lưu ordinal, migration cần chuyển dữ liệu theo semantics chứ không chỉ thêm `STRING`.

### 20.2. AttributeConverter

~~~java
@Converter(autoApply = false)
public class CurrencyCodeConverter
        implements AttributeConverter<CurrencyCode, String> {

    @Override
    public String convertToDatabaseColumn(
            CurrencyCode code) {
        return code == null ? null : code.value();
    }

    @Override
    public CurrencyCode convertToEntityAttribute(
            String value) {
        return value == null
            ? null
            : new CurrencyCode(value);
    }
}
~~~

Test persist/readback, null handling, provider invocation và column type mapping. `CurrencyCode` là domain value object do ứng dụng định nghĩa.

### 20.3. Time

Test `Instant`, `LocalDate`, `LocalDateTime` và timezone/precision nếu ứng dụng dùng. Database có thể cắt microseconds/milliseconds hoặc dùng timezone semantics khác.

### 20.4. Numeric

Test `BigDecimal` scale/precision, rounding và DB column definition. Không coi cách JDBC trả numeric scale giống nhau giữa mọi database.

### 20.5. NULL

Kiểm basic field nullable vs not-null, converter null handling và SQL default values. Một field Java null có thể khác DB default khi provider INSERT explicit NULL.

---

## 21. Associations, ownership, cascade và orphanRemoval

Khi đổi provider, graph mapping thường là điểm phát sinh khác biệt.

### 21.1. Owning side

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

`OrderLine.order` sở hữu FK. Test phải set owning side; chỉ thêm vào inverse collection không luôn ghi FK đúng.

### 21.2. Cascade PERSIST

Persist parent có cascade PERSIST phải persist children theo mapping. Fresh read đảm bảo FK và rows đúng.

### 21.3. Cascade MERGE

Merge detached parent với children chỉ propagate khi mapping có MERGE/ALL tương ứng. Kiểm returned managed graph.

### 21.4. Cascade REMOVE

Remove parent có cascade REMOVE phải xử lý children theo contract; DB FK constraints có thể ảnh hưởng deletion ordering.

### 21.5. orphanRemoval

Loại persistent child khỏi parent collection có `orphanRemoval=true` có thể xóa child ở flush/commit. Đừng test bằng new child chưa từng persistent rồi kỳ vọng DELETE SQL.

### 21.6. Many-to-many

Không dùng cascade REMOVE bừa bãi giữa các aggregate roots. Provider thay đổi có thể làm exposed bug trước đây bị che bởi SQL order.

---

## 22. Inheritance strategies

Các chiến lược chuẩn:

- `InheritanceType.SINGLE_TABLE`.
- `InheritanceType.JOINED`.
- `InheritanceType.TABLE_PER_CLASS`.

### 22.1. Test từng strategy thực sự dùng

- Persist subtype, find bằng base type.
- JPQL polymorphic query.
- Discriminator data/mapping.
- Inheritance joins và số result.
- Null/column constraints trong SINGLE_TABLE.
- Foreign key và cascade mapping trên JOINED.
- Union-like query behavior/performance của TABLE_PER_CLASS.

### 22.2. Không khóa provider-specific discriminator SQL

Giữ assertions về subclass type, field values và result set; tách SQL structure expectations vào performance suite.

### 22.3. Constructor/proxy compatibility

Entity classes cần constructor, non-final/access rules theo JPA spec. Một Hibernate optimization từng chấp nhận pattern không portable không đảm bảo provider khác cũng chấp nhận.

---

## 23. JPQL grammar: Chạy query suite trước cutover

Những queries cần test:

~~~java
SELECT c
FROM Customer c
WHERE c.tenantId = :tenantId
  AND c.status = :status
ORDER BY c.id
~~~

~~~java
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.code = :code
~~~

~~~java
SELECT c.status, COUNT(c)
FROM Customer c
WHERE c.tenantId = :tenantId
GROUP BY c.status
~~~

### 23.1. Hibernate HQL extension không đồng nghĩa JPQL portable

Một query có thể dùng syntax/chức năng Hibernate cho phép nhưng chuẩn JPQL hoặc EclipseLink không hỗ trợ. Nếu migration yêu cầu portability, ưu tiên viết JPQL chuẩn hoặc tách provider-specific paths.

### 23.2. Test parse lẫn execute

Named queries có thể được validate khi provider bootstrap hoặc chỉ khi dùng, tùy cấu hình. Test nên chạy cả những queries quan trọng với dữ liệu fixture để kiểm semantics, không chỉ parser.

### 23.3. Test parameter binding

- Named parameters.
- Positional parameters nếu code dùng.
- Enum parameters.
- Entity parameters.
- Collection parameters cho `IN`.
- Null handling có chủ đích.
- Query hints/lock modes riêng.

---

## 24. Result cardinality và exception semantics

Test ba trạng thái đối với `getSingleResult()`:

| Kết quả | Kỳ vọng |
|---|---|
| Không có result | `NoResultException` |
| Đúng một result | Trả result |
| Nhiều hơn một result | `NonUniqueResultException` |

Với `getResultList()`, no-result thường trả list rỗng.

### 24.1. Count và SUM trên tập rỗng

~~~java
Long count = em.createQuery(
    "SELECT COUNT(c) FROM Customer c WHERE c.code = :code",
    Long.class
)
.setParameter("code", "NOT-PRESENT")
.getSingleResult();
~~~

`COUNT` không có GROUP BY thường trả một scalar result bằng 0 khi không có rows match. Các aggregates như `SUM`/`AVG` có thể trả null nếu tập rỗng. Không test như thể cả hai luôn ném NoResult.

### 24.2. GROUP BY thay cardinality

Query `GROUP BY status` có thể trả nhiều results. Gọi `getSingleResult` là query contract sai, không phải provider regression.

### 24.3. Null result và missing result

Một scalar field nullable có thể tạo **một result null**. Đừng nhầm nó với zero-row case. Với API `getSingleResultOrNull`, nếu business cần phân biệt hai trạng thái, thiết kế projection kèm identifier phù hợp.

---

## 25. JOIN, DISTINCT và duplicate entity results

Ví dụ:

~~~java
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.id = :id
~~~

Một Order có ba Lines có thể tạo nhiều SQL joined rows. Provider có thể xử lý entity identity/result de-duplication theo phiên bản và query semantics.

### 25.1. Portable assertion

Nếu nghiệp vụ cần một root entity distinct, thiết kế query rõ:

~~~java
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.id = :id
~~~

Sau đó assert đúng root IDs và không duplicate business results.

### 25.2. DTO projection khác entity identity

~~~java
SELECT new com.example.LineView(
    o.id, l.sku
)
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.id = :id
~~~

Nếu Order có ba Lines, projection có thể hợp lệ trả ba DTO rows. Không dựa vào entity-level de-duplication assumption để đòi một DTO.

### 25.3. Left joins

Test cả case entity không có children. `LEFT JOIN` có thể khác `INNER JOIN` ở cardinality, đặc biệt khi WHERE predicate đặt trên bên phải join.

---

## 26. Pagination, count và ORDER BY

~~~java
TypedQuery<Customer> query = em.createQuery(
    """
    SELECT c FROM Customer c
    WHERE c.tenantId = :tenantId
    ORDER BY c.id
    """,
    Customer.class
);

query.setFirstResult(offset);
query.setMaxResults(limit);
~~~

### 26.1. ORDER BY ổn định

Không có deterministic ordering, provider/database có thể trả pages khác dù mọi result đều đúng SQL. Test pagination phải chỉ định sort keys và tie-breaker.

### 26.2. Count phải đồng nhất filters

Data query và count query phải dùng cùng tenant/ACL/business filters. Với joins to-many, có thể cần `COUNT(DISTINCT root)` hoặc `EXISTS` thay vì đếm nhân rows.

### 26.3. Collection fetch joins + pagination

Pagination trên fetch join to-many có thể được xử lý không như mong đợi, thậm chí in-memory hoặc bị chặn theo provider/config. Test với page size nhỏ, parent có nhiều children, và kiểm SQL/query count. Thiết kế ổn định thường là page root IDs rồi fetch graph theo batch.

### 26.4. Keyset pagination

Nếu dùng cursor, test tie-breaker, tenant scope, tương thích kiểu so sánh và inclusive/exclusive boundaries trên từng database.

---

## 27. Criteria API và static metamodel

Một portable Criteria query:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> c = cq.from(Customer.class);

cq.select(c)
  .where(cb.equal(
      c.get("tenantId"), tenantId
  ))
  .orderBy(cb.asc(c.get("id")));

List<Customer> result =
    em.createQuery(cq).getResultList();
~~~

### 27.1. Kiểm Typed Criteria tương đương JPQL

Dùng cùng fixture và so result IDs, ordering và filters. Không so literal SQL strings.

### 27.2. Static metamodel regeneration

Nếu code có `Customer_` generated class, version update có thể yêu cầu annotation processor mới phù hợp namespace/API. Xóa generated sources cũ và rebuild sạch trong CI; không dùng artifact `javax.persistence.metamodel.*` cũ cho module jakarta.

### 27.3. Criteria JOIN/subquery/aggregates

Test complex Criteria roots, `JoinType.LEFT`, correlated subqueries, `cb.exists`, `cb.construct` và GROUP BY nếu code dùng.

### 27.4. Không tái sử dụng Predicate của query khác

Criteria AST nodes thường gắn với query structure. Xây lại root/join/predicate cho count query riêng thay vì lấy nodes từ data query rồi áp vào một query khác tùy ý.

---

## 28. Native SQL và stored procedures

Native SQL vốn gắn với database dialect:

~~~java
List<?> rows = em.createNativeQuery(
    """
    SELECT id, customer_code
    FROM customer
    WHERE tenant_id = :tenantId
    """
)
.setParameter("tenantId", tenantId)
.getResultList();
~~~

### 28.1. Cần test những khác biệt này

- Identifier quoting/case sensitivity.
- SQL function names.
- Pagination syntax.
- `RETURNING`, identity retrieval.
- JSON/array column types.
- Boolean, UUID, timestamp mappings.
- Result scalar types từ JDBC.
- `@SqlResultSetMapping`/constructor mapping.
- Stored procedure parameter modes/types.
- Vendor-specific lock hints.

### 28.2. Đừng dùng native tests để kết luận chuẩn JPQL lỗi

Nếu native SQL chỉ chạy trên PostgreSQL, việc job MySQL fail có thể là unsupported design chứ không phải JPA provider không tuân chuẩn. Tách DB-dependent suite rõ ràng.

### 28.3. Bảo mật cũng phải được kiểm lại

Native query không đương nhiên áp provider filters, tenant/owner predicates hoặc soft-delete restrictions. Khi đổi provider, test mọi native read/write paths với dữ liệu cross-tenant.

---

## 29. Flush modes và query visibility

JPA có `FlushModeType.AUTO` và `COMMIT`.

### 29.1. AUTO

Provider cần bảo đảm query visibility theo AUTO semantics khi pending changes có thể ảnh hưởng kết quả; implementation có thể flush SQL hoặc dùng cách khác.

### 29.2. COMMIT

Tác động của unflushed changes lên queries trước commit không được bảo đảm như AUTO trong mọi trường hợp.

### 29.3. Test strategy

Tách:
- Managed getter sau setter.
- `find` cùng PK trong L1.
- JPQL query trong transaction với pending changes.
- `em.flush()` rõ ràng.
- Commit rồi query trong EM mới.

### 29.4. Không dùng undefined behavior làm portability oracle

Nếu chuẩn không cam kết query visibility trong một tình huống cụ thể, không nên viết cross-provider assertion bắt buộc hai providers trả y hệt. Thay bằng explicit flush hoặc thiết kế transaction/query phù hợp.

---

## 30. RESOURCE_LOCAL, JTA và Spring transactions

Một JPA RESOURCE_LOCAL flow:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    em.persist(customer);

    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
~~~

Trong môi trường JTA hoặc Spring, transaction owner có thể là container/framework. Không tự gọi `em.getTransaction()` trên JTA-managed EntityManager như thể đang dùng RESOURCE_LOCAL.

### 30.1. Regression cases quan trọng

- Transaction commit thành công.
- Rollback sau flush.
- Constraint violation ở flush/commit.
- Nested service calls và transaction propagation.
- Read-only transactions.
- Optimistic lock conflict.
- Transaction timeout.
- Self-invocation với Spring `@Transactional` proxy.
- Commit exception sau method body return.

### 30.2. Không nhầm JPA exception với Spring rollback rule

Một JPA `NoResultException` không tự mark transaction rollback-only theo JPA semantics; nhưng Spring có thể rollback khi unchecked exception thoát transactional proxy theo default rules. Test phải xác định transaction owner.

### 30.3. Commit ACK loss

Khi connection mất ở COMMIT, client có thể không biết DB đã commit hay chưa. Một test retry cần idempotency/operation key và fresh transaction reconciliation, không kết luận rollback chỉ từ exception.

---

## 31. Optimistic locking phải được test trên hai contexts

~~~text
Context A: load Customer version V
Context B: load Customer version V
A updates and commits -> version V+1
B attempts stale update -> conflict
~~~

### 31.1. Test flow

1. Persist fixture và commit.
2. Dùng hai EntityManagers độc lập load cùng row.
3. A sửa và commit.
4. B sửa rồi flush/commit stale snapshot.
5. Assert optimistic-lock failure đúng cause chain.
6. Fresh read xác nhận winner state, không bị lost update.

### 31.2. @Version không giải quyết authorization

Một caller không có quyền vẫn có thể gửi version hợp lệ. Row-level ACL/tenant predicates phải được test riêng khi provider thay đổi.

### 31.3. Exception timing có thể khác

Một provider có thể phát lỗi tại `merge`, một provider khác khi flush/commit. Bọc toàn transactional operation trong assertion để kiểm behavior, không chỉ một Java statement.

### 31.4. Đừng dùng một EntityManager chung

Hai references trong cùng context không tạo hai snapshots độc lập.

---

## 32. Pessimistic locks và timeout hints

Một JPA lock:

~~~java
Customer customer = em.find(
    Customer.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

### 32.1. Các điều cần test

- Lock mode có được DB/provider hỗ trợ không?
- Hai transactions cạnh tranh có bị serialize đúng không?
- Timeout được xử lý theo contract/DB?
- Lock release sau commit/rollback?
- Deadlocks có được ứng dụng retry theo chính sách không?
- `PessimisticLockException` và `LockTimeoutException` xuất hiện/được translate ra sao?

### 32.2. Query hint support không đồng đều

Một số lock/timeout hints có thể chỉ được provider hỗ trợ một phần hoặc bị bỏ qua theo database. Không dùng thời gian `Thread.sleep()` làm oracle chính xác cho mọi CI job; kiểm effect và DB wait metrics khi cần.

### 32.3. Portability target có thể là graceful degradation

Nếu database/provider không hỗ trợ một lock mode tính năng đặc thù, ứng dụng phải có alternate design hoặc fail fast được kiểm thử, không silently coi lock đã được áp dụng.

---

## 33. First-level cache, second-level cache và query cache

### 33.1. First-level cache

Một persistence context quản lý một instance theo entity identity. Test `assertSame` trong cùng EM là portable behavior quan trọng.

### 33.2. Second-level cache

L2 cache configuration, eviction/invalidation, concurrency strategies và supported entities có khác biệt theo provider. Không mặc định Hibernate L2 settings hoạt động khi chuyển sang EclipseLink.

### 33.3. Query cache

Query results caching thường là extension; migration có thể thay key structure/invalidation. Test correct results sau UPDATE/DELETE và tenant scoping, không chỉ cache hit rate.

### 33.4. Test tránh false positives

Khi mục tiêu là DB state:
- Commit.
- Fresh EM/transaction.
- Kiểm cache policy/bypass khi cần.
- Tránh reuse same managed object.
- Dùng query/DB direct evidence khi test consistency.

### 33.5. Multi-tenant cache keys

Một cache thiếu tenant discriminator có thể trộn objects hai tenants cùng numeric ID. Kiểm security/correctness trước khi tối ưu cache hit.

---

## 34. LAZY, EAGER, EntityGraph và provider-specific fetch

Mặc dù mapping có `FetchType.LAZY` hoặc `EAGER`, số SQL và thời điểm load có thể khác tùy provider, enhancement và query plan.

### 34.1. Phân biệt contract và performance

Một contract test chỉ cần xác nhận association data đúng trong permitted transaction scope. Một performance test riêng đo N+1, fetch joins, DB round trips, memory.

### 34.2. LAZY là hint trong một số mappings

Provider có thể eagerly fetch trong những trường hợp JPA cho phép; không viết portable test luôn buộc chính xác một SQL ở lần truy cập association.

### 34.3. EntityGraph

Test named/dynamic entity graphs: attributes được load theo intended fetch plan, không làm leak unrelated relations. Provider-specific attributes/hints phải được tách.

### 34.4. Detached lazy access

Hibernate có thể ném `LazyInitializationException`; provider khác có exception/behavior riêng. App nên map DTO trước khi đóng transaction thay vì phụ thuộc exception type vendor.

---

## 35. Entity listeners, converters và Bean Validation integration

Nếu dự án sử dụng `@PrePersist`/`@PreUpdate` để chuẩn hóa state hoặc Bean Validation cho constraints, compatibility tests phải bao gồm:

- Callbacks chạy đúng lifecycle.
- Validation được kích hoạt tại phase được cấu hình.
- Validation exception được dịch đúng.
- Converter được áp dụng cho basic/embedded fields như mong đợi.
- DB constraints vẫn bảo vệ khi validation không chạy.
- Không có side effects ngoài transaction trước commit.

### 35.1. Bean Validation version có thể đổi package

Khi nâng Jakarta EE stack, API `javax.validation` và `jakarta.validation` là những packages khác nhau. Kiểm dependency compatibility và exception mapping.

### 35.2. Provider không thay domain validation policy

Dù Hibernate và EclipseLink có cách tổ chức flush khác nhau, business validation phải có contract rõ; không phụ thuộc một provider tình cờ kiểm một constraint sớm.

---

## 36. Schema generation và migration DDL

Đừng chỉ bật `create-drop` rồi kết luận provider mới compatible với production schema. Production thường có Flyway/Liquibase hoặc migration scripts được kiểm soát.

### 36.1. Test trên schema do migrations tạo

Một profile nên:
1. Tạo database/schema trống.
2. Apply migrations.
3. Bootstrap provider với schema validation thích hợp.
4. Chạy CRUD/query/concurrency tests.
5. Không cho ORM tự drop/create tables trong phép kiểm migration compatibility.

### 36.2. So sánh mapping với DDL thật

- Column names/length/nullable.
- Primary/foreign keys.
- Unique constraints và composite indexes.
- Enum representation.
- Sequence names/increments.
- Identity columns.
- Timestamp precision/timezone.
- Decimal precision/scale.
- Default values.
- Join tables and constraints.

### 36.3. Provider DDL generator khác nhau là điều bình thường

`@Table(uniqueConstraints)` có thể tạo SQL DDL khác giữa Hibernate và EclipseLink. Production migration scripts phải là source of truth nếu quy trình quản lý schema đã chọn chúng.

### 36.4. Test trên dữ liệu legacy

Một schema mới tạo từ đầu có thể pass trong khi dữ liệu cũ chứa nulls/truncated strings/ordinal enums/legacy formats khiến mapping mới fail. Cần sanitized representative dataset và migration rehearsal.

---

## 37. Sequence, identity và generated keys

Ví dụ:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_seq"
)
@SequenceGenerator(
    name = "customer_seq",
    sequenceName = "customer_seq",
    allocationSize = 50
)
private Long id;
~~~

### 37.1. Những điều cần test

- Sequence/table/identity object tồn tại trên DB.
- IDs không trùng khi concurrent inserts.
- Generated ID available ở thời điểm ứng dụng thực sự cần.
- Flush/rollback không khiến dữ liệu committed sai.
- Provider optimizer tương thích database sequence INCREMENT.
- Rolling deployment không trộn generator algorithms nguy hiểm.
- JDBC batch behavior phù hợp SLO.

### 37.2. Không assert IDs liên tục

Sequences/caches/pooling có thể tạo gaps. Hai transactions không nhất thiết commit theo thứ tự ID.

### 37.3. AUTO là provider-dependent

`GenerationType.AUTO` có thể chọn generator khác khi đổi provider/dialect. Test cần ghi **effective strategy** và đánh giá schema/SQL/latency thật.

---

## 38. Performance compatibility: N+1, batching, flush cost

Một upgrade có thể giữ kết quả SQL đúng nhưng tăng truy vấn từ 2 lên 101.

### 38.1. Các workflow nên benchmark

- List page 50 DTOs.
- Load detail Order + Lines.
- Persist batch 1.000 entities.
- Update 100 versioned rows.
- Delete graph có cascade.
- Count/pagination với JOIN/ACL.
- Export chunking.
- Multi-tenant read.
- Concurrent unique-key inserts.

### 38.2. Metrics

| Metric | Mục đích |
|---|---|
| SQL count/request | Phát hiện N+1 |
| JDBC batches/executions | Kiểm batching |
| p50/p95/p99 latency | Chất lượng dịch vụ |
| DB CPU/WAL/locks | Nút cổ chai |
| Heap/GC | Persistence context và caching |
| Open connections | Transaction/pool behavior |
| Entity fetch counts | Phát hiện unexpected loads |
| Error/retry rate | Tính ổn định |
| Data correctness incidents | Quan trọng hơn micro-optimization |

### 38.3. Không so số query máy móc

Các providers có thể dùng join vs secondary SELECT mà vẫn hoàn thành cùng use case. Chỉ coi thay đổi SQL count là regression nếu ảnh hưởng SLO hoặc vượt guardrail đã định.

### 38.4. Hibernate-specific tuning

`hibernate.jdbc.batch_size`, `hibernate.order_inserts`, `@BatchSize` hoặc `@Fetch` là extensions. Khi đổi provider phải có alternative/config mới; không kỳ vọng thuộc tính Hibernate được EclipseLink tự hiểu.

---

## 39. Spring Data JPA compatibility

Spring Data có các abstractions:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndCode(
        Long tenantId,
        String code
    );
}
~~~

### 39.1. Query derivation

Kiểm:
- Method name parsing.
- Nested associations.
- Optional/list/page/slice return types.
- Null parameter semantics theo business contract.
- Custom `@Query` JPQL/native.
- Projections/DTO constructors.
- Specifications/Criteria.
- Dynamic sorting and pagination.

### 39.2. Exception translation

Spring có thể dịch JPA `NonUniqueResultException`, constraint/lock errors thành `DataAccessException` subtypes. Khi thay provider, concrete cause chain khác. Domain/service tests nên assert error meaning và API mapping, đồng thời kiểm cause khi cần.

### 39.3. Spring @Transactional proxy

Method có thể return trong body trước khi transaction interceptor commit. Một lỗi ở commit boundary có thể xuất hiện ở caller, không bị catch bên trong method. Test phải bao trọn proxy call.

### 39.4. Spring Boot dependency alignment

Spring Boot version thường quản lý bộ phiên bản Spring Data, Hibernate, Jakarta API và driver. Không tự pin một provider major version không được stack hỗ trợ rồi suy test fail là lỗi JPA spec. Cần xác nhận compatibility list trong target environment.

---

## 40. @DataJpaTest và transaction rollback ngầm

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Autowired
    TestEntityManager tem;

    @Test
    void savesCustomer() {
        Customer customer =
            new Customer(42L, "C-123", "Alice");

        Customer saved =
            repository.save(customer);

        tem.flush();
        tem.clear();

        assertTrue(
            repository.findById(
                saved.getId()
            ).isPresent()
        );
    }
}
~~~

### 40.1. Điểm mấu chốt

`@DataJpaTest` theo mặc định thường chạy trong test transaction và rollback sau test. `flush`/`clear` không chứng minh commit durability.

### 40.2. Commit test riêng

Nếu cần kiểm commit/rollback của transaction manager, dùng `TransactionTemplate`, `TestTransaction` hoặc tắt test-level transaction trong test chuyên biệt.

### 40.3. Database replacement

Spring Data slice test có thể tự chọn embedded DB. Khi matrix cần PostgreSQL/EclipseLink cụ thể, cấu hình datasource và provider profile rõ, không để H2 hoặc Hibernate default thay thế rồi làm báo cáo sai.

---

## 41. Testcontainers chạy ma trận database thực

Một Spring integration example:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgresCustomerTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void config(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }
}
~~~

Test image/version phải khớp DB mà project hỗ trợ. Đoạn này không tự chuyển provider; cần build profile tương ứng.

### 41.1. Khi đổi DB

Tạo job/container riêng cho target DB. Không ép native PostgreSQL queries chạy trên MySQL rồi gọi đó là portability nếu application thiết kế DB-dependent.

### 41.2. Testcontainers không tự giải quyết mọi trường hợp

Một container đơn không mô phỏng replication lag, failover, distributed locks hoặc network partition. Cần fault-injection và staged testing cho các use cases đó.

---

## 42. CI matrix không thể chỉ chạy một jar duy nhất tùy hứng

Một kế hoạch CI:

~~~text
Stage 1: Compile
   - API namespace + JDK + metamodel processor

Stage 2: Bootstrap smoke
   - provider baseline + target
   - assert actual implementation

Stage 3: Portable suite
   - CRUD / mappings / JPQL / Criteria
   - constraints / transactions / concurrency

Stage 4: Provider extension suite
   - Hibernate-only features
   - EclipseLink-only features

Stage 5: Database-specific suite
   - native SQL / indexes / locks / schema migrations

Stage 6: Operational acceptance
   - N+1/batch/latency guardrails
   - failover/reconciliation if relevant

Stage 7: Migration rehearsal
   - existing schema/data + target provider
   - rollback plan
~~~

### 42.1. Dependencies cần cô lập

Mỗi matrix job phải nạp đúng provider và API set. Khi provider classes cùng nằm trên classpath, cần explicit selection và test không chọn nhầm.

### 42.2. Không chạy Gradle/Maven để “chỉ báo” nếu chưa được phép

Bài viết mô tả cách thiết kế CI; việc chạy build cụ thể thuộc project workflow ngoài bài.

### 42.3. Contract tests được tái sử dụng

Dùng một code suite cho cả baseline và target để giảm nguy cơ hai suites đặt expectations khác nhau.

---

## 43. Phân loại failure trong ma trận

Khi một test fail, hãy phân loại:

| Nhóm lỗi | Dấu hiệu | Cách xử lý |
|---|---|---|
| API incompatibility | CompileError/NoSuchMethodError | Dependency/API alignment |
| Wrong provider | Runtime implementation không đúng | Classpath/persistence.xml |
| Mapping error | Bootstrap fails, unknown attribute | Annotations/access mapping |
| Dialect/schema | Missing sequence/table/type | DDL migration/config |
| JPQL extension | Query không parse trên provider mới | Viết JPQL portable/adapter |
| Result-semantic bug | Null/cardinality/order sai | Query contract/test fixture |
| Lifecycle regression | Cascade/merge/remove khác expected | Mapping + provider behavior |
| Transaction bug | Rollback/commit khác contract | Transaction owner/cfg |
| Cache bug | Stale/cross-tenant state | Cache keys/invalidation |
| Concurrency issue | Lost update/lock timeout | @Version/locks/isolation |
| Performance regression | N+1/batching p99 xấu | Fetch plan/tuning |
| Test bug | Dựa vào undefined behavior | Sửa test intent và contract |

### 43.1. Không gắn tất cả vào “Hibernate bug”

Có thể chính code đã dùng một HQL extension hoặc mapping thiếu portable annotations. Phải đối chiếu spec, query shape và expected business contract.

### 43.2. Khi behavior khác chuẩn

Nếu provider thực sự vi phạm behavior chuẩn đã xác định, giữ minimal reproduction và report đúng version/DB. Tạm workaround ở application cần được test để không tạo rủi ro mới.

---

## 44. Ưu tiên assertions bền vững qua provider

Một quy tắc:

- Assert **row values** thay vì exact SQL text.
- Assert **managed vs detached** thay vì internal proxy class.
- Assert **transaction committed state** qua fresh read thay vì ID.
- Assert **constraint failure meaning** thay vì exact vendor message.
- Assert **optimistic conflict** thay vì exact timing.
- Assert **query result cardinality** thay vì physical joined-row count.
- Assert **scope/authorization** trên returned IDs thay vì raw SQL formatting.
- Assert **latency/SQL budgets** trong performance suite, không biến mọi functional test thành microbenchmark.

### 44.1. Một số khác biệt vẫn cần test exact

Nếu application phụ thuộc một custom SQL function, stored procedure hoặc provider-specific hint, nên assert exact integration behavior trong suite tương ứng — nhưng gắn nó với explicit dependency, không gọi đó là portable JPA contract.

---

## 45. Lập migration plan trước khi đổi provider

Một quy trình an toàn:

1. Inventory dependencies và vendor extensions.
2. Freeze baseline tests và known limitations.
3. Xác nhận provider mới hỗ trợ API/JDK/DB stack.
4. Chạy compile/boot smoke với test profile mới.
5. Chạy portable CRUD/mapping/query suite.
6. Chạy transaction/cascade/locking/constraint suites.
7. Chuyển các provider-specific annotations/hints.
8. Đối chiếu migrations/DDL và test legacy data.
9. Đo hiệu năng target workload.
10. Chạy staged rehearsal với dữ liệu synthetic/sanitized.
11. Quan sát metrics/exception mapping.
12. Chuẩn bị rollback nếu phát sinh data/latency regression.
13. Rollout từng phần theo business/tenant/environment khi thiết kế cho phép.
14. Theo dõi post-cutover correctness, không chỉ uptime.

### 45.1. Những changes không đảo ngược được dễ dàng

Đổi enum ordinal sang string, PK type Long → UUID, column precision, sequence allocator, discriminator mapping hoặc schema layout có thể cần data migration. Rollback code một mình không hoàn tác schema/data.

### 45.2. Rolling deploy với hai versions

Nếu hai app versions cùng chạy trên một database, cần kiểm schema compatibility, sequence optimizer/ID allocation và event/DTO compatibility. Một provider mới có thể tạo IDs/schema assumptions không tương thích provider cũ.

### 45.3. Không đổi schema bằng ORM create-drop trong rollout

Production migrations phải rõ ràng và có recovery plan. Không bật auto drop/create vì provider mới báo schema không khớp.

---

## 46. Kiểm thử cutover/rollback có dữ liệu thật tương đương

Một rehearsal nên có:

~~~text
Existing database schema + sanitized data
                 |
                 v
     Apply migration scripts
                 |
                 v
     Start target provider/API
                 |
                 v
   Run compatibility contract suite
                 |
                 v
   Validate checksums/counts/keys/FKs
                 |
                 v
       Perform representative writes
                 |
                 v
    Test rollback-compatible path
                 |
                 v
      Confirm invariant remains true
~~~

### 46.1. Không chỉ test schema trống

Một schema trống không phát hiện legacy nulls, duplicated business keys, invalid dates, unrecognized enum strings hoặc mapping data incompatibilities.

### 46.2. Read/write validation

Sau migration, kiểm persisted rows, referential integrity, counts, aggregates và domain rules; không chỉ kiểm table tồn tại.

### 46.3. Rollback plan cần xét dữ liệu mới

Một code version cũ có thể không đọc được rows vừa ghi bởi version mới, dù schema downgrade có vẻ thành công. Vì vậy rollback rehearsal phải bao gồm **writes do target version tạo ra**.

---

## 47. Khi nào phải giữ provider-specific adapter?

Đôi khi ứng dụng cần tính năng không có trong JPA chuẩn:

- Advanced batch fetch/statement tuning.
- Vendor-specific custom types.
- Database lock hints.
- Special temporal/JSON mappings.
- Provider-specific cache APIs.
- Advanced SQL/query extensions.

### 47.1. Đừng trộn extension xuyên domain

Tách vào persistence adapter/module hẹp để việc chuyển provider không đòi sửa business logic.

### 47.2. Có contract cho adapter

Ví dụ `DocumentSearchPort.search(...)` phải trả đúng DTOs và authorized IDs. Hibernate adapter và EclipseLink adapter có thể dùng kỹ thuật khác nhưng pass cùng contract suite.

### 47.3. Không cố “portable hóa” mọi thứ bằng abstraction quá rộng

Nếu target chỉ chạy một provider/DB và extension mang lợi ích rõ, việc giữ nó có thể hợp lý — miễn được ghi nhận và kiểm thử, thay vì giả định hệ thống có thể đổi provider không tốn chi phí.

---

## 48. Quan sát compatibility sau upgrade

Theo dõi:

- Lỗi bootstrap/query parsing.
- Rollback/constraint/optimistic lock errors.
- Unexpected null values/empty pages.
- Cross-tenant authorization denials hoặc leaks.
- N+1, SQL counts, slow queries.
- Connection pool wait/timeout.
- Cache hit/miss và stale data incidents.
- Sequence allocation/generator anomalies.
- DB locks/deadlocks.
- GC/heap sau entity graph loads.
- Outbox lag/retry if applicable.
- API error rate và business correctness metrics.

### 48.1. Tách lỗi có thật khỏi thay đổi telemetry

Provider mới có thể đổi tên logs/metrics. Khi error counter giảm, cần xác minh liệu lỗi đã hết hay chỉ instrumentation mapping không còn nhận được event.

### 48.2. Alert về data correctness quan trọng hơn SQL formatting

Một duplicate business operation hay cross-tenant leak cần ưu tiên cao hơn việc SQL dùng alias khác.

---

## 49. Anti-pattern thường gặp khi kiểm tương thích

| Anti-pattern | Vấn đề | Thay thế |
|---|---|---|
| Chỉ compile rồi tuyên bố tương thích | Không test mapping/query/DB | Bootstrap + integration |
| Không assert provider runtime | Test có thể dùng provider cũ | Explicit provider selection |
| Ghép javax/jakarta API jars | Binary/type mismatch | Dependency alignment |
| Test chỉ trên H2 | Bỏ qua dialect/locks | DB production-like |
| So exact SQL text mọi query | Brittle với alias/order | Assert behavior |
| Không test dữ liệu legacy | Migration gặp dữ liệu cũ lỗi | Rehearsal sanitized data |
| Dùng `find` trong cùng EM làm DB proof | L1 cache false positive | Fresh transaction |
| Dựa vào ID để xác nhận commit | ID có trước commit | Commit + readback |
| Test `merge` như attach input | Sai lifecycle | Returned managed instance |
| Test SQL timing không được spec hứa | False regression | Hậu điều kiện |
| Chọn AUTO rồi không kiểm generator | ID allocation thay đổi | Effective generator check |
| Bỏ qua @Version | Lost updates sau upgrade | Two-context test |
| Chỉ test SELECT | Bulk DML/DELETE vẫn lỗi | Full mutation suite |
| Bỏ qua COUNT/PAGE | Data leak/pagination sai | Scoped count/page tests |
| Quên native SQL | Provider filters không áp | DB/vendor suite |
| Chỉ test entity root, bỏ associations | FK/cascade/lazy lỗi | Graph tests |
| Dùng vendor hints như standard | Bị bỏ qua | Extension suite |
| @DataJpaTest rollback mà nghĩ đã commit | False confidence | TransactionTemplate |
| Không test target dependencies | Runtime class conflicts | CI dep lock/inspection |
| Đổi provider + DB + JDK cùng lúc | Khó debug | Matrix theo trục |
| Không có rollback rehearsal | Không quay lại được | Cutover/rollback plan |

---

## 50. Bài tập thực hành

### Bài 1. Đổi Hibernate sang EclipseLink

Một test chỉ kiểm `assertNotNull(em)` đã đủ chưa?

**Đáp án:** Chưa. Cần assert provider thực tế, mappings, queries và DB transactions.

### Bài 2. javax sang jakarta

Vì sao đổi imports có thể chưa đủ?

**Đáp án:** Binary API, persistence.xml, provider, validators, processors và dependencies phải đồng bộ namespace.

### Bài 3. GenerationType.UUID

Có thể compile với JPA 2.2 không?

**Đáp án:** Không phải enum chuẩn của JPA 2.2; được chuẩn hóa ở Jakarta Persistence 3.1.

### Bài 4. getSingleResultOrNull

Có nên gọi trực tiếp từ module target Jakarta Persistence 3.0?

**Đáp án:** Không nếu API target không có method; cần nâng API/support hoặc dùng portable alternative.

### Bài 5. Hai providers sinh SQL khác alias

**Đáp án:** Không nhất thiết là incompatibility nếu behavior và performance contract đúng.

### Bài 6. @DataJpaTest save rồi clear

**Đáp án:** Có thể vẫn trong test transaction rollback mặc định; chưa chứng minh committed durability.

### Bài 7. Find ngay sau persist

**Đáp án:** Có thể trả L1 managed instance; dùng fresh transaction/EM để đọc DB committed state.

### Bài 8. Merge detached

**Đáp án:** Managed copy được trả; detached input không tự attach.

### Bài 9. Sequence allocationSize

**Đáp án:** Cần khớp generator optimizer và DDL; migration có thể đổi sequence calls/gaps.

### Bài 10. AUTO

**Đáp án:** Provider/dialect quyết định strategy; cần kiểm effective generator.

### Bài 11. Query HQL chạy Hibernate, fail EclipseLink

**Đáp án:** Xác định có dùng HQL extension ngoài JPQL không; viết portable query hoặc adapter.

### Bài 12. Count(*) khác data page

**Đáp án:** Kiểm same filters, join cardinality, `COUNT(DISTINCT)`/EXISTS và tenant scope.

### Bài 13. JOIN to-many

**Đáp án:** Test root results vs joined rows; dùng DISTINCT/projection đúng contract.

### Bài 14. SUM no rows

**Đáp án:** Có thể trả scalar null thay vì ném NoResult; kiểm đúng aggregate semantics.

### Bài 15. JPQL grouped aggregates

**Đáp án:** Có thể trả nhiều results; dùng list thay vì getSingleResult.

### Bài 16. Criteria metamodel không compile

**Đáp án:** Kiểm annotation processor và generated types có namespace/API đúng.

### Bài 17. Enum persisted ordinal

**Đáp án:** Thay sang STRING cần data migration; không chỉ thay annotation.

### Bài 18. Instant precision khác DB

**Đáp án:** Test readback với precision/tolerance đúng schema, không đòi nanosecond preservation khi DB không hỗ trợ.

### Bài 19. Cascade child không lưu

**Đáp án:** Kiểm cascade PERSIST và owning side FK; không suy do provider ngay.

### Bài 20. OrphanRemoval không xóa child new

**Đáp án:** Kiểm child persistent state và spec semantics; đừng giả định new orphan phải phát DELETE.

### Bài 21. @Version stale update

**Đáp án:** Dùng hai contexts độc lập và kiểm optimistic-lock conflict + final DB state.

### Bài 22. Lock timeout

**Đáp án:** Kiểm vendor/DB hỗ trợ hints, transaction ownership và error translation.

### Bài 23. Hibernate @Filter trên native SQL

**Đáp án:** Không mặc định native queries áp mọi provider filter. Test explicit tenant policy hoặc DB RLS.

### Bài 24. Provider mới N+1

**Đáp án:** Functional tests có thể vẫn pass; performance suite phải đo SQL count/latency và sửa fetch plan.

### Bài 25. Old app và new app cùng ghi IDs

**Đáp án:** Rolling deployment phải kiểm generator algorithm và sequence DDL tương thích để tránh collisions.

### Bài 26. Production schema do Flyway quản lý

**Đáp án:** Test migrations + provider validation, không dựa vào ORM create-drop.

### Bài 27. Chỉ dùng database trống

**Đáp án:** Chưa phát hiện legacy data incompatibilities; cần sanitized migration rehearsal.

### Bài 28. Cache sau upgrade

**Đáp án:** Kiểm invalidation, cross-tenant keys, stale reads và extension configs.

### Bài 29. Native SQL trả numeric type khác

**Đáp án:** JDBC/provider scalar mapping có thể khác; dùng explicit mapping/conversion và integration tests trên DB target.

### Bài 30. Rollback code sau target writes

**Đáp án:** Cần kiểm old version đọc được schema/rows mới, không chỉ rollback deploy artifact.

---

## 51. Checklist chuyển provider hoặc đặc tả

1. Đã ghi rõ phiên bản API/JDK/provider/DB/driver?
2. Đã kiểm runtime đúng provider?
3. Có baseline portable contract suite?
4. Có phân biệt spec features và extensions?
5. Có kiểm `javax` ↔ `jakarta` dependency boundary?
6. Có nâng annotation processor/static metamodel?
7. Có smoke bootstrap với đúng persistence unit?
8. Có cấu hình RESOURCE_LOCAL/JTA/Spring transaction owner?
9. Có test persist/find/merge/remove?
10. Có commit + fresh-context readback?
11. Có test flush rồi rollback?
12. Có test dirty checking trên managed entity?
13. Có test merge trả managed copy?
14. Có test detached/remove invalid cases?
15. Có test callbacks không phải after-commit?
16. Có test @Version stale update hai contexts?
17. Có test pessimistic locks/timeout nếu dùng?
18. Có test PK/unique/FK constraints trên DB thật?
19. Có test sequence/identity/UUID generators?
20. Có khớp pooled generator và DB sequence?
21. Có test attribute converters/enum/temporal/numeric?
22. Có test embedded/composite keys và @MapsId?
23. Có test inheritance/discriminators?
24. Có test owning side/cascade/orphanRemoval?
25. Có test lazy/EntityGraph/fetch joins?
26. Có test JPQL và Criteria trên fixture thực?
27. Có test named queries được load/executed?
28. Có test scalar null, COUNT/SUM/GROUP BY?
29. Có test pagination stable ORDER BY và count?
30. Có test JOIN to-many cardinality?
31. Có test native SQL/stored procedures nếu dùng?
32. Có test bulk UPDATE/DELETE khác entity lifecycle?
33. Có test tenant/ACL scope và DTO projections?
34. Có test L1/L2/query cache consistency?
35. Có ghi nhận SQL counts, N+1, batching/latency budgets?
36. Có chạy trên DB engine/version đại diện production?
37. Có chạy migration scripts, không chỉ create-drop?
38. Có dùng sanitized legacy data?
39. Có test Spring Data repository derivation/Optional/Page?
40. Có test exception translation và HTTP mapping?
41. Có kiểm @DataJpaTest rollback mặc định?
42. Có CI matrix tách API/provider/DB dimensions?
43. Có tránh unsupported combinations bị chấm nhầm?
44. Có test rolling deployment old/new versions?
45. Có rollback/cutover rehearsal chứa target writes?
46. Có metrics/alerts cho correctness sau cutover?
47. Có tài liệu hóa mọi provider-specific workaround?
48. Có plan xử lý schema changes khó đảo ngược?
49. Có đảm bảo tests không phụ thuộc thứ tự chạy?
50. Có fail fast khi runtime/provider không như kỳ vọng?

---

## 52. Sơ đồ ra quyết định

~~~text
           Dự định đổi JPA provider / API version
                           |
                           v
                 Inventory existing stack
                           |
                           v
              Xác nhận target combination
                 được vendor hỗ trợ?
                    /          \
                  Không         Có
                   |            |
                   v            v
              Chọn target    Compile/bootstrap
                khác           smoke
                               |
                               v
                    Portable contract suite
                       /            \
                     Fail           Pass
                      |               |
                      v               v
               Phân loại lỗi     Extension/DB suites
               - spec violation       |
               - app assumptions      v
               - config/DDL      Performance budgets
                      |               |
                      v               v
                 Fix + rerun     Data migration rehearsal
                                      |
                                      v
                             Rollback plan verified?
                                  /       \
                                Không      Có
                                  |         |
                                  v         v
                             Chưa cutover  Staged rollout
                                             |
                                             v
                                  Monitor correctness + SLO
~~~

### 52.1. Không đưa một test green vào production bằng mọi giá

Nếu phải tắt một assertion về transaction atomicity, uniqueness hay authorization mới pass, vấn đề chưa được giải quyết. Cần thay implementation hoặc sửa test contract khi có căn cứ đặc tả/nghiệp vụ rõ ràng.

---

## 53. Tổng kết

1. **Tương thích JPA có ba lớp**: source/binary, behavior và vận hành; compile pass chỉ kiểm được một phần.
2. **Xác nhận provider runtime chính xác** là điều kiện đầu tiên của provider matrix.
3. **`javax.persistence` → `jakarta.persistence` là thay đổi API/package boundary**, yêu cầu dependency, processors và platform alignment.
4. **Không dùng API mới trên target cũ**: ví dụ `GenerationType.UUID` của Jakarta Persistence 3.1 và `getSingleResultOrNull` của 3.2.
5. **Test behavior được spec bảo đảm**, không buộc các providers sinh SQL/proxy class/statement order giống nhau.
6. **Fresh EntityManager/transaction sau commit** giúp phân biệt persistence-context state với committed database state.
7. **Persist/find/merge/remove, cascade, orphanRemoval, converters, embedded IDs và inheritance** đều cần regression coverage theo mappings đang dùng.
8. **JPQL/Criteria/query cardinality/pagination** phải được chạy trên fixtures thật, không chỉ parse query.
9. **Transactions/locks/optimistic concurrency** cần integration tests có DB và nhiều contexts riêng.
10. **Native SQL, hints, caches, Hibernate/EclipseLink extensions** phải tách thành suites có dependency rõ.
11. **Schema migrations và legacy data** quan trọng hơn việc một provider mới tự tạo schema sạch thành công.
12. **Spring @DataJpaTest thường rollback ngầm**, nên test committed behavior phải tạo ranh giới transaction riêng.
13. **Performance compatibility** cần đo N+1, batching, p95/p99 và DB waits, không chỉ CRUD correctness.
14. **CI matrix, migration rehearsal và rollback plan** giúp nhận diện mismatch trước cutover.
15. **Giữ chính sách bảo mật và invariants nghiệp vụ** xuyên suốt providers, bao gồm tenant scope, uniqueness và transaction atomicity.

Một cuộc đổi provider/đặc tả JPA thành công là cuộc đổi mà ứng dụng vẫn **đọc đúng, ghi đúng, rollback đúng, chống lost update đúng và không lộ dữ liệu**, dù SQL, proxies, query planning và cache internals có thể khác. Hãy định nghĩa những điều phải giữ dưới dạng bộ kiểm thử hành vi có thể chạy lặp lại, ghi rõ môi trường mỗi lần chạy và coi khác biệt provider-specific như một dependency cần quản lý — không phải điều có thể bỏ qua cho đến khi production gặp lỗi.
