# Phối hợp begin, commit và rollback có xử lý lỗi

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Giao dịch

Một thao tác JPA không chỉ cần “gọi `persist()` để lưu dữ liệu”. Với các use case tạo, sửa hoặc xóa dữ liệu, ứng dụng cần xác định **khi nào bắt đầu giao dịch**, **điều kiện nào cho phép commit**, **lỗi nào buộc rollback**, và **tài nguyên nào phải được giải phóng dù xử lý thành công hay thất bại**.

Hãy xét nghiệp vụ chuyển tiền giữa hai tài khoản. Nếu đã trừ tiền ở tài khoản nguồn nhưng không cộng được tiền vào tài khoản đích, hệ thống phải tránh trạng thái chỉ một nửa nghiệp vụ được xác nhận. Transaction cho phép nhóm các thao tác database trong một đơn vị nguyên tử. Tuy nhiên, chương trình chỉ an toàn khi phối hợp đúng các lệnh `begin()`, `commit()` và `rollback()`; đồng thời phải xử lý các lỗi xảy ra ở **bất kỳ bước nào**, kể cả khi flush hoặc chính thao tác commit thất bại.

Bài này dùng **Jakarta Persistence (JPA)** làm ngữ cảnh chính, phân biệt hai cách quản lý giao dịch thường gặp:

- **`RESOURCE_LOCAL`:** ứng dụng điều khiển `EntityTransaction` bằng `begin()`, `commit()` và `rollback()`.
- **JTA/container hoặc Spring:** transaction manager điều khiển giao dịch, code nghiệp vụ thường dùng `@Transactional` thay vì thao tác trực tiếp trên `EntityTransaction`.

Trọng tâm là **quy trình điều khiển giao dịch với xử lý lỗi đúng**, không chỉ là cú pháp ba phương thức.

---

## 1. Kết quả cần đạt

Sau khi học xong, bạn có thể:

1. Giải thích vai trò riêng của `begin()`, `flush()`, `commit()`, `rollback()` và `EntityManager.close()`.
2. Viết một khối `try/catch/finally` đúng cho giao dịch JPA `RESOURCE_LOCAL`.
3. Chỉ rollback khi transaction còn active, không gọi rollback một cách mù quáng sau commit.
4. Giữ lại **lỗi gốc** nếu thao tác rollback hoặc đóng tài nguyên cũng phát sinh lỗi.
5. Phân biệt exception xảy ra trước `begin`, khi xử lý nghiệp vụ, tại `flush`, tại `commit` và tại `close`.
6. Biết vì sao `commit()` có thể tự kích hoạt flush, và vì sao SQL đã được phát không đồng nghĩa dữ liệu đã commit.
7. Xử lý đúng transaction đã bị đánh dấu **rollback-only**.
8. Phân biệt giao dịch `RESOURCE_LOCAL` với JTA, Spring `@Transactional` và chính sách rollback theo loại exception.
9. Nhận biết các rủi ro như nuốt exception, retry trong cùng persistence context, commit không rõ kết quả, optimistic locking và tác động ngoài database.
10. Thiết kế bài thực hành có thể chứng minh tính nguyên tử của nhiều thao tác ghi.

## 2. Vì sao ba lệnh này phải được phối hợp?

Một transaction database có thể được hình dung như sau:

```text
          begin()
             |
             v
     Transaction ACTIVE
             |
       đọc / ghi entity
       persist / remove
       thay đổi managed fields
             |
             +-- thành công ----> commit()
             |                        |
             |                        +-- COMMITTED
             |                        |
             |                        +-- commit thất bại
             |                              -> xử lý lỗi và trạng thái TX
             |
             +-- thất bại -----> rollback()
                                      |
                                      +-- ROLLED BACK
```

### 2.1. begin(): bắt đầu một đơn vị công việc

Với `EntityTransaction`:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();
```

`begin()` làm transaction bắt đầu ở phạm vi mà `EntityTransaction` quản lý. Nó **không tự thực hiện một thao tác lưu entity**, không tự INSERT và không bảo đảm mọi tác động ngoài database sẽ được rollback.

Nếu transaction đã active, gọi `begin()` thêm lần nữa không phải cách tạo “transaction lồng nhau”; API có thể báo lỗi. Muốn làm việc với nested savepoint hoặc transaction propagation, phải dùng cơ chế transaction manager/database hỗ trợ rõ ràng.

### 2.2. commit(): xác nhận những thay đổi của giao dịch

```java
tx.commit();
```

Khi commit thành công, những thay đổi database thuộc transaction được xác nhận theo quy tắc isolation/durability của hệ quản trị cơ sở dữ liệu. Trước commit, provider thường sẽ đồng bộ những thay đổi còn pending của persistence context bằng flush.

**Commit không phải thao tác đóng EntityManager.** Một EntityManager do ứng dụng tạo vẫn có thể mở sau commit. Việc các entity còn managed hay detached phụ thuộc scope của persistence context và thao tác quản lý tiếp theo.

### 2.3. rollback(): hủy những thay đổi chưa commit

```java
tx.rollback();
```

Rollback nhằm hủy các thao tác database chưa được commit trong transaction hiện tại. Nó không:

- Hủy một transaction khác đã commit trước đó.
- Xóa các email đã gửi, HTTP request đã gọi hoặc file đã ghi ra ngoài database.
- Hoàn tác tất cả mutation của object Java trong bộ nhớ.
- Đảm bảo object/entity trong persistence context cũ có thể tiếp tục dùng an toàn ngay sau lỗi.

Một giao dịch bị lỗi cần **rollback đúng lúc**, sau đó thường kết thúc unit of work và tải lại dữ liệu trong context mới nếu muốn tiếp tục.

## 3. Phân biệt flush, commit và close

Đây là ba mốc thường bị nhầm:

| Thao tác | Nhiệm vụ | Có xác nhận dữ liệu bền vững? | Có tự kết thúc EntityManager? |
|---|---|---|---|
| `em.flush()` | Đồng bộ các thay đổi pending từ persistence context vào database trong transaction | **Không**; rollback vẫn có thể hủy | Không |
| `tx.commit()` | Kết thúc transaction bằng cách xác nhận; có thể kích hoạt flush | **Có**, nếu commit thành công | Không mặc nhiên |
| `tx.rollback()` | Kết thúc transaction bằng cách hủy thay đổi chưa commit | Không | Không mặc nhiên |
| `em.close()` | Giải phóng EntityManager do ứng dụng quản lý và kết thúc context của nó theo lifecycle thích hợp | **Không phải commit** | Có |

Một timeline thường gặp:

```text
tx.begin()
    |
    | em.persist(order)
    | order.addLine(...)
    | customer.rename(...)
    |
    | em.flush()           <- có thể phát INSERT/UPDATE/DELETE
    |                        nhưng transaction vẫn chưa commit
    |
    | tx.commit()          <- xác nhận nếu thành công
    |
em.close()                 <- giải phóng EM
```

SQL có thể xảy ra **sớm hơn** flush hoặc commit, chẳng hạn `GenerationType.IDENTITY` đôi khi khiến provider INSERT để lấy generated ID. Mặt khác, một thay đổi trên managed entity có thể chỉ nằm trong bộ nhớ cho đến flush. Do đó, **đừng coi thời điểm nhìn thấy SQL là ranh giới commit**.

---

## 4. Điều kiện tiên quyết: xác định loại transaction

Trước khi viết code, cần biết ai quản lý transaction.

### 4.1. RESOURCE_LOCAL với EntityTransaction

Trong ứng dụng Java SE hoặc cấu hình `RESOURCE_LOCAL`:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("shopPU");

EntityManager em = emf.createEntityManager();

EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    // Các thao tác tạo/sửa/xóa database.
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Đây là mô hình mà ứng dụng điều khiển begin/commit/rollback trực tiếp. Đoạn trên minh họa ý tưởng ban đầu; những phần sau sẽ viết mẫu chắc chắn hơn để xử lý **lỗi ở `begin`, rollback và close**.

### 4.2. JTA/container-managed transaction

Với một EntityManager tham gia JTA transaction do container quản lý:

```java
@PersistenceContext
private EntityManager em;
```

Ứng dụng thường để container điều khiển transaction bằng cơ chế transactional service/EJB/Jakarta Transactions. Không gọi:

```java
em.getTransaction().begin();
```

trên JTA EntityManager rồi kỳ vọng nó hoạt động như `RESOURCE_LOCAL`. `EntityManager.getTransaction()` không phải API để tự điều khiển JTA-managed EntityManager; việc dùng sai thường dẫn đến exception.

### 4.3. Spring @Transactional

Với Spring:

```java
@Transactional
public void createOrder(CreateOrderCommand command) {
    // Thực hiện nghiệp vụ.
    // Transaction manager xử lý begin/commit/rollback.
}
```

Spring AOP/transaction manager điều khiển transaction khi lời gọi đi qua cơ chế interceptor phù hợp. Không tự gọi `em.getTransaction().begin()` trong một phương thức Spring `@Transactional` thông thường.

**Quy tắc chọn đúng API:** `EntityTransaction` dành cho resource-local transaction; JTA/Spring sử dụng transaction manager tương ứng. Phần tiếp theo bắt đầu từ `RESOURCE_LOCAL` để nhìn rõ từng bước, sau đó chuyển sang cách áp dụng với framework.

---

## 5. Mẫu giao dịch RESOURCE_LOCAL tối thiểu, có rollback khi lỗi

Đây là cấu trúc nên nắm vững trước tiên:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        // Đọc managed entities, kiểm tra invariant,
        // thực hiện các thay đổi thuộc một nghiệp vụ.
        performBusinessOperation(em);

        tx.commit();
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }

        throw failure;
    }
} finally {
    em.close();
}
```

Luồng:

1. Tạo `EntityManager`.
2. Lấy `EntityTransaction`.
3. Gọi `begin()`.
4. Thực hiện **tất cả thao tác database cần nguyên tử**.
5. Nếu không có lỗi, gọi `commit()`.
6. Nếu có `RuntimeException`, rollback khi transaction còn active rồi ném lại lỗi.
7. Dù thành công hay thất bại, đóng EntityManager do ứng dụng tạo.

### 5.1. Vì sao phải có finally?

Nếu code phát sinh lỗi ở `find`, `persist`, query, `flush` hoặc `commit`, câu lệnh close đặt cuối phương thức thông thường có thể không được thực thi. `finally` giúp giải phóng tài nguyên theo kiểm soát rõ ràng.

`EntityManagerFactory` thường tồn tại ở lifecycle ứng dụng; không nên đóng EMF mỗi lần thực hiện một nghiệp vụ. `EntityManager` lại thường ngắn hơn, theo unit of work.

### 5.2. Vì sao ném lại exception?

```java
catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }

    throw failure;
}
```

Ném lại cho phép tầng gọi biết nghiệp vụ **thất bại**. Nếu chỉ rollback rồi im lặng trả kết quả thành công, API có thể báo một đơn hàng đã tạo dù database không lưu.

Có thể chuyển exception persistence thành domain/application exception phù hợp, nhưng phải giữ nguyên sự thật rằng transaction thất bại và có logging/cause để điều tra.

### 5.3. Tại sao chỉ rollback khi tx.isActive()?

Có nhiều điểm lỗi:

- `tx.begin()` có thể lỗi trước khi transaction active.
- `tx.commit()` có thể thành công và kết thúc transaction.
- `tx.commit()` có thể thất bại, một số trường hợp transaction đã kết thúc/rollback.
- `tx.rollback()` chỉ có ý nghĩa khi còn transaction cần rollback.

Gọi rollback không điều kiện có thể ném thêm lỗi, che mất nguyên nhân ban đầu. Kiểm tra `isActive()` giúp giảm rủi ro này, nhưng bản thân việc kiểm tra trạng thái cũng có thể ném exception trong một số tình huống lỗi bất thường. Mẫu vững hơn ở phần tiếp theo xử lý cả trường hợp đó.

---

## 6. Mẫu chắc chắn hơn: bảo toàn lỗi gốc khi rollback cũng thất bại

Một vấn đề thực tế: `performBusinessOperation` ném exception **A**, nhưng `rollback` lại ném exception **B** vì connection gặp sự cố. Nếu cứ gọi rollback trong catch mà không xử lý B, log có thể chỉ còn B và che mất A.

Java hỗ trợ `Throwable.addSuppressed` để giữ lại những lỗi phát sinh trong quá trình cleanup.

```java
import jakarta.persistence.EntityTransaction;

private static void rollbackIfActive(
        EntityTransaction tx,
        Throwable originalFailure) {

    try {
        if (tx.isActive()) {
            tx.rollback();
        }
    } catch (RuntimeException rollbackFailure) {
        originalFailure.addSuppressed(rollbackFailure);
    }
}
```

Dùng:

```java
try {
    tx.begin();

    // Các thao tác nghiệp vụ...
    tx.commit();
} catch (RuntimeException | Error failure) {
    rollbackIfActive(tx, failure);
    throw failure;
}
```

Đặc điểm:

- `RuntimeException` bao gồm nhiều lỗi thường gặp từ JPA.
- `Error` được ném lại sau khi cố rollback; không bị nuốt im lặng.
- Nếu `rollback()` hoặc `isActive()` ném `RuntimeException`, lỗi đó được thêm vào `failure.getSuppressed()`.
- **Lỗi gốc** vẫn là exception chính đi tới tầng gọi.
- Không biến lỗi rollback thành tín hiệu “mọi thứ đã được hoàn tác”: nếu rollback thất bại, trạng thái transaction/resource có thể không xác định và cần ngừng sử dụng unit of work đó.

Trong Java, một số lỗi cực đoan như JVM termination hoặc mất process không thể được `try/catch/finally` bảo đảm dọn dẹp. Độ bền dữ liệu và recovery khi process chết vẫn thuộc database/transaction manager cùng kiến trúc hệ thống.

### 6.1. Đặt begin() bên trong vùng catch

So sánh hai vị trí:

```java
tx.begin();

try {
    doWork();
    tx.commit();
} catch (RuntimeException ex) {
    // ...
}
```

Nếu `begin()` thất bại, catch trên **không chạy**, vì begin nằm ngoài vùng try đó. Một cách rõ hơn:

```java
try {
    tx.begin();
    doWork();
    tx.commit();
} catch (RuntimeException | Error failure) {
    rollbackIfActive(tx, failure);
    throw failure;
}
```

Khi đó lỗi bắt đầu transaction cũng đi qua cơ chế ghi nhận/cố rollback phù hợp. Trong mọi trường hợp, `em.close()` vẫn cần được tổ chức ở `finally`.

### 6.2. Nếu close cũng thất bại?

Mẫu:

```java
try {
    // Giao dịch...
} finally {
    em.close();
}
```

đủ tốt cho nhiều chương trình. Nhưng nếu phần try đã ném lỗi A và `close()` cũng ném lỗi B, Java có thể để B che A.

Với code hạ tầng yêu cầu bảo toàn đầy đủ lỗi, có thể lưu nguyên nhân chính và gắn lỗi close thành suppressed:

```java
Throwable primaryFailure = null;

try {
    // Giao dịch...
} catch (RuntimeException | Error failure) {
    primaryFailure = failure;
    throw failure;
} finally {
    try {
        em.close();
    } catch (RuntimeException closeFailure) {
        if (primaryFailure != null) {
            primaryFailure.addSuppressed(closeFailure);
        } else {
            throw closeFailure;
        }
    }
}
```

**Quan trọng:** exception khi close **sau commit thành công** là lỗi cleanup, không có nghĩa transaction đã rollback. Nếu API phân loại tất cả exception là “chưa tạo dữ liệu”, nó có thể retry và vô tình tạo trùng. Khi thiết kế API production, cần phân biệt **outcome của transaction** với **outcome của cleanup**.

---

## 7. Viết một TransactionRunner tái sử dụng được

Đối với ứng dụng Java SE nhỏ, có thể gom boilerplate transaction vào một helper, để business function chỉ tập trung vào thay đổi dữ liệu.

```java
package demo.persistence;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

import java.util.Objects;
import java.util.function.Function;

public final class TransactionRunner {

    private TransactionRunner() {
    }

    public static <T> T execute(
            EntityManagerFactory emf,
            Function<EntityManager, T> work) {

        Objects.requireNonNull(emf, "emf");
        Objects.requireNonNull(work, "work");

        EntityManager em = emf.createEntityManager();
        Throwable primaryFailure = null;

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                T result = work.apply(em);

                tx.commit();
                return result;
            } catch (RuntimeException | Error failure) {
                rollbackIfActive(tx, failure);
                throw failure;
            }
        } catch (RuntimeException | Error failure) {
            primaryFailure = failure;
            throw failure;
        } finally {
            try {
                em.close();
            } catch (RuntimeException closeFailure) {
                if (primaryFailure != null) {
                    primaryFailure.addSuppressed(closeFailure);
                } else {
                    throw closeFailure;
                }
            }
        }
    }

    private static void rollbackIfActive(
            EntityTransaction tx,
            Throwable originalFailure) {

        try {
            if (tx.isActive()) {
                tx.rollback();
            }
        } catch (RuntimeException rollbackFailure) {
            originalFailure.addSuppressed(rollbackFailure);
        }
    }
}
```

Cách dùng:

```java
Long savedId = TransactionRunner.execute(emf, em -> {
    Customer customer = new Customer("Công ty An");

    em.persist(customer);

    return customer.getId();
});
```

Ý nghĩa:

- Function nhận một `EntityManager` **đã có transaction active**.
- TransactionRunner chỉ trả kết quả bình thường khi `commit()` không báo lỗi.
- Lỗi trong Function hoặc ở `commit()` đi qua quy trình rollback nếu transaction còn active.
- Lỗi rollback/close không che lỗi gốc.
- Dù lỗi, EntityManager do helper tạo được cố gắng đóng.
- Không dùng chung EntityManager cho nhiều thread.
- Helper không tự retry: retry phải xét **nghiệp vụ và loại lỗi**.

**Giới hạn quan trọng:** `Function<EntityManager,T>` chỉ cho phép ném unchecked exception trực tiếp. Nếu nghiệp vụ cần checked exception, hãy thiết kế functional interface riêng có `throws` và chiến lược catch/rollback rõ ràng. Đừng chuyển mọi checked exception thành unchecked mà không giữ cause.

### 7.1. TransactionRunner có phù hợp với Spring không?

Không nên sử dụng helper `RESOURCE_LOCAL` này trong một ứng dụng Spring mà EntityManager do `JpaTransactionManager`/JTA quản lý. Spring đã cung cấp cơ chế transaction boundary và propagation; điều khiển thêm một `EntityTransaction` thủ công có thể xung đột.

Trong Spring, nên dùng service `@Transactional` hoặc `TransactionTemplate` phù hợp, không tự tạo một “transaction runner” bên cạnh transaction manager trừ khi có kiến trúc yêu cầu rõ ràng.

### 7.2. Không giữ entity managed bên ngoài helper với giả định còn managed

`TransactionRunner.execute` đóng EM trước khi trả quyền điều khiển về caller. Vì vậy entity được trả ra từ Function có thể trở thành **detached** sau khi helper kết thúc.

Ví dụ:

```java
Customer returned = TransactionRunner.execute(emf, em ->
    em.find(Customer.class, customerId)
);

// returned không còn thuộc EntityManager đã bị đóng.
returned.rename("Tên mới"); // Chỉ sửa object detached.
```

Khi API chỉ cần dữ liệu đọc, nên trả DTO thay vì entity JPA:

```java
record CustomerView(Long id, String name) {}

CustomerView view = TransactionRunner.execute(emf, em -> {
    Customer customer = em.find(Customer.class, customerId);

    if (customer == null) {
        throw new IllegalArgumentException("Customer not found");
    }

    return new CustomerView(
        customer.getId(),
        customer.getDisplayName()
    );
});
```

Đây là ví dụ về ranh giới persistence; với read-only query đơn giản, không phải mọi môi trường đều bắt buộc một resource-local transaction cho `find()`, nhưng transaction rõ ràng có thể hữu ích khi unit of work cần consistency.

---

## 8. Ví dụ nghiệp vụ hoàn chỉnh: chuyển tiền giữa hai tài khoản

Một ví dụ dễ thấy tính nguyên tử là chuyển tiền.

**Yêu cầu:**

- Tài khoản nguồn và đích phải tồn tại và khác nhau.
- Số tiền chuyển phải dương.
- Không cho chuyển nhiều hơn số dư.
- Nếu bất kỳ bước nào thất bại, transaction không được xác nhận một phần.
- Nếu hai request đồng thời sửa cùng tài khoản, cần cơ chế phát hiện hoặc điều khiển xung đột.
- Cả hai row phải được xử lý trong một transaction database phù hợp.

### 8.1. Entity BankAccount

```java
package demo.domain;

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
@Table(name = "bank_accounts")
public class BankAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "balance",
        nullable = false,
        precision = 19,
        scale = 2
    )
    private BigDecimal balance;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected BankAccount() {
        // JPA
    }

    public BankAccount(BigDecimal initialBalance) {
        Objects.requireNonNull(initialBalance, "initialBalance");

        if (initialBalance.signum() < 0) {
            throw new IllegalArgumentException(
                "Initial balance must not be negative");
        }
        this.balance = initialBalance;
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

    public void debit(BigDecimal amount) {
        requirePositive(amount);

        if (balance.compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient balance");
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
                "Amount must be positive");
        }
    }
}
```

Tại sao dùng `BigDecimal`?

- Tiền tệ không nên được mô hình hóa bằng `double`/`float` nếu cần tính toán chính xác theo thang số thập phân.
- `@Column(precision=19, scale=2)` chỉ định metadata cột tiền trong ví dụ.
- Nghiệp vụ thực tế còn cần quản lý currency, rounding policy, ledger/audit và những quy tắc kế toán khác.
- `@Version` giúp optimistic locking trong một số tình huống concurrent update, nhưng **không thay thế** kiểm soát giao dịch và các ràng buộc nghiệp vụ.

### 8.2. Schema minh họa

```sql
CREATE TABLE bank_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT chk_bank_accounts_balance
        CHECK (balance >= 0)
);
```

Cú pháp IDENTITY phụ thuộc database. Constraint `CHECK (balance >= 0)` là lớp bảo vệ cuối cùng cho invariant không âm, nhưng không tự giải quyết tất cả tình huống đồng thời hoặc ledger nhiều bên.

### 8.3. Service RESOURCE_LOCAL dùng TransactionRunner

```java
package demo.service;

import demo.domain.BankAccount;
import demo.persistence.TransactionRunner;

import jakarta.persistence.EntityManagerFactory;

import java.math.BigDecimal;
import java.util.Objects;

public class TransferService {

    private final EntityManagerFactory emf;

    public TransferService(EntityManagerFactory emf) {
        this.emf = Objects.requireNonNull(emf, "emf");
    }

    public void transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        if (Objects.equals(fromId, toId)) {
            throw new IllegalArgumentException(
                "Source and destination must differ");
        }

        TransactionRunner.execute(emf, em -> {
            BankAccount from = em.find(
                BankAccount.class, fromId);

            BankAccount to = em.find(
                BankAccount.class, toId);

            if (from == null || to == null) {
                throw new IllegalArgumentException(
                    "Bank account not found");
            }

            from.debit(amount);
            to.credit(amount);

            return null;
        });
    }
}
```

Trong trường hợp bình thường:

1. TransactionRunner tạo EM và bắt đầu transaction.
2. Service tải hai `BankAccount` là managed.
3. `from.debit(amount)` giảm số dư nguồn.
4. `to.credit(amount)` tăng số dư đích.
5. JPA dirty checking đồng bộ các UPDATE khi flush/commit.
6. `commit()` xác nhận hai cập nhật thuộc cùng transaction.

Nếu `from.debit` phát sinh `IllegalStateException` do thiếu tiền, lệnh `credit` không chạy và transaction được rollback.

Nếu UPDATE thứ hai thất bại ở flush/commit do database hoặc optimistic locking, transaction không được xác nhận một nửa theo transaction semantics. Nhưng **không nên coi ví dụ này đã đủ làm hệ thống chuyển tiền thực tế**: production cần nhiều lớp như ledger, idempotency, audit, quy tắc chống double-spend, isolation phù hợp, xử lý commit outcome và bảo mật.

### 8.4. SQL ở mức ý tưởng

Với dữ liệu:

```text
BankAccount#1: balance = 500.00
BankAccount#2: balance = 100.00
```

Chuyển `120.00`:

```sql
BEGIN;

UPDATE bank_accounts
SET balance = 380.00,
    version = version + 1
WHERE id = 1 AND version = ?;

UPDATE bank_accounts
SET balance = 220.00,
    version = version + 1
WHERE id = 2 AND version = ?;

COMMIT;
```

Đây là SQL mô phỏng ý nghĩa; provider có thể thay đổi thứ tự UPDATE, cách tăng version và các alias/parameter. Một số provider có thể chỉ gửi SQL ở giai đoạn commit.

Nếu transaction rollback, kết quả dữ liệu đã commit trước đó vẫn là `500.00` và `100.00`. Không có trạng thái hợp lệ mà nguồn đã bị trừ còn đích chưa được cộng **trong cùng transaction đã rollback**.

---

## 9. Các vị trí có thể phát sinh lỗi

Một transaction có nhiều điểm thất bại, không chỉ phần business code.

| Vị trí lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Trước `begin()` | Input thiếu, số tiền âm | Trả lỗi sớm; không cần tạo TX nếu chưa bắt đầu |
| `begin()` | Transaction đã active, resource/connection lỗi | Catch và kiểm tra active trước khi rollback |
| `find()/query` | JDBC exception, timeout, SQL không hợp lệ | Rollback nếu active, không tiếp tục unit of work lỗi |
| Business validation | Không đủ tiền, vi phạm invariant | Ném exception và rollback |
| `persist()/remove()` | Mapping/lifecycle không hợp lệ | Rollback nếu active |
| `flush()` | NOT NULL/FK/UNIQUE/optimistic lock conflict | Rollback; không coi context cũ là sạch |
| `commit()` | Constraint phát hiện muộn, deadlock, connection failure | Xử lý exception, trạng thái TX và khả năng outcome không rõ |
| `rollback()` | Kết nối hỏng, transaction manager gặp lỗi | Bảo toàn lỗi gốc + lưu lỗi rollback thành suppressed |
| `close()` | Resource cleanup lỗi | Không che lỗi chính; phân biệt lỗi cleanup với transaction failure |

### 9.1. Lỗi có thể đến muộn ở commit

Ví dụ:

```java
tx.begin();

Customer customer = new Customer("A");
em.persist(customer);

tx.commit(); // Có thể mới phát hiện UNIQUE/FK constraint.
```

Không có exception ngay tại `persist` **không có nghĩa** dữ liệu đã hợp lệ. Provider có thể trì hoãn SQL đến `flush` hoặc `commit`, nên khối catch phải bao gồm **cả lời gọi `commit()`**.

### 9.2. Ranh giới transaction không chỉ bao quanh một phương thức repository

Giả sử một nghiệp vụ cần:

```text
1. Tạo đơn hàng.
2. Trừ tồn kho.
3. Ghi sự kiện vào outbox database.
4. Commit.
```

Nếu mỗi bước dùng một transaction riêng, bước 1 có thể commit trước khi bước 2 thất bại. Kết quả không còn nguyên tử.

Nên xác định **unit of work ở tầng service** và để các repository thao tác trong cùng transaction phù hợp. Đừng tạo/commit transaction riêng ở mỗi repository method nếu chúng là một phần của cùng nghiệp vụ nguyên tử.

---

## 10. Xử lý lỗi ở flush()

`flush()` là điểm hữu ích để buộc provider đồng bộ và phát hiện sớm một số lỗi trước khi chạy logic tiếp theo.

```java
tx.begin();

try {
    em.persist(order);
    em.flush(); // Có thể ném PersistenceException.

    // Chỉ chạy tiếp nếu flush không báo lỗi.
    updateOtherTables(em);

    tx.commit();
} catch (RuntimeException | Error failure) {
    rollbackIfActive(tx, failure);
    throw failure;
}
```

Tại sao có thể gọi flush sớm?

- Muốn phát hiện constraint violation trước khi làm một bước tính toán tốn kém.
- Muốn có dữ liệu database cần thiết để chạy query tiếp theo trong cùng transaction.
- Muốn xác định lỗi phát sinh ở một nhóm thao tác cụ thể.

Tuy nhiên:

- Flush **không phải** commit.
- Flush có thể tăng round-trip và giảm khả năng batching.
- Không nên thêm `flush()` sau mọi `persist()` một cách máy móc.
- Nếu flush ném lỗi, transaction có thể đã bị đánh dấu rollback-only; không nên cố “chữa” field rồi tiếp tục commit như chưa có gì xảy ra.

### 10.1. Không sửa lỗi bằng cách bỏ flush

Nếu một `INSERT` vi phạm `NOT NULL` và bạn xóa lời gọi `em.flush()`, lỗi thường chỉ chuyển tới lần flush khác hoặc commit. Bản chất là schema/invariant/mapping không hợp lệ, không phải flush “gây lỗi”.

Cần sửa input, association, constraint hoặc nghiệp vụ; sau failure, rollback unit of work rồi thử lại từ trạng thái hợp lệ trong context mới.

### 10.2. FlushMode.AUTO và truy vấn

Trong `FlushModeType.AUTO`, một JPQL query có thể khiến provider đồng bộ những thay đổi liên quan để bảo đảm kết quả query phù hợp:

```java
em.setFlushMode(FlushModeType.AUTO);
```

Vì vậy, exception do ghi dữ liệu có thể xuất hiện **ở một câu query tưởng chỉ đọc**, không nhất thiết đúng dòng `persist`/`update`. Điều này càng củng cố lý do mọi thao tác nằm trong một khối xử lý transaction thống nhất.

---

## 11. Rollback-only: giao dịch đã bị đánh dấu không thể commit

JPA `EntityTransaction` có API:

```java
tx.setRollbackOnly();
boolean rollbackOnly = tx.getRollbackOnly();
```

Các phương thức này dành cho tình huống transaction phù hợp đang active. Khi transaction bị đánh dấu **rollback-only**, ứng dụng không được kỳ vọng commit thành công; thao tác commit có thể dẫn đến rollback và exception theo quy tắc JPA.

### 11.1. Khi nào đánh dấu rollback-only?

Giả sử tầng xử lý phát hiện invariant bị vi phạm nhưng không muốn ném exception ở đúng vị trí đó:

```java
if (!businessRuleSatisfied) {
    tx.setRollbackOnly();
}
```

Sau đó luồng xử lý phải dừng/đưa ra kết quả lỗi đúng cách. Nếu vẫn chạy hết business flow rồi gọi commit, commit không thể xác nhận transaction đã được đánh dấu rollback-only.

Trong hầu hết use case RESOURCE_LOCAL, **ném exception rõ ràng** sau khi phát hiện lỗi thường đơn giản hơn: helper catch và rollback. `setRollbackOnly` phù hợp trong một số cơ chế hạ tầng hoặc khi cần buộc transaction bị hủy mặc dù caller có xử lý exception.

### 11.2. Tránh đọc rollback-only ngoài transaction

```java
tx.getRollbackOnly();
```

có thể không hợp lệ nếu transaction không active. Không gọi để “hỏi transaction vừa commit trước đó có rollback-only không”. Trạng thái transaction phải được hiểu theo lifecycle hiện tại và kết quả phương thức transaction manager.

### 11.3. Một số exception khiến transaction bị rollback-only

Sau exception từ provider, transaction có thể đã được đánh dấu rollback-only hoặc không còn hợp lệ để tiếp tục. Đừng giả định mọi `PersistenceException` đều cho phép sửa dữ liệu và tiếp tục trong cùng context.

Nếu đã có exception trong một thao tác ghi của JPA, một cách an toàn là rollback, đóng EM hoặc clear phù hợp, rồi bắt đầu unit of work mới. Không nên bắt lỗi constraint, bỏ qua rồi vẫn commit những thay đổi trước đó trừ khi bạn đã hiểu chính xác contract của provider và transaction manager.

---

## 12. Lỗi ở commit: điều gì được bảo đảm, điều gì không?

Một tình huống thường bị đơn giản hóa:

```java
try {
    tx.commit();
} catch (RuntimeException ex) {
    // "Chắc chắn chưa ghi gì" — kết luận này có thể sai.
}
```

Nếu commit ném exception vì database từ chối transaction, ứng dụng biết commit **không báo thành công**, và thường transaction bị rollback theo cơ chế phù hợp.

Nhưng nếu lỗi đến từ **mất kết nối đúng thời điểm commit**, client có thể không biết database đã xác nhận commit hay chưa. Ví dụ:

```text
Application                     Database
    |                              |
    | -------- COMMIT ------------>|
    |                              | commit thành công
    |<------ connection lost ------X
    |
    | nhận network exception
    | không chắc DB có commit hay không
```

Đây là trường hợp **ambiguous commit outcome**. Cố gọi rollback không thể đảm bảo đảo ngược một transaction đã thực sự commit ở database.

### 12.1. Vì sao retry mù quáng nguy hiểm?

Với nghiệp vụ “tạo đơn hàng”:

```text
Lần 1:
    INSERT order
    Database COMMIT
    Mất kết nối trước khi application nhận ACK

Ứng dụng tưởng thất bại, retry lần 2:
    INSERT order lần nữa
    Database COMMIT

Kết quả: hai đơn hàng cho một yêu cầu.
```

Cần cơ chế như:

- **Idempotency key** ổn định cho một yêu cầu nghiệp vụ.
- Database `UNIQUE` trên khóa yêu cầu/natural key phù hợp.
- Kiểm tra trạng thái bằng một truy vấn độc lập sau khi resource phục hồi.
- Retry có giới hạn và có chính sách theo loại lỗi.
- Transaction boundary rõ ràng; không retry bằng graph JPA vừa gặp lỗi.

### 12.2. Idempotency key ở mức dữ liệu

Ví dụ bảng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(80) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL
);
```

Nếu một API nhận cùng `request_key` hai lần, database constraint có thể ngăn tạo hai order trùng yêu cầu. Ứng dụng phải định nghĩa rõ khi duplicate key: đọc lại kết quả đã tạo, so sánh payload và trả phản hồi phù hợp; không chỉ nuốt constraint violation rồi coi là thành công.

**Idempotency không đồng nghĩa retry vô điều kiện.** Nó là thiết kế nghiệp vụ để nhiều lần thực thi cùng một yêu cầu không tạo thêm tác động không mong muốn.

---

## 13. Lỗi rollback và nguyên tắc bảo toàn lỗi

Khi rollback thất bại, cần báo cáo trung thực rằng không thể xác nhận transaction đã được hủy bằng lời gọi đó.

Sai:

```java
try {
    doWork();
    tx.commit();
} catch (RuntimeException e) {
    tx.rollback(); // Nếu lỗi, exception ban đầu có thể bị che.
    throw e;
}
```

Cách cẩn thận hơn:

```java
catch (RuntimeException | Error failure) {
    try {
        if (tx.isActive()) {
            tx.rollback();
        }
    } catch (RuntimeException rollbackError) {
        failure.addSuppressed(rollbackError);
    }

    throw failure;
}
```

Nếu log exception:

```java
logger.error("Transaction failed", failure);
```

nhiều logging framework sẽ hiển thị cả suppressed exceptions. Khi quan sát, cần phân biệt:

- Lỗi chính: ví dụ vi phạm UNIQUE constraint.
- Lỗi rollback: ví dụ kết nối DB không còn hoạt động.
- Lỗi close: lỗi giải phóng resource.
- Trạng thái commit cuối cùng: đã biết thành công, đã biết rollback, hay có thể không rõ.

Không nên “báo rollback thành công” chỉ vì code **đã thử gọi rollback**; muốn khẳng định phải dựa vào kết quả thực tế và khả năng transaction manager báo cáo.

---

## 14. Không tái sử dụng EntityManager như chưa có gì sau rollback

Một transaction thất bại có thể để object Java chứa những thay đổi chưa được commit:

```java
tx.begin();

Account source = em.find(Account.class, sourceId);
source.debit(amount);

tx.rollback();

// Object source có thể vẫn giữ số dư đã bị giảm trong bộ nhớ.
```

Database đã rollback không có nghĩa setter Java tự được đảo ngược. Tùy scope/provider, các entity có thể bị detach hoặc state của persistence context không còn phù hợp để tiếp tục.

### 14.1. Cách tiếp tục an toàn

```text
Giao dịch thất bại
    |
    +-- rollback nếu còn active
    |
    +-- kết thúc unit of work
    |
    +-- close/clear context phù hợp
    |
    +-- mở transaction và context mới
    |
    +-- load lại entity từ database
    |
    +-- tái áp dụng input nghiệp vụ hợp lệ
```

Không nên lấy object cũ sau rollback rồi gọi `em.merge` vào transaction mới mà không kiểm tra, vì bạn có thể vô tình ghi lại chính các thay đổi đáng lẽ bị hủy.

### 14.2. Generated ID sau rollback

Với `GenerationType.IDENTITY` hoặc sequence, entity mới có thể đã nhận ID trước khi transaction rollback. ID đó **không phải bằng chứng** bản ghi đã commit.

Nếu cần retry tạo entity, thường nên tạo **object mới từ dữ liệu yêu cầu** sau khi xác định outcome và idempotency, thay vì `persist` lại object bị rollback còn giữ generated ID. Provider có thể xem object cũ là detached hoặc báo lỗi state.

### 14.3. Rollback không phải undo bên ngoài DB

Nếu đã làm:

```java
tx.begin();
em.persist(order);
emailSender.sendOrderConfirmation(order);
tx.rollback();
```

email có thể đã gửi thành công dù order bị rollback. Transaction database không thể kéo email quay lại hộp thư người nhận.

Các tác động ngoại vi như email, message broker, gọi thanh toán, ghi object storage hoặc HTTP API cần chiến lược phối hợp riêng. Một phương án phổ biến là **transactional outbox**: ghi sự kiện vào một bảng outbox **trong cùng transaction** với dữ liệu nghiệp vụ, rồi một worker gửi sau commit. Cần cơ chế retry/idempotency ở phía worker để xử lý gửi lặp.

---

## 15. Kiểm tra điều kiện nghiệp vụ trước khi commit

Một use case thường gồm:

```text
begin()
    |
    +-- load entities
    +-- kiểm tra quyền/điều kiện nghiệp vụ
    +-- thay đổi dữ liệu
    +-- có thể flush
    |
commit()
```

Ví dụ:

```java
tx.begin();

try {
    InventoryItem item = em.find(
        InventoryItem.class, itemId);

    if (item == null) {
        throw new IllegalArgumentException("Item not found");
    }

    if (item.getAvailableQuantity() < requested) {
        throw new IllegalStateException("Insufficient inventory");
    }

    item.reserve(requested);

    tx.commit();
} catch (RuntimeException | Error failure) {
    rollbackIfActive(tx, failure);
    throw failure;
}
```

Code minh họa giả định có entity `InventoryItem` với getter và domain method `reserve`. Validation trước update giúp trả lỗi có ý nghĩa, nhưng trong hệ thống đồng thời còn cần:

- Optimistic locking (`@Version`).
- Pessimistic locking nếu phù hợp.
- Constraint database để bảo vệ invariant.
- Transaction isolation và chính sách retry có kiểm soát.

**Không đủ** chỉ dùng `if (quantity >= requested)` để chống hai transaction đồng thời đặt cùng lượng tồn kho. Cần bảo đảm dữ liệu kiểm tra và cập nhật nằm trong cơ chế concurrency phù hợp.

---

## 16. Optimistic locking và rollback transaction

Với entity có:

```java
@Version
private Long version;
```

provider có thể kiểm tra version khi UPDATE/DELETE.

```text
TX A đọc Product#10, version=5.
TX B đọc Product#10, version=5.

TX B:
  thay đổi, commit -> version=6.

TX A:
  thay đổi, flush/commit với version=5.
  -> optimistic locking conflict.
  -> transaction không thể hoàn tất như mong muốn.
```

JPA có thể phát sinh `OptimisticLockException` tại flush hoặc commit, không nhất thiết tại setter.

Mẫu xử lý:

```java
try {
    tx.begin();

    Product product = em.find(Product.class, productId);
    product.adjustStock(delta);

    tx.commit();
} catch (RuntimeException | Error failure) {
    rollbackIfActive(tx, failure);
    throw failure;
}
```

Code trên chỉ là bộ khung, giả định entity `Product` có `adjustStock`. Nếu cần retry khi optimistic conflict:

1. Xác định exception có thực sự là conflict có thể retry.
2. Rollback và giải phóng context cũ.
3. Mở transaction mới, đọc version và dữ liệu mới.
4. Kiểm tra lại quy tắc nghiệp vụ.
5. Áp dụng lại **ý định** thay đổi, không copy cả state cũ.
6. Commit, giới hạn số lần retry.

Không retry cho mọi `PersistenceException`; syntax error, mapping sai, thiếu bảng, quyền không hợp lệ thường không tự hết khi chạy lại.

---

## 17. Spring @Transactional: phiên bản khai báo của begin/commit/rollback

Trong Spring Data JPA, service thường dùng:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Order order = Order.createFrom(command);

        orderRepository.save(order);

        return order.getId();
    }
}
```

`OrderRepository`, `CreateOrderCommand` và `Order` là các thành phần domain của ứng dụng giả định.

Theo cấu hình Spring proxy thông dụng:

1. Lời gọi tới service đi qua transaction interceptor.
2. Transaction manager bắt đầu hoặc tham gia transaction hiện hành.
3. Repository làm việc với EntityManager/context được quản lý cho transaction.
4. Nếu method hoàn tất bình thường, transaction manager cố commit.
5. Nếu exception cần rollback thoát khỏi method, transaction manager rollback theo policy.
6. Resource được dọn theo framework; service không tự `em.close()` trên injected EntityManager.

### 17.1. Spring rollback theo loại exception

Trong cách cấu hình Spring mặc định phổ biến, rollback tự động áp dụng khi method ném **unchecked `RuntimeException` hoặc `Error`**; với **checked exception** thông thường, transaction có thể vẫn commit nếu không cấu hình thêm.

Ví dụ checked business exception:

```java
public class PaymentRejectedException extends Exception {

    public PaymentRejectedException(String message) {
        super(message);
    }
}
```

Nếu muốn rollback với loại exception đó:

```java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void confirmPayment(PaymentCommand command)
        throws PaymentRejectedException {

    // Ghi dữ liệu, kiểm tra nghiệp vụ...
    if (paymentRejected(command)) {
        throw new PaymentRejectedException("Payment rejected");
    }
}
```

`paymentRejected` và `PaymentCommand` là logic nghiệp vụ giả định. Spring có thể được cấu hình chính sách rollback mặc định khác, nên phải kiểm tra version và transaction config thực tế thay vì tuyệt đối hóa mọi ứng dụng Spring.

### 17.2. Đừng nuốt RuntimeException trong @Transactional

Ví dụ nguy hiểm:

```java
@Transactional
public void createOrder(CreateOrderCommand command) {
    try {
        repository.save(createEntity(command));
    } catch (RuntimeException ex) {
        logger.error("Create order failed", ex);
        // Method trở về bình thường: interceptor có thể cố commit.
    }
}
```

Nếu lỗi bị bắt rồi nuốt, interceptor có thể thấy method thành công và thực hiện commit, trừ khi transaction/provider đã đánh dấu rollback-only. Kết quả có thể là partial changes hoặc `UnexpectedRollbackException` tùy tình huống.

Hướng tốt hơn là:

- Ném lại exception hoặc chuyển sang exception phù hợp vẫn kích hoạt rollback.
- Nếu bắt buộc trả kết quả không ném exception, cần đánh dấu transaction rollback-only theo cách Spring hỗ trợ.
- Không đánh dấu rollback-only rồi tiếp tục xử lý như thể có thể commit.

Ví dụ dùng API Spring:

```java
import org.springframework.transaction.interceptor
    .TransactionAspectSupport;

@Transactional
public OperationResult attemptOperation(Command command) {
    try {
        performOperation(command);
        return OperationResult.success();
    } catch (KnownBusinessException ex) {
        TransactionAspectSupport
            .currentTransactionStatus()
            .setRollbackOnly();

        return OperationResult.failed(ex.getMessage());
    }
}
```

Đoạn này minh họa trường hợp có yêu cầu trả object lỗi thay vì ném exception; `OperationResult`, `KnownBusinessException` và `Command` là các type ứng dụng. Nó phụ thuộc vào việc code thực sự chạy trong transaction được Spring interceptor quản lý. Trong nhiều dự án, ném exception và để tầng API chuyển thành response lỗi vẫn đơn giản, rõ ràng hơn.

### 17.3. @Transactional self-invocation

Ví dụ:

```java
@Service
public class PaymentService {

    public void outer() {
        inner(); // Gọi trực tiếp cùng instance.
    }

    @Transactional
    public void inner() {
        // ...
    }
}
```

Ở chế độ Spring proxy AOP phổ biến, lời gọi nội bộ `inner()` từ cùng object thường **không đi qua proxy**, nên annotation `@Transactional` của `inner` có thể không được áp dụng như dự định.

Giải pháp phổ biến là đặt transactional boundary ở public service method được gọi từ bên ngoài proxy, hoặc tách một service hợp lý và gọi qua bean proxy. Không nên nghĩ “có annotation trên method” là đủ để bảo đảm giao dịch đã bắt đầu.

---

## 18. Transaction propagation và nguy cơ commit một phần

Spring có các propagation policy. Hai loại thường gặp:

- `Propagation.REQUIRED`: tham gia transaction hiện hành nếu có, nếu không thì tạo mới.
- `Propagation.REQUIRES_NEW`: mở một transaction độc lập, tạm đình chỉ transaction bên ngoài theo cơ chế transaction manager.

Ví dụ:

```java
@Transactional
public void placeOrder() {
    // Transaction A.
    orderRepository.save(order);

    inventoryService.reserveInNewTransaction(...);
    // Transaction B có thể đã commit độc lập.
}
```

Nếu `reserveInNewTransaction` thực sự chạy với `REQUIRES_NEW` qua Spring proxy, reservation có thể commit riêng dù transaction A về sau rollback. Khi hai thao tác phải cùng nguyên tử, đây có thể là **thiết kế sai**.

### 18.1. Một transaction cho một use case nguyên tử

Nếu tạo Order và trừ Inventory phải cùng thành công:

```java
@Transactional
public void placeOrder(CreateOrderCommand command) {
    Order order = createOrder(command);
    reserveInventory(command);
    saveOrder(order);
}
```

Các repository/service bên trong nên tham gia transaction hiện hành theo thiết kế, không tự ý commit riêng. Điều này không có nghĩa mọi lời gọi service phải gộp vào một transaction dài; cần định nghĩa unit of work theo invariant nghiệp vụ.

### 18.2. REQUIRES_NEW đôi khi có mục đích riêng

Ví dụ ghi nhận audit về việc một nghiệp vụ thất bại trong transaction độc lập. Khi đó commit audit dù transaction chính rollback có thể là yêu cầu hợp lệ.

Cần mô tả rõ kết quả của từng transaction thay vì giả định tất cả đều rollback theo transaction bên ngoài. Nếu audit mang tính bảo mật/tuân thủ, vẫn cần cân nhắc lỗi audit và tính nhất quán.

### 18.3. UnexpectedRollbackException

Một transaction bên trong có thể đánh dấu cùng transaction hiện hành rollback-only rồi ném exception; tầng ngoài bắt exception và muốn commit tiếp. Khi outer commit, Spring có thể báo `UnexpectedRollbackException` vì transaction đã bị đánh dấu không thể commit.

Điều này là tín hiệu cần thiết: caller không được nhận kết quả “thành công” khi những thay đổi đã bị rollback. Đừng cố nuốt exception rồi tuyên bố giao dịch đã commit.

---

## 19. JTA: ai gọi begin/commit/rollback?

Trong môi trường Jakarta EE, container có thể quản lý transaction qua JTA và component transaction attributes. Với declarative transaction, ứng dụng tập trung vào nghiệp vụ:

```java
@Stateless
public class OrderApplicationService {

    @PersistenceContext
    private EntityManager em;

    public void createOrder(OrderData input) {
        Order order = new Order(input);
        em.persist(order);
    }
}
```

Ví dụ giả định dùng Jakarta Enterprise Beans với container-managed transaction mặc định thích hợp; `Order` và `OrderData` là các class domain. Container bắt đầu/tham gia transaction, cố commit khi method kết thúc, rollback theo chính sách exception/transaction attributes.

### 19.1. UserTransaction cho trường hợp programmatic JTA

Trong một số môi trường cho phép quản lý JTA bằng chương trình, có `jakarta.transaction.UserTransaction`:

```java
@Resource
private UserTransaction userTransaction;
```

API cung cấp các phương thức như `begin()`, `commit()`, `rollback()`. Tuy nhiên:

- Chỉ dùng ở component/môi trường cho phép bean-managed transaction.
- Không điều khiển JTA bằng `EntityManager.getTransaction()`.
- Nếu EntityManager không tự đồng bộ với JTA, cần hiểu `joinTransaction()` và synchronization type.
- Xử lý checked exceptions từ JTA API theo contract.
- Không tự lồng `begin()` trên cùng transaction mà không có cơ chế nesting thích hợp.

### 19.2. Khi cần đánh dấu rollback ở container-managed transaction

Ở các container-managed component, có thể dùng API container/transaction manager phù hợp để đánh dấu rollback-only thay vì tự gọi `UserTransaction.rollback()` trên một transaction do container sở hữu.

Mục tiêu giống nhau: ngăn transaction bị commit khi nghiệp vụ có lỗi. Cơ chế cụ thể khác `RESOURCE_LOCAL` nên không sao chép boilerplate `EntityTransaction` sang mọi môi trường.

### 19.3. JTA có thể bao gồm nhiều resource

JTA có khả năng điều phối giao dịch qua nhiều resource theo cấu hình transaction manager và khả năng XA của resource. Tuy nhiên, **không phải mọi kết nối hoặc service đều mặc nhiên được enlist** trong JTA transaction. HTTP API, gửi email hoặc những message không được phối hợp transaction phù hợp vẫn có thể có tác động ngoài giao dịch.

Không dùng tên “JTA” để khẳng định mọi thứ trong một method đều rollback được.

---

## 20. Transaction boundary, exception và tầng API

Một API backend thường phân tầng:

```text
Controller
   |
   v
Application Service
   |    <- transaction boundary ở đây
   +--> Repository A
   +--> Repository B
   +--> Domain validation
   +--> Outbox repository
   |
   v
Commit
   |
   v
Response
```

Tầng controller không nên báo thành công trước khi service transaction đã hoàn tất theo semantics framework. Đồng thời, controller cần chuyển exception thành HTTP response phù hợp.

Ví dụ:

| Tình huống | Phản hồi API có thể phù hợp |
|---|---|
| Validation request không hợp lệ | 400 |
| Không đủ tồn kho/vi phạm quy tắc domain | 409 hoặc mã lỗi nghiệp vụ đã thống nhất |
| Optimistic locking conflict | 409 |
| Không có resource | 404 |
| DB unavailable | 503 hoặc 500 tùy kiến trúc |
| Commit outcome không xác định | Response lỗi với idempotency/reconciliation policy |
| Thành công và đã commit | 200/201 theo semantics API |

Bảng chỉ gợi ý định hướng HTTP; không phải quy tắc cố định của JPA. Quan trọng là **đừng chuyển exception transaction thành response “thành công”** nếu không có căn cứ về kết quả bền vững.

### 20.1. Logging ở đâu?

Không cần mỗi tầng đều log cùng một stack trace như lỗi mới. Một cách quản lý là:

- Tầng transaction helper/service xử lý rollback và ném lỗi.
- Tầng API boundary log lỗi có context an toàn, correlation ID và trả response.
- Logging không đưa password, dữ liệu nhạy cảm hoặc SQL parameter nhạy cảm lên log công khai.
- Nếu rollback/close thất bại, log suppressed exceptions đi cùng lỗi chính.

### 20.2. Không bắt exception quá rộng rồi tiếp tục

Sai:

```java
catch (Exception ex) {
    logger.warn("Ignored", ex);
}
tx.commit();
```

Bắt mọi exception để “giữ hệ thống hoạt động” có thể khiến transaction bị ghi một phần hoặc commit khi invariant đã bị vi phạm. Nếu lỗi làm use case không còn hợp lệ, transaction phải bị hủy và caller cần biết outcome.

---

## 21. Tác động ngoài database: chọn đúng thời điểm

Một lỗi phổ biến:

```java
tx.begin();

Order order = createOrder();
em.persist(order);

paymentGateway.charge(order.getTotal());
emailSender.sendConfirmation(order);

tx.commit();
```

Nếu charge thành công, email đã gửi, nhưng commit DB thất bại, transaction database không thể đảo ngược các tác động ngoài nó. Ngược lại, nếu commit DB thành công nhưng network timeout làm ứng dụng tưởng thất bại, retry có thể charge hai lần nếu thiếu idempotency.

### 21.1. Transactional outbox

Một giải pháp phổ biến để gửi sự kiện sau commit:

```text
BEGIN DB TRANSACTION
    INSERT purchase_orders(...)
    INSERT outbox_events(..., event_id, payload, status='NEW')
COMMIT

Worker đọc outbox_events đã commit
    |
    +-- gửi message/email qua hệ thống ngoài
    +-- đánh dấu đã gửi
    +-- retry khi lỗi
```

Cả Order và OutboxEvent được ghi trong cùng database transaction. Nếu rollback, cả hai bản ghi không được xác nhận. Worker chỉ thấy outbox đã commit theo chính sách isolation của DB.

Tuy nhiên, outbox **không tự bảo đảm exactly-once delivery**. Worker có thể gửi rồi gặp lỗi trước khi đánh dấu “đã gửi”; event được gửi lần nữa khi retry. Người nhận/cơ chế gửi cần idempotency hoặc deduplication phù hợp.

### 21.2. Không giải quyết bằng cách giữ transaction mở trong lúc chờ network

Gọi HTTP service chậm bên trong transaction database có thể giữ lock/connection lâu, tăng deadlock, timeout và giảm throughput. Nên thiết kế workflow/outbox/saga cho các tác động dài hoặc phân tán.

Transaction ngắn không đồng nghĩa phải bỏ tính nhất quán: có thể dùng outbox, state machine và các bước xác nhận/hủy bù theo kiến trúc phù hợp.

---

## 22. Trường hợp yêu cầu savepoint hoặc transaction lồng

`EntityTransaction` không định nghĩa API portable kiểu:

```java
tx.begin();
tx.begin(); // Không phải cách mở nested transaction JPA.
```

Nếu use case cần rollback riêng một phần mà giữ transaction ngoài, có thể cần:

- JDBC savepoint trong một môi trường được kiểm soát.
- Cơ chế transaction manager hỗ trợ nested propagation.
- Chia transaction và thiết kế lại invariant.
- Một workflow bù trừ, saga hoặc outbox.

Không tự ý trộn thao tác JDBC trên connection với JPA EntityManager mà không kiểm soát flush, persistence context, connection enlistment và transaction manager. Bulk SQL/JDBC có thể làm trạng thái managed entity bị stale.

### 22.1. Bulk JPQL cũng cần transaction

```java
int updated = em.createQuery(
    "update InventoryItem i " +
    "set i.reserved = i.reserved + :amount " +
    "where i.id = :id"
)
.setParameter("amount", amount)
.setParameter("id", id)
.executeUpdate();
```

Bulk update yêu cầu transaction phù hợp và có thể bỏ qua dirty checking trên từng managed entity; context có thể còn giữ dữ liệu cũ. Sau bulk operation, phải xử lý flush/clear/refresh theo chiến lược thích hợp.

Đừng dùng bulk query để “vượt qua” transaction failure mà không làm rõ consistency. Nó là một dạng thao tác database khác trong cùng transaction boundary.

---

## 23. Bài thực hành: thử từng nhánh begin/commit/rollback

Có thể dùng Java SE với một JPA provider và database quan hệ để quan sát SQL/transaction.

### 23.1. persistence.xml tham khảo

File `src/main/resources/META-INF/persistence.xml` dành cho Hibernate ORM và H2:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
             version="3.0">

    <persistence-unit name="shopPU"
                      transaction-type="RESOURCE_LOCAL">

        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.domain.BankAccount</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:transaction_demo;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>

            <!-- Chỉ dùng với database học tập. -->
            <property name="hibernate.hbm2ddl.auto"
                      value="create-drop"/>
            <property name="hibernate.show_sql"
                      value="true"/>
            <property name="hibernate.format_sql"
                      value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Cần dependency tương thích cho Jakarta Persistence API, Hibernate ORM provider và H2 JDBC driver. `hibernate.hbm2ddl.auto=create-drop` có thể xóa dữ liệu, nên **không dùng trên production database**.

### 23.2. Phần A — Transaction thành công

1. Tạo hai tài khoản với số dư `500.00` và `100.00`.
2. Dùng `TransactionRunner` để persist từng tài khoản hoặc cùng một transaction.
3. Ghi lại ID sau commit.
4. Chạy service chuyển `120.00` từ tài khoản A sang B.
5. Mở EntityManager mới đọc hai số dư.
6. Kết quả mong đợi: `380.00` và `220.00`.
7. Quan sát thời điểm SQL UPDATE và commit.

Đây là đường đi bình thường:

```text
begin -> load -> debit -> credit -> commit -> close
```

### 23.3. Phần B — Business validation thất bại

1. Tiếp tục với tài khoản A còn `380.00`.
2. Thử chuyển `999.00`.
3. `debit` ném `IllegalStateException`.
4. TransactionRunner gọi rollback nếu transaction còn active.
5. Mở EM mới, kiểm tra hai số dư không đổi.
6. Xác nhận tầng gọi nhận lỗi, không nhận phản hồi thành công.

Đường đi:

```text
begin -> load -> validation failure -> rollback -> close
```

### 23.4. Phần C — Constraint violation tại flush

1. Thêm constraint `CHECK (balance >= 0)` hoặc một bảng thử có `UNIQUE`.
2. Tạo dữ liệu vi phạm constraint trong transaction.
3. Gọi `em.flush()` để quan sát exception xuất hiện ở đâu.
4. Bắt exception, rollback và close.
5. Đọc dữ liệu bằng EM mới để chứng minh không có hàng vi phạm được commit.
6. Thử bỏ flush và xem liệu lỗi có xuất hiện muộn ở commit không.

Không cố dùng lại transaction đã gặp lỗi ghi rồi tiếp tục commit.

### 23.5. Phần D — Lỗi sau khi đã sửa object Java

1. Tải tài khoản nguồn vào persistence context.
2. Gọi `debit` để làm giảm balance trong bộ nhớ.
3. Cố tình ném exception trước bước `credit`.
4. Rollback.
5. In số dư của object Java cũ (có thể đã giảm).
6. Dùng EM mới đọc số dư database đã commit.
7. Giải thích khác biệt giữa **rollback DB** và **khôi phục Java object**.

### 23.6. Phần E — Trường hợp commit phát hiện lỗi

1. Tạo mapping/constraint có thể phát hiện lỗi khi flush/commit.
2. Không gọi flush tường minh.
3. Gọi commit.
4. Quan sát exception và trạng thái transaction.
5. Ghi lại liệu rollback còn được phép/được gọi hay không.
6. Không khẳng định đã commit chỉ vì `persist()` trước đó không lỗi.

Không cần mô phỏng network failure thực tế nếu không có môi trường chaos testing; phần commit outcome không rõ có thể phân tích bằng timeline mô phỏng.

### 23.7. Phần F — Rollback cũng ném exception

Không cần phá kết nối database thật. Có thể kiểm tra ở mức unit test bằng một fake/mock `EntityTransaction` sao cho:

```text
doWork()      -> ném IllegalStateException("Business failed")
tx.isActive() -> true
tx.rollback() -> ném RuntimeException("Rollback failed")
```

Kết quả cần kiểm tra:

- Lỗi chính vẫn là `IllegalStateException("Business failed")`.
- Lỗi rollback nằm trong `getSuppressed()` của lỗi chính.
- Caller biết giao dịch không thành công và không coi rollback là chắc chắn đã hoàn tất.
- EntityManager vẫn được cố gắng close.

### 23.8. Phần G — Spring rollbackFor

1. Tạo Spring service `@Transactional` ném checked exception.
2. Quan sát policy rollback mặc định của version/config đang dùng.
3. Thêm `rollbackFor = CheckedException.class`.
4. Chạy lại và kiểm tra dữ liệu bằng transaction mới.
5. Thử bắt exception trong service rồi trả về bình thường.
6. So sánh với việc ném lại exception hoặc đánh dấu rollback-only.
7. Giải thích vì sao method trả về bình thường không luôn đồng nghĩa business operation hợp lệ.

### 23.9. Phần H — Idempotency và retry

1. Tạo bảng order có `request_key UNIQUE`.
2. Gửi hai lần cùng request key.
3. Xác minh không có hai order cho một yêu cầu.
4. Thiết kế phản hồi khi key đã tồn tại: tra lại kết quả và so sánh payload.
5. Mô phỏng tình huống mất ACK sau commit.
6. Giải thích vì sao retry không có idempotency có thể tạo trùng.

### 23.10. Bảng ghi kết quả

| Kịch bản | Điểm lỗi | Giao dịch cần làm gì? | Trạng thái DB kỳ vọng |
|---|---|---|---|
| Chuyển tiền hợp lệ | Không có | Commit | Hai số dư đổi đồng thời |
| Không đủ tiền | Business validation | Rollback | Không đổi |
| UNIQUE/FK/NOT NULL lỗi | Flush hoặc commit | Rollback nếu còn active; báo lỗi | Không có dữ liệu vi phạm được commit |
| Optimistic locking conflict | Flush/commit | Rollback; cân nhắc retry context mới | Không ghi đè im lặng |
| begin thất bại | `begin()` | Không commit; rollback nếu active | Không xác nhận unit of work |
| rollback thất bại | `rollback()` | Giữ lỗi gốc + suppressed | Outcome cần xác minh |
| close thất bại sau commit | Cleanup | Báo đúng loại lỗi | Commit có thể đã thành công |
| Mất kết nối lúc commit | `commit()` | Không retry mù; dùng idempotency/reconciliation | Có thể không rõ |
| SQL đã flush, sau đó rollback | Sau flush | Rollback | Thay đổi chưa commit bị hủy |
| Checked exception trong Spring | Business layer | Tùy rollback policy | Có thể commit nếu chưa cấu hình rollback |

---

## 24. Những lỗi lập trình phổ biến

### 24.1. Quên begin trước khi ghi

```java
em.persist(order);
em.flush();
```

Nếu transaction phù hợp chưa active, các thao tác yêu cầu transaction có thể ném `TransactionRequiredException` hoặc có hành vi provider-specific. Trong `RESOURCE_LOCAL`, hãy bắt đầu transaction trước các thao tác ghi.

### 24.2. Commit trong finally

Sai:

```java
try {
    performOperation();
} finally {
    tx.commit();
}
```

Khi `performOperation` ném exception, finally vẫn cố commit những thay đổi đã thực hiện trước lỗi. Đây là điều **không được làm** với một unit of work cần nguyên tử.

Commit chỉ nằm trên nhánh thành công, không phải nhánh cleanup vô điều kiện.

### 24.3. Rollback trong finally không kiểm tra trạng thái

Sai:

```java
try {
    tx.begin();
    performOperation();
    tx.commit();
} finally {
    tx.rollback();
}
```

Sau commit thành công, transaction thường không còn active. Rollback thêm có thể gây exception. Đặc biệt lỗi rollback có thể làm caller tưởng operation thất bại dù commit đã thành công.

### 24.4. Nuốt exception sau rollback

Sai:

```java
catch (RuntimeException ex) {
    tx.rollback();
    return OperationResult.success();
}
```

Một giao dịch rollback không thể được báo thành công chỉ vì “hệ thống đã bắt được lỗi”. Trả failure result hoặc ném lại exception theo API contract.

### 24.5. Bắt lỗi rollback làm mất lỗi gốc

Sai:

```java
catch (RuntimeException ex) {
    tx.rollback(); // Nếu rollback ném, ex bị che.
    throw ex;
}
```

Dùng suppressed exception hoặc cơ chế logging phù hợp.

### 24.6. Tưởng em.flush() đã commit

Sau flush, dữ liệu vẫn có thể rollback. Không gửi thông báo “đơn hàng đã xác nhận” chỉ vì SQL INSERT xuất hiện trong log.

### 24.7. Cố tiếp tục transaction sau PersistenceException

Nếu flush thất bại do constraint, JPA provider/transaction manager có thể đánh dấu rollback-only. Chỉnh sửa một field rồi commit tiếp thường không phải pattern đáng tin cậy. Rollback và tạo unit of work mới.

### 24.8. Dùng cùng EntityManager qua nhiều thread

`EntityManager` không an toàn để chia sẻ đồng thời giữa nhiều request/thread. `EntityManagerFactory` được tái sử dụng theo lifecycle ứng dụng; EntityManager được tạo/gắn theo unit of work thích hợp.

### 24.9. Nghĩ mọi RuntimeException đều retry được

Các lỗi validation như không đủ tiền hoặc permission denied không tự giải quyết sau vài lần retry. Chỉ retry khi chính sách nghiệp vụ và loại lỗi cho phép, với số lần giới hạn.

### 24.10. Không phân biệt lỗi commit với lỗi close

Một exception xảy ra sau `tx.commit()` thành công nhưng trong `em.close()` không chứng minh thao tác ghi đã rollback. Logging/monitoring và retry policy nên giữ được thông tin phase của lỗi.

### 24.11. Để một repository tự commit giữa nghiệp vụ

Nếu nghiệp vụ cần ba thay đổi cùng nguyên tử, đừng tự commit ở từng repository và kỳ vọng service bên ngoài rollback được tất cả. Xác định boundary ở tầng service.

### 24.12. Gọi em.getTransaction() trên JTA-managed EntityManager

API resource-local không phải API để điều khiển JTA. Trong Jakarta EE/Spring dùng transaction manager đúng cấu hình.

### 24.13. Dùng checked exception trong Spring mà quên rollback policy

Nếu method đánh dấu `@Transactional` ném checked exception, Spring có thể không rollback theo chính sách mặc định phổ biến. Dùng `rollbackFor` hoặc policy toàn ứng dụng phù hợp với loại lỗi.

### 24.14. Tự tạo transaction trong method nội bộ Spring không qua proxy

`@Transactional` trên method được gọi bằng self-invocation có thể không được áp dụng trong Spring proxy mode. Kiểm tra ranh giới thực tế thay vì dựa vào việc có annotation.

### 24.15. Gọi external API khi DB transaction còn mở rồi coi rollback là toàn diện

Rollback DB không hủy tác động bên ngoài. Dùng outbox/saga/idempotency hoặc kiến trúc điều phối phù hợp.

---

## 25. Checklist thiết kế transaction có xử lý lỗi

Trước khi hoàn tất một use case ghi dữ liệu bằng JPA, hãy trả lời:

| Câu hỏi | Điều cần quyết định |
|---|---|
| Ai sở hữu transaction? | RESOURCE_LOCAL, JTA hay Spring transaction manager |
| Khi nào bắt đầu? | Trước nhóm thao tác cần nguyên tử |
| Nghiệp vụ nào phải cùng transaction? | Ghi nhiều bảng theo một invariant |
| Khi nào commit? | Chỉ sau khi logic hợp lệ và không có lỗi ngăn xác nhận |
| Nếu begin lỗi? | Không commit; kiểm tra active trước rollback |
| Nếu business validation lỗi? | Rollback và trả lỗi đúng contract |
| Nếu flush lỗi? | Không tiếp tục dùng transaction như bình thường |
| Nếu commit lỗi? | Phân biệt fail/rollback với outcome không rõ do network |
| Nếu rollback cũng lỗi? | Bảo toàn lỗi gốc và gắn suppressed |
| Nếu close cũng lỗi? | Không che lỗi chính; không coi lỗi close là rollback |
| Entity còn dùng sau rollback? | Tải lại trong context mới khi cần |
| Có tác động ngoài DB? | Outbox, idempotency, saga hoặc cơ chế phối hợp |
| Có xử lý concurrent updates? | Version/locking/isolation/constraints |
| Có retry không? | Chỉ cho lỗi được phân loại, dùng unit of work mới và giới hạn |
| Có transaction propagation khác? | Đảm bảo không vô tình commit một phần |
| Có test nhánh lỗi? | Test begin, business, flush, commit, rollback, cleanup |
| Có quan sát DB sau commit/rollback? | Dùng context mới để tránh first-level cache gây nhầm |

---

## 26. Sơ đồ ghi nhớ

```text
RESOURCE_LOCAL JPA

EntityManager em = emf.createEntityManager()
                 |
                 v
       EntityTransaction tx
                 |
          +------v-------+
          | try          |
          |   tx.begin() |
          |   doWork()   |
          |   tx.commit()|
          +------+-------+
                 |
          success|failure
                 |     \
                 |      \ catch
                 |       \ rollback IF ACTIVE
                 |        \ preserve original error
                 v         v
              committed   error reported
                 \         /
                  \       /
                   finally
                       |
                    em.close()


Ghi nhớ 5 nguyên tắc:
  1. BEGIN trước unit of work cần nguyên tử.
  2. COMMIT chỉ ở nhánh thành công.
  3. ROLLBACK khi có lỗi và TX còn active.
  4. Đừng che lỗi gốc bằng lỗi rollback/close.
  5. Không xem SQL đã flush là dữ liệu đã commit.
```

## 27. Câu hỏi ôn tập

1. Vì sao `begin()`, `commit()` và `rollback()` phải cùng được thiết kế quanh một unit of work?
2. `EntityTransaction` phù hợp với RESOURCE_LOCAL hay JTA-managed EntityManager?
3. Nếu một phương thức nghiệp vụ đổi hai entity rồi ném exception trước commit, chuyện gì nên xảy ra?
4. Vì sao commit không được đặt vào finally?
5. Vì sao rollback cũng không nên được gọi vô điều kiện trong finally?
6. `tx.isActive()` giúp ích gì trước rollback?
7. Nếu `tx.isActive()` hoặc `tx.rollback()` ném exception khi đang xử lý lỗi gốc, làm sao giữ cả hai lỗi?
8. `Throwable.addSuppressed` có vai trò gì trong cleanup?
9. `flush()` phát SQL nhưng `rollback()` vẫn hủy được — vì sao?
10. Vì sao một exception có thể xuất hiện ở `commit()` thay vì `persist()`?
11. Transaction đánh dấu rollback-only có thể được commit thành công không?
12. Có nên tiếp tục dùng cùng persistence context sau khi flush thất bại không?
13. Vì sao entity đã nhận ID không bảo đảm INSERT đã commit?
14. Nếu close thất bại sau commit thành công, có nên tự retry tạo entity không?
15. Mất kết nối đúng thời điểm commit có thể tạo trạng thái kết quả nào?
16. Idempotency key giúp giải quyết nguy cơ gì khi retry?
17. `@Version` hỗ trợ xử lý xung đột đồng thời ra sao?
18. Spring `@Transactional` khác gì việc gọi `EntityTransaction.begin()` trực tiếp?
19. Với checked exception trong Spring, khi nào cần `rollbackFor`?
20. Vì sao bắt exception rồi trả về bình thường trong `@Transactional` có thể làm code cố commit?
21. `Propagation.REQUIRES_NEW` có thể phá vỡ tính nguyên tử của một use case như thế nào?
22. Vì sao self-invocation có thể khiến `@Transactional` không được kích hoạt trong Spring proxy mode?
23. Có thể rollback một email đã gửi bằng cách rollback database không?
24. Transactional outbox giải quyết điều gì và vẫn cần idempotency ở đâu?
25. Tại sao retry sau optimistic lock conflict nên mở transaction/context mới?
26. Vì sao không nên giữ database transaction mở trong lúc chờ HTTP service lâu?
27. Khi viết test, vì sao nên đọc lại bằng EntityManager mới sau rollback?
28. Khác biệt giữa lỗi xảy ra trong transaction và lỗi cleanup sau transaction là gì?

## 28. Tổng kết

```text
THÀNH CÔNG
    begin
      -> thao tác nghiệp vụ hợp lệ
      -> flush nếu cần
      -> commit thành công
      -> close EntityManager

THẤT BẠI
    begin hoặc doWork hoặc flush hoặc commit ném lỗi
      -> nếu còn active: cố rollback
      -> giữ lỗi gốc, gắn lỗi rollback thành suppressed
      -> close EntityManager
      -> báo thất bại / xử lý outcome không rõ

KHÔNG ĐƯỢC
    - commit vô điều kiện trong finally
    - nuốt exception và báo thành công
    - xem flush là commit
    - retry mù sau lỗi commit
    - tái sử dụng graph bị rollback như state sạch
    - dùng EntityTransaction để điều khiển JTA-managed EM
```

**Nguyên tắc cuối bài:** Hãy coi **`begin()` — xử lý nghiệp vụ — `commit()`** là một tuyến thành công; mọi lỗi có thể làm tuyến đó không hợp lệ phải đi qua **rollback nếu transaction còn active, bảo toàn exception gốc và giải phóng tài nguyên**. Trong hệ thống dùng JTA hoặc Spring, vẫn áp dụng đúng nguyên tắc này nhưng giao việc điều khiển transaction cho transaction manager. Đồng thời, phải phân biệt lỗi nghiệp vụ, lỗi database, lỗi rollback/cleanup và trường hợp kết quả commit không rõ để quyết định retry, idempotency và phản hồi chính xác.

