# Trả về một kết quả, kết quả tùy chọn hoặc danh sách và xử lý số lượng không phù hợp trong Hibernate ORM

Một truy vấn Hibernate có thể trả **không có bản ghi**, **đúng một bản ghi**, hoặc **nhiều bản ghi**. Ba trường hợp này trông đơn giản, nhưng lựa chọn API lấy kết quả sẽ quyết định cách chương trình phát hiện lỗi dữ liệu, báo “không tìm thấy”, kiểm soát tính duy nhất, phân trang và xây dựng hợp đồng cho tầng service.

Giả sử hệ thống quản lý khách hàng theo tenant:

- Tìm khách hàng theo ID: dữ liệu có thể tồn tại hoặc không.
- Tìm khách hàng theo email đã được bảo đảm duy nhất trong tenant: mong muốn tối đa một kết quả.
- Tìm khách hàng theo tên gần đúng: có thể có nhiều kết quả.
- Lấy đơn hàng mới nhất của một khách hàng: cần **một phần tử đầu tiên theo thứ tự đã xác định**, không phải khẳng định chỉ có một đơn hàng.
- Đếm tổng số đơn hàng để phân trang: query tổng hợp `count` có quy tắc trả kết quả khác query lấy entity.

Jakarta Persistence và Hibernate cung cấp nhiều cách nhận kết quả:

- `getResultList()`: trả danh sách, thường là danh sách rỗng khi không có kết quả.
- `getSingleResult()`: yêu cầu đúng một kết quả; ném `NoResultException` khi không có, và `NonUniqueResultException` khi có nhiều.
- `getSingleResultOrNull()`: ở những phiên bản Jakarta Persistence hỗ trợ, trả `null` khi không có nhưng vẫn báo lỗi nếu có nhiều.
- `uniqueResult()` / `uniqueResultOptional()`: API native Hibernate cho kết quả đơn nhất, với semantics và hỗ trợ phụ thuộc phiên bản.
- `Optional<T>`, `List<T>`, `Page<T>`, `Slice<T>`: những hợp đồng thường dùng trong tầng repository/service, đặc biệt khi tích hợp Spring Data JPA.

Bài học tập trung vào **cardinality — số lượng kết quả mà một truy vấn được phép trả về**. Hãy xác định cardinality theo nghiệp vụ trước, sau đó chọn API phản ánh nó. Tránh bắt exception để che dữ liệu trùng, tránh `setMaxResults(1)` khi lẽ ra phải xác minh tính duy nhất, và tránh lấy `list.size()` làm tổng số phần tử của toàn bộ kết quả phân trang.

---

## 1. Cardinality là một phần của hợp đồng truy vấn

Có thể phân loại yêu cầu thành bốn nhóm:

| Hợp đồng nghiệp vụ | Số kết quả hợp lệ | Ví dụ | Kết quả nên biểu diễn |
|---|---:|---|---|
| **Bắt buộc đúng một** | 1 | Chi tiết thực thể bắt buộc tồn tại ở bước tiếp theo | Entity/DTO hoặc exception nghiệp vụ khi không có |
| **Có hoặc không, nhưng không được trùng** | 0 hoặc 1 | Tìm tài khoản theo khóa duy nhất | `Optional<T>` hoặc nullable result |
| **Có thể có nhiều** | 0 đến N | Danh sách đơn hàng của khách | `List<T>`, `Page<T>`, `Slice<T>` |
| **Chọn một phần tử theo thứ tự** | 0 hoặc 1 **được chọn từ N** | Đơn hàng mới nhất | Query có `ORDER BY` và giới hạn kết quả |

Nhóm thứ hai và nhóm thứ tư không giống nhau.

Ví dụ một người có 10 đơn hàng:

- “Đơn hàng của người này có duy nhất không?” → câu trả lời là **không**.
- “Đơn hàng mới nhất của người này là gì?” → vẫn có thể trả **một** đơn hàng hợp lệ sau khi sắp xếp.

Nếu dùng query lấy “một phần tử đầu tiên” để thay thế kiểm tra uniqueness, ứng dụng có thể che giấu dữ liệu trùng mà lẽ ra phải được phát hiện.

### 1.1. Sơ đồ quyết định

```text
Use case cần kết quả gì?
            |
      +-----+-------------------------+
      |                               |
Cần đúng một?                    Có thể có nhiều?
      |                               |
      v                               v
  getSingleResult()               getResultList()
      |                          hoặc Page / Slice
      |
      +-- 0 bản ghi -> Not found (NoResultException)
      +-- 1 bản ghi -> OK
      +-- >1 bản ghi -> Cardinality violation

Nếu 0 hoặc 1 đều hợp lệ:
      getSingleResultOrNull() (API hỗ trợ)
      hoặc uniqueResultOptional()
      hoặc helper đọc tối đa 2 hàng

Nếu chọn bản ghi mới nhất trong nhiều bản ghi:
      ORDER BY cố định + setMaxResults(1)
      rồi xử lý danh sách rỗng / một phần tử
```

### 1.2. Cardinality có thể khác giữa các use case của cùng entity

`Customer` là một entity, nhưng các truy vấn không có chung hợp đồng:

```java
findById(id);                // 0..1 theo primary key
findByEmailAndTenant(...);   // Mong muốn 0..1
findByNameContaining(...);   // 0..N
findNewestActiveCustomer();  // Lấy 1 từ tập có thể nhiều
countActiveCustomers();      // Một giá trị COUNT
```

Không nên dùng cùng một phương thức tiện ích “lấy kết quả đầu tiên” cho mọi trường hợp.

## 2. Mô hình entity minh họa

Ví dụ hệ thống CRM đa tenant, với khách hàng và đơn hàng:

```java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_normalized_email",
        columnNames = {"tenant_id", "normalized_email"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "normalized_email", nullable = false)
    private String normalizedEmail;

    @Column(nullable = false)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public UUID getTenantId() {
        return tenantId;
    }

    public String getNormalizedEmail() {
        return normalizedEmail;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Entity đơn hàng:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {}

    public UUID getId() {
        return id;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getStatus() {
        return status;
    }
}
```

Giả định bảng `customers` có unique constraint thực sự trên `(tenant_id, normalized_email)` trong database, được quản lý bằng migration hoặc DDL thích hợp. Annotation giúp mô tả ý định mapping nhưng không thay thế việc kiểm chứng schema production.

Mô hình này giúp phân biệt:

- ID là khóa chính, nên tối đa một khách hàng theo ID ở mức database.
- Email phải được chuẩn hóa và kết hợp tenant để bảo đảm uniqueness theo domain.
- Một khách hàng có nhiều đơn hàng, nên query tìm đơn hàng phải trả danh sách hoặc chọn một theo thứ tự.

## 3. getResultList(): hợp đồng cho 0 đến N kết quả

`getResultList()` được dùng khi query có thể trả nhiều dòng:

```java
List<Customer> customers = em.createQuery("""
    select c
    from Customer c
    where c.tenantId = :tenantId
    order by c.displayName, c.id
    """, Customer.class)
    .setParameter("tenantId", tenantId)
    .getResultList();
```

Nếu không có khách hàng phù hợp, kết quả là **danh sách rỗng**, không phải `null`.

Do đó:

```java
if (customers.isEmpty()) {
    // Không có bản ghi phù hợp.
}

for (Customer customer : customers) {
    // Xử lý từng kết quả.
}
```

Không cần viết:

```java
if (customers != null) {
    // Thường là kiểm tra thừa đối với getResultList().
}
```

### 3.1. Tại sao danh sách rỗng tốt hơn null?

Với “tìm nhiều kết quả”, không có dữ liệu thường là một kết quả thành công: “có 0 phần tử”. Danh sách rỗng cho phép:

- Duyệt bằng `for` mà không cần kiểm tra null.
- Chuyển sang DTO dễ dàng.
- Trả JSON `[]` rõ nghĩa.
- Phân biệt query thành công nhưng không có dữ liệu với lỗi truy vấn.

Một repository method có thể trả:

```java
public List<CustomerSummary> findActiveCustomers(UUID tenantId) {
    return em.createQuery("""
        select new com.example.CustomerSummary(c.id, c.displayName)
        from Customer c
        where c.tenantId = :tenantId
        order by c.displayName, c.id
        """, CustomerSummary.class)
        .setParameter("tenantId", tenantId)
        .getResultList();
}
```

Giả sử `CustomerSummary` là record/DTO đã được ứng dụng định nghĩa với constructor tương ứng.

### 3.2. getResultList() không tự giới hạn kích thước

Query có thể trả 100 hoặc 1.000.000 bản ghi. `List<T>` không đồng nghĩa kết quả phù hợp để tải toàn bộ vào bộ nhớ.

Nếu danh sách có thể lớn:

- Dùng pagination với `setFirstResult` và `setMaxResults`.
- Trả `Page` hoặc `Slice` ở tầng Spring Data khi phù hợp.
- Dùng query ID/chunk hoặc streaming có lifecycle Session phù hợp cho xử lý lớn.
- Ưu tiên DTO projection khi chỉ cần một vài cột.

Lựa chọn cardinality 0..N không có nghĩa phải tải tất cả N.

## 4. getSingleResult(): khi yêu cầu đúng một kết quả

Ví dụ tìm khách hàng theo tenant và normalized email:

```java
Customer customer = em.createQuery("""
    select c
    from Customer c
    where c.tenantId = :tenantId
      and c.normalizedEmail = :normalizedEmail
    """, Customer.class)
    .setParameter("tenantId", tenantId)
    .setParameter("normalizedEmail", normalizedEmail)
    .getSingleResult();
```

`getSingleResult()` diễn đạt “query phải có đúng một kết quả”. Thao tác không tự biến mất trường hợp 0 hoặc nhiều kết quả.

### 4.1. Ba kết quả có thể xảy ra

| Số kết quả theo semantics của query | `getSingleResult()` | Ý nghĩa |
|---:|---|---|
| 0 | Ném `NoResultException` | Không tìm thấy |
| 1 | Trả object/scalar | Đúng cardinality |
| Trên 1 | Ném `NonUniqueResultException` | Truy vấn không duy nhất |

Ví dụ xử lý trường hợp không tìm thấy:

```java
import jakarta.persistence.NoResultException;

public Customer requireCustomer(
        UUID tenantId,
        String normalizedEmail) {

    try {
        return em.createQuery("""
            select c
            from Customer c
            where c.tenantId = :tenantId
              and c.normalizedEmail = :email
            """, Customer.class)
            .setParameter("tenantId", tenantId)
            .setParameter("email", normalizedEmail)
            .getSingleResult();
    } catch (NoResultException ex) {
        throw new CustomerNotFoundException(
            tenantId,
            normalizedEmail
        );
    }
}
```

`CustomerNotFoundException` là exception nghiệp vụ do ứng dụng định nghĩa. Không cần bắt `NonUniqueResultException` rồi cũng chuyển thành “không tìm thấy”; đó là một lỗi dữ liệu/điều kiện truy vấn khác.

### 4.2. getSingleResult() không bắt buộc kiểu entity

Có thể lấy một scalar:

```java
String email = em.createQuery("""
    select c.normalizedEmail
    from Customer c
    where c.id = :id
    """, String.class)
    .setParameter("id", customerId)
    .getSingleResult();
```

Hoặc DTO:

```java
CustomerSummary summary = em.createQuery("""
    select new com.example.CustomerSummary(
        c.id, c.displayName
    )
    from Customer c
    where c.id = :id
    """, CustomerSummary.class)
    .setParameter("id", customerId)
    .getSingleResult();
```

Cardinality của **kết quả truy vấn** chứ không chỉ của entity root quyết định hành vi của phương thức.

## 5. NoResultException: không tìm thấy là lỗi hay kết quả hợp lệ?

`NoResultException` là exception của Jakarta Persistence, thường phát sinh từ `getSingleResult()` khi query không trả kết quả.

Điều cần quyết định trước khi code:

- Nếu entity **bắt buộc tồn tại** cho thao tác nghiệp vụ, không tìm thấy là lỗi cần chuyển thành exception phù hợp.
- Nếu tìm kiếm **có thể không tìm thấy**, đừng bắt caller phải dùng exception như đường đi thông thường. Hãy dùng kết quả nullable/Optional.

### 5.1. Trường hợp bắt buộc tồn tại

Ví dụ endpoint lấy chi tiết bằng ID:

```java
public CustomerDetail getRequiredCustomer(Long id) {
    Customer c = em.find(Customer.class, id);

    if (c == null) {
        throw new CustomerNotFoundException(id);
    }

    return toDetail(c);
}
```

Với khóa chính, `EntityManager.find()` trả entity hoặc `null`, nên thường đơn giản hơn JPQL `getSingleResult()`.

### 5.2. Trường hợp không tìm thấy là bình thường

Ví dụ kiểm tra khách hàng đã đăng ký email hay chưa:

```java
Optional<Customer> customer = findByEmail(
    tenantId,
    normalizedEmail
);

if (customer.isPresent()) {
    // Khách hàng đã tồn tại.
} else {
    // Chưa có khách hàng.
}
```

Không cần xem “chưa đăng ký” là exception kỹ thuật.

### 5.3. Exception chính xác còn phụ thuộc API

Không nhầm:

- `EntityManager.find(T.class, id)`: trả `null` nếu không có entity theo primary key.
- `getSingleResult()`: `NoResultException` khi query không có kết quả.
- `getResultList()`: trả empty list khi không có.
- `Optional.empty()`: cách biểu diễn không có dữ liệu trong API Java, không tự nói dữ liệu có duy nhất hay không.

Hợp đồng method nên rõ ràng để caller không phải đoán.

## 6. NonUniqueResultException: nhiều kết quả khi chỉ được phép một

Ví dụ tìm email bằng câu query thiếu `tenantId`:

```java
Customer c = em.createQuery("""
    select c
    from Customer c
    where c.normalizedEmail = :email
    """, Customer.class)
    .setParameter("email", normalizedEmail)
    .getSingleResult();
```

Nếu cùng một email hợp lệ ở nhiều tenant, query có thể trả nhiều Customer và Hibernate/JPA báo `NonUniqueResultException`.

Đây thường không phải “lỗi Hibernate”. Nó cho biết **hợp đồng truy vấn 1 kết quả không khớp tập dữ liệu thực tế**.

### 6.1. Phân loại nguyên nhân

Các lý do thường gặp:

1. WHERE thiếu điều kiện tenant, owner hoặc trạng thái.
2. Database thiếu unique constraint cần thiết.
3. Dữ liệu trùng đã tồn tại do import/migration.
4. Email/username không được chuẩn hóa nhất quán.
5. Join vào collection tạo nhiều dòng kết quả.
6. Query nhóm (`group by`) trả nhiều nhóm.
7. Dữ liệu thật sự cho phép nhiều bản ghi, nhưng method chọn sai hợp đồng.

Cần chẩn đoán lý do trước khi quyết định xử lý.

### 6.2. Không nên bắt lỗi rồi âm thầm lấy phần tử đầu tiên

Ví dụ không nên:

```java
try {
    return query.getSingleResult();
} catch (NonUniqueResultException ex) {
    return query.setMaxResults(1)
                .getResultList()
                .get(0);
}
```

Vấn đề:

- Dữ liệu trùng tiếp tục tồn tại mà không được phát hiện.
- Không có `ORDER BY` ổn định thì “bản ghi đầu tiên” có thể thay đổi.
- Query có thể là truy vấn nghiệp vụ nhạy cảm (tài khoản, quyền, thanh toán).
- Nếu dữ liệu khác tenant, có thể gây lộ hoặc thao tác nhầm dữ liệu.
- Việc thực thi lại query cũng có thể thấy state khác dưới concurrent changes.

Nếu thật sự muốn chọn một phần tử theo một thứ tự, hãy mô hình hóa use case ấy ngay từ đầu. Nếu business key phải duy nhất, hãy sửa điều kiện và ràng buộc dữ liệu.

### 6.3. Exception không thay thế unique constraint

`getSingleResult()` phát hiện nhiều kết quả **khi đọc**; nó không ngăn hai transaction đồng thời insert duplicate trước khi query.

Nếu nghiệp vụ yêu cầu unique, cần unique index/constraint tại database, kết hợp cách chuẩn hóa khóa đúng và xử lý conflict khi insert.

## 7. getSingleResultOrNull(): khi 0 hoặc 1 đều hợp lệ

Các phiên bản Jakarta Persistence mới có API `getSingleResultOrNull()` (ví dụ Jakarta Persistence 3.2); hỗ trợ thực tế cần đối chiếu dependency Jakarta Persistence và provider Hibernate đang dùng.

Ví dụ:

```java
Customer customer = em.createQuery("""
    select c
    from Customer c
    where c.tenantId = :tenantId
      and c.normalizedEmail = :email
    """, Customer.class)
    .setParameter("tenantId", tenantId)
    .setParameter("email", normalizedEmail)
    .getSingleResultOrNull();
```

Semantics mong muốn:

- Không có kết quả → `null`.
- Đúng một kết quả → trả kết quả.
- Nhiều kết quả → vẫn phải báo lỗi cardinality, thường `NonUniqueResultException`.

Đây không phải alias của `setMaxResults(1)`; nó không cho phép bỏ qua dữ liệu trùng.

### 7.1. Chuyển sang Optional

Ở tầng API, có thể đổi:

```java
public Optional<Customer> findByEmail(
        UUID tenantId,
        String email) {

    Customer customer = em.createQuery("""
        select c from Customer c
        where c.tenantId = :tenantId
          and c.normalizedEmail = :email
        """, Customer.class)
        .setParameter("tenantId", tenantId)
        .setParameter("email", email)
        .getSingleResultOrNull();

    return Optional.ofNullable(customer);
}
```

Đây là lựa chọn rõ khi 0..1 hợp lệ và query projection là entity không-null.

### 7.2. Khi project dùng Jakarta Persistence cũ hơn

Nếu API chưa có `getSingleResultOrNull()`, đừng sao chép code mà project không compile. Có thể:

- Dùng `getSingleResult()` và bắt riêng `NoResultException`.
- Dùng Hibernate native `uniqueResultOptional()` nếu version hỗ trợ.
- Dùng query `getResultList()` giới hạn tối đa hai kết quả để kiểm tra cardinality có chủ đích.

Mỗi cách có trade-off về portability, số lần tải và diễn đạt hợp đồng.

## 8. Tạo helper Optional trên API JPA cũ

Một helper thường gặp:

```java
public Optional<Customer> findByEmail(
        UUID tenantId,
        String email) {

    TypedQuery<Customer> query = em.createQuery("""
        select c
        from Customer c
        where c.tenantId = :tenant
          and c.normalizedEmail = :email
        """, Customer.class);

    query.setParameter("tenant", tenantId);
    query.setParameter("email", email);

    try {
        return Optional.of(query.getSingleResult());
    } catch (NoResultException ex) {
        return Optional.empty();
    }
}
```

Quan trọng: **chỉ bắt `NoResultException`** nếu 0 kết quả là tình huống bình thường. Hãy để `NonUniqueResultException` đi lên tầng xử lý lỗi dữ liệu, hoặc chuyển thành exception domain có ý nghĩa nhưng không che mất sự kiện có nhiều bản ghi.

### 8.1. Không bắt PersistenceException tổng quát

Code không nên:

```java
try {
    return Optional.of(query.getSingleResult());
} catch (PersistenceException ex) {
    return Optional.empty();
}
```

Vì `PersistenceException` có thể bao trùm lỗi kết nối, mapping, cú pháp, timeout, constraint, non-unique và nhiều lỗi khác. Chuyển tất cả thành “không tìm thấy” sẽ làm ứng dụng trả dữ liệu sai và che lỗi vận hành.

### 8.2. Không dùng null như mã báo lỗi dữ liệu trùng

`Optional.empty()` có nghĩa “không có giá trị”, không có nghĩa “có hai giá trị nên không biết chọn cái nào”. Nếu query bảo đảm tối đa một mà gặp hai, đó là violation cần xử lý.

## 9. Kiểm tra cardinality bằng danh sách tối đa hai phần tử

Nếu không muốn dùng exception cho 0 kết quả và không phụ thuộc API mới, có thể đọc tối đa **hai** kết quả để phân biệt 0, 1 và ít nhất 2.

```java
public Optional<Customer> findUniqueByEmail(
        UUID tenantId,
        String email) {

    List<Customer> rows = em.createQuery("""
        select c
        from Customer c
        where c.tenantId = :tenant
          and c.normalizedEmail = :email
        """, Customer.class)
        .setParameter("tenant", tenantId)
        .setParameter("email", email)
        .setMaxResults(2)
        .getResultList();

    if (rows.isEmpty()) {
        return Optional.empty();
    }

    if (rows.size() > 1) {
        throw new DuplicateCustomerEmailException(
            tenantId,
            email
        );
    }

    return Optional.of(rows.get(0));
}
```

`DuplicateCustomerEmailException` là kiểu ứng dụng tự định nghĩa.

### 9.1. Vì sao giới hạn hai, không phải một?

Với `setMaxResults(2)`:

- Kết quả rỗng → 0.
- Kết quả có một phần tử → 1.
- Kết quả có hai phần tử → biết đã có **ít nhất hai**, đủ để từ chối uniqueness.

Không cần tải toàn bộ hàng nghìn kết quả chỉ để xác nhận “nhiều hơn một”.

### 9.2. Điều kiện áp dụng

Cách này đáng tin cậy khi **mỗi phần tử kết quả tương ứng một đối tượng logic cần kiểm tra**. Nếu query join một collection và tạo trùng root, hai phần tử kết quả có thể đại diện cho cùng một entity logic.

Hãy thiết kế query trên unique key/ID hoặc `select distinct` theo semantics phù hợp; tránh kết hợp trực tiếp kỹ thuật kiểm tra hai phần tử với collection fetch join và pagination.

### 9.3. Không phải thay thế constraint database

Phép kiểm tra hai kết quả chỉ phát hiện dữ liệu hiện tại khi đọc. Một transaction khác vẫn có thể insert duplicate sau query nếu database không có unique constraint. Đây là công cụ đọc, không phải bảo đảm toàn vẹn dữ liệu khi ghi.

## 10. Hibernate native: uniqueResult() và uniqueResultOptional()

Nếu dùng Hibernate `Session` hoặc API query native, có thể có những phương thức như:

```java
import org.hibernate.Session;
import org.hibernate.query.Query;

Session session = em.unwrap(Session.class);

Query<Customer> query = session.createQuery("""
    select c
    from Customer c
    where c.tenantId = :tenant
      and c.normalizedEmail = :email
    """, Customer.class);

query.setParameter("tenant", tenantId);
query.setParameter("email", email);

Optional<Customer> result = query.uniqueResultOptional();
```

Phương thức Hibernate native thường có ý định:

- Không có kết quả → Optional rỗng.
- Một kết quả đơn nhất → Optional chứa kết quả.
- Nhiều kết quả không duy nhất → exception tương ứng của Hibernate.

`uniqueResult()` là biến thể trả entity hoặc `null` khi không có kết quả trong các API Hibernate hỗ trợ.

### 10.1. Lợi thế và đánh đổi

Lợi thế: diễn đạt trực tiếp 0..1 mà không cần bắt `NoResultException`.

Đánh đổi:

- Phụ thuộc API Hibernate, không portable giữa các JPA provider.
- Tên method, kiểu query và exception cụ thể có thể khác qua các thế hệ Hibernate.
- Không tự áp dụng unique constraint ở database.

Khi ứng dụng chủ động dùng Hibernate, đây có thể là giải pháp phù hợp. Khi muốn giữ portability, ưu tiên Jakarta Persistence API có sẵn trong version mục tiêu hoặc một helper JPA được kiểm soát.

### 10.2. Không nhầm uniqueResultOptional() với firstResult

`uniqueResultOptional()` không có nghĩa “lấy hàng đầu tiên tùy ý”. Nó vẫn diễn đạt yêu cầu một kết quả đơn nhất. Nếu thực sự muốn “gần nhất/mới nhất”, hãy sắp xếp và giới hạn kết quả rõ ràng.

## 11. Spring Data JPA: Optional, List, Page, Slice

Spring Data JPA cho phép biểu đạt hợp đồng lấy kết quả ngay trong kiểu trả về repository.

Ví dụ:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndNormalizedEmail(
        UUID tenantId,
        String normalizedEmail
    );

    List<Customer> findByTenantIdAndDisplayNameContainingIgnoreCase(
        UUID tenantId,
        String text
    );

    Page<Customer> findByTenantId(
        UUID tenantId,
        Pageable pageable
    );
}
```

Hành vi chung:

- `Optional<Customer>`: phù hợp truy vấn mong đợi 0..1.
- `List<Customer>`: 0..N, empty list khi không có.
- `Page<Customer>`: dữ liệu một trang cùng metadata về tổng số phần tử và trang theo cơ chế count.
- `Slice<Customer>`: dữ liệu một lát cắt và chỉ dẫn còn phần tiếp theo, thường không cần tổng count.

### 11.1. Optional không tự chọn một hàng khi trùng

Nếu repository method trả `Optional<Customer>` nhưng query tìm thấy nhiều Customer, Spring Data JPA thường báo lỗi kích thước kết quả (ví dụ `IncorrectResultSizeDataAccessException` sau khi chuyển exception/provider xử lý), chứ không lấy một row ngẫu nhiên.

Tên exception cụ thể có thể phụ thuộc Spring Data version, provider và exception translation.

### 11.2. Derived query có thể mang nhiều nghĩa

`findByEmail(...)` và `findFirstByEmailOrderByCreatedAtDesc(...)` diễn đạt hai hợp đồng khác nhau:

```java
Optional<Customer> findByTenantIdAndNormalizedEmail(
    UUID tenantId,
    String email
);

Optional<Customer> findFirstByTenantIdAndDisplayNameOrderByCreatedAtDescIdDesc(
    UUID tenantId,
    String name
);
```

Method đầu kỳ vọng tối đa một theo business key. Method sau chọn một kết quả được sắp theo thời gian và ID từ tập có thể nhiều.

### 11.3. getById/getReferenceById không phải Optional lookup

Trong Spring Data JPA, một số method dạng `getReferenceById` lấy reference/proxy thay vì bảo đảm entity đã được SELECT để xác minh tồn tại ngay. Việc truy cập proxy không có row có thể gây exception muộn hơn.

Nếu cần xác minh “có hay không” ngay trong use case, `findById` thường thể hiện ý định rõ hơn.

## 12. “Lấy một bản ghi mới nhất” không phải yêu cầu uniqueness

Giả sử người dùng hỏi “đơn hàng gần đây nhất”.

Query:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .setMaxResults(1)
    .getResultList();

Optional<PurchaseOrder> latest =
    orders.stream().findFirst();
```

Ở đây:

- Có thể có 100 đơn hàng.
- Query chỉ **chọn 1 theo thứ tự**.
- `setMaxResults(1)` được dùng có chủ đích.
- Không kết luận rằng customer chỉ có một đơn hàng.

### 12.1. Vì sao cần ORDER BY?

Nếu query chỉ viết:

```java
em.createQuery("""
    select o from PurchaseOrder o
    where o.customer.id = :customerId
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .setMaxResults(1)
    .getResultList();
```

database không có nghĩa vụ chọn cùng một row qua các lần chạy. Khi plan/index/concurrent writes thay đổi, “row đầu tiên” có thể khác.

Nếu tiêu chí là mới nhất, thêm:

```sql
order by o.createdAt desc, o.id desc
```

`id` đóng vai trò tie-breaker khi hai đơn có cùng `createdAt`, tạo thứ tự ổn định hơn. Nếu kiểu ID không phù hợp để định thứ tự nghiệp vụ, chọn một khóa phụ ổn định khác.

### 12.2. Khi nào setMaxResults(1) là sai?

Sai nếu cần:

- Bảo đảm email là duy nhất.
- Kiểm tra có hai active subscriptions cùng lúc.
- Phát hiện duplicate payment reference.
- Bảo vệ quyền sở hữu theo một khóa business key.
- Phát hiện dữ liệu trùng do migration.

Trong các use case ấy, giới hạn 1 có thể che dấu lỗi dữ liệu.

## 13. getSingleResult() kết hợp setMaxResults(1) có ý nghĩa gì?

Ví dụ:

```java
PurchaseOrder latest = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .setMaxResults(1)
    .getSingleResult();
```

Đây là cách lấy một row đã bị giới hạn bởi query. Nó **không còn xác minh tính duy nhất của toàn bộ tập trước khi giới hạn**.

Nếu không có order, `getSingleResult()` vẫn có thể ném `NoResultException`. Nếu có nhiều order, `setMaxResults(1)` khiến result của query bị giới hạn thành một, nên không nên trông chờ `NonUniqueResultException` phát hiện nhiều order ban đầu.

Nếu 0 kết quả hợp lệ, lấy list giới hạn một hoặc phương thức nullable phù hợp sẽ rõ hơn.

### 13.1. Không dùng first-row helper chung cho unique lookup

Có thể tồn tại helper:

```java
public static <T> Optional<T> firstOrEmpty(
        TypedQuery<T> query) {

    List<T> rows =
        query.setMaxResults(1).getResultList();

    return rows.isEmpty()
        ? Optional.empty()
        : Optional.ofNullable(rows.get(0));
}
```

Helper này chỉ hợp với **first-row semantics**. Không nên đặt tên `findUnique` hoặc dùng nó cho email/username khi cần bảo đảm uniqueness.

## 14. Duplicate SQL rows không đồng nghĩa duplicate logical entities

Một nguồn nhầm lẫn lớn là JOIN vào association to-many.

Ví dụ một đơn hàng có ba dòng:

```text
Order#A
  Line#1
  Line#2
  Line#3
```

Query:

```sql
select o
from PurchaseOrder o
join o.lines l
where o.id = :id
```

Ở SQL, database có thể sinh ba hàng vì một order join với ba line.

```text
SQL result:
    order A + line 1
    order A + line 2
    order A + line 3
```

Trong ORM, ba hàng này có thể cùng trỏ về **một identity entity PurchaseOrder#A**.

### 14.1. getResultList() có thể chứa duplicate references

Với một truy vấn join thường, danh sách root results có thể chứa cùng entity nhiều lần theo semantics của query/provider. Nhưng ở Hibernate 6, các truy vấn có **collection JOIN FETCH** được Hibernate xử lý khử trùng root entity results trong memory; hành vi chi tiết còn phụ thuộc query/version.

Do đó, đừng suy luận “ba SQL rows” có nghĩa “ba PurchaseOrder khác nhau”; và cũng đừng suy luận mọi query join trên mọi provider đều tự de-duplicate.

### 14.2. SELECT DISTINCT

Nếu use case cần root entity không trùng:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select distinct o
    from PurchaseOrder o
    join o.lines l
    where l.product.id = :productId
    """, PurchaseOrder.class)
    .setParameter("productId", productId)
    .getResultList();
```

`distinct` nêu ý định chọn root entities duy nhất theo result semantics. SQL và cách ORM xử lý distinct có thể khác theo provider/version và loại projection.

### 14.3. Đừng kết luận lỗi dữ liệu trước khi xem phép JOIN

Một `NonUniqueResultException` khi tìm PurchaseOrder theo ID có thể liên quan query join/selection multiplicity, trong khi bảng `purchase_orders` không có duplicate primary key.

Chẩn đoán cần xác định:

- Query select entity root, tuple hay scalar?
- Join có nhân các hàng không?
- Query có `distinct` hoặc fetch join không?
- Hibernate version xử lý duplicate root như thế nào?
- Có thực sự nhiều entity IDs khác nhau hay không?

### 14.4. Tránh dùng pagination trực tiếp với collection fetch join

`setMaxResults(1)` trên query fetch collection có thể khiến Hibernate phải phân trang trong memory hoặc áp dụng quy tắc đặc biệt; database pagination trên join rows có thể cắt mất các dòng của root.

Nếu cần lấy một order mới nhất **kèm đầy đủ lines**, hãy tách:

1. Query chọn ID của order mới nhất.
2. Query theo ID đó và fetch lines/product theo kế hoạch.
3. Map DTO trong transaction.

## 15. Khi cần xác minh uniqueness của logical root, hãy truy vấn đúng cấp

Ví dụ một customer có nhiều orders; cần tìm customer theo email nhưng query join orders để lọc trạng thái:

```sql
select c
from Customer c
join c.orders o
where c.tenantId = :tenant
  and c.normalizedEmail = :email
  and o.status = 'PAID'
```

Một Customer có ba paid orders có thể sinh nhiều hàng join, dù chỉ một Customer logic. Nếu câu hỏi nghiệp vụ là “customer có paid order hay không?”, dùng `exists` có thể sát ý nghĩa hơn:

```java
Customer customer = em.createQuery("""
    select c
    from Customer c
    where c.tenantId = :tenant
      and c.normalizedEmail = :email
      and exists (
          select 1
          from PurchaseOrder o
          where o.customer = c
            and o.status = 'PAID'
      )
    """, Customer.class)
    .setParameter("tenant", tenantId)
    .setParameter("email", email)
    .getSingleResult();
```

`exists` không nhân root Customer vì các order liên quan. Nếu Customer không có paid order, query không trả kết quả; lựa chọn Optional/no-result tùy use case.

### 15.1. Nếu chỉ cần biết có tồn tại hay không

Không cần tải cả entity:

```java
Long count = em.createQuery("""
    select count(c)
    from Customer c
    where c.tenantId = :tenant
      and c.normalizedEmail = :email
    """, Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("email", email)
    .getSingleResult();

boolean exists = count > 0;
```

Với một số trường hợp, query SELECT ID giới hạn một cũng phù hợp để kiểm tra existence và có thể tiết kiệm hơn count toàn bộ; lựa chọn phải dựa trên index/query plan và semantics. Không cần dùng getSingleResult trên entity chỉ để biết có row hay không.

## 16. Count query: một kết quả ngay cả khi không có row phù hợp

Với query aggregate không có GROUP BY:

```java
Long total = em.createQuery("""
    select count(c)
    from Customer c
    where c.tenantId = :tenant
      and c.displayName like :pattern
    """, Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("pattern", pattern)
    .getSingleResult();
```

Nếu không có Customer phù hợp, SQL aggregate COUNT thường trả **một hàng có giá trị 0**.

Điều này khác:

```java
Customer customer = em.createQuery("""
    select c
    from Customer c
    where c.id = :id
    """, Customer.class)
    .setParameter("id", id)
    .getSingleResult();
```

Query thứ hai không có row thì ném `NoResultException`.

### 16.1. COUNT thường trả Long

Trong JPQL, `COUNT` trả giá trị kiểu `Long`:

```java
Long total = em.createQuery("""
    select count(o)
    from PurchaseOrder o
    """, Long.class)
    .getSingleResult();
```

Không ép mặc định sang `Integer` hoặc cast từ `Object` mà không kiểm tra kiểu kết quả. Khi chuyển thành `int`, cần xem nguy cơ vượt giới hạn 32-bit nếu tập dữ liệu lớn.

### 16.2. COUNT(column) khác COUNT(*)

Trong SQL, `COUNT(column)` không đếm các hàng có column NULL. Trong JPQL, `count(o)` đếm các entity root tương ứng; `count(l.id)` đếm các giá trị non-null của thuộc tính trong join.

Ví dụ:

```sql
select c.id, count(o.id)
from Customer c
left join c.orders o
group by c.id
```

Với customer chưa có order, `count(o.id)` là 0. Nếu dùng `count(c)` trong một LEFT JOIN có nhiều order, có thể đếm các hàng sau join và ra số lớn hơn 1 cho cùng customer.

### 16.3. GROUP BY thay đổi cardinality

Query:

```sql
select o.status, count(o)
from PurchaseOrder o
group by o.status
```

trả **một kết quả cho mỗi nhóm trạng thái**. Nếu có ba trạng thái, query có thể trả ba tuple.

Vì vậy `getSingleResult()` trên câu query này không phù hợp trừ khi WHERE/HAVING có thể bảo đảm đúng một nhóm.

Nếu query có GROUP BY và không có nhóm nào phù hợp, nó có thể trả **không hàng**, khác với aggregate COUNT không GROUP BY thường trả 0.

## 17. SUM, AVG, MIN, MAX và giá trị null

Không phải mọi aggregate đều trả 0 khi tập đầu vào rỗng.

Ví dụ tổng doanh thu:

```java
BigDecimal total = em.createQuery("""
    select sum(o.totalAmount)
    from PurchaseOrder o
    where o.customer.id = :customerId
      and o.status = 'PAID'
    """, BigDecimal.class)
    .setParameter("customerId", customerId)
    .getSingleResult();
```

Khi không có order phù hợp, `SUM` thường trả **NULL**, không phải 0.

Ở đây có một hàng aggregate với giá trị null; do đó có thể nhận `null` từ `getSingleResult()` mà **không phát sinh `NoResultException`**.

### 17.1. COALESCE cho tổng mặc định 0

Có thể diễn đạt:

```java
BigDecimal total = em.createQuery("""
    select coalesce(
        sum(o.totalAmount),
        :zero
    )
    from PurchaseOrder o
    where o.customer.id = :customerId
    """, BigDecimal.class)
    .setParameter("zero", BigDecimal.ZERO)
    .setParameter("customerId", customerId)
    .getSingleResult();
```

Cần giữ type consistent với field và aggregate output của provider/dialect.

### 17.2. Bảng ngữ nghĩa aggregate khi không có input

| Biểu thức, không GROUP BY | Kết quả khi không có hàng phù hợp |
|---|---|
| `count(o)` | Thường `0L` |
| `sum(o.amount)` | Thường `null` |
| `avg(o.amount)` | Thường `null` |
| `min(o.amount)` | Thường `null` |
| `max(o.amount)` | Thường `null` |

### 17.3. Null scalar và “không có hàng” là hai nghĩa khác nhau

Nếu query là `select c.nickname` và field nullable, một hàng có nickname NULL có thể tạo một kết quả giá trị null. API nullable có thể không phân biệt được:

1. Không có result row.
2. Có một result row nhưng scalar value là null.

Nếu business cần phân biệt, chọn entity/tuple có ID hoặc query khác, thay vì dùng `Optional.ofNullable` trên scalar rồi suy luận không có record.

## 18. Trang kết quả và tổng số phần tử là hai khái niệm

Giả sử có 20.000 đơn hàng phù hợp, nhưng UI đang hiển thị trang số 3 gồm 25 bản ghi.

Query:

```java
List<PurchaseOrder> pageRows = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .setFirstResult(50)
    .setMaxResults(25)
    .getResultList();
```

`pageRows.size()` chỉ là **số phần tử trong trang đang nhận**. Nó không phải tổng số đơn hàng phù hợp của toàn bộ query.

### 18.1. Tính tổng bằng COUNT query riêng

```java
Long total = em.createQuery("""
    select count(o)
    from PurchaseOrder o
    where o.customer.id = :customerId
    """, Long.class)
    .setParameter("customerId", customerId)
    .getSingleResult();
```

Để tổng khớp danh sách, COUNT query cần giữ **cùng điều kiện lọc**. Nếu list query lọc status/date/tenant còn count query quên một điều kiện, UI phân trang sẽ báo tổng sai.

### 18.2. Một trang rỗng không chứng minh tổng bằng 0

Nếu `offset` vượt quá tổng số row, trang hiện tại có thể rỗng dù database vẫn có dữ liệu ở trang trước.

Ví dụ có 67 đơn hàng và client yêu cầu offset 200. `getResultList()` trả empty list, nhưng tổng `count` vẫn là 67.

### 18.3. OFFSET là số phần tử bỏ qua, không phải số trang

`setFirstResult(50)` nghĩa là bỏ qua 50 result items đầu tiên theo ordering của query. Nếu page number bắt đầu từ 0 và page size = 25, offset thường là `pageNumber * pageSize`.

Kiểm tra integer overflow hoặc giới hạn page size khi nhận tham số từ client.

## 19. COUNT với JOIN có thể bị nhân bản

Giả sử mỗi PurchaseOrder có nhiều OrderLine. Query list:

```sql
select distinct o
from PurchaseOrder o
join o.lines l
where l.product.id = :productId
```

Mục tiêu là lấy **các đơn hàng khác nhau** có chứa một sản phẩm.

Count sai dễ gặp:

```sql
select count(o)
from PurchaseOrder o
join o.lines l
where l.product.id = :productId
```

Nếu một order có ba lines cùng product, nó có thể được đếm ba lần.

Count theo logical roots:

```java
Long totalOrders = em.createQuery("""
    select count(distinct o.id)
    from PurchaseOrder o
    join o.lines l
    where l.product.id = :productId
    """, Long.class)
    .setParameter("productId", productId)
    .getSingleResult();
```

Hoặc thiết kế `EXISTS` để không nhân root:

```sql
select count(o)
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o
      and l.product.id = :productId
)
```

### 19.1. Không copy FETCH JOIN sang count query

`JOIN FETCH` phục vụ tải association cho entity result. Query count trả scalar `Long`, không phải entity owner để fetch.

Một count query kiểu `select count(o) ... join fetch o.lines` thường không hợp lệ hoặc không có ý nghĩa theo query semantics. Dùng JOIN thường, EXISTS hoặc count distinct theo mục tiêu.

### 19.2. Count distinct có chi phí

`COUNT(DISTINCT ...)` có thể tốn công xử lý tập distinct, tùy index/cardinality/query plan. `EXISTS` có thể giúp biểu đạt đúng ý định existence và tránh nhân hàng trong một số trường hợp, nhưng không khẳng định luôn nhanh hơn trên mọi DB.

Đo execution plan và dữ liệu thực tế.

## 20. Spring Data Page và Slice

Spring Data JPA thường dùng:

```java
Page<PurchaseOrder> findByCustomerId(
    Long customerId,
    Pageable pageable
);
```

`Page<T>` có metadata như:

- `getContent()`: các phần tử của trang hiện tại.
- `getNumberOfElements()`: số phần tử trong trang hiện tại.
- `getTotalElements()`: tổng số phần tử phù hợp theo phép đếm.
- `getTotalPages()`: tổng số trang từ tổng số phần tử và page size.
- `hasNext()`: còn trang tiếp hay không theo metadata.

### 20.1. Page không phải miễn phí

Để biết tổng số phần tử, Spring Data có thể cần một **count query riêng** ngoài query lấy trang. Trong một số trường hợp framework tối ưu không chạy count nếu có đủ thông tin, nhưng không nên giả định mọi Page luôn chỉ phát một SELECT.

Nếu count query có JOIN, DISTINCT, GROUP BY hoặc native SQL phức tạp, cần xem query count được tạo/khai báo có đúng semantics hay không.

### 20.2. Slice khi chỉ cần biết có trang tiếp

`Slice<T>` thường chỉ cần lấy lượng phần tử đủ để xác định còn trang tiếp, ví dụ pageSize+1, thay vì tính tổng N.

Phù hợp cho:

- Infinite scroll.
- Danh sách “xem thêm”.
- API không hiển thị tổng số trang.
- Dataset lớn có count đắt đỏ.

Nhưng `Slice` không cho biết tổng số bản ghi toàn bộ theo hợp đồng `Page`.

### 20.3. List với Pageable không có tổng

Một repository method trả `List<T>` với tham số Pageable có thể áp giới hạn/trang nhưng kết quả vẫn chỉ là List. Không có tổng số phần tử và metadata đầy đủ trừ khi ứng dụng tính riêng.

Kiểu trả về cần phản ánh UI contract, không chỉ tiện coding.

## 21. Pagination cần thứ tự ổn định

Nếu phân trang không có `ORDER BY`:

```java
query.setFirstResult(50).setMaxResults(25);
```

database có thể trả các hàng theo thứ tự khác khi index/plan/concurrent inserts thay đổi. Hai trang có thể trùng hoặc bỏ sót một số phần tử.

Ví dụ:

```sql
order by o.createdAt desc, o.id desc
```

Thêm tie-breaker unique giúp thứ tự xác định khi nhiều order có cùng timestamp.

### 21.1. Offset pagination vẫn chịu tác động của dữ liệu thay đổi

Ngay cả với ORDER BY ổn định, nếu có order mới được insert trước vị trí của page tiếp theo giữa hai request, offset pagination có thể thấy một số phần tử lặp hoặc bị bỏ qua.

Khi cần duyệt dataset lớn theo thời gian, cân nhắc keyset pagination:

```sql
where o.createdAt < :lastCreatedAt
   or (
       o.createdAt = :lastCreatedAt
       and o.id < :lastId
   )
order by o.createdAt desc, o.id desc
```

Query này giả định các trường sắp xếp và kiểu ID có semantics so sánh phù hợp với Hibernate/dialect. Với nullable fields hoặc sort phức tạp, keyset predicate cần thiết kế cẩn thận.

### 21.2. Query count và query page có thể thấy hai snapshot khác nhau

Nếu count và list thực thi thành hai SQL trong môi trường có concurrent writes, chúng có thể quan sát state khác nhau tùy transaction isolation.

Một UI hiển thị tổng 100 nhưng page cuối có 99/101 bản ghi không nhất thiết là bug của Hibernate; có thể là dữ liệu thay đổi giữa hai truy vấn. Nếu cần snapshot chính xác, xác định isolation/transaction phù hợp.

## 22. Khi query dự kiến một kết quả nhưng database cho nhiều: sửa ở đâu?

Có ba tầng xử lý:

**Tầng 1 — truy vấn:** thêm điều kiện lọc đúng phạm vi nghiệp vụ.

```sql
where c.tenantId = :tenantId
  and c.normalizedEmail = :email
```

**Tầng 2 — database:** tạo unique constraint/index đúng khóa business.

```sql
ALTER TABLE customers
ADD CONSTRAINT uk_customer_tenant_normalized_email
UNIQUE (tenant_id, normalized_email);
```

**Tầng 3 — ứng dụng:** xử lý duplicate/constraint conflict thành lỗi có ý nghĩa, đồng thời ghi log/metric để điều tra dữ liệu cũ.

Không phải câu query nào cũng cần unique constraint. Ví dụ tên hiển thị khách hàng được phép trùng; không tạo unique index chỉ để giúp một method `getSingleResult()` hoạt động.

### 22.1. Case normalization và collation

Email `A@example.com` và `a@example.com` có được xem là một không? Domain cần định nghĩa rõ:

- Chuẩn hóa trước khi lưu/tra cứu.
- Dùng cột `normalized_email`.
- Chọn collation/functional index phù hợp nếu cần.
- Xem NULL có được phép không.
- Xác định uniqueness là toàn cục hay theo tenant.

Không nên dựa vào `lower(c.email) = lower(:email)` ở truy vấn nhưng unique constraint lại đặt trên cột case-sensitive không phù hợp, vì điều đó có thể cho phép dữ liệu trùng theo semantics của ứng dụng.

### 22.2. Soft delete và unique constraint

Nếu khách hàng bị soft-delete, nghiệp vụ có thể muốn cho phép email cũ được đăng ký lại hoặc giữ email bị chiếm vĩnh viễn. Đây là quyết định nghiệp vụ.

Một số database hỗ trợ unique index có điều kiện như chỉ trên row chưa xóa; cú pháp và semantics khác giữa DB. Nếu dùng, mapping, query và migration phải thống nhất.

## 23. Check-then-insert không chống được race condition

Một flow thường gặp:

```java
if (findByEmail(tenantId, email).isEmpty()) {
    em.persist(new Customer(...));
}
```

Hai transaction có thể cùng thấy email chưa tồn tại rồi cùng insert.

```text
Transaction A                  Transaction B
-------------                  -------------
findByEmail -> empty           findByEmail -> empty
persist Customer               persist Customer
commit                         commit
```

Nếu không có unique constraint, cả hai có thể commit, tạo duplicate. Nếu có unique constraint, một transaction có thể thành công và transaction kia nhận constraint violation/exception tại flush hoặc commit.

### 23.1. Kết luận về uniqueness

- Query đơn nhất: **kiểm tra dữ liệu khi đọc**.
- Unique constraint: **bảo vệ dữ liệu khi ghi đồng thời**.
- Optimistic locking: phát hiện conflict với entity version trong phạm vi cập nhật tương ứng.
- Transaction isolation/locks: hỗ trợ các invariant khác theo cơ chế DB.

Không có một `getSingleResult()` nào tự thay thế cả ba lớp bảo vệ còn lại.

### 23.2. Xử lý lỗi ghi đúng transaction

Khi insert bị unique violation, transaction có thể rollback-only hoặc context không còn phù hợp tiếp tục. Không nên bắt một `PersistenceException` sau flush thất bại rồi tiếp tục dùng cùng EntityManager để làm việc như chưa có lỗi.

Nếu cần retry, mở một unit of work mới theo chính sách idempotency, hoặc trả thông báo “email đã tồn tại” từ exception constraint được phân loại phù hợp.

## 24. Exception JPA và rollback transaction

Theo semantics Jakarta Persistence, `NoResultException` và `NonUniqueResultException` từ `getSingleResult()` **không tự bắt buộc persistence provider đánh dấu transaction đang hoạt động là rollback-only**.

Điều này khác với nhiều lỗi persistence khác có thể làm transaction không còn an toàn.

Tuy nhiên, trong ứng dụng Spring:

```java
@Transactional
public Customer load(UUID tenantId, String email) {
    return query.getSingleResult();
}
```

Nếu unchecked exception thoát ra khỏi method được proxy `@Transactional` bao quanh, Spring transaction interceptor có thể quyết định rollback theo quy tắc mặc định, dù bản thân exception JPA không tự đánh dấu transaction rollback-only.

### 24.1. Phân biệt hai tầng quyết định

1. **JPA provider**: exception có tự đặt transaction rollback-only theo spec hay không.
2. **Transaction manager/framework**: exception thoát khỏi application service có khiến transaction rollback hay không.

Vì vậy, không kết luận “NoResultException luôn rollback” hoặc “NoResultException không bao giờ rollback” mà bỏ qua integration framework.

### 24.2. Xử lý no-result ngay trong repository/service khi nó hợp lệ

Nếu không tìm thấy là một phần flow bình thường, trả Optional tại ranh giới repository, tránh để exception không cần thiết đi qua transaction interceptor.

Nếu không tìm thấy phải báo lỗi nghiệp vụ, chuyển exception có chủ đích và cho transaction boundary xử lý nhất quán.

### 24.3. NonUniqueResultException là tín hiệu bất thường

Ngay cả khi JPA không tự mark rollback, dữ liệu trùng trong một use case yêu cầu uniqueness thường là lỗi nghiệp vụ/dữ liệu, không nên lặng lẽ cho phép transaction tiếp tục một hành động nhạy cảm dựa trên row tùy ý.

## 25. Optional không thay thế validation nghiệp vụ

`Optional<Customer>` chỉ biểu diễn có/không có giá trị. Nó không nói:

- Customer có quyền truy cập tài nguyên không.
- Customer đang active hay bị khóa.
- Customer có đúng tenant không.
- Email đã được xác minh chưa.
- Customer có bị soft-delete không.

Ví dụ:

```java
Customer customer = repository
    .findByTenantIdAndNormalizedEmail(tenantId, email)
    .filter(Customer::isActive)
    .orElseThrow(() -> new CustomerUnavailableException());
```

`isActive` và exception là API domain minh họa cần được triển khai. Phần kiểm tra quyền truy cập còn phải được thực hiện theo security model phù hợp.

### 25.1. Không dùng Optional.get() không kiểm tra

```java
Customer c = repository.findById(id).get();
```

Nếu rỗng sẽ ném `NoSuchElementException` thiếu ngữ cảnh nghiệp vụ. Nên dùng:

```java
Customer c = repository.findById(id)
    .orElseThrow(() -> new CustomerNotFoundException(id));
```

Hoặc `ifPresent`/`map`/`orElse` khi việc thiếu dữ liệu thật sự hợp lệ.

### 25.2. Optional không nên bị lạm dụng làm field entity

`Optional` thích hợp cho kiểu trả về method. Việc dùng Optional làm field entity JPA hoặc field DTO/serialization có thể tạo vấn đề mapping và API; thường không cần.

## 26. Khi truy vấn nhiều entity nhưng caller chỉ cần một thuộc tính

Giả sử UI chỉ cần customer name theo ID.

Cách 1 — tải entity:

```java
Customer c = em.find(Customer.class, id);
String name = c == null ? null : c.getDisplayName();
```

Cách 2 — scalar projection:

```java
List<String> names = em.createQuery("""
    select c.displayName
    from Customer c
    where c.id = :id
    """, String.class)
    .setParameter("id", id)
    .setMaxResults(2)
    .getResultList();
```

Cách 3 — DTO projection:

```java
CustomerLabel label = em.createQuery("""
    select new com.example.CustomerLabel(
        c.id, c.displayName
    )
    from Customer c
    where c.id = :id
    """, CustomerLabel.class)
    .setParameter("id", id)
    .getSingleResult();
```

Tùy nhu cầu:

- Tải entity nếu cần domain behavior/managed state.
- Dùng scalar/DTO nếu chỉ cần read model.
- Dùng projection có ID hoặc tuple để phân biệt null field với no-result khi cần.
- Không tải collection lớn chỉ vì muốn một field đơn giản.

## 27. Tránh N+1 khi xử lý danh sách

`getResultList()` trả danh sách entity, nhưng các association có thể vẫn lazy.

Ví dụ:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", "SUBMITTED")
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getDisplayName());
}
```

Nếu association customer chưa tải, việc đọc trong vòng lặp có thể tạo thêm nhiều SELECT (N+1), phụ thuộc cache và số Customer khác nhau.

Các cách giải quyết:

- `JOIN FETCH` cho to-one association phù hợp.
- `EntityGraph` trên query/repository method.
- DTO projection trực tiếp với JOIN cần thiết.
- Batch fetching nếu workload phù hợp.

Lựa chọn lấy danh sách đúng cardinality nhưng vẫn cần fetch plan tốt. Nếu map entity thành DTO sau khi transaction đã đóng, có thể gặp `LazyInitializationException`.

### 27.1. Không trả entity graph chưa được chuẩn bị ra JSON

Một controller trả `List<PurchaseOrder>` có thể khiến serializer duyệt association lazy ngoài transaction. Nên map DTO trong service transaction với fetch plan phù hợp.

### 27.2. Không fetch mọi collection khi phân trang

Fetch nhiều to-many collections cùng lúc có thể gây Cartesian product hoặc Hibernate `MultipleBagFetchException`. Với trang kết quả, thường nên lấy IDs/DTO trước rồi tải association cần thiết theo batch.

## 28. Result stream: khi nào phù hợp?

Jakarta Persistence có API `getResultStream()` ở các phiên bản hỗ trợ. Hibernate cũng cung cấp streaming/scrolling API riêng theo version.

Ví dụ:

```java
try (java.util.stream.Stream<Customer> stream =
        em.createQuery("""
            select c
            from Customer c
            where c.tenantId = :tenant
            order by c.id
            """, Customer.class)
        .setParameter("tenant", tenantId)
        .getResultStream()) {

    stream.forEach(this::processCustomer);
}
```

Streaming có thể hữu ích khi xử lý nhiều kết quả, nhưng cần hiểu:

- Không phải provider nào cũng stream database rows theo cùng cách.
- JDBC cursor/connection/transaction có thể cần được giữ mở trong suốt quá trình.
- Entity vẫn có thể tích lũy trong persistence context nếu dùng Session stateful.
- Cần đóng stream khi API tài nguyên yêu cầu.
- Với batch lớn, keyset/chunk processing có thể an toàn hơn giữ một transaction rất dài.

### 28.1. findFirst() trên stream không xác minh uniqueness

```java
Optional<Customer> customer =
    query.getResultStream().findFirst();
```

Đây là “lấy phần tử đầu tiên”, không bảo đảm query chỉ có một kết quả. Nếu chỉ cần một record theo thứ tự, đặt ORDER BY và limit ở query để database không phải đưa quá nhiều rows. Nếu cần unique, dùng API/logic kiểm tra cardinality.

## 29. TypedQuery, Query, Tuple và Object[]: “một kết quả” có thể là một hàng phức tạp

`getSingleResult()` trả **một result item**. Item này có thể là:

- Entity.
- Scalar như Long/String/BigDecimal.
- DTO.
- Tuple.
- Object[] chứa nhiều projection items.

Ví dụ một result tuple:

```java
Object[] row = em.createQuery("""
    select c.id, c.displayName
    from Customer c
    where c.id = :id
    """, Object[].class)
    .setParameter("id", id)
    .getSingleResult();

Long customerId = (Long) row[0];
String customerName = (String) row[1];
```

Một hàng result có hai cột **vẫn là một result item**. `NonUniqueResultException` xảy ra khi query trả nhiều result items, không phải vì một result item có nhiều trường.

### 29.1. Tuple khi muốn đặt alias

```java
import jakarta.persistence.Tuple;

Tuple row = em.createQuery("""
    select c.id as id, c.displayName as name
    from Customer c
    where c.id = :id
    """, Tuple.class)
    .setParameter("id", id)
    .getSingleResult();

Long idValue = row.get("id", Long.class);
String nameValue = row.get("name", String.class);
```

Tuple giúp tránh hardcoded index trong Object[] nhưng kết quả vẫn chịu cardinality 0/1/N như thường.

### 29.2. Typed query giúp phát hiện lỗi kiểu

`em.createQuery(hql, Customer.class)` làm hợp đồng kết quả rõ hơn raw Query. Với native SQL hoặc function khác biệt dialect, kiểu scalar thực tế vẫn cần xác minh trong integration test.

## 30. Native SQL và số lượng kết quả

Native SQL có thể dùng:

```java
List<?> rows = em.createNativeQuery("""
    select id, normalized_email
    from customers
    where tenant_id = :tenantId
    """)
    .setParameter("tenantId", tenantId)
    .getResultList();
```

`getResultList`/`getSingleResult` trên native query vẫn có ý tưởng cardinality tương ứng, nhưng:

- Truy vấn dựa trên tên bảng/cột vật lý.
- Kết quả scalar/Object[] cần mapping/kiểu được kiểm tra.
- Native SQL không tự biết mọi rule domain.
- SQL JOIN có thể nhân hàng.
- `LIMIT 1`/`FETCH FIRST` là cú pháp hoặc dialect-specific nếu viết trực tiếp SQL.
- Database query plan và index ảnh hưởng hiệu năng.

Nếu native query trả một row vì `LIMIT 1`, nó cũng **không chứng minh logical uniqueness**.

### 30.1. Tránh projection làm sai kỳ vọng

Một query `select email from ...` có thể trả hai rows có cùng chuỗi email. Dù Java values giống nhau, query vẫn có nhiều result rows theo semantics SQL nếu không DISTINCT.

Nếu muốn unique values, cân nhắc `select distinct email`. Nếu muốn duy nhất một **entity**, xác định unique key và primary keys đúng.

## 31. Xử lý lỗi theo tầng kiến trúc

Một thiết kế dễ bảo trì phân biệt bốn loại outcome:

1. **Không tìm thấy**: hợp lệ hoặc domain not-found.
2. **Nhiều kết quả khi yêu cầu unique**: data integrity/cardinality violation.
3. **Truy vấn thất bại kỹ thuật**: connection, timeout, syntax, mapping, database.
4. **Không được phép truy cập**: authorization/tenant scoping, không được gộp tùy tiện với ba loại trên.

Ví dụ service:

```java
@Transactional(readOnly = true)
public CustomerProfile getProfile(
        UUID tenantId,
        String normalizedEmail) {

    Customer customer = repository
        .findByTenantIdAndNormalizedEmail(
            tenantId,
            normalizedEmail
        )
        .orElseThrow(
            () -> new CustomerNotFoundException()
        );

    authorizationService.checkCanView(customer);

    return mapper.toProfile(customer);
}
```

Các service/exception/DTO là kiểu ứng dụng. Repository phụ trách truy vấn 0..1; service chuyển empty thành not-found; authorization được áp riêng.

### 31.1. Không log dữ liệu nhạy cảm vô tội vạ

Khi thấy duplicate email, log tenant ID, correlation ID và mã định danh phù hợp thay vì in toàn bộ entity/PII. Logging entity có association lazy còn có thể kích hoạt N+1 hoặc `LazyInitializationException`.

### 31.2. Không chuyển mọi error thành HTTP 404

HTTP 404 có thể phù hợp khi không có resource. `NonUniqueResultException` có thể là lỗi phía server/data integrity cần alert và xử lý, không phải một trường hợp “không tìm thấy”. Chi tiết HTTP status tùy API contract, nhưng phân loại lỗi nên chính xác.

## 32. Ví dụ repository gồm đủ ba dạng cardinality

Một repository JPA thuần:

```java
import jakarta.persistence.*;
import java.util.*;

public class CustomerQueries {

    private final EntityManager em;

    public CustomerQueries(EntityManager em) {
        this.em = em;
    }

    // Tối đa một entity theo business key.
    public Optional<Customer> findUnique(
            UUID tenantId,
            String normalizedEmail) {

        try {
            Customer customer = em.createQuery("""
                select c
                from Customer c
                where c.tenantId = :tenant
                  and c.normalizedEmail = :email
                """, Customer.class)
                .setParameter("tenant", tenantId)
                .setParameter("email", normalizedEmail)
                .getSingleResult();

            return Optional.of(customer);
        } catch (NoResultException ex) {
            return Optional.empty();
        }
    }

    // Danh sách có thể rỗng.
    public List<Customer> findByName(
            UUID tenantId,
            String prefix,
            int offset,
            int limit) {

        String pattern = prefix + "%";

        return em.createQuery("""
            select c
            from Customer c
            where c.tenantId = :tenant
              and c.displayName like :pattern
            order by c.displayName, c.id
            """, Customer.class)
            .setParameter("tenant", tenantId)
            .setParameter("pattern", pattern)
            .setFirstResult(offset)
            .setMaxResults(limit)
            .getResultList();
    }

    // Chọn một customer mới nhất trong tập có thể nhiều.
    public Optional<Customer> findLatest(UUID tenantId) {
        List<Customer> rows = em.createQuery("""
            select c
            from Customer c
            where c.tenantId = :tenant
            order by c.createdAt desc, c.id desc
            """, Customer.class)
            .setParameter("tenant", tenantId)
            .setMaxResults(1)
            .getResultList();

        return rows.stream().findFirst();
    }

    // Tổng số customer của tenant.
    public long count(UUID tenantId) {
        return em.createQuery("""
            select count(c)
            from Customer c
            where c.tenantId = :tenant
            """, Long.class)
            .setParameter("tenant", tenantId)
            .getSingleResult();
    }
}
```

Chú ý:

- `findUnique` không bắt `NonUniqueResultException`.
- `findByName` có paging, không giả định `getResultList()` trả toàn bộ tập dữ liệu.
- `findLatest` cố ý dùng ORDER BY + limit.
- `count` có một kết quả Long.
- Cần validate `offset ≥ 0` và `limit` trong mức cho phép ở service/API; query ví dụ giả định input đã được kiểm soát.
- Với pattern từ người dùng, ký tự `%`/`_` có thể được hiểu là wildcard; nếu nghiệp vụ muốn prefix literal, cần escape theo chuẩn JPQL/dialect phù hợp.

## 33. Ví dụ một trang kết quả thủ công

DTO:

```java
public record CustomerPageResult(
    List<CustomerSummary> items,
    long total,
    int offset,
    int limit
) {}
```

Query service:

```java
@Transactional(readOnly = true)
public CustomerPageResult listCustomers(
        UUID tenantId,
        String prefix,
        int offset,
        int limit) {

    String pattern = prefix + "%";

    List<CustomerSummary> items = em.createQuery("""
        select new com.example.CustomerSummary(
            c.id, c.displayName
        )
        from Customer c
        where c.tenantId = :tenant
          and c.displayName like :pattern
        order by c.displayName, c.id
        """, CustomerSummary.class)
        .setParameter("tenant", tenantId)
        .setParameter("pattern", pattern)
        .setFirstResult(offset)
        .setMaxResults(limit)
        .getResultList();

    Long total = em.createQuery("""
        select count(c)
        from Customer c
        where c.tenantId = :tenant
          and c.displayName like :pattern
        """, Long.class)
        .setParameter("tenant", tenantId)
        .setParameter("pattern", pattern)
        .getSingleResult();

    return new CustomerPageResult(
        items,
        total,
        offset,
        limit
    );
}
```

Các bước:

1. Query list có ordering ổn định và giới hạn trang.
2. Query count có điều kiện tương ứng.
3. Dùng `getResultList()` cho items.
4. Dùng `getSingleResult()` cho COUNT.
5. Không dùng `items.size()` làm `total`.

Đây là cách dựng manual page đơn giản. Với query join phức tạp, cần count distinct hoặc exists phù hợp; với datasets thay đổi đồng thời, count và list có thể không phản ánh cùng snapshot nếu isolation không bảo đảm.

## 34. Khi nào không nên đếm tổng?

Đếm toàn bộ tập dữ liệu đôi khi rất đắt:

- Bảng lớn.
- Filter gồm nhiều join.
- Permission predicate phức tạp.
- DISTINCT/GROUP BY.
- Query trên dữ liệu thay đổi liên tục.
- API infinite scroll không hiển thị tổng.

Nếu UI chỉ cần “còn phần tử tiếp theo không?”, có thể tải `pageSize+1` phần tử:

```java
List<CustomerSummary> rows = em.createQuery("""
    select new com.example.CustomerSummary(
        c.id, c.displayName
    )
    from Customer c
    where c.tenantId = :tenant
    order by c.id
    """, CustomerSummary.class)
    .setParameter("tenant", tenantId)
    .setFirstResult(offset)
    .setMaxResults(pageSize + 1)
    .getResultList();

boolean hasNext = rows.size() > pageSize;

List<CustomerSummary> content = hasNext
    ? new ArrayList<>(rows.subList(0, pageSize))
    : rows;
```

Cách này tiết kiệm count nhưng **không có tổng chính xác**. Nó tương ứng ý tưởng Slice, và vẫn chịu giới hạn offset pagination. Trong production, cần validate pageSize, xử lý số lớn/overflow và chọn thứ tự ổn định.

## 35. Khi nào cần dùng EXISTS thay vì COUNT?

Nếu chỉ cần kiểm tra có ít nhất một bản ghi, có thể dùng:

```java
boolean exists = !em.createQuery("""
    select c.id
    from Customer c
    where c.tenantId = :tenant
      and c.normalizedEmail = :email
    """, Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("email", email)
    .setMaxResults(1)
    .getResultList()
    .isEmpty();
```

Trong một số query phức tạp, dùng JPQL `exists` trong predicate khác có thể phù hợp hơn:

```sql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o
      and l.product.id = :productId
)
```

### 35.1. EXISTS và uniqueness khác nhau

Existence trả lời “có ít nhất một hay không”. Nó **không xác minh tối đa một**.

Nếu cần phát hiện duplicate, COUNT có thể cho số lượng; helper lấy tối đa hai result items cũng đủ xác minh có nhiều hơn một trong một số query.

### 35.2. Performance không có quy tắc tuyệt đối

`COUNT` có thể phải xử lý nhiều hàng; SELECT ID giới hạn một có thể dừng sớm với index phù hợp. Nhưng SQL optimizer/dialect có thể tối ưu chúng khác nhau.

Không chọn dựa trên niềm tin “COUNT luôn chậm hơn EXISTS” hoặc ngược lại; đo query plan với dữ liệu thực tế.

## 36. Chẩn đoán “expected one result, found N”

Khi gặp exception kiểu:

```text
jakarta.persistence.NonUniqueResultException:
    Query did not return a unique result
```

hoặc exception native Hibernate/Spring tương ứng, lần lượt kiểm tra:

1. **Mong đợi của use case:** thật sự cần unique hay đang cần newest/first/list?
2. **WHERE:** đã có tenant, status, deletedAt, owner và business key đầy đủ?
3. **Database:** có unique constraint/index đúng không?
4. **Dữ liệu thực:** có nhiều entity IDs khác nhau hay chỉ nhiều rows do join?
5. **JOIN:** to-many association có nhân kết quả không?
6. **Projection:** query chọn root entity, tuple hay scalar?
7. **Aggregate:** query có GROUP BY làm nhiều nhóm không?
8. **Provider/version:** Hibernate xử lý duplicate root/fetch join thế nào?
9. **Pagination:** có setMaxResults/offset khiến cardinality bị thay đổi?
10. **Concurrency:** có hai transactions insert duplicate do thiếu DB constraint?
11. **Soft delete:** các bản ghi ẩn/đã xóa có được loại đúng không?
12. **Email normalization:** so sánh query có khớp unique semantics của DB không?

Không kết luận lỗi là do Hibernate trả sai khi chưa biết đây là duplicate **result rows** hay duplicate **domain entities**.

## 37. Kiểm thử ranh giới số lượng kết quả

Một bộ integration test nên bao gồm:

### 37.1. Không có kết quả

- `getResultList()` trả empty list.
- `getSingleResult()` ném `NoResultException`.
- `getSingleResultOrNull()`, nếu được API hỗ trợ, trả null.
- Repository `Optional<T>` trả empty.
- COUNT không GROUP BY trả 0.

### 37.2. Đúng một kết quả

- `getSingleResult()` trả đúng entity/DTO/scalar.
- `Optional<T>` chứa giá trị.
- `getResultList()` chứa một phần tử.
- Các field null scalar được kiểm tra theo semantics riêng.

### 37.3. Nhiều kết quả

- Query unique trả lỗi cardinality, không lấy phần tử đầu tiên.
- Query list trả đủ phần tử theo paging.
- Query newest trả phần tử được sắp xếp đúng.
- Query có GROUP BY được xử lý như danh sách nếu có nhiều nhóm.

### 37.4. Duplicate do join

- Một Order có nhiều Lines.
- Query join tạo nhiều SQL rows.
- Xác nhận `distinct`/`exists` hoặc query thiết kế lại trả đúng logical entities.
- Kiểm tra Hibernate version nếu dùng fetch join collection.

### 37.5. Uniqueness và concurrent insert

- Unique constraint thực sự tồn tại trong schema test.
- Hai lần insert cùng business key không cùng thành công khi constraint cấm.
- Ứng dụng xử lý conflict đúng transaction boundary.

### 37.6. Phân trang

- Trang đầu đầy, trang cuối thiếu, offset vượt tổng.
- Các bản ghi có cùng sort field nhưng ID khác.
- `count` đúng cùng filter.
- Join to-many không làm count bị nhân.
- Khi dữ liệu thay đổi đồng thời, xác nhận semantics snapshot được chấp nhận.

Kiểm thử nên chạy trên database/dialect gần production nếu uniqueness collation, NULL, indexing, isolation hoặc pagination semantics là một phần quan trọng.

## 38. Bảng sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `getSingleResult()` cho tìm kiếm có thể nhiều | `NonUniqueResultException` | Dùng List/Page hoặc sửa domain contract |
| Bắt mọi exception và trả Optional.empty | Che lỗi DB, mapping, duplicate | Chỉ xử lý trường hợp no-result phù hợp |
| Bắt NonUnique rồi lấy first | Che dữ liệu trùng, hành vi không ổn định | Sửa predicate/constraint hoặc định nghĩa first thật |
| Dùng `setMaxResults(1)` để “bảo đảm unique” | Không phát hiện các hàng còn lại | Không giới hạn 1 khi kiểm tra uniqueness |
| Dùng `findFirst()` mà không ORDER BY | Row được chọn không ổn định | ORDER BY + tie-breaker |
| Dùng Optional cho query cố ý trả nhiều | Không hợp cardinality | List/Page/Slice |
| Coi empty list là null | Null check thừa, code phức tạp | Sử dụng `isEmpty()` |
| Dùng `list.size()` làm total count của trang | Tổng trang sai | COUNT query tương ứng hoặc Page |
| Đếm root bằng `count(o)` qua join collection | Tổng bị nhân bản | COUNT DISTINCT hoặc EXISTS |
| Copy JOIN FETCH vào count query | Sai semantics/query | Count riêng không FETCH |
| Coi COUNT không có row trả NoResult | Xử lý exception sai | COUNT thường trả 0 |
| Coi SUM không có row trả 0 | NullPointerException hoặc sai tổng | COALESCE/nullable handling |
| Nhầm scalar NULL với không có result row | Bỏ sót dữ liệu hiện hữu | Chọn entity/tuple có ID |
| Coi duplicate SQL row là duplicate entity | Chẩn đoán sai | Kiểm tra join, identity, DISTINCT |
| Không có DB unique constraint | Race tạo duplicate | Schema constraint theo business key |
| Quên tenant/soft-delete predicate | Trả nhiều hoặc nhầm dữ liệu | Scope query rõ và kiểm thử |
| Phân trang không ORDER BY | Trùng/bỏ sót kết quả | Sort ổn định |
| Fetch collection cùng pagination trực tiếp | Row multiplication/in-memory pagination | Hai bước ID → fetch graph |
| Trả entity lazy ra controller | N+1/LazyInitializationException | Map DTO trong transaction |
| Không phân biệt Page và Slice | Count dư hoặc thiếu tổng cần thiết | Chọn theo yêu cầu UI |

## 39. Bài tập thực hành

### Bài 1 — Chọn API cho email theo tenant

Use case: email đã normalized và unique trong tenant; có thể chưa tồn tại.

**Đề xuất:** repository trả `Optional<Customer>`, dùng getSingleResultOrNull hoặc helper bắt NoResultException; không che NonUniqueResultException. Database phải có unique constraint thích hợp.

### Bài 2 — Tìm tài khoản mới nhất

Use case: một tenant có thể có nhiều tài khoản, chỉ cần tài khoản tạo mới nhất.

**Đề xuất:** `ORDER BY createdAt DESC, id DESC` + `setMaxResults(1)`. Không dùng unique-result API để chứng minh chỉ có một tài khoản.

### Bài 3 — Tổng số order trong trang

Trang có 25 order, database có 1.000 order phù hợp.

**Câu hỏi:** `pageRows.size()` trả gì? **Đáp án:** số row trong trang hiện tại, thường 25. Muốn tổng 1.000 cần count query hoặc Page metadata.

### Bài 4 — JOIN ba dòng hàng

Một Order có ba OrderLines. Query `select o from PurchaseOrder o join o.lines l` có thể sinh ba SQL rows cho một Order.

**Câu hỏi:** database có ba Order? **Không.** Cần phân biệt root entity identity với row multiplication do join; dùng `distinct`/`exists` nếu cần root list duy nhất.

### Bài 5 — SUM rỗng

Không có paid orders, query `select sum(o.totalAmount) ...`.

**Câu hỏi:** có `NoResultException`? **Không nhất thiết.** Aggregate không GROUP BY thường trả một row có value NULL; dùng `coalesce` nếu muốn 0.

### Bài 6 — Phát hiện duplicate mà không tải toàn bộ

Use case kiểm tra business key có 0, 1 hay nhiều matches nhưng API JPA chưa có getSingleResultOrNull.

**Đề xuất:** `getResultList()` với `setMaxResults(2)`, phân loại 0/1/2, với điều kiện query items phản ánh logical entities cần kiểm tra. Đây là kiểm tra đọc, không thay thế constraint.

### Bài 7 — Exception và transaction

`getSingleResult()` ném `NoResultException` trong method `@Transactional`.

**Câu hỏi:** JPA và Spring có luôn xử lý rollback giống nhau? **Không.** Spec JPA quy định no-result/non-unique không tự mark rollback-only; Spring interceptor có thể rollback nếu unchecked exception thoát khỏi transactional method theo rule của Spring.

## 40. Quy trình lựa chọn phương thức lấy kết quả

Trước khi viết repository method, hãy xác nhận:

1. **Business cardinality:** 0, 1, 0..1 hay 0..N?
2. **Đang chọn “first/latest” hay kiểm tra “unique”?** Không đánh đồng.
3. **Khóa tìm kiếm:** primary key hay business key? Có unique constraint đúng scope?
4. **Tham số lọc:** tenant, owner, active/deleted, date/status đã đầy đủ?
5. **Cấu trúc result:** entity, scalar, DTO, tuple hay aggregate?
6. **JOIN cardinality:** có to-many join nhân hàng hay không?
7. **GROUP BY:** query trả một hàng tổng hợp hay một hàng cho mỗi nhóm?
8. **Null semantics:** giá trị scalar NULL có khác trường hợp no-result không?
9. **Không tìm thấy:** empty hợp lệ hay exception nghiệp vụ?
10. **Nhiều kết quả bất ngờ:** cần cảnh báo và sửa dữ liệu hay chỉ thay list contract?
11. **Thứ tự:** nếu lấy first, có ORDER BY và tie-breaker chưa?
12. **Paging:** cần total count hay chỉ hasNext?
13. **Count query:** đã áp cùng filter và distinct/exists tương ứng chưa?
14. **Fetch plan:** caller có cần association lazy không? Có N+1 hoặc collection fetch pagination?
15. **Transaction:** query/scalar/DTO có được xử lý trong boundary thích hợp?
16. **Performance:** query có index, giới hạn kích thước và execution plan tốt?
17. **Concurrency:** nếu uniqueness là invariant ghi, DB có constraint bảo vệ không?
18. **Test:** có case 0, 1, 2, nhiều, join duplicate và page cuối hay chưa?

Việc chọn API là bước cuối của thiết kế cardinality, không phải điểm khởi đầu thay thế suy nghĩ về dữ liệu.

## 41. Ghi nhớ

- **`getResultList()`** dành cho truy vấn 0..N; không có row thì trả danh sách rỗng, không phải null.
- **`getSingleResult()`** yêu cầu một result item: 0 → `NoResultException`, trên 1 → `NonUniqueResultException`.
- **`getSingleResultOrNull()`** (trên phiên bản Jakarta Persistence hỗ trợ) biểu diễn 0..1 bằng nullable result, nhưng không chấp nhận multiple results.
- **`Optional<T>`** là hợp đồng rõ cho 0..1; trong Hibernate native có `uniqueResultOptional()`, trong Spring Data có return type Optional.
- **Một hàng đầu tiên khác một hàng duy nhất.** `setMaxResults(1)` có thể chọn first/latest, nhưng không chứng minh uniqueness.
- **Tìm latest phải có `ORDER BY` ổn định** với tie-breaker; không dựa vào thứ tự mặc định của database.
- **`NonUniqueResultException`** có thể do WHERE thiếu scope, DB thiếu constraint, dữ liệu trùng hoặc query join nhân rows; phải phân loại đúng.
- **Database unique constraint** bảo vệ uniqueness khi ghi đồng thời; query unique chỉ kiểm tra khi đọc.
- **JOIN to-many có thể nhân SQL rows**; một logical entity có thể xuất hiện nhiều lần. Hibernate/version/query projection quyết định duplicate root handling.
- **`COUNT` không GROUP BY** thường trả một giá trị `Long`, kể cả 0; `SUM`/`AVG`/`MIN`/`MAX` trên tập rỗng thường trả null.
- **GROUP BY** tạo một result item cho mỗi nhóm, có thể 0 hoặc nhiều; không mặc định dùng `getSingleResult()`.
- **`list.size()` trên trang không phải tổng số record**. Dùng count query tương ứng hoặc `Page.getTotalElements()`.
- **`Slice`** phù hợp khi chỉ cần hasNext và không cần total; có thể tránh count query đắt.
- **COUNT qua collection join** có thể bị nhân; cân nhắc `COUNT(DISTINCT root.id)` hoặc `EXISTS`.
- **Exception JPA và rollback Spring** là hai tầng semantics khác nhau; không bắt mọi persistence exception thành “không tìm thấy”.
- **DTO projection và fetch plan** giúp tránh N+1, lazy loading ngoài transaction và tải dư association.
- **Thử các ranh giới 0/1/2/N** và concurrency để bảo đảm query trả đúng loại kết quả mà API hứa.

**Kết luận:** Cách lấy kết quả trong Hibernate phải phản ánh đúng **ý nghĩa số lượng** của use case. Nếu phải có đúng một kết quả, dùng `getSingleResult()` và xử lý trường hợp thiếu/trùng một cách rõ ràng; nếu 0..1 hợp lệ, dùng nullable/Optional mà vẫn phát hiện dữ liệu trùng; nếu có thể nhiều, dùng list/pagination; nếu chỉ muốn mới nhất, xác định ordering rồi giới hạn. Với truy vấn tổng hợp và phân trang, phân biệt result items, logical entities, SQL rows và total count sẽ giúp tránh những lỗi tưởng nhỏ nhưng có thể ảnh hưởng trực tiếp đến tính đúng đắn và khả năng mở rộng của ứng dụng.
