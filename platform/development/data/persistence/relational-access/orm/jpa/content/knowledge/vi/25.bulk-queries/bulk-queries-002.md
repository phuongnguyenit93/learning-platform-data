# Xóa hàng loạt bằng JPQL DELETE

Khi một ứng dụng JPA cần xóa vài entity riêng lẻ, cách tự nhiên là tải entity vào persistence context rồi gọi `EntityManager.remove(entity)`. Nhưng nếu phải xóa hàng nghìn hoặc hàng triệu bản ghi theo cùng một điều kiện, việc tải từng entity chỉ để xóa có thể tiêu tốn nhiều bộ nhớ, tạo nhiều câu SQL và kéo dài transaction.

**JPQL bulk DELETE** cho phép mô tả thao tác xóa bằng một câu lệnh trên **entity model**, ví dụ:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.status = :status AND b.createdAt < :cutoff"
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

Lệnh này có thể xóa nhiều entity khớp điều kiện mà ứng dụng không phải gọi `find()` rồi `remove()` cho từng Book. Tuy nhiên, đổi lại, bulk DELETE **không đi qua đầy đủ vòng đời xóa từng managed entity**: không tự áp dụng cascade REMOVE, orphan removal, lifecycle callbacks hay optimistic locking theo cách của `em.remove()`. Các entity đã được load vào persistence context cũng **không tự biến mất khỏi bộ nhớ** khi bulk DELETE tác động trực tiếp đến database.

Vì thế, điều cần học không chỉ là cú pháp `DELETE FROM`, mà là **khi nào nên dùng**, **khi nào không**, **xóa quan hệ phụ thuộc ra sao**, **tránh dữ liệu stale thế nào**, và **kiểm thử kết quả sau commit**.

Bài **“Xóa hàng loạt bằng JPQL DELETE”** thuộc chương **Truy vấn thay đổi**, chủ đề **Data Persistence Relational Access ORM JPA**. Các ví dụ dùng Jakarta Persistence (`jakarta.persistence`), Java 17+ và JUnit 5; với JPA trước khi chuyển namespace Jakarta, các kiểu tương đương nằm trong `javax.persistence`.

## 1. Ba phương thức xóa cần phân biệt

Trong một dự án JPA, ba kỹ thuật có thể cùng mang tên “delete”, nhưng semantics khác nhau.

| Kỹ thuật | Ví dụ | Đặc trưng |
| --- | --- | --- |
| Xóa entity qua persistence context | `em.remove(book)` | Làm việc với managed entity, lifecycle/cascade của JPA được áp dụng theo mapping |
| JPQL bulk DELETE | `DELETE FROM Book b WHERE ...` | Xóa theo điều kiện ở mức query, không cần tải từng entity |
| Native SQL DELETE | `DELETE FROM books WHERE ...` | Xóa theo schema/cú pháp của database, có thể dùng tính năng riêng của RDBMS |

Điểm phân biệt:

- **`em.remove()`** biểu diễn thao tác xóa một entity instance được quản lý, có thể lan truyền xóa theo `CascadeType.REMOVE` hoặc `CascadeType.ALL` và các quy tắc orphan removal liên quan.
- **JPQL DELETE** tác động hàng loạt lên dữ liệu của một entity type theo WHERE. Nó **bỏ qua việc đồng bộ từng instance managed** và không tự gọi các callbacks tương ứng từng entity.
- **Native DELETE** chạy SQL trực tiếp và chịu các ràng buộc/dialect DB. Nó cũng không có nghĩa tự kích hoạt JPA entity lifecycle.

Nếu hệ thống cần `@PreRemove`, domain events từ entity, xử lý orphanRemoval/cascade phức tạp hoặc per-entity optimistic locking, không thể thay `em.remove()` bằng bulk DELETE chỉ vì muốn nhanh hơn.

## 2. Mô hình ví dụ: Book, Author và Review

Giả sử ứng dụng có ba entity:

```text
Author 1 ─────────── * Book 1 ─────────── * Review
  (độc lập)              (cần xóa)          (phụ thuộc Book)

Author A ── Book B1 ── Review R1
         └─ Book B2 ── Review R2

Author X ── Book B3
```

Quy tắc nghiệp vụ:

- Một `Book` có tác giả `Author`; xóa Book **không được xóa Author**.
- Mỗi `Review` thuộc một Book; nếu Book bị xóa theo entity lifecycle, hệ thống có thể xóa các Review phụ thuộc theo cascade thích hợp.
- Book có trạng thái `DRAFT`, `ACTIVE` hoặc `ARCHIVED`.
- Job dọn dữ liệu có thể xóa những Book đã lưu trữ quá lâu.
- Một số Book vẫn được quản lý trong persistence context khi job chạy; đây là nguồn rủi ro stale state.

### Enum trạng thái

```java
public enum BookStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
```

### Entity Author

```java
import jakarta.persistence.*;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Author() {}

    public Author(String name) {
        this.name = name;
    }

    public Long getId() { return id; }

    public String getName() { return name; }
}
```

### Entity Book

```java
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

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

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private BookStatus status;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    @OneToMany(
        mappedBy = "book",
        cascade = {CascadeType.PERSIST, CascadeType.REMOVE},
        orphanRemoval = true
    )
    private List<Review> reviews = new ArrayList<>();

    protected Book() {}

    public Book(
            String title,
            BookStatus status,
            LocalDateTime createdAt,
            Author author) {

        this.title = title;
        this.status = status;
        this.createdAt = createdAt;
        this.author = author;
    }

    public Long getId() { return id; }

    public Long getVersion() { return version; }

    public String getTitle() { return title; }

    public BookStatus getStatus() { return status; }

    public LocalDateTime getCreatedAt() { return createdAt; }

    public Author getAuthor() { return author; }

    public List<Review> getReviews() {
        return List.copyOf(reviews);
    }

    public void archive() {
        status = BookStatus.ARCHIVED;
    }

    public void rename(String newTitle) {
        title = newTitle;
    }

    public void addReview(int rating) {
        reviews.add(new Review(this, rating));
    }
}
```

### Entity Review

```java
import jakarta.persistence.*;

@Entity
@Table(name = "reviews")
public class Review {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "book_id", nullable = false)
    private Book book;

    @Column(nullable = false)
    private int rating;

    protected Review() {}

    public Review(Book book, int rating) {
        this.book = book;
        this.rating = rating;
    }

    public Long getId() { return id; }

    public int getRating() { return rating; }
}
```

Trong mô hình này, `Book.reviews` được cấu hình cascade REMOVE và orphanRemoval cho **xóa theo entity lifecycle**. Tuy nhiên, **JPQL bulk DELETE Book không tự lan truyền những cơ chế JPA này đến Review**.

### Schema khái niệm

```sql
CREATE TABLE authors (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    author_id BIGINT NOT NULL,
    CONSTRAINT fk_book_author
        FOREIGN KEY (author_id) REFERENCES authors(id)
);

CREATE TABLE reviews (
    id BIGINT PRIMARY KEY,
    book_id BIGINT NOT NULL,
    rating INTEGER NOT NULL,
    CONSTRAINT fk_review_book
        FOREIGN KEY (book_id) REFERENCES books(id)
);
```

DDL chỉ mang tính giải thích; cơ chế generated identity và cú pháp của từng RDBMS có thể khác nhau. Các khóa ngoại ở đây **không có `ON DELETE CASCADE`**, để dễ quan sát khác biệt giữa JPA cascade và ràng buộc DB.

---

## 3. Cú pháp chuẩn của JPQL bulk DELETE

Dạng tổng quát:

```sql
DELETE FROM EntityName alias
WHERE condition
```

Trong đó:

- `EntityName` là **tên entity JPA**, không phải tên bảng vật lý.
- `alias` là biến định danh của entity trong câu JPQL.
- `WHERE` là tùy chọn; nếu không có WHERE, câu lệnh nhắm đến toàn bộ entity type tương ứng.
- Các field trong WHERE là **thuộc tính của entity model**.
- JPQL bulk DELETE không có một cú pháp chuẩn tương đương `DELETE ... JOIN ... LIMIT ... ORDER BY` của một số dialect SQL.

Ví dụ:

```java
Query query = em.createQuery(
    "DELETE FROM Book b WHERE b.status = :status"
);

query.setParameter("status", BookStatus.ARCHIVED);

int affected = query.executeUpdate();
```

JPQL tham chiếu `Book` và `b.status`, không cần biết bảng vật lý tên `books` hay cột tên `status`.

### Phân biệt với SQL

JPQL:

```sql
DELETE FROM Book b WHERE b.status = :status
```

SQL database có thể là:

```sql
DELETE FROM books WHERE status = ?
```

Provider chịu trách nhiệm ánh xạ entity và thuộc tính sang bảng/cột, bind tham số và lựa chọn SQL phù hợp với inheritance mapping/dialect.

**Không viết `DELETE FROM books` trong JPQL** nếu `books` chỉ là tên bảng, trừ khi tình cờ có entity được đặt đúng tên đó. Nếu muốn SQL bảng, dùng `createNativeQuery(...)` và hiểu khác biệt portability.

## 4. `executeUpdate()` là thao tác thực thi

Truy vấn thay đổi được chạy bằng:

```java
int count = em.createQuery(
    "DELETE FROM Book b WHERE b.status = :status"
)
.setParameter("status", BookStatus.ARCHIVED)
.executeUpdate();
```

Không sử dụng:

```java
query.getResultList();   // Không phải cách thực thi JPQL DELETE.
query.getSingleResult(); // Không trả entity bị xóa.
```

`executeUpdate()` trả về một `int` biểu thị **số entity bị tác động** theo contract của JPA query DML. Nó không phải một `List<Book>` và không cung cấp các ID đã bị xóa.

### Cách đọc số lượng

Giả sử có 100 Book lưu trữ quá hạn nhưng 20 Book không phù hợp điều kiện:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.status = :status AND b.createdAt < :cutoff"
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();

System.out.println("Deleted entities: " + deleted);
```

Nếu giá trị trả là 80, đây là số entity Book mà thao tác DELETE báo đã tác động. **Không nên dùng số này để suy ra số Review, số hàng join, số SQL statements hoặc tổng số hàng vật lý đã bị DB xóa do trigger/ON DELETE CASCADE.**

Đặc biệt với inheritance mapping, provider có thể cần nhiều câu SQL để xóa một tập entity. Cách triển khai và số hàng vật lý bị ảnh hưởng có thể khác số entity logical được báo.

### Trường hợp trả 0

`executeUpdate()` trả 0 khi không entity nào khớp và không có lỗi. Đây không tự động là exception. Ứng dụng phải quyết định:

- Job cleanup: 0 có thể là thành công bình thường.
- API xóa theo ID có yêu cầu tồn tại: 0 có thể ánh xạ sang not found hoặc conflict.
- Optimistic deletion: 0 có thể biểu thị version không còn khớp.

## 5. Bulk DELETE phải nằm trong transaction

Một bulk JPQL DELETE làm thay đổi database nên cần transaction phù hợp. Với application-managed resource-local `EntityManager`:

```java
public int deleteArchivedBooks(
        EntityManagerFactory emf,
        LocalDateTime cutoff) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        int deleted = em.createQuery(
            "DELETE FROM Book b " +
            "WHERE b.status = :status " +
            "AND b.createdAt < :cutoff"
        )
        .setParameter("status", BookStatus.ARCHIVED)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

        em.getTransaction().commit();

        return deleted;
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

Ở đây:

1. Tạo EntityManager riêng cho một đơn vị công việc.
2. Bắt đầu transaction.
3. Thực thi JPQL DELETE.
4. Commit nếu thành công.
5. Rollback nếu thao tác/commit thất bại và transaction còn active.
6. Đóng EntityManager.

Nếu dùng JTA hoặc Spring-managed transaction, không sao chép `em.getTransaction()` bừa bãi: framework/container quyết định begin/commit/rollback.

### `TransactionRequiredException`

Thực thi bulk UPDATE/DELETE ngoài một transaction hợp lệ thường dẫn tới `TransactionRequiredException` theo JPA contract. Đừng dựa vào một database/driver đang autocommit để giả định `executeUpdate()` được phép chạy không cần transaction.

### Flush, executeUpdate và commit

Ba mốc khác nhau:

```text
begin transaction
    │
    ├── Managed changes có thể đang pending
    │
    ├── flush() nếu cần đồng bộ trước bulk DELETE
    │
    ├── executeUpdate()  ← SQL DELETE được thực hiện
    │
    ├── clear() nếu cần bỏ managed state stale
    │
    └── commit()         ← xác nhận transaction
```

`executeUpdate()` không thay thế `commit()`. SQL DELETE có thể đã chạy nhưng vẫn được hoàn tác nếu transaction rollback.

## 6. Bind tham số thay vì nối chuỗi JPQL

Đừng tạo query bằng cách nối input trực tiếp:

```java
String jpql =
    "DELETE FROM Book b WHERE b.title = '" + userTitle + "'";
```

Cách đúng:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b WHERE b.title = :title"
)
.setParameter("title", userTitle)
.executeUpdate();
```

Lợi ích:

- Giảm nguy cơ query injection từ giá trị.
- Tránh xử lý thủ công dấu nháy và escaping.
- Giữ JPQL dễ đọc.
- Cho phép provider bind giá trị đúng kiểu.

Với enum:

```java
.setParameter("status", BookStatus.ARCHIVED)
```

Với `LocalDateTime`:

```java
.setParameter("cutoff", LocalDateTime.of(2024, 1, 1, 0, 0))
```

Không nên truyền chuỗi `"ARCHIVED"` thay enum nếu thuộc tính entity có kiểu `BookStatus` và query so sánh trực tiếp với enum. Hãy để JPA binding diễn đạt kiểu nghiệp vụ.

### Đừng truyền kiểu thời gian mơ hồ

Đối với job dọn dữ liệu, cần xác định rõ `cutoff` dùng múi giờ và chính sách lưu trữ nào. `LocalDateTime` không mang timezone; nếu dữ liệu lưu theo UTC, hãy dùng cùng một quy tắc chuyển thời gian trước khi bind để không xóa nhầm bản ghi sát ranh giới.

## 7. Vì sao `WHERE` quan trọng hơn cả cú pháp DELETE?

Câu lệnh:

```java
em.createQuery("DELETE FROM Book").executeUpdate();
```

có thể nhắm xóa **toàn bộ Book** trong phạm vi entity type và các loại con phù hợp. Đây là thao tác phá hủy dữ liệu lớn, không phải “xóa những record đã load”.

Trong cleanup jobs, nên thể hiện **ít nhất các điều kiện nghiệp vụ thiết yếu**:

```java
"DELETE FROM Book b " +
"WHERE b.status = :status " +
"AND b.createdAt < :cutoff"
```

Một số hệ thống còn yêu cầu:

- Tenant/account ID.
- Legal retention policy.
- Trạng thái đã archive/soft delete.
- Không còn giao dịch hoặc tài liệu liên quan.
- Không thuộc nhóm giữ lại theo quy định.
- Ngưỡng số bản ghi tối đa mỗi lần chạy.

**Nếu ứng dụng đa tenant, quên điều kiện tenant là lỗi phân quyền và nguy cơ mất dữ liệu**, dù câu JPQL hoàn toàn hợp lệ.

### Ví dụ kiểm soát tenant

Giả sử Book có thuộc tính `tenantId`:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.tenantId = :tenantId " +
    "AND b.status = :status " +
    "AND b.createdAt < :cutoff"
)
.setParameter("tenantId", authenticatedTenantId)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

`authenticatedTenantId` phải đến từ context phân quyền đáng tin, **không lấy tùy ý từ request body rồi coi là đã kiểm soát quyền**.

Điều kiện phân quyền cần được integration test: khi chạy xóa cho tenant A, mọi Book thuộc tenant B phải còn, kể cả cùng trạng thái và ngày tạo.

## 8. Xóa một entity bằng query khác gì `em.remove()`?

Xét cách xóa entity:

```java
Book book = em.find(Book.class, id);

if (book != null) {
    em.remove(book);
}
```

Và bulk delete theo ID:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
).setParameter("id", id)
 .executeUpdate();
```

Nếu không có quan hệ, callback hay entity đang managed, cả hai có thể làm hàng Book không còn trong DB sau commit. Nhưng **cơ chế và các tác động phụ khác nhau**.

| Vấn đề | `em.remove(book)` | JPQL `DELETE FROM Book` |
| --- | --- | --- |
| Cần managed entity instance | Có | Không |
| Tải từng Book vào context | Thường có/được managed trước | Không yêu cầu |
| Cascade REMOVE của JPA | Được xét theo mapping | Không tự áp dụng per-entity |
| Orphan removal/lifecycle quan hệ | Theo ngữ nghĩa JPA khi phù hợp | Không tự thực hiện |
| `@PreRemove`/`@PostRemove` | Thuộc lifecycle xóa entity | Không chạy cho từng entity theo bulk semantics |
| `@Version` optimistic check | Theo provider/JPA lifecycle | Không tự check version từng entity |
| Managed entities đang load | Có lifecycle removed | Có thể vẫn stale trong context |
| Số lượng SQL | Có thể nhiều, tùy batching/graph | Thường hướng tới bulk DML hiệu quả, provider/dialect quyết định SQL |
| Khả năng xóa rất nhiều bản ghi | Có thể tốn nhiều memory | Thường phù hợp hơn nếu điều kiện/quan hệ cho phép |
| Dữ liệu dependent có FK | Có thể cascade JPA | Cần xử lý FK bằng kế hoạch riêng hoặc DB cascade |

**Không có nghĩa bulk DELETE luôn tốt hơn**. Nó tối ưu hóa một dạng thao tác, nhưng không thay thế ngữ nghĩa aggregate lifecycle.

## 9. Bỏ qua cascade REMOVE và orphanRemoval

Trong entity Book mẫu:

```java
@OneToMany(
    mappedBy = "book",
    cascade = {CascadeType.PERSIST, CascadeType.REMOVE},
    orphanRemoval = true
)
private List<Review> reviews;
```

Nếu gọi:

```java
em.remove(book);
```

JPA có thể thực hiện xóa Review theo cascade REMOVE khi Book bị remove, tuân thủ ràng buộc và lifecycle mapping.

Nhưng:

```java
em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
).setParameter("id", id)
 .executeUpdate();
```

**không tự duyệt `book.reviews` để gọi remove cho mỗi Review**, dù `cascade = REMOVE` hay `orphanRemoval = true`.

### Kịch bản gây lỗi foreign key

Database:

```text
books:
  id = 42

reviews:
  id = 100, book_id = 42
  id = 101, book_id = 42
```

Foreign key:

```sql
FOREIGN KEY (book_id) REFERENCES books(id)
```

Nếu xóa Book #42 bằng bulk JPQL mà các Review vẫn tồn tại, DB thường từ chối xóa Book với lỗi referential integrity. Đây không phải bug của JPQL: DB đang bảo vệ bảng con còn tham chiếu parent.

### Tại sao orphanRemoval không giúp?

`orphanRemoval` biểu diễn lifecycle của entity con khi association sở hữu bị gỡ theo những thao tác JPA phù hợp; nó **không phải trigger database** chạy mỗi khi một hàng Book bị bất kỳ DELETE nào xóa.

Tương tự, `CascadeType.ALL` trên `Book.reviews` cũng không biến bulk DELETE thành `em.remove(book)` trên mọi Book.

## 10. Cách 1: Xóa entity con trước, parent sau

Nếu muốn dùng bulk DELETE và database có FK từ Review đến Book, một chiến lược là **xóa dependent rows trước trong cùng transaction**, rồi xóa Book.

Ví dụ xóa một Book:

```java
em.getTransaction().begin();

int removedReviews = em.createQuery(
    "DELETE FROM Review r WHERE r.book.id = :bookId"
)
.setParameter("bookId", bookId)
.executeUpdate();

int removedBooks = em.createQuery(
    "DELETE FROM Book b WHERE b.id = :bookId"
)
.setParameter("bookId", bookId)
.executeUpdate();

em.getTransaction().commit();
```

Thứ tự:

```text
DELETE Review WHERE book_id = 42
             │
             ▼
Không còn Review trỏ Book #42
             │
             ▼
DELETE Book WHERE id = 42
             │
             ▼
COMMIT (cùng transaction)
```

Nếu có các bảng phụ thuộc khác (`BookTag`, `Loan`, `Attachment`...), phải xét **tất cả đường phụ thuộc** và quy tắc giữ dữ liệu. Không được xóa mọi phụ thuộc một cách máy móc nếu một số hàng có vòng đời độc lập hoặc phải giữ lịch sử.

### Dùng transaction duy nhất

Xóa Review rồi commit, sau đó xóa Book ở transaction khác có thể khiến hệ thống rơi vào trạng thái trung gian nếu bước thứ hai thất bại. Nếu nghiệp vụ yêu cầu tính nguyên tử, hai bước phải thuộc cùng transaction.

### Đếm số Review và Book riêng

`removedReviews` và `removedBooks` không cùng đơn vị nghiệp vụ. Nếu xóa 200 Reviews của 50 Books, `executeUpdate()` sẽ trả hai số lượng khác nhau. Không gộp tổng thành “số Book đã xóa”.

## 11. Xóa dependent theo điều kiện của parent

Muốn xóa mọi Review của các Book quá hạn, không phải lúc nào cũng có danh sách ID sẵn.

Ví dụ:

```java
int deletedReviews = em.createQuery(
    "DELETE FROM Review r " +
    "WHERE r.book IN (" +
    "   SELECT b FROM Book b " +
    "   WHERE b.status = :status " +
    "   AND b.createdAt < :cutoff" +
    ")"
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

Sau đó:

```java
int deletedBooks = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.status = :status " +
    "AND b.createdAt < :cutoff"
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

Cả hai câu DELETE nằm trong **cùng transaction**. Subquery ở WHERE cho phép lọc Review theo Book phù hợp; bulk DELETE không cần join trực tiếp ở phần DELETE.

### Lưu ý race condition

Nếu transaction khác thay đổi trạng thái Book giữa hai câu lệnh, tập parent khớp có thể thay đổi theo isolation/locking. Ví dụ một Book bị chuyển từ ARCHIVED sang ACTIVE sau khi Review đã bị xóa nhưng trước khi Book được xóa. Nếu database/isolation cho phép, ứng dụng có thể đã xóa Review của Book không còn đủ điều kiện xóa.

Vì vậy, với dữ liệu nhạy cảm:

- Cân nhắc transaction isolation và locking phù hợp.
- Xác định ID tập target, kiểm tra lại điều kiện trước mỗi pha.
- Cân nhắc khóa các Book target trong transaction khi nghiệp vụ yêu cầu.
- Thiết kế cleanup ngoài giờ hoặc theo batch có giới hạn.
- Dùng trạng thái trung gian như `PURGE_PENDING` được chuyển dưới kiểm soát nghiệp vụ khi phù hợp.
- Viết integration test về cạnh tranh đồng thời nếu có nguy cơ.

Hai câu SQL trong cùng transaction đảm bảo atomicity của kết quả **nếu commit**, nhưng không tự bảo đảm tập điều kiện luôn bất biến giữa các statement ở mọi isolation level.

## 12. Cách 2: Database `ON DELETE CASCADE`

Nếu database schema cho phép:

```sql
FOREIGN KEY (book_id)
REFERENCES books(id)
ON DELETE CASCADE
```

khi hàng Book bị xóa, database có thể tự xóa các Review tham chiếu theo ràng buộc FK.

Khi đó JPQL:

```java
em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
)
.setParameter("id", bookId)
.executeUpdate();
```

có thể xóa được Book và dependent rows mà không cần JPQL DELETE Review trước.

**Đây là cascade của database, không phải JPA CascadeType.REMOVE.**

| Đặc điểm | JPA cascade REMOVE | DB ON DELETE CASCADE |
| --- | --- | --- |
| Nguồn định nghĩa | Entity mapping | Schema/foreign key |
| Kích hoạt khi `em.remove` | Theo JPA lifecycle | Khi SQL DELETE parent chạy |
| Kích hoạt bởi bulk DELETE | Không tự gọi cascade JPA | Có thể, nếu SQL xóa parent và FK có ON DELETE CASCADE |
| Entity callbacks trên child | Có thể được gọi qua lifecycle JPA | Không chạy callbacks Java cho hàng bị DB xóa |
| Persistence context được làm mới | Theo managed lifecycle | Không tự đồng bộ mọi managed child |
| Portable qua DB | JPA mapping có ngữ nghĩa chuẩn | Cần DDL/dialect và migration phù hợp |

Nếu Review cần audit callback hoặc sự kiện nghiệp vụ tại từng lần xóa, DB cascade không thể thay thế các cơ chế Java đó.

Ngoài ra, không dùng `ON DELETE CASCADE` chỉ để tránh một FK violation nếu luật nghiệp vụ yêu cầu giữ Review, giữ lịch sử hoặc có luật bảo vệ dữ liệu.

## 13. Cách 3: Xóa từng entity để giữ semantics vòng đời

Khi số lượng target vừa phải hoặc có domain invariants quan trọng:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b " +
    "WHERE b.status = :status AND b.createdAt < :cutoff",
    Book.class
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.getResultList();

for (Book book : books) {
    em.remove(book);
}
```

Cách này cho phép JPA xử lý lifecycle/cascade/optimistic locking theo mapping. Đổi lại, nó có thể:

- Load nhiều entity vào context.
- Khởi tạo các association cần thiết để cascade.
- Phát nhiều câu SQL.
- Tạo lock/transaction dài.
- Tăng memory với hàng trăm nghìn entity.

Nếu cần giữ semantics per-entity nhưng dữ liệu lớn, cân nhắc **chia batch**, mỗi batch với transaction/context phù hợp, thay vì load tất cả Book trong một lần.

### Quy tắc chọn

- **Bulk DELETE:** entity tương đối độc lập hoặc đã có kế hoạch xóa phụ thuộc và cache/context rõ ràng.
- **`em.remove()`:** nghiệp vụ cần lifecycle/cascade/callback/versioning theo entity.
- **DB cascade:** ownership ở schema rõ ràng, có chủ đích bỏ qua callbacks JPA và kiểm soát database behavior.

Không chọn chỉ theo tốc độ trước khi xác định vòng đời dữ liệu.

---

## 14. Bulk DELETE không đồng bộ persistence context

Giả sử Book #42 đã được load:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);

int removed = em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
)
.setParameter("id", 42L)
.executeUpdate();

String title = book.getTitle();

em.getTransaction().commit();
```

Có thể DB đã xóa hàng Book #42 nhưng object Java `book` vẫn tồn tại trong heap, vẫn chứa title, status, version và các association đã load.

**Bulk DELETE không tự gọi `em.remove(book)` trên các instance đang managed.**

Những biểu hiện có thể gặp:

- `book.getTitle()` vẫn trả giá trị cũ.
- `em.find(Book.class, 42L)` trong cùng context có thể trả lại instance đã managed.
- `em.contains(book)` có thể vẫn cho biết object thuộc context, dù hàng DB đã bị xóa.
- Nếu thay đổi field của object sau bulk DELETE, flush sau có thể cố UPDATE một hàng không còn tồn tại và báo lỗi stale/optimistic locking.
- Collection quan hệ đã load có thể giữ các child Java objects mà DB đã xóa.

Đây là **stale persistence context**, không phải bằng chứng bulk DELETE thất bại.

### Vì sao `find()` không nhất thiết query DB lại?

Persistence context dùng identity map/first-level cache: cùng một persistent identity trong một context có một representative managed. Nếu entity đã có, provider có thể trả instance đó mà không truy vấn lại.

Điều quan trọng là **không sử dụng `find()` trong cùng context như một phép kiểm chứng database sau bulk DELETE**.

## 15. Giải pháp thường dùng: flush trước, clear sau

Một trình tự có chủ đích:

```java
em.getTransaction().begin();

// Một số thay đổi managed khác cần được giữ.
updateManagedEntities(em);

// Đồng bộ pending changes trước bulk operation.
em.flush();

int removed = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.status = :status AND b.createdAt < :cutoff"
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();

// Bỏ managed state có thể đã stale sau bulk DELETE.
em.clear();

em.getTransaction().commit();
```

**`flush()` và `clear()` giải quyết hai vấn đề khác nhau.**

- `flush()`: đẩy pending changes của managed entities xuống database trước bulk DML, để không vô tình bỏ chúng hoặc thực hiện DML trên state chưa đồng bộ.
- `clear()`: detach tất cả managed entities sau bulk DML, giúp code tiếp theo không tiếp tục xem chúng là managed state còn đồng nhất với DB.

### Những giới hạn

- `clear()` **không phải rollback** và không làm các Java objects cũ tự mất field.
- `clear()` có thể làm **mất pending changes chưa flush** nếu gọi sai thời điểm.
- `flush()` có thể đẩy xuống DB những thay đổi nằm ngoài phạm vi bulk DELETE, thậm chí gây constraint error sớm.
- Nếu còn giữ references tới entities đã detach, đừng tự `merge()` chúng trở lại sau DELETE.
- Không gọi `clear()` bừa bãi trong một service đang giữ graph managed cho các bước nghiệp vụ tiếp theo.
- Nếu query đang dùng JPQL bulk DELETE độc lập và context mới không có entity stale, có thể không cần clear phức tạp.

**Không có quy tắc “mọi bulk DELETE phải luôn flush/clear”** bất kể hoàn cảnh; cần xác định rõ pending state, phạm vi thao tác và owner của persistence context.

## 16. `flush()` trước DELETE không có nghĩa DELETE được commit

Timeline:

```text
BEGIN TRANSACTION
      │
      ▼
Book #42 đã managed, thay đổi title
      │
      ▼
em.flush()  → UPDATE books SET title = ...
      │
      ▼
JPQL DELETE → DELETE FROM books WHERE ...
      │
      ▼
Cả UPDATE và DELETE chưa commit
      │
      ├── COMMIT   → xác nhận kết quả transaction
      │
      └── ROLLBACK → hoàn tác cả các SQL thuộc transaction
```

Nếu transaction rollback thành công, database hoàn tác thay đổi SQL, nhưng Java objects có thể vẫn giữ những field đã bị setter thay đổi. Không dựa vào getter của entity cũ sau rollback để biết trạng thái database.

### AUTO và COMMIT

`FlushModeType.AUTO` đặt yêu cầu rằng trong persistence context đã tham gia transaction, pending changes có thể ảnh hưởng query cần được phản ánh trong quá trình xử lý query. Bulk JPQL DML có thể làm provider flush trước khi thực thi theo contract/implementation.

`FlushModeType.COMMIT` không bảo đảm query trước commit phản ánh pending changes theo cách AUTO; nhưng không phải lệnh cấm tuyệt đối SQL trước commit.

Nếu logic bulk DELETE phụ thuộc vào thay đổi vừa được thực hiện trên managed entity, **explicit flush ở ranh giới có chủ đích** thường dễ suy luận hơn là dựa vào thời điểm provider tự flush.

## 17. `refresh()` có thay thế clear sau DELETE không?

`EntityManager.refresh(entity)` được dùng để nạp lại state database cho **entity đang managed**. Nếu entity đã bị bulk DELETE khỏi DB, refresh có thể thất bại vì hàng không còn tồn tại; nó không phải cách “đánh dấu removed” cho tất cả stale entities.

Ví dụ không nên viết:

```java
Book book = em.find(Book.class, id);

em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
).setParameter("id", id)
 .executeUpdate();

em.refresh(book); // Hàng đã bị xóa, có thể lỗi.
```

Một cách rõ hơn sau bulk DELETE là:

```java
em.clear();

Book stillThere = em.find(Book.class, id);
// null nếu hàng không còn và các cache/transaction được xử lý đúng.
```

Cách tốt hơn để khẳng định **đã commit** là mở EntityManager mới sau commit rồi kiểm tra từ đó. Nếu second-level cache được bật, cần biết cache invalidation policy của provider; trong bài test cần kiểm chứng DB độc lập có thể dùng JDBC/SQL trực tiếp.

## 18. Không merge graph stale sau bulk DELETE

Giả sử:

```java
Book old = em.find(Book.class, 42L);

em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

em.clear();
```

`old` trở thành detached Java object với ID, title, status và reviews cũ. Nếu một service khác gọi:

```java
Book managed = anotherEm.merge(old);
```

thì provider có thể cố hợp nhất state một entity mà DB không còn hàng, gây exception, xung đột version hoặc hành vi persistence không mong muốn tùy mapping/ID/version/provider. Đây không phải cách “khôi phục dữ liệu” hợp lệ.

Sau bulk DELETE:

- Không dùng object cũ như một entity đang managed.
- Không trả graph cũ ra API như dữ liệu chắc chắn còn tồn tại.
- Không merge object cũ để retry vô điều kiện.
- Nếu caller cần biết kết quả, trả số entity bị xóa hoặc một report/DTO đã xác minh.
- Nếu cần tiếp tục nghiệp vụ, mở context mới và đọc dữ liệu hiện tại theo ID.

Đặc biệt, các association collections của graph cũ có thể không được đồng bộ với database sau bulk DELETE hoặc DB cascade.

## 19. `@Version` không tự bảo vệ bulk DELETE

Với Book:

```java
@Version
private Long version;
```

Khi dùng `em.remove(book)`, provider có thể tham gia cơ chế optimistic locking và kiểm tra version theo lifecycle JPA. Nhưng JPQL bulk DELETE:

```java
DELETE FROM Book b WHERE b.id = :id
```

không tự động biến thành:

```sql
DELETE FROM books WHERE id = ? AND version = ?;
```

theo version của mọi Book từng được đọc. Vì bulk DML không xử lý từng managed instance, optimistic locking tự động của per-entity operations bị bỏ qua.

### Tự đưa version vào điều kiện khi cần

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.id = :id AND b.version = :expectedVersion"
)
.setParameter("id", id)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();

if (deleted == 0) {
    throw new OptimisticLockException(
        "Book does not exist or version has changed"
    );
}
```

Khi Book đang có version khác, query không xóa hàng. Đây là một cách thực hiện optimistic condition ở bulk DELETE cho **một ID**.

Tuy nhiên:

- Nếu còn Review tham chiếu Book, FK vẫn có thể ngăn xóa.
- Điều kiện version chỉ bảo vệ những cột/trạng thái được thể hiện trong WHERE.
- Nếu không có hàng, 0 có thể là not found hoặc conflict; muốn phân biệt cần đọc dữ liệu theo chính sách.
- Với deletion nhiều Book, mỗi entity có expected version khác nhau khó thể hiện bằng một predicate đơn giản.
- Các race conditions giữa xóa dependent và xóa parent vẫn cần transaction/isolation phù hợp.
- Bulk DELETE vẫn không gọi entity callbacks hoặc cascade JPA.

**Đưa version vào WHERE không biến bulk DELETE thành `em.remove()`.**

## 20. Xóa theo quan hệ: không JOIN trực tiếp ở outer DELETE

Một câu SQL của vendor có thể hỗ trợ:

```sql
DELETE b
FROM books b
JOIN authors a ON a.id = b.author_id
WHERE a.name = 'An';
```

Nhưng cú pháp **JPQL bulk DELETE chuẩn không có JOIN trực tiếp trong DELETE clause**.

Không viết:

```sql
DELETE FROM Book b JOIN b.author a
WHERE a.name = :name
```

như một JPQL DELETE portable.

### Giải pháp: lọc qua association hoặc subquery

Nếu đã có Author entity:

```java
Author author = em.find(Author.class, authorId);

int deleted = em.createQuery(
    "DELETE FROM Book b WHERE b.author = :author"
)
.setParameter("author", author)
.executeUpdate();
```

Nếu cần lọc theo tên Author:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.author IN (" +
    "  SELECT a FROM Author a " +
    "  WHERE a.name = :name" +
    ")"
)
.setParameter("name", "An")
.executeUpdate();
```

Subquery ở WHERE cho phép mô tả điều kiện liên quan entity khác mà không thêm JOIN trực tiếp trong outer DELETE clause.

Nếu Book có Reviews và không có DB cascade, vẫn phải xử lý dependent rows trước khi xóa Book; những câu ví dụ chỉ minh họa **cú pháp lọc**, không phải một workflow xóa aggregate hoàn chỉnh.

### Giới hạn thực tế

Các subquery phức tạp có thể gặp giới hạn dialect, đặc biệt khi truy vấn phụ đọc chính bảng target mà DB đang xóa hoặc khi provider phải phát SQL multi-table inheritance. Cần integration test đúng RDBMS. Nếu SQL trở nên quá phức tạp, cân nhắc chọn IDs trước rồi xóa theo batch hoặc dùng native SQL có kiểm soát.

## 21. Xóa bằng danh sách ID

Một cách hữu ích:

```java
List<Long> ids = List.of(42L, 43L, 44L);

int deleted = em.createQuery(
    "DELETE FROM Book b WHERE b.id IN :ids"
)
.setParameter("ids", ids)
.executeUpdate();
```

Đây là pattern dễ hiểu nếu ứng dụng đã có tập Book IDs hợp lệ và không có dependent rows cản.

### Danh sách rỗng

Không nên mặc định mọi provider/database đều chấp nhận `IN ()` khi `ids` rỗng. Hãy xử lý ở Java:

```java
if (ids.isEmpty()) {
    return 0;
}
```

### Giới hạn tham số

Một số RDBMS/JDBC driver có giới hạn số bind parameters hoặc kích thước SQL. Với hàng trăm nghìn IDs, đừng đưa tất cả vào một `IN` khổng lồ. Cân nhắc chia batch, temporary table/native SQL hoặc chiến lược khác phù hợp.

### Xác thực quyền xóa

Không đủ để kiểm tra IDs do caller đưa ra. Query nên bảo vệ điều kiện nghiệp vụ:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.id IN :ids " +
    "AND b.status = :status"
)
.setParameter("ids", ids)
.setParameter("status", BookStatus.ARCHIVED)
.executeUpdate();
```

Nếu ứng dụng đa tenant, bổ sung điều kiện tenant đáng tin. Việc biết ID của một Book không tự tạo quyền xóa Book đó.

## 22. Vì sao `setMaxResults` không phải LIMIT của bulk DELETE?

Với SELECT:

```java
em.createQuery(
    "SELECT b FROM Book b ORDER BY b.id",
    Book.class
)
.setMaxResults(100)
.getResultList();
```

Nhưng JPQL bulk DELETE **không có cú pháp chuẩn**:

```sql
DELETE FROM Book b
WHERE b.status = :status
ORDER BY b.id
LIMIT 100
```

Không nên kỳ vọng `query.setMaxResults(100)` sẽ giới hạn số hàng DELETE một cách portable. Pagination và `setMaxResults` là cơ chế xử lý query results, không phải một bulk DELETE LIMIT chuẩn giữa mọi provider.

### Mẫu xóa theo batch: SELECT IDs rồi DELETE

```java
List<Long> ids = em.createQuery(
    "SELECT b.id FROM Book b " +
    "WHERE b.status = :status " +
    "AND b.createdAt < :cutoff " +
    "ORDER BY b.id",
    Long.class
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.setMaxResults(500)
.getResultList();

if (!ids.isEmpty()) {
    int deleted = em.createQuery(
        "DELETE FROM Book b WHERE b.id IN :ids"
    )
    .setParameter("ids", ids)
    .executeUpdate();
}
```

Đoạn này **chỉ minh họa trường hợp Book có thể xóa độc lập** (không có dependent FK chặn hoặc đã có DB cascade phù hợp). Nếu còn Review mà không có ON DELETE CASCADE, cần xóa Review trước theo tập IDs trong cùng transaction.

### Rủi ro concurrency

Giữa SELECT IDs và DELETE, transaction khác có thể cập nhật Book. Nếu đây là retention job mà trạng thái có thể chuyển từ ARCHIVED sang ACTIVE, query DELETE theo ID thuần có thể xóa Book đã thay đổi trạng thái.

Một cách giảm rủi ro là áp dụng lại điều kiện trong DELETE:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.id IN :ids " +
    "AND b.status = :status " +
    "AND b.createdAt < :cutoff"
)
.setParameter("ids", ids)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

Tuy nhiên, nếu đã xóa dependent Reviews **trước đó** cho tất cả IDs, việc kiểm tra lại điều kiện chỉ ở parent DELETE chưa đủ: Reviews của Book không còn đủ điều kiện có thể đã bị xóa. Với graph có dependents, cần isolation/locking hoặc một workflow đánh dấu target ổn định, không chỉ thêm WHERE ở bước cuối.

## 23. Chọn transaction boundary cho cleanup theo batch

Có hai lựa chọn thường gặp:

1. **Một transaction lớn:** xóa tất cả target và dependents trong một lần, bảo đảm atomicity lớn nhưng có thể giữ locks/tốn log và khó retry.
2. **Nhiều transaction nhỏ:** mỗi batch xóa một tập ID, commit, tiếp tục batch khác; dễ kiểm soát memory/locks nhưng không atomic trên toàn bộ job.

Ví dụ chiến lược:

```text
Tìm tối đa 500 Book đủ điều kiện
             │
             ▼
BEGIN TRANSACTION
             │
             ├─ Xóa dependent rows nếu cần
             ├─ Xóa Book target
             └─ COMMIT
             │
             ▼
Tìm batch tiếp theo bằng điều kiện vẫn còn hợp lệ
             │
             ▼
Lặp tới khi không còn target
```

Nếu dùng `OFFSET` trên tập liên tục bị xóa, rất dễ bỏ sót hàng:

```text
Batch 1: xóa 500 hàng đầu
Batch 2: OFFSET 500 trên tập đã bị rút ngắn
         → có thể bỏ qua 500 hàng tiếp theo
```

Vì thế với cleanup, thường đơn giản hơn khi **mỗi lần lấy trang đầu tiên** của tập còn đủ điều kiện, hoặc dùng keyset cursor theo ID ổn định. Cần xử lý vấn đề nhiều worker đồng thời và dữ liệu mới liên tục được thêm.

### Một vòng lặp có giới hạn

```java
public int purgeInBatches(int batchSize) {
    int totalDeleted = 0;

    while (true) {
        int deletedThisBatch = purgeOneBatch(batchSize);

        if (deletedThisBatch == 0) {
            break;
        }

        totalDeleted += deletedThisBatch;
    }

    return totalDeleted;
}
```

`purgeOneBatch` phải dùng **transaction riêng**, chọn tập IDs, xử lý dependent data/locking, xóa Book và commit. Vòng lặp cần thêm giới hạn số batch/thời gian chạy ở production để tránh không bao giờ dừng nếu dữ liệu đủ điều kiện liên tục xuất hiện.

Không dùng tổng `int` nếu job có thể xóa quá `Integer.MAX_VALUE` entity qua nhiều batch; có thể dùng `long` cho tổng và kiểm tra overflow tại các ranh giới.

## 24. Bulk DELETE và inheritance

Giả sử:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public class Publication {
    @Id
    private Long id;
}

@Entity
public class Book extends Publication {
    // ...
}
```

Khi bulk DELETE một entity type có inheritance, provider cần tuân thủ mapping nhiều bảng, có thể phải phát nhiều SQL DELETE để tránh orphan rows trong các bảng con/cha.

Điểm quan trọng:

- `DELETE FROM Publication p WHERE ...` có thể tác động cả các entity loại con phù hợp theo entity inheritance.
- Cách provider xóa trên `SINGLE_TABLE`, `JOINED` hay `TABLE_PER_CLASS` có thể khác nhau.
- Một lệnh JPQL bulk DELETE không bắt buộc tương đương đúng một SQL statement trong mọi mapping.
- Số `executeUpdate()` báo về biểu thị số entity bị tác động theo contract, không nên đoán từ tổng row counts của SQL log.
- Foreign key/constraint và optimistic locking vẫn phải được đánh giá.

Không tự tối ưu bằng cách xóa thẳng bảng base hoặc subclass qua native SQL nếu chưa hiểu đầy đủ inheritance discriminator và quan hệ dữ liệu.

---

## 25. Bulk DELETE và lifecycle callbacks/audit

Entity có thể khai báo:

```java
@PreRemove
public void beforeRemove() {
    // Ghi nhận hoặc validate logic thuộc lifecycle entity.
}
```

Khi JPA thực hiện `em.remove(book)` theo lifecycle phù hợp, callback có thể được gọi. Nhưng JPQL bulk DELETE **không tải từng Book để gọi callback**. Vì thế, đừng dùng bulk DELETE rồi kỳ vọng:

- `@PreRemove`/`@PostRemove` tự chạy cho mọi Book.
- Các `EntityListeners` nhận đúng sự kiện per-entity.
- Một audit mechanism phụ thuộc lifecycle callbacks tự có lịch sử xóa đầy đủ.
- Logic Java trong domain method được gọi trước xóa.
- Các event trong aggregate tự được phát.

### Khi cần audit từng bản ghi

Có một vài lựa chọn:

- Xóa qua `em.remove()` theo batch để giữ callbacks và domain logic.
- Ghi audit entries có kiểm soát trong transaction trước bulk DELETE, dựa trên tập IDs/snapshots đã xác định.
- Dùng database trigger/audit theo một chính sách DB rõ ràng, không giả định giống JPA callback.
- Thực hiện soft delete trước, đưa vào retention queue, sau đó purge vật lý khi đủ điều kiện.

Nếu hệ thống cần bằng chứng ai xóa bản ghi, thời điểm nào và lý do gì, hãy thiết kế audit như một yêu cầu độc lập, **không phụ thuộc vào side effect ngầm mà bulk DELETE không cung cấp**.

## 26. Soft delete khác bulk DELETE vật lý

Nhiều hệ thống không xóa hàng ngay. Chúng dùng một cờ:

```java
@Column(nullable = false)
private boolean deleted;
```

hoặc trạng thái `ARCHIVED`/`DELETED`.

Khi đó:

```java
em.createQuery(
    "UPDATE Book b SET b.deleted = true WHERE ..."
).executeUpdate();
```

là **bulk UPDATE**, không phải DELETE. Hàng vật lý vẫn ở DB. Sau giai đoạn retention, job mới dùng bulk DELETE để purge.

### Lưu ý với provider-specific soft delete

Nếu dùng các extension như SQL override cho `em.remove()` hoặc bộ lọc soft-delete của provider, JPQL bulk DELETE **không nhất thiết đi qua cơ chế đó**. Một query DELETE có thể thực sự xóa vật lý, hoặc provider có quy tắc riêng trong từng version.

Không dùng “entity được cấu hình soft delete” làm lý do suy rằng mọi JPQL DELETE sẽ tự chuyển thành UPDATE cờ xóa. Hãy kiểm tra contract provider và SQL thực tế.

### Trình tự có chủ đích

```text
Business delete request
        │
        ▼
Đánh dấu DELETED / ARCHIVED (logic nghiệp vụ)
        │
        ▼
Dữ liệu vẫn tồn tại, có thể khôi phục theo policy
        │
        ▼
Hết retention period, không còn legal hold
        │
        ▼
Purge job: JPQL bulk DELETE / DB cascade / audit
        │
        ▼
Dữ liệu vật lý được xóa
```

Với một hệ thống có retention/legal requirements, đây thường là một thiết kế rõ ràng hơn xóa vật lý ngay bằng một câu JPQL quá rộng.

## 27. Bulk DELETE và các ràng buộc database

JPQL không bỏ qua `FOREIGN KEY`, `UNIQUE`, `CHECK` hoặc trigger DB chỉ vì query là bulk.

Ví dụ Book còn Review:

```java
em.createQuery(
    "DELETE FROM Book b WHERE b.status = :status"
).setParameter("status", BookStatus.ARCHIVED)
 .executeUpdate();
```

Nếu các Reviews tham chiếu Book qua FK không có ON DELETE CASCADE, DB có thể ném referential integrity exception. Transaction có thể bị đánh dấu rollback-only; tùy provider, exception xuất hiện tại `executeUpdate()` hoặc thời điểm flush/commit tương ứng.

Không sửa lỗi bằng cách tắt FK để “bulk DELETE chạy được”. FK là tuyến bảo vệ dữ liệu. Cần sửa **thứ tự xóa, ownership, DB cascade hoặc yêu cầu nghiệp vụ**.

### Xóa shared target còn được tham chiếu

Nếu Book có liên kết tới Author dùng chung, xóa Book không được xóa Author. Với JPQL DELETE Book, DB FK từ Book đến Author thường không yêu cầu xóa Author; đây là hành vi mong muốn.

Ngược lại, nếu xóa Author đang được nhiều Book tham chiếu, FK có thể chặn — và đó có thể là đúng theo nghiệp vụ.

**Một bản ghi không còn được tham chiếu không đồng nghĩa nó được phép xóa.** Mọi cascade và cleanup phải theo lifecycle ownership, không chỉ dựa vào số lượng foreign key.

## 28. Tác động đến second-level cache và query cache

First-level cache gắn với persistence context nên rất dễ stale sau bulk DML. Nhưng hệ thống còn có thể bật **second-level cache/shared cache** hoặc **query cache**.

Native/bulk DML không đi qua mọi update per-entity; provider có thể thực hiện invalidation theo query spaces hoặc cơ chế riêng. Không mặc định tất cả cache application/custom cache sẽ tự đồng bộ.

Cần phân biệt:

- **Persistence context:** xử lý bằng `clear()`, `detach()` hoặc context mới.
- **Second-level cache:** có API `EntityManagerFactory.getCache()` và cơ chế của provider.
- **Query cache:** thường do provider extension điều khiển; kết quả có thể cần invalidation.
- **Cache ngoài ORM** như Redis: phải có chiến lược invalidation/update riêng.

### Một ví dụ invalidation tường minh

```java
EntityManagerFactory emf = ...;

emf.getCache().evict(Book.class, bookId);
```

Hoặc:

```java
emf.getCache().evict(Book.class);
```

Đây là các API thao tác shared cache của JPA, nhưng không có nghĩa chúng luôn cần dùng sau mọi JPQL DELETE; có provider đã xử lý tự động, có các cache tùy biến nằm ngoài phạm vi. Việc evict quá rộng có thể giảm hiệu năng.

**`em.clear()` không đồng nghĩa evict toàn bộ second-level cache**. Đừng dùng một lệnh để suy ra tầng cache khác đã được làm sạch.

## 29. Bulk DELETE và concurrency

Bulk DELETE theo điều kiện có thể chạy cùng các transaction khác:

```text
Transaction A                         Transaction B
đọc Book #42 (ACTIVE)                 chọn Book ARCHIVED
archive Book #42                      xóa Book khớp điều kiện
commit                               commit
```

Tùy thứ tự thực thi, isolation và khóa, Book có thể bị xóa sau khi A archive. Đây có thể đúng hoặc sai tùy policy.

Tình huống nguy hiểm hơn:

```text
Transaction A                         Transaction B
đọc Book #42 ARCHIVED                 Book #42 ARCHIVED
chuyển Book sang ACTIVE               bulk DELETE ARCHIVED
commit                               commit / conflict
```

Nếu B chạy trên dữ liệu/tập điều kiện không còn phù hợp, có nguy cơ xóa Book vừa được phục hồi. Điều kiện trực tiếp trong DELETE sẽ được DB đánh giá theo isolation/locking của transaction, nhưng không thể suy rằng mọi race đều được giải quyết chỉ từ một câu JPQL.

### Các biện pháp

- Dùng status transition rõ ràng: `ARCHIVED → PURGE_PENDING → PURGED`.
- Giới hạn job chỉ xử lý dữ liệu đã cố định hoặc không thể phục hồi trong thời gian purge.
- Dùng optimistic condition/version nếu phù hợp.
- Dùng pessimistic locks cho tập target khi cần, với lưu ý lock/query behavior tùy DB.
- Thiết kế retry khi gặp deadlock/serialization failure, nhưng không retry vô điều kiện mọi exception.
- Tách batches để giảm thời gian giữ lock.
- Có idempotency và audit để tránh chạy trùng job gây tác dụng phụ.
- Kiểm thử concurrent transactions trên RDBMS tương đương production.

**`@Version` trên Book không tự cung cấp optimistic locking cho bulk JPQL DELETE**; nếu cần bảo vệ, phải đưa điều kiện version/concurrency vào thiết kế.

## 30. Bulk DELETE có thể ảnh hưởng số lượng lớn hơn dự kiến

Một query:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b WHERE b.status = :status"
)
.setParameter("status", BookStatus.ARCHIVED)
.executeUpdate();
```

có thể xóa hàng triệu Book nếu trạng thái ARCHIVED phổ biến. Điều này có thể dẫn đến:

- Transaction log/WAL rất lớn.
- Lock contention và blocking.
- Replication lag.
- DB CPU/IO cao.
- Nhiều rows/tables bị xóa do DB cascade/trigger.
- Chậm vacuum/garbage collection của DB.
- Mất khả năng khôi phục nghiệp vụ nếu không có backup/retention plan.

### Guard rail trong job

Có thể áp dụng:

1. Dry-run bằng `SELECT COUNT(b)` với **cùng điều kiện**.
2. Ghi nhận số lượng ước tính và ngưỡng cho phép.
3. Bắt buộc tenant/status/cutoff.
4. Chỉ xóa mỗi batch số lượng giới hạn.
5. Thực thi trong cửa sổ phù hợp và có monitoring.
6. Giới hạn số batch/thời gian chạy.
7. Có kill switch/feature flag cho job.
8. Ghi metrics về số entity bị xóa, thời gian và lỗi.
9. Đảm bảo restore/backup policy nếu dữ liệu quan trọng.
10. Kiểm tra sau commit từ context độc lập.

### Count trước DELETE không khóa dữ liệu

```java
Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE ...",
    Long.class
).getSingleResult();
```

Count trong một transaction có thể khác số DELETE thực tế do concurrency, isolation hoặc state thay đổi. Đây chỉ là **ước lượng/kiểm tra an toàn**, không phải một bảo đảm atomic rằng đúng số hàng đó sẽ bị xóa sau này.

Nếu cần giới hạn cứng số record bị xóa trong một batch, hãy chọn tập IDs ổn định và áp dụng locking/transaction strategy phù hợp, không chỉ đếm rồi chạy DELETE không giới hạn.

---

## 31. Spring Data JPA: `@Modifying` và `@Query`

Trong Spring Data JPA, có thể định nghĩa repository bulk delete:

```java
public interface BookRepository
        extends JpaRepository<Book, Long> {

    @Modifying
    @Query(
        "DELETE FROM Book b " +
        "WHERE b.status = :status AND b.createdAt < :cutoff"
    )
    int bulkDeleteOldBooks(
        @Param("status") BookStatus status,
        @Param("cutoff") LocalDateTime cutoff
    );
}
```

Một service điều phối transaction:

```java
@Service
public class BookCleanupService {

    private final BookRepository repository;

    public BookCleanupService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int purgeOldArchivedBooks(LocalDateTime cutoff) {
        return repository.bulkDeleteOldBooks(
            BookStatus.ARCHIVED,
            cutoff
        );
    }
}
```

Trong code trên:

- `@Query` định nghĩa JPQL DELETE.
- `@Modifying` báo cho Spring Data biết đây là modifying query.
- `@Transactional` tạo ranh giới transaction theo cấu hình Spring.
- Kiểu trả `int` là số entity bị xóa theo kết quả query.

**`@Modifying` là annotation của Spring Data JPA, không phải annotation trong chuẩn Jakarta Persistence.**

### `flushAutomatically` và `clearAutomatically`

Spring Data JPA hỗ trợ cấu hình:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("DELETE FROM Book b WHERE b.status = :status")
int deleteByStatus(@Param("status") BookStatus status);
```

Ý tưởng:

- `flushAutomatically` yêu cầu flush trước modifying query.
- `clearAutomatically` yêu cầu clear sau modifying query.

Cần thận trọng: clear có thể detach nhiều entity đang được service dùng, và nếu có pending changes chưa flush, chúng có thể bị mất. Không bật tự động chỉ để “sửa” mọi vấn đề mà không hiểu transaction/persistence context hiện tại.

### Derived delete methods không mặc nhiên là bulk DELETE

Trong Spring Data JPA, một số derived delete methods có thể tìm các entities rồi xóa từng entity để giữ callbacks/lifecycle. Đừng mặc định mọi method tên `deleteBy...` đều phát một JPQL bulk DELETE. Hãy xác định contract của phương thức và xem SQL nếu quan trọng.

Nếu cần bulk deletion rõ ràng, một `@Modifying @Query("DELETE ...")` thường diễn đạt ý định trực tiếp hơn.

## 32. Khi nào không nên dùng bulk DELETE?

Tránh dùng bulk JPQL DELETE làm lựa chọn mặc định nếu:

- Cần `@PreRemove`/`@PostRemove` cho từng entity.
- Cần audit per-entity hoặc domain events lấy từ state của từng Book.
- Cascade/orphanRemoval là một phần bắt buộc của nghiệp vụ.
- Entity graph có nhiều shared/dependent associations chưa được phân tích.
- Cần kiểm tra `@Version` của từng entity theo trạng thái đã load.
- Cần kiểm tra quyền xóa/phê duyệt riêng cho từng bản ghi.
- Cần soft delete thay vì xóa vật lý.
- Cần callback để xóa file/object storage bên ngoài DB.
- Dữ liệu có legal hold, retention policy hoặc lịch sử giao dịch.
- Transaction đang giữ một graph managed lớn vẫn cần tiếp tục sử dụng sau query.
- Database constraints không cho phép xóa trực tiếp đúng thứ tự.

Có thể chọn `em.remove()` theo batch hoặc chuyển workflow sang state machine/archive/purge hai giai đoạn.

### Callback ngoài DB không rollback cùng transaction

Nếu xóa Book đồng thời xóa ảnh từ object storage hoặc gửi event, các side effects đó **không tự rollback** khi database transaction thất bại. Đừng thực thi irreversible side effects giữa bulk DELETE và commit mà chưa có thiết kế phù hợp.

Có thể dùng after-commit hooks hoặc transactional outbox nếu hệ thống cần phát event đáng tin cậy sau khi xóa đã commit. Với yêu cầu phục hồi dữ liệu, phải thiết kế cleanup ngoài DB độc lập và idempotent.

## 33. Kiểm thử bulk DELETE đúng cách

Một integration test tốt phải xác nhận:

- Entity khớp điều kiện bị xóa sau commit.
- Entity **không** khớp điều kiện vẫn tồn tại.
- Shared Author vẫn tồn tại.
- Review dependent được xử lý đúng chiến lược, không mất/hỏng ngoài ý muốn.
- Query trả số lượng phù hợp với fixture.
- Persistence context stale không làm test kết luận sai.
- Rollback hoàn tác database changes.
- Trường hợp 0 result hoạt động.
- Tenant boundary được giữ nếu hệ thống đa tenant.

Các phép kiểm tra nên đọc kết quả **bằng EntityManager mới sau commit**, không chỉ dựa vào getter của Book đã tải trước khi xóa.

### Một helper giao dịch cho test

```java
import jakarta.persistence.*;
import java.util.function.Function;

final class JpaTestHelper {

    private final EntityManagerFactory emf;

    JpaTestHelper(EntityManagerFactory emf) {
        this.emf = emf;
    }

    <T> T inTransaction(Function<EntityManager, T> work) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            T result = work.apply(em);

            em.getTransaction().commit();
            return result;
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

    <T> T freshRead(Function<EntityManager, T> work) {
        EntityManager em = emf.createEntityManager();
        try {
            return work.apply(em);
        } finally {
            em.close();
        }
    }
}
```

Đây là helper resource-local; với Spring/JTA nên dùng transaction manager phù hợp môi trường. Fixture/test database cần có schema và persistence unit trước khi sử dụng.

## 34. Test 1: chỉ xóa Book đủ điều kiện

Tạo fixture:

```java
record Fixture(Long archivedOldId, Long activeId, Long authorId) {}

Fixture fixture = tx.inTransaction(em -> {
    Author author = new Author("Tác giả test");
    em.persist(author);

    Book archivedOld = new Book(
        "Old archived book",
        BookStatus.ARCHIVED,
        LocalDateTime.of(2020, 1, 1, 0, 0),
        author
    );

    Book active = new Book(
        "Active book",
        BookStatus.ACTIVE,
        LocalDateTime.of(2020, 1, 1, 0, 0),
        author
    );

    em.persist(archivedOld);
    em.persist(active);

    em.flush();

    return new Fixture(
        archivedOld.getId(),
        active.getId(),
        author.getId()
    );
});
```

Ở fixture này **chưa thêm Review**, để tránh FK làm nhiễu test căn bản về điều kiện DELETE.

Thực thi:

```java
int deleted = tx.inTransaction(em ->
    em.createQuery(
        "DELETE FROM Book b " +
        "WHERE b.status = :status AND b.createdAt < :cutoff"
    )
    .setParameter("status", BookStatus.ARCHIVED)
    .setParameter("cutoff", LocalDateTime.of(2022, 1, 1, 0, 0))
    .executeUpdate()
);

assertEquals(1, deleted);
```

Kiểm tra sau commit:

```java
tx.freshRead(em -> {
    assertNull(
        em.find(Book.class, fixture.archivedOldId())
    );

    assertNotNull(
        em.find(Book.class, fixture.activeId())
    );

    assertNotNull(
        em.find(Author.class, fixture.authorId())
    );

    return null;
});
```

Test có cả **phải xóa** và **phải giữ**, rất quan trọng để phát hiện sai WHERE.

### Vì sao không chỉ kiểm tra deleted == 1?

Nếu query xóa nhầm một Book khác nhưng vẫn đúng số lượng 1, assertion `deleted == 1` sẽ xanh. Phải kiểm tra ID dự kiến đã mất và ID cần bảo vệ vẫn còn.

## 35. Test 2: dependent Review ngăn bulk Book DELETE

Fixture có Book #X và Review thuộc Book đó, FK `review.book_id` không có ON DELETE CASCADE.

Thử:

```java
int deleted = em.createQuery(
    "DELETE FROM Book b WHERE b.id = :id"
)
.setParameter("id", bookIdWithReviews)
.executeUpdate();
```

Tùy database, statement có thể ném exception do FK. Test cần chuẩn bị transaction, bắt exception thích hợp và rollback; **không nên chỉ assert tên class exception cụ thể của provider** nếu yêu cầu portable.

Một test hữu ích hơn nữa xác nhận **chiến lược xóa hợp lệ**:

```java
record RemovalCounts(int reviews, int books) {}

RemovalCounts counts = tx.inTransaction(em -> {
    int reviews = em.createQuery(
        "DELETE FROM Review r WHERE r.book.id = :bookId"
    )
    .setParameter("bookId", bookIdWithReviews)
    .executeUpdate();

    int books = em.createQuery(
        "DELETE FROM Book b WHERE b.id = :bookId"
    )
    .setParameter("bookId", bookIdWithReviews)
    .executeUpdate();

    em.clear();

    return new RemovalCounts(reviews, books);
});

assertEquals(2, counts.reviews());
assertEquals(1, counts.books());
```

Sau đó dùng context mới kiểm tra Book và Review đã bị xóa, Author vẫn còn.

### Vì sao không đưa FK violation thành điều kiện thành công duy nhất?

Vì DB có thể có ON DELETE CASCADE trong môi trường khác, hoặc migration khác với test. Nếu test chủ động kiểm chứng FK bảo vệ phụ thuộc, phải dùng schema test tương ứng. Nếu use case cho phép DB cascade, test phải xác nhận Review biến mất đúng và không ảnh hưởng dữ liệu độc lập.

## 36. Test 3: managed entity trở nên stale

Một test minh họa tình huống:

```java
@Test
void bulkDeleteDoesNotUpdateOldJavaReference() {
    Long bookId = seedBookWithoutReviews();

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, bookId);
        assertNotNull(book);

        String oldTitle = book.getTitle();

        int count = em.createQuery(
            "DELETE FROM Book b WHERE b.id = :id"
        )
        .setParameter("id", bookId)
        .executeUpdate();

        assertEquals(1, count);

        // Đối tượng Java cũ không tự biến mất khỏi heap.
        assertEquals(oldTitle, book.getTitle());

        // Kết thúc việc dùng managed graph trước khi đọc lại DB.
        em.clear();

        assertNull(em.find(Book.class, bookId));

        em.getTransaction().commit();
    } finally {
        em.close();
    }
}
```

Test chứng minh sự khác nhau giữa Java reference đã được lưu trong biến và dữ liệu trong DB. Đừng viết code kỳ vọng `bulk DELETE` biến `book` thành null hoặc tự gọi `remove(book)` trong context.

Nếu test cần portable hơn giữa các provider, nên tập trung assertion vào **số lượng xóa và kết quả từ context mới sau commit**, thay vì các chi tiết internal context state ngay sau bulk DML. Java reference vẫn tồn tại vì không có thao tác Java nào xóa biến/object.

## 37. Test 4: rollback bulk DELETE

```java
@Test
void rollbackPreservesDatabaseRow() {
    Long bookId = seedBookWithoutReviews();

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        int deleted = em.createQuery(
            "DELETE FROM Book b WHERE b.id = :id"
        )
        .setParameter("id", bookId)
        .executeUpdate();

        assertEquals(1, deleted);

        em.getTransaction().rollback();
    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();
    try {
        assertNotNull(verify.find(Book.class, bookId));
    } finally {
        verify.close();
    }
}
```

Trong transaction, SQL DELETE có thể đã thực thi. Nhưng rollback thành công hoàn tác thay đổi thuộc transaction. Chỉ kiểm tra sau rollback bằng **context mới** mới thể hiện chính xác mục đích test.

Nếu database có transaction khác đồng thời sửa/xóa Book đó, test cần fixture isolation để không nhầm nguyên nhân.

## 38. Test 5: bulk DELETE không chạy entity callback

Giả sử trong Book:

```java
@PreRemove
void beforeRemove() {
    // Gọi audit hook hoặc tăng counter thử nghiệm.
}
```

Khi test cần chứng minh khác biệt, có thể cấu hình một `EntityListener` theo đúng cơ chế test để đếm số lần callback chạy trong hai trường hợp:

1. `em.remove(book)` rồi flush/commit.
2. `DELETE FROM Book b WHERE b.id = :id` rồi executeUpdate/commit.

Kỳ vọng theo ngữ nghĩa JPA: bulk DELETE **không tạo callback `@PreRemove` cho từng Book bị xóa**. Tuy nhiên, việc kiểm tra listener side effects phải được cô lập theo test và transaction; static counters toàn cục có thể gây race khi chạy test song song.

Nếu ứng dụng đang sử dụng audit framework riêng hoặc provider extension, kiểm tra cả audit rows/DB triggers để xác định cơ chế nào thực sự chịu trách nhiệm.

## 39. Test 6: tenant boundary và điều kiện lọc

Nếu Book có `tenantId`, tạo fixture:

```text
Tenant A: Book #1 ARCHIVED, createdAt=2020
Tenant A: Book #2 ACTIVE,   createdAt=2020
Tenant B: Book #3 ARCHIVED, createdAt=2020
```

JPQL:

```java
"DELETE FROM Book b " +
"WHERE b.tenantId = :tenantId " +
"AND b.status = :status " +
"AND b.createdAt < :cutoff"
```

Assert:

- Book #1 bị xóa.
- Book #2 còn.
- Book #3 còn.
- `deleted == 1`.
- Không có dependent/shared data nào bị ảnh hưởng sai.

**Đây là kiểm thử ranh giới phân quyền**, không chỉ test SQL. Trường `tenantId` phải được khai báo trong entity/migration của dự án khi áp dụng ví dụ.

## 40. Kiểm tra SQL thực tế và hiệu năng

JPA provider có thể phát:

```sql
DELETE FROM books
WHERE status = ?
  AND created_at < ?;
```

Đây chỉ là minh họa. Với inheritance, dialect, filter và mapping cụ thể, SQL có thể khác hoặc có nhiều statements.

Khi cần phân tích:

- Bật SQL logging/statistics phù hợp.
- Quan sát số statements.
- Xác nhận bind parameters đúng trạng thái/cutoff/tenant.
- Kiểm tra indexes trên các cột lọc.
- Quan sát execution plan.
- Theo dõi transaction duration, locks, WAL/log volume và replication lag.
- Kiểm chứng FK/dependent handling.
- Đo sau vài batch chứ không chỉ một lần xóa ít dữ liệu.

### Index có ý nghĩa gì?

Query:

```sql
DELETE FROM books
WHERE status = ?
  AND created_at < ?;
```

có thể hưởng lợi từ index hỗ trợ lọc theo status/created_at, nhưng chi phí DELETE còn gồm cập nhật indexes, foreign key checks, triggers và DB maintenance. Không phải mọi index đều giúp DELETE nhanh hơn: quá nhiều index còn làm mỗi lần xóa tốn công duy trì hơn.

Vì vậy, hãy đo trên dữ liệu gần production và xem execution plan phù hợp DB.

## 41. Ma trận lựa chọn cách xóa

| Tình huống | Cách tiếp cận thường phù hợp |
| --- | --- |
| Xóa một Book đã managed, cần callbacks | `em.remove(book)` |
| Xóa hàng loạt Book độc lập theo điều kiện | JPQL bulk DELETE |
| Xóa Book có Review và cần callbacks của Review | Xóa qua lifecycle JPA theo batch |
| Xóa Book có Review nhưng không cần callback, DB có FK | Xóa Review trước trong transaction hoặc DB cascade có chủ đích |
| Xóa theo ID và expected version | JPQL DELETE có predicate version + kiểm tra affected count |
| Xóa hàng triệu bản ghi, cần giới hạn lock | Chia batch theo IDs/transaction |
| Cần cú pháp DELETE JOIN/LIMIT riêng DB | Native SQL có kiểm soát và test dialect |
| Cần soft delete/restore | Bulk UPDATE cờ hoặc domain workflow |
| Cần audit và legal retention | Workflow archive/purge + audit/outbox |
| Context đang giữ nhiều managed Book | Tách context, flush/clear có chủ đích |
| Dữ liệu shared target còn được dùng | Chỉ xóa entity/association thuộc ownership, giữ shared target |
| Hệ thống đa tenant | Có điều kiện tenant đáng tin và test giữ dữ liệu tenant khác |

---

## 42. Những lỗi thường gặp

### Lỗi 1: Viết tên bảng SQL trong JPQL

```java
em.createQuery("DELETE FROM books WHERE status = 'ARCHIVED'");
```

Nếu `books` là tên bảng, JPQL không tìm thấy entity tương ứng. Dùng `Book` và thuộc tính Java hoặc chuyển sang `createNativeQuery` khi muốn SQL.

### Lỗi 2: Dùng `getResultList()` để xóa

JPQL DELETE phải thực thi qua `executeUpdate()`, không phải getResultList/getSingleResult.

### Lỗi 3: Quên transaction

Bulk DELETE cần transaction phù hợp. Với resource-local gọi begin/commit/rollback; với Spring/JTA dùng transaction manager.

### Lỗi 4: Quên WHERE

`DELETE FROM Book` có thể xóa mọi Book thuộc entity type. Guard tenant/status/cutoff và batch boundaries.

### Lỗi 5: Nghĩ cascade REMOVE vẫn chạy

JPQL bulk DELETE không gọi `em.remove()` cho từng Book nên không tự cascade tới Review theo JPA.

### Lỗi 6: Nghĩ orphanRemoval là DB trigger

`orphanRemoval = true` không tự dọn child rows khi parent bị xóa bằng bulk DML; cần xử lý FK riêng.

### Lỗi 7: Dùng bulk DELETE và đòi `@PreRemove` được gọi

Bulk DML không kích hoạt callbacks per-entity như thao tác remove bình thường.

### Lỗi 8: Quên first-level cache stale

Đã load Book trước khi bulk DELETE; sau đó getter/find trong cùng context có thể dùng state cũ. Dùng clear hoặc context mới.

### Lỗi 9: `clear()` khi còn pending changes

Clear có thể làm mất các thay đổi chưa flush. Phải xác định cái gì cần lưu trước khi detach.

### Lỗi 10: Nghĩ `@Version` tự kiểm tra

Bulk DELETE không tự dùng version của từng managed Book. Khi cần optimistic condition, bổ sung WHERE version có chủ đích.

### Lỗi 11: Dùng `setMaxResults(100)` như DELETE LIMIT

Không portable. Chọn IDs bằng SELECT có limit rồi DELETE theo batch trong transaction phù hợp.

### Lỗi 12: Xóa dependent ở transaction khác

Nếu child DELETE commit nhưng parent DELETE thất bại, graph bị phá. Dùng cùng transaction khi cần atomicity.

### Lỗi 13: Chọn IDs rồi xóa mà bỏ qua concurrent changes

Trạng thái có thể đổi giữa chọn target và xóa. Dùng condition/locking/isolation phù hợp.

### Lỗi 14: Query sai tenant

Một DELETE đúng cú pháp có thể xóa dữ liệu của tenant khác. Điều kiện tenant phải đến từ context phân quyền đáng tin.

### Lỗi 15: Chỉ assert số hàng bị xóa

`deleted == 1` không chứng minh đã xóa đúng entity. Kiểm tra ID cần xóa và ID bắt buộc còn.

### Lỗi 16: Kiểm tra bằng cùng persistence context

Managed Book cũ có thể stale; test sau commit phải dùng EntityManager mới.

### Lỗi 17: Nghĩ rollback sẽ hoàn tác setters

Database rollback thay đổi thuộc transaction; Java object không tự trở lại trạng thái ban đầu.

### Lỗi 18: Tự động gọi `merge()` trên Book đã bị bulk DELETE

Graph stale có thể gây exception hoặc persistence behavior không mong muốn. Không tái sử dụng entity đã xóa như dữ liệu hiện hành.

### Lỗi 19: Dùng DB cascade mà kỳ vọng callback Java

ON DELETE CASCADE hoạt động ở database; không tự chạy JPA `@PreRemove` cho dependent rows.

### Lỗi 20: Dùng JPQL DELETE khi nghiệp vụ chỉ muốn archive

DELETE xóa vật lý; nếu cần khôi phục/giữ dữ liệu, dùng workflow soft-delete/retention.

## 43. Bài tập thực hành

### Bài tập 1: Cú pháp cơ bản

**Yêu cầu:** Xóa mọi Book có `status = ARCHIVED` và `createdAt` trước ngày 01/01/2023.

**Gợi ý đáp án:**

```java
int deleted = em.createQuery(
    "DELETE FROM Book b " +
    "WHERE b.status = :status " +
    "AND b.createdAt < :cutoff"
)
.setParameter("status", BookStatus.ARCHIVED)
.setParameter("cutoff", LocalDateTime.of(2023, 1, 1, 0, 0))
.executeUpdate();
```

Thực hiện trong transaction và commit/rollback phù hợp.

### Bài tập 2: Đọc kiểu kết quả

**Câu hỏi:** `executeUpdate()` trả `List<Book>` hay `int`?

**Đáp án:** Trả `int` biểu thị số entity được xóa theo query contract. Không trả Book instances đã xóa.

### Bài tập 3: Callback

Có `@PreRemove` trên Book; job dùng JPQL DELETE.

**Câu hỏi:** Callback có tự chạy cho mỗi Book không?

**Đáp án:** Không. Bulk DML bỏ qua per-entity lifecycle callbacks. Nếu bắt buộc phải chạy, dùng `em.remove()` theo batch hoặc thiết kế audit độc lập.

### Bài tập 4: OrphanRemoval

Book có danh sách Review với `orphanRemoval = true`. Bulk DELETE Book thất bại do foreign key.

**Câu hỏi:** Vì sao?

**Đáp án:** Bulk DELETE không tự kích hoạt orphan removal/cascade JPA. Review vẫn tham chiếu Book ở DB. Xóa Review trước trong cùng transaction hoặc dùng DB cascade nếu chính sách cho phép.

### Bài tập 5: Managed entity stale

Book #42 đã load, sau đó JPQL bulk DELETE Book #42.

**Câu hỏi:** `book.getTitle()` còn trả dữ liệu cũ có chứng minh DELETE thất bại không?

**Đáp án:** Không. Java object vẫn tồn tại. Kiểm chứng từ context mới sau commit.

### Bài tập 6: Flush và clear

Một service sửa giá của Book #43, sau đó bulk DELETE Book cũ và gọi `em.clear()`.

**Câu hỏi:** Nguy cơ nào nếu chưa flush thay đổi giá?

**Đáp án:** `clear()` có thể detach Book #43 và làm mất pending change. Cần xác định có nên flush trước bulk/clear hoặc tách đơn vị công việc.

### Bài tập 7: Delete theo Author

**Yêu cầu:** Xóa Book của Author có tên “An” bằng JPQL mà không JOIN trực tiếp trong outer DELETE.

**Gợi ý:**

```java
"DELETE FROM Book b " +
"WHERE b.author IN (" +
"  SELECT a FROM Author a WHERE a.name = :name" +
")"
```

Nếu Book có Reviews và FK không cascade, vẫn phải xử lý dependents.

### Bài tập 8: Version

Book #42 version 5, client gửi expectedVersion 4.

**Câu hỏi:** Dùng query nào để từ chối xóa khi version không khớp?

**Đáp án:**

```java
"DELETE FROM Book b " +
"WHERE b.id = :id AND b.version = :expectedVersion"
```

Bind expectedVersion=4 và kiểm tra count bằng 0. Cần xử lý không tồn tại/không đủ quyền theo chính sách.

### Bài tập 9: Giới hạn 100 hàng

**Câu hỏi:** Có thể dựa vào `setMaxResults(100)` trên JPQL DELETE không?

**Đáp án:** Không nên. Chọn tối đa 100 IDs bằng SELECT có order, sau đó DELETE theo `IN :ids` trong transaction phù hợp; phải xét concurrency/child rows.

### Bài tập 10: Rollback

Bulk DELETE trả 12 và sau đó transaction rollback.

**Câu hỏi:** Có thể khẳng định 12 Book đã bị xóa bền vững không?

**Đáp án:** Không. Khi rollback thành công, thay đổi DB thuộc transaction bị hoàn tác. `executeUpdate()` không phải commit.

### Bài tập 11: Tenant

Hai tenant có Book ARCHIVED cùng thời điểm. Job cleanup chạy cho tenant A.

**Câu hỏi:** Cần test gì?

**Đáp án:** Book đủ điều kiện của tenant A bị xóa; mọi Book của tenant B vẫn còn. Không chỉ assert số lượng xóa.

### Bài tập 12: SQL statement và entity count

Có inheritance JOINED; provider phát hai SQL DELETE statements để xóa một loại entity.

**Câu hỏi:** `executeUpdate()` có bắt buộc bằng tổng số SQL rows từ hai câu DELETE không?

**Đáp án:** Không. Contract nói về số entity bị tác động; các SQL physical rows/statements tùy mapping/provider.

### Bài tập 13: Soft delete

Business yêu cầu Book vẫn có thể restore trong 30 ngày.

**Câu hỏi:** Bulk DELETE vật lý có phù hợp khi người dùng vừa nhấn Delete không?

**Đáp án:** Thường không. Nên đánh dấu deleted/archived và purge vật lý sau retention theo policy.

### Bài tập 14: Xóa theo batch không dùng OFFSET tăng dần

Một job mỗi batch DELETE 500 Book đủ điều kiện. Sau batch đầu, query tiếp dùng OFFSET 500.

**Câu hỏi:** Vì sao có thể bỏ sót?

**Đáp án:** Tập kết quả đã rút ngắn do delete; OFFSET 500 bỏ qua những record lẽ ra nằm ở đầu tập còn lại. Chọn trang đầu mỗi lần hoặc keyset strategy phù hợp.

### Bài tập 15: Audit

Hệ thống muốn biết chính xác những Book IDs vừa bị xóa. Bulk DELETE chỉ trả count.

**Câu hỏi:** Cần thiết kế thế nào?

**Đáp án:** Chọn/ghi nhận IDs hoặc audit rows một cách nhất quán với transaction trước khi delete; không suy ID từ `executeUpdate()`. Nếu có concurrency, phải kiểm soát tập target để audit tương ứng dữ liệu thực sự bị xóa.

---

## 44. Checklist trước khi chạy JPQL bulk DELETE

1. **Đây là entity name hay table name?** JPQL dùng entity.
2. **Có WHERE đủ chặt không?** Tenant, trạng thái, cutoff, điều kiện giữ lại?
3. **Nếu không có WHERE, có thực sự muốn xóa mọi entity type không?**
4. **Query được thực thi bằng `executeUpdate()` chứ?**
5. **Transaction đang hoạt động và persistence context đã tham gia phù hợp chưa?**
6. **Các parameters được bind đúng type, tránh nối input chưa kiểm soát không?**
7. **Có dependent child rows với foreign key không?**
8. **Có định dùng JPA cascade/orphanRemoval mà bulk DELETE không chạy không?**
9. **Nếu cần xóa child trước, các bước có cùng transaction không?**
10. **Có shared entities không được xóa (Author, Product, Category...) không?**
11. **Có DB ON DELETE CASCADE/trigger cần tính đến không?**
12. **Có lifecycle callbacks, audit hoặc domain events bắt buộc không?**
13. **Có `@Version`/optimistic locking cần kiểm tra tường minh không?**
14. **Có managed entities đang load sẽ stale sau DELETE không?**
15. **Có pending managed changes cần flush trước khi clear không?**
16. **Ai sở hữu EntityManager và ai được phép clear nó?**
17. **Có second-level/query/application cache cần invalidation không?**
18. **Có dùng `setMaxResults` sai như DELETE LIMIT không?**
19. **Tập IDs có vượt giới hạn bind parameters không?**
20. **DELETE có đủ nhỏ để không giữ lock/transaction quá lâu không?**
21. **Có dry-run count/ngưỡng bảo vệ và kill switch cho cleanup job không?**
22. **Có kiểm soát concurrency giữa chọn IDs và DELETE không?**
23. **Có chính sách rollback/retry rõ ràng khi constraint/deadlock lỗi không?**
24. **Có soft delete/retention/legal hold trước purge vật lý không?**
25. **Có test kết quả sau commit bằng context mới không?**
26. **Có test rollback và not-found/zero-result không?**
27. **Có test giữ dữ liệu không khớp điều kiện không?**
28. **Có test không xóa nhầm tenant/shared target không?**
29. **Có đo SQL, DB locking, WAL và replication lag trên dữ liệu thực tế không?**
30. **Có đường khôi phục hoặc audit phù hợp cho dữ liệu quan trọng không?**

Checklist này không yêu cầu mọi job phải phức tạp. Nó giúp nhận diện ranh giới nơi một câu `DELETE` tưởng như ngắn gọn có thể phá vỡ các bảo đảm của entity lifecycle và toàn vẹn dữ liệu.

## Kết luận

**JPQL bulk DELETE** là công cụ hiệu quả để xóa nhiều entity theo điều kiện:

```java
int affected = em.createQuery(
    "DELETE FROM Book b WHERE b.status = :status"
)
.setParameter("status", BookStatus.ARCHIVED)
.executeUpdate();
```

Nó dùng **entity name và thuộc tính JPA**, thực thi qua **`executeUpdate()`** trong transaction, và trả số entity bị tác động. Vì không phải tải từng entity, bulk DELETE thường phù hợp với cleanup jobs và các thao tác xóa có số lượng lớn.

Tuy nhiên, điều quyết định tính đúng là những gì bulk DELETE **không làm**: nó không tự cascade REMOVE/orphanRemoval theo từng entity, không tự gọi `@PreRemove`/`@PostRemove`, không tự áp dụng optimistic locking `@Version` như `em.remove()`, và không đồng bộ những managed objects đang nằm trong persistence context. Database foreign keys, DB cascades và triggers vẫn có hiệu lực theo schema.

Với graph có dependent entities, cần **xóa child trước trong cùng transaction**, dùng DB cascade có chủ đích, hoặc chọn `em.remove()` khi lifecycle semantics quan trọng. Với context đang có state, cần xác định **flush trước và clear sau** khi phù hợp, hoặc dùng transaction/EntityManager mới để tránh stale state. Với job xóa khối lượng lớn, cần batch, kiểm soát concurrency, tenant boundary, retention, audit và khả năng rollback.

Hãy nhớ bốn câu hỏi trước mọi bulk DELETE: **“Tôi thực sự muốn xóa entity nào? Những entity/quan hệ nào phải được giữ? Persistence context còn phản ánh DB sau thao tác không? Tôi đã xác minh kết quả sau commit trong context mới chưa?”**. Trả lời rõ chúng giúp tận dụng hiệu năng của JPQL DELETE mà không đánh đổi tính toàn vẹn và an toàn dữ liệu.
