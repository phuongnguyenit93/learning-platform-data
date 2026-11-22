# Xử lý NoResultException và NonUniqueResultException theo hợp đồng truy vấn trong JPA

Một ứng dụng dùng Java Persistence API (JPA) thường cần truy vấn **một đối tượng**: tìm tài khoản theo email, đọc đơn hàng theo mã nghiệp vụ, kiểm tra một cấu hình duy nhất cho tenant, hoặc lấy bản ghi đang có hiệu lực cho một thời điểm. Lỗi không nằm ở câu JPQL có chạy được hay không, mà ở câu hỏi: **nếu truy vấn trả về không có kết quả, một kết quả hoặc nhiều kết quả thì ứng dụng phải làm gì?**

JPA cung cấp `Query.getSingleResult()` và `TypedQuery.getSingleResult()` để thực thi truy vấn được kỳ vọng trả đúng một result. Hai exception liên quan trực tiếp là:

- **`NoResultException`**: truy vấn không trả result nào.
- **`NonUniqueResultException`**: truy vấn trả nhiều hơn một result trong trường hợp đòi một result.

Hai trạng thái này **khác nhau về ý nghĩa nghiệp vụ**. Không tìm thấy một giỏ hàng chưa tạo có thể là trạng thái bình thường; không tìm thấy đơn hàng bắt buộc có thể là `404` hoặc lỗi domain. Ngược lại, tìm thấy hai bản ghi khi hệ thống cam kết chỉ có một thường là dấu hiệu query sai, dữ liệu vi phạm uniqueness hoặc thay đổi schema, **không phải** lời mời chọn bừa bản ghi đầu tiên.

Bài này hướng dẫn xử lý hai exception theo **hợp đồng truy vấn**: trước khi viết `catch`, phải xác định kết quả 0/1/nhiều có ý nghĩa gì, có cần ràng buộc uniqueness ở database không, và sau lỗi có được tiếp tục transaction hay phải rollback theo chính sách ứng dụng.

Nội dung sử dụng Jakarta Persistence (`jakarta.persistence.*`), ví dụ Java, JPQL, Criteria, SQL và Spring Data JPA. Với codebase dùng JPA 2.x (`javax.persistence.*`) hoặc phiên bản Spring/Hibernate cũ, cần dùng package và APIs tương ứng.

---

## 1. Hợp đồng truy vấn là gì?

**Hợp đồng truy vấn (query contract)** là thỏa thuận giữa service/repository và caller về:

1. **Phạm vi tìm kiếm**: entity nào, tenant nào, trạng thái nào, thời điểm nào.
2. **Số lượng kết quả hợp lệ**: `0..1`, `1`, `0..n`, hay `1..n`.
3. **Kiểu kết quả**: managed entity, scalar, DTO, `Tuple`, aggregate hoặc collection.
4. **Ý nghĩa của không có dữ liệu**: bình thường, lỗi nghiệp vụ hay dữ liệu chưa đồng bộ.
5. **Ý nghĩa của nhiều kết quả**: bình thường, trùng lặp hợp lệ hay vi phạm invariant.
6. **Trách nhiệm khi lỗi**: trả Optional, ném domain exception, rollback, ghi log/metric hoặc kích hoạt quy trình khắc phục dữ liệu.
7. **Tính nhất quán**: dữ liệu có thể đọc từ replica/cache không, transaction isolation ra sao và những writers nào có thể sửa dữ liệu.

Ví dụ yêu cầu:

> Trong mỗi tenant, chỉ tồn tại tối đa một `Customer` hoạt động có `normalizedEmail` bằng một giá trị. Nếu không có Customer, caller nhận `Optional.empty()`. Nếu có hai Customer khớp, đó là lỗi dữ liệu cần phát hiện chứ không chọn một bản ghi tùy ý.

Đây là hợp đồng **`0..1`**. Cùng câu truy vấn đó có thể được một command khác dùng với hợp đồng **`exactly 1`**, khi customer bắt buộc phải tồn tại.

### 1.1. Một JPQL không tự định nghĩa hợp đồng nghiệp vụ

```java
SELECT c
FROM Customer c
WHERE c.tenantId = :tenantId
  AND c.normalizedEmail = :email
```

Câu JPQL chỉ định điều kiện tìm kiếm, không thể hiện `0` là thành công hay lỗi, và cũng không bảo đảm uniqueness nếu database không có constraint tương ứng.

### 1.2. Đừng bắt exception trước khi xác định kỳ vọng

Sai về tư duy:

```java
try {
    return query.getSingleResult();
} catch (RuntimeException ex) {
    return null;
}
```

Mọi lỗi SQL, timeout, mapping hay connection đều bị biến thành “không tìm thấy”. Caller không thể biết database đang hỏng hay chỉ đơn giản là không có Customer.

Đúng về tư duy: xác định query contract, chỉ xử lý **những trạng thái được hợp đồng cho phép** và để lỗi khác đi theo error policy riêng.

---

## 2. Kết quả 0, 1 và nhiều bản ghi

Với `getSingleResult()`:

| Số result của truy vấn | Hành vi chính | Ý nghĩa cần quyết định |
|---|---|---|
| 0 | Ném `NoResultException` | Vắng dữ liệu là bình thường hay lỗi? |
| 1 | Trả chính result đó | Kiểm tra giá trị, quyền và trạng thái nghiệp vụ |
| Từ 2 trở lên | Ném `NonUniqueResultException` | Query sai hay vi phạm uniqueness? |

Đây là **số result của query theo JPA**, không nhất thiết trùng với số rows vật lý được database xử lý trước khi provider ánh xạ entity, join hoặc projection.

### 2.1. `NoResultException`

```java
Customer c = em.createQuery(
        "SELECT c FROM Customer c WHERE c.id = :id",
        Customer.class
    )
    .setParameter("id", 999L)
    .getSingleResult();
```

Nếu không có result, JPA ném `jakarta.persistence.NoResultException`.

### 2.2. `NonUniqueResultException`

```java
Customer c = em.createQuery(
        """
        SELECT c FROM Customer c
        WHERE c.city = :city
        """,
        Customer.class
    )
    .setParameter("city", "Da Nang")
    .getSingleResult();
```

Nếu nhiều Customers cùng thành phố, đó là một tình huống hợp lệ của dữ liệu nhưng **không hợp lệ với API yêu cầu một result**. Thường cần `getResultList()` thay vì “sửa” bằng `catch`.

### 2.3. Không phải mọi truy vấn single đều phải bắt cả hai

Nếu truy vấn theo primary key, hãy cân nhắc `EntityManager.find()`, vốn có hợp đồng khác: trả entity hoặc `null` nếu không có, và primary key không cho phép nhiều rows cùng identity trong mô hình quan hệ hợp lệ.

---

## 3. Entity mẫu cho các ví dụ

Sử dụng domain nhiều tenant. Một Customer có thể được tra cứu bằng ID hoặc business key `normalizedEmail` trong một tenant.

```java
package com.example.customer.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {
            "tenant_id",
            "normalized_email"
        }
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "normalized_email", nullable = false)
    private String normalizedEmail;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    private long version;

    protected Customer() {}

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getNormalizedEmail() {
        return normalizedEmail;
    }
    public String getDisplayName() { return displayName; }
}
```

SQL minh họa:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uk_customer_tenant_email
        UNIQUE (tenant_id, normalized_email)
);
```

SQL identity/type syntax thay đổi theo database. Tùy mô hình soft delete hoặc yêu cầu cho phép đăng ký lại email của bản ghi không hoạt động, uniqueness policy có thể khác; phần sau sẽ phân tích.

### 3.1. Vì sao dùng `normalizedEmail`?

Nếu chỉ so sánh email theo dạng raw input, ứng dụng có thể coi `" USER@example.com "` và `"user@example.com"` là hai giá trị khác nhau. Các quy tắc chuẩn hóa phải được định nghĩa nhất quán tại service/domain layer; một số hệ thống còn phụ thuộc quy định về case folding và database collation.

### 3.2. Vì sao cần tenant predicate?

Truy vấn business key phải giữ đúng phạm vi dữ liệu. Cùng email có thể xuất hiện ở những tenants khác nhau. Thiếu `tenantId` có thể vừa tạo `NonUniqueResultException`, vừa tạo nguy cơ lộ dữ liệu cross-tenant.

---

## 4. Hợp đồng `0..1`: Không tìm thấy là bình thường

Một use case như “tìm Customer theo email, nếu chưa có thì cho phép onboarding” có kết quả hợp lệ là **không có hoặc có đúng một**.

Repository/service nên biểu đạt điều này bằng `Optional<Customer>`:

```java
public Optional<Customer> findByEmail(
        EntityManager em,
        long tenantId,
        String normalizedEmail) {

    TypedQuery<Customer> query = em.createQuery(
        """
        SELECT c FROM Customer c
        WHERE c.tenantId = :tenantId
          AND c.normalizedEmail = :email
        """,
        Customer.class
    );

    query.setParameter("tenantId", tenantId);
    query.setParameter("email", normalizedEmail);

    try {
        return Optional.of(
            query.getSingleResult()
        );
    } catch (NoResultException ex) {
        return Optional.empty();
    }
}
```

Điều quan trọng là **không bắt `NonUniqueResultException` để trả empty**. Với hợp đồng `0..1`, nhiều result là bất thường.

### 4.1. Không tìm thấy không phải database error

`Optional.empty()` nói “không có Customer khớp” theo truy vấn hiện tại; nó không có nghĩa connection hỏng, query timeout hoặc permission error.

### 4.2. Optional thể hiện kỳ vọng rõ hơn null

`Optional<Customer>` buộc caller nhìn thấy khả năng thiếu dữ liệu, giảm nguy cơ `NullPointerException` do quên kiểm tra. Trong một số API khác, trả `null` cũng có thể là hợp đồng được chấp nhận, nhưng phải nhất quán.

### 4.3. Không trả `Optional.empty()` khi duplicate

Nếu dữ liệu có hai rows cùng `(tenantId, normalizedEmail)`, `getSingleResult()` ném `NonUniqueResultException`. Để exception này được phát hiện hoặc translate thành lỗi rõ, thay vì biến thành “chưa đăng ký”.

---

## 5. Hợp đồng `exactly 1`: Không tìm thấy là lỗi nghiệp vụ

Trong command “cập nhật Customer theo mã bắt buộc tồn tại”, không tìm thấy có thể là lỗi.

```java
public Customer requireCustomer(
        EntityManager em,
        long tenantId,
        String normalizedEmail) {

    TypedQuery<Customer> query = em.createQuery(
        """
        SELECT c FROM Customer c
        WHERE c.tenantId = :tenantId
          AND c.normalizedEmail = :email
        """,
        Customer.class
    );

    query.setParameter("tenantId", tenantId);
    query.setParameter("email", normalizedEmail);

    try {
        return query.getSingleResult();
    } catch (NoResultException ex) {
        throw new CustomerNotFoundException(
            tenantId,
            normalizedEmail,
            ex
        );
    }
}
```

`CustomerNotFoundException` là domain exception ứng dụng tự định nghĩa:

```java
public class CustomerNotFoundException
        extends RuntimeException {

    public CustomerNotFoundException(
            long tenantId,
            String email,
            Throwable cause) {
        super(
            "Customer not found for tenant " + tenantId,
            cause
        );
    }
}
```

Thông điệp public-facing không nên chứa email/PII nếu log policy hoặc API response không cho phép. Ví dụ minh họa giữ cause để chẩn đoán.

### 5.1. Domain exception có ngữ nghĩa khác JPA exception

`NoResultException` báo điều gì xảy ra khi thực thi `getSingleResult()`. `CustomerNotFoundException` báo ý nghĩa của sự kiện đó đối với một use case cụ thể.

### 5.2. Không bắt NonUnique ở đây như “not found”

Đối với `exactly 1`, `0` và `>1` đều vi phạm kỳ vọng nhưng **không phải một lỗi**. `0` có thể map sang not found; `>1` thường là data integrity/ambiguous selection và cần quy trình xử lý riêng.

### 5.3. Không che các lỗi persistence khác

Nếu database unavailable, syntax JPQL sai hoặc transaction rollback-only, phải để lỗi đi theo persistence/infrastructure error path.

---

## 6. Hợp đồng `0..n` hoặc `1..n`: Dùng getResultList

Nếu nhiều customers khớp là bình thường, ví dụ tìm theo thành phố:

```java
List<Customer> customers = em.createQuery(
        """
        SELECT c FROM Customer c
        WHERE c.city = :city
        ORDER BY c.id
        """,
        Customer.class
    )
    .setParameter("city", "Ha Noi")
    .getResultList();
```

`getResultList()` trả một danh sách kết quả; khi không có result, nó trả **danh sách rỗng** thay vì ném `NoResultException` cho tình huống thông thường.

### 6.1. Không dùng getSingleResult chỉ để lấy một item của danh sách

Nếu query có thể trả nhiều records đúng nghiệp vụ, `NonUniqueResultException` là dấu hiệu **API đã chọn sai**.

### 6.2. Hợp đồng `1..n`

Nếu ít nhất một result bắt buộc tồn tại:

```java
List<Customer> matches = query.getResultList();

if (matches.isEmpty()) {
    throw new CustomerNotFoundException(
        tenantId, email, null
    );
}
```

Khi số result hợp lệ là nhiều, không cần catch `NonUniqueResultException`.

### 6.3. List trả empty không có nghĩa lỗi hạ tầng biến mất

DB connection exception, timeout hoặc mapping failure vẫn có thể xảy ra trong quá trình lấy danh sách; không thay `catch (RuntimeException) return List.of()`.

---

## 7. Bảng lựa chọn API theo số lượng hợp lệ

| Hợp đồng | Kết quả 0 | Kết quả 1 | Kết quả 2+ | API đề xuất |
|---|---|---|---|---|
| `0..1` | Bình thường | Bình thường | Lỗi | `Optional<T>` qua `getSingleResult` hoặc `getSingleResultOrNull` khi hỗ trợ |
| `exactly 1` | Lỗi domain | Bình thường | Lỗi uniqueness | `getSingleResult` |
| `0..n` | Danh sách rỗng | Danh sách một phần tử | Danh sách | `getResultList` |
| `1..n` | Lỗi domain | Danh sách | Danh sách | `getResultList` + kiểm tra empty |
| “Lấy bản ghi mới nhất” | Có thể empty | Một bản ghi | Nhiều bản ghi theo thứ tự | `ORDER BY` + `setMaxResults(1)` theo contract |
| “Kiểm tra tồn tại” | false | true | true | COUNT/EXISTS hoặc query có giới hạn tùy mục đích |
| Tra theo primary key | null | Entity | DB PK ngăn duplicate | `EntityManager.find` |

**Không dùng `setMaxResults(1)` thay cho unique query nếu hợp đồng đòi `0..1`.** Nó chuyển việc phát hiện duplicate thành chọn một bản ghi.

---

## 8. `getSingleResult()` và `getSingleResultOrNull()`

Trong Jakarta Persistence API có các phiên bản khác nhau. Những môi trường hỗ trợ **Jakarta Persistence 3.2** có thêm `getSingleResultOrNull()` cho query.

### 8.1. getSingleResult

```java
Customer result = query.getSingleResult();
```

- `0` result: `NoResultException`.
- `1` result: trả result.
- `2+` results: `NonUniqueResultException`.

### 8.2. getSingleResultOrNull (kiểm tra phiên bản)

Trên Jakarta Persistence **3.2 trở lên**, có thể viết:

```java
Customer result = query.getSingleResultOrNull();

return Optional.ofNullable(result);
```

- `0` result: trả `null`.
- `1` result: trả result.
- `2+` results: vẫn có thể ném `NonUniqueResultException`.

**Đừng copy method này vào dự án Jakarta Persistence 3.0/3.1 hoặc JPA 2.x nếu API dependency chưa có nó.** Cần kiểm tra version `jakarta.persistence-api` và implementation. Đừng thêm method bằng cách cast provider-specific interface rồi tuyên bố code portable.

### 8.3. Không dùng getSingleResultOrNull để nuốt duplicate

Method chỉ thay cách diễn đạt tình huống **không có kết quả**, không loại bỏ quy tắc một result tối đa.

### 8.4. Khác biệt với `find`

`em.find(Customer.class, id)` trả `null` nếu entity theo PK không tồn tại. Không cần convert `NoResultException` cho `find`, vì đó không phải hợp đồng của `find`.

---

## 9. Dùng getResultList và giới hạn hai kết quả để biểu diễn `0..1`

Một số codebase muốn tránh phụ thuộc `getSingleResult()` exceptions cho normal absence:

```java
public Optional<Customer> findOptional(
        EntityManager em,
        long tenantId,
        String email) {

    List<Customer> matches = em.createQuery(
            """
            SELECT c FROM Customer c
            WHERE c.tenantId = :tenantId
              AND c.normalizedEmail = :email
            """,
            Customer.class
        )
        .setParameter("tenantId", tenantId)
        .setParameter("email", email)
        .setMaxResults(2)
        .getResultList();

    if (matches.isEmpty()) {
        return Optional.empty();
    }

    if (matches.size() > 1) {
        throw new DuplicateCustomerIdentityException(
            tenantId
        );
    }

    return Optional.of(matches.get(0));
}
```

`DuplicateCustomerIdentityException` là exception domain riêng.

### 9.1. Vì sao giới hạn 2, không giới hạn 1?

Để phân biệt ba trạng thái `0`, `1`, `2+`, tối đa **hai** kết quả là đủ cho tình huống entity query đơn giản.

### 9.2. Giới hạn hai chỉ là phương pháp kiểm tra cardinality

Nó không thay database UNIQUE constraint, không thay transaction isolation và không đảm bảo phát hiện mọi duplicate nếu query dùng collection fetch join, pagination in-memory hoặc projections làm cardinality khó diễn giải.

### 9.3. Tránh collection fetch join trong phép kiểm tra uniqueness

Nếu mục tiêu là kiểm tra một Customer theo business key, query entity root đơn giản và đúng predicate. Fetch children bằng query riêng/fetch plan sau khi xác định Customer phù hợp nếu cần.

### 9.4. Thao tác không đảm bảo atomic với writers

Query `setMaxResults(2)` chỉ quan sát kết quả tại thời điểm query/transaction semantics. Một transaction khác vẫn có thể INSERT duplicate giữa read và write nếu không có unique constraint hoặc locking/isolation phù hợp.

### 9.5. Khi nào nên chọn cách này?

Có thể hợp lý nếu team thích `List` + explicit branching, muốn quan sát `0/1/>1` hoặc cần code chạy trên JPA version không có `getSingleResultOrNull()`. Nếu provider có `getSingleResult()` ổn định và not-found là exception đúng domain, không cần viết lại mọi query.

---

## 10. `setMaxResults(1)` không chứng minh uniqueness

Anti-pattern:

```java
Customer customer = em.createQuery(
        """
        SELECT c FROM Customer c
        WHERE c.normalizedEmail = :email
        """,
        Customer.class
    )
    .setParameter("email", email)
    .setMaxResults(1)
    .getSingleResult();
```

Nếu có nhiều Customers trùng email, query vẫn có thể trả một result do LIMIT/row restriction. Caller tưởng hợp đồng “một Customer duy nhất” được thỏa mãn.

### 10.1. Khi `setMaxResults(1)` là đúng

Nếu requirement là “lấy **sự kiện mới nhất** theo thời gian, chấp nhận có nhiều events”:

```java
List<LoginEvent> latest = em.createQuery(
        """
        SELECT e FROM LoginEvent e
        WHERE e.userId = :userId
        ORDER BY e.createdAt DESC, e.id DESC
        """,
        LoginEvent.class
    )
    .setParameter("userId", userId)
    .setMaxResults(1)
    .getResultList();
```

Đây là hợp đồng **chọn một phần tử theo thứ tự**, không phải xác nhận uniqueness.

### 10.2. Luôn có ORDER BY khi “lấy đầu tiên” theo nghiệp vụ

Không có ordering rõ ràng, database có thể trả những rows khác nhau sau khi thay query plan/indexes. Thêm tie-breaker ổn định, chẳng hạn `id DESC`.

### 10.3. “First” không có nghĩa dữ liệu unique

`findFirstBy...` trong repository cũng là chọn theo một chính sách, không thay unique constraint.

---

## 11. Hành vi đặc biệt của aggregate queries

Không phải tất cả query không match entity rows đều ném `NoResultException`.

### 11.1. COUNT trả một aggregate result

```java
Long count = em.createQuery(
        """
        SELECT COUNT(c)
        FROM Customer c
        WHERE c.tenantId = :tenantId
          AND c.normalizedEmail = :email
        """,
        Long.class
    )
    .setParameter("tenantId", tenantId)
    .setParameter("email", email)
    .getSingleResult();
```

Ngay cả khi không có Customer khớp, `COUNT` không có GROUP BY thường trả **một scalar result bằng 0**, nên không có `NoResultException`.

### 11.2. SUM/AVG/MIN/MAX trên tập rỗng

```java
BigDecimal total = em.createQuery(
        """
        SELECT SUM(p.amount)
        FROM Payment p
        WHERE p.orderId = :orderId
        """,
        BigDecimal.class
    )
    .setParameter("orderId", orderId)
    .getSingleResult();
```

Với tập rỗng, các aggregate khác COUNT có thể trả **một result mang giá trị `null`**, không nhất thiết ném `NoResultException`.

Vì vậy phải phân biệt:
- Không có **result row**.
- Có một **result row với scalar value null**.

### 11.3. GROUP BY thay đổi số result

```java
SELECT c.status, COUNT(c)
FROM Customer c
GROUP BY c.status
```

Có thể trả nhiều groups hoặc không có group nào. Nếu gọi `getSingleResult()`, `NonUniqueResultException` có thể xuất hiện khi có nhiều groups; không có group có thể dẫn đến NoResult. Dùng `getResultList()` cho báo cáo grouped aggregates.

### 11.4. HAVING và điều kiện query

Một aggregate với GROUP BY/HAVING có thể loại bỏ các nhóm. Không áp dụng suy luận “mọi aggregate đều trả đúng một result” một cách máy móc.

### 11.5. Scalar NULL và Optional

`Optional.of(query.getSingleResult())` sẽ ném `NullPointerException` nếu scalar result là null. Nếu scalar query có thể trả null, dùng `Optional.ofNullable(...)` và xác định có cần phân biệt null aggregate với hoàn toàn không có result hay không.

---

## 12. `NoResultException` khác `null` trong result

Xét:

```java
String alias = em.createQuery(
        """
        SELECT c.nickname
        FROM Customer c
        WHERE c.id = :id
        """,
        String.class
    )
    .setParameter("id", id)
    .getSingleResult();
```

Có thể có hai tình huống:

1. Không có Customer với ID: query có **0 results**, `getSingleResult()` ném `NoResultException`.
2. Có Customer nhưng `nickname` là SQL NULL: query có **1 result** với value `null`, `getSingleResult()` có thể trả null.

Hai trường hợp có ý nghĩa khác nhau. Nếu nghiệp vụ cần phân biệt “Customer không tồn tại” với “Customer có nickname null”, query entity hoặc projection có dấu nhận diện khác, thay vì chỉ trả một scalar nullable.

### 12.1. `getSingleResultOrNull` có thể làm hai trạng thái này trông giống nhau

Một method trả null cho no result có thể trả null cả khi scalar result null. Nếu caller cần phân biệt, dùng query/mô hình kết quả khác.

### 12.2. Tránh catch NoResult rồi coi như null field

Không tìm thấy entity là khác với thuộc tính của entity tồn tại nhưng rỗng. Hợp đồng dữ liệu phải thể hiện được sự khác biệt đó.

---

## 13. JOIN làm cardinality khó hiểu hơn

Một query:

```java
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.orderNumber = :number
```

có thể tạo nhiều SQL joined rows nếu Order có nhiều Lines, dù cùng một Order root.

### 13.1. Result cardinality là điều JPA Query API nhìn thấy

`getSingleResult()` kiểm tra cardinality của **query results** sau khi provider xử lý mapping/projection. Không kết luận chỉ từ số SQL rows mà provider trả đúng một hay nhiều entity results.

### 13.2. DISTINCT khi cần một entity root

```java
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.orderNumber = :number
```

`DISTINCT` có thể loại duplicate entity results do join tạo ra. Nhưng nó **không sửa** dữ liệu có hai Orders khác nhau cùng `orderNumber`.

### 13.3. Collection fetch join và provider behavior

Với `JOIN FETCH o.lines`, Hibernate và những providers/versions khác có thể de-duplicate entity roots theo cách khác nhau, đặc biệt khi pagination. Không dùng `setMaxResults(2)` trên một fetch join to-many phức tạp như bằng chứng chắc chắn về uniqueness.

### 13.4. Projection có thể tạo nhiều results dù root unique

```java
SELECT l.productId
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.orderNumber = :number
```

Nếu Order có năm lines, đây là **năm scalar results**. `getSingleResult()` là lựa chọn sai, kể cả database có UNIQUE(order_number).

### 13.5. Query theo ID trước, fetch graph sau

Nếu cần uniqueness của Order theo business key, tra Order root đơn giản. Sau khi có root, tải associations theo fetch plan riêng của use case.

---

## 14. DISTINCT không thay UNIQUE constraint

`SELECT DISTINCT c` loại duplicate **query results** theo SQL/JPA semantics. Nó không ngăn hai entity rows khác nhau có cùng email.

Ví dụ dữ liệu:

```text
id  tenant_id  normalized_email
1   10         a@example.com
2   10         a@example.com
```

Query:

```java
SELECT DISTINCT c
FROM Customer c
WHERE c.tenantId = 10
  AND c.normalizedEmail = 'a@example.com'
```

vẫn có **hai Customers khác identity**. Đây là vi phạm business uniqueness nếu contract đòi tối đa một.

### 14.1. GROUP BY không phải cách che duplicate

Gộp kết quả theo email rồi lấy một arbitrary `MAX(id)` có thể làm mất dữ liệu/ẩn lỗi. Chỉ dùng aggregation nếu nghiệp vụ **thực sự** muốn aggregate hoặc có rule chọn bản ghi.

### 14.2. DISTINCT có thể tác động hiệu năng

`DISTINCT` trên query có join lớn có thể thêm sorting/hashing và thay SQL execution plan. Nên hiểu nguyên nhân duplicate trước khi thêm DISTINCT.

---

## 15. `EntityManager.find()` có hợp đồng khác

Tra primary key:

```java
Customer customer =
    em.find(Customer.class, customerId);

if (customer == null) {
    throw new CustomerNotFoundException(
        tenantId, null, null
    );
}
```

`find` có semantics entity-or-null cho một primary key. Không mong `NoResultException` từ `find` chỉ vì không có row.

### 15.1. Primary key đại diện identity uniqueness

Database phải bảo vệ primary key, nên lỗi duplicate PK về nguyên tắc xuất hiện khi ghi/migration, không phải trạng thái query `find` trả nhiều rows.

### 15.2. Tenant authorization vẫn cần

`find(Customer.class, id)` không tự áp điều kiện tenant trên một trường business bình thường. Nếu ID do client đưa vào, cần kiểm tra ownership hoặc query scoped:

```java
SELECT c FROM Customer c
WHERE c.id = :id
  AND c.tenantId = :tenantId
```

Đừng làm lộ liệu một ID của tenant khác có tồn tại.

### 15.3. `getReference()` không tương đương `find()`

`em.getReference()` có thể trả lazy reference và phát hiện entity không tồn tại khi truy cập state theo provider semantics, thường qua `EntityNotFoundException`. Không dùng nó như API portable để kiểm tra tồn tại ngay lập tức.

---

## 16. Criteria API có cùng cardinality contract

Criteria Query chỉ thay cách xây query, không thay semantics của `getSingleResult`.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> root = cq.from(Customer.class);

cq.select(root)
  .where(
      cb.and(
          cb.equal(root.get("tenantId"), tenantId),
          cb.equal(root.get("normalizedEmail"), email)
      )
  );

TypedQuery<Customer> query = em.createQuery(cq);

Customer customer = query.getSingleResult();
```

Tùy result:
- 0 → `NoResultException`.
- 1 → Customer.
- nhiều → `NonUniqueResultException`.

### 16.1. Static metamodel

Nếu có generated `Customer_`:

```java
cb.equal(root.get(Customer_.tenantId), tenantId)
```

có thể giúp giảm lỗi tên field. Nhưng static metamodel không tự bảo vệ uniqueness dữ liệu.

### 16.2. Criteria JOIN cũng có thể nhân results

Một Criteria query join to-many vẫn cần xem result cardinality, DISTINCT và query purpose tương tự JPQL.

---

## 17. NamedQuery và native query

`@NamedQuery` là cách đặt tên query tại mapping/configuration:

```java
@NamedQuery(
    name = "Customer.byTenantEmail",
    query = """
        SELECT c FROM Customer c
        WHERE c.tenantId = :tenantId
          AND c.normalizedEmail = :email
        """
)
@Entity
public class Customer {
    // ...
}
```

Gọi:

```java
Customer c = em.createNamedQuery(
        "Customer.byTenantEmail",
        Customer.class
    )
    .setParameter("tenantId", tenantId)
    .setParameter("email", email)
    .getSingleResult();
```

Exception semantics của `getSingleResult()` không biến đổi vì query có tên.

### 17.1. Native query

```java
Object result = em.createNativeQuery(
        """
        SELECT normalized_email
        FROM customer
        WHERE tenant_id = ?1
          AND id = ?2
        """
    )
    .setParameter(1, tenantId)
    .setParameter(2, customerId)
    .getSingleResult();
```

Native query vẫn có cardinality semantics tương ứng JPA Query API. Nhưng scalar JDBC/JPA result types, mapping và database dialect có thể khác JPQL typed query.

### 17.2. Đừng suy luận tên query quyết định uniqueness

Một named query tên `findUniqueCustomer` không tạo unique constraint. Hợp đồng phải được hỗ trợ bằng dữ liệu/schema và tests.

---

## 18. Khi nào `NonUniqueResultException` là lỗi nghiêm trọng?

Ví dụ repository cam kết:

```java
Optional<Customer> findByTenantAndEmail(
    long tenantId,
    String email
);
```

Nếu database thực sự cho phép nhiều Customers cùng key, có hai khả năng:

1. **Query contract sai**: email không unique như business tưởng; cần trả List hoặc xác định rule chọn một.
2. **Data invariant sai**: đáng lẽ phải unique nhưng schema/migration/writers đã tạo duplicate.

Cả hai đều cần **chẩn đoán**, không nên đổi ngay sang `setMaxResults(1)`.

### 18.1. Dữ liệu duplicate và business impact

Nếu hai Customer records cùng email thuộc tenant, hệ thống có thể:
- Gửi thông tin cho sai người.
- Ghi payment dưới account sai.
- Gắn order vào Customer tùy ý.
- Phát sinh authorization leak.
- Tạo identity mapping không ổn định.

### 18.2. Phân biệt duplicate do query join

Trước khi kết luận dữ liệu duplicate, xem query có JOIN to-many/projection không. Có thể dữ liệu root unique nhưng query shape tạo nhiều results.

### 18.3. NonUnique không phải kết quả “có cũng được”

Một optional single lookup hứa tối đa một. Khi có hai, lời hứa đã bị vi phạm; optional empty không giải quyết được.

---

## 19. Unique constraint là lớp bảo vệ cần thiết

Annotation:

```java
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {
            "tenant_id",
            "normalized_email"
        }
    )
)
```

Có thể hỗ trợ generate DDL, nhưng trong production nên quản lý schema qua migrations và xác minh constraint tồn tại thật.

SQL:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_email
UNIQUE (tenant_id, normalized_email);
```

### 19.1. Tại sao không chỉ SELECT trước INSERT?

Hai transactions cùng chạy:

```text
Transaction A                 Transaction B
---------------------------   ---------------------------
SELECT -> 0 rows              SELECT -> 0 rows
INSERT same email             INSERT same email
COMMIT                        COMMIT
```

Nếu không có database constraint/concurrency control, cả hai có thể tạo duplicate. Precheck chỉ cho trải nghiệm thông báo sớm, không thay uniqueness ở DB.

### 19.2. Conflict có thể xuất hiện tại flush/commit

Unique violation thường phát sinh khi INSERT/UPDATE được gửi tới DB hoặc khi constraint được kiểm tra. Nó có thể được provider/Spring translate thành `PersistenceException`/`DataIntegrityViolationException`, **không phải** `NonUniqueResultException` vì không phải lỗi một single-result read.

### 19.3. Không phải constraint nào cũng portable giữa databases

Unique NULL handling, case-insensitive collation, functional indexes, partial indexes và deferrable constraints khác nhau theo vendor. Phải test DB target.

### 19.4. Không tạo constraint từ `@Table` rồi tưởng migration đã chạy

Annotation là mapping metadata. Nếu ứng dụng không bật automatic schema generation hoặc dùng migration tool, cần bảo đảm DDL tương ứng đã được áp dụng trên database thật.

---

## 20. Soft delete làm uniqueness phức tạp hơn

Có thể có rule:

> Trong mỗi tenant, tối đa một Customer **đang active** được phép dùng một normalizedEmail; các records đã soft-delete có thể giữ lại lịch sử.

Nếu query chỉ lọc email mà không lọc `deleted=false`, bản ghi cũ + mới có thể trả nhiều rows:

```java
SELECT c FROM Customer c
WHERE c.tenantId = :tenantId
  AND c.normalizedEmail = :email
  AND c.deleted = false
```

### 20.1. Business contract phải định nghĩa active

Một lookup để đăng nhập thường chỉ cần active Customer. Một audit lookup có thể cần cả deleted records và nên dùng List thay vì single.

### 20.2. Unique constraint phải đồng bộ với rule

Một unique constraint trên `(tenant_id, normalized_email)` ngăn duplicate cả khi soft-deleted. Nếu policy cho phép reuse, cần thiết kế schema khác (ví dụ filtered/partial unique index ở DB hỗ trợ hoặc một identity table riêng), không chỉ thêm `deleted=false` vào JPQL.

### 20.3. Không phụ thuộc provider filter một cách mù quáng

Hibernate filters/soft-delete mapping là tính năng/cấu hình theo phiên bản và có thể ảnh hưởng mọi query. Hợp đồng truy vấn cần rõ liệu deleted rows có được loại trừ tự động hay không.

---

## 21. Email case-insensitive uniqueness cần thống nhất

Giả sử hai rows:

```text
User@Example.com
user@example.com
```

Các databases/collations có thể xử lý so sánh và unique constraint khác nhau.

Một số chiến lược:
- Lưu `normalizedEmail` theo quy tắc đã thống nhất.
- Dùng unique index trên biểu thức/collation nếu DB hỗ trợ.
- Kiểm tra cùng quy tắc trong application service và database.
- Quản lý migration khi chuyển normalization policy.

### 21.1. Không viết `LOWER()` rồi nghĩ đã bảo đảm uniqueness

```java
WHERE LOWER(c.email) = LOWER(:email)
```

có thể làm query trả hai Customers cũ có email khác case. Nếu không có unique constraint tương ứng, `NonUniqueResultException` vẫn có thể xuất hiện.

### 21.2. Unicode và locale

Normalization email và usernames có nhiều cạnh kỹ thuật (case folding, Unicode, local part policy). Đừng áp dụng quy tắc chung không được business chấp nhận rồi coi là identity đúng cho mọi hệ thống.

---

## 22. Transaction semantics của hai JPA exceptions

Điểm quan trọng trong đặc tả JPA: **`NoResultException` và `NonUniqueResultException` không khiến transaction hiện tại tự động bị đánh dấu rollback-only chỉ vì chính exception đó được JPA ném ra**.

Điều này có nghĩa JPA không coi hai kết quả cardinality là loại lỗi transaction-level bắt buộc hủy mọi việc đã làm.

### 22.1. Không suy luận mọi RuntimeException JPA đều rollback giống nhau

Một số persistence failures khác có thể khiến transaction marked rollback-only; NoResult/NonUnique có quy tắc riêng trong JPA API.

### 22.2. Ứng dụng vẫn có thể quyết định rollback

Một command đã sửa inventory rồi phát hiện thiếu Customer bắt buộc phải rollback toàn command, dù JPA `NoResultException` tự nó không yêu cầu rollback. Quyết định thuộc **hợp đồng nghiệp vụ/transaction owner**.

### 22.3. Phân biệt exception của JPA và quy tắc Spring

Spring `@Transactional` thường rollback trên unchecked exception nếu exception **thoát ra khỏi transactional method/proxy** theo default rollback rules. Điều đó bao gồm một exception domain hoặc một `NoResultException` không bị xử lý.

Vì vậy hai câu sau có thể cùng đúng:

- Theo JPA, riêng `NoResultException` không tự mark transaction rollback-only.
- Theo Spring, khi unchecked exception thoát ra từ `@Transactional` method, transaction interceptor có thể đánh dấu rollback.

### 22.4. Catch bên trong service có thể làm transaction tiếp tục

```java
@Transactional
public void optionalLookupAndContinue() {
    try {
        Customer c = singleQuery.getSingleResult();
        // ...
    } catch (NoResultException ex) {
        // "Not found" là trạng thái bình thường.
    }

    // Có thể tiếp tục nếu transaction vẫn hợp lệ
    // và nghiệp vụ cho phép.
}
```

Tuy nhiên không nên đoán state transaction chỉ từ tên exception nếu trước đó đã có lỗi khác hoặc framework/provider đã đánh dấu rollback vì nguyên nhân khác.

---

## 23. RESOURCE_LOCAL: Xử lý trong transaction

Ví dụ JPA thuần:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Optional<Customer> result;

    try {
        Customer c = em.createQuery(
                """
                SELECT c FROM Customer c
                WHERE c.tenantId = :tenant
                  AND c.normalizedEmail = :email
                """,
                Customer.class
            )
            .setParameter("tenant", tenantId)
            .setParameter("email", normalizedEmail)
            .getSingleResult();

        result = Optional.of(c);
    } catch (NoResultException ex) {
        result = Optional.empty();
    }

    // Xử lý nghiệp vụ tiếp theo khi transaction hợp lệ.
    tx.commit();

} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }
    throw failure;
} finally {
    em.close();
}
```

Mẫu trên chỉ minh họa transaction ownership và catch NoResult theo optional contract. Trong ứng dụng thực tế, biến `result` nên được sử dụng/trả theo service design, và mọi changes đã tạo trước đó cần được đánh giá trước khi commit.

### 23.1. Khi NonUnique xuất hiện

Nếu contract đòi một Customer duy nhất, có thể để NonUnique đi vào catch ngoài để rollback command. Hoặc translate thành domain exception và để transaction owner xử lý.

### 23.2. Không gọi commit khi DB/transaction đã lỗi

`NoResultException` có JPA semantics riêng, nhưng một lỗi SQL/flush khác có thể đã làm transaction rollback-only. Không catch tất cả persistence exceptions rồi cố commit.

---

## 24. Spring @Transactional: Ngoại lệ thoát ra và rollback

Ví dụ:

```java
@Service
public class CustomerCommandService {

    private final CustomerRepository repository;

    @Transactional
    public void updateEmail(long customerId, String email) {

        Customer customer =
            repository.requireCustomer(customerId);

        customer.changeEmail(email);
    }
}
```

Nếu `requireCustomer` ném `CustomerNotFoundException extends RuntimeException` và exception thoát khỏi method, Spring transaction interceptor thường đánh dấu rollback theo default.

### 24.1. Read-only query

Nếu method chỉ tra dữ liệu:

```java
@Transactional(readOnly = true)
public Optional<Customer> lookup(...) {
    return repository.findByTenantAndEmail(...);
}
```

`Optional.empty()` thường là kết quả bình thường, không cần exception/rollback. Nhưng read-only transaction không tự tạo uniqueness và không biến một database read replica thành strongly consistent source.

### 24.2. Catch ở ngoài proxy khác catch bên trong proxy

```java
try {
    service.updateEmail(...);
} catch (CustomerNotFoundException ex) {
    // Transaction của service có thể đã rollback.
}
```

Khác với việc bắt not found bên trong service rồi tiếp tục cùng transaction. Hãy hiểu transaction interceptor đặt ở đâu.

### 24.3. noRollbackFor là chính sách riêng

Spring hỗ trợ cấu hình rollback rules, nhưng không nên sử dụng `noRollbackFor` chỉ để che một data integrity failure. Thay vào đó, thiết kế rõ các trường hợp `0` bình thường (`Optional`) và các command phải rollback.

---

## 25. Spring Data JPA và Optional<T>

Một repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer>
        findByTenantIdAndNormalizedEmail(
            Long tenantId,
            String normalizedEmail
        );
}
```

Ngữ nghĩa khai báo mong muốn:

- Không có Customer → `Optional.empty()`.
- Một Customer → `Optional.of(customer)`.
- Nhiều Customers → vi phạm single-result contract, thường được biểu diễn qua exception của Spring Data/provider.

### 25.1. Không cam kết exception class duy nhất trên mọi phiên bản

Spring exception translation có thể chuyển JPA `NonUniqueResultException` thành `IncorrectResultSizeDataAccessException` hoặc những exceptions trong hierarchy DataAccessException tùy query path/version. Không viết code chỉ bắt một concrete vendor exception ở mọi tầng và khẳng định portable.

### 25.2. Derived query không tạo DB UNIQUE

Tên `findByTenantIdAndNormalizedEmail` diễn đạt query structure. Database unique constraint vẫn là lớp bảo vệ khi nhiều transactions insert/update.

### 25.3. @Query cũng có contract tương tự

```java
@Query("""
    SELECT c FROM Customer c
    WHERE c.tenantId = :tenantId
      AND c.normalizedEmail = :email
    """)
Optional<Customer> findUnique(
    @Param("tenantId") Long tenantId,
    @Param("email") String normalizedEmail
);
```

Return type Optional có nghĩa method kỳ vọng tối đa một entity, không làm duplicates biến mất.

### 25.4. `findFirstBy`/`findTopBy`

```java
Optional<LoginEvent>
    findFirstByUserIdOrderByCreatedAtDescIdDesc(
        Long userId
    );
```

Hợp lý với query “latest event”, **không** dùng để né data duplicate của business key vốn phải unique.

---

## 26. Exception translation qua các tầng

Một hệ thống thường có nhiều lớp:

```text
Database / JDBC
       |
JPA provider (Hibernate/EclipseLink)
       |
PersistenceException / NoResult / NonUnique
       |
Spring DataAccessException translation (nếu dùng)
       |
Repository/service domain contract
       |
HTTP/API error mapping
```

### 26.1. Không expose JPA exception trực tiếp tới client

Một API công khai không nên trả stack trace, JPQL query, table names hay normalizedEmail của người khác. Service nên chuyển tình huống có ý nghĩa nghiệp vụ thành mã lỗi rõ ràng.

### 26.2. Nguyên tắc translate có chọn lọc

- `NoResultException` trong query optional → Optional.empty.
- `NoResultException` trong query required → `CustomerNotFoundException`.
- `NonUniqueResultException` trong unique lookup → data integrity/ambiguous lookup exception.
- SQL timeout/connection/mapping errors → infrastructure error policy khác.
- Unique constraint failure khi INSERT → conflict policy riêng, không phải NonUniqueResultException.

### 26.3. Giữ cause để chẩn đoán

Domain exception có thể giữ exception gốc trong cause chain, nhưng response ra client nên dùng message/codes đã được kiểm soát.

---

## 27. Mapping HTTP status theo nghiệp vụ

Không có bảng “NoResultException luôn = HTTP 404”. HTTP mapping phụ thuộc API contract.

| Tình huống | Response thường phù hợp | Lý do |
|---|---|---|
| `GET /customers/{id}` không có resource trong scope | 404 | Resource không được tìm thấy |
| `GET /customers?email=...` là search | 200 + list rỗng, hoặc contract khác | Search không có kết quả có thể bình thường |
| Create flow kiểm tra email chưa dùng | Không có Customer là trạng thái hợp lệ | Không phải HTTP 500 |
| Request cố liên kết một Customer bắt buộc không tồn tại | 404/422 tùy API semantics | Input reference không hợp lệ |
| Unique lookup trả nhiều Customers | 500/incident hoặc error code nội bộ | Dữ liệu/query vi phạm invariant |
| Client gửi key trùng khi tạo mới | 409 trong nhiều API designs | Conflict với unique constraint |
| Database unavailable | 503/5xx theo vận hành | Không thể coi là “not found” |
| Cross-tenant ID | 404/403 theo security policy | Tránh lộ existence |

### 27.1. Không tự động map NonUnique thành 409

Nếu client chỉ đọc theo email nhưng DB có duplicate sai, đây thường là lỗi server/data integrity. `409` thường dùng cho conflict do request hợp lệ gây ra hoặc resource state conflict, chứ không phải mọi lỗi dữ liệu nội bộ.

### 27.2. Không tiết lộ identity của bản ghi thứ hai

Nếu `NonUnique` liên quan email/username, response không nên liệt kê các Customer IDs của người khác. Log correlation ID và context đã được redacted.

---

## 28. Logging và monitoring hai lỗi

`NoResultException` trên optional lookup có thể là normal path. Nếu log ERROR và stack trace mỗi lần, hệ thống sẽ tràn logs và cảnh báo giả.

### 28.1. Phân loại observability

- Optional no result: có thể chỉ metric hoặc DEBUG nếu cần.
- Required no result: WARN/INFO tùy nghiệp vụ, không tự coi database outage.
- NonUnique trên unique contract: ERROR/alert vì cần kiểm tra dữ liệu hoặc query.
- Infrastructure failure: ERROR theo timeout/connection policy.

### 28.2. Metadata log hữu ích

Log có thể chứa:
- Query name hoặc use-case identifier.
- Tenant ID nếu policy cho phép.
- Correlation/request ID.
- Result cardinality category.
- Provider exception class/cause (internal).
- Transaction/operation type.
- Schema migration/version reference.

Tránh ghi raw password, access token, toàn email hoặc dữ liệu cá nhân không cần thiết.

### 28.3. Số lần no-result cao không luôn có lỗi

Một autocomplete/search endpoint có thể thường xuyên trả empty. Quan sát tỷ lệ cùng bối cảnh nghiệp vụ, đừng alert chỉ vì thấy NoResultException nếu code đã dùng hợp đồng optional hợp lý.

### 28.4. NonUnique phải có quy trình xử lý

Khi xảy ra duplicate bất thường, cần biết team nào chịu trách nhiệm dữ liệu, có migration để dọn dữ liệu không, và constraint nào nên được áp dụng sau remediation.

---

## 29. Có nên retry khi NoResultException?

Thông thường, **retry cùng query ngay lập tức không làm bản ghi xuất hiện** nếu không có một nguyên nhân transient rõ ràng.

### 29.1. Read-after-write / eventual consistency

Nếu hệ thống đọc từ read replica hoặc projection có độ trễ, không tìm thấy có thể là tình trạng tạm thời. Khi đó retry phải dựa trên thiết kế consistency (read primary, bounded retries, backoff, SLA) chứ không phải vì NoResultException nói rằng DB hỏng.

### 29.2. Retry trong transaction snapshot

Dưới isolation có snapshot cố định, lặp lại cùng query trong cùng transaction có thể tiếp tục thấy snapshot cũ. Hãy hiểu isolation level trước khi thiết kế retry.

### 29.3. Không retry vô hạn

Một resource không tồn tại thực sự không nên giữ request chờ quá lâu. Nên có timeout và trả trạng thái phù hợp.

---

## 30. Có nên retry khi NonUniqueResultException?

Thông thường **không**. Nếu query trả nhiều results vì dữ liệu duplicate hoặc query contract sai, chạy lại sẽ rất có khả năng nhận cùng kết quả.

### 30.1. Trước khi retry hãy xác định nguyên nhân

- JOIN tạo result multiplicity?
- Thiếu tenant predicate?
- Thiếu soft-delete/active status filter?
- Thiếu effective date/validity interval?
- Dữ liệu lịch sử được phép trùng?
- Database unique constraint chưa tồn tại?
- Query projection trả nhiều scalar/tuple rows?

### 30.2. Không tự chọn record có ID nhỏ nhất

Một lệnh:

```java
ORDER BY c.id
setMaxResults(1)
```

có thể ẩn duplicate nghiêm trọng. Chỉ dùng khi **business contract định nghĩa rõ** bản ghi ưu tiên, ví dụ effective configuration với priority/validity rules.

### 30.3. Data repair không nên nằm trong catch

Không viết code tự xóa/sáp nhập một Customer ngay trong catch NonUnique mà chưa có domain migration/approval. Duplicate identity có thể liên quan orders, payments và permissions.

---

## 31. “Latest active configuration” là hợp đồng khác unique config

Ví dụ mỗi tenant có nhiều versions của cấu hình và API cần **bản mới nhất đang hiệu lực**.

```java
List<TenantConfiguration> configs = em.createQuery(
        """
        SELECT c FROM TenantConfiguration c
        WHERE c.tenantId = :tenantId
          AND c.active = true
        ORDER BY c.effectiveFrom DESC, c.id DESC
        """,
        TenantConfiguration.class
    )
    .setParameter("tenantId", tenantId)
    .setMaxResults(1)
    .getResultList();
```

Đây là hợp đồng **chọn result theo precedence rule**, không phải assert database chỉ có một active configuration.

### 31.1. Thời gian hiệu lực có thể cần điều kiện

Nếu business rule là đúng một config active cho mỗi thời điểm, query cần predicate theo `effectiveFrom/effectiveTo`, và constraint/non-overlap policy phù hợp.

### 31.2. Không nhầm “first” với “unique”

Việc chọn mới nhất là ý định nghiệp vụ khác với integrity rule của unique business key.

---

## 32. Hai câu truy vấn `COUNT` rồi `SELECT` không bảo đảm atomic

Anti-pattern:

```java
Long count = countMatchingCustomers(...);

if (count == 1L) {
    return findMatchingCustomer(...);
}
```

Giữa hai queries, transaction khác có thể INSERT/DELETE/UPDATE, tùy isolation level. Dẫn đến kết quả không nhất quán:

```text
A: COUNT -> 1
B: DELETE matching Customer -> COMMIT
A: SELECT -> 0
```

Hoặc:

```text
A: COUNT -> 1
B: INSERT duplicate -> COMMIT
A: SELECT -> 2
```

### 32.1. Hướng đúng

Một `getSingleResult()` hoặc `getResultList()` với max 2 quan sát cardinality trong **một query operation**, và unique constraint bảo vệ write invariant. Nếu phải bảo vệ nhiều-step decision, dùng transaction isolation/locking/conditional DML phù hợp.

### 32.2. COUNT chỉ để tồn tại có thể tốn chi phí

Nếu business chỉ cần “có ít nhất một row không?”, một query được thiết kế để tìm existence có thể hiệu quả hơn COUNT toàn bộ. Nhưng đừng làm tối ưu đó phá contract về uniqueness.

---

## 33. Kết quả không unique do dữ liệu bị duplicate

Một quy trình điều tra nội bộ:

1. Xác định query, parameters và tenant scope từ logs/metrics an toàn.
2. Kiểm tra JPQL có join/projection gây multiplicity không.
3. Chạy diagnostic SQL theo cùng filter trên dữ liệu đã kiểm soát.
4. Xác định các distinct entity IDs cùng business key.
5. Kiểm tra migration/constraint state.
6. Xác định writer đã tạo duplicate.
7. Sửa logic ghi và backfill/dedupe theo domain rule.
8. Thêm database UNIQUE constraint hoặc index phù hợp.
9. Viết regression test cho concurrent create/update.
10. Monitor incident sau rollout.

### 33.1. Dedupe có thể không đơn giản

Hai Customers trùng email có thể đều có orders, addresses, payments và audit history. Chọn “giữ ID nhỏ nhất” có thể làm mất dữ liệu. Cần business rule và migration an toàn.

### 33.2. Unique index có thể không tạo được khi dữ liệu cũ còn trùng

Đầu tiên cần phát hiện và xử lý duplicates, sau đó áp constraint trong migration. Đừng coi constraint DDL thất bại là một lỗi runtime nhỏ có thể bỏ qua.

---

## 34. Multi-tenant lookup và bảo mật

Sai:

```java
SELECT c FROM Customer c
WHERE c.normalizedEmail = :email
```

Nếu cùng email tồn tại ở nhiều tenants, query có thể trả nhiều Customer và ném NonUnique. Nhưng còn nghiêm trọng hơn: nếu chỉ có một Customer của tenant khác, API có thể trả **dữ liệu không thuộc quyền truy cập**.

Đúng về scope:

```java
SELECT c FROM Customer c
WHERE c.tenantId = :authenticatedTenantId
  AND c.normalizedEmail = :email
```

### 34.1. Tenant ID phải đến từ nguồn đáng tin

Không mặc định dùng tenantId do caller tự gửi là đã được authorize. Service cần xác nhận tenant từ security context hoặc quan hệ được phép.

### 34.2. Đừng dùng “hết NonUnique” làm bằng chứng security đúng

Thiếu tenant predicate có thể chỉ trả một result và không ném exception nhưng vẫn lộ data. Cardinality và authorization là hai requirements độc lập.

### 34.3. Hợp đồng not-found của cross-tenant ID

Một API có thể chọn trả 404 thay vì 403 để không tiết lộ entity của tenant khác có tồn tại. Phải theo security policy nhất quán, không tự quyết định trong repository catch.

---

## 35. DTO projection và Tuple có thể có kết quả không như entity query

Một query:

```java
List<OrderSummary> items = em.createQuery(
    """
    SELECT new com.example.read.OrderSummary(
        o.id, o.orderNumber
    )
    FROM PurchaseOrder o
    JOIN o.lines l
    WHERE o.customer.id = :customerId
    """,
    OrderSummary.class
).setParameter("customerId", customerId)
 .getResultList();
```

Có thể tạo nhiều DTO results do join lines. Khi cần đúng một OrderSummary, phải xác định predicate business key/ID và loại bỏ join multiplicity.

### 35.1. Constructor projection khác entity identity map

Hai DTOs có cùng `o.id` vẫn có thể là hai Java objects khác nhau nếu query trả duplicate rows. Provider entity de-duplication assumptions không nên áp dụng máy móc cho DTO.

### 35.2. Tuple projection

`SELECT o.id, l.productId` có nhiều tuples khi Order có nhiều lines; `getSingleResult()` không hợp lệ nếu query contract cho phép nhiều.

### 35.3. DISTINCT DTO projection

`DISTINCT` có thể giải quyết duplicate tuples giống hệt nhau, nhưng nếu mỗi tuple chứa productId khác nhau, sẽ vẫn có nhiều results.

---

## 36. Exception semantics với query execution failure khác

Không gom tất cả vào NoResult/NonUnique.

| Tình huống | Có thể gặp | Hướng phân loại |
|---|---|---|
| 0 results từ single lookup | `NoResultException` | Cardinality theo contract |
| 2+ results từ single lookup | `NonUniqueResultException` | Cardinality/query/data issue |
| Query parameter chưa bind | `IllegalArgumentException`/provider exception | Programming/config issue |
| JPQL sai | Persistence/provider exception | Code/query issue |
| SQL timeout | QueryTimeout/Persistence exception theo semantics | Infrastructure/timeouts |
| Lock timeout | `LockTimeoutException` trong locking query | Contention policy |
| DB connection failure | Persistence/JDBC exception | Infrastructure |
| INSERT vi phạm unique | Constraint/Persistence exception | Write conflict |
| Optimistic version conflict | `OptimisticLockException` | Concurrency control |
| Entity bị xóa trong khi reference được dùng | `EntityNotFoundException` hoặc khác theo path | Entity lifecycle/reference |

Không catch `PersistenceException` rồi trả `Optional.empty()` cho mọi tình huống. Đó là mất thông tin lỗi nghiêm trọng.

---

## 37. `getResultStream()` không phải phép giải uniqueness miễn phí

JPA cung cấp `getResultStream()` trong những phiên bản hỗ trợ:

```java
Stream<Customer> stream =
    query.getResultStream();
```

Một số provider dùng streaming thực, một số có fallback qua `getResultList().stream()`.

### 37.1. Stream.findFirst() không bảo vệ uniqueness

```java
Customer c = query.getResultStream()
    .findFirst()
    .orElse(null);
```

Cách này có thể bỏ qua duplicate. Nếu contract đòi tối đa một, phải kiểm tra cardinality, không chỉ lấy đầu tiên.

### 37.2. Resource lifecycle

Streaming kết quả có thể gắn với JDBC resources/transaction, tùy provider. Dùng try-with-resources khi cần và không đưa stream còn mở ra ngoài transaction boundary.

### 37.3. Hiệu năng không mặc định tốt hơn

Đối với query cần kiểm tra tối đa hai rows, `setMaxResults(2).getResultList()` thường đơn giản, rõ ràng hơn phụ thuộc provider streaming semantics.

---

## 38. Code mẫu kết hợp hai hợp đồng trong một repository

```java
public final class CustomerLookupRepository {

    private final EntityManager em;

    public CustomerLookupRepository(EntityManager em) {
        this.em = em;
    }

    private TypedQuery<Customer> queryByIdentity(
            long tenantId,
            String email) {

        return em.createQuery(
                """
                SELECT c FROM Customer c
                WHERE c.tenantId = :tenantId
                  AND c.normalizedEmail = :email
                """,
                Customer.class
            )
            .setParameter("tenantId", tenantId)
            .setParameter("email", email);
    }

    public Optional<Customer> findOptional(
            long tenantId,
            String email) {

        try {
            return Optional.of(
                queryByIdentity(
                    tenantId, email
                ).getSingleResult()
            );
        } catch (NoResultException ex) {
            return Optional.empty();
        }
    }

    public Customer require(
            long tenantId,
            String email) {

        return findOptional(tenantId, email)
            .orElseThrow(
                () -> new CustomerNotFoundException(
                    tenantId, email, null
                )
            );
    }
}
```

### 38.1. Cả hai methods vẫn phát hiện NonUnique

`findOptional` không bắt NonUnique, vì đó là vi phạm uniqueness. `require` thừa hưởng behavior đó.

### 38.2. Bổ sung domain normalization trước query

Trong application service, chuẩn hóa email theo policy rồi truyền vào repository. Đừng để mỗi query tự thực hiện một quy tắc khác nhau.

### 38.3. DTO/domain return type

Với read APIs, entity có thể được map thành DTO sau repository. Không dùng detached entity trực tiếp làm API contract nếu có lazy associations, security hoặc serialization concerns.

---

## 39. Testing: 0, 1 và 2+ results

Tối thiểu cần ba bộ fixture cho mỗi single-result query contract.

### 39.1. Case 0

Không seed Customer tương ứng; gọi lookup:

```java
Optional<Customer> found =
    repository.findOptional(tenantId, email);

assertTrue(found.isEmpty());
```

Đối với require:

```java
assertThrows(
    CustomerNotFoundException.class,
    () -> repository.require(tenantId, email)
);
```

### 39.2. Case 1

Seed đúng một Customer có tenantId/email; assert returned ID/value chính xác.

### 39.3. Case 2+

Nếu database đã có unique constraint, **không thể seed hai records vi phạm cùng constraint** trong integration test bình thường. Có các lựa chọn:

- Test một query cố tình không unique, như `WHERE city = :city`, với hai Customers hợp lệ.
- Dùng query join/projection tạo nhiều results theo thiết kế.
- Test duplicate legacy data trong schema/fixture riêng trước migration.
- Dùng repository-level test với provider phù hợp nhưng không giả vờ đã kiểm tra DB uniqueness nếu chỉ mock.

Ví dụ:

```java
TypedQuery<Customer> query = em.createQuery(
    """
    SELECT c FROM Customer c
    WHERE c.city = :city
    """,
    Customer.class
);

query.setParameter("city", "Da Nang");

assertThrows(
    NonUniqueResultException.class,
    query::getSingleResult
);
```

Điều kiện là fixture thực sự có nhiều Customer trong city đó; class mẫu ban đầu cần bổ sung city field cho test này.

### 39.4. Test constraint riêng

Thêm integration test hai concurrent transactions cùng tạo một Customer key và xác nhận database chỉ cho tối đa một transaction commit theo constraint/isolation. Đây là test write-side uniqueness, khác test NonUnique read.

---

## 40. Test transaction semantics trong JPA thuần và Spring

### 40.1. JPA test không tự mark rollback

Có thể mở transaction, thực hiện optional single query không có result, catch `NoResultException`, rồi tiếp tục một thao tác hợp lệ và commit. Điều này kiểm chứng JPA exception semantics trên provider đang dùng.

### 40.2. Spring test về exception thoát proxy

Một `@Transactional` service ném unchecked domain exception ra caller thường bị rollback theo Spring default. Integration test phải gọi qua proxy thực, không tự gọi method trong cùng bean rồi tưởng interceptor đã áp dụng.

### 40.3. Chú ý @Transactional trên test method

Spring test framework có thể rollback test transaction sau khi test kết thúc. Đừng xem dữ liệu biến mất sau test là bằng chứng service `@Transactional` rollback đúng cho exception. Nên dùng transaction boundaries rõ, `TransactionTemplate` hoặc test runner phù hợp để quan sát committed state.

### 40.4. Đừng mix hai trường hợp

Test “JPA NoResult không tự mark rollback” khác với test “Spring rollback vì unchecked exception thoát transactional boundary”. Cả hai đều cần được ghi rõ expectation.

---

## 41. Unit tests không đủ chứng minh JPA cardinality

Một mock:

```java
when(query.getSingleResult())
    .thenThrow(new NoResultException());
```

có thể giúp test exception mapping ở repository adapter, nhưng không chứng minh:
- JPQL thực sự trả 0/2 results.
- Query có đúng tenant predicate.
- Provider de-duplicate entity roots ra sao.
- DB unique constraint tồn tại.
- Transaction rollback semantics hoạt động.
- Aggregate null/COUNT results như mong đợi.

### 41.1. Nên có cả hai loại tests

- Unit test: domain mapping/error policy.
- Integration test: JPA/provider/DB result cardinality, SQL constraints, transaction behaviors.

### 41.2. Test trên DB mục tiêu

H2 có thể khác PostgreSQL, MySQL, SQL Server hoặc Oracle về unique NULL, collation, isolation và SQL execution. Các ràng buộc critical cần test trên DB tương đương production.

---

## 42. Dùng two-result probe để audit contract cũ

Nếu đang nâng cấp một repository legacy chưa rõ dữ liệu unique hay không, có thể tạm dùng `setMaxResults(2)` với query root đơn giản và đo:

```java
List<Customer> matches = query
    .setMaxResults(2)
    .getResultList();

switch (matches.size()) {
    case 0 -> {
        // Không có result theo query.
    }
    case 1 -> {
        // Một result theo query.
    }
    default -> {
        // Ít nhất hai results: review contract/data.
    }
}
```

Ví dụ `switch` sử dụng cú pháp Java hiện đại; nếu dự án dùng Java version cũ hơn, dùng `if/else`.

### 42.1. Không duy trì “silent choose one” sau giai đoạn audit

Nếu phát hiện duplicates, phải quyết định là query đúng trả List hay uniqueness phải được sửa bằng data cleanup + database constraint.

### 42.2. Metrics phải tránh PII

Đếm số single-result lookup có cardinality >1 và ghi query identifier, tenant scope/correlation ID phù hợp, tránh xuất toàn bộ raw emails/addresses.

---

## 43. Một chiến lược phục hồi có cấu trúc

Khi lỗi xảy ra:

```text
               Query kỳ vọng một result
                           |
                           v
                    getSingleResult()
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
      Không có           Một result       Nhiều results
          |                |                |
          v                v                v
    NoResultException     Thành công   NonUniqueResultException
          |                                 |
          v                                 v
    Query contract?                   Kiểm tra query shape
      /       \                       + data invariant
   0..1    exactly 1                        |
     |         |                            v
     v         v                    Join duplication?
 Optional    Domain                       /     \
 empty       not-found                 Có       Không
                                       |          |
                                       v          v
                                  Sửa query   Dọn dữ liệu/
                                  projection  ràng buộc UNIQUE
```

Những nguyên tắc phục hồi:

1. Không biến mọi lỗi thành not-found.
2. Không biến duplicate thành first result nếu contract đòi unique.
3. Không retry vô hạn nếu data/query vẫn không thay đổi.
4. Không “sửa dữ liệu” âm thầm trong một exception handler giao dịch thông thường.
5. Luôn xem xét transaction ownership và dữ liệu đã thay đổi trước lỗi.

---

## 44. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách đúng |
|---|---|---|
| Catch `RuntimeException`, trả null | Che DB failure và bug | Catch đúng `NoResultException` theo contract |
| Catch NonUnique rồi trả empty | Che vi phạm uniqueness | Fail/report + điều tra |
| `setMaxResults(1)` cho unique lookup | Chọn record tùy ý | Unique constraint + single-result API |
| `findFirstBy...` thay unique key | Không phát hiện duplicate | Dùng Optional unique lookup |
| Đếm rồi SELECT như atomic check | Race condition | Một query + DB constraint/locks |
| Không filter tenant | Duplicate/lộ dữ liệu chéo | Authenticated tenant scoping |
| Không filter deleted/status | Lookup trả records ngoài scope | Business predicate đầy đủ |
| Thêm DISTINCT tùy tiện | Che join duplication, tốn SQL | Sửa query shape đúng |
| Dùng getSingleResult trên GROUP BY | Có nhiều groups | getResultList |
| Tưởng COUNT=0 ném NoResult | Sai aggregate semantics | COUNT trả 0 với no-group |
| Tưởng SUM empty luôn ném NoResult | Có thể trả null | Xử lý scalar null |
| Tưởng `find()` ném NoResult | Sai API contract | `find()` trả null nếu không có |
| Tưởng JPA NoResult luôn rollback | Sai JPA exception semantics | Phân biệt JPA và Spring rollback |
| Tưởng Spring không rollback vì JPA không mark | Bỏ qua unchecked exception proxy rule | Test @Transactional behavior |
| Bắt unique-violation INSERT như NonUnique | Nhầm read/write failures | Translate DB constraint exception |
| Chỉ `@Table(uniqueConstraints)` và không migrate | Production không có constraint | Schema migration/verification |
| Chọn customer ID nhỏ nhất khi trùng email | Gán nhầm identity/payments | Domain data repair |
| Log mọi optional miss mức ERROR | Alert noise | Theo query contract |
| Expose raw JPQL/PII ra HTTP | Security/privacy risk | Redacted API errors |
| Retry duplicate query liên tục | Tốn DB, không tự sửa | Điều tra dữ liệu/query |
| Dùng mock để kết luận SQL semantics | Test sai tầng | Provider integration test |

---

## 45. Bài tập thực hành

### Bài 1: Không có Customer trong optional lookup

Repository trả `Optional<Customer>`.

**Đáp án:** Khi 0 result, trả `Optional.empty()`; không coi là infrastructure failure.

### Bài 2: Không có Customer trong required command

Command cập nhật một Customer bắt buộc tồn tại.

**Đáp án:** Translate `NoResultException` thành domain not-found, rollback/HTTP theo command contract.

### Bài 3: Hai Customers trùng email cùng tenant

Query mong `0..1`.

**Đáp án:** NonUnique là vi phạm contract. Không chọn bừa first result; kiểm tra constraint, query, dữ liệu.

### Bài 4: Query theo city có nhiều Customers

**Đáp án:** Dùng `getResultList()`, không `getSingleResult()`.

### Bài 5: COUNT không match

`SELECT COUNT(c) ...` trên tập rỗng, không GROUP BY.

**Đáp án:** Một scalar result 0, không phải NoResult.

### Bài 6: SUM không match

**Đáp án:** Có thể trả scalar null; phân biệt với 0 query results.

### Bài 7: GROUP BY status

**Đáp án:** Trả nhiều groups, dùng List.

### Bài 8: JOIN OrderLines

Một Order có 5 Lines, SELECT Order cùng join.

**Đáp án:** Xem query multiplicity, root DISTINCT/projection và provider behavior; không suy từ 5 SQL rows rằng có 5 distinct Orders.

### Bài 9: Query DTO product IDs theo Order

**Đáp án:** Có thể có nhiều results hợp lệ; dùng List.

### Bài 10: `setMaxResults(1)` unique lookup

**Đáp án:** Che duplicate; không phù hợp.

### Bài 11: `setMaxResults(2)`

**Đáp án:** Có thể dùng để phân biệt 0/1/2+ trong entity root query đơn giản; không thay UNIQUE constraint.

### Bài 12: `getSingleResultOrNull`

**Đáp án:** Có ở Jakarta Persistence 3.2+; trả null nếu không có, vẫn phải xử lý NonUnique; phiên bản cũ không có.

### Bài 13: `EntityManager.find`

**Đáp án:** Theo primary key trả entity/null, không dùng NoResult catch cho absence.

### Bài 14: Unique constraint và concurrency

Hai transactions đều query “chưa có email” trước khi INSERT.

**Đáp án:** Precheck không đủ. Database UNIQUE cần bảo vệ conflicting INSERT.

### Bài 15: Multi-tenant query thiếu tenantId

**Đáp án:** Sửa query scope/security; không chỉ xử lý exception.

### Bài 16: Soft delete

Một record deleted và một active trùng email.

**Đáp án:** Hợp đồng phải quy định chỉ active hay cả history, và unique index/constraint phải phù hợp.

### Bài 17: Case-insensitive email

Hai values khác chữ hoa/thường.

**Đáp án:** Normalization/collation/unique constraint phải nhất quán; LOWER query đơn thuần không ngăn duplicates.

### Bài 18: NoResult trong JPA transaction

**Đáp án:** Riêng NoResult không tự mark rollback-only theo JPA spec; business/framework vẫn có thể rollback.

### Bài 19: Spring unchecked exception thoát @Transactional

**Đáp án:** Spring mặc định rollback theo interceptor rules, dù JPA NoResult tự nó không buộc.

### Bài 20: NonUnique có nên retry?

**Đáp án:** Thường không; chẩn đoán query/data trước.

### Bài 21: Read replica lag gây NoResult

**Đáp án:** Có thể cần read-primary/bounded retry theo consistency contract, không retry vô hạn.

### Bài 22: Search endpoint không match

**Đáp án:** Thường trả 200 + empty list nếu API contract là search; không tự map sang 404.

### Bài 23: GET theo ID không match

**Đáp án:** Thường 404 trong scope được phép, theo security policy.

### Bài 24: Database INSERT unique violation

**Đáp án:** Đây là write-side constraint failure; không phải NonUniqueResultException của getSingleResult.

### Bài 25: Mock JPA query

**Đáp án:** Unit mock test được exception mapping, không chứng minh query thực sự trả 0/2 results hoặc constraint DB tồn tại.

### Bài 26: Spring Data Optional

**Đáp án:** Optional là kỳ vọng tối đa một; khi có nhiều results vẫn có thể ném exception, không biến thành List hay chọn arbitrary entity.

### Bài 27: DTO scalar null

**Đáp án:** Phân biệt một result giá trị null với không có result; cần query/projection phù hợp nếu business cần hai trạng thái khác nhau.

### Bài 28: `findFirstBy...OrderBy...`

**Đáp án:** Hợp lý để lấy bản mới nhất nếu nhiều records hợp lệ và ordering rõ; không chứng minh uniqueness.

---

## 46. Checklist trước khi hoàn thiện một single-result query

1. Query contract là `0..1`, `exactly 1`, `0..n` hay latest/first?
2. Caller có hiểu `Optional.empty()` hay domain exception không?
3. Đã phân biệt không có result và scalar result null?
4. Có dùng `getSingleResult()` đúng trường hợp?
5. Có cân nhắc `getSingleResultOrNull()` theo đúng API version?
6. Có dùng `getResultList()` nếu nhiều records là hợp lệ?
7. Có tránh `setMaxResults(1)` để che duplicate?
8. Nếu dùng `setMaxResults(2)`, query có đơn giản, không collection fetch join/pagination khó đoán?
9. Có kiểm tra JOIN/DTO projection tạo multiple results?
10. Có dùng DISTINCT chỉ khi phù hợp với semantics?
11. Có tenant predicate từ authenticated context?
12. Có filters cho active/deleted/effective date?
13. Có unique constraint/index thực trong production schema?
14. Normalization/collation có nhất quán với unique constraint?
15. Có hiểu race giữa SELECT và INSERT?
16. Có phân biệt duplicate read với unique violation khi write?
17. NoResult có phải trạng thái nghiệp vụ bình thường?
18. NonUnique có được phát hiện/report thay vì nuốt?
19. Có tránh catch rộng mọi PersistenceException như not-found?
20. Có phân biệt JPA rollback semantics và Spring @Transactional rules?
21. Nếu command đã sửa dữ liệu, có policy rollback phù hợp khi lookup thất bại?
22. Có xử lý external writers/migrations gây duplicates?
23. Có telemetry/correlation ID nhưng không log PII?
24. API status mapping có đúng search/resource/command contract?
25. Có unit tests cho error mapping?
26. Có integration tests 0, 1, nhiều results?
27. Có test DB unique constraint và concurrent writes?
28. Có test aggregate COUNT/SUM/GROUP BY nếu dùng?
29. Có test query trên DB target/dialect?
30. Có remediation plan cho duplicate legacy data?

---

## 47. Sơ đồ lựa chọn cách xử lý

```text
                 Query của service/repository
                             |
                             v
                   Hợp đồng số lượng?
            +----------------+------------------+
            |                |                  |
            v                v                  v
           0..1          exactly 1             0..n
            |                |                  |
            v                v                  v
       single-result     single-result      getResultList()
       hoặc bounded 2    query
            |                |
      +-----+------+     +---+----+
      |     |      |     |   |    |
      v     v      v     v   v    v
      0     1     2+     0   1   2+
      |     |      |     |   |    |
      v     v      v     v   v    v
    empty  T     ERROR  NOT  T   ERROR
                         FOUND
      \     /        \        /
       \   /          \      /
        \ /            v    v
      Optional<T>     Chẩn đoán
                     query/data,
                     UNIQUE policy,
                     transaction
```

Nếu mục tiêu là “lấy bản mới nhất” thay vì unique, rẽ sang một contract riêng có `ORDER BY ...` và limit một, với behavior cho empty được xác định rõ.

---

## 48. Tổng kết

1. **`NoResultException` nói truy vấn `getSingleResult()` có 0 results; `NonUniqueResultException` nói có nhiều hơn một result** theo JPA Query API.
2. **Kết quả 0 không luôn là lỗi**. Với hợp đồng `0..1`, có thể trả `Optional.empty()`; với `exactly 1`, translate thành domain not-found.
3. **Kết quả nhiều không luôn là dữ liệu sai**. Nếu nghiệp vụ cho phép nhiều records, phải dùng `getResultList()` thay vì `getSingleResult()`.
4. **Không nuốt `NonUniqueResultException`** trong unique lookup. Nó có thể tiết lộ query shape sai hoặc invariant/constraint bị vi phạm.
5. **`setMaxResults(1)` không bảo vệ uniqueness**. Giới hạn hai kết quả có thể giúp detect multiple matches trong query đơn giản, nhưng vẫn cần DB UNIQUE.
6. **`getSingleResultOrNull()` trong Jakarta Persistence 3.2+** giúp biểu diễn empty mà không ném NoResult; vẫn có NonUnique khi nhiều.
7. **`EntityManager.find()` theo primary key có hợp đồng entity-or-null**; không đồng nhất nó với JPQL single-result query.
8. **COUNT trên tập rỗng thường trả 0, còn SUM/AVG/MIN/MAX có thể trả null** khi không GROUP BY; cần phân biệt scalar null với không có result.
9. **JOIN, fetch join và DTO projection ảnh hưởng result cardinality**; DISTINCT không thay database uniqueness.
10. **Unique constraints, tenant scoping, soft-delete filters và normalization phải nhất quán với query contract**.
11. **JPA NoResult/NonUnique không tự đánh dấu transaction rollback-only theo spec**, nhưng Spring @Transactional có thể rollback khi unchecked exception thoát proxy.
12. **Read-replica lag và eventual consistency có thể làm NoResult tạm thời**; retry chỉ hợp lý khi có consistency policy rõ.
13. **Không chuyển mọi exception thành null/empty**, vì như thế sẽ che lỗi DB, mapping, timeout hoặc constraint violation.
14. **Không tự sửa duplicate trong catch**; chẩn đoán, remediation migration và uniqueness constraint là quy trình riêng.
15. **Kiểm thử cả 0, 1, nhiều results và rollback semantics** trên provider/database thực tế.

Điểm quyết định của bài học là: **trước khi chọn `getSingleResult()` hay viết `catch`, hãy mô tả chính xác hợp đồng truy vấn**. Khi hợp đồng đã rõ, `NoResultException` có thể trở thành `Optional.empty()` hoặc not-found đúng ngữ cảnh, còn `NonUniqueResultException` được xem là tín hiệu cần kiểm tra truy vấn, dữ liệu và ràng buộc uniqueness — thay vì bị che bởi một kết quả chọn ngẫu nhiên.
