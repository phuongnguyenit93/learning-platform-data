# Record, lớp bất biến và lựa chọn phù hợp cho thực thể hoặc dữ liệu chiếu trong Hibernate

## 1. Vấn đề kiến trúc: không phải đối tượng nào lấy từ database cũng là entity

Trong ứng dụng dùng Hibernate ORM, cùng một bản ghi `books` có thể được biểu diễn bởi nhiều loại đối tượng Java:

- **Entity:** đối tượng biểu diễn một thực thể có định danh và vòng đời được `Session`/`EntityManager` quản lý. Hibernate có thể theo dõi thay đổi và đồng bộ chúng xuống database.
- **DTO/projection:** đối tượng chỉ chứa những giá trị cần cho một truy vấn, báo cáo hoặc response. Nó không được quản lý như entity và không tự phát sinh SQL khi dữ liệu trong đối tượng thay đổi.
- **Value object/embeddable:** đối tượng mô tả một giá trị thuộc về entity khác, chẳng hạn địa chỉ giao hàng hoặc khoảng ngày. Nó thường không có định danh và vòng đời độc lập.
- **Immutable entity:** entity được Hibernate xem là chỉ đọc về mặt cập nhật trạng thái, dù vẫn có định danh và có thể được truy vấn như entity.

Java `record`, lớp Java bất biến và annotation `@Immutable` đều liên quan đến ý tưởng “không được sửa”, nhưng **không có cùng ý nghĩa**. Chọn sai kiểu biểu diễn có thể dẫn tới entity không ánh xạ được, cơ chế lazy loading hỏng, việc cập nhật bị bỏ qua, hoặc projection vô tình kéo theo quá nhiều dữ liệu.

Ví dụ một màn hình danh sách sách chỉ cần mã, tiêu đề và tên tác giả. Không nhất thiết phải tải toàn bộ các entity `Book`, `Author` và những quan hệ khác:

```text
Database
  books(id, title, author_id, available, version, ...)
  authors(id, name, ...)
           │
           ├── Entity query
           │     → Book managed trong persistence context
           │     → có identity, dirty checking, lifecycle
           │
           └── Projection query
                 → BookSummary(id, title, authorName)
                 → snapshot dữ liệu thuần, không managed
```

Chương này tập trung vào cách chọn giữa **record, immutable class, mutable entity có đóng gói** và **Hibernate immutable entity** trong ánh xạ thực thể và đọc dữ liệu.

## 2. Bốn nghĩa khác nhau của tính bất biến

Một kiểu Java có thể bất biến ở tầng này nhưng vẫn có thể bị cập nhật ở tầng khác.

| Khái niệm | Phạm vi bảo đảm | Ví dụ | Điều không được bảo đảm |
|---|---|---|---|
| Java record | Các field thành phần của record là `final`; không gán lại được sau khởi tạo | `record BookSummary(Long id, String title) {}` | Đối tượng được tham chiếu bên trong record có thể vẫn mutable |
| Immutable Java class | API/thiết kế không cho sửa trạng thái sau khởi tạo | Class `final`, field `private final`, copy dữ liệu mutable | Không tự chặn SQL cập nhật bản ghi ở database |
| Hibernate `@Immutable` entity | Hibernate không thực hiện cập nhật trạng thái entity thông qua dirty checking thông thường | Entity danh mục `CurrencyCode` chỉ đọc | Không phải ràng buộc database chống mọi `UPDATE`, bulk DML hay tác nhân bên ngoài |
| Bất biến nghiệp vụ/database | Quy tắc “đã phát hành hóa đơn thì không được sửa” được cưỡng chế theo thiết kế | Permission, constraint, trigger, audit, mô hình version | Không tự xuất hiện chỉ nhờ Java `final` hoặc `@Immutable` |

Tính bất biến của **đối tượng Java** trả lời “code có sửa trạng thái object này được không?”. Tính bất biến của **ánh xạ Hibernate** trả lời “Hibernate có coi trạng thái entity này là thứ cần theo dõi để update không?”. Tính bất biến **nghiệp vụ** trả lời “dữ liệu có được phép thay đổi trong toàn hệ thống không?”.

Không nên dùng ba tầng ấy thay thế nhau.

## 3. Java record là gì và nó cung cấp điều gì?

Java `record` là cú pháp gọn để mô tả một tập dữ liệu có cấu trúc. Record chính thức xuất hiện trong Java 16. Với:

```java
public record BookSummary(Long id, String title, String authorName) {}
```

Java sinh ra các thành phần tương đương:

- Các field chứa ba component với quyền truy cập `private final`.
- Canonical constructor nhận ba tham số theo đúng thứ tự khai báo.
- Accessor `id()`, `title()`, `authorName()`, không phải các getter JavaBean `getId()`.
- `equals()` và `hashCode()` dựa trên component; `toString()` biểu diễn dữ liệu.

Ví dụ sử dụng:

```java
BookSummary first = new BookSummary(
        42L, "Hibernate căn bản", "Linh");
BookSummary second = new BookSummary(
        42L, "Hibernate căn bản", "Linh");

System.out.println(first.title());  // Hibernate căn bản
System.out.println(first.equals(second)); // true: bằng nhau theo giá trị
System.out.println(first);
// BookSummary[id=42, title=Hibernate căn bản, authorName=Linh]
```

**Record phù hợp khi:** đối tượng chỉ truyền tải một tập giá trị có ý nghĩa, không cần identity/lifecycle riêng, không cần proxy/entity enhancement và không cần thay đổi field sau khởi tạo. Vì code gọn và constructor mang đầy đủ thành phần, record đặc biệt hữu ích cho read model và query projection.

### 3.1. Record có thể có validation

Record không bắt buộc phải hoàn toàn thụ động. Có thể kiểm tra invariant trong compact canonical constructor:

```java
import java.util.Objects;

public record BookSummary(Long id, String title, String authorName) {
    public BookSummary {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(title, "title");
        Objects.requireNonNull(authorName, "authorName");

        if (title.isBlank()) {
            throw new IllegalArgumentException("Tên sách không được rỗng");
        }
    }
}
```

Các phép kiểm tra trên thực thi **mỗi khi record được tạo**, kể cả khi Hibernate dựng projection qua constructor. Nếu một cột database có `NULL` nhưng constructor từ chối `null`, query có thể thất bại. Hợp đồng nullability của projection phải tương thích dữ liệu thực tế và phép `LEFT JOIN`.

### 3.2. Bất biến của record là bất biến nông

Field của record là `final` nhưng nếu field tham chiếu tới `List`, `Map`, mảng hoặc một object mutable, nội dung của object đó vẫn có thể đổi:

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeBookCard(Long id, List<String> tags) {}

List<String> source = new ArrayList<>(List.of("JPA"));
UnsafeBookCard card = new UnsafeBookCard(5L, source);

source.add("Hibernate");
System.out.println(card.tags()); // [JPA, Hibernate]

card.tags().add("ORM");          // Vẫn sửa được List gốc!
```

Có thể sao chép dữ liệu đầu vào để tránh chia sẻ mutable collection:

```java
import java.util.List;
import java.util.Objects;

public record BookCard(Long id, List<String> tags) {
    public BookCard {
        Objects.requireNonNull(id, "id");
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf()` tạo danh sách không cho sửa, đồng thời từ chối phần tử `null`. Nếu phần tử bên trong List vẫn là object mutable, cần cân nhắc **deep copy** ở mức thích hợp. Mảng và kiểu ngày cũ như `java.util.Date` cũng cần defensive copy nếu xuất hiện trong DTO bất biến.

Record có thể chứa method, static field và implement interface, nhưng **không thể extends một class khác**, mọi record đều là final và không thể khai báo thêm instance field ngoài các component. Đây là giới hạn quan trọng khi đặt cạnh entity của JPA.

## 4. Vì sao record thường không thích hợp để làm @Entity?

Một entity JPA tiêu chuẩn thường cần:

1. Một class không `final`, có constructor không tham số `public` hoặc `protected`.
2. Một định danh `@Id` hoặc `@EmbeddedId`.
3. Khả năng Hibernate dựng instance từ kết quả SQL, quản lý trạng thái và liên kết association.
4. Khả năng thực hiện lazy loading/proxy phù hợp với cấu hình, dirty checking và thay đổi trạng thái.

Record xung đột với các yêu cầu truyền thống đó: record là `final`, component field là `final`, canonical constructor cần đủ tham số; record cũng không có constructor rỗng theo dạng thông thường của JPA entity. Một số khả năng runtime đặc thù của Hibernate có thể nới lỏng vài yêu cầu JavaBean, nhưng **không nên suy diễn rằng record được hỗ trợ làm entity chỉ vì Hibernate hỗ trợ record trong những ngữ cảnh khác**.

Đoạn sau là ví dụ **không nên dùng làm entity portable**:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

// Ví dụ phản diện: không phải entity JPA chuẩn.
@Entity
public record BookRecord(
        @Id Long id,
        String title) {
}
```

Ngay cả nếu một version/provider có thể tạo instance qua cơ chế riêng, một record vẫn không phù hợp tự nhiên với cập nhật trạng thái của managed entity:

- Không có setter/field mutable để Hibernate áp dụng state transition như entity thông thường.
- Loại final cản trở các cách tạo proxy bằng subclass; lazy associations cần cơ chế phù hợp.
- Record dùng value equality theo mọi component, khác với định danh entity được ánh xạ bởi khóa chính.
- Một bản ghi trong database có thể đổi theo thời gian; một record hiện có giữ snapshot giá trị cũ, không phải object sống đang được theo dõi để phản ánh cập nhật.

**Lựa chọn mặc định:** dùng class JPA thông thường cho entity; dùng record cho projection/DTO. Với value object được nhúng, một số phiên bản Hibernate hỗ trợ record dạng `@Embeddable`, được giải thích ở phần sau.

## 5. Entity có thể đóng gói chặt mà vẫn mutable với Hibernate

Không phải entity nào cũng cần public setter cho mọi field. Có thể thiết kế API theo nghiệp vụ, giấu thay đổi trạng thái đằng sau method có kiểm tra invariant.

Ví dụ:

```java
package com.example.library.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private boolean available;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    protected Book() {
        // Constructor dành cho JPA/Hibernate.
    }

    public Book(String title, Author author) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        if (author == null) {
            throw new IllegalArgumentException("Thiếu tác giả");
        }
        this.title = title;
        this.author = author;
        this.available = true;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public boolean isAvailable() { return available; }
    public Author getAuthor() { return author; }
    public Long getVersion() { return version; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = newTitle;
    }

    public void markBorrowed() {
        if (!available) {
            throw new IllegalStateException("Sách đã được mượn");
        }
        available = false;
    }
}
```

Entity liên quan:

```java
package com.example.library.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "authors")
public class Author {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Author() {}

    public Author(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

Sử dụng `@Id` trên field chọn **field access**; Hibernate có thể truy cập field phù hợp thay vì phụ thuộc vào public setter. Khi một `Book` ở trạng thái managed, gọi `book.rename(...)` vẫn được Hibernate quan sát qua dirty checking và đồng bộ khi flush trong transaction.

```java
import org.hibernate.Session;
import org.hibernate.Transaction;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Book book = session.get(Book.class, 42L);
        if (book == null) {
            throw new IllegalArgumentException("Không có sách 42");
        }
        book.rename("Hibernate từ cơ bản đến nâng cao");
        tx.commit(); // Dirty checking → UPDATE khi cần.
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
```

Entity trên **không bất biến** ở mức Java state: nó chỉ hạn chế cách sửa trạng thái qua API nghiệp vụ. Thiết kế này rất phù hợp cho entity nghiệp vụ có chuyển trạng thái. Không nên đánh đồng “không có setter public” với “Hibernate sẽ không update”.

### Identity của entity khác equality của record

Record `BookSummary(42, "A")` và `BookSummary(42, "B")` không bằng nhau vì `title` khác nhau, dù chúng mô tả cùng ID. Trong Hibernate, hai entity được truy xuất cùng ID trong cùng persistence context thường có cùng Java object identity. Entity có thể thay đổi thuộc tính mà vẫn đại diện cho một thực thể.

Do đó, không nên tự động sinh `equals()/hashCode()` của entity dựa trên tất cả các field mutable theo cách record thực hiện. Khi định nghĩa equality cho entity, phải cân nhắc ID được sinh sau `persist()`, transient entity, proxy và các hash-based collection. Không nên chọn record cho entity chỉ để “có sẵn equals/hashCode”.

## 6. Immutable class: khi cần lớp bất biến nhưng không muốn dùng record

Một DTO bất biến có thể là class Java thông thường với `private final` fields và chỉ cung cấp constructor/getters:

```java
package com.example.library.readmodel;

import java.util.List;
import java.util.Objects;

public final class BookDetails {
    private final Long id;
    private final String title;
    private final List<String> tags;

    public BookDetails(Long id, String title, List<String> tags) {
        this.id = Objects.requireNonNull(id);
        this.title = Objects.requireNonNull(title);
        this.tags = List.copyOf(tags);
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public List<String> getTags() { return tags; }
}
```

Lựa chọn này hữu ích nếu cần:

- Tuân theo convention JavaBean `getXxx()` của một thư viện hoặc serializer cụ thể.
- Cung cấp nhiều constructor/factory method mang ý nghĩa nghiệp vụ.
- Tự quản lý cách triển khai `equals()/hashCode()` hoặc identity cho read model.
- Ẩn cách biểu diễn bên trong và giữ API public ổn định qua thời gian.
- Hỗ trợ những Java version chưa có record.

Immutable class không tự động trở thành Hibernate entity. Nếu class ở trên được dùng làm projection, Hibernate chỉ gọi constructor tương ứng. Nếu muốn class tương tự làm entity, các điều kiện JPA về non-final class, constructor rỗng, persistent fields và cách Hibernate khởi tạo state vẫn cần được xét. Một “immutable Java DTO” và một “immutable Hibernate entity” là hai thiết kế khác nhau.

Record thường ngắn và rõ cho dữ liệu phẳng; class bất biến hữu ích khi API hoặc logic khởi tạo cần tùy biến hơn. Cả hai đều có thể dùng làm projection.

## 7. Hibernate @Immutable: entity chỉ đọc từ góc nhìn ORM

Hibernate cung cấp `org.hibernate.annotations.Immutable` để đánh dấu một entity là bất biến đối với việc theo dõi thay đổi. Ví dụ một bảng danh mục gần như không thay đổi trong runtime:

```java
package com.example.library.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(name = "language_codes")
public class LanguageCode {
    @Id
    @Column(length = 10)
    private String code;

    @Column(nullable = false, length = 100)
    private String displayName;

    protected LanguageCode() {}

    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }
}
```

Các entity `LanguageCode` vẫn có định danh, được nạp và tham gia persistence context. Khác biệt là Hibernate **không dirty-check/flush UPDATE** từ các thay đổi trạng thái thông thường của entity được đánh dấu immutable. Điều này có thể giảm chi phí giữ snapshot phục vụ dirty checking đối với dữ liệu chỉ đọc.

Ví dụ minh họa hành vi cần tránh hiểu sai:

```java
LanguageCode language = session.get(LanguageCode.class, "vi");
// Không có setter được công khai trong thiết kế trên.
// Nếu reflection hay một method nội bộ thay đổi displayName,
// @Immutable vẫn khiến Hibernate bỏ qua việc UPDATE entity ấy
// qua cơ chế dirty checking thông thường.
```

**`@Immutable` không có nghĩa:**

- Hibernate tự khóa bảng ở database hoặc thu hồi quyền `UPDATE` của tài khoản JDBC.
- Mọi `INSERT`, `DELETE`, native SQL hoặc bulk DML đều bị chặn tuyệt đối.
- Mọi object mà entity tham chiếu đều trở thành bất biến sâu.
- Dữ liệu không thể bị sửa bởi tác nhân khác như migration, admin tool hoặc dịch vụ độc lập.

Với HQL/JPQL bulk update nhằm vào immutable entity, hành vi và mức cảnh báo/lỗi phụ thuộc cấu hình và phiên bản Hibernate. Không dựa vào `@Immutable` làm cơ chế bảo mật dữ liệu. Nếu một bảng phải bất biến ở mức hệ thống, cần thêm database privileges, constraint/trigger hoặc thiết kế nghiệp vụ append-only phù hợp.

### 7.1. Tại sao vẫn là class bình thường?

Entity `LanguageCode` vẫn:

- Có `@Entity` và `@Id`.
- Có protected no-arg constructor.
- Không khai báo class là `final`.
- Cho phép Hibernate dựng object theo mapping thông thường.

Annotation `@Immutable` quản lý **chính sách update** của ORM, không biến entity thành một Java record. Vì vậy hai thiết kế sau khác nhau về bản chất:

```java
@Entity
@Immutable
class LanguageCode { /* Entity có identity, được Session quản lý */ }

record LanguageOption(String code, String label) {
    // Projection thuần, không phải entity.
}
```

### 7.2. Đặc biệt cẩn thận với cache cấp hai

Dữ liệu tham chiếu ít thay đổi có thể phù hợp với Hibernate second-level cache, nhưng `@Immutable` **không tự bật second-level cache**. Cache cần cấu hình provider và region; với entity thật sự không bị thay đổi, chiến lược cache dạng read-only có thể phù hợp.

Nếu bảng được cập nhật ngoài ứng dụng, ngay cả entity `@Immutable` cũng có thể trở nên stale trong cache. Cần chiến lược invalidation/expiry phù hợp, hoặc không dùng cache cho dữ liệu đó. Chính sách bất biến ở ORM không biến database thành nguồn dữ liệu bất động.

## 8. Đừng nhầm @Immutable với read-only session và updatable=false

Hibernate/JPA có nhiều cơ chế ảnh hưởng tới cập nhật, nhưng ở các mức độ khác nhau:

| Cơ chế | Tác động chính | Phạm vi điển hình | Thích hợp khi |
|---|---|---|---|
| `@Immutable` trên entity | Hibernate bỏ qua update state qua dirty checking | Mapping của cả entity | Dữ liệu tham chiếu/đối tượng đọc gần như cố định |
| `session.setReadOnly(entity, true)` | Đánh dấu một managed instance là read-only trong session hiện tại | Một entity cụ thể | Một query/workload chỉ cần đọc |
| `session.setDefaultReadOnly(true)` | Mặc định load entity tiếp theo dưới dạng read-only | Một session | Xử lý các khối đọc có kiểm soát |
| `@Column(updatable = false)` | Không đưa cột đó vào SQL `UPDATE` do entity mapping tạo | Một cột | Cột chỉ được ghi khi insert, ví dụ createdAt |
| `@Transactional(readOnly = true)` | Hint/chính sách transaction của framework | Một method/transaction | Tối ưu hóa công việc đọc trong Spring |
| Quyền DB/constraint | Ngăn các thao tác trái phép tại database | Database/table/column | Bảo vệ dữ liệu độc lập với ứng dụng |

Với `@Column(updatable = false)`:

```java
import jakarta.persistence.Column;
import java.time.Instant;

@Column(nullable = false, updatable = false)
private Instant createdAt;
```

Hibernate không đưa `createdAt` vào SQL `UPDATE` được tạo từ mapping thông thường, nhưng các field khác của entity vẫn có thể cập nhật. Điều này không tự làm đối tượng Java bất biến.

Với `session.setDefaultReadOnly(true)` hoặc `setReadOnly(entity, true)`, không nên nhầm mục tiêu với “đọc nhất quán theo snapshot isolation”. Quy tắc nhất quán phụ thuộc transaction isolation của database. Cũng cần chú ý read-only flag có thể ảnh hưởng cách Hibernate dirty-check entity, không phải hệ thống quyền database.

Trong Spring, `@Transactional(readOnly = true)` thường là hint tối ưu cho transaction manager/ORM; tùy cấu hình nó có thể thay đổi flush mode hoặc hint với JDBC. Nó không phải một rào chắn chắc chắn chặn mọi SQL ghi. Nếu yêu cầu read-only là quy tắc an toàn, cần thiết kế quyền database và tầng nghiệp vụ thích hợp.

## 9. Record làm projection: mô hình đọc gọn và rõ

**Projection** là kết quả truy vấn chỉ bao gồm các trường cần thiết. Hibernate có thể tạo class hoặc record thông qua constructor expression của JPQL/HQL. Projection hữu ích cho danh sách, báo cáo, kết quả tổng hợp và response API.

Giả sử các entity `Book` và `Author` ở phần 5 đã mapping quan hệ `Book.author`. Một read model:

```java
package com.example.library.readmodel;

public record BookSummary(
        Long id,
        String title,
        String authorName) {}
```

Truy vấn theo JPA `EntityManager`:

```java
import com.example.library.readmodel.BookSummary;
import jakarta.persistence.EntityManager;
import java.util.List;

public List<BookSummary> findAvailableBooks(EntityManager em) {
    return em.createQuery(
            "select new com.example.library.readmodel.BookSummary(" +
            "    b.id, b.title, a.name" +
            ") " +
            "from Book b " +
            "join b.author a " +
            "where b.available = :available " +
            "order by b.id",
            BookSummary.class)
            .setParameter("available", true)
            .getResultList();
}
```

HQL/JPQL constructor expression `select new ...` yêu cầu tên class **đủ package** và constructor tương thích với thứ tự, kiểu dữ liệu của các expression. Với record, đó thường là canonical constructor. Nếu đổi `BookSummary(Long id, String title, String authorName)` thành thứ tự khác mà quên sửa query, Hibernate có thể báo lỗi xây dựng kết quả khi tạo/thực thi query.

Dòng dữ liệu:

```text
SELECT b.id, b.title, a.name
FROM ...
      │
      ▼
Hibernate đọc các scalar values
      │
      ▼
new BookSummary(id, title, authorName)
      │
      ▼
Record chỉ giữ giá trị; không nằm trong persistence context
```

Ví dụ trên **không yêu cầu** load toàn bộ `Book` hoặc toàn bộ `Author` thành managed entity chỉ để lấy ba giá trị, nếu truy vấn thực sự chỉ chọn ba scalar expression. Hibernate vẫn phải sử dụng SQL/join theo query. Projection không đảm bảo mọi truy vấn đều nhanh hơn: hiệu quả còn phụ thuộc index, bộ lọc, join, pagination và volume dữ liệu.

### 9.1. DTO projection là snapshot, không tự cập nhật

```java
BookSummary dto = em.createQuery(
        "select new com.example.library.readmodel.BookSummary(" +
        "b.id, b.title, a.name) " +
        "from Book b join b.author a where b.id = :id",
        BookSummary.class)
        .setParameter("id", 42L)
        .getSingleResult();

String title = dto.title();
// Không thể dto.setTitle(...); record không có setter.
// Hibernate không theo dõi BookSummary để UPDATE database.
```

Muốn đổi tiêu đề sách, hãy tải managed entity trong transaction và gọi method nghiệp vụ:

```java
Book managed = em.find(Book.class, dto.id());
managed.rename("Tiêu đề mới");
// Commit/flush trong transaction sẽ đồng bộ entity khi cần.
```

Projection không tự động trở thành managed entity nếu component tên là `id`. Việc nó chứa khóa chính chỉ giúp người dùng đọc dữ liệu hoặc dùng khóa đó để tải lại entity khi thực hiện lệnh ghi.

### 9.2. DTO record cũng phù hợp cho aggregate query

Một projection không bắt buộc tương ứng một row/entity. Có thể dùng cho báo cáo:

```java
package com.example.library.readmodel;

public record AuthorBookCount(Long authorId,
                              String authorName,
                              Long bookCount) {}
```

```java
List<AuthorBookCount> counts = em.createQuery(
        "select new com.example.library.readmodel.AuthorBookCount(" +
        "  a.id, a.name, count(b)" +
        ") " +
        "from Author a left join a.books b " +
        "group by a.id, a.name " +
        "order by a.name",
        AuthorBookCount.class)
        .getResultList();
```

Query `a.books` giả định `Author` có collection `@OneToMany(mappedBy = "author")`; lớp `Author` đơn giản ở phần 5 chưa khai báo collection này. Không có mapping `a.books`, cần viết query từ `Book` rồi join sang `Author` theo mô hình thực tế.

Khi dùng `count()`, kiểu kết quả JPQL phổ biến là `Long`. Với `sum`, `avg`, `coalesce` hoặc phép ép kiểu, phải kiểm tra loại giá trị của expression để constructor record khớp. Nếu bài toán dùng native SQL, có thể cần cơ chế result mapping riêng; không giả định mọi native query tự gọi constructor của record giống JPQL constructor expression.

### 9.3. Projection có thể trả về class bất biến

Không có quy định projection bắt buộc là record. Class bất biến có constructor phù hợp cũng dùng được:

```java
package com.example.library.readmodel;

public final class BookRow {
    private final Long id;
    private final String title;

    public BookRow(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

```java
List<BookRow> rows = em.createQuery(
        "select new com.example.library.readmodel.BookRow(b.id, b.title) " +
        "from Book b order by b.id",
        BookRow.class)
        .getResultList();
```

Chọn record khi cần data carrier ngắn gọn; chọn class khi cần API getter, tương thích tool cũ hoặc constructor/factory tùy biến.

## 10. Truy vấn chọn entity so với chọn projection

Hai query dưới đây có ý nghĩa khác nhau:

```java
// Query A: lấy entity được Session quản lý.
List<Book> entities = em.createQuery(
        "select b from Book b where b.available = true",
        Book.class)
        .getResultList();

// Query B: chỉ lấy các trường cần hiển thị.
List<BookSummary> summaries = em.createQuery(
        "select new com.example.library.readmodel.BookSummary(" +
        "  b.id, b.title, b.author.name" +
        ") " +
        "from Book b where b.available = true",
        BookSummary.class)
        .getResultList();
```

| Đặc tính | Entity query | DTO/record projection |
|---|---|---|
| Kết quả | Managed entity (khi session còn mở) | Object mới chỉ mang giá trị |
| Có persistence context identity | Có, với entity theo ID | Không cho DTO |
| Dirty checking | Có với entity mutable | Không |
| Lazy association | Có thể là proxy/collection lazy | Chỉ có dữ liệu được chọn vào DTO |
| Update nghiệp vụ | Tốt: tải entity và gọi domain method | Không cập nhật trực tiếp |
| Chỉ chọn một vài cột | Thường tải các cột cơ bản cần mapping entity; tùy fetch plan | Chủ động chọn expression/cột |
| Dùng ngoài transaction/session | Entity detached có rủi ro lazy loading | Thường thuận tiện nếu DTO chứa toàn scalar values |
| Equality | Cần quyết định theo identity/domain semantics | Record mặc định so sánh theo tất cả component |
| Mục đích | Domain model và thay đổi trạng thái | Read model, UI/API, báo cáo |

Khi một endpoint chỉ hiển thị 20 sách mới nhất, query projection và phân trang thường tạo hợp đồng dữ liệu gọn hơn. Khi xử lý “mượn sách”, “đổi tác giả” hay “hủy đơn”, entity managed và transaction bảo đảm thay đổi qua nghiệp vụ được Hibernate đồng bộ.

### Không đặt entity managed vào trong record rồi tưởng đã tách khỏi persistence context

Ví dụ:

```java
public record BookWrapper(Book book) {}
```

`BookWrapper` là record, nhưng component `book` vẫn là entity mutable. Nếu object `Book` còn managed trong session, sửa nó vẫn có thể phát sinh SQL. Nếu detached, association lazy chưa khởi tạo vẫn có thể gây lỗi khi truy cập. Record chỉ bất biến đối với **tham chiếu**, không làm đối tượng được tham chiếu bất biến hoặc detached.

Để DTO độc lập với Hibernate, nên chọn scalar values hoặc các value object bất biến thích hợp:

```java
public record BookResponse(Long id,
                           String title,
                           String authorName,
                           boolean available) {}
```

Nếu cần nested DTO, chuyển dữ liệu trước khi đóng session. Cẩn thận tránh phát sinh N+1 query trong vòng lặp mapping entity sang DTO.

## 11. Record làm @Embeddable: trường hợp khác với @Entity

Một **embeddable** là value object được lưu như một phần của entity sở hữu nó. Không giống entity, embeddable thường không có ID và không có persistence lifecycle độc lập.

Từ các phiên bản Hibernate ORM 6.2 trở lên, Hibernate có hỗ trợ Java record dùng làm embeddable trong những mapping phù hợp. Ví dụ:

```java
package com.example.library.domain;

import jakarta.persistence.Embeddable;

@Embeddable
public record PostalAddress(String street, String city) {}
```

Entity sở hữu:

```java
package com.example.library.domain;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "members")
public class Member {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "street",
                column = @Column(name = "shipping_street")),
        @AttributeOverride(name = "city",
                column = @Column(name = "shipping_city"))
    })
    private PostalAddress shippingAddress;

    protected Member() {}

    public void changeShippingAddress(String street, String city) {
        this.shippingAddress = new PostalAddress(street, city);
    }

    public PostalAddress getShippingAddress() {
        return shippingAddress;
    }
}
```

Lược đồ có thể là:

```sql
CREATE TABLE members (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    shipping_street VARCHAR(255),
    shipping_city VARCHAR(255)
);
```

Tại thời điểm Hibernate đọc bản ghi, nó dựng `PostalAddress` từ các cột tương ứng. Vì record không cho sửa `street` hay `city`, thao tác nghiệp vụ thường **thay toàn bộ giá trị**:

```java
Member member = em.find(Member.class, memberId);
member.changeShippingAddress(
        "123 Nguyen Trai", "Ha Noi");
// Flush/commit sẽ xét thay đổi của entity Member.
```

Điểm mấu chốt:

- `Member` vẫn là managed entity bình thường; `PostalAddress` chỉ là giá trị thuộc entity.
- Record `PostalAddress` không có `@Id` riêng, không cần identity map theo khóa riêng.
- Quy tắc record embeddable là **khả năng của Hibernate/version**. Nếu dự án cần chạy trên nhiều JPA provider hoặc phiên bản cũ, hãy kiểm tra hỗ trợ thực tế hoặc dùng embeddable class với no-arg constructor.
- Không mặc định mọi kiểu dùng `@Embeddable` đều có thể biến thành record, nhất là trường hợp composite identifier, association lồng nhau hoặc cấu hình đặc thù của provider. Cần xác định hỗ trợ theo phiên bản đang dùng.

### 11.1. Embeddable class khi cần tính portable

Một kiểu truyền thống:

```java
import jakarta.persistence.Embeddable;

@Embeddable
public class PostalAddressValue {
    private String street;
    private String city;

    protected PostalAddressValue() {}

    public PostalAddressValue(String street, String city) {
        this.street = street;
        this.city = city;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
}
```

Đây là class không có setter public, nhưng Hibernate vẫn có thể điền các field theo field access. Tính bất biến ở mức API khác với việc class có mọi field `final`. Cần chấp nhận ràng buộc khởi tạo của ORM nếu muốn mapping portable.

### 11.2. Tránh nhầm embeddable với JSON/serialized value

`@Embedded` thường ánh xạ các thuộc tính của value object thành các cột trong **bảng của entity sở hữu**. Nó không tự động tạo một cột JSON hoặc serialize cả record vào một blob. Nếu dùng JSON mapping, custom type hoặc converter, đó là cơ chế khác với cấu trúc `@Embeddable` thông thường và cần cấu hình tương ứng.

## 12. Có nên dùng record làm identifier?

Một composite identifier biểu diễn nhiều cột khóa, ví dụ `OrderLineId(orderId, lineNumber)`. Record có value equality tiện lợi, nên dễ nảy sinh ý tưởng dùng record làm ID.

Tuy nhiên, composite ID là phần giao giữa specification của JPA và cách Hibernate hỗ trợ các loại embeddable/identifier:

- Đối với mã cần **portable JPA**, dạng ID class hoặc embeddable class theo yêu cầu specification và provider đích là lựa chọn dễ dự đoán hơn.
- Một số phiên bản Hibernate hỗ trợ record trong những dạng embeddable, nhưng không suy ra mọi loại `@EmbeddedId`, `@IdClass` hay composite key record đều chạy được trên mọi version.
- Identifier phải **ổn định** trong vòng đời entity. Thay đổi thành phần khóa sau khi entity đã managed là một vấn đề khác hoàn toàn với thay toàn bộ embeddable địa chỉ.

Ví dụ lựa chọn truyền thống:

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {
    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {}

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() { return orderId; }
    public Integer getLineNumber() { return lineNumber; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

Class này đáp ứng mẫu thông dụng cho embeddable composite key: có no-arg constructor, `Serializable`, `equals()`/`hashCode()` theo các thành phần khóa. Việc chọn chính xác giữa `@EmbeddedId` và `@IdClass` còn phụ thuộc quan hệ và schema của bài toán.

## 13. Vòng đời dữ liệu: chọn kiểu nào cho từng use case?

Sơ đồ quyết định:

```text
Đối tượng có định danh và cần Hibernate quản lý vòng đời?
                  │
           ┌──────┴──────┐
           │             │
          Có            Không
           │             │
           ▼             ▼
     @Entity class   Có là giá trị thuộc về entity?
           │             │
           │       ┌─────┴─────┐
           │       │           │
           │      Có          Không
           │       │           │
           │       ▼           ▼
           │   @Embeddable    Projection / DTO
           │   class/record      │
           │   (tùy version)    ├── record: data carrier gọn
           │                    └── immutable class: API linh hoạt
           ▼
   Có cần thay đổi trạng thái qua transaction?
           │
      ┌────┴────┐
      │         │
     Có        Không
      │         │
      ▼         ▼
 Managed       @Immutable entity
 mutable       nếu DB row là dữ liệu chỉ đọc
 entity        đối với Hibernate
```

Một số tình huống cụ thể:

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Sách có trạng thái còn/mượn, thay đổi theo nghiệp vụ | `Book @Entity` dạng class mutable có method kiểm tra invariant | Có ID, version, dirty checking và transaction |
| Danh sách sách với ID, title, authorName | `record BookSummary(...)` | Chỉ đọc vài cột, không cần entity tracking |
| Bảng mã ngôn ngữ, quốc gia rất ít thay đổi | `@Entity @Immutable` dạng class | Vẫn tham chiếu bằng ID, ánh xạ quan hệ; giảm dirty checking |
| Địa chỉ giao hàng là giá trị của Member | `@Embeddable` class hoặc record khi Hibernate/version hỗ trợ | Không có identity độc lập, thay theo toàn bộ giá trị |
| Báo cáo số sách theo tác giả | `record AuthorBookCount(...)` | Kết quả aggregate, không đại diện entity |
| Command yêu cầu thay trạng thái đơn hàng | Entity managed với domain method và `@Version` | Cần commit, rollback và kiểm soát cạnh tranh |
| Payload API bất biến, cần getter JavaBean/serializer cũ | Immutable Java class | Điều khiển API và khả năng tương thích |
| Bản snapshot/audit phải lưu nhiều phiên bản | Entity riêng cho từng audit row hoặc mô hình append-only | Bất biến nghiệp vụ cần quy tắc ghi/lưu lâu dài |
| Dữ liệu cập nhật bên ngoài nhưng ứng dụng chỉ xem | Projection hoặc entity read-only với chiến lược refresh/cache thích hợp | Tránh đồng bộ nhầm và giữ freshness có chủ đích |

Lựa chọn này không phải quy tắc tuyệt đối. Ví dụ danh mục rất nhỏ có thể lấy qua DTO record nếu chỉ hiển thị. `@Immutable` có ích khi chính bảng danh mục còn được tham chiếu bởi entity khác qua relationship hoặc cần truy vấn như entity.

## 14. Immutable entity trong hệ thống có transaction và concurrency

Một entity đọc-only không tự bảo đảm tính nhất quán của một nghiệp vụ đọc và ghi nhiều bước.

Ví dụ người dùng mở màn hình sửa sách:

1. Transaction A query `BookSummary(42, "Tên cũ", "Linh")`.
2. Transaction B thay đổi tên sách và commit.
3. Người dùng ở transaction A gửi yêu cầu sửa theo dữ liệu đã xem.
4. Application phải tải entity hiện tại và quyết định có cho sửa dựa trên version/điều kiện nghiệp vụ.

Record ở bước 1 là một **snapshot giá trị của kết quả truy vấn**; nó không tự theo dõi thay đổi từ database. Không dùng “record immutable” như lời bảo đảm database không đổi trong khoảng thời gian người dùng đang xem.

Trong entity `Book` ở phần 5, `@Version` hỗ trợ optimistic locking khi entity được update. Nếu client cần phát hiện stale update qua request riêng, ứng dụng có thể trả cả version trong DTO:

```java
public record BookEditView(Long id,
                           String title,
                           Long version) {}
```

Sau đó service kiểm tra phiên bản hợp lệ khi xử lý command và dùng transaction phù hợp. Hệ thống vẫn phải xử lý optimistic-lock exception hoặc xung đột cập nhật. Việc chỉ đọc version trong record không tự kích hoạt khóa.

Ngược lại, `@Immutable` trên entity `LanguageCode` có ý nghĩa “ứng dụng không cập nhật danh mục này qua dirty checking”. Nó không chặn migration/admin sửa bảng. Khi database thay đổi bên ngoài, persistence context hoặc second-level cache có thể giữ dữ liệu cũ đến khi refresh/evict hoặc tạo session mới theo chính sách cache.

## 15. Ranh giới giữa entity, DTO và API response

Một lỗi kiến trúc phổ biến là đưa entity trực tiếp vào JSON response, rồi phụ thuộc vào serializer truy cập lazy association. Điều đó có thể kéo theo:

- `LazyInitializationException` nếu session đã đóng.
- N+1 query nếu serializer lặp qua nhiều association khi session vẫn mở.
- Vòng tham chiếu hai chiều trong đồ thị entity.
- Lộ field nội bộ mà API không có ý định công bố.
- Client vô tình phụ thuộc cấu trúc mapping của database.

Record DTO giúp xác định hợp đồng response:

```java
public record BookListItem(
        Long id,
        String title,
        String authorName,
        boolean available) {}
```

Trong tầng truy vấn, lấy đúng trường cần rồi trả dữ liệu:

```java
public List<BookListItem> listBookItems(EntityManager em) {
    return em.createQuery(
            "select new com.example.library.readmodel.BookListItem(" +
            "b.id, b.title, a.name, b.available) " +
            "from Book b join b.author a order by b.id",
            BookListItem.class)
            .setMaxResults(50)
            .getResultList();
}
```

`BookListItem` cần được đặt đúng package `com.example.library.readmodel` như tên HQL. Kết quả chứa giá trị thuần, nên phần JSON không cần truy cập thêm relationship lazy. Trong hệ thống có nhiều dữ liệu, bổ sung filter, phân trang ổn định và index tương ứng thay vì luôn trả tất cả row.

Không bắt buộc dùng record chung cho tầng persistence và public API. API contract có thể cần versioning, field name riêng hoặc mapping từ internal read model sang response model khác. Đặc biệt, thêm một component vào record làm thay đổi canonical constructor và các chỗ khởi tạo theo vị trí, nên cần cân nhắc compatibility của query và consumer.

### 15.1. N+1 không tự biến mất vì chọn record

Nếu làm theo cách:

```java
List<Book> books = em.createQuery(
        "select b from Book b", Book.class).getResultList();

List<BookListItem> results = books.stream()
        .map(b -> new BookListItem(
                b.getId(),
                b.getTitle(),
                b.getAuthor().getName(),
                b.isAvailable()))
        .toList();
```

Thì `b.getAuthor().getName()` có thể kích hoạt các query bổ sung cho association lazy. Có record ở kết quả không khắc phục được việc dữ liệu đầu vào đã được tải theo cách gây N+1.

Query constructor projection với join chủ động chọn `a.name` thường rõ hơn cho use case danh sách. Tuy nhiên join qua quan hệ collection, phân trang và aggregate cần được thiết kế cẩn thận để tránh duplicate rows hoặc kết quả page sai.

### 15.2. Projection có thể chứa null

Giả sử quan hệ `Book.author` là optional và query dùng `left join`, `a.name` có thể là `null`. Nếu record constructor yêu cầu non-null, query sẽ thất bại khi gặp sách không có tác giả. Giải pháp nằm ở hợp đồng dữ liệu: cho phép null có chủ đích, dùng `coalesce(a.name, 'Chưa rõ')` hoặc loại bản ghi không phù hợp bằng predicate. Không xóa validation chỉ để che lỗi schema không mong muốn.

## 16. Tối ưu bộ nhớ và hiệu năng: đừng chọn theo cú pháp ngắn nhất

Chi phí của một query Hibernate gồm SQL, network, JDBC row materialization, entity hydration, persistence context, dirty checking và serialization. Projection có thể giảm một số chi phí đó, nhưng tối ưu còn phụ thuộc loại query.

| Yếu tố | Khi tải entity | Khi dùng projection scalar → record |
|---|---|---|
| Cột được chọn | Theo mapping/fetch plan entity | Chỉ expression được yêu cầu |
| Entity state tracking | Có với managed entity | Không cho bản thân DTO |
| First-level cache | Được quản lý theo identity | Record không đặt vào identity map |
| Dirty checking | Có với entity mutable | Không cho record |
| Quan hệ lazy | Có thể tạo proxy và bị truy cập sau đó | Chỉ chứa dữ liệu đã truyền vào constructor |
| DTO allocation | Có thể cần bước mapping thêm | Record được tạo trực tiếp từ query |
| SQL join | Phụ thuộc fetch plan/query | Phụ thuộc HQL/JPQL expression |
| Dùng cho update | Phù hợp | Cần tải entity mới cho command |

Những lưu ý thực tế:

- Projection chỉ tiết kiệm khi query thật sự chọn ít dữ liệu hơn hoặc tránh managed entities không cần thiết.
- Entity có lợi nếu cùng transaction đã tải entity đó và cần thực hiện nhiều thao tác liên quan; identity map tránh tạo nhiều managed instances cho cùng định danh.
- Projection trả về số lượng lớn vẫn tiêu tốn bộ nhớ cho mỗi record; hãy phân trang, stream/chunk hoặc batch phù hợp.
- Record với nhiều string, list, nested DTO không miễn phí. Deep copy làm tăng allocation nhưng cần thiết khi yêu cầu immutable thật.
- Không đưa `List<Book>` managed entity vào record rồi kỳ vọng loại bỏ chi phí persistence context.

Đối với dữ liệu chỉ đọc hiếm thay đổi, entity `@Immutable` và second-level cache có thể là một tối ưu khác với projection. Chọn dựa trên nhu cầu truy vấn, tần suất cập nhật và consistency, không dựa trên việc loại nào “mới” hơn.

## 17. Một luồng hoàn chỉnh: đọc bằng record, ghi bằng entity

Đây là cách kết hợp hai loại biểu diễn trong service của ứng dụng.

**Đọc danh sách** dùng projection:

```java
package com.example.library.service;

import com.example.library.readmodel.BookSummary;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookQueryService {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public List<BookSummary> findAvailable() {
        return em.createQuery(
                "select new com.example.library.readmodel.BookSummary(" +
                "b.id, b.title, a.name) " +
                "from Book b join b.author a " +
                "where b.available = true order by b.id",
                BookSummary.class)
                .setMaxResults(100)
                .getResultList();
    }
}
```

**Ghi thay đổi** dùng entity managed:

```java
package com.example.library.service;

import com.example.library.domain.Book;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookCommandService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void borrow(Long bookId) {
        Book book = em.find(Book.class, bookId);
        if (book == null) {
            throw new IllegalArgumentException("Không tìm thấy sách");
        }
        book.markBorrowed();
        // Khi transaction commit, Hibernate flush khi cần.
    }
}
```

Hai service này cùng sử dụng mapping `Book` nhưng có nhiệm vụ khác nhau:

```text
GET /books
    → BookQueryService
    → SELECT id, title, authorName
    → List<BookSummary> (record)
    → JSON response

POST /books/42/borrow
    → BookCommandService
    → EntityManager.find(Book.class, 42)
    → Book managed, book.markBorrowed()
    → Transaction commit → UPDATE books ...
```

Ví dụ dùng Spring `@Transactional` để trình bày ranh giới nghiệp vụ. Ứng dụng Hibernate thuần có thể thực hiện tương tự bằng `SessionFactory.openSession()` và `Transaction`, quản lý commit/rollback/close bằng try/finally. Lựa chọn record hay entity không thay thế chính sách transaction của ứng dụng.

## 18. Sai lầm hay gặp và cách suy nghĩ đúng

| Quan niệm hoặc cách viết | Vì sao có vấn đề | Hướng xử lý |
|---|---|---|
| “Record là immutable nên dùng ngay làm `@Entity`” | Record final, final fields, constructor và lifecycle không phù hợp yêu cầu entity JPA thông thường | Entity dùng class; record cho DTO/projection hoặc embeddable được hỗ trợ |
| “Không có setter thì Hibernate không update” | Với field access, dirty checking vẫn quan sát field thay đổi qua method nghiệp vụ | Phân biệt đóng gói API với `@Immutable` |
| “`@Immutable` bảo vệ database khỏi mọi update” | Native SQL, bulk DML, admin và dịch vụ khác có thể thay dữ liệu | Thêm ràng buộc và quyền DB nếu bất biến là quy tắc bắt buộc |
| “Record giữ một List thì cả List bất biến” | Record chỉ đóng băng tham chiếu | Defensive copy; cân nhắc deep copy |
| “Projection có ID nên Hibernate quản lý như entity” | DTO không được gắn vào persistence context | Muốn ghi, tải entity managed trong transaction |
| “Record tránh mọi N+1” | N+1 phụ thuộc cách query/fetch association | Chọn scalar projection và join/fetch phù hợp |
| “`@Transactional(readOnly=true)` cấm update ở DB” | Thường là hint tối ưu hóa, không phải cơ chế authorization | Thiết kế quyền và transaction/database policy |
| “`@Embeddable` record dùng được trên mọi JPA provider” | Hỗ trợ phụ thuộc JPA/Hibernate version và kiểu mapping | Kiểm tra compatibility hoặc dùng embeddable class |
| “Projection snapshot luôn phản ánh database mới nhất” | Giá trị có thể cũ ngay khi transaction khác commit | Xác định freshness; re-query/locking/version khi cần |
| “Entity `@Immutable` luôn hợp cho bảng ít cập nhật” | Có thể cần update định kỳ, invalidate cache, bulk maintenance | Thiết kế lifecycle cập nhật dữ liệu tham chiếu rõ ràng |
| “Chỉ đổi tên component record, query không ảnh hưởng” | Constructor expression dựa vào thứ tự/kiểu, Java API phụ thuộc accessor | Đồng bộ read model, HQL và response contract |

## 19. Tự xây mô hình lựa chọn từ yêu cầu nghiệp vụ

Giả sử hệ thống thư viện có bốn nhu cầu:

**Nhu cầu A — Thay đổi trạng thái mượn/trả.** Sách có ID, version và trạng thái thay đổi trong transaction. Chọn entity class `Book`, API nghiệp vụ `markBorrowed()`/`markReturned()`, `@Version` khi cần kiểm soát xung đột. Không dùng record làm entity.

**Nhu cầu B — Hiển thị 20 sách mới nhất.** Giao diện chỉ cần ID, tiêu đề, tác giả. Chọn `BookSummary` record thông qua constructor projection và phân trang có thứ tự ổn định. Không truyền nguyên entity graph tới HTTP response.

**Nhu cầu C — Mã ngôn ngữ xuất bản.** Bảng `language_codes` có ID và thường chỉ đọc. Nếu nhiều entity cần tham chiếu nó như một entity, có thể dùng `LanguageCode @Entity @Immutable`. Nếu chỉ cần danh sách chọn, projection `LanguageOption` cũng có thể đủ.

**Nhu cầu D — Địa chỉ thành viên.** Địa chỉ không có ID riêng, được lưu thành các cột trong bảng `members` và thường được thay theo toàn bộ giá trị. Dùng `@Embeddable` class, hoặc record khi stack Hibernate hỗ trợ mapping đó. Không cần lập một entity riêng chỉ vì muốn dùng record.

Từ bốn nhu cầu ấy có thể rút ra tiêu chí quan trọng nhất: **vai trò của đối tượng trong persistence lifecycle**, sau đó mới tới mong muốn bất biến và cú pháp Java.

## 20. Ghi nhớ ranh giới trách nhiệm

```text
JAVA RECORD / IMMUTABLE DTO CLASS
  ├─ Giữ giá trị cho read model / API / báo cáo
  ├─ Có constructor và API bất biến theo thiết kế
  └─ Không được Hibernate quản lý như entity

JPA / HIBERNATE ENTITY CLASS
  ├─ Có định danh, mapping, lifecycle
  ├─ Có thể managed trong Session / EntityManager
  ├─ Có thể dirty-check và UPDATE trong transaction
  └─ Có thể giới hạn API sửa thông qua domain method

@IMMUTABLE ENTITY
  ├─ Vẫn là entity có ID và mapping
  ├─ Hibernate xem trạng thái entity là read-only cho dirty checking
  └─ Không tự tạo ràng buộc bất biến toàn database

@EMBEDDABLE VALUE OBJECT
  ├─ Thuộc về entity khác; không có lifecycle entity độc lập
  ├─ Class thường là lựa chọn portable
  └─ Record hỗ trợ trong một số Hibernate version/mapping
```

Khi thiết kế Hibernate, hãy hỏi lần lượt: **Đây có phải một thực thể được quản lý theo định danh không? Trạng thái của nó có cần được cập nhật qua transaction không? Nó chỉ là giá trị thuộc thực thể khác hay là dữ liệu chiếu của một truy vấn?** Trả lời ba câu hỏi này sẽ giúp chọn giữa entity class, immutable entity, embeddable và record DTO một cách nhất quán.
