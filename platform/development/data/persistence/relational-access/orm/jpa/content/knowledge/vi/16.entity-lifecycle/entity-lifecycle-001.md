# Phân biệt entity mới, được quản lý, đã tách và chờ xóa

Trong Java, một đối tượng được tạo bằng `new` luôn là một Java object. Nhưng trong JPA/Jakarta Persistence, chỉ biết object đó tồn tại trong bộ nhớ là chưa đủ để dự đoán nó có được ghi vào database hay không. JPA còn quản lý **vòng đời entity** (*entity lifecycle*) thông qua **persistence context** — ngữ cảnh theo dõi danh tính và trạng thái của những đối tượng persistent.

Một instance của cùng một class `Book` có thể ở bốn trạng thái quan trọng:

1. **Mới** (*new/transient*): vừa được tạo, chưa được persistence context quản lý.
2. **Được quản lý** (*managed/persistent*): có entity identity và đang được persistence context theo dõi.
3. **Đã tách** (*detached*): đại diện một entity đã persistent nhưng không còn được context hiện tại quản lý.
4. **Chờ xóa** (*removed*): entity đã được đánh dấu xóa trong context; thay đổi xóa sẽ được đồng bộ xuống database theo quy tắc transaction.

Điểm dễ nhầm nhất: **trạng thái entity trong bộ nhớ không đồng nghĩa trực tiếp với việc một câu SQL đã chạy hay transaction đã commit**. Ví dụ, gọi `persist()` chuyển một entity mới sang managed, nhưng lệnh `INSERT` có thể còn chờ tới `flush()`; gọi `remove()` đánh dấu entity để xóa, nhưng hàng database có thể vẫn hiện diện cho đến khi lệnh `DELETE` được thực thi và transaction được commit.

Bài học này giải thích từng trạng thái, các phương thức `EntityManager` gây chuyển trạng thái, những tình huống với `merge()`, `detach()`, `clear()`, cascade, transaction và các lỗi thường gặp. Đây là nền tảng của chương **Vòng đời entity** trong chủ đề **Data Persistence Relational Access ORM JPA**.

## 1. Hai lớp khái niệm: Java object và trạng thái persistence

Giả sử một bảng quan hệ:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL
);
```

Một entity Java:

```java
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

    protected Book() {}

    public Book(String title) {
        rename(title);
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

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        this.title = newTitle.trim();
    }
}
```

Ở đây:

- `@Entity` đánh dấu class được ánh xạ.
- `@Id` xác định khóa chính, giúp provider nhận diện persistent identity.
- `@GeneratedValue` để database/provider tạo ID theo chiến lược đã chọn.
- `@Version` hỗ trợ optimistic locking; không bắt buộc để hiểu vòng đời nhưng hữu ích khi xem xét cập nhật đồng thời.
- `@Column` mô tả ánh xạ thuộc tính `title`.
- Constructor không tham số `protected` phục vụ khả năng khởi tạo entity của JPA.
- Method `rename()` thể hiện cách thay đổi trạng thái nghiệp vụ của object.

Cùng class `Book` có thể cho ra hai kết quả rất khác:

```java
Book a = new Book("JPA căn bản"); // new/transient
Book b = em.find(Book.class, 42L); // managed nếu tìm thấy
```

Cả hai đều là object kiểu `Book`. Nhưng JPA chỉ tự động theo dõi thay đổi persistent của `b` nếu `b` đang managed trong persistence context phù hợp.

## 2. Bảng phân biệt bốn trạng thái

| Trạng thái | Khái niệm | Có liên kết với persistence context? | Có tự động đồng bộ thay đổi thuộc tính? | Hàng DB có chắc đã tồn tại? |
| --- | --- | --- | --- | --- |
| **New / transient** | Object mới, chưa được JPA đưa vào quản lý | Không | Không | Không thể suy ra từ object; thông thường chưa có hàng tương ứng |
| **Managed / persistent** | Instance được context quản lý theo entity identity | Có | Có, khi có transaction/flush phù hợp | Có thể chưa: entity mới `persist()` có thể đang chờ `INSERT` |
| **Detached** | Instance trước đây persistent nhưng không còn managed | Không | Không | Không chắc: hàng có thể bị xóa hoặc thay đổi từ nơi khác |
| **Removed** | Entity được đánh dấu xóa theo ngữ nghĩa JPA | Được context theo dõi để xử lý việc xóa, nhưng không còn ở trạng thái managed thông thường | Không nên tiếp tục sửa như một managed entity bình thường | Có thể vẫn còn hàng trước khi SQL `DELETE`/commit |

Đừng dùng riêng giá trị `id` hoặc kết quả một lần truy vấn database để phân loại bốn trạng thái này. Một object new với ID được gán thủ công vẫn có thể là new. Một object detached có ID vẫn không được theo dõi. Một object removed có thể còn tồn tại trong JVM ngay cả khi hàng database đã bị xóa.

### Tên trạng thái thường gặp trong tài liệu

| Thuật ngữ phổ biến | Tên tương đương | Cần hiểu |
| --- | --- | --- |
| New | Transient | Chưa gắn với persistence context |
| Managed | Persistent | Đang được persistence context quản lý |
| Detached | Disconnected | Có identity persistent nhưng không còn được context quản lý |
| Removed | Scheduled for deletion | Được đánh dấu xóa theo lifecycle, không đồng nghĩa object Java biến mất |

Trong bài này, các tên tiếng Anh được dùng bên cạnh tiếng Việt để tiện đối chiếu với JavaDoc và lỗi ORM provider.

## 3. Sơ đồ chuyển trạng thái tổng quan

```text
                   new Book(...)
                         │
                         ▼
                    [ NEW ]
                         │
                    persist()
                         │
                         ▼
                   [ MANAGED ] ◄──────────── find() / query / getReference()
                    │    │  ▲                         (khi tải entity)
                    │    │  │
        detach()    │    │  │ merge() trả về
        clear()     │    │  │ managed instance
        close()     │    │  │
                    ▼    │  │
                [ DETACHED ]
                         ▲
                         │
              context kết thúc,
              entity không còn managed

          [ MANAGED ] ─── remove() ───► [ REMOVED ]
                                           │
                                    flush / commit
                                           │
                                  SQL DELETE được xử lý
                                           │
                                 hàng bị xóa khi commit
```

Đây là sơ đồ **khái niệm**, không phải máy trạng thái đầy đủ của mọi tình huống JPA. Có các nhánh đặc biệt:

- `persist()` trên một entity **removed** trong cùng context có thể đưa nó trở lại managed theo quy tắc JPA.
- `remove()` với entity **new** không nhất thiết tạo `DELETE`; thao tác remove trên new entity được bỏ qua đối với chính entity đó (nhưng cascade liên quan vẫn cần được xét).
- `merge()` trên entity **removed** là thao tác không hợp lệ.
- `merge()` trên một entity **new** tạo hoặc tìm managed copy thích hợp; object nguồn không tự trở thành managed.
- `rollback()` làm thay đổi kết quả transaction và có hậu quả riêng với state trong bộ nhớ; không nên vẽ nó như một mũi tên đơn giản luôn đưa mọi entity về trạng thái new.
- Một persistence context có thể có vòng đời gắn transaction hoặc kéo dài, nên **commit không đồng nghĩa mọi trường hợp đều detach tức thì**.

Để phân tích chính xác, luôn xem **lời gọi API**, **trạng thái trước đó**, **persistence context**, **transaction** và **mapping cascade**.

## 4. Trạng thái mới — New / transient

Khi gọi constructor:

```java
Book book = new Book("JPA thực hành");
```

object `book` tồn tại trong JVM, nhưng JPA chưa biết cần quản lý hoặc lưu nó.

Dấu hiệu thông thường:

- Chưa có context nào quản lý instance.
- Việc đổi `book.title` không làm database cập nhật.
- Nếu khóa chính do DB sinh, `book.getId()` thường chưa có giá trị trước khi persist.
- Object có thể được đưa vào một collection Java thuần túy mà chưa hề trở thành persistent.

Ví dụ:

```java
Book book = new Book("Tên cũ");
book.rename("Tên mới");

// Chỉ là thao tác trong bộ nhớ. Không có SQL UPDATE,
// vì book chưa từng được persist.
```

### New không đồng nghĩa ID phải null

Với entity dùng ID do ứng dụng gán:

```java
@Entity
public class CatalogItem {
    @Id
    private String code;

    protected CatalogItem() {}

    public CatalogItem(String code) {
        this.code = code;
    }
}
```

```java
CatalogItem item = new CatalogItem("SKU-101");
```

`item` vẫn là **new/transient** dù `code` khác null, vì object chưa được JPA quản lý. Vì vậy, câu kiểm tra:

```java
if (entity.getId() == null) {
    // new?
}
```

không phải bộ phân loại vòng đời JPA tổng quát. Ngược lại, một entity detached có ID có thể trỏ tới hàng đã bị xóa khỏi DB; ID không phải bằng chứng hàng luôn tồn tại.

### Object new có thể trùng dữ liệu với hàng cũ

```java
Book newBook = new Book("JPA thực hành");
```

Ngay cả khi bảng `books` đã có một hàng mang tiêu đề đó, `newBook` vẫn không tự biến thành managed entity của hàng cũ. JPA identity dựa trên mapping `@Id`, không phải việc trùng tên hay thuộc tính hiển thị.

Nếu tên sách cần duy nhất theo nghiệp vụ, đó là một ràng buộc riêng cần kiểm tra và bảo vệ bằng database constraint phù hợp.

## 5. Từ new sang managed với `persist()`

`EntityManager.persist(entity)` được dùng để đưa entity mới vào trạng thái persistent/managed theo quy tắc JPA.

Ví dụ:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Book book = new Book("JPA căn bản");

    em.persist(book); // New -> Managed.
    System.out.println(em.contains(book)); // true.

    em.getTransaction().commit();
} catch (RuntimeException e) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw e;
} finally {
    em.close();
}
```

Sau `persist(book)`, object `book` được context quản lý. Provider biết cần đồng bộ một hàng tương ứng, tùy transaction và chiến lược tạo khóa.

### `persist()` không nhất thiết lập tức `INSERT`

Một cách hình dung:

```text
new Book("JPA căn bản")
          │
          ▼
em.persist(book)
          │
          ▼
Book trở thành managed
          │
          ▼
provider lên kế hoạch INSERT
          │
          ▼
em.flush() hoặc commit
          │
          ▼
SQL được gửi theo chiến lược provider
          │
          ▼
commit thành công → dữ liệu được xác nhận
```

Với `GenerationType.IDENTITY`, provider có thể cần thực hiện `INSERT` sớm để lấy khóa chính. Với `SEQUENCE` hoặc chiến lược khác, ID có thể được cấp trước khi hàng thật được insert. Vì vậy:

**Không được dùng “đã có ID”, “đã gọi persist” và “INSERT đã commit” như ba khái niệm đồng nhất.**

### Nếu transaction rollback?

Nếu `persist()` được gọi rồi transaction rollback, database không giữ hàng mới như một transaction đã commit thành công. Tuy nhiên, object Java vẫn tồn tại; nó có thể còn giá trị ID đã được cấp trước rollback hoặc giữ các field đã thay đổi.

Không nên mặc định object vừa rollback sẽ quay về trạng thái `new Book(...)` nguyên vẹn. Cách làm an toàn sau lỗi là đóng/bỏ context phù hợp, xác định lại trạng thái và thực hiện thao tác nghiệp vụ mới một cách có kiểm soát.

### Cần persist trong transaction phù hợp

Ví dụ resource-local ở trên dùng `getTransaction()`. Trong Spring hoặc Jakarta EE, transaction có thể được framework/container quản lý, và method nghiệp vụ thường có annotation transaction tương ứng thay vì tự gọi `getTransaction()`.

Chi tiết vận hành khác nhau, nhưng **không nên dựa vào side effect persist ngoài transaction** khi kỳ vọng dữ liệu chắc chắn được ghi thành công. Cần ranh giới transaction rõ ràng.

## 6. Trạng thái managed — Được quản lý

Một entity là **managed** khi persistence context đang quản lý instance ấy theo entity identity. Có nhiều cách để có được managed entity:

- Gọi `persist()` với entity mới.
- Gọi `find()` hoặc truy vấn trả về entity hiện có.
- Gọi `getReference()` để lấy tham chiếu được quản lý theo identity.
- Nhận một entity qua association được tải trong context.
- Nhận **giá trị trả về** từ `merge()` khi thao tác hợp lệ.

Ví dụ tìm entity:

```java
Book book = em.find(Book.class, 42L);

if (book != null) {
    System.out.println(em.contains(book)); // true
}
```

`find()` thường trả về null nếu không tìm thấy entity, trong khi `getReference()` có thể trả reference rồi phát hiện ID không tồn tại ở thời điểm khác. Cả hai cùng liên quan tới persistence context nhưng không đồng nghĩa số SQL luôn bằng nhau.

### Identity map: một instance managed cho một identity

Giả sử:

```java
Book a = em.find(Book.class, 42L);
Book b = em.find(Book.class, 42L);

if (a != null) {
    System.out.println(a == b); // true
}
```

Trong cùng persistence context, JPA duy trì một managed instance tương ứng với một persistent entity identity. Đó là lý do gọi `find()` lặp lại cho cùng identity không nhất thiết nạp object mới.

Giá trị `42` ở class `Book` không trùng identity với `42` ở class `Author`. Entity identity phải gắn với loại entity theo mapping, không phải chỉ một con số.

### Managed không có nghĩa dữ liệu luôn mới nhất

Nếu một context đã load `Book #42` và một transaction khác cập nhật tiêu đề ở database, gọi `find()` lại trong context cũ có thể trả chính managed instance hiện có với state cũ.

Khi cần tải lại state từ database, xem xét `refresh()`, transaction/context mới, cache policy hoặc locking phù hợp. Identity map bảo đảm tính đồng nhất object **trong context**, không bảo đảm tự quan sát mọi thay đổi bên ngoài.

## 7. Dirty checking: sửa managed entity mà không gọi `update()`

JPA không có `EntityManager.update()` chuẩn theo cách nhiều người hình dung. Với entity managed, provider theo dõi state persistent để đồng bộ thay đổi khi flush.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);

if (book == null) {
    throw new IllegalArgumentException("Book not found");
}

book.rename("JPA nâng cao");

// Không cần em.persist(book) lần nữa.
em.getTransaction().commit();
```

Khi transaction hoàn tất thành công, provider có thể phát SQL theo ý nghĩa:

```sql
UPDATE books
SET title = ?, version = ?
WHERE id = ? AND version = ?;
```

Đây là SQL minh họa; câu lệnh thực tế phụ thuộc provider, dialect, mapping và optimistic locking.

**Điểm quyết định:** `book` đang managed. Nếu object đã detached, chỉ gọi `rename()` sẽ không tự được persistence context đồng bộ.

### Không nên dùng `persist(managed)` như thao tác “save lại”

Với managed entity, gọi `persist()` không cần thiết để ghi các thay đổi state. JPA đã quản lý object. Nếu một ứng dụng gọi persist cho một instance đã managed, nó không phải lệnh tạo bản ghi mới khác. Thực hành tốt là sử dụng domain method và để dirty checking/flush xử lý việc cập nhật.

### Thay đổi một collection cũng là thay đổi persistent state

Nếu entity có association như:

```java
@OneToMany(mappedBy = "book", cascade = CascadeType.PERSIST)
private List<Review> reviews = new ArrayList<>();
```

thao tác trên association managed có thể ảnh hưởng tới dữ liệu cần đồng bộ. Tuy nhiên, với quan hệ hai hướng, **phía sở hữu quan hệ** vẫn quyết định việc cập nhật foreign key; chỉ sửa inverse collection không phải cách chuẩn để thay FK.

Quy tắc lifecycle của entity và quy tắc owning side của association phải được hiểu đồng thời.

## 8. `flush()` và `commit()` khác nhau như thế nào?

`flush()` yêu cầu provider đồng bộ các thay đổi pending trong persistence context với database, khi điều kiện transaction thích hợp được đáp ứng.

```java
em.getTransaction().begin();

Book book = new Book("JPA");
em.persist(book);

em.flush(); // Có thể thực thi INSERT vào database.

em.getTransaction().commit();
```

Nếu flush thành công, SQL có thể đã được thực hiện nhưng **transaction chưa commit**. Một transaction tiếp tục có thể rollback, khiến thay đổi đã flush không được xác nhận bền vững.

Phân biệt:

| Thao tác | Vai trò |
| --- | --- |
| `persist()` | Đưa entity new vào trạng thái managed và yêu cầu persistence |
| Dirty checking | Theo dõi thay đổi state của entity managed |
| `flush()` | Đồng bộ những thay đổi pending xuống database theo quy tắc transaction |
| `commit()` | Hoàn tất transaction thành công, xác nhận các thay đổi |
| `rollback()` | Hủy các thay đổi của transaction theo semantics DB |

Không thể suy từ số câu SQL rằng entity sẽ thuộc trạng thái nào trong mọi trường hợp; cần biết context và transaction vẫn đang hoạt động hay không.

### Flush mode

JPA cung cấp `FlushModeType.AUTO` và `FlushModeType.COMMIT`. Với `AUTO`, provider có trách nhiệm bảo đảm kết quả truy vấn phù hợp với những thay đổi pending có thể ảnh hưởng tới truy vấn; tùy cách thực thi, nó có thể flush trước query. Với `COMMIT`, tác động của các thay đổi pending lên query trước commit không có cùng bảo đảm như AUTO.

Đổi flush mode không biến entity managed thành detached, không thay đổi ý nghĩa `remove()`, và không thay thế transaction.

## 9. Trạng thái detached — Entity đã tách

Một entity **detached** là instance từng có identity persistent nhưng **không còn được persistence context hiện tại quản lý**.

Các nguyên nhân phổ biến:

- Gọi `em.detach(entity)`.
- Gọi `em.clear()`, làm tất cả managed entities trong context thành detached.
- Đóng `EntityManager` ứng dụng quản lý hoặc để persistence context kết thúc theo lifecycle.
- Rời một transaction-scoped persistence context khi context đó kết thúc.

Ví dụ:

```java
Book book = em.find(Book.class, 42L);

System.out.println(em.contains(book)); // true nếu tìm thấy

em.detach(book);

System.out.println(em.contains(book)); // false
```

Sau khi detach, object `book` vẫn tồn tại, còn `id` và những field đã được tải. Nhưng JPA **không còn tự theo dõi các thay đổi của instance ấy** trong context đó.

### Sửa detached object không tự sinh UPDATE

```java
Book book = em.find(Book.class, 42L);

em.detach(book);
book.rename("Tên sửa khi đã detached");

// Chỉ sửa Java object. Không tự được dirty checking ghi xuống DB.
```

Điều này rất quan trọng trong ứng dụng web: một entity được tải trong request trước, rồi giữ lại trong HTTP session hoặc gửi qua tầng ngoài, có thể đã detached khi request/transaction kế tiếp xử lý nó.

### Detached không đồng nghĩa dữ liệu đã bị xóa

Đây là nhầm lẫn về từ ngữ:

- **Detached:** object không còn gắn với context.
- **Removed:** entity được đánh dấu để xóa persistent record.

Sau `detach()`, hàng `books.id = 42` vẫn có thể tồn tại bình thường. Tách entity không phải lệnh `DELETE`.

### Detached vẫn có thể giữ dữ liệu cũ

Nếu database bị cập nhật sau khi object detached, giá trị field của object đó có thể không còn mới nhất. Vì vậy, không nên gửi detached entity từ client về server rồi ghi đè mọi thuộc tính một cách máy móc mà không có chính sách kiểm soát cập nhật đồng thời.

## 10. `detach()`, `clear()` và `close()` khác nhau

Ba thao tác đều có thể dẫn tới entity không còn managed, nhưng phạm vi khác nhau.

| Phương thức/sự kiện | Phạm vi | Hệ quả |
| --- | --- | --- |
| `em.detach(book)` | Một entity cụ thể, có thể lan truyền theo cascade DETACH | Object được chọn không còn được quản lý |
| `em.clear()` | Toàn bộ persistence context | Tất cả managed entities bị detach |
| `em.close()` | Đóng application-managed EntityManager | Kết thúc khả năng tiếp tục dùng EntityManager và context liên quan |
| Transaction-scoped context kết thúc | Theo vòng đời do container/framework quản lý | Những entity từng managed có thể trở thành detached bên ngoài phạm vi |

Ví dụ `clear()`:

```java
Book a = em.find(Book.class, 42L);
Book b = em.find(Book.class, 73L);

em.clear();

System.out.println(em.contains(a)); // false
System.out.println(em.contains(b)); // false
```

### Cảnh báo: clear có thể làm mất thay đổi pending

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Thay đổi chưa flush");

em.clear(); // Book bị detach; pending state có thể không được lưu.

em.getTransaction().commit();
```

Không nên dùng `clear()` như một phương thức “làm mới entity” tùy tiện. Nếu thực sự muốn đồng bộ thay đổi trước khi detach, dùng `flush()` trong transaction phù hợp:

```java
em.flush();
em.clear();
```

Tuy nhiên, `flush()` không đồng nghĩa commit. Nếu transaction tiếp tục rồi rollback, thay đổi đã flush vẫn không được xác nhận.

### Khi nào clear hữu ích?

Trong batch processing, persistence context giữ nhiều entity và snapshot có thể tiêu tốn bộ nhớ. Một kỹ thuật là:

```java
for (int i = 0; i < books.size(); i++) {
    em.persist(books.get(i));

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}
```

Cần lưu ý sau `clear()`, những object đã persist thành detached, nên không thể tiếp tục dùng chúng như thể còn managed. Đoạn minh họa giả định vòng lặp thao tác trong transaction phù hợp và dữ liệu đầu vào là những entity new thực sự.

## 11. Từ detached trở lại managed bằng `merge()`

`EntityManager.merge()` có tên dễ gây hiểu nhầm. Nó **không đơn giản gắn lại chính instance detached vào context**. Nó sao chép state sang một managed instance tương ứng và **trả về managed instance**.

Ví dụ:

```java
Book detachedBook = ...; // Đã được tải và detach trước đó.
detachedBook.rename("JPA mới");

em.getTransaction().begin();

Book managedBook = em.merge(detachedBook);

System.out.println(em.contains(managedBook)); // true

em.getTransaction().commit();
```

Với detached entity thông thường:

```java
System.out.println(managedBook == detachedBook);
// Không nên kỳ vọng true.
```

Đối số `detachedBook` vẫn là detached. Muốn tiếp tục thay đổi state được JPA theo dõi, phải dùng `managedBook` (hoặc tải managed entity rồi sửa trực tiếp).

### Ví dụ dễ sai sau merge

```java
Book managed = em.merge(detached);

detached.rename("Tên A"); // Sửa object detached.
managed.rename("Tên B");  // Sửa object managed.
```

Trong tình huống detached bình thường, chỉ sửa `managed` được theo dõi trực tiếp bởi context sau lần merge. Không được tự coi sửa trên detached sau merge sẽ được flush.

### Nếu context đã quản lý Book cùng ID thì sao?

```java
Book current = em.find(Book.class, 42L);

Book merged = em.merge(detachedBookWithId42);

System.out.println(current == merged); // true nếu cùng identity.
```

Provider duy trì **một managed instance cho một entity identity trong một context**. State của detached object có thể được copy vào managed representative đã tồn tại.

### Merge entity new

`merge(newBook)` là thao tác hợp lệ trong những trường hợp bình thường: provider tạo một managed copy có state tương ứng rồi lưu theo lifecycle của managed copy. Nhưng object `newBook` nguồn vẫn không tự trở thành managed.

Vì vậy, với entity vừa tạo và không cần merge detached graph, `persist()` thường biểu đạt ý định đơn giản hơn. Chọn giữa persist và merge dựa trên **trạng thái và use case**, không phải muốn một method “save mọi thứ”.

### Merge không bảo đảm không ghi đè dữ liệu mới

Detached entity có thể chứa state cũ. Nếu merge một object stale, dữ liệu đã được transaction khác thay đổi có thể bị ghi đè, trừ khi có cơ chế concurrency control phù hợp.

`@Version` hỗ trợ phát hiện một số xung đột optimistic locking; provider có thể ném `OptimisticLockException` khi version không còn phù hợp. Cần thiết kế xử lý xung đột, chứ không mặc định merge là thao tác “lấy bản mới nhất rồi thông minh hợp nhất mọi field”.

## 12. Trạng thái removed — Entity chờ xóa

`EntityManager.remove(entity)` được dùng để yêu cầu xóa một entity được quản lý.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);

if (book != null) {
    em.remove(book);
}

em.getTransaction().commit();
```

Sau `remove(book)`, entity được chuyển sang trạng thái **removed**. Provider sẽ xử lý thao tác xóa khi đồng bộ persistence context với database, tùy transaction và ràng buộc.

Sơ đồ:

```text
[MANAGED Book #42]
        │
        │ em.remove(book)
        ▼
[REMOVED Book #42]
        │
        │ flush
        ▼
DELETE FROM books WHERE id = 42 ...
        │
        │ commit thành công
        ▼
Bản ghi bị xóa khỏi database
```

### Removed chưa chắc đã được xóa vật lý ngay

Gọi `remove()` không phải cam kết câu SQL `DELETE` đã chạy ngay lập tức. Có thể provider đợi `flush()` hoặc commit để xử lý.

Ngược lại, sau `flush()`, SQL `DELETE` có thể đã chạy nhưng transaction chưa commit. Nếu transaction rollback, xóa có thể bị hủy theo semantics của database.

Vì vậy:

- **Marked removed:** trạng thái lifecycle.
- **SQL DELETE executed:** thay đổi đã được gửi tới DB.
- **DELETE committed:** transaction đã xác nhận xóa.

Ba mốc có liên hệ nhưng không đồng nghĩa.

### Java object không biến mất sau remove

```java
Book book = em.find(Book.class, 42L);
em.remove(book);

System.out.println(book.getTitle());
```

Biến `book` vẫn tham chiếu một Java object. Nhưng nó không còn là một entity managed bình thường để tiếp tục chỉnh sửa như trước. Không được suy rằng gọi `remove()` sẽ đặt biến Java thành `null` hoặc giải phóng object khỏi heap.

### Muốn xóa theo ID cần lấy managed entity

```java
Book book = em.find(Book.class, id);
if (book != null) {
    em.remove(book);
}
```

Trong một số tình huống dùng reference thích hợp:

```java
Book ref = em.getReference(Book.class, id);
em.remove(ref);
```

Nhưng `getReference()` có thể không xác thực ngay hàng tồn tại; cần cân nhắc tính tồn tại, lỗi runtime, foreign key và yêu cầu thông báo nghiệp vụ.

## 13. Không gọi `remove()` trực tiếp trên detached entity

Ví dụ dễ gặp:

```java
Book book = em1.find(Book.class, 42L);
em1.close();  // book trở thành detached khi context kết thúc.

// Trong EntityManager khác:
em2.getTransaction().begin();
em2.remove(book); // Không hợp lệ: book là detached.
```

Theo quy tắc JPA, `remove()` với detached entity có thể ném `IllegalArgumentException` (tại thời điểm gọi hoặc flush, tùy trường hợp). Nó không phải lệnh “xóa hàng theo ID” chấp nhận bất kỳ object có khóa chính.

Cách thực hiện rõ ràng:

```java
em2.getTransaction().begin();

Book managed = em2.find(Book.class, book.getId());
if (managed != null) {
    em2.remove(managed);
}

em2.getTransaction().commit();
```

Một cách khác là dùng `merge()` rồi `remove()` trên managed result nếu ngữ nghĩa merge và versioning phù hợp, nhưng nếu mục đích chỉ là xóa theo ID thì `find()` rồi `remove()` thường ít gây hiểu nhầm hơn.

### Nếu entity vẫn new thì remove thế nào?

`em.remove(new Book(...))` không có ý nghĩa tạo một `DELETE` cho bản ghi chưa được persist. Theo quy tắc lifecycle JPA, thao tác remove trên new entity được bỏ qua với chính entity new, nhưng **cascade REMOVE** tới các quan hệ liên quan vẫn có thể phát sinh tùy mapping.

Trong code nghiệp vụ, thường không cần gọi remove cho một object chưa bao giờ được lưu. Chỉ cần không persist nó.

### Nếu entity đã removed rồi gọi remove nữa?

JPA xử lý thao tác remove trên removed entity như một thao tác không cần tạo thêm trạng thái xóa khác; cascade vẫn có thể liên quan tới association theo quy tắc. Không nên thiết kế workflow dựa trên việc gọi nhiều lần remove để “chắc chắn đã xóa”.

## 14. Có thể `persist()` một entity đã removed không?

Một trường hợp ít gặp nhưng có trong lifecycle JPA là gọi `persist()` trên entity đã **removed** trong cùng persistence context: nó có thể đưa entity trở lại trạng thái managed, hủy ý định xóa theo quy tắc lifecycle.

Ví dụ khái niệm:

```java
Book book = em.find(Book.class, id);

em.remove(book);

// Khi còn trong context và transaction phù hợp:
em.persist(book);
```

Không nên xem đây là một pattern nghiệp vụ thông thường để “khôi phục entity đã xóa”. Nếu `DELETE` đã được flush, transaction đã commit hoặc object đã detached, tình huống khác đi và việc đưa lại hàng có thể cần thao tác riêng.

Với nhu cầu khôi phục dữ liệu đã xóa trong hệ thống thực tế, hãy thiết kế **soft delete**, trạng thái archive hoặc quy trình restore rõ ràng, thay vì dựa vào một chuỗi `remove()/persist()` phức tạp và nhạy với thời điểm flush.

## 15. Bảng tác động của các phương thức EntityManager theo trạng thái

Các hành vi dưới đây mô tả ý nghĩa chuẩn trong tình huống thông thường, có thể kèm cascade, transaction và exception tùy trạng thái đối tượng.

| API | New | Managed | Detached | Removed |
| --- | --- | --- | --- | --- |
| `persist(x)` | Trở thành managed, lên kế hoạch insert | Không cần persist lại; entity tiếp tục managed | Không hợp lệ cho detached theo kỳ vọng tạo mới, có thể lỗi | Có thể đưa trở lại managed theo quy tắc |
| `merge(x)` | Tạo managed copy, trả về copy | Trả về managed instance với quy tắc cascade merge | Copy state vào managed instance, trả về managed | Không hợp lệ, có thể ném `IllegalArgumentException` |
| `remove(x)` | Bỏ qua cho chính x, xét cascade | Chuyển x sang removed | Không hợp lệ, có thể ném `IllegalArgumentException` | Không cần thay đổi thêm, xét cascade |
| `detach(x)` | Không có managed state để tách | Tách x khỏi context | Không cần tách thêm | Quy tắc xử lý phụ thuộc trạng thái/cascade, không dùng như cách “undo delete” |
| `refresh(x)` | Không hợp lệ nếu x không managed | Tải lại state từ database theo quy tắc | Không hợp lệ nếu x không managed | Không dùng để khôi phục removed entity |
| `contains(x)` | Không phải managed | `true` nếu x thuộc context hiện tại | `false` | Không phải kiểm tra hàng DB còn tồn tại; không dùng để phân loại removed bằng một boolean |

Chú ý: một số thao tác không hợp lệ có thể phát exception tại lệnh gọi hoặc khi provider đồng bộ; loại exception gốc/bọc có thể phụ thuộc provider và transaction. Bảng này giúp chọn đúng ý định API, **không thay thế JavaDoc hoặc đặc tả của phiên bản JPA đang dùng**.

## 16. `contains()` giúp gì và không giúp gì?

`EntityManager.contains(entity)` kiểm tra một **instance cụ thể** có phải managed entity thuộc persistence context hiện tại hay không.

```java
Book book = em.find(Book.class, 42L);

if (book != null) {
    System.out.println(em.contains(book)); // true

    em.detach(book);

    System.out.println(em.contains(book)); // false
}
```

Điều quan trọng là kết quả `false` không cho biết chắc object thuộc trạng thái nào trong ba trạng thái khác:

- Có thể là new.
- Có thể là detached.
- Có thể là removed.
- Có thể thuộc persistence context khác.

Vì vậy, đoạn sau là sai tư duy:

```java
if (!em.contains(entity)) {
    em.persist(entity);
}
```

`!contains(entity)` không có nghĩa entity mới chưa từng được lưu. Nếu entity detached, `persist()` không phải thao tác phù hợp.

Tương tự, `contains()` không kiểm tra bảng database có một hàng mang ID đó hay không. Nó kiểm tra quan hệ giữa **object Java và persistence context hiện tại**.

## 17. Transaction commit có luôn detach entity không?

Không nên đưa ra một quy tắc tuyệt đối như “sau `commit()`, entity luôn detached” hoặc “sau `commit()`, entity luôn managed” nếu chưa biết **vòng đời persistence context**.

Có nhiều kiểu quản lý:

- **Transaction-scoped persistence context:** thông thường gắn với một transaction; khi context kết thúc, các entity không còn managed trong context đó.
- **Application-managed EntityManager:** context có vòng đời liên quan đến `EntityManager` mà ứng dụng tạo và đóng; trong những cấu hình resource-local thông thường, context có thể còn sống qua nhiều transaction khi `EntityManager` vẫn mở.
- **Extended persistence context:** có thể kéo dài qua nhiều transaction theo quy tắc và môi trường phù hợp.

Do đó, hãy hỏi: **“Persistence context quản lý object này còn tồn tại và còn liên kết với instance không?”**

Trong mã resource-local:

```java
EntityManager em = emf.createEntityManager();

em.getTransaction().begin();
Book book = em.find(Book.class, 42L);
em.getTransaction().commit();

// Không tự giả định book đã detached chỉ vì commit,
// nếu EntityManager/context ứng dụng vẫn còn mở.

em.close();

// Sau khi context tương ứng kết thúc, book không còn
// managed bởi EntityManager đã đóng.
```

Trong ứng dụng container-managed, không tự kéo dài EntityManager ngoài transaction hoặc tự dùng object đã trả về như managed nếu context thực tế đã kết thúc.

## 18. Rollback không đưa object Java về đúng snapshot ban đầu

Giả sử:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
String oldTitle = book.getTitle();

book.rename("Tên mới");

em.getTransaction().rollback();
```

Ở database, các thay đổi của transaction không được commit. Nhưng trong Java, `book.getTitle()` có thể vẫn là `"Tên mới"`, bởi **rollback DB không phải phép đảo ngược tự động tất cả setter đã chạy trong JVM**.

Sau lỗi transaction, trạng thái context và entity còn có thể khác nhau theo scope/provider. Cách an toàn thường là:

1. Đánh dấu transaction thất bại và rollback.
2. Không tiếp tục dùng persistence context đang ở trạng thái không tin cậy.
3. Đóng/bỏ context hoặc tạo context mới theo framework.
4. Tải lại entity từ database khi cần xử lý tiếp.
5. Không sử dụng giá trị ID vừa được sinh trong transaction thất bại như bằng chứng hàng đã được lưu.

### Vì sao không nên “retry nguyên entity cũ” vô điều kiện?

Một entity vừa `persist()` có thể đã được cấp ID trước khi rollback, dù hàng chưa từng được commit. Retry mà giữ object/graph cũ cùng giá trị ID có thể gây xung đột hoặc trạng thái không đúng theo chiến lược tạo khóa.

Nếu cần retry nghiệp vụ, hãy xác định lại input, tạo context/transaction mới và triển khai retry có chủ đích, đặc biệt khi có optimistic locking hoặc các side effect ngoài database.

## 19. Hai EntityManager và cùng một entity identity

Giả sử:

```java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    Book fromFirst = em1.find(Book.class, 42L);
    Book fromSecond = em2.find(Book.class, 42L);

    // Thông thường là hai Java objects khác nhau.
    System.out.println(fromFirst == fromSecond);

    System.out.println(em1.contains(fromFirst)); // true
    System.out.println(em2.contains(fromSecond)); // true
} finally {
    em1.close();
    em2.close();
}
```

Hai object có thể cùng đại diện hàng `books.id = 42` nhưng thuộc hai context riêng. Một object managed trong `em1` **không tự managed trong `em2`**.

Cần phân biệt:

- **Java reference identity:** `a == b`.
- **JPA persistent identity:** cùng loại entity và cùng primary key trong mapping.
- **Managed status:** object có thuộc context cụ thể không?
- **Business equality:** cách class implement `equals()/hashCode()`.

Không nên truyền một entity từ context này sang context khác rồi giả định nó tự trở thành managed. Trong service xử lý transaction mới, thường an toàn hơn khi truyền **ID hoặc DTO**, sau đó tải entity managed theo ID.

## 20. Cascading thay đổi vòng đời như thế nào?

Vòng đời entity không chỉ chịu ảnh hưởng của lệnh gọi trực tiếp. Các association có thể khai báo cascade:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
```

Nếu `Order` được persist và mapping khai báo `CascadeType.PERSIST` phù hợp, thao tác persist có thể lan truyền tới các `OrderLine` new liên quan.

Các cascade phổ biến:

| Cascade | Ngữ nghĩa chính |
| --- | --- |
| `PERSIST` | Lan truyền yêu cầu persist |
| `MERGE` | Lan truyền merge state sang association |
| `REMOVE` | Lan truyền xóa entity liên quan |
| `REFRESH` | Lan truyền refresh state |
| `DETACH` | Lan truyền detach |
| `ALL` | Tổng hợp các cascade operation chuẩn ở trên |

### Không có cascade thì không tự persist object new liên quan

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Author author;
```

và:

```java
Book book = new Book("JPA");
book.setAuthor(new Author("An"));
em.persist(book);
```

Nếu `Author` là object new và mapping không có cascade persist, JPA không được yêu cầu tự lưu Author. Khi flush, association có thể gây lỗi về unsaved transient instance hoặc foreign key.

Hướng phù hợp:

- Persist Author new tường minh trước hoặc cùng transaction, **hoặc**
- Thiết kế cascade PERSIST nếu vòng đời cho phép.

`CascadeType.PERSIST` ảnh hưởng tới chuyển trạng thái của target. Nó **không** biến `optional = true` thành tự động persist và không thay thế constraint SQL.

### Cẩn trọng với Cascade REMOVE ở entity dùng chung

Giả sử một `Book` tham chiếu `Author` mà nhiều Book khác cùng dùng. Nếu cascade REMOVE từ Book sang Author, xóa một Book có thể cố xóa Author còn được các Book khác tham chiếu.

Chọn cascade theo quan hệ sở hữu vòng đời thực sự; không chọn `CascadeType.ALL` chỉ vì “thêm vào cho đỡ lỗi persist”.

## 21. Orphan removal khác với remove trực tiếp

`orphanRemoval = true` thường dùng khi một entity con thuộc vòng đời của entity cha, chẳng hạn `OrderLine` thuộc `Order`.

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Nếu một dòng hàng persistent bị loại khỏi association theo quy tắc orphan removal, provider có thể chuyển nó sang hành vi xóa khi đồng bộ, vì dòng hàng không còn thuộc owner.

Ví dụ:

```java
order.removeLine(line);
```

Method nghiệp vụ phải đồng bộ cả collection và owning side nếu quan hệ hai hướng, theo thiết kế của entity.

Phân biệt:

- `em.remove(line)`: yêu cầu xóa entity một cách tường minh.
- `order.removeLine(line)` với `orphanRemoval = true`: có thể dẫn tới xóa entity do nó bị loại khỏi quan hệ sở hữu.
- `order.removeLine(line)` khi **không** có orphan removal: có thể chỉ gỡ association, tùy mapping và khóa ngoại có được `NULL` hay không.

Không dùng orphan removal với entity con có thể được chuyển qua owner khác mà không muốn xóa. Quy tắc về chuyển đổi/reassignment của orphan cần thiết kế rõ ràng, không dựa vào việc gỡ rồi thêm lại trong cùng flush.

## 22. Lifecycle callbacks và thời điểm xử lý

JPA hỗ trợ callback như:

- `@PrePersist`, `@PostPersist`.
- `@PreUpdate`, `@PostUpdate`.
- `@PreRemove`, `@PostRemove`.
- `@PostLoad`.

Ví dụ:

```java
@Entity
public class AuditRecord {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String content;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected AuditRecord() {}

    @PrePersist
    void beforeInsert() {
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
```

Callback tham gia vào lifecycle persistence, nhưng **không nên mặc định callback chạy đúng lúc transaction đã commit thành công**. Ví dụ, một callback có thể chạy trước hoặc trong quá trình flush, sau đó transaction vẫn có thể rollback.

Do vậy:

- Không dùng `@PostPersist` làm bằng chứng hàng đã được commit bền vững.
- Không gửi email hoặc phát event không thể rollback tùy tiện ngay trong callback.
- Không cho logic callback gây thay đổi phức tạp trên các entity khác trong context mà không hiểu giới hạn của provider/đặc tả.

Với event phải phát sau commit, cân nhắc transaction synchronization, outbox pattern hoặc cơ chế phát event phù hợp framework.

### Callback không phải định nghĩa trạng thái

Một entity không trở thành “managed” chỉ vì có `@PostLoad` và không trở thành “detached” vì một callback riêng. Trạng thái do ngữ nghĩa persistence context và thao tác EntityManager quyết định; callback chỉ là điểm mở rộng khi các sự kiện lifecycle xảy ra.

## 23. Bulk JPQL update/delete bỏ qua nhiều khía cạnh theo dõi thông thường

Giả sử một Book đã managed:

```java
Book book = em.find(Book.class, 42L);
```

Sau đó thực hiện bulk update:

```java
em.getTransaction().begin();

em.createQuery(
    "UPDATE Book b SET b.title = :title WHERE b.id = :id"
)
.setParameter("title", "Tên từ bulk update")
.setParameter("id", 42L)
.executeUpdate();

em.getTransaction().commit();
```

Bulk JPQL update thao tác trên database theo ngữ nghĩa riêng, **không tự cập nhật state của mọi managed instance đang nằm trong context**. `book.getTitle()` có thể còn giá trị cũ.

Tương tự, bulk JPQL DELETE không giống việc gọi `em.remove()` trên từng managed entity:

- Không tự áp dụng mọi callback/cascade theo cách remove từng entity.
- Có thể để lại object graph trong context không đồng bộ với database.
- Cần tự xử lý ràng buộc foreign key và quan hệ phụ thuộc phù hợp.
- Có thể cần `clear()` hoặc `refresh()` tại ranh giới hợp lý khi sử dụng cùng context.

Do đó, không nên suy rằng “bảng không còn hàng” thì mọi Java object đại diện hàng đó đã tự chuyển qua trạng thái removed.

## 24. Entity mới, detached và removed không thể phân loại chỉ bằng ID

Xét những trường hợp:

```java
Book a = new Book("A");   // new, id có thể null
Book b = em.find(Book.class, 42L); // managed nếu tồn tại
Book c = ...;             // detached, id có thể 42
```

Nếu entity dùng assigned identifier:

```java
@Id
private String code;
```

thì entity new có thể có `code != null`. Ngược lại, một detached entity đã có ID có thể tham chiếu hàng bị xóa từ bên ngoài. Entity removed vẫn có thể giữ ID trong object Java.

Vì vậy:

| Kiểm tra | Có kết luận đủ về lifecycle không? | Vì sao |
| --- | --- | --- |
| `entity.getId() == null` | Không | Assigned ID/new hoặc các chiến lược ID khác |
| `entity.getId() != null` | Không | Có thể managed, detached, removed hoặc new có assigned ID |
| `em.contains(entity)` | Chỉ xác định managed trong context | False không phân biệt mọi trạng thái còn lại |
| Có hàng DB theo ID | Không | Hàng tồn tại không quyết định object có managed không |
| `entity instanceof Book` | Không | Kiểu Java không cho biết state |
| `entity == other` | Không | Chỉ nói hai biến cùng Java object hay không |

Hãy giữ ranh giới lifecycle rõ ràng trong thiết kế service. Thay vì cố đoán trạng thái từ ID, mỗi use case nên biết input là **mã định danh**, **object mới**, hay **object detached từ lớp ngoài**.

## 25. Ví dụ thao tác hoàn chỉnh theo từng use case

Các đoạn dưới đây là ví dụ riêng biệt. Mỗi thao tác tạo context/transaction phù hợp; không nên ghép mọi đoạn dùng chung một `EntityManager` đã đóng.

### 25.1. Tạo mới

```java
public Long createBook(EntityManagerFactory emf, String title) {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = new Book(title); // NEW.
        em.persist(book);           // MANAGED.

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

`book` được persist trong transaction. Khi EntityManager được đóng, object không còn được context ấy quản lý. ID được trả về là định danh hàng đã tạo sau commit thành công, theo chiến lược ID được hỗ trợ.

### 25.2. Cập nhật một entity đang tồn tại

```java
public void renameBook(
        EntityManagerFactory emf, Long id, String title) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, id); // MANAGED nếu tìm thấy.
        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }

        book.rename(title); // Dirty checking.

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

Không gọi `persist(book)` hoặc `merge(book)` khi `book` đã managed trong transaction này. Method nghiệp vụ chỉ thay state và provider đồng bộ.

### 25.3. Xóa một entity theo ID

```java
public void deleteBook(EntityManagerFactory emf, Long id) {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, id);
        if (book != null) {
            em.remove(book); // REMOVED.
        }

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

Nếu Book có quan hệ với entity khác, xóa còn phụ thuộc cascade, foreign key, orphan removal và nghiệp vụ. Không bảo đảm delete thành công chỉ vì gọi `em.remove()` không phát exception ngay.

### 25.4. Nhận DTO thay vì merge entity detached

Với request:

```java
public record RenameBookCommand(Long id, String title) {}
```

service có thể làm:

```java
Book managed = em.find(Book.class, cmd.id());
if (managed == null) {
    throw new IllegalArgumentException("Book not found");
}
managed.rename(cmd.title());
```

Điều này thường rõ ý định hơn việc nhận một `Book` detached từ HTTP layer rồi merge toàn bộ graph. Service quyết định field nào được phép thay đổi và áp dụng validation, authorization và optimistic locking tương ứng.

## 26. Khi nào nên dùng merge thay vì find rồi sửa?

`merge()` hữu ích nếu ứng dụng thực sự có **detached graph** cần đồng bộ và đã làm rõ:

- Entity identity nào được cập nhật?
- Cascade MERGE có lan qua các association nào?
- Những field nào từ detached object được phép ghi đè?
- Dữ liệu detached có stale không và version được kiểm tra ra sao?
- Các collection có biểu diễn đầy đủ tập con hay chỉ một phần được tải?
- Object nào là managed result và object nào vẫn detached?

Nếu input chỉ là một request cập nhật vài thuộc tính, `find()` rồi gọi method nghiệp vụ thường dễ kiểm soát hơn.

Ví dụ so sánh:

| Tình huống | Cách thường đơn giản hơn |
| --- | --- |
| Tạo entity hoàn toàn mới | `persist(newEntity)` |
| Cập nhật một Book theo ID | `find()` rồi sửa managed entity |
| Đồng bộ detached graph được thiết kế rõ | `merge(detached)` và sử dụng managed result |
| Xóa Book theo ID | `find()` rồi `remove()` |
| Lấy lại state sau thay đổi ngoài context | `refresh(managed)` hoặc context mới |
| Xử lý batch nhiều entity | Chia lô `flush()/clear()` có kiểm soát |

Không có một method `save()` của JPA chuẩn cho mọi trạng thái theo nghĩa tự động quyết định mà không cần biết new/detached/managed. Các framework có thể cung cấp abstraction riêng, nhưng hiểu bản chất lifecycle giúp dự đoán chúng chọn persist hay merge.

## 27. Nhận diện lỗi theo trạng thái

### Lỗi: persist detached entity

Một object từng tải ở context khác được gọi `persist()` như entity mới.

```java
Book detached = loadBookEarlier();
em.persist(detached);
```

Provider có thể ném exception liên quan tới detached entity hoặc duplicate identity. Hướng xử lý: tải managed entity rồi sửa, hoặc dùng merge theo đúng use case.

### Lỗi: remove detached entity

```java
em.remove(detachedBook);
```

`remove()` dành cho entity managed. Hướng xử lý: tìm managed instance theo ID trong context hiện tại rồi remove.

### Lỗi: thay đổi detached entity nhưng database không đổi

```java
em.detach(book);
book.rename("Tên khác");
```

Đây chỉ là thay đổi Java object. Hướng xử lý: dùng managed instance phù hợp hoặc merge một cách có chủ đích.

### Lỗi: tưởng flush tương đương commit

```java
em.flush();
em.getTransaction().rollback();
```

SQL có thể đã chạy nhưng transaction rollback hủy thay đổi. Flush không bảo đảm dữ liệu đã durable.

### Lỗi: merge xong tiếp tục sửa instance cũ

```java
Book managed = em.merge(detached);
detached.rename("Tên mới");
```

Đối số detached không được biến thành managed. Hướng xử lý: sửa `managed` hoặc áp dụng state trước merge.

### Lỗi: clear khi còn pending changes

```java
book.rename("Tên mới");
em.clear();
```

Có thể làm mất dirty state chưa flush. Hướng xử lý: kiểm soát transaction/flush trước khi clear, không clear như lệnh refresh tùy tiện.

### Lỗi: remove entity nhưng foreign key cản trở

```java
em.remove(author);
```

Nếu `Author` còn được `Book` tham chiếu, DB có thể từ chối delete. Hướng xử lý: xác định quan hệ, chính sách cascade/xóa liên kết/chuyển chủ và constraint; không vô hiệu hóa foreign key để che giấu sai nghiệp vụ.

### Lỗi: hai context cùng sửa entity rồi mất cập nhật

Hai instance managed ở hai context khác nhau là hợp lệ; chúng có thể có state khác nhau. Hướng xử lý: `@Version`, locking/transaction isolation và chiến lược giải quyết conflict.

## 28. Bài tập thực hành

### Bài 1: Phân loại object mới

```java
Book book = new Book("ORM");
book.rename("JPA ORM");
```

**Câu hỏi:** Trạng thái của `book` là gì? Có SQL UPDATE không?

**Đáp án:** `book` là new/transient. Chỉ có thay đổi trong bộ nhớ; không có cơ chế dirty checking JPA đối với nó.

### Bài 2: Sau persist

```java
em.getTransaction().begin();
Book book = new Book("ORM");
em.persist(book);
```

**Câu hỏi:** Entity thuộc trạng thái nào? INSERT chắc chắn đã commit chưa?

**Đáp án:** Entity đã managed. INSERT và commit là hai mốc riêng; transaction chưa commit nên chưa thể khẳng định dữ liệu đã được xác nhận.

### Bài 3: Tải lại cùng ID

```java
Book a = em.find(Book.class, 42L);
Book b = em.find(Book.class, 42L);
```

**Câu hỏi:** Trong cùng context và entity tồn tại, `a == b` có ý nghĩa gì?

**Đáp án:** JPA quản lý một instance cho entity identity trong cùng context; hai biến trỏ tới cùng managed instance.

### Bài 4: Sau detach

```java
Book book = em.find(Book.class, 42L);
em.detach(book);
book.rename("Tên khác");
```

**Câu hỏi:** Thay đổi cuối có được tự động ghi xuống DB không?

**Đáp án:** Không. Object đã detached và không còn được dirty checking của context đó theo dõi.

### Bài 5: Merge

```java
Book detached = ...;
Book result = em.merge(detached);
```

**Câu hỏi:** Object nào nên được sửa tiếp trong transaction?

**Đáp án:** `result`, managed instance được trả về. Object `detached` không tự chuyển sang managed.

### Bài 6: Remove

```java
Book book = em.find(Book.class, 42L);
em.remove(book);
```

**Câu hỏi:** Hàng DB đã chắc chắn bị xóa vĩnh viễn chưa?

**Đáp án:** Chưa. Entity được đánh dấu removed; SQL DELETE có thể xảy ra khi flush và chỉ được xác nhận khi transaction commit thành công.

### Bài 7: Rollback

```java
em.getTransaction().begin();
Book book = new Book("Mới");
em.persist(book);
em.getTransaction().rollback();
```

**Câu hỏi:** Vì sao không thể coi `book.getId() != null` là bằng chứng hàng đã được lưu?

**Đáp án:** ID có thể được cấp trước rollback, trong khi transaction không commit hàng. Giá trị trong object không tự phản ánh kết quả bền vững của DB.

### Bài 8: Contains false

```java
if (!em.contains(book)) {
    em.persist(book);
}
```

**Câu hỏi:** Vì sao điều kiện trên không an toàn?

**Đáp án:** `contains` false có thể do object new, detached, removed hoặc thuộc context khác. Chọn `persist` phải dựa vào vòng đời/use case, không chỉ một boolean.

### Bài 9: Clear khi sửa nhiều entity

```java
Book a = em.find(Book.class, 1L);
Book b = em.find(Book.class, 2L);

a.rename("A mới");
b.rename("B mới");
em.clear();
```

**Câu hỏi:** Rủi ro là gì?

**Đáp án:** Cả hai object bị detach; những thay đổi chưa flush có thể không được lưu. Nếu cần giữ thay đổi, phải quản lý flush/transaction phù hợp trước khi clear.

### Bài 10: Gỡ con khỏi collection

```java
order.removeLine(line);
```

**Câu hỏi:** Điều gì quyết định `line` có bị xóa khỏi database không?

**Đáp án:** Mapping và nghiệp vụ: `orphanRemoval`, owning side của association, cascade, nullability và các quy tắc xóa. Không thể chỉ nhìn một lời gọi remove khỏi Java collection rồi kết luận.

## 29. Quy trình suy luận nhanh khi xử lý một entity JPA

Khi gặp một entity trong code, trước hết xác định:

1. **Object được tạo ở đâu?** `new` hay `find()/query/getReference()`?
2. **Đã gọi `persist()` chưa?** Nếu có, có đang trong context/transaction phù hợp không?
3. **Object có thuộc persistence context hiện tại không?** `contains()` có thể giúp xác định managed instance.
4. **Có `detach()/clear()/close()` hoặc context hết vòng đời không?**
5. **Có `merge()` không?** Đang sử dụng đối số detached hay managed result?
6. **Có `remove()` chưa?** Entity có đang chờ xóa không và transaction đã flush/commit chưa?
7. **Khóa chính được cấp lúc nào?** Đừng đồng nhất ID đã có với DB đã commit.
8. **Association có cascade hoặc orphan removal không?** Lifecycle có thể lan tới entity khác.
9. **Có bulk SQL/JPQL hoặc cập nhật từ context khác không?** State managed có thể stale.
10. **Có transaction cạnh tranh không?** Identity trong context không thay optimistic/pessimistic locking.
11. **Có rollback không?** Java object không tự đảo lại mọi thay đổi setter.
12. **Có cần thao tác từ ID/DTO thay vì entity detached không?** Nhiều use case dễ kiểm soát hơn khi tải lại managed entity.

Quy trình trên giúp phân biệt vấn đề của **state lifecycle**, **identity map**, **transaction**, **quan hệ entity** và **database constraint** trước khi sửa mã nguồn.

## Kết luận

Một entity JPA có bốn trạng thái vòng đời quan trọng: **new, managed, detached và removed**. Entity mới là Java object chưa được quản lý; entity managed được persistence context theo dõi và có thể đồng bộ thay đổi qua dirty checking; entity detached vẫn tồn tại trong bộ nhớ nhưng không còn tự được ghi cập nhật; entity removed đã được đánh dấu để xóa theo transaction.

Các phương thức `persist()`, `find()`, `merge()`, `remove()`, `detach()`, `clear()` và `refresh()` phục vụ những mục đích khác nhau. Đặc biệt, `merge()` trả về managed instance thay vì tự biến đối số detached thành managed, còn `remove()` chỉ bắt đầu quy trình xóa chứ không tương đương một `DELETE` đã commit.

Khi phân tích vòng đời, hãy đồng thời nhìn **object Java đang ở trạng thái nào**, **persistence context còn quản lý nó hay không**, **SQL đã được flush chưa** và **transaction đã commit hay rollback**. Chỉ khi tách rõ bốn câu hỏi đó, ta mới dự đoán chính xác JPA sẽ lưu, cập nhật, bỏ qua hay xóa dữ liệu như thế nào.
