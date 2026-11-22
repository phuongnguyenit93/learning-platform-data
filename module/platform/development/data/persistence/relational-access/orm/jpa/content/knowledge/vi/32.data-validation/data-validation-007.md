# Phân biệt kiểm tra duy nhất trước ghi và ràng buộc UNIQUE thực tế trong JPA

Khi xây dựng chức năng đăng ký tài khoản, tạo mã sản phẩm, ghi nhận email khách hàng, lưu tên người dùng hoặc tạo mã đơn hàng, ứng dụng thường cần bảo đảm **một giá trị không bị trùng**. Cách triển khai dễ nghĩ đến là truy vấn database trước khi ghi:

```java
if (repository.existsByEmail(email)) {
    throw new DuplicateEmailException();
}

repository.save(new UserAccount(email));
```

Cách viết này có thể giúp phản hồi sớm nếu email **đã tồn tại tại thời điểm truy vấn**, nhưng **không bảo đảm email vẫn còn trống khi `INSERT` diễn ra**. Hai request có thể cùng đọc “chưa tồn tại”, sau đó cùng cố tạo một hàng mang email đó.

Cơ chế bảo vệ bất biến cuối cùng phải nằm ở nơi tất cả giao dịch ghi phải được điều phối: **ràng buộc `UNIQUE` hoặc unique index thực tế trên database**.

Bài học này thuộc chương **Kiểm tra dữ liệu**, chủ đề **Data Persistence Relational Access ORM JPA**, tập trung trực tiếp vào **“Phân biệt kiểm tra duy nhất trước ghi và ràng buộc UNIQUE thực tế”**.

Nội dung bao gồm:

- Tại sao `existsBy...` hoặc `SELECT COUNT(...)` không thể loại bỏ race condition.
- Cách thiết kế khóa duy nhất một cột hoặc nhiều cột.
- Sự khác nhau giữa JPA annotations và ràng buộc thực sự đã triển khai trong database.
- Cách phát hiện lỗi UNIQUE ở `persist`, `flush` hoặc `commit`.
- Cách chuyển lỗi database thành lỗi nghiệp vụ mà không che giấu lỗi khác.
- Cách kiểm thử hai transactions cùng vượt qua pre-check nhưng chỉ một transaction được phép ghi.
- Những tình huống phức tạp: chuẩn hóa chuỗi, phân biệt hoa/thường, `NULL`, tenant, soft delete, `@Version`, upsert, idempotency và migration.

**Nguyên tắc trung tâm:** *Pre-check phục vụ phản hồi sớm và trải nghiệm người dùng; `UNIQUE` thực tế ở database mới bảo vệ tính duy nhất trong điều kiện ghi đồng thời.*

---

## 1. Hai kiểu kiểm tra có vai trò khác nhau

Một pre-check hỏi:

> “Tại thời điểm truy vấn này, tôi có nhìn thấy bản ghi mang khóa nghiệp vụ K hay không?”

Ràng buộc UNIQUE ở database đặt yêu cầu:

> “Không cho phép một `INSERT` hoặc `UPDATE` tạo ra trạng thái dữ liệu vi phạm tính duy nhất của khóa K.”

| Tiêu chí | Kiểm tra trước ghi | Ràng buộc UNIQUE thực tế |
| --- | --- | --- |
| Thực hiện bởi | Application/service/repository | Database engine |
| Cơ chế thường dùng | `existsBy...`, `COUNT`, `SELECT` | `UNIQUE`, unique index |
| Thời điểm | Trước ghi | Khi database kiểm tra thao tác ghi |
| Mục tiêu | Phản hồi sớm, UX | Bất biến dữ liệu |
| Chống hai request cùng ghi giá trị | **Không đủ** | **Có**, theo semantics database |
| Bảo vệ native SQL/ứng dụng khác | Chỉ nếu đường ghi cũng check | Có nếu tất cả writers ghi vào bảng có constraint |
| Có thêm SELECT? | Thường có | Không bắt buộc |
| Có bị race giữa check và write? | Có | Điểm kiểm tra unique được DB điều phối |
| Thông báo lỗi | Dễ tùy biến | Cần dịch SQL exception |
| Cần migration? | Không riêng cho pre-check | **Có** để triển khai constraint thật |

Không có mâu thuẫn nếu `existsByEmail(...)` trả `false` nhưng `INSERT` sau đó nhận unique violation: **hai thời điểm khác nhau, dữ liệu có thể thay đổi giữa chúng**.

### 1.1. TOCTOU: lỗi check-then-act

Tình huống này thường được gọi là **time-of-check to time-of-use (TOCTOU)**:

```text
Transaction T1                        Transaction T2
--------------                        --------------
SELECT email K -> chưa tồn tại

                                      SELECT email K -> chưa tồn tại

INSERT email K
COMMIT thành công

                                      INSERT email K
                                      |
                                      +-- Có UNIQUE: bị từ chối
                                      |
                                      +-- Không UNIQUE: có thể ghi trùng
```

Pre-check **không đặt chỗ** giá trị K, không tự khóa một khóa chưa tồn tại, và không cam kết rằng request đang kiểm tra sẽ là request ghi trước.

### 1.2. Transaction không tự biến SELECT thành reservation

Ngay cả khi đặt câu `SELECT` và `INSERT` trong cùng một `@Transactional` method, hai giao dịch khác nhau vẫn có thể cùng quan sát trạng thái chưa có row trước khi một bên ghi.

Transaction đảm bảo atomicity theo quy tắc database; nó không đồng nghĩa với việc một phép đọc tìm giá trị chưa tồn tại sẽ khóa vĩnh viễn giá trị đó trên mọi database/isolation mode.

---

## 2. Xác định khóa duy nhất từ nghiệp vụ

Giả sử ứng dụng SaaS có nhiều tổ chức (tenants):

- Một tổ chức không được có hai tài khoản cùng email sau chuẩn hóa.
- Hai tổ chức khác nhau **được phép** có cùng email.
- Email nhập `Alice@Example.com` và `alice@example.com` được coi là giống nhau theo chính sách sản phẩm.
- Khi sửa email của một tài khoản, quy tắc này vẫn phải được kiểm tra.

Khóa nghiệp vụ cần bảo vệ:

```text
(tenant_id, normalized_email)
```

Ví dụ:

| id | tenant_id | email gốc | normalized_email | Hợp lệ? |
| ---: | ---: | --- | --- | --- |
| 101 | 1 | Alice@Example.com | alice@example.com | Có |
| 102 | 2 | alice@example.com | alice@example.com | Có, tenant khác |
| 103 | 1 | bob@example.com | bob@example.com | Có |
| 104 | 1 | alice@example.com | alice@example.com | **Không**, trùng với row 101 |

Một `UNIQUE(normalized_email)` toàn cục quá chặt vì chặn row 102. Hai ràng buộc riêng `UNIQUE(tenant_id)` và `UNIQUE(normalized_email)` càng sai hơn.

### 2.1. Câu hỏi cần trả lời trước khi viết annotation

1. Unique trên toàn hệ thống hay theo tenant?
2. Có phân biệt chữ hoa/thường không?
3. Dùng giá trị người dùng nhập hay một khóa canonical?
4. Trường có được `NULL` không?
5. Soft-deleted record còn chiếm tên/email không?
6. Một account có được đổi email không?
7. Restore account đã soft-delete có thể conflict không?
8. Có nhiều đường ghi từ JPA, JDBC, batch, job hoặc hệ thống khác không?
9. Retry cùng request cần được nhận diện bằng idempotency key không?
10. Bất biến có thật sự là equality uniqueness, hay phức tạp hơn như khoảng thời gian chồng lấp?

**Unique constraint chỉ bảo vệ chính xác biểu thức, tập cột, predicate và quy tắc so sánh mà database được cấu hình.** Sai quy tắc là sai nghiệp vụ dù database thực thi constraint hoàn hảo.

---

## 3. Entity JPA với unique key ghép

Ví dụ dùng Java 17+ và Jakarta Persistence.

```java
package com.example.accounts.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import java.util.Locale;

@Entity
@Table(
    name = "user_accounts",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_accounts_tenant_email",
        columnNames = {"tenant_id", "normalized_email"}
    )
)
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "email", nullable = false, length = 320)
    private String email;

    @Column(
        name = "normalized_email",
        nullable = false,
        length = 320
    )
    private String normalizedEmail;

    @Version
    private Long version;

    protected UserAccount() {
    }

    public UserAccount(Long tenantId, String email) {
        if (tenantId == null) {
            throw new IllegalArgumentException(
                "tenantId is required"
            );
        }
        this.tenantId = tenantId;
        changeEmail(email);
    }

    public void changeEmail(String nextEmail) {
        if (nextEmail == null || nextEmail.isBlank()) {
            throw new IllegalArgumentException(
                "Email is required"
            );
        }

        String cleaned = nextEmail.strip();

        this.email = cleaned;
        this.normalizedEmail =
            cleaned.toLowerCase(Locale.ROOT);
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getEmail() {
        return email;
    }

    public String getNormalizedEmail() {
        return normalizedEmail;
    }

    public Long getVersion() {
        return version;
    }
}
```

Ở đây:

- `@Table(uniqueConstraints=...)` mô tả **khóa duy nhất gồm hai cột**.
- `columnNames` là tên **cột database**, không phải tên field Java.
- `tenantId` được dùng như scalar để ví dụ ngắn gọn; hệ thống thật có thể map nó với quan hệ `@ManyToOne`.
- `changeEmail()` cập nhật đồng bộ email hiển thị và normalized key.
- `@Version` hỗ trợ optimistic locking trên một row nhưng **không ngăn hai rows mới có cùng email**.

### 3.1. Chuẩn hóa email là quyết định nghiệp vụ

Phép `strip().toLowerCase(Locale.ROOT)` trong ví dụ thể hiện quy tắc case-insensitive đơn giản, **không phải chuẩn canonicalization đầy đủ cho mọi email trên Internet**. Local part, Unicode, domain IDN và cách từng email provider xử lý địa chỉ có những đặc thù.

Không tự áp các quy tắc riêng của một provider (ví dụ bỏ dấu chấm trong username) lên tất cả địa chỉ email. Hệ thống phải xác định policy rõ và áp dụng nó thống nhất giữa dữ liệu cũ, pre-check, INSERT và UPDATE.

### 3.2. Tránh để email và normalized key bị lệch

Nếu có setter công khai chỉ sửa `email` mà không sửa `normalizedEmail`, ứng dụng có thể kiểm tra một key khác với dữ liệu người dùng nhìn thấy.

Giữ cách đổi email trong một domain method là một biện pháp giảm sai lệch. Tuy nhiên, bulk/native SQL vẫn có thể bỏ qua method này; nếu có nhiều writers, cân nhắc generated column hoặc functional index theo database.

---

## 4. UNIQUE thực tế trên database

DDL PostgreSQL minh họa:

```sql
CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uk_accounts_tenant_email
        UNIQUE (tenant_id, normalized_email)
);
```

UNIQUE bảo vệ cả các đường ghi không chạy qua pre-check Java:

```text
JPA EntityManager.persist()
Spring Data JpaRepository.save()
JDBC PreparedStatement
Native SQL
Batch job, ETL
Một ứng dụng khác ghi cùng bảng
```

Database phải thực thi ràng buộc khi các writers cùng thao tác trên bảng đó. Đây là điểm quan trọng nhất về **tính đúng đắn xuyên qua nhiều instance và nhiều quy trình ghi**.

### 4.1. Annotation không đồng nghĩa constraint đã tồn tại

```java
@Column(unique = true)
private String username;
```

và:

```java
@Table(
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"tenant_id", "normalized_email"}
    )
)
```

là **metadata về schema**. Trong production đã có database và dùng Flyway/Liquibase/SQL migrations, thay đổi annotation **không tự bảo đảm bảng hiện có được sửa**.

Nếu ràng buộc chưa được deploy, database có thể tiếp tục nhận hai hàng duplicate dù Java entity đã có `@UniqueConstraint`.

### 4.2. Đừng dựa hoàn toàn vào ORM schema validation

Một số chế độ validation của provider kiểm tra bảng và cột nhưng không nhất thiết xác minh chính xác mọi unique index, expression index, partial predicate hoặc collation theo nhu cầu nghiệp vụ.

Nên dùng:

- Migration rõ ràng.
- Kiểm tra metadata database.
- Test INSERT trùng thực tế.
- Test các trường hợp được phép, ví dụ cùng email ở hai tenants.

### 4.3. Tên constraint có nghĩa giúp xử lý lỗi

Ví dụ:

```text
uk_accounts_tenant_email
uk_accounts_tenant_username
uk_products_tenant_sku
uk_orders_tenant_code
```

Tên ổn định giúp dịch exception sang mã lỗi nghiệp vụ mà không cần parse một chuỗi SQL exception tự do.

---

## 5. Một cột, nhiều cột và primary key

### 5.1. Unique một cột

Nếu username phải duy nhất toàn hệ thống:

```java
@Column(
    name = "username",
    nullable = false,
    unique = true
)
private String username;
```

Database cần có constraint/index mang ý nghĩa:

```sql
UNIQUE (username)
```

### 5.2. Unique ghép theo tenant

Nếu SKU chỉ duy nhất trong tenant:

```java
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
```

tương ứng:

```sql
UNIQUE (tenant_id, sku)
```

Không tương đương với hai unique constraints riêng trên từng cột.

### 5.3. Primary key không thay business unique

`@Id` đã tạo row identity độc lập:

```text
id=101, email=alice@example.com
id=102, email=alice@example.com
```

Hai IDs khác nhau không hề vi phạm primary key. Chỉ business unique constraint mới ngăn trùng email nếu đó là yêu cầu.

### 5.4. Hibernate @NaturalId cũng không thay migration

`@NaturalId` là extension Hibernate mô tả natural identity và có thể hỗ trợ cache/truy vấn theo natural ID. Nó **không tự chứng minh production database đã có UNIQUE đúng**. Migration vẫn phải được triển khai và kiểm chứng.

---

## 6. Pre-check bằng Spring Data JPA

Repository:

```java
package com.example.accounts.repository;

import com.example.accounts.domain.UserAccount;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserAccountRepository
        extends JpaRepository<UserAccount, Long> {

    boolean existsByTenantIdAndNormalizedEmail(
        Long tenantId,
        String normalizedEmail
    );
}
```

Service:

```java
package com.example.accounts.service;

import com.example.accounts.domain.UserAccount;
import com.example.accounts.repository.UserAccountRepository;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegisterAccountService {

    private final UserAccountRepository accounts;

    public RegisterAccountService(
            UserAccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public Long register(Long tenantId, String email) {
        if (tenantId == null ||
                email == null ||
                email.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant and email are required"
            );
        }

        String canonical =
            email.strip().toLowerCase(Locale.ROOT);

        if (accounts.existsByTenantIdAndNormalizedEmail(
                tenantId, canonical)) {
            throw new DuplicateEmailException();
        }

        UserAccount account =
            accounts.save(new UserAccount(tenantId, email));

        return account.getId();
    }
}
```

Domain exception do ứng dụng định nghĩa:

```java
package com.example.accounts.service;

public class DuplicateEmailException
        extends RuntimeException {

    public DuplicateEmailException() {
        super("Email already exists in this tenant");
    }
}
```

**Pre-check chỉ cung cấp phản hồi sớm.** Database vẫn cần `UNIQUE (tenant_id, normalized_email)`.

### 6.1. Vì sao vẫn có race?

```text
Request A: exists(...) -> false
Request B: exists(...) -> false

Request A: save(...)
Request B: save(...)
```

Cả hai đã vượt qua `if`. Một writer được phép commit; writer còn lại cần bị unique constraint từ chối hoặc phải chịu outcome tương ứng với chính sách transaction/database.

### 6.2. `save()` không phải `commit()`

`save()` có thể làm entity managed hoặc gửi SQL sớm tùy ID generation/provider. Vi phạm UNIQUE có thể xuất hiện ở `save`, `flush`, `saveAndFlush` hoặc giai đoạn commit.

Một `@Transactional` method có thể chạy hết body, sau đó transaction interceptor mới bắt đầu commit. Vì vậy **catch chỉ quanh `repository.save()` có thể không thấy exception tại commit**.

### 6.3. Pre-check ở giao diện không phải đặt chỗ

Một API kiểm tra email khả dụng có thể trả `available=true`, nhưng đến khi người dùng gửi form thì request khác đã tạo email trước.

Giao diện phải chuẩn bị nhận `409 Conflict` từ API tạo tài khoản dù trước đó đã nhận thông báo khả dụng.

---

## 7. Pre-check thuần JPQL

Không dùng Spring Data:

```java
private static boolean accountExists(
        EntityManager em,
        Long tenantId,
        String normalizedEmail) {

    Long count = em.createQuery(
        """
        SELECT COUNT(a)
        FROM UserAccount a
        WHERE a.tenantId = :tenant
          AND a.normalizedEmail = :email
        """,
        Long.class
    )
    .setParameter("tenant", tenantId)
    .setParameter("email", normalizedEmail)
    .getSingleResult();

    return count > 0L;
}
```

`COUNT` dễ hiểu nhưng không phải hình thức tối ưu duy nhất. Query dạng `EXISTS`/chọn một row với giới hạn phù hợp có thể nhanh hơn tùy database và index. Đo execution plan/latency thực tế trước khi chuẩn hóa lựa chọn.

### 7.1. Transaction bao cả kiểm tra và ghi vẫn có race

```java
em.getTransaction().begin();

boolean exists = accountExists(
    em, tenantId, normalizedEmail
);

if (!exists) {
    em.persist(account);
}

em.getTransaction().commit();
```

Hai transactions vẫn có thể cùng thấy `exists=false` ở những thời điểm khác nhau trước khi một bên ghi.

### 7.2. SELECT FOR UPDATE trên hàng không tồn tại

```sql
SELECT id
FROM user_accounts
WHERE tenant_id = 1
  AND normalized_email = 'alice@example.com'
FOR UPDATE;
```

Khi kết quả không có row, **không được mặc định khóa đã giữ chỗ email đó** trong mọi database/isolation mode.

Một số engines có gap locks hoặc predicate locks. Đó là cơ chế database-specific, không thay thế đơn giản cho UNIQUE constraint.

---

## 8. Hai transactions cùng vượt qua pre-check

Ví dụ email chưa tồn tại:

```text
Thời gian    Transaction T1                  Transaction T2
---------    --------------                  --------------
t1           BEGIN                           BEGIN

t2           SELECT COUNT(key) -> 0

t3                                           SELECT COUNT(key) -> 0

t4           INSERT key

t5           COMMIT

t6                                           INSERT key

t7                                           UNIQUE violation
                                             ROLLBACK

Database cuối: một row mang key
```

T1 và T2 đều đọc chính xác trạng thái mà chúng nhìn thấy tại thời điểm SELECT. **Lỗi không phải hai câu SELECT sai; lỗi sẽ xảy ra nếu ứng dụng tin rằng SELECT đã đủ để bảo vệ trạng thái cuối.**

### 8.1. Khi T2 INSERT trước khi T1 commit

T2 có thể phải chờ lock trên unique key hoặc chờ transaction T1 kết thúc:

```text
T1 INSERT K, chưa commit
T2 INSERT K -> có thể chờ

T1 COMMIT   -> T2 bị unique violation
T1 ROLLBACK -> T2 có thể INSERT thành công
```

Hành vi cụ thể phụ thuộc database/isolation/driver. Để kiểm thử logic UNIQUE ít flaky, dùng interleaving **hai bên SELECT trước, T1 commit, rồi T2 INSERT**.

### 8.2. Serializable isolation không thay unique guarantee

Ở mức isolation cao, một số DB có thể ném serialization failure thay vì cùng kiểu unique violation ở mọi lịch. Nếu mục đích test là **constraint name/SQLSTATE cụ thể**, hãy chỉ rõ database và isolation. Nếu mục đích là **không có duplicate sau các transaction**, có thể thiết kế assertion invariant theo outcome được phép.

---

## 9. UNIQUE violation có thể được báo khi nào?

Một transaction:

```text
BEGIN
   |
   v
Pre-check SELECT
   |
   v
EntityManager.persist(account)
   |
   v
SQL INSERT khi provider chọn thực thi
   |
   +-- UNIQUE OK -----> COMMIT
   |
   +-- Vi phạm UNIQUE -> exception -> ROLLBACK
```

Với `GenerationType.IDENTITY`, provider có thể INSERT sớm để lấy generated ID. Với strategy khác, lỗi có thể xuất hiện ở `flush()` hoặc `commit()`.

### 9.1. Flush không phải commit

```java
em.persist(account);
em.flush(); // Có thể INSERT xong nhưng transaction chưa commit.
```

Sau một flush thành công, transaction vẫn có thể rollback vì nghiệp vụ khác thất bại.

### 9.2. saveAndFlush chỉ thay thời điểm đồng bộ

```java
accounts.saveAndFlush(account);
```

Có thể đưa lỗi UNIQUE ra sớm hơn, nhưng **không xóa race và không đồng nghĩa committed state**.

### 9.3. Deferrable unique constraints

Một số DB hỗ trợ unique constraints được kiểm tra muộn hơn, có thể tại commit nếu được cấu hình deferred. Không phải mọi unique index/DB đều hỗ trợ loại deferral này.

Exception handler nên bao phủ transaction boundary, không phụ thuộc duy nhất vào một dòng `flush`.

---

## 10. Ba lớp kiểm tra dữ liệu cần phân biệt

| Lớp | Công cụ | Mục tiêu |
| --- | --- | --- |
| Bean Validation | `@NotBlank`, `@Email`, `@Size` | Kiểm tra định dạng, giá trị |
| Application pre-check | `existsBy...`, `COUNT` | Nhìn trạng thái trước ghi |
| Database integrity | `UNIQUE`, `NOT NULL`, `CHECK`, `FOREIGN KEY` | Bất biến dữ liệu thực |

### 10.1. @Email không kiểm tra email duy nhất

```java
@NotBlank
@Email
private String email;
```

Đây là validation cú pháp và rỗng theo implementation, không có concurrency guarantee.

### 10.2. Custom @UniqueEmailValidator vẫn có TOCTOU

Nếu một custom Bean Validation `ConstraintValidator` gọi repository SELECT rồi trả true, hai requests vẫn có thể cùng pass validator trước khi ghi.

Custom validation có thể dùng cho UX; không dùng để thay database UNIQUE.

### 10.3. Hai loại ConstraintViolationException

**Bean Validation:**

```java
jakarta.validation.ConstraintViolationException
```

**Hibernate ORM database constraint error:**

```java
org.hibernate.exception.ConstraintViolationException
```

Cùng tên lớp ngắn nhưng khác hoàn toàn ý nghĩa. Loại thứ hai có thể đại diện UNIQUE, FK, CHECK hoặc NOT NULL, không tự khẳng định “email trùng”.

---

## 11. Tầng exception JDBC, JPA và Spring

Luồng lỗi có thể như sau:

```text
DB unique violation
        |
        v
JDBC SQLException
        |
        v
ORM/JPA exception
        |
        v
Spring DataAccessException / transaction wrapper
        |
        v
REST exception handler
```

Loại wrapper tùy DB, JPA provider, thời điểm exception, Spring transaction manager và exception translation.

### 11.1. PostgreSQL SQLSTATE 23505

PostgreSQL dùng SQLSTATE `23505` cho `unique_violation`.

```java
private static boolean isPostgresUniqueViolation(
        Throwable error) {

    for (Throwable current = error;
            current != null;
            current = current.getCause()) {

        if (current instanceof java.sql.SQLException sql
                && "23505".equals(sql.getSQLState())) {
            return true;
        }
    }

    return false;
}
```

Đây là classifier **PostgreSQL-specific**. Trên DB khác cần error code/SQLState phù hợp, không mặc định sao chép `23505`.

### 11.2. SQLSTATE không xác định unique key nào

Nếu bảng có:

```sql
UNIQUE (tenant_id, normalized_email);
UNIQUE (tenant_id, username);
```

cả hai có thể báo `23505`. Để trả đúng lỗi email hay username, cần constraint name hoặc DB metadata có cấu trúc.

### 11.3. Hibernate constraint name

Hibernate ORM có:

```java
org.hibernate.exception.ConstraintViolationException
    .getConstraintName()
```

Provider có thể trả `uk_accounts_tenant_email`, nhưng đôi khi giá trị null hoặc có schema/quotes tùy dialect và driver.

### 11.4. Spring DataIntegrityViolationException

`org.springframework.dao.DataIntegrityViolationException` có thể bao gồm UNIQUE, FK, NOT NULL, CHECK hoặc lỗi integrity khác.

**Không viết `catch (DataIntegrityViolationException) { throw new DuplicateEmailException(); }` không điều kiện.**

---

## 12. Chuyển đúng unique violation thành business error

Classifier Hibernate-specific:

```java
package com.example.accounts.service;

public final class IntegrityClassifier {

    private static final String EMAIL_CONSTRAINT =
        "uk_accounts_tenant_email";

    private IntegrityClassifier() {
    }

    public static boolean isDuplicateTenantEmail(
            Throwable error) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (current instanceof
                    org.hibernate.exception.ConstraintViolationException
                    hibernateError) {

                String constraint =
                    hibernateError.getConstraintName();

                if (constraint != null &&
                        EMAIL_CONSTRAINT.equalsIgnoreCase(
                            constraint
                        )) {
                    return true;
                }
            }
        }

        return false;
    }
}
```

Đây là ví dụ cần **kiểm thử với đúng Hibernate/dialect/database**. Nếu DB/driver không trả tên, ứng dụng cần một chính sách phân loại bổ sung; không tự bịa “email đã tồn tại” khi metadata không đủ.

### 12.1. Không parse message text tùy tiện

Sai:

```java
if (exception.getMessage().contains("Duplicate entry")) {
    // ...
}
```

Message có thể thay đổi theo driver, phiên bản, locale hoặc chứa dữ liệu nhạy cảm. Ưu tiên structured metadata, SQLState và tên constraint đã biết.

### 12.2. Lỗi không xác định phải được giữ đúng loại

Một mất kết nối, syntax error, missing table hoặc FK violation không phải duplicate email. Lỗi cơ sở hạ tầng phải được log/phân loại riêng; không trả thông điệp sai khiến người dùng liên tục đổi email mà vẫn không đăng ký được.

---

## 13. REST API và HTTP 409 Conflict

Một DTO trả lỗi:

```java
public record ApiError(
    String code,
    String message
) {
}
```

Ví dụ với Spring MVC:

```java
@RestControllerAdvice
public class AccountExceptionAdvice {

    @ExceptionHandler(DuplicateEmailException.class)
    public ResponseEntity<ApiError> duplicate(
            DuplicateEmailException ex) {

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "EMAIL_ALREADY_EXISTS",
                "Email is already used in this tenant"
            ));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiError> integrity(
            DataIntegrityViolationException ex) {

        if (IntegrityClassifier.isDuplicateTenantEmail(ex)) {
            return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(new ApiError(
                    "EMAIL_ALREADY_EXISTS",
                    "Email is already used in this tenant"
                ));
        }

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(new ApiError(
                "DATA_INTEGRITY_ERROR",
                "Request could not be completed"
            ));
    }
}
```

Các imports Spring MVC:

```java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
```

Đoạn handler có fallback minh họa; hệ thống production nên có error taxonomy riêng cho FK/CHECK/NOT NULL, validation failures và lỗi ngoài dự kiến.

### 13.1. Vì sao 409?

`409 Conflict` phù hợp trong nhiều create/update APIs khi request xung đột với resource state. Một API có thể chọn mã khác theo hợp đồng, chẳng hạn `422`, nhưng phải nhất quán.

Không chuyển **mọi** database integrity violation thành 409.

### 13.2. Không lộ SQL ra client

Không trả raw exception message, SQL text, constraint diagnostics chứa giá trị dữ liệu hoặc stack trace. Log nội bộ với correlation ID và tuân thủ chính sách bảo vệ dữ liệu.

### 13.3. Body @Transactional method và commit boundary

Transaction interceptor có thể commit sau khi method body trả. Nếu commit thất bại, exception xảy ra **ngoài try/catch nội bộ quanh `save()`**.

Đặt mapping lỗi tại boundary bao trùm lời gọi service transaction đã hoàn tất hoặc thiết kế translation riêng có kiểm thử.

---

## 14. Sau unique violation phải rollback

Một lỗi SQL có thể đánh dấu transaction rollback-only hoặc khiến DB transaction aborted. Với PostgreSQL, việc tiếp tục query ngay trong cùng transaction sau constraint violation có thể thất bại.

Sai:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    // Sai nếu cố query tiếp khi transaction đang aborted.
    boolean exists = accountExists(em, tenantId, email);
}
```

Cách an toàn thường là:

1. Bắt exception ở boundary phù hợp.
2. Rollback transaction nếu còn active.
3. Không tái sử dụng persistence context lỗi như một transaction lành mạnh.
4. Dựa trên exception metadata đã giữ để phân loại.
5. Nếu cần đọc lại database, mở transaction và context mới.

### 14.1. Resource-local example

```java
public Long register(
        EntityManagerFactory emf,
        Long tenantId,
        String email) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        UserAccount candidate =
            new UserAccount(tenantId, email);

        if (accountExists(
                em, tenantId,
                candidate.getNormalizedEmail())) {
            throw new DuplicateEmailException();
        }

        em.persist(candidate);
        em.flush();

        Long id = candidate.getId();

        em.getTransaction().commit();
        return id;

    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }

        if (IntegrityClassifier.isDuplicateTenantEmail(ex)) {
            throw new DuplicateEmailException();
        }

        throw ex;

    } finally {
        em.close();
    }
}
```

Đây là ứng dụng **RESOURCE_LOCAL**. Với JTA hoặc Spring-managed transactions, không dùng `em.getTransaction()` để điều khiển transaction container-managed.

### 14.2. Không nuốt DataIntegrityViolationException trong @Transactional

Sai:

```java
@Transactional
public Long register(...) {
    try {
        accounts.saveAndFlush(account);
    } catch (DataIntegrityViolationException ex) {
        return -1L;
    }
}
```

Transaction có thể đã không thể commit, nhưng method lại trả một “ID” giả. Cần để lỗi propagate và rollback, sau đó chuyển sang domain/API error ở boundary thích hợp.

---

## 15. Kiểm thử UNIQUE thực tế, không chỉ mock pre-check

Unit test có thể kiểm tra branch:

```java
when(repository.existsByTenantIdAndNormalizedEmail(
    100L, "alice@example.com"
)).thenReturn(true);
```

Nó chỉ chứng minh service ném lỗi khi repository báo đã tồn tại.

Nó **không kiểm chứng**:

- UNIQUE đã tồn tại trong DB.
- Driver sẽ trả SQLState nào.
- Hai transactions cùng pass pre-check có thể bị từ chối khi INSERT.
- Transaction có rollback đúng.
- Constraint có đúng cột, collation và predicate không.

Cần một **JPA integration test** với database thật hoặc môi trường tương ứng production.

### 15.1. Fixture helper

Ví dụ JUnit 5 và `EntityManagerFactory` RESOURCE_LOCAL:

```java
private static Long insertCommitted(
        EntityManagerFactory emf,
        Long tenantId,
        String email) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        UserAccount account =
            new UserAccount(tenantId, email);

        em.persist(account);
        em.flush();

        Long id = account.getId();

        em.getTransaction().commit();
        return id;

    } catch (RuntimeException ex) {
        rollbackIfActive(em);
        throw ex;

    } finally {
        em.close();
    }
}

private static void rollbackIfActive(EntityManager em) {
    if (em != null &&
            em.isOpen() &&
            em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
}
```

Tạo fixture trong transaction riêng, commit và đóng EntityManager trước khi chạy test đo.

### 15.2. Test INSERT trùng dù không pre-check

```java
@Test
void databaseRejectsDuplicateWithoutPrecheck() {
    Long tenantId = 100L;

    String email =
        "unique-" + UUID.randomUUID() + "@example.test";

    insertCommitted(emf, tenantId, email);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        RuntimeException error = assertThrows(
            RuntimeException.class,
            () -> {
                em.persist(
                    new UserAccount(tenantId, email)
                );
                em.flush();
                em.getTransaction().commit();
            }
        );

        assertTrue(
            isPostgresUniqueViolation(error),
            "Expected PostgreSQL UNIQUE violation"
        );

    } finally {
        rollbackIfActive(em);
        em.close();
    }
}
```

Đây là test PostgreSQL cụ thể khi dùng helper `isPostgresUniqueViolation`. Với DB khác, thay classifier tương ứng.

**Không chỉ assert một `RuntimeException` bất kỳ**: lỗi network/missing table vẫn có thể khiến test xanh giả.

---

## 16. Kiểm thử hai giao dịch cùng vượt qua pre-check

Để chứng minh TOCTOU và UNIQUE, dùng **hai EntityManagers riêng** và điều phối thứ tự:

```text
T1 BEGIN                         T2 BEGIN

T1 SELECT COUNT(K) -> 0          T2 SELECT COUNT(K) -> 0

T1 INSERT K
T1 COMMIT

                                 T2 INSERT K
                                 UNIQUE violation
                                 ROLLBACK

VERIFY trong EM mới:
  COUNT(K) = 1
```

### 16.1. Mã JUnit 5 minh họa

```java
@Test
void twoPrechecksPassButOnlyOneInsertCanCommit() {
    Long tenantId = 100L;

    String email =
        "race-" + UUID.randomUUID() + "@example.test";

    String canonical =
        email.toLowerCase(Locale.ROOT);

    EntityManager em1 = emf.createEntityManager();
    EntityManager em2 = emf.createEntityManager();

    try {
        em1.getTransaction().begin();
        em2.getTransaction().begin();

        // Cả hai SELECT trước khi bên nào ghi.
        assertFalse(
            accountExists(em1, tenantId, canonical)
        );

        assertFalse(
            accountExists(em2, tenantId, canonical)
        );

        em1.persist(
            new UserAccount(tenantId, email)
        );
        em1.getTransaction().commit();

        RuntimeException conflict = assertThrows(
            RuntimeException.class,
            () -> {
                em2.persist(
                    new UserAccount(tenantId, email)
                );
                em2.flush();
                em2.getTransaction().commit();
            }
        );

        assertTrue(
            isPostgresUniqueViolation(conflict)
        );

    } finally {
        rollbackIfActive(em2);
        rollbackIfActive(em1);
        em2.close();
        em1.close();
    }

    // Dùng context mới để đọc state đã commit.
    EntityManager verify = emf.createEntityManager();

    try {
        Long count = verify.createQuery(
            """
            SELECT COUNT(a)
            FROM UserAccount a
            WHERE a.tenantId = :tenant
              AND a.normalizedEmail = :email
            """,
            Long.class
        )
        .setParameter("tenant", tenantId)
        .setParameter("email", canonical)
        .getSingleResult();

        assertEquals(1L, count);

    } finally {
        verify.close();
    }
}
```

### 16.2. Điều kiện chạy test

- JPA provider và PostgreSQL test DB với `UNIQUE (tenant_id, normalized_email)` thực tế.
- Isolation phù hợp, ví dụ READ COMMITTED.
- Hai transactions độc lập, không bị một outer `@Transactional` test bao lại.
- Dữ liệu fixture có email riêng, thường dùng UUID.
- Classifier đọc đúng SQLSTATE từ exception chain.
- Không có test khác đang dùng chung unique key.

### 16.3. Vì sao không nhất thiết cần hai Java threads?

Hai transactions có thể được điều phối xen kẽ **trên một test thread** mà vẫn chứng minh race check-then-act: cả hai SELECT trước, transaction thứ nhất commit, transaction thứ hai ghi theo kết quả cũ.

Test multi-thread riêng hữu ích khi cần kiểm tra connection pool, row locking, retry HTTP và scheduling. Không dùng `Thread.sleep()` để đoán thời điểm commit.

### 16.4. Vì sao verify bằng EntityManager mới?

Object trong em2 có thể vẫn giữ dữ liệu Java chưa được commit sau rollback. Chỉ context mới mới cho bằng chứng rõ rằng database cuối cùng có một row chứ không phải hai.

---

## 17. Test đối chứng: uniqueness đúng phạm vi

### 17.1. Trùng email ở hai tenants phải được phép

```java
@Test
void sameEmailCanExistInDifferentTenants() {
    String email =
        "shared-" + UUID.randomUUID() + "@example.test";

    Long id1 = insertCommitted(emf, 100L, email);
    Long id2 = insertCommitted(emf, 200L, email);

    assertNotEquals(id1, id2);
}
```

Nếu test này fail, có thể bạn đã tạo UNIQUE quá rộng trên `normalized_email` toàn cục.

### 17.2. Case-insensitive policy phải được kiểm tra

```text
Tenant 100:
  INSERT Alice@Example.com
  INSERT alice@example.com

Nếu policy không phân biệt hoa/thường:
  lần thứ hai phải bị UNIQUE từ chối.
```

Không chỉ assert cùng giá trị `String.equalsIgnoreCase` ở Java; phải kiểm chứng canonical value và database index hoạt động theo cùng policy.

### 17.3. UPDATE cũng phải bị ràng buộc

```text
Account A: alice@example.com
Account B: bob@example.com

B.changeEmail("alice@example.com")
flush/commit -> UNIQUE violation
```

Nếu chỉ test create endpoint mà quên update, một đường ghi có thể làm hệ thống sai invariant.

---

## 18. @Version không thay UNIQUE

`@Version` phát hiện **stale write trên cùng entity row**:

```text
T1 read UserAccount#101 version=3
T2 read UserAccount#101 version=3
T1 update/commit -> version=4
T2 update old version=3 -> optimistic conflict
```

UNIQUE giải quyết trường hợp:

```text
T1 INSERT UserAccount#201 with email=alice
T2 INSERT UserAccount#202 with email=alice
```

Hai IDs khác nhau nên `@Version` không tự biết rằng hai rows vi phạm cùng business key.

| Vấn đề | Cơ chế phù hợp |
| --- | --- |
| Hai transactions sửa cùng row | `@Version` hoặc concurrency strategy khác |
| Hai INSERT khác row, cùng email | UNIQUE |
| Hai UPDATE khác rows, cùng SKU mới | UNIQUE |
| Retry cùng request | Idempotency key |
| Không cho khoảng booking chồng nhau | Cần exclusion/locking strategy khác tùy DB |
| Số dư kho không âm khi cạnh tranh | Atomic SQL/version/locking và invariant phù hợp |

---

## 19. NULL và UNIQUE: hành vi không luôn trực quan

Ở nhiều DB, UNIQUE cho phép nhiều rows có `NULL` trong một unique column (ví dụ PostgreSQL mặc định). Một số engines có quy tắc khác.

```sql
CREATE TABLE contacts (
    id BIGINT PRIMARY KEY,
    phone VARCHAR(40) UNIQUE
);
```

Không được mặc định bảng này cấm hai hàng `phone=NULL`.

### 19.1. Trường bắt buộc cần NOT NULL

```sql
normalized_email VARCHAR(320) NOT NULL
```

cùng:

```sql
UNIQUE (tenant_id, normalized_email)
```

Và với JPA:

```java
@Column(nullable = false)
private String normalizedEmail;
```

Metadata Java không thay ràng buộc NOT NULL đã được triển khai thực tế trong DB.

### 19.2. Composite unique và NULL

Nếu một thành phần của key ghép nullable, các rows có NULL trong phần đó có thể được xem là không trùng theo semantics của DB.

### 19.3. Nếu muốn NULL cũng “trùng”

Phải dùng DB-specific feature hoặc thay đổi data model. PostgreSQL có lựa chọn `NULLS NOT DISTINCT` trong các phiên bản hỗ trợ; không suy luận mọi DB có cùng cú pháp.

### 19.4. Chuỗi rỗng khác NULL

`""` thường là giá trị chuỗi thực, không giống NULL. Bean Validation và domain validation phải làm rõ dữ liệu rỗng, không phó mặc cho UNIQUE.

---

## 20. Case, collation và canonicalization

Một unique constraint trên email thô không nói rõ:

```text
Alice@Example.com
alice@example.com
```

có được xem như một hay hai giá trị. Hành vi phụ thuộc database collation/type.

### 20.1. Cách 1: normalized column

```text
email            = Alice@Example.com
normalized_email = alice@example.com
```

Đặt UNIQUE lên normalized value hoặc composite chứa nó.

### 20.2. Cách 2: functional unique index

Ví dụ PostgreSQL:

```sql
CREATE UNIQUE INDEX ux_accounts_tenant_lower_email
ON user_accounts (tenant_id, lower(email));
```

Đây là **database-specific expression index**, không được `@UniqueConstraint(columnNames=...)` biểu diễn portable trong mọi JPA provider.

### 20.3. Cách 3: case-insensitive type/collation

Một số DB hỗ trợ kiểu/collation không phân biệt hoa/thường, ví dụ PostgreSQL `citext`. Cần kiểm tra Unicode/case-folding, migration và truy vấn dùng cùng semantics.

### 20.4. Pre-check phải khớp unique rule

Nếu pre-check lowercase nhưng DB unique trên email gốc với collation phân biệt case, các đường ghi bypass normalized field có thể tạo duplicates nghiệp vụ.

Xác định một **equivalence relation** rõ ràng và áp cho tất cả writers.

---

## 21. Soft delete và partial UNIQUE

Giả sử account có:

```java
private Instant deletedAt;
```

và business cho phép dùng lại email sau khi account bị soft-delete.

UNIQUE toàn cục:

```sql
UNIQUE (tenant_id, normalized_email)
```

vẫn khiến deleted row chiếm email.

Trong PostgreSQL có thể dùng:

```sql
CREATE UNIQUE INDEX ux_accounts_active_email
ON user_accounts (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
```

Đây là **partial unique index**, không phải `@Table(uniqueConstraints=...)` portable.

### 21.1. Không để cả global UNIQUE nếu muốn reuse

Nếu constraint cũ vẫn tồn tại, active partial index không giúp reuse email. Migration phải xử lý constraint cũ theo policy.

### 21.2. Restore cũng có thể conflict

```sql
UPDATE user_accounts
SET deleted_at = NULL
WHERE id = ?;
```

Nếu email đã được active user khác dùng, restore phải bị từ chối theo partial UNIQUE.

### 21.3. Pre-check cần cùng predicate

```jpql
WHERE a.tenantId = :tenant
  AND a.normalizedEmail = :email
  AND a.deletedAt IS NULL
```

Ngay cả khi predicate chính xác, pre-check vẫn có race; database partial index bảo vệ invariant cuối.

---

## 22. Upsert và idempotency không đồng nghĩa pre-check

PostgreSQL có cơ chế atomic conflict handling:

```sql
INSERT INTO user_accounts (
    tenant_id, email, normalized_email, version
)
VALUES (?, ?, ?, 0)
ON CONFLICT (tenant_id, normalized_email)
DO NOTHING;
```

Đây là xử lý conflict tại database, không phải SELECT rồi INSERT.

### 22.1. DO NOTHING không luôn đúng với create-only API

Một create endpoint thường phải trả “đã tồn tại” thay vì im lặng không tạo gì. Cần kiểm tra affected-row count hoặc kết quả `RETURNING` phù hợp để phân biệt created và conflict.

### 22.2. DO UPDATE có thể ghi đè account hiện tại

`ON CONFLICT ... DO UPDATE` chỉ dùng khi nghiệp vụ thực sự là upsert. Không dùng một câu lệnh upsert để che việc trùng business key nếu hợp đồng chỉ cho phép tạo mới.

### 22.3. Native upsert có lifecycle khác managed entity update

Native/bulk SQL có thể bỏ qua các JPA callbacks/dirty checking và làm persistence context đang mở giữ state cũ. Cần test cache/version/transaction riêng.

### 22.4. Idempotency key là invariant khác

```sql
UNIQUE (tenant_id, idempotency_key)
```

có thể dùng để nhận diện retry cùng request. Email unique lại biểu diễn business key. Hai requests cùng email **không nhất thiết** là retry cùng ý định.

---

## 23. Migration: thêm UNIQUE khi đã có dữ liệu

Một database đang chạy có thể đã có duplicates. Trước khi thêm constraint:

```sql
SELECT
    tenant_id,
    normalized_email,
    COUNT(*) AS occurrences
FROM user_accounts
GROUP BY tenant_id, normalized_email
HAVING COUNT(*) > 1;
```

Nếu có duplicates, tạo UNIQUE có thể thất bại.

### 23.1. Quy trình migration

1. Chốt canonicalization và scope uniqueness.
2. Backfill normalized field một cách kiểm soát.
3. Đếm và phân loại duplicates.
4. Giải quyết duplicates theo business ownership; không tự xóa dữ liệu liên quan.
5. Rà soát foreign keys, audit logs và lịch sử.
6. Kiểm soát concurrent writes trong giai đoạn chuyển đổi.
7. Triển khai UNIQUE và NOT NULL phù hợp.
8. Kiểm tra metadata và test duplicate thực tế.
9. Theo dõi violation rates sau rollout.

### 23.2. Index trên bảng lớn

PostgreSQL có khả năng:

```sql
CREATE UNIQUE INDEX CONCURRENTLY
    ux_accounts_tenant_email
ON user_accounts (tenant_id, normalized_email);
```

`CREATE INDEX CONCURRENTLY` không chạy trong một transaction block thông thường. Migration tool có thể cần cấu hình non-transactional cho bước này.

Đây là ví dụ về phương án online, **không phải lệnh chạy trực tiếp trên production khi chưa có kế hoạch**.

### 23.3. Cửa sổ race trong migration

Nếu writers vẫn ghi tự do khi đang backfill/index build, duplicates mới có thể xuất hiện. Pre-check không đủ để bảo vệ giai đoạn chuyển đổi; cần chiến lược rollout/write coordination.

---

## 24. Xác minh constraint/index trên PostgreSQL

Unique constraints:

```sql
SELECT
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'user_accounts'::regclass
  AND contype = 'u';
```

Indexes, bao gồm partial/expression:

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename = 'user_accounts';
```

Partial unique index có thể không xuất hiện như table-level `UNIQUE` trong `pg_constraint`, nên cần kiểm tra đúng loại metadata.

### 24.1. Metadata chưa đủ chứng minh business rule

Một unique index có thể tồn tại nhưng sai cột, sai case policy, sai predicate soft-delete hoặc NULL semantics. Vì vậy cần test:

- Key trùng bị từ chối.
- Key hợp lệ khác tenant được phép.
- UPDATE/restore gây trùng bị từ chối.
- Các biến thể case/canonicalization được xử lý đúng.
- Hai giao dịch cạnh tranh không để lại duplicate.

---

## 25. Khi nào pre-check có lợi và khi nào có thể bỏ?

Pre-check phù hợp nếu cần:

- Hiển thị trạng thái khả dụng cho người dùng trước submit.
- Phản hồi dễ hiểu khi duplicate đã tồn tại.
- Kiểm tra nhiều điều kiện nghiệp vụ trước ghi.
- Giảm một số lỗi constraint thường gặp trong happy path.

Có thể bỏ server pre-check ở một số create paths nếu:

- Duplicate hiếm.
- Một round trip SELECT thêm làm tăng latency đáng kể.
- Constraint/index đã được triển khai đúng.
- Error classifier và API contract đã rõ.
- Client xử lý `409 Conflict` đúng.

**Có hay không có pre-check, database UNIQUE vẫn phải tồn tại.**

### 25.1. Batch import và chi phí SELECT

Với 10.000 accounts, cách “SELECT rồi INSERT từng account” có thể tạo hàng chục nghìn round trips. Có thể cân nhắc staging table, chunking, batch inserts hoặc atomic database conflict handling.

Tuy nhiên, khi một batch gặp duplicate, cần định nghĩa rõ rollback toàn batch, bỏ item, report lỗi từng row hay retry theo chính sách. Không bỏ UNIQUE để đạt throughput.

---

## 26. Monitoring và bảo mật

Những chỉ số có thể theo dõi:

```text
account_create_attempts_total
account_create_success_total
account_create_precheck_conflict_total
account_create_unique_violation_total
account_create_other_failure_total
```

Đây là tên metrics minh họa, không phải built-in JPA metrics.

Một số unique violations là business conflicts bình thường. Nếu số lượng tăng mạnh, có thể do:

- Client retry không idempotent.
- Lỗi canonicalization.
- Bug trong sinh mã đơn hàng.
- Batch import duplicate.
- Thay đổi traffic.
- Dữ liệu tenant bị trộn.

### 26.1. SQL logs chỉ dùng đúng phạm vi

Hibernate 6 trong dev/test:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind logs có thể chứa email, IDs và dữ liệu cá nhân. Không bật TRACE toàn production nếu chưa có redaction/access/retention policy phù hợp.

### 26.2. Không đưa raw SQL exception ra API

Response chỉ nên chứa business error code/message có kiểm soát. Log nội bộ với constraint name, correlation ID và thông tin cần thiết, hạn chế ghi trực tiếp dữ liệu nhạy cảm.

---

## 27. Những ngộ nhận thường gặp

**“Đã gọi existsBy... thì không thể trùng.”** Sai: TOCTOU race.

**“Thêm @Column(unique=true) là đủ.”** Sai nếu constraint chưa được triển khai trong database thật.

**“Đưa SELECT và INSERT vào cùng @Transactional là đủ.”** Không đủ trong nhiều isolation modes.

**“@Version sẽ chống hai INSERT trùng email.”** Không: hai entity rows có IDs khác nhau.

**“save trả ID nghĩa là đã commit.”** Không: ID có thể được sinh trước commit.

**“saveAndFlush nghĩa là commit.”** Không: flush có thể rollback.

**“ConstraintViolationException luôn là Bean Validation.”** Không: cần phân biệt package.

**“DataIntegrityViolationException luôn là duplicate email.”** Không: có thể là FK/CHECK/NOT NULL.

**“UNIQUE(email) luôn case-insensitive.”** Không: phụ thuộc DB collation/type.

**“UNIQUE luôn cấm nhiều NULL.”** Không: NULL semantics khác giữa engines.

**“Soft delete tự giải phóng unique key.”** Không nếu constraint vẫn áp lên deleted rows.

**“SELECT FOR UPDATE chắc chắn khóa key chưa tồn tại.”** Không portable.

**“Upsert luôn thay được create-only API.”** Không: DO NOTHING và DO UPDATE có semantics riêng.

**“Mock repository chứng minh DB UNIQUE.”** Không: cần integration test với DB thật.

---

## 28. Bảng tình huống lỗi

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Trùng email dù có pre-check | Race giữa SELECT và INSERT | UNIQUE thật |
| Có annotation nhưng DB nhận duplicate | Migration thiếu | Xác minh schema |
| Hai tenants không dùng chung email | Unique toàn cục quá chặt | Composite unique |
| Chữ hoa/thường không bị chặn | Canonical/DB collation khác nhau | Thống nhất equality policy |
| Migration UNIQUE thất bại | Dữ liệu cũ trùng | Dọn dữ liệu có kế hoạch |
| Lỗi ở commit chứ không ở save | Flush/check trễ | Xử lý ở tx boundary |
| Duplicate trả 500 | Thiếu error translation | 409/domain conflict |
| FK lỗi bị báo email trùng | Catch integrity exception quá rộng | Phân loại constraint |
| SQL error rồi query tiếp bị lỗi | Transaction aborted | Rollback trước |
| saveAndFlush OK rồi rollback | Flush không commit | Chờ tx outcome |
| @Version có mà vẫn trùng | Hai rows khác identity | UNIQUE |
| Soft-delete không reuse được email | Constraint toàn cục | Partial unique/migration |
| Restore gây conflict | Active account đã chiếm key | Validate restore |
| H2 pass nhưng PostgreSQL khác | SQLSTATE/NULL/isolation khác | Test DB đích |
| UI báo available rồi API 409 | TOCTOU bình thường | Xử lý 409 ở submit |
| Upsert ghi đè account khác | DO UPDATE sai nghiệp vụ | Điều chỉnh DML/contract |
| Lộ SQL/email trong response | In raw exception | Redact/error DTO |

---

## 29. Bài tập tình huống và lời giải

### Bài 1. Hai giao dịch cùng thấy “chưa tồn tại”

T1 và T2 cùng nhận `exists=false`, sau đó cùng tạo email.

**Đáp án:** Pre-check không bảo vệ khoảng thời gian sau SELECT; database UNIQUE cần từ chối một giao dịch.

### Bài 2. Entity có @UniqueConstraint nhưng production vẫn trùng

**Đáp án:** Có thể constraint chưa được migration triển khai. Xác minh DDL và test INSERT duplicate thật.

### Bài 3. Email unique theo tenant

**Đáp án:** Dùng `UNIQUE(tenant_id, normalized_email)`.

### Bài 4. @Version có thay UNIQUE không?

**Đáp án:** Không. `@Version` bảo vệ stale updates cùng row; UNIQUE bảo vệ business key giữa nhiều rows.

### Bài 5. Violation tại persist

**Đáp án:** IDENTITY có thể INSERT sớm. Test và handler cần bao cả persist/flush/commit.

### Bài 6. Violation tại commit

**Đáp án:** Có thể do delayed flush/deferred constraint. Xử lý ở transaction boundary.

### Bài 7. SQLSTATE 23505

**Đáp án:** PostgreSQL unique violation; cần constraint name nếu bảng có nhiều keys UNIQUE.

### Bài 8. DataIntegrityViolationException do foreign key

**Đáp án:** Không được trả “email trùng”; dùng taxonomy riêng.

### Bài 9. Khác hoa/thường

**Đáp án:** Xác định canonicalization hoặc case-insensitive index/collation và test trên DB thật.

### Bài 10. Hai NULL ở cột unique

**Đáp án:** Nhiều DB chấp nhận nhiều NULL; dùng NOT NULL hoặc DB-specific semantics nếu nghiệp vụ khác.

### Bài 11. Soft-delete và reuse

**Đáp án:** Partial unique index trên active records nếu DB hỗ trợ; bỏ global unique cũ khi chuyển policy.

### Bài 12. Restore account

**Đáp án:** Restore là UPDATE có thể vi phạm active uniqueness.

### Bài 13. SELECT FOR UPDATE trả zero rows

**Đáp án:** Không thể mặc định khóa một row không tồn tại; UNIQUE bảo vệ invariant.

### Bài 14. Query tiếp trong PostgreSQL transaction lỗi

**Đáp án:** Rollback trước; mở context/transaction mới.

### Bài 15. Mock existsBy=true

**Đáp án:** Chỉ test service branch, không chứng minh database constraint.

### Bài 16. H2 pass, DB production fail

**Đáp án:** Test thêm bằng database/driver/isolation mục tiêu.

### Bài 17. DO NOTHING trong create-only API

**Đáp án:** Có thể che duplicate; cần kiểm tra affected rows và response contract.

### Bài 18. Retry request

**Đáp án:** Nếu yêu cầu idempotency, dùng một idempotency key riêng, không mặc định mọi duplicate email là cùng request.

### Bài 19. Test UNIQUE chỉ kiểm tra annotation

**Đáp án:** Chưa đủ: cần DDL, duplicate-write test và allowed cases.

### Bài 20. UPDATE account B thành email account A

**Đáp án:** UNIQUE cũng chặn UPDATE trùng. Transaction thất bại phải rollback và trả conflict phù hợp.

### Bài 21. Batch tạo 10.000 users

**Đáp án:** Có thể giảm pre-check SELECT nếu DB constraint và batch failure policy được thiết kế rõ; không bỏ UNIQUE.

### Bài 22. UI báo available=true nhưng submit nhận 409

**Đáp án:** Đó là race bình thường; UI cần cập nhật trạng thái và hướng dẫn chọn key khác.

---

## 30. Checklist triển khai uniqueness

1. Business key được định nghĩa rõ chưa?
2. Unique toàn cục hay theo tenant?
3. Khóa một cột hay nhiều cột?
4. Có canonicalization/case policy rõ chưa?
5. `NULL`/empty string có semantics nào?
6. Soft delete/restore ảnh hưởng uniqueness ra sao?
7. INSERT và UPDATE đều được ràng buộc chưa?
8. Annotation có khớp tên cột DB không?
9. Migration tạo constraint/index thật chưa?
10. Dữ liệu cũ có duplicates cần dọn không?
11. Có race trong giai đoạn rollout không?
12. Pre-check có cùng predicate/canonical key với DB không?
13. Pre-check được hiểu là advisory/UX không?
14. Có xử lý race sau pre-check không?
15. Exception được bắt ở persist/flush/commit boundary không?
16. Transaction lỗi có rollback/cleanup không?
17. Có phân biệt Bean Validation và SQL constraint error không?
18. Có phân biệt UNIQUE/FK/CHECK/NOT NULL không?
19. Constraint name/SQLSTATE classifier có test chưa?
20. Có tránh parse message text thô không?
21. API trả error code/status đúng không?
22. Có tránh lộ raw SQL và dữ liệu cá nhân không?
23. Có test duplicate không cần pre-check không?
24. Có test hai transactions cùng pass pre-check không?
25. Có test same email/different tenants không?
26. Có test case normalization không?
27. Có test UPDATE/soft-delete/restore không?
28. Có verify số rows cuối từ context mới không?
29. Có test trên DB/isolation giống production không?
30. Bulk/native writers có tuân thủ canonical policy không?
31. Có cần idempotency riêng cho retry không?
32. Có quan sát chi phí query và violation metrics không?

---

## 31. Tổng kết

Pre-check và UNIQUE thực tế nằm ở hai ranh giới khác nhau:

```text
                 HTTP request
                      |
                      v
               Validate input
                      |
                      v
         Optional application pre-check
             /                \
           found             not found
             |                  |
             v                  v
       Early conflict       INSERT / UPDATE
                                |
                                v
                        Database UNIQUE check
                                |
                        +-------+-------+
                        |               |
                        v               v
                     Success        Violation
                        |               |
                        v               v
                     COMMIT          ROLLBACK
                        |               |
                        v               v
                  Created / OK     Business conflict
                                   (ví dụ HTTP 409)
```

Các điểm phải ghi nhớ:

- **`existsBy...` chỉ phản ánh trạng thái tại thời điểm đọc**, không giữ chỗ khóa nghiệp vụ.
- **Database UNIQUE là nguồn bảo vệ cuối cùng** cho mọi writers trên cùng dữ liệu.
- **JPA annotations là metadata**; không thay cho database migration và việc kiểm tra schema thực tế.
- **Phạm vi key, canonicalization, collation, NULL và soft delete** quyết định điều gì được coi là trùng.
- **`flush` không phải `commit`**; lỗi UNIQUE có thể xuất hiện ở `persist`, `flush` hoặc `commit`.
- **Rollback trước khi tiếp tục** sau constraint violation và không dùng lại context đã lỗi như transaction hợp lệ.
- **Không gọi mọi DataIntegrityViolationException là duplicate email**; phải phân loại đúng constraint.
- **`@Version` không thay UNIQUE** khi hai entity rows khác nhau trùng business key.
- **Integration test với hai transactions độc lập** phải chứng minh hai pre-check cùng pass nhưng database vẫn chỉ cho một row commit.
- **Upsert và idempotency** có mục tiêu riêng, không tự đồng nghĩa với create-only operation.

**Kiểm tra duy nhất trước ghi là tín hiệu hỗ trợ người dùng; ràng buộc UNIQUE thực tế trong database mới bảo đảm tính duy nhất của dữ liệu khi nhiều giao dịch cạnh tranh.**
