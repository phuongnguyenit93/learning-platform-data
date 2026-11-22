# Ảnh hưởng của filter khi tải theo định danh hoặc qua quan hệ theo phiên bản

## 1. Bài toán: query đã ẩn dữ liệu nhưng find(id) lại đọc được?

Giả sử ứng dụng quản lý tài khoản có cột `active_status`:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    account_number VARCHAR(40) NOT NULL,
    active_status BOOLEAN NOT NULL,
    balance NUMERIC(18, 2) NOT NULL
);

INSERT INTO accounts VALUES
    (1, 101, 'A-001', TRUE,  5000.00),
    (2, 101, 'A-002', FALSE,  900.00),
    (3, 101, 'A-003', TRUE,   100.00);
```

Trong giao diện, người dùng chỉ được thấy tài khoản đang hoạt động. Lập trình viên bật Hibernate filter:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);
```

Query:

```hql
select a from Account a order by a.id
```

chỉ trả ID 1 và 3. Nhưng trên một số phiên bản/thiết lập, lệnh:

```java
Account account = session.find(Account.class, 2L);
```

lại có thể trả tài khoản không active.

Tương tự, một `Customer` có thuộc tính `@ManyToOne Account` có thể tải một Account vốn bị filter loại khỏi danh sách. Trong khi đó, `customer.getAccounts()` qua collection `@OneToMany` lại có thể được lọc theo filter.

Đây không đơn giản là bug Hibernate. Các con đường nạp dữ liệu khác nhau có semantics khác nhau, và Hibernate **đã bổ sung lựa chọn mới ở các phiên bản sau** để áp filter lên việc tải bằng khóa.

**Mục tiêu của bài:** phân biệt *entity query*, *tải trực tiếp bằng primary key*, *tải qua to-one*, *tải qua collection*, *Persistence Context/cache* và các thay đổi **Hibernate 6.5 → 6.6 → 7.x**. Từ đó tránh thiết kế soft delete hoặc bảo mật tenant dựa trên giả định sai rằng filter luôn áp dụng ở mọi lối vào.

## 2. Filter là gì và hoạt động ở phạm vi nào?

Hibernate `@Filter` là cơ chế thêm điều kiện SQL động vào những thao tác truy vấn mà mapping hỗ trợ, sau khi một **named filter** được bật cho Hibernate `Session` hiện hành.

Thường có ba thành phần:

1. `@FilterDef`: khai báo tên filter, tham số và một số chính sách.
2. `@Filter`: gắn filter đó vào entity hoặc collection role và xác định điều kiện SQL.
3. `Session.enableFilter(...)`: bật filter, truyền tham số trước khi chạy truy vấn.

Ví dụ:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;
import java.math.BigDecimal;

@Entity
@Table(name = "accounts")
@FilterDef(
    name = "activeAccount",
    parameters = @ParamDef(
        name = "active",
        type = Boolean.class
    )
)
@Filter(
    name = "activeAccount",
    condition = "active_status = :active"
)
public class Account {

    @Id
    private Long id;

    @Column(name = "account_number")
    private String accountNumber;

    @Column(name = "active_status")
    private boolean active;

    @Column(name = "balance")
    private BigDecimal balance;

    protected Account() {}

    public Long getId() { return id; }
    public boolean isActive() { return active; }
}
```

Trong transaction:

```java
Session session = entityManager.unwrap(Session.class);

session.enableFilter("activeAccount")
       .setParameter("active", true);

List<Account> accounts = session.createQuery(
    "select a from Account a order by a.id",
    Account.class
).getResultList();
```

Khi filter đã bật, Hibernate có thể sinh điều kiện tương đương:

```sql
SELECT *
FROM accounts a
WHERE a.active_status = TRUE
ORDER BY a.id;
```

Nhưng **không có nghĩa** Hibernate tự cài một policy database ngăn mọi truy cập tới hàng `active_status = FALSE`. Filter chỉ tác động đến những SQL paths được hỗ trợ và được thực thi trong session có filter hiệu lực.

## 3. Nhìn một entity từ nhiều con đường tải

Cùng một Account có thể được nạp bằng:

| Con đường | Ví dụ | Đặc điểm |
|---|---|---|
| Entity query HQL/JPQL | `select a from Account a` | SQL query có thể áp filter đang bật |
| Criteria query | `criteriaQuery.from(Account.class)` | Tương tự entity query tùy mapping |
| Tải bằng primary key | `em.find(Account.class, id)` | Mặc định Hibernate filter **không áp** trên nhiều phiên bản; có tùy chọn mới từ 6.6 |
| Hibernate load-by-id | `session.byId(Account.class).load(id)` | Đường identifier lookup, phải xét `applyToLoadByKey` |
| Reference/proxy | `em.getReference(Account.class, id)` | Có thể chưa SQL ngay; điều kiện kiểm tra xảy ra khi initialize |
| Quan hệ to-one | `order.getAccount()` với `@ManyToOne` | Target thường tải bằng identifier; có nguy cơ bypass filter mặc định |
| Collection to-many | `customer.getAccounts()` với `@OneToMany` | Filter gắn collection role thường áp khi collection được nạp |
| JOIN trong query | `join fetch c.account` | SQL shape khác lazy by-key; cần kiểm tra generated SQL |
| Native SQL/JDBC | `select * from accounts` | Không tự kế thừa Hibernate `@Filter` |

Do đó cần tránh câu hỏi chung “Filter có hoạt động không?” và thay bằng:

> Filter nào, đặt ở entity hay collection, đã bật lúc nào, thao tác tải cụ thể là gì, SQL có được chạy không, và runtime đang dùng Hibernate phiên bản nào?

## 4. Bảng mốc phiên bản: điểm thay đổi đặc biệt quan trọng

| Hibernate ORM | Filter động | `autoEnabled` | `applyToLoadByKey` | Soft delete native |
|---|---|---|---|---|
| 5.x và 6.0–6.3 | Có `@FilterDef`/`@Filter` | Không dùng API mới từ 6.5 | Chưa có option trong `@FilterDef` như 6.6 | Thường tự thiết kế/filter/static conditions |
| **6.4** | Có | Chưa có `autoEnabled` kiểu 6.5 | Chưa có option `applyToLoadByKey` | **`@SoftDelete` được giới thiệu** |
| **6.5** | Có | **Có `autoEnabled`** | **Chưa có** trong Javadocs 6.5 | Có `@SoftDelete` |
| **6.6** | Có | Có, hỗ trợ parameter resolver | **Có `applyToLoadByKey`** (incubating) | Có `@SoftDelete` |
| **7.x** | Có | Có | Có; mặc định vẫn `false` trong Javadocs 7.x | Có; API tiếp tục phát triển |

Đây là những **mốc API/semantics** cần nắm; không suy diễn rằng mọi patch release hoặc mọi dialect phải có SQL giống hệt nhau. Kiểm tra Hibernate ORM runtime thực tế, đặc biệt khi Spring Boot quản lý dependency version.

### Sự khác nhau giữa 6.5 và 6.6

Javadocs `FilterDef` **6.5** có `autoEnabled` nhưng không có `applyToLoadByKey`.

Javadocs **6.6** bổ sung `applyToLoadByKey`, mặc định `false`, cho phép filter tác động đến thao tác tải entity bằng identifier. Javadocs **7.0–7.4** tiếp tục mô tả tính năng này và `EntityFilterException`.

Vì vậy đoạn code:

```java
@FilterDef(
    name = "minimumAmount",
    applyToLoadByKey = true
)
```

**không phải ví dụ có thể copy nguyên sang Hibernate 6.5**. Nó cần phiên bản có member annotation đó, chẳng hạn 6.6 hoặc 7.x.

## 5. Hành vi mặc định: query được lọc, find(id) có thể không

Định nghĩa:

```java
@FilterDef(
    name = "activeAccount",
    parameters = @ParamDef(
        name = "active",
        type = Boolean.class
    )
)
@Filter(
    name = "activeAccount",
    condition = "active_status = :active"
)
@Entity
public class Account {
    @Id Long id;
    boolean active;
}
```

Khi:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);

List<Account> found = session.createQuery(
    "from Account a order by a.id",
    Account.class
).getResultList();
```

Hibernate có thể trả `[Account#1, Account#3]`, không có `Account#2`.

Trong cùng filter configuration, nếu chạy trên **Persistence Context mới/chưa chứa ID 2**:

```java
Account byId = session.find(Account.class, 2L);
```

ở Hibernate có mặc định `applyToLoadByKey = false`, direct lookup theo primary key **không bị loại chỉ vì filter động đang bật**. Đó là điều được tài liệu `FilterDef` 6.6/7.x mô tả rõ.

### Vì sao Hibernate thiết kế như vậy?

Một lookup theo identifier hoặc quan hệ to-one được xây trên giả định target row tồn tại theo foreign key/identity. Nếu một filter làm target biến mất khỏi object graph:

- Một `@ManyToOne(optional = false)` có thể trông như thiếu target.
- Việc null hóa một association có thể dẫn đến ghi đè foreign key.
- Hibernate phải phân biệt “row thật sự không tồn tại” và “row bị filter che”.

Vì vậy semantics query-level filtering không mặc nhiên được áp cho tất cả identity lookups.

## 6. SQL khác nhau cho HQL query và identifier lookup

Một entity query khi bật filter:

```hql
select a
from Account a
where a.id = :id
```

có thể sinh:

```sql
SELECT a.id, a.active_status
FROM accounts a
WHERE a.id = ?
  AND a.active_status = TRUE;
```

Nhưng:

```java
session.find(Account.class, id);
```

với mặc định trên Hibernate 6.6/7.x có thể sinh:

```sql
SELECT a.id, a.active_status
FROM accounts a
WHERE a.id = ?;
```

Hai API **không có cùng hợp đồng về filter**, dù đều trả về một `Account` và cùng một `id`.

### Bài toán bảo mật

Nếu lập trình viên chỉ kiểm thử:

```java
repository.findAll()
```

và thấy tài khoản bị ẩn, rồi mặc định:

```java
repository.findById(id)
```

cũng phải bị ẩn, một endpoint `GET /accounts/{id}` có thể lộ dữ liệu không mong muốn.

**Filter động không thay thế authorization.** Mọi đường đọc nhạy cảm cần kiểm tra bằng đúng API thực tế; đối với tenant isolation mạnh, cần database RLS, schema/database isolation hoặc một policy được áp nhất quán ở tầng truy cập đáng tin.

## 7. Hibernate 6.6+: applyToLoadByKey = true

Nếu cần filter được áp khi tải trực tiếp theo khóa, `@FilterDef` hỗ trợ lựa chọn:

```java
@FilterDef(
    name = "minimumBalance",
    parameters = @ParamDef(
        name = "amount",
        type = BigDecimal.class
    ),
    applyToLoadByKey = true
)
@Filter(
    name = "minimumBalance",
    condition = "balance > :amount"
)
@Entity
@Table(name = "accounts")
public class Account {
    @Id private Long id;
    private BigDecimal balance;
}
```

Trong session mới:

```java
session.enableFilter("minimumBalance")
       .setParameter("amount", new BigDecimal("1000.00"));

Account high = session.find(Account.class, 1L);
Account low = session.find(Account.class, 2L);
```

Với dữ liệu:

```text
Account#1: balance = 5000
Account#2: balance = 900
```

trong phép thử có SQL thật và chưa có entity sẵn trong Persistence Context:

```text
high != null
low  == null
```

SQL cho ID 2 về mặt ý tưởng:

```sql
SELECT *
FROM accounts a
WHERE a.id = 2
  AND a.balance > 1000;
```

`applyToLoadByKey` được khai báo trên **filter definition**, không phải argument của từng lời gọi `find`. Nó tác động khi filter tương ứng đã enable và phù hợp mapping.

### Cẩn trọng với @Incubating

Javadocs của 6.6/7.x đánh dấu lựa chọn này `@Incubating`. Khi nâng cấp phiên bản, kiểm tra lại API, bug fixes và behavior trên các association mapping cụ thể.

## 8. applyToLoadByKey không làm mọi dữ liệu cũ tự biến mất khỏi Session

Thử:

```java
Account inactive = session.find(Account.class, 2L);

session.enableFilter("activeAccount")
       .setParameter("active", true);

Account again = session.find(Account.class, 2L);
```

Nếu `inactive` đã được nạp trong **first-level Persistence Context**, Hibernate có thể trả lại cùng managed instance khi tìm ID 2. Việc bật filter sau đó **không tự gỡ entity đang managed** ra khỏi bộ nhớ.

Điều này đúng ngay cả khi filter được thiết kế dùng `applyToLoadByKey = true`: filter là điều kiện khi Hibernate cần thực hiện một đường load/query; nó không phải một phép truy hồi xóa mọi object đang resident.

### Hệ quả

Không sử dụng:

```java
session.enableFilter("tenantFilter")
       .setParameter("tenantId", newTenantId);
```

giữa cùng một Session vốn đã nạp entity của tenant khác rồi coi mọi dữ liệu cũ được vô hiệu hóa.

**Đổi tenant/filter parameter giữa unit of work là vùng nguy hiểm.** Nên có Session/Persistence Context mới cho mỗi tenant hoặc policy scope thay vì tái sử dụng một context đã chứa entities không còn được phép xem.

## 9. Bật filter trước truy vấn đầu tiên

Mẫu tốt:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        session.enableFilter("activeAccount")
               .setParameter("active", true);

        List<Account> visible = session.createQuery(
            "from Account",
            Account.class
        ).getResultList();

        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Trong thực tế, cấu hình filter phải xảy ra **trước mọi thao tác đọc có thể tạo object/collection trong Persistence Context**, trừ khi filter được `autoEnabled` đúng cách.

### Vấn đề “bật muộn”

```java
Customer c = session.find(Customer.class, 101L);
int before = c.getAccounts().size(); // Collection đã initialize.

session.enableFilter("activeAccount")
       .setParameter("active", true);

int after = c.getAccounts().size();
```

Collection đã initialized không bắt buộc tự refresh chỉ vì filter vừa bật. `after` có thể vẫn bằng `before`.

**Enable/disable filter không phải phương thức refresh entity graph.**

## 10. Collection @OneToMany: một trường hợp filter rất thường hoạt động

Giả sử:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @Filter(
        name = "activeAccount",
        condition = "active_status = :active"
    )
    private List<Account> accounts = new ArrayList<>();

    public List<Account> getAccounts() { return accounts; }
}
```

Ở một chỗ khác có `@FilterDef` cho `activeAccount` với parameter Boolean.

Khi:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);

Customer customer = session.find(Customer.class, 101L);
List<Account> accounts = customer.getAccounts();
accounts.size(); // Initialize nếu collection đang lazy.
```

Hibernate có thể sinh:

```sql
SELECT *
FROM accounts a
WHERE a.customer_id = 101
  AND a.active_status = TRUE;
```

Với dữ liệu mẫu, collection chỉ chứa Account#1 và Account#3.

### Điểm tinh tế

`Customer` được tải bằng ID **không cần chịu filter của Account**. Sau đó, Hibernate nạp collection bằng query có điều kiện trên collection role.

Đây là lý do cùng một ứng dụng có thể thấy:

```text
session.find(Account.class, 2) -> tìm được Account#2
customer.getAccounts()         -> không chứa Account#2
```

Hai kết quả khác nhau vì **con đường tải và vị trí gắn filter khác nhau**.

## 11. Entity-level filter và collection-level filter không giống nhau

Entity-level:

```java
@Entity
@Filter(
    name = "activeAccount",
    condition = "active_status = :active"
)
public class Account { /* ... */ }
```

Collection-level:

```java
@OneToMany(mappedBy = "customer")
@Filter(
    name = "activeAccount",
    condition = "active_status = :active"
)
private List<Account> accounts;
```

| Vị trí | Ý nghĩa chính |
|---|---|
| `@Filter` trên Account entity | Điều kiện cho những SQL/query paths có filter khi nạp Account |
| `@Filter` trên `Customer.accounts` | Điều kiện cho những SQL load collection của role đó |
| `@FilterJoinTable` | Điều kiện áp lên các hàng **join table** của collection |

**Không nên mặc định** chỉ gắn filter trên entity target sẽ tạo đúng mọi giới hạn collection theo tất cả fetch strategies. Thiết kế mapping và integration test cho những đường nạp quan trọng, đặc biệt to-many, many-to-many và join fetch.

### Không nhầm SQL condition với HQL

`@Filter(condition = "active_status = :active")` dùng **SQL column name** `active_status`, không phải tên Java field `active`.

Nếu entity property là `createdAt` nhưng cột vật lý là `created_at`, filter condition phải tham chiếu cột đúng theo SQL/table alias của mapping.

## 12. Filter trên @ManyToMany và @FilterJoinTable

Giả sử `User` có nhiều `Group` qua bảng liên kết:

```text
users
groups
user_group_memberships
  user_id | group_id | membership_active
```

Nếu cần chỉ lấy membership còn active, điều kiện nằm trên **join table**:

```java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "user_group_memberships",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "group_id")
)
@FilterJoinTable(
    name = "activeMembership",
    condition = "membership_active = true"
)
private Set<Group> groups = new HashSet<>();
```

`activeMembership` cần được định nghĩa bằng `@FilterDef`.

Nếu điều kiện là `groups.status = 'ACTIVE'`, nó nằm trên **target table**, nên cần mapping/filter áp lên target/collection entries phù hợp, không nhầm sang cột join table.

### Ví dụ truy vấn mong muốn

```sql
SELECT g.*
FROM user_group_memberships m
JOIN groups g ON g.id = m.group_id
WHERE m.user_id = ?
  AND m.membership_active = TRUE;
```

`@FilterJoinTable` giúp diễn đạt restriction trên `m`. Nó không tự thay thế một filter bổ sung trên `g` nếu còn cần kiểm tra trạng thái Group.

## 13. To-one @ManyToOne: vì sao target có thể “lọt” filter?

Ví dụ:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private Account account;

    public Account getAccount() { return account; }
}
```

Database:

```text
Order#9001.account_id = 2
Account#2.active_status = FALSE
```

Khi:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);

PurchaseOrder order = session.find(PurchaseOrder.class, 9001L);
Account account = order.getAccount();
account.getAccountNumber();
```

nếu filter mặc định không áp cho to-one identifier fetching, Hibernate có thể nạp Account#2 mặc dù `active_status = FALSE`.

Đây là semantics được mô tả trong Javadocs `FilterDef` 6.6/7.x: **mặc định filter không áp lên `@ManyToOne` target lookup hoặc `find()`**.

### Vì sao nguy hiểm khi hiểu nhầm?

Một màn hình danh sách Accounts có thể ẩn inactive accounts, nhưng trang Order detail vẫn lộ account inactive qua relation.

Nếu business chỉ muốn “danh sách tài khoản có thể chọn”, đây có thể là behavior hợp lý: Order lịch sử vẫn cần tham chiếu Account đã đóng.

Nếu policy là “tuyệt đối không được đọc dữ liệu account inactive”, behavior này không phù hợp và cần một boundary bảo mật khác hoặc cấu hình/load policy được thiết kế rõ.

## 14. To-one với applyToLoadByKey = true: EntityFilterException

Đổi filter definition:

```java
@FilterDef(
    name = "activeAccount",
    parameters = @ParamDef(
        name = "active",
        type = Boolean.class
    ),
    applyToLoadByKey = true
)
```

Khi Order#9001 tham chiếu Account#2 nhưng filter đang loại Account#2:

```text
Order#9001.account_id = 2
Account#2 exists physically
Account#2 is excluded by activeAccount filter
```

Nếu Hibernate phải tải target to-one bằng key và filter loại target, nó có thể ném:

```text
org.hibernate.EntityFilterException
```

Đây là exception Hibernate kế thừa `EntityNotFoundException`; nó biểu thị **đối tượng target bị filter loại khỏi to-one association**, không đơn thuần là hàng database không tồn tại.

### Vì sao không trả null cho mọi to-one?

Nếu association có foreign key thật trong DB nhưng ORM tự biến tham chiếu thành `null` vì filter:

```java
order.getAccount() == null;
```

rồi flush một entity modified, Hibernate có thể diễn giải quan hệ đã bị xóa và ghi `account_id = NULL`, làm mất liên kết.

Do đó khi `applyToLoadByKey = true` làm target to-one bị filter, Hibernate có cơ chế báo lỗi thay vì tự null hóa.

### Exception có phải luôn xảy ra khi load Order?

Không nhất thiết. Với `fetch = LAZY`, target có thể chỉ được initialize khi truy cập. Với EAGER/join fetch, SQL shape khác và thời điểm phát hiện có thể khác.

**Thời điểm lỗi phụ thuộc fetch strategy, mapping và phiên bản**, cần kiểm thử đúng path thay vì chỉ test `session.find(PurchaseOrder, id)`.

## 15. Đừng dùng @NotFound(IGNORE) để “chữa” to-one filtered

Hibernate có annotation:

```java
@NotFound(action = NotFoundAction.IGNORE)
```

Một số codebases dùng nó để biến missing target thành `null`. Nhưng Hibernate User Guide 6.6 đặc biệt cảnh báo: kết hợp `@NotFound(IGNORE)` với filter `applyToLoadByKey = true` có thể **null hóa association khi target bị filter**, rồi khi flush có thể cập nhật FK thành NULL và làm mất dữ liệu.

### Vì sao đây là lỗi mô hình?

Giả sử:

```text
Order.account_id = 2
Account#2 vẫn tồn tại, chỉ bị ẩn do policy
```

Nếu Java model trông như:

```text
Order.account = null
```

thì model **đánh đồng “không được phép nhìn thấy” với “không có quan hệ”**.

Điều này có thể phá:

- Referential integrity.
- Business history.
- Not-null foreign key.
- Logic tính tiền hoặc chủ sở hữu.

**Không sử dụng `@NotFound(IGNORE)` như giải pháp mặc định cho security/soft-delete filter.** Nếu association có thể bị ẩn, thiết kế DTO/reference view hoặc policy riêng, giữ foreign key semantics rõ ràng.

## 16. optional = true không có nghĩa “filtered target sẽ thành null an toàn”

`@ManyToOne(optional = true)` cho phép quan hệ null trong domain; nó **không định nghĩa** một policy rằng “nếu target bị filter thì Hibernate nên xóa liên kết”.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
private Account preferredAccount;
```

Nếu `preferred_account_id = 2` thật sự tồn tại, nhưng Account#2 bị filter loại, semantics vẫn khác với `preferred_account_id IS NULL`.

Khi dùng `applyToLoadByKey = true`, to-one association có thể ném `EntityFilterException` để phân biệt hai trạng thái.

### Lựa chọn API nếu muốn ẩn target

Không nhất thiết trả entity:

```java
public record PreferredAccountView(
    Long accountId,
    boolean visible,
    String accountNumber
) {}
```

Một service có thể:

1. Đọc foreign key theo policy phù hợp.
2. Kiểm tra quyền/visibility.
3. Trả `visible=false` hoặc không expose target fields.
4. Không sửa foreign key trong entity chỉ vì target đang bị ẩn.

Việc có được trả `accountId` hay không cũng là quyết định bảo mật, không mặc định an toàn.

## 17. @OneToOne cũng là quan hệ to-one cần kiểm tra

Đối với:

```java
@OneToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "profile_id")
private CustomerProfile profile;
```

nếu `CustomerProfile` bị filter:

- Mặc định lọc cho entity query nhưng không nhất thiết cho direct target-by-key.
- Với `applyToLoadByKey=true`, target bị filter có thể kích hoạt `EntityFilterException`.
- Mapping `optional`, owning side và lazy support ảnh hưởng thời điểm load.
- Shared primary key `@MapsId` cũng có identity/relationship semantics riêng.

Không giả định `@OneToOne` và `@OneToMany` sẽ xử lý “ẩn target” giống nhau vì cả hai đều có từ “One”.

## 18. LAZY và EAGER thay đổi đường đi của SQL

### LAZY

```java
@ManyToOne(fetch = FetchType.LAZY)
private Account account;
```

Hệ thống có thể:

1. Nạp Order.
2. Giữ proxy/reference cho Account.
3. Khi truy cập `getAccount().getAccountNumber()`, tải Account bằng key.
4. Áp hoặc không áp filter theo version/`applyToLoadByKey`.

### EAGER

```java
@ManyToOne(fetch = FetchType.EAGER)
private Account account;
```

Hibernate có thể dùng join hoặc secondary select tùy query/fetch plan. Filter behavior có thể chịu ảnh hưởng SQL join shape; ví dụ một inner join tới target không thỏa điều kiện có thể làm **cả row chủ không xuất hiện** trong query.

### Đừng suy ra từ annotation đơn lẻ

`FetchType.LAZY/EAGER` là chỉ dẫn về timing, không phải bảo đảm về mọi SQL do Hibernate phát. EntityGraph, HQL join fetch, batch fetching và bytecode enhancement có thể tác động.

Với filter quan trọng, phải test:

- `find` root + truy cập lazy association.
- HQL select root + join fetch.
- `EntityGraph`.
- Direct query target entity.
- Tải trong Session trống và Session đã chứa target.

## 19. HQL JOIN FETCH không đồng nhất với truy cập lazy to-one

Ví dụ:

```hql
select o
from PurchaseOrder o
join fetch o.account a
where o.id = :orderId
```

SQL sinh ra là một joined query, không nhất thiết giống:

```java
PurchaseOrder o = session.find(PurchaseOrder.class, orderId);
Account a = o.getAccount();
a.getAccountNumber();
```

Nếu filter áp lên joined target hoặc query conditions, `INNER JOIN` có thể loại toàn bộ Order nếu Account target không thỏa; `LEFT JOIN` có thể giữ Order nhưng có association behavior cần quan sát.

**Không đưa ra một quy tắc tuyệt đối rằng tất cả JOIN FETCH luôn áp/bỏ qua filter theo cùng cách**. Cách đặt restriction trên ON/WHERE, alias, association mapping và phiên bản có thể quyết định kết quả.

Khi cần một hợp đồng query cụ thể cho authorization, có thể viết điều kiện rõ:

```hql
select o
from PurchaseOrder o
join o.account a
where o.id = :orderId
  and a.active = true
```

Ngay cả khi query được lọc đúng, method khác `find(Order)` vẫn có thể dùng đường khác. Hạn chế quyền ở **mọi API paths** chứ không chỉ một query.

## 20. Collection đã initialize không được “lọc lại” tự động

Ví dụ:

```java
Customer customer = session.find(Customer.class, 101L);
List<Account> all = customer.getAccounts();
all.size(); // Collection initialized khi filter chưa bật.

session.enableFilter("activeAccount")
       .setParameter("active", true);

List<Account> afterEnable = customer.getAccounts();
```

Không có lý do để Hibernate tự thay nội dung `all` theo một predicate khác sau khi object collection đã được initialize. `afterEnable` có thể vẫn chứa Account#2.

### Tắt filter cũng không hồi đầy collection đang initialized

```java
session.disableFilter("activeAccount");
```

nếu collection đã được load như một subset, tắt filter không có nghĩa Hibernate tự query thêm những rows bị bỏ qua.

### Thực tế tốt hơn

- Chọn filter parameters trước khi load.
- Không đổi filter giữa một unit of work đang dùng managed graph.
- Dùng Session/Persistence Context mới cho các visibility scopes khác nhau.
- Nếu chỉ cần một danh sách dữ liệu mới, viết query DTO explicit theo điều kiện thay vì phụ thuộc vào việc refresh managed collection.

## 21. Persistence Context là bộ nhớ identity, không phải một query cache tùy ý

Hibernate Session stateful giữ identity map:

```text
(Account.class, id=2) -> Java object Account#2
```

Khi `find(Account,2)` được gọi lần nữa, Hibernate thường có thể trả object sẵn có.

Đây là điều kiện ảnh hưởng kết quả filter:

```text
Session trống + filter bật -> có thể query DB theo filter
Session đã chứa Account#2 -> có thể trả Account#2 đã managed
```

Vì vậy **SQL log không xuất hiện khi load lần hai** không phải bằng chứng filter đã “bị lỗi”; nó cho thấy Hibernate không cần chạy SQL vì object đã nằm trong context.

Một filter không phải access-control barrier có thể “revoke” mọi object đã được ứng dụng nhận trước đó.

### Có nên em.clear() sau khi đổi filter?

`entityManager.clear()` detach managed entities, nhưng:

- Nó có thể làm mất pending changes nếu chưa flush/commit đúng.
- Các Java references cũ vẫn tồn tại trong application.
- Collection snapshots và business invariants có thể bị ảnh hưởng.

Trong những use cases nhạy cảm, **new transaction/new Session** thường dễ suy luận hơn việc đổi visibility policy trong một Session đã chạy nhiều thao tác.

## 22. Second-level cache và filter: cần phân biệt entity cache với collection cache

Hibernate có hai tầng:

1. **First-level cache (Persistence Context)**: gắn Session, chứa managed entities.
2. **Second-level cache**: chia sẻ qua Sessions nếu entity/collection được cấu hình cache.

Filter động có parameters khác nhau theo session. Nếu cache một collection chỉ chứa subset cho tenant A/active=true rồi phát lại cho Session khác, có nguy cơ dữ liệu sai.

Hibernate User Guide 6.6 giải thích rằng **không thể kết hợp `@Filter` và `@Cache` trên cùng collection mapping** trong trường hợp áp dụng restriction động vì filtered collection không phù hợp lưu như một collection snapshot dùng chung.

### Vì sao?

```text
Session A: filter active=true
  Customer#101.accounts -> [Account#1, Account#3]

Session B: không bật filter
  Customer#101.accounts -> phải gồm [Account#1,#2,#3]
```

Nếu L2 cache chỉ lưu subset từ A mà không lưu parameters/filter scope, B có thể nhận danh sách thiếu.

### Entity cache vẫn cần xem xét riêng

Entity data trong L2 cache không phải cơ chế phân quyền. Với đường load-by-ID, cache hits và `applyToLoadByKey`/mapping behavior phải được kiểm thử trên đúng phiên bản. Không giả định `@Cache` tự đưa tenant/active status vào cache key một cách tương thích với mọi filter tùy biến.

Đặc biệt trong multi-tenancy, cần thiết kế cache regions/keys và tenant routing đúng; nếu yêu cầu cách ly bảo mật mạnh, dựa thêm vào DB RLS hoặc isolation vật lý phù hợp.

## 23. Trường hợp có hai filter đồng thời

Ví dụ:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);

session.enableFilter("minimumBalance")
       .setParameter("amount", new BigDecimal("1000"));
```

Nếu Account được gắn cả hai filters, query có thể chịu cả hai predicates:

```sql
WHERE active_status = TRUE
  AND balance > 1000;
```

Tuy nhiên, khi tải theo ID, nếu chỉ `minimumBalance` khai báo `applyToLoadByKey = true`, còn `activeAccount` là `false`, **không được kết luận cả hai predicates đều được áp** lên identifier lookup.

### Bài test

Một Account:

```text
id=2, active=false, balance=5000
```

Khi:

- Entity query: bị loại vì active=false.
- Direct find: có thể lọt active filter nhưng vẫn vượt minBalance.

Một Account khác:

```text
id=3, active=true, balance=500
```

Khi direct find có `minimumBalance.applyToLoadByKey=true` có thể bị loại.

**Mỗi filter definition có chính sách key loading riêng**, không phải một cờ global cho toàn Session.

## 24. autoEnabled từ Hibernate 6.5 không giống applyToLoadByKey

Hai thuộc tính giải quyết **hai vấn đề hoàn toàn khác nhau**:

| Thuộc tính của `@FilterDef` | Câu hỏi nó trả lời |
|---|---|
| `autoEnabled` | Session mới có tự bật filter không? |
| `applyToLoadByKey` | Khi filter đã bật, có áp cho identifier lookups/to-one key loading không? |

Một filter:

```java
@FilterDef(
    name = "activeAccount",
    autoEnabled = true
)
```

**không có nghĩa** direct `find(id)` tự được lọc. Nếu `applyToLoadByKey` mặc định `false` (ở 6.6+), tự bật filter chỉ giúp không quên `enableFilter`, không đổi chính sách load by key.

### Khi có tham số

Trong Hibernate 6.5+/6.6+/7.x, auto-enabled filters có thể dùng `@ParamDef(resolver = ... )` để cung cấp parameter value bằng `Supplier` phù hợp.

Ví dụ minh họa:

```java
@FilterDef(
    name = "activeAccount",
    autoEnabled = true,
    parameters = @ParamDef(
        name = "active",
        type = Boolean.class,
        resolver = ActiveAccountSupplier.class
    )
)
@Filter(
    name = "activeAccount",
    condition = "active_status = :active"
)
@Entity
public class Account {
    @Id Long id;
    boolean active;
}

public class ActiveAccountSupplier
        implements java.util.function.Supplier<Boolean> {
    @Override
    public Boolean get() {
        return true;
    }
}
```

Resolver được Hibernate quản lý theo cơ chế bean/provider phù hợp; kiểm tra constructor/managed-bean integration của version. Nếu resolver trả tenant từ ThreadLocal, phải bảo đảm tenant context đã đúng **trước khi Hibernate tạo/bind Session và chạy query**.

## 25. Tại sao không chỉ cần @Filter để làm soft delete?

Một mô hình soft delete thủ công:

```java
@Entity
@Table(name = "accounts")
@FilterDef(name = "notDeleted")
@Filter(
    name = "notDeleted",
    condition = "deleted = false"
)
public class Account {
    @Id Long id;
    @Column(nullable = false)
    boolean deleted;
}
```

Rồi:

```java
session.enableFilter("notDeleted");
```

Câu query danh sách có thể ẩn deleted rows.

Nhưng:

- Nếu Session chưa bật filter, row bị xóa mềm vẫn có thể hiện.
- Khi `find(id)` mặc định bypass filter, row vẫn có thể được đọc.
- Quan hệ to-one có thể trỏ đến target deleted và nạp nó.
- Một command `remove(entity)` thông thường **không tự đổi thành UPDATE deleted=true** chỉ nhờ có `@Filter`.
- Bulk/native SQL hoặc direct JDBC bypass filter.

Vì vậy `@Filter` không phải một giải pháp soft delete đầy đủ nếu không có write-side delete policy và nhất quán ở mọi load paths.

## 26. Hibernate 6.4+: @SoftDelete là cơ chế chuyên dụng

Từ Hibernate ORM **6.4**, Enity/collection soft deletion có hỗ trợ native qua `@SoftDelete`:

```java
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "accounts")
@SoftDelete(strategy = SoftDeleteType.DELETED)
public class Account {

    @Id
    private Long id;

    @Column(name = "account_number")
    private String accountNumber;
}
```

Với strategy `DELETED`, indicator boolean mang nghĩa:

```text
false -> row chưa bị xóa
true  -> row đã bị xóa mềm
```

Khi remove, Hibernate có cơ chế soft-delete tương ứng và các SQL loads của mapping được thiết kế để xử lý indicator. Nó phù hợp hơn việc tự ghép filter + custom delete SQL trên mỗi entity.

### Phân biệt với @Filter

`@SoftDelete` không phải một filter động tùy ý bật/tắt mỗi Session. Nó là **quy tắc visibility/deletion gắn mapping**.

Trong hệ thống cần “restore deleted row” hoặc admin đọc records đã xóa, phải thiết kế **đường admin riêng** có kiểm soát, có thể dùng native SQL/khác mapping, thay vì mặc định session.disableFilter sẽ làm mọi @SoftDelete records xuất hiện.

### Giới hạn

- Cấu hình `@SoftDelete` cho entity/collection và strategy hỗ trợ thay đổi theo version.
- Không tự biến tất cả writes ngoài Hibernate thành soft-delete-aware.
- Dữ liệu đã có phải được migration để indicator hợp lệ.
- To-one relation và proxy behaviors vẫn cần integration test theo đúng ORM version.

Không nói “@SoftDelete giải quyết hoàn toàn mọi vấn đề bảo mật” — nó giải quyết **lifecycle và visibility semantics của xóa mềm trong Hibernate**.

## 27. @SQLRestriction, @Where và filter động

Hibernate có cơ chế static SQL restriction.

Ví dụ:

```java
@Entity
@SQLRestriction("active_status = true")
public class Account {
    @Id Long id;
}
```

`@SQLRestriction` phù hợp khi restriction cố định, không cần parameters và không cần enable/disable theo Session.

Trong code Hibernate cũ, có thể thấy `@Where(clause = "...")`; annotation này bị deprecate trong các phiên bản mới, và tài liệu hướng người dùng sang `@SQLRestriction` cho restriction tĩnh.

| Cơ chế | Dynamic per session? | Có params? | Mục đích |
|---|---|---|---|
| `@Filter` + `@FilterDef` | Có | Có | Visibility động theo lựa chọn/session |
| `@SQLRestriction` | Không | Không | Restriction SQL cố định |
| `@SoftDelete` (6.4+) | Không như `@Filter` | Indicator mapping | Soft-delete lifecycle/visibility |
| Business HQL `where` | Theo từng query | Có | Quy định query explicit |
| DB Row-Level Security | Policy của DB | Theo DB session/user context | Ranh giới dữ liệu ở tầng database |

Các cơ chế có thể bổ sung nhau, nhưng không được mặc định chúng có cùng semantics load-by-key, caching, update/delete và relations.

## 28. Filter và @SoftDelete khác nhau ở soft-deleted to-one

Giả sử:

```text
Order#9001.account_id = 2
Account#2 bị xóa mềm
```

Nếu Account dùng **filter động**:

- Query danh sách có thể loại Account#2.
- Identifier lookup mặc định có thể vẫn tìm thấy Account#2.
- Bật `applyToLoadByKey=true` có thể dẫn đến `EntityFilterException` khi tải qua to-one.

Nếu Account dùng **`@SoftDelete`**:

- Hibernate có native soft-delete semantics cho mapping; row được coi không còn visible theo đường load thông thường.
- To-one association tới row deleted có thể gây vấn đề domain tương tự một target không tồn tại (không phải cơ chế `EntityFilterException` của filter động trong mọi trường hợp).
- Ứng dụng cần quyết định có nên giữ một “historical reference” tới target deleted hay thiết kế record snapshot/tombstone.

### Mô hình domain có thể hợp lý hơn

Nếu Order đã thanh toán phải giữ thông tin tài khoản ngay cả sau khi Account bị đóng/xóa mềm:

- Lưu snapshot tối thiểu tại Order: masked account number, provider, account display name tại thời điểm thanh toán.
- Giữ `account_id` làm link nội bộ nếu phù hợp.
- Chỉ expose fields theo authorization.
- Không dựa vào việc vẫn nạp được Account deleted để giữ tính đúng của lịch sử giao dịch.

Xóa mềm có semantics nghiệp vụ, không chỉ là cách làm câu `SELECT` ngắn hơn.

## 29. Filter không phải cơ chế cưỡng chế DELETE/UPDATE SQL

`@Filter` chủ yếu là read/query restriction và không nên được dùng làm hàng rào duy nhất cho các thao tác mutation.

Ví dụ:

```java
session.enableFilter("tenantFilter")
       .setParameter("tenantId", tenantId);

Account account = session.get(Account.class, id);
account.setBalance(BigDecimal.ZERO);
```

Nếu identifier lookup không áp filter, thao tác này có thể cập nhật một Account nằm ngoài visibility scope mong muốn.

Tương tự, HQL bulk DML:

```hql
update Account a
set a.balance = :newBalance
where a.id = :id
```

không nên được bảo vệ bằng niềm tin rằng named filter sẽ được áp đúng trên mọi mutation path. Những operation này cần authorization/tenant predicates tường minh hoặc enforced RLS.

### Policy write-side đúng

- Check authorization trước hành động.
- Load entity bằng query có tenant predicate phù hợp.
- Có immutable tenant/owner field.
- Dùng optimistic locking và constraints khi cần.
- Với bulk DML, có `WHERE tenant_id = :tenantId` explicit.
- Nếu cần bảo đảm ở mọi client, dùng RLS hoặc isolation database/schema.

Không coi “người dùng không nhìn thấy hàng” đồng nghĩa “không thể cập nhật/xóa hàng”.

## 30. Tenant filter: ví dụ một rủi ro nghiêm trọng

Entity:

```java
@Entity
@Table(name = "documents")
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(
        name = "tenantId",
        type = String.class
    )
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
public class Document {
    @Id private Long id;
    @Column(name = "tenant_id")
    private String tenantId;
}
```

Service:

```java
@Transactional(readOnly = true)
public Document findForTenant(long documentId, String tenantId) {
    Session session = em.unwrap(Session.class);
    session.enableFilter("tenantFilter")
           .setParameter("tenantId", tenantId);

    return em.find(Document.class, documentId);
}
```

Nếu chạy ở version/config mặc định bypass direct load by key, method **có thể trả Document của tenant khác**.

Đây không phải một bug giao diện nhỏ; nó có thể là rò dữ liệu xuyên tenant.

### Phương án tốt hơn

```java
@Transactional(readOnly = true)
public DocumentView findForTenant(
        long documentId,
        String trustedTenantId) {

    Document document = em.createQuery(
        "select d from Document d " +
        "where d.id = :id " +
        "and d.tenantId = :tenantId",
        Document.class
    )
    .setParameter("id", documentId)
    .setParameter("tenantId", trustedTenantId)
    .getResultStream()
    .findFirst()
    .orElseThrow(NotFoundOrForbiddenException::new);

    return toAuthorizedView(document);
}
```

`trustedTenantId` phải đến từ authentication/session tenant context đáng tin, không lấy nguyên query param `tenantId` mà cho client tùy chọn tenants khác.

Với isolation cấp hệ thống, dùng **Hibernate multi-tenancy đúng cấu hình** (nếu đáp ứng topology) hoặc database RLS, không chỉ một filter có thể bị quên hoặc bypass.

## 31. Ranh giới tenant với relation to-one

Ví dụ:

```text
Tenant A: Order#9001.account_id=2
Tenant B: Account#2
```

Một FK chỉ theo account ID mà không chứa tenant có thể cho dữ liệu cross-tenant nếu schema cho phép. Dù filter che query danh sách, to-one load-by-key có thể tìm Account#2.

### Thiết kế dữ liệu

- Cân nhắc composite keys/foreign keys có tenant key nơi cần enforce.
- Đảm bảo insert/update không tạo cross-tenant associations.
- Tenant routing và Session scope phải được thiết lập trước load.
- Kiểm tra direct find, lazy association, eager join, collection, native query và bulk mutation.
- Không dùng `@NotFound(IGNORE)` để che mismatch; có thể mất liên kết và giấu bug dữ liệu.

Sửa một filter không thay thế việc sửa những foreign keys cho phép quan hệ không hợp lệ.

## 32. Filter có thể được bật trong một Session và quên tắt

`Session.enableFilter` điều khiển trạng thái filter của Session đó.

Nếu một Session sống lâu hoặc được giữ qua nhiều bước:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);

// ... work 1

session.disableFilter("activeAccount");

// ... work 2
```

Sau khi `disableFilter`, các query về sau không còn restriction đó. Nếu một service quản lý Session không rõ scope, có thể vô tình bỏ filter trước khi query nhạy cảm.

Trong Spring JPA:

- Transaction/request scopes quyết định EntityManager thực.
- `@PersistenceContext` thường inject proxy, nhưng current Session vẫn phải được xác định đúng.
- OSIV có thể giữ Persistence Context ngoài service transaction trong request.
- Worker `@Async` không tự kế thừa Session/filter state của request thread.

**Đừng bật filter ở một thread rồi mong nó tự áp trong worker thread khác.**

## 33. @Async và filter theo Session

Ví dụ:

```java
@Transactional
public void scheduleProcess(String tenantId) {
    em.unwrap(Session.class)
      .enableFilter("tenantFilter")
      .setParameter("tenantId", tenantId);

    asyncFacade.processDocument(documentId);
}
```

Trong `processDocument` chạy ở một worker thread có transaction/EntityManager riêng, filter **không tự được bật** chỉ vì caller đã bật filter trên request thread.

Mẫu đúng:

1. Truyền trusted tenant ID hoặc job ID rõ ràng.
2. Worker mở transaction riêng.
3. Áp đúng tenant/filter policy trong Session của worker trước khi load.
4. Dùng explicit authorization/tenant predicates cho đường load.
5. Clear thread-local context nếu có trong `finally`.

Nếu dùng auto-enabled filter có parameter resolver, vẫn phải đảm bảo resolver lấy tenant đúng của job hiện tại, không đọc nhầm ThreadLocal của worker trước đó.

## 34. Filter parameter và SQL injection

Một filter:

```java
@FilterDef(
    name = "regionFilter",
    parameters = @ParamDef(
        name = "region",
        type = String.class
    )
)
@Filter(
    name = "regionFilter",
    condition = "region_code = :region"
)
```

Và:

```java
session.enableFilter("regionFilter")
       .setParameter("region", regionFromTrustedContext);
```

Hibernate bind parameter qua cơ chế JDBC, không nối trực tiếp giá trị vào fragment SQL như string concatenation.

**Không tự tạo `condition` bằng nối text input từ client**:

```java
// Tránh các đường xây SQL fragment tùy ý từ input.
String condition = "tenant_id = '" + userInput + "'";
```

`@Filter.condition` là static mapping SQL fragment, không phải một field để người dùng tự cung cấp. Dynamic sort/conditions cần sử dụng allow-list và bind parameters.

Ngoài injection, nếu parameter value được lấy sai tenant, filter vẫn có thể là một SQL query hợp lệ nhưng trả dữ liệu sai quyền.

## 35. NULL, boolean và điều kiện SQL của filter

Ví dụ soft-delete column có thể nullable vì schema cũ:

```text
deleted = FALSE
deleted = TRUE
deleted = NULL
```

Filter:

```sql
deleted = FALSE
```

sẽ **không chọn rows deleted = NULL** theo SQL three-valued logic.

Nếu nghiệp vụ coi NULL là “chưa xóa”, predicate phải được định nghĩa rõ:

```sql
(deleted = FALSE OR deleted IS NULL)
```

Nhưng tốt hơn là migration dữ liệu và áp `NOT NULL`/default hợp lệ khi có thể, tránh trạng thái ba nghĩa không mong muốn.

### Chuyển đổi column type

DB khác nhau có syntax boolean khác nhau. `@Filter.condition` dùng SQL fragment và dialect/naming ảnh hưởng câu SQL thực tế; thử trên database mục tiêu, không mặc định mọi DDL và literal `TRUE/FALSE` hoạt động giống nhau trên tất cả DBs.

## 36. Filter và điều kiện của JOIN có thể khác với WHERE

Giả sử:

```sql
SELECT o.id, a.id
FROM purchase_orders o
LEFT JOIN accounts a
  ON a.id = o.account_id
 AND a.active_status = TRUE;
```

Order vẫn xuất hiện khi target Account bị loại; cột của Account trong SQL result có thể là NULL.

Nếu đổi điều kiện thành:

```sql
SELECT o.id, a.id
FROM purchase_orders o
LEFT JOIN accounts a ON a.id = o.account_id
WHERE a.active_status = TRUE;
```

thì Order không có target matching có thể bị loại hoàn toàn, khiến LEFT JOIN mang behavior gần INNER JOIN.

Hibernate tự đặt filter restriction ở vị trí nào phụ thuộc query/mapping/dialect. Vì vậy khi debug:

1. Xem generated SQL.
2. Xem điều kiện filter nằm ở ON hay WHERE.
3. Xem join type (INNER/LEFT).
4. Đếm root rows trước/sau filter.
5. Thử target bị soft-deleted và target thật sự missing.

Không kết luận to-one sẽ luôn thành null hoặc luôn ném exception chỉ từ một đoạn HQL ngắn.

## 37. Filter collection không tự xóa các phần tử bị ẩn

Một collection `customer.getAccounts()` chỉ có active Accounts:

```java
session.enableFilter("activeAccount")
       .setParameter("active", true);

Customer c = session.find(Customer.class, 101L);
c.getAccounts().size(); // Chỉ thấy subset.
```

Các Account không visible **vẫn tồn tại trong database**. Filter điều khiển visibility khi đọc; nó không xóa row, không đổi foreign key, và không bảo đảm domain relationship ở DB chỉ còn phần tử đã thấy.

### Nếu ứng dụng sửa collection bị lọc?

Những thao tác như:

```java
c.getAccounts().clear();
```

có thể tương tác với persistence semantics của collection, cascade/orphanRemoval và dirty checking. Nếu collection chỉ đang chứa một subset, dự đoán các SQL deletes/updates chỉ từ giao diện Java có thể sai.

**Không dùng một filtered collection như nguồn sự thật đầy đủ để thực hiện những thao tác xóa/hợp nhất toàn bộ quan hệ** trừ khi đã kiểm chứng ORM behavior của mapping.

Trong service thao tác quan hệ nhạy cảm:

- Load toàn bộ association cần sửa trong scope kiểm soát.
- Hoặc dùng explicit DML với predicate rõ.
- Xác định rõ hành vi đối với rows bị filter ẩn.
- Integration test SQL emitted và database state sau flush.

## 38. JOIN FETCH collection và pagination

Ví dụ:

```hql
select c
from Customer c
left join fetch c.accounts
order by c.id
```

Nếu `accounts` là to-many, JOIN có thể tạo nhiều rows cho một Customer. Kết hợp `setFirstResult`/`setMaxResults` có thể khiến Hibernate cảnh báo hoặc xử lý pagination trong bộ nhớ để không cắt dở collection.

Filter còn làm số rows sau join thay đổi, khiến kết quả:

- Có thể ít hoặc nhiều Accounts trong một Customer theo filter.
- Chi phí query/caching khó dự đoán.
- Count of customers không đơn giản bằng count joined rows.

Khi cần phân trang root:

1. Lấy trang IDs của Customer theo điều kiện và ORDER BY ổn định.
2. Load DTO/associations cho IDs của trang.
3. Áp filter đúng scope nếu cần.
4. Giữ thứ tự kết quả theo trang ID, không giả định `IN (:ids)` giữ nguyên thứ tự.

Không chỉ test danh sách hiển thị đẹp mà bỏ qua SQL có bị load quá nhiều dữ liệu hay không.

## 39. COUNT query và filter

Một trang:

```hql
select a
from Account a
order by a.id
```

và count:

```hql
select count(a)
from Account a
```

đều là entity queries nên có thể chịu filter đang bật. Nhưng nếu service đếm bằng **native SQL**:

```sql
SELECT COUNT(*) FROM accounts;
```

thì count có thể bao gồm cả rows bị filter ẩn.

### Bẫy API

```text
items = 8 active accounts
totalElements = 12 all accounts
```

Tổng sai nếu hai query không dùng cùng business predicate.

Với multi-tenant hoặc soft-delete:

- Data query, count query và authorization scope phải thống nhất.
- Native count cần WHERE explicit.
- Filter phải bật trước cả hai query nếu dựa vào filter.
- Kết quả vẫn có thể khác nhau nếu database thay đổi giữa hai statements (tùy isolation).

## 40. Filter và entity equality/identity

Một entity có thể đã được nạp qua `find` trước khi bật filter. Sau đó, query có filter không trả row ấy nhưng Persistence Context vẫn chứa object.

```java
Account a = session.find(Account.class, 2L);

session.enableFilter("activeAccount")
       .setParameter("active", true);

List<Account> visible = session.createQuery(
    "from Account",
    Account.class
).getResultList();
```

`a` vẫn là một Java reference hợp lệ, bất kể `visible` có chứa nó hay không. Không dùng `visible.contains(a)` để kết luận object đó có được phép truy cập hoặc cập nhật.

Identity map chỉ đảm bảo một số điều về entity instance trong Session, không phải business visibility policy.

### Truy cập direct by-ID trong Session mới vẫn quan trọng

Để xác minh load-by-key filter, luôn có test ở **Session chưa từng load entity đó**. Nếu không, cache hit first-level có thể khiến test không thực sự thực hiện identifier SQL path.

## 41. Những điều cần lưu ý về EntityGraph

JPA EntityGraph giúp quyết định association nào được fetch trong truy vấn hoặc `find`:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("account");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

Với graph, Hibernate có thể thay đổi SQL để nạp Account cùng Order, thay vì lazy by-key sau đó.

**Đừng suy ra** `applyToLoadByKey=true` khiến mọi EntityGraph có kết quả giống lazy path: tải root bằng ID, fetch graph, JOIN và secondary select là những cơ chế khác cần đối chiếu.

Test graph với cả active/inactive target và lưu SQL/trường hợp exception, đặc biệt khi relation optional.

## 42. Các biểu hiện thực tế và cách điều tra

| Hiện tượng | Nguyên nhân cần kiểm tra trước |
|---|---|
| Query danh sách ẩn row nhưng `find(id)` thấy | Mặc định filter không áp direct key load |
| `@ManyToOne` tìm thấy target bị ẩn | Target được load bằng identifier khi `applyToLoadByKey=false` |
| Sau bật `applyToLoadByKey=true`, to-one ném exception | Target có FK nhưng bị filter loại |
| Bật filter rồi collection vẫn giữ phần tử cũ | Collection đã initialize trước đó |
| Tắt filter mà collection không hiện thêm rows | Collection hiện tại là snapshot đã nạp |
| Filter không có tác dụng trong `@Async` | Worker dùng Session mới, chưa bật filter/context |
| Native SQL vẫn đọc deleted rows | Hibernate filter không áp cho native/JDBC SQL |
| Hibernate 6.5 không compile `applyToLoadByKey` | Member có từ 6.6 |
| Collection cache không dùng được cùng `@Filter` | L2 collection cache không thể lưu subset theo filter params |
| `@NotFound(IGNORE)` tạo FK NULL sau load | Filtered to-one bị coi là missing/null và flush gây mất link |
| Filter đúng nhưng actor vẫn truy cập chéo tenant | Thiếu authorization/DB isolation; first-level cache hoặc by-ID path |
| HQL join fetch trả thiếu root | INNER JOIN/condition trên target có thể loại parent |

Đừng đoán chỉ từ kết quả của một method. Cần logs SQL, current filter state, Hibernate version và một session clean để tái hiện.

## 43. Mẫu integration test: query khác find mặc định

Giả sử Account entity mapping như phần 2, với filter mặc định (không `applyToLoadByKey`).

Test trên database thật:

```java
@Test
void queryCanExcludeRowButFindByIdCanSeeIt() {
    doInNewTransaction(em -> {
        Session session = em.unwrap(Session.class);
        session.enableFilter("activeAccount")
               .setParameter("active", true);

        List<Account> active = em.createQuery(
            "select a from Account a order by a.id",
            Account.class
        ).getResultList();

        assertThat(active)
            .extracting(Account::getId)
            .containsExactly(1L, 3L);

        Account inactive = em.find(Account.class, 2L);
        assertThat(inactive).isNotNull();
    });
}
```

`doInNewTransaction` là test helper do dự án cung cấp, không phải JPA API. Test setup phải seed dữ liệu và bảo đảm entity ID 2 **chưa được load vào Persistence Context** trước lời gọi `find`.

Kỳ vọng test này được đưa ra cho đường lọc mặc định ở phiên bản hỗ trợ như 6.6/7.x; nếu mapping dùng `@SoftDelete` hoặc static restrictions khác, kết quả có thể khác.

## 44. Mẫu integration test: applyToLoadByKey=true

Tạo một filter riêng:

```java
@FilterDef(
    name = "minimumBalance",
    applyToLoadByKey = true,
    parameters = @ParamDef(
        name = "amount",
        type = BigDecimal.class
    )
)
@Filter(
    name = "minimumBalance",
    condition = "balance > :amount"
)
```

Trong session mới:

```java
@Test
void idLookupHonorsMinimumBalance() {
    doInNewTransaction(em -> {
        Session session = em.unwrap(Session.class);
        session.enableFilter("minimumBalance")
               .setParameter("amount", new BigDecimal("1000"));

        Account high = em.find(Account.class, 1L);
        Account low = em.find(Account.class, 2L);

        assertThat(high).isNotNull();
        assertThat(low).isNull();
    });
}
```

Điều kiện:

- Hibernate version **6.6 hoặc 7.x** có member `applyToLoadByKey`.
- Không có Account#2 đã managed trong context.
- SQL path thực sự dùng DB và mapping đúng.

Nếu test không thấy SQL do cache, phải điều chỉnh setup/test scope thay vì kết luận từ một cache hit.

## 45. Mẫu integration test: to-one target bị filter

Seed:

```text
PurchaseOrder#9001.account_id = 2
Account#2.balance = 900
minimumBalance.amount = 1000
```

Mapping:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "account_id", nullable = false)
private Account account;
```

Test ý tưởng:

```java
@Test
void filteredToOneTargetIsNotSilentlyNullified() {
    doInNewTransaction(em -> {
        Session session = em.unwrap(Session.class);
        session.enableFilter("minimumBalance")
               .setParameter("amount", new BigDecimal("1000"));

        PurchaseOrder order =
            em.find(PurchaseOrder.class, 9001L);

        assertThatThrownBy(() ->
            order.getAccount().getAccountNumber()
        ).isInstanceOf(EntityFilterException.class);
    });
}
```

Đây là expectation cần kiểm tra với **LAZY to-one target key load** theo mapping đã định nghĩa. Nếu proxy/bytecode enhancement thay đổi wrapper exception hoặc thời điểm initialization, hãy assert nguyên nhân thực tế theo test harness, không cố kết luận exception nhất thiết được ném ở dòng `find(PurchaseOrder)`.

### Đừng sửa bằng @NotFound(IGNORE)

Thử biến target bị filter thành null có thể gây mất link khi flush như cảnh báo User Guide. Nếu cần hide target khỏi API, projection/DTO an toàn hơn.

## 46. Ma trận test theo phiên bản

| Thí nghiệm | Hibernate 6.4 | Hibernate 6.5 | Hibernate 6.6 | Hibernate 7.x |
|---|---|---|---|---|
| Entity HQL query với filter enabled | Kiểm thử | Kiểm thử | Kiểm thử | Kiểm thử |
| `find(id)` và mặc định filter | Kiểm thử behavior | Kiểm thử behavior | Mặc định không áp | Mặc định không áp |
| `@FilterDef(autoEnabled=true)` | Không có member theo mốc 6.5 | Có | Có | Có |
| `@FilterDef(applyToLoadByKey=true)` | Không có member | Không có member | Có | Có |
| `@ManyToOne` target bị filter | Kiểm thử lazy/eager | Kiểm thử lazy/eager | Có thể `EntityFilterException` khi bật key filter | Tương tự contract Javadocs |
| Collection `@Filter` | Kiểm thử | Kiểm thử | Kiểm thử | Kiểm thử |
| `@SoftDelete` | Có từ 6.4 | Có | Có | Có |
| Entity đã có trong L1 cache | Không tự bị revoke | Không tự bị revoke | Không tự bị revoke | Không tự bị revoke |

Không cố ép một test suite dùng member annotation 6.6 build trên 6.5. Nếu dự án hỗ trợ nhiều Hibernate versions, tách module/source set hoặc sử dụng test profiles phù hợp.

## 47. Kiểm thử trên Spring Data JPA

Repository:

```java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    List<Account> findByActiveTrue();
}
```

Các lối vào:

```java
repository.findAll();
repository.findById(2L);
repository.findByActiveTrue();
```

không có cùng semantics filter/where:

- `findAll` thường đi qua entity query có thể áp filter.
- `findById` thường dùng JPA identifier lookup; xem `applyToLoadByKey`.
- `findByActiveTrue` có explicit predicate, có thể ổn định về active status bất kể dynamic filter, nhưng authorization tenant vẫn phải kiểm tra.

### @Transactional và current Session

Trong service:

```java
@Transactional(readOnly = true)
public List<Account> activeAccounts() {
    Session session = em.unwrap(Session.class);
    session.enableFilter("activeAccount")
           .setParameter("active", true);
    return repository.findAll();
}
```

Filter được bật trên Hibernate Session gắn transaction khi sử dụng đúng EntityManager/transaction setup.

Nhưng nếu repository được gọi trong transaction khác, thread khác hoặc sau khi Session đã nạp entities, hành vi có thể khác. Không tự tin rằng một aspect bật filter ở controller sẽ bao phủ toàn bộ repository calls trong hệ thống.

## 48. Mô hình API ít rủi ro hơn nếu cần visibility policy

Thay vì trả raw entity:

```java
public record AccountView(
    Long id,
    String maskedAccountNumber,
    boolean active
) {}
```

Thiết kế service:

```java
@Transactional(readOnly = true)
public AccountView getVisibleAccount(
        long accountId,
        String trustedTenantId) {

    Account account = em.createQuery(
        "select a from Account a " +
        "where a.id = :id " +
        "  and a.tenantId = :tenantId " +
        "  and a.active = true",
        Account.class
    )
    .setParameter("id", accountId)
    .setParameter("tenantId", trustedTenantId)
    .getResultStream()
    .findFirst()
    .orElseThrow(NotFoundOrForbiddenException::new);

    return new AccountView(
        account.getId(),
        mask(account.getAccountNumber()),
        account.isActive()
    );
}
```

`tenantId`, `getAccountNumber`, `mask` và exception là các thành phần domain/helper giả định cần có trong ứng dụng thực. Ví dụ nhấn mạnh:

- Predicate bảo mật/visibility explicit ở data access boundary.
- Tenant ID lấy từ trusted auth context.
- Không phụ thuộc vào filter enabled state ngầm định.
- Trả DTO được redacted thay vì serialize entity graph.

Khi yêu cầu nghiêm ngặt hơn, bổ sung DB RLS và security tests. Filter vẫn hữu ích để giảm lặp điều kiện query, nhưng **không là lớp bảo vệ duy nhất**.

## 49. Những lỗi thường gặp

### Lỗi 1: “Đã bật @Filter thì find(id) sẽ luôn tuân thủ”

Không đúng theo mặc định trên Hibernate 6.6/7.x. Tìm hiểu `applyToLoadByKey` và phiên bản thật.

### Lỗi 2: “autoEnabled nghĩa là bật cả direct-load filter”

Không. `autoEnabled` là chuyện filter được bật; `applyToLoadByKey` là chuyện áp khi tải by key.

### Lỗi 3: “@ManyToOne sẽ lọc giống @OneToMany”

Không. To-one thường nạp target theo identifier, to-many collection có SQL load riêng.

### Lỗi 4: “Nếu target bị ẩn thì nullable association phải thành null”

Không. Nếu FK vẫn có giá trị và target chỉ bị lọc, null hóa có thể làm mất data; `EntityFilterException` tồn tại vì lý do này.

### Lỗi 5: “@NotFound(IGNORE) giúp bỏ lỗi không ảnh hưởng data”

Nguy hiểm khi kết hợp key filter; Hibernate cảnh báo khả năng FK bị ghi NULL.

### Lỗi 6: “Bật filter sau khi collection nạp sẽ cập nhật list”

Không. Initialized collection giữ snapshot đã load.

### Lỗi 7: “Tắt filter sẽ bổ sung records bị ẩn vào collection”

Không tự động reload.

### Lỗi 8: “Filter param thay đổi sẽ revoke managed entity”

Không. Persistence Context đã có object thì không tự mất reference.

### Lỗi 9: “Filter dùng làm tenant isolation tuyệt đối”

Không. Có các đường by-ID, native, bulk và cache cần kiểm tra; dùng authorization/DB enforcement.

### Lỗi 10: “@Filter đủ để thực hiện soft delete”

Không. Nó không tự biến remove thành UPDATE marker; cân nhắc `@SoftDelete` ở 6.4+.

### Lỗi 11: “@SQLRestriction là filter có thể tắt”

Không. Đây là static restriction.

### Lỗi 12: “@Filter trên target và @FilterJoinTable là một”

Không. Condition trên target row khác condition trên join-table row.

### Lỗi 13: “Cache chỉ ảnh hưởng tốc độ, không ảnh hưởng kiểm thử filter”

Không. L1 cache làm query không chạy; L2 collection cache không tương thích với arbitrary filtered subset.

### Lỗi 14: “SQL log không thấy WHERE là Hibernate bỏ filter”

Có thể statement đang là direct by-ID path theo mặc định hoặc **không có SQL vì identity-map hit**. Phân biệt trước khi kết luận.

### Lỗi 15: “HQL query filter đúng nghĩa mọi JOIN FETCH đều an toàn”

Không. Join type và vị trí restriction có thể làm root rows bị loại hoặc to-one có semantics khác.

## 50. Bài thực hành 1: query so với find trên 6.5 và 6.6

Tạo ba Accounts như phần mở đầu:

```text
ID=1 active=true
ID=2 active=false
ID=3 active=true
```

1. Cấu hình `@FilterDef` và `@Filter` cho `activeAccount`.
2. Bật filter trong Session mới.
3. Chạy HQL `from Account`.
4. Chạy `find(Account.class, 2L)` trong Session mới khác.
5. Quan sát SQL và kết quả.
6. Thử `@FilterDef(applyToLoadByKey=true)` trên Hibernate 6.6.
7. Ghi nhận member annotation này **không có ở 6.5**.
8. Kiểm tra `find` với flag true trả gì khi Account inactive.

Giải thích vì sao hai code paths có thể khác nhau dù cùng ID.

## 51. Bài thực hành 2: quan hệ to-one bị lọc

Seed:

```text
Order#9001 -> Account#2 inactive
```

Yêu cầu:

1. Mapping `@ManyToOne(fetch=LAZY)`.
2. Bật filter mặc định `applyToLoadByKey=false`.
3. Load Order rồi initialize Account; ghi kết quả.
4. Đổi thành `applyToLoadByKey=true` trên 6.6/7.x.
5. Load trong Session mới và truy cập target.
6. Quan sát `EntityFilterException` hoặc wrapper phù hợp.
7. Thử `optional=true` và không suy luận rằng target bị ẩn nên tự null.
8. Không áp `@NotFound(IGNORE)` để làm mất liên kết.
9. So sánh với explicit HQL JOIN và `EntityGraph`.

## 52. Bài thực hành 3: to-many và filter khi collection initialize

Seed:

```text
Customer#101
  Account#1 active=true
  Account#2 active=false
  Account#3 active=true
```

1. Gắn `@Filter` lên `Customer.accounts`.
2. Session A bật filter **trước** khi load collection: kỳ vọng 2 rows.
3. Session B load toàn bộ collection rồi mới bật filter: quan sát collection đã initialized.
4. Tắt filter và đọc lại same collection.
5. Mở Session C mới không filter, đối chiếu full collection.
6. Kiểm tra `orphanRemoval` hoặc `clear()` trên collection bị lọc trong DB test riêng.
7. Không chuyển kết quả thử nghiệm mutation vào production nếu chưa có quy tắc nghiệp vụ.

## 53. Bài thực hành 4: @FilterJoinTable với membership

Tạo:

```text
users
groups
memberships(user_id, group_id, membership_active)
```

1. Gắn `@FilterJoinTable` vào `User.groups`.
2. Bật `activeMembership`.
3. Truy vấn User và initialize groups.
4. Quan sát SQL restriction áp vào cột của bảng memberships.
5. Thử `@Filter` trên `Group` để lọc Group status riêng.
6. Giải thích sự khác nhau giữa target row visibility và link-row visibility.

## 54. Bài thực hành 5: cache và filter

1. Bật filter và load Account#2 bằng query (bị loại).
2. Dùng `find(Account#2)` trong cùng/mới Session để kiểm tra đường by-ID.
3. Load Account#2 **trước** khi bật filter; gọi lại `find` sau khi bật.
4. Kiểm tra không có SQL khi L1 cache hit.
5. Thử một collection đã initialized và thay filter param.
6. Quan sát behavior của collection L2 cache/filter restrictions.
7. Nếu dự án dùng tenant filters, test L2 cache cross-tenant isolation với multiple sessions.

Phân biệt cache behavior và SQL filtering thay vì gọi mọi khác biệt là “Hibernate bug”.

## 55. Bài thực hành 6: soft delete theo phiên bản

1. Hibernate 6.3 hoặc code legacy: thiết kế soft delete bằng flag + filter + custom deletion.
2. Ghi rõ những đường lookup còn có thể bỏ qua filter.
3. Hibernate 6.4+: thử mapping `@SoftDelete`.
4. Tạo, remove và query Account; quan sát SQL soft-delete.
5. Test `find` direct, lazy to-one và query collection sau remove.
6. Kiểm tra data migration thêm soft-delete indicator cho rows cũ.
7. Thử admin cần xem deleted rows và thiết kế API riêng, không giả định `disableFilter` đủ.

Không so sánh bằng cách chạy trên hai DBs với schema khác nhau mà không tính đến migration.

## 56. Bài thực hành 7: tenant leakage và authorization

Tạo:

```text
Tenant A: Document#101
Tenant B: Document#202
```

1. Bật `tenantFilter=A`.
2. Kiểm tra `findAll` chỉ thấy A.
3. Kiểm tra `findById(202)` trên đúng Hibernate version.
4. Kiểm tra lazy association từ entity A tới target B nếu schema cho phép.
5. Bật `applyToLoadByKey=true` trên 6.6/7.x và thử lại.
6. Thử đổi tenant parameter giữa cùng Session đã load entity B.
7. Thử worker `@Async` không có filter tự động.
8. Chuyển sang explicit tenant predicate + authorization checks.
9. Nếu DB hỗ trợ, bổ sung RLS và kiểm thử trực tiếp bằng JDBC.

Mục tiêu: chứng minh rằng query filtering và **tenant security boundary** không phải cùng một thứ.

## 57. Bài thực hành 8: COUNT, JOIN và fetch plan

1. Viết HQL query Account theo filter và HQL count tương ứng.
2. Viết native count không có WHERE, ghi nhận khác biệt.
3. Thêm to-many JOIN và kiểm tra root cardinality.
4. Dùng JOIN FETCH collection + pagination, xem SQL/warning.
5. Dùng ID pagination hai bước.
6. Dùng `EntityGraph` tải to-one target bị filter.
7. So sánh với lazy to-one và giải thích khác nhau ở SQL shape.

## 58. Câu hỏi tự kiểm tra

1. `@FilterDef` khác `@Filter` ở điểm nào?
2. Filter được bật ở phạm vi Session hay toàn database?
3. Tại sao HQL query được lọc nhưng `find(id)` vẫn có thể trả row bị ẩn?
4. `applyToLoadByKey` xuất hiện trong `@FilterDef` từ mốc phiên bản nào?
5. `autoEnabled` có thay thế `applyToLoadByKey` không?
6. Vì sao `@ManyToOne` có behavior khác `@OneToMany` filtered collection?
7. Tại sao target to-one bị lọc lại có thể ném `EntityFilterException`?
8. Vì sao null hóa target có FK thật có thể gây mất dữ liệu?
9. Tại sao `@NotFound(IGNORE)` nguy hiểm trong trường hợp này?
10. `@ManyToOne(optional=true)` có nghĩa target bị ẩn phải trở thành null không?
11. Filter bật sau khi entity đã managed có “ẩn lại” entity đó được không?
12. Filter bật/tắt sau collection initialization có làm collection tự query lại không?
13. `@FilterJoinTable` áp condition lên bảng nào?
14. `@Filter` condition dùng tên Java field hay SQL column?
15. Vì sao `@Filter` không thay thế complete soft delete behavior?
16. Hibernate `@SoftDelete` được thêm từ dòng phiên bản nào?
17. `@SQLRestriction` khác filter động thế nào?
18. Native SQL/JdbcTemplate có tự dùng Hibernate `@Filter` không?
19. Vì sao filter không đủ làm tenant security?
20. `@Filter` và `@Cache` trên collection có vấn đề gì?
21. HQL count có thể khác native count khi filter bật vì sao?
22. Tại sao nên test trên Session mới khi kiểm tra filter?
23. Worker `@Async` có tự nhận filter đã bật trên request không?
24. JOIN FETCH/EAGER có làm đổi SQL path so với lazy by-key không?
25. Cần làm gì trước khi đổi từ Hibernate 6.5 lên 6.6 để dùng `applyToLoadByKey`?

**Gợi ý:** (1) định nghĩa và áp dụng mapping; (2) Session; (3) mặc định bỏ qua identifier lookup; (4) 6.6; (5) không; (6) direct target ID khác collection SQL; (7) tránh null hóa FK thật; (8) flush có thể ghi null FK; (9) làm mất liên kết; (10) không; (11) không tự revoke; (12) không; (13) join table; (14) SQL column; (15) không xử lý write-side remove; (16) 6.4; (17) restriction tĩnh; (18) không; (19) bypass và thiếu DB enforcement; (20) cache không biết dynamic subset; (21) native không tự áp filter; (22) tránh L1 cache hits; (23) không; (24) có; (25) kiểm tra version, mapping, to-one exception và tests.

## 59. Những nguyên tắc quan trọng cần nhớ

1. **Đường tải quyết định hành vi filter.** HQL/Criteria query, `find(id)`, load qua to-one và collection không đương nhiên tương đương.
2. **Hibernate 6.6/7.x mặc định không áp dynamic filter lên primary-key lookups**, ví dụ `find()` và target `@ManyToOne`; `applyToLoadByKey` mặc định `false`.
3. **`applyToLoadByKey=true` có từ Hibernate 6.6** và có thể lọc direct lookup; không dùng annotation member này trong code build trên 6.5.
4. **Khi filter loại target của to-one**, Hibernate có thể ném `EntityFilterException` thay vì tự đưa foreign key association về null.
5. **Tránh `@NotFound(IGNORE)` để che filtered target.** Việc null hóa association có nguy cơ ghi mất FK.
6. **To-many collections áp filter trên collection load**, và `@FilterJoinTable` dành cho restriction trên các rows của join table.
7. **Filter có hiệu lực theo Session, không theo toàn database**, và chỉ với những mapping/SQL paths được hỗ trợ.
8. **Bật filter trước khi load.** Object hay collection đã initialized trong Persistence Context không tự bị lọc hoặc refresh khi thay filter.
9. **`autoEnabled` khác `applyToLoadByKey`.** Một thuộc tính quyết định enable; thuộc tính kia quyết định key lookup semantics.
10. **`@SoftDelete` từ 6.4 là hướng chuyên dụng cho soft deletion**, khác với filter động và static `@SQLRestriction`.
11. **Filter không phải authorization hoặc RLS.** Tăng cường bằng trusted tenant context, explicit predicates và database enforcement nếu cần.
12. **Đừng coi filtered collection là toàn bộ association để xóa/sửa hàng loạt** khi còn những rows bị ẩn.
13. **Filter và L1/L2 cache cần thiết kế cùng nhau.** First-level hits làm thay đổi đường load; dynamic-filtered collection không phù hợp cache snapshot dùng chung.
14. **Fetch plan, JOIN type và SQL ON/WHERE placement ảnh hưởng kết quả**, đặc biệt to-one, eager loading và join fetch.
15. **Integration test trên đúng Hibernate version và database** phải bao gồm query, find by ID, lazy/eager relations, collection, cache, tenant, async và native/bulk paths.

Khi một ứng dụng cần “ẩn” bản ghi, câu hỏi quan trọng không phải chỉ là **“đã viết `@Filter` chưa?”** mà là **“mọi con đường đọc và ghi dữ liệu có tuân thủ cùng chính sách visibility hay không, và phiên bản Hibernate hiện tại hỗ trợ những bảo đảm nào?”**. Phân biệt được identifier loads với relation loads là bước quyết định để tránh những lỗi soft-delete, kết quả không nhất quán và rò dữ liệu qua foreign key association.

### Tài liệu tham khảo chính thức theo phiên bản

- [Hibernate ORM 6.5 Javadocs — FilterDef (chưa có applyToLoadByKey)](https://docs.hibernate.org/orm/6.5/javadocs/org/hibernate/annotations/FilterDef.html)
- [Hibernate ORM 6.6 Javadocs — FilterDef](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/FilterDef.html)
- [Hibernate ORM 7.4 Javadocs — FilterDef](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/annotations/FilterDef.html)
- [Hibernate ORM 6.6 Javadocs — EntityFilterException](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/EntityFilterException.html)
- [Hibernate ORM 7.4 Javadocs — EntityFilterException](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/EntityFilterException.html)
- [Hibernate ORM 6.6 User Guide — @Filter và load by key](https://docs.hibernate.org/orm/6.6/userguide/html_single/#pc-filter)
- [Hibernate ORM 6.6 User Guide — @FilterJoinTable](https://docs.hibernate.org/orm/6.6/userguide/html_single/#pc-filter-join-table)
- [Hibernate ORM 6.6 Introduction — Filters](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
- [Hibernate ORM 6.6 User Guide — Soft Delete](https://docs.hibernate.org/orm/6.6/userguide/html_single/#soft-delete)
- [Hibernate ORM 7.x Javadocs — SoftDelete](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/annotations/SoftDelete.html)
- [Hibernate ORM 6.6 Javadocs — Filter](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/Filter.html)
- [Hibernate ORM 6.6 Javadocs — FilterJoinTable](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/FilterJoinTable.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
