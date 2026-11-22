# Khác biệt giữa ghi bộ nhớ, flush và commit trong Spring Transaction Management

## 1. Ba mốc khác nhau của cùng một thay đổi

Khi làm việc với Spring Framework, JPA/Hibernate và một cơ sở dữ liệu quan hệ, câu “đã lưu dữ liệu” có thể mô tả ba trạng thái rất khác nhau:

1. **Ghi vào bộ nhớ ứng dụng**: đối tượng Java đang được quản lý (*managed entity*) đã thay đổi trong `Persistence Context`. Thay đổi có thể mới tồn tại trong trạng thái mà JPA/Hibernate theo dõi.
2. **Flush**: JPA/Hibernate đồng bộ các thay đổi đang chờ từ `Persistence Context` xuống cơ sở dữ liệu bằng các câu lệnh SQL phù hợp. Những câu lệnh này chạy **trong transaction hiện tại**.
3. **Commit**: hệ quản trị cơ sở dữ liệu xác nhận transaction thành công, khiến các thay đổi trở thành kết quả đã cam kết theo những bảo đảm của database.

**Điểm mấu chốt: flush không phải commit; thay đổi ở bộ nhớ cũng không bảo đảm SQL đã chạy.** Một transaction vẫn có thể `ROLLBACK` sau khi `flush()` thành công.

| Tiêu chí | Thay đổi trong bộ nhớ | `flush` | `commit` |
| --- | --- | --- | --- |
| Nơi thể hiện thay đổi | Đối tượng Java / `Persistence Context` | Database đã nhận, thực thi các SQL cần thiết trong transaction | Database đã cam kết transaction |
| SQL bắt buộc đã chạy chưa? | Chưa chắc | Các thao tác đang chờ thuộc lần flush đã được đồng bộ; provider có thể đã chạy một số SQL sớm hơn | Các thay đổi cần thiết đã được xử lý để commit thành công |
| Dữ liệu đã commit chưa? | Không suy ra được | **Chưa**, chỉ vì vừa flush | **Có**, nếu commit thực sự thành công |
| Transaction khác có thấy không? | Không thể kết luận từ trạng thái Java | Thường chưa, với mức cô lập `READ COMMITTED` | Có thể thấy theo mức cô lập, snapshot và thời điểm truy vấn của transaction đọc |
| Có thể rollback thay đổi DB không? | Có, nếu thay đổi thuộc transaction chưa commit | **Có** với các thao tác DB có tính giao dịch | Không thể dùng rollback của transaction đã kết thúc để đảo ngược commit |
| Lỗi có thể xuất hiện | Lỗi nghiệp vụ ở Java | Lỗi SQL, khóa ngoại, unique, optimistic locking... | Lỗi ràng buộc hoãn kiểm tra, xung đột, kết nối hoặc lỗi tại bước commit |

Bảng này mô tả trường hợp thông dụng: Spring quản lý transaction, JPA/Hibernate làm ORM và database có transaction. Không nên đánh đồng “ghi bộ nhớ” với “database đã ghi ra ổ đĩa”: buffer của database, write-ahead log, cache của ORM và bộ nhớ heap Java là những tầng khác nhau.

## 2. “Ghi bộ nhớ” nghĩa là gì trong JPA/Hibernate?

### 2.1. Persistence Context và managed entity

`EntityManager` duy trì một `Persistence Context`, thường gắn với transaction trong ứng dụng Spring. Đây là nơi JPA theo dõi những entity đang được quản lý, danh tính của chúng và các thay đổi phải đồng bộ với database.

Ví dụ:

```java
@Transactional
public void changeBalance(Long accountId) {
    Account account = entityManager.find(Account.class, accountId);
    account.setBalance(200L); // Thay đổi trạng thái của managed entity
    // Không có lệnh SQL UPDATE tường minh tại dòng setter này.
}
```

Trong ví dụ trên, nếu `account` là managed entity, JPA có thể phát hiện phần trạng thái bị sửa thông qua *dirty checking* và tạo SQL khi cần flush. **Không cần gọi `save()` sau mỗi setter của managed entity.**

Lưu ý ba trường hợp:

- **Managed**: entity còn được gắn với `Persistence Context`; những sửa đổi thuộc các trường persistent được JPA theo dõi.
- **New/transient**: object mới tạo bằng `new` không tự trở thành đối tượng bền vững; cần `persist()` hoặc cơ chế thích hợp như `repository.save()`.
- **Detached**: object đã tách khỏi `Persistence Context`; thay đổi field của object đó không tự được đồng bộ. `merge()` có thể đưa trạng thái sang một managed instance; bản trả về mới là instance cần tiếp tục thao tác.

“Đã set field” không có nghĩa database đã lưu. Ngược lại, cũng không thể kết luận “chưa gọi flush thì chưa có SQL”: chiến lược cấp ID như `IDENTITY`, lệnh truy vấn, hoặc thao tác khác có thể khiến provider thực thi SQL sớm.

### 2.2. Phân biệt các lớp bộ nhớ

- **Java object và Persistence Context (L1 cache)**: trạng thái entity trong ứng dụng, gắn với ngữ cảnh JPA.
- **Hibernate action queue / cơ chế write-behind**: các thao tác dự kiến được quản lý, có thể được gom nhóm và sắp xếp để đồng bộ sau.
- **Database buffer/cache và transaction log**: cơ chế nội bộ của hệ quản trị CSDL, độc lập với việc đối tượng Java còn managed hay không.

Vì vậy, “đã ghi vào bộ nhớ” cần được nói rõ là bộ nhớ nào. Với chủ đề này, ta chủ yếu nói về **thay đổi trạng thái entity trong Persistence Context**.

## 3. Flush: đồng bộ SQL, chưa kết thúc transaction

`EntityManager.flush()` yêu cầu đồng bộ các thay đổi đang chờ trong `Persistence Context` với database. Hibernate thường chuyển đổi các thao tác thích hợp thành `INSERT`, `UPDATE` và `DELETE`.

```java
@Transactional
public void changeBalanceAndFlush(Long accountId) {
    Account account = entityManager.find(Account.class, accountId);
    account.setBalance(200L);

    entityManager.flush(); // Đồng bộ SQL với DB trong transaction hiện tại

    // Transaction vẫn đang mở trong thân phương thức này.
    // Một RuntimeException sau đây vẫn có thể khiến transaction rollback.
}
```

Điều `flush()` đem lại:

- Đẩy các thay đổi cần đồng bộ tới database ở thời điểm chủ động hơn, thay vì để tới lúc commit.
- Có thể làm lộ ra **sớm** các lỗi DB như vi phạm khóa ngoại, unique constraint, not-null hoặc lỗi khóa phiên bản.
- Giúp SQL đã chạy trong transaction được những câu SQL tiếp theo của **cùng transaction** nhìn thấy theo quy tắc của DB.
- Có thể tạo lock hoặc chi phí I/O/round-trip sớm hơn; flush quá thường xuyên làm giảm cơ hội batching.

Điều `flush()` **không** đem lại:

- Không gọi `COMMIT`.
- Không bảo đảm các transaction khác lập tức thấy thay đổi.
- Không bảo đảm kết quả chắc chắn sẽ bền vững nếu transaction sau đó rollback hoặc commit thất bại.
- Không đồng nghĩa với `fsync` hay một lệnh “đẩy mọi byte từ RAM xuống ổ đĩa”.
- Không chỉ giới hạn ở entity vừa lưu: một lần flush có thể xử lý **nhiều thay đổi đang chờ trong cùng Persistence Context**.

Một số database có ràng buộc *deferrable* được kiểm tra khi commit; vì vậy **flush thành công không bảo đảm commit chắc chắn thành công**.

Nếu gọi `EntityManager.flush()` mà không có transaction đang hoạt động hoặc Persistence Context chưa tham gia transaction, JPA có thể ném `TransactionRequiredException`; không nên xem flush là cơ chế lưu dữ liệu độc lập transaction.

## 4. Commit: xác nhận toàn bộ transaction

Trong một phương thức Spring được gọi **qua proxy transaction** với `@Transactional`, transaction interceptor thường mở hoặc tham gia transaction trước khi gọi thân phương thức. Khi thân phương thức hoàn tất, Spring dùng `PlatformTransactionManager` phù hợp để quyết định commit hoặc rollback.

Với JPA thông thường, trước khi commit thành công, các thay đổi persistent cần thiết được flush/synchronize. Vì vậy **không cần `flush()` thủ công chỉ để “bảo đảm dữ liệu được lưu” trong mọi phương thức transactional**.

Trình tự thường gặp:

```text
Lời gọi vào proxy @Transactional
    -> bắt đầu hoặc tham gia transaction
    -> load managed entity
    -> sửa field: trạng thái ở Persistence Context thay đổi
    -> (có thể auto-flush trước truy vấn hoặc flush thủ công)
    -> phương thức nghiệp vụ trả về
    -> Spring hoàn tất transaction: flush cần thiết và COMMIT
    -> proxy trả kết quả cho bên gọi nếu commit thành công
```

Nếu gặp ngoại lệ dẫn đến rollback:

```text
sửa managed entity -> flush -> SQL UPDATE đã chạy
    -> RuntimeException -> Spring ROLLBACK
    -> UPDATE chưa commit bị database hoàn tác
```

**Ranh giới commit là ranh giới transaction, không phải dòng `repository.save(...)` hoặc `entityManager.flush()`.** Với `Propagation.REQUIRED` (mặc định), phương thức thường tham gia transaction hiện có; trong trường hợp đó, commit cuối cùng thuộc về owner của transaction bên ngoài.

Theo mặc định của Spring, `RuntimeException` và `Error` kích hoạt rollback; checked exception thông thường không tự kích hoạt rollback trừ khi có cấu hình rollback tương ứng. Việc nuốt ngoại lệ có thể khiến lời gọi kết thúc bình thường và transaction tiếp tục đến commit; xử lý lỗi phải nhất quán với ý định rollback.

## 5. Ví dụ Spring Data JPA: flush rồi vẫn rollback

Các mảnh mã sau minh họa một ứng dụng **Java 17+, Spring Data JPA, Jakarta Persistence (`jakarta.persistence`)**. Đây là những file cần đặt trong một Spring Boot project đã cấu hình `spring-boot-starter-data-jpa` và database; chúng **không phải một chương trình Java độc lập chỉ cần `javac`**.

**`Account.java`**

```java
package demo.transaction;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false)
    private long balance;

    protected Account() {
        // JPA cần constructor không đối số.
    }

    public Account(Long id, long balance) {
        this.id = id;
        this.balance = balance;
    }

    public Long getId() {
        return id;
    }

    public long getBalance() {
        return balance;
    }

    public void setBalance(long balance) {
        this.balance = balance;
    }
}
```

**`AccountRepository.java`**

```java
package demo.transaction;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<Account, Long> {
}
```

**`AccountService.java`**

```java
package demo.transaction;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final AccountRepository accounts;
    private final EntityManager entityManager;

    public AccountService(AccountRepository accounts, EntityManager entityManager) {
        this.accounts = accounts;
        this.entityManager = entityManager;
    }

    @Transactional
    public void changeNormally(Long id, long newBalance) {
        Account account = accounts.findById(id).orElseThrow();
        account.setBalance(newBalance);
        // Dirty checking; JPA sẽ flush khi cần, thường trước commit.
    }

    @Transactional
    public void changeWithFlush(Long id, long newBalance) {
        Account account = accounts.findById(id).orElseThrow();
        account.setBalance(newBalance);
        entityManager.flush(); // SQL có thể đã chạy, vẫn chưa commit.
        // Nếu không có lỗi, proxy sẽ hoàn tất transaction sau khi method trả về.
    }

    @Transactional
    public void changeWithFlushThenFail(Long id, long newBalance) {
        Account account = accounts.findById(id).orElseThrow();
        account.setBalance(newBalance);
        entityManager.flush();

        throw new IllegalStateException("Lỗi sau flush");
        // RuntimeException khiến Spring rollback theo cấu hình mặc định.
    }

    @Transactional
    public void saveAndFlushThenFail(Account account) {
        accounts.saveAndFlush(account);
        throw new IllegalStateException("Lỗi sau saveAndFlush");
    }
}
```

**Phân tích với bản ghi ban đầu `accounts(id=1, balance=100)`:**

| Lệnh gọi qua Spring bean proxy | Sau khi lời gọi kết thúc | Giải thích |
| --- | --- | --- |
| `service.changeNormally(1L, 200L)` | Bình thường: balance = 200 | Transaction được commit thành công, dù không gọi flush thủ công |
| `service.changeWithFlush(1L, 200L)` | Bình thường: balance = 200 | Flush sớm; commit vẫn do transaction manager quyết định |
| `service.changeWithFlushThenFail(1L, 200L)` | Balance vẫn là 100, nếu rollback thành công | SQL đã flush nhưng RuntimeException khiến transaction rollback |
| `service.saveAndFlushThenFail(new Account(1L, 200L))` | Với entity hợp lệ và rollback thành công: bản ghi vẫn giữ giá trị trước transaction | `saveAndFlush` không thay thế commit; thực tế có thể `merge` đối tượng có ID |

Kết quả giả định không xảy ra lỗi DB ngoài lỗi được nêu. Khi thử lần lượt các case, **khôi phục dữ liệu gốc trước mỗi case** để chúng độc lập; case cuối dùng một object có ID trùng bản ghi sẵn có để minh họa `merge`, không cần thiết cho quy trình cập nhật managed entity.

Không gọi `changeWithFlushThenFail` từ một phương thức khác của **chính `AccountService`** rồi kỳ vọng proxy transaction áp dụng độc lập: self-invocation thông thường bỏ qua proxy. Hãy gọi từ bean khác hoặc phép thử tích hợp thật sự qua Spring container.

## 6. Cơ chế `save()`, `saveAndFlush()`, `flush()` và `@Transactional`

| API / thao tác | Ý nghĩa thực tế | Hiểu nhầm cần tránh |
| --- | --- | --- |
| `account.setBalance(...)` trên managed entity | Đổi trạng thái được JPA theo dõi, có thể dirty-check | “Setter chắc chắn gửi UPDATE ngay” |
| `entityManager.persist(newEntity)` | Đưa entity mới vào trạng thái managed; lịch SQL tùy provider/ID strategy | “persist luôn INSERT ngay” |
| `repository.save(entity)` | Spring Data JPA dùng `persist` cho entity mới hoặc `merge` cho entity không được nhận diện là mới | “save = commit” |
| `entityManager.flush()` | Đồng bộ các thay đổi pending của Persistence Context với DB trong transaction | “flush = commit” |
| `repository.flush()` | Yêu cầu JPA flush thay đổi đang chờ | “Chỉ flush entity của repository này” |
| `repository.saveAndFlush(entity)` | Save rồi yêu cầu flush ngay | “Đã chắc chắn commit, không rollback được” |
| Kết thúc transaction và `commit` thành công | Xác nhận các thao tác DB thuộc transaction | “Bắt buộc phải gọi flush thủ công trước” |

**Điểm tinh tế về transaction boundary:** Nếu không có `@Transactional` ở service, phương thức `save()` hoặc `saveAndFlush()` của Spring Data repository thường có transaction riêng và có thể **commit trước khi trả về**. Khi service có transaction bao ngoài, các lệnh repository thường **tham gia transaction đó**; lúc `saveAndFlush()` trả về, transaction bao ngoài vẫn chưa commit. Hai cách gọi có thể tạo ra quan sát khác nhau dù tên API giống nhau.

Ví dụ khung giao dịch:

```java
@Transactional
public void updateTwoAccounts(Long firstId, Long secondId) {
    Account first = accounts.findById(firstId).orElseThrow();
    Account second = accounts.findById(secondId).orElseThrow();

    first.setBalance(150L);
    accounts.flush();         // Có thể đồng bộ thay đổi của first.
    second.setBalance(250L);  // Tiếp tục đổi entity trong cùng transaction.

    // Nếu transaction rollback, cả hai thay đổi thuộc transaction đều bị hủy.
}
```

Gọi `flush()` ở giữa không chia phương thức thành hai transaction và không biến thao tác thứ nhất thành một lần commit riêng. Nếu muốn hai transaction độc lập, phải thiết kế ranh giới transaction/propagation tương ứng; đó là một quyết định nghiệp vụ riêng, không phải mục đích của flush.

## 7. Khi nào flush tự xảy ra?

JPA quy định cơ chế đồng bộ theo flush mode; Hibernate triển khai các tình huống cụ thể:

- **`FlushModeType.AUTO` (mặc định)**: provider bảo đảm thay đổi liên quan được xét đến khi thực hiện query có thể chịu ảnh hưởng, và đồng bộ trước khi transaction commit. Hibernate thường flush trước những JPQL/HQL query có liên quan tới các thay đổi đang chờ; quy tắc native SQL và API có thể khác.
- **`FlushModeType.COMMIT`**: chủ yếu trì hoãn đồng bộ đến commit; đừng dựa vào việc query trong transaction trước commit sẽ luôn có cùng kết quả như `AUTO`.
- **Flush thủ công**: `entityManager.flush()` chủ động yêu cầu đồng bộ ngay.
- **Hibernate-specific modes** như `MANUAL` không nên đánh đồng với các giá trị chuẩn của Jakarta Persistence; chúng cần hiểu rõ cấu hình và hệ quả.

Các trường hợp sau có thể làm SQL chạy trước `flush()` thủ công:

1. Query yêu cầu trạng thái mới theo quy tắc flush mode.
2. Provider phải INSERT sớm để lấy ID với một số chiến lược tạo khóa, điển hình `IDENTITY`.
3. Ứng dụng gọi repository method có flush, hoặc một đường đi khác buộc đồng bộ.

Vì vậy không dùng số lượng lệnh gọi `save()` hoặc sự xuất hiện của ID để suy ra commit; hãy kiểm tra **SQL thực tế, transaction boundary và thời điểm commit**.

## 8. Quan sát bằng hai kết nối SQL độc lập

Ví dụ PostgreSQL dưới đây minh họa **transaction isolation**. Lệnh `UPDATE` trong phiên A tương ứng với ý tưởng “SQL đã tới DB” sau flush của JPA. Cần hai kết nối/database sessions độc lập; mỗi block chạy trong phiên chỉ định.

**Khởi tạo (một lần; transaction init tự commit):**

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL
);

INSERT INTO accounts(id, balance)
VALUES (1, 100)
ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance;
```

**Phiên A — mở transaction và ghi nhưng chưa commit:**

```sql
BEGIN;
UPDATE accounts SET balance = 200 WHERE id = 1;
SELECT balance FROM accounts WHERE id = 1;
-- Kết quả trong phiên A: 200
```

**Phiên B — một kết nối khác, mức READ COMMITTED (mặc định PostgreSQL):**

```sql
SELECT balance FROM accounts WHERE id = 1;
-- Kết quả: 100, vì phiên A chưa commit.
```

**Phiên A — rollback:**

```sql
ROLLBACK;
```

**Phiên B — truy vấn lại:**

```sql
SELECT balance FROM accounts WHERE id = 1;
-- Kết quả: 100. UPDATE trong transaction A đã được hoàn tác.
```

Nếu thay `ROLLBACK` bằng `COMMIT` ở phiên A, một truy vấn mới của phiên B trong `READ COMMITTED` thông thường sẽ đọc `200`. Nếu phiên B đang dùng transaction lâu dài ở `REPEATABLE READ`, snapshot của phiên đó có thể tiếp tục thấy phiên bản cũ cho tới khi kết thúc; không nên diễn giải “commit xong là mọi reader tức thì thấy cùng giá trị” mà bỏ qua isolation.

SQL minh họa ở đây không có API JPA `flush()`: với JDBC/SQL trực tiếp, `UPDATE` đã được gửi đi, nhưng vẫn chưa cam kết khi chưa `COMMIT`.

## 9. Những tình huống dễ nhầm trong ứng dụng thực tế

### 9.1. Đọc lại trong cùng transaction

Sau khi sửa một managed entity, `entityManager.find()` với cùng ID thường trả về entity đang managed từ Persistence Context; giá trị mới có thể được đọc **ngay cả khi chưa flush**. Tương tự, query trong transaction có thể kích hoạt auto-flush. Do đó “chính tôi đọc thấy giá trị mới” **không chứng minh commit đã xảy ra**.

### 9.2. Đọc từ một transaction khác

Với database transaction có isolation thông dụng như `READ COMMITTED`, connection khác chưa thấy các cập nhật chưa commit, kể cả khi flush đã gửi SQL. Hành vi cụ thể còn phụ thuộc DB, isolation, loại câu query và snapshot. `READ UNCOMMITTED`, nếu DB hỗ trợ dirty read thực sự, có thể khác.

### 9.3. Flush thành công nhưng commit thất bại

Lỗi ràng buộc trì hoãn, deadlock, lỗi kết nối, transaction bị đánh dấu rollback-only hoặc xung đột tại thời điểm commit vẫn có thể khiến toàn transaction thất bại. Không trả về thông điệp “thanh toán đã hoàn tất” chỉ vì `saveAndFlush()` không ném exception.

### 9.4. Trì hoãn flush khiến lỗi xuất hiện muộn

`repository.save()` có thể trả về bình thường, rồi exception SQL xuất hiện khi flush tự động hoặc lúc commit. Gọi `flush()` có chủ đích trước khi thực hiện bước tiếp theo **có thể phát hiện sớm một số lỗi**, nhưng không bảo đảm bắt được mọi lỗi commit. Sau một lỗi persistence/flush, thông thường cần rollback transaction hiện tại; không nên tự giả định Persistence Context còn ở trạng thái an toàn để tiếp tục.

### 9.5. Gửi email, phát event hoặc gọi API bên ngoài trước commit

Database có thể rollback nhưng email/API bên ngoài không tự rollback theo. Nếu tác vụ chỉ được làm sau khi DB commit thành công, cân nhắc transaction-bound event (`@TransactionalEventListener(phase = AFTER_COMMIT)`) hoặc transactional outbox để bảo đảm quy trình phát tin phù hợp với yêu cầu hệ thống. **Flush không tạo bảo đảm cho side effect bên ngoài.**

### 9.6. JDBC không có dirty checking của JPA

Với `JdbcTemplate` hoặc JDBC trực tiếp, `executeUpdate()` thường gửi SQL ngay; transaction của connection quyết định commit/rollback. Với JDBC batch, `executeBatch()` là lúc gửi nhóm lệnh cần thực thi. Đây không phải cùng khái niệm với `EntityManager.flush()` của JPA. Các phương thức `flush()` của I/O stream, `Writer` hoặc file cũng không phải transaction commit của database.

### 9.7. `@Transactional(readOnly = true)`

Đây là gợi ý/configuration tối ưu cho tác vụ đọc và có thể ảnh hưởng chế độ flush trong Hibernate tùy Spring/provider; không nên trông đợi một thao tác sửa entity rồi flush/commit bình thường trong phương thức read-only. Đồng thời, `readOnly` **không phải một cơ chế phân quyền hay bảo đảm tuyệt đối rằng DB sẽ từ chối mọi câu ghi**.

## 10. Khi nào nên gọi flush chủ động?

**Thông thường không cần:** một service `@Transactional` chỉ đọc/sửa entity và hoàn tất bình thường. Cứ để provider đồng bộ theo flush mode và transaction manager commit.

**Có thể cần:** khi cần phát hiện sớm một lỗi DB trước một bước nghiệp vụ tiếp theo; khi muốn SQL trước đó được DB xử lý trước một truy vấn phụ thuộc; hoặc khi kiểm soát kích thước batch trong tác vụ nhập dữ liệu lớn (thường kết hợp `flush` và `clear` theo lô, với hiểu biết về trạng thái detached).

**Tránh lạm dụng:** `flush()` cho từng bản ghi có thể làm tăng round-trip, lock duration và giảm lợi ích JDBC batching. `flush()` không tăng tính chắc chắn của commit; nó chỉ thay đổi **thời điểm đồng bộ**.

Các câu hỏi cần tự trả lời trước khi gọi flush:

1. Tôi có đang trong đúng transaction không?
2. Thao tác trước đó đang thay đổi **managed**, **new** hay **detached** entity?
3. Tôi cần SQL được gửi sớm, hay tôi thực sự cần **commit** để hệ thống khác nhìn thấy dữ liệu?
4. Lỗi nào có thể xuất hiện tại flush, lỗi nào vẫn phải đợi commit?
5. Nếu bước sau thất bại, tôi có muốn **toàn transaction rollback** không?

## 11. Kiểm tra hiểu đúng qua bốn nhận định

- **“Gọi `save()` là DB đã commit.” — Sai như một quy tắc chung.** Trong transaction ngoài, save thường chỉ tham gia transaction đó. Không có transaction ngoài, repository có thể tạo/commit transaction của riêng nó.
- **“Flush rồi thì rollback không còn tác dụng.” — Sai.** Flush vẫn thuộc transaction chưa commit; database rollback những thay đổi chưa commit.
- **“Không gọi flush thủ công thì không có SQL nào chạy.” — Sai.** Provider có thể tự flush hoặc phát SQL sớm vì query, chiến lược ID hay thao tác khác.
- **“Commit thành công nghĩa là database xác nhận giao dịch; nếu muốn kiểm soát side effect ngoài DB thì cần thiết kế riêng.” — Đúng.** Commit có ý nghĩa đối với tài nguyên nằm trong transaction; không tự xác nhận email, HTTP call, cache ngoài hoặc bản sao DB đã đồng bộ tức thì.

**Ghi nhớ cuối bài:** **set/managed state** trả lời “ứng dụng đang giữ thay đổi gì”; **flush** trả lời “ORM đã đồng bộ những thay đổi nào thành SQL trong transaction”; **commit** trả lời “database có chấp nhận transaction thành công hay chưa”. Luôn xác định **transaction owner**, **flush mode** và **isolation** trước khi kết luận một thao tác đã “lưu xong”.

## Tài liệu đối chiếu

- Jakarta Persistence, `EntityManager` và `flush()`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html
- Jakarta Persistence 3.2, đồng bộ Persistence Context với DB: https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html
- Hibernate ORM User Guide, *Flushing*: https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html
- Spring Data JPA, `JpaRepository.flush()` và `saveAndFlush()`: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
- Spring Data JPA, *Persisting Entities*: https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html
- Spring Framework, transaction proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, cấu hình `@Transactional` và quy tắc rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
