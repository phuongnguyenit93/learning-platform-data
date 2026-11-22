# Phân biệt bảo đảm JPA và mức cô lập do cơ sở dữ liệu cung cấp

Khi sử dụng Jakarta Persistence (JPA), ta thường làm việc với entity và `EntityManager` thay vì tự viết từng câu SQL. Điều này giúp quản lý vòng đời object, quan hệ, truy vấn và đồng bộ trạng thái, nhưng **không có nghĩa JPA tự quyết định mức cô lập giao dịch của cơ sở dữ liệu**.

Một đoạn Java có thể sửa cùng một entity một cách hợp lệ:

~~~java
Account account = em.find(Account.class, accountId);
account.withdraw(new BigDecimal("100.00"));
~~~

Tuy nhiên, nếu hai request cùng đọc số dư rồi cùng rút tiền, kết quả đúng hay sai còn phụ thuộc vào **ranh giới transaction, isolation, locking, ràng buộc cơ sở dữ liệu và cách ứng dụng xử lý xung đột**. Dirty checking không tự biến một phép kiểm tra số dư thành thao tác nguyên tử giữa các transaction. Một `@Version` giúp phát hiện một lớp xung đột, nhưng chưa tự bảo vệ mọi bất biến liên quan tới nhiều bản ghi.

Bài học này tách rõ hai câu hỏi:

1. **JPA bảo đảm điều gì ở tầng ánh xạ và quản lý entity?**
2. **Database và transaction manager bảo đảm điều gì về khả năng nhìn thấy dữ liệu, sự xen kẽ giữa các giao dịch và kết quả commit?**

Đây là hai tầng phối hợp với nhau, không thể thay thế cho nhau.

## 1. Bản đồ trách nhiệm: từ object Java đến dữ liệu đã commit

~~~text
┌────────────────────────────────────────────────────────────────┐
│ ỨNG DỤNG JAVA                                                  │
│   Service methods, business rules, DTO, domain operations       │
└──────────────────────────┬─────────────────────────────────────┘
                           │ gọi API
                           ▼
┌────────────────────────────────────────────────────────────────┐
│ JPA / ENTITY MANAGER                                           │
│   - Persistence context, managed identity                       │
│   - Entity mapping và association mapping                       │
│   - Dirty checking, cascade, persist/remove/merge               │
│   - JPQL/Criteria, flush và một số lock mode                     │
└──────────────────────────┬─────────────────────────────────────┘
                           │ SQL / JDBC
                           ▼
┌────────────────────────────────────────────────────────────────┐
│ TRANSACTION MANAGER / CONNECTION                               │
│   - Begin, commit, rollback                                     │
│   - Phối hợp resource-local hoặc JTA                            │
│   - Cấu hình isolation theo môi trường/framework               │
└──────────────────────────┬─────────────────────────────────────┘
                           │ transaction requests
                           ▼
┌────────────────────────────────────────────────────────────────┐
│ DATABASE MANAGEMENT SYSTEM                                     │
│   - MVCC hoặc khóa đọc/ghi                                     │
│   - Isolation, snapshot, lock scheduling, deadlock              │
│   - UNIQUE, FK, CHECK, PK, NOT NULL                             │
│   - SQL execution, commit/rollback, durability                  │
└────────────────────────────────────────────────────────────────┘
~~~

JPA định nghĩa **mô hình lập trình persistence** và các API tương tác với giao dịch, khóa, flush. DBMS thực thi **cơ chế cô lập và tính nhất quán khi nhiều transaction cùng truy cập dữ liệu**. Framework như Spring hoặc container Jakarta EE có thể cung cấp thêm cách khai báo transaction và isolation, nhưng không được coi mọi tính năng của framework là hợp đồng chuẩn JPA.

| Vấn đề | Thành phần chịu trách nhiệm chính |
| --- | --- |
| Một entity có đang managed không? | Persistence context của JPA |
| Cùng ID trong một context có trả cùng managed instance? | JPA identity map |
| Field nào ánh xạ thành cột? | JPA mapping và provider |
| Khi nào dirty state được đồng bộ SQL? | JPA flush rules và provider |
| Khi nào transaction hoàn tất? | Transaction manager và database |
| Giao dịch khác có thấy dữ liệu chưa commit? | DB isolation |
| Hai lần SELECT trong một transaction có thấy cùng snapshot? | DB isolation và cách thực hiện truy vấn |
| Hai bản ghi có được cùng business key? | UNIQUE constraint tại database |
| UPDATE với phiên bản cũ có bị từ chối? | JPA optimistic locking phối hợp SQL/database |
| Hai transaction thay các hàng khác nhau có phá bất biến tổng thể? | Isolation/locking/ràng buộc và thiết kế nghiệp vụ |
| Read replica đã cập nhật ngay sau commit chưa? | Hệ thống replication, không phải JPA |

**Không nên dùng từ “JPA bảo đảm transaction an toàn” mà không nói rõ đang xét tính an toàn nào.**

## 2. Những bảo đảm cốt lõi mà JPA cung cấp

JPA cung cấp các cơ chế tiêu biểu sau:

- **Ánh xạ:** `@Entity`, `@Id`, `@Column`, `@ManyToOne`... mô tả cách entity liên hệ tới bảng và khóa ngoại.
- **Identity trong persistence context:** với cùng một entity identity đã được managed, các lần truy cập trong cùng context nhận cùng managed instance.
- **Vòng đời entity:** new, managed, detached, removed; các API `persist()`, `merge()`, `remove()`, `detach()`.
- **Dirty checking:** thay đổi persistent state của entity managed được đồng bộ theo flush rules.
- **Truy vấn object:** JPQL/Criteria và một số quy tắc tương tác với trạng thái pending.
- **Optimistic locking:** `@Version` và các lock mode tương ứng giúp phát hiện một số cập nhật xung đột.
- **Pessimistic locking API:** yêu cầu khóa đọc/ghi tại database thông qua provider khi được hỗ trợ.
- **Tham gia transaction:** EntityManager có thể tham gia resource-local transaction hoặc transaction được JTA/container quản lý.

JPA **không** mặc nhiên cung cấp:

- Một isolation level chung được áp dụng giống nhau trên mọi DBMS.
- Cách nâng isolation portable bằng một annotation `@Isolation` chuẩn JPA.
- Cơ chế làm mới tất cả managed entity khi giao dịch khác commit.
- Bảo đảm không có phantom/write skew khi database đang ở isolation không đủ mạnh.
- Giao dịch bao trùm email, HTTP call hoặc message broker chỉ vì database transaction đang mở.
- Hợp đồng rằng mọi câu SQL được gửi đúng thứ tự các lời gọi Java.
- Mọi điều kiện nghiệp vụ luôn được giữ chỉ nhờ kiểm tra `if` trên một entity.

Muốn đạt được một bất biến kinh doanh, cần chọn cơ chế thích hợp ở **đúng tầng**.

## 3. Transaction, ACID và isolation

**Transaction** là một nhóm thao tác database được xử lý theo ranh giới bắt đầu, commit hoặc rollback. ACID thường được dùng để mô tả bốn đặc tính:

| Chữ | Tên | Ý nghĩa khái quát |
| --- | --- | --- |
| A | Atomicity | Các thay đổi của một transaction được xác nhận cùng nhau hoặc bị hủy theo khả năng giao dịch của DBMS |
| C | Consistency | Database bảo toàn các ràng buộc và quy tắc được thực thi; ứng dụng vẫn phải thiết kế đúng invariant |
| I | Isolation | Kiểm soát khả năng transaction khác quan sát và tương tác với thao tác đang diễn ra |
| D | Durability | Dữ liệu đã commit được duy trì theo bảo đảm của hệ thống lưu trữ |

Ở đây, **Consistency không có nghĩa database tự biết mọi quy tắc nghiệp vụ**. Nếu luật là “mỗi ca trực cần ít nhất một bác sĩ đang trực”, nhưng schema không có constraint/phương thức khóa thích hợp, database có thể chấp nhận các transaction mà cuối cùng phá luật, đặc biệt ở isolation yếu hơn serializable.

Isolation là thành phần chính của bài. Nó trả lời: khi nhiều transaction chạy đồng thời, chúng được phép nhìn các phiên bản dữ liệu nào và kết quả có thể khác một lịch thực hiện tuần tự tới mức nào?

### Ví dụ thời gian

~~~text
Transaction T1                       Transaction T2
----------------------------------   -----------------------------------
BEGIN                                BEGIN
UPDATE accounts SET balance = ...
-- thay đổi chưa commit             SELECT balance FROM accounts ...
                                     -- có thể thấy giá trị nào?
COMMIT
                                     SELECT balance FROM accounts ...
                                     -- có còn thấy giá trị như trước?
                                     COMMIT
~~~

Hai câu hỏi ở phía T2 phụ thuộc **isolation của database**, không thể trả lời chỉ bằng việc T1 dùng `EntityManager` hay JdbcTemplate.

## 4. Hai cách quản lý transaction với JPA

Trước khi nói tới cô lập, phải xác định transaction nằm ở đâu.

### 4.1. Resource-local transaction

Trong môi trường Java SE hoặc ứng dụng tự quản lý transaction bằng `EntityManager`:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Account account = em.find(Account.class, accountId);
    account.withdraw(new BigDecimal("100.00"));

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Code này giả định `EntityManagerFactory` cấu hình `RESOURCE_LOCAL` và entity `Account` có phương thức `withdraw()`. `EntityTransaction` điều phối transaction của resource tương ứng; nó **không có phương thức chuẩn `setIsolationLevel()`**.

### 4.2. JTA/container-managed transaction

Trong Jakarta EE hoặc một cấu hình JTA phù hợp, transaction thường được quản lý bởi container/transaction manager:

~~~java
@Transactional
public void withdraw(long accountId, BigDecimal amount) {
    Account account = em.find(Account.class, accountId);
    account.withdraw(amount);
}
~~~

Ở đây `@Transactional` có thể là `jakarta.transaction.Transactional` hoặc annotation của framework tương ứng. Cơ chế bắt đầu/kết thúc transaction cần được cấu hình đúng; **không tự gọi `em.getTransaction().begin()` trên JTA-managed EntityManager**.

JTA điều phối ranh giới và khả năng phối hợp resources. Nhưng **JTA không đồng nghĩa SERIALIZABLE isolation**. Isolation của các database connection tham gia transaction vẫn là vấn đề cấu hình của DBMS, datasource, transaction manager và provider.

### 4.3. Spring Data JPA và Spring transaction

Trong Spring:

~~~java
@org.springframework.transaction.annotation.Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    // Nạp managed entities rồi cập nhật trong cùng transaction.
}
~~~

Spring cung cấp propagation, read-only, timeout và isolation attributes tùy transaction manager. Đây là **tính năng của Spring**, không phải annotation chuẩn JPA; các thuộc tính còn có giới hạn áp dụng nếu method tham gia transaction đã mở.

## 5. Flush và commit: hai mốc khác nhau

Giả sử:

~~~java
tx.begin();

Account account = em.find(Account.class, 10L);
account.withdraw(new BigDecimal("100.00"));

em.flush();
// Chưa commit.

tx.commit();
~~~

JPA có thể phát `UPDATE` tại `flush()`, nhưng dữ liệu vẫn nằm **trong transaction chưa commit**.

~~~text
T0: database có balance=500 committed
T1: JPA object trong RAM balance=400
T2: flush -> DB thực thi UPDATE balance=400 trong transaction A
T3: transaction B đọc -> phụ thuộc isolation và lock, không tự thấy 400
T4: commit transaction A -> thay đổi được xác nhận
~~~

| Mốc | JPA object | SQL/database | Transaction khác |
| --- | --- | --- | --- |
| Sau setter | Giá trị mới trong RAM | Có thể chưa UPDATE | Chưa có lý do nhìn thấy giá trị mới |
| Sau flush | Vẫn giá trị mới | SQL đã được đồng bộ theo flush rules trong transaction | Thường không thấy write chưa commit |
| Sau commit | Object vẫn có giá trị đã gán | Thay đổi được xác nhận | Có thể thấy tùy isolation/snapshot/cache |
| Sau rollback | Object Java không tự đảo setter | Database hủy thay đổi của transaction | Thấy trạng thái đã commit trước đó theo góc nhìn của mình |

**Flush không nâng isolation. Commit không tự refresh các object nằm trong một persistence context khác.** Cả hai mệnh đề này rất quan trọng khi đọc log SQL và điều tra dữ liệu stale.

### Provider có thể gửi SQL sớm

`persist()` với `GenerationType.IDENTITY` có thể phải INSERT để lấy khóa ngay trước flush tường minh. `FlushModeType.AUTO` có thể làm provider flush trước truy vấn có liên quan. Nhưng **SQL đã chạy sớm không có nghĩa transaction đã commit** và không làm thay đổi isolation của DB.

## 6. Một mô hình Account có version để thực hành

Ta sử dụng bảng đơn giản:

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_account_balance_nonnegative CHECK (balance >= 0)
);
~~~

Entity:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_name", nullable = false, length = 120)
    private String ownerName;

    @Column(name = "balance",
            nullable = false,
            precision = 14,
            scale = 2)
    private BigDecimal balance;

    @Version
    private Long version;

    protected Account() {
    }

    public Account(String ownerName, BigDecimal balance) {
        this.ownerName = Objects.requireNonNull(ownerName);
        this.balance = Objects.requireNonNull(balance);
        if (balance.signum() < 0) {
            throw new IllegalArgumentException("Balance < 0");
        }
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public Long getVersion() {
        return version;
    }

    public void withdraw(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        BigDecimal next = balance.subtract(amount);
        if (next.signum() < 0) {
            throw new IllegalStateException("Insufficient balance");
        }
        balance = next;
    }

    public void deposit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        balance = balance.add(amount);
    }
}
~~~

Các ví dụ sử dụng mapping với `@Version` để minh họa cơ chế bảo vệ một hàng. Việc dùng `BigDecimal` tránh lỗi làm tròn nhị phân kiểu `double` cho số tiền; một hệ thống tài chính thật còn cần chính sách currency, scale, rounding, định danh nghiệp vụ, đối soát và sổ cái riêng.

## 7. Những hiện tượng đồng thời cần phân biệt

Các thuật ngữ thường gặp:

| Hiện tượng | Ý nghĩa |
| --- | --- |
| **Dirty read** | Đọc được thay đổi của transaction khác **chưa commit**, có thể bị rollback |
| **Non-repeatable read** | Đọc cùng một hàng hai lần trong transaction, giá trị thay đổi do transaction khác commit |
| **Phantom read** | Chạy cùng điều kiện truy vấn, tập hàng thỏa điều kiện thay đổi do transaction khác commit |
| **Lost update** | Một cập nhật ghi đè kết quả của cập nhật khác mà không xử lý xung đột đúng |
| **Write skew** | Hai transaction đọc cùng một điều kiện tổng thể, sửa **những hàng khác nhau** và cùng phá bất biến |
| **Serialization anomaly** | Lịch concurrent không tương đương một thứ tự tuần tự hợp lệ cho các transaction |

Đây là những khái niệm khác nhau. Một mức isolation có thể tránh một số hiện tượng nhưng **không mặc nhiên tránh mọi biến thể của lost update hay write skew**. Phải xem behavior cụ thể của DBMS và loại thao tác.

## 8. Dirty read: thấy dữ liệu chưa commit

Giả sử số dư ban đầu là 500:

~~~text
T1                                      T2
----------------------------------      -----------------------------------
BEGIN                                   BEGIN
UPDATE accounts SET balance=100
WHERE id=10;
-- chưa commit                          SELECT balance FROM accounts
                                        WHERE id=10;
                                        -> Nếu trả 100: dirty read
ROLLBACK
                                        -- T2 đã dùng dữ liệu 100,
                                        -- dù DB cuối cùng vẫn 500.
~~~

Dirty read rất nguy hiểm khi dùng số liệu cho quyết định nghiệp vụ, bởi T2 có thể hành động dựa trên một giá trị **chưa từng được commit**.

### JPA có chống dirty read mặc định không?

Không thể chỉ nói “có” vì gọi query qua JPA. **Database isolation** kiểm soát khả năng đọc uncommitted data. Nhiều DBMS phổ biến không cho dirty read ở mặc định của chúng, nhưng đây không phải một bảo đảm độc lập của persistence context.

Nếu JPA trả một entity đã managed từ trước, ta còn phải phân biệt trường hợp **đọc lại giá trị đang ở RAM** với việc database có cho dirty read hay không. Getter trả giá trị của object managed không nhất thiết đã gửi SELECT.

## 9. Non-repeatable read: cùng một hàng, hai thời điểm

Ví dụ:

~~~text
T1                                             T2
------------------------------------------     ---------------------------
BEGIN                                          BEGIN
SELECT balance FROM accounts WHERE id=10;
-> 500
                                               UPDATE accounts
                                               SET balance=400 WHERE id=10;
                                               COMMIT
SELECT balance FROM accounts WHERE id=10;
-> Có thể là 400 ở READ COMMITTED
COMMIT
~~~

Ở database dùng isolation `READ COMMITTED` theo cách thông thường, mỗi câu SELECT có thể nhìn snapshot committed mới ở thời điểm statement bắt đầu. Vì thế hai câu truy vấn cùng row trong một transaction có thể trả hai giá trị khác nhau.

### Nhưng JPA `find()` hai lần có thể vẫn trả 500

~~~java
Account first = em.find(Account.class, 10L);
// first.balance = 500

// Transaction khác commit balance=400.

Account second = em.find(Account.class, 10L);
System.out.println(first == second); // true trong cùng context
System.out.println(second.getBalance()); // có thể vẫn 500
~~~

Đây là **first-level cache/identity map** của JPA, không phải bằng chứng database đang dùng `REPEATABLE READ`. Persistence context tái sử dụng managed instance cho cùng identity.

Muốn khảo sát isolation, cần thực sự làm database đọc lại, bằng truy vấn phù hợp, `refresh()` hoặc context khác, và vẫn phải xét snapshot của transaction. Không được đo isolation bằng hai getter từ cùng object rồi kết luận.

## 10. Phantom read: tập kết quả của điều kiện thay đổi

Giả sử hệ thống quản lý các đơn đang chờ xử lý.

~~~text
T1                                           T2
----------------------------------------     ------------------------------
BEGIN                                        BEGIN
SELECT COUNT(*) FROM orders
WHERE status='PENDING';
-> 8
                                             INSERT INTO orders(...)
                                             VALUES (...,'PENDING');
                                             COMMIT
SELECT COUNT(*) FROM orders
WHERE status='PENDING';
-> Có thể là 9
COMMIT
~~~

T1 không đơn thuần đọc lại *một hàng* có giá trị bị thay đổi: một hàng **mới xuất hiện trong tập kết quả**. Đây là phantom trong mô hình SQL truyền thống.

**Persistence context không khóa mọi hàng có thể khớp điều kiện ở tương lai.** Việc T1 đang quản lý tám entity Order không ngăn T2 tạo Order thứ chín. Muốn bảo vệ một bất biến trên cả tập kết quả, cần chọn isolation/locking/constraint đáp ứng được yêu cầu.

Một số DBMS dùng MVCC hoặc predicate/range locking để xử lý truy vấn theo các cách khác nhau. Không nên phát biểu rằng mức `REPEATABLE READ` luôn có phantom hoặc luôn không có phantom trên mọi DBMS chỉ dựa vào tên mức isolation.

## 11. Lost update: hai transaction cùng sửa một hàng

Số dư tài khoản 10 là 500. Cả T1 và T2 nạp Account#10 rồi cùng quyết định giảm số dư:

~~~text
T1                                           T2
----------------------------------------     ------------------------------
BEGIN                                        BEGIN
find Account#10: balance=500, version=7
                                             find Account#10:
                                             balance=500, version=7
withdraw(100) -> balance=400
                                             withdraw(200) -> balance=300
flush/commit
UPDATE ... balance=400, version=8
                                             flush/commit
                                             cố UPDATE với version=7
                                             -> optimistic lock conflict
~~~

Nếu không có kiểm soát xung đột, một transaction có thể ghi đè giá trị của transaction kia và gây **lost update**. Tùy DBMS, kiểu UPDATE và isolation, database có thể bảo vệ một số trường hợp nhưng không được dựa vào giả định chung.

### `@Version` giúp gì?

Với:

~~~java
@Version
private Long version;
~~~

provider có thể tạo câu UPDATE có điều kiện:

~~~sql
UPDATE accounts
SET balance = 400.00, version = 8
WHERE id = 10 AND version = 7;
~~~

Nếu không còn hàng nào có `id=10, version=7`, provider biết entity được nạp từ một phiên bản cũ và có thể ném `OptimisticLockException` (hoặc exception tương đương được framework chuyển đổi).

**JPA hỗ trợ optimistic locking, nhưng cơ sở dữ liệu vẫn thực thi câu UPDATE và quyết định kết quả của nó.** Lỗi có thể chỉ xuất hiện ở flush hoặc commit; không phải khi gọi `withdraw()`.

### Một số điều `@Version` không làm

- Không làm entity ở persistence context khác tự cập nhật số dư mới.
- Không bảo vệ mọi nghiệp vụ nhiều hàng nếu mỗi transaction cập nhật những hàng riêng.
- Không tự kiểm tra version của từng hàng trong một bulk JPQL UPDATE thông thường.
- Không bảo vệ dữ liệu bị cập nhật bằng SQL/JDBC bên ngoài mà không tôn trọng cơ chế version tương ứng.
- Không thay thế constraint như `UNIQUE`, `CHECK`, `FOREIGN KEY`.

Do đó **optimistic locking là một lớp kiểm soát cạnh tranh**, không phải tên gọi khác của isolation level.

## 12. Write skew: khi `@Version` trên từng hàng vẫn chưa đủ

Giả sử bệnh viện có hai bác sĩ đang trực: A và B. Luật nghiệp vụ: **phải luôn có ít nhất một bác sĩ trực**.

~~~text
doctors
-----------------------
id | on_call | version
A  | true    | 1
B  | true    | 1
~~~

Hai transaction:

~~~text
T1                                           T2
----------------------------------------     ------------------------------
Đọc A=true và B=true                        Đọc A=true và B=true
Thấy còn B trực, nên cho A nghỉ             Thấy còn A trực, nên cho B nghỉ
UPDATE A: on_call=false                     UPDATE B: on_call=false
COMMIT                                      COMMIT

Trạng thái cuối:
A=false, B=false  --> vi phạm "ít nhất một bác sĩ trực"
~~~

Hai transaction cập nhật **hai hàng khác nhau**, nên `@Version` trên A và B có thể không tạo xung đột trực tiếp. Dưới một số mô hình snapshot isolation, cả hai transaction có thể commit nếu không có cơ chế bổ sung; đây là write skew.

### Các cách bảo vệ invariant tập thể

Tùy database và nghiệp vụ:

1. **SERIALIZABLE isolation** khi DBMS triển khai bảo đảm serializable đúng nghĩa, kèm xử lý serialization failure/retry.
2. **Khóa một hàng chung** đại diện cho ca trực trước khi kiểm tra và sửa, với điều kiện mọi đường ghi tham gia cùng giao thức khóa.
3. **Thiết kế ràng buộc hoặc cấu trúc dữ liệu khác** cho phép DB thực thi invariant.
4. **Thực thi một thao tác nguyên tử** có điều kiện tại DB thay vì chia kiểm tra và ghi giữa nhiều statement, khi logic có thể diễn đạt được bằng SQL.

Đây là lý do câu “entity của tôi có `@Version` nên hệ thống đã serializable” là sai.

## 13. Các mức isolation theo cách nhìn SQL

SQL nêu các mức thường được gọi là `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Tên mức giúp trao đổi, nhưng chi tiết MVCC/locking và ngữ nghĩa mỗi mức **khác nhau giữa DBMS**.

| Mức | Dirty read | Non-repeatable read | Phantom read | Ghi chú |
| --- | --- | --- | --- | --- |
| READ UNCOMMITTED | Có thể | Có thể | Có thể | Một số DBMS thực tế xử lý như mức cao hơn |
| READ COMMITTED | Bị ngăn theo ý nghĩa chuẩn | Có thể | Có thể | Snapshot thường theo từng statement, tùy DBMS |
| REPEATABLE READ | Bị ngăn | Bị ngăn theo ngữ nghĩa mức này | Hành vi phụ thuộc định nghĩa/triển khai | Không tự kết luận ngăn write skew |
| SERIALIZABLE | Bị ngăn | Bị ngăn | Bị ngăn theo tính tương đương tuần tự | Có thể chờ, deadlock hoặc phát sinh serialization failure |

Đây là **bảng định hướng về hiện tượng**, không thay thế tài liệu hệ quản trị cụ thể. Trong một số DBMS, `REPEATABLE READ` dựa trên MVCC snapshot khiến truy vấn lặp lại không thấy phantom theo cách đọc nhất quán, nhưng vẫn có loại anomaly khác. DBMS khác có thể dùng khóa khoảng, khóa next-key hoặc cơ chế riêng.

### Isolation mạnh hơn không có nghĩa giao dịch luôn thành công

Ở `SERIALIZABLE`, database phải bảo đảm kết quả các transaction commit có thể được giải thích theo một thứ tự tuần tự hợp lệ. Một cách thực hiện là **từ chối một transaction** bằng serialization error khi không thể duy trì bảo đảm đó.

Ứng dụng phải chuẩn bị cho trường hợp:

~~~text
BEGIN
SELECT ...
UPDATE ...
COMMIT
--> serialization failure
ROLLBACK / retry trong transaction mới
~~~

Không có lời hứa rằng nâng isolation thì mọi giao dịch đồng thời đều commit thành công mà không chờ hoặc không cần retry.

## 14. MVCC là gì và vì sao ảnh hưởng kết quả SELECT?

**Multi-Version Concurrency Control (MVCC)** là cách nhiều database quản lý các phiên bản hàng để phục vụ đọc/ghi đồng thời. Thay vì bắt mọi SELECT chờ mọi UPDATE, DBMS có thể cho transaction đọc một phiên bản hàng phù hợp với snapshot của nó.

Sơ đồ ý tưởng:

~~~text
Account#10:
    version dữ liệu V1: balance=500, đã commit
    version dữ liệu V2: balance=400, transaction T1 chưa commit
    version dữ liệu V3: balance=300, nếu transaction khác commit sau

Transaction T2 đọc một snapshot hợp lệ
    -> Có thể nhìn V1 dù T1 đã thực thi UPDATE
    -> Không nhất thiết thấy V2 khi T1 chưa commit
~~~

Ở đây, **phiên bản MVCC nội bộ của DBMS** không nhất thiết là cùng một thứ với field `@Version` của JPA:

- MVCC quản lý phiên bản hàng/transaction visibility ở storage engine.
- `@Version` là thuộc tính entity dùng cho optimistic locking do JPA ánh xạ.
- Hai cơ chế có thể phối hợp, nhưng không đồng nghĩa và không dùng chung thuật toán.

Ví dụ ở PostgreSQL, `READ COMMITTED` thông thường dùng snapshot mới theo từng câu lệnh, còn `REPEATABLE READ` dựa trên snapshot transaction; PostgreSQL cũng cung cấp `SERIALIZABLE` dựa trên cơ chế kiểm tra xung đột để ngăn lịch không serializable. Ở MySQL InnoDB, consistent read và locking read có thể có hành vi khác nhau dưới `REPEATABLE READ`. Vì vậy khi thiết kế, cần xem **DBMS, phiên bản, loại câu SQL và kiểu đọc** thay vì chỉ nhìn chuỗi tên isolation.

## 15. First-level cache của JPA không phải isolation của DB

Một persistence context quản lý identity của entity:

~~~java
Account a = em.find(Account.class, 10L);
Account b = em.find(Account.class, 10L);

System.out.println(a == b); // true trong cùng persistence context
~~~

Ngay cả nếu transaction khác commit thay số dư, `a` và `b` vẫn có thể là cùng object với state đã nạp trước đó. Đây là một dạng **stale state trong persistence context**, không phải một câu khẳng định về isolation của SQL.

### Sơ đồ khác biệt

~~~text
T1 / EntityManager A
  Account#10 trong RAM: balance=500
  Database ban đầu:    balance=500

T2 / EntityManager B
  UPDATE Account#10:   balance=400
  COMMIT

T1 gọi lại em.find(Account.class, 10)
  -> có thể trả lại object đang managed, balance vẫn 500
  -> không nhất thiết thực thi SELECT mới
~~~

Muốn phân biệt rõ nguyên nhân:

- **Context stale:** entity đã nạp được tái sử dụng.
- **Snapshot stale:** database transaction đang đọc snapshot cũ.
- **Cache khác stale:** second-level cache, application cache hoặc replica có độ trễ.

Thay `READ COMMITTED` thành `SERIALIZABLE` không tự làm JPA refresh object managed đã giữ trong RAM. Ngược lại, `em.refresh()` cũng không tự nâng isolation của transaction.

## 16. `refresh()` và `clear()` có tác dụng gì khi dữ liệu stale?

Với entity managed:

~~~java
Account account = em.find(Account.class, 10L);
em.refresh(account);
~~~

`refresh()` yêu cầu provider đọc lại persistent state của entity từ database. Nhưng:

1. Giá trị được đọc vẫn chịu isolation và snapshot của transaction hiện tại.
2. Các thay đổi chưa được flush trên object có thể bị ghi đè.
3. Provider có thể phải gửi SELECT và xử lý cache/locking phù hợp.
4. Không nên gọi refresh trên detached entity như thể nó đang managed.

`clear()`:

~~~java
em.clear();
~~~

detach tất cả managed entities khỏi persistence context. Sau đó `find()` có thể nạp object mới, nhưng transaction isolation và các cache khác vẫn có thể ảnh hưởng kết quả.

**Không dùng `clear()` như một thao tác đổi isolation.** Nó không đổi isolation level của connection và không hoàn tác SQL đã flush.

### Vùng đọc theo transaction

Nếu một transaction dùng snapshot lâu dài, clear rồi find lại trong cùng transaction có thể **vẫn đọc phiên bản theo snapshot cũ**. Muốn bắt đầu một góc nhìn mới, đôi khi cần transaction mới chứ không chỉ context mới.

## 17. Flush mode của JPA không phải isolation level

JPA cho phép:

~~~java
em.setFlushMode(FlushModeType.AUTO);
// hoặc:
em.setFlushMode(FlushModeType.COMMIT);
~~~

Cần import `jakarta.persistence.FlushModeType`. Ý nghĩa:

- **AUTO:** provider phải bảo đảm thay đổi pending có thể ảnh hưởng query được phản ánh theo quy tắc JPA; có thể flush trước query.
- **COMMIT:** provider có thể trì hoãn đồng bộ tới commit; tác động của các thay đổi pending đối với kết quả query trước commit có thể không được xác định giống AUTO.

Những thuộc tính này điều chỉnh **khi nào JPA đồng bộ state của chính persistence context**, không điều chỉnh **transaction khác được thấy gì**.

| Khía cạnh | Flush mode | Isolation level |
| --- | --- | --- |
| Tầng quyết định | JPA provider | DBMS/connection/transaction manager |
| Câu hỏi | Query có cần thấy pending changes của context không? | Các transaction khác thấy dữ liệu và xung đột ra sao? |
| Ví dụ | AUTO, COMMIT | READ COMMITTED, REPEATABLE READ, SERIALIZABLE |
| Điều khiển commit? | Không | Không thay thế transaction begin/commit |
| Ngăn dirty read? | Không | Tùy mức isolation |
| Ngăn write skew? | Không | Cần isolation/constraint/locking thích hợp |

Lỗi điển hình là đổi flush mode sang COMMIT vì cho rằng nó làm database “đọc dữ liệu đã commit”; thực ra **đó là hai khái niệm dùng chữ commit ở hai lớp khác nhau**.

## 18. Optimistic locking là gì trong hợp đồng JPA?

JPA cung cấp optimistic locking qua `@Version` và các lock mode như `OPTIMISTIC`, `OPTIMISTIC_FORCE_INCREMENT`.

~~~java
Account account = em.find(Account.class, 10L);
account.withdraw(new BigDecimal("100.00"));
// JPA sử dụng @Version khi ghi thay đổi thích hợp.
~~~

Provider xác định version đã nạp có còn khớp khi UPDATE/DELETE hay không. Nếu không, transaction có thể thất bại vì conflict.

### Yêu cầu kiểm tra version mà không sửa dữ liệu ngay

~~~java
Account account = em.find(
        Account.class,
        10L,
        LockModeType.OPTIMISTIC);
~~~

Hoặc:

~~~java
em.lock(account, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

`OPTIMISTIC_FORCE_INCREMENT` yêu cầu tăng version theo quy tắc locking, có thể hữu ích để điều phối thay đổi của aggregate khi những thành phần khác không tự làm version root tăng theo cách nghiệp vụ cần.

**Thời điểm chính xác version được kiểm tra hoặc tăng có thể ở flush/commit theo provider.** Không suy luận rằng `em.lock(..., OPTIMISTIC)` luôn gửi SELECT/UPDATE ngay.

### Version là một cơ chế hợp tác

Nếu một hệ thống khác chạy:

~~~sql
UPDATE accounts SET balance = 300 WHERE id = 10;
~~~

mà không tuân theo cơ chế version của JPA, các bảo đảm optimistic locking có thể bị phá vỡ. Các đường ghi phải cùng tôn trọng quy ước kiểm tra/tăng version hoặc được bảo vệ bằng cách khác.

## 19. Pessimistic locking: JPA yêu cầu khóa, database thực thi

Khi cần ngăn những giao dịch khác cập nhật một hàng trong khoảng thời gian đọc–sửa–ghi, JPA hỗ trợ:

~~~java
Account account = em.find(
        Account.class,
        accountId,
        LockModeType.PESSIMISTIC_WRITE);
~~~

Thao tác này đòi hỏi transaction phù hợp và provider/DBMS hỗ trợ locking semantics được yêu cầu. Ở một số DBMS, SQL có thể tương tự:

~~~sql
SELECT *
FROM accounts
WHERE id = ?
FOR UPDATE;
~~~

`SELECT ... FOR UPDATE` chỉ là **một dạng triển khai minh họa**, không phải SQL bắt buộc của mọi JPA provider.

### Pessimistic read và write

| Lock mode | Ý định điển hình | Lưu ý |
| --- | --- | --- |
| `PESSIMISTIC_READ` | Bảo vệ việc đọc khỏi một số thay đổi đồng thời | Có thể bị nâng thành lock mạnh hơn tùy DBMS |
| `PESSIMISTIC_WRITE` | Khóa để chuẩn bị cập nhật | Có thể chặn transaction khác đang muốn khóa/ghi |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa bi quan và tăng version với entity versioned theo quy tắc | Không phải lựa chọn mặc định cho mọi lệnh đọc |
| `OPTIMISTIC` | Kiểm tra version thay vì giữ khóa row lâu | Phát hiện conflict ở giai đoạn kiểm tra |

Khóa bi quan thường được giữ cho tới transaction kết thúc theo semantics của DBMS. Nó có thể gây **blocking**, timeout, deadlock hoặc giảm throughput. Vì thế khóa phải được đặt đúng phạm vi và dùng transaction ngắn.

### Khóa một hàng không bảo vệ mọi tập hàng

Nếu invariant là “tổng số đơn đang pending không vượt 100”, `PESSIMISTIC_WRITE` trên **một đơn hàng cụ thể** không tự ngăn transaction khác INSERT một đơn hàng mới. Muốn bảo vệ một điều kiện tập thể, phải khóa một tài nguyên chung có ý nghĩa hoặc dùng isolation/constraint phù hợp.

## 20. Lock scope, timeout và giới hạn portable

JPA có các hint và lock scope nhằm điều khiển khóa trong một số tình huống, nhưng khả năng thực thi phụ thuộc provider/DBMS. Ví dụ:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 3000
);

Account account = em.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

Ví dụ dùng `java.util.Map` và `Map.of()` (Java 9+). Hint timeout ở đây là giá trị millisecond theo quy ước JPA; **provider có thể không hỗ trợ đầy đủ hoặc database không có cơ chế tương ứng**, nên không nên coi đây là SLA chính xác 3 giây trên mọi stack.

Hệ quả cần cân nhắc:

- `LockTimeoutException` có thể xảy ra nếu chỉ statement bị ảnh hưởng trong trường hợp được quy định.
- `PessimisticLockException` có thể xuất hiện khi lock failure khiến transaction phải rollback.
- Database có thể phát deadlock/serialization exception được bọc hoặc chuyển đổi bởi provider/framework.
- Một lock đọc hoặc write trên entity không có nghĩa mọi dòng ở bảng liên quan hoặc mọi row trong association đã bị khóa.
- Các tùy chọn như NOWAIT/SKIP LOCKED hay chi tiết `SELECT FOR UPDATE` là tính năng DBMS/provider, không nên mặc định portable.

Nếu bắt lỗi lock, phải xem **transaction còn dùng được hay đã rollback-only** trước khi thực hiện thao tác tiếp theo. Không tiếp tục ghi trong transaction đã bị DB từ chối.

## 21. Phân biệt `@Version`, khóa row và SERIALIZABLE isolation

Ba kỹ thuật giải quyết những lớp vấn đề khác nhau:

| Kỹ thuật | Cơ chế | Phù hợp | Không tự bảo đảm |
| --- | --- | --- | --- |
| `@Version` optimistic locking | So sánh version khi update | Ít tranh chấp, sửa một entity/aggregate với quy ước version rõ | Invariant trên các hàng không cùng version; bulk/native writes ngoài giao thức |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa tại DB | Tranh chấp ghi cao, cần giữ quyền sửa một hàng khi transaction hoạt động | Predicate/range không được khóa; các đường ghi không tham gia giao thức |
| `SERIALIZABLE` isolation | Chỉ commit những lịch tương đương tuần tự theo DBMS | Invariant cần semantics tuần tự; có thể gồm nhiều query/hàng | Giao dịch không bao trùm hệ thống ngoài DB; không loại bỏ nhu cầu retry |
| UNIQUE/FK/CHECK | Database ràng buộc trạng thái hợp lệ | Dữ liệu phải đúng bất kể nguồn ghi | Các invariant không diễn đạt được bằng constraint đơn giản |

Trong nhiều ứng dụng, cần **kết hợp**:

- Constraint bắt buộc ở database.
- `@Version` cho cập nhật cạnh tranh thông thường.
- Lock theo transaction hoặc SERIALIZABLE cho thao tác không thể bảo vệ bằng một row version.
- Chính sách retry, idempotency và phản hồi conflict.

Không có một annotation JPA duy nhất thay thế mọi thành phần trên.

## 22. JPA không chuẩn hóa cách đặt isolation level của transaction

Trong JDBC, `Connection` có API:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED);
~~~

Đây là **API JDBC**, không phải `EntityManager.setIsolation(...)` chuẩn JPA. Trong ứng dụng quản lý transaction bằng connection pool và framework, việc chỉnh isolation đúng cách thường phải được làm **trước khi transaction bắt đầu** hoặc qua datasource/transaction manager theo quy ước của hạ tầng.

### Ví dụ về Spring

Spring cung cấp:

~~~java
@org.springframework.transaction.annotation.Transactional(
    isolation = org.springframework.transaction.annotation
        .Isolation.SERIALIZABLE)
public void performCriticalOperation() {
    // Dùng JPA trong transaction do Spring quản lý.
}
~~~

Đây là cấu hình **Spring-specific**. Thuộc tính isolation có thể chỉ được áp dụng khi tạo một transaction vật lý mới; nếu method tham gia transaction hiện có với propagation mặc định, isolation thực tế có thể là isolation của transaction đã mở. Cấu hình transaction manager, proxy/self-invocation và database driver cũng quan trọng.

### Ví dụ với Jakarta EE/JTA

`jakarta.transaction.Transactional` không có thuộc tính `isolation` tương ứng với Spring annotation. Nếu cần một mức isolation cụ thể, phải sử dụng cấu hình datasource, transaction manager, database hoặc API hỗ trợ của môi trường đang chạy.

### Tránh chỉnh trực tiếp connection ngoài cơ chế quản lý

Trong ứng dụng JPA có connection pool:

~~~java
Connection conn = ...; // Được quản lý bởi pool/framework.
conn.setTransactionIsolation(...);
~~~

không nên tùy tiện đổi isolation giữa một transaction đã chạy, hoặc bỏ qua việc reset trạng thái connection khi trả lại pool. Nhiều stack có cơ chế bảo đảm reset, nhưng ứng dụng phải tuân thủ contract của pool/transaction manager đang dùng. Việc unwrap raw connection từ EntityManager chỉ để đổi isolation có thể không portable và phá cách framework quản lý resource.

## 23. Isolation mặc định không đến từ JPA

Một hiểu lầm thường gặp là “JPA mặc định READ COMMITTED” hoặc “Hibernate mặc định REPEATABLE READ”. Cách nói chính xác hơn:

**JPA không định nghĩa một isolation level mặc định chung cho mọi ứng dụng.** Giá trị thực tế thường đến từ database, datasource, JDBC driver/connection pool hoặc transaction manager/framework.

Ví dụ môi trường có thể khác nhau:

- PostgreSQL thường dùng `READ COMMITTED` làm isolation mặc định.
- MySQL InnoDB thường dùng `REPEATABLE READ` làm mặc định.
- Một ứng dụng có thể cấu hình pool hoặc transaction manager để dùng mức khác.
- Một transaction riêng có thể bị nâng lên `SERIALIZABLE` cho use case quan trọng.

Các câu trên chỉ minh họa **sự khác nhau giữa hệ quản trị phổ biến**, không phải suy luận được isolation hiện tại chỉ từ tên datasource. Hãy kiểm tra cấu hình và tài liệu của DBMS/driver đang chạy.

### Cách xác nhận

Tùy DBMS, có thể dùng câu SQL kiểm tra transaction/session isolation hoặc truy vấn metadata của connection. Ví dụ PostgreSQL:

~~~sql
SHOW transaction_isolation;
~~~

Đây là cú pháp PostgreSQL. Ở DBMS khác, dùng lệnh tương ứng. Nên xác nhận **trên connection/transaction thật được ứng dụng sử dụng**, không chỉ chạy thủ công trong một client SQL có cấu hình session khác.

## 24. JDBC transaction isolation khác JPA flush mode trong một ví dụ

Giả sử service:

~~~java
em.setFlushMode(FlushModeType.AUTO);

tx.begin();
Account a = em.find(Account.class, 10L);
a.withdraw(new BigDecimal("100.00"));

long total = em.createQuery(
        "SELECT COUNT(x) FROM Account x",
        Long.class)
    .getSingleResult();

tx.commit();
~~~

Tại query, provider quyết định có cần flush những thay đổi pending theo `AUTO` để bảo đảm kết quả JPA được phản ánh đúng quy tắc. Nhưng khi một request khác đọc balance của Account#10, khả năng nhìn thấy 400 trước commit hay không vẫn do **DB isolation**.

Hai chiều điều khiển độc lập:

~~~text
AUTO/COMMIT của JPA
    -> Có thể ảnh hưởng thời điểm đồng bộ SQL bên trong T1.

READ COMMITTED/REPEATABLE READ/SERIALIZABLE của DB
    -> Ảnh hưởng T2 nhìn dữ liệu T1 ra sao và conflict nào có thể xảy ra.
~~~

Không dùng một cấu hình để suy luận cấu hình còn lại.

## 25. Bulk JPQL UPDATE/DELETE bypass trạng thái entity managed

Giả sử:

~~~java
Account account = em.find(Account.class, 10L);
BigDecimal before = account.getBalance();

int count = em.createQuery(
        "UPDATE Account a "
      + "SET a.balance = :balance "
      + "WHERE a.id = :id")
    .setParameter("balance", new BigDecimal("300.00"))
    .setParameter("id", 10L)
    .executeUpdate();
~~~

Bulk JPQL update thao tác lên database theo câu query, không cập nhật field của **từng managed Account instance** như việc gọi setter rồi dirty checking. Sau `executeUpdate()`:

~~~java
System.out.println(account.getBalance());
// Có thể vẫn là giá trị 'before'.
~~~

Thậm chí `@Version` không tự được áp dụng như thao tác update từng entity: bulk DML có quy tắc riêng và thông thường không kiểm tra/tăng version cho từng managed entity.

### Một mẫu phối hợp có chủ đích

~~~java
em.flush(); // Đồng bộ pending managed changes trước bulk.

em.createQuery(
        "UPDATE Account a "
      + "SET a.balance = :newBalance "
      + "WHERE a.id = :id")
    .setParameter("newBalance", new BigDecimal("300.00"))
    .setParameter("id", 10L)
    .executeUpdate();

em.clear(); // Loại managed state có thể stale.
~~~

Đoạn trên chỉ minh họa ranh giới persistence context, **không khuyên dùng bulk update để sửa số dư tài khoản thực**; nghiệp vụ tài chính cần atomicity, concurrency checks và audit phù hợp. `clear()` detach toàn context nên không thích hợp nếu còn entity dirty chưa được xử lý hoặc code cần tiếp tục dùng các managed references cũ.

Với bulk SQL, isolation vẫn do DBMS thực thi; việc clear context **không nâng isolation** và không xử lý write skew.

## 26. Kiểm tra nghiệp vụ trước khi INSERT không thay UNIQUE constraint

Một tình huống phổ biến:

~~~java
boolean exists = em.createQuery(
        "SELECT COUNT(u) FROM UserAccount u "
      + "WHERE u.email = :email",
        Long.class)
    .setParameter("email", email)
    .getSingleResult() > 0;

if (!exists) {
    em.persist(new UserAccount(email));
}
~~~

Hai transaction có thể cùng đọc “email chưa tồn tại” rồi đều INSERT.

~~~text
T1                                      T2
--------------------------------        --------------------------------
COUNT(email) = 0                        COUNT(email) = 0
persist(User(email=x))                   persist(User(email=x))
INSERT email=x                           INSERT email=x
                    UNIQUE(email)
          Một transaction có thể xung đột
~~~

**JPA query kiểm tra trước không tự bảo đảm uniqueness trong concurrent execution.** Nên đặt:

~~~sql
ALTER TABLE user_accounts
ADD CONSTRAINT uq_user_account_email UNIQUE(email);
~~~

Database constraint bảo vệ mọi đường ghi, kể cả JPA, JDBC, migration hoặc dịch vụ khác. Ứng dụng nên xử lý lỗi constraint thành phản hồi phù hợp hoặc thiết kế idempotent insert theo DBMS khi use case yêu cầu.

Một cách ngăn race bằng “kiểm tra rồi insert” chỉ trong transaction không tự đủ nếu isolation/locking không bảo vệ điều kiện “chưa tồn tại”. Predicate locking hay SERIALIZABLE có thể hữu ích, nhưng UNIQUE constraint vẫn thường là lựa chọn trực tiếp và rõ ràng nhất cho một business key.

## 27. Foreign key và CHECK constraint cũng không phải tính năng cô lập của JPA

JPA cho phép metadata:

~~~java
@ManyToOne(optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

Nhưng sự tồn tại thực tế của `FOREIGN KEY(customer_id) REFERENCES customers(id)` phụ thuộc database schema.

Tương tự:

~~~sql
CHECK (balance >= 0)
~~~

có thể bảo vệ bất biến đơn giản ngay cả khi một đường ghi không dùng phương thức `withdraw()` của entity.

Phân biệt:

- **Business validation trong Java:** phản hồi sớm, giải thích lỗi rõ, xây dựng state hợp lệ trong ứng dụng.
- **Constraint trong DB:** lớp bảo vệ cuối cùng cho mọi transaction và đường ghi.
- **Isolation:** điều khiển cách các transaction tương tác với nhau.

Một CHECK constraint trên một hàng có thể ngăn balance âm, nhưng không tự đảm bảo một tổng nhiều hàng hoặc invariant xuyên nhiều bảng. Với invariant phức tạp, cần thiết kế transaction/locking hoặc schema bổ sung.

## 28. Thay quan hệ đúng phía sở hữu không giải quyết mọi tranh chấp

Giả sử:

~~~java
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
~~~

Ở quan hệ hai chiều, field giữ FK là owning side; collection `mappedBy` ở entity Department là inverse side. Để JPA ghi liên kết, cần sửa owning side đúng:

~~~java
employee.setDepartment(newDepartment);
~~~

Nhưng nếu hai transaction đồng thời chuyển cùng Employee sang hai Department khác nhau, **ownership mapping đúng không giải quyết lost update**. Cần thêm version/locking hoặc quy tắc nghiệp vụ.

Một cách tách các vấn đề:

1. **Mapping:** cột FK nào phải đổi?
2. **Persistence context:** entity có managed và dirty không?
3. **Transaction:** SQL đã flush/commit chưa?
4. **Isolation/concurrency:** có transaction khác cùng sửa FK hoặc invariant không?
5. **Constraint:** FK/UNIQUE/NOT NULL có được database bảo vệ không?

Không trộn lỗi “không đổi FK vì chỉ sửa inverse side” với lỗi “hai transaction tranh chấp cùng FK”.

## 29. Isolation và cache ngoài persistence context

Một transaction đã commit thành công nhưng API khác vẫn có thể đọc dữ liệu cũ vì:

- Entity managed trong persistence context dài hạn đang stale.
- Second-level cache/query cache của provider không được invalidation như kỳ vọng.
- Application cache hoặc HTTP cache giữ kết quả cũ.
- Read replica có replication lag.
- Transaction đọc giữ snapshot trước commit.

Những nguyên nhân này thuộc **nhiều tầng** khác nhau, không giải quyết hết bằng một câu `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`.

### Read-your-writes

Trong cùng transaction và connection thích hợp, transaction thường đọc được những thay đổi nó đã thực thi theo semantics DBMS. Nhưng ứng dụng JPA phải nhớ pending state:

- Nếu mới gọi setter, dữ liệu có thể chỉ tồn tại trong RAM.
- JPQL với `AUTO` có thể phản ánh pending changes.
- Native SQL/JDBC qua connection khác không nhất thiết thấy pending SQL chưa flush hoặc write chưa commit.
- Một request tiếp theo đọc **replica** có thể không thấy commit mới ngay nếu replication bất đồng bộ.

Muốn bảo đảm người dùng “ghi xong đọc lại thấy ngay” trong kiến trúc có replica, cần thiết kế **read routing/consistency policy**, không chỉ đặt isolation cho database primary.

## 30. Cách thiết kế thao tác chuyển tiền giữa hai tài khoản

Với mô hình `Account` có balance và version, một service có thể cập nhật hai entity trong cùng transaction:

~~~java
public void transfer(
        EntityManager em,
        long fromId,
        long toId,
        BigDecimal amount) {

    if (fromId == toId) {
        throw new IllegalArgumentException(
                "Hai tài khoản phải khác nhau");
    }

    Account from = em.find(Account.class, fromId);
    Account to = em.find(Account.class, toId);

    if (from == null || to == null) {
        throw new IllegalArgumentException(
                "Không tìm thấy tài khoản");
    }

    from.withdraw(amount);
    to.deposit(amount);
}
~~~

Đoạn này **phải được gọi trong một transaction** quản lý cả hai entity; nó không tự begin/commit. Khi transaction commit thành công, JPA đồng bộ cả hai thay đổi theo quy tắc flush.

### Vẫn còn các câu hỏi thiết kế

1. Nếu hai transfer cùng rút từ một tài khoản, có dùng `@Version` hoặc pessimistic lock không?
2. Khi optimistic conflict xảy ra, có rollback cả transaction không?
3. Nếu dùng retry, có đảm bảo request được thực hiện **một lần theo ý định** và không chuyển tiền hai lần không?
4. Có ghi ledger/audit transaction cùng ranh giới atomically không?
5. Có phép chuyển tiền qua hai database hoặc dịch vụ ngoài phạm vi một transaction không?
6. Có cần order lock theo ID để giảm deadlock?

Trong hệ thống thanh toán thực tế, balance cập nhật trực tiếp không phải mô hình đủ cho kiểm toán; thường cần ledger, idempotency key, trạng thái giao dịch và đối soát. Ví dụ này chỉ minh họa **ranh giới JPA và bảo đảm concurrency của database**.

### Kiểm tra giới hạn business rule

Phương thức `withdraw()` kiểm tra balance trong object managed. Nếu object đó được nạp từ state stale, check có thể vượt qua dựa trên số dư cũ. `@Version` giúp từ chối một số lần ghi cạnh tranh nhưng ứng dụng phải xử lý transaction thất bại thay vì bỏ qua exception.

## 31. Write skew trong chuyển tiền hoặc hạn mức tổng

Giả sử hai tài khoản thuộc cùng một nhóm, với luật:

~~~text
Tổng số dư của nhóm phải luôn >= 100.
~~~

Trạng thái ban đầu:

~~~text
Account A: 100
Account B: 100
Tổng = 200
~~~

T1 đọc cả hai account và rút 80 từ A, vì tổng sau rút dự kiến là 120. T2 cũng đọc cùng snapshot và rút 80 từ B, vì tổng sau rút dự kiến là 120.

~~~text
T1: SELECT A+B = 200        T2: SELECT A+B = 200
T1: UPDATE A = 20          T2: UPDATE B = 20
T1: COMMIT                 T2: COMMIT
Kết quả: A+B = 40  --> vi phạm hạn mức 100
~~~

Mỗi transaction cập nhật một hàng khác nhau. `@Version` của từng Account không nhất thiết phát hiện conflict. Đây là một dạng invariant đa hàng có thể bị phá dưới snapshot isolation nếu không có bảo vệ thích hợp.

### Cách xử lý

- Khóa một **group row** chung trước khi tính tổng và cập nhật, nếu tất cả thao tác cạnh tranh đều khóa đúng row đó.
- Dùng `SERIALIZABLE` và retry khi transaction bị từ chối.
- Chuyển invariant sang một mô hình có row tổng/constraint và thao tác cập nhật nguyên tử nếu nghiệp vụ cho phép.

Đây là bài toán **transaction isolation và thiết kế dữ liệu**, không giải quyết bằng việc gọi `em.flush()` sớm hơn.

## 32. Transaction propagation không đồng nghĩa isolation

Trong Spring, các thuộc tính như `Propagation.REQUIRED`, `REQUIRES_NEW` hoặc `NESTED` liên quan đến **cách method tham gia hoặc tạo transaction**. Trong khi đó, `Isolation.READ_COMMITTED` và `Isolation.SERIALIZABLE` liên quan đến **mức cô lập của transaction với các transaction khác**.

| Thuộc tính | Câu hỏi |
| --- | --- |
| Propagation | Method này dùng chung transaction với caller hay mở transaction mới? |
| Isolation | Transaction nhìn thấy/xung đột với transaction khác theo quy tắc nào? |
| Timeout | Transaction được phép kéo dài tới mức nào theo hạ tầng? |
| Read-only | Gợi ý/thiết lập cho đường đọc và tối ưu tùy framework/DB |
| Rollback rules | Exception nào làm transaction được đánh dấu rollback? |

Ví dụ:

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED)
public void writeAuditRecord(...) {
    // ...
}
~~~

Đây là cú pháp Spring, cần import annotation và enums của Spring. `REQUIRES_NEW` thường mở transaction vật lý riêng và tạm ngưng transaction ngoài khi transaction manager hỗ trợ, nhưng cách này có thể khiến audit record commit **trước** khi nghiệp vụ ngoài rollback. Đó có thể là chủ đích hoặc bug nghiêm trọng tùy yêu cầu.

Không dùng propagation để suy ra rằng isolation đã mạnh hơn; hai thuộc tính độc lập.

### Self-invocation trong Spring

Ở mô hình proxy-based transaction thông thường, một method trong cùng object gọi trực tiếp method được chú thích `@Transactional` có thể **không đi qua transaction proxy**, khiến kỳ vọng về isolation hoặc propagation không được áp dụng. Khi điều tra, phải xác nhận transaction thực sự được tạo, không chỉ nhìn annotation trong source code.

## 33. Read-only transaction cũng không tự định nghĩa isolation

Ví dụ:

~~~java
@Transactional(readOnly = true)
public AccountView getAccount(long id) {
    // Đọc dữ liệu và trả DTO.
}
~~~

Trong Spring, `readOnly = true` có thể ảnh hưởng tới flush mode, connection hoặc gợi ý tối ưu tùy transaction manager/provider. **Nó không phải một chuẩn JPA cam kết mọi write bị database từ chối**, và không đồng nghĩa `REPEATABLE READ` hoặc `SERIALIZABLE`.

Một truy vấn chỉ đọc vẫn có thể thấy dữ liệu cũ, phantom hoặc non-repeatable read theo isolation. Nếu report yêu cầu một snapshot nhất quán cho nhiều câu SELECT, cần chọn transaction/isolation phù hợp, không chỉ đánh dấu read-only.

## 34. Transaction không tự bao trùm email, HTTP và hệ thống ngoài DB

Giả sử:

~~~java
@Transactional
public void approveOrder(long orderId) {
    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
    order.approve();
    emailClient.sendOrderApproved(orderId);
}
~~~

Nếu gửi email thành công rồi database transaction rollback, người dùng có thể nhận email xác nhận cho đơn hàng **chưa được commit**. JPA transaction không tự đảo ngược email đã gửi.

Nếu ứng dụng có nhiều service/database:

- Một DB transaction không tự bao trùm mọi resource ngoài.
- JTA có thể điều phối nhiều XA-compatible resources khi hạ tầng được cấu hình; điều đó **không có nghĩa isolation của mọi resource trở thành SERIALIZABLE**.
- Các HTTP API thông thường không tự tham gia JTA 2PC.
- Với event publishing, có thể dùng **transactional outbox** hoặc cơ chế đảm bảo gửi sau commit/idempotent consumer.
- Với nghiệp vụ kéo dài qua nhiều service, có thể cần saga/compensation thay vì một transaction kéo dài.

### Outbox minh họa

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE orders SET status='APPROVED' WHERE id=...
  INSERT INTO outbox_events(...) VALUES (...)
COMMIT

Process riêng:
  đọc outbox event đã commit
  gửi message
  ghi trạng thái delivered / retry idempotent
~~~

Phương án này giúp trạng thái đơn và ý định gửi event được commit atomically **trong một database**, nhưng việc gửi message vẫn cần thiết kế retry và idempotency. Đây là vấn đề rộng hơn JPA isolation, nhưng rất quan trọng để không phóng đại bảo đảm của một `@Transactional`.

## 35. Serializable transaction vẫn có thể cần retry

Một chiến lược khi invariant phức tạp không thể bảo vệ bằng unique constraint hoặc optimistic version riêng lẻ là dùng SERIALIZABLE transaction.

Pseudo-flow:

~~~text
attempt 1:
    begin SERIALIZABLE
    đọc tập bản ghi
    kiểm tra invariant
    cập nhật
    commit
    -> có thể serialization failure

attempt 2 (transaction mới):
    begin SERIALIZABLE
    đọc lại dữ liệu mới
    kiểm tra lại invariant
    cập nhật
    commit
~~~

**Retry phải lặp lại toàn bộ logic đọc–kiểm tra–ghi trong transaction mới**, không phải chạy lại chỉ câu UPDATE sau khi context đã stale.

### Những lưu ý khi retry

1. Chỉ retry những lỗi được xác định là có thể retry, chẳng hạn serialization conflict/deadlock theo contract của stack.
2. Dùng transaction/persistence context mới; đừng reuse transaction đã rollback.
3. Giới hạn số lần retry và áp dụng backoff/jitter phù hợp khi tải cao.
4. Bảo đảm operation có tính idempotent hoặc có idempotency key nếu bên ngoài cũng có side effect.
5. Không phát email/HTTP event không thể đảo ngược ở giữa mỗi attempt.
6. Kiểm tra kết quả cuối và điều kiện nghiệp vụ trên snapshot mới.

Khi một request rất quan trọng, thất bại do conflict có thể được trả về client để người dùng xác nhận lại, thay vì tự động retry đến khi thắng bằng mọi giá.

## 36. Một thí nghiệm hai EntityManager

Muốn hiểu isolation, nên dùng **hai EntityManager và hai transaction riêng biệt**, không chỉ hai biến trỏ tới cùng managed entity.

Giả sử database đã có Account#10 với balance 500.

### Transaction T1 cập nhật nhưng chưa commit

~~~java
EntityManager em1 = emf.createEntityManager();
EntityTransaction tx1 = em1.getTransaction();

tx1.begin();
Account a1 = em1.find(Account.class, 10L);
a1.withdraw(new BigDecimal("100.00"));
em1.flush();

// Ở thời điểm này T1 có thể đã UPDATE balance=400,
// nhưng transaction chưa commit.
~~~

### Transaction T2 đọc ở context riêng

~~~java
EntityManager em2 = emf.createEntityManager();
EntityTransaction tx2 = em2.getTransaction();

tx2.begin();
Account a2 = em2.find(Account.class, 10L);
System.out.println(a2.getBalance());
// Giá trị hoặc việc chờ lock phụ thuộc isolation và DBMS.
~~~

### Kết thúc theo thứ tự mong muốn

~~~java
try {
    tx2.commit();
    tx1.commit();
} finally {
    if (tx2.isActive()) tx2.rollback();
    if (tx1.isActive()) tx1.rollback();
    em2.close();
    em1.close();
}
~~~

Các đoạn trên minh họa thao tác theo mốc và giả sử không có exception ở phần setup. Trong test thực, phải bao toàn bộ begin/find/flush/commit bằng `try/catch/finally` để rollback và đóng cả hai context khi lỗi.

**Không kết luận từ kết quả một lần chạy rằng mọi DBMS cho kết quả giống vậy**. Có DBMS cho T2 đọc phiên bản committed cũ, có tình huống SELECT bị chờ hoặc thời điểm statement/snapshot khác; cần xác định isolation thực tế.

### Thí nghiệm non-repeatable read chính xác hơn

Để quan sát giá trị SQL, sau T2 đã đọc và trong khi T2 còn mở:

1. T1 thay giá, flush và commit.
2. Trong T2, thực hiện một **truy vấn SQL thực sự mới** hoặc `refresh(a2)` theo semantics transaction.
3. Ghi lại giá trị được đọc và so sánh với lần đầu.
4. Lặp thí nghiệm với các isolation level khác nhau trên DBMS đang dùng.

Chỉ gọi `em2.find(Account.class, 10L)` lần thứ hai có thể trả managed instance mà không SELECT lại, nên không phải phép đo isolation đáng tin.

## 37. Kiểm thử bảo đảm concurrency bằng hai transaction thật

Một unit test chỉ mock `EntityManager.find()` không tạo ra DB lock, MVCC snapshot hoặc constraint violation thực. Với concurrency/isolation, cần **integration test** chạy trên DBMS đủ gần môi trường production.

Các mục cần xác minh:

- Data source của test có isolation giống production không?
- Hai worker/test thread có thực sự dùng **hai connection/transaction riêng** không?
- Có dùng connection pool với số connection đủ cho concurrent test không?
- EntityManager có được chia sẻ giữa các thread không? **Không nên chia sẻ một EntityManager giữa các thread**, vì nó không được thiết kế để dùng concurrently.
- Test có xác nhận ranh giới commit/rollback rõ không?
- Có đo dữ liệu bằng context mới thay vì getter từ entity stale không?
- Conflict được quy về lỗi nào và transaction còn có thể tiếp tục không?

### Định nghĩa kịch bản thay vì dựa vào sleep

Với hai thread, có thể sử dụng `CountDownLatch` hoặc `CyclicBarrier` ở test harness để điều khiển những mốc:

~~~text
T1 đọc xong       ─┐
                   ├─ Barrier: cả hai đã đọc
T2 đọc xong       ─┘

T1 cập nhật       ─┐
                   ├─ Cho cả hai thử flush/commit
T2 cập nhật       ─┘
~~~

Các thí nghiệm lock có thể phải dùng timeout và cơ chế hủy để tránh deadlock test vô thời hạn. Không dùng `Thread.sleep()` tùy tiện rồi giả định scheduler luôn thực hiện đúng thứ tự.

### Test cần xác nhận bất biến cuối cùng

Với số dư:

- Không có balance âm nếu domain cấm.
- Không mất cập nhật khi hai giao dịch cùng rút.
- Conflict được rollback và trả thông báo đúng.

Với lịch bác sĩ:

- Sau mọi transaction commit, vẫn có ít nhất một bác sĩ trực.
- Nếu một transaction bị từ chối do serializable conflict, ứng dụng rollback và có chiến lược retry rõ.

Mục tiêu là **bảo đảm trạng thái cuối**, không phải assert một chuỗi log SQL duy nhất.

## 38. Lỗi phổ biến khi nhầm JPA với DB isolation

| Nhận định sai | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “JPA tự dùng SERIALIZABLE.” | JPA không chuẩn hóa default isolation chung | Isolation đến từ DB/datasource/transaction manager |
| “Có `@Transactional` là không có race condition.” | Transaction boundary không tự chọn mức cô lập đủ mạnh | Xác định anomaly và dùng constraint/lock/isolation |
| “`em.flush()` nghĩa là transaction khác đã thấy dữ liệu.” | Flush chưa commit | Visibility theo isolation và commit |
| “`@Version` ngăn mọi lỗi đồng thời.” | Không bảo vệ mọi invariant đa hàng hoặc bulk/native writes | Bổ sung locking/serializable/constraint |
| “`find()` hai lần cùng giá nghĩa là REPEATABLE READ.” | JPA có identity map | Cần đọc SQL thực sự để kiểm tra isolation |
| “`refresh()` luôn lấy bản mới nhất tuyệt đối.” | Refresh vẫn chịu snapshot/isolation | Xem transaction hiện tại và cache |
| “Đổi flush mode sang COMMIT nâng isolation.” | Flush mode và isolation khác tầng | Cấu hình isolation tại hạ tầng transaction |
| “DB dùng MVCC nên không còn write skew.” | Snapshot isolation có thể cho phép write skew | Dùng serializable hoặc bảo vệ invariant khác |
| “SELECT rồi INSERT là đủ tránh trùng.” | Hai transaction cùng SELECT chưa tồn tại | UNIQUE constraint và xử lý conflict |
| “PESSIMISTIC_WRITE một hàng khóa luôn cả tập truy vấn.” | Row lock không tự khóa mọi predicate/range | Lock tài nguyên chung hoặc isolation phù hợp |
| “JTA có nghĩa mọi resource đều serializable.” | JTA điều phối transaction, không biến isolation của resource | Cấu hình database và XA riêng |
| “Read-only transaction có snapshot ổn định.” | Read-only không tự chọn REPEATABLE READ | Chọn isolation nếu cần báo cáo nhất quán |
| “Commit xong mọi replica đã có dữ liệu mới.” | Replication có thể bất đồng bộ | Chọn read routing/consistency policy |
| “Một transaction DB rollback được email đã gửi.” | Email không tự tham gia transaction | Outbox/idempotency/compensation |
| “Lỗi serialization có thể retry ngay trong transaction cũ.” | Transaction đã thất bại và state có thể stale | Rollback, context mới, thực thi lại cả unit of work |

## 39. Quy trình chọn bảo đảm đúng cho một nghiệp vụ

Khi thiết kế operation ghi, có thể đi theo trình tự:

1. **Viết invariant rõ ràng:** ví dụ “email duy nhất”, “balance không âm”, “chỉ một người giữ chỗ”, “tổng hạn mức không vượt”.
2. **Xác định phạm vi dữ liệu:** một cột/hàng, nhiều hàng trong bảng, nhiều bảng hay nhiều dịch vụ?
3. **Xác định các giao dịch cạnh tranh:** hai người cùng đăng ký, cùng sửa, cùng rút, cùng tạo bản ghi?
4. **Phân tích anomaly có thể xảy ra:** dirty/nonrepeatable/phantom, lost update, write skew, check-then-act race.
5. **Đặt constraint database khi biểu diễn được:** PK, UNIQUE, FK, CHECK và các constraint DB-specific.
6. **Chọn chiến lược entity:** JPA managed entity, `@Version`, owning side/cascade, JPQL bulk hay native SQL?
7. **Chọn isolation và locking:** dùng mức vừa đủ; không nâng lên serializable toàn hệ thống nếu chỉ một use case cần.
8. **Đảm bảo transaction boundary:** bắt đầu trước đọc–kiểm tra–ghi, commit sau khi hoàn thành; tránh gọi dịch vụ chậm trong transaction.
9. **Quy định xử lý conflict:** rollback, retry có kiểm soát hoặc trả thông báo yêu cầu người dùng thử lại.
10. **Kiểm tra cache/replica:** nếu cần read-after-write thì quy định đọc ở đâu.
11. **Test hai hoặc nhiều transaction trên DBMS thực:** assert bất biến cuối cùng và các đường lỗi.
12. **Giám sát production:** thời gian chờ lock, deadlock, serialization failure, optimistic lock conflict, transaction timeout và retry rate.

Một câu hỏi hữu ích xuyên suốt là: **“Cơ chế nào thực sự ngăn lịch thực thi không hợp lệ của hai transaction?”** Nếu câu trả lời chỉ là “vì code Java đã kiểm tra trước”, cần xem lại.

## 40. Bài tập vận dụng

### Bài 1 — Dirty read và flush

T1 nạp Account#10, giảm balance, gọi `em.flush()` nhưng chưa commit. T2 query bằng EntityManager khác. T2 có bắt buộc thấy số dư mới không?

**Gợi ý:** không. Flush không commit; DB isolation/lock quyết định T2 đọc được gì.

### Bài 2 — Hai lần `find()`

Trong cùng một EntityManager, T1 gọi `em.find(Account.class, 10L)` hai lần và luôn thấy cùng balance. Có thể kết luận database đang ở REPEATABLE READ không?

**Gợi ý:** không. First-level cache có thể trả cùng managed instance mà không gửi SELECT mới.

### Bài 3 — Lost update

Hai request cùng nạp Account#10 version 5 và cùng sửa số dư. `@Version` giúp phát hiện điều gì?

**Gợi ý:** một lần ghi dựa trên version cũ có thể bị từ chối; ứng dụng phải rollback và xử lý conflict.

### Bài 4 — Write skew

Hai bác sĩ A và B đều đang trực. Mỗi request thấy người kia còn trực rồi cho một người nghỉ. Vì sao `@Version` riêng trên mỗi Doctor có thể không đủ?

**Gợi ý:** hai transaction sửa hai hàng khác nhau, không conflict trên cùng version; cần bảo vệ invariant tập thể.

### Bài 5 — Kiểm tra email rồi insert

Hai transaction cùng thực hiện `SELECT COUNT(email)` và đều nhận 0. Biện pháp nào chặn database chứa hai user cùng email sau commit?

**Gợi ý:** UNIQUE constraint trên email; xử lý conflict khi một insert thất bại.

### Bài 6 — Đặt isolation trong JPA

Có thể gọi `em.setIsolationLevel(SERIALIZABLE)` bằng API chuẩn JPA không?

**Gợi ý:** không. Phải dùng cấu hình database/datasource/transaction manager hoặc API framework thích hợp.

### Bài 7 — Spring isolation

Một method Spring khai báo `@Transactional(isolation = SERIALIZABLE)` nhưng được gọi khi một transaction READ COMMITTED đã mở. Có thể chắc chắn transaction hiện tại sẽ nâng isolation không?

**Gợi ý:** không. Với propagation tham gia transaction hiện có, isolation được yêu cầu có thể không tạo transaction mới; cần xem transaction manager và cấu hình validation.

### Bài 8 — Read-only

Một report dùng `@Transactional(readOnly = true)` và chạy hai lần COUNT trong cùng transaction. Có mặc nhiên tránh phantom không?

**Gợi ý:** không. Read-only không tự chọn isolation đủ mạnh.

### Bài 9 — Bulk update

JPQL bulk UPDATE đổi balance trong DB, nhưng một managed Account object vẫn hiển thị số cũ. Đặt isolation SERIALIZABLE có làm object tự đổi không?

**Gợi ý:** không. Bulk DML không tự cập nhật managed state; cần refresh/clear hoặc dùng context mới theo yêu cầu.

### Bài 10 — Lock một row

Bạn khóa Account#10 bằng `PESSIMISTIC_WRITE` trước khi cập nhật. Điều đó có ngăn request khác INSERT một bản ghi Order có cùng trạng thái PENDING vào bảng Orders không?

**Gợi ý:** không mặc nhiên. Row lock Account không tự khóa mọi predicate của bảng khác.

### Bài 11 — SERIALIZABLE conflict

Transaction ở SERIALIZABLE thất bại khi commit do serialization anomaly. Có nên gọi lại `em.flush()` trong transaction lỗi và giữ nguyên object cũ không?

**Gợi ý:** không. Rollback, lập transaction/context mới và thực thi lại đọc–kiểm tra–ghi nếu operation an toàn để retry.

### Bài 12 — Read replica

Service cập nhật Account#10 trên primary và commit, nhưng request GET đọc replica vẫn thấy giá cũ. Lỗi này có được khắc phục bằng `em.refresh()` trên replica không?

**Gợi ý:** không bảo đảm. Replication lag và routing là vấn đề kiến trúc ngoài persistence context và isolation của primary.

### Bài 13 — Transaction với email

Ứng dụng commit thất bại sau khi gửi email “đã duyệt đơn”. Có thể dùng một database transaction duy nhất để tự rollback email không?

**Gợi ý:** không. Cân nhắc outbox, gửi sau commit, idempotency và các cơ chế phân tán thích hợp.

### Bài 14 — Bảo vệ bất biến nhiều hàng

Hai tài khoản cùng thuộc một nhóm, luật tổng số dư không dưới 100. Hai transaction cùng đọc tổng 200 rồi rút 80 từ hai tài khoản khác nhau. Constraint `CHECK(balance >= 0)` trên từng hàng có đủ không?

**Gợi ý:** không. Cần bảo vệ invariant tổng bằng serializable, lock chung hoặc mô hình dữ liệu có ràng buộc/thao tác nguyên tử phù hợp.

## Kết luận

**JPA và database isolation giải quyết hai tầng vấn đề khác nhau.** JPA quản lý entity, persistence context, dirty checking, flush, lifecycle, mapping và cung cấp các API optimistic/pessimistic locking. DBMS quyết định transaction nào nhìn thấy phiên bản dữ liệu nào, xử lý lock/xung đột, bảo vệ constraint vật lý và xác nhận hoặc rollback thay đổi.

Một entity managed có thể giữ state mới khi database chưa flush; database có thể đã UPDATE mà chưa commit; một transaction khác có thể tiếp tục đọc snapshot cũ; và cùng một entity đã managed trong context khác có thể không tự refresh. Vì vậy, **flush mode không phải isolation level**, `@Version` không tự biến mọi nghiệp vụ thành serializable, và `@Transactional` không tự loại bỏ tất cả race condition.

Để xây dựng giao dịch đúng, hãy **phát biểu rõ bất biến nghiệp vụ, xác định loại tranh chấp có thể xảy ra, dùng constraint và isolation/locking phù hợp, quản lý transaction thực sự và chuẩn bị xử lý conflict hoặc retry**. Chỉ khi kết hợp đúng các lớp này, ứng dụng JPA mới đạt được tính nhất quán theo yêu cầu thay vì chỉ trông có vẻ đúng khi chạy một request đơn lẻ.
