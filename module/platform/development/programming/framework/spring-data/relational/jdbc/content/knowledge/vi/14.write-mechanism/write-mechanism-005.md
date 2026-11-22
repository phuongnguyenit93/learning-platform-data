# Phân biệt save với merge và dirty checking của JPA

## 1. Vì sao cùng là “lưu” nhưng hành vi khác nhau?

Khi làm việc với dữ liệu quan hệ, ta thường gặp ba từ: `save`, `merge` và `dirty checking`. Chúng đều liên quan tới việc đưa thay đổi từ Java xuống database, nhưng **không phải ba tên gọi khác nhau cho cùng một thao tác**.

- Trong **Spring Data JDBC**, `repository.save(entity)` là lời gọi persistence tường minh. Framework xác định entity mới hay đã tồn tại, rồi thực hiện insert hoặc update cho aggregate.
- Trong **JPA**, `EntityManager.persist(entity)` đưa một entity mới vào trạng thái managed; `EntityManager.merge(entity)` sao chép trạng thái của entity truyền vào sang một instance managed.
- **Dirty checking của JPA** theo dõi thay đổi của entity đang managed trong persistence context. Khi flush, provider đồng bộ những thay đổi đó xuống database; vì thế nhiều trường hợp không cần gọi `save` sau mỗi lần sửa field.

Đây là một khác biệt nền tảng khi học Spring Data Relational JDBC hoặc chuyển một ứng dụng từ Spring Data JPA sang Spring Data JDBC. Nếu mang kỳ vọng “đã tải entity trong transaction thì sửa field là tự lưu” từ Hibernate/JPA sang JDBC, thay đổi có thể chỉ nằm trong bộ nhớ và không bao giờ được ghi xuống database.

Bài này làm rõ vòng đời entity, cách các API hoạt động, thời điểm SQL được thực thi, tác động của transaction và những tình huống dễ gây mất dữ liệu khi dùng sai mô hình.

## 2. Bốn khái niệm cần tách biệt

### 2.1. Save — yêu cầu repository lưu trạng thái

`save` là tên phương thức phổ biến trong Spring Data repository:

```java
repository.save(entity);
```

Nó là một **API ở tầng repository**. Ý nghĩa cụ thể phụ thuộc module Spring Data:

- Spring Data JDBC: lưu aggregate bằng cơ chế persistence của JDBC.
- Spring Data JPA: `SimpleJpaRepository.save` kiểm tra entity mới hay cũ rồi gọi `EntityManager.persist` hoặc `EntityManager.merge`.

Vì vậy, không thể chỉ nhìn thấy chữ `save` rồi kết luận rằng nó luôn gọi JPA merge, hoặc luôn tạo một câu SQL `INSERT`.

### 2.2. Persist — đưa entity mới vào persistence context của JPA

`EntityManager.persist(entity)` dùng cho entity mới. Sau khi gọi, entity trở thành managed trong persistence context hiện tại. Provider sẽ ghi entity khi flush theo quy tắc của JPA và chiến lược ID/database.

`persist` không có nghĩa “cập nhật bản ghi đã tồn tại”. Nếu truyền một entity có định danh trùng với một entity đang tồn tại, kết quả phụ thuộc trạng thái và ràng buộc; không dùng `persist` như API update.

### 2.3. Merge — sao chép trạng thái vào entity managed

`EntityManager.merge(entity)` lấy trạng thái của object được truyền vào và hợp nhất trạng thái đó vào một instance managed. Instance truyền vào không vì gọi `merge` mà tự trở thành managed.

Điểm rất quan trọng: **phải dùng object được trả về bởi `merge`**:

```java
Account managed = entityManager.merge(detachedAccount);
```

`managed` là instance managed trong persistence context. `detachedAccount` ban đầu vẫn là object detached.

### 2.4. Dirty checking — phát hiện thay đổi của entity managed

Dirty checking là cơ chế của JPA provider theo dõi trạng thái entity managed trong persistence context. Khi một thuộc tính thay đổi, provider phát hiện sự khác biệt so với trạng thái đã đọc/được theo dõi và tạo SQL khi flush.

```java
Account account = entityManager.find(Account.class, id);
account.rename("Lan Nguyen");

// Không cần gọi entityManager.merge(account)
// Không cần gọi repository.save(account) trong trường hợp managed này.
```

Nếu `account` vẫn managed trong transaction, thay đổi có thể được ghi khi transaction flush/commit.

Dirty checking **không hoạt động với mọi object Java**. Nó chỉ áp dụng cho entity đang managed trong persistence context. Một object được tạo bằng `new` hoặc đã detached không tự được JPA theo dõi.

## 3. So sánh nhanh Spring Data JDBC và JPA

| Tiêu chí | Spring Data JDBC | JPA/Hibernate |
| --- | --- | --- |
| Mô hình theo dõi entity | Không có persistence context/identity map kiểu JPA | Có persistence context quản lý entity |
| Sửa object vừa tải | Phải gọi `repository.save(...)` hoặc lệnh ghi tường minh | Entity managed được dirty checking khi flush |
| Ý nghĩa `save` | Yêu cầu lưu aggregate; framework chọn insert/update | Spring Data JPA chọn `persist` hoặc `merge` theo trạng thái mới |
| `merge` | Không phải cơ chế vòng đời của Spring Data JDBC | API JPA để sao chép trạng thái vào instance managed |
| Object trả về | Nên dùng object trả về vì ID/version hoặc trạng thái persistence có thể thay đổi | Với JPA merge, phải dùng instance trả về vì đó là instance managed |
| Transaction | Bao quanh các câu SQL JDBC; không tạo dirty checking | Quản lý persistence context và flush; dirty checking diễn ra trong context |
| Quan hệ/collection | Tập trung vào aggregate và ownership | ORM quản lý entity association, cascade, fetch, persistence context |
| Lưu entity con | Có thể đồng bộ lại các entity con thuộc aggregate khi save root | Tùy trạng thái managed, cascade, owning side và mapping |

Điểm mấu chốt: **Spring Data JDBC dùng lệnh save để yêu cầu ghi; JPA có thể ghi thay đổi của entity managed mà không cần một lệnh save mới.**

## 4. Spring Data JDBC: save là thao tác ghi tường minh

Giả sử có bảng `accounts` và một aggregate `Account`.

### 4.1. Model và repository

Ví dụ Java 21:

```java
package com.example.accounts;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("accounts")
public record Account(
        @Id Long id,
        String owner,
        BigDecimal balance
) {
    public Account rename(String newOwner) {
        return new Account(id, newOwner, balance);
    }
}
```

Repository:

```java
package com.example.accounts;

import org.springframework.data.repository.CrudRepository;

public interface AccountRepository
        extends CrudRepository<Account, Long> {
}
```

Record được dùng để minh họa object bất biến. Phương thức `rename` tạo instance mới với ID và số dư giữ nguyên.

### 4.2. Sửa object rồi save

```java
package com.example.accounts;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final AccountRepository accounts;

    public AccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void rename(Long id, String newOwner) {
        Account current = accounts.findById(id)
                .orElseThrow();

        Account changed = current.rename(newOwner);

        // Đây là thao tác ghi tường minh.
        Account saved = accounts.save(changed);
    }
}
```

Trong Spring Data JDBC:

1. `findById` thực thi truy vấn và dựng một object Java.
2. Không có persistence context theo dõi object vừa đọc.
3. `rename` tạo object mới trong ví dụ record.
4. `accounts.save(changed)` yêu cầu framework ghi aggregate.
5. SQL được thực thi trong transaction hiện tại; transaction chỉ commit khi ranh giới transaction kết thúc thành công.

Nếu bỏ lời gọi save:

```java
@Transactional
public void renameWithoutSave(Long id, String newOwner) {
    Account current = accounts.findById(id)
            .orElseThrow();

    Account changed = current.rename(newOwner);

    // Không có repository.save(changed).
    // Database không được yêu cầu cập nhật owner.
}
```

Database vẫn giữ tên chủ tài khoản cũ. Việc có `@Transactional` không biến Spring Data JDBC thành JPA và không tạo cơ chế dirty checking.

### 4.3. SQL minh họa

Khi ID `null` và entity được nhận diện là mới, save đi theo đường insert:

```sql
INSERT INTO accounts (owner, balance)
VALUES (?, ?);
```

Khi entity đã tồn tại và được nhận diện là cũ, save đi theo đường update:

```sql
UPDATE accounts
SET owner = ?, balance = ?
WHERE id = ?;
```

Đây là hình dạng minh họa; tên cột, thứ tự bind parameter và câu SQL cụ thể phụ thuộc mapping/dialect. Với aggregate có collection con, save root còn có thể phát sinh các câu SQL để đồng bộ phần tử con.

**Save không phải upsert.** Nếu entity được nhận diện là cũ, Spring Data JDBC không mặc nhiên chuyển sang insert khi không tìm thấy hàng. Nếu cần upsert, phải thiết kế rõ câu lệnh/constraint và semantics theo database.

## 5. JPA: entity managed được dirty checking

JPA định nghĩa vòng đời entity với những trạng thái chính:

```text
NEW
  |
  | EntityManager.persist(...)
  v
MANAGED
  |
  | detach / clear / close
  v
DETACHED
  |
  | EntityManager.merge(...)
  v
MANAGED COPY
  |
  | remove(...)
  v
REMOVED
```

Một entity managed gắn với persistence context. Trong một persistence context, JPA provider quản lý identity và trạng thái của entity. Khi thay đổi thuộc tính, dirty checking giúp provider nhận ra thay đổi và đồng bộ xuống database khi flush.

### 5.1. Ví dụ entity JPA

```java
package com.example.jpa;

import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class JpaAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String owner;

    @Column(nullable = false)
    private BigDecimal balance;

    protected JpaAccount() {
    }

    public JpaAccount(String owner, BigDecimal balance) {
        this.owner = owner;
        this.balance = balance;
    }

    public void rename(String newOwner) {
        this.owner = newOwner;
    }

    public Long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}
```

### 5.2. Sửa entity managed mà không gọi save

```java
@Service
public class JpaAccountService {

    private final EntityManager entityManager;

    public JpaAccountService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void rename(Long id, String newOwner) {
        JpaAccount account =
                entityManager.find(JpaAccount.class, id);

        if (account == null) {
            throw new IllegalArgumentException("Account not found");
        }

        account.rename(newOwner);

        // account đang MANAGED.
        // JPA dirty checking sẽ phát hiện owner thay đổi.
        // Không cần gọi merge(account) hay repository.save(account).
    }
}
```

Khi transaction flush/commit, provider phát hiện `owner` thay đổi và đồng bộ xuống database. SQL minh họa:

```sql
UPDATE accounts
SET owner = ?
WHERE id = ?;
```

Một số provider/cấu hình có thể tạo SQL cập nhật khác, ví dụ cập nhật nhiều cột hoặc dùng version trong điều kiện `WHERE`. SQL cụ thể phụ thuộc mapping và chiến lược của provider.

### 5.3. Flush không đồng nghĩa commit

Dirty checking không có nghĩa SQL luôn chạy ngay tại dòng Java vừa sửa field. Provider thường đồng bộ các thay đổi khi:

- Transaction commit và persistence context flush.
- Ứng dụng gọi `EntityManager.flush()` tường minh.
- Provider cần flush trước một truy vấn theo quy tắc flush mode.

`flush` gửi các thay đổi xuống database trong transaction hiện tại. **Commit** mới kết thúc transaction và làm thay đổi được xác nhận theo transaction semantics của database. Nếu transaction rollback, các lệnh SQL đã flush vẫn có thể bị rollback.

## 6. JPA merge: sao chép trạng thái, không “gắn lại” object cũ

Khi một entity rời persistence context, nó trở thành detached. Những thay đổi trên object detached không được dirty checking theo dõi.

```java
JpaAccount detached = ...; // Entity đã được đọc ở transaction trước
detached.rename("Lan Nguyen");

// Thay đổi trên detached chưa được tự động ghi.
```

Muốn hợp nhất trạng thái detached vào persistence context hiện tại, gọi `merge`:

```java
@Transactional
public void updateDetached(JpaAccount detached) {
    JpaAccount managed = entityManager.merge(detached);

    // Tiếp tục làm việc với managed.
    managed.rename("Lan Nguyen");
}
```

`EntityManager.merge(detached)`:

1. Tìm hoặc tạo một instance managed phù hợp trong persistence context.
2. Sao chép trạng thái từ object được truyền vào sang instance managed theo quy tắc JPA và cascade mapping.
3. Trả về instance managed đó.
4. Không làm object detached ban đầu tự trở thành managed.

Sau merge, dirty checking áp dụng với instance managed. Việc SQL chạy lúc nào vẫn tuân theo flush/transaction.

### Phải dùng object trả về từ merge

Không nên viết:

```java
entityManager.merge(detached);
detached.rename("New name"); // detached vẫn không phải instance managed
```

Thay vào đó:

```java
JpaAccount managed = entityManager.merge(detached);
managed.rename("New name");
```

Nếu tiếp tục sửa object detached cũ sau merge, những thay đổi đó không tự động được theo dõi.

### Merge có phải lúc nào cũng SELECT rồi UPDATE?

Không nên gắn một chuỗi SQL cố định cho `merge`. Provider cần hợp nhất trạng thái vào entity managed; nó có thể cần tải trạng thái hiện tại hoặc sử dụng dữ liệu đã có trong persistence context. SQL cụ thể tùy provider, ID strategy, cache, trạng thái entity và mapping. Với entity đã tồn tại, thao tác merge thường dẫn tới việc đồng bộ trạng thái cuối cùng bằng update khi flush, nhưng số câu SELECT/UPDATE không phải hợp đồng cố định của JPA.

## 7. Spring Data JPA save thực hiện persist hay merge?

Đây là điểm thường gây nhầm lẫn vì cả Spring Data JDBC và Spring Data JPA đều có method tên `save`.

Với Spring Data JPA, implementation repository tiêu chuẩn kiểm tra trạng thái mới của entity:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
} else {
    return entityManager.merge(entity);
}
```

Đoạn code trên minh họa logic cốt lõi của `SimpleJpaRepository.save`; không phải code mà ứng dụng cần tự viết. Chiến lược xác định entity mới có thể dùng version, ID hoặc `Persistable.isNew()`.

Do đó:

- Gọi `jpaRepository.save(newEntity)` có thể dẫn tới `persist`.
- Gọi `jpaRepository.save(existingOrDetachedEntity)` thường dẫn tới `merge`.
- Gọi `jpaRepository.save(managedEntity)` cũng có thể đi qua nhánh merge nếu entity không còn được nhận diện là mới; merge một entity đang managed trả về instance managed phù hợp. Việc gọi save trong trường hợp này thường không cần thiết.

Nếu đang dùng Spring Data JDBC, không có nhánh JPA `EntityManager.merge` ở bên dưới. `CrudRepository.save` thực hiện persistence theo mô hình JDBC.

## 8. So sánh một use case qua hai công nghệ

Giả sử cần đổi tên chủ tài khoản có ID 10.

### Spring Data JDBC

```java
@Transactional
public void rename(Long id, String newName) {
    Account current = jdbcAccounts.findById(id).orElseThrow();
    Account changed = current.rename(newName);
    jdbcAccounts.save(changed);
}
```

Luồng:

```text
findById
  -> SELECT và tạo object
rename
  -> tạo object mới
save
  -> UPDATE tường minh
commit
```

### JPA với entity managed

```java
@Transactional
public void rename(Long id, String newName) {
    JpaAccount account = entityManager.find(JpaAccount.class, id);
    account.rename(newName);
    // Không gọi save/merge.
}
```

Luồng:

```text
find
  -> SELECT và đưa entity vào persistence context
rename
  -> thay đổi entity managed
flush
  -> dirty checking phát hiện thay đổi và UPDATE
commit
```

### JPA với object detached

```java
@Transactional
public void rename(JpaAccount detached, String newName) {
    JpaAccount managed = entityManager.merge(detached);
    managed.rename(newName);
}
```

Luồng:

```text
detached entity
  -> merge
  -> copy state vào managed instance
rename managed
  -> dirty checking
flush
  -> SQL nếu cần
commit
```

Ba luồng có thể tạo SQL cuối cùng tương tự, nhưng **cơ chế quản lý trạng thái object hoàn toàn khác nhau**.

## 9. Những rủi ro khi dùng merge với detached object

Merge thường tiện khi nhận lại một entity detached từ tầng khác, nhưng cũng dễ gây lỗi nếu object chỉ chứa một phần dữ liệu.

Giả sử database đang có:

```text
id       = 10
owner    = "Lan"
balance  = 500000
currency = "VND"
```

Client gửi object detached chỉ có:

```text
id       = 10
owner    = "Lan Nguyen"
balance  = null
currency = null
```

Nếu object được merge như thể nó chứa toàn bộ trạng thái entity, các giá trị null có thể được sao chép vào instance managed. Khi flush, ứng dụng có nguy cơ ghi đè dữ liệu đang tồn tại, hoặc gặp lỗi constraint nếu cột không nullable.

Vì vậy:

- Không dùng entity JPA làm request DTO tùy tiện.
- Không merge một object “partial update” mà không xác định rõ semantics của field bị thiếu/null.
- Với PATCH, nên dùng command/DTO biểu diễn rõ field nào được yêu cầu thay đổi, tải entity managed rồi gọi hành vi phù hợp.
- Kiểm tra cascade merge trên association; không để trạng thái của một đồ thị entity bị hợp nhất ngoài ý muốn.
- Sau merge, chỉ tiếp tục thao tác trên instance được trả về.

Ví dụ cập nhật an toàn hơn bằng cách tải entity managed:

```java
@Transactional
public void changeOwner(Long id, String newOwner) {
    JpaAccount account = entityManager.find(JpaAccount.class, id);
    if (account == null) {
        throw new IllegalArgumentException("Account not found");
    }

    account.rename(newOwner);
    // balance và các field khác được giữ nguyên.
}
```

Với Spring Data JDBC, mô hình tương tự là tải aggregate, thay đổi qua hành vi rồi gọi `save`. DTO chỉ chứa field được phép cập nhật giúp service không vô tình ghi đè các thuộc tính không liên quan.

## 10. Aggregate và collection: khác biệt quan trọng của Spring Data JDBC

Spring Data JDBC tập trung vào aggregate root. Khi lưu root đã tồn tại, framework đồng bộ các entity con thuộc aggregate. Với collection con, cơ chế thông thường có thể xóa các hàng con hiện tại rồi insert lại các phần tử theo trạng thái collection mới.

Ví dụ:

```text
PurchaseOrder #42
  lines:
    BOOK-01 x 2
    PEN-02  x 5
```

Nếu chỉ đổi số lượng một dòng rồi gọi `repository.save(order)`, thao tác persistence trên bảng con có thể gồm xóa và chèn lại các dòng được sở hữu. Đây là chiến lược lưu aggregate của Spring Data JDBC, không phải dirty checking từng phần tử kiểu Hibernate.

Trong JPA, nếu `PurchaseOrder` và các `OrderLine` đang managed, thay đổi một thuộc tính trên một child managed có thể được dirty checking phát hiện mà không cần gọi merge toàn bộ aggregate. Tuy nhiên, kết quả còn phụ thuộc owning side, cascade, orphan removal, fetch và cách mapping.

Không nên kết luận JPA luôn chỉ update một dòng hoặc JDBC luôn chậm. Hãy xem SQL thật và đo trên dữ liệu thực tế. Khác biệt quan trọng là mô hình quản lý trạng thái:

- JDBC: aggregate được ghi tường minh qua repository.
- JPA: entity managed được theo dõi trong persistence context.

Nếu một phần tử con cần được sửa thường xuyên, có định danh và vòng đời độc lập, đó là dấu hiệu nên đánh giá lại ranh giới aggregate thay vì cố dùng một collection lớn.

## 11. Transaction không đồng nghĩa dirty checking

Cả Spring Data JDBC và JPA đều có thể dùng `@Transactional` của Spring, nhưng transaction và dirty checking là hai khái niệm khác nhau.

| Thành phần | Trách nhiệm |
| --- | --- |
| Transaction | Xác định phạm vi commit/rollback và tính nguyên tử của thao tác database. |
| Persistence context của JPA | Quản lý các entity managed và identity trong một phạm vi. |
| Dirty checking | Phát hiện thay đổi của entity managed để tạo lệnh ghi khi flush. |
| Repository save của JDBC | Yêu cầu Spring Data JDBC thực hiện thao tác persistence cho aggregate. |

Một phương thức Spring Data JDBC có `@Transactional` nhưng không gọi `save` vẫn không tự ghi thay đổi trong object. Ngược lại, trong JPA, một entity managed có thể được ghi dù phương thức không gọi repository `save`.

### Transaction ở đâu?

Với use case gồm nhiều thao tác:

```java
@Transactional
public void transfer(Long fromId, Long toId, BigDecimal amount) {
    Account from = accounts.findById(fromId).orElseThrow();
    Account to = accounts.findById(toId).orElseThrow();

    // Kiểm tra nghiệp vụ, cập nhật cả hai aggregate.
    Account updatedFrom = from.debit(amount);
    Account updatedTo = to.credit(amount);

    accounts.save(updatedFrom);
    accounts.save(updatedTo);
}
```

Trong Spring Data JDBC, cả hai lời gọi save được thực hiện trong transaction của use case. Nếu một thao tác lỗi và exception làm transaction rollback theo cấu hình, cả hai thay đổi database được rollback.

Trong JPA, nếu hai entity được tải và đang managed, thay đổi cả hai có thể được dirty checking ghi khi flush/commit. Không cần gọi merge cho từng entity managed.

Không nhầm việc “không gọi save” trong JPA với việc “không cần transaction”. Dirty checking và flush vẫn diễn ra trong persistence context/transaction thích hợp.

## 12. Optimistic locking không phải dirty checking

`@Version` có thể được dùng trong cả Spring Data JDBC và JPA để phát hiện cập nhật cạnh tranh, nhưng nó không thay thế cơ chế ghi:

- Dirty checking trả lời: entity managed đã thay đổi thuộc tính nào?
- Optimistic locking trả lời: entity có còn ở version mà transaction đã đọc không?
- Save/merge trả lời: trạng thái nào cần được đồng bộ theo API persistence?

Ví dụ SQL update có version:

```sql
UPDATE accounts
SET owner = ?, version = 4
WHERE id = ? AND version = 3;
```

Nếu một transaction khác đã tăng version lên 4, câu lệnh với điều kiện version 3 không cập nhật được hàng. Framework có thể ném lỗi optimistic locking. Chi tiết SQL và cách tăng version tùy module/provider.

Đừng dùng `@Version` như lý do để bỏ qua `save` trong Spring Data JDBC. Nó bổ sung kiểm soát cạnh tranh cho thao tác ghi; nó không tự theo dõi mọi thay đổi trong object.

## 13. Bảng quyết định: nên gọi API nào?

| Tình huống | Spring Data JDBC | JPA |
| --- | --- | --- |
| Tạo aggregate mới | `repository.save(newAggregate)` | `persist(newEntity)` hoặc `jpaRepository.save(newEntity)` nếu nhận diện new |
| Đọc rồi sửa aggregate | Tải, gọi hành vi, gọi `repository.save(changed)` | Tải entity managed, thay đổi; dirty checking ghi khi flush |
| Sửa object detached | Tải lại và áp dụng command rồi save; không có JPA merge | `merge(detached)`, tiếp tục dùng object trả về; hoặc tải managed rồi áp dụng thay đổi |
| Sửa object mới tạo trong bộ nhớ | Phải gọi save để ghi | `persist` để đưa vào managed; sau đó dirty checking |
| Cần ghi SQL ngay trong transaction | Gọi repository save/SQL tương ứng | Gọi flush khi thật sự cần; commit sẽ flush theo quy tắc |
| Chỉ có `@Transactional` và thay đổi field | Không tự ghi nếu không có thao tác save | Nếu entity managed, dirty checking có thể ghi |
| Có collection con thuộc aggregate | Save root để đồng bộ aggregate; cân nhắc chi phí ghi lại child | Theo dõi association managed, cascade/orphan removal tùy mapping |

## 14. Những nhầm lẫn thường gặp

### Nhầm lẫn 1: “save của Spring Data JDBC gọi merge”

Không đúng. `save` của JDBC là API repository của Spring Data JDBC. Nó không gọi `EntityManager.merge` và không cần JPA persistence context.

### Nhầm lẫn 2: “Có @Transactional thì object tự được lưu”

Không đúng với Spring Data JDBC. Transaction chỉ bao quanh thao tác database; nó không theo dõi field của object. Cần gọi save hoặc câu lệnh ghi.

### Nhầm lẫn 3: “Merge làm object truyền vào trở thành managed”

Không đúng. `merge` sao chép trạng thái vào instance managed và trả về instance đó. Object truyền vào vẫn detached.

### Nhầm lẫn 4: “JPA phải gọi save sau khi sửa entity”

Không cần nếu entity vẫn managed trong persistence context. Dirty checking sẽ đồng bộ thay đổi khi flush. Gọi save/merge lại thường dư thừa trong trường hợp này.

### Nhầm lẫn 5: “Merge luôn phát một câu UPDATE ngay”

Không đúng. Merge là thao tác hợp nhất trạng thái vào persistence context; SQL có thể được thực hiện khi flush. Provider có thể cần truy vấn để tải trạng thái hiện tại và câu SQL cụ thể phụ thuộc nhiều yếu tố.

### Nhầm lẫn 6: “save tự động là upsert”

Không đúng. Save chọn insert/update dựa trên trạng thái entity; nó không mặc nhiên là câu lệnh database upsert. Hàng không tồn tại ở nhánh update không tự biến thành insert.

### Nhầm lẫn 7: “JDBC và JPA đều chỉ ghi những field thay đổi”

Không thể kết luận như vậy. JPA dirty checking xác định thay đổi của entity managed, nhưng SQL cập nhật thực tế tùy provider/cấu hình. Spring Data JDBC lưu aggregate theo persistence strategy của nó, bao gồm việc đồng bộ collection con. Cần quan sát SQL và hiểu mapping.

## 15. Lưu ý khi chuyển từ Spring Data JPA sang Spring Data JDBC

Khi migration, tìm những đoạn code có dạng:

```java
Account account = repository.findById(id).orElseThrow();
account.setOwner(newOwner);
// Không có repository.save(account)
```

Trong JPA, đoạn này có thể hợp lệ nếu entity managed trong transaction. Trong Spring Data JDBC, đoạn code không đủ để yêu cầu database ghi thay đổi.

Hãy rà soát:

1. **Managed entity assumptions:** mọi nơi dựa vào dirty checking phải chuyển thành thao tác save tường minh hoặc SQL cập nhật rõ ràng.
2. **Merge assumptions:** những nơi dùng merge với detached object cần được chuyển thành tải aggregate rồi áp dụng command/hành vi nghiệp vụ phù hợp.
3. **Cascade/fetch assumptions:** `CascadeType.MERGE`, lazy loading và persistence context của JPA không chuyển nguyên xi sang Spring Data JDBC.
4. **Collection updates:** đánh giá chi phí đồng bộ lại entity con khi save aggregate.
5. **Entity identity:** không giả định hai lần đọc cùng ID sẽ trả về cùng một object Java như identity map của JPA.
6. **Transaction boundaries:** giữ ranh giới nghiệp vụ đúng và bảo đảm các lời gọi save liên quan cùng tham gia transaction.
7. **Optimistic locking:** thiết kế version và xử lý xung đột riêng, không nhầm với dirty checking.

Một cách chuyển đổi an toàn là viết lại từng use case theo luồng: tải aggregate → gọi hành vi → save aggregate, sau đó kiểm tra SQL và kết quả database.

## 16. Bài tập tự thực hành

**Bài tập 1 — Bỏ save trong Spring Data JDBC.** Tải một record Account, tạo record mới với owner khác nhưng không gọi save. Đọc lại ở một transaction khác và xác nhận dữ liệu không đổi. Sau đó thêm save và so sánh.

**Bài tập 2 — JPA dirty checking.** Dùng EntityManager tìm một JpaAccount trong transaction, đổi owner và không gọi save/merge. Sau commit, đọc lại để quan sát thay đổi đã được ghi.

**Bài tập 3 — JPA detached.** Tải entity trong transaction thứ nhất, để nó detached, sửa field rồi kết thúc. Xác nhận thay đổi chưa được ghi. Trong transaction mới gọi merge, dùng object trả về và kiểm tra database.

**Bài tập 4 — Nhầm object sau merge.** Gọi `merge(detached)` nhưng tiếp tục sửa detached ban đầu. So sánh với việc sửa object managed được trả về. Giải thích vì sao kết quả khác nhau.

**Bài tập 5 — Spring Data JPA save.** Dùng `JpaRepository.save` với entity mới và entity đã tồn tại. Bật SQL log để quan sát nhánh persist/merge; nhớ rằng SQL thực tế có thể được trì hoãn đến flush.

**Bài tập 6 — Collection aggregate.** Trong Spring Data JDBC, tạo một đơn hàng có nhiều dòng, sửa một dòng rồi save root. Quan sát SQL bảng con. So sánh với JPA khi các entity con đang managed.

**Bài tập 7 — Transaction và flush.** Trong JPA, gọi `flush` trước commit rồi chủ động rollback. Quan sát SQL đã được gửi nhưng thay đổi không được commit. Giải thích vì sao flush không phải commit.

## 17. Ghi nhớ

Spring Data JDBC và JPA có cách quản lý trạng thái entity khác nhau. Với Spring Data JDBC, `save` là thao tác ghi tường minh lên aggregate; thay đổi trong object không tự được phát hiện chỉ vì object đã được tải trong `@Transactional`. Với JPA, entity managed nằm trong persistence context và dirty checking có thể ghi các thay đổi khi flush mà không cần gọi save.

`merge` là API JPA để sao chép trạng thái của object detached vào instance managed; hãy luôn dùng object trả về. Spring Data JPA `save` có thể gọi `persist` hoặc `merge` tùy trạng thái mới của entity, nhưng điều đó không có nghĩa `save` của Spring Data JDBC cũng dùng merge.

Khi đọc hoặc chuyển đổi code, hãy hỏi ba điều: object đang ở trạng thái nào, cơ chế nào phát hiện thay đổi, và thao tác nào thực sự yêu cầu ghi xuống database. Hiểu đúng ba câu hỏi này sẽ tránh được những lỗi phổ biến như sửa object nhưng không lưu, merge nhầm partial entity hoặc gọi save không cần thiết.

### Tài liệu tham khảo

- [Spring Data Relational – Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data JPA – Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [Jakarta Persistence – EntityManager API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Hibernate ORM – Persistence Context and Dirty Checking](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
