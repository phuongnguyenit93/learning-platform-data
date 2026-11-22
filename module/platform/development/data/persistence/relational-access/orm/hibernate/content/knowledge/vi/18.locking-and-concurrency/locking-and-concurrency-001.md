# Mất cập nhật, đọc dữ liệu cũ và điều kiện tranh chấp

Khi nhiều request cùng truy cập một database, việc mỗi request chạy trong transaction **không tự bảo đảm dữ liệu luôn đúng**. Hai transaction có thể cùng đọc một giá trị rồi cùng ghi lại dựa trên giá trị cũ; một `EntityManager` có thể tiếp tục trả một entity đã tải trước đó dù transaction khác vừa commit; hoặc hai request đều kiểm tra “chưa có bản ghi” và sau đó cùng tạo bản ghi mới.

Đây là những biểu hiện phổ biến của **concurrency anomalies** trong Hibernate/Jakarta Persistence:

- **Mất cập nhật (*lost update*):** một kết quả ghi bị ghi đè bởi kết quả khác.
- **Đọc dữ liệu cũ (*stale read*):** quyết định được đưa ra từ trạng thái không còn phản ánh dữ liệu mới nhất hoặc phiên bản hợp lệ cần dùng.
- **Điều kiện tranh chấp (*race condition*):** kết quả phụ thuộc thứ tự đan xen các thao tác của nhiều transaction/thread, nhất là chuỗi *kiểm tra rồi thực hiện* (*check-then-act*, TOCTOU).

Hibernate cung cấp `@Version`, optimistic/pessimistic locking, persistence context và các API flush/refresh/lock. Database cung cấp isolation, row lock, constraint, atomic SQL và cơ chế concurrency control. **Không công cụ đơn lẻ nào sửa mọi cuộc tranh chấp.** Cần biết invariant nghiệp vụ, các hàng đang cạnh tranh, ranh giới transaction và đường ghi thực sự.

Bài học sử dụng ví dụ kho hàng (`InventoryItem`) và đặt chỗ/giữ tên duy nhất để giải thích rõ cơ chế, hướng xử lý và cách kiểm thử.

## 1. Tình huống nền tảng: hai request cùng trừ tồn kho

Giả sử sản phẩm `SKU-A` có **10 sản phẩm khả dụng**. Hai khách hàng đồng thời yêu cầu mua 1 sản phẩm.

Logic tưởng như hợp lý:

```java
InventoryItem item = em.find(InventoryItem.class, id);

if (item.getAvailable() < 1) {
    throw new OutOfStockException();
}

item.reserve(1);
```

Nếu thực hiện tuần tự:

```text
Ban đầu: 10
Request A đọc 10, trừ 1, ghi 9
Request B đọc 9,  trừ 1, ghi 8

Kết quả đúng: 8
```

Nhưng khi hai transaction cùng đọc trước khi bất kỳ bên nào commit:

```text
Thời điểm        Transaction A                 Transaction B
-----------      ---------------------------   ---------------------------
T0               SELECT available → 10         -
T1               -                             SELECT available → 10
T2               Tính 10 - 1 = 9               -
T3               -                             Tính 10 - 1 = 9
T4               UPDATE available = 9          -
T5               COMMIT                        -
T6               -                             UPDATE available = 9
T7               -                             COMMIT

Kết quả sai: 9, dù đã có hai yêu cầu mua thành công.
```

Đây là **lost update**: hai tác vụ đều tưởng đã trừ hàng, nhưng một phép trừ bị ghi đè. Dữ liệu đúng theo quy tắc nghiệp vụ phải còn **8**, không phải 9.

**Lưu ý về database:** lịch thực thi trên mô tả một trường hợp có thể xảy ra, điển hình dưới `READ COMMITTED` với read–modify–write không có version check. Ở mức isolation hoặc DBMS khác, transaction thứ hai có thể bị chặn hoặc báo lỗi serialization/concurrent update thay vì commit thành công. Không suy rằng mọi database luôn cho phép lịch trên.

## 2. Đọc, tính toán, ghi: vì sao transaction đơn lẻ chưa đủ?

Trong Hibernate, luồng xử lý thường đi qua ba giai đoạn:

```text
READ
  em.find(InventoryItem.class, id)
       ↓
Persistence Context giữ managed entity
       ↓
COMPUTE
  item.reserve(quantity)
       ↓
Dirty checking
       ↓
FLUSH / COMMIT
  UPDATE inventory_items SET available = ? WHERE id = ?
```

Nếu không có cơ chế phát hiện xung đột, SQL có thể chỉ dựa vào primary key:

```sql
UPDATE inventory_items
SET available = 9
WHERE id = 100;
```

Database có thể khóa hàng trong thời gian thực hiện UPDATE, nhưng **khóa riêng lẻ của UPDATE không sửa được quyết định đã tính từ dữ liệu cũ**. Transaction B có thể chờ A kết thúc, rồi vẫn gửi `SET available = 9`.

Cần phân biệt:

- **Atomicity:** một transaction hoặc hoàn tất, hoặc rollback.
- **Isolation:** các giao dịch đồng thời được phép quan sát/tương tác với nhau như thế nào.
- **Ứng dụng tránh lost update:** phải có version check, phù hợp row lock/atomic update, hoặc mức isolation/transaction retry đáp ứng yêu cầu.
- **Ràng buộc nghiệp vụ:** không âm kho, không bán quá số lượng, không cấp hai chỗ cho cùng một người.

`@Transactional` bảo đảm ranh giới giao dịch theo framework; nó **không tự thêm điều kiện `version` vào mọi UPDATE** nếu entity không dùng optimistic versioning, cũng không tự làm toàn bộ check-then-act trở thành atomic.

## 3. Một entity minh họa với `@Version`

Dùng entity `InventoryItem`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.Objects;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 60)
    private String sku;

    @Column(name = "available", nullable = false)
    private int available;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int available) {
        this.sku = Objects.requireNonNull(sku);
        if (available < 0) {
            throw new IllegalArgumentException("available must be >= 0");
        }
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }

    public long getVersion() {
        return version;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        if (available < quantity) {
            throw new IllegalStateException("Not enough stock");
        }
        available -= quantity;
    }
}
```

Một schema minh họa:

```sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    available INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_inventory_available CHECK (available >= 0)
);
```

Các điểm chính:

1. `available` là **trạng thái nghiệp vụ** đang bị tranh chấp.
2. `version` là **số phiên bản** do Hibernate quản lý thông qua `@Version`.
3. `CHECK (available >= 0)` bảo vệ invariant cơ bản ở **database**, kể cả khi ghi ngoài Hibernate.
4. `sku UNIQUE` bảo vệ tính duy nhất của mã sản phẩm.
5. Không có public setter tùy ý cho `version`; ứng dụng không tự tăng version khi sửa entity managed.

Cú pháp `GENERATED BY DEFAULT AS IDENTITY` phù hợp một số DBMS như PostgreSQL; hệ quản trị khác có cú pháp sinh khóa riêng. Các đoạn SQL trong bài là minh họa, cần kiểm tra dialect/DDL thực tế của hệ thống.

### 3.1. Entity không có version sẽ khác thế nào?

Nếu bỏ field `@Version` khỏi mapping và **không bổ sung cơ chế khác** để kiểm tra xung đột, Hibernate thường phát UPDATE theo ID và trạng thái cuối của object. Đó là trường hợp dễ xuất hiện lost update trong nhiều workload.

**Không nên tạo đồng thời hai entity class có mapping trùng bảng chỉ để “bật/tắt version” trong production.** Khi thử nghiệm, dùng hai cấu hình/schema kiểm thử rõ ràng hoặc một dự án mẫu riêng; bài đang so sánh về mặt cơ chế.

## 4. `@Version`: optimistic locking ngăn ghi đè dựa trên bản cũ

Với:

```java
@Version
private long version;
```

Hibernate ghi nhận phiên bản của entity khi load. Giả sử:

```text
inventory_items:
    id        = 100
    available = 10
    version   = 0
```

Hai transaction đều đọc `version=0`. Khi A sửa và flush, câu SQL về ý tưởng là:

```sql
UPDATE inventory_items
SET available = 9, version = 1
WHERE id = 100 AND version = 0;
```

A cập nhật thành công **một hàng**.

B vẫn giữ snapshot cũ `available=10`, `version=0`, muốn ghi `available=9`. Hibernate gửi một UPDATE với điều kiện phiên bản cũ:

```sql
UPDATE inventory_items
SET available = 9, version = 1
WHERE id = 100 AND version = 0;
```

Nhưng database hiện có `version=1` nên **không còn hàng nào phù hợp**. Hibernate phát hiện kết quả cập nhật không như kỳ vọng và báo xung đột optimistic locking.

Dòng thời gian:

```text
T0  DB: available=10, version=0

T1  TX A load (10, v0)           TX B load (10, v0)

T2  A.reserve(1) → 9            B.reserve(1) → 9

T3  A flush:
      UPDATE ... WHERE version=0
      1 row updated
      DB: (9, v1)

T4  A COMMIT

T5  B flush/commit:
      UPDATE ... WHERE version=0
      0 rows updated
      Optimistic locking conflict → B rollback

T6  Ứng dụng xử lý B:
      bắt đầu transaction mới
      load (9, v1)
      reserve(1) → 8
      UPDATE ... WHERE version=1
      COMMIT thành công → DB: (8, v2)
```

**Lợi ích:** tránh việc B âm thầm ghi đè kết quả của A. B phải **xử lý xung đột**, ví dụ retry sau khi đọc lại hoặc báo cho người dùng.

### 4.1. Hibernate báo lỗi lúc nào?

Có thể xảy ra trong:

- `em.flush()`;
- bước flush tự động trước query;
- `tx.commit()`/kết thúc transaction;
- một thao tác locking có kiểm tra version.

Tùy API/framework, lỗi có thể là `jakarta.persistence.OptimisticLockException`, exception Hibernate như `StaleObjectStateException`, hoặc wrapper từ Spring/transaction manager. **Không hardcode giả định mọi xung đột đều ném đúng một loại exception tại cùng một dòng Java.**

### 4.2. Version tăng khi nào?

Với entity **thực sự có update được Hibernate quản lý**, phiên bản thường tăng theo quy tắc optimistic versioning. Chỉ tải entity rồi không sửa thường **không tăng version**. Các thao tác force increment và một số thay đổi association có semantics riêng.

Không tự viết:

```java
item.version++;
```

thay cho `@Version`. Provider phải quản lý điều kiện version khi ghi để bảo vệ dữ liệu khỏi conflict.

## 5. Optimistic locking không khóa hàng ngay từ lúc đọc

Tên “optimistic” thể hiện giả định **tranh chấp không thường xuyên**. Transaction được phép đọc và làm việc trên dữ liệu; xung đột thường chỉ được phát hiện **khi kiểm tra version**.

So sánh:

```text
OPTIMISTIC
  A đọc v0    ────────────────────────── A ghi v1, commit
  B đọc v0    ────────────────────────── B ghi theo v0 → conflict

PESSIMISTIC
  A khóa hàng ─── đọc/sửa ─── commit, nhả khóa
  B yêu cầu khóa ── chờ ───── đọc giá trị mới ─── sửa/commit
```

Optimistic locking phù hợp khi:

- Số người đọc lớn, xung đột ghi tương đối hiếm.
- Transaction ngắn hoặc dữ liệu được tải và sửa trong những bước tách rời.
- Ứng dụng có chính sách retry hoặc báo lỗi conflict.
- Không muốn giữ database lock trong thời gian user đang tương tác.

Nhưng optimistic locking **không đảm bảo một request luôn thành công**. Nếu xung đột nhiều, retry liên tục có thể làm tăng tải và trải nghiệm xấu.

### 5.1. Read-only transaction có cần version check không?

Nếu chỉ:

```java
InventoryItem item = em.find(InventoryItem.class, 100L);
```

và không sửa entity, một `@Version` **không có nghĩa Hibernate tự xác minh tới cuối transaction rằng dữ liệu chưa bị thay đổi**. Nếu quyết định nghiệp vụ phụ thuộc việc bản ghi *không đổi trong suốt transaction*, có thể yêu cầu **optimistic lock rõ ràng**:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    100L,
    jakarta.persistence.LockModeType.OPTIMISTIC
);
```

Với versioned entity, mode này yêu cầu kiểm tra phiên bản theo quy tắc provider/transaction. Nó không đồng nghĩa khóa database như `SELECT FOR UPDATE`.

## 6. Các mode optimistic locking quan trọng

Jakarta Persistence có các lock modes:

| Mode | Ý nghĩa |
| --- | --- |
| `NONE` | Không yêu cầu khóa tường minh |
| `OPTIMISTIC` | Kiểm tra version của entity phù hợp để phát hiện thay đổi xung đột |
| `OPTIMISTIC_FORCE_INCREMENT` | Kiểm tra và **tăng version** ngay cả khi không có thay đổi field bình thường |
| `READ` | Alias lịch sử của `OPTIMISTIC`; nên dùng tên rõ |
| `WRITE` | Alias lịch sử của `OPTIMISTIC_FORCE_INCREMENT` |
| `PESSIMISTIC_READ` | Yêu cầu khóa đọc/shared protection, tùy database |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi/exclusive protection |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa ghi đồng thời tăng version của entity có version |

Ví dụ:

```java
InventoryItem item = em.find(InventoryItem.class, 100L);
em.lock(item, LockModeType.OPTIMISTIC);
```

Hoặc khi cần thông báo rằng **aggregate root đã thay đổi về mặt nghiệp vụ** dù không sửa scalar field của root:

```java
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

Tình huống thứ hai có thể hữu ích khi cập nhật child/association mà muốn root version phản ánh thay đổi và tham gia phát hiện xung đột. Đây là **quyết định thiết kế aggregate**, không phải yêu cầu rằng mọi thay đổi collection luôn cần force increment.

**Không nên trộn alias `LockModeType.READ` của JPA với những mode nội bộ Hibernate có tên gần giống.** Dùng `OPTIMISTIC`/`OPTIMISTIC_FORCE_INCREMENT` để mã rõ nghĩa.

## 7. Đọc dữ liệu cũ: persistence context (L1) là nguyên nhân rất thường gặp

Hibernate `Session`/`EntityManager` dùng **first-level cache (L1)** và identity map.

```java
InventoryItem first = em.find(InventoryItem.class, 100L);
InventoryItem second = em.find(InventoryItem.class, 100L);

System.out.println(first == second); // Thường true trong cùng context.
```

Khi entity đã managed, lần `find()` thứ hai có thể trả **cùng object Java**, không bắt buộc SELECT lại database.

Điều này tối ưu truy cập và giữ identity nhất quán trong một unit of work, nhưng cũng có nghĩa dữ liệu có thể **stale**.

### 7.1. Hai transaction và một context đã giữ state cũ

```text
Thời điểm   EntityManager A             Database              EntityManager B
---------   -------------------------   -------------------   -----------------------
T0          find Item#100 → 10, v0       10, v0                -
T1          vẫn giữ managed instance    10, v0                load 10, v0
T2          -                           9, v1                 sửa và COMMIT
T3          find Item#100 lần nữa       9, v1                 -
            → vẫn cùng object 10, v0
```

**A không đọc mới**, vì `find()` ưu tiên managed entity đang có trong persistence context. Từ góc độ ORM, nó không bị lỗi: việc tái sử dụng managed state là hành vi được thiết kế.

Một getter:

```java
item.getAvailable();
```

chỉ đọc field trong object Java, không phải truy vấn dữ liệu mới nhất từ database.

### 7.2. Vì sao stale read nguy hiểm?

Nếu A dùng `available=10` đã cũ để:

- cho phép tạo order;
- hứa còn hàng;
- quyết định mức giá/giới hạn tín dụng;
- kiểm tra trạng thái đơn “chưa thanh toán”;
- đưa ra thông tin cuối cùng cho khách hàng;

thì quyết định có thể không còn chính xác. **Stale read không nhất thiết gây lost update**, nhưng có thể là điều kiện dẫn tới lost update hoặc vi phạm quy tắc khác nếu không kiểm tra lại trước khi ghi.

## 8. `refresh()`, `clear()`, `detach()` và scope transaction

Nếu cần yêu cầu Hibernate đọc lại state của entity managed:

```java
InventoryItem item = em.find(InventoryItem.class, 100L);

// Trong transaction/persistence context thích hợp:
em.refresh(item);
```

Theo Jakarta Persistence, `refresh()` nạp lại trạng thái từ database và có thể **ghi đè các thay đổi chưa flush** trên entity đó.

Phân biệt:

| API | Tác động | Lưu ý |
| --- | --- | --- |
| `em.find(type, id)` | Có thể trả từ L1 | Không bảo đảm reload |
| `em.refresh(managed)` | Nạp lại state từ DB | Ghi đè thay đổi chưa flush |
| `em.clear()` | Detach mọi entity khỏi context | Thay đổi chưa flush có thể mất |
| `em.detach(entity)` | Detach một entity | Object không còn tự dirty-check |
| `em.close()` | Đóng context application-managed | Object đã tải trở thành detached |
| `em.merge(detached)` | Sao chép state detached vào managed instance | **Không phải** lệnh refresh; có nguy cơ merge state cũ |
| `em.lock(entity, mode)` | Yêu cầu lock/version check theo mode | Tùy mode mà có SQL và phạm vi kiểm tra khác |

Ví dụ:

```java
InventoryItem item = em.find(InventoryItem.class, 100L);
item.reserve(1);

em.refresh(item); // Có thể hủy phép trừ đang chờ chưa flush.
```

Không dùng `refresh()` theo thói quen để “chắc dữ liệu mới” khi đang có thay đổi chưa lưu; phải biết mình muốn **giữ hay bỏ** state Java hiện có.

### 8.1. Refresh không vượt qua database isolation

Nếu transaction đang chạy dưới một cơ chế isolation kiểu snapshot/repeatable read, một `SELECT` mới hoặc `refresh()` **không nhất thiết nhìn thấy commit mới của transaction khác** trong cùng transaction đó.

Do đó:

```text
refresh()       ≠ luôn là dữ liệu mới nhất toàn hệ thống
clear() + find() ≠ tự động vượt mọi transaction snapshot
```

Cần đặt lại câu hỏi về **ranh giới transaction, isolation level và freshness requirement** trước khi chọn API.

## 9. Phân biệt stale read với các hiện tượng isolation

Cùng gọi là “đọc sai dữ liệu”, nhưng có các hiện tượng khác nhau:

| Hiện tượng | Mô tả | Minh họa |
| --- | --- | --- |
| **Stale read do L1** | EntityManager trả state đã managed, không reload DB | A giữ Item v0 dù B đã commit v1 |
| **Dirty read** | Đọc dữ liệu transaction khác **chưa commit** | A thấy giá trị B đang sửa nhưng B sẽ rollback |
| **Non-repeatable read** | Trong một transaction, hai lần đọc cùng hàng bằng SQL thấy giá trị khác | A đọc 10, B commit 9, A đọc lại 9 |
| **Phantom read** | Cùng điều kiện truy vấn, tập hàng kết quả thay đổi do insert/delete | Query số ghế trống trả thêm/bớt row |
| **Read skew** | Đọc các hàng ở những thời điểm không nhất quán | Đọc số dư A trước transfer, B sau transfer |
| **Lost update** | Hai tác vụ cùng ghi dựa trên state cũ, một kết quả ghi bị đè | Hai request cùng tính 10-1 và ghi 9 |
| **Write skew** | Hai transaction cập nhật **hai hàng khác nhau** dựa trên invariant chung | Hai bác sĩ cùng rời ca, mỗi người thấy còn người kia |

**Stale read do L1** không phải cùng khái niệm với **non-repeatable read ở mức database**. Một context có thể giữ object cũ ngay cả khi DB isolation cho phép query mới nhìn thấy commit của transaction khác.

Một JPQL query được thực thi lại có thể gửi SELECT mới, nhưng nếu hàng trả về tương ứng entity đang managed, Hibernate thường **tái sử dụng instance** trong persistence context thay vì tự ghi đè mọi field. Muốn kiểm tra dữ liệu DB, cần chọn cách đọc/mapping/refresh phù hợp.

## 10. Isolation level không phải lời hứa chung ngăn mọi race

Hệ quản trị cơ sở dữ liệu thường hỗ trợ các mức isolation mang tên:

- `READ UNCOMMITTED`
- `READ COMMITTED`
- `REPEATABLE READ`
- `SERIALIZABLE`

Nhưng cách thực hiện **MVCC, snapshot, row lock và xử lý concurrent writers khác nhau giữa DBMS**. Các tên level không đủ để suy ra mọi anomaly bị chặn ở mọi engine.

### 10.1. Bảng định hướng

| Isolation | Điều thường mong đợi | Giới hạn cần kiểm chứng |
| --- | --- | --- |
| READ UNCOMMITTED | Ít hạn chế nhất | Một số DBMS vẫn không cho dirty read vì implementation MVCC |
| READ COMMITTED | Không đọc dữ liệu chưa commit | Read-modify-write không có version check có thể lost update; query tiếp theo có thể thấy snapshot mới |
| REPEATABLE READ | Hạn chế việc cùng transaction đọc lại hàng bị thay đổi | Cơ chế engine có thể bảo vệ concurrent update khác nhau; write skew vẫn là nguy cơ ở một số hệ |
| SERIALIZABLE | Hành vi tương đương một lịch tuần tự hợp lệ | Có thể phải **retry toàn transaction** khi DB báo serialization failure; chi phí/độ tranh chấp tăng |

Không nên kết luận “đặt REPEATABLE READ thì chắc chắn không bao giờ mất cập nhật” hoặc “SERIALIZABLE làm mọi request tự thành công”. Một số database sẽ **hủy một trong hai transaction**, đòi hỏi ứng dụng retry.

### 10.2. Isolation là thuộc tính transaction/database

`@Version` của Hibernate và isolation của database **bổ sung cho nhau**:

- `@Version` kiểm tra thay đổi **cùng entity row** khi Hibernate thực thi update/delete được quản lý.
- Isolation kiểm soát cách các **transaction** tương tác và những lịch thực thi nào được chấp nhận.
- DB constraint bảo vệ những invariant mà một version field không thể bao trùm.
- Business logic quyết định có retry, gộp yêu cầu, từ chối hay cần lock ngay.

## 11. Race condition kiểu “kiểm tra rồi tạo” (TOCTOU)

Giả sử hệ thống yêu cầu **mỗi email chỉ có một tài khoản**:

```java
if (!accountRepository.existsByEmail(email)) {
    accountRepository.save(new Account(email));
}
```

Hai request đồng thời:

```text
T0  Request A: existsByEmail("a@example.org") → false
T1  Request B: existsByEmail("a@example.org") → false
T2  Request A: INSERT account
T3  Request B: INSERT account
```

Nếu database **không có UNIQUE(email)**, có thể xuất hiện **hai hàng trùng email**.

Nếu database có `UNIQUE(email)`, ít nhất một request có thể bị constraint violation. Đó là kết quả **đúng theo mục tiêu toàn vẹn dữ liệu**; code phải xử lý nó như race hợp lệ thay vì cho rằng check ban đầu bảo đảm insert sẽ thành công.

Schema:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(200) NOT NULL,
    CONSTRAINT uq_accounts_email UNIQUE (email)
);
```

Nguyên tắc:

> **`existsBy...()` trước `save()` không phải thao tác atomic.** Constraint ở database là hàng rào bảo vệ tính duy nhất; application check chủ yếu để cải thiện thông báo lỗi khi không có cạnh tranh.

### 11.1. Vì sao `@Version` không giải quyết race tạo hàng mới?

Hai request đang tạo **hai entity mới**, chưa có cùng một persistent row/version để đối chiếu. Optimistic locking trên từng entity mới không thay thế `UNIQUE(email)`.

Khi cần “tạo nếu chưa có” với cạnh tranh cao, cân nhắc **database upsert** (`INSERT ... ON CONFLICT`/`MERGE` tùy DBMS) và semantics được xác nhận, hoặc dùng transaction/locking trên một tài nguyên ổn định. Không suy ra mọi upsert có hành vi giống nhau ở mọi database.

### 11.2. “Đếm rồi thêm” cũng có race

Ví dụ một chương trình chỉ cho phép tối đa 20 người đăng ký:

```java
long count = enrollmentRepository.countByEventId(eventId);

if (count < 20) {
    enrollmentRepository.save(new Enrollment(eventId, userId));
}
```

Hai request có thể cùng thấy `count=19`, rồi cả hai insert, kết quả 21. **Một unique constraint trên `(event_id, user_id)` chỉ ngăn cùng user đăng ký hai lần**, không tự bảo vệ giới hạn tổng số 20.

Muốn giữ capacity invariant, cần một **counter/hàng đại diện event** được cập nhật atomically hoặc khóa, constraint cùng chiến lược transaction/serialization phù hợp, hay cơ chế reservation allocation đã kiểm thử.

## 12. Atomic conditional UPDATE: xử lý kho bằng một câu SQL

Với quy tắc “không được trừ kho xuống âm”, không nhất thiết phải:

```text
SELECT available
→ kiểm tra trong Java
→ UPDATE available = giá trị đã tính
```

Có thể dùng câu SQL **update có điều kiện**, để database thực hiện check và decrement như một thao tác:

```sql
UPDATE inventory_items
SET available = available - :quantity,
    version = version + 1
WHERE id = :id
  AND available >= :quantity;
```

Sau khi execute, đọc **số hàng được cập nhật**:

- `1`: trừ kho thành công.
- `0`: hàng không tồn tại hoặc lượng hàng hiện tại không đáp ứng điều kiện; cần xác định cách báo lỗi nghiệp vụ.

Hai transaction tranh chấp cùng hàng sẽ được database xử lý bằng cơ chế update/lock/concurrency của DBMS. Điều kiện được đánh giá tại lúc thực hiện update theo semantics tương ứng; kết quả không phải hai lần đọc giá trị 10 trong Java rồi mù quáng ghi 9.

### 12.1. Ví dụ native SQL qua EntityManager

```java
public boolean reserveAtomically(
        EntityManager em,
        long itemId,
        int quantity) {

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    int updated = em.createNativeQuery("""
            UPDATE inventory_items
            SET available = available - :quantity,
                version = version + 1
            WHERE id = :id
              AND available >= :quantity
            """)
        .setParameter("quantity", quantity)
        .setParameter("id", itemId)
        .executeUpdate();

    return updated == 1;
}
```

Code phải chạy trong transaction phù hợp. Cột `version` ở đây dùng kiểu nguyên như `BIGINT`; SQL tăng version thủ công để **không vô hiệu hóa** các kiểm tra version của Hibernate ở các luồng dùng managed entity.

**Cảnh báo:** Native/bulk SQL đi ngoài cơ chế dirty checking từng managed entity. Nếu cùng `EntityManager` đã load `InventoryItem` trước đó, object trong L1 có thể **bị cũ** sau câu UPDATE; cần tránh trộn hai đường ghi lên cùng entity trong một transaction, hoặc `refresh()`/`clear()` có chủ đích sau khi xử lý pending changes.

### 12.2. Vì sao cần version increment thủ công trong bulk SQL?

JPQL/native bulk update **không mặc định tăng `@Version` như khi Hibernate flush một entity managed**. Nếu một code path bulk sửa `available` mà không thay version, transaction khác đã load entity cũ có thể ghi đè hoặc không phát hiện conflict qua điều kiện version.

Nếu dùng native conditional update trên bảng có `@Version`, phải thiết kế **tính nhất quán giữa tất cả write paths**. Việc `version = version + 1` ở đây là chủ đích cụ thể cho version kiểu số nguyên; không áp máy móc cho timestamp hoặc custom version type.

### 12.3. Số rows affected không phải toàn bộ kết quả nghiệp vụ

`0` có thể là:

- ID sản phẩm không tồn tại;
- còn ít hơn quantity;
- một cơ chế database/hệ thống từ chối update;
- điều kiện khác được bổ sung sau này.

Nếu API cần thông báo phân biệt, có thể query bổ sung trong transaction để đưa ra lỗi thân thiện, nhưng **không dùng query bổ sung đó làm điều kiện an toàn duy nhất**. Hàng rào chống race vẫn là câu UPDATE/constraint.

## 13. Pessimistic locking: khóa trước khi quyết định

Khi nhiều transaction thường xuyên tranh chấp một hàng, có thể lấy **khóa database ngay lúc đọc**:

```java
import jakarta.persistence.LockModeType;

InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);

item.reserve(quantity);
```

Đoạn code phải chạy trong **transaction đang hoạt động**.

Với một DBMS như PostgreSQL và query phù hợp, SQL có thể có dạng:

```sql
SELECT id, sku, available, version
FROM inventory_items
WHERE id = ?
FOR UPDATE;
```

Row lock được giữ tới khi transaction commit hoặc rollback theo semantics database. Transaction khác yêu cầu khóa ghi trên **cùng hàng** thường phải chờ hoặc thất bại theo timeout/no-wait policy.

### 13.1. Timeline

```text
TX A                                 TX B
----------------------------------   ---------------------------------
BEGIN                                BEGIN
SELECT ... FOR UPDATE Item#100
được khóa, available=10              SELECT ... FOR UPDATE Item#100
reserve(1) → 9                       phải chờ khóa tương thích
UPDATE / COMMIT                      ...
nhả lock                             được tiếp tục, đọc state theo DB
                                     reserve(1) → 8
                                     UPDATE / COMMIT
```

Khi được dùng đúng, pessimistic locking có thể **tuần tự hóa các writer tranh chấp hàng đó** và làm quyết định dựa trên trạng thái được bảo vệ.

Nhưng lưu ý:

- `PESSIMISTIC_WRITE` không bảo đảm **mọi ordinary SELECT ở mọi DBMS đều bị chặn**. Với MVCC, các snapshot reads có thể vẫn chạy và thấy phiên bản phù hợp isolation.
- Lock bảo vệ **những hàng được khóa**, không tự ngăn mọi insert tạo *phantom* hoặc thay đổi ở hàng khác.
- Lock chỉ có ý nghĩa khi **mọi writer liên quan** tuân thủ một protocol tương thích.
- Giữ transaction dài khiến request khác chờ, có thể tăng timeout, deadlock và contention.
- Chỉ khóa sau khi đã đọc và quyết định dựa trên state cũ có thể là **quá muộn**; phải khóa **trước khi kiểm tra invariant**.

### 13.2. Pessimistic READ và WRITE

| Mode | Ý tưởng | Giới hạn |
| --- | --- | --- |
| `PESSIMISTIC_READ` | Shared protection khi DB hỗ trợ | Một số dialect có thể nâng thành khóa mạnh hơn |
| `PESSIMISTIC_WRITE` | Exclusive protection đối với conflicting writers/lockers | Không bảo đảm chặn mọi nonlocking reader |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa pessimistic và tăng version | Chỉ phù hợp versioned entity, có tác động write |

Khi database không thể cấp lock đúng yêu cầu, JPA có thể ném `PessimisticLockException`, `LockTimeoutException` hoặc exception được framework bao bọc. Cần phân biệt **timeout/deadlock có thể retry** với **lỗi logic/constraint không nên retry mù quáng**.

### 13.3. Timeout hint không hoàn toàn portable

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE,
    java.util.Map.of("jakarta.persistence.lock.timeout", 2000)
);
```

Ý định là giới hạn thời gian chờ khóa tính theo mili-giây. Nhưng Jakarta Persistence cảnh báo ứng dụng **không nên phụ thuộc hoàn toàn vào việc timeout hint luôn được tôn trọng**: database, driver và provider có thể khác nhau. Trong ứng dụng thực, cấu hình timeout tại DB/transaction và test hành vi lỗi.

## 14. Optimistic hay pessimistic: chọn theo tần suất tranh chấp

| Tiêu chí | Optimistic (`@Version`) | Pessimistic (`PESSIMISTIC_WRITE`) |
| --- | --- | --- |
| Phương pháp | Cho phép làm việc, kiểm tra xung đột khi ghi | Khóa hàng trước khi sửa/ra quyết định |
| Nguồn bảo vệ | Version check trong SQL UPDATE/DELETE | Locking protocol của database |
| Chi phí khi ít tranh chấp | Thường thấp | Có thêm thao tác/chi phí lock |
| Chi phí khi tranh chấp cao | Nhiều conflict, retry, rollback | Chờ lock, timeout, deadlock |
| Transaction dài | Không giữ row lock từ lúc đọc, nhưng có nguy cơ state cũ | Không nên giữ lock dài |
| Xử lý sau xung đột | Bắt lỗi và quyết định retry/báo conflict | Timeout/deadlock handling, retry khi phù hợp |
| Phạm vi | Thường entity row có version | Hàng được khóa; lock scope có giới hạn |
| Đảm bảo unique giữa hàng mới | Không | Không tự đủ; vẫn cần UNIQUE |
| Đảm bảo giới hạn tổng số dòng | Không tự đủ | Cần khóa row đại diện/serializable/invariant khác |

Một chiến lược thực dụng là:

- Thao tác cập nhật hồ sơ, thay đổi đơn ít tranh chấp: bắt đầu từ **`@Version`**.
- Một counter/hàng “nóng” bị trừ cộng liên tục: cân nhắc **atomic conditional UPDATE** hoặc pessimistic lock.
- Invariant liên quan nhiều hàng: thiết kế **constraint/locking/isolation ở đúng phạm vi**, không chỉ version một entity bất kỳ.
- Nếu người dùng mở form lâu rồi mới bấm lưu: dùng optimistic version check, **không giữ row lock trong suốt thời gian người dùng nhập**.

## 15. Retry phải làm lại *toàn bộ quyết định*, không chỉ gửi lại SQL cũ

Giả sử hai request mua hàng đều đọc 10. Một request bị optimistic conflict.

Cách xử lý sai:

```java
// Cố lặp lại việc ghi available=9 từ state cũ,
// không load lại và không kiểm tra tồn kho.
```

Cách xử lý đúng hơn:

```text
1. Rollback transaction bị lỗi.
2. Đóng/bỏ EntityManager hoặc persistence context đã lỗi.
3. Bắt đầu transaction mới.
4. Load lại item/version mới.
5. Kiểm tra lại quantity và các invariant nghiệp vụ.
6. Tính toán và persist thay đổi.
7. Commit.
8. Dừng sau số lần retry hữu hạn; nếu vẫn conflict, báo lỗi phù hợp.
```

Ví dụ pseudo-service:

```java
public ReservationResult reserveWithRetry(long itemId, int quantity) {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            // Mỗi lần gọi phải bắt đầu transaction/persistence context MỚI.
            return reservationTransactionalService.reserveOnce(
                itemId, quantity
            );
        } catch (OptimisticLockingFailureException ex) {
            if (attempt == 3) {
                throw ex;
            }
            // Có thể backoff+jitter phù hợp trước retry.
        }
    }
    throw new IllegalStateException("Unreachable");
}
```

Đây là **cấu trúc Spring minh họa**. `OptimisticLockingFailureException` thuộc Spring DAO abstraction, không phải exception chuẩn JPA; tên `reservationTransactionalService` đại diện **một bean khác** có method `@Transactional` thực sự. Không đặt `@Transactional` trên một method rồi gọi `this.reserveOnce()` trong cùng class và mặc định proxy Spring sẽ mở transaction mới.

### 15.1. Các điều kiện phải có để retry an toàn

- Retry **toàn transaction**, không tái sử dụng entity/version cũ.
- Không tiếp tục dùng transaction sau `OptimisticLockException`/constraint/deadlock failure; rollback.
- Giới hạn số lần thử và có backoff/jitter nếu phù hợp.
- **Idempotency:** một lần người dùng bấm “Đặt hàng” không được tạo hai order hoặc trừ kho hai lần khi request/commit response bị mất.
- Side effects như gửi email, gọi payment provider hoặc publish message phải được thiết kế **sau commit** hoặc qua outbox/idempotent mechanism; không lặp không kiểm soát trong retry.
- Không retry mọi `UNIQUE` violation: nhiều trường hợp đó là lỗi nghiệp vụ thật như email đã được dùng.

### 15.2. Trả 409 Conflict khi nào?

Với API REST, một optimistic conflict do người dùng sửa phiên bản cũ có thể được biểu diễn bằng **HTTP 409 Conflict** hoặc một chính sách API khác như `412 Precondition Failed` nếu dùng `If-Match`/ETag. Không bắt buộc mọi conflict phải auto-retry: khi người dùng cần xem nội dung thay đổi trước khi quyết định, **báo conflict và yêu cầu tải lại** có thể phù hợp hơn.

## 16. `merge()` một detached entity cũ dễ tạo lost update nếu thiếu version

Trong ứng dụng web:

```text
T0  User A tải Order để chỉnh sửa → DTO/version cũ
T1  User B cập nhật Order và commit
T2  User A gửi bản form cũ
T3  Backend merge detached state của A
```

Nếu entity không có `@Version` hay cơ chế kiểm tra tương đương, `merge()` có thể **ghi đè** những field đã thay đổi bởi B, đặc biệt khi request gửi toàn bộ snapshot object thay vì các trường người dùng thực sự sửa.

Với entity có `@Version`, khi merge một detached instance version cũ, Hibernate có thể phát hiện mismatch ở thời điểm merge hoặc flush và báo conflict. Nhưng vẫn cần kiểm soát:

- DTO có gửi version hay không?
- Có mapping DTO sang entity mới với ID nhưng **không giữ đúng version** không?
- Controller có tự set mọi field, kể cả field người dùng không được quyền sửa?
- Có bulk SQL hoặc một service khác sửa DB mà **không tăng version** không?

### 16.1. Cập nhật bằng patch có chủ đích

Một cách thông dụng:

```java
@Transactional
public void renameCustomer(
        long id,
        String newName,
        long expectedVersion) {

    Customer customer = repository.findById(id)
        .orElseThrow();

    if (customer.getVersion() != expectedVersion) {
        throw new ConflictException("Customer was modified");
    }

    customer.rename(newName);
    // Hibernate @Version sẽ kiểm tra lại khi flush/commit.
}
```

`Customer`, repository và exception là thành phần giả định của ứng dụng. Đây là ví dụ Spring-style; phần **so version ở Java giúp báo lỗi sớm**, còn `@Version` trong UPDATE mới bảo vệ khỏi race phát sinh **sau bước kiểm tra**. Không thay SQL version check bằng một câu `if` đơn thuần.

## 17. Tại sao “đọc lại trước khi ghi” vẫn có thể race?

Một số code cố sửa lost update bằng cách `refresh()` hoặc query lại ngay trước khi commit:

```java
InventoryItem item = em.find(InventoryItem.class, itemId);
em.refresh(item);

if (item.getAvailable() >= quantity) {
    item.reserve(quantity);
}
```

Nếu không có version check, lock hoặc atomic SQL, một transaction khác **vẫn có thể sửa hàng ngay sau `refresh()` và trước UPDATE**.

Timeline:

```text
A refresh → thấy 10
B refresh → thấy 10
A update → 9, commit
B update → 9, commit
```

Vì vậy:

> **Thời gian ngắn giữa check và act không làm chuỗi đó atomic.**

Một cách đọc “mới hơn” không thay cho concurrency control. Muốn bảo vệ thao tác, kiểm tra điều kiện tại **thời điểm ghi** (version/conditional update), hoặc khóa tài nguyên trước khi đọc và ra quyết định.

## 18. Write skew: `@Version` từng hàng vẫn chưa đủ

Giả sử hệ thống ca trực có hai bác sĩ A và B. Quy tắc nghiệp vụ: **ít nhất một bác sĩ phải đang trực**.

Bảng:

```text
doctor_shifts
+-----------+---------+---------+
| doctor_id | on_call | version |
+-----------+---------+---------+
| A         | true    | 0       |
| B         | true    | 0       |
+-----------+---------+---------+
```

Hai transaction đồng thời:

```text
TX 1: thấy A=true, B=true → cho A nghỉ → UPDATE hàng A
TX 2: thấy A=true, B=true → cho B nghỉ → UPDATE hàng B
```

Vì hai transaction cập nhật **hai hàng khác nhau**, mỗi hàng có version riêng và các UPDATE có thể đều thành công:

```text
Kết quả: A=false, B=false
Invariant "ít nhất một người trực" bị phá.
```

Đây là **write skew**. `@Version` trên từng row phát hiện khi **cùng row** bị cập nhật xung đột, nhưng không tự phát hiện một constraint liên quan **nhiều row**.

Giải pháp tùy DB/domain:

- Khóa một **row đại diện cho ca trực** trước khi đọc tập bác sĩ.
- Cập nhật một **aggregate version** chung khi thay đổi membership, có thể dùng `OPTIMISTIC_FORCE_INCREMENT` trên root phù hợp.
- Dùng `SERIALIZABLE` và retry khi database báo serialization failure.
- Thiết kế constraint ở database nếu có thể diễn đạt invariant theo schema.
- Dùng một bảng/counter được cập nhật atomic để bảo vệ invariant.

**Không lấy lock một bác sĩ riêng lẻ rồi kết luận toàn bộ lịch trực đã được khóa.**

## 19. Phantom và race khi thay đổi số lượng thành viên

Một ví dụ khác: chỉ cho phép **tối đa 5 thành viên** trong một nhóm.

```java
long members = em.createQuery(
    "select count(m) from Membership m where m.group.id = :id",
    Long.class
).setParameter("id", groupId).getSingleResult();

if (members < 5) {
    em.persist(new Membership(group, user));
}
```

Cả A và B cùng đếm `4`, rồi cả hai thêm thành viên thành `6`. Hai entity `Membership` mới khác nhau, nên versioning từng membership không phát hiện cùng row conflict.

Một hướng là giữ `memberCount` trong entity `Group` có `@Version`:

```java
Group group = em.find(Group.class, groupId);

if (group.getMemberCount() >= 5) {
    throw new IllegalStateException("Group full");
}

group.incrementMemberCount();
em.persist(new Membership(group, user));
```

Nếu mọi luồng thay đổi membership đều **cập nhật cùng Group row/version** trong transaction, conflict sẽ được phát hiện. Nhưng phải xử lý các đường ghi ngoài ứng dụng, bulk SQL, xóa thành viên, duplicate user và rollback cho nhất quán.

Một phương án khác là khóa `Group` bằng `PESSIMISTIC_WRITE` trước khi đếm và thêm, với điều kiện **mọi writer tuân thủ protocol khóa Group**.

`@Version` **không mặc định khóa tập kết quả của một query đếm**.

## 20. Những trường hợp `@Version` không tự bảo vệ

| Trường hợp | Vì sao version có thể không đủ? |
| --- | --- |
| Hai entity mới cùng email | Chưa có cùng row/version; cần UNIQUE |
| Bulk JPQL/HQL UPDATE | Không mặc định áp version check/increment từng managed entity |
| Native SQL UPDATE | Bỏ qua ORM dirty checking trừ khi tự có điều kiện/version |
| Ghi từ service khác | Service ngoài Hibernate có thể không tăng version |
| Invariant trên nhiều rows | Mỗi row version riêng có thể đều hợp lệ nhưng tổ hợp state sai |
| `@ElementCollection`/association | Version increment của owner phụ thuộc mapping/ownership và thao tác |
| Chỉ đọc mà không sửa | `@Version` không mặc nhiên xác minh mọi read khi transaction kết thúc |
| Dữ liệu được cache lâu ngoài session | DTO/Redis/HTTP cache không tự được refresh chỉ vì có `@Version` |
| Long-running business workflow | Giữa các transaction, dữ liệu có thể đổi; cần version/ETag/revalidation |

Vì vậy, dùng `@Version` là nền tảng tốt cho entity update nhưng không nên mô tả nó là **chốt khóa toàn hệ thống**.

### 20.1. Hibernate versionless optimistic locking

Hibernate hỗ trợ một số cấu hình đặc thù như `@OptimisticLocking(type = OptimisticLockType.ALL)` hoặc `DIRTY` cho những mapping cũ không có cột version. Hibernate có thể so các giá trị column cũ trong điều kiện UPDATE để phát hiện xung đột.

Các cơ chế này có giới hạn với detached state, mapping mutable, nullable columns, `@DynamicUpdate` và cách ORM theo dõi snapshot. Chúng **không portable theo Jakarta Persistence** và phức tạp hơn một cột `@Version` rõ ràng.

Với schema cho phép thêm version, **ưu tiên `@Version`** trước khi chọn versionless strategy, trừ khi có lý do thiết kế hoặc migration cụ thể.

## 21. Lỗi optimistic lock và lỗi constraint là hai nhóm khác nhau

Một số loại lỗi dễ bị nhầm:

| Lỗi | Thường có nghĩa | Xử lý |
| --- | --- | --- |
| `OptimisticLockException` | Entity/version đã đổi hoặc row không còn phù hợp | Rollback; đọc lại và retry/409 có điều kiện |
| `StaleObjectStateException` (Hibernate) | Provider phát hiện state/version stale | Thường được bao bởi JPA/Spring exception |
| `PessimisticLockException` | Không lấy được lock và transaction bị ảnh hưởng | Rollback, đánh giá retry |
| `LockTimeoutException` | Timeout lock theo semantics provider/DB | Xử lý timeout, kiểm tra trạng thái transaction |
| SQL unique constraint violation | Hai thao tác muốn dùng cùng key hoặc dữ liệu trùng | Dựa vào invariant; thường báo trùng, không retry mù |
| FK constraint violation | Tham chiếu parent/child không hợp lệ tại thời điểm SQL | Sửa lifecycle/order/schema, không che bằng retry vô hạn |
| Serialization failure/deadlock | DB hủy transaction để bảo vệ concurrency | Retry nguyên transaction có giới hạn nếu an toàn |

**Không bắt mọi `RuntimeException` rồi retry**. Một lỗi mapping, null constraint hoặc dữ liệu sai sẽ chỉ được lặp đi lặp lại và làm tăng tải.

### 21.1. Rollback sau lỗi ở flush/commit

Khi Hibernate/JPA báo lỗi concurrency hoặc SQL trong flush/commit, transaction thường phải rollback. Persistence context có thể không còn phù hợp để tiếp tục thao tác. Với transaction resource-local, rollback và đóng `EntityManager`; với Spring, để transaction manager rollback và gọi lại method ở **transaction mới** nếu có retry hợp lệ.

## 22. Spring `@Transactional` và scope persistence context

Trong Spring Boot/Spring Data JPA, service thường viết:

```java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(long itemId, int quantity) {
        InventoryItem item = repository.findById(itemId)
            .orElseThrow();

        item.reserve(quantity);
        // Dirty checking + @Version khi flush/commit.
    }
}
```

Đoạn này giả định đã có `InventoryRepository` cho `InventoryItem`, cùng các import `@Service`, `@Transactional` và framework cấu hình phù hợp. Khi Hibernate flush/commit, versioned update bảo vệ khỏi silent lost update.

Nhưng **đừng hiểu**:

```java
@Transactional
```

là yêu cầu database luôn chạy ở `SERIALIZABLE`, luôn `SELECT FOR UPDATE`, hay tự động retry optimistic exception. Isolation mặc định thường kế thừa cấu hình transaction/database. Muốn đặt isolation riêng:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
```

là tùy chọn Spring, và vẫn phải xử lý lỗi serialization/retry. Mức isolation cao hơn có thể ảnh hưởng throughput; không dùng như lựa chọn mặc định cho mọi endpoint chỉ vì chưa xác định invariant.

### 22.1. Cùng một EntityManager không dùng cho hai thread

`EntityManager`/Hibernate stateful `Session` không được thiết kế để chia sẻ tùy tiện giữa các thread. **Kiểm thử race** phải tạo **hai persistence contexts/transactions độc lập**, không chạy hai thread cùng sửa một managed instance rồi gọi đó là “database concurrency test”.

Hai request độc lập trong server thông thường sẽ có unit-of-work scopes tương ứng. Nếu ứng dụng giữ `EntityManager` quá lâu, stale state trong L1 còn có thể kéo dài ngoài một transaction tùy configuration.

## 23. Kiểm thử lost update bằng hai EntityManager

Muốn tái hiện deterministic kịch bản stale write, không cần ngay lập tức dùng thread. Có thể mở hai `EntityManager` riêng, cho cả hai **load trước khi bên nào cập nhật**, rồi commit tuần tự.

### 23.1. Kịch bản sử dụng `@Version`

Giả sử test fixture đã seed `InventoryItem#100`:

```text
available = 10
version   = 0
```

Test với JUnit 5, sử dụng `EntityManagerFactory emf` đã cấu hình:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

@Test
void staleWriterFailsInsteadOfOverwriting() {
    EntityManager emA = emf.createEntityManager();
    EntityManager emB = emf.createEntityManager();

    EntityTransaction txA = emA.getTransaction();
    EntityTransaction txB = emB.getTransaction();

    try {
        txA.begin();
        txB.begin();

        InventoryItem a = emA.find(InventoryItem.class, 100L);
        InventoryItem b = emB.find(InventoryItem.class, 100L);

        assertNotNull(a);
        assertNotNull(b);
        assertEquals(10, a.getAvailable());
        assertEquals(10, b.getAvailable());

        a.reserve(1);
        emA.flush();
        txA.commit();

        b.reserve(1);

        // Loại wrapper exception và thời điểm throw phụ thuộc provider;
        // test thực nên kiểm tra exception chain/root cause.
        assertThrows(RuntimeException.class, emB::flush);

        if (txB.isActive()) {
            txB.rollback();
        }
    } finally {
        if (txA.isActive()) txA.rollback();
        if (txB.isActive()) txB.rollback();
        emA.close();
        emB.close();
    }
}
```

Đây là **test body minh họa**, không gồm cấu hình `emf`, seed/cleanup. Test trên PostgreSQL hoặc DBMS có transaction snapshot khác nhau có thể quan sát error class khác; với một số isolation, transaction B bị DB từ chối bằng serialization error trước khi Hibernate có thể kết luận version mismatch.

Điểm cần kiểm tra:

1. `emA` và `emB` là **hai contexts**.
2. A và B đều load **trước** khi A commit.
3. A cập nhật thành công và đổi version.
4. B không được âm thầm ghi đè trạng thái A.
5. Sau lỗi phải rollback transaction B.
6. Sau khi đọc lại trong transaction mới, available phải phản ánh đúng lần cập nhật đã thành công.

### 23.2. Không khẳng định test là tranh chấp đồng thời thật ở mọi DB

Ví dụ trên tạo **stale writer** có chủ đích trong hai transaction; nó kiểm tra version-based conflict mà không cần hai thread chạy cùng thời điểm. Một DBMS ở `REPEATABLE READ` có thể báo serialization conflict theo cách riêng. Để thử chờ lock/deadlock/cạnh tranh thời gian thực, cần test khác với hai thread và latch.

### 23.3. Test không có version

Với một mapping/schema **không có optimistic locking**, cùng kịch bản dưới `READ COMMITTED` có thể dẫn đến:

```text
A UPDATE available=9, COMMIT
B UPDATE available=9, COMMIT
Final available=9
```

Đây là kết quả lost update cần minh họa. Nhưng không hardcode kỳ vọng này trên mọi DBMS/isolation; có engine sẽ từ chối transaction B. Tốt hơn là **quan sát SQL và trạng thái cuối** trong môi trường test được chọn.

## 24. Kiểm thử race thật bằng nhiều transaction và latch

Khi cần tạo cạnh tranh giữa hai luồng, sử dụng `CountDownLatch` hoặc `CyclicBarrier` để kiểm soát thời điểm hai transaction đọc/ghi.

Pseudo-test:

```java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowWrite = new CountDownLatch(1);

Runnable worker = () -> {
    // MỖI worker tạo EntityManager và transaction RIÊNG.
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        InventoryItem item = em.find(InventoryItem.class, itemId);

        bothRead.countDown();
        if (!allowWrite.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out");
        }

        item.reserve(1);
        tx.commit(); // Có thể thành công hoặc báo conflict.
    } catch (Exception ex) {
        if (tx.isActive()) tx.rollback();
        // Ghi lại exception vào result holder của test.
    } finally {
        em.close();
    }
};

// Submit 2 worker tới ExecutorService;
// test thread chờ bothRead.await(...), sau đó allowWrite.countDown();
```

Đây là **mã phác thảo**, phải khai báo/import `emf`, `itemId`, `ExecutorService`, latch, timeout, result holder và lifecycle cleanup trong test thực. Không dùng `Thread.sleep()` để “đoán” thứ tự thực thi: dễ tạo flaky tests.

Một kiểm thử tốt phải có:

- Timeout hữu hạn để không treo CI.
- Latch bảo đảm **cả hai đã đọc** trước khi cùng viết.
- Hai `EntityManager` và hai transaction riêng.
- Ghi lại outcome của cả hai transactions.
- Kiểm tra tổng số lần thành công và số tồn kho cuối.
- Cleanup test data sau khi rollback/commit.
- Kịch bản riêng cho `@Version`, atomic SQL và pessimistic lock.
- Database test tương đồng production (ví dụ Testcontainers), vì H2 và PostgreSQL có thể khác behavior lock/isolation.

### 24.1. Pessimistic locking có thể cần test cách khác

Nếu cả hai worker lấy `PESSIMISTIC_WRITE` **ngay khi đọc**, latch “đợi cả hai đọc xong mới cho ghi” có thể gây deadlock logic ngay trong test: worker thứ hai chưa được lock/read vì worker thứ nhất vẫn giữ khóa và chờ latch.

Với test pessimistic lock, cho A lấy khóa và giữ tới một điểm kiểm soát; cho B bắt đầu yêu cầu khóa; sau đó cho A commit; kiểm tra B chỉ tiếp tục **sau khi A nhả lock**. Không dùng cùng một barrier thiết kế cho optimistic loading.

## 25. Test đọc cũ và `refresh()`

Kịch bản:

```text
1. EntityManager A load Item#100 → (10, version 0).
2. EntityManager B bắt đầu transaction, reserve(1), commit → (9, version 1).
3. A gọi find(Item#100) lần nữa:
       vẫn có thể trả object (10, version 0) từ L1.
4. A gọi refresh(item):
       yêu cầu đọc DB, nhưng giá trị nhìn thấy phụ thuộc isolation/snapshot.
```

Nếu A không giữ một transaction dài và DB cho phép thấy commit mới, `refresh()` có thể đưa object về `(9, v1)`. Trong một transaction đã mở dưới snapshot isolation, cần kiểm tra semantics của DB trước khi khẳng định nhất định nhận được v1.

Bài test này phải phân biệt:

- **L1 identity:** `assertSame(first, second)` trong một context.
- **Stale state:** `first.getAvailable()` không tự đổi khi B commit.
- **Freshness:** `refresh()`/context mới và isolation phù hợp.
- **Conflict protection:** A sửa state cũ và flush thì `@Version` chặn stale write.

Không biến một thử nghiệm đọc dữ liệu cũ thành chứng minh rằng `refresh()` thay thế locking.

## 26. Đặt invariant tại database khi có thể

Hibernate mapping giúp thao tác với object, nhưng dữ liệu có thể bị ghi qua:

- Native SQL hoặc bulk HQL/JPQL;
- Job chạy trực tiếp JDBC;
- Service khác dùng cùng database;
- Script migration, ETL, data repair;
- Console quản trị.

Vì vậy database phải bảo vệ các điều kiện **có thể biểu diễn bằng constraint**, ví dụ:

```sql
ALTER TABLE inventory_items
ADD CONSTRAINT ck_inventory_available CHECK (available >= 0);
```

```sql
ALTER TABLE accounts
ADD CONSTRAINT uq_accounts_email UNIQUE (email);
```

```sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_order_lines_order
FOREIGN KEY (order_id) REFERENCES purchase_orders(id);
```

Nhưng một `CHECK (available >= 0)` **không đảm bảo không lost update** nếu hai phép trừ đều ghi `9`: giá trị 9 vẫn không âm, chỉ sai về số phép trừ đã được chấp nhận.

Để giữ đúng invariant phải phối hợp **constraint + concurrency control + transaction**. Đừng xem các annotation JPA là thay thế database constraints đã được triển khai.

## 27. Idempotency: tránh double execution khi retry hoặc mất response

Giả sử client gửi lệnh mua 1 sản phẩm, server commit thành công, nhưng mạng ngắt trước khi client nhận response. Client retry:

```text
Request #1 → trừ kho 1 → COMMIT → response bị mất
Request #2 → trừ kho 1 → COMMIT → client nhận success
```

Dù mỗi transaction được khóa đúng, ứng dụng vẫn có thể **trừ hai lần cho một ý định mua hàng**. Đây là vấn đề **idempotency**, khác lost update.

Có thể cấp `idempotencyKey` cho mỗi hành động mua:

```sql
CREATE TABLE reservation_requests (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(100) NOT NULL UNIQUE,
    item_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Trong cùng một transaction có quy trình ghi `request_key` unique và cập nhật stock/booking tương ứng; khi request lặp, hệ thống trả lại outcome đã ghi **thay vì thực hiện hành động lần hai**.

Chỉ `SELECT request_key` rồi quyết định tạo **vẫn race**; unique constraint và transaction phải là nguồn bảo vệ. Nếu side effect đi qua payment/message broker, cần cơ chế idempotency/outbox/deduplication bổ sung phù hợp.

## 28. Một chiến lược cho tổng thể quy trình đặt hàng

Thay vì chỉ thêm `@Version` rồi coi như xong, nên thiết kế từ đầu theo các bước:

**Bước 1 — Xác định invariant.**

Ví dụ: `available >= 0`, mỗi request idempotency chỉ có tối đa một reservation, một seat không được cấp cho hai booking, tổng member không vượt capacity.

**Bước 2 — Xác định những hàng nào cùng bị cạnh tranh.**

Có phải mọi request cùng sửa một `InventoryItem`? Có invariant trên nhiều `Membership` rows? Có row aggregate root cần khóa?

**Bước 3 — Chọn điểm thực thi atomic.**

Đối với kho: conditional UPDATE hoặc `@Version` + retry. Đối với đăng ký tối đa N người: version/counter chung, pessimistic lock của group, hoặc serializable logic.

**Bước 4 — Bảo vệ schema.**

`UNIQUE`, `FK`, `CHECK`, index thích hợp và constraints đúng DBMS. Tạo DB migrations thay vì chỉ thay annotation rồi hy vọng DDL tự khớp.

**Bước 5 — Đặt transaction boundary.**

Không gửi email, chờ user input, gọi HTTP chậm hoặc giữ pessimistic lock lâu trong một transaction nếu tránh được.

**Bước 6 — Định nghĩa conflict handling.**

Optimistic conflict → rollback, retry toàn transaction có giới hạn hoặc trả 409. Unique key trùng thật → báo business error. Serialization/deadlock → retry có kiểm soát.

**Bước 7 — Bảo đảm idempotency.**

Request có thể được gửi lại. Việc retry phải không tạo hai đơn hoặc trừ kho hai lần.

**Bước 8 — Xác định freshness yêu cầu.**

Dữ liệu để hiển thị có thể stale trong một khoảng nhỏ; dữ liệu dùng quyết định cuối phải được xác thực bởi update/lock/constraint tại thời điểm ghi.

**Bước 9 — Kiểm thử nhiều contexts/transactions.**

Tạo lịch tranh chấp có chủ đích; không dựa vào unit test mock repository một luồng để chứng minh an toàn concurrency.

**Bước 10 — Theo dõi production.**

Đo optimistic-conflict rate, lock wait, deadlock, transaction latency, retry count, constraint violations và độ lệch tồn kho nếu có.

## 29. Những hiểu nhầm thường gặp

### “Có `@Transactional` nên không thể mất cập nhật”

Sai. Transaction atomicity không tự thêm version check cho read-modify-write. Isolation và conflict detection mới quyết định lịch thực thi nào được chấp nhận.

### “`@Version` ngăn mọi race condition”

Sai. Nó bảo vệ chủ yếu những update/delete của entity row theo optimistic versioning. Hai entity mới, count-then-insert và invariant nhiều row cần giải pháp khác.

### “Gọi `find()` lần hai sẽ thấy transaction khác vừa commit”

Không nhất thiết. Persistence context có thể trả chính managed instance cũ mà không gửi SELECT mới.

### “Gọi `refresh()` là đã khóa dữ liệu”

Không. `refresh()` yêu cầu đọc lại state; transaction khác vẫn có thể thay đổi ngay sau đó, và kết quả đọc còn phụ thuộc isolation.

### “Khóa pessimistic làm mọi request SELECT phải chờ”

Không. Trên DB dùng MVCC, ordinary snapshot SELECT thường vẫn chạy; lock ngăn những thao tác cạnh tranh theo semantics database.

### “Đếm còn 1 chỗ rồi INSERT sẽ luôn an toàn”

Không. Hai transaction có thể cùng thấy một chỗ trống trước khi cùng thêm thành viên. Cần atomic capacity control.

### “`UNIQUE(email)` sẽ làm hai request tạo email trùng đều thành công nhưng giữ một hàng”

Không. Thường một request thành công và request kia nhận conflict/constraint error; nếu muốn upsert/idempotent behavior phải thiết kế rõ.

### “Retry câu UPDATE đã tính sẵn là đủ”

Không. Retry phải reload và kiểm tra lại invariant trong transaction mới, hoặc dùng một atomic statement có semantics đúng.

### “Pessimistic lock một row bảo vệ mọi hàng liên quan”

Không. Phạm vi khóa do database/provider xác định. Phantom insert và multi-row invariants cần protocol/constraint riêng.

### “Bulk JPQL update tự tăng version như entity dirty checking”

Không mặc định. Nếu cần thống nhất với `@Version`, phải chủ động cập nhật version và xử lý state L1.

### “Cùng một `EntityManager` chạy trên hai thread là concurrency test tốt”

Không. EntityManager/Session stateful không thread-safe; cần hai contexts/transactions độc lập.

### “Tăng isolation lên SERIALIZABLE là xong, không cần xử lý lỗi”

Không. Database có thể hủy transaction và báo serialization failure. Ứng dụng vẫn cần rollback/retry có giới hạn, idempotency và kiểm tra dữ liệu.

## 30. Bài tập tình huống

### Bài tập A — Hai lần trừ kho

Tồn kho là 10. Hai giao dịch cùng đọc 10, sau đó đều ghi 9, cuối cùng còn 9. Tên lỗi gì?

**Đáp án:** *Lost update*. Một phép trừ bị ghi đè. Có thể dùng `@Version` để phát hiện stale write hoặc conditional UPDATE để giảm giá trị atomically.

### Bài tập B — `find()` trả giá trị cũ

EntityManager A đã load `Item#100` với `available=10`. Transaction B commit thành 9. A gọi `find()` cùng ID vẫn được 10. Hibernate có hỏng không?

**Đáp án:** Không. A có first-level cache/managed instance. `find()` không mặc định reload. Dùng context/refresh phù hợp để đọc lại; dùng version/lock/conditional SQL bảo vệ khi ghi.

### Bài tập C — `refresh()` trước update

A gọi `refresh()`, thấy hàng còn 10, rồi B trừ còn 9 trước khi A lưu. A có được bảo vệ chỉ nhờ refresh không?

**Đáp án:** Không. Đây vẫn là check-then-act race. Cần update có version/điều kiện atomic hoặc khóa trước quyết định.

### Bài tập D — Hai user tạo cùng email

Cả hai `existsByEmail()` trả false. Cần điều gì ở database?

**Đáp án:** `UNIQUE(email)`, đồng thời có cách xử lý conflict/UPSERT/idempotency theo nghiệp vụ. `@Version` của account mới không thay thế unique.

### Bài tập E — Một bác sĩ luôn trực

Hai bác sĩ A và B đều trực. Mỗi người thấy người kia trực rồi đồng thời đánh dấu bản thân nghỉ, nên không còn ai trực. `@Version` riêng trên từng row có đủ không?

**Đáp án:** Không. Đây là *write skew* trên invariant nhiều row; cần row khóa chung, serializable + retry hoặc cấu trúc constraint/protocol phù hợp.

### Bài tập F — Retry sau optimistic exception

Transaction B nhận optimistic conflict. Có nên tiếp tục gọi `em.flush()` trên cùng EntityManager đến khi thành công?

**Đáp án:** Không. Rollback transaction lỗi, bỏ context đó và bắt đầu transaction mới; load lại dữ liệu, kiểm tra lại nghiệp vụ và retry có giới hạn nếu an toàn.

### Bài tập G — Pessimistic lock và đọc thường

A dùng `PESSIMISTIC_WRITE` trên Item#100. B chạy ordinary SELECT ở DB MVCC. B có chắc luôn phải chờ?

**Đáp án:** Không. Nonlocking snapshot reads có thể chạy và thấy bản phù hợp isolation; lock chủ yếu tuần tự hóa conflicting writers/locking requests.

### Bài tập H — Bulk SQL không tăng version

Một service dùng native SQL trừ `available` nhưng không tăng `version`. Service khác dùng Hibernate entity với `@Version`. Nguy cơ gì?

**Đáp án:** Các thay đổi ngoài ORM có thể không được Hibernate optimistic check nhận biết. Phải chuẩn hóa mọi write paths; với version số nguyên, atomic native update có thể chủ động tăng version.

### Bài tập I — Hết hàng khi retry

A và B cùng đặt 1 sản phẩm khi kho còn 1. A thành công; B bị optimistic conflict, retry đọc kho còn 0. B nên làm gì?

**Đáp án:** Thất bại nghiệp vụ “hết hàng”, không cố ép trừ tiếp. Retry là để đánh giá lại invariant, không bảo đảm mọi request cuối cùng đều được chấp nhận.

### Bài tập J — Request được gửi lại

Client không nhận response và gửi lại cùng lệnh mua. `@Version` có đủ ngăn trừ kho hai lần không?

**Đáp án:** Không. Hai giao dịch có thể chạy tuần tự và đều hợp lệ. Cần idempotency key gắn với ý định mua, unique constraint và quy trình trả lại kết quả đã xử lý.

### Bài tập K — Cập nhật hai bảng

Đăng ký thành viên tăng `Group.memberCount` và thêm `Membership`. Chỉ `@Version` trên `Membership` có đảm bảo capacity không?

**Đáp án:** Không. Nên để mọi thao tác capacity cạnh tranh trên cùng một row/version của Group, hoặc áp row lock/transaction protocol phù hợp cùng DB constraints.

### Bài tập L — Thread-safe

Hai worker cùng chia sẻ một EntityManager và mỗi worker sửa một field. Có phải đó là cách mô phỏng hai transaction cạnh tranh?

**Đáp án:** Không. EntityManager không thread-safe và cùng context không tương đương hai transaction. Tạo context/transaction riêng cho mỗi worker.

## 31. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Locking](https://docs.hibernate.org/stable/core/userguide/html_single/#locking): optimistic/pessimistic locking, versioned entities, lock modes và hành vi đối với conflict.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/stable/core/userguide/html_single/#pc): managed/detached state, dirty checking, merge, refresh, first-level cache.
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/stable/core/userguide/html_single/#flushing): khi nào SQL được đồng bộ, flush mode và transaction boundaries.
- [Hibernate ORM Javadoc — `OptimisticLocking`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/annotations/OptimisticLocking.html): optimistic locking theo trạng thái cũ cho những mapping không dùng version column.
- [Jakarta Persistence 3.2 — `EntityManager`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html): `find()`, `refresh()`, `lock()`, `merge()`, `flush()`, concurrency exceptions.
- [Jakarta Persistence 3.2 — `LockModeType`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/LockModeType.html): danh sách standard lock modes.
- [Jakarta Persistence 3.2 — Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): transaction, locking, optimistic version checks và persistence context.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): MVCC, isolation levels và anomalies trong PostgreSQL.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks và hành vi `FOR UPDATE`.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `CHECK`, `UNIQUE`, foreign key và bảo vệ invariant.

Hãy chọn tài liệu tương ứng **đúng phiên bản Hibernate/Jakarta Persistence và DBMS** đang dùng. Các SQL timeline trong bài mang tính giải thích; lịch thực thi có thể dẫn đến optimistic conflict, serialization error, deadlock hoặc kết quả khác tùy isolation và khả năng khóa của database.

## Kết luận

**Mất cập nhật, đọc dữ liệu cũ và điều kiện tranh chấp là ba hiện tượng khác nhau nhưng thường xuất hiện trong cùng một luồng nghiệp vụ.** Một persistence context có thể giữ state cũ; hai transaction có thể tính toán từ cùng snapshot; hai request có thể vượt qua bước kiểm tra trước khi database ghi bất kỳ thay đổi nào.

Trong Hibernate, `@Version` là công cụ quan trọng để **phát hiện stale writes trên cùng entity**, `PESSIMISTIC_WRITE` hỗ trợ **tuần tự hóa các writer tranh chấp những hàng đã khóa**, còn **atomic conditional UPDATE** giúp kiểm tra và thay đổi trạng thái tại database trong một thao tác. `refresh()` chỉ làm mới state theo khả năng nhìn thấy của transaction, không tự giải quyết race. Các invariant như email duy nhất, số chỗ tối đa, tồn kho không âm và ràng buộc trên nhiều hàng còn cần database constraints, transaction isolation và protocol cập nhật phù hợp.

Để xử lý an toàn, hãy **xác định invariant trước**, chọn đúng phạm vi hàng cần bảo vệ, kiểm thử với **hai persistence contexts/transactions độc lập**, xử lý rollback/retry/idempotency, và kiểm tra SQL thật trên DBMS triển khai. Đừng coi một annotation hoặc một lời gọi `@Transactional` là đủ để loại bỏ mọi điều kiện tranh chấp.
