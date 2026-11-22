# Kiểm thử N+1 và số câu SQL của kế hoạch tải trong JPA

Một truy vấn JPA có thể trả kết quả đúng, test nghiệp vụ vẫn xanh, nhưng ứng dụng lại thực hiện hàng trăm hoặc hàng nghìn câu SQL để xử lý một trang dữ liệu. Đây là biểu hiện điển hình của **N+1 query problem**: một câu SQL lấy danh sách entity gốc, tiếp theo là N câu SQL hoặc nhiều nhóm SQL bổ sung khi ứng dụng truy cập những quan hệ chưa được tải.

Ví dụ:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o ORDER BY o.id",
        PurchaseOrder.class)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getName()
    );
}
~~~

Với `PurchaseOrder.customer` là `@ManyToOne(fetch = LAZY)` và mỗi đơn hàng tham chiếu một Customer khác nhau, có thể phát:

~~~sql
SELECT * FROM purchase_orders ORDER BY id; -- 1
SELECT * FROM customers WHERE id = ?;      -- 2
SELECT * FROM customers WHERE id = ?;      -- 3
SELECT * FROM customers WHERE id = ?;      -- 4
SELECT * FROM customers WHERE id = ?;      -- ...
~~~

Một trang 50 đơn hàng có thể cần 51 SELECTs để lấy thông tin khách hàng. Nhưng con số thực **không luôn bằng N+1**: first-level cache, second-level cache, số Customer identities khác nhau, batch fetching, fetch graph và provider version có thể ảnh hưởng.

**Mục tiêu của bài** là tạo được những **integration tests đo SQL thật**, tái hiện N+1 có kiểm soát, đặt **SQL budget** cho từng use case, so sánh các kế hoạch tải như JOIN FETCH/EntityGraph/DTO/batch fetching và kiểm thử những góc khuất: lazy initialization, cache che lỗi, pagination, cartesian multiplication, count queries, flush, transaction boundary và sự khác biệt giữa số statement, số JDBC batches và số SQL rows.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cơ chế phát sinh N+1 trên to-one và to-many associations.
2. Phân biệt câu SQL chính, secondary selects, lazy loading và N+1.
3. Thiết kế test fixtures để lỗi hiện rõ thay vì bị L1/L2 cache che đi.
4. Đếm SQL qua Hibernate Statistics, SQL interception hoặc JDBC DataSource instrumentation.
5. Phân biệt prepared statement count, executed SQL, query execution count, entity load count và JDBC batch count.
6. Viết JUnit integration tests khẳng định query budget của một use case.
7. Kiểm tra tác động của `JOIN FETCH`, `EntityGraph`, `DTO projection`, batch fetching và subselect loading.
8. Không kết luận “ít SQL hơn” đồng nghĩa “nhanh hơn” khi result set và object graph phình to.
9. Kiểm thử phân trang với fetch join to-many, count query và bước fetch thứ hai.
10. Tổ chức regression tests, metrics và performance baselines cho kế hoạch tải.

## 2. N+1 là gì?

Khi tải danh sách entity gốc:

~~~text
SELECT Orders                       1 query
    |
    +-- Load Customer of Order 1    1 query
    +-- Load Customer of Order 2    1 query
    +-- Load Customer of Order 3    1 query
    ...
    +-- Load Customer of Order N    1 query
                                   --------
                           Total ~ N + 1
~~~

N+1 không phải một loại lỗi cú pháp JPQL. Nó phát sinh khi **kế hoạch tải** không đáp ứng **mẫu truy cập dữ liệu** của application.

Ví dụ một màn hình chỉ hiển thị mã đơn hàng và tổng tiền có thể không cần fetch Customer. Nhưng màn hình hiển thị tên Customer cạnh mỗi đơn sẽ dereference association, khiến những lần load phụ xảy ra nếu fetch plan không phù hợp.

### Hai điều độc lập

- Query lấy Order có thể nhanh.
- Code chuyển Order sang response DTO có thể thực hiện thêm hàng loạt queries.

Nếu chỉ đo thời gian và số SQL của câu `getResultList()` mà bỏ qua bước mapping/serialization, test có thể bỏ sót N+1.

## 3. N+1 trên quan hệ to-one

Ví dụ mapping:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

Lệnh:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class)
    .getResultList();
~~~

có thể chỉ load Orders. Khi gọi:

~~~java
for (PurchaseOrder o : orders) {
    String customerName =
        o.getCustomer().getName();
}
~~~

provider phải giải quyết tên Customer. Nếu Customer chưa ở persistence context/cache và không có fetching optimization, các SELECT riêng có thể xuất hiện.

### Vì sao dùng getName chứ không chỉ getId?

Một lazy proxy có thể biết ID mà không cần khởi tạo toàn entity. `o.getCustomer().getId()` **có thể không phát SQL**, nên test dùng ID sẽ không đảm bảo tái hiện lazy initialization.

Hãy truy cập một thuộc tính không phải identifier, hoặc một collection thực sự cần duyệt, theo đúng use case.

## 4. N+1 trên quan hệ to-many

Mapping:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Query:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class)
    .getResultList();
~~~

Sau đó:

~~~java
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        consume(line);
    }
}
~~~

Provider có thể dùng một SELECT cho Orders và thêm một SELECT cho collection của mỗi Order:

~~~sql
SELECT ... FROM purchase_orders;
SELECT ... FROM order_lines WHERE order_id = ?;
SELECT ... FROM order_lines WHERE order_id = ?;
...
~~~

### Vì sao không chỉ test `lines.size()`?

Một số provider-specific extra-lazy optimizations có thể thực hiện `COUNT(*)` thay vì khởi tạo cả collection. Nếu use case thực sự cần các lines và dữ liệu của chúng, test nên **duyệt các phần tử hoặc đọc field** như production code.

## 5. N+1 không đồng nghĩa đúng N câu SELECT phụ

Giả sử 20 Orders cùng thuộc một Customer.

~~~text
20 Order rows
1 distinct Customer identity
~~~

Trong cùng persistence context, provider có thể load Customer một lần rồi tái sử dụng managed instance. Tổng query có thể gần 2, không phải 21.

Các yếu tố khác:

- Hibernate batch fetching.
- Second-level cache.
- EntityGraph hoặc JOIN FETCH.
- Subselect collection fetching.
- To-one EAGER mặc định hoặc provider fetch strategy.
- Một số associations đã managed trước.

**Bài test có giá trị phải kiểm soát các yếu tố này** và nêu rõ kỳ vọng: “một câu SELECT” hay “không tăng tuyến tính theo N”.

## 6. Vì sao unit test với Mockito không đủ?

Ví dụ:

~~~java
when(repository.findAll()).thenReturn(
    List.of(order1, order2)
);
~~~

Các entity mocks hoặc Java objects tự tạo không đi qua ORM:

- Không có proxy thật.
- Không có JDBC statements.
- Không có persistence context lifecycle.
- Không có lazy initialization.
- Không có generated SQL.

Mockito unit test phù hợp kiểm tra business logic, nhưng không thể chứng minh query plan có N+1 hay không.

### Phải dùng integration test

Một N+1 regression test cần:

1. JPA provider thật.
2. Entity mappings thật.
3. Database/test datasource.
4. Data fixtures.
5. Transaction boundary phù hợp.
6. SQL measurement.
7. Access pattern thực sự kích hoạt associations.

## 7. Test cần đo cả use case, không chỉ repository query

Mẫu thường gặp:

~~~java
public List<OrderRow> listOrders() {
    List<PurchaseOrder> orders =
        repository.findRecentOrders();

    return orders.stream()
        .map(o -> new OrderRow(
            o.getId(),
            o.getCustomer().getName(),
            o.getTotalAmount()
        ))
        .toList();
}
~~~

Nếu SQL counter chỉ bao quanh `repository.findRecentOrders()`, phần `getCustomer().getName()` có thể bị bỏ sót. Test nên đo **toàn bộ service call**, kể cả mapping DTO.

### Sơ đồ instrumentation

~~~text
SQL recorder START
    |
    +-- repository query
    |
    +-- association dereference
    |
    +-- DTO mapping
    |
SQL recorder STOP
    |
assert SQL budget
~~~

Không đếm cả schema setup, fixture insert, cleanup hoặc transaction commit nếu SQL budget muốn đo read path; nếu cần đo cả transaction, phải đặt contract rõ.

## 8. Mô hình dữ liệu dùng cho các ví dụ

Giả sử hệ thống có:

~~~text
Customer
  id, name

PurchaseOrder
  id, code, totalAmount
  customer_id (FK -> Customer)

OrderLine
  id, order_id, productCode, quantity
~~~

Mô hình:

~~~text
Customer 1  <----  N PurchaseOrder
                          |
                          | 1:N
                          v
                       OrderLine
~~~

Các ví dụ dùng `PurchaseOrder` thay vì class `Order` để không nhập nhằng với `ORDER BY` trong code/query.

## 9. Customer entity

~~~java
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
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
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
~~~

Để quan sát to-one N+1, các fixture Orders nên tham chiếu **nhiều Customer identities khác nhau**, không cùng một Customer.

## 10. PurchaseOrder entity

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = CascadeType.ALL,
        orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String code,
            Customer customer,
            BigDecimal totalAmount) {
        this.code = code;
        this.customer = customer;
        this.totalAmount = totalAmount;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
~~~

Ví dụ `addLine()` duy trì hai phía của quan hệ trong Java; `OrderLine.order` là owning side do `@ManyToOne`.

## 11. OrderLine entity

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String productCode, int quantity) {
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public void setOrder(PurchaseOrder order) {
        this.order = order;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Các entity ở ví dụ sử dụng SEQUENCE để dễ tạo fixture; ID allocation có thể sinh SQL liên quan sequence. **Không tính SQL tạo fixture hoặc ID generation vào budget của read path**.

## 12. Bộ dữ liệu test phải cố tình làm N+1 lộ ra

Nên tạo ít nhất:

~~~text
Customer A -> Order A -> 2 Lines
Customer B -> Order B -> 2 Lines
Customer C -> Order C -> 2 Lines
Customer D -> Order D -> 2 Lines
~~~

Mỗi Customer riêng và Order có Lines riêng.

Trong fixture setup:

~~~java
for (int i = 0; i < 4; i++) {
    Customer customer =
        new Customer("Customer-" + i);
    em.persist(customer);

    PurchaseOrder order = new PurchaseOrder(
        "ORDER-" + i,
        customer,
        new BigDecimal("100.00")
    );

    order.addLine(new OrderLine("SKU-A", 1));
    order.addLine(new OrderLine("SKU-B", 2));

    em.persist(order);
}
~~~

### Vì sao phải flush/clear?

Nếu vừa persist fixtures xong mà cùng EntityManager query trở lại, các entity vẫn managed và relationships có thể đã initialized từ Java constructors. Test có thể không phát secondary SELECT nào.

**Luồng đúng:**

~~~text
Create fixture
    |
    v
Flush and commit
    |
    v
Fresh EntityManager / clear context
    |
    v
Reset SQL counters
    |
    v
Run measured query + access associations
~~~

Để test số SQL thật ổn định, tốt nhất tách fixture transaction khỏi measured transaction và dùng EntityManager/persistence context mới.

## 13. Kiến trúc một test đo N+1

~~~text
Arrange:
  - Create dataset, commit
  - Ensure first-level cache empty
  - Disable or isolate second-level cache
  - Reset counters

Act:
  - Run query under test
  - Access fields required by API
  - Force lazy associations to initialize

Assert:
  - Business results đúng
  - SQL SELECT/statement count trong budget
  - No unexpected extra loads

Cleanup:
  - Finish transaction
  - Close EntityManager
  - Reset capture/clean fixtures
~~~

Không nên chỉ assert SQL count mà quên kiểm tra dữ liệu: một method có thể “đạt 1 SQL” đơn giản vì không thực sự truy xuất Customer hoặc trả thiếu OrderLines.

## 14. Instrumentation: những số đếm khác nhau

| Chỉ số | Nó nói gì? | Hạn chế |
| --- | --- | --- |
| Hibernate `getPrepareStatementCount()` | Số prepared JDBC statements do provider chuẩn bị | Không phải rows/round trips, global statistics |
| Hibernate `getEntityLoadCount()` | Số entity loads theo statistics semantics | Không bằng SQL count |
| Hibernate `getQueryExecutionCount()` | Số lần thực hiện tracked queries theo Hibernate | Không bao quát mọi SQL phụ |
| Hibernate `getCollectionFetchCount()` | Collection fetch activity | Provider-specific, không là total SQL |
| `StatementInspector` | SQL statement strings Hibernate chuẩn bị | Không nhất thiết phản ánh exact DB executions/batches |
| DataSource/JDBC proxy | Calls vào JDBC connection/statement/execute | Phải lọc fixture/metadata statements và setup |
| DB query log/tracing | Statements DB thực nhận | Có thể gồm nhiều requests/sessions |
| SQL row count | Số rows được đọc/trả | Không bằng số SQL statements |
| JDBC batch count | Batch executions | Một batch có nhiều DML statements |

**Đặt tên metric chính xác**. “Có 1 QueryExecutionCount” không có nghĩa chỉ có 1 SELECT ở JDBC nếu lazy loads xảy ra.

## 15. Hibernate Statistics: cách bật

Ví dụ Hibernate ORM:

~~~properties
hibernate.generate_statistics=true
~~~

Trong Spring Boot integration test, property Hibernate có thể được cung cấp qua:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Đây là **Hibernate-specific instrumentation**, không phải API chuẩn JPA.

Lấy statistics:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();
~~~

Một số methods:

~~~java
long prepared = statistics.getPrepareStatementCount();
long loaded = statistics.getEntityLoadCount();
long fetched = statistics.getEntityFetchCount();
long collections =
    statistics.getCollectionFetchCount();
~~~

Ý nghĩa chính xác có thể khác theo Hibernate version và mapping; dùng những counters phù hợp mục tiêu thay vì coi chúng là SQL parser.

## 16. Hibernate Statistics: đo delta, không đo tổng lịch sử

Ví dụ:

~~~java
long before =
    statistics.getPrepareStatementCount();

List<PurchaseOrder> orders = queryOrders();
for (PurchaseOrder o : orders) {
    consume(o.getCustomer().getName());
}

long after =
    statistics.getPrepareStatementCount();

long preparedStatements = after - before;
~~~

Nếu không có SQL khác xen vào trên cùng SessionFactory, delta hữu ích để phát hiện N+1.

### Vấn đề global counters

Hibernate Statistics thường thuộc **SessionFactory**, tức nhiều threads/requests có thể cùng tăng counter.

Trong một test chạy song song:

~~~text
Test A reads before=100
Test B executes 30 statements
Test A executes 5 statements
Test A reads after=135
~~~

Test A tưởng chính nó dùng 35 statements. Vì vậy SQL budget test dùng global statistics phải **chạy cô lập**, hoặc chọn instrumentation theo connection/thread/request.

### Không reset global statistics bừa bãi

`statistics.clear()` có ích trong test cô lập nhưng gây nhiễu nếu test khác cùng SessionFactory đang chạy. Nếu suite song song, dùng resource lock/isolation hoặc per-connection SQL capture.

## 17. Test N+1 to-one với Hibernate Statistics

Ví dụ JUnit 5 integration test (fixture đã commit, Hibernate statistics đã bật và L2 cache không che kết quả):

~~~java
@Test
void lazyCustomerAccessMayCauseNPlusOne() {
    EntityManager em = emf.createEntityManager();
    try {
        SessionFactory sf =
            emf.unwrap(SessionFactory.class);
        Statistics statistics = sf.getStatistics();

        long before =
            statistics.getPrepareStatementCount();

        List<PurchaseOrder> orders = em.createQuery(
                "SELECT o FROM PurchaseOrder o " +
                "ORDER BY o.id",
                PurchaseOrder.class)
            .getResultList();

        List<String> names = new ArrayList<>();
        for (PurchaseOrder order : orders) {
            names.add(
                order.getCustomer().getName()
            );
        }

        long statements =
            statistics.getPrepareStatementCount() -
            before;

        assertEquals(4, orders.size());
        assertEquals(4, names.size());
        assertEquals(5L, statements);
    } finally {
        em.close();
    }
}
~~~

Con số **5** ở đây là **kỳ vọng của fixture và cấu hình thí nghiệm**: 1 SELECT Orders + 4 SELECT Customers. Nó không phải một bảo đảm JPA ở mọi database/provider/cache configuration.

### Chú ý transaction

Ví dụ đang quan sát lazy loads bên trong một EntityManager còn mở. Với Spring/JTA production, service nên khai báo transaction read-only khi cần consistency và đảm bảo toàn bộ DTO mapping nằm trong boundary thích hợp.

### Đây là test tái hiện, không phải test regression được phép pass mãi

Test này chứng minh đường đọc naive sinh N+1 trong môi trường cụ thể. Sau khi sửa, có thể giữ nó như test minh họa; regression test quan trọng hơn là test **kế hoạch tải tối ưu** có SQL count thuộc budget.

## 18. Regression test bằng JOIN FETCH cho to-one

Khi use case cần Order và Customer name, có thể viết:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "JOIN FETCH o.customer " +
        "ORDER BY o.id",
        PurchaseOrder.class)
    .getResultList();
~~~

Khi truy cập:

~~~java
for (PurchaseOrder o : orders) {
    consume(o.getCustomer().getName());
}
~~~

Customer đã được tải theo fetch plan nên không cần secondary SELECT cho Customer trong trường hợp mapping và query này.

### Test SQL budget

~~~java
@Test
void fetchJoinCustomerUsesOneSelect() {
    EntityManager em = emf.createEntityManager();
    try {
        Statistics stats =
            emf.unwrap(SessionFactory.class)
                .getStatistics();

        long before =
            stats.getPrepareStatementCount();

        List<PurchaseOrder> orders = em.createQuery(
                "SELECT o FROM PurchaseOrder o " +
                "JOIN FETCH o.customer ORDER BY o.id",
                PurchaseOrder.class)
            .getResultList();

        List<String> names = orders.stream()
            .map(o -> o.getCustomer().getName())
            .toList();

        long sqlCount =
            stats.getPrepareStatementCount() - before;

        assertEquals(4, names.size());
        assertEquals(1L, sqlCount);
    } finally {
        em.close();
    }
}
~~~

**Kỳ vọng một prepared statement** hợp lý cho fixture đơn giản, một query và không có SQL phụ. Nếu provider/DB tạo thêm statement không thuộc read plan, nên dùng SQL capture để phân loại thay vì xóa assertion cho qua.

## 19. JOIN FETCH khác JOIN bình thường

Hai query:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.name LIKE :prefix
~~~

và:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.code LIKE :prefix
~~~

không có cùng mục đích.

`JOIN` thường dùng cho điều kiện/truy vấn dựa trên relationship; nó **không nhất thiết yêu cầu provider materialize association làm initialized state**.

`JOIN FETCH` yêu cầu tải association vào fetch plan tương ứng.

### Trong test

Không chỉ assert JPQL có từ `JOIN`. Phải truy cập `o.getCustomer().getName()` sau query và đo có secondary SELECT hay không.

## 20. Khi LEFT JOIN FETCH cần thiết

Nếu `PurchaseOrder.customer` là optional:

~~~jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.customer
ORDER BY o.id
~~~

`LEFT JOIN FETCH` giúp giữ các Orders không có Customer. `INNER JOIN FETCH` có thể loại bỏ Orders không match relationship.

### Correctness trước SQL count

Một test đạt “1 SELECT” nhưng thiếu những Orders optional là **sai chức năng**. Phải assert số/root identities và dữ liệu nullability, không chỉ query count.

Trong ví dụ entity trước đó, customer `optional=false` nên INNER JOIN phù hợp. Với một domain khác cho phép null, dùng LEFT JOIN phù hợp và kiểm thử fixtures có null.

## 21. EntityGraph là một cách thiết lập fetch plan

JPA hỗ trợ entity graph:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o ORDER BY o.id",
        PurchaseOrder.class)
    .setHint(
        "jakarta.persistence.fetchgraph",
        graph
    )
    .getResultList();
~~~

### Có chắc EntityGraph tạo một SQL JOIN?

Không nên khẳng định vậy trên mọi provider/query/database. EntityGraph định nghĩa **những attributes cần được fetched**, còn provider quyết định cách thực thi, có thể là JOIN hoặc selects phụ tùy chiến lược.

### Test nên khẳng định gì?

- Association cần thiết được dùng trong context mở mà không phát sinh N+1 theo budget đã định.
- Dữ liệu đầy đủ và đúng.
- SQL budget đáp ứng SLA.

Một assertion “chính xác một JOIN syntax” không phải contract portable của EntityGraph.

## 22. So sánh fetchgraph và loadgraph

JPA có:

~~~text
jakarta.persistence.fetchgraph
jakarta.persistence.loadgraph
~~~

Về ý định:

- `fetchgraph`: các attributes được chỉ rõ có fetch semantics thích hợp cho graph; các attributes không nằm trong graph được định hướng lazy theo spec/provider constraints.
- `loadgraph`: các attributes trong graph được fetch, còn attributes khác theo mapping defaults.

### Cần đo khi có EAGER relationships khác

Nếu Order có Customer, SalesRep, ShippingAddress với mappings khác nhau, EntityGraph thiếu kiểm soát có thể vẫn tải nhiều associations hoặc phát secondary selects.

Trong test, cần nhìn **tất cả SQL của use case**, không chỉ association đang tối ưu.

## 23. JPA EAGER mặc định không bảo đảm không có N+1

Một mapping:

~~~java
@ManyToOne
private Customer customer;
~~~

thường có default fetch type **EAGER**. Nhưng “EAGER” là yêu cầu về thời điểm dữ liệu sẵn sàng, **không bắt buộc phải dùng đúng một SQL JOIN**.

Với JPQL chọn Orders, provider có thể dùng secondary selects để đáp ứng EAGER mapping, dẫn tới nhiều SQL.

### Bài test nên quan sát thực tế

Không suy:

~~~text
EAGER => 1 SQL
LAZY  => N+1
~~~

Đây là suy luận sai. LAZY + JOIN FETCH đúng use case có thể rất hiệu quả; EAGER nhiều associations có thể tạo SQL hoặc object graph lớn.

## 24. Tái hiện N+1 trên to-many

Với mỗi Order có hai Lines:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o ORDER BY o.id",
        PurchaseOrder.class)
    .getResultList();

List<String> productCodes = new ArrayList<>();
for (PurchaseOrder order : orders) {
    for (OrderLine line : order.getLines()) {
        productCodes.add(line.getProductCode());
    }
}
~~~

Trong fixture bốn Orders với collections LAZY không batch fetching, kỳ vọng trực giác:

~~~text
SELECT Orders              1
SELECT Lines of Order A    1
SELECT Lines of Order B    1
SELECT Lines of Order C    1
SELECT Lines of Order D    1
----------------------------
Total                      5
~~~

### Test count và dữ liệu

~~~java
@Test
void lazyLinesCanTriggerNPlusOne() {
    EntityManager em = emf.createEntityManager();
    try {
        Statistics stats =
            emf.unwrap(SessionFactory.class)
                .getStatistics();

        long before =
            stats.getPrepareStatementCount();

        List<PurchaseOrder> orders = em.createQuery(
                "SELECT o FROM PurchaseOrder o " +
                "ORDER BY o.id",
                PurchaseOrder.class)
            .getResultList();

        int lineCount = 0;
        for (PurchaseOrder o : orders) {
            for (OrderLine line : o.getLines()) {
                assertNotNull(line.getProductCode());
                lineCount++;
            }
        }

        long count =
            stats.getPrepareStatementCount() - before;

        assertEquals(8, lineCount);
        assertEquals(5L, count);
    } finally {
        em.close();
    }
}
~~~

Giống ví dụ to-one, đây là baseline fixture-specific, không phải portable guarantee. Batching, SUBSELECT, L2 cache hoặc provider optimization có thể giảm statement count.

## 25. JOIN FETCH to-many: giảm SELECT nhưng có chi phí khác

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT DISTINCT o FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "ORDER BY o.id",
        PurchaseOrder.class)
    .getResultList();
~~~

Trong fixture bốn Orders, tám Lines:

~~~text
SQL statements: có thể 1
SQL rows:       có thể 8 hoặc nhiều hơn tùy JOIN
Managed:        4 Orders + 8 Lines
~~~

Nếu một Order có 10.000 Lines, một SQL JOIN FETCH có thể trả 10.000 rows cho riêng Order đó.

### Vì sao cần kiểm tra số root Orders?

To-many join nhân số physical rows; tùy provider/version, duplicate root results được xử lý khác nhau. `DISTINCT` thường được dùng để diễn tả unique roots; hiệu ứng SQL/provider phải được xác nhận thực tế.

### SQL count không đủ

Một test 1 SQL có thể đạt budget mà vẫn chuyển hàng triệu rows qua network và làm JVM OOM. Nên đo đồng thời **statement count, rows returned, peak heap và latency** trong performance tests.

## 26. Không fetch join nhiều to-many collections vô điều kiện

Giả sử:

~~~text
Order
   10 Lines
   20 Events
~~~

Một JOIN FETCH cả Lines và Events có thể tạo:

~~~text
10 × 20 = 200 SQL rows cho một Order
~~~

Đây là cartesian multiplication trên collections. Một số Hibernate mappings với nhiều bags còn có thể không hỗ trợ fetch đồng thời và ném exception.

### Kế hoạch thay thế

- Fetch to-one associations cùng root query.
- Fetch một to-many collection nếu thật sự cần và result bounded.
- Dùng secondary batched collections query.
- DTO projections/aggregations.
- Hai hoặc nhiều queries có controlled scope.

**Mục tiêu không phải ép tất cả dữ liệu vào một SELECT**; mục tiêu là đạt latency, memory và SQL budget tổng thể mà vẫn đúng kết quả.

## 27. Query count phải đi cùng row count

Hai kế hoạch:

~~~text
Plan A:
  6 SQL statements
  6 × 50 rows
  bounded DTOs

Plan B:
  1 SQL JOIN
  100,000 rows
  huge managed graph
~~~

Không thể kết luận Plan B luôn tốt hơn chỉ vì `1 < 6`.

Các chỉ số:

- Number of statements.
- Total result rows transferred.
- Selected columns/bytes.
- Time spent in JDBC/materialization.
- Heap retained by persistence context.
- Database locks/sorts/temp memory.

Đặt SQL budget như một **regression guardrail**, đồng thời có performance benchmarks khác cho workloads lớn.

## 28. Batch fetching trên to-one/to-many

Hibernate có provider-specific batch fetching, ví dụ:

~~~java
@BatchSize(size = 16)
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

hoặc collections theo mapping/provider:

~~~java
@BatchSize(size = 16)
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
~~~

Khi truy cập một lazy association, provider có thể nhóm IDs của nhiều chưa-initialized proxies/collections thành câu SELECT theo `IN (...)` hoặc cơ chế tương đương.

### Mô hình

~~~text
Không batch:
  1 + N selects

Có batch size B:
  root SELECT + một số batched SELECT
  số SELECT thường giảm đáng kể
~~~

Không khẳng định chính xác `1 + ceil(N/B)` trong mọi tình huống vì L1/L2 cache, collection groups, fetch strategies và provider behavior khác nhau.

## 29. Test batch fetching

Một regression test có thể:

1. Tạo fixture N=40 Orders thuộc 40 Customers.
2. Bật batch fetching theo provider configuration.
3. Clear context và reset counter trong test cô lập.
4. Load Orders bằng một root query.
5. Truy cập Customer name của tất cả Orders.
6. Khẳng định SQL count nhỏ hơn một budget được đo trên stack thực.

### Ví dụ assertion

~~~java
assertTrue(
    statements <= 6,
    "Expected bounded batched fetching"
);
~~~

Giá trị 6 **chỉ là ví dụ**. Chọn threshold sau khi đo provider/driver/mapping thực tế, không áp dụng mù cho mọi môi trường.

### Vì sao test N=4 có thể không đủ?

Nếu batch size 16 và N=4, cả một batch cũng chỉ có ít dữ liệu. Với N=40, sự khác biệt giữa N+1 và batch strategy rõ hơn.

## 30. Subselect fetching của Hibernate

Với collections, Hibernate có thể hỗ trợ subselect fetching theo mapping/cấu hình:

~~~text
SELECT orders WHERE ...
  |
  v
Khi truy cập một collection:
  SELECT lines WHERE order_id IN (
    SELECT id FROM ... original order query ...
  )
~~~

Hình thức SQL thực tế tùy provider/version/database.

### Không phải JPA portable

Subselect fetching là tối ưu provider-specific. Nó có thể tải collections của nhiều Orders cùng lúc, giảm secondary SQL, nhưng cũng có thể fetch nhiều rows hơn một request thực sự cần.

### Cách kiểm thử

Đo cả SQL count và rows/heap; không chỉ assert không còn N+1.

## 31. DTO projection: không cần entity graph để hiển thị danh sách

Nếu màn hình chỉ cần Order code, Customer name, total:

~~~java
public record OrderRow(
    Long id,
    String code,
    String customerName,
    BigDecimal totalAmount
) {}
~~~

JPQL:

~~~java
List<OrderRow> rows = em.createQuery(
        "SELECT NEW com.example.dto.OrderRow(" +
        "o.id, o.code, c.name, o.totalAmount) " +
        "FROM PurchaseOrder o " +
        "JOIN o.customer c " +
        "ORDER BY o.id",
        OrderRow.class)
    .getResultList();
~~~

Đây là một SELECT projection trả DTO, không cần managed Customer entity cho từng row chỉ để đọc name.

### Regression test

Đo statements cho toàn query và assert DTO fields đúng. Không bắt buộc initialized state của Customer vì use case không cần entity graph.

### Bảo mật dữ liệu

DTO còn giúp giới hạn fields public; song query vẫn cần tenant/authorization predicates theo hệ thống thực tế.

## 32. Test DTO projection SQL budget

~~~java
@Test
void orderSummaryProjectionUsesBoundedSql() {
    EntityManager em = emf.createEntityManager();
    try {
        Statistics stats =
            emf.unwrap(SessionFactory.class)
                .getStatistics();

        long before =
            stats.getPrepareStatementCount();

        List<OrderRow> rows = em.createQuery(
                "SELECT NEW com.example.dto.OrderRow(" +
                "o.id, o.code, c.name, o.totalAmount) " +
                "FROM PurchaseOrder o " +
                "JOIN o.customer c ORDER BY o.id",
                OrderRow.class)
            .getResultList();

        long count =
            stats.getPrepareStatementCount() - before;

        assertEquals(4, rows.size());
        assertEquals(1L, count);
        assertTrue(
            rows.stream()
                .allMatch(row -> row.customerName() != null)
        );
    } finally {
        em.close();
    }
}
~~~

Kỳ vọng 1 prepared statement phù hợp fixture/query đơn giản. Khi projection thêm calculations, joins hoặc server-generated SQL khác, xem SQL log và điều chỉnh **query design**, không chỉ tăng budget.

## 33. Lazy access sau khi EntityManager đóng

Ví dụ:

~~~java
List<PurchaseOrder> orders;
EntityManager em = emf.createEntityManager();
try {
    orders = em.createQuery(
            "SELECT o FROM PurchaseOrder o",
            PurchaseOrder.class)
        .getResultList();
} finally {
    em.close();
}

for (PurchaseOrder order : orders) {
    consume(order.getCustomer().getName());
}
~~~

Nếu Customer chưa được initialized, Hibernate có thể ném `LazyInitializationException` hoặc provider-specific error.

### N+1 và LazyInitializationException là hai triệu chứng khác

- Context còn mở → lazy loads có thể chạy và gây N+1.
- Context đã đóng → lazy loads không thể thực thi trong một số providers → exception.

Đừng “sửa” LazyInitializationException bằng cách giữ EntityManager mở xuyên mọi layer/serialization mà không kiểm tra SQL count. Có thể chuyển exception thành N+1 ẩn.

## 34. Open EntityManager in View có thể che N+1

Trong một số Spring web applications, Open EntityManager in View (OSIV) giữ persistence context mở qua controller/JSON serialization.

~~~text
Service query Orders
        |
        v
Service transaction ends
        |
        v
Controller serializes Orders
        |
        v
Lazy Customer loads -> many SELECTs
~~~

Nếu test chỉ chạy service method rồi dừng counter, nó có thể bỏ sót SQL do Jackson getter traversal trong view phase.

### Cách tốt hơn

Trả DTO được dựng trong transactional service và đo cả mapping. Với endpoint cố tình cho lazy graph serialization, cần HTTP integration test đo SQL trọn request và kiểm tra response fields.

## 35. Flush SQL không phải N+1

Một test:

~~~java
em.persist(new Customer("New"));

List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class)
    .getResultList();
~~~

Trong flush AUTO mode, provider có thể thực hiện flush trước query nếu cần; fixture/transaction khác cũng có thể tạo INSERT/UPDATE/sequence statements.

### Hệ quả với assertions

Nếu SQL counter đếm mọi statement từ lúc tạo fixture, kết quả 1+N có thể bị lệch bởi INSERT, SELECT sequence, UPDATE, DDL.

**Đặt measurement window chính xác**:

~~~text
fixture setup -> flush/commit
new context -> start SQL recorder
root SELECT + association access
stop recorder -> assert SELECT count
~~~

Để test toàn use case ghi, có thể đo INSERT/UPDATE riêng nhưng không gọi chúng là N+1 SELECT.

## 36. Không nhầm query execution count với statement count

Ví dụ:

~~~java
List<PurchaseOrder> orders =
    em.createQuery("SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class)
      .getResultList();

for (PurchaseOrder o : orders) {
    consume(o.getCustomer().getName());
}
~~~

Hibernate có thể thống kê một HQL/JPQL query execution, nhưng các secondary SELECTs khởi tạo proxies vẫn có JDBC statements khác.

### Dùng đúng counter

Đối với câu hỏi “bao nhiêu câu SQL đã được chuẩn bị/thực hiện?”, `getPrepareStatementCount()` hoặc JDBC interception liên quan trực tiếp hơn `getQueryExecutionCount()`.

Đối với “bao nhiêu entity objects được load?”, dùng entity load/fetch counters và heap metrics.

Không đổi tên metric trong báo cáo cho dễ đẹp mà làm mất ý nghĩa.

## 37. Một SELECT có thể fetch nhiều rows

JOIN FETCH to-many:

~~~sql
SELECT o.*, l.*
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id;
~~~

Một statement có thể trả hàng chục nghìn result rows. JPA provider phải materialize và de-duplicate entities theo identity trong context.

### Test nên kiểm tra

- SQL statement count.
- Root entity count/IDs.
- Child collection counts.
- Duplicate roots theo API contract.
- Rows transferred và query latency ở performance tests.
- Peak heap/GC với các Orders có collection lớn.

**SQL count test là cần thiết, nhưng không đủ để kết luận một fetch plan tối ưu.**

## 38. Pagination với collection fetch join: bài toán riêng

Ví dụ tưởng hợp lý:

~~~java
List<PurchaseOrder> page = em.createQuery(
        "SELECT DISTINCT o FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines ORDER BY o.id",
        PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Với to-many join, một Order có thể chiếm nhiều SQL rows. Áp LIMIT/OFFSET trực tiếp lên physical rows dễ làm collections bị tải một phần hoặc page thiếu root entities. Tùy provider/version, pagination trên collection fetch có thể bị cảnh báo, xử lý **in-memory** hoặc từ chối.

### Một test chỉ đếm 1 SELECT bỏ sót gì?

- Provider tải toàn bộ Orders/Lines rồi mới lấy 20 roots.
- Response đúng 20 Orders nhưng SQL chuyển hàng trăm nghìn rows.
- Truy vấn dùng nhiều heap và CPU.
- Page rất chậm khi dataset tăng.

### Hibernate guardrail

Một số phiên bản Hibernate hỗ trợ:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Khi được hỗ trợ/bật, property giúp phát hiện usage nguy hiểm thay vì silently pagination in-memory. Đây là **Hibernate-specific behavior**, không phải JPA portable API.

## 39. Two-step ID pagination rồi fetch associations

**Bước 1 — lấy page IDs** bằng stable order:

~~~java
List<Long> ids = em.createQuery(
        "SELECT o.id FROM PurchaseOrder o " +
        "WHERE o.createdAt >= :from " +
        "ORDER BY o.createdAt DESC, o.id DESC",
        Long.class)
    .setParameter("from", from)
    .setMaxResults(pageSize)
    .getResultList();
~~~

**Bước 2 — fetch collections cho các IDs ấy**:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT DISTINCT o FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines WHERE o.id IN :ids",
        PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

Ví dụ giả định `PurchaseOrder.createdAt` được map trong domain thực và `pageSize` đã giới hạn.

### Cần làm thêm

- Nếu `ids` rỗng, không chạy bước 2.
- Áp tenant/authorization predicates ở **cả hai bước** khi cần, không chỉ tin IDs.
- Giới hạn số IDs để tránh quá nhiều query parameters.
- Bước 2 không bảo đảm thứ tự của list `ids`; khôi phục thứ tự theo bước 1.
- Cân nhắc isolation/snapshot consistency giữa hai queries.
- Query COUNT riêng nếu API cần exact totalElements.

### SQL budget

Không phải mọi màn hình phải đạt một SQL. **Hai hoặc ba SQL cố định** có thể tốt hơn một giant JOIN FETCH làm phình result set.

## 40. Test two-step pagination

Fixture:

~~~text
30 Orders, mỗi Order có nhiều Lines
Page size = 10
~~~

Regression test:

~~~text
Expect:
  10 root Orders distinct và đúng thứ tự
  đủ OrderLines của mỗi root
  không lazy SELECT phụ trong bước DTO mapping
  1 SELECT ids
  1 SELECT fetch page data
  0 hoặc 1 COUNT tùy API
  không in-memory pagination trên collection fetch
~~~

Ví dụ:

~~~java
assertEquals(10, orderDtos.size());
assertEquals(2L, preparedStatements);
~~~

Con số 2 chỉ phù hợp khi thực tế có đúng hai queries và không có COUNT. Nếu có third SQL có chủ đích, cần mô tả budget thay vì bỏ test.

## 41. COUNT query là một SQL có chủ đích

Một pageable API có thể cần:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.createdAt >= :from
~~~

Một plan thực tế:

~~~text
1 SELECT root ids
1 SELECT fetch page
1 SELECT COUNT (nếu cần total)
~~~

Ba queries này **không phải N+1**. Chúng là một lượng query cố định, không tăng tuyến tính với số root entities.

### Count với joins

Một JOIN to-many có thể nhân rows; cần `COUNT(DISTINCT o.id)` hoặc thiết kế `EXISTS`/predicate count tương đương khi phù hợp. Kiểm thử totalElements trong dataset có Orders nhiều Lines, không chỉ Orders mỗi bên một Line.

### Slice thay Page

Nếu UI chỉ cần `hasNext`, có thể dùng `pageSize + 1` results mà không yêu cầu exact count. Khi Spring Data hỗ trợ, `Slice` là abstraction hữu ích. Nhưng đừng bỏ COUNT nếu business contract thực sự cần tổng.

## 42. Test tăng N để thấy query scaling

Một SQL budget test mạnh có thể đo hai quy mô:

~~~text
Fixture nhỏ:  5 Orders, 5 Customers
Fixture lớn: 50 Orders, 50 Customers

Naive lazy:
  ~6 và ~51 SELECTs

JOIN FETCH to-one:
  ~1 và ~1 SELECT
~~~

Đây là số dự kiến với fixture/provider không có cache/batch fetching. Không phải luật tuyệt đối JPA.

### Assertion theo tăng trưởng

~~~java
assertTrue(
    largeSqlCount <= smallSqlCount + 1
);
~~~

Với provider có batch fetching thresholds, giới hạn cho phép tăng theo số batches thay vì buộc luôn bằng 1. Điểm quan trọng là tránh growth gần N khi user đang tải N associations.

### Công bằng

Hai runs phải dùng context/cache state tương đương; nếu lần lớn được warm cache từ lần nhỏ, kết quả có thể đánh lừa.

## 43. L1 cache có thể che N+1

Trong cùng EntityManager:

~~~java
Customer cached = em.find(Customer.class, customerId);
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

consume(order.getCustomer().getName());
~~~

Nếu Customer đã managed, có thể không có secondary SELECT.

### Với fixture

Không đo trên chính EntityManager vừa persist Customer/Order. Dùng:

~~~java
em.flush();
em.clear();
~~~

hoặc tốt hơn commit fixture, mở EntityManager/persistence context mới rồi bắt đầu measurement.

## 44. L2 cache cũng có thể che N+1

Khi L2 bật, lần truy vấn sau có thể:

~~~text
Cold run: 1 + N SELECTs
Warm run: 1 SELECT và nhiều L2 cache hits
~~~

Trong integration test **cold fetch plan**, tắt L2/query cache hoặc evict có kiểm soát trước khi đo:

~~~java
emf.getCache().evictAll();
~~~

Đây là API cho shared cache, **không thay `em.clear()` của L1**. Không evict global L2 trong production hoặc các tests chạy song song mà không cô lập.

### Không dùng cache như bản vá duy nhất

Cache miss, instance khởi động mới và dữ liệu mới vẫn có thể gặp N+1. Query plan vẫn phải có giới hạn SQL.

## 45. Query cache cũng làm biến thiên số SQL

Một số providers có query cache độc lập với entity cache:

~~~text
N+1 baseline test:
  L1 fresh
  L2 off
  query cache off

Caching benchmark:
  explicit warm-up
  eviction policy rõ
  separate performance expectations
~~~

Định nghĩa test profile rõ trước khi đo. Không kết luận fetch plan đã tốt chỉ vì repeated warm-query có ít JDBC statements.

## 46. @DataJpaTest và transaction test

Trong Spring Boot, `@DataJpaTest` thường mở transaction cho test và rollback cuối test. Nó phù hợp kiểm thử repositories/mappings nhưng có các bẫy:

- Fixtures còn managed sau persist.
- Test transaction dài hơn production service transaction.
- Lazy access trong test vẫn được phép vì context mở.
- Test database có thể khác production.

### Cách cải thiện

Sau tạo fixtures:

~~~java
em.flush();
em.clear();
// Reset/start SQL measurement here.
~~~

Nếu cần thật sự kiểm tra transaction boundary/commit/cross-request behavior, viết integration test với transaction manager và production-like DB thay vì chỉ dựa vào một rollback-only test transaction.

## 47. H2 và production DB có thể khác

In-memory H2 có thể đủ để phát hiện nhiều N+1 query patterns, nhưng khác production về:

- SQL dialect/pagination SQL.
- Query optimizer và statistics.
- Locking/isolation.
- JDBC driver fetch/batch behavior.
- Statement timeout/cancellation.

Với kiểm thử SQL plans, pagination performance, DB-specific fetching và locking, nên có suite trên DB engine/version gần production (ví dụ containerized test database).

**SQL count tests** có thể chạy nhanh; **load/performance benchmarks** có thể chạy định kỳ riêng để tránh làm CI mất ổn định.

## 48. Hibernate StatementInspector quan sát SQL text

Hibernate có `StatementInspector` để quan sát hoặc sửa SQL trước JDBC prepare. Test-only implementation:

~~~java
import org.hibernate.resource.jdbc.spi.StatementInspector;
import java.util.ArrayList;
import java.util.List;

public final class TestSqlInspector
        implements StatementInspector {

    private static final ThreadLocal<List<String>> SQL =
        ThreadLocal.withInitial(ArrayList::new);

    @Override
    public String inspect(String sql) {
        SQL.get().add(sql);
        return sql;
    }

    public static void beginCapture() {
        SQL.get().clear();
    }

    public static List<String> endCapture() {
        try {
            return List.copyOf(SQL.get());
        } finally {
            SQL.remove();
        }
    }
}
~~~

Cấu hình khi dùng Hibernate:

~~~properties
hibernate.session_factory.statement_inspector=com.example.test.TestSqlInspector
~~~

Với Spring Boot:

~~~properties
spring.jpa.properties.hibernate.session_factory.statement_inspector=com.example.test.TestSqlInspector
~~~

### Giới hạn

- Đây là Hibernate-specific.
- Inspector quan sát SQL Hibernate chuẩn bị, **không phải audit chính xác từng physical execution hoặc số JDBC batches**.
- ThreadLocal capture chỉ phù hợp khi measured operations chạy trong **cùng thread**.
- Những SQL từ async worker khác có thể không xuất hiện.
- Capturing global logs không tự cho biết SQL thuộc request nào.

## 49. Test với SQL inspector

~~~java
@Test
void fetchJoinCustomerAvoidsSecondarySelects() {
    EntityManager em = emf.createEntityManager();
    try {
        List<String> statements;

        TestSqlInspector.beginCapture();
        try {
            List<PurchaseOrder> orders = em.createQuery(
                    "SELECT o FROM PurchaseOrder o " +
                    "JOIN FETCH o.customer ORDER BY o.id",
                    PurchaseOrder.class)
                .getResultList();

            for (PurchaseOrder o : orders) {
                assertNotNull(
                    o.getCustomer().getName()
                );
            }

            assertEquals(4, orders.size());
        } finally {
            statements = TestSqlInspector.endCapture();
        }

        assertEquals(1, statements.size());
    } finally {
        em.close();
    }
}
~~~

Test giả định inspector được cài khi SessionFactory khởi tạo, fixtures đã commit, không có SQL phụ trong measurement, provider/query plan phù hợp và test chạy cùng thread.

### Vì sao finally?

Khi query hoặc assertion ném exception, ThreadLocal phải được dọn để không ảnh hưởng test tiếp theo trên thread tái sử dụng.

### Đừng assert SQL raw string quá cứng

Aliases, parameter placeholders, column order, formatting và schema-qualified identifiers có thể thay đổi giữa dialects/provider versions. Nếu mục tiêu là SQL count, chỉ đếm; nếu cần phân loại SELECT from customers, dùng parsing/patterns có độ bền thích hợp thay vì exact full string.

## 50. JDBC DataSource proxy: quan sát execution boundary

Một DataSource proxy/tracing library nằm giữa ORM và JDBC driver:

~~~text
Application
    |
    v
JPA Provider
    |
    v
Instrumented DataSource
    |
    v
JDBC Driver -> Database
~~~

Những công cụ như datasource-proxy hoặc P6Spy có thể quan sát SQL statements và timing tùy integration.

### Khi nào hữu ích hơn StatementInspector?

- Cần quan sát actual JDBC execute calls.
- Cần phân biệt batch operations.
- Cần test nhiều providers hơn Hibernate.
- Cần gắn SQL metrics vào trace/test scope.

### Nhưng phải định nghĩa cách đếm

Công cụ có thể đếm SQL chuẩn bị, execute calls, batch executions hoặc SQL strings theo cách khác nhau. Một prepared statement có thể được execute nhiều lần; một JDBC batch có thể chứa nhiều DML operations. Đừng trộn các counters rồi đều gọi “số câu SQL”.

## 51. SQL text không phản ánh mọi database work

Trong một SQL statement:

~~~sql
SELECT o.id, l.id
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
ORDER BY o.id;
~~~

database có thể scan, sort, filter và trả rất nhiều rows. Ngược lại, một batched query có thể thực hiện ít round trips hơn nhiều single executions.

### Test SQL count đo cái gì?

Nó là một **guardrail chống số lượng statements tăng bất thường**, không phải phép đo tổng DB CPU, IO, memory hoặc latency.

Kết hợp database slow-query tracing, EXPLAIN, row counts và JVM memory profiling cho workloads lớn.

## 52. Phân loại SELECT và DML

Trong một transaction, có thể thấy:

~~~sql
INSERT INTO customers (...) VALUES (...);
SELECT ... FROM purchase_orders;
SELECT ... FROM customers WHERE id = ?;
UPDATE ...;
~~~

Nếu test N+1, tập trung vào SELECT liên quan fetch plan. Nhưng có một số caveats:

- Sequence allocation có thể dùng SELECT.
- CTE có thể bắt đầu bằng `WITH`.
- Native SQL hoặc stored procedures không chỉ là simple `SELECT` text.
- Một SQL statement có thể phát DB triggers mà JDBC instrumentation không quan sát như separate calls.
- Flush AUTO có thể tạo DML trước read query.

### Nên báo metrics theo tên rõ

~~~text
preparedStatementsTotal
jdbcSelectExecutions
entityLoads
entityFetches
collectionFetches
jdbcBatchExecutions
~~~

Không đổi tên `getQueryExecutionCount()` thành “JDBC SELECT count” vì tên nghe thuận tiện.

## 53. Exact count hay upper bound?

**Exact assertion**:

~~~java
assertEquals(1L, preparedStatements);
~~~

Phù hợp khi một query path đơn giản, fixtures cố định, cache disabled, provider/dialect pinned và không có SQL xen vào.

**Upper-bound assertion**:

~~~java
assertTrue(
    preparedStatements <= 3L,
    "Fetch plan exceeds expected SQL budget"
);
~~~

Phù hợp khi một fixed small number of secondary selects/COUNT được cho phép.

### Budget không nên quá rộng

Nếu page size tối đa 20 nhưng đặt threshold 100, test sẽ không phát hiện N+1 21 SELECTs. Budget phải **thấp hơn rõ rệt** so với naive N+1 trên fixture dự kiến.

### Provider-independent tests

Nếu cần chạy nhiều providers/DBMS, ưu tiên assertions về **growth pattern** và kết quả, kết hợp provider-specific metrics chỉ trong profile tương ứng.

## 54. Test correctness và SQL count cùng lúc

Nếu method trả danh sách rỗng, SQL count = 0 vẫn rất “đẹp” nhưng logic sai.

Test cần assert:

~~~java
assertEquals(expectedOrderIds, actualOrderIds);
assertEquals(expectedNames, customerNames);
assertEquals(expectedLineCount, lineCount);
assertTrue(sqlCount <= budget);
~~~

Nếu pagination:

- Đúng root count.
- Stable ordering.
- Không mất roots do INNER JOIN không phù hợp.
- Không duplicate Orders ngoài contract.
- Collections đầy đủ, không partial.
- TotalElements đúng nếu API yêu cầu.
- Tenant/ACL scope được giữ.

**N+1 regression test có giá trị khi vừa bảo đảm data correctness vừa bảo đảm resource budget.**

## 55. SQL budget theo use case

Một repository method có thể được dùng cho:

~~~text
Order list:
  code, totalAmount, customerName

Order details:
  customer, lines, shipping, payment

Order export:
  millions of rows, scalar fields
~~~

Các use cases có fetch plans khác nhau.

| Use case | Data needed | Plan | SQL budget minh họa |
| --- | --- | --- | --- |
| Order list page 20 | Order + Customer name | DTO/JOIN FETCH to-one | 1–2 |
| Order detail | Aggregate bounded | Fetch graph | 1–3 |
| Order list + Lines | Page roots + to-many | 2-step IDs then fetch | 2–3 |
| Order export | Many scalar rows | DTO chunks | Theo chunks |
| Update single Order | Managed aggregate | Dirty checking | Theo mapping |

Đây là những **số minh họa**, phải điều chỉnh theo architecture, schema, requirements và provider behavior.

### Không ép mọi endpoint còn 1 SQL

Đôi khi 2–3 bounded queries tốt hơn 1 JOIN cartesian explosion. Đo cả result set bytes, heap và latency.

## 56. Spring Data JPA @EntityGraph

Spring Data JPA có annotation:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    @Query(
        "SELECT o FROM PurchaseOrder o " +
        "ORDER BY o.id")
    List<PurchaseOrder> findAllForSummary();
}
~~~

Annotation điều chỉnh fetch graph trong framework, nhưng **không phải cam kết SQL = 1 cho mọi provider/version**.

### Regression test

Gọi repository từ service thật, dereference Customer name và đo statements. Không chỉ kiểm tra annotation tồn tại trên method.

### Nhiều associations

Nếu thêm `lines` vào attributePaths, có thể tăng rows/object graph đáng kể và gây pagination problems. Một test SQL budget nhỏ chưa đủ để xác nhận performance khi dữ liệu lớn.

## 57. Spring Data derived queries và projection

Một repository có thể trả interface projection:

~~~java
public interface OrderSummaryView {
    Long getId();
    String getCode();
}
~~~

Nhưng với nested association projections, provider/framework có thể thực hiện joins hoặc materialize data khác tùy implementation.

### Điều nên test

- SQL selected columns.
- Số statements.
- DTO/projection fields thực trả.
- Không lazy access ngoài transaction.
- Peak heap nếu result lớn.

**Không suy từ return type có chữ Projection rằng N+1 chắc chắn biến mất.** Đo SQL của production mapping path.

## 58. Test HTTP endpoint khác test repository

Một repository test có thể pass:

~~~text
repository.findAllForSummary() -> 1 SELECT
~~~

nhưng controller:

~~~java
return orders.stream()
    .map(o -> new OrderResponse(
        o.getCode(),
        o.getCustomer().getName(),
        o.getLines().size()
    ))
    .toList();
~~~

có thể tải thêm Lines và gây N+1.

### Tầng cần đo

- Repository integration test: SQL plan riêng của method.
- Service integration test: query + mapping DTO + authorization.
- HTTP integration test: end-to-end including serialization nếu entity graph bị expose.

Mỗi tầng có mục tiêu; test repository không chứng minh toàn endpoint đã tránh N+1.

## 59. OSIV và serialization queries

Nếu Open EntityManager in View giữ context mở đến khi render JSON, một serializer có thể truy cập associations ngoài service transaction:

~~~text
Service query:   1 SQL
JSON serializers: N SQL
Total endpoint: N+1
~~~

Tắt OSIV có thể làm vấn đề bộc lộ dưới dạng lazy initialization exception, nhưng không tự thiết kế fetch plan đúng.

**Hướng bền vững:** mapping response DTO trong transactional application service hoặc explicit query projection và test toàn mapping path.

## 60. Query budget dưới multiple transaction scopes

Một use case có thể gọi:

~~~text
Service @Transactional
  -> Repository A: load Orders
  -> Repository B: load Customers
  -> Repository C: load Payments
  -> Map DTO
~~~

Nếu budget đo riêng từng repository, tổng statements có thể lớn. Đo cả service cho **business operation**; sau đó dùng subspans để tìm component tạo nhiều SQL.

### Tránh global stats bị nhiễu

Trong test parallel/concurrent, không dùng một SessionFactory-wide before/after counter mà không cô lập. Dùng JDBC correlation/test-scoped capture nếu cần scope per request.

## 61. EntityManager.clear() trong test khác với production

`em.clear()` sau fixture giúp tạo cold L1 state, nhưng trong production `clear()` có thể detach managed entities đang được service khác tiếp tục sử dụng.

### Không đưa optimization này vào repository một cách vô điều kiện

Test setup:

~~~java
em.flush();
em.clear();
~~~

là để **kiểm soát môi trường đo**.

Production code:

~~~java
em.clear();
~~~

là một quyết định lifecycle có thể gây mất unflushed changes và làm callers nhận detached objects.

Phân biệt rõ lý do ở hai ngữ cảnh.

## 62. Flush AUTO có thể làm test lệch số statements

Một query trong FlushMode.AUTO có thể kích hoạt SQL DML trước SELECT. Vì vậy nếu test vừa persist fixtures vừa query, counter có thể tăng vì:

- INSERT.
- UPDATE.
- Sequence allocation SELECT.
- Constraint checking SQL.
- Actual SELECT của fetch plan.

### Cách loại nhiễu

Flush/commit fixture transaction rồi mở EntityManager mới. Chỉ bắt đầu SQL capture sau khi setup xong. Nếu vẫn có writes trong measured use case, ghi budget cho DML tách khỏi SELECT fetch plan.

## 63. Không nhầm N+1 với polling hoặc repeated query

Một service có thể gọi cùng JPQL query 20 lần trong loop:

~~~java
for (Long id : ids) {
    em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.id = :id",
        PurchaseOrder.class)
      .setParameter("id", id)
      .getSingleResult();
}
~~~

Đây cũng là **nhiều truy vấn phụ thuộc N**, nhưng không nhất thiết xuất phát từ lazy association loading. Vẫn cần xem lại access pattern: có thể dùng một `IN` query có giới hạn, batching hoặc domain-specific query.

### Test không nên chỉ tìm chữ LAZY

Một query count regression test có thể bắt cả repeated explicit repository calls trong loop và classic ORM lazy N+1.

## 64. Không nhầm batch statements với số row writes

Một batch insert 100 OrderLines có thể:

- Tạo 100 rows.
- Dùng một số JDBC batch executions.
- Chỉ có một SQL template/PreparedStatement.

Nói “1 SQL” ở đây có thể che việc application đã ghi 100 rows.

### Khi đo N+1

Tập trung read association SELECT pattern; khi đo write performance, bổ sung entity insert/update counts, JDBC batch efficiency và DB execution timing.

## 65. Một câu SQL cũng có thể gây Cartesian explosion

Ví dụ:

~~~text
100 Orders
  × 20 Lines/order
  × 10 Events/order
= 20.000 SQL rows
~~~

Một query có 1 JDBC statement nhưng transfer/allocate nhiều dữ liệu.

Test nên tách:

- SQL budget guardrail ở integration suite.
- Large-fixture benchmark đo rows/bytes, heap, GC, latency và DB plan.

Không tối ưu tới “1 SELECT bằng mọi giá”.

## 66. Quan sát N+1 trong production

Một số tín hiệu:

- JDBC statement count per request tăng cùng số root results.
- Nhiều SELECT cùng SQL fingerprint khác bind ID.
- Endpoint p95 latency tăng mạnh khi page size tăng.
- Database QPS tăng nhưng CPU application ít thay đổi.
- Serialization duration lớn sau repository query.
- Repeated association fetch counters.

### Cách ghi metrics

~~~text
operation = order.list
pageSize = 50
jdbcPrepared = 51
entityLoads = 100
collectionFetches = 0
durationMs = ...
~~~

Không log toàn bộ customer names, bind parameters hoặc SQL chứa dữ liệu nhạy cảm. Dùng SQL fingerprints/traces có privacy controls, gắn với request ID.

## 67. SQL budgets nên gắn với behavior contract

Một regression test được dùng trong CI nên nêu rõ:

~~~text
Operation: listOrderSummaries
Fixture: 30 Orders, 30 distinct Customers
Access: code, total, customerName
Cache: cold L1, L2 disabled
Transaction: read-only, same thread
Budget: <= 2 SELECT-related statements
Correctness: 30 summaries with exact values
~~~

Với contract này, nếu developer vô tình xóa JOIN FETCH hoặc chuyển DTO projection sang entity mapping gây lazy SELECT mỗi Order, test sẽ fail.

### Tại sao phải ghi fixture distribution?

Nếu 30 Orders đều thuộc cùng Customer, N+1 to-one có thể chỉ phát một extra SELECT do identity map. Test không có **distinct customers** sẽ khó phát hiện regression.

### Khi business thay đổi

Nếu response cần thêm OrderLines, SQL budget có thể tăng có chủ đích. Không đơn giản thay `assertEquals(1,...)` thành `assertTrue(count <= 100)`; hãy thiết kế fetch plan và đo lại.

## 68. Fixtures cần các trường hợp đối nghịch

Một test suite tốt có ít nhất:

| Fixture | Mục đích |
| --- | --- |
| 1 Order, 1 Customer | Kiểm tra hành vi cơ bản |
| 20 Orders, 20 Customers | Làm lộ N+1 to-one |
| 20 Orders, 1 Customer | Kiểm tra identity map reuse |
| 20 Orders, 20 nonempty Lines collections | Làm lộ N+1 to-many |
| Orders có 0 Lines | Xác nhận LEFT JOIN semantics |
| Order có 100+ Lines | Quan sát row multiplication/memory |
| 2 to-many collections | Nhận diện cartesian explosion |
| Mixed null/optional relationships | Không mất roots với INNER JOIN |
| Multiple tenants | Kiểm tra scope query đúng |
| Two pages of data | Kiểm tra pagination/order |

**Không cần cho mọi test chạy toàn bộ fixtures**. Tách focused SQL-count tests nhanh khỏi heavy performance tests; nhưng mỗi thay đổi fetch plan cần ít nhất các edge cases liên quan.

## 69. Test SQL budget bằng helper có phạm vi rõ

Một helper cho Hibernate Statistics trong test tuần tự:

~~~java
static long countPreparedStatements(
        Statistics stats,
        Runnable action) {

    long before =
        stats.getPrepareStatementCount();

    action.run();

    return stats.getPrepareStatementCount() -
        before;
}
~~~

Ví dụ:

~~~java
long statements = countPreparedStatements(
    statistics,
    () -> {
        List<PurchaseOrder> orders =
            repository.findAllForSummary();

        for (PurchaseOrder order : orders) {
            assertNotNull(
                order.getCustomer().getName()
            );
        }
    }
);

assertTrue(statements <= 2);
~~~

### Giới hạn không thể bỏ qua

Helper này đọc **SessionFactory-wide counters**; nếu test parallel hoặc background tasks cùng SessionFactory hoạt động, delta bị nhiễu. Nó chỉ hợp lệ trong test cô lập. Để đếm chính xác per-test trong suite concurrent, dùng instrumented DataSource/test-scoped query recorder có correlation đáng tin.

### Với transaction rollback hoặc exception

Test vẫn cần cleanup EntityManager/transaction trong finally. Không để helper đo query mà che lỗi, sửa transaction state, hoặc nuốt exception.

## 70. So sánh N nhỏ và N lớn trong test cô lập

Thay vì chỉ assert:

~~~java
assertEquals(1, queryCount);
~~~

có thể tạo hai database fixture groups, mỗi group chạy trong context mới:

~~~text
Group A: 10 Orders
Group B: 100 Orders

Measured query:
  SELECT Orders within group
  Convert each to DTO using Customer name

Expected optimized plan:
  Statement count gần hằng số
~~~

### Khi nào không yêu cầu hằng số tuyệt đối?

Nếu dùng Hibernate batch fetching, số statements có thể tăng theo số batch groups. Khi đó test kiểm tra tỷ lệ tăng nhỏ và upper bound, không nhất thiết =1.

### Kiểm tra latency nữa?

CI assertion về latency vài milliseconds thường flaky. Với latency, dùng performance benchmark/threshold có môi trường kiểm soát và phân tích distributions, không dùng đồng hồ một lần thay SQL-count assertions ổn định.

## 71. Query có to-one LAZY nhưng getId không đủ để bắt N+1

Test sai mục tiêu:

~~~java
for (PurchaseOrder order : orders) {
    consume(order.getCustomer().getId());
}
~~~

Với proxy biết identifier, code có thể không cần SELECT Customers.

Test đúng theo màn hình:

~~~java
for (PurchaseOrder order : orders) {
    consume(order.getCustomer().getName());
}
~~~

Hãy truy cập chính xác fields mà production code dùng.

### Với to-many

Nếu production render line details, test cần duyệt `OrderLine` elements chứ không chỉ đọc collection reference. Nếu test không trigger association initialization, budget có thể pass giả tạo.

## 72. Pagination correctness và SQL count

Một page query với JOIN to-many cần test:

~~~text
Given:
  Order A có 20 Lines
  Order B có 1 Line
  Order C có 0 Line

When:
  Page size = 2

Then:
  Root IDs đúng page
  Không thiếu Order B/C ở những pages tương ứng
  Không có partial Lines
  SQL count đúng budget
  Không có in-memory pagination không mong muốn
~~~

### Vì sao Order A nhiều Lines?

Nó làm lộ sự khác nhau giữa “2 SQL rows” và “2 root Orders”. Khi JOIN FETCH collections, LIMIT trên rows có thể làm sai root paging nếu provider không có chiến lược hợp lệ.

### Viết assertions cho root IDs

Đừng chỉ kiểm tra `orders.size() == 2`. Kiểm tra exact Order IDs/order và child counts.

## 73. Trường hợp zero/optional association

Một to-one `optional=true` hoặc to-many collection rỗng cần được test riêng:

~~~text
Order X -> Customer null
Order Y -> Customer present

Order Z -> 0 Lines
~~~

Nếu đổi từ LEFT JOIN FETCH sang INNER JOIN FETCH để giảm SQL mà làm biến mất Order X, SQL count đẹp nhưng business output sai.

Trong fixture hiện tại `PurchaseOrder.customer` là non-nullable, nên test optional association cần một mapping/use case khác cho phép null. Không cố vi phạm constraint để làm fixture.

## 74. Test service transaction boundary

Service:

~~~java
@Transactional(readOnly = true)
public List<OrderRow> listSummaries() {
    List<PurchaseOrder> orders =
        repository.findAllForSummary();

    return orders.stream()
        .map(o -> new OrderRow(
            o.getId(),
            o.getCode(),
            o.getCustomer().getName(),
            o.getTotalAmount()
        ))
        .toList();
}
~~~

Mapping diễn ra **trước khi transaction/context kết thúc**. SQL counter của integration test nên bao toàn bộ call `listSummaries()`.

### Không để method tự trả managed entities rồi mapping nơi khác

Nếu controller mapping sau transaction, có thể gặp LazyInitializationException hoặc OSIV-triggered N+1. Test service trả DTO giúp kiểm soát fetch plan và output scope.

### Spring proxy caveat

Nếu dùng proxy-based transaction management, direct self-invocation trong cùng bean có thể không kích hoạt `@Transactional` như mong đợi. Integration test phải gọi managed service qua Spring context.

## 75. Dùng DB EXPLAIN bổ sung cho SQL-count regression

Nếu một JOIN FETCH giảm từ 51 xuống 1 SQL nhưng query chậm hơn:

1. Capture SQL thực tế.
2. Dùng EXPLAIN/EXPLAIN ANALYZE trên database test phù hợp.
3. Xem row estimates, actual rows, join strategy, index usage, sort/temp files.
4. Đo JDBC transfer time và Java allocations.
5. Xem có cartesian multiplication do collections hay không.

### Không chạy heavy EXPLAIN ANALYZE bừa bãi trong production

Với một số DBMS, EXPLAIN ANALYZE thực sự thực thi query và có thể tạo tải. Dùng staging/controlled tooling với dữ liệu representative.

## 76. Quy trình chẩn đoán N+1

~~~text
Endpoint chậm khi page size tăng
                |
                v
    Query count tăng cùng N?
          /            \
        Có             Không
        |                |
        v                v
  SQL fingerprint      Query plan, result rows,
  secondary selects?   sort/locks/serialization
       /    \
     Có      Không
      |        |
      v        v
 Lazy/other    Repeated explicit
 relationship  repository queries?
  accesses        |
      |           v
      v        Refactor batching/IN
Fetch DTO / JOIN FETCH
EntityGraph / Batch fetch
      |
      v
Test correctness + SQL budget
      |
      v
Benchmark heap/rows/latency
~~~

Nếu SQL count không tăng mà latency vẫn tăng mạnh, N+1 có thể không phải bottleneck chính. Hãy xem total rows, query plan, serialization, contention và cache effects.

## 77. Bảng sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục/test |
| --- | --- | --- |
| N Orders tạo N Customer SELECT | Lazy to-one access | JOIN FETCH/DTO/EntityGraph, SQL budget |
| Mỗi Order thêm SELECT Lines | Lazy to-many | Fetch/batch/2-step |
| Test thấy 1 SELECT dù production N+1 | L1 cache còn fixtures | Flush/clear/new EM |
| Test pass lần sau, fail lần đầu | L2/query cache warm state | Cố định cache profile |
| `getQueryExecutionCount()=1` nhưng DB nhiều SELECT | Counter không tính secondary SQL như JDBC count | Prepare/JDBC instrumentation |
| Stats count flaky khi CI parallel | SessionFactory global counter | Run isolated/per-request recorder |
| JOIN FETCH còn nhiều queries | Fetch plan chưa đúng hoặc another association | Capture full service SQL |
| @EntityGraph không giảm số SQL như mong đợi | Provider strategy khác JOIN | Budget/SQL inspect |
| Pagination collection fetch chạy chậm | In-memory pagination/cartesian rows | Two-step ID pagination |
| 1 SELECT nhưng OOM | To-many graph quá lớn | DTO/partition/batched query |
| Root Orders bị mất | INNER JOIN khi relation optional | LEFT JOIN, correctness test |
| Root Orders bị duplicate | To-many row multiplication | Distinct/grouping/DTO verify |
| N+1 chỉ ở HTTP response | OSIV/serializer lazy access | DTO at service, HTTP SQL test |
| Exception sau khi đóng EM | Lazy relation chưa initialized | Fetch before context ends |
| SELECT count lệch do sequence/INSERT | Fixtures nằm trong measurement | Separate arrange/act |
| Count query nhân rows | JOIN to-many trong COUNT | COUNT DISTINCT/EXISTS |
| Batch fetch SQL budget không còn =1 | Controlled IN batches | Upper bound theo provider |
| N+1 không hiện ở test N=1 | Fixture quá nhỏ | Test N đủ lớn/distinct IDs |
| Test dùng mocks không phát SQL | Không có ORM runtime | JPA integration test |
| SQL count thấp nhưng p99 xấu | Lock/IO/index/large results | EXPLAIN + performance metrics |
| Query sau thay đổi mapping tự EAGER | Hidden secondary loads | Fetch-plan regression suite |

## 78. Những anti-pattern cần tránh

- **Chỉ test `repository.findAll()`** nhưng không test code dereference associations.
- **Dùng mock repositories** để chứng minh số SQL.
- **Không flush/clear fixtures** nên cache che N+1.
- **Reset global Hibernate Statistics giữa parallel tests** làm số liệu của test khác bị nhiễu.
- **Coi `getQueryExecutionCount()` là số mọi JDBC statements**.
- **Assert SQL aliases/string nguyên văn** gây flaky khi đổi dialect.
- **Tăng SQL budget vô hạn khi test fail** mà không điều tra query plan.
- **Đổi mọi LAZY thành EAGER** với kỳ vọng chắc chắn còn một SQL.
- **JOIN FETCH mọi to-many cùng lúc** gây cartesian explosion.
- **Paginate trực tiếp collection fetch join** mà không kiểm tra provider behavior.
- **Dựa vào L2 cache để che N+1** thay vì sửa fetch plan.
- **Chỉ đếm SQL, không kiểm tra dữ liệu**.
- **Chỉ đo SQL count, bỏ heap/rows/latency**.
- **Chỉ benchmark N=1** nên không thấy linear growth.
- **Không chạy DTO mapping trong transaction measurement**.
- **Không kiểm tra authorization/tenant scope** khi thay JPQL để tối ưu.
- **Xem mọi extra SQL là N+1** dù có count/IDs/fetch queries cố định có chủ đích.
- **Đếm SQL setup/DDL/sequence chung với read path**.
- **Cho SQL inspector ThreadLocal chạy async mà nghĩ capture đủ**.
- **Dùng in-memory DB benchmark thay production-like query plan**.

## 79. Bài tập thực hành

### Bài 1 — Nhận diện N+1

Một query lấy 20 Orders, sau đó vòng for đọc Customer name. SQL log cho thấy 1 SELECT Orders và 20 SELECT Customers. Đây là mẫu gì?

**Gợi ý:** N+1 to-one association access.

### Bài 2 — Vì sao getId không đủ?

Test chỉ gọi `order.getCustomer().getId()` nhưng không có secondary SELECT. Có chứng minh không có N+1 khi UI hiển thị Customer name không?

**Gợi ý:** Không. Proxy có thể biết identifier; phải access field UI thực sự cần.

### Bài 3 — N+1 to-many

Query 30 Orders rồi duyệt `order.getLines()` từng Order. Khi nào có thể thấy khoảng 31 SELECTs?

**Gợi ý:** Lazy collection không batching/cache và mỗi collection được initialize riêng.

### Bài 4 — Identity map

50 Orders đều cùng một Customer. Vì sao lazy to-one có thể ít hơn 51 SELECTs?

**Gợi ý:** Customer đã managed sau lần tải đầu, các Orders khác reuse same identity.

### Bài 5 — Fixture distribution

Muốn test lộ N+1 to-one rõ, nên tạo 20 Orders thuộc 1 Customer hay 20 Customers khác nhau?

**Gợi ý:** Nhiều distinct identities, không chỉ tăng số Orders.

### Bài 6 — Mock

Mockito repository trả 100 Order POJOs nhưng không phát SQL. Đây có phải bằng chứng ORM fetch plan tốt không?

**Gợi ý:** Không, cần integration test với JPA provider thật.

### Bài 7 — Measurement window

Vì sao nên tạo/commit fixtures **trước** khi bắt đầu đếm SQL read path?

**Gợi ý:** Tránh INSERT/sequence/flush/setup SQL làm nhiễu.

### Bài 8 — Context lifecycle

Vì sao test nên mở EntityManager mới hoặc `flush()/clear()` sau setup?

**Gợi ý:** Tránh L1 cache/initialized Java associations che secondary queries.

### Bài 9 — L2 cache

Run 1 có 31 SELECTs, run 2 có 1 SELECT. Nên xem yếu tố gì trước khi tuyên bố đã sửa N+1?

**Gợi ý:** L2/query cache warm states và fixture/EM lifecycle.

### Bài 10 — Counter đúng

`Statistics.getQueryExecutionCount()` trả 1 nhưng SQL log có 21 SELECTs. Có mâu thuẫn không?

**Gợi ý:** Không; counter HQL/JPQL executions không đồng nhất mọi secondary JDBC SQL.

### Bài 11 — PrepareStatementCount

`getPrepareStatementCount()` của Hibernate có phạm vi chỉ một request không?

**Gợi ý:** Thường là SessionFactory-wide statistics, phải cô lập hoặc dùng scoped recorder.

### Bài 12 — Parallel tests

Hai tests cùng SessionFactory đo delta counters, số liệu bị nhiễu. Có những cách khắc phục nào?

**Gợi ý:** Test isolation, resource locks, per-connection/per-request JDBC instrumentation.

### Bài 13 — JOIN vs JOIN FETCH

Một JPQL có `JOIN o.customer c` chỉ để lọc theo c.name. Có chắc Customer association initialized không?

**Gợi ý:** Không; JOIN thường không đồng nghĩa FETCH.

### Bài 14 — Fetch join to-one

Vì sao `JOIN FETCH o.customer` có thể giảm secondary SELECTs khi màn hình cần Customer name?

**Gợi ý:** Customer được tải theo query fetch plan thay vì lazy proxy resolution từng Order.

### Bài 15 — EAGER

Vì sao `FetchType.EAGER` không chứng minh query chỉ phát một SQL JOIN?

**Gợi ý:** Provider có thể dùng secondary selects để thực hiện eager semantics.

### Bài 16 — EntityGraph

EntityGraph khai báo customer được fetch, có bắt buộc tạo đúng một SQL statement trên mọi provider không?

**Gợi ý:** Không; test effect và SQL budget thay vì suy syntax.

### Bài 17 — Optional relationships

Một Order có Customer nullable. Đổi LEFT JOIN FETCH sang INNER JOIN FETCH làm biến mất Order đó. Test SQL count =1 có còn đạt yêu cầu không?

**Gợi ý:** Không, correctness sai.

### Bài 18 — To-many

Một JOIN FETCH `order.lines` làm SQL count từ 31 xuống 1. Cần đo thêm gì?

**Gợi ý:** SQL rows, heap, latency, collection completeness và duplicate root handling.

### Bài 19 — Cartesian explosion

Order có 10 Lines và 20 Events. Fetch join hai collections có thể tạo bao nhiêu physical rows cho Order ấy?

**Gợi ý:** Khoảng 200 rows theo phép nhân 10×20 trong tình huống đơn giản.

### Bài 20 — Pagination

Vì sao `setMaxResults(20)` với collection fetch join có thể gây in-memory pagination?

**Gợi ý:** LIMIT trên physical joined rows không tương đương 20 complete root collections.

### Bài 21 — Two-step pagination

Hãy mô tả hai SQL queries lấy 20 Order roots và Lines của đúng 20 Orders.

**Gợi ý:** Query page IDs, rồi fetch roots/collections theo IN các IDs; giữ đúng thứ tự.

### Bài 22 — COUNT

API Page yêu cầu totalElements. Vì sao 3 queries cố định có thể đúng và không phải N+1?

**Gợi ý:** Page IDs, fetch associations, COUNT — không tăng một SELECT cho mỗi root.

### Bài 23 — COUNT to-many

Một COUNT join Order với Lines bị nhân duplicates. Có cách nào giảm sai tổng?

**Gợi ý:** COUNT DISTINCT root ID hoặc EXISTS/semantics count phù hợp.

### Bài 24 — Batch fetching

Batch size 16 có bảo đảm chính xác `1 + ceil(N/16)` statements ở mọi Hibernate version không?

**Gợi ý:** Không; provider, cache và groups ảnh hưởng.

### Bài 25 — DTO projection

Màn hình chỉ cần Order code, Customer name và total. Vì sao constructor DTO projection có thể đơn giản hơn entity graph?

**Gợi ý:** Chỉ select fields cần, tránh managed association loading/dirty tracking không cần thiết.

### Bài 26 — Lazy exception

Sau khi EntityManager đóng, truy cập lazy Customer name gây LazyInitializationException. Việc bật OSIV có chắc chữa hiệu năng không?

**Gợi ý:** Không; có thể chuyển lỗi thành N+1 ở serialization phase.

### Bài 27 — StatementInspector

ThreadLocal SQL recorder có bắt được mọi SQL của một async worker thread không?

**Gợi ý:** Không; phải dùng scoped instrumentation/correlation phù hợp multi-thread.

### Bài 28 — SQL batch

Một JDBC batch INSERT 100 rows có tương đương chỉ một row write không?

**Gợi ý:** Không; số batch executions khác số operations/rows.

### Bài 29 — Query size

Hai fetch plans: Plan A có 4 SQL và 200 rows; Plan B có 1 SQL và 100.000 rows. Plan nào chắc chắn nhanh hơn?

**Gợi ý:** Không thể kết luận chỉ từ SQL count; cần latency, heap, DB IO và data transfer.

### Bài 30 — Bộ test tổng hợp

Thiết kế regression suite cho `OrderListService.listSummaries(pageSize=50)`:

1. Fixtures 50 Orders thuộc 50 Customers khác nhau.
2. Query fetch plan muốn sử dụng.
3. Thời điểm reset SQL counters.
4. Cách trigger association accesses.
5. Expected business assertions.
6. SQL budget.
7. Test với L2 cache bật/tắt.
8. Test nếu thêm to-many `lines`.

**Gợi ý:** Cô lập measured context, dùng DTO/JOIN FETCH, count toàn service và lưu test cache profile rõ ràng.

### Bài 31 — N+1 ngoài ORM lazy

Một service gọi repository.findById() trong loop 50 IDs. Đây có thể là performance pattern gì?

**Gợi ý:** N repeated explicit queries; batch/IN query khi phù hợp.

### Bài 32 — HTTP integration

Repository query chỉ chạy 1 SELECT nhưng API response phát thêm 100 SELECTs. Cần đo tầng nào?

**Gợi ý:** Toàn endpoint/serialization hoặc service DTO mapping.

### Bài 33 — SQL alias

Vì sao assert nguyên văn tên alias `o1_0` trong generated SQL thường không bền?

**Gợi ý:** Provider/dialect/version có thể đổi cách đặt alias.

### Bài 34 — Timing

Vì sao test `assertTrue(durationMs < 10)` trong CI dễ flaky hơn SQL-count assertion?

**Gợi ý:** JVM warm-up, OS scheduling, DB load, GC và latency noise.

### Bài 35 — Tính đúng và an toàn

Tối ưu JPQL thành JOIN FETCH nhưng quên tenant predicate. Test SQL count pass, ứng dụng có đạt yêu cầu không?

**Gợi ý:** Không; authorization/cross-tenant correctness phải kiểm tra riêng.

### Bài 36 — @DataJpaTest

Vì sao test transaction rộng do `@DataJpaTest` có thể che LazyInitializationException xảy ra trong production controller?

**Gợi ý:** Context còn mở trong test, khác boundary lúc response được tạo ở production.

### Bài 37 — Large dataset

Khi nào cần thêm Testcontainers hoặc database cùng engine production thay vì chỉ H2?

**Gợi ý:** Query plan, locking, pagination SQL, driver behavior, large-fixture performance.

### Bài 38 — SQL count threshold

Một page size 20 có budget 100 SQL. Test có bắt N+1 21 SELECTs không?

**Gợi ý:** Không; budget quá rộng, phải dựa vào fetch plan dự kiến.

### Bài 39 — Query cache

Vì sao warm query cache không được coi là bằng chứng query shape không có N+1?

**Gợi ý:** Cold reads/cache misses vẫn cần association fetch.

### Bài 40 — Tối ưu có trách nhiệm

Nếu 2-step pagination tốn 2 SELECTs còn collection JOIN FETCH tốn 1 SELECT nhưng memory cao gấp nhiều lần, nên chọn bằng tiêu chí nào?

**Gợi ý:** Correctness, SQL/rows, heap, latency, lock/concurrency và production workload.

## 80. Bảng ghi nhớ nhanh

| Chủ đề | Cần nhớ |
| --- | --- |
| N+1 | Một root query cộng nhiều secondary queries tăng theo N |
| To-one LAZY | Dereference non-ID field có thể trigger SELECT |
| To-many LAZY | Initialize mỗi collection có thể trigger SELECT |
| Entity identity | L1 reuse có thể giảm SQL thực tế |
| L2/query cache | Có thể che cold N+1 |
| Fixture tốt | Nhiều distinct association identities |
| Unit mocks | Không chứng minh SQL/fetch plan |
| Integration test | Provider/DB/transactions thật |
| Measurement window | Bao cả DTO mapping/association dereference |
| SQL setup | Không trộn fixture insert/DDL với read path |
| `getPrepareStatementCount()` | Prepared JDBC statement counter của Hibernate |
| `getQueryExecutionCount()` | Không bằng mọi JDBC SELECT |
| Hibernate Statistics | Có thể là SessionFactory-wide |
| StatementInspector | Hibernate SQL capture trước JDBC prepare |
| DataSource proxy | JDBC-level instrumentation |
| Exact SQL count | Phù hợp fixture/provider cố định |
| Upper SQL budget | Phù hợp fixed bounded secondary queries |
| JOIN FETCH to-one | Có thể tránh secondary association SELECT |
| JOIN thường | Không tự đồng nghĩa initialized association |
| EAGER | Không bảo đảm chỉ 1 JOIN SQL |
| EntityGraph | Khai báo fetch plan; SQL shape provider-dependent |
| JOIN FETCH to-many | Có thể nhân SQL rows |
| Multiple to-many fetch | Cartesian explosion/multiple bag limitations |
| Collection fetch + pagination | Có thể in-memory/unsafe, cần kiểm tra |
| Two-step pagination | Page IDs, sau đó fetch associations |
| COUNT query | Một SQL cố định có chủ đích |
| Batch fetching | Giảm N secondary queries theo nhóm |
| Subselect fetching | Provider-specific collection fetch optimization |
| DTO projection | Chọn fields cần dùng, tránh lazy graph |
| OSIV | Có thể che N+1 ở serialization |
| LazyInitializationException | Khác N+1 nhưng cùng fetch-boundary design |
| SQL statement count | Không bằng số rows hoặc latency |
| Regression test | Phải assert cả correctness và SQL budget |
| Performance benchmark | Thêm rows, bytes, heap, GC, p95 |
| Kết quả tốt | Dữ liệu đúng, SQL bounded, tài nguyên hợp lý |

## Kết luận

**N+1 là vấn đề của kế hoạch tải và đường truy cập dữ liệu, không phải chỉ của một dòng JPQL.** Một repository query trả 50 Orders có thể chỉ dùng một SQL, nhưng việc truy cập Customer names hoặc OrderLines trong service/serializer sẽ phát thêm những SELECT riêng. Vì thế một test bắt N+1 phải chạy **cả truy vấn lẫn phần dereference/mapping thực sự của use case**, trên JPA provider và database thật, với fixtures cố tình dùng nhiều association identities khác nhau.

Để đo đúng, cần hiểu sự khác nhau giữa **Hibernate query execution count, prepared statement count, entity/collection fetch counters, SQL inspector và JDBC execution instrumentation**. L1/L2 cache, setup INSERT/flush, test transaction và parallel SessionFactory-wide statistics có thể làm số liệu sai lệch. Hãy xác định measurement window rõ, cô lập cache/transactions và đặt SQL budget theo **use-case contract**.

Khi phát hiện N+1, có thể dùng **JOIN FETCH to-one, EntityGraph, DTO projection, batch/subselect fetching hoặc two-step pagination** tùy nhu cầu. Không ép mọi use case còn đúng một SQL: collection fetch join có thể nhân hàng nghìn rows, gây in-memory pagination và tốn heap; 2–3 queries cố định nhiều khi tốt hơn một truy vấn khổng lồ. Mọi tối ưu phải tiếp tục được kiểm tra về **đủ root entities, đầy đủ collections, stable paging, permissions và transaction behavior**.

Một regression suite bền vững nên có **SQL-count assertions ổn định**, tăng N để phát hiện query growth, kiểm thử cold cache và trường hợp null/collections lớn, cộng performance benchmarks trên database giống production để đo **rows transferred, latency, heap, GC và query plans**. Nguyên tắc cuối cùng: **không chỉ làm ít SQL hơn, mà phải tải đúng dữ liệu, với số câu SQL có kiểm soát và tổng chi phí phù hợp nhu cầu thực**.





