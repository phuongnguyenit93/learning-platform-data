# Xử lý EntityNotFoundException khi tham chiếu không còn hợp lệ

Trong JPA, một đối tượng tham chiếu tới entity khác **không nhất thiết đồng nghĩa bản ghi được tham chiếu đang tồn tại trong database tại thời điểm truy cập**. Khi sử dụng `EntityManager.getReference()` hoặc một quan hệ lazy, provider có thể tạo một **reference/proxy** trước khi cần truy vấn toàn bộ state. Nếu sau đó ứng dụng thực sự cần nạp entity nhưng hàng tương ứng không tồn tại, JPA có thể ném **`jakarta.persistence.EntityNotFoundException`**.

Một tình huống điển hình:

```java
Customer customer = em.getReference(Customer.class, 404L);

// Ở thời điểm này, một provider có thể chưa SELECT khách hàng.
String name = customer.getName();

// Nếu Customer #404 không tồn tại, thao tác tải state có thể ném
// EntityNotFoundException.
```

Điều cần hiểu đầu tiên là: **`getReference()` không phải một phép xác nhận tồn tại đáng tin cậy**, và một proxy hợp lệ về mặt Java không đảm bảo foreign key/row phía database vẫn hợp lệ.

Bài **“Xử lý EntityNotFoundException khi tham chiếu không còn hợp lệ”** thuộc chương **Lỗi và phục hồi** của chủ đề **Data Persistence Relational Access ORM JPA**. Bài hướng dẫn xác định nguồn exception, phân biệt với các lỗi gần giống, quản lý transaction sau failure, chuyển lỗi thành phản hồi nghiệp vụ phù hợp, sửa dữ liệu mồ côi và phòng ngừa bằng foreign key, cùng các bài integration test thực tế.

Các ví dụ dùng Java 17+, Jakarta Persistence 3.x (`jakarta.persistence`), SQL quan hệ, JUnit 5; ví dụ Spring Data JPA/Hibernate được đánh dấu riêng. Với JPA 2.x cũ, package tương ứng là `javax.persistence`. Những chi tiết về SQL được phát, thời điểm khởi tạo proxy và exception được framework bọc phụ thuộc JPA provider/transaction manager, nên bài phân biệt rõ **contract JPA** với **hành vi triển khai**.

---

## 1. Bản chất của EntityNotFoundException

`EntityNotFoundException` là một loại `PersistenceException` dùng cho trường hợp JPA cần truy cập một entity/reference nhưng không tìm thấy persistent entity tương ứng theo điều kiện được mong đợi.

Ví dụ:

```java
import jakarta.persistence.EntityNotFoundException;
```

Khả năng quan sát thường gặp:

1. `getReference(Customer.class, id)` được gọi với ID chưa có row.
2. JPA trả về một reference được trì hoãn truy vấn dữ liệu, hoặc phát hiện thiếu row ngay tại lời gọi.
3. Ứng dụng truy cập một thuộc tính cần nạp state của Customer.
4. Provider không thể nạp row Customer đó.
5. `EntityNotFoundException` được phát ra.

Một nguồn khác là một quan hệ `@ManyToOne(fetch = FetchType.LAZY)` chứa foreign key trỏ tới hàng không còn tồn tại, đặc biệt khi schema thiếu foreign key thật hoặc đã có dữ liệu mồ côi.

**Exception không có nghĩa mọi lệnh đọc không tìm thấy entity đều phải ném lỗi.** `EntityManager.find()` với một ID không tồn tại thông thường trả về `null`, trong khi `getReference()` mang hợp đồng khác.

### Từ khóa cần ghi nhớ

- **Reference:** đại diện cho một entity identity, có thể chưa nạp state.
- **Proxy/lazy initialization:** cơ chế triển khai trì hoãn truy vấn DB.
- **Dangling reference:** khóa tham chiếu trỏ tới entity không tồn tại hoặc không thể resolve.
- **Database foreign key:** ràng buộc có thể ngăn dangling reference được commit.
- **Transaction failure:** sau lỗi persistence, transaction có thể bị đánh dấu rollback-only; không nên tiếp tục unit of work như chưa có gì xảy ra.

## 2. Phân biệt `find()` và `getReference()`

| Đặc điểm | `EntityManager.find(Entity.class, id)` | `EntityManager.getReference(Entity.class, id)` |
| --- | --- | --- |
| Ý định chính | Tìm entity theo ID | Lấy reference đại diện cho identity |
| Nếu row không tồn tại | Thông thường trả `null` | Có thể ném `EntityNotFoundException` khi gọi hoặc khi state được truy cập |
| Có thể tránh tải state ngay? | Có thể tận dụng L1/L2 nhưng ý định là tìm entity | Có, được thiết kế để có thể trì hoãn tải |
| Có thể dùng làm kiểm tra tồn tại? | Phù hợp hơn trong context mới, nhưng vẫn có race | **Không** |
| Kết quả có thể là proxy? | Có thể tùy provider/mapping | Thường có lazy reference/proxy |
| Có ngăn transaction khác xóa row sau đó? | Không | Không |
| Có tự kiểm tra quyền hoặc tenant? | Không | Không |
| Có tự thay FK constraint? | Không | Không |

Ví dụ:

```java
Customer found = em.find(Customer.class, 404L);

if (found == null) {
    throw new CustomerNotFoundException(404L);
}
```

So với:

```java
Customer reference = em.getReference(
    Customer.class,
    404L
);

// Không nên coi dòng trên là bằng chứng
// Customer #404 hiện tồn tại trong DB.
```

Nếu business logic cần xác nhận Customer tồn tại, còn hoạt động và thuộc đúng tenant, nên **tìm, kiểm tra và áp dụng nghiệp vụ rõ ràng** thay vì lấy một proxy rồi hy vọng provider sẽ xác nhận hộ.

## 3. Vì sao JPA cung cấp `getReference()`?

Có những trường hợp ứng dụng chỉ cần **entity identity** để thiết lập một association, không cần toàn bộ state của entity liên quan.

Ví dụ tạo PurchaseOrder thuộc Customer:

```java
PurchaseOrder order = new PurchaseOrder();

Customer customer = em.getReference(
    Customer.class,
    customerId
);

order.setCustomer(customer);
em.persist(order);
```

Một provider có thể dùng customerId để đặt foreign key mà không chạy SELECT toàn bộ Customer. Điều này có thể tiết kiệm query trong trường hợp ID đã được xác minh từ nguồn đáng tin và nghiệp vụ không cần đọc Customer.

Nhưng sự tối ưu đó có đánh đổi:

- `getReference()` có thể chưa xác minh Customer tồn tại.
- Nếu không có FK thật, một order có thể lưu ID tham chiếu mồ côi.
- Nếu có FK, DB có thể từ chối INSERT ở `flush()` hoặc `commit()`.
- Nếu chỉ đọc reference sau khi Customer đã bị xóa, `EntityNotFoundException` có thể xuất hiện.
- Nếu nghiệp vụ cần trạng thái `Customer.active`, reference-by-ID không đủ để kiểm tra.

**`getReference()` là công cụ làm việc với identity, không phải một API xác thực đầu vào.**

## 4. Một entity model dùng xuyên suốt

Ta dùng Customer và PurchaseOrder:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 160)
    private String displayName;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {}

    public Customer(Long id, String displayName) {
        this.id = id;
        this.displayName = displayName;
        this.active = true;
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public boolean isActive() { return active; }

    public void deactivate() {
        active = false;
    }
}
```

PurchaseOrder:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "customer_id",
        nullable = false
    )
    private Customer customer;

    @Column(nullable = false)
    private String description;

    protected PurchaseOrder() {}

    public PurchaseOrder(
            Long id,
            Customer customer,
            String description) {
        this.id = id;
        this.customer = customer;
        this.description = description;
    }

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public String getDescription() { return description; }
}
```

DDL ý tưởng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    version BIGINT,
    display_name VARCHAR(160) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    version BIGINT,
    customer_id BIGINT NOT NULL,
    description VARCHAR(250) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
```

DDL có thể khác theo DB dialect và ID/version strategy. Đây là mô hình để giải thích lỗi, không phải migration tự động áp được nguyên văn trên mọi database.

### Điểm đáng chú ý

- `@ManyToOne(fetch = LAZY)` cho phép trì hoãn tải Customer.
- `optional = false` và `nullable = false` mô tả quan hệ bắt buộc trong mapping.
- **Ràng buộc SQL `FOREIGN KEY` được triển khai thật** mới bảo vệ tham chiếu khi writers dùng native SQL/JDBC.
- `@Version` xử lý optimistic concurrency của từng entity, không phải một phép kiểm tra Customer tồn tại.
- Một Customer không còn active vẫn là một entity **có tồn tại**; `EntityNotFoundException` không phải lỗi nghiệp vụ “khách hàng chưa hoạt động”.

---

## 5. Timeline: reference được tạo trước khi lỗi xuất hiện

Ví dụ provider hỗ trợ lazy proxy:

```text
Transaction A
   │
   ├─ em.getReference(Customer, 404)
   │       │
   │       └─ proxy/reference với identity 404
   │          (có thể chưa SELECT)
   │
   ├─ order.setCustomer(reference)
   │
   ├─ em.persist(order)
   │
   ├─ một bước khác cần customer.getDisplayName()
   │       │
   │       └─ SELECT Customer WHERE id=404
   │                       │
   │                       └─ Không có row
   │
   └─ EntityNotFoundException
```

Một implementation có thể phát `EntityNotFoundException` **ngay tại `getReference()`** nếu nó chọn xác minh row sớm. Vì vậy các tests và handler không nên dựa vào giả định exception luôn xuất hiện đúng ở getter.

Một implementation cũng có thể giữ reference nhưng **lỗi database FK** xuất hiện khi order được INSERT, trước khi có ai gọi `customer.getDisplayName()`. Hai lỗi phản ánh hai kiểm tra khác nhau.

## 6. `getId()` có làm proxy khởi tạo không?

Nhiều provider, nhất là Hibernate với một số kiểu proxy, có thể trả identifier từ reference mà không truy vấn toàn bộ entity:

```java
Customer reference = em.getReference(
    Customer.class, 404L
);

Long id = reference.getId();
```

Tuy nhiên, **không dựa vào thao tác lấy ID như một phép chứng minh tồn tại hoặc một trigger tải row portable**. Cách proxy định nghĩa getters, bytecode enhancement, access type và provider behavior có thể khác.

Nếu muốn kiểm tra reference thực sự được resolve, phải thực hiện thao tác có contract tải state tương ứng trong môi trường thực tế; còn nếu mục tiêu chỉ là tồn tại, hãy dùng một phép tìm với business checks rõ ràng.

Một API cũng không nên trả về entity proxy rồi mong JSON serializer tự lựa chọn đúng mốc kiểm tra tồn tại.

## 7. Một FK bị hỏng sẽ biểu hiện thế nào?

Giả sử schema legacy không có foreign key:

```text
customers:
  id=10, display_name="Lan"

purchase_orders:
  id=500, customer_id=99

customers id=99: KHÔNG TỒN TẠI
```

Khi load PurchaseOrder #500:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    500L
);

Customer customer = order.getCustomer();
```

Tùy provider và mapping, `getCustomer()` có thể trả lazy reference cho ID 99. Khi truy cập:

```java
String name = customer.getDisplayName();
```

JPA phải cố lấy state Customer #99. Vì không có row, `EntityNotFoundException` (hoặc exception provider-specific được translation) có thể xảy ra.

**Order #500 vẫn tồn tại.** Nếu API đang GET order và lỗi xuất hiện khi nạp Customer, việc trả “order không tồn tại” là sai về ngữ nghĩa. Đây thường là **lỗi toàn vẹn dữ liệu tham chiếu** cần giám sát và sửa nguồn.

## 8. Tại sao dữ liệu mồ côi có thể tồn tại?

Các nguyên nhân thường gặp:

1. Schema production chưa tạo FK thật, dù Java có `@ManyToOne`.
2. FK bị disable trong giai đoạn import dữ liệu.
3. Dữ liệu legacy có trước khi constraint được thêm.
4. Batch JDBC/native SQL ghi `customer_id` không hợp lệ.
5. Customer bị xóa bằng script bên ngoài khi constraint không hoạt động.
6. Một hệ thống khác ghi trực tiếp vào database.
7. Dữ liệu được di chuyển hoặc đồng bộ không đầy đủ giữa databases.
8. Đọc từ replica chưa đồng bộ, hoặc consistency window làm row liên quan chưa thấy được.
9. Provider/cache/persistence context giữ reference cũ trong khi trạng thái database đã thay đổi.
10. Mapping trỏ sai schema/table/tenant hoặc định danh không khớp.
11. Soft-delete filters khiến hàng vật lý vẫn tồn tại nhưng không được resolve theo cách query/provider đang dùng.
12. Logic ứng dụng lạm dụng `getReference()` để gán quan hệ từ ID do client gửi mà không có policy kiểm tra.

Không phải nguyên nhân nào cũng tạo ra đúng cùng exception. Một số trường hợp sẽ báo DB FK violation, `OptimisticLockException`, `LazyInitializationException` hoặc lỗi tenant access thay vì `EntityNotFoundException`.

Đừng kết luận “database có orphan” chỉ dựa trên class exception; cần điều tra entity identity, SQL, transaction và mappings.

## 9. Tìm dữ liệu mồ côi bằng SQL

Với hai bảng ví dụ:

```sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM purchase_orders o
LEFT JOIN customers c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

Câu SQL trả về các PurchaseOrders có `customer_id` nhưng không có Customer cùng ID.

Đây là một **data-quality query**, không phải biện pháp tự sửa. Khi phát hiện rows:

- Xác định chúng có bị tạo bởi import/job cụ thể không.
- Kiểm tra có thiếu constraint trong migration không.
- Xác minh dữ liệu có bị xóa hợp lệ theo chính sách hay không.
- Kiểm tra replicated/partitioned/tenant databases đúng context.
- Xác định restore Customer, reassign Order hoặc xử lý dữ liệu theo business decision.
- Sau cleanup, thêm FK và giám sát integrity.

**Không tự sửa `customer_id` thành bất kỳ Customer ID nào chỉ để exception biến mất.** Việc gắn nhầm Customer có thể gây sai dữ liệu giao dịch và vi phạm quyền riêng tư.

## 10. `optional = false` có ngăn orphan không?

Annotation:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    optional = false
)
private Customer customer;
```

biểu đạt một association bắt buộc ở mapping level.

Nó không tự chứng minh database production đã được tạo FK. Thêm:

```java
@JoinColumn(
    name = "customer_id",
    nullable = false
)
```

có thể giúp DDL generation/mapping, nhưng **schema đang chạy mới là nguồn sự thật**.

So sánh:

| Cơ chế | Điều bảo vệ |
| --- | --- |
| `optional = false` | Ý định quan hệ không được null trong object mapping |
| `@JoinColumn(nullable = false)` | Metadata nullability cột, hỗ trợ tạo DDL |
| `@NotNull` trên property | Bean Validation khi được kích hoạt |
| SQL `customer_id NOT NULL` | Cột không chứa SQL NULL |
| SQL `FOREIGN KEY(customer_id) REFERENCES customers(id)` | ID trỏ tới parent tồn tại theo DB constraint semantics |

Một cột `customer_id NOT NULL` vẫn có thể chứa 99 khi bảng customers không có 99 **nếu thiếu FK**. NOT NULL và FOREIGN KEY không hoán đổi cho nhau.

## 11. Foreign key là hàng rào quan trọng nhất

Với ràng buộc:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id);
```

database có thể ngăn INSERT/UPDATE order trỏ tới Customer không có row, và kiểm soát DELETE parent khi còn rows tham chiếu theo referential action.

Lợi ích:

- Bảo vệ kể cả các writers ngoài JPA.
- Tránh orphan do gán ID sai.
- Ngăn xóa parent làm quan hệ mất integrity khi `ON DELETE` action phù hợp.
- Làm lỗi xuất hiện ở thời điểm ghi thay vì đợi lazy navigation của một request khác.
- Cung cấp hợp đồng dữ liệu rõ cho import/migration.

### Ranh giới của FK

Foreign key **không** thay thế:

- Kiểm tra Customer active.
- Authorization/tenant scoping.
- Business rule không được đặt Order cho Customer bị suspended.
- Soft-delete policy.
- Transaction isolation/locking cho quy tắc phức tạp.
- Kiểm tra dữ liệu từ replica đọc chậm.
- Chính sách archive hoặc GDPR deletion.

FK trả lời câu hỏi “ID được tham chiếu có hợp lệ theo ràng buộc database không?”, không trả lời mọi câu hỏi nghiệp vụ.

## 12. Tại sao một FK đúng có thể cho lỗi khác EntityNotFoundException?

Giả sử:

```java
Customer ghost = em.getReference(
    Customer.class, 404L
);

PurchaseOrder order = new PurchaseOrder(
    700L,
    ghost,
    "New order"
);

em.persist(order);
em.flush();
```

Nếu ứng dụng **chưa đọc state của ghost**, provider có thể chỉ dùng ID 404 cho `customer_id`. Khi INSERT order, database thấy FK trỏ row không có và từ chối.

Kết quả có thể là một `PersistenceException` có cause SQL FK constraint violation, không phải `EntityNotFoundException`.

Vậy:

- **Lỗi khi giải tham chiếu:** thường biểu hiện `EntityNotFoundException`.
- **Lỗi khi lưu foreign key trỏ ID thiếu:** thường biểu hiện database integrity/foreign-key violation.
- **Lỗi khi parent bị xóa trong transaction khác:** có thể biểu hiện lock/constraint/concurrency exception theo schedule.

Không chỉ bắt `EntityNotFoundException` rồi cho rằng đã xử lý mọi trường hợp “Customer không tồn tại”.

---

## 13. Phân biệt `EntityNotFoundException` và các lỗi gần giống

| Lỗi/cơ chế | Tình huống điển hình | Hướng xử lý |
| --- | --- | --- |
| `EntityNotFoundException` | Reference/proxy không resolve được entity | Xác định ID, nguồn reference, rollback, kiểm tra integrity |
| `EntityManager.find(...) == null` | Tra cứu ID không có row | Chuyển thành domain NotFound/404 nếu phù hợp |
| `NoResultException` | `getSingleResult()` không tìm thấy row | Xử lý kết quả query trống theo API |
| `NonUniqueResultException` | `getSingleResult()` có nhiều kết quả | Sửa query/unique business invariant |
| `OptimisticLockException` | Version/state stale khi ghi | Rollback, reload, xử lý conflict/retry có kiểm soát |
| `TransactionRequiredException` | Cần transaction active nhưng không có | Sửa transaction boundary |
| `LazyInitializationException` (Hibernate) | Truy cập lazy proxy ngoài Session/context phù hợp | Sửa fetch/DTO/service boundary, không mặc định row mất |
| SQL FK violation | INSERT/UPDATE/DELETE vi phạm referential constraint | Xác định constraint, sửa write path/data |
| `EntityExistsException` | Persist identity đã tồn tại theo context/DB | Xử lý duplicate identity/unique conflict |
| Access denied/tenant mismatch | Caller không được xem entity | Authorization/tenant mapping, không coi là orphan mặc định |

**Tên exception là tín hiệu, không phải toàn bộ chẩn đoán.** Hãy xem khi nào nó phát sinh và dữ liệu thực tế ở database.

## 14. `NoResultException` không giống `EntityNotFoundException`

Một query:

```java
Customer customer = em.createQuery(
    "SELECT c FROM Customer c WHERE c.id = :id",
    Customer.class
).setParameter("id", customerId)
 .getSingleResult();
```

Nếu không có result, tùy API/version JPA có thể ném:

```java
jakarta.persistence.NoResultException
```

Điều đó khác việc có một reference rồi **không thể resolve persistent entity**.

Một cách tránh exception cho lookup:

```java
Customer customer = em.find(
    Customer.class,
    customerId
);

if (customer == null) {
    throw new CustomerNotFoundException(customerId);
}
```

Hoặc Spring Data:

```java
Customer customer = repository.findById(customerId)
    .orElseThrow(
        () -> new CustomerNotFoundException(customerId)
    );
```

Điều này giúp business intent rõ: caller tìm Customer ID và không thấy. Nhưng vẫn cần transaction/locking/constraints nếu Customer có thể bị xóa sau bước kiểm tra.

## 15. `LazyInitializationException` không đồng nghĩa row đã mất

Với Hibernate:

```java
PurchaseOrder order = service.loadOrder(id);

// Transaction/Session đã đóng.
String name = order.getCustomer().getDisplayName();
```

Nếu association lazy chưa initialized và không còn Session thích hợp, có thể ném:

```java
org.hibernate.LazyInitializationException
```

Ở đây database **có thể vẫn chứa Customer hợp lệ**; chỉ là ứng dụng đã cố truy cập lazy state ngoài lifecycle của persistence context.

Ngược lại, nếu session còn mở và JPA cố load Customer nhưng row không tồn tại, có thể gặp `EntityNotFoundException`.

Giải pháp cho lỗi Session không còn:

- Lấy những dữ liệu cần thiết trong service transaction.
- Dùng DTO projection.
- Fetch join hoặc `EntityGraph` theo use case.
- Không trả entity graphs chứa lazy proxies ra API serializer.
- Không chỉ bật Open Session in View để che thiết kế fetch plan chưa rõ.

**Không sửa dữ liệu hoặc thêm FK một cách mù quáng khi lỗi thực sự là LazyInitializationException.**

## 16. `EntityNotFoundException` và soft delete

Giả sử Customer không bị xóa vật lý nhưng có:

```java
private boolean deleted;
```

Một hệ thống áp filter “chỉ đọc customer chưa bị soft-delete”. Khi Order trỏ tới Customer đã soft-delete:

- Row Customer có thể **vẫn tồn tại vật lý**.
- Filter/provider-specific SQL restriction có thể làm association không resolve được theo một số loading paths.
- Hành vi có thể là null, exception, proxy không khởi tạo được hoặc provider-specific; cần kiểm tra mapping thật.
- Không nên tự đồng nhất “không resolve được” với “row bị xóa vật lý”.

### Chính sách nên rõ ràng

Chọn một trong các cách phù hợp nghiệp vụ:

1. Giữ association tới Customer đã inactive/soft-deleted để bảo toàn lịch sử đơn hàng, nhưng hạn chế hiển thị thông tin nhạy cảm.
2. Tạo một snapshot các thông tin khách hàng cần thiết ngay trên Order (theo chính sách lưu trữ).
3. Tách active filter khỏi đường resolve lịch sử có quyền truy cập.
4. Dùng một đối tượng lưu trữ/archived reference riêng có semantics rõ.
5. Không xóa dữ liệu quan hệ đang được nghiệp vụ yêu cầu giữ lại.

Không dùng `@NotFound(IGNORE)` như một giải pháp mặc định cho mọi soft-delete issue.

## 17. `@NotFound(IGNORE)` của Hibernate là gì?

Hibernate có extension:

```java
@org.hibernate.annotations.NotFound(
    action = org.hibernate.annotations.NotFoundAction.IGNORE
)
```

Trong một số mappings, extension này hướng Hibernate xử lý association có FK tham chiếu row không tồn tại như không có association, thay vì throw, **theo semantics provider-specific**.

Điều cần cân nhắc:

- Không thuộc Jakarta Persistence chuẩn.
- Có thể làm relation “tưởng là null” dù FK column không null.
- Che dữ liệu mồ côi và làm báo cáo không đầy đủ.
- Một số cách mapping có thể ảnh hưởng lazy fetching/khởi tạo, dẫn tới truy vấn eager ngoài dự kiến.
- Không sửa database integrity.
- Có thể làm business logic nhầm “chưa gán Customer” với “Customer đã mất”.
- Hành vi tùy Hibernate version, mapping và constraints.

Chỉ dùng khi **có quyết định rõ ràng về dữ liệu legacy không sửa được ngay**, có test và observability, đồng thời vẫn lập kế hoạch xử lý nguồn tạo orphan.

## 18. Tránh nhầm “null association” và “dangling association”

Ba trạng thái khác nhau:

```text
A) order.customer_id = NULL
   → Không có association theo schema/mapping cho phép.

B) order.customer_id = 20
   customers.id=20 tồn tại
   → Association hợp lệ.

C) order.customer_id = 99
   customers.id=99 không tồn tại
   → Dangling/invalid reference.
```

Nếu ứng dụng chuyển trường hợp C thành `null`, nó có thể:

- Làm người dùng tưởng đơn hàng không có khách hàng.
- Phá logic báo cáo “số order guest”.
- Che import job gây lỗi.
- Khiến audit không thấy nguyên nhân thiếu dữ liệu.
- Làm khó thêm FK sau này.

**Một association không có giá trị được cho phép** và **một association bị đứt referential integrity** nên có cách xử lý/ghi nhận khác nhau.

## 19. Trường hợp nào nên dùng `find()` thay vì `getReference()`?

Nên chọn `find()` khi:

- ID do client/request truyền vào chưa tin cậy.
- Cần trả 404 có chủ ý nếu Customer không tồn tại.
- Cần kiểm tra `active` hoặc business policy.
- Cần đọc thuộc tính Customer.
- Cần áp tenant/authorization filter trong query.
- Cần thông báo lỗi domain trước khi tạo Order.
- Muốn tránh mang proxy không kiểm chứng tới nhiều layers.
- Nếu hàng không tồn tại, logic phải dừng **ngay trước** các bước khác.

Ví dụ:

```java
public PurchaseOrder createOrder(
        EntityManager em,
        Long orderId,
        Long customerId,
        String description) {

    Customer customer = em.find(
        Customer.class,
        customerId
    );

    if (customer == null) {
        throw new CustomerNotFoundException(customerId);
    }

    if (!customer.isActive()) {
        throw new CustomerInactiveException(customerId);
    }

    PurchaseOrder order = new PurchaseOrder(
        orderId,
        customer,
        description
    );

    em.persist(order);

    return order;
}
```

Method này giả định caller đã thiết lập transaction và quyền/tenant context đúng. Nó không tự giải quyết deletion race sau bước find; DB foreign key và transaction policy vẫn cần thiết.

## 20. Khi nào `getReference()` là lựa chọn hợp lý?

Có thể dùng khi:

- ID đã được xác minh trong một flow được tin cậy.
- Business operation chỉ cần relationship-by-ID.
- Không cần đọc thuộc tính của target.
- Muốn tránh SELECT không cần thiết trong một transaction ngắn.
- Database có FK và application xử lý integrity failure đúng.
- Không có một policy yêu cầu target active/owned-by-tenant phải được kiểm tra tại thời điểm này.

Ví dụ một import nội bộ có Customer IDs đã qua kiểm tra:

```java
Customer customer = em.getReference(
    Customer.class,
    trustedCustomerId
);

PurchaseOrder order = new PurchaseOrder(
    generatedOrderId,
    customer,
    description
);

em.persist(order);
```

Nhưng “trusted” là giả định về nguồn; nó **không bảo đảm Customer không bị xóa bởi concurrent transaction**. Foreign key vẫn là lớp bảo vệ quan trọng.

### Không dùng `getReference()` làm “exists”

Anti-pattern:

```java
Customer customer = em.getReference(
    Customer.class,
    customerId
);

return customer != null; // Không kiểm tra DB.
```

Reference có thể không null ngay cả khi row không có.

## 21. Một lần `find()` cũng không chống race condition

Giả sử:

```text
Transaction A                          Transaction B
       │                                     │
find(Customer #10) → tồn tại                │
       │                                DELETE Customer #10
       │                                     │
       │                                  COMMIT
       │
persist(PurchaseOrder -> Customer #10)
       │
flush()/commit()
       │
FK violation / lock wait / conflict
```

Nếu DB có FK, insert child và delete parent được phối hợp theo khóa/constraint semantics; kết quả cụ thể phụ thuộc engine và thời điểm. Nhưng **“đã find thấy Customer” không giữ được row tồn tại mãi mãi**.

Để đạt đúng nghiệp vụ có thể cần:

- FK chuẩn.
- Transaction boundaries ngắn.
- Khóa phù hợp nếu cần bảo vệ parent state trong toàn operation.
- Quy tắc xóa parent có child.
- Optimistic versioning khi parent state liên quan quyết định.
- Retry có kiểm soát khi là conflict tạm thời.

`find()` cải thiện semantic lookup và error clarity, không thay concurrency control.

## 22. Có nên khóa Customer khi tạo Order?

Nếu rule là “không được tạo Order khi Customer đã bị deactivate hoặc đang bị xóa”, chỉ đọc state rồi tạo có thể chưa đủ khi có concurrent writers.

Một phương án là yêu cầu lock thích hợp:

```java
Customer customer = em.find(
    Customer.class,
    customerId,
    LockModeType.PESSIMISTIC_READ
);
```

hoặc:

```java
Customer customer = em.find(
    Customer.class,
    customerId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Lựa chọn phụ thuộc DB isolation, contention và nghiệp vụ. `PESSIMISTIC_READ` không phải shared-lock bảo đảm giống nhau trên mọi DB; `WRITE` mạnh hơn nhưng tăng tranh chấp. Đối với thao tác tạo child, DB FK có thể đã cung cấp một mức phối hợp tồn tại phù hợp, nhưng kiểm tra **trạng thái active** có thể cần policy bổ sung.

Không bật WRITE lock trên mọi Customer chỉ để tránh một ngoại lệ hiếm nếu business invariant và workload không đòi hỏi.

## 23. `EntityNotFoundException` có tự rollback transaction không?

JPA xem `EntityNotFoundException` là một persistence failure; với persistence context tham gia một transaction đang hoạt động, exception do provider ném có thể đánh dấu transaction **rollback-only** theo contract JPA áp dụng.

Thực hành an toàn:

1. **Không cố tiếp tục unit of work như thành công.**
2. Phân loại exception và ghi log context phù hợp.
3. Rollback transaction hiện tại nếu bạn sở hữu nó.
4. Kết thúc/đóng EntityManager của unit of work thất bại.
5. Nếu cần phục hồi, tạo transaction và context mới.
6. Tải lại dữ liệu thật; không tin proxy/stale managed graph cũ.
7. Xử lý business result hoặc retry theo nguyên nhân.

Đừng viết:

```java
try {
    customer.getDisplayName();
} catch (EntityNotFoundException ignored) {
    // Bỏ qua.
}

em.persist(anotherOrder);
em.getTransaction().commit(); // Có thể thất bại, rollback-only.
```

Ngay cả khi `EntityTransaction.isActive()` còn true, điều đó **không chứng minh transaction có thể commit**. Hãy coi failure nghiêm trọng và rollback, trừ khi một contract cụ thể được kiểm chứng cho phép recovery trong transaction hiện tại.

## 24. Mẫu rollback resource-local đúng

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Customer reference = em.getReference(
        Customer.class,
        customerId
    );

    String name = reference.getDisplayName();

    // Thao tác nghiệp vụ khác trong cùng transaction...

    em.getTransaction().commit();
} catch (RuntimeException failure) {
    if (em.getTransaction().isActive()) {
        try {
            em.getTransaction().rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }

    throw failure;
} finally {
    em.close();
}
```

Trong môi trường Spring/JTA, transaction manager thường sở hữu commit/rollback; **không gọi thủ công `em.getTransaction()`** trên transaction-scoped container-managed EntityManager.

Mẫu chỉ minh họa quản lý tài nguyên; trong service production nên biết exception từ reference được map ở tầng nào và không làm lộ implementation details cho client.

## 25. Vì sao không dùng lại reference sau rollback?

Một proxy/reference được tạo trong persistence context đã lỗi có thể:

- Mang identifier nhưng chưa từng nạp state hợp lệ.
- Gắn với EntityManager/Session đã đóng.
- Không phản ánh dữ liệu vừa được sửa/khôi phục ở database.
- Gây exception khác khi truy cập (ví dụ lazy initialization failure).
- Bị detached, không còn lifecycle phù hợp.

Sau rollback:

```java
// KHÔNG coi "oldReference" là đại diện cho DB hiện tại.
Customer oldReference = ...;
```

Nếu muốn kiểm tra lại:

```java
EntityManager fresh = emf.createEntityManager();

try {
    Customer current = fresh.find(
        Customer.class,
        customerId
    );

    // null hoặc entity theo committed state được nhìn thấy.
} finally {
    fresh.close();
}
```

Tạo context mới cũng loại ảnh hưởng của identity map cũ. Nếu dùng L2 cache hoặc replica, còn cần xem cache/isolation policy để hiểu độ mới của dữ liệu.

## 26. Khác biệt giữa Java object state và database state

Giả sử một PurchaseOrder managed đã load Customer proxy. Trong lúc khác, một writer trực tiếp xóa Customer hoặc database đã có orphan.

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId
);

Customer ref = order.getCustomer();
```

Ở Java, `ref` có thể tồn tại và `ref != null`. Nhưng DB có thể không có row tương ứng.

**Java reference ≠ referential integrity.**

Tương tự, sau rollback, các setters/callbacks trên Order object không tự được khôi phục về giá trị DB committed. Không serialize object từ failed transaction rồi gọi đó là dữ liệu chính thức.

## 27. EntityManager đã có entity trong L1 thì sao?

JPA duy trì identity map trong persistence context. Giả sử:

```java
Customer customer = em.find(Customer.class, 10L);
```

Sau đó một transaction khác xóa Customer #10 và commit. Nếu EntityManager hiện tại vẫn giữ Customer #10 managed:

```java
Customer again = em.find(Customer.class, 10L);
```

nó có thể trả cùng managed representative mà **không query DB mới**. Không nên suy rằng lần `find` sau chứng minh row còn tồn tại.

Khi cần kiểm tra committed state mới:

- Dùng EntityManager mới.
- Cân nhắc `refresh()` hoặc load policy thích hợp, nhưng refresh thiếu row có thể ném exception.
- Xem transaction isolation/snapshot.
- Xem L2 cache và read replica.
- Không tái sử dụng extended persistence context dài hạn cho freshness checks mà không có policy.

Như vậy, một lỗi missing reference có thể bị phát hiện muộn, còn một entity đã managed có thể tạm thời chưa phát hiện row đã mất.

## 28. `refresh()` có giúp phát hiện row đã bị xóa không?

Khi entity đang managed, có thể:

```java
em.refresh(customer);
```

Đây là một yêu cầu JPA đọc lại state persistent từ database. Nếu row không tồn tại theo visibility của transaction/provider, refresh có thể ném `EntityNotFoundException` theo contract áp dụng.

Nhưng:

- `refresh()` không phải một phép kiểm tra tồn tại không có tác dụng phụ.
- Nó có thể ghi đè changes chưa flush của managed entity.
- Có thể liên quan cascade REFRESH.
- Isolation level có thể giới hạn state được thấy.
- Sau exception phải xem transaction rollback-only.
- Không nên gọi refresh trên detached entity rồi kỳ vọng thành công.

Dùng refresh khi thật sự có mục tiêu reload state của một managed entity, không chỉ làm “phép thử” cho mọi ID client gửi.

## 29. Một entity bị xóa giữa `getReference` và getter

Timeline:

```text
A: getReference(Customer #10)
         │
B: DELETE Customer #10, COMMIT
         │
A: customer.getDisplayName()
         │
A: cố nạp row #10, không thấy
         │
A: EntityNotFoundException
```

Điều này có thể xảy ra trong hệ thống không có lock/transaction visibility đủ để giữ row tồn tại qua khoảng đó. Nhưng nếu A đã load/lock row hoặc isolation cho snapshot cũ, kết quả có thể khác.

Đây là lý do không xem `getReference` như việc “đặt chỗ” một entity identity cho tương lai.

Nếu nghiệp vụ cần “Customer tồn tại và active trong suốt thao tác Order”, cần **thiết kế transaction và business coordination**, không chỉ sửa catch block.

## 30. Khi exception đến từ kết quả JSON serialization

Một API trả entity trực tiếp:

```java
@GetMapping("/orders/{id}")
public PurchaseOrder get(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
```

Nếu serializer duyệt:

```text
PurchaseOrder.customer.displayName
```

nó có thể kích hoạt lazy initialization ở **ngoài service transaction**. Khi target thiếu, lỗi có thể phát sinh ở serializer thay vì repository/service.

Hậu quả:

- Lỗi xảy ra muộn, đôi khi HTTP response đã bắt đầu ghi.
- Controller/service không dễ phân loại nguyên nhân.
- Exception có thể bị framework wrap.
- Log trông như lỗi JSON thay vì lỗi dữ liệu.
- Có nguy cơ vô tình tải sâu association graph hoặc lộ dữ liệu.

Hướng tốt hơn: **trả DTO** và resolve các association cần thiết trong transaction.

```java
public record OrderView(
    Long id,
    Long customerId,
    String customerName,
    String description
) {}
```

Service chuẩn bị DTO khi còn transaction, đồng thời kiểm soát missing relation.

## 31. Một service chuyển entity sang DTO rõ ràng

Ví dụ:

```java
@Transactional(readOnly = true)
public OrderView getOrder(Long id) {
    PurchaseOrder order = orderRepository.findById(id)
        .orElseThrow(
            () -> new OrderNotFoundException(id)
        );

    Customer customer;

    try {
        customer = order.getCustomer();

        // Truy cập thuộc tính cần thiết, có thể kích hoạt lazy load.
        String customerName = customer.getDisplayName();

        return new OrderView(
            order.getId(),
            customer.getId(),
            customerName,
            order.getDescription()
        );
    } catch (EntityNotFoundException failure) {
        throw new OrderDataIntegrityException(
            id,
            "Order refers to missing Customer",
            failure
        );
    }
}
```

Đây là Spring-style example, phụ thuộc các classes/repositories/exceptions của ứng dụng. Quan trọng: khi catch `EntityNotFoundException`, **transaction có thể rollback-only**, nên custom exception vẫn phải được propagate để transaction boundary rollback. Không catch rồi trả thành công.

Cũng không được map trường hợp này thành `OrderNotFoundException`, vì Order tồn tại; dữ liệu Customer liên quan mới không resolve được.

Nếu ứng dụng cần trả một Order lịch sử dù Customer bị xóa, hãy thiết kế **data representation/snapshot policy** thay vì cố dereference một FK hỏng.

## 32. Tránh bắt lỗi quá rộng

Anti-pattern:

```java
try {
    return order.getCustomer().getDisplayName();
} catch (RuntimeException ex) {
    return "Unknown";
}
```

Điều này nuốt:

- EntityNotFoundException.
- LazyInitializationException.
- Database connection failure.
- Programming bugs.
- Security violations.
- Mapping errors.

Hậu quả: API trả dữ liệu trông hợp lệ, còn hệ thống mất tín hiệu lỗi integrity.

Nếu nghiệp vụ thật sự chấp nhận “Customer không còn dữ liệu hiển thị”, phải định nghĩa **một trạng thái domain rõ** và có cách lấy Order không làm vỡ transaction, ví dụ thông tin được snapshot ở Order hoặc một đường query/phép chiếu biết Customer có thể vắng mặt.

Đừng coi mọi exception là “khách hàng đã xóa”.

## 33. Nên trả HTTP 404, 409 hay 500?

Không có một mã HTTP duy nhất áp cho mọi `EntityNotFoundException`. Chọn theo **nguồn ID và đối tượng người dùng đang thao tác**.

| Trường hợp | Mã thường phù hợp | Giải thích |
| --- | --- | --- |
| Client GET `/customers/404`, Customer không tồn tại | 404 | Resource được yêu cầu không có |
| Client POST Order với customerId không hợp lệ | 400/404/422 theo API contract | Related resource không hợp lệ, cần trả lỗi rõ |
| Customer vừa bị xóa trong request tạo Order | 409 hoặc 422 theo policy | Conflict với trạng thái mới; cân nhắc retry/reload |
| GET `/orders/500`, Order tồn tại nhưng FK customer mồ côi | 500 hoặc lỗi integrity được xử lý nội bộ | Không nên giả vờ Order không tồn tại |
| Query `getSingleResult` không có row | 404/empty result theo use case | Không phải mặc định EntityNotFound |
| User không được xem Customer trong tenant khác | 403 hoặc 404 không lộ tồn tại | Authorization policy, không phải dữ liệu mồ côi mặc định |
| Transaction/DB unavailable | 500/503 | Infrastructure error; không chuyển thành customer-not-found |

Một hệ thống có thể cố định contract khác (ví dụ 422 cho missing related resource), miễn **ổn định và phân biệt đúng domain state**.

### Không phơi bày identity nội bộ

Nếu thiếu Customer vì lỗi data integrity, log nên đủ correlation ID/order ID để điều tra, nhưng response không nên công khai raw SQL, stack trace hay thông tin của Customer thuộc tenant khác.

## 34. Xử lý ở application boundary thay vì proxy boundary

Một kiểu exception domain:

```java
public final class CustomerNotFoundException
        extends RuntimeException {

    private final Long customerId;

    public CustomerNotFoundException(Long customerId) {
        super("Customer not found");
        this.customerId = customerId;
    }

    public Long getCustomerId() {
        return customerId;
    }
}
```

Service:

```java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    Customer customer = customerRepository
        .findById(command.customerId())
        .orElseThrow(
            () -> new CustomerNotFoundException(
                command.customerId()
            )
        );

    // Kiểm tra quyền, tenant, active, business invariants.
    PurchaseOrder order = createDomainOrder(customer, command);

    orderRepository.save(order);
    return order.getId();
}
```

`CreateOrderCommand` và `createDomainOrder` là application types/helpers cần triển khai. Điểm chính: **chuyển ý nghĩa ID không hợp lệ sang domain exception chủ động**, thay vì đợi JPA proxy fail muộn.

Database FK vẫn cần tồn tại để chặn race, vì Customer có thể bị xóa giữa check và INSERT.

## 35. Spring Data JPA `findById` và `getReferenceById`

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {}
```

Hai API thường gặp:

```java
Optional<Customer> found =
    customerRepository.findById(id);
```

và:

```java
Customer reference =
    customerRepository.getReferenceById(id);
```

**`getReferenceById` của Spring Data JPA** thường dựa trên cơ chế JPA `getReference` và có thể trả lazy reference, không bảo đảm row đã được kiểm tra.

Đừng dùng:

```java
Customer customer = repository.getReferenceById(id);

if (customer != null) {
    // Tưởng Customer tồn tại.
}
```

Thay bằng `findById` nếu business flow cần xác nhận tồn tại và nạp state.

### Tên các API cũ

Một số version Spring Data có `getOne` hoặc `getById` với lazy-reference semantics; chúng đã được thay thế/deprecate theo các phiên bản thư viện. Khi đọc code cũ, cần kiểm tra **contract thực tế của method theo Spring Data version** trước khi suy nó đã truy vấn DB.

## 36. Exception translation của Spring có thể thay đổi type

Trong ứng dụng Spring, JPA provider exceptions có thể được Spring DAO layer dịch thành exception khác, ví dụ một dạng object retrieval failure.

Vì vậy:

```java
catch (EntityNotFoundException ex)
```

ở controller không phải lúc nào cũng bắt đúng exception sau repository proxy/transaction interceptor.

Thực hành:

1. Xác định exception nào Spring đang expose ở boundary.
2. Xem cause chain và class gốc.
3. Map các failure đã biết sang domain/API responses.
4. Không catch toàn bộ `DataAccessException` rồi coi là 404.
5. Xem transaction đã bị rollback-only chưa.
6. Giữ log nội bộ có nguyên nhân đầy đủ.
7. Viết integration test cho handler trên **stack Spring/provider thực tế**.

Một exception translation strategy tốt tách business lookup `findById(...).orElseThrow()` khỏi unexpected dangling references.

## 37. Không nuốt exception trong `@Transactional` rồi commit

Ví dụ nguy hiểm:

```java
@Transactional
public void processOrder(Long orderId) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();

    try {
        order.getCustomer().getDisplayName();
    } catch (EntityNotFoundException ex) {
        // Bỏ qua và tiếp tục.
    }

    anotherRepository.save(...);
}
```

Vì persistence failure có thể đánh dấu transaction rollback-only, transaction manager có thể ném rollback-related error lúc method kết thúc. Ngay cả khi không ném ngay, đơn vị công việc có thể không còn đáng tin để tiếp tục.

Hướng tốt hơn:

- Ném domain/integrity exception ra ngoài transaction.
- Để transaction interceptor rollback.
- Nếu có thể phục hồi, thực hiện việc đó **trong một transaction mới**.
- Không dùng lại entities/proxies từ context thất bại.

Trong Spring, một method được gọi qua `this.method()` nội bộ có thể không đi qua transaction proxy theo proxy-based configuration; vì vậy cần hiểu transaction boundary thật trước khi thiết kế recovery.

## 38. Recovery có nghĩa là gì trong trường hợp entity missing?

Không phải mọi lỗi đều phù hợp retry.

Phân loại nguyên nhân:

| Nguyên nhân | Recovery hợp lý |
| --- | --- |
| Client gửi ID không có | Trả domain validation/not found; yêu cầu chọn ID hợp lệ |
| Customer bị xóa theo nghiệp vụ | Không tạo Order mới; chọn Customer khác hoặc báo conflict |
| Order có FK mồ côi do dữ liệu cũ | Sửa data migration/integrity, không retry vô hạn |
| Replica chưa đồng bộ | Áp dụng read consistency policy, có thể retry có giới hạn theo thiết kế |
| Transaction đang đọc stale state | Rollback, mở context mới, đọc lại current state |
| Sai tenant/schema mapping | Sửa query/mapping/authorization, không retry |
| Hibernate proxy bị dùng sau Session đóng | Sửa fetch/DTO/transaction boundary |
| Database FK violation khi commit | Xác định constraint, xử lý domain conflict, rollback |
| Cấu hình soft-delete khiến liên kết lịch sử không resolve được | Sửa modeling/filter access policy |

**Đừng lập trình `retry(3)` mặc định cho EntityNotFoundException.** Nếu parent đã bị xóa thật, retry không tạo lại row và chỉ tăng tải DB.

## 39. Khi nào retry có giới hạn được xem xét?

Một số hệ thống phân tán có eventual consistency hoặc read replica lag. Một reference có thể chưa resolve được trên replica tại thời điểm đọc nhưng dữ liệu sẽ xuất hiện sau replication delay.

Trong tình huống này cần:

- Bằng chứng về nguyên nhân tạm thời, không chỉ suy đoán.
- Một consistency policy nêu rõ reader có thể stale.
- Bounded retry/backoff hoặc đọc lại primary khi cần.
- Idempotency cho operation có side effects.
- Transaction/context mới cho mỗi attempt sau persistence failure.
- Giới hạn thời gian tổng và timeout.
- Metrics để phát hiện tình trạng kéo dài.
- Trả lỗi rõ nếu dữ liệu vẫn không có.

Ví dụ sơ đồ:

```text
Attempt #1:
  begin new transaction/context
  lookup/reference access
  missing → rollback and close

Check known transient condition (e.g. replica lag policy)
          │
          ├─ không có bằng chứng transient → fail
          └─ có → bounded backoff
                        │
                        ▼
Attempt #2:
  begin NEW transaction/context
  repeat authoritative lookup
```

Không tái sử dụng một EntityManager đã rollback để “thử lại” cùng proxy; không retry vô hạn.

## 40. Soft-delete và hard-delete cần được thiết kế cho lịch sử

Trong hệ thống đơn hàng, xóa cứng Customer có thể phá khả năng tra cứu lịch sử. Những lựa chọn:

1. **Không hard-delete** Customer đang được Order tham chiếu; DB FK mặc định RESTRICT/NO ACTION tùy engine.
2. **Soft-delete** Customer, vẫn giữ row để association hợp lệ; hạn chế dữ liệu hiển thị theo policy.
3. **Snapshot** các thông tin cần lưu bền vững của Customer trong Order tại thời điểm giao dịch.
4. **Tách bảng archive** và xây mapping/query lịch sử có chủ đích.
5. **Cascade deletion** nếu nghiệp vụ thật sự cho phép xóa toàn bộ child; cân nhắc audit/legal retention.
6. **SET NULL** cho optional association nếu nghiệp vụ cho phép Order không còn Customer.
7. **Anonymization** thay xóa row để tuân chính sách dữ liệu mà vẫn giữ integrity.

Không chọn `ON DELETE CASCADE` chỉ để tránh `EntityNotFoundException` nếu nó sẽ xóa cả đơn hàng lịch sử ngoài ý muốn.

## 41. `ON DELETE` trong database khác JPA cascade

Ví dụ FK:

```sql
FOREIGN KEY (customer_id)
REFERENCES customers(id)
ON DELETE CASCADE
```

khi database xóa Customer, DB có thể tự xóa những PurchaseOrders tham chiếu.

Đây không đồng nghĩa:

```java
@ManyToOne(cascade = CascadeType.REMOVE)
private Customer customer;
```

JPA cascade là propagation của **entity lifecycle operations** trong ORM; DB cascade là SQL referential action. Hai cơ chế khác nhau về callback, persistence context, cache và những writer ngoài ORM.

Đặc biệt, **không nên đặt `CascadeType.REMOVE` tùy tiện trên @ManyToOne Customer**: xóa một Order có thể khiến ORM cố xóa Customer dùng chung, tác động các Orders khác. Đây thường là mapping nguy hiểm.

Muốn bảo vệ Order → Customer, thông thường để Customer tồn tại độc lập và dùng FK rõ ràng.

## 42. `ON DELETE SET NULL` có phù hợp không?

Nếu business cho phép Order giữ lại sau khi Customer bị xóa nhưng không còn reference:

```sql
FOREIGN KEY (customer_id)
REFERENCES customers(id)
ON DELETE SET NULL
```

có thể là một cách, với điều kiện cột `customer_id` **cho phép NULL**. Nếu schema định nghĩa `NOT NULL` hoặc mapping `optional = false` theo domain invariant, cần thay đổi mô hình phù hợp trước.

Đừng chọn SET NULL nếu Order bắt buộc có Customer để tính thuế/đối soát. Có thể thay bằng snapshot hoặc archived customer reference.

**Sửa EntityNotFoundException bằng cách chuyển dữ liệu sang null chỉ đúng khi business contract cho phép quan hệ không còn tồn tại.**

## 43. Phòng ngừa orphan khi import/bulk jobs

Một import job có thể bỏ qua JPA mapping:

```sql
INSERT INTO purchase_orders
    (id, version, customer_id, description)
VALUES (1000, 0, 999, 'Imported order');
```

Nếu FK chưa tồn tại, hàng mồ côi có thể được ghi và chỉ gây lỗi khi một application request lazy-load Customer.

Một import pipeline tốt:

- Kiểm tra schema FK trước khi chạy.
- Validate input IDs và normalize.
- Nếu cần, load/validate parent keys theo batch.
- Viết child rows trong DB transaction phù hợp.
- Để FK chặn những IDs không còn hợp lệ do race.
- Lưu rejected rows với reason codes.
- Không tắt FK tùy tiện để tăng tốc.
- Nếu phải tắt constraint cho migration, kiểm tra lại và rebuild/validate trước production traffic.
- Theo dõi số rows orphan sau import.
- Có chính sách xử lý records không map được Customer.

Application pre-check giúp báo lỗi import thân thiện, nhưng **không thay FK**.

## 44. Quy trình sửa dữ liệu mồ côi hiện hữu

Nếu đã có Order #500 trỏ Customer #99 không tồn tại, quy trình thường gồm:

1. **Đóng băng hành động gây lỗi** nếu vẫn đang viết orphan.
2. Truy vấn danh sách orphans theo các joins phù hợp.
3. Đếm số lượng và phân loại nguồn tạo.
4. Đối chiếu audit/backup/source systems.
5. Quyết định business-approved remediation:
   - Khôi phục Customer nếu hợp lệ và đủ dữ liệu.
   - Gắn Order sang Customer đúng đã xác minh.
   - Chuyển sang mô hình archived/snapshot/nullable nếu nghiệp vụ cho phép.
   - Quarantine record để xử lý thủ công nếu không đủ chứng cứ.
6. Chạy migration trong transaction/batch có kiểm soát.
7. Kiểm tra không còn orphans thuộc phạm vi rule.
8. Thêm FK/NOT NULL hoặc nâng cấp constraint.
9. Triển khai application code tương thích.
10. Đặt monitoring để phát hiện nếu lỗi tái diễn.

Không được tự chọn một Customer “default” cho tất cả Orders vì có thể ghép sai dữ liệu giao dịch, phá tenant isolation và vi phạm nghĩa vụ lưu trữ.

## 45. Migration thêm foreign key cần xử lý dữ liệu cũ

Không nên chạy:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id);
```

và mặc định thành công khi schema đã chứa orphans. Nhiều DB sẽ từ chối tạo FK nếu dữ liệu cũ vi phạm.

Trước migration:

```sql
SELECT COUNT(*) AS orphan_count
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

Sau cleanup, thêm FK theo cách phù hợp database. Với bảng lớn, cần kế hoạch online migration, lock duration, constraint validation và rolling deploy. Các khả năng như `NOT VALID`/`VALIDATE CONSTRAINT` là **dialect-specific**; không coi là câu SQL JPA portable.

### Giám sát sau khi triển khai

- Count orphan rows = 0.
- FK constraint thực tồn tại và enabled.
- Số FK violations theo import/service.
- Rate EntityNotFoundException theo entity/association.
- Các endpoints có lỗi data integrity.
- Thời gian lock/timeout khi tạo/xóa parents.
- Sai lệch giữa primary và replicas nếu có.

## 46. Read replica, cache và transaction isolation

Một lỗi reference không resolve được có thể bị ảnh hưởng bởi data visibility:

- **Read replica lag:** row parent mới được ghi ở primary nhưng replica chưa nhận.
- **Transaction isolation:** snapshot có thể không thấy thay đổi từ transaction khác.
- **First-level cache:** EntityManager giữ một entity đã load từ trước.
- **Second-level cache:** shared cache có thể giữ state/identity cũ nếu invalidation không đúng.
- **Tenant schema routing:** parent và child query chạy vào hai schema/tenants khác nhau.
- **Soft-delete filters:** parent vật lý còn nhưng bị lọc khỏi một đường fetch.

Không nên bật `CacheRetrieveMode.BYPASS` rồi kết luận mọi visibility issue sẽ biến mất. Bypass L2 không phá first-level identity map và không sửa replica lag.

Khi điều tra, xác định **database endpoint, transaction, schema, tenant, EntityManagerFactory và cache policy** trước khi đổi mapping.

## 47. Mapping tenant mismatch có thể giống missing row

Giả sử Customer #10 tồn tại trong tenant A, Order thuộc tenant B có `customer_id=10` nhưng query Customer luôn lọc tenant B.

Nếu application chỉ dùng ID toàn cục và FK sai phạm vi, quan hệ có thể:

- Resolve sai Customer của tenant khác.
- Không resolve được vì filter.
- Dẫn tới lỗi bảo mật hoặc EntityNotFoundException.
- Gây khó thêm constraint composite.

Một mô hình multi-tenant cần suy xét:

- IDs toàn cục hay chỉ unique theo tenant?
- FK có bao gồm `tenant_id` không?
- Join columns có trỏ đúng schema không?
- Application service có kiểm tra tenant scope?
- Có DB row-level security phù hợp không?
- Soft-delete/security filters có nhất quán giữa root và association không?

**Đừng trả 404 cho một ID không thuộc quyền chỉ sau khi tùy tiện dereference cross-tenant proxy.** Authorization phải được kiểm soát ở boundary trước khi lộ dữ liệu.

## 48. Dùng DTO projection để tránh dereference không cần thiết

Nếu một màn hình chỉ cần Customer ID của Order, không cần tên Customer, có thể query scalar/DTO:

```java
public record OrderSummary(
    Long id,
    Long customerId,
    String description
) {}
```

Nếu PurchaseOrder mapping có association Customer, JPQL có thể dùng path đến identifier tùy provider semantics, nhưng nếu muốn **đảm bảo chỉ đọc FK column** với mapping/SQL cụ thể, cần kiểm tra generated SQL. Một native/SQL projection có thể rõ hơn trong những trường hợp điều tra dữ liệu legacy:

```sql
SELECT id, customer_id, description
FROM purchase_orders
WHERE id = ?;
```

Điều này có thể cho phép hiển thị thông tin Order cơ bản mà không cần truy vấn Customer row.

Nhưng DTO projection **không tự sửa FK hỏng**. Đây là một lựa chọn chỉ khi business use case thật sự không cần Customer state và API có hợp đồng hiển thị phù hợp.

## 49. Dùng JOIN FETCH có chữa được orphan không?

Ví dụ:

```java
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.id = :id
```

Với inner join, Order có Customer FK mồ côi có thể **không xuất hiện trong result**, vì không có parent row để join.

Đây không phải bằng chứng Order không tồn tại.

Một LEFT JOIN FETCH:

```java
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.customer
WHERE o.id = :id
```

có thể làm cách quan sát khác đi, nhưng behavior mapping với FK invalid vẫn phải được kiểm tra theo provider. **Không dùng join fetch như data integrity repair.** Nó chỉ thay fetch plan/query shape và có thể che rows mồ côi khỏi result nếu dùng inner join.

Khi chẩn đoán, SQL LEFT JOIN + `WHERE c.id IS NULL` là công cụ chính xác hơn để tìm orphan.

## 50. Một API “tự phục hồi” không nên làm gì?

Tránh các cách xử lý tưởng nhanh:

- Catch `EntityNotFoundException` rồi silently return `null` cho mọi association.
- Tự động tạo Customer placeholder ở ID thiếu.
- Bật Hibernate `@NotFound(IGNORE)` trên toàn bộ domain model.
- Xóa Order mồ côi không qua phê duyệt nghiệp vụ.
- Retry vô hạn trong cùng transaction.
- Bỏ database foreign keys để giảm exception.
- Tắt optimistic locking khi thấy lỗi retrieval.
- Trả raw stack trace cho client.
- Dùng `EntityManager.clear()` để “sửa DB”.
- Coi `getReference(...) != null` là existence check.
- Chuyển mọi lỗi reference thành HTTP 404 của resource root.
- Gửi success event/email trước khi transaction được commit.

Phục hồi đúng không chỉ là ngăn exception xuất hiện; nó phải **giữ đúng dữ liệu, business semantics và khả năng điều tra lỗi**.

---

## 51. Kiểm thử cơ bản: `find()` trả null nếu row không tồn tại

Một test JUnit 5 đơn giản với `EntityManagerFactory emf` đã cấu hình:

```java
@Test
void findReturnsNullForMissingCustomer() {
    Long missingId = chooseNonexistentCustomerId();

    EntityManager em = emf.createEntityManager();

    try {
        Customer found = em.find(
            Customer.class,
            missingId
        );

        assertNull(found);
    } finally {
        em.close();
    }
}
```

`chooseNonexistentCustomerId` phải là helper chọn ID chắc chắn không tồn tại trong fixture, không chỉ hardcode một số tùy ý rồi hy vọng database không dùng.

Test chứng minh **lookup semantics của find** trong test context. Nó chưa chứng minh transaction khác không thể tạo Customer cùng ID ngay sau thời điểm find.

## 52. Kiểm thử quan trọng: `getReference()` với ID không tồn tại

Do thời điểm ném exception có thể là lúc gọi `getReference` hoặc khi truy cập state, test nên bao cả hai:

```java
@Test
void getReferenceThrowsWhenMissingEntityStateIsNeeded() {
    Long missingId = chooseNonexistentCustomerId();

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        assertThrows(
            EntityNotFoundException.class,
            () -> {
                Customer reference = em.getReference(
                    Customer.class,
                    missingId
                );

                // Buộc truy cập state, thay vì chỉ so sánh
                // reference != null hoặc lấy ID.
                reference.getDisplayName();
            }
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
```

Test mục tiêu Jakarta Persistence `EntityNotFoundException`. Với provider/framework có wrapping hoặc translation, cần xác minh root cause đúng thay vì chấp nhận mọi RuntimeException.

Không nên viết test chỉ:

```java
Customer ref = em.getReference(Customer.class, missingId);
assertNotNull(ref);
```

rồi kết luận ref có row hợp lệ. Reference có thể được tạo mà chưa hề SELECT.

## 53. Kiểm thử trong transaction mới sau exception

Một test recovery:

```java
@Test
void failedReferenceAccessDoesNotCorruptCommittedData() {
    Long existingId = seedAndCommitCustomer();
    Long missingId = chooseNonexistentCustomerId();

    EntityManager failing = emf.createEntityManager();

    try {
        failing.getTransaction().begin();

        assertThrows(
            EntityNotFoundException.class,
            () -> failing.getReference(
                Customer.class,
                missingId
            ).getDisplayName()
        );
    } finally {
        if (failing.getTransaction().isActive()) {
            failing.getTransaction().rollback();
        }
        failing.close();
    }

    EntityManager fresh = emf.createEntityManager();

    try {
        Customer existing = fresh.find(
            Customer.class,
            existingId
        );

        assertNotNull(existing);
    } finally {
        fresh.close();
    }
}
```

`seedAndCommitCustomer` là fixture helper tạo Customer trong transaction hoàn tất. Test chứng minh sau khi transaction lỗi được rollback/đóng, thao tác tra cứu khác có thể được thực hiện trên context mới.

Không tái sử dụng `failing` sau exception để đánh giá DB state.

## 54. Tạo fixture dữ liệu orphan có kiểm soát

Để test lazy association trỏ tới row thiếu, database **có FK đúng sẽ không cho tạo dữ liệu mồ côi**. Đừng phá schema production để tạo fixture.

Một trong các lựa chọn test:

1. Test riêng trên một schema/fixture **cố ý không có FK**, mô phỏng legacy DB.
2. Tạo một bảng thử nghiệm không có FK, map entity test chuyên dụng.
3. Dùng migration fixture được kiểm soát trên disposable database.
4. Nếu database có cách tạm disable constraint cho migration, chỉ dùng trong một test DB cô lập, sau đó restore/validate; tránh nếu không cần.
5. Dùng `getReference` với ID thiếu để test cơ chế EntityNotFound **mà không cần orphan row**.

Một fixture schema legacy:

```sql
-- Chỉ dùng trong disposable test database cố ý thiếu FK.
CREATE TABLE legacy_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    description VARCHAR(250) NOT NULL
);

INSERT INTO legacy_orders (
    id, customer_id, description
)
VALUES (
    500, 999, 'Legacy order with broken reference'
);
```

Để test thực tế, cần mapping `LegacyOrder` tới bảng này và association tới Customer, cùng ID strategy/schema thích hợp. Không nên dùng cùng production `purchase_orders` rồi drop FK trên database thật.

## 55. Integration test lazy association bị đứt

Với fixture legacy có Order #500 → Customer #999 không tồn tại:

```java
@Test
void accessingBrokenLazyAssociationFails() {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        LegacyOrder order = em.find(
            LegacyOrder.class,
            500L
        );

        assertNotNull(order);

        assertThrows(
            EntityNotFoundException.class,
            () -> order.getCustomer()
                .getDisplayName()
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
```

Test giả định:

- `LegacyOrder` có `@ManyToOne(fetch=LAZY)` tương ứng.
- FK column trỏ ID không có Customer.
- Provider hỗ trợ lazy association và ném exception như mục tiêu trên stack đó.
- Không có provider-specific `@NotFound(IGNORE)` hoặc một filter thay đổi behavior.
- Không có stale object trong L1/L2 từ fixture khác.

Nếu provider khởi tạo association sớm hoặc ném lúc load Order, assertion boundary có thể cần bao cả `find` và navigation. Để kiểm tra portable **“invalid relation bị phát hiện”**, bao trọn thao tác; để kiểm tra **đúng timing lazy dereference**, cần stack-specific test.

## 56. Test database FK bằng JDBC trực tiếp

Để chứng minh schema được bảo vệ, test nên cố tạo Order trỏ Customer thiếu qua JDBC:

```java
@Test
void databaseRejectsDanglingForeignKey() {
    Long missingId = chooseNonexistentCustomerId();

    assertThrows(SQLException.class, () -> {
        try (Connection connection =
                 dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(
                     "INSERT INTO purchase_orders " +
                     "(id, version, customer_id, description) " +
                     "VALUES (?, ?, ?, ?)"
                 )) {

            statement.setLong(1, nextOrderId());
            statement.setLong(2, 0L);
            statement.setLong(3, missingId);
            statement.setString(4, "Invalid customer");
            statement.executeUpdate();
        }
    });
}
```

Test minh họa cho database có FK check ngay khi INSERT và connection autocommit phù hợp. Với **deferrable FK constraints**, có thể cần commit để DB báo lỗi; với transaction do test quản lý cần rollback/cleanup thích hợp.

Test này **không** kiểm tra EntityNotFoundException; nó kiểm tra lớp phòng vệ khác: DB từ chối orphan trước khi dữ liệu được commit.

Cả hai tests quan trọng nếu hệ thống cần tương thích legacy DB và đồng thời ngăn tạo orphan mới.

## 57. Test Spring Data: `getReferenceById` khác `findById`

Ví dụ:

```java
@Test
@Transactional
void referenceByIdMayFailWhenAccessed() {
    Long missingId = chooseNonexistentCustomerId();

    assertThrows(
        EntityNotFoundException.class,
        () -> customerRepository
            .getReferenceById(missingId)
            .getDisplayName()
    );
}
```

Ở Spring, exception được translation/wrapping tùy provider/repository layer, nên test cần điều chỉnh loại exception mong đợi theo stack. Ngoài ra, `@Transactional` test có thể rollback sau test, nên không coi nó là kiểm thử commit/constraint đã được xác nhận.

Test khác:

```java
@Test
void findByIdReportsMissingAsOptionalEmpty() {
    Long missingId = chooseNonexistentCustomerId();

    assertTrue(
        customerRepository.findById(missingId)
            .isEmpty()
    );
}
```

Hai test giúp team đọc method names và không dùng `getReferenceById` để kiểm tra tồn tại.

## 58. Kiểm thử concurrency: Customer bị xóa sau khi tìm

Một test đúng cần **hai transactions độc lập** và một database có locking/FK semantics tương đương production.

Ví dụ schedule:

```text
Transaction A                 Transaction B
      │                             │
Find Customer #10                   │
      │                          Try delete #10
      │                             │
Persist Order -> Customer #10       │
      │                             │
Flush / Commit                      │
      │                             │
                        Commit delete or conflict
      └───────────────┬─────────────┘
                      ▼
          DB referential integrity
          must remain valid
```

Kết quả có thể là A commit và B delete bị FK từ chối, B delete trước và A insert bị FK từ chối, hoặc một transaction chờ/timeout theo isolation và scheduling.

**Không nên assert một exception class/timing tuyệt đối cho mọi DB**, mà assert bất biến cuối:

- Không có committed Order trỏ Customer không tồn tại.
- Một transaction có thể bị từ chối hợp lệ.
- Error mapping không coi dữ liệu đã lưu khi transaction rollback.
- Test dùng hai EntityManagers/connections riêng, không share một EntityManager giữa threads.

Dùng `CountDownLatch`/`ExecutorService` để điều khiển thứ tự, tránh `Thread.sleep` làm test flaky.

## 59. Khi xóa parent đang có child

Giả sử:

```text
Customer #10
 └─ PurchaseOrder #500 (customer_id=10)
```

Nếu DB FK mặc định không cho xóa parent khi còn child, thao tác:

```sql
DELETE FROM customers WHERE id=10;
```

sẽ bị từ chối khi constraint được kiểm tra, trừ khi referential action/migration cho phép cách xử lý khác.

Đây thường là **hành vi mong muốn** nếu Order phải được giữ để đối soát.

Ở JPA, nếu gọi:

```java
em.remove(customer);
em.flush();
```

lỗi database có thể xuất hiện dưới dạng FK constraint violation, không phải EntityNotFoundException. Đừng catch EntityNotFoundException để xử lý “Customer còn Order không thể xóa”; hãy xử lý referential integrity/business rule phù hợp.

## 60. Cấu trúc logging khi phát hiện broken reference

Một log hữu ích có thể ghi:

```text
event=JPA_DANGLING_REFERENCE
root_entity=PurchaseOrder
root_id=500
association=customer
target_entity=Customer
target_id=999
transaction_correlation_id=...
tenant_id=...
root_cause=EntityNotFoundException
```

Chỉ log những fields được phép; không ghi raw Customer PII hoặc dữ liệu thẻ thanh toán.

Các thông tin cần chẩn đoán:

1. Entity/association gây lỗi.
2. Identity của root và target (nếu có quyền log).
3. Query/use case và transaction boundary.
4. ID do client nhập hay đến từ FK lưu trong DB?
5. Database/schema/tenant/replica đang đọc.
6. Có L1/L2 cache hoặc soft-delete filter không?
7. Có migration/import/batch chạy gần thời điểm lỗi không?
8. Actual SQL đã phát tại mốc exception.
9. Error cause chain qua ORM/Spring.
10. Transaction đã rollback và connection được trả về pool chưa?

Không dựa vào việc đoán nguyên nhân chỉ từ một câu “Unable to find entity with id …”.

## 61. Đo và cảnh báo lỗi tham chiếu trong production

Có thể thêm metrics:

- `entity_not_found_total` theo entity type/association.
- `dangling_fk_rows` từ data-quality job.
- `fk_violation_total` theo constraint.
- Rate 404 của client input không tồn tại.
- Rate 500 do unexpected broken relation.
- Import rejection count.
- Retry attempts do replica lag policy.
- Số errors theo tenant/schema/provider version.
- Time-to-remediate của integrity incidents.

Quan trọng là **không gộp 404 hợp lệ do người dùng tìm ID không có với lỗi data integrity thật**; nếu gộp, hệ thống rất khó phát hiện một migration đang tạo orphan rows.

Đối với dữ liệu mồ côi, một cảnh báo có thể chủ động quét SQL LEFT JOIN theo lịch với giới hạn tải và báo phát hiện để dừng nguồn tạo dữ liệu lỗi.

## 62. Bài tập 1: Nhận diện lỗi ở `getReference`

```java
Customer c = em.getReference(
    Customer.class, 999L
);

System.out.println(c != null);
```

**Câu hỏi:** In `true` có chứng minh Customer #999 tồn tại không?

**Đáp án:** Không. Reference có thể được tạo mà chưa kiểm tra row. Truy cập state có thể ném `EntityNotFoundException`, và provider có thể chọn ném sớm tại `getReference`.

## 63. Bài tập 2: Chọn API để trả 404 chủ động

Một GET endpoint cần tìm Customer bằng ID và trả 404 nếu thiếu.

**Gợi ý:** `em.find(Customer.class, id)` rồi kiểm tra `null`, hoặc Spring `findById(id).orElseThrow(...)`. Không dùng `getReference` làm existence check.

## 64. Bài tập 3: Tạo Order bằng proxy

```java
Customer c = em.getReference(Customer.class, 999L);
PurchaseOrder o = new PurchaseOrder(500L, c, "Test");
em.persist(o);
em.flush();
```

DB có FK Customer.

**Câu hỏi:** Chắc chắn nhận `EntityNotFoundException` ở flush không?

**Đáp án:** Không. Nếu provider chỉ dùng ID 999 khi INSERT, DB có thể từ chối bằng FK constraint violation. `EntityNotFoundException` thường liên quan việc resolve entity state, không phải mọi FK insert failures.

## 65. Bài tập 4: Quan hệ lazy bị đứt

Order #500 có `customer_id=999`, DB không có Customer #999.

**Câu hỏi:** Vì sao `order.getCustomer()` có thể chưa ném, nhưng `getDisplayName()` ném?

**Đáp án:** Getter association có thể trả proxy; khi đọc persistent state, provider mới phải SELECT Customer và phát hiện thiếu row.

## 66. Bài tập 5: DB NOT NULL và FK

`customer_id BIGINT NOT NULL`, nhưng thiếu FOREIGN KEY.

**Câu hỏi:** Có thể lưu customer_id=999 không?

**Đáp án:** Có nếu SQL engine không có ràng buộc khác chặn. NOT NULL chỉ cấm NULL, không kiểm tra target row.

## 67. Bài tập 6: Phân biệt lỗi

Một request load Order thành công, khi serializer lấy customer.name thì ném `LazyInitializationException`.

**Câu hỏi:** Có cần sửa Customer missing không?

**Đáp án:** Chưa thể kết luận row thiếu. Đây thường là vấn đề truy cập lazy state ngoài Hibernate Session; sửa fetch/DTO/transaction boundary trước.

## 68. Bài tập 7: Wrong HTTP status

GET `/orders/500`: Order tồn tại nhưng FK customer trỏ ID không có.

**Câu hỏi:** Có nên trả 404 “Order not found” không?

**Đáp án:** Không. Root resource tồn tại; đây là lỗi integrity/association. Phân loại và xử lý theo API/data remediation policy, không che lỗi.

## 69. Bài tập 8: Rollback-only

Catch `EntityNotFoundException` trong transaction rồi tiếp tục persist một entity mới.

**Câu hỏi:** Có an toàn không?

**Đáp án:** Không nên. Persistence failure có thể đánh dấu rollback-only. Rollback, đóng context, rồi tạo transaction mới nếu cần phục hồi.

## 70. Bài tập 9: Retry

Customer #999 đã bị hard-delete thật.

**Câu hỏi:** Retry getReference 100 lần có giúp không?

**Đáp án:** Không. Cần sửa ID/business flow hoặc integrity; chỉ retry có giới hạn khi có bằng chứng nguyên nhân tạm thời như replica lag.

## 71. Bài tập 10: Tìm orphans

Viết SQL phát hiện Orders có Customer FK không tồn tại.

**Đáp án gợi ý:**

```sql
SELECT o.id, o.customer_id
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
```

## 72. Bài tập 11: Xóa Customer

Một Customer có nhiều Orders cần lưu để đối soát.

**Câu hỏi:** Nên thêm `ON DELETE CASCADE` để không còn lỗi reference?

**Đáp án:** Thường không. Cascade có thể xóa Orders lịch sử ngoài ý muốn. Cần chính sách không xóa, soft-delete, anonymization hoặc snapshot phù hợp.

## 73. Bài tập 12: Soft delete

Customer row còn trong DB, nhưng filter active-only làm lazy association không resolve.

**Câu hỏi:** Có phải chắc chắn là FK hỏng vật lý không?

**Đáp án:** Không. Cần kiểm tra filters/tenant visibility và mapping. Thiết kế đường đọc lịch sử riêng khi cần.

## 74. Bài tập 13: Spring Data JPA

`repository.getReferenceById(id)` trả object không null.

**Câu hỏi:** Method có xác nhận row tồn tại chưa?

**Đáp án:** Không có bảo đảm như vậy. Với input chưa tin cậy, dùng `findById` và xử lý `Optional.empty`.

## 75. Bài tập 14: L1 stale state

Customer đã được quản lý trong EntityManager A; EntityManager B xóa row và commit.

**Câu hỏi:** `emA.find(Customer.class,id)` lần nữa chắc chắn đọc DB không?

**Đáp án:** Không. L1 có thể trả managed object cũ. Dùng context mới/refresh theo policy nếu cần committed state mới.

## 76. Bài tập 15: Kiểm thử thật

Một unit test mock `EntityManager.getReference` trả Customer giả.

**Câu hỏi:** Test này có chứng minh `EntityNotFoundException` khi row thiếu không?

**Đáp án:** Không. Cần JPA provider + database integration test, không chỉ Mockito mock.

## 77. Bài tập 16: Hai giao dịch đồng thời

A tìm thấy Customer, B xóa Customer, A tạo Order trỏ Customer.

**Câu hỏi:** Bước find có đủ để tránh orphan không?

**Đáp án:** Không. DB FK/transaction locking/invariant mới bảo vệ khi races xảy ra.

## 78. Bài tập 17: Mapping và production schema

Java khai báo `@JoinColumn(nullable=false)` nhưng DB migration không có FK.

**Câu hỏi:** Có chắc reference hợp lệ không?

**Đáp án:** Không. Mapping metadata và DB referential constraint là hai lớp khác nhau. Phải kiểm tra schema đang chạy.

## 79. Bài tập 18: HTTP input ID sai

Client gửi `customerId=999` trong CreateOrderRequest, ID không có.

**Câu hỏi:** Nên trả lỗi ở đâu?

**Đáp án:** Application service xác minh Customer, chuyển thành domain error, API map 404/400/422 theo contract. FK vẫn cần cho race/external writers.

## 80. Bài tập 19: `@NotFound(IGNORE)`

Hibernate `@NotFound(IGNORE)` làm association trở thành null khi target thiếu.

**Câu hỏi:** Nó có sửa dữ liệu mồ côi không?

**Đáp án:** Không. Đây là vendor extension có thể che lỗi và thay fetching behavior. Cần remediation và policy rõ.

## 81. Bài tập 20: DTO thay entity serialization

Controller trả trực tiếp PurchaseOrder, serializer truy cập lazy Customer và lỗi.

**Câu hỏi:** Thay đổi thiết kế nào phù hợp?

**Đáp án:** Service load/projection dữ liệu cần thiết trong transaction rồi trả OrderView DTO. Phân loại missing association ở service, không đợi serializer.

## 82. Bài tập 21: Parent bị xóa

`em.remove(customer)` thất bại do FK constraint đang giữ Orders.

**Câu hỏi:** Có phải `EntityNotFoundException` không?

**Đáp án:** Không nhất thiết; đây thường là DB referential-integrity violation. Xử lý rule xóa Customer có Orders.

## 83. Bài tập 22: Refetch sau rollback

Transaction lỗi tạo proxy ID=999 và bị rollback.

**Câu hỏi:** Có nên tiếp tục đọc proxy cũ trong request tiếp theo không?

**Đáp án:** Không. Mở transaction/context mới, tải lại state nếu cần, không tái sử dụng proxy từ context thất bại.

## 84. Bài tập 23: Cần tạo placeholder Customer?

Import Order thiếu Customer nhưng có email/tên không rõ thuộc tài khoản nào.

**Câu hỏi:** Có nên tự tạo Customer #999 cho đủ FK?

**Đáp án:** Không khi chưa xác minh identity. Quarantine Order, đối chiếu source/audit và xử lý theo business-approved remediation.

## 85. Bài tập 24: SQL inner join

`SELECT o FROM PurchaseOrder o JOIN FETCH o.customer` không trả một Order legacy có FK mồ côi.

**Câu hỏi:** Có chứng minh Order không tồn tại không?

**Đáp án:** Không. Inner join có thể loại row không có parent. Dùng direct order lookup/LEFT JOIN diagnostic SQL để xác minh orphan.

## 86. Bài tập 25: Recovery plan

**Yêu cầu:** Hệ thống báo `EntityNotFoundException` liên tục ở `PurchaseOrder.customer` sau một đợt import.

**Gợi ý giải quyết:** Thu thập IDs và transaction context, kiểm tra FK/schema, chạy orphan query, xác định import source, ngăn thêm orphan, làm sạch theo business policy, thêm/validate FK, sửa import writer, integration test JDBC + JPA lazy access, giám sát lỗi sau deploy. Không chỉ thêm catch trả null.

---

## 87. Checklist chẩn đoán và xử lý trên production

Khi gặp `EntityNotFoundException`:

1. Xác định exception gốc là `jakarta.persistence.EntityNotFoundException` hay wrapper/provider exception chưa?
2. Nó phát tại `getReference`, property getter, `refresh`, query, serializer hay flush?
3. Có gọi `find` trên root entity trước đó không?
4. ID thiếu do client gửi hay đã tồn tại trong foreign key của một row khác?
5. Entity root có tồn tại không, hay chỉ association target không tồn tại?
6. Mapping có `@ManyToOne(fetch = LAZY)` hoặc `@OneToOne` lazy không?
7. Có dùng Spring `getReferenceById` như phép kiểm tra tồn tại không?
8. Có phân biệt `NoResultException`, `LazyInitializationException`, `OptimisticLockException` và FK constraint violation không?
9. Persistence context đang managed/detached/closed ở thời điểm lỗi?
10. Transaction đã bị đánh dấu rollback-only chưa?
11. Đã rollback và đóng EntityManager đúng quyền sở hữu chưa?
12. Có đang tiếp tục dùng proxy sau rollback hoặc sau EntityManager close không?
13. Có foreign key thật trong schema production không?
14. FK có đang enabled/validated hay bị disable khi import không?
15. Có dữ liệu legacy mồ côi do external writers không?
16. Có `NOT NULL` nhưng thiếu `FOREIGN KEY` không?
17. FK có scope đúng tenant/schema/partition không?
18. Có soft-delete filter làm target không resolve không?
19. Có đọc từ replica lag hoặc cache stale không?
20. Có dùng `@NotFound(IGNORE)` che dữ liệu invalid không?
21. Có SQL LEFT JOIN diagnostic query để liệt kê orphans không?
22. Có business-approved remediation cho từng loại orphan không?
23. Có tránh tự gán ID placeholder vào Customer khác không?
24. Có fix đường tạo orphan trong JDBC/native/bulk import không?
25. Có transaction/locking/versioning policy cho parent deletion race không?
26. API có trả đúng 404 cho missing root nhưng không che orphan association không?
27. Có DTO projection để tránh lazy access trong JSON serializer không?
28. Có exception translation/cause chain phù hợp Spring/provider không?
29. Có integration test `getReference` tới missing row không?
30. Có integration test lazy association tới orphan trong fixture cô lập không?
31. Có JDBC FK constraint test dùng schema thật không?
32. Có concurrency test parent delete vs child insert không?
33. Có readback dữ liệu committed bằng context mới sau rollback không?
34. Có monitoring tách client 404 và unexpected broken FK không?
35. Có kiểm tra schema migration/cleanup trước khi thêm FK không?
36. Có chính sách xóa/ẩn danh Customer mà không phá Order history không?
37. Có tránh gọi network side effects khi unit of work chưa commit không?
38. Có tránh retry vô hạn một missing entity thật không?
39. Có bảo vệ thông tin tenant/PII trong log và error response không?
40. Có tài liệu hóa identity/fetch/recovery conventions để các code paths dùng nhất quán không?

Checklist giúp tách ba nhóm quyết định:

- **Giải quyết request hiện tại:** xác định ID bị thiếu, trả lỗi domain hay integrity đúng nghĩa.
- **Đảm bảo transaction:** rollback/context mới, không tiếp tục unit of work lỗi.
- **Sửa hệ thống tận gốc:** FK, migration, import, soft-delete, concurrency và monitoring.

## Kết luận

**`EntityNotFoundException` là tín hiệu một entity/reference mà JPA cần resolve không còn hợp lệ hoặc không tìm thấy ở thời điểm tải state.** Nó đặc biệt dễ gặp khi dùng `getReference()` và lazy associations vì **Java reference có thể tồn tại trước khi database row được kiểm tra**.

Những nguyên tắc cần nhớ:

- `EntityManager.find()` thường trả `null` cho ID không có; `getReference()` có thể trì hoãn kiểm tra và ném `EntityNotFoundException` lúc gọi hoặc khi truy cập state.
- `getReferenceById()` của Spring Data JPA cũng không phải một existence check đáng tin.
- Một Order có FK tới Customer bị thiếu không đồng nghĩa Order không tồn tại; không tự map thành HTTP 404 của Order.
- Đừng nhầm `EntityNotFoundException` với `NoResultException`, Hibernate `LazyInitializationException`, `OptimisticLockException` hoặc database FK violation.
- Sau persistence failure, transaction có thể rollback-only. **Rollback, đóng context, và dùng transaction mới để phục hồi hoặc đọc lại**, thay vì nuốt exception rồi tiếp tục.
- **Database foreign key thật** là lớp phòng vệ chính chống references mồ côi do nhiều writers và races; JPA mapping annotations không tự chứng minh production schema đã có FK.
- Khi có orphan, cần chẩn đoán bằng SQL, xác định nguồn tạo lỗi và sửa dữ liệu theo nghiệp vụ; `@NotFound(IGNORE)` không phải cách sửa integrity mặc định.
- Soft-delete, cache, replica lag, tenant filters và serialization có thể ảnh hưởng việc resolve; phải kiểm tra đúng bối cảnh.
- Integration test cần JPA provider, database, transaction và contexts độc lập, không chỉ mock `getReference`.

Bốn câu hỏi quan trọng khi xử lý là: **“Tham chiếu này đến từ đâu? Row thực sự thiếu hay chỉ không nhìn thấy được? Transaction hiện tại còn an toàn để tiếp tục không? Và ràng buộc nào sẽ ngăn lỗi tương tự được commit lần sau?”**. Trả lời rõ sẽ giúp xử lý `EntityNotFoundException` như **một vấn đề về identity, lifecycle, integrity và phục hồi**, thay vì chỉ thêm `try/catch` để che đi một tham chiếu không còn hợp lệ.
