# Kiểm thử định danh, khóa ghép và quan hệ có vòng đời phụ thuộc

Trong Hibernate/JPA, nhiều lỗi chỉ xuất hiện khi một entity được gắn với một định danh cụ thể, khi khóa chính gồm nhiều cột, hoặc khi vòng đời của entity con phụ thuộc vào entity cha. Một test chỉ gọi `persist()` rồi kiểm tra object trong bộ nhớ có thể bỏ sót các lỗi quan trọng: khóa được sinh sai thời điểm, hai object có `equals()` không nhất quán với primary key, foreign key ghép trỏ nhầm tenant, cascade không chạy như mong đợi, `orphanRemoval` xóa nhầm child, hoặc transaction rollback sau khi SQL đã được thực thi.

Để kiểm thử đúng, cần xác định **đơn vị định danh**, **nguồn tạo ID**, **quy tắc sở hữu quan hệ**, **điều kiện tồn tại của parent/child** và **ranh giới transaction**. Các test phải kiểm tra cả trạng thái object lẫn dữ liệu trong database sau flush/commit/rollback, tốt nhất bằng một persistence context mới và DBMS tương đương production.

Bài học tập trung vào các tình huống:

- ID được cấp bởi database, sequence hoặc ứng dụng.
- Khóa ghép bằng `@EmbeddedId` và `@IdClass`.
- Khóa dẫn xuất từ entity cha bằng `@MapsId`.
- Composite foreign keys và ràng buộc tenant.
- `CascadeType`, owning side, `orphanRemoval` và thứ tự ghi/xóa.
- Optimistic locking, concurrent updates và rollback.
- Cách tổ chức unit/integration tests với JUnit, Spring Data JPA và Testcontainers.

---

## 1. Bắt đầu từ mô hình dữ liệu và invariant

Giả sử một đơn hàng có nhiều dòng chi tiết. Mỗi dòng được nhận diện bởi mã đơn hàng và số thứ tự dòng:

```text
PurchaseOrder
  id
  orderNumber
  status
  version
     |
     +-- OrderLine
           orderId
           lineNumber
           sku
           quantity
```

Invariant của mô hình:

1. Mỗi đơn hàng có một `id` duy nhất.
2. Trong cùng một đơn hàng, `lineNumber` không trùng.
3. Một `OrderLine` luôn thuộc đúng một `PurchaseOrder`.
4. ID của `OrderLine` được tạo từ `orderId + lineNumber`.
5. Khi thêm child, cả hai phía của quan hệ Java phải được đồng bộ.
6. Khi xóa một child khỏi aggregate, child được xóa theo chính sách `orphanRemoval`.
7. Không thể tạo một child trỏ tới parent không tồn tại.
8. Một transaction thất bại không để lại parent/child đã commit một phần.

Các invariant này phải được kiểm chứng ở nhiều lớp:

| Lớp | Điều cần kiểm tra |
| --- | --- |
| Java/domain | Constructor, method thêm/xóa child, equality |
| ORM mapping | ID strategy, `@MapsId`, owning side, cascade |
| Database | PK, UNIQUE, FK, NOT NULL, CHECK |
| Transaction | Flush, commit, rollback, optimistic locking |
| API/service | Tenant scope, authorization, lỗi nghiệp vụ |
| Vận hành | Migrations, DBMS thật, concurrency |

Một test tốt xác nhận invariant ở lớp có thể thực thi nó. Ví dụ, Java validation có thể đưa ra lỗi sớm, nhưng chỉ database constraint mới bảo vệ được khi có hai transactions đồng thời hoặc một writer ngoài Hibernate.

## 2. Chọn ID strategy: generated, sequence hay assigned?

JPA cung cấp các chiến lược phổ biến:

```java
@GeneratedValue(strategy = GenerationType.IDENTITY)
@GeneratedValue(strategy = GenerationType.SEQUENCE)
@GeneratedValue(strategy = GenerationType.TABLE)
@GeneratedValue(strategy = GenerationType.AUTO)
```

Ứng dụng cũng có thể tự gán ID mà không dùng `@GeneratedValue`.

| Chiến lược | Nguồn ID | Điều cần test |
| --- | --- | --- |
| `IDENTITY` | Cột identity/auto-increment của DB | Thời điểm INSERT, generated key, batching |
| `SEQUENCE` | Database sequence | Cấp ID, allocation size, gaps, concurrency |
| `TABLE` | Bảng generator | Locking/throughput và generator row |
| `AUTO` | Provider chọn chiến lược | Chiến lược thực tế trên Hibernate/dialect |
| Assigned ID | Ứng dụng tạo ID | Duplicate, format, uniqueness, retry |

Không viết test phụ thuộc vào việc một chiến lược luôn phát SQL ở đúng một dòng Java. Thời điểm cấp ID và INSERT có thể khác giữa generator, Hibernate version và DBMS.

### 2.1. Test IDENTITY

Ví dụ:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {}

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

Test:

```java
@Test
void identityIdIsAvailableAfterFlush() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Customer customer = new Customer("An");
        em.persist(customer);
        em.flush();

        assertNotNull(customer.getId());

        Long id = customer.getId();
        tx.commit();

        EntityManager verify = emf.createEntityManager();
        try {
            assertEquals(
                "An",
                verify.find(Customer.class, id).getName()
            );
        } finally {
            verify.close();
        }
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

Điểm kiểm tra chính là ID tồn tại sau flush và row được đọc lại sau commit. Với IDENTITY, Hibernate thường cần INSERT sớm để lấy generated key, nhưng test không nên dùng thứ tự SQL log làm contract.

### 2.2. Test SEQUENCE

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customerSeq"
)
@SequenceGenerator(
    name = "customerSeq",
    sequenceName = "customer_seq",
    allocationSize = 50
)
private Long id;
```

Một test có thể kiểm tra:
- ID được gán sau khi persist theo behavior của generator/version.
- ID khác nhau giữa nhiều entities.
- Sau flush, rows có đúng IDs.
- Restart EntityManagerFactory không làm generator cấp lại ID đã dùng.
- Nhiều transactions đồng thời không nhận cùng ID.

Không assert ID phải liên tiếp `1, 2, 3`. Sequence/pooled allocation và rollback có thể tạo khoảng trống. **Uniqueness và tính hợp lệ quan trọng hơn tính liên tục.**

### 2.3. Test assigned ID

Nếu ứng dụng dùng UUID hoặc mã nghiệp vụ:

```java
@Entity
public class ExternalDocument {

    @Id
    private UUID id;

    protected ExternalDocument() {}

    public ExternalDocument(UUID id) {
        this.id = Objects.requireNonNull(id);
    }
}
```

Test:
- Constructor từ chối null nếu ID bắt buộc.
- Hai object dùng cùng ID bị database chặn.
- Retry cùng request ID không tạo duplicate business record.
- ID được tạo trước hay sau transaction theo contract của application.
- UUID/string normalization nhất quán giữa API, Java và DB.

## 3. ID được cấp không có nghĩa row đã commit

Với `SEQUENCE`, Hibernate có thể lấy ID trước khi INSERT. Với `IDENTITY`, INSERT thường được thực thi sớm để đọc generated key. Trong cả hai trường hợp, transaction vẫn có thể rollback.

```text
BEGIN
  allocate ID
  INSERT row
  flush succeeds
ROLLBACK
```

ID đã cấp có thể không được tái sử dụng. Test phải phân biệt:
- Object có ID.
- SQL đã chạy.
- Row còn trong transaction hiện tại.
- Row tồn tại sau commit trong một transaction mới.

Không viết test kiểu:

```java
em.persist(customer);
assertNotNull(customer.getId());
// Kết luận customer đã lưu bền vững.
```

Đó mới là assertion về identifier assignment. Muốn kiểm chứng persistence, phải flush, commit và đọc lại qua context/transaction khác.

## 4. Test primary key và unique constraint ở database

Giả sử `email` phải unique:

```sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_email UNIQUE (email);
```

Một service có thể kiểm tra email đã tồn tại trước khi persist, nhưng hai transactions có thể cùng vượt qua pre-check rồi cùng INSERT. Constraint database mới là lớp bảo vệ cuối.

Test nên có hai nhóm:

**Validation sớm**

```java
assertThrows(
    DuplicateEmailException.class,
    () -> customerService.register("an@example.org")
);
```

**Database integrity**

Tạo duplicate bằng hai persistence operations hoặc native SQL trong fixture, flush và xác nhận constraint violation theo DBMS/exception translation.

Sau khi flush lỗi, rollback transaction và đóng/discard persistence context. Đừng tiếp tục dùng một EntityManager đã gặp persistence exception như thể nó còn ở trạng thái bình thường.

## 5. Khóa ghép là gì?

Một khóa ghép (composite primary key) gồm nhiều cột. Ví dụ enrollment được nhận diện bằng:

```text
student_id + course_id
```

Không có một ID riêng cho enrollment; cặp hai ID xác định duy nhất một quan hệ đăng ký.

```sql
CREATE TABLE enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
```

Dùng khóa ghép khi các thành phần có ý nghĩa định danh tự nhiên và ổn định. Không chọn composite key chỉ để tiết kiệm một cột surrogate ID; nó ảnh hưởng tới foreign keys, joins, caches, equals/hashCode, repository APIs và index width.

## 6. Hai cách mapping composite ID: `@EmbeddedId` và `@IdClass`

| Tiêu chí | `@EmbeddedId` | `@IdClass` |
| --- | --- | --- |
| Khóa nằm ở đâu? | Trong một `@Embeddable` object | Các `@Id` nằm trực tiếp trên entity |
| Truy cập ID | `entity.getId().get...()` | `entity.get...()` |
| Mapping ID | Tập trung trong key class | Tên và kiểu phải khớp entity attributes |
| Phù hợp | Key là một value object | Muốn giữ các ID fields trực tiếp |
| Rủi ro | Key object mutable | Mapping trùng tên/kiểu dễ sai |

Cả hai đều cần equality semantics đúng. Đừng trộn hai kiểu mapping trên cùng một entity.

## 7. Mapping `@EmbeddedId`

Key class:

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class EnrollmentId implements Serializable {

    private Long studentId;
    private Long courseId;

    protected EnrollmentId() {}

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = Objects.requireNonNull(studentId);
        this.courseId = Objects.requireNonNull(courseId);
    }

    public Long getStudentId() { return studentId; }
    public Long getCourseId() { return courseId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EnrollmentId that)) return false;
        return Objects.equals(studentId, that.studentId)
            && Objects.equals(courseId, that.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

Entity:

```java
@Entity
@Table(name = "enrollments")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @Column(name = "enrolled_at", nullable = false)
    private Instant enrolledAt;

    protected Enrollment() {}

    public Enrollment(EnrollmentId id, Instant enrolledAt) {
        this.id = Objects.requireNonNull(id);
        this.enrolledAt = Objects.requireNonNull(enrolledAt);
    }

    public EnrollmentId getId() {
        return id;
    }
}
```

Test equality:

```java
@Test
void embeddedIdUsesBothKeyParts() {
    EnrollmentId first = new EnrollmentId(10L, 20L);
    EnrollmentId same = new EnrollmentId(10L, 20L);
    EnrollmentId otherCourse = new EnrollmentId(10L, 21L);

    assertEquals(first, same);
    assertEquals(first.hashCode(), same.hashCode());
    assertNotEquals(first, otherCourse);
}
```

Test này không cần database; nó kiểm tra contract của value object.

### 7.1. `equals()` và `hashCode()` phải dùng tất cả thành phần khóa

Lỗi:

```java
@Override
public boolean equals(Object other) {
    return other instanceof EnrollmentId that
        && Objects.equals(studentId, that.studentId);
}
```

sẽ coi enrollment của cùng student ở hai courses khác nhau là một ID. Một phần của composite key bị bỏ qua, dẫn tới:
- Set loại nhầm phần tử.
- Map ghi đè value.
- Cache/entity identity bị nhầm.
- Test pass sai nếu fixture không có cùng student ở nhiều course.

Hãy test từng thành phần độc lập và test cặp bằng nhau.

### 7.2. Key class nên immutable sau khi dùng

Thay đổi một field của ID sau khi entity đã managed hoặc đã được dùng làm key trong `HashMap`/`HashSet` làm equality/hashCode thay đổi. Điều này phá lookup và không phù hợp với primary key semantics.

Thiết kế ID class không cung cấp setter công khai nếu không cần. Nếu ORM cần constructor no-arg hoặc field access, giữ constructor theo yêu cầu persistence nhưng tránh mutating API trong domain.

## 8. Mapping `@IdClass`

Ví dụ enrollment:

```java
public class EnrollmentKey implements Serializable {

    private Long studentId;
    private Long courseId;

    public EnrollmentKey() {}

    public EnrollmentKey(Long studentId, Long courseId) {
        this.studentId = studentId;
        this.courseId = courseId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EnrollmentKey that)) return false;
        return Objects.equals(studentId, that.studentId)
            && Objects.equals(courseId, that.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

```java
@Entity
@IdClass(EnrollmentKey.class)
@Table(name = "enrollments")
public class Enrollment {

    @Id
    @Column(name = "student_id")
    private Long studentId;

    @Id
    @Column(name = "course_id")
    private Long courseId;

    @Column(name = "enrolled_at", nullable = false)
    private Instant enrolledAt;

    protected Enrollment() {}
}
```

Trong `@IdClass`, tên và kiểu các ID attributes trong key class phải tương ứng với các persistent ID attributes của entity theo Jakarta Persistence rules. Đừng viết key class với `student` nếu entity field tên `studentId`, hoặc dùng `Student` trong key class khi entity ID attribute thực tế là `Long studentId`.

### 8.1. Những lỗi mapping cần bắt ngay khi bootstrap

- Key class thiếu constructor no-arg theo yêu cầu provider/spec.
- Thiếu `equals()`/`hashCode()`.
- Field name/type không khớp entity.
- Một thành phần `@Id` bị thiếu `@Column` mapping.
- DB PK order/column names không khớp migration.
- Entity dùng `@EmbeddedId` đồng thời khai báo các `@Id` riêng không hợp lệ.
- Composite key có null component khi persist.
- Key field bị thay đổi sau khi entity đã persistent.

Một integration test khởi động EntityManagerFactory và persist/read một row thật sẽ bắt nhiều lỗi mapping sớm hơn chỉ unit test key class.

## 9. Test composite key trong repository

Spring Data JPA repository dùng kiểu ID của entity:

```java
public interface EnrollmentRepository
        extends JpaRepository<Enrollment, EnrollmentId> {
}
```

Test:

```java
EnrollmentId id = new EnrollmentId(10L, 20L);

Enrollment enrollment = new Enrollment(
    id,
    Instant.parse("2026-01-10T10:00:00Z")
);

repository.saveAndFlush(enrollment);

Enrollment loaded = repository.findById(id).orElseThrow();

assertEquals(id, loaded.getId());
```

Với `@IdClass`, repository ID type là `EnrollmentKey`; cách truy cập key từ entity có thể khác vì các thành phần ID nằm trực tiếp trên entity.

Test thêm:
- `findById()` với cả hai components đúng.
- Cùng student, course khác.
- Student khác, cùng course.
- Xóa theo composite key.
- Duplicate cùng cặp bị database chặn.
- Một component null bị từ chối theo mapping/constraint.

## 10. Kiểm thử khóa ghép không chỉ bằng equality

Một key class có `equals()` đúng nhưng database migration lại khai báo PK sai vẫn có thể gây lỗi production.

Đối chiếu ba lớp:

```text
Java EnrollmentId(studentId, courseId)
            |
            v
Hibernate @EmbeddedId / @IdClass
            |
            v
Database PRIMARY KEY(student_id, course_id)
```

Test tích hợp phải chứng minh:
1. Hai thành phần được ghi đúng columns.
2. Đọc lại tạo key object có giá trị đúng.
3. Composite PK ngăn duplicate pair.
4. Foreign keys tham chiếu đúng thứ tự/cặp columns.
5. Query bằng key không nhầm tenant hoặc entity khác.

Dùng `ddl-auto=validate` với schema do Flyway/Liquibase quản lý để phát hiện một số khác biệt mapping/schema, nhưng vẫn cần test constraints bằng dữ liệu thực.

## 11. Composite foreign key và tenant boundary

Một bảng Customer có khóa:

```text
(tenant_id, customer_no)
```

Order phải tham chiếu đúng cặp này. DDL:

```sql
CREATE TABLE customers (
    tenant_id BIGINT NOT NULL,
    customer_no BIGINT NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (tenant_id, customer_no)
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_no BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (tenant_id, customer_no)
        REFERENCES customers(tenant_id, customer_no)
);
```

Composite FK ngăn order tenant A tham chiếu customer tenant B chỉ bằng cách trùng `customer_no`.

### 11.1. Mapping `@JoinColumns`

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumns({
    @JoinColumn(
        name = "tenant_id",
        referencedColumnName = "tenant_id"
    ),
    @JoinColumn(
        name = "customer_no",
        referencedColumnName = "customer_no"
    )
})
private Customer customer;
```

Đây là mẫu mapping khi các columns của association thuộc owning side và không bị map trùng với basic attributes khác. Nếu `tenantId` cũng là một persistent property riêng trên `PurchaseOrder`, cần thiết kế duplicate column mapping bằng `insertable=false, updatable=false` ở một trong các mappings, hoặc chọn một mô hình sở hữu cột rõ ràng. Không để hai properties cùng ghi một column.

### 11.2. Test tenant isolation ở database

Test phải tạo:
- Tenant 1, Customer#7.
- Tenant 2, Customer#7.
- Order của tenant 1 tham chiếu Customer#7 tenant 1.
- Thử insert order tenant 1 tham chiếu cặp `(tenant 2, 7)`.

Database composite FK phải từ chối cặp sai. Test chỉ kiểm tra service `if (customer.tenantId != order.tenantId)` chưa chứng minh DB bảo vệ được raw SQL hoặc concurrent writes.

## 12. Derived identity: khóa của child phụ thuộc parent

Một `OrderLine` có khóa ghép `(order_id, line_number)`. `order_id` lấy từ ID của PurchaseOrder; `line_number` do ứng dụng cấp trong đơn hàng.

Đây là **derived identity**: một phần hoặc toàn bộ identity của dependent entity được dẫn xuất từ parent.

JPA hỗ trợ mô hình này qua `@MapsId`.

Key:

```java
@Embeddable
public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {}

    public OrderLineId(Integer lineNumber) {
        this.lineNumber = Objects.requireNonNull(lineNumber);
    }

    public Long getOrderId() { return orderId; }
    public Integer getLineNumber() { return lineNumber; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

Entity child:

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(
            Integer lineNumber,
            String sku,
            int quantity
    ) {
        this.id = new OrderLineId(lineNumber);
        this.sku = Objects.requireNonNull(sku);
        this.quantity = quantity;
    }

    void attachTo(PurchaseOrder order) {
        this.order = Objects.requireNonNull(order);
    }

    public OrderLineId getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
}
```

Parent:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(OrderLine line) {
        line.attachTo(this);
        lines.add(line);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            // orphanRemoval sẽ xử lý child khi flush
        }
    }

    public Long getId() { return id; }
    public List<OrderLine> getLines() { return lines; }
}
```

Đoạn code tập trung vào quan hệ derived identity; entity thực tế cần các fields, constructors và imports khác theo schema. `order_id` được ánh xạ bởi `@MapsId("orderId")`, còn `lineNumber` là phần ID được gán từ ứng dụng.

### 12.1. Tại sao dùng `@MapsId`?

Nó nói với persistence provider rằng association `order` cung cấp giá trị cho thành phần `orderId` của embedded ID. Nhờ vậy mapping tránh phải tự quản lý hai nguồn giá trị cho cùng một FK/ID column.

Không map `order_id` vừa như một scalar writable property vừa như association writable mà không có chiến lược rõ; nếu trùng column mapping, phải chỉ định ownership/insertable/updatable đúng.

## 13. Test `@MapsId` khi parent dùng generated ID

Đây là test trọng tâm của derived identity:

```java
@Test
void childKeyUsesGeneratedParentId() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        PurchaseOrder order = new PurchaseOrder();
        order.addLine(new OrderLine(1, "SKU-A", 2));
        order.addLine(new OrderLine(2, "SKU-B", 1));

        em.persist(order);
        em.flush();

        assertNotNull(order.getId());

        for (OrderLine line : order.getLines()) {
            assertEquals(order.getId(), line.getId().getOrderId());
        }

        Long orderId = order.getId();
        tx.commit();

        EntityManager verify = emf.createEntityManager();
        try {
            PurchaseOrder loaded =
                verify.find(PurchaseOrder.class, orderId);

            assertEquals(2, loaded.getLines().size());
            assertEquals(
                orderId,
                loaded.getLines().get(0).getId().getOrderId()
            );
        } finally {
            verify.close();
        }
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

Test này xác nhận:
- Parent được persist.
- Generated parent ID được áp vào child key.
- Composite key của child có đúng parent ID.
- FK/PK thực sự được lưu.
- Persistence context mới dựng lại quan hệ.

Với derived identity, đừng chỉ assert `line.getOrder() == order` trước flush; đó mới là reference trong bộ nhớ, chưa chứng minh khóa dẫn xuất đã ghi đúng.

### 13.1. Không đưa key mutable vào HashSet trước khi ID hoàn chỉnh

Trong ví dụ, `orderId` có thể chưa có trước khi parent được persist. Nếu `OrderLineId.hashCode()` thay đổi sau khi `@MapsId` điền parent ID, một `OrderLine` đã được đặt vào `HashSet` theo hash cũ có thể không còn tìm thấy được.

Các cách giảm rủi ro:
- Dùng `List` cho children khi phù hợp.
- Không thay đổi key sau khi object đã làm key của hash-based collection.
- Cân nhắc assigned parent ID nếu domain cho phép.
- Thiết kế equality cho entity có generated/derived IDs theo lifecycle rõ ràng.

Không sửa `equals()` tùy tiện để bỏ qua một phần primary key; điều đó tạo identity semantics sai.

## 14. `@MapsId` với parent có composite ID

Nếu parent có `@EmbeddedId`:

```java
@Embeddable
public class TenantCustomerId implements Serializable {
    private Long tenantId;
    private Long customerNo;
    // constructor, getters, equals, hashCode
}
```

và child ID chứa cả hai phần:

```java
@Embeddable
public class CustomerDocumentId implements Serializable {
    private Long tenantId;
    private Long customerNo;
    private Long documentNo;
    // constructor, getters, equals, hashCode
}
```

Mapping có thể dùng:

```java
@EmbeddedId
private CustomerDocumentId id;

@MapsId("customerId")
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumns({
    @JoinColumn(name = "tenant_id", referencedColumnName = "tenant_id"),
    @JoinColumn(name = "customer_no", referencedColumnName = "customer_no")
})
private Customer customer;
```

Trong ví dụ này, `CustomerDocumentId` cần một embedded attribute tên `customerId` có kiểu `TenantCustomerId`; chuỗi `"customerId"` trong `@MapsId` phải trỏ đúng attribute đó. Các nested embedded mappings cần cấu hình `@AttributeOverrides`/column names phù hợp.

Điều quan trọng là:
- `@MapsId` value là **tên attribute trong embedded ID**, không phải tên database column.
- Join columns phải khớp thứ tự và tên referenced columns.
- Composite PK/FK trong migrations phải tương ứng mapping.
- Test hai tenants có cùng `customerNo` để phát hiện association nhầm.

## 15. Derived identity không phải lúc nào cũng cần composite PK

Nếu child có surrogate ID:

```text
order_lines
  id (PK)
  order_id (FK)
  line_number
  UNIQUE(order_id, line_number)
```

thì có thể giữ `id` đơn giản và thêm unique constraint cho `(order_id, line_number)`.

Ưu điểm:
- Entity ID không phụ thuộc parent ID.
- Reparenting (nếu nghiệp vụ cho phép) đơn giản hơn.
- Foreign keys từ bảng khác ngắn hơn.
- Entity equality có thể dễ quản lý hơn khi ID immutable.

Đánh đổi:
- Có thêm surrogate key.
- Vẫn phải bảo vệ uniqueness của line number trong order.

Chọn derived composite identity khi chính cặp `(parent, local number)` là identity nghiệp vụ ổn định; chọn surrogate ID khi child cần identity độc lập. Test nên phản ánh domain decision, không chỉ một cách mapping ORM.

## 16. Owning side quyết định FK được ghi

Mapping hai chiều:

```java
// Parent
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

// Child
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

`OrderLine.order` là owning side vì nó ánh xạ FK `order_id`. `PurchaseOrder.lines` là inverse side.

Method domain phải cập nhật owning side:

```java
public void addLine(OrderLine line) {
    line.attachTo(this);
    lines.add(line);
}
```

Test phải xác nhận cả hai:
- Parent collection có child.
- Child FK trỏ đúng parent sau flush/reload.

Nếu chỉ thêm vào inverse collection, object graph có thể trông đúng trong memory nhưng FK không được ghi như mong muốn.

## 17. Cascade PERSIST và thứ tự lưu parent/child

`CascadeType.PERSIST` lan truyền thao tác persist từ parent sang child:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Test:
1. Tạo parent transient.
2. Tạo child transient.
3. Gọi `parent.addLine(child)`.
4. Chỉ gọi `em.persist(parent)`.
5. Flush.
6. Xác nhận cả parent và child rows tồn tại sau commit.

Nếu không có cascade PERSIST, child transient chưa được persist có thể gây lỗi khi flush do unsaved transient association, tùy mapping/provider. Test nên xác nhận behavior dự kiến thay vì thêm `CascadeType.ALL` để che lỗi.

### 17.1. Cascade không phải foreign key

Cascade JPA/Hibernate điều khiển ORM lifecycle. Foreign key database bảo vệ tính toàn vẹn dữ liệu ở DB.

- ORM cascade có thể persist child khi parent được persist.
- DB FK không tự tạo child.
- DB `ON DELETE CASCADE` là hành vi database khác với `CascadeType.REMOVE`.
- Native SQL không tự kích hoạt JPA cascade.

Cần kiểm tra cả mapping và DDL.

## 18. Phân biệt PERSIST, MERGE, REMOVE và ALL

| Cascade | Ý nghĩa khi thao tác parent | Test cần có |
| --- | --- | --- |
| `PERSIST` | Persist transient children | Parent + child mới |
| `MERGE` | Merge state sang associated entities theo cascade | Detached graph |
| `REMOVE` | Remove children theo cascade khi remove parent | Delete parent |
| `REFRESH` | Refresh children khi refresh parent | DB state thay đổi ngoài context |
| `DETACH` | Detach children cùng parent | Persistence context lifecycle |
| `ALL` | Bao gồm các cascade types trên | Phải hiểu toàn bộ tác động |

Không dùng `CascadeType.ALL` mặc định cho mọi association. Với shared reference như `Product`, `Customer` hoặc `Category`, cascade REMOVE có thể xóa một entity được nhiều aggregates dùng chung.

Test nên mô phỏng parent/child/reference ownership thật để bắt việc cascade quá rộng.

## 19. `orphanRemoval=true`: child bị loại khỏi aggregate

Mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Khi child bị loại khỏi quan hệ private ownership, provider sẽ lên lịch xóa child theo orphan-removal semantics tại flush.

```java
order.removeLine(line);
em.flush();
```

Test phải:
1. Tạo parent và hai lines, commit.
2. Mở EntityManager mới.
3. Remove một line bằng domain method.
4. Flush/commit.
5. Mở context khác và kiểm tra line bị xóa.
6. Kiểm tra line còn lại vẫn thuộc parent.

### 19.1. Orphan removal không phải soft delete

`orphanRemoval=true` có semantics remove entity. Nếu child entity dùng Hibernate `@SoftDelete`, kết quả SQL có thể là soft delete theo mapping của child. Nếu không, thường là DELETE vật lý. Test trên đúng Hibernate mapping/DB schema.

Đừng dùng từ “orphan” để suy ra child bị đánh dấu inactive; phải xác định delete strategy của child.

### 19.2. Không tái sử dụng orphan đã bị remove

JPA orphan removal dành cho child có quan hệ sở hữu riêng. Đừng xóa child khỏi parent A rồi chuyển ngay sang parent B trong cùng unit of work và kỳ vọng provider portable sẽ xử lý như reparenting bình thường. Nếu domain cho phép chuyển, hãy mô hình hóa explicit move với mapping/cascade phù hợp, không dùng orphanRemoval như một cách chuyển ownership.

## 20. Test xóa parent và cascade REMOVE

Với:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines;
```

Test:
- Persist parent và child.
- Commit.
- Remove parent.
- Flush/commit.
- Kiểm tra parent và children theo đúng cascade.
- Kiểm tra các references dùng chung không bị xóa ngoài ý muốn.

Nếu parent/child có composite FK, SQL delete order phải tôn trọng constraints và thứ tự. ORM có thể phát child deletes trước parent delete; database cascade có thể thay đổi SQL shape. Không assert một thứ tự SQL cứng nếu không phải contract của hệ thống; assert committed state và constraints.

## 21. DB cascade và ORM cascade là hai đường khác nhau

DDL:

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

có thể xóa children khi parent bị DELETE trực tiếp ở database.

`CascadeType.REMOVE` làm Hibernate phát remove operations cho associated entities theo ORM mapping.

Khác biệt quan trọng:
- Native SQL DELETE có thể kích hoạt DB cascade nhưng không gọi entity callbacks cho từng child.
- Hibernate cascade có thể tải/đánh dấu children và phát các lifecycle events.
- Soft delete parent bằng UPDATE flag không kích hoạt `ON DELETE CASCADE`.
- DB cascade không đồng nghĩa Envers nhận đủ child lifecycle events.

Test từng đường đi nếu hệ thống hỗ trợ cả ORM và direct SQL writers.

## 22. Kiểm thử NOT NULL và FK khi child phụ thuộc parent

Schema:

```sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    PRIMARY KEY (order_id, line_number),
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Các trường hợp test:
- Persist child không có parent.
- Persist child với parent transient nhưng không cascade PERSIST.
- Persist child với parent ID không tồn tại qua native SQL.
- Đặt `order_id = null`.
- Xóa parent khi child còn tồn tại và không có cascade.
- Thay đổi FK sang parent khác theo quy tắc domain.

Đừng chỉ assert Java exception ở constructor. Flush/DB constraint test xác nhận database bảo vệ invariant ngay cả khi data đi qua một đường khác.

## 23. Thứ tự SQL không phải thứ tự gọi method

Ví dụ:

```java
em.persist(parent);
em.persist(child);
em.flush();
```

Hibernate quản lý ActionQueue và dependency ordering. Thứ tự SQL cuối có thể không đúng thứ tự dòng Java, đặc biệt khi có cascade, generated identifiers, secondary tables và FK dependencies.

Test không nên mặc định:
- Parent INSERT luôn là câu SQL đầu tiên trong mọi mapping.
- Child DELETE luôn xuất hiện đúng sau một method call.
- Một lần `persist()` tương ứng một INSERT ngay lập tức.

Nếu cần bảo đảm một dependency, hãy khai báo mapping/cascade/FK đúng và test kết quả sau flush/commit. Chỉ assert SQL order khi hệ thống có một contract thực sự phụ thuộc vào nó.

## 24. Flush để phát hiện lỗi constraint tại đúng ranh giới

Một test:

```java
tx.begin();
em.persist(parent);
em.persist(child);
em.flush();
```

Flush giúp phát SQL và phát hiện nhiều lỗi mapping/constraint trước khi test tiếp tục. Nhưng:
- Deferred constraints có thể chỉ lỗi tại commit.
- Transaction vẫn có thể rollback sau flush.
- Sau persistence exception, rollback và bỏ EntityManager.
- Không assert “flush pass = commit pass”.

Với DB constraints không deferred, flush thường là điểm tốt để xác nhận lỗi uniqueness/FK xuất hiện. Test commit riêng nếu semantics cần được xác minh.

## 25. Composite key và child equality trong collection

Nếu `OrderLine` dùng `@EmbeddedId`, `equals()`/`hashCode()` trên entity cần thận trọng vì:
- ID có thể chưa đầy đủ trước persist khi dùng `@MapsId`.
- Proxy subclass có thể ảnh hưởng `getClass()` comparison.
- Lazy association không nên bị truy cập trong equality.
- Hash code dựa vào ID mutable có thể thay đổi trong lifecycle.

Một lựa chọn là dùng `List` và quản lý child bằng domain identity (`lineNumber`) trong parent, thay vì đưa entity generated/derived ID vào `HashSet` trước khi key hoàn chỉnh.

Nếu dùng `Set`, hãy định nghĩa equality có chủ đích và test:
- Hai transient children.
- Hai managed children cùng ID.
- Entity proxy và entity đã load.
- Hash lookup trước/sau persist.
- Detached/merged instances.

Không sao chép một `equals()` implementation chung cho mọi entity; entity identity có semantics khác value object ID.

## 26. Test composite key trùng và transaction rollback

Ví dụ test duplicate pair:

```java
@Test
void duplicateEnrollmentKeyIsRejectedByDatabase() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        em.persist(new Enrollment(
            new EnrollmentId(10L, 20L), Instant.now()
        ));
        em.flush();

        em.persist(new Enrollment(
            new EnrollmentId(10L, 20L), Instant.now()
        ));

        assertThrows(RuntimeException.class, em::flush);
        tx.rollback();
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }
}
```

Trong test production-quality, bắt exception cụ thể theo Hibernate/Spring/DBMS, và tách duplicate insertion thành test riêng. Sau lỗi flush, không tiếp tục thao tác trên cùng persistence context; rollback và đóng nó.

Có thể kiểm tra duplicate bằng native SQL trong transaction riêng để xác nhận constraint DB, nhưng phải tránh phụ thuộc thứ tự ID generator.

## 27. `@MapsId` và thay đổi parent

Với child ID chứa `orderId`, việc đổi `OrderLine.order` từ Order A sang Order B cũng có nghĩa **thay đổi primary key**.

Primary key của entity persistent không được thay đổi như một field thông thường. Nếu domain yêu cầu chuyển line sang order khác:
- Có thể xóa child cũ và tạo child mới dưới parent mới.
- Hoặc dùng surrogate child ID và chỉ cập nhật FK nếu reparenting được cho phép.
- Có thể dùng một model assignment/version mới thay vì mutate identity.

Test cần khẳng định hành vi khi cố đổi parent:
- Application từ chối.
- Hoặc workflow tạo entity mới/xóa entity cũ.
- Không để một entity managed có primary key thay đổi giữa transaction.

## 28. Test vòng đời child độc lập và child phụ thuộc

Không phải mọi quan hệ `@OneToMany` đều có ownership như nhau.

| Child type | Có thể tồn tại độc lập? | Parent remove | `orphanRemoval` |
| --- | --- | --- | --- |
| OrderLine thuộc riêng Order | Thường không | Thường remove cùng parent | Thường phù hợp |
| Comment dùng chung cho nhiều contexts | Có thể | Không nên xóa tùy tiện | Thường không |
| Product reference | Có | Không xóa Product khi Order xóa | Không |
| Membership entity (UserRole) | Bản thân membership là quan hệ | Có thể xóa membership | Có thể phù hợp |
| Attachment record | Tùy retention/file policy | Cần workflow riêng | Không mặc định |

Test phải mô phỏng các use cases thực tế, đặc biệt shared references và child có retention độc lập.

## 29. Optimistic locking trên parent và child

Entity có:

```java
@Version
private long version;
```

Hibernate sử dụng version để phát hiện concurrent updates cho entity đó. Nếu parent và child đều có `@Version`, mỗi entity có version riêng.

Ví dụ:
- T1 load Order version 4.
- T2 load Order version 4.
- T1 update và commit version 5.
- T2 update với version 4.
- T2 gặp optimistic locking failure khi flush/commit.

### 29.1. Collection change có luôn tăng parent version không?

Không nên mặc định mọi thay đổi collection đều tăng version của parent theo cùng cách ở mọi mapping/provider. Version behavior phụ thuộc collection ownership, dirty state và mapping semantics. Nếu domain cần parent aggregate version thay đổi khi child thay đổi, hãy xác định rõ cách mapping/aggregate update và kiểm thử.

Một lựa chọn là chủ động cập nhật một aggregate version/state field ở parent trong domain method, hoặc dùng locking strategy phù hợp. Không dựa vào một test đơn lẻ để suy mọi child mutations đều bump parent version.

## 30. Test concurrent updates bằng hai EntityManagers

Pseudo-flow:

```text
T1: load Order#100, version=4
T2: load Order#100, version=4
T1: change status, flush, commit -> version=5
T2: change status, flush/commit -> optimistic lock failure
```

Trong test:
- Dùng hai EntityManagers/connections riêng.
- Không dùng cùng một persistence context cho cả hai transactions.
- Đồng bộ thời điểm đọc trước khi update bằng latches/barriers nếu chạy threads.
- Xác nhận một transaction thành công và transaction còn lại thất bại.
- Mở context mới để đọc committed state cuối.

Không chỉ assert exception class; kiểm tra row/version cuối để chứng minh không có lost update.

## 31. Cascade và rollback phải được test cùng nhau

Ví dụ:
1. Tạo parent và hai children.
2. Persist parent với cascade PERSIST.
3. Flush để SQL được thực thi.
4. Ném exception và rollback.
5. Mở EntityManager mới.
6. Xác nhận parent và cả hai children đều không tồn tại.

Nếu chỉ kiểm tra rollback trước flush, test chưa chứng minh database có thể undo các SQL đã thực thi.

Nếu có `REQUIRES_NEW` hoặc child service dùng transaction riêng, kết quả có thể khác. Test cần kiểm tra đúng propagation contract.

## 32. Transactional test trong Spring thường tự rollback

`@DataJpaTest` và test transaction của Spring thường chạy mỗi test trong transaction được rollback sau test theo mặc định.

Ví dụ:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    TestEntityManager entityManager;

    @Test
    void savesOrder() {
        PurchaseOrder order = new PurchaseOrder();
        entityManager.persistAndFlush(order);

        assertNotNull(order.getId());
    }
}
```

Test này hữu ích cho mapping và flush, nhưng không chứng minh commit đã xảy ra.

Nếu cần kiểm tra commit:
- Dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` khi phù hợp.
- Hoặc chạy test không nằm trong test-managed transaction và dùng `TransactionTemplate`.
- Mở transaction/persistence context mới để verify.
- Đảm bảo dữ liệu test được dọn sạch.

Không tắt rollback toàn bộ test suite chỉ để một test quan sát commit.

## 33. `TestEntityManager` và `EntityManager` mới

Spring Boot `TestEntityManager` hỗ trợ `persist`, `flush`, `clear`, `find`, `remove` tiện cho `@DataJpaTest`.

Ví dụ:

```java
entityManager.persist(order);
entityManager.flush();
entityManager.clear();

PurchaseOrder loaded =
    entityManager.find(PurchaseOrder.class, order.getId());
```

`clear()` làm detached các entities trong cùng Persistence Context, giúp lần find không chỉ trả cùng object đang managed.

Nhưng `clear()` **không commit transaction** và không tạo một physical connection mới. Nếu cần kiểm tra transaction visibility hoặc commit/rollback, phải mở context/transaction khác.

## 34. Kiểm thử database constraint thay vì chỉ mock repository

Một unit test:

```java
when(repository.save(any())).thenReturn(order);
```

không thể xác nhận:
- Composite primary key thật.
- FK thật.
- Unique constraints.
- Generated key timing.
- SQL ordering.
- Cascade/orphan removal.
- Deferred constraints.
- DB dialect behavior.

Mock repository hữu ích cho service orchestration, nhưng mapping và relational invariants cần integration tests với DB.

Một test repository có giá trị phải chạy Hibernate thật, schema thật và transaction thật.

## 35. Testcontainers với PostgreSQL

Nếu production sử dụng PostgreSQL, một cấu hình Testcontainers:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class CompositeIdentityIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
        registry.add("spring.flyway.enabled", () -> "true");
    }
}
```

Đây là test skeleton; cần imports, dependencies JUnit 5/Testcontainers/Spring Boot, migration files và entity mappings của dự án.

Testcontainers giúp xác nhận:
- Composite PK/FK trên đúng DBMS.
- Sequence/identity behavior.
- Unique violations và SQLSTATE.
- `ON DELETE` semantics.
- Transaction isolation và locking.
- Migrations tương thích Hibernate `ddl-auto=validate`.

Không dùng H2 để kết luận PostgreSQL composite index, sequence pooling, deferred constraints hay locking giống nhau.

## 36. Migration là một phần của test định danh

Một entity mapping đúng nhưng migration tạo sai PK vẫn là lỗi production.

CI nên:
1. Khởi động DB trống.
2. Chạy Flyway/Liquibase migrations từ đầu.
3. Bootstrap EntityManagerFactory với `ddl-auto=validate`.
4. Persist/read entity với ID đơn.
5. Persist/read entity với composite ID.
6. Kiểm tra FK/unique constraints.
7. Chạy tests cascade/orphanRemoval.
8. Chạy tests rollback/concurrency.
9. Có thể nâng từ schema version cũ để kiểm tra migration path.

Không để Hibernate `create`/`update` tự tạo schema trong test rồi kết luận migration production đúng; test phải dùng đúng migration scripts được deploy.

## 37. Property-based tests cho composite keys

Composite ID thường có nhiều trường hợp equality hơn một ví dụ cố định.

Có thể sinh các cặp `(studentId, courseId)` ngẫu nhiên và xác nhận:

- Hai key có cùng components thì equal.
- Đổi một component thì không equal.
- `equals()` có tính phản xạ, đối xứng, bắc cầu.
- Nếu equal thì hashCode bằng nhau.
- HashMap lookup bằng instance tương đương hoạt động.
- Serialization/deserialization (nếu ứng dụng dùng) giữ equality.

Ví dụ pseudo-code với property-based testing library:

```java
@Property
void equalKeysHaveEqualHashCode(
        @ForAll long studentId,
        @ForAll long courseId
) {
    EnrollmentId a =
        new EnrollmentId(studentId, courseId);
    EnrollmentId b =
        new EnrollmentId(studentId, courseId);

    assertEquals(a, b);
    assertEquals(a.hashCode(), b.hashCode());
}
```

Tên annotations và dependency tùy thư viện được chọn. Property-based test bổ sung cho integration test; nó không thay database constraint test.

## 38. Kiểm thử thứ tự lifecycle và callbacks

Có thể dùng một test observer hoặc JPA lifecycle listener để ghi lại:
- `@PrePersist`
- `@PostPersist`
- `@PreRemove`
- `@PostRemove`
- Flush/commit boundaries ở service/test harness.

Nhưng không nên đóng đinh thứ tự callback nội bộ của Hibernate ngoài contract Jakarta Persistence hoặc version-specific behavior mà ứng dụng thật sự phụ thuộc.

Các câu hỏi cần kiểm tra:
- Cascade PERSIST có tạo child trước/sau parent SQL?
- Generated ID đã có lúc callback nào?
- `@PreRemove` có chạy cho child khi ORM cascade REMOVE?
- DB `ON DELETE CASCADE` có gọi callback child không? Không, vì DB không gọi Java lifecycle.
- Rollback có hoàn tác side effects ngoài DB của callback không? Không.

Nếu listener ghi metrics/email, test rollback phải xác nhận side effects không bị nhầm với committed state.

## 39. Composite foreign key và chống cross-tenant references

Một integration test nên:
1. Tạo Customer `(tenant=1, customerNo=7)`.
2. Tạo Customer `(tenant=2, customerNo=7)`.
3. Tạo Order tenant 1 tham chiếu đúng cặp `(1,7)`.
4. Thử tạo Order tenant 1 tham chiếu `(2,7)`.
5. Flush.
6. Xác nhận DB từ chối FK hoặc service từ chối trước và DB vẫn bảo vệ raw SQL path.

Nếu chỉ có FK `customer_no` mà không bao gồm `tenant_id`, DB có thể cho phép liên kết chéo tenant khi customer numbers trùng. Test fixture với IDs trùng giữa tenants là cách tốt để phát hiện thiếu thành phần composite FK.

## 40. Lifecycle phụ thuộc khi parent bị xóa

Cần xác định một trong các semantics:
- Child bị xóa cùng parent.
- Child bị soft-delete cùng parent.
- Child được giữ nhưng không còn truy cập qua parent.
- Parent không thể xóa khi còn child.
- Child được chuyển sang owner khác trước khi parent bị xóa.

Test phải chứng minh chính sách đã chọn. Ví dụ với `orphanRemoval=true`, remove parent và kiểm tra child rows sau commit. Với DB `ON DELETE RESTRICT`, thử xóa parent bằng native SQL khi child tồn tại và xác nhận DB chặn.

Không giả định `CascadeType.REMOVE` và `ON DELETE CASCADE` có cùng behavior cho Envers, callbacks hoặc native SQL.

## 41. Test reparenting và giới hạn identity

Nếu child có surrogate ID và domain cho phép chuyển parent:
- Load child.
- Thay owning-side reference.
- Flush/commit.
- Kiểm tra FK mới.
- Kiểm tra collection cũ và mới sau reload.
- Kiểm tra optimistic locking.

Nếu child dùng derived ID `@MapsId`, parent ID là một phần PK. Reparenting đồng nghĩa đổi identity, thường nên được mô hình hóa thành delete/create hoặc bị cấm.

Test cần assert business rule, không chỉ assert SQL UPDATE chạy.

## 42. Kiểm thử thứ tự thao tác trong aggregate

Domain methods nên giữ hai phía của association nhất quán:

```java
public void addLine(OrderLine line) {
    Objects.requireNonNull(line);

    if (line.getOrder() != null && line.getOrder() != this) {
        throw new IllegalStateException(
            "Line already belongs to another order"
        );
    }

    line.attachTo(this);
    lines.add(line);
}
```

```java
public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.detachFrom(this);
    }
}
```

Unit tests không cần DB để kiểm tra:
- Add cùng child hai lần có duplicate không?
- Remove child không thuộc aggregate có làm gì không?
- Reparent có được cho phép không?
- Child đã bị remove có thể add lại không?
- Line number có unique trong parent không?

Integration tests sau đó xác nhận mapping persist đúng những invariant đã kiểm tra trong domain.

## 43. Kiểm thử duplicate line number dưới concurrency

Một check Java:

```java
if (lines.stream().anyMatch(
        line -> line.getLineNumber() == nextNumber
)) {
    throw new DuplicateLineNumberException();
}
```

không đủ khi hai transactions đồng thời thêm cùng `lineNumber`.

Database cần:

```sql
PRIMARY KEY (order_id, line_number)
```

hoặc:

```sql
UNIQUE (order_id, line_number)
```

Concurrency test:
1. T1 và T2 cùng đọc parent state.
2. Cả hai cùng thêm line number 3.
3. Cả hai flush/commit.
4. Một transaction thành công, transaction còn lại gặp constraint/optimistic conflict.
5. DB chỉ có một line number 3.

Dùng hai EntityManagers và synchronization barrier để tạo race có chủ đích. Không dùng một transaction test duy nhất rồi kết luận concurrency được bảo vệ.

## 44. Test delete/restore và lifecycle state

Nếu child/parent có soft-delete hoặc status:
- Xóa mềm parent có làm child ẩn theo policy không?
- Restore parent có phục hồi child bị xóa độc lập không?
- Unique keys có conflict khi restore không?
- Child FK có giữ nguyên?
- Envers có audit state theo Hibernate lifecycle không?
- Native bulk updates có bypass callbacks không?

Đây là test matrix khác với physical delete. Đừng kết luận `orphanRemoval` sẽ đặt soft-delete marker trừ khi child mapping hỗ trợ và integration test xác nhận.

## 45. Kiểm thử query theo composite ID và association

Các query cần test:
- `findById(embeddedId)`.
- Derived query theo một thành phần.
- Join qua composite FK.
- Pagination/count khi composite key.
- Tenant scope.
- Delete/exists.
- Query native SQL với đầy đủ columns.

Ví dụ:

```java
List<Enrollment> findByIdStudentId(Long studentId);
```

Spring Data property path cho embedded ID có thể phụ thuộc naming/entity model; khai báo query rõ khi cần:

```java
@Query("""
    select e
    from Enrollment e
    where e.id.studentId = :studentId
    """)
List<Enrollment> findForStudent(Long studentId);
```

Test cả query JPQL và raw SQL nếu ứng dụng dùng cả hai.

## 46. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ID null sau persist | Generator/flush timing hoặc mapping sai | Kiểm tra ID strategy, flush và SQL |
| ID đã có nhưng row không tồn tại | Transaction rollback | Verify bằng EntityManager mới sau commit |
| Sequence có gaps | Allocation, rollback hoặc concurrency | Không yêu cầu ID liên tục |
| Hai key khác course bị coi equal | `equals()` bỏ sót component | Dùng toàn bộ PK fields |
| HashSet không tìm thấy child sau persist | Hash code đổi khi derived ID hoàn thiện | Tránh mutable key trong hash collection |
| `@IdClass` bootstrap lỗi | Tên/kiểu key class không khớp | Đối chiếu entity attributes và ID class |
| Duplicate composite row được ghi | DB PK/unique migration thiếu | Tạo constraint thật và test |
| FK composite liên kết sai tenant | Thiếu tenant column trong FK | Dùng composite FK đầy đủ |
| Child transient gây flush error | Thiếu cascade PERSIST hoặc persist child | Thiết kế cascade rõ |
| Parent collection có child nhưng FK null | Chỉ sửa inverse side | Cập nhật owning side |
| Remove child không xóa row | `orphanRemoval`/owning side không đúng | Kiểm tra mapping và flush |
| Xóa parent không xóa child | Thiếu ORM cascade hoặc DB cascade | Chọn một lifecycle policy rõ |
| DB cascade xóa child nhưng callback không chạy | DB tự thực hiện cascade | Không dựa callback ORM cho raw DB action |
| `@MapsId` key không được điền | Sai attribute name hoặc join mapping | Kiểm tra `@MapsId` trỏ đúng ID attribute |
| Reparent gây lỗi PK | Parent ID là một phần derived identity | Không đổi primary key; delete/create hoặc surrogate ID |
| Duplicate line number khi concurrent | Chỉ check ở Java | Composite PK/UNIQUE ở DB |
| Test pass nhưng production fail | H2 khác DBMS | Testcontainers đúng DB |
| Flush pass, commit fail | Deferred constraints/transaction error | Test commit boundary |
| Test không thấy dữ liệu sau method | Test transaction rollback mặc định | Commit thật và verify context mới |
| Optimistic lock không bắt conflict | Thiếu `@Version` hoặc native SQL bỏ version predicate | Thêm version semantics và concurrency test |
| Test callback thứ tự flaky | Dựa vào internal ordering không portable | Assert contract cần thiết, pin version |
| `clear()` không chứng minh commit | Vẫn cùng transaction | Dùng transaction mới/commit thật |
| Child còn stale trong L1 | Persistence Context đã cache entity | Clear/close và reload |
| Parent version không đổi khi child đổi | Collection semantics/mapping | Xác định aggregate version contract |
| Repeated test bị duplicate key | Fixture data không cô lập | Transaction cleanup/schema reset/unique test IDs |

## 47. Quy trình thiết kế test cho ID và dependent relationships

**Bước 1 — Xác định identity.** ID generated, assigned, composite hay derived từ parent?

**Bước 2 — Kiểm tra key class.** Constructor, component nullability, equals/hashCode, immutability.

**Bước 3 — Kiểm tra mapping.** `@EmbeddedId`/`@IdClass`, `@MapsId`, `@JoinColumns`, owning side.

**Bước 4 — Kiểm tra schema.** PK, unique, FK, NOT NULL, composite indexes và migration.

**Bước 5 — Test persistence cơ bản.** Persist, flush, commit, reload trong context mới.

**Bước 6 — Test duplicate và invalid references.** Dựa vào database constraints, không chỉ service pre-check.

**Bước 7 — Test cascade.** PERSIST, MERGE, REMOVE theo đúng ownership.

**Bước 8 — Test orphanRemoval.** Xóa child, reload, kiểm tra child state và parent collection.

**Bước 9 — Test derived identity.** Parent generated ID được áp vào child key và FK.

**Bước 10 — Test transaction failure.** Flush rồi rollback; xác nhận không có parent/child committed.

**Bước 11 — Test concurrency.** Hai EntityManagers, unique collision và optimistic locking.

**Bước 12 — Test tenant isolation.** Cùng business key ở hai tenants nhưng composite FK không cho liên kết chéo.

**Bước 13 — Test DBMS thật.** Testcontainers với migrations production.

**Bước 14 — Test đường ngoài ORM.** Native SQL, DB cascade và batch operations nếu ứng dụng hỗ trợ.

## 48. Bài tập tình huống

### Bài 1 — Generated ID

Sau `em.persist(customer)`, ID đã khác null. Có thể kết luận row đã commit không?

**Đáp án:** Không. ID có thể được cấp trước hoặc trong INSERT; transaction vẫn có thể rollback.

### Bài 2 — Sequence gap

Test kỳ vọng IDs `1, 2, 3`, nhưng sau rollback ID tiếp theo là `52`. Có phải lỗi không?

**Đáp án:** Không nhất thiết. Sequence allocation/rollback có thể tạo gaps. Chỉ yêu cầu uniqueness và generator correctness.

### Bài 3 — Composite equality

Hai Enrollment có cùng `studentId` nhưng khác `courseId`. `equals()` trả true. Lỗi nằm ở đâu?

**Đáp án:** Key class bỏ sót một thành phần primary key trong equals/hashCode.

### Bài 4 — EmbeddedId

Entity dùng `@EmbeddedId`, nhưng key class không có equals/hashCode. Rủi ro?

**Đáp án:** Entity identity trong Java collections/repository/cache có thể sai; mapping composite ID không có value semantics đúng.

### Bài 5 — IdClass

Entity có `studentId` và `courseId`, nhưng `EnrollmentKey` dùng tên `student` và `course`. Có vấn đề gì?

**Đáp án:** Tên/kiểu các ID attributes không tương ứng entity mapping; bootstrap/persistence có thể lỗi.

### Bài 6 — Derived identity

OrderLine ID là `(orderId, lineNumber)`. Parent ID được sinh lúc persist. Annotation nào biểu diễn association cung cấp phần ID?

**Đáp án:** `@MapsId("orderId")` trên association tới parent.

### Bài 7 — Parent ID trong HashSet

OrderLine được đưa vào HashSet trước khi `orderId` được gán; hashCode dựa vào cả hai ID fields. Sau persist, lookup thất bại. Vì sao?

**Đáp án:** Hash code thay đổi khi derived ID hoàn thiện, phần tử nằm ở bucket cũ.

### Bài 8 — Owning side

`order.getLines().add(line)` nhưng không set `line.order`. Vì sao FK có thể không được ghi?

**Đáp án:** Child `ManyToOne` là owning side; inverse collection không điều khiển FK.

### Bài 9 — Cascade PERSIST

Persist parent với transient child, không có cascade PERSIST và không persist child riêng. Điều gì có thể xảy ra khi flush?

**Đáp án:** Hibernate có thể báo transient object/unsaved association; phải khai báo cascade hoặc persist child.

### Bài 10 — Orphan removal

Remove child khỏi collection có `orphanRemoval=true`, commit. Cần kiểm tra điều gì?

**Đáp án:** Child row bị remove theo mapping, các child còn lại vẫn thuộc parent và collection reload chính xác.

### Bài 11 — Shared reference

Order có `ManyToOne Product`; parent remove cascade REMOVE tới Product. Rủi ro?

**Đáp án:** Có thể xóa Product được nhiều orders dùng chung. Không cascade REMOVE tới shared reference tùy tiện.

### Bài 12 — DB cascade

DB `ON DELETE CASCADE` xóa children khi native SQL xóa parent. `@PreRemove` của từng child có chạy không?

**Đáp án:** Không. Database cascade không gọi Java lifecycle callbacks của Hibernate.

### Bài 13 — Composite tenant FK

Hai tenants đều có `customerNo=7`. FK chỉ tham chiếu `customer_no`. Có bảo vệ tenant boundary không?

**Đáp án:** Không. FK phải bao gồm tenant_id và customer_no.

### Bài 14 — Duplicate line number

Hai transactions cùng thêm line 3. Service check trước đều pass. Bảo vệ cuối là gì?

**Đáp án:** Composite PK hoặc UNIQUE `(order_id, line_number)` trong database; một transaction sẽ bị từ chối.

### Bài 15 — Reparent derived ID

OrderLine ID chứa orderId. Có thể chuyển line sang Order khác bằng setter không?

**Đáp án:** Không nên thay primary key của entity persistent. Dùng delete/create hoặc thiết kế surrogate ID nếu reparenting là use case.

### Bài 16 — Flush và rollback

Parent/child đã flush, sau đó transaction rollback. Context mới có tìm thấy rows không?

**Đáp án:** Không nếu rollback thành công; SQL đã chạy nhưng không được commit.

### Bài 17 — Spring test rollback

`@DataJpaTest` persistAndFlush pass, nhưng sau test DB không có row. Có lỗi Hibernate không?

**Đáp án:** Không nhất thiết. Test transaction thường rollback sau test.

### Bài 18 — Optimistic lock

Hai EntityManagers đọc cùng version; một update commit, update thứ hai thất bại. Annotation nào hỗ trợ?

**Đáp án:** `@Version`, kết hợp update predicate theo version.

### Bài 19 — Parent version

Child collection đổi nhưng parent version không tăng như mong đợi. Có nên giả định Hibernate luôn bump parent version?

**Đáp án:** Không. Xác định aggregate version contract và test theo mapping/version; có thể cần cập nhật parent state rõ ràng.

### Bài 20 — H2 vs PostgreSQL

Test composite FK và sequence pass trên H2 nhưng fail PostgreSQL. Hướng xử lý?

**Đáp án:** Chạy integration test trên PostgreSQL Testcontainers với migrations production và mapping thật.

## 49. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): primary keys, composite key classes, `@EmbeddedId`, `@IdClass`, derived identities, `@MapsId`, relationship ownership, cascades và orphan removal.
- [Hibernate ORM User Guide — Identifiers](https://docs.hibernate.org/orm/7.2/userguide/html_single/#identifiers): generated identifiers, sequence, identity và custom generators.
- [Hibernate ORM User Guide — Composite identifiers](https://docs.hibernate.org/orm/7.2/userguide/html_single/#identifiers-composite): composite key mappings và provider-specific considerations.
- [Hibernate ORM User Guide — Associations](https://docs.hibernate.org/orm/7.2/userguide/html_single/#associations): owning/inverse sides, one-to-many, many-to-one, one-to-one, many-to-many.
- [Hibernate ORM User Guide — Cascading](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc-cascade): cascade operations, orphan removal và lifecycle.
- [Hibernate ORM User Guide — Transactions and concurrency](https://docs.hibernate.org/orm/7.2/userguide/html_single/#transactions): transaction boundaries, optimistic locking và versioning.
- [Hibernate ORM Javadocs — `MapsId`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/mapsid): mapping derived identity.
- [Jakarta Persistence Javadocs — `EmbeddedId`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/embeddedid): embedded primary key.
- [Jakarta Persistence Javadocs — `IdClass`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/idclass): composite ID class.
- [Jakarta Persistence Javadocs — `Version`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic locking version attribute.
- [Spring Data JPA Reference — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): `save`, `persist`, `merge` và entity new-state detection.
- [Spring Framework Testing — TestContext transaction management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): transactional tests, rollback và commit controls.
- [Testcontainers Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL integration tests.
- [PostgreSQL Documentation — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary key, unique, foreign key, composite constraints và referential integrity.
- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshot visibility và concurrent transactions.

**Ghi chú phiên bản:** Các ví dụ dùng Jakarta Persistence và Hibernate hiện đại. Generated ID timing, composite mapping details, SQL ordering, cascade implementation và TestEntityManager/Spring transaction behavior phụ thuộc Hibernate, Spring Data, JDBC driver và DBMS version. Composite key classes phải tuân thủ contract của Jakarta Persistence đang dùng; các derived-identity mappings cần test bằng schema thật. SQL DDL/constraint behavior trong ví dụ cần được điều chỉnh cho DBMS khác PostgreSQL.

## Kết luận

Kiểm thử định danh và quan hệ phụ thuộc cần đi xa hơn việc xác nhận một object đã nhận ID. Với generated IDs, hãy phân biệt thời điểm cấp ID, flush và commit. Với composite IDs, xác nhận tất cả key components, equality, database primary key và foreign keys. Với derived identity, kiểm tra `@MapsId` thực sự lấy đúng ID từ parent và không cho phép thay đổi primary key trong vòng đời entity.

Với quan hệ parent-child, test phải phản ánh đúng owning side, cascade, `orphanRemoval`, shared references và database constraints. Hãy kiểm tra cả hai chiều object graph sau reload, cả committed state sau transaction mới, lẫn rollback sau khi SQL đã flush. Khi có concurrency, dùng nhiều EntityManagers/transactions và dựa vào `@Version`, UNIQUE/FK constraints để chứng minh database ngăn lost updates và liên kết sai.

Cuối cùng, chạy integration tests trên DBMS tương đương production với migrations thật. Một mapping có thể trông đúng trong Java và pass khi dùng H2, nhưng vẫn sai ở composite FK, sequence, constraint hoặc transaction behavior trên database triển khai thực tế.
