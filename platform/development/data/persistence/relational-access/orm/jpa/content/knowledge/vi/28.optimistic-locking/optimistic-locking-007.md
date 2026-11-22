# Xác định thời điểm lỗi khóa lạc quan có thể xuất hiện

Trong JPA, **khóa lạc quan** (*optimistic locking*) giúp phát hiện tình huống hai transaction cùng làm việc trên một entity nhưng một transaction đã thay đổi dữ liệu trước khi transaction còn lại ghi phiên bản cũ xuống database. Cơ chế này thường được triển khai thông qua thuộc tính `@Version` trên entity.

Câu hỏi quan trọng không chỉ là **“xung đột xảy ra khi nào?”** mà còn là **“JPA có thể phát hiện và báo lỗi ở dòng code nào?”**. Hai thời điểm đó có thể khác nhau.

Ví dụ:

```java
Book book = em.find(Book.class, 42L);

book.rename("Tên mới");

// Đến đây có thể chưa có SQL UPDATE.

em.flush(); // Có thể ném OptimisticLockException.
```

Nếu không gọi `flush()` tường minh:

```java
book.rename("Tên mới");

em.getTransaction().commit(); // Lỗi có thể xuất hiện tại đây.
```

Trong một số tình huống khác, lỗi có thể xuất hiện ngay khi gọi `merge()` một detached entity đã lỗi thời, khi yêu cầu `lock()` với optimistic lock mode, hoặc ở một câu JPQL/Criteria/native query làm persistence context **auto-flush** trước khi truy vấn.

**Không có một vị trí duy nhất và cố định trong Java code mà mọi provider bắt buộc phải ném `OptimisticLockException`.** Chuẩn JPA cho phép một số kiểm tra phiên bản diễn ra ngay tại thao tác, tại flush, hoặc được trì hoãn tới lúc transaction commit. Khác biệt còn phụ thuộc chiến lược provider, trạng thái entity, cách truy cập DB và transaction manager.

Bài **“Xác định thời điểm lỗi khóa lạc quan có thể xuất hiện”** thuộc chương **Khóa lạc quan** trong chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung tập trung vào timeline thực thi, dấu hiệu xung đột, các điểm có thể ném exception, cách kiểm thử có hai transaction độc lập, chiến lược xử lý và các trường hợp không được bảo vệ bởi `@Version`.

Các ví dụ sử dụng Java 17+, Jakarta Persistence (`jakarta.persistence`). Dự án JPA cũ sử dụng package `javax.persistence`; những class exception tương ứng có tên gần giống, nhưng cần import thống nhất theo phiên bản. Các ví dụ về Spring được ghi rõ là framework-specific, không phải API JPA chuẩn.

---

## 1. Xung đột xảy ra trước khi ứng dụng biết có xung đột

Giả sử bảng `books` chứa:

| id | title | price | version |
| ---: | --- | ---: | ---: |
| 42 | JPA căn bản | 120000.00 | 5 |

Hai transaction tải Book #42:

```text
                  Transaction A                     Transaction B
                       │                                  │
T1            Đọc Book #42, version=5                       │
                       │                          Đọc Book #42, version=5
                       │                                  │
T2             Đổi title="JPA A"                  Đổi price=150000
                       │                                  │
T3             Flush: UPDATE thành công                     │
               version từ 5 → 6                           │
                       │                                  │
T4                    COMMIT                               │
                       │                                  │
T5                                                        Flush/commit:
                                             UPDATE ... WHERE version=5
                                                          │
                                                Không cập nhật được hàng
                                                          │
                                               OptimisticLockException
```

Tại T4, dữ liệu DB đã sang phiên bản 6. Nhưng transaction B vẫn giữ một entity mà nó tải từ phiên bản 5. **Tình trạng stale đã tồn tại trước T5**, còn ngoại lệ chỉ xuất hiện khi provider kiểm tra phiên bản.

Nếu B chỉ đọc getter:

```java
bookB.getPrice();
bookB.getTitle();
```

thì thường chỉ đọc state Java của object đã managed. Không có quy tắc rằng mỗi getter phải gọi SQL để kiểm tra version mới. B có thể tiếp tục làm việc với dữ liệu lỗi thời mà chưa nhận lỗi.

Điều JPA cần bảo vệ là các thao tác theo optimistic-locking semantics, nhất là cập nhật/xóa entity versioned hoặc yêu cầu khóa lạc quan, **không phải bảo đảm mỗi lần đọc object đều thấy dữ liệu vừa commit của transaction khác**.

## 2. Entity có `@Version`

Một entity minh họa:

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    protected Book() {
    }

    public Book(String title, BigDecimal price) {
        rename(title);
        changePrice(price);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getTitle() {
        return title;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Invalid title");
        }
        title = newTitle.trim();
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        price = newPrice;
    }
}
```

DDL mang tính minh họa:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL
);
```

Cách sinh khóa và cú pháp DDL có thể khác theo database. Cột `version` được quản lý qua JPA mapping; **ứng dụng không nên tự tăng hoặc đặt giá trị version của managed entity** để giả lập khóa lạc quan.

Trong một entity có version, thông thường khai báo một thuộc tính `@Version` thuộc các kiểu được Jakarta Persistence hỗ trợ. Ở ví dụ này dùng `Long` để dễ quan sát phiên bản tăng dần. Không phải toàn bộ database/provider có cùng lựa chọn kiểu version hoặc chiến lược timestamp; cần kiểm tra phiên bản spec đang áp dụng nếu sử dụng loại khác.

### Bất biến cần hiểu

Khi hai transaction có snapshot/version cũ cùng cập nhật một row, provider dùng version để tránh chấp nhận im lặng một thay đổi dựa trên state lỗi thời. Nhưng **version check chỉ xảy ra khi có một điểm kiểm tra**, chứ không được gắn tự động vào mọi setter/getter của object Java.

## 3. SQL minh họa cách phát hiện xung đột

Một managed update versioned thường có ý tưởng:

```sql
UPDATE books
SET title = ?, version = ?
WHERE id = ? AND version = ?;
```

Ví dụ transaction A:

```sql
UPDATE books
SET title = 'JPA A', version = 6
WHERE id = 42 AND version = 5;
```

Nếu bản ghi còn version 5, câu lệnh cập nhật thành công.

Sau khi A commit, transaction B vẫn dùng version 5:

```sql
UPDATE books
SET price = 150000, version = 6
WHERE id = 42 AND version = 5;
```

Vì row hiện mang version 6, điều kiện `version = 5` không còn khớp. Provider có thể thấy số hàng được cập nhật không phù hợp kỳ vọng và báo optimistic locking failure.

**SQL trên chỉ minh họa ý tưởng**, không phải cú pháp SQL bắt buộc JPA phải phát cho mọi entity/provider. SQL thực tế có thể:

- Chỉ chứa các cột dirty hoặc cập nhật nhiều cột.
- Sử dụng kiểu version/timestamp phù hợp.
- Tận dụng batching.
- Dùng câu lệnh khác để kiểm tra lock.
- Thực thi tại flush hoặc commit tùy workflow.

Khi phân tích thời điểm ngoại lệ, hãy nhìn **khi nào SQL có kiểm tra version thực sự được gửi xuống database**.

## 4. Ba mốc thời gian dễ nhầm

Có thể phân thành:

| Mốc | Ý nghĩa | Có bắt buộc ném lỗi ngay? |
| --- | --- | --- |
| Entity trở nên stale | Transaction khác commit thay đổi version | Không; Java object có thể chưa biết |
| Ứng dụng thay đổi managed entity | Setter/domain method làm state dirty | Không; có thể chưa SQL |
| JPA kiểm tra version | Flush, commit hoặc thao tác yêu cầu lock/version check | **Có thể ném OptimisticLockException tại đây** |

Ví dụ:

```java
Book book = em.find(Book.class, id);

book.rename("Tên mới"); // Chỉ sửa managed state.

validateBusinessRules(book); // Có thể chỉ chạy code Java.

em.flush(); // Điểm thường phát SQL UPDATE và kiểm tra version.
```

Không nên đặt toàn bộ xử lý optimistic conflict vào catch quanh `rename` rồi nghĩ đã bảo vệ được thao tác lưu. Nếu flush/commit xảy ra sau đó, catch ấy không bắt lỗi.

Tương tự, không nên gọi commit thành công chỉ vì `em.flush()` chưa ném lỗi; commit còn có thể gặp optimistic lock failure bị trì hoãn hoặc lỗi transaction khác.

---

## 5. Địa điểm thường xuất hiện lỗi: `EntityManager.flush()`

`flush()` yêu cầu JPA đồng bộ những thay đổi pending của persistence context xuống database.

```java
em.getTransaction().begin();

Book book = em.find(Book.class, id);
book.rename("Tên cập nhật");

em.flush(); // Có thể phát UPDATE và ném OptimisticLockException.

em.getTransaction().commit();
```

Nếu Book version đã lỗi thời, provider có thể phát hiện ngay tại `flush()`.

Đây là nơi phù hợp để **chủ động đặt điểm kiểm tra** khi application muốn sớm biết việc ghi có vượt qua optimistic locking hay không.

Ví dụ:

```java
try {
    book.rename(command.newTitle());

    em.flush();

    // Chỉ đến đây khi các thao tác flush đã thành công.
    performNextStep();
} catch (OptimisticLockException conflict) {
    // Không cố dùng tiếp transaction đã bị lỗi.
    throw conflict;
}
```

Tuy nhiên:

- `flush()` không phải commit.
- Exception từ database có thể là constraint violation, deadlock hoặc loại khác, không chỉ `OptimisticLockException`.
- Provider có thể hoãn một số kiểm tra đến commit theo chuẩn/implementation.
- Flush có thể đồng bộ **nhiều entity dirty**, không nhất thiết Book ở ngay dòng gần nhất.

Vì vậy thông báo lỗi nên dựa trên nguyên nhân được xác định, không mặc định mọi lỗi tại flush là “Book này đã bị người khác sửa”.

## 6. Địa điểm thường xuất hiện lỗi: transaction `commit()`

Khi ứng dụng không gọi `flush()` tường minh, provider thường thực hiện việc đồng bộ cần thiết trong quá trình commit.

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Book book = em.find(Book.class, id);
    book.rename("Tên cập nhật");

    em.getTransaction().commit(); // Có thể thất bại tại đây.
} finally {
    em.close();
}
```

Xung đột có thể đã tồn tại trước đó nhiều giây, nhưng chỉ khi commit cố gắng đồng bộ/check version mới có lỗi.

### Ngoại lệ tại commit có thể được bọc

Với JPA resource-local transaction, lỗi commit có thể được thể hiện bằng một ngoại lệ cấp transaction, ví dụ `RollbackException` có `OptimisticLockException` hoặc exception provider bên trong chuỗi nguyên nhân.

Không chỉ viết:

```java
try {
    em.getTransaction().commit();
} catch (OptimisticLockException e) {
    // Có thể bỏ sót lỗi được bọc bởi exception khác.
}
```

Khi cần phân loại lỗi ổn định, xem **exception chain**, transaction status và contract của JPA provider/transaction manager. Không nên tự parse mọi error message dạng text vì chúng có thể thay đổi theo driver và ngôn ngữ.

### Commit có thể ném lỗi khác

Với concurrency, bạn còn có thể gặp:

- `PersistenceException`.
- `RollbackException`.
- Database deadlock/serialization failure.
- Unique/foreign-key constraint errors.
- Lock timeout.

Không phải mọi commit failure đều là optimistic locking conflict, dù use case đang cập nhật entity có `@Version`.

## 7. Địa điểm bất ngờ: một truy vấn gây auto-flush

Một câu JPQL SELECT có thể là nơi **biểu hiện** của lỗi trên entity đang dirty.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, bookId);
book.rename("Tên mới");

List<Book> matches = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
).setParameter("title", "Tên mới")
 .getResultList(); // Có thể kích hoạt auto-flush.

em.getTransaction().commit();
```

Với `FlushModeType.AUTO` trong persistence context tham gia transaction, provider phải bảo đảm những pending changes có thể ảnh hưởng kết quả query được phản ánh theo semantics của JPA. Một cách phổ biến là flush trước query.

Nếu Book đã stale, exception có thể xuất hiện ngay ở:

```java
getResultList();
```

không phải ở:

```java
book.rename(...);
```

### Các thao tác query tương tự

Xung đột có thể biểu hiện ở nhiều phương thức thực thi query:

- `getResultList()`.
- `getSingleResult()`.
- `getResultStream()` hoặc lúc tiêu thụ stream, tùy provider và lúc thực thi.
- Các query JPQL/Criteria khác kích hoạt flush.
- Native query có chiến lược auto-flush tương ứng.

Câu SELECT không “sửa Book” theo logic nghiệp vụ. **Nó chỉ có thể khiến provider quyết định phải đồng bộ Book trước khi trả kết quả.**

### Ví dụ SQL log

```text
begin transaction
SELECT ... FROM books WHERE id = ?
-- ứng dụng rename Book trong heap
UPDATE books SET title=?, version=? WHERE id=? AND version=?
-- UPDATE khớp 0 hàng
OptimisticLockException
-- SELECT JPQL mà ứng dụng định chạy có thể chưa được gửi
```

Vì vậy khi stack trace chỉ tới `getResultList()`, hãy xem SQL phát trước SELECT và những entity đang dirty trong context.

## 8. AUTO và COMMIT khác nhau thế nào về thời điểm phát hiện lỗi?

Có thể đặt flush mode:

```java
em.setFlushMode(FlushModeType.AUTO);
```

hoặc:

```java
query.setFlushMode(FlushModeType.COMMIT);
```

### `FlushModeType.AUTO`

Provider phải xử lý ảnh hưởng của pending changes lên query khi context tham gia transaction. Vì vậy, một query có thể tạo ra **điểm phát hiện xung đột sớm** do auto-flush.

Điều này không có nghĩa:

- Mọi SELECT đều phát SQL UPDATE.
- Mọi dirty entity đều được flush trước mọi query.
- Có một thời điểm auto-flush cố định trên mọi JPA provider.
- Truy vấn luôn đọc lại mọi managed object từ DB.

### `FlushModeType.COMMIT`

Ảnh hưởng của pending changes lên query trước commit không có cùng bảo đảm như AUTO. Provider có thể trì hoãn flush đến commit, nên một optimistic conflict có thể xuất hiện muộn hơn.

Nhưng **COMMIT không phải chế độ “tuyệt đối cấm flush trước commit”**. Explicit `em.flush()`, việc sinh ID hoặc tình huống khác vẫn có thể gây SQL sớm; provider cũng có những lựa chọn implementation riêng.

### Bảng so sánh

| Tình huống | AUTO | COMMIT |
| --- | --- | --- |
| Query có thể kích hoạt flush pending update | Có | Không có bảo đảm giống AUTO; phụ thuộc hoàn cảnh |
| Conflict có thể bị phát hiện tại query | Có | Có thể, nhưng không được coi là cam kết chung |
| Conflict có thể bị phát hiện tại explicit `flush()` | Có | Có |
| Conflict có thể bị phát hiện tại commit | Có | Có |
| Setter luôn báo conflict ngay | Không | Không |
| Flush mode quyết định transaction đã commit? | Không | Không |

**Flush mode ảnh hưởng thời điểm đồng bộ; nó không thay thế optimistic locking, transaction isolation hoặc chiến lược xử lý lỗi.**

## 9. Địa điểm khác: `merge()` detached entity đã stale

Một tình huống thường gặp trong ứng dụng web:

1. Transaction A đọc Book version 5.
2. Book được detached khi request/context kết thúc.
3. Transaction B cập nhật Book lên version 6.
4. Ứng dụng cố merge detached Book version 5.

```java
Book detached = loadBookInAnotherContext(bookId);
// detached mang version cũ.

EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Book managedCopy = em.merge(detached);

    em.getTransaction().commit();
} finally {
    em.close();
}
```

Nếu entity detached có version stale, JPA provider có thể kiểm tra version **ngay trong `merge()`** hoặc **trì hoãn tới flush/commit**.

Điều này quan trọng vì:

```java
Book managedCopy = em.merge(detached);
```

**không phải một bảo đảm rằng merge đã vượt qua toàn bộ optimistic locking** chỉ vì lời gọi trả về object.

### `merge()` không chuyển detached object thành managed

```java
Book managedCopy = em.merge(detached);
```

Thông thường:

- `detached` vẫn là detached instance.
- `managedCopy` là managed representative trong context.
- JPA copy state phù hợp từ detached sang managed instance.
- Version check có thể diễn ra ngay hoặc muộn hơn.

Không nên tiếp tục sửa `detached` rồi nghĩ những sửa đổi ấy sẽ tự được dirty checking trong context mới.

### Vì sao merge dễ gây mất cập nhật ngoài ý muốn?

Một detached graph có thể chứa nhiều field cũ. Khi merge, những field stale có thể được copy vào managed graph và gây ghi đè ngoài ý định, đặc biệt nếu versioning không được áp dụng đầy đủ hoặc dữ liệu không versioned.

Với API cập nhật, thường an toàn và rõ ràng hơn khi nhận **command DTO**, load entity managed mới nhất trong transaction và áp dụng đúng field được phép, thay vì merge toàn bộ detached entity lấy từ client.

## 10. `persist()` có phát OptimisticLockException không?

Với entity mới:

```java
Book book = new Book(
    "JPA căn bản",
    new BigDecimal("120000")
);

em.persist(book);
```

Đây là thao tác thêm entity; không có một phiên bản DB cũ của cùng managed instance để kiểm tra optimistic update theo cơ chế thường gặp.

Tuy nhiên, `persist` vẫn có thể gây:

- Constraint violations khi INSERT.
- Duplicate key error.
- `EntityExistsException` hoặc exception khác liên quan entity identity.
- Lỗi transaction/DB khi flush hoặc commit.

**Không nên gán mọi lỗi ghi đồng thời cho `OptimisticLockException`.** Với INSERT trùng khóa hoặc unique constraint, bản chất lỗi thường là ràng buộc dữ liệu, không phải stale versioned update.

Có những mapping/provider đặc thù làm việc với version khi thêm entity, nhưng trong nghiệp vụ thông thường `@Version` được dùng để phát hiện conflict khi update/delete hoặc yêu cầu optimistic lock trên entity đã tồn tại.

## 11. `remove()` có thể phát hiện xung đột muộn

Ví dụ:

```java
Book book = em.find(Book.class, bookId);

em.remove(book);

// Có thể chưa có DELETE SQL ngay tại dòng remove.

em.flush(); // Có thể ném OptimisticLockException.
```

Nếu transaction khác đã update/delete row hoặc version không còn khớp, provider có thể phát hiện khi thực thi version-checked DELETE.

SQL minh họa:

```sql
DELETE FROM books
WHERE id = ? AND version = ?;
```

Nếu hàng không còn tồn tại hoặc version khác, số hàng bị ảnh hưởng có thể không đúng kỳ vọng.

Lưu ý:

- `em.remove(book)` yêu cầu đối tượng ở trạng thái phù hợp (thường managed).
- `remove` có thể gây cascade và xử lý lifecycle của graph.
- Conflict có thể xuất hiện ngay hoặc tại flush/commit tùy provider.
- Nếu xóa bằng **bulk JPQL DELETE** hoặc native SQL DELETE, đó là cơ chế khác, không tự mang toàn bộ per-entity `@Version` checks.

### Ví dụ sai về kỳ vọng

```java
try {
    em.remove(book);
    System.out.println("Delete succeeded");
} catch (OptimisticLockException ex) {
    ...
}
```

Dòng log “Delete succeeded” chỉ nói method `remove` đã trả về, không chứng minh transaction đã xóa row thành công và commit.

## 12. `lock(entity, OPTIMISTIC)` có thể phát hiện lỗi lúc nào?

Ngoài optimistic locking tự nhiên của update/delete versioned entity, JPA có explicit optimistic lock modes:

```java
LockModeType.OPTIMISTIC
LockModeType.OPTIMISTIC_FORCE_INCREMENT
```

Ví dụ:

```java
Book book = em.find(Book.class, bookId);

em.lock(book, LockModeType.OPTIMISTIC);
```

Với `OPTIMISTIC`, provider xác minh phiên bản phù hợp theo semantics của khóa lạc quan. **Việc kiểm tra có thể được thực hiện khi gọi `lock()` hoặc hoãn tới flush/commit**, tùy provider.

Vì vậy:

```java
em.lock(book, LockModeType.OPTIMISTIC);
// Không ném ở đây ≠ không thể ném lúc commit.
```

Đừng nhầm `OPTIMISTIC` với `PESSIMISTIC_READ`/`PESSIMISTIC_WRITE`:

- Optimistic lock chủ yếu dựa vào kiểm tra version; không đồng nghĩa tự giữ DB row lock suốt transaction.
- Pessimistic lock có thể dùng database locking và có các lỗi timeout/lock conflict riêng.
- Chọn lock mode là quyết định về concurrency semantics, không phải công tắc “lỗi xuất hiện sớm chắc chắn”.

### Entity không có version

JPA có quy tắc về hỗ trợ optimistic locking với versioned/non-versioned entities theo chuẩn và provider. Để có hành vi portable và dễ dự đoán cho chương này, hãy dùng `@Version` hợp lệ; không giả định optimistic lock modes hoạt động như nhau trên mọi entity không versioned.

## 13. `OPTIMISTIC_FORCE_INCREMENT`: còn có thao tác tăng version

Một use case muốn bảo vệ aggregate ngay cả khi chưa sửa field trực tiếp:

```java
Book book = em.find(Book.class, bookId);

em.lock(book, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

Mode này yêu cầu cơ chế kiểm tra và tăng version phù hợp. Thời điểm phát SQL tăng version có thể được trì hoãn, thường tới flush hoặc commit, theo semantics của provider/chuẩn.

Vì thế:

```java
em.lock(book, LockModeType.OPTIMISTIC_FORCE_INCREMENT);

// Version Java/DB có thể chưa phản ánh ngay thời điểm sẽ tăng.
// Không dựa vào một giá trị version ngay sau lock() như hợp đồng chung.

em.flush(); // Có thể kích hoạt kiểm tra/tăng version và phát hiện conflict.
```

Ví dụ trong domain aggregate: Order có child lines, muốn bảo đảm một transaction thay đổi child nhưng conflict với transaction khác đang sửa Order. `OPTIMISTIC_FORCE_INCREMENT` trên Order root có thể là một chiến lược để tăng version root khi phù hợp.

Tuy nhiên, sử dụng chiến lược này phải gắn với aggregate design và transaction thật, không tự động chọn nó cho mọi lần đọc vì có thể tăng contention và số SQL ghi.

## 14. `find()` với LockModeType có thể phát hiện xung đột

`EntityManager.find` có overload nhận lock mode:

```java
Book book = em.find(
    Book.class,
    bookId,
    LockModeType.OPTIMISTIC
);
```

Khi query lấy entity và yêu cầu optimistic lock, provider phải thực hiện version verification theo ngữ nghĩa tương ứng. Lỗi có thể xuất hiện khi thao tác lấy/khóa, hoặc bị trì hoãn tới flush/commit theo contract thích hợp.

Điểm cần nhớ:

- `find(Book.class, id)` **không có lock mode** là một thao tác đọc thông thường; nó không phải lệnh kiểm tra version liên tục với các transaction khác.
- `find(..., OPTIMISTIC)` diễn đạt yêu cầu khóa lạc quan.
- Thời điểm exception không được đồng nhất với thời điểm gọi getter của Book.
- Nếu Book đã managed, provider có thể tái sử dụng identity map nhưng vẫn phải đáp ứng yêu cầu lock mode theo semantics của API.

Khi muốn bảo vệ một workflow chỉ đọc rồi thực hiện logic phụ thuộc consistency, explicit lock mode có thể phù hợp hơn việc mong `find` mặc định “biết có người khác đã sửa”.

## 15. Query với `setLockMode(OPTIMISTIC)`

Một typed query có thể chỉ định:

```java
TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b WHERE b.id = :id",
    Book.class
);

query.setParameter("id", bookId);
query.setLockMode(LockModeType.OPTIMISTIC);

Book book = query.getSingleResult();
```

Tùy provider, optimistic verification có thể được thực hiện trong quá trình query hoặc ở một thời điểm muộn hơn trong transaction.

Cần phân biệt:

- `getSingleResult()` có thể ném `NoResultException` nếu không có row.
- Có thể ném `NonUniqueResultException` nếu query trả nhiều row.
- Có thể ném `OptimisticLockException` nếu version check thất bại theo semantics lock mode.
- Có thể có lỗi SQL/transaction khác.

Nếu gặp exception tại `getSingleResult()`, không nên suy ngay đó là optimistic locking conflict chỉ dựa trên method name. Hãy kiểm tra type/cause của exception.

### Không đặt lock mode tùy tiện trên scalar query

Một số query chỉ trả aggregate/scalar values không phù hợp với entity locking semantics. `Query.setLockMode` có các ràng buộc và có thể ném `IllegalStateException` hoặc ngoại lệ khác khi query không hỗ trợ lock mode/không có transaction.

Hãy sử dụng optimistic locking khi query trả versioned entities và transaction context đáp ứng yêu cầu.

## 16. `refresh()` và optimistic lock modes

`refresh()` thông thường:

```java
em.refresh(book);
```

có ý định tải lại state của managed entity từ database. Nhưng gọi refresh thường không phải cách chính để xử lý một transaction đã bị optimistic conflict, bởi transaction có thể đã được đánh dấu rollback-only.

JPA cũng có overload nhận lock mode:

```java
em.refresh(book, LockModeType.OPTIMISTIC);
```

Khi sử dụng optimistic lock mode, provider phải tuân thủ version-check semantics; ngoại lệ có thể phát sinh theo thời điểm kiểm tra.

### Không xử lý conflict bằng cách “refresh rồi commit tiếp” trên transaction lỗi

Ví dụ nguy hiểm:

```java
try {
    em.flush();
} catch (OptimisticLockException conflict) {
    em.refresh(book);
    em.getTransaction().commit(); // Không phải pattern an toàn.
}
```

Một `OptimisticLockException` liên quan transaction thường khiến transaction bị đánh dấu **rollback-only**. Đừng cố tiếp tục dùng cùng transaction sau khi xung đột đã được phát hiện.

Cách đúng về mặt lifecycle là rollback, kết thúc đơn vị công việc và quyết định có retry trong **transaction/persistence context mới** hay thông báo người dùng giải quyết conflict.

## 17. `getReference()` và lazy proxies không bảo đảm phát hiện stale ngay

`EntityManager.getReference(Book.class, id)` có thể trả một reference/proxy mà provider chưa phải đọc toàn bộ row ngay lập tức.

```java
Book ref = em.getReference(Book.class, bookId);

// Có thể chưa thực thi SELECT đầy đủ tại đây.

String title = ref.getTitle();
```

Việc khởi tạo proxy có thể phát SQL hoặc gặp `EntityNotFoundException` nếu row không tồn tại, tùy provider và bối cảnh.

Không nên tự coi `getReference` là một optimistic version verification. Nếu ứng dụng cần lock/check, dùng API lock mode phù hợp hoặc bảo vệ thao tác update/delete qua `@Version`.

Một lỗi “row không tồn tại khi proxy được sử dụng” **không đồng nghĩa** `OptimisticLockException`.

---

## 18. Từ setter đến commit: bảng vị trí lỗi

| Thao tác | Có thể kích hoạt kiểm tra version? | Ghi chú |
| --- | --- | --- |
| `book.rename(...)` | Thường **không ngay lúc setter** | Chỉ làm managed object dirty |
| `em.persist(newBook)` | Không phải optimistic update của row đã tồn tại theo luồng thường | Lỗi INSERT/constraint khác |
| `em.flush()` | **Có** | Đồng bộ update/delete và có thể check version |
| `em.getTransaction().commit()` | **Có** | Có thể thực hiện flush/check còn lại; exception có thể bị bọc |
| JPQL `getResultList()` | **Có thể** | Query có thể auto-flush pending changes |
| JPQL `getSingleResult()` | **Có thể** | Tương tự; còn có NoResult/NonUniqueResult |
| `getResultStream()`/traversal | **Có thể** | Provider quyết định lúc execute/read/flush |
| Native `SELECT` thực thi | **Có thể** | Phụ thuộc flush mode và provider/native query semantics |
| `em.merge(detached)` | **Có thể ngay hoặc muộn hơn** | Stale detached version check có thể deferred |
| `em.remove(managed)` | **Có thể ngay hoặc muộn hơn** | DELETE versioned thường được kiểm tra khi SQL chạy |
| `em.lock(book, OPTIMISTIC)` | **Có thể ngay hoặc muộn hơn** | Explicit optimistic verification |
| `em.lock(book, OPTIMISTIC_FORCE_INCREMENT)` | **Có thể ngay hoặc muộn hơn** | Còn có version increment |
| `em.find(..., OPTIMISTIC)` | **Có thể ngay hoặc muộn hơn** | Fetch có optimistic lock requirement |
| Query `setLockMode(OPTIMISTIC)` | **Có thể ngay hoặc muộn hơn** | Phù hợp với query/entity semantics |
| Getter của Book đã managed | Thường không | Đọc state Java, không tự refresh liên tục |
| Bulk JPQL/native UPDATE không có version predicate | **Không được bảo vệ tự động như managed update** | Phải tự thiết kế version check nếu cần |
| `em.clear()` | Không phải lock check | Detach toàn persistence context |
| `em.detach(book)` | Không phải lock check | Detach một entity; không tự flush |

Bảng nêu những điểm **có thể** phát hiện xung đột, không gán một lệnh Java với một SQL bắt buộc cho mọi provider.

## 19. Vì sao lần SELECT trước không bắt buộc phát hiện conflict?

Một transaction có thể:

```java
Book book = em.find(Book.class, 42L);

display(book.getTitle());

// Transaction khác update Book #42 và commit.

display(book.getTitle());
```

Book hiện tại vẫn được quản lý trong một persistence context có identity map. Getter không phải query và không bị buộc phải kiểm tra DB version ở mỗi lần đọc. `find(Book.class, 42L)` lần nữa trong cùng context cũng có thể trả cùng object, không nhất thiết gửi SELECT mới.

Khi transaction này sửa Book rồi flush, version check mới phát hiện conflict.

### Vậy optimistic locking có chặn stale reads không?

Không theo nghĩa “mọi lần đọc đều luôn mới nhất”. Optimistic locking bảo vệ những thao tác theo semantics versioned entity/explicit optimistic lock. Nó không thay thế:

- Database isolation level.
- Refresh khi cần dữ liệu mới.
- Snapshot consistency.
- Cache invalidation.
- Business rule tính toán dựa trên dữ liệu đồng thời.

Nếu một quyết định nghiệp vụ đòi hỏi kiểm tra nhất quán khi chỉ đọc, có thể cần `OPTIMISTIC` lock mode hoặc cơ chế concurrency khác phù hợp; không đơn thuần dùng entity getter.

## 20. Ví dụ timeline đầy đủ với hai EntityManager

Ta tạo hai EntityManager độc lập đại diện hai transaction.

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    emA.getTransaction().begin();
    emB.getTransaction().begin();

    Book bookA = emA.find(Book.class, bookId);
    Book bookB = emB.find(Book.class, bookId);

    Long versionAtStart = bookB.getVersion();

    bookA.rename("Tác giả A sửa");

    emA.flush();
    emA.getTransaction().commit();

    bookB.rename("Tác giả B sửa");

    // Tại đây B vẫn có thể giữ versionAtStart.
    // B sẽ gặp conflict khi version check xảy ra:
    emB.flush();

    emB.getTransaction().commit();
} catch (RuntimeException ex) {
    if (emA.getTransaction().isActive()) {
        emA.getTransaction().rollback();
    }
    if (emB.getTransaction().isActive()) {
        emB.getTransaction().rollback();
    }
    throw ex;
} finally {
    emA.close();
    emB.close();
}
```

Đoạn code minh họa đường đi conflict: cả A/B load cùng version, A commit, B thử ghi version cũ.

**Không nên coi ví dụ này là test portable chạy ổn trên mọi database ở mọi isolation mode khi giữ transaction B mở suốt lúc A commit**. Ở một số database/isolation level, snapshot/lock hoặc transaction serialization có thể thay đổi thời điểm chờ, gây lock timeout/deadlock/serialization error thay vì optimistic conflict thuần túy.

Để kiểm thử deterministic hơn, có thể tạo một Book **detached snapshot ở phiên bản cũ**, cho transaction mới update/commit trước, rồi merge/update từ phiên bản cũ trong transaction khác; hoặc dùng phối hợp hai transaction được kiểm soát bằng test harness trên database thật.

## 21. Khác biệt database isolation: không phải lỗi đồng thời nào cũng là OptimisticLockException

Một số database có MVCC; một số áp dụng row-level locks hoặc snapshot isolation. Khi hai transaction cùng cập nhật một row:

- Transaction thứ hai có thể phải chờ transaction thứ nhất.
- Database có thể trả deadlock hoặc serialization failure.
- Provider có thể phát hiện version mismatch sau khi lock được giải phóng.
- Một transaction có thể bị rollback do cơ chế DB trước khi kiểm tra `WHERE version = ?` thành công/không thành công.
- Driver có thể gói exception bằng SQLState/vendor code.

Vì thế một integration test chỉ assert:

```java
assertThrows(OptimisticLockException.class, () -> emB.flush());
```

có thể quá cứng nếu chưa kiểm soát transaction schedule và DB isolation. Cần xác định mục tiêu test:

- Kiểm tra JPA optimistic locking trên provider cụ thể.
- Kiểm tra concurrency end-to-end dưới isolation production.
- Kiểm tra retry/HTTP conflict translation.

Cả ba mục tiêu liên quan nhưng không giống nhau.

## 22. Một phương án test dễ tái hiện bằng detached version cũ

Thay vì giữ hai transaction đồng thời mở lâu, ta có thể mô tả ba giai đoạn:

1. Transaction đọc Book và đóng context, giữ detached Book version V.
2. Transaction khác cập nhật cùng Book và commit thành version V+1.
3. Transaction mới cố `merge()` detached Book V.

```java
private Book loadDetached(EntityManagerFactory emf, Long bookId) {
    EntityManager em = emf.createEntityManager();
    try {
        return em.find(Book.class, bookId);
    } finally {
        em.close();
    }
}
```

Chuẩn bị:

```java
Book stale = loadDetached(emf, bookId);
stale.rename("Tên từ bản cũ");

EntityManager writer = emf.createEntityManager();
try {
    writer.getTransaction().begin();

    Book current = writer.find(Book.class, bookId);
    current.rename("Tên mới đã commit");

    writer.getTransaction().commit();
} finally {
    writer.close();
}
```

Thử merge phiên bản cũ:

```java
EntityManager retry = emf.createEntityManager();
try {
    retry.getTransaction().begin();

    Book managedCopy = retry.merge(stale);

    // Lỗi có thể xảy ra ngay ở merge, ở flush,
    // hoặc ở commit tùy provider.
    retry.flush();

    retry.getTransaction().commit();
} catch (RuntimeException ex) {
    if (retry.getTransaction().isActive()) {
        retry.getTransaction().rollback();
    }
    throw ex;
} finally {
    retry.close();
}
```

Bài test nên bắt lỗi cho **toàn đơn vị công việc** thay vì chỉ quanh `merge()`, vì JPA cho phép timing khác nhau.

### Một hạn chế quan trọng

Khi kiểm thử entity detached, cần chắc chắn instance vẫn là entity versioned có identity/version hợp lệ. Nếu object được dựng thủ công từ JSON mà thiếu version, behavior có thể là insert/merge không hợp lệ hoặc vấn đề khác, không đơn thuần là stale-version conflict.

## 23. Test xác minh conflict bất kể xuất hiện tại merge, flush hay commit

Một cách viết test:

```java
@Test
void staleDetachedBookIsRejectedWhenWriting() {
    Long bookId = seedBookAndCommit();

    Book stale = loadDetached(emf, bookId);
    stale.rename("Đề nghị từ bản cũ");

    updateTitleAndCommit(emf, bookId, "Người khác đã lưu");

    EntityManager em = emf.createEntityManager();

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> {
            try {
                em.getTransaction().begin();

                em.merge(stale);
                em.flush();
                em.getTransaction().commit();
            } finally {
                if (em.getTransaction().isActive()) {
                    em.getTransaction().rollback();
                }
            }
        }
    );

    assertTrue(
        containsOptimisticFailure(failure),
        "Expected an optimistic-locking failure"
    );

    em.close();
}
```

`seedBookAndCommit`, `updateTitleAndCommit` và `containsOptimisticFailure` là **test helpers cần triển khai** trong dự án. Helper `containsOptimisticFailure` phải kiểm tra exception chain/provider translation có chủ đích, không chỉ tìm substring trong message.

Ở ví dụ này, lỗi được bắt qua cả merge/flush/commit, nhưng việc `em.close()` nên nằm trong `finally` ngoài cùng của test thực tế để bảo đảm cleanup ngay cả khi assertion thất bại. Một mẫu lifecycle chặt chẽ hơn sẽ mở EntityManager trong try/finally đầy đủ.

### Không biến assertThrows(RuntimeException.class) thành test quá rộng

Một `NullPointerException` trong test cũng là RuntimeException, nhưng không chứng minh optimistic locking. Vì vậy nhất thiết phải **xác nhận cause/type** sau khi bắt, hoặc bắt đúng exception class khi provider/framework đã có contract rõ.

## 24. Test riêng: ép kiểm tra sớm bằng flush

Nếu cần test rằng một conflict được phát hiện trước khi gọi external service hoặc thực hiện tác vụ tiếp theo, có thể đặt `flush()` ở boundary cụ thể.

Ví dụ resource-local:

```java
public void updateTitleAndValidateEarly(
        EntityManager em,
        Long id,
        String title) {

    Book book = em.find(Book.class, id);
    if (book == null) {
        throw new IllegalArgumentException("Book not found");
    }

    book.rename(title);

    em.flush(); // Cố ý kích hoạt đồng bộ và kiểm tra sớm.
}
```

Khi em đang tham gia transaction, flush có thể phát hiện version mismatch trước khi code gọi những công việc phía sau.

Tuy nhiên:

- Flush không phải final commit.
- Commit vẫn có thể thất bại vì optimistic check bị trì hoãn hoặc lỗi khác.
- Nếu thay đổi từ transaction khác xảy ra **sau flush nhưng trước commit**, concurrency vẫn có thể tạo tình huống cần xử lý ở commit/serialization level.
- Tránh gọi một external irreversible action trong transaction chỉ vì flush đã thành công.

Đối với side effects như gửi email, thanh toán hoặc publish message, nên cân nhắc **transactional outbox** hoặc mô hình phối hợp để chỉ phát side effects sau commit thành công, thay vì coi flush success là giấy phép phát tác vụ không thể rollback.

## 25. Test riêng: lỗi có thể xuất hiện tại query

Một test minh họa:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, bookId);

// Giả định transaction khác đã commit thay đổi
// sau khi Book này được tải.

book.rename("Đổi tên bằng bản stale");

List<Book> results = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
).setParameter("title", "Đổi tên bằng bản stale")
 .getResultList(); // Có thể auto-flush và phát hiện conflict.
```

**Không nên assert cố định rằng getResultList phải ném OptimisticLockException trên mọi provider**. Muốn kiểm chứng query-triggered flush:

1. Dùng `AUTO`.
2. Đảm bảo context tham gia active transaction.
3. Chuẩn bị entity stale có pending change ảnh hưởng query.
4. Bật SQL logging.
5. Quan sát thứ tự UPDATE/SELECT và exception.
6. Kiểm tra provider-specific behavior/version.

Nếu mục tiêu là kiểm thử nghiệp vụ portable, bắt conflict ở **ranh giới transaction tổng thể**, không lệ thuộc việc query hay commit ném lỗi.

---

## 26. Sự kiện flush xảy ra với nhiều entity

Giả sử một transaction cập nhật ba entity:

```java
Book bookA = em.find(Book.class, idA);
Book bookB = em.find(Book.class, idB);
Book bookC = em.find(Book.class, idC);

bookA.rename("Tên A");
bookB.rename("Tên B");
bookC.rename("Tên C");

em.flush();
```

Nếu Book B stale, exception được ném tại `flush()`. Nhưng stack trace có thể chỉ cho thấy `flush`, không cho biết chính xác câu setter nào gây version mismatch.

SQL log có thể cho biết:

```text
UPDATE books ... WHERE id=A AND version=...
UPDATE books ... WHERE id=B AND version=...
-- B ảnh hưởng 0 hàng
OptimisticLockException
```

Lúc này transaction có thể đã gửi SQL của A trước khi lỗi ở B. Những SQL đó vẫn thuộc transaction và phải được rollback nếu đơn vị công việc thất bại.

**Không được giả định exception tại flush chỉ liên quan entity được sửa gần nhất trong code.** Cần xem tất cả pending state trong persistence context.

## 27. JDBC batching có thể dời thời điểm biết lỗi

Với Hibernate/JDBC batch update, provider có thể gom nhiều SQL statements. Lỗi version check/row count có thể được phát hiện khi batch được gửi và xử lý:

```text
Book A dirty
Book B dirty
Book C dirty
     │
     ▼
flush → gom UPDATE statements
     │
     ▼
executeBatch()
     │
     ▼
phát hiện UPDATE của một Book không khớp version
     │
     ▼
OptimisticLockException hoặc wrapper
```

Hệ quả:

- Dòng Java báo lỗi có thể là `flush()` hoặc `commit()`.
- Driver/provider error chain có thể nhắc tới batch.
- SQL log một batch không luôn tách rõ từng câu như khi không batching.
- Batch execution errors cũng có thể là constraint/driver errors, không phải tất cả đều optimistic lock conflicts.

Nếu debug khó, hãy dùng cấu hình SQL/batch diagnostics phù hợp với provider trong môi trường test. Không tắt batching vĩnh viễn chỉ để “sửa” một optimistic conflict thực sự.

## 28. Concurrency giữa entity cha và con

Giả sử `PurchaseOrder` có nhiều `OrderLine`. Nếu hai transaction sửa **những line khác nhau**, optimistic locking ở Order root có bắt conflict không?

Không nhất thiết.

`@Version` trên Order thường bảo vệ những update/delete của **Order row** theo semantics và những thao tác force increment phù hợp. Thay đổi row OrderLine có thể không làm version của Order tăng trừ khi mapping/provider/application thiết kế điều đó.

Ví dụ:

```java
OrderLine line = em.find(OrderLine.class, lineId);
line.changeQuantity(5);
```

Nếu OrderLine có `@Version` riêng, xung đột trên chính line có thể được phát hiện khi flush/commit của line.

Nhưng nếu business invariant nằm ở toàn aggregate (ví dụ tổng số lượng không vượt giới hạn), phải xác định lock/version boundary ở aggregate root hoặc có cơ chế kiểm soát khác.

### Khi nào force increment root?

Một service có thể:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId
);

em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);

// Sau đó sửa lines liên quan trong cùng transaction.
```

Mục tiêu là buộc thay đổi version Order khi workflow sửa aggregate; tuy nhiên timing của increment/check vẫn có thể ở flush/commit. Hãy test trên đúng mapping/provider và tránh giả định mọi child modification tự increment root version.

## 29. Bulk JPQL UPDATE/DELETE không tự theo dõi version như managed update

Đây là ngoại lệ quan trọng của mô hình “entity có `@Version` nên mọi update đều được bảo vệ”.

```java
int count = em.createQuery(
    "UPDATE Book b " +
    "SET b.price = :price " +
    "WHERE b.id = :id"
).setParameter("price", new BigDecimal("200000"))
 .setParameter("id", bookId)
 .executeUpdate();
```

Bulk JPQL DML thường bỏ qua optimistic locking/version increments tự động giống thao tác dirty-checking từng managed entity. Nếu câu lệnh không có điều kiện version/tăng version, người viết query có thể vô tình cập nhật hàng từ bản stale mà không được báo `OptimisticLockException`.

Tương tự:

```java
em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
).setParameter("id", bookId)
 .executeUpdate();
```

không tương đương `em.remove(bookManaged)` về lifecycle/optimistic locking.

### Nếu cần version check trong bulk DML

Có thể thiết kế điều kiện:

```java
int updated = em.createQuery(
    "UPDATE Book b " +
    "SET b.price = :price, b.version = b.version + 1 " +
    "WHERE b.id = :id AND b.version = :expected"
).setParameter("price", newPrice)
 .setParameter("id", bookId)
 .setParameter("expected", expectedVersion)
 .executeUpdate();

if (updated != 1) {
    throw new OptimisticLockException(
        "Book was changed or deleted"
    );
}
```

Đây là ví dụ **ứng dụng tự quản lý version bằng bulk query**. Phải kiểm tra kiểu version, provider hỗ trợ cú pháp arithmetic trong update và transaction/row-count semantics. Nó không làm provider tự đồng bộ managed Book đã nằm trong persistence context.

Quan trọng: exception trong `if (updated != 1)` được **application chủ động ném**; không phải provider tự phát hiện optimistic lock qua `@Version` ở câu bulk DML đó.

## 30. Native SQL UPDATE cũng có thể bypass `@Version`

Ví dụ:

```java
em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Tên mới")
 .setParameter(2, bookId)
 .executeUpdate();
```

SQL này không kiểm tra `version`, cũng không tăng version. Vì vậy:

- Nó có thể ghi đè dữ liệu mà transaction khác đã cập nhật.
- Managed Book trong persistence context có thể stale.
- Versioned managed update sau đó có thể không phát hiện thay đổi nếu native SQL không bump version.
- Không có bảo đảm tự phát `OptimisticLockException` từ câu native UPDATE này.

Muốn optimistic locking ở SQL:

```sql
UPDATE books
SET title = ?, version = version + 1
WHERE id = ? AND version = ?;
```

và kiểm tra số hàng ảnh hưởng. Sau native update, cân nhắc refresh/clear/context mới theo nghiệp vụ để tránh state stale. Đừng trộn native DML và managed entity dirty checking trên cùng row mà thiếu chiến lược.

## 31. Lỗi optimistic locking có phải luôn là "người khác sửa" không?

Thường là một transaction hoặc thao tác ngoài context đã thay đổi/xóa row khiến version không còn khớp. Nhưng có những nguyên nhân khác cũng có thể biểu hiện như stale-state/version mismatch:

- DB trigger tự sửa cột `version`.
- JDBC job hoặc ứng dụng khác sửa version không theo convention.
- Mapping `@Version` sai cột/kiểu.
- Ứng dụng tự đặt version của entity.
- Row bị xóa trong lúc transaction đang làm việc.
- Bulk SQL cập nhật version nhưng persistence context chưa refresh.
- Provider nhận số row affected khác kỳ vọng do mapping/DB behavior.
- Test fixture không được cô lập, transaction khác thay dữ liệu.

Vì vậy, không nên luôn hiển thị thông báo “Người dùng X vừa sửa bản ghi” nếu hệ thống chưa có audit chứng minh điều đó. Một thông báo chính xác hơn:

> “Dữ liệu đã thay đổi hoặc không còn hợp lệ so với phiên bản bạn đang chỉnh sửa. Hãy tải lại và thử thao tác trên dữ liệu mới.”

Các lỗi technical cần được log có kiểm soát để xác định root cause, không phơi SQL exception hoặc stack trace cho người dùng cuối.

## 32. Khóa lạc quan và khóa bi quan: khác cả loại lỗi

Khóa bi quan:

```java
Book book = em.find(
    Book.class,
    bookId,
    LockModeType.PESSIMISTIC_WRITE
);
```

có thể yêu cầu DB row lock và gây:

- `PessimisticLockException`.
- `LockTimeoutException`.
- Driver lock timeout/deadlock exceptions.
- `PersistenceException` liên quan transaction.

Khóa lạc quan:

```java
Book book = em.find(
    Book.class,
    bookId,
    LockModeType.OPTIMISTIC
);
```

chủ yếu dựa vào version verification và có thể gây `OptimisticLockException` khi kiểm tra phiên bản thất bại.

Một serialization failure do isolation của DB **không tự động đồng nghĩa** JPA `OptimisticLockException`, dù nó cũng do concurrency. Muốn xử lý đúng retry/user feedback, hãy phân loại theo cause từ provider/transaction manager.

## 33. Khi OptimisticLockException xảy ra, transaction thường không còn dùng tiếp được

Đây là nguyên tắc xử lý then chốt.

Ví dụ sai:

```java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    book.rename("Đổi lại một tên khác");
    em.flush(); // Cố cứu cùng transaction.
}
```

Trong JPA, `OptimisticLockException` thường khiến transaction hiện tại được đánh dấu rollback-only. Việc sửa entity rồi flush tiếp trong transaction đó không phải một chiến lược khôi phục an toàn.

Điều nên làm:

1. Dừng đơn vị công việc hiện tại.
2. Để transaction manager rollback hoặc rollback tường minh khi phù hợp.
3. Đóng/kết thúc persistence context của lần thử thất bại.
4. Xem conflict là kết quả nghiệp vụ cần xử lý.
5. Nếu retry hợp lệ, khởi tạo **transaction và EntityManager/persistence context mới**.
6. Đọc lại phiên bản mới và áp dụng lại ý định nghiệp vụ sau khi kiểm tra invariants.
7. Không tự động merge graph stale trong lần retry.

### Resource-local mẫu

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Book book = em.find(Book.class, id);
    book.rename(newTitle);

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

Mẫu catch rộng dùng để đảm bảo rollback/cleanup cho transaction thất bại. Phân loại optimistic conflict có thể thực hiện ở tầng service boundary hoặc exception translator, sau khi xem chuỗi nguyên nhân phù hợp.

## 34. Không retry mù quáng mọi optimistic conflict

Có những tác vụ có thể retry an toàn, ví dụ tăng một bộ đếm độc lập với giá trị tuyệt đối nếu phép tính được chạy lại từ state mới và nghiệp vụ cho phép.

Nhưng một cập nhật có ý định:

> “Đổi giá từ 100.000 thành 110.000 vì tôi vừa nhìn thấy giá 100.000”

không nên tự động ghi 110.000 sau khi người khác đã đổi giá thành 200.000. Retry mù có thể ghi đè quyết định mới của người khác.

Phân loại:

| Use case | Chiến lược sau conflict |
| --- | --- |
| Người dùng sửa form | Trả conflict, tải bản mới, cho so sánh/merge có chủ đích |
| Tăng counter theo business rule | Có thể retry command trong transaction mới, giới hạn số lần |
| Job idempotent | Có thể retry sau backoff nếu invariants vẫn đúng |
| Thanh toán/side effect ngoài DB | Phải xem idempotency và transaction/outbox, không retry mù |
| Chuyển trạng thái có điều kiện | Đọc lại state và kiểm tra transition hợp lệ |
| Bulk update không version check | Không tự có OptimisticLockException; thiết kế conditional update riêng |

**Retry phải chạy lại logic trên dữ liệu mới**, không chỉ lặp lại `em.flush()` trên một entity stale.

## 35. Mẫu retry giới hạn và transaction mới

Một ý tưởng với command tự chứa, idempotent theo chính sách:

```java
public void renameWithRetry(
        EntityManagerFactory emf,
        Long bookId,
        String desiredTitle,
        int maxAttempts) {

    if (maxAttempts < 1) {
        throw new IllegalArgumentException("maxAttempts must be positive");
    }

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            Book current = em.find(Book.class, bookId);
            if (current == null) {
                throw new IllegalArgumentException("Book not found");
            }

            // Nghiệp vụ phải cho phép áp dụng lại desiredTitle
            // lên phiên bản mới. Nếu không, trả conflict cho client.
            current.rename(desiredTitle);

            em.getTransaction().commit();
            return;
        } catch (RuntimeException failure) {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }

            if (!isOptimisticFailure(failure) ||
                attempt == maxAttempts) {
                throw failure;
            }
        } finally {
            em.close();
        }
    }
}
```

`isOptimisticFailure` là helper của ứng dụng để nhận diện exception/cause theo provider đang dùng; không phải method JPA chuẩn.

Đoạn code minh họa điểm quan trọng: **mỗi lần retry dùng một EntityManager và transaction mới**. Trong sản phẩm thật nên có backoff/jitter phù hợp, logging, idempotency, phân quyền và quyết định nghiệp vụ rõ. Không dùng retry cho những command mà việc áp lại trên state mới có thể gây mất dữ liệu.

## 36. Spring @Transactional và thời điểm exception

Trong Spring:

```java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void renameBook(Long id, String title) {
        Book book = repository.findById(id)
            .orElseThrow();

        book.rename(title);

        // Không gọi flush tường minh.
        // Commit thường do transaction interceptor thực hiện
        // sau khi method body hoàn tất.
    }
}
```

Với `@Transactional` áp dụng qua Spring proxy, commit thường xảy ra **sau khi method body trả về** trong transaction interceptor.

Vì vậy code đặt catch bên trong method:

```java
@Transactional
public void renameBook(Long id, String title) {
    try {
        Book book = repository.findById(id).orElseThrow();
        book.rename(title);
    } catch (OptimisticLockException ex) {
        handleConflict(ex);
    }
}
```

có thể **không bắt được conflict phát sinh khi transaction interceptor commit bên ngoài method body**.

### Vị trí xử lý ở Spring

- Ở tầng gọi service (nằm ngoài transaction boundary).
- Ở web exception handler như `@ControllerAdvice`.
- Qua Spring exception translation/transaction manager exception chain.
- Hoặc dùng `EntityManager.flush()` trong method nếu cần sớm phát hiện, nhưng vẫn phải xử lý commit failure ở boundary.

Ngoài JPA `OptimisticLockException`, Spring có thể dịch lỗi thành các ngoại lệ như `ObjectOptimisticLockingFailureException` hoặc một subclass của `OptimisticLockingFailureException`. Không giả định mọi lỗi luôn đến controller đúng một class JPA gốc.

### Spring Data JPA `save()`

`repository.save(book)` không bảo đảm mọi SQL ghi/version check đã hoàn tất. Khi entity managed, việc gọi `save` có thể không cần cho dirty checking; với detached entity, Spring Data có thể dùng merge theo chính sách entity state.

`saveAndFlush` yêu cầu flush sớm hơn trong một số use case, nhưng **không commit transaction thay cho transaction manager**.

## 37. Vì sao try/catch đặt sai chỗ dễ bỏ sót lỗi?

Xét:

```java
@Transactional
public void update(Long id, String title) {
    try {
        Book book = em.find(Book.class, id);
        book.rename(title);
        log.info("Update succeeded");
    } catch (OptimisticLockException e) {
        log.warn("Conflict");
    }
}
```

Có hai lỗi thiết kế:

1. **Log thành công trước commit**, khi dirty update có thể chưa được gửi xuống DB.
2. Catch ở body có thể bỏ sót optimistic conflict chỉ phát sinh khi Spring commit.

Tốt hơn:

- Log “đã yêu cầu cập nhật” nếu còn trong transaction.
- Log “đã commit thành công” ở tầng sau transaction completion nếu cần.
- Đặt error mapping ở transaction/API boundary.
- Nếu có side effects, dùng event-after-commit hoặc transactional outbox phù hợp.
- Không nuốt exception trong transaction bị đánh dấu rollback-only.

Một exception handler có thể trả HTTP 409 Conflict khi xác định thật sự có concurrency conflict, nhưng **không tự map mọi `PersistenceException` sang 409**.

## 38. Phân biệt version conflict với lỗi không có bản ghi

Giả sử Book #42 đã bị xóa.

```java
Book book = em.find(Book.class, 42L);
```

Nếu không tìm thấy row, `find` thường trả `null`. Đây là tình huống “not found”, không tự là optimistic conflict.

Nhưng nếu:

1. Transaction tải Book #42 phiên bản 5.
2. Transaction khác xóa Book #42 và commit.
3. Transaction đầu tiên cố update/remove managed Book #42.

thì version-checked UPDATE/DELETE có thể ảnh hưởng 0 row và provider phát `OptimisticLockException` hoặc stale-state failure tương ứng.

Điều khác biệt là **đơn vị công việc đã nắm một phiên bản cũ và đang cố áp dụng thay đổi dựa trên nó**.

Với HTTP API:

- GET một ID chưa tồn tại → thường 404 theo thiết kế.
- PUT/DELETE với expected version cũ → có thể 409/412 theo contract.
- Bản ghi bị xóa giữa lúc đọc và ghi → có thể là conflict, không nhất thiết chỉ là 404.

Ứng dụng cần quy tắc lỗi nhất quán và không tiết lộ thông tin ngoài phạm vi quyền.

## 39. Không phải mọi cập nhật cùng lúc đều xung đột

Giả sử transaction A đổi title của Book #42, transaction B đổi title của Book #43. Hai thao tác khác hàng, không nhất thiết có optimistic conflict.

Nếu A và B cùng update Book #42 nhưng B bắt đầu **sau khi A đã commit và tải version mới**, B có thể cập nhật thành công.

Nếu Book không có `@Version`, provider có thể thực hiện UPDATE mà không phát hiện lost update qua cơ chế version column chuẩn. Một số DB isolation hoặc provider strategy có thể chặn theo cách khác, nhưng không nên gọi đó là bảo đảm `@Version`.

Nếu cả hai transaction chỉ đọc Book #42 và không yêu cầu optimistic lock mode đặc biệt, không nhất thiết có exception dù dữ liệu thay đổi trong lúc chúng đọc.

Do đó, cần xác định **cùng persistent identity? cùng phiên bản cũ? có thao tác version-checked nào không?** rồi mới dự đoán conflict.

## 40. Có thể xảy ra conflict dù ứng dụng chỉ đọc?

Có, nếu ứng dụng **yêu cầu optimistic lock check** trên một entity versioned dù không sửa field.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, id);
em.lock(book, LockModeType.OPTIMISTIC);

// Ứng dụng không sửa Book.
// Transaction khác có thể thay đổi Book và commit.

em.getTransaction().commit(); // Version verification có thể phát hiện conflict.
```

Đây là ý nghĩa của `OPTIMISTIC` lock cho một workflow cần đảm bảo đối tượng không bị sửa trong khoảng hoạt động nhất định theo spec/transaction semantics.

Nhưng:

- Không phải mọi SELECT thông thường đều yêu cầu check như vậy.
- Database isolation và snapshot/lock schedule có thể ảnh hưởng khả năng quan sát conflict.
- Provider có thể thực hiện version verification ở một thời điểm khác.
- Cần active transaction và entity/version mapping phù hợp.

Với `OPTIMISTIC_FORCE_INCREMENT`, dù không sửa field, provider còn có yêu cầu tăng version, có thể dẫn tới UPDATE và conflict.

---

## 41. Tại sao exception không có nghĩa tất cả thay đổi trước đó đã commit?

Giả sử transaction đang flush ba Book:

```text
UPDATE Book A → SQL thành công
UPDATE Book B → SQL thành công
UPDATE Book C → version mismatch → exception
```

Các UPDATE của A/B có thể đã được DB thực thi trong **cùng transaction**, nhưng nếu optimistic conflict khiến transaction rollback, những thay đổi đó cũng bị hoàn tác khi rollback thành công.

Đừng hiểu SQL log có “UPDATE A” là A đã được commit.

Phân biệt:

- **Statement executed:** DB đã chạy SQL trong transaction.
- **Flush succeeded:** provider đã đồng bộ một phần/toàn bộ pending changes theo lượt flush.
- **Commit succeeded:** transaction được xác nhận.
- **Rollback succeeded:** các thay đổi của transaction được hoàn tác ở DB; không tự undo setters trên Java objects.

Sau rollback, các managed/detached objects có thể giữ state trong heap mà DB đã từ chối. Không dùng lại graph cũ để làm kết quả “đã lưu”.

## 42. Có nên dùng `em.refresh()` sau OptimisticLockException?

Nếu mục tiêu là cho người dùng thấy dữ liệu mới, về mặt nghiệp vụ cần đọc lại từ DB. Nhưng không nên gọi `refresh()` rồi cố sửa/commit trên transaction đã lỗi.

Một workflow phù hợp:

```text
Transaction A update thất bại
          │
          ▼
Rollback A
          │
          ▼
Đóng/kết thúc persistence context A
          │
          ▼
Transaction/context B mới
          │
          ▼
Load Book version mới
          │
          ▼
So sánh với command người dùng
          │
          ├─ Có thể áp dụng lại an toàn → retry có kiểm soát
          └─ Cần người dùng quyết định → trả conflict + dữ liệu hiện tại
```

Nếu một transaction khác còn đang thay đổi row, context B cũng có thể nhìn phiên bản khác khi retry; vì vậy phải luôn dựa vào versioning/transaction semantics cho lần ghi mới.

Không lấy exception làm tín hiệu “chỉ refresh là đủ”. Nó là tín hiệu workflow ban đầu không còn hợp lệ theo concurrency policy.

## 43. Chuẩn bị integration test có tính quyết định

Để kiểm tra thời điểm phát hiện conflict, cần:

- Một `EntityManagerFactory` thử nghiệm.
- Một Book đã được insert và **commit**.
- Hai persistence contexts độc lập.
- Một bản stale hoặc một transaction đọc version cũ.
- Transaction khác update và commit.
- Một thao tác update/merge/lock trên bản stale.
- Xác nhận rollback và DB state sau conflict.
- Logging SQL khi cần xác định thời điểm chính xác.

### Không dùng một EntityManager cho cả hai “người dùng”

Sai:

```java
Book a = em.find(Book.class, id);
Book b = em.find(Book.class, id);
```

Trong cùng context, `a` và `b` thường là cùng managed instance. Không có hai snapshot độc lập cạnh tranh; test này không mô phỏng hai transaction như mong muốn.

### Không dùng fixture đang managed từ lúc seed

Nếu vừa `persist` Book trong cùng EntityManager rồi dùng nó làm cả A/B, identity map hoặc pending insert có thể làm test sai. Seed và commit, đóng context, rồi mới chạy concurrency scenario.

## 44. Helper transaction resource-local

Một helper để tạo transaction/context mới cho mỗi unit:

```java
public final class Transactions {

    private final EntityManagerFactory emf;

    public Transactions(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public <T> T call(Function<EntityManager, T> work) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            T result = work.apply(em);

            em.getTransaction().commit();
            return result;
        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                try {
                    em.getTransaction().rollback();
                } catch (RuntimeException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
```

Helper dùng `java.util.function.Function` và resource-local transactions. Với JTA/Spring `@Transactional`, transaction manager phải quản lý commit/rollback, không thay bằng `em.getTransaction()` thủ công.

Các ví dụ JUnit dưới đây giả định helper seed Book và xác định ID có tồn tại. Dự án thực tế cần dùng unique fixture riêng cho mỗi test và tránh database shared state khi chạy song song.

## 45. Integration test: một transaction cập nhật thành công

Trước khi test conflict, cần chứng minh mapping `@Version` hoạt động khi không tranh chấp.

```java
@Test
void singleUpdateIncrementsVersion() {
    Long id = seedBookAndCommit();

    Long before = transactions.call(em -> {
        Book book = em.find(Book.class, id);
        return book.getVersion();
    });

    transactions.call(em -> {
        Book book = em.find(Book.class, id);
        book.rename("Tên mới");
        return null;
    });

    Long after = transactions.call(em -> {
        Book book = em.find(Book.class, id);
        return book.getVersion();
    });

    assertNotNull(before);
    assertNotNull(after);
    assertTrue(after > before);
}
```

Test minh họa với numeric `Long` version. Không phải mọi provider/version strategy đều yêu cầu tăng đúng một đơn vị theo cách có thể assert với mọi mapping. Nếu dùng timestamp version, thay bằng assertion phù hợp.

Mục tiêu: tránh nhầm **mapping `@Version` không hoạt động** với vấn đề timing của exception.

## 46. Integration test: stale detached merge phải bị từ chối

Một test có thể gom toàn bộ thao tác có khả năng ném exception:

```java
@Test
void staleDetachedMergeFailsBeforeOrAtCommit() {
    Long id = seedBookAndCommit();

    Book stale = loadDetachedBook(id);
    Long oldVersion = stale.getVersion();

    transactions.call(em -> {
        Book current = em.find(Book.class, id);
        current.rename("Người khác đã lưu");
        return null;
    });

    assertEquals(oldVersion, stale.getVersion());

    RuntimeException conflict = assertThrows(
        RuntimeException.class,
        () -> transactions.call(em -> {
            em.merge(stale);
            em.flush();
            return null;
        })
    );

    assertTrue(isOptimisticFailure(conflict));
}
```

Test này chấp nhận lỗi tại `merge`, `flush` hoặc `commit` của helper, miễn xác định được optimistic failure từ exception chain.

### Có nên assert exception class chính xác?

Nếu dự án gắn một provider và một transaction manager cố định, có thể viết assertion chính xác theo contract stack đó. Nhưng với tài liệu JPA portable, việc lỗi được bọc ở commit là tình huống cần dự liệu.

Không nên dựa vào thời điểm fail **chỉ vì** một test trên H2/Hibernate cụ thể ném ở `merge`. Version và transaction semantics cần được giữ khi đổi provider.

## 47. Integration test: dữ liệu committed cuối cùng không bị ghi đè

Sau khi transaction B thất bại, cần kiểm tra Book vẫn mang thay đổi của transaction A:

```java
Book latest = loadDetachedBook(id);

assertEquals("Người khác đã lưu", latest.getTitle());
```

Nếu đang dùng shared second-level cache, kiểm soát cache hoặc xác minh DB bằng JDBC/EntityManager mới theo mục tiêu test. Đừng dùng stale Book đang nằm trong EntityManager của transaction thất bại để kiểm tra DB state sau rollback.

Một test đầy đủ nên assert:

- Winner commit thành công.
- Loser nhận optimistic conflict đúng loại.
- Loser transaction rollback.
- Book trong DB không bị thay bởi stale update.
- Version đã thay đổi theo update của winner.
- Không có side effects được xem là thành công trước commit của loser.

## 48. Integration test: conflict ở explicit flush

Để kiểm tra điểm ném ở `flush()` với một provider cụ thể:

```java
@Test
void staleManagedUpdateMayFailAtFlush() {
    Long id = seedBookAndCommit();

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book stale = em.find(Book.class, id);
        Long expected = stale.getVersion();

        // Helper khác cập nhật và commit Book trong
        // EntityManager/transaction độc lập.
        updateWithOtherTransaction(id);

        stale.rename("Stale update");

        // Với provider/DB phù hợp, version mismatch
        // có thể được phát hiện tại đây.
        assertThrows(
            OptimisticLockException.class,
            () -> em.flush()
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
```

Đây là **provider-specific timing test**. Với DB isolation/transaction schedule khác, có thể nhận lock/serialization exception hoặc kiểm tra bị hoãn tới commit. Không nên dùng test này làm yêu cầu bắt buộc của mọi JPA implementation.

Để kiểm thử portable hơn, hãy bao toàn bộ unit of work và kiểm tra optimistic conflict, như test stale detached merge ở trên.

## 49. Integration test: explicit optimistic lock

Nếu ứng dụng dùng:

```java
em.lock(book, LockModeType.OPTIMISTIC);
```

test nên xác định:

1. Transaction A tải Book version V.
2. Transaction B thay đổi và commit version V+1 trong điều kiện transaction isolation cho phép.
3. A yêu cầu/đã yêu cầu optimistic lock.
4. Bất kỳ verification failure nào ở `lock`, `flush` hoặc `commit` được bắt ở transaction boundary.
5. A rollback và không phát side effects thành công.

Không viết test khẳng định provider **luôn** ném ngay trong lời gọi `lock`. Trong JPA, optimistic verification có thể được trì hoãn.

Một test tách khác cho `OPTIMISTIC_FORCE_INCREMENT` nên xác minh version có thay đổi sau commit thành công của transaction có lock, mà không dựa vào giá trị version được đọc ngay sau `lock` trước flush.

## 50. Thực thi `getResultStream()` không làm optimistic conflict biến mất

Nếu sử dụng:

```java
try (Stream<Book> books = em.createQuery(
        "SELECT b FROM Book b WHERE b.price > :minPrice",
        Book.class
    ).setParameter("minPrice", new BigDecimal("100000"))
     .getResultStream()) {

    books.forEach(this::process);
}
```

query vẫn chịu flush mode và transaction semantics. Một provider có thể cần flush pending changes trước khi thực thi/duyệt stream. Nếu có stale entity dirty khác trong context, conflict có thể xuất hiện:

- Khi gọi `getResultStream()`.
- Khi bắt đầu terminal operation.
- Khi provider đọc dữ liệu.
- Khi đóng stream hoặc transaction hoàn tất, tùy implementation.

Tuy nhiên, **Stream không bảo đảm JDBC cursor streaming thực sự**, và thời điểm execution có thể khác. Không đặt logic xử lý optimistic conflict chỉ quanh một dòng `getResultStream` rồi cho rằng traversal không thể lỗi.

Luôn đóng stream có thể giữ JDBC resources bằng `try-with-resources`, và quản lý transaction/context xuyên suốt quá trình tiêu thụ.

## 51. Bảng chẩn đoán: nơi ném lỗi có nói đúng nguyên nhân không?

| Nơi bắt gặp exception | Khả năng cần xem | Hướng xác minh |
| --- | --- | --- |
| `em.merge(detached)` | Detached version stale, provider check sớm | Version của detached vs DB/managed |
| `em.flush()` | Version-checked update/delete thất bại | SQL UPDATE/DELETE với version predicate |
| `commit()` | Flush/check trì hoãn hoặc transaction failure | Exception chain, transaction status |
| JPQL SELECT `getResultList()` | Auto-flush pending dirty entity | SQL UPDATE trước SELECT, flush mode |
| Native SELECT | Provider-native auto-flush strategy | API EntityManager/Session, hints, SQL log |
| `em.lock(OPTIMISTIC)` | Explicit verification | Lock mode, transaction, version |
| `find(..., OPTIMISTIC)` | Load kèm optimistic requirement | Query/lock semantics và timing |
| `remove()` hoặc flush sau remove | Versioned DELETE thất bại | DELETE row count/version |
| `saveAndFlush` Spring Data | Flush chủ động trong repository | Spring exception translation |
| Spring service caller | Commit diễn ra sau method body | Transaction interceptor exception |
| JDBC batch execution | Một statement trong batch stale | Batch diagnostics, version columns |
| Row-count mismatch trong native/bulk DML | Có thể do ứng dụng kiểm tra thủ công | SQL WHERE version, affected rows |
| Getter sau khi transaction khác update | Thường chưa phải điểm check | First-level cache và managed state |

**Stack trace chỉ cho biết vị trí provider phát hiện hoặc chuyển tiếp lỗi**, không nhất thiết là dòng code đầu tiên làm trạng thái trở nên stale.

## 52. Một chuỗi sự kiện thường gặp trong production

Ví dụ REST API cập nhật Book:

```text
GET /books/42
    ↓
Client nhận version=5
    ↓
Client chỉnh form trong vài phút
    ↓
Một client khác cập nhật Book → version=6
    ↓
PUT /books/42 gửi expectedVersion=5
    ↓
Service bắt đầu transaction
    ↓
Service tìm Book hiện tại (version=6)
    ↓
Phát hiện version không khớp ngay bằng business check
    hoặc cố merge detached entity version 5
    ↓
JPA version verification tại merge/flush/commit
    ↓
Optimistic conflict
    ↓
Rollback + kết thúc persistence context
    ↓
HTTP response: conflict theo API contract
```

Có **hai lớp kiểm tra**:

1. Application-level expected-version check từ command/DTO có thể chủ động báo conflict sớm trước khi setter.
2. JPA `@Version` check khi flush/commit giúp chống race giữa thời điểm business check và thời điểm ghi DB.

Nếu server đã tải bản version 6 và chỉ đổi title mà **không dùng expectedVersion 5 từ client**, request có thể ghi đè lựa chọn của người khác một cách hợp lệ theo góc nhìn entity vừa load version 6. Do đó `@Version` không tự giải quyết **stale client intent** trừ khi version/token từ client được đưa vào concurrency policy.

## 53. DTO version là token, không tự tạo quyền quản lý

Response DTO:

```java
public record BookDetail(
    Long id,
    String title,
    BigDecimal price,
    Long version
) {}
```

Command:

```java
public record RenameBookCommand(
    String newTitle,
    Long expectedVersion
) {}
```

Trong transaction:

```java
Book current = em.find(Book.class, bookId);

if (current == null) {
    throw new NotFoundException("Book not found");
}

if (!Objects.equals(
        current.getVersion(),
        command.expectedVersion())) {
    throw new OptimisticLockException(
        "Client was based on an old version"
    );
}

current.rename(command.newTitle());
```

Ở đây application chủ động ném `OptimisticLockException` sớm khi phát hiện token cũ. Đó là **business-level precondition check**, khác với exception do JPA provider ném khi SQL version check thất bại.

Cần lưu ý:

- JPA `@Version` vẫn phải bảo vệ update ở DB để ngăn race sau so sánh.
- Authorization/tenant validation phải xảy ra đúng phạm vi.
- Không nên cho client tự đặt version của entity managed.
- DTO không phải entity; `em.merge(dto)` không áp dụng.
- Có thể dùng HTTP `ETag`/`If-Match` hoặc 409/412 theo API contract.

Nếu use case trả HTTP 412 Precondition Failed khi If-Match không khớp, hãy phân biệt với 409 Conflict do transaction-level collision theo thiết kế API.

## 54. Xử lý với Spring và exception translation

Trong một ứng dụng Spring Data JPA/Hibernate:

```java
@Transactional
public void rename(Long id, RenameBookCommand command) {
    Book book = repository.findById(id).orElseThrow();

    checkExpectedVersion(book, command.expectedVersion());

    book.rename(command.newTitle());
}
```

Lỗi có thể xuất hiện:

- Ngay trong `checkExpectedVersion` nếu application phát hiện sớm.
- Trong repository flush nếu gọi `saveAndFlush` hoặc `EntityManager.flush()`.
- Khi Spring transaction interceptor commit sau method body.
- Trong query phát auto-flush trước đó.
- Trong Hibernate provider stack rồi được Spring dịch sang `OptimisticLockingFailureException`/subtype.

Vì vậy nên có một **error boundary** ở tầng ngoài transaction để chuẩn hóa lỗi cho API.

Ví dụ khái niệm:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<ApiError> onOptimisticConflict(
            OptimisticLockingFailureException ex) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "CONFLICT",
                "Dữ liệu đã thay đổi. Vui lòng tải lại."
            ));
    }
}
```

Các class Spring và `ApiError` trong ví dụ cần import/định nghĩa tùy dự án; đây không phải JPA standard API. Một handler production có thể cần xử lý cả JPA `OptimisticLockException` không được translate và wrapper causes theo transaction manager.

**Không đưa tên exception provider/SQL statement/stack trace vào HTTP response**, vì thông tin đó có thể làm lộ nội bộ hệ thống.

## 55. Checklist trước khi kết luận thời điểm xảy ra lỗi

1. Entity có thuộc tính `@Version` hợp lệ không?
2. Version nằm ở field nào và kiểu nào?
3. Có transaction khác đã commit update/delete không?
4. Hai thao tác có cùng persistent identity không?
5. Entity trong transaction hiện tại managed hay detached?
6. Nếu detached, version được giữ lại đúng từ lần đọc ban đầu không?
7. Có đang gọi `merge()` không và provider check version ở bước nào?
8. Có thay đổi persistent state khiến entity trở nên dirty không?
9. Có gọi `flush()` tường minh không?
10. Nếu không flush, transaction manager commit ở đâu?
11. Có JPQL/Criteria/native query phát auto-flush giữa chừng không?
12. Flush mode của context/query là AUTO hay COMMIT?
13. Có explicit `OPTIMISTIC` hoặc `OPTIMISTIC_FORCE_INCREMENT` không?
14. Có query `setLockMode(...)` hoặc `find(..., lockMode)` không?
15. Có SQL `UPDATE/DELETE ... WHERE version = ?` thực sự không?
16. Có đang dùng bulk JPQL/native SQL bypass versioning không?
17. JDBC batching có che vị trí statement thất bại không?
18. Exception được ném trực tiếp hay bọc trong `RollbackException`/Spring exception?
19. Có phải optimistic failure thật hay serialization/deadlock/constraint failure?
20. Khi lỗi xảy ra, transaction có rollback-only không?
21. Code có vô tình catch rồi tiếp tục flush/commit không?
22. Có retry trong một **transaction/context mới** không?
23. Retry có áp dụng lại business rule trên state mới không?
24. HTTP request có mang expected version/ETag để bảo vệ stale client intent không?
25. Có log “thành công” hoặc publish side effect trước commit không?
26. Test có hai persistence contexts thực sự độc lập không?
27. Fixture đã seed/commit trước khi bắt đầu concurrency scenario chưa?
28. Test có kiểm tra DB state cuối cùng bằng context mới không?
29. Có test trên database/isolation/provider tương đương production không?
30. Có phân biệt vị trí **phát hiện lỗi** với thời điểm dữ liệu đã **trở nên stale** không?

Checklist này hữu ích khi debug những lỗi chỉ xuất hiện dưới tải cao, khi thêm một query vào service, khi thay provider hoặc khi chuyển một update entity sang bulk SQL.

## 56. Bài tập thực hành

### Bài tập 1: Setter có phải điểm ném lỗi?

```java
Book book = em.find(Book.class, id);
book.rename("Tên mới");
```

**Câu hỏi:** Nếu Book đã bị transaction khác sửa, dòng `rename` bắt buộc ném `OptimisticLockException` không?

**Đáp án:** Không. Setter thường chỉ sửa state Java; lỗi thường được phát hiện khi provider kiểm tra version ở flush/commit hoặc thao tác lock/merge liên quan.

### Bài tập 2: Lỗi tại SELECT

```java
book.rename("Tên mới");

List<Book> books = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
).setParameter("title", "Tên mới")
 .getResultList();
```

**Câu hỏi:** Vì sao exception có thể nằm ở `getResultList()`?

**Đáp án:** AUTO query có thể kích hoạt flush pending update trước khi SELECT; version check thất bại ở UPDATE và exception được ném tại query execution.

### Bài tập 3: Không gọi flush

```java
book.rename("Tên mới");
em.getTransaction().commit();
```

**Câu hỏi:** Exception có thể xuất hiện ở đâu?

**Đáp án:** Trong quá trình commit, khi provider đồng bộ/check version. Có thể bị bọc trong `RollbackException` hoặc wrapper của transaction manager.

### Bài tập 4: Merge detached

Detached Book version 3, database Book version 4.

**Câu hỏi:** `em.merge(detached)` chắc chắn ném ngay không?

**Đáp án:** Không. JPA provider có thể check version khi merge, tại flush hoặc commit. Bắt lỗi ở boundary của đơn vị công việc.

### Bài tập 5: Explicit lock

```java
em.lock(book, LockModeType.OPTIMISTIC);
```

**Câu hỏi:** Nếu không ném ngay, nghĩa là version sẽ không xung đột khi commit?

**Đáp án:** Không. Optimistic verification có thể được trì hoãn.

### Bài tập 6: Force increment

`em.lock(book, OPTIMISTIC_FORCE_INCREMENT)` rồi đọc `book.getVersion()` ngay.

**Câu hỏi:** Có chắc version đã tăng trong object/DB chưa?

**Đáp án:** Không nên dựa vào thời điểm tăng cụ thể ngay sau lock. Kiểm tra sau flush/commit theo provider/transaction semantics.

### Bài tập 7: Bulk JPQL UPDATE

```java
UPDATE Book b SET b.price = :price WHERE b.id = :id
```

**Câu hỏi:** `@Version` trên Book tự bảo vệ câu bulk UPDATE không?

**Đáp án:** Không như dirty-checked managed entity update. Cần version predicate/increment có chủ đích và kiểm tra row count nếu muốn optimistic semantics.

### Bài tập 8: Native SQL

```sql
UPDATE books SET title = ? WHERE id = ?;
```

**Câu hỏi:** Có cơ chế version check không?

**Đáp án:** Không có nếu query không thêm `AND version = ?` hoặc cơ chế DB riêng. Native DML không tự kế thừa mọi JPA version handling.

### Bài tập 9: Spring transactional method

`@Transactional` method đổi title rồi return mà không gọi flush.

**Câu hỏi:** Catch quanh method body có chắc bắt conflict commit không?

**Đáp án:** Không. Spring transaction interceptor có thể commit sau method body. Xử lý ở boundary ngoài transaction.

### Bài tập 10: Rollback

Flush ném OptimisticLockException, code catch rồi gọi refresh và commit tiếp.

**Câu hỏi:** Có đúng không?

**Đáp án:** Không nên. Transaction thường rollback-only; rollback và dùng context/transaction mới.

### Bài tập 11: Hai EntityManager

Hai lần `find` trong cùng EntityManager được gọi là hai transaction cạnh tranh.

**Câu hỏi:** Vì sao sai?

**Đáp án:** Cùng persistence context có identity map; cùng persistent identity thường trả cùng managed instance. Cần contexts/transactions độc lập.

### Bài tập 12: Data race sau flush

Flush thành công, sau đó ứng dụng gửi email rồi commit thất bại.

**Câu hỏi:** Điểm sai trong thiết kế?

**Đáp án:** Flush không phải commit. Side effect không thể rollback cần được phối hợp sau commit hoặc qua transactional outbox/idempotent workflow.

### Bài tập 13: GET và optimistic locking

GET Book một lần, transaction khác cập nhật Book, GET lại trong cùng context.

**Câu hỏi:** Có bắt buộc nhận OptimisticLockException không?

**Đáp án:** Không nếu chỉ `find`/getter thông thường mà không yêu cầu optimistic lock/check hoặc update. Identity map có thể giữ state cũ.

### Bài tập 14: Update khác field

Transaction A sửa title, B sửa price của cùng Book version 5.

**Câu hỏi:** Có thể B bị conflict dù không sửa cùng field không?

**Đáp án:** Có. Entity-level version thường đại diện cho một persistent row/entity, không nhất thiết từng field. B vẫn dùng version 5 trong khi A đã tăng version.

### Bài tập 15: Xóa cùng Book

A xóa Book và commit; B đang giữ Book cũ rồi cố update.

**Câu hỏi:** B có thể gặp lỗi nào?

**Đáp án:** Version-checked UPDATE ảnh hưởng 0 row và có thể gây OptimisticLockException/stale state error; SQL/DB provider cũng có thể trả lỗi khác tùy workflow.

### Bài tập 16: Exception wrapper

`commit()` ném `RollbackException` chứa `OptimisticLockException`.

**Câu hỏi:** Nếu chỉ catch OptimisticLockException trực tiếp, có thể bỏ sót không?

**Đáp án:** Có. Phân loại chuỗi nguyên nhân và contract transaction manager.

### Bài tập 17: Retry

Một request đổi giá dựa trên giá đã xem; conflict vì người khác đổi giá thành giá mới.

**Câu hỏi:** Có nên tự retry bằng cách ghi giá cũ lên bản mới không?

**Đáp án:** Không mặc định. Cần kiểm tra business intent; có thể trả conflict và cho người dùng quyết định.

### Bài tập 18: Đo chính xác timing

Một integration test assert exception luôn tại `em.flush()`, nhưng đổi provider thì exception tới `commit()`.

**Câu hỏi:** Test nào portable hơn?

**Đáp án:** Test toàn transaction boundary với expectation là optimistic failure được nhận diện, không buộc một method cụ thể; timing test nên gắn với provider/version/DB riêng.

## 57. Tóm tắt ra quyết định

Khi xử lý một thao tác ghi có `@Version`, hãy dùng mô hình:

```text
Ứng dụng tải entity version V
          │
          ▼
Transaction khác có thể cập nhật lên V+1
          │
          ▼
Ứng dụng sửa managed entity / merge detached
          │
          ▼
Điểm kiểm tra có thể xuất hiện:
   ├─ merge()
   ├─ lock()/find(..., OPTIMISTIC)
   ├─ query-triggered auto-flush
   ├─ explicit flush()
   └─ transaction commit()
          │
          ├─ Version phù hợp → thao tác có thể tiến tới commit
          │
          └─ Version không phù hợp
                    │
                    ▼
            OptimisticLockException
            hoặc wrapper/DB concurrency failure
                    │
                    ▼
            Rollback transaction
                    │
                    ▼
            Đọc lại, báo conflict hoặc retry có kiểm soát
```

Điểm mấu chốt trong sơ đồ là **có nhiều vị trí kiểm tra**, nhưng chỉ một nguyên tắc xử lý nhất quán: đừng coi setter/merge/flush thành công là bằng chứng transaction chắc chắn đã commit.

## Kết luận

**Lỗi khóa lạc quan trong JPA có thể được phát hiện tại nhiều thời điểm**, không chỉ khi gọi `commit()`. Với managed entity có `@Version`, việc thay đổi bằng setter thường chỉ làm object dirty; optimistic version check có thể xảy ra khi `flush()` hoặc commit. Một query trong `AUTO` có thể gây auto-flush nên `getResultList()`, `getSingleResult()` hoặc một thao tác truy vấn khác cũng có thể trở thành nơi exception xuất hiện.

Với detached entity, stale version có thể được kiểm tra **ngay lúc `merge()` hoặc được trì hoãn**. Các thao tác `lock(..., OPTIMISTIC)`, `OPTIMISTIC_FORCE_INCREMENT`, `find` hoặc query kèm optimistic lock mode cũng có khả năng phát hiện xung đột tại một điểm khác với nơi ứng dụng lần đầu yêu cầu lock. Thời điểm chính xác phụ thuộc provider, flush mode, transaction và database isolation.

Quan trọng không kém là biết **khi nào không có bảo vệ tự động**: bulk JPQL DML hoặc native SQL không tự áp dụng đầy đủ cơ chế version check của per-entity managed updates. Không nên dựa vào `@Version` để bảo vệ câu `UPDATE ... WHERE id = ?` nếu SQL không kiểm tra phiên bản phù hợp.

Khi ngoại lệ xảy ra, transaction thường phải rollback. Hãy xử lý conflict ở **ranh giới transaction**, nhận diện cả exception wrapper, không tiếp tục sửa cùng persistence context đã thất bại và chỉ retry bằng transaction mới khi business rule cho phép. Integration test nên dùng dữ liệu đã commit, nhiều persistence contexts độc lập, kiểm tra database state sau rollback và tránh buộc mọi provider phải ném exception ở cùng một method Java.

Câu hỏi đúng khi debug không phải chỉ là **“Dòng nào ném lỗi?”** mà là **“Entity đang giữ version nào, database đã sang version nào, thao tác nào kích hoạt version check, kiểm tra ấy diễn ra trong transaction nào và kết quả commit cuối cùng là gì?”**. Trả lời rõ năm câu hỏi đó sẽ giúp xác định đúng thời điểm xung đột, vị trí phát hiện lỗi và cách xử lý optimistic locking an toàn.
