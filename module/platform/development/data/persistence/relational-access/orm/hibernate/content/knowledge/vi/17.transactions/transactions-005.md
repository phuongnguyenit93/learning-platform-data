# Phân biệt mức cô lập của cơ sở dữ liệu với cơ chế quản lý trạng thái của ORM

## 1. Hai cơ chế cùng ảnh hưởng đến dữ liệu nhưng giải quyết hai bài toán khác nhau

Khi một ứng dụng Java sử dụng **Jakarta Persistence (JPA)** với **Hibernate ORM**, việc đọc và ghi entity chịu tác động đồng thời của ít nhất hai lớp:

- **Cơ sở dữ liệu quan hệ** thực hiện transaction, isolation, khóa (lock), kiểm tra constraint và quyết định một transaction thấy những thay đổi đã hoặc chưa được commit của transaction khác ở mức nào.
- **ORM và persistence context** theo dõi các Java entity instances, giữ identity map/first-level cache, phát hiện thay đổi (dirty checking), quản lý thao tác đang chờ và đồng bộ SQL (flush).

Hai lớp này phối hợp với nhau, nhưng **không phải một cơ chế**. Đặc biệt:

> **Transaction isolation không phải “chế độ cache” của Hibernate; còn persistence context không tự biến transaction ở mức READ COMMITTED thành REPEATABLE READ hay SERIALIZABLE.**

Một tình huống thường gặp:

1. Transaction A đọc một sản phẩm giá 100 và giữ entity `Product` trong persistence context.
2. Transaction B sửa giá sản phẩm thành 120 và commit.
3. Transaction A đọc lại sản phẩm bằng `EntityManager.find()`.
4. Kết quả ở bước 3 vẫn có thể là giá 100, **ngay cả khi DB dùng READ COMMITTED**, vì Hibernate trả instance đã managed trong first-level cache mà không phát SQL SELECT mới.

Ngược lại, nếu A bỏ entity khỏi context rồi SELECT lại, kết quả còn phụ thuộc **isolation level, snapshot của transaction, lock, thời điểm SELECT và database cụ thể**. Đổi `em.clear()` không có nghĩa DB phải cho thấy giá mới trong một transaction có snapshot ổn định.

Bài học sẽ làm rõ các câu hỏi:

- Mức cô lập của DB kiểm soát những hiện tượng gì: dirty read, non-repeatable read, phantom, write skew?
- Persistence context giữ managed entities thế nào và tại sao truy vấn lại có thể nhận đối tượng cũ?
- `flush()`, `clear()`, `refresh()`, `detach()` và `commit()` ảnh hưởng tới các tầng nào?
- `@Version`/optimistic locking khác transaction isolation ra sao?
- Khi nào cần isolation cao, lock tường minh, constraint, hay đơn giản chỉ cần context mới?
- Làm thế nào kiểm thử các tình huống hai transaction cạnh tranh mà không nhầm cache của ORM với snapshot của DB?

**Ngữ cảnh phiên bản:** ví dụ dùng Jakarta Persistence (`jakarta.persistence.*`), Hibernate ORM hiện đại và, khi đề cập `@Transactional`, Spring. Các đặc tính isolation thực tế phụ thuộc **hệ quản trị cơ sở dữ liệu, phiên bản, cấu hình và JDBC driver**; không nên coi tất cả database đều triển khai bốn mức ISO/ANSI giống hệt nhau.

## 2. Mô hình ba lớp cần đặt cạnh nhau

Có thể hình dung một request như sau:

~~~text
Application / Business Service
              |
              v
    EntityManager / Hibernate Session
    +----------------------------------+
    | Persistence Context              |
    | - Managed entity identity map    |
    | - Snapshots / dirty checking     |
    | - Pending inserts, updates       |
    | - Lazy association state         |
    +----------------------------------+
              |
              | SQL SELECT/INSERT/UPDATE/DELETE
              | khi cần query hoặc flush
              v
        JDBC Connection
    +----------------------------------+
    | Database Transaction             |
    | - Isolation level                |
    | - MVCC snapshot / row locks      |
    | - Commit / rollback              |
    | - Unique, FK, CHECK constraints  |
    +----------------------------------+
              |
              v
      Relational tables / rows
~~~

### 2.1. Persistence context là gì?

Một persistence context quản lý một tập entity instances. Với cùng entity identity, một context duy trì một managed instance tương ứng. Từ đây ORM hỗ trợ:

- Tính nhất quán danh tính: `find(Product.class, 7L)` nhiều lần trong cùng context thường trả **cùng Java object**.
- Dirty checking: nếu một managed entity thay đổi, Hibernate có thể nhận biết rồi phát SQL khi flush.
- Tracking các thao tác tạo, sửa, xóa của những entity đã được quản lý.
- Giải quyết lazy associations trong phạm vi session/context phù hợp.

Đó thường được gọi là **first-level cache** của Hibernate, nhưng nó còn chứa cơ chế quản lý trạng thái, không chỉ là một bộ nhớ đệm SELECT.

### 2.2. Transaction của database là gì?

Một database transaction là đơn vị commit/rollback có các quy tắc ACID và isolation cụ thể. Nó chi phối:

- Khi những thay đổi do transaction khác thực hiện được phép xuất hiện trong truy vấn.
- Các lock và xung đột truy cập giữa transaction.
- Hành vi của snapshot hoặc version dữ liệu theo cơ chế MVCC của DB.
- Phát hiện serialization failure, deadlock hoặc ràng buộc uniqueness khi ghi.

ORM gửi SQL xuống JDBC connection. **Nếu không có SQL mới được gửi**, database isolation không có cơ hội quyết định kết quả của phép đọc đó: entity có thể được trả trực tiếp từ context.

### 2.3. Transaction và persistence context có phải luôn bắt đầu/kết thúc cùng lúc?

Không.

Trong nhiều ứng dụng Spring/Jakarta EE, persistence context thường có scope theo transaction. Nhưng application-managed `EntityManager` có thể được giữ mở qua nhiều transaction, và Jakarta Persistence có cơ chế **extended persistence context** trong các môi trường hỗ trợ.

Vì vậy:

- Context có thể tồn tại lâu hơn một transaction.
- Một transaction có thể kết thúc mà một Java reference vẫn còn; reference đó có thể là detached khi context của transaction đã kết thúc.
- Trong một context kéo dài, entity đã managed có thể giữ dữ liệu cũ qua nhiều transaction.
- Không nên dùng một EntityManager chia sẻ giữa nhiều thread/request; EntityManager/Session không thread-safe.

Để dự đoán kết quả, luôn hỏi **context còn giữ entity nào** và **database transaction hiện tại đang ở isolation nào**, chứ không chỉ hỏi một trong hai.

## 3. Ví dụ chung: tài khoản và chuyển khoản

Để minh họa vấn đề concurrency, dùng `Account` với số dư và version:

~~~java
package example.banking;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "owner_name", nullable = false, length = 120)
    private String ownerName;

    @Column(name = "balance", nullable = false, precision = 18, scale = 2)
    private BigDecimal balance;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    protected Account() {}

    public Account(String ownerName, BigDecimal balance) {
        this.ownerName = ownerName;
        this.balance = balance;
    }

    public Long getId() { return id; }
    public String getOwnerName() { return ownerName; }
    public BigDecimal getBalance() { return balance; }
    public long getVersion() { return version; }

    public void deposit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance = balance.add(amount);
    }

    public void withdraw(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (balance.compareTo(amount) < 0) {
            throw new IllegalStateException("insufficient funds");
        }
        balance = balance.subtract(amount);
    }
}
~~~

Ví dụ schema khái niệm:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance DECIMAL(18, 2) NOT NULL,
    row_version BIGINT NOT NULL,
    CONSTRAINT ck_accounts_non_negative CHECK (balance >= 0)
);
~~~

Đây là ví dụ dạy về isolation và ORM; **không phải thiết kế đầy đủ cho hệ thống ngân hàng production**. Các nghiệp vụ chuyển tiền còn cần ledger/audit, idempotency, định danh giao dịch, quyền truy cập, quản lý lỗi, chống double spending và nhiều yêu cầu khác.

Với `@Version`, Hibernate thường đưa version cũ vào điều kiện `UPDATE` và tăng version khi một entity update được ghi đúng. Điều này cho phép phát hiện một số xung đột giữa các transaction, nhưng không thay thế isolation/constraint ở DB.

## 4. Mức cô lập của DB: câu hỏi về visibility và interleaving

Chuẩn SQL/JDBC thường nhắc tới bốn mức:

1. `READ UNCOMMITTED`
2. `READ COMMITTED`
3. `REPEATABLE READ`
4. `SERIALIZABLE`

Đây là cách đặt tên hữu ích để thảo luận, **không phải cam kết mọi DB có cùng triển khai và mọi anomaly được phép/không được phép y hệt nhau**. Hệ quản trị sử dụng lock hoặc MVCC theo cách khác nhau; ví dụ PostgreSQL và MySQL/InnoDB khác nhau ở nhiều chi tiết.

### 4.1. Dirty read — đọc dữ liệu chưa commit

~~~text
Transaction A                         Transaction B
-------------                         -------------
UPDATE accounts
SET balance = 900
WHERE id = 1;
-- CHƯA COMMIT
                                      SELECT balance
                                      FROM accounts WHERE id = 1;
A ROLLBACK;
~~~

Nếu B thấy 900 dù A chưa commit, đó là **dirty read**: B thấy dữ liệu có thể bị rollback sau đó.

`READ UNCOMMITTED` cho phép hiện tượng dirty read theo mô hình tiêu chuẩn. Tuy nhiên, nhiều DB hiện đại không thực sự cho dirty read dù người dùng yêu cầu mức này. Ví dụ PostgreSQL xử lý `READ UNCOMMITTED` theo cơ chế tương đương `READ COMMITTED`.

### 4.2. Non-repeatable read — cùng hàng, hai lần đọc, hai kết quả

~~~text
Transaction A                         Transaction B
-------------                         -------------
SELECT balance
FROM accounts WHERE id = 1;
-- nhận 1000

                                      UPDATE accounts
                                      SET balance = 1200
                                      WHERE id = 1;
                                      COMMIT;

SELECT balance
FROM accounts WHERE id = 1;
-- có thể nhận 1200
~~~

Ở mức `READ COMMITTED`, hai câu SELECT riêng có thể thấy snapshot dữ liệu đã commit ở các thời điểm khác nhau (phụ thuộc DB). Đây là **non-repeatable read**.

**Lưu ý rất quan trọng:** sơ đồ trên nói về **hai SQL SELECT thực sự gửi tới database**. Nếu A dùng `em.find(Account.class, 1L)` lần thứ hai và context đã giữ managed entity, Hibernate có thể trả object cũ mà **không thực thi SELECT thứ hai**. Như vậy không được lấy kết quả từ `find()` để khẳng định DB không cho phép non-repeatable read.

### 4.3. Phantom read — cùng điều kiện, tập hàng đổi

~~~text
Transaction A                         Transaction B
-------------                         -------------
SELECT COUNT(*)
FROM accounts WHERE balance >= 1000;
-- nhận 5

                                      INSERT INTO accounts (...)
                                      -- hàng mới balance = 2000
                                      COMMIT;

SELECT COUNT(*)
FROM accounts WHERE balance >= 1000;
-- có thể nhận 6
~~~

Ở đây cùng một predicate nhưng số hàng khác nhau vì một transaction khác thêm hàng phù hợp; đó là **phantom**.

Không nên nhầm phantom với non-repeatable read: phantom liên quan tập kết quả của predicate, còn non-repeatable read thường mô tả giá trị của cùng một hàng đổi giữa hai lần đọc.

DB có MVCC hoặc predicate/range locking theo cách khác nhau, nên khả năng xảy ra phantom ở `REPEATABLE READ` phụ thuộc implementation.

### 4.4. Write skew — mỗi transaction cập nhật hàng khác nhau nhưng phá bất biến chung

Giả sử một nhóm trực cần **ít nhất một bác sĩ trực**. Hai bác sĩ A và B đều đang trực; hai transaction cùng thấy có hai người, rồi mỗi transaction cho một người nghỉ:

~~~text
Transaction 1                         Transaction 2
-------------                         -------------
SELECT count(on_call) = 2;
                                      SELECT count(on_call) = 2;
UPDATE doctors
SET on_call = false
WHERE id = A;
                                      UPDATE doctors
                                      SET on_call = false
                                      WHERE id = B;
COMMIT;                               COMMIT;

Kết quả: không còn ai trực.
~~~

Hai giao dịch viết **hai hàng khác nhau**, nên row-level optimistic lock trên từng entity riêng lẻ không nhất thiết phát hiện vi phạm bất biến liên hàng. Write skew có thể xảy ra dưới một số isolation/snapshot implementations nếu không có bảo vệ khác.

Tùy DB và cách truy vấn/locking, `SERIALIZABLE` có thể ngăn một lịch sử không tương đương lịch sử tuần tự, thường bằng cách chặn hoặc abort một transaction; ứng dụng phải chuẩn bị **retry transaction mới** khi gặp serialization failure.

### 4.5. Lost update — ghi đè thay đổi từ transaction khác

Giả sử hai giao dịch cùng đọc số dư 100. A cộng 20, B cộng 30 bằng cách tự tính giá trị mới:

~~~text
Transaction A                         Transaction B
-------------                         -------------
READ balance = 100
                                      READ balance = 100
SET balance = 120
COMMIT
                                      SET balance = 130
                                      COMMIT
                                      (khả năng mất phần +20)
~~~

Nếu DB/transaction/API cho phép hai thao tác cập nhật với giá trị đã tính từ snapshot cũ và không phát hiện xung đột, kết quả 130 thay vì 150 là **lost update**.

Cách xử lý có thể gồm:

- `@Version` và optimistic locking khi cập nhật qua managed entity.
- Lock hàng bằng `SELECT ... FOR UPDATE`/`PESSIMISTIC_WRITE` trong transaction phù hợp.
- SQL atomic update `SET balance = balance + :delta` khi semantics cho phép.
- Isolation/serialization phù hợp với DB.
- Retry toàn transaction khi phát hiện conflict.

Không nên khẳng định mức `READ COMMITTED` của mọi DB luôn cho lost update, hay `REPEATABLE READ` của mọi DB luôn ngăn: hành vi phụ thuộc giao thức cập nhật, cách DB phát hiện xung đột và version/lock của ứng dụng.

## 5. Bảng phân biệt các mức cô lập theo ý nghĩa thường dùng

| Mức isolation | Dirty read | Non-repeatable read | Phantom read | Ý định tổng quát |
|---|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể | Mức đảm bảo visibility thấp nhất theo mô hình chuẩn |
| `READ COMMITTED` | Không | Có thể | Có thể | Mỗi statement đọc dữ liệu đã commit theo DB semantics |
| `REPEATABLE READ` | Không | Thông thường được ngăn | Phụ thuộc DB/chuẩn và implementation | Ổn định hơn đối với những hàng đã đọc |
| `SERIALIZABLE` | Không | Không, khi giao dịch thành công với ngữ nghĩa serializable | Không theo lịch sử giao dịch serializable | Kết quả tương đương một thứ tự tuần tự của các transaction thành công |

Bảng là **khái quát để nhận biết mục tiêu**, không phải bảng cam kết tối đa về implementation của PostgreSQL, MySQL, Oracle, SQL Server hoặc các engine khác.

Các điểm cần chú ý:

- `REPEATABLE READ` trong PostgreSQL dựa trên snapshot isolation và có khả năng khác với mức cùng tên ở hệ khác. Snapshot nhất quán không đồng nghĩa mọi bất biến liên hàng được bảo vệ; write skew có thể vẫn cần cơ chế bổ sung.
- `READ COMMITTED` trong PostgreSQL thường dùng snapshot ở cấp statement; hai SELECT riêng có thể thấy kết quả khác nhau sau transaction khác commit.
- `SERIALIZABLE` có thể phát hiện xung đột rồi abort/rollback một giao dịch, không đảm bảo mọi giao dịch cạnh tranh sẽ chờ đến khi cả hai cùng thành công.
- `READ UNCOMMITTED` không nhất thiết thực sự tạo dirty reads; PostgreSQL triển khai như `READ COMMITTED`.
- Mức isolation là **một phần** của thiết kế concurrency; unique/FK/CHECK constraints và khóa ứng dụng vẫn có vai trò độc lập.

### 5.1. Cấu hình isolation là cấu hình transaction/JDBC, không phải @Column

Ví dụ với Spring:

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.REPEATABLE_READ)
public void runReport() {
    // Những SQL trong transaction này chịu isolation được
    // transaction manager / datasource / database áp dụng.
}
~~~

`@Transactional(isolation = ...)` không biến một entity thành immutable, không bắt Hibernate tự `refresh`, và không làm thay đổi Java reference đã trả về trước đó.

Trong JDBC thuần, có thể dùng:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Cần import `java.sql.Connection`. Việc thay đổi isolation phải diễn ra **đúng thời điểm/transaction boundary** và tuân theo JDBC driver, pool và DB. Không tự sửa isolation của một connection đang tham gia transaction được framework quản lý, vì có thể phá contract của transaction manager hoặc tạo hành vi ngoài ý định.
## 6. Cơ chế trạng thái của ORM: managed, detached, flush và identity map

Mức isolation giải thích những gì **SQL có quyền quan sát**; trạng thái entity giải thích những gì **Hibernate giữ trong Java và tự đồng bộ**.

### 6.1. Bốn trạng thái vòng đời, nhắc lại trong ngữ cảnh transaction

| Trạng thái | Ý nghĩa với ORM | Quan hệ với database transaction |
|---|---|---|
| `Transient` (new) | Object chưa thuộc persistence context | Chưa tự tạo SQL chỉ vì constructor chạy |
| `Managed` | Context theo dõi persistent state và identity | Có thể được flush trong transaction phù hợp |
| `Detached` | Object không còn thuộc context đó | Sửa setter không tự UPDATE trong transaction khác |
| `Removed` | Context ghi nhận yêu cầu xóa | DELETE có thể chưa được gửi cho đến flush |

Ví dụ:

~~~java
Account a = new Account("An", new BigDecimal("100.00"));
// a: transient

em.getTransaction().begin();

em.persist(a);
// a: managed

a.deposit(new BigDecimal("20.00"));
// Hibernate có thể đưa số dư 120 vào INSERT/UPDATE khi flush.

em.flush();
// SQL được đồng bộ, transaction chưa commit.

em.detach(a);
// a: detached; sửa tiếp không được context này dirty-check.

em.getTransaction().commit();
~~~

Với một entity đã tồn tại:

~~~java
em.getTransaction().begin();

Account a = em.find(Account.class, accountId);
// a là managed trong context nếu tìm thấy.

a.deposit(new BigDecimal("20.00"));
// Thường chưa cần gọi save/update.

em.getTransaction().commit();
// Hibernate flush phù hợp, DB commit nếu thành công.
~~~

Không thể quyết định trạng thái chỉ bằng `id == null`. Entity transient có thể có ID tự gán, còn managed entity chưa insert vẫn có thể được cấp ID từ sequence. Vấn đề là **instance có thuộc persistence context hiện tại không**.

### 6.2. Identity map khác SQL snapshot

~~~java
Account first = em.find(Account.class, accountId);
Account second = em.find(Account.class, accountId);

System.out.println(first == second); // true trong cùng context
~~~

Lần `find` thứ hai thường không tạo SQL mới nếu entity đang managed. Cho dù database ở `READ COMMITTED`, Hibernate có thể trả cùng object với những giá trị đã đọc trước đó.

Tính chất này phục vụ nhất quán identity của object graph: nếu `Order.account` và một `Account` được truy vấn riêng cùng đại diện một hàng, Hibernate tránh tạo nhiều managed instances có cùng identity trong một context.

**Không nên gọi hành vi này là “DB đã cung cấp repeatable read”.** DB có thể chưa nhận câu SELECT thứ hai nào cả.

### 6.3. Dirty checking không phải isolation

~~~java
em.getTransaction().begin();

Account managed = em.find(Account.class, id);
managed.deposit(new BigDecimal("10.00"));

em.getTransaction().commit();
~~~

Dirty checking kiểm tra persistent state đã thay đổi để sinh SQL. Nó không bảo vệ mặc định mọi xung đột với transaction khác. Trong ứng dụng có concurrent writers, phải xem version/locking/isolation/atomic SQL và constraint.

Ví dụ hai context độc lập cùng đọc balance 100, mỗi context sửa entity thành một balance mới. Việc cả hai đều managed **không đủ** để bảo đảm tổng tiền cuối cùng là 130 nếu một giao dịch cộng 10, giao dịch kia cộng 20; cơ chế `@Version` hoặc update/locking thích hợp mới quyết định conflict được phát hiện thế nào.

### 6.4. Snapshot của ORM khác snapshot MVCC của database

Từ “snapshot” xuất hiện ở cả hai tầng, nhưng nghĩa khác nhau:

**ORM snapshot:**
- Có thể là bản biểu diễn persistent state mà Hibernate giữ để so sánh dirty fields.
- Gắn với một managed entity trong persistence context.
- Bị ảnh hưởng bởi flush, load, refresh, dirty tracking implementation.
- Không phải cam kết có phiên bản đồng nhất của mọi hàng DB tại một thời điểm.

**Database MVCC snapshot:**
- Là quy tắc database xác định version của các row mà một SQL statement hoặc transaction được phép nhìn thấy.
- Liên quan trực tiếp đến isolation và concurrency.
- Có thể được tạo theo statement hoặc transaction tùy DB/isolation.
- Không phải một collection các Java entity objects.

Hai snapshot có thể không đồng bộ. Ví dụ ORM còn state balance 100, còn một SQL SELECT trong cùng transaction `READ COMMITTED` có thể thấy giá trị đã commit mới 120, nếu SQL đó thực sự chạy và điều kiện database cho phép.

## 7. Case study: hai EntityManager và một hàng, READ COMMITTED

Xét database đang có:

~~~sql
INSERT INTO accounts (id, owner_name, balance, row_version)
VALUES (10, 'An', 100.00, 0);
~~~

Hai EntityManager độc lập:

~~~text
Transaction A / EntityManager A             Transaction B / EntityManager B
----------------------------------           --------------------------------
BEGIN (READ COMMITTED)

a1 = emA.find(Account, 10)
SQL SELECT -> balance=100
a1 MANAGED trong context A

                                             BEGIN
                                             b1 = emB.find(Account, 10)
                                             b1.deposit(20)
                                             flush UPDATE, COMMIT
                                             DB balance=120

a2 = emA.find(Account, 10)
Thường KHÔNG SELECT mới
a2 == a1; a2.balance=100

COMMIT A
~~~

Tình huống này không mâu thuẫn với `READ COMMITTED`, vì bước `emA.find` thứ hai được thỏa mãn ngay trong context.

### 7.1. Nếu thực thi một truy vấn SQL thật thì sao?

Giả sử A dùng JPQL scalar projection:

~~~java
BigDecimal balanceFromQuery = emA.createQuery(
        "select a.balance from Account a where a.id = :id",
        BigDecimal.class)
    .setParameter("id", 10L)
    .getSingleResult();
~~~

Ở mức `READ COMMITTED` của DB như PostgreSQL, nếu transaction B đã commit và không có thay đổi local/xung đột nào khác, SELECT scalar mới có thể thấy balance 120. Nhưng `a1.getBalance()` có thể vẫn là 100, vì `a1` là managed instance trước đó và Hibernate không bắt buộc tự refresh nó khi câu scalar query trả kết quả.

**Lưu ý:** Query flush mode, pending changes ở context A, lock và isolation có thể ảnh hưởng kết quả. Nếu A đã sửa balance và Hibernate flush trước query, ví dụ sẽ không còn đơn giản như một transaction chỉ đọc.

### 7.2. Truy vấn entity cũng chưa chắc cập nhật managed instance

~~~java
Account fromQuery = emA.createQuery(
        "select a from Account a where a.id = :id",
        Account.class)
    .setParameter("id", 10L)
    .getSingleResult();
~~~

Provider có thể thực thi SELECT để tìm identity, nhưng khi context đã quản lý `Account#10`, Hibernate sẽ dùng managed instance tương ứng. Không nên giả định object vừa được lấy qua JPQL tự có mọi giá trị mới từ DB.

Đây là một nguồn nhầm lẫn thường gặp: **SQL đọc dữ liệu mới hơn** và **entity object trong context đã được refresh** là hai sự kiện khác nhau.

### 7.3. Dùng refresh để nạp lại khi thật sự cần

~~~java
Account a = emA.find(Account.class, 10L);

// Transaction B commit thay đổi tại DB.

emA.refresh(a);

BigDecimal current = a.getBalance();
~~~

`refresh` yêu cầu provider nạp lại trạng thái entity managed từ database, ghi đè trạng thái persistent của instance bằng kết quả phù hợp với transaction/isolation hiện tại.

Ở `READ COMMITTED`, nếu SQL refresh chạy sau khi B commit và không bị ngăn bởi lock/visibility khác, A có thể nhận giá trị mới.

**Nhưng refresh không vượt qua database isolation.** Ở transaction có snapshot ổn định như PostgreSQL `REPEATABLE READ`, một refresh trong cùng transaction có thể tiếp tục quan sát version phù hợp với snapshot cũ, không thấy commit mới của B.

Ngoài ra, refresh có thể **làm mất các thay đổi local chưa flush**:

~~~java
Account a = emA.find(Account.class, 10L);
a.deposit(new BigDecimal("10.00")); // local balance 110

emA.refresh(a);
// Có thể ghi đè local balance 110 bằng dữ liệu DB đọc được.
~~~

Vì vậy không gọi refresh như cách chữa mặc định cho mọi vấn đề nhất quán.

### 7.4. clear rồi find lại có khác refresh không?

~~~java
emA.clear(); // Gỡ tất cả managed entities khỏi context A.

Account reloaded = emA.find(Account.class, 10L);
~~~

`clear()` làm các instances trước đó thành detached và lần `find` sau có thể cần SELECT mới. `refresh()` vẫn giữ chính managed instance trong context nhưng nạp lại giá trị. Cả hai đều phụ thuộc database isolation khi thực thi SELECT.

| Tác vụ | `refresh(a)` | `clear(); find(...)` |
|---|---|---|
| Gỡ toàn bộ entities khỏi context? | Không | Có |
| Giữ cùng Java instance `a`? | Có, nếu refresh thành công | Không bảo đảm; context mới nạp instance mới |
| Có thể ghi đè/bỏ thay đổi chưa flush? | Có đối với a | Có đối với nhiều entities |
| Vượt qua snapshot DB? | Không | Không |
| Có cần SQL nạp lại dữ liệu? | Thường có | Khi query cần nạp từ DB |
| Phạm vi tác động | Một entity và cascades phù hợp | Toàn bộ context |

Không dùng `clear` tùy tiện trong một transaction đang có thay đổi khác chưa flush: thay đổi đó có thể bị bỏ. Không dùng `refresh` tùy tiện khi người dùng vừa sửa dữ liệu trên form nhưng chưa commit.

### 7.5. Nếu A đã sửa entity cũ rồi commit sau B?

Giả sử:

~~~text
A đọc Account#10 balance=100, version=0
B đọc Account#10 balance=100, version=0
B cập nhật balance=120, version=1, COMMIT
A tự tính balance=110 và cố COMMIT
~~~

Nếu mapping có `@Version` và cả hai update qua đường Hibernate managed entity thông thường, A thường không cập nhật thành công lặng lẽ: update của A có điều kiện version cũ và bị phát hiện xung đột khi DB đã có version mới.

Cơ chế này **không phát sinh từ first-level cache tự thân** và cũng không có nghĩa READ COMMITTED đã biến thành SERIALIZABLE. Đây là **optimistic concurrency control** ở mức ORM phối hợp với SQL UPDATE và database.

## 8. Case study: REPEATABLE READ không có nghĩa “mọi object đều tự tươi mới”

Chọn PostgreSQL `REPEATABLE READ` làm ví dụ cụ thể. Giả sử:

~~~text
Transaction A (REPEATABLE READ)       Transaction B
----------------------------------    --------------------------
BEGIN
SELECT balance WHERE id=10
-> balance=100
(Snapshot của transaction A)

                                     UPDATE balance=120
                                     COMMIT

A dùng em.clear()
A SELECT lại cùng hàng
-> theo snapshot A, vẫn có thể thấy 100
~~~

Ở đây `clear()` đã buộc ORM không giữ object cũ, nhưng database tiếp tục cấp version phù hợp snapshot của A. Nếu A muốn ghi một hàng đã bị transaction B cập nhật, PostgreSQL có thể phát hiện xung đột và báo lỗi serialization/concurrent update, tùy lịch thao tác.

Đây là phản ví dụ quan trọng cho câu nói sai: **“Chỉ cần clear session là luôn đọc được dữ liệu mới nhất.”** Clear chỉ xóa managed state của ORM, không đổi snapshot DB đã được thiết lập.

### 8.1. Một transaction READ COMMITTED kéo dài cũng không nên giữ context vô hạn

READ COMMITTED có thể cho mỗi SQL SELECT mới thấy các commit mới, nhưng một persistence context sống lâu vẫn giữ rất nhiều managed entities và những bản state cũ. Vì vậy lựa chọn isolation thấp **không loại bỏ** nhu cầu quản lý vòng đời EntityManager/session.

Ví dụ xử lý theo lô 50.000 hàng mà giữ context xuyên nhiều thao tác:

~~~java
for (Long id : ids) {
    Account account = em.find(Account.class, id);
    // ...
}
~~~

Khi quá nhiều entities được managed, memory tăng và ứng dụng có thể không nhìn thấy những thay đổi ngoài context theo cách mong đợi. Có thể cần chia transaction/context theo chunk, stream DTO, hoặc flush/clear đúng lúc tùy mục tiêu. Đó là quyết định quản lý trạng thái ORM và hiệu năng, không phải một thuộc tính trực tiếp của READ COMMITTED.

### 8.2. Serializable có làm mọi reference Java trở nên an toàn?

Không. `SERIALIZABLE` là cam kết về lịch sử thực thi các transaction **đã commit thành công** ở DB theo implementation. Nó không đảm bảo một object detached được giữ qua nhiều request tự cập nhật dữ liệu trong bộ nhớ. Nó cũng không bảo đảm hai transaction concurrent đều thành công: một transaction có thể bị abort và yêu cầu chạy lại từ đầu.

Nếu code giữ một entity cũ sau khi transaction kết thúc rồi bắt đầu một transaction mới, entity đó có thể là detached. Mức SERIALIZABLE của transaction mới không tự làm detached entity đó managed hoặc fresh; cần nạp lại và áp dụng logic nghiệp vụ trong context/transaction mới.

## 9. Flush và commit: ORM đồng bộ SQL, DB quyết định visibility

Trong JPA/Hibernate, **flush** thường là thời điểm provider gửi những câu SQL pending để đồng bộ persistence context với database. **Commit** là thời điểm database transaction xác nhận thay đổi.

~~~java
em.getTransaction().begin();

Account a = em.find(Account.class, accountId);
a.deposit(new BigDecimal("20.00"));

em.flush(); // SQL UPDATE có thể đã chạy trong transaction hiện tại.
// Chưa có commit.

em.getTransaction().commit();
~~~

Tác động với concurrency:

- Transaction hiện tại thường có thể quan sát tác động các thay đổi của chính nó theo database semantics.
- Transaction khác ở READ COMMITTED không được thấy các thay đổi chưa commit của transaction hiện tại.
- Ở isolation thích hợp, các transaction có thể chờ lock hoặc gặp conflict.
- Nếu rollback, SQL đã flush nhưng chưa commit không trở thành thay đổi durable.
- Flush không detach entity và không làm entity từ transaction khác tự refresh.

### 9.1. AUTO flush trước query

Mặc định `FlushModeType.AUTO` có thể khiến Hibernate flush trước khi chạy một truy vấn để bảo đảm kết quả query phù hợp với thay đổi pending theo đặc tả/provider.

~~~java
em.getTransaction().begin();

Account a = em.find(Account.class, accountId);
a.deposit(new BigDecimal("20.00"));

BigDecimal balance = em.createQuery(
        "select a.balance from Account a where a.id = :id",
        BigDecimal.class)
    .setParameter("id", accountId)
    .getSingleResult();

em.getTransaction().commit();
~~~

Không nên suy luận “SELECT này đọc database cũ vì chưa gọi flush” hay “SELECT này nhất định chạy một UPDATE trước đó” khi chưa biết flush mode, query và implementation. Hibernate có thể flush theo query space/metadata, và SQL được gửi sẽ tuân theo isolation DB.

### 9.2. Flush có thể làm lộ lỗi sớm, nhưng chưa phải commit

Constraint `UNIQUE`, FK hoặc `CHECK` có thể được kiểm tra khi SQL INSERT/UPDATE chạy lúc flush. Một số constraint được DB cho phép deferred tới commit nếu được khai báo/cấu hình như vậy.

Dù flush thành công, commit vẫn có thể thất bại vì conflict, deferred constraints, lỗi hạ tầng hoặc cơ chế transaction khác. Vì vậy code không nên báo thao tác nghiệp vụ đã thành công vĩnh viễn chỉ sau `em.flush()`.

### 9.3. Transaction rollback không khôi phục field Java

~~~java
em.getTransaction().begin();

Account a = em.find(Account.class, accountId);
a.deposit(new BigDecimal("50.00"));

em.getTransaction().rollback();
~~~

DB rollback nhưng biến `a` có thể vẫn giữ số dư đã cộng trong RAM. Rollback **không tự gọi các setter ngược lại** để restore toàn bộ object graph. Sau exception/rollback, không tiếp tục tin cậy context đã lỗi; với application-managed EntityManager, nên rollback, đóng context và dùng context mới cho use case tiếp theo.
## 10. Optimistic locking: @Version không phải mức cô lập

**Optimistic locking** phù hợp khi xung đột cập nhật không quá thường xuyên và ứng dụng chấp nhận kiểm tra khi ghi thay vì khóa row ngay từ lúc đọc.

Với entity có:

~~~java
@Version
@Column(name = "row_version", nullable = false)
private long version;
~~~

Hibernate thường tạo lệnh UPDATE về ý tưởng như:

~~~sql
UPDATE accounts
SET balance = ?, row_version = ?
WHERE id = ? AND row_version = ?;
~~~

Giả sử row ban đầu có `balance = 100, version = 5`:

~~~text
Transaction A                            Transaction B
-------------                            -------------
Đọc balance=100, version=5
                                         Đọc balance=100, version=5
                                         UPDATE balance=120, version=6
                                         WHERE id=10 AND version=5;
                                         COMMIT

A cố UPDATE balance=130, version=6
WHERE id=10 AND version=5;
-> không còn row khớp: conflict
~~~

Provider có thể ném `OptimisticLockException` hoặc ngoại lệ liên quan ở lúc flush/commit (đôi khi sớm hơn). Nhờ vậy thay đổi của B không bị A ghi đè lặng lẽ qua đường managed-entity update thông thường, miễn các writer tuân theo cơ chế version.

**Tách rõ ba trách nhiệm:**

- **DB isolation:** visibility, khóa và lịch sử giao dịch được phép.
- **Hibernate managed state:** giữ entity và phát hiện thay đổi cần UPDATE.
- **`@Version`:** kiểm tra version khi ghi và phát hiện một loại conflict, dựa trên SQL/DB để xác định update có khớp không.

Một transaction `READ COMMITTED` vẫn có thể tránh lost update trên một row nhờ `@Version`. Nhưng `@Version` không chuyển toàn transaction thành `SERIALIZABLE`.

### 10.1. Vì sao version trên từng entity chưa đủ cho bất biến nhiều hàng?

Quay lại ví dụ “phải có ít nhất một bác sĩ trực”. T1 chỉ sửa Doctor A; T2 chỉ sửa Doctor B. Mỗi hàng có version và mỗi transaction chỉ cập nhật **một hàng khác nhau**. Chúng có thể không đụng cùng version, trong khi tổng thể quy tắc “ít nhất một bác sĩ trực” bị vi phạm.

Có thể phải chọn isolation `SERIALIZABLE` phù hợp với DB, một shared control row được lock/version, constraint hoặc transaction protocol bảo vệ bất biến liên hàng. Không tuyên bố “mọi entity có `@Version` thì mọi business invariant đều an toàn”.

### 10.2. Detached entity và merge

~~~java
Account detached = ...; // Đọc ở request cũ, version=5.
Account managed = em.merge(detached);
~~~

`merge` sao chép trạng thái của detached instance vào một managed instance và trả về **managed instance**. Nó không tự biến object đầu vào thành managed. Nếu version đã thay đổi trong DB, conflict có thể được phát hiện khi merge, flush hoặc commit.

Trong API nhiều request, ưu tiên DTO chứa những field được phép thay đổi; service nạp managed entity trong transaction mới và cập nhật có chọn lọc. Nếu cần phát hiện người dùng chỉnh sửa dựa trên state cũ, hãy thiết kế version/ETag/If-Match rõ ràng.

Khi `OptimisticLockException` làm transaction thất bại, không tiếp tục sửa trên context cũ. Thông thường rollback, đóng/discard context lỗi, bắt đầu transaction/context mới, đọc lại dữ liệu và quyết định retry có giới hạn hoặc trả conflict cho người dùng. **Retry phải đánh giá lại business condition**, không chỉ chạy lại một phép tính từ dữ liệu stale.

## 11. Pessimistic locking: ORM yêu cầu khóa do database thực hiện

JPA hỗ trợ yêu cầu khóa pessimistic:

~~~java
import jakarta.persistence.LockModeType;

em.getTransaction().begin();

Account account = em.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE
);

account.withdraw(new BigDecimal("50.00"));

em.getTransaction().commit();
~~~

Hibernate và dialect có thể dùng lệnh SQL locking tương ứng, chẳng hạn biến thể của `SELECT ... FOR UPDATE` trên DB hỗ trợ. Việc khóa là **cơ chế database trong transaction**, không phải một dấu hiệu lưu trong Java entity vượt qua request.

### 11.1. Khi nào PESSIMISTIC_WRITE có ích?

Nếu hai giao dịch cùng muốn thay đổi **cùng một row**, một giao dịch khóa trước có thể khiến giao dịch kia chờ hoặc nhận timeout/conflict. Điều này hữu ích cho thao tác đọc–kiểm tra–ghi cần giữ row không bị transaction khác sửa trong lúc thực hiện.

Tuy nhiên:

- Khóa đúng row không tự bảo vệ mọi điều kiện liên hàng.
- Cần transaction thực sự bao trùm cả việc đọc và ghi.
- Khóa lâu làm tăng contention, deadlock và latency.
- Không nên giữ transaction mở trong lúc gọi dịch vụ bên ngoài hoặc chờ thao tác người dùng.
- Timeout, cú pháp SQL, lock escalation và deadlock detection tùy DB/driver.

### 11.2. Các lock modes của JPA

| Lock mode | Ý định |
|---|---|
| `OPTIMISTIC` | Yêu cầu kiểm tra optimistic lock/version phù hợp |
| `OPTIMISTIC_FORCE_INCREMENT` | Yêu cầu tăng version theo contract/provider |
| `PESSIMISTIC_READ` | Yêu cầu khóa đọc theo khả năng DB |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi theo khả năng DB |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa pessimistic và version increment phù hợp |

Không suy luận `PESSIMISTIC_READ` sẽ luôn tạo một SQL giống nhau trong PostgreSQL, Oracle, MySQL hoặc SQL Server. Provider/dialect có thể dùng các cách khác nhau.

Ví dụ hint timeout:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 1000
);

Account account = em.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

Hint cần import `java.util.Map`; cách driver/DB hỗ trợ lock timeout có thể khác. Đặt timeout không biến `READ COMMITTED` thành `REPEATABLE READ`, và không sửa được một transaction có phạm vi quá dài.

### 11.3. Lock không tồn tại “bên trong một detached object”

~~~text
Transaction A:
    SELECT Account#10 FOR UPDATE
    COMMIT
    -> lock được giải phóng theo DB

Request B sau đó:
    giữ Java object Account#10 từ A
    -> KHÔNG còn giữ lock của A
~~~

Muốn khóa trong thao tác B, phải bắt đầu transaction B và lấy khóa thích hợp tại DB. Truyền entity Java giữa các request không kéo theo transaction lock.

## 12. Atomic SQL và DB constraints: lớp bảo vệ riêng

Một số thay đổi có thể viết trực tiếp dưới dạng SQL có điều kiện, tránh mẫu đọc giá trị cũ về Java rồi tự tính số mới.

Ví dụ kho hàng:

~~~sql
UPDATE inventory
SET quantity = quantity + 5
WHERE product_id = 42;
~~~

Với thao tác xuất kho không để lượng âm:

~~~sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 42
  AND quantity >= 3;
~~~

Nếu update ảnh hưởng 0 row, có thể không đủ hàng hoặc product ID không tồn tại; code nghiệp vụ cần phân biệt nếu quan trọng. Constraint DB vẫn giúp bảo vệ dữ liệu:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_non_negative CHECK (quantity >= 0);
~~~

**Atomic SQL** có thể giải quyết một phép biến đổi cụ thể mà không cần đọc–sửa–ghi bằng stale entity. Nhưng nếu context đang giữ `Inventory#42`, sau native SQL object đó có thể vẫn chứa quantity cũ. SQL correctness và Java managed state vẫn phải được quản lý riêng.

### 12.1. UNIQUE không phải một isolation level

Giả sử tạo email mới:

~~~java
if (!repository.existsByEmail(email)) {
    repository.save(new Customer(email));
}
~~~

Hai transaction cùng thấy “chưa tồn tại” rồi cùng insert. Ở `READ COMMITTED`, điều này có thể tạo một cuộc đua. Cần DB unique constraint đúng phạm vi:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_email UNIQUE (email);
~~~

Constraint ngăn duplicate dù script SQL hoặc ứng dụng khác cũng ghi vào bảng. Code phải xử lý lỗi duplicate và rollback transaction đúng cách. Không dùng first-level cache hoặc `existsByEmail` thay cho constraint.

### 12.2. Foreign key và CHECK cũng không được thay bởi ORM state

`@ManyToOne(optional = false)`, `@Column(nullable = false)` và validation ở Java là metadata/lớp kiểm tra ứng dụng. Nếu mọi đường ghi đều phải bảo đảm FK, not-null và miền giá trị, database phải có ràng buộc thực sự tương ứng.

Isolation chi phối cách transaction cùng hoạt động; **constraint** mô tả trạng thái dữ liệu nào được DB chấp nhận. Chúng bổ sung cho nhau.

## 13. Second-level cache và query cache không phải transaction snapshot

Ngoài first-level cache, Hibernate có thể cấu hình second-level cache/query cache. Các khái niệm cần phân biệt:

| Cơ chế | Phạm vi | Ý nghĩa |
|---|---|---|
| First-level cache / persistence context | Một EntityManager/Session | Identity map, managed state, dirty checking |
| Second-level cache (tùy chọn) | Có thể chia sẻ giữa sessions | Cache dữ liệu entity/collection theo chính sách |
| Query cache (tùy chọn) | Có thể chia sẻ theo cấu hình query | Cache kết quả/identifiers theo strategy |
| Database MVCC snapshot | DB statement/transaction | Quy tắc row versions nào được thấy |
| Database buffer cache | Database engine | Cache trang/index để thực thi SQL |

Second-level cache không biến một instance của session A thành managed trong session B. Query cache không tự thực thi `SERIALIZABLE`; nó có thể làm một truy vấn không cần SELECT trong một lần thực hiện, nhưng đó là cache behavior, không phải isolation của một SQL transaction.

Những thay đổi bằng native SQL hoặc hệ thống ngoài Hibernate có thể khiến cache stale nếu không phối hợp invalidation. Đặc biệt với nghiệp vụ cần tính nhất quán cao, không dựa vào cache để bảo vệ uniqueness, số dư, quyền truy cập hoặc quy tắc đồng thời.

## 14. Bulk JPQL/SQL làm thay đổi DB nhưng không tự refresh managed entity

Xét context đã tải một Account:

~~~java
Account account = em.find(Account.class, 10L);
// account.balance = 100.
~~~

Sau đó chạy bulk JPQL update:

~~~java
int changed = em.createQuery(
        "update Account a " +
        "set a.balance = a.balance + :delta " +
        "where a.id = :id")
    .setParameter("delta", new BigDecimal("10.00"))
    .setParameter("id", 10L)
    .executeUpdate();
~~~

Câu bulk DML thao tác trực tiếp trên database thay vì cập nhật từng managed instance qua dirty checking. `account.getBalance()` có thể vẫn là 100 dù SQL đã tăng thành 110 trong DB transaction.

Hệ quả thực tế:

- `em.find(Account.class, 10L)` có thể trả lại chính instance cũ từ identity map.
- `em.refresh(account)` yêu cầu đọc lại với visibility theo transaction hiện tại, nhưng có thể ghi đè thay đổi local.
- `em.clear()` detach toàn bộ entities và có thể bỏ pending changes chưa flush.
- Entity lifecycle callbacks, cascades và optimistic version handling của từng entity không được áp dụng cho bulk SQL giống cập nhật managed entity thông thường.
- Nếu cần cập nhật version hoặc kiểm tra conflict khi bulk update, phải thiết kế SQL và transaction protocol riêng.

Một workflow có chủ đích có thể tách:

~~~text
1. Hoàn tất/flush những managed changes cần giữ.
2. Chạy bulk DML trong transaction phù hợp.
3. Kết thúc context hoặc refresh/clear có kiểm soát.
4. Tiếp tục sử dụng state mới ở context phù hợp.
~~~

Không gọi `clear()` tùy tiện khi còn những entity khác chưa được flush. Và không xem bulk DML là một “lệnh Hibernate cập nhật mọi Java object trong bộ nhớ”.

Nếu script SQL của hệ thống khác sửa account, context đang mở cũng không tự nhận thay đổi đó. **Database visibility không tương đương đồng bộ toàn bộ object graph.**
## 15. Spring @Transactional: thiết lập isolation khác với quản lý EntityManager

Trong Spring, người dùng thường cấu hình transaction tại service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void deposit(Long id, BigDecimal amount) {
        Account account = repository.findById(id).orElseThrow();
        account.deposit(amount);
    }
}
~~~

Đoạn ví dụ giả định `AccountRepository` là repository đã được khai báo phù hợp và `Account` có method `deposit` như phần trước. Spring transaction manager sẽ điều phối transaction khi lời gọi đi qua cơ chế transaction interceptor/proxy thích hợp.

Điều cần hiểu:

- `isolation = Isolation.READ_COMMITTED` yêu cầu isolation theo khả năng transaction manager/database; nó không đổi cách `EntityManager` quản lý identity map.
- `@Transactional` tạo ranh giới giao dịch theo propagation và phạm vi invocation, **không mặc nhiên trả một entity fresh** ở mọi câu gọi repository.
- EntityManager thường được Spring cung cấp dưới dạng proxy gắn với persistence context phù hợp với transaction.
- Cần kết hợp với datasource/connection pool để bảo đảm isolation đúng; không tự can thiệp connection bằng JDBC code độc lập ngoài transaction manager.
- `@Transactional(readOnly = true)` là một chỉ dẫn/optimization hint ở framework/provider, **không đồng nghĩa database transaction đang SERIALIZABLE hoặc mọi SELECT luôn là snapshot bất biến**.

### 15.1. Propagation ảnh hưởng isolation thực tế

Giả sử service A đã mở transaction:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    innerService.run();
}
~~~

Và service B yêu cầu:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void run() {
    // ...
}
~~~

Nếu `run()` tham gia transaction đang tồn tại theo propagation mặc định `REQUIRED`, yêu cầu isolation của method trong có thể **không làm thay đổi isolation đã được chọn cho transaction ngoài**. Isolation thường được thiết lập khi mở một transaction mới.

Không nên giả định cứ nhìn thấy `@Transactional(isolation = SERIALIZABLE)` trên method thì mọi SQL trong lời gọi của method đó chắc chắn chạy ở mức SERIALIZABLE, bất kể caller.

Những hướng xử lý:

- Thiết kế transaction boundary rõ ràng để method cần isolation cao mở transaction mới trong phạm vi phù hợp.
- Nếu dùng `REQUIRES_NEW`, hiểu rằng giao dịch mới độc lập với giao dịch ngoài về commit/rollback và có thể dùng connection khác.
- Kiểm tra transaction manager có hỗ trợ validation của isolation với existing transactions không.
- Tránh mở transaction ngoài nếu không cần và tránh nesting chỉ để giải quyết sự nhầm lẫn về propagation.

### 15.2. Self-invocation và transaction proxy

Một class tự gọi method gắn `@Transactional`:

~~~java
@Service
public class ExampleService {
    public void outer() {
        this.inner(); // Trong Spring proxy mode thường không qua proxy.
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void inner() {
        // ...
    }
}
~~~

Trong cơ chế proxy-based AOP phổ biến, self-invocation không đi qua transaction interceptor, nên annotation ở `inner()` có thể không tạo transaction như mong đợi. Cách đơn giản là tách method cần boundary sang bean khác hoặc dùng `TransactionTemplate`. Khi triển khai, cần kiểm tra chế độ AOP/AspectJ mà dự án thực sự cấu hình.

### 15.3. Open Session in View không phải isolation

OSIV (Open Session in View) giữ persistence context/session trong phạm vi web request để truy cập lazy associations ở tầng view/serializer. Nó không có nghĩa một database transaction dài tự bao toàn request, cũng không cho phép suy luận read consistency.

Khi API serializer tải lazy collection sau khi service transaction đã kết thúc, có thể phát sinh SQL ngoài boundary nghiệp vụ đã tính toán, tạo N+1 hoặc quan sát dữ liệu ở thời điểm khác. Với hệ thống cần kiểm soát tính nhất quán, ưu tiên thiết kế fetch plan và DTO trong transaction được định nghĩa rõ.

## 16. Đọc nhất quán: lựa chọn mức isolation và cách sử dụng ORM

Cần xác định **mục tiêu nhất quán** trước khi chọn một mức isolation.

### 16.1. Màn hình hiển thị thông tin thông thường

Một màn hình sản phẩm chỉ đọc tên và giá. Dữ liệu có thể thay đổi giữa hai request và việc cập nhật mới nhất không mang ý nghĩa giao dịch quan trọng. Thường có thể dùng READ COMMITTED và context ngắn theo request/transaction.

Nếu cùng request thực hiện nhiều query và đòi mọi thông tin thuộc một thời điểm nhất quán, phải xem thêm semantics snapshot của DB hoặc chuẩn bị một DTO được truy vấn đúng phạm vi. Giữ một managed instance trong first-level cache không đảm bảo **mọi bảng** đã được đọc cùng một snapshot.

### 16.2. Báo cáo nhiều truy vấn cần snapshot thống nhất

Một báo cáo gồm tổng doanh thu và chi tiết theo đơn hàng. Nếu chạy query tổng ở thời điểm t1, query chi tiết ở t2, và transaction khác thêm đơn hàng giữa chúng, hai số có thể không khớp dưới READ COMMITTED.

Nếu nghiệp vụ đòi một snapshot ổn định, có thể chọn transaction isolation/snapshot cơ sở dữ liệu phù hợp, ví dụ REPEATABLE READ với PostgreSQL trong phạm vi transaction báo cáo. Nhưng cần hiểu việc mở transaction dài có chi phí MVCC/locks và isolation của DB khác có thể không giống.

**Persistence context không tự tạo snapshot toàn bộ database.** Nếu query đầu chỉ tải 10 entity, không có nghĩa nó giữ toàn bộ dữ liệu cho report ở một thời điểm cố định.

### 16.3. Đọc–kiểm tra–ghi một hàng quan trọng

Ví dụ rút tiền:

~~~java
@Transactional
public void withdraw(Long accountId, BigDecimal amount) {
    Account account = em.find(
        Account.class, accountId, LockModeType.PESSIMISTIC_WRITE
    );
    account.withdraw(amount);
}
~~~

Khi cần bảo đảm hai thao tác cạnh tranh trên cùng row không cùng vượt qua điều kiện, pessimistic lock hoặc optimistic version kèm retry/error handling có thể phù hợp. Phải xác định lock được thực thi trong transaction và xử lý timeout/deadlock đúng.

Với SQL atomic conditional update, cũng có thể bảo vệ một số bất biến mà không cần tải entity, nhưng sẽ thay đổi cách ORM callbacks/version/managed state được áp dụng.

### 16.4. Bất biến liên hàng

Ví dụ tổng phân bổ không vượt hạn mức hoặc ít nhất một người trực. Có thể cần serializable isolation, lock một aggregate-control row, constraint hoặc một mô hình dữ liệu khác để bảo vệ.

Một `@Version` trên từng entity không tự phát hiện hai transaction sửa hai hàng khác nhau. Cần kiểm tra invariants cụ thể và transaction schedule.

### 16.5. Danh sách phân trang trên dữ liệu đang thay đổi

Nếu API lấy page 1 ở transaction A và page 2 ở transaction B, data có thể được thêm/xóa giữa hai lần. Không isolation của transaction A nào giữ snapshot cho transaction B sau khi A kết thúc.

Các hướng khác nhau:

- Chấp nhận dữ liệu thay đổi theo thời điểm truy vấn.
- Keyset pagination theo khóa ổn định để giảm bỏ sót/lặp do offset dịch chuyển.
- Định nghĩa cutoff/version của dataset.
- Dùng snapshot/staging/result set riêng khi yêu cầu một báo cáo bất biến qua nhiều trang.

Persistence context không thể được dùng như một giải pháp tổng quát để “đóng băng” danh sách hàng cho người dùng qua nhiều request.

## 17. Thiết kế một thí nghiệm hai giao dịch không nhầm ORM với DB

Để hiểu đúng một anomaly, cần phân biệt **đọc bằng ORM từ managed instance** và **gửi lại SQL thật**.

Một bài thực nghiệm nên có ba biến:

1. Database/isolation: ví dụ PostgreSQL với READ COMMITTED hoặc REPEATABLE READ.
2. Cách đọc: `em.find` khi entity đã managed, `em.refresh`, `em.clear(); find`, hoặc scalar JPQL/native SELECT.
3. Lịch transaction: A đọc trước; B cập nhật và commit; A đọc sau, trong cùng transaction A nếu muốn kiểm tra isolation.

### 17.1. Mẫu lịch kiểm thử

~~~text
Chuẩn bị: Account#10, balance=100, version=0.

A: BEGIN, isolation được thiết lập.
A: emA.find(Account, 10) -> managedA.balance=100

B: BEGIN.
B: emB.find(Account, 10)
B: thay balance=120
B: COMMIT.

A: emA.find(Account, 10) lần 2
   -> ghi lại có SELECT mới hay không

A: chạy scalar query SELECT balance
   -> ghi lại SQL và giá trị

A: emA.refresh(managedA) hoặc emA.clear(); find(...)
   -> ghi lại SQL và giá trị

A: COMMIT hoặc ROLLBACK.
~~~

Nếu muốn kiểm tra READ COMMITTED và REPEATABLE READ một cách có thể lặp lại, cần bảo đảm thứ tự trên bằng các điểm đồng bộ (barrier/latch) khi test chạy nhiều thread hoặc bằng hai connection/transaction được điều khiển từ integration test.

### 17.2. Không dùng cùng EntityManager cho hai thread

Sai:

~~~java
// Hai thread cùng sử dụng một EntityManager instance.
threadA(() -> sharedEntityManager.find(Account.class, 10L));
threadB(() -> sharedEntityManager.find(Account.class, 10L));
~~~

EntityManager không thread-safe. Cần **mỗi transaction/thread có EntityManager riêng** và transaction manager phù hợp. Nếu test dùng một `@Transactional` trên toàn test method rồi khởi chạy thread khác, thread đó thường không tự tham gia cùng transaction do transaction context gắn với execution/thread theo mô hình framework thông dụng.

### 17.3. Ví dụ Java SE gồm hai EntityManager

Mẫu logic sau phù hợp khi database/driver hỗ trợ thay đổi isolation qua JDBC và EntityManager được cấu hình resource-local. Phần điều phối barrier được lược bỏ để tập trung vào các bước:

~~~java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    emA.getTransaction().begin();
    Account a = emA.find(Account.class, 10L);
    BigDecimal firstValue = a.getBalance();

    emB.getTransaction().begin();
    Account b = emB.find(Account.class, 10L);
    b.deposit(new BigDecimal("20.00"));
    emB.getTransaction().commit();

    // ORM read: có thể nhận lại cùng managed instance của A.
    Account again = emA.find(Account.class, 10L);
    BigDecimal ormValue = again.getBalance();

    // Scalar SQL path: yêu cầu provider thực hiện truy vấn.
    BigDecimal sqlValue = emA.createQuery(
            "select a.balance from Account a where a.id = :id",
            BigDecimal.class)
        .setParameter("id", 10L)
        .getSingleResult();

    // Quan sát kết quả trước khi quyết định refresh/clear.
    System.out.println(firstValue + " / " + ormValue + " / " + sqlValue);

    emA.getTransaction().commit();
} finally {
    if (emA.getTransaction().isActive()) emA.getTransaction().rollback();
    if (emB.getTransaction().isActive()) emB.getTransaction().rollback();
    emA.close();
    emB.close();
}
~~~

Đây là **mẫu minh họa để xây integration test**, không phải test độc lập bảo đảm deterministic cho mọi DB. Trước khi chạy thực tế, cần cấu hình isolation rõ, bảo đảm hàng tồn tại, kiểm soát thời điểm và xử lý exception khi hai transaction xung đột. Ví dụ trên chỉ một thread điều phối và dùng nhiều EntityManager nên thuận tiện để hiểu thứ tự, nhưng không kiểm tra được mọi trường hợp deadlock/write skew mà concurrency thực tạo ra.

Nếu test framework rollback mọi transaction lúc kết thúc test, phải chú ý transaction B có thật sự commit trước khi A đọc lại hay không. Nếu dùng in-memory database thay PostgreSQL/MySQL production, kết quả không tự đại diện chính xác cho DB thật.

### 17.4. Điều gì cần ghi trong kết quả?

Để khẳng định nguyên nhân:

- Isolation level thực tế của transaction/connection.
- Thời điểm transaction bắt đầu và mỗi transaction commit.
- SQL log: lần đọc thứ hai có phát SELECT không?
- Managed instance identity: `first == second` hay không?
- `refresh`/`clear` đã được gọi chưa?
- Có second-level/query cache được bật không?
- Có `@Version` và UPDATE có điều kiện version không?
- Có transaction rollback hoặc serialization failure không?

Bằng chứng từ SQL log và database behavior giúp tránh hai kết luận sai: “READ COMMITTED không hoạt động” và “Hibernate đã vượt qua isolation”. Thực tế có thể chỉ là ORM trả object đã managed hoặc query được thực hiện dưới snapshot DB không như giả định.

## 18. Một số nguyên tắc về isolation khi dùng Hibernate

### 18.1. Đặt isolation từ đầu transaction

Mức isolation thường phải được thiết lập trước khi các SQL liên quan chạy trong transaction, và phải tuân theo quy tắc driver/transaction manager. Đổi isolation sau khi transaction đã đọc dữ liệu có thể bị DB từ chối, bỏ qua hoặc tạo hành vi không như dự đoán.

Với PostgreSQL, có thể dùng SQL về ý tưởng:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance FROM accounts WHERE id = 10;

COMMIT;
~~~

Đây là SQL minh họa riêng PostgreSQL. Trong ứng dụng Spring, nên để transaction manager áp dụng isolation thay vì tự gửi `BEGIN`/`SET TRANSACTION` trên một connection do framework đang điều khiển, trừ khi hiểu rõ hợp đồng tích hợp.

### 18.2. Isolation cao không phải lựa chọn mặc định cho mọi tác vụ

`SERIALIZABLE` có thể hạn chế các bất biến concurrency khó, nhưng tăng nguy cơ transaction phải rollback/retry khi xung đột. Nếu transaction dài, phức tạp hoặc thường xuyên đụng cùng dữ liệu, throughput và latency có thể bị ảnh hưởng.

Với các thao tác ngắn trên cùng entity có version, `READ COMMITTED` + `@Version`/constraint đôi khi phù hợp hơn. Với một báo cáo cần snapshot nhất quán, một mức isolation cho đọc có thể thích hợp; với một biến động số dư liên quan nhiều hàng, cần phân tích invariants sâu hơn.

**Không có quy tắc “isolation cao nhất luôn tốt nhất”**. Lựa chọn phải theo các anomaly cần ngăn, workload, DB semantics, chiến lược retry và yêu cầu latency.

### 18.3. Không đồng nhất consistency với freshness

Một kết quả đọc có thể **nhất quán theo snapshot** nhưng **không phải giá trị vừa commit gần nhất**. Ví dụ REPEATABLE READ có thể cho một transaction báo cáo nhìn thấy một snapshot ổn định nhưng không thấy các cập nhật mới xảy ra sau snapshot.

Ngược lại, READ COMMITTED cho nhiều statement thấy dữ liệu mới hơn, nhưng một báo cáo đa truy vấn có thể tự mâu thuẫn nếu dữ liệu thay đổi giữa chúng.

“Freshness” và “transaction consistency” là hai mục tiêu khác nhau. First-level cache lại thêm một phạm vi khác: tính nhất quán của managed object graph trong cùng context.
## 19. Những lỗi thường gặp khi nhầm database isolation với ORM state

| Hiện tượng | Giải thích có thể | Việc cần xác định |
|---|---|---|
| `READ COMMITTED` nhưng hai lần `find()` trả cùng dữ liệu cũ | Lần sau lấy lại managed instance từ first-level cache | Có SELECT thứ hai thực sự không? |
| Dùng `clear()` mà vẫn thấy dữ liệu cũ | Transaction đang dùng snapshot theo isolation hoặc query/cache khác | Isolation, transaction snapshot, SQL log |
| `refresh()` không thấy commit mới từ transaction khác | DB snapshot/lock/visibility, hoặc query chưa phù hợp | Isolation của DB và thời điểm statement |
| `flush()` xong nhưng session khác chưa thấy UPDATE | Chưa commit, READ COMMITTED không thấy thay đổi chưa commit | Transaction boundary, flush vs commit |
| Rollback rồi object Java vẫn giữ giá mới | Rollback DB không hoàn tác setter Java | Context đã đóng/discard và có reload không? |
| Hai managed entities ở hai EntityManager cùng sửa một row | Managed chỉ là trạng thái trong mỗi context | Version, locking, isolation, conflict handling |
| `@Version` không bảo vệ điều kiện ít nhất một bác sĩ trực | Mỗi transaction sửa row khác nhau | Bất biến liên hàng, write skew, serializable/aggregate lock |
| Gọi bulk update xong entity cũ vẫn giữ giá trước đó | Bulk DML không tự refresh first-level cache | Refresh/clear/context boundary |
| Câu query scalar thấy giá mới nhưng entity getter vẫn thấy giá cũ | SQL và managed instance đang ở hai trạng thái khác nhau | Identity map, SQL log, query result type |
| Hai transaction cùng kiểm tra email chưa tồn tại rồi insert | Check-then-act race; isolation/context không thay UNIQUE | DB constraint và xử lý duplicate |
| `@Transactional(isolation = SERIALIZABLE)` ở method trong không hiệu lực như nghĩ | Đã tham gia transaction ngoài; propagation/transaction manager | Boundary thực, proxy, isolation hiện tại |
| `@Transactional` trên self-call không tạo boundary mới | Spring proxy-based AOP không intercept `this.method()` | Bean invocation path, AOP config |
| `PESSIMISTIC_WRITE` không ngăn giao dịch khác sửa một row khác | Khóa chỉ bao phủ tài nguyên cụ thể theo DB | Predicate/invariant nào cần bảo vệ? |
| `SERIALIZABLE` gây serialization failure | DB phát hiện lịch sử không thể tuần tự hóa | Retry transaction mới, idempotency |
| Bật second-level cache nhưng vẫn thấy dữ liệu stale | Cache invalidation hoặc external writes | Cache policy, update path, context |
| Đóng EntityManager rồi đọc lazy relation bị lỗi | Entity detached, association chưa tải | Fetch plan/DTO trong transaction |
| Đổi isolation trên JDBC connection nhưng kết quả không đổi | Đặt sai thời điểm/connection hoặc transaction ngoài đã tồn tại | DataSource, pool, transaction manager, SQL session |
| Test concurrency chạy trên H2 cho kết quả khác PostgreSQL | DB implementation khác | Test tích hợp trên đúng DB/driver |

Không có một cách sửa chung cho tất cả những triệu chứng này. Cùng kết quả “đọc dữ liệu cũ” có thể xuất phát từ managed state, cache, snapshot MVCC, replicas, transaction propagation hoặc việc truy vấn không thực sự chạy. Cần xác định đúng tầng trước khi chọn giải pháp.

### 19.1. Sai lầm: đổi mọi transaction sang SERIALIZABLE để sửa stale entity

Nếu `em.find()` trả cùng managed instance từ first-level cache, đổi isolation có thể không làm một SQL mới xuất hiện. Cách giải quyết phụ thuộc nhu cầu:

- Nếu cần tải trạng thái DB mới trong transaction cho phép thấy giá trị mới: `refresh`, `clear()+find` hoặc context mới.
- Nếu DB snapshot phải ổn định: chấp nhận kết quả snapshot và không cố dùng clear để vượt isolation.
- Nếu cần cập nhật cạnh tranh an toàn: version, locking, atomic update hoặc serializable transaction tùy invariant.

Chọn isolation cao một cách toàn cục có thể làm giảm throughput và tăng retry mà vẫn không giải quyết nguyên nhân là object Java cũ.

### 19.2. Sai lầm: clear context để “rollback SQL”

`clear()` detach managed entities và có thể bỏ những thay đổi chưa flush; nó **không phải rollback của database transaction**. Nếu SQL UPDATE đã flush trong transaction, clear không tự hủy SQL đó. Cần `rollback()` cho transaction khi phải hủy các thay đổi chưa commit.

### 19.3. Sai lầm: cùng EntityManager nhưng transaction khác thì không có stale state

Một application-managed EntityManager có thể sống qua nhiều transactions. Khi entity còn managed qua một phạm vi context dài, nó có thể giữ state cũ dù transaction mới đã bắt đầu. Không suy luận cứ có `BEGIN` mới là mọi managed objects tự được nạp lại.

Trong web/service thông thường, context theo transaction ngắn thường giảm rủi ro này. Tuy nhiên, kể cả context mới cũng chỉ cho SQL quan sát dữ liệu theo isolation và thời điểm transaction được thiết lập.

### 19.4. Sai lầm: @Version thay thế database constraints

`@Version` không bắt một cột `email` phải unique, không bảo đảm FK tồn tại và không cấm balance âm nếu nghiệp vụ bypass validation bằng SQL. Cần database constraints cho các invariants có thể diễn đạt bằng schema và dùng version cho concurrency của những row được quản lý.

### 19.5. Sai lầm: SELECT trước UPDATE chắc chắn an toàn vì hai lời gọi trong một method

Nếu method không có transaction boundary đúng (ví dụ self-invocation, thiếu transaction proxy, query chạy trên các connections khác), SELECT và UPDATE có thể không thuộc cùng một transaction như developer nghĩ. Ngay cả khi cùng transaction, `READ COMMITTED` không tự bảo vệ mọi read–modify–write race nếu không lock/version/atomic SQL.

Thiết kế transaction phải được xác nhận bằng scope thực, không suy ra chỉ từ hai lệnh nằm gần nhau trong Java source.

## 20. Cách lựa chọn theo mục tiêu nhất quán

| Yêu cầu | Cơ chế nên cân nhắc | Điều không đủ |
|---|---|---|
| Tránh dirty read | Isolation ≥ `READ COMMITTED` theo DB | First-level cache |
| Nhiều SQL SELECT cần cùng snapshot | DB snapshot/isolation phù hợp | Chỉ giữ một managed entity |
| Không ghi đè cập nhật cùng entity | `@Version`, pessimistic lock hoặc SQL atomic | Dirty checking đơn thuần |
| Bảo vệ điều kiện liên hàng | Serializable/locking/control row/constraint theo invariant | Version riêng từng row |
| Email/SKU duy nhất | `UNIQUE` tại DB | `exists` trước insert |
| Không cho số dư âm | CHECK và transaction logic/conditional update | Setter validation ở một code path |
| Lấy lại một managed entity bị stale | `refresh` phù hợp với isolation | Chỉ gọi `find` lần hai |
| Loại bỏ mọi managed state để đọc lại | `clear` + query/context mới có chủ đích | `flush` |
| Lưu các thay đổi pending | Flush + commit transaction thành công | Chỉ flush |
| Hủy thay đổi chưa commit | Rollback transaction | Chỉ clear |
| Đồng bộ sau native/bulk SQL | Refresh/clear/context mới phù hợp | Nghĩ bulk SQL cập nhật Java objects |
| Giảm lỗi lazy loading khi trả API | Fetch plan/DTO và transaction rõ ràng | Giữ Session mở vô hạn |
| Xử lý serialization failure | Rollback và retry transaction mới có idempotency | Retry ngay trong context lỗi |
| Phân quyền cập nhật field | Service/DTO/validation/authorization | Merge một entity từ client bất kỳ |

Một ví dụ chọn cơ chế theo câu hỏi cụ thể:

- “Tại sao trong cùng request tôi đọc lại vẫn thấy tên cũ?” → kiểm tra **managed instance** và SQL log trước.
- “Tại sao hai request cùng sửa giá có thể làm mất update?” → kiểm tra **`@Version`, lock hoặc atomic SQL**.
- “Tại sao báo cáo tổng và chi tiết không khớp?” → kiểm tra **snapshot/isolation của nhiều truy vấn**.
- “Tại sao 2 người đăng ký cùng email?” → kiểm tra **UNIQUE DB và xử lý concurrent insert**.
- “Tại sao transaction SERIALIZABLE bị hủy?” → hiểu **serialization conflict và retry**, không coi mọi abort là lỗi lập trình.

## 21. Bài tập tự luyện

### Bài 1 — READ COMMITTED nhưng find không đổi

~~~java
Account first = em.find(Account.class, 10L);
// Transaction khác sửa account, commit.
Account second = em.find(Account.class, 10L);
~~~

**Câu hỏi:** nếu `first == second` và giá trị không đổi, có thể kết luận database không hỗ trợ READ COMMITTED không?

**Gợi ý:** Không. Hibernate có thể không gửi SQL ở lần `find` thứ hai. Đây là identity map behavior trong persistence context.

### Bài 2 — SQL scalar thấy dữ liệu mới

Transaction A đọc Account#10 balance 100. Transaction B đổi thành 120 và commit. A dùng scalar JPQL query trong PostgreSQL READ COMMITTED và thấy 120, nhưng `a.getBalance()` vẫn 100.

**Câu hỏi:** điều gì đã xảy ra?

**Gợi ý:** Query scalar tạo SQL mới nhìn thấy dữ liệu đã commit mới; managed instance `a` vẫn có state cũ. Phân biệt DB SELECT result với Java entity state.

### Bài 3 — Clear dưới PostgreSQL REPEATABLE READ

Transaction A đọc balance 100, B commit balance 120. A gọi `clear(); find` nhưng tiếp tục thấy 100.

**Câu hỏi:** có phải clear bị lỗi?

**Gợi ý:** Không nhất thiết. Clear đã gỡ cache/context state, nhưng SQL SELECT vẫn bị chi phối bởi snapshot của transaction A ở PostgreSQL REPEATABLE READ.

### Bài 4 — Flush nhưng chưa commit

Transaction A gọi `em.flush()` sau khi update số dư. Transaction B ở READ COMMITTED đọc tài khoản.

**Câu hỏi:** B có chắc thấy số dư vừa update không?

**Gợi ý:** Không. Flush gửi SQL nhưng chưa commit. READ COMMITTED không được đọc thay đổi chưa commit của A.

### Bài 5 — @Version và lost update

A và B đều đọc Product version 3. B commit thành version 4. A cố commit thay đổi version 3 thông qua managed entity.

**Câu hỏi:** cơ chế nào phát hiện conflict?

**Gợi ý:** Optimistic locking qua `@Version` và điều kiện SQL/version. Nó độc lập về mặt khái niệm với first-level cache và mức isolation.

### Bài 6 — Write skew không sửa cùng row

Hai bác sĩ đều đang trực. A kiểm tra có hai người rồi tắt trạng thái trực của bác sĩ 1. B cũng kiểm tra có hai người rồi tắt trạng thái trực bác sĩ 2.

**Câu hỏi:** version riêng từng doctor có chắc ngăn việc không còn ai trực không?

**Gợi ý:** Không. Hai transaction sửa hai row khác nhau. Cần bảo vệ invariant liên hàng bằng một transaction protocol/isolation/lock phù hợp.

### Bài 7 — Merge detached state từ client

Client gửi một entity Account cũ có cả `ownerName` và `balance`, nhưng chỉ muốn sửa tên. Service merge toàn bộ object vào context.

**Câu hỏi:** rủi ro là gì?

**Gợi ý:** Có thể ghi đè balance/field khác bằng giá trị stale hoặc ngoài quyền. Dùng DTO, nạp managed entity và sửa có chọn lọc; cân nhắc version/ETag.

### Bài 8 — Bulk update và cache

Một bulk JPQL UPDATE tăng balance của Account#10. `em.find(Account.class, 10L)` vẫn trả value cũ.

**Câu hỏi:** nên kiểm tra tầng nào đầu tiên?

**Gợi ý:** Kiểm tra context đã managed entity hay chưa và bulk update có tự refresh state không; dùng context mới/refresh/clear có chủ đích.

### Bài 9 — Propagation

Method A mở transaction READ COMMITTED rồi gọi method B có `@Transactional(isolation = SERIALIZABLE)` với propagation REQUIRED.

**Câu hỏi:** SQL trong B chắc chắn dùng SERIALIZABLE không?

**Gợi ý:** Không. B có thể tham gia transaction A đã tồn tại. Isolation không tự đổi trên một transaction chỉ vì method bên trong yêu cầu mức khác.

### Bài 10 — Unique constraint

Hai transaction cùng SELECT kiểm tra `email` chưa tồn tại, rồi cả hai insert. Một developer đề xuất sửa bằng `entityManager.clear()` trước insert.

**Câu hỏi:** giải pháp này có ngăn race condition không?

**Gợi ý:** Không. Clear không tạo constraint và không khóa predicate. Cần UNIQUE DB cùng handling khi concurrent insert.

### Bài 11 — Khi nào dùng pessimistic lock?

Hai worker phải lấy hàng `inventory`, kiểm tra quantity và trừ số lượng trong một thao tác yêu cầu an toàn đồng thời.

**Câu hỏi:** loại cơ chế nào đáng xem xét?

**Gợi ý:** Lock hàng trong cùng transaction, optimistic version + retry, hoặc SQL UPDATE có điều kiện nguyên tử. Chọn theo tần suất xung đột, semantics và database.

### Bài 12 — Rollback không restore Java state

Sau khi cộng balance trên managed Account, transaction rollback vì lỗi FK ở một entity khác. Debugger vẫn thấy balance đã tăng.

**Câu hỏi:** có phải DB rollback thất bại không?

**Gợi ý:** Chưa chắc. Java object vẫn có field đã sửa; rollback DB không đảo ngược setter. Tạo context mới để xác nhận dữ liệu committed tại DB.

### Bài 13 — Serializable và retry

Hai transaction SERIALIZABLE cùng cố sửa một business invariant. Một transaction báo serialization failure.

**Câu hỏi:** vì sao đây không nhất thiết là bug của DB?

**Gợi ý:** DB có thể abort một transaction để chỉ những lịch sử serializable được commit. Cần rollback, mở transaction mới, nạp lại dữ liệu, tính lại quyết định và retry có giới hạn, idempotent.

## 22. Kết luận

Để phân biệt đúng hai lớp quan trọng của Hibernate và cơ sở dữ liệu:

**1. Database isolation** xác định SQL trong transaction nhìn thấy dữ liệu nào từ các giao dịch khác và những lịch sử concurrent nào được phép commit. Các mức `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` là ngôn ngữ thảo luận về visibility/anomalies, nhưng DB implementations có khác biệt thực tế.

**2. Persistence context** xác định entity instances nào đang được Hibernate quản lý; identity map có thể trả lại cùng Java object mà không phát SQL. Dirty checking và flush chuyển những thay đổi managed state thành SQL, nhưng **không thay thế transaction isolation**.

**3. Optimistic/pessimistic locking và constraints** là các cơ chế riêng để phát hiện/chặn tranh chấp hoặc bảo vệ invariants. `@Version` không đồng nghĩa SERIALIZABLE; `UNIQUE` không đồng nghĩa READ COMMITTED; một `PESSIMISTIC_WRITE` không thay thế tất cả predicate/range constraints.

**4. Context state và database state có thể khác nhau.** `refresh`/`clear` giúp kiểm soát state đang managed nhưng không vượt qua DB snapshot. `flush` gửi SQL nhưng không commit; `rollback` hủy DB changes chưa commit nhưng không tự đảo ngược các trường Java.

**5. Transaction boundary là lựa chọn nghiệp vụ.** Khi cần snapshot nhất quán, kiểm soát lost update hoặc bảo vệ bất biến liên hàng, phải chọn mức isolation, lock, version, constraint và chiến lược retry tương ứng. Không thể chỉ đổi một annotation hoặc bật một cache để thay thế thiết kế concurrency.

Cách tự hỏi khi gặp vấn đề là:

> “Lần đọc này có thực sự gửi SQL xuống database không? Nếu có, SQL đang nằm trong transaction với isolation/snapshot nào? Nếu có ghi, cơ chế nào phát hiện conflict hoặc bảo vệ bất biến nghiệp vụ?”

Trả lời ba câu hỏi đó giúp tách các lỗi do **Hibernate giữ entity state cũ** khỏi các hiện tượng **concurrent transaction của database**, từ đó chọn cách sửa đúng tầng mà không làm hệ thống phức tạp hoặc chậm đi không cần thiết.

### Tài liệu chính thức tham khảo

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — persistence context, EntityManager, flush, locks, optimistic versioning và transaction semantics.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/) — persistence context, first-level cache, flushing, locking và concurrency của phiên bản đang sử dụng.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — ví dụ về fetching, managed/detached entities, optimistic/pessimistic locking và bulk updates.
- [JDBC Connection API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html) — các hằng số transaction isolation và contract JDBC.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — cách PostgreSQL triển khai READ COMMITTED, REPEATABLE READ và SERIALIZABLE.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — `@Transactional`, isolation, propagation và transaction proxy.

> Đối với bài toán concurrency, cần kiểm thử tích hợp trên chính DB/dialect/driver sẽ triển khai. Mức cô lập có cùng tên nhưng khác implementation, cộng với persistence context và cache của Hibernate, có thể dẫn đến kết quả khác với suy luận chỉ dựa vào annotation Java.




