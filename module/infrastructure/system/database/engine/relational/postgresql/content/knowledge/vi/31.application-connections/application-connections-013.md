# ORM, ranh giới giao dịch và kiểm tra SQL thực tế trong PostgreSQL

## 1. Vì sao viết Java đúng chưa chắc truy cập PostgreSQL đúng?

Một service Java có thể chỉ chứa vài dòng:

```java
@Transactional
public OrderDto placeOrder(CreateOrderCommand command) {
    Customer customer = customerRepository.findById(command.customerId())
        .orElseThrow();
    Order order = new Order(customer);
    orderRepository.save(order);
    return OrderDto.from(order);
}
```

Nhưng để đánh giá tính đúng đắn, cần biết nhiều điều không xuất hiện trong phương thức:

- `findById` có thật sự phát `SELECT` hay lấy từ persistence context/cache?
- `save` phát `INSERT` ngay hay chờ `flush`?
- Java đã có `order.id` có đồng nghĩa row đã commit?
- `OrderDto.from(order)` có truy cập quan hệ LAZY rồi phát thêm truy vấn?
- `@Transactional` có thực sự được áp dụng cho lời gọi này qua Spring proxy?
- Connection đang ở isolation level nào?
- Lệnh UPDATE có bảo vệ chống cập nhật mất dữ liệu (*lost update*)?
- Nếu có exception sau khi INSERT, row có rollback không?
- Nếu hệ thống đồng thời gửi email, việc gửi có rollback được cùng database không?
- Trong log PostgreSQL, câu SQL thực tế, giá trị bind và thời gian chờ khóa có giống giả định của người viết không?

**ORM (Object–Relational Mapping) ánh xạ object với dữ liệu quan hệ; nó không xóa bỏ SQL, ranh giới giao dịch hoặc những quy tắc đồng thời của PostgreSQL.**

Bài này xây dựng thói quen suy nghĩ theo ba tầng:

```text
TẦNG 1: Java / ORM
  Entity, repository, persistence context, lazy loading
             |
             v
TẦNG 2: JDBC / transaction manager / connection pool
  PreparedStatement, bind parameters, commit, rollback
             |
             v
TẦNG 3: PostgreSQL
  SQL thực tế, locks, MVCC, constraints, WAL, query plans
```

Một ứng dụng đáng tin cậy phải hiểu **cả ba tầng** và kiểm chứng được các ranh giới giao nhau.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ORM, JPA, Hibernate, Spring Data JPA, JDBC và PostgreSQL.
2. Giải thích entity state, persistence context, dirty checking và flush.
3. Phân biệt `save`, `flush`, `commit` và thời điểm row được nhìn thấy từ transaction khác.
4. Xác định transaction boundary theo service method và transaction manager, không theo từng repository call.
5. Nhận ra các trường hợp `@Transactional` không có tác dụng vì proxy/self-invocation.
6. Hiểu `REQUIRED`, `REQUIRES_NEW`, `NESTED` và những giới hạn thực tế.
7. Áp dụng PostgreSQL isolation levels, row locks và optimistic locking khi có concurrent writers.
8. Thiết kế retry có giới hạn cho serialization failures và deadlocks.
9. Phân biệt transaction database với giao dịch nhiều hệ thống; áp dụng outbox khi phù hợp.
10. Đo SQL thực tế bằng Hibernate/JDBC logs, PostgreSQL logs, `pg_stat_activity`, `pg_stat_statements`, `EXPLAIN`.
11. Chẩn đoán N+1, cartesian product từ fetch joins, pagination, batching và slow queries.
12. Lựa chọn ORM, SQL trực tiếp, JDBC, native query hoặc jOOQ theo độ phức tạp và đặc tính nghiệp vụ.
13. Kiểm soát connection pool, timeouts, idle-in-transaction và sự cố giữ khóa.
14. Kiểm tra migration, constraints, default values, timezone, `jsonb` và ánh xạ kiểu dữ liệu.
15. Thực hành theo một hệ thống đơn hàng có concurrency và ranh giới an toàn.

---

## 2. ORM là gì và không phải là gì?

ORM tạo một cơ chế ánh xạ giữa:

| Trong Java | Trong PostgreSQL |
|---|---|
| Class `Customer` | Table `customers` |
| Field `id` | Column `customer_id` |
| `@ManyToOne` | Foreign key/reference |
| Object identity | Khóa chính và ngữ nghĩa persistence context |
| `BigDecimal` | `numeric` |
| `Instant` / `OffsetDateTime` | Thường `timestamptz` theo mapping |
| `LocalDate` | `date` |
| Entity lifecycle | SQL SELECT/INSERT/UPDATE/DELETE được phát khi cần |
| Query method | Truy vấn SQL hoặc phương án truy xuất do framework sinh |

ORM **không**:

- Làm cho mọi truy vấn nhanh.
- Loại bỏ SQL injection nếu lập trình viên tự nối chuỗi native SQL.
- Tự biến nhiều database thành một transaction ACID.
- Bảo đảm mọi relation được load trong đúng một query.
- Thay thế constraint/unique key/foreign key ở PostgreSQL.
- Ngăn race conditions nếu không có locking/version protocol.
- Tự kiểm chứng query plan, index và độ chọn lọc trên data production.
- Bảo đảm cache luôn phản ánh thay đổi từ process khác.

### 2.1. JPA và Hibernate

- **Jakarta Persistence (JPA)**: đặc tả API và mô hình persistence cho Java.
- **Hibernate ORM**: một implementation phổ biến của JPA, có thêm những tính năng riêng.
- **Spring Data JPA**: tầng repository abstraction dựa trên JPA/Hibernate hoặc provider tương ứng.
- **JDBC**: API driver-level để gửi SQL và xử lý transaction/ResultSet.
- **PostgreSQL JDBC Driver (pgjdbc)**: JDBC driver giao tiếp với PostgreSQL.

Ví dụ `JpaRepository.save` là hành vi ở lớp repository; thực tế phát SQL thế nào còn phụ thuộc entity state, Hibernate mapping, flush mode, ID generator và transaction.

### 2.2. ORM và SQL trực tiếp có thể phối hợp

Không cần chọn “100% ORM” hoặc “100% raw SQL”.

Một hệ thống có thể dùng:

- ORM cho CRUD đơn giản và quản lý quan hệ.
- JPQL/Criteria cho query động phù hợp.
- SQL native cho `INSERT ... ON CONFLICT ... RETURNING`, `SKIP LOCKED` hoặc truy vấn PostgreSQL chuyên biệt.
- `JdbcTemplate`/JDBC cho batch/reporting.
- Migration SQL để quản lý schema/index/constraint.
- Outbox + worker để xử lý integration events.

Tiêu chí lựa chọn là **tính đúng đắn, khả năng bảo trì và hành vi đo được**, không phải tránh viết SQL bằng mọi giá.

## 3. Một lab PostgreSQL cho toàn bộ bài

Chỉ dùng trên database thực hành. Các bảng và ID bên dưới là dữ liệu giả.

```sql
CREATE SCHEMA IF NOT EXISTS orm406;

CREATE TABLE orm406.customers (
    customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orm406.products (
    product_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_code text NOT NULL UNIQUE,
    product_name text NOT NULL,
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_on_hand integer NOT NULL CHECK (stock_on_hand >= 0),
    version bigint NOT NULL DEFAULT 0
);

CREATE TABLE orm406.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES orm406.customers(customer_id),
    external_request_id text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount numeric(14, 2) NOT NULL DEFAULT 0
        CHECK (total_amount >= 0),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orm406.order_items (
    order_item_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL
        REFERENCES orm406.orders(order_id) ON DELETE CASCADE,
    product_id bigint NOT NULL
        REFERENCES orm406.products(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    UNIQUE (order_id, product_id)
);

CREATE TABLE orm406.outbox_events (
    event_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
```

Dữ liệu mẫu:

```sql
INSERT INTO orm406.customers(customer_id, full_name, email)
VALUES
    (1, 'An', 'an@example.invalid'),
    (2, 'Bình', 'binh@example.invalid');

INSERT INTO orm406.products(
    product_id, product_code, product_name,
    unit_price, stock_on_hand
)
VALUES
    (10, 'BOOK-001', 'Sách SQL', 150000, 5),
    (11, 'KEY-002', 'Bàn phím', 650000, 3),
    (12, 'MOU-003', 'Chuột', 200000, 0);
```

Do fixture dùng ID tường minh với cột identity `BY DEFAULT`, sequence chưa chắc đã tự tiến theo giá trị fixture. Để tiếp tục tạo ID tự động an toàn trong lab:

```sql
SELECT setval(
    pg_get_serial_sequence('orm406.customers', 'customer_id'),
    (SELECT max(customer_id) FROM orm406.customers),
    true
);

SELECT setval(
    pg_get_serial_sequence('orm406.products', 'product_id'),
    (SELECT max(product_id) FROM orm406.products),
    true
);
```

**Ghi nhớ:** `setval` là thao tác sequence, không phải rollback được theo ngữ nghĩa giao dịch giống row DML. Đây là fixture, không phải migration mẫu cho production.

### 3.1. Vì sao có constraints ở database?

ORM validation có ích cho UI/API, nhưng dữ liệu có thể đến qua SQL script, ETL, một service khác, pgAdmin hoặc migration. PostgreSQL cần giữ các invariant tối thiểu:

- Giá và tổng tiền không âm.
- Số lượng đặt hàng dương.
- Tồn kho không âm.
- Email/product_code/external_request_id không trùng.
- Order chỉ tham chiếu khách hàng hợp lệ.

Ứng dụng vẫn phải cung cấp thông báo lỗi thân thiện, nhưng không nên chỉ kiểm tra trong Java rồi bỏ constraints.

## 4. Entity mapping tối thiểu với JPA

Một ánh xạ Java (minh họa, bỏ import cho gọn):

```java
@Entity
@Table(name = "products", schema = "orm406")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "product_id")
    private Long id;

    @Column(name = "product_code", nullable = false, unique = true)
    private String code;

    @Column(name = "product_name", nullable = false)
    private String name;

    @Column(name = "unit_price", precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "stock_on_hand", nullable = false)
    private Integer stockOnHand;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Product() { }
    // getters, methods enforcing invariants
}
```

### 4.1. Chú thích Java không tự làm DDL production thay đổi

`@Column(nullable = false)` mô tả mapping và có thể tham gia DDL generation nếu bật tính năng tương ứng. Trong production, schema cần được quản lý qua migration, với constraints/indexes được kiểm chứng trực tiếp.

### 4.2. @Version giải quyết bài toán nào?

`@Version` giúp Hibernate/JPA thực hiện **optimistic locking** khi update entity được quản lý:

```sql
-- SQL minh họa về nguyên tắc, không phải câu cố định
-- cho mọi Hibernate version:
UPDATE orm406.products
SET stock_on_hand = ?, version = ?
WHERE product_id = ?
  AND version = ?;
```

Nếu phiên bản cũ không còn khớp, số hàng được update có thể bằng 0 và provider báo optimistic locking failure.

**Giới hạn:** các câu SQL cập nhật trực tiếp không tuân theo version protocol vẫn có thể phá kỳ vọng. Bulk JPQL UPDATE thường không hoạt động giống dirty checking của một entity managed; cần cập nhật version hoặc dùng protocol riêng nếu muốn bảo vệ đồng thời.

### 4.3. BigDecimal cho tiền

`numeric(12,2)` phù hợp với `BigDecimal` hơn `double` khi cần độ chính xác thập phân. Tuy nhiên còn phải thống nhất:

- Đơn vị tiền và currency.
- Rounding mode.
- Precision/scale.
- Tính thuế/discount.
- Xử lý overflow và đối soát.

Không coi việc chuyển kiểu đúng là thay cho các quy tắc tính tiền.

## 5. Các trạng thái entity và persistence context

Trong JPA, entity có thể nằm ở những trạng thái quan trọng:

| Trạng thái | Ý nghĩa |
|---|---|
| New/transient | Object Java chưa được persistence context quản lý |
| Managed/persistent | Được EntityManager quản lý trong persistence context |
| Detached | Từng managed, nhưng không còn được context hiện tại quản lý |
| Removed | Được đánh dấu xóa trong context |

Mô hình:

```text
new Product(...)
      |
      | persist()
      v
Managed entity <---- find() / query
      |
      | thay field
      v
Dirty managed entity
      |
      | flush()
      v
SQL UPDATE/INSERT/DELETE gửi tới PostgreSQL
      |
      | commit()
      v
Transaction commit hoặc rollback theo kết quả
```

### 5.1. Managed entity không cần save sau mọi thay đổi

Trong transaction:

```java
@Transactional
public void renameProduct(Long id, String newName) {
    Product product = entityManager.find(Product.class, id);
    product.rename(newName);
    // Thường không cần entityManager.persist(product) lần nữa.
}
```

Nếu entity còn managed, Hibernate dirty checking có thể phát hiện thay đổi và phát SQL vào lúc flush.

### 5.2. Detached entity không tự động được theo dõi

Một object được load trong transaction đã kết thúc có thể trở thành detached. Sửa field ở object đó không tự bảo đảm một UPDATE trong DB.

Sử dụng `merge`/repository logic phải hiểu semantics copy state và optimistic locking, không tự “save” một object cũ rồi giả định không có lost update.

### 5.3. Identity trong persistence context

Trong một persistence context, JPA/Hibernate thường cố gắng bảo đảm một managed entity instance tương ứng một database identity theo cơ chế của provider. Nhưng cache là **phạm vi làm việc của context**, không phải chân lý toàn hệ thống về dữ liệu đã được thay đổi bởi transactions khác.

## 6. save không đồng nghĩa INSERT ngay

Xem chuỗi:

```java
@Transactional
public Long createOrder(Order order) {
    orderRepository.save(order);
    return order.getId();
}
```

SQL thực tế phụ thuộc:

- Entity mới hay detached.
- `persist` hay `merge` được chọn.
- ID generator `IDENTITY`, `SEQUENCE`, `TABLE` hay assigned.
- Flush mode.
- Provider và phiên bản.
- Các thao tác khác trong cùng transaction.

### 6.1. IDENTITY có thể yêu cầu INSERT sớm

Nếu ID do database tạo khi INSERT với identity column, Hibernate có thể cần thực thi INSERT sớm để biết ID. Nhưng ngay cả khi đã có ID, transaction có thể **chưa commit**.

### 6.2. SEQUENCE có thể cấp ID trước INSERT

Nếu dùng sequence:

```sql
SELECT nextval('some_sequence');
```

ID có thể được cấp khi row chưa được INSERT. Sequence có semantics riêng, các giá trị đã cấp có thể tạo gap sau rollback.

### 6.3. Đừng dùng ID làm bằng chứng transaction thành công

Một order đã có `id=123` trong Java vẫn có thể:

- Đang ở transaction chưa commit.
- Bị rollback.
- Bị một lỗi constraint khác làm transaction thất bại.
- Chưa được flush trong một số mapping.

Chỉ dựa vào kết quả commit và error handling đúng để xác định dữ liệu đã ghi bền vững.

## 7. flush, commit và rollback: ba khái niệm khác nhau

| Hành động | Diễn giải |
|---|---|
| `persist/save` | Đưa entity vào thao tác persistence theo API |
| `flush` | Đồng bộ thay đổi của persistence context thành SQL trong transaction |
| `commit` | Hoàn tất transaction thành công ở PostgreSQL |
| `rollback` | Hủy các thay đổi giao dịch chưa commit (trừ một số side effects ngoài transaction/sequence) |
| `clear` | Bỏ các managed entity khỏi persistence context; không tự rollback SQL đã gửi |
| `refresh` | Nạp lại state từ DB theo semantics context/provider |

### 7.1. Timeline minh họa

```text
Java method bắt đầu
   |
   +-- load Product (SELECT)
   +-- thay name trong managed entity
   +-- save(Order) / persist
   |
   +-- flush
   |     +-- INSERT/UPDATE gửi đến PostgreSQL
   |     +-- constraints có thể báo lỗi ngay hoặc tại thời điểm khác
   |
   +-- code khác tiếp tục
   |
   +-- commit transaction
          |
          +-- thành công: dữ liệu được commit
          +-- thất bại: transaction không thành công
```

### 7.2. Flush không có nghĩa dữ liệu nhìn thấy từ connection khác

Với MVCC/PostgreSQL isolation thông thường, transaction khác không đọc được uncommitted rows chỉ vì Hibernate đã flush.

### 7.3. Flush có thể xảy ra trước khi bạn gọi flush()

Trong các trường hợp phù hợp, Hibernate có thể auto-flush trước query để giữ nhất quán theo flush mode. Không giả định chỉ cuối `@Transactional` mới có SQL.

### 7.4. Commit có thể trigger flush

Khi transaction manager commit, provider thường flush những thay đổi pending cần thiết. Nhưng đừng dùng kiến thức này để bỏ qua những lỗi có thể xuất hiện ở commit boundary mà service method đã trả về body.

### 7.5. Rollback không thu hồi email đã gửi

Nếu sau khi flush INSERT, service gọi external email API, rồi database rollback, email đã gửi không được PostgreSQL rollback theo.

Đây là ranh giới transaction **giữa hai hệ thống**, cần outbox/workflow tương ứng.

## 8. @Transactional ở đâu là boundary?

Trong Spring, mẫu phổ biến là đặt transaction tại **application/service layer**, bao phủ một use case cần atomicity:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final ProductRepository products;

    public OrderService(OrderRepository orders,
                        ProductRepository products) {
        this.orders = orders;
        this.products = products;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Product product = products.findById(command.productId())
            .orElseThrow();
        Order order = new Order(...);
        orders.save(order);
        return order.getId();
    }
}
```

**Ý nghĩa mong muốn:** các thao tác DB của use case dùng cùng transaction được transaction manager quản lý, với một connection/resource tương ứng theo configuration thực tế.

### 8.1. Không phải mỗi repository call là một transaction riêng

Nếu một Spring transaction đang active và repository dùng cùng transaction manager/resource, nhiều repository calls có thể cùng tham gia transaction ấy.

### 8.2. Transaction boundary không tự hiện qua tên method

Nếu không có transaction active, nhiều JDBC operations chạy với autocommit hoặc transaction riêng theo cấu hình. Kết quả rất khác khi ta kỳ vọng “tạo order rồi tạo items là một thao tác atomic”.

### 8.3. Boundary có thể trải qua nhiều lớp

```text
Controller
    |
    v
OrderService.createOrder() [@Transactional proxy]
    |
    +--> CustomerRepository
    +--> ProductRepository
    +--> OrderRepository
    +--> OutboxRepository
    |
    v
commit / rollback
```

Một unit of work có thể bao gồm nhiều repository. Nhưng một external HTTP call không được nhập vào PostgreSQL ACID transaction chỉ vì nằm cùng method Java.

## 9. Spring proxy và self-invocation: lỗi âm thầm phổ biến

Xem:

```java
@Service
public class InvoiceService {
    public void submit() {
        saveWithinTransaction();
    }

    @Transactional
    public void saveWithinTransaction() {
        // database writes
    }
}
```

Nếu `submit()` gọi trực tiếp `this.saveWithinTransaction()` trong cùng object, với Spring proxy-based transaction management phổ biến, cuộc gọi **không đi qua proxy**. Annotation trên inner method không được interceptor áp dụng theo cách bạn kỳ vọng.

### 9.1. Cách sửa

- Đặt `@Transactional` trên public service method được gọi qua proxy.
- Tách transactional unit sang bean khác và gọi qua dependency injection.
- Hoặc dùng `TransactionTemplate` khi cần ranh giới chương trình rõ ràng.

Ví dụ:

```java
@Service
public class InvoiceService {
    private final InvoiceWriter writer;

    public InvoiceService(InvoiceWriter writer) {
        this.writer = writer;
    }

    public void submit() {
        writer.saveWithinTransaction();
    }
}

@Service
public class InvoiceWriter {
    @Transactional
    public void saveWithinTransaction() {
        // transactional database writes
    }
}
```

### 9.2. Những tình huống cần kiểm tra thêm

- Phương thức private/final hoặc class final tùy loại proxy và framework configuration.
- Bean không do Spring quản lý.
- Lời gọi trong constructor hoặc lifecycle không qua proxy.
- Code chạy trong một thread khác không tự mang transaction context.
- Một scheduled/async boundary tạo luồng mới.
- Dùng sai transaction manager khi có nhiều DataSource.

**Cần quan sát transaction thật**, không chỉ thấy annotation trong code.

## 10. @Transactional mặc định là gì?

Các mặc định thường gặp trong Spring (cần đối chiếu cấu hình/version thực tế):

| Thuộc tính | Mặc định thường gặp |
|---|---|
| `propagation` | `REQUIRED` |
| `isolation` | `DEFAULT`: theo datasource/database |
| `readOnly` | `false` |
| `timeout` | Dựa trên transaction manager / không đặt riêng |
| Rollback | Mặc định rollback cho `RuntimeException` và `Error` |
| Checked exception | Không mặc định rollback chỉ vì là checked exception |

### 10.1. Đừng gắn mặc định isolation cho mọi DB

PostgreSQL thường mặc định `READ COMMITTED`, nhưng `@Transactional(isolation = DEFAULT)` nghĩa là dùng mức isolation cấu hình cho connection/database, không phải Spring tự đảm bảo READ COMMITTED ở mọi môi trường.

### 10.2. Checked exceptions

```java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // DB writes ...
    // có thể ném IOException
}
```

Dùng `rollbackFor` khi nghiệp vụ yêu cầu rollback với checked exception ấy. Không giả định mọi exception đều rollback theo cùng một policy.

### 10.3. Một exception bị catch có thể không kích hoạt rollback

```java
@Transactional
public void process() {
    try {
        doDatabaseWrite();
        callSomethingThatFails();
    } catch (SomeBusinessException e) {
        log.warn("Handled", e);
        // method kết thúc bình thường
    }
}
```

Nếu exception bị catch và code không đánh dấu rollback-only, transaction manager có thể commit thay đổi đã thực hiện, tùy loại lỗi và trạng thái resource. Với PostgreSQL, một lỗi SQL có thể khiến transaction chuyển sang trạng thái aborted, khi đó không thể tiếp tục SQL bình thường trước rollback.

**Cần quyết định chủ động:** lỗi nào rollback, lỗi nào được coi là xử lý thành công, và cơ sở dữ liệu đã ở trạng thái gì.

## 11. Rollback-only và UnexpectedRollbackException

Một phương thức inner tham gia transaction `REQUIRED` có thể đánh dấu transaction là rollback-only. Method outer catch exception và tưởng vẫn commit được:

```text
Outer @Transactional
   |
   +-- Inner REQUIRED joins same transaction
   |       |
   |       +-- error, marks rollback-only
   |
   +-- Outer catches error
   +-- Outer returns normally
   |
   v
Commit attempt
   |
   v
UnexpectedRollbackException / rollback
```

Không nên “giấu lỗi rồi cứ trả HTTP 200” khi transaction đã bị đánh dấu rollback-only.

### 11.1. Kiểm tra transaction state trong debug

Trong Spring có thể quan sát ngữ cảnh:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

Đây là những dấu hiệu trong tầng Spring, không thay kiểm tra connection/PostgreSQL backend và commit outcome khi nghi ngờ transaction manager không đúng.

## 12. Transaction propagation: REQUIRED và REQUIRES_NEW

### 12.1. REQUIRED

Nếu đang có transaction phù hợp, inner method **tham gia transaction hiện có**. Nếu chưa có, tạo một transaction mới.

```java
@Transactional(propagation = Propagation.REQUIRED)
public void adjustStock() {
    // joins caller transaction if present
}
```

### 12.2. REQUIRES_NEW

Inner method dùng **transaction độc lập**; transaction outer bị suspend theo cơ chế transaction manager.

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void persistAttemptLog() {
    // commits/rollbacks independently of outer transaction
}
```

**Cảnh báo:** khi outer đã giữ connection và inner cần connection khác, áp lực connection pool tăng. Nếu nhiều threads đồng thời giữ outer transactions rồi chờ inner connections, có nguy cơ pool exhaustion/deadlock-like waits.

### 12.3. REQUIRES_NEW không giải quyết “atomic order + audit”

Nếu audit bắt buộc phải rollback khi order rollback, ghi audit bằng REQUIRES_NEW là **sai mục tiêu**: audit có thể commit trong khi order rollback.

Nó chỉ hữu ích khi business thực sự muốn independent transaction và chấp nhận hệ quả consistency.

### 12.4. Không gọi self method và kỳ vọng propagation mới

Nếu `@Transactional(REQUIRES_NEW)` ở method cùng class nhưng gọi `this.inner()`, proxy có thể không intercept; transaction mới không được tạo như annotation gợi ý.

## 13. NESTED và savepoint: không đồng nhất với REQUIRES_NEW

`Propagation.NESTED` thường dùng cơ chế **savepoint** bên trong transaction hiện có khi transaction manager/driver hỗ trợ.

Mô hình:

```text
BEGIN outer transaction
   |
   +-- insert order
   |
   +-- SAVEPOINT before optional step
   |      +-- insert optional data
   |      +-- error
   |      +-- ROLLBACK TO SAVEPOINT
   |
   +-- continue outer transaction
   |
COMMIT outer transaction
```

Khác với REQUIRES_NEW:

- NESTED savepoint không phải transaction commit độc lập.
- Nếu outer rollback, các thay đổi “đã qua savepoint” vẫn rollback.
- Hỗ trợ phụ thuộc transaction manager; không mặc định `JpaTransactionManager` hỗ trợ nested semantics cho mọi JPA operations.

### 13.1. SQL minh họa

```sql
BEGIN;

INSERT INTO orm406.orders(
    customer_id, external_request_id, total_amount
)
VALUES (1, 'LAB-NESTED-001', 0);

SAVEPOINT item_step;

-- Một thao tác có thể thất bại:
INSERT INTO orm406.order_items(
    order_id, product_id, quantity, unit_price
)
VALUES (999999, 10, 1, 150000);

-- Nếu INSERT báo FK violation:
ROLLBACK TO SAVEPOINT item_step;

COMMIT;
```

Đây là **lab theo từng bước**: chỉ chạy `ROLLBACK TO SAVEPOINT` nếu savepoint đã tạo và câu lỗi đã xảy ra; không chạy như một script mong mọi câu luôn thành công.

### 13.2. Khi có JPA persistence context

Rollback tới database savepoint không tự đồng bộ mọi object state đã dirty trong ORM persistence context. Nếu thử nested transaction/savepoints bên cạnh JPA entities, cần thiết kế cách refresh/clear và hỗ trợ thực tế của provider/transaction manager.

## 14. @Transactional(readOnly = true) có ngăn DML tuyệt đối không?

Trong Spring, `readOnly=true` thường là **hint/optimization intent** đến transaction manager và ORM. Tùy cấu hình, nó có thể ảnh hưởng flush mode, connection read-only flag hoặc transaction SQL.

Nhưng không nên coi annotation này là **một hệ thống phân quyền**:

```java
@Transactional(readOnly = true)
public ProductDto getProduct(Long id) {
    // Intended read-only
}
```

### 14.1. Cần xác định điều gì được enforce thật?

- ORM có flush các entity đã thay đổi không?
- JDBC connection có read-only không?
- Transaction ở PostgreSQL có `READ ONLY` thật không?
- Native SQL có thể ghi không?
- Role có quyền INSERT/UPDATE/DELETE không?

### 14.2. PostgreSQL read-only transaction

Khi cần kiểm tra rõ trong SQL:

```sql
BEGIN READ ONLY;

SELECT count(*)
FROM orm406.products;

COMMIT;
```

Hoặc trong transaction phù hợp:

```sql
SHOW transaction_read_only;
```

Một read-only PostgreSQL transaction hạn chế các lệnh ghi theo semantics của server, nhưng đó vẫn không phải permission model cho mọi tình huống/role. Phân quyền SQL bằng GRANT/REVOKE vẫn cần.

### 14.3. Đừng tin readOnly để thay lock/consistency design

Một query chỉ đọc vẫn có thể cần snapshot nhất quán, latency giới hạn, index phù hợp hoặc quyền tenant chính xác.

## 15. Connection pool và autocommit

Ứng dụng Java thường lấy kết nối từ HikariCP hoặc một pool tương đương.

Một kết nối có trạng thái phiên:

```text
autocommit
transaction isolation
read-only flag
search_path
role/session variables
timezone
statement_timeout
prepared statements
temporary tables
locks và transaction state
```

### 15.1. JDBC autocommit

Trong JDBC thuần, connection mới thường có `autoCommit=true` nếu không được thay đổi bởi pool/framework.

```java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        // execute SQL statements on c
        c.commit();
    } catch (SQLException ex) {
        c.rollback();
        throw ex;
    }
}
```

Một transaction manager như Spring quản lý tương ứng các resource/connection. Không tự gọi `commit()` trên cùng connection nằm dưới transaction Spring mà không hiểu tác động.

### 15.2. Pool phải trả session về trạng thái phù hợp

Nếu một request chạy:

```sql
SET search_path = tenant_a;
```

và connection được trả vào pool mà không reset theo chính sách, request sau có thể kế thừa session state ngoài ý muốn.

Tương tự với `SET ROLE`, timeouts, temp tables hoặc GUC tùy biến.

### 15.3. Ưu tiên SET LOCAL cho trạng thái transaction-scoped

Trong một transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

-- Queries ...

COMMIT;
```

`SET LOCAL` áp dụng trong phạm vi transaction phù hợp, giảm rủi ro trạng thái tồn tại qua request khác. Tuy nhiên vẫn phải kiểm soát transaction ownership, connection reuse và các thao tác thiết lập session khác.

### 15.4. Tenant context không tự là authentication

Một policy dựa trên `current_setting('app.tenant_id')` có thể hữu ích trong kiến trúc được thiết kế đúng, nhưng nếu client/role có thể tùy ý `SET app.tenant_id`, nó không tự là bằng chứng ủy quyền.

## 16. Một transaction dài có giá gì?

Mẫu xấu:

```java
@Transactional
public void checkout(OrderCommand command) {
    loadAndUpdateDatabase();
    callPaymentGatewayOverHttp();
    waitForUserConfirmation();
    sendEmail();
    updateDatabaseAgain();
}
```

Giữ transaction mở trong khi chờ I/O mạng/người dùng có thể:

- Giữ connection lâu.
- Giữ row locks đến commit/rollback.
- Làm tăng lock contention.
- Giữ snapshot cũ, cản trở vacuum/reclaim tài nguyên.
- Tăng xác suất deadlock, timeout hoặc serialization failure.
- Tạo pool exhaustion khi tải cao.

### 16.1. Ranh giới nên đủ nhỏ cho một database invariant

Phân tách workflow:

```text
Transaction 1: tạo order + reservation/outbox
       |
       v
Commit
       |
       v
Gọi dịch vụ ngoài / worker
       |
       v
Transaction 2: cập nhật trạng thái dựa trên kết quả
```

Lúc này hệ thống cần state machine, idempotency và cách bù trừ khi thất bại. Nó không còn là một transaction ACID duy nhất trải qua gateway thanh toán.

### 16.2. Không cắt transaction đến mức phá atomicity

Nếu một use case cần giảm tồn kho **và** tạo order cùng thành công hoặc cùng rollback, hai thao tác DB đó nên trong một transaction đúng. Tối ưu độ dài không có nghĩa tách bất cứ hai lệnh SQL nào.

## 17. PostgreSQL READ COMMITTED và snapshot theo câu lệnh

PostgreSQL mặc định thường dùng `READ COMMITTED`.

Ở mức này, mỗi statement nhìn dữ liệu đã commit theo snapshot phù hợp tại thời điểm bắt đầu statement. Hai SELECT trong cùng transaction có thể thấy kết quả khác nhau nếu transaction khác commit ở giữa.

Ví dụ tư duy:

```text
T1: BEGIN READ COMMITTED
T1: SELECT stock_on_hand FROM products WHERE id=10 -> 5

T2: BEGIN
T2: UPDATE products SET stock_on_hand=3 WHERE id=10
T2: COMMIT

T1: SELECT stock_on_hand FROM products WHERE id=10 -> 3
T1: COMMIT
```

### 17.1. Lưu ý ORM first-level cache

Nếu T1 gọi `entityManager.find(Product.class,10)` hai lần trong cùng persistence context, lần hai có thể nhận **cùng managed entity đang có state cũ**, không phát SELECT mới.

Do đó ví dụ PostgreSQL raw SELECT ở trên không đồng nhất với:

```java
Product p1 = entityManager.find(Product.class, 10L);
Product p2 = entityManager.find(Product.class, 10L);
```

Truy vấn SQL có thể nhìn thấy 3, nhưng object managed chưa được refresh có thể còn 5.

### 17.2. @Transactional không tự cho snapshot lặp lại

Một transaction READ COMMITTED không có cam kết repeatable read cho mọi SELECT. Nếu business cần snapshot nhất quán, phải chọn isolation/protocol phù hợp.

## 18. REPEATABLE READ và SERIALIZABLE

PostgreSQL hỗ trợ các isolation levels; trong PostgreSQL, `READ UNCOMMITTED` được xử lý gần với `READ COMMITTED` thay vì cho dirty reads như một số suy luận từ chuẩn.

| Isolation | Điểm quan trọng | Ranh giới |
|---|---|---|
| READ COMMITTED | Snapshot theo câu lệnh | Non-repeatable observations có thể xảy ra |
| REPEATABLE READ | Snapshot transaction ổn định hơn theo PostgreSQL | Có thể cần retry khi concurrent updates, không ngăn mọi anomaly |
| SERIALIZABLE | PostgreSQL kiểm tra để các transaction có kết quả tương đương một thứ tự serializable | Có thể abort transaction với `40001`; phải retry toàn bộ unit |
| READ UNCOMMITTED | PostgreSQL áp dụng semantics tương đương READ COMMITTED | Không đọc dirty data như kỳ vọng một số DBMS khác |

### 18.1. Demo REPEATABLE READ

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT stock_on_hand
FROM orm406.products
WHERE product_id = 10;

-- Giả sử transaction khác commit một UPDATE.

SELECT stock_on_hand
FROM orm406.products
WHERE product_id = 10;

COMMIT;
```

Với snapshot được thiết lập đúng và không có sửa đổi tương ứng bởi chính transaction, hai SELECT thường nhìn cùng phiên bản row theo snapshot ấy.

### 18.2. SERIALIZABLE không có nghĩa không bao giờ cần retry

PostgreSQL dùng cơ chế phát hiện conflict/serialization anomalies; một transaction có thể thất bại:

```text
SQLSTATE 40001: serialization_failure
```

Ứng dụng cần retry **toàn bộ transaction logic** ở boundary thích hợp, không retry một UPDATE riêng lẻ giữa transaction đã bị abort.

### 18.3. Retry không thay authorization

Một transaction được retry có thể chạy nhiều lần. Mọi side effect ngoài DB trong body phải idempotent hoặc được tách phù hợp, nếu không sẽ lặp email/payment request.

## 19. Lost update: đọc–sửa–ghi là một race condition

Giả sử tồn kho = 5.

Hai request cùng đọc tồn kho rồi sửa object:

```text
T1 đọc stock=5
T2 đọc stock=5

T1 ghi stock=4
T2 ghi stock=4

Kết quả: 4
Trong khi đã xử lý hai lần mua 1 item,
kỳ vọng: 3
```

Nếu logic không có khóa/version/atomic update đúng, một thay đổi có thể bị mất.

### 19.1. Chỉ @Transactional là chưa đủ

Cả T1 và T2 đều có transaction không có nghĩa chúng tự bảo vệ khỏi lost update ở isolation và cách cập nhật được chọn.

### 19.2. Dùng @Version

Một entity managed với `@Version` có thể tránh việc ghi đè cùng một version mà không phát hiện. Transaction thứ hai sẽ thấy optimistic locking failure khi UPDATE version cũ không còn hợp lệ.

### 19.3. Cần xem mọi đường UPDATE

Nếu một job chạy:

```sql
UPDATE orm406.products
SET stock_on_hand = 100
WHERE product_id = 10;
```

mà không xử lý version tương ứng, nó có thể làm mất giả định optimistic locking của ORM. Phải có một protocol cập nhật nhất quán giữa JPA và SQL trực tiếp.

## 20. Cập nhật tồn kho nguyên tử bằng SQL

Khi cần giảm tồn kho nếu đủ hàng, PostgreSQL có thể thực hiện một statement:

```sql
UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 2,
    version = version + 1
WHERE product_id = 10
  AND stock_on_hand >= 2
RETURNING
    product_id,
    stock_on_hand,
    version;
```

Giải thích:

- PostgreSQL kiểm tra điều kiện trên row theo semantics concurrent UPDATE/locking.
- Nếu đủ hàng, giảm 2.
- Nếu không đủ hoặc không có product, trả **0 hàng**.
- Khi UPDATE thành công, kết quả trả tồn kho mới.
- `version` cũng tăng theo một protocol được thể hiện rõ.

### 20.1. Vì sao tốt hơn đọc stock rồi set absolute value?

Không có khoảng trống logic “SELECT ra 5, ứng dụng tính 3, sau đó UPDATE stock=3” mà không kiểm tra state hiện hành.

### 20.2. RETURNING không có nghĩa transaction đã commit

Một UPDATE trả 1 hàng có thể bị rollback sau đó. API chỉ nên báo “đặt hàng hoàn tất” khi toàn bộ transaction cần thiết commit thành công.

### 20.3. Kết hợp ORM cần chú ý state cũ

Nếu persistence context đã load Product trước câu native UPDATE, managed entity có thể còn stock/version cũ. Có thể cần refresh/clear, hoặc thiết kế use case tránh trộn native DML và dirty managed entity cho cùng row.

### 20.4. Không thử trên fixture mà quên reset

Lệnh thực hành này thay đổi stock của product 10. Trong lab, nếu cần lập lại dự đoán tồn kho ban đầu, hãy reset có chủ đích:

```sql
UPDATE orm406.products
SET stock_on_hand = 5,
    version = version + 1
WHERE product_id = 10;
```

Đừng làm reset này trên hệ thống thật, và đừng cho app tùy tiện đưa version lùi lại.

## 21. Pessimistic locking: SELECT ... FOR UPDATE

Một chiến lược khác là khóa row trước khi sửa:

```sql
BEGIN;

SELECT product_id, stock_on_hand
FROM orm406.products
WHERE product_id = 10
FOR UPDATE;

-- Trong transaction này, tính toán và UPDATE theo quy tắc.

UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 1
WHERE product_id = 10
  AND stock_on_hand >= 1;

COMMIT;
```

### 21.1. Lock giữ đến khi nào?

Row locks được giữ theo transaction semantics, thường cho tới commit hoặc rollback của transaction liên quan.

### 21.2. @Lock(PESSIMISTIC_WRITE) trên JPA

Tùy provider/dialect và câu query, JPA lock mode có thể khiến SQL chứa `FOR UPDATE` hoặc phương án tương ứng. Đừng suy đoán từ annotation mà không xem SQL thực tế.

### 21.3. Không để remote API call bên trong transaction có row lock

Lock giữ lâu khiến các giao dịch cùng sản phẩm phải chờ, tăng latency/timeout và nguy cơ deadlock.

### 21.4. NOWAIT và SKIP LOCKED có mục đích khác nhau

- `NOWAIT`: không chờ lấy lock; lỗi ngay nếu không thể lấy phù hợp.
- `SKIP LOCKED`: bỏ qua những row đang bị lock, hữu ích cho job queue.

Chúng không tương đương “lấy đúng dữ liệu nhất quán cho báo cáo”. `SKIP LOCKED` tạo góc nhìn không đầy đủ có chủ đích, không phù hợp mọi truy vấn nghiệp vụ.

## 22. SKIP LOCKED cho worker queue

Ví dụ worker cần lấy các outbox events chưa publish:

```sql
BEGIN;

SELECT event_id, payload
FROM orm406.outbox_events
WHERE published_at IS NULL
ORDER BY event_id
FOR UPDATE SKIP LOCKED
LIMIT 10;

-- Xử lý claim/mark theo thiết kế, trong transaction.

COMMIT;
```

### 22.1. Điều chưa có trong ví dụ

Câu SELECT trên **chưa phải worker hoàn chỉnh**:

- Worker phải xác định claim/lease/retry protocol.
- Không nên giữ transaction mở trong lúc gọi broker hàng giây/phút.
- Phải có idempotent consumer và dedup.
- Hàng bị bỏ qua vì lock sẽ được thử lại bằng cơ chế polling.
- Một crashed worker cần được phục hồi/lease expiration nếu đã claim.

### 22.2. PostgreSQL lock semantics không bằng exactly-once delivery

Lock tránh hai worker cùng lấy một row trong một số thời điểm. Nó không giải quyết mạng đứt sau publish nhưng trước khi mark published; broker có thể nhận duplicate khi retry.

## 23. Deadlock: hai transactions lấy lock theo thứ tự ngược

Giả sử T1:

```text
Lock product 10
  -> lock product 11
```

T2:

```text
Lock product 11
  -> lock product 10
```

Cả hai có thể chờ nhau và PostgreSQL phát hiện deadlock, abort một transaction:

```text
SQLSTATE 40P01: deadlock_detected
```

### 23.1. Giảm deadlock bằng lock ordering

Khi sửa nhiều products, thống nhất một thứ tự khóa (ví dụ theo `product_id` tăng dần) giúp giảm khả năng tạo vòng chờ.

### 23.2. Lock timeout khác deadlock

Một câu SQL có thể fail do `lock_timeout` dù chưa thành deadlock. Cần phân biệt SQLSTATE, trạng thái transaction và nguyên nhân thực.

### 23.3. Retry đúng boundary

Khi PostgreSQL abort transaction, ứng dụng cần rollback transaction đó rồi mở transaction mới cho toàn bộ use case nếu retry được. Không thể chỉ gọi lại một repository method trên transaction đã aborted.

## 24. Transaction retry: không phải cứ lỗi là thử lại

Những lỗi thường xem xét retry **có kiểm soát**:

- `40001`: serialization failure.
- `40P01`: deadlock detected.

Nhưng:

- `23505` unique violation thường có ý nghĩa nghiệp vụ (trùng external_request_id), không nên vô hạn retry.
- `23503` foreign key violation thường do dữ liệu tham chiếu sai.
- `23514` check violation thường do input không hợp lệ.
- Timeout có thể do lock/CPU/IO; retry vô điều kiện gây thêm tải.
- Lỗi mạng lúc commit có thể làm kết quả commit **không chắc chắn** đối với client: cần idempotency/reconciliation.

### 24.1. Pseudocode retry

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return transactionTemplate.execute(status ->
            performDatabaseUnitOfWork(command)
        );
    } catch (DataAccessException ex) {
        if (!isRetryableTransactionFailure(ex)
                || attempt == maxAttempts) {
            throw ex;
        }
        backoffWithJitter(attempt);
    }
}
throw new IllegalStateException("unreachable");
```

Hàm `isRetryableTransactionFailure` phải kiểm tra nguyên nhân/SQLSTATE hoặc Spring exception mapping theo driver/version. `backoffWithJitter` là placeholder cần implementation, không phải code thư viện sẵn có.

### 24.2. Retry phải bọc transaction mới

Không đặt vòng retry **bên trong** một method `@Transactional` duy nhất đã bắt đầu transaction; có thể retry trên transaction aborted/rollback-only.

### 24.3. Không lặp side effects ngoài DB

Nếu body giao dịch gửi payment request/email trước commit, retry có thể gửi nhiều lần. Tách external side effects hoặc dùng idempotency keys phù hợp.

## 25. Idempotency: bảo vệ trước client retry và timeout

Một HTTP client có thể gửi lại “tạo đơn hàng” vì không nhận được response dù transaction trước đã commit.

Chúng ta đã tạo:

```sql
external_request_id text NOT NULL UNIQUE
```

trên `orm406.orders`.

Đây là cơ sở để nhận biết một yêu cầu đã xử lý.

### 25.1. INSERT ... ON CONFLICT với PostgreSQL

```sql
INSERT INTO orm406.orders(
    customer_id,
    external_request_id,
    status,
    total_amount
)
VALUES (
    1,
    'REQUEST-XYZ-001',
    'NEW',
    150000
)
ON CONFLICT (external_request_id)
DO NOTHING
RETURNING order_id;
```

Nếu được INSERT mới, trả order_id. Nếu conflict và DO NOTHING, câu lệnh trả **0 hàng**.

### 25.2. 0 hàng không chứng minh request tương đương

Có thể cùng request ID nhưng payload khác. Khi conflict, ứng dụng cần tải order cũ và kiểm tra payload/ownership/status theo idempotency protocol. Không tự trả “thành công” nếu caller gửi request_id trùng nhưng nội dung không giống.

### 25.3. Unique constraint là tuyến phòng thủ đồng thời

Hai requests cùng external_request_id không nên dựa vào:

```text
SELECT xem đã có chưa
  -> nếu chưa thì INSERT
```

vì cả hai có thể cùng thấy chưa có. Unique constraint/ON CONFLICT xử lý race ở DB tốt hơn ứng dụng tự pre-check không khóa.

## 26. Một transaction order + item + outbox

Mục tiêu:

1. Giảm tồn kho nếu đủ.
2. Tạo order và item.
3. Ghi outbox event.
4. Cùng commit hoặc cùng rollback.

Một phiên bản SQL minh họa dùng transaction:

```sql
BEGIN;

-- 1) Reserve 1 item, chỉ thành công nếu còn hàng:
UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 1,
    version = version + 1
WHERE product_id = 10
  AND stock_on_hand >= 1
RETURNING product_id, unit_price, stock_on_hand;

-- 2) CHỈ khi bước 1 trả đúng một hàng:
INSERT INTO orm406.orders(
    customer_id, external_request_id, total_amount
)
VALUES (1, 'ORDER-406-A', 150000)
RETURNING order_id;

-- 3) Sử dụng order_id vừa trả, ví dụ 100:
-- INSERT INTO orm406.order_items(
--     order_id, product_id, quantity, unit_price
-- ) VALUES (100, 10, 1, 150000);

-- 4) Ghi outbox cho order_id thực:
-- INSERT INTO orm406.outbox_events(
--     aggregate_type, aggregate_id, event_type, payload
-- ) VALUES ('order', 100, 'OrderCreated',
--          '{"product_id": 10, "quantity": 1}'::jsonb);

-- CHỈ COMMIT sau khi các bước đúng đã chạy thành công:
-- COMMIT;
-- Khi lab chỉ minh họa/không muốn lưu: ROLLBACK;
```

Đây là **kịch bản từng bước, không phải một script end-to-end tự động hoàn chỉnh**. Giá trị `order_id=100` chỉ là placeholder, không được hard-code trong production; ứng dụng phải dùng ID thực từ `RETURNING` và xử lý 0 hàng/lỗi.

### 26.1. Lỗi thường gặp: cập nhật stock trước nhưng vẫn tạo order khi 0 row

Nếu bước UPDATE trả 0 row, phải coi đó là “không đủ tồn kho/không tồn tại sản phẩm” theo policy; không tiếp tục tạo order thành công.

### 26.2. Không commit trước outbox

Nếu order commit rồi outbox insert ở transaction khác thất bại, event có thể bị mất khỏi workflow. Ghi order + outbox cùng transaction giúp giữ liên kết durable.

### 26.3. Outbox không tự bảo đảm đúng một lần phát

Worker publish ra message broker có thể retry sau network error. Consumer phải hỗ trợ idempotent handling.

### 26.4. ORM service nên thực hiện một unit

Nếu dùng ORM để persist order/item và JDBC cho stock/outbox, chúng phải chia sẻ transaction manager/connection phù hợp. Một DataSource khác hoặc gọi service transaction riêng không tự tham gia cùng atomic unit.

## 27. @TransactionalEventListener AFTER_COMMIT có đủ durable không?

Spring hỗ trợ listener ở phase sau commit:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    // e.g. notify an in-memory listener
}
```

Nó giúp tách logic khỏi giai đoạn trước commit, nhưng **không tự bảo đảm durable event delivery**:

- Process có thể crash sau DB commit nhưng trước callback.
- Listener/broker có thể lỗi.
- Event in-memory không tự có retry store.
- Transaction resources tại callback có những semantics riêng; nếu ghi DB cần transaction thích hợp.
- Callback trong cùng process không phải message queue bền vững.

Với sự kiện quan trọng phải được giao, outbox/CDC/queue protocol thường cần hơn một AFTER_COMMIT callback.

## 28. N+1 query: một SELECT ban đầu và N SELECT phát sinh

Giả sử ta tải 100 orders, rồi trong vòng lặp đọc customer name:

```java
List<Order> orders = orderRepository.findAll();
for (Order o : orders) {
    System.out.println(o.getCustomer().getName());
}
```

Nếu customer association lazy và không được fetch trong query đầu, ORM có thể sinh:

```sql
SELECT ... FROM orm406.orders;             -- 1 query

SELECT ... FROM orm406.customers WHERE customer_id = ?;
SELECT ... FROM orm406.customers WHERE customer_id = ?;
-- ... tiếp tục theo những associations chưa được load
```

### 28.1. N+1 không luôn đúng bằng N+1 literal

First-level cache/second-level cache, nhiều orders cùng customer, fetch plan và provider behavior có thể làm số query ít hơn hoặc nhiều dạng khác. Điểm mấu chốt là số round-trips tăng theo số rows/associations.

### 28.2. Vì sao chậm?

Ngay cả SELECT theo PK rất nhanh, 100 hoặc 1.000 round-trips qua network vẫn tăng latency, connection usage và CPU.

### 28.3. Giải pháp tùy use case

- DTO projection chỉ lấy cột cần.
- `JOIN FETCH` với quan hệ phù hợp.
- `@EntityGraph`.
- Batch fetching/subselect fetching theo provider.
- Query SQL trực tiếp cho report.
- Caching có kiểm soát khi dữ liệu/consistency cho phép.

Không “sửa N+1” bằng cách chuyển mọi association sang `EAGER` toàn cục; điều đó có thể gây thừa dữ liệu hoặc N+1 theo đường khác.

## 29. DTO projection: tránh load toàn bộ entity graph

Ví dụ SQL cho màn hình danh sách order:

```sql
SELECT
    o.order_id,
    o.external_request_id,
    o.status,
    o.total_amount,
    c.full_name AS customer_name
FROM orm406.orders AS o
JOIN orm406.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

Đây có thể là một query trả đúng cột cần.

JPQL projection ý tưởng:

```java
@Query("""
    select new com.example.api.OrderRow(
        o.id, o.externalRequestId, o.status,
        o.totalAmount, c.fullName
    )
    from Order o join o.customer c
    order by o.createdAt desc, o.id desc
    """)
List<OrderRow> findRows(Pageable pageable);
```

Đoạn Java giả định DTO/mapping tương ứng đã tồn tại; không phải file runnable độc lập.

### 29.1. Projection không tự ngăn mọi N+1

Nếu DTO constructor hoặc mapper sau query lại truy cập lazy collections, có thể tạo query khác. Phải đo **tại boundary response serialization**, không chỉ ở repository return.

### 29.2. Không trả JPA entity thẳng ra JSON như mặc định

Serialization của entities có thể đi theo lazy associations, phát SQL ngoài dự kiến, lộ dữ liệu và gây recursion. Tạo DTO rõ ràng thường cho API contract dễ kiểm soát hơn.

## 30. JOIN FETCH không phải giải pháp miễn phí

Một query fetch quan hệ to-many:

```java
@Query("select o from Order o join fetch o.items")
List<Order> findWithItems();
```

có thể làm kết quả SQL lặp thông tin order theo số items:

```text
order 1 × 4 items -> 4 SQL rows
order 2 × 8 items -> 8 SQL rows
```

### 30.1. Cartesian explosion

Fetch nhiều collections (ví dụ items và discounts) có thể tạo kết quả nhân:

```text
1 order × 20 items × 10 discounts = 200 rows
```

Dù Hibernate khử trùng object order ở Java, database vẫn có thể phải tạo/truyền tập SQL lớn.

### 30.2. Pagination với fetch join collections

Kết hợp `LIMIT/OFFSET` logic với một-to-many fetch join có thể dẫn đến pagination không như kỳ vọng, warnings hoặc pagination trong memory tùy provider/version/configuration.

Thường dùng **hai pha**:

1. Query IDs của orders theo trang có ORDER BY ổn định.
2. Query orders/items theo tập IDs ấy.

Hoặc projection/aggregation được thiết kế riêng.

### 30.3. Đặt WHERE và JOIN theo nghiệp vụ

Nếu JOIN bắt buộc nhưng association optional, `INNER JOIN` có thể làm mất row. Với `LEFT JOIN`, đưa filter ở `WHERE` hay `ON` ảnh hưởng giữ row; SQL thực tế cần được kiểm tra.

## 31. LazyInitializationException và Open Session in View

Một entity có relation lazy, nhưng service transaction đã đóng:

```java
Order order = service.loadOrder(id); // transaction ends
return order.getItems().size();      // lazy collection not loaded
```

Tùy provider/configuration, việc truy cập có thể gây `LazyInitializationException`.

### 31.1. Giải pháp không nhất thiết là “bật eager hết”

Hãy đưa dữ liệu cần cho response vào một service query/transaction hợp lý và map sang DTO trước khi trả:

```java
@Transactional(readOnly = true)
public OrderDetailDto getDetail(Long id) {
    Order o = repository.findWithRequiredAssociations(id)
        .orElseThrow();
    return mapper.toDetailDto(o);
}
```

### 31.2. Open Session in View (OSIV)

OSIV giữ persistence context/session mở qua giai đoạn render HTTP response, có thể cho phép lazy loading sau service boundary.

Giới hạn:

- SQL phát trong serialization khó quan sát.
- Có thể tạo N+1 ngoài use case transaction.
- Transaction/autocommit/connection usage có thể khác kỳ vọng.
- API contract phụ thuộc graph entities.

Nhiều ứng dụng API chọn tắt OSIV và dùng DTO/fetch plan rõ. Nhưng cần kiểm tra cấu hình Spring Boot/version và nhu cầu cụ thể, không đoán OSIV luôn bật hoặc luôn tắt.

## 32. Batch INSERT/UPDATE và Hibernate

Batching giảm số round-trips khi ghi nhiều rows, nhưng phụ thuộc mapping/provider.

Ví dụ cấu hình Hibernate (tên property tùy phiên bản):

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

### 32.1. IDENTITY có thể hạn chế insert batching

Khi Hibernate cần ID từ database sau mỗi `IDENTITY INSERT`, một số phương án JDBC insert batching không hoạt động như với sequence-based generators. Đừng chỉ bật `batch_size` rồi kết luận đã có một batch INSERT.

### 32.2. SEQUENCE và allocation size

Một sequence generator có thể dùng preallocation/pooled optimizer, giảm số lần round-trip lấy ID. Nhưng thiết kế phải khớp DB sequence increment/ORM metadata, migration và concurrency requirements.

### 32.3. Batching không đồng nghĩa một transaction

Có thể batch nhiều statements trong một transaction, hoặc nhiều transactions; batch là tối ưu cách gửi lệnh, **không định nghĩa atomicity**.

### 32.4. Persistence context cần quản lý khi bulk insert lớn

Một vòng lặp persist hàng trăm nghìn entities có thể giữ rất nhiều managed objects. Có thể cần `flush()/clear()` theo batch, nhưng phải hiểu rằng `flush` gửi SQL chứ **không commit**, còn `clear` làm detach entities.

## 33. Bulk JPQL UPDATE/DELETE và cache consistency

Một JPQL bulk update như:

```java
@Modifying
@Query("""
    update Product p
    set p.stockOnHand = p.stockOnHand + :delta
    where p.id = :id
    """)
int adjust(@Param("id") Long id, @Param("delta") int delta);
```

có semantics khác việc load managed entity rồi sửa field.

### 33.1. Bulk DML không tự đồng bộ mọi managed instance

Nếu persistence context đã load Product ID 10, bulk update DB có thể thay row trong PostgreSQL nhưng instance managed trong cùng context vẫn giữ giá trị cũ.

Spring Data JPA hỗ trợ các tùy chọn như flush/clear với modifying queries trong tình huống phù hợp, nhưng chúng có hệ quả tới các thay đổi pending khác.

### 33.2. Version có thể không tự tăng

Bulk update không mặc nhiên áp optimistic locking như một entity-managed update. Nếu cần version protocol, query phải thể hiện điều kiện và cập nhật version đúng.

### 33.3. DML phải kiểm tra affected row count

`UPDATE ... WHERE id = ? AND version = ?` trả 0 rows có thể là dữ liệu đã đổi bởi transaction khác, không nên coi như update thành công.

## 34. Query pagination: OFFSET và keyset

ORM `Pageable` thường sinh `LIMIT/OFFSET` hoặc cú pháp tương ứng.

```sql
SELECT
    order_id,
    created_at,
    status
FROM orm406.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
```

Với OFFSET lớn, DB có thể phải duyệt nhiều rows trước khi trả 20 rows.

### 34.1. Keyset pagination

Nếu dùng thứ tự `created_at DESC, order_id DESC`, trang tiếp theo có thể lọc theo last seen key:

```sql
SELECT order_id, created_at, status
FROM orm406.orders
WHERE (created_at, order_id)
      < ($1::timestamptz, $2::bigint)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Đây là prepared query pattern; caller phải truyền cursor từ hàng cuối trang trước.

### 34.2. Vì sao cần tie-breaker?

`created_at` có thể trùng nhau. Thêm `order_id` tạo thứ tự ổn định phù hợp, giúp tránh bỏ/trùng rows chỉ vì đồng hồ.

### 34.3. Keyset cũng phải xét snapshot/dữ liệu thay đổi

Khi dữ liệu mới được INSERT/UPDATE giữa hai trang, tính nhất quán của feed phụ thuộc use case/cursor; keyset không tạo snapshot toàn cục vô thời hạn.

### 34.4. ORM Page<T> có thể phát COUNT query

Một repository trả `Page<Order>` có thể cần query đếm tổng số hàng bên cạnh query lấy page, tùy framework và tối ưu. Đo SQL thực tế để biết có COUNT hay không và nó có đắt không.

## 35. Đếm query thay vì đếm repository methods

Một repository method có thể:

- Không phát SQL vì cache/persistence context.
- Phát một SELECT.
- Phát thêm SELECT lazy hoặc batch-fetch.
- Phát COUNT + SELECT cho pagination.
- Phát INSERT/UPDATE khi auto-flush.
- Phát SELECT kiểm tra mapping/hierarchy tùy provider.
- Phát nhiều SQL do cascade.

Ngược lại, nhiều repository methods cùng đọc một managed entity có thể không tăng số SELECT tương ứng.

### 35.1. Cách đo

Thu thập số SQL statements và loại truy vấn trong một request/transaction end-to-end, bao gồm serialization nếu OSIV còn mở.

### 35.2. Đừng chỉ đo thời gian ở service

Một request mất 500 ms có thể gồm 50 ms SQL và 450 ms HTTP, hoặc 400 ms chờ lock và 100 ms Java. Cần trace xuyên tầng.

## 36. Log SQL Hibernate: thấy câu SQL nhưng chưa phải toàn bộ sự thật

Ví dụ cấu hình logger của Hibernate 6 (có thể khác ở Hibernate 5/provider khác):

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Có thể thấy:

```text
Hibernate:
    select p.product_id, p.stock_on_hand, p.version
    from orm406.products p
    where p.product_id=?
```

Và nếu bật bind logging:

```text
binding parameter (1:BIGINT) <- [10]
```

### 36.1. Vì sao SQL text chưa đủ?

Một dấu `?` có thể đại diện:

- bigint.
- text.
- date/timestamp.
- numeric.
- JSON/bytea.

Kiểu bind ảnh hưởng cast, chọn overload, operator/index và đôi khi query plan. Cần quan sát kiểu/giá trị ở môi trường **không lộ PII/secrets**.

### 36.2. Bind logging có thể lộ dữ liệu nhạy cảm

Trace bind values ở production có thể ghi mật khẩu, tokens, email, số giấy tờ. Chỉ bật có kiểm soát và redaction/retention rõ, hoặc dùng dữ liệu giả trong môi trường test.

### 36.3. ORM SQL logs chưa chứng minh DB đã commit

Log `INSERT` chỉ chứng minh SQL đã được gửi/được xây ở một thời điểm. Sau đó transaction có thể rollback hoặc commit lỗi.

## 37. PostgreSQL log và truy vấn thực tế

PostgreSQL có nhiều tùy chọn logging như:

```conf
# Ví dụ ý tưởng, không bật rộng trên production nếu chưa xem rủi ro:
log_min_duration_statement = '250ms'
log_lock_waits = on
deadlock_timeout = '1s'
```

Một số hệ thống còn bật `log_line_prefix` có application name/transaction/session ID để liên kết logs.

### 37.1. log_min_duration_statement

Giúp ghi nhận những statement vượt ngưỡng duration, nhưng:

- Tùy cách prepared queries/extended query protocol, thông tin log/parameters khác nhau.
- Có nguy cơ lộ dữ liệu nhạy cảm.
- Không đo được mọi query nhanh khi chỉ log slow statements.
- Thời gian statement có thể bao gồm chờ lock.

### 37.2. application_name

Gắn tên dịch vụ:

```text
application_name=checkout-api
```

giúp phân biệt query source trên PostgreSQL. Với hệ thống nhiều instances, thêm correlation/tracing ở app thay vì chỉ dựa application_name tĩnh.

### 37.3. Không bật log_statement='all' vô điều kiện

Logging mọi SQL có thể tạo overhead, log volume rất lớn và rò rỉ dữ liệu. Dùng chính sách observability theo nhu cầu và quyền xem log.

## 38. pg_stat_activity: ai đang chạy câu gì?

PostgreSQL cung cấp `pg_stat_activity` để quan sát backends.

```sql
SELECT
    pid,
    application_name,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    left(query, 300) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

### 38.1. Các trạng thái đáng chú ý

- `active`: backend đang chạy query.
- `idle`: chờ lệnh.
- `idle in transaction`: transaction đang mở nhưng backend chờ lệnh tiếp.
- `idle in transaction (aborted)`: transaction lỗi, chưa rollback/khép lại.

### 38.2. Vì sao idle in transaction nguy hiểm?

Một transaction mở lâu có thể giữ locks/snapshot và cản trở vệ sinh MVCC; nó cũng giữ connection trong pool nếu app chưa trả.

### 38.3. Query text không phải nguồn toàn năng

Quyền truy cập, cấu hình thống kê và độ dài query text có thể hạn chế thông tin. `pg_stat_activity` cung cấp **ảnh chụp trạng thái hiện tại**, không phải hồ sơ lịch sử của mọi request.

## 39. pg_locks: quan sát lock contention

Một truy vấn khái quát:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, granted, locktype;
```

### 39.1. Không phải mỗi lock đều là vấn đề

PostgreSQL sử dụng locks cho những thao tác hợp lệ. Thấy lock không có nghĩa DB đang deadlock.

### 39.2. Tìm blocking session

Có thể dùng:

```sql
SELECT
    a.pid,
    a.application_name,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 200) AS query_excerpt
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.pid;
```

Hàm `pg_blocking_pids` giúp xác định backend blockers theo semantics của PostgreSQL.

### 39.3. Không vội terminate backend

`pg_terminate_backend` có thể rollback transaction của ứng dụng, làm gián đoạn dữ liệu/khách hàng. Cần điều tra source, business impact và quyền vận hành trước khi can thiệp.

## 40. pg_stat_statements: query families và xu hướng

Extension `pg_stat_statements` hỗ trợ thống kê truy vấn theo query identity/normalized representation theo cấu hình/version.

Ví dụ bật trên môi trường được phép (có thể cần thiết lập `shared_preload_libraries` và restart server):

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

Truy vấn tham khảo:

```sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    left(query, 300) AS query_excerpt
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 40.1. Metrics quan trọng

- Số lần gọi.
- Tổng thời gian thực thi.
- Trung bình thời gian.
- Số rows.
- Block reads/hits và các metrics khác tùy view/configuration.

### 40.2. Normalization có giới hạn

Query normalization giúp gom những truy vấn cùng cấu trúc, nhưng không được xem là cơ chế redaction bảo đảm 100%. Query text vẫn có thể chứa cấu trúc/cụm nhạy cảm, còn logs/parameters có nguồn khác.

### 40.3. Pg_stat_statements không thay trace theo HTTP request

Nó chủ yếu tổng hợp theo query family, không tự biết “HTTP request 123 đã phát 17 SQL queries và 5 trong số đó do JSON serializer”. Dùng application tracing/metrics cùng DB metrics.

## 41. EXPLAIN và EXPLAIN (ANALYZE, BUFFERS)

Để hiểu kế hoạch thực thi câu SQL do ORM sinh:

```sql
EXPLAIN (VERBOSE, COSTS ON)
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM orm406.orders AS o
JOIN orm406.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'NEW'
ORDER BY o.created_at DESC
LIMIT 50;
```

Để đo thực tế trên query đọc, trong môi trường phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM orm406.orders AS o
JOIN orm406.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'NEW'
ORDER BY o.created_at DESC
LIMIT 50;
```

### 41.1. EXPLAIN không đồng nghĩa EXPLAIN ANALYZE

- `EXPLAIN` mô tả kế hoạch ước lượng, không thực thi SELECT theo cách ANALYZE đo.
- `EXPLAIN ANALYZE` **thực thi query** để đo actual time/rows.

Với UPDATE/DELETE/INSERT, `EXPLAIN ANALYZE` có thể **thực hiện DML thật**. Chỉ thử trong transaction rollback có kiểm soát nếu cần và hiểu rõ side effects, hoặc dùng môi trường staging.

### 41.2. Chú ý rows estimated vs actual

Một node:

```text
rows=100 (estimated)
actual rows=100000
```

có thể chỉ ra thống kê/selectivity sai hoặc giả định kém, kéo theo join strategy không phù hợp.

### 41.3. BUFFERS

Thông tin shared/local/temp buffers giúp phân biệt IO/caching/spill, nhưng phải kết hợp CPU, lock waits và workload. Một plan tốt trên bảng nhỏ không bảo đảm plan tốt khi hàng triệu rows.

### 41.4. Dùng query thực và bind types thực

Không phân tích một SQL “nhìn tương tự” nhưng khác WHERE/cast/join/order. Ưu tiên lấy query phát từ app, tạo test với parameter types tương ứng, rồi EXPLAIN trên dataset có phân bố đại diện.

## 42. Prepared statements và plan caching

JDBC thường dùng `PreparedStatement`:

```java
String sql = """
    SELECT product_id, stock_on_hand
    FROM orm406.products
    WHERE product_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, productId);
    try (ResultSet rs = ps.executeQuery()) {
        // consume result set
    }
}
```

### 42.1. Dùng bind giảm SQL injection

Không xây SQL bằng:

```java
String sql = "SELECT * FROM products WHERE code = '" + userInput + "'";
```

vì có rủi ro injection và khó quản lý types.

### 42.2. PreparedStatement không mặc định là một named server prepared statement

Driver có thể dùng extended query protocol, server-side preparation thresholds hoặc plan caching tùy cấu hình. Không suy ra một lần `prepareStatement` trong Java luôn tạo một prepared statement vĩnh viễn trong PostgreSQL.

### 42.3. Generic vs custom plan

PostgreSQL có cơ chế chọn generic/custom plans cho prepared statements trong những trường hợp phù hợp. Nếu các giá trị bind có phân bố rất khác nhau, một plan tổng quát có thể không tối ưu cho mọi parameter.

Điều tra bằng:

- EXPLAIN trên tham số đại diện.
- `pg_prepared_statements` cho phiên hiện tại khi liên quan.
- Các metrics latency theo giá trị/nhóm truy vấn.
- PostgreSQL documentation về plan caching và `plan_cache_mode`.

Không ép generic/custom plan khi chưa đo và hiểu tác động.

## 43. Chuyển SQL từ Hibernate log sang EXPLAIN thế nào?

Một quy trình thực tiễn:

1. Gắn request/trace ID ở ứng dụng.
2. Bật SQL logging có kiểm soát tại môi trường test hoặc sampling an toàn.
3. Ghi câu SQL do ORM sinh và **kiểu bind**.
4. Xác định mapping input thực tế, bao gồm nullable casts.
5. Khôi phục query đại diện trong psql/DB client mà không log secrets.
6. Chạy `EXPLAIN`, rồi `ANALYZE` cho SELECT an toàn trên dữ liệu test.
7. Kiểm tra indexes, estimates, row counts, sort, join, buffers, thời gian chờ.
8. Đối chiếu với `pg_stat_statements` và application tracing.
9. Sửa query/schema/index/fetch strategy theo kết quả.
10. Kiểm tra lại end-to-end request và database metrics.

### 43.1. Không chỉ thay dấu ? bằng chuỗi trong editor

Nếu Hibernate bind `OffsetDateTime`, `BigDecimal`, `UUID`, `jsonb` hoặc `bytea`, cách literal hóa sai kiểu có thể khiến PostgreSQL chọn operator/plan khác.

### 43.2. Chú ý timezone

Nếu app dùng Instant/OffsetDateTime và bảng `timestamptz`, đối chiếu timestamp ở cùng ý nghĩa tuyệt đối; đừng biến thời gian thành local string không timezone rồi so query plan.

### 43.3. Không bỏ qua LIMIT/OFFSET hoặc DISTINCT

Những chi tiết như `DISTINCT`, `ORDER BY`, `LIMIT/OFFSET`, JOIN FETCH và COUNT query có thể là chính nguồn chi phí.

## 44. auto_explain và truy vấn bên trong functions

Một số hệ thống PostgreSQL dùng extension `auto_explain` để ghi plan của slow statements theo cấu hình; nó có thể hỗ trợ phát hiện query ẩn ở bên trong functions khi bật các tùy chọn tương ứng.

Nhưng:

- Cần quyền và cấu hình phù hợp.
- Có overhead nếu bật quá rộng, đặc biệt `log_analyze`.
- Plan logs có thể chứa tên objects, query text hoặc thông tin nhạy cảm.
- Không phải mặc định được bật trên mọi managed PostgreSQL.

**Không bật auto_explain với settings rộng trên production mà không có kế hoạch giới hạn và bảo vệ log.**

## 45. Indexes phải xuất phát từ SQL thật

Nếu application thường gọi:

```sql
SELECT
    order_id,
    customer_id,
    status,
    created_at
FROM orm406.orders
WHERE customer_id = 1
  AND status = 'NEW'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Có thể xem xét index:

```sql
CREATE INDEX idx_orm406_orders_customer_status_created
ON orm406.orders(
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
```

### 45.1. Không tạo index vì có field trong entity

Các properties trong class Java không có nghĩa mọi cột cần một index độc lập. Index design dựa trên filter, join, ordering, selectivity, update load và tính chất truy vấn.

### 45.2. Index có chi phí ghi

Mỗi INSERT/UPDATE/DELETE có thể phải duy trì indexes, làm tăng WAL, CPU, disk. Không giải quyết một slow SELECT bằng hàng chục indexes “để chắc chắn”.

### 45.3. UNIQUE constraint vừa bảo vệ dữ liệu vừa hỗ trợ lookup

`external_request_id UNIQUE` không chỉ giúp tìm nhanh; nó là invariant chống duplicate dưới concurrency. ORM annotation chỉ là metadata, constraint thực tế mới thực thi ràng buộc.

## 46. N+1 và SQL statistics: một ví dụ quan sát

Giả sử endpoint trả 100 orders:

```text
HTTP GET /orders
  Repository.findAll()             -> 1 SELECT
  Map each order.customer.name     -> 37 SELECT
  Map each order.items             -> 100 SELECT
  Serializer loads product names   -> 80 SELECT
------------------------------------------------
  Total SQL                         218 SELECT
```

Đây là số liệu **minh họa** (không phải số đo từ lab). Nó cho thấy vì sao nhìn một repository method không đủ.

### 46.1. Cách đặt ngưỡng test

Một integration test có thể assert:

```text
fetch 20 order summary rows
  -> không quá một vài SQL statements hợp lý
```

Nhưng số chính xác phụ thuộc thiết kế/fetch strategy; đừng cứng nhắc “mọi endpoint chỉ được một query”. Đo latency, payload và business requirements.

### 46.2. Lấy SQL ở đâu?

- Hibernate SQL logging/statistics.
- Test utility ghi statement count.
- Datasource proxy phù hợp nếu được dùng.
- PostgreSQL query logs/pg_stat_statements.
- Distributed tracing với DB spans.

Chọn instrument không lộ PII hay secrets.

## 47. ORM cache: cache không phải transaction isolation

Các tầng cache có thể gồm:

1. Persistence context first-level cache.
2. Hibernate second-level cache (nếu bật).
3. Query cache (nếu cấu hình).
4. Application caches như Redis.
5. Database buffer cache.

### 47.1. First-level cache và repeatability của entity

EntityManager có thể trả cùng object managed nhiều lần mà không gửi SELECT; đây là đặc tính identity/state của persistence context, không phải bằng chứng PostgreSQL đang ở REPEATABLE READ.

### 47.2. Second-level cache có rủi ro invalidation

Nếu một service khác cập nhật bảng bằng native SQL mà cache layer không đồng bộ đúng, app có thể đọc state cũ.

### 47.3. Query cache có hợp với high-write dataset không?

Đôi khi không: invalidation, churn và scope/tenant có thể khiến cache tốn hơn lợi. Đo hit rate, stale data risk và mutation patterns.

### 47.4. Cache không bảo vệ lost update

Một value cache cũ có thể làm lost update tệ hơn nếu app cập nhật absolute value mà không có version/atomic predicate.

## 48. Timezone, numeric và jsonb mapping

### 48.1. timestamp vs timestamptz

- `timestamp without time zone`: giá trị ngày–giờ không kèm diễn giải timezone trong kiểu.
- `timestamptz`: PostgreSQL lưu một thời điểm tuyệt đối, hiển thị theo session timezone.

Không dùng `LocalDateTime` như một Instant có timezone nếu business cần thời điểm tuyệt đối mà không có thỏa thuận timezone.

### 48.2. Date

`date` phù hợp `LocalDate` cho ngày sinh/ngày giao không cần thời điểm.

### 48.3. Numeric

`numeric(14,2)` nên được map sang `BigDecimal` khi xử lý tiền để tránh sai số binary floating point.

### 48.4. jsonb

ORM/provider có thể hỗ trợ JSON mapping; nhưng `jsonb` có semantics riêng:

- JSON objects/arrays.
- Index GIN, operators và path queries.
- JSON null khác SQL NULL.
- Validation/schema evolution cần ứng dụng quản lý.

Không biến toàn bộ domain model thành một jsonb blob chỉ để tránh migration quan hệ.

### 48.5. Nullability

Một Java field `@NotNull` trong Bean Validation và một `NOT NULL` constraint ở PostgreSQL là hai lớp kiểm tra khác nhau. Cần đồng nhất, nhưng database constraint phải có thật.

## 49. RLS/tenant boundaries với ORM

ORM có thể tự thêm điều kiện theo tenant trong repository query, nhưng đó không phải cách ly dữ liệu tuyệt đối nếu:

- Có native SQL không qua filter.
- Có background job/administrative query khác.
- Có một entity graph/relation chưa áp filter.
- Có SQL injection dưới role quá rộng.
- Có DB view/function chạy với quyền khác.

### 49.1. Phân tầng an toàn

```text
Authentication
  -> trusted tenant identity
  -> service authorization
  -> ORM filter/query scoping
  -> PostgreSQL RLS where appropriate
  -> GRANT/role separation
  -> audit/monitoring
```

### 49.2. RLS không bảo vệ tenant nếu role bypass

Superuser, BYPASSRLS và một số owner contexts có quy tắc bypass. Không dùng app superuser.

### 49.3. Session tenant context và connection pool

Khi dùng GUC/role cho RLS, phải đảm bảo:

- Context đến từ identity đáng tin.
- Không bị user tự đổi qua unrestricted SQL.
- Được thiết lập đúng trong transaction.
- Được reset khi connection trở về pool.
- Được test dưới effective DB role của ứng dụng.

### 49.4. Schema per tenant có trade-off khác

Schema-per-tenant và database-per-tenant tạo các lựa chọn khác về migration, connection pools, search_path, privileges, backup và monitoring. ORM có multi-tenancy support không có nghĩa database tự chứng minh authorization đúng.

## 50. Migration/schema validation: tránh để Hibernate tự sửa production

Trong phát triển, có thể thấy:

```properties
spring.jpa.hibernate.ddl-auto=update
```

Nó tiện trong một số lab nhưng rủi ro cao khi dùng để thay đổi schema production không kiểm soát.

### 50.1. Khuyến nghị kiến trúc

- Dùng migration có version như Flyway/Liquibase hoặc SQL scripts được review.
- DDL được chạy ở deployment boundary có quyền phù hợp.
- Application role không có quyền CREATE/ALTER rộng trong production.
- ORM mapping được kiểm tra tương thích với schema.
- Migrations được test trên PostgreSQL version thật và dữ liệu đại diện.
- Indexes lớn cần kế hoạch locks, concurrency, rollout.

### 50.2. @Column(unique=true) không thay UNIQUE migration

Có `@Column(unique=true)` trong entity không có nghĩa PostgreSQL đang có unique constraint đúng. Luôn xác minh catalog/DDL thực tế.

### 50.3. enum mapping

Một Java enum được map sang text hoặc PostgreSQL enum type có trade-off về migration, thêm giá trị, đổi tên, compatibility và check constraints. Không đổi enum mapping mà chưa đánh giá dữ liệu cũ.

### 50.4. Sequence allocation mismatch

Nếu ORM generator và database sequence increment không khớp, có thể gây hiệu ứng cấp ID lạ hoặc lỗi tùy provider. Kiểm tra DDL sequence và mapping khi chuyển từ IDENTITY sang SEQUENCE.

## 51. Pool sizing: nhiều connection hơn không luôn nhanh hơn

Một connection pool có các giới hạn:

```text
maxPoolSize
minIdle
connectionTimeout
idleTimeout
maxLifetime
validationQuery/connectionTestQuery (khi áp dụng)
leakDetectionThreshold (phục vụ chẩn đoán)
```

Tên property tùy pool/configuration.

### 51.1. Pool lớn có thể làm PostgreSQL quá tải

Nhiều connections đồng thời tạo thêm CPU scheduling, memory và contention. Nếu database tối ưu ở 20 active queries, mở 200 connections cùng thực thi không tự làm hệ thống nhanh gấp 10.

### 51.2. Pool starvation do transaction dài

Một request giữ connection qua HTTP call và hàng trăm requests khác chờ pool có thể làm latency tăng đột biến dù SQL statement thực tế rất ngắn.

### 51.3. REQUIRES_NEW gây nhu cầu connection thêm

Outer transaction giữ một connection, inner REQUIRES_NEW cần connection khác. Nếu pool quá chật, nhiều threads có thể chờ nhau. Cần tính cả propagation khi sizing.

### 51.4. Kiểm tra trực tiếp

Kết hợp pool metrics (active/idle/pending), `pg_stat_activity`, DB CPU/locks và request trace. Không chỉ tăng `maximumPoolSize` khi thấy timeout.

## 52. Statement timeout, lock timeout và idle transaction timeout

PostgreSQL hỗ trợ các giới hạn:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

SELECT *
FROM orm406.products
WHERE product_id = 10;

COMMIT;
```

### 52.1. statement_timeout

Giới hạn thời gian statement theo semantics PostgreSQL. Nó không tương đương HTTP request timeout hay JPA transaction timeout trong mọi cấu hình.

### 52.2. lock_timeout

Hạn thời gian chờ để lấy lock; nếu cần chờ quá mức, query bị hủy. Đặt quá thấp có thể làm workload hợp lệ thất bại thường xuyên.

### 52.3. idle_in_transaction_session_timeout

Hữu ích để xử lý sessions bị bỏ quên trong transaction, nhưng terminate transaction có thể khiến ứng dụng thấy lỗi cần xử lý. Không dùng như thay thế cho việc quản lý transaction boundary đúng.

### 52.4. Timeout layering

Cần phối hợp:

```text
HTTP timeout
    |
    +-- service-level deadline
    |
    +-- connection acquisition timeout
    |
    +-- transaction timeout
    |
    +-- statement_timeout
    |
    +-- lock_timeout
```

Nếu HTTP đã trả timeout nhưng DB query còn chạy dài, có nguy cơ xử lý thừa hoặc kết quả không xác định với client. Thiết kế cancellation/idempotency và quan sát request lifecycle.

## 53. Một kịch bản lỗi transaction: SQL thành công nhưng response thất bại

Timeline:

```text
T1: Service tạo order.
T2: Hibernate flush -> INSERT thành công.
T3: PostgreSQL COMMIT thành công.
T4: Network giữa app và client đứt.
T5: Client không nhận order_id.
T6: Client retry cùng request.
```

Nếu request 2 tạo order mới, hệ thống có duplicate business effect.

### 53.1. Cách xử lý

- Client cung cấp idempotency key.
- PostgreSQL có unique constraint trên key.
- Service kiểm tra yêu cầu cũ cùng payload.
- Trả kết quả đã commit tương ứng nếu retry hợp lệ.
- Không dựa vào “client không nhận HTTP 200” để kết luận rollback.

### 53.2. Không biến exception HTTP thành bằng chứng DB rollback

Một lỗi trong giai đoạn trả response có thể xảy ra **sau commit**. Ranh giới database transaction đã đóng, rollback Java không thể quay lại transaction trước đó.

## 54. Một kịch bản lỗi khác: flush đã chạy nhưng cuối cùng rollback

Timeline:

```text
T1: BEGIN.
T2: INSERT order -> PostgreSQL nhận.
T3: INSERT order_item -> PostgreSQL nhận.
T4: INSERT outbox -> lỗi constraint.
T5: Transaction rollback.
T6: Query từ transaction khác không thấy order/item.
```

### 54.1. Vì sao không nên log “order created” quá sớm?

Nếu log/metric có ý nghĩa business event thành công, phát nó trước commit khiến observability lệch với trạng thái durable.

### 54.2. Logging và outbox khác nhau

- Log chẩn đoán có thể ghi “attempt started”, “SQL sent”, “rollback”.
- Outbox event dành cho hậu quả business đã commit và được consumer xử lý theo protocol.

Không dùng log text làm durable event queue.

## 55. Transaction boundary và API composition

Một endpoint gọi nhiều service:

```java
@PostMapping("/checkout")
public OrderResponse checkout(@RequestBody CheckoutRequest req) {
    Customer c = customerService.load(req.customerId());
    Order o = orderService.create(req, c);
    inventoryService.decrement(req.items());
    paymentService.charge(req.paymentToken());
    return ...;
}
```

Nếu từng method tự mở transaction khác nhau, request này **không có một database transaction nguyên tử** chỉ vì endpoint là một HTTP request.

### 55.1. Chọn một application service orchestration

Nếu database invariant cần atomicity, tạo một transactional method bao các thao tác DB liên quan. External payment thực hiện qua workflow khác hoặc với protocol phù hợp.

### 55.2. Ranh giới transaction không nên trải qua thread mới không kiểm soát

`@Async` hoặc executor thread thường không thừa hưởng transaction Spring ThreadLocal context tự động. Một method async có thể dùng connection/transaction riêng.

### 55.3. Multiple DataSources

Hai database khác nhau được dùng trong một Java method không tự tạo distributed ACID transaction với `@Transactional` gắn một transaction manager. Nếu thật sự cần coordination, phải chọn kiến trúc rõ (XA/JTA với giới hạn, saga/outbox hoặc consistency model khác).

### 55.4. TransactionTemplate khi boundary phức tạp

Với retry/outside-I/O split, `TransactionTemplate` có thể làm phạm vi transaction rõ và hỗ trợ khởi tạo transaction mới từng attempt, miễn sử dụng đúng transaction manager.

## 56. Kiểm tra query generated: một quy trình end-to-end

Giả sử endpoint chậm: `GET /customers/1/orders`.

**Bước 1:** đo request p95/p99 và correlation ID.

**Bước 2:** quan sát số SQL statements và thời gian trong application tracing.

**Bước 3:** xác định N+1 do mapping entities/serialization.

**Bước 4:** ghi SQL thực tế và kiểu bind (dùng test data, không log secrets).

**Bước 5:** tìm query families đắt trên `pg_stat_statements`.

**Bước 6:** xem hoạt động chờ khóa/idle transactions qua `pg_stat_activity` và `pg_locks`.

**Bước 7:** `EXPLAIN (ANALYZE, BUFFERS)` SELECT chậm trên dữ liệu đại diện.

**Bước 8:** cải tiến fetch plan/projection/index/query/pagination/transaction length.

**Bước 9:** chạy lại cùng load và kiểm tra correctness/row counts/locks.

**Bước 10:** triển khai có monitoring/rollback.

### 56.1. Đừng sửa index trước khi biết câu SQL thật

Một slow request có thể do:

- 101 queries ngắn thay vì một query dài.
- Chờ lock.
- JDBC pool wait.
- Lỗi slow serializer.
- External API.
- Garbage collection.
- Một query thiếu index.

Mỗi nguyên nhân có cách sửa khác.

## 57. Mẫu integration test cho transaction rollback

Một integration test nên thực hiện:

1. Bắt đầu một use case DB có nhiều bước.
2. Gây lỗi có chủ đích ở bước cuối (ví dụ unique violation).
3. Đảm bảo method báo lỗi/rollback.
4. Dùng một transaction/connection khác để xác nhận không có order/item/outbox mới.
5. Kiểm tra sequence gap không bị hiểu là “hàng đã commit”.
6. Kiểm tra external side effect không được phát trước commit.

Pseudo-code:

```java
@Test
void orderAndOutboxRollbackTogether() {
    assertThrows(
        SomeExpectedException.class,
        () -> orderService.createWithInjectedOutboxFailure(command)
    );

    // Quan sát bằng transaction/EntityManager sạch:
    assertThat(orderRepository.findByExternalRequestId(key))
        .isEmpty();
    assertThat(outboxRepository.findByBusinessKey(key))
        .isEmpty();
}
```

### 57.1. Test method @Transactional có thể tạo false confidence

Nếu integration test được bọc `@Transactional` và auto-rollback, nó có thể không đi qua cùng commit boundary của production service. Khi muốn test **commit-time errors** hoặc `REQUIRES_NEW`, cần xây test boundary cẩn thận.

### 57.2. Dùng PostgreSQL thật cho behavior-specific tests

H2/in-memory DB có thể khác PostgreSQL về:

- Isolation and locking.
- `ON CONFLICT`.
- `RETURNING`.
- `jsonb`.
- Indexes/partial indexes.
- Sequence/identity.
- SQLSTATE.
- RLS.

Dùng PostgreSQL test container/instance phù hợp khi những đặc tính ấy là trọng tâm.

## 58. Các lỗi phổ biến khi dùng ORM và giao dịch

### Lỗi 1 — Coi save là commit

`save` có thể chỉ đưa entity vào context hoặc phát INSERT sớm, không chứng minh transaction commit.

### Lỗi 2 — Coi flush là commit

Flush đồng bộ SQL trong transaction; rollback vẫn có thể xảy ra.

### Lỗi 3 — Dùng @Transactional ở method self-invoked

Proxy không intercept lời gọi `this.inner()` trong cấu hình proxy thường gặp.

### Lỗi 4 — Coi @Transactional(readOnly=true) là quyền SELECT-only

Nó không thay DB grants và RLS.

### Lỗi 5 — Catch exception rồi nghĩ Spring chắc chắn rollback

Nếu không propagate/mark rollback, framework có thể cố commit; lỗi SQL còn có thể làm transaction aborted.

### Lỗi 6 — Retry serialization error trong transaction cũ

Transaction aborted cần rollback, mở transaction mới.

### Lỗi 7 — Retry mọi SQLSTATE

Unique/FK/check violations không được giải quyết bằng retry mù quáng.

### Lỗi 8 — Gửi email/payment trong DB transaction rồi trông chờ rollback cả hai

External side effect không tham gia PostgreSQL ACID transaction.

### Lỗi 9 — Dùng REQUIRES_NEW cho audit bắt buộc rollback theo order

Independent commit có thể làm audit tồn tại khi order thất bại.

### Lỗi 10 — NESTED được hiểu là commit độc lập

Savepoint không tạo một durable transaction độc lập.

### Lỗi 11 — Đọc stock rồi set stock-1 không khóa/version

Race có thể gây lost update.

### Lỗi 12 — ORM @Version nhưng native SQL không cập nhật version

Có thể phá optimistic locking protocol.

### Lỗi 13 — Bulk JPQL UPDATE rồi tin managed entity đã refresh

Persistence context có thể còn stale.

### Lỗi 14 — N+1 do lazy associations

Một repository call có thể tạo nhiều SQL khi mapping/serialization.

### Lỗi 15 — Set toàn bộ relation EAGER để sửa N+1

Có thể tăng payload, JOIN explosion và tạo truy vấn khác.

### Lỗi 16 — JOIN FETCH nhiều collections với Pageable

Có thể dẫn tới cartesian explosion hoặc pagination không như mong muốn.

### Lỗi 17 — Bật batch_size nhưng dùng IDENTITY và không đo SQL

Batching có thể không hoạt động như kỳ vọng.

### Lỗi 18 — Coi @Column(unique=true) là đã có unique index/constraint thật

Phải kiểm tra migration/schema PostgreSQL.

### Lỗi 19 — Mở transaction qua HTTP call

Giữ connection/locks/snapshot lâu và tăng contention.

### Lỗi 20 — Bật OSIV rồi không quan sát query khi serialize

SQL có thể phát ngoài service boundary.

### Lỗi 21 — Dùng Entity trực tiếp làm API response

Có thể lộ data và phát lazy queries/recursion.

### Lỗi 22 — Chỉ đọc log Hibernate mà không xem bind type

Loại param có thể ảnh hưởng operator, plan và semantics.

### Lỗi 23 — Bật SQL/bind logging rộng trên production

Có thể lộ secrets/PII và tạo log volume lớn.

### Lỗi 24 — Chạy EXPLAIN ANALYZE UPDATE trên dữ liệu thật

ANALYZE **thực thi statement**, có thể thay đổi dữ liệu.

### Lỗi 25 — Coi pg_stat_statements là trace của một HTTP request

Nó chủ yếu tổng hợp query families, không cung cấp mọi request context.

### Lỗi 26 — Coi first-level cache là isolation level

Persistence context state và PostgreSQL MVCC snapshots khác nhau.

### Lỗi 27 — Pagination chỉ ORDER BY created_at

Timestamps có thể trùng, thứ tự không ổn định.

### Lỗi 28 — OFFSET rất lớn mà không đo plan

Có thể gây nhiều work trước khi trả page.

### Lỗi 29 — Tăng pool size để sửa mọi latency

Có thể làm DB quá tải hơn và không giải quyết lock/N+1.

### Lỗi 30 — Không reset connection/session state trong pool

Có thể rò rỉ search_path/tenant/role/timeouts giữa requests.

### Lỗi 31 — Dùng app role SUPERUSER để giải quyết quyền

Phá boundary RLS/permissions và tăng blast radius.

### Lỗi 32 — Tin rằng SQL UPDATE RETURNING một hàng nghĩa đã commit

Chỉ là kết quả statement trong transaction hiện tại.

### Lỗi 33 — Retry HTTP tạo order mà không có idempotency key

Có thể tạo duplicate order nếu response bị mất sau commit.

### Lỗi 34 — Không kiểm tra affected rows của optimistic/conditional UPDATE

0 rows có thể là conflict hoặc điều kiện nghiệp vụ không được thỏa.

### Lỗi 35 — Để Hibernate tự update schema production

Có rủi ro DDL không kiểm soát, downtime và sai lệch migration.

### Lỗi 36 — Đo trên bảng có 3 hàng rồi kết luận query tốt ở 30 triệu hàng

Plan/index choice và cardinality khác rất lớn theo dữ liệu thực.

## 59. Bài tập thực hành có đáp án

Các bài tập dựa trên schema `orm406` và các tình huống Java/Spring. Khi câu SQL thay đổi dữ liệu, chạy trong transaction lab riêng và rollback/reset nếu cần.

### Bài 1. ORM có xóa bỏ SQL không?

**Đáp án:** không. ORM ánh xạ object operations thành SQL hoặc các thao tác persistence thích hợp.

### Bài 2. JPA và Hibernate khác nhau thế nào?

**Đáp án:** JPA là đặc tả persistence; Hibernate là một implementation/provider phổ biến, có các tính năng riêng.

### Bài 3. Một managed entity đổi field cần gọi save mỗi lần?

**Đáp án:** không nhất thiết; dirty checking có thể phát SQL khi flush trong transaction.

### Bài 4. save(order) trả về id, transaction đã commit chưa?

**Đáp án:** chưa thể kết luận. ID có thể được cấp trước/during INSERT; commit là boundary khác.

### Bài 5. flush xong rồi rollback thì row còn không?

**Đáp án:** row DML chưa commit được rollback, trừ những side effects không thuộc transaction như sequence value đã cấp.

### Bài 6. Khi nào auto-flush có thể xảy ra?

**Đáp án:** trước một số queries, trước commit hoặc khi explicit flush; phụ thuộc flush mode/provider.

### Bài 7. Tại sao this.innerTransactional() có thể không tạo transaction?

**Đáp án:** self-invocation bỏ qua Spring proxy trong proxy-based transaction management thường gặp.

### Bài 8. @Transactional rollback checked exception mặc định?

**Đáp án:** không mặc định chỉ vì là checked exception. Có thể dùng rollbackFor hoặc policy được cấu hình.

### Bài 9. Inner REQUIRED báo lỗi và đánh dấu rollback-only, outer catch lỗi rồi trả bình thường?

**Đáp án:** transaction vẫn có thể rollback và outer gặp UnexpectedRollbackException khi commit.

### Bài 10. REQUIRES_NEW có commit độc lập khỏi outer không?

**Đáp án:** có transaction độc lập theo manager tương ứng; outer rollback không tự rollback một inner transaction đã commit.

### Bài 11. Vì sao REQUIRES_NEW ảnh hưởng connection pool?

**Đáp án:** outer có thể giữ connection trong khi inner cần connection khác.

### Bài 12. NESTED và REQUIRES_NEW có tương đương?

**Đáp án:** không; NESTED dựa trên savepoint trong transaction lớn khi được hỗ trợ, không commit độc lập.

### Bài 13. readOnly=true có thay GRANT không?

**Đáp án:** không. Nó không thay SQL authorization.

### Bài 14. JDBC autoCommit=true mang nghĩa gì?

**Đáp án:** theo JDBC transaction handling, statements có thể được commit tự động khi hoàn tất; framework/pool có thể đổi setting.

### Bài 15. Nếu app set search_path theo tenant nhưng không reset connection?

**Đáp án:** request kế tiếp có thể kế thừa state, tạo lỗi hoặc rò rỉ tenant. Dùng transaction-scoped state/quản trị pool đúng.

### Bài 16. Hai SELECT trong READ COMMITTED có thể thấy kết quả khác?

**Đáp án:** có, nếu transaction khác commit ở giữa, và truy vấn thực được gửi/không bị entity cache che state mới.

### Bài 17. REPEATABLE READ có nghĩa mọi transaction không bao giờ fail?

**Đáp án:** không; concurrent updates/conflicts vẫn có thể gây lỗi cần retry.

### Bài 18. SQLSTATE 40001 biểu thị gì?

**Đáp án:** serialization failure; thường cần retry toàn bộ transaction với policy phù hợp.

### Bài 19. SQLSTATE 40P01 biểu thị gì?

**Đáp án:** deadlock detected; một transaction bị abort, cần rollback/retry có giới hạn.

### Bài 20. Lost update trong ví dụ stock=5, hai người mua một sản phẩm có thể dẫn tới?

**Đáp án:** nếu cả hai set absolute stock=4 từ snapshot cũ, tồn kho sai (kỳ vọng 3).

### Bài 21. Dùng UPDATE atomic để trừ một sản phẩm

```sql
UPDATE orm406.products
SET stock_on_hand = stock_on_hand - 1,
    version = version + 1
WHERE product_id = 10
  AND stock_on_hand >= 1
RETURNING stock_on_hand;
```

**Đáp án:** trả hàng khi thành công; 0 hàng nếu không đủ stock hoặc không có product.

### Bài 22. UPDATE RETURNING một hàng có nghĩa commit thành công?

**Đáp án:** không, transaction có thể rollback sau đó.

### Bài 23. @Version bảo vệ native SQL không kiểm tra version?

**Đáp án:** không tự động. Phải đưa native SQL vào cùng locking/version protocol nếu cần.

### Bài 24. FOR UPDATE phù hợp trường hợp nào?

**Đáp án:** cần khóa row để thực hiện một chuỗi thao tác đọc–sửa theo transaction; phải giữ transaction ngắn.

### Bài 25. SKIP LOCKED phù hợp báo cáo doanh thu chính xác không?

**Đáp án:** thường không; nó bỏ qua những rows bị khóa và có thể tạo góc nhìn không đầy đủ. Phù hợp hơn cho worker queue.

### Bài 26. Vì sao retry một transaction có payment call trong body nguy hiểm?

**Đáp án:** external payment có thể bị gọi nhiều lần nếu transaction bị retry.

### Bài 27. external_request_id UNIQUE giúp gì?

**Đáp án:** giảm tạo trùng order khi client retry, nhưng cần kiểm tra payload/ownership khi ID trùng.

### Bài 28. ON CONFLICT DO NOTHING RETURNING trả gì khi conflict?

**Đáp án:** 0 hàng cho insert bị bỏ qua.

### Bài 29. Order và outbox nên commit trong mấy transactions nếu cần atomicity?

**Đáp án:** một PostgreSQL transaction chung khi có thể.

### Bài 30. AFTER_COMMIT listener có tự durable event delivery không?

**Đáp án:** không; crash giữa commit và callback có thể làm mất event. Outbox/CDC xử lý bài toán khác.

### Bài 31. N+1 là gì?

**Đáp án:** một query lấy danh sách dẫn tới nhiều queries bổ sung khi duyệt associations, gây round-trip overhead.

### Bài 32. EAGER trên mọi association có luôn sửa N+1?

**Đáp án:** không; có thể tạo JOIN lớn, truy vấn bổ sung hoặc over-fetching.

### Bài 33. Fetch join 2 collections có rủi ro gì?

**Đáp án:** cartesian explosion/multiple collection fetch limitations và pagination không như kỳ vọng.

### Bài 34. DTO projection phù hợp khi nào?

**Đáp án:** query chỉ cần các cột phục vụ API, tránh load cả entity graph.

### Bài 35. OSIV có thể tạo SQL ở giai đoạn nào?

**Đáp án:** trong rendering/serialization sau service method, tùy cấu hình/provider.

### Bài 36. Hibernate JDBC batch_size=50 có bảo đảm INSERT được batch khi IDENTITY?

**Đáp án:** không; ID generation và provider behavior có thể hạn chế.

### Bài 37. Bulk JPQL UPDATE có tự refresh managed entity không?

**Đáp án:** không mặc nhiên; context có thể stale, cần xử lý state/version.

### Bài 38. Vì sao PAGE có thể chạy hai query?

**Đáp án:** lấy rows và có thể đếm tổng (COUNT) để biết total elements/pages.

### Bài 39. Keyset pagination cần gì?

**Đáp án:** thứ tự hoàn chỉnh và cursor từ last seen key, ví dụ (created_at, order_id).

### Bài 40. Cách tránh SQL injection trong JDBC?

**Đáp án:** `PreparedStatement` + bind parameters; không nối user input vào SQL text.

### Bài 41. Bật Hibernate bind TRACE ở production có nguy cơ gì?

**Đáp án:** lộ PII/credentials và tăng log volume.

### Bài 42. pg_stat_activity cho biết điều gì?

**Đáp án:** trạng thái backends, query/current wait, transaction age, nhưng là snapshot có quyền/giới hạn.

### Bài 43. idle in transaction có thể gây tác hại gì?

**Đáp án:** giữ locks/snapshot/connection, tăng contention và ảnh hưởng vacuum.

### Bài 44. pg_stat_statements có biết request HTTP cụ thể không?

**Đáp án:** không tự biết; nó tổng hợp query families, cần kết hợp app tracing.

### Bài 45. EXPLAIN ANALYZE UPDATE có an toàn trên production không?

**Đáp án:** nó thực thi UPDATE; cần môi trường test/rollback có kiểm soát và hiểu side effects.

### Bài 46. SQL log có dấu ?, phân tích plan cần thêm gì?

**Đáp án:** kiểu bind/giá trị đại diện, session context, schema/search_path và query chính xác.

### Bài 47. Index nào có thể phù hợp query theo customer+status+created_at?

**Đáp án:** một index bắt đầu với (customer_id, status, created_at DESC, order_id DESC) có thể hữu ích, cần EXPLAIN với dữ liệu đại diện.

### Bài 48. Pool size càng lớn càng nhanh?

**Đáp án:** không; có thể làm DB chịu nhiều contention hơn. Quan sát active/pending/locks/DB capacity.

### Bài 49. Email gửi sau flush nhưng trước commit, transaction rollback; email có rollback không?

**Đáp án:** không. Cần workflow/outbox và idempotency.

### Bài 50. Test với H2 có đủ để xác minh ON CONFLICT/SKIP LOCKED không?

**Đáp án:** không; phải thử PostgreSQL thật khi phụ thuộc tính năng PostgreSQL.

## 60. Checklist kiểm tra trước khi triển khai ORM use case

| Câu hỏi | Điều phải nắm |
|---|---|
| Use case nào là một atomic DB unit? | Transaction boundary |
| @Transactional thực sự được intercept? | Proxy/self-invocation/thread |
| Transaction manager đúng DataSource? | Multi-DataSource correctness |
| Có external I/O trong transaction? | Lock duration/side effects |
| Service method có thể throw checked exception? | rollbackFor policy |
| Có catch exception làm mất rollback intent? | rollback-only/commit behavior |
| Có dùng REQUIRES_NEW/NESTED? | Independent commit/savepoints |
| Có nhiều rows cùng được update đồng thời? | Version/locks/atomic SQL |
| Có cần retry 40001/40P01? | New transaction/limited backoff |
| Client có thể retry request? | Unique idempotency key |
| Có outbox cho event quan trọng? | Atomic DB write, async delivery |
| Entity states/dirty checking đã hiểu? | Managed/detached |
| Flush/commit được phân biệt? | Correct success signaling |
| Có native DML cùng managed entities? | Stale persistence context |
| Bulk JPQL update có quản lý version? | Optimistic locking |
| Có lazy relations trong serializer? | N+1/OSIV |
| Fetch joins có làm kết quả phình? | Cartesian explosion |
| Pagination có ORDER BY ổn định? | Tie-breakers/keyset |
| Page<T> có count query tốn kém? | Query counts |
| JDBC batching có thực sự hoạt động? | ID strategy/SQL logs |
| ORM mapping khớp DDL? | Constraint/index/type verification |
| Tiền và thời gian map đúng? | BigDecimal/timestamptz |
| Tất cả SQL đã được bind an toàn? | PreparedStatement |
| Log SQL có lộ PII/keys? | Redaction/sampling |
| Có thấy SQL thực sự phát ra? | Hibernate logs/JDBC |
| Có thấy chờ DB/locks? | pg_stat_activity/pg_locks |
| Có thống kê top query families? | pg_stat_statements |
| EXPLAIN trên dữ liệu đại diện? | Plan, actual rows, buffers |
| Có đo cả pool wait/network/serialization? | End-to-end tracing |
| Connection/session state có reset? | Pool, search_path, role |
| Role app có quyền tối thiểu? | GRANT/RLS, không SUPERUSER |
| Transaction có timeout hợp lý? | statement/lock/deadline |
| Idle-in-transaction được giám sát? | Pool/DB metrics |
| Migrations được review/versioned? | Flyway/Liquibase/DDL |
| Integration tests chạy PostgreSQL thật? | Isolation/locking/SQLSTATE |
| Có test commit-time failure và retry? | Correct rollback/idempotency |

## 61. Bảng tra cứu nhanh

| Tình huống | Cơ chế liên quan | Cần kiểm chứng |
|---|---|---|
| Lưu entity mới | `persist/save` | Khi nào INSERT/ID được tạo |
| Đổi managed field | Dirty checking | SQL UPDATE lúc flush |
| Muốn ép SQL trước commit | `flush` | Chưa commit |
| Cần atomicity nhiều repository calls | `@Transactional` | Proxy + manager đúng |
| Inner method cần transaction chung | `REQUIRED` | Join transaction hiện có |
| Inner method cần commit độc lập | `REQUIRES_NEW` | Pool và consistency |
| Partial rollback trong transaction | `NESTED`/savepoint | Manager/provider support |
| Tránh lost update | `@Version` hoặc atomic UPDATE | Đồng bộ cả native DML |
| Khóa row | `FOR UPDATE` | Giữ transaction ngắn |
| Worker queue | `SKIP LOCKED` | Lease/retry/idempotency |
| Serialization failure | SQLSTATE `40001` | Retry toàn transaction |
| Deadlock | SQLSTATE `40P01` | Lock order/retry |
| Client retry | Unique request ID | Payload consistency |
| Sau commit phát event durable | Outbox + worker/CDC | Consumer idempotency |
| N+1 | DTO/fetch plan/batch fetch | SQL count và latency |
| Fetch join nhiều collections | Hai-phase loading/projection | Query rows/pagination |
| Bulk update | Native SQL/JPQL | Context/version consistency |
| SQL do ORM tạo | Hibernate SQL logger | Bind types/sensitive logging |
| Backend đang làm gì | `pg_stat_activity` | Wait/transaction age |
| Ai giữ lock | `pg_locks`, `pg_blocking_pids` | Blockers |
| Query families chậm | `pg_stat_statements` | Calls/time/rows |
| Query plan | `EXPLAIN` | Estimates/indexes |
| Actual query plan | `EXPLAIN (ANALYZE, BUFFERS)` | Thực thi statement |
| Quản lý schema | SQL migrations | DDL đúng với mapping |
| Data integrity | DB constraints | Không chỉ annotation |
| Tenant protection | Roles + RLS | Trusted context/pool |
| Query timeout | statement/lock timeouts | Các deadline phối hợp |

## 62. Tài liệu tham khảo và hướng đọc tiếp

**PostgreSQL:**

- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — READ COMMITTED, REPEATABLE READ, SERIALIZABLE.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks, table locks, deadlocks.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — `ON CONFLICT`, `RETURNING`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — conditional updates, row counts, RETURNING.
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html) và [ROLLBACK TO SAVEPOINT](https://www.postgresql.org/docs/current/sql-rollback-to.html).
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW) — backend, wait events, transaction age.
- [pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html) — lock monitoring.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — thống kê query.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — kế hoạch ước lượng và thực thi.
- [Runtime Config: Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html) — statement/lock/idle transaction timeouts.
- [Prepared Statements](https://www.postgresql.org/docs/current/sql-prepare.html) — generic/custom plans.
- [DDL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — PK/FK/UNIQUE/CHECK.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS và quyền.
- [Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html) — timestamp vs timestamptz.
- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html) — `json`/`jsonb`.

**Java và framework** (đọc đúng phiên bản triển khai):

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — managed entities, persistence context, flush, queries.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html) — identifiers, fetch plans, batching, versioning.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — proxy, propagation, rollback, transaction managers.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repositories, projections, modifying queries.
- [PostgreSQL JDBC Driver](https://jdbc.postgresql.org/documentation/) — JDBC connections, prepared statements, PostgreSQL types.
- Tài liệu connection pool như HikariCP tương ứng phiên bản và cấu hình thực tế.

Các đoạn Java trong bài là **mã minh họa ý tưởng**, không phải một project độc lập đã biên dịch. Các đoạn SQL là **lab lý thuyết**, chưa được chạy trên PostgreSQL thực tế trong giai đoạn soạn bài. Khi triển khai phải kiểm thử với đúng driver/provider/framework/PostgreSQL version và workload của ứng dụng.

## 63. Tổng kết

Hãy ghi nhớ các lớp:

```text
HTTP request
    |
    v
Spring service + @Transactional
    |
    +--> ORM persistence context
    |        |
    |        +--> entities/relations
    |        +--> dirty checking
    |        +--> flush
    |
    +--> JDBC/connection manager
    |        |
    |        +--> SQL / bind parameters
    |        +--> BEGIN/COMMIT/ROLLBACK
    |
    v
PostgreSQL
    |
    +--> MVCC/isolation
    +--> locks/concurrency
    +--> constraints/indexes
    +--> query planner/executor
    +--> WAL/commit
    |
    v
Durable result
```

Những nguyên tắc cốt lõi:

1. **ORM không loại bỏ SQL.** Đọc query thực tế và kế hoạch PostgreSQL khi cần tối ưu hoặc xác minh tính đúng.
2. **`save`, `flush` và `commit` khác nhau.** Có ID/đã phát INSERT không chứng minh transaction thành công.
3. **`@Transactional` có ranh giới phụ thuộc proxy và transaction manager.** Self-invocation hoặc thread khác có thể không nhận transaction mong đợi.
4. **Các propagation modes có semantics khác nhau.** REQUIRED dùng chung, REQUIRES_NEW độc lập, NESTED thường qua savepoints nếu hỗ trợ.
5. **READ COMMITTED không tự ngăn lost update.** Dùng `@Version`, atomic SQL hoặc locks/protocol phù hợp.
6. **Retry serialization/deadlock phải tạo transaction mới.** Không retry mù quáng mọi lỗi hoặc external side effects.
7. **Một HTTP request không đồng nghĩa một DB transaction.** Nhiều repository/services và external calls cần thiết kế boundary.
8. **Dùng unique constraints và idempotency keys** để đối phó retry/lỗi response sau commit.
9. **Outbox có thể bảo đảm order và event record commit cùng nhau**, nhưng external delivery vẫn cần retry/dedup.
10. **N+1, fetch join explosion, pagination và batching đều phải đo SQL thực tế.** Đừng giả định từ annotation.
11. **Quan sát hai phía:** app SQL/traces và PostgreSQL `pg_stat_activity`, `pg_locks`, `pg_stat_statements`, `EXPLAIN`.
12. **Thời gian chờ lock/pool có thể quan trọng hơn query plan.** Theo dõi transaction age, timeouts và connection usage.
13. **Schema/constraints là nguồn sự thật của database.** Quản lý migrations thay vì dựa vào entity annotations để tự sửa production.
14. **Bảo mật SQL vẫn cần GRANT/RLS/bind parameters.** ORM không thay phân quyền tenant hoặc làm native SQL an toàn nếu nối chuỗi.
15. **Kiểm thử PostgreSQL thật cho hành vi PostgreSQL-specific**, đặc biệt isolation, locking, `ON CONFLICT`, `RETURNING` và SQLSTATE.

### Một câu để nhớ

> **ORM giúp viết ứng dụng trên mô hình đối tượng; PostgreSQL vẫn quyết định dữ liệu có được ghi đúng, thấy đúng, khóa đúng và commit đúng hay không.** Ranh giới giao dịch phải được thiết kế có chủ đích, còn SQL thực tế phải được **quan sát và kiểm chứng**, không chỉ suy đoán từ Java annotations.

