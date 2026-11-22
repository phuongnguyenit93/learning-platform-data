# Phối hợp `flush` và `clear` quanh truy vấn thay đổi trong JPA

Khi làm việc với cơ sở dữ liệu quan hệ qua JPA, chúng ta thường sửa entity bằng cách gọi setter rồi để JPA tự phát sinh câu lệnh SQL khi đồng bộ persistence context. Tuy nhiên, **truy vấn thay đổi hàng loạt** (bulk `UPDATE`/`DELETE` bằng JPQL, Criteria API hoặc native SQL) đi thẳng tới dữ liệu trong cơ sở dữ liệu và **không cập nhật trạng thái các entity đang được quản lý trong persistence context**. Nếu phối hợp không đúng, ứng dụng có thể gửi SQL theo thứ tự không mong muốn, đọc dữ liệu cũ hoặc làm mất những thay đổi còn nằm trong bộ nhớ.

Quy trình thường dùng khi một transaction vừa sửa entity thông thường vừa chạy truy vấn thay đổi là:

```text
Entity managed có thay đổi chưa đồng bộ
                |
                v
       EntityManager.flush()
    Đẩy thay đổi đang chờ thành SQL
                |
                v
     JPQL UPDATE / DELETE
      Thay đổi trực tiếp trong DB
                |
                v
       EntityManager.clear()
      Detach toàn bộ entity cũ
                |
                v
   find()/query để lấy trạng thái mới
                |
                v
       Commit hoặc rollback
```

Đây là **một mẫu an toàn có điều kiện**, không phải quy tắc bắt buộc cho mọi truy vấn: cần quyết định `flush` và `clear` dựa trên việc có thay đổi đang chờ hay không, và liệu transaction còn dùng các entity đã nạp sau bulk DML hay không.

## 1. Vì sao bulk UPDATE/DELETE gây lệch trạng thái?

Persistence context là phạm vi JPA theo dõi các entity ở trạng thái **managed**. Trong cùng một persistence context, khi gọi `find(Account.class, 1L)` nhiều lần, JPA thường trả về cùng một đối tượng đang managed; dirty checking so sánh các thuộc tính để đồng bộ thay đổi xuống cơ sở dữ liệu.

Xét tình huống:

```java
Account account = em.find(Account.class, 1L); // active = true

int affected = em.createQuery("""
    UPDATE Account a
       SET a.active = false
     WHERE a.id = :id
    """)
    .setParameter("id", 1L)
    .executeUpdate();

System.out.println(account.isActive()); // vẫn có thể là true
Account again = em.find(Account.class, 1L);
System.out.println(again.isActive());   // có thể vẫn là true
```

Giả sử `affected` cho biết truy vấn đã thay đổi bản ghi trong DB, đối tượng `account` **không được tự động sửa thành `active = false`**. Lần `find` tiếp theo trong cùng persistence context có thể trả lại chính đối tượng cũ. Điều này khác với cập nhật entity thông qua setter và dirty checking.

Một số đặc điểm quan trọng của bulk DML:

- Truy vấn áp dụng trực tiếp vào những bản ghi thỏa điều kiện, thay vì duyệt từng entity managed để gọi setter.
- Persistence context có thể chứa trạng thái cũ hoặc thậm chí còn tham chiếu entity đã bị bulk `DELETE`.
- Việc tăng `@Version`, kiểm tra optimistic locking cho từng entity, JPA lifecycle callback như `@PreUpdate`/`@PreRemove` và JPA cascade không tự động hoạt động theo cách của `save`/`remove` trên từng entity. Ràng buộc, trigger và cascade khai báo **ở cơ sở dữ liệu** vẫn có thể áp dụng.
- `executeUpdate()` cung cấp số lượng phần tử bị tác động theo kết quả của provider; đây không phải cơ chế đồng bộ các object đang managed.

Vì vậy cần xử lý hai chiều khác nhau: **trước bulk DML**, bảo đảm các sửa đổi đang chờ đã được ghi thành SQL nếu chúng phải có hiệu lực trước truy vấn; **sau bulk DML**, bảo đảm ứng dụng không tiếp tục tin vào trạng thái entity cũ.

## 2. Phân biệt `flush()`, `clear()` và `commit`

| Thao tác | Tác động chính | Điều không xảy ra |
|---|---|---|
| `em.flush()` | Đồng bộ các thay đổi đang chờ của persistence context thành lệnh SQL trong transaction hiện tại | Không kết thúc transaction; không tự làm mới entity bị thay đổi bởi bulk DML |
| `em.clear()` | Detach **tất cả** entity đang managed khỏi persistence context; các lần tải sau có thể tạo entity managed mới | Không tự ghi các thay đổi chưa flush; không rollback những SQL đã flush |
| `em.refresh(entity)` | Đọc lại trạng thái cơ sở dữ liệu cho **một entity còn managed**, ghi đè trạng thái trong bộ nhớ của entity đó | Không xóa toàn bộ persistence context |
| `commit` | Kết thúc transaction thành công; thường bao gồm việc flush những thay đổi cần thiết | Không thay thế việc xử lý entity cũ nếu vẫn đọc chúng trước khi transaction kết thúc |
| `rollback` | Hủy các thay đổi thuộc transaction ở cấp cơ sở dữ liệu | Không có nghĩa các object Java đang giữ tự quay về trạng thái trước đó |

Ví dụ, `flush()` có thể đã phát sinh `UPDATE accounts ...`, nhưng transaction vẫn chưa commit và vẫn có thể rollback. Ngược lại, `clear()` loại bỏ dữ liệu chưa đồng bộ **trong bộ nhớ**; nếu trước đó không flush, thay đổi có thể bị mất khỏi quá trình dirty checking.

**Cần có transaction cho bulk UPDATE/DELETE và cho việc flush persistence context thông thường.** Trong ứng dụng Spring, đặt ranh giới transaction ở service bằng `@Transactional` giúp toàn bộ trình tự chạy trong cùng một transaction.

## 3. Vì sao nên flush **trước** truy vấn thay đổi?

Giả sử entity `Account` đã managed và có sửa đổi chưa ghi:

```java
Account account = em.find(Account.class, accountId);
account.setReviewedAt(Instant.now()); // thay đổi mới nằm trong persistence context
```

Nếu lệnh bulk tiếp theo dựa vào `reviewedAt`, hoặc thao tác trên cùng bản ghi, dữ liệu nằm trong bộ nhớ có thể chưa xuất hiện trong cơ sở dữ liệu ở thời điểm bulk SQL được chạy. `flush()` chủ động đồng bộ chúng trước:

```java
em.flush(); // gửi SQL cho các thay đổi trước đó

int affected = em.createQuery("""
    UPDATE Account a
       SET a.active = false
     WHERE a.active = true
       AND a.lastLoginAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Nếu đổi thứ tự thành `executeUpdate() → flush()`, một entity cũ còn dirty có thể được đồng bộ **sau** bulk update. Tùy provider, kiểu cập nhật cột và mapping, SQL này có thể ghi đè một phần kết quả bulk DML hoặc khiến trạng thái cuối cùng khác ý định nghiệp vụ.

### Flush tự động có đủ không?

JPA cung cấp hai lựa chọn flush mode thường gặp:

- `FlushModeType.AUTO`: provider chịu trách nhiệm bảo đảm những thay đổi có thể ảnh hưởng đến kết quả truy vấn được nhìn thấy theo quy định của JPA. Hibernate có thể tự flush trước các truy vấn liên quan, nhưng thời điểm thực tế phụ thuộc truy vấn, mapping và cách chạy.
- `FlushModeType.COMMIT`: việc thay đổi chưa flush ảnh hưởng thế nào đến truy vấn trước commit không được quy định chặt như chế độ `AUTO`.

Không nên dựa vào một lần auto-flush ngầm nếu thứ tự **“đồng bộ sửa đổi entity trước rồi mới bulk UPDATE/DELETE”** là yêu cầu nghiệp vụ rõ ràng. Gọi `flush()` làm thứ tự này tường minh và tránh phụ thuộc vào tình huống provider có tự flush hay không.

Ngoài ra, `flush()` có thể phát hiện sớm lỗi ràng buộc DB, lỗi optimistic locking hoặc lỗi SQL của các sửa đổi đang chờ. Nếu flush thất bại, transaction cần được xử lý theo cơ chế rollback thay vì tiếp tục bulk update.

## 4. Vì sao cần clear **sau** truy vấn thay đổi?

Sau khi bulk SQL chạy, JPA không đi qua từng entity managed để cập nhật thuộc tính tương ứng. `clear()` loại bỏ các bản thể managed cũ, khiến thao tác `find()`/query tiếp theo có thể tải lại dữ liệu từ DB:

```java
Account account = em.find(Account.class, accountId);

em.createQuery("""
    UPDATE Account a SET a.active = false WHERE a.id = :id
    """)
    .setParameter("id", accountId)
    .executeUpdate();

// account vẫn là object Java cũ, không tự đổi thuộc tính active.
em.clear();

Account refreshed = em.find(Account.class, accountId);
// refreshed là entity managed mới, đọc trạng thái sau UPDATE.
```

Lưu ý: **`clear()` detach toàn bộ entity, không chỉ những entity thuộc bảng vừa UPDATE**. Biến `account` vẫn tham chiếu object cũ nhưng object đó đã detached; sửa thuộc tính của nó sau `clear()` sẽ không được JPA tự lưu. Những collection lazy chưa được tải cũng có thể không dùng được như trước sau khi tách khỏi persistence context.

Nếu chỉ cần đồng bộ **một entity** và muốn giữ các entity khác ở trạng thái managed, có thể cân nhắc `em.refresh(entity)` sau khi flush những thay đổi cần giữ. `refresh` ghi đè trạng thái của đối tượng đó bằng dữ liệu được tải lại; nó không thích hợp để gọi bừa khi đối tượng còn sửa đổi chưa flush.

## 5. Ví dụ hoàn chỉnh với `EntityManager`

Giả sử hệ thống có entity `Account` với các thuộc tính `id`, `active`, `lastLoginAt` và `reviewedAt`. Khi nhân viên kiểm tra một tài khoản, hệ thống muốn ghi nhận thời điểm kiểm tra rồi vô hiệu hóa tài khoản nếu quá lâu không đăng nhập.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;

@Service
public class AccountMaintenanceService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public boolean deactivateIfDormant(Long accountId, Instant cutoff) {
        Account managed = em.find(Account.class, accountId);
        if (managed == null) {
            return false;
        }

        // (1) Sửa entity theo dirty checking thông thường.
        managed.setReviewedAt(Instant.now());

        // (2) Ghi sửa đổi đang chờ trước khi chạy bulk SQL.
        em.flush();

        // (3) Bulk UPDATE tác động trực tiếp vào cơ sở dữ liệu.
        int affected = em.createQuery("""
                UPDATE Account a
                   SET a.active = false
                 WHERE a.id = :id
                   AND a.active = true
                   AND a.lastLoginAt < :cutoff
                """)
            .setParameter("id", accountId)
            .setParameter("cutoff", cutoff)
            .executeUpdate();

        // (4) Bỏ các entity managed có thể còn trạng thái cũ.
        em.clear();

        // (5) Đọc lại sau bulk UPDATE trong cùng transaction.
        Account reloaded = em.find(Account.class, accountId);
        return affected > 0 && reloaded != null && !reloaded.isActive();
    }
}
```

Tại bước (2), giá trị `reviewedAt` được đồng bộ trước. Bước (3) thực hiện truy vấn JPQL thay đổi tài khoản thỏa điều kiện. Sau bước (3), biến `managed` có thể vẫn trả về `true` khi gọi `isActive()` vì dữ liệu trong object không được bulk SQL cập nhật. Bước (4) làm object đó detached, còn bước (5) lấy entity mới với giá trị `active` đã lưu trong DB theo góc nhìn transaction hiện tại.

Phương thức đang chạy trong một transaction: nếu xảy ra lỗi và transaction bị rollback, cả phần ghi `reviewedAt` lẫn bulk update đều được rollback theo transaction. `flush` ở bước (2) không phải là commit độc lập.

Trong ứng dụng thực tế, nếu phải trả kết quả ra ngoài transaction, DTO thường giúp biểu diễn rõ những dữ liệu cần trả và tránh vô tình dùng lại entity detached.

## 6. Cách làm tương đương trong Spring Data JPA

Với repository khai báo `@Query` để thực hiện bulk DML, Spring Data JPA có `@Modifying`. Hai thuộc tính sau điều khiển chính xác hai thao tác đang xét:

| Thuộc tính | Giá trị mặc định | Khi bật `true` |
|---|---|---|
| `flushAutomatically` | `false` | Gọi flush persistence context trước khi thực thi truy vấn thay đổi |
| `clearAutomatically` | `false` | Gọi clear persistence context sau khi thực thi truy vấn thay đổi |

```java
import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository extends JpaRepository<Account, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        UPDATE Account a
           SET a.active = false
         WHERE a.active = true
           AND a.lastLoginAt < :cutoff
        """)
    int deactivateDormant(@Param("cutoff") Instant cutoff);
}
```

Gọi repository từ service có transaction:

```java
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountBatchService {
    private final AccountRepository repository;

    public AccountBatchService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateDormantAccounts(Instant cutoff) {
        return repository.deactivateDormant(cutoff);
    }
}
```

Về thứ tự, phương thức repository tương ứng với:

```java
em.flush();             // flushAutomatically = true
query.executeUpdate();  // truy vấn @Modifying
em.clear();             // clearAutomatically = true
```

**`@Modifying` không tự tạo transaction**: `@Transactional` vẫn phải được cấu hình ở nơi phù hợp. `@Modifying` ở đây phục vụ một modifying query được khai báo qua `@Query`; nó không cần thiết cho các thao tác CRUD thông thường của repository.

Khi bật cả hai cờ, cần hiểu rằng **mọi entity đang managed của cùng persistence context** được flush rồi detach, kể cả các entity không liên quan trực tiếp đến câu `UPDATE`. Vì vậy, nên gọi bulk DML tại một đoạn xử lý có ranh giới transaction và kế hoạch sử dụng entity rõ ràng.

## 7. Chọn thứ tự phù hợp với từng tình huống

| Tình huống | Cách xử lý đề xuất | Lý do |
|---|---|---|
| Có entity dirty và bulk DML cần nhìn thấy thay đổi đó | `flush → bulk DML` | Bảo đảm thay đổi cần thiết được gửi thành SQL trước truy vấn |
| Sau bulk DML sẽ `find`/query lại các entity bị ảnh hưởng | `bulk DML → clear → load lại` | Tránh tái sử dụng trạng thái managed cũ |
| Vừa có thay đổi pending vừa cần dùng lại dữ liệu mới | `flush → bulk DML → clear → load lại` | Xử lý cả thứ tự ghi và tình trạng stale entity |
| Bulk DML chạy ở cuối transaction, không còn sử dụng entity bị ảnh hưởng | Có thể không cần `clear` ngay | Không có bước đọc lại trong cùng persistence context |
| Chỉ một entity cần cập nhật lại trạng thái; cần giữ những entity khác | `flush` nếu cần, bulk DML, rồi `refresh(entity)` | Giới hạn phạm vi đồng bộ trong bộ nhớ |
| Không có entity đang dirty trong persistence context | `flush` tường minh có thể không cần | Không có thay đổi chờ cần đẩy xuống DB |
| Bulk `DELETE` rồi truy cập lại entity đã xóa | `clear` trước khi tải lại/kiểm tra sự tồn tại | Tránh gặp entity managed đã không còn bản ghi trong DB |

Bảng này giả định thao tác nằm trong một transaction thích hợp. Với native SQL, cơ chế tự flush và đồng bộ cache có thể phụ thuộc provider; càng cần kiểm soát rõ thời điểm đồng bộ và cơ chế cache.

## 8. Những lỗi thường gặp

### 8.1. Clear trước khi flush: mất thay đổi chưa đồng bộ

```java
Account account = em.find(Account.class, accountId);
account.setReviewedAt(Instant.now()); // chưa flush

em.clear(); // account trở thành detached; thay đổi pending có thể bị bỏ
```

Về phía JPA, giá trị mới của `reviewedAt` không còn là dirty state của entity managed. Nếu muốn giữ, hãy flush trước khi clear hoặc tổ chức lại luồng xử lý để lưu thay đổi qua entity managed hợp lệ.

### 8.2. Chỉ flush sau bulk: có thể đảo thứ tự ghi dữ liệu

```java
Account account = em.find(Account.class, accountId);
account.setActive(true); // dirty state

em.createQuery("UPDATE Account a SET a.active = false WHERE a.id = :id")
  .setParameter("id", accountId)
  .executeUpdate();

em.flush(); // thay đổi dirty từ account có thể ghi sau bulk SQL
```

Nếu `account` vẫn managed, kết quả cuối có thể không tương ứng với ý định “deactivate”. Thời điểm flush phụ thuộc flush mode/provider nên đoạn mã này còn khó dự đoán. Nếu bulk update phải diễn ra **sau** những chỉnh sửa trên entity, hãy chủ động flush trước bulk.

### 8.3. Clear rồi tiếp tục sửa biến entity cũ

```java
Account old = em.find(Account.class, accountId);
em.flush();
em.createQuery("UPDATE Account a SET a.active = false WHERE a.id = :id")
  .setParameter("id", accountId)
  .executeUpdate();
em.clear();

old.setReviewedAt(Instant.now()); // old đã detached, không tự được lưu
Account current = em.find(Account.class, accountId); // entity managed mới
current.setReviewedAt(Instant.now()); // JPA theo dõi thay đổi này
```

Không nên gọi `merge(old)` một cách máy móc sau bulk update: dữ liệu cũ của `old` có thể ghi đè trạng thái mới nếu mapping và thao tác merge cho phép. Hãy tải lại, xác định trường cần thay đổi và cập nhật trên entity managed mới.

### 8.4. Coi flush như commit hoặc coi clear như rollback

`flush` chỉ đồng bộ trong transaction, nên một rollback sau đó vẫn có thể hủy các SQL đã gửi. `clear` chỉ thay đổi trạng thái quản lý object trong ứng dụng; nó không hoàn tác SQL đã thực thi. Vì vậy, lỗi trong bulk DML phải được xử lý thông qua transaction, không bằng cách gọi `clear()`.

### 8.5. Quên rằng bulk DML bỏ qua cơ chế của từng entity

Bulk `UPDATE`/`DELETE` không tự chạy quy trình thay đổi/xóa cho từng entity theo cách entity lifecycle thường làm. Nếu nghiệp vụ dựa vào callback, entity listener, JPA cascade hoặc kiểm tra `@Version` mặc định, cần cân nhắc:

- Cập nhật/xóa từng entity khi cần lifecycle và cascade của JPA;
- Hoặc triển khai rõ việc kiểm tra version, ghi audit và ràng buộc cần thiết ở tầng phù hợp khi chọn bulk DML.

Ví dụ, với trường version số, một bulk update đòi hỏi optimistic locking có thể phải thêm điều kiện `WHERE a.version = :expectedVersion` và tự quản lý việc tăng version theo mapping/provider; chỉ dùng `@Version` trên entity **không tự khiến mọi bulk update kiểm tra version**.

### 8.6. Quên tầng cache khác

`em.clear()` làm rỗng **first-level cache/persistence context**, không đồng nghĩa với xóa mọi mục trong second-level cache hoặc query cache. Với native SQL, trigger DB, thao tác qua ứng dụng khác hoặc cấu hình cache đặc thù, cần kiểm tra cơ chế vô hiệu hóa cache của provider. Trong trường hợp phải xóa cache entity cấp hai một cách chủ động, JPA có API:

```java
em.getEntityManagerFactory().getCache().evict(Account.class);
```

Lệnh này có phạm vi khác `clear()` và không nên được dùng thường xuyên nếu provider đã đồng bộ cache đúng theo cơ chế của nó.

## 9. Cân nhắc về hiệu năng và ranh giới transaction

Bulk DML có lợi thế lớn khi xử lý nhiều bản ghi bằng một hoặc ít câu lệnh SQL. Tuy vậy, `flush` có thể kích hoạt toàn bộ dirty checking và gửi thêm SQL, còn `clear` khiến các đối tượng phải được nạp lại nếu dùng tiếp. Đừng gọi hai thao tác này ở mọi bước chỉ theo thói quen.

Ví dụ một tác vụ cập nhật hàng loạt độc lập, không giữ entity managed và kết thúc transaction ngay sau khi `executeUpdate()`, thường không cần clear tường minh. Ngược lại, trong một transaction dài đang thao tác nhiều entity, việc clear toàn bộ có thể vô hiệu hóa các tham chiếu mà phần còn lại của service tưởng vẫn managed. Đó là lý do nên đặt bulk DML tại ranh giới xử lý hợp lý, chia thành transaction riêng khi cần và ghi rõ đối tượng nào phải tải lại sau đó.

Đối với job xử lý nhiều đợt (batch), mô hình `flush → clear` cũng được sử dụng định kỳ để giới hạn số entity managed; nhưng đó là mục tiêu tối ưu bộ nhớ khi xử lý theo entity, khác với nhu cầu **clear sau bulk query để tránh dữ liệu cũ**. Hai trường hợp có thể dùng cùng API nhưng phải hiểu nguyên nhân và thời điểm.

## 10. Ghi nhớ qua một kịch bản

Giả sử một transaction:

1. Nạp `Account#42` và đổi `reviewedAt` để lưu lịch sử kiểm tra.
2. Thực hiện bulk `UPDATE` đặt `active = false` cho những tài khoản quá hạn.
3. Đọc lại `Account#42` để hiển thị kết quả ngay.

Nếu bỏ `flush` trước (2), cập nhật `reviewedAt` có thể chưa được gửi khi bulk chạy. Nếu bỏ `clear` sau (2), bước (3) có thể nhận lại `Account#42` cũ đang managed với `active = true`. Nếu gọi `clear` mà quên lưu `reviewedAt`, phần ghi nhận lịch sử có thể mất.

Khi có đủ ba nhu cầu đó, thứ tự dễ hiểu nhất là:

```java
em.flush();                  // Hoàn tất các sửa đổi trước bulk ở mức SQL
int count = query.executeUpdate(); // UPDATE/DELETE trực tiếp trong DB
em.clear();                  // Bỏ entity managed cũ
Account fresh = em.find(Account.class, accountId); // Tải lại khi cần
```

**Nguyên tắc thiết kế:** `flush` giải quyết thứ tự đồng bộ **trước** truy vấn thay đổi; `clear` giải quyết trạng thái entity trong bộ nhớ **sau** truy vấn thay đổi. Cả hai làm việc bên trong ranh giới transaction và không thay thế commit/rollback.
