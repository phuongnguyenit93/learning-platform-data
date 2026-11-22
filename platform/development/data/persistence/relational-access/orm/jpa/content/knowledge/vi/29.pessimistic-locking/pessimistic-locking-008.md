# Giảm bế tắc bằng thứ tự truy cập nhất quán trong khóa bi quan JPA

Khi sử dụng **khóa bi quan** (*pessimistic locking*) trong Jakarta Persistence (JPA), ứng dụng yêu cầu cơ sở dữ liệu ngăn một số thao tác cạnh tranh trên những bản ghi đang được xử lý. Cơ chế này thường hữu ích khi nhiều transaction đồng thời muốn sửa cùng một tập dữ liệu, nhưng cũng có thể tạo **bế tắc** (*deadlock*): transaction A chờ khóa do B giữ, trong khi B lại chờ khóa do A giữ.

Một trong những nguyên tắc thực tiễn quan trọng nhất để **giảm khả năng deadlock** là:

> **Nếu các giao dịch phải lấy nhiều khóa, hãy quy định một thứ tự khóa toàn cục và buộc mọi luồng nghiệp vụ lấy khóa theo đúng thứ tự đó, bất kể thứ tự dữ liệu do người dùng truyền vào.**

Ví dụ, khi chuyển tiền giữa tài khoản #10 và #20, luôn khóa **tài khoản có ID nhỏ hơn trước**, rồi khóa tài khoản có ID lớn hơn. Dù giao dịch chuyển từ #10 sang #20 hay từ #20 sang #10, chúng đều cố lấy khóa #10 trước và #20 sau.

Bài học nằm trong chương **Khóa bi quan** của module **Data Persistence Relational Access ORM JPA**. Nội dung giải thích cách deadlock hình thành, cách chuẩn hóa thứ tự truy cập, thiết kế code JPA dùng `LockModeType.PESSIMISTIC_WRITE`, giao dịch Spring/JTA, xử lý timeout và deadlock victim, nhiều bảng/aggregate, tác động của flush và query optimizer, kiểm thử đồng thời và giới hạn của phương pháp.

**Điểm cần nhớ trước tiên:** Thứ tự truy cập nhất quán giúp *loại bỏ một nguyên nhân deadlock phổ biến* là **đảo ngược thứ tự lấy khóa cùng các tài nguyên**. Nó **không** bảo đảm database không còn bất kỳ deadlock nào, bởi provider, SQL optimizer, foreign keys, indexes, triggers và những transaction khác có thể lấy thêm khóa theo một trình tự ngoài tầm kiểm soát trực tiếp của ứng dụng.

---

## 1. Khóa bi quan và nhu cầu lấy nhiều khóa

Một entity có thể được đọc rồi chỉnh sửa trong một transaction:

```java
Account account = em.find(
    Account.class,
    10L,
    LockModeType.PESSIMISTIC_WRITE
);

account.withdraw(amount);
```

`LockModeType.PESSIMISTIC_WRITE` yêu cầu khóa phù hợp nhằm bảo vệ việc đọc/ghi entity trong transaction trước các giao dịch cạnh tranh. Với nhiều DBMS, SQL phía dưới có thể tương tự `SELECT ... FOR UPDATE` hoặc cơ chế khóa tương ứng.

Nếu nghiệp vụ chỉ sửa **một bản ghi**, việc chờ khóa thường là một chiều: B chờ A giải phóng khóa trên cùng record.

Nhưng nghiệp vụ thực tế thường có **nhiều bản ghi**:

- Chuyển tiền: khóa tài khoản gửi và nhận.
- Chuyển tồn kho: khóa kho nguồn và kho đích.
- Chuyển chỗ ngồi: khóa hai ghế.
- Chuyển trách nhiệm: khóa hai nhóm hoặc hai đơn vị.
- Chuyển đơn hàng: khóa order cùng allocation record.
- Cập nhật quan hệ cha–con: có thể chạm tới parent, children, join table hoặc các ràng buộc liên quan.

Khi cần hai khóa trở lên, **thứ tự lấy khóa** trở thành một phần của thiết kế tương tranh.

### 1.1. Khóa được giữ trong phạm vi giao dịch

Trong một giao dịch bình thường, database giữ những khóa giao dịch cần thiết cho tới khi transaction kết thúc theo quy tắc isolation và loại khóa.

Sơ đồ đơn giản:

```text
BEGIN
   |
   v
LOCK Account#10
   |
   v
LOCK Account#20
   |
   v
Validate + change balances
   |
   v
FLUSH / COMMIT
   |
   v
Database releases transaction locks
```

Đóng Java variable hoặc cho object ra khỏi scope **không tự giải phóng** khóa database. Việc giải phóng phụ thuộc transaction/DBMS. Vì vậy, một transaction có thao tác mạng chậm sau khi đã khóa dữ liệu có thể làm các transaction khác chờ lâu.

### 1.2. Khóa bi quan không phải mutex Java

Một `synchronized` block hoặc `ReentrantLock` chỉ điều phối các thread thuộc phạm vi JVM/process tương ứng. Trong hệ thống nhiều instance, database lock có thể điều phối nhiều application nodes cùng truy cập một database.

Ngược lại, khóa bi quan không thay thế mọi cơ chế đồng bộ trong Java, và không bảo vệ những tài nguyên bên ngoài database nếu chúng không tham gia cùng giao dịch.

## 2. Bế tắc (deadlock) là gì?

Deadlock xảy ra khi một tập giao dịch **chờ lẫn nhau theo vòng kín** và không giao dịch nào trong vòng có thể tiến lên để giải phóng tài nguyên mà giao dịch khác cần.

Ví dụ:

- Transaction A đang giữ khóa tài khoản #10.
- Transaction B đang giữ khóa tài khoản #20.
- A đòi khóa #20, phải chờ B.
- B đòi khóa #10, phải chờ A.

```text
               WAIT-FOR GRAPH

           +------------------+
           | Transaction A    |
           | holds Account#10 |
           +------------------+
                    |
                    | needs Account#20
                    v
           +------------------+
           | Transaction B    |
           | holds Account#20 |
           +------------------+
                    |
                    | needs Account#10
                    v
           +------------------+
           | Transaction A    |
           +------------------+

                     A → B → A
```

Đây là một **vòng chờ**. Database thường có cơ chế phát hiện/giải quyết deadlock (chẳng hạn chọn một transaction làm *deadlock victim* và rollback nó), nhưng chi tiết phụ thuộc hệ quản trị.

### 2.1. Deadlock khác lock wait thông thường

**Chờ khóa đơn giản:**

```text
A holds #10
B waits #10
A commits
B obtains #10
```

B có thể tiếp tục ngay khi A kết thúc. Không có vòng chờ.

**Deadlock:**

```text
A holds #10, waits #20
B holds #20, waits #10
```

Không có giao dịch nào tự giải phóng khóa đang giữ trước khi lấy được khóa tiếp theo. Cần cơ chế phá vòng.

### 2.2. Deadlock khác timeout

**Lock timeout** nghĩa là một thao tác chờ khóa vượt thời gian chờ được áp dụng. Nó có thể xảy ra dù **không có vòng chờ**.

**Deadlock detection** nhận diện vòng phụ thuộc giữa các transaction. Database có thể chủ động rollback một bên mà không cần chờ hết timeout.

| Tình huống | Có vòng chờ? | Kết quả khả dĩ |
| --- | --- | --- |
| B chờ A đang sửa một record | Không | B tiếp tục sau khi A commit hoặc timeout |
| A chờ B, B chờ A | Có | Database phát hiện deadlock, chọn victim |
| A chạy truy vấn rất chậm nhưng không chờ B | Không nhất thiết | Query timeout, không nhất thiết deadlock |
| Nhiều transactions tranh một hot row theo cùng thứ tự | Không tự tạo vòng hai khóa | Lock contention, latency cao |

**Giảm deadlock không đồng nghĩa loại bỏ lock contention hoặc timeout.**

## 3. Mẫu ABBA: nguyên nhân dễ gặp nhất

Giả sử có hai tài khoản:

```text
Account#10: balance = 1,000
Account#20: balance =   500
```

Hai giao dịch:

- A chuyển 100 từ #10 sang #20.
- B chuyển 50 từ #20 sang #10.

Một cách cài đặt dễ gây deadlock là **luôn khóa tài khoản nguồn trước, đích sau**.

### 3.1. Code có rủi ro

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {

    Account from = em.find(
        Account.class,
        fromId,
        LockModeType.PESSIMISTIC_WRITE
    );

    Account to = em.find(
        Account.class,
        toId,
        LockModeType.PESSIMISTIC_WRITE
    );

    from.debit(amount);
    to.credit(amount);
}
```

Ý đồ nghiệp vụ rõ, nhưng thứ tự phụ thuộc vào **vai trò nguồn/đích** của request.

Giao dịch A:

```text
lock #10
lock #20
```

Giao dịch B:

```text
lock #20
lock #10
```

Nếu hai giao dịch xen kẽ đúng thời điểm, vòng chờ xuất hiện.

### 3.2. Timeline cụ thể

| Thời điểm | Transaction A: 10 → 20 | Transaction B: 20 → 10 |
| --- | --- | --- |
| t1 | Khóa #10 | |
| t2 | | Khóa #20 |
| t3 | Chờ khóa #20 do B giữ | |
| t4 | | Chờ khóa #10 do A giữ |
| t5 | **Vòng chờ A ↔ B** | **Vòng chờ B ↔ A** |
| t6 | Database có thể chọn một victim | Transaction còn lại tiếp tục sau khi khóa được giải phóng |

Kết quả cuối có thể đúng sau khi một bên rollback, nhưng request bị lỗi, latency tăng và retry có thể gây tải bổ sung.

### 3.3. Tại sao nghiệp vụ đúng vẫn deadlock?

Cả A và B đều có thể kiểm tra số dư và cập nhật hai tài khoản đúng nếu chạy tuần tự. Deadlock không nhất thiết chứng minh thuật toán debit/credit sai về toán học. Nó là **lỗi phối hợp thứ tự tài nguyên** khi chạy đồng thời.

Vì vậy cần tách:

1. **Invariant nghiệp vụ:** tổng số tiền, số dư không âm, không ghi chuyển tiền hai lần.
2. **Chiến lược khóa:** những record nào phải khóa, theo thứ tự nào.
3. **Transaction policy:** khi nào begin, commit, rollback và retry.
4. **Hiệu năng:** giảm thời gian giữ khóa, tránh hot rows và query không cần thiết.

## 4. Nguyên tắc khóa theo thứ tự toàn cục

Với một nhóm tài nguyên cùng loại và một khóa định danh có thứ tự toàn phần, ví dụ Account ID tăng dần, mọi transaction phải:

1. Xác định **tập ID cần thao tác**.
2. Chuẩn hóa và loại trùng ID.
3. Sắp xếp theo **một quy tắc chung**.
4. Lấy khóa theo thứ tự ấy.
5. Chỉ sau khi lấy đủ khóa, kiểm tra điều kiện nghiệp vụ và cập nhật state.
6. Kết thúc transaction sớm nhất có thể.

Với hai tài khoản:

```text
firstId  = min(fromId, toId)
secondId = max(fromId, toId)
```

Cả hai giao dịch A và B đều thực hiện:

```text
lock #10
lock #20
```

### 4.1. Vì sao loại được vòng ABBA?

Nếu A đã giữ khóa #10, B muốn khóa #10 phải chờ **trước khi có cơ hội lấy #20**.

```text
A: lock #10 -> lock #20 -> commit
B: wait #10 -> lock #10 -> lock #20 -> commit
```

Trong trình tự này, B không giữ #20 để A phải chờ, nên **vòng A↔B trên hai tài khoản đó không hình thành**.

### 4.2. Thứ tự toàn cục không nhất thiết là ID tăng dần

Có thể chọn:

- ID tăng dần.
- ID giảm dần.
- Loại tài nguyên rồi ID.
- Tenant ID, aggregate type, aggregate ID.
- Partition ID rồi record ID.

Điều quan trọng là **mọi code path tuân thủ cùng một quy tắc đã định nghĩa**, chứ không phải chiều tăng hay giảm.

### 4.3. “Toàn cục” quan trọng hơn “nhất quán trong một method”

Nếu method A sắp ID tăng dần nhưng method B trong module khác luôn khóa nguồn trước, hệ thống vẫn có thể tạo ABBA.

Tương tự, nếu Java service dùng quy tắc tăng dần nhưng một stored procedure, scheduler hoặc job ETL khóa theo quy tắc ngược, deadlock vẫn có thể xảy ra.

Quy tắc cần được chia sẻ giữa:

- API requests.
- Scheduled jobs.
- Message consumers.
- Batch processing.
- Native SQL/JDBC paths.
- Stored procedures.
- Dịch vụ khác cùng ghi vào database.

## 5. Mô hình JPA: hai tài khoản và giao dịch chuyển tiền

Để tập trung vào khóa bi quan, ví dụ dùng một entity đơn giản.

### 5.1. Entity Account

```java
package com.example.banking;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    private Long id;

    @Column(nullable = false, length = 3)
    private String currency;

    @Column(
        nullable = false,
        precision = 19,
        scale = 2
    )
    private BigDecimal balance;

    @Version
    private Long version;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public String getCurrency() {
        return currency;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public void debit(BigDecimal amount) {
        requirePositive(amount);

        if (balance.compareTo(amount) < 0) {
            throw new InsufficientFundsException(
                "Insufficient account balance"
            );
        }

        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        requirePositive(amount);
        balance = balance.add(amount);
    }

    private static void requirePositive(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");

        if (amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }
    }

    public static final class InsufficientFundsException
            extends RuntimeException {

        public InsufficientFundsException(String message) {
            super(message);
        }
    }
}
```

`@Version` có thể kết hợp với khóa bi quan để hỗ trợ kiểm soát phiên bản theo JPA, nhưng **mục tiêu bài học không phải bắt exception khóa lạc quan**. Bài này tập trung vào **thứ tự lấy PESSIMISTIC_WRITE locks**. Ngay cả khi entity có `@Version`, các vòng chờ khóa vật lý vẫn có thể xảy ra nếu thứ tự lấy khóa không thống nhất.

### 5.2. DDL minh họa

Ví dụ PostgreSQL:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    currency CHAR(3) NOT NULL,
    balance NUMERIC(19, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_account_balance_nonnegative
        CHECK (balance >= 0)
);
```

Giả sử hai tài khoản đều dùng cùng một currency:

```text
Account#10, USD, 1000.00
Account#20, USD,  500.00
```

Trong thực tế còn cần sổ cái, định danh lệnh chuyển tiền, trạng thái và đối soát. Những phần đó sẽ được thảo luận sau; ví dụ cơ bản chỉ mô tả khóa hai Account.

## 6. Cách sai: khóa theo thứ tự nguồn → đích

```java
public void transfer(
        EntityManager em,
        long fromId,
        long toId,
        BigDecimal amount) {

    Account from = em.find(
        Account.class,
        fromId,
        LockModeType.PESSIMISTIC_WRITE
    );

    Account to = em.find(
        Account.class,
        toId,
        LockModeType.PESSIMISTIC_WRITE
    );

    from.debit(amount);
    to.credit(amount);
}
```

Từ khóa `PESSIMISTIC_WRITE` đã đúng mục tiêu bảo vệ các tài khoản, nhưng **cách chọn thứ tự bằng vai trò from/to** có rủi ro.

### 6.1. Hai request cùng chạy

```text
transfer(10, 20, 100)
transfer(20, 10,  50)
```

Bản thân hai transfer không xung đột về **thứ tự business arguments**, nhưng xung đột về **thứ tự khóa**.

### 6.2. Không chữa bằng sleep()

Một phương án không đáng tin:

```java
Account from = lock(fromId);
Thread.sleep(50);
Account to = lock(toId);
```

Sleep có thể làm **tăng** thời gian giữ khóa đầu tiên và mở rộng cửa sổ deadlock. Nó không tạo ra quy tắc thứ tự chung.

### 6.3. Không chữa bằng tăng lock timeout

Tăng lock timeout có thể khiến các request chờ lâu hơn; nó không loại bỏ vòng chờ. Database deadlock detector vẫn có thể phải rollback victim.

**Sửa thứ tự** là biện pháp cấu trúc đúng cho ABBA. Timeout/retry là cơ chế phục hồi bổ sung.

## 7. Cách đúng: chuẩn hóa thứ tự ID trước khi lấy khóa

Một transaction chuyển tiền giữa hai tài khoản có thể khóa theo ID tăng dần:

```java
long firstId = Math.min(fromId, toId);
long secondId = Math.max(fromId, toId);

Account first = em.find(
    Account.class,
    firstId,
    LockModeType.PESSIMISTIC_WRITE
);

Account second = em.find(
    Account.class,
    secondId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Sau khi lấy đủ hai khóa, mới ánh xạ lại vai trò:

```java
Account from =
    fromId == firstId ? first : second;

Account to =
    toId == firstId ? first : second;
```

Sau đó:

```java
from.debit(amount);
to.credit(amount);
```

**Thứ tự khóa phụ thuộc ID, không phụ thuộc vai trò nguồn/đích.**

### 7.1. Tách rõ “thứ tự khóa” và “hướng chuyển tiền”

Một transfer là quan hệ có hướng:

```text
from -> to
```

Nhưng thứ tự khóa là quy tắc kỹ thuật:

```text
min(ID) -> max(ID)
```

Không được đảo hướng nghiệp vụ chỉ vì sắp khóa. Chuyển từ #20 sang #10 vẫn phải debit #20 và credit #10, dù khóa #10 trước.

### 7.2. Xử lý self-transfer

Nếu `fromId == toId`, hai ID thực ra là cùng một entity. Hãy xác định business rule trước khi lấy khóa:

```java
if (fromId == toId) {
    throw new IllegalArgumentException(
        "Source and destination must differ"
    );
}
```

Không nên lấy hai lần cùng một khóa rồi giả định đó là hai resources khác nhau. Một số nghiệp vụ có thể cho phép chuyển nội bộ cùng tài khoản, nhưng khi ấy cần một nhánh logic riêng, không áp dụng phép debit/credit không có ý nghĩa.

### 7.3. Xử lý ID không tồn tại

`em.find(...)` có thể trả `null` nếu không có entity, không phải mọi tình huống đều tạo khóa trên một entity hợp lệ.

```java
if (first == null || second == null) {
    throw new IllegalArgumentException(
        "Account does not exist"
    );
}
```

Trong transaction, việc một row bị xóa/thay đổi cùng thời điểm còn phụ thuộc isolation/locking semantics của DBMS. Phải có chính sách lỗi phù hợp; không được tiếp tục thao tác trên null.

## 8. Service Java SE resource-local hoàn chỉnh

Đoạn code dưới đây minh họa một đơn vị công việc được quản lý bằng `EntityManagerFactory` và `EntityTransaction`. Mỗi lời gọi tạo transaction riêng, khóa hai tài khoản theo ID rồi mới sửa số dư.

```java
package com.example.banking;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

public final class BankTransferService {

    private final EntityManagerFactory emf;

    public BankTransferService(
            EntityManagerFactory emf) {
        this.emf = Objects.requireNonNull(emf);
    }

    public void transfer(
            long fromId,
            long toId,
            BigDecimal amount) {

        if (fromId <= 0 || toId <= 0) {
            throw new IllegalArgumentException(
                "Invalid account ID"
            );
        }
        if (fromId == toId) {
            throw new IllegalArgumentException(
                "Cannot transfer to same account"
            );
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }

        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                long firstId =
                    Math.min(fromId, toId);

                long secondId =
                    Math.max(fromId, toId);

                // Thứ tự khóa luôn tăng dần ID.
                Account first = em.find(
                    Account.class,
                    firstId,
                    LockModeType.PESSIMISTIC_WRITE
                );

                Account second = em.find(
                    Account.class,
                    secondId,
                    LockModeType.PESSIMISTIC_WRITE
                );

                if (first == null || second == null) {
                    throw new IllegalArgumentException(
                        "Account not found"
                    );
                }

                Account from =
                    fromId == firstId ? first : second;

                Account to =
                    toId == firstId ? first : second;

                if (!from.getCurrency()
                        .equals(to.getCurrency())) {
                    throw new IllegalArgumentException(
                        "Currency mismatch"
                    );
                }

                from.debit(amount);
                to.credit(amount);

                // Đồng bộ thay đổi trong transaction.
                em.flush();

                // Release transaction locks khi DB kết thúc
                // transaction theo semantics tương ứng.
                tx.commit();

            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackEx) {
                        ex.addSuppressed(rollbackEx);
                    }
                }

                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

### 8.1. Các thuộc tính quan trọng

1. Input được xác thực trước khi mở transaction.
2. Không khóa theo `fromId` trước rồi `toId` sau.
3. Hai lời gọi `em.find(..., PESSIMISTIC_WRITE)` diễn ra **tuần tự** theo ID.
4. Vai trò debit/credit được xác định **sau khi** lấy khóa.
5. Không thực hiện network call giữa các lần lấy khóa.
6. `flush()` và `commit()` nằm trong khối có rollback khi lỗi.
7. EntityManager được đóng trong `finally`.

### 8.2. Vì sao không gọi em.flush() giữa hai lần khóa?

Giả sử persistence context đã chứa những thay đổi pending từ trước. Flush hoặc auto-flush có thể thực hiện SQL DML và lấy thêm khóa **trước khi ứng dụng hoàn tất thứ tự khóa dự kiến**.

Một thiết kế tốt là:

```text
Begin transaction
    |
Lock tất cả resources theo thứ tự
    |
Validate state
    |
Apply changes
    |
Flush / commit
```

Đừng thay đổi nhiều entity rồi mới bắt đầu “khóa theo thứ tự” sau đó; lúc ấy transaction có thể đã có khóa từ SQL trước.

### 8.3. Cần kiểm soát số dư và tính idempotent riêng

Code ví dụ đảm bảo một transaction chuyển giữa hai tài khoản theo cách nhất quán trong phạm vi state đang quản lý. Nó **không tự giải quyết**:

- Yêu cầu chuyển tiền bị gửi lặp do client retry.
- Cùng một business transfer được chạy hai lần ở hai request.
- Vấn đề phí, tỷ giá, rounding.
- Ledger postings và audit.
- External payment gateway.
- Quy định pháp lý/đối soát.

Một hệ thống tài chính thực tế phải có **transfer request ID duy nhất** và ledger/constraint phù hợp để chống chuyển tiền lặp. Thứ tự khóa chỉ là một phần của bảo đảm dữ liệu.

## 9. Vì sao khóa tuần tự tốt hơn một query IN có ORDER BY?

Một cách tưởng như tương đương:

```jpql
SELECT a
FROM Account a
WHERE a.id IN :ids
ORDER BY a.id ASC
```

rồi:

```java
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
```

Câu query có `ORDER BY a.id`, nhưng cần phân biệt:

- **Thứ tự các hàng trả về** cho ứng dụng.
- **Thứ tự database thực sự giành các khóa** khi thực thi plan.

Hai điều này **không nhất thiết giống nhau**.

### 9.1. ORDER BY không phải một lock-order guarantee portable

Database optimizer có thể:

- Duyệt index/heap theo một thứ tự khác.
- Thu thập/khóa rows rồi mới sort kết quả.
- Chọn kế hoạch khác tùy statistics/parameters.
- Thêm khóa ở các index/foreign key liên quan.
- Thực hiện SQL lock clause theo cách riêng của DBMS/provider.

Do đó **JPQL ORDER BY không bảo đảm vật lý lock acquisition order** cho một bulk locking query trên mọi DBMS.

### 9.2. Lấy khóa từng ID theo thứ tự đã sắp

Cách điều khiển từ ứng dụng:

```java
for (Long id : sortedIds) {
    Account account = em.find(
        Account.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );
    // Lưu lại account đã khóa.
}
```

Mỗi lời gọi một ID đưa ra một thứ tự yêu cầu rõ ràng hơn. Với mô hình/DBMS phù hợp, nó giảm rủi ro đảo thứ tự khóa root entities so với một query tập hợp.

**Nhưng cũng không phải bảo đảm tuyệt đối:** provider có thể dùng execution strategy riêng, database vẫn có những khóa phụ, triggers, constraints, index locks hoặc lock escalation. Phải kiểm chứng trên hệ quản trị đích.

### 9.3. Khi nào batch locking query phù hợp?

Một query IN với `ORDER BY` có thể giảm round-trips đáng kể khi cần hàng nghìn rows. Nếu buộc phải tối ưu theo cách đó:

- Hiểu chính xác SQL do provider tạo.
- Kiểm tra query plan/lock acquisition behavior của DBMS.
- Đo deadlock rate thực tế.
- Có quy trình rollback/retry.
- Không dùng danh sách đầu vào ngẫu nhiên làm thứ tự ngầm.

Đây là một **trade-off giữa kiểm soát thứ tự và chi phí round-trip**, không nên quyết định chỉ bằng việc query trả rows đã sort.

## 10. Khóa N tài nguyên theo thứ tự nhất quán

Ví dụ xử lý một batch gồm nhiều tài khoản:

```text
Input IDs: [40, 10, 30, 10, 20]
```

Cần:

1. Loại ID null/invalid theo contract.
2. Loại trùng.
3. Sắp xếp.
4. Khóa từng ID theo thứ tự.

```text
Normalized IDs: [10, 20, 30, 40]
Lock sequence:   10 → 20 → 30 → 40
```

### 10.1. Helper Java

```java
import jakarta.persistence.*;
import java.util.*;

public final class OrderedAccountLocker {

    public Map<Long, Account> lockAll(
            EntityManager em,
            Collection<Long> requestedIds) {

        Objects.requireNonNull(em);
        Objects.requireNonNull(requestedIds);

        List<Long> ids = requestedIds.stream()
            .map(id -> Objects.requireNonNull(
                id, "Account ID must not be null"
            ))
            .distinct()
            .sorted()
            .toList();

        Map<Long, Account> locked = new LinkedHashMap<>();

        for (Long id : ids) {
            Account account = em.find(
                Account.class,
                id,
                LockModeType.PESSIMISTIC_WRITE
            );

            if (account == null) {
                throw new IllegalArgumentException(
                    "Account missing: " + id
                );
            }

            locked.put(id, account);
        }

        return locked;
    }
}
```

Cần các classes Account/EntityManager đã được định nghĩa. Helper **không begin/commit transaction**: caller phải sở hữu một transaction đang hoạt động phù hợp, để tất cả locks cùng sống tới cuối đơn vị công việc.

### 10.2. Vì sao distinct() cần thiết?

Nếu input chứa ID lặp, khóa cùng record thêm lần nữa thường không đem lại lợi ích, nhưng có thể:

- Làm code khó theo dõi.
- Làm sai logic nghiệp vụ nếu “mỗi phần tử input” lại bị hiểu thành một resource duy nhất.
- Tăng số thao tác/provider calls.

**Loại trùng khóa** không đồng nghĩa **loại trùng nghiệp vụ**. Nếu một lệnh batch có hai dòng cùng account ID và mỗi dòng mang một giá trị cần áp dụng, phải cộng/tổng hợp/chỉ định ngữ nghĩa business riêng, không tự bỏ bớt những giao dịch hợp lệ.

### 10.3. Vì sao sorted() phải ổn định?

Với `Long`, comparator tự nhiên tạo thứ tự rõ. Với composite key hoặc UUID, phải quy định comparator ổn định và giống nhau giữa tất cả services.

Không dựa vào:

- Thứ tự HashMap/HashSet iteration.
- Thứ tự JSON array từ client.
- Thứ tự database tự trả khi không có ORDER BY.
- Thứ tự “dòng được chọn trước” theo tình huống nghiệp vụ.

### 10.4. Nếu có nhiều tenant?

Một ID có thể chỉ duy nhất trong phạm vi tenant. Khóa tài nguyên cần được xác định bằng **định danh đủ đầy**:

```text
(tenantId, accountId)
```

Quy tắc có thể là sort theo tenantId, sau đó accountId. Quan trọng hơn: truy vấn và authorization phải lọc đúng tenant; sắp thứ tự không thay thế kiểm tra phân quyền hoặc chống truy cập chéo tenant.

## 11. Thứ tự toàn cục khi có nhiều loại entity

Nghiệp vụ chuyển kho có thể cần:

- `Warehouse`.
- `InventoryBalance`.
- `Reservation`.
- `Order`.
- `AuditLog`.

Chỉ sort IDs trong từng loại entity chưa đủ nếu các use cases lấy **khóa khác loại theo thứ tự ngược**.

Ví dụ:

```text
Transaction A:
  lock Warehouse#1
  lock InventoryBalance#10

Transaction B:
  lock InventoryBalance#10
  lock Warehouse#1
```

Dù mỗi loại có duy nhất một ID, vẫn có vòng ABBA vì **thứ tự giữa các loại** không thống nhất.

### 11.1. Quy định thứ tự theo loại, rồi theo ID

Một chính sách ví dụ:

```text
1. Warehouse (sorted by warehouseId)
2. InventoryBalance (sorted by warehouseId, productId)
3. Order (sorted by orderId)
4. Reservation (sorted by reservationId)
```

Mọi transaction có thể chạm tới những resource này cần tuân theo thứ tự tương thích.

Lưu ý: bảng chính sách trên là một **quy ước thiết kế của ví dụ**, không phải thứ tự do JPA quy định. Hệ thống thực tế phải tự xác định các nhóm tài nguyên và đường đi update.

### 11.2. Tài nguyên nhiều khóa composite

Nếu một inventory balance được định danh bằng:

```text
(warehouseId, productId)
```

thì thứ tự nhất quán là:

```text
compare warehouseId, then productId
```

Không dùng kiểu so sánh bất ổn như `key.toString()` nếu representation khác nhau giữa các service/language.

### 11.3. Tránh khóa vòng ngược do workflow tầng cao

Giả sử `OrderConfirmationService` khóa Order rồi Inventory, nhưng `InventoryAdjustmentService` khóa Inventory rồi Order. Hai giao dịch đối nghịch có thể tạo deadlock.

Khắc phục không chỉ là sửa một method. Cần thống nhất:

- Quy tắc cấp ứng dụng.
- Các query trong repository.
- Stored procedures và triggers.
- Batch jobs.
- Thời điểm flush.
- Thứ tự tạo/cập nhật các bản ghi bổ sung.

## 12. Không giữ khóa trong lúc làm việc ngoài database

Một lỗi phổ biến:

```text
BEGIN
LOCK Account#10
Call external currency API (500 ms)
LOCK Account#20
Call notification service (800 ms)
UPDATE + COMMIT
```

Trong 1,3 giây gọi mạng, khóa đầu tiên vẫn có thể được giữ và các transaction khác phải chờ.

### 12.1. Di chuyển công việc chuẩn bị ra trước khi khóa

```text
Validate input
Compute amount / currency rules
Call read-only external services if truly required
BEGIN
LOCK #10
LOCK #20
Check latest balances / invariants
Update both accounts
COMMIT
Send notification asynchronously after commit
```

Những kiểm tra phụ thuộc vào dữ liệu **có thể thay đổi** (ví dụ available balance) vẫn phải được xác nhận **sau khi khóa** chứ không chỉ dựa vào snapshot trước đó.

### 12.2. Ngoại tác không rollback theo database

Nếu gọi payment gateway hoặc gửi email bên trong transaction rồi deadlock victim bị rollback, external side effect có thể đã xảy ra.

Các giải pháp có thể gồm:

- Transactional outbox.
- Idempotency key.
- Workflow trạng thái/pending.
- Saga khi cần điều phối nhiều hệ thống.

**Giảm deadlock bằng thứ tự khóa không bảo vệ ứng dụng khỏi side effect bị lặp hoặc không thể rollback.**

### 12.3. Thời gian giữ khóa

Từ khi lấy khóa đầu tiên tới khi commit/rollback, tránh:

- Network I/O dài.
- File I/O không cần thiết.
- Vòng lặp tính toán nặng.
- Đợi tương tác người dùng.
- Sleep/backoff.
- Rendering/serialization response.
- Đọc dữ liệu không cần thiết.

**Lấy khóa càng muộn khi còn an toàn và kết thúc transaction càng sớm khi hoàn tất công việc** là một nguyên tắc bổ sung cho thứ tự khóa.

## 13. Auto-flush có thể làm lệch thứ tự dự kiến

JPA persistence context có cơ chế dirty checking. Ở `FlushModeType.AUTO`, một số thao tác query có thể khiến provider tự flush các thay đổi pending khi cần.

Ví dụ:

```java
Account a = em.find(Account.class, 20L);
a.credit(amount);

// Sau đó mới cố lock #10 và #20 theo thứ tự.
Account first = em.find(
    Account.class,
    10L,
    LockModeType.PESSIMISTIC_WRITE
);
```

Nếu transaction đã thực hiện DML cho #20 trước khi lấy khóa #10, chiến lược “luôn khóa #10 trước” **không còn được thực hiện trên toàn bộ các khóa đã lấy**.

### 13.1. Quy tắc “lock before mutate”

Khi dùng thứ tự khóa rõ ràng, nên:

```text
Determine IDs
    |
Sort IDs
    |
Acquire pessimistic locks in order
    |
Validate latest state
    |
Mutate managed entities
    |
Flush once as needed
    |
Commit
```

Không sửa các entities trong cùng lock domain trước khi khóa đủ những resources mà thao tác sẽ phụ thuộc.

### 13.2. Flush order vẫn có thể khác thứ tự Java setters

Ngay cả khi gọi:

```java
account10.debit(...);
account20.credit(...);
```

provider có thể batch hoặc sắp xếp SQL UPDATE theo cơ chế riêng. Việc thay đổi Java objects theo một thứ tự **không phải bảo đảm thứ tự JDBC statements**.

Lấy khóa **trước khi mutate**, theo global order, giúp kiểm soát thứ tự khóa trên các row chính hơn là cố đoán provider flush order.

### 13.3. Query chính nó có thể kích hoạt SQL phụ

Đọc entity có EAGER relationships, triggers hay database constraints có thể đụng thêm rows/indexes. Điều này giải thích vì sao các nguyên tắc thứ tự ở application chỉ **giảm**, chứ không thể loại bỏ deadlock ở mọi mức.

## 14. Vì sao không thể hứa “zero deadlock”?

Ngay cả khi mọi code path do team sở hữu đều cố sắp khóa theo ID tăng dần, deadlock vẫn có thể xuất hiện do những nguồn khóa khác.

### 14.1. SQL optimizer và kế hoạch truy vấn

Một câu:

```sql
UPDATE accounts
SET balance = ...
WHERE id IN (10, 20);
```

không có nghĩa database lấy tất cả row/index locks theo thứ tự `10 → 20`. Execution plan có thể thay đổi theo statistics/indexes.

### 14.2. Index và secondary structures

UPDATE một cột được index có thể cần khóa hoặc cập nhật nhiều cấu trúc index. Hai transaction đang làm việc với các rows khác nhau vẫn có thể tranh chấp ở index pages hoặc các cấu trúc metadata tùy DBMS.

### 14.3. Foreign keys và constraints

INSERT/UPDATE bảng child có thể phải kiểm tra FK tới parent. Những khóa liên quan tới ràng buộc có thể tham gia wait-for graph ngoài các entity được code Java khóa trực tiếp.

### 14.4. Triggers và stored procedures

Một trigger tự cập nhật bảng khác có thể lấy khóa theo thứ tự không tương thích với application. Thứ tự khóa toàn cục phải tính đến những writer ở phía database.

### 14.5. Lock escalation

Một số DBMS có thể nâng phạm vi khóa từ nhiều row/page lên cấp lớn hơn tùy tải. Điều này tạo contention mới mà thứ tự ID không diễn tả đầy đủ.

### 14.6. Range/predicate locks

Ở những isolation levels/DBMS nhất định, truy vấn theo khoảng hoặc điều kiện có thể lấy thêm locks để bảo vệ range/predicate. Thứ tự các entity IDs không đủ mô tả toàn bộ tài nguyên đó.

### 14.7. Concurrent DDL/maintenance

Schema migrations, index maintenance hoặc thao tác quản trị có thể tạo những loại khóa không được một transfer service tính đến.

### 14.8. Vì sao vẫn nên làm?

Vì **ABBA do đảo thứ tự khóa** là một nguyên nhân deadlock phổ biến, dễ hiểu và dễ sửa. Global order loại bỏ một nguồn vòng chờ cụ thể trên các resources đã được kiểm soát. Những deadlock còn lại được xử lý bằng quan sát DBMS, transaction rollback và thiết kế bổ sung.

## 15. PESSIMISTIC_READ, PESSIMISTIC_WRITE và PESSIMISTIC_FORCE_INCREMENT

JPA có các lock modes bi quan:

```java
LockModeType.PESSIMISTIC_READ
LockModeType.PESSIMISTIC_WRITE
LockModeType.PESSIMISTIC_FORCE_INCREMENT
```

### 15.1. PESSIMISTIC_READ

Yêu cầu bảo vệ việc đọc entity theo semantics của pessimistic read lock. Chi tiết lock vật lý và khả năng coexist với các locks khác phụ thuộc DBMS/provider.

Ví dụ:

```java
Account account = em.find(
    Account.class,
    10L,
    LockModeType.PESSIMISTIC_READ
);
```

### 15.2. PESSIMISTIC_WRITE

Yêu cầu khóa để bảo vệ thao tác đọc/ghi với ý định cập nhật:

```java
Account account = em.find(
    Account.class,
    10L,
    LockModeType.PESSIMISTIC_WRITE
);
```

Đây là mode chính trong ví dụ chuyển tiền.

### 15.3. PESSIMISTIC_FORCE_INCREMENT

Tương tự yêu cầu khóa bi quan với ý định cập nhật và thêm semantics **force increment version** khi entity có version phù hợp.

```java
Account account = em.find(
    Account.class,
    10L,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

Đừng dùng force-increment chỉ để chống deadlock; nó có thể tạo thêm writes/version changes. Chọn mode theo mục tiêu bảo vệ dữ liệu, sau đó quản lý thứ tự khóa.

### 15.4. Lock mode không thay thế global order

Dù dùng `PESSIMISTIC_READ` hay `PESSIMISTIC_WRITE`, nếu transaction A lấy resource X rồi Y trong khi B lấy Y rồi X, một số kết hợp khóa hoặc chuyển đổi khóa (*lock upgrade*) vẫn có thể dẫn tới deadlock.

Thứ tự và loại khóa là **hai chiều thiết kế khác nhau**.

## 16. Lock upgrade và chiến lược đọc trước, ghi sau

Một tình huống:

```text
Transaction A:
  read-lock #10
  read-lock #20
  later request write-lock #10

Transaction B:
  read-lock #10
  read-lock #20
  later request write-lock #10
```

Hai transaction cùng giữ shared/read locks có thể gây vòng chờ khi cùng cố nâng lên write/exclusive lock, tùy DBMS và semantics lock.

### 16.1. Khóa phù hợp từ đầu

Nếu đã biết nghiệp vụ sẽ sửa các rows, thường nên lấy `PESSIMISTIC_WRITE` theo thứ tự nhất quán ngay từ giai đoạn khóa, thay vì lấy read locks rồi nâng cấp hàng loạt sau đó.

### 16.2. Không dùng write lock quá rộng

Điều ngược lại cũng quan trọng: không khóa ghi toàn bộ danh sách entity chỉ vì muốn đọc. Write locks có thể giảm concurrency.

Quyết định:

- Chỉ đọc nhất quán → xem isolation và read lock.
- Sẽ cập nhật → cân nhắc write lock phù hợp.
- Cần kiểm tra rồi cập nhật nhiều rows → lấy những locks thực sự bảo vệ invariant, theo thứ tự chung.

## 17. Thứ tự khóa khi tạo mới và khi xóa

Không phải mọi tài nguyên cần khóa đã tồn tại sẵn.

Ví dụ nghiệp vụ tạo Reservation mới có thể:

1. Khóa Product.
2. Kiểm tra tồn.
3. Insert Reservation.
4. Update Inventory.
5. Ghi Audit.

INSERT và DELETE có thể lấy thêm khóa ở indexes/FKs ngay cả khi app chưa `find(..., PESSIMISTIC_WRITE)` được một row mới.

### 17.1. Quy tắc với entity đã tồn tại

Nếu có root entities cần bảo vệ, lấy khóa theo thứ tự quy định **trước khi** tạo/xóa child entities phụ thuộc, nếu semantics cho phép.

### 17.2. Quy tắc cho thao tác DML bổ sung

Thiết kế thứ tự toàn cục nên bao gồm cả những bảng mà DML thực sự sẽ tác động. Không chỉ đếm explicit pessimistic lock API calls.

Ví dụ:

```text
1. Lock Warehouse
2. Lock Product / InventoryBalance
3. Validate
4. Insert Reservation
5. Insert Audit
6. Commit
```

Nếu một batch job lại:

```text
Insert Audit
Lock InventoryBalance
Lock Warehouse
```

và Audit insert gây khóa FK/index phụ thuộc, có thể tạo nguồn contention/vòng chờ khác.

### 17.3. Không thể locking một hàng chưa tồn tại bằng find()

`em.find(Entity.class, id, PESSIMISTIC_WRITE)` trả `null` khi entity không tồn tại. Trong một số use cases, cần bảo vệ việc **không tồn tại** (ví dụ “chỉ tạo một reservation duy nhất”). Row lock trên record chưa có không đủ.

Cần thêm:

- Unique constraint.
- Isolation/range locking phù hợp.
- Lock một aggregate/root hiện có.
- Atomic INSERT với xử lý conflict.
- Advisory lock DBMS-specific nếu thực sự phù hợp.

Thứ tự khóa giải quyết một lớp vấn đề; tính duy nhất khi insert là một bài toán riêng.

## 18. Lock timeout và deadlock handling trong JPA

Pessimistic locking có thể ném các ngoại lệ như:

- `jakarta.persistence.PessimisticLockException`.
- `jakarta.persistence.LockTimeoutException`.
- `jakarta.persistence.PersistenceException` hoặc ngoại lệ do framework/provider bọc.
- Một `RollbackException` khi transaction fail ở commit.

### 18.1. PessimisticLockException

Theo contract JPA, `PessimisticLockException` liên quan tới trường hợp pessimistic locking failure dẫn đến **transaction-level rollback**.

Không tiếp tục commit transaction đã lỗi theo kiểu này.

### 18.2. LockTimeoutException

`LockTimeoutException` mô tả trường hợp lock failure áp ở **statement-level rollback** theo JPA. Nó có thể không tự đánh dấu toàn bộ transaction rollback-only theo semantics tương ứng.

Tuy nhiên, không được suy:

> “Cứ bắt LockTimeoutException là có thể tiếp tục mọi workflow trong cùng transaction.”

Vì:

- Hệ quản trị và provider có thể áp trạng thái transaction khác theo lỗi thực tế.
- Đơn vị công việc có thể đã có state/locks khác và không còn phù hợp business invariant.
- Framework transaction rules có thể đánh dấu rollback nếu exception lan ra khỏi interceptor.
- Một số lỗi vendor được bọc khác với ngoại lệ JPA được kỳ vọng.

**Chính sách an toàn cho nghiệp vụ chuyển tiền nhiều hàng là rollback toàn bộ attempt thất bại rồi quyết định retry trong transaction mới.**

### 18.3. Lock timeout hint

JPA có hint chuẩn dạng:

```java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.lock.timeout",
    1000
);

Account account = em.find(
    Account.class,
    10L,
    LockModeType.PESSIMISTIC_WRITE,
    properties
);
```

Giá trị thường được biểu diễn bằng **milli-giây** theo contract JPA hint, nhưng **hỗ trợ áp dụng chính xác hoặc bỏ qua hint phụ thuộc provider/DBMS**. Không nên coi `1000` là thời gian chờ tuyệt đối luôn đúng trong mọi môi trường.

Đoạn ví dụ cần `java.util.Map` và Jakarta Persistence imports, và caller phải có transaction phù hợp.

### 18.4. Timeout không thay thế thứ tự khóa

Nếu deadlock vẫn tồn tại, tăng timeout chỉ làm độ trễ hoặc thời gian chờ của một số trường hợp tăng. Phải ưu tiên sửa lock order và giảm lock hold time.

## 19. Xử lý deadlock victim và retry

Ngay cả khi đã áp global order, vẫn cần chính sách phục hồi vì:

- DBMS có thể còn khóa phụ.
- Stored procedure/trigger có thể dùng thứ tự khác.
- Query optimizer có thể đổi execution plan.
- Có thể có nhiều use cases chưa tuân thủ cùng chính sách.

Khi database chọn một deadlock victim, **transaction của victim bị rollback hoặc không còn có thể commit** theo quy tắc database/driver. Ứng dụng cần nhận diện lỗi, rollback/để transaction manager xử lý, rồi cân nhắc retry.

### 19.1. Retry toàn bộ đơn vị công việc

Không chỉ retry:

```java
em.find(Account.class, secondId, PESSIMISTIC_WRITE);
```

ngay trong transaction đã lỗi. Phải retry:

```text
New transaction
  -> Determine resource IDs
  -> Lock in global order
  -> Re-check balances and business rules
  -> Apply all modifications
  -> Flush/commit
```

### 19.2. Không đồng nhất mọi ngoại lệ khóa là deadlock

`PessimisticLockException`, `LockTimeoutException` và một số vendor exceptions có semantics khác nhau. Một deadlock có thể được bọc trong `PersistenceException` hay Spring `DataAccessException`. Cần phân loại **theo provider/driver/DBMS cụ thể**, có kiểm thử, không chỉ dựa vào một tên class.

### 19.3. Không retry vô hạn

Một policy có thể cho tối đa vài attempts, với backoff/jitter ngoài transaction. Nhưng nếu hot row liên tục bị tranh chấp, nhiều retries có thể làm hệ thống nghẽn thêm.

### 19.4. Idempotency trước retry chuyển tiền

Đây là điểm quan trọng nhất trong nghiệp vụ tài chính:

Nếu client không chắc request đầu tiên đã commit hay chưa do mất kết nối đúng lúc phản hồi, retry mà không có **idempotency key** có thể chuyển tiền hai lần.

Mỗi business transfer nên có một request/transfer ID duy nhất được bảo vệ bởi DB constraint và quản lý cùng transaction/ledger.

Deadlock victim thường rollback, nhưng một cơ chế retry tổng quát không nên nhầm trường hợp **đã chắc rollback** với trường hợp **commit outcome không xác định**.

## 20. Spring @Transactional: khóa theo thứ tự

Trong Spring Data JPA, ví dụ service:

```java
package com.example.banking;

import jakarta.persistence.*;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void transfer(
            long fromId,
            long toId,
            BigDecimal amount) {

        if (fromId <= 0 || toId <= 0 || fromId == toId) {
            throw new IllegalArgumentException(
                "Invalid account pair"
            );
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }

        long firstId = Math.min(fromId, toId);
        long secondId = Math.max(fromId, toId);

        Account first = em.find(
            Account.class,
            firstId,
            LockModeType.PESSIMISTIC_WRITE
        );

        Account second = em.find(
            Account.class,
            secondId,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (first == null || second == null) {
            throw new IllegalArgumentException(
                "Account not found"
            );
        }

        Account from =
            fromId == firstId ? first : second;
        Account to =
            toId == firstId ? first : second;

        if (!from.getCurrency().equals(to.getCurrency())) {
            throw new IllegalArgumentException(
                "Currency mismatch"
            );
        }

        from.debit(amount);
        to.credit(amount);
    }
}
```

Transaction interceptor quản lý commit/rollback khi method được gọi đúng qua Spring proxy và transaction manager.

### 20.1. Vì sao không gọi getTransaction()?

Với EntityManager do Spring/container quản lý, không tự:

```java
em.getTransaction().begin();
```

để thay thế transaction manager. Dùng `@Transactional` hoặc cơ chế transaction programmatic phù hợp.

### 20.2. Lỗi có thể xuất hiện sau khi method trả về

JPA provider có thể phát SQL UPDATE/flush khi commit. Do đó deadlock hoặc lỗi constraint có thể xuất hiện **khi transaction interceptor kết thúc invocation**, không nhất thiết tại `find` hoặc setters.

Nếu cần retry, coordinator phải bao **toàn bộ lời gọi có commit**, không chỉ try/catch một dòng repository.

### 20.3. Self-invocation và proxy

Trong Spring proxy-based transaction mode, gọi `this.transfer(...)` trong cùng bean có thể bypass transaction interceptor. Khi đó lock calls có thể xảy ra ngoài transaction mong muốn và thất bại hoặc không giữ khóa đúng phạm vi.

Cần bảo đảm method transactional được gọi qua proxy hoặc dùng transaction management tương ứng.

## 21. Spring retry: một transaction mới cho mỗi attempt

Một cấu trúc rõ:

```text
TransferRetryCoordinator (không có outer transaction)
     |
     +-- attempt 1
     |      TransferTransactionalWorker.transferOnce()
     |      begin -> lock -> mutate -> commit/rollback
     |
     +-- attempt 2 (chỉ nếu retryable)
            TransferTransactionalWorker.transferOnce()
            begin -> lock -> mutate -> commit/rollback
```

**Không** đặt một `@Transactional` bao toàn bộ vòng retry rồi tiếp tục sau deadlock victim; transaction đã rollback hoặc rollback-only.

### 21.1. Worker thực thi một attempt

```java
@Service
public class TransferTransactionalWorker {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void transferOnce(
            long fromId,
            long toId,
            BigDecimal amount) {

        long firstId = Math.min(fromId, toId);
        long secondId = Math.max(fromId, toId);

        Account first = em.find(
            Account.class,
            firstId,
            LockModeType.PESSIMISTIC_WRITE
        );

        Account second = em.find(
            Account.class,
            secondId,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (first == null || second == null) {
            throw new IllegalArgumentException(
                "Account missing"
            );
        }

        Account from =
            firstId == fromId ? first : second;
        Account to =
            secondId == toId ? second : first;

        from.debit(amount);
        to.credit(amount);
    }
}
```

Đây là fragment minh họa ranh giới transaction; service thật còn phải validate input, currencies, authorization và idempotency. Trong ví dụ, biểu thức chọn `to` dựa trên `secondId == toId` tương đương chọn tài khoản còn lại vì đã kiểm tra hai IDs khác nhau ở tầng caller.

### 21.2. Coordinator quyết định retry

```java
@Service
public class TransferRetryCoordinator {

    private final TransferTransactionalWorker worker;
    private final DatabaseFailureClassifier classifier;

    public TransferRetryCoordinator(
            TransferTransactionalWorker worker,
            DatabaseFailureClassifier classifier) {
        this.worker = worker;
        this.classifier = classifier;
    }

    public void transfer(
            long fromId,
            long toId,
            BigDecimal amount) {

        int maxAttempts = 3;

        for (int attempt = 1;
                attempt <= maxAttempts;
                attempt++) {

            try {
                worker.transferOnce(
                    fromId, toId, amount
                );
                return;
            } catch (RuntimeException ex) {
                if (!classifier.isRetryableDeadlock(ex)
                        || attempt == maxAttempts) {
                    throw ex;
                }
                // Attempt sau dùng transaction mới.
            }
        }
    }
}
```

`DatabaseFailureClassifier` ở đây là một interface/service do ứng dụng tự xây cho **đúng DBMS/driver/provider**; không có một classifier portable hoàn chỉnh chỉ dựa vào các exception classes chuẩn.

### 21.3. Điều kiện để ví dụ đúng về transaction

- Coordinator không chạy trong một outer transaction làm mọi attempts cùng tham gia.
- Worker được gọi qua một Spring bean/proxy khác.
- Mỗi `transferOnce` kết thúc transaction trước khi trả control.
- Classifier không coi mọi lỗi database là deadlock.
- Có chính sách idempotency cho business transfer.
- Sau deadlock, không tái sử dụng entity/proxy từ attempt cũ.

Nếu có outer transaction, cần thiết kế propagation/transaction boundary rõ; `REQUIRES_NEW` không phải giải pháp miễn phí vì nó có thể tạo các commit độc lập với workflow bên ngoài.

## 22. Java SE và Spring đều cần rollback khi có lỗi

Một lỗi pessimistic lock có thể làm transaction không thể commit, tùy ngoại lệ và DBMS. Dù một `LockTimeoutException` theo semantics JPA có thể chỉ rollback statement, một business transfer nhiều account thường **nên rollback toàn bộ attempt** để tránh state không nhất quán.

### 22.1. Resource-local

```java
try {
    tx.begin();
    doBusinessWithOrderedLocks(em);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đây là mẫu tối giản; production code cần bảo toàn exception gốc nếu rollback tiếp tục lỗi và đóng EntityManager.

### 22.2. Spring/JTA

Để exception đi qua transaction interceptor và được rollback theo chính sách phù hợp. Không catch rồi trả success trong transaction đã lỗi.

### 22.3. Không dùng clear() để giải phóng locks

`EntityManager.clear()` detach entities và có thể làm mất pending changes, nhưng không tự commit/rollback transaction. Nó **không phải API giải phóng database locks** của một transaction chưa kết thúc.

## 23. Thứ tự khóa trong truy vấn theo business priority

Một câu hỏi thường gặp:

> “Nghiệp vụ muốn xử lý đơn ưu tiên cao trước. Có cần lấy khóa theo priority thay vì ID không?”

**Thứ tự xử lý nghiệp vụ** và **thứ tự cấp phát khóa** không nhất thiết phải giống nhau.

Một batch có thể:

1. Thu thập các orders cần thao tác.
2. Khóa các orders theo ID tăng dần.
3. Khi đã có đủ locks, xử lý chúng theo business priority.
4. Commit.

Nhưng cần đảm bảo khi xử lý theo priority **không phát sinh thêm các yêu cầu khóa quan trọng theo thứ tự trái ngược**.

### 23.1. Không để business order ngầm quyết định lock order

Ví dụ:

```java
for (Order order : ordersSortedByPriority) {
    em.lock(order, PESSIMISTIC_WRITE);
}
```

Priority có thể thay đổi giữa requests, và hai batches có thể có thứ tự khác nhau. Nó không bảo đảm một order toàn cục theo ID.

### 23.2. Lock all rồi xử lý

Một cách rõ:

```java
List<Long> ids = ordersToProcess.stream()
    .map(Order::getId)
    .distinct()
    .sorted()
    .toList();

for (Long id : ids) {
    em.find(
        Order.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );
}

// Sau đó mới xử lý theo thứ tự business phù hợp.
```

Nếu xử lý phát sinh một child entity mới cần khóa, phải đưa nó vào chiến lược global ordering nếu có thể hoặc tái cấu trúc transaction.

## 24. Một ví dụ khác: chuyển tồn kho giữa hai kho

Mô hình:

```text
InventoryBalance(warehouseId, productId, quantity)
```

Một lệnh:

```text
moveStock(sourceWarehouse=7,
          targetWarehouse=2,
          productId=101,
          quantity=5)
```

Nếu code khóa kho nguồn trước đích, các lệnh đối nghịch 7→2 và 2→7 có thể tạo ABBA.

### 24.1. Sắp composite key

Định nghĩa key:

```java
public record InventoryKey(
    long warehouseId,
    long productId
) implements Comparable<InventoryKey> {

    @Override
    public int compareTo(InventoryKey other) {
        int byWarehouse =
            Long.compare(warehouseId, other.warehouseId);

        if (byWarehouse != 0) {
            return byWarehouse;
        }

        return Long.compare(productId, other.productId);
    }
}
```

Có hai keys:

```text
(2,101)
(7,101)
```

Luôn khóa:

```text
(2,101) -> (7,101)
```

bất kể direction chuyển tồn.

### 24.2. Khóa theo composite ID

Khi entity `InventoryBalance` dùng `@EmbeddedId InventoryKey`, có thể `em.find(InventoryBalance.class, key, PESSIMISTIC_WRITE)` theo thứ tự `Comparable`. Việc entity/ID mapping cụ thể cần được định nghĩa riêng; ví dụ này tập trung vào so sánh khóa.

### 24.3. Không bỏ qua kiểm tra invariants

Sau khi khóa hai balances, cần:

- Kiểm tra nguồn còn đủ quantity.
- Kiểm tra hai keys khác nhau.
- Xác nhận product/tenant hợp lệ.
- Trừ nguồn và cộng đích trong cùng transaction.
- Có constraint ngăn quantity âm.
- Ghi movement record theo idempotency/business contract.

Thứ tự khóa giảm deadlock; nó không thay thế các checks này.

## 25. Hạn chế số lượng khóa và kích thước transaction

Một transaction batch khóa 10.000 entities theo ID tăng dần có thể tránh một số vòng ABBA nhưng:

- Giữ rất nhiều row locks.
- Tăng thời gian chờ của transactions khác.
- Có thể gây lock escalation.
- Làm connection/transaction sống lâu.
- Tăng phạm vi rollback nếu một bước cuối lỗi.

### 25.1. Chia batch khi nghiệp vụ cho phép

Nếu các records độc lập và không cần atomicity toàn batch, có thể chia thành các đơn vị nhỏ với idempotency/commit rõ.

**Không chia batch tùy tiện** nếu nghiệp vụ yêu cầu tất cả 10.000 rows được cập nhật nguyên tử. Khi đó phải cân nhắc kiến trúc khác hoặc kiểm soát throughput.

### 25.2. Chọn phạm vi khóa tối thiểu

Khóa những rows thực sự liên quan tới invariant. Không đọc rồi PESSIMISTIC_WRITE toàn bộ danh sách chỉ để sửa một phần nhỏ.

### 25.3. Tối ưu indexes và truy vấn

Một query thiếu index có thể quét nhiều rows/tables và tăng số locks. Tạo index phù hợp với filter có thể giảm thời gian xử lý, nhưng không phải mọi index đều làm mọi UPDATE nhanh hơn: index thêm cũng cần maintenance.

## 26. Quan sát deadlock từ database

Khi deadlock xuất hiện, cần dữ liệu thực tế để tìm vòng chờ. Chỉ nhìn stack trace Java thường không đủ.

Các nguồn thông tin tùy DBMS:

- Deadlock graph hoặc deadlock diagnostics.
- Transaction/connection IDs.
- SQL statements đang chạy.
- Các bảng/index/lock resources liên quan.
- Lock wait events.
- Query plan.
- Lock timeout/deadlock counters.
- Application trace/request/transfer IDs.

### 26.1. Mô tả một incident

Giả sử có log:

```text
T1: UPDATE accounts id=10
T2: UPDATE accounts id=20
T1: waiting on id=20
T2: waiting on id=10
```

Đây là dấu hiệu một vòng ABBA rõ.

Nhưng nếu log chỉ thấy:

```text
T1: UPDATE inventory_balance ...
T2: INSERT reservation ...
```

phải kiểm tra locks thực sự (FK/index/trigger) trước khi kết luận thứ tự nào sai.

### 26.2. Đừng suy thứ tự lock từ Java source mà không kiểm chứng

JPA provider có thể flush theo thứ tự không trùng Java property access. SQL optimizer có thể lấy khóa ngoài thứ tự kết quả. Khi vấn đề khó, phải dùng thông tin database để xác nhận wait-for graph.

### 26.3. Nên lưu những metrics nào?

- Deadlocks theo phút/giờ.
- Lock wait time.
- Số request bị rollback vì deadlock victim.
- Retry attempts và success-after-retry.
- Độ dài transaction.
- Top SQL statements liên quan.
- Hot entities/indexes.
- Latency p95/p99 của các endpoints cập nhật.

Một thay đổi lock order nên được đánh giá bằng **độ giảm deadlocks và hiệu năng thực tế**, không chỉ bằng việc code “trông đã sắp xếp”.

## 27. Kiểm thử deadlock đồng thời bằng hai transaction

Một unit test mock `EntityManager` không chứng minh SQL locks và vòng chờ thực tế. Cần **integration test với DBMS mục tiêu**.

### 27.1. Hai tests khác nhau

**Test A — Reproduce ABBA (lấy khóa sai thứ tự):**

- Transaction A khóa #10.
- Transaction B khóa #20.
- A yêu cầu #20.
- B yêu cầu #10.
- Database có thể phát hiện deadlock hoặc có timeout phù hợp.

**Test B — Consistent ordering (lấy khóa theo thứ tự):**

- Transaction A yêu cầu #10 trước rồi #20.
- Transaction B cũng yêu cầu #10 trước rồi #20.
- B có thể phải chờ A ở #10, nhưng không tự giữ #20 theo trình tự ngược.
- Cả hai có thể hoàn tất tuần tự nếu không có lỗi khác.

### 27.2. Vì sao test sai thứ tự cần thận trọng?

Một test cố tình tạo deadlock có thể **treo** hoặc chạy lâu nếu không có timeout/cleanup phù hợp. Nó chỉ nên chạy trong môi trường test có kiểm soát, không trên database production.

### 27.3. Mã giả điều phối hai luồng

```text
Thread A:
  txA.begin()
  lock Account#10
  signal "A has 10"
  await "B has 20"
  lock Account#20
  txA.commit()

Thread B:
  txB.begin()
  lock Account#20
  signal "B has 20"
  await "A has 10"
  lock Account#10
  txB.commit()
```

Đây là mã giả nhằm giải thích lịch trình ABBA. Trong test thật, dùng hai EntityManager/connections độc lập, synchronization primitives có timeout và cleanup transaction trong `finally`.

### 27.4. Test thứ tự chuẩn hóa

Không nên dùng hai barriers đặt **sau khi mỗi thread đã lấy khóa thứ nhất** nếu cả hai cùng cố khóa #10: B phải chờ ngay ở #10 nên không tới barrier, dẫn tới test tự treo dù code đúng.

Thay vào đó:

1. Cho A bắt đầu và giữ #10.
2. Cho B bắt đầu và xác nhận B đang cố lấy #10, chưa giữ #20.
3. Cho A lấy #20 rồi commit.
4. Xác nhận B tiếp tục, khóa #10 rồi #20, sau đó commit.
5. Kiểm tra số dư cuối và số lượng transfers đã ghi.

Đây là một tình huống kiểm thử **không tạo artificial synchronization deadlock** trong test harness.

### 27.5. Test trên DB thật thay vì in-memory giả lập

Lock semantics phụ thuộc DBMS và isolation, nên một in-memory database khác vendor không phải bằng chứng rằng PostgreSQL/Oracle/SQL Server/MySQL production sẽ xử lý giống vậy.

Nếu dự án dùng Testcontainers, chọn DBMS/version phù hợp production, cài migrations và cấu hình timeout đủ an toàn.

### 27.6. Hậu điều kiện

Sau hai giao dịch chuyển tiền thành công:

```text
Initial:
  A=1000
  B=500

Transfer 1:
  A -> B: 100

Transfer 2:
  B -> A: 50

Expected:
  A=950
  B=550
  Total=1500
```

Với nghiệp vụ thực tế phải kiểm tra thêm ledger entries và idempotency. Không chỉ kiểm tra “test không ném deadlock exception”.

## 28. Kiểm thử tính nhất quán của global order

Ngoài test concurrency, có thể kiểm tra các invariants của chính helper khóa.

### 28.1. Hai hướng phải cho một thứ tự

```text
input (10,20) -> [10,20]
input (20,10) -> [10,20]
```

### 28.2. N ID với duplicates

```text
input [9,3,9,1] -> [1,3,9]
```

### 28.3. Composite keys

```text
input [(7,2),(3,9),(3,1)] ->
      [(3,1),(3,9),(7,2)]
```

### 28.4. Bảo đảm đủ tập tài nguyên

Nếu transaction cần tài khoản #10, #20 và FeeAccount#99, quy tắc khóa phải bao gồm FeeAccount hoặc một global resource order bao quát nó. Chỉ kiểm tra hai tài khoản nguồn/đích là chưa đủ nếu fee posting được ghi trong cùng transaction.

### 28.5. Không lấy khóa trong method phụ theo thứ tự bất ngờ

Nếu `transfer()` khóa #10 và #20 xong, nhưng `calculateFeeAndSave()` lại khóa bảng khác theo thứ tự gây ABBA với batch job, global order có thể bị vi phạm ở đường đi sâu hơn.

Cần xác định tất cả repositories/services tham gia transaction.

## 29. Các hiểu nhầm và sai lầm thường gặp

### Sai lầm 1 — Khóa nguồn rồi đích vì thuận business flow

Hai request ngược chiều tạo ABBA.

**Cách đúng:** Chuẩn hóa thứ tự khóa theo ID hoặc global comparator trước.

### Sai lầm 2 — Nghĩ PESSIMISTIC_WRITE tự loại deadlock

`PESSIMISTIC_WRITE` giúp quản lý tranh chấp dữ liệu nhưng vẫn có thể deadlock khi lấy nhiều khóa theo thứ tự ngược.

### Sai lầm 3 — Chỉ sắp thứ tự trong một repository method

Nếu workflow khác đảo thứ tự, vẫn có vòng chờ.

**Cách đúng:** quy ước toàn cục cho mọi writer liên quan.

### Sai lầm 4 — Dùng HashSet iteration để quyết định thứ tự khóa

`HashSet` không bảo đảm thứ tự tăng dần. Dùng comparator/sort rõ ràng.

### Sai lầm 5 — Dùng ORDER BY trong query IN và khẳng định database sẽ khóa theo thứ tự đó

`ORDER BY` quy định thứ tự kết quả, không phải một bảo đảm lock acquisition order portable.

### Sai lầm 6 — Sửa entity trước rồi mới lấy khóa

Pending changes/auto-flush có thể đã lấy khóa theo thứ tự khác.

### Sai lầm 7 — Cho rằng setter order quyết định flush SQL order

JPA provider có thể batch/reorder DML.

### Sai lầm 8 — Dùng sleep để tránh deadlock

Sleep trong transaction kéo dài lock hold time, không loại bỏ vòng chờ.

### Sai lầm 9 — Tăng lock timeout để sửa vòng ABBA

Timeout chỉ là cơ chế kết thúc chờ, không sửa cấu trúc vòng.

### Sai lầm 10 — Catch deadlock rồi tiếp tục trong transaction cũ

Transaction deadlock victim có thể đã bị rollback/rollback-only. Phải kết thúc attempt và retry trong transaction mới nếu an toàn.

### Sai lầm 11 — Retry mọi lỗi lock không phân biệt

Deadlock, lock timeout và lỗi constraint có nguyên nhân/semantics khác nhau.

### Sai lầm 12 — Retry chuyển tiền thiếu idempotency key

Nếu outcome commit chưa rõ, cùng lệnh có thể được thực hiện hai lần.

### Sai lầm 13 — Lấy khóa trước khi gọi external API

Network delay làm tăng thời gian giữ khóa và contention.

### Sai lầm 14 — Chỉ khóa hai root entities, bỏ qua FK/trigger/ledger locks

Những khóa bổ sung có thể tạo vòng chờ khác.

### Sai lầm 15 — Cho rằng quy tắc ID tăng dần bảo đảm zero deadlocks

Query optimizer, indexes, triggers, range locks và nhiều code paths khác vẫn có thể tạo deadlock.

### Sai lầm 16 — Khóa tất cả rows để chắc chắn an toàn

Khóa quá rộng tăng contention và lock escalation; cần đúng scope.

### Sai lầm 17 — Gọi em.clear() để giải phóng database locks

`clear()` chỉ detach state của persistence context, không kết thúc transaction.

### Sai lầm 18 — Gọi @Transactional method qua this.method()

Spring proxy-based transaction interceptor có thể không chạy, làm boundary khác mong muốn.

### Sai lầm 19 — Dùng một EntityManager từ nhiều threads

`EntityManager` không được thiết kế để share tùy tiện giữa concurrent threads; transaction và lock state có thể bị rối. Mỗi đơn vị công việc cần context phù hợp.

### Sai lầm 20 — Chỉ unit test bằng mock để chứng minh hết deadlock

Mock không mô phỏng DB lock manager/execution plans. Cần integration tests và quan sát deadlock metrics thật.

## 30. Bài tập thực hành

### Bài 1 — Nhận diện ABBA

A giữ khóa #5 rồi chờ #9; B giữ #9 rồi chờ #5.

**Đáp án:** Có vòng chờ A↔B. Nếu quy tắc chung là khóa ID tăng dần, cả hai phải xin #5 trước #9.

### Bài 2 — Hai hướng chuyển tiền

```text
transfer(30, 10, 100)
transfer(10, 30, 50)
```

**Đáp án:** Cả hai khóa #10 rồi #30. Vai trò debit/credit vẫn giữ nguyên theo request.

### Bài 3 — HashSet

Code dùng:

```java
for (Long id : new HashSet<>(ids)) {
    em.find(Account.class, id, PESSIMISTIC_WRITE);
}
```

**Đáp án:** Không có thứ tự ổn định được bảo đảm. Dùng `distinct().sorted()` hoặc `TreeSet` với comparator rõ.

### Bài 4 — ORDER BY trong JPQL

Query `SELECT a FROM Account a WHERE a.id IN :ids ORDER BY a.id` dùng `PESSIMISTIC_WRITE`.

**Câu hỏi:** Có bảo đảm database cấp khóa theo thứ tự ID?

**Đáp án:** Không portable. SQL optimizer và locking strategy có thể khác. Nếu cần kiểm soát order rõ, có thể khóa từng ID theo thứ tự, rồi đo DBMS thực tế.

### Bài 5 — Mutation trước lock

Code sửa Account#20 rồi mới cố lấy khóa #10 và #20.

**Đáp án:** Auto-flush/DML có thể đã đụng #20 trước. Để kiểm soát global order, lấy đủ locks trước khi mutate những records thuộc lock domain.

### Bài 6 — N tài khoản

IDs đầu vào `[8,3,8,2,5]`.

**Đáp án:** Chuẩn hóa thành `[2,3,5,8]` trước khi lấy khóa.

### Bài 7 — Composite keys

`(warehouseId, productId)`. Input: `(3,5)`, `(2,8)`, `(3,1)`.

**Đáp án:** Nếu so thứ tự từ warehouse rồi product, khóa `(2,8)`, `(3,1)`, `(3,5)`.

### Bài 8 — Hai entity types

Workflow A khóa Order rồi Inventory. Workflow B khóa Inventory rồi Order.

**Đáp án:** Có nguy cơ ABBA dù các IDs được sort trong từng loại. Cần global ordering giữa types.

### Bài 9 — Lock wait nhưng không deadlock

B đợi A nhả #10; A không đợi B.

**Đáp án:** Đây là lock contention/wait, chưa phải vòng chờ deadlock. B có thể tiếp tục hoặc timeout.

### Bài 10 — Deadlock victim

Database rollback transaction A vì deadlock.

**Đáp án:** Không retry trong A đã lỗi. Rollback/đóng context phù hợp, bắt đầu transaction mới, kiểm tra lại tất cả business rules và idempotency.

### Bài 11 — LockTimeoutException

Một statement không lấy được khóa trong thời gian chờ.

**Đáp án:** Phân biệt statement-level timeout với transaction-level failure. Dù JPA có semantics khác nhau, một workflow multi-account thường nên rollback attempt và xử lý ở ranh giới transaction.

### Bài 12 — Network call sau khóa thứ nhất

Một method lock Account#10 rồi gọi dịch vụ tỷ giá trước khi lock #20.

**Đáp án:** Tính toán/lấy tỷ giá cần thiết nên chuẩn bị trước nếu có thể; sau đó lấy locks theo thứ tự và xác nhận dữ liệu mutable trong transaction.

### Bài 13 — Hai collection dữ liệu

Một batch update vừa khóa Parent vừa xóa Child, trong khi job khác xử lý Child rồi Parent.

**Đáp án:** Có thể tạo vòng khóa ngoài danh sách root IDs. Cần đánh giá cả FK/index/trigger và thống nhất order liên loại.

### Bài 14 — Chuyển 100 tài khoản

Cần xử lý 100 tài khoản trong một transaction.

**Đáp án:** Sort keys và khóa theo order nếu phải atomic. Đồng thời đánh giá độ dài transaction, số round-trips, lock escalation và khả năng chia batch nếu nghiệp vụ cho phép.

### Bài 15 — Test deadlock

Hai threads cố tình tạo ABBA bằng barriers.

**Đáp án:** Dùng DB thật, EntityManager/transaction riêng, timeout và cleanup. Không chạy test cố ý deadlock trên production.

### Bài 16 — Test thứ tự chuẩn

Hai threads cùng khóa #10 trước #20.

**Đáp án:** Không đặt barrier bắt cả hai cùng “đã lấy khóa thứ nhất” vì thread B đang chờ #10. Test phải điều phối đúng trạng thái chờ và cho A commit để B tiếp tục.

### Bài 17 — Side effect

Một transfer ghi DB rồi gửi email trước commit, sau đó deadlock.

**Đáp án:** Email không rollback. Dùng outbox và idempotency khi gửi thông báo.

### Bài 18 — Cập nhật cùng account nhưng không dùng khóa bi quan

Một transaction dùng managed entity `@Version`, transaction khác PESSIMISTIC_WRITE.

**Gợi ý:** Không có nghĩa mọi writer hoàn toàn bị serial theo ý định nếu các code paths không có transaction/version policy tương thích. Cần xét dirty checking/SQL locking/optimistic conflicts và business invariants.

### Bài 19 — Index không phù hợp

Một query locking quét nhiều rows vì thiếu index.

**Đáp án:** Có thể tăng lock footprint và latency. Đánh giá query plan, indexes và lock scope thay vì chỉ chỉnh timeout.

### Bài 20 — Metrics sau thay đổi

Sau khi sửa global order, deadlock count giảm nhưng p99 latency vẫn cao.

**Giải thích:** Có thể vòng chờ đã giảm nhưng hot-row contention vẫn lớn. Cần đo lock waits, transaction duration, index performance và throughput.

## 31. Câu hỏi tự kiểm tra

**1. Deadlock là gì?**

Một vòng phụ thuộc giữa các transaction đang chờ tài nguyên nhau giữ, khiến chúng không thể tự tiến lên.

**2. Deadlock khác lock wait đơn giản ở đâu?**

Lock wait đơn giản không cần vòng chờ; deadlock có chu trình A→B→A hoặc dài hơn.

**3. Mẫu ABBA là gì?**

A lấy khóa X rồi muốn Y, B lấy Y rồi muốn X.

**4. Biện pháp chính trong bài học là gì?**

Mọi transaction lấy nhiều khóa theo cùng một thứ tự toàn cục.

**5. Vì sao phải khóa theo ID thay vì nguồn/đích?**

Hai giao dịch chuyển tiền ngược chiều có thể đảo thứ tự nguồn/đích nhưng ID order vẫn giống nhau.

**6. Phải làm gì trước khi khóa N resources?**

Xác định tập keys, loại trùng và sắp xếp bằng comparator thống nhất.

**7. Việc sort Java IDs có đủ bảo đảm database tuyệt đối không deadlock?**

Không. Còn nhiều khóa phụ, query plan và code paths khác.

**8. ORDER BY ở query IN có đảm bảo thứ tự cấp locks không?**

Không portable; ORDER BY chủ yếu quy định thứ tự kết quả.

**9. Vì sao lấy khóa từng ID có lợi?**

Nó biểu đạt thứ tự yêu cầu khóa trên các root entities rõ ràng hơn.

**10. Vì sao không mutate trước khi acquire all locks?**

Auto-flush và DML có thể lấy khóa theo thứ tự khác.

**11. Setter order có quyết định thứ tự SQL UPDATE không?**

Không bắt buộc; provider có thể batch hoặc reorder.

**12. Khóa bi quan nào thường được dùng khi sẽ cập nhật entity?**

`LockModeType.PESSIMISTIC_WRITE`.

**13. PESSIMISTIC_WRITE có tự ngăn mọi deadlock không?**

Không. Vẫn có thể deadlock khi lấy nhiều resources theo thứ tự ngược hoặc do khóa phụ.

**14. LockTimeoutException và PessimisticLockException có cùng transaction semantics không?**

Theo JPA, chúng phân biệt statement-level với transaction-level rollback; nhưng xử lý thực tế cần xét provider/DBMS và business atomicity.

**15. Khi deadlock victim bị rollback, có nên tiếp tục transaction cũ không?**

Không. Phải kết thúc attempt và chỉ retry trong transaction mới nếu an toàn.

**16. Vì sao retry phải có idempotency trong transfer?**

Để tránh ghi giao dịch chuyển tiền lặp khi request/commit outcome không rõ hoặc client retry.

**17. Có nên gọi external API khi đang giữ nhiều database locks không?**

Nên tránh nếu có thể; kéo dài thời gian giữ khóa và side effects ngoài DB không rollback.

**18. Thứ tự khóa liên loại nên được định nghĩa như thế nào?**

Một quy tắc toàn cục cho entity types và keys, nhất quán ở tất cả code paths.

**19. Global ordering có loại bỏ lock contention trên hot row không?**

Không. Nó giảm một loại deadlock, không làm biến mất việc nhiều transaction chờ cùng một row.

**20. Vì sao FK và triggers có thể làm deadlock dù root IDs đã sort?**

Chúng có thể lấy khóa ở những bảng/index khác với thứ tự ngoài kiểm soát trực tiếp của code root.

**21. Có nên tăng lock timeout làm biện pháp chính để chữa ABBA không?**

Không. Cần sửa thứ tự khóa và giảm transaction duration.

**22. Unit test mock có chứng minh hết deadlock không?**

Không. Cần integration tests với DBMS/driver/provider thật.

**23. Khi kiểm thử global order, vì sao không chặn hai threads ở barrier sau khi cả hai đã khóa #10?**

Vì một thread phải chờ #10; barrier như vậy có thể tự tạo test deadlock.

**24. Có nên dùng em.clear() để nhả khóa DB không?**

Không. Database locks liên quan transaction, không phải chỉ managed objects.

**25. Khi nào nên chia batch?**

Khi các phần việc có thể commit độc lập theo domain contract và việc chia giúp giảm lock hold time/footprint.

**26. Thứ tự xử lý nghiệp vụ có phải là thứ tự khóa không?**

Không nhất thiết. Có thể khóa theo global order trước, sau đó xử lý nghiệp vụ theo priority mà không phá lock ordering.

**27. Nếu hai transfer lần lượt 10→20 và 20→10, lock order đúng theo ID tăng dần là gì?**

Cả hai khóa #10 rồi #20.

**28. Một câu nói chuẩn xác nhất về lợi ích của kỹ thuật là gì?**

Global lock ordering **giảm nguy cơ deadlock do đảo thứ tự khóa**, nhưng không đảm bảo loại bỏ mọi deadlock hoặc timeout.

## 32. Tình huống tổng hợp: chuyển tiền an toàn dưới tải đồng thời

Một yêu cầu chuyển tiền thực tế có thể mang:

```java
public record TransferCommand(
    String requestId,
    long fromAccountId,
    long toAccountId,
    BigDecimal amount,
    String currency
) {}
```

Ngoài thứ tự khóa, workflow cần:

- Xác thực caller có quyền sử dụng account nguồn.
- Kiểm tra `requestId` duy nhất và idempotent.
- Không cho chuyển cùng account nếu hợp đồng không hỗ trợ.
- Kiểm tra currency và amount.
- Khóa cả hai accounts theo global order.
- Xác nhận số dư mới nhất.
- Debit/Credit trong cùng transaction.
- Ghi ledger rows tương ứng trong cùng transaction.
- Ghi outbox event.
- Commit và trả kết quả.
- Retry deadlock victim có giới hạn và không tạo transfer trùng.

### 32.1. Luồng đề xuất

```text
HTTP / Message TransferCommand
             |
             v
Authorization + Validation
             |
             v
Resolve requestId / Idempotency policy
             |
             v
BEGIN TRANSACTION
             |
             v
Normalize account IDs:
  first = min(from,to)
  second = max(from,to)
             |
             v
PESSIMISTIC_WRITE first
             |
             v
PESSIMISTIC_WRITE second
             |
             v
Check latest balances + currency
             |
             v
Debit source / Credit destination
             |
             v
Insert ledger + idempotency record
             |
             v
Insert outbox event
             |
             v
FLUSH / COMMIT
             |
          +--+--+
          |     |
       success  deadlock/lock failure
          |     |
          v     v
       Return   Rollback
       receipt     |
                   v
             New transaction retry
             only when safe
```

### 32.2. Điểm khó: idempotency record cũng là một lock resource

Nếu `requestId` được ghi vào bảng idempotency trước hoặc sau account locks, tất cả code paths xử lý cùng command và các jobs liên quan phải áp một lock order hợp lý trên tài nguyên này nữa.

Không được chỉ tối ưu account lock order mà bỏ qua ledger/outbox/idempotency insert khi deadlock graph thực tế cho thấy chúng là một phần vòng chờ.

### 32.3. Khi có ledger và nhiều bảng

Sắp các account IDs có thể loại ABBA ở tài khoản, nhưng ledger insert có thể gây tranh index/FK; cần quan sát DBMS và giữ transaction ngắn.

Nếu request duy nhất phải tạo ledger entry có khóa unique, hãy khai báo unique constraint cho `requestId`/business key phù hợp. Idempotency không nên chỉ dựa vào SELECT “chưa thấy row” trước INSERT vì hai transaction có thể cùng thấy chưa có.

### 32.4. Hậu điều kiện

Sau các transfer được commit:

- Tổng số dư hai tài khoản được bảo toàn theo rule tiền tệ (không xét phí).
- Không số dư âm khi điều kiện không cho phép.
- Một business request không bị ghi nhận hai lần.
- Ledger tương ứng đúng.
- Outbox chỉ chứa event của transaction commit.
- Transactions bị rollback không để lại partial updates.
- Các khóa được lấy theo global order ở những paths có thể kiểm soát.
- Deadlock rate và lock wait latency nằm trong ngưỡng vận hành.

## 33. Tổng kết

**Bế tắc khi dùng khóa bi quan** thường xuất hiện vì những transaction cùng cần nhiều tài nguyên nhưng **lấy khóa theo thứ tự không thống nhất**. Mẫu dễ gặp là hai giao dịch chuyển tiền ngược chiều: một bên khóa tài khoản nguồn trước, bên kia cũng khóa nguồn của nó trước, tạo thứ tự **A→B và B→A**.

Giải pháp cấu trúc:

1. **Xác định toàn bộ các tài nguyên cần khóa** trong một đơn vị công việc.
2. **Định nghĩa thứ tự khóa toàn cục** theo type/key/ID; với hai Account IDs là `min(id)` rồi `max(id)`.
3. **Chuẩn hóa, loại trùng và sắp xếp keys** trước khi bắt đầu lấy khóa.
4. **Lấy khóa tuần tự theo thứ tự**, ví dụ `em.find(Entity.class, id, PESSIMISTIC_WRITE)` cho từng ID.
5. **Chỉ mutate sau khi lấy đủ khóa**, tránh auto-flush hoặc DML sớm phá trình tự.
6. **Giữ transaction ngắn**, không gọi mạng hoặc ngủ trong lúc đang giữ khóa.
7. **Áp chính sách ở mọi writer**, không chỉ một service method.
8. **Rollback và retry có kiểm soát** khi thực sự gặp deadlock victim, trong transaction mới và có idempotency cho các nghiệp vụ dễ bị lặp.
9. **Đo deadlock graph và thực thi SQL thật** vì FK, indexes, triggers, isolation, optimizer và lock escalation vẫn có thể tạo vòng chờ khác.
10. **Kiểm thử trên DBMS thật** với lịch trình đồng thời có timeout, không dựa vào mock hay số query đơn giản.

Kết luận quan trọng nhất: **thứ tự truy cập nhất quán là một kỹ thuật giảm deadlock hiệu quả, chứ không phải chứng nhận hệ thống “không bao giờ deadlock”.** Sự an toàn tổng thể cần cả transaction boundaries, invariant nghiệp vụ, DB constraints, chiến lược retry, idempotency và quan sát thực tế trên hệ quản trị đang vận hành.
