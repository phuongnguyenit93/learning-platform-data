# Ảnh hưởng của truy vấn đến thời điểm đồng bộ

Trong JPA, khi chúng ta thay đổi một entity đang được quản lý (*managed entity*), câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` tương ứng không nhất thiết được gửi đến database ngay lập tức. Provider có thể giữ các thay đổi trong **persistence context** và đồng bộ chúng khi thích hợp bằng thao tác **flush**.

Điều dễ gây bất ngờ là: **một truy vấn đọc cũng có thể làm thời điểm flush đến sớm hơn dự kiến**.

Ví dụ, trong cùng một transaction:

```java
Book book = em.find(Book.class, 42L);
book.rename("JPA nâng cao");

long total = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.title = :title",
    Long.class
).setParameter("title", "JPA nâng cao")
 .getSingleResult();
```

Lệnh `book.rename(...)` chỉ sửa Java object. Nhưng khi query đếm sách được thực thi, JPA phải xét liệu thay đổi tên đang chờ có ảnh hưởng đến kết quả hay không. Với flush mode mặc định `AUTO` và một persistence context đã tham gia transaction, provider phải bảo đảm các thay đổi liên quan được phản ánh trong việc xử lý query. Một cách thường dùng là **flush trước khi chạy SELECT**.

Vì vậy, “đọc dữ liệu” không nhất thiết là thao tác không có tác động lên luồng SQL. Một câu `SELECT` có thể đứng sau các câu `UPDATE` phát sinh từ những thay đổi đã thực hiện trước đó trong cùng transaction.

Bài học **“Ảnh hưởng của truy vấn đến thời điểm đồng bộ”** thuộc chương **Đồng bộ và flush** của chủ đề **Data Persistence Relational Access ORM JPA**. Chúng ta sẽ phân biệt flush và commit, tìm hiểu khi nào query có thể kích hoạt flush, các chế độ `AUTO`/`COMMIT`, tác động của JPQL/Criteria/native SQL, tính nhất quán dữ liệu, lỗi thường gặp và cách kiểm tra SQL thực tế.

Các ví dụ sử dụng `jakarta.persistence`. Dự án dùng JPA phiên bản cũ có thể sử dụng package `javax.persistence` tương ứng.

## 1. Vì sao JPA không gửi SQL ngay sau mọi setter?

Với JDBC thuần, ứng dụng thường gọi `PreparedStatement.executeUpdate()` khi muốn cập nhật database. Với JPA, ứng dụng tương tác trước hết với các **entity được quản lý**:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên sách mới");
```

Không có lệnh `em.update(book)` trong API `EntityManager` chuẩn. Provider theo dõi thay đổi persistent state của entity managed (thường gọi là **dirty checking**), và tại một thời điểm đồng bộ, nó quyết định những SQL nào cần gửi xuống database.

Sơ đồ:

```text
Entity được tải và quản lý
           │
           ▼
book.rename("Tên mới")
           │
           ▼
State trong persistence context đổi
           │
           │ Chưa nhất thiết có SQL
           ▼
Có yêu cầu đồng bộ (flush)
           │
           ▼
Provider tạo/thực thi SQL tương ứng
           │
           ▼
Database nhận thay đổi trong transaction
           │
           ▼
commit thành công mới xác nhận transaction
```

Việc trì hoãn có những lợi ích: provider có thể gom nhiều thay đổi, sắp thứ tự thao tác để phù hợp khóa ngoại, batch SQL và tránh phát lệnh ngay sau mỗi setter. Nhưng đổi lại, lập trình viên phải hiểu **thời điểm nào hệ thống buộc phải đồng bộ**.

Một trong những thời điểm quan trọng đó là **khi thực thi query**.

## 2. Phân biệt thay đổi trong bộ nhớ, flush và commit

Trước khi xét truy vấn, cần tách ba khái niệm thường bị coi là một.

### 2.1. Thay đổi Java object

```java
book.rename("ORM chuyên sâu");
```

Nếu `book` đang managed, thay đổi này được ghi nhận trong trạng thái persistence context. Không thể chỉ từ lời gọi method mà kết luận có một câu `UPDATE` đã chạy.

### 2.2. Flush

```java
em.flush();
```

`flush()` đồng bộ các thay đổi cần thiết của persistence context xuống database theo ngữ nghĩa JPA trong phạm vi transaction phù hợp. Điều này có thể dẫn tới `INSERT`, `UPDATE`, `DELETE` hoặc thao tác liên quan đến collection.

Một flush thành công **không có nghĩa transaction đã commit**.

### 2.3. Commit

```java
em.getTransaction().commit();
```

Commit hoàn tất transaction thành công và xác nhận những thay đổi của nó trong database. Khi commit, provider thường phải đồng bộ các thay đổi pending cần thiết theo quy tắc persistence.

Bảng phân biệt:

| Sự kiện | State trong persistence context | SQL có thể đã chạy? | Database đã commit? |
| --- | --- | --- | --- |
| Gọi setter trên managed entity | Đã đổi | Chưa chắc | Chưa |
| Gọi `persist(newEntity)` | Entity trở thành managed | Có thể, tùy ID strategy | Chưa |
| Gọi query ở chế độ `AUTO` | Provider bảo đảm kết quả theo quy tắc AUTO | Có thể phát SQL trước query | Chưa, nếu transaction còn mở |
| Gọi `flush()` thành công | Thay đổi cần thiết được đồng bộ | Có | Chưa nếu chưa commit |
| Gọi `commit()` thành công | Transaction được hoàn tất | Các SQL cần thiết đã được xử lý | Có |
| Gọi `rollback()` | Object Java có thể vẫn giữ giá trị đã sửa | SQL có thể đã chạy trước đó | Không xác nhận thay đổi transaction |

**Flush không phải commit. Query-triggered flush cũng không phải commit.**

Điều này giải thích vì sao một lỗi ràng buộc SQL có thể xuất hiện trong lúc chạy query, mặc dù code chưa đi tới lệnh `commit()`.

## 3. Ví dụ entity và schema xuyên suốt

Ta dùng entity `Book` đơn giản:

```java
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

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Column(name = "category", nullable = false, length = 50)
    private String category;

    @Version
    private long version;

    protected Book() {}

    public Book(String title, String category) {
        rename(title);
        changeCategory(category);
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public String getCategory() { return category; }
    public long getVersion() { return version; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        this.title = newTitle.trim();
    }

    public void changeCategory(String newCategory) {
        if (newCategory == null || newCategory.isBlank()) {
            throw new IllegalArgumentException("category");
        }
        this.category = newCategory.trim();
    }
}
```

Schema minh họa:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    version BIGINT NOT NULL
);
```

Cú pháp sinh khóa và định nghĩa constraint thực tế phụ thuộc hệ quản trị database. Ở đây `@Version` giúp thấy thêm một hệ quả: khi provider flush cập nhật entity, SQL có thể mang điều kiện kiểm tra version để phát hiện cập nhật đồng thời.

Mọi ví dụ transaction dưới đây giả định dùng resource-local `EntityManager` trong môi trường minh họa:

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    em.getTransaction().begin();

    // Thao tác JPA.

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Trong Spring hoặc Jakarta EE, transaction có thể do framework/container quản lý. Khi đó không tự sao chép `getTransaction()` vào một container-managed `EntityManager`; chỉ thay phần quản lý transaction bằng cơ chế phù hợp.

## 4. Flush mode: bộ điều khiển quan trọng khi query chạy

JPA định nghĩa hai giá trị trong `FlushModeType`:

```java
FlushModeType.AUTO
FlushModeType.COMMIT
```

Có thể xem flush mode hiện tại:

```java
FlushModeType current = em.getFlushMode();
```

Và thay đổi bằng:

```java
em.setFlushMode(FlushModeType.AUTO);
```

Chế độ mặc định của persistence context thường là `AUTO` theo quy tắc JPA, trừ khi ứng dụng/framework cấu hình khác.

### `AUTO`: query phải thấy những thay đổi liên quan

Với `AUTO`, trong trường hợp persistence context đã tham gia một transaction, provider có trách nhiệm bảo đảm **những thay đổi của entity trong context có thể ảnh hưởng tới kết quả query sẽ được phản ánh trong quá trình xử lý query**.

Provider có thể thực hiện điều này bằng cách flush thay đổi xuống database, hoặc bằng cơ chế khác bảo đảm đúng kết quả. Đặc tả không yêu cầu mọi query ở AUTO phải phát một flush SQL đầy đủ một cách vô điều kiện.

Phân biệt:

- **Bảo đảm về kết quả:** query được xử lý đúng với thay đổi liên quan đã chờ đồng bộ.
- **Chiến lược thực hiện:** provider có thể flush hoặc dùng phương pháp khác.
- **Số lượng SQL:** không được đặc tả cố định.

### `COMMIT`: không bảo đảm query thấy mọi thay đổi pending

Với `COMMIT`, những thay đổi pending sẽ được đồng bộ khi transaction commit theo quy tắc persistence. **Ảnh hưởng của thay đổi trong persistence context tới các query thực hiện trước commit là không được đặc tả bảo đảm theo cách của AUTO.**

Ví dụ, ứng dụng tạo Book mới nhưng chưa flush, rồi chạy query `COUNT`. Ở COMMIT, không nên viết code nghiệp vụ giả định kết quả count chắc chắn tính cả hàng mới đó.

Điểm rất quan trọng:

> `COMMIT` không phải cam kết “provider tuyệt đối không bao giờ flush trước commit”. Nó chủ yếu thay đổi mức bảo đảm về việc pending changes ảnh hưởng tới kết quả query.

Provider có thể phải thực hiện SQL sớm vì chiến lược sinh khóa, thao tác đã gọi trước đó, constraint hoặc những lý do implementation khác. Vì thế, COMMIT không được sử dụng như một lời hứa rằng mọi câu SQL ghi đều trì hoãn tới dòng `commit()`.

### Bảng so sánh

| Tiêu chí | `AUTO` | `COMMIT` |
| --- | --- | --- |
| Ý định chính | Bảo đảm query được xử lý thấy thay đổi liên quan đã pending | Trì hoãn đồng bộ theo transaction, không bảo đảm mức nhìn thấy pending changes như AUTO |
| Query có thể kích hoạt flush? | Có | Không nên suy ra tuyệt đối có/không |
| Query có chắc nhìn thấy entity mới chưa flush? | Phải đáp ứng ngữ nghĩa AUTO nếu thay đổi ảnh hưởng kết quả và context đã tham gia transaction | Không có bảo đảm tương tự |
| Commit có đồng bộ thay đổi cần thiết? | Có | Có |
| `em.flush()` tường minh có tác dụng? | Có | Có |
| Là cách cấm mọi SQL ghi trước commit? | Không | Không |
| Có thay đổi isolation level DB không? | Không | Không |

Lựa chọn flush mode là quyết định về **ngữ nghĩa query và thời điểm đồng bộ**, không phải công tắc kiểm soát toàn bộ hành vi transaction.

## 5. Query tự động tạo nhu cầu flush như thế nào?

Giả sử trong database đang có `Book #42`:

```text
id=42, title="JPA cơ bản", category="JAVA"
```

Trong transaction:

```java
em.setFlushMode(FlushModeType.AUTO);

Book book = em.find(Book.class, 42L);
book.rename("JPA nâng cao");

List<Book> found = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :name",
    Book.class
).setParameter("name", "JPA nâng cao")
 .getResultList();
```

Tại thời điểm query chạy, trạng thái có hai lớp:

```text
Persistence context:
Book #42.title = "JPA nâng cao"

Database trước khi đồng bộ:
books.id=42, title = "JPA cơ bản"
```

Nếu provider chạy SQL `SELECT ... WHERE title = 'JPA nâng cao'` trực tiếp trên database chưa flush, bản ghi #42 có thể không xuất hiện. Điều đó trái với kết quả mà ngữ nghĩa AUTO yêu cầu trong trường hợp thay đổi liên quan.

Vì vậy, provider có thể flush:

```sql
UPDATE books
SET title = ?, version = ?
WHERE id = ? AND version = ?;
```

trước khi chạy:

```sql
SELECT ...
FROM books
WHERE title = ?;
```

Chuỗi SQL này chỉ là **một cách thực hiện thông dụng**, không phải thứ tự duy nhất được bảo đảm cho mọi provider/phiên bản. JPA yêu cầu tính đúng của việc xử lý query theo AUTO chứ không chuẩn hóa từng bước SQL nội bộ.

### Sơ đồ thời gian

```text
Ứng dụng                           Persistence context             Database
    │                                      │                         │
    │ find(Book, 42)                       │                         │
    ├─────────────────────────────────────►│──── SELECT ────────────►│
    │◄─────────────────────────────────────│◄─── row ────────────────│
    │                                      │                         │
    │ book.rename("JPA nâng cao")          │                         │
    ├─────────────────────────────────────►│ state changed           │
    │                                      │ (chưa chắc có UPDATE)    │
    │                                      │                         │
    │ execute JPQL query                   │                         │
    ├─────────────────────────────────────►│                         │
    │                                      ├── UPDATE nếu cần ──────►│
    │                                      ├── SELECT ──────────────►│
    │◄────────────────── kết quả ──────────│◄── rows ────────────────│
    │                                      │                         │
    │ commit                               │                         │
    ├──────────────────────────────────────────────────────────────►│
```

Điểm đáng nhớ là query đã đưa thời điểm đồng bộ tới **trước commit**.

## 6. Những thao tác nào mới thực sự “thực thi query”?

Đoạn sau chỉ tạo đối tượng truy vấn:

```java
TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b WHERE b.category = :category",
    Book.class
);
```

Bản thân việc gọi `createQuery(...)` không có nghĩa một câu SQL `SELECT` đã được gửi đi. Query thường thực sự được xử lý khi sử dụng terminal operation phù hợp, chẳng hạn:

```java
query.setParameter("category", "JAVA");
List<Book> results = query.getResultList();
```

Hoặc:

```java
Book book = em.createQuery(
    "SELECT b FROM Book b WHERE b.id = :id",
    Book.class
).setParameter("id", 42L)
 .getSingleResult();
```

Các thao tác thực thi query thường gặp:

| API | Vai trò | Flush có thể liên quan? |
| --- | --- | --- |
| `createQuery(...)` | Tạo/query parse đối tượng query | Không nên coi riêng lời gọi này là thực thi SELECT |
| `setParameter(...)` | Gán tham số | Không tự biểu thị query đã chạy |
| `getResultList()` | Lấy danh sách kết quả | Có, theo flush mode và tình huống |
| `getSingleResult()` | Lấy một kết quả | Có, theo flush mode và tình huống |
| `getResultStream()` | Lấy kết quả dưới dạng stream | Có; thời điểm truy vấn/tiêu thụ phụ thuộc implementation |
| `executeUpdate()` | Thực thi bulk UPDATE/DELETE | Có tác động SQL trực tiếp và cần xét đồng bộ context |
| `em.flush()` | Yêu cầu flush tường minh, không phải query | Có, theo API |

Không nên đặt lô code ở trước `getResultList()` rồi giả định “chưa commit nên DB chưa thể phát UPDATE”. Ở AUTO, việc thực thi truy vấn có thể là điểm provider cần làm việc đó.

## 7. Query tìm cùng entity khác query lọc theo thuộc tính

Xét hai cách đọc:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

// Cách 1: truy vấn lại entity theo khóa chính.
Book same = em.find(Book.class, 42L);
```

`find()` có thể dùng managed instance đã có trong persistence context, nên không nhất thiết cần SQL mới hoặc flush để “thấy” tên mới. Cả `book` và `same` đại diện cùng managed entity instance trong context.

Trong khi đó:

```java
List<Book> list = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
).setParameter("title", "Tên mới")
 .getResultList();
```

Query dựa trên một điều kiện lọc ở database. Nếu DB chưa có tên mới, nó có thể bỏ qua bản ghi. Vì vậy, việc query đúng theo AUTO có thể cần đồng bộ trước khi thực hiện điều kiện lọc.

Điểm phân biệt:

- **Đọc trực tiếp từ managed instance**: thấy state Java trong context.
- **Tìm bằng khóa chính đã managed**: có thể nhận cùng instance đã nằm trong context.
- **Thực thi query với predicate/order/aggregate**: database và provider phải bảo đảm kết quả phù hợp với flush mode.
- **Trả entity từ query**: JPA vẫn sử dụng identity map; nếu entity đã managed, query không tạo một managed instance thứ hai cho cùng persistent identity.

Không nên lấy hành vi của `find()` rồi suy diễn rằng mọi `SELECT` đều thấy dirty state mà không cần bất kỳ cơ chế đồng bộ nào.

## 8. Query đếm và thống kê cũng có thể kích hoạt flush

Lấy danh sách entity không phải kiểu truy vấn duy nhất có liên quan đến flush. Query aggregate có thể chịu ảnh hưởng trực tiếp của thay đổi pending.

Ví dụ:

```java
em.setFlushMode(FlushModeType.AUTO);

Book book = new Book("Hibernate", "JAVA");
em.persist(book);

Long numberOfJavaBooks = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = 'JAVA'",
    Long.class
).getSingleResult();
```

Nếu việc thêm `book` chưa có `INSERT` trong database và query count chỉ đọc DB, kết quả sẽ thiếu hàng mới. Ở AUTO với transaction đang tham gia, provider phải bảo đảm thay đổi liên quan được phản ánh trong việc xử lý query.

Vì vậy query:

```sql
SELECT COUNT(*)
FROM books
WHERE category = 'JAVA';
```

có thể được thực hiện sau khi provider flush các thay đổi cần thiết.

Tương tự, những query sau cũng cần xét ảnh hưởng của pending changes:

```java
SELECT SUM(p.amount) FROM Payment p
SELECT MAX(o.createdAt) FROM PurchaseOrder o
SELECT COUNT(DISTINCT s.id) FROM Student s JOIN s.courses c
SELECT b.category, COUNT(b) FROM Book b GROUP BY b.category
```

Nếu một entity mới, một trạng thái vừa đổi hoặc liên kết mới có thể ảnh hưởng tới `COUNT`, `SUM`, `JOIN` hay `GROUP BY`, provider phải xử lý tương thích với flush mode.

**Không nên dùng `COUNT` như một cách “chỉ đọc, chắc chắn không flush”.** Nó vẫn là query có thể phụ thuộc vào dữ liệu đang chờ đồng bộ.

## 9. Flush có phải xảy ra trước mọi truy vấn ở AUTO không?

Không. `AUTO` là một **bảo đảm về sự phù hợp của kết quả**, không phải một quy tắc rằng trước mỗi query provider phải flush toàn bộ context.

Giả sử persistence context có thay đổi một `Book`, nhưng query đọc bảng `Warehouse` hoàn toàn độc lập:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

List<Warehouse> warehouses = em.createQuery(
    "SELECT w FROM Warehouse w",
    Warehouse.class
).getResultList();
```

Nếu thay đổi Book không ảnh hưởng kết quả của query Warehouse, một provider có thể quyết định không cần flush pending update Book trước SELECT Warehouse.

Một số ORM phân tích các **query spaces/tables** được truy vấn và so sánh với những bảng có pending changes. Nếu không giao nhau, nó có thể bỏ qua flush ở thời điểm đó. Tuy nhiên, đây là **chiến lược tối ưu hóa của provider**, không phải một hợp đồng portable rằng query không trùng bảng sẽ luôn không flush.

Các lý do có thể khiến provider flush dù lập trình viên nghĩ không cần:

- Query phức tạp, có subquery hoặc join khó phân tích.
- Native SQL không được provider biết rõ những bảng bị ảnh hưởng.
- Mapping inheritance, secondary table, collection table hoặc join table.
- Chiến lược nội bộ của provider/phiên bản khác nhau.
- Có thao tác yêu cầu đồng bộ trước đó.
- Entity lifecycle hoặc cơ chế phát SQL có yêu cầu khác.

Ngược lại, nếu đang ở chế độ phù hợp, provider có thể bảo đảm kết quả mà không thực hiện chính xác chuỗi SQL ta dự đoán.

**Đừng xây logic nghiệp vụ dựa trên giả định “câu SELECT này không đụng bảng dirty nên chắc chắn chưa flush”.** Khi cần kiểm soát chính xác, phải dùng API/transaction/constraint phù hợp và kiểm tra provider cụ thể.

## 10. Những thay đổi đối với association cũng ảnh hưởng query

Không chỉ field scalar như `title` mới bị dirty. Association có thể thêm hoặc xóa dữ liệu trong join table hoặc thay đổi foreign key.

Giả sử có quan hệ:

```java
@Entity
public class Student {
    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    // Constructor, getter và domain methods phù hợp.
}
```

Trong transaction:

```java
Student student = em.find(Student.class, studentId);
Course course = em.find(Course.class, courseId);

student.enroll(course);

Long registered = em.createQuery(
    "SELECT COUNT(s) FROM Student s JOIN s.courses c " +
    "WHERE s.id = :sid AND c.id = :cid",
    Long.class
).setParameter("sid", studentId)
 .setParameter("cid", courseId)
 .getSingleResult();
```

Nếu phương thức `enroll()` cập nhật **owning side** của association, query kiểm tra liên kết có thể phụ thuộc vào một hàng mới trong bảng `student_courses` chưa được ghi xuống DB.

Khi chạy ở AUTO trong transaction đã tham gia, provider phải xử lý để kết quả truy vấn phản ánh những thay đổi liên quan theo semantics được bảo đảm.

Lưu ý: Nếu `enroll()` chỉ sửa inverse side của quan hệ hai hướng mà owning side không thay đổi, JPA không có nghĩa vụ coi đó là cập nhật liên kết cần ghi xuống join table. **Flush không sửa được lỗi thiết kế association**.

Tương tự:

- `@ManyToOne` đổi foreign key có thể ảnh hưởng query `JOIN` hoặc `WHERE` theo quan hệ.
- `@OneToMany` thêm/xóa entity con có thể ảnh hưởng `COUNT` hoặc `EXISTS`.
- `@ElementCollection` có thể ghi vào collection table.
- `@ManyToMany` thường liên quan tới join table.

Nghĩa là việc đánh giá “pending changes có ảnh hưởng query không?” phải xét toàn bộ mapping, chứ không chỉ bảng chính của entity.

## 11. Query-level flush mode: điều chỉnh cho một truy vấn

Không bắt buộc phải đổi flush mode của cả `EntityManager`. JPA cho phép đặt flush mode trên chính `Query`/`TypedQuery`:

```java
TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b WHERE b.category = :category",
    Book.class
);

query.setParameter("category", "JAVA");
query.setFlushMode(FlushModeType.COMMIT);

List<Book> books = query.getResultList();
```

Một query có thể có flush mode khác với mặc định của context.

Ví dụ:

```java
em.setFlushMode(FlushModeType.AUTO);

TypedQuery<Long> countQuery = em.createQuery(
    "SELECT COUNT(b) FROM Book b",
    Long.class
);
countQuery.setFlushMode(FlushModeType.COMMIT);
Long count = countQuery.getSingleResult();
```

Trong tình huống này, query dùng `COMMIT` theo thiết lập query. Không nên kỳ vọng query đếm chắc chắn phản ánh toàn bộ thay đổi trong context chưa được flush.

### Khi nào nên thay flush mode cho một query?

Có thể hữu ích trong một số trường hợp báo cáo, truy vấn phụ không cần thấy pending state hoặc cần tối ưu cách ORM đồng bộ. Nhưng phải đặt câu hỏi:

- Query có cần thấy entity/association vừa thay đổi trong transaction không?
- Kết quả query được dùng để quyết định nghiệp vụ quan trọng hay chỉ hiển thị tham khảo?
- Có phụ thuộc các invariant chưa được kiểm tra tại DB không?
- Có thao tác phát SQL sớm vì ID generation không?
- Kết quả có cần portable trên nhiều provider không?

Nếu query là một phần xác nhận “dữ liệu vừa tạo có tồn tại chưa?”, dùng `COMMIT` có thể làm kết quả khó dự đoán. Trong trường hợp cần ngữ nghĩa đọc-sau-ghi rõ ràng, `AUTO` cùng transaction hoặc `flush()` có chủ đích sẽ dễ hiểu hơn.

## 12. Ví dụ đối chiếu `AUTO` và `COMMIT`

Giả sử đang có 5 Book thuộc category `JAVA`.

### Trường hợp AUTO

```java
em.getTransaction().begin();
em.setFlushMode(FlushModeType.AUTO);

Book newBook = new Book("JPA", "JAVA");
em.persist(newBook);

Long total = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = :category",
    Long.class
).setParameter("category", "JAVA")
 .getSingleResult();

em.getTransaction().commit();
```

Với context đã tham gia transaction và không có các thay đổi khác, query đếm phải xử lý đúng việc Book mới có thể ảnh hưởng kết quả. Trong ví dụ cơ bản, ta mong kết quả bao gồm Book mới, tức số lượng chuyển từ 5 lên 6.

Provider có thể đã chạy `INSERT` sớm vì `IDENTITY` hoặc flush trước query. Đừng dùng con số SQL dự đoán để chứng minh flush xảy ra chính xác ở đâu; điều quan trọng là bảo đảm về kết quả theo AUTO.

### Trường hợp COMMIT

```java
em.getTransaction().begin();
em.setFlushMode(FlushModeType.COMMIT);

Book newBook = new Book("JPA", "JAVA");
em.persist(newBook);

Long total = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = :category",
    Long.class
).setParameter("category", "JAVA")
 .getSingleResult();

em.getTransaction().commit();
```

Ở COMMIT, tác động của các thay đổi trong context lên query trước commit không được đặc tả như AUTO. Trên một provider/chiến lược ID, `INSERT` có thể đã xảy ra, nên count có thể bao gồm Book. Với cấu hình khác, pending insert có thể chưa được xử lý theo cùng cách.

**Đừng viết assertion portable rằng COMMIT bắt buộc trả 5, cũng đừng viết assertion rằng nó luôn trả 6.**

Nếu nghiệp vụ yêu cầu chắc chắn dữ liệu đã được đưa xuống DB trước truy vấn, dùng flush tường minh trong transaction thích hợp:

```java
em.persist(newBook);
em.flush();

Long total = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = :category",
    Long.class
).setParameter("category", "JAVA")
 .getSingleResult();
```

Lúc này thay đổi đã được flush trước query. Nhưng kết quả vẫn chịu ảnh hưởng của transaction isolation, dữ liệu đồng thời và những điều kiện truy vấn khác.

## 13. `flush()` tường minh giúp gì trước truy vấn?

Có những trường hợp ứng dụng cần kiểm soát thời điểm đồng bộ, ví dụ:

- Muốn phát hiện vi phạm constraint trước khi thực hiện bước tiếp theo.
- Cần query/SQL có thể dựa vào thay đổi vừa ghi.
- Cần đồng bộ để lấy hiệu ứng do database tạo ra trước một bước sử dụng tiếp theo.
- Muốn giới hạn điểm SQL có thể thất bại trong quy trình nghiệp vụ dài.
- Cần phối hợp với query native hoặc logic database không được ORM tự phân tích đầy đủ.

Ví dụ:

```java
em.getTransaction().begin();

Book book = new Book("JPA nâng cao", "JAVA");
em.persist(book);

em.flush(); // Ranh giới đồng bộ có chủ đích.

Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = :category",
    Long.class
).setParameter("category", "JAVA")
 .getSingleResult();

em.getTransaction().commit();
```

Ở đây, code thể hiện rõ rằng trước khi chạy query, ứng dụng muốn flush pending changes.

### Lợi ích và chi phí

Flush tường minh giúp thời điểm SQL rõ ràng hơn nhưng có thể:

- Giảm cơ hội provider batch nhiều lệnh ghi.
- Phát hiện constraint/optimistic locking lỗi sớm hơn.
- Tạo thêm công việc nếu gọi quá thường xuyên.
- Khi transaction dài, làm DB nhận nhiều thay đổi chưa commit, kéo theo locking/transaction log.
- Không biến dữ liệu thành đã commit.
- Không làm các transaction khác mặc nhiên nhìn thấy dữ liệu chưa commit.

Đừng gọi `em.flush()` sau mọi setter như một thói quen. Chỉ gọi khi có yêu cầu về ngữ nghĩa hoặc vận hành rõ ràng.

## 14. Truy vấn native SQL: cần thận trọng hơn với kỳ vọng flush

JPA cho phép:

```java
Query query = em.createNativeQuery(
    "SELECT COUNT(*) FROM books WHERE category = ?"
);
query.setParameter(1, "JAVA");

Number count = (Number) query.getSingleResult();
```

Ở native query, provider có thể không thể phân tích đầy đủ mọi bảng, view, hàm, stored procedure hoặc tác động logic của câu SQL như nó phân tích JPQL trên entity model.

Hành vi flush cụ thể với native query phụ thuộc:

- Nhà cung cấp ORM (ví dụ Hibernate, EclipseLink).
- API được sử dụng (`EntityManager` chuẩn hoặc API riêng của provider).
- Flush mode và transaction hiện tại.
- Thông tin đồng bộ/query-space mà provider biết.
- Phiên bản provider và cấu hình.

Một số provider có thể chọn flush thận trọng hơn trước native query. Một số API mở rộng cho phép khai báo rõ các bảng/entity mà query phụ thuộc để tránh flush không cần thiết. Đó là **tính năng provider-specific**, không phải hợp đồng chung có thể sao chép sang mọi JPA implementation.

### Không được giả định native SQL luôn nhìn thấy pending object state

Nếu query native trực tiếp đọc một cột đã được sửa trong managed entity nhưng thay đổi chưa flush, database có thể chưa có giá trị mới. Trong một transaction và cấu hình AUTO, provider có nghĩa vụ theo đặc tả về query; cách đạt bảo đảm và các chi tiết native SQL có thể phụ thuộc loại query cùng implementation. Khi thao tác native phục vụ nghiệp vụ quan trọng, nên **kiểm soát flush tường minh và kiểm thử trên chính provider đang dùng** nếu cần bảo đảm kết quả sau ghi.

Ví dụ minh họa:

```java
Book book = em.find(Book.class, 42L);
book.changeCategory("DATABASE");

em.flush();

Number count = (Number) em.createNativeQuery(
    "SELECT COUNT(*) FROM books WHERE category = ?"
).setParameter(1, "DATABASE")
 .getSingleResult();
```

Ở đây, flush là chủ ý rõ ràng trước khi query SQL sử dụng thay đổi trong cùng transaction.

### Native query không nhất thiết là read-only

Một `createNativeQuery(...)` có thể thực thi SQL đặc biệt hoặc DML tùy API và database. Không nên coi nó “chỉ đọc” dựa trên tên method. Cần phân biệt query `SELECT` với native `UPDATE`/`DELETE`, và xem cơ chế đồng bộ persistence context sau khi bulk SQL thay đổi hàng.

## 15. Bulk UPDATE/DELETE làm tình hình phức tạp hơn

Một truy vấn bulk JPQL có thể thay đổi dữ liệu trực tiếp ở mức database:

```java
int updated = em.createQuery(
    "UPDATE Book b SET b.category = :newCategory " +
    "WHERE b.category = :oldCategory"
).setParameter("newCategory", "PROGRAMMING")
 .setParameter("oldCategory", "JAVA")
 .executeUpdate();
```

Đây là **bulk operation**, không tương đương việc load từng Book rồi gọi `changeCategory()`.

Hai vấn đề phải xử lý riêng:

1. **Trước khi bulk query chạy**, có pending changes nào trong context ảnh hưởng predicate/kết quả của bulk operation không? Phải xét flush mode, provider và yêu cầu đồng bộ.
2. **Sau khi bulk query chạy**, những managed Book instances đã tải có thể vẫn giữ state cũ, vì bulk DML không tự cập nhật mọi object trong persistence context.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
// book.category = "JAVA" lúc được tải.

em.createQuery(
    "UPDATE Book b SET b.category = :category WHERE b.id = :id"
).setParameter("category", "DATABASE")
 .setParameter("id", 42L)
 .executeUpdate();

// book có thể vẫn có category "JAVA" trong bộ nhớ.

em.getTransaction().commit();
```

Lần `em.find(Book.class, 42L)` tiếp theo trong cùng context có thể trả lại managed instance cũ, không phải tự sửa state sau bulk operation.

### Vì sao dễ gặp lỗi ghi đè?

Nếu sau bulk update, ứng dụng sửa một thuộc tính khác trên managed Book stale và provider flush sau đó, tùy mapping/update strategy có nguy cơ cập nhật state không như mong muốn. Ngoài ra, bulk update có những quy tắc riêng với versioning và callbacks; không nên giả định tất cả bảo đảm của việc sửa từng managed entity đều được áp dụng tự động cho bulk query.

Cách xử lý tùy trường hợp:

- Flush những pending changes cần được database thấy **trước** bulk query.
- Sau bulk operation, refresh các entity cụ thể nếu cần.
- Hoặc clear persistence context ở ranh giới phù hợp.
- Hoặc thực hiện bulk operation trong một context/transaction tách biệt.
- Thiết kế rõ quy tắc versioning, locking và hiệu ứng với second-level cache.

Lưu ý:

```java
em.clear();
```

sẽ detach **tất cả** managed entities và có thể làm mất thay đổi chưa flush. Không dùng clear như biện pháp “an toàn tuyệt đối” nếu transaction đang chứa các thay đổi quan trọng khác.

## 16. Một ví dụ thứ tự hoạt động gây nhầm lẫn

Giả sử code:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

Long matches = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.title = :title",
    Long.class
).setParameter("title", "Tên mới")
 .getSingleResult();

book.changeCategory("DATABASE");

em.getTransaction().commit();
```

Ở AUTO, khi query count thực thi, provider có thể flush thay đổi `title` trước query. Sau query, ứng dụng lại sửa `category`, vì vậy có thể xuất hiện **hai giai đoạn đồng bộ** trong cùng transaction:

```text
T0  Book được tải
T1  Sửa title (pending)
T2  Query count
    └── Có thể flush UPDATE title để query đúng
T3  Sửa category (pending)
T4  Commit
    └── Flush thay đổi category còn lại
T5  Transaction commit thành công
```

Trên một provider, có thể quan sát hai `UPDATE` thay vì một `UPDATE` nếu không có query ở giữa. Đây là **lý do hiệu năng thực tế** khiến việc đặt query ở đâu trong luồng xử lý có thể ảnh hưởng tới số round trip và khả năng batching.

Nhưng không được khẳng định chắc chắn hai `UPDATE` sẽ luôn xảy ra. SQL phụ thuộc provider, snapshot/dirty checking, dynamic update, chiến lược ID, transaction và flush optimization.

### Bài học thiết kế

Nếu không cần query giữa hai lần sửa, có thể hoàn tất các thay đổi liên quan trước rồi mới chạy query hoặc commit. Điều này có thể giảm những lần flush trung gian.

Nếu query **cần** kiểm tra trạng thái sau khi sửa title nhưng trước khi sửa category, việc flush sớm có thể là đúng yêu cầu nghiệp vụ. Tính đúng phải được ưu tiên hơn một tối ưu hóa SQL không tương thích với luồng xử lý.

## 17. Query có thể làm lỗi constraint xuất hiện sớm

Giả sử title phải unique trong một category:

```sql
ALTER TABLE books
ADD CONSTRAINT uq_books_category_title
UNIQUE (category, title);
```

Code:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên đang bị trùng");

List<Book> candidates = em.createQuery(
    "SELECT b FROM Book b WHERE b.category = :category",
    Book.class
).setParameter("category", book.getCategory())
 .getResultList();

em.getTransaction().commit();
```

Nếu provider flush pending UPDATE trước query, database có thể phát hiện unique violation **ngay ở `getResultList()`** thay vì đợi tới `commit()`.

Vì thế, exception ném từ dòng query không nhất thiết có nghĩa `SELECT` sai. Nguyên nhân có thể là **INSERT/UPDATE/DELETE được flush trước SELECT**.

Một số lỗi có thể xuất hiện khi query-triggered flush:

- `NOT NULL` violation.
- `UNIQUE` violation.
- Foreign key violation.
- Optimistic locking conflict.
- Data truncation hoặc conversion error.
- Constraint do DB trigger/check.
- Deadlock hoặc lock timeout khi ghi các thay đổi pending.

### Cách debug

Khi thấy stack trace chỉ vào `getResultList()` nhưng lỗi là `ConstraintViolationException` hoặc `OptimisticLockException`:

1. Xem những managed entities/associations đã bị sửa **trước query**.
2. Xem flush mode của query và context.
3. Bật SQL logging và bind parameter logging an toàn.
4. Xác định câu `INSERT`/`UPDATE`/`DELETE` nào chạy trước SELECT.
5. Kiểm tra ràng buộc và dữ liệu thực tế.
6. Rollback transaction nếu lỗi khiến transaction không thể tiếp tục.
7. Sửa root cause của dữ liệu/mapping/transaction, không chỉ xóa query gây kích hoạt flush.

**Di chuyển query xuống dưới chưa chắc giải quyết lỗi nghiệp vụ**; nhiều trường hợp chỉ dời lỗi sang `commit()`.

## 18. Transaction boundary quyết định bảo đảm flush

Các quy tắc query flush ở trên phải được đặt trong bối cảnh **persistence context có tham gia transaction hay không**.

Trong JPA, khi **không có transaction đang hoạt động hoặc persistence context chưa tham gia transaction**, provider không được flush các thay đổi đang chờ xuống database chỉ vì flush mode được đặt AUTO. Vì thế, không thể đơn giản nói “mọi query AUTO luôn làm SQL UPDATE trước SELECT”.

Bối cảnh:

```text
Persistence context joined to active transaction
    └── AUTO: provider phải bảo đảm thay đổi liên quan
        được phản ánh khi xử lý query.

Không có joined active transaction
    └── Không flush pending modifications xuống DB
        chỉ để chạy query theo cách của transaction.
```

Trong môi trường transaction-scoped, container thường quản lý ngữ cảnh và giao dịch. Trong application-managed `EntityManager` resource-local, cần begin/commit/rollback phù hợp.

### Query ngoài transaction có chạy được không?

Nhiều query đọc có thể được thực thi ngoài transaction tùy API và provider, nhưng **không nên suy rằng một query như thế sẽ tự commit các thay đổi trong context**. Các bulk modifying queries thường yêu cầu transaction phù hợp và có thể ném `TransactionRequiredException` nếu không có transaction khi cần.

### Unsynchronized persistence context

Jakarta Persistence có cơ chế context **unsynchronized** trong các môi trường hỗ trợ, có thể tham gia transaction sau bằng `joinTransaction()`. Chỉ có transaction ở tầng hệ thống không tự động có nghĩa mọi context chưa đồng bộ đã tham gia. Khi cần bảo đảm flush/query, phải xét trạng thái **joined** của context.

Đây là lý do các quy tắc ngắn gọn “AUTO luôn flush” hoặc “một query luôn thấy toàn bộ setter trước đó” dễ sai nếu bỏ qua transaction/context.

## 19. Query read-your-writes khác dữ liệu transaction khác nhìn thấy

Một nhầm lẫn quan trọng:

> Nếu query trong transaction của tôi thấy dữ liệu vừa thay đổi, liệu các transaction khác cũng thấy dữ liệu ấy ngay?

Không nhất thiết.

Giả sử transaction A:

```text
A1: sửa Book #42
A2: AUTO query khiến provider flush UPDATE
A3: query trong A thấy thay đổi
A4: chưa commit
```

Transaction B chạy song song chịu sự kiểm soát của database isolation level và lock. Với những mức isolation phổ biến như READ COMMITTED, B thường **không thấy** thay đổi chưa commit của A.

`flush()` chỉ gửi SQL trong transaction; không phải thông báo mọi client khác sẽ đọc được giá trị mới. Khi A rollback, thay đổi đã flush cũng không được xác nhận.

### Phân biệt ba mức

| Mức | Nội dung |
| --- | --- |
| Persistence context | Managed objects và thay đổi đang chờ trong bộ nhớ |
| Transaction database | Những SQL đã chạy nhưng có thể chưa commit |
| Quan sát của transaction khác | Phụ thuộc isolation/locking và commit |

Query-triggered flush tác động đến **thời điểm đồng bộ từ context xuống DB**, không tự thay đổi isolation level.

Nếu cần một hệ thống khác thấy thay đổi, phải xác định **đã commit** và cơ chế consistency/integration riêng; không thể chỉ gọi `flush()`.

## 20. Ảnh hưởng tới hiệu năng: query placement và batching

JPA có thể trì hoãn và gom các SQL update/insert, nhưng một query có thể tạo ranh giới flush trung gian.

Ví dụ minh họa:

```java
em.getTransaction().begin();

for (Book book : booksToRename) {
    book.rename("Prefix: " + book.getTitle());

    // Query nằm trong vòng lặp:
    Long count = em.createQuery(
        "SELECT COUNT(b) FROM Book b WHERE b.category = :cat",
        Long.class
    ).setParameter("cat", book.getCategory())
     .getSingleResult();
}

em.getTransaction().commit();
```

Với AUTO, query trong mỗi vòng có thể khiến provider phải xem xét pending changes và flush nhiều lần. Hệ quả có thể gồm:

- Nhiều đợt SQL/round trip.
- Khả năng gom batch thay đổi nhỏ đi.
- Áp lực transaction log hoặc lock đến sớm.
- Query aggregate lặp lại nhiều lần.
- Khó dự đoán nơi exception xảy ra.

Một cách tổ chức có thể tốt hơn:

```java
em.getTransaction().begin();

for (Book book : booksToRename) {
    book.rename("Prefix: " + book.getTitle());
}

// Chỉ truy vấn khi thực sự cần kết quả.
Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = :cat",
    Long.class
).setParameter("cat", "JAVA")
 .getSingleResult();

em.getTransaction().commit();
```

Tuy nhiên, không được đổi thứ tự thao tác nếu nghiệp vụ yêu cầu query sau mỗi lần xử lý để quyết định bước kế tiếp. Cần ưu tiên semantics trước tối ưu.

### Không có bảo đảm “AUTO = flush toàn bộ mỗi lần”

Một provider có thể phát hiện query không liên quan tới những bảng dirty và bỏ qua flush. Cũng có thể sử dụng các tối ưu hóa khác. Vì vậy muốn đo hiệu năng:

- Xem SQL và số lần flush thực tế.
- Đo transaction latency.
- Xem batching và kích thước batch.
- Kiểm tra số entity dirty/managed.
- Phân tích index và kế hoạch query.
- Tránh suy luận chỉ từ annotation.

## 21. Kiểm tra SQL và flush trong môi trường phát triển

Để hiểu ứng dụng thật, ta cần quan sát **thứ tự SQL** thay vì chỉ nhìn code.

Có thể dùng:

- SQL logging của provider (ví dụ cấu hình Hibernate SQL logging).
- Logging bind parameters ở môi trường an toàn.
- Statistics/metrics mà ORM hỗ trợ, nếu bật.
- Database statement log/profiler.
- Integration tests trên database được dự án sử dụng.

Một thứ tự giả định dễ nhận diện:

```text
SELECT ... FROM books WHERE id = 42
UPDATE books SET title = ?, version = ? WHERE id = ? AND version = ?
SELECT COUNT(*) FROM books WHERE title = ?
COMMIT
```

Nếu `UPDATE` xuất hiện trước `SELECT COUNT`, đó là dấu hiệu provider đã đồng bộ pending state trước query. Nếu `UPDATE` không xuất hiện, cần xem có thật sự dirty change không, entity có managed không, transaction có đang joined không, query có liên quan không và provider dùng phương pháp nào.

### Các chi tiết dễ ảnh hưởng quan sát

**GenerationType.IDENTITY:** `INSERT` có thể chạy sớm để lấy ID, không nhất thiết do query gây flush.

**Query cache:** provider có thể dùng cache với điều kiện phù hợp; không suy rằng mọi lời gọi query phát một SQL SELECT.

**Dynamic update:** SQL `UPDATE` có thể chỉ gồm một số cột bị sửa, tùy provider/cấu hình.

**Bytecode enhancement:** cách phát hiện dirty state có thể khác nhau nhưng semantics của managed entity vẫn phải đúng.

**Native query:** provider có thể flush theo cách thận trọng hơn vì không biết rõ phụ thuộc bảng.

**Query-specific flush mode:** `Query.setFlushMode(...)` có thể ghi đè lựa chọn chung.

**Transaction infrastructure:** Spring/Java EE có thể quản lý context, read-only hint và lifecycle theo cấu hình riêng; không coi hint framework là một định luật JPA portable.

Mục tiêu là nhận biết **nguyên nhân thực tế** của flush, không chỉ đếm số câu SQL.

## 22. Kiểm thử ảnh hưởng của query tới kết quả

Một integration test có giá trị khi kiểm chứng hành vi thực tế của `AUTO` với thay đổi chưa commit. Ví dụ giả định dùng JUnit và một `EntityManager` có transaction phù hợp.

### Test query thấy thay đổi liên quan ở AUTO

```java
@Test
void autoQuerySeesChangedTitle() {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, existingBookId);
        book.rename("Unique Title For Test");

        List<Book> matches = em.createQuery(
            "SELECT b FROM Book b WHERE b.title = :title",
            Book.class
        ).setParameter("title", "Unique Title For Test")
         .getResultList();

        assertTrue(matches.contains(book));

        em.getTransaction().rollback();
    } finally {
        em.close();
    }
}
```

Ví dụ minh họa giả định tên test không trùng với sách khác và flush mode là AUTO. Nội dung cần kiểm tra là **query xử lý thay đổi liên quan**, không phải đếm chắc chắn một lệnh UPDATE. Nếu dùng `contains`, cần xem `equals()`/`hashCode()` của Book; với cùng managed instance, kiểm tra reference hoặc ID có thể phù hợp hơn cho bài test tập trung vào identity.

### Test COMMIT không được dùng làm khẳng định cố định

Không nên viết test portable:

```java
// Sai nếu coi đây là bảo đảm chung của COMMIT:
assertEquals(oldCount, countBeforeCommit);
```

Ở COMMIT, hành vi quan sát pending changes trước commit không được chuẩn hóa như AUTO; ID strategy, flush đã xảy ra và provider có thể dẫn đến các kết quả khác nhau.

Thay vì vậy, test COMMIT có thể dùng để **ghi nhận hành vi của provider/version cụ thể** hoặc kiểm tra rằng sau `flush()` tường minh, query trên cùng transaction nhận dữ liệu phù hợp.

### Test query-triggered flush và lỗi constraint

Thiết kế một test tích hợp với unique constraint:

1. Tạo hai Book cùng category, title ban đầu khác nhau.
2. Bắt đầu transaction.
3. Đổi title của một Book thành title đang được Book khác sử dụng.
4. Thực thi một query liên quan ở AUTO.
5. Quan sát lỗi và thứ tự SQL của provider.
6. Rollback transaction và đóng context.

Không giả định vị trí exception hoàn toàn portable; mục tiêu là hiểu provider **có thể** phát hiện lỗi ở query-triggered flush chứ không chỉ ở commit.

## 23. Trường hợp query không cần flush vì object đã managed

Một số thao tác đọc không tạo query database mới, chẳng hạn đọc trực tiếp thuộc tính:

```java
Book book = em.find(Book.class, 42L);
book.rename("JPA chuyên sâu");

String title = book.getTitle();
```

`title` được lấy từ Java object. Không cần flush chỉ để getter thấy field vừa sửa.

Tương tự:

```java
Book same = em.find(Book.class, 42L);
```

trong cùng persistence context có thể trả lại chính managed instance đã có.

Nhưng nếu code phải tính tổng theo nhiều entity từ DB:

```java
Long total = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.title = :title",
    Long.class
).setParameter("title", "JPA chuyên sâu")
 .getSingleResult();
```

thì đây là một query có ngữ nghĩa khác. Bảo đảm của AUTO có thể yêu cầu đồng bộ để kết quả phản ánh thay đổi.

**Đọc field của managed entity và truy vấn tập hợp qua SQL không phải hai cách hoàn toàn tương đương.**

## 24. Tránh dùng flush mode để che lỗi mapping hoặc constraint

Giả sử một quan hệ ManyToOne là bắt buộc:

```java
@ManyToOne(optional = false)
@JoinColumn(name = "author_id", nullable = false)
private Author author;
```

Code gán `author = null` rồi query ở AUTO. Provider có thể flush và nhận lỗi `NOT NULL`/foreign key.

Chuyển query sang COMMIT chỉ vì muốn “truy vấn không lỗi” có thể làm lỗi xuất hiện muộn hơn ở commit; nó không giải quyết association đang sai.

Tương tự:

- Unique key bị trùng.
- Entity mới tham chiếu transient entity chưa persist.
- Hai phía của quan hệ hai hướng không được đồng bộ.
- Dữ liệu enum/converter không hợp lệ.
- Version optimistic locking đã cũ.

Flush mode không chữa được dữ liệu không hợp lệ. Cách đúng là sửa business logic, mapping, cascade hoặc transaction/constraint tương ứng.

## 25. Bảng quyết định nhanh: query nào nên chú ý?

| Tình huống | Cần chú ý điều gì? |
| --- | --- |
| Sửa managed entity rồi `find` lại cùng ID | Có thể nhận cùng object managed, không nhất thiết query SQL |
| Sửa managed entity rồi JPQL lọc theo field đó | AUTO bảo đảm pending change liên quan phản ánh vào query |
| `persist` entity mới rồi query `COUNT` | AUTO có thể dẫn đến SQL đồng bộ trước count |
| Sửa association rồi query `JOIN`/`EXISTS` | Phải xét FK/join table và owning side |
| Query đọc bảng khác không liên quan | Provider có thể tối ưu tránh flush, nhưng không được đảm bảo tuyệt đối |
| `Query.setFlushMode(COMMIT)` | Pending changes ảnh hưởng query trước commit là không được bảo đảm như AUTO |
| Native SQL | Cần xét phụ thuộc provider và query-space; flush tường minh nếu yêu cầu |
| Bulk JPQL UPDATE/DELETE | Có thể cần flush trước và xử lý stale context sau |
| Query trong vòng lặp thay đổi entity | Nguy cơ nhiều flush trung gian và kém batching |
| Query phát lỗi constraint | Có thể do SQL ghi được flush trước SELECT |
| Không có transaction đang active/joined | Provider không flush pending state xuống DB vì query AUTO |
| Có `flush()` tường minh trước query | SQL pending được đồng bộ trong transaction, nhưng chưa commit |

Một bảng như vậy giúp phân loại vấn đề trước khi kết luận “JPA flush quá sớm” hoặc “JPA chưa cập nhật”.

## 26. Những sai lầm thường gặp

### Sai lầm 1: “Query SELECT chỉ đọc nên không thể kích hoạt UPDATE”

Trong AUTO, provider có thể flush các thay đổi pending trước khi thực thi SELECT để bảo đảm query đúng. Chính vì thế exception của UPDATE có thể xuất hiện tại dòng `getResultList()`.

### Sai lầm 2: “Mặc định AUTO luôn flush trước mọi query”

Không phải yêu cầu của chuẩn. AUTO yêu cầu kết quả phù hợp với thay đổi liên quan; provider có thể tối ưu hoặc dùng cơ chế khác.

### Sai lầm 3: “COMMIT chắc chắn không có SQL ghi trước commit”

Không chính xác. Provider có thể phát SQL sớm vì generated ID hoặc flush tường minh, và COMMIT không định nghĩa một lệnh cấm tuyệt đối mọi SQL trước commit.

### Sai lầm 4: “Đã flush thì transaction khác phải nhìn thấy”

Sai. Flush đồng bộ trong transaction hiện tại; khả năng quan sát từ transaction khác phụ thuộc isolation/locking/commit.

### Sai lầm 5: “`createQuery()` vừa gọi là DB chạy SELECT”

Thường query thực sự được xử lý khi terminal operation như `getResultList()` hoặc `getSingleResult()` được gọi.

### Sai lầm 6: “JPQL COUNT không cần flush vì chỉ lấy một số”

Count cũng phụ thuộc các hàng và các thuộc tính đang chờ thay đổi, nên có thể dẫn đến flush theo AUTO.

### Sai lầm 7: “Query cùng bảng mới gây flush”

Provider có thể phân tích phụ thuộc bảng, nhưng native query, join, collection table và chiến lược implementation khiến việc suy đoán từ tên bảng đơn lẻ không đủ chắc chắn.

### Sai lầm 8: “Bulk update sẽ sửa mọi managed entity trong bộ nhớ”

Không. Bulk JPQL DML có thể thay DB mà các instance đã tải vẫn stale. Cần refresh/clear/transaction boundary phù hợp.

### Sai lầm 9: “Đổi sang COMMIT là cách giải quyết constraint violation”

Nếu dữ liệu không hợp lệ, lỗi có thể chỉ bị dời đến thời điểm flush/commit. Phải sửa root cause.

### Sai lầm 10: “Cứ flush sau mỗi setter cho dễ hiểu”

Điều này có thể làm tăng số round trip, giảm batching và không giải quyết yêu cầu commit. Chỉ flush tường minh khi cần.

### Sai lầm 11: “Không có transaction thì AUTO vẫn flush ghi xuống DB”

Provider không được flush pending modifications khi persistence context không tham gia active transaction. Cần phân biệt query ngoài transaction và query trong joined transaction.

### Sai lầm 12: “Entity đã loaded thì query luôn thấy dữ liệu mới nhất từ DB”

Persistence context có identity map; một managed entity có thể giữ state cũ sau bulk SQL hay transaction khác. Query flush và refresh là các cơ chế khác nhau.

## 27. Bài tập suy luận

### Bài tập 1: Sửa title rồi query theo title

```java
em.setFlushMode(FlushModeType.AUTO);

Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

List<Book> found = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
).setParameter("title", "Tên mới")
 .getResultList();
```

**Câu hỏi:** Tại sao provider có thể phát UPDATE trước SELECT?

**Gợi ý:** Predicate dựa vào title đang chờ cập nhật. Với AUTO trong joined transaction, query phải phản ánh thay đổi liên quan; flush là cách thường dùng để bảo đảm điều đó.

### Bài tập 2: Query đếm sau persist

```java
Book book = new Book("JPA", "JAVA");
em.persist(book);

Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.category = 'JAVA'",
    Long.class
).getSingleResult();
```

**Câu hỏi:** `COUNT` có thể ảnh hưởng thời điểm INSERT không?

**Đáp án:** Có. Nếu Book mới ảnh hưởng kết quả count, ở AUTO provider cần bảo đảm kết quả phản ánh nó; có thể flush trước query. IDENTITY cũng có thể khiến INSERT xảy ra sớm không liên quan riêng tới query.

### Bài tập 3: Chế độ COMMIT

```java
em.setFlushMode(FlushModeType.COMMIT);
em.persist(new Book("JPA", "JAVA"));

Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b",
    Long.class
).getSingleResult();
```

**Câu hỏi:** Có thể khẳng định count chắc chắn không bao gồm Book mới không?

**Đáp án:** Không. Với COMMIT, tác động của pending changes lên query trước commit không được đặc tả bảo đảm như AUTO. Provider có thể đã gửi SQL vì ID generation hoặc flush khác.

### Bài tập 4: Constraint báo lỗi tại query

`book.rename("Tên trùng")` rồi gọi `getResultList()`; exception báo unique constraint violation.

**Câu hỏi:** Có phải SELECT viết sai không?

**Đáp án:** Không nhất thiết. Query có thể kích hoạt flush trước SELECT và chính UPDATE pending bị database từ chối.

### Bài tập 5: Flush và transaction khác

A thay đổi Book, gọi `em.flush()` rồi chưa commit; B dùng transaction riêng query dữ liệu.

**Câu hỏi:** B có chắc thấy title mới không?

**Đáp án:** Không. Phụ thuộc isolation/locking của DB; ở các mức cách ly phổ biến, dữ liệu chưa commit không được B nhìn thấy. Flush không phải commit.

### Bài tập 6: Query không liên quan

Sửa Book rồi query Warehouse không có quan hệ với Book.

**Câu hỏi:** JPA AUTO có luôn flush update Book không?

**Đáp án:** Không có quy tắc tuyệt đối như vậy. Provider có thể bỏ qua flush nếu thay đổi không ảnh hưởng query; cũng có thể flush vì chiến lược riêng. Đừng viết code dựa vào một tối ưu hóa không portable.

### Bài tập 7: Bulk UPDATE

Một Book đã managed có `category = "JAVA"`. Chạy JPQL bulk update đặt category thành `"DATABASE"`.

**Câu hỏi:** Getter `book.getCategory()` có tự đổi ngay không?

**Đáp án:** Không được bảo đảm. Bulk DML có thể thay database mà persistence context còn giữ state cũ. Cần refresh/clear hoặc ranh giới context phù hợp.

### Bài tập 8: Truy vấn nhiều lần trong vòng lặp

Trong mỗi vòng lặp, sửa một managed Book rồi chạy query thống kê.

**Câu hỏi:** Có rủi ro hiệu năng gì?

**Đáp án:** Query ở AUTO có thể tạo nhiều điểm flush trung gian, giảm batching và tăng round trip. Cân nhắc gom thao tác và query khi ngữ nghĩa nghiệp vụ cho phép.

### Bài tập 9: Không có joined transaction

Một persistence context chưa tham gia active transaction có thay đổi object, rồi thực thi query AUTO.

**Câu hỏi:** Provider có được flush thay đổi xuống database như khi đang joined transaction không?

**Đáp án:** Không. Đặc tả không cho phép flush pending modifications xuống database khi không có transaction đang active/joined; phải xét đúng vòng đời context.

### Bài tập 10: Một query có flush mode riêng

`em` đang ở AUTO, nhưng một query đặt `setFlushMode(COMMIT)`.

**Câu hỏi:** Ngữ nghĩa nào áp dụng cho query đó?

**Đáp án:** Query sử dụng flush mode tường minh của chính nó, nên không được kỳ vọng các thay đổi pending ảnh hưởng tới kết quả theo bảo đảm AUTO.

## 28. Quy trình phân tích một query gây flush ngoài dự kiến

Khi thấy SQL ghi xuất hiện trước một query, có thể phân tích theo các bước:

1. **Xác định entity đang managed:** Có instance nào đã sửa từ lần flush trước không?
2. **Xác định pending changes:** `persist`, `remove`, dirty scalar field, FK, join table, collection table?
3. **Xem transaction:** Context có đang tham gia active transaction không?
4. **Xem flush mode:** `EntityManager` đang AUTO hay COMMIT? Query có mode riêng không?
5. **Xem loại query:** JPQL, Criteria, native SQL, bulk UPDATE/DELETE?
6. **Xem query cần dữ liệu gì:** Predicate, JOIN, COUNT, SUM, GROUP BY hoặc ORDER BY phụ thuộc thay đổi pending không?
7. **Kiểm tra provider/version:** Có chiến lược query-space, flush optimization, cache hoặc IDENTITY insert sớm không?
8. **Xem thứ tự SQL:** Có INSERT/UPDATE/DELETE trước SELECT không?
9. **Kiểm tra lỗi:** Có constraint/optimistic locking failure do flush thay vì SELECT không?
10. **Xem transaction sau lỗi:** Cần rollback và tạo context mới không?
11. **Xem hiệu năng:** Query có đang trong vòng lặp và tạo nhiều flush/batch boundary không?
12. **Chọn cách sửa đúng tầng:** Đổi vị trí query, explicit flush, query-level flush mode, quản lý transaction hoặc sửa mapping/dữ liệu — tùy mục đích.

Nếu sau khi xử lý vẫn còn sự khác biệt giữa các database/provider, hãy ghi nhận đó là **hành vi implementation-dependent** cần integration test với đúng phiên bản hệ thống đang triển khai.

## Kết luận

Trong JPA, **thời điểm đồng bộ dữ liệu không chỉ được quyết định bởi `flush()` tường minh hoặc `commit()`; việc thực thi truy vấn cũng có thể ảnh hưởng mạnh tới thời điểm đó**. Với `FlushModeType.AUTO` trong một persistence context đã tham gia transaction, provider phải bảo đảm các thay đổi pending có thể ảnh hưởng kết quả query được phản ánh trong quá trình xử lý query. Một cách thực hiện thường gặp là flush các SQL ghi cần thiết trước khi chạy `SELECT`.

Với `FlushModeType.COMMIT`, tác động của pending changes tới query trước commit không có cùng mức bảo đảm. Không nên suy diễn COMMIT là “cấm toàn bộ SQL trước commit”, cũng không nên suy diễn AUTO là “luôn flush trước mọi SELECT”. JPQL, Criteria, native SQL, bulk DML, association, generated ID, query cache và chiến lược provider đều có thể ảnh hưởng chi tiết thực thi.

Quan trọng nhất, **flush không phải commit**: query có thể kích hoạt SQL ghi và phát hiện lỗi sớm hơn, nhưng transaction vẫn có thể rollback; transaction khác không tự nhìn thấy dữ liệu chưa commit.

Khi cần dự đoán đúng hành vi, hãy đặt bốn câu hỏi: **“Có những thay đổi managed nào đang chờ? Query có phụ thuộc chúng không? Context đang dùng flush mode/transaction nào? Provider thực tế đồng bộ vào lúc nào?”**. Trả lời được những câu hỏi đó giúp thiết kế truy vấn đúng ngữ nghĩa, giải thích lỗi phát sinh tại `getResultList()` và tránh những lần flush không cần thiết làm giảm hiệu năng.
