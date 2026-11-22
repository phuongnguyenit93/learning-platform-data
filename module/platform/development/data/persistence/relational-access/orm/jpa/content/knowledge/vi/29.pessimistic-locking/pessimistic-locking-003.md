# Phân biệt PESSIMISTIC_READ, WRITE và FORCE_INCREMENT

Trong ứng dụng sử dụng JPA, nhiều transaction có thể đọc và chỉnh sửa cùng một bản ghi trong database. Nếu chỉ dựa vào việc tải entity, thay đổi field rồi commit, ứng dụng phải xử lý nguy cơ hai thao tác cùng dựa trên trạng thái cũ, cùng đặt chỗ một tài nguyên hoặc cập nhật chồng lấn.

**Khóa bi quan** (*pessimistic locking*) cho phép transaction yêu cầu database bảo vệ dữ liệu trong khi thực hiện một đơn vị công việc. Thay vì chờ tới khi có xung đột lúc ghi mới xử lý, transaction có thể chủ động lấy khóa khi đọc hoặc thao tác trên entity.

Jakarta Persistence định nghĩa ba lock mode bi quan thường gặp:

- `LockModeType.PESSIMISTIC_READ`: yêu cầu bảo vệ cho thao tác đọc, với ngữ nghĩa ngăn dirty read và non-repeatable read đối với entity bị khóa.
- `LockModeType.PESSIMISTIC_WRITE`: yêu cầu bảo vệ mạnh hơn cho tình huống đọc rồi ghi, nhằm ngăn các transaction khác cùng sửa dữ liệu được khóa khi transaction hiện tại còn giữ khóa.
- `LockModeType.PESSIMISTIC_FORCE_INCREMENT`: có ngữ nghĩa khóa bi quan mạnh tương tự WRITE và **yêu cầu tăng version của một entity có `@Version`**, ngay cả khi ứng dụng không sửa thuộc tính persistent nào của entity đó.

Ví dụ cách gọi:

```java
Book readLocked = em.find(
    Book.class,
    42L,
    LockModeType.PESSIMISTIC_READ
);

Book writeLocked = em.find(
    Book.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE
);

Book writeLockedAndVersioned = em.find(
    Book.class,
    42L,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

Những lời gọi này cần **transaction đang hoạt động và persistence context tham gia transaction**, đồng thời database/provider phải hỗ trợ cơ chế thích hợp. Không nên gọi chúng trên một `EntityManager` nằm ngoài transaction rồi mong khóa vẫn được duy trì.

Điểm then chốt của bài học: **ba mode thể hiện ba ý định bảo vệ khác nhau, không phải ba cú pháp SQL cố định**. `PESSIMISTIC_READ` không bắt buộc được triển khai bằng shared lock trên mọi database; `PESSIMISTIC_WRITE` không bảo đảm khóa mọi câu SELECT thường trong hệ thống dùng MVCC; và `PESSIMISTIC_FORCE_INCREMENT` không đơn thuần là một alias của WRITE vì nó còn tác động tới version.

Bài **“Phân biệt PESSIMISTIC_READ, WRITE và FORCE_INCREMENT”** nằm trong chương **Khóa bi quan** của chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung đi từ contract JPA, cơ chế database và các timeline cạnh tranh đến ví dụ nghiệp vụ, timeout, deadlock, exception, transaction, Spring Data JPA, integration test và bài tập.

Các ví dụ dùng `jakarta.persistence` và Java 17+. Với các phiên bản JPA cũ có package `javax.persistence`, cần thay import/hint namespace tương ứng. Khi nói tới Hibernate hoặc Spring, bài sẽ phân biệt rõ đó là API/framework bổ sung chứ không phải đặc tả JPA portable.

---

## 1. Vì sao cần khóa bi quan?

Giả sử hệ thống bán vé chỉ còn một chỗ:

```text
InventoryItem #42
availableQuantity = 1
```

Hai request chạy gần như cùng lúc:

```text
Transaction A                          Transaction B
      │                                      │
  SELECT quantity=1                     SELECT quantity=1
      │                                      │
  Tính 1 - 1 = 0                      Tính 1 - 1 = 0
      │                                      │
  UPDATE quantity=0                    UPDATE quantity=0
      │                                      │
    COMMIT                               COMMIT
```

Nếu không có cơ chế concurrency control phù hợp, cả hai request có thể cùng thông báo đặt vé thành công dù chỉ còn một chỗ. Đây là tình huống **lost update** hoặc vi phạm bất biến nghiệp vụ tùy cách câu SQL được thực hiện.

Có nhiều chiến lược xử lý:

1. **Khóa lạc quan với `@Version`:** cho phép các transaction cùng làm việc, nhưng kiểm tra version khi cập nhật; transaction dùng phiên bản cũ sẽ bị từ chối.
2. **Khóa bi quan:** lấy khóa database trước khi kiểm tra và sửa trạng thái, khiến thao tác cạnh tranh phải chờ, thất bại do timeout hoặc được xử lý nối tiếp.
3. **Câu UPDATE nguyên tử có điều kiện:** ví dụ `UPDATE inventory SET quantity = quantity - 1 WHERE id = ? AND quantity > 0`; kiểm tra row count.
4. **Cơ chế khác:** uniqueness constraints, isolation levels, queues, distributed coordination hoặc domain-specific reservations.

Khóa bi quan hữu ích khi:

- Có khả năng xung đột cao.
- Sau khi đọc một row, transaction phải quyết định ghi dựa trên giá trị vừa đọc.
- Không muốn transaction thực hiện nhiều tính toán rồi thất bại muộn do optimistic conflict.
- Cần bảo vệ nhất quán cho một đơn vị công việc ngắn và rõ.
- Có nhiều thao tác đồng thời cùng tranh chấp một số tài nguyên nhỏ.

Đổi lại, nó có thể làm tăng thời gian chờ, contention, deadlock và mức sử dụng connection. Vì vậy không nên coi pessimistic lock là mặc định cho mọi SELECT.

## 2. Khóa bi quan đặt ở đâu?

Trong ứng dụng JPA, lời gọi API diễn đạt yêu cầu khóa:

```java
em.find(Book.class, id, LockModeType.PESSIMISTIC_WRITE);
```

Provider chuyển yêu cầu này thành cơ chế tương ứng của database/dialect, thường thông qua SQL có locking clause hoặc lệnh khóa bổ sung. Ví dụ minh họa trên một số database:

```sql
SELECT id, version, title, price
FROM books
WHERE id = ?
FOR UPDATE;
```

Nhưng **`FOR UPDATE` không phải SQL chuẩn duy nhất mà tất cả provider phải sinh ra**. Một database có shared row locks, một database dùng các locking hints, một database dùng MVCC kết hợp row-level locks, và một số tính năng có thể không được hỗ trợ theo cách hoàn toàn tương đương.

Cần phân biệt ba tầng:

| Tầng | Trách nhiệm |
| --- | --- |
| JPA `LockModeType` | Diễn đạt ngữ nghĩa khóa mà ứng dụng yêu cầu |
| JPA provider/dialect | Ánh xạ yêu cầu sang SQL/driver/database phù hợp |
| Database transaction | Cấp, duy trì, chờ hoặc từ chối khóa; quyết định visibility theo isolation |

**Ngữ nghĩa của mode là hợp đồng ứng dụng; cú pháp và chi tiết contention là đặc thù DB/provider.**

## 3. Bảng so sánh ba lock mode

| Tiêu chí | `PESSIMISTIC_READ` | `PESSIMISTIC_WRITE` | `PESSIMISTIC_FORCE_INCREMENT` |
| --- | --- | --- | --- |
| Mục đích chính | Bảo vệ thao tác đọc ổn định | Bảo vệ thao tác đọc–sửa–ghi | Bảo vệ như WRITE và buộc thay đổi version |
| Ngăn dirty/non-repeatable reads theo yêu cầu JPA | Có | Có | Có |
| Chặn cập nhật cạnh tranh lên hàng bị khóa | Theo ngữ nghĩa khóa đọc mà provider bảo đảm | Mục tiêu chính là khóa ghi độc quyền tương ứng | Tương tự WRITE |
| Nhiều transaction cùng lấy READ có luôn tương thích không? | **Không bảo đảm portable**; tùy DB/implementation | Không áp dụng như shared-read intent | Không |
| Có thể chặn transaction khác lấy WRITE không? | Có thể | Có | Có |
| Bắt buộc có entity `@Version` để dùng hợp lý? | Không nhất thiết | Không nhất thiết | **Có**, mode mang semantics tăng version |
| Có yêu cầu tăng version dù không sửa field? | Không | Không | **Có** |
| Phù hợp nhất | Đọc cần bảo vệ trong transaction | Kiểm tra số dư/tồn kho trước khi cập nhật | Sửa aggregate/association và cần báo thay đổi qua version root |
| Có thể gây chờ/timeout/deadlock? | Có | Có | Có |
| Có thay thế transaction không? | Không | Không | Không |
| Có bảo đảm khóa cả bảng/graph liên quan không? | Không | Không | Không |
| Có đảm bảo mọi plain SELECT khác bị chặn không? | Không | Không, nhất là dưới MVCC | Không, nhất là dưới MVCC |

Bảng trên mô tả **ý định và bảo đảm ở cấp JPA**. Nó không phải sơ đồ tương thích shared/exclusive lock cố định cho mọi database. Khi một database không có shared lock hoặc không đủ khả năng hỗ trợ `PESSIMISTIC_READ` riêng, provider có thể dùng khóa mạnh hơn để bảo đảm yêu cầu tối thiểu.

## 4. `PESSIMISTIC_READ`: khóa để đọc ổn định

Ví dụ một transaction cần đọc các thuộc tính của Book và dùng kết quả cho quyết định quan trọng:

```java
em.getTransaction().begin();

Book book = em.find(
    Book.class,
    bookId,
    LockModeType.PESSIMISTIC_READ
);

validateBookState(book);

// Những phép đọc/kiểm tra cần nhất quán
// vẫn nằm trong transaction được bảo vệ.

em.getTransaction().commit();
```

Theo JPA, `PESSIMISTIC_READ` được dùng để ngăn **dirty reads** và **non-repeatable reads** đối với dữ liệu thực thể được khóa. Hãy hiểu:

- **Dirty read:** một transaction đọc thay đổi chưa commit của transaction khác.
- **Non-repeatable read:** cùng một transaction đọc lại một row nhưng giá trị bị thay đổi do transaction khác commit trong khoảng thời gian đó.

Một cách cài đặt phổ biến là shared lock, nhưng **không nên suy rằng mọi database luôn dùng shared lock**. Provider có thể yêu cầu khóa mạnh hơn nếu DB không có shared-lock primitive phù hợp.

### Khóa READ có nghĩa mọi transaction READ chạy song song?

Không có bảo đảm đó trên tất cả tổ hợp database, isolation và provider.

Ví dụ về **khả năng** ở một DB có shared locks:

```text
Transaction A: shared/read lock Book #42
Transaction B: shared/read lock Book #42  → có thể cùng được cấp
Transaction C: exclusive/write lock #42   → có thể phải chờ
```

Nhưng ở một DB/provider dùng exclusive lock để thực hiện `PESSIMISTIC_READ`, B cũng có thể phải chờ A. Vì vậy **PESSIMISTIC_READ không phải cam kết “READ luôn không chặn READ”**.

### Khi nào READ không đáng dùng?

Một trang danh sách thuần hiển thị có thể chỉ cần một snapshot phù hợp isolation của database. Nếu dùng READ lock cho mọi row trên trang lớn, transaction dễ giữ nhiều khóa, gây tranh chấp không cần thiết.

Khóa READ nên dành cho use case thật sự cần bảo vệ trong thời gian transaction, không phải mọi lệnh đọc vì muốn “chắc chắn mới nhất”.

## 5. `PESSIMISTIC_WRITE`: khóa cho thao tác đọc rồi sửa

Đây là mode phổ biến nhất cho workflow tồn kho, đặt chỗ, số dư hoặc trạng thái có cạnh tranh cao.

```java
em.getTransaction().begin();

Book book = em.find(
    Book.class,
    bookId,
    LockModeType.PESSIMISTIC_WRITE
);

book.changePrice(new BigDecimal("220000"));

em.getTransaction().commit();
```

Ý nghĩa: transaction muốn một dạng khóa ghi độc quyền phù hợp ở database để tránh transaction khác cập nhật cùng dữ liệu trong khi đơn vị công việc hiện tại thao tác.

Một timeline thường gặp:

```text
Transaction A                            Transaction B
      │                                        │
SELECT ... FOR UPDATE Book #42                │
      │                                        │
  Được cấp lock                                 │
      │                              Thử PESSIMISTIC_WRITE #42
      │                                        │
  Đổi giá                                   Chờ lock
      │                                        │
  Flush / COMMIT                             Chờ lock
      │                                        │
  Lock được giải phóng                         ▼
                                      B được cấp lock hoặc
                                      thất bại do timeout
```

Kết quả “B chờ rồi tiếp tục” hay “B bị lỗi” phụ thuộc lock timeout, isolation, chính sách database và transaction schedule.

### WRITE không đồng nghĩa chặn mọi SELECT thường

Ở database dùng MVCC, transaction khác chạy `SELECT` không khóa có thể đọc **bản dữ liệu đã commit trước đó**, dù transaction A đang giữ write lock. Đây là hành vi có thể hoàn toàn hợp lệ.

Ví dụ:

```text
A giữ PESSIMISTIC_WRITE và đã UPDATE nhưng chưa commit.
B chạy plain SELECT.
B có thể thấy giá trị committed cũ theo MVCC.
```

Đừng viết test mặc định rằng mọi `SELECT` phải bị block bởi `PESSIMISTIC_WRITE`. Phải phân biệt:

- Plain SELECT theo isolation policy.
- SELECT với explicit pessimistic lock.
- UPDATE/DELETE trên cùng row.
- Reads dùng snapshot.
- Database cụ thể và lock granularity.

WRITE chủ yếu bảo vệ những thao tác cạnh tranh mà DB row locks có thể kiểm soát, không thay thế mọi guarantee về freshness cho tất cả readers.

## 6. `PESSIMISTIC_FORCE_INCREMENT`: WRITE kèm tăng version

Giả sử Book có:

```java
@Id
private Long id;

@Version
private Long version;
```

Khi dùng:

```java
Book book = em.find(
    Book.class,
    id,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

JPA được yêu cầu thực hiện khóa theo semantics của `PESSIMISTIC_WRITE` **và tăng version** của Book, kể cả khi Book không bị sửa field thông thường.

Ý nghĩa:

- Transaction muốn bảo vệ Book bằng khóa bi quan.
- Khi transaction thay đổi và commit thành công, version phản ánh rằng Book đã trải qua một lần thay đổi logic cần được nhận diện.
- Một transaction khác đã giữ version cũ rồi cố update qua optimistic locking có thể bị phát hiện stale.

### Có thể dùng FORCE_INCREMENT không có `@Version`?

`PESSIMISTIC_FORCE_INCREMENT` mang yêu cầu tăng version. Với entity không versioned, không có cơ chế version JPA portable để thực hiện yêu cầu này. Hãy dùng mode này cho **entity có `@Version` hợp lệ** và kiểm tra hỗ trợ provider. Không coi nó là cách tự động “thêm version ảo” cho một entity không có cột version.

### Version tăng lúc nào?

Không nên viết:

```java
Book b = em.find(
    Book.class,
    id,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);

assertEquals(oldVersion + 1, b.getVersion());
```

rồi coi assertion ngay sau `find` là portable. Provider có thể xử lý việc tăng version tại một thời điểm phù hợp khi lock, flush hoặc commit; cụ thể cần kiểm tra theo JPA/provider. Kiểu version cũng không bắt buộc là số tăng đúng một đơn vị trong mọi mapping.

Muốn xác nhận persisted version đã đổi, hãy **commit** rồi đọc bằng EntityManager mới trong integration test.

## 7. FORCE_INCREMENT khác WRITE ở đâu?

So sánh một transaction chỉ khóa Book mà không sửa field.

Với WRITE:

```java
em.getTransaction().begin();

Book book = em.find(
    Book.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);

// Không sửa thuộc tính persistent.

em.getTransaction().commit();
```

Nếu không có dirty changes hay cơ chế khác, **WRITE không tự bắt buộc tăng version** chỉ vì đã lấy khóa.

Với FORCE_INCREMENT:

```java
em.getTransaction().begin();

Book book = em.find(
    Book.class,
    id,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);

// Không sửa thuộc tính persistent.

em.getTransaction().commit();
```

**FORCE_INCREMENT yêu cầu tăng version**, miễn transaction thành công và entity được versioned theo contract.

Điểm này quan trọng trong domain-driven design: nhiều thao tác cập nhật những entity con hoặc quan hệ mà ứng dụng muốn xem là một thay đổi của aggregate root. FORCE_INCREMENT có thể biểu thị rằng root đã thay đổi ở cấp logic, dù field của row root không đổi.

## 8. Khác biệt với `OPTIMISTIC_FORCE_INCREMENT`

JPA còn có:

```java
LockModeType.OPTIMISTIC_FORCE_INCREMENT
```

Đừng nhầm nó với:

```java
LockModeType.PESSIMISTIC_FORCE_INCREMENT
```

| Đặc điểm | OPTIMISTIC_FORCE_INCREMENT | PESSIMISTIC_FORCE_INCREMENT |
| --- | --- | --- |
| Họ khóa | Lạc quan | Bi quan |
| Yêu cầu tăng version | Có | Có |
| Yêu cầu database pessimistic write lock | Không theo định nghĩa mode | Có |
| Đọc/sửa cạnh tranh | Dựa vào optimistic version verification và increment | Kết hợp row locking với version increment |
| Có thể gây lock wait | Có thể do SQL version update/isolation nhưng không phải mục đích lấy pessimistic lock ngay | Có, đây là phần chính |
| Dùng khi | Muốn báo thay đổi version mà không cần pessimistic locking | Muốn loại trừ cạnh tranh trong transaction **và** báo thay đổi qua version |

Hai mode đều có thể khiến một optimistic transaction cũ thất bại, nhưng **cơ chế tranh chấp và mức lock mà ứng dụng yêu cầu không giống nhau**.

## 9. Entity mẫu: tồn kho và phiên bản

Một ví dụ sát nghiệp vụ:

```java
import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int availableQuantity;

    protected InventoryItem() {}

    public InventoryItem(String sku, int availableQuantity) {
        this.sku = Objects.requireNonNull(sku);
        if (availableQuantity < 0) {
            throw new IllegalArgumentException("Quantity must be >= 0");
        }
        this.availableQuantity = availableQuantity;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getSku() { return sku; }
    public int getAvailableQuantity() { return availableQuantity; }

    public void reserve(int requested) {
        if (requested <= 0) {
            throw new IllegalArgumentException("requested must be positive");
        }
        if (availableQuantity < requested) {
            throw new IllegalStateException("Insufficient stock");
        }
        availableQuantity -= requested;
    }

    public void restock(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        availableQuantity = Math.addExact(
            availableQuantity, amount
        );
    }
}
```

DDL ý tưởng:

```sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(120) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL,
    CONSTRAINT ck_available_nonnegative
        CHECK (available_quantity >= 0)
);
```

Cú pháp tạo khóa và hỗ trợ CHECK constraint phụ thuộc DB. `@Version` giúp khóa lạc quan khi dùng managed entity, còn row-level locks được yêu cầu bằng pessimistic lock modes.

### Vì sao vẫn cần constraint?

Ngay cả khi khóa bi quan đúng, dữ liệu cũng có thể bị sửa bởi batch SQL, ứng dụng khác hoặc lỗi mapping. Constraint ở database bảo vệ bất biến tối thiểu như số lượng không âm; code ứng dụng và locking vẫn cần kiểm tra nghiệp vụ nhưng không nên là tầng bảo vệ duy nhất.

## 10. Ví dụ WRITE: đặt chỗ tồn kho an toàn

Một service resource-local:

```java
public void reserveStock(
        EntityManagerFactory emf,
        Long itemId,
        int quantity) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item = em.find(
            InventoryItem.class,
            itemId,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (item == null) {
            throw new IllegalArgumentException(
                "Inventory item not found"
            );
        }

        item.reserve(quantity);

        em.getTransaction().commit();
    } catch (RuntimeException failure) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Luồng:

1. Bắt đầu transaction.
2. Tải InventoryItem kèm yêu cầu WRITE lock.
3. Kiểm tra `availableQuantity` trong transaction đang bảo vệ row.
4. Trừ số lượng bằng domain method.
5. Commit; managed change được JPA flush.
6. Lock được giải phóng khi transaction hoàn tất.

Nếu transaction khác cùng dùng phương thức này trên cùng row, nó thường phải chờ hoặc bị từ chối theo timeout, thay vì cả hai cùng đọc tồn kho và quyết định trên cùng giá trị cũ.

**Bảo đảm cuối cùng còn phụ thuộc mọi đường ghi khác vào cùng inventory row đều tôn trọng row locking/constraint.** Nếu application khác sửa dữ liệu theo một quy trình không phù hợp, cần kiểm tra transaction và DB semantics chứ không mặc định một lời gọi JPA sẽ bảo vệ cả hệ thống phân tán.

## 11. Vì sao READ chưa đủ cho thao tác đặt chỗ?

Giả sử code:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_READ
);

item.reserve(quantity);
```

Ứng dụng thực tế **định ghi**, nhưng lại yêu cầu khóa đọc. Nếu database cho phép nhiều shared read locks cùng lúc, hai transaction có thể cùng giữ read lock rồi đều cố nâng cấp thành write lock khi flush.

Timeline minh họa:

```text
Transaction A                          Transaction B
READ lock item #42                    READ lock item #42
      │                                      │
Cả hai đều thấy quantity=1           Cả hai đều thấy quantity=1
      │                                      │
A cần nâng lên WRITE                  B cần nâng lên WRITE
      │                                      │
Có thể xảy ra lock-conversion deadlock hoặc wait
```

Không thể kết luận rằng luôn xảy ra deadlock; kết quả tùy engine. Nhưng đây là lý do **nếu mục tiêu chắc chắn là sửa row, thường nên yêu cầu `PESSIMISTIC_WRITE` ngay từ đầu**, thay vì cố bắt đầu READ rồi nâng cấp sau.

### READ có làm business logic không bao giờ đua tranh?

Không. READ bảo vệ theo ngữ nghĩa đọc của JPA/DB. Một update cuối cùng vẫn phải lấy điều kiện khóa ghi, và sự tương thích/upgrade của các transaction khác nhau có thể gây chờ hoặc deadlock.

## 12. Ví dụ READ: đọc trạng thái cần ổn định trong transaction

Giả sử một workflow xác thực các điều kiện từ một Book:

```java
public ValidationResult checkBookStatus(
        EntityManager em, Long bookId) {

    Book book = em.find(
        Book.class,
        bookId,
        LockModeType.PESSIMISTIC_READ
    );

    if (book == null) {
        return ValidationResult.notFound();
    }

    boolean valid = book.isPublished()
        && book.getPrice().signum() > 0;

    return valid
        ? ValidationResult.allowed()
        : ValidationResult.denied();
}
```

Đoạn code giả định caller đang ở **active joined transaction**, `Book` có mapping tương ứng và `ValidationResult` là DTO/domain result riêng. Không được gọi method này ngoài transaction rồi mong READ lock có hiệu lực.

READ phù hợp khi:

- Đang đọc một entity có ý nghĩa nhất quán xuyên các bước trong transaction.
- Cần ngăn những thay đổi cạnh tranh khiến cùng entity được đọc không lặp lại.
- Không có ý định cập nhật row ngay trong đơn vị công việc đó.
- Đã cân nhắc overhead khóa so với database isolation/snapshot.

Tuy nhiên, nếu kết quả validation dùng để **quyết định ghi vào cùng row hoặc tài nguyên phụ thuộc**, có thể cần WRITE hoặc chiến lược khóa một tập row khác để bảo đảm bất biến.

## 13. Force increment cho aggregate root

Giả sử có PurchaseOrder root và OrderLine entities. Các transaction sửa lines nhưng cần phát hiện xung đột ở cấp Order.

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Long getVersion() { return version; }
}
```

`OrderLine` là entity khác có FK tới PurchaseOrder.

Một service muốn thay một line và buộc root version thay đổi:

```java
em.getTransaction().begin();

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);

if (order == null) {
    throw new IllegalArgumentException("Order not found");
}

OrderLine line = em.find(OrderLine.class, lineId);

if (line == null ||
    !line.getOrder().getId().equals(orderId)) {
    throw new IllegalArgumentException(
        "Order line does not belong to order"
    );
}

line.changeQuantity(newQuantity);

em.getTransaction().commit();
```

Mục đích:

- Order root được bảo vệ bằng pessimistic write semantics.
- Version của root được yêu cầu tăng dù field `status` không thay đổi.
- Một workflow khác dựa vào version cũ của PurchaseOrder có thể phát hiện xung đột khi thực hiện optimistic update/check.

**Không được suy rằng FORCE_INCREMENT tự khóa mọi OrderLine row hoặc tự biến thay đổi child thành một transaction an toàn ở cấp aggregate.** Nếu các workflow khác sửa lines mà không tuân theo quy tắc khóa root/version, chúng vẫn có thể cạnh tranh ở child rows. Mọi đường ghi cần nhất quán với aggregate locking policy.

### Chọn FORCE_INCREMENT hay WRITE?

- Chỉ cần bảo vệ Order row trong một transaction ngắn, không cần phát tín hiệu thay đổi version khi row không đổi → WRITE có thể đủ.
- Cần bảo vệ Order row **và** thể hiện rằng aggregate đã thay đổi để các optimistic clients có thể nhận diện stale state → cân nhắc FORCE_INCREMENT.
- Không cần exclusive pessimistic lock nhưng muốn version root tăng → cân nhắc `OPTIMISTIC_FORCE_INCREMENT`, với trade-off khác.

## 14. Nếu sửa field bình thường, WRITE đã có thể tăng version

Với entity có `@Version`:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);

item.reserve(1);
```

Khi entity dirty và managed update được flush/commit, `@Version` thường được tăng theo optimistic versioning semantics.

Vì vậy, trong tình huống này dùng `PESSIMISTIC_FORCE_INCREMENT` **không nhất thiết mang lại lợi ích phiên bản đáng kể hơn** nếu root đã chắc chắn có managed update.

FORCE_INCREMENT đặc biệt có ý nghĩa khi:

- Không có field persistent nào của root thay đổi.
- Muốn bảo vệ business operation thuộc aggregate bằng việc bump root version.
- Cần signal cho optimistic readers/clients rằng trạng thái logic đã đổi.

Không nên bật FORCE_INCREMENT cho mọi thao tác đọc vì nó có thể phát thêm UPDATE, gây write amplification và tăng contention.

## 15. Timeline so sánh cùng một tài nguyên

Xét hai transaction A/B cùng truy cập InventoryItem #42.

### Trường hợp A và B đều READ

```text
A: PESSIMISTIC_READ #42 ──── giữ khóa ───── COMMIT
B: PESSIMISTIC_READ #42 ──── ?
```

Nếu DB hỗ trợ shared locks tương thích, B có thể cùng được cấp khóa đọc. Nếu không, B có thể phải chờ. Không có thứ tự toàn cục portable để khẳng định.

### A WRITE, B WRITE

```text
A: PESSIMISTIC_WRITE #42 ─── giữ khóa ──── COMMIT
B: thử PESSIMISTIC_WRITE #42  ─────────────► chờ/timeout
                                      sau khi A kết thúc:
                                      lấy khóa hoặc thất bại
```

Ở DB thông thường có row-level locking, hai thao tác ghi cùng row không thể cùng giữ một exclusive row lock ở cùng thời điểm.

### A FORCE_INCREMENT, B optimistic reader

```text
B: Đọc PurchaseOrder version=7
A: FORCE_INCREMENT Order, commit version mới
B: Dùng bản version=7 để cập nhật/check
   → có thể gặp OptimisticLockException khi kiểm tra version
```

Lợi ích ở đây là kết nối **pessimistic coordination trong transaction A** với **optimistic version check trong workflow B**.

### A WRITE, B plain SELECT

Trong hệ thống MVCC, B có thể đọc phiên bản đã commit trước đó. Không lấy kết quả plain SELECT làm bằng chứng A không giữ WRITE lock.

---

## 16. Transaction là phạm vi sống của pessimistic lock

Một yêu cầu pessimistic lock **không phải khóa gắn vĩnh viễn với entity object**. Nó được dùng trong transaction mà provider/database thực thi yêu cầu.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(
    Book.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);

// Xử lý nghiệp vụ ngắn gọn.

em.getTransaction().commit(); // Transaction kết thúc.
```

Thời điểm giải phóng database locks được điều khiển bởi DB transaction completion/rollback semantics. Không nên nghĩ đóng EntityManager mà vẫn còn một active transaction theo mô hình tùy tiện là cách hợp lệ để giữ hay nhả lock.

### Tại sao cần transaction?

Pessimistic locks phải tồn tại đủ lâu để bảo vệ quyết định nghiệp vụ. Nếu mỗi SELECT chạy một transaction riêng và commit ngay, khóa có thể được nhả trước khi UPDATE tiếp theo diễn ra.

Sai về cấu trúc:

```java
// Transaction A: chỉ đọc lock rồi kết thúc.
Book book = readWithPessimisticWrite(id);

// Transaction B khác, về sau mới cập nhật.
updateBook(id, newTitle);
```

Nếu `readWithPessimisticWrite` đã commit trước khi `updateBook` bắt đầu, khoảng trống giữa chúng không còn được bảo vệ bởi khóa cũ.

Đúng về ý định:

```text
Begin transaction
  ├─ Acquire lock
  ├─ Read state
  ├─ Validate business rules
  ├─ Apply managed changes
  └─ Commit/Rollback
End transaction
```

**Không kéo dài transaction chỉ để chờ người dùng nhập liệu hoặc gọi một hệ thống bên ngoài chậm.** Khi đó phải chọn workflow/coordination khác.

## 17. `EntityManager.find` với lock mode

JPA cung cấp overload:

```java
T entity = em.find(
    EntityClass.class,
    id,
    lockMode
);
```

Ví dụ:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Ưu điểm:

- Rõ ràng transaction cần row khóa ngay khi tải entity theo ID.
- Thích hợp cho thao tác trên một row đã biết ID.
- Không cần JPQL nếu chỉ tìm một entity.

### Entity đã nằm trong persistence context thì sao?

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id
);

// ... item đã managed ...

InventoryItem locked = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

Provider vẫn phải đáp ứng yêu cầu lock mode phù hợp. Nhưng việc gọi `find` lại không đồng nghĩa nó tạo một Java object mới hoặc refresh tất cả field. Identity map có thể giữ cùng representative.

Khi entity được tải trước lúc transaction khác sửa DB, yêu cầu pessimistic lock trên một entity versioned có thể dẫn tới version consistency check và phát lỗi thay vì âm thầm chấp nhận state stale.

Nếu mục tiêu là **đọc lại state** kèm lock, hãy xem `refresh(entity, lockMode)` theo semantics của JPA, không mặc định một lần `find` thứ hai luôn loại bỏ state cũ.

## 18. `EntityManager.lock`: nâng yêu cầu khóa cho managed entity

Khi đã có managed instance:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId
);

// Sau khi xác định cần cập nhật:
em.lock(item, LockModeType.PESSIMISTIC_WRITE);
```

`lock()` yêu cầu provider áp dụng lock mode cho managed entity phù hợp.

Nhưng hãy cân nhắc khoảng thời gian **trước** lời gọi lock: nếu ứng dụng đã đọc state và đưa ra quyết định quan trọng trước khi khóa, decision có thể dựa trên dữ liệu cũ.

Ví dụ đáng ngờ:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id
);

boolean available =
    item.getAvailableQuantity() >= requested;

// Transaction khác có thể thay đổi dữ liệu trước khi lock.

em.lock(item, LockModeType.PESSIMISTIC_WRITE);

if (available) {
    item.reserve(requested);
}
```

Đây là lỗi **check-then-lock**: kết quả `available` được tính từ trạng thái trước khi bảo vệ. Với entity versioned, provider có thể phát hiện stale version; nhưng không nên phụ thuộc vào điều đó thay cho thứ tự nghiệp vụ đúng.

Tốt hơn là khóa trước khi đọc/validate hoặc refresh dữ liệu dưới lock khi cần:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);

if (item == null) {
    throw new IllegalArgumentException("Not found");
}

item.reserve(requested);
```

## 19. `refresh(entity, lockMode)`: đọc lại state dưới khóa

`EntityManager.refresh` có overload nhận lock mode:

```java
em.refresh(
    item,
    LockModeType.PESSIMISTIC_WRITE
);
```

Khi entity đang managed và transaction hợp lệ, lời gọi thể hiện mục đích **làm mới state** và áp dụng lock mode thích hợp.

Các lưu ý:

- `refresh()` có thể **ghi đè thay đổi local chưa flush** trên entity.
- Không gọi `refresh()` để “cứu” một transaction đã bị exception/rollback-only.
- Nếu row đã bị xóa, refresh có thể gây lỗi.
- Association/cascade REFRESH có thể ảnh hưởng scope.
- Database isolation/cache policy vẫn tác động cách quan sát dữ liệu.

Ví dụ cẩn trọng:

```java
em.getTransaction().begin();

InventoryItem item = em.find(
    InventoryItem.class, id
);

// Chưa sửa local state.
em.refresh(item, LockModeType.PESSIMISTIC_WRITE);

// Lúc này kiểm tra và áp dụng command nghiệp vụ.
item.reserve(requested);

em.getTransaction().commit();
```

Nếu không có lý do phải load trước, thường đơn giản hơn là gọi `find(..., PESSIMISTIC_WRITE)` ngay từ đầu.

## 20. Query với `setLockMode`

Không phải mọi use case đều tìm theo ID. Có thể khóa các entity trả về từ JPQL:

```java
TypedQuery<InventoryItem> query = em.createQuery(
    "SELECT i FROM InventoryItem i " +
    "WHERE i.sku = :sku",
    InventoryItem.class
);

query.setParameter("sku", sku);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);

InventoryItem item = query.getSingleResult();
```

Ý nghĩa:

- Query chọn entity theo điều kiện.
- Provider phải áp dụng lock mode cho các entity kết quả theo semantics phù hợp.
- SQL có thể gồm locking clause hoặc câu lệnh bổ sung.

### Query chỉ trả scalar thì sao?

```java
TypedQuery<Long> query = em.createQuery(
    "SELECT COUNT(i) FROM InventoryItem i",
    Long.class
);
```

Một scalar aggregate không phải một managed entity result có thể khóa theo JPA `setLockMode`. Không nên tự áp lock mode cho mọi query rồi suy nó sẽ “khóa các row đã count”.

Theo contract JPA, các thao tác lock mode trên query không phù hợp có thể ném `IllegalStateException` hoặc ngoại lệ khác. Nếu cần một invariant dựa trên nhiều rows, phải thiết kế locking/query/constraints phù hợp với nhóm dữ liệu thực sự cần bảo vệ.

## 21. Criteria API và pessimistic lock

Có thể xây SELECT bằng Criteria:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<InventoryItem> cq =
    cb.createQuery(InventoryItem.class);

Root<InventoryItem> root =
    cq.from(InventoryItem.class);

cq.select(root)
  .where(cb.equal(root.get("sku"), sku));

TypedQuery<InventoryItem> query =
    em.createQuery(cq);

query.setLockMode(
    LockModeType.PESSIMISTIC_WRITE
);

InventoryItem item = query.getSingleResult();
```

Phân chia trách nhiệm:

- `CriteriaBuilder` tạo các biểu thức.
- `CriteriaQuery` mô tả SELECT.
- `Root` xác định entity nguồn.
- `TypedQuery.setLockMode` yêu cầu khóa khi query thực thi.

**Criteria API không tự làm transaction hay lock mạnh hơn JPQL.** Khóa chỉ có hiệu lực theo mode, database và transaction.

## 22. Native SQL `FOR UPDATE` và JPA LockModeType

Có thể viết native SQL mang locking clause riêng:

```java
Query q = em.createNativeQuery(
    "SELECT id, version, sku, available_quantity " +
    "FROM inventory_items WHERE id = ? FOR UPDATE",
    InventoryItem.class
);
```

Đây là ví dụ theo dialect hỗ trợ `FOR UPDATE`. Nó không tự portable trên mọi database; SQL Server, PostgreSQL, MySQL, Oracle và các DB khác có chi tiết khác nhau về locking clause/options.

Đặc biệt:

- Native SQL do application tự viết có thể bỏ qua abstraction JPA lock mode.
- Dùng `FOR UPDATE` trên một query không có active transaction có thể khiến khóa được nhả ngay hoặc query không hợp lệ theo DB/transaction setup.
- Nếu query trả entity đã managed, context có thể giữ state cũ và cần xem consistency/refresh.
- `NOWAIT`, `SKIP LOCKED` và vendor-specific hints không phải cú pháp native portable trong JPA.

Nếu ứng dụng chủ yếu dùng JPA, nên ưu tiên API `find(..., lockMode)` hoặc `query.setLockMode(...)` khi chúng biểu diễn đúng nhu cầu và provider hỗ trợ. Chỉ dùng native syntax riêng khi chủ động chấp nhận phụ thuộc dialect và đã kiểm thử.

## 23. Kiểm soát thời gian chờ bằng lock timeout hint

Nếu một transaction giữ WRITE lock quá lâu, transaction khác có thể chờ. JPA định nghĩa hint thông dụng:

```java
"jakarta.persistence.lock.timeout"
```

Ví dụ:

```java
Map<String, Object> hints = new HashMap<>();

hints.put(
    "jakarta.persistence.lock.timeout",
    3000
);

InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
```

Giá trị được biểu diễn bằng **mili-giây** theo API/hint. Trong ứng dụng JPA cũ, tên có thể là `javax.persistence.lock.timeout`.

Hoặc trên query:

```java
TypedQuery<InventoryItem> query = em.createQuery(
    "SELECT i FROM InventoryItem i WHERE i.id = :id",
    InventoryItem.class
);

query.setParameter("id", id);
query.setLockMode(
    LockModeType.PESSIMISTIC_WRITE
);

query.setHint(
    "jakarta.persistence.lock.timeout",
    3000
);

InventoryItem item = query.getSingleResult();
```

### Hint không phải cam kết mọi database tuân chính xác

- Không phải provider/database nào cũng hỗ trợ lock timeout hint ở mọi tình huống.
- Một số database chỉ hỗ trợ mức statement/session hoặc có độ phân giải khác.
- Giá trị `0` thường được dùng cho ý định no-wait; cần kiểm tra provider/dialect.
- Thời gian thực tế có thể chịu timeout của transaction, statement, driver hoặc database.
- Một số hint không được hỗ trợ có thể bị bỏ qua theo contract.

Không nên dùng một con số nhỏ rồi giả định transaction **chắc chắn** kết thúc đúng sau bấy nhiêu mili-giây trên mọi DB.

## 24. Hai loại exception liên quan lock failure

JPA phân biệt các tình huống quan trọng:

### `LockTimeoutException`

Thường biểu thị thất bại khi lấy khóa mà chỉ làm **rollback statement** (không nhất thiết đánh dấu toàn bộ transaction rollback-only).

```java
catch (LockTimeoutException ex) {
    // Một lock request bị timeout.
}
```

### `PessimisticLockException`

Thường biểu thị thất bại khi lấy khóa dẫn tới **transaction-level rollback**.

```java
catch (PessimisticLockException ex) {
    // Lock failure ảnh hưởng transaction.
}
```

Tuy nhiên, trong hệ thống thực tế còn có thể gặp:

- `PersistenceException` hoặc `RollbackException` bọc nguyên nhân.
- Database deadlock/serialization errors.
- Driver-specific SQL exceptions.
- Spring `PessimisticLockingFailureException` hoặc `CannotAcquireLockException`.
- Lỗi transaction timeout ngoài lock timeout.
- `OptimisticLockException` khi entity versioned stale tại lúc khóa.

### Có được tiếp tục transaction sau LockTimeoutException không?

Chuẩn phân biệt statement-level và transaction-level failure, nhưng để quyết định retry trong cùng transaction phải xét **transaction status thật**, database, provider và logic nghiệp vụ. Nhiều hệ thống chọn rollback cả unit of work rồi retry trong transaction mới cho đơn giản và an toàn hơn.

Không mặc định rằng một `LockTimeoutException` luôn cho phép tiếp tục các bước còn lại mà không ảnh hưởng invariants; cũng không gộp mọi lock error thành “đã có ai sửa dữ liệu”.

## 25. `OptimisticLockException` vẫn có thể xuất hiện khi dùng pessimistic lock

Có vẻ mâu thuẫn: đã yêu cầu `PESSIMISTIC_WRITE` tại sao còn optimistic conflict?

Với entity có `@Version`, JPA provider có thể kiểm tra sự nhất quán giữa version của entity đang managed trong persistence context với version trong database khi áp dụng pessimistic lock. Nếu instance stale do một transaction khác đã cập nhật, provider có thể phát hiện version mismatch.

Ví dụ:

```java
Book book = em.find(Book.class, id);

// Một transaction khác cập nhật Book và commit.

em.lock(
    book,
    LockModeType.PESSIMISTIC_WRITE
);
```

Nếu `book` mang version cũ, lấy khóa bi quan không nhất thiết đồng nghĩa được phép bỏ qua phiên bản stale và ghi đè. Có thể xuất hiện `OptimisticLockException`.

Cần phân biệt:

- **Lock wait failure:** cạnh tranh không lấy được database lock đúng hạn.
- **Optimistic version mismatch:** entity đang có version không còn phù hợp với DB.
- **Serialization/deadlock failure:** database từ chối một transaction schedule.
- **Not found:** hàng không tồn tại khi tìm, có thể trả null hoặc lỗi theo API.

Một phương thức dùng pessimistic lock có thể thất bại vì nhiều nguyên nhân, không chỉ `PessimisticLockException`.

## 26. Vì sao khóa READ không bảo vệ khỏi phantom reads?

**Non-repeatable read** xảy ra khi một row đã đọc bị đổi giá trị giữa hai lần đọc.

**Phantom read** xảy ra khi chạy lại một truy vấn theo điều kiện nhưng số hàng khớp thay đổi do transaction khác thêm/xóa row.

Ví dụ:

```sql
SELECT *
FROM reservations
WHERE room_id = 42
  AND reserved_date = '2026-11-20';
```

Nếu kết quả trống, transaction không có một **row đang tồn tại** để khóa theo cách thông thường. Một transaction khác có thể INSERT một reservation mới vào khoảng/điều kiện đó, tùy DB isolation và lock strategy.

`PESSIMISTIC_READ` hoặc `PESSIMISTIC_WRITE` trên một entity cụ thể **không tự bảo đảm ngăn phantom rows trong mọi query**.

### Cách bảo vệ điều kiện “không có row”

Có thể cần:

- Unique constraint ở database, ví dụ `UNIQUE(room_id, reserved_date)`.
- Khóa một parent/guard row đã tồn tại.
- Serializable isolation hoặc range/predicate locks khi DB hỗ trợ.
- Atomic conditional INSERT/UPDATE.
- Transaction schedule/queue theo tài nguyên.

**Không lấy lock một row bất kỳ rồi tin rằng mọi row liên quan trong query predicate đều được khóa.**

## 27. Lock một entity không có nghĩa lock toàn object graph

Ví dụ:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Order có thể liên kết:

- OrderLines.
- Customer.
- Payments.
- Addresses.

Không nên suy rằng tất cả các row của các entities ấy đều bị locked với cùng mode.

JPA có quy tắc về locking scopes và provider mapping; mặc định nhiều trường hợp tập trung ở row entity được khóa cùng một số bảng cấu thành state entity, không tự khoá toàn bộ relations tới các entity khác.

Nếu business invariant phụ thuộc vào nhiều rows, phải xác định **những rows nào cần bảo vệ**, và chọn thứ tự khóa, constraints hoặc aggregate root coordination phù hợp.

Đặc biệt, với `PESSIMISTIC_FORCE_INCREMENT` trên Order root, ý định bump version root **không tự cấp exclusive locks cho từng OrderLine row**.

## 28. `PessimisticLockScope.NORMAL` và `EXTENDED`

JPA có khái niệm locking scope:

```java
PessimisticLockScope.NORMAL
PessimisticLockScope.EXTENDED
```

Có thể cung cấp hint:

```java
Map<String, Object> hints = new HashMap<>();

hints.put(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
```

Đây là cách yêu cầu phạm vi mở rộng theo semantics của JPA, trong những trường hợp liên quan association tables/element collections.

Nhưng:

- `EXTENDED` không có nghĩa tự khóa đệ quy toàn bộ entity graph.
- Các row của related entities không mặc nhiên được khóa chỉ vì object association có trong Java graph.
- Một số provider/database có giới hạn hỗ trợ hoặc bỏ qua phần hint.
- Việc lock join table có thể khác với việc lock target entity rows.
- Nếu nghiệp vụ dựa vào hành vi chính xác, cần integration test tương ứng.

### NORMAL có nghĩa không khóa secondary tables?

Không nên diễn giải quá đơn giản. Một entity có thể được ánh xạ qua joined inheritance hoặc secondary tables; spec định nghĩa những phần state entity nào cần được bảo vệ theo phạm vi NORMAL. Cách SQL thực hiện có thể gồm nhiều bảng. Điều không được suy ra là mọi entity liên quan được khóa tự động.

## 29. Khóa bi quan và mức cách ly database

Lock mode và isolation level là hai khía cạnh khác nhau:

| Khái niệm | Điều điều khiển |
| --- | --- |
| `LockModeType.PESSIMISTIC_*` | Yêu cầu khóa trên entity/query trong transaction |
| READ COMMITTED | Quy tắc đọc dữ liệu committed |
| REPEATABLE READ | Bảo đảm đọc lặp của database theo implementation |
| SERIALIZABLE | Mức cách ly mạnh nhất theo semantics DB |
| MVCC | Cách DB giữ và cung cấp snapshot versions |
| DB constraints | Bảo vệ một số invariants độc lập với application code |

Một số database thực hiện READ COMMITTED bằng snapshot/MVCC, một số dùng shared locks nhiều hơn. Vì vậy:

- Với `PESSIMISTIC_WRITE`, plain SELECT vẫn có thể đọc committed snapshot.
- Với `PESSIMISTIC_READ`, provider phải bảo đảm ngữ nghĩa JPA dù DB không có shared-lock primitive.
- Lock modes không tự đổi toàn transaction thành SERIALIZABLE.
- Không suy rằng row lock ngăn phantom reads trong mọi predicate.
- Để kiểm tra correctness, phải biết actual isolation, DB engine và transaction schedule.

Đừng lấy một ví dụ PostgreSQL rồi áp nguyên si vào MySQL/InnoDB, SQL Server hoặc Oracle mà không kiểm tra dialect.

## 30. Deadlock: khóa đúng mode vẫn có thể gây lỗi

Giả sử A và B cần sửa hai InventoryItems #1 và #2.

```text
Transaction A                            Transaction B
WRITE lock Item 1                       WRITE lock Item 2
      │                                        │
Thử WRITE lock Item 2                  Thử WRITE lock Item 1
      │                                        │
A chờ B                                B chờ A
      └────────────── deadlock ────────────────┘
```

Database thường phát hiện deadlock và chọn một transaction làm nạn nhân để rollback. Exception cụ thể có thể là lock/transaction/database error.

### Phòng tránh

1. **Khóa theo thứ tự thống nhất**, ví dụ luôn ascending ID.
2. Giữ transaction ngắn.
3. Không gọi network API chậm trong lúc giữ khóa nếu có thể tránh.
4. Tránh khóa hàng loạt rows theo một query không có kế hoạch rõ.
5. Dùng timeout hợp lý và xử lý lỗi.
6. Sử dụng indexes cho điều kiện khóa để giảm số row bị scan/khóa.
7. Bảo đảm các code paths tranh chấp cùng tài nguyên tuân thủ quy tắc thứ tự.

Ví dụ:

```java
List<Long> sortedIds = requestedIds.stream()
    .distinct()
    .sorted()
    .toList();

for (Long id : sortedIds) {
    InventoryItem item = em.find(
        InventoryItem.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (item == null) {
        throw new IllegalArgumentException("Missing item " + id);
    }
}
```

Đây là một chiến lược giảm nguy cơ deadlock, không bảo đảm triệt tiêu mọi deadlock do indexes, foreign keys, triggers hoặc transaction khác có thứ tự khác.

## 31. Không giữ lock khi chờ thao tác ngoài database

Một anti-pattern:

```java
@Transactional
public void checkout(Long itemId) {
    InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );

    paymentProvider.chargeCard(); // Có thể mất nhiều giây.

    item.reserve(1);
}
```

Vấn đề:

- Lock row phải chờ external network call.
- Các requests khác bị block.
- Transaction giữ connection lâu.
- Timeout/deadlock và exhaustion dễ xảy ra.
- Nếu payment đã thành công nhưng DB rollback, external side effect không tự hoàn tác.

### Thiết kế thay thế

Tùy nghiệp vụ:

- Reservation ngắn trong database transaction, có expiry.
- Idempotent payment workflow.
- Transactional outbox để gửi event sau commit.
- Saga/compensation khi cần nhiều hệ thống.
- Trạng thái `PENDING`/`CONFIRMED` có điều kiện.
- Queue theo tài nguyên trong hệ thống cạnh tranh cao.

Khóa bi quan giải quyết một phần **concurrency ở DB**, không thể biến một transaction chứa nhiều dịch vụ ngoài DB thành atomic operation.

## 32. Spring `@Transactional` với pessimistic lock

Trong Spring, transaction thường do framework quản lý:

```java
@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserve(Long id, int quantity) {
        InventoryItem item = em.find(
            InventoryItem.class,
            id,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (item == null) {
            throw new IllegalArgumentException("Not found");
        }

        item.reserve(quantity);
    }
}
```

Ở đây Spring transaction interceptor commit/rollback sau khi method hoàn tất. Không tự gọi `em.getTransaction().begin()` hoặc `commit()` trên container-managed JTA/transaction-scoped EntityManager khi framework sở hữu transaction.

### Self-invocation có thể làm mất transaction

Trong mô hình proxy-based Spring `@Transactional`, gọi một annotated method từ **cùng instance** qua `this.method()` có thể không đi qua proxy, vì vậy transaction boundary như mong đợi có thể không tồn tại.

Nếu gọi pessimistic lock mà không có transaction đang active/joined, JPA có thể ném `TransactionRequiredException`.

Cần đặt transaction ở service entrypoint được gọi qua Spring proxy hoặc sử dụng transaction programmatic rõ ràng khi phù hợp.

### `readOnly = true` không thay thế READ lock

`@Transactional(readOnly = true)` của Spring mô tả ý định transaction và có thể ảnh hưởng provider flush behavior. Nó **không tự yêu cầu `PESSIMISTIC_READ` trên mọi query**.

Tương tự, `PESSIMISTIC_READ` không có nghĩa transaction phải được khai báo `readOnly = true`. Chúng là hai khái niệm khác.

## 33. Spring Data JPA `@Lock`

Repository có thể khai báo lock mode:

```java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
        "SELECT i FROM InventoryItem i " +
        "WHERE i.sku = :sku"
    )
    Optional<InventoryItem> findBySkuForUpdate(
        @Param("sku") String sku
    );
}
```

`@Lock` của Spring Data JPA giúp đặt JPA lock mode trên repository query. Nó không phải annotation của Jakarta Persistence chuẩn để gắn lên một method repository bất kỳ.

Caller cần transaction:

```java
@Transactional
public void reserveBySku(String sku, int quantity) {
    InventoryItem item = repository.findBySkuForUpdate(sku)
        .orElseThrow();

    item.reserve(quantity);
}
```

Nếu repository query được gọi ngoài transaction, hành vi có thể thất bại hoặc lock được nhả quá sớm theo transaction setup. Đừng giả định annotation repository tự tạo toàn bộ business transaction bảo vệ đọc–ghi.

### Query hint cho timeout

Spring Data có thể áp `@QueryHints` để truyền provider/JPA query hints. Nhưng hint namespace và việc DB thực thi timeout vẫn cần kiểm tra.

## 34. Trường hợp transaction propagation bất ngờ

Trong Spring, một service có thể:

```java
@Transactional
public void outer() {
    innerService.lockAndUpdate();
}
```

Nếu `innerService.lockAndUpdate` tham gia cùng transaction (`REQUIRED` mặc định), khóa thường sống tới khi **outer transaction** kết thúc, không phải khi method con return.

Với `REQUIRES_NEW`, có thể có transaction độc lập, làm thay đổi thời điểm giữ/nhả lock và visibility. Nếu transaction ngoài đang giữ một row lock mà transaction mới lại yêu cầu cùng row, có nguy cơ chờ/timeout ngay trong cùng luồng nghiệp vụ.

Do đó, khi debug “tại sao lock lâu?”, hãy xem:

- Transaction boundary thực tế.
- Propagation của method cha/con.
- Đường call qua Spring proxy.
- Transaction timeout.
- Khi nào commit/rollback thực sự xảy ra.
- Có external calls nằm giữa lúc lock và commit không.

**Lock lifetime theo transaction**, không theo tên method repository.

## 35. Pessimistic lock khác flush như thế nào?

`em.flush()` đồng bộ pending changes từ persistence context xuống DB.

`em.lock(item, PESSIMISTIC_WRITE)` yêu cầu database locking semantics.

Hai thao tác không thay thế nhau.

Ví dụ:

```java
em.getTransaction().begin();

InventoryItem item = em.find(
    InventoryItem.class, id
);

item.reserve(1);

em.flush(); // Ghi UPDATE, nhưng không phải yêu cầu
            // explicit pessimistic lock từ lúc đọc.

em.getTransaction().commit();
```

Nếu transaction khác đã đọc quantity trước đó, việc chỉ flush cuối cùng có thể vẫn khiến xung đột, tùy versioning và SQL. Để bảo vệ read-modify-write bằng pessimistic lock, cần lấy khóa **trước bước kiểm tra và quyết định**.

Ngược lại:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

không làm mọi thay đổi entity khác đã pending tự commit. Khóa giúp phối hợp concurrency; flush/commit vẫn quản lý ghi và xác nhận transaction.

## 36. FORCE_INCREMENT không phải commit

Với:

```java
em.getTransaction().begin();

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    id,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);

em.getTransaction().rollback();
```

Nếu transaction rollback thành công, các thay đổi version được thực hiện trong transaction đó không được commit bền vững. Tuy nhiên, Java object `order` có thể giữ state/version trong bộ nhớ không còn tương ứng database sau rollback.

**Rollback database không tự hoàn tác mọi thay đổi trên Java objects.** Sau rollback, không nên tái sử dụng managed/detached object từ transaction lỗi như nguồn state đã lưu. Dùng transaction/context mới khi cần đọc lại.

Điều này cũng giải thích vì sao gọi FORCE_INCREMENT rồi in `order.getVersion()` trước commit không chứng minh version mới đã được lưu.

## 37. FORCE_INCREMENT và entity không thay đổi field

Một test quan trọng:

1. Đọc version V của một PurchaseOrder đã commit.
2. Transaction A lấy `PESSIMISTIC_WRITE` rồi commit, không sửa field.
3. Đọc version sau A; **WRITE không bắt buộc bump version**.
4. Transaction B lấy `PESSIMISTIC_FORCE_INCREMENT` rồi commit, không sửa field.
5. Đọc version sau B; version phải phản ánh increment theo semantics hỗ trợ.

Điểm này thể hiện sự khác nhau thật giữa WRITE và FORCE_INCREMENT.

Không assert cụ thể rằng version luôn bằng V+1 nếu provider dùng timestamp hoặc chiến lược version khác. Với numeric Long trong một provider hỗ trợ, có thể kiểm tra giá trị mới lớn hơn trước hoặc khác trước theo test contract.

## 38. Pessimistic lock trên query trả nhiều entity

Ví dụ:

```java
List<InventoryItem> items = em.createQuery(
    "SELECT i FROM InventoryItem i " +
    "WHERE i.availableQuantity > 0 " +
    "ORDER BY i.id",
    InventoryItem.class
).setLockMode(LockModeType.PESSIMISTIC_WRITE)
 .setMaxResults(20)
 .getResultList();
```

Điều cần xem:

- Các rows nào thực sự được khóa?
- Database có khóa rows trong quá trình scan trước khi áp dụng LIMIT không?
- Có index phù hợp không?
- Provider có phải phát follow-on locking SQL vì dialect/joins/pagination không?
- Lock order có ổn định giữa các workers không?
- Một transaction có vô tình lock quá nhiều rows không?
- Query có thay đổi khi row bị transaction khác khóa không?

**Không mặc định `setMaxResults(20)` bảo đảm database chỉ ever khóa đúng 20 rows trong mọi query plan.**

Nếu nghiệp vụ là worker queue, nhiều DB có `SKIP LOCKED`/`NOWAIT` extensions, nhưng cách áp dụng qua JPA provider có thể khác nhau và không phải giải pháp portable. Không mô tả `PESSIMISTIC_WRITE` thông thường như thể nó luôn “tự động bỏ qua các row đang bị khóa”.

## 39. Khóa bi quan và pagination

Một màn hình danh sách có thể chỉ cần xem một page dữ liệu. Dùng pessimistic locks trên page query:

```java
query.setFirstResult(page * size);
query.setMaxResults(size);
query.setLockMode(LockModeType.PESSIMISTIC_READ);
```

có thể gây khóa nhiều row trong thời gian xử lý và tạo contention với writers. Nếu mục tiêu chỉ là render danh sách, thường nên dùng transaction/isolation và DTO projection phù hợp, không dùng row locks dài.

Nếu mục tiêu là “claim jobs” từ một hàng đợi, locking+pagination theo thứ tự có thể là một workflow riêng, cần xem:

- Multiple workers.
- Ordering and fairness.
- Lock timeout.
- SKIP LOCKED vendor behavior.
- Transaction length.
- Retry and idempotency.
- Unique claim status/lease.

Một UI page read và một job-claim operation không nên mặc định dùng cùng fetch/lock strategy.

## 40. Khi khóa cùng nhiều entity types

Giả sử chuyển tiền giữa hai Account:

```java
Account source = em.find(
    Account.class, sourceId, LockModeType.PESSIMISTIC_WRITE
);

Account target = em.find(
    Account.class, targetId, LockModeType.PESSIMISTIC_WRITE
);
```

Nếu transaction khác chuyển theo chiều ngược, nó có thể khóa target trước source và dẫn đến deadlock.

Một cách đặt thứ tự:

```java
Long firstId = Math.min(sourceId, targetId);
Long secondId = Math.max(sourceId, targetId);

Account first = em.find(
    Account.class, firstId, LockModeType.PESSIMISTIC_WRITE
);

Account second = firstId.equals(secondId)
    ? first
    : em.find(
        Account.class, secondId, LockModeType.PESSIMISTIC_WRITE
    );
```

Sau đó xác định lại vai trò source/target theo IDs rồi kiểm tra số dư và cập nhật trong cùng transaction.

**Tránh trộn lock order theo trình tự request** vì A→B và B→A có thể đảo ngược nhau. Với nhiều loại row khác nhau, cần quy ước thứ tự xuyên entity types, không chỉ sort ID bên trong một bảng.

## 41. Các đường ghi khác cũng phải tôn trọng invariant

Giả sử service A dùng pessimistic WRITE để reserve stock:

```java
InventoryItem item = em.find(
    InventoryItem.class, id, LockModeType.PESSIMISTIC_WRITE
);
item.reserve(1);
```

Nhưng service B chạy native SQL:

```sql
UPDATE inventory_items
SET available_quantity = available_quantity - 1
WHERE id = ?;
```

Một DB thông thường vẫn phối hợp row locks cho UPDATE trên cùng row, nhưng câu SQL B có thể **không kiểm tra quantity > 0**, không đi qua domain method, không tự tăng `@Version` theo JPA và không theo cùng policy audit.

Vì vậy, pessimistic lock ở một code path **không tự chứng minh tất cả invariants được giữ**. Cần:

- DB constraints.
- SQL conditional updates phù hợp.
- Transaction boundaries nhất quán.
- Versioning nếu có optimistic consumers.
- Domain validations.
- Audit/integration tests.
- Kiểm soát các batch jobs và external writers.

Tương tự, FORCE_INCREMENT trên root không tự bảo vệ child rows nếu một service khác sửa child mà bỏ qua aggregate rule.

## 42. Khóa và first-level cache

`EntityManager` duy trì một representative cho cùng persistent identity trong persistence context.

```java
InventoryItem a = em.find(
    InventoryItem.class, id
);

InventoryItem b = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

Thông thường `a == b` đối với cùng managed entity identity. Provider có thể thực hiện SQL để đáp ứng lock requirement mà vẫn trả cùng Java object.

Nhưng đừng nghĩ `find(..., lockMode)` là một “SELECT luôn lấy state mới” bỏ qua toàn bộ identity map.

Nếu entity đã stale:

- Provider có thể kiểm tra version khi lock và phát `OptimisticLockException`.
- Nếu cần reload state theo contract, cân nhắc `refresh(entity, lockMode)` khi transaction/entity hợp lệ.
- Không tiếp tục dùng context đã bị concurrency exception/rollback-only.

Khóa row ở database không tự sửa những object Java detached hoặc DTO đã được tạo trước đó.

## 43. Khóa và second-level cache

Nếu provider có second-level cache, các thao tác đọc thông thường có thể dùng cache. Nhưng pessimistic locking yêu cầu phối hợp với database locking/consistency; provider phải xử lý phù hợp và có thể phải truy cập DB để lấy khóa.

Không nên suy rằng:

- Một entity đang nằm trong second-level cache nghĩa là lock đã được cấp.
- `em.clear()` xóa toàn bộ second-level cache.
- Lock ở một transaction tự invalidates DTO cache của ứng dụng.
- Query cache luôn phối hợp đúng với mọi native SQL do ứng dụng khác chạy.

Nếu một batch job ngoài ORM cập nhật rows, cache invalidation và versioning cần được thiết kế riêng. Khi test concurrency, hãy xác định second-level cache có bật và có che mất SQL đọc hay không.

## 44. TransactionRequiredException và các lỗi dùng sai

Các thao tác khóa bi quan thường yêu cầu active transaction mà persistence context tham gia.

Ví dụ sai:

```java
EntityManager em = emf.createEntityManager();

InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);

// Không begin transaction.
```

Tùy API/provider, có thể ném `TransactionRequiredException`.

Các sai sót khác:

- Gọi `em.lock` trên detached entity → có thể `IllegalArgumentException`.
- Gọi lock mode không phù hợp với query scalar → `IllegalStateException` theo contract áp dụng.
- Provider/database không hỗ trợ yêu cầu locking → exception hoặc fallback tùy semantics.
- Hàng không tồn tại → `find` trả null (không có row để khóa).
- Lock timeout/deadlock → exceptions tùy transaction-level failure.
- Entity versioned stale → có thể `OptimisticLockException`.
- Transaction đã rollback-only → các thao tác tiếp theo có thể thất bại.

Không nên try/catch hết rồi trả “không tìm thấy hàng”, vì lock failure khác với missing entity về mặt nghiệp vụ.

## 45. Xử lý exception và rollback

Một mẫu resource-local transaction:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (item == null) {
        throw new IllegalArgumentException("Item not found");
    }

    item.reserve(quantity);

    em.getTransaction().commit();
} catch (RuntimeException failure) {
    if (em.getTransaction().isActive()) {
        try {
            em.getTransaction().rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }

    throw failure;
} finally {
    em.close();
}
```

Mẫu trên rollback khi transaction còn active và đảm bảo close EntityManager. Nó không tự phân loại lock timeout, deadlock, optimistic mismatch hay constraint failure. Ở tầng ngoài, một exception translator hoặc service policy có thể chuyển lỗi thành:

- Conflict/Retryable error (theo contract).
- “Tài nguyên đang được xử lý, thử lại” nếu lock wait timeout.
- Concurrency conflict nếu version mismatch.
- Validation error nếu insufficient stock.
- Internal error nếu provider/database không hỗ trợ cấu hình.

Không tự động retry mọi lock error. Nếu transaction đã thực hiện side effects ngoài database, retry có thể nhân đôi tác động; cần idempotency.

## 46. Retry sau lock timeout có khác retry sau optimistic conflict?

Có.

### Lock timeout

Ý nghĩa thường là không lấy được lock trong khoảng thời gian/phạm vi được hỗ trợ. Một lần retry sau backoff trong **transaction mới** có thể thành công khi transaction kia đã hoàn tất.

Nhưng vẫn phải kiểm tra state mới vì inventory/reservation có thể đã đổi.

### Optimistic conflict

Ý nghĩa thường là transaction dùng version stale. Cần đọc lại phiên bản mới và xác định business intent còn hợp lệ. Retry mù việc ghi một giá trị cũ có thể gây lost update về nghiệp vụ.

### Deadlock

Database đã chọn rollback một transaction. Retry có thể phù hợp nếu operation idempotent và lock order/transaction size được cải thiện. Không nên chỉ lặp vô hạn mà không xử lý nguyên nhân contention.

### Không retry bằng cùng EntityManager lỗi

Sau một transaction đã rollback hoặc bị đánh dấu rollback-only, không dùng lại managed graph từ lần thử thất bại để quyết định nghiệp vụ. Tạo transaction/context mới và đọc lại state.

## 47. Một chiến lược retry có giới hạn

Ví dụ ý tưởng:

```java
public void reserveWithRetry(
        EntityManagerFactory emf,
        Long itemId,
        int quantity,
        int maxAttempts) {

    if (maxAttempts < 1) {
        throw new IllegalArgumentException("Invalid maxAttempts");
    }

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            InventoryItem item = em.find(
                InventoryItem.class,
                itemId,
                LockModeType.PESSIMISTIC_WRITE
            );

            if (item == null) {
                throw new IllegalArgumentException("Not found");
            }

            item.reserve(quantity);
            em.getTransaction().commit();
            return;
        } catch (RuntimeException failure) {
            if (em.getTransaction().isActive()) {
                try {
                    em.getTransaction().rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }

            if (!isRetryableLockFailure(failure)
                    || attempt == maxAttempts) {
                throw failure;
            }

            // Có thể backoff/jitter ở tầng retry ngoài transaction.
        } finally {
            em.close();
        }
    }
}
```

`isRetryableLockFailure` là helper của ứng dụng, phải dựa vào exception chain và provider-specific translation. Đoạn code chỉ minh họa **transaction mới cho mỗi attempt**.

Trong hệ thống thật, thêm:

- Idempotency key cho command đặt chỗ.
- Giới hạn tổng thời gian retry.
- Backoff/jitter ngoài transaction.
- Logging/metrics cho contention.
- Không retry business validation như insufficient stock.
- Không tạo side effect ngoài DB trước khi commit.
- Phân biệt optimistic version conflict và lock acquisition failure.

## 48. Test cơ bản: lock trong transaction hợp lệ

Một integration test sử dụng EntityManagerFactory:

```java
@Test
void canAcquireWriteLockOnExistingItem() {
    Long id = seededItemId;

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item = em.find(
            InventoryItem.class,
            id,
            LockModeType.PESSIMISTIC_WRITE
        );

        assertNotNull(item);
        assertEquals(id, item.getId());

        item.reserve(1);

        em.getTransaction().commit();
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
```

Fixture `seededItemId` phải được tạo trong một transaction đã commit. Test này xác nhận API được provider/database hỗ trợ ở mức cơ bản. Nó **chưa kiểm tra tranh chấp** giữa hai transactions.

Sau commit, nên đọc lại bằng EntityManager mới để assert quantity và version nếu cần.

## 49. Test concurrency: hai transaction tranh một WRITE lock

Một test đúng mục tiêu cần **hai database transactions độc lập**. Cách triển khai có thể dùng hai Java threads, mỗi thread có một EntityManager riêng. Không chia sẻ một EntityManager giữa các threads vì EntityManager không thread-safe.

Mô hình:

```text
Main/test thread                    Worker thread
       │                                 │
Begin Tx A                              │
Get PESSIMISTIC_WRITE #42               │
Signal A_HAS_LOCK                       │
       │                          Begin Tx B
       │                          Attempt PESSIMISTIC_WRITE #42
       │                                 │
       │                          Block / timeout (theo DB)
Commit Tx A                             │
       │                          Acquire or fail
       │                          Commit/Rollback Tx B
       ▼                                 ▼
Verify final DB state with fresh EntityManager
```

Một harness có thể dùng `ExecutorService` và `CountDownLatch`, nhưng **không dùng một latch khiến A chờ B hoàn tất trong khi B đang chờ lock của A**, vì chính test tạo deadlock.

### Pseudocode harness

```java
EntityManager emA = emf.createEntityManager();

ExecutorService pool =
    Executors.newSingleThreadExecutor();

CountDownLatch workerStarted =
    new CountDownLatch(1);

try {
    emA.getTransaction().begin();

    emA.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );

    Future<String> future = pool.submit(() -> {
        EntityManager emB = emf.createEntityManager();

        try {
            emB.getTransaction().begin();

            workerStarted.countDown();

            emB.find(
                InventoryItem.class,
                itemId,
                LockModeType.PESSIMISTIC_WRITE
            );

            emB.getTransaction().commit();
            return "acquired";
        } catch (RuntimeException failure) {
            if (emB.getTransaction().isActive()) {
                emB.getTransaction().rollback();
            }
            return "failed: " + failure.getClass().getName();
        } finally {
            emB.close();
        }
    });

    assertTrue(workerStarted.await(5, TimeUnit.SECONDS));

    // Không chờ future hoàn tất trong lúc giữ A lock.
    emA.getTransaction().commit();

    String outcome = future.get(10, TimeUnit.SECONDS);

    assertNotNull(outcome);
    // Assertions cụ thể về blocking/timeout cần gắn
    // với DB isolation, provider và lock-timeout config.
} finally {
    if (emA.getTransaction().isActive()) {
        emA.getTransaction().rollback();
    }

    emA.close();
    pool.shutdownNow();
}
```

Ví dụ này kiểm tra việc hai transaction truy cập cùng row với locking modes, nhưng **không chứng minh chính xác B đã block bao nhiêu mili-giây**. Với timing tests nghiêm túc, cần thêm signal sau acquire, hợp đồng timeout cụ thể, kiểm soát isolation và một DB thật hỗ trợ locking semantics.

Không chạy concurrency test trên một database in-memory/single-connection giả lập nếu nó không phản ánh cách production xử lý row locks.

## 50. Test READ và WRITE phải phụ thuộc mục tiêu

Nếu bạn muốn xác minh nhiều `PESSIMISTIC_READ` có thể chạy song song:

- Chỉ assert điều đó khi DB/provider thật có **shared-lock compatibility** được tài liệu hóa.
- Không coi đó là yêu cầu portable của JPA trên mọi DB.
- Nếu provider phải dùng exclusive lock để bảo đảm READ semantics, hai READ có thể cạnh tranh.

Nếu mục tiêu là xác minh WRITE bảo vệ update:

1. Seed một InventoryItem có quantity=1.
2. Chạy hai transaction reserve(1) theo timeline kiểm soát.
3. Cả hai đường code dùng WRITE lock trước khi kiểm tra quantity.
4. Chỉ một transaction được phép reserve thành công; transaction sau quan sát quantity=0 và nhận business validation failure, hoặc thất bại do timeout.
5. Kiểm tra database quantity không âm và số reservation committed phù hợp.

**Đó là integration test nghiệp vụ có giá trị hơn việc chỉ assert có SQL `FOR UPDATE` trong log.** SQL syntax và scheduling có thể khác, nhưng bất biến inventory phải được giữ.

## 51. Test FORCE_INCREMENT: chỉ khóa, không sửa field

Một test đặc trưng:

```java
@Test
void forceIncrementChangesVersionWithoutFieldMutation() {
    Long id = seededVersionedOrderId;

    Long before = readCommittedVersion(id);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            id,
            LockModeType.PESSIMISTIC_FORCE_INCREMENT
        );

        assertNotNull(order);

        // Không thay đổi status hay field nào.

        em.getTransaction().commit();
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }

    Long after = readCommittedVersion(id);

    assertNotNull(after);
    assertNotEquals(before, after);
}
```

`readCommittedVersion` là helper dùng **EntityManager mới sau transaction** để lấy version, không đọc lại từ managed object cũ. Với numeric version Long, thường có thể assert sau > trước; test contract cụ thể phụ thuộc provider/version strategy.

### So sánh với WRITE

Viết một test tương tự chỉ dùng `PESSIMISTIC_WRITE` mà không sửa field. Khi đó **không bắt buộc phải có version increment**. Mục tiêu của test là chứng minh sự khác biệt về yêu cầu version semantics.

## 52. Test timeout và exception classification

Một test chuyên biệt:

1. Transaction A giữ WRITE lock.
2. Transaction B yêu cầu WRITE lock với hint timeout.
3. B có thể ném lock timeout/pessimistic exception tùy provider/DB.
4. B rollback/cleanup.
5. A commit hoặc rollback.
6. Đọc lại bằng EntityManager mới, kiểm tra DB consistency.

Không nên dùng:

```java
assertThrows(
    LockTimeoutException.class,
    () -> acquireWithTimeout()
);
```

làm assertion portable tuyệt đối trên mọi database. Provider có thể không hỗ trợ timeout hint chính xác hoặc DB phân loại thành transaction-level failure. Với test gắn production stack, assert exception translator và thời gian giới hạn theo contract đã xác minh.

### Vì sao không dùng sleep cố định?

Lệnh `Thread.sleep(100)` để “chắc rằng B đã lock” dễ gây flaky test dưới CI load. Dùng latch/barrier và một scheduler rõ ràng để điều khiển điểm A đã lock trước khi B bắt đầu thử, rồi đo behavior theo kỳ vọng của DB.

## 53. Khóa WRITE có bảo đảm số lượng tồn kho luôn đúng?

Không nếu còn đường ghi vi phạm nghiệp vụ.

Ví dụ:

```sql
UPDATE inventory_items
SET available_quantity = -100
WHERE id = 42;
```

Một transaction có lock khác không thể ngăn mọi lỗi code được chạy sau khi khóa được giải phóng. Vì vậy ngoài lock:

- Domain method phải validate requested amount.
- Database CHECK constraint phải bảo vệ giá trị tối thiểu.
- Những worker khác phải dùng transaction đúng.
- Nếu có reservations records, cần constraints/idempotency key.
- Nếu có optimistic clients, version phải được cập nhật đúng.
- Có thể dùng atomic conditional UPDATE cho throughput cao.

Pessimistic locking là một công cụ điều phối concurrency, **không thay thế schema constraints và business rules**.

## 54. Có cần khóa mọi lần đọc dữ liệu quan trọng không?

Không. Một dashboard thống kê không cần giữ WRITE lock lên 10.000 records chỉ để hiển thị số lượng. Một API GET thông thường cũng thường không cần READ lock trên mọi entity.

Chọn chiến lược bằng câu hỏi:

| Câu hỏi | Hướng lựa chọn |
| --- | --- |
| Chỉ hiển thị dữ liệu đã commit, chấp nhận thay đổi giữa requests? | Query thông thường + DB isolation/DTO |
| Cần đọc một entity ổn định trong một transaction, không có ý định sửa row? | Cân nhắc PESSIMISTIC_READ |
| Đọc row rồi kiểm tra và cập nhật trong cùng transaction, xung đột cao? | Cân nhắc PESSIMISTIC_WRITE |
| Cần WRITE lock và bắt buộc báo thay đổi qua root version dù row root không dirty? | PESSIMISTIC_FORCE_INCREMENT |
| Ít xung đột, chấp nhận retry sau conflict? | @Version/optimistic locking có thể tốt hơn |
| Chỉ cần decrement quantity nguyên tử? | Conditional UPDATE có thể đơn giản hơn |
| Cần ngăn đặt chỗ trùng khi row chưa tồn tại? | Unique constraint/guard row/serializable policy |
| Hàng đợi nhiều workers cần claim jobs? | DB-specific SKIP LOCKED/lease strategy khi phù hợp |

Không có một mode tốt nhất cho mọi tình huống; lựa chọn tùy business invariant và workload.

## 55. Một nguyên tắc quan trọng: thứ tự “lock → read → decide → write”

Mẫu nguy hiểm:

```text
Read state
Perform expensive calculations
Acquire lock
Write based on old state
Commit
```

Dù cuối cùng có lock, quyết định đã dựa trên dữ liệu trước lúc khóa.

Mẫu dễ suy luận hơn:

```text
Begin transaction
Acquire appropriate lock
Read/refresh authoritative state
Validate against current state
Apply domain change
Commit
Release lock
```

Nếu workflow tính toán đắt, có thể tính trước những phần **không phụ thuộc state có thể đổi**, rồi lấy lock, đọc lại và xác minh những tiền đề cần thiết trước khi commit.

Đừng giữ khóa trong suốt quá trình tính toán dài nếu có thể giảm phạm vi critical section mà vẫn đúng nghiệp vụ.

## 56. Nhiều transaction cùng dùng FORCE_INCREMENT có thể gây contention

Ví dụ một dashboard query Order bằng FORCE_INCREMENT “để chắc chắn mới nhất”:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    id,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

Nếu hàng nghìn lần GET cùng thực hiện, nó có thể:

- Lấy exclusive locks.
- Tăng version dù không có business change.
- Gây transaction contention.
- Làm optimistic clients thường xuyên gặp conflict giả về mặt nghiệp vụ.
- Tăng SQL writes/WAL/replication traffic.
- Làm cache invalidation thường xuyên hơn.

**FORCE_INCREMENT là một thao tác có side effect lên version**, không phải một mode để đọc “độ tin cậy cao nhất” miễn phí.

Với GET request, thường cần query/isolation/ETag policy phù hợp thay vì luôn tăng version.

## 57. Khóa trên graph và thứ tự các thao tác con

Giả sử hai services chỉnh cùng Order:

```text
Service A:
  lock Order
  update OrderLine A

Service B:
  update OrderLine B
  lock Order
```

Dù cả hai cuối cùng lấy lock Order, thứ tự khác nhau có thể gây deadlock hoặc khiến một service đã đổi child trước khi bảo vệ root.

Nếu aggregate invariant yêu cầu root lock:

1. Luôn lấy khóa root trước các child changes.
2. Xác định một lock order chung.
3. Xác minh child thuộc đúng root.
4. Kiểm tra version/constraints.
5. Giữ transaction ngắn.
6. Nếu dùng FORCE_INCREMENT, đừng bỏ qua optimistic policy ở client.
7. Không cho các đường ghi trực tiếp vào child tránh coordinator một cách tùy tiện.

Đó là **một convention của ứng dụng**, không phải quy tắc JPA tự động áp cho mọi mapped association.

## 58. Những hiểu nhầm thường gặp

### Hiểu nhầm 1: READ nghĩa là mọi transaction khác vẫn đọc song song

Không portable. Provider có thể phải dùng khóa mạnh hơn shared lock trên DB không hỗ trợ shared locking phù hợp.

### Hiểu nhầm 2: WRITE chặn mọi SELECT khác

Không đúng trong nhiều DB MVCC. Plain SELECT có thể đọc snapshot đã commit.

### Hiểu nhầm 3: FORCE_INCREMENT chỉ là alias của WRITE

Không. FORCE_INCREMENT còn yêu cầu tăng version của entity có `@Version`.

### Hiểu nhầm 4: Dùng FORCE_INCREMENT trên entity không versioned vẫn tăng “version ảo”

Không có cơ chế JPA portable như vậy. Dùng entity versioned.

### Hiểu nhầm 5: Lấy WRITE lock rồi commit ở method A, sau đó method B update vẫn được bảo vệ

Khóa sống trong transaction A. Sau khi commit, lock thường đã được nhả.

### Hiểu nhầm 6: `flush()` tương đương `lock()`

Flush đồng bộ pending changes; lock yêu cầu cơ chế concurrency protection. Hai API phục vụ mục đích khác.

### Hiểu nhầm 7: Khóa root tự khóa mọi collections/child entities

Không. Lock scope và association mappings phải được phân tích; EXTENDED cũng không đồng nghĩa khóa đệ quy toàn graph.

### Hiểu nhầm 8: Khóa một row có thể ngăn người khác INSERT row mới thỏa predicate

Không bảo đảm phantom prevention. Cần constraint, guard row hoặc isolation/locking strategy phù hợp.

### Hiểu nhầm 9: `@Transactional(readOnly = true)` nghĩa là PESSIMISTIC_READ

Không. Đó là Spring transaction hint, không tự đặt JPA LockModeType.

### Hiểu nhầm 10: `PESSIMISTIC_READ` luôn đủ cho read-modify-write

Không lý tưởng. Shared lock upgrades có thể gây deadlock và vẫn cần exclusive write. Thường chọn WRITE từ đầu khi có ý định cập nhật.

### Hiểu nhầm 11: Lock timeout hint được mọi DB thực thi chính xác

Không. Provider/dialect có thể bỏ qua hoặc áp dụng khác.

### Hiểu nhầm 12: Mọi lock failure là `PessimisticLockException`

Không. Có `LockTimeoutException`, optimistic version mismatch, deadlock/serialization/provider exceptions.

### Hiểu nhầm 13: FORCE_INCREMENT tăng version ngay tại Java getter

Thời điểm tăng/đồng bộ phụ thuộc provider; kiểm tra sau commit bằng context mới.

### Hiểu nhầm 14: Native SQL UPDATE tự tuân theo `@Version`

Không. Native DML phải tự có version predicate/increment nếu nghiệp vụ cần.

### Hiểu nhầm 15: Một lần lấy khóa có thể giữ qua HTTP request sau

Không nên; khóa thuộc database transaction, không thuộc object DTO hoặc HTTP session.

### Hiểu nhầm 16: Cứ dùng WRITE lock là không có deadlock

Sai. Hai transaction lock nhiều rows theo thứ tự khác nhau vẫn có thể deadlock.

### Hiểu nhầm 17: Lock concurrency xong thì không cần constraint

Không. Constraints và invariants DB vẫn là lớp bảo vệ dữ liệu quan trọng.

### Hiểu nhầm 18: EntityManager có thể dùng chung giữa hai threads để test lock

Không. EntityManager không thread-safe; mỗi transaction/thread dùng context riêng.

### Hiểu nhầm 19: Một query trả scalar COUNT có thể đặt WRITE lock và coi như toàn tập row được khóa

Không phải semantics phù hợp cho query scalar. Phải thiết kế locking trên entities/rows hoặc chiến lược DB khác.

### Hiểu nhầm 20: Retry sau lock error bằng cùng persistence context

Không an toàn khi transaction đã thất bại/rollback-only. Dùng transaction và context mới.

## 59. Bài tập thực hành

### Bài tập 1: Chọn mode cho đọc ổn định

Một transaction cần kiểm tra trạng thái Book trong lúc chạy validation nhưng không có ý định sửa Book.

**Đáp án gợi ý:** `PESSIMISTIC_READ` nếu thật sự cần ngăn dirty/non-repeatable reads ở mức entity và chấp nhận chi phí khóa. Nếu chỉ là GET thông thường, query dưới DB isolation có thể đủ.

### Bài tập 2: Chọn mode cho tồn kho

Hai checkout requests cùng muốn mua món hàng cuối.

**Đáp án gợi ý:** `PESSIMISTIC_WRITE` khi tải InventoryItem trước khi đọc quantity và reserve, trong một transaction ngắn. Kết hợp CHECK constraint/idempotency.

### Bài tập 3: Chọn mode cho aggregate root

Transaction thay đổi OrderLine nhưng không sửa field của Order root. Client khác dùng root version để kiểm tra xung đột.

**Đáp án gợi ý:** `PESSIMISTIC_FORCE_INCREMENT` trên versioned Order root nếu đồng thời cần exclusive pessimistic lock và bump version. Mọi đường ghi child cần tuân thủ aggregate convention.

### Bài tập 4: READ lock giữa hai transactions

A đang giữ READ lock; B muốn READ lock cùng row.

**Câu hỏi:** Có chắc B không chờ không?

**Đáp án:** Không. Compatibility phụ thuộc database/provider; JPA cho phép implementation chọn khóa mạnh hơn khi cần.

### Bài tập 5: WRITE và plain SELECT

A giữ WRITE lock, B chạy SELECT thường.

**Câu hỏi:** B bắt buộc block không?

**Đáp án:** Không. B có thể đọc committed snapshot cũ ở DB MVCC, theo isolation.

### Bài tập 6: Không có transaction

`em.find(Book.class, id, PESSIMISTIC_WRITE)` được gọi trên resource-local EntityManager chưa `begin`.

**Câu hỏi:** Vấn đề?

**Đáp án:** Pessimistic locking cần active joined transaction; có thể nhận `TransactionRequiredException`.

### Bài tập 7: FORCE_INCREMENT không sửa field

A lấy FORCE_INCREMENT trên Book version 5, không gọi setter, rồi commit thành công.

**Câu hỏi:** Version có phải thay đổi không?

**Đáp án:** Có yêu cầu version increment theo mode với entity versioned; timing/giá trị cụ thể tùy provider/version strategy.

### Bài tập 8: WRITE không sửa field

A lấy WRITE trên Book version 5, không sửa field, commit.

**Câu hỏi:** Version bắt buộc tăng không?

**Đáp án:** Không. WRITE không có yêu cầu force increment.

### Bài tập 9: So sánh optimistic force increment

**Câu hỏi:** `OPTIMISTIC_FORCE_INCREMENT` khác `PESSIMISTIC_FORCE_INCREMENT` thế nào?

**Đáp án:** Cả hai yêu cầu bump version, nhưng chỉ PESSIMISTIC variant yêu cầu pessimistic write locking semantics.

### Bài tập 10: Lock timeout

B không lấy được lock của A trước timeout.

**Câu hỏi:** Có chắc ném `LockTimeoutException` không?

**Đáp án:** Không. Có thể khác giữa statement-level và transaction-level failures, driver/provider/DB và hint support. Cần phân loại đúng exception chain.

### Bài tập 11: Shared-to-exclusive upgrade

A và B cùng lấy READ rồi cả hai update cùng row.

**Câu hỏi:** Rủi ro?

**Đáp án:** Có thể gây lock conversion wait/deadlock ở DB có shared locks. Nếu biết trước sẽ ghi, dùng WRITE lock sớm hơn.

### Bài tập 12: Phantom

Query thấy chưa có reservation cho ngày D. A khóa một Booking khác rồi INSERT reservation.

**Câu hỏi:** Đã ngăn duplicate reservation chưa?

**Đáp án:** Chưa. Cần constraint `UNIQUE(room_id,date)` hoặc guard-row/serializable policy phù hợp.

### Bài tập 13: Collection

Order được khóa FORCE_INCREMENT; transaction khác trực tiếp cập nhật OrderLine mà không khóa Order.

**Câu hỏi:** Có chắc bị chặn không?

**Đáp án:** Không. Root lock/version chỉ phối hợp với những workflow tôn trọng locking convention và những row thực sự bị khóa.

### Bài tập 14: Transaction propagation

`@Transactional(REQUIRES_NEW)` ở method con cố khóa row mà transaction ngoài vẫn đang giữ.

**Câu hỏi:** Có thể xảy ra gì?

**Đáp án:** Transaction con có thể chờ/timeout trên row lock còn được transaction ngoài giữ. Cần xem propagation và thứ tự transaction.

### Bài tập 15: Native SQL

Bulk native UPDATE thay quantity nhưng không tăng version.

**Câu hỏi:** FORCE_INCREMENT từ một workflow khác có đủ bảo vệ mọi lần ghi không?

**Đáp án:** Không. Native SQL phải có điều kiện/constraint/version strategy phù hợp; không tự kế thừa per-entity optimistic semantics.

### Bài tập 16: Test concurrency

**Yêu cầu:** Kiểm tra hai requests không cùng reserve thành công một item quantity=1.

**Gợi ý:** Seed/commit item, chạy hai transactions ở hai EntityManagers, cả hai khóa WRITE trước khi đọc, đảm bảo chỉ một thành công và quantity cuối không âm. Dùng latch để sắp schedule; không share EntityManager.

### Bài tập 17: Deadlock

A lock item 1 rồi 2, B lock item 2 rồi 1.

**Câu hỏi:** Cách giảm nguy cơ?

**Đáp án:** Thống nhất lock order theo ID/tài nguyên, giảm thời gian giữ khóa và giới hạn transaction scope.

### Bài tập 18: External API

Một transaction giữ WRITE lock rồi chờ payment API 8 giây.

**Câu hỏi:** Vì sao không phù hợp?

**Đáp án:** Gây lock contention và giữ DB connection lâu, side effect payment không tự rollback. Dùng reservation/outbox/idempotent workflow phù hợp.

### Bài tập 19: READ trên một GET endpoint

API GET có 1000 Book, chỉ cần DTO danh sách.

**Câu hỏi:** Có nên khóa READ mọi Book không?

**Đáp án:** Thường không cần; có thể tăng contention nặng. Dùng projection/isolation và consistency policy phù hợp.

### Bài tập 20: Lock scope EXTENDED

**Câu hỏi:** EXTENDED có tự khóa toàn bộ Customer, OrderLine và Payment entities được tham chiếu từ Order không?

**Đáp án:** Không. EXTENDED có semantics cụ thể với association/collection tables; không phải recursive graph locking.

## 60. Checklist chọn khóa trong production

Trước khi thêm một `PESSIMISTIC_*` lock:

1. **Business invariant nào** cần bảo vệ?
2. Đang bảo vệ **một row, nhiều rows hay một điều kiện không có row**?
3. Có thật cần pessimistic lock, hay `@Version`/conditional UPDATE đủ?
4. Transaction bắt đầu trước khi lấy lock chưa?
5. Persistence context đã joined transaction chưa?
6. Có chọn mode **trước khi đọc state để quyết định** không?
7. Với thao tác đọc, READ lock có cần thiết hơn DB isolation/snapshot không?
8. Với thao tác ghi, WRITE có phù hợp hơn READ để tránh lock upgrade không?
9. Nếu cần root version bump dù root không dirty, có dùng FORCE_INCREMENT trên versioned entity không?
10. Có phân biệt FORCE_INCREMENT với OPTIMISTIC_FORCE_INCREMENT không?
11. Có kiểm soát version type/mapping và optimistic conflict không?
12. Lock có thể block plain SELECT trên DB này không, hay MVCC cho đọc snapshot?
13. Có đủ index để database tránh scan quá nhiều rows không?
14. Lock order có thống nhất giữa mọi transaction không?
15. Có external call hoặc xử lý dài nằm trong critical section không?
16. Query có pagination/fetch join/collection làm thay đổi phạm vi lock không?
17. Có phantom/invariant cần unique constraint hoặc guard row không?
18. Có dùng lock scope EXTENDED thực sự cần thiết và được provider hỗ trợ không?
19. Hint timeout đã kiểm tra trên database/dialect production chưa?
20. Exception mapping có phân biệt timeout, deadlock, optimistic conflict và not-found không?
21. Sau failure có rollback/đóng context đúng không?
22. Retry có dùng transaction/context mới và kiểm tra state mới không?
23. Nếu dùng Spring, @Transactional có thực sự đi qua proxy và đúng propagation không?
24. Có con đường native SQL/batch khác bypass version/domain rules không?
25. Có transaction khác không tôn trọng root locking convention khi sửa child không?
26. Có tránh dùng FORCE_INCREMENT trên read-only GET không?
27. Có integration test hai EntityManagers độc lập không?
28. Có test invariant với dữ liệu đã commit và context mới không?
29. Có test số câu SQL, thời gian chờ, deadlocks và throughput dưới tải không?
30. Có observability cho lock wait/timeout/deadlock tại DB và ứng dụng không?

Checklist này không yêu cầu mọi service đều dùng khóa. Mục tiêu là để mỗi lock **có lý do nghiệp vụ**, có thời hạn transaction rõ và được kiểm chứng bằng database/provider cụ thể.

## Kết luận

**`PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` và `PESSIMISTIC_FORCE_INCREMENT` khác nhau trước hết ở ý định bảo vệ và tác động lên version.**

- **`PESSIMISTIC_READ`** dành cho thao tác đọc cần bảo vệ theo ngữ nghĩa ngăn dirty/non-repeatable reads. Nó có thể dùng shared lock nếu database hỗ trợ, nhưng JPA không bảo đảm mọi READ locks luôn cùng được cấp.
- **`PESSIMISTIC_WRITE`** dành cho thao tác đọc–kiểm tra–ghi trong một transaction, thường sử dụng khóa độc quyền phù hợp để phối hợp writers. Nó không có nghĩa mọi plain SELECT khác đều phải chờ trong cơ sở dữ liệu MVCC.
- **`PESSIMISTIC_FORCE_INCREMENT`** có semantics WRITE và còn yêu cầu tăng version của **entity có `@Version`**, ngay cả khi không có field update trên entity root. Nó hữu ích khi cần bảo vệ một aggregate operation và báo thay đổi qua optimistic version cho các workflow khác.

Cả ba mode đều phải được dùng trong **active joined transaction**, có thể phát sinh lock wait/timeout/deadlock hoặc optimistic version conflict, và không tự khóa mọi row trong graph hay ngăn phantom inserts. Lock scope, timeout và SQL cụ thể phụ thuộc DB/provider; không nên dựa vào một chuỗi `SELECT ... FOR UPDATE` làm hợp đồng portability.

Khi triển khai, hãy chọn khóa **trước khi đọc state để quyết định**, giữ transaction ngắn, thống nhất thứ tự khóa, kết hợp database constraints và kiểm thử concurrency bằng các EntityManagers độc lập. Đối với việc chỉ hiển thị dữ liệu, projection/transaction isolation thường thích hợp hơn lấy khóa dài. Đối với side effects bên ngoài DB, nên dùng workflow idempotent/outbox/reservation chứ không giữ row lock trong lúc chờ network.

Hãy luôn hỏi bốn câu: **“Tôi chỉ cần đọc ổn định hay chuẩn bị cập nhật? Tôi đang khóa row nào và trong transaction nào? Tôi có cần tăng version dù row không dirty không? Tôi đã kiểm thử contention/timeout trên database thực tế chưa?”**. Trả lời rõ sẽ giúp chọn đúng `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` hoặc `PESSIMISTIC_FORCE_INCREMENT` mà không biến concurrency control thành gánh nặng hiệu năng.
