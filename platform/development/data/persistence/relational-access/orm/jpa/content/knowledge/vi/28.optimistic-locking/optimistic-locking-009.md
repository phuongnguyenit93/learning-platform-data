# Thử lại bằng giao dịch và ngữ cảnh mới khi phù hợp trong JPA

Trong chương **Khóa lạc quan (optimistic locking)**, một tình huống quen thuộc là hai giao dịch cùng đọc một entity ở phiên bản cũ rồi cùng cố cập nhật nó. Khi entity có `@Version`, JPA có thể phát hiện việc bản ghi đã bị transaction khác thay đổi và từ chối ghi đè bằng `OptimisticLockException` hoặc một exception tương ứng do provider/framework chuyển đổi.

Câu hỏi tiếp theo không chỉ là **“bắt exception nào?”**, mà là:

> Sau khi một giao dịch gặp xung đột phiên bản, có nên thử lại hay không, và nếu thử lại thì phải dùng transaction và persistence context nào?

**Nguyên tắc trọng tâm:** khi một lần cập nhật đã thất bại vì optimistic locking, không tiếp tục làm việc như thể transaction/persistence context đó vẫn còn tốt. Nếu nghiệp vụ cho phép retry, hãy **rollback lần thử cũ, kết thúc ngữ cảnh làm việc cũ, bắt đầu một transaction mới với persistence context phù hợp, đọc lại state hiện tại rồi thực hiện lại toàn bộ unit of work**.

Sơ đồ:

~~~text
      LẦN THỬ 1
┌─────────────────────────────────┐
│ Transaction A / Context A       │
│   find Product(v=7)             │
│   tính lại thay đổi             │
│   UPDATE ... WHERE version=7    │
│           -> 0 rows / conflict │
│   ROLLBACK                      │
└─────────────────────────────────┘
                  |
                  | Chỉ retry nếu phù hợp nghiệp vụ
                  v
      LẦN THỬ 2
┌─────────────────────────────────┐
│ Transaction B / Context B       │
│   find Product(v=8)             │
│   kiểm tra lại invariant        │
│   tính lại từ dữ liệu mới       │
│   UPDATE ... WHERE version=8    │
│   COMMIT nếu thành công         │
└─────────────────────────────────┘
~~~

Bài này giải thích **tại sao cần giao dịch và ngữ cảnh mới**, cách nhận diện trường hợp được phép retry, cách xây vòng lặp retry đúng với JPA `RESOURCE_LOCAL`, Spring `@Transactional`/`TransactionTemplate` và JTA, cách xử lý idempotency, backoff, lỗi commit không rõ kết quả, cũng như cách kiểm thử retry bằng hai giao dịch thực.

## 1. Nhắc lại: @Version phát hiện cập nhật dựa trên trạng thái cũ

Ví dụ một bản ghi điểm thưởng:

~~~text
reward_accounts
-------------------------------------------------
id | tenant_id | owner_id | points | version
10 | 100       | 25       | 200    | 4
~~~

Hai thao tác cộng điểm khác nhau cùng bắt đầu từ `points=200, version=4`.

~~~text
Transaction A                    Transaction B
-----------------------------    -----------------------------
SELECT -> 200 điểm, version=4    SELECT -> 200 điểm, version=4
cộng 30 -> 230                  cộng 50 -> 250
UPDATE ... WHERE version=4
  -> thành công, version=5
COMMIT
                                 UPDATE ... WHERE version=4
                                   -> không khớp
                                 Optimistic conflict
                                 ROLLBACK
~~~

Nếu cả hai lần cộng điểm đều là nghiệp vụ hợp lệ và độc lập, kết quả mong muốn có thể là `280`. Không nên bỏ qua cập nhật của B; nhưng cũng không nên ghi thẳng 250 đè lên kết quả 230 của A.

Một retry đúng:

~~~text
B bắt đầu transaction MỚI.
B đọc points=230, version=5.
B áp lại quy tắc cộng 50 -> 280.
B UPDATE ... WHERE version=5.
B COMMIT, version=6.
~~~

### SQL version-aware

Khi dùng managed entity có:

~~~java
@Version
private Long version;
~~~

JPA provider có thể phát SQL về bản chất:

~~~sql
UPDATE reward_accounts
SET points = 230, version = 5
WHERE id = 10 AND version = 4;
~~~

Nếu một transaction khác đã thay version lên 5, điều kiện `version=4` không còn đúng. Provider phát hiện kết quả cập nhật không phù hợp và báo optimistic conflict.

**Lưu ý:** SQL cụ thể, thứ tự bind parameters, thời điểm kiểm tra và exception wrapper thay đổi theo JPA provider/DBMS. `@Version` quan trọng ở **giao thức kiểm tra phiên bản**, không phải ở chính xác một câu SQL cố định.

## 2. Vì sao không đơn giản bắt lỗi rồi gọi lại UPDATE?

Sai lầm thường gặp:

~~~java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    // Thử thay đổi lại chính entity cũ.
    account.addPoints(50);
    em.flush();
}
~~~

Đoạn này có ba rủi ro riêng biệt:

1. **Transaction có thể đã bị đánh dấu rollback-only.** Optimistic conflict không phải một cảnh báo mà ứng dụng cứ bỏ qua rồi commit tiếp trong cùng giao dịch.
2. **Entity managed đang giữ state cũ.** Account có thể vẫn ở `points=250, version=4` hoặc trạng thái trung gian khác, không tương ứng giá trị đã commit `230, version=5`.
3. **Áp lại thay đổi trên object cũ không giống tính lại nghiệp vụ.** Nếu tiếp tục `addPoints(50)`, giá trị trong RAM có thể thành 300 từ state 250, dù kết quả đúng sau retry phải là 280.

Vì vậy, **catch exception rồi chạy lại dòng lệnh** không phải là chiến lược retry optimistic locking đáng tin cậy.

### Điều JPA có thể làm khi phát hiện lỗi

Khi nhận `OptimisticLockException` trong transaction, JPA có thể đánh dấu transaction rollback-only theo contract; provider cũng có thể đã tạo/bind các managed objects ở trạng thái không an toàn để tiếp tục. Trong Spring/JTA, transaction manager có thể đánh dấu rollback-only và báo lỗi lúc commit, ngay cả khi code đã catch exception ở một phương thức con.

**Hướng xử lý mặc định:** kết thúc transaction thất bại bằng rollback; không tái sử dụng persistence context của lần thử để suy ra state mới, đặc biệt không dùng tiếp entity đã dirty.

## 3. Giao dịch mới và ngữ cảnh mới là hai yêu cầu khác nhau

Một lần retry đúng cần phân biệt:

| Thành phần | Vì sao phải bắt đầu lại? |
| --- | --- |
| **Transaction** | Để thoát trạng thái lỗi/rollback-only và có commit boundary mới |
| **Persistence context** | Để không tái dùng identity map, snapshot/version hoặc dirty state của lần thử cũ |
| **Đọc dữ liệu** | Để tính nghiệp vụ từ state đã commit phù hợp, không từ các giá trị stale |
| **Kiểm tra invariant** | Vì điều kiện như đủ tồn kho/giới hạn tín dụng có thể đã thay đổi |
| **Unit of work** | Để các quyết định phụ thuộc vào state được lặp lại thống nhất |

### Chỉ gọi clear() có đủ?

Không. `em.clear()` detach managed entities nhưng **không sửa transaction đã bị đánh dấu rollback-only** và cũng không tự bắt đầu transaction mới.

### Chỉ gọi begin() lại trên cùng EntityManager có đủ?

Với `RESOURCE_LOCAL`, một EntityManager trong nhiều trường hợp có thể được dùng qua nhiều transaction, nhưng sau lỗi persistence/optimistic nghiêm trọng, tái sử dụng cùng context thường khó kiểm soát. Đối với một chiến lược retry dễ chứng minh và kiểm thử, **tạo EntityManager mới cho từng attempt** là lựa chọn rõ nhất.

Với Spring/JTA transaction-scoped EntityManager, cần bảo đảm mỗi attempt có **một transaction boundary mới thực sự** và persistence context tương ứng, không chỉ gọi method khác trên cùng proxy.

## 4. Bốn trường hợp thường bị nhầm với nhau

| Trường hợp | Nên xử lý thế nào? |
| --- | --- |
| Hai transaction tự động cộng cùng counter | Có thể retry sau khi đọc lại, nếu phép tính và side effects an toàn |
| Hai nhân viên cùng sửa giá từ form cũ | Thường **không tự retry**; trả conflict để họ xác nhận |
| Database từ chối vì deadlock/serialization | Có thể retry toàn transaction nhưng phân loại lỗi riêng, không gọi tất cả là optimistic conflict |
| Request đã commit nhưng client mất response | Không retry mù; cần idempotency/kiểm tra outcome |

Thông điệp “retry khi phù hợp” quan trọng ngang với “transaction và context mới”. Retry có thể là cách phục hồi chính xác cho một operation, nhưng lại trở thành **cách ghi đè có chủ ý mà không hỏi người dùng** đối với operation khác.

## 5. Điều kiện cần để tự động retry an toàn

Trước khi thêm retry loop, hãy trả lời:

1. Operation có thể **tái thực thi** mà không thay đổi ý nghĩa yêu cầu ban đầu không?
2. Thay đổi có thể **tính lại từ state mới**, thay vì ghi một kết quả tuyệt đối dựa trên state cũ không?
3. Những quy tắc như tồn kho, hạn mức, trạng thái đơn hoặc quyền truy cập có được **kiểm tra lại trong attempt mới** không?
4. Có side effects bên ngoài database như gửi email, gọi payment gateway, publish message không?
5. Có idempotency key hoặc cơ chế khác ngăn **một yêu cầu đã commit bị thực hiện lại** không?
6. Lỗi có thật sự là **retryable concurrency conflict**, hay chỉ là validation/auth/constraint error?
7. Có giới hạn attempts, backoff và giám sát để tránh retry storm không?
8. Có bảo đảm mỗi attempt sử dụng transaction/context mới không?

Nếu một trong các câu hỏi quan trọng chưa có câu trả lời, nên **báo conflict hoặc dừng lại** thay vì tự động lặp.

### Ví dụ phù hợp

Một event `RewardEarned(eventId, +30 points)` được thiết kế idempotent, lưu trong database cùng account balance. Khi hai event hợp lệ cùng tăng cùng account và một event gặp optimistic conflict, việc đọc lại balance rồi cộng 30 trong transaction mới thường là hợp lý.

### Ví dụ không phù hợp

Một form cập nhật thủ công:

~~~text
Nhân viên A đặt giá 110000, commit.
Nhân viên B vẫn xem giá cũ 100000 và gửi 120000.
~~~

Tự retry bằng cách đọc giá 110000 rồi áp 120000 có thể khiến cập nhật A mất đi, dù cơ chế `@Version` đã phát hiện xung đột. Nên trả 409/412 theo API contract và cho B xem dữ liệu mới.

## 6. Một giao thức retry tối thiểu

Sơ đồ thực hành:

~~~text
retry(operation, maxAttempts)
    |
    +-- attempt 1
    |     BEGIN transaction mới
    |     persistence context mới
    |     SELECT dữ liệu hiện tại
    |     kiểm tra business invariant
    |     tính và áp thay đổi
    |     FLUSH / COMMIT
    |         |
    |         +-- thành công -> trả kết quả
    |         |
    |         +-- retryable conflict
    |                -> ROLLBACK
    |                -> đóng context
    |
    +-- backoff (ở ngoài transaction)
    |
    +-- attempt 2
          BEGIN transaction mới
          persistence context mới
          SELECT lại dữ liệu hiện tại
          ...
~~~

**Vòng lặp phải bao quanh toàn bộ transaction**, không được nằm sâu bên trong một transaction đã mở sẵn. Điều này ảnh hưởng cách tổ chức service trong Spring, vì transaction proxy thường bắt đầu/commit transaction ở bên ngoài body của method.

## 7. Entity ví dụ: RewardAccount dùng @Version

Ví dụ tiếp theo dùng tài khoản điểm thưởng để thấy rõ phép cộng có thể tính lại. Đây là **mô hình đơn giản cho bài học**, không phải một ví dụ thay thế ledger/kiểm toán của hệ thống tài chính thực.

DDL:

~~~sql
CREATE TABLE reward_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    member_id BIGINT NOT NULL,
    points BIGINT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_reward_account_member
        UNIQUE (tenant_id, member_id),
    CONSTRAINT ck_reward_nonnegative
        CHECK (points >= 0)
);
~~~

Entity:

~~~java
package com.example.rewards;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "reward_accounts")
public class RewardAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "member_id", nullable = false)
    private Long memberId;

    @Column(nullable = false)
    private long points;

    @Version
    @Column(nullable = false)
    private Long version;

    protected RewardAccount() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public long getPoints() {
        return points;
    }

    public Long getVersion() {
        return version;
    }

    public void addPoints(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "amount phải dương");
        }

        points = Math.addExact(points, amount);
    }

    public void redeemPoints(long amount) {
        if (amount <= 0 || amount > points) {
            throw new IllegalArgumentException(
                "Số điểm không đủ");
        }
        points -= amount;
    }
}
~~~

`@Version` làm JPA kiểm tra concurrency khi UPDATE managed entity theo rules của provider. Application không tạo setter để tự sửa version.

### Vì sao dùng long và Math.addExact?

Điểm thưởng là số nguyên; `Math.addExact` báo lỗi khi overflow thay vì âm thầm quay vòng số `long`. Nếu domain cho phép lượng điểm đặc biệt lớn hoặc có đơn vị phức tạp, cần thiết kế kiểu dữ liệu phù hợp.

### Vì sao tách addPoints và redeemPoints?

Hai thao tác có **invariant khác nhau**:

- Cộng điểm: lượng cộng phải dương, tránh overflow.
- Đổi điểm: lượng trừ phải dương và số điểm hiện tại phải đủ.

Khi retry, phải gọi lại **đúng domain operation** trên state mới và kiểm tra invariant lại, không chỉ gán giá trị cũ.

## 8. Unit of work cho một lần cộng điểm

Giả sử câu lệnh nghiệp vụ là:

> Cộng thêm 30 điểm cho RewardAccount#10 nếu tài khoản thuộc tenant hiện hành.

Trong một lần thử:

~~~java
RewardAccount account =
    em.find(RewardAccount.class, accountId);

if (account == null
        || !Objects.equals(account.getTenantId(), tenantId)) {
    throw new AccountNotFoundException(accountId);
}

account.addPoints(30);
~~~

Đây là logic **read-modify-write**. Nếu account version bị transaction khác thay đổi trong lúc operation đang chạy, lần thử có thể nhận optimistic conflict tại flush/commit.

Khi retry, **không được** viết:

~~~java
account.setPoints(previouslyComputedPoints);
~~~

nếu previouslyComputedPoints được tính từ bản ghi cũ. Thay vào đó, đọc account mới rồi gọi lại `addPoints(30)`.

### Đơn vị retry

Nếu operation còn phải ghi `RewardEvent` và `OutboxEvent` trong cùng transaction, cả ba thao tác phải nằm trong **cùng một attempt**. Không retry riêng lệnh UPDATE account sau khi event hoặc outbox đã commit độc lập.

## 9. RESOURCE_LOCAL: tạo EntityManager mới cho từng attempt

Với JPA thuần `RESOURCE_LOCAL`, cách rõ ràng nhất là để mỗi attempt:

1. Gọi `EntityManagerFactory.createEntityManager()`.
2. Bắt đầu `EntityTransaction` mới.
3. Đọc dữ liệu và áp lại business operation.
4. Flush/commit.
5. Rollback nếu lỗi.
6. Đóng EntityManager trong `finally`.

Ví dụ:

~~~java
package com.example.rewards;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.util.Objects;

public class RewardAccountWriter {

    private final EntityManagerFactory emf;

    public RewardAccountWriter(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public RewardSnapshot addPointsOnce(
            long tenantId,
            long accountId,
            long amount) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            RewardAccount account =
                em.find(RewardAccount.class, accountId);

            if (account == null
                    || !Objects.equals(
                        account.getTenantId(), tenantId)) {
                throw new AccountNotFoundException(accountId);
            }

            account.addPoints(amount);

            // Có thể phát hiện optimistic conflict trước commit.
            em.flush();
            tx.commit();

            // Chỉ trả kết quả sau commit thành công.
            return new RewardSnapshot(
                account.getId(),
                account.getPoints(),
                account.getVersion()
            );

        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

DTO kết quả:

~~~java
package com.example.rewards;

public record RewardSnapshot(
        Long accountId,
        long points,
        Long version) {
}
~~~

Custom exception minh họa:

~~~java
public class AccountNotFoundException
        extends RuntimeException {

    public AccountNotFoundException(long id) {
        super("Không tìm thấy reward account: " + id);
    }
}
~~~

### Những điểm quan trọng

- `emf` là tài nguyên dùng chung/thread-safe theo contract JPA; `em` được tạo **riêng cho attempt**.
- Không dùng cùng một `EntityManager` cho hai threads.
- `tx.begin()`/`commit()`/`rollback()` chỉ dành cho RESOURCE_LOCAL, không phải JTA-managed EntityManager.
- `em.flush()` có thể báo conflict sớm, nhưng **commit vẫn có thể thất bại**.
- `finally em.close()` đảm bảo context attempt không được dùng làm nguồn dữ liệu cho attempt tiếp theo.
- Sau commit thành công, method trả snapshot dữ liệu; không trả managed entity để bên ngoài tiếp tục sửa.

### Vì sao rollback error được thêm vào suppressed?

Nếu rollback cũng thất bại, ta không muốn làm mất exception ban đầu. Đây chỉ là một mẫu xử lý kỹ thuật. Production vẫn cần log transaction/resource failure và không tự nhận định trạng thái commit khi kết nối bị mất đúng thời điểm xác nhận.

## 10. Vòng retry nằm ngoài addPointsOnce

Một retry coordinator sẽ gọi **lại addPointsOnce**, thay vì lặp các setter trong cùng EntityManager.

~~~java
package com.example.rewards;

import jakarta.persistence.OptimisticLockException;
import java.util.concurrent.ThreadLocalRandom;

public class RewardRetryCoordinator {

    private final RewardAccountWriter writer;

    public RewardRetryCoordinator(RewardAccountWriter writer) {
        this.writer = writer;
    }

    public RewardSnapshot addPointsWithRetry(
            long tenantId,
            long accountId,
            long amount) {

        final int maxAttempts = 3;

        for (int attempt = 1;
                attempt <= maxAttempts;
                attempt++) {

            try {
                // Mỗi lần gọi mở TX và EntityManager mới.
                return writer.addPointsOnce(
                    tenantId, accountId, amount);

            } catch (RuntimeException ex) {
                if (!isOptimisticConflict(ex)
                        || attempt == maxAttempts) {
                    throw ex;
                }

                // Transaction cũ đã rollback/đóng context.
                pauseBetweenAttempts(attempt);
            }
        }

        throw new IllegalStateException(
            "Không thể đạt tới trạng thái này");
    }

    private static boolean isOptimisticConflict(
            Throwable error) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (current instanceof OptimisticLockException) {
                return true;
            }
        }
        return false;
    }

    private static void pauseBetweenAttempts(int attempt) {
        long baseMillis = 40L << (attempt - 1);
        long jitter = ThreadLocalRandom.current()
            .nextLong(0, 30);

        try {
            Thread.sleep(baseMillis + jitter);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Retry bị gián đoạn", ex);
        }
    }
}
~~~

### Điều kiện sử dụng mẫu trên

Mẫu này chỉ minh họa **cơ chế retry optimistic** cho một thao tác cộng điểm có thể tính lại. Nó chưa xử lý idempotency xuyên các lần gửi request độc lập; phần sau sẽ bổ sung.

`isOptimisticConflict` chỉ nhận diện `jakarta.persistence.OptimisticLockException` trong exception cause chain. Trong Spring, cần bổ sung các exception được framework chuyển đổi như `ObjectOptimisticLockingFailureException` hoặc `OptimisticLockingFailureException` theo stack thực tế.

**Không nhận mọi `RuntimeException` là retryable.** `AccountNotFoundException`, `IllegalArgumentException`, lỗi schema, quyền truy cập hoặc dữ liệu sai không nên được thử lại chỉ vì chúng xảy ra trong transaction.

### Backoff phải ở ngoài transaction

Ở ví dụ trên, `addPointsOnce` đã kết thúc transaction và đóng context trước khi coordinator gọi `pauseBetweenAttempts`. Do đó thread không ngủ trong khi giữ row lock/transaction/resource của lần thử cũ.

Trong ứng dụng web tải lớn, việc dùng `Thread.sleep` cũng có chi phí chiếm request thread; có thể dùng retry scheduler hoặc framework phù hợp, nhưng **không biến vòng retry thành một transaction kéo dài**.

## 11. Những gì phải được tính lại trong attempt mới

Không chỉ nạp version mới; toàn bộ quyết định phụ thuộc dữ liệu cần được xem lại.

Ví dụ đổi điểm:

~~~text
Account ban đầu: 100 điểm, v=7
A muốn đổi 80 điểm.
B muốn đổi 50 điểm.
~~~

Nếu A commit trước:

~~~text
Account sau A: 20 điểm, v=8
~~~

B gặp optimistic conflict. Trong attempt mới, B **không thể cứ trừ 50** vì invariant `points >= 50` không còn thỏa.

Đúng:

~~~java
RewardAccount fresh = em.find(
    RewardAccount.class, accountId);

fresh.redeemPoints(50);
// Nếu chỉ còn 20 điểm -> domain validation failure.
// Không retry mãi như thể đây là xung đột tạm thời.
~~~

### Tại sao không retry với kết quả tính cũ?

Nếu B tính từ điểm=100 và quyết định “còn 50 sau khi đổi”, việc đặt `points=50` ở attempt mới sẽ vô tình thêm điểm so với state 20. Còn nếu B cố trừ `50` bất chấp invariant, số điểm thành âm.

**Retry đúng là chạy lại business rule trên current state**, không phải chỉ phát lại SQL/giá trị tuyệt đối của lần cũ.

## 12. Sau rollback: managed entity cũ không còn là nguồn sự thật

Trong attempt thất bại:

~~~java
RewardAccount account = em.find(...);
account.addPoints(30);
em.flush(); // OptimisticLockException
~~~

Java object `account` vẫn có thể chứa số điểm đã cộng trong RAM. Sau rollback:

- Nó không phản ánh một write đã được commit.
- Nó có thể bị detach/không còn được provider quản lý theo trạng thái mong đợi.
- Version của nó có thể cũ hoặc trung gian.
- Các association đã nạp và pending changes có thể không đồng bộ.

Không làm:

~~~java
RewardAccount retryTarget = oldAccount;
retryTarget.addPoints(30);
~~~

Thay vào đó:

~~~java
EntityManager newEm = emf.createEntityManager();
// Begin transaction mới.
RewardAccount fresh =
    newEm.find(RewardAccount.class, accountId);
~~~

Sau đó mới áp dụng lại quy tắc trên `fresh`.

### Không chuyển object cũ sang transaction mới bằng merge một cách máy móc

`em.merge(oldAccount)` có thể sao chép state stale — bao gồm những giá trị đã tính trên snapshot lỗi — vào managed entity mới, thay vì tái tính toán nghiệp vụ. Có thể phát hiện stale version khi merge, nhưng dùng merge như “chiêu retry” vừa khó hiểu vừa dễ dẫn tới overwrite nếu version bị bỏ/lệch.

**Dùng command bất biến như `AddPoints(accountId, amount, requestId)` cho retry, không dùng entity dirty của attempt trước làm payload.**

## 13. Vì sao clear() và refresh() không đủ thay transaction mới?

### clear()

~~~java
em.clear();
~~~

Detach tất cả managed entities. Nó **không**:

- Rollback transaction hiện tại.
- Xóa rollback-only flag.
- Tạo một transaction mới.
- Hoàn tác SQL đã flush trong database.

### refresh()

~~~java
em.refresh(account);
~~~

Có thể đọc lại persistent state từ database khi entity managed và transaction/context hợp lệ. Nhưng sau một optimistic conflict đã làm transaction thất bại, `refresh()` trong transaction cũ không được xem là bước phục hồi thay rollback. Ngoài ra, refresh có thể ghi đè pending changes chưa flush.

### Flush

~~~java
em.flush();
~~~

Không phải một lời “thử lại”. Nó gửi pending SQL của context; nếu context/transaction đã lỗi, lặp flush không biến stale version thành version mới.

### Tóm tắt

| API | Có tạo transaction mới? | Có bảo đảm context mới? | Phù hợp để retry sau conflict? |
| --- | --- | --- | --- |
| `em.flush()` | Không | Không | Không |
| `em.refresh(entity)` | Không | Không | Không dùng thay rollback |
| `em.clear()` | Không | Làm rỗng context cũ, không tạo context riêng | Không đủ |
| `em.merge(staleEntity)` | Không | Không | Không phải retry nghiệp vụ |
| Transaction mới + EntityManager mới + đọc lại | Có | Có | Mẫu rõ ràng |

## 14. Không retry lỗi nghiệp vụ

Ví dụ:

~~~java
if (requestedPoints > account.getPoints()) {
    throw new InsufficientPointsException();
}
~~~

Đây thường là **business precondition failure**, không phải optimistic locking conflict. Tự lặp ba lần ngay lập tức không tạo thêm điểm.

Những lỗi thường không retry:

- Không tìm thấy entity hoặc không có quyền tenant.
- Input âm, null hoặc sai định dạng.
- SKU không hợp lệ.
- Vượt hạn mức nghiệp vụ hiện hành.
- Vi phạm unique key do request trùng đã được xác định.
- SQL syntax error, mapping error hoặc routine không tồn tại.
- Thao tác đã được người dùng xác nhận theo phiên bản cũ nhưng trạng thái mới khác.

Một số lỗi validation có thể trở nên hợp lệ sau sự kiện ngoài hệ thống, nhưng lúc đó cần **workflow chờ sự kiện** hoặc hành động mới; không phải optimistic retry ngắn hạn.

## 15. Không tự retry ghi đè lựa chọn của con người

Một nhân viên mở form Product:

~~~text
GET Product#10:
    price=100000
    version=7
~~~

Trong khi người đó suy nghĩ, người khác đổi:

~~~text
price=110000
version=8
~~~

Người thứ nhất gửi:

~~~json
{
  "newPrice": 120000,
  "expectedVersion": 7
}
~~~

Server phải nhìn `expectedVersion=7` như một **precondition của quyết định người dùng**. Nếu version hiện tại là 8, việc âm thầm nạp version=8 rồi đặt price=120000 sẽ biến optimistic locking thành chính sách “last write wins”.

### Đường xử lý tốt hơn

1. Trả conflict (thường 409 đối với body version contract).
2. Với HTTP `If-Match` không còn đúng, trả 412 Precondition Failed theo semantics HTTP.
3. Cho người dùng biết dữ liệu đã thay đổi.
4. Hiển thị phiên bản mới và thay đổi họ đang định thực hiện.
5. Chỉ lưu khi người dùng xác nhận dựa trên version hiện tại.

**Retry tự động phù hợp với thao tác có thể tính lại, không phù hợp với mọi thao tác ghi giá trị tuyệt đối.**

## 16. Hai nguồn version phải cùng được bảo vệ

Trong một API chỉnh sửa, có hai khoảng cạnh tranh:

~~~text
A. Giữa GET của client và PUT/PATCH của client.
B. Giữa SELECT của service và UPDATE của service.
~~~

`@Version` trên managed entity giúp bảo vệ **B** nếu provider sinh version-aware UPDATE.

`expectedVersion` từ request hoặc `If-Match` giúp bảo vệ **A**.

Ví dụ:

~~~text
GET của B -> version=7
A commit version=8

PUT của B:
  Service mở transaction mới
  SELECT hiện tại -> version=8
  Nếu KHÔNG so expectedVersion=7, @Version vẫn thấy
  một entity managed version=8 và có thể cập nhật thành 9.
~~~

Đó không phải optimistic conflict trong transaction service; nó là **stale client intent**. Phải so version của lần GET cũ.

## 17. @Version không thay thế idempotency

Khi thao tác cộng điểm thành công:

~~~text
POST add 30 points
  Transaction commit balance 230.
  Response 200 bị mất do network.
Client gửi lại POST add 30 points.
~~~

Nếu server lặp phép cộng ở transaction mới, balance sẽ thành `260`, dù chỉ có **một sự kiện thưởng điểm**.

`@Version` có thể bảo đảm hai write cạnh tranh không âm thầm overwrite, nhưng **không tự biết hai HTTP requests là cùng một ý định**.

### Phân biệt

| Vấn đề | Cơ chế chính |
| --- | --- |
| Hai attempt cùng sửa row từ version cũ | Optimistic locking |
| Retry sau một transaction đã rollback | Transaction/context mới và tính lại |
| Retry request đã commit nhưng mất response | Idempotency key và tra kết quả đã xử lý |
| Cập nhật form cũ từ người dùng | ExpectedVersion/ETag, báo conflict |

Trong production, nghiệp vụ cộng điểm phải có cơ chế idempotency nếu có khả năng yêu cầu bị gửi lại.

## 18. Mô hình idempotency key cho sự kiện cộng điểm

Thêm bảng ghi nhận mỗi yêu cầu thưởng điểm:

~~~sql
CREATE TABLE processed_reward_commands (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    request_key VARCHAR(120) NOT NULL,
    account_id BIGINT NOT NULL,
    amount BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reward_command
        UNIQUE (tenant_id, request_key),
    CONSTRAINT ck_reward_command_amount
        CHECK (amount > 0)
);
~~~

Một operation có thể làm trong **cùng transaction**:

~~~text
BEGIN
    Kiểm tra/ghi nhận request_key theo unique constraint
    Đọc RewardAccount/version mới
    Áp addPoints(amount)
    INSERT outbox event nếu cần
COMMIT
~~~

Nếu attempt thất bại vì optimistic conflict và rollback:

~~~text
Command record chưa commit -> rollback cùng account change.
Retry transaction mới -> có thể thử lại an toàn.
~~~

Nếu transaction đã commit nhưng response mất:

~~~text
Command record đã commit, UNIQUE(tenant, request_key).
Request gửi lại cùng key -> không áp cộng điểm lần hai;
ứng dụng đọc kết quả/trạng thái request cũ.
~~~

### Unique constraint là điều kiện cần, chưa phải toàn bộ implementation

Không nên chỉ:

~~~text
SELECT xem request_key có tồn tại không.
Nếu không -> INSERT.
~~~

rồi giả định an toàn trước hai requests đồng thời. Hai transaction có thể cùng SELECT “chưa tồn tại”; **unique constraint tại database** phải là lớp bảo vệ cuối.

Ứng dụng còn cần kiểm tra nếu cùng key được gửi lại nhưng **amount/account khác**, phải coi đó là yêu cầu không hợp lệ hoặc xung đột contract, không tái sử dụng kết quả của thao tác khác.

### Không retry mù unique violation

Unique constraint conflict của request_key có thể nghĩa **request đã được xử lý**, không nhất thiết là transient optimistic conflict. Hãy truy vấn outcome của request theo transaction mới và trả kết quả đúng, không tiếp tục áp lại phép cộng.

## 19. Chuyện gì xảy ra nếu commit trả lỗi nhưng DB đã commit?

Đây là một tình huống khó hơn optimistic conflict:

~~~text
Application gửi COMMIT.
Database COMMIT thành công.
Network connection mất trước khi application nhận phản hồi.
Application thấy exception, không biết commit đã thành công chưa.
~~~

Không thể suy ra chỉ từ exception ở client rằng transaction chắc chắn **chưa commit**.

Nếu ứng dụng retry ngay một thao tác không idempotent:

~~~text
Credit 30 points
  COMMIT đã thành công (nhưng response mất)
Retry 30 points
  COMMIT thêm lần nữa
=> +60 thay vì +30
~~~

### Cách thiết kế

- Gắn một request ID/idempotency key ổn định.
- Ghi kết quả/record của request cùng transaction với business update.
- Khi outcome commit không rõ, mở transaction mới để **xác minh bằng request key**.
- Nếu đã commit, trả lại outcome đã ghi.
- Nếu chắc chắn chưa commit hoặc có cơ chế an toàn để retry, mới thực hiện lại.
- Với resource ngoài DB, dùng mô hình outbox/compensation khi phù hợp.

**Một lỗi kết nối hoặc timeout tại commit không được mặc định là optimistic conflict an toàn để retry.**

## 20. Retry phải bao trùm toàn bộ unit of work

Giả sử nghiệp vụ cộng điểm gồm:

~~~text
1. Verify event chưa xử lý.
2. Load RewardAccount.
3. Kiểm tra account active.
4. Add points.
5. Insert RewardEvent.
6. Insert OutboxEvent.
7. Commit.
~~~

Nếu optimistic conflict phát sinh ở bước 7, lần retry không thể chỉ làm:

~~~text
Load RewardAccount -> add points -> commit
~~~

mà bỏ qua các bước kiểm tra và ghi event. Mọi dữ liệu phụ thuộc state cũ phải được tái xác nhận.

### Định nghĩa transaction boundary theo nghiệp vụ

Một transaction hợp lý:

~~~text
BEGIN
    SELECT account/version
    Validate status/tenant/points
    Update account/version
    Insert command record/event/outbox
COMMIT
~~~

Tất cả database writes có quan hệ nguyên tử nên nằm trong cùng transaction/resource. Retry lại **toàn bộ operation** nếu lần trước rollback.

### Không gửi email trước commit

Nếu gửi email trong attempt 1:

~~~text
Send email "Bạn nhận 30 điểm"
Flush -> optimistic conflict
Rollback
Retry -> send email lần nữa
~~~

khách có thể nhận nhiều email dù chỉ một lần cộng thành công. Dùng transactional outbox: INSERT “ý định gửi thông báo” trong transaction; worker gửi sau commit và xử lý idempotent.

## 21. Backoff và jitter: tránh nhiều retry va chạm lặp

Khi nhiều giao dịch cùng tranh một RewardAccount nóng:

~~~text
100 requests cùng đọc version=7
1 request commit version=8
99 requests conflict

Nếu cả 99 retry ngay lập tức:
  cùng đọc version=8
  lại chỉ một vài transaction thành công
  phần lớn lại conflict
~~~

Đây là **retry storm**. Backoff và jitter giúp phân tán các attempts.

Ví dụ policy:

| Attempt | Trì hoãn trước attempt tiếp theo | Ý tưởng |
| --- | --- | --- |
| 1 | 40–70 ms | Backoff ngắn + jitter |
| 2 | 80–110 ms | Tăng dần |
| 3 | Hết số lần | Trả conflict/busy tùy business |

Các số trên chỉ là **giá trị minh họa**, phải dựa vào SLA, tải và latency thực tế.

### Exponential backoff

Mẫu:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1}) + J_n
\]

Trong đó:

- `d0` là delay cơ bản.
- `dmax` là mức trần.
- `J_n` là jitter ngẫu nhiên.

Đừng để exponential growth overflow khi shift hoặc nhân với attempts lớn; nên giới hạn attempts và dùng phép toán an toàn.

### Backoff ở đâu?

**Sau khi transaction thất bại đã rollback và resources đã được giải phóng**. Không sleep trong `@Transactional` method đang giữ persistence context hoặc DB locks.

## 22. Giới hạn attempts và ngân sách thời gian

Không retry vô hạn:

~~~java
while (true) {
    try {
        return update();
    } catch (OptimisticLockException ex) {
        // retry mãi
    }
}
~~~

Với contention cao, vòng lặp này có thể:

- Tăng tải database.
- Làm chậm các request khác.
- Cạn request threads/connection pool.
- Biến xung đột cục bộ thành sự cố diện rộng.
- Che một lỗi thiết kế invariant hoặc truy vấn khiến mọi attempt đều thất bại.

### Policy thực hành

- `maxAttempts` nhỏ, có cấu hình/giám sát (ví dụ 2–3 attempts).
- Có deadline cho request hoặc job.
- Backoff có jitter.
- Phân loại lỗi chặt chẽ.
- Giảm khả năng cạnh tranh nếu row là hotspot.
- Trả lỗi rõ ràng khi hết số lần.

### Retry exhaustion

Khi hết attempts, không trả `200 OK` hoặc coi “đã cộng điểm” là thành công. Có thể trả lỗi conflict/busy phù hợp, hoặc đưa job vào queue với idempotency key nếu nghiệp vụ cho phép xử lý sau. Việc trả HTTP 409, 503 hay một domain result khác phụ thuộc nguyên nhân và contract, không có quy tắc JPA bắt buộc.

## 23. Không biến mọi lỗi DB thành optimistic retry

Các nguồn lỗi khác nhau:

| Loại lỗi | Có thể retry tự động? | Lý do |
| --- | --- | --- |
| `OptimisticLockException` | Có thể | Nếu operation tính lại an toàn |
| Spring `ObjectOptimisticLockingFailureException` | Có thể | Adapter/provider translation |
| Deadlock victim | Có thể | Retry transaction mới sau backoff |
| Serialization failure | Có thể | DB yêu cầu lịch sử transaction khác |
| Lock timeout | Tùy | Có thể liên quan contention/configuration |
| Constraint UNIQUE vì cùng request ID | Thường kiểm tra idempotency outcome | Không nhân đôi side effect |
| Validation error | Không | Input không hợp lệ |
| Authorization failure | Không | Retry không cấp thêm quyền |
| SQL syntax/mapping error | Không | Cần sửa code/schema |
| Commit outcome không rõ do mất kết nối | Không retry mù | Cần kiểm tra bằng request key |

### Chỉ được retry khi lỗi đã được phân loại

Không viết:

~~~java
catch (Exception ex) {
    retry();
}
~~~

hay:

~~~java
catch (PersistenceException ex) {
    retry();
}
~~~

để bao tất cả lỗi database. Một số lỗi, chẳng hạn không có table hoặc field mapping sai, sẽ luôn thất bại và gây retry vô ích.

### SQLSTATE/error code

Với deadlock và serialization failure, mỗi DBMS có mã lỗi riêng (ví dụ PostgreSQL sử dụng SQLSTATE cho serialization/deadlock). Nếu muốn mở rộng retry ngoài optimistic lock, dùng classifier dựa trên **provider/database thực tế** và kiểm thử; đừng coi mọi `PersistenceException` là transient.

## 24. Spring @Transactional: retry bên trong cùng method là sai phổ biến

Ví dụ:

~~~java
@Transactional
public void awardPoints(...) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            RewardAccount account =
                repository.findById(...).orElseThrow();

            account.addPoints(30);
            entityManager.flush();
            return;

        } catch (OptimisticLockException ex) {
            // Cố lặp ngay.
        }
    }
}
~~~

Vấn đề: Spring transaction proxy đã mở **một transaction bao quanh cả method**. Mọi lượt lặp thường cùng transaction/persistence context, không phải ba attempts độc lập.

Ngoài ra, method có thể `return` **trước khi transaction interceptor commit**; một exception ở commit sẽ xuất hiện sau body method, nằm ngoài catch.

### Cách đặt boundary đúng

~~~text
Non-transactional RetryCoordinator
      |
      +-- gọi AttemptService.creditOnce()
      |     @Transactional
      |     -> transaction #1 -> rollback
      |
      +-- backoff
      |
      +-- gọi AttemptService.creditOnce()
            @Transactional
            -> transaction #2 -> commit
~~~

Retry coordinator phải nằm **bên ngoài** transaction boundary của từng attempt và bắt exception từ **lời gọi proxy** sau khi interceptor xử lý commit.

## 25. Spring: hai service tách rõ coordinator và một attempt

Một cách tổ chức:

~~~java
package com.example.rewards;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RewardAttemptService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public RewardSnapshot addPointsOnce(
            long tenantId,
            long accountId,
            long amount) {

        RewardAccount account = em.find(
            RewardAccount.class, accountId);

        if (account == null
                || !Objects.equals(
                    account.getTenantId(), tenantId)) {
            throw new AccountNotFoundException(accountId);
        }

        account.addPoints(amount);
        em.flush();

        return new RewardSnapshot(
            account.getId(),
            account.getPoints(),
            account.getVersion()
        );
    }
}
~~~

Ở đây `RewardSnapshot` được tạo trong method, nhưng transaction interceptor chỉ commit **sau khi method body return**. Tầng gọi bên ngoài chỉ thật sự nhận được kết quả khi proxy đã xử lý hoàn tất transaction; nếu commit ném exception, kết quả trả về không đi tới caller theo luồng bình thường.

Coordinator:

~~~java
package com.example.rewards;

import org.springframework.stereotype.Service;
import org.springframework.transaction.support
    .TransactionSynchronizationManager;

@Service
public class RewardRetryService {

    private final RewardAttemptService attemptService;

    public RewardRetryService(
            RewardAttemptService attemptService) {
        this.attemptService = attemptService;
    }

    public RewardSnapshot addPoints(
            long tenantId,
            long accountId,
            long amount) {

        if (TransactionSynchronizationManager
                .isActualTransactionActive()) {
            throw new IllegalStateException(
                "Retry coordinator phải được gọi ngoài " +
                "transaction hiện hữu");
        }

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return attemptService.addPointsOnce(
                    tenantId, accountId, amount);

            } catch (RuntimeException ex) {
                if (!RetryClassifier.isRetryable(ex)
                        || attempt == 3) {
                    throw ex;
                }
                RetryBackoff.pause(attempt);
            }
        }

        throw new IllegalStateException(
            "Không có nhánh thực thi hợp lệ");
    }
}
~~~

`RetryClassifier` và `RetryBackoff` là các utility của dự án, thực hiện chức năng phân loại lỗi và backoff như ví dụ ở mục 10/23. Đoạn trên minh họa tổ chức responsibility, không phải một source file độc lập đã có sẵn mọi helper imports.

### Điều kiện bảo đảm context mới

Trong cấu hình Spring JPA thông thường, một transaction mới dùng transaction-scoped EntityManager sẽ có persistence context gắn với transaction đó. Tuy nhiên, nếu ứng dụng bật **Open EntityManager in View**, extended persistence context hoặc cơ chế bind EntityManager đặc biệt, phải kiểm chứng thật sự không tái sử dụng stale state xuyên attempts.

### Tránh self-invocation

Không viết trong cùng bean:

~~~java
this.addPointsOnce(...); // Có thể bỏ qua Spring proxy.
~~~

Nếu `@Transactional` áp qua proxy-based AOP, gọi `this.method()` không đi qua proxy nên transaction annotation có thể không hoạt động như dự kiến.

## 26. Propagation.REQUIRED, REQUIRES_NEW và ranh giới ngoài

Spring `@Transactional` mặc định thường dùng `Propagation.REQUIRED`.

### Khi coordinator không có transaction

~~~text
Coordinator (không transaction)
    |
    +-- AttemptService @Transactional(REQUIRED)
    |      -> Spring tạo transaction mới
    |
    +-- AttemptService @Transactional(REQUIRED)
           -> Lần gọi tiếp theo tạo transaction mới
~~~

Đây là cấu trúc phù hợp khi muốn mỗi attempt độc lập.

### Khi caller đã có transaction

~~~text
Outer @Transactional
    |
    +-- Retry coordinator
         |
         +-- AttemptService REQUIRED
               -> tham gia Outer transaction
~~~

Khi đó retry coordinator **không thể đảm bảo có transaction mới** chỉ bằng việc gọi method lần nữa. Nếu inner attempt đánh dấu rollback-only, outer transaction cũng bị ảnh hưởng.

### Có nên đổi sang REQUIRES_NEW?

`Propagation.REQUIRES_NEW` có thể mở một physical transaction mới và tạm ngưng transaction ngoài:

~~~text
Outer Transaction A
    |
    +-- Inner Transaction B (REQUIRES_NEW) -> COMMIT
    |
    +-- Outer A -> ROLLBACK
~~~

Điều này **phá tính nguyên tử** nếu outer và inner cần cùng commit/rollback. Không dùng REQUIRES_NEW như “cách sửa nhanh” cho retry mà chưa hiểu toàn unit of work.

### Phương án thiết kế

- Đặt retry ở entrypoint **ngoài transaction**, rồi mỗi attempt chạy một transaction riêng.
- Nếu một operation lớn gồm nhiều bước nguyên tử, cả operation đó phải chạy lại trong attempt transaction mới.
- Nếu bắt buộc có outer transaction do framework, thay đổi kiến trúc boundary hoặc dùng cơ chế transaction orchestration phù hợp — không tự mở inner commit tách rời.

## 27. Spring TransactionTemplate: một transaction cho mỗi callback

Một phương án programmatic để nhìn rõ boundary là `TransactionTemplate`.

~~~java
package com.example.rewards;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction
    .PlatformTransactionManager;
import org.springframework.transaction.support
    .TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RewardTemplateCoordinator {

    private final TransactionTemplate template;

    @PersistenceContext
    private EntityManager em;

    public RewardTemplateCoordinator(
            PlatformTransactionManager manager) {
        this.template = new TransactionTemplate(manager);
    }

    public RewardSnapshot award(
            long tenantId, long accountId, long amount) {

        if (TransactionSynchronizationManager
                .isActualTransactionActive()) {
            throw new IllegalStateException(
                "Coordinator không nhận outer transaction");
        }

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return template.execute(status -> {
                    RewardAccount account =
                        em.find(RewardAccount.class, accountId);

                    if (account == null
                            || !account.getTenantId()
                                .equals(tenantId)) {
                        throw new AccountNotFoundException(
                            accountId);
                    }

                    account.addPoints(amount);
                    em.flush();

                    return new RewardSnapshot(
                        account.getId(),
                        account.getPoints(),
                        account.getVersion()
                    );
                });

            } catch (RuntimeException ex) {
                if (!RetryClassifier.isRetryable(ex)
                        || attempt == 3) {
                    throw ex;
                }
                RetryBackoff.pause(attempt);
            }
        }

        throw new IllegalStateException(
            "Không có nhánh thực thi hợp lệ");
    }
}
~~~

`TransactionTemplate.execute(...)` trả về **sau khi transaction manager đã hoàn thành việc commit/rollback** của callback. Vì catch nằm **bên ngoài lời gọi execute**, nó có thể xử lý cả lỗi được phát hiện ở commit.

### Điều kiện cần

- `PlatformTransactionManager` được cấu hình cho đúng JPA/DataSource.
- `EntityManager` được inject phải là transaction-scoped proxy gắn với resource/transaction hiện tại.
- Coordinator phải được gọi khi **không có transaction ngoài**, như guard đã nêu.
- Không có extended/OSIV context bị tái sử dụng ngoài chủ ý; kiểm chứng cấu hình nếu có.
- `RetryClassifier` chỉ nhận những lỗi thật sự retryable.

`TransactionTemplate` mặc định dùng propagation tương ứng với cấu hình template. Nếu dùng REQUIRED mà caller đã có transaction, callback sẽ tham gia transaction đó, **không tạo boundary mới**. Guard ở ví dụ nhằm biến yêu cầu này thành ràng buộc rõ.

## 28. Spring @Retryable và @Transactional: thứ tự advice quan trọng

Nếu dự án có Spring Retry, có thể muốn dùng annotation:

~~~java
@Retryable(...)
@Transactional
public void update(...) {
    // ...
}
~~~

Nhưng chỉ đặt hai annotations cạnh nhau **không đủ để chứng minh mỗi attempt có transaction mới**. Điều đó phụ thuộc thứ tự AOP advice/interceptors và cách bean được gọi.

### Hai thứ tự có kết quả khác nhau

**Thứ tự mong muốn: Retry nằm ngoài Transaction.**

~~~text
Retry advice
  attempt 1 -> Transaction advice BEGIN/ROLLBACK
  delay
  attempt 2 -> Transaction advice BEGIN/COMMIT
~~~

**Thứ tự nguy hiểm: Transaction nằm ngoài Retry.**

~~~text
Transaction advice BEGIN
  Retry advice
    attempt 1 -> lỗi, transaction rollback-only
    attempt 2 -> vẫn cùng transaction
Transaction advice COMMIT -> lỗi/rollback
~~~

### Những điều phải kiểm tra

- Phiên bản Spring Retry/Spring AOP và advisor ordering.
- Annotation có được thực thi qua proxy không?
- Exception có xuất hiện tại flush/commit và đi qua retry interceptor không?
- Có một transaction/persistence context mới thật cho từng attempt không?
- Có outer transaction phía trên không?
- Retry classifier có vô tình bắt validation/authorization errors không?

Khi một hệ thống quan trọng cần giao dịch rõ ràng, **tách RetryCoordinator và transactional AttemptService** hoặc dùng `TransactionTemplate` dễ giải thích/kiểm thử hơn dựa trên thứ tự advice khó quan sát.

## 29. JTA-managed EntityManager và retry

Trong Jakarta EE/JTA, transaction boundary thuộc container hoặc JTA transaction manager, không nằm trong `em.getTransaction()`.

Ví dụ sơ đồ:

~~~text
Non-transactional coordinator
    |
    +-- Gọi CDI/EJB service có transaction boundary
    |      -> JTA Transaction #1
    |      -> JTA-managed EntityManager tham gia
    |      -> conflict, rollback
    |
    +-- Gọi lại business service qua container
           -> JTA Transaction #2
           -> EntityManager/context phù hợp của #2
           -> đọc lại, commit
~~~

### Không dùng EntityTransaction trên JTA-managed EM

Sai:

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();
~~~

đối với JTA-managed EntityManager.

Đúng là để container/JTA transaction manager bắt đầu/rollback/commit theo các giao dịch độc lập mà ứng dụng điều phối, ví dụ bằng `jakarta.transaction.Transactional` và các propagation semantics/hạ tầng tương ứng.

### Transaction-scoped vs extended persistence context

Với **extended persistence context**, EntityManager có thể giữ state qua nhiều transaction. Vì vậy việc bắt đầu JTA transaction mới **không tự bảo đảm identity map mới** như một transaction-scoped context.

Nếu retry yêu cầu state sạch, hãy thiết kế persistence-context lifecycle phù hợp, hoặc dùng một boundary/EntityManager mới tường minh theo container rules. Không suy luận “new JTA tx = new context” trong mọi cấu hình.

## 30. Transaction mới không có nghĩa snapshot dữ liệu luôn mới hơn

Một attempt mới với EntityManager mới thường loại bỏ first-level cache stale của lần cũ, nhưng dữ liệu nó nhìn được vẫn chịu:

- Database isolation level.
- Transaction snapshot/MVCC.
- Replication lag nếu đọc qua replica.
- Second-level cache nếu bật và cấu hình invalidation không đúng.
- Các transaction khác chưa commit.

### Ví dụ

Nếu một transaction đọc trên read replica chậm vài giây, attempt mới có thể tiếp tục thấy version cũ dù primary đã commit. Khi retry optimistic write, cần chắc chắn mọi read/write liên quan đến entity diễn ra trên resource nhất quán với transaction và version check.

### Điều nên kiểm chứng

- Retry có đọc trên primary khi operation sắp ghi primary không?
- Provider có dùng cache đáng tin để thấy version mới không?
- Transaction mỗi attempt có snapshot mới theo DBMS/isolation không?
- Có bẫy extended persistence context hoặc OSIV tái sử dụng state không?

**Context mới là điều kiện quan trọng, nhưng không thay thế kiến trúc nhất quán đọc/ghi của database.**

## 31. @OptimisticLocking và Hibernate-specific behavior

JPA chuẩn khuyến nghị cách phổ biến là `@Version`. Một số provider có chế độ optimistic locking không dùng version column hoặc dùng tất cả/những cột dirty để xác định xung đột.

Ví dụ Hibernate có các extension liên quan như:

- `@DynamicUpdate` để điều chỉnh cột SET trong SQL UPDATE.
- Provider-specific optimistic locking strategies dựa trên dirty/all columns trong một số trường hợp.

Các extension này **không tạo ra cùng một contract portable** như một `@Version` nhất quán. Khi viết retry classifier, phải biết provider báo lỗi nào và lúc nào.

Không biến ví dụ `@Version` thành giả định mọi entity đều có số version, nhưng cũng không loại bỏ yêu cầu rollback/context mới khi transaction đã lỗi.

## 32. Optimistic conflict, lock timeout và deadlock khác nhau

Một operation có thể thất bại vì:

~~~text
Optimistic conflict:
  UPDATE ... WHERE version=7 ảnh hưởng 0 row

Deadlock:
  Hai transaction giữ lock và cùng chờ nhau

Lock timeout:
  Chờ lock vượt giới hạn

Serialization failure:
  DBMS không cho một lịch sử transaction commit dưới SERIALIZABLE
~~~

Tất cả đều có thể dẫn tới retry **toàn transaction mới** nếu phù hợp, nhưng:

- Mã lỗi/exception khác nhau.
- Chính sách retry có thể khác.
- Root cause cần quan sát khác.
- Một số database đánh dấu transaction aborted và bắt buộc rollback.

### Ví dụ SQLSTATE

PostgreSQL có mã SQLSTATE cho serialization failure và deadlock detection. Nhưng không nên hardcode một SQLSTATE rồi suy ra nó áp dụng cho mọi DBMS/JDBC driver. Classifier ở tầng hạ tầng phải được kiểm thử với stack production.

### Pessimistic exception có luôn rollback toàn transaction?

Một số lock timeout được JPA/provider mô tả ở mức statement, một số dẫn tới transaction rollback. Đối với chiến lược retry **sau transaction failed**, cách an toàn là để attempt boundary quyết định rollback/cleanup; không mù quáng tiếp tục transaction nếu trạng thái đã không chắc chắn.

## 33. Retry và transaction isolation

Với optimistic locking, một attempt có thể:

~~~text
BEGIN
SELECT account(version=7)
...
UPDATE WHERE version=7
COMMIT
~~~

Khi retry:

~~~text
BEGIN transaction MỚI
SELECT account(version=8)
...
UPDATE WHERE version=8
COMMIT
~~~

Nếu ứng dụng giữ một transaction SNAPSHOT/REPEATABLE READ duy nhất rồi chỉ `clear()`, query sau có thể vẫn đọc **cùng snapshot cũ** tùy DBMS, cho dù identity map đã bị làm rỗng.

### Vì sao transaction mới quan trọng hơn việc gọi find lại?

Vì transaction mới tạo một phạm vi isolation/commit mới. Trong hệ thống MVCC, snapshot cho transaction mới có thể nhìn được commit của transaction trước. Điều này **phụ thuộc DBMS/isolation**, nhưng là mô hình đúng để ứng dụng có cơ hội cập nhật từ state hiện hành.

### SERIALIZABLE và retry

Ở SERIALIZABLE, một transaction có thể bị rollback do serialization conflict dù không có UPDATE cùng một versioned entity. Nếu nghiệp vụ cho phép, phải retry **toàn bộ transaction**, không chỉ một SQL statement.

## 34. Không dùng REQUIRES_NEW bên trong một transaction đang thực hiện nghiệp vụ lớn

Ví dụ CheckoutService:

~~~text
Outer Transaction:
  Insert Order
  Reserve Inventory
  Create PaymentRecord
  Commit
~~~

Nếu ReserveInventory được retry bằng một service `REQUIRES_NEW` rồi commit riêng:

~~~text
Outer TX:
  Insert Order (chưa commit)
  |
  +-- Inner TX:
        Reserve Inventory
        COMMIT
  |
  Outer TX gặp lỗi
  ROLLBACK
~~~

thì tồn kho đã trừ nhưng Order không tồn tại. Đây là **phá vỡ atomicity**, dù retry nội bộ đã thành công.

### Giải pháp

Đặt retry **bên ngoài toàn bộ checkout operation**, rồi mỗi attempt mở một transaction mới chứa **tất cả** database writes của checkout:

~~~text
Retry CheckoutCoordinator
    |
    +-- Attempt #1:
    |     BEGIN
    |     Insert Order
    |     Reserve Inventory
    |     PaymentRecord
    |     CONFLICT -> ROLLBACK
    |
    +-- Attempt #2:
          BEGIN
          Insert Order
          Reserve Inventory
          PaymentRecord
          COMMIT
~~~

Tất cả side effects ngoài DB vẫn phải được điều phối riêng bằng outbox/idempotency.

## 35. Retry với cascade và quan hệ entity

Một transaction không chỉ sửa một row:

~~~text
PurchaseOrder
   |
   +-- OrderLine#1
   +-- OrderLine#2
   |
   +-- InventoryItem
~~~

Nếu transaction đã:

- `persist(order)`.
- `persist(lines)` qua cascade.
- Trừ stock qua managed InventoryItem.
- Tăng version InventoryItem.

rồi một bước gặp optimistic conflict, **không được retry riêng InventoryItem** mà giữ lại Order/Lines đã rollback.

### Vì sao object graph cũ không phù hợp?

Sau rollback, những entity vừa persist có thể vẫn có generated IDs trong RAM nhưng các rows đã bị hủy trong database. Collection ownership và cascade state không còn là một snapshot hợp lệ của unit of work mới.

Trong attempt mới, tạo hoặc nạp lại graph theo business command. Không mang một graph dirty/managed của attempt cũ sang bằng merge rồi tin rằng quan hệ đã được khôi phục.

### Generated IDs có thể có khoảng trống

Database sequence/identity values có thể đã được cấp trong attempt bị rollback và không nhất thiết được tái sử dụng. Retry có thể tạo Order ID khác hoặc để lại gap trong sequence. **ID liên tiếp không phải một bảo đảm transactional**.

## 36. Retry và @Version trên aggregate root

Một nghiệp vụ sửa OrderLine có thể không tự làm PurchaseOrder.version tăng ở mọi provider/mapping.

Nếu invariant cần bảo vệ ở mức Order, ứng dụng có thể yêu cầu:

~~~java
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

trong transaction phù hợp, để buộc tăng version root theo semantics hỗ trợ.

### Lưu ý

- Không phải mọi thay đổi collection đều làm tăng version owner theo mọi mapping/provider.
- Một đường ghi native vào OrderLine có thể bỏ qua optimistic version của Order.
- Retry dựa trên Order version chỉ hữu ích khi **mọi writer liên quan** tuân thủ protocol aggregate.
- Nếu invariant gồm nhiều rows mà không có row chung/version chung, cần lock/constraint/isolation khác.

**Retry không sửa được một concurrency protocol thiếu bảo vệ invariant.** Nó chỉ thử lại khi một conflict đã được phát hiện.

## 37. Khi contention cao, có nên chuyển sang pessimistic lock?

Ví dụ một RewardAccount có hàng nghìn thao tác cộng điểm mỗi giây. Nhiều optimistic attempts cùng cập nhật một row có thể gây rất nhiều conflict và retry.

Phương án khác:

~~~java
RewardAccount account = em.find(
    RewardAccount.class,
    id,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Hoặc đối với phép cộng đơn giản:

~~~sql
UPDATE reward_accounts
SET points = points + :amount,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenant;
~~~

### So sánh

| Lựa chọn | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| @Version + retry | Không giữ lock từ lúc đọc, tốt khi conflict hiếm | Có thể rollback nhiều |
| PESSIMISTIC_WRITE | Điều phối truy cập trước khi sửa | Lock wait, deadlock, throughput giảm |
| Atomic UPDATE | Ít round-trip cho phép cộng/trừ đơn giản | Bypass managed state; phải tự quản lý version/invariant |
| Queue per key | Tránh nhiều writers cùng row | Tăng latency và độ phức tạp |
| Event ledger/append-only | Lưu mọi thay đổi theo sự kiện | Cần projection/aggregation và consistency policy |

Không phải “càng nhiều retry càng tốt”. Khi số conflict tăng, nên xem lại mô hình dữ liệu, cơ chế khóa và hotspot hơn là chỉ tăng maxAttempts.

## 38. Atomic update không đòi retry optimistic theo cùng cách

Với phép cộng thuần:

~~~sql
UPDATE reward_accounts
SET points = points + :amount,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenant;
~~~

thao tác dùng **giá trị hiện tại của database trong chính câu UPDATE**. Khi DBMS phối hợp row locks/isolations phù hợp, nó tránh kiểu gán tuyệt đối từ snapshot cũ.

Tuy nhiên:

- Không kiểm tra business rules ngoài predicate SQL.
- Vẫn cần idempotency để tránh trùng event.
- Có thể thất bại vì lock timeout, deadlock hoặc constraint.
- JPA managed RewardAccount đã nạp trước đó có thể stale.
- Version phải được tăng/điều phối thủ công khi bulk/native SQL bypass automatic @Version.

Đây là lựa chọn để **giảm nhu cầu optimistic retry** cho một loại operation cụ thể, không phải một cách sửa tổng quát cho mọi nghiệp vụ.

## 39. Một transaction mới có cần dùng cùng DB connection?

Không. Khi kết thúc attempt, connection có thể được trả về pool; attempt tiếp theo nhận cùng physical connection hoặc connection khác. Điều ứng dụng cần bảo đảm là:

- Mỗi attempt có **transaction boundary độc lập**.
- EntityManager/context không giữ state stale qua attempts.
- Cả operation làm việc trên đúng database/resource và tenant.
- Transaction manager có thể commit/rollback đúng.

Việc cố ép retry dùng một physical JDBC connection mới **không phải yêu cầu cốt lõi**. Một connection có thể được tái sử dụng qua pool sau khi rollback và reset session state đúng; các transaction vẫn là các transaction khác nhau.

### Vấn đề thật sự

Nếu connection/session cũ đang ở trạng thái transaction aborted hoặc chưa rollback, bắt đầu một “retry” trên nó không có nghĩa bắt đầu giao dịch mới thành công. Transaction manager phải đóng/rollback/reset resource đúng trước attempt tiếp theo.

## 40. Isolation của request và optimistic conflict của UI

Retry được đặt ở tầng backend không đồng nghĩa UI luôn nên nhận success.

### Trường hợp tác vụ background

Một event “khách hoàn thành bài học, +10 điểm” có idempotency key, semantics cộng dồn rõ. Service có thể retry vài lần khi collision.

### Trường hợp trang quản trị

Người dùng sửa đơn:

~~~text
expectedVersion=3
currentVersion=4
~~~

Service không nên biến 409 thành retry tự động rồi ghi theo phiên bản 4. Người dùng cần biết người khác đã thay đổi dữ liệu.

### Trường hợp tính giá/phí tự động

Nếu backend tính lại phí từ state đơn hàng mới trong một quy trình có invariant rõ, retry có thể hợp lý, nhưng phải kiểm tra giới hạn, khuyến mại, tính lại tiền và điều kiện khách đã đồng ý. Không chỉ “cộng lại một số” khi state đã đổi.

## 41. Test cơ bản: hai EntityManager cùng đọc version cũ

Để kiểm thử optimistic conflict, dùng **hai EntityManager và hai transaction độc lập**.

Fixture:

~~~text
RewardAccount#10:
    points=200
    version=4
~~~

Sơ đồ:

~~~text
EM_A / TX_A                           EM_B / TX_B
----------------------------------    ----------------------------------
BEGIN                                 BEGIN
find(id=10) -> 200,v=4                find(id=10) -> 200,v=4
addPoints(30)                         addPoints(50)
flush / commit -> 230,v=5
                                      flush/commit -> conflict
                                      rollback
~~~

Kỳ vọng:

- A được commit.
- B bị từ chối version cũ (hoặc DBMS báo conflict tương ứng).
- Database committed không bị ghi thành 250.
- Retry B trong transaction/context **mới** sẽ đọc 230 rồi cộng thành 280 nếu operation được cho phép.

### Vì sao không chia sẻ EntityManager?

EntityManager không được thiết kế cho concurrent access giữa threads. Hai transactions phải có hai context độc lập. Một test dùng chung EM có thể kiểm tra nhầm identity map thay vì optimistic concurrency thực.

## 42. Skeleton integration test RESOURCE_LOCAL

Ví dụ dưới đây minh họa cách tạo hai contexts cùng đọc dữ liệu cũ; cần điều chỉnh cách điều phối transaction theo DBMS để tránh giữ snapshot/lock không phù hợp:

~~~java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    emA.getTransaction().begin();
    emB.getTransaction().begin();

    RewardAccount a =
        emA.find(RewardAccount.class, accountId);
    RewardAccount b =
        emB.find(RewardAccount.class, accountId);

    // Cả hai đã đọc cùng một version trước khi A commit.
    a.addPoints(30);
    b.addPoints(50);

    emA.flush();
    emA.getTransaction().commit();

    boolean conflictDetected = false;
    try {
        emB.flush();
        emB.getTransaction().commit();
    } catch (OptimisticLockException ex) {
        conflictDetected = true;
        if (emB.getTransaction().isActive()) {
            emB.getTransaction().rollback();
        }
    }

    if (!conflictDetected) {
        throw new AssertionError(
            "Expected optimistic conflict");
    }
} finally {
    if (emA.getTransaction().isActive()) {
        emA.getTransaction().rollback();
    }
    if (emB.getTransaction().isActive()) {
        emB.getTransaction().rollback();
    }
    emA.close();
    emB.close();
}
~~~

### Giới hạn của skeleton

- Phải import `jakarta.persistence.OptimisticLockException`, `EntityManager`, `BigDecimal`/type tương ứng nếu dùng.
- Provider có thể bọc optimistic exception trong exception khác, hoặc ném ở commit.
- Một số DBMS/isolation có thể báo serialization failure thay vì đúng `OptimisticLockException`.
- Nếu dùng test framework tự rollback transaction bao ngoài hoặc chia sẻ persistence context, test có thể không tái tạo xung đột.
- Không catch mọi `RuntimeException` rồi tuyên bố optimistic locking hoạt động.

Test production cần chạy trên DBMS/provider thật, giải phóng resource đúng và kiểm tra exception classification chính xác theo stack.

## 43. Test quan trọng hơn: một lần retry có thật sự đọc state mới?

Sau conflict của B, tạo một EntityManager khác:

~~~java
EntityManager retryEm = emf.createEntityManager();

try {
    retryEm.getTransaction().begin();

    RewardAccount fresh =
        retryEm.find(RewardAccount.class, accountId);

    // Kỳ vọng sau commit của A:
    assertEquals(230L, fresh.getPoints());

    fresh.addPoints(50);
    retryEm.flush();
    retryEm.getTransaction().commit();
} finally {
    if (retryEm.getTransaction().isActive()) {
        retryEm.getTransaction().rollback();
    }
    retryEm.close();
}
~~~

Đây là JUnit-style pseudocode với fixture thích hợp. Sau đó, mở **EntityManager kiểm tra riêng**:

~~~text
Expected:
    points=280
    version=6 (nếu bắt đầu v=4 và mỗi update tăng một đơn vị)
~~~

Số version tăng cụ thể phụ thuộc quy tắc/version strategy và không nên hardcode cho mọi provider/loại version. Với `Long @Version` phổ biến, kỳ vọng hai updates thành công tăng version tương ứng có thể được test theo stack.

### Kiểm tra điều quan trọng

Test phải chứng minh B đã cộng 50 **trên 230**, không phải:

- Gán lại 250 từ snapshot cũ.
- Cộng 50 lần hai trên object cũ đã là 250.
- Sử dụng cùng persistence context stale.

## 44. Test retry coordinator và số lần mở transaction

Một unit test có thể mock `RewardAccountWriter.addPointsOnce`:

~~~text
Call 1 -> throw OptimisticLockException
Call 2 -> return RewardSnapshot
~~~

Test xác minh coordinator:

- Retry tối đa số lần cấu hình.
- Không retry validation errors.
- Không backoff trước lần đầu.
- Dừng ngay khi thành công.
- Trả exception gốc/hợp lý khi hết attempts.

Nhưng mock test **không chứng minh transaction/context mới**. Integration test phải kiểm tra:

1. Writer tạo EntityManager mới trong RESOURCE_LOCAL, hoặc Spring transaction manager mở transaction mới.
2. Previous transaction đã rollback trước attempt mới.
3. Entity version thực sự thay đổi và attempt mới đọc lại.
4. Không có side effects database bị ghi hai lần.

### SQL logging và transaction IDs

Có thể dùng logs/metrics để quan sát begin/rollback/commit, EntityManager creation và SQL:

~~~text
attempt=1 transaction=txA SELECT version=4
attempt=1 transaction=txA UPDATE conflict
attempt=1 transaction=txA ROLLBACK
attempt=2 transaction=txB SELECT version=5
attempt=2 transaction=txB UPDATE success
attempt=2 transaction=txB COMMIT
~~~

Không đưa thông tin nhạy cảm hoặc session credentials vào log production.

## 45. Test failure sau khi đã tạo entity liên quan

Giả sử operation:

~~~text
BEGIN
  INSERT RewardEvent
  UPDATE RewardAccount
  INSERT OutboxEvent
COMMIT
~~~

Khi UPDATE account gặp optimistic conflict, toàn bộ transaction rollback. Test cần xác minh:

- RewardEvent của attempt thất bại không tồn tại sau rollback.
- OutboxEvent của attempt thất bại không tồn tại.
- Account vẫn phản ánh write được commit bởi transaction thắng.
- Attempt mới tạo các rows đúng **một lần** khi commit.
- Unique request_key tiếp tục ngăn duplicate khi request được gửi lại.

### Tránh assertion trên Java objects stale

Không dùng `emFailed.find()` trên persistence context đã rollback để xác nhận database. Hãy mở context/transaction kiểm tra mới và đọc committed state.

## 46. Test concurrent với barrier/latch

Nếu muốn kiểm tra tranh chấp thực sự song song:

~~~text
Worker A                        Worker B
----------------------------    ----------------------------
BEGIN                           BEGIN
find account v=4                find account v=4
     \                            /
      \ ---- CountDownLatch ---- /
       \                        /
addPoints(30)                  addPoints(50)
flush/commit                   flush/commit
~~~

Không dùng `Thread.sleep(...)` để giả định B đã đọc xong trước A; timing phụ thuộc CPU/scheduler. Dùng barrier/latch để bảo đảm đúng sự kiện.

### Những lưu ý

- Hai threads dùng hai EntityManager/transactions.
- Test pool đủ connections.
- Có timeout tránh deadlock test harness.
- Quan sát commit/rollback và loại lỗi chính xác.
- Không để assertions tự gây deadlock khi một worker chưa release barrier.
- Đọc state cuối qua context mới.

Nếu test có database transaction snapshot behavior khác, cần điều chỉnh timeline sao cho cả hai thật sự đọc version cũ trước khi một commit.

## 47. Khi không thể retry ngay, làm gì?

Một hệ thống tải cao có thể nhận quá nhiều conflicts hoặc đang thiếu resource. Sau số attempts giới hạn:

1. Trả domain conflict/busy và cho caller quyết định.
2. Với background job idempotent, đẩy lại vào queue có retry policy.
3. Dùng backoff dài hơn ở scheduler thay vì giữ HTTP thread.
4. Xem thiết kế dữ liệu hot row, chiến lược lock hoặc atomic UPDATE.
5. Theo dõi tỷ lệ conflict theo entity/key để xác định hotspot.

### Không tự động lên lịch một tác vụ không idempotent

Nếu job sẽ charge payment hoặc gửi thông báo ngoài transaction, phải có trạng thái/khóa duy nhất trước khi retry bất đồng bộ. “Retry sau 5 phút” không tự làm side effect trở nên an toàn.

## 48. Observability: cần đo những gì?

Trong production, có thể theo dõi:

- Tỷ lệ optimistic conflict trên từng operation/entity.
- Số attempts trung bình và phân bố attempts.
- Tỷ lệ thành công sau retry.
- Số requests hết retry budget.
- Latency của attempt đầu và toàn operation.
- Thời gian backoff.
- Deadlock/serialization/lock timeout phân biệt với optimistic conflicts.
- Số lượng duplicated request keys và idempotency hits.
- Transaction rollbacks và commit failures.
- Hotspot keys, nhưng phải tránh log trực tiếp thông tin nhạy cảm.

### Một vài chỉ báo thiết kế

| Quan sát | Giả thuyết cần kiểm tra |
| --- | --- |
| Conflict cao trên một account | Hotspot, mô hình one-row aggregate |
| Retry thành công nhưng latency tăng mạnh | Too many contenders/backoff/DB contention |
| Conflict gần như luôn thất bại | Lỗi logic/version mapping hoặc transaction boundary sai |
| Có nhiều notification duplicate | Side effects nằm ngoài transaction/idempotency |
| 409 tăng sau deploy | Thay đổi fetch/version/DTO contract hoặc client gửi version cũ |
| Mỗi attempt SELECT vẫn version cũ | Cache/snapshot/context reuse hoặc replica lag |

Đừng chỉ log “retry=2” mà không biết transaction trước đã rollback hay request đã thực sự commit chưa.

## 49. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai/rủi ro | Cách thay thế |
| --- | --- | --- |
| Catch `OptimisticLockException` rồi `em.flush()` lại | Transaction có thể rollback-only, entity stale | Rollback, transaction/context mới |
| `em.clear()` rồi nghĩ đã reset transaction | Clear không rollback hoặc begin mới | Transaction boundary mới |
| Retry bằng entity đã dirty từ attempt trước | State/giá trị tính cũ | Retry từ business command và đọc lại |
| Retry trong một method `@Transactional` duy nhất | Cùng transaction/context | Coordinator ngoài TX, attempt riêng |
| Tự gọi `this.transactionalMethod()` | Có thể bỏ qua Spring proxy | Gọi qua bean/proxy phù hợp |
| Dùng `REQUIRES_NEW` lồng trong outer unit of work | Commit tách rời, phá atomicity | Retry toàn outer unit |
| Retry mọi `RuntimeException` | Che lỗi schema/validation/auth | Retry classifier có kiểm soát |
| Retry vô hạn | Retry storm, quá tải | Attempts/deadline/backoff |
| Sleep khi transaction vẫn active | Giữ lock/connection lâu | Backoff sau rollback |
| Retry stale UI update tự động | Ghi đè quyết định người dùng khác | 409/412, UI resolve |
| Chỉ dùng @Version mà bỏ expectedVersion của GET | Stale form qua nhiều request lọt qua | ETag/If-Match hoặc body version |
| Retry request đã commit nhưng mất response | Nhân đôi business effect | Idempotency key/outcome lookup |
| Gửi email trước commit của attempt | Email duplicate/phát dù rollback | Transactional outbox |
| Bulk SQL không tăng/check version | JPA không biết write ngoài managed entity | Một concurrency protocol thống nhất |
| Sửa giá trị tuyệt đối tính từ snapshot cũ | Lost update vẫn có thể xảy ra | Recompute trên fresh entity hoặc atomic SQL |
| Retry nhưng không kiểm tra lại stock/credit limit | Business invariant có thể đã đổi | Revalidate trong mỗi attempt |
| Dùng cùng EntityManager giữa threads | Không thread-safe, sai context | Một EM riêng cho từng TX/thread |
| Dựa vào cache để biết latest version | Có thể stale | Context mới, cache/DB policy đúng |
| Chỉ test mock retry | Không chứng minh DB/version check | Integration test hai transactions |
| Trả success ngay sau setter/flush | Commit có thể fail | Xác nhận sau transaction boundary |

## 50. Checklist trước khi đưa retry vào production

1. **Xác định operation cần retry:** một câu SQL, một entity hay toàn unit of work?
2. **Phân loại exception:** optimistic conflict, deadlock, serialization, lock timeout, business error.
3. **Kiểm tra retry semantics:** operation có thể tái tính toán không?
4. **Thiết kế command bất biến:** tenant, entity ID, amount/delta, request key.
5. **Bảo vệ stale human decisions:** expectedVersion/ETag cho form editing.
6. **Bắt đầu transaction mới cho từng attempt.**
7. **Dùng persistence context mới hoặc đảm bảo không còn state stale.**
8. **Đọc lại dữ liệu hiện hành và revalidate invariants.**
9. **Đặt retry coordinator ngoài transaction và bắt được lỗi commit.**
10. **Không dùng REQUIRES_NEW để phá outer atomicity.**
11. **Rollback hoàn chỉnh trước backoff.**
12. **Đặt giới hạn attempts và deadline.**
13. **Dùng backoff/jitter khi contention.**
14. **Đảm bảo tenant/ACL ở mỗi attempt.**
15. **Tăng/check @Version ở mọi đường ghi liên quan.**
16. **Thiết kế idempotency key chống duplicate request.**
17. **Chuyển side effects ngoài DB sang outbox/idempotent worker.**
18. **Kiểm tra outcome khi lỗi commit không rõ thành công hay thất bại.**
19. **Kiểm thử hai EntityManager/transactions thật.**
20. **Theo dõi tỷ lệ conflict và tác động lên throughput/latency.**

## 51. Bài tập thực hành

### Bài 1 — Sai ở đâu?

~~~java
@Transactional
public void add(...) {
    for (int i = 0; i < 3; i++) {
        try {
            account.addPoints(30);
            em.flush();
            break;
        } catch (OptimisticLockException ex) {
            em.clear();
        }
    }
}
~~~

**Gợi ý:** vòng lặp vẫn trong cùng transaction; sau optimistic conflict có thể rollback-only; account cũ là object stale; clear không tạo transaction mới.

### Bài 2 — Transaction hay EntityManager?

Một application rollback transaction cũ nhưng vẫn giữ EntityManager extended với một RewardAccount đã dirty. Nó đã đủ điều kiện retry chưa?

**Gợi ý:** chưa; phải xử lý state stale/context lifecycle, đọc lại dữ liệu đúng trong transaction mới.

### Bài 3 — Tính lại từ state mới

Ban đầu points=200, v=4. A cộng 30 và commit. B định cộng 50 và gặp conflict. B nên ghi 250 hay 280 khi retry?

**Gợi ý:** đọc 230 rồi cộng 50 thành 280.

### Bài 4 — Trừ điểm và invariant

Ban đầu points=100. A trừ 80 và commit. B định trừ 50 nhưng gặp conflict. Khi retry B đọc points=20. Có nên tiếp tục trừ 50?

**Gợi ý:** không; đủ điểm là invariant phải kiểm tra lại, trả business error.

### Bài 5 — Catch ở đâu trong Spring?

Vì sao try/catch **bên trong** `@Transactional` service có thể không bắt được optimistic conflict xuất hiện lúc commit?

**Gợi ý:** transaction interceptor commit sau khi method body return; bắt ở coordinator bên ngoài proxy invocation.

### Bài 6 — Propagation

Retry coordinator gọi `@Transactional(REQUIRED)` method ba lần nhưng coordinator nằm trong outer `@Transactional`. Có bảo đảm ba physical transactions không?

**Gợi ý:** không; REQUIRED tham gia outer transaction.

### Bài 7 — REQUIRES_NEW

Một checkout outer transaction lưu Order; inner REQUIRES_NEW trừ tồn kho và commit. Outer rollback. Kết quả có thể sai thế nào?

**Gợi ý:** stock đã trừ nhưng Order bị hủy; cần retry/transaction cho toàn checkout.

### Bài 8 — Thời điểm backoff

Nên sleep trước hay sau rollback transaction lỗi?

**Gợi ý:** sau rollback/giải phóng resource; không giữ lock/transaction trong thời gian chờ.

### Bài 9 — Loại lỗi

Một retry classifier xử lý mọi `PersistenceException` như transient. Có nguy cơ gì?

**Gợi ý:** retry lỗi schema/mapping/constraint không thể tự hết.

### Bài 10 — Stale form

Client B gửi `expectedVersion=7`; server nạp Product hiện tại version=8. Có nên auto retry rồi áp price của B?

**Gợi ý:** thường không; trả 409 hoặc 412 theo API contract để user resolve.

### Bài 11 — Commit outcome

Client mất network sau COMMIT; không biết transaction đã commit hay chưa. Có nên retry một thao tác cộng điểm không có idempotency key?

**Gợi ý:** không; có thể cộng hai lần.

### Bài 12 — Idempotency key

Tại sao chỉ SELECT để xem request key chưa tồn tại rồi INSERT không đủ an toàn khi có hai requests đồng thời?

**Gợi ý:** cả hai có thể cùng SELECT “chưa tồn tại”; cần UNIQUE constraint và xử lý duplicate outcome.

### Bài 13 — Outbox

Một attempt gửi email rồi optimistic conflict, attempt mới gửi email lần nữa. Vì sao đây là lỗi dù database cuối đúng?

**Gợi ý:** email là side effect ngoài DB không bị rollback; cần outbox/idempotency.

### Bài 14 — New context

`em.clear()` rồi `em.find()` ngay trong transaction rollback-only có thể thay cho retry mới không?

**Gợi ý:** không; transaction vẫn thất bại.

### Bài 15 — Provider exception

Một ứng dụng Spring chỉ catch trực tiếp `jakarta.persistence.OptimisticLockException`. Có thể bỏ sót optimistic conflicts không?

**Gợi ý:** có; Spring/provider có thể translate/wrap exception, nhất là tại commit.

### Bài 16 — Đếm attempts

Nếu `maxAttempts=3`, “3” có nghĩa 3 retries sau lần đầu hay 3 lần thử tổng?

**Gợi ý:** định nghĩa rõ. Trong ví dụ bài, có tối đa **3 attempts tổng** (lần đầu + tối đa hai lần thử lại).

### Bài 17 — Hotspot

Một RewardAccount có hàng nghìn credits/giây, phần lớn optimistic attempts fail. Có nên chỉ tăng maxAttempts từ 3 lên 100?

**Gợi ý:** không; xem atomic SQL, queue/partitioning/pessimistic lock hoặc redesign hotspot.

### Bài 18 — Batch update

Một bulk JPQL UPDATE đổi points nhưng không tăng @Version. Các transaction JPA cũ có chắc phát hiện không?

**Gợi ý:** không; mọi writer phải tuân thủ concurrency protocol.

### Bài 19 — Entity graph từ attempt cũ

Một attempt persist Order và OrderLines rồi rollback. Có nên đem graph đó merge vào attempt mới và xem là retry đúng?

**Gợi ý:** không mặc định; object graph còn generated IDs/pending state cũ. Dựng lại từ business command.

### Bài 20 — Test concurrency

Làm sao bảo đảm hai transaction cùng thấy version=4 trước khi một transaction commit?

**Gợi ý:** dùng hai EntityManager/transactions và điều phối điểm đọc bằng barrier/latch hoặc thứ tự test tường minh; không chia sẻ EM.

### Bài 21 — TransactionTemplate

Nếu `TransactionTemplate` dùng REQUIRED và caller đã có transaction, callback có chắc mở transaction mới không?

**Gợi ý:** không; callback có thể join. Đặt coordinator ngoài outer TX hoặc cấu hình boundary đúng.

### Bài 22 — API success

Service gọi `em.flush()` thành công, trả 200 trước khi transaction manager COMMIT. Có chắc write đã commit không?

**Gợi ý:** không; commit vẫn có thể thất bại. Confirm thành công tại transaction boundary.

### Bài 23 — Cache

Attempt mới mở EntityManager nhưng vẫn đọc version cũ qua cache/replica. Có thể làm gì?

**Gợi ý:** kiểm tra tính nhất quán read/write, cache invalidation, replica routing và isolation.

### Bài 24 — Row-level vs aggregate invariant

Hai transactions sửa hai OrderLines khác nhau nhưng cùng phá tổng hạn mức Order. @Version riêng của mỗi Line có đủ không?

**Gợi ý:** chưa chắc; cần bảo vệ aggregate/invariant chung bằng version root, lock hoặc constraint/isolation thích hợp.

### Bài 25 — Một unit of work

Operation gồm tăng điểm, ghi RewardEvent và OutboxEvent. Nếu conflict phát sinh ở bước cập nhật điểm, retry nên lặp những bước nào?

**Gợi ý:** toàn bộ transaction nghiệp vụ, với idempotency key để ngăn duplicate event khi outcome không rõ.

## 52. Tóm tắt quyết định: thử lại hay dừng?

~~~text
Operation thất bại
        |
        v
Lỗi có phải retryable concurrency conflict?
        |
     +-- KHÔNG ---> Trả lỗi thật, không retry mù.
        |
       CÓ
        |
        v
Lần trước chắc chắn rollback, không có
commit-outcome uncertainty/side effect ngoài?
        |
     +-- KHÔNG ---> Kiểm tra idempotency/outcome,
        |            compensation nếu cần.
        |
       CÓ
        |
        v
Business command có an toàn khi tái tính toán?
        |
     +-- KHÔNG ---> Trả conflict, yêu cầu người dùng
        |            hoặc workflow khác quyết định.
        |
       CÓ
        |
        v
Đã hết attempts/deadline?
        |
     +-- CÓ ------> Dừng, trả conflict/busy phù hợp.
        |
      CHƯA
        |
        v
ROLLBACK + đóng context lỗi
        |
        v
Backoff (ngoài transaction)
        |
        v
BEGIN transaction/context mới
        |
        v
SELECT state mới + revalidate invariant
        |
        v
Thực hiện lại toàn unit of work
        |
        v
COMMIT hoặc xử lý conflict tiếp
~~~

### Bảng ghi nhớ

| Tình huống | Hành động nên cân nhắc |
| --- | --- |
| `OptimisticLockException` trên operation cộng dồn idempotent | Rollback, context mới, đọc lại, retry có giới hạn |
| `OptimisticLockException` khi người dùng sửa form | Trả conflict, không tự overwrite |
| Transaction rollback-only | Không tiếp tục, rollback |
| Entity dirty từ attempt lỗi | Không dùng làm dữ liệu retry |
| Spring retry đặt bên trong `@Transactional` | Đưa retry ra ngoài transaction boundary |
| Retry trong outer transaction có nhiều nghiệp vụ | Retry toàn outer unit, tránh inner commit riêng |
| Retry ngắn trên hot row | Backoff/jitter, đo contention |
| Retry request có thể đã commit | Dùng idempotency/outcome lookup |
| Email/payment/message ngoài transaction | Outbox/idempotency/compensation |
| Native/bulk writer bỏ version | Sửa concurrency protocol |
| Retry ở SERIALIZABLE | Transaction mới và tái kiểm tra toàn bộ reads |
| Cần xác nhận hoạt động | Integration test hai contexts và kiểm tra committed state |

## Kết luận

**Thử lại bằng giao dịch và ngữ cảnh mới khi phù hợp** là bước tiếp theo của một thiết kế optimistic locking đúng: khi một attempt thất bại, kết thúc transaction cũ, loại bỏ persistence context stale, đọc lại dữ liệu đã thay đổi và **thực hiện lại toàn bộ quyết định nghiệp vụ** trong một transaction độc lập. Chỉ gọi lại `flush()`, `merge()` hoặc sửa entity cũ không giải quyết được rollback-only state và có thể gây sai giá trị.

Tuy nhiên, **không phải conflict nào cũng nên tự retry**. Với phép cộng dồn được thiết kế idempotent, retry có giới hạn và backoff có thể là cách phục hồi tốt. Với chỉnh sửa từ một form cũ, retry im lặng có thể vô hiệu hóa mục đích của `@Version`; nên dùng expectedVersion/ETag và yêu cầu người dùng giải quyết. Khi kết quả COMMIT không rõ hoặc có tác động ngoài database, phải dựa trên idempotency, outbox và kiểm tra outcome thay vì phát lại toàn bộ một cách mù quáng.

Điều quan trọng nhất là **đặt retry coordinator ngoài transaction của mỗi attempt, giữ unit of work nguyên tử, tái kiểm tra invariant trên state mới và kiểm thử bằng nhiều transaction/persistence context thật**. Làm được như vậy giúp ứng dụng xử lý xung đột đồng thời có kiểm soát mà không âm thầm làm mất cập nhật hoặc nhân đôi tác dụng nghiệp vụ.
