# Xử lý entity trong bộ nhớ sau khi rollback

Khi một giao dịch thất bại trong JPA, lập trình viên thường gọi `rollback()` và kỳ vọng mọi thứ trở lại trạng thái ban đầu. **Database có thể hoàn tác các thao tác ghi thuộc transaction, nhưng Java object không tự động quay ngược những setter, method nghiệp vụ hoặc thay đổi collection đã chạy trong bộ nhớ.**

Đây là điểm cốt lõi của bài **“Xử lý entity trong bộ nhớ sau khi rollback”**, thuộc chương **Giao dịch** của chủ đề **Data Persistence Relational Access ORM JPA**.

Giả sử một giao dịch thay đổi tên sách:

```java
Book book = entityManager.find(Book.class, 42L);
book.rename("JPA nâng cao");
entityManager.getTransaction().rollback();
```

Sau rollback, hàng database có thể vẫn giữ tên cũ, nhưng biến Java `book` có thể vẫn trả về `"JPA nâng cao"`. Thậm chí object có thể giữ một ID mới sinh, một version đã thay đổi hoặc một collection đã được bổ sung phần tử, dù các thay đổi tương ứng không được commit.

Vì thế, xử lý rollback đúng đòi hỏi phân biệt rõ **bốn lớp trạng thái**:

1. **Trạng thái Java object**: field, tham chiếu, collection, cờ và dữ liệu đang nằm trong heap.
2. **Persistence context**: các entity nào còn được quản lý, những thay đổi nào đã được theo dõi hoặc chờ flush.
3. **Database transaction**: câu SQL nào đã được thực thi và có được commit hay đã rollback.
4. **Tác động bên ngoài database**: email, message, HTTP call, file, cache và những side effect không nhất thiết chịu sự điều khiển của cùng transaction.

Bài viết sẽ đi từ ví dụ cơ bản đến cách tổ chức transaction, xử lý entity mới/đã sửa/chờ xóa, vấn đề ID và version, retry, Spring/Jakarta EE, và bài tập để nhận biết những lỗi thường gặp.

## 1. Rollback thực sự hoàn tác điều gì?

Một transaction quan hệ có thể gồm:

```sql
BEGIN;

UPDATE books
SET title = 'JPA nâng cao'
WHERE id = 42;

INSERT INTO audit_logs(entity_id, action)
VALUES (42, 'RENAME_BOOK');

ROLLBACK;
```

Khi rollback thành công, các thay đổi SQL **thuộc transaction đó** được hoàn tác theo ngữ nghĩa của hệ quản trị dữ liệu. Tuy nhiên, rollback không tương đương với việc ứng dụng tự gọi lại:

```java
book.rename(oldTitle);
auditLogs.remove(newAuditLog);
```

JPA và database không thể tự đảo ngược tùy ý mọi thao tác Java đã chạy:

- Setter có thể đã thay đổi field.
- Collection có thể đã thêm/xóa phần tử.
- Object mới có thể đã được tạo và giữ bởi những biến khác.
- Một ID hoặc sequence value có thể đã được cấp.
- Event trong bộ nhớ có thể đã được phát.
- Email hoặc HTTP request gửi ra bên ngoài có thể đã hoàn tất.

Hình dung:

```text
                    Giao dịch trước lỗi
                           │
          ┌────────────────┼───────────────────┐
          ▼                ▼                   ▼
     Java heap       Persistence context    Database
 book.title="Mới"    Book dirty             title="Cũ"
          │                │                   │
          │                └── flush ─────────►│ title="Mới"
          │                                    │ (chưa commit)
          └──────────────────── rollback ─────►│
          │                                    │ title="Cũ"
          ▼                                    ▼
 Java object có thể                        DB đã hoàn tác
 vẫn title="Mới"                           transaction
```

**Rollback database không phải một chức năng “undo object graph” trong JVM.**

### Không đồng nhất các mốc thời gian

| Sự kiện | Điều chắc chắn nên hiểu |
| --- | --- |
| Gọi setter trên managed entity | State Java đã đổi; SQL chưa chắc đã chạy |
| Gọi `persist()` | Entity được đưa vào vòng đời persistence; INSERT có thể được hoãn hoặc xảy ra sớm |
| Gọi `flush()` | Provider đồng bộ thay đổi xuống database trong transaction phù hợp; chưa commit |
| Query kích hoạt auto-flush | Một số SQL ghi có thể đã chạy trước SELECT; chưa commit |
| Gọi `commit()` thành công | Database transaction được xác nhận theo quy tắc DB |
| Gọi `rollback()` thành công | SQL thuộc transaction được hoàn tác; object Java không tự phục hồi |
| Có lỗi khi commit | Không được mặc định transaction đã commit; cần dựa vào contract và xử lý tình huống kết quả không chắc chắn |

Cần biết **transaction đã thực sự rollback thành công** trước khi tin trạng thái database được hoàn tác. Với sự cố mạng hoặc lỗi kết nối khi commit, ứng dụng đôi khi không thể xác định ngay kết quả cuối cùng; khi đó cần cơ chế kiểm tra hoặc idempotency thay vì tự kết luận chắc chắn.

## 2. Entity minh họa

Ta dùng entity `Book` với các field title, price và version:

```java
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
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    protected Book() {
        // JPA cần constructor không tham số.
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
            throw new IllegalArgumentException("title");
        }
        title = newTitle.trim();
    }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice, "price");
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
        price = newPrice;
    }
}
```

Cấu trúc database minh họa:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL
);
```

Ví dụ giả định hàng đang có:

| id | version | title | price |
| ---: | ---: | --- | ---: |
| 42 | 3 | JPA cơ bản | 180000.00 |

Một transaction có thể nạp `Book #42`, đổi title/price và sau đó rollback vì bất kỳ nguyên nhân nào: lỗi unique constraint, foreign key, optimistic locking, exception nghiệp vụ hoặc lỗi tại commit.

## 3. Entity managed sau rollback: object không tự phục hồi

Xét đoạn code resource-local JPA:

```java
EntityManager em = emf.createEntityManager();
Book book;

try {
    em.getTransaction().begin();

    book = em.find(Book.class, 42L);
    book.rename("JPA nâng cao");
    book.changePrice(new BigDecimal("250000.00"));

    em.flush(); // SQL có thể đã thực thi trong transaction.

    em.getTransaction().rollback();
} finally {
    em.close();
}
```

Database không lưu thay đổi vừa rollback. Nhưng object Java `book` không có cơ chế tổng quát khiến:

```java
book.getTitle()
```

tự động trả lại giá trị cũ `"JPA cơ bản"`. Trong tình huống thông thường, field đã được setter thay đổi vẫn là `"JPA nâng cao"`.

Phân biệt:

```text
Sau rollback thành công:

Database:
  books.id = 42
  title = "JPA cơ bản"
  price = 180000.00

Java variable book:
  id = 42
  title = "JPA nâng cao"       ← giá trị từng gán
  price = 250000.00           ← giá trị từng gán
```

**Object Java không phải là bằng chứng trạng thái database sau rollback.**

### Vì sao không có cơ chế tự đảo setter?

Provider có thể giữ snapshot phục vụ dirty checking hoặc optimistic locking, nhưng những snapshot đó không phải contract rằng sau rollback provider sẽ hồi phục mọi field, every collection, transient reference, domain event hoặc giá trị được tính bằng business method.

Một setter có thể có tác dụng phụ:

```java
public void rename(String newName) {
    this.title = newName;
    this.slug = createSlug(newName);
    this.history.add("Renamed to " + newName);
}
```

Dù database rollback, JPA không có nghĩa vụ tự chạy một thuật toán đảo tất cả các thay đổi trong Java object graph. Cách xử lý an toàn là **không tiếp tục xem object đó như nguồn sự thật đã được đồng bộ**.

## 4. Persistence context sau rollback có thể sử dụng tiếp không?

Sau một transaction rollback, cần phân biệt **entity instance**, **persistence context** và **EntityManager handle**.

Với các persistence context gắn với transaction, khi transaction kết thúc bằng rollback, context tương ứng cũng kết thúc; những entity từng được nó quản lý trở thành detached. Với các dạng context mở rộng hoặc application-managed, quy tắc rollback có các chi tiết lifecycle riêng; nói chung không nên giả định context tiếp tục giữ được trạng thái managed nhất quán của transaction vừa lỗi.

Một điểm thực dụng:

> **Sau rollback hoặc lỗi persistence khiến transaction thất bại, đừng tiếp tục dùng object graph đang sửa như thể nó vẫn managed và nhất quán với database.**

Với resource-local `EntityManager`, handle có thể vẫn ở trạng thái mở sau rollback trong một số tình huống. Tuy nhiên, “`em.isOpen() == true`” **không phải bằng chứng rằng persistence context giữ một trạng thái an toàn để tiếp tục transaction cũ**.

Đặc biệt sau lỗi database/ORM, lựa chọn rõ ràng và an toàn thường là:

1. Rollback nếu transaction đang active và rollback còn thực hiện được.
2. Đóng `EntityManager` của đơn vị công việc thất bại.
3. Bỏ những entity đang giữ state liên quan transaction đó.
4. Mở một `EntityManager`/transaction mới.
5. Đọc lại entity từ DB và áp dụng lại **ý định nghiệp vụ hợp lệ**, không sao chép vô điều kiện object cũ.

Sơ đồ:

```text
Transaction thất bại
        │
        ▼
rollback()
        │
        ▼
Kết thúc đơn vị công việc và đóng/bỏ context
        │
        ├── Không dùng tiếp entity cũ như managed
        │
        └── Khi cần retry/đọc lại:
                    │
                    ▼
             EntityManager mới
                    │
                    ▼
             find(id) từ DB
                    │
                    ▼
             Áp dụng lại command
                    │
                    ▼
             Transaction mới
```

Không nên dùng `clear()` hoặc `refresh()` như thao tác “hồi sinh” một transaction đã lỗi và bỏ qua rollback. Chúng có ý nghĩa riêng và cần context/trạng thái phù hợp.

## 5. `em.contains(entity)` sau rollback có nói được hàng còn tồn tại không?

Không. `EntityManager.contains(entity)` kiểm tra **instance có được quản lý trong persistence context hiện tại hay không**, không kiểm tra database có hàng hay không.

Trước rollback:

```java
Book book = em.find(Book.class, 42L);
System.out.println(em.contains(book)); // true nếu tìm thấy và managed
```

Sau rollback, kết quả `contains` còn phụ thuộc lifecycle context/EntityManager. Dù trả `false`, điều đó **không có nghĩa hàng Book #42 đã bị xóa**. Object có thể detached trong khi hàng database vẫn tồn tại.

Tương tự:

```java
book.getId() != null
```

không chứng minh object đang managed hoặc database còn hàng tương ứng.

| Dấu hiệu | Điều nó biểu thị | Điều không thể suy ra |
| --- | --- | --- |
| `book.getId() != null` | Java object có giá trị ID | Hàng đã commit/tồn tại/managed |
| `em.contains(book) == false` | Object không managed trong context đó | Hàng đã bị xóa hoặc chưa từng có |
| `em.isOpen() == true` | EntityManager handle chưa đóng | Context sau lỗi đáng tin và có thể retry an toàn |
| `book.getTitle()` | State hiện tại của Java object | Giá trị đang commit trong database |
| `rollback()` thành công | Transaction DB đã hoàn tác thay đổi của nó | Các field/collection Java đã quay lại |
| `em.find(Book.class, id)` trong context mới | Managed instance tương ứng DB state mà query nhìn thấy | Mọi vấn đề concurrency đã được giải quyết |

**Đừng dùng trạng thái một biến Java sau rollback để dự đoán kết quả transaction.**

## 6. Ví dụ an toàn: rollback rồi đọc lại bằng EntityManager mới

Một cách triển khai đơn giản cho thao tác cập nhật:

```java
public void renameBook(
        EntityManagerFactory emf, Long id, String newTitle) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }

        book.rename(newTitle);

        em.getTransaction().commit();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Trong phương thức trên, không trả entity `book` sau lỗi. Nếu caller cần trạng thái hiện tại sau khi transaction thất bại, hãy truy vấn trong một đơn vị công việc khác:

```java
public BookSnapshot loadBookSnapshot(
        EntityManagerFactory emf, Long id) {

    EntityManager em = emf.createEntityManager();
    try {
        Book book = em.find(Book.class, id);
        if (book == null) {
            return null;
        }

        return new BookSnapshot(
            book.getId(),
            book.getTitle(),
            book.getPrice(),
            book.getVersion()
        );
    } finally {
        em.close();
    }
}

public record BookSnapshot(
    Long id,
    String title,
    BigDecimal price,
    Long version
) {}
```

DTO `BookSnapshot` diễn đạt dữ liệu đọc được ở thời điểm truy vấn; không phơi bày một managed entity kéo dài vòng đời ngoài context.

### Vì sao lại dùng context mới?

Nếu tái sử dụng object cũ, không thể biết chắc field hiện tại là trạng thái đã commit hay trạng thái do transaction thất bại để lại. Với context mới, ứng dụng có một ngữ cảnh rõ ràng để nạp lại hàng database theo isolation/locking hiện tại.

Cũng cần hiểu rằng nếu transaction khác đã commit sau khi transaction của ta rollback, trạng thái mới đọc được **không nhất thiết bằng đúng bản snapshot trước khi ta bắt đầu**. Nó là dữ liệu đang nhìn thấy theo transaction isolation của lần đọc mới.

## 7. Entity mới `persist()` rồi rollback: ID không chứng minh dữ liệu đã lưu

Đây là tình huống gây lỗi phổ biến.

```java
Book book = new Book(
    "Java Persistence",
    new BigDecimal("150000.00")
);

em.getTransaction().begin();
em.persist(book);

// Có thể ID đã được cấp ở đây hoặc sau flush.
em.flush();

Long generatedId = book.getId();

em.getTransaction().rollback();
```

Sau rollback:

- Hàng Book mới không được commit trong transaction vừa rollback.
- Java object `book` vẫn tồn tại.
- `book.getId()` **có thể vẫn mang giá trị vừa được cấp**.
- Giá trị sequence/identity đã tiêu thụ không nhất thiết được lấy lại.
- Không thể dùng `generatedId != null` làm bằng chứng một bản ghi Book tồn tại.

Sơ đồ:

```text
Book mới:
  id = null
  title = "Java Persistence"

persist/flush:
  id = 123              ← giá trị có thể được cấp
  INSERT id=123         ← thuộc transaction chưa commit

rollback:
  DB không còn hàng do transaction tạo
  Java Book có thể vẫn id=123
```

Không nên “retry” bằng cách gọi `persist(book)` nguyên object cũ trong một context mới mà không suy xét state/ID strategy. Với khóa sinh tự động, object có ID có thể bị provider phân loại khác với một entity mới, dẫn đến lỗi về detached entity, identity hoặc duplicate key tùy mapping.

### Cách retry dễ kiểm soát hơn

Thay vì tái sử dụng entity đã tham gia transaction lỗi, giữ một **command/DTO thuần dữ liệu**:

```java
public record CreateBookCommand(
    String title,
    BigDecimal price
) {}
```

Mỗi attempt tạo một entity mới và transaction mới:

```java
public Long createBookOnce(
        EntityManagerFactory emf,
        CreateBookCommand command) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = new Book(
            command.title(),
            command.price()
        );
        em.persist(book);

        em.getTransaction().commit();
        return book.getId();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Nếu có chính sách retry, mỗi attempt có thể gọi lại method trên với **cùng command bất biến** nhưng tạo `Book` mới. Cần kết hợp idempotency key/natural key nếu việc lặp request có nguy cơ tạo nhiều bản ghi hoặc kết quả commit trước đó không chắc chắn.

### Vì sao sequence có thể bị “nhảy số”?

Nhiều cơ chế cấp số sequence/identity không rollback bộ đếm cùng với các DML của transaction. Sau rollback, ID 123 có thể không được tái sử dụng và lần tạo tiếp theo nhận 124 hoặc số khác.

**Khoảng trống ID không phải tự nó là bằng chứng mất dữ liệu**. Đừng thiết kế logic nghiệp vụ phụ thuộc ID phải liên tục.

## 8. Entity bị sửa rồi rollback: tránh merge object stale

Giả sử transaction tải `Book #42`, sửa giá rồi rollback:

```java
Book detachedAfterFailure = ...;
detachedAfterFailure.changePrice(
    new BigDecimal("999999.00")
);
```

Nếu sau đó mở transaction mới và gọi:

```java
Book managed = newEm.merge(detachedAfterFailure);
```

thì `merge()` có thể **sao chép state của object cũ vào managed entity**, bao gồm giá `999999.00` vốn là thay đổi đã bị rollback và đáng lẽ không còn được áp dụng.

Đây là một lỗi logic nghiêm trọng: ứng dụng vô tình **ghi lại thay đổi của transaction đã thất bại**.

### `merge()` không có nghĩa “phục hồi từ DB”

`EntityManager.merge(detached)` dùng để hợp nhất state của một entity detached vào managed instance tương ứng. Nó **không phải** lệnh bỏ thay đổi local rồi đọc dữ liệu mới nhất từ database.

| Mục tiêu | Cách tiếp cận thường phù hợp |
| --- | --- |
| Bỏ thay đổi từ transaction lỗi | Bỏ object/graph cũ, nạp lại entity trong context mới |
| Cập nhật một vài field hợp lệ từ request | Nạp managed entity mới rồi gọi domain methods cho field được phép |
| Đồng bộ detached graph có chủ đích | Dùng `merge()`, quản lý version/cascade và kết quả trả về |
| Lấy lại state DB cho một entity managed hợp lệ | Dùng `refresh()` khi contract/trạng thái cho phép |
| Retry một thao tác nghiệp vụ | Chạy lại command trong transaction mới, không tái dùng graph lỗi |

Nếu nghiệp vụ cần một phần thay đổi được phép giữ sau rollback, hãy **trích xuất ý định** sang command có validation, chứ không âm thầm merge toàn bộ object đã stale.

## 9. Entity chờ xóa `remove()` rồi rollback

Với entity đã tồn tại:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
em.remove(book);

em.flush(); // DELETE có thể đã chạy, nhưng chưa commit.

em.getTransaction().rollback();
```

Sau rollback thành công:

- Hàng Book #42 có thể vẫn tồn tại trong database, vì DELETE thuộc transaction bị hoàn tác.
- Java object `book` vẫn tồn tại trong heap.
- Không nên coi object đó đã “khôi phục trạng thái managed bình thường” để tiếp tục sửa/commit ở một context bất kỳ.
- Để xử lý tiếp, nên đọc Book #42 vào một transaction/context mới.

Sơ đồ:

```text
Trước:
  DB: Book #42 tồn tại
  Context: Book #42 managed

remove():
  Context: Book #42 marked for removal

flush():
  DB transaction: DELETE #42 đã thực thi
  Chưa commit

rollback():
  DB: hoàn tác DELETE, Book #42 còn tồn tại
  Java object: không tự trở thành managed trong context mới
```

### Nếu object bị xóa còn liên kết với entity khác?

`Book` có thể thuộc `Author.books` hoặc `Order.items`. Sau khi ứng dụng gọi helper xóa liên kết và `remove(book)`, các collection Java có thể đã bị sửa:

```java
author.getBooks().remove(book);
em.remove(book);
em.getTransaction().rollback();
```

Database rollback các DML, nhưng collection `author.getBooks()` trong object graph cũ **không tự được thêm lại `book`**. Nếu tiếp tục dùng collection ấy, nghiệp vụ có thể tưởng quan hệ đã được gỡ thành công.

Vì thế, khi rollback một graph có nhiều association, hãy **bỏ cả graph có liên quan**, không chỉ object được gọi `remove()`.

## 10. Collection và quan hệ hai hướng không tự đồng bộ ngược

Một graph JPA có thể chứa:

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private List<OrderLine> lines = new ArrayList<>();
```

Và phía `OrderLine`:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
```

Giả sử giao dịch thêm một dòng hàng mới:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
OrderLine line = new OrderLine(...);

order.addLine(line);  // Cập nhật order.lines và line.order.
em.flush();

em.getTransaction().rollback();
```

Sau rollback:

- Hàng `OrderLine` mới không được commit.
- `order.lines` trong object graph cũ có thể vẫn chứa `line`.
- `line.order` có thể vẫn trỏ tới `order`.
- `line.id` có thể đã được cấp.
- Các collection wrapper/proxy từ context lỗi không nên được dùng để tạo transaction mới một cách tùy tiện.

Một kiểu thao tác rất nguy hiểm là:

```java
newEm.merge(orderFromRolledBackTransaction);
```

Nếu mapping cascade MERGE/ALL và graph chứa `line` không còn tồn tại trong database, provider có thể cố hợp nhất những state đã rollback vào dữ liệu mới. Kết quả phụ thuộc mapping và versioning, có thể gây lỗi hoặc đưa thay đổi không mong muốn trở lại database.

**Đối với rollback trên aggregate, bỏ graph cũ và tải lại aggregate trong context mới** là quy tắc an toàn hơn việc cố “vá từng collection”.

## 11. Rollback sau flush hoặc query vẫn phải xử lý như rollback bình thường

`flush()` có thể xảy ra tại nhiều thời điểm:

- Khi ứng dụng gọi `em.flush()`.
- Trong quá trình commit.
- Trước một JPQL/Criteria query khi `FlushModeType.AUTO` yêu cầu kết quả phản ánh thay đổi pending.
- Do provider phải tạo ID hoặc tuân thủ ràng buộc/mapping cụ thể.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên đã sửa");

Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.title = :title",
    Long.class
).setParameter("title", "Tên đã sửa")
 .getSingleResult();

// Query ở AUTO có thể đã kích hoạt flush.
em.getTransaction().rollback();
```

Ngay cả nếu SQL `UPDATE` đã chạy trước SELECT, rollback vẫn hoàn tác UPDATE thuộc transaction. Nhưng object Java có thể vẫn mang tên vừa sửa.

### Exception xuất hiện ở getResultList không có nghĩa lỗi SELECT

Giả sử một thay đổi pending vi phạm unique constraint. Nếu query ở AUTO kích hoạt flush, exception có thể ném tại:

```java
query.getResultList();
```

thay vì tại:

```java
em.getTransaction().commit();
```

Sau lỗi đó, không nên cố dùng persistence context cũ để sửa vài field rồi “thử query lại” nếu transaction đã bị đánh dấu rollback-only hoặc provider báo trạng thái không hợp lệ. Phải xử lý transaction thất bại và tạo đơn vị công việc mới.

Đây là lý do cần bao phủ **cả thao tác query và commit** bằng quy trình xử lý lỗi giao dịch thích hợp, không chỉ bọc `commit()`.

## 12. `@Version` và optimistic locking sau rollback

Một entity có:

```java
@Version
private Long version;
```

giúp phát hiện xung đột khi hai transaction cùng cập nhật entity theo cơ chế optimistic locking.

Giả sử `Book #42` ở DB có version 3. Trong transaction A:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên do A thay đổi");
em.flush();
```

Provider có thể phát SQL kiểu:

```sql
UPDATE books
SET title = ?, version = 4
WHERE id = 42 AND version = 3;
```

Nhưng nếu A rollback sau đó, version trong database có thể trở về 3 nếu không có transaction khác được commit liên quan. Java object `book` có thể đang giữ version 4 hoặc một trạng thái nội bộ khác do provider quyết định.

**Đừng kết luận version ở Java object sau rollback là version đã commit trong DB.**

### Khi có xung đột optimistic lock

Giả sử transaction B đã commit thay đổi version 4, còn transaction A vẫn dựa trên version 3. Khi flush hoặc commit, A có thể nhận `OptimisticLockException`.

Khi gặp exception:

1. Rollback transaction A theo contract.
2. Bỏ context và các entity state cũ.
3. Mở transaction mới.
4. Đọc lại entity/version mới từ DB.
5. Quyết định nghiệp vụ: thông báo conflict, cho người dùng cập nhật lại, hoặc retry có điều kiện.
6. Nếu retry, dùng command và kiểm tra invariant trên dữ liệu mới.

Không nên tự đặt `book.version = 4` trên object stale rồi merge để vượt kiểm tra optimistic locking. Làm vậy có thể che giấu mất cập nhật.

### Version có thể được cập nhật lúc nào?

Provider có thể cập nhật version ở flush hoặc thời điểm khác theo quy tắc và chiến lược của mình. Khi có rollback, trạng thái version ở Java không nên được dùng làm nguồn tin cậy. Cách đúng là **đọc version của hàng đang tồn tại trong context/transaction mới**.

## 13. Cache cấp một và cấp hai sau rollback

JPA thường có hai tầng quản lý dữ liệu:

- **First-level cache / identity map**: gắn với persistence context, quản lý từng instance entity và dirty state.
- **Second-level cache / shared cache**: tùy provider và cấu hình; có thể lưu state được chia sẻ giữa nhiều context.

Rollback có thể khiến những entity từng managed trở thành detached hoặc context không còn phù hợp để tiếp tục sử dụng. Điều đó khác với việc xóa/cập nhật dữ liệu cache dùng chung.

### Không tái sử dụng first-level state của transaction đã lỗi

Một managed entity cũ có thể chứa giá trị không được commit. Tốt nhất là kết thúc context đó và dùng context mới cho nghiệp vụ mới.

### Cache cấp hai có luôn phản ánh đúng database không?

Một provider phù hợp có cơ chế riêng để xử lý cache và transaction. Tuy vậy, nếu hệ thống dùng native SQL ngoài ORM, nhiều tiến trình, cache tùy biến hoặc cấu hình provider-specific, cần hiểu chính sách cache invalidation khi giao dịch rollback/cập nhật.

Không nên tự suy rằng việc gọi rollback sẽ cập nhật mọi cache Java tùy biến do ứng dụng tạo. Nếu application có cache riêng, chỉ publish/cache kết quả sau khi transaction commit thành công hoặc có quy trình rollback/invalidation tương ứng.

### Không “sửa” rollback bằng cách evict toàn bộ cache

Evict cache có thể hữu ích khi xác định cache stale, nhưng nó **không phục hồi các object Java đã được giữ bên ngoài cache**. Đồng thời evict toàn bộ cache có thể ảnh hưởng hiệu năng hệ thống. Cần xác định nguồn state sai và scope của thao tác trước.

## 14. Tác động ngoài database: email và event không tự rollback

Giả sử service xử lý đăng ký:

```java
em.getTransaction().begin();

Enrollment enrollment = new Enrollment(student, course);
em.persist(enrollment);

emailService.sendWelcomeMessage(student); // Side effect bên ngoài DB.

em.getTransaction().rollback();
```

Database không giữ enrollment mới, nhưng email có thể đã được gửi. Rollback không gọi “thu hồi email”.

Tương tự với:

- HTTP request tới hệ thống thanh toán.
- Gửi Kafka/RabbitMQ message ngoài transaction phù hợp.
- Ghi file hoặc upload object storage.
- Cập nhật Redis hoặc cache không tham gia cùng transaction.
- Gửi notification, WebSocket message.
- Gọi API bên thứ ba.

Vì vậy, xử lý entity trong bộ nhớ sau rollback chỉ là **một phần** của bài toán nhất quán toàn hệ thống.

### Phát event sau commit

Một lựa chọn là đăng ký callback/hook **sau khi transaction commit thành công** để gửi thông báo. Trong môi trường Spring, có thể sử dụng cơ chế sự kiện theo pha transaction; trong Jakarta EE có các cơ chế synchronization/event tương ứng.

Tuy nhiên, nếu quy trình cần độ tin cậy cao, gửi event ngay sau commit vẫn có cửa sổ lỗi (DB đã commit nhưng tiến trình chết trước khi gửi). **Transactional outbox** thường giải quyết tốt hơn bằng cách ghi bản ghi outbox trong cùng transaction DB, rồi worker độc lập gửi message một cách idempotent.

### Transactional outbox minh họa

```text
Transaction:
  INSERT enrollment
  INSERT outbox_event
  COMMIT
       │
       ▼
Worker đọc outbox đã commit
       │
       ▼
Gửi notification / message
       │
       ▼
Đánh dấu event đã xử lý
```

Nếu transaction rollback, cả enrollment và outbox record không được commit. Worker không có event mới để gửi.

Điểm chính là **chỉ đặt những side effect thật sự thuộc transaction vào lời hứa “rollback sẽ hoàn tác”**.

## 15. Quy trình xử lý exception an toàn với resource-local EntityManager

Một mẫu triển khai thông thường:

```java
public void updatePrice(
        EntityManagerFactory emf,
        Long bookId,
        BigDecimal newPrice) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, bookId);
        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }

        book.changePrice(newPrice);

        // Query hoặc flush có thể phát hiện lỗi trước commit.
        em.getTransaction().commit();
    } catch (RuntimeException originalFailure) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                originalFailure.addSuppressed(rollbackFailure);
            }
        }

        throw originalFailure;
    } finally {
        em.close();
    }
}
```

Ưu điểm:

- Một EntityManager phục vụ một đơn vị công việc.
- Có transaction boundary rõ ràng.
- Exception từ thao tác entity, query, flush hoặc commit đều được xử lý.
- Rollback được thử khi transaction còn active.
- Không tiếp tục sử dụng các entity sau khi đơn vị công việc thất bại.
- Đóng context trong `finally`.
- Nếu rollback cũng lỗi, exception rollback được ghi kèm, không che mất nguyên nhân chính.

Đây là mẫu **resource-local**. Trong container-managed JTA hoặc Spring, việc tự begin/rollback bằng `em.getTransaction()` không nhất thiết hợp lệ; cần dùng cách quản lý transaction của môi trường tương ứng.

### Lưu ý khi commit ném exception

Không phải mọi lỗi `commit()` đều có tình trạng kết quả hoàn toàn rõ ràng. Ví dụ lỗi mạng xảy ra khi client mất kết nối sau khi DB đã commit có thể tạo trạng thái “kết quả không chắc chắn” ở tầng ứng dụng. Trong trường hợp đó, **retry không điều kiện** có thể làm thao tác tạo mới thực hiện hai lần.

Hãy phân biệt:

- **Rollback được xác nhận:** các thay đổi của transaction bị hoàn tác.
- **Transaction được đánh dấu rollback-only và kết thúc rollback:** không có commit thành công.
- **Kết quả commit không chắc chắn do sự cố truyền thông:** cần kiểm tra bằng khóa nghiệp vụ/idempotency mechanism hoặc quy trình reconciliation.

Không nên đơn giản coi mọi exception từ commit là bằng chứng không có gì được ghi.

## 16. Xử lý rollback trong Spring `@Transactional`

Với Spring, transaction thường được quản lý qua `@Transactional`:

```java
@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public void rename(Long id, String newTitle) {
        Book book = bookRepository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Book not found")
            );

        book.rename(newTitle);

        // Spring/JPA đồng bộ khi phù hợp trong transaction.
    }
}
```

Nếu method ném exception khiến transaction rollback theo cấu hình, database changes thuộc transaction không được commit. Nhưng **object Java đã bị sửa không tự được gán lại state ban đầu**.

### Cẩn trọng khi catch rồi nuốt exception trong transaction

Ví dụ:

```java
@Transactional
public void dangerousOperation(Long id) {
    Book book = bookRepository.findById(id).orElseThrow();
    book.rename("Tên mới");

    try {
        bookRepository.flush(); // Có thể phát hiện constraint failure.
    } catch (RuntimeException ex) {
        log.warn("Flush failed", ex);
        // Nuốt exception, rồi tiếp tục xử lý.
    }

    // Transaction có thể đã bị đánh dấu rollback-only.
}
```

Nếu transaction đã bị đánh dấu rollback-only, việc nuốt exception không làm nó trở lại bình thường. Khi method kết thúc, Spring có thể ném `UnexpectedRollbackException` hoặc exception khác vì transaction không thể commit như mong đợi.

Sau lỗi persistence nghiêm trọng, không nên tiếp tục thực hiện truy vấn/ghi trên cùng persistence context với kỳ vọng “sửa field rồi commit lại” là đủ.

### Rule rollback trong Spring không phải quy tắc toàn bộ JPA

Theo cấu hình mặc định thông dụng của Spring `@Transactional`, runtime exceptions và errors kích hoạt rollback; checked exceptions cần được cấu hình thêm nếu muốn rollback theo kiểu đó. Có thể dùng `rollbackFor` hoặc transaction rules khác tùy dự án.

Điều này là **chính sách Spring**, không phải quy tắc chung rằng mọi checked exception tự động rollback JPA transaction.

Nếu method bắt exception và không ném ra ngoài, Spring có thể không biết cần rollback trừ khi transaction đã bị đánh dấu rollback-only hoặc code đánh dấu rollback theo API Spring.

### Retry cần transaction mới

Không nên retry bằng vòng lặp ngay bên trong một `@Transactional` đã bị rollback-only:

```java
@Transactional
public void problematicRetry() {
    for (int i = 0; i < 3; i++) {
        try {
            doDatabaseWork();
            return;
        } catch (RuntimeException ex) {
            // Cùng transaction có thể đã hỏng.
        }
    }
}
```

Retry đúng thường phải nằm **bên ngoài** transaction thất bại, để mỗi attempt chạy với transaction/persistence context mới. Có thể dùng service riêng, cơ chế retry của framework hoặc transaction template phù hợp.

Một lưu ý Spring: gọi `@Transactional` method qua `this.someMethod()` trong cùng class có thể không đi qua transaction proxy theo cấu hình proxy mặc định, nên không tự tạo một transaction mới chỉ vì method được annotation. Phải hiểu proxy/weaving và transaction boundary thực tế.

## 17. Bối cảnh Jakarta EE/JTA

Trong Jakarta EE, `EntityManager` có thể là container-managed và transaction do JTA điều phối. Khi lỗi xảy ra, service có thể cần đánh dấu transaction rollback-only bằng cơ chế phù hợp, thay vì gọi `em.getTransaction().rollback()` như resource-local.

Ví dụ khái niệm:

```java
@Stateless
public class BookService {

    @PersistenceContext
    private EntityManager em;

    public void rename(Long id, String title) {
        Book book = em.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }

        book.rename(title);
        // Container quyết định transaction commit/rollback.
    }
}
```

Trong môi trường container:

- Không tự đóng container-managed `EntityManager`.
- Không dùng `getTransaction()` cho một JTA EntityManager theo cách của resource-local.
- Phạm vi managed/detached phụ thuộc transaction-scoped hay extended persistence context.
- Sau transaction rollback, không giữ reference tới entity cũ rồi mặc định chúng sẽ được quản lý trong một transaction mới.

Mục tiêu nghiệp vụ giống nhau ở cả Spring và Jakarta EE: **mỗi đơn vị công việc có transaction boundary rõ ràng; khi thất bại, bỏ state không còn đáng tin và xử lý lại trong một ngữ cảnh thích hợp**.

## 18. Vì sao `refresh()` không phải phương thuốc tổng quát?

`EntityManager.refresh(entity)` yêu cầu tải lại state của **managed entity** từ database theo ngữ nghĩa JPA.

Trước khi giao dịch thất bại, nếu cần bỏ thay đổi local trong một tình huống còn hợp lệ, refresh có thể có tác dụng thích hợp. Nhưng sau rollback:

- Entity cũ có thể đã detached.
- Persistence context cũ có thể đã kết thúc hoặc không phù hợp dùng tiếp.
- Transaction có thể bị rollback-only hoặc `EntityManager` đã đóng.
- Refresh trên entity không managed có thể ném `IllegalArgumentException`.

Ví dụ không nên viết:

```java
try {
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    em.getTransaction().rollback();

    em.refresh(book); // Không phải cách xử lý rollback an toàn chung.
}
```

Một cách rõ ràng hơn sau rollback là tạo context mới và tìm lại:

```java
EntityManager freshEm = emf.createEntityManager();

try {
    Book fresh = freshEm.find(Book.class, bookId);
    // Dùng fresh để xây DTO/trả dữ liệu đọc được.
} finally {
    freshEm.close();
}
```

Nếu cần refresh trong một context mới, phải gọi trên **managed instance của context mới**, không trên object detached từ transaction cũ.

## 19. Vì sao `clear()` cũng không phải rollback?

`em.clear()` tách các managed entities khỏi persistence context. Nó **không rollback database transaction** và cũng không đảm bảo phục hồi state của những Java objects đã sửa.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

em.clear(); // Book bị detach, pending changes có thể bị bỏ.
em.getTransaction().commit();
```

`clear()` không gửi lệnh SQL đảo thay đổi đã flush, cũng không bắt buộc reset `book.title` về tên cũ. Nếu transaction cần rollback, phải gọi rollback qua cơ chế transaction phù hợp.

Phân biệt:

| API | Tác dụng chính | Không có nghĩa |
| --- | --- | --- |
| `em.flush()` | Đồng bộ pending changes xuống DB trong transaction | Commit |
| `em.clear()` | Tách toàn bộ managed instances khỏi context | Rollback hoặc reset field Java |
| `em.detach(entity)` | Tách một instance khỏi context | Xóa hàng DB |
| `em.refresh(managed)` | Tải lại state của managed entity theo quy tắc | Phục hồi transaction đã lỗi |
| `em.merge(detached)` | Copy state detached vào managed representative | Hủy thay đổi đã rollback |
| `rollback()` | Hoàn tác DB transaction khi thành công | Undo mọi Java object và side effect |
| `em.close()` | Kết thúc application-managed EntityManager | Đảo ngược mọi setter |

Không chọn nhầm một thao tác chỉ vì kết quả có vẻ “giống như làm sạch” ở tầng bộ nhớ.

## 20. Retry như thế nào để không tái áp dụng trạng thái lỗi?

Retry có vẻ đơn giản:

```java
try {
    save(entity);
} catch (RuntimeException ex) {
    save(entity); // Retry ngay với chính entity cũ?
}
```

Nhưng cùng object `entity` có thể đã:

- Nhận ID do DB/provider cấp.
- Tăng version hoặc thay đổi timestamp/audit field.
- Có collection thêm entity con.
- Giữ reference tới removed entity.
- Chứa giá trị do transaction lỗi tính ra.
- Là detached object có state stale.
- Tác động đến hệ thống bên ngoài.

Do đó, retry một object graph sau rollback có thể khác hoàn toàn retry **ý định nghiệp vụ** ban đầu.

### Mô hình retry bằng command

```java
public record ChangeBookPriceCommand(
    Long bookId,
    BigDecimal newPrice
) {}
```

Mỗi attempt nhận command và tự tải entity managed mới:

```java
public void changePriceOnce(ChangeBookPriceCommand command) {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, command.bookId());
        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }

        book.changePrice(command.newPrice());

        em.getTransaction().commit();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Bộ điều phối retry ở bên ngoài:

```java
public void changePriceWithRetry(ChangeBookPriceCommand command) {
    RuntimeException last = null;

    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            changePriceOnce(command);
            return;
        } catch (TransientConcurrencyException ex) {
            last = ex;
            // Có thể backoff theo chính sách hệ thống.
        }
    }

    throw last;
}
```

`TransientConcurrencyException` ở đây là **kiểu exception phân loại do ứng dụng tự định nghĩa hoặc chuyển đổi**, không phải class chuẩn của Jakarta Persistence. Cần chỉ retry các lỗi được xác định là tạm thời và an toàn; không retry vô điều kiện mọi `RuntimeException`.

### Các điều kiện retry an toàn

1. **Mỗi attempt có transaction/context mới.**
2. **Đầu vào là command/DTO độc lập với managed graph cũ.**
3. **Tải lại dữ liệu đã commit ở attempt mới.**
4. **Kiểm tra lại invariant nghiệp vụ** vì dữ liệu có thể đã đổi.
5. **Xử lý optimistic locking/concurrency** theo chính sách.
6. **Có idempotency** cho thao tác tạo mới hoặc side effect ngoài DB.
7. **Số lần retry và backoff có giới hạn.**
8. **Không retry lỗi validation/unique nghiệp vụ cố định** như thể nó sẽ tự hết.

Không nên bỏ qua trường hợp kết quả commit không xác định. Retry thao tác tạo mới không có idempotency key có thể làm tạo hai bản ghi nếu attempt trước đã commit nhưng client không nhận được phản hồi.

## 21. Giữ ý định nghiệp vụ mà không giữ stale entity

Khi rollback, có hai loại dữ liệu:

- **Intent (ý định):** người dùng muốn đổi giá sách sang 250000, thêm khóa học X hoặc hủy đơn Y.
- **Derived/persistent state:** trạng thái entity đã được tải, thay đổi qua helper, generated ID, version, association collection và các field phụ.

Ta thường muốn giữ **intent hợp lệ**, nhưng phải bỏ **persistent state không còn chắc chắn** của transaction lỗi.

Ví dụ:

```java
public record AddCourseCommand(
    Long studentId,
    Long courseId
) {}
```

Trong attempt mới:

```java
Student student = em.find(Student.class, command.studentId());
Course course = em.find(Course.class, command.courseId());

if (student == null || course == null) {
    throw new IllegalArgumentException("Invalid references");
}

student.enroll(course);
```

Mỗi attempt tạo object graph managed mới từ DB và áp dụng lại ý định đăng ký. Nếu transaction trước rollback, collection của student trong attempt mới không mang những phần tử transient từng được thêm ở attempt lỗi.

Đối với thao tác xóa, command chỉ cần entity ID và lý do xóa, thay vì chuyển một removed entity instance đã tham gia transaction thất bại.

## 22. Xóa mềm và trạng thái nghiệp vụ sau rollback

Nhiều ứng dụng dùng **soft delete**:

```java
@Column(name = "deleted", nullable = false)
private boolean deleted;

public void markDeleted() {
    deleted = true;
}
```

Nếu transaction gọi:

```java
book.markDeleted();
em.getTransaction().rollback();
```

database có thể vẫn giữ `deleted = false`, nhưng Java object có thể có `deleted == true`.

Vấn đề giống như đổi title, dù không gọi `em.remove()`. Điều này cho thấy **rollback không chỉ liên quan đến trạng thái removed của JPA**; mọi persistent field, enum status và state machine nghiệp vụ đều có thể lệch giữa heap và DB.

Ví dụ một đơn hàng có thể đã chạy:

```java
order.markPaid();
order.reserveInventory();
order.addPaymentAttempt(attempt);
```

Nếu transaction rollback, không nên tiếp tục dùng `order.getStatus() == PAID` của graph cũ để quyết định giao hàng. Hãy dùng dữ liệu đã commit mới nhất và thiết kế event/outbox phù hợp.

## 23. Domain event trong bộ nhớ có cần dọn không?

Một số aggregate giữ domain events trong collection:

```java
private final List<DomainEvent> pendingEvents = new ArrayList<>();

public void approve() {
    status = Status.APPROVED;
    pendingEvents.add(new OrderApproved(id));
}
```

Nếu transaction rollback, `pendingEvents` trong object cũ có thể vẫn chứa `OrderApproved`. Nếu code tiếp tục dùng chính aggregate đó rồi publish tất cả events, hệ thống có thể phát sự kiện về một thay đổi chưa được commit.

Cần chọn cơ chế rõ ràng:

- Aggregate chỉ sống trong transaction và bị bỏ khi transaction thất bại.
- Events chỉ được publish sau commit thành công.
- Hoặc dùng transactional outbox để gắn event với transaction DB.
- Nếu có một event buffer sống ngoài transaction, phải có quy tắc xóa/đánh dấu abort đáng tin cậy.

Không nên tự assume entity lifecycle và event lifecycle được JPA đồng bộ với nhau. `@PostPersist` hoặc `@PostUpdate` cũng không đồng nghĩa transaction đã commit thành công; callback có thể xảy ra trước rollback.

## 24. Nhiều transaction cùng làm việc: rollback không đưa dữ liệu về “lúc đầu”

Giả sử ban đầu:

```text
Book #42.price = 180000
```

Hai transaction cùng chạy:

```text
Transaction A                   Transaction B
đọc price=180000                đọc price=180000
đổi price=200000                đổi price=220000
                               commit thành công
A thất bại và rollback
```

Tùy isolation và locking, diễn biến thực tế có thể có chờ khóa hoặc conflict. Điều cần hiểu là: sau A rollback, **database có thể giữ 220000 của B**, không phải nhất thiết là 180000 của thời điểm A bắt đầu.

Vậy nên không được “phục hồi” bằng cách tự gán lại state cũ:

```java
book.changePrice(new BigDecimal("180000.00"));
newTransaction.merge(book);
```

Hành động đó có thể **ghi đè cập nhật hợp lệ của B**.

Nếu cần xử lý tiếp:

1. Mở transaction/context mới.
2. Đọc price và version đang có trong DB.
3. So sánh ý định nghiệp vụ của A với dữ liệu mới.
4. Quyết định áp dụng lại, từ chối conflict hoặc yêu cầu người dùng xác nhận.
5. Ghi bằng cơ chế locking/version phù hợp.

**Rollback bảo vệ tính nguyên tử của A; nó không đóng băng hoặc hoàn tác transaction hợp lệ của B.**

## 25. Snapshot trước transaction có đủ để phục hồi object Java không?

Có thể có ý tưởng lưu:

```java
String oldTitle = book.getTitle();
BigDecimal oldPrice = book.getPrice();
```

rồi khi lỗi:

```java
book.rename(oldTitle);
book.changePrice(oldPrice);
```

Cách này đôi khi hữu ích cho **UI model thuần Java** hoặc view state đơn giản. Nhưng với JPA entity graph, nó không phải giải pháp tổng quát:

- Có thể quên một field đã đổi.
- Embedded object có thể bị mutate bên trong.
- Collection đã thêm/xóa phần tử.
- Association hai hướng có tham chiếu cần đồng bộ.
- Generated ID/version có thể thay đổi.
- Lifecycle callback có thể cập nhật timestamp.
- Entity con có thể đã được persist/remove.
- Transaction khác có thể đã commit một giá trị mới sau snapshot.
- Provider có snapshot nội bộ và context lifecycle riêng.

Vì vậy, dù có thể khôi phục một vài field trên object cho mục đích hiển thị, **không được dùng thao tác đảo setter như một cách thay thế rollback database hoặc làm entity cũ trở lại managed an toàn**.

Nếu giao diện cần giữ dữ liệu người dùng nhập sau lỗi, hãy lưu vào **form DTO/view model**, không dùng JPA entity từ transaction thất bại làm nơi giữ form state.

## 26. Khi nào cần `refresh()` trên entity đang managed?

Trước một rollback, nếu transaction còn hợp lệ và muốn bỏ thay đổi local có chủ đích, `refresh(managedEntity)` có thể tải state database trở lại. Nhưng phải xét:

- Transaction isolation và kết quả SQL đã flush.
- Entity có đang managed không?
- Có cascade REFRESH không?
- Có đang giữ pending changes muốn giữ ở các entity khác không?
- State DB có bị transaction khác sửa không?

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Thay đổi nháp");

// Nếu phù hợp với nghiệp vụ/context:
em.refresh(book);

// book được đọc lại từ DB theo quy tắc refresh.
em.getTransaction().commit();
```

Đây là thao tác quản lý **một entity managed trong một transaction còn hợp lệ**, không phải lời khuyên “sau rollback thì gọi refresh trên mọi object”.

Sau rollback, cách an toàn nhất thường là **mở context mới rồi find lại**.

## 27. Savepoint và “nested transaction” có làm object tự phục hồi?

Một số hệ quản trị hỗ trợ SQL savepoint:

```sql
SAVEPOINT before_step;
UPDATE books SET price = 250000 WHERE id = 42;
ROLLBACK TO SAVEPOINT before_step;
```

Nhưng rollback đến savepoint ở database **không tự động quay ngược state của những Java entity mà JPA đã thay đổi**. Đồng thời, JPA không cung cấp một API chuẩn tổng quát để đồng bộ identity map/snapshots theo mọi savepoint JDBC do ứng dụng tự quản lý.

Nếu framework dùng “nested transaction” dựa trên savepoint, cần kiểm tra:

- Persistence context có được chia sẻ với outer transaction không?
- Những entity đã sửa có còn managed với state cũ/dirty không?
- Provider có biết savepoint đã rollback không?
- Flush nào đã xảy ra trước/sau savepoint?
- Có thể cần clear/refresh hoặc tạo transaction mới thay vì tiếp tục graph cũ không?

**Savepoint là công cụ của transaction database, không mặc nhiên là cơ chế undo Java object graph.** Đừng dựa vào sự tương đương này nếu chưa có hợp đồng và integration test cụ thể cho provider/framework đang dùng.

## 28. Phân biệt rollback-only với transaction đã rollback

Một transaction có thể bị đánh dấu **rollback-only** trước khi thực sự kết thúc.

Ví dụ trong Spring, một thao tác nội bộ thất bại và framework đánh dấu transaction rollback-only. Caller bắt exception rồi tiếp tục xử lý:

```java
@Transactional
public void process() {
    doFirstStep();

    try {
        doStepThatMarksRollbackOnly();
    } catch (RuntimeException ex) {
        // Thử tiếp tục, nhưng transaction có thể đã rollback-only.
    }

    doFinalStep();
}
```

Các method sau có thể vẫn sửa Java object, nhưng cuối cùng transaction không thể commit thành công. Code phải hiểu:

- **Rollback-only:** quyết định rằng transaction không được commit; chưa chắc transaction đã kết thúc.
- **Rollback completed:** transaction đã được hoàn tác và kết thúc.
- **Entity state:** Java field có thể tiếp tục bị sửa trong cả hai giai đoạn.
- **Persistence context:** có thể còn tồn tại tới lúc transaction kết thúc, nhưng không nên tiếp tục thao tác như một transaction khỏe mạnh nếu đã hỏng.

Khi transaction được xác định không thể commit, nên dừng luồng nghiệp vụ đó và để transaction manager hoàn tất rollback, thay vì tạo thêm thay đổi khó giải thích.

## 29. Kiểm thử rollback đúng cách

Một lỗi thường gặp là kiểm thử như sau:

```java
Book book = em.find(Book.class, 42L);

book.changePrice(new BigDecimal("250000.00"));
em.getTransaction().rollback();

assertEquals(
    new BigDecimal("180000.00"),
    book.getPrice()
); // Sai về giả định rollback tự hồi phục object.
```

Assertion này đặt kỳ vọng sai lên object Java. Điều cần kiểm thử là **database đã hoàn tác transaction**, bằng cách đọc trong một context mới.

### Mẫu integration test

```java
@Test
void rollbackDoesNotCommitBookPrice() {
    Long bookId = existingBookId;

    EntityManager workEm = emf.createEntityManager();

    try {
        workEm.getTransaction().begin();

        Book book = workEm.find(Book.class, bookId);
        book.changePrice(new BigDecimal("250000.00"));

        workEm.flush();
        workEm.getTransaction().rollback();
    } finally {
        workEm.close();
    }

    EntityManager verifyEm = emf.createEntityManager();

    try {
        Book persisted = verifyEm.find(Book.class, bookId);

        assertEquals(
            0,
            persisted.getPrice().compareTo(
                new BigDecimal("180000.00")
            )
        );
    } finally {
        verifyEm.close();
    }
}
```

Test giả định fixture `Book #existingBookId` ban đầu có giá `180000.00` và không có transaction khác can thiệp. Việc sử dụng `compareTo` trong assertion tránh nhầm lẫn do `BigDecimal.equals()` phân biệt scale.

Một test khác có thể chủ động xác minh object cũ **không được tin làm state DB**, nhưng không nên viết expectation cứng về toàn bộ lifecycle nội bộ sau rollback trên mọi provider. Điều portable cần xác nhận là kết quả DB và hợp đồng transaction.

### Các kịch bản test nên có

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Đổi scalar field rồi rollback | Database giữ giá trị đã commit trước đó |
| `persist` entity mới rồi rollback | Không có hàng mới được commit |
| `remove` entity rồi rollback | Hàng cũ vẫn tồn tại nếu không có transaction khác thay đổi |
| Thêm entity con/association rồi rollback | Không có hàng liên kết hoặc entity con mới được commit |
| Flush trước rollback | SQL có thể chạy nhưng không được commit |
| Query AUTO gây flush rồi rollback | DB vẫn hoàn tác thay đổi |
| Optimistic lock conflict | Lỗi được xử lý, không merge graph stale để ghi đè |
| Retry | Mỗi attempt dùng context mới và không tạo bản ghi trùng |
| Event/email | Không phát side effect phản ánh dữ liệu chưa commit |
| Exception tại commit | Xử lý tình huống kết quả không chắc chắn/idempotency nếu có |

Không cần kiểm thử rằng SQL chưa từng chạy. Mục tiêu là kiểm tra **kết quả transaction** và quy trình xử lý state sau khi thất bại.

## 30. Những lỗi thường gặp khi xử lý rollback

### Lỗi 1: Tin rằng field tự về giá trị cũ

```java
book.rename("Tên mới");
rollback();
System.out.println(book.getTitle());
```

Giá trị Java có thể vẫn là `"Tên mới"`. Đọc lại từ context mới nếu cần dữ liệu đã commit.

### Lỗi 2: Tái sử dụng entity mới đã rollback vì thấy ID khác null

ID có thể đã được cấp trước rollback. Không suy ra hàng tồn tại từ ID. Retry bằng command với entity mới trong transaction mới.

### Lỗi 3: Merge toàn bộ detached graph sau rollback

`merge` có thể ghi lại state đáng lẽ đã bị loại bỏ. Chỉ áp dụng lại những thay đổi nghiệp vụ hợp lệ lên managed graph mới.

### Lỗi 4: Gọi `refresh()` ngay trên detached entity sau rollback

`refresh` cần managed entity theo quy tắc; dùng context mới và `find()` an toàn hơn sau transaction thất bại.

### Lỗi 5: Dùng `clear()` như lệnh rollback

`clear()` chỉ detach entity, không thay thế rollback DB và không tự hồi phục field.

### Lỗi 6: Giữ association collection đã sửa trong object graph cũ

Rollback không tự thêm lại phần tử vừa xóa, cũng không tự loại bỏ object con đã thêm trong collection Java. Bỏ graph cũ khi tiếp tục nghiệp vụ.

### Lỗi 7: Nuốt exception rồi tiếp tục cùng transaction rollback-only

Transaction có thể không thể commit. Hãy để nó kết thúc rollback rồi tạo transaction mới nếu cần.

### Lỗi 8: Phát event trước commit

Database rollback nhưng email/message đã gửi. Dùng after-commit hook hoặc outbox theo yêu cầu tin cậy.

### Lỗi 9: Cố gán lại snapshot cũ vào database

Một transaction khác có thể đã cập nhật hợp lệ. Nạp lại state mới và xử lý conflict, không tự ghi đè bằng giá trị trước transaction thất bại.

### Lỗi 10: Cho rằng lỗi ở `getResultList()` chỉ liên quan đến query

Ở AUTO, query có thể kích hoạt flush của pending changes và gặp constraint violation. Đây là lỗi của transaction đang ghi, cần rollback/context mới.

### Lỗi 11: Retry mọi exception

Validation error, duplicate business key và constraint cố định không tự hết khi retry. Chỉ retry những lỗi đã phân loại tạm thời; có giới hạn attempt/backoff.

### Lỗi 12: Xem `EntityManager.isOpen()` là dấu hiệu transaction an toàn

Handle còn mở không bảo đảm context sau lỗi có state sạch. Kiểm soát đơn vị công việc và không tái dùng graph thất bại.

## 31. Bài tập vận dụng

### Bài 1: Giá trị field sau rollback

```java
Book book = em.find(Book.class, 42L);
book.rename("JPA nâng cao");
em.getTransaction().rollback();
```

**Câu hỏi:** Có bảo đảm `book.getTitle()` tự trở về tên cũ không?

**Đáp án:** Không. Rollback hoàn tác DB transaction; các setter trên Java object không tự bị đảo ngược. Cần nạp lại Book trong context mới để biết state DB.

### Bài 2: ID đã được cấp

```java
Book book = new Book("A", new BigDecimal("100.00"));
em.persist(book);
em.flush();
Long id = book.getId();
em.getTransaction().rollback();
```

**Câu hỏi:** Có thể khẳng định hàng ID đó đã được lưu vì `id != null` không?

**Đáp án:** Không. ID có thể được cấp trước rollback; hàng INSERT chưa commit đã bị hoàn tác. Không dùng lại object cũ như entity mới mà không xét lifecycle.

### Bài 3: Xóa rồi rollback

```java
Book book = em.find(Book.class, 42L);
em.remove(book);
em.flush();
em.getTransaction().rollback();
```

**Câu hỏi:** DB có thể vẫn còn hàng 42 không?

**Đáp án:** Có. DELETE thuộc transaction đã rollback không được commit. Muốn tiếp tục xử lý, hãy nạp lại entity trong context mới.

### Bài 4: Collection không được hoàn tác

```java
order.addLine(newLine);
em.flush();
em.getTransaction().rollback();
```

**Câu hỏi:** `order.getLines()` có chắc tự xóa `newLine` không?

**Đáp án:** Không. Object graph Java có thể vẫn chứa dòng hàng vừa thêm, dù DB không commit bản ghi tương ứng. Không merge nguyên graph đó vô điều kiện.

### Bài 5: Merge sau rollback

Một object `Book` đã rollback vẫn có `price = 999999`. Ứng dụng mở transaction mới và gọi `merge(book)`.

**Câu hỏi:** Vì sao nguy hiểm?

**Đáp án:** Merge có thể copy giá đã bị rollback vào managed Book và ghi lại xuống DB. Nên tải Book mới rồi áp dụng command được phép.

### Bài 6: Concurrent update

A đọc price 100, B commit price 120, A rollback sau khi thử đặt price 110.

**Câu hỏi:** Nên tự ghi price 100 để “phục hồi” không?

**Đáp án:** Không. Đó có thể là ghi đè cập nhật hợp lệ của B. Đọc lại price/version trong transaction mới và xử lý xung đột.

### Bài 7: Event bên ngoài

Service persist enrollment, gửi email và sau đó rollback.

**Câu hỏi:** Email có tự thu hồi không?

**Đáp án:** Không. Cần trì hoãn phát event tới sau commit hoặc dùng outbox phù hợp.

### Bài 8: Spring rollback-only

Method `@Transactional` bắt exception từ một thao tác repository, log rồi chạy tiếp.

**Câu hỏi:** Có thể chắc chắn transaction vẫn commit không?

**Đáp án:** Không. Transaction có thể đã được đánh dấu rollback-only; Spring có thể ném `UnexpectedRollbackException` khi hoàn tất. Không tiếp tục dùng cùng context như một transaction khỏe mạnh.

### Bài 9: Test kết quả DB

Sau rollback, một test assert trên `book.getTitle()` trong object cũ.

**Câu hỏi:** Vì sao chưa chứng minh rollback đúng?

**Đáp án:** Vì object cũ có thể mang state đã sửa. Phải nạp lại dữ liệu bằng context mới và assert trên trạng thái DB được quan sát.

### Bài 10: Lỗi tại query

Sau khi sửa Book, `getResultList()` ném unique constraint error.

**Câu hỏi:** Có thể query gây flush không, và cần làm gì?

**Đáp án:** Có, đặc biệt với AUTO. Cần coi transaction đã lỗi, rollback, bỏ context/graph cũ và sửa root cause của thay đổi không hợp lệ.

## 32. Quy trình phản ứng sau rollback trong ứng dụng thực tế

Khi một thao tác JPA bị thất bại, có thể theo quy trình:

1. **Nhận diện lỗi:** validation, constraint, optimistic lock, deadlock, connection failure hay lỗi nghiệp vụ?
2. **Xác định kết quả transaction:** rollback đã thành công hay commit outcome còn không chắc chắn?
3. **Đảm bảo transaction kết thúc:** rollback nếu còn active và contract cho phép, hoặc để container/framework thực hiện.
4. **Kết thúc context của đơn vị công việc thất bại:** không tiếp tục dùng các managed/detached objects cũ như trạng thái tin cậy.
5. **Không cố đảo setters trên entity JPA** như cách duy nhất để phục hồi.
6. **Giữ lại command/input hợp lệ**, không giữ toàn bộ graph dirty.
7. **Mở context/transaction mới khi cần:** dùng `find()` và đọc state hiện tại.
8. **Kiểm tra invariant và version một lần nữa**, vì transaction khác có thể đã commit.
9. **Retry có điều kiện:** chỉ với lỗi tạm thời, giới hạn attempts, có idempotency.
10. **Không phát side effect trước commit:** dùng after-commit/outbox theo yêu cầu.
11. **Kiểm tra cache/event buffer:** không dùng kết quả của transaction bị rollback để cập nhật state chia sẻ.
12. **Test với database thật:** xác minh DB state sau rollback bằng context mới.
13. **Ghi log thông tin chẩn đoán phù hợp:** transaction ID/correlation ID, lỗi chính, lỗi rollback kèm theo; tránh log thông tin nhạy cảm.
14. **Đưa thông báo phù hợp cho caller:** conflict, validation error, retryable failure hoặc kết quả không chắc chắn.
15. **Đừng trộn API quản lý transaction:** resource-local, JTA và Spring transaction manager có hợp đồng khác nhau.

Quy trình này giúp giảm nguy cơ “rollback xong vẫn ghi lại dữ liệu lỗi” — một vấn đề khó phát hiện hơn cả exception ban đầu.

## Kết luận

**Rollback hoàn tác các thay đổi thuộc database transaction; nó không tự phục hồi mọi Java object trong heap.** Một entity managed vừa đổi field có thể giữ giá trị mới sau rollback. Một entity `persist()` rồi rollback có thể giữ ID dù hàng chưa được commit. Một entity `remove()` rồi rollback có thể còn hàng trong DB, trong khi object graph đã bị thay đổi. Collection, version, event và các side effect bên ngoài càng cần xử lý riêng.

Nguyên tắc an toàn nhất sau một transaction JPA thất bại là **kết thúc đơn vị công việc, không tái sử dụng entity graph đáng ngờ, mở persistence context mới để đọc state đã commit, rồi áp dụng lại ý định nghiệp vụ qua một transaction mới nếu cần**. `merge()`, `refresh()` và `clear()` không phải những câu lệnh thay thế rollback hoặc phép “undo” toàn bộ trạng thái Java.

Khi cần retry, hãy retry **command**, không retry vô điều kiện **managed/detached object từ giao dịch lỗi**. Khi cần gửi thông báo, hãy gắn việc phát event với kết quả commit thật sự. Và khi cần xác minh rollback, hãy kiểm tra database bằng một persistence context mới thay vì dựa vào các getter của entity cũ.

Câu hỏi cuối cùng phải luôn được đặt ra là: **“Database đã rollback điều gì, Java object vẫn giữ điều gì, context nào còn đáng tin và nghiệp vụ nào được phép thực hiện lại?”**. Trả lời chính xác bốn câu hỏi ấy là nền tảng để xử lý rollback trong JPA an toàn và nhất quán.
