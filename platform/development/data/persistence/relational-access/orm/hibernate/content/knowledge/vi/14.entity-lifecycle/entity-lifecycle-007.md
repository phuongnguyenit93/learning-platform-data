# detach, clear và việc chấm dứt quản lý trạng thái

## 1. Tại sao phải hiểu việc một entity ngừng được Hibernate quản lý?

Khi dùng Hibernate ORM, cùng một đối tượng Java có thể được tạo mới, được Hibernate quản lý trong một `Session`/`EntityManager`, rồi trở thành đối tượng **detached** khi không còn thuộc persistence context. Đây là một trong những ranh giới quan trọng nhất của vòng đời thực thể: trước ranh giới ấy, thay đổi field có thể được Hibernate phát hiện để ghi SQL; sau ranh giới ấy, cùng một thao tác Java không còn tự động đồng bộ xuống database.

Hãy tưởng tượng ứng dụng quản lý sách. Một lần xử lý nghiệp vụ có thể diễn ra:

```text
Database: books(id=42, title="Hibernate cơ bản", version=3)
                       │
                       │ em.find(Book.class, 42L)
                       ▼
             Persistence Context A
             ┌───────────────────────────────┐
             │ Book #42  [MANAGED]           │
             │ title = "Hibernate cơ bản"    │
             │ Hibernate theo dõi thay đổi   │
             └───────────────────────────────┘
                       │
                       │ book.rename("Hibernate nâng cao")
                       │ flush / commit
                       ▼
             SQL UPDATE khi phù hợp

Khi em.detach(book) hoặc em.clear():
             Book #42 [DETACHED]
                       │
                       │ book.rename("Tên mới khác")
                       ▼
             Chỉ đổi Java object hiện tại
             Không có dirty checking của PC A cho object đó
```

Trong bài này, **persistence context** (viết tắt PC) là tập hợp các entity đang được quản lý và thông tin Hibernate cần để đồng bộ chúng với database. Các API `detach()` và `clear()` làm thay đổi thành viên của PC; chúng **không phải** là thao tác xóa bản ghi khỏi database hay đóng toàn bộ hạ tầng kết nối.

Ba câu hỏi xuyên suốt bài:

1. **Entity nào vẫn managed?** Chỉ entity đó mới được Hibernate theo dõi thay đổi trạng thái theo cơ chế bình thường.
2. **Những thay đổi nào đã được flush?** Rời PC trước khi flush có thể khiến thay đổi chưa đồng bộ bị mất.
3. **Sau khi detached, phải làm gì nếu muốn ghi dữ liệu?** Tải managed instance mới và áp dụng thay đổi có kiểm soát, hoặc dùng `merge()` với đầy đủ hiểu biết về semantics.

## 2. Persistence context là gì?

Hibernate thường quản lý entity thông qua `Session`. Khi dùng Jakarta Persistence, ứng dụng làm việc qua `EntityManager`; Hibernate là provider thực thi và cung cấp `Session` phía dưới. Một persistence context gắn với phạm vi quản lý đó có các nhiệm vụ:

- Duy trì **identity map**: trong cùng một PC, cùng entity type và identifier thường có một managed instance đại diện.
- Biết trạng thái entity đã đọc và trạng thái hiện tại để thực hiện **dirty checking**.
- Quản lý lịch trình `INSERT`, `UPDATE`, `DELETE` và thay đổi quan hệ/collection trước khi flush.
- Phối hợp lazy loading, proxy và persistent collection còn gắn với session.
- Hỗ trợ thao tác vòng đời như `persist`, `remove`, `refresh`, `detach` và `merge`.

Một ví dụ:

```java
Book first = em.find(Book.class, 42L);
Book second = em.find(Book.class, 42L);

System.out.println(first == second); // true trong cùng PC
System.out.println(em.contains(first)); // true nếu đang managed
```

Hibernate có thể dùng dữ liệu từ PC để trả về object đã có mà không đọc lại row, nhưng không phải mọi HQL/JPQL query đều được bỏ qua SQL. Query vẫn có thể chạy để xác định tập kết quả, sau đó ánh xạ hàng vào managed instances tương ứng.

### 2.1. “Managed” không đồng nghĩa “transaction đang commit”

Một entity có thể vẫn thuộc persistence context sau một transaction đã commit, tùy loại EntityManager/session và phạm vi lifecycle của framework. Ngược lại, một entity có thể bị detach **trong khi transaction vẫn còn hoạt động**. Do đó:

- **Transaction** quyết định ranh giới nguyên tử của các thay đổi database.
- **Persistence context** quyết định những object Java nào đang được ORM quản lý.
- **Session/EntityManager lifecycle** quyết định khi nào PC được tạo, xóa và đóng; phạm vi phụ thuộc application-managed, container-managed hoặc transaction-scoped/persistence context mở rộng.

Không sử dụng cụm “đã commit” như từ đồng nghĩa với “đã detached”. Trong một transaction-scoped persistence context thông thường, container có thể kết thúc PC cùng transaction, nhưng đó là lựa chọn quản lý của runtime chứ không phải định nghĩa chung của `commit()`.

## 3. Bốn trạng thái thường gặp của entity

| Trạng thái | Có trong persistence context? | Có row tương ứng trong DB? | Điểm cần nhớ |
|---|---|---|---|
| **Transient/New** | Không | Chưa chắc; object Java vừa tạo thường chưa có row | `new Book(...)` chưa phải managed; `persist()` để yêu cầu lưu |
| **Managed/Persistent** | Có | Có hoặc đang được lên lịch tạo trong transaction | Hibernate theo dõi, hỗ trợ flush/dirty checking |
| **Detached** | Không | Thường có row trước đó, nhưng không được bảo đảm còn tồn tại | Có ID và dữ liệu cũ, không tự được flush khi sửa |
| **Removed** | Được đánh dấu xóa trong PC trước khi hoàn tất | Row có thể chưa bị SQL DELETE trước flush | `remove()` khác hoàn toàn `detach()` |

Sơ đồ trạng thái:

```text
new Book(...)
      │
      ▼
   TRANSIENT ─────── persist() ─────────► MANAGED
                                          │
       ┌──────────────────────────────────┼───────────────────────┐
       │                                  │                       │
       │ em.detach(entity)                │ em.remove(entity)     │
       │ em.clear()                       │                       │
       │ close/end of PC                  │                       │
       ▼                                  ▼                       │
   DETACHED                            REMOVED                    │
       │                                                          │
       │ merge(detached) → managed instance trả về                 │
       └──────────────────────────────────────────────────────────┘
                                                                  │
                                          flush/commit đồng bộ SQL
```

`merge()` **không biến object detached ban đầu thành managed**. Nó sao chép state phù hợp vào một managed instance và trả về instance đó. Nếu lập sơ đồ đơn giản bằng mũi tên “DETACHED → MANAGED”, phải nhớ có thể là **hai Java references khác nhau**.

## 4. Ví dụ entity để thực hành vòng đời

Giả sử bảng PostgreSQL:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    isbn VARCHAR(32) NOT NULL UNIQUE,
    version BIGINT NOT NULL DEFAULT 0
);
```

Entity với Jakarta Persistence:

```java
package com.example.library.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255)
    private String title;

    @Column(nullable = false, unique = true, length = 32)
    private String isbn;

    @Version
    private Long version;

    protected Book() {
        // Constructor dành cho Hibernate/JPA.
    }

    public Book(String isbn, String title) {
        if (isbn == null || isbn.isBlank()
                || title == null || title.isBlank()) {
            throw new IllegalArgumentException(
                    "ISBN và tiêu đề phải có giá trị");
        }
        this.isbn = isbn;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public String getIsbn() { return isbn; }
    public Long getVersion() { return version; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = newTitle;
    }
}
```

Thư viện Hibernate ORM, JDBC driver, `SessionFactory` và database đã được cấu hình phù hợp. Nếu dùng Hibernate để đối chiếu schema, có thể chọn `hibernate.hbm2ddl.auto=validate` khi migration quản lý DDL. Các đoạn code tiếp theo tập trung vào thao tác PC, giả định có một `EntityManager` trong phạm vi transaction hoặc `SessionFactory` của ứng dụng.

## 5. detach(): loại một entity khỏi persistence context

Jakarta Persistence định nghĩa:

```java
entityManager.detach(entity);
```

Sau lệnh này, entity không còn được EntityManager ấy quản lý. Với Hibernate native `Session`, API `evict(entity)` có ý nghĩa gần tương đương để đưa một entity ra khỏi persistence context:

```java
session.evict(entity);
```

Lưu ý sự khác nhau giữa API chuẩn Jakarta Persistence và API riêng của Hibernate khi viết code cần portable sang JPA provider khác.

### 5.1. Minh họa chính xác với EntityManager

Ví dụ:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityTransaction tx = em.getTransaction();
tx.begin();
try {
    Book book = em.find(Book.class, 42L);
    if (book == null) {
        throw new IllegalArgumentException("Không tìm thấy sách");
    }

    System.out.println(em.contains(book)); // true

    em.detach(book);
    System.out.println(em.contains(book)); // false

    book.rename("Tiêu đề chỉ đổi trong Java");

    tx.commit(); // Không cập nhật field title của book đã detached
} catch (RuntimeException | Error failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }
    throw failure;
}
```

Đoạn code minh họa **resource-local EntityManager** do ứng dụng quản lý; không áp dụng `em.getTransaction()` trực tiếp khi đang dùng JTA/container-managed transactions. Trong Spring, dùng `@Transactional` và tránh tự commit trong service.

`em.detach(book)` không gọi SQL `DELETE`, không tự đóng `EntityManager`, và không kết thúc transaction. Nó chỉ chấm dứt quản lý object tương ứng. Sau đó, `rename()` vẫn chạy như một phương thức Java bình thường nhưng Hibernate không dirty-check object ấy nữa.

### 5.2. detach không làm object biến mất

Object Java vẫn tồn tại nếu application còn giữ reference:

```java
Book book = em.find(Book.class, 42L);
Long id = book.getId();

em.detach(book);

System.out.println(book.getId().equals(id)); // true
System.out.println(book.getTitle());         // field đã load vẫn đọc được
```

`detach()` không đặt ID về null, không xóa dữ liệu đã đọc và không “reset” object. Nếu application lưu detached Book trong cache hoặc truyền nó sang tầng giao diện, đó vẫn là snapshot giá trị ở một thời điểm; nó có thể dần cũ so với database.

### 5.3. detach một entity, không phải clear cả session

```java
Book first = em.find(Book.class, 42L);
Book second = em.find(Book.class, 43L);

em.detach(first);

System.out.println(em.contains(first));  // false
System.out.println(em.contains(second)); // true
```

Ở đây `second` vẫn được quản lý bình thường. Vì thế `detach()` hữu ích khi chỉ muốn bỏ một object cụ thể khỏi PC mà vẫn giữ những entity khác.

## 6. clear(): loại toàn bộ entity khỏi persistence context

Jakarta Persistence và Hibernate đều có phương thức:

```java
entityManager.clear();
// Hoặc:
session.clear();
```

Ý nghĩa là **xóa toàn bộ entity đang managed khỏi persistence context hiện tại**. Không nên hiểu “xóa” ở đây là xóa các bản ghi trong database.

Ví dụ:

```java
Book a = em.find(Book.class, 42L);
Book b = em.find(Book.class, 43L);

System.out.println(em.contains(a)); // true
System.out.println(em.contains(b)); // true

em.clear();

System.out.println(em.contains(a)); // false
System.out.println(em.contains(b)); // false
```

`a` và `b` vẫn còn trong memory nếu code giữ references; các giá trị đã load có thể tiếp tục được đọc. Nhưng không object nào còn là managed entity của PC cũ.

### 6.1. Identity map sau clear

```java
Book oldReference = em.find(Book.class, 42L);

em.clear();

Book newReference = em.find(Book.class, 42L);

System.out.println(oldReference == newReference); // thường false
System.out.println(em.contains(oldReference));    // false
System.out.println(em.contains(newReference));    // true
```

Trong ví dụ bình thường, EntityManager tạo managed instance mới sau `clear()`. Dù hai Java object cùng `id=42`, chúng không cùng reference. Đừng dựa vào `==` để so sánh entity sống qua những persistence context khác nhau. Nếu định nghĩa `equals()/hashCode()` cho entity, cần bảo đảm nó tương thích generated IDs, detached instances và proxy.

### 6.2. clear không đóng EntityManager

Sau `em.clear()`, cùng `EntityManager` (nếu vẫn open) có thể tiếp tục query và tạo một PC đang được lấp đầy bằng các managed entities mới:

```java
em.clear();
Book book = em.find(Book.class, 42L);
// book là managed trở lại, nhưng là kết quả của lần nạp mới.
```

`clear()` **không** phải `close()`; nó không mặc nhiên ngắt mọi JDBC connection, không dừng transaction và cũng không đóng pool dùng chung.

## 7. So sánh detach, clear, flush, close và remove

Các API có tên ngắn nhưng tác động khác hẳn:

| Thao tác | Phạm vi | Entity sau đó | SQL/transaction | Tình huống sử dụng |
|---|---|---|---|---|
| `em.detach(entity)` | Một entity và các target có cascade DETACH phù hợp | Không còn managed trong PC đó | Không tự commit/DELETE; thay đổi chưa flush có thể mất | Ngừng theo dõi một object |
| `session.evict(entity)` | Tương tự ở Hibernate native | Không còn managed | Không tự commit | Hibernate Session API |
| `em.clear()`/`session.clear()` | Toàn bộ PC | Tất cả entity trở thành detached | Thay đổi chưa flush không được đồng bộ về sau qua PC này | Batch, bỏ state đang giữ, tránh PC phình |
| `em.flush()` | Các thay đổi pending trong PC | Vẫn managed | Thực thi SQL cần thiết trong transaction; **chưa commit** | Đồng bộ trước query/clear, phát hiện constraint |
| `em.close()` | Đóng application-managed EntityManager | Những managed entity của PC đó không còn được quản lý | Kết thúc vòng đời resource; không thay cho commit | Dừng sử dụng EntityManager |
| `session.close()` | Đóng Hibernate Session | Entity không còn được session quản lý | Giải phóng resource theo connection handling | Đóng một session tự quản lý |
| `em.remove(entity)` | Đánh dấu entity managed để xóa | Removed trong PC | Lên lịch SQL DELETE khi flush | Xóa row theo lifecycle ORM |
| `tx.rollback()` | Transaction | State JVM cần được xử lý như không đồng bộ | Hoàn tác SQL chưa commit ở database | Xử lý lỗi, hủy giao dịch |
| `tx.commit()` | Transaction | Tùy PC lifecycle còn managed hay không | Xác nhận thay đổi đã flush | Kết thúc đơn vị công việc thành công |

Các lời gọi `close()` không phải cách thay thế an toàn cho `commit()` hoặc `rollback()`. Ngay cả khi đóng session giải phóng resource, code cần kết thúc transaction có chủ đích và xử lý lỗi tương ứng.

### Không nhầm cache cấp một với cache cấp hai

Persistence context là **first-level cache/identity map** của session. `detach()` và `clear()` tác động lên nó. Hibernate còn có **second-level cache** tùy cấu hình ở phạm vi SessionFactory.

`em.clear()` không phải lệnh “xóa hết cache Hibernate” của toàn ứng dụng. Nếu cần evict các vùng cache cấp hai, Hibernate có API cache riêng, ví dụ `sessionFactory.getCache().evictEntityData(Book.class)` với provider/config tương thích. Không evict cache toàn cục chỉ vì một request muốn nhìn dữ liệu mới; cần chiến lược invalidation/freshness rõ ràng.

## 8. Thời điểm detach hoặc clear có thể làm mất thay đổi

Đây là điểm quan trọng nhất về tính đúng đắn.

Khi entity managed được sửa, Hibernate thường phát hiện thay đổi ở lần flush. Nếu entity bị detach trước khi thay đổi được flush, PC không còn theo dõi object để tạo UPDATE tương ứng.

Ví dụ **nguy hiểm**:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tiêu đề vừa sửa");

em.detach(book); // Bỏ quản lý khi thay đổi chưa được flush.

// Nếu chưa có flush tự động hoặc SQL tương ứng:
// commit sau đó không tự tìm lại thay đổi ở book.
```

Tương tự:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tiêu đề vừa sửa");

em.clear(); // Bỏ toàn bộ managed entities và thay đổi chưa flush.
```

Không nên “sửa rồi clear” nếu cần lưu thay đổi. Khi muốn đưa SQL xuống database trước khi clear:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tiêu đề cần lưu");

em.flush(); // Đồng bộ SQL trong transaction hiện tại.
em.clear(); // Sau đó bỏ các managed instances.

// Cuối transaction: commit thành công mới xác nhận thay đổi.
```

**Cảnh báo:** một câu JPQL query, native query hoặc việc commit có thể kích hoạt automatic flush tùy flush mode và provider. Vì vậy không nên tuyên bố “chưa gọi flush nên chắc chắn chưa có SQL”. Quy tắc an toàn là: **nếu muốn giữ thay đổi, flush có chủ đích trong transaction trước khi detach/clear**, sau đó commit để xác nhận. Nếu muốn hủy toàn bộ giao dịch, dùng rollback chứ không dùng clear như cơ chế undo.

### 8.1. flush rồi clear không phải commit

```text
begin transaction
  │
  ├── book.rename("A")
  ├── em.flush()      → SQL UPDATE đã chạy trong transaction
  ├── em.clear()      → Book không còn managed
  │
  ├── lỗi nghiệp vụ
  └── rollback()      → UPDATE vẫn bị database hoàn tác
```

`clear()` không “hoàn tác” SQL đã flush. Ngược lại, `flush()` không làm thay đổi trở thành bất khả đảo ngược. Cả hai API phải được đặt trong một chiến lược transaction hoàn chỉnh.

### 8.2. Những thao tác pending ngoài scalar field

Ngoài sửa `title`, PC còn theo dõi entity mới, removed entity và persistent collection. `clear()` có thể làm các thay đổi chưa flush ở các nhóm đó không được thực thi như người lập trình mong đợi.

Ví dụ:

```java
Order order = em.find(Order.class, orderId);
order.addLine(new OrderLine("JAVA", 2)); // Pending association/persist

em.clear(); // Không có lời bảo đảm thay đổi mới được ghi.
```

Với generator `IDENTITY`, Hibernate đôi khi phải INSERT sớm để lấy ID; với cascade, flush mode và thứ tự SQL, một phần hoạt động có thể đã xuống DB trước khi clear. Đừng suy luận “clear chắc chắn xóa mọi row vừa thêm” hoặc “clear chắc chắn không có SQL”. Ranh giới bảo đảm cần thiết là **transaction commit/rollback**. Muốn giữ mọi thay đổi: flush rồi commit. Muốn hủy: rollback.

## 9. detach không bảo đảm cả object graph cùng detached

Một entity có thể có association tới entity khác:

```java
@Entity
public class Publisher {
    @Id
    private Long id;

    private String name;

    protected Publisher() {}
}

@Entity
public class Book {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Publisher publisher;
}
```

Giả sử `Book` và `Publisher` đều đã được load vào cùng PC. Khi gọi:

```java
em.detach(book);
```

**Không mặc nhiên suy ra** `publisher` cũng detached. Một entity reference liên quan vẫn có thể managed nếu không có cascade DETACH phù hợp. Jakarta Persistence cung cấp `CascadeType.DETACH` hoặc `CascadeType.ALL` cho các association được cấu hình để detach lan truyền.

Ví dụ:

```java
@OneToMany(mappedBy = "order",
           cascade = {CascadeType.PERSIST, CascadeType.DETACH})
private List<OrderLine> lines = new ArrayList<>();
```

Khi detach Order, cascade DETACH có thể truyền tới những OrderLine liên quan theo mapping/provider. Nhưng không nên bật `CascadeType.ALL` chỉ để có tính năng detach; ALL cũng chứa `REMOVE`, điều có thể nguy hiểm với entity dùng chung hoặc relationship không sở hữu vòng đời.

### 9.1. clear khác cascade detach

`em.clear()` làm toàn bộ PC rời quản lý, không cần tìm đường association từ một root entity. Vì thế:

```java
Book book = em.find(Book.class, 42L);
Publisher publisher = em.find(Publisher.class, 9L);

em.detach(book);
// publisher có thể vẫn managed nếu không bị cascade DETACH.

em.clear();
// Cả book và publisher đều không còn managed trong PC.
```

Nếu muốn bỏ quản lý toàn bộ tập entity đang được giữ, `clear()` rõ ràng hơn việc duyệt graph thủ công gọi detach từng object. Nếu chỉ muốn giữ nguyên các entity khác, chọn detach trên đối tượng cụ thể.

### 9.2. Bidirectional association vẫn cần nhất quán

Detach không sửa quan hệ Java giữa parent và child. Nếu một detached parent vẫn tham chiếu tới child managed, việc sửa child managed trong transaction vẫn có thể ghi SQL. Không được dùng việc detach parent như một cơ chế bảo đảm rằng **toàn bộ graph** đã trở thành read-only.

Nếu domain yêu cầu kết quả truy vấn độc lập và bất biến, cách rõ ràng hơn là tạo DTO/projection chứa những scalar values cần thiết.

## 10. Lazy loading sau khi detached

Hibernate có thể trì hoãn tải association bằng lazy proxy hoặc persistent collection:

```java
@OneToMany(mappedBy = "book", fetch = FetchType.LAZY)
private List<Review> reviews = new ArrayList<>();
```

Nếu `reviews` chưa được khởi tạo:

```java
Book book = em.find(Book.class, 42L);
em.detach(book);

int count = book.getReviews().size();
// Có thể ném LazyInitializationException nếu collection chưa load
// và không còn session thích hợp để khởi tạo.
```

Hibernate cần session hợp lệ để thực hiện lazy load thông thường. Khi entity detached, nó không còn một persistence context quản lý để tải thêm dữ liệu theo đường bình thường. Đây là lý do endpoint trả trực tiếp entity từ service đã đóng transaction thường gặp `LazyInitializationException` ở tầng serializer.

### 10.1. Dữ liệu đã được khởi tạo trước detach

Nếu code thực sự cần đọc collection sau khi detach, có thể tải nó khi PC vẫn mở:

```java
import org.hibernate.Hibernate;

Book book = em.find(Book.class, 42L);
Hibernate.initialize(book.getReviews());

em.detach(book);

// Collection đã được khởi tạo trước đó; có thể đọc dữ liệu đã tải.
int count = book.getReviews().size();
```

Đây không phải giải pháp mặc định cho collection rất lớn. `Hibernate.initialize()` có thể tải toàn bộ association và kéo theo dữ liệu không cần thiết. Ngoài ra, một graph đã tải một collection vẫn có thể chứa **association lồng sâu chưa khởi tạo**. Việc initialize một mức không đồng nghĩa object graph đã detached hoàn toàn và sẵn sàng serialize.

### 10.2. DTO/projection tránh phụ thuộc vào Session

Một read model nhỏ:

```java
package com.example.library.readmodel;

public record BookSummary(
        Long id, String title, String publisherName) {}
```

JPQL constructor projection:

```java
List<BookSummary> rows = em.createQuery(
        "select new com.example.library.readmodel.BookSummary(" +
        "  b.id, b.title, p.name" +
        ") " +
        "from Book b join b.publisher p " +
        "order by b.id",
        BookSummary.class)
        .setMaxResults(50)
        .getResultList();
```

Query giả định `Book.publisher` mapping đúng và `BookSummary` có canonical constructor tương thích các expression. Kết quả record không phải managed entity, cũng không cần detach. Nó mang giá trị đã được chọn; không kích hoạt lazy load của `Book` khi code gọi `row.publisherName()`.

Đối với API read-only, lựa chọn projection đúng cột thường rõ và ít rủi ro hơn việc tải entity graph rồi detach để đưa sang UI.

## 11. detach khác read-only

Một số API làm thay đổi cách Hibernate theo dõi update, nhưng không giống detach:

| Cơ chế | Object còn managed? | Có dirty checking update? | Lazy loading thông thường còn dùng được? |
|---|---|---|---|
| `em.detach(entity)` | Không | Không qua PC cũ | Association chưa load có thể lỗi |
| `em.clear()` | Không, với mọi managed entity cũ | Không qua PC cũ | Association chưa load có thể lỗi |
| `session.setReadOnly(entity, true)` | Có | Giảm/bỏ theo dõi cập nhật scalar state của entity theo semantics Hibernate | Có, nếu session còn mở |
| Entity `@Immutable` | Có | Hibernate bỏ update trạng thái entity theo mapping | Có, nếu session còn mở |
| Spring `@Transactional(readOnly=true)` | Có thể có managed entities | Chủ yếu là hint/cấu hình flush và transaction, phụ thuộc integration | Phụ thuộc persistence context còn mở |
| DTO/record projection | Không phải entity managed | Không | Không có lazy proxy entity nếu DTO chỉ chứa scalar values |

Nếu nhu cầu là “đọc trong một transaction và không muốn update entity này”, đánh dấu read-only hoặc query DTO có thể hợp hơn detach. Nếu nhu cầu là “giải phóng managed entity khỏi PC để giảm state tracking và duyệt qua lô lớn”, detach/clear hợp hơn.

`@Immutable` được định nghĩa trên mapping, có phạm vi khác với `setReadOnly()` của một session cụ thể. `@Transactional(readOnly=true)` ở Spring không nên được coi là bảo đảm database từ chối mọi SQL UPDATE; cần quyền DB và chính sách transaction nếu muốn enforce read-only.

## 12. merge(): đưa dữ liệu từ detached object vào managed entity

Sau detach, nếu code tiếp tục thay đổi object và muốn ghi trạng thái ấy, có hai hướng:

1. **Tải entity managed rồi áp dụng những thay đổi được cho phép.** Hướng này minh bạch, đặc biệt với HTTP request/DTO.
2. **Dùng `merge(detached)`.** Hibernate sao chép state của object detached vào managed instance; có thể tải instance đã tồn tại và thực hiện cascade MERGE theo mapping.

Ví dụ:

```java
Book detached = em.find(Book.class, 42L);
em.detach(detached);

detached.rename("Tiêu đề do client nhập");

Book managed = em.merge(detached);

System.out.println(em.contains(detached)); // false
System.out.println(em.contains(managed));  // true

// detached và managed có thể là hai object khác nhau.
// Chỉ managed được dirty-check trong PC hiện tại.
```

Hành vi quan trọng của `merge()`:

- Không làm object detached trở thành managed trong cùng chỗ tham chiếu.
- Trả về một managed object (có thể là object đã tồn tại trong PC).
- Có thể phải SELECT để nạp trạng thái/canonical managed instance trước khi sao chép dữ liệu.
- Có thể cascade tới association có `CascadeType.MERGE` hoặc ALL.
- Dùng phiên bản/ID/mapping để xác định trạng thái; không phải lệnh “upsert” vô điều kiện.
- Nếu dữ liệu detached stale so với DB, có thể phát sinh optimistic lock exception hoặc conflict khi flush/commit.

### 12.1. Lỗi khi bỏ qua giá trị trả về của merge

Mẫu không tốt:

```java
em.merge(detached);
detached.rename("Tên được sửa tiếp sau merge");
// Thay đổi sau đó trên detached không tự được theo dõi.
```

Mẫu hợp lý hơn nếu bắt buộc dùng merge:

```java
Book managed = em.merge(detached);
managed.rename("Tên sau khi merge");
```

Đừng nhầm `merge()` với `persist()`. `persist()` phù hợp với entity mới; cố `persist()` một detached entity đã có identifier có thể gây lỗi lifecycle/duplicate row, tùy mapping/generator và provider.

### 12.2. Dữ liệu detached không phải patch an toàn

Giả sử client gửi JSON:

```json
{
  "id": 42,
  "title": "Tiêu đề mới"
}
```

Nếu ánh xạ trực tiếp thành `Book` detached với các field khác mặc định `null` rồi gọi `merge()`, application có thể vô tình sao chép cả những field **không được gửi** hoặc **không được phép sửa** vào managed entity. Điều này gây rủi ro mất dữ liệu hoặc overposting.

Hướng rõ ràng hơn:

```java
public record RenameBookCommand(Long bookId, String newTitle) {}
```

```java
@Transactional
public void renameBook(RenameBookCommand command) {
    Book managed = em.find(Book.class, command.bookId());
    if (managed == null) {
        throw new IllegalArgumentException("Không tìm thấy sách");
    }

    // Kiểm tra authorization/version và business invariant.
    managed.rename(command.newTitle());
    // Hibernate ghi UPDATE khi flush trong transaction.
}
```

Đối với update có mục đích, dùng command/DTO giúp xác định chính xác trường được thay và xử lý quyền. Detached entity phù hợp trong một số workflow có kiểm soát, nhưng không nên biến `merge()` thành điểm vào duy nhất cho mọi payload API.

## 13. Detached entity, optimistic locking và dữ liệu stale

Một detached object thường giữ các giá trị cũ:

```text
T0: Session A tải Book #42, version=3
T1: Session A đóng / detach → Book A detached, version=3
T2: Session B sửa Book #42, commit → version=4
T3: Client sửa Book A trong Java, vẫn version=3
T4: Session C cố merge Book A
            ↓
        Có nguy cơ optimistic locking conflict
```

Với `@Version`, Hibernate có thể phát hiện việc update state dựa trên phiên bản cũ và ném lỗi khi merge/flush/commit. Thời điểm chính xác tùy Hibernate version, mapping và tình trạng database.

Ví dụ:

```java
@Version
private Long version;
```

Lệnh SQL update do ORM tạo thường có điều kiện phiên bản:

```sql
UPDATE books
SET title = :new_title,
    version = :new_version
WHERE id = :book_id
  AND version = :old_version;
```

Nếu không có hàng phù hợp, Hibernate báo xung đột theo optimistic locking. Entity ID xác định hàng, version xác định kỳ vọng về phiên bản đã đọc. `detach()` tự nó không tạo snapshot an toàn trước thay đổi từ các transaction khác.

### 13.1. Đừng tự động bỏ qua xung đột

Không nên xử lý optimistic lock exception bằng cách âm thầm tải entity mới nhất rồi ghi đè mọi field từ detached object; cách này tạo **last writer wins** có thể làm mất cập nhật của người khác. Tùy domain, hướng giải quyết là trả conflict để client tải lại, thực hiện merge từng field theo quy tắc cụ thể hoặc chạy lại command nếu operation idempotent.

Nếu dùng phiên bản trong DTO, client có thể gửi expectedVersion để service so sánh. Nhưng kiểm tra Java đơn thuần vẫn cần cơ chế đồng bộ DB (optimistic update, lock hoặc conditional SQL) để tránh race giữa check và commit.

## 14. detach và clear trong batch processing

Một ứng dụng đọc hoặc ghi hàng trăm nghìn entity trong cùng session có thể để persistence context tăng rất lớn:

```text
Session bắt đầu
   ↓
Đọc/ghi 1.000 entity → PC giữ ~1.000 managed instances
   ↓
Đọc/ghi 10.000 entity → PC giữ ~10.000 managed instances
   ↓
Đọc/ghi 100.000 entity → memory/dirty checking/GC tăng
```

Với batch, `flush()` và `clear()` sau từng chunk giúp giới hạn số entity managed trong PC:

```java
import org.hibernate.Session;
import org.hibernate.Transaction;

public void importBooks(SessionFactory factory, List<BookDraft> drafts) {
    final int batchSize = 50;

    try (Session session = factory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            for (int i = 0; i < drafts.size(); i++) {
                BookDraft draft = drafts.get(i);
                Book book = new Book(draft.isbn(), draft.title());
                session.persist(book);

                if ((i + 1) % batchSize == 0) {
                    session.flush();
                    session.clear();
                }
            }

            session.flush(); // Nốt các phần tử ở chunk cuối.
            session.clear();
            tx.commit();
        } catch (RuntimeException | Error error) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
            }
            throw error;
        }
    }
}

public record BookDraft(String isbn, String title) {}
```

Trong ví dụ trên, `SessionFactory`, `List` và các import Hibernate/Jakarta cần có trong project, `BookDraft` được đặt trong file Java riêng nếu là kiểu public. Với `GenerationType.IDENTITY`, Hibernate có thể INSERT sớm để lấy ID và hạn chế JDBC insert batching; chiến lược sequence/generator thích hợp có thể cải thiện throughput. `flush/clear` giúp giới hạn kích thước PC, **không bảo đảm** database batching theo đúng 50 câu lệnh.

### 14.1. Một transaction lớn vẫn là một transaction lớn

Ví dụ `importBooks()` commit **một lần cuối cùng**, dù đã flush/clear nhiều lần. Vì vậy:

- Mọi SQL trước commit vẫn có thể bị rollback.
- Database có thể phải giữ lock, undo/redo log và tài nguyên transaction trong thời gian dài.
- Clear giúp giảm state trong Hibernate nhưng không giải phóng chi phí transaction ở database.
- Nếu cần retry từng chunk độc lập, phải chia thành **nhiều transaction** có checkpoint/idempotency riêng.

Nếu import chấp nhận thành công một phần, một transaction cho từng chunk thường khả thi. Nếu mọi phần tử phải nguyên tử cùng nhau, cần cân nhắc giới hạn kích thước lô hoặc thiết kế staging/import transaction phù hợp.

### 14.2. detach từng entity trong vòng lặp đọc

Khi cần đọc từng entity rồi xuất dữ liệu mà không cần tracking:

```java
for (Long id : ids) {
    Book book = session.get(Book.class, id);
    if (book != null) {
        writeSummary(book.getId(), book.getTitle());
        session.evict(book);
    }
}
```

Ví dụ này giới hạn managed instances đã đọc, nhưng vẫn có **N query** nếu duyệt từng ID, và dùng `ids` lớn trong memory cũng gây chi phí. Đối với export nhiều dòng, nên dùng projection có phân trang hoặc streaming/scrolling phù hợp, đóng cursor/resource và đặt transaction boundary rõ.

Nếu chỉ cần scalar values như `id` và `title`, constructor projection thường tránh được việc tạo managed entity ngay từ đầu; khi ấy không cần `detach()` cho từng hàng.

### 14.3. clear không nhất thiết làm heap giảm ngay

`em.clear()` làm Hibernate bỏ các reference/tracking trong PC, nhưng nếu code giữ `List<Book> allBooks`, mọi Book vẫn có reference từ list. Garbage collector không thể thu hồi chúng chỉ vì đã clear PC. Muốn kiểm soát memory, cần tránh giữ cả lô trong cấu trúc khác, xử lý từng chunk và giải phóng reference khi không cần.

## 15. Mối quan hệ giữa clear, first-level cache và SQL truy vấn

Giả sử:

```java
Book b1 = em.find(Book.class, 42L);
Book b2 = em.find(Book.class, 42L);
// Với cùng PC, b1 == b2.

em.clear();

Book b3 = em.find(Book.class, 42L);
// Không còn identity map entry cũ, nên b3 là instance mới.
```

Việc `clear()` buộc PC bỏ identity entries cũ, nhưng **không bảo đảm** mỗi lần `find()` tiếp theo phải đi qua network đến database: Hibernate còn có second-level cache nếu đã bật và cache entry hợp lệ. Vì thế không nên dùng `em.clear()` như cam kết “chắc chắn đọc trực tiếp giá trị mới nhất trên DB”.

### 15.1. Muốn thấy dữ liệu mới thì làm thế nào?

Nếu một entity đang managed và cần cập nhật state từ database, Jakarta Persistence có `em.refresh(entity)`. Nó yêu cầu entity ở trạng thái managed phù hợp, và chịu ảnh hưởng transaction/isolation/locking. Khi một entity đã detached, phải nạp managed instance trở lại hoặc merge theo semantics tương ứng; không mặc định gọi `refresh(detached)` là hợp lệ.

```java
Book managed = em.find(Book.class, 42L);
em.refresh(managed); // Reload theo provider/transaction context.
```

Trong giao dịch có snapshot isolation hoặc repeatable-read, việc refresh có nhìn thấy commit từ transaction khác hay không còn phụ thuộc cơ chế isolation. Không dùng clear/refresh để vượt qua quy tắc nhất quán của database.

### 15.2. Clear sau native SQL hoặc bulk DML

JPQL bulk update, bulk delete hoặc native SQL có thể thay database mà không đồng bộ các entity đã tải trong PC:

```java
Book old = em.find(Book.class, 42L);

em.createQuery(
        "update Book b set b.title = :title where b.id = :id")
        .setParameter("title", "Cập nhật hàng loạt")
        .setParameter("id", 42L)
        .executeUpdate();

// old có thể vẫn chứa title cũ trong memory.
em.clear();

Book current = em.find(Book.class, 42L);
```

Sau bulk DML, clear rồi load lại là một hướng xử lý khi cần đồng bộ PC. Nhưng trước `clear()` phải bảo đảm **những thay đổi managed hợp lệ khác đã được flush**, hoặc tách bulk DML sang một transaction/session riêng để tránh bỏ mất việc chưa lưu.

Bulk DML có các hệ quả thêm: không chạy entity lifecycle callbacks/dirty checking từng entity như đường thông thường, và `@Version` có thể không được cập nhật theo kỳ vọng nếu không thiết kế query phù hợp. Ranh giới của `clear()` chỉ giải quyết trạng thái trong PC, không tự xử lý mọi vấn đề cache cấp hai, version và concurrency.

## 16. Transaction rollback có giống clear không?

Không. Một transaction có thể rollback khi các thay đổi đã được flush:

```text
BEGIN
  ├── managed Book đổi title từ A thành B
  ├── flush → DB row trong transaction tạm có title B
  ├── ROLLBACK → DB quay lại A
  └── Java Book object có thể vẫn giữ title B trong memory
```

`clear()` chỉ ngừng tracking; nó không hoàn tác transaction database. `rollback()` hoàn tác SQL chưa commit; nó không tự đặt mọi Java field trở lại giá trị trước khi sửa. Sau lỗi trong Hibernate transaction, nên rollback, đóng/bỏ session bị lỗi theo lifecycle và sử dụng session mới để tải trạng thái đúng.

Một mẫu xử lý thông thường với Hibernate native:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Book book = session.get(Book.class, bookId);
        if (book == null) {
            throw new IllegalArgumentException("Không tìm thấy sách");
        }

        book.rename("Tên mới");
        tx.commit();
    } catch (RuntimeException | Error failure) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    }
}
```

Không thêm `session.clear()` trong `catch` với kỳ vọng thay rollback. Với Spring/JTA, rollback và đóng session thường do transaction manager/framework thực hiện; code nghiệp vụ cần phát exception phù hợp để framework xử lý.

## 17. close(): chấm dứt quản lý bằng cách kết thúc vòng đời session

`detach()` bỏ một entity; `clear()` bỏ tất cả các entity khỏi PC; `close()` kết thúc khả năng sử dụng session/entity manager theo lifecycle của nó.

Ví dụ Java SE tự quản lý Hibernate Session:

```java
Book detached;

try (Session session = sessionFactory.openSession()) {
    detached = session.get(Book.class, 42L);
    // Dữ liệu cơ bản đã load.
}

// Session đã đóng. detached không còn managed bởi Session cũ.
String title = detached.getTitle();
```

Chỉ đọc những field đã khởi tạo một cách độc lập được. Nếu sau khi session đóng code truy cập association lazy chưa load, có thể phát sinh `LazyInitializationException`.

### 17.1. EntityManager tự tạo

```java
EntityManager em = entityManagerFactory.createEntityManager();
try {
    // Thao tác trong transaction được quản lý phù hợp.
} finally {
    em.close();
}
```

Ứng dụng tạo EntityManager thì thường chịu trách nhiệm đóng nó. Nếu ứng dụng tự tạo `EntityManagerFactory`, factory có lifecycle dài hơn và cần đóng riêng ở shutdown. Đóng một EntityManager không đồng nghĩa đóng factory/pool.

### 17.2. EntityManager do container hoặc Spring quản lý

Với:

```java
@PersistenceContext
private EntityManager em;
```

trong một service Spring, reference thường là proxy tới EntityManager do framework quản lý. **Không gọi `em.close()` trong business method** để “detach” hoặc “tiết kiệm tài nguyên”. Nó vi phạm ownership/lifecycle của framework và có thể làm hỏng transaction đang chạy.

Nếu chỉ cần một read model độc lập, hãy query DTO. Nếu cần giải phóng persistence context khi xử lý batch đặc biệt, việc dùng `clear()` cũng có tác động trên toàn PC đang tham gia transaction, nên chỉ thực hiện tại ranh giới được kiểm soát, không trong helper chung có thể xóa state của các thành phần khác.

## 18. Tại sao detach không phải cách thiết kế API response mặc định?

Một cách dễ mắc lỗi là:

```java
@Transactional(readOnly = true)
public Book getBook(Long id) {
    Book book = em.find(Book.class, id);
    em.detach(book);
    return book;
}
```

Sau khi trả Book, tầng JSON serializer có thể cần `book.getPublisher().getName()` hoặc `book.getReviews()`. Nếu association lazy chưa load, nó không còn session để truy cập. Ngoài ra, trả entity trực tiếp có thể làm lộ field nhạy cảm hoặc coupling API với schema ORM.

Thay bằng read-model:

```java
public record BookDetailsResponse(
        Long id, String title, String isbn) {}
```

```java
@Transactional(readOnly = true)
public BookDetailsResponse getBookDetails(Long id) {
    return em.createQuery(
            "select new com.example.api.BookDetailsResponse(" +
            "  b.id, b.title, b.isbn" +
            ") from Book b where b.id = :id",
            BookDetailsResponse.class)
            .setParameter("id", id)
            .getResultStream()
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Không tìm thấy sách"));
}
```

Giả định `BookDetailsResponse` được đặt tại package `com.example.api`; với `select new ...`, package và constructor phải khớp. Projection chứa scalar values, không phải managed entity; không phải gọi `detach()`. API không còn phụ thuộc vào thời điểm session đóng hay proxy chưa khởi tạo của entity.

## 19. Khi nào nên dùng detach cụ thể?

`detach()` hữu ích khi:

- Ứng dụng muốn ngừng dirty checking một **entity cụ thể** nhưng vẫn giữ những managed entities khác trong cùng session.
- Một workflow chuyên biệt đọc và chuyển một object đã khởi tạo thành snapshot không cần quản lý nữa.
- Batch processing cần giảm dần số managed instances nhưng vẫn giữ PC hiện tại cho những entity khác.
- Code đang dùng Hibernate Session/EntityManager dài hơn một unit of work (cần cân nhắc lại thiết kế) và muốn chủ động giải phóng vài entity khỏi identity map.

Tuy vậy, nếu chỉ cần query dữ liệu đọc cho màn hình hoặc report, projection thường hợp hơn. Nếu muốn ngăn cập nhật entity nhưng vẫn cần lazy loading trong session, read-only hint có thể phù hợp hơn. Nếu cần loại bỏ **toàn bộ** state tracking giữa các chunk, `clear()` rõ ràng và ít thao tác hơn detach từng entity.

## 20. Khi nào nên dùng clear cụ thể?

`clear()` thường được dùng khi:

- Batch import/update lớn đã `flush()` các thay đổi của chunk và cần giới hạn kích thước PC.
- Sau bulk DML/native SQL, PC có state stale và application chủ động muốn bỏ toàn bộ managed objects trước khi query lại.
- Muốn bỏ một đơn vị dữ liệu đọc lớn để tránh giữ snapshot/tracking không cần thiết, trong khi session vẫn open.
- Một ranh giới xử lý đặc biệt cần bảo đảm lần `find()` tiếp theo không tái sử dụng managed instance cũ của PC.

Không nên gọi `clear()` tùy tiện trong một repository method nhỏ được sử dụng bên trong transaction của service khác. Ví dụ:

```java
@Transactional
public void updateOrderAndBook() {
    Order order = em.find(Order.class, orderId);
    order.changeStatus("PAID"); // pending

    bookRepository.someUtilityCallingClear();

    // order không còn managed: thay đổi status có thể chưa được flush.
}
```

Helper đó có thể vô tình chấm dứt quản lý của **tất cả entity** mà caller đang sử dụng. Quyết định clear phải thuộc tầng nắm toàn bộ transaction/persistence context boundary, không bị giấu như một chi tiết triển khai trong hàm tiện ích.

## 21. Một số lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Đổi title sau detach nhưng DB không đổi | Entity detached không còn dirty checking | Tải managed entity rồi sửa, hoặc merge đúng |
| Sửa rồi clear nhưng mất update | Thay đổi chưa flush đã bị bỏ khỏi PC | Flush trước clear nếu muốn giữ, sau đó commit |
| Gọi clear để hủy giao dịch | Clear không rollback SQL đã flush | Dùng rollback transaction |
| Gọi detach rồi vẫn thấy publisher được update | Publisher có thể vẫn managed; không cascade detach | Hiểu phạm vi và `CascadeType.DETACH` |
| `LazyInitializationException` sau detach | Proxy/collection chưa khởi tạo | Query đúng dữ liệu trước khi rời PC; ưu tiên DTO |
| Dùng merge nhưng sửa tiếp object cũ | `merge()` trả managed instance khác | Tiếp tục trên object được trả về |
| Merge request chỉ có title làm null field khác | Detached graph thiếu field nhưng merge sao chép state | Dùng command DTO và update managed entity |
| `em.contains(entity)` false dù ID hợp lệ | ID không quyết định membership của PC | Hiểu detached vs managed; tải lại trong PC |
| Query sau clear vẫn nhận dữ liệu cache | Clear không evict second-level cache | Chính sách cache/refresh/transaction isolation |
| Memory không giảm sau clear | Application vẫn giữ danh sách references lớn | Xử lý theo chunk, bỏ reference ở code khác |
| Dùng clear trong helper gây mất thay đổi của caller | Clear toàn PC, không chỉ một entity | Kiểm soát boundary ở application service |
| Gọi `em.remove(detached)` bị lỗi | Remove cần managed entity phù hợp | Load managed instance rồi remove |
| `persist(detached)` gây lỗi duplicate | Persist dành cho entity mới | Tách logic tạo mới và cập nhật, dùng managed entity |
| Bị mất update do dữ liệu stale qua nhiều request | Detached state cũ, không kiểm soát version | `@Version`, expectedVersion và xử lý conflict |
| SQL đã chạy trước clear dù chưa commit | Hibernate flush sớm khi query/generator yêu cầu | Phân biệt flush và commit |
| Đóng EntityManager trong Spring service | Framework sở hữu resource | Để transaction manager/context đóng |
| Clear trong batch nhưng DB vẫn giữ lock lâu | Vẫn một transaction lớn | Phân chunk thành nhiều transaction nếu semantics cho phép |

## 22. Một luồng ví dụ đầy đủ: đọc, detach, thay đổi và cập nhật lại

Giả sử cần thực hiện workflow qua hai lần giao tiếp người dùng. Lần đầu đọc sách để hiển thị:

```java
public record BookEditView(
        Long id, String title, Long version) {}
```

```java
@Transactional(readOnly = true)
public BookEditView loadBookForEditing(Long id) {
    Book book = em.find(Book.class, id);
    if (book == null) {
        throw new IllegalArgumentException("Không tìm thấy sách");
    }
    return new BookEditView(
            book.getId(), book.getTitle(), book.getVersion());
}
```

API trả DTO đã tách khỏi PC; không cần giữ entity detached trong server giữa các request.

Khi người dùng gửi lệnh đổi tiêu đề:

```java
public record UpdateBookTitle(
        Long id, String title, Long expectedVersion) {}
```

```java
@Transactional
public void updateBookTitle(UpdateBookTitle command) {
    Book managed = em.find(Book.class, command.id());
    if (managed == null) {
        throw new IllegalArgumentException("Không tìm thấy sách");
    }

    if (!Objects.equals(
            managed.getVersion(), command.expectedVersion())) {
        throw new IllegalStateException(
                "Sách đã được cập nhật; cần tải lại");
    }

    // Kiểm tra quyền cập nhật và invariant nghiệp vụ.
    managed.rename(command.title());
    // Hibernate flush/commit và @Version bảo vệ thêm
    // khỏi xung đột phát sinh sau khi đọc version.
}
```

Đoạn code giả định import `java.util.Objects` và `@Transactional` của Spring. Kiểm tra expectedVersion ở Java mang lại phản hồi sớm khi client stale, còn optimistic locking của ORM/database bảo vệ race xảy ra giữa lúc check và commit. Đây là cách xử lý cập nhật qua nhiều request rõ ràng hơn việc giữ một detached entity dài hạn rồi merge toàn bộ state.

Nếu hệ thống thực sự cần xử lý detached entity đã được serialize giữa hai transaction, cần kiểm tra tính toàn vẹn của dữ liệu, authorizations, ID, version và những field được phép thay đổi trước khi merge. Chỉ vì object có ID và `@Entity` không có nghĩa dữ liệu client gửi đáng tin cậy.

## 23. Mẫu batch an toàn với nhiều transaction riêng

Một cách khác để giới hạn cả PC và transaction là xử lý từng chunk trong session riêng. Điều này phù hợp nếu nghiệp vụ **chấp nhận kết quả thành công một phần** và có cơ chế retry.

```java
public void importInChunks(
        SessionFactory factory,
        List<BookDraft> drafts,
        int chunkSize) {
    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize phải dương");
    }

    for (int from = 0; from < drafts.size(); from += chunkSize) {
        int to = Math.min(drafts.size(), from + chunkSize);

        try (Session session = factory.openSession()) {
            Transaction tx = session.beginTransaction();
            try {
                for (int i = from; i < to; i++) {
                    BookDraft draft = drafts.get(i);
                    session.persist(
                            new Book(draft.isbn(), draft.title()));
                }
                tx.commit();
            } catch (RuntimeException | Error ex) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackEx) {
                        ex.addSuppressed(rollbackEx);
                    }
                }
                throw ex;
            }
        }
    }
}
```

Mỗi chunk có PC và transaction riêng; đóng Session kết thúc vòng đời managed objects của chunk mà không cần gọi `clear()` thủ công. Bù lại, nếu chunk thứ 10 lỗi thì chín chunk trước đã commit. Cần lưu checkpoint, deduplication key, audit và kế hoạch retry. Chọn giữa một transaction lớn dùng flush/clear và nhiều transaction nhỏ theo tính nguyên tử mà domain yêu cầu, không chỉ theo tốc độ.

## 24. Những câu hỏi tự kiểm tra khi sử dụng detach/clear

**Câu hỏi 1:** Đã tải `Book`, gọi `em.detach(book)` rồi sửa `book.title` trong cùng transaction. Hibernate có tự update không?

**Trả lời:** Không thông qua dirty checking của PC cũ; Book đã detached. Nếu muốn lưu thay đổi, cần managed entity và thao tác phù hợp. Phải phân biệt với các SQL đã thực thi **trước thời điểm detach**.

**Câu hỏi 2:** Gọi `em.clear()` khi `Order`, `Book` và `Publisher` đều managed. Entity nào còn managed?

**Trả lời:** Không entity nào trong số đó còn managed trong PC vừa bị clear. Các Java references vẫn có thể tồn tại, nhưng mọi object cũ đã rời PC.

**Câu hỏi 3:** Gọi `em.flush(); em.clear(); tx.rollback();`. Các SQL UPDATE đã flush có được commit không?

**Trả lời:** Không. Flush thực thi SQL trong transaction, rollback hoàn tác chúng. Clear không quyết định commit hay rollback.

**Câu hỏi 4:** Detach một `Order` có đồng thời detach mọi `OrderLine` không?

**Trả lời:** Không nhất thiết. Phải xét cascade DETACH và tình trạng quản lý của các target entity. Với `clear()`, tất cả managed entities trong PC đều rời quản lý.

**Câu hỏi 5:** Sau `em.clear()`, câu `em.find(Book.class, id)` tiếp theo chắc chắn query database không?

**Trả lời:** Không chắc chắn. PC không còn entry cũ, nhưng Hibernate có thể dùng second-level cache nếu bật; database transaction isolation cũng quyết định độ mới của dữ liệu.

**Câu hỏi 6:** Với một API chỉ cần `id` và `title`, nên tải Book rồi detach hay dùng DTO?

**Trả lời:** Thường dùng DTO/constructor projection. Không cần tạo managed entity chỉ để lập tức đưa nó ra khỏi PC, và tránh cả rủi ro lazy association.

**Câu hỏi 7:** Sau khi `Book managed = em.merge(detached)`, sửa tiếp trên detached có được flush không?

**Trả lời:** Không. Object detached ban đầu vẫn detached; thay đổi phải thực hiện trên managed instance hoặc trong một transaction được thiết kế rõ ràng.

## 25. Sơ đồ quyết định ngắn gọn

```text
                 Đang xử lý một entity/collection trong Hibernate
                                    │
                   Có cần tiếp tục theo dõi thay đổi không?
                           ┌────────┴────────┐
                          CÓ                KHÔNG
                           │                  │
                           ▼                  ▼
                   Giữ entity managed   Có muốn bỏ quản lý
                   trong PC             đúng một entity?
                                             │
                                     ┌───────┴───────┐
                                    CÓ              KHÔNG
                                     │                │
                                     ▼                ▼
                            detach()/evict()     Muốn bỏ toàn PC?
                                                      │
                                              ┌───────┴───────┐
                                             CÓ              KHÔNG
                                              │                │
                                              ▼                ▼
                                            clear()        DTO/read-only
                                              │            hoặc giữ PC
                                              ▼
                       Có thay đổi chưa flush cần lưu không?
                                │
                             CÓ │
                                ▼
                     Flush trước khi clear/detach
                     rồi commit theo transaction

Sau detached:
  ├── cần đọc field đã load → đọc Java object như snapshot
  ├── cần lazy field chưa load → query/lấy dữ liệu khi còn PC
  ├── cần ghi theo command → tải managed entity và áp dụng thay đổi
  └── cần hợp nhất detached state → merge(), dùng instance trả về
```

**Kết luận:** `detach()` chấm dứt quản lý đối với một entity, `clear()` chấm dứt quản lý với toàn bộ entity trong persistence context, và `close()` kết thúc vòng đời của Session/EntityManager do ứng dụng sở hữu. Các thao tác ấy không tương đương `flush()`, `commit()`, `rollback()` hay `remove()`. Khi hiểu rõ ranh giới giữa **Java object còn tồn tại** và **Hibernate còn theo dõi object**, bạn sẽ tránh mất thay đổi chưa flush, xử lý đúng detached graph/lazy loading, kiểm soát xung đột qua `@Version` và giới hạn bộ nhớ khi xử lý dữ liệu lớn.
