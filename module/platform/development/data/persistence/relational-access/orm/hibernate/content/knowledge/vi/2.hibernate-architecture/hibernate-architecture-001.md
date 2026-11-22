# SessionFactory, Session và Transaction trong toàn bộ vòng đời truy cập dữ liệu

## 1. Bức tranh tổng thể: một lần truy cập dữ liệu đi qua những gì?

Trong Hibernate ORM, truy cập cơ sở dữ liệu không chỉ là gọi một lệnh `INSERT`, `SELECT` hay `UPDATE`. Ứng dụng cần biết **ai tạo hạ tầng ORM**, **ai quản lý các entity đang được thao tác** và **ai quyết định một nhóm thay đổi được xác nhận hay hủy bỏ**. Ba vai trò cốt lõi lần lượt thuộc về `SessionFactory`, `Session` và `Transaction`.

Ví dụ, một nghiệp vụ “mượn sách” thường đi theo trình tự:

1. Ứng dụng đã khởi tạo `SessionFactory` lúc bắt đầu chạy.
2. Khi nhận yêu cầu mượn sách, tầng nghiệp vụ mở một `Session`.
3. Trong `Session` đó, ứng dụng bắt đầu `Transaction`.
4. Hibernate tải sách từ cơ sở dữ liệu thành một entity **managed** (được `Session` quản lý).
5. Nghiệp vụ sửa trạng thái của entity. Hibernate phát hiện sự thay đổi thông qua cơ chế *dirty checking*.
6. Khi `flush`, Hibernate đồng bộ các thao tác cần thiết thành SQL; khi `commit`, giao dịch được xác nhận ở cơ sở dữ liệu.
7. `Session` được đóng và tài nguyên được giải phóng. `SessionFactory` tiếp tục sống để phục vụ yêu cầu khác.

```text
KHỞI ĐỘNG ỨNG DỤNG
    │
    └── Tạo SessionFactory ─────────────────────────────────────┐
                                                                │
MỘT NGHIỆP VỤ TRUY CẬP DỮ LIỆU                                 │
    │                                                           │
    ├── Mở Session ◄─────────────────────────────────────────────┘
    │      │
    │      ├── Bắt đầu Transaction
    │      │      ├── get / persist / query / remove ...
    │      │      ├── Theo dõi entity trong persistence context
    │      │      ├── flush → phát SQL xuống JDBC
    │      │      └── commit hoặc rollback
    │      │
    │      └── Đóng Session
    │
    └── Trả kết quả nghiệp vụ

DỪNG ỨNG DỤNG
    └── Đóng SessionFactory
```

Đây là mô hình thường gặp khi ứng dụng tự quản lý Hibernate theo kiểu *resource-local transaction* (giao dịch JDBC). Trong Spring hoặc môi trường JTA, framework có thể đảm nhiệm phần mở/đóng và ràng buộc transaction; bản chất ba vai trò vẫn như vậy.

## 2. Phân biệt trách nhiệm và vòng đời

| Thành phần | Nhiệm vụ chính | Phạm vi sống thường gặp | Dùng chung giữa các luồng? |
|---|---|---|---|
| `SessionFactory` | Giữ metadata mapping, cấu hình ORM, dịch vụ nội bộ; tạo `Session`; tích hợp cache cấp hai nếu được bật | Gần như toàn bộ vòng đời ứng dụng, thường một instance cho mỗi cấu hình/database | **Có**; thiết kế thread-safe |
| `Session` | Cung cấp API thao tác entity, giữ *persistence context* (cache cấp một), theo dõi thay đổi, sắp xếp thao tác SQL | Một đơn vị công việc hoặc một phạm vi giao dịch được quản lý | **Không**; không thread-safe |
| `Transaction` | Đại diện ranh giới xác nhận/hủy bỏ công việc; `begin`, `commit`, `rollback` | Một nghiệp vụ có yêu cầu tính nhất quán | Không chia sẻ độc lập giữa các luồng |
| JDBC `Connection` | Thực thi câu lệnh SQL tới database; thực hiện commit/rollback vật lý khi dùng JDBC transaction | Được cấp và trả theo chính sách connection handling/pool | Không sử dụng đồng thời bừa bãi giữa các luồng |

### SessionFactory: hạ tầng được xây một lần

Việc tạo `SessionFactory` cần đọc mapping của entity, chuẩn bị metadata, dịch vụ Hibernate và các cấu hình liên quan. Vì khá tốn kém, ứng dụng thường tạo một `SessionFactory` khi khởi động rồi tái sử dụng cho nhiều nghiệp vụ. Có thể tạo nhiều factory nếu ứng dụng chủ động dùng nhiều database hoặc tập cấu hình độc lập; đó là quyết định kiến trúc, không phải mỗi request tạo một factory.

`SessionFactory` **không phải** một phiên làm việc với một người dùng hay một HTTP request. Nó không thay thế cho `Session`, và cũng không đồng nghĩa với một JDBC `Connection` duy nhất. Khi ứng dụng dừng, cần đóng factory để giải phóng các dịch vụ và tài nguyên liên quan.

### Session: không gian quản lý entity

`Session` đại diện cho một ngữ cảnh thao tác với database. Nó chứa **persistence context**, nơi Hibernate ghi nhớ entity nào đã được nạp/quản lý, khóa định danh của chúng và trạng thái cần theo dõi. Trong cùng một `Session`, tải cùng một entity bằng khóa chính thường trả lại cùng đối tượng Java:

```java
try (Session session = sessionFactory.openSession()) {
    Book first = session.get(Book.class, bookId);
    Book second = session.get(Book.class, bookId);
    System.out.println(first == second); // true nếu bản ghi tồn tại
}
```

Điều này là **identity map/cache cấp một**, không có nghĩa mọi truy vấn HQL tiếp theo sẽ bỏ qua SQL. `Session` giữ trạng thái của đối tượng; database vẫn có thể được truy vấn để tìm kết quả phù hợp.

`Session` không thread-safe. Không lưu nó trong singleton để dùng đồng thời, không truyền chung cho các request độc lập và không giữ vô hạn trong một ứng dụng chạy lâu. Một `Session` giữ quá nhiều entity có thể làm tăng bộ nhớ, chậm dirty checking và tạo dữ liệu cũ so với database.

### Transaction: ranh giới nhất quán

Một `Transaction` bao bọc công việc cần được xác nhận hoặc hủy như một đơn vị. Nếu một nghiệp vụ giảm tồn kho và tạo đơn hàng, cả hai thay đổi phải thuộc cùng một ranh giới giao dịch nếu cần tính nguyên tử trong cùng cơ sở dữ liệu.

`Transaction` của Hibernate là lớp trừu tượng. Với cấu hình JDBC resource-local, nó điều phối JDBC transaction. Với JTA, nó tham gia cơ chế giao dịch do môi trường quản lý. `Transaction` **không phải** persistence context và cũng không tự cung cấp các entity: đó là nhiệm vụ của `Session`.

## 3. Khởi tạo SessionFactory khi ứng dụng bắt đầu

Một ví dụ Hibernate ORM dùng API native, Jakarta Persistence annotations và PostgreSQL. Các ví dụ phía dưới giả định ứng dụng đã có dependency tương thích cho Hibernate ORM, JDBC driver PostgreSQL và database `demo`. Ví dụ dùng cấu hình programmatic để thể hiện rõ vòng đời, không gắn vào một framework cụ thể.

Entity `Book`:

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

    @Column(nullable = false, length = 255)
    private String title;

    @Column(nullable = false)
    private boolean available;

    @Version
    private Long version;

    protected Book() {
        // Constructor cho Hibernate
    }

    public Book(String title) {
        this.title = title;
        this.available = true;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isAvailable() {
        return available;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }

    public void markBorrowed() {
        this.available = false;
    }
}
```

Nếu cấu hình `hibernate.hbm2ddl.auto=validate` thì bảng phải tồn tại từ trước. Ví dụ DDL PostgreSQL tương ứng:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    available BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);
```

Khởi tạo:

```java
import java.util.HashMap;
import java.util.Map;
import org.hibernate.SessionFactory;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.StandardServiceRegistry;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;

public final class HibernateBootstrap {
    private HibernateBootstrap() {}

    public static SessionFactory createSessionFactory() {
        Map<String, Object> settings = new HashMap<>();
        settings.put("hibernate.connection.driver_class", "org.postgresql.Driver");
        settings.put("hibernate.connection.url",
                     "jdbc:postgresql://localhost:5432/demo");
        settings.put("hibernate.connection.username", "demo");
        settings.put("hibernate.connection.password", "demo_password");
        settings.put("hibernate.hbm2ddl.auto", "validate");

        StandardServiceRegistry registry =
                new StandardServiceRegistryBuilder()
                        .applySettings(settings)
                        .build();

        try {
            return new MetadataSources(registry)
                    .addAnnotatedClass(Book.class)
                    .buildMetadata()
                    .buildSessionFactory();
        } catch (RuntimeException ex) {
            StandardServiceRegistryBuilder.destroy(registry);
            throw ex;
        }
    }
}
```

Sau đó application root giữ factory làm phụ thuộc dùng chung:

```java
SessionFactory sessionFactory = HibernateBootstrap.createSessionFactory();
try {
    BookService service = new BookService(sessionFactory);
    // Xử lý nhiều nghiệp vụ thông qua service ...
} finally {
    sessionFactory.close();  // Khi ứng dụng thực sự dừng
}
```

Trong ứng dụng triển khai thực tế, thông tin kết nối đến từ cấu hình bảo mật/biến môi trường và database connection pool; không hard-code mật khẩu như giá trị minh họa. Schema thường được tạo, nâng cấp bằng migration, còn `validate` kiểm tra mapping khi khởi động. Không nên tùy tiện dùng `create` hoặc `create-drop` trên dữ liệu cần giữ vì các chế độ ấy có thể xóa/tạo lại schema.

> **Một khác biệt cần nhớ:** gọi `sessionFactory.openSession()` chưa chắc đã lấy ngay một physical JDBC connection. Hibernate có thể lấy connection khi cần chạy SQL hoặc bắt đầu thao tác giao dịch, rồi trả connection theo chính sách quản lý tài nguyên. Cách cấp connection cụ thể phụ thuộc cấu hình và môi trường.

## 4. Một transaction đầy đủ: mở, thao tác, commit hoặc rollback, đóng

Với resource-local transaction, hình dạng an toàn thường là:

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public void renameBook(SessionFactory factory, Long id, String newTitle) {
    try (Session session = factory.openSession()) {
        Transaction tx = session.beginTransaction();

        try {
            Book book = session.get(Book.class, id);
            if (book == null) {
                throw new IllegalArgumentException("Không tìm thấy sách: " + id);
            }

            book.rename(newTitle); // Entity đang managed
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
    } // Tự đóng Session kể cả khi có ngoại lệ
}
```

**Đọc dòng thời gian từ trên xuống:**

| Thời điểm | Hibernate/JDBC đang làm gì? | Điểm cần chú ý |
|---|---|---|
| `openSession()` | Tạo `Session` và persistence context mới | Chưa đồng nghĩa một transaction mới |
| `beginTransaction()` | Bắt đầu ranh giới transaction theo transaction coordinator | Phạm vi tài nguyên phụ thuộc JDBC/JTA |
| `get(Book.class, id)` | Kiểm tra persistence context; nếu cần, phát `SELECT` | Entity trả về là managed nếu tồn tại |
| `book.rename(...)` | Sửa trạng thái đối tượng Java | Không cần gọi `update()` để ghi lại entity đã managed |
| `flush` (thường khi commit) | Dirty checking; tạo và thực thi `UPDATE` cần thiết | SQL đã chạy **chưa** đồng nghĩa đã commit |
| `tx.commit()` | Flush theo flush mode áp dụng, rồi xác nhận giao dịch | Thành công mới là mốc ghi nhận thay đổi về mặt giao dịch |
| `tx.rollback()` khi lỗi | Hủy các thay đổi đã thực hiện trong transaction tại database | Không tự hoàn nguyên giá trị field của các Java object |
| `session.close()` | Kết thúc persistence context và giải phóng tài nguyên của session | Entity còn tham chiếu trở thành detached |

Chỉ `session.close()` không thay thế cho `tx.commit()` hoặc `tx.rollback()`. Ứng dụng phải quản lý dứt điểm transaction; không phó mặc cho việc đóng connection. Sau lỗi Hibernate hoặc lỗi JDBC nghiêm trọng, hãy rollback rồi bỏ `Session` đó, đừng tiếp tục dùng nó cho nghiệp vụ khác.

### Mẫu tái sử dụng ranh giới giao dịch

Có thể đóng gói cùng một vòng đời cho nhiều nghiệp vụ, để từng hàm nghiệp vụ tập trung vào dữ liệu:

```java
import java.util.function.Function;
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public final class Transactions {
    private Transactions() {}

    public static <T> T execute(
            SessionFactory factory,
            Function<Session, T> work) {
        try (Session session = factory.openSession()) {
            Transaction tx = session.beginTransaction();
            try {
                T result = work.apply(session);
                tx.commit();
                return result;
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

Ví dụ một `BookService` thực hiện tạo, đọc, cập nhật và xóa:

```java
import java.util.List;
import org.hibernate.SessionFactory;

public final class BookService {
    private final SessionFactory factory;

    public BookService(SessionFactory factory) {
        this.factory = factory;
    }

    public Long create(String title) {
        Book saved = Transactions.execute(factory, session -> {
            Book book = new Book(title); // transient
            session.persist(book);       // managed
            return book;
        });
        // Transaction đã commit; session đã đóng; saved giờ là detached.
        return saved.getId();
    }

    public List<String> listTitles() {
        return Transactions.execute(factory, session ->
                session.createQuery(
                        "select b.title from Book b order by b.title",
                        String.class)
                        .getResultList());
    }

    public void borrow(Long id) {
        Transactions.execute(factory, session -> {
            Book book = session.get(Book.class, id);
            if (book == null) {
                throw new IllegalArgumentException("Không tìm thấy sách: " + id);
            }
            if (!book.isAvailable()) {
                throw new IllegalStateException("Sách đã được mượn");
            }
            book.markBorrowed(); // dirty checking tại flush
            return null;
        });
    }

    public void delete(Long id) {
        Transactions.execute(factory, session -> {
            Book book = session.get(Book.class, id);
            if (book != null) {
                session.remove(book);
            }
            return null;
        });
    }
}
```

Ở đây mỗi lời gọi của `BookService` là một transaction độc lập. Nếu có nghiệp vụ “tạo phiếu mượn **và** cập nhật sách” cần nguyên tử, hai thao tác đó phải chạy bên trong **cùng một lần** `Transactions.execute(...)` và cùng `Session`, thay vì ghép hai service method vốn đã tự commit riêng.

## 5. Vòng đời của entity bên trong Session

Muốn hiểu vì sao Hibernate tự ghi `UPDATE`, cần phân biệt **vòng đời `Session`** với **trạng thái entity**.

```text
new Book(...)           session.persist(book)
    │                          │
    ▼                          ▼
TRANSIENT ─────────────────► MANAGED ◄──── session.get(...) từ database
                              │ │
      session.remove(book)     │ └── Sửa field → dirty checking → flush
                 │            │
                 ▼            │ session.close() / session.clear()
              REMOVED         ▼
                            DETACHED
                               │
              session.merge(detached) → trả về một instance MANAGED
```

| Trạng thái | Ý nghĩa | Thao tác thường gặp |
|---|---|---|
| **Transient** | Đối tượng Java mới, chưa được gắn vào persistence context | `new Book(...)` |
| **Managed/Persistent** | `Session` đang theo dõi entity theo định danh; thay đổi có thể được ghi khi flush | `persist()`, `get()`, kết quả query entity |
| **Removed** | Entity được đánh dấu cần xóa trong persistence context | `remove(managedEntity)`; SQL `DELETE` khi đồng bộ |
| **Detached** | Entity có định danh nhưng không còn thuộc persistence context hiện tại | Sau `close()`, `clear()`, `detach()` hoặc `evict()` |

**Ví dụ dirty checking:**

```java
Transactions.execute(sessionFactory, session -> {
    Book book = session.get(Book.class, 10L); // managed
    if (book != null) {
        book.rename("Hibernate nâng cao");
        // Không cần session.update(book)
    }
    return null;
}); // commit → Hibernate flush UPDATE nếu thực sự có thay đổi
```

Sửa field của một entity **detached** không tự sinh SQL:

```java
Book detached = Transactions.execute(sessionFactory,
        session -> session.get(Book.class, 10L));

if (detached != null) {
    detached.rename("Tên mới"); // Session cũ đã đóng; không tự UPDATE

    Transactions.execute(sessionFactory, session -> {
        Book managedCopy = session.merge(detached);
        // managedCopy thuộc session mới; detached vẫn là đối tượng detached.
        return null;
    });
}
```

Với `merge()`, Hibernate sao chép trạng thái sang instance managed và **trả về instance managed**; đừng mặc định chính đối tượng truyền vào trở thành managed. Mặt khác, khi đang có transaction, có thể tải lại entity rồi cập nhật các field cho phép từ dữ liệu đầu vào. Cách này giúp kiểm soát giá trị cập nhật và phiên bản entity rõ ràng hơn.

`persist()` đưa một entity mới vào persistence context nhưng thời điểm `INSERT` vật lý phụ thuộc chiến lược sinh ID và thao tác đồng bộ. Ví dụ `GenerationType.IDENTITY` thường cần `INSERT` sớm để lấy ID từ database. Đã thực thi `INSERT` trong transaction vẫn có thể `rollback` nếu chưa commit.

### Persistence context không phải transaction

Hai khái niệm liên hệ chặt nhưng không đồng nhất:

- Persistence context quyết định **đối tượng nào được quản lý**, cache cấp một, dirty checking và chuỗi thao tác ORM cần đồng bộ.
- Transaction quyết định **những thay đổi nào được xác nhận/hủy bỏ** trên database theo cơ chế transaction đang dùng.

Một `Session` có thể tồn tại qua nhiều transaction nếu chủ động thiết kế, nhưng điều đó làm phức tạp việc xử lý dữ liệu cũ, trạng thái sau rollback và bộ nhớ. Với đa số nghiệp vụ web thông thường, nên xác định một transaction rõ ràng cho mỗi đơn vị công việc và dùng session ngắn, phù hợp với phạm vi ấy.

## 6. Flush, commit và rollback: ba hành động thường bị nhầm

**Flush** là quá trình đồng bộ các thay đổi trong persistence context thành các lệnh SQL cần thiết. **Commit** là xác nhận giao dịch ở tầng transaction/database. **Rollback** là yêu cầu database hủy các thay đổi chưa commit trong giao dịch đó.

```text
Java: book.rename("B")    ← Thay đổi trong persistence context
              │
              ▼
        session.flush()
              │
              └── JDBC UPDATE books SET title = 'B' ...
                      │
                      ├── tx.rollback() → database hủy UPDATE
                      └── tx.commit()   → database xác nhận UPDATE
```

Ví dụ flush thủ công:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Book book = session.get(Book.class, 10L);
        if (book != null) {
            book.rename("Đang thử nghiệm");
            session.flush(); // SQL UPDATE có thể đã chạy trong transaction
        }

        tx.rollback();        // Database không giữ thay đổi chưa commit
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Sau `rollback`, đối tượng `book` trong bộ nhớ Java vẫn có thể mang giá trị "Đang thử nghiệm"; Hibernate không tự dựng lại mọi giá trị Java như trước transaction. Hãy kết thúc session và lấy dữ liệu trong session mới nếu cần trạng thái đã xác nhận ở database.

Với flush mode thông thường (`AUTO`), Hibernate có thể flush trước commit và trước một số truy vấn để truy vấn nhìn thấy thay đổi cần thiết. `session.flush()` cho phép yêu cầu đồng bộ sớm, ví dụ để phát hiện một lỗi constraint ngay trong transaction. Việc flush không bảo đảm commit cuối cùng thành công: deadlock, constraint, timeout hoặc lỗi kết nối vẫn có thể khiến transaction thất bại.

Không nên gọi `flush()` sau mọi lần `persist()` hoặc sửa field. Làm vậy có thể tăng round trip và giảm cơ hội Hibernate gom lệnh hiệu quả. Flush mode `MANUAL` hoặc cấu hình read-only có thể đổi hành vi mặc định; khi dùng chúng phải hiểu rõ tác động đến dirty checking và commit.

## 7. Đường đi từ Hibernate xuống JDBC và database

Một lát cắt kiến trúc đủ để định vị ba thành phần:

```text
Controller / API
      │
      ▼
Application Service ─── xác định một đơn vị nghiệp vụ
      │
      ▼
Repository / DAO ────── Session API (get, persist, createQuery...)
      │                          │
      │                          ▼
      │                Persistence context
      │                (identity map, dirty checking)
      │                          │
      └──── Transaction ────────┼── flush → SQL
                                 ▼
                         Hibernate JDBC layer
                                 │
                         DataSource / Connection pool
                                 │
                                 ▼
                          Database / ACID
```

`SessionFactory` đứng phía trên cơ chế tạo `Session`, metadata và dịch vụ Hibernate cho toàn ứng dụng. Khi cần truy cập database, `Session` sử dụng các dịch vụ này để lấy connection thích hợp và thực thi SQL. Nếu có pool, việc `Session` đóng/transaction kết thúc dẫn tới trả connection vào pool theo chiến lược quản lý tài nguyên; không có nghĩa luôn đóng TCP connection vật lý.

Hai kết luận quan trọng:

1. **Một request không bắt buộc tương đương một transaction.** Một request có thể chỉ tính toán trong bộ nhớ, hoặc gọi nhiều nghiệp vụ khác nhau; ranh giới transaction được chọn theo tính nhất quán mong muốn. Tuy nhiên, việc gom các thay đổi phải nguyên tử thì cần cùng ranh giới transaction.
2. **Một transaction ở database không bao trùm mọi side effect.** Nếu cùng nghiệp vụ vừa commit database vừa gửi email hoặc gọi dịch vụ ngoài, `rollback` JDBC không thể “thu hồi” email/API call đó. Khi yêu cầu nhất quán giữa database và message, cần cơ chế phù hợp như transactional outbox, idempotency hoặc saga.

## 8. Truy vấn, lazy loading và giới hạn của Session

Khi truy vấn trả về entity, các entity đó được quản lý bởi `Session` hiện tại:

```java
List<Book> books = Transactions.execute(sessionFactory, session ->
        session.createQuery(
                "from Book b where b.available = :available",
                Book.class)
                .setParameter("available", true)
                .getResultList());
// Ở đây List<Book> vẫn tồn tại, nhưng các Book đã detached.
```

Với `Book` đơn giản, đọc các scalar field đã tải có thể vẫn dùng được sau khi session đóng. Nhưng với một association được lazy load, truy cập dữ liệu chưa khởi tạo sau khi session đóng có thể gây `LazyInitializationException`:

```java
// Ví dụ giả định Author có collection books được mapping LAZY.
Author author = Transactions.execute(sessionFactory,
        session -> session.get(Author.class, authorId));

author.getBooks().size(); // Có thể lỗi: collection chưa khởi tạo,
                          // Session đã đóng.
```

Các giải pháp chủ động gồm:

- Lấy đúng dữ liệu cần dùng **ngay trong transaction**, chuyển sang DTO trước khi đóng `Session`.
- Dùng `join fetch` hoặc entity graph khi cần lấy quan hệ cụ thể cùng truy vấn.
- Điều chỉnh query và fetch plan theo use case, không đổi tất cả association thành `EAGER` một cách máy móc.

Ví dụ với entity `Author` và `Book` có quan hệ phù hợp, một câu HQL có thể chủ động tải association:

```java
Author author = Transactions.execute(sessionFactory, session ->
        session.createQuery(
                "select a from Author a " +
                "left join fetch a.books " +
                "where a.id = :id",
                Author.class)
                .setParameter("id", authorId)
                .getSingleResult());
```

Đoạn `Author` là ví dụ mở rộng **giả định mapping đã có**, không thuộc model `Book` tối giản ở mục 3. Khi fetch collection, còn phải cân nhắc tập kết quả lớn, phân trang và truy vấn lặp dạng N+1; `join fetch` không phải lựa chọn tối ưu cho mọi trường hợp.

### Vì sao không giữ Session mở cho đến khi UI render xong?

Kỹ thuật *Open Session in View* có thể làm lazy loading hoạt động ở tầng trình bày, nhưng cũng khiến SQL được phát sinh muộn, khó nhìn ranh giới transaction và khó dự đoán số lượng truy vấn. Với ứng dụng yêu cầu kiểm soát hiệu năng, nên tải dữ liệu phục vụ response trong service/transaction rồi trả DTO. Nếu framework bật OSIV mặc định, phải cân nhắc theo kiến trúc cụ thể.

## 9. Transaction xử lý cạnh tranh như thế nào?

Transaction tạo ranh giới commit/rollback, nhưng **không tự giải quyết mọi race condition** giữa các request. Mức isolation của database, cơ chế khóa và yêu cầu nghiệp vụ quyết định kết quả.

Ví dụ hai người cùng mượn một cuốn sách:

```text
Transaction A              Transaction B
      │                          │
  Đọc available=true        Đọc available=true
      │                          │
  Đặt available=false       Đặt available=false
      │                          │
     COMMIT                    COMMIT ?
```

Nếu không có kiểm soát cạnh tranh, hai nghiệp vụ có thể cùng kết luận “mượn thành công”. Annotation `@Version` trong `Book` minh họa **optimistic locking**: khi update, Hibernate kiểm tra phiên bản bản ghi; transaction cập nhật trên phiên bản cũ có thể nhận lỗi optimistic locking thay vì im lặng ghi đè. Dạng SQL khái quát:

```sql
UPDATE books
SET available = FALSE, version = version + 1
WHERE id = :id AND version = :old_version;
```

Nếu số bản ghi cập nhật không như kỳ vọng, Hibernate có thể phát hiện xung đột. Điều kiện bảo đảm nghiệp vụ còn phụ thuộc thứ tự kiểm tra, cách phản hồi lỗi và cơ chế retry. Không nên retry mù quáng toàn bộ transaction nếu thao tác có side effect bên ngoài.

Một lựa chọn khác là **pessimistic locking**, ví dụ khóa hàng khi tải entity:

```java
import org.hibernate.LockMode;

Transactions.execute(sessionFactory, session -> {
    Book book = session.get(Book.class, 10L, LockMode.PESSIMISTIC_WRITE);
    if (book != null && book.isAvailable()) {
        book.markBorrowed();
    }
    return null;
});
```

Khả năng khóa, thời gian chờ và SQL phát sinh phụ thuộc database/dialect. Lock pessimistic cũng không thay thế việc chọn transaction boundary gọn và xử lý trường hợp deadlock/timeout. Nếu cần ghi nhiều bảng, hãy giữ mọi thay đổi có liên quan trong một transaction và xác định isolation phù hợp theo yêu cầu nhất quán.

## 10. openSession(), getCurrentSession() và @Transactional

### openSession(): ứng dụng tự sở hữu vòng đời

`sessionFactory.openSession()` tạo session mới và thường yêu cầu người gọi đóng rõ ràng. Phù hợp với CLI, batch job nhỏ, ứng dụng tự quản lý Hibernate hoặc đoạn code độc lập như ví dụ ở trên. Người gọi cũng cần xác định ranh giới transaction.

### getCurrentSession(): session theo ngữ cảnh

`sessionFactory.getCurrentSession()` tìm session được gắn vào *current session context* của môi trường. Nó **không tự động đồng nghĩa** “lấy session được mở bởi `openSession()` gần nhất”. Muốn dùng phải có cơ chế context thích hợp, chẳng hạn transaction manager/framework đã cấu hình; thời điểm mở, bind và đóng session do cơ chế đó quyết định. Nếu chưa có context tương ứng, thao tác có thể thất bại.

Không trộn tùy tiện hai cách này trong cùng luồng xử lý: mở một session thủ công rồi gọi `getCurrentSession()` có thể dẫn đến hai session khác nhau hoặc lỗi do thiếu context.

### Spring: để transaction manager quản lý ranh giới

Trong ứng dụng Spring dùng JPA với Hibernate là provider, cách phổ biến là inject `EntityManager` và đặt `@Transactional` tại service:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringBookService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void rename(Long id, String title) {
        Book book = entityManager.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Không tìm thấy sách: " + id);
        }
        book.rename(title); // Managed: flush khi transaction hoàn tất
    }
}
```

Nếu thật sự cần API riêng của Hibernate trong transaction Spring, có thể lấy `Session` bằng `entityManager.unwrap(Session.class)` với Hibernate làm provider. Thông thường không tự `close()` entity manager/session do Spring quản lý, cũng không gọi `session.beginTransaction()` song song với `@Transactional`. Transaction manager sẽ chịu trách nhiệm commit/rollback theo cấu hình.

Lưu ý `@Transactional` hoạt động thông qua cơ chế proxy/AOP trong cấu hình Spring thường gặp; một lời gọi trực tiếp từ method này sang method khác trên **cùng đối tượng** có thể không đi qua proxy. Ngoài ra, rollback mặc định của Spring thường áp dụng cho `RuntimeException` và `Error`; checked exception cần cấu hình `rollbackFor` nếu nghiệp vụ yêu cầu.

Với JTA hoặc giao dịch được container quản lý, API và trách nhiệm đóng session/connection khác với mẫu resource-local. Cần tuân thủ transaction manager hiện có, không áp nguyên xi đoạn code tự gọi commit/rollback.

## 11. Các lỗi thiết kế thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý đúng trọng tâm |
|---|---|---|
| Mỗi request xây lại `SessionFactory` | Nhầm factory với session | Khởi tạo factory một lần ở application startup; đóng ở shutdown |
| Hai request chia sẻ một `Session` | Lưu session trong singleton/static field | Mỗi đơn vị công việc có session/context phù hợp; không chia session qua thread |
| Sửa entity nhưng database không đổi | Entity detached; transaction chưa commit; flush mode phù hợp chưa được áp dụng | Xác định entity có managed không, ranh giới transaction và flush mode |
| Dùng `flush()` nhưng tưởng đã lưu vĩnh viễn | Nhầm SQL execution với transaction commit | Commit giao dịch; xử lý lỗi phát sinh tới lúc commit |
| Lỗi nghiệp vụ nhưng dữ liệu một phần đã được xác nhận | Nhiều service tự commit riêng | Đặt các thao tác liên quan vào cùng một transaction |
| `LazyInitializationException` khi render response | Truy cập association chưa tải sau khi session đóng | Chuẩn bị DTO hoặc fetch plan phù hợp trong transaction |
| Session giữ nhiều entity và chậm dần | Persistence context sống quá lâu, đặc biệt với import khối lượng lớn | Batch theo chunk, flush/clear có kiểm soát và xác định lại transaction boundary |
| Update bị ghi đè hoặc cả hai request đều “thành công” | Thiếu kiểm soát đồng thời | Dùng `@Version`, locking hoặc lệnh cập nhật có điều kiện theo nghiệp vụ |
| Sau Hibernate exception vẫn tiếp tục gọi cùng session | Persistence context có thể không còn nhất quán | Rollback, đóng và tạo session mới cho lần xử lý tiếp theo |
| Kết nối cạn dù request đã xử lý xong | Session/transaction/stream chưa đóng, hoặc pool cấu hình chưa phù hợp | Đóng tài nguyên đúng phạm vi, kiểm tra luồng xử lý và pool |

### Batch processing có điều gì khác?

Khi ghi hàng chục nghìn entity, cache cấp một tăng lên theo số entity managed. Có thể flush và clear theo từng lô nếu thiết kế cho phép:

```java
Transactions.execute(sessionFactory, session -> {
    for (int i = 0; i < input.size(); i++) {
        session.persist(new Book(input.get(i)));
        if ((i + 1) % 50 == 0) {
            session.flush();
            session.clear();
        }
    }
    return null;
});
```

Ví dụ trên giả định `input` là `List<String>` có sẵn và một transaction bao phủ toàn bộ batch; `clear()` khiến các entity trước đó bị detached. Flush theo lô **không** làm các lô đã commit độc lập, nên transaction dài vẫn có thể giữ lock và tốn tài nguyên. Nếu muốn commit theo từng chunk, phải thiết kế transaction theo từng chunk và xác định rõ khả năng thành công một phần. Với `IDENTITY`, khả năng JDBC insert batching có thể bị hạn chế vì Hibernate cần ID từ database.

### Nên mở transaction cho SELECT không?

Đọc dữ liệu cũng cần một chính sách transaction có chủ đích. Với nhiều ứng dụng, một read transaction ngắn giúp việc truy vấn và tải các dữ liệu liên quan diễn ra trong một phạm vi nhất quán và quản lý tài nguyên rõ ràng. Tuy nhiên, mức nhất quán thực tế phụ thuộc isolation của database; chỉ có `@Transactional(readOnly = true)` không có nghĩa transaction luôn lấy snapshot bất biến, cũng không đồng nghĩa database sẽ cấm mọi câu `UPDATE`. Tùy framework và provider, `readOnly` có thể chỉ là gợi ý tối ưu flush.

## 12. Ghép lại thành vòng đời đầy đủ

Xét một request mượn sách, gồm kiểm tra trạng thái và ghi nhận thay đổi:

```text
T0  Ứng dụng khởi động
    └── Bootstrap metadata, mapping → SessionFactory

T1  Request gọi BookService.borrow(id)
    └── SessionFactory.openSession() → Session mới

T2  Session.beginTransaction()
    └── Bắt đầu resource-local JDBC transaction

T3  Session.get(Book.class, id)
    ├── Tìm trong persistence context
    └── Nếu cần: JDBC SELECT → Book managed

T4  Nghiệp vụ kiểm tra book.isAvailable()
    └── book.markBorrowed() → object managed đổi trạng thái

T5  Transaction.commit()
    ├── Hibernate flush thay đổi → JDBC UPDATE
    ├── Kiểm tra version/constraint và xử lý SQL
    └── Database COMMIT (nếu mọi thứ thành công)
        HOẶC lỗi → rollback theo đường xử lý ngoại lệ

T6  Session.close()
    └── Kết thúc persistence context; trả/giải phóng tài nguyên

T7  Request tiếp theo
    └── Dùng lại SessionFactory, mở Session mới

T8  Ứng dụng shutdown
    └── SessionFactory.close()
```

Từ đó có thể phân định ba câu hỏi kiến trúc:

- **“Hạ tầng Hibernate để tạo các phiên truy cập nằm ở đâu?”** — `SessionFactory`, thường sống cùng ứng dụng.
- **“Entity nào đang được theo dõi và khi nào phát SQL?”** — `Session`, persistence context, dirty checking và flush.
- **“Nhóm thay đổi nào được lưu hoặc hủy như một đơn vị?”** — `Transaction` kết hợp cơ chế transaction của database.

Giữ đúng ba ranh giới này giúp code truy cập dữ liệu có hiệu năng dự đoán được, xử lý lỗi rõ ràng, tránh chia sẻ session sai cách và bảo vệ tính nhất quán của nghiệp vụ.
