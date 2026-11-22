# Thiết kế DTO không mang theo quyền quản lý của persistence context

Trong JPA, một **entity** có thể được quản lý bởi `EntityManager` thông qua **persistence context**. Khi entity ở trạng thái managed, JPA provider theo dõi các thuộc tính persistent, duy trì identity map, thực hiện dirty checking và có thể đồng bộ thay đổi xuống database tại flush/commit.

Ngược lại, **Data Transfer Object (DTO)** là đối tượng dùng để truyền tải dữ liệu giữa các tầng, giữa service và API client, hoặc giữa những đơn vị xử lý. DTO **không phải entity JPA managed** và không tự mang theo quyền được persistence context quản lý.

Ví dụ:

```java
public record BookCard(
    Long id,
    String title,
    String authorName,
    BigDecimal price
) {}
```

Một `BookCard` chứa các giá trị cần hiển thị. Đổi tên sách bằng cách tạo một `BookCard` khác không làm JPA tự gửi `UPDATE books`. Nó không được quản lý chỉ vì có một field `id` trùng với ID của `Book`.

**Mục tiêu của thiết kế DTO** không chỉ là “không trả entity ra controller”, mà còn là:

1. Định nghĩa **hợp đồng dữ liệu** rõ ràng, độc lập với ORM.
2. Chỉ mang theo những giá trị cần thiết của use case.
3. Không để lazy proxy, persistent collection hoặc managed graph thoát ra khỏi transaction.
4. Không cho consumer tưởng sửa DTO sẽ được dirty checking/flush.
5. Không nhầm DTO với detached entity rồi dùng `merge()` vô điều kiện.
6. Phân trang và query projection hiệu quả, tránh tải cả object graph không cần thiết.
7. Phân biệt thao tác **đọc dữ liệu** với **command cập nhật**.

Bài **“Thiết kế DTO không mang theo quyền quản lý của persistence context”**, thuộc chương **DTO và phân trang** trong chủ đề **Data Persistence Relational Access ORM JPA**, sẽ làm rõ cơ chế này qua entity mẫu, DTO cho trang danh sách và chi tiết, JPQL/Criteria/native SQL projection, phân trang, lazy loading, optimistic locking, API cập nhật và integration test.

Các ví dụ sử dụng Java 17+, Jakarta Persistence (`jakarta.persistence`) và đôi chỗ có Spring Data JPA được ghi chú riêng. DTO không nhất thiết phải là Java record; có thể là class bất biến hoặc class có setters tùy yêu cầu framework, miễn hợp đồng ownership và persistence semantics được giữ rõ ràng.

---

## 1. Persistence context quản lý entity nghĩa là gì?

Một `EntityManager` có persistence context, nơi JPA provider quản lý các entity instances gắn với database identity.

```java
Book book = em.find(Book.class, 42L);

book.rename("JPA chuyên sâu");

// Nếu book đang managed trong transaction hợp lệ,
// thay đổi persistent có thể được dirty checking và flush.
em.flush();
```

Một số đặc điểm của managed entity:

- JPA giữ quan hệ giữa entity type + ID và Java instance trong persistence context.
- JPA có thể theo dõi persistent changes, so sánh snapshot hoặc dùng bytecode enhancement.
- Khi flush, pending changes có thể thành `INSERT`, `UPDATE`, `DELETE`.
- Quan hệ `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany` có fetch/cascade/lifecycle semantics riêng.
- Một entity có thể giữ lazy proxy hoặc persistent collection cần context còn hoạt động.
- Các entity cùng ID thường dùng chung managed representative trong cùng persistence context.
- Sau `clear()`, `detach()` hoặc `close()`, entity có thể không còn managed nhưng vẫn là **entity instance**.

DTO **không được đăng ký vào identity map** của JPA vì nó chỉ là dữ liệu trình bày/trao đổi, không có entity mapping cần quản lý.

### Câu hỏi nền tảng

Nếu:

```java
BookCard card = new BookCard(
    42L,
    "JPA chuyên sâu",
    "Nguyễn An",
    new BigDecimal("250000")
);
```

thì `card.id() == 42L` **không** có nghĩa JPA đang quản lý `card` như Book #42. Giá trị ID trong DTO là dữ liệu, không phải quyền quản lý hoặc handle tới một row có thể tự ghi.

## 2. Phân biệt managed entity, detached entity và DTO

Ba đối tượng thường bị gộp chung vì đều có field giống nhau.

| Tiêu chí | Managed entity | Detached entity | DTO |
| --- | --- | --- | --- |
| Có mapping `@Entity`? | Có | Có | Thông thường không |
| Đang thuộc persistence context? | Có | Không | Không |
| Có JPA persistent identity? | Có | Có, dựa trên entity type/ID | Chỉ có giá trị ID nếu thiết kế DTO chứa |
| Dirty checking tự động? | Có khi context/transaction phù hợp | Không | Không |
| Có thể dùng `merge()` theo entity semantics? | Có nhưng thường không cần | Có thể, cần thận trọng | Không phải entity nên không dùng |
| Có lazy associations/proxies? | Có thể | Có thể còn proxy chưa khởi tạo | **Không nên** |
| Phù hợp trực tiếp làm JSON response? | Thường không nên | Cũng không nên mặc định | Có, khi hợp đồng API rõ |
| Có thể truyền qua transaction boundary? | Không nên phụ thuộc context bên ngoài | Có thể nhưng dễ stale/lazy error | Được thiết kế để làm việc đó |
| Thay đổi object có tự cập nhật DB? | Có thể khi dirty checking/flush | Không | Không |

Điểm khác biệt quan trọng: **detached entity vẫn là một entity JPA về kiểu và mapping; DTO thì không**.

Ví dụ:

```java
Book managed = em.find(Book.class, id);
em.detach(managed);

managed.rename("Tên ở detached object");
```

`managed` lúc này detached nhưng vẫn có annotation `@Entity` và các association của Book. Nếu ứng dụng sau đó `merge(managed)`, provider có thể copy state detached vào managed entity khác.

Ngược lại:

```java
BookCard dto = new BookCard(
    id, "Tên ở DTO", "Tác giả", price
);
```

`dto` không phải entity chỉ vì có dữ liệu giống Book. Nó không được JPA quản lý và không phải đối tượng để gọi `em.merge(dto)`.

### Không dùng DTO làm “entity detached thay tên”

Đừng thiết kế DTO như một entity sao chép toàn bộ object graph rồi mong `merge()` biến nó thành managed. Đó là hai abstraction khác nhau:

- Entity: mô hình persistence và domain lifecycle.
- DTO: hợp đồng dữ liệu cho use case/transport.

DTO có thể cố tình thiếu field, aggregate nhiều entity hoặc đổi tên field để phù hợp API; đây là lợi ích chứ không phải khiếm khuyết.

## 3. Entity mẫu Book và Author

Ta sử dụng hai entity:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Author() {}

    public Author(String name) { this.name = name; }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

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

    @Column(nullable = false)
    private boolean published;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    protected Book() {}

    public Book(String title, BigDecimal price, Author author) {
        this.title = title;
        this.price = price;
        this.author = author;
        this.published = false;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getTitle() { return title; }
    public BigDecimal getPrice() { return price; }
    public boolean isPublished() { return published; }
    public Author getAuthor() { return author; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Invalid title");
        }
        title = newTitle.trim();
    }

    public void changePrice(BigDecimal value) {
        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        price = value;
    }
}
```

Book có quan hệ tới Author và một số field như `version`, `published` có thể cần cho những use case cụ thể.

**Không phải endpoint nào cũng cần toàn bộ những field này.** Một API liệt kê 20 sách thường chỉ cần ID, title, authorName, price; một trang chi tiết có thể cần thêm version và trạng thái published.

Thiết kế DTO đúng nghĩa là chọn dữ liệu theo yêu cầu, không đưa mặc định entity đầy đủ ra ngoài.

## 4. DTO cho danh sách và DTO cho chi tiết nên khác nhau

Một DTO cho danh sách:

```java
public record BookCard(
    Long id,
    String title,
    String authorName,
    BigDecimal price
) {}
```

Một DTO cho chi tiết:

```java
public record BookDetail(
    Long id,
    String title,
    BigDecimal price,
    boolean published,
    Long version,
    AuthorSummary author
) {}

public record AuthorSummary(
    Long id,
    String name
) {}
```

Tại sao không dùng một DTO lớn cho mọi nơi?

- Danh sách cần nhiều items; mỗi field dư tăng băng thông và CPU.
- Graph chi tiết có thể có association lớn hoặc nhạy cảm.
- Fetch plan danh sách và chi tiết khác nhau.
- API contract cần ổn định dù mapping entity đổi.
- DTO nhỏ dễ tối ưu bằng SQL projection.

Sơ đồ:

```text
Database
   │
   ├── SELECT id, title, price, author_name
   │       ▼
   │     BookCard (list endpoint)
   │
   └── SELECT detailed fields / bounded associations
           ▼
         BookDetail (detail endpoint)
```

**Không để kích thước persistence graph quyết định kích thước HTTP payload.** Chính use case và contract API phải quyết định.

## 5. Vì sao trả entity trực tiếp dễ mang theo quyền quản lý?

Một controller giả định:

```java
@GetMapping("/books/{id}")
public Book findBook(@PathVariable Long id) {
    return bookService.findEntity(id);
}
```

Rủi ro:

- Entity có lazy association `author` chưa load.
- JSON serializer có thể gọi getter và kích hoạt SQL ngoài phạm vi service.
- Nếu context đóng, có thể xuất hiện lazy initialization error.
- Nếu context còn mở (Open Session in View), serialization có thể tạo N+1.
- JSON có thể vô tình chứa field nội bộ như version, audit metadata hoặc quan hệ không nên trả.
- Quan hệ hai hướng có thể tạo vòng tham chiếu.
- API schema bị ghép chặt với entity mapping.
- Consumer có thể bị lẫn lộn rằng response là một object managed.
- Refactor entity làm thay đổi API ngoài ý muốn.

DTO giải quyết ranh giới:

```java
@GetMapping("/books/{id}")
public BookDetail findBook(@PathVariable Long id) {
    return bookService.findDetail(id);
}
```

Service thực hiện query/projection và trả object không có liên kết persistence. Sau khi transaction kết thúc, client vẫn có đủ dữ liệu DTO để sử dụng.

### DTO không phải công cụ security tự động

Nếu DTO chứa email riêng tư hoặc giá nội bộ, dữ liệu vẫn có thể bị lộ. DTO giúp **chọn rõ field**, nhưng ứng dụng phải kiểm tra phân quyền, tenant và các yêu cầu bảo mật trước khi trả dữ liệu.

## 6. Dấu hiệu một DTO đang “rò rỉ” persistence context

Những cấu trúc sau trông như DTO nhưng vẫn kéo theo JPA graph:

```java
public record BadBookDto(
    Long id,
    String title,
    Author author
) {}
```

Field `author` vẫn là entity. Nếu `author` managed hoặc lazy proxy, DTO đang chứa một reference tới JPA object.

Một dạng khác:

```java
public class BadBookDto {

    private final Book book;

    public BadBookDto(Book book) {
        this.book = book;
    }

    public String getAuthorName() {
        return book.getAuthor().getName();
    }
}
```

DTO này **chưa thực sự tách khỏi persistence context**, vì getter vẫn truy cập entity lúc caller đọc. Khi context đóng, có thể phát sinh lazy exception.

Một dạng khác nữa:

```java
public record BadBookListDto(
    Long id,
    List<Review> reviews
) {}
```

`Review` là entity và `List<Review>` có thể là persistent collection wrapper hoặc chứa managed/detached entities.

### Quy tắc thiết kế

Một DTO tốt thường chỉ chứa:

- Primitive/boxed primitive.
- `String`.
- `BigDecimal`, `BigInteger` và các kiểu value immutable phù hợp.
- `LocalDate`, `Instant`, `OffsetDateTime` theo time contract.
- Enum nếu ổn định trong API, hoặc string value có chủ đích.
- Nested DTO khác, không phải entity.
- Collection của DTO/value objects đã được copy theo nhu cầu.
- IDs và version tokens khi use case cần.

**Đừng chứa EntityManager, Query, PersistenceContext, Hibernate proxy, PersistentCollection hoặc trực tiếp một entity có lazy associations bên trong DTO.**

## 7. JPQL constructor projection: tạo DTO ngay từ query

Đây là cách điển hình để trả DTO mà không phải hydrate entity Book và Author đầy đủ.

```java
List<BookCard> cards = em.createQuery(
    "SELECT NEW com.example.dto.BookCard(" +
    "b.id, b.title, a.name, b.price) " +
    "FROM Book b JOIN b.author a " +
    "WHERE b.published = true " +
    "ORDER BY b.id",
    BookCard.class
).getResultList();
```

Yêu cầu:

- `com.example.dto.BookCard` là tên class đầy đủ, thay theo package thực tế.
- Constructor có tham số tương thích với thứ tự/kiểu expression được chọn.
- Query trả một DTO cho mỗi result row.
- DTO không được JPA quản lý chỉ vì được tạo từ JPQL.
- Nếu Book có nhiều association gây row multiplication, cần thiết kế join/projection để không trả trùng DTO.

### Vì sao constructor projection có lợi?

So sánh:

```java
// Phương án dễ kéo N+1:
List<Book> books = em.createQuery(
    "SELECT b FROM Book b",
    Book.class
).getResultList();

List<BookCard> cards = books.stream()
    .map(book -> new BookCard(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName(),
        book.getPrice()
    ))
    .toList();
```

Vòng map phải truy cập Author. Nếu chưa fetch, có thể sinh N+1.

Projection:

```java
SELECT NEW ...BookCard(b.id, b.title, a.name, b.price)
FROM Book b JOIN b.author a
```

đưa chính các cột cần thiết vào query, thường tránh việc lazy-load từng Author sau đó. Nó cũng không cần Book managed identity/snapshot cho mỗi row nếu chỉ lấy scalar fields.

### Record có dùng được không?

Java record có canonical constructor; khi tham số constructor khớp result expressions và provider hỗ trợ cách gọi phù hợp, nó có thể dùng làm JPQL constructor projection. Cần kiểm thử với JPA provider/version đang dùng.

Một record thường phù hợp vì dữ liệu đầu ra đã xác định và không cần setter. Tuy nhiên, tính bất biến của record **không tự làm các object bên trong immutable**, đặc biệt với `List`, `Map` hoặc mutable date classes.

## 8. DTO được tạo qua mapper vẫn hợp lệ

Không phải mọi DTO đều cần được tạo trực tiếp bằng JPQL.

Ví dụ:

```java
Book book = em.createQuery(
    "SELECT b FROM Book b " +
    "JOIN FETCH b.author " +
    "WHERE b.id = :id",
    Book.class
).setParameter("id", id)
 .getSingleResult();

BookDetail detail = new BookDetail(
    book.getId(),
    book.getTitle(),
    book.getPrice(),
    book.isPublished(),
    book.getVersion(),
    new AuthorSummary(
        book.getAuthor().getId(),
        book.getAuthor().getName()
    )
);
```

DTO được tạo sau khi entity đã load, nhưng chỉ chứa giá trị và nested DTO. Khi đóng EntityManager, `detail` vẫn là DTO độc lập.

Cách này phù hợp khi:

- Domain logic cần managed entity trước khi tính dữ liệu.
- Mapping nhiều field phụ thuộc business methods.
- Cần reuse một aggregate đã được fetch có chủ đích.
- Query constructor expression trở nên quá phức tạp.

**Điểm quyết định không phải DTO tạo ở SQL hay Java, mà là DTO cuối cùng không giữ reference tới JPA-managed graph và mapping không gây N+1 ngoài dự kiến.**

### Mapping trước khi đóng context

Nếu mapper gọi lazy association, phải thực thi trong transaction/context còn hợp lệ với fetch plan phù hợp:

```java
BookDetail detail;

try {
    Book book = em.find(Book.class, id);
    detail = mapToDetail(book); // Trong context.
} finally {
    em.close();
}

return detail; // Không cần lazy load nữa.
```

Đừng tạo DTO chứa method lazy để sau này consumer mới gọi entity getter khi context đã đóng.

## 9. DTO không có dirty checking: ví dụ kiểm chứng

Giả sử:

```java
BookCard card = em.createQuery(
    "SELECT NEW com.example.dto.BookCard(" +
    "b.id, b.title, a.name, b.price) " +
    "FROM Book b JOIN b.author a " +
    "WHERE b.id = :id",
    BookCard.class
).setParameter("id", 42L)
 .getSingleResult();
```

Bây giờ tạo DTO khác:

```java
BookCard modified = new BookCard(
    card.id(),
    "Tên mới trên UI",
    card.authorName(),
    card.price()
);
```

Dù có transaction active, JPA không tự chạy:

```sql
UPDATE books SET title = 'Tên mới trên UI' WHERE id = 42;
```

vì `BookCard` không phải managed entity.

Tương tự, nếu dùng class mutable:

```java
public class BookEditView {
    private Long id;
    private String title;

    public void setTitle(String value) { title = value; }
}
```

thì:

```java
view.setTitle("Tên mới");
em.flush();
```

không tạo UPDATE chỉ vì object `view` có ID khớp Book. JPA chỉ dirty-check persistent entity state do context quản lý, không quét mọi Java object trong heap.

### Có thể truyền DTO cho `persist()` hay `merge()` không?

Không theo cách của entity. Các API `persist`/`merge` nhận entity instances theo semantics JPA. Truyền DTO không được mapping thành entity có thể gây `IllegalArgumentException` hoặc lỗi provider tương ứng.

Một command cập nhật phải được **áp dụng lên managed entity** bằng logic nghiệp vụ, không gửi nguyên DTO vào `em.merge()`.

## 10. Phân biệt response DTO và command DTO

Đôi khi cùng một kiểu dữ liệu bị dùng cho cả đọc và ghi, dẫn đến nhầm lẫn về ownership:

```java
public record BookDto(
    Long id,
    String title,
    BigDecimal price
) {}
```

Nếu vừa trả từ GET vừa nhận trong PUT, các câu hỏi khó xuất hiện:

- Có được cho client sửa ID không?
- Version có được kiểm tra không?
- Client có quyền thay đổi giá hay chỉ title?
- Field vắng mặt có nghĩa “giữ nguyên” hay “xóa”?
- Có phải mọi field trong response đều được phép ghi?
- Entity có domain invariants cần kiểm tra không?

Thường nên tách:

```java
public record BookDetail(
    Long id,
    String title,
    BigDecimal price,
    boolean published,
    Long version
) {}

public record ChangeBookTitleCommand(
    String newTitle,
    Long expectedVersion
) {}
```

Đây là hai hợp đồng khác nhau:

- **Response DTO:** dữ liệu đã đọc để trình bày.
- **Command DTO:** ý định cập nhật với những field được phép.

Không cần sao chép toàn entity vào command. Một field ID thường nằm trong route/command identity, còn các field cần thay đổi được validate rõ.

## 11. Cập nhật an toàn bằng command và managed entity

Một resource-local JPA service:

```java
public void renameBook(
        EntityManagerFactory emf,
        Long bookId,
        ChangeBookTitleCommand command) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, bookId);

        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }

        if (!Objects.equals(
                book.getVersion(), command.expectedVersion())) {
            throw new OptimisticLockException(
                "Book version changed"
            );
        }

        book.rename(command.newTitle());

        em.getTransaction().commit();
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
```

Ý nghĩa:

1. Nhận command thuần dữ liệu.
2. Mở transaction/context.
3. Tải **managed Book** theo ID.
4. Kiểm tra version nghiệp vụ nếu client gửi version.
5. Gọi domain method `rename` với validation.
6. JPA dirty checking/`@Version` xử lý trong transaction.
7. Không dùng `merge()` trên DTO.
8. Kết thúc context sau transaction.

### Version của DTO không tạo optimistic locking tự động

`BookDetail.version()` là **giá trị**. Khi client gửi lại version, ứng dụng phải dùng nó để kiểm tra hoặc thực thi conditional update.

`@Version` trên entity giúp JPA phát hiện concurrent modifications khi provider thực hiện managed update. Nhưng version nằm trong DTO không tự mang quyền quản lý persistence context.

### Vì sao phải kiểm tra lại version khi commit?

Hai transaction có thể đọc cùng version. Việc so sánh version trong Java là kiểm tra sớm, nhưng **không thay thế** optimistic locking ở database do JPA `@Version` hoặc atomic conditional SQL thực hiện. Một transaction khác có thể commit sau lúc ta so sánh và trước lúc transaction hiện tại flush.

Do đó vẫn phải xử lý `OptimisticLockException` hoặc lỗi tương ứng khi flush/commit.

## 12. Tránh overposting/mass assignment

Một anti-pattern:

```java
public void update(BookUpdateDto input) {
    Book book = em.find(Book.class, input.id());

    book.setTitle(input.title());
    book.setPrice(input.price());
    book.setPublished(input.published());
    book.setOwnerId(input.ownerId());
}
```

Nếu endpoint chỉ cho phép đổi title mà DTO lại chứa price/published/ownerId, ứng dụng dễ cho client thay đổi dữ liệu không được phép.

Tách command theo use case:

```java
public record RenameBookCommand(String title) {}
public record ChangePriceCommand(BigDecimal newPrice) {}
public record PublishBookCommand() {}
```

Các command đi qua service methods kiểm tra quyền và invariants riêng.

**DTO không managed là một ranh giới thuận lợi để kiểm soát update intent**, nhưng chỉ an toàn nếu không tự động copy mọi field vào managed entity.

## 13. Nested DTO: copy giá trị, không copy reference entity

Sai:

```java
public record OrderDto(
    Long id,
    Customer customer,
    List<OrderLine> lines
) {}
```

`Customer` và `OrderLine` có thể là entities, `lines` có thể là persistent collection. DTO vẫn phụ thuộc persistence lifecycle và có thể tạo lazy-loading khi serialize.

Đúng hơn:

```java
public record CustomerSummary(
    Long id,
    String displayName
) {}

public record OrderLineDto(
    Long id,
    String productName,
    int quantity
) {}

public record OrderDetail(
    Long id,
    CustomerSummary customer,
    List<OrderLineDto> lines
) {
    public OrderDetail {
        lines = List.copyOf(lines);
    }
}
```

Một constructor mapper:

```java
OrderDetail detail = new OrderDetail(
    order.getId(),
    new CustomerSummary(
        order.getCustomer().getId(),
        order.getCustomer().getDisplayName()
    ),
    order.getLines().stream()
        .map(line -> new OrderLineDto(
            line.getId(),
            line.getProduct().getName(),
            line.getQuantity()
        ))
        .toList()
);
```

Mapping này **phải được chạy trong scope có fetch plan phù hợp**, vì `order.getLines()` và `line.getProduct()` có thể phát SQL/N+1. DTO cuối cùng không mang entity, nhưng quá trình tạo DTO vẫn có thể tốn nhiều truy vấn nếu viết thiếu chủ đích.

### Tính bất biến sâu

`List.copyOf(lines)` ngăn sửa cấu trúc list đã lưu trong record, nhưng không làm các phần tử mutable trở thành immutable. Ở ví dụ này, `OrderLineDto` là record chứa các value types nên khá an toàn. Nếu nested DTO là class mutable hoặc có `Date`, `byte[]`, cần defensive copy phù hợp.

## 14. DTO và phân trang: chỉ lấy page cần thiết

Một endpoint danh sách thường trả:

```java
public record PageDto<T>(
    List<T> items,
    long totalElements,
    int page,
    int size
) {
    public PageDto {
        items = List.copyOf(items);
    }
}
```

Query page bằng JPQL projection:

```java
public PageDto<BookCard> findBookCards(
        EntityManager em,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid pagination");
    }

    int offset = Math.multiplyExact(page, size);

    List<BookCard> cards = em.createQuery(
        "SELECT NEW com.example.dto.BookCard(" +
        "b.id, b.title, a.name, b.price) " +
        "FROM Book b JOIN b.author a " +
        "ORDER BY b.id",
        BookCard.class
    ).setFirstResult(offset)
     .setMaxResults(size)
     .getResultList();

    Long total = em.createQuery(
        "SELECT COUNT(b) FROM Book b",
        Long.class
    ).getSingleResult();

    return new PageDto<>(
        cards,
        total,
        page,
        size
    );
}
```

Đây là ví dụ cơ bản. Nếu query page có WHERE filter, count query **phải áp dụng cùng điều kiện logic** để tổng số phản ánh tập dữ liệu đang phân trang.

### Vì sao cần giới hạn size?

Nếu client gửi `size = 1_000_000`, query có thể tải lượng dữ liệu khổng lồ vào RAM, dù dùng DTO. API cần đặt giới hạn page size theo use case.

### Thứ tự ổn định

`ORDER BY b.id` đảm bảo một key order rõ ràng trong ví dụ. Với sort theo title, nên thêm ID tiebreaker để tránh thứ tự không ổn định khi title trùng:

```sql
ORDER BY b.title ASC, b.id ASC
```

Còn nếu dữ liệu thay đổi giữa các page requests, offset pagination vẫn có nguy cơ lặp/bỏ sót rows; cần keyset pagination hoặc consistency policy nếu nghiệp vụ đòi hỏi.

## 15. DTO giúp tránh vấn đề fetch collection + pagination

Giả sử Book có 100 Reviews. Nếu query:

```java
SELECT b FROM Book b LEFT JOIN FETCH b.reviews
```

và đặt `setMaxResults(20)`, collection fetch join có thể nhân bản SQL rows và khiến phân trang root Book khó tối ưu.

Nếu danh sách chỉ cần:

```text
Book ID + title + reviewCount
```

hãy dùng DTO aggregate projection:

```java
public record BookReviewCard(
    Long id,
    String title,
    Long reviewCount
) {}
```

```java
List<BookReviewCard> cards = em.createQuery(
    "SELECT NEW com.example.dto.BookReviewCard(" +
    "b.id, b.title, COUNT(r)) " +
    "FROM Book b LEFT JOIN b.reviews r " +
    "GROUP BY b.id, b.title " +
    "ORDER BY b.id",
    BookReviewCard.class
).setFirstResult(offset)
 .setMaxResults(size)
 .getResultList();
```

Query chỉ cần kết quả aggregate mỗi Book, không cần tải toàn bộ Reviews.

Cần kiểm tra SQL trên DB/provider thật, đặc biệt grouping, pagination và dataset lớn. Khi có nhiều association collections hoặc quyền lọc phức tạp, có thể cần hai query hoặc subquery để tránh duplicate/count distortion.

**Không bắt buộc biến mọi graph relation thành nested DTO nếu UI chỉ cần số liệu tổng hợp.**

## 16. Khi DTO có nested collections: pagination hai giai đoạn

Trang chi tiết danh sách có thể cần mỗi Book kèm top Reviews. JPQL constructor projection đơn giản không tự tạo List<ReviewDto> cho từng Book từ nhiều SQL rows.

Một chiến lược:

1. Query trang Book IDs và các scalar fields.
2. Query Reviews cho tất cả Book IDs trong trang **một lần theo batch**.
3. Chuyển từng Review thành ReviewDto.
4. Group theo Book ID.
5. Gắn các list vào Book DTO theo đúng thứ tự page.
6. Trả DTO hoàn chỉnh, không giữ JPA entities/collections.

Ví dụ ý tưởng:

```java
List<Long> bookIds = em.createQuery(
    "SELECT b.id FROM Book b ORDER BY b.id",
    Long.class
).setFirstResult(offset)
 .setMaxResults(size)
 .getResultList();

List<ReviewRow> reviewRows = bookIds.isEmpty()
    ? List.of()
    : em.createQuery(
        "SELECT NEW com.example.dto.ReviewRow(" +
        "r.book.id, r.id, r.rating) " +
        "FROM Review r WHERE r.book.id IN :ids",
        ReviewRow.class
    ).setParameter("ids", bookIds)
     .getResultList();
```

Record:

```java
public record ReviewRow(
    Long bookId,
    Long reviewId,
    int rating
) {}
```

Group:

```java
Map<Long, List<ReviewRow>> byBook = reviewRows.stream()
    .collect(Collectors.groupingBy(ReviewRow::bookId));
```

Tạo nested DTO từ IDs và các scalar/BookCard rows đã query. Trong code production, cần chỉ rõ thứ tự reviews, giới hạn số reviews mỗi Book nếu có và xử lý Book không có Review bằng list rỗng.

### Vì sao cách này tránh N+1?

Thay vì mỗi Book có một query lấy Reviews, ta thực hiện **một query cho cả tập Book IDs của page**. Số round trips thường phụ thuộc số batch, không tăng một theo từng Book.

### Các giới hạn cần xét

- DB có giới hạn số phần tử `IN` hoặc bind parameters.
- Page size lớn có thể cần chia batch.
- Một Book có quá nhiều Reviews vẫn làm dữ liệu lớn.
- Query giữa hai bước có thể nhìn những snapshot khác nhau nếu transaction khác cập nhật.
- Muốn đảm bảo page là một snapshot nhất quán có thể cần transaction isolation/consistency riêng.

DTO giúp biểu diễn kết quả, nhưng không tự đảm bảo nhất quán transaction.

## 17. DTO với Criteria API

JPA Criteria API cũng hỗ trợ constructor projection:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<BookCard> cq =
    cb.createQuery(BookCard.class);

Root<Book> book = cq.from(Book.class);
Join<Book, Author> author =
    book.join("author", JoinType.INNER);

cq.select(cb.construct(
    BookCard.class,
    book.get("id"),
    book.get("title"),
    author.get("name"),
    book.get("price")
));

cq.orderBy(cb.asc(book.get("id")));

List<BookCard> cards = em.createQuery(cq)
    .setFirstResult(offset)
    .setMaxResults(size)
    .getResultList();
```

Ở đây:

- `CriteriaBuilder` tạo constructor expression.
- `CriteriaQuery<BookCard>` khai báo kiểu kết quả.
- `Root<Book>` xác định nguồn Book.
- `Join<Book,Author>` lấy authorName.
- `BookCard` nhận giá trị qua constructor, không thành managed entity.

Các lỗi tên thuộc tính dùng chuỗi như `"titel"` có thể chỉ xuất hiện runtime. Static metamodel có thể tăng type safety, nhưng không thay đổi bản chất DTO không managed.

## 18. Native SQL và DTO: không giữ `Object[]` làm API contract

Với native SQL:

```java
List<?> rows = em.createNativeQuery(
    "SELECT b.id, b.title, a.name, b.price " +
    "FROM books b JOIN authors a ON a.id = b.author_id " +
    "ORDER BY b.id"
).setFirstResult(offset)
 .setMaxResults(size)
 .getResultList();
```

Mỗi row nhiều cột thường là `Object[]`. Nên map ngay tại repository:

```java
List<BookCard> cards = rows.stream()
    .map(raw -> {
        if (!(raw instanceof Object[] cols) || cols.length != 4) {
            throw new IllegalStateException("Unexpected native row");
        }

        Long id = toLongExact(cols[0]);
        String title = (String) cols[1];
        String authorName = (String) cols[2];
        BigDecimal price = toBigDecimal(cols[3]);

        return new BookCard(id, title, authorName, price);
    })
    .toList();
```

`toLongExact` và `toBigDecimal` là helper do ứng dụng định nghĩa; cần xử lý kiểu Number/BigInteger/BigDecimal theo driver mà không truncate số tiền. Không nên luôn cast native BIGINT sang `Long` vì JDBC/provider có thể trả kiểu Number khác.

Một lựa chọn khác là `@SqlResultSetMapping` với `@ConstructorResult` để provider tạo DTO theo alias/constructor mapping. Dù dùng cách nào, **DTO cuối cùng vẫn là value projection, không được JPA dirty checking**.

### Native mapping trực tiếp vào entity khác DTO

`em.createNativeQuery(sql, Book.class)` có thể tạo/trả Book entity managed theo mapping; đây **không phải DTO projection**. Không dùng resultClass entity chỉ vì muốn tránh ép `Object[]` nếu mục tiêu là trả dữ liệu nhỏ và không mang ORM lifecycle.

## 19. Spring Data JPA interface projection: phân biệt proxy của framework và JPA entity

Spring Data JPA có interface projection như:

```java
public interface BookCardView {
    Long getId();
    String getTitle();
    BigDecimal getPrice();
}
```

Repository:

```java
public interface BookRepository
        extends JpaRepository<Book, Long> {

    List<BookCardView> findByPublishedTrue();
}
```

Đây là **khả năng của Spring Data JPA**, không phải đối tượng `BookCardView` managed JPA entity. Framework có thể dùng proxy/projection objects để đọc dữ liệu.

Tuy nhiên:

- Closed interface projection có thể giúp giới hạn selected fields tùy query và framework.
- Open projection với expression/SpEL hoặc nested projection có thể khiến framework materialize nhiều dữ liệu hơn, thậm chí truy cập association.
- Không tự giả định mọi projection đều tạo SQL chỉ chọn đúng các cột hiển thị.
- Nếu nested projection trả một entity reference hoặc lazy object, DTO contract vẫn cần kiểm tra.

**Phân biệt proxy cho projection của Spring và lazy proxy của entity JPA.** Một projection interface có getter không đồng nghĩa nó trở thành entity managed.

Khi yêu cầu kiểm soát SQL chặt, class/record constructor projection thường minh bạch hơn.

## 20. DTO và việc cập nhật từ response

Một lỗi phổ biến:

```java
BookDetail detail = service.findDetail(id);

BookDetail changed = new BookDetail(
    detail.id(),
    "Tên được chỉnh trên UI",
    detail.price(),
    detail.published(),
    detail.version(),
    detail.author()
);

// Không có SQL UPDATE tự động.
```

Để lưu, caller cần gửi một command:

```java
ChangeBookTitleCommand command =
    new ChangeBookTitleCommand(
        changed.title(),
        changed.version()
    );

service.renameBook(id, command);
```

Service phải:

- Kiểm tra quyền thay đổi Book.
- Kiểm tra entity tồn tại trong tenant/scope phù hợp.
- Validate title.
- Kiểm tra optimistic version nếu yêu cầu.
- Gọi domain method trên managed Book.
- Commit transaction.
- Trả response DTO mới nếu API cần.

**DTO là dữ liệu đầu vào/đầu ra, không phải phương tiện điều khiển persistence context từ xa.**

## 21. Có nên cho DTO giữ entity ID không?

Có, khi ID là một phần hữu ích của contract:

```java
public record BookCard(Long id, String title) {}
```

Nhưng:

- ID không làm DTO managed.
- ID không chứng minh entity còn tồn tại; dữ liệu có thể đã bị xóa.
- ID có thể thuộc tenant khác, cần authorization ở service.
- ID có thể là khóa nội bộ không nên công khai trong một số API; có thể dùng external identifier.
- Gửi ID từ client không có nghĩa client được sửa/xóa row đó.
- Version token có thể đã stale.

Cần phân biệt **định danh dữ liệu** với **quyền truy cập và quyền sửa dữ liệu**.

Không nên dùng DTO ID để bỏ qua domain validation:

```java
em.createQuery(
    "UPDATE Book b SET b.price = :price WHERE b.id = :id"
).setParameter("price", input.price())
 .setParameter("id", input.id())
 .executeUpdate();
```

nếu use case cần owner/tenant check, optimistic locking, auditing và domain invariants. Bulk update có semantics khác managed entity update và không tự gọi mọi entity callback.

## 22. DTO và optimistic locking khi client cập nhật

Client có thể đọc:

```json
{
  "id": 42,
  "title": "JPA cơ bản",
  "version": 3
}
```

Sau đó hai người dùng cùng chỉnh sửa:

```text
User A đọc version 3 ── đổi title ── commit version 4
User B đọc version 3 ── đổi title ── xung đột
```

DTO chứa version 3 của B không tự chặn ghi đè. Service cần kiểm tra version và dựa vào `@Version`/conditional update thực sự để phát hiện conflict.

Ví dụ command:

```java
public record RenameBookCommand(
    String title,
    Long expectedVersion
) {}
```

Server tải managed Book, so sánh version theo contract API và commit. Nếu có concurrent transaction giữa check và flush, `@Version` là lớp bảo vệ cần thiết.

Nếu ứng dụng dùng HTTP ETag/If-Match, version có thể được mã hóa thành token thay vì field JSON; đây là thiết kế API khác nhưng cùng mục đích tránh lost updates.

## 23. DTO không mang các tác động lifecycle/cascade

Một entity `PurchaseOrder` có `@OneToMany(cascade = ALL, orphanRemoval = true)` tới OrderLine. Nếu DTO chứa:

```java
public record OrderDetail(
    Long id,
    List<OrderLineDto> lines
) {}
```

và người dùng xóa một line khỏi list DTO, JPA **không tự chạy orphanRemoval**.

Chỉ khi service chuyển ý định gỡ line thành thao tác trên **managed association**:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

OrderLine line = findLineOwnedBy(order, lineId);

order.removeLine(line);
```

và mapping/transaction phù hợp, orphan removal mới có thể được áp dụng.

**Mọi cascade, dirty checking và orphan removal thuộc entity graph được quản lý, không thuộc nested DTO graph.**

Điều này giúp DTO không gây tác dụng phụ khi API client chỉ chỉnh một bản nháp hoặc bộ lọc trên màn hình.

## 24. DTO không nên chứa PersistentCollection

Anti-pattern:

```java
public record BadOrderDto(
    Long id,
    List<OrderLine> lines
) {}

return new BadOrderDto(order.getId(), order.getLines());
```

`order.getLines()` có thể là một wrapper quản lý lazy collection, hoặc list chứa entity managed/detached. Khi context đóng, caller có thể gặp lazy-loading issue; khi context còn mở, serialization có thể query thêm.

Tạo list DTO:

```java
List<OrderLineDto> lineDtos = order.getLines().stream()
    .map(line -> new OrderLineDto(
        line.getId(),
        line.getProduct().getName(),
        line.getQuantity()
    ))
    .toList();

return new OrderDetail(
    order.getId(),
    lineDtos
);
```

Kết quả `List.copyOf(...)` trong canonical constructor của `OrderDetail` tạo một bản list độc lập với persistent collection.

Lưu ý: Việc đọc `getProduct().getName()` có thể gây N+1 nếu fetch plan không phù hợp. Thiết kế DTO và thiết kế query/fetch plan phải đi cùng nhau.

## 25. DTO và vòng đời transaction

Một service thường có ranh giới:

```text
HTTP request
     │
     ▼
Service transaction
     │
     ├── query entity / projection
     ├── map to DTO
     ├── close stream/query resources nếu có
     └── commit/rollback
     │
     ▼
DTO không phụ thuộc context
     │
     ▼
HTTP serializer → JSON
```

Mục tiêu là serializer chỉ đọc dữ liệu sẵn có, không phải khởi tạo lazy associations.

### Khi dùng DTO projection trực tiếp

```java
public BookCard findCard(EntityManager em, Long id) {
    return em.createQuery(
        "SELECT NEW com.example.dto.BookCard(" +
        "b.id, b.title, a.name, b.price) " +
        "FROM Book b JOIN b.author a " +
        "WHERE b.id = :id",
        BookCard.class
    ).setParameter("id", id)
     .getSingleResult();
}
```

Phương thức trả DTO đã có đầy đủ scalar fields, không giữ managed Book.

### Khi dùng entity mapper

Phải map trong lúc context còn mở:

```java
Book book = em.find(Book.class, id);

BookCard dto = mapToCard(book);

// Sau khi map xong, có thể kết thúc context.
```

Nếu mapper cần associations chưa được tải, hãy chọn fetch plan hoặc projection trước, không chỉ kéo dài transaction để né lỗi.

## 26. Spring @Transactional: return DTO thay vì live entity graph

Ví dụ:

```java
@Service
public class BookReadService {

    private final BookRepository repository;

    public BookReadService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BookCard findCard(Long id) {
        return repository.findCardById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Book not found")
            );
    }
}
```

Trong ví dụ này, `repository.findCardById` giả định là method projection query trả `Optional<BookCard>`. Annotation Spring là framework feature, không phải JPA chuẩn.

`readOnly = true` có thể giúp mô tả mục đích đọc và provider-specific optimization; nó **không phải bảo đảm mọi query được tự chuyển thành DTO hoặc mọi entity bên trong transaction không thể bị sửa**.

Điều quan trọng là service trả một DTO đã hoàn chỉnh. Transaction kết thúc không ảnh hưởng việc đọc các record fields sau đó.

## 27. DTO và vấn đề lazy initialization

Lỗi:

```java
Book book = em.find(Book.class, id);
em.close();

String author = book.getAuthor().getName();
```

Có thể thất bại khi `author` chưa được khởi tạo. Nhưng nếu service tạo DTO trong transaction:

```java
BookCard card = new BookCard(
    book.getId(),
    book.getTitle(),
    book.getAuthor().getName(),
    book.getPrice()
);

em.close();

String authorName = card.authorName();
```

thì `card.authorName()` chỉ đọc String, không cần connection/session.

Cần phân biệt:

- **Detached entity:** có thể còn lazy proxy chưa initialized.
- **DTO:** phải giữ dữ liệu đã được chuyển thành values, không mang proxy.

Một DTO có field `Supplier<String> authorNameSupplier` mà lambda bên trong đọc `book.getAuthor().getName()` cũng là cách rò rỉ dependency, dù field có vẻ không phải entity. Tránh delayed callbacks giữ reference tới managed graph.

## 28. DTO như snapshot, không phải dữ liệu sống

DTO thường là **snapshot tại thời điểm query/map**:

```java
BookCard card = service.findCard(42L);
```

Nếu sau đó transaction khác cập nhật Book #42, `card.title()` không tự đổi. Đây là hành vi **mong muốn**: DTO không phải live view đồng bộ với database.

Điều này có hai hệ quả:

1. DTO có thể stale nếu được giữ trong cache/client lâu.
2. Cập nhật dựa trên DTO phải kiểm tra concurrency/version nếu dữ liệu có thể đổi.

### DTO không cần gọi refresh

`em.refresh(card)` không hợp lệ vì `card` không phải managed entity. Muốn có dữ liệu mới, thực hiện query/projection lại:

```java
BookCard latest = service.findCard(42L);
```

Đây cũng là lý do DTO phù hợp với các layer không nên giữ persistence context: consumer biết nó đang làm việc với một bản dữ liệu tại thời điểm đọc.

## 29. DTO cache khác ORM second-level cache

Nếu ứng dụng cache `BookCard`:

```java
Map<Long, BookCard> cache;
```

thì đó là **application-level DTO cache**, không tự đồng bộ theo JPA second-level cache hay dirty checking. Khi Book thay đổi, ứng dụng cần invalidation/TTL/event strategy riêng.

Ưu điểm của cache DTO:

- Không giữ managed entity, lazy proxy hoặc persistence collection.
- Serialization dễ hơn.
- Không mang transaction context ra khỏi service.

Rủi ro:

- DTO có thể stale.
- DTO chứa thông tin cá nhân có thể cần expiry/xóa theo policy.
- DTO version cần được kiểm tra khi dùng làm update input.
- Cache key phải bao gồm tenant/authorization context nếu dữ liệu phụ thuộc quyền.

Không lầm tưởng DTO “không managed” nghĩa là dữ liệu của nó luôn mới. Nó chỉ không có những tác dụng phụ persistence lifecycle.

## 30. DTO và phân quyền đa tenant

Một response:

```java
public record BookCard(
    Long id,
    String title,
    String authorName,
    BigDecimal price
) {}
```

có thể chỉ được phép trả cho tenant sở hữu Book. Vì DTO không chứa JPA context, nó cũng **không tự mang tenant filter**.

Repository/service phải áp dụng điều kiện:

```java
"SELECT NEW com.example.dto.BookCard(" +
"b.id, b.title, a.name, b.price) " +
"FROM Book b JOIN b.author a " +
"WHERE b.tenant.id = :tenantId " +
"ORDER BY b.id"
```

Đây là ví dụ giả định Book có quan hệ `tenant`. Nếu model dùng field `tenantId` thay vì association, query đổi tương ứng.

Quan trọng:

- Tenant ID phải lấy từ security context đáng tin, không tin trực tiếp input client nếu không được kiểm chứng.
- Count query cho pagination phải có cùng tenant filter.
- API không nên lộ field không được phép chỉ vì entity/DTO có sẵn.
- Update command phải kiểm tra ownership khi nạp managed entity.

**Projection DTO làm rõ trường dữ liệu được trả, nhưng authorization vẫn phải bảo vệ cả danh sách, chi tiết và thao tác ghi.**

## 31. DTO và thời gian/tiền tệ

Khi xây DTO, chọn kiểu value rõ:

```java
public record BookPriceDto(
    Long id,
    BigDecimal amount,
    String currencyCode,
    Instant lastUpdatedAt
) {}
```

Lý do:

- `BigDecimal` phù hợp giá trị thập phân chính xác hơn `double` trong nhiều nghiệp vụ tiền tệ.
- `currencyCode` làm rõ đơn vị, tránh trộn nhiều đồng tiền.
- `Instant` thể hiện mốc thời gian tuyệt đối, phù hợp hệ thống nhiều múi giờ.
- Không trả `java.sql.Timestamp` hoặc driver-specific object trực tiếp nếu API có thể dùng type ổn định hơn.
- Khi dùng record/immutable value objects, DTO ít có khả năng bị sửa ngoài dự kiến.

Nhưng conversion từ database native query có thể trả `BigInteger`, `BigDecimal` hoặc `Timestamp` theo driver/provider. Phải map đúng contract ở repository trước khi tạo DTO.

Nếu DTO dùng mutable `Date` hoặc `byte[]`, cần defensive copy để thực sự không chia sẻ mutable state ngoài ý muốn.

## 32. Một DTO có nhiều field không có nghĩa được cấp quyền ghi nhiều field

Xét:

```java
public record BookDetail(
    Long id,
    String title,
    BigDecimal price,
    boolean published,
    Long version,
    AuthorSummary author
) {}
```

Response cung cấp `price` để xem; không có nghĩa client được gửi một request sửa giá nếu role không cho phép.

Tương tự, AuthorSummary có ID/name; client không vì vậy mà được thay tác giả của Book hoặc cập nhật Author record.

Do đó, service write phải có **allowlist field theo use case**, không copy mọi field đã xuất hiện trong response DTO vào entity.

Một số ứng dụng dùng JSON Patch/merge patch; kể cả khi cần partial update, hãy map patch vào command validated và áp dụng với domain rules, thay vì reflection copy vào entity.

## 33. Bài toán null và field vắng mặt trong DTO ghi

Ví dụ:

```java
public record UpdateBookRequest(
    String title,
    BigDecimal price
) {}
```

Nếu `title == null`, có hai ý nghĩa khả dĩ:

- Client không muốn cập nhật title.
- Client muốn xóa title (nếu field nullable).

Record này không phân biệt được **field absent** với **field present = null** khi JSON binding không có convention rõ.

Giải pháp tùy API:

- Dùng command cụ thể như `RenameBookCommand`, field bắt buộc.
- Dùng các wrapper biểu diễn presence rõ.
- Theo PATCH semantics có hỗ trợ tri-state.
- Dùng endpoint PUT yêu cầu toàn bộ state hợp lệ nếu business contract phù hợp.

Không tự chuyển mọi null từ DTO thành setter `entity.setField(null)`, vì có thể làm mất dữ liệu.

Một response DTO có null vì thiếu giá trị DB là chuyện khác với command muốn xóa dữ liệu.

## 34. Không tái sử dụng DTO từ transaction lỗi như managed state

Khi một transaction bị rollback:

```java
Book book = em.find(Book.class, id);
book.rename("Tên mới");
em.getTransaction().rollback();
```

Object `book` có thể vẫn giữ title mới trong heap, dù database đã hoàn tác thay đổi. Nếu tạo DTO từ object đó sau rollback:

```java
BookCard dto = mapToCard(book);
```

DTO cũng có thể chứa dữ liệu **không được commit**.

DTO không managed, nhưng điều đó **không bảo đảm nguồn giá trị của nó đã commit**. Vấn đề là bạn map ở thời điểm nào và từ nguồn dữ liệu nào.

Cách đáng tin sau rollback là kết thúc context thất bại, đọc lại dữ liệu trong context mới rồi tạo DTO.

Nếu cần giữ input người dùng đã nhập sau lỗi, hãy giữ **command/form DTO**, không dựa vào entity từ transaction đã rollback để làm nguồn dữ liệu đã lưu.

## 35. DTO không tự giải quyết N+1 trong mapper

Code:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b",
    Book.class
).getResultList();

List<BookCard> cards = books.stream()
    .map(book -> new BookCard(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName(),
        book.getPrice()
    ))
    .toList();
```

Có thể tạo N+1 nếu mỗi Author được lazy load riêng. DTO cuối cùng đúng abstraction, nhưng **quá trình tạo DTO không hiệu quả**.

Hai hướng:

**Projection trực tiếp:**

```java
SELECT NEW ...BookCard(b.id, b.title, a.name, b.price)
FROM Book b JOIN b.author a
```

**Hoặc fetch plan rõ trước khi map:**

```java
SELECT b FROM Book b JOIN FETCH b.author
```

Sau đó map trong transaction. Chọn theo việc nghiệp vụ có cần managed entity hay chỉ cần scalar values.

Nếu DTO có collection, tránh một query collection theo từng Book. Dùng aggregate, batch query theo IDs hoặc pagination hai giai đoạn.

## 36. DTO và performance: không chỉ số entity ít hơn

Một DTO projection thường có thể giảm:

- Số field truyền từ DB.
- Số entity objects được hydrate.
- Chi phí dirty checking/snapshot của persistence context.
- Số lazy association traversals.
- Dữ liệu JSON trả client.

Nhưng không tự bảo đảm:

- SQL luôn dùng index tốt.
- Query join luôn một row trên mỗi Book.
- Không có N+1 ở nested DTO query.
- Pagination luôn ổn định.
- Cache invalidation chính xác.
- Response không lộ dữ liệu nhạy cảm.

Ví dụ một DTO projection có:

```java
SELECT NEW ...BookCard(...)
FROM Book b
JOIN b.author a
JOIN b.reviews r
```

có thể tạo duplicate Book rows nếu một Book có nhiều Reviews. Khi cần một DTO mỗi Book, hãy xác định đúng cardinality, aggregation, DISTINCT hoặc query strategy.

**DTO giúp giới hạn graph; query shape quyết định chi phí thực tế.**

## 37. DTO vs Java Map và Object[]

Có thể dùng `Map<String,Object>` hoặc `Object[]` làm kết quả repository:

```java
Object[] row = (Object[]) nativeQuery.getSingleResult();
```

Nhưng khi truyền sâu vào service/controller:

- Ý nghĩa `row[2]` không rõ.
- Dễ cast sai numeric types.
- Dễ lệch thứ tự cột khi SQL đổi.
- Nullability không được diễn đạt rõ.
- API contract khó phát hiện sai lúc compile.

Một DTO:

```java
public record BookCard(
    Long id,
    String title,
    String authorName,
    BigDecimal price
) {}
```

có tên field và kiểu ổn định hơn. Mapping từ native `Object[]` nên xảy ra tại repository, cùng kiểm tra số cột, null và conversion.

Nhưng nếu một query ngắn dùng nội bộ để lấy `COUNT(*)`, trả `long` trực tiếp cũng có thể đủ; không cần tạo DTO cho mọi scalar query.

## 38. Unit test kiểm tra DTO độc lập với entity

Một test thuần Java:

```java
@Test
void dtoIsJustValuesNotLiveEntity() {
    BookCard before = new BookCard(
        42L,
        "Tên cũ",
        "Tác giả A",
        new BigDecimal("100000")
    );

    BookCard after = new BookCard(
        before.id(),
        "Tên mới",
        before.authorName(),
        before.price()
    );

    assertEquals("Tên cũ", before.title());
    assertEquals("Tên mới", after.title());
}
```

Test này minh họa value semantics của record, **chưa chứng minh JPA không phát SQL**. Để kiểm tra persistence isolation, cần integration test với EntityManager.

## 39. Integration test: đọc DTO không tạo managed Book

Một ví dụ khái niệm:

```java
@Test
void projectionReturnsDtoWithoutManagedBookGraph() {
    Long id = seededBookId;

    EntityManager em = emf.createEntityManager();

    try {
        BookCard dto = em.createQuery(
            "SELECT NEW com.example.dto.BookCard(" +
            "b.id, b.title, a.name, b.price) " +
            "FROM Book b JOIN b.author a " +
            "WHERE b.id = :id",
            BookCard.class
        ).setParameter("id", id)
         .getSingleResult();

        assertEquals(id, dto.id());

        // DTO không phải @Entity, không nên gọi em.contains(dto).
        // Mục tiêu là kiểm tra query trả đúng DTO value fields,
        // không phải managed Book.
    } finally {
        em.close();
    }
}
```

Lưu ý: `EntityManager.contains(Object)` yêu cầu entity instance theo contract và có thể ném `IllegalArgumentException` nếu truyền DTO không phải entity. Vì vậy **không nên dùng `assertFalse(em.contains(dto))` như một kiểm thử portable**.

Thay vào đó, test query result type, không có entity/proxy/reference, rồi kiểm thử rằng thay đổi DTO không làm database update.

### Test sửa DTO không thay đổi DB

```java
@Test
void changingDtoValueDoesNotUpdateBook() {
    Long id = seededBookId;

    String originalTitle = loadCommittedTitle(id);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        BookCard dto = loadBookCard(em, id);

        BookCard changed = new BookCard(
            dto.id(),
            "Tên chỉ trong DTO",
            dto.authorName(),
            dto.price()
        );

        assertEquals("Tên chỉ trong DTO", changed.title());

        em.flush();
        em.getTransaction().commit();
    } finally {
        em.close();
    }

    String databaseTitle = loadCommittedTitle(id);

    assertEquals(originalTitle, databaseTitle);
}
```

`loadBookCard` và `loadCommittedTitle` là helper được triển khai trong test. Helper kiểm tra DB nên sử dụng persistence context mới và fixture ổn định, tránh lẫn các thay đổi của transaction khác.

Test xác minh đặc điểm trọng tâm: **tạo một DTO mới không làm dirty checking cập nhật Book**.

## 40. Integration test: DTO còn dùng được sau khi context đóng

```java
@Test
void dtoDoesNotNeedPersistenceContextAfterQuery() {
    EntityManager em = emf.createEntityManager();
    BookCard card;

    try {
        card = loadBookCard(em, seededBookId);
    } finally {
        em.close();
    }

    assertNotNull(card.id());
    assertNotNull(card.title());
    assertNotNull(card.authorName());
    assertNotNull(card.price());
}
```

Đây là một test đơn giản nhưng quan trọng: DTO đã chứa scalar values, không yêu cầu lazy loading sau khi context đóng.

Nếu DTO chứa `Author` entity thay vì String authorName, test này vẫn có thể pass khi chỉ đọc title, nhưng sẽ thất bại khi truy cập nested lazy field. Vì vậy một test DTO phong phú nên **đọc tất cả nested DTO fields sau khi đóng context** và đảm bảo không có entity/proxy bên trong.

## 41. Integration test: kiểm tra phân trang đúng tập và tổng số

Với trang danh sách, tạo fixture:

- 25 Book published.
- 10 Book unpublished.
- Nhiều Author khác nhau.
- Một số Books có cùng title để kiểm tra sort tiebreaker.

Query:

```java
List<BookCard> page = em.createQuery(
    "SELECT NEW com.example.dto.BookCard(" +
    "b.id, b.title, a.name, b.price) " +
    "FROM Book b JOIN b.author a " +
    "WHERE b.published = true " +
    "ORDER BY b.title ASC, b.id ASC",
    BookCard.class
).setFirstResult(10)
 .setMaxResults(10)
 .getResultList();
```

Count:

```java
Long total = em.createQuery(
    "SELECT COUNT(b) FROM Book b " +
    "WHERE b.published = true",
    Long.class
).getSingleResult();
```

Test cần assert:

- Page có tối đa 10 items.
- IDs đúng slice theo thứ tự mong đợi.
- `total` bằng 25 với fixture cô lập.
- Không có unpublished Book.
- Không có duplicate item do join.
- DTO fields đúng và dùng được sau transaction.
- Query count không tăng theo số Author khi tạo response.
- Filter và count query sử dụng cùng conditions.

Cẩn thận khi dùng Spring `@DataJpaTest` với transaction mặc định rollback: nếu mục tiêu là dữ liệu sau commit, phải tổ chức transaction và persistence context riêng, không chỉ assert trên objects trong cùng context.

## 42. Kiểm thử tránh entity/proxy lọt vào DTO

Một số nguyên tắc kiểm thử định dạng:

1. Dùng reflection hoặc schema review để xem DTO fields chỉ thuộc các kiểu được phép.
2. Không có field type `Book`, `Author`, `Collection<Review>` trực tiếp nếu đó là JPA entities.
3. Nested DTO chỉ chứa DTO/value types, không chứa lazy suppliers/callbacks đọc EntityManager.
4. Mapping DTO hoàn tất trong transaction.
5. Sau khi đóng context, serialize DTO thành JSON không phát SQL.
6. Khi data lớn, kiểm tra không có N+1 do DTO mapper.
7. Kiểm tra field privacy và authorization.
8. Kiểm tra version/ID conversion rõ ràng.

Không nên phụ thuộc vào tên class proxy cụ thể của Hibernate trong một test yêu cầu provider portability. Nếu dự án gắn chặt Hibernate, có thể dùng công cụ của Hibernate để phát hiện proxies, nhưng phải ghi rõ đó là integration test provider-specific.

## 43. Những lỗi thường gặp

### Lỗi 1: DTO chứa entity reference

`record BookDto(Long id, Author author)` vẫn có thể kéo theo lazy proxy. Chỉ đưa `AuthorSummary` hoặc scalar fields cần thiết.

### Lỗi 2: DTO giữ entity và tính field khi getter được gọi

Nếu DTO getter gọi `book.getAuthor().getName()` sau transaction, nó không độc lập với persistence context. Tính dữ liệu khi mapping.

### Lỗi 3: Chuyển entity sang DTO ở controller sau khi transaction đã đóng

Mapping có thể gặp lazy initialization error. Map trong service/transaction hoặc projection trực tiếp.

### Lỗi 4: Ngỡ DTO có ID sẽ được dirty checking

DTO không managed. Tạo/sửa DTO không phát SQL UPDATE.

### Lỗi 5: Truyền DTO cho `em.merge()`

`merge` áp dụng entity semantics, không chuyển tùy ý DTO thành entity. Hãy tải managed entity và áp dụng command.

### Lỗi 6: Dùng detached entity thay DTO

Detached entity vẫn có mapping/proxy/graph và có thể stale. DTO là một abstraction khác.

### Lỗi 7: Copy mọi field từ DTO vào entity

Dễ mass assignment, vi phạm quyền hoặc ghi đè field vắng mặt. Dùng command theo use case.

### Lỗi 8: DTO chứa List entity hoặc persistent collection

Khi serializer duyệt, vẫn có thể load lazy hoặc lộ entity graph. Copy thành list DTO values.

### Lỗi 9: Đọc cả graph khi chỉ cần danh sách nhỏ

Nên dùng projection và pagination, không fetch toàn bộ associations.

### Lỗi 10: DTO mapper gây N+1

Nhiều DTO nhưng mỗi Book lazy-load Author/Reviews riêng. Dùng fetch plan/projection/batch.

### Lỗi 11: Lấy page bằng join fetch collection rồi cắt trong Java

Có nguy cơ row multiplication và memory lớn. Dùng page IDs/projection theo nhu cầu.

### Lỗi 12: Count query thiếu filter/tenant

Trang liệt kê đúng nhưng totalElements sai hoặc lộ thông tin. Áp dụng cùng điều kiện phân quyền.

### Lỗi 13: Record có List mutable không defensive copy

Record chỉ bất biến ở reference fields, không bảo đảm nested collection immutable. Dùng `List.copyOf` và DTO immutable.

### Lỗi 14: Client gửi version cũ nhưng server không kiểm tra

DTO version chỉ là dữ liệu. Cần optimistic locking thực sự trong service/DB.

### Lỗi 15: Dùng DTO từ entity sau rollback làm trạng thái đã commit

Entity có thể giữ field đã thay đổi nhưng rollback DB. Đọc lại bằng context mới.

### Lỗi 16: Native Object[] đi thẳng tới HTTP

Khó kiểm soát shape/types và dễ lộ dữ liệu. Map tại repository.

### Lỗi 17: Coi Spring interface projection là JPA entity

Projection có thể dùng proxy framework nhưng không có JPA-managed entity semantics. Cần đo query shape và tránh nested entity leakage.

### Lỗi 18: DTO cache tự nghĩ là JPA cache

Application DTO cache cần TTL/invalidation/security riêng.

### Lỗi 19: Trả cả trường nội bộ do DTO trùng entity model

DTO cần được thiết kế theo contract API và quyền, không copy nguyên entity fields mặc định.

### Lỗi 20: Không kiểm tra hiệu năng của DTO query

Một DTO projection với nhiều JOIN/GROUP vẫn có thể đắt. Đo SQL, rows và memory thực tế.

## 44. Bài tập thực hành

### Bài tập 1: Phân biệt entity và DTO

```java
Book book = em.find(Book.class, 42L);
BookCard card = new BookCard(
    book.getId(),
    book.getTitle(),
    book.getAuthor().getName(),
    book.getPrice()
);
```

**Câu hỏi:** Object nào có thể được JPA dirty checking?

**Đáp án:** Book nếu đang managed trong persistence context/transaction phù hợp. BookCard là DTO, không được JPA quản lý.

### Bài tập 2: DTO có ID

`BookCard(42L, "A", "...", ...)` được tạo bằng `new`.

**Câu hỏi:** Có thể gọi `em.merge(card)` để lưu title không?

**Đáp án:** Không. BookCard không phải entity. Dùng command và tải Book managed để cập nhật.

### Bài tập 3: DTO chứa entity

`record BookDto(Long id, Author author)`.

**Câu hỏi:** Rủi ro?

**Đáp án:** Author là entity có thể mang lazy proxy/state gắn persistence context. Truy cập/serialize sau transaction dễ gặp lazy load hoặc vô tình phát SQL. Dùng AuthorSummary.

### Bài tập 4: Lazy-loading sau transaction

Một DTO getter có nội dung `return book.getAuthor().getName()` và service đã đóng EntityManager.

**Câu hỏi:** DTO có thực sự độc lập không?

**Đáp án:** Không. Nó giữ Book reference và lazy computation. Chuyển authorName thành String khi mapping trong context.

### Bài tập 5: JPQL projection

**Yêu cầu:** Trả ID, title, authorName, price.

**Đáp án:** Dùng `SELECT NEW com.example.dto.BookCard(b.id,b.title,a.name,b.price) FROM Book b JOIN b.author a` với constructor khớp.

### Bài tập 6: Chỉnh sửa DTO

Người dùng sửa BookCard title trên UI rồi gửi lại.

**Câu hỏi:** Có SQL update tự động không?

**Đáp án:** Không. Service phải nhận một command, kiểm tra quyền/version, tải managed Book và gọi domain method.

### Bài tập 7: Phân trang

API cho phép page size 100000.

**Câu hỏi:** Vấn đề?

**Đáp án:** DTO vẫn phải được materialize/serialize, có thể tiêu tốn bộ nhớ và tải DB. Giới hạn page size theo chính sách.

### Bài tập 8: Review count

Một Book có 1000 Reviews; danh sách chỉ cần số reviews.

**Câu hỏi:** Nên trả List<ReviewDto> đầy đủ không?

**Đáp án:** Không cần. Dùng query aggregate COUNT(r) cho BookReviewCard hoặc batch aggregation.

### Bài tập 9: Nested DTO

`OrderDetail` chứa `List<OrderLineDto>` được tạo từ persistent collection.

**Câu hỏi:** Làm sao hạn chế rò rỉ context?

**Đáp án:** Chuyển từng entity con thành DTO thuần dữ liệu trong transaction, copy list, không giữ OrderLine entity/proxy.

### Bài tập 10: Version

Client có DTO version 3, server Book đã version 4.

**Câu hỏi:** DTO version 3 tự làm JPA từ chối update chưa?

**Đáp án:** Chưa. Service cần kiểm tra version/optimistic locking ở entity hoặc conditional SQL.

### Bài tập 11: DTO và rollback

Transaction đổi Book title rồi rollback. Sau đó mapper entity cũ thành BookDto.

**Câu hỏi:** DTO có chắc phản ánh DB không?

**Đáp án:** Không. DTO chỉ phản ánh nguồn object được map; entity cũ có thể giữ state bị rollback. Đọc lại trong context mới.

### Bài tập 12: Native SQL projection

Native SELECT trả `Object[]` với ID, title, price.

**Câu hỏi:** Đưa `Object[]` trực tiếp ra REST API có nên không?

**Đáp án:** Không nên trong phần lớn ứng dụng. Map thành DTO với field names, kiểm tra type/null/index và chỉ expose trường được phép.

### Bài tập 13: Tối ưu N+1

Mapper duyệt 100 Books và gọi `book.getAuthor().getName()`.

**Câu hỏi:** DTO đã giúp tránh N+1 chưa?

**Đáp án:** Chưa chắc. Mapping có thể kích hoạt 100 secondary SELECT. Dùng JPQL constructor projection hoặc fetch plan phù hợp.

### Bài tập 14: Data security

Book entity có `internalCost` và `publicPrice`; API chỉ được trả publicPrice.

**Câu hỏi:** DTO nên chứa gì?

**Đáp án:** Chỉ những field được phép như ID, title, publicPrice. Repository/authorization kiểm tra quyền; không expose internalCost vì tiện copy entity.

### Bài tập 15: Snapshot

DTO đã được cache một giờ, trong khi Book đã thay đổi.

**Câu hỏi:** DTO có tự đồng bộ lại không?

**Đáp án:** Không. Cần cache invalidation, TTL, version hoặc query lại theo consistency requirements.

## 45. Checklist thiết kế DTO không mang persistence context

Trước khi đưa một DTO vào API/service boundary, kiểm tra:

1. DTO có thực sự **không được gắn `@Entity`** và không được xử lý như entity không?
2. Field DTO có chỉ là value types, IDs hoặc nested DTO hợp lệ không?
3. Có chứa entity, proxy, persistent collection, `EntityManager` hoặc `Query` không?
4. Có getter/lambda/supplier nào giữ reference tới entity và lazy-load sau transaction không?
5. DTO có được tạo hoàn chỉnh trước khi đóng context không?
6. Với nested lists/maps, đã copy collection và kiểm soát mutability chưa?
7. Response fields có theo đúng use case, không lộ trường nội bộ không?
8. Tenant/authorization filters có áp dụng ở query/service không?
9. DTO list có `setFirstResult`/`setMaxResults` và giới hạn page size không?
10. ORDER BY có ổn định cho pagination không?
11. Count query có áp dụng cùng filter/authorization không?
12. Có join collection làm nhân row và duplicate DTO không?
13. Có thể dùng projection thay vì load managed entity graph không?
14. Nếu mapping từ entity, fetch plan có tránh N+1 không?
15. Nested collections có thể batch-load theo page IDs không?
16. DTO có giữ version token khi thao tác ghi cần optimistic locking không?
17. Service ghi có load managed entity và áp dụng command thay vì `merge(dto)` không?
18. Có validation và allowlist field update rõ ràng không?
19. DTO được tạo sau rollback có dựa trên state đã commit không?
20. DTO cache có policy làm mới/invalidation riêng không?
21. Native query Object[] có được chuyển kiểu và map ở repository không?
22. Có integration test dùng DTO sau khi context đã đóng không?
23. Có test sửa DTO không làm database update không?
24. Có test phân trang, total count và dữ liệu tenant đúng không?
25. Có xem DTO là snapshot thay vì live managed state không?

## Kết luận

**DTO không mang theo quyền quản lý của persistence context vì nó là một hợp đồng dữ liệu, không phải một JPA entity đang managed.** DTO có thể chứa ID, version và những giá trị xuất phát từ entity, nhưng các field đó không làm nó được JPA dirty checking, flush, cascade hay orphan removal. Thay đổi DTO không tự cập nhật database; `merge()` cũng không phải cơ chế chuyển tùy ý DTO thành managed entity.

Thiết kế tốt cần **cắt ranh giới persistence**: đọc bằng JPQL/Criteria/native projection hoặc map entity thành DTO hoàn chỉnh trong transaction; chỉ mang scalar values, value objects và nested DTO qua service/API boundary; không giữ entity, lazy proxies hoặc persistent collections. Khi cần dữ liệu mới, query lại thay vì refresh DTO. Khi cần cập nhật, nhận command riêng, kiểm tra quyền và optimistic version, tải managed entity rồi áp dụng domain methods.

Với danh sách lớn, DTO đi cùng **phân trang, ORDER BY ổn định, count query đúng filter và fetch plan chống N+1**. DTO giúp chọn chính xác những cột cần thiết nhưng không thay thế query optimization, transaction isolation hoặc authorization.

Hãy tự hỏi bốn câu khi thiết kế một response: **“DTO đang chứa giá trị hay reference tới entity? Nó còn cần EntityManager sau khi được trả đi không? Sửa DTO có bị hiểu nhầm thành sửa database không? Query có chỉ tải đúng dữ liệu cần cho trang hiện tại không?”**. Trả lời rõ bốn câu ấy sẽ giúp hệ thống tách bạch JPA persistence lifecycle khỏi dữ liệu trao đổi, giảm lỗi lazy loading, stale state và cập nhật ngoài ý muốn.
